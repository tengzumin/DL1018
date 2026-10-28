"""Same-trace output-filter replay on the locked delayed-start HF6 raws.

This is an offline signal replay, not a closed-loop counterfactual.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import h5py
import numpy as np
from scipy.spatial.transform import Rotation


HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
SCORE = HERE / "ROOT_HF6_SCORE_v1.json"
OUT_JSON = HERE / "ROOT_STAGE1_COMPENSATION_LPF_REPLAY_HF6_v1.json"
OUT_MD = HERE / "ROOT_STAGE1_COMPENSATION_LPF_REPLAY_HF6_v1.md"
DT = 0.001
EVENT_DT = 0.01
GRAVITY = 9.8
MAX_TILT = np.pi / 6
TAU_OLD = 1 / 18
TAU_NEW = 0.1
METHOD = "Delayed_Start_Candidate"
SOURCE_FILES = (
    STUDY / "candidate_runner_work" / "matlab" / "core" / "command_filter_step.m",
    STUDY / "candidate_runner_work" / "matlab" / "core" / "baseline_force_to_attitude.m",
    STUDY / "candidate_runner_work" / "matlab" / "runtime" / "run_gate_holdout_closed_loop.m",
)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def wrap(a: np.ndarray) -> np.ndarray:
    return np.arctan2(np.sin(a), np.cos(a))


def lowpass_1ms(x: np.ndarray, tau: float) -> np.ndarray:
    y = np.empty_like(x)
    y[0] = x[0]
    alpha = np.exp(-DT / tau)
    for k in range(1, len(x)):
        y[k] = alpha * y[k - 1] + (1 - alpha) * x[k]
    return y


def lowpass_events(x: np.ndarray, events: np.ndarray, tau: float) -> np.ndarray:
    """Update at 100 Hz inference events and hold between events."""
    y = np.empty_like(x)
    y[0] = x[0]
    alpha = np.exp(-EVENT_DT / tau)
    held = y[0].copy()
    for k in range(1, len(x)):
        if events[k]:
            held = alpha * held + (1 - alpha) * x[k]
        y[k] = held
    return y


def target_euler(command_accel: np.ndarray, yaw_state: np.ndarray,
                 yaw_reference: np.ndarray) -> np.ndarray:
    specific = command_accel.copy()
    specific[:, 2] += GRAVITY
    a = np.cos(yaw_state) * specific[:, 0] + np.sin(yaw_state) * specific[:, 1]
    b = np.sin(yaw_state) * specific[:, 0] - np.cos(yaw_state) * specific[:, 1]
    roll = np.arctan2(b, np.hypot(specific[:, 2], a))
    pitch = np.arctan2(a, specific[:, 2])
    tilt = np.hypot(roll, pitch)
    scale = np.minimum(1, MAX_TILT / np.maximum(tilt, np.finfo(float).eps))
    return np.column_stack((roll * scale, pitch * scale, yaw_reference))


def task_euler(reference_accel: np.ndarray, yaw: np.ndarray) -> np.ndarray:
    acc = reference_accel.copy()
    acc[:, 2] += GRAVITY
    a = np.cos(yaw) * acc[:, 0] + np.sin(yaw) * acc[:, 1]
    b = np.sin(yaw) * acc[:, 0] - np.cos(yaw) * acc[:, 1]
    roll = np.arctan2(b, np.hypot(acc[:, 2], a))
    pitch = np.arctan2(a, acc[:, 2])
    scale = np.minimum(1, MAX_TILT / np.maximum(np.hypot(roll, pitch), np.finfo(float).eps))
    return np.column_stack((roll * scale, pitch * scale, yaw))


def command_filter(target: np.ndarray, initial_euler: np.ndarray) -> np.ndarray:
    """Replay the frozen 1-ms second-order command filter."""
    wn = np.array([18.0, 18.0, 12.0])
    rate = np.zeros(3)
    euler = initial_euler.copy()
    out = np.empty_like(target)
    for k in range(len(target)):
        out[k] = euler
        error = wrap(target[k] - euler)
        requested = wn**2 * error - 2 * wn * rate
        acceleration = np.clip(requested, [-np.inf, -np.inf, -6], [np.inf, np.inf, 6])
        rate += DT * acceleration
        euler = wrap(euler + DT * rate)
    return out


def geodesic_rmse(a: np.ndarray, b: np.ndarray) -> float:
    angle = (Rotation.from_euler("xyz", a).inv() * Rotation.from_euler("xyz", b)).magnitude()
    return float(np.sqrt(np.mean(angle**2)))


def rms_norm(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.sum(x**2, axis=1))))


def filter_response(tau: float, fs: float, frequency: float) -> dict:
    """Discrete one-pole response including the output's zero-order hold."""
    alpha = np.exp(-1 / (fs * tau))
    omega = 2 * np.pi * frequency / fs
    recurrence = (1 - alpha) / (1 - alpha * np.exp(-1j * omega))
    hold = np.sinc(frequency / fs) * np.exp(-1j * np.pi * frequency / fs)
    total = recurrence * hold
    return {"gain": float(abs(total)), "gain_db": float(20 * np.log10(abs(total))),
            "phase_deg": float(np.degrees(np.angle(total)))}


