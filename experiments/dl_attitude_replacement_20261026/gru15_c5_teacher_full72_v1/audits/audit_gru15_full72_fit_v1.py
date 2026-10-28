#!/usr/bin/env python3
"""Read-only in-sample fit audit for the frozen GRU15 C5 teacher model."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import torch
from torch.nn import functional as F

TASK_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = TASK_ROOT.parents[2]
DATA_ROOT = PROJECT_ROOT / "experiments/dl_attitude_replacement_20261026/mlp15_c5_teacher_redistill_v1"
DATA_PATH = DATA_ROOT / "matched_teacher_data_v1.npz"
MANIFEST_PATH = DATA_ROOT / "DATASET_MANIFEST_v1.json"
RUN_DIR = TASK_ROOT / "runs/C5_GRU15_FULL72_SEED2026102001"
CHECKPOINT_PATH = RUN_DIR / "final_step_60000.pt"
MODEL_PATH = RUN_DIR / "gru15_attitude_weights_v1.mat"
SCREEN_ROOT = PROJECT_ROOT / "experiments/dl_attitude_replacement_20261026/architecture_screen_v1"
OUT_PATH = Path(__file__).with_name("GRU15_FULL72_TRAINING_FIT_AUDIT_v1.json")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    sys.path.insert(0, str(SCREEN_ROOT))
    from screen_attitude_architectures_v1 import GRU15, make_windows

    config = json.loads((RUN_DIR / "training_config.json").read_text(encoding="utf-8"))
    receipt = json.loads((RUN_DIR / "run_receipt.json").read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if (config.get("status") != "PASS" or receipt.get("status") != "PASS"
            or config.get("plant_called") is not False or config.get("TEST48_read") is not False
            or receipt.get("TEST48_read") is not False or manifest.get("TEST_accessed") is not False
            or manifest.get("plant_truth_read") is not False
            or sha256(DATA_PATH) != config["dataset_identity"]["dataset_sha256"]
            or sha256(MODEL_PATH) != config["weights_sha256"]
            or sha256(CHECKPOINT_PATH) != config["checkpoint_sha256"]):
        raise ValueError("locked GRU15 training/data/model identity or no-Plant contract failed")

    with np.load(DATA_PATH, allow_pickle=False) as archive:
        x_train = np.asarray(archive["c5_train_x"], dtype=np.float32)
        y_train = np.asarray(archive["c5_train_y"], dtype=np.float32)
        x_dev = np.asarray(archive["c5_val_x"], dtype=np.float32)
        y_dev = np.asarray(archive["c5_val_y"], dtype=np.float32)
    x = np.concatenate((x_train, x_dev), axis=0)
    y = np.concatenate((y_train, y_dev), axis=0)
    if x.shape != (72, 1999, 13) or y.shape != (72, 1999, 3):
        raise ValueError("unexpected C5-only development dataset shapes")

    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    checkpoint = torch.load(CHECKPOINT_PATH, map_location="cpu", weights_only=False)
    model = GRU15().to(device)
    model.load_state_dict(checkpoint["state_dict"], strict=True)
    model.eval()
    mean = np.asarray(checkpoint["input_mean"], dtype=np.float32).reshape(1, 1, 13)
    std = np.asarray(checkpoint["input_std"], dtype=np.float32).reshape(1, 1, 13)
    target_rms = np.asarray(checkpoint["target_rms"], dtype=np.float64).reshape(3)
    x_norm = ((x - mean) / std).astype(np.float32)
    padded = F.pad(torch.as_tensor(x_norm, device=device).permute(0, 2, 1), (14, 0))

    def score(first: int, last: int, targets: np.ndarray) -> dict[str, object]:
        scene_count, event_count, _ = targets.shape
        prediction = np.empty_like(targets, dtype=np.float32)
        flat_count = scene_count * event_count
        with torch.inference_mode():
            for start in range(0, flat_count, 512):
                stop = min(start + 512, flat_count)
                flat = torch.arange(start, stop, device=device)
                scenes = torch.div(flat, event_count, rounding_mode="floor") + first
                steps = torch.remainder(flat, event_count)
                windows = make_windows(padded, scenes, steps)
                prediction.reshape(-1, 3)[start:stop] = model(windows).cpu().numpy()
        error = prediction.astype(np.float64) * target_rms - targets.astype(np.float64)
        axis_rmse = np.sqrt(np.mean(error * error, axis=(0, 1)))
        axis_target_rms = np.sqrt(np.mean(targets.astype(np.float64) ** 2, axis=(0, 1)))
        return {
            "scene_count": scene_count,
            "event_count": flat_count,
            "axis_rmse_rad_s2": axis_rmse.tolist(),
            "axis_target_rms_rad_s2": axis_target_rms.tolist(),
            "axis_normalized_rmse": (axis_rmse / np.maximum(axis_target_rms, 1e-12)).tolist(),
        }

    result = {
        "schema": "DL1018_GRU15_FULL72_TRAINING_FIT_AUDIT_V1",
        "status": "PASS_IN_SAMPLE_INFERENCE",
        "plant_invoked": False,
        "test_data_read": False,
        "in_sample_only": True,
        "device": str(device),
        "optimizer_steps": receipt["optimizer_steps"],
        "dataset_sha256": sha256(DATA_PATH),
        "model_sha256": sha256(MODEL_PATH),
        "train_c5_24": score(0, 24, y[:24]),
        "c5_val48_reclassified_as_dev_train": score(24, 72, y[24:]),
        "all72_development_scenes": score(0, 72, y),
    }
    OUT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "device": result["device"],
                      "all72": result["all72_development_scenes"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
