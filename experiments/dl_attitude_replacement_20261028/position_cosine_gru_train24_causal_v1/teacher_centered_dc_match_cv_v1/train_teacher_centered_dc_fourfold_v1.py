#!/usr/bin/env python3
"""One fixed scene-group OOF GRU with teacher-centered scene-mean action supervision."""
from __future__ import annotations

import hashlib
import json
import os
import random
import sys
import time
from pathlib import Path

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

import numpy as np
import torch

OUT = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = ROOT / "experiments/dl_attitude_replacement_20261028/position_cosine_gru_train24_causal_v1"
SOURCE = DATA_DIR / "task_aware_cv_v1"
NO_DC_DIR = DATA_DIR / "teacher_position_balanced_cv_v1"
ZERO_DC_DIR = DATA_DIR / "teacher_position_balanced_dc_penalty_cv_v1"
ANALYSIS_DIR = DATA_DIR / "teacher_teacher_dc_frequency_train24_analysis_v1"
sys.path.insert(0, str(SOURCE))
import fit_task_aware_fourfold_v1 as fit  # noqa: E402
from task_aware_common import (DATA_MANIFEST_PATH, DATA_PATH, SOURCE_LOCK_PATH,
                               load_locked_inputs, sha256)  # noqa: E402

TEACHER_NPZ = SOURCE / "TRAIN24_TEACHER_DISTILLATION_OOF_v1.npz"
TEACHER_LABEL_NPZ = SOURCE / "TRAIN24_FEASIBILITY_TEACHER_DELTAS_v1.npz"
TEACHER_META = SOURCE / "TRAIN24_FEASIBILITY_TEACHER_MANIFEST_v1.json"
TEACHER_DISTILL_LOCK = SOURCE / "TRAIN24_TEACHER_DISTILLATION_SOURCE_LOCK_v1.json"
TEACHER_DISTILL_RESULT = SOURCE / "TRAIN24_TEACHER_DISTILLATION_RESULTS_v1.json"
NO_DC_NPZ = NO_DC_DIR / "TEACHER_POSITION_BALANCED_OOF_v1.npz"
NO_DC_RESULT = NO_DC_DIR / "TEACHER_POSITION_BALANCED_RESULTS_v1.json"
ZERO_DC_NPZ = ZERO_DC_DIR / "DC_PENALTY_OOF_v1.npz"
ZERO_DC_RESULT = ZERO_DC_DIR / "DC_PENALTY_RESULTS_v1.json"
DESIGN_NOTE = ANALYSIS_DIR / "TRAIN_ONLY_DESIGN_DECISION_v1.md"
ANALYSIS_RESULT = ANALYSIS_DIR / "TEACHER_DC_FREQUENCY_TIME_RESULTS_v1.json"
DC_ABLATION = ANALYSIS_DIR / "SCENE_DC_ABLATION_v1.json"

PLAN = OUT / "PREDECLARED_CONFIG_v1.json"
OOF_PATH = OUT / "TEACHER_CENTERED_DC_OOF_v1.npz"
RESULT_PATH = OUT / "TEACHER_CENTERED_DC_RESULTS_v1.json"
LOCK_PATH = OUT / "TEACHER_CENTERED_DC_SOURCE_LOCK_v1.json"
CKPT_DIR = OUT / "checkpoints"

SEED, STEPS, LR = 20261028, 300, 1e-3
TEACHER_WEIGHT, POSITION_WEIGHT, CENTERED_DC_WEIGHT = 0.5, 0.5, 0.5
DC_SCALE_RATIO = 0.1


