#!/usr/bin/env python3
"""Compare frozen full72 and GHP7-balanced MLP15 on G3 C5 teacher states."""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch.nn import functional as F

TASK_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = TASK_ROOT.parents[2]
RESEARCH_ROOT = PROJECT_ROOT / "experiments/dl_attitude_replacement_20261026"
BASE_TASK = RESEARCH_ROOT / "mlp15_c5_teacher_full72_v1"
BASE_RUN = BASE_TASK / "runs/C5_MLP15_FULL72_SEED2026102001"
NEW_RUN = TASK_ROOT / "runs/C5_MLP15_GHP7_BALANCE_SEED2026102001"
SCREEN_ROOT = RESEARCH_ROOT / "architecture_screen_v1"
DATA_DIR = TASK_ROOT / "data"
HOLDOUT_PATH = DATA_DIR / "ghp7_g3_dev_holdout_v1.npz"
DATA_MANIFEST_PATH = DATA_DIR / "GHP7_TEACHER_DATA_MANIFEST_v1.json"
OUT_PATH = TASK_ROOT / "GHP7_BALANCED_MLP15_G3_OFFLINE_AUDIT_v1.json"
D_MAX = np.asarray([45.0, 45.0, 4.7124], dtype=np.float64)
EXPECTED_IDS = ["DL1018_GHP7_G3_W00", "DL1018_GHP7_G3_W12"]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_model_helpers():
    sys.path.insert(0, str(SCREEN_ROOT))
    from screen_attitude_architectures_v1 import MLP15, make_windows
    return MLP15, make_windows


def load_checkpoint(path: Path, MLP15):
    checkpoint = torch.load(path, map_location="cpu", weights_only=False)
    model = MLP15().cpu()
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    mean = checkpoint["input_mean"].cpu().numpy().astype(np.float64)
    std = checkpoint["input_std"].cpu().numpy().astype(np.float64)
    target_rms = checkpoint["target_rms"].cpu().numpy().astype(np.float64)
    if mean.shape != (13,) or std.shape != (13,) or target_rms.shape != (3,):
        raise ValueError(f"invalid MLP normalizer shapes: {path}")
    return model, mean, std, target_rms


def predict(model, x: np.ndarray, mean: np.ndarray, std: np.ndarray,
            target_rms: np.ndarray, make_windows) -> tuple[np.ndarray, np.ndarray]:
    x_norm = ((x.astype(np.float64) - mean) / std).astype(np.float32)
    padded = F.pad(torch.as_tensor(x_norm).permute(0, 2, 1), (14, 0))
    scene_count, event_count = x.shape[:2]
    scene_index = torch.arange(scene_count).repeat_interleave(event_count)
    event_index = torch.arange(event_count).repeat(scene_count)
    windows = make_windows(padded, scene_index, event_index)
    predictions = []
    with torch.inference_mode():
        for start in range(0, windows.shape[0], 2048):
            predictions.append(model(windows[start:start + 2048]).numpy())
    raw = np.concatenate(predictions).reshape(scene_count, event_count, 3).astype(np.float64)
    unbounded = raw * target_rms
    clipped = np.clip(unbounded, -D_MAX, D_MAX)
    clip_counts = np.count_nonzero(np.abs(unbounded) > D_MAX, axis=(0, 1))
    return clipped, clip_counts


def metrics(prediction: np.ndarray, target: np.ndarray, ids: list[str],
            teacher_rms: np.ndarray) -> dict[str, Any]:
    difference = prediction - target
    axis_rmse = np.sqrt(np.mean(difference ** 2, axis=(0, 1)))
    normalized_axis = axis_rmse / np.maximum(teacher_rms, 1e-12)
    scene_vector_rmse = np.sqrt(np.mean(np.sum(difference ** 2, axis=2), axis=1))
    return {
        "axis_rmse_rad_s2": axis_rmse.tolist(),
        "axis_normalized_rmse": normalized_axis.tolist(),
        "pooled_normalized_rmse": float(np.sqrt(np.mean(normalized_axis ** 2))),
        "pooled_vector_rmse_rad_s2": float(np.sqrt(np.mean(np.sum(difference ** 2, axis=2)))),
        "per_scene_vector_rmse_rad_s2": {
            scene_id: float(value) for scene_id, value in zip(ids, scene_vector_rmse)
        },
    }


