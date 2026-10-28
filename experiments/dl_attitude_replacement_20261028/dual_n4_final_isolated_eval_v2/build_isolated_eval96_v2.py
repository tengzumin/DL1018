#!/usr/bin/env python
"""Generate and freeze a new 96-scene input-only queue; no controller or scorer is called."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import tempfile

import numpy as np
from scipy.io import savemat


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
V1 = REPO / "experiments/dl_attitude_replacement_20261028/dual_n4_final_isolated_eval_v1"
TRAIN = REPO / "experiments/dl_attitude_replacement_20261028/causal_n4_gate_train24_batch_v2"
SEED_BASE = 2026102896
WIND_SPECTRA = [
    {"wind_class": "LOW", "meaning": "v1 low-frequency / low-amplitude", "f1_hz": 0.23, "f2_hz": 0.43, "A1_mps": 1.2, "A2_mps": 0.8},
    {"wind_class": "MID", "meaning": "v1 mid-frequency / mid-amplitude", "f1_hz": 0.63, "f2_hz": 0.96, "A1_mps": 3.0, "A2_mps": 2.1},
    {"wind_class": "CONSTANT", "meaning": "v1 constant 9 m/s after the fixed startup ramp", "f1_hz": 0.23, "f2_hz": 0.43, "A1_mps": 0.0, "A2_mps": 0.0},
    {"wind_class": "AMP_SHIFT", "meaning": "v1 1.25x MID amplitudes", "f1_hz": 0.63, "f2_hz": 0.96, "A1_mps": 3.75, "A2_mps": 2.625},
    {"wind_class": "HF_A", "meaning": "original W09-W11 high band", "f1_hz": 2.2, "f2_hz": 3.2, "A1_mps": 4.2, "A2_mps": 3.1},
    {"wind_class": "HF_B", "meaning": "original W12-W14 high band", "f1_hz": 3.7, "f2_hz": 4.8, "A1_mps": 4.2, "A2_mps": 3.1},
    {"wind_class": "HF_A_SHIFT", "meaning": "HF_A frequencies shifted by +10%", "f1_hz": 2.42, "f2_hz": 3.52, "A1_mps": 4.2, "A2_mps": 3.1},
    {"wind_class": "HF_B_SHIFT", "meaning": "HF_B frequencies shifted by +10%", "f1_hz": 4.07, "f2_hz": 5.28, "A1_mps": 4.2, "A2_mps": 3.1},
]
HF_CLASSES = {"HF_A", "HF_B", "HF_A_SHIFT", "HF_B_SHIFT"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def canonical_json(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def write_frozen(path: Path, value) -> None:
    data = canonical_json(value)
    if path.exists() and path.read_bytes() != data:
        raise RuntimeError(f"Refusing to alter frozen v2 file: {path.name}")
    if not path.exists():
        path.write_bytes(data)


def load_v1_builder():
    path = V1 / "build_scene_queue.py"
    spec = importlib.util.spec_from_file_location("dual_n4_v1_scene_formulas", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def build_specs(v1):
    specs = []
    for ti, task in enumerate(v1.TASKS):
        for wi, wind in enumerate(WIND_SPECTRA):
            for mi, morph in enumerate(v1.MORPHOLOGY):
                seed = SEED_BASE + 10000 * ti + 100 * wi + mi
                rng = np.random.default_rng(seed)
                phase1, phase2 = rng.uniform(0.0, 2.0 * math.pi, size=2)
                azimuth = rng.uniform(0.0, 360.0)
                elevation = rng.uniform(-18.0, 18.0)
                arms = v1.TOPOLOGY_ARMS[morph["topology"]]
                targets, starts, retracts = [None] * 4, [None] * 4, [None] * 4
                for q, arm in enumerate(arms):
                    targets[arm - 1] = v1.TARGET_LENGTHS_M[(arm - 1 + mi) % len(v1.TARGET_LENGTHS_M)]
                    starts[arm - 1] = morph["start_base_s"] + q * morph["start_step_s"]
                    retracts[arm - 1] = morph["retract_base_s"] + q * morph["retract_step_s"]
                    travel_s = (targets[arm - 1] - v1.ARM_INITIAL_M[arm - 1]) / v1.MORPH_SPEED_MPS
                    if retracts[arm - 1] - starts[arm - 1] - travel_s < v1.MIN_HOLD_S:
                        raise ValueError(f"Insufficient morphology hold for {task['task_code']}/{wind['wind_class']}/{morph['morph_id']}")
                sid = f"DUALN4_EVAL96_V2_{task['task_code']}_{wind['wind_class']}_{morph['morph_id']}"
                specs.append({
                    "scene_id": sid, "task_code": task["task_code"], "task": task["task"],
                    "wind_class": wind["wind_class"], "morph_id": morph["morph_id"], "seed": seed,
                    "wind": {
                        "type": "biased_dual_sine", "direction_azimuth_deg": float(azimuth),
                        "direction_elevation_deg": float(elevation), "V0_mps": 9.0,
                        "A1_mps": wind["A1_mps"], "f1_hz": wind["f1_hz"], "phi1_rad": float(phase1),
                        "A2_mps": wind["A2_mps"], "f2_hz": wind["f2_hz"], "phi2_rad": float(phase2),
                        "rise_time_s": 0.8, "rho_air_kg_m3": 1.225, "CdBody": 1.0, "CdArm": 1.0,
                    },
                    "morphology": {
                        "topology": morph["topology"], "active_arms": arms,
                        "target_arm_lengths_m": targets, "start_time_s": starts,
                        "retract_start_time_s": retracts, "retract": True,
                        "morph_speed_mps": v1.MORPH_SPEED_MPS, "minimum_hold_s": v1.MIN_HOLD_S,
                    },
                    "payload_path": f"payloads/{sid}.mat",
                })
    expected = {(t["task_code"], w["wind_class"], m["morph_id"])
                for t in v1.TASKS for w in WIND_SPECTRA for m in v1.MORPHOLOGY}
    actual = {(s["task_code"], s["wind_class"], s["morph_id"]) for s in specs}
    if len(specs) != 96 or len({s["scene_id"] for s in specs}) != 96 or len({s["seed"] for s in specs}) != 96 or actual != expected:
        raise ValueError("v2 cohort is not the exact 3 x 8 x 4 grid")
    return specs


def make_config(v1):
    return {
        "schema": "DUALN4_EVAL96_GENERATOR_CONFIG_V2",
        "study_id": "dual_n4_final_isolated_eval_v2",
        "id_namespace": "DUALN4_EVAL96_V2",
        "duration_s": v1.DURATION_S,
        "dt_s": v1.DT,
        "state_samples": int(round(v1.DURATION_S / v1.DT)) + 1,
        "reference_contract_id": v1.REFERENCE_CONTRACT,
        "wind": {"model": "biased_dual_sine", "V0_mps": 9.0, "rise_time_s": 0.8,
                 "rho_air_kg_m3": 1.225, "CdBody": 1.0, "CdArm": 1.0},
        "wind_spectra": WIND_SPECTRA,
        "hf_definition": {
            "HF_A": ["HF_A", "HF_A_SHIFT"], "HF_B": ["HF_B", "HF_B_SHIFT"],
            "HF_all": sorted(HF_CLASSES), "nominal_HF": ["HF_A", "HF_B"],
            "detuned_HF": ["HF_A_SHIFT", "HF_B_SHIFT"],
            "detune_ratio": 1.1,
            "amplitudes_A1_A2_mps": [4.2, 3.1],
        },
        "morphology": {"variants": v1.MORPHOLOGY, "topology_arms": v1.TOPOLOGY_ARMS,
                       "target_lengths_m": v1.TARGET_LENGTHS_M,
                       "morph_speed_mps": v1.MORPH_SPEED_MPS,
                       "minimum_hold_s": v1.MIN_HOLD_S, "retract": True},
        "seed_rule": f"{SEED_BASE} + 10000*task_index + 100*wind_index + morphology_index; NumPy PCG64",
        "controller_input_policy": {
            "environment_wind_exposed_to_controller": False,
            "model_weights_in_scene_payload": False,
            "future_samples_exposed_to_controller": False,
            "environment_wind_role": "Plant environment only; consumers must keep it outside controller inputs.",
        },
        "training_and_tuning_policy": "v2 scenes are sealed evaluation inputs only; never add them to training or tuning.",
    }


def write_payload(v1, path: Path, scene: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".mat", delete=False) as temp:
        temp_path = Path(temp.name)
    try:
        savemat(temp_path, {"scene": scene}, do_compression=True, oned_as="column", format="5")
        header = b"MATLAB 5.0 MAT-file, Frozen DUALN4_EVAL96 scene payload v2".ljust(116, b" ")
        with temp_path.open("r+b") as stream:
            stream.write(header)
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def formula_paths():
    return {
        "run_comparison.m": REPO / "run_comparison.m",
        "make_paired_dev58_scene.m": TRAIN / "candidate_runner_work/matlab/scenes/make_paired_dev58_scene.m",
        "wind_velocity_profile.m": TRAIN / "candidate_runner_work/matlab/core/wind_velocity_profile.m",
        "tcn0916_morphology_scenario.m": TRAIN / "candidate_runner_work/matlab/core/tcn0916_morphology_scenario.m",
        "tcn0916_topologies.m": TRAIN / "candidate_runner_work/matlab/core/tcn0916_topologies.m",
    }


def main():
    v1 = load_v1_builder()
    specs = build_specs(v1)
    config = make_config(v1)
    v1_context_path = V1 / "SOURCE_CONTEXT_v1.json"
    v1_context = json.loads(v1_context_path.read_text(encoding="utf-8"))
    context = {
        "schema": "DUALN4_EVAL96_SOURCE_CONTEXT_V2",
        "reference_scene_id": v1_context["reference_scene_id"],
        "reference_source_split": v1_context["reference_source_split"],
        "parent_run_start_sha256": v1_context["parent_run_start_sha256"],
        "parent_scene_payload_sha256": v1_context["parent_scene_payload_sha256"],
        "cfg_field_used": v1_context["cfg_field_used"],
        "cfg_arm_initial_m": v1_context["cfg_arm_initial_m"],
        "cfg_arm_initial_canonical_sha256": v1_context["cfg_arm_initial_canonical_sha256"],
        "v1_source_context_sha256": sha256(v1_context_path),
        "note": "Inherits only the v1 geometry/config provenance; no model weights, TEST arrays, controller, or scoring are loaded.",
    }
    config_path, specs_path, context_path = (HERE / "GENERATOR_CONFIG_v2.json", HERE / "SCENE_SPECS_v2.json", HERE / "SOURCE_CONTEXT_v2.json")
    write_frozen(config_path, config)
    write_frozen(context_path, context)
    write_frozen(specs_path, {
        "schema": "DUALN4_EVAL96_SCENE_SPECS_V2", "status": "FROZEN_PENDING_CANDIDATE_SEAL",
        "study_id": config["study_id"], "spec_count": 96, "task_count": 3,
        "wind_group_count": 8, "morphology_schedule_count": 4,
        "controller_input_policy": config["controller_input_policy"],
        "hf_reporting_groups": {
            "HF_all": sorted(HF_CLASSES), "nominal_HF": ["HF_A", "HF_B"],
            "detuned_HF": ["HF_A_SHIFT", "HF_B_SHIFT"],
        },
        "cases": specs,
    })
    payload_hashes = {}
    for spec in specs:
        path = HERE / spec["payload_path"]
        scene = v1.make_scene(spec)
        if path.exists():
            v1.validate_saved_mat(path, spec, scene)
        else:
            write_payload(v1, path, scene)
            v1.validate_saved_mat(path, spec, scene)
        payload_hashes[path.name] = sha256(path)

    formulas = {name: sha256(path) for name, path in formula_paths().items()}
    builder_hash = sha256(Path(__file__).resolve())
    v1_builder_hash = sha256(V1 / "build_scene_queue.py")
    source_lock = {
        "schema": "DUALN4_EVAL96_SOURCE_LOCK_V2",
        "status": "FROZEN_96_SCENES_PENDING_CANDIDATE_FREEZE",
        "spec_sha256": sha256(specs_path), "generator_config_sha256": sha256(config_path),
        "source_context_sha256": sha256(context_path), "builder_sha256": builder_hash,
        "v1_scene_formula_builder_sha256": v1_builder_hash,
        "v1_source_lock_sha256": sha256(V1 / "SOURCE_LOCK_v1.json"),
        "v1_source_lock_unchanged": True,
        "formula_source_sha256": formulas,
        "payload_sha256": payload_hashes,
        "controller_input_policy": config["controller_input_policy"],
        "Plant_calls": 0, "controller_calls": 0, "score_calls": 0,
        "TEST_read": False, "inertia_reconstruction_enabled": False,
        "new_scenes_used_for_training_or_tuning": False,
    }
    write_frozen(HERE / "SOURCE_LOCK_v2.json", source_lock)
    audit = {
        "schema": "DUALN4_EVAL96_GENERATION_AUDIT_V2",
        "status": "PASS_FULL_PAYLOADS",
        "frozen_spec_count": 96, "generated_payload_count": 96,
        "sample_shape": {"time_samples": 20001, "dt_s": v1.DT, "duration_s": v1.DURATION_S,
                         "initial_state": [12, 1], "wind": [20001, 3],
                         "reference_xyz": [20001, 3], "arms": [20001, 4]},
        "HF_counts": {"HF_all": 48, "nominal_HF": 24, "detuned_HF": 24, "all_scene_count": 96},
        "Plant_calls": 0, "controller_calls": 0, "score_calls": 0,
        "TEST_read": False, "inertia_reconstruction_enabled": False,
        "new_scenes_used_for_training_or_tuning": False,
        "v1_files_modified": False,
    }
    write_frozen(HERE / "GENERATION_AUDIT_v2.json", audit)
    print(json.dumps({"status": audit["status"], "spec_count": 96, "payload_count": len(payload_hashes),
                      "HF_all": 48, "nominal_HF": 24, "detuned_HF": 24,
                      "Plant_calls": 0, "controller_calls": 0, "score_calls": 0,
                      "source_lock_sha256": sha256(HERE / "SOURCE_LOCK_v2.json")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