def score_scene(row: dict) -> dict:
    sid = row["scene_id"]
    method = row["methods"][METHOD]
    base_method = row["methods"]["B"]
    candidate_path, b_path = Path(method["raw_path"]), Path(base_method["raw_path"])
    if sha(candidate_path).lower() != method["raw_sha256"].lower():
        raise RuntimeError(f"candidate raw hash mismatch: {sid}")
    if sha(b_path).lower() != base_method["raw_sha256"].lower():
        raise RuntimeError(f"B raw hash mismatch: {sid}")

    with h5py.File(candidate_path, "r") as f:
        log = f["log"]
        state = np.asarray(log["state"][()], dtype=float).T
        transition_time = np.asarray(log["transition_time"][()], dtype=float).reshape(-1)
        compensation = np.asarray(log["stage1_position_held_applied_acceleration_mps2"][()], dtype=float).T
        compensation_force = np.asarray(log["stage1_position_held_force_I_N"][()], dtype=float).T
        command_force = np.asarray(log["position_commanded_force_N"][()], dtype=float).T
        target_logged = np.asarray(log["command_filter_target_euler"][()], dtype=float).T
        filtered_logged = np.asarray(log["filtered_attitude_reference"][()], dtype=float).T
        inference_event = np.asarray(log["stage1_position_event_inference_valid"][()], dtype=bool).reshape(-1)
        ref_acc = np.asarray(f["scene/reference/acceleration"][()], dtype=float).T
        ref_yaw = np.asarray(f["scene/reference/yaw"][()], dtype=float).reshape(-1)
        run_identity = f["runIdentity"]
        logged_wn = np.asarray(run_identity["command_filter_wn_rad_s"][()], dtype=float).reshape(-1)

    n = len(transition_time)
    if n != 20000 or compensation.shape != (n, 3) or inference_event.shape != (n,):
        raise RuntimeError(f"unexpected transition log shape: {sid}")
    if bool(np.any(~np.isfinite(compensation))) or bool(np.any(~np.isfinite(command_force))):
        raise RuntimeError(f"non-finite trace: {sid}")
    if not np.allclose(logged_wn, [18, 18, 12], atol=1e-12, rtol=0):
        raise RuntimeError(f"command-filter configuration mismatch: {sid}")

    initial_compensation = compensation[0].copy()
    if not np.array_equal(initial_compensation, np.zeros(3)):
        raise RuntimeError(f"initial compensation is not zero: {sid}")
    valid_events = np.flatnonzero(inference_event)
    first_event = int(valid_events[0]) if len(valid_events) else None
    if first_event is None or not np.isclose(transition_time[first_event], 0.32, atol=1e-12):
        raise RuntimeError(f"unexpected first valid event time: {sid}")
    event_intervals = np.diff(transition_time[valid_events])
    if len(event_intervals) < 1 or np.max(np.abs(event_intervals - EVENT_DT)) > 1e-12:
        raise RuntimeError(f"Stage1 inference events are not spaced at 100 Hz: {sid}")

    nonzero = np.abs(compensation) > 1e-9
    mass_values = compensation_force[nonzero] / compensation[nonzero]
    mass = float(np.median(mass_values))
    if np.max(np.abs(mass_values - mass)) > 1e-12:
        raise RuntimeError(f"inconsistent mass ratio in force/acceleration logs: {sid}")
    command_accel = command_force / mass
    yaw_state = state[:n, 8]
    task = task_euler(ref_acc[:n], ref_yaw[:n])

    rebuilt_target = target_euler(command_accel, yaw_state, ref_yaw[:n])
    target_rebuild_error = float(np.max(np.abs(wrap(rebuilt_target - target_logged))))
    original_filter_replay = command_filter(target_logged, state[0, 6:9])
    filter_replay_error = float(np.max(np.abs(wrap(original_filter_replay - filtered_logged))))
    if target_rebuild_error > 1e-10 or filter_replay_error > 1e-10:
        raise RuntimeError(f"frozen target/filter replay parity failed: {sid}")

    fc_1ms = lowpass_1ms(compensation, TAU_OLD)
    tau_1ms = lowpass_1ms(compensation, TAU_NEW)
    tau_event = lowpass_events(compensation, inference_event, TAU_NEW)
    next_event = int(valid_events[1])
    event_output = tau_event[first_event]
    match = np.flatnonzero(np.linalg.norm(tau_1ms[first_event:next_event] - event_output, axis=1) < 1e-12)
    if not len(match):
        raise RuntimeError(f"could not verify event/1-ms first-response timing: {sid}")
    match_index = first_event + int(match[0])
    traces = {"raw": compensation, "fc18_over_2pi_1ms": fc_1ms,
              "tau_0p1_1ms": tau_1ms, "tau_0p1_event100hz": tau_event}
    output = {}
    for name, filtered_comp in traces.items():
        output[name] = {"compensation_rms_mps2": rms_norm(filtered_comp)}
        if name == "raw":
            output[name]["task_to_logged_filtered_reference_rad"] = geodesic_rmse(task, filtered_logged)
        else:
            replay_command_accel = command_accel + compensation - filtered_comp
            new_target = target_euler(replay_command_accel, yaw_state, ref_yaw[:n])
            new_filtered_ref = command_filter(new_target, state[0, 6:9])
            output[name]["task_to_replayed_filtered_reference_rad"] = geodesic_rmse(task, new_filtered_ref)
            output[name]["command_accel_delta_rms_mps2"] = rms_norm(compensation - filtered_comp)
            output[name]["compensation_delta_rms_mps2"] = rms_norm(compensation - filtered_comp)

    with h5py.File(b_path, "r") as f:
        b_filtered = np.asarray(f["log/filtered_attitude_reference"][()], dtype=float).T[:n]
    b_task = geodesic_rmse(task, b_filtered)
    first_input = compensation[first_event].copy()
    result = {
        "scene_id": sid, "split": row["split"], "candidate_raw_path": str(candidate_path),
        "candidate_raw_sha256": method["raw_sha256"], "B_raw_path": str(b_path),
        "B_raw_sha256": base_method["raw_sha256"], "mass_derived_from_logged_force_over_acceleration_kg": mass,
        "initial_compensation_at_t0_mps2": initial_compensation.tolist(),
        "first_valid_event_index": first_event, "first_valid_event_time_s": float(transition_time[first_event]),
        "first_valid_event_raw_compensation_mps2": first_input.tolist(),
        "first_valid_event_filter_output_mps2": {
            "fc18_over_2pi_1ms": fc_1ms[first_event].tolist(),
            "tau_0p1_1ms": tau_1ms[first_event].tolist(),
            "tau_0p1_event100hz": tau_event[first_event].tolist(),
        },
        "tau_0p1_1ms_first_matching_event_response_time_s": float(transition_time[match_index]),
        "tau_0p1_event100hz_lead_over_1ms_curve_s": float(transition_time[match_index] - transition_time[first_event]),
        "target_reconstruction_max_error_rad": target_rebuild_error,
        "original_command_filter_replay_max_error_rad": filter_replay_error,
        "B_task_to_logged_filtered_reference_rad": b_task,
        "signals": output,
        "between_tau_event100hz_and_tau_1ms_rms_mps2": rms_norm(tau_event - tau_1ms),
    }
    return result


