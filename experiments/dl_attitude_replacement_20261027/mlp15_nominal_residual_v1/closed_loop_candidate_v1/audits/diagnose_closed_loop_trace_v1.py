"""Read-only, single-scene timing/shift diagnostic for the MLP15 candidate."""
from __future__ import annotations

import json
from pathlib import Path

import h5py
import numpy as np
from scipy.io import loadmat

HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
ROOT = HERE.parents[4]
MODEL_DIR = ROOT / "experiments/dl_attitude_replacement_20261027/mlp15_nominal_residual_v1"
SCENE = "DL1018_DEV_T1_C10_W09"  # first authorized HF scene; no TEST access
RAW = STUDY / "runs" / SCENE / "PHYS_RESIDUAL_ATTEMPT_01" / "raw_run.mat"
STATUS = RAW.with_name("run_status.json")
RELEASE = STUDY / "RELEASE.json"
TRAIN = MODEL_DIR / "TRAIN_C5_24_PHYSICAL_RESIDUAL_v1.npz"
MODEL = MODEL_DIR / "runs/MLP15_TRAIN_C5_24_PHYSICAL_RESIDUAL_SEED2026102001_REPAIR01/mlp15_attitude_weights_v1.mat"
OUT = HERE / "CLOSED_LOOP_TRACE_DIAG_W09_v2.json"


def vec(group, key):
    return np.asarray(group[key][()], dtype=np.float64).reshape(-1)


def scalar(group, key):
    return float(vec(group, key)[0])


def rmse(a: np.ndarray, b: np.ndarray) -> dict:
    e = np.asarray(a, dtype=np.float64) - np.asarray(b, dtype=np.float64)
    return {"n": int(len(e)), "axis_rmse": np.sqrt(np.mean(e * e, axis=0)).tolist(),
            "vector_rmse": float(np.sqrt(np.mean(np.sum(e * e, axis=1))))}


