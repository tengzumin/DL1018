#!/usr/bin/env python3
"""One locked GRU15 training job on all 72 reusable C5-RBF teacher scenes."""
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

TASK_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = TASK_ROOT.parents[2]
DATA_ROOT = PROJECT_ROOT / "experiments/dl_attitude_replacement_20261026/mlp15_c5_teacher_redistill_v1"
DATASET_PATH = DATA_ROOT / "matched_teacher_data_v1.npz"
MANIFEST_PATH = DATA_ROOT / "DATASET_MANIFEST_v1.json"
LOCK_PATH = TASK_ROOT / "GRU15_C5_TEACHER_FULL72_SOURCE_LOCK_v1.json"
SCREEN_ROOT = PROJECT_ROOT / "experiments/dl_attitude_replacement_20261026/architecture_screen_v1"
OUTPUT_DIR = TASK_ROOT / "runs/C5_GRU15_FULL72_SEED2026102001"

SEED, STEPS, BATCH, WINDOW, INPUT_DIM = 2026102001, 60000, 512, 15, 13
LOG_EVERY = 1000
EXPECTED_SPLITS = {"TRAIN_C5_24": 24, "C5_VAL48": 48}
FEATURE_ORDER = [
    "wrapped_attitude_error_euler_rad_x3", "body_rate_rad_s_x3",
    "nominal_bs_body_torque_Nm_x3", "morph_command_x4",
]
FORBIDDEN_INPUTS = [
    "Jhat", "Jdot_hat", "inertia or mass properties", "Plant truth",
    "RBF weights or hidden state", "observer", "physical feedforward",
]
TARGET_CONTRACT = "logged rbf_output_raw at attitude event k; post-dmax/pre-beta; rad/s^2"
D_MAX = np.asarray([45.0, 45.0, 4.7124], dtype=np.float64)
TEST_TOKEN = re.compile(r"test", re.IGNORECASE)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_array(array: np.ndarray) -> str:
    contiguous = np.ascontiguousarray(array)
    return hashlib.sha256(contiguous.tobytes()).hexdigest()


def write_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def reject_test_path(path: Path, label: str) -> None:
    if TEST_TOKEN.search(str(path)):
        raise ValueError(f"{label} path contains TEST: {path}")


def require_root_release(lock: dict[str, Any]) -> None:
    release = lock.get("training_release", {})
    if (lock.get("status") != "APPROVED_FOR_TRAINING"
            or release.get("approved") is not True
            or release.get("authorized_jobs") != 1
            or not release.get("approved_by")
            or not release.get("approval_reference")):
        raise PermissionError("source lock is pending root review; training is not released")


def validate_feature_contract(feature_order: list[str], lock: dict[str, Any]) -> None:
    contract = lock.get("feature_contract", {})
    if feature_order != FEATURE_ORDER or contract.get("allowed_feature_groups") != FEATURE_ORDER:
        raise ValueError("input feature order is not the frozen 13-D whitelist")
    if contract.get("input_dim") != INPUT_DIM or contract.get("prohibited_inputs") != FORBIDDEN_INPUTS:
        raise ValueError("source lock does not bind the complete input allow/deny contract")
    feature_text = " ".join(feature_order).lower()
    if any(token.lower() in feature_text for token in ("jhat", "jdot", "inertia", "plant", "observer", "feedforward")):
        raise ValueError("prohibited input appears in feature names")


