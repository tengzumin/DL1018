"""Paired offline signed SO(3)-log decomposition for the six notch/B scenes."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import h5py
import numpy as np
from scipy.spatial.transform import Rotation

HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
ROOT = HERE.parents[3]
SCORE = HERE / "NOTCH_HF6_FROZEN_SCORE_v2.json"
BASELINE_TAU = ROOT / "experiments/dl_attitude_replacement_20261028/gru_cosine_c5_notch35_tau01_v1/runs/DL1018_VAL_T3_C01_W14/raw_run.mat"
OUT = HERE / "NOTCH_TASK_ERROR_DECOMPOSITION_v1.json"
DT = 0.001
BANDS = [(0, .5), (.5, 2), (2, 5), (5, 10), (10, 20), (20, 50), (50, 100), (100, 500)]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_trace(path: Path):
    with h5py.File(path, "r") as f:
        log, ref = f["log"], f["scene/reference"]
        state = np.asarray(log["state"][()], float).T
        inner = np.asarray(log["filtered_attitude_reference"][()], float).T
        target = np.asarray(log["command_filter_target_euler"][()], float).T
        acc = np.asarray(ref["acceleration"][()], float).T
        yaw = np.asarray(ref["yaw"][()], float).reshape(-1)
        time = np.asarray(log["time"][()], float).reshape(-1)
    acc[:, 2] += 9.8
    a = np.cos(yaw) * acc[:, 0] + np.sin(yaw) * acc[:, 1]
    b = np.sin(yaw) * acc[:, 0] - np.cos(yaw) * acc[:, 1]
    roll = np.arctan2(b, np.hypot(acc[:, 2], a))
    pitch = np.arctan2(a, acc[:, 2])
    scale = np.minimum(1.0, (np.pi / 6) / np.maximum(np.hypot(roll, pitch), np.finfo(float).eps))
    task = np.column_stack((roll * scale, pitch * scale, yaw))
    assert state.shape == (20001, 12) and task.shape == (20001, 3)
    assert inner.shape == target.shape == (20000, 3) and time.shape == (20001,)
    return time, state[:, 6:9], task, inner, target, acc, yaw


def relative_log(reference: np.ndarray, target: np.ndarray) -> np.ndarray:
    return (Rotation.from_euler("xyz", reference).inv() *
            Rotation.from_euler("xyz", target)).as_rotvec()


def band_power(x: np.ndarray) -> dict:
    x = x - np.mean(x, axis=0, keepdims=True)
    n = len(x)
    spec = np.fft.rfft(x, axis=0)
    p = np.abs(spec) ** 2 / n**2
    if n % 2 == 0:
        p[1:-1] *= 2
    else:
        p[1:] *= 2
    hz = np.fft.rfftfreq(n, DT)
    out = {}
    for lo, hi in BANDS:
        q = p[(hz >= lo) & (hz < hi)]
        axis = np.sum(q, axis=0)
        out[f"{lo:g}-{hi:g}Hz"] = {"axis_rms_rad": np.sqrt(axis).tolist(),
                                     "vector_rms_rad": float(np.sqrt(axis.sum()))}
    return out


def band_cross(x: np.ndarray, y: np.ndarray) -> dict:
    x, y = x-np.mean(x, axis=0), y-np.mean(y, axis=0)
    n = len(x)
    fx, fy = np.fft.rfft(x, axis=0), np.fft.rfft(y, axis=0)
    px, py = np.abs(fx)**2/n**2, np.abs(fy)**2/n**2
    cross = np.real(np.conj(fx)*fy)/n**2
    factor = np.full(len(cross), 2.0)
    factor[0] = 1.0
    if n % 2 == 0:
        factor[-1] = 1.0
    px, py, cross = px*factor[:, None], py*factor[:, None], cross*factor[:, None]
    hz = np.fft.rfftfreq(n, DT)
    out = {}
    for lo, hi in BANDS:
        mask = (hz >= lo) & (hz < hi)
        cx, ax, ay = np.sum(cross[mask], axis=0), np.sum(px[mask], axis=0), np.sum(py[mask], axis=0)
        corr = cx/np.sqrt(np.maximum(ax*ay, np.finfo(float).tiny))
        out[f"{lo:g}-{hi:g}Hz"] = {"cross_rad2_by_axis": cx.tolist(),
                                     "normalized_cross_by_axis": corr.tolist(),
                                     "cross_rad2_total": float(cx.sum())}
    return out


def summarize(x: np.ndarray) -> dict:
    return {"signed_mean_rad": np.mean(x, axis=0).tolist(),
            "axis_rmse_rad": np.sqrt(np.mean(x*x, axis=0)).tolist(),
            "vector_rmse_rad": float(np.sqrt(np.mean(np.sum(x*x, axis=1)))),
            "band_fluctuation": band_power(x)}


def main():
    score_doc = json.loads(SCORE.read_text(encoding="utf-8"))
    require = lambda cond, msg: (_ for _ in ()).throw(RuntimeError(msg)) if not cond else None
    require(score_doc["status"] == "COMPLETE_HF6_DEVELOPMENT_SCREEN", "HF6 frozen score incomplete")
    metric = Path(score_doc["frozen_metric_path"])
    require(sha(metric) == score_doc["frozen_metric_sha256"], "frozen scorer changed")
    spec = importlib.util.spec_from_file_location("frozen_score", metric)
    scorer = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = scorer
    spec.loader.exec_module(scorer)

    all_rows = []
    stage_names = ("task_to_target", "target_to_filtered", "task_to_filtered",
                   "filtered_to_actual", "task_to_actual")
    for row in score_doc["scene_results"]:
        traces = {}
        for method in ("Applied_Notch_3p5Hz_Q1", "B"):
            binding = row["bindings"][method]
            path = Path(binding["raw_path"])
            require(sha(path) == binding["raw_sha256"], f"raw hash mismatch {row['scene_id']} {method}")
            traces[method] = load_trace(path)
        cn, bn = traces["Applied_Notch_3p5Hz_Q1"], traces["B"]
        require(np.array_equal(cn[0], bn[0]) and np.array_equal(cn[2], bn[2]),
                f"scene reference/time differs across paired runs: {row['scene_id']}")
        # Signed principal rotation logs; component axes are each residual's reference frame.
        n = {
            "task_to_target": relative_log(cn[2][:20000], cn[4]),
            "target_to_filtered": relative_log(cn[4], cn[3]),
            "task_to_filtered": relative_log(cn[2][:20000], cn[3]),
            "filtered_to_actual": relative_log(cn[3], cn[1][:20000]),
            "task_to_actual": relative_log(cn[2][:20000], cn[1][:20000]),
        }
        b = {
            "task_to_target": relative_log(bn[2][:20000], bn[4]),
            "target_to_filtered": relative_log(bn[4], bn[3]),
            "task_to_filtered": relative_log(bn[2][:20000], bn[3]),
            "filtered_to_actual": relative_log(bn[3], bn[1][:20000]),
            "task_to_actual": relative_log(bn[2][:20000], bn[1][:20000]),
        }
        stages = {}
        for name in stage_names:
            stages[name] = {
                "notch": summarize(n[name]), "B": summarize(b[name]),
                "paired_signed_delta_notch_minus_B": {
                    "mean_rad": np.mean(n[name]-b[name], axis=0).tolist(),
                    "axis_rmse_rad": np.sqrt(np.mean((n[name]-b[name])**2, axis=0)).tolist(),
                    "band_fluctuation": band_power(n[name]-b[name]),
                },
                "band_power_delta_notch_minus_B_rad2": {
                    band: [float(nn*nn - bb*bb) for nn, bb in zip(
                        stages_axis(n[name], lo, hi), stages_axis(b[name], lo, hi))]
                    for band, (lo, hi) in zip((f"{lo:g}-{hi:g}Hz" for lo, hi in BANDS), BANDS)
                },
            }
        stage_cross = {
            method: band_cross(parts["task_to_target"], parts["target_to_filtered"])
            for method, parts in (("notch", n), ("B", b))
        }
        all_rows.append({"scene_id": row["scene_id"], "stages": stages,
                         "task_target_target_filtered_cross": stage_cross})

    macro = {}
    for stage in stage_names:
        macro[stage] = {}
        for method in ("notch", "B"):
            macro[stage][method] = {
                "mean_vector_rmse_rad": float(np.mean([r["stages"][stage][method]["vector_rmse_rad"] for r in all_rows])),
                "mean_axis_rmse_rad": np.mean([r["stages"][stage][method]["axis_rmse_rad"] for r in all_rows], axis=0).tolist(),
                "mean_signed_bias_rad": np.mean([r["stages"][stage][method]["signed_mean_rad"] for r in all_rows], axis=0).tolist(),
                "mean_band_vector_rms_rad": {band: float(np.mean([r["stages"][stage][method]["band_fluctuation"][band]["vector_rms_rad"] for r in all_rows])) for band in all_rows[0]["stages"][stage][method]["band_fluctuation"]},
            }
        macro[stage]["mean_band_power_delta_notch_minus_B_rad2_by_axis"] = {
            band: np.mean([r["stages"][stage]["band_power_delta_notch_minus_B_rad2"][band] for r in all_rows], axis=0).tolist()
            for band in all_rows[0]["stages"][stage]["band_power_delta_notch_minus_B_rad2"]
        }
    tau_metrics = None
    if BASELINE_TAU.is_file():
        m = scorer.score_raw(BASELINE_TAU, 9.8, np.pi/6)
        tau_metrics = {"raw_path": str(BASELINE_TAU), "raw_sha256": sha(BASELINE_TAU),
                       "Q_mm": 1000*m["Q_m"], "task_SO3_mrad": 1000*m["task_SO3_rad"],
                       "inner_SO3_mrad": 1000*m["inner_SO3_rad"]}
    result = {
        "schema": "DL1018_NOTCH_TASK_ERROR_DECOMPOSITION_V1",
        "scope": "Read-only paired six-scene notch-vs-B signed rotation-log and DFT band-energy analysis; development screen only.",
        "task_reference": "Frozen FULL72 reconstruction from reference acceleration + yaw, gravity 9.8, tilt cap pi/6.",
        "rotation_log_convention": "principal Log(R_ref.T R_target), xyz Euler rotation matrices; residual components are signed and expressed in each stage reference frame.",
        "frequency_bands_hz": BANDS,
        "frequency_method": "demeaned signed-log vectors, one-sided Parseval DFT energy at 1 ms sampling; signed mean reported separately as DC bias.",
        "scenes": all_rows, "macro": macro, "notch_plus_tau01_first_scene_frozen_score": tau_metrics,
        "Plant_calls": 0, "TEST_read": False, "inertia_reconstruction": False,
    }
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(OUT), "macro": macro, "notch_plus_tau01_first_scene": tau_metrics}, indent=2))


def stages_axis(x: np.ndarray, lo: float, hi: float) -> np.ndarray:
    return np.array([entry["axis_rms_rad"] for entry in [band_power(x)[f"{lo:g}-{hi:g}Hz"]]][0])


if __name__ == "__main__":
    main()
