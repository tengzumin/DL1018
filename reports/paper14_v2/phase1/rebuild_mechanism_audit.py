#!/usr/bin/env python3
"""Read-only, whitelist-bounded reconstruction of corrected DSSM14 full72 labels.

Run with PowerShell 7 from DL1018:
  python -B reports/paper14_v2/phase1/rebuild_mechanism_audit.py
Reads only the two named corrected-pair RAW_INDEX files, the 72 raw files they
whitelist, and the local per-scene result table. Writes only into this script's
phase1 directory. It does not inspect TEST indexes or launch simulations.
"""
from __future__ import annotations
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import time

import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
BASE = ROOT.parent / "REFERENCE_FIX_FULL72_20261021_022342_313"
EVALS = [
    BASE / "corrected_reference_training_v1" / "corrected_pair_eval_v1" / "reports" / "RAW_INDEX.csv",
    BASE / "corrected_reference_training_v1" / "corrected_pair_eval_tail21_v1" / "reports" / "RAW_INDEX.csv",
]
SCORE_CSV = OUT / "mechanism_by_scene.csv"
PAIR_CSV = ROOT / "reports" / "corrected14_full72_benchmark_20261021" / "PAIR14_SCENE_RESULTS_VS_B.csv"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def csv_rows(path: Path):
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict]):
    if not rows:
        raise RuntimeError(f"refusing to write empty table: {path}")
    cols = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="raise")
        w.writeheader()
        w.writerows(rows)


def rot_zyx_third_col(euler: np.ndarray) -> np.ndarray:
    """R_ZYX(roll,pitch,yaw) @ [0,0,1], shape (3,N), all radians."""
    roll, pitch, yaw = euler
    cp, sp = np.cos(roll), np.sin(roll)
    ct, st = np.cos(pitch), np.sin(pitch)
    cy, sy = np.cos(yaw), np.sin(yaw)
    return np.vstack((cy * st * cp + sy * sp,
                      sy * st * cp - cy * sp,
                      ct * cp))


def rms(a: np.ndarray) -> float:
    a = np.asarray(a, dtype=np.float64)
    return float(np.sqrt(np.mean(np.square(a)))) if a.size else math.nan


def safe_float(x):
    return float(x) if np.isfinite(x) else None


def summarize_component(rows: list[dict], name: str) -> dict:
    ev = np.concatenate([r["component_arrays"][name].reshape(-1) for r in rows])
    per_scene = [r["component_rms"][name] for r in rows]
    return {
        f"{name}_rms_pooled_mps2": rms(ev),
        f"{name}_rms_scene_macro_mps2": float(np.mean(per_scene)),
    }


def file_stat(path: Path):
    st = path.stat()
    return {"size_bytes": st.st_size, "mtime_ns": st.st_mtime_ns}


def h5_text(f, name: str) -> str:
    return "".join(chr(int(v)) for v in np.asarray(f[name]).reshape(-1) if int(v))


def h5_scalar(f, name: str) -> float:
    return float(np.asarray(f[name]).item())


# Build the exact 72-row whitelist from the named VAL/DEV corrected-pair indexes.
score_rows = csv_rows(SCORE_CSV)
score_by_scene = {r["scene_id"]: r for r in score_rows}
if len(score_by_scene) != 72:
    raise RuntimeError(f"expected 72 existing score rows, got {len(score_by_scene)}")
index_rows = []
index_hashes = {}
index_selected_counts = {}
index_selected_alias_counts = {}
for index_path in EVALS:
    index_sha = sha256(index_path)
    index_hashes[str(index_path)] = index_sha
    selected_from_file = []
    for row in csv_rows(index_path):
        if (row.get("method_id") == "CORRECTED_TRAIN_DSSM14_G12_R32"
                and row.get("action") == "RUN"
                and row.get("status") == "RUN_COMPLETE_STABLE"
                and row.get("complete", "").lower() == "true"
                and row.get("finite", "").lower() == "true"):
            row["_raw_index_file"] = str(index_path)
            row["_raw_index_sha256"] = index_sha
            index_rows.append(row)
            selected_from_file.append(row)
    index_selected_counts[str(index_path)] = len(selected_from_file)
    index_selected_alias_counts[str(index_path)] = sum(
        r["runtime_scene_id"].endswith("_ACC_FIX_V1") for r in selected_from_file
    )
index_by_sha = {}
for row in index_rows:
    sha = row["raw_sha256"].lower()
    if sha in index_by_sha:
        raise RuntimeError(f"duplicate raw SHA in the two named indexes: {sha}")
    index_by_sha[sha] = row
by_scene = {}
alias_count = 0
for scene, score in score_by_scene.items():
    sha = score["raw_sha256"].lower()
    if sha not in index_by_sha:
        raise RuntimeError(f"score raw SHA absent from the two named indexes: {scene} {sha}")
    row = index_by_sha[sha]
    index_scene = row["runtime_scene_id"]
    if index_scene != scene:
        if index_scene != scene + "_ACC_FIX_V1":
            raise RuntimeError(f"unapproved scene alias for matching raw SHA: {scene} -> {index_scene}")
        alias_count += 1
    if row["split"] != score["split"] or row["task"] != score["task"] or int(row["wind_index"]) != int(score["wind_index"]):
        raise RuntimeError(f"split/task/wind mismatch for raw SHA: {scene} -> {index_scene}")
    if not (scene.startswith("DL1018_VAL_") or scene.startswith("DL1018_DEV_")):
        raise RuntimeError(f"unexpected split/path outside VAL/DEV whitelist: {scene}")
    by_scene[scene] = row
if len(by_scene) != 72:
    raise RuntimeError(f"expected corrected 72 raw files, got {len(by_scene)}")

# Bind the pairwise summary using the exact frozen raw SHA set. The file also
# contains KAN rows, so the DSSM method filter is explicit; source IDs are only
# checked as metadata after the SHA-keyed join.
pair_file_sha = sha256(PAIR_CSV)
pair_all_rows = csv_rows(PAIR_CSV)
pair_dssm_rows = [r for r in pair_all_rows if r.get("method_id") == "CORRECTED_TRAIN_DSSM14_G12_R32"]
pair_by_raw_sha = {}
for r in pair_dssm_rows:
    pair_sha = r["candidate_raw_sha256"].lower()
    if pair_sha in pair_by_raw_sha:
        raise RuntimeError(f"duplicate DSSM candidate raw SHA in pair summary: {pair_sha}")
    pair_by_raw_sha[pair_sha] = r
expected_raw_shas = {r["raw_sha256"].lower() for r in score_rows}
if len(expected_raw_shas) != 72 or set(pair_by_raw_sha) != expected_raw_shas:
    missing = sorted(expected_raw_shas - set(pair_by_raw_sha))
    extra = sorted(set(pair_by_raw_sha) - expected_raw_shas)
    raise RuntimeError(f"pair summary DSSM raw SHA set differs from frozen 72: missing={missing}, extra={extra}")
if len(pair_dssm_rows) != 72 or len(pair_all_rows) != 144:
    raise RuntimeError(f"unexpected pair summary row counts: all={len(pair_all_rows)} DSSM={len(pair_dssm_rows)}")
