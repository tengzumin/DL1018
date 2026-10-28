#!/usr/bin/env python3
"""Build matched B24/C5-24 training data and common C5 VAL48 action data.

This is an offline, read-only raw parser. It reads only the frozen DEV/VAL rows
from C5_DEV72_INPUT_LOCK_v3, their B72 scoring raw/status, and the C5 batch
status/reused C5 rows. It never discovers inputs by directory globbing.
Generation requires the explicit --execute flag and refuses to overwrite.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import ntpath
import platform
import sys
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import scipy


ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
C5_LOCK_REL = Path("experiments/position_axis_coordinate_c5_dev72_20261023/C5_DEV72_INPUT_LOCK_v3.json")
C5_BATCH_REL = Path("experiments/position_axis_coordinate_c5_dev72_20261023/C5_DEV72_BATCH_STATUS_v3.json")
B_LOCK_REL = Path("experiments/b_traceable_c3core_dev72_20261023/B_TRACEABLE_DEV72_INPUT_LOCK_v3.json")
PARENT_REUSE_SUMMARY_REL = Path("reports/paper_continuation_20261023/c5_axis_coordinate_parent_review/screen12_parent_review/SUMMARY.json")
MORPH_SOURCE_REL = Path("matlab/core/tcn0916_morphology_scenario.m")
C5_TEACHER_AUDIT_REL = Path("experiments/dl_attitude_replacement_20261026/mlp15_c5_teacher_redistill_v1/audits/C5_TEACHER_RAW_AND_MLP15_SAME_STATE_AUDIT_v1.md")
EXPECTED_C5_TEACHER_AUDIT_SHA = "fe577e5530a949472c319eb9adfee9d81c3c130fea95def57d474b8735c6edf4"
EXPECTED_C5_LOCK_SHA = "82024c01276cc4bfbd9b7772cf5332dee3fdfcbed422969589b68f1c90ed2d75"
EXPECTED_C5_BATCH_SHA = "20cc9caca553ebf676fd7b39087fe0a2640fcd976aaf7c8cdb0030c76b5bea22"
EXPECTED_B_LOCK_SHA = "8d738e5c70ba2fc8697550549d1a0537f08eadb49b99bc5684e5c26f6222f452"
EXPECTED_PARENT_REUSE_SUMMARY_SHA = "fe217ac8b259706b1953e07dd44586b6a64368a6d4f5e0145e8f507863d82ad8"
EVENTS = np.arange(10, 20_000, 10, dtype=np.int64)
N_EVENTS = 1999
N_TRANSITIONS = 20_000
N_STATES = 20_001
DMAX_EXPECTED = np.array([45.0, 45.0, 4.7124], dtype=np.float64)
J0_DIAGONAL = np.array([0.003257553333333334, 0.0032575533333333334, 0.006360648333333333], dtype=np.float64)
FEATURE_ORDER = [
    "wrapped_attitude_error_euler_rad_x3",
    "body_rate_rad_s_x3",
    "nominal_bs_body_torque_Nm_x3",
    "morph_command_x4",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def repo_file(value: str | Path, *, must_exist: bool = True) -> Path:
    p = Path(value)
    p = (p if p.is_absolute() else ROOT / p).resolve(strict=must_exist)
    try:
        p.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"input path escapes repository: {value}") from exc
    return p


def same_repo_path(a: str | Path, b: str | Path) -> bool:
    return repo_file(a).as_posix().casefold() == repo_file(b).as_posix().casefold()


def same_absolute_path_string(a: str | Path, b: str | Path) -> bool:
    paths = (str(a), str(b))
    if any(not ntpath.isabs(path) or not ntpath.splitdrive(path)[0] for path in paths):
        raise ValueError("identity paths must be absolute drive or UNC paths")
    return ntpath.normcase(ntpath.normpath(paths[0])) == ntpath.normcase(ntpath.normpath(paths[1]))


def validate_reused_scene_parent_audits(
    c5_rows: list[dict[str, Any]], summary: dict[str, Any], summary_path: Path,
) -> dict[str, dict[str, Any]]:
    if (summary.get("status") != "C5_SCREEN_PASS"
            or summary.get("TEST_accessed") is not False
            or int(summary.get("training", -1)) != 0
            or int(summary.get("new_Plant_in_audit", -1)) != 0
            or summary.get("B_identity_status") != "PARENT_AUDITED_NEW_TRACEABLE_B72"
            or summary.get("gates", {}).get("all_12_complete_finite_STABLE_full_event_audits") is not True):
        raise ValueError("parent C5 reuse summary lacks PASS/TEST-sealed/no-training/no-Plant top-level gate")
    reuse_rows = [row for row in c5_rows if row.get("C5_reuse", {}).get("reused") is True]
    audits = summary.get("audits")
    if not isinstance(audits, list) or len(reuse_rows) != 12 or len(audits) != 12:
        raise ValueError("parent summary and lock must each contain exactly 12 audited reuse scenes")
    audit_by_id = {audit.get("scene_id"): audit for audit in audits if isinstance(audit, dict)}
    if len(audit_by_id) != 12 or set(audit_by_id) != {row["scene_id"] for row in reuse_rows}:
        raise ValueError("parent audit scene IDs differ from the frozen 12-scene C5 reuse list")

    evidence: dict[str, dict[str, Any]] = {}
    for row in reuse_rows:
        sid = row["scene_id"]
        audit = audit_by_id[sid]
        c5 = audit.get("C5_metrics", {})
        b72 = audit.get("B_metrics", {})
        lock_reuse = row["C5_reuse"]
        lock_b = row["B72_scoring"]
        external = str(row["external_identity_sha256"]).lower()
        checks = (
            audit.get("status") == "PASS_C5_RAW_ALL_EVENTS",
            audit.get("event_count") == int(lock_reuse.get("parent_screen_event_count", -1)),
            audit.get("B_identity_status") == "PARENT_AUDITED_NEW_TRACEABLE_B72",
            audit.get("TEST_accessed") is False,
            int(audit.get("new_Plant_in_audit", -1)) == 0,
            audit.get("scene_id") == sid,
            c5.get("scene_id") == sid and b72.get("scene_id") == sid,
            str(c5.get("method", "")) == "C5_M110",
            str(b72.get("method", "")) == "B_TRACEABLE",
            str(c5.get("sha256", "")).lower() == str(lock_reuse.get("raw_sha256", "")).lower(),
            str(audit.get("raw_sha256", "")).lower() == str(lock_reuse.get("raw_sha256", "")).lower(),
            str(audit.get("run_status_sha256", "")).lower() == str(lock_reuse.get("run_status_sha256", "")).lower(),
            str(b72.get("sha256", "")).lower() == str(lock_b.get("raw_sha256", "")).lower(),
            str(c5.get("external_identity_sha256", "")).lower() == external,
            str(b72.get("external_identity_sha256", "")).lower() == external,
            same_repo_path(c5.get("path", ""), lock_reuse.get("raw_path", "")),
            same_repo_path(b72.get("path", ""), lock_b.get("raw_path", "")),
            lock_reuse.get("parent_screen_status") == "PASS_C5_RAW_ALL_EVENTS",
        )
        if not all(checks):
            raise ValueError(f"parent reuse evidence does not exactly bind lock/raw/status/identity for {sid}")
        evidence[sid] = {
            "summary_path": str(summary_path),
            "summary_sha256": EXPECTED_PARENT_REUSE_SUMMARY_SHA,
            "parent_status": audit["status"],
            "parent_event_count_metadata": int(audit["event_count"]),
            "c5_raw_sha256": str(c5["sha256"]).lower(),
            "b72_raw_sha256": str(b72["sha256"]).lower(),
            "c5_external_identity_sha256": str(c5["external_identity_sha256"]).lower(),
            "b72_external_identity_sha256": str(b72["external_identity_sha256"]).lower(),
            "B_identity_status": audit["B_identity_status"],
            "TEST_accessed": audit["TEST_accessed"],
            "new_Plant_in_audit": int(audit["new_Plant_in_audit"]),
            "status": "PASS_EXACT_PARENT_AUDIT_BINDING",
        }
    return evidence


def text_dataset(group: h5py.Group, key: str) -> str:
    a = np.asarray(group[key]).reshape(-1)
    if a.dtype.kind in "ui":
        return "".join(chr(int(x)) for x in a if int(x) != 0)
    if a.dtype.kind in "SU":
        return "".join(x.decode() if isinstance(x, bytes) else str(x) for x in a).rstrip("\x00")
    return str(a[0]) if len(a) == 1 else ""


def optional_text(group: h5py.Group, key: str) -> str:
    return text_dataset(group, key) if key in group else ""


def status_binding(raw_path: Path, status_path: Path, expected_raw_sha: str,
                   expected_status_sha: str, expected_start_sha: str | None,
                   expected_start_path: str | None, scene_id: str) -> tuple[dict[str, Any], Path, str, str]:
    if sha256(raw_path) != expected_raw_sha.lower():
        raise ValueError(f"raw SHA mismatch: {scene_id}")
    if sha256(status_path) != expected_status_sha.lower():
        raise ValueError(f"status SHA mismatch: {scene_id}")
    status = read_json(status_path)
    if status.get("status") not in ("RUN_COMPLETE_RAW_PENDING_AUDIT", "RUN_COMPLETE_STABLE"):
        raise ValueError(f"run_status is not an allowed completed/pending state: {scene_id}: {status.get('status')}")
    if status.get("scene_id") != scene_id:
        raise ValueError(f"status scene_id mismatch: {scene_id}")
    if Path(status.get("raw_path", "")).resolve() != raw_path.resolve():
        raise ValueError(f"status raw_path mismatch: {scene_id}")
    if str(status.get("raw_sha256", "")).lower() != expected_raw_sha.lower():
        raise ValueError(f"status raw_sha256 mismatch: {scene_id}")
    embedded_status_path = status.get("run_status_path")
    if embedded_status_path:
        if repo_file(embedded_status_path).resolve() != status_path.resolve():
            raise ValueError(f"embedded run_status_path mismatch: {scene_id}")
        status_path_binding = "embedded run_status_path matches frozen path"
    else:
        status_path_binding = "run_status_path absent; frozen record path plus locked status SHA"
    if status.get("log_status") != "STABLE" or int(status.get("transitions", -1)) != N_TRANSITIONS or int(status.get("state_samples", -1)) != N_STATES:
        raise ValueError(f"status run completeness mismatch: {scene_id}")
    if status.get("safety_stop_reason", "") not in ("", None):
        raise ValueError(f"safety stop recorded: {scene_id}")
    start_path = repo_file(status.get("run_start_path", ""))
    start_sha = str(status.get("run_start_sha256", "")).lower()
    if expected_start_sha and start_sha != expected_start_sha.lower():
        raise ValueError(f"run_start SHA differs from the independently recorded identity: {scene_id}")
    if expected_start_path and repo_file(expected_start_path).resolve() != start_path.resolve():
        raise ValueError(f"run_start path differs from the independently recorded identity: {scene_id}")
    if not start_sha or sha256(start_path) != start_sha:
        raise ValueError(f"run_start hash mismatch: {scene_id}")
    return status, start_path, start_sha, status_path_binding


def load_run_contract(path: Path) -> dict[str, Any]:
    with h5py.File(path, "r") as f:
        cfg = f["runStart/cfg"] if "runStart/cfg" in f else f["cfg"]
        mode = text_dataset(cfg, "controller_morphology_mode").lower()
        rbf = cfg["rbf/attitude"]
        dmax = np.asarray(rbf["dmax"], dtype=np.float64).reshape(-1)
        beta_rise = float(np.asarray(rbf["beta_rise_time"], dtype=np.float64).reshape(-1)[0])
        identity: dict[str, Any] = {}
        if "runStart/scene_identity" in f:
            ident = f["runStart/scene_identity"]
            for key in ("external_identity_sha256", "source_scene_id"):
                value = optional_text(ident, key)
                if value:
                    identity[key] = value
            if "identity" in ident:
                nested = ident["identity"]
                identity["identity"] = {key: optional_text(nested, key) for key in
                                         ("scene_id", "raw_scene_id", "canonical_scene_id", "payload_review_sha256")
                                         if key in nested}
    if mode != "fixed" or dmax.shape != (3,) or not np.array_equal(dmax, DMAX_EXPECTED) or beta_rise != 2.2:
        raise ValueError(f"unexpected fixed attitude RBF contract in {path}")
    return {"controller_morphology_mode": mode, "dmax_rad_s2": dmax.tolist(), "beta_rise_time_s": beta_rise,
            "run_start_scene_identity": identity}


def read_teacher_raw(raw_path: Path, scene_id: str, status: dict[str, Any], status_path: Path, start_path: Path,
                     split: str, source: str, raw_sha: str, status_sha: str,
                     start_sha: str, audit_status: str) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    contract = load_run_contract(start_path)
    with h5py.File(raw_path, "r") as f:
        if "log" not in f or "scene/arms/command" not in f:
            raise ValueError(f"missing /log or /scene/arms/command: {scene_id}")
        log = f["log"]
        needed = ("time", "transition_time", "state", "filtered_attitude_reference",
                  "attitude_event_flag", "attitude_bs_nominal_torque_Nm", "rbf_output_raw",
                  "rbf_output_unclipped", "attitude_rbf_estimate_acceleration_rads2",
                  "attitude_rbf_compensation_torque_Nm", "rbf_update_flag", "rbf_update_dt")
        missing = [k for k in needed if k not in log]
        if missing:
            raise ValueError(f"missing raw fields for {scene_id}: {missing}")
        time = np.asarray(log["time"], dtype=np.float64).reshape(-1)
        transition_time = np.asarray(log["transition_time"], dtype=np.float64).reshape(-1)
        state = np.asarray(log["state"], dtype=np.float64).T
        ref = np.asarray(log["filtered_attitude_reference"], dtype=np.float64).T
        event_flag = np.asarray(log["attitude_event_flag"]).reshape(-1).astype(bool)
        tau_nom = np.asarray(log["attitude_bs_nominal_torque_Nm"], dtype=np.float64).T
        y_all = np.asarray(log["rbf_output_raw"], dtype=np.float64).T
        y_unclipped = np.asarray(log["rbf_output_unclipped"], dtype=np.float64).T
        y_applied = np.asarray(log["attitude_rbf_estimate_acceleration_rads2"], dtype=np.float64).T
        tau_comp = np.asarray(log["attitude_rbf_compensation_torque_Nm"], dtype=np.float64).T
        rbf_update_flag = np.asarray(log["rbf_update_flag"]).reshape(-1)
        rbf_update_dt = np.asarray(log["rbf_update_dt"], dtype=np.float64).reshape(-1)
        command = np.asarray(f["scene/arms/command"], dtype=np.float64).T
        event_beta = np.asarray(log["attitude_event_beta"], dtype=np.float64).reshape(-1) if "attitude_event_beta" in log else np.full(N_TRANSITIONS, np.nan)
        raw_identity: dict[str, Any] = {}
        if "runIdentity" in f:
            ident = f["runIdentity"]
            for key in ("external_identity_sha256", "scene_id", "candidate"):
                value = optional_text(ident, key)
                if value:
                    raw_identity[key] = value
            if "coordinate_mask" in ident:
                raw_identity["coordinate_mask"] = np.asarray(ident["coordinate_mask"], dtype=np.float64).reshape(-1).tolist()

    if (time.shape != (N_STATES,) or transition_time.shape != (N_TRANSITIONS,)
            or state.shape != (N_STATES, 12) or ref.shape != (N_TRANSITIONS, 3)
            or event_flag.shape != (N_TRANSITIONS,) or tau_nom.shape != (N_TRANSITIONS, 3)
            or y_all.shape != (N_TRANSITIONS, 3) or y_unclipped.shape != (N_TRANSITIONS, 3)
            or y_applied.shape != (N_TRANSITIONS, 3) or tau_comp.shape != (N_TRANSITIONS, 3)
            or rbf_update_flag.shape != (N_TRANSITIONS,) or rbf_update_dt.shape != (N_TRANSITIONS,)
            or command.shape != (N_STATES, 4)):
        raise ValueError(f"unexpected raw dimensions: {scene_id}")
    if not np.array_equal(np.flatnonzero(event_flag), EVENTS):
        raise ValueError(f"event clock differs from locked 100-Hz schedule: {scene_id}")
    update_flag_events = rbf_update_flag[EVENTS]
    update_dt_events = rbf_update_dt[EVENTS]
    if (not np.isfinite(update_flag_events).all() or not np.all(update_flag_events == 1)
            or not np.isfinite(update_dt_events).all() or not np.all(update_dt_events > 0)):
        raise ValueError(f"attitude RBF online update is not enabled at every locked event: {scene_id}")
    if (abs(time[0]) > 1e-12 or abs(time[-1] - 20.0) > 1e-12
            or np.max(np.abs(np.diff(time) - 0.001)) > 1e-12
            or np.max(np.abs(transition_time - time[:-1])) > 1e-12):
        raise ValueError(f"raw timebase mismatch: {scene_id}")

    omega = state[EVENTS, 9:12]
    euler = state[EVENTS, 6:9]
    err = ref[EVENTS] - euler
    err = np.arctan2(np.sin(err), np.cos(err))
    x = np.concatenate((err, omega, tau_nom[EVENTS], command[EVENTS]), axis=1)
    y = y_all[EVENTS]
    if x.shape != (N_EVENTS, 13) or y.shape != (N_EVENTS, 3) or not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError(f"event features/labels malformed or non-finite: {scene_id}")

    raw_clip_err = float(np.max(np.abs(y - np.clip(y_unclipped[EVENTS], -DMAX_EXPECTED, DMAX_EXPECTED))))
    k_matlab = EVENTS.astype(np.float64) + 1.0
    beta_expected = np.minimum(k_matlab * 0.001 / contract["beta_rise_time_s"], 1.0)
    applied_err = float(np.max(np.abs(y_applied[EVENTS] - beta_expected[:, None] * y)))
    tau_expected = y_applied[EVENTS] * J0_DIAGONAL[None, :]
    torque_map_err = float(np.max(np.abs(tau_comp[EVENTS] - tau_expected)))
    beta_log_finite = int(np.isfinite(event_beta[EVENTS]).sum())
    if raw_clip_err > 1e-12 or applied_err > 1e-10 or torque_map_err > 1e-12:
        raise ValueError(f"clip/pre-beta application contract failed: {scene_id}")

    command_trace_sha = hashlib.sha256(np.ascontiguousarray(command).tobytes()).hexdigest()
    if float(np.max(np.abs(command))) > 1.0 + 1e-12:
        raise ValueError(f"normalized morph command is outside [-1,1]: {scene_id}")
    row = {
        "scene_id": scene_id, "split": split, "teacher_source": source,
        "raw_path": str(raw_path), "raw_sha256": raw_sha,
        "status_path": str(status_path.resolve()), "status_sha256": status_sha,
        "status_value": status.get("status"), "status_trace_audit_state": audit_status,
        "run_start_path": str(start_path), "run_start_sha256": start_sha,
        "scene_identity_sha256": status.get("external_identity_sha256", ""),
        "raw_run_identity": raw_identity,
        "run_start_scene_identity": contract["run_start_scene_identity"],
        "source_scene_id": status.get("source_scene_id", scene_id),
        "candidate": status.get("candidate", ""),
        "coordinate_mask": status.get("coordinate_mask", ""),
        "morph_command_trace_sha256": command_trace_sha,
        "morph_command_min": float(command.min()), "morph_command_max": float(command.max()),
        "event_count": int(len(EVENTS)), "event_index_zero_based_first_last": [int(EVENTS[0]), int(EVENTS[-1])],
        "event_index_matlab_first_last": [int(EVENTS[0] + 1), int(EVENTS[-1] + 1)],
        "event_time_s_first_last": [float(time[EVENTS[0]]), float(time[EVENTS[-1]])],
        "feature_shape": list(x.shape), "target_shape": list(y.shape),
        "feature_finite": True, "target_finite": True,
        "rbf_raw_clip_max_abs_error": raw_clip_err,
        "beta_applied_acceleration_max_abs_error_rad_s2": applied_err,
        "fixed_J0_torque_map_max_abs_error_Nm": torque_map_err,
        "attitude_event_beta_logged_finite_events": beta_log_finite,
        "rbf_update_flag_true_event_count": int(np.count_nonzero(update_flag_events == 1)),
        "rbf_update_dt_finite_event_count": int(np.isfinite(update_dt_events).sum()),
        "rbf_update_dt_min_event_s": float(np.min(update_dt_events)),
        "rbf_update_dt_max_event_s": float(np.max(update_dt_events)),
        "transitions": int(status["transitions"]), "state_samples": int(status["state_samples"]),
        **contract,
    }
    return x.astype(np.float32), y.astype(np.float32), row


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="required to read raw files and write dataset artifacts")
    parser.add_argument("--output", type=Path, default=HERE / "matched_teacher_data_v1.npz")
    args = parser.parse_args()
    if not args.execute:
        raise SystemExit("This builder is gated: obtain source-lock review, then pass --execute.")
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output = output.resolve(strict=False)
    try:
        output.relative_to(HERE.resolve())
    except ValueError as exc:
        raise ValueError("output must remain inside mlp15_c5_teacher_redistill_v1") from exc
    manifest_path = output.with_name("DATASET_MANIFEST_v1.json")
    b_audit_path = output.with_name("B24_RAW_TRACE_READONLY_AUDIT_v1.md")
    if output.exists() or manifest_path.exists() or b_audit_path.exists():
        raise FileExistsError("refusing to overwrite an existing dataset/manifest/audit artifact")

    c5_lock_path = repo_file(C5_LOCK_REL)
    c5_batch_path = repo_file(C5_BATCH_REL)
    b_lock_path = repo_file(B_LOCK_REL)
    parent_reuse_summary_path = repo_file(PARENT_REUSE_SUMMARY_REL)
    c5_audit_path = repo_file(C5_TEACHER_AUDIT_REL)
    if sha256(c5_audit_path) != EXPECTED_C5_TEACHER_AUDIT_SHA:
        raise ValueError("C5 raw/J0 audit report SHA mismatch")
    input_hashes = {str(p.relative_to(ROOT)): sha256(p) for p in
                    (c5_lock_path, c5_batch_path, b_lock_path, parent_reuse_summary_path)}
    if (input_hashes[str(C5_LOCK_REL)] != EXPECTED_C5_LOCK_SHA
            or input_hashes[str(C5_BATCH_REL)] != EXPECTED_C5_BATCH_SHA
            or input_hashes[str(B_LOCK_REL)] != EXPECTED_B_LOCK_SHA
            or input_hashes[str(PARENT_REUSE_SUMMARY_REL)] != EXPECTED_PARENT_REUSE_SUMMARY_SHA):
        raise ValueError("frozen input-lock/batch SHA mismatch")
    c5_lock, c5_batch, b_lock = read_json(c5_lock_path), read_json(c5_batch_path), read_json(b_lock_path)
    parent_reuse_summary = read_json(parent_reuse_summary_path)
    if c5_lock.get("schema") != "C5_AXIS_COORDINATE_DEV72_INPUT_LOCK_V3" or c5_lock.get("candidate") != "C5_AXIS_MIXED_COORDINATE_M110":
        raise ValueError("C5 lock is not the frozen M110 candidate")
    if (c5_batch.get("schema") != "C5_AXIS_COORDINATE_DEV72_BATCH_STATUS_V3"
            or c5_batch.get("status") != "COMPLETE_RAW_PENDING_PARENT_AUDIT"
            or c5_batch.get("TEST_accessed") is not False
            or int(c5_batch.get("training_steps", -1)) != 0
            or int(c5_batch.get("optimizer_steps", -1)) != 0):
        raise ValueError("C5 batch is not the expected raw-only, TEST-sealed batch")
    c5_rows = [r for r in c5_lock["scenes"] if r.get("source_split") in ("DEV", "VAL")]
    dev_rows = [r for r in c5_rows if r["source_split"] == "DEV"]
    val_rows = [r for r in c5_rows if r["source_split"] == "VAL"]
    if len(c5_rows) != 72 or len(dev_rows) != 24 or len(val_rows) != 48:
        raise ValueError("C5 lock must resolve exactly DEV24 + VAL48")
    parent_reuse_evidence = validate_reused_scene_parent_audits(
        c5_rows, parent_reuse_summary, parent_reuse_summary_path)
    if b_lock.get("schema") != "B_TRACEABLE_C3CORE_DEV72_INPUT_LOCK_V3":
        raise ValueError("unexpected B72 source-lock schema")
    b_dev_ids = {r.get("scene_id") for r in b_lock.get("scenes", []) if r.get("source_split") == "DEV"}
    if b_dev_ids != {r["scene_id"] for r in dev_rows}:
        raise ValueError("B72 input lock DEV scene IDs differ from the frozen C5 DEV24 list")
    batch_by_id = {r["scene_id"]: r for r in c5_batch["records"]}
    reused_ids = {r["scene_id"] for r in c5_rows if r["C5_reuse"].get("reused") is True}
    new_ids = {r["scene_id"] for r in c5_rows if r["C5_reuse"].get("reused") is not True}
    if len(reused_ids) != 12 or len(new_ids) != 60 or not new_ids.issubset(batch_by_id):
        raise ValueError("C5 source split must resolve 12 reused + 60 batch records")

    def c5_ref(row: dict[str, Any]) -> tuple[Path, Path, str, str, str, str, str]:
        ref = row["C5_reuse"] if row["C5_reuse"].get("reused") is True else batch_by_id[row["scene_id"]]
        raw_path = repo_file(ref["raw_path"])
        status_path = repo_file(ref["run_status_path"])
        return (raw_path, status_path, str(ref["raw_sha256"]).lower(),
                str(ref["run_status_sha256"]).lower(), str(ref["run_start_sha256"]).lower(),
                str(ref["run_start_path"]),
                str(ref.get("parent_screen_status", ref.get("status", ""))))

    b24_x: list[np.ndarray] = []
    b24_y: list[np.ndarray] = []
    c5_train_x: list[np.ndarray] = []
    c5_train_y: list[np.ndarray] = []
    c5_val_x: list[np.ndarray] = []
    c5_val_y: list[np.ndarray] = []
    manifest_rows: list[dict[str, Any]] = []
    b_audit_rows: list[dict[str, Any]] = []

    # Training arm B24 is bound to the exact B72 scoring raws in the C5 scene lock.
    for row in dev_rows:
        sid = row["scene_id"]
        b = row["B72_scoring"]
        if b.get("scene_id") != sid:
            raise ValueError(f"B72 scoring scene mismatch: {sid}")
        raw_path, status_path = repo_file(b["raw_path"]), repo_file(b["run_status_path"])
        raw_sha, status_sha = str(b["raw_sha256"]).lower(), str(b["run_status_sha256"]).lower()
        # B72_scoring has no direct run_start SHA field. Its run_status SHA is
        # frozen in the C5 lock; after pinning that status, its embedded
        # run_start SHA becomes the transitive expected identity.
        b_status_record = read_json(status_path)
        expected_start_sha = str(b_status_record.get("run_start_sha256", "")).lower()
        status, start_path, start_sha, status_path_binding = status_binding(
            raw_path, status_path, raw_sha, status_sha, expected_start_sha,
            str(b_status_record.get("run_start_path", "")), sid)
        expected_external = str(row["external_identity_sha256"]).lower()
        expected_source_scene = status.get("source_scene_id", sid)
        if (str(status.get("external_identity_sha256", "")).lower() != expected_external
                or expected_source_scene not in (sid, sid + "_ACC_FIX_V1")):
            raise ValueError(f"B72 source identity does not map to frozen scene payload: {sid}")
        bx, by, bmeta = read_teacher_raw(raw_path, sid, status, status_path, start_path, "TRAIN_B24", "B72_RBF", raw_sha, status_sha, start_sha, "PENDING_PARENT_AUDIT_STATUS_RETAINED")
        bmeta["scene_identity_sha256"] = expected_external
        bmeta["start_sha_provenance"] = "run_start_sha256 embedded in run_status whose SHA is pinned by C5 B72_scoring"
        bmeta["status_path_binding"] = status_path_binding
        b24_x.append(bx); b24_y.append(by); manifest_rows.append(bmeta); b_audit_rows.append(bmeta)

    # C5-24 and common C5 VAL48 use C5 lock reuse rows or the locked 60-run batch.
    for row in c5_rows:
        sid = row["scene_id"]
        raw_path, status_path, raw_sha, status_sha, expected_start_sha, expected_start_path, audit_state = c5_ref(row)
        status, start_path, start_sha, status_path_binding = status_binding(
            raw_path, status_path, raw_sha, status_sha, expected_start_sha, expected_start_path, sid)
        reuse = row["C5_reuse"].get("reused") is True
        parent_evidence = parent_reuse_evidence.get(sid) if reuse else None
        b72_raw_sha = str(row["B72_scoring"]["raw_sha256"]).lower()
        if "scoring_B72_raw_sha256" in status:
            if str(status["scoring_B72_raw_sha256"]).lower() != b72_raw_sha:
                raise ValueError(f"C5 status is not bound to locked same-scene B72 raw: {sid}")
        elif not parent_evidence:
            raise ValueError(f"C5 status lacks scoring_B72_raw_sha256 without exact parent-audit fallback: {sid}")
        external_identity = str(row["external_identity_sha256"]).lower()
        source_scene_id = str(status.get("source_scene_id", ""))
        if (source_scene_id not in (sid, sid + "_ACC_FIX_V1")
                or status.get("candidate") != "C5_AXIS_MIXED_COORDINATE_M110"
                or list(status.get("coordinate_mask", [])) != [1, 1, 0]):
            raise ValueError(f"C5 status scene/candidate/mask identity mismatch: {sid}")
        if ("external_identity_sha256" in status
                and str(status["external_identity_sha256"]).lower() != external_identity):
            raise ValueError(f"C5 status external identity mismatch: {sid}")
        split = "TRAIN_C5_24" if row["source_split"] == "DEV" else "C5_VAL48"
        cx, cy, cmeta = read_teacher_raw(raw_path, sid, status, status_path, start_path, split, "C5_RBF", raw_sha, status_sha, start_sha, audit_state)
        b_match = next((r for r in b_audit_rows if r["scene_id"] == sid), None)
        if reuse:
            if "scene_identity" in status:
                scene_identity = status["scene_identity"]
                scene_b_path = str(scene_identity.get("B_raw_path", "")) if isinstance(scene_identity, dict) else ""
                if (not isinstance(scene_identity, dict)
                        or scene_identity.get("canonical_scene_id") != sid
                        or scene_identity.get("raw_scene_id") not in (sid, sid + "_ACC_FIX_V1")
                        or str(scene_identity.get("B_raw_sha256", "")).lower() != str(row["B_source"]["sha256"]).lower()
                        or not same_absolute_path_string(scene_b_path, row["B_source"]["path"])
                        or len(str(scene_identity.get("payload_review_sha256", ""))) != 64):
                    raise ValueError(f"C5 reuse status.scene_identity mismatch despite parent audit: {sid}")
                identity_binding = "status.scene_identity verified; parent summary independently binds C5/B72 raw hashes and external identities"
            elif parent_evidence:
                identity_binding = "missing status.scene_identity/scoring_B72_raw_sha256; exact locked parent summary binds C5/B72 raw hashes, both external identities, and PASS status"
            else:
                raise ValueError(f"C5 reuse lacks status.scene_identity without exact parent-audit fallback: {sid}")
        else:
            raw_ext = str(cmeta.get("raw_run_identity", {}).get("external_identity_sha256", "")).lower()
            start_ext = str(cmeta.get("run_start_scene_identity", {}).get("external_identity_sha256", "")).lower()
            if raw_ext != external_identity or start_ext != external_identity:
                raise ValueError(f"C5 fresh raw/run_start external identity differs from frozen lock: {sid}")
            identity_binding = "raw.runIdentity and run_start.scene_identity external SHA both equal C5 lock; status has no top-level external identity"
        # Bind C5's recorded identity to its same-scene B72 status. C5 status
        # lacks a top-level external_identity_sha256 in this cohort.
        b72 = row["B72_scoring"]
        b72_status_path = repo_file(b72["run_status_path"])
        if sha256(b72_status_path) != str(b72["run_status_sha256"]).lower():
            raise ValueError(f"same-scene B72 status SHA mismatch while checking C5 identity: {sid}")
        b72_status = read_json(b72_status_path)
        if (b72_status.get("scene_id") != sid
                or str(b72_status.get("external_identity_sha256", "")).lower() != external_identity
                or str(b72_status.get("raw_sha256", "")).lower() != str(b72["raw_sha256"]).lower()):
            raise ValueError(f"same-scene B72 status external identity/raw binding mismatch: {sid}")
        if row["source_split"] == "DEV":
            if b_match is None or b_match["source_scene_id"] != source_scene_id:
                raise ValueError(f"B/C5 source_scene_id mismatch for matched DEV scene: {sid}")
            if b_match["scene_identity_sha256"].lower() != external_identity:
                raise ValueError(f"B/C5 external payload identity mismatch: {sid}")
            if b_match["morph_command_trace_sha256"] != cmeta["morph_command_trace_sha256"]:
                raise ValueError(f"B/C5 arms.command traces differ for matched DEV scene: {sid}")
        cmeta["identity_binding"] = identity_binding
        cmeta["status_path_binding"] = status_path_binding
        cmeta["start_sha_provenance"] = "run_start SHA/path cross-checked against frozen C5 reuse/batch record"
        cmeta["scene_identity_sha256"] = external_identity
        cmeta["same_scene_B72_status_path"] = str(b72_status_path)
        cmeta["same_scene_B72_status_sha256"] = str(b72["run_status_sha256"]).lower()
        cmeta["same_scene_B72_external_identity_sha256"] = str(b72_status["external_identity_sha256"]).lower()
        if reuse:
            cmeta["parent_screen_status"] = row["C5_reuse"].get("parent_screen_status")
            cmeta["parent_screen_event_count_metadata"] = int(row["C5_reuse"].get("parent_screen_event_count", 0))
            cmeta["parent_reuse_audit_evidence"] = parent_evidence
        manifest_rows.append(cmeta)
        if row["source_split"] == "DEV":
            c5_train_x.append(cx); c5_train_y.append(cy)
        else:
            c5_val_x.append(cx); c5_val_y.append(cy)

    arrays = {
        "b24_x": np.stack(b24_x), "b24_y": np.stack(b24_y),
        "c5_train_x": np.stack(c5_train_x), "c5_train_y": np.stack(c5_train_y),
        "c5_val_x": np.stack(c5_val_x), "c5_val_y": np.stack(c5_val_y),
        "b24_scene_ids": np.asarray([r["scene_id"] for r in dev_rows], dtype=np.str_),
        "c5_train_scene_ids": np.asarray([r["scene_id"] for r in dev_rows], dtype=np.str_),
        "c5_val_scene_ids": np.asarray([r["scene_id"] for r in val_rows], dtype=np.str_),
    }
    expected_shapes = {
        "b24_x": (24, N_EVENTS, 13), "b24_y": (24, N_EVENTS, 3),
        "c5_train_x": (24, N_EVENTS, 13), "c5_train_y": (24, N_EVENTS, 3),
        "c5_val_x": (48, N_EVENTS, 13), "c5_val_y": (48, N_EVENTS, 3),
    }
    for key, shape in expected_shapes.items():
        if arrays[key].shape != shape or not np.isfinite(arrays[key]).all():
            raise ValueError(f"dataset array shape/finiteness failure: {key} {arrays[key].shape}")
    for key, expected_n in (("b24_scene_ids", 24), ("c5_train_scene_ids", 24), ("c5_val_scene_ids", 48)):
        if arrays[key].shape != (expected_n,) or len(set(arrays[key].tolist())) != expected_n:
            raise ValueError(f"dataset scene identity array malformed: {key}")
    if [r["scene_id"] for r in manifest_rows if r["split"] == "TRAIN_B24"] != [r["scene_id"] for r in dev_rows]:
        raise ValueError("B24 scene ordering differs from frozen C5 DEV list")
    if [r["scene_id"] for r in manifest_rows if r["split"] == "TRAIN_C5_24"] != arrays["c5_train_scene_ids"].tolist():
        raise ValueError("C5-24 NPZ scene ID order differs from manifest rows")
    if [r["scene_id"] for r in manifest_rows if r["split"] == "C5_VAL48"] != arrays["c5_val_scene_ids"].tolist():
        raise ValueError("C5 VAL48 NPZ scene ID order differs from manifest rows")

    output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(output, **arrays)
    manifest = {
        "schema": "DL1018_MLP15_MATCHED_B24_C5_24_C5_VAL48_DATASET_V1",
        "status": "PASS_OFFLINE_EXTRACTION",
        "dataset_path": str(output.relative_to(ROOT)), "dataset_sha256": sha256(output),
        "dataset_bytes": output.stat().st_size,
        "input_locks": input_hashes,
        "parent_reuse_audit": {
            "path": str(PARENT_REUSE_SUMMARY_REL), "sha256": EXPECTED_PARENT_REUSE_SUMMARY_SHA,
            "status": parent_reuse_summary["status"], "scene_count": len(parent_reuse_evidence),
            "TEST_accessed": parent_reuse_summary["TEST_accessed"],
            "training": int(parent_reuse_summary["training"]),
            "new_Plant_in_audit": int(parent_reuse_summary["new_Plant_in_audit"]),
            "B_identity_status": parent_reuse_summary["B_identity_status"],
            "missing_status_field_exception": (
                "Only C5_reuse=true rows may use exact per-scene parent evidence when legacy C5 status lacks "
                "scoring_B72_raw_sha256 and/or scene_identity. Any present field remains strictly checked."
            ),
        },
        "splits": {k: {"scenes": int(v.shape[0]), "events_per_scene": int(v.shape[1]), "x_shape": list(v.shape), "y_shape": list(arrays[k.replace("_x", "_y")].shape) if k.endswith("_x") else None,
                        "scene_id_array": {"b24_x": "b24_scene_ids", "c5_train_x": "c5_train_scene_ids", "c5_val_x": "c5_val_scene_ids"}[k]}
                    for k, v in arrays.items() if k.endswith("_x")},
        "feature_order": FEATURE_ORDER,
        "feature_units": ["rad x3", "rad/s x3", "N*m x3", "dimensionless normalized morph command x4"],
        "morph_command_definition": "command = rhoDot / morph_speed_mps; dimensionless normalized morphology velocity in [-1,1]",
        "morph_command_source": {"path": str(MORPH_SOURCE_REL), "sha256": sha256(repo_file(MORPH_SOURCE_REL))},
        "fixed_J0_reference": {"diagonal_kg_m2": J0_DIAGONAL.tolist(),
                                "source_audit_path": str(C5_TEACHER_AUDIT_REL),
                                "source_audit_sha256": sha256(c5_audit_path),
                                "B_run_start_mode_required": "fixed",
                                "torque_mapping": "attitude_rbf_compensation_torque_Nm = J0 * attitude_rbf_estimate_acceleration_rads2"},
        "target": "logged rbf_output_raw at attitude event k; post-dmax/pre-beta; rad/s^2",
        "event_schedule": {"event_count": N_EVENTS, "zero_based_transition_indices_first_last": [10, 19990],
                           "matlab_transition_indices_first_last": [11, 19991], "event_stride_transitions": 10,
                           "dt_s": 0.001, "event_time_s_first_last": [0.01, 19.99]},
        "window_contract": {"events": 15, "causal": True, "scene_boundary_reset": True,
                             "first_14_history": "zero after TRAIN-only feature normalization", "flatten_order": "event-major/feature-minor"},
        "plant_truth_read": False, "inertia_config_read": False, "TEST_accessed": False,
        "old_raw_status_model_modified": False, "rows": manifest_rows,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    md = [
        "# B24 raw trace read-only audit",
        "",
        "Scope: the 24 B72 scoring raws on the frozen C5 DEV24 scene list. This is an offline extraction gate, not a retroactive parent audit; historical B run_status values remain unchanged.",
        "",
        f"- C5 lock SHA-256: `{input_hashes[str(C5_LOCK_REL)]}`",
        f"- B lock SHA-256: `{input_hashes[str(B_LOCK_REL)]}`",
        f"- Dataset SHA-256: `{sha256(output)}`",
        "- Raw/status/run_start identities: checked against frozen C5 lock or status binding.",
        "- Event contract: 1,999 extracted events per scene, indices 10..19,990 (0-based transition), 13 finite causal features, 3 finite post-dmax/pre-beta labels. For the 12 reused C5 rows, `parent_screen_event_count` is retained as prior-screen metadata and is not substituted for the current raw event count.",
        "- Online-update contract: `/log/rbf_update_flag` must be true on all 1,999 attitude events; `/log/rbf_update_dt` must be finite and positive on all events. The audit does not infer update enablement from run_start fields.",
        "- Beta field caveat: explicit event beta is inspected and reported per scene; applied beta is verified from the logged applied acceleration and run_start 2.2 s rise time.",
        f"- Fixed-inertia torque closure: use C5 audit J0 diagonal `{J0_DIAGONAL.tolist()}` kg·m²; all B run_start modes must be `fixed`, then compare J0 × logged applied acceleration with logged compensation torque eventwise.",
        "- No Plant, training, TEST reads, or historical artifact writes.",
        "",
        "| Scene | B status | Raw SHA | Status SHA | run_start SHA | events | update flags true | update dt min/max s | feature/target | max clip err | max beta-apply err | max J0→Nm err | beta finite events |",
        "|---|---|---|---|---|---:|---:|---|---|---:|---:|---:|---:|",
    ]
    for r in b_audit_rows:
        md.append(f"| {r['scene_id']} | {r['status_value']} | `{r['raw_sha256']}` | `{r['status_sha256']}` | `{r['run_start_sha256']}` | {r['event_count']} | {r['rbf_update_flag_true_event_count']}/{r['event_count']} | {r['rbf_update_dt_min_event_s']:.6g}/{r['rbf_update_dt_max_event_s']:.6g} | {r['feature_shape']}/{r['target_shape']} | {r['rbf_raw_clip_max_abs_error']:.3g} | {r['beta_applied_acceleration_max_abs_error_rad_s2']:.3g} | {r['fixed_J0_torque_map_max_abs_error_Nm']:.3g} | {r['attitude_event_beta_logged_finite_events']} |")
    b_audit_path.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps({"status": manifest["status"], "dataset": str(output), "dataset_sha256": manifest["dataset_sha256"],
                      "manifest": str(manifest_path), "b24_audit": str(b_audit_path),
                      "shapes": {k: list(v.shape) for k, v in arrays.items()},
                      "plant_calls": 0, "training_steps": 0, "TEST_accessed": False}, indent=2))


if __name__ == "__main__":
    main()
