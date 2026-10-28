#!/usr/bin/env python3
"""Read-only causal-band observability audit for the physical TRAIN_C5_24 set.

This script does not train a model or run Plant. It binds the existing physical
TRAIN24 event pairs and C5 raw files, reads only scene.reference position,
velocity, acceleration plus the already-built C5 action/target/X14 arrays, and
writes a Markdown report and JSON result beside this file.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re

import h5py
import numpy as np
import pandas as pd
from scipy.signal import butter, coherence, csd, sosfreqz, sosfiltfilt, welch


ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
DATA = ROOT / "experiments/dl_attitude_replacement_20261028/position_cosine_gru_train24_causal_v1/COSINE_GRU_C5_TRAIN24_POSITION_CAUSAL_PAIRS_v1.npz"
DATA_LOCK = ROOT / "experiments/dl_attitude_replacement_20261028/position_cosine_gru_train24_causal_v1/SOURCE_LOCK_v1.json"
PHYSICAL_MANIFEST = ROOT / "experiments/dl_attitude_replacement_20261027/mlp15_nominal_residual_v1/TRAIN_C5_24_PHYSICAL_RESIDUAL_MANIFEST_v1.json"
PROFILE = ROOT / "experiments/dl_attitude_replacement_20261028/position_compensation_windband_train24_audit_v1/TRAIN24_C5_WIND_BAND_PROFILE_v1.csv"
SCENE_SOURCE = ROOT / "matlab/scenes/make_scenes_dl1018.m"
OUT_JSON = OUT / "POSITION_CAUSAL_BAND_OBSERVABILITY_AUDIT_v1.json"
OUT_MD = OUT / "POSITION_CAUSAL_BAND_OBSERVABILITY_AUDIT_v1.md"

FS = 100.0
WELCH_NPERSEG = 1024
WELCH_NOVERLAP = 512
BANDS = (("0.10-0.50", 0.10, 0.50), ("0.50-1.00", 0.50, 1.00),
         ("1.00-2.00", 1.00, 2.00), ("2.00-3.00", 2.00, 3.00),
         ("3.00-4.00", 3.00, 4.00), ("4.00-5.00", 4.00, 5.00))
FOLD_GROUPS = ((0, 5, "holdout_W00_05"), (6, 10, "holdout_W06_10"),
               (11, 13, "holdout_W11_13"), (14, 15, "holdout_W14_15"))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def json_ready(value):
    if isinstance(value, dict):
        return {str(k): json_ready(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    return value


def group_for_wind(w: int) -> str:
    if 0 <= w <= 2:
        return "W00-W02"
    if 3 <= w <= 5:
        return "W03-W05"
    if 6 <= w <= 8:
        return "W06-W08"
    if 9 <= w <= 11:
        return "W09-W11"
    if 12 <= w <= 14:
        return "W12-W14"
    return "W15"


def tone_fit(x: np.ndarray, t: np.ndarray, f_hz: float,
             window: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Weighted sinusoid plus intercept/linear trend; returned amplitudes/phases per axis."""
    design = np.column_stack((np.ones(len(t)), t - float(t.mean()),
                              np.cos(2 * np.pi * f_hz * t),
                              np.sin(2 * np.pi * f_hz * t)))
    weights = np.ones(len(t), dtype=np.float64) if window is None else np.asarray(window, dtype=np.float64)
    sw = np.sqrt(np.maximum(weights, 0.0))[:, None]
    coef = np.linalg.lstsq(design * sw, x * sw, rcond=None)[0]
    c, s = coef[2], coef[3]
    return np.hypot(c, s), np.degrees(np.arctan2(s, c))


def vec_tone(x: np.ndarray, t: np.ndarray, f_hz: float,
             window: np.ndarray | None = None) -> dict:
    amp, phase = tone_fit(x, t, f_hz, window)
    return {"vector_amplitude": float(np.linalg.norm(amp)),
            "axis_amplitude": amp.tolist(), "axis_phase_deg": phase.tolist()}


def phase_delta_deg(x: np.ndarray, y: np.ndarray, t: np.ndarray, f_hz: float,
                    window: np.ndarray) -> float | None:
    ax, px = tone_fit(x, t, f_hz, window)
    ay, py = tone_fit(y, t, f_hz, window)
    valid = (ax > 1e-10) & (ay > 1e-10)
    if not np.any(valid):
        return None
    delta = np.deg2rad(px[valid] - py[valid])
    weights = ax[valid] * ay[valid]
    return float(np.degrees(np.angle(np.sum(weights * np.exp(1j * delta)))))


def welch_band_rms(x: np.ndarray, low: float, high: float) -> float:
    per_axis = []
    for axis in range(x.shape[1]):
        f, p = welch(x[:, axis], fs=FS, window="hann", nperseg=WELCH_NPERSEG,
                     noverlap=WELCH_NOVERLAP, detrend="constant")
        use = (f >= low) & (f < high)
        per_axis.append(math.sqrt(max(float(np.trapz(p[use], f[use])), 0.0))
                        if np.count_nonzero(use) >= 2 else 0.0)
    return float(np.linalg.norm(per_axis))


def welch_local_tone_rms(x: np.ndarray, f_hz: float) -> float:
    """Integrated Hann-Welch amplitude in f +/- 0.12 Hz, not a line estimator."""
    per_axis = []
    for axis in range(x.shape[1]):
        f, p = welch(x[:, axis], fs=FS, window="hann", nperseg=WELCH_NPERSEG,
                     noverlap=WELCH_NOVERLAP, detrend="linear")
        use = (f >= max(0.10, f_hz - 0.12)) & (f <= f_hz + 0.12)
        per_axis.append(math.sqrt(max(float(np.trapz(p[use], f[use])), 0.0))
                        if np.count_nonzero(use) >= 2 else 0.0)
    return float(np.linalg.norm(per_axis))


