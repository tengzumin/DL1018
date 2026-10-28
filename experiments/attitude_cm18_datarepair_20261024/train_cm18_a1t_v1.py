"""One-shot A1T trainer: direct compensation targets on fixed B TRAIN/VAL."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import random
import shutil
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SEED = 2026102001
STEPS = 60_000
BATCH_SIZE = 512
EVAL_EVERY = 1_000
PROGRESS_EVERY = 100
MAX_OUTPUT_BYTES = 1 << 30
MIN_FREE_BYTES = 30 * 1024 ** 3
TASKBOOK = "reports/attitude_cm18_datarepair_20261024/A1T_TRAINING_TASKBOOK_v1_ZH.md"
TASKBOOK_SHA256 = "2fe158fd370019bfe9e3d95e6b3222e1f4d7829cfa1681bd8dd85d06615102e9"
SOURCE_MANIFEST = "reports/attitude_cm18_datarepair_20261024/B_REF_REPAIRED_SOURCE_MANIFEST_v1.json"
SOURCE_MANIFEST_SHA256 = "0f86b47d01940e7b556b78a9664470531572809aa6857a59fc77d88a33681ec5"
DATASET_MANIFEST = "reports/attitude_cm18_datarepair_20261024/cstar_all816_v1/CSTAR_RELABEL_ALL816_v1.json"
BASE_DATASET_MANIFEST = "reports/attitude_cm18_datarepair_20261024/repaired_all816_v1/DATASET_MANIFEST_v1.json"
BASE_DATASET_MANIFEST_SHA256 = "3f51a1cd0e2e8c3eae79a16df363f2f8d47b0d5dbd876ecd95f1571d9e70a5e0"
A1_DATASET_MANIFEST = "reports/attitude_cm18_a1_20261024/data_preparation_v1/events_all816_v1/DATASET_MANIFEST_v1.json"
A1_DATASET_MANIFEST_SHA256 = "7dd3e1f786f6095ecc2ba56473e5cf0fab6b92cdd42e38a184d6ad1223f36271"
INPUT_MANIFEST = "reports/attitude_cm18_a1_20261024/data_preparation_v1/INPUT_MANIFEST_v1.json"
INPUT_MANIFEST_SHA256 = "a5f7fea9b0918c1449af6fa83929177d3bf7d5e70cb3b71711c40f6338d210a5"
NORMALIZER_AUDIT = "reports/attitude_cm18_datarepair_20261024/ROOT_CSTAR_ALL816_INDEPENDENT_AUDIT_v1.json"
TRAINER = "experiments/attitude_cm18_datarepair_20261024/train_cm18_a1t_v1.py"
READER = "experiments/attitude_cm18_datarepair_20261024/read_cstar_split_v1.py"
NUMPY_MODEL = "experiments/attitude_cm18_a1_20261024/model_cm18_v1.py"
TORCH_MODEL = "experiments/attitude_cm18_a1_20261024/torch_model_cm18_v1.py"
FORMAL_OUTPUT = "experiments/attitude_cm18_datarepair_20261024/training_a1t_v1"
A1R_NORMALIZER = "experiments/attitude_cm18_datarepair_20261024/training_a1r_v1/normalizer.json"
A1R_NORMALIZER_SHA256 = "712627125bf48c3d07cc71de10b13efcb4560b7c31673a179b371cc91d1fe48c"
A1R_INITIAL_PARAMETERS = "experiments/attitude_cm18_datarepair_20261024/training_a1r_v1/initial_parameters.npz"
A1R_INITIAL_PARAMETERS_SHA256 = "ba39ca088db1eddd9f0f029ab1b051f601f6861e33203bdea8a747d2d433dc26"
SOURCE_HASHES = {
    READER: "ced4251719f986d762f29ccced04fb80208a28e7aed1e2fe12d3b504955a4096",
    NUMPY_MODEL: "ad32c4f97bf96c63172547c944d80c45062502f1062b774934e0f7a868720cf6",
    TORCH_MODEL: "bc9fe34fe957cb624438eeccfdfe2ddd38ad40cc9a4e706ce58863c9271d5aa0",
}


def _set_math_environment() -> None:
    if os.environ.get("KMP_DUPLICATE_LIB_OK"):
        raise RuntimeError("KMP_DUPLICATE_LIB_OK is forbidden")
    os.environ["MKL_THREADING_LAYER"] = "SEQUENTIAL"
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
    os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"


_set_math_environment()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _repo_path(root: Path, relative: str, must_exist: bool = True) -> Path:
    base = root.resolve(strict=True)
    path = (base / relative).resolve(strict=must_exist)
    try:
        path.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"path escapes repository root: {relative}") from exc
    return path


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _write_json(path: Path, value: Any) -> None:
    temp = path.with_name(path.name + ".tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    for attempt in range(20):
        try:
            os.replace(temp, path)
            return
        except PermissionError as exc:
            if getattr(exc, "winerror", None) not in (5, 32, 33) or attempt == 19:
                raise
            time.sleep(0.05)


def _append_jsonl(path: Path, value: Any) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")))
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _load_module(root: Path, relative: str, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, _repo_path(root, relative))
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load pinned module: {relative}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _source_modules(root: Path) -> tuple[Any, Any, Any]:
    return (
        _load_module(root, READER, "cm18_a1t_reader_v1"),
        _load_module(root, NUMPY_MODEL, "cm18_a1_numpy_model_v1"),
        _load_module(root, TORCH_MODEL, "cm18_a1_torch_model_v1"),
    )


def _check_source_pins(root: Path, release: dict[str, Any]) -> dict[str, str]:
    expected_paths = {TRAINER, READER, NUMPY_MODEL, TORCH_MODEL}
    rows = release.get("source_files")
    if not isinstance(rows, list) or len(rows) != len(expected_paths):
        raise ValueError("release must pin exactly the trainer, repaired reader, and two frozen A1 model sources")
    observed = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("malformed source_files entry")
        relative, expected = row.get("path"), row.get("sha256")
        if relative not in expected_paths or relative in observed or not isinstance(expected, str):
            raise ValueError("source_files contains an unexpected or duplicate path")
        actual = _sha256(_repo_path(root, relative)).lower()
        if actual != expected.lower():
            raise ValueError(f"release source SHA mismatch: {relative}")
        if relative in SOURCE_HASHES and actual != SOURCE_HASHES[relative]:
            raise ValueError(f"frozen A1/helper source changed: {relative}")
        observed[relative] = actual
    if set(observed) != expected_paths:
        raise ValueError("release source pins are incomplete")
    return observed


def _check_document_pin(root: Path, release: dict[str, Any], key: str, path: str, sha: str) -> None:
    entry = release.get(key)
    if not isinstance(entry, dict) or entry.get("path") != path:
        raise ValueError(f"release {key} path mismatch")
    if str(entry.get("sha256", "")).lower() != sha or _sha256(_repo_path(root, path)) != sha:
        raise ValueError(f"pinned {key} SHA mismatch")


def _validate_dataset_manifest(root: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    if (manifest.get("schema") != "CM18_A1T_CSTAR_RELABEL_ALL816_V1"
            or manifest.get("status") != "PASS"
            or manifest.get("training_eligible") is not True
            or manifest.get("TEST_accessed") is not False
            or manifest.get("scene_count") != 816
            or manifest.get("qualified_count") != 816
            or manifest.get("failed_count") != 0
            or manifest.get("split_counts") != {"TRAIN": 768, "VAL": 48}):
        raise ValueError("C* ALL816 manifest is not a complete, eligible PASS dataset")
    scope = manifest.get("scope")
    if (not isinstance(scope, dict) or scope.get("plant_calls") != 0
            or scope.get("engine_calls") != 0 or scope.get("training_steps") != 0
            or scope.get("optimizer_steps") != 0 or scope.get("TEST_accessed") is not False):
        raise ValueError("C* relabel manifest contains an invalid preparation scope")
    identities = (
        ("source_manifest_path", SOURCE_MANIFEST, "source_manifest_sha256", SOURCE_MANIFEST_SHA256),
        ("dataset_manifest_path", BASE_DATASET_MANIFEST,
         "dataset_manifest_sha256", BASE_DATASET_MANIFEST_SHA256),
    )
    for path_key, path, sha_key, sha in identities:
        if (manifest.get(path_key) != path or str(manifest.get(sha_key, "")).lower() != sha
                or _sha256(_repo_path(root, path)).lower() != sha):
            raise ValueError(f"C* dataset lineage mismatch for {path}")
    rows = manifest.get("rows")
    if not isinstance(rows, list) or len(rows) != 816:
        raise ValueError("C* manifest must contain 816 rows")
    ids, splits, counts = [], [], {"TRAIN": 0, "VAL": 0}
    for row in rows:
        if (not isinstance(row, dict) or row.get("status") != "PASS"
                or row.get("qualified") is not True or row.get("split") not in counts
                or not isinstance(row.get("scene_id"), str)
                or row.get("cache_schema") != "CM18_CSTAR_LABEL_CACHE_V1"):
            raise ValueError("C* manifest contains an invalid scene row")
        for path_key, sha_key, bytes_key in (
                ("cache_path", "cache_sha256", "cache_bytes"),
                ("input_cache_path", "input_cache_sha256", "input_cache_bytes")):
            if (not isinstance(row.get(path_key), str) or not isinstance(row.get(sha_key), str)
                    or len(row[sha_key]) != 64
                    or not isinstance(row.get(bytes_key), int) or isinstance(row[bytes_key], bool)
                    or row[bytes_key] <= 0):
                raise ValueError(f"invalid {path_key} identity for {row.get('scene_id')}")
        ids.append(row["scene_id"])
        splits.append(row["split"])
        counts[row["split"]] += 1
    if len(set(ids)) != 816 or counts != {"TRAIN": 768, "VAL": 48}:
        raise ValueError("C* manifest has duplicate rows or wrong split counts")
    base = _load_json(_repo_path(root, BASE_DATASET_MANIFEST))
    if _sha256(_repo_path(root, A1_DATASET_MANIFEST)).lower() != A1_DATASET_MANIFEST_SHA256:
        raise ValueError("frozen A1 ALL816 manifest SHA mismatch")
    a1 = _load_json(_repo_path(root, A1_DATASET_MANIFEST))
    if (base.get("schema") != "CM18_B_REF_REPAIRED_ALL816_DATASET_MANIFEST_V1"
            or base.get("status") != "PASS" or base.get("training_eligible") is not True
            or base.get("TEST_accessed") is not False or base.get("Plant_calls") != 0
            or base.get("training_steps") != 0 or base.get("optimizer_steps") != 0
            or base.get("scene_count") != 816 or base.get("qualified_count") != 816
            or base.get("failed_count") != 0 or base.get("split_counts") != {"TRAIN": 768, "VAL": 48}
            or base.get("input_manifest_path") != INPUT_MANIFEST
            or base.get("input_manifest_sha256") != INPUT_MANIFEST_SHA256
            or base.get("a1_dataset_manifest_path") != A1_DATASET_MANIFEST
            or base.get("a1_dataset_manifest_sha256") != A1_DATASET_MANIFEST_SHA256):
        raise ValueError("pinned B_REF_REPAIRED base dataset metadata/lineage mismatch")
    if (_sha256(_repo_path(root, INPUT_MANIFEST)).lower() != INPUT_MANIFEST_SHA256
            or _sha256(_repo_path(root, SOURCE_MANIFEST)).lower() != SOURCE_MANIFEST_SHA256):
        raise ValueError("pinned input/source manifest SHA mismatch")
    source = _load_json(_repo_path(root, SOURCE_MANIFEST))
    source_scenes = source.get("scenes")
    if (source.get("schema") != "CM18_REFERENCE_REPAIRED_SOURCE_MANIFEST_V1"
            or not isinstance(source_scenes, list) or len(source_scenes) != 816
            or [r.get("scene_id") for r in source_scenes] != ids
            or [r.get("split") for r in source_scenes] != splits):
        raise ValueError("pinned B_REF source plan differs from C* ALL816 order")
    for name, source in (("repaired", base), ("A1", a1)):
        source_rows = source.get("rows")
        if (not isinstance(source_rows, list) or len(source_rows) != 816
                or [r.get("scene_id") for r in source_rows] != ids
                or [r.get("split") for r in source_rows] != splits):
            raise ValueError(f"C* scene order/splits differ from frozen {name} ALL816")
    if (a1.get("schema") != "CM18_A1_DATASET_MANIFEST_V1"
            or a1.get("mode") != "ALL816" or a1.get("TEST_accessed") is not False):
        raise ValueError("frozen A1 ALL816 lineage is invalid")
    return rows

def _check_release(root: Path, release_path: Path, release_sha: str) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    release_path = release_path.resolve(strict=True)
    try:
        release_path.relative_to(root.resolve(strict=True))
    except ValueError as exc:
        raise ValueError("ROOT release must reside inside the repository") from exc
    if _sha256(release_path).lower() != release_sha.lower():
        raise ValueError("ROOT release SHA256 mismatch")
    release = _load_json(release_path)
    if (release.get("schema") != "CM18_A1T_TRAINING_RELEASE_V1"
            or release.get("decision") != "APPROVE_ONE_FORMAL_TRAINING"
            or release.get("seed") != SEED or release.get("optimizer_steps") != STEPS
            or release.get("batch_size") != BATCH_SIZE or release.get("device") != "cuda:0"
            or release.get("output_directory") != FORMAL_OUTPUT):
        raise ValueError("ROOT release does not match the single frozen A1T experiment")
    _check_document_pin(root, release, "taskbook", TASKBOOK, TASKBOOK_SHA256)
    _check_document_pin(root, release, "source_manifest", SOURCE_MANIFEST, SOURCE_MANIFEST_SHA256)
    dataset = release.get("dataset_manifest")
    if not isinstance(dataset, dict) or dataset.get("path") != DATASET_MANIFEST:
        raise ValueError("ROOT release C* dataset manifest path mismatch")
    dataset_sha = str(dataset.get("sha256", "")).lower()
    dataset_path = _repo_path(root, DATASET_MANIFEST)
    if len(dataset_sha) != 64 or _sha256(dataset_path).lower() != dataset_sha:
        raise ValueError("ROOT release final C* manifest SHA mismatch")
    manifest = _load_json(dataset_path)
    rows = _validate_dataset_manifest(root, manifest)
    audit = release.get("normalizer_audit")
    if (not isinstance(audit, dict) or not isinstance(audit.get("path"), str)
            or not isinstance(audit.get("sha256"), str) or len(audit["sha256"]) != 64):
        raise ValueError("ROOT release must pin the independent C* normalizer audit")
    if (audit["path"] != NORMALIZER_AUDIT
            or _sha256(_repo_path(root, audit["path"])).lower() != audit["sha256"].lower()):
        raise ValueError("ROOT release C* normalizer audit pin mismatch")
    for key, path, sha in (
            ("a1r_normalizer", A1R_NORMALIZER, A1R_NORMALIZER_SHA256),
            ("a1r_initial_parameters", A1R_INITIAL_PARAMETERS, A1R_INITIAL_PARAMETERS_SHA256)):
        _check_document_pin(root, release, key, path, sha)
    source_hashes = _check_source_pins(root, release)
    return {
        "release_path": str(release_path),
        "release_sha256": release_sha.lower(),
        "taskbook_sha256": TASKBOOK_SHA256,
        "source_manifest_sha256": SOURCE_MANIFEST_SHA256,
        "dataset_manifest_path": DATASET_MANIFEST,
        "dataset_manifest_sha256": dataset_sha,
        "normalizer_audit_path": audit["path"],
        "normalizer_audit_sha256": audit["sha256"].lower(),
        "a1r_normalizer_sha256": A1R_NORMALIZER_SHA256,
        "a1r_initial_parameters_sha256": A1R_INITIAL_PARAMETERS_SHA256,
        "source_files": source_hashes,
    }, manifest, rows


def _validate_scenes(scenes: list[dict[str, Any]], rows: list[dict[str, Any]], split: str, np: Any) -> list[dict[str, Any]]:
    selected = [row for row in rows if row["split"] == split]
    expected_ids = [row["scene_id"] for row in selected]
    if len(scenes) != len(expected_ids) or [scene.get("scene_id") for scene in scenes] != expected_ids:
        raise ValueError(f"{split} reader scene order/coverage differs from manifest")
    expected_time = np.arange(1, 2000, dtype=np.float64) * 0.01
    expected_plant = np.arange(11, 20000, 10, dtype=np.int64)
    result = []
    for scene, row in zip(scenes, selected, strict=True):
        if scene.get("split") != split or scene.get("scene_id") != row["scene_id"]:
            raise ValueError("reader returned a scene in the wrong split")
        x = np.asarray(scene["X18"], dtype=np.float64)
        y = np.asarray(scene["target_raw_output_rad_s2"], dtype=np.float64)
        applied = np.asarray(scene["target_applied_acceleration_rad_s2"], dtype=np.float64)
        clipped = np.asarray(scene["target_after_clip_beta_rad_s2"], dtype=np.float64)
        event_time = np.asarray(scene["event_time_s"], dtype=np.float64).reshape(-1)
        phase = np.asarray(scene["phase_code"]).reshape(-1)
        plant = np.asarray(scene["plant_index"]).reshape(-1)
        if (x.shape != (1999, 18) or y.shape != (1999, 3)
                or applied.shape != (1999, 3) or clipped.shape != (1999, 3)
                or event_time.shape != (1999,) or phase.shape != (1999,) or plant.shape != (1999,)
                or not np.isfinite(x).all() or not np.isfinite(y).all()
                or not np.isfinite(applied).all() or not np.isfinite(clipped).all()
                or not np.isfinite(event_time).all() or not np.isfinite(phase).all()
                or not np.isfinite(plant).all()
                or not np.array_equal(plant, expected_plant)
                or np.max(np.abs(event_time - expected_time)) > 1e-10
                or np.any(phase != np.floor(phase))
                or np.any((phase < 0) | (phase > 5))):
            raise ValueError(f"{split} scene arrays/timing are invalid: {row['scene_id']}")
        result.append({
            "scene_id": row["scene_id"], "split": split, "X18": x, "target_raw_output_rad_s2": y,
            "event_time_s": event_time, "phase_code": phase.astype(np.int64),
            "plant_index": plant.astype(np.int64),
        })
    return result


def _read_dataset(root: Path, manifest_sha: str, reader: Any, np: Any, rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    train = reader.load_cstar_split(root, DATASET_MANIFEST, "TRAIN", manifest_sha)
    val = reader.load_cstar_split(root, DATASET_MANIFEST, "VAL", manifest_sha)
    train = _validate_scenes(train, rows, "TRAIN", np)
    val = _validate_scenes(val, rows, "VAL", np)
    if (len(train) != 768 or len(val) != 48
            or set(s["scene_id"] for s in train).intersection(s["scene_id"] for s in val)):
        raise ValueError("reader did not preserve disjoint TRAIN768/VAL48 partitions")
    return train, val


def _load_a1r_normalizer(root: Path, np: Any) -> tuple[Any, Any, dict[str, Any]]:
    path = _repo_path(root, A1R_NORMALIZER)
    if _sha256(path).lower() != A1R_NORMALIZER_SHA256:
        raise ValueError("frozen A1R normalizer file SHA mismatch")
    record = _load_json(path)
    if (record.get("schema") != "CM18_A1R_NORMALIZER_V1" or record.get("fit_rows") != 307_200
            or record.get("train_scenes") != 768
            or record.get("sample_indices_per_scene_zero_based") != "0,5,...,1995 (400 rows)"
            or record.get("std_ddof") != 0):
        raise ValueError("frozen A1R normalizer metadata mismatch")
    mean = np.asarray(record.get("input_mean_float64"), dtype=np.float64)
    std = np.asarray(record.get("input_std_float64"), dtype=np.float64)
    old_rms = np.asarray(record.get("train_axis_rms_rad_s2_float64"), dtype=np.float64)
    if (mean.shape != (18,) or std.shape != (18,) or old_rms.shape != (3,)
            or not np.isfinite(mean).all() or not np.isfinite(std).all()
            or not np.isfinite(old_rms).all() or np.any(std < 1e-6) or np.any(old_rms <= 0)):
        raise ValueError("frozen A1R normalizer arrays are invalid")
    digest = hashlib.sha256(b"".join(
        np.ascontiguousarray(a, dtype=np.float64).tobytes() for a in (mean, std, old_rms)
    )).hexdigest()
    if (digest != "faf8748f640c944c745406247ab8486825966abd763088ad1f4e0cde626ad14c"
            or record.get("canonical_float64_sha256") != digest):
        raise ValueError("frozen A1R canonical normalizer identity mismatch")
    return mean, std, record


def _load_a1r_initial_parameters(root: Path, np: Any) -> dict[str, Any]:
    path = _repo_path(root, A1R_INITIAL_PARAMETERS)
    if _sha256(path).lower() != A1R_INITIAL_PARAMETERS_SHA256:
        raise ValueError("frozen A1R initial-parameter archive SHA mismatch")
    with np.load(path, allow_pickle=False) as archive:
        result = {key: np.asarray(archive[key], dtype=np.float64).copy()
                  for key in ("W1", "b1", "W2", "b2", "W3", "b3")}
    expected = {"W1": (32, 18), "b1": (32,), "W2": (32, 32),
                "b2": (32,), "W3": (24, 32), "b3": (24,)}
    if any(result[key].shape != shape or not np.isfinite(result[key]).all()
           for key, shape in expected.items()):
        raise ValueError("frozen A1R initial W/b arrays are invalid")
    return result


def _normalizer_audit(root: Path, path_value: str, sha_value: str, dataset_sha: str,
                      a1r_mean: Any, a1r_std: Any, np: Any) -> dict[str, Any]:
    if path_value != NORMALIZER_AUDIT or len(sha_value) != 64:
        raise ValueError("C* normalizer audit path/SHA pin is invalid")
    path = _repo_path(root, path_value)
    actual_sha = _sha256(path).lower()
    if actual_sha != sha_value.lower():
        raise ValueError("C* independent normalizer audit SHA mismatch")
    audit = _load_json(path)
    required = (audit.get("schema") == "CM18_CSTAR_ALL816_INDEPENDENT_AUDIT_V1"
                and audit.get("status") == "PASS" and audit.get("scene_count") == 816
                and audit.get("split_counts") == {"TRAIN": 768, "VAL": 48}
                and audit.get("train_fit_rows") == 307_200
                and audit.get("label_manifest_sha256", "").lower() == dataset_sha.lower()
                and audit.get("a1r_normalizer_canonical_sha256")
                == "faf8748f640c944c745406247ab8486825966abd763088ad1f4e0cde626ad14c")
    if not required:
        raise ValueError("C* independent normalizer audit metadata mismatch")
    mean = np.asarray(audit.get("input_mean_float64"), dtype=np.float64)
    std = np.asarray(audit.get("input_std_float64"), dtype=np.float64)
    axis_rms = np.asarray(audit.get("target_axis_rms_rad_s2_float64"), dtype=np.float64)
    if (mean.shape != (18,) or std.shape != (18,) or axis_rms.shape != (3,)
            or not np.isfinite(mean).all() or not np.isfinite(std).all()
            or not np.isfinite(axis_rms).all() or np.any(axis_rms <= 0)
            or not np.array_equal(mean, a1r_mean) or not np.array_equal(std, a1r_std)):
        raise ValueError("C* audit input normalizer or target RMS arrays are invalid")
    digest = hashlib.sha256(b"".join(
        np.ascontiguousarray(a, dtype=np.float64).tobytes() for a in (mean, std, axis_rms)
    )).hexdigest()
    if digest != audit.get("canonical_normalizer_sha256"):
        raise ValueError("C* canonical normalizer digest does not match audit arrays")
    return {"path": path_value, "sha256": actual_sha, "target_axis_rms_rad_s2": axis_rms,
            "canonical_normalizer_sha256": digest, "record": audit}


def _training_arrays(scenes: list[dict[str, Any]], np: Any, input_mean: Any,
                     input_std: Any, audit: dict[str, Any]) -> tuple[Any, Any, Any, Any, Any, Any]:
    sample_idx = np.arange(0, 1996, 5, dtype=np.int64)
    if sample_idx.shape != (400,) or sample_idx[-1] != 1995:
        raise AssertionError("frozen A1R sampling rule changed")
    x = np.concatenate([scene["X18"][sample_idx] for scene in scenes], axis=0)
    y = np.concatenate([scene["target_raw_output_rad_s2"][sample_idx] for scene in scenes], axis=0)
    mean_recomputed = x.mean(axis=0, dtype=np.float64)
    std_raw = x.std(axis=0, ddof=0, dtype=np.float64)
    std_recomputed = np.maximum(std_raw, 1e-6)
    mean = np.asarray(input_mean, dtype=np.float64).copy()
    std = np.asarray(input_std, dtype=np.float64).copy()
    axis_rms = np.sqrt(np.mean(np.square(y, dtype=np.float64), axis=0, dtype=np.float64))
    if (x.shape != (307_200, 18) or y.shape != (307_200, 3)
            or not np.isfinite(mean).all() or not np.isfinite(std).all()
            or not np.isfinite(axis_rms).all() or np.any(axis_rms <= 0)):
        raise ValueError("A1T TRAIN-only target normalizer or fit rows are invalid")
    if not np.array_equal(mean_recomputed, mean) or not np.array_equal(std_recomputed, std):
        raise ValueError("A1T X18 does not exactly reproduce frozen A1R input mean/std")
    if not np.array_equal(axis_rms, audit["target_axis_rms_rad_s2"]):
        raise ValueError("TRAIN-only C* axis RMS differs from independent all-816 audit")
    digest = hashlib.sha256(b"".join(
        np.ascontiguousarray(a, dtype=np.float64).tobytes() for a in (mean, std, axis_rms)
    )).hexdigest()
    if digest != audit["canonical_normalizer_sha256"]:
        raise ValueError("canonical A1T normalizer differs from independent audit digest")
    return x, y, mean, std, axis_rms, std_raw


def _state_sha256(model: Any) -> str:
    digest = hashlib.sha256()
    for name, tensor in sorted(model.state_dict().items()):
        array = tensor.detach().cpu().contiguous().numpy()
        digest.update(name.encode("utf-8") + b"\0")
        digest.update(array.dtype.str.encode("ascii") + b"\0")
        digest.update(json.dumps(list(array.shape), separators=(",", ":")).encode("ascii") + b"\0")
        digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def _save_checkpoint(torch: Any, model: Any, path: Path, step: int, kind: str, score: float | None = None) -> str:
    state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
    torch.save({
        "schema": "CM18_A1T_CHECKPOINT_V1", "kind": kind, "optimizer_step": step,
        "selection_score": score, "state_dict": state,
    }, path)
    return _sha256(path)


def _metrics(actual: Any, target: Any, np: Any) -> dict[str, Any]:
    error = np.asarray(actual, dtype=np.float64) - np.asarray(target, dtype=np.float64)
    return {
        "events": int(error.shape[0]),
        "axis": {
            name: {"mae_rad_s2": float(np.mean(np.abs(error[:, i]))),
                   "rmse_rad_s2": float(np.sqrt(np.mean(np.square(error[:, i]))))}
            for i, name in enumerate(("x", "y", "z"))
        },
    }


def _scene_eval(model: Any, scene: dict[str, Any], axis_rms: Any, device: Any, torch: Any, np: Any) -> dict[str, Any]:
    model.eval()
    chunks = []
    with torch.no_grad():
        for start in range(0, 1999, 4096):
            batch = torch.as_tensor(scene["X18"][start:start + 4096], dtype=torch.float32, device=device)
            chunks.append(model(batch)["physical_output_rad_s2"].detach().cpu().numpy().astype(np.float64))
    pred = np.concatenate(chunks, axis=0)
    target = scene["target_raw_output_rad_s2"]
    score = float(np.sqrt(np.mean(np.sum(np.square((pred - target) / axis_rms), axis=1))))
    phases = {}
    for code in range(6):
        mask = scene["phase_code"] == code
        phases[str(code)] = (
            {"events": int(mask.sum()), "physical_error": _metrics(pred[mask], target[mask], np)}
            if np.any(mask) else {"events": 0, "physical_error": None}
        )
    return {
        "scene_id": scene["scene_id"], "normalized_scene_score": score,
        "physical_error": _metrics(pred, target, np), "phase": phases,
    }


def _evaluate(model: Any, scenes: list[dict[str, Any]], axis_rms: Any, device: Any, torch: Any, np: Any) -> tuple[float, list[dict[str, Any]]]:
    rows = [_scene_eval(model, scene, axis_rms, device, torch, np) for scene in scenes]
    return float(np.mean([row["normalized_scene_score"] for row in rows])), rows


def _runtime_preflight(output_parent: Path) -> dict[str, Any]:
    free = shutil.disk_usage(output_parent).free
    if free < MIN_FREE_BYTES:
        raise RuntimeError(f"less than 30 GB free: {free} bytes")
    nvidia = shutil.which("nvidia-smi")
    if nvidia is None:
        raise RuntimeError("nvidia-smi is required for CUDA preflight")
    proc = subprocess.run([nvidia, "--query-compute-apps=pid,process_name", "--format=csv,noheader,nounits"],
                          capture_output=True, text=True, timeout=20, check=False)
    if proc.returncode:
        raise RuntimeError(f"nvidia-smi process query failed: {proc.stderr.strip()}")
    process_rows = [s.strip() for s in proc.stdout.splitlines() if s.strip() and "No running processes found" not in s]
    util_run = subprocess.run([nvidia, "--query-gpu=index,utilization.gpu", "--format=csv,noheader,nounits"],
                              capture_output=True, text=True, timeout=20, check=False)
    if util_run.returncode:
        raise RuntimeError(f"nvidia-smi GPU query failed: {util_run.stderr.strip()}")
    util_rows = [s.strip() for s in util_run.stdout.splitlines() if s.strip()]
    try:
        util = [float(row.rsplit(",", 1)[1].strip().removesuffix("%")) for row in util_rows]
    except (IndexError, ValueError) as exc:
        raise RuntimeError(f"cannot parse GPU utilization rows: {util_rows}") from exc
    if not util or any(not math.isfinite(value) or value < 0.0 or value > 100.0 for value in util):
        raise RuntimeError(f"invalid GPU utilization values: {util_rows}")
    return {
        "free_disk_bytes_at_start": free,
        "compute_process_rows_recorded_for_root_review": process_rows,
        "gpu_utilization_rows": util_rows,
        "gpu_utilization_percent": util,
    }


def _check_budget(run_dir: Path) -> None:
    size = sum(p.stat().st_size for p in run_dir.rglob("*") if p.is_file())
    if size > MAX_OUTPUT_BYTES:
        raise RuntimeError(f"A1T output exceeds 1 GiB: {size}")


def _record_failure(run_dir: Path, receipt: dict[str, Any], exc: BaseException, step: int | None) -> None:
    _write_json(run_dir / "failure.json", {
        "schema": "CM18_A1T_TRAINING_FAILURE_V1", "recorded_at_utc": _now(),
        "stage": receipt.get("active_stage"), "optimizer_step_attempted": step,
        "optimizer_steps_completed": receipt.get("optimizer_steps_completed", 0),
        "exception_type": type(exc).__name__, "message": str(exc),
        "traceback": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
    })
    receipt.update({
        "status": "FAILED", "ended_at_utc": _now(),
        "failure_reason": f"{type(exc).__name__}: {exc}", "failure_step": step,
    })
    _write_json(run_dir / "run_receipt.json", receipt)

def _assert_a1r_weights(parameters: dict[str, Any], a1r_parameters: dict[str, Any], np: Any) -> None:
    for name in ("W1", "b1", "W2", "b2", "W3", "b3"):
        if not np.array_equal(parameters[name], a1r_parameters[name]):
            raise AssertionError(f"A1T seed initialization differs from frozen A1R {name}")


def _self_check(root: Path, manifest_sha: str, audit_path: str, audit_sha: str) -> dict[str, Any]:
    import numpy as np
    import torch

    if _sha256(_repo_path(root, DATASET_MANIFEST)).lower() != manifest_sha.lower():
        raise ValueError("zero-step C* dataset manifest SHA mismatch")
    _check_document_pin(root, {"taskbook": {"path": TASKBOOK, "sha256": TASKBOOK_SHA256},
                              "source_manifest": {"path": SOURCE_MANIFEST, "sha256": SOURCE_MANIFEST_SHA256}},
                        "taskbook", TASKBOOK, TASKBOOK_SHA256)
    _check_document_pin(root, {"taskbook": {"path": TASKBOOK, "sha256": TASKBOOK_SHA256},
                              "source_manifest": {"path": SOURCE_MANIFEST, "sha256": SOURCE_MANIFEST_SHA256}},
                        "source_manifest", SOURCE_MANIFEST, SOURCE_MANIFEST_SHA256)
    manifest = _load_json(_repo_path(root, DATASET_MANIFEST))
    rows = _validate_dataset_manifest(root, manifest)
    input_mean, input_std, a1r_normalizer = _load_a1r_normalizer(root, np)
    audit = _normalizer_audit(root, audit_path, audit_sha, manifest_sha, input_mean, input_std, np)
    a1r_parameters = _load_a1r_initial_parameters(root, np)
    for relative, expected in SOURCE_HASHES.items():
        if _sha256(_repo_path(root, relative)).lower() != expected:
            raise ValueError(f"zero-step frozen source identity mismatch: {relative}")
    reader, numpy_model, torch_model = _source_modules(root)
    train = _validate_scenes(reader.load_cstar_split(root, DATASET_MANIFEST, "TRAIN", manifest_sha), rows, "TRAIN", np)
    val = _validate_scenes(reader.load_cstar_split(root, DATASET_MANIFEST, "VAL", manifest_sha), rows, "VAL", np)
    if len(train) != 768 or len(val) != 48:
        raise AssertionError("zero-step reader coverage must be 768 TRAIN plus 48 VAL")
    x, y, mean, std, axis_rms, std_raw = _training_arrays(train, np, input_mean, input_std, audit)
    if x.shape != (307_200, 18) or y.shape != (307_200, 3) or sum(len(s["X18"]) for s in val) != 95_952:
        raise AssertionError("zero-step sampling/validation event totals differ from taskbook")
    random.seed(SEED)
    torch.manual_seed(SEED)
    torch.use_deterministic_algorithms(True)
    parameters = numpy_model.initialize_random_parameters(SEED, mean, std, axis_rms)
    _assert_a1r_weights(parameters, a1r_parameters, np)
    model = torch_model.TorchCM18A1(mean, std, axis_rms)
    model.load_numpy_parameters(parameters)
    if any(not np.array_equal(model.numpy_parameters()[k], parameters[k]) for k in parameters):
        raise AssertionError("initialized double parameters differ from frozen A1 NumPy rule")
    model.float()
    actual_f32 = model.numpy_parameters()
    if any(not np.array_equal(actual_f32[k], parameters[k].astype(np.float32)) for k in parameters):
        raise AssertionError("float32 initialization differs from exact cast of A1 parameters")
    active = np.flatnonzero(np.any(x[:, 7:15] != 0.0, axis=1))[:64]
    if len(active) != 64:
        raise AssertionError("zero-step forward/backward requires 64 nonzero-basis TRAIN rows")
    features = torch.as_tensor(x[active].astype(np.float32), dtype=torch.float32)
    targets = torch.as_tensor((y[active] / axis_rms).astype(np.float32), dtype=torch.float32)
    prediction = model(features)["physical_output_rad_s2"] / model.train_axis_rms_rad_s2
    loss = torch.nn.functional.smooth_l1_loss(prediction, targets, beta=1.0, reduction="mean")
    loss.backward()
    zero_features = features.clone()
    zero_features[:, 7:15] = 0.0
    with torch.no_grad():
        zero_output = model(zero_features)["physical_output_rad_s2"]
    if not torch.equal(zero_output, torch.zeros_like(zero_output)):
        raise AssertionError("A1T zero morphology basis must produce exactly zero output")
    if (not torch.isfinite(loss).item()
            or any(p.grad is None or not torch.isfinite(p.grad).all().item() for p in model.parameters())):
        raise FloatingPointError("zero-step forward/backward produced non-finite loss or gradients")
    return {
        "schema": "CM18_A1T_ZERO_STEP_SELF_CHECK_V1",
        "status": "PASS",
        "source_sha256": _sha256(_repo_path(root, TRAINER)),
        "reader_sha256": _sha256(_repo_path(root, READER)),
        "numpy_model_sha256": _sha256(_repo_path(root, NUMPY_MODEL)),
        "torch_model_sha256": _sha256(_repo_path(root, TORCH_MODEL)),
        "taskbook_sha256": TASKBOOK_SHA256,
        "source_manifest_sha256": SOURCE_MANIFEST_SHA256,
        "dataset_manifest_path": DATASET_MANIFEST,
        "dataset_manifest_sha256": manifest_sha.lower(),
        "normalizer_audit_path": audit_path,
        "normalizer_audit_sha256": audit_sha.lower(),
        "a1r_normalizer_file_sha256": A1R_NORMALIZER_SHA256,
        "a1r_initial_parameters_sha256": A1R_INITIAL_PARAMETERS_SHA256,
        "train_scenes": len(train),
        "val_scenes": len(val),
        "train_fit_rows": int(x.shape[0]),
        "val_events": int(sum(len(s["X18"]) for s in val)),
        "train_sample_indices_zero_based": "0,5,...,1995",
        "input_mean_float64": mean.tolist(),
        "input_std_float64": std.tolist(),
        "input_std_raw_float64": std_raw.tolist(),
        "input_std_floor_indices": np.flatnonzero(std_raw < 1e-6).tolist(),
        "train_axis_rms_rad_s2_float64": axis_rms.tolist(),
        "canonical_normalizer_sha256": hashlib.sha256(b"".join(
            np.ascontiguousarray(a, dtype=np.float64).tobytes() for a in (mean, std, axis_rms)
        )).hexdigest(),
        "input_normalizer_exactly_reused_from_a1r": True,
        "target_rms_matches_independent_audit": True,
        "initial_float32_state_sha256": _state_sha256(model),
        "initial_weights_and_biases_match_a1r": True,
        "zero_basis_exact_output": True,
        "forward_backward_loss": float(loss.detach().item()),
        "nonzero_basis_rows_checked": int(len(active)),
        "optimizer_steps": 0,
        "optimizer_step_calls": 0,
        "training_started": False,
        "C5_VAL48_fit_or_selection_rows": 0,
        "TEST_accessed": False,
        "environment": {key: os.environ.get(key) for key in
                        ("MKL_THREADING_LAYER", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
                         "OPENBLAS_NUM_THREADS", "CUBLAS_WORKSPACE_CONFIG")},
    }


def _formal_train(root: Path, release_path: Path, release_sha: str) -> Path:
    root = root.resolve(strict=True)
    pinned, manifest, rows = _check_release(root, release_path, release_sha)
    output = _repo_path(root, FORMAL_OUTPUT, must_exist=False)
    if output.exists():
        raise FileExistsError(f"refusing to reuse A1T output: {output}")
    if not output.parent.is_dir():
        raise FileNotFoundError(f"formal output parent missing: {output.parent}")
    preflight = _runtime_preflight(output.parent)
    output.mkdir(exist_ok=False)
    receipt: dict[str, Any] = {
        "schema": "CM18_A1T_TRAINING_RECEIPT_V1",
        "status": "INITIALIZING",
        "started_at_utc": _now(),
        "ended_at_utc": None,
        "command": sys.argv,
        "cwd": str(Path.cwd()),
        "run_directory": FORMAL_OUTPUT,
        "release": pinned,
        "runtime_preflight": preflight,
        "environment": {key: os.environ.get(key) for key in
                        ("MKL_THREADING_LAYER", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
                         "OPENBLAS_NUM_THREADS", "CUBLAS_WORKSPACE_CONFIG")},
        "optimizer_steps_completed": 0,
        "optimizer_step_calls_attempted": 0,
        "active_stage": "import_runtime",
        "failure_reason": None,
        "label_semantics": "direct compensation C*: raw network target is C*/beta; unchanged runtime clip then beta",
        "B_VAL48_selects_checkpoint": True,
        "C5_VAL48_used_for_training_or_selection": False,
        "TEST_accessed": False,
    }
    _write_json(output / "run_receipt.json", receipt)
    failure_step: int | None = None
    model = None
    torch = None
    try:
        import numpy as np
        import torch as torch_module
        torch = torch_module
        receipt["runtime"] = {
            "python": sys.version, "numpy": np.__version__, "torch": torch.__version__,
            "cuda_runtime": torch.version.cuda, "gpu_name": None, "device": "cuda:0",
            "dtype": "float32", "amp": False, "tf32": False, "deterministic_algorithms": True,
        }
        if not torch.cuda.is_available() or torch.cuda.device_count() < 1:
            raise RuntimeError("A1T formal training requires CUDA device cuda:0")
        torch.cuda.set_device(0)
        receipt["runtime"]["gpu_name"] = torch.cuda.get_device_name(0)
        torch.use_deterministic_algorithms(True)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        if hasattr(torch, "set_float32_matmul_precision"):
            torch.set_float32_matmul_precision("highest")
        random.seed(SEED)
        torch.manual_seed(SEED)
        torch.cuda.manual_seed_all(SEED)

        reader, numpy_model, torch_model = _source_modules(root)
        receipt["active_stage"] = "load_cstar_train_and_val"
        _write_json(output / "run_receipt.json", receipt)
        input_mean, input_std, a1r_normalizer = _load_a1r_normalizer(root, np)
        audit = _normalizer_audit(root, pinned["normalizer_audit_path"],
                                  pinned["normalizer_audit_sha256"],
                                  pinned["dataset_manifest_sha256"], input_mean, input_std, np)
        a1r_parameters = _load_a1r_initial_parameters(root, np)
        train, val = _read_dataset(root, pinned["dataset_manifest_sha256"], reader, np, rows)
        x64, y64, mean, std, axis_rms, std_raw = _training_arrays(
            train, np, input_mean, input_std, audit
        )
        val_events = sum(len(s["X18"]) for s in val)
        if x64.shape != (307_200, 18) or y64.shape != (307_200, 3) or val_events != 48 * 1999:
            raise ValueError("A1T fit/validation totals differ from the frozen taskbook")

        params = numpy_model.initialize_random_parameters(SEED, mean, std, axis_rms)
        _assert_a1r_weights(params, a1r_parameters, np)
        model = torch_model.TorchCM18A1(mean, std, axis_rms)
        model.load_numpy_parameters(params)
        if any(not np.array_equal(model.numpy_parameters()[k], params[k]) for k in params):
            raise AssertionError("double initialization differs from A1 NumPy rule")
        model = model.float().to(torch.device("cuda:0"))
        initial_f32 = model.numpy_parameters()
        if any(not np.array_equal(initial_f32[k], params[k].astype(np.float32)) for k in params):
            raise AssertionError("float32 initialization differs from A1 cast")
        initial_state_sha = _state_sha256(model)
        normalizer = {
            "schema": "CM18_A1T_NORMALIZER_V1", "fit_rows": 307_200, "train_scenes": 768,
            "sample_indices_per_scene_zero_based": "0,5,...,1995 (400 rows)",
            "calculation_dtype": "float64", "std_ddof": 0,
            "input_mean_float64": mean.tolist(), "input_std_raw_float64": std_raw.tolist(),
            "input_std_float64": std.tolist(), "train_axis_rms_rad_s2_float64": axis_rms.tolist(),
            "a1r_normalizer_file_sha256": A1R_NORMALIZER_SHA256,
            "a1r_normalizer_canonical_sha256": a1r_normalizer["canonical_float64_sha256"],
            "normalizer_audit_path": audit["path"],
            "normalizer_audit_sha256": audit["sha256"],
            "normalizer_audit_canonical_sha256": audit["canonical_normalizer_sha256"],
            "a1r_initial_parameters_sha256": A1R_INITIAL_PARAMETERS_SHA256,
            "input_mean_float32_buffer": initial_f32["input_mean"].tolist(),
            "input_std_float32_buffer": initial_f32["input_std"].tolist(),
            "train_axis_rms_float32_buffer": initial_f32["train_axis_rms_rad_s2"].tolist(),
            "std_floor_indices": np.flatnonzero(std_raw < 1e-6).tolist(),
            "float32_std_promoted_below_floor_indices": np.flatnonzero(initial_f32["input_std"].astype(np.float64) < 1e-6).tolist(),
            "float32_buffer_sha256": hashlib.sha256(b"".join(
                initial_f32[k].tobytes(order="C") for k in ("input_mean", "input_std", "train_axis_rms_rad_s2")
            )).hexdigest(),
            "canonical_float64_sha256": hashlib.sha256(b"".join(
                np.ascontiguousarray(a, dtype=np.float64).tobytes() for a in (mean, std, axis_rms)
            )).hexdigest(),
            "initial_float32_state_sha256": initial_state_sha,
            "deployment_export_rule": "retain canonical float64 normalizers; promote trained float32 W/b; never infer canonical values from float32 buffers",
        }
        _write_json(output / "normalizer.json", normalizer)
        np.savez_compressed(output / "initial_parameters.npz", **params,
                            **{f"actual_float32_{k}": v for k, v in initial_f32.items()})
        initial_npz_sha = _sha256(output / "initial_parameters.npz")
        initial_ckpt_sha = _save_checkpoint(torch, model, output / "initial.pt", 0, "initial")
        config = {
            "schema": "CM18_A1T_TRAINING_CONFIG_V1", "release": pinned,
            "seed": SEED, "optimizer_steps": STEPS, "batch_size": BATCH_SIZE,
            "optimizer": {"name": "Adam", "lr": 0.001, "betas": [0.9, 0.999], "eps": 1e-8, "weight_decay": 1e-5},
            "loss": "SmoothL1(beta=1.0), mean over batch and 3 axes; output/target normalized by TRAIN axis RMS",
            "sampling": "NumPy default_rng(seed), uniform with replacement over ordered 307200 TRAIN rows",
            "selection": "B direct-target VAL48 equal-scene mean of normalized scene scores; strict improvement; earliest tie",
            "train_scene_count": len(train), "train_fit_rows": int(len(x64)),
            "b_val_scene_count": len(val), "b_val_events": val_events,
            "c5_val48_training_eligible": False, "c5_val48_used_for_selection": False,
            "initial_parameters_npz_sha256": initial_npz_sha,
            "initial_float32_state_sha256": initial_state_sha,
            "initial_checkpoint_sha256": initial_ckpt_sha,
            "normalizer_sha256": _sha256(output / "normalizer.json"),
            "runtime": receipt["runtime"],
        }
        _write_json(output / "training_config.json", config)
        _check_budget(output)
        device = torch.device("cuda:0")
        train_x = torch.as_tensor(x64.astype(np.float32), dtype=torch.float32, device=device)
        train_y_norm = torch.as_tensor((y64 / axis_rms).astype(np.float32), dtype=torch.float32, device=device)
        axis_rms_t = torch.as_tensor(axis_rms.astype(np.float32), dtype=torch.float32, device=device)
        optimizer = torch.optim.Adam(
            model.parameters(), lr=0.001, betas=(0.9, 0.999), eps=1e-8, weight_decay=1e-5
        )
        rng = np.random.default_rng(SEED)
        best_score = math.inf
        best_step = -1
        failure_step = 0

        def validate_at(step: int) -> None:
            nonlocal best_score, best_step
            score, scene_rows = _evaluate(model, val, axis_rms, device, torch, np)
            improved = score < best_score
            if improved:
                best_score, best_step = score, step
                best_sha = _save_checkpoint(torch, model, output / "best.pt", step, "best", score)
            else:
                best_sha = _sha256(output / "best.pt")
            _append_jsonl(output / "val_metrics.jsonl", {
                "optimizer_step": step,
                "b_val_scene_weighted_normalized_score": score,
                "best_updated": improved,
                "best_step": best_step,
                "best_score": best_score,
                "best_checkpoint_sha256": best_sha,
            })
            for row in scene_rows:
                _append_jsonl(output / "val_per_scene.jsonl", {"optimizer_step": step, **row})
            _check_budget(output)

        receipt.update({"status": "RUNNING", "active_stage": "evaluate_step0"})
        _write_json(output / "run_receipt.json", receipt)
        validate_at(0)
        receipt.update({"best_step": best_step, "best_score": best_score, "active_stage": "train"})
        _write_json(output / "run_receipt.json", receipt)
        model.train()
        for step in range(1, STEPS + 1):
            failure_step = step
            sample = rng.integers(0, len(train_x), size=BATCH_SIZE, dtype=np.int64)
            indices = torch.as_tensor(sample, dtype=torch.long, device=device)
            optimizer.zero_grad(set_to_none=True)
            prediction = model(train_x[indices])["physical_output_rad_s2"] / axis_rms_t
            loss = torch.nn.functional.smooth_l1_loss(
                prediction, train_y_norm[indices], beta=1.0, reduction="mean"
            )
            loss_value = float(loss.detach().item())
            if not math.isfinite(loss_value):
                raise FloatingPointError(f"non-finite loss at step {step}")
            loss.backward()
            for name, parameter in model.named_parameters():
                if parameter.grad is None or not torch.isfinite(parameter.grad).all().item():
                    raise FloatingPointError(f"missing/non-finite gradient: {name} at step {step}")
                if not torch.isfinite(parameter).all().item():
                    raise FloatingPointError(f"non-finite parameter before step {step}: {name}")
            receipt["optimizer_step_calls_attempted"] = step
            optimizer.step()
            receipt["optimizer_steps_completed"] = step
            if any(not torch.isfinite(parameter).all().item() for parameter in model.parameters()):
                raise FloatingPointError(f"non-finite parameter after step {step}")
            if step % PROGRESS_EVERY == 0:
                _write_json(output / "progress.json", {
                    "optimizer_steps_completed": step, "optimizer_step_calls_attempted": step,
                    "optimizer_steps_target": STEPS, "latest_loss": loss_value, "updated_at_utc": _now(),
                })
                _check_budget(output)
            if step % EVAL_EVERY == 0:
                receipt.update({"active_stage": f"validation_step_{step}", "best_step": best_step, "best_score": best_score})
                _write_json(output / "run_receipt.json", receipt)
                validate_at(step)
                receipt.update({"active_stage": "train", "best_step": best_step, "best_score": best_score})
                _write_json(output / "run_receipt.json", receipt)
                model.train()

        failure_step = None
        final_sha = _save_checkpoint(torch, model, output / "final.pt", STEPS, "final")
        best_sha = _sha256(output / "best.pt")
        receipt.update({
            "status": "COMPLETED", "ended_at_utc": _now(),
            "optimizer_steps_completed": STEPS, "best_step": best_step,
            "best_score": best_score, "best_checkpoint_sha256": best_sha,
            "final_checkpoint_sha256": final_sha, "active_stage": None,
            "candidate_frozen": True, "C5_VAL48_post_selection_diagnostic_pending": True,
        })
        _write_json(output / "run_receipt.json", receipt)
        _check_budget(output)
        return output
    except BaseException as exc:
        if model is not None and torch is not None:
            try:
                _save_checkpoint(torch, model, output / "final.pt",
                                 int(receipt.get("optimizer_steps_completed", 0)), "final_on_failure")
            except BaseException:
                pass
        try:
            _record_failure(output, receipt, exc, failure_step)
        except BaseException:
            pass
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--manifest-sha256")
    parser.add_argument("--normalizer-audit", type=Path)
    parser.add_argument("--normalizer-audit-sha256")
    parser.add_argument("--release", type=Path)
    parser.add_argument("--release-sha256")
    args = parser.parse_args()
    root = args.repo_root.resolve(strict=True)
    if args.self_check:
        if args.release is not None or args.release_sha256 is not None:
            parser.error("--self-check cannot be combined with a formal release")
        if (not args.manifest_sha256 or args.normalizer_audit is None
                or not args.normalizer_audit_sha256):
            parser.error("--self-check requires manifest SHA and independent normalizer audit path/SHA")
        try:
            audit_path = args.normalizer_audit.resolve(strict=True).relative_to(root).as_posix()
        except ValueError as exc:
            parser.error(f"--normalizer-audit must be inside --repo-root: {exc}")
        result = _self_check(root, args.manifest_sha256, audit_path, args.normalizer_audit_sha256)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return
    if (args.manifest_sha256 is not None or args.normalizer_audit is not None
            or args.normalizer_audit_sha256 is not None):
        parser.error("manifest/audit pins are only valid for the zero-step self-check")
    if args.release is None or args.release_sha256 is None:
        parser.error("formal training requires ROOT --release and --release-sha256 pins")
    if len(args.release_sha256) != 64:
        parser.error("--release-sha256 must be a 64-character SHA256")
    output = _formal_train(root, args.release, args.release_sha256)
    print(json.dumps({"status": "COMPLETED", "run_directory": str(output), "optimizer_steps": STEPS}, indent=2))


if __name__ == "__main__":
    main()
