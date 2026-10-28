#!/usr/bin/env python3
"""Frozen same-scene score and W09 2.2/3.2-Hz spectra for the one T1 diagnostic call."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import h5py
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
REPLAY = ROOT / "experiments/dl_attitude_replacement_20261028/position_compensation_dual_notch_train_replay_v1"
PREFILTER = ROOT / "experiments/dl_attitude_replacement_20261028/position_dc_penalty_oof_train_pair_preflight_W09_T1_C10_attempt014_v1"
SCORE_SOURCE = ROOT / "experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_full72_v1/audits/score_full72_candidate_v1.py"
CONSTANTS = ROOT / "experiments/dl_attitude_replacement_20261026/mlp15_composite_dev_v3/RELEASE.json"
PLAN_PATH = HERE / "SINGLE_CALL_PLAN_T1_v1.json"
OUT = HERE / "audits/DUAL_NOTCH_SINGLE_CALL_T1_SCORE_v1.json"
FS_HZ = 1_000.0
TRANSITIONS = 20_000
SCENE_ID = "DL1018_DEV_T1_C10_W09"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_log(raw: h5py.File, key: str) -> np.ndarray:
    return np.asarray(raw["log"][key][()], dtype=np.float64).T


def wrapped_delta(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    d = a - b
    return np.arctan2(np.sin(d), np.cos(d))


def force_to_task_euler(acceleration: np.ndarray, yaw: np.ndarray, max_tilt: float) -> np.ndarray:
    specific = acceleration.copy()
    specific[:, 2] += 9.8
    cy, sy = np.cos(yaw), np.sin(yaw)
    a = cy * specific[:, 0] + sy * specific[:, 1]
    b = sy * specific[:, 0] - cy * specific[:, 1]
    roll = np.arctan2(b, np.hypot(specific[:, 2], a))
    pitch = np.arctan2(a, specific[:, 2])
    tilt = np.hypot(roll, pitch)
    scale = np.ones_like(tilt)
    over = tilt > max_tilt
    scale[over] = max_tilt / tilt[over]
    return np.column_stack((roll * scale, pitch * scale, yaw))


def vector_band_rms(signal: np.ndarray, low_hz: float, high_hz: float) -> float:
    x = np.asarray(signal, dtype=np.float64)
    if x.ndim == 1:
        x = x[:, None]
    x = x - np.mean(x, axis=0, keepdims=True)
    n = x.shape[0]
    window = np.hanning(n)
    spectrum = np.fft.rfft(x * window[:, None], axis=0)
    psd = np.abs(spectrum) ** 2 / (FS_HZ * np.sum(window**2))
    if n % 2 == 0:
        psd[1:-1] *= 2.0
    else:
        psd[1:] *= 2.0
    frequencies = np.fft.rfftfreq(n, d=1.0 / FS_HZ)
    selected = (frequencies >= low_hz) & (frequencies < high_hz)
    power = np.sum(psd[selected], axis=0) * (FS_HZ / n)
    return float(np.sqrt(np.sum(power)))


def spectrum_for_raw(raw_path: Path, max_tilt: float) -> dict:
    with h5py.File(raw_path, "r") as raw:
        accel = np.asarray(raw["scene/reference/acceleration"][()], dtype=np.float64).T[:TRANSITIONS]
        yaw = np.asarray(raw["scene/reference/yaw"][()], dtype=np.float64).reshape(-1)[:TRANSITIONS]
        state = read_log(raw, "state")[:TRANSITIONS]
        command = read_log(raw, "command_filter_target_euler")
        filtered = read_log(raw, "filtered_attitude_reference")
    if accel.shape != (TRANSITIONS, 3) or yaw.shape != (TRANSITIONS,) or state.shape[0] != TRANSITIONS:
        raise RuntimeError(f"Unexpected W09 reference/state shapes in {raw_path}")
    task = force_to_task_euler(accel, yaw, max_tilt)
    actual = state[:, 6:9]
    error = wrapped_delta(task, actual)
    bands = {"peak_2p2": (1.5, 2.5), "peak_3p2": (2.5, 3.5)}
    output = {}
    for name, (low, high) in bands.items():
        output[name] = {
            "band_hz": [low, high],
            "task_minus_actual_wrapped_euler_vector_rms_mrad": vector_band_rms(error, low, high) * 1e3,
            "command_filter_target_vector_rms_mrad": vector_band_rms(command, low, high) * 1e3,
            "filtered_attitude_reference_vector_rms_mrad": vector_band_rms(filtered, low, high) * 1e3,
            "actual_euler_vector_rms_mrad": vector_band_rms(actual, low, high) * 1e3,
            "task_euler_vector_rms_mrad": vector_band_rms(task, low, high) * 1e3,
        }
    return output


def main() -> None:
    if OUT.exists():
        raise RuntimeError(f"Refusing to overwrite {OUT}")
    plan = read_json(PLAN_PATH)
    release = read_json(HERE / "RELEASE.json")
    binding = read_json(HERE / "TRAIN_SCENE_BINDING_v1.json")
    status_path = HERE / "runs" / SCENE_ID / "attempt_01" / "run_status.json"
    candidate_raw = HERE / "runs" / SCENE_ID / "attempt_01" / "raw_run.mat"
    status = read_json(status_path)
    if (plan["status"] != "PREDECLARED_BEFORE_SINGLE_CALL" or plan["scope"]["scene_id"] != SCENE_ID or
            release["study_id"] != plan["study_id"] or status.get("scene_id") != SCENE_ID or
            status.get("state") != "COMPLETED" or status.get("status_value") != "STABLE" or
            status.get("transitions") != TRANSITIONS or status.get("state_samples") != TRANSITIONS + 1 or
            status.get("Plant_calls") != 1 or status.get("VAL_data_read") is not False or
            status.get("TEST_read") is not False or not candidate_raw.is_file()):
        raise RuntimeError("The single authorized T1 attempt is incomplete or outside the frozen scope.")
    candidate_sha = sha256(candidate_raw)
    if candidate_sha.lower() != str(status.get("raw_sha256", "")).lower():
        raise RuntimeError("Candidate raw/status SHA mismatch.")

    pre_score_path = PREFILTER / "audits/TRAIN_SINGLE_SCENE_PAIRED_SCORE_v1.json"
    pre_report = read_json(REPLAY / "TRAIN_FROZEN_DUAL_NOTCH_REPLAY_v1.json")
    pre_row = next(row for row in pre_report["results"] if row["scene_id"] == SCENE_ID)
    pre_raw = Path(pre_row["candidate_raw_path"]).resolve(strict=True)
    pre_status = pre_raw.with_name("run_status.json")
    specs = {
        "B": (Path(binding["b72_scoring_raw_path"]).resolve(strict=True), Path(binding["b72_scoring_status_path"]).resolve(strict=True), binding["b72_scoring_raw_sha256"], binding["b72_scoring_status_sha256"]),
        "C5": (Path(binding["c5_raw_path"]).resolve(strict=True), Path(binding["c5_status_path"]).resolve(strict=True), binding["c5_raw_sha256"], binding["c5_status_sha256"]),
        "parent_GRU": (Path(binding["parent_raw_path"]).resolve(strict=True), Path(binding["parent_status_path"]).resolve(strict=True), binding["parent_raw_sha256"], binding["parent_status_sha256"]),
        "candidate_pre_dual_notch": (pre_raw, pre_status, pre_row["candidate_raw_sha256"], sha256(pre_status)),
        "dual_notch_candidate": (candidate_raw.resolve(), status_path.resolve(), candidate_sha, sha256(status_path)),
    }
    for name, (raw_path, stat_path, raw_hash, stat_hash) in specs.items():
        if sha256(raw_path).lower() != str(raw_hash).lower() or sha256(stat_path).lower() != str(stat_hash).lower():
            raise RuntimeError(f"Frozen raw/status hash mismatch: {name}")
        st = read_json(stat_path)
        if st.get("scene_id") != SCENE_ID or any(st.get(k) is True for k in ("TEST_read", "TEST_accessed", "test_data_read")):
            raise RuntimeError(f"Source is not the exact TRAIN scene or reports TEST access: {name}")

    score_spec = importlib.util.spec_from_file_location("frozen_full72_score", SCORE_SOURCE)
    if score_spec is None or score_spec.loader is None:
        raise RuntimeError("Cannot load the locked frozen score implementation.")
    scorer = importlib.util.module_from_spec(score_spec)
    score_spec.loader.exec_module(scorer)
    constants = read_json(CONSTANTS)
    gravity, max_tilt = float(constants["gravity_mps2"]), float(constants["max_tilt_rad"])
    scores = {}
    spectra = {}
    raw_bindings = {}
    for name, (raw_path, stat_path, raw_hash, stat_hash) in specs.items():
        metrics = scorer.score_raw(raw_path, gravity, max_tilt)
        scores[name] = metrics
        spectra[name] = spectrum_for_raw(raw_path, max_tilt)
        raw_bindings[name] = {"raw_path": str(raw_path), "raw_sha256": raw_hash,
                              "status_path": str(stat_path), "status_sha256": stat_hash}
    pre_q = float(scores["candidate_pre_dual_notch"]["Q_m"])
    new_q = float(scores["dual_notch_candidate"]["Q_m"])
    q_worsening = 100.0 * (new_q - pre_q) / pre_q if pre_q else None
    reductions = {}
    for band in ("peak_2p2", "peak_3p2"):
        before = spectra["candidate_pre_dual_notch"][band]["task_minus_actual_wrapped_euler_vector_rms_mrad"]
        after = spectra["dual_notch_candidate"][band]["task_minus_actual_wrapped_euler_vector_rms_mrad"]
        reductions[band] = 100.0 * (before - after) / before if before else 0.0
    safety = scores["dual_notch_candidate"]["safety"]
    safety_names = ("motor_saturation_samples", "generalized_clip_samples", "tilt_limited_samples",
                    "attitude_head_projection_samples", "attitude_head_output_saturated_samples")
    safe = all(int(safety.get(name, 0)) == 0 for name in safety_names)
    limits = plan["single_call_falsifier"]
    passed = (all(value >= limits["task_minus_actual_band_rms_reduction_percent_min_each_band_vs_candidate_pre_dual_notch"] for value in reductions.values()) and
              q_worsening is not None and q_worsening <= limits["Q_m_relative_worsening_percent_max_vs_candidate_pre_dual_notch"] and safe)
    result = {
        "schema": "POSITION_COMPENSATION_DUAL_NOTCH_SINGLE_CALL_T1_FROZEN_SCORE_V1",
        "status": "PASS_T1_SINGLE_CALL_FALSIFIER" if passed else "FAIL_T1_SINGLE_CALL_FALSIFIER",
        "study_id": plan["study_id"], "scene_id": SCENE_ID, "source_split": "TRAIN_C5_24", "fold_id": binding["fold_id"],
        "release_sha256": sha256(HERE / "RELEASE.json"), "source_lock_sha256": sha256(HERE / "SOURCE_LOCK_SINGLE_CALL_v1.json"),
        "single_call_plan_sha256": sha256(PLAN_PATH), "prior_no_plant_preflight_sha256": release["prior_no_plant_preflight_sha256"],
        "plant_calls": 1, "TEST_read": False, "VAL_read": False, "inertia_reconstruction_enabled": False,
        "frozen_replay_status_preserved": "FAIL_FIXED_FROZEN_REPLAY",
        "frozen_score_source_path": str(SCORE_SOURCE.resolve()), "frozen_score_source_sha256": sha256(SCORE_SOURCE),
        "score_constants_sha256": sha256(CONSTANTS), "gravity_mps2": gravity, "max_tilt_rad": max_tilt,
        "same_scene_raw_bindings": raw_bindings, "frozen_scores": scores, "w09_spectra": spectra,
        "falsifier": {"task_minus_actual_reduction_percent_vs_pre_dual_notch": reductions,
                      "Q_m_relative_worsening_percent_vs_pre_dual_notch": q_worsening,
                      "safety_counters_all_zero": safe, "limits": limits},
        "interpretation": "One T1 W09 closed-loop mechanism diagnostic only. The intervention has no cross-wind-spectrum generalization claim.",
    }
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUT.resolve()), "status": result["status"],
                      "dual_notch_candidate": {k: scores["dual_notch_candidate"].get(k) for k in scorer.MAIN},
                      "task_actual_reduction_percent": reductions, "Q_worsening_percent": q_worsening,
                      "safe": safe}, indent=2))


if __name__ == "__main__":
    main()
