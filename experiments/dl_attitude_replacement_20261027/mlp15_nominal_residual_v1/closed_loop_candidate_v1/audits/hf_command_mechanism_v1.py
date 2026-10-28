"""Read-only HF command-path audit for the frozen MLP15 12-scene screen."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import h5py
import numpy as np

HERE = Path(__file__).resolve().parent
STUDY = HERE.parent.parent
ROOT = HERE.parents[4]
SCORE_PATH = HERE / "CLOSED_LOOP_SCORE_v1.json"
WN12 = ROOT / "experiments/dl_attitude_replacement_20261027/task_attitude_filter_wn12_hf_screen_v1"
METRIC_PATH = ROOT / "experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_full72_v1/audits/score_full72_candidate_v1.py"
OUTPUT = HERE / "HF_COMMAND_MECHANISM_v1.json"

spec = importlib.util.spec_from_file_location("frozen_metrics", METRIC_PATH)
if spec is None or spec.loader is None:
    raise ImportError(METRIC_PATH)
metrics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metrics)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def readj(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def bound(path_value: str, expected: str, label: str) -> Path:
    path = Path(path_value)
    if not path.is_file() or sha(path).lower() != expected.lower():
        raise RuntimeError(f"{label} is missing or its SHA-256 changed: {path}")
    return path


def load_arrays(path: Path) -> dict[str, np.ndarray]:
    with h5py.File(path, "r") as f:
        log, ref = f["log"], f["scene/reference"]
        return {
            "state": np.asarray(log["state"][()], dtype=float).T,
            "target": np.asarray(log["command_filter_target_euler"][()], dtype=float).T,
            "filtered": np.asarray(log["filtered_attitude_reference"][()], dtype=float).T,
            "acceleration_ref": np.asarray(ref["acceleration"][()], dtype=float).T,
            "yaw_ref": np.asarray(ref["yaw"][()], dtype=float).reshape(-1),
            "nominal_acceleration": np.asarray(log["position_nominal_acceleration_mps2"][()], dtype=float).T,
            "nominal_force": np.asarray(log["position_bs_nominal_force_N"][()], dtype=float).T,
            "command_force": np.asarray(log["position_commanded_force_N"][()], dtype=float).T,
            "compensation_force": np.asarray(log["position_compensation_applied_force_N"][()], dtype=float).T,
            "position_held_force": np.asarray(log["stage1_position_held_force_I_N"][()], dtype=float).T,
        }


def task_euler(raw: dict, gravity: float, max_tilt: float) -> np.ndarray:
    a = raw["acceleration_ref"].copy()
    yaw = raw["yaw_ref"]
    a[:, 2] += gravity
    ax = np.cos(yaw) * a[:, 0] + np.sin(yaw) * a[:, 1]
    ay = np.sin(yaw) * a[:, 0] - np.cos(yaw) * a[:, 1]
    roll = np.arctan2(ay, np.hypot(a[:, 2], ax))
    pitch = np.arctan2(ax, a[:, 2])
    scale = np.minimum(1.0, max_tilt / np.maximum(np.hypot(roll, pitch), np.finfo(float).eps))
    return np.column_stack((roll * scale, pitch * scale, yaw))


def rms_rate(x: np.ndarray, dt: float) -> float:
    d = np.arctan2(np.sin(np.diff(x, axis=0)), np.cos(np.diff(x, axis=0))) / dt
    return float(np.sqrt(np.mean(np.sum(d * d, axis=1))))


def vector_rms_rate(x: np.ndarray, dt: float) -> float:
    return float(np.sqrt(np.mean(np.sum((np.diff(x, axis=0) / dt) ** 2, axis=1))))


def highpass_rms(x: np.ndarray, dt: float, cutoff_hz: float = 10.0) -> float:
    centered = x - np.mean(x, axis=0, keepdims=True)
    freq = np.fft.rfftfreq(len(centered), dt)
    spectrum = np.fft.rfft(centered, axis=0)
    spectrum[freq < cutoff_hz] = 0
    high = np.fft.irfft(spectrum, n=len(centered), axis=0)
    return float(np.sqrt(np.mean(np.sum(high * high, axis=1))))


def target_from_force(force: np.ndarray, mass: float, yaw_for_mapping: np.ndarray,
                      yaw_target: np.ndarray, gravity: float, max_tilt: float) -> np.ndarray:
    specific = force / mass
    specific[:, 2] += gravity
    a = np.cos(yaw_for_mapping) * specific[:, 0] + np.sin(yaw_for_mapping) * specific[:, 1]
    b = np.sin(yaw_for_mapping) * specific[:, 0] - np.cos(yaw_for_mapping) * specific[:, 1]
    roll = np.arctan2(b, np.hypot(specific[:, 2], a))
    pitch = np.arctan2(a, specific[:, 2])
    scale = np.minimum(1.0, max_tilt / np.maximum(np.hypot(roll, pitch), np.finfo(float).eps))
    return np.column_stack((roll * scale, pitch * scale, yaw_target[:len(force)]))


def replay_filter(target: np.ndarray, initial: np.ndarray, dt: float = 0.001) -> np.ndarray:
    wn = np.array([18.0, 18.0, 12.0])
    zeta = np.ones(3)
    # The bound run raws show no RP clipping even when requested acceleration exceeds 8 rad/s^2.
    limit = np.array([np.inf, np.inf, 6.0])
    angle, rate = initial.copy(), np.zeros(3)
    result = np.empty_like(target)
    for i, desired in enumerate(target):
        result[i] = angle
        err = np.arctan2(np.sin(desired - angle), np.cos(desired - angle))
        acc = np.clip(wn * wn * err - 2 * zeta * wn * rate, -limit, limit)
        rate = rate + dt * acc
        angle = np.arctan2(np.sin(angle + dt * rate), np.cos(angle + dt * rate))
    return result


def causal_lowpass(x: np.ndarray, cutoff_hz: float, dt: float = 0.001) -> np.ndarray:
    alpha = np.exp(-2 * np.pi * cutoff_hz * dt)
    out = np.empty_like(x)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = alpha * out[i - 1] + (1 - alpha) * x[i]
    return out


def main() -> None:
    score = readj(SCORE_PATH)
    manifest_path = WN12 / "MANIFEST.json"
    manifest = readj(manifest_path)
    records = {r["scene_id"]: r for r in manifest["records"]}
    hf_rows = [r for r in score["rows"] if r.get("candidate_status", "SCORED") == "SCORED"
               and 9 <= int(r["scene_id"].rsplit("W", 1)[1]) <= 14]
    if len(hf_rows) != 6:
        raise RuntimeError(f"Expected exactly six scored HF scenes, found {len(hf_rows)}")

    constants = score["baseline_binding"]
    gravity, max_tilt = float(constants["gravity_mps2"]), float(constants["max_tilt_rad"])
    scene_rows = []
    for row in hf_rows:
        sid = row["scene_id"]
        rec = records[sid]
        paths = {
            "Candidate": bound(row["candidate_raw_path"], row["candidate_raw_sha256"], f"{sid} candidate raw"),
            "B": bound(rec["b_raw_path"], rec["b_raw_sha256"], f"{sid} B raw"),
            "C5": bound(rec["c5_raw_path"], rec["c5_raw_sha256"], f"{sid} C5 raw"),
        }
        arrays = {name: load_arrays(path) for name, path in paths.items()}
        candidate = arrays["Candidate"]
        task = task_euler(candidate, gravity, max_tilt)
        task_to_filtered = float(np.sqrt(np.mean(metrics.so3(candidate["filtered"], task[:20000]) ** 2)))
        nominal = candidate["nominal_force"]
        compensation = candidate["compensation_force"]
        command = candidate["command_force"]
        # position_nominal_acceleration is not needed: infer the configured mass from F=m*a.
        nominal_acceleration = candidate["nominal_acceleration"]
        valid = np.abs(nominal_acceleration) > 1e-7
        mass_values = (nominal[valid] / nominal_acceleration[valid])
        mass = float(np.median(mass_values[np.isfinite(mass_values)]))
        reconstructed = nominal - compensation
        force_reconstruction_error = float(np.max(np.abs(reconstructed - command)))
        yaw_for_mapping = candidate["state"][:20000, 8]
        yaw_target = candidate["yaw_ref"][:20000]
        target_no_comp = target_from_force(nominal, mass, yaw_for_mapping, yaw_target, gravity, max_tilt)
        target_replay = target_from_force(command, mass, yaw_for_mapping, yaw_target, gravity, max_tilt)
        shaped_compensation = causal_lowpass(compensation, cutoff_hz=10.0)
        target_shaped = target_from_force(nominal - shaped_compensation, mass, yaw_for_mapping,
                                          yaw_target, gravity, max_tilt)
        alpha_compensation = 0.9 * compensation
        target_alpha09 = target_from_force(nominal - alpha_compensation, mass, yaw_for_mapping,
                                           yaw_target, gravity, max_tilt)
        replayed_filtered = replay_filter(target_replay, candidate["state"][0, 6:9])
        replayed_no_comp_filtered = replay_filter(target_no_comp, candidate["state"][0, 6:9])
        replayed_shaped_filtered = replay_filter(target_shaped, candidate["state"][0, 6:9])
        replayed_alpha09_filtered = replay_filter(target_alpha09, candidate["state"][0, 6:9])
        target_reconstruction_error = float(np.max(np.abs(np.arctan2(
            np.sin(target_replay - candidate["target"]), np.cos(target_replay - candidate["target"])))) )
        filter_replay_error = float(np.max(np.abs(np.arctan2(
            np.sin(replayed_filtered - candidate["filtered"]), np.cos(replayed_filtered - candidate["filtered"])))) )
        comp_held_error = float(np.max(np.abs(compensation - candidate["position_held_force"])))
        if max(force_reconstruction_error, target_reconstruction_error, filter_replay_error, comp_held_error) > 1e-9:
            raise RuntimeError(f"{sid}: component replay contract mismatch")
        task_to_filtered_no_comp = float(np.sqrt(np.mean(metrics.so3(replayed_no_comp_filtered, task[:20000]) ** 2)))
        task_to_filtered_shaped = float(np.sqrt(np.mean(metrics.so3(replayed_shaped_filtered, task[:20000]) ** 2)))
        task_to_filtered_alpha09 = float(np.sqrt(np.mean(metrics.so3(replayed_alpha09_filtered, task[:20000]) ** 2)))
        # Dense, same-state component ablation: keep the logged BS nominal force and yaw,
        # remove only the learned compensation before the fixed force-to-angle map/filter.
        target_rate = rms_rate(candidate["target"], 0.001)
        filtered_rate = rms_rate(candidate["filtered"], 0.001)
        nominal_force_rate = vector_rms_rate(nominal, 0.001)
        compensation_force_rate = vector_rms_rate(compensation, 0.001)
        command_force_rate = vector_rms_rate(command, 0.001)
        method_scores = {name: metrics.score_raw(path, gravity, max_tilt) for name, path in paths.items()}
        scene_rows.append({
            "scene_id": sid,
            "raw_sha256": {name: sha(path) for name, path in paths.items()},
            "candidate_task_to_filtered_SO3_rad": task_to_filtered,
            "candidate_task_to_filtered_no_comp_same_state_SO3_rad": task_to_filtered_no_comp,
            "candidate_task_to_filtered_lowpass10_comp_same_state_SO3_rad": task_to_filtered_shaped,
            "candidate_task_to_filtered_alpha09_comp_same_state_SO3_rad": task_to_filtered_alpha09,
            "candidate_task_actual_SO3_rad": method_scores["Candidate"]["task_SO3_rad"],
            "B_task_actual_SO3_rad": method_scores["B"]["task_SO3_rad"],
            "C5_task_actual_SO3_rad": method_scores["C5"]["task_SO3_rad"],
            "candidate_inner_SO3_rad": method_scores["Candidate"]["inner_SO3_rad"],
            "command_force_reconstruction_max_abs_N": force_reconstruction_error,
            "command_target_reconstruction_max_abs_wrapped_rad": target_reconstruction_error,
            "filter_replay_max_abs_wrapped_rad": filter_replay_error,
            "candidate_command_target_rate_rads": target_rate,
            "candidate_filtered_reference_rate_rads": filtered_rate,
            "candidate_bs_nominal_force_rate_Nps": nominal_force_rate,
            "candidate_compensation_force_rate_Nps": compensation_force_rate,
            "candidate_position_command_force_rate_Nps": command_force_rate,
            "bs_nominal_force_highpass10hz_rms_N": highpass_rms(nominal, 0.001),
            "compensation_force_highpass10hz_rms_N": highpass_rms(compensation, 0.001),
            "command_force_highpass10hz_rms_N": highpass_rms(command, 0.001),
            "target_highpass10hz_rms_rad": highpass_rms(candidate["target"], 0.001),
            "target_no_comp_highpass10hz_rms_rad": highpass_rms(target_no_comp, 0.001),
            "target_lowpass10_comp_highpass10hz_rms_rad": highpass_rms(target_shaped, 0.001),
            "target_lowpass10_comp_rate_rads": rms_rate(target_shaped, 0.001),
            "compensation_lowpass10_hz_force_rate_Nps": vector_rms_rate(shaped_compensation, 0.001),
            "target_alpha09_comp_highpass10hz_rms_rad": highpass_rms(target_alpha09, 0.001),
            "target_alpha09_comp_rate_rads": rms_rate(target_alpha09, 0.001),
            "compensation_alpha09_force_rate_Nps": vector_rms_rate(alpha_compensation, 0.001),
            "compensation_force_vs_stage1_held_max_abs_N": comp_held_error,
        })

    metrics_to_average = [k for k in scene_rows[0] if k.endswith("_rad") or k.endswith("_rads") or k.endswith("_Nps")]
    macro = {key: float(np.mean([r[key] for r in scene_rows])) for key in metrics_to_average}
    result = {
        "schema": "DL1018_MLP15_HF_COMMAND_MECHANISM_AUDIT_V1",
        "status": "PASS_READ_ONLY_BOUND_HF6",
        "scope": "Current 6 HF candidate raws and their exact WN12-manifest B/C5 raws; no Plant, training, TEST, or truth inputs.",
        "inputs": {
            "score_path": str(SCORE_PATH), "score_sha256": sha(SCORE_PATH),
            "wn12_manifest_path": str(manifest_path), "wn12_manifest_sha256": sha(manifest_path),
            "metric_scorer_path": str(METRIC_PATH), "metric_scorer_sha256": sha(METRIC_PATH),
            "gravity_mps2": gravity, "max_tilt_rad": max_tilt,
            "command_filter_replay": {"wn_rad_s": [18.0, 18.0, 12.0], "damping": [1.0, 1.0, 1.0],
                                       "effective_acceleration_limits_rad_s2": ["unclipped", "unclipped", 6.0]},
            "position_bs_k1_k2_in_raw_log": False,
        },
        "macro_mean_of_scene_rmse_or_rate": macro,
        "candidate_per_scene": scene_rows,
        "interpretation_limit": "Task-to-filtered is a conditional ideal-inner reference-path benchmark on recorded candidate trajectories, not a closed-loop counterfactual or causal attribution.",
        "component_ablation": "Remove only the logged position compensation force while keeping same logged state, BS nominal force, actual-yaw force-to-angle mapping, reference-yaw target, gravity/tilt map, and recorded WN18 command filter. It is an offline same-state component ablation, not a Plant rerun.",
        "single_causal_shape_screen": "One same-state diagnostic only: causal first-order 10-Hz low-pass on the logged compensation force, initialized at its first sample; BS feedback remains intact. Not a closed-loop prediction.",
        "single_fixed_amplitude_screen": "One same-state diagnostic only: alpha=0.9 scales only the NN compensation force; BS nominal force, force-to-attitude mapping, WN18 filter, and recorded state remain fixed. No alpha sweep; not a closed-loop prediction.",
        "highpass_band_hz": {"cutoff": 10.0, "sample_rate": 1000.0},
    }
    OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "scene_count": len(scene_rows), "macro": macro,
                      "output": str(OUTPUT)}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
