#!/usr/bin/env python3
"""Fixed TRAIN-only frequency/time decomposition of teacher and two student OOF arms."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from scipy.signal import butter, periodogram, sosfiltfilt
from scipy.spatial.transform import Rotation

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "experiments/dl_attitude_replacement_20261028/position_cosine_gru_train24_causal_v1"
SOURCE = DATA_DIR / "task_aware_cv_v1"
TEACHER_OOF = SOURCE / "TRAIN24_TEACHER_DISTILLATION_OOF_v1.npz"
NO_DC_OOF = DATA_DIR / "teacher_position_balanced_cv_v1/TEACHER_POSITION_BALANCED_OOF_v1.npz"
DC_OOF = DATA_DIR / "teacher_position_balanced_dc_penalty_cv_v1/DC_PENALTY_OOF_v1.npz"
PLAN = OUT / "ANALYSIS_PLAN_v1.json"
RESULTS = OUT / "TEACHER_DC_FREQUENCY_TIME_RESULTS_v1.json"
REPORT = OUT / "TEACHER_DC_FREQUENCY_TIME_REPORT_v1.md"
sys.path.insert(0, str(SOURCE))
import fit_task_aware_fourfold_v1 as fit  # noqa: E402
from task_aware_common import (DATA_MANIFEST_PATH, DATA_PATH, SOURCE_LOCK_PATH,
                               load_locked_inputs, sha256)  # noqa: E402

FS = 100.0
TIME_WINDOWS = [(0, 5), (5, 10), (10, 15), (15, 20)]
BANDS = [(0.05, 0.5), (0.5, 2), (2, 5), (5, 20), (20, 50)]


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_npz(path: Path) -> dict:
    with np.load(path, allow_pickle=False) as z:
        return {k: z[k] for k in z.files}


def filter_band(delta: np.ndarray, low: float, high: float) -> np.ndarray:
    if high >= FS / 2:
        sos = butter(4, low, btype="highpass", fs=FS, output="sos")
    else:
        sos = butter(4, [low, high], btype="bandpass", fs=FS, output="sos")
    return sosfiltfilt(sos, delta, axis=0)


def attitude_trace(action: np.ndarray, trajectory: dict) -> tuple[np.ndarray, float]:
    applied = np.concatenate((trajectory["applied_acc_1ms"][:10],
                              np.repeat(action, 10, axis=0)), axis=0).astype(np.float64)
    command = trajectory["nominal_acc_1ms"].astype(np.float64) - applied
    euler = fit.force_to_euler(command, trajectory["state_yaw_1ms"],
                               trajectory["reference_yaw_1ms"])
    filtered, _, _ = fit.replay_filter(euler, trajectory["initial_euler"].astype(np.float64))
    target = trajectory["task_target_euler"].astype(np.float64)
    theta = (Rotation.from_euler("xyz", target).inv() *
             Rotation.from_euler("xyz", filtered)).magnitude()
    mask_time = np.arange(20000, dtype=np.float64) * 0.001
    window = {f"{a}_{b}s": float(np.sqrt(np.mean(theta[(mask_time >= a) & (mask_time < b)] ** 2)))
              for a, b in TIME_WINDOWS}
    return theta, float(np.sqrt(np.mean(theta ** 2)))


def residual_metrics(action: np.ndarray, target: np.ndarray, ready: np.ndarray) -> float:
    e = action[ready].astype(np.float64) - target[ready].astype(np.float64)
    return float(np.sqrt(np.mean(e * e)))


def spectrum(delta: np.ndarray) -> dict:
    mean = delta.mean(axis=0)
    centered = delta - mean[None, :]
    freq, psd = periodogram(centered, fs=FS, axis=0, window="hann", detrend=False,
                            scaling="density")
    df = float(freq[1] - freq[0])
    total_ac = float(np.sum(psd[freq > 0]) * df)
    bands = {}
    for lo, hi in BANDS:
        m = (freq >= lo) & (freq < hi if hi < 50 else freq <= hi)
        bands[f"{lo:g}_{hi:g}Hz"] = float(np.sum(psd[m]) * df)
    return {"dc_mean_xyz_mps2": mean.tolist(),
            "dc_mean_norm_mps2": float(np.linalg.norm(mean)),
            "dc_mean_square_mps2_sq": float(np.mean(mean ** 2)),
            "ac_variance_mps2_sq": total_ac,
            "ac_band_energy_mps2_sq": bands,
            "ac_band_fraction": {k: (v / total_ac if total_ac > 0 else 0.0) for k, v in bands.items()}}


def main() -> None:
    for p in (RESULTS, REPORT):
        if p.exists():
            raise RuntimeError(f"Refusing to overwrite {p}")
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    bundle = load_locked_inputs()
    data = bundle["arrays"]
    ids = data["scene_ids"].astype(str).tolist()
    base = np.clip(data["applied_acceleration_event_mps2"].astype(np.float32), -3, 3)
    target = data["target_interval_clip_mps2"].astype(np.float32)
    ready = data["ready_mask"].astype(bool)
    times = data["event_time_s"].astype(np.float64)
    bind = plan["input_sha256"]
    current = {"dataset": sha256(DATA_PATH), "dataset_manifest": sha256(DATA_MANIFEST_PATH),
               "dataset_source_lock": sha256(SOURCE_LOCK_PATH),
               "teacher_oof": sha(TEACHER_OOF), "teacher_position_no_dc_oof": sha(NO_DC_OOF),
               "teacher_position_dc_penalty_oof": sha(DC_OOF)}
    if current != bind:
        raise RuntimeError(f"TRAIN24 inputs differ from the analysis plan: {current}")
    teacher_z, no_dc_z, dc_z = load_npz(TEACHER_OOF), load_npz(NO_DC_OOF), load_npz(DC_OOF)
    for z in (teacher_z, no_dc_z, dc_z):
        if (z["scene_ids"].astype(str).tolist() != ids or
                not np.array_equal(z["ready_mask"].astype(bool), ready) or
                not np.array_equal(z["target_clip_mps2"].astype(np.float32), target)):
            raise RuntimeError("Teacher/student action artifact alignment mismatch")
    actions = {
        "C5_baseline": base,
        "feasibility_teacher": teacher_z["teacher_action_mps2"].astype(np.float32),
        "student_no_dc": no_dc_z["student_action_mps2"].astype(np.float32),
        "student_dc_penalty": dc_z["student_action_mps2"].astype(np.float32),
    }
    for name, a in actions.items():
        if not np.isfinite(a).all(): raise RuntimeError(f"Nonfinite action in {name}")
    positions = {k: {} for k in actions}
    spectra = {k: {} for k in actions}
    full_task = {k: {} for k in actions}
    band_task = {"feasibility_teacher": {}}
    band_labels = [f"{lo:g}_{hi:g}Hz" for lo, hi in BANDS]

    for i, sid in enumerate(ids):
        beta = np.clip(times[i] / fit.BETA_RISE_S, 0.0, 1.0)[:, None]
        teacher_delta = teacher_z["teacher_delta_mps2"][i].astype(np.float32)
        teacher_action_check = np.clip(base[i] + beta * teacher_delta, -fit.ACTION_LIMIT, fit.ACTION_LIMIT)
        if not np.allclose(teacher_action_check, actions["feasibility_teacher"][i], atol=2e-6, rtol=0):
            raise RuntimeError(f"{sid}: teacher action formula mismatch")
        for name, full in actions.items():
            delta = (full[i] - base[i]).astype(np.float64)
            delta[~ready[i]] = 0.0
            spectra[name][sid] = spectrum(delta)
            positions[name][sid] = residual_metrics(full[i], target[i], ready[i])
            theta, total_rmse = attitude_trace(full[i], bundle["trajectories"][i])
            t = np.arange(len(theta), dtype=np.float64) * 0.001
            full_task[name][sid] = {"all_20s_rad": total_rmse}
            for a, b in TIME_WINDOWS:
                full_task[name][sid][f"{a}_{b}s"] = float(np.sqrt(np.mean(theta[(t >= a) & (t < b)] ** 2)))
        for method in band_task:
            delta = (actions[method][i] - base[i]).astype(np.float64)
            delta[~ready[i]] = 0.0
            band_task[method][sid] = {}
            for (lo, hi), label in zip(BANDS, band_labels):
                component = filter_band(delta, lo, hi)
                component[~ready[i]] = 0.0
                band_action = np.clip(base[i].astype(np.float64) + component,
                                      -fit.ACTION_LIMIT, fit.ACTION_LIMIT)
                theta, band_total = attitude_trace(band_action, bundle["trajectories"][i])
                t = np.arange(len(theta), dtype=np.float64) * 0.001
                band_task[method][sid][label] = {"all_20s_rad": band_total}
                for a, b in TIME_WINDOWS:
                    band_task[method][sid][label][f"{a}_{b}s"] = float(np.sqrt(np.mean(theta[(t >= a) & (t < b)] ** 2)))

    method_summary = {}
    for name in actions:
        method_summary[name] = {
            "position_residual_rmse_scene_macro_mps2": float(np.mean(list(positions[name].values()))),
            "frozen_SO3_rmse_scene_macro_rad": float(np.mean([v["all_20s_rad"] for v in full_task[name].values()])),
            "frozen_SO3_rmse_scene_macro_by_time_rad": {
                f"{a}_{b}s": float(np.mean([v[f"{a}_{b}s"] for v in full_task[name].values()]))
                for a, b in TIME_WINDOWS},
            "action_dc_bias_norm_scene_macro_mps2": float(np.mean([v["dc_mean_norm_mps2"] for v in spectra[name].values()])),
            "action_dc_mean_square_scene_macro_mps2_sq": float(np.mean([v["dc_mean_square_mps2_sq"] for v in spectra[name].values()])),
            "action_ac_band_fraction_scene_macro": {
                label: float(np.mean([v["ac_band_fraction"][label] for v in spectra[name].values()]))
                for label in band_labels},
        }
    method_band_summary = {}
    for method in band_task:
        method_band_summary[method] = {}
        for label in band_labels:
            method_band_summary[method][label] = {
                "frozen_SO3_rmse_scene_macro_rad": float(np.mean([band_task[method][sid][label]["all_20s_rad"] for sid in ids])),
                "frozen_SO3_rmse_scene_macro_by_time_rad": {
                    f"{a}_{b}s": float(np.mean([band_task[method][sid][label][f"{a}_{b}s"] for sid in ids]))
                    for a, b in TIME_WINDOWS},
            }
    result = {
        "schema": "COSINE_GRU_TRAIN24_TEACHER_DC_FREQUENCY_TIME_ANALYSIS_RESULTS_V1",
        "scope": "TRAIN_C5_24 only; no VAL/TEST, no new Plant call, no inertia reconstruction.",
        "input_hashes": current, "analysis_plan_sha256": sha(PLAN),
        "time_windows_s": TIME_WINDOWS, "frequency_bands_hz": BANDS,
        "method_summary": method_summary,
        "per_scene": {sid: {
            "oof_fold": str(data["fold_id"][i]),
            "position_residual_mps2": {m: positions[m][sid] for m in actions},
            "frozen_SO3_by_time_rad": {m: full_task[m][sid] for m in actions},
            "action_spectrum": {m: spectra[m][sid] for m in actions},
            "band_only_frozen_SO3": {m: band_task[m][sid] for m in band_task},
        } for i, sid in enumerate(ids)},
        "band_only_method_summary": method_band_summary,
        "interpretation_limits": [
            "Teacher action is a per-scene feasibility oracle from the same logged TRAIN trajectory; it is not cross-fit generalization.",
            "Students are strict scene-group OOF; their actions are replayed on frozen C5 states/references, not a counterfactual feedback trajectory.",
            "Frequency-filtered band-only task replay is non-additive due command-filter dynamics, action clipping and rotations; it is diagnostic and cannot be read as a causal decomposition or closed-loop score.",
            "No validation scene or score participates in this analysis or the next training design.",
        ],
    }
    RESULTS.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    lines = [
        "# TRAIN24 teacher attitude gain and DC-penalty frequency audit", "",
        "## Scope", "",
        "Uses locked TRAIN_C5_24 trajectories, the existing feasibility-teacher labels, and both scene-group OOF student outputs. No VAL/TEST data, new Plant call, or inertia reconstruction. Teacher is an in-sample per-scene oracle; its result is not generalization evidence. Student posture values are frozen-trajectory SO(3) replays, not closed-loop scores.", "",
        "## Full-action comparison", "",
        "| Method | position residual macro (m/s²) | frozen SO(3) macro (rad) | 0–5 s | 5–10 s | 10–15 s | 15–20 s | DC bias norm macro (m/s²) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for name in actions:
        s = method_summary[name]
        windows = s["frozen_SO3_rmse_scene_macro_by_time_rad"]
        lines.append(f"| {name} | {s['position_residual_rmse_scene_macro_mps2']:.6f} | {s['frozen_SO3_rmse_scene_macro_rad']:.6f} | {windows['0_5s']:.6f} | {windows['5_10s']:.6f} | {windows['10_15s']:.6f} | {windows['15_20s']:.6f} | {s['action_dc_bias_norm_scene_macro_mps2']:.6f} |")
    lines += ["", "## Correction spectra", "", "Band fractions below are averaged per scene after separating the per-scene mean (DC) from nonzero-frequency variance.", "",
              "| Method | <0.5 Hz | 0.5–2 Hz | 2–5 Hz | 5–20 Hz | 20–50 Hz |", "|---|---:|---:|---:|---:|---:|"]
    for name in actions:
        fr = method_summary[name]["action_ac_band_fraction_scene_macro"]
        lines.append("| " + name + " | " + " | ".join(f"{fr[k]:.3f}" for k in band_labels) + " |")
    lines += ["", "## Band-only attitude proxy", "", "Each row injects one zero-phase filtered action-correction band into the logged C5 action, then replays the exact frozen 1-ms attitude command filter. Bands are evaluated separately, so scores are non-additive.", "",
              "| Method | Correction band | 0–5 s SO(3) | 5–10 s | 10–15 s | 15–20 s | all 20 s |", "|---|---|---:|---:|---:|---:|---:|"]
    for method in band_task:
        for label in band_labels:
            w = method_band_summary[method][label]["frozen_SO3_rmse_scene_macro_by_time_rad"]
            total = method_band_summary[method][label]["frozen_SO3_rmse_scene_macro_rad"]
            lines.append(f"| {method} | {label} | {w['0_5s']:.6f} | {w['5_10s']:.6f} | {w['10_15s']:.6f} | {w['15_20s']:.6f} | {total:.6f} |")
    lines += ["", "## Interpretation and next fixed test", "",
              "The DC-penalty arm is compared against its no-DC parent by per-scene action spectrum and frozen posture replay above. Use only TRAIN24 findings to select one follow-up recipe. The follow-up must keep the model causal and use a teacher-centered low-frequency target if the teacher's useful posture corrections reside at low frequency; teacher remains offline supervision only. It must be evaluated once under the same four scene-group folds, with no held-out tuning.", "",
              "Band-only replay is not a causal decomposition: filtered components can interact, and a frozen trajectory cannot model changed feedback states. No result here establishes closed-loop Q.", "",
              f"- Analysis plan SHA-256: `{sha(PLAN)}`",
              f"- Analysis script SHA-256: `{sha(Path(__file__))}`",
              f"- Results JSON SHA-256: `{sha(RESULTS)}`", ""]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"method_summary": method_summary,
                      "band_only_teacher": method_band_summary["feasibility_teacher"],
                      "report_sha256": sha(REPORT), "results_sha256": sha(RESULTS)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
