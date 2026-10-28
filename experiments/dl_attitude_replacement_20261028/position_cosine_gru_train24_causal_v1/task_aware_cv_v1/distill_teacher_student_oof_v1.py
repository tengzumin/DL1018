#!/usr/bin/env python3
"""Resume the causal student OOF stage from the already hash-locked TRAIN24 teacher labels."""
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
                               load_locked_inputs, sha256)


OUT = Path(__file__).resolve().parent
TEACHER_NPZ = OUT / "TRAIN24_FEASIBILITY_TEACHER_DELTAS_v1.npz"
TEACHER_META = OUT / "TRAIN24_FEASIBILITY_TEACHER_MANIFEST_v1.json"
TEACHER_SCRIPT = OUT / "fit_teacher_distillation_oof_v1.py"
NO_TASK_OOF = OUT.parent / "gru_residual_cv_v1/CV_OOF_PREDICTIONS_v1.npz"
TASK_OOF = OUT / "TASK_AWARE_CV_OOF_v1.npz"
NO_TASK_SHA = "9dc29cc2d94b990bafc2bdf77cc8c704fb14e2c0582987e3057cd6464e177d0f"
TASK_SHA = "a92c61662fa2fee8faf11d97b1f0234db13f6875c1cc6036098d71f3dccf5dcd"
OOF_NPZ = OUT / "TRAIN24_TEACHER_DISTILLATION_OOF_v1.npz"
RESULTS_JSON = OUT / "TRAIN24_TEACHER_DISTILLATION_RESULTS_v1.json"
SOURCE_LOCK = OUT / "TRAIN24_TEACHER_DISTILLATION_SOURCE_LOCK_v1.json"
CKPT_DIR = OUT / "teacher_distill_checkpoints"
SEED, STEPS, LR = 20261028, 300, 1e-3


