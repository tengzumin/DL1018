"""Read-only HF task-error budget from locked TRAIN24 candidate raw files."""

import argparse
import hashlib
import json
from pathlib import Path

import h5py
import numpy as np
from scipy.spatial.transform import Rotation


ROOT = Path(__file__).resolve().parents[3]
TRAIN = ROOT / "experiments/dl_attitude_replacement_20261028/causal_n4_gate_train24_batch_v2"
SUMMARY = TRAIN / "TRAIN24_SCORE_SUMMARY_v2.json"
SCORER = ROOT / "experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_full72_v1/audits/score_full72_candidate_v1.py"
RELEASE = ROOT / "experiments/dl_attitude_replacement_20261026/mlp15_composite_dev_v3/RELEASE.json"
OUTDIR = Path(__file__).resolve().parent
IDEALIZATION_NOTE = (
    "Band removal is an offline Fourier projection of the finite-window error vector. "
    "It is not a control-reachable upper bound; it ignores causality, actuator limits, "
    "closed-loop dynamics, and SO(3) composition after correction."
)
LEAKAGE_NOTE = (
    "Finite-window leakage applies: the 20,001 samples include both t=0 and t=20 s, "
    "so the DFT's periodic extension is 20.001 s and generally has endpoint mismatch; "
    "non-bin-centered components spread across adjacent bins and band edges."
)


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def need(ok, message):
    if not ok:
        raise ValueError(message)


def band_summary(error_rotvec, time_s):
    n = len(time_s)
    dt = float(np.diff(time_s)[0])
    freqs = np.fft.rfftfreq(n, d=dt)
    coeff = np.fft.rfft(error_rotvec, axis=0)
    bin_mse = np.sum(np.abs(coeff) ** 2, axis=1) / (n * n)
    if n % 2 == 0:
        bin_mse[1:-1] *= 2.0
    else:
        bin_mse[1:] *= 2.0

    direct_mse = float(np.mean(np.sum(error_rotvec ** 2, axis=1)))
    parseval_mse = float(np.sum(bin_mse))
    parseval_abs_error = abs(parseval_mse - direct_mse)
    need(parseval_abs_error <= max(1e-14, direct_mse * 1e-11),
         f"Parseval mismatch: direct={direct_mse:.17g}, FFT={parseval_mse:.17g}")

    masks = {
        "DC": freqs == 0.0,
        "0_lt_f_lt_0p5_Hz": (freqs > 0.0) & (freqs < 0.5),
        "0p5_le_f_lt_2_Hz": (freqs >= 0.5) & (freqs < 2.0),
        "2_le_f_le_5_Hz": (freqs >= 2.0) & (freqs <= 5.0),
        "f_gt_5_Hz": freqs > 5.0,
    }
    bands = {}
    for name, mask in masks.items():
        e = float(bin_mse[mask].sum())
        residual_rmse = float(np.sqrt(max(0.0, direct_mse - e)))
        total_rmse = float(np.sqrt(direct_mse))
        bands[name] = {
            "bin_count": int(mask.sum()),
            "mse_rad2": e,
            "mse_fraction": e / direct_mse if direct_mse else 0.0,
            "rmse_after_ideal_band_deletion_rad": residual_rmse,
            "ideal_rmse_drop_rad": total_rmse - residual_rmse,
            "ideal_rmse_drop_pct": 100.0 * (total_rmse - residual_rmse) / total_rmse if total_rmse else 0.0,
            "note": IDEALIZATION_NOTE,
        }
    return {
        "sample_count": n,
        "sample_interval_s": dt,
        "record_endpoint_s": float(time_s[-1]),
        "dft_period_s": n * dt,
        "frequency_bin_width_Hz": 1.0 / (n * dt),
        "mse_direct_rad2": direct_mse,
        "mse_parseval_rad2": parseval_mse,
        "parseval_abs_error_rad2": parseval_abs_error,
        "bands": bands,
        "finite_window_leakage_note": LEAKAGE_NOTE,
    }


def candidate_path(scene_id):
    if scene_id == "DL1018_DEV_T3_C09_W09":
        base = ROOT / "experiments/dl_attitude_replacement_20261028/n4cg_v2/r1"
    elif scene_id == "DL1018_DEV_T1_C11_W12":
        base = ROOT / "experiments/dl_attitude_replacement_20261028/n4cg_v2/r2"
    else:
        base = TRAIN
    return base / "runs" / scene_id / "attempt_01" / "raw_run.mat"


