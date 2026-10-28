from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

import h5py
import numpy as np


ROOT = Path(__file__).resolve().parents[5]
ENTRY = ROOT / "experiments/attitude_physics_inertia_observer_20261025/paired_runner/morph_dev2_dev72_v1"
REVIEW = ENTRY / "review"
C5_LOCK = ROOT / "experiments/position_axis_coordinate_c5_dev72_20261023/C5_DEV72_INPUT_LOCK_v3.json"
B_LOCK = ROOT / "experiments/b_traceable_c3core_dev72_20261023/B_TRACEABLE_DEV72_INPUT_LOCK_v3.json"
DEV58_MANIFEST = ENTRY / "manifest/DEV58_PREPARED_MANIFEST_B72_V2.json"
SOURCE_LOCK = ENTRY / "SOURCE_LOCK_MORPH_DEV2_DEV58_V2_FROZEN.json"
ROOT_RELEASE = ENTRY / "ROOT_RELEASE_MORPH_DEV2_DEV58_v2.json"
SCREEN_MANIFEST = ROOT / "experiments/attitude_physics_inertia_observer_20261025/paired_runner/morph_dev2_screen12_v1/manifest/SCREEN12_PREPARED_MANIFEST.json"
SCREEN_REVIEW = REVIEW / "SCREEN12_CANDIDATE_VS_B_RAW.json"
T2_REVIEW = REVIEW / "PRIOR_T2_RAW_REUSE_REVIEW_V2.json"
T3_REVIEW = REVIEW / "PRIOR_T3_RAW_REUSE_REVIEW.json"

