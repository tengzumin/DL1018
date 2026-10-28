"""Load one pinned TRAIN/VAL split from the offline C* relabel export."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat


SOURCE_MANIFEST = "reports/attitude_cm18_datarepair_20261024/B_REF_REPAIRED_SOURCE_MANIFEST_v1.json"
SOURCE_SHA256 = "0f86b47d01940e7b556b78a9664470531572809aa6857a59fc77d88a33681ec5"
DATASET_MANIFEST = "reports/attitude_cm18_datarepair_20261024/repaired_all816_v1/DATASET_MANIFEST_v1.json"
DATASET_SHA256 = "3f51a1cd0e2e8c3eae79a16df363f2f8d47b0d5dbd876ecd95f1571d9e70a5e0"
SCHEMA = "CM18_A1T_CSTAR_RELABEL_ALL816_V1"
N_EVENTS = 1999


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _repo_file(root: Path, relative: str) -> Path:
    base = root.resolve(strict=True)
    path = (base / relative).resolve(strict=True)
    try:
        path.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"path escapes repository: {relative}") from exc
    return path


def _text(value: Any) -> str:
    array = np.asarray(value)
    if array.dtype.kind in "US":
        return "".join(str(part) for part in array.reshape(-1)).strip()
    if array.dtype.kind in "ui":
        return "".join(chr(int(part)) for part in array.reshape(-1) if int(part)).strip()
    raise ValueError(f"expected MATLAB text, got {array.dtype}")


def _array(mat: dict[str, Any], name: str, shape: tuple[int, ...], dtype: Any = None) -> np.ndarray:
    if name not in mat:
        raise ValueError(f"MAT cache lacks {name}")
    value = np.asarray(mat[name])
    if value.shape != shape or (dtype is not None and value.dtype != dtype):
        raise ValueError(f"{name} has shape/dtype {value.shape}/{value.dtype}, expected {shape}/{dtype}")
    if np.issubdtype(value.dtype, np.number) and not np.isfinite(value).all():
        raise ValueError(f"{name} contains non-finite values")
    return value


def _manifest(root: Path, relative: str, expected_sha: str) -> dict[str, Any]:
    path = _repo_file(root, relative)
    if _sha256(path) != expected_sha.lower():
        raise ValueError(f"manifest SHA256 mismatch: {relative}")
    return json.loads(path.read_text(encoding="utf-8"))


def _verify_input_manifests(root: Path, manifest: dict[str, Any]) -> tuple[list[dict], list[dict]]:
    if manifest.get("source_manifest_path") != SOURCE_MANIFEST or manifest.get("source_manifest_sha256", "").lower() != SOURCE_SHA256:
        raise ValueError("C* manifest is not bound to the repaired-source manifest")
    if manifest.get("dataset_manifest_path") != DATASET_MANIFEST or manifest.get("dataset_manifest_sha256", "").lower() != DATASET_SHA256:
        raise ValueError("C* manifest is not bound to the repaired ALL816 dataset")

    source = _manifest(root, SOURCE_MANIFEST, SOURCE_SHA256)
    base = _manifest(root, DATASET_MANIFEST, DATASET_SHA256)
    if source.get("schema") != "CM18_REFERENCE_REPAIRED_SOURCE_MANIFEST_V1" or source.get("status") != "PREPARED_METADATA_ONLY_RAW_AND_CACHE_EXPORT_PENDING":
        raise ValueError("unexpected repaired-source manifest metadata status")
    if base.get("schema") != "CM18_B_REF_REPAIRED_ALL816_DATASET_MANIFEST_V1" or base.get("status") != "PASS":
        raise ValueError("unexpected base dataset manifest")
    if base.get("source_manifest_sha256", "").lower() != SOURCE_SHA256:
        raise ValueError("base dataset does not bind the expected source manifest")
    source_rows, base_rows = source.get("scenes"), base.get("rows")
    if not isinstance(source_rows, list) or not isinstance(base_rows, list) or len(source_rows) != 816 or len(base_rows) != 816:
        raise ValueError("input manifests must each contain 816 ordered rows")
    return source_rows, base_rows


def _read_scene(root: Path, row: dict[str, Any], source_row: dict[str, Any], base_row: dict[str, Any], dmax: np.ndarray, beta_rise_s: float) -> dict[str, Any]:
    scene_id, split = row.get("scene_id"), row.get("split")
    ordinal = int(row.get("ordinal", -1))
    if not isinstance(scene_id, str) or split not in ("TRAIN", "VAL") or row.get("status") != "PASS" or row.get("qualified") is not True:
        raise ValueError(f"unqualified C* row at ordinal {ordinal}")
    if source_row.get("scene_id") != scene_id or base_row.get("scene_id") != scene_id:
        raise ValueError(f"input scene order/identity mismatch at {ordinal}")
    if source_row.get("split") != split or base_row.get("split") != split or source_row.get("ordinal") != ordinal or base_row.get("ordinal") != ordinal:
        raise ValueError(f"input split/ordinal mismatch: {scene_id}")
    if source_row.get("source_action") != row.get("source_action") or base_row.get("qualified") is not True:
        raise ValueError(f"source action or base qualification mismatch: {scene_id}")
    if row.get("cache_schema") != "CM18_CSTAR_LABEL_CACHE_V1":
        raise ValueError(f"unexpected C* cache schema: {scene_id}")

    input_path = str(base_row["cache_path"])
    if row.get("input_cache_path") != input_path or row.get("input_cache_sha256", "").lower() != str(base_row["cache_sha256"]).lower() or int(row.get("input_cache_bytes", -1)) != int(base_row["cache_bytes"]):
        raise ValueError(f"original X18 cache binding mismatch: {scene_id}")
    cache_path = _repo_file(root, str(row["cache_path"]))
    if cache_path.stat().st_size != int(row["cache_bytes"]) or _sha256(cache_path) != str(row["cache_sha256"]).lower():
        raise ValueError(f"C* cache size/SHA mismatch: {scene_id}")

    if row.get("source_action") == "REUSE_A1_CERTIFIED_CACHE":
        source_ref = source_row["original_a1_source"]
        raw_ref, start_ref = source_ref["raw_run"], source_ref["run_start"]
    elif row.get("source_action") == "REBUILD_FROM_CORRECTED_T2_B_RAW":
        source_ref = source_row["corrected_source"]
        raw_ref, start_ref = source_ref["raw"], source_ref["run_start"]
    else:
        raise ValueError(f"unknown source action: {scene_id}")
    if row.get("raw_path") != raw_ref["path"] or row.get("raw_sha256", "").lower() != raw_ref["sha256"].lower():
        raise ValueError(f"raw source identity mismatch: {scene_id}")
    if row.get("run_start_path") != start_ref["path"] or row.get("run_start_sha256", "").lower() != start_ref["sha256"].lower():
        raise ValueError(f"run_start identity mismatch: {scene_id}")

    new_vars = (
        "scene_id", "split", "source_manifest_sha256", "dataset_manifest_sha256",
        "raw_path", "raw_sha256", "run_start_path", "run_start_sha256",
        "old_cache_path", "old_cache_sha256", "old_cache_schema", "event_index",
        "plant_index", "event_time_s", "phase_code", "target_applied_acceleration_rad_s2",
        "target_raw_output_rad_s2", "target_raw_output_reachable",
        "target_after_clip_beta_rad_s2", "beta", "output_clip_mask", "beta_zero_unreachable_mask",
    )
    new = loadmat(cache_path, squeeze_me=False, struct_as_record=False, variable_names=new_vars)
    if _text(new["scene_id"]) != scene_id or _text(new["split"]) != split:
        raise ValueError(f"embedded C* scene identity mismatch: {scene_id}")
    if _text(new["source_manifest_sha256"]).lower() != SOURCE_SHA256 or _text(new["dataset_manifest_sha256"]).lower() != DATASET_SHA256:
        raise ValueError(f"embedded C* source pin mismatch: {scene_id}")
    if _text(new["old_cache_path"]) != input_path or _text(new["old_cache_sha256"]).lower() != str(base_row["cache_sha256"]).lower():
        raise ValueError(f"embedded original-cache identity mismatch: {scene_id}")
    if _text(new["old_cache_schema"]) != base_row["cache_schema"]:
        raise ValueError(f"embedded original-cache schema mismatch: {scene_id}")
    if _text(new["raw_path"]) != row["raw_path"] or _text(new["raw_sha256"]).lower() != row["raw_sha256"].lower():
        raise ValueError(f"embedded raw source identity mismatch: {scene_id}")
    if _text(new["run_start_path"]) != row["run_start_path"] or _text(new["run_start_sha256"]).lower() != row["run_start_sha256"].lower():
        raise ValueError(f"embedded run_start identity mismatch: {scene_id}")

    event_index = _array(new, "event_index", (N_EVENTS, 1))
    plant_index = _array(new, "plant_index", (N_EVENTS, 1))
    event_time = _array(new, "event_time_s", (N_EVENTS, 1), np.float64)
    phase = _array(new, "phase_code", (N_EVENTS, 1), np.uint8)
    applied = _array(new, "target_applied_acceleration_rad_s2", (N_EVENTS, 3), np.float64)
    target = _array(new, "target_raw_output_rad_s2", (N_EVENTS, 3), np.float64)
    reachable = np.asarray(new["target_raw_output_reachable"], dtype=bool)
    after_clip = _array(new, "target_after_clip_beta_rad_s2", (N_EVENTS, 3), np.float64)
    beta = _array(new, "beta", (N_EVENTS, 1), np.float64).reshape(-1)
    output_clip = np.asarray(new["output_clip_mask"], dtype=bool)
    beta_unreachable = np.asarray(new["beta_zero_unreachable_mask"], dtype=bool)
    if reachable.shape != (N_EVENTS, 3) or output_clip.shape != (N_EVENTS, 3) or beta_unreachable.shape != (N_EVENTS, 3):
        raise ValueError(f"C* target masks have wrong shape: {scene_id}")
    if not reachable.all() or beta_unreachable.any() or not np.isfinite(target).all():
        raise ValueError(f"C* raw target is unreachable or non-finite: {scene_id}")
    if not np.array_equal(event_index.reshape(-1), np.arange(1, N_EVENTS + 1)) or not np.array_equal(plant_index.reshape(-1), np.arange(11, 20000, 10)):
        raise ValueError(f"C* event/index sequence mismatch: {scene_id}")
    expected_time = (plant_index.reshape(-1) - 1) * 0.001
    if np.max(np.abs(event_time.reshape(-1) - expected_time)) > 1e-12 or np.any(np.diff(event_time.reshape(-1)) <= 0):
        raise ValueError(f"C* event clock mismatch: {scene_id}")
    expected_beta = np.minimum(plant_index.reshape(-1) * 0.001 / beta_rise_s, 1.0)
    expected_clip = np.clip(target, -dmax, dmax)
    expected_applied = expected_beta[:, None] * expected_clip
    if np.max(np.abs(beta - expected_beta)) > 1e-12 or np.max(np.abs(after_clip - expected_applied)) > 1e-10:
        raise ValueError(f"C* beta/clip target arithmetic mismatch: {scene_id}")
    if np.max(np.abs(beta[:, None] * target - applied)) > 1e-10:
        raise ValueError(f"C* raw target does not scale back to applied target: {scene_id}")
    expected_clip_mask = np.abs(target - expected_clip) > 1e-12
    if not np.array_equal(output_clip, expected_clip_mask):
        raise ValueError(f"C* output clip mask mismatch: {scene_id}")

    old_path = _repo_file(root, input_path)
    if old_path.stat().st_size != int(base_row["cache_bytes"]) or _sha256(old_path) != str(base_row["cache_sha256"]).lower():
        raise ValueError(f"original cache size/SHA mismatch: {scene_id}")
    old_vars = loadmat(old_path, squeeze_me=False, struct_as_record=False, variable_names=("X18", "event_time_s", "phase_code", "plant_index", "scene_id", "split"))
    x = _array(old_vars, "X18", (N_EVENTS, 18), np.float64)
    old_time = _array(old_vars, "event_time_s", (N_EVENTS, 1), np.float64)
    old_phase = _array(old_vars, "phase_code", (N_EVENTS, 1), np.uint8)
    old_index = _array(old_vars, "plant_index", (N_EVENTS, 1))
    if _text(old_vars["scene_id"]) != scene_id or _text(old_vars["split"]) != split:
        raise ValueError(f"original cache embedded identity mismatch: {scene_id}")
    if not np.array_equal(old_index, plant_index) or not np.array_equal(old_phase, phase) or np.max(np.abs(old_time - event_time)) > 1e-12:
        raise ValueError(f"C* event grouping differs from original X18 cache: {scene_id}")

    return {
        "scene_id": scene_id,
        "split": split,
        "X18": x,
        "target_raw_output_rad_s2": target,
        "target_applied_acceleration_rad_s2": applied,
        "target_after_clip_beta_rad_s2": after_clip,
        "event_time_s": event_time,
        "phase_code": phase,
        "plant_index": plant_index,
    }


def load_cstar_split(
    root: Path,
    manifest_relative_path: str,
    split: str,
    manifest_sha256: str,
) -> list[dict[str, Any]]:
    """Load only one split after verifying the pinned relabel and source manifests."""
    if split not in ("TRAIN", "VAL"):
        raise ValueError("only TRAIN and VAL are allowed")
    repo_root = Path(root).resolve(strict=True)
    manifest_path = _repo_file(repo_root, manifest_relative_path)
    if _sha256(manifest_path) != manifest_sha256.lower():
        raise ValueError("C* relabel manifest SHA256 mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != SCHEMA or manifest.get("status") != "PASS":
        raise ValueError("C* relabel manifest is not PASS or has the wrong schema")
    if manifest.get("scene_count") != 816 or manifest.get("qualified_count") != 816 or manifest.get("failed_count") != 0:
        raise ValueError("C* relabel scene qualification counts mismatch")
    if manifest.get("split_counts") != {"TRAIN": 768, "VAL": 48} or manifest.get("training_eligible") is not True:
        raise ValueError("C* relabel split counts or training eligibility gate failed")
    if manifest.get("TEST_accessed") is not False:
        raise ValueError("C* relabel manifest does not certify TEST isolation")
    scope = manifest.get("scope", {})
    if any(scope.get(key) != 0 for key in ("plant_calls", "engine_calls", "training_steps", "optimizer_steps")) or scope.get("TEST_accessed") is not False:
        raise ValueError("C* relabel scope is not offline-only")
    rows = manifest.get("rows")
    if not isinstance(rows, list) or len(rows) != 816:
        raise ValueError("C* relabel rows must contain all 816 scenes")
    source_rows, base_rows = _verify_input_manifests(repo_root, manifest)
    dmax = np.asarray(manifest.get("dmax_rad_s2"), dtype=np.float64)
    beta_rise_s = float(manifest.get("beta_rise_time_s", np.nan))
    if dmax.shape != (3,) or not np.isfinite(dmax).all() or np.any(dmax <= 0) or not np.isfinite(beta_rise_s) or beta_rise_s <= 0:
        raise ValueError("C* manifest clip/beta parameters are invalid")
    ids = []
    for ordinal, row in enumerate(rows, 1):
        if row.get("ordinal") != ordinal or row.get("scene_id") != source_rows[ordinal - 1].get("scene_id"):
            raise ValueError(f"C* relabel order mismatch at ordinal {ordinal}")
        ids.append(row.get("scene_id"))
    if len(set(ids)) != 816:
        raise ValueError("duplicate scene_id in C* relabel manifest")
    selected = [i for i, row in enumerate(rows) if row.get("split") == split]
    expected_count = 768 if split == "TRAIN" else 48
    if len(selected) != expected_count:
        raise ValueError(f"expected {expected_count} {split} rows, got {len(selected)}")
    return [
        _read_scene(repo_root, rows[i], source_rows[i], base_rows[i], dmax, beta_rise_s)
        for i in selected
    ]
