#!/usr/bin/env python3
"""Locked TRAIN_C5_24 inputs and exact command-filter replay helpers."""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

import h5py
import numpy as np


ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = ROOT / "experiments/dl_attitude_replacement_20261028/position_cosine_gru_train24_causal_v1"
DATA_PATH = DATA_DIR / "COSINE_GRU_C5_TRAIN24_POSITION_CAUSAL_PAIRS_v1.npz"
DATA_MANIFEST_PATH = DATA_DIR / "DATASET_MANIFEST_v1.json"
SOURCE_LOCK_PATH = DATA_DIR / "SOURCE_LOCK_v1.json"
PARENT_DIR = ROOT / "experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_full72_v1"
PARENT_RELEASE = PARENT_DIR / "RELEASE.json"
PARENT_SOURCE_LOCK = PARENT_DIR / "SOURCE_LOCK_v1.json"
PARENT_MANIFEST = PARENT_DIR / "MANIFEST.json"
PARENT_LEDGER = PARENT_DIR / "audits/FULL72_PROGRESS_LEDGER_v02.json"
LOCKED_CFG_PATH = PARENT_DIR / "LOCKED_CFG.json"
DT_S = 0.001
EVENT_DT_S = 0.01
GRAVITY_MPS2 = 9.8
MAX_TILT_RAD = math.pi / 6
FILTER_WN = np.array([18.0, 18.0, 12.0])
FILTER_DAMPING = np.ones(3)
FILTER_LIMIT = np.array([np.inf, np.inf, 6.0])


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def wrap(a: np.ndarray) -> np.ndarray:
    return np.arctan2(np.sin(a), np.cos(a))


def force_to_euler(acc: np.ndarray, adapter_yaw: np.ndarray,
                   output_yaw: np.ndarray | None = None) -> np.ndarray:
    specific = np.asarray(acc, dtype=np.float64).copy()
    specific[:, 2] += GRAVITY_MPS2
    adapter_yaw = np.asarray(adapter_yaw, dtype=np.float64)
    a = np.cos(adapter_yaw) * specific[:, 0] + np.sin(adapter_yaw) * specific[:, 1]
    b = np.sin(adapter_yaw) * specific[:, 0] - np.cos(adapter_yaw) * specific[:, 1]
    roll = np.arctan2(b, np.hypot(specific[:, 2], a))
    pitch = np.arctan2(a, specific[:, 2])
    tilt = np.hypot(roll, pitch)
    scale = np.minimum(1.0, MAX_TILT_RAD / np.maximum(tilt, np.finfo(float).eps))
    yaw_out = adapter_yaw if output_yaw is None else np.asarray(output_yaw, dtype=np.float64)
    return np.column_stack((roll * scale, pitch * scale, yaw_out))


