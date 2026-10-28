"""Read-only first-scene paired score and force-path audit for force09."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import h5py
import numpy as np

HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
ROOT = STUDY.parents[4]
SID = "DL1018_DEV_T1_C10_W09"
RAW = STUDY / "runs" / SID / "PHYS_RESIDUAL_ATTEMPT_01" / "raw_run.mat"
STATUS = RAW.with_name("run_status.json")
OUT = HERE / "FIRST_SCENE_FORCE09_PARTIAL_SCORE_v1.json"
SCORE_PATH = HERE / "score_closed_loop_v1.py"


def load_scorer():
    spec = importlib.util.spec_from_file_location("force09_frozen_scorer", SCORE_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(SCORE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> None:
    scorer = load_scorer()
    release = scorer.readj(STUDY / "RELEASE.json")
    baselines = scorer.validate_baseline_bindings(release)
    manifest_row = next(r for r in scorer.readj(scorer.WN12 / "MANIFEST.json")["records"]
                        if r["scene_id"] == SID)
    legacy_identity = scorer.readj(scorer.WN12 / "SCREEN12_RESULTS_v1.json")["scenes"][manifest_row["order"] - 1]["identity"]
    candidate = scorer.discover_candidate(SID, manifest_row["payload_sha256"],
                                          manifest_row["b_raw_sha256"], release,
                                          scorer.sha(STUDY / "RELEASE.json"), legacy_identity)
    if candidate["status"] != "SCORED":
        raise RuntimeError(f"first scene not scoreable: {candidate['status']}")
    paired = {"Candidate": candidate["metrics"]}
    paired.update({m: baselines["records"][SID][m]["metrics"] for m in ("B", "C5")})

    with h5py.File(RAW, "r") as f:
        log = f["log"]
        get = lambda name: np.asarray(log[name][()], dtype=float)
        scale = float(get("stage1_position_compensation_scale").reshape(-1)[0])
        unscaled = get("stage1_position_applied_acceleration_unscaled_mps2")
        applied = get("stage1_position_applied_acceleration_mps2")
        held_unscaled = get("stage1_position_held_applied_acceleration_unscaled_mps2")
        held_applied = get("stage1_position_held_applied_acceleration_mps2")
        held_force = get("stage1_position_held_force_I_N")
        injected_force = get("stage1_position_injected_force_I_N")
        compensation_force = get("position_compensation_applied_force_N")
        nominal_force = get("position_bs_nominal_force_N")
        nominal_accel = get("position_nominal_acceleration_mps2")
        commanded_force = get("position_commanded_force_N")
        pcf_request = get("stage1_position_pcf_a_req_mps2")
        pcf_applied = get("stage1_position_pcf_a_f_mps2")

    # Infer the configured mass from force/acceleration trace pairs; no plant truth is read.
    nonzero = np.linalg.norm(held_applied, axis=0) > 1e-10
    mass = float(np.sum(held_force[:, nonzero] * held_applied[:, nonzero]) /
                 np.sum(held_applied[:, nonzero] ** 2))
    errors = {
        "applied_vs_scale_times_unscaled_mps2": float(np.max(np.abs(applied - scale * unscaled))),
        "held_applied_vs_scale_times_unscaled_mps2": float(np.max(np.abs(held_applied - scale * held_unscaled))),
        "held_force_vs_mass_times_held_applied_N": float(np.max(np.abs(held_force - mass * held_applied))),
        "injected_force_vs_held_force_N": float(np.max(np.abs(injected_force - held_force))),
        "logged_compensation_vs_injected_force_N": float(np.max(np.abs(compensation_force - injected_force))),
        "commanded_force_nominal_minus_compensation_N": float(np.max(np.abs(commanded_force - nominal_force + compensation_force))),
        "nominal_force_vs_mass_times_nominal_accel_N": float(np.max(np.abs(nominal_force - mass * nominal_accel))),
        "pcf_request_vs_commanded_force_over_mass_mps2": float(np.max(np.abs(pcf_request - commanded_force / mass))),
    }
    result = {
        "schema": "DL1018_FORCE09_FIRST_SCENE_PARTIAL_SCORE_AND_TRACE_AUDIT_V1",
        "status": "PASS_SINGLE_SCENE_SCORE_AND_FORCE_PATH_TRACE_CHECKS",
        "scope": "one completed DEV scene; not a 12-scene macro/gate or causal comparison",
        "scene_id": SID,
        "release_sha256": scorer.sha(STUDY / "RELEASE.json"),
        "raw_path": str(RAW),
        "raw_sha256": scorer.sha(RAW),
        "run_status_path": str(STATUS),
        "run_status_sha256": scorer.sha(STATUS),
        "force_scale": scale,
        "inferred_mass_kg_from_logged_force_and_acceleration": mass,
        "paired_metrics": {m: {k: float(paired[m][k]) for k in scorer.metrics.MAIN}
                            for m in ("Candidate", "B", "C5")},
        "candidate_minus_baseline": {
            b: {k: float(paired["Candidate"][k] - paired[b][k]) for k in scorer.metrics.MAIN}
            for b in ("B", "C5")},
        "force_path_max_abs_reconstruction_errors": errors,
        "trace_interpretation": {
            "position_nominal_feedback": "position_bs_nominal_force is logged separately and remains the BS term; the runtime relation commanded_force = nominal_force - applied_compensation is verified.",
            "pcf": "PCF request equals the applied-force-derived commanded acceleration; PCF filtered acceleration is downstream and is not required to equal the request.",
            "causality": "logged identities validate this run's implementation path only; they do not establish counterfactual closed-loop causality."
        },
        "test_data_read": False,
    }
    if abs(scale - 0.9) > 1e-12 or max(errors.values()) > 2e-10:
        raise RuntimeError(f"force-path trace check failed: {result}")
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "output": str(OUT),
                      "force_scale": scale, "mass_kg": mass, "errors": errors,
                      "paired_metrics": result["paired_metrics"],
                      "candidate_minus_baseline": result["candidate_minus_baseline"]},
                     indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