lineage_rows = []
for scene, score in score_by_scene.items():
    raw_sha = score["raw_sha256"].lower()
    index_row = by_scene[scene]
    pair_row = pair_by_raw_sha[raw_sha]
    if pair_row["split"] != score["split"] or pair_row["task"] != score["task"]:
        raise RuntimeError(f"pair summary split/task mismatch at frozen raw SHA: {scene} {raw_sha}")
    candidate_q = float(pair_row["candidate_Q_0_20_m"])
    b_q = float(pair_row["B_Q_0_20_m"])
    if (abs(candidate_q - float(score["candidate_q_m"])) > 1e-12
            or abs(b_q - float(score["B_q_m"])) > 1e-12):
        raise RuntimeError(f"pair summary Q mismatch at frozen raw SHA: {scene} {raw_sha}")
    expected_outcome = "WIN" if candidate_q < b_q - 1e-12 else "LOSS" if candidate_q > b_q + 1e-12 else "TIE"
    if expected_outcome != score["win"] or pair_row["result_vs_B"] != expected_outcome:
        raise RuntimeError(f"pair summary outcome mismatch at frozen raw SHA: {scene} {raw_sha}")
    lineage_rows.append({
        "scene_id": scene, "raw_sha256": raw_sha, "split": score["split"], "task": score["task"],
        "wind_index": score["wind_index"], "raw_index_source_file": index_row["_raw_index_file"],
        "raw_index_sha256": index_row["_raw_index_sha256"], "raw_index_runtime_scene_id": index_row["runtime_scene_id"],
        "raw_index_id_match": "ALIAS_ACC_FIX_V1" if index_row["runtime_scene_id"] != scene else "EXACT",
        "pair_summary_file": str(PAIR_CSV), "pair_summary_sha256": pair_file_sha,
        "pair_method_id": pair_row["method_id"], "pair_model_id": pair_row["model_id"],
        "pair_candidate_raw_sha256": pair_row["candidate_raw_sha256"].lower(),
        "pair_candidate_q_m": candidate_q, "pair_B_q_m": b_q, "pair_result_vs_B": expected_outcome,
    })
if sum(index_selected_counts.values()) != 72:
    raise RuntimeError(f"raw-index shard union selected count is not 72: {index_selected_counts}")
if list(index_selected_counts.values()) != [61, 11] or list(index_selected_alias_counts.values()) != [21, 3]:
    raise RuntimeError(f"unexpected raw-index shard/alias distribution: rows={index_selected_counts}, aliases={index_selected_alias_counts}")

