#!/usr/bin/env python3
"""Read-only one-event dAtt persistence check on frozen VAL+DEV raw logs."""
from __future__ import annotations
import csv
import hashlib
import json
import math
from pathlib import Path
import sys

import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
PHASE1 = Path(__file__).resolve().parent
STAGE = PHASE1 / ".datt_lag_proxy_v1_staging"
OUT = PHASE1 / "datt_lag_proxy_v1"
sys.path.insert(0, str(PHASE1))
import datt_nextblock_diagnostic as base  # frozen identity/path validators


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def lag_metrics(datt: np.ndarray) -> dict:
    previous, current = datt[:, :-1], datt[:, 1:]
    error = current - previous
    norm_previous = np.linalg.norm(previous, axis=0)
    norm_current = np.linalg.norm(current, axis=0)
    valid_cos = (norm_previous > 1e-12) & (norm_current > 1e-12)
    cosine = np.sum(previous[:, valid_cos] * current[:, valid_cos], axis=0) / (
        norm_previous[valid_cos] * norm_current[valid_cos]
    )
    current_rms = float(np.sqrt(np.mean(np.sum(current * current, axis=0))))
    error_rms = float(np.sqrt(np.mean(np.sum(error * error, axis=0))))
    result = {
        "n_pairs": int(previous.shape[1]),
        "datt_current_vector_rms_mps2": current_rms,
        "datt_previous_vector_rms_mps2": float(np.sqrt(np.mean(np.sum(previous * previous, axis=0)))),
        "persistence_prediction_vector_rmse_mps2": error_rms,
        "persistence_prediction_vector_nrmse": error_rms / max(current_rms, 1e-12),
        "mean_pair_cosine": float(np.mean(cosine)) if cosine.size else None,
        "median_pair_cosine": float(np.median(cosine)) if cosine.size else None,
        "positive_cosine_fraction": float(np.mean(cosine > 0.0)) if cosine.size else None,
        "cosine_valid_pairs": int(cosine.size),
    }
    for axis, i in zip(("x", "y", "z"), range(3)):
        p, c = previous[i], current[i]
        if np.std(p) > 1e-15 and np.std(c) > 1e-15:
            result[f"{axis}_lag_correlation"] = float(np.corrcoef(p, c)[0, 1])
        else:
            result[f"{axis}_lag_correlation"] = None
        nonzero = (np.abs(p) > 1e-12) & (np.abs(c) > 1e-12)
        result[f"{axis}_sign_pairs"] = int(np.sum(nonzero))
        result[f"{axis}_sign_agreement"] = (
            float(np.mean(np.sign(p[nonzero]) == np.sign(c[nonzero]))) if np.any(nonzero) else None
        )
    return result


def self_check() -> None:
    synthetic = np.array([[0.0, 1.0, 2.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]])
    got = lag_metrics(synthetic)
    assert got["n_pairs"] == 2 and got["cosine_valid_pairs"] == 1
    assert abs(got["mean_pair_cosine"] - 1.0) < 1e-12
    assert abs(got["persistence_prediction_vector_nrmse"] - 1.0 / math.sqrt(2.5)) < 1e-12


def summarize(rows: list[dict], name: str) -> dict:
    result = {"group": name, "n_scenes": len(rows), "n_pairs": sum(r["n_pairs"] for r in rows)}
    for key in (
        "persistence_prediction_vector_nrmse", "mean_pair_cosine", "positive_cosine_fraction",
        "x_lag_correlation", "y_lag_correlation", "z_lag_correlation",
        "x_sign_agreement", "y_sign_agreement", "z_sign_agreement",
    ):
        vals = [float(r[key]) for r in rows if r.get(key) is not None and math.isfinite(float(r[key]))]
        result[f"{key}_scene_macro_mean"] = float(np.mean(vals)) if vals else None
        result[f"{key}_scene_macro_median"] = float(np.median(vals)) if vals else None
    vals = [float(r["mean_pair_cosine"]) for r in rows if r.get("mean_pair_cosine") is not None]
    result["fraction_scenes_positive_mean_cosine"] = float(np.mean(np.asarray(vals) > 0.0)) if vals else None
    result["warning"] = "descriptive within-trajectory persistence only; not causal, not a treatment effect, not a safety bound"
    return result