def write_json(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def position_rmse(action: np.ndarray, target: np.ndarray, ready: np.ndarray) -> float:
    e = action[ready].astype(np.float64) - target[ready].astype(np.float64)
    return float(np.sqrt(np.mean(e * e)))


def action_lowfreq(action: np.ndarray, base: np.ndarray, ready: np.ndarray,
                   event_time: np.ndarray) -> dict:
    delta = (action - base).astype(np.float64)
    delta[~ready] = 0.0
    d = delta[ready]
    bins = np.floor(event_time).astype(int)
    means = np.array([delta[bins == b].mean(axis=0) for b in range(20)])
    return {
        "mean_action_delta_xyz_mps2": d.mean(axis=0).tolist(),
        "scene_dc_bias_norm_mps2": float(np.linalg.norm(d.mean(axis=0))),
        "mean_1s_bias_norm_mps2": float(np.mean(np.linalg.norm(means, axis=1))),
        "max_1s_bias_norm_mps2": float(np.max(np.linalg.norm(means, axis=1))),
        "action_delta_rms_mps2": float(np.sqrt(np.mean(d ** 2))),
    }


def main() -> None:
    for p in (PLAN, OOF_PATH, RESULT_PATH, LOCK_PATH):
        if p.exists(): raise RuntimeError(f"Refusing to overwrite {p}")
    if any(CKPT_DIR.iterdir()): raise RuntimeError("Refusing to overwrite checkpoints")
    bundle = load_locked_inputs()
    data, manifest = bundle["arrays"], bundle["manifest"]
    ids = data["scene_ids"].astype(str).tolist()
    x = data["x14_model_input"].astype(np.float32)
    ready = data["ready_mask"].astype(bool)
    target = data["target_interval_clip_mps2"].astype(np.float32)
    base = np.clip(data["applied_acceleration_event_mps2"].astype(np.float32), -3, 3)
    event_time = data["event_time_s"].astype(np.float64)
    beta = np.clip(event_time / fit.BETA_RISE_S, 0, 1)[..., None].astype(np.float32)
    folds = manifest["scene_folds"]
    if [f["holdout_scene_count"] for f in folds] != [6, 8, 4, 6]:
        raise RuntimeError("Fixed scene-group split changed")

    inputs = {
        "dataset_sha256": sha256(DATA_PATH), "dataset_manifest_sha256": sha256(DATA_MANIFEST_PATH),
        "dataset_source_lock_sha256": sha256(SOURCE_LOCK_PATH),
        "teacher_oof_sha256": file_sha(TEACHER_NPZ), "teacher_manifest_sha256": file_sha(TEACHER_META),
        "teacher_delta_labels_sha256": file_sha(TEACHER_LABEL_NPZ),
        "teacher_distillation_source_lock_sha256": file_sha(TEACHER_DISTILL_LOCK),
        "teacher_distillation_results_sha256": file_sha(TEACHER_DISTILL_RESULT),
        "no_dc_oof_sha256": file_sha(NO_DC_NPZ), "no_dc_results_sha256": file_sha(NO_DC_RESULT),
        "zero_dc_oof_sha256": file_sha(ZERO_DC_NPZ), "zero_dc_results_sha256": file_sha(ZERO_DC_RESULT),
        "frequency_analysis_sha256": file_sha(ANALYSIS_RESULT), "dc_ablation_sha256": file_sha(DC_ABLATION),
        "design_note_sha256": file_sha(DESIGN_NOTE),
    }
    teacher_meta = json.loads(TEACHER_META.read_text(encoding="utf-8"))
    teacher_distill_lock = json.loads(TEACHER_DISTILL_LOCK.read_text(encoding="utf-8"))
    with np.load(TEACHER_NPZ, allow_pickle=False) as z:
        teacher_ids = z["scene_ids"].astype(str).tolist()
        teacher_folds = z["fold_id"].astype(str).tolist()
        teacher_ready = z["ready_mask"].astype(bool)
        teacher_target = z["target_clip_mps2"].astype(np.float32)
        teacher_delta = z["teacher_delta_mps2"].astype(np.float32)
        teacher_action = z["teacher_action_mps2"].astype(np.float32)
    fold_by_id = {sid: f["fold_id"] for f in folds for sid in f["holdout_scene_ids"]}
    fold_for_row = [fold_by_id[sid] for sid in ids]
    if (teacher_ids != ids or teacher_folds != fold_for_row or teacher_action.shape != base.shape or
            not np.array_equal(teacher_ready, ready) or not np.array_equal(teacher_target, target) or
            not np.isfinite(teacher_action).all() or not np.isfinite(teacher_delta).all() or
            teacher_meta.get("teacher_delta_npz_sha256") != inputs["teacher_delta_labels_sha256"] or
            teacher_meta.get("dataset_sha256") != inputs["dataset_sha256"]):
        raise RuntimeError("Teacher labels/actions do not align with locked TRAIN24 scenes")
    if (teacher_distill_lock.get("teacher_npz_sha256") != inputs["teacher_delta_labels_sha256"] or
            teacher_distill_lock.get("oof_sha256") != inputs["teacher_oof_sha256"] or
            teacher_distill_lock.get("results_sha256") != inputs["teacher_distillation_results_sha256"]):
        raise RuntimeError("Teacher-distillation source lock does not bind the declared labels and OOF output")
    old_results = json.loads(NO_DC_RESULT.read_text(encoding="utf-8"))
    zero_results = json.loads(ZERO_DC_RESULT.read_text(encoding="utf-8"))
    if (old_results.get("oof_sha256") != inputs["no_dc_oof_sha256"] or
            zero_results.get("oof_sha256") != inputs["zero_dc_oof_sha256"]):
        raise RuntimeError("Prior OOF result hashes are stale")
    with np.load(NO_DC_NPZ, allow_pickle=False) as z:
        no_dc_action = z["student_action_mps2"].astype(np.float32)
        if z["scene_ids"].astype(str).tolist() != ids or not np.array_equal(z["ready_mask"], ready):
            raise RuntimeError("No-DC OOF alignment failure")
    with np.load(ZERO_DC_NPZ, allow_pickle=False) as z:
        zero_dc_action = z["student_action_mps2"].astype(np.float32)
        if z["scene_ids"].astype(str).tolist() != ids or not np.array_equal(z["ready_mask"], ready):
            raise RuntimeError("Zero-DC OOF alignment failure")

    plan = {
        "schema": "COSINE_GRU_TRAIN24_TEACHER_CENTERED_DC_PREDECLARED_V1",
        "scope": "Locked TRAIN_C5_24 only; causal X14; strict four-fold scene OOF. No VAL/TEST read, Plant, or inertia reconstruction.",
        "design_evidence": "Frozen-task TRAIN24 ablations show teacher scene-mean correction helps SO3; the zero-mean penalty suppresses it. See source-bound TRAIN_ONLY_DESIGN_DECISION_v1.md. This does not guarantee closed-loop Q.",
        "input_hashes": inputs,
        "model": "Same ResidualGRU(14,32)->Linear(32,3); same C5 action, ramp, clipping, and readiness.",
        "fixed_training": {
            "seed_base": SEED, "steps_per_fold": STEPS, "optimizer": "Adam", "learning_rate": LR,
            "normalizer": "Fold-only X14 mean/std from training scenes across all causal rows.",
            "base_loss": "0.5*teacher-delta normalized MSE + 0.5*position-action normalized MSE; ready rows only.",
            "teacher_centered_dc_loss": "0.5*mean_scene,axis(((mean_ready(student_action-C5_action)-mean_ready(teacher_action-C5_action))/(0.1*teacher_train_RMS))^2).",
            "scales": "Teacher RMS, position residual RMS, X14 normalizer, and DC scale are computed from the training fold only; DC scale is 0.1*teacher RMS.",
            "teacher_role": "Teacher labels, including their scene mean, are training supervision on training-fold scenes only; teacher is excluded from inference.",
            "action": "clip(C5_action + clip(event_time_s/1.8,0,1)*clip(delta,-0.5,0.5), -3,3); residual zero while not ready.",
            "weights": {"teacher": TEACHER_WEIGHT, "position": POSITION_WEIGHT, "teacher_centered_dc": CENTERED_DC_WEIGHT},
        },
        "folds": [{"fold_id": f["fold_id"], "train_scene_ids": f["train_scene_ids"],
                   "holdout_scene_ids": f["holdout_scene_ids"],
                   "train_count": f["train_scene_count"], "holdout_count": f["holdout_scene_count"]}
                  for f in folds],
        "created_before_optimization": True,
        "selection_rule": "Exactly one OOF run. Report position, frozen SO3, and teacher-mean tracking regardless of outcome; do not tune on held-out folds.",
    }
    write_json(PLAN, plan)

    torch.set_num_threads(1)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    torch.use_deterministic_algorithms(True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    xt = torch.as_tensor(x, device=device)
    mt = torch.as_tensor(ready, device=device, dtype=torch.bool)
    tt = torch.as_tensor(teacher_delta, device=device)
    teacher_action_t = torch.as_tensor(teacher_action, device=device)
    bt = torch.as_tensor(base, device=device)
    betat = torch.as_tensor(beta, device=device)
    yt = torch.as_tensor(target, device=device)
    action_oof = np.full_like(base, np.nan, dtype=np.float32)
    raw_oof = np.full_like(base, np.nan, dtype=np.float32)
    delta_oof = np.full_like(base, np.nan, dtype=np.float32)
    folds_result = {}
    start = time.perf_counter()
    for fi, spec in enumerate(folds):
        fold_id = spec["fold_id"]
        tr = [ids.index(s) for s in spec["train_scene_ids"]]
        ho = [ids.index(s) for s in spec["holdout_scene_ids"]]
        if (len(tr) != spec["train_scene_count"] or len(ho) != spec["holdout_scene_count"] or
                set(tr) & set(ho) or set(tr) | set(ho) != set(range(24))):
            raise RuntimeError(f"{fold_id}: invalid exact scene partition")
        mu = x[tr].reshape(-1, 14).mean(axis=0)
        sd = x[tr].reshape(-1, 14).std(axis=0); sd[sd < 1e-6] = 1.0
        xn = ((x - mu[None, None, :]) / sd[None, None, :]).astype(np.float32)
        tx = torch.as_tensor(xn, device=device)
        tri = torch.as_tensor(tr, device=device, dtype=torch.long)
        mask = mt[tri]
        teacher_scale = float(np.sqrt(np.mean(teacher_delta[tr][ready[tr]].astype(np.float64) ** 2)))
        pos_e = base[tr][ready[tr]].astype(np.float64) - target[tr][ready[tr]].astype(np.float64)
        position_scale = float(np.sqrt(np.mean(pos_e ** 2)))
        dc_scale = DC_SCALE_RATIO * teacher_scale
        if min(teacher_scale, position_scale, dc_scale) <= 1e-8:
            raise RuntimeError(f"{fold_id}: invalid training-only scales")
        seed = SEED + fi
        random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
        if torch.cuda.is_available(): torch.cuda.manual_seed_all(seed)
        model = fit.ResidualGRU().to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=LR)
        logs = []
        for step in range(STEPS):
            optimizer.zero_grad(set_to_none=True)
            _, d = model(tx[tri])
            d = torch.where(mask[:, :, None], d, torch.zeros_like(d))
            action = torch.clamp(bt[tri] + betat[tri] * d, -fit.ACTION_LIMIT, fit.ACTION_LIMIT)
            teacher_loss = (((d[mask] - tt[tri][mask]) / teacher_scale) ** 2).mean()
            position_loss = (((action[mask] - yt[tri][mask]) / position_scale) ** 2).mean()
            correction = action - bt[tri]
            teacher_correction = teacher_action_t[tri] - bt[tri]
            n_ready = mask.sum(dim=1).clamp_min(1)[:, None]
            student_mean = correction.sum(dim=1) / n_ready
            teacher_mean = teacher_correction.sum(dim=1) / n_ready
            dc_loss = (((student_mean - teacher_mean) / dc_scale) ** 2).mean()
            loss = TEACHER_WEIGHT * teacher_loss + POSITION_WEIGHT * position_loss + CENTERED_DC_WEIGHT * dc_loss
            if not torch.isfinite(loss): raise RuntimeError(f"{fold_id}: nonfinite loss")
            loss.backward(); optimizer.step()
            if step == 0 or (step + 1) % 50 == 0:
                logs.append({"step": step + 1,
                             "teacher_normalized_mse": float(teacher_loss.detach().cpu()),
                             "position_normalized_mse": float(position_loss.detach().cpu()),
                             "teacher_centered_dc_normalized_mse": float(dc_loss.detach().cpu()),
                             "weighted_total": float(loss.detach().cpu())})
        model.eval()
        with torch.no_grad():
            raw, d = model(tx)
            d = torch.where(mt[:, :, None], d, torch.zeros_like(d))
            a = torch.clamp(bt + betat * d, -fit.ACTION_LIMIT, fit.ACTION_LIMIT)
        raw_np, d_np, a_np = (v.detach().cpu().numpy() for v in (raw, d, a))
        raw_oof[ho], delta_oof[ho], action_oof[ho] = raw_np[ho], d_np[ho], a_np[ho]
        ckpt = CKPT_DIR / f"{fold_id}_teacher_centered_dc.pt"
        torch.save({"state_dict": model.cpu().state_dict(), "normalizer_mean": mu,
                    "normalizer_std": sd, "fold_id": fold_id,
                    "train_scene_ids": spec["train_scene_ids"], "holdout_scene_ids": spec["holdout_scene_ids"],
                    "seed": seed, "steps": STEPS, "learning_rate": LR,
                    "teacher_scale_train_only_mps2": teacher_scale,
                    "position_scale_train_only_mps2": position_scale,
                    "dc_scale_train_only_mps2": dc_scale,
                    "teacher_npz_sha256": inputs["teacher_oof_sha256"]}, ckpt)
        folds_result[fold_id] = {
            "train_scene_ids": spec["train_scene_ids"], "holdout_scene_ids": spec["holdout_scene_ids"],
            "train_count": len(tr), "holdout_count": len(ho), "seed": seed,
            "teacher_rms_train_only_mps2": teacher_scale,
            "position_rms_train_only_mps2": position_scale,
            "dc_scale_train_only_mps2": dc_scale,
            "loss_log": logs, "checkpoint_sha256": file_sha(ckpt),
        }
        print(f"{fold_id}: completed, teacher-centered DC scale={dc_scale:.6g}", flush=True)

    if not np.isfinite(action_oof).all(): raise RuntimeError("Missing/nonfinite OOF actions")
    no_dc_metrics = old_results["method_metrics"]["teacher_position_balanced_OOF"]
    zero_dc_metrics = zero_results["method_metrics"]["dc_penalty_OOF"]
    position, task, lowfreq, mean_err = {}, {}, {}, {}
    teacher_mean = {}
    for i, sid in enumerate(ids):
        teacher_delta_action = (teacher_action[i] - base[i]).astype(np.float64)
        student_delta_action = (action_oof[i] - base[i]).astype(np.float64)
        teacher_mean[sid] = teacher_delta_action[ready[i]].mean(axis=0)
        student_mean = student_delta_action[ready[i]].mean(axis=0)
        position[sid] = position_rmse(action_oof[i], target[i], ready[i])
        task[sid] = fit.evaluate_task_action(i, action_oof[i], bundle["trajectories"][i])
        lowfreq[sid] = action_lowfreq(action_oof[i], base[i], ready[i], event_time[i])
        mean_err[sid] = {"teacher_mean_xyz_mps2": teacher_mean[sid].tolist(),
                         "student_mean_xyz_mps2": student_mean.tolist(),
                         "student_teacher_mean_error_xyz_mps2": (student_mean - teacher_mean[sid]).tolist(),
                         "student_teacher_mean_error_norm_mps2": float(np.linalg.norm(student_mean - teacher_mean[sid]))}
    pooled = np.concatenate([(action_oof[i, ready[i]] - target[i, ready[i]]).astype(np.float64) for i in range(24)], axis=0)
    metrics = {
        "C5_baseline": old_results["method_metrics"]["C5_baseline"],
        "student_no_dc": no_dc_metrics,
        "student_zero_dc_penalty": zero_dc_metrics,
        "teacher_centered_dc_OOF": {
            "position_residual_rmse_scene_macro_mps2": float(np.mean(list(position.values()))),
            "position_residual_rmse_pooled_mps2": float(np.sqrt(np.mean(pooled ** 2))),
            "task_frozen_SO3_rmse_scene_macro_rad": float(np.mean(list(task.values()))),
            "task_frozen_SO3_rmse_pooled_rad": float(np.sqrt(np.mean(np.square(list(task.values()))))),
            "per_scene_position_residual_rmse_mps2": position,
            "per_scene_task_frozen_SO3_rmse_rad": task,
            "per_scene_teacher_mean_tracking": mean_err,
            "mean_teacher_dc_tracking_error_macro_mps2": float(np.mean([v["student_teacher_mean_error_norm_mps2"] for v in mean_err.values()])),
            "mean_dc_bias_norm_macro_mps2": float(np.mean([v["scene_dc_bias_norm_mps2"] for v in lowfreq.values()])),
            "mean_1s_bias_norm_macro_mps2": float(np.mean([v["mean_1s_bias_norm_mps2"] for v in lowfreq.values()])),
            "max_1s_bias_norm_macro_mps2": float(np.mean([v["max_1s_bias_norm_mps2"] for v in lowfreq.values()])),
            "per_scene_action_low_frequency": lowfreq,
        },
    }
    np.savez_compressed(OOF_PATH, scene_ids=np.asarray(ids), fold_id=np.asarray(fold_for_row),
                        ready_mask=ready, event_time_s=event_time, target_clip_mps2=target,
                        teacher_delta_mps2=teacher_delta, teacher_action_mps2=teacher_action,
                        student_raw_delta_mps2=raw_oof, student_delta_mps2=delta_oof,
                        student_action_mps2=action_oof, c5_baseline_action_mps2=base)
    lock = {"schema": "COSINE_GRU_TRAIN24_TEACHER_CENTERED_DC_SOURCE_LOCK_V1",
            "input_hashes": inputs, "config_sha256": file_sha(PLAN),
            "script_sha256": file_sha(Path(__file__)), "oof_sha256": file_sha(OOF_PATH),
            "checkpoint_sha256_by_fold": {k: v["checkpoint_sha256"] for k, v in folds_result.items()},
            "fold_ids": [f["fold_id"] for f in folds], "scope": plan["scope"]}
    write_json(LOCK_PATH, lock)
    result = {
        "schema": "COSINE_GRU_TRAIN24_TEACHER_CENTERED_DC_RESULTS_V1",
        "scope": plan["scope"], "config_sha256": lock["config_sha256"],
        "script_sha256": lock["script_sha256"], "oof_sha256": lock["oof_sha256"],
        "input_hashes": inputs, "folds": folds_result, "method_metrics": metrics,
        "comparison_vs_zero_dc_position_win_tie_loss": [
            sum(position[s] < zero_dc_metrics["per_scene_position_residual_rmse_mps2"][s] for s in ids),
            sum(abs(position[s] - zero_dc_metrics["per_scene_position_residual_rmse_mps2"][s]) <= 1e-12 for s in ids),
            sum(position[s] > zero_dc_metrics["per_scene_position_residual_rmse_mps2"][s] for s in ids)],
        "comparison_vs_zero_dc_task_win_tie_loss": [
            sum(task[s] < zero_dc_metrics["per_scene_task_frozen_SO3_rmse_rad"][s] for s in ids),
            sum(abs(task[s] - zero_dc_metrics["per_scene_task_frozen_SO3_rmse_rad"][s]) <= 1e-12 for s in ids),
            sum(task[s] > zero_dc_metrics["per_scene_task_frozen_SO3_rmse_rad"][s] for s in ids)],
        "comparison_vs_no_dc_teacher_mean_error_win_tie_loss": [
            sum(mean_err[s]["student_teacher_mean_error_norm_mps2"] < np.linalg.norm((no_dc_action[i][ready[i]] - base[i][ready[i]]).mean(axis=0) - teacher_mean[s]) for i, s in enumerate(ids)),
            0,
            sum(mean_err[s]["student_teacher_mean_error_norm_mps2"] > np.linalg.norm((no_dc_action[i][ready[i]] - base[i][ready[i]]).mean(axis=0) - teacher_mean[s]) for i, s in enumerate(ids))],
        "runtime_seconds": time.perf_counter() - start,
        "interpretation_limit": "Frozen SO3 and position residual are OOF proxies; teacher-centered DC matching does not guarantee closed-loop position Q or passing B.",
    }
    write_json(RESULT_PATH, result)
    m = result["method_metrics"]
    table = ["# Teacher-centered DC OOF experiment", "", "## Prespecified recipe", "",
             "Same GRU, scene folds, seed schedule, 300 steps and Adam 1e-3 as the prior teacher+position/DC experiment. Loss = 0.5 normalized teacher-delta MSE + 0.5 normalized position-action MSE + 0.5 teacher-centered scene-mean action loss. The last term matches each training scene's student mean correction to its teacher mean correction, scaled by 0.1×training-fold teacher RMS. Means, scales and X14 normalization are training-fold-only; teacher is not an inference input.",
             "",
             "This follow-up tests only the hypothesis that keeping the teacher's TRAIN-only scene mean recovers some frozen posture benefit suppressed by the zero-mean penalty. It does not turn the teacher's frozen-task benefit into a closed-loop Q guarantee. The parent-reported pilot showed position improvement without beating B on attitude; no heldout/pilot values were used to choose this objective or its constants.", "",
             "## Aggregate OOF", "",
             "| Method | Position macro (m/s²) | Frozen SO(3) macro (rad) | Teacher DC tracking error (m/s²) | DC bias norm (m/s²) | Mean 1-s bias (m/s²) |",
             "|---|---:|---:|---:|---:|---:|"]
    for key, label in (("C5_baseline", "C5"), ("student_no_dc", "No-DC teacher+position"),
                       ("student_zero_dc_penalty", "Zero-DC penalty"), ("teacher_centered_dc_OOF", "Teacher-centered DC")):
        v = m[key]
        table.append(f"| {label} | {v['position_residual_rmse_scene_macro_mps2']:.6f} | {v['task_frozen_SO3_rmse_scene_macro_rad']:.6f} | {v.get('mean_teacher_dc_tracking_error_macro_mps2', float('nan')):.6f} | {v.get('mean_dc_bias_norm_macro_mps2', v.get('action_delta_scene_dc_bias_norm_macro_mps2', 0.0)):.6f} | {v.get('mean_1s_bias_norm_macro_mps2', v.get('action_delta_mean_1s_bias_norm_macro_mps2', 0.0)):.6f} |")
    table += ["", f"Position and frozen task win/tie/loss vs zero-DC arm: `{result['comparison_vs_zero_dc_position_win_tie_loss']}` and `{result['comparison_vs_zero_dc_task_win_tie_loss']}`.",
              f"Teacher-mean tracking closer/equal/farther vs no-DC student: `{result['comparison_vs_no_dc_teacher_mean_error_win_tie_loss']}`.", "",
              "## Per-scene OOF", "", "| Scene | Fold | Position (m/s²) | SO(3) (rad) | Teacher-mean error (m/s²) | DC bias norm (m/s²) | max 1-s bias (m/s²) |", "|---|---|---:|---:|---:|---:|---:|"]
    for i, sid in enumerate(ids):
        q = m["teacher_centered_dc_OOF"]
        table.append(f"| {sid} | {fold_for_row[i]} | {position[sid]:.5f} | {task[sid]:.5f} | {mean_err[sid]['student_teacher_mean_error_norm_mps2']:.5f} | {lowfreq[sid]['scene_dc_bias_norm_mps2']:.5f} | {lowfreq[sid]['max_1s_bias_norm_mps2']:.5f} |")
    table += ["", "## Limits", "",
              "All task scores are frozen-state command-filter replays, not closed-loop attitude results. Position residual is the supervised 10-ms label metric, not Q. The teacher-centered loss uses held-out teacher means only in post-hoc OOF comparison; only training-fold teacher labels enter optimization. No VAL/TEST, Plant, or inertia reconstruction was used.", "",
              f"- Config SHA-256: `{file_sha(PLAN)}`", f"- Script SHA-256: `{file_sha(Path(__file__))}`",
              f"- OOF SHA-256: `{lock['oof_sha256']}`", f"- Results SHA-256: `{file_sha(RESULT_PATH)}`", ""]
    REPORT = OUT / "REPORT_v1.md"
    REPORT.write_text("\n".join(table), encoding="utf-8")
    print(json.dumps({"position_macro": m["teacher_centered_dc_OOF"]["position_residual_rmse_scene_macro_mps2"],
                      "task_macro": m["teacher_centered_dc_OOF"]["task_frozen_SO3_rmse_scene_macro_rad"],
                      "teacher_mean_error": m["teacher_centered_dc_OOF"]["mean_teacher_dc_tracking_error_macro_mps2"],
                      "report_sha256": file_sha(REPORT), "oof_sha256": lock["oof_sha256"]}, ensure_ascii=False), flush=True)


if __name__ == "__main__": main()