scene_out = []
run_start_rows = []
canonical_model_hashes = set()
normalizer_hashes = set()
runtime_configs = set()
for ordinal, scene in enumerate(sorted(by_scene), 1):
    row = by_scene[scene]
    score = score_by_scene[scene]
    run_status_path = (ROOT.parent / Path(*row["run_status_path"].split("\\"))).resolve()
    run_start_path = run_status_path.with_name("run_start.mat")
    if not run_start_path.is_file() or not run_start_path.is_relative_to(BASE.resolve()):
        raise FileNotFoundError(f"index-whitelisted run_start missing/outside eval root: {scene} {run_start_path}")
    run_start_stat_before = file_stat(run_start_path)
    run_start_sha_before = sha256(run_start_path)
    with h5py.File(run_start_path, "r") as start:
        run_start_record = {
            "scene_id": scene,
            "raw_sha256": row["raw_sha256"].lower(),
            "split": row["split"], "task": row["task"], "wind_index": row["wind_index"],
            "raw_index_runtime_scene_id": row["runtime_scene_id"],
            "run_start_path": str(run_start_path),
            "run_start_size_bytes": run_start_stat_before["size_bytes"],
            "run_start_mtime_ns_before": run_start_stat_before["mtime_ns"],
            "run_start_sha256_before": run_start_sha_before,
            "run_start_source_scene_id": h5_text(start, "meta/source_scene_id"),
            "run_start_runtime_scene_id": h5_text(start, "meta/runtime_scene_id"),
            "run_start_model_id": h5_text(start, "meta/model_id"),
            "run_start_model_sha256": h5_text(start, "meta/model_sha256"),
            "run_start_method_id": h5_text(start, "meta/method_id"),
            "run_start_architecture": h5_text(start, "opts/stage1_position_runtime/model/architecture"),
            "run_start_seed": int(h5_scalar(start, "opts/stage1_position_runtime/model/seed")),
            "run_start_selected_step": int(h5_scalar(start, "opts/stage1_position_runtime/model/selected_step")),
            "run_start_input_dim": int(h5_scalar(start, "opts/stage1_position_runtime/model/input_dim")),
            "run_start_window": int(h5_scalar(start, "opts/stage1_position_runtime/model/window")),
            "run_start_context_length": int(h5_scalar(start, "opts/stage1_position_runtime/model/context_length")),
            "run_start_head_type": h5_text(start, "opts/stage1_position_runtime/position_only_search_head/head_type"),
            "run_start_head_enabled": int(h5_scalar(start, "opts/stage1_position_runtime/position_only_search_head/enabled")),
            "run_start_update_enabled": int(h5_scalar(start, "opts/stage1_position_runtime/update_enabled")),
            "run_start_gamma": h5_scalar(start, "opts/stage1_position_runtime/position_only_search_head/gamma"),
            "run_start_kappa": h5_scalar(start, "opts/stage1_position_runtime/position_only_search_head/kappa"),
            "run_start_beta_scale": h5_scalar(start, "opts/stage1_position_runtime/beta_scale"),
            "run_start_pcf_enabled": int(h5_scalar(start, "opts/stage1_position_runtime/command_filter_coordination_v3_5/enabled")),
            "run_start_position_sample_time_s": h5_scalar(start, "cfg/control/learned/position_sample_time"),
            "run_start_position_update_hz": h5_scalar(start, "cfg/rbf/runtime/position_update_hz"),
            "run_start_plant_dt_s": h5_scalar(start, "cfg/plant/dt"),
            "run_start_update_dt_scale": h5_scalar(start, "opts/stage1_position_runtime/update_dt_scale"),
        }
    run_start_stat_after = file_stat(run_start_path)
    run_start_sha_after = sha256(run_start_path)
    run_start_record["run_start_size_bytes_after"] = run_start_stat_after["size_bytes"]
    run_start_record["run_start_mtime_ns_after"] = run_start_stat_after["mtime_ns"]
    run_start_record["run_start_sha256_after"] = run_start_sha_after
    if run_start_stat_before != run_start_stat_after or run_start_sha_before != run_start_sha_after:
        raise RuntimeError(f"run_start changed during read: {scene} {run_start_path}")
    if (run_start_record["run_start_source_scene_id"] != row["source_scene_id"]
            or run_start_record["run_start_runtime_scene_id"] != row["runtime_scene_id"]
            or run_start_record["run_start_model_sha256"].lower() != row["model_sha256"].lower()
            or run_start_record["run_start_model_id"] != row["model_id"]
            or run_start_record["run_start_gamma"] != 12.0
            or run_start_record["run_start_kappa"] != 1.0
            or run_start_record["run_start_head_type"] != "FEATURE"
            or run_start_record["run_start_head_enabled"] != 1
            or run_start_record["run_start_update_enabled"] != 1
            or run_start_record["run_start_pcf_enabled"] != 1
            or run_start_record["run_start_position_sample_time_s"] != 0.01
            or run_start_record["run_start_position_update_hz"] != 100.0
            or run_start_record["run_start_plant_dt_s"] != 0.001):
        raise RuntimeError(f"run_start identity/config mismatch: {scene} {run_start_record}")
    run_start_rows.append(run_start_record)
    raw_path = (ROOT.parent / Path(*row["raw_path"].split("\\"))).resolve()
    # Path whitelist is the exact index entry; no directory search/glob is used.
    if not raw_path.is_file():
        raise FileNotFoundError(raw_path)
    before_stat = file_stat(raw_path)
    before_sha = sha256(raw_path)
    if before_sha.lower() != row["raw_sha256"].lower():
        raise RuntimeError(f"raw SHA mismatch before read: {scene}")

    with h5py.File(raw_path, "r") as f:
        def get(name):
            return np.asarray(f[name], dtype=np.float64)
        event_flag = get("log/position_event_flag").reshape(-1) > 0
        if not np.array_equal(event_flag, get("log/stage1_position_event").reshape(-1) > 0):
            raise RuntimeError(f"position/stage1 event flags differ: {scene}")
        idx = np.flatnonzero(event_flag)  # HDF5 0-based offset; MATLAB transition k=idx+1.
        k_matlab = idx + 1
        times = get("log/transition_time").reshape(-1)[idx]
        if len(idx) != 1999 or len(times) != 1999:
            raise RuntimeError(f"expected 1999 scheduled events: {scene} got {len(idx)}")
        if np.max(np.abs(np.diff(times) - 0.01)) > 1e-12:
            raise RuntimeError(f"scheduled position events are not 100 Hz: {scene}")

        # State/reference/action at the exact 1 kHz transition column k.
        state = get("log/state")[:, idx]
        ref_pos = get("log/reference/position")[:, idx]
        ref_vel = get("log/reference/velocity")[:, idx]
        ref_acc = get("log/reference/acceleration")[:, idx]
        dt_plant = float(get("cfg/plant/dt").item())
        transition_times_full = get("log/transition_time").reshape(-1)
        # The benchmark Q uses the 20,000 timestamped samples t=0,...,19.999 s;
        # the MAT also retains one unscored terminal t=20.000 s state column.
        position_error_full = get("log/state")[0:3, :-1] - get("log/reference/position")[:, :-1]
        state_times_full = transition_times_full
        if position_error_full.shape[1] != 20000 or len(state_times_full) != 20000:
            raise RuntimeError(f"unexpected full position state/time history: {scene}")
        if np.max(np.abs(np.diff(state_times_full) - dt_plant)) > 1e-12:
            raise RuntimeError(f"position state time axis is not the 1 kHz plant grid: {scene}")
        phase_mask = {
            "0_5": (state_times_full >= 0.0) & (state_times_full < 5.0),
            "5_20": (state_times_full >= 5.0) & (state_times_full < 20.0),
        }
        position_rmse_phase = {
            phase: np.sqrt(np.mean(position_error_full[:, mask] ** 2, axis=1))
            for phase, mask in phase_mask.items()
        }
        position_samples_phase = {phase: int(np.sum(mask)) for phase, mask in phase_mask.items()}
        position_q_replay = float(np.sqrt(np.mean(np.sum(position_error_full ** 2, axis=0))))
        position_q_replay_error = abs(position_q_replay - float(score["candidate_q_m"]))
        if position_q_replay_error > 1e-12:
            raise RuntimeError(f"raw position Q replay differs from benchmark score: {scene} {position_q_replay_error}")
        k1 = get("cfg/control/bs/position/k1").reshape(-1)
        k2 = get("cfg/control/bs/position/k2").reshape(-1)
        error = ref_pos - state[0:3]
        rate_error = ref_vel - state[3:6]
        surface = rate_error + k1[:, None] * error
        nominal = ref_acc + k1[:, None] * rate_error + error + k2[:, None] * surface
        nominal_logged = get("log/position_nominal_acceleration_mps2")[:, idx]
        applied = get("log/stage1_position_applied_acceleration_mps2")[:, idx]
        applied_alias = get("log/position_compensation_applied_acceleration_mps2")[:, idx]
        realized = get("log/realized_generalized")[:, idx]
        requested = get("log/controller_clipped_generalized")[:, idx]
        wind = get("log/wind_force_I")[:, idx]
        raw_attitude = get("log/raw_outer_attitude")[:, idx]
        rho = get("scene/arms/rho_true")[:, idx]
        rho_dot = get("scene/arms/rhoDot_true")[:, idx]
        mass = float(get("cfg/plant/mass").item())
        gravity = float(get("cfg/plant/g").item())
        if not (np.isfinite(mass) and mass > 0 and np.isfinite(gravity)):
            raise RuntimeError(f"invalid physical constants: {scene}")
        if not (np.all(np.isfinite(rho)) and np.all(np.isfinite(rho_dot))):
            raise RuntimeError(f"rho_true/rhoDot_true nonfinite: {scene}")

        # Verify the identity/config actually embedded in each corrected-pair raw.
        model_prefix = "opts/stage1_position_runtime/model/"
        model_id = "".join(chr(int(c)) for c in get(model_prefix + "model_id").reshape(-1) if c)
        architecture = "".join(chr(int(c)) for c in get(model_prefix + "architecture").reshape(-1) if c)
        seed = int(get(model_prefix + "seed").item())
        selected_step = int(get(model_prefix + "selected_step").item())
        input_dim = int(get(model_prefix + "input_dim").item())
        model_window = int(get(model_prefix + "window").item())
        context_length = int(get(model_prefix + "context_length").item())
        gamma = float(get("log/stage1_position_search_gamma").item())
        kappa = float(get("log/stage1_position_search_kappa").item())
        head_type = "".join(chr(int(c)) for c in get("log/stage1_position_search_head_type").reshape(-1) if c)
        beta_scale = float(get("log/stage1_position_beta_scale").item())
        head_enabled = int(get("log/stage1_position_search_head_enabled").item())
        update_enabled = int(get("log/stage1_position_update_enabled").item())
        pcf_enabled = int(get("log/stage1_position_pcf_coordination_enabled").item())
        if (model_id, architecture, seed, selected_step, input_dim, model_window, context_length) != (
                "DSSM14", "DSSM", 2026102001, 60000, 14, 32, 32):
            raise RuntimeError(f"corrected model identity mismatch: {scene}: {(model_id, architecture, seed, selected_step, input_dim, model_window, context_length)}")
        if (head_type, gamma, kappa, beta_scale, head_enabled, update_enabled, pcf_enabled) != (
                "FEATURE", 12.0, 1.0, 1.0, 1, 1, 1):
            raise RuntimeError(f"corrected runtime config mismatch: {scene}: {(head_type, gamma, kappa, beta_scale, head_enabled, update_enabled, pcf_enabled)}")
        output_w = get(model_prefix + "output_W")
        W0_logged = get("log/stage1_position_search_initial_weight")
        W0_error = float(np.max(np.abs(W0_logged - kappa * output_w)))
        if W0_error > 1e-6:
            raise RuntimeError(f"kappa*W0/output_W identity mismatch: {scene}: {W0_error}")
        model_fields = ["input_W", "input_b", "input_mu", "input_sigma", "output_W", "project_W", "project_b", "ssm_tau"]
        mh = hashlib.sha256()
        for field in model_fields:
            arr = np.ascontiguousarray(get(model_prefix + field))
            mh.update(field.encode("ascii") + b"\0")
            mh.update(repr((arr.shape, str(arr.dtype))).encode("ascii") + b"\0")
            mh.update(arr.tobytes(order="C"))
        model_arrays_identity = mh.hexdigest()
        nh = hashlib.sha256()
        for field in ("input_mu", "input_sigma"):
            arr = np.ascontiguousarray(get(model_prefix + field))
            nh.update(field.encode("ascii") + b"\0")
            nh.update(repr((arr.shape, str(arr.dtype))).encode("ascii") + b"\0")
            nh.update(arr.tobytes(order="C"))
        normalizer_identity = nh.hexdigest()
        canonical_model_hashes.add(model_arrays_identity)
        normalizer_hashes.add(normalizer_identity)
        runtime_configs.add((model_id, architecture, seed, selected_step, input_dim,
                             model_window, context_length, head_type, gamma, kappa,
                             beta_scale, head_enabled, update_enabled, pcf_enabled))

        z_actual = rot_zyx_third_col(state[6:9])
        z_raw = rot_zyx_third_col(raw_attitude)
        d_wind = wind / mass
        d_alloc = z_actual * ((realized[0] - requested[0]) / mass)[None, :]
        d_att = (z_actual - z_raw) * (requested[0] / mass)[None, :]
        gravity_vec = np.array([[0.0], [0.0], [gravity]])
        d_map = z_raw * (requested[0] / mass)[None, :] - gravity_vec - (nominal - applied)
        y_direct = z_actual * (realized[0] / mass)[None, :] - gravity_vec + wind / mass - (nominal - applied)
        component_stack = np.stack([d_wind, d_alloc, d_att, d_map], axis=0)
        closure = y_direct - np.sum(component_stack, axis=0)
        y_clip = np.clip(y_direct, -3.0, 3.0)

        valid = get("log/stage1_position_event_inference_valid").reshape(-1)[idx] > 0
        valid_idx = idx[valid]
        valid_times = times[valid]
        valid_k = k_matlab[valid]
        if int(np.sum(valid)) != 1968:
            raise RuntimeError(f"expected 1968 online inference events: {scene} got {int(np.sum(valid))}")
        step_index = get("log/stage1_position_event_step_index").reshape(-1)
        if not np.array_equal(step_index.astype(np.int64), valid_k.astype(np.int64)):
            raise RuntimeError(f"step_index does not map to valid 1 kHz transition k: {scene}")
        beta = get("log/stage1_position_event_beta").reshape(-1)[valid_idx]
        beta_calc = np.clip(valid_times / 1.8, 0.0, 1.0)
        beta_error = float(np.max(np.abs(beta - beta_calc)))
        if beta_error > 1e-12:
            raise RuntimeError(f"logged beta ramp mismatch: {scene} error={beta_error}")

        # Replay PCF's 1 kHz held-input eta state and its 100 Hz sample at the
        # controller event. The raw logs contain the exact request/residual,
        # pre/post eta, and event surface used by the runtime.
        eta_before_1khz = get("log/stage1_position_pcf_eta_before_mps")
        eta_after_1khz = get("log/stage1_position_pcf_eta_after_mps")
        a_req_1khz = get("log/stage1_position_pcf_a_req_mps2")
        a_f_1khz = get("log/stage1_position_pcf_a_f_mps2")
        r_f_1khz = get("log/stage1_position_pcf_r_f_mps2")
        k2_filter = get("cfg/control/bs/position/k2").reshape(-1)
        if eta_before_1khz.shape != (3, 20000) or eta_after_1khz.shape != (3, 20000):
            raise RuntimeError(f"unexpected PCF eta history shape: {scene}")
        pcf_residual_error = float(np.max(np.abs(r_f_1khz - (a_req_1khz - a_f_1khz))))
        pcf_eta_continuity_error = float(np.max(np.abs(eta_before_1khz[:, 1:] - eta_after_1khz[:, :-1])))
        decay = np.exp(-k2_filter[:, None] * dt_plant)
        integral = np.full((3, 1), dt_plant, dtype=np.float64)
        positive_k2 = k2_filter > 0
        integral[positive_k2, 0] = -np.expm1(-k2_filter[positive_k2] * dt_plant) / k2_filter[positive_k2]
        eta_after_replay = decay * eta_before_1khz + integral * r_f_1khz
        pcf_eta_replay_error = float(np.max(np.abs(eta_after_replay - eta_after_1khz)))
        event_eta = get("log/stage1_position_pcf_event_eta_before_mps")[:, valid_idx]
        event_surface = get("log/stage1_position_pcf_event_s_original_mps")[:, valid_idx]
        event_coord = get("log/stage1_position_pcf_event_s_coord_mps")[:, valid_idx]
        event_coord_eff = get("log/stage1_position_pcf_event_s_coord_eff_mps")[:, valid_idx]
        event_eta_alignment_error = float(np.max(np.abs(event_eta - eta_before_1khz[:, valid_idx])))
        event_coord_error = float(np.max(np.abs(event_coord - (event_surface - event_eta))))
        event_coord_eff_expected = np.maximum(np.minimum(event_coord, np.array([[7.0], [8.0], [10.0]])),
                                              -np.array([[7.0], [8.0], [10.0]]))
        event_coord_eff_error = float(np.max(np.abs(event_coord_eff - event_coord_eff_expected)))
        if max(pcf_residual_error, pcf_eta_continuity_error, pcf_eta_replay_error,
               event_eta_alignment_error, event_coord_error, event_coord_eff_error) > 1e-9:
            raise RuntimeError(f"PCF 1kHz/event replay mismatch: {scene}")

        # Same state, same phi, same beta/clip, three output states.
        phi = get("log/stage1_position_event_phi_33")[:, valid_idx]
        W0 = get("log/stage1_position_search_initial_weight")
        W0 = np.asarray(W0, dtype=np.float64).reshape(3, 33)
        kappa = float(get("log/stage1_position_search_kappa").item())
        if not np.isclose(kappa, 1.0):
            raise RuntimeError(f"unexpected current full72 kappa={kappa}: {scene}")
        W0 = kappa * W0
        w_before = get("log/stage1_position_event_weight_before_33x3")
        w_after = get("log/stage1_position_event_weight_after_33x3")
        if w_before.shape != (1968, 3, 33) or w_after.shape != (1968, 3, 33):
            raise RuntimeError(f"unexpected logged online weight shape: {scene} {w_before.shape}/{w_after.shape}")
        event_dt = get("log/stage1_position_event_dt_s").reshape(-1)[valid_idx]
        if np.any(event_dt <= 0) or not np.all(np.isfinite(event_dt)):
            raise RuntimeError(f"invalid logged search-head event dt: {scene}")
        update_outer = np.einsum("ei,ej->eij", event_coord_eff.T, phi.T)
        w_unprojected_replay = w_before + event_dt[:, None, None] * (
            -gamma * beta[:, None, None] * update_outer - 0.002 * w_before
        )
        w_after_replay = np.clip(w_unprojected_replay, -60.0, 60.0)
        search_weight_update_error = float(np.max(np.abs(w_after_replay - w_after)))
        projection_expected = np.any(np.abs(w_unprojected_replay) > 60.0, axis=(1, 2))
        projection_logged = get("log/stage1_position_event_projection").reshape(-1)[valid_idx] > 0
        search_projection_mismatch_count = int(np.sum(projection_expected != projection_logged))
        if search_weight_update_error > 1e-9 or search_projection_mismatch_count != 0:
            raise RuntimeError(f"search-head discrete update replay mismatch: {scene} {search_weight_update_error}")
        weight_delta_norm_by_axis = np.linalg.norm(w_after - w_before, axis=2)
        weight_delta_rms_by_phase = {}
        valid_phase_mask = {
            "0_5": (valid_times >= 0.0) & (valid_times < 5.0),
            "5_20": (valid_times >= 5.0) & (valid_times < 20.0),
        }
        for phase, mask in valid_phase_mask.items():
            weight_delta_rms_by_phase[phase] = np.sqrt(np.mean(weight_delta_norm_by_axis[mask, :] ** 2, axis=0))
        eta_rms_by_axis = np.sqrt(np.mean(eta_before_1khz ** 2, axis=1))
        seff_rms_by_axis = np.sqrt(np.mean(event_coord_eff ** 2, axis=1))
        weight_delta_rms_by_axis = np.sqrt(np.mean(weight_delta_norm_by_axis ** 2, axis=0))
        raw0 = W0 @ phi
        raw_before = np.einsum("eij,je->ei", w_before, phi)
        raw_after = np.einsum("eij,je->ei", w_after, phi)
        dmax = get("cfg/rbf/position/dmax").reshape(-1)
        target = beta[None, :] * np.clip(y_direct[:, valid], -dmax[:, None], dmax[:, None])
        prior = beta[None, :] * np.clip(raw0, -dmax[:, None], dmax[:, None])
        before = beta[None, :] * np.clip(raw_before.T, -dmax[:, None], dmax[:, None])
        after_same_state = beta[None, :] * np.clip(raw_after.T, -dmax[:, None], dmax[:, None])
        same_state_axis_rms = {
            "target_signal_rms_xyz_mps2": np.sqrt(np.mean(target ** 2, axis=1)),
            "prior_target_residual_rms_xyz_mps2": np.sqrt(np.mean((prior - target) ** 2, axis=1)),
            "online_before_target_residual_rms_xyz_mps2": np.sqrt(np.mean((before - target) ** 2, axis=1)),
            "online_after_same_state_target_residual_rms_xyz_mps2": np.sqrt(np.mean((after_same_state - target) ** 2, axis=1)),
        }
        same_state_axis_rms["online_before_vs_after_residual_improvement_xyz_mps2"] = (
            same_state_axis_rms["online_before_target_residual_rms_xyz_mps2"]
            - same_state_axis_rms["online_after_same_state_target_residual_rms_xyz_mps2"]
        )
        same_state_series = {
            "target_signal": target,
            "W0_prior_residual": prior - target,
            "online_before_residual": before - target,
            "online_after_same_state_residual": after_same_state - target,
        }
        for phase, mask in valid_phase_mask.items():
            for metric, values in same_state_series.items():
                same_state_axis_rms[f"{metric}_rms_{phase}_xyz_mps2"] = np.sqrt(np.mean(values[:, mask] ** 2, axis=1))
            same_state_axis_rms[f"online_update_residual_gain_rms_{phase}_xyz_mps2"] = (
                same_state_axis_rms[f"online_before_residual_rms_{phase}_xyz_mps2"]
                - same_state_axis_rms[f"online_after_same_state_residual_rms_{phase}_xyz_mps2"]
            )
        applied_event = get("log/stage1_position_event_applied_acceleration_mps2")[:, valid_idx]
        applied_valid = applied[:, valid]
        output_applied_error = float(np.max(np.abs(before - applied_event)))
        stage1_applied_error = float(np.max(np.abs(applied_event - applied_valid)))
        if max(output_applied_error, stage1_applied_error) > 1e-10:
            raise RuntimeError(f"logged output/application replay mismatch: {scene}")

    after_stat = file_stat(raw_path)
    after_sha = sha256(raw_path)
    if before_stat != after_stat or before_sha != after_sha:
        raise RuntimeError(f"raw changed during read: {scene}")

    comps = {"d_wind": d_wind, "d_alloc": d_alloc, "d_att": d_att, "d_map": d_map}
    comp_rms = {name: rms(val) for name, val in comps.items()}
    score = score_by_scene[scene]
    scene_out.append({
        "scene_id": scene, "raw_index_scene_id": row["runtime_scene_id"],
        "raw_index_source_file": row["_raw_index_file"], "raw_index_sha256": row["_raw_index_sha256"],
        "raw_index_id_match": "ALIAS_ACC_FIX_V1" if row["runtime_scene_id"] != scene else "EXACT",
        "split": row["split"], "task": row["task"], "wind_index": int(row["wind_index"]),
        "band": "W00-W08" if int(row["wind_index"]) <= 8 else "W09-W14" if int(row["wind_index"]) <= 14 else "W15",
        "score": score,
        "raw_path": str(raw_path), "raw_sha256_before": before_sha,
        "raw_size_bytes_before": before_stat["size_bytes"], "raw_mtime_ns_before": before_stat["mtime_ns"],
        "raw_sha256_after": after_sha,
        "raw_size_bytes_after": after_stat["size_bytes"], "raw_mtime_ns_after": after_stat["mtime_ns"],
        "event_count_scheduled": int(len(idx)), "event_count_online_valid": int(np.sum(valid)),
        "transition_k_first": int(k_matlab[0]), "transition_k_last": int(k_matlab[-1]),
        "event_time_first_s": float(times[0]), "event_time_last_s": float(times[-1]),
        "mass_kg": mass, "gravity_mps2": gravity,
        "model_id": model_id, "architecture": architecture, "seed": seed,
        "selected_step": selected_step, "input_dim": input_dim,
        "window": model_window, "context_length": context_length,
        "head_type": head_type, "gamma": gamma, "kappa": kappa,
        "beta_scale": beta_scale, "pcf_enabled": pcf_enabled,
        "W0_kappa_output_W_max_abs": W0_error,
        "model_arrays_identity_sha256": model_arrays_identity,
        "normalizer_identity_sha256": normalizer_identity,
        "nominal_replay_max_abs_mps2": float(np.max(np.abs(nominal - nominal_logged))),
        "applied_alias_max_abs_mps2": float(np.max(np.abs(applied - applied_alias))),
        "beta_ramp_max_abs": beta_error,
        "output_applied_max_abs_mps2": output_applied_error,
        "event_applied_max_abs_mps2": stage1_applied_error,
        "pcf_r_f_vs_a_req_minus_a_f_max_abs_mps2": pcf_residual_error,
        "pcf_eta_1khz_continuity_max_abs_m": pcf_eta_continuity_error,
        "pcf_eta_1khz_replay_max_abs_m": pcf_eta_replay_error,
        "pcf_event_eta_sample_alignment_max_abs_m": event_eta_alignment_error,
        "pcf_event_coord_relation_max_abs_mps": event_coord_error,
        "pcf_event_coord_eff_clip_max_abs_mps": event_coord_eff_error,
        "search_weight_update_replay_max_abs": search_weight_update_error,
        "search_projection_mismatch_count": search_projection_mismatch_count,
        "search_event_dt_min_s": float(np.min(event_dt)),
        "search_event_dt_max_s": float(np.max(event_dt)),
        "target_signal_rms_mps2": rms(target),
        **same_state_axis_rms,
        "online_event_count_0_5": int(np.sum(valid_phase_mask["0_5"])),
        "online_event_count_5_20": int(np.sum(valid_phase_mask["5_20"])),
        "position_rmse_0_5_xyz_m": position_rmse_phase["0_5"],
        "position_rmse_5_20_xyz_m": position_rmse_phase["5_20"],
        "position_samples_0_5": position_samples_phase["0_5"],
        "position_samples_5_20": position_samples_phase["5_20"],
        "position_q_replay_max_abs_m": position_q_replay_error,
        "position_error_full_xyz_m": position_error_full,
        "position_phase_mask_0_5": phase_mask["0_5"],
        "position_phase_mask_5_20": phase_mask["5_20"],
        "pcf_eta_before_xyz_mps": eta_before_1khz,
        "pcf_event_s_eff_xyz_mps": event_coord_eff,
        "pcf_eta_rms_xyz_mps": eta_rms_by_axis,
        "pcf_s_eff_rms_xyz_mps": seff_rms_by_axis,
        "search_weight_delta_rms_frob_xyz_mps2": weight_delta_rms_by_axis,
        "search_weight_delta_rms_frob_0_5_xyz_mps2": weight_delta_rms_by_phase["0_5"],
        "search_weight_delta_rms_frob_5_20_xyz_mps2": weight_delta_rms_by_phase["5_20"],
        "search_weight_delta_norm_events_xyz_mps2": weight_delta_norm_by_axis,
        "valid_phase_mask_0_5": valid_phase_mask["0_5"],
        "valid_phase_mask_5_20": valid_phase_mask["5_20"],
        "prior_target_residual_rms_mps2": rms(prior - target),
        "online_before_target_residual_rms_mps2": rms(before - target),
        "online_after_same_state_target_residual_rms_mps2": rms(after_same_state - target),
        "online_before_vs_after_residual_improvement_mps2": rms(before - target) - rms(after_same_state - target),
        "target_clip_fraction_valid": float(np.mean(np.abs(y_direct[:, valid]) > dmax[:, None])),
        "closure_rms_mps2": rms(closure), "closure_max_abs_mps2": float(np.max(np.abs(closure))),
        "component_rms": comp_rms, "component_arrays": comps,
        "closure_array": closure,
        "raw_target_array": y_direct,
    })
    print(f"[{ordinal}/72] {scene}: scheduled=1999 online=1968 closure_max={scene_out[-1]['closure_max_abs_mps2']:.3e} m/s^2", flush=True)