def replay_filter(target: np.ndarray, initial_euler: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    euler = np.asarray(initial_euler, dtype=np.float64).copy()
    rate = np.zeros(3, dtype=np.float64)
    output = np.empty_like(target, dtype=np.float64)
    applied = np.empty_like(target, dtype=np.float64)
    requested = np.empty_like(target, dtype=np.float64)
    for i in range(len(target)):
        output[i] = euler  # command_filter_step returns pre-update state
        err = wrap(target[i] - euler)
        req = FILTER_WN * FILTER_WN * err - 2.0 * FILTER_DAMPING * FILTER_WN * rate
        requested[i] = req
        applied[i] = np.clip(req, -FILTER_LIMIT, FILTER_LIMIT)
        rate = rate + DT_S * applied[i]
        euler = wrap(euler + DT_S * rate)  # semi-implicit update
    return output, applied, requested


def _locked_command_filter() -> dict:
    # Parse only the command_filter JSON object; do not load unrelated cfg fields.
    source = LOCKED_CFG_PATH.read_text(encoding="utf-8-sig")
    match = re.search(r'"command_filter"\s*:\s*(\{[^{}]*\})', source, flags=re.S)
    if match is None:
        raise RuntimeError("Could not isolate locked command_filter configuration")
    return json.loads(match.group(1))


def load_locked_inputs() -> tuple[dict, dict, list[dict], dict]:
    manifest = read_json(DATA_MANIFEST_PATH)
    source_lock = read_json(SOURCE_LOCK_PATH)
    data_sha = sha256(DATA_PATH)
    if data_sha.lower() != manifest["dataset_sha256"].lower():
        raise RuntimeError("Causal NPZ SHA mismatch")
    if sha256(SOURCE_LOCK_PATH).lower() != manifest["source_lock_sha256"].lower():
        raise RuntimeError("Dataset source-lock SHA mismatch")
    if source_lock.get("data_sha256", "").lower() != data_sha.lower():
        raise RuntimeError("Source lock does not bind the causal NPZ")
    if manifest.get("scope", {}).get("VAL_raw_read") is not False or \
            manifest.get("scope", {}).get("TEST_read") is not False or \
            manifest.get("scope", {}).get("Plant_called_by_builder") is not False or \
            manifest.get("scope", {}).get("inertia_reconstruction") is not False:
        raise RuntimeError("TRAIN_C5_24 dataset scope lock failed")

    current_hashes = {
        "parent_release_sha256": sha256(PARENT_RELEASE),
        "parent_source_lock_sha256": sha256(PARENT_SOURCE_LOCK),
        "parent_manifest_sha256": sha256(PARENT_MANIFEST),
        "parent_ledger_sha256": sha256(PARENT_LEDGER),
        "parent_locked_cfg_sha256": sha256(LOCKED_CFG_PATH),
    }
    for key in ("parent_release_sha256", "parent_source_lock_sha256",
                "parent_manifest_sha256", "parent_ledger_sha256"):
        value = current_hashes[key]
        if source_lock.get(key, "").lower() != value.lower():
            raise RuntimeError(f"Parent lineage SHA mismatch for {key}")
    cfg = _locked_command_filter()
    if (cfg.get("wn") != [18, 18, 12] or cfg.get("damping") != [1, 1, 1] or
            cfg.get("acceleration_limit_numeric_labels") != ["Inf", "Inf", 6]):
        raise RuntimeError("Unexpected locked command-filter config")
    with np.load(DATA_PATH, allow_pickle=False) as z:
        # Deliberately do not load wind_cells or any wind/inertia field.
        arrays = {k: z[k] for k in (
            "scene_ids", "fold_id", "x14_logged", "x14_model_input",
            "target_interval_raw_mps2", "target_interval_clip_mps2",
            "applied_acceleration_event_mps2", "event_time_s", "interval_end_time_s",
            "ready_mask", "event_index_zero_based")}
    ids = arrays["scene_ids"].astype(str).tolist()
    lock_rows = source_lock["scene_rows"]
    if len(ids) != 24 or [r["scene_id"] for r in lock_rows] != ids:
        raise RuntimeError("Source-lock scene identities/order differ from NPZ")
    if arrays["x14_model_input"].shape != (24, 1999, 14) or \
            arrays["target_interval_clip_mps2"].shape != (24, 1999, 3) or \
            arrays["applied_acceleration_event_mps2"].shape != (24, 1999, 3) or \
            arrays["ready_mask"].shape != (24, 1999) or \
            arrays["event_index_zero_based"].shape != (24, 1999):
        raise RuntimeError("Unexpected corrected cosine-GRU TRAIN24 data shapes")
    if not np.array_equal(arrays["x14_logged"], arrays["x14_model_input"]):
        raise RuntimeError("Logged X14 differs from model input")
    if not np.array_equal(arrays["ready_mask"], np.broadcast_to(np.arange(1999) >= 31, (24, 1999))):
        raise RuntimeError("Unexpected position-GRU readiness mask")

    release_sha, source_sha, manifest_sha, cfg_sha = (
        current_hashes["parent_release_sha256"], current_hashes["parent_source_lock_sha256"],
        current_hashes["parent_manifest_sha256"], current_hashes["parent_locked_cfg_sha256"])
    trajectories = []
    audit_rows = []
    for i, rec in enumerate(lock_rows):
        sid = ids[i]
        raw_path = Path(rec["parent_cosine_gru_raw_path"])
        status_path = Path(rec["parent_status_path"])
        start_path = raw_path.parent / "run_start.json"
        for path, expected, label in (
            (raw_path, rec["parent_cosine_gru_raw_sha256"], "raw"),
            (status_path, rec["parent_status_sha256"], "status"),
            (start_path, rec["parent_run_start_sha256"], "run-start"),
        ):
            if sha256(path).lower() != expected.lower():
                raise RuntimeError(f"{sid}: {label} hash mismatch")
        status = read_json(status_path)
        start = read_json(start_path)
        if (status.get("state") != "COMPLETED" or status.get("status_value") != "STABLE" or
                status.get("safety_stop_reason") not in ("", "NONE", None) or
                status.get("scene_id") != sid or status.get("transitions") != 20000 or
                status.get("state_samples") != 20001 or status.get("TEST_read") is not False or
                status.get("raw_sha256", "").lower() != rec["parent_cosine_gru_raw_sha256"].lower()):
            raise RuntimeError(f"{sid}: parent status/safety/raw binding failed")
        if (start.get("scene_id") != sid or start.get("TEST_read") is not False or
                start.get("inertia_reconstruction_enabled") is not False or
                start.get("release_sha256", "").lower() != release_sha.lower() or
                start.get("source_lock_sha256", "").lower() != source_sha.lower() or
                start.get("manifest_sha256", "").lower() != manifest_sha.lower() or
                start.get("locked_cfg_sha256", "").lower() != cfg_sha.lower() or
                status.get("release_sha256", "").lower() != release_sha.lower() or
                status.get("source_lock_sha256", "").lower() != source_sha.lower()):
            raise RuntimeError(f"{sid}: parent run-start/release/source identity mismatch")

        with h5py.File(raw_path, "r") as f:
            g = f["log"]
            state_angles = np.asarray(g["state"][6:9, :], dtype=np.float64)
            time = np.asarray(g["transition_time"][()], dtype=np.float64).reshape(-1)
            nominal = np.asarray(g["position_nominal_acceleration_mps2"][()], dtype=np.float64).T
            applied = np.asarray(g["position_compensation_applied_acceleration_mps2"][()], dtype=np.float64).T
            logged_target = np.asarray(g["command_filter_target_euler"][()], dtype=np.float64).T
            logged_filtered = np.asarray(g["filtered_attitude_reference"][()], dtype=np.float64).T
            logged_req = np.asarray(g["command_filter_acceleration_request_unclamped_rads2"][()], dtype=np.float64).T
            logged_applied_cf = np.asarray(g["command_filter_acceleration_applied_rads2"][()], dtype=np.float64).T
            event_flag = np.asarray(g["position_event_flag"][()], dtype=bool).reshape(-1)
            ref = f["scene/reference"]
            ref_acc = np.asarray(ref["acceleration"][()], dtype=np.float64).T
            ref_yaw = np.asarray(ref["yaw"][()], dtype=np.float64).reshape(-1)
        if (state_angles.shape != (3, 20001) or time.shape != (20000,) or
                nominal.shape != (20000, 3) or applied.shape != (20000, 3) or
                logged_target.shape != (20000, 3) or logged_filtered.shape != (20000, 3) or
                ref_acc.shape != (20001, 3) or ref_yaw.shape != (20001,) or
                event_flag.shape != (20000,)):
            raise RuntimeError(f"{sid}: parent raw task/filter dimensions mismatch")
        event_idx = np.flatnonzero(event_flag)
        if (len(event_idx) != 1999 or event_idx[0] != 10 or not np.all(np.diff(event_idx) == 10) or
                not np.array_equal(event_idx, arrays["event_index_zero_based"][i])):
            raise RuntimeError(f"{sid}: position event indices/cadence mismatch")
        if not np.allclose(time, np.arange(20000) * DT_S, atol=1e-12, rtol=0):
            raise RuntimeError(f"{sid}: transition time/index mismatch")
        if not np.allclose(arrays["event_time_s"][i], time[event_idx], atol=2e-6, rtol=0):
            raise RuntimeError(f"{sid}: event-time vs parent raw mismatch")
        if not np.array_equal(arrays["ready_mask"][i], np.arange(1999) >= 31):
            raise RuntimeError(f"{sid}: ready mask differs from required 31-event warmup")
        event_action_err = float(np.max(np.abs(arrays["applied_acceleration_event_mps2"][i] - applied[event_idx]), initial=0.0))
        hold_err = max(float(np.max(np.abs(applied[j:j + 10] - applied[j]), initial=0.0)) for j in event_idx)
        if event_action_err > 1e-6 or hold_err > 1e-10:
            raise RuntimeError(f"{sid}: parent event action/100-Hz ZOH mismatch")

        outer_acc = nominal - applied
        target = force_to_euler(outer_acc, state_angles[2, :20000], ref_yaw[:20000])
        filtered, applied_cf, requested_cf = replay_filter(target, state_angles[:, 0])
        task_target = force_to_euler(ref_acc[:20000], ref_yaw[:20000], ref_yaw[:20000])
        d_target = wrap(target - logged_target)
        d_filtered = wrap(filtered - logged_filtered)
        audit_rows.append({
            "scene_id": sid,
            "raw_sha256": rec["parent_cosine_gru_raw_sha256"],
            "status_sha256": rec["parent_status_sha256"],
            "run_start_sha256": rec["parent_run_start_sha256"],
            "release_sha256": release_sha, "source_lock_sha256": source_sha,
            "event_count": int(len(event_idx)),
            "event_first_last_s": [float(time[event_idx[0]]), float(time[event_idx[-1]])],
            "event_action_vs_logged_applied_max_abs_mps2": event_action_err,
            "event_100hz_zoh_hold_max_abs_mps2": hold_err,
            "outer_target_replay_max_abs_wrapped_rad": float(np.max(np.abs(d_target))),
            "outer_target_replay_rmse_rad": float(np.sqrt(np.mean(d_target ** 2))),
            "filtered_reference_replay_max_abs_wrapped_rad": float(np.max(np.abs(d_filtered))),
            "filtered_reference_replay_rmse_rad": float(np.sqrt(np.mean(d_filtered ** 2))),
            "filter_requested_acceleration_max_abs_error_rad_s2": float(np.max(np.abs(requested_cf - logged_req))),
            "filter_applied_acceleration_max_abs_error_rad_s2": float(np.max(np.abs(applied_cf - logged_applied_cf))),
            "filter_clip_count_by_axis": np.sum(np.abs(requested_cf) > FILTER_LIMIT[None, :] + 1e-12, axis=0).astype(int).tolist(),
        })
        trajectories.append({
            "nominal_acc_1ms": nominal.astype(np.float32),
            "applied_acc_1ms": applied.astype(np.float32),
            "state_yaw_1ms": state_angles[2, :20000].astype(np.float32),
            "reference_acc_1ms": ref_acc[:20000].astype(np.float32),
            "reference_yaw_1ms": ref_yaw[:20000].astype(np.float32),
            "initial_euler": state_angles[:, 0].astype(np.float32),
            "task_target_euler": task_target.astype(np.float32),
        })

    audit = {
        "schema": "COSINE_GRU_TRAIN_C5_24_TASK_FILTER_REPLAY_AUDIT_V1",
        "scope": "Locked TRAIN_C5_24 parent cosine-GRU raw only; no VAL/TEST raw, no new Plant, no real-wind fields, no inertia reconstruction or use.",
        "dataset_sha256": data_sha,
        "dataset_manifest_sha256": sha256(DATA_MANIFEST_PATH),
        "source_lock_sha256": sha256(SOURCE_LOCK_PATH),
        "parent_lineage_sha256": current_hashes,
        "parent_model_exposure_note": manifest.get("parent_model_exposure", {}).get("limit"),
        "filter_config_from_locked_cfg": cfg,
        "filter_runtime": {"dt_s": DT_S, "initial_state": "logged initial Euler; zero initial Euler-rate", "logged_filter_output_is_pre_update": True},
        "outer_target_equation": "a_cmd = a_nominal - applied_position_compensation; map roll/pitch with current state yaw, then replace target yaw with reference yaw.",
        "task_target_equation": "map reference acceleration plus gravity and reference yaw through the frozen force-to-attitude adapter and max-tilt limit.",
        "maximum_replay_errors": {
            "outer_target_wrapped_rad": max(x["outer_target_replay_max_abs_wrapped_rad"] for x in audit_rows),
            "filtered_reference_wrapped_rad": max(x["filtered_reference_replay_max_abs_wrapped_rad"] for x in audit_rows),
            "filter_requested_acceleration_rad_s2": max(x["filter_requested_acceleration_max_abs_error_rad_s2"] for x in audit_rows),
            "filter_applied_acceleration_rad_s2": max(x["filter_applied_acceleration_max_abs_error_rad_s2"] for x in audit_rows),
            "event_action_hold_mps2": max(x["event_100hz_zoh_hold_max_abs_mps2"] for x in audit_rows),
        },
        "scenes": audit_rows,
    }
    return {"manifest": manifest, "source_lock": source_lock, "arrays": arrays,
            "trajectories": trajectories, "audit": audit}