C5_LOCK_SHA256 = "82024c01276cc4bfbd9b7772cf5332dee3fdfcbed422969589b68f1c90ed2d75"
B_LOCK_SHA256 = "8d738e5c70ba2fc8697550549d1a0537f08eadb49b99bc5684e5c26f6222f452"
DEV58_MANIFEST_SHA256 = "4ce70de0d846a9c26a46b545b610a246eac1141499de926ada5014b3f4257904"
SCREEN_MANIFEST_SHA256 = "322957f7e446dd6a58607f70e0be379d98ad5ed6ae8b3e772fc42f10ea056fba"
SOURCE_LOCK_SHA256 = "e5f7df898ee9db506d920b6ee43707c6ea86fc5bb408e54b67ae27b82fe14a69"
ROOT_RELEASE_SHA256 = "d82a1b8f9cc72f32fab97ff1f4a6eae9bc9bcaa38f3c7282008d0b96ad920844"
ATTEMPT_ID = "DEV58_PHYATT_B72_20261025_A02"
N = 20_000
TASK_BY_T = {"T1": "HELIX", "T2": "FIG8_3D", "T3": "SQUARE"}
INPUT_PATHS = (
    "time",
    "transition_time",
    "initial_state",
    "environment_wind_I",
    "arms/command",
    "reference/position",
    "reference/velocity",
    "reference/acceleration",
    "reference/yaw",
    "reference/yaw_rate",
    "reference/yaw_acceleration",
    "arms/rho_true",
    "arms/rho_hat",
    "arms/rhoDot_true",
    "arms/rhoDot_hat",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def require_sha(path: Path, expected: str, label: str) -> str:
    actual = sha256_file(path)
    if actual.lower() != expected.lower():
        raise ValueError(f"{label} SHA-256 mismatch: {path} expected={expected} actual={actual}")
    return actual


def same_path(a: str | Path, b: str | Path) -> bool:
    return os.path.normcase(str(Path(a).resolve())) == os.path.normcase(str(Path(b).resolve()))


def gate_value(status: dict[str, Any], key: str) -> bool | None:
    value = status.get(key)
    if isinstance(value, dict):
        value = value.get("passed")
    return value if isinstance(value, bool) else None


def scene_tokens(scene_id: str) -> tuple[str, int, str]:
    match = re.fullmatch(r"DL1018_(?:DEV|VAL)_(T[123])_C\d{2}_W(\d{2})", scene_id)
    if not match:
        raise ValueError(f"Unexpected fixed-scene ID: {scene_id}")
    task_id, wind = match.groups()
    return TASK_BY_T[task_id], int(wind), task_id


def _read_reuse_review_refs(reused: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    screen_report = read_json(SCREEN_REVIEW)
    t2_report = read_json(T2_REVIEW)
    t3_report = read_json(T3_REVIEW)
    reports = {"screen12": screen_report, "T2": t2_report, "T3": t3_report}
    screen_rows = {x["scene_id"]: x for x in screen_report["pairs"]}
    expected_ids = set(screen_rows) | {t2_report["scene_id"], t3_report["scene_id"]}
    by_id: dict[str, dict[str, Any]] = {}
    for item in reused:
        sid = item["scene_id"]
        if sid in screen_rows:
            source = "screen12"
            expected_raw = screen_rows[sid]["candidate_raw_sha256"]
            expected_review = SCREEN_REVIEW
        elif sid == t2_report["scene_id"]:
            source = "T2"
            expected_raw = t2_report["candidate_source_raw_sha256"]
            expected_review = T2_REVIEW
        elif sid == t3_report["scene_id"]:
            source = "T3"
            expected_raw = t3_report["candidate_raw_sha256"]
            expected_review = T3_REVIEW
        else:
            raise ValueError(f"Unexpected reused candidate scene: {sid}")
        if sid in by_id or item["raw_sha256"].lower() != expected_raw.lower():
            raise ValueError(f"Reused candidate SHA/uniqueness mismatch: {sid}")
        if not same_path(item["review_path"], expected_review):
            raise ValueError(f"Reused candidate points to unexpected review: {sid}")
        require_sha(expected_review, item["review_sha256"], f"{sid} review")
        by_id[sid] = {**item, "provenance": source}
    if set(by_id) != expected_ids or len(by_id) != 14:
        raise ValueError("Expected exactly screen12's 12 plus T2/T3's 2 reused candidate raws")
    return by_id, reports


def load_context() -> dict[str, Any]:
    require_sha(C5_LOCK, C5_LOCK_SHA256, "C5 DEV72 lock")
    require_sha(B_LOCK, B_LOCK_SHA256, "B traceable DEV72 lock")
    require_sha(DEV58_MANIFEST, DEV58_MANIFEST_SHA256, "DEV58 B72 manifest")
    require_sha(SCREEN_MANIFEST, SCREEN_MANIFEST_SHA256, "screen12 manifest")
    require_sha(SOURCE_LOCK, SOURCE_LOCK_SHA256, "frozen DEV58 V2 source lock")
    require_sha(ROOT_RELEASE, ROOT_RELEASE_SHA256, "DEV58 V2 root release")
    c5 = read_json(C5_LOCK)
    manifest = read_json(DEV58_MANIFEST)
    screen_manifest = read_json(SCREEN_MANIFEST)
    source_lock = read_json(SOURCE_LOCK)
    release = read_json(ROOT_RELEASE)
    if c5.get("schema") != "C5_AXIS_COORDINATE_DEV72_INPUT_LOCK_V3" or len(c5.get("scene_ids_all_72", [])) != 72:
        raise ValueError("C5 lock schema or fixed 72-scene list differs")
    if c5.get("b72_input_lock_sha256", "").lower() != B_LOCK_SHA256:
        raise ValueError("C5 lock does not bind the expected B72 source lock")
    if manifest.get("schema") != "MORPH_DEV2_DEV58_PREPARED_MANIFEST_V1" or len(manifest.get("scenes", [])) != 58:
        raise ValueError("DEV58 prepared manifest schema/count differs")
    if not manifest.get("b_comparator", {}).get("all_72_B_raw_reused", False):
        raise ValueError("DEV58 manifest does not identify the locked B72 comparator")
    if source_lock.get("schema") != "SOURCE_LOCK_MORPH_DEV2_DEV58_V1":
        raise ValueError("Unexpected candidate source-lock schema")
    if not (
        source_lock.get("status") == "FROZEN_INPUTS"
        and source_lock.get("root_release_issued") is True
        and source_lock.get("executed") is False
        and release.get("approved") is True
        and release.get("attempt_id") == ATTEMPT_ID
        and release.get("source_lock_sha256", "").lower() == SOURCE_LOCK_SHA256
        and same_path(release.get("source_lock_path", ""), SOURCE_LOCK)
        and int(release.get("max_runner_calls", -1)) == 58
        and release.get("comparator") == "B_TRACEABLE_C3CORE_V1"
    ):
        raise ValueError("Frozen V2 DEV58 lock/release identity differs")
    wrapper = source_lock.get("wrapper", {})
    if not wrapper.get("path") or not wrapper.get("sha256"):
        raise ValueError("Frozen V2 source lock is missing its runner identity")
    require_sha(Path(wrapper["path"]), wrapper["sha256"], "frozen DEV58 MATLAB runner")
    c5_ids = list(c5["scene_ids_all_72"])
    c5_rows = {x["scene_id"]: x for x in c5["scenes"]}
    if len(c5_rows) != 72 or set(c5_rows) != set(c5_ids):
        raise ValueError("C5 locked scene records do not match its 72-ID list")
    reused, reports = _read_reuse_review_refs(source_lock.get("reused_candidate_raws", []))
    new_rows = {x["scene_id"]: x for x in manifest["scenes"]}
    screen_rows = {x["scene_id"]: x for x in screen_manifest["scenes"]}
    if len(new_rows) != 58 or len(screen_rows) != 12 or len(new_rows) + len(reused) != 72:
        raise ValueError("Candidate scene manifest/reuse cardinalities differ")
    if set(new_rows) & set(reused) or set(new_rows) | set(reused) != set(c5_ids):
        raise ValueError("The 58 new plus 14 reused candidate scenes are not the locked DEV72 set")
    expected_new_order = [sid for sid in c5_ids if sid not in reused]
    if list(new_rows) != expected_new_order:
        raise ValueError("DEV58 manifest no longer preserves the C5 locked scene order")
    for sid, row in {**new_rows, **screen_rows}.items():
        task, wind, _ = scene_tokens(sid)
        if row.get("task") != task or int(row.get("wind_id", -1)) != wind:
            raise ValueError(f"Task/wind metadata mismatch for {sid}")
    for sid, row in new_rows.items():
        if row["external_identity_sha256"].lower() != c5_rows[sid]["external_identity_sha256"].lower():
            raise ValueError(f"DEV58 external identity differs from C5 lock for {sid}")
    return {
        "c5": c5,
        "manifest": manifest,
        "screen_manifest": screen_manifest,
        "source_lock": source_lock,
        "release": release,
        "wrapper_sha256": str(wrapper["sha256"]).lower(),
        "c5_ids": c5_ids,
        "c5_rows": c5_rows,
        "new_rows": new_rows,
        "screen_rows": screen_rows,
        "reused": reused,
        "reports": reports,
        "source_lock_sha256": sha256_file(SOURCE_LOCK),
    }


def matlab_text(log: h5py.Group, key: str) -> str:
    values = np.asarray(log[key][()])
    if values.dtype.kind in "ui" and values.dtype.itemsize <= 2:
        return "".join(chr(int(x)) for x in values.reshape(-1) if int(x))
    if values.dtype.kind in "SU":
        return "".join(x.decode("utf-8", errors="replace") if isinstance(x, bytes) else str(x) for x in values.reshape(-1)).rstrip("\x00")
    if np.issubdtype(values.dtype, np.number) and not np.any(values):
        # MATLAB v7.3 writes this empty char field as two zero uint64 values.
        return ""
    raise ValueError(f"Unsupported MATLAB text encoding in log.{key}: {values.dtype} {values.shape}")


def rot_zyx_batch(euler_xyz: np.ndarray) -> np.ndarray:
    r, p, y = euler_xyz.T
    cr, sr = np.cos(r), np.sin(r)
    cp, sp = np.cos(p), np.sin(p)
    cy, sy = np.cos(y), np.sin(y)
    out = np.empty((len(r), 3, 3), dtype=np.float64)
    out[:, 0, 0] = cy * cp
    out[:, 0, 1] = cy * sp * sr - sy * cr
    out[:, 0, 2] = cy * sp * cr + sy * sr
    out[:, 1, 0] = sy * cp
    out[:, 1, 1] = sy * sp * sr + cy * cr
    out[:, 1, 2] = sy * sp * cr - cy * sr
    out[:, 2, 0] = -sp
    out[:, 2, 1] = cp * sr
    out[:, 2, 2] = cp * cr
    return out


def transition_count(flags: np.ndarray, n: int, name: str) -> int:
    a = np.asarray(flags)
    if a.ndim == 1 and a.size == n:
        per_step = a
    elif a.ndim >= 2 and a.shape[-1] == n:
        per_step = np.any(a != 0, axis=tuple(range(a.ndim - 1)))
    elif a.ndim >= 2 and a.shape[0] == n:
        per_step = np.any(a != 0, axis=tuple(range(1, a.ndim)))
    else:
        raise ValueError(f"{name} does not contain one flag vector per transition: {a.shape}")
    return int(np.count_nonzero(per_step))


def score_raw(path: Path) -> tuple[dict[str, Any], dict[str, np.ndarray], dict[str, Any]]:
    with h5py.File(path, "r") as mat:
        log = mat["log"]
        time = np.asarray(log["time"][()], dtype=np.float64).reshape(-1)
        transition_time = np.asarray(log["transition_time"][()], dtype=np.float64).reshape(-1)
        state = np.asarray(log["state"][()], dtype=np.float64)
        reference = log["reference"]
        position = np.asarray(reference["position"][()], dtype=np.float64)
        filtered_attitude = np.asarray(log["filtered_attitude_reference"][()], dtype=np.float64)
        controller_time = np.asarray(log["controller_call_time_s"][()], dtype=np.float64).reshape(-1)
        if state.shape != (12, N + 1) or position.shape != (3, N + 1) or filtered_attitude.shape != (3, N):
            raise ValueError(f"Unexpected full-run array shape in {path}: state={state.shape}, position={position.shape}, attitude_ref={filtered_attitude.shape}")
        if time.shape != (N + 1,) or transition_time.shape != (N,):
            raise ValueError(f"Unexpected full-run time shape in {path}")
        inputs: dict[str, np.ndarray] = {}
        for item in INPUT_PATHS:
            node: Any = log
            for part in item.split("/"):
                node = node[part]
            inputs[item] = np.asarray(node[()], dtype=np.float64)
        finite = all(np.all(np.isfinite(x)) for x in (time, transition_time, state, position, filtered_attitude, controller_time, *inputs.values()))
        if not finite or not np.all(np.diff(time) > 0) or not np.all(np.diff(transition_time) > 0):
            raise ValueError(f"Non-finite or non-monotonic scoring/input arrays in {path}")
        if controller_time.shape != (N,) or not np.allclose(transition_time, time[:-1], atol=1e-12, rtol=0):
            raise ValueError(f"Unexpected controller timing shape or transition_time in {path}")
        e = (state[:3, :] - position).T
        position_error_norm = np.linalg.norm(e, axis=1)
        early_state, late_state = time < 2.2, time >= 2.2
        early_transition, late_transition = transition_time < 2.2, transition_time >= 2.2
        if (np.count_nonzero(early_state), np.count_nonzero(late_state),
                np.count_nonzero(early_transition), np.count_nonzero(late_transition)) != (2200, 17801, 2200, 17800):
            raise ValueError(f"Unexpected frozen 2.2-second split in {path}")
        q = float(np.sqrt(np.mean(np.sum(e * e, axis=1))))
        actual = rot_zyx_batch(state[6:9, :N].T)
        desired = rot_zyx_batch(filtered_attitude.T)
        relative = np.einsum("nji,njk->nik", desired, actual)
        cosine = np.clip((np.trace(relative, axis1=1, axis2=2) - 1.0) * 0.5, -1.0, 1.0)
        skew = np.stack(
            (relative[:, 2, 1] - relative[:, 1, 2],
             relative[:, 0, 2] - relative[:, 2, 0],
             relative[:, 1, 0] - relative[:, 0, 1]),
            axis=1,
        )
        sine = 0.5 * np.linalg.norm(skew, axis=1)
        theta = np.arctan2(sine, cosine)
        theta_p95 = float(np.percentile(theta, 95))
        motor = np.asarray(log["motor_saturated"][()])
        clipped = np.asarray(log["generalized_clipped"][()])
        tilt = np.asarray(log["tilt_limited"][()])
        raw_status = matlab_text(log, "status")
        raw_stop = matlab_text(log, "safety_stop_reason")
        last_transition = float(np.asarray(log["last_transition"][()], dtype=np.float64).reshape(-1)[0])
        metrics = {
            "q_rmse_m": q,
            "q_axis_rmse_m": np.sqrt(np.mean(e * e, axis=0)).tolist(),
            "q_early_rmse_m": float(np.sqrt(np.mean(np.sum(e[early_state] * e[early_state], axis=1)))),
            "q_early_axis_rmse_m": np.sqrt(np.mean(e[early_state] * e[early_state], axis=0)).tolist(),
            "q_early_peak_m": float(np.max(position_error_norm[early_state])),
            "q_late_rmse_m": float(np.sqrt(np.mean(np.sum(e[late_state] * e[late_state], axis=1)))),
            "q_late_axis_rmse_m": np.sqrt(np.mean(e[late_state] * e[late_state], axis=0)).tolist(),
            "q_late_peak_m": float(np.max(position_error_norm[late_state])),
            "q_peak_m": float(np.max(position_error_norm)),
            "q_p95_m": float(np.percentile(position_error_norm, 95)),
            "so3_rmse_rad": float(np.sqrt(np.mean(theta * theta))),
            "so3_peak_rad": float(np.max(theta)),
            "so3_early_rmse_rad": float(np.sqrt(np.mean(theta[early_transition] ** 2))),
            "so3_early_peak_rad": float(np.max(theta[early_transition])),
            "so3_late_rmse_rad": float(np.sqrt(np.mean(theta[late_transition] ** 2))),
            "so3_late_peak_rad": float(np.max(theta[late_transition])),
            "so3_p95_rad": theta_p95,
            "controller_call_time_s_mean": float(np.mean(controller_time)),
            "controller_call_time_s_p95": float(np.percentile(controller_time, 95)),
            "controller_call_time_excludes_candidate_post_allocator_commit": True,
            "motor_saturation_count": transition_count(motor, N, "motor_saturated"),
            "generalized_clip_count": transition_count(clipped, N, "generalized_clipped"),
            "tilt_limited_count": int(np.count_nonzero(tilt)),
            "state_points": int(state.shape[1]),
            "transitions": int(transition_time.size),
        }
        evidence = {
            "raw_log_status": raw_status,
            "raw_safety_stop_reason": raw_stop,
            "raw_last_transition": last_transition,
            "numeric_arrays_finite": finite,
        }
    return metrics, inputs, evidence


def compare_scene_inputs(candidate: dict[str, np.ndarray], baseline: dict[str, np.ndarray], scene_id: str) -> None:
    for name in INPUT_PATHS:
        if candidate[name].shape != baseline[name].shape or not np.array_equal(candidate[name], baseline[name]):
            raise ValueError(f"Candidate and locked B72 scene input differs at {scene_id}: {name}")


def commanded_morphing_arms(command: np.ndarray) -> int:
    command = np.asarray(command, dtype=np.float64)
    if command.ndim == 2 and command.shape[0] == 4 and command.shape[1] in (N, N + 1):
        per_arm = np.max(np.abs(command), axis=1)
    elif command.ndim == 2 and command.shape[1] == 4 and command.shape[0] in (N, N + 1):
        per_arm = np.max(np.abs(command), axis=0)
    else:
        raise ValueError(f"Unexpected 4-arm command array shape: {command.shape}")
    return int(np.count_nonzero(per_arm > 1e-12))


def validate_baseline(ctx: dict[str, Any], sid: str, lock_row: dict[str, Any]) -> tuple[Path, Path, dict[str, Any], str, str]:
    b = lock_row["B72_scoring"]
    if b.get("scene_id") != sid or int(b.get("plant_calls", -1)) != 1:
        raise ValueError(f"C5 B72 row identity mismatch for {sid}")
    raw = Path(b["raw_path"])
    status_path = Path(b["run_status_path"])
    raw_sha = require_sha(raw, b["raw_sha256"], f"{sid} locked B72 raw")
    status_sha = require_sha(status_path, b["run_status_sha256"], f"{sid} locked B72 status")
    status = read_json(status_path)
    expected_external = lock_row["external_identity_sha256"]
    if not (
        status.get("scene_id") == sid
        and status.get("status") == "RUN_COMPLETE_RAW_PENDING_AUDIT"
        and status.get("log_status") == "STABLE"
        and status.get("safety_stop_reason", "") == ""
        and int(status.get("last_transition", -1)) == N
        and int(status.get("transitions", -1)) == N
        and int(status.get("state_samples", -1)) == N + 1
        and int(status.get("plant_calls", -1)) == 1
        and not bool(status.get("TEST_accessed", True))
        and status.get("raw_sha256", "").lower() == raw_sha.lower()
        and status.get("external_identity_sha256") == expected_external
        and status.get("scene_raw_sha256") == lock_row["B_source"]["sha256"]
    ):
        raise ValueError(f"Locked B72 status contract mismatch for {sid}")
    if status.get("raw_path") and not same_path(status["raw_path"], raw):
        raise ValueError(f"Locked B72 status raw_path mismatch for {sid}")
    return raw, status_path, status, raw_sha, status_sha


def candidate_reference(ctx: dict[str, Any], sid: str, attempt_dir: Path | None) -> tuple[Path, Path, dict[str, Any], dict[str, Any], str]:
    if sid in ctx["reused"]:
        ref = ctx["reused"][sid]
        raw, status_path = Path(ref["raw_path"]), Path(ref["status_path"])
        expected_raw_sha = ref["raw_sha256"]
        provenance = ref["provenance"]
        expected_status_sha = ref["status_sha256"]
        status_sha = require_sha(status_path, expected_status_sha, f"{sid} reused candidate status")
        raw_sha = require_sha(raw, expected_raw_sha, f"{sid} reused candidate raw")
    else:
        if attempt_dir is None:
            raise ValueError("--attempt-dir is required to score all 72 candidate/B pairs")
        index = list(ctx["new_rows"]).index(sid) + 1
        run_dir = attempt_dir / f"{index:02d}_{sid}_candidate"
        raw, status_path = run_dir / "run_raw.mat", run_dir / "run_status.json"
        if not raw.is_file() or not status_path.is_file():
            raise FileNotFoundError(f"Missing generated candidate raw/status for {sid}: {run_dir}")
        status_sha = sha256_file(status_path)
        status = read_json(status_path)
        raw_sha = require_sha(raw, status.get("raw_sha256", ""), f"{sid} new candidate raw")
        provenance = "new_DEV58"
        expected_status_sha = status_sha
    status = read_json(status_path)
    if status.get("scene_id") != sid or status.get("arm") != "candidate" or int(status.get("last_transition", -1)) != N:
        raise ValueError(f"Candidate status scene/arm/transition mismatch for {sid}")
    if provenance == "new_DEV58" and not (
        status.get("status") == "COMPLETED_DEV58_CANDIDATE"
        and status.get("runner_status") == "STABLE"
        and status.get("safety_stop_reason", "") == ""
        and gate_value(status, "engineering_gate") is True
        and gate_value(status, "safety_gate") is True
    ):
        raise ValueError(f"New DEV58 candidate status/safety gate failed for {sid}")
    return raw, status_path, status, {"provenance": provenance, "raw_sha256": raw_sha, "status_sha256": status_sha}, provenance


def historical_expectation(ctx: dict[str, Any], sid: str) -> dict[str, float]:
    screen_rows = {x["scene_id"]: x for x in ctx["reports"]["screen12"]["pairs"]}
    if sid in screen_rows:
        row = screen_rows[sid]
        return {
            "candidate_q_rmse_m": float(row["candidate_q_rmse_m"]),
            "b_q_rmse_m": float(row["b_q_rmse_m"]),
            "candidate_so3_rmse_rad": float(row["candidate_so3_rmse_rad"]),
            "b_so3_rmse_rad": float(row["b_so3_rmse_rad"]),
        }
    if sid == ctx["reports"]["T2"]["scene_id"]:
        report = ctx["reports"]["T2"]
        b_score = report["B_scores"]
    elif sid == ctx["reports"]["T3"]["scene_id"]:
        report = ctx["reports"]["T3"]
        b_score = report["locked_B_score"]
    else:
        raise ValueError(f"No existing audited result for self-check scene {sid}")
    c_score = report.get("candidate_score", report.get("candidate_scores"))
    return {
        "candidate_q_rmse_m": float(c_score["q_rmse_m"]),
        "b_q_rmse_m": float(b_score["q_rmse_m"]),
        "candidate_so3_rmse_rad": float(c_score["so3_rmse_rad"]),
        "b_so3_rmse_rad": float(b_score["so3_rmse_rad"]),
    }


def score_pair(ctx: dict[str, Any], sid: str, attempt_dir: Path | None) -> dict[str, Any]:
    c5_row = ctx["c5_rows"][sid]
    b_raw, b_status_path, b_status, b_sha, b_status_sha = validate_baseline(ctx, sid, c5_row)
    cand_raw, cand_status_path, cand_status, candidate_ref, provenance = candidate_reference(ctx, sid, attempt_dir)
    if cand_status.get("raw_path") and not same_path(cand_status["raw_path"], cand_raw):
        raise ValueError(f"Candidate status raw_path mismatch for {sid}")
    if cand_status.get("raw_sha256", "").lower() != candidate_ref["raw_sha256"].lower():
        raise ValueError(f"Candidate status raw SHA mismatch for {sid}")
    candidate_seed = int(cand_status.get("seed", -1))
    expected_meta = ctx["new_rows"].get(sid) or ctx["screen_rows"].get(sid)
    if expected_meta and candidate_seed != int(expected_meta["seed"]):
        raise ValueError(f"Candidate seed differs from its prepared scene manifest for {sid}")
    if b_status.get("seed") is not None and int(b_status["seed"]) != candidate_seed:
        raise ValueError(f"Candidate/B72 seed mismatch for {sid}")
    if cand_status.get("scene_sha256") and sid in ctx["new_rows"]:
        if cand_status["scene_sha256"].lower() != ctx["new_rows"][sid]["scene_sha256"].lower():
            raise ValueError(f"Candidate scene SHA differs from prepared manifest for {sid}")
    if cand_status.get("scene_sha256") and sid in ctx["screen_rows"]:
        if cand_status["scene_sha256"].lower() != ctx["screen_rows"][sid]["scene_sha256"].lower():
            raise ValueError(f"Candidate scene SHA differs from screen12 manifest for {sid}")
    if provenance == "new_DEV58":
        meta = ctx["new_rows"][sid]
        for field in ("scene_sha256", "spec_sha256", "metadata_sha256"):
            if cand_status.get(field, "").lower() != meta[field].lower():
                raise ValueError(f"Candidate status {field} differs from DEV58 manifest for {sid}")
        expected_binding = {
            "release_sha256": ROOT_RELEASE_SHA256,
            "source_lock_sha256": SOURCE_LOCK_SHA256,
            "manifest_sha256": DEV58_MANIFEST_SHA256,
            "runner_sha256": ctx["wrapper_sha256"],
        }
        for field, expected in expected_binding.items():
            if cand_status.get(field, "").lower() != expected:
                raise ValueError(f"Candidate status {field} differs from frozen DEV58 identity for {sid}")
        if cand_status.get("b_raw_sha256", "").lower() != b_sha.lower() or not same_path(cand_status.get("b_raw_path", ""), b_raw):
            raise ValueError(f"Candidate status B72 raw reference differs from lock for {sid}")
        if cand_status.get("b_run_status_sha256", "").lower() != b_status_sha.lower():
            raise ValueError(f"Candidate status B72 status SHA differs from lock for {sid}")
        run_index = list(ctx["new_rows"]).index(sid) + 1
        scene_audit_path = cand_raw.parent / "scene_audit.json"
        pair_audit_path = attempt_dir / f"pair_{run_index:02d}_audit.json"
        scene_audit = read_json(scene_audit_path)
        pair_audit = read_json(pair_audit_path)
        for name, record in (("scene audit", scene_audit), ("pair audit", pair_audit)):
            if (
                record.get("scene_id") != sid
                or record.get("release_sha256", expected_binding["release_sha256"]).lower() != expected_binding["release_sha256"]
                or record.get("source_lock_sha256", expected_binding["source_lock_sha256"]).lower() != expected_binding["source_lock_sha256"]
                or record.get("manifest_sha256", expected_binding["manifest_sha256"]).lower() != expected_binding["manifest_sha256"]
            ):
                raise ValueError(f"Candidate {name} identity differs from frozen DEV58 inputs for {sid}")
        if scene_audit.get("runner_sha256", "").lower() != expected_binding["runner_sha256"]:
            raise ValueError(f"Candidate scene audit runner SHA differs from frozen wrapper for {sid}")
        if (
            scene_audit.get("arm") != "candidate"
            or scene_audit.get("seed") != candidate_seed
            or scene_audit.get("scene_sha256") != meta["scene_sha256"]
            or scene_audit.get("spec_sha256") != meta["spec_sha256"]
            or scene_audit.get("metadata_sha256") != meta["metadata_sha256"]
            or scene_audit.get("same_scene_payload_sha256") != meta["scene_sha256"]
            or scene_audit.get("effective_options_sha256") != cand_status.get("effective_options_sha256")
        ):
            raise ValueError(f"Candidate scene audit does not match the prepared scene and status for {sid}")
        pair_baseline_raw = Path(pair_audit.get("baseline_raw_path", ""))
        pair_baseline_status = Path(pair_audit.get("baseline_run_status_path", ""))
        pair_candidate_raw = Path(pair_audit.get("candidate_raw_path", ""))
        pair_candidate_status = Path(pair_audit.get("candidate_status_path", ""))
        if (
            pair_audit.get("schema") != "MORPH_DEV2_DEV58_B72_PAIR_AUDIT_V1"
            or pair_audit.get("scope") != "MORPH_DEV2_DEV58"
            or pair_audit.get("status") != "RECORDED"
            or pair_audit.get("baseline_controller") != "B_TRACEABLE_C3CORE_V1"
            or pair_audit.get("external_identity_sha256", "").lower() != meta["external_identity_sha256"].lower()
            or pair_audit.get("same_scene_sha256", "").lower() != meta["scene_sha256"].lower()
            or pair_audit.get("baseline_raw_sha256", "").lower() != b_sha.lower()
            or pair_audit.get("baseline_run_status_sha256", "").lower() != b_status_sha.lower()
            or not same_path(pair_baseline_raw, b_raw)
            or not same_path(pair_baseline_status, b_status_path)
            or pair_audit.get("candidate_raw_sha256", "").lower() != candidate_ref["raw_sha256"].lower()
            or pair_audit.get("candidate_status_sha256", "").lower() != candidate_ref["status_sha256"].lower()
            or not same_path(pair_candidate_raw, cand_raw)
            or not same_path(pair_candidate_status, cand_status_path)
            or int(pair_audit.get("candidate_plant_calls", -1)) != 1
            or int(pair_audit.get("training_run_count", -1)) != 0
            or pair_audit.get("TEST_accessed") is not False
            or pair_audit.get("candidate_engineering_gate", {}).get("passed") is not True
            or pair_audit.get("safety_gate", {}).get("passed") is not True
        ):
            raise ValueError(f"Candidate pair audit does not bind the expected B72 pair and scene identity for {sid}")
        candidate_ref["scene_audit_path"] = str(scene_audit_path)
        candidate_ref["scene_audit_sha256"] = sha256_file(scene_audit_path)
        candidate_ref["pair_audit_path"] = str(pair_audit_path)
        candidate_ref["pair_audit_sha256"] = sha256_file(pair_audit_path)
    candidate_score, candidate_inputs, candidate_evidence = score_raw(cand_raw)
    b_score, b_inputs, b_evidence = score_raw(b_raw)
    stored_diffs = {
        key: abs(candidate_score[key] - float(cand_status["score"][key]))
        for key in ("q_rmse_m", "so3_rmse_rad")
        if key in cand_status.get("score", {})
    }
    if provenance == "new_DEV58" and (len(stored_diffs) != 2 or max(stored_diffs.values()) > 1e-12):
        raise ValueError(f"Independent raw score differs from new candidate status by >1e-12 for {sid}: {stored_diffs}")
    if b_evidence["raw_log_status"] != "STABLE" or b_evidence["raw_safety_stop_reason"] or b_evidence["raw_last_transition"] != N:
        raise ValueError(f"Locked B72 raw status differs from its stable C5 record for {sid}")
    if (candidate_evidence["raw_log_status"] != cand_status.get("runner_status")
            or candidate_evidence["raw_safety_stop_reason"] != cand_status.get("safety_stop_reason", "")
            or candidate_evidence["raw_last_transition"] != float(cand_status["last_transition"])):
        raise ValueError(f"Candidate raw/status evidence differs for {sid}")
    compare_scene_inputs(candidate_inputs, b_inputs, sid)
    morphing_arms = commanded_morphing_arms(candidate_inputs["arms/command"])
    dq = candidate_score["q_rmse_m"] - b_score["q_rmse_m"]
    dr = candidate_score["so3_rmse_rad"] - b_score["so3_rmse_rad"]
    return {
        "scene_id": sid,
        "task": scene_tokens(sid)[0],
        "wind_id": scene_tokens(sid)[1],
        "commanded_morphing_arms_count": morphing_arms,
        "commanded_morphing_active": morphing_arms > 0,
        "seed": int(cand_status["seed"]),
        "b_status_seed": b_status.get("seed"),
        "candidate_provenance": provenance,
        "candidate_status": cand_status.get("status", "UNKNOWN"),
        "candidate_runner_status": cand_status.get("runner_status", "UNKNOWN"),
        "candidate_safety_stop_reason": cand_status.get("safety_stop_reason", ""),
        "candidate_engineering_gate": gate_value(cand_status, "engineering_gate"),
        "candidate_safety_gate": gate_value(cand_status, "safety_gate"),
        "candidate_raw_log_status": candidate_evidence["raw_log_status"],
        "candidate_raw_safety_stop_reason": candidate_evidence["raw_safety_stop_reason"],
        "candidate_last_transition": candidate_evidence["raw_last_transition"],
        "candidate_raw_path": str(cand_raw),
        "candidate_raw_sha256": candidate_ref["raw_sha256"],
        "candidate_status_path": str(cand_status_path),
        "candidate_status_sha256": candidate_ref["status_sha256"],
        "candidate_scene_audit_path": candidate_ref.get("scene_audit_path", ""),
        "candidate_scene_audit_sha256": candidate_ref.get("scene_audit_sha256", ""),
        "candidate_pair_audit_path": candidate_ref.get("pair_audit_path", ""),
        "candidate_pair_audit_sha256": candidate_ref.get("pair_audit_sha256", ""),
        "candidate_scene_sha256": cand_status.get("scene_sha256", ""),
        "candidate_spec_sha256": cand_status.get("spec_sha256", ""),
        "candidate_metadata_sha256": cand_status.get("metadata_sha256", ""),
        "b_status": b_status.get("status", "UNKNOWN"),
        "b_runner_status": b_status.get("log_status", "UNKNOWN"),
        "b_safety_stop_reason": b_status.get("safety_stop_reason", ""),
        "b_raw_log_status": b_evidence["raw_log_status"],
        "b_raw_safety_stop_reason": b_evidence["raw_safety_stop_reason"],
        "b_last_transition": b_evidence["raw_last_transition"],
        "b_raw_path": str(b_raw),
        "b_raw_sha256": b_sha,
        "b_status_path": str(b_status_path),
        "b_status_sha256": b_status_sha,
        "external_identity_sha256": c5_row["external_identity_sha256"],
        "candidate_metrics": candidate_score,
        "b_metrics": b_score,
        "delta_candidate_minus_b": {"q_rmse_m": dq, "so3_rmse_rad": dr},
        "q_result": "tie" if abs(dq) <= 1e-12 else ("win" if dq < 0 else "loss"),
        "so3_result": "win" if dr < 0 else ("loss" if dr > 0 else "tie"),
        "same_scene_inputs_bitwise_equal": True,
        "candidate_status_stored_score_abs_diff": stored_diffs,
    }


def paired_scene_bootstrap_ci(values: list[float], seed: int = 20261025, replicates: int = 20_000) -> dict[str, Any]:
    if not values:
        return {"lower_95": None, "upper_95": None}
    samples = np.asarray(values, dtype=np.float64)
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, samples.size, size=(replicates, samples.size))
    means = np.mean(samples[indices], axis=1)
    return {
        "lower_95": float(np.quantile(means, 0.025)),
        "upper_95": float(np.quantile(means, 0.975)),
        "method": "percentile bootstrap resampling paired scenes (not time samples)",
        "seed": seed,
        "replicates": replicates,
        "resampling_unit_count": int(samples.size),
    }


def group_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"scene_count": 0}
    dq = [float(row["delta_candidate_minus_b"]["q_rmse_m"]) for row in rows]
    dr = [float(row["delta_candidate_minus_b"]["so3_rmse_rad"]) for row in rows]
    def metric_means(name: str) -> dict[str, float]:
        c = np.asarray([row["candidate_metrics"][name] for row in rows], dtype=np.float64)
        b = np.asarray([row["b_metrics"][name] for row in rows], dtype=np.float64)
        return {
            "candidate_mean": float(np.mean(c)),
            "b_mean": float(np.mean(b)),
            "delta_candidate_minus_b_mean": float(np.mean(c - b)),
        }

    axis_means = {}
    for axis, index in zip(("x", "y", "z"), range(3)):
        c = np.asarray([row["candidate_metrics"]["q_axis_rmse_m"][index] for row in rows], dtype=np.float64)
        b = np.asarray([row["b_metrics"]["q_axis_rmse_m"][index] for row in rows], dtype=np.float64)
        axis_means[axis] = {
            "candidate_mean_m": float(np.mean(c)),
            "b_mean_m": float(np.mean(b)),
            "delta_candidate_minus_b_mean_m": float(np.mean(c - b)),
        }
    return {
        "scene_count": len(rows),
        "commanded_morphing_scenes": sum(bool(row["commanded_morphing_active"]) for row in rows),
        "candidate_q_mean_m": float(np.mean([row["candidate_metrics"]["q_rmse_m"] for row in rows])),
        "b_q_mean_m": float(np.mean([row["b_metrics"]["q_rmse_m"] for row in rows])),
        "q_delta_candidate_minus_b_mean_m": float(np.mean(dq)),
        "q_wins_ties_losses": {name: sum(row["q_result"] == name for row in rows) for name in ("win", "tie", "loss")},
        "candidate_so3_mean_rad": float(np.mean([row["candidate_metrics"]["so3_rmse_rad"] for row in rows])),
        "b_so3_mean_rad": float(np.mean([row["b_metrics"]["so3_rmse_rad"] for row in rows])),
        "so3_delta_candidate_minus_b_mean_rad": float(np.mean(dr)),
        "so3_wins_ties_losses": {name: sum(row["so3_result"] == name for row in rows) for name in ("win", "tie", "loss")},
        "position_axis_rmse_scene_macros": axis_means,
        "position_early_0_to_2p2s_rmse_m": metric_means("q_early_rmse_m"),
        "position_late_2p2_to_20s_rmse_m": metric_means("q_late_rmse_m"),
        "position_peak_error_m": metric_means("q_peak_m"),
        "position_error_p95_m": metric_means("q_p95_m"),
        "attitude_early_0_to_2p2s_so3_rmse_rad": metric_means("so3_early_rmse_rad"),
        "attitude_late_2p2_to_20s_so3_rmse_rad": metric_means("so3_late_rmse_rad"),
        "attitude_peak_so3_error_rad": metric_means("so3_peak_rad"),
        "attitude_so3_error_p95_rad": metric_means("so3_p95_rad"),
        "controller_call_time_s_mean_per_scene": metric_means("controller_call_time_s_mean"),
        "controller_call_time_s_p95_per_scene": metric_means("controller_call_time_s_p95"),
        "paired_scene_bootstrap_95ci": {
            "q_delta_candidate_minus_b_mean_m": paired_scene_bootstrap_ci(dq),
            "so3_delta_candidate_minus_b_mean_rad": paired_scene_bootstrap_ci(dr),
        },
    }