# Summarize all required scene-level slices; RMS is pooled over events and axes,
# and also averaged across scene RMS values so the weighting convention is explicit.
groups: list[tuple[str, str, list[dict]]] = [("all", "ALL72", scene_out)]
for band in ("W00-W08", "W09-W14", "W15"):
    groups.append(("wind_band", band, [r for r in scene_out if r["band"] == band]))
    for task in sorted({r["task"] for r in scene_out}):
        groups.append(("wind_task", f"{band}:{task}", [r for r in scene_out if r["band"] == band and r["task"] == task]))
for split in ("VAL", "DEV"):
    groups.append(("split", split, [r for r in scene_out if r["split"] == split]))
    for band in ("W00-W08", "W09-W14", "W15"):
        groups.append(("split_wind", f"{split}:{band}", [r for r in scene_out if r["split"] == split and r["band"] == band]))
for task in sorted({r["task"] for r in scene_out}):
    groups.append(("task", task, [r for r in scene_out if r["task"] == task]))
for split in ("VAL", "DEV"):
    for task in sorted({r["task"] for r in scene_out}):
        groups.append(("split_task", f"{split}:{task}", [r for r in scene_out if r["split"] == split and r["task"] == task]))
for outcome in ("WIN", "LOSS"):
    groups.append(("outcome", outcome, [r for r in scene_out if r["score"]["win"] == outcome]))

