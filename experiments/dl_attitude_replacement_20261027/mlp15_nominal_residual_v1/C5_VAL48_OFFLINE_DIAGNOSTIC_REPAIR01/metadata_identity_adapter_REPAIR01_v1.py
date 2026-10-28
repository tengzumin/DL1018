#!/usr/bin/env python3
"""Metadata-only identity adapter for the frozen C5_VAL48 source set.

Only JSON identity metadata and named HDF5 identity/configuration metadata are
read. HDF5 log and command arrays are never accessed. Whole-file SHA-256 checks
read bytes only to bind each file to its frozen source record.
"""
from __future__ import annotations

import hashlib
import json
import ntpath
import os
from pathlib import Path
from typing import Any

import h5py
import numpy as np


ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
DIAG = ROOT / "experiments/dl_attitude_replacement_20261027/mlp15_nominal_residual_v1/C5_VAL48_OFFLINE_DIAGNOSTIC_v1"
SOURCE_FREEZE = DIAG / "C5_VAL48_SOURCE_FREEZE_v1.json"
IDENTITY_CHECK = DIAG / "C5_VAL48_IDENTITY_CHECK_v1.json"
SCORE_LOCK = DIAG / "C5_VAL48_SCORE_LOCK_v1.json"
FAILED_MARKER = DIAG / "C5_VAL48_SCORE_STARTED_v1.json"
FAILURE_REPORT = DIAG / "C5_VAL48_SCORE_FAILURE_v1.json"
C5_INPUT_LOCK = ROOT / "experiments/position_axis_coordinate_c5_dev72_20261023/C5_DEV72_INPUT_LOCK_v3.json"
C5_BATCH = ROOT / "experiments/position_axis_coordinate_c5_dev72_20261023/C5_DEV72_BATCH_STATUS_v3.json"
FULL72_SOURCE_LOCK = ROOT / "experiments/dl_attitude_replacement_20261026/mlp15_c5_teacher_full72_v1/MLP15_C5_TEACHER_FULL72_SOURCE_LOCK_v1.json"
PARENT_REUSE_SUMMARY = ROOT / "reports/paper_continuation_20261023/c5_axis_coordinate_parent_review/screen12_parent_review/SUMMARY.json"

EXPECTED = {
    "source_freeze": "7f15ef2570251e21a67149d8e133069c1b0d3ffa643675135031aba364d02634",
    "identity_check": "bd2dddba268b74c2aa0eaa1515cc8d85454447b55c93e02c34e94b3f703e4ffd",
    "score_lock": "3f63814353b587b50506783bc32041ca9644ce91fa2f1844c10bacc4c14d40c7",
    "c5_input_lock": "82024c01276cc4bfbd9b7772cf5332dee3fdfcbed422969589b68f1c90ed2d75",
    "c5_batch": "20cc9caca553ebf676fd7b39087fe0a2640fcd976aaf7c8cdb0030c76b5bea22",
    "full72_source_lock": "2c733dd093ab2ea1ff74f6cf2828a130345f022b3439456bf22abff8961edc8a",
    "parent_reuse_summary": "fe217ac8b259706b1953e07dd44586b6a64368a6d4f5e0145e8f507863d82ad8",
    "failed_marker": "0bd9428da5e64550b7d2876674830a4a1c10dfc40d1be8868edaf990ca16caa3",
    "failure_report": "d6a174ded63ce69407dd40276390720c142d753300c95def17c41ff6b2c780f8",
}
EXPECTED_SCHEMA_COUNTS = {
    "C5_TAIL11_RUN_IDENTITY_V2": 11,
    "C5_AXIS_COORDINATE_DEV72_RUN_IDENTITY_V3": 36,
    "C5_AXIS_COORDINATE_RUN_IDENTITY_V1": 1,
}
EXPECTED_ALIAS_COUNT = 16
EXPECTED_CANDIDATE = "C5_AXIS_MIXED_COORDINATE_M110"
EXPECTED_MASK = [1.0, 1.0, 0.0]
ALIAS_SUFFIX = "_ACC_FIX_V1"
N_STATES, N_TRANSITIONS = 20_001, 20_000


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def need(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def checked_hash(label: str, path: Path, expected: str) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"missing {label}: {path}")
    actual = sha256(path)
    need(actual == expected.lower(), f"{label} SHA mismatch: {actual} != {expected}")
    return actual


def repo_path(value: str | Path) -> Path:
    path = Path(value)
    path = (path if path.is_absolute() else ROOT / path).resolve(strict=True)
    try:
        path.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"source path escapes repository: {value}") from exc
    return path


def same_path(a: str | Path, b: str | Path) -> bool:
    # Lock files mix absolute Windows paths and repo-relative paths.
    pa, pb = str(a), str(b)
    if ntpath.isabs(pa):
        left = ntpath.normcase(ntpath.normpath(pa))
    else:
        left = os.path.normcase(os.path.normpath(str((ROOT / pa).resolve(strict=False))))
    if ntpath.isabs(pb):
        right = ntpath.normcase(ntpath.normpath(pb))
    else:
        right = os.path.normcase(os.path.normpath(str((ROOT / pb).resolve(strict=False))))
    return left == right