def task_error(raw_path, gravity, max_tilt):
    with h5py.File(raw_path, "r") as f:
        log = f["log"]
        ref = f["scene/reference"]
        state = np.asarray(log["state"][()], dtype=np.float64).T
        time_s = np.asarray(log["time"][()], dtype=np.float64).reshape(-1)
        acceleration = np.asarray(ref["acceleration"][()], dtype=np.float64).T.copy()
        yaw = np.asarray(ref["yaw"][()], dtype=np.float64).reshape(-1)

    need(state.shape == (20001, 12), f"Unexpected state shape: {raw_path}")
    need(acceleration.shape == (20001, 3) and yaw.shape == (20001,), f"Unexpected reference shape: {raw_path}")
    need(np.isfinite(state).all() and np.isfinite(acceleration).all() and np.isfinite(yaw).all(),
         f"Non-finite task input: {raw_path}")
    need(np.max(np.abs(np.diff(time_s) - 0.001)) < 1e-10, f"Unexpected time base: {raw_path}")

    # Frozen score_full72_candidate_v1.py:115-121 task attitude construction.
    acceleration[:, 2] += gravity
    a = np.cos(yaw) * acceleration[:, 0] + np.sin(yaw) * acceleration[:, 1]
    b = np.sin(yaw) * acceleration[:, 0] - np.cos(yaw) * acceleration[:, 1]
    roll = np.arctan2(b, np.hypot(acceleration[:, 2], a))
    pitch = np.arctan2(a, acceleration[:, 2])
    scale = np.minimum(1.0, max_tilt / np.maximum(np.hypot(roll, pitch), np.finfo(float).eps))
    task = np.column_stack((roll * scale, pitch * scale, yaw))

    actual_rotation = Rotation.from_euler("xyz", state[:, 6:9])
    task_rotation = Rotation.from_euler("xyz", task)
    relative_rotation = task_rotation.inv() * actual_rotation
    error_rotvec = relative_rotation.as_rotvec()
    theta = relative_rotation.magnitude()
    return time_s, error_rotvec, float(np.sqrt(np.mean(theta ** 2)))


