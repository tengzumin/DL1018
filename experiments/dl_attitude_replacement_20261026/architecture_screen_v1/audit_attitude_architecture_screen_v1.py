#!/usr/bin/env python3
"""Independently recompute the frozen four-family screen from its checkpoints."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import torch


SCREEN_ROOT = Path(__file__).resolve().parent
TASK_ROOT = SCREEN_ROOT.parent
RUNS = SCREEN_ROOT / "runs_v1"
DATASET = TASK_ROOT / "dataset_v4_teacher_distill" / "attitude_rbf_teacher_train_val_v2.npz"
MANIFEST = TASK_ROOT / "dataset_v4_teacher_distill" / "DATASET_MANIFEST_v2.json"
SOURCE = SCREEN_ROOT / "screen_attitude_architectures_v1.py"
FAMILIES = ("MLP15", "GRU15", "DSSM15", "TCN15")
WINDOW = 15
INPUT_DIM = 13
BATCH = 4096


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: dict[str, Any]) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(path)


def main() -> None:
    sys.path.insert(0, str(SCREEN_ROOT))
    spec = importlib.util.spec_from_file_location("screen_models", SOURCE)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load frozen architecture definitions")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    summary = json.loads((RUNS / "screen_results.json").read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if (
        summary.get("status") != "PASS_OFFLINE_SCREEN_ONLY"
        or summary.get("test_data_read") is not False
        or summary.get("plant_called") is not False
        or manifest.get("test_data_read") is not False
        or manifest.get("plant_truth_read") is not False
        or manifest.get("nominal_inertia_read") is not False
        or sha256(DATASET) != summary.get("dataset_sha256")
    ):
        raise ValueError("screen/result/data contract mismatch")
    with np.load(DATASET, allow_pickle=False) as data:
        val_x = np.asarray(data["val_x"], dtype=np.float32)
        val_y = np.asarray(data["val_y"], dtype=np.float32)
    assert val_x.shape == (48, 1999, INPUT_DIM) and val_y.shape == (48, 1999, 3)
    assert np.isfinite(val_x).all() and np.isfinite(val_y).all()
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    verified = []

    for family in FAMILIES:
        candidate = RUNS / family
        metrics = json.loads((candidate / "metrics.json").read_text(encoding="utf-8"))
        checkpoint_path = candidate / "step_02000.pt"
        checkpoint_hash_before = sha256(checkpoint_path)
        if checkpoint_hash_before != metrics.get("checkpoint_sha256"):
            raise ValueError(f"{family}: checkpoint hash differs from metrics")
        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
        model = module.build_model(family).to(device)
        model.load_state_dict(checkpoint["state_dict"])
        model.eval()
        mean = np.asarray(checkpoint["input_mean"], dtype=np.float64)
        std = np.asarray(checkpoint["input_std"], dtype=np.float64)
        target_rms = np.asarray(checkpoint["target_rms"], dtype=np.float64)
        val_norm = ((val_x - mean) / std).astype(np.float32)
        padded = np.pad(
            val_norm.transpose(0, 2, 1),
            ((0, 0), (0, 0), (WINDOW - 1, 0)),
        )
        prediction = np.empty(val_y.shape, dtype=np.float64)
        total = val_y.shape[0] * val_y.shape[1]
        offsets = np.arange(WINDOW, dtype=np.int64)
        with torch.inference_mode():
            for start in range(0, total, BATCH):
                stop = min(start + BATCH, total)
                flat = np.arange(start, stop, dtype=np.int64)
                scenes, times = np.divmod(flat, val_y.shape[1])
                source = padded[scenes]
                index = np.broadcast_to(
                    (times[:, None] + offsets[None, :])[:, None, :],
                    (stop - start, INPUT_DIM, WINDOW),
                )
                windows = np.take_along_axis(source, index, axis=2).transpose(0, 2, 1).copy()
                batch = torch.from_numpy(windows).to(device)
                prediction.reshape(-1, 3)[start:stop] = model(batch).cpu().numpy()

        error_norm = prediction - val_y.astype(np.float64) / target_rms
        recomputed = float(np.mean(np.sqrt(np.mean(error_norm ** 2, axis=(1, 2)))))
        error_phys = error_norm * target_rms
        axis_macro = np.mean(np.sqrt(np.mean(error_phys ** 2, axis=1)), axis=0)
        difference = recomputed - float(metrics["normalized_scene_macro_teacher_action_rmse"])
        checkpoint_hash_after = sha256(checkpoint_path)
        if abs(difference) > 2e-6 or checkpoint_hash_after != checkpoint_hash_before:
            raise ValueError(f"{family}: independent metric/hash check failed ({difference})")
        verified.append({
            "architecture": family,
            "screen_metric": float(metrics["normalized_scene_macro_teacher_action_rmse"]),
            "independent_metric": recomputed,
            "absolute_difference": abs(difference),
            "independent_axis_scene_macro_rmse_rad_s2": axis_macro.tolist(),
            "checkpoint_sha256": checkpoint_hash_after,
            "training_seconds": float(metrics["training_seconds"]),
            "full_val_seconds": float(metrics["full_val_seconds"]),
            "parameter_count": int(metrics["parameter_count"]),
        })
        del model
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    ranking = [
        row["architecture"]
        for row in sorted(verified, key=lambda row: (
            row["independent_metric"], row["training_seconds"], row["architecture"]
        ))
    ]
    if ranking != summary.get("architecture_ranking"):
        raise ValueError("independent ranking differs from frozen summary")
    report = {
        "schema": "DL1018_ATTITUDE_ARCHITECTURE_SCREEN_AUDIT_V1",
        "status": "PASS_INDEPENDENT_VAL48_RECOMPUTE",
        "ranking": ranking,
        "records": verified,
        "screen_summary_sha256": sha256(RUNS / "screen_results.json"),
        "screen_script_sha256": sha256(SOURCE),
        "audit_script_sha256": sha256(Path(__file__).resolve()),
        "test_data_read": False,
        "plant_called": False,
        "runtime_inertia_reconstruction_used": False,
    }
    out = SCREEN_ROOT / "SCREEN_AUDIT_v1.json"
    if out.exists():
        raise FileExistsError(f"refusing to overwrite {out}")
    write_json(out, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
