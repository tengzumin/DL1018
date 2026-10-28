"""Score both frozen final-step B24/C5-24 models on identical C* VAL48 inputs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
SCORER = "experiments/attitude_position_context_probe_20261024/b24_c524_paired_v1/score_b24_c524_final_v1.py"
TRAINER = "experiments/attitude_position_context_probe_20261024/b24_c524_paired_v1/train_cm18_b24_c524_paired_v1.py"
PAIR_READER = "experiments/attitude_position_context_probe_20261024/b24_c524_paired_v1/read_b24_c524_paired_v1.py"
B_READER = "experiments/attitude_cm18_datarepair_20261024/read_cstar_split_v1.py"
NUMPY_MODEL = "experiments/attitude_cm18_a1_20261024/model_cm18_v1.py"
TORCH_MODEL = "experiments/attitude_cm18_a1_20261024/torch_model_cm18_v1.py"
C5_RELABELER = "experiments/attitude_position_context_probe_20261024/c5_val48_cstar_v1/relabel_c5_val48_cstar_v1.m"
B_DATASET = "reports/attitude_cm18_datarepair_20261024/cstar_all816_v1/CSTAR_RELABEL_ALL816_v1.json"
B_DATASET_SHA256 = "421298399aacf2d7f82031f2bdecc39eacacc28196c7b872b925866655d211a6"
NORMALIZER = "experiments/attitude_cm18_datarepair_20261024/training_a1t_v1/normalizer.json"
NORMALIZER_SHA256 = "23e8432f4a1c3f71bfaaa4e3a7b07c4b9f6b0201842e35ba3bcb032ac61fd781"
NORMALIZER_AUDIT = "reports/attitude_cm18_datarepair_20261024/ROOT_CSTAR_ALL816_INDEPENDENT_AUDIT_v1.json"
NORMALIZER_AUDIT_SHA256 = "f8db2f1fa13447db4fd5b91b5b945391f437de56a2d8cf3ee01cab7c59f75a06"
INITIAL_PARAMETERS = "experiments/attitude_cm18_datarepair_20261024/training_a1t_v1/initial_parameters.npz"
INITIAL_PARAMETERS_SHA256 = "1f3a469eeb648345bacf6f6aa3be906e10efebc91e24442914fd32e880439cb2"
CANONICAL_NORMALIZER_SHA256 = "12c864b9c2404235e0ea3f313bb0801a99902eca7cfdfbf43f0d8d584d5d609a"
C5_SOURCE_MANIFEST_SHA256 = "3e72f4726219cfd0e89476c70d24796a06c8f8447d4064cfdc471433a863a501"
C5_CANDIDATE_MANIFEST_SHA256 = "80ef7a37cb0fff237086ccc138772c71494cacd50a916ed2dba4037d4f833494"
OUTPUT_PARENT = "reports/attitude_position_context_probe_20261024/b24_c524_paired_v1/postselection_scores"
BRANCHES = ("B24", "C5_24")
DMAX = (45.0, 45.0, 4.7124)
BETA_RISE_S = 2.2
N_EVENTS = 1999
PLANT_INDEX = tuple(range(11, 20000, 10))
PHASES = {0: "STATIC", 1: "PRE", 2: "EXTEND", 3: "HOLD", 4: "RETRACT", 5: "RECOVERY"}
SOURCE_PATHS = (SCORER, TRAINER, PAIR_READER, B_READER, NUMPY_MODEL, TORCH_MODEL, C5_RELABELER)


def _math_environment() -> None:
    if os.environ.get("KMP_DUPLICATE_LIB_OK"):
        raise RuntimeError("KMP_DUPLICATE_LIB_OK is forbidden")
    os.environ["MKL_THREADING_LAYER"] = "SEQUENTIAL"
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"
    os.environ["OPENBLAS_NUM_THREADS"] = "1"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _repo_path(root: Path, value: str, *, exists: bool = True) -> Path:
    p = Path(value)
    result = (p if p.is_absolute() else root / p).resolve(strict=exists)
    try:
        result.relative_to(root.resolve(strict=True))
    except ValueError as exc:
        raise ValueError(f"path escapes repository: {value}") from exc
    return result


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _pin(root: Path, item: Any, label: str) -> tuple[Path, str]:
    if not isinstance(item, dict) or not isinstance(item.get("path"), str):
        raise ValueError(f"release {label} must contain path and sha256")
    expected = str(item.get("sha256", "")).lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError(f"release {label} SHA256 is malformed")
    path = _repo_path(root, item["path"])
    if _sha256(path) != expected:
        raise ValueError(f"actual {label} SHA256 mismatch: {item['path']}")
    return path, expected


def _load_module(root: Path, relative: str, name: str) -> Any:
    path = _repo_path(root, relative)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load module: {relative}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _verify_sources(root: Path, release: dict[str, Any]) -> dict[str, str]:
    rows = release.get("source_files")
    if not isinstance(rows, list) or len(rows) != len(SOURCE_PATHS):
        raise ValueError("release must pin the seven scorer/model/reader/trainer/relabeler source files")
    actual: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict) or row.get("path") not in SOURCE_PATHS or row["path"] in actual:
            raise ValueError("release source_files contains an unexpected or duplicate path")
        path = _repo_path(root, row["path"])
        digest = _sha256(path)
        if digest != str(row.get("sha256", "")).lower():
            raise ValueError(f"source SHA mismatch: {row['path']}")
        actual[row["path"]] = digest
    if tuple(p for p in SOURCE_PATHS if p not in actual) or set(actual) != set(SOURCE_PATHS):
        raise ValueError("release source_files is incomplete")
    return actual


def _verify_release(root: Path, release_path: Path, release_sha: str) -> tuple[dict[str, Any], dict[str, str]]:
    release_path = release_path.resolve(strict=True)
    try:
        release_path.relative_to(root.resolve(strict=True))
    except ValueError as exc:
        raise ValueError("score release must live inside the repository") from exc
    if _sha256(release_path) != release_sha.lower():
        raise ValueError("score release SHA256 mismatch")
    release = _read_json(release_path)
    if (release.get("schema") != "CM18_B24_C524_FINAL_SCORE_RELEASE_V1"
            or release.get("decision") != "APPROVE_FINAL60000_POSTSELECTION_SCORE"):
        raise ValueError("ROOT release does not approve this fixed post-selection score")
    if release.get("output_parent") != OUTPUT_PARENT:
        raise ValueError("score release output_parent must be the fixed postselection_scores directory")
    normalizer = release.get("canonical_normalizer")
    if not isinstance(normalizer, dict) or normalizer.get("path") != NORMALIZER or normalizer.get("sha256", "").lower() != NORMALIZER_SHA256 or normalizer.get("canonical_sha256", "").lower() != CANONICAL_NORMALIZER_SHA256:
        raise ValueError("score release canonical normalizer identity differs from the frozen A1T normalizer")
    _pin(root, {"path": NORMALIZER, "sha256": NORMALIZER_SHA256}, "canonical normalizer")
    _pin(root, {"path": NORMALIZER_AUDIT, "sha256": NORMALIZER_AUDIT_SHA256}, "normalizer audit")
    _pin(root, {"path": INITIAL_PARAMETERS, "sha256": INITIAL_PARAMETERS_SHA256}, "common initial parameters")
    b_pin = release.get("b_val_dataset_manifest")
    if b_pin != {"path": B_DATASET, "sha256": B_DATASET_SHA256}:
        raise ValueError("score release B VAL manifest must use the fixed B C* ALL816 manifest")
    _pin(root, b_pin, "B VAL dataset manifest")
    c5_pin = release.get("c5_val_manifest")
    c5_path, c5_sha = _pin(root, c5_pin, "C5 VAL C* relabel manifest")
    if not isinstance(release.get("paired_identity"), dict):
        raise ValueError("release lacks common paired training identity")
    sources = _verify_sources(root, release)
    return ({**release, "_release_path": str(release_path), "_release_sha256": release_sha.lower(),
             "_c5_manifest_path": str(c5_path), "_c5_manifest_sha256": c5_sha}, sources)


def _state_hash(state: dict[str, Any]) -> str:
    h = hashlib.sha256()
    for name, tensor in sorted(state.items()):
        array = tensor.detach().cpu().contiguous().numpy()
        h.update(name.encode("utf-8") + b"\0")
        h.update(str(array.dtype).encode("ascii") + b"\0")
        h.update(str(tuple(array.shape)).encode("ascii") + b"\0")
        h.update(array.tobytes(order="C"))
    return h.hexdigest()


def _verify_runs(root: Path, release: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    runs = release.get("runs")
    if not isinstance(runs, dict) or set(runs) != set(BRANCHES):
        raise ValueError("score release must pin exactly B24 and C5_24 terminal runs")
    prepared: dict[str, dict[str, Any]] = {}
    checkpoints: dict[str, dict[str, Any]] = {}
    pair = release["paired_identity"]
    trainer_sha = _sha256(_repo_path(root, TRAINER))
    for branch in BRANCHES:
        entries = runs[branch]
        if not isinstance(entries, dict):
            raise ValueError(f"malformed run pins: {branch}")
        paths = {}
        for key in ("training_release", "receipt", "training_config", "checkpoint"):
            paths[key] = _pin(root, entries.get(key), f"{branch} {key}")[0]
        train_release = _read_json(paths["training_release"])
        receipt = _read_json(paths["receipt"])
        config = _read_json(paths["training_config"])
        checkpoint_pin = entries["checkpoint"]
        train_sources = train_release.get("source_files")
        if not isinstance(train_sources, list):
            raise ValueError(f"{branch} training release lacks source pins")
        train_source_map = {row.get("path"): str(row.get("sha256", "")).lower()
                            for row in train_sources if isinstance(row, dict)}
        receipt_sources = receipt.get("source_files")
        if (train_source_map.get(TRAINER) != trainer_sha
                or not isinstance(receipt_sources, dict) or receipt_sources.get(TRAINER, "").lower() != trainer_sha):
            raise ValueError(f"{branch} run did not use the frozen paired trainer source")
        if (train_release.get("schema") != "CM18_B24_C524_TRAINING_RELEASE_V1"
                or train_release.get("branch") != branch
                or train_release.get("decision") != "APPROVE_ONE_BRANCH_TRAINING"
                or train_release.get("seed") != 2026102001
                or train_release.get("optimizer_steps") != 60_000
                or train_release.get("batch_size") != 512
                or train_release.get("device") != "cuda:0"):
            raise ValueError(f"{branch} training release is not the fixed final-60000 run")
        if (receipt.get("schema") != "CM18_B24_C524_TRAINING_RECEIPT_V1"
                or receipt.get("status") != "COMPLETED" or receipt.get("branch") != branch
                or receipt.get("optimizer_steps_target") != 60_000
                or receipt.get("optimizer_steps_completed") != 60_000
                or receipt.get("optimizer_step_calls_attempted") != 60_000
                or receipt.get("candidate_frozen") is not True
                or receipt.get("checkpoint_selection") != "fixed_final_60000_no_validation_selection"
                or receipt.get("Plant_calls") != 0 or receipt.get("TEST_accessed") is not False
                or receipt.get("C5_VAL48_used_for_training_or_selection") is not False):
            raise ValueError(f"{branch} is not a completed, frozen, unselected final-60000 receipt")
        if (config.get("schema") != "CM18_B24_C524_TRAINING_CONFIG_V1" or config.get("branch") != branch
                or config.get("seed") != 2026102001 or config.get("optimizer_steps") != 60_000
                or config.get("batch_size") != 512 or config.get("scene_count") != 24
                or config.get("fit_rows") != 9_600
                or config.get("selection") != "none; only fixed final step 60000 is retained"):
            raise ValueError(f"{branch} training config differs from the frozen comparison protocol")
        train_release_sha = _sha256(paths["training_release"])
        receipt_release_path = _repo_path(root, str(receipt.get("release_path", "")))
        if (receipt_release_path != paths["training_release"]
                or receipt.get("release_sha256", "").lower() != train_release_sha):
            raise ValueError(f"{branch} receipt does not bind its released run")
        common_values = {
            "paired_row_map_sha256": pair.get("paired_row_map_sha256"),
            "sample_index_stream_sha256": pair.get("sample_index_stream_sha256"),
        }
        for key, value in common_values.items():
            if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value.lower()):
                raise ValueError(f"score release {key} is malformed")
            if (train_release.get(key, "").lower() != value.lower()
                    or receipt.get(key, receipt.get(key + "_actual", "")).lower() != value.lower()
                    or config.get(key, "").lower() != value.lower()):
                raise ValueError(f"{branch} {key} differs from shared paired identity")
        if (receipt.get("sample_index_stream_sha256_expected", "").lower()
                != common_values["sample_index_stream_sha256"].lower()
                or receipt.get("sample_index_stream_sha256_actual", "").lower()
                != common_values["sample_index_stream_sha256"].lower()):
            raise ValueError(f"{branch} actual sampling stream differs from the pinned shared stream")
        for key in ("initial_checkpoint_sha256", "initial_float32_state_sha256"):
            if not isinstance(receipt.get(key), str) or len(receipt[key]) != 64:
                raise ValueError(f"{branch} receipt lacks {key}")
        if (train_release.get("normalizer", {}).get("canonical_sha256", "").lower()
                != CANONICAL_NORMALIZER_SHA256
                or train_release.get("initial_parameters", {}).get("sha256", "").lower()
                != INITIAL_PARAMETERS_SHA256
                or config.get("normalizer_sha256", "").lower() != NORMALIZER_SHA256
                or config.get("canonical_normalizer_sha256", "").lower() != CANONICAL_NORMALIZER_SHA256
                or config.get("initial_parameters_sha256", "").lower() != INITIAL_PARAMETERS_SHA256):
            raise ValueError(f"{branch} did not use the common canonical normalizer and initial parameters")
        if (receipt.get("final_checkpoint_sha256", "").lower() != checkpoint_pin["sha256"].lower()
                or receipt.get("run_directory") != train_release.get("output_directory")):
            raise ValueError(f"{branch} final checkpoint/receipt binding mismatch")
        initial_path = _repo_path(root, str(train_release.get("output_directory", "")) + "/initial.pt")
        if _sha256(initial_path) != receipt["initial_checkpoint_sha256"].lower():
            raise ValueError(f"{branch} actual initial checkpoint differs from terminal receipt")
        prepared[branch] = {"release": train_release, "receipt": receipt, "config": config,
                            "paths": paths, "checkpoint_sha256": checkpoint_pin["sha256"].lower()}
        checkpoints[branch] = _load_final_checkpoint(paths["checkpoint"], receipt)
    if (prepared["B24"]["receipt"]["initial_checkpoint_sha256"].lower()
            != prepared["C5_24"]["receipt"]["initial_checkpoint_sha256"].lower()
            or prepared["B24"]["receipt"]["initial_float32_state_sha256"].lower()
            != prepared["C5_24"]["receipt"]["initial_float32_state_sha256"].lower()):
        raise ValueError("the two branches do not share the exact initial checkpoint and float32 state")
    return prepared, checkpoints


def _load_final_checkpoint(path: Path, receipt: dict[str, Any]) -> dict[str, Any]:
    import numpy as np
    import torch

    try:
        checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    except TypeError:
        checkpoint = torch.load(path, map_location="cpu")
    if (checkpoint.get("schema") != "CM18_B24_C524_CHECKPOINT_V1"
            or checkpoint.get("kind") != "final" or checkpoint.get("optimizer_step") != 60_000
            or not isinstance(checkpoint.get("state_dict"), dict)):
        raise ValueError(f"final checkpoint schema/step mismatch: {path}")
    state = checkpoint["state_dict"]
    if _state_hash(state) != receipt.get("final_float32_state_sha256", "").lower():
        raise ValueError(f"checkpoint float32 state digest differs from terminal receipt: {path}")
    names = {"fc1.weight", "fc1.bias", "fc2.weight", "fc2.bias", "fc3.weight", "fc3.bias",
             "input_mean", "input_std", "train_axis_rms_rad_s2"}
    if set(state) != names:
        raise ValueError("checkpoint state_dict keys differ from CM18 18-32-32-24")
    shapes = {"fc1.weight": (32, 18), "fc1.bias": (32,), "fc2.weight": (32, 32),
              "fc2.bias": (32,), "fc3.weight": (24, 32), "fc3.bias": (24,),
              "input_mean": (18,), "input_std": (18,), "train_axis_rms_rad_s2": (3,)}
    result: dict[str, Any] = {}
    for name, shape in shapes.items():
        tensor = state[name]
        if tensor.dtype != torch.float32 or tuple(tensor.shape) != shape or not torch.isfinite(tensor).all().item():
            raise ValueError(f"invalid final float32 tensor: {name}")
        result[name] = tensor.detach().cpu().numpy().copy()
    return result


def _canonical_normalizer(root: Path) -> dict[str, Any]:
    import numpy as np

    record = _read_json(_repo_path(root, NORMALIZER))
    if (record.get("schema") != "CM18_A1T_NORMALIZER_V1"
            or record.get("canonical_float64_sha256", "").lower() != CANONICAL_NORMALIZER_SHA256):
        raise ValueError("canonical A1T normalizer metadata mismatch")
    arrays = {
        "input_mean": np.asarray(record["input_mean_float64"], dtype=np.float64),
        "input_std": np.asarray(record["input_std_float64"], dtype=np.float64),
        "train_axis_rms_rad_s2": np.asarray(record["train_axis_rms_rad_s2_float64"], dtype=np.float64),
    }
    expected_shapes = {"input_mean": (18,), "input_std": (18,), "train_axis_rms_rad_s2": (3,)}
    for name, a in arrays.items():
        if a.shape != expected_shapes[name] or not np.isfinite(a).all():
            raise ValueError(f"invalid canonical normalizer array {name}")
    if np.any(arrays["input_std"] < 1e-6) or np.any(arrays["train_axis_rms_rad_s2"] <= 0):
        raise ValueError("canonical normalizer has invalid std or axis RMS")
    digest = hashlib.sha256(b"".join(np.ascontiguousarray(a, dtype=np.float64).tobytes(order="C")
                                        for a in arrays.values())).hexdigest()
    if digest != CANONICAL_NORMALIZER_SHA256:
        raise ValueError("canonical normalizer float64 bytes differ from the frozen digest")
    audit = _read_json(_repo_path(root, NORMALIZER_AUDIT))
    if (audit.get("status") != "PASS" or audit.get("schema") != "CM18_CSTAR_ALL816_INDEPENDENT_AUDIT_V1"
            or audit.get("canonical_normalizer_sha256", "").lower() != digest
            or audit.get("label_manifest_sha256", "").lower() != B_DATASET_SHA256
            or audit.get("scene_count") != 816 or audit.get("split_counts") != {"TRAIN": 768, "VAL": 48}):
        raise ValueError("independent canonical normalizer audit mismatch")
    return arrays


def _mat_field(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        if key not in obj:
            raise ValueError(f"MAT struct lacks field {key}")
        return obj[key]
    if not hasattr(obj, key):
        raise ValueError(f"MAT struct lacks field {key}")
    return getattr(obj, key)


def _mat_text(value: Any) -> str:
    import numpy as np

    if isinstance(value, str):
        return value.strip()
    a = np.asarray(value)
    if a.dtype.kind in "US":
        return "".join(str(x) for x in a.reshape(-1)).strip()
    if a.dtype.kind in "ui":
        return "".join(chr(int(x)) for x in a.reshape(-1) if int(x)).strip()
    raise ValueError(f"MAT string has unsupported dtype {a.dtype}")


def _mat_array(obj: Any, key: str, shape: tuple[int, ...], dtype: Any) -> Any:
    import numpy as np

    value = np.asarray(_mat_field(obj, key), dtype=dtype)
    if value.shape == (shape[0], 1) and len(shape) == 1:
        value = value.reshape(-1)
    if value.shape != shape or not np.isfinite(value).all():
        raise ValueError(f"MAT events/{key} has shape/finite mismatch: {value.shape}, expected {shape}")
    return value


def _read_c5_val(root: Path, manifest_path: Path, manifest: dict[str, Any], b_ids: list[str],
                 relabeler_sha: str) -> list[dict[str, Any]]:
    import numpy as np
    from scipy.io import loadmat

    if (manifest.get("schema") != "CM18_C5_VAL48_CSTAR_RELABEL_MANIFEST_V1"
            or manifest.get("status") != "PASS" or manifest.get("training_eligible") is not False
            or manifest.get("TEST_accessed") is not False
            or manifest.get("source_manifest_path") != "reports/attitude_cm18_datarepair_20261024/c5_val48_c5_teacher_v3/C5_VAL48_EVENT_CACHE_MANIFEST_v3.json"
            or manifest.get("source_manifest_sha256", "").lower() != C5_SOURCE_MANIFEST_SHA256
            or manifest.get("candidate_manifest_path") != "reports/attitude_position_context_probe_20261024/C5_MATCHED_VAL_REUSE_CANDIDATES_v1.json"
            or manifest.get("candidate_manifest_sha256", "").lower() != C5_CANDIDATE_MANIFEST_SHA256):
        raise ValueError("C5 VAL C* manifest is not a certified diagnostic-only PASS")
    if (manifest.get("entry_path") != C5_RELABELER
            or manifest.get("entry_sha256", "").lower() != relabeler_sha):
        raise ValueError("C5 VAL relabel manifest does not bind the pinned relabeler source")
    summary = manifest.get("summary", {})
    if (summary.get("scene_count") != 48 or summary.get("qualified_count") != 48
            or summary.get("failed_count") != 0 or summary.get("split_counts") != {"TRAIN": 0, "VAL": 48}
            or summary.get("event_count") != 48 * N_EVENTS or summary.get("training_eligible") is not False):
        raise ValueError("C5 VAL C* manifest counts/eligibility mismatch")
    rows = manifest.get("scenes")
    if not isinstance(rows, list) or len(rows) != 48:
        raise ValueError("C5 VAL manifest must contain all 48 scenes")
    by_id = {row.get("scene_id"): row for row in rows if isinstance(row, dict)}
    if len(by_id) != 48 or set(by_id) != set(b_ids):
        raise ValueError("C5 VAL scene set does not exactly match B VAL48")
    output: list[dict[str, Any]] = []
    for sid in b_ids:
        row = by_id[sid]
        sid = row.get("scene_id")
        if (row.get("status") != "PASS" or row.get("qualified") is not True or row.get("split") != "VAL"
                or row.get("training_eligible") is not False):
            raise ValueError(f"C5 VAL row is not diagnostic-only PASS: {sid}")
        cache_rel = row.get("cache_path")
        if not isinstance(cache_rel, str):
            raise ValueError(f"C5 VAL row lacks cache path: {sid}")
        cache_path = _repo_path(root, cache_rel)
        if cache_path.stat().st_size != int(row.get("cache_bytes", -1)) or _sha256(cache_path) != row.get("cache_sha256", "").lower():
            raise ValueError(f"C5 VAL cache SHA/size mismatch: {sid}")
        mat = loadmat(cache_path, squeeze_me=True, struct_as_record=False, variable_names=("cache",))
        if "cache" not in mat:
            raise ValueError(f"C5 VAL MAT lacks scalar cache: {sid}")
        cache = mat["cache"]
        identity = _mat_field(cache, "identity")
        events = _mat_field(cache, "events")
        if (_mat_text(_mat_field(cache, "schema")) != "CM18_C5_VAL48_CSTAR_EVENT_CACHE_V1"
                or _mat_text(_mat_field(identity, "schema")) != "CM18_C5_VAL48_CSTAR_CACHE_IDENTITY_V1"
                or _mat_text(_mat_field(identity, "scene_id")) != sid
                or _mat_text(_mat_field(identity, "split")) != "VAL"
                or bool(np.asarray(_mat_field(identity, "training_eligible")).reshape(-1)[0])
                or _mat_text(_mat_field(identity, "candidate_manifest_sha256")).lower() != C5_CANDIDATE_MANIFEST_SHA256
                or _mat_text(_mat_field(identity, "C5_event_manifest_sha256")).lower() != C5_SOURCE_MANIFEST_SHA256
                or _mat_text(_mat_field(events, "schema")) != "CM18_C5_VAL48_CSTAR_EVENTS_V1"
                or _mat_text(_mat_field(events, "scene_id")) != sid):
            raise ValueError(f"C5 VAL cache identity/schema mismatch: {sid}")
        x = np.asarray(_mat_field(events, "X18"), dtype=np.float64)
        target = np.asarray(_mat_field(events, "target_raw_output_rad_s2"), dtype=np.float64)
        cstar = np.asarray(_mat_field(events, "target_applied_acceleration_rad_s2"), dtype=np.float64)
        after_clip = np.asarray(_mat_field(events, "target_after_clip_beta_rad_s2"), dtype=np.float64)
        gflat = np.asarray(_mat_field(events, "G_row_major"), dtype=np.float64)
        g_layout = _mat_text(_mat_field(events, "G_layout")).lower()
        if x.shape != (N_EVENTS, 18) or any(a.shape != (N_EVENTS, 3) for a in (target, cstar, after_clip)) or gflat.shape != (N_EVENTS, 9):
            raise ValueError(f"C5 VAL event arrays have wrong MATLAB V7 shape: {sid}")
        if "row-major" not in g_layout:
            raise ValueError(f"C5 VAL event cache does not declare row-major G layout: {sid}")
        beta = _mat_array(events, "beta", (N_EVENTS,), np.float64)
        event_index = _mat_array(events, "event_index", (N_EVENTS,), np.float64).astype(np.int64)
        plant = _mat_array(events, "plant_index", (N_EVENTS,), np.float64).astype(np.int64)
        time = _mat_array(events, "event_time_s", (N_EVENTS,), np.float64)
        phase = _mat_array(events, "phase_code", (N_EVENTS,), np.float64).astype(np.int64)
        if (not all(np.isfinite(a).all() for a in (x, target, cstar, after_clip, gflat))
                or not np.array_equal(event_index, np.arange(1, N_EVENTS + 1))
                or not np.array_equal(plant, np.asarray(PLANT_INDEX))
                or np.max(np.abs(time - (plant - 1) * 0.001)) > 1e-12
                or np.any((phase < 0) | (phase > 5))):
            raise ValueError(f"C5 VAL event clock/finite gate failed: {sid}")
        expected_beta = np.minimum(plant * 0.001 / BETA_RISE_S, 1.0)
        if (np.max(np.abs(beta - expected_beta)) > 1e-12 or np.any(beta <= 0)
                or np.max(np.abs(beta[:, None] * target - cstar)) > 1e-9
                or np.max(np.abs(after_clip - beta[:, None] * np.clip(target, -np.asarray(DMAX), np.asarray(DMAX)))) > 1e-9):
            raise ValueError(f"C5 VAL C*/beta/clip arithmetic mismatch: {sid}")
        reachable = np.asarray(_mat_field(events, "target_raw_output_reachable"), dtype=bool)
        if reachable.shape != (N_EVENTS, 3) or not reachable.all():
            raise ValueError(f"C5 VAL raw target has unreachable components: {sid}")
        g = gflat.reshape(N_EVENTS, 3, 3)
        e0 = np.asarray(_mat_field(events, "E0_rad_s2"), dtype=np.float64)
        if e0.shape != (N_EVENTS, 3) or not np.isfinite(e0).all() or np.max(np.abs(e0 - np.einsum("nij,nj->ni", g, cstar))) > 1e-8:
            raise ValueError(f"C5 VAL row-major G/E0/cStar closure mismatch: {sid}")
        output.append({"scene_id": sid, "split": "VAL", "X18": x, "target_raw": target,
                       "cstar": cstar, "target_after_clip": after_clip, "beta": beta,
                       "event_time_s": time, "phase_code": phase, "plant_index": plant,
                       "G": g, "E0": e0, "G_layout": "row-major", "cache_sha256": row["cache_sha256"]})
    return output


def _load_b_val(root: Path, b_reader: Any) -> list[dict[str, Any]]:
    import numpy as np
    from scipy.io import loadmat

    scenes = b_reader.load_cstar_split(root, B_DATASET, "VAL", B_DATASET_SHA256)
    manifest = _read_json(_repo_path(root, B_DATASET))
    rows = {row["scene_id"]: row for row in manifest["rows"] if row.get("split") == "VAL"}
    output = []
    for scene in scenes:
        sid = scene["scene_id"]
        row = rows.get(sid)
        if row is None:
            raise ValueError(f"B VAL manifest row missing: {sid}")
        mat_path = _repo_path(root, row["cache_path"])
        if _sha256(mat_path) != row["cache_sha256"].lower() or mat_path.stat().st_size != int(row["cache_bytes"]):
            raise ValueError(f"B VAL cache identity mismatch: {sid}")
        stored = loadmat(mat_path, squeeze_me=False, struct_as_record=False,
                         variable_names=("G_column_major", "G_layout"))
        layout = _mat_text(stored["G_layout"]).lower()
        flat = np.asarray(stored["G_column_major"], dtype=np.float64)
        if "column-major" not in layout or flat.shape != (N_EVENTS, 9) or not np.isfinite(flat).all():
            raise ValueError(f"B VAL G cache layout/shape mismatch: {sid}")
        g = flat.reshape(N_EVENTS, 3, 3).transpose(0, 2, 1)
        beta = np.minimum(np.asarray(scene["plant_index"]).reshape(-1) * 0.001 / BETA_RISE_S, 1.0)
        cstar = np.asarray(scene["target_applied_acceleration_rad_s2"], dtype=np.float64)
        target_raw = np.asarray(scene["target_raw_output_rad_s2"], dtype=np.float64)
        after_clip = np.asarray(scene["target_after_clip_beta_rad_s2"], dtype=np.float64)
        if (cstar.shape != (N_EVENTS, 3) or target_raw.shape != (N_EVENTS, 3)
                or after_clip.shape != (N_EVENTS, 3)
                or np.max(np.abs(beta[:, None] * target_raw - cstar)) > 1e-9
                or np.max(np.abs(after_clip - beta[:, None] * np.clip(target_raw, -np.asarray(DMAX), np.asarray(DMAX)))) > 1e-9):
            raise ValueError(f"B VAL C*/beta/clip arithmetic mismatch: {sid}")
        plant = np.asarray(scene["plant_index"], dtype=np.int64).reshape(-1)
        time = np.asarray(scene["event_time_s"], dtype=np.float64).reshape(-1)
        phase = np.asarray(scene["phase_code"], dtype=np.int64).reshape(-1)
        e0 = np.einsum("nij,nj->ni", g, cstar)
        output.append({"scene_id": sid, "split": "VAL", "X18": np.asarray(scene["X18"], dtype=np.float64),
                       "target_raw": target_raw, "cstar": cstar, "target_after_clip": after_clip,
                       "beta": beta, "event_time_s": time, "phase_code": phase, "plant_index": plant,
                       "G": g, "E0": e0, "G_layout": "column-major", "cache_sha256": row["cache_sha256"],
                       "E0_provenance": "derived from pinned B cache G_column_major*cStar; not stored"})
    return output


def _parse_scene_id(sid: str) -> tuple[str, str, str]:
    match = re.fullmatch(r"DL1018_VAL_(T[123])_(C\d{2})_(W\d{2})", sid)
    if not match:
        raise ValueError(f"unexpected VAL scene ID: {sid}")
    return match.group(1), match.group(2), match.group(3)


def _metric(raw_error: Any, action_error: Any, physics_residual: Any, mask: Any = None) -> dict[str, Any] | None:
    import numpy as np

    if mask is not None:
        raw_error, action_error, physics_residual = raw_error[mask], action_error[mask], physics_residual[mask]
    if len(raw_error) == 0:
        return None
    def axes(a: Any) -> list[float]:
        return np.sqrt(np.mean(np.square(a), axis=0)).astype(float).tolist()
    def vector(a: Any) -> float:
        return float(np.sqrt(np.mean(np.sum(np.square(a), axis=1))))
    return {"events": int(len(raw_error)),
            "raw_output_axis_rmse_rad_s2": axes(raw_error), "raw_output_vector_rmse_rad_s2": vector(raw_error),
            "cstar_action_axis_rmse_rad_s2": axes(action_error), "cstar_action_vector_rmse_rad_s2": vector(action_error),
            "linear_physics_residual_axis_rmse_rad_s2": axes(physics_residual),
            "linear_physics_residual_vector_rmse_rad_s2": vector(physics_residual)}


def _score_model(scenes: list[dict[str, Any]], weights: dict[str, Any], normalizer: dict[str, Any],
                 numpy_model: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    import numpy as np

    params = {"W1": weights["fc1.weight"].astype(np.float64), "b1": weights["fc1.bias"].astype(np.float64),
              "W2": weights["fc2.weight"].astype(np.float64), "b2": weights["fc2.bias"].astype(np.float64),
              "W3": weights["fc3.weight"].astype(np.float64), "b3": weights["fc3.bias"].astype(np.float64),
              **normalizer}
    scene_metrics = []
    computed = []
    for scene in scenes:
        x = scene["X18"]
        pred = numpy_model.forward(x, params)["physical_output_rad_s2"]
        action = scene["beta"][:, None] * np.clip(pred, -np.asarray(DMAX), np.asarray(DMAX))
        raw_error = pred - scene["target_raw"]
        action_error = action - scene["cstar"]
        physics = scene["E0"] - np.einsum("nij,nj->ni", scene["G"], action)
        pred_clip = np.abs(pred) > np.asarray(DMAX)[None, :]
        target_clip = np.abs(scene["target_raw"]) > np.asarray(DMAX)[None, :]
        zero_basis = np.all(x[:, 7:15] == 0.0, axis=1)
        all_metric = _metric(raw_error, action_error, physics)
        task, condition, wind = _parse_scene_id(scene["scene_id"])
        row = {"scene_id": scene["scene_id"], "task": task, "condition": condition, "wind": wind,
               "events": N_EVENTS, "beta_min": float(scene["beta"].min()), "beta_max": float(scene["beta"].max()),
               "zero_basis_events": int(zero_basis.sum()), "predicted_clip_events": int(np.any(pred_clip, axis=1).sum()),
               "predicted_clip_by_axis": pred_clip.sum(axis=0).astype(int).tolist(),
               "target_clip_events": int(np.any(target_clip, axis=1).sum()),
               "target_clip_by_axis": target_clip.sum(axis=0).astype(int).tolist(),
               "E0_provenance": scene.get("E0_provenance", "stored in C5 VAL C* cache"),
               "G_layout": scene["G_layout"], "cache_sha256": scene["cache_sha256"], "metrics": all_metric,
               "zero_basis_metrics": _metric(raw_error, action_error, physics, zero_basis),
               "nonzero_basis_metrics": _metric(raw_error, action_error, physics, ~zero_basis),
               "predicted_clipped_metrics": _metric(raw_error, action_error, physics, np.any(pred_clip, axis=1)),
               "predicted_unclipped_metrics": _metric(raw_error, action_error, physics, ~np.any(pred_clip, axis=1))}
        row.update({
            "raw_output_axis_rmse_rad_s2": all_metric["raw_output_axis_rmse_rad_s2"],
            "raw_output_vector_rmse_rad_s2": all_metric["raw_output_vector_rmse_rad_s2"],
            "cstar_action_axis_rmse_rad_s2": all_metric["cstar_action_axis_rmse_rad_s2"],
            "cstar_action_vector_rmse_rad_s2": all_metric["cstar_action_vector_rmse_rad_s2"],
            "linear_physics_residual_axis_rmse_rad_s2": all_metric["linear_physics_residual_axis_rmse_rad_s2"],
            "linear_physics_residual_vector_rmse_rad_s2": all_metric["linear_physics_residual_vector_rmse_rad_s2"],
        })
        scene_metrics.append(row)
        computed.append({"raw_error": raw_error, "action_error": action_error, "physics": physics,
                         "zero_basis": zero_basis, "pred_clip": np.any(pred_clip, axis=1),
                         "phase": scene["phase_code"], "scene": row})

    def pooled(items: list[dict[str, Any]], mask_name: str | None = None, mask_value: Any = None) -> dict[str, Any] | None:
        if not items:
            return None
        raw = np.concatenate([i["raw_error"] for i in items])
        act = np.concatenate([i["action_error"] for i in items])
        phys = np.concatenate([i["physics"] for i in items])
        if mask_name is None:
            return _metric(raw, act, phys)
        mask = np.concatenate([i[mask_name] == mask_value for i in items])
        return _metric(raw, act, phys, mask)

    def group(items: list[dict[str, Any]]) -> dict[str, Any]:
        rows = [i["scene"] for i in items]
        keys = ("raw_output_vector_rmse_rad_s2", "cstar_action_vector_rmse_rad_s2",
                "linear_physics_residual_vector_rmse_rad_s2")
        axes = ("raw_output_axis_rmse_rad_s2", "cstar_action_axis_rmse_rad_s2",
                "linear_physics_residual_axis_rmse_rad_s2")
        macro = {key: float(np.mean([r[key] for r in rows])) for key in keys} if rows else {}
        macro.update({key: np.mean([r[key] for r in rows], axis=0).astype(float).tolist() for key in axes} if rows else {})
        return {"scene_count": len(rows), "scene_macro": macro,
                "pooled_events": pooled(items)}

    groups: dict[str, Any] = {"ALL": group(computed)}
    tasks = sorted({i["scene"]["task"] for i in computed})
    winds = sorted({i["scene"]["wind"] for i in computed})
    groups["by_task"] = {key: group([i for i in computed if i["scene"]["task"] == key]) for key in tasks}
    groups["by_wind"] = {key: group([i for i in computed if i["scene"]["wind"] == key]) for key in winds}
    groups["by_task_wind"] = {
        f"{task}_{wind}": group([i for i in computed if i["scene"]["task"] == task and i["scene"]["wind"] == wind])
        for task in tasks for wind in winds
        if any(i["scene"]["task"] == task and i["scene"]["wind"] == wind for i in computed)
    }
    groups["HF_W09_W14"] = group([i for i in computed if 9 <= int(i["scene"]["wind"][1:]) <= 14])
    groups["no_wind_W15"] = group([i for i in computed if i["scene"]["wind"] == "W15"])
    groups["by_phase"] = {
        str(code): {"name": name, "metrics": pooled([i for i in computed if np.any(i["phase"] == code)], "phase", code)}
        for code, name in PHASES.items()
    }
    groups["by_basis"] = {
        "zero": pooled(computed, "zero_basis", True),
        "nonzero": pooled(computed, "zero_basis", False),
        "predicted_clipped": pooled(computed, "pred_clip", True),
        "predicted_unclipped": pooled(computed, "pred_clip", False),
    }
    return {"groups": groups, "scene_count": len(scene_metrics)}, scene_metrics


def _torch_numpy_parity(root: Path, weights_by_branch: dict[str, dict[str, Any]],
                        normalizer: dict[str, Any], scenes_by_domain: dict[str, list[dict[str, Any]]],
                        numpy_model: Any) -> dict[str, Any]:
    import numpy as np
    import torch

    torch_model = _load_module(root, TORCH_MODEL, "score_torch_cm18")
    out = {}
    for branch, weights in weights_by_branch.items():
        params = {"W1": weights["fc1.weight"].astype(np.float64), "b1": weights["fc1.bias"].astype(np.float64),
                  "W2": weights["fc2.weight"].astype(np.float64), "b2": weights["fc2.bias"].astype(np.float64),
                  "W3": weights["fc3.weight"].astype(np.float64), "b3": weights["fc3.bias"].astype(np.float64),
                  **normalizer}
        model = torch_model.TorchCM18A1(normalizer["input_mean"], normalizer["input_std"], normalizer["train_axis_rms_rad_s2"])
        model.load_numpy_parameters(params)
        records = {}
        for domain, scenes in scenes_by_domain.items():
            sample = next(s for s in scenes if np.any(s["X18"][:, 7:15] != 0.0))
            x = sample["X18"][:64]
            with torch.no_grad():
                actual = model(torch.as_tensor(x, dtype=torch.float64, device="cpu"))["physical_output_rad_s2"].numpy()
            expected = numpy_model.forward(x, params)["physical_output_rad_s2"]
            delta = float(np.max(np.abs(actual - expected)))
            if not np.isfinite(delta) or delta > 1e-10:
                raise AssertionError(f"{branch}/{domain} actual-weight CPU parity failed: {delta}")
            records[domain] = {"scene_id": sample["scene_id"], "rows": len(x), "max_abs_delta_rad_s2": delta}
        out[branch] = records
    return out


def _csv_bytes(rows: list[dict[str, Any]]) -> bytes:
    import io

    fields = ["model", "domain", "scene_id", "task", "condition", "wind", "events", "beta_min", "beta_max",
              "zero_basis_events", "predicted_clip_events", "predicted_clip_x", "predicted_clip_y", "predicted_clip_z",
              "target_clip_events", "target_clip_x", "target_clip_y", "target_clip_z",
              "raw_rmse_x_rad_s2", "raw_rmse_y_rad_s2", "raw_rmse_z_rad_s2", "raw_vector_rmse_rad_s2",
              "action_rmse_x_rad_s2", "action_rmse_y_rad_s2", "action_rmse_z_rad_s2", "action_vector_rmse_rad_s2",
              "physics_rmse_x_rad_s2", "physics_rmse_y_rad_s2", "physics_rmse_z_rad_s2", "physics_vector_rmse_rad_s2",
              "G_layout", "E0_provenance", "cache_sha256"]
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="raise", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        raw_axis = row["raw_output_axis_rmse_rad_s2"]
        act_axis = row["cstar_action_axis_rmse_rad_s2"]
        phy_axis = row["linear_physics_residual_axis_rmse_rad_s2"]
        writer.writerow({"model": row["model"], "domain": row["domain"], "scene_id": row["scene_id"],
                         "task": row["task"], "condition": row["condition"], "wind": row["wind"],
                         "events": row["events"], "beta_min": row["beta_min"], "beta_max": row["beta_max"],
                         "zero_basis_events": row["zero_basis_events"], "predicted_clip_events": row["predicted_clip_events"],
                         "predicted_clip_x": row["predicted_clip_by_axis"][0], "predicted_clip_y": row["predicted_clip_by_axis"][1],
                         "predicted_clip_z": row["predicted_clip_by_axis"][2], "target_clip_events": row["target_clip_events"],
                         "target_clip_x": row["target_clip_by_axis"][0], "target_clip_y": row["target_clip_by_axis"][1],
                         "target_clip_z": row["target_clip_by_axis"][2], "raw_rmse_x_rad_s2": raw_axis[0],
                         "raw_rmse_y_rad_s2": raw_axis[1], "raw_rmse_z_rad_s2": raw_axis[2],
                         "raw_vector_rmse_rad_s2": row["raw_output_vector_rmse_rad_s2"],
                         "action_rmse_x_rad_s2": act_axis[0], "action_rmse_y_rad_s2": act_axis[1],
                         "action_rmse_z_rad_s2": act_axis[2], "action_vector_rmse_rad_s2": row["cstar_action_vector_rmse_rad_s2"],
                         "physics_rmse_x_rad_s2": phy_axis[0], "physics_rmse_y_rad_s2": phy_axis[1],
                         "physics_rmse_z_rad_s2": phy_axis[2], "physics_vector_rmse_rad_s2": row["linear_physics_residual_vector_rmse_rad_s2"],
                         "G_layout": row["G_layout"], "E0_provenance": row["E0_provenance"], "cache_sha256": row["cache_sha256"]})
    return stream.getvalue().encode("utf-8")


def _write_exclusive(path: Path, data: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _score(root: Path, release: dict[str, Any], sources: dict[str, str]) -> dict[str, Any]:
    import numpy as np

    pair_reader = _load_module(root, PAIR_READER, "b24_c524_pair_reader")
    b_reader = _load_module(root, B_READER, "b24_cstar_reader")
    numpy_model = _load_module(root, NUMPY_MODEL, "cm18_numpy_model")
    c5_manifest = _read_json(Path(release["_c5_manifest_path"]))
    b_scenes = _load_b_val(root, b_reader)
    b_ids = [scene["scene_id"] for scene in b_scenes]
    c5_scenes = _read_c5_val(root, Path(release["_c5_manifest_path"]), c5_manifest, b_ids,
                             sources[C5_RELABELER])
    for b, c in zip(b_scenes, c5_scenes, strict=True):
        if (b["scene_id"] != c["scene_id"] or not np.array_equal(b["plant_index"], c["plant_index"])
                or not np.array_equal(b["phase_code"], c["phase_code"])
                or not np.array_equal(b["event_time_s"], c["event_time_s"])):
            raise ValueError(f"B/C5 same-input event alignment mismatch: {b['scene_id']}")
    normalizer = _canonical_normalizer(root)
    runs, weights = _verify_runs(root, release)
    expected_stream = release["paired_identity"]["sample_index_stream_sha256"].lower()
    actual_stream = pair_reader.sample_stream_sha()
    if actual_stream != expected_stream:
        raise ValueError("the paired reader's frozen 60,000-step RNG stream differs from the release")
    for branch in BRANCHES:
        for stored, canonical, name in (("input_mean", "input_mean", "input_mean"),
                                        ("input_std", "input_std", "input_std"),
                                        ("train_axis_rms_rad_s2", "train_axis_rms_rad_s2", "axis RMS")):
            if not np.array_equal(weights[branch][stored], normalizer[canonical].astype(np.float32)):
                raise ValueError(f"{branch} checkpoint {name} buffer differs from canonical float64 cast")
    domains = {"B_VAL48": b_scenes, "C5_VAL48": c5_scenes}
    parity = _torch_numpy_parity(root, weights, normalizer, domains, numpy_model)
    all_rows = []
    metrics = {}
    for branch in BRANCHES:
        metrics[branch] = {}
        for domain, scenes in domains.items():
            summary, rows = _score_model(scenes, weights[branch], normalizer, numpy_model)
            metrics[branch][domain] = summary
            for row in rows:
                all_rows.append({"model": branch, "domain": domain, **row})
    pair = release["paired_identity"]
    return {
        "schema": "CM18_B24_C524_FINAL_SCORE_RESULT_V1", "status": "PASS",
        "release_path": release["_release_path"], "release_sha256": release["_release_sha256"],
        "source_files": sources, "normalizer_path": NORMALIZER, "normalizer_file_sha256": NORMALIZER_SHA256,
        "canonical_normalizer_sha256": CANONICAL_NORMALIZER_SHA256,
        "normalizer_policy": "canonical float64 input_mean/input_std/axis_RMS loaded from normalizer.json; never inferred from float32 buffers",
        "b_val_manifest_path": B_DATASET, "b_val_manifest_sha256": B_DATASET_SHA256,
        "c5_val_manifest_path": release["c5_val_manifest"]["path"],
        "c5_val_manifest_sha256": release["_c5_manifest_sha256"],
        "C5_VAL_training_eligible": False, "ordered_scene_ids": b_ids, "scene_count": 48,
        "events_per_scene": N_EVENTS, "paired_row_map_sha256": pair["paired_row_map_sha256"],
        "sample_index_stream_sha256": pair["sample_index_stream_sha256"],
        "sample_index_stream_recomputed_sha256": actual_stream,
        "runs": {branch: {"training_release_path": str(runs[branch]["paths"]["training_release"]),
                           "training_release_sha256": _sha256(runs[branch]["paths"]["training_release"]),
                           "receipt_path": str(runs[branch]["paths"]["receipt"]),
                           "receipt_sha256": _sha256(runs[branch]["paths"]["receipt"]),
                           "training_config_path": str(runs[branch]["paths"]["training_config"]),
                           "training_config_sha256": _sha256(runs[branch]["paths"]["training_config"]),
                           "checkpoint_sha256": runs[branch]["checkpoint_sha256"],
                           "final_float32_state_sha256": runs[branch]["receipt"]["final_float32_state_sha256"],
                           "initial_float32_state_sha256": runs[branch]["receipt"]["initial_float32_state_sha256"]}
                 for branch in BRANCHES},
        "torch_double_numpy_actual_weight_parity": parity,
        "E0_provenance": {"B_VAL48": "derived per event as G_column_major*cStar from the bound B C* cache; B cache does not store E0",
                          "C5_VAL48": "stored E0_rad_s2 from the pinned C5 VAL C* V7 cache"},
        "metric_definitions": {
            "raw_output_error": "prediction in rad/s^2 minus cStar/beta target in rad/s^2",
            "action_error": "beta*componentwise_clip(prediction, DMAX) minus cStar, rad/s^2",
            "linear_physics_residual": "E0 - G @ beta*componentwise_clip(prediction, DMAX), rad/s^2",
            "vector_RMSE": "sqrt(mean over selected events of the sum of three squared axis errors))",
            "scene_macro": "equal-weight arithmetic mean of per-scene RMSEs; pooled-event metrics are separately labeled",
            "selection": "fixed final step 60000 only; VAL did not select checkpoints"},
        "metrics": metrics, "scene_results": all_rows,
        "scope": {"training_steps": 0, "optimizer_steps": 0, "Plant_calls": 0,
                  "TEST_accessed": False, "checkpoint_selection": "none; both pinned final-60000 checkpoints scored"},
    }


def _synthetic_check() -> None:
    _math_environment()
    import numpy as np

    g = np.asarray([[2.0, 3.0, 5.0], [7.0, 11.0, 13.0], [17.0, 19.0, 23.0]])
    row_flat = g.reshape(1, 9)
    col_flat = g.T.reshape(1, 9)
    if not np.array_equal(row_flat.reshape(1, 3, 3)[0], g):
        raise AssertionError("synthetic C5 row-major decode failed")
    if not np.array_equal(col_flat.reshape(1, 3, 3).transpose(0, 2, 1)[0], g):
        raise AssertionError("synthetic B column-major decode failed")
    cstar = np.asarray([[1.0, -2.0, 3.0]])
    e0 = np.einsum("ij,j->i", g, cstar[0])[None, :]
    if np.max(np.abs(e0 - np.einsum("nij,nj->ni", g[None, :, :], cstar))) != 0.0:
        raise AssertionError("synthetic E0=G*cStar closure failed")
    beta = np.asarray([0.5])
    raw = np.asarray([[100.0, -1.0, 20.0]])
    action = beta[:, None] * np.clip(raw, -np.asarray(DMAX), np.asarray(DMAX))
    if not np.array_equal(action, np.asarray([[22.5, -0.5, 2.3562]])):
        raise AssertionError("synthetic beta/clip action failed")
    root = HERE.parents[2]
    model = _load_module(root, NUMPY_MODEL, "synthetic_cm18_numpy")
    zero_weights = {"fc1.weight": np.zeros((32, 18)), "fc1.bias": np.zeros(32),
                    "fc2.weight": np.zeros((32, 32)), "fc2.bias": np.zeros(32),
                    "fc3.weight": np.zeros((24, 32)), "fc3.bias": np.zeros(24)}
    norm = {"input_mean": np.zeros(18), "input_std": np.ones(18), "train_axis_rms_rad_s2": np.ones(3)}
    scenes = []
    for sid, phase in (("DL1018_VAL_T1_C00_W00", 0), ("DL1018_VAL_T2_C04_W15", 3)):
        x = np.zeros((2, 18)); x[1, 7] = 0.25; x[1, 11] = 0.1
        scenes.append({"scene_id": sid, "X18": x, "target_raw": np.zeros((2, 3)),
                       "cstar": np.zeros((2, 3)), "beta": np.full(2, 0.5),
                       "E0": np.zeros((2, 3)), "G": np.broadcast_to(np.eye(3), (2, 3, 3)).copy(),
                       "phase_code": np.asarray([phase, phase]), "cache_sha256": "0" * 64,
                       "G_layout": "synthetic", "event_time_s": np.asarray([0.01, 0.02]),
                       "plant_index": np.asarray([11, 21]), "split": "VAL"})
    summary, rows = _score_model(scenes, zero_weights, norm, model)
    serial = json.dumps({"summary": summary, "rows": rows}, allow_nan=False)
    csv_data = _csv_bytes([{"model": "B24", "domain": "B_VAL48", **row} for row in rows])
    if (summary["scene_count"] != 2 or summary["groups"]["ALL"]["scene_count"] != 2
            or len(rows) != 2 or serial.count("DL1018_VAL_") != 2 or csv_data.count(b"\n") != 3):
        raise AssertionError("synthetic scene/group/CSV result shape failed")
    print("SYNTHETIC_CHECK=PASS B_column_major C5_row_major E0_G_cStar beta_clip scene_groups_JSON_CSV; no release/data/checkpoint/optimizer/Plant")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=HERE.parents[2])
    parser.add_argument("--release", type=Path)
    parser.add_argument("--release-sha256")
    parser.add_argument("--synthetic-check", action="store_true")
    args = parser.parse_args()
    _math_environment()
    if args.synthetic_check:
        if args.release is not None or args.release_sha256 is not None:
            parser.error("--synthetic-check cannot be combined with a score release")
        _synthetic_check()
        return
    if args.release is None or args.release_sha256 is None:
        parser.error("an actual ROOT final-score release path and SHA256 are required")
    root = args.repo_root.resolve(strict=True)
    release, sources = _verify_release(root, args.release, args.release_sha256)
    output_rel = release.get("output_directory")
    if not isinstance(output_rel, str):
        raise ValueError("release must specify output_directory")
    output = _repo_path(root, output_rel, exists=False)
    if output.parent != _repo_path(root, OUTPUT_PARENT, exists=False):
        raise ValueError("output_directory must be one new child under the fixed postselection_scores directory")
    if output.exists():
        raise FileExistsError(f"refusing to overwrite score output: {output}")
    result = _score(root, release, sources)
    flat_rows = result["scene_results"]
    json_bytes = (json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    csv_bytes = _csv_bytes(flat_rows)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir(exist_ok=False)
    _write_exclusive(output / "B24_C5_24_FINAL_SCORE_v1.json", json_bytes)
    _write_exclusive(output / "B24_C5_24_FINAL_SCORE_SCENES_v1.csv", csv_bytes)
    print(json.dumps({"status": "PASS", "output_directory": output_rel,
                      "models": list(BRANCHES), "domains": ["B_VAL48", "C5_VAL48"],
                      "scene_model_domain_rows": len(flat_rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