summary_rows = []
for kind, name, subset in groups:
    if not subset:
        continue
    item = {"group_kind": kind, "group": name, "n_scenes": len(subset),
            "n_scheduled_events": sum(r["event_count_scheduled"] for r in subset),
            "n_online_valid_events": sum(r["event_count_online_valid"] for r in subset)}
    for term in ("d_wind", "d_alloc", "d_att", "d_map"):
        item.update(summarize_component(subset, term))
    item.update({
        "closure_rms_pooled_mps2": rms(np.concatenate([r["closure_array"].reshape(-1) for r in subset])),
        "closure_rms_scene_macro_mps2": float(np.mean([r["closure_rms_mps2"] for r in subset])),
        "closure_max_abs_mps2": float(max(r["closure_max_abs_mps2"] for r in subset)),
        "nominal_replay_max_abs_mps2": float(max(r["nominal_replay_max_abs_mps2"] for r in subset)),
        "beta_ramp_max_abs": float(max(r["beta_ramp_max_abs"] for r in subset)),
        "target_signal_rms_scene_macro_mps2": float(np.mean([r["target_signal_rms_mps2"] for r in subset])),
        "prior_residual_rms_scene_macro_mps2": float(np.mean([r["prior_target_residual_rms_mps2"] for r in subset])),
        "online_before_residual_rms_scene_macro_mps2": float(np.mean([r["online_before_target_residual_rms_mps2"] for r in subset])),
        "online_after_same_state_residual_rms_scene_macro_mps2": float(np.mean([r["online_after_same_state_target_residual_rms_mps2"] for r in subset])),
    })
    for axis_i, axis in enumerate(("x", "y", "z")):
        for metric, field in (
            ("target_signal", "target_signal_rms_xyz_mps2"),
            ("W0_prior_residual", "prior_target_residual_rms_xyz_mps2"),
            ("online_before_residual", "online_before_target_residual_rms_xyz_mps2"),
            ("online_after_same_state_residual", "online_after_same_state_target_residual_rms_xyz_mps2"),
            ("online_update_residual_gain", "online_before_vs_after_residual_improvement_xyz_mps2"),
        ):
            per_scene_axis = np.array([r[field][axis_i] for r in subset], dtype=np.float64)
            item[f"{metric}_{axis}_rms_scene_macro_mps2"] = float(np.mean(per_scene_axis))
            item[f"{metric}_{axis}_rms_pooled_mps2"] = float(np.sqrt(np.mean(per_scene_axis ** 2)))
        for phase in ("0_5", "5_20"):
            for metric in ("target_signal", "W0_prior_residual", "online_before_residual",
                           "online_after_same_state_residual", "online_update_residual_gain"):
                field = f"{metric}_rms_{phase}_xyz_mps2"
                per_scene_axis = np.array([r[field][axis_i] for r in subset], dtype=np.float64)
                counts = np.array([r[f"online_event_count_{phase}"] for r in subset], dtype=np.float64)
                item[f"{metric}_{axis}_rms_{phase}_scene_macro_mps2"] = float(np.mean(per_scene_axis))
                item[f"{metric}_{axis}_rms_{phase}_pooled_mps2"] = float(np.sqrt(np.average(per_scene_axis ** 2, weights=counts)))
    item["n_position_samples_0_5"] = sum(r["position_samples_0_5"] for r in subset)
    item["n_position_samples_5_20"] = sum(r["position_samples_5_20"] for r in subset)
    item["n_pcf_eta_samples"] = sum(r["pcf_eta_before_xyz_mps"].shape[1] for r in subset)
    item["n_pcf_seff_events"] = sum(r["pcf_event_s_eff_xyz_mps"].shape[1] for r in subset)
    item["n_online_weight_update_events"] = sum(r["search_weight_delta_norm_events_xyz_mps2"].shape[0] for r in subset)
    for phase in ("0_5", "5_20"):
        axis_macro = np.mean(np.stack([r[f"position_rmse_{phase}_xyz_m"] for r in subset]), axis=0)
        for axis_i, axis in enumerate(("x", "y", "z")):
            item[f"position_{axis}_rmse_{phase}_scene_macro_m"] = float(axis_macro[axis_i])
            pooled = np.concatenate([r["position_error_full_xyz_m"][axis_i, r[f"position_phase_mask_{phase}"]] for r in subset])
            item[f"position_{axis}_rmse_{phase}_pooled_m"] = rms(pooled)
    for axis_i, axis in enumerate(("x", "y", "z")):
        item[f"pcf_eta_{axis}_rms_scene_macro_mps"] = float(np.mean([r["pcf_eta_rms_xyz_mps"][axis_i] for r in subset]))
        item[f"pcf_eta_{axis}_rms_pooled_mps"] = rms(np.concatenate([r["pcf_eta_before_xyz_mps"][axis_i, :] for r in subset]))
        item[f"pcf_s_eff_{axis}_rms_scene_macro_mps"] = float(np.mean([r["pcf_s_eff_rms_xyz_mps"][axis_i] for r in subset]))
        item[f"pcf_s_eff_{axis}_rms_pooled_mps"] = rms(np.concatenate([r["pcf_event_s_eff_xyz_mps"][axis_i, :] for r in subset]))
        item[f"weight_delta_{axis}_rms_frob_scene_macro_mps2"] = float(np.mean([r["search_weight_delta_rms_frob_xyz_mps2"][axis_i] for r in subset]))
        item[f"weight_delta_{axis}_rms_frob_pooled_mps2"] = rms(np.concatenate([r["search_weight_delta_norm_events_xyz_mps2"][:, axis_i] for r in subset]))
        for phase in ("0_5", "5_20"):
            item[f"weight_delta_{axis}_rms_frob_{phase}_scene_macro_mps2"] = float(np.mean([r[f"search_weight_delta_rms_frob_{phase}_xyz_mps2"][axis_i] for r in subset]))
            chunks = [r["search_weight_delta_norm_events_xyz_mps2"][r[f"valid_phase_mask_{phase}"], axis_i] for r in subset]
            item[f"weight_delta_{axis}_rms_frob_{phase}_pooled_mps2"] = rms(np.concatenate(chunks))
    score_rows_subset = [r["score"] for r in subset]
    item["candidate_win_count"] = sum(r["win"] == "WIN" for r in score_rows_subset)
    item["candidate_q_scene_macro_m"] = float(np.mean([float(r["candidate_q_m"]) for r in score_rows_subset]))
    item["B_q_scene_macro_m"] = float(np.mean([float(r["B_q_m"]) for r in score_rows_subset]))
    item["delta_q_scene_macro_m"] = item["candidate_q_scene_macro_m"] - item["B_q_scene_macro_m"]
    summary_rows.append(item)

