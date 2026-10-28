#!/usr/bin/env python3
"""Fixed four-fold causal GRU: balanced TRAIN-fold teacher and position losses."""
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
SOURCE = ROOT / "experiments/dl_attitude_replacement_20261028/position_cosine_gru_train24_causal_v1/task_aware_cv_v1"
sys.path.insert(0, str(SOURCE))
import fit_task_aware_fourfold_v1 as fit  # noqa: E402
from task_aware_common import (DATA_MANIFEST_PATH, DATA_PATH, SOURCE_LOCK_PATH,
                               load_locked_inputs, sha256)  # noqa: E402

TEACHER_NPZ = SOURCE / "TRAIN24_FEASIBILITY_TEACHER_DELTAS_v1.npz"
TEACHER_META = SOURCE / "TRAIN24_FEASIBILITY_TEACHER_MANIFEST_v1.json"
DISTILL_OOF = SOURCE / "TRAIN24_TEACHER_DISTILLATION_OOF_v1.npz"
TASK_OOF = SOURCE / "TASK_AWARE_CV_OOF_v1.npz"
DISTILL_RESULTS = SOURCE / "TRAIN24_TEACHER_DISTILLATION_RESULTS_v1.json"
TASK_RESULTS = SOURCE / "TASK_AWARE_CV_RESULTS_v1.json"
PLAN = OUT / "PREDECLARED_CONFIG_v1.json"
OOF_PATH = OUT / "TEACHER_POSITION_BALANCED_OOF_v1.npz"
RESULTS_PATH = OUT / "TEACHER_POSITION_BALANCED_RESULTS_v1.json"
LOCK_PATH = OUT / "TEACHER_POSITION_BALANCED_SOURCE_LOCK_v1.json"
CKPT_DIR = OUT / "checkpoints"

SEED = 20261028
STEPS = 300
LR = 1e-3
TEACHER_WEIGHT = 0.5
POSITION_WEIGHT = 0.5


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def pos_rmse(action: np.ndarray, target: np.ndarray, ready: np.ndarray) -> float:
    e = action[ready].astype(np.float64) - target[ready].astype(np.float64)
    return float(np.sqrt(np.mean(e * e)))


def scene_metrics(actions: np.ndarray, target: np.ndarray, ready: np.ndarray,
                  ids: list[str], trajectories: list[dict]) -> dict:
    pos, task = {}, {}
    errors = []
    for i, sid in enumerate(ids):
        pos[sid] = pos_rmse(actions[i], target[i], ready[i])
        task[sid] = fit.evaluate_task_action(i, actions[i], trajectories[i])
        errors.append(actions[i, ready[i]].astype(np.float64) - target[i, ready[i]].astype(np.float64))
    pooled = np.concatenate(errors, axis=0)
    return {
        "position_residual_rmse_scene_macro_mps2": float(np.mean(list(pos.values()))),
        "position_residual_rmse_pooled_mps2": float(np.sqrt(np.mean(pooled ** 2))),
        "task_frozen_SO3_rmse_scene_macro_rad": float(np.mean(list(task.values()))),
        "task_frozen_SO3_rmse_pooled_rad": float(np.sqrt(np.mean(np.square(list(task.values()))))),
        "per_scene_position_residual_rmse_mps2": pos,
        "per_scene_task_frozen_SO3_rmse_rad": task,
    }


