#!/usr/bin/env python3
"""Export deterministic PyTorch predictions for multi-window MATLAB parity."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

import numpy as np
import torch
from scipy.io import savemat
from torch.nn import functional as F

TASK_ROOT = Path(__file__).resolve().parent
TRAINER = TASK_ROOT / "train_tcn_teacher_v2.py"
DATASET = TASK_ROOT / "dataset_v4_teacher_distill" / "attitude_rbf_teacher_train_val_v2.npz"
MANIFEST = TASK_ROOT / "dataset_v4_teacher_distill" / "DATASET_MANIFEST_v2.json"
TRAINING_DIR = TASK_ROOT / "training_v2_teacher_distill"
OUTPUT_MAT = TRAINING_DIR / "parity_vectors_batch_v3.mat"
OUTPUT_JSON = TRAINING_DIR / "parity_vectors_batch_v3.json"
TIMES = (0, 1, 100, 999, 1998)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: dict[str, Any]) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(path)


def main() -> None:
    progress = json.loads((TRAINING_DIR / "training_progress.json").read_text(encoding="utf-8"))
    config = json.loads((TRAINING_DIR / "training_config.json").read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    release_path = TASK_ROOT / "TRAINING_RELEASE_v3.json"
    release = json.loads(release_path.read_text(encoding="utf-8"))
    model_path = TRAINING_DIR / "best.pt"
    if progress.get("status") != "PASS" or progress.get("completed_steps") != 60000:
        raise RuntimeError("formal teacher training is not complete")
    if config.get("status") != "PASS" or config.get("test_data_read") is not False:
        raise RuntimeError("training config is not a clean PASS")
    if (config.get("training_script_sha256") != sha256(TRAINER)
            or config.get("training_release_sha256") != sha256(release_path)
            or progress.get("dataset_manifest_sha256") != sha256(MANIFEST)):
        raise RuntimeError("training config, live progress, or frozen release identity changed")
    expected_trainer_sha = release.get("source_files", {}).get(
        "experiments/dl_attitude_replacement_20261026/train_tcn_teacher_v2.py")
    if expected_trainer_sha != sha256(TRAINER):
        raise RuntimeError("training script differs from the frozen training release")
    if (manifest.get("status") != "PASS" or manifest.get("test_data_read") is not False
            or manifest.get("plant_truth_read") is not False
            or manifest.get("nominal_inertia_read") is not False
            or manifest.get("split_counts") != {"TRAIN": 768, "VAL": 48}):
        raise RuntimeError("dataset manifest is not a clean, fixed-split PASS")
    if not model_path.is_file() or sha256(DATASET) != manifest.get("npz_sha256"):
        raise RuntimeError("model or frozen training dataset identity check failed")
    if OUTPUT_MAT.exists() or OUTPUT_JSON.exists():
        raise FileExistsError("refusing to overwrite parity batch artifacts")

    spec = importlib.util.spec_from_file_location("tcn_teacher_training_v2", TRAINER)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot import the frozen training implementation")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    with np.load(DATASET, allow_pickle=False) as data:
        train_x = np.asarray(data["train_x"], dtype=np.float32)
        train_y = np.asarray(data["train_y"], dtype=np.float32)
        val_x = np.asarray(data["val_x"], dtype=np.float32)
    mean = train_x.mean(axis=(0, 1), dtype=np.float64)
    std = np.maximum(train_x.std(axis=(0, 1), dtype=np.float64), 1e-6)
    target_rms = np.sqrt(np.mean(train_y.astype(np.float64) ** 2, axis=(0, 1)))
    val_xn = ((val_x - mean) / std).astype(np.float32)

    scene_count = int(val_xn.shape[0])
    if scene_count != 48 or val_xn.shape[1] != 1999 or val_xn.shape[2] != 13:
        raise RuntimeError(f"unexpected VAL feature shape: {val_xn.shape}")
    scene_ids = np.repeat(np.arange(scene_count, dtype=np.int64), len(TIMES))
    times = np.tile(np.asarray(TIMES, dtype=np.int64), scene_count)
    val_pad = F.pad(torch.as_tensor(val_xn).permute(0, 2, 1), (module.WINDOW - 1, 0))
    windows = module.make_windows(
        val_pad,
        torch.as_tensor(scene_ids, dtype=torch.long),
        torch.as_tensor(times, dtype=torch.long),
    )

    model = module.CausalTCN().cpu()
    checkpoint = torch.load(model_path, map_location="cpu", weights_only=True)
    if int(checkpoint.get("step", -1)) != int(config.get("best_step", -2)):
        raise RuntimeError("best checkpoint step differs from the frozen training config")
    model.load_state_dict(checkpoint["state_dict"], strict=True)
    model.eval()
    val_scene_rows = [row for row in manifest["rows"] if row["split"] == "VAL"]
    if len(val_scene_rows) != 48:
        raise RuntimeError("dataset manifest VAL scene list is not exactly 48")
    sequence_index = next((i for i, row in enumerate(val_scene_rows)
                           if any(abs(value) > 1e-9 for value in
                                  row["feature_min"][9:13] + row["feature_max"][9:13])), None)
    if sequence_index is None:
        raise RuntimeError("no VAL sequence has nonzero morphology command features")
    sequence_times = torch.arange(val_xn.shape[1], dtype=torch.long)
    sequence_scenes = torch.full((val_xn.shape[1],), sequence_index, dtype=torch.long)
    sequence_windows = module.make_windows(val_pad, sequence_scenes, sequence_times)
    with torch.inference_mode():
        prediction = model(windows).numpy().astype(np.float64) * target_rms[None, :]
        sequence_prediction = model(sequence_windows).numpy().astype(np.float64) * target_rms[None, :]
    inputs = windows.numpy().astype(np.float64).transpose(1, 2, 0)
    expected = prediction.T
    sequence_features_raw = val_x[sequence_index].astype(np.float64).T
    sequence_expected = sequence_prediction.T
    if inputs.shape != (13, 15, scene_count * len(TIMES)) or expected.shape != (3, inputs.shape[2]):
        raise RuntimeError(f"unexpected parity tensor shapes: {inputs.shape}, {expected.shape}")
    if sequence_features_raw.shape != (13, 1999) or sequence_expected.shape != (3, 1999):
        raise RuntimeError(f"unexpected sequential parity shapes: {sequence_features_raw.shape}, {sequence_expected.shape}")
    if not all(np.isfinite(array).all() for array in (inputs, expected, sequence_features_raw, sequence_expected)):
        raise RuntimeError("non-finite parity vectors generated")


    savemat(OUTPUT_MAT, {
        "input_normalized": inputs,
        "expected_teacher_rbf_output_rad_s2": expected,
        "sequence_feature_raw": sequence_features_raw,
        "sequence_expected_rad_s2": sequence_expected,
    }, do_compression=True)
    report = {
        "schema": "DL1018_CAUSAL_TCN_PARITY_BATCH_V3",
        "status": "PASS",
        "sample_count": int(inputs.shape[2]),
        "scene_count": scene_count,
        "sequence_step_count": int(sequence_features_raw.shape[1]),
        "sequence_scene_id": val_scene_rows[sequence_index]["scene_id"],
        "times_event_index": list(TIMES),
        "selection": "all 48 B VAL scenes x event indices [0,1,100,999,1998]",
        "training_split_only": True,
        "test_data_read": False,
        "plant_called": False,
        "dataset_manifest_sha256": sha256(MANIFEST),
        "dataset_npz_sha256": sha256(DATASET),
        "model_sha256": sha256(model_path),
        "training_script_sha256": sha256(TRAINER),
        "exporter_sha256": sha256(Path(__file__).resolve()),
        "mat_path": OUTPUT_MAT.as_posix(),
        "mat_sha256": sha256(OUTPUT_MAT),
    }
    write_json(OUTPUT_JSON, report)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()




