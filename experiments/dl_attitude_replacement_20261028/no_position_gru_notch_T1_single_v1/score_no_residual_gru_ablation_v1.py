#!/usr/bin/env python3
"""Frozen same-scene score and W09 spectra for a no-position-GRU dual-notch call."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import h5py
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PLAN_PATH = HERE / "SINGLE_CALL_PLAN_v1.json"
OUT = HERE / "audits/NO_RESIDUAL_GRU_DUAL_NOTCH_SCORE_v1.json"
SCORE_SOURCE = ROOT / "experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_full72_v1/audits/score_full72_candidate_v1.py"
CONSTANTS = ROOT / "experiments/dl_attitude_replacement_20261026/mlp15_composite_dev_v3/RELEASE.json"
FS_HZ = 1000.0
TRANSITIONS = 20000


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_log(raw: h5py.File, key: str) -> np.ndarray:
    return np.asarray(raw["log"][key][()], dtype=np.float64).T


def wrap_delta(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    d = a - b
    return np.arctan2(np.sin(d), np.cos(d))


def force_to_task_euler(accel: np.ndarray, yaw: np.ndarray, max_tilt: float) -> np.ndarray:
    specific = accel.copy()
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


def band_rms(signal: np.ndarray, lo: float, hi: float) -> float:
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
    freq = np.fft.rfftfreq(n, d=1.0 / FS_HZ)
    selected = (freq >= lo) & (freq < hi)
    power = np.sum(psd[selected], axis=0) * (FS_HZ / n)
    return float(np.sqrt(np.sum(power)))


def spectrum(raw_path: Path, max_tilt: float) -> dict:
    with h5py.File(raw_path, "r") as raw:
        accel = np.asarray(raw["scene/reference/acceleration"][()], dtype=np.float64).T[:TRANSITIONS]
        yaw = np.asarray(raw["scene/reference/yaw"][()], dtype=np.float64).reshape(-1)[:TRANSITIONS]
        state = read_log(raw, "state")[:TRANSITIONS]
        command = read_log(raw, "command_filter_target_euler")
        filtered = read_log(raw, "filtered_attitude_reference")
    task = force_to_task_euler(accel, yaw, max_tilt)
    error = wrap_delta(task, state[:, 6:9])
    result = {}
    for name, lo, hi in (("peak_2p2", 1.5, 2.5), ("peak_3p2", 2.5, 3.5)):
        result[name] = {
            "band_hz": [lo, hi],
            "task_minus_actual_wrapped_euler_vector_rms_mrad": band_rms(error, lo, hi) * 1e3,
            "command_filter_target_vector_rms_mrad": band_rms(command, lo, hi) * 1e3,
            "filtered_attitude_reference_vector_rms_mrad": band_rms(filtered, lo, hi) * 1e3,
            "actual_euler_vector_rms_mrad": band_rms(state[:, 6:9], lo, hi) * 1e3,
            "task_euler_vector_rms_mrad": band_rms(task, lo, hi) * 1e3,
        }
    return result


def main() -> None:
    if OUT.exists():
        raise RuntimeError(f"Refusing to overwrite {OUT}")
    plan = read_json(PLAN_PATH)
    release = read_json(HERE / "RELEASE.json")
    binding = read_json(HERE / "TRAIN_SCENE_BINDING_v1.json")
    scene_id = plan["scene_id"]
    attempt = HERE / "runs" / scene_id / "attempt_01"
    candidate_raw, candidate_status = attempt / "raw_run.mat", attempt / "run_status.json"
    raw_audit = read_json(HERE / "audits/NO_RESIDUAL_GRU_RAW_VALIDATION_v1.json")
    status = read_json(candidate_status)
    if (release["study_id"] != plan["study_id"] or release["status"] != "RELEASED" or
            plan["status"] != "PREDECLARED_BEFORE_SINGLE_CALL" or
            status.get("scene_id") != scene_id or status.get("state") != "COMPLETED" or
            status.get("status_value") != "STABLE" or status.get("transitions") != TRANSITIONS or
            status.get("state_samples") != TRANSITIONS + 1 or status.get("Plant_calls") != 1 or
            status.get("TEST_read") is not False or status.get("VAL_data_read") is not False or
            raw_audit.get("status") != "PASS_NO_POSITION_GRU_EVENTS_OR_CORRECTION"):
        raise RuntimeError("The ablation attempt or raw contract is incomplete/out of scope.")

    refs = plan["score_inputs"]
    specs = {}
    for name, item in refs.items():
        path, stat = Path(item["raw_path"]).resolve(strict=True), Path(item["status_path"]).resolve(strict=True)
        if sha(path) != item["raw_sha256"] or sha(stat) != item["status_sha256"]:
            raise RuntimeError(f"Frozen input hash changed: {name}")
        s = read_json(stat)
        if s.get("scene_id") != scene_id or s.get("TEST_read") is True or s.get("VAL_data_read") is True:
            raise RuntimeError(f"Frozen input outside the physical TRAIN scene/scope: {name}")
        specs[name] = (path, stat, item["raw_sha256"], item["status_sha256"])
    raw_sha = sha(candidate_raw)
    if raw_sha != status.get("raw_sha256"):
        raise RuntimeError("Candidate raw/status SHA mismatch.")
    specs["dual_notch_no_position_residual_gru"] = (
        candidate_raw.resolve(), candidate_status.resolve(), raw_sha, sha(candidate_status))

    module_spec = importlib.util.spec_from_file_location("frozen_full72_score", SCORE_SOURCE)
    if module_spec is None or module_spec.loader is None:
        raise RuntimeError("Cannot import the locked full72 score implementation.")
    scorer = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(scorer)
    constants = read_json(CONSTANTS)
    gravity, max_tilt = float(constants["gravity_mps2"]), float(constants["max_tilt_rad"])
    scores, spectra, bindings = {}, {}, {}
    for name, (raw, stat, raw_hash, stat_hash) in specs.items():
        scores[name] = scorer.score_raw(raw, gravity, max_tilt)
        spectra[name] = spectrum(raw, max_tilt)
        bindings[name] = {"raw_path": str(raw), "raw_sha256": raw_hash,
                          "status_path": str(stat), "status_sha256": stat_hash}

    no_gru = scores["dual_notch_no_position_residual_gru"]
    with_gru = scores["dual_notch_with_position_residual_gru"]
    q_extra = with_gru["Q_m"] - no_gru["Q_m"]
    task_extra = with_gru["task_SO3_rad"] - no_gru["task_SO3_rad"]
    inner_extra = with_gru["inner_SO3_rad"] - no_gru["inner_SO3_rad"]
    spectral = {}
    for band in ("peak_2p2", "peak_3p2"):
        no_err = spectra["dual_notch_no_position_residual_gru"][band]["task_minus_actual_wrapped_euler_vector_rms_mrad"]
        with_err = spectra["dual_notch_with_position_residual_gru"][band]["task_minus_actual_wrapped_euler_vector_rms_mrad"]
        spectral[band] = {
            "no_position_gru_error_mrad": no_err,
            "with_position_gru_error_mrad": with_err,
            "no_position_gru_minus_with_position_gru_mrad": no_err - with_err,
        }
    result = {
        "schema": "POSITION_DUAL_NOTCH_NO_POSITION_RESIDUAL_GRU_FROZEN_SCORE_V1",
        "status": "MEASURED_FIXED_TRAIN_ABLATION",
        "study_id": plan["study_id"], "scene_id": scene_id, "source_split": "TRAIN_C5_24",
        "fold_id": binding["fold_id"], "matlab_release": "R2025b",
        "Plant_calls": 1, "TEST_read": False, "VAL_read": False,
        "inertia_reconstruction_enabled": False,
        "frozen_replay_status_preserved": "FAIL_FIXED_FROZEN_REPLAY",
        "fixed_intervention": plan["fixed_intervention"],
        "frozen_score_source_path": str(SCORE_SOURCE.resolve()), "frozen_score_source_sha256": sha(SCORE_SOURCE),
        "score_constants_sha256": sha(CONSTANTS), "same_scene_raw_bindings": bindings,
        "frozen_scores": scores, "w09_spectra": spectra,
        "incremental_position_gru_effect_with_same_filter": {
            "Q_m_with_gru_minus_without_gru": q_extra,
            "Q_m_relative_to_without_gru_percent": 100.0 * q_extra / no_gru["Q_m"] if no_gru["Q_m"] else None,
            "task_SO3_rad_with_gru_minus_without_gru": task_extra,
            "inner_SO3_rad_with_gru_minus_without_gru": inner_extra,
            "interpretation": "Positive Q delta means the added position residual GRU increased position error in this fixed scene.",
            "high_frequency_error_with_minus_without": spectral,
        },
        "safety": {
            "no_position_gru": no_gru["safety"],
            "with_position_gru": with_gru["safety"],
            "no_position_gru_raw_contract": raw_audit,
        },
        "interpretation_limit": "Single fixed W09 TRAIN scene ablation; no cross-wind generalization and no change to the frozen replay FAIL.",
    }
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUT.resolve()), "status": result["status"],
                      "scene_id": scene_id, "no_residual_gru": {k: no_gru[k] for k in scorer.MAIN},
                      "with_residual_gru": {k: with_gru[k] for k in scorer.MAIN},
                      "incremental_position_gru_Q_delta": q_extra,
                      "high_frequency_error_with_minus_without": spectral}, indent=2))


if __name__ == "__main__":
    main()