def h5_text(group: h5py.Group, key: str) -> str:
    """Decode one explicitly named identity string dataset; never dereference refs."""
    if key not in group or not isinstance(group[key], h5py.Dataset):
        return ""
    values = np.asarray(group[key][()]).reshape(-1)
    if values.dtype.kind in "ui":
        return "".join(chr(int(value)) for value in values if int(value) != 0)
    if values.dtype.kind in "SU":
        return "".join(value.decode() if isinstance(value, bytes) else str(value)
                        for value in values).rstrip("\x00")
    # Object references and numeric payloads are intentionally not followed/read.
    raise ValueError(f"identity text field has unsupported storage: {key} ({values.dtype})")


def h5_mask(group: h5py.Group) -> list[float] | None:
    if "coordinate_mask" not in group or not isinstance(group["coordinate_mask"], h5py.Dataset):
        return None
    values = np.asarray(group["coordinate_mask"][()], dtype=np.float64).reshape(-1)
    need(values.shape == (3,), "coordinate_mask metadata must have three entries")
    return values.tolist()


def group_fields(group: h5py.Group, names: tuple[str, ...]) -> dict[str, str]:
    return {name: h5_text(group, name) for name in names if name in group}


RAW_TEXT_FIELDS = (
    "schema", "scene_id", "source_scene_id", "candidate", "external_identity_sha256",
    "run_start_sha256", "physical_B_source_path", "physical_B_source_sha256",
    "scoring_B72_raw_path", "scoring_B72_raw_sha256", "scoring_B72_status_path",
    "scoring_B72_status_sha256", "scene_b_raw_sha256",
)
START_TEXT_FIELDS = (
    "schema", "scene_id", "source_scene_id", "candidate", "external_identity_sha256",
    "scene_raw_sha256", "physical_B_source_path", "physical_B_source_sha256",
    "scoring_B72_raw_path", "scoring_B72_raw_sha256", "scoring_B72_status_path",
    "scoring_B72_status_sha256", "scene_b_raw_sha256",
)
NESTED_TEXT_FIELDS = (
    "canonical_scene_id", "raw_scene_id", "scene_id", "payload_review_sha256",
    "B_raw_path", "B_raw_sha256", "external_identity_sha256", "source_scene_id",
)


def nested_h5_identity(group: h5py.Group) -> dict[str, str]:
    result = group_fields(group, NESTED_TEXT_FIELDS)
    if "identity" in group and isinstance(group["identity"], h5py.Group):
        result["identity"] = group_fields(group["identity"], NESTED_TEXT_FIELDS)  # type: ignore[assignment]
    return result


def read_raw_identity(path: Path) -> dict[str, Any]:
    # Access is deliberately limited to /runIdentity and its identity subgroups.
    with h5py.File(path, "r") as raw:
        need("runIdentity" in raw, "raw is missing /runIdentity")
        identity = raw["runIdentity"]
        result: dict[str, Any] = group_fields(identity, RAW_TEXT_FIELDS)
        result["coordinate_mask"] = h5_mask(identity)
        if "scene_identity" in identity and isinstance(identity["scene_identity"], h5py.Group):
            result["scene_identity"] = nested_h5_identity(identity["scene_identity"])
        else:
            result["scene_identity"] = {}
    return result


def read_start_identity(path: Path) -> dict[str, Any]:
    # Access is deliberately limited to /runStart and its scene_identity group.
    with h5py.File(path, "r") as start:
        root = start["runStart"] if "runStart" in start else start
        result: dict[str, Any] = group_fields(root, START_TEXT_FIELDS)
        result["coordinate_mask"] = h5_mask(root)
        if "scene_identity" in root and isinstance(root["scene_identity"], h5py.Group):
            nested = root["scene_identity"]
            start_identity_fields = group_fields(nested, NESTED_TEXT_FIELDS)
            for name in ("scene_id", "source_scene_id", "external_identity_sha256"):
                if not result.get(name) and start_identity_fields.get(name):
                    result[name] = start_identity_fields[name]
            result["scene_identity"] = start_identity_fields
            if "identity" in nested and isinstance(nested["identity"], h5py.Group):
                result["scene_identity"]["identity"] = group_fields(nested["identity"], NESTED_TEXT_FIELDS)
        else:
            result["scene_identity"] = {}
    return result


def validate_alias_values(scene_id: str, values: list[str], label: str) -> bool:
    allowed = {scene_id, scene_id + ALIAS_SUFFIX}
    for value in values:
        if value:
            need(value in allowed, f"{label} scene id is not canonical or approved alias for {scene_id}: {value}")
    return any(value == scene_id + ALIAS_SUFFIX for value in values)


def validate_nested_identity(nested: dict[str, Any], scene_id: str, b_source: dict[str, Any],
                             label: str, *, require_v2_payload: bool) -> str:
    if not nested:
        if require_v2_payload:
            raise ValueError(f"{label} nested V2 identity is missing for {scene_id}")
        return ""
    canonical = str(nested.get("canonical_scene_id", ""))
    if canonical:
        need(canonical == scene_id, f"{label} canonical_scene_id mismatch for {scene_id}: {canonical}")
    validate_alias_values(scene_id, [str(nested.get(k, "")) for k in ("scene_id", "raw_scene_id")], label)
    payload = str(nested.get("payload_review_sha256", "")).lower()
    if require_v2_payload:
        need(len(payload) == 64 and all(c in "0123456789abcdef" for c in payload),
             f"{label} V2 payload_review_sha256 missing/invalid for {scene_id}")
    elif payload:
        need(len(payload) == 64 and all(c in "0123456789abcdef" for c in payload),
             f"{label} payload_review_sha256 invalid for {scene_id}")
    b_sha = str(nested.get("B_raw_sha256", "")).lower()
    b_path = str(nested.get("B_raw_path", ""))
    if b_sha:
        need(b_sha == str(b_source["sha256"]).lower(), f"{label} B_raw_sha256 mismatch for {scene_id}")
    if b_path:
        need(same_path(b_path, b_source["path"]), f"{label} B_raw_path mismatch for {scene_id}")
    if require_v2_payload:
        need(b_sha == str(b_source["sha256"]).lower() and same_path(b_path, b_source["path"]),
             f"{label} V2 identity lacks the exact locked B source binding for {scene_id}")
    return payload


