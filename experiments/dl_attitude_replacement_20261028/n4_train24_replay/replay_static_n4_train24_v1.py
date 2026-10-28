#!/usr/bin/env python3
"""Freeze and replay one fixed four-notch bank on the exact physical TRAIN24 raws."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import sys
from pathlib import Path

import h5py
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PROTOCOL_PATH = HERE / "PREDECLARED_PROTOCOL_v1.json"
BINDING_PATH = HERE / "SOURCE_BINDING_v1.json"
REPORT_PATH = HERE / "TRAIN24_STATIC_N4_REPLAY_v1.json"
GROUP_CSV_PATH = HERE / "TRAIN24_STATIC_N4_WIND_GROUPS_v1.csv"

DATASET_DIR = ROOT / "experiments/dl_attitude_replacement_20261028/position_cosine_gru_train24_causal_v1"
DATASET_MANIFEST_PATH = DATASET_DIR / "DATASET_MANIFEST_v1.json"
DATASET_PATH = DATASET_DIR / "COSINE_GRU_C5_TRAIN24_POSITION_CAUSAL_PAIRS_v1.npz"
PROFILE_PATH = ROOT / "experiments/dl_attitude_replacement_20261028/position_compensation_windband_train24_audit_v1/TRAIN24_C5_WIND_BAND_PROFILE_v1.json"
OLD_PROTOCOL_PATH = ROOT / "experiments/dl_attitude_replacement_20261028/position_compensation_dual_notch_train_replay_v1/PREDECLARED_PROTOCOL_v1.json"
OLD_RESULT_PATH = ROOT / "experiments/dl_attitude_replacement_20261028/position_compensation_dual_notch_train_replay_v1/TRAIN_FROZEN_DUAL_NOTCH_REPLAY_v1.json"
PARENT_RUNS = ROOT / "experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_full72_v1/runs"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_new_json(path: Path, data: dict) -> None:
    if path.exists():
        raise RuntimeError(f"Refusing to overwrite {path}")
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def group_for_wind_code(code: int) -> str:
    if 0 <= code <= 2:
        return "W00-W02"
    if 3 <= code <= 5:
        return "W03-W05"
    if 6 <= code <= 8:
        return "W06-W08"
    if 9 <= code <= 11:
        return "W09-W11"
    if 12 <= code <= 14:
        return "W12-W14"
    if code == 15:
        return "W15"
    raise RuntimeError(f"Unexpected TRAIN24 wind code {code}")


def freeze_protocol() -> None:
    if PROTOCOL_PATH.exists() or BINDING_PATH.exists() or REPORT_PATH.exists():
        raise RuntimeError("Freeze artifacts already exist; refusing to replace them.")

    manifest = read_json(DATASET_MANIFEST_PATH)
    profile = read_json(PROFILE_PATH)
    old_protocol = read_json(OLD_PROTOCOL_PATH)
    old_result = read_json(OLD_RESULT_PATH)
    scene_ids = list(manifest["source_scene_ids"])
    profile_ids = list(profile["scope"]["scene_ids"])
    if (manifest.get("status") != "PASS_READ_ONLY_PARENT_RAW_CAUSAL_DATASET_BUILT" or
            manifest.get("scene_count") != 24 or len(scene_ids) != 24 or len(set(scene_ids)) != 24 or
            not manifest.get("scope", {}).get("only_physical_train24_ids") or
            manifest["scope"].get("VAL_raw_read") is not False or
            manifest["scope"].get("TEST_read") is not False or
            manifest["scope"].get("Plant_called_by_builder") is not False or
            profile.get("status") != "PASS_READ_ONLY_TRAIN24_RAW_PROFILE" or
            profile.get("scope", {}).get("physical_split") != "TRAIN_C5_24" or
            profile.get("scope", {}).get("scene_count") != 24 or profile_ids != scene_ids or
            profile.get("scope", {}).get("other_split_raws_read") is not False or
            profile.get("scope", {}).get("TEST_raw_or_score_read") is not False or
            profile.get("scope", {}).get("Plant_called") is not False or
            profile.get("scope", {}).get("inertia_reconstruction") is not False):
        raise RuntimeError("The exact physical TRAIN24 cohort/profile is not cleanly bound.")
    if (old_result.get("status") != "FAIL_FIXED_FROZEN_REPLAY" or
            old_result.get("TEST_read") is not False or
            old_result.get("plant_called_by_this_replay") is not False or
            old_protocol.get("notch_centers_hz") != [2.2, 3.2] or
            old_protocol.get("quality_factor_each") != 4.0):
        raise RuntimeError("The prior two-notch failure record is absent or changed.")

    profile_rows = {row["scene_id"]: row for row in profile["scene_records"]}
    if set(profile_rows) != set(scene_ids):
        raise RuntimeError("The TRAIN24 frequency profile scene set differs from the causal dataset.")
    source_rows = []
    model_ids = set()
    position_model_ids = set()
    position_options_ids = set()
    candidates = set()
    total_bytes = 0
    for index, scene_id in enumerate(scene_ids, start=1):
        row = profile_rows[scene_id]
        raw_path = PARENT_RUNS / scene_id / "raw_run.mat"
        status_path = PARENT_RUNS / scene_id / "run_status.json"
        start_path = PARENT_RUNS / scene_id / "run_start.json"
        if not raw_path.is_file() or not status_path.is_file() or not start_path.is_file():
            raise RuntimeError(f"Missing exact TRAIN parent source for {scene_id}")
        status = read_json(status_path)
        start = read_json(start_path)
        if (status.get("state") != "COMPLETED" or status.get("status_value") != "STABLE" or
                status.get("scene_id") != scene_id or status.get("transitions") != 20_000 or
                status.get("state_samples") != 20_001 or status.get("Plant_calls") != 1 or
                status.get("TEST_read") is not False or sha256(raw_path) != status.get("raw_sha256") or
                start.get("scene_id") != scene_id or start.get("attitude_arm") != "GRU_STREAM" or
                start.get("geometry_arm") != "ACTIVE" or start.get("TEST_read") is not False or
                start.get("inertia_reconstruction_enabled") is not False or
                start.get("Plant_truth_deployment_input") is not False):
            raise RuntimeError(f"TRAIN parent run/status identity mismatch for {scene_id}")
        model_ids.add(str(start.get("gru_model_sha256", "")))
        position_model_ids.add(str(start.get("position_model_sha256", "")))
        position_options_ids.add(str(start.get("common_position_options_sha256", "")))
        candidates.add(str(start.get("candidate", "")))
        wind_code = int(row["wind_code"])
        source_rows.append({
            "scene_id": scene_id,
            "wind_code_for_offline_grouping_only": wind_code,
            "wind_group_for_offline_grouping_only": group_for_wind_code(wind_code),
            "target_peak_f1_hz_from_frozen_train24_profile": row.get("wind_peak_f1_hz"),
            "target_peak_f2_hz_from_frozen_train24_profile": row.get("wind_peak_f2_hz"),
            "parent_raw_path": str(raw_path.resolve()),
            "parent_raw_sha256": status["raw_sha256"],
            "parent_raw_bytes": raw_path.stat().st_size,
            "parent_status_path": str(status_path.resolve()),
            "parent_status_sha256": sha256(status_path),
            "parent_run_start_path": str(start_path.resolve()),
            "parent_run_start_sha256": sha256(start_path),
            "parent_candidate": start["candidate"],
            "attitude_arm": start["attitude_arm"],
            "geometry_arm": start["geometry_arm"],
            "gru_model_sha256": start["gru_model_sha256"],
            "position_model_sha256": start["position_model_sha256"],
            "common_position_options_sha256": start["common_position_options_sha256"],
        })
        total_bytes += raw_path.stat().st_size
        print(f"Locked TRAIN parent {index}/24: {scene_id}", flush=True)
    if (len(model_ids) != 1 or "" in model_ids or len(position_model_ids) != 1 or
            "" in position_model_ids or len(position_options_ids) != 1 or "" in position_options_ids or
            len(candidates) != 1 or "" in candidates):
        raise RuntimeError("The 24 TRAIN raws do not share one frozen parent/C5 controller identity.")

    controls = [
        DATASET_MANIFEST_PATH, DATASET_PATH, PROFILE_PATH, OLD_PROTOCOL_PATH, OLD_RESULT_PATH,
        Path(__file__).resolve(),
    ]
    control_files = [{"path": str(path.resolve()), "sha256": sha256(path), "bytes": path.stat().st_size}
                     for path in controls]
    binding = {
        "schema": "STATIC_N4_TRAIN24_SOURCE_BINDING_V1",
        "status": "LOCKED_BEFORE_REPLAY",
        "source_split": "TRAIN_C5_24 (canonical DEV prefix)",
        "scene_count": 24,
        "scene_ids": scene_ids,
        "controller_identity": {
            "candidate": next(iter(candidates)),
            "attitude_arm": "GRU_STREAM",
            "geometry_arm": "ACTIVE",
            "gru_model_sha256": next(iter(model_ids)),
            "position_model_sha256": next(iter(position_model_ids)),
            "common_position_options_sha256": next(iter(position_options_ids)),
            "position_controller": "frozen C5 DSSM14 / M110 from parent raw; no added position residual GRU",
            "current_action_source": "log/stage1_position_held_applied_acceleration_mps2, cross-checked against the locked TRAIN24 causal NPZ event action",
        },
        "control_files": control_files,
        "parent_run_root": str(PARENT_RUNS.resolve()),
        "parent_total_raw_bytes": total_bytes,
        "source_rows": source_rows,
        "scope": {
            "only_exact_physical_train24_dev_prefix_raws": True,
            "VAL_read": False,
            "TEST_read": False,
            "inertia_reconstruction_enabled": False,
            "Plant_called_by_this_replay": False,
        },
    }
    write_new_json(BINDING_PATH, binding)
    binding_sha = sha256(BINDING_PATH)
    protocol = {
        "schema": "STATIC_N4_C5_PARENT_GRU_TRAIN24_FROZEN_REPLAY_PROTOCOL_V1",
        "study_id": "static_n4_train24_replay_v1",
        "status": "PREDECLARED_BEFORE_REPLAY",
        "scope": "Exact 24-scene physical TRAIN_C5_24 cohort only; canonical IDs have DEV prefix and are in-sample for the frozen parent model.",
        "purpose": "Screen one shared fixed four-notch bank on final applied C5 position compensation while retaining the parent cosine-GRU attitude arm; no added position residual GRU.",
        "filter": {
            "type": "four causal unity-DC biquad notches, cascaded in ascending listed order",
            "sample_rate_hz": 100.0,
            "centers_hz": [2.2, 3.2, 3.7, 4.8],
            "quality_factor_each": [4.0, 4.0, 4.0, 4.0],
            "application_point": "final held applied position-compensation acceleration, after frozen C5 action and before conversion to injected force",
            "update_rule": "Only at the logged 100-Hz position events; zero-order hold between events",
            "state_initialization": "At the first nonzero action event, initialize every section's input/output history to that current action and pass it unchanged",
            "final_action_clip_mps2": [-3.0, 3.0],
            "nominal_acceleration_yaw_and_shared_command_filter_changed": False,
            "wind_code_or_wind_truth_used_by_filter": False,
            "per_scene_frequency_switching": False,
        },
        "frequency_source": {
            "path": str(PROFILE_PATH.resolve()),
            "sha256": sha256(PROFILE_PATH),
            "use": "offline TRAIN24 group reporting only; fixed bank is identical for all 24 scenes",
        },
        "frozen_replay_metrics": {
            "transition_count": 20000,
            "target_definition": "Reconstruct logged command_filter_target_euler from commanded force; replay replaces only the final applied compensation, retaining logged yaw and nominal force",
            "low_frequency_band_hz": [0.05, 0.5],
            "low_frequency_amplitude": "Per-scene action and command-target RMS before/after plus RMS delta percentage",
            "low_frequency_phase": "Exact cascade response phase/equivalent delay and numeric group delay over 0.05-0.5 Hz; point response at 0.05, 0.10, 0.25, 0.45, 0.50 Hz",
            "wind_group_target_bands": "For each nonzero TRAIN24 wind group's fixed measured f1/f2, command-target and action vector RMS in center +/-0.10-Hz windows; report each scene and group median/range",
            "zero_wind_group": "W15 has no configured tone bands; report the fixed 0.05-10-Hz command-target RMS change",
            "additional_outputs": ["action clipping counts", "force-chain and baseline command reconstruction residuals", "group-wise broadband target RMS change"],
        },
        "predeclared_risk_flags_not_pass_gates": {
            "low_band_rms_delta_percent_max": 2.0,
            "low_band_group_delay_ms_max": 10.0,
            "rationale": "2% reuses the prior frozen low-band screen; 10 ms is one 100-Hz filter update interval.",
            "also_flag": "Any scene/group wind-tone command-target band whose RMS increases; report as counterevidence without tuning.",
        },
        "source_binding_path": str(BINDING_PATH.resolve()),
        "source_binding_sha256": binding_sha,
        "replay_script_path": str(Path(__file__).resolve()),
        "replay_script_sha256": sha256(Path(__file__).resolve()),
        "prior_two_notch_result": {
            "path": str(OLD_RESULT_PATH.resolve()),
            "sha256": sha256(OLD_RESULT_PATH),
            "status": "FAIL_FIXED_FROZEN_REPLAY",
            "preserve_without_overwrite": True,
        },
        "Plant_called_by_this_replay": False,
        "VAL_read": False,
        "TEST_read": False,
        "inertia_reconstruction_enabled": False,
        "parameter_sweep": False,
        "candidate_pass_claim": False,
        "interpretation_limit": "Frozen same-trajectory TRAIN replay only; no closed-loop actual-attitude/position prediction and no cross-wind generalization claim.",
    }
    write_new_json(PROTOCOL_PATH, protocol)
    print(json.dumps({"status": "PREDECLARED_AND_SOURCE_LOCKED", "scene_count": 24,
                      "controller_identity": binding["controller_identity"],
                      "source_binding_sha256": binding_sha,
                      "protocol_sha256": sha256(PROTOCOL_PATH),
                      "prior_two_notch_status": old_result["status"],
                      "raw_bytes_locked": total_bytes}, indent=2))


def notch_coefficients(center_hz: float, fs_hz: float, q: float) -> tuple[np.ndarray, np.ndarray]:
    w0 = 2.0 * np.pi * center_hz / fs_hz
    alpha = np.sin(w0) / (2.0 * q)
    scale = 1.0 + alpha
    b = np.array([1.0, -2.0 * np.cos(w0), 1.0], dtype=np.float64) / scale
    a = np.array([1.0, -2.0 * np.cos(w0) / scale, (1.0 - alpha) / scale], dtype=np.float64)
    return b, a


def section_step(x: np.ndarray, b: np.ndarray, a: np.ndarray, state: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    y = b[0] * x + b[1] * state[:, 0] + b[2] * state[:, 1] - a[1] * state[:, 2] - a[2] * state[:, 3]
    next_state = np.column_stack((x, state[:, 0], y, state[:, 2]))
    return y, next_state


def four_notch_event_replay(action: np.ndarray, event: np.ndarray, centers: list[float], q_values: list[float], fs_hz: float, limit: float) -> tuple[np.ndarray, int]:
    sections = [notch_coefficients(center, fs_hz, q) for center, q in zip(centers, q_values)]
    states = [np.zeros((3, 4), dtype=np.float64) for _ in sections]
    output = np.zeros_like(action)
    held = np.zeros(3, dtype=np.float64)
    initialized = False
    clip_count = 0
    for k in range(action.shape[0]):
        if event[k]:
            x = action[k]
            if not initialized and np.max(np.abs(x)) > 1e-12:
                for state in states:
                    state[:] = x[:, None]
                held = x.copy()
                initialized = True
            elif initialized:
                y = x
                for index, (b, a) in enumerate(sections):
                    y, states[index] = section_step(y, b, a, states[index])
                clipped = np.clip(y, -limit, limit)
                clip_count += int(np.count_nonzero(np.abs(clipped - y) > 1e-12))
                held = clipped
            else:
                held = x.copy()
        output[k] = held
    return output, clip_count


def vector_band_rms(signal: np.ndarray, fs_hz: float, low_hz: float, high_hz: float) -> float:
    x = np.asarray(signal, dtype=np.float64)
    if x.ndim == 1:
        x = x[:, None]
    x = x - np.mean(x, axis=0, keepdims=True)
    n = x.shape[0]
    window = np.hanning(n)
    spectrum = np.fft.rfft(x * window[:, None], axis=0)
    psd = np.abs(spectrum) ** 2 / (fs_hz * np.sum(window**2))
    if n % 2 == 0:
        psd[1:-1] *= 2.0
    else:
        psd[1:] *= 2.0
    freq = np.fft.rfftfreq(n, d=1.0 / fs_hz)
    selected = (freq >= low_hz) & (freq < high_hz)
    power = np.sum(psd[selected], axis=0) * (fs_hz / n)
    return float(np.sqrt(np.sum(power)))


def force_to_euler(acceleration: np.ndarray, yaw: np.ndarray) -> np.ndarray:
    specific = acceleration.copy()
    specific[:, 2] += 9.8
    cy, sy = np.cos(yaw), np.sin(yaw)
    a = cy * specific[:, 0] + sy * specific[:, 1]
    b = sy * specific[:, 0] - cy * specific[:, 1]
    roll = np.arctan2(b, np.hypot(specific[:, 2], a))
    pitch = np.arctan2(a, specific[:, 2])
    tilt = np.hypot(roll, pitch)
    scale = np.ones_like(tilt)
    over = tilt > (np.pi / 6.0)
    scale[over] = (np.pi / 6.0) / tilt[over]
    return np.column_stack((roll * scale, pitch * scale))


def transfer_response(f_hz: np.ndarray | float, centers: list[float], q_values: list[float], fs_hz: float) -> np.ndarray:
    f = np.asarray(f_hz, dtype=np.float64)
    z1 = np.exp(-1j * 2.0 * np.pi * f / fs_hz)
    response = np.ones_like(z1, dtype=np.complex128)
    for center, q in zip(centers, q_values):
        b, a = notch_coefficients(center, fs_hz, q)
        response *= (b[0] + b[1] * z1 + b[2] * z1**2) / (1.0 + a[1] * z1 + a[2] * z1**2)
    return response


def response_row(f_hz: float, centers: list[float], q_values: list[float], fs_hz: float) -> dict:
    h = complex(transfer_response(float(f_hz), centers, q_values, fs_hz))
    phase_deg = math.degrees(math.atan2(h.imag, h.real))
    return {
        "frequency_hz": f_hz,
        "magnitude": abs(h),
        "magnitude_db": 20.0 * math.log10(max(abs(h), 1e-15)),
        "phase_deg": phase_deg,
        "equivalent_phase_delay_ms": -phase_deg / (360.0 * f_hz) * 1000.0,
    }


def wind_tone_bands(row: dict) -> list[dict]:
    bands = []
    for label in ("f1", "f2"):
        center = row.get(f"target_peak_{label}_hz_from_frozen_train24_profile")
        if center is not None:
            center = float(center)
            bands.append({"label": label, "center_hz": center,
                          "band_hz": [max(0.05, center - 0.10), center + 0.10]})
    return bands


def analyze_scene(row: dict, raw_path: Path, npz: np.lib.npyio.NpzFile, npz_index: int,
                  protocol: dict) -> dict:
    fs_hz = float(protocol["filter"]["sample_rate_hz"])
    centers = [float(x) for x in protocol["filter"]["centers_hz"]]
    q_values = [float(x) for x in protocol["filter"]["quality_factor_each"]]
    limit = float(protocol["filter"]["final_action_clip_mps2"][1])
    transitions = int(protocol["frozen_replay_metrics"]["transition_count"])
    with h5py.File(raw_path, "r") as raw:
        log = raw["log"]
        read_log = lambda key: np.asarray(log[key][()], dtype=np.float64).T
        action = read_log("stage1_position_held_applied_acceleration_mps2")
        logged_compensation = read_log("position_compensation_applied_acceleration_mps2")
        nominal_acc = read_log("position_nominal_acceleration_mps2")
        nominal_force = read_log("position_bs_nominal_force_N")
        commanded_force = read_log("position_commanded_force_N")
        injected_force = read_log("stage1_position_injected_force_I_N")
        target = read_log("command_filter_target_euler")
        state = read_log("state")
        event = np.asarray(log["stage1_position_event"][()], dtype=bool).reshape(-1)

    if (action.shape != (transitions, 3) or logged_compensation.shape != action.shape or
            nominal_acc.shape != action.shape or nominal_force.shape != action.shape or
            commanded_force.shape != action.shape or injected_force.shape != action.shape or
            target.shape != (transitions, 3) or state.shape[0] != transitions + 1):
        raise RuntimeError(f"Unexpected parent raw log shapes: {row['scene_id']}")
    event_indices = np.flatnonzero(event)
    if len(event_indices) != 1999 or not np.all(np.diff(event_indices) == 10):
        raise RuntimeError(f"Unexpected 100-Hz C5 event schedule: {row['scene_id']}")
    if not np.array_equal(event_indices, np.asarray(npz["event_index_zero_based"][npz_index], dtype=np.int64)):
        raise RuntimeError(f"TRAIN24 NPZ event index differs from parent raw: {row['scene_id']}")
    npz_action = np.asarray(npz["applied_acceleration_event_mps2"][npz_index], dtype=np.float64)
    source_action_error = float(np.max(np.abs(action[event_indices] - npz_action)))
    if source_action_error > 2e-6:
        raise RuntimeError(f"TRAIN24 applied-action source cross-check failed: {row['scene_id']} ({source_action_error})")

    action_lineage_error = float(np.max(np.abs(action - logged_compensation)))
    ratio_mask = np.abs(nominal_acc) > 1e-7
    mass = float(np.median(nominal_force[ratio_mask] / nominal_acc[ratio_mask]))
    nominal_force_residual = float(np.max(np.abs(nominal_force - mass * nominal_acc)))
    injected_force_residual = float(np.max(np.abs(injected_force - mass * action)))
    commanded_force_residual = float(np.max(np.abs(commanded_force - (nominal_force - injected_force))))
    if (action_lineage_error > 1e-8 or nominal_force_residual > 1e-8 or
            injected_force_residual > 1e-8 or commanded_force_residual > 1e-8):
        raise RuntimeError(f"Parent C5 force/action chain mismatch: {row['scene_id']}")

    base_acc = commanded_force / mass
    yaw = state[:transitions, 8]
    reconstructed_rp = force_to_euler(base_acc, yaw)
    target_delta = np.arctan2(np.sin(reconstructed_rp - target[:, :2]), np.cos(reconstructed_rp - target[:, :2]))
    target_reconstruction_error = float(np.max(np.abs(target_delta)))
    if target_reconstruction_error > 1e-8:
        raise RuntimeError(f"Baseline command target reconstruction failed: {row['scene_id']}")

    filtered_action, clip_count = four_notch_event_replay(action, event, centers, q_values, fs_hz, limit)
    candidate_acc = base_acc + action - filtered_action
    candidate_rp = force_to_euler(candidate_acc, yaw)
    candidate_target = target.copy()
    candidate_target[:, :2] = candidate_rp

    low = (0.05, 0.5)
    low_action_before = vector_band_rms(action, 1000.0, *low)
    low_action_after = vector_band_rms(filtered_action, 1000.0, *low)
    low_action_delta = vector_band_rms(filtered_action - action, 1000.0, *low)
    low_target_before = vector_band_rms(target, 1000.0, *low)
    low_target_after = vector_band_rms(candidate_target, 1000.0, *low)
    low_target_delta = vector_band_rms(candidate_target - target, 1000.0, *low)

    tone_results = []
    for band in wind_tone_bands(row):
        lo, hi = band["band_hz"]
        before_all = vector_band_rms(target, 1000.0, lo, hi)
        after_all = vector_band_rms(candidate_target, 1000.0, lo, hi)
        before_rp = vector_band_rms(target[:, :2], 1000.0, lo, hi)
        after_rp = vector_band_rms(candidate_target[:, :2], 1000.0, lo, hi)
        before_action = vector_band_rms(action, 1000.0, lo, hi)
        after_action = vector_band_rms(filtered_action, 1000.0, lo, hi)
        tone_results.append({
            **band,
            "command_target_euler_vector_rms_before_mrad": before_all * 1e3,
            "command_target_euler_vector_rms_after_mrad": after_all * 1e3,
            "command_target_euler_reduction_percent": 100.0 * (before_all - after_all) / max(before_all, 1e-15),
            "command_target_roll_pitch_vector_rms_before_mrad": before_rp * 1e3,
            "command_target_roll_pitch_vector_rms_after_mrad": after_rp * 1e3,
            "command_target_roll_pitch_reduction_percent": 100.0 * (before_rp - after_rp) / max(before_rp, 1e-15),
            "applied_action_vector_rms_before_mps2": before_action,
            "applied_action_vector_rms_after_mps2": after_action,
            "applied_action_reduction_percent": 100.0 * (before_action - after_action) / max(before_action, 1e-15),
            "static_bank_response": response_row(band["center_hz"], centers, q_values, fs_hz),
        })

    broad_before = vector_band_rms(target, 1000.0, 0.05, 10.0)
    broad_after = vector_band_rms(candidate_target, 1000.0, 0.05, 10.0)
    return {
        "scene_id": row["scene_id"],
        "source_split": "TRAIN_C5_24",
        "wind_code_for_offline_grouping_only": row["wind_code_for_offline_grouping_only"],
        "wind_group_for_offline_grouping_only": row["wind_group_for_offline_grouping_only"],
        "target_peak_f1_hz": row["target_peak_f1_hz_from_frozen_train24_profile"],
        "target_peak_f2_hz": row["target_peak_f2_hz_from_frozen_train24_profile"],
        "source_parent_raw_path": str(raw_path),
        "source_parent_raw_sha256": row["parent_raw_sha256"],
        "parent_c5_action_npz_event_max_abs_difference_mps2": source_action_error,
        "logged_final_compensation_max_abs_difference_mps2": action_lineage_error,
        "transitions": transitions,
        "event_count": int(len(event_indices)),
        "derived_mass_kg_from_logged_nominal_force_over_acceleration": mass,
        "baseline_force_chain_max_abs_residual_N": max(nominal_force_residual, injected_force_residual, commanded_force_residual),
        "baseline_target_reconstruction_max_abs_error_rad": target_reconstruction_error,
        "action_limit_clip_count": clip_count,
        "low_frequency_0p05_0p5_hz": {
            "action_rms_before_mps2": low_action_before,
            "action_rms_after_mps2": low_action_after,
            "action_rms_delta_percent": 100.0 * (low_action_after - low_action_before) / max(low_action_before, 1e-15),
            "action_delta_rms_percent_of_before": 100.0 * low_action_delta / max(low_action_before, 1e-15),
            "command_target_euler_rms_before_mrad": low_target_before * 1e3,
            "command_target_euler_rms_after_mrad": low_target_after * 1e3,
            "command_target_euler_rms_delta_percent": 100.0 * (low_target_after - low_target_before) / max(low_target_before, 1e-15),
            "command_target_euler_delta_rms_percent_of_before": 100.0 * low_target_delta / max(low_target_before, 1e-15),
            "command_target_roll_pitch_rms_before_mrad": vector_band_rms(target[:, :2], 1000.0, *low) * 1e3,
            "command_target_roll_pitch_rms_after_mrad": vector_band_rms(candidate_target[:, :2], 1000.0, *low) * 1e3,
        },
        "wind_tone_target_bands": tone_results,
        "broad_command_target_0p05_10_hz": {
            "euler_vector_rms_before_mrad": broad_before * 1e3,
            "euler_vector_rms_after_mrad": broad_after * 1e3,
            "euler_vector_change_percent": 100.0 * (broad_after - broad_before) / max(broad_before, 1e-15),
        },
    }


def median_or_none(values: list[float]) -> float | None:
    return float(np.median(np.asarray(values, dtype=np.float64))) if values else None


def range_or_none(values: list[float]) -> list[float] | None:
    return [float(min(values)), float(max(values))] if values else None


def group_summary(rows: list[dict]) -> list[dict]:
    groups = ["W00-W02", "W03-W05", "W06-W08", "W09-W11", "W12-W14", "W15"]
    result = []
    for group in groups:
        members = [row for row in rows if row["wind_group_for_offline_grouping_only"] == group]
        f1 = members[0]["target_peak_f1_hz"] if members else None
        f2 = members[0]["target_peak_f2_hz"] if members else None
        tone_summary = []
        if f1 is not None and f2 is not None:
            for label in ("f1", "f2"):
                items = [next(b for b in row["wind_tone_target_bands"] if b["label"] == label) for row in members]
                tone_summary.append({
                    "label": label,
                    "center_hz": items[0]["center_hz"],
                    "band_hz": items[0]["band_hz"],
                    "command_target_euler_reduction_percent_median_range": {
                        "median": median_or_none([x["command_target_euler_reduction_percent"] for x in items]),
                        "range": range_or_none([x["command_target_euler_reduction_percent"] for x in items]),
                    },
                    "command_target_roll_pitch_reduction_percent_median_range": {
                        "median": median_or_none([x["command_target_roll_pitch_reduction_percent"] for x in items]),
                        "range": range_or_none([x["command_target_roll_pitch_reduction_percent"] for x in items]),
                    },
                    "applied_action_reduction_percent_median_range": {
                        "median": median_or_none([x["applied_action_reduction_percent"] for x in items]),
                        "range": range_or_none([x["applied_action_reduction_percent"] for x in items]),
                    },
                    "target_roll_pitch_rms_before_after_mrad_median": [
                        median_or_none([x["command_target_roll_pitch_vector_rms_before_mrad"] for x in items]),
                        median_or_none([x["command_target_roll_pitch_vector_rms_after_mrad"] for x in items]),
                    ],
                })
        low_action_delta = [row["low_frequency_0p05_0p5_hz"]["action_delta_rms_percent_of_before"] for row in members]
        low_target_delta = [row["low_frequency_0p05_0p5_hz"]["command_target_euler_delta_rms_percent_of_before"] for row in members]
        broad_change = [row["broad_command_target_0p05_10_hz"]["euler_vector_change_percent"] for row in members]
        result.append({
            "wind_group": group,
            "scene_count": len(members),
            "target_peaks_hz": [f1, f2] if f1 is not None and f2 is not None else None,
            "low_frequency_action_delta_rms_percent_median_max": {
                "median": median_or_none(low_action_delta), "max": max(low_action_delta) if low_action_delta else None,
            },
            "low_frequency_command_target_delta_rms_percent_median_max": {
                "median": median_or_none(low_target_delta), "max": max(low_target_delta) if low_target_delta else None,
            },
            "target_tone_bands": tone_summary,
            "broad_command_target_0p05_10_hz_change_percent_median_range": {
                "median": median_or_none(broad_change), "range": range_or_none(broad_change),
            },
            "zero_wind_group_no_tone_bands": group == "W15",
        })
    return result


def run_replay() -> None:
    if REPORT_PATH.exists() or GROUP_CSV_PATH.exists():
        raise RuntimeError("Replay output exists; refusing to overwrite.")
    protocol = read_json(PROTOCOL_PATH)
    binding = read_json(BINDING_PATH)
    if (protocol.get("status") != "PREDECLARED_BEFORE_REPLAY" or
            protocol.get("source_binding_sha256") != sha256(BINDING_PATH) or
            protocol.get("replay_script_sha256") != sha256(Path(__file__).resolve()) or
            binding.get("status") != "LOCKED_BEFORE_REPLAY" or
            binding.get("scene_count") != 24 or binding.get("scope", {}).get("TEST_read") is not False or
            binding.get("scope", {}).get("VAL_read") is not False):
        raise RuntimeError("Frozen protocol/source binding mismatch.")
    for item in binding["control_files"]:
        path = Path(item["path"])
        if not path.is_file() or sha256(path) != item["sha256"]:
            raise RuntimeError(f"Frozen control source changed: {path}")
    old_result = read_json(OLD_RESULT_PATH)
    if old_result.get("status") != "FAIL_FIXED_FROZEN_REPLAY" or sha256(OLD_RESULT_PATH) != protocol["prior_two_notch_result"]["sha256"]:
        raise RuntimeError("The old two-notch FAIL result changed; refusing to overwrite or reinterpret it.")

    manifest = read_json(DATASET_MANIFEST_PATH)
    profile = read_json(PROFILE_PATH)
    npz = np.load(DATASET_PATH, allow_pickle=False)
    scene_ids = list(binding["scene_ids"])
    if (list(manifest["source_scene_ids"]) != scene_ids or
            [str(s) for s in npz["scene_ids"].tolist()] != scene_ids):
        raise RuntimeError("TRAIN24 manifest/NPZ order differs from the source binding.")
    profile_rows = {row["scene_id"]: row for row in profile["scene_records"]}
    npz_index = {str(scene_id): index for index, scene_id in enumerate(npz["scene_ids"].tolist())}
    rows = []
    for index, source in enumerate(binding["source_rows"], start=1):
        scene_id = source["scene_id"]
        raw_path = Path(source["parent_raw_path"])
        status_path = Path(source["parent_status_path"])
        start_path = Path(source["parent_run_start_path"])
        if (not raw_path.is_file() or sha256(raw_path) != source["parent_raw_sha256"] or
                not status_path.is_file() or sha256(status_path) != source["parent_status_sha256"] or
                not start_path.is_file() or sha256(start_path) != source["parent_run_start_sha256"]):
            raise RuntimeError(f"Locked TRAIN source changed: {scene_id}")
        status = read_json(status_path)
        if (status.get("state") != "COMPLETED" or status.get("status_value") != "STABLE" or
                status.get("scene_id") != scene_id or status.get("TEST_read") is not False or
                status.get("raw_sha256") != source["parent_raw_sha256"]):
            raise RuntimeError(f"TRAIN status failed scope/identity check: {scene_id}")
        profile_row = profile_rows[scene_id]
        if (group_for_wind_code(int(profile_row["wind_code"])) != source["wind_group_for_offline_grouping_only"] or
                profile_row.get("wind_peak_f1_hz") != source["target_peak_f1_hz_from_frozen_train24_profile"] or
                profile_row.get("wind_peak_f2_hz") != source["target_peak_f2_hz_from_frozen_train24_profile"]):
            raise RuntimeError(f"Frozen offline wind group definition changed: {scene_id}")
        print(f"Replaying TRAIN scene {index}/24: {scene_id}", flush=True)
        rows.append(analyze_scene(source, raw_path, npz, npz_index[scene_id], protocol))

    centres = [float(x) for x in protocol["filter"]["centers_hz"]]
    q_values = [float(x) for x in protocol["filter"]["quality_factor_each"]]
    fs_hz = float(protocol["filter"]["sample_rate_hz"])
    low_grid = np.linspace(0.05, 0.5, 451)
    low_h = transfer_response(low_grid, centres, q_values, fs_hz)
    low_phase = np.unwrap(np.angle(low_h))
    low_omega = 2.0 * np.pi * low_grid / fs_hz
    group_delay_ms = -np.gradient(low_phase, low_omega) / fs_hz * 1000.0
    point_frequencies = sorted(set([0.05, 0.10, 0.25, 0.45, 0.50, 0.60, 0.85, 1.15, 1.75, *centres]))
    static_points = [response_row(f, centres, q_values, fs_hz) for f in point_frequencies]
    low_action_flag = [r["scene_id"] for r in rows if r["low_frequency_0p05_0p5_hz"]["action_delta_rms_percent_of_before"] > 2.0]
    low_target_flag = [r["scene_id"] for r in rows if r["low_frequency_0p05_0p5_hz"]["command_target_euler_delta_rms_percent_of_before"] > 2.0]
    tone_amplification = [
        {"scene_id": r["scene_id"], "band": b["label"], "center_hz": b["center_hz"],
         "command_target_rms_change_percent": -b["command_target_euler_reduction_percent"]}
        for r in rows for b in r["wind_tone_target_bands"]
        if b["command_target_euler_reduction_percent"] < 0.0
    ]
    clips = [r["scene_id"] for r in rows if r["action_limit_clip_count"] > 0]
    max_low_group_delay = float(np.max(np.abs(group_delay_ms)))
    report = {
        "schema": "STATIC_N4_C5_PARENT_GRU_TRAIN24_FROZEN_REPLAY_V1",
        "status": "MEASURED_FIXED_TRAIN24_REPLAY",
        "protocol_path": str(PROTOCOL_PATH.resolve()),
        "protocol_sha256": sha256(PROTOCOL_PATH),
        "source_binding_path": str(BINDING_PATH.resolve()),
        "source_binding_sha256": sha256(BINDING_PATH),
        "replay_script_sha256": sha256(Path(__file__).resolve()),
        "source_split": "TRAIN_C5_24 (canonical DEV prefix)",
        "controller_identity": binding["controller_identity"],
        "scene_count": len(rows),
        "filter": protocol["filter"],
        "static_low_frequency_response": {
            "band_hz": [0.05, 0.5],
            "max_abs_group_delay_ms": max_low_group_delay,
            "group_delay_ms_range": [float(np.min(group_delay_ms)), float(np.max(group_delay_ms))],
            "magnitude_db_range": [float(np.min(20.0 * np.log10(np.maximum(np.abs(low_h), 1e-15)))),
                                   float(np.max(20.0 * np.log10(np.maximum(np.abs(low_h), 1e-15))))],
            "phase_deg_range_unwrapped": [float(np.rad2deg(np.min(low_phase))), float(np.rad2deg(np.max(low_phase)))],
            "point_response": static_points,
        },
        "per_wind_group_summary_offline_only": group_summary(rows),
        "risk_flags": {
            "scene_low_action_delta_exceeds_2_percent": low_action_flag,
            "scene_low_command_target_delta_exceeds_2_percent": low_target_flag,
            "low_band_group_delay_exceeds_10ms": max_low_group_delay > 10.0,
            "wind_tone_command_target_rms_amplified": tone_amplification,
            "action_limit_clipping_scenes": clips,
        },
        "results": rows,
        "prior_two_notch_status_preserved": old_result["status"],
        "prior_two_notch_result_path": str(OLD_RESULT_PATH.resolve()),
        "prior_two_notch_result_sha256": sha256(OLD_RESULT_PATH),
        "Plant_called_by_this_replay": False,
        "VAL_read": False,
        "TEST_read": False,
        "inertia_reconstruction_enabled": False,
        "parameter_sweep": False,
        "closed_loop_effect_measured": False,
        "interpretation_limit": protocol["interpretation_limit"],
    }
    write_new_json(REPORT_PATH, report)
    with GROUP_CSV_PATH.open("x", newline="", encoding="utf-8") as stream:
        fields = ["wind_group", "scene_count", "target_peaks_hz", "low_action_delta_pct_median", "low_target_delta_pct_median",
                  "f1_target_reduction_pct_median", "f2_target_reduction_pct_median", "broad_target_change_pct_median"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for group in report["per_wind_group_summary_offline_only"]:
            tones = group["target_tone_bands"]
            writer.writerow({
                "wind_group": group["wind_group"], "scene_count": group["scene_count"],
                "target_peaks_hz": json.dumps(group["target_peaks_hz"]),
                "low_action_delta_pct_median": group["low_frequency_action_delta_rms_percent_median_max"]["median"],
                "low_target_delta_pct_median": group["low_frequency_command_target_delta_rms_percent_median_max"]["median"],
                "f1_target_reduction_pct_median": tones[0]["command_target_euler_reduction_percent_median_range"]["median"] if tones else "",
                "f2_target_reduction_pct_median": tones[1]["command_target_euler_reduction_percent_median_range"]["median"] if tones else "",
                "broad_target_change_pct_median": group["broad_command_target_0p05_10_hz_change_percent_median_range"]["median"],
            })
    print(json.dumps({
        "report": str(REPORT_PATH.resolve()),
        "group_csv": str(GROUP_CSV_PATH.resolve()),
        "status": report["status"],
        "scene_count": report["scene_count"],
        "low_frequency_response": report["static_low_frequency_response"],
        "risk_flags": report["risk_flags"],
        "wind_groups": report["per_wind_group_summary_offline_only"],
        "prior_two_notch_status_preserved": report["prior_two_notch_status_preserved"],
    }, indent=2))


def main() -> None:
    if len(sys.argv) == 2 and sys.argv[1] == "--freeze":
        freeze_protocol()
    elif len(sys.argv) == 1:
        run_replay()
    else:
        raise SystemExit("Usage: replay_static_n4_train24_v1.py [--freeze]")


if __name__ == "__main__":
    main()
