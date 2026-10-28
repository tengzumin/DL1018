#!/usr/bin/env python3
"""Export deterministic TRAIN24 inputs and DC-model eventwise references."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import torch
from scipy.io import savemat

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DATA = ROOT / "experiments/dl_attitude_replacement_20261028/position_cosine_gru_train24_causal_v1"
MODEL_SOURCE = DATA / "teacher_position_balanced_dc_penalty_full24_deploy_v1"
TASK = DATA / "task_aware_cv_v1"
sys.path.insert(0, str(TASK))
import fit_task_aware_fourfold_v1 as fit  # noqa: E402
from task_aware_common import DATA_PATH, DATA_MANIFEST_PATH, SOURCE_LOCK_PATH, sha256  # noqa: E402

MODEL_PT = HERE / "DEPLOYMENT_MODEL_v1.pt"
MODEL_JSON = HERE / "MODEL_MANIFEST_v1.json"
OUT_MAT = HERE / "MATLAB_EVENTWISE_PARITY_INPUTS_v1.mat"
OUT_JSON = HERE / "MATLAB_EVENTWISE_PARITY_INPUTS_v1.json"


def main() -> None:
    if OUT_MAT.exists() or OUT_JSON.exists():
        raise RuntimeError("Refusing to overwrite parity export")
    model_manifest = json.loads(MODEL_JSON.read_text(encoding="utf-8"))
    if sha256(MODEL_PT) != model_manifest["checkpoint_sha256"]:
        raise RuntimeError("Copied DC checkpoint SHA mismatch")
    if sha256(HERE / "DEPLOYMENT_WEIGHTS_v1.npz") != model_manifest["weights_export_npz_sha256"]:
        raise RuntimeError("Copied DC weight export SHA mismatch")
    if sha256(DATA_PATH) != model_manifest["dataset_sha256"]:
        raise RuntimeError("TRAIN24 dataset SHA mismatch")
    with np.load(DATA_PATH, allow_pickle=False) as z:
        ids = z["scene_ids"].astype(str).tolist()
        x = z["x14_model_input"].astype(np.float32)
        ready = z["ready_mask"].astype(bool)
        base = z["applied_acceleration_event_mps2"].astype(np.float32)
        event_t = z["event_time_s"].astype(np.float32)
    if ids != model_manifest["training_scene_ids"] or x.shape != (24, 1999, 14) or base.shape != (24, 1999, 3):
        raise RuntimeError("TRAIN24 shape/order mismatch")
    if not np.array_equal(ready, np.broadcast_to(np.arange(1999) >= 31, (24, 1999))):
        raise RuntimeError("Warmup/ready-event contract changed")
    if not np.all(base[:, :31] == 0) or not np.allclose(event_t[:, 0], .01, atol=2e-6, rtol=0):
        raise RuntimeError("C5 base or first-event timing mismatch")

    checkpoint = torch.load(MODEL_PT, map_location="cpu", weights_only=False)
    if checkpoint["scene_ids"] != ids or checkpoint["dataset_sha256"] != model_manifest["dataset_sha256"]:
        raise RuntimeError("Checkpoint does not bind this exact TRAIN24 set")
    model = fit.ResidualGRU().cpu().eval()
    model.load_state_dict(checkpoint["state_dict"])
    mean = np.asarray(checkpoint["normalizer_mean"], np.float32)
    std = np.asarray(checkpoint["normalizer_std"], np.float32)
    if mean.shape != (14,) or std.shape != (14,) or np.any(std <= 0):
        raise RuntimeError("Invalid X14 normalizer")
    xn = ((x - mean[None, None, :]) / std[None, None, :]).astype(np.float32)
    with torch.no_grad():
        raw, clipped = model(torch.from_numpy(xn))
    raw = raw.numpy().astype(np.float64)
    clipped = clipped.numpy().astype(np.float64)
    clipped[~ready] = 0.0
    beta = np.clip(event_t / 1.8, 0, 1).astype(np.float64)
    action = np.clip(base.astype(np.float64) + beta[..., None] * clipped, -3, 3)
    action[~ready] = 0.0
    if not np.all(clipped[:, :31] == 0) or not np.all(action[:, :31] == 0):
        raise RuntimeError("Warmup outputs must be exactly zero")

    savemat(OUT_MAT, {
        "x14": np.transpose(x, (2, 1, 0)), "ready_mask": ready,
        "event_time_s": event_t, "expected_beta": beta,
        "base_applied_mps2": np.transpose(base, (2, 1, 0)),
        "expected_raw_mps2": np.transpose(raw, (2, 1, 0)),
        "expected_delta_mps2": np.transpose(clipped, (2, 1, 0)),
        "expected_action_mps2": np.transpose(action, (2, 1, 0)),
    }, do_compression=True)
    report = {
        "schema": "POSITION_TEACHER_DC_PENALTY_MATLAB_PARITY_INPUTS_V1",
        "scope": "TRAIN24 causal X14 and C5 applied acceleration only; no VAL/TEST/wind/inertia",
        "model_checkpoint_sha256": sha256(MODEL_PT),
        "weights_mat_sha256": sha256(HERE / "candidate_runner_work/matlab/models/position_balanced_full24.mat"),
        "weights_export_npz_sha256": sha256(HERE / "DEPLOYMENT_WEIGHTS_v1.npz"),
        "dataset_sha256": sha256(DATA_PATH), "scene_ids": ids,
        "event_count_per_scene": 1999, "x14_shape_matlab": [14, 1999, 24],
        "base_applied_shape_matlab": [3, 1999, 24],
        "first_event_time_s": float(event_t[0, 0]), "first_ready_zero_based_index": 31,
        "first_ready_event_time_s": float(event_t[0, 31]),
        "beta_formula": "clip(event_time_s/1.8,0,1)", "delta_clip_mps2": 0.5,
        "total_action_clip_mps2": 3.0, "hidden_reset_each_scene": True,
        "hidden_updates_from_event0_during_warmup": True,
        "warmup_delta_and_action_exactly_zero": True,
    }
    OUT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    report["mat_sha256"] = sha256(OUT_MAT)
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