def safety_summary(rows: list[dict[str, Any]], arm: str) -> dict[str, Any]:
    metric_key = "candidate_metrics" if arm == "candidate" else "b_metrics"
    status_key = f"{arm}_status"
    raw_status_key = f"{arm}_raw_log_status"
    runner_status_key = f"{arm}_runner_status"
    safety_key = f"{arm}_safety_stop_reason" if arm == "b" else "candidate_safety_stop_reason"
    gate_key = "candidate_safety_gate" if arm == "candidate" else None
    sat = [int(row[metric_key]["motor_saturation_count"]) for row in rows]
    clip = [int(row[metric_key]["generalized_clip_count"]) for row in rows]
    tilt = [int(row[metric_key]["tilt_limited_count"]) for row in rows]
    labels: dict[str, int] = {}
    for row in rows:
        label = str(row.get(status_key, row.get("candidate_status", "UNKNOWN")))
        labels[label] = labels.get(label, 0) + 1
    return {
        "scene_count": len(rows),
        "status_labels": dict(sorted(labels.items())),
        "raw_stable_log_count": sum(row[raw_status_key] == "STABLE" for row in rows),
        "status_or_raw_safety_stop_count": sum(
            bool(row.get(safety_key, "")) or row[raw_status_key] != "STABLE" or row.get(runner_status_key, "STABLE") != "STABLE"
            for row in rows
        ),
        "candidate_safety_gate_failed_count": sum(row.get(gate_key) is False for row in rows) if gate_key else None,
        "motor_saturation_steps_total": sum(sat),
        "scenes_with_motor_saturation": sum(x > 0 for x in sat),
        "generalized_clip_steps_total": sum(clip),
        "scenes_with_generalized_clip": sum(x > 0 for x in clip),
        "tilt_limited_steps_total": sum(tilt),
        "scenes_with_tilt_limit": sum(x > 0 for x in tilt),
    }