def main() -> None:
    for p in (OOF_PATH, RESULTS_PATH, LOCK_PATH):
        if p.exists():
            raise RuntimeError(f"Refusing to overwrite {p}")
    if any(CKPT_DIR.iterdir()):
        raise RuntimeError("Refusing to overwrite checkpoints")
    bundle = load_locked_inputs()
    data, manifest = bundle["arrays"], bundle["manifest"]
    ids = data["scene_ids"].astype(str).tolist()
    x = data["x14_model_input"].astype(np.float32)
    ready = data["ready_mask"].astype(bool)
    target = data["target_interval_clip_mps2"].astype(np.float32)
    base = np.clip(data["applied_acceleration_event_mps2"].astype(np.float32),
                   -fit.ACTION_LIMIT, fit.ACTION_LIMIT)
    event_t = data["event_time_s"].astype(np.float32)
    beta = np.clip(event_t / fit.BETA_RISE_S, 0.0, 1.0)[..., None].astype(np.float32)
    expected_folds = manifest["scene_folds"]
    if [f["holdout_scene_count"] for f in expected_folds] != [6, 8, 4, 6]:
        raise RuntimeError("The fixed 6/8/4/6 whole-scene fold split changed")

    teacher_meta = json.loads(TEACHER_META.read_text(encoding="utf-8"))
    input_hashes = {
        "dataset_sha256": sha256(DATA_PATH),
        "dataset_manifest_sha256": sha256(DATA_MANIFEST_PATH),
        "dataset_source_lock_sha256": sha256(SOURCE_LOCK_PATH),
        "teacher_delta_npz_sha256": sha256(TEACHER_NPZ),
        "teacher_manifest_sha256": sha256(TEACHER_META),
        "prior_distill_oof_sha256": sha256(DISTILL_OOF),
        "prior_distill_results_sha256": sha256(DISTILL_RESULTS),
        "task_aware_oof_sha256": sha256(TASK_OOF),
        "task_aware_results_sha256": sha256(TASK_RESULTS),
    }
    if (teacher_meta.get("teacher_delta_npz_sha256") != input_hashes["teacher_delta_npz_sha256"] or
            teacher_meta.get("dataset_sha256") != input_hashes["dataset_sha256"] or
            teacher_meta.get("dataset_manifest_sha256") != input_hashes["dataset_manifest_sha256"] or
            teacher_meta.get("dataset_source_lock_sha256") != input_hashes["dataset_source_lock_sha256"]):
        raise RuntimeError("Existing teacher does not bind the locked TRAIN24 inputs")
    with np.load(TEACHER_NPZ, allow_pickle=False) as z:
        teacher_ids = z["scene_ids"].astype(str).tolist()
        teacher_fold = z["fold_id"].astype(str).tolist()
        teacher_ready = z["ready_mask"].astype(bool)
        teacher_target = z["target_clip_mps2"].astype(np.float32)
        teacher = z["teacher_delta_mps2"].astype(np.float32)
    folds_for_ids = {sid: fold["fold_id"] for fold in expected_folds for sid in fold["holdout_scene_ids"]}
    data_fold = data["fold_id"].astype(str).tolist()
    if (teacher_ids != ids or teacher_fold != data_fold or teacher.shape != (24, 1999, 3) or
            not np.array_equal(teacher_ready, ready) or not np.array_equal(teacher_target, target) or
            not np.isfinite(teacher).all() or data_fold != [folds_for_ids[sid] for sid in ids]):
        raise RuntimeError("Teacher labels, folds, or causal dataset rows do not align")

    # Record the complete fixed plan before any optimization begins.
    plan = {
        "schema": "COSINE_GRU_C5_TRAIN24_TEACHER_POSITION_BALANCED_PREDECLARED_V1",
        "scope": "TRAIN_C5_24 only; causal X14; scene-group OOF; no VAL/TEST raw, Plant, or inertia reconstruction.",
        "model": "Existing ResidualGRU: GRU(14,32)->Linear(32,3), zero-initialized head, per-scene hidden reset.",
        "input_bindings": input_hashes,
        "script_sha256": sha256_file(Path(__file__)),
        "fixed_training": {
            "seed_base": SEED, "steps_per_fold": STEPS, "optimizer": "Adam",
            "learning_rate": LR, "fold_count": 4,
            "normalizer": "X14 mean/std across training-fold scenes and all causal rows only; applied unchanged to every row.",
            "action": "clip(a_C5 + beta(t)*clip(delta,-0.5,0.5), -3, 3); beta=clip(t/1.8,0,1); non-ready delta masked to zero.",
            "loss": "0.5*mean(((student_delta-teacher_delta)/teacher_train_RMS)^2) + 0.5*mean(((student_action-position_target)/C5_position_error_train_RMS)^2), ready rows only.",
            "loss_scales": "Each RMS is computed only from ready rows in this fold's 18 training scenes; no held-out rows enter either scale.",
            "teacher_labels": "Saved feasibility-teacher delta; only training-fold labels participate in the loss.",
            "position_target": "Logged 10-ms clipped interval acceleration target, from the training scenes only.",
            "weights": {"teacher_normalized_mse": TEACHER_WEIGHT, "position_normalized_mse": POSITION_WEIGHT},
        },
        "folds": [{"fold_id": f["fold_id"], "train_scene_ids": f["train_scene_ids"],
                   "holdout_scene_ids": f["holdout_scene_ids"],
                   "train_count": f["train_scene_count"], "holdout_count": f["holdout_scene_count"]}
                  for f in expected_folds],
        "created_before_training": True,
    }
    write_json(PLAN, plan)

    torch.set_num_threads(1)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    torch.use_deterministic_algorithms(True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    start = time.perf_counter()
    x_t = torch.as_tensor(x, device=device)
    ready_t = torch.as_tensor(ready, device=device, dtype=torch.bool)
    teacher_t = torch.as_tensor(teacher, device=device)
    base_t = torch.as_tensor(base, device=device)
    beta_t = torch.as_tensor(beta, device=device)
    target_t = torch.as_tensor(target, device=device)
    pred = np.full_like(base, np.nan, dtype=np.float32)
    delta_oof = np.full_like(base, np.nan, dtype=np.float32)
    raw_oof = np.full_like(base, np.nan, dtype=np.float32)
    fold_results = {}

    for fi, spec in enumerate(expected_folds):
        fold_id = spec["fold_id"]
        tr = [ids.index(s) for s in spec["train_scene_ids"]]
        ho = [ids.index(s) for s in spec["holdout_scene_ids"]]
        if len(tr) != spec["train_scene_count"] or len(ho) != spec["holdout_scene_count"] or set(tr) & set(ho) or set(tr) | set(ho) != set(range(24)):
            raise RuntimeError(f"{fold_id}: invalid exact scene partition")
        mu = x[tr].reshape(-1, 14).mean(axis=0)
        sd = x[tr].reshape(-1, 14).std(axis=0)
        sd[sd < 1e-6] = 1.0
        xn = ((x - mu[None, None, :]) / sd[None, None, :]).astype(np.float32)
        tx = torch.as_tensor(xn, device=device)
        tri = torch.as_tensor(tr, device=device, dtype=torch.long)
        mask = ready_t[tri]
        teacher_scale = float(np.sqrt(np.mean(teacher[tr][ready[tr]].astype(np.float64) ** 2)))
        c5_err = base[tr][ready[tr]].astype(np.float64) - target[tr][ready[tr]].astype(np.float64)
        position_scale = float(np.sqrt(np.mean(c5_err ** 2)))
        if min(teacher_scale, position_scale) <= 1e-8:
            raise RuntimeError(f"{fold_id}: invalid training-only loss scale")

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
            pred_tr = torch.clamp(base_t[tri] + beta_t[tri] * d, -fit.ACTION_LIMIT, fit.ACTION_LIMIT)
            teacher_loss = (((d[mask] - teacher_t[tri][mask]) / teacher_scale) ** 2).mean()
            position_loss = (((pred_tr[mask] - target_t[tri][mask]) / position_scale) ** 2).mean()
            loss = TEACHER_WEIGHT * teacher_loss + POSITION_WEIGHT * position_loss
            if not torch.isfinite(loss):
                raise RuntimeError(f"{fold_id}: non-finite loss at step {step + 1}")
            loss.backward()
            optimizer.step()
            if step == 0 or (step + 1) % 50 == 0:
                loss_log.append({"step": step + 1,
                                 "teacher_normalized_mse": float(teacher_loss.detach().cpu()),
                                 "position_normalized_mse": float(position_loss.detach().cpu()),
                                 "weighted_total": float(loss.detach().cpu())})
        model.eval()
        with torch.no_grad():
            raw_all, d_all = model(tx)
            d_all = torch.where(ready_t[:, :, None], d_all, torch.zeros_like(d_all))
            action_all = torch.clamp(base_t + beta_t * d_all, -fit.ACTION_LIMIT, fit.ACTION_LIMIT)
        raw_np, delta_np, action_np = (v.detach().cpu().numpy() for v in (raw_all, d_all, action_all))
        raw_oof[ho], delta_oof[ho], pred[ho] = raw_np[ho], delta_np[ho], action_np[ho]
        ckpt = CKPT_DIR / f"{fold_id}_teacher_position_balanced.pt"
        torch.save({"state_dict": model.cpu().state_dict(), "normalizer_mean": mu,
                    "normalizer_std": sd, "fold_id": fold_id,
                    "train_scene_ids": spec["train_scene_ids"],
                    "holdout_scene_ids": spec["holdout_scene_ids"], "seed": seed,
                    "steps": STEPS, "learning_rate": LR,
                    "teacher_scale_train_only_mps2": teacher_scale,
                    "position_scale_train_only_mps2": position_scale,
                    "teacher_npz_sha256": input_hashes["teacher_delta_npz_sha256"]}, ckpt)
        fold_results[fold_id] = {
            "train_scene_ids": spec["train_scene_ids"], "holdout_scene_ids": spec["holdout_scene_ids"],
            "train_count": len(tr), "holdout_count": len(ho), "seed": seed,
            "normalizer_fit_scope": "training-fold scenes only; all causal X14 rows",
            "teacher_scale_train_only_mps2": teacher_scale,
            "position_scale_C5_error_train_only_mps2": position_scale,
            "loss_log": loss_log, "checkpoint_sha256": sha256_file(ckpt),
        }
        print(f"{fold_id}: complete, scales teacher={teacher_scale:.6g} position={position_scale:.6g}", flush=True)

    if not (np.isfinite(pred).all() and np.isfinite(delta_oof).all() and np.isfinite(raw_oof).all()):
        raise RuntimeError("Missing or nonfinite OOF outputs")
    metrics = {"C5_baseline": scene_metrics(base, target, ready, ids, bundle["trajectories"]),
               "teacher_position_balanced_OOF": scene_metrics(pred, target, ready, ids, bundle["trajectories"])}
    prior_arrays = {}
    with np.load(DISTILL_OOF, allow_pickle=False) as z:
        prior_ids = z["scene_ids"].astype(str).tolist()
        if prior_ids != ids or not np.array_equal(z["ready_mask"], ready) or not np.array_equal(z["target_clip_mps2"], target):
            raise RuntimeError("Prior student OOF does not bind exact same TRAIN24 rows")
        prior_arrays["prior_causal_teacher_student_OOF"] = z["student_action_oof_mps2"].astype(np.float32)
        prior_arrays["ordinary_position_student_OOF"] = z["ordinary_head_oof_action_mps2"].astype(np.float32)
        prior_arrays["task_head_from_teacher_OOF"] = z["task_head_oof_action_mps2"].astype(np.float32)
    with np.load(TASK_OOF, allow_pickle=False) as z:
        if z["scene_ids"].astype(str).tolist() != ids or not np.array_equal(z["ready_mask"], ready) or not np.array_equal(z["target_clip_mps2"], target):
            raise RuntimeError("Task-aware OOF does not bind exact same TRAIN24 rows")
        prior_arrays["task_aware_fourfold_OOF"] = z["task_action_lambda_task_0_1"].astype(np.float32)
    for name, actions in prior_arrays.items():
        metrics[name] = scene_metrics(actions, target, ready, ids, bundle["trajectories"])

    oof_fold = [folds_for_ids[s] for s in ids]
    np.savez_compressed(OOF_PATH, scene_ids=np.asarray(ids), fold_id=np.asarray(oof_fold),
                        ready_mask=ready, event_time_s=event_t, target_clip_mps2=target,
                        teacher_delta_mps2=teacher, student_raw_delta_mps2=raw_oof,
                        student_delta_mps2=delta_oof, student_action_mps2=pred,
                        c5_baseline_action_mps2=base)
    lock = {"schema": "COSINE_GRU_C5_TRAIN24_TEACHER_POSITION_BALANCED_SOURCE_LOCK_V1",
            "dataset_sha256": input_hashes["dataset_sha256"],
            "teacher_npz_sha256": input_hashes["teacher_delta_npz_sha256"],
            "prior_distill_oof_sha256": input_hashes["prior_distill_oof_sha256"],
            "task_aware_oof_sha256": input_hashes["task_aware_oof_sha256"],
            "script_sha256": sha256_file(Path(__file__)),
            "predeclared_config_sha256": sha256_file(PLAN),
            "oof_sha256": sha256_file(OOF_PATH),
            "checkpoint_sha256_by_fold": {k: v["checkpoint_sha256"] for k, v in fold_results.items()},
            "fold_ids": [f["fold_id"] for f in expected_folds],
            "scope": "Causal X14, strict scene-group OOF, fold-only normalization/loss scales, TRAIN24 only."}
    write_json(LOCK_PATH, lock)
    results = {
        "schema": "COSINE_GRU_C5_TRAIN24_TEACHER_POSITION_BALANCED_RESULTS_V1",
        "scope": lock["scope"], "predeclared_config_sha256": lock["predeclared_config_sha256"],
        "input_hashes": input_hashes, "folds": fold_results,
        "method_metrics": metrics,
        "comparison_vs_C5_scene_counts_position_win_tie_loss": [
            sum(metrics["teacher_position_balanced_OOF"]["per_scene_position_residual_rmse_mps2"][s] < metrics["C5_baseline"]["per_scene_position_residual_rmse_mps2"][s] for s in ids),
            sum(abs(metrics["teacher_position_balanced_OOF"]["per_scene_position_residual_rmse_mps2"][s] - metrics["C5_baseline"]["per_scene_position_residual_rmse_mps2"][s]) <= 1e-12 for s in ids),
            sum(metrics["teacher_position_balanced_OOF"]["per_scene_position_residual_rmse_mps2"][s] > metrics["C5_baseline"]["per_scene_position_residual_rmse_mps2"][s] for s in ids)],
        "comparison_vs_C5_scene_counts_task_win_tie_loss": [
            sum(metrics["teacher_position_balanced_OOF"]["per_scene_task_frozen_SO3_rmse_rad"][s] < metrics["C5_baseline"]["per_scene_task_frozen_SO3_rmse_rad"][s] for s in ids),
            sum(abs(metrics["teacher_position_balanced_OOF"]["per_scene_task_frozen_SO3_rmse_rad"][s] - metrics["C5_baseline"]["per_scene_task_frozen_SO3_rmse_rad"][s]) <= 1e-12 for s in ids),
            sum(metrics["teacher_position_balanced_OOF"]["per_scene_task_frozen_SO3_rmse_rad"][s] > metrics["C5_baseline"]["per_scene_task_frozen_SO3_rmse_rad"][s] for s in ids)],
        "runtime_seconds": time.perf_counter() - start,
        "oof_path": str(OOF_PATH.relative_to(ROOT)).replace("\\", "/"),
        "oof_sha256": sha256_file(OOF_PATH),
        "limitations": ["TRAIN24 only; parent trajectories are in-sample relative to the frozen parent model.",
                        "Task SO3 is a frozen-state/reference replay, not closed-loop validation.",
                        "No VAL/TEST, Plant, inertia reconstruction, or independent generalization claim."],
    }
    write_json(RESULTS_PATH, results)
    print(json.dumps({"position_macro": metrics["teacher_position_balanced_OOF"]["position_residual_rmse_scene_macro_mps2"],
                      "task_macro": metrics["teacher_position_balanced_OOF"]["task_frozen_SO3_rmse_scene_macro_rad"],
                      "oof_sha256": lock["oof_sha256"]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
