#!/usr/bin/env python3
"""Fixed scene-group OOF GRU with a fold-local per-scene DC action penalty."""
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
PREVIOUS = DATA_DIR / "teacher_position_balanced_cv_v1"
sys.path.insert(0, str(SOURCE))
import fit_task_aware_fourfold_v1 as fit  # noqa: E402
from task_aware_common import (DATA_MANIFEST_PATH, DATA_PATH, SOURCE_LOCK_PATH,
                               load_locked_inputs, sha256)  # noqa: E402

TEACHER_NPZ = SOURCE / "TRAIN24_FEASIBILITY_TEACHER_DELTAS_v1.npz"
TEACHER_META = SOURCE / "TRAIN24_FEASIBILITY_TEACHER_MANIFEST_v1.json"
PREVIOUS_OOF = PREVIOUS / "TEACHER_POSITION_BALANCED_OOF_v1.npz"
PREVIOUS_RESULTS = PREVIOUS / "TEACHER_POSITION_BALANCED_RESULTS_v1.json"
PLAN = OUT / "PREDECLARED_CONFIG_v1.json"
OOF_PATH = OUT / "DC_PENALTY_OOF_v1.npz"
RESULTS = OUT / "DC_PENALTY_RESULTS_v1.json"
REPORT = OUT / "REPORT_v1.md"
LOCK = OUT / "DC_PENALTY_SOURCE_LOCK_v1.json"
CKPT_DIR = OUT / "checkpoints"

SEED, STEPS, LR = 20261028, 300, 1e-3
TEACHER_WEIGHT, POSITION_WEIGHT, DC_WEIGHT = 0.5, 0.5, 0.5
DC_SCALE_RATIO = 0.1


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def position_rmse(action: np.ndarray, target: np.ndarray, ready: np.ndarray) -> float:
    e = action[ready].astype(np.float64) - target[ready].astype(np.float64)
    return float(np.sqrt(np.mean(e * e)))


def summarize_actions(action: np.ndarray, base: np.ndarray, ready: np.ndarray,
                      event_time: np.ndarray) -> dict:
    delta = (action - base).astype(np.float64)
    delta[~ready] = 0.0
    ready_delta = delta[ready]
    bins = np.floor(event_time).astype(int)
    means = np.asarray([delta[bins == b].mean(axis=0) for b in range(20)])
    # Event-level impulse proxy: sum of held action changes over each 10-ms interval.
    delta_v = np.sum(delta, axis=0) * 0.01
    return {
        "mean_action_delta_xyz_mps2": ready_delta.mean(axis=0).tolist(),
        "scene_dc_bias_norm_mps2": float(np.linalg.norm(ready_delta.mean(axis=0))),
        "action_delta_rms_mps2": float(np.sqrt(np.mean(ready_delta ** 2))),
        "mean_1s_bias_norm_mps2": float(np.mean(np.linalg.norm(means, axis=1))),
        "max_1s_bias_norm_mps2": float(np.max(np.linalg.norm(means, axis=1))),
        "max_1s_bias_vector_xyz_mps2": means[int(np.argmax(np.linalg.norm(means, axis=1)))].tolist(),
        "cumulative_delta_velocity_proxy_xyz_mps": delta_v.tolist(),
    }


IDS: list[str] = []