def csv_row(row: dict[str, Any]) -> dict[str, Any]:
    c, b, d = row["candidate_metrics"], row["b_metrics"], row["delta_candidate_minus_b"]
    return {
        "scene_id": row["scene_id"], "task": row["task"], "wind_id": row["wind_id"], "seed": row["seed"],
        "commanded_morphing_arms_count": row["commanded_morphing_arms_count"],
        "commanded_morphing_active": row["commanded_morphing_active"],
        "candidate_provenance": row["candidate_provenance"], "q_result": row["q_result"], "so3_result": row["so3_result"],
        "candidate_status": row["candidate_status"], "candidate_runner_status": row["candidate_runner_status"],
        "candidate_raw_sha256": row["candidate_raw_sha256"], "candidate_status_sha256": row["candidate_status_sha256"],
        "candidate_q_rmse_m": c["q_rmse_m"], "b_q_rmse_m": b["q_rmse_m"], "delta_q_rmse_m": d["q_rmse_m"],
        "candidate_q_x_rmse_m": c["q_axis_rmse_m"][0], "candidate_q_y_rmse_m": c["q_axis_rmse_m"][1], "candidate_q_z_rmse_m": c["q_axis_rmse_m"][2],
        "b_q_x_rmse_m": b["q_axis_rmse_m"][0], "b_q_y_rmse_m": b["q_axis_rmse_m"][1], "b_q_z_rmse_m": b["q_axis_rmse_m"][2],
        "candidate_q_early_rmse_m": c["q_early_rmse_m"], "b_q_early_rmse_m": b["q_early_rmse_m"],
        "candidate_q_late_rmse_m": c["q_late_rmse_m"], "b_q_late_rmse_m": b["q_late_rmse_m"],
        "candidate_q_peak_m": c["q_peak_m"], "b_q_peak_m": b["q_peak_m"],
        "candidate_q_p95_m": c["q_p95_m"], "b_q_p95_m": b["q_p95_m"],
        "candidate_so3_rmse_rad": c["so3_rmse_rad"], "b_so3_rmse_rad": b["so3_rmse_rad"], "delta_so3_rmse_rad": d["so3_rmse_rad"],
        "candidate_so3_early_rmse_rad": c["so3_early_rmse_rad"], "b_so3_early_rmse_rad": b["so3_early_rmse_rad"],
        "candidate_so3_late_rmse_rad": c["so3_late_rmse_rad"], "b_so3_late_rmse_rad": b["so3_late_rmse_rad"],
        "candidate_so3_peak_rad": c["so3_peak_rad"], "b_so3_peak_rad": b["so3_peak_rad"],
        "candidate_so3_p95_rad": c["so3_p95_rad"], "b_so3_p95_rad": b["so3_p95_rad"],
        "candidate_controller_call_time_s_mean": c["controller_call_time_s_mean"], "b_controller_call_time_s_mean": b["controller_call_time_s_mean"],
        "candidate_controller_call_time_s_p95": c["controller_call_time_s_p95"], "b_controller_call_time_s_p95": b["controller_call_time_s_p95"],
        "candidate_motor_saturation_count": c["motor_saturation_count"], "b_motor_saturation_count": b["motor_saturation_count"],
        "candidate_generalized_clip_count": c["generalized_clip_count"], "b_generalized_clip_count": b["generalized_clip_count"],
        "candidate_tilt_limited_count": c["tilt_limited_count"], "b_tilt_limited_count": b["tilt_limited_count"],
        "b_raw_sha256": row["b_raw_sha256"], "b_status_sha256": row["b_status_sha256"],
        "same_scene_inputs_bitwise_equal": row["same_scene_inputs_bitwise_equal"],
    }