def load_and_verify_lock(*, require_release: bool) -> dict[str, Any]:
    reject_test_path(DATASET_PATH, "dataset")
    reject_test_path(MANIFEST_PATH, "manifest")
    reject_test_path(OUTPUT_DIR, "output")
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    if lock.get("schema") != "DL1018_GRU15_C5_TEACHER_FULL72_SOURCE_LOCK_V1":
        raise ValueError("unexpected C5 full72 source-lock schema")
    validate_feature_contract(FEATURE_ORDER, lock)
    if require_release:
        require_root_release(lock)
    files = lock.get("source_file_sha256", {})
    if not files:
        raise ValueError("source lock has no source-file hashes")
    for relative, expected in files.items():
        source_path = PROJECT_ROOT / Path(relative)
        reject_test_path(source_path, "source")
        if not source_path.is_file() or sha256_file(source_path) != expected:
            raise ValueError(f"locked source hash mismatch: {relative}")
    if lock.get("dataset", {}).get("sha256") != sha256_file(DATASET_PATH):
        raise ValueError("dataset SHA-256 differs from source lock")
    if lock.get("dataset", {}).get("manifest_sha256") != sha256_file(MANIFEST_PATH):
        raise ValueError("manifest SHA-256 differs from source lock")
    if sha256_file(Path(__file__).resolve()) != files.get(Path(__file__).resolve().relative_to(PROJECT_ROOT).as_posix()):
        raise ValueError("trainer SHA-256 differs from source lock")
    return lock


def _ordered_ids(rows: list[dict[str, Any]], split: str) -> list[str]:
    return [row["scene_id"] for row in rows if row.get("split") == split]


