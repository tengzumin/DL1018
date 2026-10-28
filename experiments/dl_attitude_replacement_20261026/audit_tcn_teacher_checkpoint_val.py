#!/usr/bin/env python3
"""Read-only CPU audit of a frozen TCN teacher-action checkpoint on VAL48."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True

import numpy as np
import torch


TASK = Path(__file__).resolve().parent
DATASET = TASK / "dataset_v4_teacher_distill" / "attitude_rbf_teacher_train_val_v2.npz"
MANIFEST = DATASET.with_name("DATASET_MANIFEST_v2.json")
RELEASE = TASK / "TRAINING_RELEASE_v3.json"
TRAINER = TASK / "train_tcn_teacher_v2.py"
OUTPUT = TASK / "training_v2_teacher_distill"
PROGRESS = OUTPUT / "training_progress.json"
CHECKPOINT = OUTPUT / "best.pt"
WINDOW = 15


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    release = json.loads(RELEASE.read_text(encoding="utf-8"))
    progress = json.loads(PROGRESS.read_text(encoding="utf-8"))
    assert release["schema"] == "DL1018_CAUSAL_TCN_TRAINING_RELEASE_V3" and release["status"] == "FROZEN"
    assert manifest["status"] == "PASS" and manifest["test_data_read"] is False
    assert manifest["plant_truth_read"] is False and manifest["split_counts"] == {"TRAIN": 768, "VAL": 48}
    assert sha256(DATASET) == manifest["npz_sha256"]
    dataset_key = "experiments/dl_attitude_replacement_20261026/dataset_v4_teacher_distill/attitude_rbf_teacher_train_val_v2.npz"
    assert sha256(DATASET) == release["source_files"][dataset_key]
    trainer_key = "experiments/dl_attitude_replacement_20261026/train_tcn_teacher_v2.py"
    assert sha256(TRAINER) == release["source_files"][trainer_key]
    assert sha256(MANIFEST) == release["source_files"][
        "experiments/dl_attitude_replacement_20261026/dataset_v4_teacher_distill/DATASET_MANIFEST_v2.json"
    ]

    spec = importlib.util.spec_from_file_location("tcn_teacher_architecture", TRAINER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    with np.load(DATASET, allow_pickle=False) as data:
        train_x = np.asarray(data["train_x"], dtype=np.float32)
        train_y = np.asarray(data["train_y"], dtype=np.float32)
        val_x = np.asarray(data["val_x"], dtype=np.float32)
        val_y = np.asarray(data["val_y"], dtype=np.float32)
    assert train_x.shape == (768, 1999, 13) and train_y.shape == (768, 1999, 3)
    assert val_x.shape == (48, 1999, 13) and val_y.shape == (48, 1999, 3)
    assert all(np.isfinite(array).all() for array in (train_x, train_y, val_x, val_y))
    assert progress["seed"] == release["seed"]
    assert progress["dataset_npz_sha256"] == sha256(DATASET)
    assert progress["dataset_manifest_sha256"] == sha256(MANIFEST)

    input_mean = train_x.mean(axis=(0, 1), dtype=np.float64)
    input_std = np.maximum(train_x.std(axis=(0, 1), dtype=np.float64), 1e-6)
    target_rms = np.sqrt(np.mean(train_y.astype(np.float64) ** 2, axis=(0, 1)))
    val_xn = ((val_x - input_mean) / input_std).astype(np.float32)
    val_yn = (val_y / target_rms).astype(np.float32)
    padded = np.pad(val_xn.transpose(0, 2, 1), ((0, 0), (0, 0), (WINDOW - 1, 0)))

    checkpoint_hash_before = sha256(CHECKPOINT)
    checkpoint = torch.load(CHECKPOINT, map_location="cpu", weights_only=True)
    assert int(checkpoint["step"]) == int(progress["best_step"])
    assert abs(float(checkpoint["val_scene_macro_teacher_action_rmse"])
               - float(progress["best_val_scene_macro_teacher_action_rmse"])) < 1e-12
    model = module.CausalTCN().cpu()
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()

    prediction = np.empty_like(val_yn, dtype=np.float64)
    offsets = np.arange(WINDOW, dtype=np.int64)
    with torch.inference_mode():
        for scene in range(val_x.shape[0]):
            for start in range(0, val_x.shape[1], 512):
                stop = min(start + 512, val_x.shape[1])
                steps = np.arange(start, stop, dtype=np.int64)[:, None]
                indices = steps + offsets[None, :]
                # Independent causal window construction: past 14 events plus event k.
                windows = np.take(padded[scene], indices, axis=1).transpose(1, 0, 2).copy()
                batch = torch.from_numpy(windows)
                prediction[scene, start:stop] = model(batch).numpy()

    error_norm = prediction - val_yn.astype(np.float64)
    normalized_scene_macro = float(np.mean(np.sqrt(np.mean(error_norm ** 2, axis=(1, 2)))))
    error_phys = prediction * target_rms - val_y.astype(np.float64)
    axis_scene_macro = np.mean(np.sqrt(np.mean(error_phys ** 2, axis=1)), axis=0)
    axis_pooled = np.sqrt(np.mean(error_phys ** 2, axis=(0, 1)))
    checkpoint_hash_after = sha256(CHECKPOINT)
    assert checkpoint_hash_before == checkpoint_hash_after, "checkpoint changed during read-only audit"
    assert abs(normalized_scene_macro - float(progress["best_val_scene_macro_teacher_action_rmse"])) < 1e-7

    print(json.dumps({
        "status": "PASS_READ_ONLY_VAL48",
        "checkpoint_step": int(checkpoint["step"]),
        "checkpoint_sha256": checkpoint_hash_after,
        "progress_sha256": sha256(PROGRESS),
        "progress_updated_utc": progress["updated_utc"],
        "val_scenes": int(val_y.shape[0]),
        "events_per_scene": int(val_y.shape[1]),
        "normalized_scene_macro_rmse_recomputed": normalized_scene_macro,
        "normalized_rmse_progress": float(progress["best_val_scene_macro_teacher_action_rmse"]),
        "absolute_difference": normalized_scene_macro - float(progress["best_val_scene_macro_teacher_action_rmse"]),
        "target_rms_rad_s2": target_rms.tolist(),
        "val_axis_scene_macro_rmse_rad_s2": axis_scene_macro.tolist(),
        "val_axis_pooled_rmse_rad_s2": axis_pooled.tolist(),
        "test_data_read": False,
        "plant_data_read": False,
        "writes_to_model_or_dataset": False,
    }, indent=2))


if __name__ == "__main__":
    main()