def run_self_check(ctx: dict[str, Any]) -> dict[str, Any]:
    sample_ids = [
        "DL1018_VAL_T1_C00_W07",
        "DL1018_DEV_T2_C02_W15",
        "DL1018_DEV_T3_C10_W11",
    ]
    checks = []
    for sid in sample_ids:
        row = score_pair(ctx, sid, None)
        expected = historical_expectation(ctx, sid)
        observed = {
            "candidate_q_rmse_m": row["candidate_metrics"]["q_rmse_m"],
            "b_q_rmse_m": row["b_metrics"]["q_rmse_m"],
            "candidate_so3_rmse_rad": row["candidate_metrics"]["so3_rmse_rad"],
            "b_so3_rmse_rad": row["b_metrics"]["so3_rmse_rad"],
        }
        diffs = {key: abs(observed[key] - expected[key]) for key in expected}
        if max(diffs.values()) > 1e-12:
            raise ValueError(f"Self-check differs from prior reviewed result for {sid}: {diffs}")
        checks.append({"scene_id": sid, "observed": observed, "prior_review": expected, "absolute_differences": diffs, "checks_passed": True})
    return {
        "mode": "read_only_self_check",
        "scene_count": len(checks),
        "checks": checks,
        "plant_calls": 0,
        "training_runs": 0,
        "TEST_accessed": False,
    }