def run() -> None:
    self_check()
    if STAGE.exists() or OUT.exists():
        raise RuntimeError(f"refusing to overwrite {STAGE} or {OUT}")
    for path, expected in ((base.INPUT, base.EXPECTED_MANIFEST_SHA256),
                           (base.PAIR_CSV, base.EXPECTED_PAIR_SHA256)):
        if sha256(path).lower() != expected:
            raise RuntimeError(f"pinned input hash mismatch: {path}")
    index_by_sha = base.frozen_raw_index_map()
    manifest = base.csv_rows(base.INPUT)
    pair_rows = [r for r in base.csv_rows(base.PAIR_CSV) if r.get("method_id") == base.METHOD_ID]
    pair_by_sha = {r["candidate_raw_sha256"].lower(): r for r in pair_rows}
    if (len(index_by_sha) != 72 or len(manifest) != 72 or len(pair_by_sha) != 72
            or {r["split"] for r in manifest} != {"VAL", "DEV"}
            or set(pair_by_sha) != set(index_by_sha)):
        raise RuntimeError("inputs must identify exactly the frozen non-TEST VAL+DEV 72 scenes")

    scene_rows, raw_hashes = [], []
    for row in sorted(manifest, key=lambda r: r["scene_id"]):
        raw_path = base.validate_manifest_row(row, index_by_sha, pair_by_sha)
        before = sha256(raw_path)
        if before.lower() != row["raw_sha256_before"].lower():
            raise RuntimeError(f"raw SHA mismatch before read: {row['scene_id']}")
        with h5py.File(raw_path, "r") as f:
            def get(name: str) -> np.ndarray:
                return np.asarray(f[name], dtype=np.float64)
            times = get("log/transition_time").reshape(-1)
            event = get("log/position_event_flag").reshape(-1) > 0
            stage = get("log/stage1_position_event").reshape(-1) > 0
            if not np.array_equal(event, stage):
                raise RuntimeError(f"position event flags differ: {row['scene_id']}")
            event_idx = np.flatnonzero(event)
            expected_idx = np.arange(10, 20000, 10, dtype=np.int64)
            if not np.array_equal(event_idx, expected_idx):
                raise RuntimeError(f"unexpected event grid: {row['scene_id']}")
            valid = get("log/stage1_position_event_inference_valid").reshape(-1)[event_idx] > 0
            valid_idx = event_idx[valid]
            if int(np.sum(valid)) != 1968:
                raise RuntimeError(f"unexpected valid event count: {row['scene_id']}")
            valid_times = times[valid_idx]
            if np.max(np.abs(np.diff(valid_times) - 0.01)) > 1e-12:
                raise RuntimeError(f"valid events are not consecutive 100 Hz samples: {row['scene_id']}")
            state = get("log/state")
            raw_att = get("log/raw_outer_attitude")[:, valid_idx]
            requested = get("log/controller_clipped_generalized")[:, valid_idx]
            mass = float(get("cfg/plant/mass").item())
            if state.shape[0] != 12 or mass <= 0 or not math.isfinite(mass):
                raise RuntimeError(f"invalid state shape or mass: {row['scene_id']}")
            actual_axis = base.rotation_z_axis(state[6:9, valid_idx])
            raw_axis = base.rotation_z_axis(raw_att)
            datt = (actual_axis - raw_axis) * (requested[0] / mass)[None, :]
            bound = 2.0 * requested[0] / mass
            if (not np.all(np.isfinite(datt))
                    or np.max(np.linalg.norm(datt, axis=0) - bound) > 1e-12):
                raise RuntimeError(f"dAtt finite/geometric bound check failed: {row['scene_id']}")
            stats = lag_metrics(datt)
            wind = int(row["wind_index"])
            wind_group = "W00_W08" if wind <= 8 else "W09_W14" if wind <= 14 else "W15"
            if row["band"].replace("-", "_") != wind_group:
                raise RuntimeError(f"wind group mismatch: {row['scene_id']}")
            scene_rows.append({
                "scene_id": row["scene_id"], "split": row["split"], "task": row["task"],
                "wind_index": wind, "wind_group": wind_group, "raw_sha256": before,
                "valid_event_count": int(valid_idx.size),
                "datt_current_rms_mps2": float(np.sqrt(np.mean(np.sum(datt * datt, axis=0)))),
                "datt_current_max_norm_mps2": float(np.max(np.linalg.norm(datt, axis=0))),
                "pointwise_bound_max_2T_over_m_mps2": float(np.max(bound)),
                **stats,
            })
        after = sha256(raw_path)
        if after != before:
            raise RuntimeError(f"raw changed during read: {row['scene_id']}")
        raw_hashes.append((row["scene_id"], before))

    if len({sha for _, sha in raw_hashes}) != 72:
        raise RuntimeError("raw hashes are not unique")
    summaries = [summarize(scene_rows, "ALL72")]
    for split in ("VAL", "DEV"):
        summaries.append(summarize([r for r in scene_rows if r["split"] == split], split))
    for wind_group in ("W00_W08", "W09_W14", "W15"):
        selected = [r for r in scene_rows if r["wind_group"] == wind_group]
        summaries.append(summarize(selected, wind_group))
        for split in ("VAL", "DEV"):
            summaries.append(summarize([r for r in selected if r["split"] == split], f"{wind_group}_{split}"))

    STAGE.mkdir()
    for name, rows in (("datt_lag_proxy_scene_summary.csv", scene_rows),
                       ("datt_lag_proxy_group_summary.csv", summaries)):
        with (STAGE / name).open("x", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    metadata = {
        "schema": "DATT_LAG_PROXY_DESCRIPTIVE_V1",
        "analysis_role": "offline descriptive persistence diagnostic on existing VAL+DEV raw; not an experiment",
        "test_accessed": False,
        "inputs": {
            "mechanism_manifest_sha256": sha256(base.INPUT),
            "paired_score_table_sha256": sha256(base.PAIR_CSV),
            "frozen_raw_indexes": {str(p): expected for p, expected in base.INDEX_SOURCES},
            "scene_count": len(scene_rows), "split_set": sorted({r["split"] for r in scene_rows}),
            "raw_identity_set_sha256": hashlib.sha256("\n".join(
                f"{scene}:{sha}" for scene, sha in sorted(raw_hashes)
            ).encode()).hexdigest(),
        },
        "signal": "dAtt_k=(R_actual_k-R_raw_k)e3*T_req_k/m_true; computed after event k command and compared with dAtt_(k+1), the persistence predictor available one event later",
        "timing": "100 Hz events; one event lag is 0.01 s; only valid inference events, consecutive within each scene",
        "metrics": "scene-level vector persistence RMSE/cosine and per-axis correlation/sign agreement; group summaries macro-average scenes",
        "geometric_bound": "||dAtt_k||_2 <= 2*T_req_k/m_true, checked pointwise; this is not a safety or lag-error bound",
        "limits": [
            "uses oracle simulated attitude and true mass; sensor/mass estimator error is not represented",
            "closed-loop trajectories would change under intervention; same-trajectory persistence is not a causal treatment result",
            "no alpha, saturation safety margin, stability proof, or performance qualification is inferred",
            "all 72 raw files are VAL/DEV; TEST48 is not accessed",
        ],
        "command": "python -B reports/paper14_v2/phase1/datt_lag_proxy_analysis.py",
    }
    (STAGE / "datt_lag_proxy_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8"
    )
    STAGE.rename(OUT)
    print(json.dumps({"output": str(OUT), "groups": summaries}, indent=2, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    run()