def validate_reuse_parent_audit(lock_rows: list[dict[str, Any]], summary: dict[str, Any]) -> dict[str, dict[str, Any]]:
    need(summary.get("status") == "C5_SCREEN_PASS", "parent C5 reuse summary is not PASS")
    need(summary.get("TEST_accessed") is False and int(summary.get("training", -1)) == 0
         and int(summary.get("new_Plant_in_audit", -1)) == 0,
         "parent reuse summary lacks TEST-sealed/no-training/no-new-Plant claims")
    need(summary.get("B_identity_status") == "PARENT_AUDITED_NEW_TRACEABLE_B72"
         and summary.get("gates", {}).get("all_12_complete_finite_STABLE_full_event_audits") is True,
         "parent reuse summary top-level identity gate failed")
    reused = [row for row in lock_rows if row.get("C5_reuse", {}).get("reused") is True]
    audits = summary.get("audits")
    need(len(reused) == len(audits) == 12, "parent summary/lock must bind exactly 12 reused scenes")
    by_id = {item.get("scene_id"): item for item in audits if isinstance(item, dict)}
    need(len(by_id) == 12 and set(by_id) == {row["scene_id"] for row in reused},
         "parent audit scene ids differ from reused lock rows")
    evidence: dict[str, dict[str, Any]] = {}
    for row in reused:
        sid = row["scene_id"]
        audit = by_id[sid]
        c5 = audit.get("C5_metrics", {})
        b72 = audit.get("B_metrics", {})
        reuse = row["C5_reuse"]
        b_lock = row["B72_scoring"]
        external = str(row["external_identity_sha256"]).lower()
        checks = (
            audit.get("status") == "PASS_C5_RAW_ALL_EVENTS",
            int(audit.get("event_count", -1)) == int(reuse.get("parent_screen_event_count", -2)),
            audit.get("B_identity_status") == "PARENT_AUDITED_NEW_TRACEABLE_B72",
            audit.get("TEST_accessed") is False,
            int(audit.get("new_Plant_in_audit", -1)) == 0,
            c5.get("scene_id") == sid and b72.get("scene_id") == sid,
            c5.get("method") == "C5_M110" and b72.get("method") == "B_TRACEABLE",
            str(c5.get("sha256", "")).lower() == str(reuse["raw_sha256"]).lower(),
            str(audit.get("raw_sha256", "")).lower() == str(reuse["raw_sha256"]).lower(),
            str(audit.get("run_status_sha256", "")).lower() == str(reuse["run_status_sha256"]).lower(),
            str(b72.get("sha256", "")).lower() == str(b_lock["raw_sha256"]).lower(),
            str(c5.get("external_identity_sha256", "")).lower() == external,
            str(b72.get("external_identity_sha256", "")).lower() == external,
            same_path(c5.get("path", ""), reuse["raw_path"]),
            same_path(b72.get("path", ""), b_lock["raw_path"]),
            reuse.get("parent_screen_status") == "PASS_C5_RAW_ALL_EVENTS",
        )
        need(all(checks), f"exact V2-compatible parent reuse audit binding failed for {sid}")
        evidence[sid] = {
            "parent_status": audit["status"], "parent_event_count_metadata": int(audit["event_count"]),
            "c5_raw_sha256": str(c5["sha256"]).lower(),
            "b72_raw_sha256": str(b72["sha256"]).lower(),
            "external_identity_sha256": external,
            "status": "PASS_EXACT_PARENT_AUDIT_BINDING",
        }
    return evidence


