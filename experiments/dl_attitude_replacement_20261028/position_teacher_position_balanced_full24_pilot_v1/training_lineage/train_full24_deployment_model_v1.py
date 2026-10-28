#!/usr/bin/env python3
"""Fit the fixed teacher/position-balanced GRU once on all locked TRAIN24 scenes."""
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
PLAN = OUT / "PREDECLARED_FULL24_CONFIG_v1.json"
CKPT = OUT / "DEPLOYMENT_MODEL_v1.pt"
EXPORT = OUT / "DEPLOYMENT_MODEL_WEIGHTS_v1.npz"
RESULT = OUT / "FULL24_TRAINING_RESULT_v1.json"

SEED, STEPS, LR = 20261028, 300, 1e-3
TEACHER_WEIGHT = POSITION_WEIGHT = 0.5


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    for path in (PLAN, CKPT, EXPORT, RESULT):
        if path.exists():
            raise RuntimeError(f"Refusing to overwrite {path}")
    bundle = load_locked_inputs()
    data, manifest = bundle["arrays"], bundle["manifest"]
    ids = data["scene_ids"].astype(str).tolist()
    if len(ids) != 24 or len(set(ids)) != 24 or manifest.get("scene_count") != 24:
        raise RuntimeError("Expected the exact locked TRAIN_C5_24 cohort")
    x = data["x14_model_input"].astype(np.float32)
    ready = data["ready_mask"].astype(bool)
    target = data["target_interval_clip_mps2"].astype(np.float32)
    base = np.clip(data["applied_acceleration_event_mps2"].astype(np.float32),
                   -fit.ACTION_LIMIT, fit.ACTION_LIMIT)
    event_t = data["event_time_s"].astype(np.float32)
    beta = np.clip(event_t / fit.BETA_RISE_S, 0.0, 1.0)[..., None].astype(np.float32)
    with np.load(TEACHER_NPZ, allow_pickle=False) as z:
        teacher_ids = z["scene_ids"].astype(str).tolist()
        teacher_ready = z["ready_mask"].astype(bool)
        teacher_target = z["target_clip_mps2"].astype(np.float32)
        teacher = z["teacher_delta_mps2"].astype(np.float32)
    teacher_meta = json.loads(TEACHER_META.read_text(encoding="utf-8"))
    input_hashes = {
        "dataset_sha256": sha(DATA_PATH), "dataset_manifest_sha256": sha(DATA_MANIFEST_PATH),
        "dataset_source_lock_sha256": sha(SOURCE_LOCK_PATH),
        "teacher_delta_npz_sha256": sha(TEACHER_NPZ),
        "teacher_manifest_sha256": sha(TEACHER_META),
    }
    if (teacher_ids != ids or not np.array_equal(teacher_ready, ready) or
            not np.array_equal(teacher_target, target) or teacher.shape != (24, 1999, 3) or
            not np.isfinite(teacher).all() or
            teacher_meta.get("teacher_delta_npz_sha256") != input_hashes["teacher_delta_npz_sha256"] or
            teacher_meta.get("dataset_sha256") != input_hashes["dataset_sha256"]):
        raise RuntimeError("Teacher labels do not bind to the full locked TRAIN24 inputs")

    # Freeze and write the deployment-training plan before optimization.
    plan = {
        "schema": "COSINE_GRU_C5_TRAIN24_TEACHER_POSITION_BALANCED_FULL24_DEPLOY_CONFIG_V1",
        "role": "Single deployment fit on all 24 authorized TRAIN_C5_24 scenes; this is not validation or OOF evaluation.",
        "model": "GRU(input=14, hidden=32, batch_first) -> Linear(32,3); zero-initialized head.",
        "training_scene_ids": ids, "training_scene_count": 24,
        "input_hashes": input_hashes,
        "seed": SEED, "steps": STEPS, "optimizer": "Adam", "learning_rate": LR,
        "normalizer": "X14 mean/std over all 24 TRAIN_C5_24 scenes and all causal event rows; std floor 1e-6 -> 1.",
        "objective": "0.5*mean(((student_delta-teacher_delta)/teacher_train_RMS)^2) + 0.5*mean(((student_action-position_target)/C5_position_error_train_RMS)^2), ready rows only.",
        "loss_scales": "RMS values computed over ready rows from all 24 TRAIN_C5_24 training scenes only.",
        "teacher_role": "Auxiliary training supervision only; excluded from deployed inference inputs and tau_score scoring.",
        "action": "clip(a_C5 + clip(t/1.8,0,1)*clip(delta,-0.5,0.5), -3,3); non-ready residual masked to zero.",
        "scope": "No VAL/TEST data read; no Plant call; no inertia reconstruction.",
    }
    write_json(PLAN, plan)

    # Full-cohort normalization and objective scales use training data only.
    mu = x.reshape(-1, 14).mean(axis=0)
    sd = x.reshape(-1, 14).std(axis=0)
    sd[sd < 1e-6] = 1.0
    teacher_scale = float(np.sqrt(np.mean(teacher[ready].astype(np.float64) ** 2)))
    c5_err = base[ready].astype(np.float64) - target[ready].astype(np.float64)
    position_scale = float(np.sqrt(np.mean(c5_err ** 2)))
    if min(teacher_scale, position_scale) <= 1e-8:
        raise RuntimeError("Invalid full-training loss scale")

    torch.set_num_threads(1)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    torch.use_deterministic_algorithms(True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    random.seed(SEED); np.random.seed(SEED); torch.manual_seed(SEED)
    if torch.cuda.is_available(): torch.cuda.manual_seed_all(SEED)
    model = fit.ResidualGRU().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=LR)
    xn = ((x - mu[None, None, :]) / sd[None, None, :]).astype(np.float32)
    tx = torch.as_tensor(xn, device=device)
    tm = torch.as_tensor(ready, device=device, dtype=torch.bool)
    ty = torch.as_tensor(target, device=device)
    tb = torch.as_tensor(beta, device=device)
    ta = torch.as_tensor(base, device=device)
    td = torch.as_tensor(teacher, device=device)
    logs = []
    start = time.perf_counter()
    for step in range(STEPS):
        optimizer.zero_grad(set_to_none=True)
        _, d = model(tx)
        d = torch.where(tm[:, :, None], d, torch.zeros_like(d))
        action = torch.clamp(ta + tb * d, -fit.ACTION_LIMIT, fit.ACTION_LIMIT)
        teacher_loss = (((d[tm] - td[tm]) / teacher_scale) ** 2).mean()
        position_loss = (((action[tm] - ty[tm]) / position_scale) ** 2).mean()
        loss = TEACHER_WEIGHT * teacher_loss + POSITION_WEIGHT * position_loss
        if not torch.isfinite(loss):
            raise RuntimeError(f"Nonfinite full24 objective at step {step + 1}")
        loss.backward()
        optimizer.step()
        if step == 0 or (step + 1) % 50 == 0:
            row = {"step": step + 1,
                   "teacher_normalized_mse": float(teacher_loss.detach().cpu()),
                   "position_normalized_mse": float(position_loss.detach().cpu()),
                   "weighted_total": float(loss.detach().cpu())}
            logs.append(row)
            print(json.dumps(row), flush=True)

    model = model.cpu().eval()
    checkpoint = {
        "schema": "COSINE_GRU_C5_TRAIN24_TEACHER_POSITION_BALANCED_DEPLOYMENT_MODEL_V1",
        "state_dict": model.state_dict(), "normalizer_mean": mu.astype(np.float32),
        "normalizer_std": sd.astype(np.float32), "input_size": 14, "hidden_size": 32,
        "seed": SEED, "steps": STEPS, "learning_rate": LR,
        "teacher_scale_train_all24_mps2": teacher_scale,
        "position_scale_train_all24_mps2": position_scale,
        "scene_ids": ids, "dataset_sha256": input_hashes["dataset_sha256"],
        "teacher_npz_sha256": input_hashes["teacher_delta_npz_sha256"],
        "teacher_used_at_inference": False,
        "inference_contract": {
            "feature": "current causal X14 vector, same 14 logged position features, in training order",
            "hidden": "32-vector carried within a scene and reset to zeros at scene start; update hidden even while residual is not ready",
            "delta": "clip(head(GRU((x14-mean)/std)), -0.5, 0.5) m/s^2",
            "action": "clip(C5_base_action + clip(t_event_s/1.8,0,1)*delta, -3,3) m/s^2; emit zero residual when ready=false",
        },
    }
    torch.save(checkpoint, CKPT)
    state = model.state_dict()
    np.savez_compressed(EXPORT,
        gru_weight_ih_l0=state["gru.weight_ih_l0"].numpy(),
        gru_weight_hh_l0=state["gru.weight_hh_l0"].numpy(),
        gru_bias_ih_l0=state["gru.bias_ih_l0"].numpy(),
        gru_bias_hh_l0=state["gru.bias_hh_l0"].numpy(),
        head_weight=state["head.weight"].numpy(), head_bias=state["head.bias"].numpy(),
        input_mean=mu.astype(np.float32), input_std=sd.astype(np.float32),
        teacher_scale_train_all24_mps2=np.asarray(teacher_scale, dtype=np.float32),
        position_scale_train_all24_mps2=np.asarray(position_scale, dtype=np.float32))

    result = {
        "schema": "COSINE_GRU_C5_TRAIN24_TEACHER_POSITION_BALANCED_FULL24_DEPLOY_TRAINING_RESULT_V1",
        "role": "Deployment fit; no validation or OOF score produced.",
        "config_sha256": sha(PLAN), "script_sha256": sha(Path(__file__)),
        "checkpoint_sha256": sha(CKPT), "weights_export_sha256": sha(EXPORT),
        "dataset_sha256": input_hashes["dataset_sha256"],
        "teacher_npz_sha256": input_hashes["teacher_delta_npz_sha256"],
        "training_scene_count": 24, "training_scene_ids": ids,
        "teacher_scale_train_all24_mps2": teacher_scale,
        "position_scale_train_all24_mps2": position_scale,
        "training_loss_log": logs, "runtime_seconds": time.perf_counter() - start,
        "teacher_used_at_inference": False,
        "scope": "No VAL/TEST data read, no Plant call, no inertia reconstruction.",
    }
    write_json(RESULT, result)
    print(json.dumps({"checkpoint_sha256": result["checkpoint_sha256"],
                      "weights_export_sha256": result["weights_export_sha256"],
                      "training_scenes": 24, "runtime_seconds": result["runtime_seconds"]}), flush=True)


if __name__ == "__main__":
    main()
