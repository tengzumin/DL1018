#!/usr/bin/env python3
"""Single full-TRAIN24 deployment fit of the fixed DC-penalized objective."""
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
CV = DATA_DIR / "teacher_position_balanced_dc_penalty_cv_v1"
sys.path.insert(0, str(SOURCE))
import fit_task_aware_fourfold_v1 as fit  # noqa: E402
from task_aware_common import (DATA_MANIFEST_PATH, DATA_PATH, SOURCE_LOCK_PATH,
                               load_locked_inputs, sha256)  # noqa: E402

TEACHER_NPZ = SOURCE / "TRAIN24_FEASIBILITY_TEACHER_DELTAS_v1.npz"
TEACHER_META = SOURCE / "TRAIN24_FEASIBILITY_TEACHER_MANIFEST_v1.json"
CV_PLAN = CV / "PREDECLARED_CONFIG_v1.json"
CV_OOF = CV / "DC_PENALTY_OOF_v1.npz"
CV_RESULT = CV / "DC_PENALTY_RESULTS_v1.json"
CV_LOCK = CV / "DC_PENALTY_SOURCE_LOCK_v1.json"

PLAN = OUT / "PREDECLARED_FULL24_CONFIG_v1.json"
CHECKPOINT = OUT / "DEPLOYMENT_MODEL_v1.pt"
EXPORT_NPZ = OUT / "DEPLOYMENT_WEIGHTS_v1.npz"
RESULT = OUT / "FULL24_TRAINING_RESULT_v1.json"
LOCK = OUT / "FULL24_SOURCE_LOCK_v1.json"

SEED, STEPS, LR = 20261028, 300, 1e-3
TEACHER_WEIGHT, POSITION_WEIGHT, DC_WEIGHT = 0.5, 0.5, 0.5
DC_SCALE_RATIO = 0.1