def verify_scene(record: dict[str, Any], lock_row: dict[str, Any], batch_row: dict[str, Any] | None,
                 parent_evidence: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, str]]:
    sid = record["scene_id"]
    reuse = lock_row.get("C5_reuse", {}).get("reused") is True
    if reuse:
        ref = lock_row["C5_reuse"]
        audit_state = ref.get("parent_screen_status", "")
        expected_paths = {
            "raw_path": ref["raw_path"], "status_path": ref["run_status_path"],
            "run_start_path": ref["run_start_path"],
        }
        expected_hashes = {
            "raw_sha256": ref["raw_sha256"], "status_sha256": ref["run_status_sha256"],
            "run_start_sha256": ref["run_start_sha256"],
        }
    else:
        need(batch_row is not None, f"missing C5 batch row for new scene {sid}")
        expected_paths = {
            "raw_path": batch_row["raw_path"], "status_path": batch_row["run_status_path"],
            "run_start_path": batch_row["run_start_path"],
        }
        expected_hashes = {
            "raw_sha256": batch_row["raw_sha256"], "status_sha256": batch_row["run_status_sha256"],
            "run_start_sha256": batch_row["run_start_sha256"],
        }
        audit_state = "C5_BATCH_STATUS_V3"
    for key in ("raw_path", "status_path", "run_start_path"):
        need(same_path(record[key], expected_paths[key]), f"{key} differs from locked C5 source for {sid}")
    for hash_key in ("raw_sha256", "status_sha256", "run_start_sha256"):
        need(str(record[hash_key]).lower() == str(expected_hashes[hash_key]).lower(),
             f"{hash_key} differs from locked C5 source for {sid}")
    need(record.get("source_split") == "C5_VAL48" and record.get("teacher_source") == "C5_RBF",
         f"source freeze split/teacher mismatch for {sid}")
    need(int(record.get("event_count", -1)) == 1999 and record.get("feature_shape") == [1999, 13]
         and record.get("target_shape") == [1999, 3], f"source freeze dimensions mismatch for {sid}")
    expected_audit_state = "PASS_C5_RAW_ALL_EVENTS" if reuse else "RUN_COMPLETE_RAW_PENDING_AUDIT"
    need(record.get("status_trace_audit_state") == expected_audit_state,
         f"source freeze audit state mismatch for {sid}: {record.get('status_trace_audit_state')}")

    paths = {key: repo_path(record[key]) for key in ("raw_path", "status_path", "run_start_path")}
    byte_hashes = {
        "raw_sha256": checked_hash(f"{sid} raw", paths["raw_path"], record["raw_sha256"]),
        "status_sha256": checked_hash(f"{sid} status", paths["status_path"], record["status_sha256"]),
        "run_start_sha256": checked_hash(f"{sid} run_start", paths["run_start_path"], record["run_start_sha256"]),
    }
    status = read_json(paths["status_path"])
    need(status.get("status") in ("RUN_COMPLETE_RAW_PENDING_AUDIT", "RUN_COMPLETE_STABLE"),
         f"unexpected run status for {sid}: {status.get('status')}")
    need(status.get("scene_id") == sid, f"status canonical scene_id mismatch for {sid}")
    need(str(status.get("raw_sha256", "")).lower() == str(record["raw_sha256"]).lower()
         and same_path(status.get("raw_path", ""), record["raw_path"]), f"status raw binding mismatch for {sid}")
    need(str(status.get("run_start_sha256", "")).lower() == str(record["run_start_sha256"]).lower()
         and same_path(status.get("run_start_path", ""), record["run_start_path"]),
         f"status run_start binding mismatch for {sid}")
    if status.get("run_status_path"):
        need(same_path(status["run_status_path"], record["status_path"]), f"embedded status path mismatch for {sid}")
    need(status.get("log_status") == "STABLE" and int(status.get("transitions", -1)) == N_TRANSITIONS
         and int(status.get("state_samples", -1)) == N_STATES
         and status.get("safety_stop_reason", "") in ("", None), f"run completeness metadata mismatch for {sid}")

    raw_id = read_raw_identity(paths["raw_path"])
    start_id = read_start_identity(paths["run_start_path"])
    raw_schema = raw_id.get("schema", "")
    need(raw_schema in EXPECTED_SCHEMA_COUNTS, f"unexpected runIdentity schema for {sid}: {raw_schema}")
    expected_start_schema = {
        "C5_TAIL11_RUN_IDENTITY_V2": "C5_TAIL11_RUN_START_V2",
        "C5_AXIS_COORDINATE_DEV72_RUN_IDENTITY_V3": "C5_AXIS_COORDINATE_DEV72_RUN_START_V3",
        "C5_AXIS_COORDINATE_RUN_IDENTITY_V1": "C5_AXIS_COORDINATE_RUN_START_V1",
    }[raw_schema]
    need(start_id.get("schema") == expected_start_schema,
         f"raw/run_start identity schema pair mismatch for {sid}: {raw_schema}/{start_id.get('schema')}")
    if raw_id.get("run_start_sha256"):
        need(str(raw_id["run_start_sha256"]).lower() == str(record["run_start_sha256"]).lower(),
             f"raw identity run_start SHA mismatch for {sid}")
    expected_external = str(lock_row["external_identity_sha256"]).lower()
    need(len(expected_external) == 64 and all(c in "0123456789abcdef" for c in expected_external),
         f"input-lock external identity SHA invalid for {sid}")
    need(str(record.get("scene_identity_sha256", "")).lower() == expected_external,
         f"source freeze external identity differs from input lock for {sid}")
    need(str(lock_row.get("candidate_action", "")) in ("REUSE_AUDITED_C5_SCREEN", "PROPOSE_NEW_C5_M110_RUN"),
         f"unexpected source action for {sid}")

    source_scene_id = str(status.get("source_scene_id", ""))
    raw_ids = [str(raw_id.get("scene_id", ""))]
    start_ids = [str(start_id.get("scene_id", "")), str(start_id.get("source_scene_id", ""))]
    status_alias = validate_alias_values(sid, [source_scene_id], f"status {sid}")
    raw_alias = validate_alias_values(sid, raw_ids, f"raw {sid}")
    start_alias = validate_alias_values(sid, start_ids, f"run_start {sid}")
    raw_nested = raw_id.get("scene_identity", {})
    start_nested = start_id.get("scene_identity", {})
    status_nested = status.get("scene_identity") if isinstance(status.get("scene_identity"), dict) else {}
    for label, nested in (("raw", raw_nested), ("run_start", start_nested), ("status", status_nested)):
        layers = [nested]
        if isinstance(nested.get("identity"), dict):
            layers.append(nested["identity"])
        for layer in layers:
            raw_alias |= validate_alias_values(sid, [str(layer.get(k, "")) for k in ("scene_id", "raw_scene_id")],
                                               f"{label} nested {sid}")
            canonical = str(layer.get("canonical_scene_id", ""))
            if canonical:
                need(canonical == sid, f"{label} canonical_scene_id mismatch for {sid}")

    # Candidate and the small controller coordinate mask are identity/config metadata.
    for label, candidate, mask in (
        ("status", str(status.get("candidate", "")), status.get("coordinate_mask")),
        ("raw", str(raw_id.get("candidate", "")), raw_id.get("coordinate_mask")),
        ("run_start", str(start_id.get("candidate", "")), start_id.get("coordinate_mask")),
    ):
        if candidate:
            need(candidate == EXPECTED_CANDIDATE, f"{label} candidate mismatch for {sid}")
        if mask is not None:
            need(np.array_equal(np.asarray(mask, dtype=np.float64), np.asarray(EXPECTED_MASK)),
                 f"{label} coordinate_mask mismatch for {sid}")
    need(status.get("candidate") == EXPECTED_CANDIDATE
         and np.array_equal(np.asarray(status.get("coordinate_mask"), dtype=np.float64), np.asarray(EXPECTED_MASK)),
         f"status candidate/mask missing or mismatched for {sid}")
    need(raw_id.get("candidate") == EXPECTED_CANDIDATE and raw_id.get("coordinate_mask") == EXPECTED_MASK,
         f"raw candidate/mask missing or mismatched for {sid}")
    need(start_id.get("coordinate_mask") == EXPECTED_MASK,
         f"run_start coordinate_mask missing or mismatched for {sid}")

    # Bind the physical B source and traceable B72 scoring source separately.
    b_source = lock_row["B_source"]
    b72 = lock_row["B72_scoring"]
    need(b72.get("scene_id") == sid, f"B72 scoring scene mapping mismatch for {sid}")
    if start_id.get("scene_raw_sha256"):
        expected_start_raw_sha = b_source["sha256"] if raw_schema == "C5_AXIS_COORDINATE_RUN_IDENTITY_V1" else record["raw_sha256"]
        need(str(start_id["scene_raw_sha256"]).lower() == str(expected_start_raw_sha).lower(),
             f"run_start scene_raw_sha256 provenance mismatch for {sid}")
    legacy_reused = reuse and raw_schema == "C5_AXIS_COORDINATE_RUN_IDENTITY_V1"
    status_b_source_sha = str(status.get("physical_B_source_sha256", "")).lower()
    status_b_source_path = str(status.get("physical_B_source_path", ""))
    if status_b_source_sha or status_b_source_path:
        need(status_b_source_sha == str(b_source["sha256"]).lower()
             and same_path(status_b_source_path, b_source["path"]),
             f"status physical B source chain mismatch for {sid}")
    else:
        need(legacy_reused and str(raw_id.get("scene_b_raw_sha256", "")).lower()
             == str(b_source["sha256"]).lower() and parent_evidence is not None,
             f"missing physical B source metadata without exact legacy reuse fallback for {sid}")
    status_b72_sha = str(status.get("scoring_B72_raw_sha256", "")).lower()
    status_b72_path = str(status.get("scoring_B72_raw_path", ""))
    if status_b72_sha or status_b72_path:
        need(status_b72_sha == str(b72["raw_sha256"]).lower()
             and same_path(status_b72_path, b72["raw_path"]),
             f"status same-scene B72 scoring raw chain mismatch for {sid}")
    else:
        need(legacy_reused and parent_evidence is not None
             and str(raw_id.get("scoring_B72_raw_sha256", "")).lower() == str(b72["raw_sha256"]).lower()
             and same_path(raw_id.get("scoring_B72_raw_path", ""), b72["raw_path"]),
             f"missing B72 scoring metadata without exact legacy reuse fallback for {sid}")
    if status.get("scoring_B72_status_sha256"):
        need(str(status["scoring_B72_status_sha256"]).lower() == str(b72["run_status_sha256"]).lower(),
             f"status same-scene B72 status SHA mismatch for {sid}")
    if status.get("scoring_B72_status_path"):
        need(same_path(status["scoring_B72_status_path"], b72["run_status_path"]),
             f"status same-scene B72 status path mismatch for {sid}")

    # Any actual external identity fields must match. Missing fields are allowed
    # only for audited reused rows; payload_review_sha256 is never substituted.
    raw_external = str(raw_id.get("external_identity_sha256", "")).lower()
    start_external = str(start_id.get("external_identity_sha256", "")).lower()
    status_external = str(status.get("external_identity_sha256", "")).lower()
    for label, value in (("raw", raw_external), ("run_start", start_external), ("status", status_external)):
        if value:
            need(value == expected_external, f"{label} external_identity_sha256 mismatch for {sid}")
    if reuse:
        need(parent_evidence is not None, f"reused row lacks exact parent audit fallback for {sid}")
        b_payload = validate_nested_identity(raw_nested, sid, b_source, "raw", require_v2_payload=raw_schema == "C5_TAIL11_RUN_IDENTITY_V2")
        s_payload = validate_nested_identity(start_nested, sid, b_source, "run_start", require_v2_payload=raw_schema == "C5_TAIL11_RUN_IDENTITY_V2")
        st_payload = validate_nested_identity(status_nested, sid, b_source, "status", require_v2_payload=bool(status_nested))
        payloads = [p for p in (b_payload, s_payload, st_payload) if p]
        if payloads:
            need(len(set(payloads)) == 1, f"V2 payload review SHA differs across raw/start/status for {sid}")
        # Legacy V1 reused identity exposes only the physical-B SHA.
        raw_b_sha = str(raw_id.get("scene_b_raw_sha256", "")).lower()
        if raw_b_sha:
            need(raw_b_sha == str(b_source["sha256"]).lower(), f"legacy raw scene_b_raw_sha256 mismatch for {sid}")
        need(str(raw_id.get("scoring_B72_raw_sha256", "")).lower() == str(b72["raw_sha256"]).lower()
             and same_path(raw_id.get("scoring_B72_raw_path", ""), b72["raw_path"]),
             f"reused raw B72 scoring chain mismatch for {sid}")
        if start_id.get("scoring_B72_raw_sha256"):
            need(str(start_id["scoring_B72_raw_sha256"]).lower() == str(b72["raw_sha256"]).lower()
                 and same_path(start_id.get("scoring_B72_raw_path", ""), b72["raw_path"]),
                 f"reused run_start B72 scoring chain mismatch for {sid}")
        identity_binding = "C5_DEV72 lock external SHA + exact parent reuse audit; V2 payload SHA remains separate"
        if raw_schema == "C5_TAIL11_RUN_IDENTITY_V2":
            need(raw_nested.get("canonical_scene_id") == sid
                 and str(raw_nested.get("raw_scene_id", "")) in (sid, sid + ALIAS_SUFFIX),
                 f"raw V2 canonical/raw scene mapping mismatch for {sid}")
            need(start_nested.get("canonical_scene_id") == sid
                 and str(start_nested.get("raw_scene_id", "")) in (sid, sid + ALIAS_SUFFIX),
                 f"run_start V2 canonical/raw scene mapping mismatch for {sid}")
        else:
            need(raw_schema == "C5_AXIS_COORDINATE_RUN_IDENTITY_V1" and not raw_nested and not start_nested,
                 f"unsupported reused legacy identity form for {sid}")
    else:
        need(raw_external == expected_external and start_external == expected_external,
             f"new C5 row must bind external identity in raw and run_start for {sid}")
        need(start_id.get("source_scene_id") in (sid, sid + ALIAS_SUFFIX),
             f"new C5 run_start source_scene_id mismatch for {sid}")
        identity_binding = "raw.runIdentity and run_start.scene_identity external SHA both equal C5_DEV72 lock"
        b_payload = s_payload = st_payload = ""

    alias = bool(status_alias or raw_alias or start_alias)
    return status, raw_id, start_id, {
        "identity_binding": identity_binding,
        "raw_schema": raw_schema,
        "is_reused": str(reuse).lower(),
        "is_acc_fix_alias": str(alias).lower(),
        "canonical_scene_id": sid,
        "raw_scene_id": str(raw_nested.get("raw_scene_id", raw_id.get("scene_id", ""))),
        "source_scene_id": source_scene_id,
        "external_identity_sha256_from_lock": expected_external,
        "raw_external_identity_sha256_actual": raw_external,
        "run_start_external_identity_sha256_actual": start_external,
        "status_external_identity_sha256_actual": status_external,
        "payload_review_sha256": (b_payload if reuse else ""),
        "physical_B_source_sha256": str(b_source["sha256"]).lower(),
        "B72_scoring_raw_sha256": str(b72["raw_sha256"]).lower(),
        "raw_sha256_verified": byte_hashes["raw_sha256"],
        "status_sha256_verified": byte_hashes["status_sha256"],
        "run_start_sha256_verified": byte_hashes["run_start_sha256"],
        "status_value": str(status.get("status", "")),
        "candidate": EXPECTED_CANDIDATE,
        "coordinate_mask": EXPECTED_MASK,
        "event_metadata": {"transitions": int(status["transitions"]), "state_samples": int(status["state_samples"])},
        "parent_reuse_audit": (parent_evidence or {}).get("status", "NOT_APPLICABLE"),
        "audit_status": "PASS_METADATA_ONLY",
    }