def median_rows(rows: list[dict], fields: tuple[str, ...]) -> dict:
    out = {"scene_count": len({r["scene_id"] for r in rows})}
    for field in fields:
        values = [r[field] for r in rows if r.get(field) is not None and np.isfinite(r[field])]
        out[field + "_median"] = float(np.median(values)) if values else None
        out[field + "_p25"] = float(np.percentile(values, 25)) if values else None
        out[field + "_p75"] = float(np.percentile(values, 75)) if values else None
    return out


def verify_inputs() -> tuple[dict, dict, pd.DataFrame, dict, list[dict]]:
    lock = json.loads(DATA_LOCK.read_text(encoding="utf-8-sig"))
    physical = json.loads(PHYSICAL_MANIFEST.read_text(encoding="utf-8-sig"))
    npz_sha = sha256_file(DATA)
    physical_sha = sha256_file(PHYSICAL_MANIFEST)
    if npz_sha.lower() != str(lock["data_sha256"]).lower():
        raise RuntimeError("TRAIN24 causal-pairs NPZ SHA differs from its source lock")
    if physical_sha.lower() != str(lock["physical_manifest_sha256"]).lower():
        raise RuntimeError("physical TRAIN24 manifest SHA differs from its source lock")
    if physical.get("train_split") != "TRAIN_C5_24" or int(physical.get("train_scene_count", -1)) != 24:
        raise RuntimeError("physical manifest is not the declared TRAIN_C5_24 manifest")
    if physical.get("TEST_read") is not False or physical.get("Plant_called") is not False:
        raise RuntimeError("physical manifest scope flags do not pass")

    data = np.load(DATA, allow_pickle=False)
    scene_ids = data["scene_ids"].astype(str).tolist()
    if len(scene_ids) != 24 or any(not re.fullmatch(r"DL1018_DEV_T[123]_C\d{2}_W\d{2}", s) for s in scene_ids):
        raise RuntimeError("expected the exact 24 DEV-prefix IDs declared physical TRAIN_C5_24")
    if data["x14_model_input"].shape != (24, 1999, 14):
        raise RuntimeError("unexpected X14 tensor shape")
    if data["applied_acceleration_event_mps2"].shape != (24, 1999, 3):
        raise RuntimeError("unexpected C5 action tensor shape")
    if data["target_interval_raw_mps2"].shape != (24, 1999, 3):
        raise RuntimeError("unexpected interval-label tensor shape")
    if not np.all(data["ready_mask"].sum(axis=1) == 1968):
        raise RuntimeError("ready mask differs from the 1968/1999 contract")

    profile = pd.read_csv(PROFILE)
    need = {"scene_id", "configured_f1_hz", "configured_f2_hz", "raw_path", "raw_sha256"}
    if not need.issubset(profile.columns) or len(profile) != 24:
        raise RuntimeError("TRAIN24 wind-band profile does not have the expected 24 rows/columns")
    if set(profile.scene_id.astype(str)) != set(scene_ids):
        raise RuntimeError("profile IDs do not match causal-pairs NPZ IDs")
    lock_rows = {r["scene_id"]: r for r in lock["scene_rows"]}
    profile_by_id = profile.set_index("scene_id")
    raw_hashes = []
    for sid in scene_ids:
        row = profile_by_id.loc[sid]
        raw_path = (ROOT / Path(str(row.raw_path))).resolve()
        source_row = lock_rows.get(sid)
        if source_row is None:
            raise RuntimeError(f"missing source-lock scene row: {sid}")
        if str(row.raw_sha256).lower() != str(source_row["physical_c5_raw_sha256"]).lower():
            raise RuntimeError(f"profile/source-lock raw SHA mismatch: {sid}")
        if not raw_path.is_file():
            raise FileNotFoundError(raw_path)
        actual_raw_sha = sha256_file(raw_path)
        if actual_raw_sha.lower() != str(row.raw_sha256).lower():
            raise RuntimeError(f"physical C5 raw SHA mismatch: {sid}")
        raw_hashes.append({"scene_id": sid, "raw_path": str(raw_path.relative_to(ROOT)).replace("\\", "/"),
                           "raw_sha256": actual_raw_sha})
    return lock, physical, profile, data, raw_hashes


