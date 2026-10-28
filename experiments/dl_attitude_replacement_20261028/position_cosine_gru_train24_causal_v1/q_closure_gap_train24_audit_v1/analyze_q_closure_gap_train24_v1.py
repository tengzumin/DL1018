#!/usr/bin/env python3
"""Fixed descriptive audit of one-step action metrics vs logged TRAIN24 Q."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import h5py
import numpy as np
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "experiments/dl_attitude_replacement_20261028/position_cosine_gru_train24_causal_v1"
SOURCE = DATA_DIR / "task_aware_cv_v1"
OOF_PATH = ROOT / "experiments/dl_attitude_replacement_20261028/position_cosine_gru_train24_causal_v1/teacher_position_balanced_cv_v1/TEACHER_POSITION_BALANCED_OOF_v1.npz"
sys.path.insert(0, str(SOURCE))
from task_aware_common import (DATA_MANIFEST_PATH, DATA_PATH, SOURCE_LOCK_PATH,
                               load_locked_inputs, sha256)  # noqa: E402

PLAN_PATH = OUT / "ANALYSIS_PLAN_v1.json"
RESULT_PATH = OUT / "Q_CLOSURE_GAP_TRAIN24_RESULTS_v1.json"
REPORT_PATH = OUT / "Q_CLOSURE_GAP_TRAIN24_REPORT_v1.md"


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def rmse(action: np.ndarray, target: np.ndarray, ready: np.ndarray) -> float:
    e = action[ready].astype(np.float64) - target[ready].astype(np.float64)
    return float(np.sqrt(np.mean(e * e)))


def normcorr(x: list[np.ndarray], y: list[np.ndarray]) -> float | None:
    xx = np.concatenate([a - np.mean(a) for a in x])
    yy = np.concatenate([a - np.mean(a) for a in y])
    if xx.std() == 0 or yy.std() == 0:
        return None
    return float(np.corrcoef(xx, yy)[0, 1])


def main() -> None:
    for path in (RESULT_PATH, REPORT_PATH):
        if path.exists():
            raise RuntimeError(f"Refusing to overwrite {path}")
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    bundle = load_locked_inputs()
    data, manifest, source_lock = bundle["arrays"], bundle["manifest"], bundle["source_lock"]
    ids = data["scene_ids"].astype(str).tolist()
    x = data["x14_model_input"]
    ready = data["ready_mask"].astype(bool)
    target = data["target_interval_clip_mps2"].astype(np.float32)
    base = np.clip(data["applied_acceleration_event_mps2"].astype(np.float32), -3.0, 3.0)
    event_t = data["event_time_s"].astype(np.float64)

    input_hashes = {"dataset_sha256": sha256(DATA_PATH),
                    "dataset_manifest_sha256": sha256(DATA_MANIFEST_PATH),
                    "dataset_source_lock_sha256": sha256(SOURCE_LOCK_PATH),
                    "oof_sha256": file_sha(OOF_PATH)}
    if input_hashes != plan["source_bindings"]:
        raise RuntimeError(f"Analysis inputs no longer match the predeclared hashes: {input_hashes}")
    with np.load(OOF_PATH, allow_pickle=False) as z:
        oof_ids = z["scene_ids"].astype(str).tolist()
        fold_ids = z["fold_id"].astype(str).tolist()
        oof_ready = z["ready_mask"].astype(bool)
        oof_target = z["target_clip_mps2"].astype(np.float32)
        student = z["student_action_mps2"].astype(np.float32)
        oof_base = z["c5_baseline_action_mps2"].astype(np.float32)
    if (oof_ids != ids or not np.array_equal(oof_ready, ready) or
            not np.array_equal(oof_target, target) or not np.array_equal(oof_base, base) or
            student.shape != base.shape or not np.isfinite(student).all()):
        raise RuntimeError("Scene-group OOF predictions do not align with exact TRAIN24 source rows")

    lock_by_id = {r["scene_id"]: r for r in source_lock["scene_rows"]}
    if set(lock_by_id) != set(ids) or len(lock_by_id) != 24:
        raise RuntimeError("Raw source lock is not exactly the 24-scene TRAIN cohort")
    scenes = {}
    all_position_errors, all_delta_norms = [], []
    all_candidate_errors, all_base_errors, all_deltas = [], [], []
    for i, sid in enumerate(ids):
        row = lock_by_id[sid]
        raw_path = Path(row["parent_cosine_gru_raw_path"])
        status_path = Path(row["parent_status_path"])
        if (file_sha(raw_path) != row["parent_cosine_gru_raw_sha256"] or
                file_sha(status_path) != row["parent_status_sha256"]):
            raise RuntimeError(f"{sid}: TRAIN raw/status hash differs from source lock")
        status = json.loads(status_path.read_text(encoding="utf-8"))
        if (status.get("scene_id") != sid or status.get("state") != "COMPLETED" or
                status.get("status_value") != "STABLE" or status.get("TEST_read") is not False):
            raise RuntimeError(f"{sid}: raw status or scope binding failed")
        with h5py.File(raw_path, "r") as f:
            state = np.asarray(f["log/state"][()], dtype=np.float64)
            if state.shape == (20001, 12):
                state = state.T
            ref = np.asarray(f["scene/reference/position"][()], dtype=np.float64)
            if ref.shape == (3, 20001):
                ref = ref.T
            elif ref.shape == (20001, 3):
                pass
            else:
                raise RuntimeError(f"{sid}: unexpected TRAIN position-reference dimensions {ref.shape}")
            time = np.asarray(f["log/time"][()], dtype=np.float64).reshape(-1)
        if state.shape != (12, 20001) or ref.shape != (20001, 3) or time.shape != (20001,):
            raise RuntimeError(f"{sid}: unexpected TRAIN state/reference/time dimensions")
        pos_err = state[:3].T - ref
        q_c5 = float(np.sqrt(np.mean(np.sum(pos_err * pos_err, axis=1))))
        event_idx = data["event_index_zero_based"][i].astype(np.int64)
        if not np.array_equal(event_idx, np.arange(10, 20000, 10)):
            raise RuntimeError(f"{sid}: unexpected 100-Hz event schedule")
        current_pos_error = pos_err[event_idx]
        delta = student[i] - base[i]
        delta[~ready[i]] = 0.0
        delta_norm = np.linalg.norm(delta[ready[i]], axis=1)
        q_rmse = rmse(student[i], target[i], ready[i])
        c5_rmse = rmse(base[i], target[i], ready[i])
        # No-feedback unit double-integrator proxy; explicitly not the plant or Q.
        dv = np.cumsum(delta.astype(np.float64), axis=0) * 0.01
        dp = np.cumsum(dv, axis=0) * 0.01
        sec_bin = np.floor(event_t[i]).astype(int)
        bin_means = np.array([delta[sec_bin == b].mean(axis=0) for b in range(20)])
        row_result = {
            "scene_id": sid, "oof_fold": fold_ids[i],
            "logged_C5_Q_m": q_c5,
            "C5_acceleration_residual_rmse_mps2": c5_rmse,
            "student_OOF_acceleration_residual_rmse_mps2": q_rmse,
            "one_step_gain_vs_C5_mps2": c5_rmse - q_rmse,
            "student_minus_C5_action_mean_xyz_mps2": delta[ready[i]].astype(np.float64).mean(axis=0).tolist(),
            "student_minus_C5_action_rms_mps2": float(np.sqrt(np.mean(delta[ready[i]].astype(np.float64) ** 2))),
            "mean_1s_action_bias_norm_mps2": float(np.mean(np.linalg.norm(bin_means, axis=1))),
            "max_1s_action_bias_norm_mps2": float(np.max(np.linalg.norm(bin_means, axis=1))),
            "no_feedback_terminal_delta_v_proxy_mps": dv[-1].tolist(),
            "no_feedback_terminal_delta_p_proxy_m": dp[-1].tolist(),
            "no_feedback_peak_delta_p_proxy_norm_m": float(np.max(np.linalg.norm(dp, axis=1))),
            "mean_event_position_error_norm_m": float(np.mean(np.linalg.norm(current_pos_error, axis=1))),
            "mean_ready_position_error_norm_m": float(np.mean(np.linalg.norm(current_pos_error[ready[i]], axis=1))),
        }
        scenes[sid] = row_result
        all_position_errors.append(np.linalg.norm(current_pos_error[ready[i]], axis=1))
        all_delta_norms.append(delta_norm)
        all_candidate_errors.append(q_rmse)
        all_base_errors.append(c5_rmse)
        all_deltas.append(delta[ready[i]].astype(np.float64))

    per = list(scenes.values())
    q_values = np.asarray([r["logged_C5_Q_m"] for r in per])
    gains = np.asarray([r["one_step_gain_vs_C5_mps2"] for r in per])
    q_rank_gain = spearmanr(q_values, gains)
    candidate_resid = float(np.mean(all_candidate_errors))
    c5_resid = float(np.mean(all_base_errors))
    pooled_c5 = float(np.sqrt(np.mean(np.square(np.asarray(all_base_errors)))))
    all_delta = np.concatenate(all_deltas, axis=0)
    all_qnorm = np.concatenate(all_position_errors)
    all_dnorm = np.concatenate(all_delta_norms)
    all_res = {
        "scope": "Locked TRAIN_C5_24 only; this analysis makes no new Plant call, reads no VAL/TEST data, and does no inertia reconstruction; OOF actions are compared offline against existing C5 states only.",
        "input_hashes": input_hashes,
        "predeclared_analysis_plan_sha256": file_sha(PLAN_PATH),
        "scene_count": len(scenes),
        "fold_counts_holdout": {fold: fold_ids.count(fold) for fold in dict.fromkeys(fold_ids)},
        "summary": {
            "C5_logged_Q_scene_macro_m": float(q_values.mean()),
            "C5_logged_Q_scene_median_m": float(np.median(q_values)),
            "C5_acceleration_residual_scene_macro_mps2": c5_resid,
            "student_OOF_acceleration_residual_scene_macro_mps2": candidate_resid,
            "student_OOF_one_step_gain_scene_macro_mps2": c5_resid - candidate_resid,
            "student_minus_C5_action_mean_xyz_mps2": all_delta.mean(axis=0).tolist(),
            "student_minus_C5_action_rms_mps2": float(np.sqrt(np.mean(all_delta ** 2))),
            "mean_within_scene_centered_corr_abs_delta_vs_current_position_error_norm": normcorr(all_delta_norms, all_position_errors),
            "spearman_C5_Q_vs_student_one_step_gain": {"rho": float(q_rank_gain.statistic), "p_descriptive": float(q_rank_gain.pvalue)},
            "mean_no_feedback_terminal_delta_p_proxy_norm_m": float(np.mean([r["no_feedback_peak_delta_p_proxy_norm_m"] for r in per])),
            "median_no_feedback_peak_delta_p_proxy_norm_m": float(np.median([r["no_feedback_peak_delta_p_proxy_norm_m"] for r in per])),
            "max_no_feedback_peak_delta_p_proxy_norm_m": float(np.max([r["no_feedback_peak_delta_p_proxy_norm_m"] for r in per])),
        },
        "per_scene": scenes,
        "interpretation": [
            "The OOF score tests a 10-ms acceleration-residual target on frozen X14/history from the logged C5 trajectory; it does not roll forward the candidate's changed state, features, or future feedback actions.",
            "Logged Q is the closed-loop C5 baseline only. The student has no counterfactual closed-loop Q in these data.",
            "The unit double-integrator accumulation is a falsifiable sensitivity proxy for low-frequency action bias, not a physical prediction and not a replacement for Plant/closed-loop scoring.",
            "The scene-rank statistic is descriptive on 24 correlated development trajectories and is not a validation or model-selection signal.",
        ],
    }
    RESULT_PATH.write_text(json.dumps(all_res, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    lines = [
        "# Why one-step residual gains may not transfer to closed-loop position Q",
        "",
        "## Scope and method",
        "",
        "Only the locked 24-scene TRAIN_C5_24 dataset, its already-existing hash-bound parent TRAIN raw runs, and the already-produced scene-group OOF student actions were used. This analysis made no new Plant call, read no VAL/TEST data, and used no inertia reconstruction. No hyperparameter or model was selected from this analysis.",
        "",
        "The logged C5 Q is RMS Euclidean position error over 20,001 states. Student-vs-C5 action residual uses the existing 10-ms clipped acceleration target on the held-out scene fold. Action drift uses a unit double-integrator with no feedback solely as a sensitivity proxy; it is not actual position Q.",
        "",
        "## Aggregate findings",
        "",
        f"- Logged C5 Q scene-macro: {all_res['summary']['C5_logged_Q_scene_macro_m']:.4f} m (median {all_res['summary']['C5_logged_Q_scene_median_m']:.4f} m).",
        f"- One-step acceleration residual: C5 {c5_resid:.6f} vs OOF student {candidate_resid:.6f} m/s² scene-macro; gain {c5_resid-candidate_resid:.6f} m/s².",
        f"- OOF action change from C5: pooled mean {all_delta.mean(axis=0).tolist()} m/s², componentwise RMS {all_res['summary']['student_minus_C5_action_rms_mps2']:.6f} m/s².",
        f"- No-feedback double-integrator peak displacement proxy: median {all_res['summary']['median_no_feedback_peak_delta_p_proxy_norm_m']:.3f} m, max {all_res['summary']['max_no_feedback_peak_delta_p_proxy_norm_m']:.3f} m.",
        f"- Baseline Q vs one-step gain across scenes: Spearman rho {q_rank_gain.statistic:.3f} (descriptive p={q_rank_gain.pvalue:.3f}, n=24).",
        "",
        "A large proxy would show that small, persistent action bias can accumulate, but would not establish that the candidate causes a Q increase. The exact closed-loop effect remains unobserved.",
        "",
        "## Per-scene TRAIN diagnostics",
        "",
        "| Scene | OOF fold | C5 Q (m) | C5 residual | student OOF residual | one-step gain | action RMS Δ | peak no-feedback Δp proxy (m) |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for sid, r in scenes.items():
        lines.append(f"| {sid} | {r['oof_fold']} | {r['logged_C5_Q_m']:.4f} | {r['C5_acceleration_residual_rmse_mps2']:.5f} | {r['student_OOF_acceleration_residual_rmse_mps2']:.5f} | {r['one_step_gain_vs_C5_mps2']:.5f} | {r['student_minus_C5_action_rms_mps2']:.5f} | {r['no_feedback_peak_delta_p_proxy_norm_m']:.3f} |")
    lines += [
        "",
        "## Why the current loss leaves Q unconstrained",
        "",
        "1. The position term predicts a local 10-ms acceleration residual measured while C5 generated the logged states. It rewards matching that label, not minimizing the integral of future position error under an intervention.",
        "2. Teacher distillation carries a frozen-trajectory attitude/task preference into the student. The teacher's per-scene position cap is also checked on those same logged C5 states; neither is a counterfactual rollout of the updated policy.",
        "3. Once a candidate changes position compensation, the vehicle state, the next X14, and all later feedback actions change. Frozen-history OOF cannot propagate that feedback loop. A small coherent bias may alter phase or accumulate over many events even when one-step RMSE improves.",
        "4. Frozen SO(3) command-filter replay is likewise a fixed-state task metric, not coupled position tracking or closed-loop Q.",
        "",
        "## Falsifiable next steps without using VAL for tuning",
        "",
        "- First use this report's predeclared OOF diagnostics to decide whether the actual student action has appreciable low-frequency/scene-level bias. Do not treat the no-feedback proxy as a Q score.",
        "- A low-cost training-only candidate is a fold-local penalty on the one-second mean or cumulative impulse of `a_student-a_C5`, evaluated under the same whole-scene OOF protocol. Predeclare its scale from training folds only. This tests the specific bias hypothesis; it still does not prove better Q.",
        "- A principled Q objective requires counterfactual closed-loop trajectories or a validated response model. Given the current no-Plant/no-inertia constraint and absence of candidate interventions in TRAIN logs, no training-only loss can identify the candidate's true Q effect. Any eventual claim needs a separately authorized, paired closed-loop evaluation after design freeze.",
        "",
        "## Reproducibility",
        "",
        f"- Analysis plan SHA-256: `{file_sha(PLAN_PATH)}`",
        f"- Analysis script SHA-256: `{file_sha(Path(__file__))}`",
        f"- Results JSON SHA-256: `{file_sha(RESULT_PATH)}`",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"summary": all_res["summary"],
                      "results_sha256": file_sha(RESULT_PATH),
                      "report_sha256": file_sha(REPORT_PATH)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