def load_context() -> dict[str, Any]:
    source_freeze = read_json(SOURCE_FREEZE)
    identity_check = read_json(IDENTITY_CHECK)
    old_score_lock = read_json(SCORE_LOCK)
    input_lock = read_json(C5_INPUT_LOCK)
    batch = read_json(C5_BATCH)
    full72_lock = read_json(FULL72_SOURCE_LOCK)
    parent_summary = read_json(PARENT_REUSE_SUMMARY)
    for label, path in (("source_freeze", SOURCE_FREEZE), ("identity_check", IDENTITY_CHECK),
                        ("score_lock", SCORE_LOCK), ("c5_input_lock", C5_INPUT_LOCK),
                        ("c5_batch", C5_BATCH), ("full72_source_lock", FULL72_SOURCE_LOCK),
                        ("parent_reuse_summary", PARENT_REUSE_SUMMARY),
                        ("failed_marker", FAILED_MARKER), ("failure_report", FAILURE_REPORT)):
        checked_hash(label, path, EXPECTED[label])
    need(input_lock.get("schema") == "C5_AXIS_COORDINATE_DEV72_INPUT_LOCK_V3", "C5 input lock schema mismatch")
    need(batch.get("schema") == "C5_AXIS_COORDINATE_DEV72_BATCH_STATUS_V3", "C5 batch schema mismatch")
    need(full72_lock.get("status") == "APPROVED_FOR_TRAINING", "full72 source lock status mismatch")
    need(source_freeze.get("schema") == "DL1018_MLP15_C5_VAL48_SOURCE_FREEZE_V1"
         and source_freeze.get("status") == "FROZEN_BEFORE_NUMERIC_READ"
         and source_freeze.get("scene_count") == 48 and source_freeze.get("validation_split") == "C5_VAL48",
         "VAL source freeze contract mismatch")
    need(identity_check.get("status") == "PASS" and identity_check.get("all_sha_match") is True
         and identity_check.get("files_checked") == 144
         and identity_check.get("source_freeze_manifest_sha256") == EXPECTED["source_freeze"],
         "frozen 144-file identity check is not PASS")
    lock_rows = [row for row in input_lock.get("scenes", []) if row.get("source_split") == "VAL"]
    need(len(lock_rows) == 48, "C5_DEV72 input lock must contain exactly 48 VAL rows")
    freeze_rows = source_freeze["records"]
    need(len(freeze_rows) == 48 and source_freeze.get("scene_ids") == [row["scene_id"] for row in freeze_rows],
         "source freeze scene list/order mismatch")
    need(source_freeze.get("source_lock_sha256") == EXPECTED["full72_source_lock"],
         "source freeze does not bind the reviewed full72 source lock")
    need([row["scene_id"] for row in lock_rows] == source_freeze["scene_ids"],
         "C5_DEV72 VAL order differs from the frozen C5_VAL48 scene order")
    lock_by_id = {row["scene_id"]: row for row in lock_rows}
    need(len(lock_by_id) == 48, "duplicate C5_DEV72 VAL scene id")
    need(set(lock_by_id) == set(source_freeze["scene_ids"]), "C5_DEV72 VAL scene set differs from frozen C5_VAL48")
    batch_by_id = {row["scene_id"]: row for row in batch.get("records", [])}
    need(len(batch_by_id) == 60, "C5 batch must contain exactly 60 new rows")
    parent_evidence = validate_reuse_parent_audit(lock_rows, parent_summary)
    reused_ids = {row["scene_id"] for row in lock_rows if row.get("C5_reuse", {}).get("reused") is True}
    need(len(reused_ids) == 12 and set(parent_evidence) == reused_ids, "reused C5 set differs from parent audit")
    return {
        "source_freeze": source_freeze, "identity_check": identity_check,
        "old_score_lock": old_score_lock, "input_lock": input_lock, "batch": batch,
        "full72_lock": full72_lock, "parent_summary": parent_summary,
        "lock_by_id": lock_by_id, "batch_by_id": batch_by_id,
        "parent_evidence": parent_evidence, "rows_by_id": {r["scene_id"]: r for r in freeze_rows},
    }