def analyze(scene, gravity, max_tilt, include_b):
    scene_id = scene["scene_id"]
    raw_path = candidate_path(scene_id)
    need(raw_path.is_file(), f"Missing candidate raw for {scene_id}: {raw_path}")
    time_s, error_rotvec, computed_rmse = task_error(raw_path, gravity, max_tilt)
    raw_sha = sha256(raw_path)
    summary_rmse = float(scene["task_SO3_rad"]["candidate"])
    consistency_delta = computed_rmse - summary_rmse

    result = {
        "scene_id": scene_id,
        "task": scene["task"],
        "wind_code": scene["wind_code"],
        "candidate_raw_path": str(raw_path),
        "candidate_raw_sha256": raw_sha,
        "candidate_task_rmse_from_log_SO3_rad": computed_rmse,
        "summary_candidate_task_rmse_rad": summary_rmse,
        "candidate_vs_summary_delta_rad": consistency_delta,
        "candidate_summary_consistent_1e_10": abs(consistency_delta) <= 1e-10,
        "same_scene_B_task_rmse_from_summary_rad": float(scene["task_SO3_rad"]["B"]),
        "candidate_vs_B_improvement_pct": 100.0 * (1.0 - computed_rmse / float(scene["task_SO3_rad"]["B"])),
        "error_log_vector_definition": "Log(R_task^T R_actual) as a right-multiplied SO(3) rotvec; theta=norm(rotvec).",
        "parseval": band_summary(error_rotvec, time_s),
    }
    if include_b:
        binding_path = TRAIN / "bindings" / f"{scene_id}.json"
        binding = json.loads(binding_path.read_text(encoding="utf-8"))
        b_raw_path = Path(binding["b72_scoring_raw_path"])
        expected_b_sha = binding["b72_scoring_raw_sha256"]
        need(b_raw_path.is_file(), f"Missing same-scene B raw for {scene_id}: {b_raw_path}")
        b_sha = sha256(b_raw_path)
        need(b_sha.lower() == expected_b_sha.lower(), f"B raw SHA mismatch for {scene_id}: {b_raw_path}")
        b_time_s, b_error_rotvec, b_rmse = task_error(b_raw_path, gravity, max_tilt)
        b_summary_rmse = float(scene["task_SO3_rad"]["B"])
        b_delta = b_rmse - b_summary_rmse
        need(abs(b_delta) <= 1e-10, f"Recomputed B Task RMSE does not match summary for {scene_id}")
        need(np.array_equal(time_s, b_time_s), f"Candidate/B time grids differ for {scene_id}")
        result.update({
            "same_scene_B_raw_path": str(b_raw_path),
            "same_scene_B_raw_sha256": b_sha,
            "same_scene_B_task_rmse_from_raw_SO3_rad": b_rmse,
            "summary_B_task_rmse_rad": b_summary_rmse,
            "B_vs_summary_delta_rad": b_delta,
            "B_summary_consistent_1e_10": True,
            "same_scene_B_parseval": band_summary(b_error_rotvec, b_time_s),
        })
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, choices=(1, 10), default=10)
    parser.add_argument("--include-b", action="store_true", help="Read only the 10 same-scene TRAIN B raws named by these batch bindings.")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    need(summary["schema"] == "DL1018_CAUSAL_N4_TRAIN24_BATCH_SCORE_SUMMARY_V2", "Wrong score summary schema")
    need(summary["status"] == "COMPLETE_TRAIN24_DIAGNOSTIC", "TRAIN24 score summary is not complete")
    hf_scenes = [s for s in summary["scenes"] if s.get("HF_W09_W14") is True]
    need(len(hf_scenes) == 10, f"Expected the locked 10 HF scenes, found {len(hf_scenes)}")
    scenes = hf_scenes[:args.limit]

    release = json.loads(RELEASE.read_text(encoding="utf-8"))
    gravity = float(release["gravity_mps2"])
    max_tilt = float(release["max_tilt_rad"])
    rows = [analyze(scene, gravity, max_tilt, args.include_b) for scene in scenes]
    need(all(r["candidate_summary_consistent_1e_10"] for r in rows), "Recomputed candidate Task RMSE does not match summary")

    n_scenes = len(rows)
    total_mse = float(np.mean([r["parseval"]["mse_direct_rad2"] for r in rows]))
    band_names = list(rows[0]["parseval"]["bands"])
    aggregate_bands = {}
    for name in band_names:
        e = float(np.mean([r["parseval"]["bands"][name]["mse_rad2"] for r in rows]))
        aggregate_bands[name] = {
            "mean_scene_mse_rad2": e,
            "fraction_of_mean_total_mse": e / total_mse if total_mse else 0.0,
            "rmse_after_ideal_band_deletion_rad": float(np.sqrt(max(0.0, total_mse - e))),
            "ideal_rmse_drop_pct": 100.0 * (np.sqrt(total_mse) - np.sqrt(max(0.0, total_mse - e))) / np.sqrt(total_mse) if total_mse else 0.0,
            "note": IDEALIZATION_NOTE,
        }
    candidate_macro = float(np.mean([r["candidate_task_rmse_from_log_SO3_rad"] for r in rows]))
    b_macro = float(np.mean([r["same_scene_B_task_rmse_from_summary_rad"] for r in rows]))
    paired_b = None
    if args.include_b:
        need(all(r["B_summary_consistent_1e_10"] for r in rows), "Recomputed B Task RMSE does not match summary")
        paired_b = {}
        for method, selector in (
            ("candidate", lambda r: r["parseval"]),
            ("B", lambda r: r["same_scene_B_parseval"]),
        ):
            equal_scene_mse = float(np.mean([selector(r)["mse_direct_rad2"] for r in rows]))
            band_mse = {name: float(np.mean([selector(r)["bands"][name]["mse_rad2"] for r in rows])) for name in band_names}
            ac_mse_by_scene = [sum(selector(r)["bands"][name]["mse_rad2"] for name in band_names if name != "DC") for r in rows]
            paired_b[method] = {
                "macro_task_rmse_rad": float(np.mean([
                    r["candidate_task_rmse_from_log_SO3_rad"] if method == "candidate" else r["same_scene_B_task_rmse_from_raw_SO3_rad"]
                    for r in rows
                ])),
                "mean_scene_2_to_5_Hz_rmse_rad": float(np.mean([np.sqrt(selector(r)["bands"]["2_le_f_le_5_Hz"]["mse_rad2"]) for r in rows])),
                "pooled_2_to_5_Hz_rmse_rad": float(np.sqrt(band_mse["2_le_f_le_5_Hz"])),
                "mean_scene_demeaned_AC_rmse_rad": float(np.mean([np.sqrt(e) for e in ac_mse_by_scene])),
                "pooled_demeaned_AC_rmse_rad": float(np.sqrt(sum(ac_mse_by_scene) / len(ac_mse_by_scene))),
                "mean_scene_mse_rad2": equal_scene_mse,
                "mean_scene_band_mse_rad2": band_mse,
                "parseval_max_abs_error_rad2": max(selector(r)["parseval_abs_error_rad2"] for r in rows),
            }
        for metric in ("mean_scene_2_to_5_Hz_rmse_rad", "pooled_2_to_5_Hz_rmse_rad",
                       "mean_scene_demeaned_AC_rmse_rad", "pooled_demeaned_AC_rmse_rad", "macro_task_rmse_rad"):
            c, b = paired_b["candidate"][metric], paired_b["B"][metric]
            paired_b[f"candidate_improvement_vs_B_pct_{metric}"] = 100.0 * (1.0 - c / b)
        paired_b["candidate_improvement_vs_B_pct_by_band_mse"] = {
            name: 100.0 * (1.0 - paired_b["candidate"]["mean_scene_band_mse_rad2"][name] / paired_b["B"]["mean_scene_band_mse_rad2"][name])
            for name in band_names
        }
    out = {
        "schema": "HF_TASK_ERROR_BUDGET_V1",
        "scene_count": n_scenes,
        "cohort": "Only the 10 HF_W09_W14 scenes from the completed TRAIN24 summary.",
        "metric": "SO(3) log-vector error, theta=norm(Log(R_task^T R_actual)); the N=20001 states match score_full72 task_SO3_rad.",
        "candidate_macro_task_rmse_rad": candidate_macro,
        "same_scene_B_macro_task_rmse_rad_from_summary": b_macro,
        "candidate_macro_improvement_vs_B_pct": 100.0 * (1.0 - candidate_macro / b_macro),
        "aggregate_equal_scene_parseval": {
            "mean_scene_mse_rad2": total_mse,
            "rmse_from_mean_scene_mse_rad": float(np.sqrt(total_mse)),
            "bands": aggregate_bands,
            "parseval_max_abs_error_rad2": max(r["parseval"]["parseval_abs_error_rad2"] for r in rows),
            "finite_window_leakage_note": LEAKAGE_NOTE,
        },
        "paired_candidate_vs_same_scene_B": paired_b,
        "input_sha256": {
            "score_summary": sha256(SUMMARY),
            "frozen_task_scorer": sha256(SCORER),
            "frozen_constants_release": sha256(RELEASE),
            "analysis_script": sha256(Path(__file__)),
            "candidate_raws": {r["scene_id"]: r["candidate_raw_sha256"] for r in rows},
            "same_scene_B_raws": ({r["scene_id"]: r["same_scene_B_raw_sha256"] for r in rows} if args.include_b else None),
            "batch_bindings": ({r["scene_id"]: sha256(TRAIN / "bindings" / f"{r['scene_id']}.json") for r in rows} if args.include_b else None),
        },
        "frozen_task_formula_source": str(SCORER),
        "frozen_constants_source": str(RELEASE),
        "scope_note": ("B Task RMSE is read from the same-scene summary rows. No Plant, VAL, TEST, inertia reconstruction, or legacy DL1018_TRAIN input is read."
                       if not args.include_b else
                       "Reads only these 10 HF candidate raws plus the 10 same-scene TRAIN B raws explicitly named and SHA-bound by this batch's per-scene bindings. No Plant, VAL, TEST, inertia reconstruction, or legacy DL1018_TRAIN input is read."),
        "scenes": rows,
    }
    suffix = "_with_B" if args.include_b else ""
    output = args.output or OUTDIR / f"HF_TASK_BUDGET_v1_{n_scenes}scene{'s' if n_scenes != 1 else ''}{suffix}.json"
    output = output.resolve()
    need(output.parent == OUTDIR.resolve(), f"Output must stay in hfbudget_v1: {output}")
    output.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "scenes": n_scenes,
        "candidate_macro_task_rmse_rad": candidate_macro,
        "same_scene_B_macro_task_rmse_rad": b_macro,
        "improvement_vs_B_pct": out["candidate_macro_improvement_vs_B_pct"],
        "parseval_max_abs_error_rad2": out["aggregate_equal_scene_parseval"]["parseval_max_abs_error_rad2"],
        "max_candidate_summary_delta_rad": max(abs(r["candidate_vs_summary_delta_rad"]) for r in rows),
        "aggregate_band_mse_fractions": {k: v["fraction_of_mean_total_mse"] for k, v in aggregate_bands.items()},
    }, indent=2))


if __name__ == "__main__":
    main()
