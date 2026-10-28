#!/usr/bin/env python3
"""Fixed, no-Plant dual-notch replay on the two bound physical TRAIN W09 raws."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import h5py
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PROTOCOL = json.loads((HERE / "PREDECLARED_PROTOCOL_v1.json").read_text(encoding="utf-8"))
OUT = HERE / "TRAIN_FROZEN_DUAL_NOTCH_REPLAY_v1.json"
CASES = (
    ("position_dc_penalty_oof_train_pair_preflight_W09_T1_C10_attempt014_v1", "DL1018_DEV_T1_C10_W09"),
    ("position_dc_penalty_oof_train_pair_preflight_W09_T3_C09_attempt015_v1", "DL1018_DEV_T3_C09_W09"),
)
FS_HZ = float(PROTOCOL["event_sample_rate_hz"])
NOTCHES = tuple(float(x) for x in PROTOCOL["notch_centers_hz"])
Q = float(PROTOCOL["quality_factor_each"])
ACTION_LIMIT = float(PROTOCOL["action_limit_mps2"])
TRANSITIONS = 20_000
SAMPLE_RATE_HZ = 1_000.0


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def resolved(path: str | Path) -> Path:
    return Path(path).resolve(strict=True)


def notch_coefficients(center_hz: float) -> tuple[np.ndarray, np.ndarray]:
    w0 = 2.0 * np.pi * center_hz / FS_HZ
    alpha = np.sin(w0) / (2.0 * Q)
    scale = 1.0 + alpha
    b = np.array([1.0, -2.0 * np.cos(w0), 1.0], dtype=np.float64) / scale
    a = np.array([1.0, -2.0 * np.cos(w0) / scale, (1.0 - alpha) / scale], dtype=np.float64)
    return b, a


def section_step(x: np.ndarray, b: np.ndarray, a: np.ndarray, state: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    # State columns: x[n-1], x[n-2], y[n-1], y[n-2].
    y = b[0] * x + b[1] * state[:, 0] + b[2] * state[:, 1] - a[1] * state[:, 2] - a[2] * state[:, 3]
    next_state = np.column_stack((x, state[:, 0], y, state[:, 2]))
    return y, next_state


def dual_notch_event_replay(action: np.ndarray, event: np.ndarray) -> tuple[np.ndarray, int]:
    b1, a1 = notch_coefficients(NOTCHES[0])
    b2, a2 = notch_coefficients(NOTCHES[1])
    state1 = np.zeros((3, 4), dtype=np.float64)
    state2 = np.zeros((3, 4), dtype=np.float64)
    output = np.zeros_like(action)
    held = np.zeros(3, dtype=np.float64)
    initialized = False
    clip_count = 0

    for k in range(action.shape[0]):
        if event[k]:
            x = action[k]
            if not initialized and np.max(np.abs(x)) > 1e-12:
                # Unity-DC initialization at the first observed nonzero action.
                state1[:] = x[:, None]
                state2[:] = x[:, None]
                held = x.copy()
                initialized = True
            elif initialized:
                y1, state1 = section_step(x, b1, a1, state1)
                y2, state2 = section_step(y1, b2, a2, state2)
                clipped = np.clip(y2, -ACTION_LIMIT, ACTION_LIMIT)
                clip_count += int(np.count_nonzero(np.abs(clipped - y2) > 1e-12))
                held = clipped
            else:
                # Preserve an exact zero warm-up until the first nonzero action.
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
    frequency = np.fft.rfftfreq(n, d=1.0 / fs_hz)
    selected = (frequency >= low_hz) & (frequency < high_hz)
    df = fs_hz / n
    axis_power = np.sum(psd[selected], axis=0) * df
    return float(np.sqrt(np.sum(axis_power)))


def force_to_euler(acceleration: np.ndarray, yaw: np.ndarray) -> np.ndarray:
    specific = acceleration.copy()
    specific[:, 2] += 9.8
    cy = np.cos(yaw)
    sy = np.sin(yaw)
    a = cy * specific[:, 0] + sy * specific[:, 1]
    b = sy * specific[:, 0] - cy * specific[:, 1]
    roll = np.arctan2(b, np.hypot(specific[:, 2], a))
    pitch = np.arctan2(a, specific[:, 2])
    tilt = np.hypot(roll, pitch)
    over = tilt > (np.pi / 6.0)
    scale = np.ones_like(tilt)
    scale[over] = (np.pi / 6.0) / tilt[over]
    return np.column_stack((roll * scale, pitch * scale))


def pct_reduction(before: float, after: float) -> float:
    return 100.0 * (before - after) / before if before > 1e-15 else 0.0


def replay_case(study_name: str, expected_scene: str) -> dict:
    study = ROOT / "experiments" / "dl_attitude_replacement_20261028" / study_name
    binding_path = study / "TRAIN_SCENE_BINDING_v1.json"
    binding = read_json(binding_path)
    if binding["selected_scene_id"] != expected_scene or binding["source_split"] != "TRAIN_C5_24 (canonical ID prefix DEV)":
        raise RuntimeError(f"Wrong physical TRAIN scene binding: {study_name}")
    if binding["fold_id"] != "holdout_W06_10" or expected_scene in binding["fold_train_scene_ids"] or expected_scene not in binding["fold_holdout_scene_ids"]:
        raise RuntimeError(f"The selected scene is not held out by holdout_W06_10: {expected_scene}")

    parent_manifest_path = resolved(binding["parent_cosine_manifest_path"])
    parent_manifest = read_json(parent_manifest_path)
    parent_rows = [row for row in parent_manifest["records"] if row.get("scene_id") == expected_scene]
    if len(parent_rows) != 1:
        raise RuntimeError(f"Parent manifest does not have one exact TRAIN row: {expected_scene}")
    parent_raw_from_manifest = resolved(parent_rows[0]["candidate_raw_path"])
    parent_raw_from_binding = resolved(binding["parent_raw_path"])
    if parent_raw_from_manifest != parent_raw_from_binding:
        raise RuntimeError(f"Parent raw path differs between binding and manifest: {expected_scene}")

    source_records = {
        "B": (binding["b72_scoring_raw_path"], binding["b72_scoring_raw_sha256"]),
        "C5": (binding["c5_raw_path"], binding["c5_raw_sha256"]),
        "parent": (binding["parent_raw_path"], binding["parent_raw_sha256"]),
    }
    source_audit = {}
    for name, (path_text, expected_sha) in source_records.items():
        path = resolved(path_text)
        actual_sha = sha256(path)
        if actual_sha.lower() != str(expected_sha).lower():
            raise RuntimeError(f"Bound {name} TRAIN raw SHA mismatch for {expected_scene}")
        source_audit[name] = {"raw_path": str(path), "raw_sha256": actual_sha}

    status_path = study / "runs" / expected_scene / "attempt_01" / "run_status.json"
    status = read_json(status_path)
    if (status.get("state") != "COMPLETED" or status.get("scene_id") != expected_scene or
            status.get("transitions") != TRANSITIONS or status.get("state_samples") != TRANSITIONS + 1 or
            status.get("Plant_calls") != 1 or status.get("TEST_read") is True):
        raise RuntimeError(f"Candidate run status is not the expected completed single TRAIN scene: {expected_scene}")
    candidate_raw = resolved(status["raw_path"])
    if candidate_raw != resolved(study / "runs" / expected_scene / "attempt_01" / "raw_run.mat"):
        raise RuntimeError(f"Candidate raw path is outside the exact attempt directory: {expected_scene}")
    candidate_sha = sha256(candidate_raw)
    if candidate_sha.lower() != str(status["raw_sha256"]).lower():
        raise RuntimeError(f"Candidate raw/status hash mismatch for {expected_scene}")

    with h5py.File(candidate_raw, "r") as raw:
        log = raw["log"]
        read_log = lambda key: np.asarray(log[key][()], dtype=np.float64).T
        action = read_log("stage1_position_held_applied_acceleration_mps2")
        nominal_acc = read_log("position_nominal_acceleration_mps2")
        nominal_force = read_log("position_bs_nominal_force_N")
        commanded_force = read_log("position_commanded_force_N")
        injected_force = read_log("stage1_position_injected_force_I_N")
        target = read_log("command_filter_target_euler")
        state = read_log("state")
        event = np.asarray(log["stage1_position_event"][()], dtype=bool).reshape(-1)

    if action.shape != (TRANSITIONS, 3) or target.shape != (TRANSITIONS, 3) or state.shape[0] != TRANSITIONS + 1:
        raise RuntimeError(f"Unexpected MATLAB log shapes for {expected_scene}")
    event_indices = np.flatnonzero(event)
    if len(event_indices) != 1999 or not np.all(np.diff(event_indices) == 10):
        raise RuntimeError(f"Stage-1 event clock is not the locked 100-Hz schedule for {expected_scene}")

    ratio_mask = np.abs(nominal_acc) > 1e-7
    mass = float(np.median(nominal_force[ratio_mask] / nominal_acc[ratio_mask]))
    nominal_force_residual = float(np.max(np.abs(nominal_force - mass * nominal_acc)))
    injected_force_residual = float(np.max(np.abs(injected_force - mass * action)))
    commanded_force_residual = float(np.max(np.abs(commanded_force - (nominal_force - injected_force))))
    if nominal_force_residual > 1e-8 or injected_force_residual > 1e-8 or commanded_force_residual > 1e-8:
        raise RuntimeError(f"Logged force/action chain is not a simple stage-1 injection for {expected_scene}")

    base_acc = commanded_force / mass
    yaw = state[:TRANSITIONS, 8]
    reconstructed_roll_pitch = force_to_euler(base_acc, yaw)
    target_reconstruction_error = np.arctan2(
        np.sin(reconstructed_roll_pitch - target[:, :2]),
        np.cos(reconstructed_roll_pitch - target[:, :2]),
    )
    max_target_reconstruction_error = float(np.max(np.abs(target_reconstruction_error)))
    if max_target_reconstruction_error > float(PROTOCOL["frozen_replay_pass_conditions"]["baseline_command_target_reconstruction_max_abs_rad"]):
        raise RuntimeError(f"Baseline command reconstruction failed for {expected_scene}: {max_target_reconstruction_error}")

    filtered_action, clip_count = dual_notch_event_replay(action, event)
    candidate_acc = base_acc + action - filtered_action
    candidate_roll_pitch = force_to_euler(candidate_acc, yaw)
    candidate_target = target.copy()
    candidate_target[:, :2] = candidate_roll_pitch

    bands = {"1p5_2p5_hz": (1.5, 2.5), "2p5_3p5_hz": (2.5, 3.5)}
    high_frequency = {}
    for band_name, (low, high) in bands.items():
        before = vector_band_rms(target, SAMPLE_RATE_HZ, low, high) * 1e3
        after = vector_band_rms(candidate_target, SAMPLE_RATE_HZ, low, high) * 1e3
        action_before = vector_band_rms(action, SAMPLE_RATE_HZ, low, high)
        action_after = vector_band_rms(filtered_action, SAMPLE_RATE_HZ, low, high)
        high_frequency[band_name] = {
            "command_target_before_mrad": before,
            "command_target_after_frozen_replay_mrad": after,
            "command_target_reduction_percent": pct_reduction(before, after),
            "stage1_action_before_mps2": action_before,
            "stage1_action_after_mps2": action_after,
            "stage1_action_reduction_percent": pct_reduction(action_before, action_after),
        }

    low_action_before = vector_band_rms(action, SAMPLE_RATE_HZ, 0.05, 0.5)
    low_action_delta = vector_band_rms(filtered_action - action, SAMPLE_RATE_HZ, 0.05, 0.5)
    low_target_before = vector_band_rms(target, SAMPLE_RATE_HZ, 0.05, 0.5)
    low_target_delta = vector_band_rms(candidate_target - target, SAMPLE_RATE_HZ, 0.05, 0.5)
    low_action_delta_pct = 100.0 * low_action_delta / max(low_action_before, 1e-15)
    low_target_delta_pct = 100.0 * low_target_delta / max(low_target_before, 1e-15)

    return {
        "scene_id": expected_scene,
        "split": "TRAIN_C5_24",
        "fold_id": binding["fold_id"],
        "binding_path": str(binding_path.resolve()),
        "binding_sha256": sha256(binding_path),
        "parent_manifest_path": str(parent_manifest_path),
        "parent_manifest_scene_row_count": len(parent_rows),
        "source_raws": source_audit,
        "candidate_raw_path": str(candidate_raw),
        "candidate_raw_sha256": candidate_sha,
        "transitions": TRANSITIONS,
        "state_samples": TRANSITIONS + 1,
        "event_count": int(len(event_indices)),
        "event_stride_samples": int(np.median(np.diff(event_indices))),
        "derived_mass_kg": mass,
        "baseline_force_chain_max_abs_residual_N": max(nominal_force_residual, injected_force_residual, commanded_force_residual),
        "baseline_target_reconstruction_max_abs_error_rad": max_target_reconstruction_error,
        "action_limit_clip_count": clip_count,
        "high_frequency": high_frequency,
        "low_frequency": {
            "band_hz": [0.05, 0.5],
            "stage1_action_before_mps2": low_action_before,
            "stage1_action_delta_mps2": low_action_delta,
            "stage1_action_delta_percent_of_before": low_action_delta_pct,
            "command_target_before_mrad": low_target_before * 1e3,
            "command_target_delta_mrad": low_target_delta * 1e3,
            "command_target_delta_percent_of_before": low_target_delta_pct,
        },
    }


def main() -> None:
    if OUT.exists():
        raise RuntimeError(f"Refusing to overwrite {OUT}")
    results = [replay_case(*case) for case in CASES]
    limits = PROTOCOL["frozen_replay_pass_conditions"]
    passed = True
    for row in results:
        passed &= row["baseline_target_reconstruction_max_abs_error_rad"] <= limits["baseline_command_target_reconstruction_max_abs_rad"]
        passed &= row["action_limit_clip_count"] <= limits["action_limit_clip_count_max"]
        passed &= row["low_frequency"]["stage1_action_delta_percent_of_before"] <= limits["low_band_action_delta_rms_percent_max_0p05_0p5_hz"]
        passed &= row["low_frequency"]["command_target_delta_percent_of_before"] <= limits["low_band_command_target_delta_rms_percent_max_0p05_0p5_hz"]
        for band in row["high_frequency"].values():
            passed &= band["command_target_reduction_percent"] >= limits["command_target_rms_reduction_percent_min_each_1p5_2p5_and_2p5_3p5_hz"]

    report = {
        "schema": "POSITION_COMPENSATION_DUAL_NOTCH_TRAIN_FROZEN_REPLAY_V1",
        "status": "PASS_FIXED_FROZEN_REPLAY" if passed else "FAIL_FIXED_FROZEN_REPLAY",
        "scope": "Two exact physical TRAIN_C5_24 W09 scenes; frozen logged trajectory only.",
        "filter": {
            "event_sample_rate_hz": FS_HZ,
            "notch_centers_hz": list(NOTCHES),
            "quality_factor_each": Q,
            "b_a_coefficients": {str(f): {"b": notch_coefficients(f)[0].tolist(), "a": notch_coefficients(f)[1].tolist()} for f in NOTCHES},
            "update_rule": "Stage-1 event updates at 100 Hz; zero-order hold between events.",
            "state_initialization": "Initialize at first nonzero action event to preserve the observed action value.",
            "scope": "Filter final stage-1 applied position compensation only; nominal acceleration, yaw and shared command filter unchanged.",
            "action_limit_mps2": ACTION_LIMIT,
        },
        "predeclared_protocol_path": str((HERE / "PREDECLARED_PROTOCOL_v1.json").resolve()),
        "predeclared_protocol_sha256": sha256(HERE / "PREDECLARED_PROTOCOL_v1.json"),
        "results": results,
        "plant_called_by_this_replay": False,
        "TEST_read": False,
        "inertia_reconstruction_enabled": False,
        "parameter_sweep": False,
        "interpretation": "This is a same-trajectory command-chain screen. It does not predict closed-loop actual-attitude or position-error changes and does not establish cross-wind generalization.",
    }
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(OUT.resolve()), "status": report["status"], "results": [
        {"scene_id": r["scene_id"], "high_frequency": r["high_frequency"], "low_frequency": r["low_frequency"], "clips": r["action_limit_clip_count"]}
        for r in results
    ]}, indent=2))


if __name__ == "__main__":
    main()
