#!/usr/bin/env python3
"""Independent CPU audit of the frozen MLP15 checkpoint and MATLAB export."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import torch
from scipy.io import loadmat
from torch.nn import functional as F


ROOT = Path(__file__).resolve().parent
TASK = ROOT.parent
DATASET = TASK / "dataset_v4_teacher_distill" / "attitude_rbf_teacher_train_val_v2.npz"
MANIFEST = DATASET.with_name("DATASET_MANIFEST_v2.json")
OUT = ROOT / "run_v1"
PROGRESS = OUT / "training_progress.json"
CONFIG = OUT / "training_config.json"
CHECKPOINT = OUT / "best.pt"
WEIGHTS = OUT / "mlp15_attitude_weights_v1.mat"
PARITY = OUT / "parity_vector_v1.mat"
AUDIT = OUT / "MLP15_CHECKPOINT_AUDIT_v1.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    progress = json.loads(PROGRESS.read_text(encoding="utf-8"))
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert progress["status"] == "PASS" and progress["completed_steps"] == 60000
    assert progress["plant_called"] is False and progress["test_data_read"] is False
    assert config["status"] == "PASS" and config["best_step"] == progress["best_step"]
    assert manifest["status"] == "PASS" and manifest["test_data_read"] is False
    dataset_hash = sha256(DATASET)
    assert dataset_hash == config["dataset_sha256"] == progress["dataset_sha256"]

    with np.load(DATASET, allow_pickle=False) as data:
        train_x = np.asarray(data["train_x"], dtype=np.float32)
        train_y = np.asarray(data["train_y"], dtype=np.float32)
        val_x = np.asarray(data["val_x"], dtype=np.float32)
        val_y = np.asarray(data["val_y"], dtype=np.float32)
    assert train_x.shape == (768, 1999, 13) and train_y.shape == (768, 1999, 3)
    assert val_x.shape == (48, 1999, 13) and val_y.shape == (48, 1999, 3)
    assert all(np.isfinite(x).all() for x in (train_x, train_y, val_x, val_y))

    mean = train_x.mean(axis=(0, 1), dtype=np.float64)
    std = np.maximum(train_x.std(axis=(0, 1), dtype=np.float64), 1e-6)
    target_rms = np.sqrt(np.mean(train_y.astype(np.float64) ** 2, axis=(0, 1)))
    val_norm = ((val_x - mean) / std).astype(np.float32)
    # Rebuild causal windows directly, including zero-left-padding at each scene start.
    padded = np.pad(val_norm.transpose(0, 2, 1), ((0, 0), (0, 0), (14, 0)))
    windows = np.stack([
        np.stack([padded[s, :, k:k + 15].T for k in range(1999)])
        for s in range(48)
    ])

    checkpoint_hash_before = sha256(CHECKPOINT)
    checkpoint = torch.load(CHECKPOINT, map_location="cpu", weights_only=True)
    assert checkpoint["step"] == config["best_step"]
    assert checkpoint["dataset_sha256"] == dataset_hash
    state = checkpoint["state_dict"]
    mat = loadmat(WEIGHTS)
    mapping = {
        "net.0.weight": "fc1_weight", "net.0.bias": "fc1_bias",
        "net.2.weight": "fc2_weight", "net.2.bias": "fc2_bias",
        "net.4.weight": "head_weight", "net.4.bias": "head_bias",
    }
    for key, mat_key in mapping.items():
        assert np.array_equal(state[key].cpu().numpy(), np.asarray(mat[mat_key]).squeeze()), mat_key
    assert np.allclose(mat["input_mean"].reshape(-1), mean, rtol=0, atol=1e-12)
    assert np.allclose(mat["input_std"].reshape(-1), std, rtol=0, atol=1e-12)
    assert np.allclose(mat["target_rms"].reshape(-1), target_rms, rtol=0, atol=1e-12)

    # Independently evaluate checkpoint weights in bounded batches on CPU.
    prediction = np.empty((48, 1999, 3), dtype=np.float64)
    flat_windows = windows.reshape(-1, 195)
    with torch.inference_mode():
        for start in range(0, len(flat_windows), 4096):
            x = torch.from_numpy(flat_windows[start:start + 4096].copy())
            z = F.silu(F.linear(x, state["net.0.weight"], state["net.0.bias"]))
            z = F.silu(F.linear(z, state["net.2.weight"], state["net.2.bias"]))
            y = F.linear(z, state["net.4.weight"], state["net.4.bias"])
            stop = min(start + len(y), prediction.size // 3)
            prediction.reshape(-1, 3)[start:stop] = y[:stop - start].numpy()
    error = prediction - val_y.astype(np.float64) / target_rms
    recomputed = float(np.mean(np.sqrt(np.mean(error ** 2, axis=(1, 2)))))
    assert abs(recomputed - progress["best_val_scene_macro_teacher_action_rmse"]) < 1e-7

    # Recompute the exported single-vector result from its raw causal window.
    vector = loadmat(PARITY)
    raw_window = np.asarray(vector["input_raw_window"], dtype=np.float64)
    normalized_window = ((raw_window - mean) / std).astype(np.float32).astype(np.float64)
    assert raw_window.shape == (15, 13)
    assert np.allclose(normalized_window, vector["input_normalized_window"], rtol=0, atol=1e-12)
    flat = torch.from_numpy(normalized_window.reshape(1, 195).astype(np.float32))
    with torch.inference_mode():
        z = F.silu(F.linear(flat, state["net.0.weight"], state["net.0.bias"]))
        z = F.silu(F.linear(z, state["net.2.weight"], state["net.2.bias"]))
        parity_action = F.linear(z, state["net.4.weight"], state["net.4.bias"]).numpy().reshape(-1) * target_rms
    parity_error = float(np.max(np.abs(parity_action - vector["expected_teacher_action_rad_s2"].reshape(-1))))
    assert parity_error < 1e-5
    assert checkpoint_hash_before == sha256(CHECKPOINT), "checkpoint changed during audit"

    report = {
        "schema": "DL1018_MLP15_CHECKPOINT_AUDIT_V1",
        "status": "PASS_READ_ONLY_VAL48_AND_EXPORT",
        "best_step": int(checkpoint["step"]),
        "checkpoint_sha256": checkpoint_hash_before,
        "weights_sha256": sha256(WEIGHTS),
        "dataset_sha256": dataset_hash,
        "val_scenes": 48,
        "events_per_scene": 1999,
        "normalized_scene_macro_teacher_action_rmse": recomputed,
        "progress_metric": float(progress["best_val_scene_macro_teacher_action_rmse"]),
        "parity_vector_max_abs_error_rad_s2": parity_error,
        "plant_called": False,
        "test_data_read": False,
        "historical_results_modified": False,
    }
    AUDIT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