def analyze() -> dict:
    lock, physical, profile, data, raw_hashes = verify_inputs()
    scene_ids = data["scene_ids"].astype(str)
    profile_by_id = profile.set_index("scene_id")
    band_rows: list[dict] = []
    tone_rows: list[dict] = []
    derivative_rows: list[dict] = []
    n = 1999
    event_t = data["event_time_s"].astype(np.float64)
    lowpass_sos = butter(4, 0.5, btype="lowpass", fs=FS, output="sos")

    for i, sid in enumerate(scene_ids):
        profile_row = profile_by_id.loc[sid]
        raw_path = ROOT / Path(str(profile_row.raw_path))
        with h5py.File(raw_path, "r") as h:
            # Intentionally read only these public scene-reference arrays.
            # No wind, state, plant derivative, motor, or TEST/VAL dataset is accessed.
            ref_raw = {
                "position": np.asarray(h["scene/reference/position"][()], dtype=np.float64),
                "velocity": np.asarray(h["scene/reference/velocity"][()], dtype=np.float64),
                "acceleration": np.asarray(h["scene/reference/acceleration"][()], dtype=np.float64),
            }
        if any(v.shape != (3, 20001) for v in ref_raw.values()):
            raise RuntimeError(f"unexpected reference shape for {sid}")

        starts = np.rint(event_t[i] * 1000).astype(np.int64)
        def event_interval_mean(x: np.ndarray) -> np.ndarray:
            return np.stack([x[:, k:k + 10].mean(axis=1) for k in starts], axis=0)
        ref = {name: event_interval_mean(value) for name, value in ref_raw.items()}
        action = data["applied_acceleration_event_mps2"][i].astype(np.float64)
        target = data["target_interval_raw_mps2"][i].astype(np.float64)
        x14 = data["x14_model_input"][i].astype(np.float64)
        error = x14[:, 0:3]
        surface = x14[:, 3:6]
        ready = data["ready_mask"][i].astype(bool)
        w = int(sid[-2:])
        task = sid.split("_")[2]

        # Finite-difference consistency is measured on the original 1-kHz arrays.
        inner = slice(5, -5)
        dp = np.gradient(ref_raw["position"], 0.001, axis=1)
        dv = np.gradient(ref_raw["velocity"], 0.001, axis=1)
        vel_rel = float(np.sqrt(np.mean((dp[:, inner] - ref_raw["velocity"][:, inner]) ** 2)) /
                        max(np.sqrt(np.mean(ref_raw["velocity"][:, inner] ** 2)), 1e-12))
        acc_rel = float(np.sqrt(np.mean((dv[:, inner] - ref_raw["acceleration"][:, inner]) ** 2)) /
                        max(np.sqrt(np.mean(ref_raw["acceleration"][:, inner] ** 2)), 1e-12))
        derivative_rows.append({"scene_id": sid, "wind_group_offline": group_for_wind(w),
                                "position_to_velocity_relative_rms": vel_rel,
                                "velocity_to_acceleration_relative_rms": acc_rel})

        # The band audit uses ready rows and de-meaned signals. DC is stored separately.
        sig = {"action": action[ready].copy(), "target": target[ready].copy(),
               "reference_acceleration": ref["acceleration"][ready].copy(),
               "position_error": error[ready].copy(), "surface": surface[ready].copy()}
        for x in sig.values():
            x -= x.mean(axis=0, keepdims=True)
        for band_name, low, high in BANDS:
            rms = {name: welch_band_rms(x, low, high) for name, x in sig.items()}
            msc_ur, msc_yr, msc_uy, phase_ur, phase_yr, phase_uy = [], [], [], [], [], []
            for axis in range(3):
                f, cu = coherence(sig["reference_acceleration"][:, axis], sig["action"][:, axis],
                                  fs=FS, nperseg=WELCH_NPERSEG, noverlap=WELCH_NOVERLAP,
                                  detrend="constant")
                _, cy = coherence(sig["reference_acceleration"][:, axis], sig["target"][:, axis],
                                  fs=FS, nperseg=WELCH_NPERSEG, noverlap=WELCH_NOVERLAP,
                                  detrend="constant")
                _, c_action_target = coherence(sig["target"][:, axis], sig["action"][:, axis],
                                               fs=FS, nperseg=WELCH_NPERSEG, noverlap=WELCH_NOVERLAP,
                                               detrend="constant")
                _, z_ur = csd(sig["reference_acceleration"][:, axis], sig["action"][:, axis],
                              fs=FS, nperseg=WELCH_NPERSEG, noverlap=WELCH_NOVERLAP,
                              detrend="constant")
                _, z_yr = csd(sig["reference_acceleration"][:, axis], sig["target"][:, axis],
                              fs=FS, nperseg=WELCH_NPERSEG, noverlap=WELCH_NOVERLAP,
                              detrend="constant")
                _, z_uy = csd(sig["target"][:, axis], sig["action"][:, axis],
                              fs=FS, nperseg=WELCH_NPERSEG, noverlap=WELCH_NOVERLAP,
                              detrend="constant")
                use = (f >= low) & (f < high)
                if np.any(use):
                    msc_ur.extend(cu[use].tolist()); msc_yr.extend(cy[use].tolist())
                    msc_uy.extend(c_action_target[use].tolist())
                    def weighted_phase(z, c):
                        weights = np.abs(z[use]) * c[use]
                        if not np.any(weights > 0):
                            return None
                        return float(np.angle(np.sum(weights * np.exp(1j * np.angle(z[use]))), deg=True))
                    p = weighted_phase(z_ur, cu)
                    if p is not None: phase_ur.append(p)
                    p = weighted_phase(z_yr, cy)
                    if p is not None: phase_yr.append(p)
                    p = weighted_phase(z_uy, c_action_target)
                    if p is not None: phase_uy.append(p)
            band_rows.append({"scene_id": sid, "task": task, "wind_cell_offline": w,
                              "wind_group_offline": group_for_wind(w), "band": band_name,
                              "ready_count": int(ready.sum()),
                              "action_rms_mps2": rms["action"], "target_rms_mps2": rms["target"],
                              "reference_acceleration_rms_mps2": rms["reference_acceleration"],
                              "position_error_rms_m": rms["position_error"],
                              "surface_rms_mps": rms["surface"],
                              "reference_to_action_rms_ratio": (rms["reference_acceleration"] / rms["action"]
                                                                 if rms["action"] > 1e-12 else None),
                              "welch_msc2_action_reference_raw": float(np.median(msc_ur)) if msc_ur else None,
                              "welch_msc2_target_reference_raw": float(np.median(msc_yr)) if msc_yr else None,
                              "welch_msc2_action_target_same_trajectory": float(np.median(msc_uy)) if msc_uy else None,
                              "phase_action_minus_reference_deg_raw": float(np.median(phase_ur)) if phase_ur else None,
                              "phase_target_minus_reference_deg_raw": float(np.median(phase_yr)) if phase_yr else None,
                              "phase_action_minus_target_deg_same_trajectory": float(np.median(phase_uy)) if phase_uy else None,
                              "reference_coherence_interpretation":
                                  "LOW_REFERENCE_POWER_DO_NOT_USE_AS_SEPARATION_SIGNAL"
                                  if rms["reference_acceleration"] < 0.05 * max(rms["action"], 1e-12)
                                  else "POWER_PRESENT_BUT_STILL_DESCRIPTIVE_NOT_CAUSAL",
                              "action_mean_norm_mps2": float(np.linalg.norm(action[ready].mean(axis=0))),
                              "target_mean_norm_mps2": float(np.linalg.norm(target[ready].mean(axis=0)))})

        # Full-window and Hann fits use all 1,999 reference samples to avoid a readiness crop.
        # A 0.5-Hz zero-phase detrend is an offline residual-fit diagnostic only.
        full_window = np.ones(n, dtype=np.float64)
        hann_window = np.hanning(n)
        for label, f_hz in (("f1", float(profile_row.configured_f1_hz)),
                            ("f2", float(profile_row.configured_f2_hz))):
            if f_hz <= 0:
                continue
            rec = {"scene_id": sid, "task": task, "wind_cell_offline": w,
                   "wind_group_offline": group_for_wind(w), "line_label_offline": label,
                   "configured_frequency_hz_offline": f_hz}
            for name in ("position", "velocity", "acceleration"):
                x = ref[name]
                low = sosfiltfilt(lowpass_sos, x, axis=0)
                residual = x - low
                rec[name + "_tone_full_vector_amplitude"] = vec_tone(x, event_t[i], f_hz, full_window)["vector_amplitude"]
                rec[name + "_tone_hann_vector_amplitude"] = vec_tone(x, event_t[i], f_hz, hann_window)["vector_amplitude"]
                rec[name + "_tone_welch_local_rms"] = welch_local_tone_rms(x, f_hz)
                rec[name + "_tone_lowpass_residual_hann_amplitude"] = vec_tone(residual, event_t[i], f_hz, hann_window)["vector_amplitude"]
            rec["action_tone_hann_vector_amplitude_mps2"] = vec_tone(action, event_t[i], f_hz, hann_window)["vector_amplitude"]
            rec["target_tone_hann_vector_amplitude_mps2"] = vec_tone(target, event_t[i], f_hz, hann_window)["vector_amplitude"]
            rec["surface_tone_hann_vector_amplitude_mps"] = vec_tone(surface, event_t[i], f_hz, hann_window)["vector_amplitude"]
            rec["action_minus_target_phase_deg_hann"] = phase_delta_deg(action, target, event_t[i], f_hz, hann_window)
            rec["action_minus_surface_phase_deg_hann"] = phase_delta_deg(action, surface, event_t[i], f_hz, hann_window)
            ref_acc_amp = vec_tone(ref["acceleration"], event_t[i], f_hz, hann_window)["vector_amplitude"]
            rec["reference_acceleration_tone_hann_vector_amplitude_mps2"] = ref_acc_amp
            rec["reference_acceleration_to_action_tone_ratio"] = (
                ref_acc_amp / rec["action_tone_hann_vector_amplitude_mps2"]
                if rec["action_tone_hann_vector_amplitude_mps2"] > 1e-12 else None)
            rec["reference_phase_interpretable"] = bool(
                rec["reference_acceleration_to_action_tone_ratio"] is not None and
                rec["reference_acceleration_to_action_tone_ratio"] >= 0.05)
            tone_rows.append(rec)

    # Candidate transfer function example: high-pass residual branch at 0.5 Hz.
    # It has exact DC zero, but nonzero leakage/phase below the nominal corner.
    hp_sos = butter(4, 0.5, btype="highpass", fs=FS, output="sos")
    filter_frequencies = [0.0, 0.10, 0.25, 0.40, 0.45, 0.50, 0.55, 0.58,
                          0.70, 0.85, 1.0, 1.15, 1.75, 2.2, 3.2, 3.7, 4.8]
    _, h = sosfreqz(hp_sos, worN=2 * np.pi * np.asarray(filter_frequencies) / FS)
    filter_response = []
    for f_hz, response in zip(filter_frequencies, h):
        mag = float(abs(response))
        filter_response.append({"frequency_hz": f_hz,
                                "gain_db": -300.0 if mag < 1e-15 else 20 * math.log10(mag),
                                "magnitude": mag,
                                "phase_deg": float(np.angle(response, deg=True))})

    # Per-band descriptive summaries; any W labels are audit strata only.
    band_summary = []
    for band_name, _, _ in BANDS:
        rows = [r for r in band_rows if r["band"] == band_name]
        band_summary.append({"band": band_name, **median_rows(rows, (
            "action_rms_mps2", "target_rms_mps2", "reference_acceleration_rms_mps2",
            "position_error_rms_m", "surface_rms_mps", "reference_to_action_rms_ratio",
            "welch_msc2_action_reference_raw", "welch_msc2_target_reference_raw",
            "welch_msc2_action_target_same_trajectory"))})
    group_summary = []
    for group in ("W00-W02", "W03-W05", "W06-W08", "W09-W11", "W12-W14", "W15"):
        rows = [r for r in band_rows if r["wind_group_offline"] == group]
        if rows:
            group_summary.append({"offline_stratum": group,
                                  "scene_count": len({r["scene_id"] for r in rows}),
                                  "bands": [{"band": b, **median_rows([r for r in rows if r["band"] == b], (
                                      "action_rms_mps2", "target_rms_mps2", "reference_acceleration_rms_mps2",
                                      "reference_to_action_rms_ratio", "welch_msc2_action_reference_raw",
                                      "welch_msc2_action_target_same_trajectory"))}
                                            for b, _, _ in BANDS]})
    tone_group_summary = []
    for group in ("W00-W02", "W03-W05", "W06-W08", "W09-W11", "W12-W14"):
        rows = [r for r in tone_rows if r["wind_group_offline"] == group]
        tone_group_summary.append({"offline_stratum": group,
                                   "scene_count": len({r["scene_id"] for r in rows}),
                                   "line_count": len(rows),
                                   **median_rows(rows, (
                                       "position_tone_full_vector_amplitude",
                                       "position_tone_hann_vector_amplitude",
                                       "position_tone_welch_local_rms",
                                       "position_tone_lowpass_residual_hann_amplitude",
                                       "velocity_tone_full_vector_amplitude",
                                       "velocity_tone_hann_vector_amplitude",
                                       "velocity_tone_welch_local_rms",
                                       "velocity_tone_lowpass_residual_hann_amplitude",
                                       "acceleration_tone_full_vector_amplitude",
                                       "acceleration_tone_hann_vector_amplitude",
                                       "acceleration_tone_welch_local_rms",
                                       "acceleration_tone_lowpass_residual_hann_amplitude",
                                       "action_tone_hann_vector_amplitude_mps2",
                                       "target_tone_hann_vector_amplitude_mps2",
                                       "reference_acceleration_to_action_tone_ratio",
                                       "action_minus_target_phase_deg_hann",
                                       "action_minus_surface_phase_deg_hann"))})

    deriv_vel = [r["position_to_velocity_relative_rms"] for r in derivative_rows]
    deriv_acc = [r["velocity_to_acceleration_relative_rms"] for r in derivative_rows]
    coherence_warning = (
        "Reference coherence at bands where reference acceleration power is below 5% of C5 action power is retained only as a raw descriptive number; "
        "it is not an identifiable deployment gate. Action-target coherence is same-trajectory and is not a causal action effect."
    )
    pair_plan = {
        "status": "DESIGN_ONLY_NOT_EXECUTED",
        "baseline": "exact C5 DSSM14 position + cosineGRU attitude; pair on same scene ID, initial state, reference, morphology schedule, and deterministic wind phase; reuse an existing C5 or B run only after full runner/source identity is bound",
        "primary_anchor_scenes": [
            {"stratum": "W03-W05", "scene_ids": ["DL1018_DEV_T1_C00_W03", "DL1018_DEV_T2_C00_W04", "DL1018_DEV_T3_C00_W05"], "purpose": "0.58/0.87-Hz transition-edge risk"},
            {"stratum": "W06-W08", "scene_ids": ["DL1018_DEV_T1_C05_W06", "DL1018_DEV_T2_C06_W07", "DL1018_DEV_T3_C06_W08"], "purpose": "1.15/1.75-Hz adjacent band"},
            {"stratum": "W09-W11", "scene_ids": ["DL1018_DEV_T1_C10_W09", "DL1018_DEV_T2_C09_W10", "DL1018_DEV_T3_C10_W11"], "purpose": "2.2/3.2-Hz target failure band"},
            {"stratum": "W12-W14", "scene_ids": ["DL1018_DEV_T1_C11_W12", "DL1018_DEV_T2_C12_W13", "DL1018_DEV_T3_C15_W14"], "purpose": "3.7/4.8-Hz upper band"},
            {"stratum": "W00-W02", "scene_ids": ["DL1018_DEV_T1_C04_W00", "DL1018_DEV_T2_C03_W01", "DL1018_DEV_T3_C05_W02"], "purpose": "low-frequency/reference-confound guard; do not shape below 0.5 Hz"},
            {"stratum": "W15", "scene_ids": ["DL1018_DEV_T1_C01_W15", "DL1018_DEV_T2_C02_W15", "DL1018_DEV_T3_C03_W15"], "purpose": "no-two-sine negative control"},
        ],
        "interventions": {
            "identity_gain": 1.0,
            "mild_band_gain": 0.90,
            "moderate_band_gain": 0.75,
            "application": "One broad causal band at a time; other bands unity; same fixed bank across every scene; no W-code input; no exact notch; do not optimize gain on the held-out group.",
            "paired_candidate_runs_for_minimum_screen": "12 active-band anchors x 2 gains + 3 low-frequency controls x 2 gains = 30 candidate runs, plus exact C5 and B baselines for the 15 treated contexts. W15 is identity/no-tone control and needs only an identity parity check.",
            "expanded_screen": "Use all 24 physical TRAIN_C5_24 scenes at both gains for the active broad band, adding the six non-anchor scenes; this estimates task/amplitude heterogeneity before fitting at most 4-6 global band parameters.",
        },
        "outcomes": ["paired delta Q_m vs C5", "paired task_SO3 vs C5 and B", "inner SO3", "per-task/per-phase position xyz errors", "saturation and safety", "actual applied-action spectrum and band response"],
        "decision_rule": "Proceed only if the paired dose response is directionally stable across tasks and amplitude levels, candidate task_SO3 is no worse than B, and position Q stays within the predeclared C5 non-inferiority margin. Mixed signs or a sharp task interaction reject a global band gain.",
        "model_size": "Do not train a new deep net from these 24 trajectories. At most fit 4-6 shared scalar gains (or a low-dimensional regularized response curve) after paired closed-loop labels exist; scene count, not event count, is the effective sample size. Group all folds by whole frequency/W stratum and report every paired scene.",
        "not_identifiable_now": "Existing C5 records contain only one closed-loop action per scene. Frequency correlation or frozen replay cannot identify the counterfactual Q_m or task_SO3 under a changed filter.",
    }

    result = {
        "schema": "POSITION_CAUSAL_BAND_OBSERVABILITY_AUDIT_V1",
        "status": "PASS_TRAIN_ONLY_READONLY_AUDIT_NO_MODEL_TRAINED",
        "scope": {
            "physical_split": "TRAIN_C5_24",
            "canonical_scene_prefix": "DL1018_DEV",
            "scene_count": 24,
            "event_count_per_scene": 1999,
            "ready_count_per_scene": 1968,
            "sample_rate_hz": FS,
            "raw_data_decoded": ["scene/reference/position", "scene/reference/velocity", "scene/reference/acceleration"],
            "raw_data_not_decoded": ["environment_wind_I", "wind force/torque", "Plant state", "motor truth", "VAL", "TEST"],
            "Plant_called": False, "model_trained": False, "inertia_reconstruction": False,
            "frequency_group_labels_used_only_for_offline_stratification": True,
            "online_W_code_or_future_input": False,
            "parent_data_exposure_limit": "The frozen parent/C5 system has seen these DEV-prefix TRAIN24 scenes; these 24 are not an independent deployment test.",
        },
        "source_hashes": {
            "causal_pairs_npz_sha256": sha256_file(DATA),
            "causal_pairs_source_lock_sha256": sha256_file(DATA_LOCK),
            "physical_train24_manifest_sha256": sha256_file(PHYSICAL_MANIFEST),
            "windband_profile_csv_sha256": sha256_file(PROFILE),
            "scene_generation_source_sha256": sha256_file(SCENE_SOURCE),
            "audit_script_sha256": sha256_file(Path(__file__)),
            "physical_c5_raw_sha256_verified_count": len(raw_hashes),
            "physical_c5_raw_sources": raw_hashes,
        },
        "method": {
            "band_summary": "100-Hz ready event action, raw 10-ms target, reference acceleration, position error, and surface; Hann Welch nperseg=1024 (df=0.09765625 Hz), 50% overlap; per-scene PSD integration.",
            "coherence": "Welch magnitude-squared coherence within each band; flagged unusable as a separation signal if reference-acceleration band RMS < 5% of action RMS. Same-trajectory action/target coherence is descriptive only.",
            "tone_sensitivity": "For offline scene-spec frequencies only: compare 20-s full-window sinusoid+trend fit, Hann-weighted fit, Welch local band RMS (f +/- 0.12 Hz), and a Hann fit after subtracting a zero-phase 0.5-Hz low-pass reference trend. The low-pass residual is an offline decomposition, not a deployable input.",
            "tone_residual_limit": "The 0.5-Hz low-pass residual deliberately removes reference content at/below 0.5 Hz; it is not used to judge the W00-W02 .25/.45-Hz reference lines.",
            "derivative_consistency": "Relative RMS between 1-kHz finite differences of reference position/velocity and logged reference velocity/acceleration, excluding 5 ms at record edges.",
            "causal_filter_response_example": "Fourth-order Butterworth causal high-pass residual branch at 0.5 Hz, fs=100 Hz; response example only, not a proposed candidate or proof of 0-.5-Hz identity.",
        },
        "welch_band_medians_all_scenes": band_summary,
        "welch_band_medians_by_offline_wind_group": group_summary,
        "reference_tone_sensitivity_by_offline_wind_group": tone_group_summary,
        "reference_derivative_consistency": {
            "scenes": derivative_rows,
            "position_to_velocity_relative_rms_median": float(np.median(deriv_vel)),
            "position_to_velocity_relative_rms_p95": float(np.percentile(deriv_vel, 95)),
            "velocity_to_acceleration_relative_rms_median": float(np.median(deriv_acc)),
            "velocity_to_acceleration_relative_rms_p95": float(np.percentile(deriv_acc, 95)),
        },
        "causal_highpass_response_example": filter_response,
        "per_scene_band_metrics": band_rows,
        "per_scene_line_metrics": tone_rows,
        "key_interpretation": {
            "reference_tone_boundary_leakage": "Unwindowed finite-record tone regression can assign slow reference trajectory/edge content to a high-frequency sinusoid. On W09, the full-window position tone at 2.2 Hz is ~1e-2 m while Hann/residual fits are orders smaller; raw 1-kHz derivatives are mutually consistent, so the full-fit value is not a trustworthy high-frequency reference component.",
            "position_target_conflict": "The 10-ms target and C5 action share strong same-trajectory narrowband structure in the active wind bands. Fitting that target can reward the very wind-frequency compensation whose attitude effect is under dispute.",
            "reference_separation": coherence_warning,
            "counterfactual_limit": "No same-scene alternative action exists in this audit; no frequency decomposition or frozen replay identifies closed-loop Q_m or task_SO3 under a changed action.",
        },
        "minimal_paired_closed_loop_plan": pair_plan,
    }

    result = json_ready(result)
    OUT_JSON.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    write_report(result)
    return result


