#!/usr/bin/env python3
"""Compare three frozen MLP15 models on the same C5 VAL48 states and actions."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

import numpy as np
import torch
from scipy.io import loadmat
from torch.nn import functional as F

ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = Path(__file__).resolve().parents[4]
ISOLATION_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ISOLATION_ROOT / "runs"
SCREEN_ROOT = ROOT / "architecture_screen_v1"
INPUT_DIM, WINDOW, EVENT_COUNT = 13, 15, 1999
FEATURE_ORDER = [
    "wrapped_attitude_error_euler_rad_x3", "body_rate_rad_s_x3",
    "nominal_bs_body_torque_Nm_x3", "morph_command_x4",
]
FEATURE_ERROR_CONTRACT = {
    "feature": "wrapped_attitude_error_euler_rad_x3",
    "formula": "atan2(sin(filtered_attitude_reference - state_euler), cos(filtered_attitude_reference - state_euler))",
    "reference_source": "experiments/dl_attitude_replacement_20261026/prepare_tcn_teacher_dataset_v2.py::load_scene",
    "new_builder_formula_matches_reference": True,
}
TARGET_CONTRACT = "logged rbf_output_raw at attitude event k; post-dmax/pre-beta; rad/s^2"
D_MAX = np.asarray([45.0, 45.0, 4.7124], dtype=np.float64)
TEST_TOKEN = re.compile(r"test", re.IGNORECASE)
MODEL_KEYS = ("input_mean", "input_std", "target_rms", "fc1_weight", "fc1_bias",
              "fc2_weight", "fc2_bias", "head_weight", "head_bias")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def reject_test_path(path: Path, label: str) -> None:
    if TEST_TOKEN.search(str(path)):
        raise ValueError(f"{label} path contains TEST: {path}")


def load_model_helpers():
    sys.path.insert(0, str(SCREEN_ROOT))
    from screen_attitude_architectures_v1 import MLP15, make_windows
    return MLP15, make_windows


def _assert_ordered_scene_ids(actual: np.ndarray | list[str], expected: list[str], label: str) -> None:
    actual_array = np.asarray(actual)
    if actual_array.ndim != 1 or actual_array.tolist() != expected:
        raise ValueError(f"{label} scene IDs do not match manifest order")


def load_val(path: Path, manifest_path: Path) -> tuple[np.ndarray, np.ndarray, list[str], dict[str, Any]]:
    reject_test_path(path, "VAL dataset")
    reject_test_path(manifest_path, "VAL manifest")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (manifest.get("schema") != "DL1018_MLP15_MATCHED_B24_C5_24_C5_VAL48_DATASET_V1"
            or manifest.get("status") != "PASS_OFFLINE_EXTRACTION"):
        raise ValueError("comparison requires the frozen matched-builder manifest")
    if manifest.get("target") != TARGET_CONTRACT:
        raise ValueError("VAL labels must be C5_RBF post-dmax/pre-beta rad/s^2")
    if manifest.get("TEST_accessed") is not False:
        raise ValueError("manifest indicates prohibited TEST access")
    if manifest.get("plant_truth_read") is not False:
        raise ValueError("manifest must explicitly state plant_truth_read=false")
    if manifest.get("feature_order") != FEATURE_ORDER:
        raise ValueError("VAL feature/time contract mismatch")
    scene_rows = [r for r in manifest.get("rows", []) if r.get("split") == "C5_VAL48"]
    scene_ids = [r.get("scene_id") for r in scene_rows]
    if len(scene_ids) != 48 or len(set(scene_ids)) != 48 or any(r.get("teacher_source") != "C5_RBF" for r in scene_rows):
        raise ValueError("manifest must contain 48 unique C5_RBF VAL scene rows")
    if any(not isinstance(s, str) or not s.startswith("DL1018_VAL_") or "TEST" in s.upper() for s in scene_ids):
        raise ValueError("non-VAL scene ID in comparison set")
    declared_hash = manifest.get("dataset_sha256")
    if not declared_hash or declared_hash != sha256(path):
        raise ValueError("VAL data SHA does not match manifest")
    if (PROJECT_ROOT / manifest.get("dataset_path", "")).resolve() != path.resolve():
        raise ValueError("dataset path differs from manifest identity")
    with np.load(path, allow_pickle=False) as data:
        if any(name.lower().startswith("test") for name in data.files):
            raise ValueError("NPZ contains TEST arrays")
        required = {"c5_val_x", "c5_val_y", "c5_val_scene_ids"}
        if not required.issubset(data.files):
            raise ValueError(f"combined builder NPZ lacks arrays: {sorted(required - set(data.files))}")
        x = np.asarray(data["c5_val_x"], dtype=np.float32)
        y = np.asarray(data["c5_val_y"], dtype=np.float32)
        npz_scene_ids = np.asarray(data["c5_val_scene_ids"])
    _assert_ordered_scene_ids(npz_scene_ids, scene_ids, "c5_val_npz")
    if x.shape != (48, EVENT_COUNT, INPUT_DIM) or y.shape != (48, EVENT_COUNT, 3):
        raise ValueError(f"unexpected VAL shapes: features={x.shape}, targets={y.shape}")
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError("VAL data finite-value check failed")
    if any(r.get("event_count") != EVENT_COUNT or r.get("feature_shape") != [EVENT_COUNT, INPUT_DIM]
           or r.get("target_shape") != [EVENT_COUNT, 3] for r in scene_rows):
        raise ValueError("VAL per-scene shape/event contract mismatch")
    return x, y, scene_ids, manifest


def load_model(path: Path, label: str, expected_arm: str | None = None,
               config_path: Path | None = None):
    reject_test_path(path, f"{label} model")
    if not path.is_file():
        raise FileNotFoundError(path)
    config = None
    if config_path is None:
        auto = path.parent / "training_config.json"
        config_path = auto if auto.is_file() else None
    if config_path is not None:
        reject_test_path(config_path, f"{label} training config")
        config = json.loads(config_path.read_text(encoding="utf-8"))
        if config.get("status") != "PASS" or config.get("test_data_read") is not False:
            raise ValueError(f"{label} config is not an audited TEST-free model")
        if expected_arm is not None and config.get("arm") != expected_arm:
            raise ValueError(f"{label} config arm must be {expected_arm}")
        if config.get("architecture") not in (None, "MLP15"):
            raise ValueError(f"{label} is not MLP15")
    mat = loadmat(path)
    missing = [k for k in MODEL_KEYS if k not in mat]
    if missing:
        raise ValueError(f"{label} model missing MAT fields: {missing}")
    values = {k: np.asarray(mat[k], dtype=np.float64) for k in MODEL_KEYS}
    for k in ("input_mean", "input_std", "target_rms", "fc1_bias", "fc2_bias", "head_bias"):
        values[k] = values[k].reshape(-1)
    shapes = {
        "input_mean": (13,), "input_std": (13,), "target_rms": (3,),
        "fc1_weight": (64, 195), "fc1_bias": (64,),
        "fc2_weight": (32, 64), "fc2_bias": (32,),
        "head_weight": (3, 32), "head_bias": (3,),
    }
    for key, shape in shapes.items():
        if values[key].shape != shape or not np.isfinite(values[key]).all():
            raise ValueError(f"{label} {key} invalid: got {values[key].shape}, expected {shape}")
    if np.any(values["input_std"] <= 0) or np.any(values["target_rms"] <= 0):
        raise ValueError(f"{label} normalizer must be positive")
    MLP15, _ = load_model_helpers()
    model = MLP15().cpu()
    model.load_state_dict({
        "net.0.weight": torch.from_numpy(values["fc1_weight"]).float(),
        "net.0.bias": torch.from_numpy(values["fc1_bias"]).float(),
        "net.2.weight": torch.from_numpy(values["fc2_weight"]).float(),
        "net.2.bias": torch.from_numpy(values["fc2_bias"]).float(),
        "net.4.weight": torch.from_numpy(values["head_weight"]).float(),
        "net.4.bias": torch.from_numpy(values["head_bias"]).float(),
    })
    model.eval()
    return model, values, config


def _basic_error_summary(error: np.ndarray) -> dict[str, Any]:
    err = error.astype(np.float64)
    axis_scene = np.mean(np.sqrt(np.mean(err ** 2, axis=1)), axis=0)
    return {
        "scene_count": int(err.shape[0]),
        "scene_macro_rmse_rad_s2": float(np.mean(np.sqrt(np.mean(err ** 2, axis=(1, 2))))),
        "axis_scene_macro_rmse_rad_s2": axis_scene.tolist(),
        "axis_pooled_rmse_rad_s2": np.sqrt(np.mean(err ** 2, axis=(0, 1))).tolist(),
        "pooled_rmse_rad_s2": float(np.sqrt(np.mean(err ** 2))),
    }


def summarize_error(error: np.ndarray, scene_ids: list[str]) -> dict[str, Any]:
    err = error.astype(np.float64)
    wind = [int(s.rsplit("_W", 1)[1]) for s in scene_ids]
    groups = {
        "W09_W14": [i for i, w in enumerate(wind) if 9 <= w <= 14],
        "W15_NO_WIND": [i for i, w in enumerate(wind) if w == 15],
        "W00_W08": [i for i, w in enumerate(wind) if 0 <= w <= 8],
    }
    result = _basic_error_summary(err)
    result["wind_groups"] = {
        name: _basic_error_summary(err[idx]) if idx else {"scene_count": 0}
        for name, idx in groups.items()
    }
    result["per_scene"] = [
        {"scene_id": scene_ids[i], "wind_id": f"W{wind[i]:02d}",
         "scene_rmse_rad_s2": float(np.sqrt(np.mean(err[i] ** 2))),
         "axis_rmse_rad_s2": np.sqrt(np.mean(err[i] ** 2, axis=0)).tolist()}
        for i in range(len(scene_ids))
    ]
    return result


def infer(model, params: dict[str, np.ndarray], x: np.ndarray, y: np.ndarray,
          make_windows, batch_size: int = 4096) -> np.ndarray:
    mean, std = params["input_mean"], params["input_std"]
    target_rms = params["target_rms"]
    x_norm = ((x - mean) / std).astype(np.float32)
    padded = F.pad(torch.as_tensor(x_norm).permute(0, 2, 1), (WINDOW - 1, 0))
    scenes_n, events, _ = y.shape
    pred_norm = np.empty(y.shape, dtype=np.float32)
    total = scenes_n * events
    with torch.inference_mode():
        for start in range(0, total, batch_size):
            stop = min(start + batch_size, total)
            flat = torch.arange(start, stop)
            scenes = torch.div(flat, events, rounding_mode="floor")
            steps = torch.remainder(flat, events)
            windows = make_windows(padded, scenes, steps)
            pred_norm.reshape(-1, 3)[start:stop] = model(windows).numpy()
    pred_phys = pred_norm * target_rms.astype(np.float32)
    return np.clip(pred_phys, -D_MAX, D_MAX)


def self_check() -> None:
    MLP15, make_windows = load_model_helpers()
    model = MLP15().cpu().eval()
    x = np.zeros((2, 20, INPUT_DIM), dtype=np.float32)
    x[:, :, 0] = 0.25
    padded = F.pad(torch.as_tensor(x).permute(0, 2, 1), (WINDOW - 1, 0))
    window = make_windows(padded, torch.tensor([0, 1]), torch.tensor([0, 19]))
    assert window.shape == (2, WINDOW, INPUT_DIM)
    assert torch.allclose(window[0, -1, 0], torch.tensor(0.25))
    assert model(window).shape == (2, 3)
    e = np.zeros((2, 20, 3), dtype=np.float32)
    e[0, :, 0] = 1.0
    summary = summarize_error(e, ["DL1018_VAL_T1_C00_W09", "DL1018_VAL_T1_C01_W15"])
    assert summary["scene_count"] == 2 and summary["wind_groups"]["W09_W14"]["scene_count"] == 1
    assert summary["wind_groups"]["W15_NO_WIND"]["scene_count"] == 1
    assert np.allclose(np.clip(np.asarray([[60.0, -50.0, 5.0]]), -D_MAX, D_MAX), [[45.0, -45.0, 4.7124]])
    expected_ids = ["DL1018_VAL_T1_C00_W09", "DL1018_VAL_T1_C01_W15", "DL1018_VAL_T1_C02_W00"]
    _assert_ordered_scene_ids(np.asarray(expected_ids, dtype=np.str_), expected_ids, "valid synthetic")
    for wrong_ids in (expected_ids[::-1], [expected_ids[0], expected_ids[1], "DL1018_VAL_WRONG"]):
        try:
            _assert_ordered_scene_ids(np.asarray(wrong_ids, dtype=np.str_), expected_ids, "invalid synthetic")
        except ValueError:
            pass
        else:
            raise AssertionError("misordered or wrong C5 VAL scene IDs were accepted")
    print("SELF_CHECK=PASS (CPU synthetic windows, MLP forward, physical RMSE/wind groups; no data read)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-npz", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--b24-model", type=Path)
    parser.add_argument("--c5-24-model", type=Path)
    parser.add_argument("--b768-model", type=Path)
    parser.add_argument("--b24-config", type=Path)
    parser.add_argument("--c5-24-config", type=Path)
    parser.add_argument("--b768-config", type=Path)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--device", choices=("cpu",), default="cpu",
                        help="comparison defaults to CPU to keep this read-only utility deterministic")
    parser.add_argument("--self-check", action="store_true", help="CPU synthetic check only")
    args = parser.parse_args()
    if args.self_check:
        self_check()
        return
    required = (args.dataset_npz, args.manifest, args.b24_model, args.c5_24_model,
                args.b768_model, args.output_json)
    if any(v is None for v in required):
        parser.error("comparison requires combined dataset NPZ/manifest, three model MAT files and --output-json")
    reject_test_path(args.output_json, "output")
    output_json = args.output_json.resolve(strict=False)
    output_csv = output_json.with_suffix(".csv")
    output_root = OUTPUT_ROOT.resolve(strict=False)
    try:
        output_json.relative_to(output_root)
    except ValueError as exc:
        raise ValueError(f"output-json must remain inside the isolated runs directory {output_root}") from exc
    if output_json == output_root:
        raise ValueError("output-json must name a report file below runs")
    if output_json.exists() or output_csv.exists():
        raise FileExistsError("refusing to overwrite comparison output")
    x, y, scene_ids, manifest = load_val(args.dataset_npz, args.manifest)
    models = {
        "B24": load_model(args.b24_model, "B24", "B24", args.b24_config),
        "C5-24": load_model(args.c5_24_model, "C5-24", "C5-24", args.c5_24_config),
        "B-768": load_model(args.b768_model, "B-768", None, args.b768_config),
    }
    _, make_windows = load_model_helpers()
    report: dict[str, Any] = {
        "schema": "DL1018_MLP15_C5_VAL_ACTION_COMPARISON_V1", "status": "PASS",
        "target_contract": TARGET_CONTRACT, "target_unit": "rad/s^2",
        "scene_count": 48, "events_per_scene": EVENT_COUNT,
        "dataset_manifest_schema": manifest["schema"],
        "val_scene_ids": scene_ids,
        "feature_error_contract": FEATURE_ERROR_CONTRACT,
        "reference_feature_source_sha256": sha256(PROJECT_ROOT / FEATURE_ERROR_CONTRACT["reference_source"].split("::")[0]),
        "dataset_npz_sha256": sha256(args.dataset_npz),
        "manifest_sha256": sha256(args.manifest),
        "test_data_read": False, "plant_called": False,
        "models": {},
    }
    rows = []
    for label, (model, params, config) in models.items():
        pred = infer(model, params, x, y, make_windows)
        error = pred.astype(np.float64) - y.astype(np.float64)
        summary = summarize_error(error, scene_ids)
        per_scene = summary.pop("per_scene")
        summary["model_sha256"] = sha256({"B24": args.b24_model, "C5-24": args.c5_24_model,
                                          "B-768": args.b768_model}[label])
        config_path = {"B24": args.b24_config, "C5-24": args.c5_24_config,
                       "B-768": args.b768_config}[label]
        if config_path is not None:
            summary["training_config_sha256"] = sha256(config_path)
        report["models"][label] = summary
        for row in per_scene:
            rows.append({"model": label, **row})
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with output_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["model", "scene_id", "wind_id", "scene_rmse_rad_s2", "axis_rmse_rad_s2"])
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({"status": "PASS", "output_json": str(output_json),
                      "output_csv": str(output_csv), "test_data_read": False,
                      "plant_called": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()