component_csv_rows = []
for r in scene_out:
    score = r["score"]
    axis_array_fields = {k for k, v in r.items() if isinstance(v, np.ndarray) and k.endswith("_xyz_mps2")}
    item = {k: v for k, v in r.items() if k not in axis_array_fields | {
        "score", "component_rms", "component_arrays", "closure_array", "raw_target_array",
        "position_rmse_0_5_xyz_m", "position_rmse_5_20_xyz_m", "position_samples_0_5", "position_samples_5_20",
        "position_error_full_xyz_m", "position_phase_mask_0_5", "position_phase_mask_5_20",
        "pcf_eta_before_xyz_mps", "pcf_event_s_eff_xyz_mps", "pcf_eta_rms_xyz_mps", "pcf_s_eff_rms_xyz_mps",
        "search_weight_delta_rms_frob_xyz_mps2", "search_weight_delta_rms_frob_0_5_xyz_mps2",
        "search_weight_delta_rms_frob_5_20_xyz_mps2", "search_weight_delta_norm_events_xyz_mps2",
        "valid_phase_mask_0_5", "valid_phase_mask_5_20",
    }}
    for axis_i, axis in enumerate(("x", "y", "z")):
        item[f"position_{axis}_rmse_0_5_m"] = float(r["position_rmse_0_5_xyz_m"][axis_i])
        item[f"position_{axis}_rmse_5_20_m"] = float(r["position_rmse_5_20_xyz_m"][axis_i])
        item[f"pcf_eta_{axis}_rms_mps"] = float(r["pcf_eta_rms_xyz_mps"][axis_i])
        item[f"pcf_s_eff_{axis}_rms_mps"] = float(r["pcf_s_eff_rms_xyz_mps"][axis_i])
        item[f"weight_delta_{axis}_rms_frob_mps2"] = float(r["search_weight_delta_rms_frob_xyz_mps2"][axis_i])
        item[f"weight_delta_{axis}_rms_frob_0_5_mps2"] = float(r["search_weight_delta_rms_frob_0_5_xyz_mps2"][axis_i])
        item[f"weight_delta_{axis}_rms_frob_5_20_mps2"] = float(r["search_weight_delta_rms_frob_5_20_xyz_mps2"][axis_i])
        item[f"target_signal_{axis}_rms_mps2"] = float(r["target_signal_rms_xyz_mps2"][axis_i])
        item[f"W0_prior_residual_{axis}_rms_mps2"] = float(r["prior_target_residual_rms_xyz_mps2"][axis_i])
        item[f"online_before_residual_{axis}_rms_mps2"] = float(r["online_before_target_residual_rms_xyz_mps2"][axis_i])
        item[f"online_after_same_state_residual_{axis}_rms_mps2"] = float(r["online_after_same_state_target_residual_rms_xyz_mps2"][axis_i])
        item[f"online_update_residual_gain_{axis}_mps2"] = float(r["online_before_vs_after_residual_improvement_xyz_mps2"][axis_i])
        for phase in ("0_5", "5_20"):
            for metric, field in (
                ("target_signal", f"target_signal_rms_{phase}_xyz_mps2"),
                ("W0_prior_residual", f"W0_prior_residual_rms_{phase}_xyz_mps2"),
                ("online_before_residual", f"online_before_residual_rms_{phase}_xyz_mps2"),
                ("online_after_same_state_residual", f"online_after_same_state_residual_rms_{phase}_xyz_mps2"),
                ("online_update_residual_gain", f"online_update_residual_gain_rms_{phase}_xyz_mps2"),
            ):
                item[f"{metric}_{axis}_rms_{phase}_mps2"] = float(r[field][axis_i])
    item.update({f"{k}_rms_mps2": v for k, v in r["component_rms"].items()})
    item.update({
        "closure_rms_mps2": r["closure_rms_mps2"],
        "closure_max_abs_mps2": r["closure_max_abs_mps2"],
        "candidate_q_m": score["candidate_q_m"], "B_q_m": score["B_q_m"],
        "delta_mm": score["delta_mm"], "outcome": score["win"],
        "model_id": score["model_id"], "model_sha256": score["model_sha256"],
    })
    component_csv_rows.append(item)