def write_json(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    for p in (PLAN, CHECKPOINT, EXPORT_NPZ, RESULT, LOCK):
        if p.exists():
            raise RuntimeError(f"Refusing to overwrite {p}")
    bundle = load_locked_inputs()
    data = bundle["arrays"]
    ids = data["scene_ids"].astype(str).tolist()
    if len(ids) != 24 or len(set(ids)) != 24:
        raise RuntimeError("Expected exact 24-scene TRAIN_C5_24")
    x = data["x14_model_input"].astype(np.float32)
    ready = data["ready_mask"].astype(bool)
    target = data["target_interval_clip_mps2"].astype(np.float32)
    base = np.clip(data["applied_acceleration_event_mps2"].astype(np.float32), -3.0, 3.0)
    event_time = data["event_time_s"].astype(np.float32)
    beta = np.clip(event_time / fit.BETA_RISE_S, 0.0, 1.0)[..., None].astype(np.float32)

    with np.load(TEACHER_NPZ, allow_pickle=False) as z:
        teacher_ids = z["scene_ids"].astype(str).tolist()
        teacher_ready = z["ready_mask"].astype(bool)
        teacher_target = z["target_clip_mps2"].astype(np.float32)
        teacher = z["teacher_delta_mps2"].astype(np.float32)
    teacher_meta = json.loads(TEACHER_META.read_text(encoding="utf-8"))
    input_hashes = {
        "dataset_sha256": sha256(DATA_PATH),
        "dataset_manifest_sha256": sha256(DATA_MANIFEST_PATH),
        "dataset_source_lock_sha256": sha256(SOURCE_LOCK_PATH),
        "teacher_npz_sha256": sha256(TEACHER_NPZ),
        "teacher_manifest_sha256": sha256(TEACHER_META),
        "cv_plan_sha256": file_sha(CV_PLAN), "cv_oof_sha256": file_sha(CV_OOF),
        "cv_results_sha256": file_sha(CV_RESULT), "cv_source_lock_sha256": file_sha(CV_LOCK),
    }
    cv_result = json.loads(CV_RESULT.read_text(encoding="utf-8"))
    cv_lock = json.loads(CV_LOCK.read_text(encoding="utf-8"))
    if (teacher_ids != ids or not np.array_equal(teacher_ready, ready) or
            not np.array_equal(teacher_target, target) or teacher.shape != (24, 1999, 3) or
            not np.isfinite(teacher).all() or
            teacher_meta.get("teacher_delta_npz_sha256") != input_hashes["teacher_npz_sha256"] or
            teacher_meta.get("dataset_sha256") != input_hashes["dataset_sha256"] or
            cv_result.get("oof_sha256") != input_hashes["cv_oof_sha256"] or
            cv_lock.get("oof_sha256") != input_hashes["cv_oof_sha256"] or
            cv_lock.get("config_sha256") != input_hashes["cv_plan_sha256"]):
        raise RuntimeError("Teacher, CV experiment or TRAIN24 source bindings do not match")

    plan = {
        "schema": "COSINE_GRU_TRAIN24_TEACHER_POSITION_DC_PENALTY_FULL24_DEPLOY_CONFIG_V1",
        "role": "Single full-TRAIN24 deployment fit; not validation, OOF, or hyperparameter selection.",
        "training_scene_count": 24, "training_scene_ids": ids,
        "input_hashes": input_hashes,
        "architecture": "GRU(input=14, hidden=32, batch_first)->Linear(32,3); zero-initialized output head.",
        "seed": SEED, "steps": STEPS, "optimizer": "Adam", "learning_rate": LR,
        "normalizer": "X14 mean/std over all rows of these 24 authorized TRAIN_C5_24 scenes only; std floor 1e-6 -> 1.",
        "base_loss": "0.5*mean(((delta-teacher_delta)/teacher_train_RMS)^2) + 0.5*mean(((student_action-position_target)/C5_position_error_train_RMS)^2), ready events only.",
        "dc_penalty": "0.5*mean_scene,axis((mean_ready(student_action-C5_action)/(0.1*teacher_train_RMS))^2).",
        "scales": "All teacher RMS, C5 position-error RMS, X14 normalization, and DC scale are computed on all 24 training scenes only; DC scale is exactly 0.1*teacher RMS.",
        "action": "clip(C5_action + clip(event_time_s/1.8,0,1)*clip(delta,-0.5,0.5), -3,3); residual zero while not ready.",
        "teacher_role": "Auxiliary training supervision only; not used by inference or tau_score.",
        "scope": "No VAL/TEST read; no Plant call; no inertia reconstruction.",
        "copied_cv_recipe": "Weights and DC scale ratio exactly match the predeclared four-fold experiment; one full24 fit uses all 24 authorized training scenes.",
        "created_before_optimization": True,
    }
    write_json(PLAN, plan)

    mean = x.reshape(-1, 14).mean(axis=0)
    std = x.reshape(-1, 14).std(axis=0)
    std[std < 1e-6] = 1.0
    teacher_scale = float(np.sqrt(np.mean(teacher[ready].astype(np.float64) ** 2)))
    c5_error = base[ready].astype(np.float64) - target[ready].astype(np.float64)
    position_scale = float(np.sqrt(np.mean(c5_error ** 2)))
    dc_scale = DC_SCALE_RATIO * teacher_scale
    if min(teacher_scale, position_scale, dc_scale) <= 1e-8:
        raise RuntimeError("Invalid full24 train-only objective scale")

    torch.set_num_threads(1)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    torch.use_deterministic_algorithms(True)
    random.seed(SEED); np.random.seed(SEED); torch.manual_seed(SEED)
    if torch.cuda.is_available(): torch.cuda.manual_seed_all(SEED)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = fit.ResidualGRU().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=LR)
    xn = ((x - mean[None, None, :]) / std[None, None, :]).astype(np.float32)
    tx = torch.as_tensor(xn, device=device)
    mask = torch.as_tensor(ready, device=device, dtype=torch.bool)
    ty = torch.as_tensor(target, device=device)
    tb = torch.as_tensor(beta, device=device)
    ta = torch.as_tensor(base, device=device)
    tt = torch.as_tensor(teacher, device=device)
    logs = []
    start = time.perf_counter()
    for step in range(STEPS):
        optimizer.zero_grad(set_to_none=True)
        _, delta = model(tx)
        delta = torch.where(mask[:, :, None], delta, torch.zeros_like(delta))
        action = torch.clamp(ta + tb * delta, -fit.ACTION_LIMIT, fit.ACTION_LIMIT)
        teacher_loss = (((delta[mask] - tt[mask]) / teacher_scale) ** 2).mean()
        position_loss = (((action[mask] - ty[mask]) / position_scale) ** 2).mean()
        correction = action - ta
        scene_mean = correction.sum(dim=1) / mask.sum(dim=1).clamp_min(1)[:, None]
        dc_loss = ((scene_mean / dc_scale) ** 2).mean()
        total = TEACHER_WEIGHT * teacher_loss + POSITION_WEIGHT * position_loss + DC_WEIGHT * dc_loss
        if not torch.isfinite(total):
            raise RuntimeError(f"Nonfinite full24 objective at step {step + 1}")
        total.backward()
        optimizer.step()
        if step == 0 or (step + 1) % 50 == 0:
            row = {"step": step + 1,
                   "teacher_normalized_mse": float(teacher_loss.detach().cpu()),
                   "position_normalized_mse": float(position_loss.detach().cpu()),
                   "scene_dc_bias_normalized_mse": float(dc_loss.detach().cpu()),
                   "weighted_total": float(total.detach().cpu())}
            logs.append(row)
            print(json.dumps(row), flush=True)

    model = model.cpu().eval()
    state = model.state_dict()
    checkpoint = {
        "schema": "COSINE_GRU_C5_TRAIN24_TEACHER_POSITION_DC_PENALTY_DEPLOYMENT_MODEL_V1",
        "state_dict": state, "normalizer_mean": mean.astype(np.float32),
        "normalizer_std": std.astype(np.float32), "input_size": 14, "hidden_size": 32,
        "seed": SEED, "steps": STEPS, "learning_rate": LR,
        "teacher_scale_train_all24_mps2": teacher_scale,
        "position_scale_train_all24_mps2": position_scale,
        "dc_scale_train_all24_mps2": dc_scale,
        "scene_ids": ids, "dataset_sha256": input_hashes["dataset_sha256"],
        "teacher_npz_sha256": input_hashes["teacher_npz_sha256"],
        "teacher_used_at_inference": False,
        "runtime_contract": {
            "input": "current causal X14 in training order; current C5 event action; event_time_s; ready flag",
            "hidden": "32-state carried within one scene, zero-initialized/reset at scene start; hidden advances during warmup",
            "delta": "clip(head(GRU((X14-input_mean)/input_std)), -0.5,0.5) m/s^2",
            "action": "clip(C5_action + clip(event_time_s/1.8,0,1)*delta, -3,3) m/s^2; delta=0 while not ready",
            "teacher": "not loaded by inference",
        },
    }
    torch.save(checkpoint, CHECKPOINT)
    np.savez_compressed(EXPORT_NPZ,
        gru_weight_ih_l0=state["gru.weight_ih_l0"].numpy(),
        gru_weight_hh_l0=state["gru.weight_hh_l0"].numpy(),
        gru_bias_ih_l0=state["gru.bias_ih_l0"].numpy(),
        gru_bias_hh_l0=state["gru.bias_hh_l0"].numpy(),
        head_weight=state["head.weight"].numpy(), head_bias=state["head.bias"].numpy(),
        input_mean=mean.astype(np.float32), input_std=std.astype(np.float32),
        teacher_scale_train_all24_mps2=np.asarray(teacher_scale, np.float32),
        position_scale_train_all24_mps2=np.asarray(position_scale, np.float32),
        dc_scale_train_all24_mps2=np.asarray(dc_scale, np.float32))
    result = {
        "schema": "COSINE_GRU_TRAIN24_TEACHER_POSITION_DC_PENALTY_FULL24_TRAINING_RESULT_V1",
        "role": "Full24 deployment fit only; no validation or OOF evaluation was performed.",
        "config_sha256": file_sha(PLAN), "script_sha256": file_sha(Path(__file__)),
        "checkpoint_sha256": file_sha(CHECKPOINT), "weights_export_npz_sha256": file_sha(EXPORT_NPZ),
        "dataset_sha256": input_hashes["dataset_sha256"],
        "teacher_npz_sha256": input_hashes["teacher_npz_sha256"],
        "cv_experiment_oof_sha256": input_hashes["cv_oof_sha256"],
        "training_scene_count": 24, "training_scene_ids": ids,
        "teacher_scale_train_all24_mps2": teacher_scale,
        "position_scale_train_all24_mps2": position_scale,
        "dc_scale_train_all24_mps2": dc_scale,
        "train_loss_log": logs, "runtime_seconds": time.perf_counter() - start,
        "teacher_used_at_inference": False,
        "scope": plan["scope"],
    }
    write_json(RESULT, result)
    lock = {
        "schema": "COSINE_GRU_TRAIN24_TEACHER_POSITION_DC_PENALTY_FULL24_SOURCE_LOCK_V1",
        "input_hashes": input_hashes, "config_sha256": file_sha(PLAN),
        "script_sha256": file_sha(Path(__file__)),
        "checkpoint_sha256": file_sha(CHECKPOINT), "weights_export_npz_sha256": file_sha(EXPORT_NPZ),
        "training_result_sha256": file_sha(RESULT), "training_scene_ids": ids,
        "scope": plan["scope"],
    }
    write_json(LOCK, lock)
    print(json.dumps({"checkpoint_sha256": lock["checkpoint_sha256"],
                      "weights_npz_sha256": lock["weights_export_npz_sha256"],
                      "teacher_scale": teacher_scale, "position_scale": position_scale,
                      "dc_scale": dc_scale, "runtime_seconds": result["runtime_seconds"]}), flush=True)


if __name__ == "__main__":
    main()
