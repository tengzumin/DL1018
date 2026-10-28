#!/usr/bin/env python3
"""TRAIN_C5_24 noncausal teacher labels plus scene-grouped causal GRU distillation."""
from __future__ import annotations

import hashlib
import json
import os
import random
import time
from pathlib import Path

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

import numpy as np
import torch
from torch.nn import functional as F

import fit_task_aware_fourfold_v1 as fit
from task_aware_common import (DATA_PATH, DATA_MANIFEST_PATH, SOURCE_LOCK_PATH,
                               FILTER_LIMIT, load_locked_inputs, sha256)
import probe_task_position_feasibility_oracle_v1 as oracle


OUT = Path(__file__).resolve().parent
TEACHER_NPZ = OUT / "TRAIN24_FEASIBILITY_TEACHER_DELTAS_v1.npz"
TEACHER_META = OUT / "TRAIN24_FEASIBILITY_TEACHER_MANIFEST_v1.json"
OOF_NPZ = OUT / "TRAIN24_TEACHER_DISTILLATION_OOF_v1.npz"
RESULTS_JSON = OUT / "TRAIN24_TEACHER_DISTILLATION_RESULTS_v1.json"
SOURCE_LOCK = OUT / "TRAIN24_TEACHER_DISTILLATION_SOURCE_LOCK_v1.json"
CKPT_DIR = OUT / "teacher_distill_checkpoints"
NO_TASK_OOF = OUT.parent / "gru_residual_cv_v1/CV_OOF_PREDICTIONS_v1.npz"
TASK_OOF = OUT / "TASK_AWARE_CV_OOF_v1.npz"
NO_TASK_SHA = "9dc29cc2d94b990bafc2bdf77cc8c704fb14e2c0582987e3057cd6464e177d0f"
TASK_SHA = "a92c61662fa2fee8faf11d97b1f0234db13f6875c1cc6036098d71f3dccf5dcd"
SEED = 20261028
STEPS = 300
LR = 1e-3
TEACHER_STEPS = 15
TEACHER_STEP = 0.02
MAX_BACKTRACK = 8
POS_TOL = 1e-8