def main() -> None:
    release = json.loads(RELEASE.read_text(encoding="utf-8"))
    status = json.loads(STATUS.read_text(encoding="utf-8"))
    assert SCENE in release["authorized_scenes"] and "TEST" not in SCENE
    assert release.get("TEST_read") is False and status.get("test_data_read") is False
    assert status.get("state") == "COMPLETED" and status.get("status_value") == "STABLE"
    assert not OUT.exists(), f"refusing to overwrite {OUT}"

    weights = loadmat(MODEL)
    scale = np.asarray(weights["target_rms"], dtype=np.float64).reshape(-1)
    x_train = np.load(TRAIN)["x_train"].astype(np.float64).reshape(-1, 13)
    mean, std = x_train.mean(0), x_train.std(0)
    assert np.all(std > 0) and scale.shape == (3,)

    rows = []
    with h5py.File(RAW, "r") as raw:
        log = raw["log"]
        flags = np.asarray(log["attitude_event_flag"]).reshape(-1).astype(bool)
        refs = log["mlp15_attitude_trace"][()].reshape(-1)
        assert flags.shape == refs.shape and int(flags.sum()) == 1999
        for q in np.flatnonzero(flags):
            g = raw[refs[q]]
            h = g["causal_head"]
            rows.append({
                "q": int(q), "sample": int(scalar(g, "sample_index")),
                "time": scalar(g, "time_s"), "beta": scalar(g, "beta"),
                "feature": vec(g, "feature_raw"), "z": vec(g, "feature_normalized"),
                "phi": vec(h, "phi"), "base": vec(h, "base_residual_rad_s2"),
                "correction": vec(h, "correction_residual_rad_s2"),
                "raw": vec(g, "raw_residual_rad_s2"), "clipped": vec(g, "clipped_residual_rad_s2"),
                "obs": vec(h, "observation_residual_rad_s2"),
                "prev_sample": int(scalar(h, "previous_feature_sample_index")),
                "obs_start": scalar(h, "observation_start_time_s"),
                "obs_end": scalar(h, "observation_end_time_s"),
                "updated": bool(scalar(h, "update_executed")),
                "w_before": np.asarray(h["weight_before"][()], dtype=np.float64).T,
                "w_after": np.asarray(h["weight_after"][()], dtype=np.float64).T,
                "tracking_drive": np.asarray(h["tracking_drive"][()], dtype=np.float64).T,
                "dt": scalar(h, "actual_event_dt"),
                "projection": bool(scalar(h, "projection_active")),
            })

    by_sample = {r["sample"]: r for r in rows}
    by_previous_sample = {r["prev_sample"]: r for r in rows if r["prev_sample"]}
    # The h5 trace's raw total must equal base plus the logged causal correction.
    assert max(np.max(np.abs(r["raw"] - r["base"] - r["correction"])) for r in rows) < 1e-8
    # The stored feature at current event is the one used by base+RLS before this event's observation update.
    assert max(np.max(np.abs(r["raw"] - r["base"] - scale * (r["w_before"].T @ r["phi"])))
               for r in rows) < 2e-7

    aligned = []          # current x_k prediction vs y_k (training-label alignment)
    deployed = []         # previous event's issued prediction vs y_k (actual held interval)
    update_pairs = []     # at k: pre/RLS-only/full update predictions vs y_(k+1), same x_k
    fit_pairs = []        # RLS fit of y_k against previous feature, before vs after RLS only
    continuity = []
    for r in rows:
        p = by_sample.get(r["prev_sample"])
        if p is None:
            continue
        assert r["sample"] - p["sample"] == 10
        assert abs((r["obs_end"] - r["obs_start"]) - .01) < 1e-9
        y = r["obs"]
        aligned.append((r["base"], r["raw"], y))
        p_applied = p["beta"] * p["clipped"]
        deployed.append((p["base"], p["raw"], p_applied, y))
        next_row = by_previous_sample.get(r["sample"])
        if r["updated"] and next_row is not None and r["beta"] >= 1 and next_row["beta"] >= 1:
            continuity.append(np.max(np.abs(next_row["w_before"] - r["w_after"])))
            if not r["projection"]:
                # Remove the separately logged tracking-gradient increment to isolate RLS.
                w_rls = r["w_after"] - r["dt"] * r["tracking_drive"]
                after_rls = r["base"] + scale * (w_rls.T @ r["phi"])
                after_full = r["base"] + scale * (r["w_after"].T @ r["phi"])
                update_pairs.append((r["raw"], after_rls, after_full, next_row["obs"]))
                p = by_sample[r["prev_sample"]]
                fit_before = p["base"] + scale * (r["w_before"].T @ p["phi"])
                fit_after = p["base"] + scale * (w_rls.T @ p["phi"])
                fit_pairs.append((fit_before, fit_after, r["obs"]))

    aligned_base, aligned_total, aligned_y = (np.asarray([x[i] for x in aligned]) for i in range(3))
    dep_base, dep_total, dep_applied, dep_y = (np.asarray([x[i] for x in deployed]) for i in range(4))
    before, after_rls, after_full, next_y = (np.asarray([x[i] for x in update_pairs]) for i in range(4))
    fit_before, fit_after, fit_y = (np.asarray([x[i] for x in fit_pairs]) for i in range(3))

    runtime_z = np.asarray([r["z"] for r in rows])
    runtime_x = np.asarray([r["feature"] for r in rows])
    train_z = (x_train - mean) / std
    feature_shift = {
        "feature_order": ["attitude_error_xyz", "body_rate_xyz", "nominal_torque_xyz", "morph_command_4"],
        "runtime_abs_z_gt3_fraction_by_feature": (np.abs(runtime_z) > 3).mean(0).tolist(),
        "runtime_abs_z_gt4_fraction_by_feature": (np.abs(runtime_z) > 4).mean(0).tolist(),
        "runtime_abs_z_gt3_fraction_all": float((np.abs(runtime_z) > 3).mean()),
        "runtime_abs_z_gt4_fraction_all": float((np.abs(runtime_z) > 4).mean()),
        "train_abs_z_gt3_fraction_all": float((np.abs(train_z) > 3).mean()),
        "runtime_raw_feature_p99_abs": np.quantile(np.abs(runtime_x), .99, axis=0).tolist(),
    }
    report = {
        "status": "PASS_READ_ONLY_SINGLE_HF_TRACE_DIAGNOSTIC",
        "scene_id": SCENE, "sample_count": len(rows), "valid_observation_count": len(aligned),
        "target_contract": release["target_contract"], "source_raw_path": str(RAW),
        "timing_contract": {
            "training": "feature x_k predicts measured physical residual over [k-10ms,k]",
            "runtime": "at event k, output uses W_before and phi_k for [k,k+10ms]; current y_k then updates W for a later event",
            "head_observation_previous_sample_delta": 10,
            "valid_observation_interval_s": [float(min(r["obs_end"]-r["obs_start"] for r in rows if r["prev_sample"])),
                                               float(max(r["obs_end"]-r["obs_start"] for r in rows if r["prev_sample"]))],
        },
        "same_record_observation_errors_rad_s2": {
            "current_event_feature_base_vs_y_k": rmse(aligned_base, aligned_y),
            "current_event_feature_base_plus_RLS_vs_y_k": rmse(aligned_total, aligned_y),
            "previous_event_issued_base_vs_y_k": rmse(dep_base, dep_y),
            "previous_event_issued_base_plus_RLS_vs_y_k": rmse(dep_total, dep_y),
            "previous_event_actually_applied_beta_clipped_vs_y_k": rmse(dep_applied, dep_y),
        },
        "update_order_replay_rad_s2": {
            "description": "same current x_k and base_k; compare logged W_before output, RLS-only W_after replay, and full W_after replay against next measured interval y_(k+1); paired same-record counterfactual only",
            "eligible_updates_after_beta_ramp": len(update_pairs),
            "projected_updates_skipped_for_RLS_reconstruction": sum(rowsi["projection"] for rowsi in rows if rowsi["updated"] and rowsi["beta"] >= 1),
            "weight_after_to_next_event_weight_before_max_abs": float(max(continuity, default=0.0)),
            "before_output_vs_next_interval": rmse(before, next_y),
            "after_RLS_only_replay_vs_next_interval": rmse(after_rls, next_y),
            "after_full_update_replay_vs_next_interval": rmse(after_full, next_y),
            "relative_vector_rmse_change_RLS_only_vs_before": float(rmse(after_rls, next_y)["vector_rmse"] / rmse(before, next_y)["vector_rmse"] - 1),
            "relative_vector_rmse_change_full_update_vs_before": float(rmse(after_full, next_y)["vector_rmse"] / rmse(before, next_y)["vector_rmse"] - 1),
            "same_observation_fit_before_RLS": rmse(fit_before, fit_y),
            "same_observation_fit_after_RLS_only": rmse(fit_after, fit_y),
            "RLS_fit_pairs_without_projection": len(fit_pairs),
        },
        "runtime_vs_training_input_distribution": feature_shift,
        "limitations": ["one authorized W09 scene only; this is a timing screen, not a closed-loop counterfactual", "no TEST data, true inertia, Jdot, or oracle input read"],
    }
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"scene": SCENE, "valid_obs": len(aligned),
        "prev_total": report["same_record_observation_errors_rad_s2"]["previous_event_issued_base_plus_RLS_vs_y_k"]["vector_rmse"],
        "current_total": report["same_record_observation_errors_rad_s2"]["current_event_feature_base_plus_RLS_vs_y_k"]["vector_rmse"],
        "prev_applied": report["same_record_observation_errors_rad_s2"]["previous_event_actually_applied_beta_clipped_vs_y_k"]["vector_rmse"],
        "update_pairs": len(update_pairs), "before_next": report["update_order_replay_rad_s2"]["before_output_vs_next_interval"]["vector_rmse"],
        "after_RLS_only_next": report["update_order_replay_rad_s2"]["after_RLS_only_replay_vs_next_interval"]["vector_rmse"],
        "after_full_update_next": report["update_order_replay_rad_s2"]["after_full_update_replay_vs_next_interval"]["vector_rmse"],
        "report": str(OUT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