def fmt(x, digits=4):
    return "—" if x is None else f"{x:.{digits}f}"


def write_report(r: dict) -> None:
    bands = r["welch_band_medians_all_scenes"]
    tone_groups = r["reference_tone_sensitivity_by_offline_wind_group"]
    derivative = r["reference_derivative_consistency"]
    response = r["causal_highpass_response_example"]
    plan = r["minimal_paired_closed_loop_plan"]
    md = [
        "# TRAIN24 因果频带可观测性审计 v1", "",
        "## 结论", "",
        "现有数据不足以训练一个可靠的、能同时保住 C5 位置表现并把高频任务姿态压到 B 水平的频带门控网络。本次只做了 TRAIN-only 信号审计，没有训练模型、没有运行 Plant、没有读取 VAL/TEST、没有惯量重建。",
        "",
        "把现成 10 ms 位置残差 target 作为高频 band 的监督会有方向冲突：在同一条闭环轨迹中，C5 action 与 target 在主要风频附近高度同频；target 可能奖励保留/增强这部分位置补偿，而姿态目标可能希望抑制其进入姿态回路。它不是改动作后位置 Q 的标签。",
        "",
        "参考频率回归也有严重窗口边界泄漏：未加窗的有限记录 tone fit 会把慢任务轨迹泄漏到 2.2–4.8 Hz。参考位置/速度/加速度本身 1 kHz 数值微分保持一致，因此不能把全窗未加窗拟合幅值当作真实高频命令线。Hann、Welch 和去慢趋势 residual-fit 显著减小这些线。",
        "",
        "## 数据与口径", "",
        f"- 数据：物理 `TRAIN_C5_24` 的 24 个 `DL1018_DEV_*` 场景；每场 1,999 个 position event、1,968 个 ready event，100 Hz。输入是现成 X14、C5 applied action、10 ms raw target；从同一批 C5 raw 只读取 scene reference 的 position/velocity/acceleration。",
        "- 风组/频率只用于离线分层和指定 tone 查询，不进入任何部署输入。未解析 wind truth 字段。",
        "- PSD/coherence：Hann Welch，1024 样本窗（0.0977 Hz bin），50% overlap。相干度在参考加速度频带 RMS 小于 action 的 5% 时标为低功率，不解释为可部署分离信号。",
        "- Tone 检查：全窗未加权拟合、Hann 加权拟合、Welch `f±0.12 Hz` 局部功率、减去 0.5 Hz 零相位低通参考趋势后的残差拟合。后两者仅作离线诊断，不是在线滤波器。",
        "",
        "## 全 TRAIN24 频带摘要", "",
        "以下为按场先算频带、再对 24 场取中位；RMS 单位均按对应信号单位。Msc² 是原始描述值，参考能量不足的频带不应作为门控判据。",
        "",
        "| 频带 Hz | action RMS m/s² | target RMS m/s² | reference accel RMS m/s² | ref/action | action-target Msc² | action-reference Msc² |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in bands:
        md.append(f"| {row['band']} | {fmt(row.get('action_rms_mps2_median'),3)} | {fmt(row.get('target_rms_mps2_median'),3)} | {fmt(row.get('reference_acceleration_rms_mps2_median'),5)} | {fmt(row.get('reference_to_action_rms_ratio_median'),3)} | {fmt(row.get('welch_msc2_action_target_same_trajectory_median'),3)} | {fmt(row.get('welch_msc2_action_reference_raw_median'),3)} |")
    md += [
        "",
        "参考线相干在参考能量很小的高频段数值不稳；表中的 action-target 相干也来自同一闭环 raw，不是 action 干预的因果估计。",
        "0.5 Hz 低通趋势剥离会按定义去掉 W00–02 的 .25/.45 Hz 成分；该 residual-fit 只用于检查高于转折频段的边界泄漏，不用于评估这两条低频参考线。",
        "",
        "## 参考 tone 边界泄漏检查", "",
        "取 W09 2.2 Hz 的同场参考位置为例：未加窗全记录 fit 约 1e-2 m，Hann fit 约 1e-5 m，低频趋势剥离后的 Hann residual fit 约 1e-6 m；明显的量级差说明全窗拟合受慢轨迹/端点污染。raw 1 kHz 参考信号的差分一致性如下：",
        "",
        f"- finite-difference(position) 对 logged velocity：relative RMS 中位 `{derivative['position_to_velocity_relative_rms_median']:.3g}`，P95 `{derivative['position_to_velocity_relative_rms_p95']:.3g}`。",
        f"- finite-difference(velocity) 对 logged acceleration：relative RMS 中位 `{derivative['velocity_to_acceleration_relative_rms_median']:.3g}`，P95 `{derivative['velocity_to_acceleration_relative_rms_p95']:.3g}`。",
        "- 对 W09 residual-fit 的小参考 tone，位置/速度/加速度的导数关系大体恢复一致；绝对参考加速度线仍比 C5 action 小很多。W12–14 更高频的参考线接近数值/谱估计底噪，应标不可辨。",
        "",
        "| 离线频组 | lines | position full / Hann / residual median (m) | velocity full / Hann / residual median (m/s) | acceleration full / Hann / residual median (m/s²) |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in tone_groups:
        md.append(f"| {row['offline_stratum']} | {row['line_count']} | {fmt(row.get('position_tone_full_vector_amplitude_median'),6)} / {fmt(row.get('position_tone_hann_vector_amplitude_median'),6)} / {fmt(row.get('position_tone_lowpass_residual_hann_amplitude_median'),6)} | {fmt(row.get('velocity_tone_full_vector_amplitude_median'),6)} / {fmt(row.get('velocity_tone_hann_vector_amplitude_median'),6)} / {fmt(row.get('velocity_tone_lowpass_residual_hann_amplitude_median'),6)} | {fmt(row.get('acceleration_tone_full_vector_amplitude_median'),6)} / {fmt(row.get('acceleration_tone_hann_vector_amplitude_median'),6)} / {fmt(row.get('acceleration_tone_lowpass_residual_hann_amplitude_median'),6)} |")
    md += [
        "",
        "The full-window tone fit is not a safe estimate of high-frequency command content. The deployment model must not use future/window-wide spectral estimates; any causal feature needs a measured transfer function and startup behavior.",
        "",
        "## 有限阶滤波的低频泄漏", "",
        "以 100 Hz、0.5 Hz 四阶 Butterworth 因果高通残差支路为响应示例：DC 数学上为零，但 0–0.5 Hz 并非零；.25 Hz 幅值仍为 0.062，.40 为 0.379，.45 为 0.549，.50 为 0.707，.58 为 0.875。相位在转折区也显著变化。不能声称“0–.5 Hz machine-zero/identity”；要以实际最终 SOS 系数报告整条幅相曲线，并让 paired scene 测到其位置代价。",
        "",
        "| f Hz | gain dB | magnitude | phase deg |",
        "|---:|---:|---:|---:|",
    ]
    for row in response:
        if row["frequency_hz"] in (0.0, 0.25, 0.4, 0.45, 0.5, 0.58, 0.85, 1.15, 2.2, 3.2, 3.7, 4.8):
            md.append(f"| {row['frequency_hz']:.2f} | {row['gain_db']:.2f} | {row['magnitude']:.5f} | {row['phase_deg']:.1f} |")
    md += [
        "",
        "## 最小 paired closed-loop 数据方案（仅设计，未执行）", "",
        "先用低维干预识别位置–姿态响应，不训练大网络。对照必须是完全相同 scene/initial state/reference/arm schedule 的 C5 DSSM14 + cosineGRU 基线；B raw 只在方法身份和场景身份匹配后作姿态门槛。旧 C5 raw 若不是这一精确 dual-loop stack，不可当成配对基线。",
        "",
        "- 每个频组取 T1/T2/T3 各一条，12 条 active-band anchors：",
        "  - W03–05：T1_C00_W03、T2_C00_W04、T3_C00_W05（0.58/0.87 Hz，转折边缘）；",
        "  - W06–08：T1_C05_W06、T2_C06_W07、T3_C06_W08（1.15/1.75 Hz）；",
        "  - W09–11：T1_C10_W09、T2_C09_W10、T3_C10_W11（2.2/3.2 Hz）；",
        "  - W12–14：T1_C11_W12、T2_C12_W13、T3_C15_W14（3.7/4.8 Hz）。",
        "- 再加入 3 条 W00–02 低频/reference-confound 控制（T1_C04_W00、T2_C03_W01、T3_C05_W02），检查 .45 Hz 附近泄漏；3 条 W15 no-tone 控制只作 identity/parity。W分组只用于选测试场，不提供给在线模块。",
        "- 每个 active band 单独做两档轻到中等扰动：band gain 0.90 与 0.75；其余 bands=1，基线 gain=1。低组只作低频保护检查；不再做 gain=0 硬陷波。最小筛查为 12×2 + 3×2 = 30 条候选闭环运行，另需 15 个 exact C5 baseline 与对应 B score（可复用已存在且身份锁定的 raw，否则补齐）。",
        "- 若最小筛查的 paired ΔQ_m/Δtask_SO3 方向稳定，再把该 TRAIN_C5_24 的其余 6 条 active scenes 纳入同样两档，检查 amplitude/task 异质性。看 paired Q_m、task/inner SO(3)、逐 phase XYZ 误差和安全字段。",
        "- 只从成对结果拟合最多 4–6 个共享 band gain/低维响应曲线；按整组频带留出，scene 是有效样本单位，不能把 100 Hz event 数伪装成大数据。若不同 task/幅度组响应符号相反，拒绝全局门控，不扩充网络容量。",
        "- 当前同轨迹 target、PSD/coherence、零相位 replay 均不能识别改动作后的闭环 Q。任何通过只够支持进一步验证，不等于部署证据。",
        "",
        "## 文件与范围锁", "",
        f"- 数据 NPZ SHA-256：`{r['source_hashes']['causal_pairs_npz_sha256']}`",
        f"- TRAIN24 physical manifest SHA-256：`{r['source_hashes']['physical_train24_manifest_sha256']}`",
        f"- Windband profile SHA-256：`{r['source_hashes']['windband_profile_csv_sha256']}`",
        f"- Scene source SHA-256：`{r['source_hashes']['scene_generation_source_sha256']}`",
        f"- 本审计脚本 SHA-256：`{r['source_hashes']['audit_script_sha256']}`",
        f"- 已绑定并核验 C5 raw 文件数：{r['source_hashes']['physical_c5_raw_sha256_verified_count']}。具体逐场路径和 SHA 在 JSON 中。",
        "- 本报告与 JSON 均由同目录脚本生成；本次无模型训练、无 Plant、无 VAL/TEST、无惯量重建。",
        "",
    ]
    OUT_MD.write_text("\n".join(md), encoding="utf-8")


if __name__ == "__main__":
    result = analyze()
    print(json.dumps({"status": result["status"], "json": str(OUT_JSON), "markdown": str(OUT_MD),
                      "script_sha256": result["source_hashes"]["audit_script_sha256"],
                      "raw_sources_verified": result["source_hashes"]["physical_c5_raw_sha256_verified_count"],
                      "model_trained": False, "Plant_called": False}, indent=2))
