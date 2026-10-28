#!/usr/bin/env python3
"""Prepare and run the single locked GRU32 cosine-LR continuous-state NCMD job."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

import numpy as np
import torch
from scipy.io import savemat
from torch.nn import functional as F

TASK_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = TASK_ROOT.parents[2]
DATA_ROOT = PROJECT_ROOT / "experiments/dl_attitude_replacement_20261026/mlp15_c5_teacher_redistill_v1"
DATASET_PATH = DATA_ROOT / "matched_teacher_data_v1.npz"
MANIFEST_PATH = DATA_ROOT / "DATASET_MANIFEST_v1.json"
TARGET_ROOT = PROJECT_ROOT / "experiments/dl_attitude_replacement_20261026/nominal_command_target_data_v1"
TARGET_PATH = TARGET_ROOT / "nominal_command_target_v1.npz"
TARGET_MANIFEST_PATH = TARGET_ROOT / "MANIFEST_v1.json"
DATA_APPROVAL_PATH = TARGET_ROOT / "ROOT_DATA_PREPARATION_APPROVAL_v1.json"
NUMERIC_REVIEW_PATH = PROJECT_ROOT / "reports/attitude_replacement_progress_20261027/ROOT_NCMD_TARGET_NUMERIC_REVIEW_v1.json"
BASE_TASK_ROOT = PROJECT_ROOT / "experiments/dl_attitude_replacement_20261026/gru15_c5_teacher_full72_v1"
BASE_LOCK_PATH = BASE_TASK_ROOT / "GRU15_C5_TEACHER_FULL72_SOURCE_LOCK_v1.json"
BASE_TRAINER_PATH = BASE_TASK_ROOT / "train_gru15_c5_full72_v1.py"
NORMALIZER_PATH = BASE_TASK_ROOT / "runs/C5_GRU15_FULL72_SEED2026102001/normalizer.npz"
COSINE_TASK_ROOT = PROJECT_ROOT / "experiments/dl_attitude_replacement_20261026/gru_stream_cosine_c5_teacher_v1"
COSINE_LOCK_PATH = COSINE_TASK_ROOT / "GRU_STREAM_COSINE_C5_TEACHER_SOURCE_LOCK_v1.json"
COSINE_TRAINER_PATH = COSINE_TASK_ROOT / "train_gru_stream_cosine_c5_teacher_v1.py"
SCREEN_ROOT = PROJECT_ROOT / "experiments/dl_attitude_replacement_20261026/architecture_screen_v1"
MODEL_SOURCE_PATH = SCREEN_ROOT / "screen_attitude_architectures_v1.py"
LOCK_PATH = TASK_ROOT / "GRU_STREAM_NCMD_SOURCE_LOCK_v1.json"
RELEASE_PATH = TASK_ROOT / "GRU_STREAM_NCMD_TRAINING_RELEASE0_v1.json"
TASKBOOK_PATH = TASK_ROOT.parent / "luna_xhigh_dispatch_20261027_v1/ROOT_GRU_NCMD_TRAINING_TASKBOOK_v1.md"
COMMAND_PATH = TASK_ROOT / "ACTUAL_REPRODUCIBLE_COMMAND_v1.md"
OUTPUT_DIR = TASK_ROOT / "runs/GRU32_STREAM72_NCMD_S2026102001"
EXPECTED_INITIAL_STATE_DICT_SHA256 = "82d952ce8f150388015bc2776b8acceb9c9da59814470eb036ec9ca99420e06e"
LR_START, LR_END = 1e-3, 1e-5

SEED, STEPS, BATCH, TBPTT, INPUT_DIM, HIDDEN, OUTPUT_DIM = 2026102001, 60000, 4, 128, 13, 32, 3
EVENTS_PER_SCENE, SCENES, LOG_EVERY = 1999, 72, 1000
EXPECTED_SPLITS = {"TRAIN_C5_24": 24, "C5_VAL48": 48}
FEATURE_ORDER = [
    "wrapped_attitude_error_euler_rad_x3", "body_rate_rad_s_x3",
    "nominal_bs_body_torque_Nm_x3", "morph_command_x4",
]
FORBIDDEN_INPUTS = [
    "Jhat", "Jdot_hat", "inertia or mass properties", "Plant truth",
    "RBF weights or hidden state", "observer", "physical feedforward",
]
TARGET_CONTRACT = "nominal requested-command port residual; exact-DMAX-clipped float32, post-DMAX/pre-beta; rad/s^2; not RBF output supervision"
TEST_TOKEN = re.compile(r"test", re.IGNORECASE)
STATE_SHAPES = {
    "gru.weight_ih_l0": (3 * HIDDEN, INPUT_DIM),
    "gru.weight_hh_l0": (3 * HIDDEN, HIDDEN),
    "gru.bias_ih_l0": (3 * HIDDEN,),
    "gru.bias_hh_l0": (3 * HIDDEN,),
    "head.weight": (OUTPUT_DIM, HIDDEN),
    "head.bias": (OUTPUT_DIM,),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_array(array: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def initialization_identity(model: torch.nn.Module) -> dict[str, Any]:
    per_parameter: dict[str, str] = {}
    combined = hashlib.sha256()
    for name, tensor in sorted(model.state_dict().items()):
        array = tensor.detach().cpu().contiguous().numpy()
        per_parameter[name] = sha256_array(array)
        combined.update(name.encode("utf-8") + b"\0")
        combined.update(str(array.dtype).encode("ascii") + b"\0")
        combined.update(json.dumps(list(array.shape), separators=(",", ":")).encode("ascii") + b"\0")
        combined.update(array.tobytes())
    return {"state_dict_sha256": combined.hexdigest(), "parameter_sha256": per_parameter}


def write_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def reject_test_path(path: Path, label: str) -> None:
    if TEST_TOKEN.search(str(path)):
        raise ValueError(f"{label} path contains TEST: {path}")


def require_root_release(lock: dict[str, Any], release: dict[str, Any], lock_hash: str) -> None:
    gate = lock.get("training_release", {})
    if (lock.get("status") != "APPROVED_FOR_TRAINING"
            or gate.get("approved") is not True or gate.get("authorized_jobs") != 1
            or not gate.get("approved_by") or not gate.get("approval_reference")
            or release.get("status") != "APPROVED_FOR_TRAINING"
            or release.get("approved") is not True or release.get("authorized_jobs") != 1
            or not release.get("approved_by") or not release.get("approval_reference")
            or release.get("source_lock_sha256") != lock_hash):
        raise PermissionError("source lock/release0 are pending root review; training is not released")


def validate_feature_contract(feature_order: list[str], lock: dict[str, Any]) -> None:
    contract = lock.get("feature_contract", {})
    if feature_order != FEATURE_ORDER or contract.get("allowed_feature_groups") != FEATURE_ORDER:
        raise ValueError("input feature order is not the frozen 13-D whitelist")
    if contract.get("input_dim") != INPUT_DIM or contract.get("prohibited_inputs") != FORBIDDEN_INPUTS:
        raise ValueError("source lock does not bind the complete input allow/deny contract")
    names = " ".join(feature_order).lower()
    if any(token in names for token in ("jhat", "jdot", "inertia", "plant", "observer", "feedforward")):
        raise ValueError("prohibited input appears in feature names")


def load_and_verify_lock(*, require_release: bool) -> dict[str, Any]:
    reject_test_path(DATASET_PATH, "dataset")
    reject_test_path(MANIFEST_PATH, "manifest")
    reject_test_path(TARGET_PATH, "target dataset")
    reject_test_path(TARGET_MANIFEST_PATH, "target manifest")
    reject_test_path(NORMALIZER_PATH, "normalizer")
    reject_test_path(OUTPUT_DIR, "output")
    lock_bytes = LOCK_PATH.read_bytes()
    lock = json.loads(lock_bytes)
    if lock.get("schema") != "DL1018_GRU32_STREAM72_NCMD_SOURCE_LOCK_V1":
        raise ValueError("unexpected GRU32 NCMD stream source-lock schema")
    validate_feature_contract(FEATURE_ORDER, lock)
    if lock.get("training_contract", {}).get("learning_rate_schedule") != learning_rate_schedule_contract():
        raise ValueError("source lock does not match the fixed cosine learning-rate schedule")
    lock_hash = hashlib.sha256(lock_bytes).hexdigest()
    release = json.loads(RELEASE_PATH.read_text(encoding="utf-8"))
    if release.get("schema") != "DL1018_GRU32_STREAM72_NCMD_TRAINING_RELEASE_V1":
        raise ValueError("unexpected training-release schema")
    if release.get("source_lock_sha256") != lock_hash:
        raise ValueError("release0 does not identify the current source lock")
    runtime = lock.get("runtime_versions", {})
    actual_runtime = {"python": sys.version.split()[0], "numpy": np.__version__, "torch": str(torch.__version__)}
    if runtime != actual_runtime:
        raise RuntimeError(f"Python/NumPy/PyTorch versions differ from source lock: {actual_runtime}")
    if require_release:
        require_root_release(lock, release, lock_hash)
    elif lock.get("status") not in {"PREPARED_PENDING_ROOT_REVIEW", "APPROVED_FOR_TRAINING"}:
        raise ValueError("source lock has an unrecognized status")

    for relative, expected in lock.get("source_file_sha256", {}).items():
        source_path = PROJECT_ROOT / Path(relative)
        reject_test_path(source_path, "source")
        if not source_path.is_file() or sha256_file(source_path) != expected:
            raise ValueError(f"locked source hash mismatch: {relative}")
    references = lock["references"]
    for key, path in (("base_source_lock", BASE_LOCK_PATH),
                      ("cosine_source_lock", COSINE_LOCK_PATH),
                      ("feature_dataset", DATASET_PATH), ("feature_manifest", MANIFEST_PATH),
                      ("target_dataset", TARGET_PATH), ("target_manifest", TARGET_MANIFEST_PATH),
                      ("reused_normalizer", NORMALIZER_PATH)):
        if not path.is_file() or sha256_file(path) != references[key]["sha256"]:
            raise ValueError(f"locked {key} hash mismatch: {path}")
    cosine_reference = json.loads(COSINE_LOCK_PATH.read_text(encoding="utf-8"))
    if (cosine_reference.get("initialization", {}).get("state_dict_sha256") != EXPECTED_INITIAL_STATE_DICT_SHA256
            or lock.get("initialization", {}).get("state_dict_sha256") != EXPECTED_INITIAL_STATE_DICT_SHA256):
        raise ValueError("NCMD initial state_dict does not match the cosine reference")
    dataset = lock.get("dataset", {})
    if dataset.get("feature_npz_sha256") != sha256_file(DATASET_PATH):
        raise ValueError("feature NPZ SHA-256 differs from stream source lock")
    if dataset.get("feature_manifest_sha256") != sha256_file(MANIFEST_PATH):
        raise ValueError("feature manifest SHA-256 differs from stream source lock")
    if dataset.get("target_npz_sha256") != sha256_file(TARGET_PATH):
        raise ValueError("NCMD target NPZ SHA-256 differs from stream source lock")
    if dataset.get("target_manifest_sha256") != sha256_file(TARGET_MANIFEST_PATH):
        raise ValueError("NCMD target manifest SHA-256 differs from stream source lock")
    if lock.get("normalizer", {}).get("sha256") != sha256_file(NORMALIZER_PATH):
        raise ValueError("reused GRU15 full72 normalizer SHA-256 differs from source lock")
    relative_trainer = Path(__file__).resolve().relative_to(PROJECT_ROOT).as_posix()
    if lock["source_file_sha256"].get(relative_trainer) != sha256_file(Path(__file__).resolve()):
        raise ValueError("trainer SHA-256 differs from source lock")
    return lock


def _project_relative(source_path: str) -> str:
    path = Path(source_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve(strict=False).relative_to(PROJECT_ROOT).as_posix()


def validate_manifest(lock: dict[str, Any]) -> list[str]:
    feature_manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    target_manifest = json.loads(TARGET_MANIFEST_PATH.read_text(encoding="utf-8"))
    dataset = lock["dataset"]
    if (feature_manifest.get("schema") != "DL1018_MLP15_MATCHED_B24_C5_24_C5_VAL48_DATASET_V1"
            or feature_manifest.get("status") != "PASS_OFFLINE_EXTRACTION"
            or feature_manifest.get("TEST_accessed") is not False
            or feature_manifest.get("plant_truth_read") is not False
            or feature_manifest.get("inertia_config_read") is not False
            or dataset.get("feature_inertia_config_read") is not False
            or feature_manifest.get("dataset_sha256") != dataset["feature_npz_sha256"]):
        raise ValueError("feature source manifest no longer matches the locked C5 feature source")
    validate_feature_contract(feature_manifest.get("feature_order", []), lock)
    if _project_relative(feature_manifest.get("dataset_path", "")) != DATASET_PATH.resolve().relative_to(PROJECT_ROOT).as_posix():
        raise ValueError("feature manifest points to a different source NPZ")
    if (target_manifest.get("schema") != "DL1018_NOMINAL_COMMAND_TARGET_DATA_V1"
            or target_manifest.get("status") != "PASS_OFFLINE_C5_LABEL_PREPARATION"
            or target_manifest.get("training_started") is not False
            or target_manifest.get("Plant_called") is not False
            or target_manifest.get("TEST_read") is not False
            or target_manifest.get("source_npz", {}).get("sha256") != dataset["feature_npz_sha256"]
            or target_manifest.get("outputs", {}).get("target_npz_sha256") != dataset["target_npz_sha256"]
            or target_manifest.get("target_contract", {}).get("name") != "nominal requested-command port residual"
            or target_manifest.get("target_contract", {}).get("stored_training_dtype") != "float32"):
        raise ValueError("target manifest does not identify the approved clipped NCMD labels")
    split_roles = target_manifest.get("split_role_interpretation", {})
    if (split_roles.get("TRAIN_C5_24", {}).get("actual_scene_id_prefix") != "DL1018_DEV_"
            or split_roles.get("C5_VAL48_AS_DEV_TRAIN", {}).get("actual_scene_id_prefix") != "DL1018_VAL_"
            or split_roles.get("combined_72") != "The target package is DEV24+VAL48 development data, with no held-out generalization cohort."):
        raise ValueError("NCMD split-role alias note is missing or inconsistent")

    selected_rows: list[dict[str, Any]] = []
    scene_ids: list[str] = []
    for split, expected_count in EXPECTED_SPLITS.items():
        split_rows = [row for row in feature_manifest.get("rows", []) if row.get("split") == split]
        if len(split_rows) != expected_count:
            raise ValueError(f"unexpected {split} scene count: {len(split_rows)}")
        for row in split_rows:
            scene_id = row.get("scene_id", "")
            if (not scene_id or TEST_TOKEN.search(scene_id)
                    or row.get("event_count") != EVENTS_PER_SCENE
                    or row.get("feature_shape") != [EVENTS_PER_SCENE, INPUT_DIM]
                    or row.get("feature_finite") is not True):
                raise ValueError(f"invalid C5 feature source row: {scene_id}")
        selected_rows.extend(split_rows)
        scene_ids.extend(row["scene_id"] for row in split_rows)
    if len(scene_ids) != SCENES or len(set(scene_ids)) != SCENES:
        raise ValueError("C5 development scene IDs are not unique 72-scene identity")
    if scene_ids != lock.get("scene_ids_in_training_order"):
        raise ValueError("C5 feature scene order differs from source lock")
    ids_hash = hashlib.sha256(("\n".join(scene_ids) + "\n").encode("utf-8")).hexdigest()
    if ids_hash != lock.get("ordered_scene_ids_sha256"):
        raise ValueError("ordered C5 scene-ID digest differs from source lock")

    source_fields = ("scene_id", "raw_sha256", "status_sha256", "run_start_sha256",
                     "scene_identity_sha256", "event_count", "feature_shape", "status_trace_audit_state")
    expected_sources = []
    for row in selected_rows:
        source = {field: row.get(field) for field in source_fields}
        source["source_split"] = row["split"]
        for kind in ("raw", "status", "run_start"):
            source[f"{kind}_path"] = _project_relative(row[f"{kind}_path"])
        expected_sources.append(source)
    if expected_sources != lock.get("scene_sources"):
        raise ValueError("per-scene C5 raw/status identity/order differs from source lock")

    target_ids = []
    for split in ("TRAIN_C5_24", "C5_VAL48_AS_DEV_TRAIN"):
        target_ids.extend(target_manifest["splits"][split]["scene_ids"])
    if target_ids != scene_ids:
        raise ValueError("NCMD target manifest IDs/order differ from the C5 feature source")
    return scene_ids


def load_c5_training_arrays(lock: dict[str, Any], expected_ids: list[str]) -> tuple[np.ndarray, np.ndarray]:
    # Source NPZ access is limited to C5 X/IDs; target NPZ access is limited to clipped float32 Y/IDs.
    with np.load(DATASET_PATH, allow_pickle=False) as archive:
        train_x = np.asarray(archive["c5_train_x"], dtype=np.float32)
        train_ids = np.asarray(archive["c5_train_scene_ids"]).astype(str).tolist()
        dev_x = np.asarray(archive["c5_val_x"], dtype=np.float32)
        dev_ids = np.asarray(archive["c5_val_scene_ids"]).astype(str).tolist()
    with np.load(TARGET_PATH, allow_pickle=False) as archive:
        train_y = np.asarray(archive["c5_train_y_clipped_float32"])
        target_train_ids = np.asarray(archive["c5_train_scene_ids"]).astype(str).tolist()
        dev_y = np.asarray(archive["c5_val_y_clipped_float32"])
        target_dev_ids = np.asarray(archive["c5_val_scene_ids"]).astype(str).tolist()
    if train_ids + dev_ids != expected_ids or target_train_ids + target_dev_ids != expected_ids:
        raise ValueError("C5 feature/NCMD target archive scene IDs/order differ from frozen manifest")
    feature_arrays = {"c5_train_x": train_x, "c5_val_x": dev_x}
    target_arrays = {"c5_train_y_clipped_float32": train_y, "c5_val_y_clipped_float32": dev_y}
    identity = lock["dataset"]
    for key, array in feature_arrays.items():
        if sha256_array(array) != identity["feature_array_sha256"][key]:
            raise ValueError(f"C5 feature array content hash differs from source lock: {key}")
    for key, array in target_arrays.items():
        if sha256_array(array) != identity["target_array_sha256"][key]:
            raise ValueError(f"clipped NCMD target array content hash differs from source lock: {key}")
    if (train_x.shape != (24, EVENTS_PER_SCENE, INPUT_DIM)
            or dev_x.shape != (48, EVENTS_PER_SCENE, INPUT_DIM)
            or train_y.shape != (24, EVENTS_PER_SCENE, OUTPUT_DIM)
            or dev_y.shape != (48, EVENTS_PER_SCENE, OUTPUT_DIM)
            or not all(array.dtype == np.float32 and np.isfinite(array).all()
                       for array in (*feature_arrays.values(), *target_arrays.values()))):
        raise ValueError("C5 X or clipped NCMD Y shape, dtype, or finite-value check failed")
    x = np.concatenate((train_x, dev_x), axis=0)
    y = np.concatenate((train_y, dev_y), axis=0)
    if (x.shape != (SCENES, EVENTS_PER_SCENE, INPUT_DIM)
            or y.shape != (SCENES, EVENTS_PER_SCENE, OUTPUT_DIM)
            or sha256_array(x) != identity["full72_x_sha256"]
            or sha256_array(y) != identity["full72_clipped_y_sha256"]):
        raise ValueError("combined C5 feature/NCMD target identity or shape mismatch")
    return x, y


def load_reused_normalizer(lock: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if sha256_file(NORMALIZER_PATH) != lock["normalizer"]["sha256"]:
        raise ValueError("reused normalizer file changed")
    with np.load(NORMALIZER_PATH, allow_pickle=False) as archive:
        mean = np.asarray(archive["input_mean"], dtype=np.float64)
        std = np.asarray(archive["input_std"], dtype=np.float64)
        target_rms = np.asarray(archive["target_rms"], dtype=np.float64)
    if (mean.shape != (INPUT_DIM,) or std.shape != (INPUT_DIM,) or target_rms.shape != (OUTPUT_DIM,)
            or not np.isfinite(np.r_[mean, std, target_rms]).all()
            or np.any(std <= 0) or np.any(target_rms <= 1e-8)):
        raise ValueError("reused GRU15 normalizer has invalid shapes or values")
    for key, array in (("input_mean", mean), ("input_std", std), ("target_rms", target_rms)):
        if sha256_array(array) != lock["normalizer"]["array_sha256"][key]:
            raise ValueError(f"reused normalizer member differs from source lock: {key}")
    return mean, std, target_rms


def load_gru_class():
    sys.path.insert(0, str(SCREEN_ROOT))
    from screen_attitude_architectures_v1 import GRU15
    return GRU15


def stream_forward(model: torch.nn.Module, x: torch.Tensor, hidden: torch.Tensor | None = None,
                   valid_events: int | None = None) -> tuple[torch.Tensor, torch.Tensor]:
    if x.ndim != 3 or x.shape[-1] != INPUT_DIM:
        raise ValueError("stream input must have shape batch,time,13")
    count = x.shape[1] if valid_events is None else valid_events
    if not 1 <= count <= x.shape[1]:
        raise ValueError("valid_events must select a nonempty input prefix")
    sequence, next_hidden = model.gru(x[:, :count, :], hidden)
    return model.head(sequence), next_hidden


def validate_model_shapes(model: torch.nn.Module) -> None:
    state = model.state_dict()
    if set(state) != set(STATE_SHAPES):
        raise ValueError(f"unexpected GRU parameter names: {sorted(state)}")
    for name, shape in STATE_SHAPES.items():
        if tuple(state[name].shape) != shape:
            raise ValueError(f"unexpected GRU parameter shape for {name}: {tuple(state[name].shape)}")


def schedule_accounting(steps: int = STEPS) -> dict[str, int]:
    chunk_sizes = [min(TBPTT, EVENTS_PER_SCENE - start)
                   for start in range(0, EVENTS_PER_SCENE, TBPTT)]
    cohorts_per_epoch = SCENES // BATCH
    steps_per_epoch = cohorts_per_epoch * len(chunk_sizes)
    full_epochs, remaining = divmod(steps, steps_per_epoch)
    full_cohorts, partial_cohort_steps = divmod(remaining, len(chunk_sizes))
    total = full_epochs * SCENES * EVENTS_PER_SCENE
    total += full_cohorts * BATCH * EVENTS_PER_SCENE
    total += sum(BATCH * chunk_sizes[index] for index in range(partial_cohort_steps))
    return {
        "chunks_per_scene": len(chunk_sizes), "steps_per_cohort": len(chunk_sizes),
        "cohorts_per_epoch": cohorts_per_epoch, "steps_per_epoch": steps_per_epoch,
        "full_epochs": full_epochs, "remaining_steps": remaining,
        "full_cohorts_in_partial_epoch": full_cohorts,
        "partial_cohort_steps": partial_cohort_steps, "expected_valid_samples": total,
    }


def cosine_learning_rate(update_index: int) -> float:
    if not 1 <= update_index <= STEPS:
        raise ValueError(f"optimizer update index must be in [1,{STEPS}]")
    phase = math.pi * (update_index - 1) / (STEPS - 1)
    return LR_END + (LR_START - LR_END) * (1.0 + math.cos(phase)) / 2.0


def learning_rate_schedule_contract() -> dict[str, Any]:
    return {
        "kind": "fixed_cosine_per_optimizer_update",
        "formula": "lr(s)=1e-5+(1e-3-1e-5)*(1+cos(pi*(s-1)/59999))/2; s=1..60000",
        "set_before_optimizer_step": True, "first_update_lr": LR_START,
        "last_update_lr": LR_END, "warmup": False, "restarts": False,
    }


def prepare_release0() -> None:
    """Freeze NCMD source/data/model identity with optimizer and Plant releases at zero."""
    if LOCK_PATH.exists() or RELEASE_PATH.exists():
        if not (LOCK_PATH.is_file() and RELEASE_PATH.is_file() and not OUTPUT_DIR.exists()):
            raise FileExistsError("release0 artifacts are incomplete or a training run already exists")
        prior_lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
        prior_release = json.loads(RELEASE_PATH.read_text(encoding="utf-8"))
        if (prior_lock.get("status") != "PREPARED_PENDING_ROOT_REVIEW"
                or prior_lock.get("training_release", {}).get("authorized_jobs") != 0
                or prior_release.get("status") != "RELEASE0_PENDING_ROOT_REVIEW"
                or prior_release.get("authorized_jobs") != 0):
            raise PermissionError("refusing to replace a reviewed or released source lock")

    base = json.loads(BASE_LOCK_PATH.read_text(encoding="utf-8"))
    cosine_reference = json.loads(COSINE_LOCK_PATH.read_text(encoding="utf-8"))
    approval = json.loads(DATA_APPROVAL_PATH.read_text(encoding="utf-8"))
    numeric_review = json.loads(NUMERIC_REVIEW_PATH.read_text(encoding="utf-8"))
    target_manifest = json.loads(TARGET_MANIFEST_PATH.read_text(encoding="utf-8"))
    if (approval.get("status") != "DATA_APPROVED_FOR_NCMD_TRAINER_PREPARATION_ONLY"
            or approval.get("formal_training_jobs_authorized") != 0
            or approval.get("target_npz_sha256") != sha256_file(TARGET_PATH)
            or approval.get("manifest_sha256") != sha256_file(TARGET_MANIFEST_PATH)
            or approval.get("TEST_read") is not False):
        raise PermissionError("root data approval does not match the current NCMD artifact or only-preparation scope")
    if (numeric_review.get("status") != "PASS_ROOT_ALL72_INDEPENDENT_FORWARD_LABEL_REBUILD"
            or numeric_review.get("target_npz_sha256") != sha256_file(TARGET_PATH)
            or numeric_review.get("final_manifest_sha256") != sha256_file(TARGET_MANIFEST_PATH)
            or numeric_review.get("optimizer_updates") != 0
            or numeric_review.get("Plant_calls") != 0
            or numeric_review.get("TEST_read") is not False):
        raise ValueError("independent all72 NCMD target review does not match current artifacts")
    if cosine_reference.get("initialization", {}).get("state_dict_sha256") != EXPECTED_INITIAL_STATE_DICT_SHA256:
        raise ValueError("cosine reference does not carry the taskbook's approved initial state_dict")
    if (target_manifest.get("outputs", {}).get("target_npz_sha256") != sha256_file(TARGET_PATH)
            or target_manifest.get("source_npz", {}).get("sha256") != sha256_file(DATASET_PATH)):
        raise ValueError("approved target manifest does not bind the selected feature and target files")

    base_data = base["dataset"]
    source_manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    scene_ids = list(cosine_reference["scene_ids_in_training_order"])
    feature_rows = [row for split in EXPECTED_SPLITS for row in source_manifest["rows"] if row.get("split") == split]
    source_fields = ("scene_id", "raw_sha256", "status_sha256", "run_start_sha256",
                     "scene_identity_sha256", "event_count", "feature_shape", "status_trace_audit_state")
    scene_sources = []
    for row in feature_rows:
        source = {field: row.get(field) for field in source_fields}
        source["source_split"] = row["split"]
        for kind in ("raw", "status", "run_start"):
            source[f"{kind}_path"] = _project_relative(row[f"{kind}_path"])
        scene_sources.append(source)
    if [row["scene_id"] for row in feature_rows] != scene_ids:
        raise ValueError("feature manifest order differs from cosine training source order")

    with np.load(DATASET_PATH, allow_pickle=False) as archive:
        train_x = np.asarray(archive["c5_train_x"], dtype=np.float32)
        train_ids = np.asarray(archive["c5_train_scene_ids"]).astype(str).tolist()
        val_x = np.asarray(archive["c5_val_x"], dtype=np.float32)
        val_ids = np.asarray(archive["c5_val_scene_ids"]).astype(str).tolist()
    with np.load(TARGET_PATH, allow_pickle=False) as archive:
        train_y = np.asarray(archive["c5_train_y_clipped_float32"])
        target_train_ids = np.asarray(archive["c5_train_scene_ids"]).astype(str).tolist()
        val_y = np.asarray(archive["c5_val_y_clipped_float32"])
        target_val_ids = np.asarray(archive["c5_val_scene_ids"]).astype(str).tolist()
    if train_ids + val_ids != scene_ids or target_train_ids + target_val_ids != scene_ids:
        raise ValueError("feature and clipped-NCMD target IDs do not match the locked 72-scene order")
    if any(array.shape != shape or array.dtype != np.float32 or not np.isfinite(array).all()
           for array, shape in ((train_x, (24, EVENTS_PER_SCENE, INPUT_DIM)),
                                (val_x, (48, EVENTS_PER_SCENE, INPUT_DIM)),
                                (train_y, (24, EVENTS_PER_SCENE, OUTPUT_DIM)),
                                (val_y, (48, EVENTS_PER_SCENE, OUTPUT_DIM)))):
        raise ValueError("source X or approved clipped float32 NCMD target has invalid shape/dtype/value")

    with np.load(NORMALIZER_PATH, allow_pickle=False) as archive:
        normalizer_arrays = {
            key: np.asarray(archive[key], dtype=np.float64)
            for key in ("input_mean", "input_std", "target_rms")
        }
    source_paths = [
        TASKBOOK_PATH, COMMAND_PATH, Path(__file__).resolve(), TASK_ROOT / "self_check_gru_stream_ncmd_v1.py",
        BASE_TRAINER_PATH, MODEL_SOURCE_PATH, COSINE_TRAINER_PATH,
        DATA_APPROVAL_PATH, NUMERIC_REVIEW_PATH,
    ]
    source_hashes = {
        path.resolve().relative_to(PROJECT_ROOT).as_posix(): sha256_file(path)
        for path in source_paths
    }
    GRU15 = load_gru_class()
    torch.manual_seed(SEED)
    initial_model = GRU15().cpu()
    validate_model_shapes(initial_model)
    initial_identity = initialization_identity(initial_model)
    if initial_identity["state_dict_sha256"] != EXPECTED_INITIAL_STATE_DICT_SHA256:
        raise ValueError("seeded initial GRU state_dict differs from the approved cosine candidate")

    feature_arrays = {"c5_train_x": train_x, "c5_val_x": val_x}
    target_arrays = {
        "c5_train_y_clipped_float32": train_y,
        "c5_val_y_clipped_float32": val_y,
    }
    full_x = np.concatenate((train_x, val_x), axis=0)
    full_y = np.concatenate((train_y, val_y), axis=0)
    runtime_versions = {"python": sys.version.split()[0], "numpy": np.__version__, "torch": str(torch.__version__)}
    lock = {
        "schema": "DL1018_GRU32_STREAM72_NCMD_SOURCE_LOCK_V1",
        "candidate": "GRU32_STREAM72_NCMD_S2026102001",
        "status": "PREPARED_PENDING_ROOT_REVIEW",
        "source_file_sha256": source_hashes,
        "references": {
            "base_source_lock": {"path": BASE_LOCK_PATH.resolve().relative_to(PROJECT_ROOT).as_posix(), "sha256": sha256_file(BASE_LOCK_PATH)},
            "cosine_source_lock": {"path": COSINE_LOCK_PATH.resolve().relative_to(PROJECT_ROOT).as_posix(), "sha256": sha256_file(COSINE_LOCK_PATH)},
            "feature_dataset": {"path": DATASET_PATH.resolve().relative_to(PROJECT_ROOT).as_posix(), "sha256": sha256_file(DATASET_PATH)},
            "feature_manifest": {"path": MANIFEST_PATH.resolve().relative_to(PROJECT_ROOT).as_posix(), "sha256": sha256_file(MANIFEST_PATH)},
            "target_dataset": {"path": TARGET_PATH.resolve().relative_to(PROJECT_ROOT).as_posix(), "sha256": sha256_file(TARGET_PATH)},
            "target_manifest": {"path": TARGET_MANIFEST_PATH.resolve().relative_to(PROJECT_ROOT).as_posix(), "sha256": sha256_file(TARGET_MANIFEST_PATH)},
            "data_preparation_approval": {"path": DATA_APPROVAL_PATH.resolve().relative_to(PROJECT_ROOT).as_posix(), "sha256": sha256_file(DATA_APPROVAL_PATH)},
            "numeric_target_review": {"path": NUMERIC_REVIEW_PATH.resolve().relative_to(PROJECT_ROOT).as_posix(), "sha256": sha256_file(NUMERIC_REVIEW_PATH)},
            "reused_normalizer": {"path": NORMALIZER_PATH.resolve().relative_to(PROJECT_ROOT).as_posix(), "sha256": sha256_file(NORMALIZER_PATH)},
        },
        "runtime_versions": runtime_versions,
        "dataset": {
            "feature_npz_path": DATASET_PATH.resolve().relative_to(PROJECT_ROOT).as_posix(),
            "feature_npz_sha256": sha256_file(DATASET_PATH),
            "feature_manifest_path": MANIFEST_PATH.resolve().relative_to(PROJECT_ROOT).as_posix(),
            "feature_manifest_sha256": sha256_file(MANIFEST_PATH),
            "feature_inertia_config_read": False,
            "target_npz_path": TARGET_PATH.resolve().relative_to(PROJECT_ROOT).as_posix(),
            "target_npz_sha256": sha256_file(TARGET_PATH),
            "target_manifest_path": TARGET_MANIFEST_PATH.resolve().relative_to(PROJECT_ROOT).as_posix(),
            "target_manifest_sha256": sha256_file(TARGET_MANIFEST_PATH),
            "supervision_source": "NOMINAL_COMMAND_RESIDUAL; clipped float32 target members only; not RBF output supervision",
            "target_contract": TARGET_CONTRACT,
            "target_member_keys": list(target_arrays),
            "feature_member_keys": list(feature_arrays),
            "feature_array_sha256": {key: sha256_array(value) for key, value in feature_arrays.items()},
            "target_array_sha256": {key: sha256_array(value) for key, value in target_arrays.items()},
            "feature_array_shapes": {key: list(value.shape) for key, value in feature_arrays.items()},
            "target_array_shapes": {key: list(value.shape) for key, value in target_arrays.items()},
            "feature_array_dtypes": {key: str(value.dtype) for key, value in feature_arrays.items()},
            "target_array_dtypes": {key: str(value.dtype) for key, value in target_arrays.items()},
            "full72_x_sha256": sha256_array(full_x),
            "full72_clipped_y_sha256": sha256_array(full_y),
            "scenes": SCENES, "events_per_scene": EVENTS_PER_SCENE,
            "unique_training_events": SCENES * EVENTS_PER_SCENE,
            "original_source_splits": {"DEV": 24, "VAL": 48},
            "internal_array_aliases": {"TRAIN_C5_24": "DEV24", "C5_VAL48_AS_DEV_TRAIN": "VAL48"},
            "independent_validation": False,
            "B24_values_read": False, "old_C5_Y_values_read": False,
            "unclipped_target_members_read": False,
        },
        "feature_contract": base["feature_contract"],
        "normalizer": {
            "source_path": NORMALIZER_PATH.resolve().relative_to(PROJECT_ROOT).as_posix(),
            "source_candidate": "C5_GRU15_FULL72_SEED2026102001",
            "sha256": sha256_file(NORMALIZER_PATH),
            "array_sha256": {key: sha256_array(value) for key, value in normalizer_arrays.items()},
            "fitted_splits": ["DEV24", "VAL48"], "refit_for_stream_candidate": False,
        },
        "initialization": {
            "seed": SEED, "construction": "torch.manual_seed(seed), CPU GRU15 construction, then move to cuda:0",
            "state_dict_sha256": initial_identity["state_dict_sha256"],
            "parameter_sha256": initial_identity["parameter_sha256"],
            "reference_candidate": cosine_reference["candidate"],
            "reference_source_lock_sha256": sha256_file(COSINE_LOCK_PATH),
        },
        "scene_ids_in_training_order": scene_ids,
        "ordered_scene_ids_sha256": hashlib.sha256(("\n".join(scene_ids) + "\n").encode("utf-8")).hexdigest(),
        "scene_sources": scene_sources,
        "training_contract": {
            **cosine_reference["training_contract"],
            "supervision_source": "NOMINAL_COMMAND_RESIDUAL",
            "plant_called": False, "TEST48_read": False, "B24_values_read": False,
        },
        "data_read_flags": {
            "C5_features_and_approved_clipped_NCMD_targets_only": True,
            "B24_values_read": False, "old_C5_Y_values_read": False,
            "unclipped_target_members_read": False, "TEST48_read": False,
            "J_or_Jdot_read": False,
        },
        "training_release": {"approved": False, "authorized_jobs": 0, "approved_by": None, "approval_reference": None},
        "plant_calls_authorized": 0,
        "claims_prohibited": ["generalization", "independent validation passed", "paper passed"],
    }
    lock_path_tmp = LOCK_PATH.with_suffix(LOCK_PATH.suffix + ".tmp")
    lock_path_tmp.write_text(json.dumps(lock, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lock_path_tmp.replace(LOCK_PATH)
    release = {
        "schema": "DL1018_GRU32_STREAM72_NCMD_TRAINING_RELEASE_V1",
        "status": "RELEASE0_PENDING_ROOT_REVIEW", "approved": False,
        "authorized_jobs": 0, "plant_calls_authorized": 0,
        "source_lock_path": LOCK_PATH.resolve().relative_to(PROJECT_ROOT).as_posix(),
        "source_lock_sha256": sha256_file(LOCK_PATH),
        "formal_optimizer_jobs_started": 0, "formal_optimizer_steps_started": 0,
        "TEST48_read": False, "B24_values_read": False, "old_C5_Y_values_read": False,
        "unclipped_target_members_read": False, "Plant_called": False,
        "approved_by": None, "approval_reference": None,
    }
    write_json(RELEASE_PATH, release)
    print(json.dumps({"status": release["status"], "source_lock": str(LOCK_PATH),
                      "source_lock_sha256": release["source_lock_sha256"],
                      "candidate": "GRU32_STREAM72_NCMD_S2026102001",
                      "supervision_source": "NOMINAL_COMMAND_RESIDUAL",
                      "authorized_jobs": 0, "plant_calls_authorized": 0}))


def self_check() -> None:
    """Verify identities, cosine schedule, and stream semantics without an optimizer step."""
    lock = load_and_verify_lock(require_release=False)
    if lock.get("training_release", {}).get("authorized_jobs") not in (0, 1):
        raise AssertionError("invalid job authorization count")
    scene_ids = validate_manifest(lock)
    x, y = load_c5_training_arrays(lock, scene_ids)
    mean, std, target_rms = load_reused_normalizer(lock)
    assert x.shape == (SCENES, EVENTS_PER_SCENE, INPUT_DIM)
    assert y.shape == (SCENES, EVENTS_PER_SCENE, OUTPUT_DIM)
    assert mean.shape == std.shape == (INPUT_DIM,) and target_rms.shape == (OUTPUT_DIM,)
    chunk_sizes = [min(TBPTT, EVENTS_PER_SCENE - start)
                   for start in range(0, EVENTS_PER_SCENE, TBPTT)]
    assert chunk_sizes == [TBPTT] * 15 + [79]
    assert sum(chunk_sizes) == EVENTS_PER_SCENE
    assert sum(BATCH * count for count in chunk_sizes) == 7996
    assert schedule_accounting()["expected_valid_samples"] == 29_985_000

    try:
        require_root_release(
            {"status": "PREPARED_PENDING_ROOT_REVIEW", "training_release": {"approved": False}},
            {"status": "RELEASE0_PENDING_ROOT_REVIEW", "approved": False}, "pending-lock",
        )
    except PermissionError:
        pass
    else:
        raise AssertionError("synthetic pending release must refuse formal training")
    try:
        reject_test_path(Path("synthetic/TEST48/forbidden.npz"), "self-check")
    except ValueError:
        pass
    else:
        raise AssertionError("TEST path was not rejected")

    GRU15 = load_gru_class()
    torch.manual_seed(SEED)
    model = GRU15().cpu().eval()
    validate_model_shapes(model)
    assert initialization_identity(model) == {
        "state_dict_sha256": lock["initialization"]["state_dict_sha256"],
        "parameter_sha256": lock["initialization"]["parameter_sha256"],
    }
    assert lock["initialization"]["state_dict_sha256"] == EXPECTED_INITIAL_STATE_DICT_SHA256
    expected_mid = LR_END + (LR_START - LR_END) * (1 + math.cos(math.pi * (30000 - 1) / (STEPS - 1))) / 2
    assert math.isclose(cosine_learning_rate(1), LR_START, rel_tol=0.0, abs_tol=1e-15)
    assert math.isclose(cosine_learning_rate(30000), expected_mid, rel_tol=0.0, abs_tol=1e-15)
    assert math.isclose(cosine_learning_rate(STEPS), LR_END, rel_tol=0.0, abs_tol=1e-15)
    lr_samples = [cosine_learning_rate(s) for s in range(1, STEPS + 1)]
    assert all(a >= b for a, b in zip(lr_samples, lr_samples[1:]))
    features = torch.linspace(-1.0, 1.0, 2 * 260 * INPUT_DIM, dtype=torch.float32).reshape(2, 260, INPUT_DIM)
    with torch.inference_mode():
        all_outputs, all_hidden = stream_forward(model, features)
        hidden = None
        stepped = []
        for t in range(features.shape[1]):
            out, hidden = stream_forward(model, features[:, t:t + 1], hidden)
            stepped.append(out)
        stepped_outputs = torch.cat(stepped, dim=1)
        assert torch.allclose(all_outputs, stepped_outputs, atol=1e-6, rtol=1e-6)
        assert torch.allclose(all_hidden, hidden, atol=1e-6, rtol=1e-6)

        first, first_hidden = stream_forward(model, features[:1, :199])
        again, again_hidden = stream_forward(model, features[:1, :199])
        assert torch.equal(first, again) and torch.equal(first_hidden, again_hidden)

        cut = 100
        altered = features.clone()
        altered[:, cut:, :] += 100.0
        changed_outputs, _ = stream_forward(model, altered)
        assert torch.equal(all_outputs[:, :cut], changed_outputs[:, :cut])

        valid = 79
        padded = F.pad(features[:, :valid], (0, 0, 0, 128 - valid))
        unpadded_outputs, unpadded_hidden = stream_forward(model, features[:, :valid])
        padded_outputs, padded_hidden = stream_forward(model, padded, valid_events=valid)
        assert torch.equal(unpadded_outputs, padded_outputs)
        assert torch.equal(unpadded_hidden, padded_hidden)

    first_chunk = features[:1, :128].clone().requires_grad_(True)
    second_chunk = features[:1, 128:256].clone().requires_grad_(True)
    chunk_model = GRU15().cpu()
    _, carry = stream_forward(chunk_model, first_chunk)
    second_outputs, _ = stream_forward(chunk_model, second_chunk, carry.detach())
    second_outputs.square().mean().backward()
    assert first_chunk.grad is None and second_chunk.grad is not None
    assert all(parameter.grad is not None for parameter in chunk_model.parameters())
    assert OUTPUT_DIR.exists() is False, "self-check must not create a training run directory"
    print("SELF_CHECK=PASS (C5 X/ID + approved clipped NCMD Y identities + byte-identical normalizer + init SHA + cosine LR + GRU stream/reset/future/padding/detach; optimizer.step=0)")


def set_determinism() -> None:
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


def formal_training_command() -> str:
    script = Path(__file__).resolve().relative_to(PROJECT_ROOT).as_posix().replace("/", "\\")
    root = str(PROJECT_ROOT)
    attempt_log = Path("experiments/dl_attitude_replacement_20261026/gru_stream_ncmd_v1/logs/attempt01")
    return "\n".join((
        f"Set-Location '{root}'",
        "$env:MKL_THREADING_LAYER = 'SEQUENTIAL'",
        "$env:OMP_NUM_THREADS = '1'",
        "$env:MKL_NUM_THREADS = '1'",
        "$env:CUBLAS_WORKSPACE_CONFIG = ':4096:8'",
        f"$attemptLog = '{attempt_log.as_posix()}'",
        "New-Item -ItemType Directory -Force -Path $attemptLog | Out-Null",
        f"$script = '{script}'",
        "$pythonCode = \"import os,runpy,sys,numpy,torch,scipy.io; os.environ.pop('KMP_DUPLICATE_LIB_OK',None); sys.argv=[r'$script','--train','--device','cuda:0']; runpy.run_path(sys.argv[0],run_name='__main__')\"",
        "python -u -c $pythonCode 2>&1 | Tee-Object -FilePath (Join-Path $attemptLog 'GRU32_STREAM72_NCMD_S2026102001.stdout.log')",
        "$trainingExitCode = $LASTEXITCODE",
        "exit $trainingExitCode",
    ))


def require_training_environment() -> None:
    expected = {"MKL_THREADING_LAYER": "SEQUENTIAL", "OMP_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1", "CUBLAS_WORKSPACE_CONFIG": ":4096:8"}
    incorrect = {key: os.environ.get(key) for key, value in expected.items()
                 if os.environ.get(key) != value}
    if incorrect:
        raise RuntimeError(f"required PowerShell training environment is missing or changed: {incorrect}")
    if os.environ.get("KMP_DUPLICATE_LIB_OK"):
        raise RuntimeError("KMP_DUPLICATE_LIB_OK must be unset")


def run_training() -> None:
    lock = load_and_verify_lock(require_release=True)
    require_training_environment()
    if OUTPUT_DIR.exists():
        raise FileExistsError(f"single authorized run output already exists: {OUTPUT_DIR}")
    scene_ids = validate_manifest(lock)
    x, y = load_c5_training_arrays(lock, scene_ids)
    mean, std, target_rms = load_reused_normalizer(lock)
    if not torch.cuda.is_available():
        raise RuntimeError("the authorized run is fixed to cuda:0, but CUDA is unavailable")
    if torch.cuda.device_count() < 1:
        raise RuntimeError("cuda:0 is unavailable")
    device = torch.device("cuda:0")

    set_determinism()
    GRU15 = load_gru_class()
    model = GRU15().to(device)
    validate_model_shapes(model)
    if initialization_identity(model) != {
            "state_dict_sha256": lock["initialization"]["state_dict_sha256"],
            "parameter_sha256": lock["initialization"]["parameter_sha256"]}:
        raise ValueError("seeded GRU initialization SHA differs from source lock")
    optimizer = torch.optim.Adam(model.parameters(), lr=LR_START, weight_decay=1e-5)
    x_norm = torch.as_tensor(((x - mean) / std).astype(np.float32), device=device)
    y_norm = torch.as_tensor((y / target_rms).astype(np.float32), device=device)
    rng = np.random.default_rng(SEED)
    lock_hash = sha256_file(LOCK_PATH)
    release_hash = sha256_file(RELEASE_PATH)
    run_identity = {
        "source_lock_sha256": lock_hash, "training_release_sha256": release_hash,
        "base_gru15_source_lock_sha256": lock["references"]["base_source_lock"]["sha256"],
        "cosine_reference_source_lock_sha256": lock["references"]["cosine_source_lock"]["sha256"],
        "feature_npz_sha256": lock["dataset"]["feature_npz_sha256"],
        "feature_manifest_sha256": lock["dataset"]["feature_manifest_sha256"],
        "target_npz_sha256": lock["dataset"]["target_npz_sha256"],
        "target_manifest_sha256": lock["dataset"]["target_manifest_sha256"],
        "supervision_source": "NOMINAL_COMMAND_RESIDUAL; clipped float32 only",
        "reused_normalizer_sha256": lock["normalizer"]["sha256"],
        "selected_normalizer_arrays_sha256": lock["normalizer"]["array_sha256"],
        "train_splits": ["DEV24 (internal TRAIN_C5_24 alias)", "VAL48 (internal C5_VAL48_AS_DEV_TRAIN alias)"],
        "independent_validation": False,
        "scene_ids_in_training_order": scene_ids, "ordered_scene_ids_sha256": lock["ordered_scene_ids_sha256"],
        "events_per_scene": EVENTS_PER_SCENE, "unique_training_events": SCENES * EVENTS_PER_SCENE,
        "feature_contract": lock["feature_contract"], "target_contract": TARGET_CONTRACT,
        "TEST48_read": False, "B24_values_read": False, "old_C5_Y_values_read": False,
        "unclipped_target_members_read": False, "Plant_called": False,
    }
    config = {
        "schema": "DL1018_GRU32_STREAM72_NCMD_TRAINING_CONFIG_V1", "status": "RUNNING",
        "candidate": "GRU32_STREAM72_NCMD_S2026102001", "architecture": "single-layer GRU(13,32)+Linear(32,3)",
        "input_dim": INPUT_DIM, "hidden_size": HIDDEN, "output_dim": OUTPUT_DIM,
        "input_events_per_forward": 1, "inference_hidden_reset": "zero at scene start; carry every 10 ms event",
        "seed": SEED, "optimizer_steps": STEPS, "batch_scenes": BATCH, "tbptt_events": TBPTT,
        "optimizer": "Adam", "learning_rate_schedule": learning_rate_schedule_contract(), "weight_decay": 1e-5,
        "learning_rate_ledger": "training_history.jsonl records the applied rate on every optimizer update",
        "loss": "SmoothL1(beta=1.0)", "gradient_clip": None,
        "checkpoint_policy": "final_step_only_at_60000; no selection or resume",
        "cohort_schedule": "fixed-seed shuffle of 72 scenes, disjoint groups of four; each cohort runs from event 0 to 1998",
        "schedule_accounting": schedule_accounting(),
        "hidden_policy": "carry between chunks; detach at each chunk boundary; reset after cohort scenes end",
        "last_chunk": {"start_event": 1920, "valid_events": 79, "padding_events": 0},
        "normalizer_policy": "copy byte-identical GRU15 full72 normalizer; no refit",
        "supervision_source": "NOMINAL_COMMAND_RESIDUAL; approved clipped float32 labels; not RBF output supervision",
        "model_config": {"layout": "batch,time,feature", "gate_order": "reset,update,new"},
        "dataset_identity": run_identity, "device": str(device), "torch_version": torch.__version__,
        "created_utc": datetime.now(timezone.utc).isoformat(), "Plant_called": False,
        "TEST48_read": False, "B24_values_read": False,
    }
    OUTPUT_DIR.mkdir(parents=True)
    shutil.copy2(NORMALIZER_PATH, OUTPUT_DIR / "normalizer.npz")
    if sha256_file(OUTPUT_DIR / "normalizer.npz") != lock["normalizer"]["sha256"]:
        raise ValueError("copied run normalizer SHA differs from the locked GRU15 full72 normalizer")
    history_path = OUTPUT_DIR / "training_history.jsonl"
    progress_path = OUTPUT_DIR / "training_progress.json"
    write_json(OUTPUT_DIR / "training_config.json", config)
    write_json(progress_path, {
        "schema": "DL1018_GRU32_STREAM72_NCMD_PROGRESS_V1", "status": "RUNNING",
        "completed_steps": 0, "target_steps": STEPS, "cumulative_valid_events": 0,
        "target_valid_samples": schedule_accounting()["expected_valid_samples"],
        "logged_every_steps": LOG_EVERY, "optimizer_step_calls": 0,
        "Plant_called": False, "TEST48_read": False, "B24_values_read": False,
    })
    history_path.write_text("", encoding="utf-8")
    started = time.perf_counter()
    loss_sum, cumulative_valid_events, step = 0.0, 0, 0
    history_stream = history_path.open("a", encoding="utf-8", buffering=1)

    try:
        epoch = 0
        while step < STEPS:
            epoch += 1
            scene_order = rng.permutation(SCENES)
            for first in range(0, SCENES, BATCH):
                cohort = scene_order[first:first + BATCH]
                if len(cohort) != BATCH:
                    raise AssertionError("fixed 72-scene schedule must divide into 4-scene cohorts")
                scene_indices = torch.as_tensor(cohort.copy(), device=device)
                hidden = None
                for offset in range(0, EVENTS_PER_SCENE, TBPTT):
                    if step >= STEPS:
                        break
                    end = min(offset + TBPTT, EVENTS_PER_SCENE)
                    valid = end - offset
                    batch_x = x_norm[scene_indices, offset:end]
                    batch_y = y_norm[scene_indices, offset:end]
                    model.train()
                    optimizer.zero_grad(set_to_none=True)
                    output, next_hidden = stream_forward(model, batch_x, hidden)
                    loss = F.smooth_l1_loss(output, batch_y, beta=1.0)
                    if not torch.isfinite(loss):
                        raise FloatingPointError(f"non-finite loss at step {step + 1}")
                    loss.backward()
                    update_lr = cosine_learning_rate(step + 1)
                    for parameter_group in optimizer.param_groups:
                        parameter_group["lr"] = update_lr
                    optimizer.step()
                    hidden = next_hidden.detach()
                    step += 1
                    valid_events = BATCH * valid
                    cumulative_valid_events += valid_events
                    loss_sum += float(loss.item())
                    row = {
                        "step": step, "epoch": epoch, "cohort_index": first // BATCH + 1,
                        "learning_rate_step": step, "learning_rate": update_lr,
                        "chunk_index": offset // TBPTT + 1, "chunk_start_event": offset,
                        "chunk_end_event_exclusive": end, "train_loss": float(loss.item()),
                        "valid_samples_per_scene": valid, "valid_samples_this_step": valid_events,
                        "valid_events_this_step": valid_events,
                        "cumulative_valid_samples": cumulative_valid_events,
                        "cumulative_valid_events": cumulative_valid_events, "padding_samples_this_step": 0,
                        "padding_events_this_step": 0,
                        "cohort_scene_ids": [scene_ids[int(index)] for index in cohort],
                    }
                    if step % LOG_EVERY == 0:
                        row["train_loss_mean_last_1000_steps"] = loss_sum / LOG_EVERY
                        loss_sum = 0.0
                        write_json(progress_path, {
                            "schema": "DL1018_GRU32_STREAM72_NCMD_PROGRESS_V1", "status": "RUNNING",
                            "completed_steps": step, "target_steps": STEPS,
                            "latest_logged_loss": row["train_loss"],
                            "latest_learning_rate": update_lr,
                            "train_loss_mean_last_1000_steps": row["train_loss_mean_last_1000_steps"],
                            "valid_samples_this_step": valid_events,
                            "valid_events_this_step": valid_events,
                            "cumulative_valid_samples": cumulative_valid_events,
                            "cumulative_valid_events": cumulative_valid_events,
                            "updated_utc": datetime.now(timezone.utc).isoformat(),
                            "Plant_called": False, "TEST48_read": False, "B24_values_read": False,
                        })
                        print(json.dumps(row), flush=True)
                    history_stream.write(json.dumps(row) + "\n")
                    if step % LOG_EVERY == 0:
                        history_stream.flush()
                hidden = None
                if step >= STEPS:
                    break
    except Exception as error:
        write_json(progress_path, {
            "schema": "DL1018_GRU32_STREAM72_NCMD_PROGRESS_V1", "status": "FAILED",
            "completed_steps": step, "target_steps": STEPS,
            "cumulative_valid_events": cumulative_valid_events,
            "cumulative_valid_samples": cumulative_valid_events,
            "error": f"{type(error).__name__}: {error}",
            "Plant_called": False, "TEST48_read": False, "B24_values_read": False,
        })
        raise
    finally:
        history_stream.close()

    if step != STEPS:
        raise AssertionError(f"expected exactly {STEPS} optimizer steps, got {step}")
    if cumulative_valid_events != schedule_accounting()["expected_valid_samples"]:
        raise AssertionError("cumulative valid-sample ledger differs from the locked schedule")
    model.eval()
    state = model.state_dict()
    checkpoint_path = OUTPUT_DIR / "final_step_60000.pt"
    torch.save({
        **config, "status": "PASS", "step": STEPS, "state_dict": state,
        "input_mean": torch.as_tensor(mean.copy()), "input_std": torch.as_tensor(std.copy()),
        "target_rms": torch.as_tensor(target_rms.copy()),
    }, checkpoint_path)
    weights_path = OUTPUT_DIR / "gru_stream_c5_teacher_weights_v1.mat"
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
    with torch.inference_mode():
        fixture = torch.as_tensor(((x[0] - mean) / std).astype(np.float32), device=device).unsqueeze(0)
        fixture_outputs, fixture_hidden = stream_forward(model, fixture)
    parity_path = OUTPUT_DIR / "stream_parity_vector_v1.mat"
    savemat(parity_path, {
        "input_features_raw": x[0].astype(np.float64),
        "expected_output_raw_rad_s2": (fixture_outputs.cpu().numpy()[0] * target_rms).astype(np.float64),
        "expected_hidden_float32": fixture_hidden.cpu().numpy()[0].T.astype(np.float64),
        "scene_id": scene_ids[0], "input_mean": mean.reshape(1, -1),
        "input_std": std.reshape(1, -1), "target_rms": target_rms.reshape(1, -1),
    }, do_compression=True, oned_as="row")

    elapsed = time.perf_counter() - started
    config.update({"status": "PASS", "elapsed_seconds": elapsed,
                   "trainer_sha256": sha256_file(Path(__file__).resolve()),
                   "training_command": formal_training_command()})
    write_json(OUTPUT_DIR / "training_config.json", config)
    write_json(progress_path, {
        "schema": "DL1018_GRU32_STREAM72_NCMD_PROGRESS_V1", "status": "PASS",
        "completed_steps": STEPS, "target_steps": STEPS,
        "cumulative_valid_events": cumulative_valid_events,
        "cumulative_valid_samples": cumulative_valid_events,
        "target_valid_samples": schedule_accounting()["expected_valid_samples"],
        "updated_utc": datetime.now(timezone.utc).isoformat(),
        "final_learning_rate": cosine_learning_rate(STEPS),
        "Plant_called": False, "TEST48_read": False, "B24_values_read": False,
    })
    output_files = [checkpoint_path, weights_path, OUTPUT_DIR / "normalizer.npz", parity_path,
                    history_path, progress_path, OUTPUT_DIR / "training_config.json"]
    receipt = {
        "schema": "DL1018_GRU32_STREAM72_NCMD_RECEIPT_V1", "status": "PASS",
        "training_job_count": 1, "optimizer_steps": STEPS, "unique_scenes": SCENES,
        "unique_training_events": SCENES * EVENTS_PER_SCENE,
        "cumulative_valid_events": cumulative_valid_events,
        "cumulative_valid_samples": cumulative_valid_events,
        "target_valid_samples": schedule_accounting()["expected_valid_samples"],
        "schedule_accounting": schedule_accounting(), "padding_events_counted": 0,
        "tbptt_events": TBPTT, "batch_scenes": BATCH,
        "checkpoint_policy": "final_step_only_at_60000", "selection_used": False,
        "learning_rate_schedule": learning_rate_schedule_contract(),
        "Plant_called": False, "TEST48_read": False, "B24_values_read": False,
        "dataset_identity": run_identity,
        "output_sha256": {path.name: sha256_file(path) for path in output_files},
        "elapsed_seconds": elapsed,
        "training_command": config["training_command"],
    }
    write_json(OUTPUT_DIR / "run_receipt.json", receipt)
    print(json.dumps({"status": "PASS", "output_dir": str(OUTPUT_DIR),
                      "steps": STEPS, "scenes": SCENES, "unique_events": SCENES * EVENTS_PER_SCENE,
                      "cumulative_valid_events": cumulative_valid_events,
                      "Plant_called": False, "TEST48_read": False, "B24_values_read": False}))


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare-release0", action="store_true", help="freeze source/data identity with no training release")
    mode.add_argument("--self-check", action="store_true", help="verify C5 identities and toy stream semantics")
    mode.add_argument("--train", action="store_true", help="run the one authorized 60000-step GPU job")
    parser.add_argument("--device", choices=("cuda:0",), default="cuda:0")
    args = parser.parse_args()
    if args.prepare_release0:
        prepare_release0()
    elif args.self_check:
        self_check()
    else:
        run_training()


if __name__ == "__main__":
    main()