write_csv(OUT / "mechanism_components_by_scene.csv", component_csv_rows)
write_csv(OUT / "mechanism_components_summary.csv", summary_rows)
write_csv(OUT / "mechanism_input_lineage.csv", lineage_rows)
write_csv(OUT / "mechanism_run_start_lineage.csv", run_start_rows)

# Current score table's old target_rmse field is target-signal magnitude, not a residual.
# Emit a separately named machine-readable summary with explicit macro weights.
same_state_rows = []
for kind, name, subset in groups:
    if not subset:
        continue
    same_state_rows.append({
        "group_kind": kind, "group": name, "n_scenes": len(subset),
        "candidate_wins": sum(r["score"]["win"] == "WIN" for r in subset),
        "candidate_q_scene_macro_m": float(np.mean([float(r["score"]["candidate_q_m"]) for r in subset])),
        "B_q_scene_macro_m": float(np.mean([float(r["score"]["B_q_m"]) for r in subset])),
        "delta_q_scene_macro_m": float(np.mean([float(r["score"]["candidate_q_m"]) - float(r["score"]["B_q_m"]) for r in subset])),
        "beta_target_signal_rms_scene_macro_mps2": float(np.mean([r["target_signal_rms_mps2"] for r in subset])),
        "W0_prior_target_residual_rms_scene_macro_mps2": float(np.mean([r["prior_target_residual_rms_mps2"] for r in subset])),
        "online_before_target_residual_rms_scene_macro_mps2": float(np.mean([r["online_before_target_residual_rms_mps2"] for r in subset])),
        "online_after_same_state_target_residual_rms_scene_macro_mps2": float(np.mean([r["online_after_same_state_target_residual_rms_mps2"] for r in subset])),
        "weight_update_same_state_residual_gain_mps2": float(np.mean([r["online_before_vs_after_residual_improvement_mps2"] for r in subset])),
    })
    for axis_i, axis in enumerate(("x", "y", "z")):
        for metric, field in (
            ("target_signal", "target_signal_rms_xyz_mps2"),
            ("W0_prior_residual", "prior_target_residual_rms_xyz_mps2"),
            ("online_before_residual", "online_before_target_residual_rms_xyz_mps2"),
            ("online_after_same_state_residual", "online_after_same_state_target_residual_rms_xyz_mps2"),
            ("online_update_residual_gain", "online_before_vs_after_residual_improvement_xyz_mps2"),
        ):
            per_scene_axis = np.array([r[field][axis_i] for r in subset], dtype=np.float64)
            same_state_rows[-1][f"{metric}_{axis}_rms_scene_macro_mps2"] = float(np.mean(per_scene_axis))
            same_state_rows[-1][f"{metric}_{axis}_rms_pooled_mps2"] = float(np.sqrt(np.mean(per_scene_axis ** 2)))
        for phase in ("0_5", "5_20"):
            for metric in ("target_signal", "W0_prior_residual", "online_before_residual",
                           "online_after_same_state_residual", "online_update_residual_gain"):
                field = f"{metric}_rms_{phase}_xyz_mps2"
                per_scene_axis = np.array([r[field][axis_i] for r in subset], dtype=np.float64)
                counts = np.array([r[f"online_event_count_{phase}"] for r in subset], dtype=np.float64)
                same_state_rows[-1][f"{metric}_{axis}_rms_{phase}_scene_macro_mps2"] = float(np.mean(per_scene_axis))
                same_state_rows[-1][f"{metric}_{axis}_rms_{phase}_pooled_mps2"] = float(np.sqrt(np.average(per_scene_axis ** 2, weights=counts)))
write_csv(OUT / "mechanism_same_state_groups.csv", same_state_rows)

max_closure = max(r["closure_max_abs_mps2"] for r in scene_out)
max_nominal = max(r["nominal_replay_max_abs_mps2"] for r in scene_out)
max_beta = max(r["beta_ramp_max_abs"] for r in scene_out)
max_pcf_r = max(r["pcf_r_f_vs_a_req_minus_a_f_max_abs_mps2"] for r in scene_out)
max_pcf_eta_continuity = max(r["pcf_eta_1khz_continuity_max_abs_m"] for r in scene_out)
max_pcf_eta_replay = max(r["pcf_eta_1khz_replay_max_abs_m"] for r in scene_out)
max_pcf_event_eta = max(r["pcf_event_eta_sample_alignment_max_abs_m"] for r in scene_out)
max_pcf_coord = max(r["pcf_event_coord_relation_max_abs_mps"] for r in scene_out)
max_pcf_coord_eff = max(r["pcf_event_coord_eff_clip_max_abs_mps"] for r in scene_out)
max_weight_update = max(r["search_weight_update_replay_max_abs"] for r in scene_out)
max_position_q_replay = max(r["position_q_replay_max_abs_m"] for r in scene_out)
projection_mismatch_total = sum(r["search_projection_mismatch_count"] for r in scene_out)
if (max_closure > 1e-9 or max_nominal > 1e-9 or max_beta > 1e-12
        or max_pcf_r > 1e-9 or max_pcf_eta_continuity > 1e-9 or max_pcf_eta_replay > 1e-9
        or max_pcf_event_eta > 1e-9 or max_pcf_coord > 1e-9 or max_pcf_coord_eff > 1e-9
        or max_weight_update > 1e-9 or max_position_q_replay > 1e-12 or projection_mismatch_total != 0):
    raise RuntimeError("audit label/PCF/head replay threshold failed")
if len(canonical_model_hashes) != 1 or len(normalizer_hashes) != 1 or len(runtime_configs) != 1:
    raise RuntimeError(f"corrected full72 model/runtime identity is not homogeneous: model={canonical_model_hashes}, norm={normalizer_hashes}, config={runtime_configs}")
if (len(run_start_rows) != 72
        or len({r["run_start_sha256_before"] for r in run_start_rows}) != 72
        or len({r["run_start_model_sha256"] for r in run_start_rows}) != 1):
    raise RuntimeError("run_start path/hash/model coverage is not a unique, homogeneous 72-row binding")