def write_json(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def pos_rmse(action: np.ndarray, target: np.ndarray, ready: np.ndarray) -> float:
    e = action[ready].astype(np.float64) - target[ready].astype(np.float64)
    return float(np.sqrt(np.mean(e * e)))


def metrics(actions: np.ndarray, target: np.ndarray, ready: np.ndarray,
            ids: list[str], trajectories: list[dict]) -> dict:
    pp, tt = {}, {}
    errs = []
    for i, sid in enumerate(ids):
        pp[sid] = pos_rmse(actions[i], target[i], ready[i])
        tt[sid] = fit.evaluate_task_action(i, actions[i], trajectories[i])
        errs.append(actions[i, ready[i]].astype(np.float64) - target[i, ready[i]].astype(np.float64))
    pooled = np.concatenate(errs, axis=0)
    return {"position_residual_rmse_scene_macro_mps2": float(np.mean(list(pp.values()))),
            "position_residual_rmse_pooled_mps2": float(np.sqrt(np.mean(pooled ** 2))),
            "task_frozen_SO3_rmse_scene_macro_rad": float(np.mean(list(tt.values()))),
            "task_frozen_SO3_rmse_pooled_rad": float(np.sqrt(np.mean(np.square(list(tt.values()))))),
            "per_scene_position_residual_rmse_mps2": pp,
            "per_scene_task_frozen_SO3_rmse_rad": tt}


def win_counts(a: dict[str, float], b: dict[str, float], ids: list[str], lower_is_better=True) -> list[int]:
    dif = [a[s] - b[s] for s in ids]
    return [sum(d < -1e-12 for d in dif), sum(abs(d) <= 1e-12 for d in dif), sum(d > 1e-12 for d in dif)]


def main() -> None:
    for p in (OOF_NPZ, RESULTS_JSON, SOURCE_LOCK):
        if p.exists():
            raise RuntimeError(f"Refusing to overwrite {p}")
    if not CKPT_DIR.is_dir() or any(CKPT_DIR.iterdir()):
        raise RuntimeError("Expected the empty checkpoint directory created before teacher generation")
    torch.set_num_threads(1)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    torch.use_deterministic_algorithms(True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    start = time.perf_counter()

    # Recovery binding: consume the already-complete teacher artifact; never rerun or overwrite it.
    teacher_meta = json.loads(TEACHER_META.read_text(encoding="utf-8"))
    if (teacher_meta.get("schema") != "COSINE_GRU_TRAIN_C5_24_FEASIBILITY_TEACHER_MANIFEST_V1" or
            teacher_meta.get("teacher_delta_npz_sha256") != sha256(TEACHER_NPZ) or
            teacher_meta.get("teacher_script_sha256") != sha256(TEACHER_SCRIPT) or
            teacher_meta.get("dataset_sha256") != sha256(DATA_PATH) or
            teacher_meta.get("dataset_manifest_sha256") != sha256(DATA_MANIFEST_PATH) or
            teacher_meta.get("dataset_source_lock_sha256") != sha256(SOURCE_LOCK_PATH)):
        raise RuntimeError("Saved teacher, generator-script, or TRAIN dataset binding mismatch")
    bundle = load_locked_inputs()
    data, manifest = bundle["arrays"], bundle["manifest"]
    ids = data["scene_ids"].astype(str).tolist()
    target = data["target_interval_clip_mps2"].astype(np.float32)
    ready = data["ready_mask"].astype(bool)
    base = data["applied_acceleration_event_mps2"].astype(np.float32)
    event_t = data["event_time_s"].astype(np.float64)
    x = data["x14_model_input"].astype(np.float32)
    with np.load(TEACHER_NPZ, allow_pickle=False) as z:
        teacher_ids = z["scene_ids"].astype(str).tolist()
        teacher_fold = z["fold_id"].astype(str).tolist()
        teacher_ready = z["ready_mask"].astype(bool)
        teacher_target = z["target_clip_mps2"].astype(np.float32)
        teacher = z["teacher_delta_mps2"].astype(np.float32)
    if (teacher_ids != ids or teacher_fold != data["fold_id"].astype(str).tolist() or
            not np.array_equal(teacher_ready, ready) or not np.array_equal(teacher_target, target) or
            teacher.shape != (24, 1999, 3) or not np.isfinite(teacher).all()):
        raise RuntimeError("Saved teacher labels do not align with locked TRAIN24 scenes/targets")
    if len(teacher_meta.get("scenes", {})) != 24 or list(teacher_meta["scenes"]) != ids:
        raise RuntimeError("Teacher manifest scene inventory/order mismatch")
    if sha256(NO_TASK_OOF) != NO_TASK_SHA or sha256(TASK_OOF) != TASK_SHA:
        raise RuntimeError("Existing comparison OOF artifact hash mismatch")
    with np.load(NO_TASK_OOF, allow_pickle=False) as z:
        no_ids = z["scene_ids"].astype(str).tolist(); no_action = z["prediction_lambda_0_01"].astype(np.float32)
        if no_ids != ids or not np.array_equal(z["ready_mask"], ready) or not np.array_equal(z["target_clip_mps2"], target):
            raise RuntimeError("Ordinary OOF scene/target binding mismatch")
    with np.load(TASK_OOF, allow_pickle=False) as z:
        task_ids = z["scene_ids"].astype(str).tolist(); task_action = z["task_action_lambda_task_0_1"].astype(np.float32)
        task_fold = z["fold_id"].astype(str).tolist()
        if task_ids != ids or not np.array_equal(z["ready_mask"], ready) or not np.array_equal(z["target_clip_mps2"], target):
            raise RuntimeError("Task OOF scene/target binding mismatch")
    expected_fold = {sid: f["fold_id"] for f in manifest["scene_folds"] for sid in f["holdout_scene_ids"]}
    if task_fold != [expected_fold[sid] for sid in ids]:
        raise RuntimeError("Task OOF manifest fold binding mismatch")

    beta = np.clip(event_t / fit.BETA_RISE_S, 0.0, 1.0)[..., None].astype(np.float32)
    teacher_action = np.clip(base + beta * teacher, -fit.ACTION_LIMIT, fit.ACTION_LIMIT).astype(np.float32)
    baseline_action = np.clip(base, -fit.ACTION_LIMIT, fit.ACTION_LIMIT).astype(np.float32)
    # Recompute every per-scene teacher residual cap and the exact task forward from source data.
    teacher_recheck = {}
    for i, sid in enumerate(ids):
        pos_c5 = pos_rmse(baseline_action[i], target[i], ready[i])
        pos_teacher = pos_rmse(teacher_action[i], target[i], ready[i])
        meta_scene = teacher_meta["scenes"][sid]
        if (np.abs(teacher[i, :31]).max() != 0.0 or np.abs(teacher[i]).max() > fit.DELTA_LIMIT + 1e-6 or
                pos_teacher > pos_c5 + 1.01e-8 or
                abs(pos_teacher - meta_scene["teacher_position_residual_rmse_mps2"]) > 2e-7):
            raise RuntimeError(f"{sid}: teacher residual cap/bounds/meta recheck failed")
        tau = fit.evaluate_task_action(i, teacher_action[i], bundle["trajectories"][i])
        if abs(tau - meta_scene["teacher_frozen_task_so3_rmse_rad_scipy"]) > 2e-7:
            raise RuntimeError(f"{sid}: teacher frozen SO3 replay mismatch")
        teacher_recheck[sid] = {"c5_position_residual_rmse_mps2": pos_c5,
                                "teacher_position_residual_rmse_mps2": pos_teacher,
                                "task_so3_rmse_rad_recomputed": tau,
                                "teacher_constraint_pass": pos_teacher <= pos_c5 + 1.01e-8}
    print(json.dumps({"saved_teacher_bindings_pass": True, "teacher_scenes_verified": len(ids),
                      "teacher_max_position_cap_excess_mps2": max(v["teacher_position_residual_rmse_mps2"] - v["c5_position_residual_rmse_mps2"] for v in teacher_recheck.values()),
                      "teacher_file_sha256": sha256(TEACHER_NPZ), "starting_student_folds": True}), flush=True)

    device_ids = torch.as_tensor(np.arange(24), device=device, dtype=torch.long)
    x_t = torch.as_tensor(x, device=device)
    teacher_t = torch.as_tensor(teacher, device=device)
    ready_t = torch.as_tensor(ready, device=device, dtype=torch.bool)
    student_raw = np.full_like(teacher, np.nan, dtype=np.float32)
    student_delta = np.full_like(teacher, np.nan, dtype=np.float32)
    student_action = np.full_like(teacher, np.nan, dtype=np.float32)
    fold_results = {}
    for fi, spec in enumerate(manifest["scene_folds"]):
        fold_id = spec["fold_id"]
        train_ids, holdout_ids = spec["train_scene_ids"], spec["holdout_scene_ids"]
        tr = [ids.index(s) for s in train_ids]; ho = [ids.index(s) for s in holdout_ids]
        if len(set(tr) & set(ho)) or set(tr) | set(ho) != set(range(24)):
            raise RuntimeError(f"{fold_id}: fold does not exactly partition TRAIN24")
        mu = x[tr].reshape(-1, 14).mean(axis=0)
        sd = x[tr].reshape(-1, 14).std(axis=0); sd[sd < 1e-6] = 1.0
        xn = ((x - mu[None, None, :]) / sd[None, None, :]).astype(np.float32)
        tx = torch.as_tensor(xn, device=device)
        tri = torch.as_tensor(tr, device=device, dtype=torch.long)
        seed = SEED + fi
        random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
        if torch.cuda.is_available(): torch.cuda.manual_seed_all(seed)
        model = fit.ResidualGRU().to(device)
        opt = torch.optim.Adam(model.parameters(), lr=LR)
        loss_log = []
        for step in range(STEPS):
            opt.zero_grad(set_to_none=True)
            _, d = model(tx[tri])
            # Only training-fold teacher labels participate in the loss.
            loss = F.smooth_l1_loss(d[ready_t[tri]], teacher_t[tri][ready_t[tri]], reduction="mean")
            if not torch.isfinite(loss): raise RuntimeError(f"{fold_id}: nonfinite student loss")
            loss.backward(); opt.step()
            if step == 0 or (step + 1) % 50 == 0:
                loss_log.append({"step": step + 1, "train_teacher_delta_smooth_l1": float(loss.detach().cpu())})
            if (step + 1) % 100 == 0:
                print(f"{fold_id} student {step+1}/{STEPS} loss={loss.item():.6g}", flush=True)
        model.eval()
        with torch.no_grad():
            raw_all, d_all = model(tx)
            d_all = torch.where(ready_t[:, :, None], d_all, torch.zeros_like(d_all))
            action_all = torch.clamp(torch.as_tensor(base, device=device) + torch.as_tensor(beta, device=device) * d_all,
                                     -fit.ACTION_LIMIT, fit.ACTION_LIMIT)
        raw_np, d_np, a_np = (v.detach().cpu().numpy() for v in (raw_all, d_all, action_all))
        student_raw[ho], student_delta[ho], student_action[ho] = raw_np[ho], d_np[ho], a_np[ho]
        ckpt = CKPT_DIR / f"{fold_id}_teacher_distill.pt"
        torch.save({"state_dict": model.cpu().state_dict(), "normalizer_mean": mu, "normalizer_std": sd,
                    "fold_id": fold_id, "train_scene_ids": train_ids, "holdout_scene_ids": holdout_ids,
                    "seed": seed, "steps": STEPS, "learning_rate": LR,
                    "dataset_sha256": sha256(DATA_PATH), "teacher_npz_sha256": sha256(TEACHER_NPZ),
                    "teacher_labels_used_for_loss": "training fold scenes only"}, ckpt)
        fold_results[fold_id] = {"train_scene_ids": train_ids, "holdout_scene_ids": holdout_ids,
                                 "train_count": len(tr), "holdout_count": len(ho), "seed": seed,
                                 "normalizer_fit_scope": "training fold scenes only, all causal X14 rows",
                                 "training_loss_log": loss_log, "checkpoint_sha256": sha256(ckpt)}
        print(f"{fold_id}: student OOF complete; holdout={len(ho)}", flush=True)

    if not np.isfinite(student_raw).all() or not np.isfinite(student_delta).all() or not np.isfinite(student_action).all():
        raise RuntimeError("Student OOF predictions missing or nonfinite")
    methods = {"C5_baseline": baseline_action, "ordinary_head_lambda_0_01": no_action,
               "task_head_lambda_0_1": task_action, "offline_teacher_sample": teacher_action,
               "causal_student_OOF": student_action}
    score = {k: metrics(v, target, ready, ids, bundle["trajectories"]) for k, v in methods.items()}
    de = student_delta[ready].astype(np.float64) - teacher[ready].astype(np.float64)
    tv = teacher[ready].reshape(-1).astype(np.float64); sv = student_delta[ready].reshape(-1).astype(np.float64)
    delta_fit = {"oof_delta_mae_mps2": float(np.mean(np.abs(de))),
                 "oof_delta_rmse_mps2": float(np.sqrt(np.mean(de ** 2))),
                 "oof_delta_pearson_r": float(np.corrcoef(tv, sv)[0, 1]) if np.std(tv) > 0 and np.std(sv) > 0 else None,
                 "oof_delta_rmse_per_scene_mps2": {sid: float(np.sqrt(np.mean((student_delta[i, ready[i]] - teacher[i, ready[i]]) ** 2))) for i, sid in enumerate(ids)},
                 "teacher_ready_abs_ge_0_5_fraction": float(np.mean(np.abs(teacher[ready]) >= fit.DELTA_LIMIT)),
                 "student_raw_ready_abs_ge_0_5_fraction": float(np.mean(np.abs(student_raw[ready]) >= fit.DELTA_LIMIT)),
                 "student_clipped_ready_abs_ge_0_5_fraction": float(np.mean(np.abs(student_delta[ready]) >= fit.DELTA_LIMIT)),
                 "student_total_action_ready_abs_ge_3_fraction": float(np.mean(np.abs(student_action[ready]) >= fit.ACTION_LIMIT))}
    fold_ids_by_scene = [expected_fold[s] for s in ids]
    np.savez_compressed(OOF_NPZ, scene_ids=np.asarray(ids), fold_id=np.asarray(fold_ids_by_scene),
                        ready_mask=ready, event_time_s=event_t.astype(np.float32), target_clip_mps2=target,
                        teacher_delta_mps2=teacher, teacher_action_mps2=teacher_action,
                        student_raw_delta_oof_mps2=student_raw, student_delta_oof_mps2=student_delta,
                        student_action_oof_mps2=student_action, ordinary_head_oof_action_mps2=no_action,
                        task_head_oof_action_mps2=task_action)
    results = {"schema": "COSINE_GRU_TRAIN_C5_24_TEACHER_DISTILLATION_OOF_RESULTS_V1",
               "scope": "TRAIN_C5_24 development only; parent model has seen these scenes; no VAL/TEST, Plant, wind field, or inertia reconstruction/use.",
               "recovery": {"initial_driver_failure": "Teacher loop completed and wrote the full NPZ and manifest, then the batch driver exited at its status print because flush=True was passed to json.dumps; student training had not started.",
                            "recovery_action": "Did not rerun or overwrite teachers; verified teacher NPZ SHA, 24-scene inventory/order, generation script SHA, dataset/manifest/source-lock SHA, warmup, bounds, per-scene residual cap, and SO3 replay; resumed student OOF from saved labels."},
               "teacher": {"npz_sha256": sha256(TEACHER_NPZ), "manifest_sha256": sha256(TEACHER_META),
                           "generation_script_sha256": teacher_meta["teacher_script_sha256"],
                           "runtime": teacher_meta["runtime"], "per_scene_recheck": teacher_recheck,
                           "scope_limit": "Full future scene used only for offline per-scene teacher label, never a student input."},
               "distillation": {"architecture": "GRU(14,32)->Linear(32,3), zero output head, hidden reset per scene",
                                "loss": "SmoothL1(clipped student delta, teacher delta) on ready events only",
                                "seed_base": SEED, "steps_per_fold": STEPS, "learning_rate": LR,
                                "normalizer": "fold training scenes only", "folds": fold_results,
                                "oof_teacher_delta_fit": delta_fit,
                                "method_metrics": score,
                                "student_vs_teacher_scene_counts": {
                                    "position_residual_rmse": win_counts(score["causal_student_OOF"]["per_scene_position_residual_rmse_mps2"], score["offline_teacher_sample"]["per_scene_position_residual_rmse_mps2"], ids),
                                    "task_frozen_SO3": win_counts(score["causal_student_OOF"]["per_scene_task_frozen_SO3_rmse_rad"], score["offline_teacher_sample"]["per_scene_task_frozen_SO3_rmse_rad"], ids)},
                                "metric_limit": "Position values are predicted-acceleration residual RMSE, not physical position Q. SO3 uses frozen raw state/yaw/reference and fixed command filter; not closed-loop."},
               "runtime_student_seconds": time.perf_counter() - start,
               "oof_path": str(OOF_NPZ.relative_to(fit.ROOT)).replace("\\", "/"),
               "oof_sha256": sha256(OOF_NPZ)}
    write_json(RESULTS_JSON, results)
    lock = {"schema": "COSINE_GRU_TRAIN_C5_24_TEACHER_DISTILLATION_SOURCE_LOCK_V1",
            "dataset_sha256": sha256(DATA_PATH), "dataset_manifest_sha256": sha256(DATA_MANIFEST_PATH),
            "dataset_source_lock_sha256": sha256(SOURCE_LOCK_PATH),
            "teacher_npz_sha256": sha256(TEACHER_NPZ), "teacher_manifest_sha256": sha256(TEACHER_META),
            "teacher_generation_script_sha256": sha256(TEACHER_SCRIPT),
            "no_task_oof_sha256": sha256(NO_TASK_OOF), "task_head_oof_sha256": sha256(TASK_OOF),
            "distillation_script_sha256": sha256(Path(__file__)),
            "fold_ids": list(fold_results), "checkpoint_sha256_by_fold": {k: v["checkpoint_sha256"] for k, v in fold_results.items()},
            "oof_sha256": sha256(OOF_NPZ), "results_sha256": sha256(RESULTS_JSON)}
    write_json(SOURCE_LOCK, lock)
    print(json.dumps({"done": True, "teacher_seconds": teacher_meta["runtime"]["all_24_teacher_seconds_excluding_locked_input_load"],
                      "student_runtime_seconds": results["runtime_student_seconds"],
                      "delta_fit": delta_fit,
                      "position_macro_residual_rmse_mps2": {k: v["position_residual_rmse_scene_macro_mps2"] for k, v in score.items()},
                      "task_macro_frozen_mrad": {k: 1000 * v["task_frozen_SO3_rmse_scene_macro_rad"] for k, v in score.items()},
                      "student_vs_teacher_wins": results["distillation"]["student_vs_teacher_scene_counts"],
                      "oof_sha256": sha256(OOF_NPZ)}, indent=2), flush=True)


if __name__ == "__main__":
    main()