def audit_all() -> dict[str, Any]:
    context = load_context()
    schema_counts: dict[str, int] = {}
    rows: list[dict[str, Any]] = []
    hash_cache: dict[str, str] = {}
    for record in context["source_freeze"]["records"]:
        sid = record["scene_id"]
        lock_row = context["lock_by_id"][sid]
        reused = lock_row.get("C5_reuse", {}).get("reused") is True
        batch_row = None if reused else context["batch_by_id"].get(sid)
        metadata, raw_id, start_id, summary = verify_scene(
            record, lock_row, batch_row,
            context["parent_evidence"].get(sid) if reused else None,
        )
        schema_counts[summary["raw_schema"]] = schema_counts.get(summary["raw_schema"], 0) + 1
        for key, path_key in (("raw_sha256_verified", "raw_path"),
                              ("status_sha256_verified", "status_path"),
                              ("run_start_sha256_verified", "run_start_path")):
            hash_cache[str(repo_path(record[path_key]))] = summary[key]
        rows.append({
            "scene_id": sid,
            "source_split": "C5_VAL48",
            "input_lock_source_split": lock_row["source_split"],
            "raw_identity_schema": summary["raw_schema"],
            "is_reused": summary["is_reused"],
            "is_acc_fix_alias": summary["is_acc_fix_alias"],
            "canonical_scene_id": summary["canonical_scene_id"],
            "raw_scene_id": summary["raw_scene_id"],
            "status_source_scene_id": summary["source_scene_id"],
            "external_identity_sha256_lock": summary["external_identity_sha256_from_lock"],
            "raw_external_identity_sha256_actual": summary["raw_external_identity_sha256_actual"],
            "run_start_external_identity_sha256_actual": summary["run_start_external_identity_sha256_actual"],
            "status_external_identity_sha256_actual": summary["status_external_identity_sha256_actual"],
            "payload_review_sha256_separate": summary["payload_review_sha256"],
            "raw_path": record["raw_path"], "raw_sha256": summary["raw_sha256_verified"],
            "status_path": record["status_path"], "status_sha256": summary["status_sha256_verified"],
            "run_start_path": record["run_start_path"], "run_start_sha256": summary["run_start_sha256_verified"],
            "candidate": summary["candidate"], "coordinate_mask": summary["coordinate_mask"],
            "physical_B_source_sha256": summary["physical_B_source_sha256"],
            "B72_scoring_raw_sha256": summary["B72_scoring_raw_sha256"],
            "parent_reuse_audit": summary["parent_reuse_audit"],
            "identity_binding": summary["identity_binding"],
            "status_value": summary["status_value"], "transitions": summary["event_metadata"]["transitions"],
            "state_samples": summary["event_metadata"]["state_samples"],
            "audit_status": summary["audit_status"],
        })
    alias_count = sum(row["is_acc_fix_alias"] == "true" for row in rows)
    need(len(rows) == 48, "metadata audit must cover all 48 VAL scenes")
    need(schema_counts == EXPECTED_SCHEMA_COUNTS, f"runIdentity schema counts changed: {schema_counts}")
    need(alias_count == EXPECTED_ALIAS_COUNT, f"_ACC_FIX_V1 alias count changed: {alias_count}")
    return {
        "status": "PASS_METADATA_ONLY_IDENTITY_ADAPTER",
        "source_scene_count": len(rows), "schema_counts": schema_counts,
        "acc_fix_alias_count": alias_count, "reused_scene_count": 12,
        "fresh_batch_scene_count": 36,
        "source_freeze_sha256": EXPECTED["source_freeze"],
        "c5_dev72_input_lock_sha256": EXPECTED["c5_input_lock"],
        "c5_batch_status_sha256": EXPECTED["c5_batch"],
        "full72_source_lock_sha256": EXPECTED["full72_source_lock"],
        "parent_reuse_summary_sha256": EXPECTED["parent_reuse_summary"],
        "failed_score_marker_sha256_preserved": EXPECTED["failed_marker"],
        "failure_report_sha256_preserved": EXPECTED["failure_report"],
        "raw_status_run_start_byte_hashes_revalidated": True,
        "hdf5_raw_members_read": ["/runIdentity/<whitelisted identity text fields>", "/runIdentity/coordinate_mask metadata"],
        "hdf5_run_start_members_read": ["/runStart/<whitelisted identity text fields>", "/runStart/scene_identity/<whitelisted identity fields>", "/runStart/coordinate_mask metadata"],
        "status_json_fields_read": ["source/run identity", "candidate/mask", "raw/run_start paths and SHAs", "physical B source and B72 chain", "run completeness metadata"],
        "numeric_log_or_command_arrays_opened": False,
        "numeric_VAL_features_or_labels_read": False,
        "TEST_accessed": False, "Plant_called": False, "training_run": False,
        "score_start_marker_created": False, "scoring_started": False,
        "rows": rows,
        "hash_cache_for_preflight": hash_cache,
    }