def make_result() -> dict:
    score = read_json(SCORE)
    if (score.get("status") != "COMPLETE_HF6_SCREEN" or score.get("completed_scene_count") != 6
            or score.get("TEST_read") is not False or score.get("inertia_reconstruction") is not False):
        raise RuntimeError("HF6 score scope/status is not the expected complete DEV/VAL screen")
    rows = score["scene_results"]
    if len(rows) != 6 or any("TEST" in r["scene_id"] for r in rows):
        raise RuntimeError("expected exactly six non-TEST scenes")
    constants = score["metric_constants"]
    if float(constants["gravity_mps2"]) != GRAVITY or abs(float(constants["max_tilt_rad"]) - MAX_TILT) > 1e-12:
        raise RuntimeError("frozen score constants differ from replay")
    results = [score_scene(r) for r in rows]

    signals = ("raw", "fc18_over_2pi_1ms", "tau_0p1_1ms", "tau_0p1_event100hz")
    summary = {}
    for signal in signals:
        rms_key = "compensation_rms_mps2"
        task_key = ("task_to_logged_filtered_reference_rad" if signal == "raw"
                    else "task_to_replayed_filtered_reference_rad")
        means = {
            "mean_scene_compensation_rms_mps2": float(np.mean([r["signals"][signal][rms_key] for r in results])),
            "mean_scene_task_to_filtered_reference_rad": float(np.mean([r["signals"][signal][task_key] for r in results])),
            "mean_scene_command_accel_delta_rms_mps2": (0.0 if signal == "raw" else
                float(np.mean([r["signals"][signal]["command_accel_delta_rms_mps2"] for r in results]))),
        }
        ratios = [r["signals"][signal][rms_key] / r["signals"]["raw"][rms_key] for r in results]
        means["mean_scene_compensation_rms_ratio_vs_raw"] = float(np.mean(ratios))
        means["ratio_of_macro_mean_rms_vs_raw"] = (means["mean_scene_compensation_rms_mps2"] /
            summary.get("raw", {}).get("mean_scene_compensation_rms_mps2", means["mean_scene_compensation_rms_mps2"]))
        means["delta_task_vs_B_mrad"] = 1000 * (means["mean_scene_task_to_filtered_reference_rad"] -
            float(np.mean([r["B_task_to_logged_filtered_reference_rad"] for r in results])))
        means["candidate_scene_wins_vs_B"] = sum(r["signals"][signal][task_key] < r["B_task_to_logged_filtered_reference_rad"] for r in results)
        summary[signal] = means

    freq_response = {}
    for freq in (0.5, 1.0, 18 / (2 * np.pi), 5.0, 10.0):
        freq_response[f"{freq:.6g}_Hz"] = {
            "fc18_over_2pi_1ms": filter_response(TAU_OLD, 1 / DT, freq),
            "tau_0p1_1ms": filter_response(TAU_NEW, 1 / DT, freq),
            "tau_0p1_event100hz": filter_response(TAU_NEW, 1 / EVENT_DT, freq),
        }
    return {
        "schema": "DL1018_STAGE1_COMPENSATION_LPF_SAME_TRACE_REPLAY_HF6_V1",
        "status": "COMPLETE_SAME_TRACE_REPLAY_NOT_CLOSED_LOOP",
        "scope": "Six existing DEV/VAL HF6 candidate raws, paired with same-scene B; no TEST, Plant, training, or inertia reconstruction.",
        "same_trace_replay": True, "closed_loop_result": False,
        "TEST_read": False, "Plant_calls_by_replay": 0, "training_runs_by_replay": 0,
        "inertia_reconstruction": False, "scene_count": len(results),
        "input_score_path": str(SCORE), "input_score_sha256": sha(SCORE),
        "replay_script_path": str(Path(__file__).resolve()), "replay_script_sha256": sha(Path(__file__).resolve()),
        "source_bindings": [{"path": str(p), "sha256": sha(p)} for p in SOURCE_FILES],
        "filter_definitions": {
            "existing_fc18_over_2pi_1ms": {"type": "one-pole exponential ZOH at 1 kHz", "fc_hz": 18 / (2 * np.pi), "tau_s": TAU_OLD, "alpha_1ms": float(np.exp(-DT / TAU_OLD))},
            "proposed_tau0p1_1ms_curve": {"type": "one-pole exponential ZOH at 1 kHz", "tau_s": TAU_NEW, "fc_hz": 1 / (2 * np.pi * TAU_NEW), "alpha_1ms": float(np.exp(-DT / TAU_NEW))},
            "proposed_tau0p1_event100hz": {"type": "one-pole exponential update at valid Stage1 inference events; zero-order hold between events", "tau_s": TAU_NEW, "event_period_s": EVENT_DT, "fc_hz": 1 / (2 * np.pi * TAU_NEW), "alpha_event": float(np.exp(-EVENT_DT / TAU_NEW))},
            "initialization": "filter state equals first raw compensation sample; verified [0,0,0] m/s^2 in all six scenes. The first nonzero Stage1 inference event occurs at 0.320 s and has nonzero raw output.",
        },
        "first_event_update_coefficients": {
            "fc18_over_2pi_1ms": float(1 - np.exp(-DT / TAU_OLD)),
            "tau_0p1_1ms": float(1 - np.exp(-DT / TAU_NEW)),
            "tau_0p1_event100hz": float(1 - np.exp(-EVENT_DT / TAU_NEW)),
        },
        "frequency_response_including_output_hold": freq_response,
        "summary_equal_scene_means": summary,
        "B_mean_task_to_filtered_reference_rad": float(np.mean([r["B_task_to_logged_filtered_reference_rad"] for r in results])),
        "tau_event_vs_tau_1ms_rms_difference_mean_mps2": float(np.mean([r["between_tau_event100hz_and_tau_1ms_rms_mps2"] for r in results])),
        "position_closure_risk": {
            "metric": "RMS of command-acceleration perturbation on the unchanged recorded state trajectory, equal to raw Stage1 compensation minus filtered compensation.",
            "position_Q_recomputed": False,
            "interpretation": "Changing this outer-loop force changes future position states and commands; same-trace results cannot predict closed-loop Q.",
        },
        "scene_results": results,
    }


