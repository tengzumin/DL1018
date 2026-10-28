#!/usr/bin/env python3
"""Matched MLP15 teacher training; B24/C5-24 differ only by their DEV data source."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

import numpy as np
import torch
from scipy.io import savemat
from torch import nn
from torch.nn import functional as F

ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = Path(__file__).resolve().parents[4]
ISOLATION_ROOT = Path(__file__).resolve().parents[1]
SCREEN_ROOT = ROOT / "architecture_screen_v1"
RUNS_ROOT = ISOLATION_ROOT / "runs"
SEED, STEPS, BATCH, WINDOW, INPUT_DIM, VAL_BATCH, VAL_EVERY = 2026102001, 60000, 512, 15, 13, 4096, 1000
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
MODEL_CONFIG = {
    "architecture": "MLP15", "input_dim": INPUT_DIM, "window_events": WINDOW,
    "hidden": [64, 32], "activation": "SiLU", "output_dim": 3,
    "flatten_order": "event-major, feature-minor",
    "attitude_error_feature_contract": FEATURE_ERROR_CONTRACT,
}
TEST_TOKEN = re.compile(r"test", re.IGNORECASE)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def reject_test_path(path: Path, label: str) -> None:
    if TEST_TOKEN.search(str(path)):
        raise ValueError(f"{label} path contains TEST: {path}")


def _check_manifest(manifest_path: Path, data_path: Path) -> dict[str, Any]:
    reject_test_path(manifest_path, "manifest")
    reject_test_path(data_path, "dataset")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "DL1018_MLP15_MATCHED_B24_C5_24_C5_VAL48_DATASET_V1" or manifest.get("status") != "PASS_OFFLINE_EXTRACTION":
        raise ValueError("dataset manifest is not the frozen matched-builder output")
    if manifest.get("TEST_accessed") is not False:
        raise ValueError("manifest indicates TEST data access")
    if manifest.get("plant_truth_read") is not False:
        raise ValueError("manifest must explicitly state plant_truth_read=false")
    if manifest.get("feature_order") != FEATURE_ORDER:
        raise ValueError("feature order differs from frozen MLP15 contract")
    if manifest.get("target") != TARGET_CONTRACT:
        raise ValueError(f"target must be {TARGET_CONTRACT}")
    declared_hash = manifest.get("dataset_sha256")
    if not declared_hash or declared_hash != sha256(data_path):
        raise ValueError(f"dataset SHA does not match manifest: {data_path}")
    expected_path = (PROJECT_ROOT / manifest["dataset_path"]).resolve()
    if expected_path != data_path.resolve():
        raise ValueError("dataset path differs from manifest identity")
    rows = manifest.get("rows")
    if not isinstance(rows, list):
        raise ValueError("manifest lacks per-scene row identities")
    return manifest


def _assert_ordered_scene_ids(actual: np.ndarray | list[str], expected: list[str], label: str) -> None:
    actual_array = np.asarray(actual)
    if actual_array.ndim != 1 or actual_array.tolist() != expected:
        raise ValueError(f"{label} scene IDs do not match manifest order")


def _load_npz(path: Path, manifest: dict[str, Any], arm: str) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, list[str], list[str]]:
    with np.load(path, allow_pickle=False) as data:
        if any(name.lower().startswith("test") for name in data.files):
            raise ValueError("TEST arrays are prohibited")
        required = {"b24_x", "b24_y", "c5_train_x", "c5_train_y", "c5_val_x", "c5_val_y",
                    "b24_scene_ids", "c5_train_scene_ids", "c5_val_scene_ids"}
        if not required.issubset(data.files):
            raise ValueError(f"combined builder NPZ lacks arrays: {sorted(required - set(data.files))}")
        train_key = "b24" if arm == "B24" else "c5_train"
        train_x = np.asarray(data[f"{train_key}_x"], dtype=np.float32)
        train_y = np.asarray(data[f"{train_key}_y"], dtype=np.float32)
        val_x = np.asarray(data["c5_val_x"], dtype=np.float32)
        val_y = np.asarray(data["c5_val_y"], dtype=np.float32)
        b24_npz_ids = np.asarray(data["b24_scene_ids"])
        c5_train_npz_ids = np.asarray(data["c5_train_scene_ids"])
        c5_val_npz_ids = np.asarray(data["c5_val_scene_ids"])
    split_name = "TRAIN_B24" if arm == "B24" else "TRAIN_C5_24"
    teacher = "B72_RBF" if arm == "B24" else "C5_RBF"
    def ids_for(split: str, source: str, count: int) -> list[str]:
        selected = [r for r in manifest["rows"] if r.get("split") == split]
        ids = [r.get("scene_id") for r in selected]
        if len(ids) != count or len(set(ids)) != count or any(r.get("teacher_source") != source for r in selected):
            raise ValueError(f"manifest rows do not match {split}/{source}/{count}")
        if any(not isinstance(s, str) or "TEST" in s.upper() for s in ids):
            raise ValueError(f"TEST scene ID in {split}")
        return ids
    train_ids = ids_for(split_name, teacher, 24)
    b24_ids = ids_for("TRAIN_B24", "B72_RBF", 24)
    c5_train_ids = ids_for("TRAIN_C5_24", "C5_RBF", 24)
    val_ids = ids_for("C5_VAL48", "C5_RBF", 48)
    _assert_ordered_scene_ids(b24_npz_ids, b24_ids, "b24_npz")
    _assert_ordered_scene_ids(c5_train_npz_ids, c5_train_ids, "c5_train_npz")
    _assert_ordered_scene_ids(c5_val_npz_ids, val_ids, "c5_val_npz")
    selected_train_npz_ids = b24_npz_ids if arm == "B24" else c5_train_npz_ids
    _assert_ordered_scene_ids(selected_train_npz_ids, train_ids, f"selected_{arm}_train_npz")
    _validate_arrays(train_x, train_y, 24)
    _validate_arrays(val_x, val_y, 48)
    for split, x, y, count in ((split_name, train_x, train_y, 24), ("C5_VAL48", val_x, val_y, 48)):
        rows = [r for r in manifest["rows"] if r.get("split") == split]
        for i, row in enumerate(rows):
            if row.get("event_count") != 1999 or row.get("feature_shape") != [1999, INPUT_DIM] or row.get("target_shape") != [1999, 3]:
                raise ValueError(f"per-scene shape/event contract mismatch: {row.get('scene_id')}")
    return train_x, train_y, val_x, val_y, train_ids, val_ids


def _validate_arrays(x: np.ndarray, y: np.ndarray, expected_scenes: int) -> None:
    if x.shape != (expected_scenes, 1999, INPUT_DIM) or y.shape != (expected_scenes, 1999, 3):
        raise ValueError(f"unexpected dataset shapes: features={x.shape}, targets={y.shape}")
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError("dataset contains non-finite values")


def clip_runtime(prediction_rad_s2: np.ndarray) -> np.ndarray:
    return np.clip(prediction_rad_s2, -D_MAX, D_MAX)


def load_model_helpers():
    sys.path.insert(0, str(SCREEN_ROOT))
    from screen_attitude_architectures_v1 import MLP15, make_windows
    return MLP15, make_windows


def evaluate(model: nn.Module, padded: torch.Tensor, y: np.ndarray, target_rms: np.ndarray,
             make_windows, device: torch.device) -> tuple[float, list[float], list[float]]:
    model.eval()
    scenes_n, events, _ = y.shape
    pred = np.empty(y.shape, dtype=np.float32)
    total = scenes_n * events
    with torch.inference_mode():
        for start in range(0, total, VAL_BATCH):
            stop = min(start + VAL_BATCH, total)
            flat = torch.arange(start, stop, device=device)
            scenes = torch.div(flat, events, rounding_mode="floor")
            steps = torch.remainder(flat, events)
            windows = make_windows(padded, scenes, steps)
            pred.reshape(-1, 3)[start:stop] = model(windows).cpu().numpy()
    pred_phys = clip_runtime(pred.astype(np.float64) * target_rms)
    err_phys = pred_phys - y.astype(np.float64)
    scene_macro = float(np.mean(np.sqrt(np.mean(err_phys ** 2, axis=(1, 2)))))
    axis_macro = np.mean(np.sqrt(np.mean(err_phys ** 2, axis=1)), axis=0).tolist()
    axis_pooled = np.sqrt(np.mean(err_phys ** 2, axis=(0, 1))).tolist()
    return scene_macro, axis_macro, axis_pooled


def atomic_torch_save(path: Path, obj: Any) -> str:
    tmp = path.with_suffix(path.suffix + ".tmp")
    torch.save(obj, tmp)
    tmp.replace(path)
    return sha256(path)


def self_check() -> None:
    MLP15, make_windows = load_model_helpers()
    _validate_arrays(np.zeros((24, 1999, 13), dtype=np.float32),
                     np.zeros((24, 1999, 3), dtype=np.float32), 24)
    _validate_arrays(np.zeros((48, 1999, 13), dtype=np.float32),
                     np.zeros((48, 1999, 3), dtype=np.float32), 48)
    try:
        _validate_arrays(np.zeros((24, 1999, 12), dtype=np.float32),
                         np.zeros((24, 1999, 3), dtype=np.float32), 24)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid feature shape was accepted")
    expected_ids = ["DL1018_DEV_T1_C00_W03", "DL1018_DEV_T1_C01_W15", "DL1018_DEV_T1_C04_W00"]
    _assert_ordered_scene_ids(np.asarray(expected_ids, dtype=np.str_), expected_ids, "valid synthetic")
    for wrong_ids in (expected_ids[::-1], [expected_ids[0], expected_ids[1], "DL1018_DEV_WRONG"]):
        try:
            _assert_ordered_scene_ids(np.asarray(wrong_ids, dtype=np.str_), expected_ids, "invalid synthetic")
        except ValueError:
            pass
        else:
            raise AssertionError("misordered or wrong scene IDs were accepted")
    x = torch.arange(2 * 32 * INPUT_DIM, dtype=torch.float32).reshape(2, 32, INPUT_DIM)
    padded = F.pad(x.permute(0, 2, 1), (WINDOW - 1, 0))
    windows = make_windows(padded, torch.tensor([0, 1]), torch.tensor([0, 31]))
    assert windows.shape == (2, WINDOW, INPUT_DIM)
    assert torch.count_nonzero(windows[0, :-1]).item() == 0
    assert torch.equal(windows[0, -1], x[0, 0])
    model = MLP15().cpu()
    assert model(windows).shape == (2, 3)
    clipped = clip_runtime(np.asarray([[60.0, -50.0, 5.0]]))
    assert np.allclose(clipped, [[45.0, -45.0, 4.7124]])
    try:
        reject_test_path(Path("fixture/TEST48/data.npz"), "self-check")
    except ValueError:
        pass
    else:
        raise AssertionError("TEST path was not rejected")
    print("SELF_CHECK=PASS (CPU synthetic shapes/windows/model; no data read, no training)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", choices=("B24", "C5-24"))
    parser.add_argument("--dataset-npz", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda:0"), default="auto")
    parser.add_argument("--self-check", action="store_true", help="CPU synthetic check only; never trains")
    args = parser.parse_args()
    if args.self_check:
        self_check()
        return
    required = (args.arm, args.dataset_npz, args.manifest, args.output_dir)
    if any(v is None for v in required):
        parser.error("training requires --arm, --dataset-npz, --manifest and --output-dir")
    manifest = _check_manifest(args.manifest, args.dataset_npz)
    train_x, train_y, val_x, val_y, train_ids, val_ids = _load_npz(args.dataset_npz, manifest, args.arm)
    train_teacher = "B72_RBF" if args.arm == "B24" else "C5_RBF"
    reject_test_path(args.output_dir, "output")
    output = args.output_dir.resolve(strict=False)
    runs_root = RUNS_ROOT.resolve(strict=False)
    try:
        output.relative_to(runs_root)
    except ValueError as exc:
        raise ValueError(f"output-dir must be inside the isolated runs directory {runs_root}") from exc
    if output == runs_root:
        raise ValueError("output-dir must name a new run directory below runs")
    if output.exists():
        raise FileExistsError(f"refusing to overwrite output: {output}")

    mean = train_x.mean(axis=(0, 1), dtype=np.float64)
    std = np.maximum(train_x.std(axis=(0, 1), dtype=np.float64), 1e-6)
    target_rms = np.sqrt(np.mean(train_y.astype(np.float64) ** 2, axis=(0, 1)))
    if not np.isfinite(np.r_[mean, std, target_rms]).all() or np.any(target_rms <= 1e-8):
        raise ValueError("invalid DEV-only normalizer")
    train_norm = ((train_x - mean) / std).astype(np.float32)
    val_norm = ((val_x - mean) / std).astype(np.float32)
    train_target = (train_y / target_rms).astype(np.float32)

    if args.device == "cuda:0" and not torch.cuda.is_available():
        raise RuntimeError("cuda:0 requested but unavailable")
    device = torch.device("cuda:0" if args.device == "cuda:0" or
                          (args.device == "auto" and torch.cuda.is_available()) else "cpu")
    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    torch.use_deterministic_algorithms(True)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(SEED)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False

    MLP15, make_windows = load_model_helpers()
    train_pad = F.pad(torch.as_tensor(train_norm, device=device).permute(0, 2, 1), (WINDOW - 1, 0))
    val_pad = F.pad(torch.as_tensor(val_norm, device=device).permute(0, 2, 1), (WINDOW - 1, 0))
    target_tensor = torch.as_tensor(train_target, device=device)
    rng = np.random.default_rng(SEED)
    model = MLP15().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
    dataset_identity = {
        "schema": manifest["schema"], "dataset_path": manifest["dataset_path"],
        "dataset_sha256": sha256(args.dataset_npz), "manifest_sha256": sha256(args.manifest),
        "train_split": "TRAIN_B24" if args.arm == "B24" else "TRAIN_C5_24",
        "teacher_source": train_teacher, "train_scene_ids": train_ids,
        "val_split": "C5_VAL48", "val_scene_ids": val_ids,
        "input_locks": manifest.get("input_locks", {}),
        "feature_error_contract": FEATURE_ERROR_CONTRACT,
        "reference_feature_source_sha256": sha256(PROJECT_ROOT / FEATURE_ERROR_CONTRACT["reference_source"].split("::")[0]),
    }
    run_metadata = {"arm": args.arm, "seed": SEED, "model_config": MODEL_CONFIG,
                    "dataset_identity": dataset_identity}
    output.mkdir(parents=True)
    started = time.perf_counter()
    best_metric, _, _ = evaluate(model, val_pad, val_y, target_rms, make_windows, device)
    best_step = 0
    atomic_torch_save(output / "initial.pt", {
        **run_metadata, "step": 0, "state_dict": model.state_dict(),
    })
    best_hash = atomic_torch_save(output / "best.pt", {
        **run_metadata, "step": 0, "state_dict": model.state_dict(),
        "input_mean": torch.as_tensor(mean.copy()),
        "input_std": torch.as_tensor(std.copy()),
        "target_rms": torch.as_tensor(target_rms.copy()),
        "val_scene_macro_physical_rmse_rad_s2": best_metric,
    })
    history_path = output / "training_history.jsonl"
    progress_path = output / "training_progress.json"
    progress = {
        "schema": "DL1018_MLP15_MATCHED_TRAINING_PROGRESS_V1", "status": "RUNNING",
        **run_metadata, "completed_steps": 0, "target_steps": STEPS,
        "best_step": best_step, "best_metric": best_metric,
        "plant_called": False, "test_data_read": False,
    }
    progress_path.write_text(json.dumps(progress, indent=2) + "\n", encoding="utf-8")

    for step in range(1, STEPS + 1):
        scenes = torch.as_tensor(rng.integers(0, 24, BATCH, dtype=np.int64), device=device)
        times = torch.as_tensor(rng.integers(0, 1999, BATCH, dtype=np.int64), device=device)
        windows = make_windows(train_pad, scenes, times)
        target = target_tensor[scenes, times]
        model.train()
        optimizer.zero_grad(set_to_none=True)
        loss = F.smooth_l1_loss(model(windows), target, beta=1.0)
        if not torch.isfinite(loss):
            raise FloatingPointError(f"non-finite loss at step {step}")
        loss.backward()
        optimizer.step()
        if step % VAL_EVERY == 0:
            metric, axis_macro, axis_pooled = evaluate(model, val_pad, val_y, target_rms, make_windows, device)
            if metric < best_metric:
                best_metric, best_step = metric, step
                best_hash = atomic_torch_save(output / "best.pt", {
                    **run_metadata, "step": step, "state_dict": model.state_dict(),
                    "input_mean": torch.as_tensor(mean.copy()),
                    "input_std": torch.as_tensor(std.copy()),
                    "target_rms": torch.as_tensor(target_rms.copy()),
                    "val_scene_macro_physical_rmse_rad_s2": metric,
                })
            row = {
                "step": step, "train_loss": float(loss.item()),
                "val_scene_macro_physical_rmse_rad_s2": metric,
                "val_axis_scene_macro_rmse_rad_s2": axis_macro,
                "val_axis_pooled_rmse_rad_s2": axis_pooled,
                "best_step": best_step, "best_metric": best_metric,
            }
            with history_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            progress.update({"completed_steps": step, "best_step": best_step,
                             "best_metric": best_metric, "best_sha256": best_hash,
                             "latest_train_loss": float(loss.item()),
                             "updated_utc": datetime.now(timezone.utc).isoformat()})
            progress_path.write_text(json.dumps(progress, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(row, ensure_ascii=False), flush=True)

    final_path = output / "final.pt"
    atomic_torch_save(final_path, {**run_metadata, "step": STEPS, "state_dict": model.state_dict()})
    best = torch.load(output / "best.pt", map_location=device, weights_only=True)
    model.load_state_dict(best["state_dict"])
    model.eval()
    state = model.state_dict()
    weights_path = output / "mlp15_attitude_weights_v1.mat"
    savemat(weights_path, {
        "input_mean": mean.reshape(1, -1), "input_std": std.reshape(1, -1),
        "target_rms": target_rms.reshape(1, -1),
        "fc1_weight": state["net.0.weight"].cpu().numpy().astype(np.float64),
        "fc1_bias": state["net.0.bias"].cpu().numpy().astype(np.float64),
        "fc2_weight": state["net.2.weight"].cpu().numpy().astype(np.float64),
        "fc2_bias": state["net.2.bias"].cpu().numpy().astype(np.float64),
        "head_weight": state["net.4.weight"].cpu().numpy().astype(np.float64),
        "head_bias": state["net.4.bias"].cpu().numpy().astype(np.float64),
    }, do_compression=True, oned_as="row")
    window = make_windows(val_pad, torch.tensor([0], device=device), torch.tensor([100], device=device))
    with torch.inference_mode():
        expected = model(window).cpu().numpy()[0] * target_rms
    parity_path = output / "parity_vector_v1.mat"
    savemat(parity_path, {
        "input_normalized_window": window.cpu().numpy()[0].astype(np.float64),
        "expected_teacher_action_rad_s2": expected.astype(np.float64),
        "scene_index_zero_based": np.asarray([[0]], dtype=np.int32),
        "event_index_zero_based": np.asarray([[100]], dtype=np.int32),
    }, do_compression=True, oned_as="row")
    config = {
        "schema": "DL1018_MLP15_MATCHED_TRAINING_CONFIG_V1", "status": "PASS",
        "arm": args.arm, "architecture": "MLP15", "input_dim": INPUT_DIM,
        "window_events": WINDOW, "hidden": [64, 32], "activation": "SiLU", "output_dim": 3,
        "seed": SEED, "optimizer_steps": STEPS, "batch_size": BATCH,
        "validation_interval": VAL_EVERY, "optimizer": "Adam",
        "learning_rate": 1e-3, "weight_decay": 1e-5, "loss": "SmoothL1(beta=1.0)",
        "selection": "earliest strict minimum C5 VAL48 physical-unit scene-macro RMSE after runtime dmax clipping",
        "target_contract": TARGET_CONTRACT, "teacher_id": train_teacher,
        "input_mean_fit_split": "DEV24", "input_std_fit_split": "DEV24",
        "target_rms_fit_split": "DEV24", "best_step": best_step,
        "best_val_scene_macro_physical_rmse_rad_s2": best_metric,
        "model_config": MODEL_CONFIG, "dataset_identity": dataset_identity,
        "trainer_sha256": sha256(Path(__file__).resolve()),
        "plant_called": False, "test_data_read": False,
        "device": str(device), "torch_version": torch.__version__,
        "gpu_name": torch.cuda.get_device_name(0) if device.type == "cuda" else "CPU",
        "elapsed_seconds": time.perf_counter() - started,
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }
    config_path = output / "training_config.json"
    config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    progress.update({"status": "PASS", "completed_steps": STEPS, "best_step": best_step,
                     "best_metric": best_metric,
                     "updated_utc": datetime.now(timezone.utc).isoformat()})
    progress_path.write_text(json.dumps(progress, indent=2) + "\n", encoding="utf-8")
    receipt = {
        "schema": "DL1018_MLP15_MATCHED_TRAINING_RECEIPT_V1", "status": "PASS",
        "arm": args.arm, "best_step": best_step, "best_metric": best_metric,
        "input_sha256": {"dataset_npz": sha256(args.dataset_npz), "manifest": sha256(args.manifest)},
        "dataset_identity": config["dataset_identity"], "model_config": MODEL_CONFIG,
        "output_sha256": {p.name: sha256(p) for p in
                          (output / "initial.pt", output / "best.pt", final_path, weights_path,
                           parity_path, history_path, progress_path, config_path)},
        "plant_called": False, "test_data_read": False,
    }
    receipt_path = output / "run_receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "arm": args.arm, "best_step": best_step,
                      "output_dir": str(output), "plant_called": False, "test_data_read": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()

