#!/usr/bin/env python
"""Lightweight, read-only verification of the two v9 PROBE event logs."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import h5py
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
RUN_DIR = ROOT / "experiments/position_prior_calibration_c1_20261022_v9/runs_v9/DL1018_VAL_T2_C00_W10"
OUT = Path(__file__).with_name("probe_event_contract_review.json")
C_STAR = 0.2802979648061464
W0_SHA256 = "88f8c4f2495438c3797655c48bab1bf0c11ac2e27bff1f5f2a7423a8f0a2cf53"
RAW_SHA256 = {
    "ON1": "2377ee61ec67f15012256502e28f008c26b61af78d0964995ec2f2d8678e854e",
    "ONC": "311a4292f97198c387bd1548cece83ba616ddff52e09200935e44cbea5deca42",
}
EXPECTED = {
    "source_lock": "02668f6268944715e65e6d2cffa52b395417506132212b00e7d273d88df164e5",
    "release": "7aa072835b0e633f9e40d0e471a17870735d32ddf079eafc61ac6790ea7974d0",
    "runner": "927cce40444f70c4012f9aae5d9a2584591c2adeb21b2c2c5617a5b4fcc72d18",
    "head": "3bd0fe9686c3b75793575e517d4cc5f08de58ab6a26a2bc7516aa690422bb7dc",
    "runtime": "01d83dec95aea5d30feef3afd0628a2ce0911f70465f0773a4f568a01b08450b",
    "pcf": "b4ae22db5bd444a162d0cd01a3a59a589f2e37077b089bb33693401b660228d0",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def maxabs(a: np.ndarray) -> float:
    return float(np.max(np.abs(a))) if a.size else 0.0


def vector(g: h5py.Group, name: str) -> np.ndarray:
    return np.asarray(g[name][()]).reshape(-1)


def verify_source_pins() -> dict:
    exp = ROOT / "experiments/position_prior_calibration_c1_20261022_v9"
    lock_path = exp / "C1_SOURCE_LOCK_v2.json"
    release_path = exp / "C1_RELEASE_v9.json"
    runner_path = exp / "run_c1_screen.m"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    actual = {
        "source_lock": sha256(lock_path),
        "release": sha256(release_path),
        "runner": sha256(runner_path),
    }
    runtime_by_name = {Path(row["path"]).name: row for row in lock["frozen_runtime_files"]}
    runtime_paths = {
        "head": Path(runtime_by_name["position_only_search_head_step.m"]["path"]),
        "runtime": Path(runtime_by_name["run_dl1018_closed_loop.m"]["path"]),
        "pcf": Path(runtime_by_name["position_filter_realization_pcf_step_v3_5.m"]["path"]),
    }
    for key, path in runtime_paths.items():
        actual[key] = sha256(path)
        assert actual[key] == EXPECTED[key], (key, actual[key])
    for key in ("source_lock", "release", "runner"):
        assert actual[key] == EXPECTED[key], (key, actual[key])
    return actual


def verify_run(condition: str, w0_from_on1: np.ndarray | None) -> tuple[dict, np.ndarray]:
    path = RUN_DIR / condition / "attempt_01/raw_run.mat"
    stat_before = path.stat()
    raw_hash_before = sha256(path)
    assert raw_hash_before == RAW_SHA256[condition], (condition, raw_hash_before)

    with h5py.File(path, "r") as f:
        g = f["log"]
        steps = vector(g, "stage1_position_event_step_index").astype(int)
        q = steps - 1  # MATLAB step k is HDF5 time column k-1.
        assert len(steps) == 1968 and np.all((q >= 0) & (q < 20000))

        scheduler_flag = vector(g, "stage1_position_event").astype(bool)
        scheduler_steps = np.flatnonzero(scheduler_flag) + 1
        assert np.array_equal(steps, scheduler_steps[scheduler_steps >= steps[0]])
        valid = vector(g, "stage1_position_event_inference_valid").astype(bool)[q]
        assert int(valid.sum()) == 1968

        phi = np.asarray(g["stage1_position_event_phi_33"][()])[:, q].T
        raw = np.asarray(g["stage1_position_event_raw_acceleration_mps2"][()])[:, q].T
        applied = np.asarray(g["stage1_position_event_applied_acceleration_mps2"][()])[:, q].T
        beta = vector(g, "stage1_position_event_beta")[q]
        event_dt = vector(g, "stage1_position_event_dt_s")[q]
        update_dt = vector(g, "stage1_position_effective_update_dt_s")[q]
        projection = vector(g, "stage1_position_event_projection").astype(bool)[q]
        w_before = np.asarray(g["stage1_position_event_weight_before_33x3"][()]).transpose(0, 2, 1)
        w_after = np.asarray(g["stage1_position_event_weight_after_33x3"][()]).transpose(0, 2, 1)

        w0 = np.asarray(g["stage1_position_search_initial_weight"][()]).T
        w_initial = np.asarray(g["stage1_position_weight_initial"][()]).T
        w_final = np.asarray(g["stage1_position_weight_final"][()]).T
        w0_hash = hashlib.sha256(np.asarray(w0, dtype="<f8").tobytes(order="F")).hexdigest()
        assert w0_hash == W0_SHA256 and w0.shape == (33, 3)
        scale = 1.0 if condition == "ON1" else C_STAR
        assert maxabs(w_initial - scale * w0) == 0.0
        if condition == "ON1":
            assert w0_from_on1 is None
        else:
            assert w0_from_on1 is not None and maxabs(w0 - w0_from_on1) == 0.0

        gamma = float(np.asarray(g["stage1_position_search_gamma"][()]).item())
        kappa = float(np.asarray(g["stage1_position_search_kappa"][()]).item())
        beta_scale = float(np.asarray(g["stage1_position_beta_scale"][()]).item())
        dt_scale = float(np.asarray(g["stage1_position_update_dt_scale"][()]).item())
        update_enabled = bool(np.asarray(g["stage1_position_update_enabled"][()]).item())
        pcf_enabled = bool(np.asarray(g["stage1_position_pcf_coordination_enabled"][()]).item())
        assert gamma == 12.0 and kappa == scale and beta_scale == 1.0 and dt_scale == 1.0
        assert update_enabled and pcf_enabled

        dmax = np.array([3.0, 3.0, 3.0])
        s_limit = np.array([7.0, 8.0, 10.0])
        leak = 0.002
        raw_calc = np.einsum("nfi,nf->ni", w_before, phi)
        applied_calc = beta[:, None] * np.clip(raw_calc, -dmax, dmax)

        s_original = np.asarray(g["stage1_position_pcf_event_s_original_mps"][()])[:, q].T
        eta_event = np.asarray(g["stage1_position_pcf_event_eta_before_mps"][()])[:, q].T
        s_coord = np.asarray(g["stage1_position_pcf_event_s_coord_mps"][()])[:, q].T
        s_eff = np.asarray(g["stage1_position_pcf_event_s_coord_eff_mps"][()])[:, q].T
        s_coord_calc = s_original - eta_event
        s_eff_calc = np.clip(s_coord_calc, -s_limit, s_limit)
        unprojected = w_before + update_dt[:, None, None] * (
            -gamma * beta[:, None, None] * phi[:, :, None] * s_eff_calc[:, None, :] - leak * w_before
        )
        w_after_calc = np.clip(unprojected, -60.0, 60.0)
        projection_calc = np.any(np.abs(unprojected) > 60.0, axis=(1, 2))

        time = np.asarray(g["time"][()]).reshape(-1)
        transition_time = np.asarray(g["transition_time"][()]).reshape(-1)
        step_dt = np.diff(time)
        beta_calc = np.clip(transition_time[q] / 1.8, 0.0, 1.0)

        eta_before = np.asarray(g["stage1_position_pcf_eta_before_mps"][()])
        eta_after = np.asarray(g["stage1_position_pcf_eta_after_mps"][()])
        a_req = np.asarray(g["stage1_position_pcf_a_req_mps2"][()])
        a_f = np.asarray(g["stage1_position_pcf_a_f_mps2"][()])
        r_f = np.asarray(g["stage1_position_pcf_r_f_mps2"][()])
        k2 = np.full((3, 1), 4.0)
        decay = np.exp(-k2 * step_dt[None, :])
        integral = -np.expm1(-k2 * step_dt[None, :]) / k2
        eta_after_calc = decay * eta_before + integral * r_f

        errors = {
            "raw_WbeforeT_phi_max_abs": maxabs(raw_calc - raw),
            "applied_beta_clip_max_abs": maxabs(applied_calc - applied),
            "sc_equals_s_minus_eta_max_abs": maxabs(s_coord_calc - s_coord),
            "seff_clip_max_abs": maxabs(s_eff_calc - s_eff),
            "full_discrete_update_max_abs": maxabs(w_after_calc - w_after),
            "projection_flag_mismatches": int(np.count_nonzero(projection_calc != projection)),
            "event_eta_matches_current_step_max_abs": maxabs(eta_event - eta_before[:, q].T),
            "eta_after_to_next_before_max_abs": maxabs(eta_after[:, :-1] - eta_before[:, 1:]),
            "rF_equals_aReq_minus_aF_max_abs": maxabs(r_f - (a_req - a_f)),
            "full_plant_step_eta_recurrence_max_abs": maxabs(eta_after_calc - eta_after),
            "weight_event_chain_max_abs": maxabs(w_before[1:] - w_after[:-1]),
            "first_before_matches_initial_max_abs": maxabs(w_before[0] - w_initial),
            "last_after_matches_final_max_abs": maxabs(w_after[-1] - w_final),
            "beta_formula_max_abs": maxabs(beta - beta_calc),
            "effective_dt_equals_event_dt_max_abs": maxabs(update_dt - event_dt),
        }
        assert max(errors[k] for k in errors if k.endswith("max_abs")) <= 1e-12
        assert errors["projection_flag_mismatches"] == 0
        assert 0.0 < float(np.min(step_dt)) and len(step_dt) == 20000

        z_delta = w_after[:, :, 2] - w_before[:, :, 2]
        result = {
            "condition": condition,
            "raw_path": str(path),
            "raw_sha256": raw_hash_before,
            "raw_size_bytes": int(stat_before.st_size),
            "event_count": int(len(steps)),
            "event_step_indices_matlab_1based": [int(steps[0]), int(steps[-1])],
            "event_transition_times_s": [float(transition_time[q[0]]), float(transition_time[q[-1]])],
            "scheduler_event_count": int(len(scheduler_steps)),
            "event_indices_match_scheduler_after_readiness": True,
            "readiness_event_count": int(np.asarray(g["stage1_position_readiness_events"][()]).item()),
            "plant_dt_s_min_max": [float(np.min(step_dt)), float(np.max(step_dt))],
            "head_event_dt_s_min_max": [float(np.min(event_dt)), float(np.max(event_dt))],
            "beta_min_max": [float(np.min(beta)), float(np.max(beta))],
            "gamma_kappa_beta_scale_dt_scale": [gamma, kappa, beta_scale, dt_scale],
            "phi_norm_min_max": [float(np.min(np.linalg.norm(phi, axis=1))), float(np.max(np.linalg.norm(phi, axis=1)))],
            "w0_canonical_sha256_matlab_f_order_double": w0_hash,
            "initial_weight_scale_vs_w0_max_abs": maxabs(w_initial - scale * w0),
            "raw_clip_component_hits": int(np.count_nonzero(np.abs(raw_calc) > dmax[None, :])),
            "projection_event_count_recomputed_recorded": [int(np.count_nonzero(projection_calc)), int(np.count_nonzero(projection))],
            "pcf_eta_event_max_abs_xyz_m": np.max(np.abs(eta_event), axis=0).tolist(),
            "pcf_scoord_max_abs_xyz_m": np.max(np.abs(s_coord), axis=0).tolist(),
            "pcf_z_s_eff_nonzero_event_count": int(np.count_nonzero(np.abs(s_eff[:, 2]) > 1e-15)),
            "weight_z_update_nonzero_event_count": int(np.count_nonzero(np.linalg.norm(z_delta, axis=1) > 1e-15)),
            "weight_z_update_norm_max": float(np.max(np.linalg.norm(z_delta, axis=1))),
            "max_errors": errors,
        }

    after = path.stat()
    raw_hash_after = sha256(path)
    assert raw_hash_after == raw_hash_before and after.st_size == stat_before.st_size and after.st_mtime_ns == stat_before.st_mtime_ns
    result["raw_stat_before_after_equal"] = True
    return result, w0


def main() -> None:
    source_hashes = verify_source_pins()
    probe_path = ROOT / "experiments/position_prior_calibration_c1_20261022_v9/reports/probe_c1_v9.json"
    probe = json.loads(probe_path.read_text(encoding="utf-8"))
    assert probe["scene_id"] == "DL1018_VAL_T2_C00_W10" and probe["c_star"] == C_STAR
    by_condition = {row["condition"]: row for row in probe["run_rows"]}

    on1, w0 = verify_run("ON1", None)
    onc, _ = verify_run("ONC", w0)
    for condition, row in (("ON1", on1), ("ONC", onc)):
        assert by_condition[condition]["raw_sha256"] == row["raw_sha256"]

    result = {
        "schema": "C1_V9_ACTUAL_EVENT_CONTRACT_REVIEW_V1",
        "status": "PASS",
        "scene_id": "DL1018_VAL_T2_C00_W10",
        "c_star": C_STAR,
        "source_hashes": source_hashes,
        "probe_summary_sha256": sha256(probe_path),
        "runs": [on1, onc],
        "timing_and_causal_boundary": (
            "At each plant step the FEATURE head emits raw/applied output from W_before and current phi, "
            "then applies the recorded discrete weight update using current s_eff. The current step's PCF eta_before "
            "forms s_coord=s-eta; the physical command and filtered Euler are computed later in that step, after "
            "which eta_after is advanced for the next step. This verifies implementation and event-log alignment "
            "on each closed-loop trajectory; it does not isolate the head's causal effect on closed-loop performance."
        ),
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "output": str(OUT), "runs": [
        {"condition": r["condition"], "events": r["event_count"], "raw_sha256": r["raw_sha256"], "max_errors": r["max_errors"]}
        for r in result["runs"]
    ]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