def build_report(ctx: dict[str, Any], attempt_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    attempt_dir = attempt_dir.resolve()
    try:
        attempt_dir.relative_to((ENTRY / "attempts").resolve())
    except ValueError as exc:
        raise ValueError("--attempt-dir must be inside morph_dev2_dev72_v1/attempts") from exc
    batch_path = attempt_dir / "batch_status.json"
    if not batch_path.is_file():
        raise FileNotFoundError(f"Missing DEV58 batch_status.json: {batch_path}")
    batch = read_json(batch_path)
    if not (
        batch.get("schema") == "MORPH_DEV2_DEV58_BATCH_STATUS_V1"
        and batch.get("status") == "MORPH_DEV2_DEV58_COMPLETE"
        and batch.get("release_sha256", "").lower() == ROOT_RELEASE_SHA256
        and batch.get("source_lock_sha256", "").lower() == SOURCE_LOCK_SHA256
        and batch.get("manifest_sha256", "").lower() == DEV58_MANIFEST_SHA256
        and int(batch.get("runner_invocation_count", -1)) == 58
        and int(batch.get("confirmed_plant_runs", -1)) == 58
        and int(batch.get("confirmed_transitions", -1)) == 1_160_000
        and int(batch.get("unknown_plant_invocations", -1)) == 0
        and int(batch.get("training_run_count", -1)) == 0
        and batch.get("TEST_accessed") is False
        and len(batch.get("completed_scenes", [])) == 58
        and all(batch.get("completed_scenes", []))
        and len(batch.get("safety_pass", [])) == 58
        and all(batch.get("safety_pass", []))
        and attempt_dir.name == ATTEMPT_ID
    ):
        raise ValueError("Attempt batch_status or A02 release identity does not identify a complete, safe 58-call DEV58 batch")
    rows = [score_pair(ctx, sid, attempt_dir) for sid in ctx["c5_ids"]]
    tasks = {name: group_summary([row for row in rows if row["task"] == name]) for name in ("HELIX", "FIG8_3D", "SQUARE")}
    winds = {
        "W09-W14": group_summary([row for row in rows if 9 <= row["wind_id"] <= 14]),
        "W15": group_summary([row for row in rows if row["wind_id"] == 15]),
    }
    morphology = {
        "commanded_active_morphing": group_summary([row for row in rows if row["commanded_morphing_active"]]),
        "fixed_geometry": group_summary([row for row in rows if not row["commanded_morphing_active"]]),
    }
    all_summary = group_summary(rows)
    report = {
        "schema": "MORPH_DEV2_DEV72_CANDIDATE_VS_LOCKED_B72_INDEPENDENT_RESCORE_V3",
        "status": "INDEPENDENT_RAW_RESCORE_COMPLETE",
        "interpretation": "Descriptive paired rescore only; it does not create or alter an acceptance gate.",
        "candidate_scope": "C5 DSSM14/M110 frozen position encoder, normalizer and W0 with its existing online position head; attitude RBF output/update disabled and replaced by analytic inertia feedforward plus bounded disturbance observer. Candidate-vs-B is a total-stack comparison, not an attitude-only causal ablation.",
        "scene_count": len(rows),
        "candidate_provenance_counts": {name: sum(row["candidate_provenance"] == name for row in rows) for name in ("screen12", "T2", "T3", "new_DEV58")},
        "input_locks": {
            "c5_path": str(C5_LOCK), "c5_sha256": C5_LOCK_SHA256,
            "b_traceable_path": str(B_LOCK), "b_traceable_sha256": B_LOCK_SHA256,
            "dev58_manifest_path": str(DEV58_MANIFEST), "dev58_manifest_sha256": DEV58_MANIFEST_SHA256,
            "screen12_manifest_path": str(SCREEN_MANIFEST), "screen12_manifest_sha256": SCREEN_MANIFEST_SHA256,
            "dev58_candidate_source_lock_path": str(SOURCE_LOCK), "dev58_candidate_source_lock_sha256": ctx["source_lock_sha256"],
            "dev58_root_release_path": str(ROOT_RELEASE), "dev58_root_release_sha256": ROOT_RELEASE_SHA256,
            "screen12_rescore_path": str(SCREEN_REVIEW), "screen12_rescore_sha256": sha256_file(SCREEN_REVIEW),
            "prior_t2_review_path": str(T2_REVIEW), "prior_t2_review_sha256": sha256_file(T2_REVIEW),
            "prior_t3_review_path": str(T3_REVIEW), "prior_t3_review_sha256": sha256_file(T3_REVIEW),
            "rescore_script_path": str(Path(__file__).resolve()), "rescore_script_sha256": sha256_file(Path(__file__).resolve()),
        },
        "dev58_attempt_dir": str(attempt_dir),
        "dev58_batch_status": batch.get("status", "UNKNOWN"),
        "dev58_batch_status_sha256": sha256_file(batch_path),
        "batch_reported_completed_scenes": sum(bool(x) for x in batch.get("completed_scenes", [])),
        "batch_reported_safety_pass_scenes": sum(bool(x) for x in batch.get("safety_pass", [])),
        "formula": {
            "position_Q": "sqrt(mean_t(sum_xyz((state_position - reference_position)^2))) over all 20,001 logged state samples from 0 to 20 s.",
            "attitude_SO3": "sqrt(mean_k(theta_k^2)) over 20,000 transitions; theta=atan2(0.5*norm(vee(Rd^T R - R^T Rd)), clip((trace(Rd^T R)-1)/2,-1,1)); R uses the logged ZYX Euler convention.",
            "pair_delta": "candidate minus same-scene locked B72. For position Q, |delta|<=1e-12 m is a tie; otherwise lower is a win. For SO(3), exact equality is a tie; otherwise lower is a win. All values use unrounded RMSEs.",
            "group_macro": "Unweighted arithmetic mean of per-scene RMSEs and per-scene paired deltas within each group; time samples are not treated as independent scenes.",
            "early_late": "Position samples split at t=2.2 s using state time (<2.2 early, >=2.2 late); attitude transitions use the same threshold on transition_time. Counts are fixed at 2,200/17,801 states and 2,200/17,800 transitions.",
            "p95": "Per-scene 95th percentile of Euclidean position error norm over 20,001 states and SO(3) error over 20,000 transitions, using NumPy linear percentile interpolation; group values are unweighted means of per-scene percentiles.",
            "controller_time": "Per-scene mean and 95th percentile of logged controller_call_time_s across 20,000 transitions; timing excludes candidate post-allocator commit as flagged in the raw score contract.",
            "morphology_group": "A scene is commanded-active if any arm/command element is nonzero above 1e-12 over the 20,000 transitions. This is a descriptive stratification only, not evidence that morphing itself improves performance.",
            "safety_counts": "Per-transition any-axis counts from raw motor_saturated and generalized_clipped arrays; tilt_limited counts nonzero transitions; stop/status text is copied from raw/status records.",
        },
        "macro_all_72": all_summary,
        "task_group_macros": tasks,
        "wind_group_macros": winds,
        "wind_group_all_16_macros": {
            f"W{wind:02d}": group_summary([row for row in rows if row["wind_id"] == wind])
            for wind in range(16)
        },
        "morphology_group_macros": morphology,
        "safety_summary": {"candidate": safety_summary(rows, "candidate"), "b72": safety_summary(rows, "b")},
        "unresolved_items": [
            "The reused T2 candidate run_status remains FAILED_ENGINEERING; the prior independent review attributes that label to the former trace-shape checker. This rescore preserves the status label and reports raw metrics without rewriting it.",
            "Historical reused status files have differing schemas; missing historical TEST/training fields are not inferred from the raw. Their provenance remains the locked source/review records.",
            "The scorer verifies C5-locked B72 file hashes and exact same-scene raw input arrays. It does not rebuild all scene payloads from source CSVs or re-audit the full 20,000-sample observer causal traces.",
            "The B lineage review records historical_72_runtime_tree_gap_closed=false while closing per-scene C5 B72 raw/status lineage; retain both statements with their original scopes.",
        ],
        "pairs": rows,
    }
    return report, rows


def write_outputs(report: dict[str, Any], rows: list[dict[str, Any]]) -> tuple[Path, Path]:
    json_path = REVIEW / "DEV72_INDEPENDENT_RESCORE_v3.json"
    csv_path = REVIEW / "DEV72_INDEPENDENT_RESCORE_v3.csv"
    if json_path.exists() or csv_path.exists():
        raise FileExistsError("Rescore report output exists; refusing to overwrite an earlier review artifact")
    fields = list(csv_row(rows[0]).keys())
    with csv_path.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(csv_row(row) for row in rows)
    with json_path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    return json_path, csv_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only offline DEV72 candidate vs locked B72 raw rescorer")
    parser.add_argument("--attempt-dir", help="Completed DEV58 attempt directory under morph_dev2_dev72_v1/attempts")
    parser.add_argument("--self-check", action="store_true", help="Rescore one screen12, T2 and T3 pair against prior reviewed values; write no files")
    args = parser.parse_args()
    if args.self_check and args.attempt_dir:
        parser.error("--self-check cannot be combined with --attempt-dir")
    if not args.self_check and not args.attempt_dir:
        parser.error("--attempt-dir is required unless --self-check is selected")
    ctx = load_context()
    if args.self_check:
        print(json.dumps(run_self_check(ctx), ensure_ascii=False, indent=2, allow_nan=False))
        return
    attempt_dir = Path(args.attempt_dir)
    if not attempt_dir.is_absolute():
        attempt_dir = ROOT / attempt_dir
    report, rows = build_report(ctx, attempt_dir)
    json_path, csv_path = write_outputs(report, rows)
    print(json.dumps({
        "status": report["status"],
        "scene_count": report["scene_count"],
        "dev58_batch_status": report["dev58_batch_status"],
        "macro_all_72": report["macro_all_72"],
        "task_group_macros": report["task_group_macros"],
        "wind_group_macros": report["wind_group_macros"],
        "json_path": str(json_path),
        "csv_path": str(csv_path),
        "plant_calls": 0,
        "training_runs": 0,
        "TEST_accessed": False,
    }, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
