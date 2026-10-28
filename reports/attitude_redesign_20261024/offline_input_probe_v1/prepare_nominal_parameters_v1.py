"""Prepare pinned fixed-model attitude parameters for the offline input probe.

Reads only the scene lock, 96 small run_start.mat files, and pinned evidence;
never opens H5/raw_run arrays or executes a controller/Plant.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat


ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "PARAMETERS_v1.json"
LOCK_PATH = HERE / "INPUT_SCENE_LOCK_v1.json"
AUDIT_PATH = HERE / "ROOT_INPUT_LOCK_AUDIT_v1.json"
EQUIV_PATH = HERE / "ROOT_PHYSICAL_CONFIGURATION_EQUIVALENCE_v1.json"
RECON_PATH = ROOT / "reports/attitude_redesign_20261024/nonzero_pair_reconstruction_v1.json"
MATLAB_RECEIPT_PATH = ROOT / "reports/attitude_redesign_20261024/nonzero_pair_validation_receipt_v1.json"

PINS = {
    "input_lock_sha256": "2711d5ebc3c8c0463633a6d65b59c3333508ce6352c0ba62c942c2ff6547348d",
    "root_input_audit_sha256": "8a08ac8c76ade20804aed6053867257646649c38a1840dc05a2fd8c23b81e210",
    "physical_equivalence_sha256": "0c0eff38cfb9fc07011b0768bfece7a7b291bd929f9b120622ea9a81cecbe3ee",
    "matlab_reconstruction_sha256": "e328c4786231a9eb498cad05590b145bc80c86a86b449e31fdf36af4c5f71c77",
    "matlab_receipt_sha256": "26b49799ab0f5110ee9d285e08ad1b25807407115015a89e37ae0820dab44755",
    "matlab_script_sha256": "f455bb80ace5e2149ab84f56b1330c115c3217212cbb5cf545c4b0873e75c952",
    "current_validator_source_sha256": "bfacfadad2fbf9dc3e10fadbbf7c728ae16450141515fdecfb3a99d4856705f5",
}
CORE_SOURCE_SHA256 = {
    "matlab/core/simulation_parameters.m": "962b5434c23d5ac1a9ac568f136635a8ea651a775165d84b7d95250ca88bb9ae",
    "matlab/core/controller_parameters.m": "4fad5e78c0bd4177461647af167e7c86a7defa628b43d523b0b7da2ef5556398",
    "matlab/core/arm_mass_properties.m": "8ec66e107156b5219f7e41aca2464eef1ec8043eb7f67df313c0f23ef4b551f5",
    "matlab/core/distributed_mass_properties.m": "db380b506e4bacc37bc398d5726c5ebd25be8ebc08b6c9e76ff59bc78fd45d3a",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def check_hash(path: Path, expected: str) -> str:
    actual = sha256(path)
    if actual.lower() != expected.lower():
        raise RuntimeError(f"SHA256 mismatch for {path}: {actual} != {expected}")
    return actual


def mat_string(value) -> str:
    return str(np.asarray(value).item()).strip()


def main() -> None:
    if OUTPUT.exists():
        raise FileExistsError(f"refusing to overwrite {OUTPUT}")

    for key, path in {
        "input_lock_sha256": LOCK_PATH,
        "root_input_audit_sha256": AUDIT_PATH,
        "physical_equivalence_sha256": EQUIV_PATH,
        "matlab_reconstruction_sha256": RECON_PATH,
        "matlab_receipt_sha256": MATLAB_RECEIPT_PATH,
    }.items():
        check_hash(path, PINS[key])

    lock, audit = read_json(LOCK_PATH), read_json(AUDIT_PATH)
    equivalence = read_json(EQUIV_PATH)
    reconstruction = read_json(RECON_PATH)
    matlab_receipt = read_json(MATLAB_RECEIPT_PATH)
    assert audit["input_lock_sha256"] == PINS["input_lock_sha256"]
    assert audit["status"] == "PASS_INPUT_IDENTITY_AND_SELECTION_ONLY_NOT_FEATURE_OR_FIT_RELEASE"
    assert audit["TRAIN_scenes"] == audit["VAL_scenes"] == 48
    assert audit["actual_input_file_hashes_verified"] == 288
    assert audit["TEST_accessed"] is False
    assert equivalence["scene_count"] == 96
    assert equivalence["signature_counts"] == {
        "9e2a17aa588856e6184abe7e26e040f886ccc674058a1300350aa82cfb9023dd": 96
    }
    assert matlab_receipt["assertions_passed"] is True
    assert matlab_receipt["matlab_execution"]["os_exit_code"] == 0
    assert matlab_receipt["matlab_script_sha256"].lower() == PINS["matlab_script_sha256"]
    assert matlab_receipt["python_validator_sha256"].lower() == PINS["current_validator_source_sha256"]

    lock_sources = {x["path"]: x["sha256"].lower() for x in lock["feature_reconstruction_sources"]}
    replay_sources = {k: v.lower() for k, v in matlab_receipt["source_sha256"].items()}
    source_files = {}
    for rel, expected in CORE_SOURCE_SHA256.items():
        assert lock_sources[rel] == expected
        assert replay_sources[rel] == expected
        source_files[rel] = check_hash(ROOT / rel, expected)

    replay_by_id = {s["scene_id"]: s for s in reconstruction["scenes"]}
    assert set(replay_by_id) == {
        "DL1018_TRAIN_T1_C01_W00",
        "DL1018_VAL_T1_C01_W08",
    }
    assert all(s["replay_maxabs_error_rads2"] <= 1e-8 for s in reconstruction["scenes"])
    j0_values = [np.asarray(s["Jnom_kgm2"], dtype=np.float64) for s in reconstruction["scenes"]]
    assert np.array_equal(j0_values[0], j0_values[1])
    j0 = j0_values[0]
    jdot0 = np.zeros((3, 3), dtype=np.float64)

    eq_by_id = {x["scene_id"]: x for x in equivalence["rows"]}
    assert set(eq_by_id) == {s["scene_id"] for s in lock["scenes"]}
    assert len(lock["scenes"]) == 96

    scenes = []
    for locked in lock["scenes"]:
        scene_id, split = locked["scene_id"], locked["split"]
        files = {x["role"]: x for x in locked["files"]}
        start_rel = files["run_start"]["path"]
        start_path = ROOT / start_rel
        start_sha = check_hash(start_path, files["run_start"]["sha256"])
        run_start = loadmat(
            start_path, variable_names=["runStart"], squeeze_me=True, struct_as_record=False
        )["runStart"]
        cfg, plant = run_start.cfg, run_start.cfg.plant
        run_id = mat_string(run_start.run_id)
        collector_id, model_id = mat_string(run_start.collector_id), mat_string(run_start.model_id)
        morphology_mode = mat_string(cfg.controller_morphology_mode)
        derivative_mode = mat_string(cfg.controller_inertia_derivative_mode)
        arm_initial = np.asarray(plant.arm_initial, dtype=np.float64).reshape(-1)
        mass, kf, km = float(plant.mass), float(plant.kf), float(plant.km)
        row = eq_by_id[scene_id]
        assert run_id and scene_id in run_id
        assert collector_id == model_id == "B"
        assert morphology_mode == row["morphology_mode"] == "fixed"
        assert derivative_mode == row["inertia_derivative_mode"] == "full"
        assert row["physical_configuration_sha256"] == "9e2a17aa588856e6184abe7e26e040f886ccc674058a1300350aa82cfb9023dd"
        assert arm_initial.shape == (4,) and np.allclose(arm_initial, 0.15, rtol=0, atol=1e-15)
        assert np.isclose(mass, 0.695, rtol=0, atol=1e-15)
        assert np.isclose(kf, 1.7e-6, rtol=0, atol=1e-20)
        assert np.isclose(km, 3.2e-8, rtol=0, atol=1e-22)
        scenes.append({
            "scene_id": scene_id,
            "split": split,
            "run_id": run_id,
            "collector_id": collector_id,
            "model_id": model_id,
            "run_start_path": start_rel,
            "run_start_sha256": start_sha,
            "input_paths_locked_but_not_read": {
                role: {"path": files[role]["path"], "sha256": files[role]["sha256"]}
                for role in ("B_h5", "raw_run")
            },
            "physical_configuration_sha256": row["physical_configuration_sha256"],
            "morphology_mode": morphology_mode,
            "inertia_derivative_mode": derivative_mode,
            "arm_initial_m": arm_initial.tolist(),
            "mass_kg": mass,
            "kf_N_per_omega2": kf,
            "km_Nm_per_omega2": km,
            "J0_kg_m2": j0.tolist(),
            "Jdot0_for_bs_kg_m2_s": jdot0.tolist(),
        })

    assert sum(s["split"] == "TRAIN" for s in scenes) == 48
    assert sum(s["split"] == "VAL" for s in scenes) == 48
    assert len({tuple(np.asarray(s["J0_kg_m2"]).ravel().tolist()) for s in scenes}) == 1
    assert len({s["mass_kg"] for s in scenes}) == 1

    result = {
        "schema": "OFFLINE_INPUT_PROBE_NOMINAL_PARAMETERS_V1",
        "scene_lock_sha256": sha256(LOCK_PATH),
        "root_physical_configuration_sha256": sha256(EQUIV_PATH),
        "root_nonzero_pair_result_sha256": sha256(RECON_PATH),
        "matlab_reconstruction_receipt_sha256": sha256(MATLAB_RECEIPT_PATH),
        "source_files": [{"path": rel, "sha256": digest} for rel, digest in sorted(source_files.items())],
        "construction": {
            "controller_mode": "fixed",
            "J0_source": "Jnom_kgm2 from the two pinned offline MATLAB replays; exact matrices agree",
            "Jdot0_source": "zero 3x3 for the fixed nominal model with zero arm-rate input",
            "J0_replay_scenes": sorted(replay_by_id),
            "matlab_receipt_os_exit_code": 0,
            "raw_arrays_read": False,
            "H5_opened": False,
            "TEST_accessed": False,
            "runner_or_Plant_executed": False,
            "fit_executed": False,
        },
        "global_consistency": {
            "scene_count": len(scenes),
            "TRAIN_count": 48,
            "VAL_count": 48,
            "physical_configuration_signature_count": 1,
            "unique_J0_count": 1,
            "unique_mass_count": 1,
            "controller_mode": "fixed",
            "morphology_mode": "fixed",
            "inertia_derivative_mode": "full",
        },
        "scenes": scenes,
    }
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    main()