def main() -> None:
    if OUT_PATH.exists():
        raise FileExistsError(f"refusing to overwrite offline audit: {OUT_PATH}")
    manifest = json.loads(DATA_MANIFEST_PATH.read_text(encoding="utf-8"))
    if (manifest.get("status") != "PASS_OFFLINE_EXTRACTION"
            or manifest.get("holdout_scene_ids") != EXPECTED_IDS
            or manifest.get("TEST48_read") is not False
            or manifest.get("plant_called") is not False):
        raise ValueError("GHP7 development holdout manifest failed identity/seal checks")
    if sha256_file(HOLDOUT_PATH) != manifest["holdout_bundle"]["sha256"]:
        raise ValueError("GHP7 holdout bundle SHA mismatch")
    baseline_receipt = json.loads((BASE_RUN / "run_receipt.json").read_text(encoding="utf-8"))
    new_receipt = json.loads((NEW_RUN / "run_receipt.json").read_text(encoding="utf-8"))
    if (baseline_receipt.get("status") != "PASS" or baseline_receipt.get("optimizer_steps") != 60_000
            or new_receipt.get("status") != "PASS" or new_receipt.get("optimizer_steps") != 60_000
            or new_receipt.get("ghp7_holdout_opened") is not False):
        raise ValueError("MLP training receipts are incomplete or indicate holdout leakage")
    with np.load(HOLDOUT_PATH, allow_pickle=False) as archive:
        x = np.asarray(archive["x"], dtype=np.float32)
        y = np.asarray(archive["y"], dtype=np.float64)
        ids = np.asarray(archive["scene_ids"]).astype(str).tolist()
    if ids != EXPECTED_IDS or x.shape != (2, 1999, 13) or y.shape != (2, 1999, 3):
        raise ValueError("G3 holdout array shape or order mismatch")
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError("non-finite G3 holdout data")

    MLP15, make_windows = load_model_helpers()
    baseline, base_mean, base_std, base_target_rms = load_checkpoint(BASE_RUN / "final_step_60000.pt", MLP15)
    candidate, new_mean, new_std, new_target_rms = load_checkpoint(NEW_RUN / "final_step_60000.pt", MLP15)
    base_pred, base_clips = predict(baseline, x, base_mean, base_std, base_target_rms, make_windows)
    new_pred, new_clips = predict(candidate, x, new_mean, new_std, new_target_rms, make_windows)
    teacher_rms = np.sqrt(np.mean(y ** 2, axis=(0, 1)))
    base_metrics = metrics(base_pred, y, ids, teacher_rms)
    new_metrics = metrics(new_pred, y, ids, teacher_rms)
    reduction = 1.0 - new_metrics["pooled_normalized_rmse"] / max(base_metrics["pooled_normalized_rmse"], 1e-12)
    per_scene_ratio = {
        scene_id: new_metrics["per_scene_vector_rmse_rad_s2"][scene_id]
        / max(base_metrics["per_scene_vector_rmse_rad_s2"][scene_id], 1e-12)
        for scene_id in ids
    }
    gate_pass = reduction >= 0.10 and all(ratio <= 1.05 for ratio in per_scene_ratio.values())
    report = {
        "schema": "DL1018_MLP15_C5_GHP7_G3_OFFLINE_AUDIT_V1",
        "status": "PASS_OFFLINE_FIT_GATE" if gate_pass else "FAIL_OFFLINE_FIT_GATE",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "plant_called": False, "TEST48_read": False,
        "interpretation": "development diagnostic only; G3 was excluded from this training job but was previously used in candidate screening",
        "teacher_contract": "C5 logged rbf_output_raw at attitude event k; post-dmax/pre-beta; rad/s^2",
        "feature_contract": manifest["feature_order"],
        "dmax_rad_s2": D_MAX.tolist(), "holdout_scene_ids": ids,
        "holdout_bundle_sha256": sha256_file(HOLDOUT_PATH),
        "baseline_model_sha256": sha256_file(BASE_RUN / "mlp15_attitude_weights_v1.mat"),
        "candidate_model_sha256": sha256_file(NEW_RUN / "mlp15_attitude_weights_v1.mat"),
        "teacher_rms_rad_s2": teacher_rms.tolist(),
        "baseline_full72": {**base_metrics, "runtime_clip_count_by_axis": base_clips.tolist()},
        "candidate_ghp7_balanced": {**new_metrics, "runtime_clip_count_by_axis": new_clips.tolist()},
        "pooled_normalized_rmse_reduction_fraction": float(reduction),
        "per_scene_vector_rmse_candidate_to_baseline_ratio": per_scene_ratio,
        "predeclared_gate": {
            "pooled_normalized_rmse_reduction_at_least": 0.10,
            "per_scene_vector_rmse_ratio_at_most": 1.05,
            "passed": gate_pass,
        },
        "training_holdout_access_claim": {
            "candidate_training_receipt_ghp7_holdout_opened": new_receipt.get("ghp7_holdout_opened"),
            "candidate_training_receipt_test48_read": new_receipt.get("TEST48_read"),
        },
    }
    OUT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "reduction_fraction": reduction,
                      "per_scene_ratio": per_scene_ratio, "plant_called": False,
                      "TEST48_read": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