def verify_run_identity_for_builder(row: dict[str, Any], raw_path: Path, status_path: Path,
                                    start_path: Path, context: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Narrow replacement for TRAIN builder's legacy external/source-id gate.

    It preserves actual per-file fields and reports the lock-bound external ID
    separately; V2 payload review SHA is never promoted to an external SHA.
    """
    sid = row["scene_id"]
    record = context["rows_by_id"].get(sid)
    need(record is not None, f"builder requested a scene outside frozen VAL48: {sid}")
    for key, path in (("raw_path", raw_path), ("status_path", status_path), ("run_start_path", start_path)):
        need(same_path(row[key], record[key]) and same_path(path, record[key]),
             f"builder path differs from metadata-audited source freeze for {sid}: {key}")
    lock_row = context["lock_by_id"][sid]
    reused = lock_row.get("C5_reuse", {}).get("reused") is True
    status, raw_id, start_id, summary = verify_scene(
        record, lock_row, None if reused else context["batch_by_id"].get(sid),
        context["parent_evidence"].get(sid) if reused else None,
    )
    raw_actual = str(raw_id.get("external_identity_sha256", "")).lower()
    start_actual = str(start_id.get("external_identity_sha256", "")).lower()
    return status, {
        "raw": {
            "scene_id": raw_id.get("scene_id", ""), "candidate": raw_id.get("candidate", ""),
            "coordinate_mask": raw_id.get("coordinate_mask"),
            "external_identity_sha256": raw_actual,
            "external_identity_sha256_lock_binding": str(lock_row["external_identity_sha256"]).lower(),
            "scene_identity": raw_id.get("scene_identity", {}),
        },
        "run_start": {
            "scene_id": start_id.get("scene_id", ""), "source_scene_id": start_id.get("source_scene_id", ""),
            "coordinate_mask": start_id.get("coordinate_mask"),
            "external_identity_sha256": start_actual,
            "external_identity_sha256_lock_binding": str(lock_row["external_identity_sha256"]).lower(),
            "scene_identity": start_id.get("scene_identity", {}),
        },
        "identity_binding": summary["identity_binding"],
        "payload_review_sha256_separate": summary["payload_review_sha256"],
    }


def builder_verifier(context: dict[str, Any]):
    return lambda row, raw_path, status_path, start_path: verify_run_identity_for_builder(
        row, raw_path, status_path, start_path, context
    )