def write_markdown(result: dict) -> None:
    lines = ["# Stage1 compensation low-pass replay on HF6", "",
             "Same-trace DEV/VAL replay only; this is not a changed-state closed-loop result. No TEST, Plant, training, or inertia reconstruction.", "",
             "The raw compensation is exactly zero at t=0 in all six scenes. The first valid Stage1 inference event is at 0.320 s and is nonzero. Thus initialization at the first sample is zero; the first active event is not zero.", "",
             "| Replay | Mean compensation RMS (m/s²) | Mean ideal-inner task→filtered (mrad) | Δ vs B (mrad) | Scenes better than B | Mean command-accel perturbation RMS (m/s²) |",
             "|---|---:|---:|---:|---:|---:|"]
    labels = {"raw": "raw", "fc18_over_2pi_1ms": "fc=18/(2π) Hz, 1-ms", "tau_0p1_1ms": "τ=0.1 s, 1-ms curve", "tau_0p1_event100hz": "τ=0.1 s, 100-Hz update + hold"}
    for key, label in labels.items():
        x = result["summary_equal_scene_means"][key]
        lines.append(f"| {label} | {x['mean_scene_compensation_rms_mps2']:.6f} | {1000*x['mean_scene_task_to_filtered_reference_rad']:.3f} | {x['delta_task_vs_B_mrad']:+.3f} | {x['candidate_scene_wins_vs_B']}/6 | {x['mean_scene_command_accel_delta_rms_mps2']:.6f} |")
    lines.extend(["", f"B mean task→logged-filtered-reference: {1000*result['B_mean_task_to_filtered_reference_rad']:.3f} mrad.",
                  f"First-event coefficients: old 1-ms={result['first_event_update_coefficients']['fc18_over_2pi_1ms']:.5f}; τ=0.1 1-ms={result['first_event_update_coefficients']['tau_0p1_1ms']:.5f}; τ=0.1 100-Hz={result['first_event_update_coefficients']['tau_0p1_event100hz']:.5f}.",
                  "The 100-Hz recurrence applies a larger update at the event and holds it between events. It is not pointwise equivalent to the 1-ms curve; the first-event responses differ, and the event-based output leads the gradual 1-ms rise by nearly one event interval.",
                  "The conditional task estimate freezes the recorded position/state trajectory, recalculates the outer-loop target from the filtered compensation, and replays the original attitude command filter. It assumes perfect inner tracking of that replayed filter output.",
                  "Position Q was not recomputed. The command-acceleration perturbation shows the position-loop path can change, so none of these conditional task numbers predicts closed-loop position or attitude performance.", ""])
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    if OUT_JSON.exists() or OUT_MD.exists():
        raise RuntimeError("refusing to overwrite an existing replay artifact")
    result = make_result()
    # Minimal executable self-checks for the high-risk replay alignment and init.
    assert result["scene_count"] == 6
    assert max(r["target_reconstruction_max_error_rad"] for r in result["scene_results"]) < 1e-10
    assert max(r["original_command_filter_replay_max_error_rad"] for r in result["scene_results"]) < 1e-10
    assert all(np.array_equal(r["initial_compensation_at_t0_mps2"], [0, 0, 0]) for r in result["scene_results"])
    OUT_JSON.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_markdown(result)
    print(json.dumps({"status": result["status"], "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))


if __name__ == "__main__":
    main()