summary_json = {
    "audit": "corrected DSSM14 G12/R32, full72 VAL+DEV only; no TEST read",
    "inputs": {
        "workspace": str(ROOT), "raw_index_files": [str(p) for p in EVALS],
        "raw_index_sha256": index_hashes, "existing_score_table": str(SCORE_CSV),
        "raw_index_shard_selected_rows": index_selected_counts,
        "raw_index_shard_alias_rows": index_selected_alias_counts,
        "raw_index_shard_exact_id_rows": {k: index_selected_counts[k] - index_selected_alias_counts[k] for k in index_selected_counts},
        "raw_index_shard_union_unique_raw_sha_count": len(index_by_sha),
        "raw_files": 72, "split_counts": {s: sum(r["split"] == s for r in scene_out) for s in ["VAL", "DEV"]},
        "raw_index_id_alias_count": alias_count,
        "raw_index_exact_id_match_count": len(by_scene) - alias_count,
        "raw_index_id_alias_rule": "24 raw rows preserve exact raw SHA but carry a trailing _ACC_FIX_V1 runtime_scene_id; base scene IDs are kept from the score table after split/task/wind agreement",
        "raw_sha_stat_unchanged_all72": True,
        "run_start_files": len(run_start_rows),
        "run_start_sha_stat_unchanged_all72": True,
        "run_start_path_source": "sibling run_start.mat derived only from each selected RAW_INDEX.csv run_status_path",
        "run_start_unique_file_sha256_count": len({r["run_start_sha256_before"] for r in run_start_rows}),
        "run_start_model_sha256_unique_count": len({r["run_start_model_sha256"] for r in run_start_rows}),
        "run_start_gamma_values": sorted({r["run_start_gamma"] for r in run_start_rows}),
        "run_start_kappa_values": sorted({r["run_start_kappa"] for r in run_start_rows}),
        "run_start_head_type_values": sorted({r["run_start_head_type"] for r in run_start_rows}),
        "run_start_pcf_enabled_values": sorted({r["run_start_pcf_enabled"] for r in run_start_rows}),
        "run_start_position_sample_time_s_values": sorted({r["run_start_position_sample_time_s"] for r in run_start_rows}),
        "run_start_position_update_hz_values": sorted({r["run_start_position_update_hz"] for r in run_start_rows}),
        "pair_summary": {
            "path": str(PAIR_CSV), "sha256": pair_file_sha,
            "all_rows": len(pair_all_rows), "DSSM_rows": len(pair_dssm_rows),
            "KAN_rows_excluded": len(pair_all_rows) - len(pair_dssm_rows),
            "DSSM_candidate_raw_sha_unique": len(pair_by_raw_sha),
            "exact_same_frozen_raw_sha_set_as_mechanism_72": set(pair_by_raw_sha) == expected_raw_shas,
            "split_task_Q_and_outcome_match_count": len(lineage_rows),
        },
        "model_arrays_identity_hash_count": len(canonical_model_hashes),
        "normalizer_identity_hash_count": len(normalizer_hashes),
        "runtime_config_identity_count": len(runtime_configs),
        "current_model_identity": {
            "model_id": "DSSM14", "architecture": "DSSM", "seed": 2026102001,
            "selected_step": 60000, "input_dim": 14, "window": 32, "context_length": 32,
            "head_type": "FEATURE", "gamma": 12.0, "kappa": 1.0,
            "beta_scale": 1.0, "pcf_enabled": True,
            "W0_equals_kappa_output_W_max_abs": max(r["W0_kappa_output_W_max_abs"] for r in scene_out),
            "model_arrays_identity_sha256_custom": next(iter(canonical_model_hashes)),
            "normalizer_identity_sha256_custom": next(iter(normalizer_hashes)),
        },
    },
    "event_convention": {
        "scheduled_position_events_per_scene": 1999,
        "online_inference_events_per_scene": 1968,
        "hdf5_event_index": "zero-based column i; MATLAB transition k=i+1",
        "first_last_transition_k": [11, 19991], "first_last_event_time_s": [0.01, 19.99],
        "beta_source": "logged stage1_position_event_beta on valid inference events",
        "beta_formula": "clip(transition_time(k)/1.8 s, 0, 1)",
        "beta_max_abs_error": max_beta,
    },
    "label_equations": {
        "Y": "R_actual*e3*T_real/m - g*e3 + wind/m - (a_nominal - a_applied)",
        "dWind": "wind_force_I/m",
        "dAlloc": "R_actual*e3*(T_real-T_req)/m",
        "dAtt": "(R_actual-R_raw)*e3*T_req/m",
        "dMap": "R_raw*e3*T_req/m - g*e3 - (a_nominal-a_applied)",
        "closure": "Y - (dWind+dAlloc+dAtt+dMap)",
        "units": "all Y/dWind/dAlloc/dAtt/dMap/closure m/s^2; Y is offline-only, not deployed input",
    },
    "pcf_and_online_head_equations": {
        "pcf_realized_acceleration": "a_F = (T/m) R(euler_filtered)e3 - g e3",
        "pcf_filter_residual": "r_F = a_req - a_F",
        "pcf_eta_1khz_update": "eta[k+1] = exp(-K2*dt) eta[k] + diag((1-exp(-K2*dt))/K2) r_F[k]",
        "pcf_coordination_at_position_event": "s_coord = s - eta_before_event; s_eff = clip(s_coord, [-7,-8,-10], [7,8,10])",
        "position_search_output_then_update": "u[k] = beta*clip(W_before^T phi, +/-dmax); W_after = clip(W_before + h*(-gamma*beta*phi*s_eff^T - 0.002*W_before), +/-60)",
        "event_convention": "PCF eta runs each 1 kHz transition; position SEARCH inference/Head update runs at 100 Hz scheduled events, with logged h approximately 0.01 s; output is evaluated before W update",
        "units": "eta/s/s_eff m/s; r_F/a_req/a_F/u m/s^2; phi and beta dimensionless; h and dt s; K2 and leakage 0.002 s^-1; gamma s^-2 under physical units; W has output scale m/s^2",
    },
    "validation": {
        "closure_rms_all72_mps2": rms(np.concatenate([r["closure_array"].reshape(-1) for r in scene_out])),
        "closure_max_abs_all72_mps2": max_closure,
        "nominal_bs_replay_max_abs_all72_mps2": max_nominal,
        "applied_alias_max_abs_all72_mps2": max(r["applied_alias_max_abs_mps2"] for r in scene_out),
        "online_output_applied_max_abs_all72_mps2": max(r["output_applied_max_abs_mps2"] for r in scene_out),
        "same_event_stage1_applied_max_abs_all72_mps2": max(r["event_applied_max_abs_mps2"] for r in scene_out),
        "pcf_r_f_vs_a_req_minus_a_f_max_abs_all72_mps2": max_pcf_r,
        "pcf_eta_1khz_continuity_max_abs_all72_m": max_pcf_eta_continuity,
        "pcf_eta_1khz_replay_max_abs_all72_m": max_pcf_eta_replay,
        "pcf_event_eta_sample_alignment_max_abs_all72_m": max_pcf_event_eta,
        "pcf_event_coord_relation_max_abs_all72_mps": max_pcf_coord,
        "pcf_event_coord_eff_clip_max_abs_all72_mps": max_pcf_coord_eff,
        "search_weight_update_replay_max_abs_all72": max_weight_update,
        "search_projection_mismatch_total_all72": projection_mismatch_total,
        "position_q_replay_max_abs_all72_m": max_position_q_replay,
        "search_effective_update_dt_range_s": [
            min(r["search_event_dt_min_s"] for r in scene_out),
            max(r["search_event_dt_max_s"] for r in scene_out),
        ],
    },
    "outputs": [
        str(OUT / "mechanism_components_by_scene.csv"),
        str(OUT / "mechanism_components_summary.csv"),
        str(OUT / "mechanism_same_state_groups.csv"),
        str(OUT / "mechanism_input_lineage.csv"),
        str(OUT / "mechanism_run_start_lineage.csv"),
    ],
}
(OUT / "mechanism_components_summary.json").write_text(json.dumps(summary_json, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps(summary_json["validation"], indent=2))
print(f"Wrote phase1 tables under {OUT}")