def main() -> None:
    for p in (PLAN, OOF_PATH, RESULTS, REPORT, LOCK):
        if p.exists():
            raise RuntimeError(f"Refusing to overwrite {p}")
    if any(CKPT_DIR.iterdir()):
        raise RuntimeError("Refusing to overwrite checkpoints")
    bundle = load_locked_inputs()
    data, manifest = bundle["arrays"], bundle["manifest"]
    global IDS
    IDS = data["scene_ids"].astype(str).tolist()
    x = data["x14_model_input"].astype(np.float32)
    ready = data["ready_mask"].astype(bool)
    target = data["target_interval_clip_mps2"].astype(np.float32)
    base = np.clip(data["applied_acceleration_event_mps2"].astype(np.float32), -3.0, 3.0)
    event_time = data["event_time_s"].astype(np.float64)
    event_idx = data["event_index_zero_based"].astype(np.int64)
    beta = np.clip(event_time / fit.BETA_RISE_S, 0.0, 1.0)[..., None].astype(np.float32)
    fold_specs = manifest["scene_folds"]
    if [f["holdout_scene_count"] for f in fold_specs] != [6, 8, 4, 6]:
        raise RuntimeError("Fixed whole-scene fold sizes changed")

    input_hashes = {
        "dataset_sha256": sha256(DATA_PATH),
        "dataset_manifest_sha256": sha256(DATA_MANIFEST_PATH),
        "dataset_source_lock_sha256": sha256(SOURCE_LOCK_PATH),
        "teacher_npz_sha256": sha256(TEACHER_NPZ),
        "teacher_manifest_sha256": sha256(TEACHER_META),
        "previous_dc_free_oof_sha256": file_sha(PREVIOUS_OOF),
        "previous_dc_free_results_sha256": file_sha(PREVIOUS_RESULTS),
    }
    previous_results = json.loads(PREVIOUS_RESULTS.read_text(encoding="utf-8"))
    if (previous_results.get("input_hashes", {}).get("dataset_sha256") != input_hashes["dataset_sha256"] or
            previous_results.get("oof_sha256") != input_hashes["previous_dc_free_oof_sha256"]):
        raise RuntimeError("Prior OOF comparison no longer binds to current dataset/artifact")
    with np.load(TEACHER_NPZ, allow_pickle=False) as z:
        teacher_ids = z["scene_ids"].astype(str).tolist()
        teacher_folds = z["fold_id"].astype(str).tolist()
        teacher_ready = z["ready_mask"].astype(bool)
        teacher_target = z["target_clip_mps2"].astype(np.float32)
        teacher = z["teacher_delta_mps2"].astype(np.float32)
    teacher_meta = json.loads(TEACHER_META.read_text(encoding="utf-8"))
    expected_fold_by_id = {sid: f["fold_id"] for f in fold_specs for sid in f["holdout_scene_ids"]}
    fold_by_row = [expected_fold_by_id[sid] for sid in IDS]
    if (teacher_ids != IDS or teacher_folds != fold_by_row or teacher.shape != base.shape or
            not np.array_equal(teacher_ready, ready) or not np.array_equal(teacher_target, target) or
            not np.isfinite(teacher).all() or
            teacher_meta.get("teacher_delta_npz_sha256") != input_hashes["teacher_npz_sha256"] or
            teacher_meta.get("dataset_sha256") != input_hashes["dataset_sha256"]):
        raise RuntimeError("Teacher labels do not bind to exact TRAIN24 source rows/folds")
    with np.load(PREVIOUS_OOF, allow_pickle=False) as z:
        if (z["scene_ids"].astype(str).tolist() != IDS or
                not np.array_equal(z["ready_mask"].astype(bool), ready) or
                not np.array_equal(z["target_clip_mps2"].astype(np.float32), target)):
            raise RuntimeError("Previous OOF artifact does not align with locked TRAIN24")
        previous_action = z["student_action_mps2"].astype(np.float32)
    if not np.isfinite(previous_action).all() or not np.array_equal(data["fold_id"].astype(str), fold_by_row):
        raise RuntimeError("Prior OOF or source scene-group fold labels are invalid")

    plan = {
        "schema": "COSINE_GRU_TRAIN24_TEACHER_POSITION_DC_PENALTY_PREDECLARED_V1",
        "scope": "Causal X14; fixed scene-group OOF on locked TRAIN_C5_24 only. No VAL/TEST read, Plant call, inertia reconstruction, or model selection from holdout folds.",
        "model": "Same ResidualGRU(14,32)->Linear(32,3) as the DC-free teacher+position student.",
        "source_hashes": input_hashes,
        "fixed_training": {
            "seed_base": SEED, "steps_per_fold": STEPS, "optimizer": "Adam", "learning_rate": LR,
            "normalizer": "Per-fold X14 mean/std from training scene rows only; all causal event rows.",
            "base_objective": "0.5*mean(((delta-teacher_delta)/teacher_train_RMS)^2) + 0.5*mean(((student_action-position_target)/C5_position_error_train_RMS)^2), ready rows only.",
            "dc_penalty": "0.5*mean_scene,axis((mean_ready(student_action-C5_action)/(0.1*teacher_train_RMS))^2).",
            "dc_scale": "0.1 times the current fold's teacher delta RMS from training scenes only; fixed ratio, no heldout-based fitting.",
            "reason": "Directly penalize the scene-level DC action change flagged by the predeclared TRAIN24 audit; track one-second means as a diagnostic.",
            "action": "clip(C5_action + clip(t/1.8,0,1)*clip(delta,-0.5,0.5), -3,3); non-ready residual masked to zero.",
        },
        "folds": [{"fold_id": f["fold_id"], "train_scene_ids": f["train_scene_ids"],
                   "holdout_scene_ids": f["holdout_scene_ids"],
                   "train_count": f["train_scene_count"], "holdout_count": f["holdout_scene_count"]}
                  for f in fold_specs],
        "created_before_optimization": True,
    }
    write_json(PLAN, plan)

    torch.set_num_threads(1)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    torch.use_deterministic_algorithms(True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    x_t = torch.as_tensor(x, device=device)
    ready_t = torch.as_tensor(ready, device=device, dtype=torch.bool)
    teacher_t = torch.as_tensor(teacher, device=device)
    base_t = torch.as_tensor(base, device=device)
    beta_t = torch.as_tensor(beta, device=device)
    target_t = torch.as_tensor(target, device=device)
    action_oof = np.full_like(base, np.nan, dtype=np.float32)
    delta_oof = np.full_like(base, np.nan, dtype=np.float32)
    raw_oof = np.full_like(base, np.nan, dtype=np.float32)
    fold_results = {}
    start = time.perf_counter()
    for fi, spec in enumerate(fold_specs):
        fold_id = spec["fold_id"]
        train = [IDS.index(sid) for sid in spec["train_scene_ids"]]
        hold = [IDS.index(sid) for sid in spec["holdout_scene_ids"]]
        if len(train) != spec["train_scene_count"] or len(hold) != spec["holdout_scene_count"] or set(train) & set(hold) or set(train) | set(hold) != set(range(24)):
            raise RuntimeError(f"{fold_id}: invalid exact whole-scene partition")
        mu = x[train].reshape(-1, 14).mean(axis=0)
        sd = x[train].reshape(-1, 14).std(axis=0)
        sd[sd < 1e-6] = 1.0
        xn = ((x - mu[None, None, :]) / sd[None, None, :]).astype(np.float32)
        tx = torch.as_tensor(xn, device=device)
        tri = torch.as_tensor(train, device=device, dtype=torch.long)
        mask = ready_t[tri]
        teacher_scale = float(np.sqrt(np.mean(teacher[train][ready[train]].astype(np.float64) ** 2)))
        c5e = base[train][ready[train]].astype(np.float64) - target[train][ready[train]].astype(np.float64)
        position_scale = float(np.sqrt(np.mean(c5e ** 2)))
        dc_scale = DC_SCALE_RATIO * teacher_scale
        if min(teacher_scale, position_scale, dc_scale) <= 1e-8:
            raise RuntimeError(f"{fold_id}: invalid train-only objective scale")

        seed = SEED + fi
        random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
        if torch.cuda.is_available(): torch.cuda.manual_seed_all(seed)
        model = fit.ResidualGRU().to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=LR)
        loss_log = []
        for step in range(STEPS):
            optimizer.zero_grad(set_to_none=True)
            _, d = model(tx[tri])
            d = torch.where(mask[:, :, None], d, torch.zeros_like(d))
            action = torch.clamp(base_t[tri] + beta_t[tri] * d, -fit.ACTION_LIMIT, fit.ACTION_LIMIT)
            teacher_loss = (((d[mask] - teacher_t[tri][mask]) / teacher_scale) ** 2).mean()
            position_loss = (((action[mask] - target_t[tri][mask]) / position_scale) ** 2).mean()
            correction = action - base_t[tri]
            scene_mean = correction.sum(dim=1) / mask.sum(dim=1).clamp_min(1)[:, None]
            dc_loss = ((scene_mean / dc_scale) ** 2).mean()
            total = TEACHER_WEIGHT * teacher_loss + POSITION_WEIGHT * position_loss + DC_WEIGHT * dc_loss
            if not torch.isfinite(total):
                raise RuntimeError(f"{fold_id}: nonfinite loss at step {step + 1}")
            total.backward()
            optimizer.step()
            if step == 0 or (step + 1) % 50 == 0:
                loss_log.append({"step": step + 1,
                                 "teacher_normalized_mse": float(teacher_loss.detach().cpu()),
                                 "position_normalized_mse": float(position_loss.detach().cpu()),
                                 "scene_dc_bias_normalized_mse": float(dc_loss.detach().cpu()),
                                 "weighted_total": float(total.detach().cpu())})
        model.eval()
        with torch.no_grad():
            raw_all, d_all = model(tx)
            d_all = torch.where(ready_t[:, :, None], d_all, torch.zeros_like(d_all))
            a_all = torch.clamp(base_t + beta_t * d_all, -fit.ACTION_LIMIT, fit.ACTION_LIMIT)
        raw_np, d_np, a_np = (v.detach().cpu().numpy() for v in (raw_all, d_all, a_all))
        raw_oof[hold], delta_oof[hold], action_oof[hold] = raw_np[hold], d_np[hold], a_np[hold]
        ckpt = CKPT_DIR / f"{fold_id}_dc_penalty.pt"
        torch.save({"state_dict": model.cpu().state_dict(), "normalizer_mean": mu,
                    "normalizer_std": sd, "fold_id": fold_id,
                    "train_scene_ids": spec["train_scene_ids"],
                    "holdout_scene_ids": spec["holdout_scene_ids"], "seed": seed,
                    "steps": STEPS, "learning_rate": LR,
                    "teacher_scale_train_only_mps2": teacher_scale,
                    "position_scale_train_only_mps2": position_scale,
                    "dc_scale_train_only_mps2": dc_scale,
                    "teacher_npz_sha256": input_hashes["teacher_npz_sha256"]}, ckpt)
        fold_results[fold_id] = {
            "train_scene_ids": spec["train_scene_ids"], "holdout_scene_ids": spec["holdout_scene_ids"],
            "train_count": len(train), "holdout_count": len(hold), "seed": seed,
            "normalizer_scope": "Training-fold scenes only; all causal X14 rows.",
            "teacher_scale_train_only_mps2": teacher_scale,
            "position_scale_train_only_mps2": position_scale,
            "dc_scale_train_only_mps2": dc_scale,
            "loss_log": loss_log, "checkpoint_sha256": file_sha(ckpt),
        }
        print(f"{fold_id}: complete, dc-scale={dc_scale:.6g}", flush=True)

    if not np.isfinite(action_oof).all():
        raise RuntimeError("Missing/nonfinite scene-group OOF predictions")
    old_metrics = previous_results["method_metrics"]
    new_position, new_task, lowfreq = {}, {}, {}
    for i, sid in enumerate(IDS):
        new_position[sid] = position_rmse(action_oof[i], target[i], ready[i])
        lowfreq[sid] = summarize_actions(action_oof[i], base[i], ready[i], event_time[i])
    previous_lowfreq = {sid: summarize_actions(previous_action[i], base[i], ready[i], event_time[i])
                        for i, sid in enumerate(IDS)}
    for i, sid in enumerate(IDS):
        new_task[sid] = fit.evaluate_task_action(i, action_oof[i], bundle["trajectories"][i])

    pooled_err = np.concatenate([(action_oof[i, ready[i]].astype(np.float64) - target[i, ready[i]].astype(np.float64)) for i in range(24)], axis=0)
    metrics = {
        "C5_baseline": old_metrics["C5_baseline"],
        "prior_teacher_position_no_dc_OOF": old_metrics["teacher_position_balanced_OOF"],
        "dc_penalty_OOF": {
            "position_residual_rmse_scene_macro_mps2": float(np.mean(list(new_position.values()))),
            "position_residual_rmse_pooled_mps2": float(np.sqrt(np.mean(pooled_err ** 2))),
            "task_frozen_SO3_rmse_scene_macro_rad": float(np.mean(list(new_task.values()))),
            "task_frozen_SO3_rmse_pooled_rad": float(np.sqrt(np.mean(np.square(list(new_task.values()))))),
            "per_scene_position_residual_rmse_mps2": new_position,
            "per_scene_task_frozen_SO3_rmse_rad": new_task,
            "per_scene_action_low_frequency": lowfreq,
            "action_delta_scene_dc_bias_norm_macro_mps2": float(np.mean([v["scene_dc_bias_norm_mps2"] for v in lowfreq.values()])),
            "action_delta_mean_1s_bias_norm_macro_mps2": float(np.mean([v["mean_1s_bias_norm_mps2"] for v in lowfreq.values()])),
            "action_delta_max_1s_bias_norm_macro_mps2": float(np.mean([v["max_1s_bias_norm_mps2"] for v in lowfreq.values()])),
            "action_delta_rms_pooled_mps2": float(np.sqrt(np.mean(np.square(np.concatenate([action_oof[i, ready[i]] - base[i, ready[i]] for i in range(24)], axis=0))))),
        },
    }
    metrics["C5_baseline"]["action_delta_scene_dc_bias_norm_macro_mps2"] = 0.0
    metrics["C5_baseline"]["action_delta_mean_1s_bias_norm_macro_mps2"] = 0.0
    metrics["prior_teacher_position_no_dc_OOF"]["per_scene_action_low_frequency"] = previous_lowfreq
    metrics["prior_teacher_position_no_dc_OOF"]["action_delta_scene_dc_bias_norm_macro_mps2"] = float(np.mean([v["scene_dc_bias_norm_mps2"] for v in previous_lowfreq.values()]))
    metrics["prior_teacher_position_no_dc_OOF"]["action_delta_mean_1s_bias_norm_macro_mps2"] = float(np.mean([v["mean_1s_bias_norm_mps2"] for v in previous_lowfreq.values()]))

    np.savez_compressed(OOF_PATH, scene_ids=np.asarray(IDS), fold_id=np.asarray(fold_by_row),
                        ready_mask=ready, event_time_s=event_time, target_clip_mps2=target,
                        teacher_delta_mps2=teacher, c5_baseline_action_mps2=base,
                        student_raw_delta_mps2=raw_oof, student_delta_mps2=delta_oof,
                        student_action_mps2=action_oof)
    lock = {"schema": "COSINE_GRU_TRAIN24_TEACHER_POSITION_DC_PENALTY_SOURCE_LOCK_V1",
            "input_hashes": input_hashes, "config_sha256": file_sha(PLAN),
            "script_sha256": file_sha(Path(__file__)), "oof_sha256": file_sha(OOF_PATH),
            "checkpoint_sha256_by_fold": {k: v["checkpoint_sha256"] for k, v in fold_results.items()},
            "fold_ids": [f["fold_id"] for f in fold_specs],
            "scope": plan["scope"]}
    write_json(LOCK, lock)
    result = {
        "schema": "COSINE_GRU_TRAIN24_TEACHER_POSITION_DC_PENALTY_RESULTS_V1",
        "scope": plan["scope"], "config_sha256": lock["config_sha256"],
        "script_sha256": lock["script_sha256"], "oof_sha256": lock["oof_sha256"],
        "input_hashes": input_hashes, "folds": fold_results, "method_metrics": metrics,
        "comparison_vs_C5_position_win_tie_loss": [
            sum(new_position[s] < old_metrics["C5_baseline"]["per_scene_position_residual_rmse_mps2"][s] for s in IDS),
            sum(abs(new_position[s] - old_metrics["C5_baseline"]["per_scene_position_residual_rmse_mps2"][s]) <= 1e-12 for s in IDS),
            sum(new_position[s] > old_metrics["C5_baseline"]["per_scene_position_residual_rmse_mps2"][s] for s in IDS)],
        "comparison_vs_prior_position_position_win_tie_loss": [
            sum(new_position[s] < old_metrics["teacher_position_balanced_OOF"]["per_scene_position_residual_rmse_mps2"][s] for s in IDS),
            sum(abs(new_position[s] - old_metrics["teacher_position_balanced_OOF"]["per_scene_position_residual_rmse_mps2"][s]) <= 1e-12 for s in IDS),
            sum(new_position[s] > old_metrics["teacher_position_balanced_OOF"]["per_scene_position_residual_rmse_mps2"][s] for s in IDS)],
        "comparison_vs_C5_task_win_tie_loss": [
            sum(new_task[s] < old_metrics["C5_baseline"]["per_scene_task_frozen_SO3_rmse_rad"][s] for s in IDS),
            sum(abs(new_task[s] - old_metrics["C5_baseline"]["per_scene_task_frozen_SO3_rmse_rad"][s]) <= 1e-12 for s in IDS),
            sum(new_task[s] > old_metrics["C5_baseline"]["per_scene_task_frozen_SO3_rmse_rad"][s] for s in IDS)],
        "comparison_vs_prior_task_win_tie_loss": [
            sum(new_task[s] < old_metrics["teacher_position_balanced_OOF"]["per_scene_task_frozen_SO3_rmse_rad"][s] for s in IDS),
            sum(abs(new_task[s] - old_metrics["teacher_position_balanced_OOF"]["per_scene_task_frozen_SO3_rmse_rad"][s]) <= 1e-12 for s in IDS),
            sum(new_task[s] > old_metrics["teacher_position_balanced_OOF"]["per_scene_task_frozen_SO3_rmse_rad"][s] for s in IDS)],
        "runtime_seconds": time.perf_counter() - start,
        "interpretation_limit": "OOF position residual and frozen SO3 are offline/frozen-history proxies; no counterfactual closed-loop Q is estimated.",
    }
    write_json(RESULTS, result)
    m = result["method_metrics"]
    dc, old, c5 = (m["dc_penalty_OOF"], m["prior_teacher_position_no_dc_OOF"], m["C5_baseline"])
    report = [
        "# Scene-group OOF with per-scene DC action-bias penalty", "",
        "## Fixed objective and protocol", "",
        "- Same causal X14 GRU, four whole-scene folds, 300 steps/fold, Adam 1e-3 and seeds 20261028 + fold index.",
        "- Base loss: 0.5 teacher-delta normalized MSE + 0.5 position-action normalized MSE; each scale uses ready rows from that fold's training scenes only.",
        "- Added one fixed term: 0.5 times the mean squared per-scene action-change mean, normalized by `(0.1 × training-fold teacher RMS)`. The penalized signal is `mean_ready(student_action − C5_action)` by scene and axis.",
        "- The four actual train/holdout counts are 18/6, 16/8, 20/4 and 18/6. X14 normalization uses training-fold rows only. No VAL/TEST data, Plant call, or inertia reconstruction.",
        "- Teacher labels are auxiliary training supervision only; they are not part of inference.", "",
        "## OOF results", "",
        "| Method | Position residual macro (m/s²) | Position residual pooled (m/s²) | Frozen SO(3) macro (rad) | Frozen SO(3) pooled (rad) | DC action bias macro (m/s²) | 1-s bias norm macro (m/s²) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for key, label in (("C5_baseline", "C5 baseline"),
                       ("prior_teacher_position_no_dc_OOF", "Prior teacher + position OOF"),
                       ("dc_penalty_OOF", "New DC-penalty OOF")):
        v = m[key]
        report.append(f"| {label} | {v['position_residual_rmse_scene_macro_mps2']:.6f} | {v['position_residual_rmse_pooled_mps2']:.6f} | {v['task_frozen_SO3_rmse_scene_macro_rad']:.6f} | {v['task_frozen_SO3_rmse_pooled_rad']:.6f} | {v['action_delta_scene_dc_bias_norm_macro_mps2']:.6f} | {v.get('action_delta_mean_1s_bias_norm_macro_mps2', 0.0):.6f} |")
    report += ["", f"Position win/tie/loss vs C5: `{result['comparison_vs_C5_position_win_tie_loss']}`; frozen posture: `{result['comparison_vs_C5_task_win_tie_loss']}`.",
               f"Position win/tie/loss vs prior student: `{result['comparison_vs_prior_position_position_win_tie_loss']}`; frozen posture: `{result['comparison_vs_prior_task_win_tie_loss']}`.", "",
               "## Fold scales", "", "| Fold | train/holdout | teacher RMS | position RMS | DC scale |", "|---|---:|---:|---:|---:|"]
    for fold, fr in fold_results.items():
        report.append(f"| {fold} | {fr['train_count']}/{fr['holdout_count']} | {fr['teacher_scale_train_only_mps2']:.6f} | {fr['position_scale_train_only_mps2']:.6f} | {fr['dc_scale_train_only_mps2']:.6f} |")
    report += ["", "## Per-scene held-out diagnostics", "",
               "| Scene | Fold | Prior position | New position | Prior SO(3) | New SO(3) | Prior DC | New DC | New max 1-s bias |",
               "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for sid in IDS:
        old_dc = previous_lowfreq[sid]["scene_dc_bias_norm_mps2"]
        new_dc = lowfreq[sid]["scene_dc_bias_norm_mps2"]
        report.append(f"| {sid} | {fold_by_row[IDS.index(sid)]} | {old['per_scene_position_residual_rmse_mps2'][sid]:.5f} | {dc['per_scene_position_residual_rmse_mps2'][sid]:.5f} | {old['per_scene_task_frozen_SO3_rmse_rad'][sid]:.5f} | {dc['per_scene_task_frozen_SO3_rmse_rad'][sid]:.5f} | {old_dc:.5f} | {new_dc:.5f} | {lowfreq[sid]['max_1s_bias_norm_mps2']:.5f} |")
    report += ["", "## Interpretation limits", "",
               "This fixed penalty directly targets scene-level DC action change and tracks one-second block means. These are training/OOF diagnostics; they do not simulate candidate state feedback and cannot establish closed-loop Q. No weights were selected or changed after seeing held-out scores. The low-frequency hypothesis is supported only if the new OOF DC and one-second bias decrease without unacceptable degradation in position residual or frozen SO(3); closed-loop benefit still requires a separately authorized paired evaluation.", "",
               f"- Plan SHA-256: `{file_sha(PLAN)}`",
               f"- Script SHA-256: `{file_sha(Path(__file__))}`",
               f"- OOF SHA-256: `{lock['oof_sha256']}`",
               f"- Results SHA-256: `{file_sha(RESULTS)}`", ""]
    REPORT.write_text("\n".join(report), encoding="utf-8")
    print(json.dumps({"position_macro": metrics["dc_penalty_OOF"]["position_residual_rmse_scene_macro_mps2"],
                      "task_macro": metrics["dc_penalty_OOF"]["task_frozen_SO3_rmse_scene_macro_rad"],
                      "dc_bias_macro": metrics["dc_penalty_OOF"]["action_delta_scene_dc_bias_norm_macro_mps2"],
                      "one_second_bias_macro": metrics["dc_penalty_OOF"]["action_delta_mean_1s_bias_norm_macro_mps2"],
                      "oof_sha256": lock["oof_sha256"],
                      "report_sha256": file_sha(REPORT)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
