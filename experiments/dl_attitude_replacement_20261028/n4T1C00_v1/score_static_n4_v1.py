from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import h5py
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SCENE = "DL1018_DEV_T1_C00_W03"
ATTEMPT = HERE / "runs" / SCENE / "attempt_01"
OUT = HERE / "audits/STATIC_N4_CLOSED_LOOP_SCORE_v1.json"
SCORE_SOURCE = ROOT / "experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_full72_v1/audits/score_full72_candidate_v1.py"
CONSTANTS = ROOT / "experiments/dl_attitude_replacement_20261026/mlp15_composite_dev_v3/RELEASE.json"
FS_HZ = 1000.0
N = 20000
CENTERS = (2.2, 3.2, 3.7, 4.8)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_log(raw: h5py.File, name: str) -> np.ndarray:
    return np.asarray(raw["log"][name][()], dtype=np.float64).T


def wrap_delta(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    d = a - b
    return np.arctan2(np.sin(d), np.cos(d))


def band_rms(x: np.ndarray, lo: float, hi: float) -> float:
    x = np.asarray(x, dtype=np.float64)
    if x.ndim == 1:
        x = x[:, None]
    x = x - np.mean(x, axis=0, keepdims=True)
    n = x.shape[0]
    window = np.hanning(n)
    spec = np.fft.rfft(x * window[:, None], axis=0)
    psd = np.abs(spec) ** 2 / (FS_HZ * np.sum(window**2))
    if n % 2 == 0:
        psd[1:-1] *= 2
    else:
        psd[1:] *= 2
    freq = np.fft.rfftfreq(n, 1 / FS_HZ)
    selected = (freq >= lo) & (freq < hi)
    power = np.sum(psd[selected], axis=0) * FS_HZ / n
    return float(np.sqrt(np.sum(power)))


def tone(signal: np.ndarray, target: np.ndarray, f_hz: float) -> dict:
    signal = np.asarray(signal, dtype=np.float64)
    target = np.asarray(target, dtype=np.float64)
    if signal.ndim == 1:
        signal = signal[:, None]
    if target.ndim == 1:
        target = target[:, None]
    n = min(signal.shape[0], target.shape[0])
    signal, target = signal[:n], target[:n]
    win = np.hanning(n)
    k = int(round(f_hz * n / FS_HZ))
    xs = np.fft.rfft((signal - signal.mean(axis=0)) * win[:, None], axis=0)[k]
    xt = np.fft.rfft((target - target.mean(axis=0)) * win[:, None], axis=0)[k]
    amplitude = 2 * np.abs(xs) / np.sum(win) / np.sqrt(2)
    phase = np.angle(np.conj(xt) * xs)
    return {
        "frequency_hz": f_hz,
        "signal_axis_rms_amplitude": amplitude.tolist(),
        "signal_vector_rms_amplitude": float(np.linalg.norm(amplitude)),
        "phase_signal_minus_target_deg_per_axis": (np.rad2deg(phase)).tolist(),
    }


def low_transfer(candidate: np.ndarray, parent: np.ndarray) -> dict:
    candidate = np.asarray(candidate, dtype=np.float64)[:N]
    parent = np.asarray(parent, dtype=np.float64)[:N]
    rms_c, rms_p = band_rms(candidate, 0.05, 0.5), band_rms(parent, 0.05, 0.5)
    n = min(len(candidate), len(parent))
    win = np.hanning(n)
    f = np.fft.rfftfreq(n, 1 / FS_HZ)
    idx = np.flatnonzero((f >= 0.05) & (f < 0.5))
    phase_by_axis, delay_by_axis, gain_by_axis = [], [], []
    for axis in range(3):
        xp = np.fft.rfft((parent[:n, axis] - np.mean(parent[:n, axis])) * win)[idx]
        xc = np.fft.rfft((candidate[:n, axis] - np.mean(candidate[:n, axis])) * win)[idx]
        valid = np.abs(xp) > (np.max(np.abs(xp)) * 1e-5 if xp.size else np.inf)
        if valid.sum() < 2:
            phase_by_axis.append(None);delay_by_axis.append(None);gain_by_axis.append(None);continue
        h = xc[valid] / xp[valid]
        omega = 2 * np.pi * f[idx][valid]
        phase = np.unwrap(np.angle(h))
        slope, intercept = np.polyfit(omega, phase, 1)
        phase_by_axis.append(float(np.rad2deg(np.angle(np.mean(np.exp(1j * phase))))))
        delay_by_axis.append(float(-slope))
        gain_by_axis.append(float(np.median(np.abs(h))))
    return {
        "band_hz": [0.05, 0.5],
        "applied_action_vector_rms_mps2": rms_c,
        "parent_action_vector_rms_mps2": rms_p,
        "vector_amplitude_ratio": rms_c / rms_p if rms_p else None,
        "phase_deg_candidate_minus_parent_by_axis": phase_by_axis,
        "group_delay_s_by_axis": delay_by_axis,
        "median_gain_by_axis": gain_by_axis,
    }


def main() -> None:
    if OUT.exists():
        raise SystemExit(f"refusing to overwrite {OUT}")
    binding = json.loads((HERE / "TRAIN_SCENE_BINDING_v1.json").read_text(encoding="utf-8-sig"))
    raw_path, status_path = ATTEMPT / "raw_run.mat", ATTEMPT / "run_status.json"
    raw_status = json.loads(status_path.read_text(encoding="utf-8-sig"))
    raw_audit = json.loads((HERE / "audits/RAW_VALIDATION_v1.json").read_text(encoding="utf-8-sig"))
    if (raw_audit.get("status") != "PASS_FIXED_N4_NO_POSITION_GRU_RAW" or
            raw_status.get("raw_sha256") != sha(raw_path) or raw_status.get("Plant_calls") != 1):
        raise SystemExit("candidate raw did not pass its frozen one-call contract")
    comparators = {
        "B": (Path(binding["b72_scoring_raw_path"]), Path(binding["b72_scoring_status_path"]),
              binding["b72_scoring_raw_sha256"], binding["b72_scoring_status_sha256"]),
        "C5": (Path(binding["c5_raw_path"]), Path(binding["c5_status_path"]),
               binding["c5_raw_sha256"], binding["c5_status_sha256"]),
        "parent_C5_cosine_GRU_pre_filter": (Path(binding["parent_raw_path"]), Path(binding["parent_status_path"]),
               binding["parent_raw_sha256"], binding["parent_status_sha256"]),
    }
    module = importlib.util.spec_from_file_location("frozen_full72_score", SCORE_SOURCE)
    if module is None or module.loader is None:
        raise SystemExit("cannot import frozen scorer")
    scorer = importlib.util.module_from_spec(module);module.loader.exec_module(scorer)
    constants = json.loads(CONSTANTS.read_text(encoding="utf-8-sig"))
    gravity, max_tilt = float(constants["gravity_mps2"]), float(constants["max_tilt_rad"])
    raws = {"candidate_static_N4": (raw_path, status_path)}
    input_hashes = {}
    scores, spectra = {}, {}
    for name, (raw, status, raw_hash, status_hash) in comparators.items():
        raw, status = raw.resolve(strict=True), status.resolve(strict=True)
        if sha(raw) != raw_hash or sha(status) != status_hash:
            raise SystemExit(f"same-scene comparator source hash changed: {name}")
        st = json.loads(status.read_text(encoding="utf-8-sig"))
        if st.get("scene_id") != SCENE or st.get("TEST_read") is True or st.get("VAL_data_read") is True:
            raise SystemExit(f"comparator is outside physical TRAIN scene/scope: {name}")
        raws[name] = (raw, status)
        input_hashes[name] = {"raw_path": str(raw), "raw_sha256": raw_hash,
                              "status_path": str(status), "status_sha256": status_hash}
    input_hashes["candidate_static_N4"] = {"raw_path": str(raw_path.resolve()), "raw_sha256": sha(raw_path),
        "status_path": str(status_path.resolve()), "status_sha256": sha(status_path)}
    arrays = {}
    for name, (raw, _) in raws.items():
        scores[name] = scorer.score_raw(raw, gravity, max_tilt)
        with h5py.File(raw, "r") as f:
            ref_acc = np.asarray(f["scene/reference/acceleration"][()], dtype=np.float64).T[:N]
            yaw = np.asarray(f["scene/reference/yaw"][()], dtype=np.float64).reshape(-1)[:N]
            state = read_log(f, "state")[:N]
            command = read_log(f, "command_filter_target_euler")
            filtered = read_log(f, "filtered_attitude_reference")
            action = read_log(f, "stage1_position_held_applied_acceleration_mps2")
        specific = ref_acc.copy();specific[:, 2] += gravity
        cy, sy = np.cos(yaw), np.sin(yaw)
        accel_x = cy * specific[:, 0] + sy * specific[:, 1]
        accel_y = sy * specific[:, 0] - cy * specific[:, 1]
        roll = np.arctan2(accel_y, np.hypot(specific[:, 2], accel_x))
        pitch = np.arctan2(accel_x, specific[:, 2])
        tilt = np.hypot(roll, pitch);scale = np.minimum(1, max_tilt / np.maximum(tilt, np.finfo(float).eps))
        task = np.column_stack((roll * scale, pitch * scale, yaw))
        actual = state[:, 6:9]
        arrays[name] = {"task": task, "actual": actual, "command": command, "filtered": filtered, "action": action}
        spectra[name] = {"bands": {}, "exact_tones": {}}
        for center in CENTERS:
            lo, hi = max(0.01, center - 0.5), center + 0.5
            spectra[name]["bands"][f"{center:.1f}Hz"] = {
                "band_hz": [lo, hi],
                "task_minus_actual_wrapped_euler_vector_rms_mrad": band_rms(wrap_delta(task, actual), lo, hi) * 1e3,
                "command_filter_target_vector_rms_mrad": band_rms(command, lo, hi) * 1e3,
                "filtered_attitude_reference_vector_rms_mrad": band_rms(filtered, lo, hi) * 1e3,
                "actual_euler_vector_rms_mrad": band_rms(actual, lo, hi) * 1e3,
                "task_euler_vector_rms_mrad": band_rms(task, lo, hi) * 1e3,
                "applied_compensation_vector_rms_mps2": band_rms(action, lo, hi),
            }
            spectra[name]["exact_tones"][f"{center:.1f}Hz"] = {
                "task_to_actual": tone(actual, task, center),
                "command_to_filtered": tone(filtered, command, center),
                "filtered_to_actual": tone(actual, filtered, center),
            }
    candidate = scores["candidate_static_N4"]
    c5_q = scores["C5"]["Q_m"]
    q_ratio = candidate["Q_m"] / c5_q if c5_q else float("inf")
    task_vs_b = candidate["task_SO3_rad"] <= scores["B"]["task_SO3_rad"]
    task_criterion_applicable = SCENE in {"DL1018_DEV_T3_C09_W09", "DL1018_DEV_T1_C11_W12"}
    safety = candidate["safety"]
    safety_zero = all(safety[k] == 0 for k in ("motor_saturation_samples", "generalized_clip_samples", "tilt_limited_samples"))
    pass_q = q_ratio <= 1.05
    pre = arrays["parent_C5_cosine_GRU_pre_filter"]["action"]
    low = low_transfer(arrays["candidate_static_N4"]["action"], pre)
    criteria = {"candidate_Q_le_1p05x_C5": pass_q,
                "candidate_task_not_worse_than_B": task_vs_b if task_criterion_applicable else None,
                "candidate_task_criterion_applicable": task_criterion_applicable,
                "stable_20k_one_call": raw_status.get("status_value") == "STABLE" and raw_status.get("transitions") == 20000 and raw_status.get("Plant_calls") == 1,
                "safety_counters_zero": safety_zero}
    pass_all = pass_q and (not task_criterion_applicable or task_vs_b) and criteria["stable_20k_one_call"] and safety_zero
    result = {
        "status": "PASS_FIXED_SCENE_N4_DIAGNOSTIC" if pass_all else "FAIL_FIXED_SCENE_N4_DIAGNOSTIC",
        "study_id": "static_n4_T1C00_no_position_gru_v1", "scene_id": SCENE,
        "source_split": "TRAIN_C5_24", "wind_peaks_hz": [0.6, 0.85], "MATLAB_release": "R2025b",
        "Plant_calls": 1, "TEST_read": False, "VAL_read": False, "inertia_reconstruction_enabled": False,
        "prior_two_notch_status_preserved": "FAIL_FIXED_FROZEN_REPLAY",
        "n4_train24_replay_status_preserved": "MEASURED_FIXED_TRAIN24_REPLAY",
        "fixed_intervention": {"centers_hz": list(CENTERS), "quality_factor_each": [4,4,4,4],
            "sample_rate_hz": 100.0, "action_limit_mps2": 3.0,
            "application_point": "final held C5 compensation before force injection", "runtime_wind_or_W_code_branching": False},
        "frozen_score_source_path": str(SCORE_SOURCE.resolve()), "frozen_score_source_sha256": sha(SCORE_SOURCE),
        "score_constants_sha256": sha(CONSTANTS), "same_scene_inputs": input_hashes,
        "scores": scores, "frequency_metrics": spectra,
        "low_band_applied_action_transfer_candidate_vs_parent": low,
        "predeclared_criteria": criteria,
        "decision_values": {"candidate_Q_m": candidate["Q_m"], "same_scene_C5_Q_m": c5_q,
            "candidate_Q_over_C5": q_ratio, "candidate_task_SO3_rad": candidate["task_SO3_rad"],
            "same_scene_B_task_SO3_rad": scores["B"]["task_SO3_rad"], "candidate_safety": safety},
        "raw_validation_path": str((HERE / "audits/RAW_VALIDATION_v1.json").resolve()),
        "raw_validation_sha256": sha(HERE / "audits/RAW_VALIDATION_v1.json"),
        "interpretation_limit": "One fixed W09 TRAIN scene and static N4 diagnostic only; no cross-wind generalization or candidate acceptance claim.",
    }
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUT.resolve()), "status": result["status"], "scene_id": SCENE,
        "Q_m": candidate["Q_m"], "C5_Q_m": c5_q, "Q_over_C5": q_ratio,
        "task_SO3_rad": candidate["task_SO3_rad"], "B_task_SO3_rad": scores["B"]["task_SO3_rad"],
        "safety": safety, "criteria": criteria}, indent=2))


if __name__ == "__main__":
    main()
