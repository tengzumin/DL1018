#!/usr/bin/env python3
"""Read-only one-second dAtt to next-block Z-RMSE diagnostic for corrected DSSM14 full72."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import time

import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
BASE = ROOT.parent / "REFERENCE_FIX_FULL72_20261021_022342_313"
INPUT = OUT / "mechanism_components_by_scene.csv"
PAIR_CSV = ROOT / "reports" / "corrected14_full72_benchmark_20261021" / "PAIR14_SCENE_RESULTS_VS_B.csv"
INDEX_SOURCES = [
    (BASE / "corrected_reference_training_v1" / "corrected_pair_eval_v1" / "reports" / "RAW_INDEX.csv",
     "364367e46ae8e3eb3335efd34a834b984a2a87fc1cef0dd5bf4991bbf342d8b4"),
    (BASE / "corrected_reference_training_v1" / "corrected_pair_eval_tail21_v1" / "reports" / "RAW_INDEX.csv",
     "3527883329ec23f51928d3967071d307a42683adc831cee8958822c7b732d116"),
]
EXPECTED_MANIFEST_SHA256 = "f1ba9ff2335ea75e992436f753fb75ff1678271f33bf6d2fe706db4b45572e3b"
EXPECTED_PAIR_SHA256 = "b2264145e9d18896f5764ffe38302576dd08c80e7cce1c277323246092169137"
EXPECTED_MODEL_SHA256 = "6f3628b10540c617496b2a20f249c4319af79c1a02d5945f1f91f0aead9c9b6e"
METHOD_ID = "CORRECTED_TRAIN_DSSM14_G12_R32"
CANONICAL_MODEL_ID = "CORRECTED_DSSM14_SEED2026102001_FINAL60000"
SEED = 2026102201
BOOTSTRAPS = 2000
MIN_SCENES_FOR_POINT = 5
MIN_SCENES_FOR_CI = 20
DATT_EPS_MPS2 = 1e-12
FINAL_DIR = OUT / "datt_nextblock_v1"
STAGE_DIR = OUT / ".datt_nextblock_v1_staging"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise RuntimeError(f"refusing to write empty output: {path}")
    with path.open("x", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def rotation_z_axis(euler: np.ndarray) -> np.ndarray:
    roll, pitch, yaw = euler
    cp, sp = np.cos(roll), np.sin(roll)
    ct, st = np.cos(pitch), np.sin(pitch)
    cy, sy = np.cos(yaw), np.sin(yaw)
    return np.vstack((cy * st * cp + sy * sp,
                      sy * st * cp - cy * sp,
                      ct * cp))


def residualize_two_way(values: np.ndarray, scene_code: np.ndarray, block_code: np.ndarray,
                        n_scene: int, n_block: int) -> np.ndarray | None:
    out = values.astype(np.float64, copy=True)
    scene_counts = np.bincount(scene_code, minlength=n_scene).astype(np.float64)
    block_counts = np.bincount(block_code, minlength=n_block).astype(np.float64)
    if np.any(scene_counts == 0) or np.any(block_counts == 0):
        return None
    for _ in range(1000):
        before = out.copy()
        out -= np.bincount(scene_code, weights=out, minlength=n_scene)[scene_code] / scene_counts[scene_code]
        out -= np.bincount(block_code, weights=out, minlength=n_block)[block_code] / block_counts[block_code]
        if np.max(np.abs(out - before)) < 1e-13:
            return out
    raise RuntimeError("two-way fixed-effect residualization failed to converge")


def fixed_effect_fit(clusters: list[list[dict]]) -> tuple[float, float] | None:
    records = [(cluster_i, row) for cluster_i, cluster in enumerate(clusters) for row in cluster]
    if not records:
        return None
    scene_code = np.fromiter((i for i, _ in records), dtype=np.int64)
    block_values = np.array([int(r["source_block"]) for _, r in records], dtype=np.int64)
    _, block_code = np.unique(block_values, return_inverse=True)
    n_scene, n_block = len(clusters), int(np.max(block_code)) + 1
    x = np.array([float(r["projection_mean_mps2"]) for _, r in records])
    current = np.array([float(r["source_z_rmse_m"]) for _, r in records])
    y = np.array([float(r["target_z_rmse_m"]) for _, r in records])
    rx = residualize_two_way(x, scene_code, block_code, n_scene, n_block)
    rc = residualize_two_way(current, scene_code, block_code, n_scene, n_block)
    ry = residualize_two_way(y, scene_code, block_code, n_scene, n_block)
    if rx is None or rc is None or ry is None:
        return None
    coef, _, rank, _ = np.linalg.lstsq(np.column_stack((rx, rc)), ry, rcond=None)
    if rank < 2 or not np.all(np.isfinite(coef)):
        return None
    return float(coef[0]), float(coef[1])


def self_check() -> None:
    rng = np.random.default_rng(17)
    clusters = []
    for i in range(6):
        cluster = []
        for j in range(8):
            x = float(rng.normal())
            current = 0.01 + 0.0004 * i + 0.0002 * j + float(rng.normal()) * 0.001
            y = 0.003 * i + 0.0007 * j + 2.0 * x + 0.6 * current
            cluster.append({"source_block": j, "projection_mean_mps2": x,
                            "source_z_rmse_m": current, "target_z_rmse_m": y})
        clusters.append(cluster)
    fit = fixed_effect_fit(clusters)
    assert fit is not None and abs(fit[0] - 2.0) < 1e-10 and abs(fit[1] - 0.6) < 1e-10


def frozen_raw_index_map() -> dict[str, dict]:
    by_sha: dict[str, dict] = {}
    for index_path, expected_sha in INDEX_SOURCES:
        if sha256(index_path).lower() != expected_sha:
            raise RuntimeError(f"frozen raw-index SHA mismatch: {index_path}")
        allowed_runs = (index_path.parent.parent / "runs").resolve()
        for item in csv_rows(index_path):
            if not (item.get("method_id") == METHOD_ID and item.get("action") == "RUN"
                    and item.get("status") == "RUN_COMPLETE_STABLE"
                    and item.get("complete", "").lower() == "true"
                    and item.get("finite", "").lower() == "true"):
                continue
            raw_path = (ROOT.parent / Path(*item["raw_path"].split("\\"))).resolve()
            if not raw_path.is_relative_to(allowed_runs):
                raise RuntimeError(f"raw path outside locked index runs directory: {raw_path}")
            if item.get("model_id") != CANONICAL_MODEL_ID or item.get("model_sha256", "").lower() != EXPECTED_MODEL_SHA256:
                raise RuntimeError(f"raw-index model identity mismatch: {item.get('runtime_scene_id')}")
            raw_sha = item["raw_sha256"].lower()
            if raw_sha in by_sha:
                raise RuntimeError(f"duplicate raw SHA in frozen indexes: {raw_sha}")
            by_sha[raw_sha] = {
                "path": raw_path, "source": index_path.resolve(), "index_sha256": expected_sha,
                "runtime_scene_id": item["runtime_scene_id"], "split": item["split"],
                "task": item["task"], "wind_index": int(item["wind_index"]), "raw_sha256": raw_sha,
            }
    if len(by_sha) != 72:
        raise RuntimeError(f"frozen raw indexes must whitelist exactly 72 candidate raws, got {len(by_sha)}")
    return by_sha


def validate_manifest_row(row: dict[str, str], index_by_sha: dict[str, dict], pair_by_sha: dict[str, dict]) -> Path:
    raw_sha = row["raw_sha256_before"].lower()
    item = index_by_sha.get(raw_sha)
    if item is None:
        raise RuntimeError(f"manifest raw SHA absent from frozen indexes: {row['scene_id']}")
    raw_path = Path(row["raw_path"]).resolve()
    if (raw_path != item["path"] or Path(row["raw_index_source_file"]).resolve() != item["source"]
            or row["raw_index_sha256"].lower() != item["index_sha256"]
            or row["raw_sha256_after"].lower() != raw_sha
            or row["raw_index_scene_id"] != item["runtime_scene_id"]
            or row["split"] != item["split"] or row["task"] != item["task"]
            or int(row["wind_index"]) != item["wind_index"]
            or row["model_id"] != CANONICAL_MODEL_ID or row["model_sha256"].lower() != EXPECTED_MODEL_SHA256):
        raise RuntimeError(f"manifest provenance mismatch: {row['scene_id']}")
    expected_match = "EXACT" if row["scene_id"] == item["runtime_scene_id"] else "ALIAS_ACC_FIX_V1"
    if row["raw_index_id_match"] != expected_match:
        raise RuntimeError(f"raw-index scene alias rule mismatch: {row['scene_id']}")
    wind = item["wind_index"]
    expected_band = "W00-W08" if wind <= 8 else "W09-W14" if wind <= 14 else "W15"
    if row["band"] != expected_band or row["outcome"] not in {"WIN", "LOSS", "TIE"}:
        raise RuntimeError(f"unexpected wind/outcome label: {row['scene_id']}")
    paired = pair_by_sha.get(raw_sha)
    if paired is None:
        raise RuntimeError(f"raw absent from canonical paired score table: {row['scene_id']}")
    score_values = np.array([
        float(row["candidate_q_m"]), float(row["B_q_m"]),
        float(paired["candidate_Q_0_20_m"]), float(paired["B_Q_0_20_m"]),
    ], dtype=np.float64)
    if not np.all(np.isfinite(score_values)):
        raise RuntimeError(f"nonfinite paired score: {row['scene_id']}")
    if (paired["source_scene_id"] != row["scene_id"] or paired["split"] != row["split"]
            or paired["task"] != row["task"] or paired["result_vs_B"] != row["outcome"]
            or abs(float(paired["candidate_Q_0_20_m"]) - float(row["candidate_q_m"])) > 1e-12
            or abs(float(paired["B_Q_0_20_m"]) - float(row["B_q_m"])) > 1e-12):
        raise RuntimeError(f"canonical score/outcome mismatch: {row['scene_id']}")
    return raw_path


def collect_scene(row: dict[str, str], raw_path: Path) -> tuple[list[dict], dict]:
    scene = row["scene_id"]
    before_stat = raw_path.stat()
    before_sha = sha256(raw_path)
    if before_sha.lower() != row["raw_sha256_before"].lower():
        raise RuntimeError(f"raw SHA mismatch before read: {scene}")

    with h5py.File(raw_path, "r") as f:
        def get(name: str) -> np.ndarray:
            return np.asarray(f[name], dtype=np.float64)

        times = get("log/transition_time").reshape(-1)
        state = get("log/state")
        ref = get("log/reference/position")
        if times.size != 20000 or state.shape[1] != 20001 or ref.shape[1] != 20001:
            raise RuntimeError(f"unexpected 20 s score grid: {scene} {times.shape}/{state.shape}/{ref.shape}")
        expected_times = np.arange(20000, dtype=np.float64) * 0.001
        if (not np.all(np.isfinite(times)) or not np.all(np.isfinite(state)) or not np.all(np.isfinite(ref))
                or np.max(np.abs(times - expected_times)) > 1e-12):
            raise RuntimeError(f"invalid or mismatched 1 kHz score grid: {scene}")

        z_error = state[2, :20000] - ref[2, :20000]
        block_rmse = []
        for j in range(20):
            mask = (times >= j) & (times < j + 1)
            if int(np.sum(mask)) != 1000:
                raise RuntimeError(f"unexpected 1 kHz samples in block {j}: {scene}")
            block_rmse.append(float(np.sqrt(np.mean(z_error[mask] ** 2))))

        event = get("log/position_event_flag").reshape(-1) > 0
        stage_event = get("log/stage1_position_event").reshape(-1) > 0
        if not np.array_equal(event, stage_event):
            raise RuntimeError(f"position event flags differ: {scene}")
        event_idx = np.flatnonzero(event)
        event_times = times[event_idx]
        expected_event_idx = np.arange(10, 20000, 10, dtype=np.int64)
        expected_event_times = np.arange(1, 2000, dtype=np.float64) / 100.0
        if (not np.array_equal(event_idx, expected_event_idx)
                or np.max(np.abs(event_times - expected_event_times)) > 1e-12):
            raise RuntimeError(f"position events are shifted from exact 0.01..19.99 s grid: {scene}")
        valid = get("log/stage1_position_event_inference_valid").reshape(-1)[event_idx] > 0
        valid_idx = event_idx[valid]
        valid_times = times[valid_idx]
        if int(np.sum(valid)) != 1968:
            raise RuntimeError(f"unexpected valid event count: {scene}")

        actual_att = rotation_z_axis(state[6:9, valid_idx])
        raw_att = rotation_z_axis(get("log/raw_outer_attitude")[:, valid_idx])
        realized = get("log/realized_generalized")[:, valid_idx]
        requested = get("log/controller_clipped_generalized")[:, valid_idx]
        wind = get("log/wind_force_I")[:, valid_idx]
        nominal = get("log/position_nominal_acceleration_mps2")[:, valid_idx]
        applied = get("log/stage1_position_applied_acceleration_mps2")[:, valid_idx]
        output = get("log/stage1_position_event_applied_acceleration_mps2")[:, valid_idx]
        beta = get("log/stage1_position_event_beta").reshape(-1)[valid_idx]
        mass = float(get("cfg/plant/mass").item())
        gravity = float(get("cfg/plant/g").item())
        dmax = get("cfg/rbf/position/dmax").reshape(-1)
        arrays = (actual_att, raw_att, realized, requested, wind, nominal, applied, output, beta)
        if (not np.isfinite(mass) or mass <= 0 or not np.isfinite(gravity)
                or not np.all(np.isfinite(dmax)) or dmax.shape != (3,)
                or np.max(np.abs(dmax - 3.0)) > 1e-12
                or any(not np.all(np.isfinite(a)) for a in arrays)):
            raise RuntimeError(f"nonfinite physical/input field or unexpected clipping: {scene}")
        if np.max(np.abs(output - applied)) > 1e-10:
            raise RuntimeError(f"logged event output differs from applied output: {scene}")

        d_att = (actual_att - raw_att) * (requested[0] / mass)[None, :]
        y = (actual_att * (realized[0] / mass)[None, :]
             - np.array([[0.0], [0.0], [gravity]])
             + wind / mass - (nominal - applied))
        target = beta[None, :] * np.clip(y, -dmax[:, None], dmax[:, None])
        residual = output - target
        d_norm = np.linalg.norm(d_att, axis=0)
        if not (np.all(np.isfinite(d_att)) and np.all(np.isfinite(target))
                and np.all(np.isfinite(residual)) and np.all(np.isfinite(d_norm))):
            raise RuntimeError(f"nonfinite diagnostic target/residual: {scene}")

        target_rms = float(np.sqrt(np.mean(target ** 2)))
        residual_rms = float(np.sqrt(np.mean(residual ** 2)))
        audit_rms = np.array([
            target_rms, residual_rms,
            float(row["target_signal_rms_mps2"]),
            float(row["online_before_target_residual_rms_mps2"]),
            *(float(row[f"online_before_residual_{axis}_rms_mps2"]) for axis in ("x", "y", "z")),
        ], dtype=np.float64)
        if not np.all(np.isfinite(audit_rms)):
            raise RuntimeError(f"nonfinite audited/reconstructed RMS: {scene}")
        if (abs(target_rms - float(row["target_signal_rms_mps2"])) > 1e-12
                or abs(residual_rms - float(row["online_before_target_residual_rms_mps2"])) > 1e-12):
            raise RuntimeError(f"reconstructed target/residual differs from audited full72 values: {scene}")
        for axis, axis_i in zip(("x", "y", "z"), range(3)):
            axis_rms = float(np.sqrt(np.mean(residual[axis_i] ** 2)))
            if abs(axis_rms - float(row[f"online_before_residual_{axis}_rms_mps2"])) > 1e-12:
                raise RuntimeError(f"reconstructed {axis} residual differs from audited full72 value: {scene}")

        projectable = d_norm > DATT_EPS_MPS2
        projection = np.full(d_norm.shape, np.nan, dtype=np.float64)
        projection[projectable] = np.sum(residual[:, projectable] * d_att[:, projectable], axis=0) / d_norm[projectable]
        block_rows = []
        for j in range(19):
            source_mask = (valid_times >= j) & (valid_times < j + 1)
            source_n = int(np.sum(source_mask))
            usable = source_mask & projectable
            usable_n = int(np.sum(usable))
            block_rows.append({
                "scene_id": scene, "split": row["split"], "task": row["task"],
                "wind_index": int(row["wind_index"]), "wind_group": row["band"].replace("-", "_"),
                "outcome_vs_b": row["outcome"], "source_block": j,
                "source_phase": "EARLY_0_10S" if j < 10 else "LATE_10_19S",
                "source_time_start_s": j, "target_time_start_s": j + 1,
                "n_valid_inference_events": source_n, "n_projected_events": usable_n,
                "n_excluded_nearzero_datt": source_n - usable_n,
                "projection_mean_mps2": float(np.mean(projection[usable])) if usable_n else None,
                "source_z_rmse_m": block_rmse[j], "target_z_rmse_m": block_rmse[j + 1],
                "delta_z_rmse_m": block_rmse[j + 1] - block_rmse[j],
                "candidate_q_m": float(row["candidate_q_m"]), "B_q_m": float(row["B_q_m"]),
            })

    after_stat = raw_path.stat()
    after_sha = sha256(raw_path)
    if (before_stat.st_size != after_stat.st_size or before_stat.st_mtime_ns != after_stat.st_mtime_ns
            or before_sha != after_sha):
        raise RuntimeError(f"raw changed during read: {scene}")
    return block_rows, {"scene_id": scene, "raw_sha256": before_sha, "raw_size_bytes": before_stat.st_size}


def group_specs(rows: list[dict]) -> list[tuple[str, str, list[dict]]]:
    rows = [r for r in rows if r["projection_mean_mps2"] is not None]
    hf = [r for r in rows if r["wind_group"] == "W09_W14"]
    specs = [("ALL72", "context", rows)]
    for band in ("W00_W08", "W09_W14", "W15"):
        specs.append((f"WIND_{band}", "wind_group", [r for r in rows if r["wind_group"] == band]))
    for task in sorted({r["task"] for r in hf}):
        specs.append((f"HF_TASK_{task}", "task_within_W09_W14", [r for r in hf if r["task"] == task]))
    for phase in ("EARLY_0_10S", "LATE_10_19S"):
        specs.append((f"HF_PHASE_{phase}", "source_phase_within_W09_W14", [r for r in hf if r["source_phase"] == phase]))
    for outcome in ("WIN", "LOSS", "TIE"):
        selected = [r for r in hf if r["outcome_vs_b"] == outcome]
        if selected:
            specs.append((f"HF_OUTCOME_{outcome}", "posthoc_outcome_exploratory_within_W09_W14", selected))
    return specs


def summarize_group(name: str, role: str, rows: list[dict], seed_offset: int) -> dict:
    by_scene: dict[str, list[dict]] = {}
    for row in rows:
        by_scene.setdefault(row["scene_id"], []).append(row)
    clusters = [by_scene[k] for k in sorted(by_scene)]
    point = fixed_effect_fit(clusters) if len(clusters) >= MIN_SCENES_FOR_POINT else None
    result = {
        "group": name, "stratifier": role, "n_scenes": len(clusters), "n_block_pairs": len(rows),
        "n_bootstrap": BOOTSTRAPS, "n_bootstrap_valid": 0,
        "beta_next_rmse_m_per_mps2": None, "beta_ci95_low": None, "beta_ci95_high": None,
        "gamma_current_rmse_m_per_m": None, "gamma_ci95_low": None, "gamma_ci95_high": None,
        "mean_projection_mps2": None, "mean_delta_z_rmse_m": None,
        "estimate_status": "TOO_FEW_SCENES" if len(clusters) < MIN_SCENES_FOR_POINT else "NOT_ESTIMABLE",
        "interpretation_limit": "Conditional association, not causal. B outcome strata are posthoc/exploratory.",
    }
    if rows:
        result["mean_projection_mps2"] = float(np.mean([r["projection_mean_mps2"] for r in rows]))
        result["mean_delta_z_rmse_m"] = float(np.mean([r["delta_z_rmse_m"] for r in rows]))
    if point is None:
        return result
    result["beta_next_rmse_m_per_mps2"], result["gamma_current_rmse_m_per_m"] = point
    if len(clusters) < MIN_SCENES_FOR_CI:
        result["estimate_status"] = "DESCRIPTIVE_POINT_ONLY_LT20_SCENES"
        return result
    rng = np.random.default_rng(SEED + seed_offset)
    boot = []
    for _ in range(BOOTSTRAPS):
        picks = rng.integers(0, len(clusters), size=len(clusters))
        sampled = [clusters[int(i)] for i in picks]  # duplicate draws remain separate FE clusters
        estimate = fixed_effect_fit(sampled)
        if estimate is not None:
            boot.append(estimate)
    result["n_bootstrap_valid"] = len(boot)
    if len(boot) >= int(0.95 * BOOTSTRAPS):
        arr = np.asarray(boot, dtype=np.float64)
        beta_ci = np.quantile(arr[:, 0], [0.025, 0.975])
        gamma_ci = np.quantile(arr[:, 1], [0.025, 0.975])
        result["beta_ci95_low"], result["beta_ci95_high"] = map(float, beta_ci)
        result["gamma_ci95_low"], result["gamma_ci95_high"] = map(float, gamma_ci)
        result["estimate_status"] = "EXPLORATORY_CLUSTER_BOOTSTRAP_95CI"
    else:
        result["estimate_status"] = "INSUFFICIENT_VALID_BOOTSTRAPS"
    return result


def run() -> None:
    started = time.time()
    if FINAL_DIR.exists() or STAGE_DIR.exists():
        raise RuntimeError(f"output exists; refusing to overwrite: {FINAL_DIR} or {STAGE_DIR}")
    input_sha = sha256(INPUT)
    pair_sha = sha256(PAIR_CSV)
    if input_sha.lower() != EXPECTED_MANIFEST_SHA256 or pair_sha.lower() != EXPECTED_PAIR_SHA256:
        raise RuntimeError("pinned mechanism manifest or paired score table SHA mismatch")
    index_by_sha = frozen_raw_index_map()
    manifest = csv_rows(INPUT)
    pair_rows = [r for r in csv_rows(PAIR_CSV) if r.get("method_id") == METHOD_ID]
    pair_by_sha = {r["candidate_raw_sha256"].lower(): r for r in pair_rows}
    if (len(manifest) != 72 or len({r["scene_id"] for r in manifest}) != 72
            or len(pair_rows) != 72 or len(pair_by_sha) != 72
            or len({r["source_scene_id"] for r in pair_rows}) != 72
            or set(pair_by_sha) != set(index_by_sha)):
        raise RuntimeError("manifest, frozen raw indexes, and paired score table do not share exact 72-scene identity")
    if {r["split"] for r in manifest} != {"VAL", "DEV"}:
        raise RuntimeError("manifest contains an unexpected split; TEST is forbidden")
    validated = [(row, validate_manifest_row(row, index_by_sha, pair_by_sha)) for row in manifest]

    pairs, raw_identities = [], []
    for i, (row, raw_path) in enumerate(sorted(validated, key=lambda x: x[0]["scene_id"]), start=1):
        scene_pairs, raw_identity = collect_scene(row, raw_path)
        pairs.extend(scene_pairs)
        raw_identities.append(raw_identity)
        print(f"[{i}/72] {row['scene_id']}: 19 target-block pairs read-only", flush=True)
    if len(pairs) != 72 * 19 or any(r["projection_mean_mps2"] is None for r in pairs):
        missing = [f"{r['scene_id']}:{r['source_block']}" for r in pairs if r["projection_mean_mps2"] is None]
        raise RuntimeError(f"incomplete projectable scene/block panel; no imputation/model fit; missing={missing[:30]}")
    if len({r["raw_sha256"] for r in raw_identities}) != 72:
        raise RuntimeError("raw identities are not unique across 72 scenes")
    if sha256(INPUT).lower() != input_sha or sha256(PAIR_CSV).lower() != pair_sha:
        raise RuntimeError("a pinned text input changed during analysis")
    for path, expected in INDEX_SOURCES:
        if sha256(path).lower() != expected:
            raise RuntimeError(f"frozen raw-index changed during analysis: {path}")

    summary = [summarize_group(name, role, rows, i * 1000)
               for i, (name, role, rows) in enumerate(group_specs(pairs))]
    STAGE_DIR.mkdir()
    pair_path = STAGE_DIR / "datt_nextblock_pairs.csv"
    summary_path = STAGE_DIR / "datt_nextblock_group_summary.csv"
    metadata_path = STAGE_DIR / "datt_nextblock_metadata.json"
    write_csv(pair_path, pairs)
    write_csv(summary_path, summary)
    metadata = {
        "schema": "DATT_NEXTBLOCK_DIAGNOSTIC_V1",
        "analysis_role": "offline observational mechanism diagnostic; no causal claim or experiment",
        "inputs": {"manifest_path": str(INPUT), "manifest_sha256": input_sha,
                   "paired_score_table": str(PAIR_CSV), "paired_score_sha256": pair_sha,
                   "frozen_raw_indexes": {str(p): h for p, h in INDEX_SOURCES},
                   "scenes": 72, "raw_sha_unique": 72,
                   "raw_identity_set_sha256": hashlib.sha256("\n".join(
                       f"{r['scene_id']}:{r['raw_sha256']}" for r in sorted(raw_identities, key=lambda x: x["scene_id"])
                   ).encode()).hexdigest()},
        "time_and_event_rules": {
            "scored_samples": "exact existing full72 grid t=0.000..19.999 s at 1 kHz; t=20 terminal excluded",
            "blocks": "20 half-open blocks [j,j+1), j=0..19; each has exactly 1000 scored samples",
            "source_target_pairs": "source j=0..18 only; target j+1=1..19; no overlap in source-derived predictor and target interval",
            "source_phase": "early j=0..9; late j=10..18; phase is determined by predictor/source block",
            "events": "event flag indices are exactly 10,20,...,19990 (0-based); event times exactly 0.01..19.99 s; only valid inference events enter projections",
        },
        "predictor": {
            "datt": "(R_actual-R_raw)e3*T_req/m, same-event world/inertial coordinates, m/s^2",
            "residual": "logged applied_output - beta*clip(Y,-3,3), same-event world/inertial coordinates, m/s^2",
            "event_projection": "residual dot dAtt / norm(dAtt), m/s^2; equal-weight mean over valid source-block events",
            "near_zero_rule": f"exclude event when norm(dAtt) <= {DATT_EPS_MPS2:.1e} m/s^2; count exclusions; no imputation",
            "reconstruction_check": "per-scene 3D target RMS and online residual RMS/axis RMS must match the audited full72 mechanism table within 1e-12 m/s^2",
        },
        "outcome_and_model": {
            "z_rmse": "sqrt(mean((logged state z - reference z)^2)) on the same 1000 aligned full72 score timestamps per block",
            "main_model": "target_block_z_rmse ~ projection_mean + source_block_z_rmse + scene_FE + source_block_FE",
            "main_coefficient": "projection beta is a conditional predictive association beyond current-block error and common source-block trend; units s^2",
            "estimation": "two-way FE OLS; 2000 percentile bootstrap replicates resampling entire scene clusters; duplicate draws receive distinct scene FE IDs; seed 2026102201",
            "interval_rule": "report CI only for strata with >=20 independent scenes; 5..19 scene point estimates are descriptive only; this threshold does not guarantee generalization",
            "posthoc_outcome_strata": "candidate WIN/LOSS/TIE vs B uses full-horizon outcome and is exploratory only; outcome strata are produced within W09-W14",
            "group_scope": "overall and wind groups; task, source-phase and posthoc outcome strata within W09-W14 only",
        },
        "outputs": [str(FINAL_DIR / "datt_nextblock_pairs.csv"), str(FINAL_DIR / "datt_nextblock_group_summary.csv"), str(FINAL_DIR / "datt_nextblock_metadata.json")],
        "script_sha256": sha256(Path(__file__)),
        "elapsed_seconds": time.time() - started,
        "all_72_raw_sha_before_after_matched": True,
    }
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    STAGE_DIR.rename(FINAL_DIR)
    print(json.dumps({"summary": summary, "metadata": metadata}, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test-only", action="store_true")
    args = parser.parse_args()
    self_check()
    if args.self_test_only:
        print("SELF_CHECK=PASS")
    else:
        run()
