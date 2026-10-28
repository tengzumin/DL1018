"""Merge/read the repaired-label CM18 ALL816 set after both exports terminate.

This module is deliberately read-only with respect to scene caches. The CLI
builds a new manifest only from finalized receipts; it never runs Plant,
training, optimizer steps, or accesses TEST data.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat


SOURCE_MANIFEST = "reports/attitude_cm18_datarepair_20261024/B_REF_REPAIRED_SOURCE_MANIFEST_v1.json"
SOURCE_MANIFEST_SHA256 = "0f86b47d01940e7b556b78a9664470531572809aa6857a59fc77d88a33681ec5"
A1_MANIFEST = "reports/attitude_cm18_a1_20261024/data_preparation_v1/events_all816_v1/DATASET_MANIFEST_v1.json"
A1_MANIFEST_SHA256 = "7dd3e1f786f6095ecc2ba56473e5cf0fab6b92cdd42e38a184d6ad1223f36271"
INPUT_MANIFEST = "reports/attitude_cm18_a1_20261024/data_preparation_v1/INPUT_MANIFEST_v1.json"
INPUT_MANIFEST_SHA256 = "a5f7fea9b0918c1449af6fa83929177d3bf7d5e70cb3b71711c40f6338d210a5"
A1_READER = "experiments/attitude_cm18_a1_20261024/cache_reader_cm18_v1.py"
A1_READER_SHA256 = "a2867cbf516d7ed655a6f50e05b8600ffb7582e0f2164b1ce21d5e647adf2b47"
SCREEN4_RECEIPT = "reports/attitude_cm18_datarepair_20261024/export_screen4_v1/SCREEN4_EXPORT_RECEIPT_v1.json"
SCREEN4_RECEIPT_SHA256 = "64bd3f8662a371c72da8b5d2095931140a8df16c06fc8eae2ac45a487cb80bd0"
SCREEN4_AUDIT = "reports/attitude_cm18_datarepair_20261024/ROOT_REFERENCE_REPAIRED_SCREEN4_CACHE_AUDIT_v1.json"
SCREEN4_AUDIT_SHA256 = "03b73973dd462e2d7f9e809b429c71d2a09ad3edfbf3e005a83c4264c00bcb98"
C5_VAL48_MANIFEST = "reports/attitude_cm18_datarepair_20261024/c5_val48_c5_teacher_v3/C5_VAL48_EVENT_CACHE_MANIFEST_v3.json"
C5_VAL48_MANIFEST_SHA256 = "3e72f4726219cfd0e89476c70d24796a06c8f8447d4064cfdc471433a863a501"
REST268_RECEIPT = "reports/attitude_cm18_datarepair_20261024/export_rest268_v1/REST268_EXPORT_RECEIPT_v1.json"
REST268_RECEIPT_SHA256 = "955d7c53381cd3f56015397d9cb1cd1006c929071c0faf374bcbfe17dbf6d1de"
DEFAULT_OUTPUT = "reports/attitude_cm18_datarepair_20261024/repaired_all816_v1/DATASET_MANIFEST_v1.json"

REPAIRED_VARIABLES = (
    "X18", "target_raw", "event_time_s", "phase_code", "plant_index",
    "event_index", "scene_id", "split", "cache_schema", "input_identity",
    "original_a1_identity", "export_meta",
)
EXPECTED_EVENT_INDEX = np.arange(1, 2000, dtype=np.uint16)
EXPECTED_PLANT_INDEX = np.arange(11, 20000, 10, dtype=np.int64)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _repo_file(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or relative.startswith(("/", "\\")):
        raise ValueError(f"expected repository-relative path: {relative!r}")
    path = (root.resolve(strict=True) / relative.replace("\\", "/")).resolve(strict=True)
    try:
        path.relative_to(root.resolve(strict=True))
    except ValueError as exc:
        raise ValueError(f"repository path escapes root: {relative}") from exc
    if not path.is_file():
        raise ValueError(f"missing repository file: {relative}")
    return path


def _repo_output(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or relative.startswith(("/", "\\")):
        raise ValueError("output must be a repository-relative path")
    path = (root.resolve(strict=True) / relative.replace("\\", "/")).resolve()
    try:
        path.relative_to(root.resolve(strict=True))
    except ValueError as exc:
        raise ValueError("output escaped repository root") from exc
    return path


def _pinned_json(root: Path, relative: str, expected_sha256: str) -> tuple[dict[str, Any], str]:
    path = _repo_file(root, relative)
    actual = _sha256(path)
    if actual != expected_sha256.lower():
        raise ValueError(f"pinned file SHA256 mismatch: {relative}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {relative}")
    return value, actual


def _mat_text(value: Any) -> str:
    array = np.asarray(value)
    if array.dtype.kind in "US":
        return "".join(str(part) for part in array.reshape(-1)).strip()
    if array.dtype.kind in "ui":
        return "".join(chr(int(part)) for part in array.reshape(-1) if int(part)).strip()
    raise ValueError(f"expected MATLAB text, got {array.dtype}")


def _mat_struct(value: Any, name: str) -> Any:
    array = np.asarray(value)
    if array.shape != (1, 1) or not hasattr(array[0, 0], "_fieldnames"):
        raise ValueError(f"{name} must be a scalar MATLAB struct")
    return array[0, 0]


def _field_text(value: Any, name: str, field: str) -> str:
    try:
        return _mat_text(getattr(value, field))
    except AttributeError as exc:
        raise ValueError(f"{name} is missing {field}") from exc


def _field_number(value: Any, name: str, field: str) -> float:
    try:
        array = np.asarray(getattr(value, field))
    except AttributeError as exc:
        raise ValueError(f"{name} is missing {field}") from exc
    if array.size != 1 or not np.issubdtype(array.dtype, np.number):
        raise ValueError(f"{name}.{field} must be a numeric scalar")
    number = float(array.reshape(-1)[0])
    if not math.isfinite(number):
        raise ValueError(f"{name}.{field} must be finite")
    return number


def _field_bool(value: Any, name: str, field: str) -> bool:
    number = _field_number(value, name, field)
    if number not in (0.0, 1.0):
        raise ValueError(f"{name}.{field} must encode logical false/true")
    return bool(number)


def _load_a1_reader(root: Path) -> Any:
    path = _repo_file(root, A1_READER)
    if _sha256(path) != A1_READER_SHA256:
        raise ValueError("the pinned A1 cache reader source changed")
    spec = importlib.util.spec_from_file_location("_cm18_a1_cache_reader_pinned", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load pinned A1 cache reader")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _check_scope(receipt: dict[str, Any], mode: str, expected_count: int) -> None:
    if receipt.get("schema") != "CM18_REPAIRED_T2_EXPORT_RECEIPT_V1" or receipt.get("status") != "PASS":
        raise ValueError(f"{mode} receipt is not a finalized PASS receipt")
    if receipt.get("source_manifest_path") != SOURCE_MANIFEST:
        raise ValueError(f"{mode} receipt source-manifest path mismatch")
    if receipt.get("mode") != mode or int(receipt.get("scene_count", -1)) != expected_count:
        raise ValueError(f"{mode} receipt count/mode mismatch")
    if int(receipt.get("event_count_per_scene", -1)) != 1999:
        raise ValueError(f"{mode} receipt does not record 1999 events per scene")
    for key in ("Plant_calls", "training_steps", "optimizer_steps"):
        if int(receipt.get(key, -1)) != 0:
            raise ValueError(f"{mode} receipt has nonzero {key}")
    if receipt.get("TEST_accessed") is not False or receipt.get("old_A1_H5_read") is not False:
        raise ValueError(f"{mode} receipt does not certify TEST/H5 isolation")
    if receipt.get("source_manifest_sha256", "").lower() != SOURCE_MANIFEST_SHA256:
        raise ValueError(f"{mode} receipt source manifest identity mismatch")


def _validate_c5_val_only(root: Path, source_manifest: dict[str, Any],
                          source_rows: list[dict[str, Any]]) -> dict[str, Any]:
    candidate_path = source_manifest["source_pins"]["val_candidates_path"]
    candidate_sha = source_manifest["source_pins"]["val_candidates_sha256"].lower()
    _pinned_json(root, candidate_path, candidate_sha)
    c5, sha = _pinned_json(root, C5_VAL48_MANIFEST, C5_VAL48_MANIFEST_SHA256)
    if (c5.get("schema") != "C5_MATCHED_VAL48_EVENT_CACHE_MANIFEST_V3"
            or c5.get("status") != "PASS" or c5.get("training_eligible") is not False):
        raise ValueError("C5 VAL48 artifact is not a validation-only PASS manifest")
    if c5.get("candidate_manifest_sha256", "").lower() != candidate_sha:
        raise ValueError("C5 VAL48 candidate-manifest identity differs from the repair source pin")
    c5_rows = c5.get("scenes")
    if (not isinstance(c5_rows, list) or len(c5_rows) != 48
            or any(row.get("status") != "PASS" for row in c5_rows)):
        raise ValueError("C5 VAL48 artifact must contain exactly 48 validation candidates")
    if any(not str(row.get("scene_id", "")).startswith("DL1018_VAL_") for row in c5_rows):
        raise ValueError("C5 VAL48 contains a non-VAL row")
    physical_rows = {
        row["scene_id"]: row for row in source_rows
        if row.get("source_action") == "REBUILD_FROM_CORRECTED_T2_B_RAW"
        and row.get("corrected_source", {}).get("class") == "CORRECTED_T2_VAL_PHYSICAL_B"
    }
    if len(physical_rows) != 16:
        raise ValueError("source manifest does not identify exactly 16 corrected T2 VAL physical-B rows")
    c5_by_id = {row.get("scene_id"): row for row in c5_rows}
    if len(c5_by_id) != 48:
        raise ValueError("duplicate scene identity in C5 VAL48 manifest")
    for scene_id, planned in physical_rows.items():
        row = c5_by_id.get(scene_id)
        if row is None or row.get("status") != "PASS":
            raise ValueError(f"C5 VAL48 is missing PASS source binding for {scene_id}")
        raw_sha = planned["corrected_source"]["raw"]["sha256"].lower()
        if row.get("physical_B_source_sha256", "").lower() != raw_sha:
            raise ValueError(f"C5 physical-B source SHA mismatch for {scene_id}")
    return {
        "path": C5_VAL48_MANIFEST,
        "sha256": sha,
        "scene_count": 48,
        "training_eligible": False,
        "used_as_training_rows": False,
        "purpose": "bind the 16 corrected T2 VAL physical-B sources; C5 VAL caches are not imported",
    }


def _source_rows(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    source, _ = _pinned_json(root, SOURCE_MANIFEST, SOURCE_MANIFEST_SHA256)
    a1, _ = _pinned_json(root, A1_MANIFEST, A1_MANIFEST_SHA256)
    input_manifest, _ = _pinned_json(root, INPUT_MANIFEST, INPUT_MANIFEST_SHA256)
    if (source.get("schema") != "CM18_REFERENCE_REPAIRED_SOURCE_MANIFEST_V1"
            or source.get("status") != "PREPARED_METADATA_ONLY_RAW_AND_CACHE_EXPORT_PENDING"
            or source.get("counts") != {
                "all_scenes": 816, "reuse_a1_t1_t3_cache": 544, "rebuild_corrected_t2": 272,
                "t2_train_g3_b": 256, "t2_val_physical_b": 16, "screen4_fixed": 4,
            }):
        raise ValueError("source manifest schema/counts differ from the frozen 816-scene plan")
    if (a1.get("schema") != "CM18_A1_DATASET_MANIFEST_V1" or a1.get("mode") != "ALL816"
            or a1.get("input_manifest_sha256", "").lower() != INPUT_MANIFEST_SHA256
            or a1.get("scene_count") != 816 or a1.get("qualified_count") != 816
            or a1.get("failed_count") != 0 or a1.get("TEST_accessed") is not False):
        raise ValueError("pinned A1 ALL816 manifest is not fully qualified")
    if input_manifest.get("schema") != "ATTITUDE_CM18_A1_INPUT_MANIFEST_V1":
        raise ValueError("pinned A1 input manifest schema changed")
    src_rows, a1_rows = source.get("scenes"), a1.get("rows")
    if not isinstance(src_rows, list) or len(src_rows) != 816 or not isinstance(a1_rows, list) or len(a1_rows) != 816:
        raise ValueError("source/A1 manifest must each have 816 rows")
    for ordinal, (src, old) in enumerate(zip(src_rows, a1_rows), start=1):
        if (src.get("ordinal") != ordinal or src.get("scene_id") != old.get("scene_id")
                or src.get("split") != old.get("split")):
            raise ValueError(f"A1 order/split identity mismatch at ordinal {ordinal}")
    if sum(row.get("split") == "TRAIN" for row in src_rows) != 768 or sum(row.get("split") == "VAL" for row in src_rows) != 48:
        raise ValueError("source manifest split counts are not 768 TRAIN / 48 VAL")
    return source, src_rows, a1, a1_rows


def _check_receipts(root: Path, source: dict[str, Any], source_rows: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    screen, screen_sha = _pinned_json(root, SCREEN4_RECEIPT, SCREEN4_RECEIPT_SHA256)
    _check_scope(screen, "SCREEN4", 4)
    screen_audit, _ = _pinned_json(root, SCREEN4_AUDIT, SCREEN4_AUDIT_SHA256)
    if (screen_audit.get("schema") != "ROOT_REFERENCE_REPAIRED_SCREEN4_CACHE_AUDIT_V1"
            or screen_audit.get("status") != "PASS"
            or screen_audit.get("source_manifest_sha256", "").lower() != SOURCE_MANIFEST_SHA256
            or screen_audit.get("receipt_sha256", "").lower() != screen_sha
            or screen_audit.get("event_count") != 7996
            or screen_audit.get("scope", {}).get("Plant_calls") != 0
            or screen_audit.get("scope", {}).get("optimizer_steps") != 0
            or screen_audit.get("scope", {}).get("TEST_accessed") is not False
            or screen_audit.get("scope", {}).get("all816_certified") is not False):
        raise ValueError("pinned SCREEN4 independent audit no longer certifies the four-cache rehearsal")

    rest, rest_sha = _pinned_json(root, REST268_RECEIPT, REST268_RECEIPT_SHA256)
    _check_scope(rest, "REST268", 268)
    expected = {row["scene_id"] for row in source_rows
                if row.get("source_action") == "REBUILD_FROM_CORRECTED_T2_B_RAW"}
    screen_ids = {row.get("scene_id") for row in screen.get("rows", [])}
    if screen_ids != set(source.get("screen4_scene_ids", [])) or len(screen_ids) != 4:
        raise ValueError("SCREEN4 finalized receipt scene set differs from the frozen selection")
    rest_ids = {row.get("scene_id") for row in rest.get("rows", [])}
    if len(rest.get("rows", [])) != 268 or len(rest_ids) != 268 or rest_ids != expected - screen_ids:
        raise ValueError("REST268 finalized receipt does not cover exactly the remaining T2 rows")
    by_id: dict[str, dict[str, Any]] = {}
    for row in [*screen["rows"], *rest["rows"]]:
        scene_id = row.get("scene_id")
        if scene_id in by_id:
            raise ValueError(f"duplicate repaired export receipt row: {scene_id}")
        by_id[scene_id] = row
    return by_id, screen, {"path": REST268_RECEIPT, "sha256": rest_sha, "receipt": rest}


def _validate_repaired_scene(root: Path, source_row: dict[str, Any], a1_row: dict[str, Any],
                             receipt_row: dict[str, Any], source_manifest: dict[str, Any],
                             reader_source_files: dict[str, str]) -> tuple[dict[str, Any], dict[str, Any]]:
    scene_id, split = source_row["scene_id"], source_row["split"]
    planned = source_row["corrected_source"]
    if (source_row.get("source_action") != "REBUILD_FROM_CORRECTED_T2_B_RAW"
            or planned.get("role") != "B" or planned.get("eligible") is not True
            or planned.get("runtime_scene_id") != scene_id + "_ACC_FIX_V1"):
        raise ValueError(f"{scene_id}: repaired source-plan identity mismatch")
    if (receipt_row.get("scene_id") != scene_id or receipt_row.get("split") != split
            or receipt_row.get("status") != "PASS"):
        raise ValueError(f"{scene_id}: terminal receipt row is not PASS for its split")
    if receipt_row.get("raw_sha256", "").lower() != planned["raw"]["sha256"].lower():
        raise ValueError(f"{scene_id}: receipt corrected raw SHA differs from source plan")
    if receipt_row.get("run_start_sha256", "").lower() != planned["run_start"]["sha256"].lower():
        raise ValueError(f"{scene_id}: receipt run_start SHA differs from source plan")
    cache_rel = source_row["cache"]["path"]
    if cache_rel != receipt_row.get("cache_path") or not cache_rel.startswith("data/events/attitude_cm18_datarepair_20261024/"):
        raise ValueError(f"{scene_id}: repaired cache path is outside the dedicated cache root")
    if (source_row["cache"].get("status") != "NOT_EXPORTED"
            or source_row["cache"].get("use_as_repaired_label") is not True):
        raise ValueError(f"{scene_id}: prepared source manifest cache-plan flags changed")
    path = _repo_file(root, cache_rel)
    size = int(receipt_row["cache_bytes"])
    sha = str(receipt_row["cache_sha256"]).lower()
    if path.stat().st_size != size or _sha256(path) != sha:
        raise ValueError(f"{scene_id}: repaired cache receipt size/SHA mismatch")

    mat = loadmat(path, squeeze_me=False, struct_as_record=False, variable_names=REPAIRED_VARIABLES)
    missing = set(REPAIRED_VARIABLES) - set(mat)
    if missing:
        raise ValueError(f"{scene_id}: repaired MAT is missing {sorted(missing)}")
    x = np.asarray(mat["X18"])
    target = np.asarray(mat["target_raw"])
    event_time = np.asarray(mat["event_time_s"])
    phase = np.asarray(mat["phase_code"])
    plant_index = np.asarray(mat["plant_index"])
    event_index = np.asarray(mat["event_index"])
    n = 1999
    if x.shape != (n, 18) or x.dtype != np.float64:
        raise ValueError(f"{scene_id}: X18 must be float64 (1999,18)")
    if target.shape != (n, 3) or target.dtype != np.float64:
        raise ValueError(f"{scene_id}: target_raw must be float64 (1999,3)")
    if event_time.shape != (n, 1) or event_time.dtype != np.float64:
        raise ValueError(f"{scene_id}: event_time_s must be float64 (1999,1)")
    if phase.shape != (n, 1) or phase.dtype != np.uint8:
        raise ValueError(f"{scene_id}: phase_code must be uint8 (1999,1)")
    if plant_index.shape != (n, 1) or not np.issubdtype(plant_index.dtype, np.integer):
        raise ValueError(f"{scene_id}: plant_index must be integer (1999,1)")
    if event_index.shape != (n, 1) or event_index.dtype != np.uint16:
        raise ValueError(f"{scene_id}: event_index must be uint16 (1999,1)")
    if not all(np.isfinite(v).all() for v in (x, target, event_time)):
        raise ValueError(f"{scene_id}: repaired cache contains non-finite arrays")
    if not np.array_equal(event_index.reshape(-1), EXPECTED_EVENT_INDEX):
        raise ValueError(f"{scene_id}: event_index is not 1..1999")
    idx = plant_index.reshape(-1).astype(np.int64)
    if not np.array_equal(idx, EXPECTED_PLANT_INDEX):
        raise ValueError(f"{scene_id}: plant_index is not 11:10:19991")
    t = event_time.reshape(-1)
    if np.max(np.abs(t - (idx - 1) * 0.001)) > 1e-12 or np.any(np.diff(t) <= 0):
        raise ValueError(f"{scene_id}: event timing does not align with plant_index")
    phases = phase.reshape(-1)
    if np.any(phases > 5):
        raise ValueError(f"{scene_id}: phase_code must lie in 0..5")
    if (_mat_text(mat["scene_id"]) != scene_id or _mat_text(mat["split"]) != split
            or _mat_text(mat["cache_schema"]) != "CM18_REPAIRED_EVENT_CACHE_V1"):
        raise ValueError(f"{scene_id}: embedded scene/split/cache schema mismatch")

    identity = _mat_struct(mat["input_identity"], "input_identity")
    old_identity = _mat_struct(mat["original_a1_identity"], "original_a1_identity")
    checks = {
        "source_manifest_path": SOURCE_MANIFEST,
        "source_manifest_sha256": SOURCE_MANIFEST_SHA256,
        "canonical_scene_id": scene_id,
        "runtime_scene_id": planned["runtime_scene_id"],
        "split": split,
        "source_class": planned["class"],
        "corrected_raw_path": planned["raw"]["path"],
        "corrected_raw_sha256": planned["raw"]["sha256"],
        "corrected_run_start_path": planned["run_start"]["path"],
        "corrected_run_start_sha256": planned["run_start"]["sha256"],
        "c5_snapshot_sha256": source_manifest["source_pins"]["c5_snapshot_sha256"],
        "train_cfg_opts_audit_sha256": source_manifest["source_pins"]["train_cfg_opts_audit_sha256"],
        "corrected_reference_helper_sha256": source_manifest["source_pins"]["corrected_reference_helper_sha256"],
        "extractor_sha256": reader_source_files["experiments/attitude_cm18_datarepair_20261024/extract_cm18_events_v1.m"],
    }
    for field, expected in checks.items():
        if _field_text(identity, "input_identity", field).lower() != str(expected).lower():
            raise ValueError(f"{scene_id}: input_identity.{field} mismatch")
    if _field_bool(identity, "input_identity", "old_A1_H5_read"):
        raise ValueError(f"{scene_id}: repaired exporter claims it read the old A1 H5")

    manifest_field = _field_text(identity, "input_identity", "corrected_run_start_manifest_field")
    manifest_sha = _field_text(identity, "input_identity", "corrected_run_start_manifest_sha256").lower()
    if planned["class"] == "CORRECTED_T2_VAL_PHYSICAL_B":
        if manifest_field or manifest_sha:
            raise ValueError(f"{scene_id}: C5 physical-B cache must not invent a G3 manifest identity")
    elif planned["class"] == "CORRECTED_T2_TRAIN_B_G3":
        pins = source_manifest["source_pins"]
        if manifest_field == "g3_manifest_sha256":
            expected_manifest_sha = pins["g3_cohort_sha256"].lower()
        elif manifest_field == "manifest_sha256":
            state_path = Path(pins["corrected_train_state_path"])
            if not state_path.is_file() or _sha256(state_path) != pins["corrected_train_state_sha256"].lower():
                raise ValueError("pinned corrected TRAIN state file SHA mismatch")
            state = json.loads(state_path.read_text(encoding="utf-8"))
            expected_manifest_sha = str(state.get("manifest_sha256", "")).lower()
        else:
            raise ValueError(f"{scene_id}: unrecognized corrected TRAIN run_start manifest field")
        if not expected_manifest_sha or manifest_sha != expected_manifest_sha:
            raise ValueError(f"{scene_id}: corrected TRAIN run_start manifest identity mismatch")
    else:
        raise ValueError(f"{scene_id}: unsupported corrected source class")

    old_source = source_row["original_a1_source"]
    old_cache = source_row["original_a1_cache"]
    a1_inputs = a1_row.get("input_sha256", {})
    for source_role, a1_key in (("event_h5", "event_h5"), ("raw_run", "raw_run"), ("run_start", "run_start")):
        if old_source[source_role]["sha256"].lower() != str(a1_inputs.get(a1_key, "")).lower():
            raise ValueError(f"{scene_id}: planned original A1 {source_role} SHA differs from pinned A1 manifest")
    if (old_cache.get("path") != a1_row.get("cache_path")
            or old_cache.get("sha256", "").lower() != a1_row.get("cache_sha256", "").lower()
            or int(old_cache.get("size_bytes", -1)) != int(a1_row.get("cache_bytes", -2))):
        raise ValueError(f"{scene_id}: planned original A1 cache differs from pinned A1 manifest")
    old_checks = {
        "raw_path": old_source["raw_run"]["path"],
        "raw_sha256": old_source["raw_run"]["sha256"],
        "run_start_path": old_source["run_start"]["path"],
        "run_start_sha256": old_source["run_start"]["sha256"],
        "cache_path": old_cache["path"],
        "cache_sha256": old_cache["sha256"],
        "scene_id": scene_id,
    }
    for field, expected in old_checks.items():
        if _field_text(old_identity, "original_a1_identity", field).lower() != str(expected).lower():
            raise ValueError(f"{scene_id}: original_a1_identity.{field} mismatch")
    if _field_bool(old_identity, "original_a1_identity", "cache_used_as_repaired_label"):
        raise ValueError(f"{scene_id}: old A1 cache is incorrectly marked as the repaired label")

    meta = _mat_struct(mat["export_meta"], "export_meta")
    request_closure = _field_number(meta, "export_meta", "requested_torque_vs_nominal_minus_applied_max_abs_Nm")
    dynamics_residual = _field_number(meta, "export_meta", "true_dynamics_equation_residual_max_abs_Nm")
    if request_closure < 0 or request_closure > 1e-8:
        raise ValueError(f"{scene_id}: request-torque closure metadata exceeds 1e-8 Nm")
    if dynamics_residual < 0 or dynamics_residual > 1e-12:
        raise ValueError(f"{scene_id}: dynamics residual metadata exceeds 1e-12 Nm")

    scene = {
        "scene_id": scene_id,
        "split": split,
        "X18": x,
        "target_raw": target,
        "event_time_s": event_time,
        "phase_code": phase,
        "plant_index": plant_index,
    }
    row_result = {
        "ordinal": int(source_row["ordinal"]),
        "scene_id": scene_id,
        "split": split,
        "status": "PASS",
        "qualified": True,
        "cache_schema": "CM18_REPAIRED_EVENT_CACHE_V1",
        "cache_path": cache_rel,
        "cache_sha256": sha,
        "cache_bytes": size,
        "source_action": source_row["source_action"],
        "corrected_source_class": planned["class"],
        "corrected_raw_path": planned["raw"]["path"],
        "corrected_raw_sha256": planned["raw"]["sha256"],
        "corrected_run_start_path": planned["run_start"]["path"],
        "corrected_run_start_sha256": planned["run_start"]["sha256"],
        "original_a1_input_sha256": a1_row["input_sha256"],
        "original_a1_source": old_source,
        "original_a1_cache_path": old_cache["path"],
        "original_a1_cache_sha256": old_cache["sha256"],
        "original_a1_cache_used_as_repaired_label": False,
        "event_count": n,
        "event_index_first_last": [1, 1999],
        "plant_index_first_last": [11, 19991],
        "phase_code_counts": {str(int(code)): int(np.count_nonzero(phases == code)) for code in np.unique(phases)},
        "requested_torque_closure_max_abs_Nm_metadata": request_closure,
        "requested_torque_closure_tolerance_Nm": 1e-8,
        "true_dynamics_equation_residual_max_abs_Nm_metadata": dynamics_residual,
        "true_dynamics_equation_residual_tolerance_Nm": 1e-12,
    }
    return scene, row_result


def build_dataset_manifest(repo_root: Path, output_relative_path: str = DEFAULT_OUTPUT) -> dict[str, Any]:
    """Build a new immutable manifest from finalized receipts and verified caches."""
    root = Path(repo_root).resolve(strict=True)
    source, source_rows, a1, a1_rows = _source_rows(root)
    val_binding = _validate_c5_val_only(root, source, source_rows)
    receipt_by_id, screen, rest_meta = _check_receipts(root, source, source_rows)
    receipt_meta = {
        "SCREEN4": {"path": SCREEN4_RECEIPT, "sha256": SCREEN4_RECEIPT_SHA256, "scene_count": 4},
        "REST268": {"path": REST268_RECEIPT, "sha256": rest_meta["sha256"], "scene_count": 268},
    }
    a1_reader = _load_a1_reader(root)
    extractor = next((r for r in source["source_files"]
                      if r.get("path") == "experiments/attitude_cm18_datarepair_20261024/extract_cm18_events_v1.m"), None)
    if not extractor:
        raise ValueError("source manifest has no pinned pure event extractor")
    source_file_pins = _source_file_hashes(root)
    if source_file_pins.get(extractor["path"]) != extractor["sha256"].lower():
        raise ValueError("extractor source pin is malformed")

    # REST is accepted only from its final receipt. No progress file is consulted.
    if _sha256(_repo_file(root, REST268_RECEIPT)) != rest_meta["sha256"]:
        raise ValueError("REST268 receipt changed during source preparation")
    old_by_id = {row["scene_id"]: row for row in a1_rows}
    validated_rows: list[dict[str, Any]] = []
    cache_scenes: dict[str, dict[str, Any]] = {}
    failed = 0
    for source_row in source_rows:
        scene_id = source_row["scene_id"]
        try:
            if source_row.get("source_action") == "REUSE_A1_CERTIFIED_CACHE":
                old_row = old_by_id[scene_id]
                planned_cache = source_row["original_a1_cache"]
                old_source = source_row["original_a1_source"]
                old_inputs = old_row.get("input_sha256", {})
                if (source_row["cache"] != planned_cache or planned_cache.get("status") != "PASS"
                        or planned_cache.get("use_as_repaired_label") is not True
                        or old_row.get("cache_path") != planned_cache.get("path")
                        or old_row.get("cache_sha256", "").lower() != planned_cache.get("sha256", "").lower()
                        or int(old_row.get("cache_bytes", -1)) != int(planned_cache.get("size_bytes", -2))):
                    raise ValueError("planned reuse cache differs from the certified A1 ALL816 row")
                if any(old_source[key]["sha256"].lower() != str(old_inputs.get(key, "")).lower()
                       for key in ("event_h5", "raw_run", "run_start")):
                    raise ValueError("planned reused A1 source SHA differs from its certified manifest row")
                scene = a1_reader._read_scene(root, old_row, INPUT_MANIFEST_SHA256)
                cache_rel = str(old_row["cache_path"])
                if not cache_rel.startswith("reports/attitude_cm18_a1_20261024/data_preparation_v1/events_"):
                    raise ValueError("A1 cache path is outside the certified A1 cache roots")
                result = {
                    "ordinal": int(source_row["ordinal"]), "scene_id": scene_id,
                    "split": source_row["split"], "status": "PASS", "qualified": True,
                    "cache_schema": "CM18_A1_EVENT_CACHE_V1", "cache_path": cache_rel,
                    "cache_sha256": old_row["cache_sha256"].lower(), "cache_bytes": int(old_row["cache_bytes"]),
                    "source_action": source_row["source_action"], "corrected_source_class": "ORIGINAL_A1_T1_T3",
                    "original_a1_input_sha256": old_row["input_sha256"],
                    "original_a1_source": source_row["original_a1_source"],
                    "original_a1_cache_path": cache_rel, "original_a1_cache_sha256": old_row["cache_sha256"].lower(),
                    "original_a1_cache_used_as_repaired_label": True,
                    "event_count": 1999, "event_index_first_last": None,
                    "plant_index_first_last": [11, 19991],
                    "phase_code_counts": {
                        str(int(code)): int(np.count_nonzero(scene["phase_code"].reshape(-1) == code))
                        for code in np.unique(scene["phase_code"])
                    },
                }
            elif source_row.get("source_action") == "REBUILD_FROM_CORRECTED_T2_B_RAW":
                receipt_row = receipt_by_id[scene_id]
                scene, result = _validate_repaired_scene(
                    root, source_row, old_by_id[scene_id], receipt_row, source, source_file_pins
                )
            else:
                raise ValueError("unsupported source_action")
            cache_scenes[scene_id] = scene
            validated_rows.append(result)
        except Exception as exc:
            failed += 1
            validated_rows.append({
                "ordinal": int(source_row["ordinal"]), "scene_id": scene_id,
                "split": source_row["split"], "status": "FAIL", "qualified": False,
                "source_action": source_row.get("source_action", ""),
                "failure_type": type(exc).__name__, "failure_message": str(exc),
            })

    train_count = sum(row["split"] == "TRAIN" and row["status"] == "PASS" for row in validated_rows)
    val_count = sum(row["split"] == "VAL" and row["status"] == "PASS" for row in validated_rows)
    qualified = len(validated_rows) == 816 and failed == 0 and train_count == 768 and val_count == 48
    manifest = {
        "schema": "CM18_B_REF_REPAIRED_ALL816_DATASET_MANIFEST_V1",
        "status": "PASS" if qualified else "FAIL",
        "mode": "ALL816_REPAIRED_LABELS",
        "scene_count": len(validated_rows),
        "qualified_count": len(validated_rows) - failed,
        "failed_count": failed,
        "split_counts": {"TRAIN": train_count, "VAL": val_count},
        "training_eligible": qualified,
        "TEST_accessed": False,
        "Plant_calls": 0,
        "training_steps": 0,
        "optimizer_steps": 0,
        "input_manifest_path": INPUT_MANIFEST,
        "input_manifest_sha256": INPUT_MANIFEST_SHA256,
        "a1_dataset_manifest_path": A1_MANIFEST,
        "a1_dataset_manifest_sha256": A1_MANIFEST_SHA256,
        "source_manifest_path": SOURCE_MANIFEST,
        "source_manifest_sha256": SOURCE_MANIFEST_SHA256,
        "source_repair_plan_counts": source["counts"],
        "merge_reader_source_path": "experiments/attitude_cm18_datarepair_20261024/cache_reader_cm18_b_ref_repaired_v1.py",
        "merge_reader_source_sha256": _sha256(Path(__file__).resolve()),
        "a1_reader_source_path": A1_READER,
        "a1_reader_source_sha256": A1_READER_SHA256,
        "receipt_pins": receipt_meta,
        "validation_only_source_binding": val_binding,
        "cache_row_validation_attempts": len(validated_rows),
        "cache_validated_scene_count": len(cache_scenes),
        "training_sampling": {
            "TRAIN_rows_per_scene": 400,
            "TRAIN_zero_based_indices": "0,5,...,1995",
            "VAL_rows_per_scene": 1999,
            "application": "reader returns full events; frozen trainer applies TRAIN stride and uses all VAL events",
        },
        "closure_metadata_interpretation": (
            "request-closure is cache metadata; true_dynamics_equation_residual is the same linear-solve residual, "
            "not an independent physical validation"
        ),
        "rows": validated_rows,
    }
    out = _repo_output(root, output_relative_path)
    if out.exists():
        raise FileExistsError(f"refusing to overwrite existing manifest: {output_relative_path}")
    out.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive create keeps old attempts intact. A FAIL manifest is still explicit evidence.
    with out.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    return manifest


def _read_repaired_scene(root: Path, row: dict[str, Any], source_by_id: dict[str, Any],
                         a1_by_id: dict[str, Any], source_manifest: dict[str, Any],
                         source_file_hashes: dict[str, str]) -> dict[str, Any]:
    path = _repo_file(root, row["cache_path"])
    if path.stat().st_size != int(row["cache_bytes"]) or _sha256(path) != row["cache_sha256"].lower():
        raise ValueError(f"{row['scene_id']}: final repaired cache size/SHA mismatch")
    source_row = source_by_id[row["scene_id"]]
    receipt_row = {
        "scene_id": row["scene_id"], "split": row["split"], "status": "PASS",
        "cache_path": row["cache_path"], "cache_bytes": row["cache_bytes"],
        "cache_sha256": row["cache_sha256"],
        "raw_sha256": row["corrected_raw_sha256"],
        "run_start_sha256": row["corrected_run_start_sha256"],
    }
    scene, _ = _validate_repaired_scene(
        root, source_row, a1_by_id[row["scene_id"]], receipt_row,
        source_manifest, source_file_hashes,
    )
    return scene


def _load_json_at(root: Path, relative: str) -> dict[str, Any]:
    return json.loads(_repo_file(root, relative).read_text(encoding="utf-8"))


def _source_file_hashes(root: Path) -> dict[str, str]:
    source = _load_json_at(root, SOURCE_MANIFEST)
    pinned = {str(row["path"]): str(row["sha256"]).lower() for row in source["source_files"]}
    for relative, expected in pinned.items():
        candidate = Path(relative)
        path = candidate.resolve(strict=True) if candidate.is_absolute() else _repo_file(root, relative)
        if not path.is_file() or _sha256(path) != expected:
            raise ValueError(f"pinned repair source changed: {relative}")
    helper_path = Path(source["source_pins"]["corrected_reference_helper_path"])
    if (not helper_path.is_file()
            or _sha256(helper_path) != source["source_pins"]["corrected_reference_helper_sha256"].lower()):
        raise ValueError("pinned corrected-reference helper changed")
    return pinned


def load_qualified_split(
    repo_root: Path,
    manifest_relative_path: str,
    split: str,
    expected_manifest_sha256: str,
) -> list[dict[str, Any]]:
    """Load verified scene arrays with the same keys returned by the A1 reader."""
    if split not in ("TRAIN", "VAL"):
        raise ValueError("only TRAIN and VAL are permitted")
    root = Path(repo_root).resolve(strict=True)
    manifest_path = _repo_file(root, manifest_relative_path)
    manifest_sha = _sha256(manifest_path)
    if manifest_sha != expected_manifest_sha256.lower():
        raise ValueError("merged dataset manifest SHA256 mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (manifest.get("schema") != "CM18_B_REF_REPAIRED_ALL816_DATASET_MANIFEST_V1"
            or manifest.get("mode") != "ALL816_REPAIRED_LABELS"
            or manifest.get("status") != "PASS" or manifest.get("training_eligible") is not True
            or manifest.get("TEST_accessed") is not False or manifest.get("failed_count") != 0
            or manifest.get("scene_count") != 816 or manifest.get("qualified_count") != 816
            or manifest.get("cache_validated_scene_count") != 816
            or manifest.get("split_counts") != {"TRAIN": 768, "VAL": 48}):
        raise ValueError("merged dataset manifest is not a fully qualified ALL816 training release")
    rows = manifest.get("rows")
    if not isinstance(rows, list) or len(rows) != 816:
        raise ValueError("merged dataset manifest row count mismatch")
    source, source_rows, a1, _ = _source_rows(root)
    val_binding = _validate_c5_val_only(root, source, source_rows)
    if manifest.get("validation_only_source_binding") != val_binding:
        raise ValueError("merged manifest C5 VAL48 validation-only binding mismatch")
    if [row.get("scene_id") for row in rows] != [row["scene_id"] for row in source_rows]:
        raise ValueError("merged dataset manifest no longer preserves A1 scene order")
    source_by_id = {row["scene_id"]: row for row in source_rows}
    selected = [row for row in rows if row.get("split") == split]
    if len(selected) != (768 if split == "TRAIN" else 48):
        raise ValueError(f"merged manifest has an unexpected {split} split count")
    a1_reader = _load_a1_reader(root)
    a1_by_id = {row["scene_id"]: row for row in a1["rows"]}
    source_file_hashes = _source_file_hashes(root)
    result: list[dict[str, Any]] = []
    for row in selected:
        if row.get("status") != "PASS" or row.get("qualified") is not True:
            raise ValueError(f"unqualified merged row: {row.get('scene_id')}")
        if row.get("cache_schema") == "CM18_A1_EVENT_CACHE_V1":
            a1_row = a1_by_id[row["scene_id"]]
            if (row.get("cache_path") != a1_row.get("cache_path")
                    or row.get("cache_sha256", "").lower() != a1_row.get("cache_sha256", "").lower()
                    or int(row.get("cache_bytes", -1)) != int(a1_row.get("cache_bytes", -2))):
                raise ValueError(f"{row['scene_id']}: merged legacy cache identity differs from pinned A1 manifest")
            scene = a1_reader._read_scene(root, a1_row, INPUT_MANIFEST_SHA256)
            if (_sha256(_repo_file(root, row["cache_path"])) != row["cache_sha256"].lower()
                    or _repo_file(root, row["cache_path"]).stat().st_size != int(row["cache_bytes"])):
                raise ValueError(f"{row['scene_id']}: legacy cache identity changed")
        elif row.get("cache_schema") == "CM18_REPAIRED_EVENT_CACHE_V1":
            scene = _read_repaired_scene(root, row, source_by_id, a1_by_id, source, source_file_hashes)
        else:
            raise ValueError(f"{row.get('scene_id')}: unknown cache schema")
        if scene["scene_id"] != row["scene_id"] or scene["split"] != split:
            raise ValueError("cache identity differs from merged manifest row")
        result.append(scene)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--build-manifest", action="store_true", help="build only after SCREEN4 and REST268 receipts are finalized")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="new repository-relative manifest path; never overwritten")
    args = parser.parse_args()
    if not args.build_manifest:
        parser.error("select --build-manifest")
    manifest = build_dataset_manifest(args.repo_root, args.output)
    print(json.dumps({
        "schema": manifest["schema"], "status": manifest["status"],
        "scene_count": manifest["scene_count"], "qualified_count": manifest["qualified_count"],
        "failed_count": manifest["failed_count"], "split_counts": manifest["split_counts"],
        "cache_validated_scene_count": manifest["cache_validated_scene_count"], "Plant_calls": 0,
        "training_steps": 0, "optimizer_steps": 0, "TEST_accessed": False,
    }, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