def write_json(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def pos_rmse(action: np.ndarray, target: np.ndarray, ready: np.ndarray) -> float:
    e = action[ready].astype(np.float64) - target[ready].astype(np.float64)
    return float(np.sqrt(np.mean(e * e)))


def solve_teacher(i: int, sid: str, bundle: dict, base_event: np.ndarray,
                  target: np.ndarray, ready: np.ndarray, event_t: np.ndarray) -> tuple[np.ndarray, dict]:
    tr, mask, beta, base, y, action_from_delta, p_mse_fn, t_mse_fn = oracle.candidate_tensors(
        i, bundle, base_event, target, ready, event_t)
    delta = torch.zeros((1, len(event_t[i]), 3), dtype=torch.float64, requires_grad=True)
    baseline_action = np.clip(base_event[i], -fit.ACTION_LIMIT, fit.ACTION_LIMIT)
    cap_rmse = pos_rmse(baseline_action, target[i], ready[i])
    history = []
    stopped = "fixed_iteration_budget"
    for it in range(TEACHER_STEPS):
        action, _ = action_from_delta(delta)
        p_loss, t_loss = p_mse_fn(action), t_mse_fn(action)
        gp = torch.autograd.grad(p_loss, delta, retain_graph=True)[0]
        gt = torch.autograd.grad(t_loss, delta)[0]
        direction = -gt.detach()
        pos_dir = torch.sum(gp.detach() * direction)
        gp_norm = torch.linalg.vector_norm(gp.detach())
        if float(pos_dir) > 0.0 and float(gp_norm) > 1e-20:
            direction = direction - (pos_dir / gp.detach().square().sum().clamp_min(1e-30)) * gp.detach()
        dnorm = torch.linalg.vector_norm(direction)
        if float(dnorm) <= 1e-20:
            stopped = "no_nonzero_projected_task_descent"
            break
        if float(gp_norm) > 1e-20:
            direction = direction - 0.02 * dnorm * gp.detach() / gp_norm
        direction = direction / direction.abs().max().clamp_min(1e-30)
        accepted = False
        cur_task = float(t_loss.detach())
        for bt in range(MAX_BACKTRACK + 1):
            step = TEACHER_STEP * (0.5 ** bt)
            with torch.no_grad():
                proposal = torch.where(mask[:, :, None],
                                       (delta.detach() + step * direction).clamp(-fit.DELTA_LIMIT, fit.DELTA_LIMIT),
                                       torch.zeros_like(delta))
                p_action, p_delta = action_from_delta(proposal)
                p_now = float(p_mse_fn(p_action))
                if p_now > (cap_rmse + POS_TOL) ** 2:
                    continue
                t_now = float(t_mse_fn(p_action))
                if np.isfinite(t_now) and t_now < cur_task - 1e-14:
                    delta = proposal.detach().requires_grad_(True)
                    accepted = True
                    history.append({"step": it + 1, "backtrack": bt,
                                    "position_residual_rmse_mps2": float(np.sqrt(p_now)),
                                    "task_so3_rmse_rad": float(np.sqrt(t_now)),
                                    "max_abs_delta_mps2": float(p_delta.abs().max())})
                    break
        if not accepted:
            stopped = "no_feasible_task_decrease_within_fixed_backtracking_budget"
            break

    with torch.no_grad():
        action_t, delta_t = action_from_delta(delta)
        pos_final = float(torch.sqrt(p_mse_fn(action_t)))
        task_final = float(torch.sqrt(t_mse_fn(action_t)))
    delta_np = delta_t[0].detach().cpu().numpy().astype(np.float32)
    action_np = action_t[0].detach().cpu().numpy().astype(np.float32)
    base_task = fit.evaluate_task_action(i, baseline_action, tr)
    task_final_scipy = fit.evaluate_task_action(i, action_np, tr)
    return delta_np, {
        "scene_id": sid, "scene_index": i,
        "position_constraint_cap_residual_rmse_mps2": cap_rmse,
        "teacher_position_residual_rmse_mps2": pos_final,
        "teacher_position_residual_cap_excess_mps2": max(0.0, pos_final - cap_rmse),
        "c5_frozen_task_so3_rmse_rad": base_task,
        "teacher_frozen_task_so3_rmse_rad_torch": task_final,
        "teacher_frozen_task_so3_rmse_rad_scipy": task_final_scipy,
        "torch_scipy_abs_diff_rad": abs(task_final - task_final_scipy),
        "optimizer": {"accepted_steps": len(history), "step_budget": TEACHER_STEPS,
                      "max_backtracking_trials": MAX_BACKTRACK + 1,
                      "initial_max_delta_step_mps2": TEACHER_STEP, "stop_reason": stopped,
                      "history": history},
        "delta": {"max_abs_mps2": float(np.abs(delta_np).max()),
                  "ready_clip_abs_ge_0_5_fraction": float(np.mean(np.abs(delta_np[ready[i]]) >= fit.DELTA_LIMIT)),
                  "warmup_abs_max_mps2": float(np.abs(delta_np[:31]).max()),
                  "ready_event_count": int(ready[i].sum())},
        "total_action_clip_abs_ge_3_fraction": float(np.mean(np.abs(action_np) >= fit.ACTION_LIMIT)),
    }


def metric_bundle(actions: np.ndarray, target: np.ndarray, ready: np.ndarray,
                  ids: list[str], trajectories: list[dict]) -> dict:
    per_pos = {}
    per_task = {}
    for i, sid in enumerate(ids):
        per_pos[sid] = pos_rmse(actions[i], target[i], ready[i])
        per_task[sid] = fit.evaluate_task_action(i, actions[i], trajectories[i])
    err_list = [actions[i, ready[i]].astype(np.float64) - target[i, ready[i]].astype(np.float64)
                for i in range(len(ids))]
    pool = np.concatenate(err_list, axis=0)
    return {"position_residual_rmse_scene_macro_mps2": float(np.mean(list(per_pos.values())),),
            "position_residual_rmse_pooled_mps2": float(np.sqrt(np.mean(pool ** 2))),
            "task_frozen_SO3_rmse_scene_macro_rad": float(np.mean(list(per_task.values()))),
            "task_frozen_SO3_rmse_pooled_rad": float(np.sqrt(np.mean(np.square(list(per_task.values()))))),
            "per_scene_position_residual_rmse_mps2": per_pos,
            "per_scene_task_frozen_SO3_rmse_rad": per_task}


def main() -> None:
    for p in (TEACHER_NPZ, TEACHER_META, OOF_NPZ, RESULTS_JSON, SOURCE_LOCK):
        if p.exists():
            raise RuntimeError(f"Refusing to overwrite {p}")
    CKPT_DIR.mkdir(parents=True, exist_ok=True)
    if any(CKPT_DIR.iterdir()):
        raise RuntimeError(f"Refusing to overwrite checkpoint in {CKPT_DIR}")
    torch.set_num_threads(1)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    torch.use_deterministic_algorithms(True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    t_all = time.perf_counter()
    bundle = load_locked_inputs()
    data, manifest = bundle["arrays"], bundle["manifest"]
    ids = data["scene_ids"].astype(str).tolist()
    if len(ids) != 24:
        raise RuntimeError("Expected exactly 24 TRAIN_C5 scenes")
    target = data["target_interval_clip_mps2"].astype(np.float32)
    ready = data["ready_mask"].astype(bool)
    base_event = data["applied_acceleration_event_mps2"].astype(np.float32)
    event_t = data["event_time_s"].astype(np.float64)
    teacher = np.zeros_like(base_event, dtype=np.float32)
    teacher_meta = {}

    # Verify the comparison OOF heads are the already-audited artifacts and same exact scenes/targets.
    if sha256(NO_TASK_OOF) != NO_TASK_SHA or sha256(TASK_OOF) != TASK_SHA:
        raise RuntimeError("Matched OOF control hash changed")
    with np.load(NO_TASK_OOF, allow_pickle=False) as z:
        no_ids = z["scene_ids"].astype(str).tolist()
        no_action = z["prediction_lambda_0_01"].astype(np.float32)
        if no_ids != ids or not np.array_equal(z["ready_mask"], ready) or not np.array_equal(z["target_clip_mps2"], target):
            raise RuntimeError("Ordinary-head OOF binding mismatch")
    with np.load(TASK_OOF, allow_pickle=False) as z:
        task_ids = z["scene_ids"].astype(str).tolist()
        task_action = z["task_action_lambda_task_0_1"].astype(np.float32)
        task_fold = z["fold_id"].astype(str).tolist()
        if task_ids != ids or not np.array_equal(z["ready_mask"], ready) or not np.array_equal(z["target_clip_mps2"], target):
            raise RuntimeError("Task-head OOF binding mismatch")
    expected_fold = {sid: f["fold_id"] for f in manifest["scene_folds"] for sid in f["holdout_scene_ids"]}
    if task_fold != [expected_fold[sid] for sid in ids]:
        raise RuntimeError("Task-head OOF fold assignment mismatch")

    t_teacher = time.perf_counter()
    for i, sid in enumerate(ids):
        start = time.perf_counter()
        teacher[i], teacher_meta[sid] = solve_teacher(i, sid, bundle, base_event, target, ready, event_t)
        teacher_meta[sid]["elapsed_seconds"] = time.perf_counter() - start
        if (teacher_meta[sid]["teacher_position_residual_cap_excess_mps2"] > POS_TOL + 1e-12 or
                teacher_meta[sid]["torch_scipy_abs_diff_rad"] > 1e-9 or
                teacher_meta[sid]["delta"]["warmup_abs_max_mps2"] != 0.0 or
                not np.isfinite(teacher[i]).all()):
            raise RuntimeError(f"{sid}: teacher feasibility, SO3 parity, warmup, or finite check failed")
        print(json.dumps({"teacher_scene": sid, "elapsed_seconds": teacher_meta[sid]["elapsed_seconds"],
                          "accepted_steps": teacher_meta[sid]["optimizer"]["accepted_steps"],
                          "position_residual_rmse": teacher_meta[sid]["teacher_position_residual_rmse_mps2"],
                          "task_so3_rmse_rad": teacher_meta[sid]["teacher_frozen_task_so3_rmse_rad_torch"]}), flush=True)
    teacher_elapsed = time.perf_counter() - t_teacher
    np.savez_compressed(TEACHER_NPZ, scene_ids=np.asarray(ids), fold_id=data["fold_id"].astype(str),
                        ready_mask=ready, event_time_s=event_t.astype(np.float32),
                        teacher_delta_mps2=teacher, target_clip_mps2=target)
    teacher_manifest = {
        "schema": "COSINE_GRU_TRAIN_C5_24_FEASIBILITY_TEACHER_MANIFEST_V1",
        "scope": "Each TRAIN scene optimized independently using its full future only to create an offline label; future trajectory is not a model input or deployment signal.",
        "dataset_sha256": sha256(DATA_PATH), "dataset_manifest_sha256": sha256(DATA_MANIFEST_PATH),
        "dataset_source_lock_sha256": sha256(SOURCE_LOCK_PATH),
        "teacher_delta_npz_sha256": sha256(TEACHER_NPZ), "teacher_script_sha256": sha256(Path(__file__)),
        "protocol": {"per_event_delta_bounds_mps2": [-fit.DELTA_LIMIT, fit.DELTA_LIMIT],
                     "warmup_first_31_events_fixed_zero": True,
                     "beta": "clip(event_time_s/1.8,0,1)", "total_action_clip_mps2": [-fit.ACTION_LIMIT, fit.ACTION_LIMIT],
                     "position_constraint": "ready-event prediction residual RMSE <= the same scene's C5 baseline residual RMSE",
                     "task_objective": "frozen-state SO3 geodesic RMSE over 20,000 1-ms filter outputs; exact locked filter and reference-derived task target",
                     "optimizer": f"projected gradient, {TEACHER_STEPS} steps maximum, step {TEACHER_STEP}, up to {MAX_BACKTRACK+1} feasibility backtracking attempts"},
        "runtime": {"all_24_teacher_seconds_excluding_locked_input_load": teacher_elapsed,
                    "all_24_elapsed_seconds_including_input_load": time.perf_counter() - t_all,
                    "median_per_scene_seconds": float(np.median([v["elapsed_seconds"] for v in teacher_meta.values()])),
                    "max_per_scene_seconds": float(max(v["elapsed_seconds"] for v in teacher_meta.values()))},
        "scenes": teacher_meta,
    }
    write_json(TEACHER_META, teacher_manifest)
    print(json.dumps({"teacher_done": True, "teacher_seconds": teacher_elapsed,
                      "all_elapsed_seconds": time.perf_counter() - t_all,
                      "teacher_sha256": sha256(TEACHER_NPZ)}, flush=True))

    # Causal student OOF: train only on each fold's TRAIN-scene teacher labels.
    x = data["x14_model_input"].astype(np.float32)
    tb = np.clip(event_t / fit.BETA_RISE_S, 0.0, 1.0)[..., None].astype(np.float32)
    t_teacher_t = torch.as_tensor(teacher, device=device, dtype=torch.float32)
    tm = torch.as_tensor(ready, device=device, dtype=torch.bool)
    student_raw = np.full_like(teacher, np.nan, dtype=np.float32)
    student_delta = np.full_like(teacher, np.nan, dtype=np.float32)
    student_action = np.full_like(teacher, np.nan, dtype=np.float32)
    fold_results = {}
    for fold_i, spec in enumerate(manifest["scene_folds"]):
        fold_id = spec["fold_id"]
        tr = [ids.index(s) for s in spec["train_scene_ids"]]
        ho = [ids.index(s) for s in spec["holdout_scene_ids"]]
        if len(set(tr) & set(ho)) or set(tr) | set(ho) != set(range(24)):
            raise RuntimeError(f"{fold_id}: invalid scene fold partition")
        mu = x[tr].reshape(-1, 14).mean(axis=0)
        sd = x[tr].reshape(-1, 14).std(axis=0)
        sd[sd < 1e-6] = 1.0
        xn = ((x - mu[None, None, :]) / sd[None, None, :]).astype(np.float32)
        tx = torch.as_tensor(xn, device=device)
        tri = torch.as_tensor(tr, device=device, dtype=torch.long)
        seed = SEED + fold_i
        random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
        if torch.cuda.is_available(): torch.cuda.manual_seed_all(seed)
        model = fit.ResidualGRU().to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=LR)
        losses = []
        for step in range(STEPS):
            optimizer.zero_grad(set_to_none=True)
            _, delta = model(tx[tri])
            loss = F.smooth_l1_loss(delta[tm[tri]], t_teacher_t[tri][tm[tri]], reduction="mean")
            if not torch.isfinite(loss):
                raise RuntimeError(f"{fold_id}: nonfinite teacher-distillation loss")
            loss.backward(); optimizer.step()
            if step == 0 or (step + 1) % 50 == 0:
                losses.append({"step": step + 1, "train_teacher_delta_smooth_l1": float(loss.detach().cpu())})
            if (step + 1) % 100 == 0:
                print(f"{fold_id}: student step {step+1}/{STEPS}, teacher_delta_loss={loss.item():.6g}", flush=True)
        model.eval()
        with torch.no_grad():
            raw_all, delta_all = model(torch.as_tensor(xn, device=device))
            delta_all = torch.where(tm[:, :, None], delta_all, torch.zeros_like(delta_all))
            base_t = torch.as_tensor(base_event, device=device)
            beta_t = torch.as_tensor(tb, device=device)
            action_all = torch.clamp(base_t + beta_t * delta_all, -fit.ACTION_LIMIT, fit.ACTION_LIMIT)
        raw_np, delta_np, action_np = (v.detach().cpu().numpy() for v in (raw_all, delta_all, action_all))
        student_raw[ho] = raw_np[ho]; student_delta[ho] = delta_np[ho]; student_action[ho] = action_np[ho]
        ckpt = CKPT_DIR / f"{fold_id}_teacher_distill.pt"
        torch.save({"state_dict": model.cpu().state_dict(), "normalizer_mean": mu, "normalizer_std": sd,
                    "fold_id": fold_id, "train_scene_ids": spec["train_scene_ids"],
                    "holdout_scene_ids": spec["holdout_scene_ids"], "seed": seed,
                    "steps": STEPS, "learning_rate": LR, "dataset_sha256": sha256(DATA_PATH),
                    "teacher_npz_sha256": sha256(TEACHER_NPZ), "teacher_fold_train_only": True}, ckpt)
        fold_results[fold_id] = {"train_scene_ids": spec["train_scene_ids"], "holdout_scene_ids": spec["holdout_scene_ids"],
                                 "train_count": len(tr), "holdout_count": len(ho), "seed": seed,
                                 "normalizer_fit_scope": "TRAIN fold scenes only; all causal X14 event rows",
                                 "loss_log": losses, "checkpoint_sha256": sha256(ckpt)}
        print(f"{fold_id}: student OOF fold complete ({len(ho)} held-out scenes)", flush=True)

    if not np.isfinite(student_delta).all() or not np.isfinite(student_action).all():
        raise RuntimeError("Student OOF missing or nonfinite")
    baseline_action = np.clip(base_event, -fit.ACTION_LIMIT, fit.ACTION_LIMIT)
    beta = tb
    teacher_action = np.clip(base_event + beta * teacher, -fit.ACTION_LIMIT, fit.ACTION_LIMIT).astype(np.float32)
    no_action, task_action = no_action.astype(np.float32), task_action.astype(np.float32)
    methods = {"C5_baseline": baseline_action, "ordinary_head_lambda_0_01": no_action,
               "task_head_lambda_0_1": task_action, "offline_teacher_sample": teacher_action,
               "causal_student_OOF": student_action}
    scores = {k: metric_bundle(v, target, ready, ids, bundle["trajectories"]) for k, v in methods.items()}
    d_err = student_delta[ready] - teacher[ready]
    tvals, svals = teacher[ready].reshape(-1), student_delta[ready].reshape(-1)
    corr = float(np.corrcoef(tvals, svals)[0, 1]) if np.std(tvals) > 0 and np.std(svals) > 0 else None
    distill = {"oof_teacher_delta_mae_mps2": float(np.mean(np.abs(d_err))),
               "oof_teacher_delta_rmse_mps2": float(np.sqrt(np.mean(d_err ** 2))),
               "oof_teacher_delta_pearson_r_all_ready_axes": corr,
               "teacher_delta_ready_abs_ge_0_5_fraction": float(np.mean(np.abs(teacher[ready]) >= fit.DELTA_LIMIT)),
               "student_raw_ready_abs_ge_0_5_fraction": float(np.mean(np.abs(student_raw[ready]) >= fit.DELTA_LIMIT)),
               "student_clipped_ready_abs_ge_0_5_fraction": float(np.mean(np.abs(student_delta[ready]) >= fit.DELTA_LIMIT)),
               "student_total_action_ready_abs_ge_3_fraction": float(np.mean(np.abs(student_action[ready]) >= fit.ACTION_LIMIT)),
               "per_scene_teacher_delta_rmse_mps2": {sid: float(np.sqrt(np.mean((student_delta[i, ready[i]] - teacher[i, ready[i]]) ** 2)))
                                                       for i, sid in enumerate(ids)}}

    np.savez_compressed(OOF_NPZ, scene_ids=np.asarray(ids), fold_id=data["fold_id"].astype(str), ready_mask=ready,
                        event_time_s=event_t.astype(np.float32), target_clip_mps2=target,
                        teacher_delta_mps2=teacher, teacher_action_mps2=teacher_action,
                        student_raw_delta_oof_mps2=student_raw, student_delta_oof_mps2=student_delta,
                        student_action_oof_mps2=student_action, ordinary_head_oof_action_mps2=no_action,
                        task_head_oof_action_mps2=task_action)
    results = {"schema": "COSINE_GRU_TRAIN_C5_24_TEACHER_DISTILLATION_OOF_RESULTS_V1",
               "scope": "Development only on parent-seen TRAIN_C5_24; no VAL/TEST, Plant, wind fields, or inertia reconstruction/use.",
               "teacher_manifest_sha256": sha256(TEACHER_META), "teacher_npz_sha256": sha256(TEACHER_NPZ),
               "OOF": {"scene_folds": fold_results, "student_teacher_fit": distill,
                       "method_metrics": scores,
                       "position_metric_definition": "RMSE of predicted applied acceleration residual against clipped 10-ms label on ready events; not physical position Q.",
                       "task_metric_definition": "Frozen-state reference-task SO3 RMSE over the locked 1-ms command-filter replay; not closed-loop.",
                       "paired_scene_counts_student_vs_teacher": {
                           "position_residual_rmse": [int(sum(scores["causal_student_OOF"]["per_scene_position_residual_rmse_mps2"][s] < scores["offline_teacher_sample"]["per_scene_position_residual_rmse_mps2"][s] - 1e-12 for s in ids)),
                                                       int(sum(abs(scores["causal_student_OOF"]["per_scene_position_residual_rmse_mps2"][s] - scores["offline_teacher_sample"]["per_scene_position_residual_rmse_mps2"][s]) <= 1e-12 for s in ids)),
                                                       int(sum(scores["causal_student_OOF"]["per_scene_position_residual_rmse_mps2"][s] > scores["offline_teacher_sample"]["per_scene_position_residual_rmse_mps2"][s] + 1e-12 for s in ids))],
                           "task_frozen_SO3": [int(sum(scores["causal_student_OOF"]["per_scene_task_frozen_SO3_rmse_rad"][s] < scores["offline_teacher_sample"]["per_scene_task_frozen_SO3_rmse_rad"][s] - 1e-12 for s in ids)),
                                                int(sum(abs(scores["causal_student_OOF"]["per_scene_task_frozen_SO3_rmse_rad"][s] - scores["offline_teacher_sample"]["per_scene_task_frozen_SO3_rmse_rad"][s]) <= 1e-12 for s in ids)),
                                                int(sum(scores["causal_student_OOF"]["per_scene_task_frozen_SO3_rmse_rad"][s] > scores["offline_teacher_sample"]["per_scene_task_frozen_SO3_rmse_rad"][s] + 1e-12 for s in ids))]},
                       "teacher_scope_warning": "Each teacher label uses the complete future of its own scene. Held-out teacher labels are used only for OOF fitting diagnostics, never for student training in that fold; no future feature is input to the student."},
               "runtime_seconds_total": time.perf_counter() - t_all,
               "oof_path": str(OOF_NPZ.relative_to(fit.ROOT)).replace("\\", "/"),
               "oof_sha256": sha256(OOF_NPZ)}
    write_json(RESULTS_JSON, results)
    lock = {"schema": "COSINE_GRU_TRAIN_C5_24_TEACHER_DISTILLATION_SOURCE_LOCK_V1",
            "dataset_sha256": sha256(DATA_PATH), "dataset_manifest_sha256": sha256(DATA_MANIFEST_PATH),
            "dataset_source_lock_sha256": sha256(SOURCE_LOCK_PATH),
            "teacher_npz_sha256": sha256(TEACHER_NPZ), "teacher_manifest_sha256": sha256(TEACHER_META),
            "script_sha256": sha256(Path(__file__)), "no_task_oof_sha256": sha256(NO_TASK_OOF),
            "task_head_oof_sha256": sha256(TASK_OOF), "fold_ids": list(fold_results),
            "checkpoint_sha256_by_fold": {k: v["checkpoint_sha256"] for k, v in fold_results.items()},
            "oof_sha256": sha256(OOF_NPZ), "results_sha256": sha256(RESULTS_JSON)}
    write_json(SOURCE_LOCK, lock)
    print(json.dumps({"all_done": True, "teacher_seconds": teacher_elapsed,
                      "runtime_total_seconds": results["runtime_seconds_total"],
                      "distillation": distill,
                      "position_macro": {k: v["position_residual_rmse_scene_macro_mps2"] for k, v in scores.items()},
                      "task_macro_mrad": {k: 1000 * v["task_frozen_SO3_rmse_scene_macro_rad"] for k, v in scores.items()},
                      "paired_student_vs_teacher": results["OOF"]["paired_scene_counts_student_vs_teacher"],
                      "oof_sha256": sha256(OOF_NPZ)}, indent=2), flush=True)


if __name__ == "__main__":
    main()