def _project_relative(source_path: str) -> str:
    path = Path(source_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve(strict=False).relative_to(PROJECT_ROOT).as_posix()


def _validate_manifest(lock: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if (manifest.get("schema") != "DL1018_MLP15_MATCHED_B24_C5_24_C5_VAL48_DATASET_V1"
            or manifest.get("status") != "PASS_OFFLINE_EXTRACTION"
            or manifest.get("TEST_accessed") is not False
            or manifest.get("plant_truth_read") is not False
            or manifest.get("inertia_config_read") is not False
            or manifest.get("target") != TARGET_CONTRACT):
        raise ValueError("frozen dataset manifest does not satisfy the C5 teacher contract")
    validate_feature_contract(manifest.get("feature_order", []), lock)
    dataset = lock["dataset"]
    if (dataset.get("manifest_inertia_config_read") is not False
            or manifest.get("inertia_config_read") is not dataset.get("manifest_inertia_config_read")
            or manifest.get("dataset_sha256") != dataset.get("sha256")
            or _project_relative(manifest.get("dataset_path", ""))
            != DATASET_PATH.resolve().relative_to(PROJECT_ROOT).as_posix()):
        raise ValueError("manifest dataset identity/inertia-read flag differs from source lock")
    selected_rows: list[dict[str, Any]] = []
    expected_ids: list[str] = []
    for split, expected_count in EXPECTED_SPLITS.items():
        split_rows = [row for row in manifest.get("rows", []) if row.get("split") == split]
        if len(split_rows) != expected_count:
            raise ValueError(f"unexpected {split} scene count: {len(split_rows)}")
        for row in split_rows:
            scene_id = row.get("scene_id", "")
            if (row.get("teacher_source") != "C5_RBF" or not scene_id
                    or TEST_TOKEN.search(scene_id) or row.get("event_count") != 1999
                    or row.get("feature_shape") != [1999, INPUT_DIM]
                    or row.get("target_shape") != [1999, 3]
                    or row.get("feature_finite") is not True or row.get("target_finite") is not True):
                raise ValueError(f"invalid C5 scene row: {scene_id}")
        selected_rows.extend(split_rows)
        expected_ids.extend(_ordered_ids(split_rows, split))
    if len(expected_ids) != 72 or len(set(expected_ids)) != 72:
        raise ValueError("C5 development scene IDs are not unique 72-scene identity")
    locked_ids = lock.get("scene_ids_in_training_order")
    if expected_ids != locked_ids:
        raise ValueError("manifest C5 scene order differs from source lock")
    ids_hash = hashlib.sha256(("\n".join(expected_ids) + "\n").encode("utf-8")).hexdigest()
    if ids_hash != lock.get("ordered_scene_ids_sha256"):
        raise ValueError("ordered C5 scene-ID digest differs from source lock")
    source_fields = ("scene_id", "teacher_source", "raw_sha256", "status_sha256",
                     "run_start_sha256", "scene_identity_sha256", "event_count",
                     "feature_shape", "target_shape", "status_trace_audit_state")
    locked_sources = lock.get("scene_sources", [])
    expected_sources = []
    for row in selected_rows:
        source = {field: row.get(field) for field in source_fields}
        source["source_split"] = row["split"]
        for kind in ("raw", "status", "run_start"):
            source[f"{kind}_path"] = _project_relative(row[f"{kind}_path"])
        expected_sources.append(source)
    if expected_sources != locked_sources:
        raise ValueError("per-scene C5 source hashes/order differ from source lock")
    return manifest, selected_rows, expected_ids


def _load_c5_training_arrays(lock: dict[str, Any], expected_ids: list[str]) -> tuple[np.ndarray, np.ndarray]:
    # Access only the six named C5 members. In particular, no b24_* member is
    # indexed or materialized; the container SHA locks the opaque NPZ bytes.
    with np.load(DATASET_PATH, allow_pickle=False) as archive:
        c5_train_x = np.asarray(archive["c5_train_x"], dtype=np.float32)
        c5_train_y = np.asarray(archive["c5_train_y"], dtype=np.float32)
        c5_train_ids = np.asarray(archive["c5_train_scene_ids"]).astype(str).tolist()
        c5_dev_x = np.asarray(archive["c5_val_x"], dtype=np.float32)
        c5_dev_y = np.asarray(archive["c5_val_y"], dtype=np.float32)
        c5_dev_ids = np.asarray(archive["c5_val_scene_ids"]).astype(str).tolist()
    if c5_train_ids + c5_dev_ids != expected_ids:
        raise ValueError("C5 archive scene IDs/order differ from frozen manifest")
    arrays = {
        "c5_train_x": c5_train_x, "c5_train_y": c5_train_y,
        "c5_val_x": c5_dev_x, "c5_val_y": c5_dev_y,
    }
    for key, array in arrays.items():
        if sha256_array(array) != lock["dataset"]["selected_array_sha256"][key]:
            raise ValueError(f"C5 array content hash differs from source lock: {key}")
    if (c5_train_x.shape != (24, 1999, INPUT_DIM) or c5_train_y.shape != (24, 1999, 3)
            or c5_dev_x.shape != (48, 1999, INPUT_DIM) or c5_dev_y.shape != (48, 1999, 3)
            or not all(np.isfinite(array).all() for array in arrays.values())):
        raise ValueError("C5 array shape or finite-value check failed")
    x = np.concatenate((c5_train_x, c5_dev_x), axis=0)
    y = np.concatenate((c5_train_y, c5_dev_y), axis=0)
    if (x.shape != (72, 1999, INPUT_DIM) or y.shape != (72, 1999, 3)
            or sha256_array(x) != lock["dataset"]["full72_x_sha256"]
            or sha256_array(y) != lock["dataset"]["full72_y_sha256"]):
        raise ValueError("combined C5 full72 array identity/shape mismatch")
    return x, y


def fit_normalizer(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mean = x.mean(axis=(0, 1), dtype=np.float64)
    std = np.maximum(x.std(axis=(0, 1), dtype=np.float64), 1e-6)
    target_rms = np.sqrt(np.mean(y.astype(np.float64) ** 2, axis=(0, 1)))
    if not np.isfinite(np.r_[mean, std, target_rms]).all() or np.any(target_rms <= 1e-8):
        raise ValueError("invalid full72-only normalizer")
    return mean, std, target_rms


def load_model_helpers():
    sys.path.insert(0, str(SCREEN_ROOT))
    from screen_attitude_architectures_v1 import GRU15, make_windows
    return GRU15, make_windows


def atomic_torch_save(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    torch.save(payload, temporary)
    temporary.replace(path)


def self_check() -> None:
    """CPU-only synthetic wiring check; does not open the dataset or train."""
    pending_lock = {"status": "PREPARED_PENDING_ROOT_REVIEW",
                    "training_release": {"approved": False, "authorized_jobs": 1}}
    try:
        require_root_release(pending_lock)
    except PermissionError:
        pass
    else:
        raise AssertionError("pending source lock must refuse training")
    validate_feature_contract(FEATURE_ORDER, {
        "feature_contract": {"input_dim": INPUT_DIM,
                             "allowed_feature_groups": FEATURE_ORDER,
                             "prohibited_inputs": FORBIDDEN_INPUTS},
    })
    try:
        validate_feature_contract(FEATURE_ORDER + ["Jhat"], {
            "feature_contract": {"input_dim": INPUT_DIM,
                                 "allowed_feature_groups": FEATURE_ORDER + ["Jhat"],
                                 "prohibited_inputs": FORBIDDEN_INPUTS},
        })
    except ValueError:
        pass
    else:
        raise AssertionError("prohibited input feature was accepted")
    x = np.zeros((2, 20, INPUT_DIM), dtype=np.float32)
    y = np.ones((2, 20, 3), dtype=np.float32)
    mean, std, target_rms = fit_normalizer(x, y)
    assert mean.shape == std.shape == (INPUT_DIM,)
    assert target_rms.shape == (3,) and np.all(target_rms == 1.0)

    GRU15, make_windows = load_model_helpers()
    features = torch.arange(2 * 20 * INPUT_DIM, dtype=torch.float32).reshape(2, 20, INPUT_DIM)
    padded = F.pad(features.permute(0, 2, 1), (WINDOW - 1, 0))
    windows = make_windows(padded, torch.tensor([0, 1]), torch.tensor([0, 19]))
    assert windows.shape == (2, WINDOW, INPUT_DIM)
    assert torch.count_nonzero(windows[0, :-1]).item() == 0
    assert torch.equal(windows[0, -1], features[0, 0])
    model = GRU15().cpu()
    assert model(windows).shape == (2, 3)
    assert torch.isfinite(model(windows)).all()
    try:
        reject_test_path(Path("synthetic/TEST48/forbidden.npz"), "self-check")
    except ValueError:
        pass
    else:
        raise AssertionError("TEST path was not rejected")
    print("SELF_CHECK=PASS (CPU synthetic normalizer/windows/GRU; pending-release gate; no dataset read/training)")


def run_training(device_name: str) -> None:
    lock = load_and_verify_lock(require_release=True)
    if OUTPUT_DIR.exists():
        raise FileExistsError(f"single authorized run output already exists: {OUTPUT_DIR}")
    _, _, scene_ids = _validate_manifest(lock)
    x, y = _load_c5_training_arrays(lock, scene_ids)
    OUTPUT_DIR.mkdir(parents=True)

    mean, std, target_rms = fit_normalizer(x, y)
    x_norm = ((x - mean) / std).astype(np.float32)
    y_norm = (y / target_rms).astype(np.float32)
    if device_name == "cuda:0" and not torch.cuda.is_available():
        raise RuntimeError("cuda:0 requested but unavailable")
    device = torch.device("cuda:0" if device_name == "cuda:0" or
                          (device_name == "auto" and torch.cuda.is_available()) else "cpu")

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

    GRU15, make_windows = load_model_helpers()
    padded = F.pad(torch.as_tensor(x_norm, device=device).permute(0, 2, 1), (WINDOW - 1, 0))
    targets = torch.as_tensor(y_norm, device=device)
    rng = np.random.default_rng(SEED)
    model = GRU15().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
    run_identity = {
        "dataset_sha256": lock["dataset"]["sha256"],
        "manifest_sha256": lock["dataset"]["manifest_sha256"],
        "source_lock_sha256": sha256_file(LOCK_PATH),
        "source_file_sha256": lock["source_file_sha256"],
        "train_splits": ["TRAIN_C5_24", "C5_VAL48_AS_DEV_TRAIN"],
        "teacher_source": "C5_RBF",
        "scene_ids_in_training_order": scene_ids,
        "scene_sources": lock["scene_sources"],
        "events_per_scene": 1999,
        "unique_training_events": 143928,
        "feature_contract": lock["feature_contract"],
        "target_contract": TARGET_CONTRACT,
        "TEST48_read": False,
        "B24_arrays_read": False,
    }
    config = {
        "schema": "DL1018_GRU15_C5_TEACHER_FULL72_TRAINING_CONFIG_V1",
        "status": "RUNNING", "architecture": "GRU15", "input_dim": INPUT_DIM,
        "window_events": WINDOW, "hidden_size": 32, "cell": "GRU", "output_dim": 3,
        "seed": SEED, "optimizer_steps": STEPS, "batch_size": BATCH,
        "optimizer": "Adam", "learning_rate": 1e-3, "weight_decay": 1e-5,
        "loss": "SmoothL1(beta=1.0)", "checkpoint_policy": "final_step_only_at_60000",
        "validation": "disabled; no validation or checkpoint selection",
        "normalizer_fit_data": "all 72 C5_RBF development scenes",
        "normalizer_fit_splits": ["TRAIN_C5_24", "C5_VAL48_AS_DEV_TRAIN"],
        "model_config": {"layout": "batch,time,feature", "gate_order": "reset,update,new"},
        "dataset_identity": run_identity, "device": str(device),
        "torch_version": torch.__version__, "created_utc": datetime.now(timezone.utc).isoformat(),
        "plant_called": False, "TEST48_read": False,
    }
    history_path = OUTPUT_DIR / "training_history.jsonl"
    progress_path = OUTPUT_DIR / "training_progress.json"
    write_json(OUTPUT_DIR / "training_config.json", config)
    write_json(progress_path, {
        "schema": "DL1018_GRU15_C5_FULL72_PROGRESS_V1", "status": "RUNNING",
        "completed_steps": 0, "target_steps": STEPS, "logged_every_steps": LOG_EVERY,
        "plant_called": False, "TEST48_read": False,
    })
    history_path.write_text("", encoding="utf-8")
    started = time.perf_counter()
    loss_sum = 0.0

    try:
        for step in range(1, STEPS + 1):
            scenes = torch.as_tensor(rng.integers(0, 72, BATCH, dtype=np.int64), device=device)
            times = torch.as_tensor(rng.integers(0, 1999, BATCH, dtype=np.int64), device=device)
            windows = make_windows(padded, scenes, times)
            target = targets[scenes, times]
            model.train()
            optimizer.zero_grad(set_to_none=True)
            loss = F.smooth_l1_loss(model(windows), target, beta=1.0)
            if not torch.isfinite(loss):
                raise FloatingPointError(f"non-finite loss at step {step}")
            loss.backward()
            optimizer.step()
            loss_sum += float(loss.item())
            if step % LOG_EVERY == 0:
                row = {"step": step, "train_loss_mean_last_1000_steps": loss_sum / LOG_EVERY,
                       "latest_batch_train_loss": float(loss.item())}
                with history_path.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(row) + "\n")
                loss_sum = 0.0
                write_json(progress_path, {
                    "schema": "DL1018_GRU15_C5_FULL72_PROGRESS_V1", "status": "RUNNING",
                    "completed_steps": step, "target_steps": STEPS,
                    "latest_logged_loss": row["latest_batch_train_loss"],
                    "train_loss_mean_last_1000_steps": row["train_loss_mean_last_1000_steps"],
                    "updated_utc": datetime.now(timezone.utc).isoformat(),
                    "plant_called": False, "TEST48_read": False,
                })
                print(json.dumps(row), flush=True)
    except Exception as error:
        write_json(progress_path, {
            "schema": "DL1018_GRU15_C5_FULL72_PROGRESS_V1", "status": "FAILED",
            "target_steps": STEPS, "error": f"{type(error).__name__}: {error}",
            "plant_called": False, "TEST48_read": False,
        })
        raise

    model.eval()
    state = model.state_dict()
    checkpoint_path = OUTPUT_DIR / "final_step_60000.pt"
    atomic_torch_save(checkpoint_path, {
        **config, "status": "PASS", "step": STEPS, "state_dict": state,
        "input_mean": torch.as_tensor(mean.copy()), "input_std": torch.as_tensor(std.copy()),
        "target_rms": torch.as_tensor(target_rms.copy()),
    })
    normalizer_path = OUTPUT_DIR / "normalizer.npz"
    np.savez_compressed(normalizer_path, input_mean=mean, input_std=std, target_rms=target_rms)
    weights_path = OUTPUT_DIR / "gru15_attitude_weights_v1.mat"
    savemat(weights_path, {
        "input_mean": mean.reshape(1, -1), "input_std": std.reshape(1, -1),
        "target_rms": target_rms.reshape(1, -1),
        "gru_weight_ih": state["gru.weight_ih_l0"].cpu().numpy().astype(np.float64),
        "gru_weight_hh": state["gru.weight_hh_l0"].cpu().numpy().astype(np.float64),
        "gru_bias_ih": state["gru.bias_ih_l0"].cpu().numpy().astype(np.float64),
        "gru_bias_hh": state["gru.bias_hh_l0"].cpu().numpy().astype(np.float64),
        "head_weight": state["head.weight"].cpu().numpy().astype(np.float64),
        "head_bias": state["head.bias"].cpu().numpy().astype(np.float64),
    }, do_compression=True, oned_as="row")
    fixture_window = make_windows(padded, torch.tensor([0], device=device), torch.tensor([100], device=device))
    with torch.inference_mode():
        raw_output = model(fixture_window).cpu().numpy()[0] * target_rms
    parity_path = OUTPUT_DIR / "parity_vector_v1.mat"
    savemat(parity_path, {
        "input_normalized_window": fixture_window.cpu().numpy()[0].astype(np.float64),
        "expected_model_output_raw_rad_s2": raw_output.astype(np.float64),
        "expected_runtime_output_clipped_rad_s2": np.clip(raw_output, -D_MAX, D_MAX).astype(np.float64),
        "scene_index_zero_based": np.asarray([[0]], dtype=np.int32),
        "event_index_zero_based": np.asarray([[100]], dtype=np.int32),
    }, do_compression=True, oned_as="row")
    elapsed = time.perf_counter() - started
    config.update({"status": "PASS", "elapsed_seconds": elapsed,
                   "trainer_sha256": sha256_file(Path(__file__).resolve()),
                   "normalizer_sha256": sha256_file(normalizer_path),
                   "weights_sha256": sha256_file(weights_path),
                   "checkpoint_sha256": sha256_file(checkpoint_path)})
    write_json(OUTPUT_DIR / "training_config.json", config)
    write_json(progress_path, {
        "schema": "DL1018_GRU15_C5_FULL72_PROGRESS_V1", "status": "PASS",
        "completed_steps": STEPS, "target_steps": STEPS,
        "updated_utc": datetime.now(timezone.utc).isoformat(),
        "plant_called": False, "TEST48_read": False,
    })
    output_files = [checkpoint_path, normalizer_path, weights_path, parity_path,
                    history_path, progress_path, OUTPUT_DIR / "training_config.json"]
    receipt = {
        "schema": "DL1018_GRU15_C5_TEACHER_FULL72_RECEIPT_V1", "status": "PASS",
        "training_job_count": 1, "optimizer_steps": STEPS,
        "unique_scenes": 72, "unique_training_events": 143928,
        "training_event_presentations": STEPS * BATCH,
        "checkpoint_policy": "final_step_only_at_60000",
        "selection_used": False, "plant_called": False, "TEST48_read": False,
        "B24_arrays_read": False, "dataset_identity": run_identity,
        "input_source_sha256": lock["source_file_sha256"],
        "output_sha256": {path.name: sha256_file(path) for path in output_files},
        "elapsed_seconds": elapsed,
    }
    write_json(OUTPUT_DIR / "run_receipt.json", receipt)
    print(json.dumps({"status": "PASS", "output_dir": str(OUTPUT_DIR),
                      "steps": STEPS, "scenes": 72, "events": 143928,
                      "plant_called": False, "TEST48_read": False}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda:0"), default="auto")
    args = parser.parse_args()
    run_training(args.device)


if __name__ == "__main__":
    main()
