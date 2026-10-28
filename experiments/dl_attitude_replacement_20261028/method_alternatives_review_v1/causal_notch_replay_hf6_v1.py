"""Causal 3.5-Hz/Q=1 notch replay on six locked C5 traces; no Plant."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import h5py
import numpy as np
from scipy.signal import freqz, iirnotch, lfilter
from scipy.spatial.transform import Rotation


ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
SCORE = ROOT / "experiments/dl_attitude_replacement_20261028/gru_prediction_tau01_v1/audits/GRU_PREDICTION_TAU01_SCORE_final12.json"
OUT_JSON = HERE / "CAUSAL_NOTCH_C5_SAME_TRACE_HF6_FINAL_v1.json"
OUT_MD = HERE / "CAUSAL_NOTCH_C5_SAME_TRACE_HF6_FINAL_v1.md"
SCORE_SHA256 = "132ac1ccf86f3c2b51a4c89eaebdb23170f62598205e7ce7072a6a7e47759fcb"
HISTORICAL_NOTCH_STATE = ROOT / "experiments/dl_attitude_replacement_20261027/mlp15_nominal_residual_v1/CONTINUATION_STATE_v2.json"
HISTORICAL_NOTCH_STATE_SHA256 = "bb03724bb6a4c4633f13d153d53c597f983c055fa0962383ce1ec12cecccdeef"
LOCKED_FILES = {
    "experiments/b_traceable_c3core_dev72_20261023/B_TRACEABLE_DEV72_INPUT_LOCK_v3.json": "8d738e5c70ba2fc8697550549d1a0537f08eadb49b99bc5684e5c26f6222f452",
    "experiments/position_axis_coordinate_c5_dev72_20261023/C5_DEV72_INPUT_LOCK_v3.json": "82024c01276cc4bfbd9b7772cf5332dee3fdfcbed422969589b68f1c90ed2d75",
    "experiments/position_axis_coordinate_c5_dev72_20261023/run_dl1018_closed_loop.m": "48350037b66efe00301b138068f187c62cf92583f0f9ba2fabc9b24f248a963c",
    "matlab/core/baseline_force_to_attitude.m": "ef42d1d08af24ed82da307a4d886b0c205e28e754177765a2584e3e9bb0cd039",
    "matlab/core/command_filter_step.m": "15c7eb27162e1971a1164304830f4afd3af35eb9bd709291e969dbfefd0d262b",
    "matlab/core/default_config.m": "685abb7b72a335fdc826673e6431098fe79af88409f17b1b70ce08edb214dc51",
}
SCENES = (
    "DL1018_DEV_T1_C10_W09",
    "DL1018_DEV_T2_C09_W10",
    "DL1018_DEV_T3_C09_W09",
    "DL1018_VAL_T1_C07_W14",
    "DL1018_VAL_T2_C04_W14",
    "DL1018_VAL_T3_C01_W14",
)
DT = 0.001
EVENT_DT = 0.01
FS_EVENT = 1.0 / EVENT_DT
MASS = 0.695
G = 9.8
MAX_TILT = np.pi / 6
F0_HZ = 3.5
Q = 1.0
BANDS = ((0.0, 1.0), (1.0, 2.0), (2.0, 5.0), (5.0, 15.0))


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def arr3(group: h5py.Group, name: str, n: int) -> np.ndarray:
    x = np.asarray(group[name][()], dtype=float)
    if x.shape == (3, n):
        x = x.T
    if x.shape != (n, 3):
        raise RuntimeError(f"{name}: expected {(n, 3)}, got {x.shape}")
    return x


def wrap(a: np.ndarray) -> np.ndarray:
    return np.arctan2(np.sin(a), np.cos(a))


def target_euler(command_accel: np.ndarray, yaw_state: np.ndarray,
                 yaw_reference: np.ndarray) -> np.ndarray:
    specific = command_accel.copy()
    specific[:, 2] += G
    a = np.cos(yaw_state) * specific[:, 0] + np.sin(yaw_state) * specific[:, 1]
    b = np.sin(yaw_state) * specific[:, 0] - np.cos(yaw_state) * specific[:, 1]
    roll = np.arctan2(b, np.hypot(specific[:, 2], a))
    pitch = np.arctan2(a, specific[:, 2])
    tilt = np.hypot(roll, pitch)
    scale = np.minimum(1.0, MAX_TILT / np.maximum(tilt, np.finfo(float).eps))
    return np.column_stack((roll * scale, pitch * scale, yaw_reference))


def task_euler(reference_accel: np.ndarray, yaw: np.ndarray) -> np.ndarray:
    specific = reference_accel.copy()
    specific[:, 2] += G
    a = np.cos(yaw) * specific[:, 0] + np.sin(yaw) * specific[:, 1]
    b = np.sin(yaw) * specific[:, 0] - np.cos(yaw) * specific[:, 1]
    roll = np.arctan2(b, np.hypot(specific[:, 2], a))
    pitch = np.arctan2(a, specific[:, 2])
    tilt = np.hypot(roll, pitch)
    scale = np.minimum(1.0, MAX_TILT / np.maximum(tilt, np.finfo(float).eps))
    return np.column_stack((roll * scale, pitch * scale, yaw))


def replay_command_filter(target: np.ndarray, initial_euler: np.ndarray) -> np.ndarray:
    wn = np.array([18.0, 18.0, 12.0])
    rate = np.zeros(3)
    euler = initial_euler.copy()
    out = np.empty_like(target)
    for k in range(len(target)):
        out[k] = euler
        error = wrap(target[k] - euler)
        requested = wn**2 * error - 2 * wn * rate
        acceleration = np.clip(requested, [-np.inf, -np.inf, -6.0], [np.inf, np.inf, 6.0])
        rate += DT * acceleration
        euler = wrap(euler + DT * rate)
    return out


def geodesic_rmse(a: np.ndarray, b: np.ndarray) -> float:
    angle = (Rotation.from_euler("xyz", a).inv() * Rotation.from_euler("xyz", b)).magnitude()
    return float(np.sqrt(np.mean(angle**2)))


def event_zoh(event_values: np.ndarray, event_indices: np.ndarray, n: int) -> np.ndarray:
    out = np.zeros((n, 3), dtype=float)
    held = np.zeros(3, dtype=float)
    q = 0
    for k in range(n):
        if q < len(event_indices) and k == event_indices[q]:
            held = event_values[q].copy()
            q += 1
        out[k] = held
    if q != len(event_indices):
        raise RuntimeError("event ZOH failed to consume all event samples")
    return out


def lowpass_event_replay(x: np.ndarray, event_indices: np.ndarray, n: int) -> np.ndarray:
    alpha = 1.0 - np.exp(-EVENT_DT / 0.1)
    state = np.zeros(3)
    values = []
    for idx in event_indices:
        state = state + alpha * (x[idx] - state)
        values.append(state.copy())
    return event_zoh(np.asarray(values), event_indices, n)


def band_power(x: np.ndarray, low: float, high: float) -> float:
    n = len(x)
    spec = np.fft.rfft(x, axis=0)
    f = np.fft.rfftfreq(n, DT)
    weight = np.full(len(f), 2.0)
    weight[0] = 1.0
    if n % 2 == 0:
        weight[-1] = 1.0
    use = (f >= low) & (f < high)
    return float(np.sum(np.abs(spec[use]) ** 2 * weight[use, None]) / n**2)


def band_rms(x: np.ndarray, low: float, high: float) -> float:
    return float(np.sqrt(max(0.0, band_power(x, low, high))))


def cross_power(base: np.ndarray, delta: np.ndarray, low: float, high: float) -> float:
    n = len(base)
    xb, xd = np.fft.rfft(base, axis=0), np.fft.rfft(delta, axis=0)
    f = np.fft.rfftfreq(n, DT)
    weight = np.full(len(f), 2.0)
    weight[0] = 1.0
    if n % 2 == 0:
        weight[-1] = 1.0
    use = (f >= low) & (f < high)
    return float(2.0 * np.sum(np.real(xb[use] * np.conj(xd[use])) * weight[use, None]) / n**2)


def rms_norm(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.sum(x**2, axis=1))))


def score_scene(row: dict, b_notch: np.ndarray, a_notch: np.ndarray) -> dict:
    sid = row["scene_id"]
    entry = row["methods"]["C5"]
    path = Path(entry["raw_path"])
    raw_sha = sha(path)
    if raw_sha.lower() != entry["raw_sha256"].lower():
        raise RuntimeError(f"C5 raw hash mismatch: {sid}")

    with h5py.File(path, "r") as f:
        log = f["log"]
        time = np.asarray(log["transition_time"][()], dtype=float).reshape(-1)
        n = len(time)
        state = np.asarray(log["state"][()], dtype=float).T[:n]
        compensation = arr3(log, "stage1_position_held_applied_acceleration_mps2", n)
        total_comp = arr3(log, "position_compensation_applied_acceleration_mps2", n)
        nominal = arr3(log, "position_nominal_acceleration_mps2", n)
        command_force = arr3(log, "position_commanded_force_N", n)
        target_logged = arr3(log, "command_filter_target_euler", n)
        filtered_logged = arr3(log, "filtered_attitude_reference", n)
        events = np.asarray(log["stage1_position_event"][()], dtype=bool).reshape(-1)
        event_dt_logged = np.asarray(log["stage1_position_event_dt_s"][()], dtype=float).reshape(-1)
        ref_acc = arr3(f["scene/reference"], "acceleration", n + 1)[:n]
        ref_yaw = np.asarray(f["scene/reference/yaw"][()], dtype=float).reshape(-1)[:n]
        flags = [int(np.asarray(log[name][()]).squeeze()) for name in (
            "stage1_position_replacement_enabled", "stage1_position_delayed_prediction_enabled",
            "stage1_position_pcf_coordination_enabled")]

    if n != 20_000 or state.shape != (n, 12) or len(events) != n:
        raise RuntimeError(f"unexpected raw shape: {sid}")
    if flags != [1, 1, 1]:
        raise RuntimeError(f"raw is not C5 delayed+PCF: {sid}, flags={flags}")
    if not np.allclose(total_comp, compensation, atol=1e-12, rtol=0):
        raise RuntimeError(f"held head signal does not equal total applied C5 compensation: {sid}")
    event_idx = np.flatnonzero(events)
    if len(event_idx) != 1_999 or not np.array_equal(np.diff(event_idx), np.full(len(event_idx)-1, 10)):
        raise RuntimeError(f"unexpected 100-Hz event indexing: {sid}")
    if abs(time[event_idx[0]] - 0.01) > 1e-12 or np.max(np.abs(np.diff(time) - DT)) > 1e-12:
        raise RuntimeError(f"event/time origin mismatch: {sid}")
    if np.max(np.abs(event_dt_logged[event_idx] - EVENT_DT)) > 1e-12:
        raise RuntimeError(f"logged event dt is not 10 ms: {sid}")
    if np.max(np.abs(command_force / MASS - (nominal - compensation))) > 2e-10:
        raise RuntimeError(f"position force/acceleration identity mismatch: {sid}")

    # Causal filter updates consume only the current event's held Stage1 output.
    comp_lp = lowpass_event_replay(compensation, event_idx, n)
    comp_notch_event = lfilter(b_notch, a_notch, compensation[event_idx], axis=0)
    comp_notch = event_zoh(comp_notch_event, event_idx, n)
    traces = {"raw_C5": compensation, "tau0p1_event100hz": comp_lp, "notch_3p5Hz_Q1_event100hz": comp_notch}

    yaw_state = state[:, 8]
    task = task_euler(ref_acc, ref_yaw)
    raw_command_accel = command_force / MASS
    raw_target_rebuilt = target_euler(raw_command_accel, yaw_state, ref_yaw)
    target_error = float(np.max(np.abs(wrap(raw_target_rebuilt - target_logged))))
    filtered_error = float(np.max(np.abs(wrap(replay_command_filter(target_logged, state[0, 6:9]) - filtered_logged))))
    if target_error > 1e-10 or filtered_error > 1e-10:
        raise RuntimeError(f"logged C5 target/filter reconstruction failed: {sid}, {target_error}, {filtered_error}")

    result = {"scene_id": sid, "split": row["split"], "HF_group": sid.rsplit("_", 1)[-1],
              "C5_raw_path": str(path), "C5_raw_sha256": raw_sha,
              "event_count": int(len(event_idx)), "event_first_index_zero_based": int(event_idx[0]),
              "event_last_index_zero_based": int(event_idx[-1]), "event_period_s": EVENT_DT,
              "target_reconstruction_max_abs_rad": target_error,
              "command_filter_replay_max_abs_rad": filtered_error,
              "methods": {}}
    raw_target = raw_target_rebuilt
    for name, comp in traces.items():
        command_accel = nominal - comp
        target = target_euler(command_accel, yaw_state, ref_yaw)
        filtered = (filtered_logged if name == "raw_C5" else
                    replay_command_filter(target, state[0, 6:9]))
        dtarget = target[:, :2] - raw_target[:, :2]
        dcomp = comp - compensation
        dforce = MASS * (compensation - comp)
        band_rows = {}
        for low, high in BANDS:
            key = f"{low:g}_{high:g}Hz"
            base_p = band_power(raw_target[:, :2], low, high)
            delta_p = band_power(dtarget, low, high)
            changed_p = band_power(target[:, :2], low, high)
            band_rows[key] = {
                "compensation_rms_mps2": band_rms(comp, low, high),
                "signed_compensation_delta_rms_mps2": band_rms(dcomp, low, high),
                "target_RP_rms_mrad": 1000 * band_rms(target[:, :2], low, high),
                "signed_target_RP_delta_rms_mrad": 1000 * band_rms(dtarget, low, high),
                "target_RP_delta_cross_term_mrad2": 1e6 * cross_power(raw_target[:, :2], dtarget, low, high),
                "target_RP_power_identity_residual_mrad2": 1e6 * (changed_p - base_p - delta_p - cross_power(raw_target[:, :2], dtarget, low, high)),
                "filtered_reference_RP_rms_mrad": 1000 * band_rms(filtered[:, :2], low, high),
            }
        # Command-force delta is signed, and is not an estimate of physical wind force.
        result["methods"][name] = {
            "compensation_rms_mps2": rms_norm(comp),
            "task_to_command_target_SO3_rmse_mrad": 1000 * geodesic_rmse(task, target),
            "task_to_filtered_reference_SO3_rmse_mrad": 1000 * geodesic_rmse(task, filtered),
            "signed_command_force_delta_from_raw_rms_N": rms_norm(dforce),
            "command_force_delta_peak_norm_N": float(np.max(np.linalg.norm(dforce, axis=1))),
            "bands": band_rows,
        }
    # Separate B is a different closed-loop trajectory: comparator only, not same-trace causality.
    b_entry = row["methods"]["B"]
    b_path = Path(b_entry["raw_path"])
    if sha(b_path).lower() != b_entry["raw_sha256"].lower():
        raise RuntimeError(f"B raw hash mismatch: {sid}")
    with h5py.File(b_path, "r") as f:
        b_filtered = arr3(f["log"], "filtered_attitude_reference", n)
    result["B_different_trajectory_comparator"] = {
        "raw_path": str(b_path), "raw_sha256": b_entry["raw_sha256"],
        "task_to_logged_filtered_reference_SO3_rmse_mrad": 1000 * geodesic_rmse(task, b_filtered),
    }
    return result


def response_summary(b: np.ndarray, a: np.ndarray) -> dict:
    f, h = freqz(b, a, worN=32768, fs=FS_EVENT)
    db = 20 * np.log10(np.maximum(np.abs(h), 1e-15))
    below = db <= -3.01029995664
    edges = (float(f[np.flatnonzero(below)[0]]), float(f[np.flatnonzero(below)[-1]]))
    points = {}
    for hz in (0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5, 6, 8, 10):
        _, val = freqz(b, a, worN=np.array([hz]), fs=FS_EVENT)
        is_zero = abs(val[0]) < 1e-12
        points[f"{hz:g}_Hz"] = {"gain_db": None if is_zero else float(20*np.log10(abs(val[0]))),
                                "phase_deg_principal": None if is_zero else float(np.degrees(np.angle(val[0]))),
                                "notch_zero": bool(is_zero)}
    return {"sample_rate_hz": FS_EVENT, "frequency_hz": F0_HZ, "Q": Q,
            "coeff_b": b.tolist(), "coeff_a": a.tolist(),
            "poles": [[float(z.real), float(z.imag)] for z in np.roots(a)],
            "stable": bool(np.max(np.abs(np.roots(a))) < 1),
            "minus_3dB_edges_hz_dense_grid": list(edges), "response_points": points}


def main() -> None:
    if OUT_JSON.exists() or OUT_MD.exists():
        raise RuntimeError("refusing to overwrite notch replay artifacts")
    if sha(SCORE) != SCORE_SHA256:
        raise RuntimeError("HF6 score manifest SHA mismatch")
    if sha(HISTORICAL_NOTCH_STATE) != HISTORICAL_NOTCH_STATE_SHA256:
        raise RuntimeError("historical notch state changed")
    for relpath, expected in LOCKED_FILES.items():
        if sha(ROOT / relpath) != expected:
            raise RuntimeError(f"locked source changed: {relpath}")
    score = json.loads(SCORE.read_text(encoding="utf-8-sig"))
    if score.get("TEST_read") is not False or score.get("test_data_read") is not False:
        raise RuntimeError("score scope flags are not permitted")
    by_scene = {r["scene_id"]: r for r in score["scene_results"]}
    if not set(SCENES).issubset(by_scene) or any("TEST" in s for s in SCENES):
        raise RuntimeError("locked six-scene DEV/VAL set not found")
    b, a = iirnotch(F0_HZ, Q, fs=FS_EVENT)
    results = [score_scene(by_scene[sid], b, a) for sid in SCENES]
    methods = ("raw_C5", "tau0p1_event100hz", "notch_3p5Hz_Q1_event100hz")
    summary = {}
    for name in methods:
        rows = [r["methods"][name] for r in results]
        bands = {}
        for low, high in BANDS:
            key = f"{low:g}_{high:g}Hz"
            bands[key] = {metric: float(np.mean([r["bands"][key][metric] for r in rows])) for metric in (
                "compensation_rms_mps2", "signed_compensation_delta_rms_mps2", "target_RP_rms_mrad",
                "signed_target_RP_delta_rms_mrad", "target_RP_delta_cross_term_mrad2",
                "filtered_reference_RP_rms_mrad")}
        summary[name] = {
            "mean_scene_compensation_rms_mps2": float(np.mean([r["compensation_rms_mps2"] for r in rows])),
            "mean_scene_task_to_command_target_SO3_rmse_mrad": float(np.mean([r["task_to_command_target_SO3_rmse_mrad"] for r in rows])),
            "mean_scene_task_to_filtered_reference_SO3_rmse_mrad": float(np.mean([r["task_to_filtered_reference_SO3_rmse_mrad"] for r in rows])),
            "mean_scene_signed_command_force_delta_rms_N": float(np.mean([r["signed_command_force_delta_from_raw_rms_N"] for r in rows])),
            "bands_equal_scene_mean": bands,
        }
    by_hf = {}
    for hf in sorted({r["HF_group"] for r in results}):
        by_hf[hf] = {}
        for name in methods:
            rows = [r["methods"][name] for r in results if r["HF_group"] == hf]
            by_hf[hf][name] = {
                "n_scenes": len(rows),
                "task_to_filtered_reference_SO3_rmse_mrad_mean": float(np.mean([r["task_to_filtered_reference_SO3_rmse_mrad"] for r in rows])),
                "comp_2_5Hz_rms_mps2_mean": float(np.mean([r["bands"]["2_5Hz"]["compensation_rms_mps2"] for r in rows])),
                "target_RP_2_5Hz_rms_mrad_mean": float(np.mean([r["bands"]["2_5Hz"]["target_RP_rms_mrad"] for r in rows])),
                "target_RP_delta_2_5Hz_rms_mrad_mean": float(np.mean([r["bands"]["2_5Hz"]["signed_target_RP_delta_rms_mrad"] for r in rows])),
            }
    result = {
        "schema": "DL1018_CAUSAL_NOTCH_C5_SAME_TRACE_HF6_V1",
        "status": "COMPLETE_OFFLINE_SAME_TRACE_REPLAY_NOT_CLOSED_LOOP",
        "scope": "Six locked HF6 DEV/VAL C5 traces; raw, event-rate tau=0.1s LPF, and one fixed causal 3.5Hz Q=1 notch; no Plant, TEST, training, wind-field read, or inertia reconstruction.",
        "Plant_calls_by_replay": 0, "TEST_read": False, "training_runs": 0,
        "inertia_reconstruction": False, "wind_field_read": False,
        "VAL_is_independent_validation": False,
        "input_score_path": str(SCORE), "input_score_sha256": sha(SCORE),
        "historical_notch_search": {
            "search_scope": "experiments/ and matlab/ MATLAB/Python/JSON/Markdown source files before this probe was added",
            "completed_notch_implementation_found": False,
            "historical_mention_path": str(HISTORICAL_NOTCH_STATE.relative_to(ROOT)),
            "historical_mention_sha256": sha(HISTORICAL_NOTCH_STATE),
            "historical_probe_state": json.loads(HISTORICAL_NOTCH_STATE.read_text(encoding="utf-8-sig"))["notch_probe"],
        },
        "replay_script_path": str(Path(__file__).resolve()), "replay_script_sha256": sha(Path(__file__).resolve()),
        "locked_source_bindings": [{"path": rel, "sha256": sha(ROOT / rel)} for rel in LOCKED_FILES],
        "notch": response_summary(b, a),
        "band_method": "1-ms transition sequences; un-demeaned rectangular-window rFFT, 2x one-sided interior bins, low-inclusive/high-exclusive bands. Angular target signals are signed roll/pitch; target delta and the cross term are reported separately.",
        "summary_equal_scene_mean": summary, "summary_by_HF_group": by_hf,
        "B_comparator_mean_task_to_filtered_reference_mrad_different_trajectory": float(np.mean([r["B_different_trajectory_comparator"]["task_to_logged_filtered_reference_SO3_rmse_mrad"] for r in results])),
        "scene_results": results,
        "interpretation_limits": [
            "The notch is causal at 100-Hz Stage1 output events and its output is zero-order held; no future samples enter.",
            "The replay changes the position compensation on fixed C5 states. Q and future states are not recomputed, so all filter results are same-trace signal/command diagnostics, not closed-loop outcomes.",
            "VAL rows are development diagnostics because the frozen backbone was already exposed to development data; they are not independent validation.",
            "Command-force delta is the controller command change induced by filtering, not external wind or physical disturbance force.",
            "The response phase can alter task alignment even where magnitude is preserved; phase risk is part of the fixed Q=1 result, not a negligible detail.",
        ],
    }
    OUT_JSON.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_md(result)
    print(json.dumps({"status": result["status"], "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))


def write_md(result: dict) -> None:
    lines = [
        "# Causal notch replay on C5 HF6 traces", "",
        "Offline same-trace replay only; no Plant, TEST, training, wind-field read, or inertia reconstruction. VAL is a development diagnostic, not independent validation.", "",
        "Fixed scheme: second-order causal `iirnotch` at 3.5 Hz, Q=1, fs=100 Hz, zero initial state, updated only when `stage1_position_event` is true; hold output between events. No Q/frequency sweep was performed.", "",
        "The C5 raw log has 20,000 1-ms transitions and 1,999 Stage1 events per scene at zero-based indices 10, 20, …, 19,990 (event time 10 ms onward). The filtered input is the logged held applied Stage1 acceleration at the current event. Its output replaces the compensation only for reconstructing command/target on the unchanged raw state trajectory.", "",
        "## Filter response", "",
        f"Poles: `{result['notch']['poles']}`; stable={result['notch']['stable']}; dense-grid −3 dB edges {result['notch']['minus_3dB_edges_hz_dense_grid'][0]:.3f}–{result['notch']['minus_3dB_edges_hz_dense_grid'][1]:.3f} Hz.", "",
        "| Frequency (Hz) | Gain (dB) | Phase (deg) |", "|---:|---:|---:|",
    ]
    for hz, vals in result["notch"]["response_points"].items():
        gain = "notch zero" if vals["gain_db"] is None else f"{vals['gain_db']:.3f}"
        phase = "undefined" if vals["phase_deg_principal"] is None else f"{vals['phase_deg_principal']:+.2f}"
        lines.append(f"| {hz.replace('_Hz','')} | {gain} | {phase} |")
    lines.extend(["", "At 1 Hz the response is −0.407 dB/−17.41°; at 5 Hz it is −4.599 dB/+53.92°. This does **not** leave all sub-1-Hz content untouched, and its phase is material around the band edges. The response is computed for the 100-Hz event-rate filter; the 1-ms output hold adds a further frequency-dependent response not included in this table.", "",
        "Historical-source check: the repository search found no completed prior notch implementation. The only older mention is `experiments/dl_attitude_replacement_20261027/mlp15_nominal_residual_v1/CONTINUATION_STATE_v2.json`, marked `OFFLINE_PREPARING` (SHA-256 recorded in the JSON); it contains no prior completed result.", "",
        "## Equal-scene results", "",
        "| Signal | Compensation RMS (m/s²) | Task→command target SO(3) (mrad) | Task→filtered reference SO(3) (mrad) | Δ command force RMS (N) | Comp 0–1 Hz | Comp 1–2 Hz | Comp 2–5 Hz | Target RP 2–5 Hz | Signed target RP Δ 2–5 Hz |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"])
    for name, row in result["summary_equal_scene_mean"].items():
        b = row["bands_equal_scene_mean"]
        lines.append(f"| {name} | {row['mean_scene_compensation_rms_mps2']:.4f} | {row['mean_scene_task_to_command_target_SO3_rmse_mrad']:.3f} | {row['mean_scene_task_to_filtered_reference_SO3_rmse_mrad']:.3f} | {row['mean_scene_signed_command_force_delta_rms_N']:.4f} | {b['0_1Hz']['compensation_rms_mps2']:.4f} | {b['1_2Hz']['compensation_rms_mps2']:.4f} | {b['2_5Hz']['compensation_rms_mps2']:.4f} | {b['2_5Hz']['target_RP_rms_mrad']:.3f} | {b['2_5Hz']['signed_target_RP_delta_rms_mrad']:.3f} |")
    lines.extend(["", "The signed target RP delta is candidate minus raw C5. The reported 2–5 Hz cross term is retained separately in the JSON because the candidate target spectrum is not the sum of the raw target and compensation spectra; force-to-attitude mapping is nonlinear. Per-scene values and HF-group means are in the JSON.", "",
        f"Different-trajectory B comparator: mean task→logged-filtered-reference {result['B_comparator_mean_task_to_filtered_reference_mrad_different_trajectory']:.3f} mrad. This is contextual only; it is not a same-state counterfactual.", "",
        "## Limits", "",
        "Filtering `dF` on a fixed trajectory does not recompute position closure Q or the next state. A lower compensation-band RMS or conditional attitude-reference error cannot establish closed-loop success. The filter's phase may improve one trace and worsen another; the six DEV/VAL signals only support or falsify this offline mechanism hypothesis.", "",
        "## Reproduction", "",
        "From the repository root: `python experiments/dl_attitude_replacement_20261028/method_alternatives_review_v1/causal_notch_replay_hf6_v1.py`.", "",
        f"Script SHA-256: `{result['replay_script_sha256']}`.", ""])
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
