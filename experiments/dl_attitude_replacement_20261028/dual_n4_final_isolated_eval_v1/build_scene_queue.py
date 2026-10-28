"""Freeze and build the independent dual-N4 evaluation scene queue; no runner is called."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
from pathlib import Path

import numpy as np
from scipy.io import loadmat, savemat


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DT = 0.001
DURATION_S = 20.0
ARM_INITIAL_M = [0.15] * 4
MORPH_SPEED_MPS = 0.05
MIN_HOLD_S = 5.0
REFERENCE_CONTRACT = "DL1018_SCENE_REF_FIG8_A2_V2"
SCENE_FIELDS = {
    "scene_id", "time", "initial_state", "reference", "arms",
    "environment_wind_I", "reference_contract_id",
}

TASKS = [
    {"task_code": "T1", "task": "HELIX"},
    {"task_code": "T2", "task": "FIG8_3D"},
    {"task_code": "T3", "task": "SQUARE"},
]
WIND_SPECTRA = [
    {"wind_class": "LOW", "meaning": "low-frequency / low-amplitude", "f1_hz": 0.23, "f2_hz": 0.43, "A1_mps": 1.2, "A2_mps": 0.8},
    {"wind_class": "MID", "meaning": "mid-frequency / mid-amplitude", "f1_hz": 0.63, "f2_hz": 0.96, "A1_mps": 3.0, "A2_mps": 2.1},
    {"wind_class": "HIGH", "meaning": "high-frequency / high-amplitude", "f1_hz": 1.35, "f2_hz": 2.05, "A1_mps": 4.2, "A2_mps": 3.1},
    {"wind_class": "CONSTANT", "meaning": "9 m/s after the fixed startup ramp", "f1_hz": 0.23, "f2_hz": 0.43, "A1_mps": 0.0, "A2_mps": 0.0},
    {"wind_class": "FREQ_SHIFT", "meaning": "prelisted frequency shift: 1.20x MID frequencies", "f1_hz": 0.756, "f2_hz": 1.152, "A1_mps": 3.0, "A2_mps": 2.1},
    {"wind_class": "AMP_SHIFT", "meaning": "prelisted amplitude shift: 1.25x MID amplitudes", "f1_hz": 0.63, "f2_hz": 0.96, "A1_mps": 3.75, "A2_mps": 2.625},
]
MORPHOLOGY = [
    {"morph_id": "M01", "topology": "12", "start_base_s": 5.8, "start_step_s": 0.0, "retract_base_s": 13.4, "retract_step_s": 0.0},
    {"morph_id": "M02", "topology": "24", "start_base_s": 5.4, "start_step_s": 0.3, "retract_base_s": 13.2, "retract_step_s": 0.2},
    {"morph_id": "M03", "topology": "123", "start_base_s": 6.1, "start_step_s": 0.15, "retract_base_s": 14.0, "retract_step_s": 0.15},
    {"morph_id": "M04", "topology": "1234", "start_base_s": 5.3, "start_step_s": 0.25, "retract_base_s": 13.6, "retract_step_s": 0.25},
]
TOPOLOGY_ARMS = {"12": [1, 2], "24": [2, 4], "123": [1, 2, 3], "1234": [1, 2, 3, 4]}
TARGET_LENGTHS_M = [0.18, 0.20, 0.22, 0.24]
SOURCE_CONTEXT = {
    "schema": "DUALN4_EVAL72_SOURCE_CONTEXT_V1",
    "reference_scene_id": "DL1018_DEV_T3_C05_W02",
    "reference_source_split": "TRAIN_C5_24 (canonical ID prefix DEV)",
    "parent_run_start_sha256": "4e27ddc7b459ec064dbdbbb960de69e22077645aee8c2e45df680f44386793fc",
    "parent_scene_payload_sha256": "614c72a7556260dbde87c7651c4bd210a526aa59f56976bba80455a17237bcf4",
    "cfg_field_used": "plant.arm_initial",
    "cfg_arm_initial_m": ARM_INITIAL_M,
    "cfg_arm_initial_canonical_sha256": "0f994fba30bdc9316f1f6f04266c2ff94e3c71997e22367f2732f349a82d6edb",
    "note": "Only scene geometry and arm initial lengths were used for source-shape validation; no model weights were loaded into this builder.",
}
BASE_CONFIG = {
    "schema": "DUALN4_EVAL72_GENERATOR_CONFIG_V1",
    "study_id": "dual_n4_final_isolated_eval_v1",
    "id_namespace": "DUALN4_EVAL72_V1",
    "duration_s": DURATION_S,
    "dt_s": DT,
    "state_samples": int(round(DURATION_S / DT)) + 1,
    "reference_contract_id": REFERENCE_CONTRACT,
    "wind": {"model": "biased_dual_sine", "V0_mps": 9.0, "rise_time_s": 0.8, "rho_air_kg_m3": 1.225, "CdBody": 1.0, "CdArm": 1.0},
    "wind_spectra": WIND_SPECTRA,
    "morphology": {"variants": MORPHOLOGY, "topology_arms": TOPOLOGY_ARMS, "target_lengths_m": TARGET_LENGTHS_M, "morph_speed_mps": MORPH_SPEED_MPS, "minimum_hold_s": MIN_HOLD_S, "retract": True},
    "seed_rule": "2026102800 + 10000*task_index + 100*wind_index + morphology_index; NumPy PCG64",
    "controller_input_policy": {
        "environment_wind_exposed_to_controller": False,
        "model_weights_in_scene_payload": False,
        "future_samples_exposed_to_controller": False,
        "environment_wind_role": "Plant environment only; consumers must keep it outside controller inputs.",
    },
}


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_frozen_json(path: Path, value: object) -> None:
    data = canonical_json(value)
    if path.exists():
        if path.read_bytes() != data:
            raise RuntimeError(f"Refusing to change frozen file: {path.name}")
        return
    path.write_bytes(data)


def make_specs() -> list[dict]:
    specs = []
    for ti, task in enumerate(TASKS):
        for wi, wind in enumerate(WIND_SPECTRA):
            for mi, morph in enumerate(MORPHOLOGY):
                seed = 2026102800 + 10000 * ti + 100 * wi + mi
                rng = np.random.default_rng(seed)
                phase1, phase2 = rng.uniform(0.0, 2.0 * math.pi, size=2)
                azimuth = rng.uniform(0.0, 360.0)
                elevation = rng.uniform(-18.0, 18.0)
                arms = TOPOLOGY_ARMS[morph["topology"]]
                targets = [None] * 4
                starts = [None] * 4
                retracts = [None] * 4
                for q, arm in enumerate(arms):
                    targets[arm - 1] = TARGET_LENGTHS_M[(arm - 1 + mi) % len(TARGET_LENGTHS_M)]
                    starts[arm - 1] = morph["start_base_s"] + q * morph["start_step_s"]
                    retracts[arm - 1] = morph["retract_base_s"] + q * morph["retract_step_s"]
                    travel_s = (targets[arm - 1] - ARM_INITIAL_M[arm - 1]) / MORPH_SPEED_MPS
                    assert retracts[arm - 1] - starts[arm - 1] - travel_s >= MIN_HOLD_S
                spec_id = f"DUALN4_EVAL72_V1_{task['task_code']}_{wind['wind_class']}_{morph['morph_id']}"
                specs.append({
                    "scene_id": spec_id,
                    "task_code": task["task_code"],
                    "task": task["task"],
                    "wind_class": wind["wind_class"],
                    "morph_id": morph["morph_id"],
                    "seed": seed,
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
                        "morph_speed_mps": MORPH_SPEED_MPS, "minimum_hold_s": MIN_HOLD_S,
                    },
                    "payload_path": f"payloads/{spec_id}.mat",
                })
    assert len(specs) == 72 and len({s["scene_id"] for s in specs}) == 72
    assert len({s["seed"] for s in specs}) == 72
    assert len({s["wind"]["direction_azimuth_deg"] for s in specs}) == 72
    assert len({(s["wind"]["phi1_rad"], s["wind"]["phi2_rad"]) for s in specs}) == 72
    assert all(sum(s["wind_class"] == w["wind_class"] for s in specs) == 12 for w in WIND_SPECTRA)
    assert all(sum(s["morph_id"] == m["morph_id"] for s in specs) == 18 for m in MORPHOLOGY)
    return specs


def make_reference(task: str, time: np.ndarray) -> dict[str, np.ndarray]:
    t = time.reshape(-1)
    s = np.clip(t / DURATION_S, 0.0, 1.0)
    u = 10 * s**3 - 15 * s**4 + 6 * s**5
    ud = (30 * s**2 - 60 * s**3 + 30 * s**4) / DURATION_S
    udd = (60 * s - 180 * s**2 + 120 * s**3) / (DURATION_S**2)
    if task == "HELIX":
        theta = 3 * math.pi * u
        p = np.column_stack((1.2 * (np.cos(theta) - 1), 1.2 * np.sin(theta), 2 * u))
        pu = np.column_stack((-3.6 * math.pi * np.sin(theta), 3.6 * math.pi * np.cos(theta), np.full_like(t, 2.0)))
        puu = np.column_stack((-10.8 * math.pi**2 * np.cos(theta), -10.8 * math.pi**2 * np.sin(theta), np.zeros_like(t)))
        v, a = pu * ud[:, None], puu * (ud**2)[:, None] + pu * udd[:, None]
    elif task == "FIG8_3D":
        theta = 2 * math.pi * u
        p = np.column_stack((1.5 * np.sin(theta), np.sin(2 * theta), 0.4 * u + 0.35 * (1 - np.cos(2 * theta))))
        pu = np.column_stack((3 * math.pi * np.cos(theta), 4 * math.pi * np.cos(2 * theta), 0.4 + 1.4 * math.pi * np.sin(2 * theta)))
        puu = np.column_stack((-6 * math.pi**2 * np.sin(theta), -16 * math.pi**2 * np.sin(2 * theta), 5.6 * math.pi**2 * np.cos(2 * theta)))
        v, a = pu * ud[:, None], puu * (ud**2)[:, None] + pu * udd[:, None]
    elif task == "SQUARE":
        points = np.array([[0, 0, 0], [2, 0, 0], [2, 2, 0], [0, 2, 0], [0, 0, 0]], dtype=float)
        segment = np.minimum(np.floor(t / 5).astype(int), 3)
        p, v, a = (np.zeros((len(t), 3), dtype=float) for _ in range(3))
        for i in range(4):
            mask = segment == i
            u_seg = np.clip((t[mask] - 5 * i) / 5, 0.0, 1.0)
            h = 10 * u_seg**3 - 15 * u_seg**4 + 6 * u_seg**5
            hd = 30 * u_seg**2 - 60 * u_seg**3 + 30 * u_seg**4
            hdd = 60 * u_seg - 180 * u_seg**2 + 120 * u_seg**3
            delta = points[i + 1] - points[i]
            p[mask] = points[i] + h[:, None] * delta
            v[mask] = hd[:, None] * delta / 5
            a[mask] = hdd[:, None] * delta / 25
    else:
        raise ValueError(f"Unknown task: {task}")
    return {
        "position": p, "velocity": v, "acceleration": a,
        "yaw": np.zeros((len(t), 1)), "yaw_rate": np.zeros((len(t), 1)),
        "yaw_acceleration": np.zeros((len(t), 1)),
    }


def make_morphology(spec: dict, time: np.ndarray) -> dict[str, np.ndarray]:
    n = len(time)
    meta = spec["morphology"]
    target = np.asarray([v if v is not None else 0.15 for v in meta["target_arm_lengths_m"]], dtype=float)
    starts = meta["start_time_s"]
    retracts = meta["retract_start_time_s"]
    active = np.asarray(meta["active_arms"], dtype=int) - 1
    rho = np.asarray(ARM_INITIAL_M, dtype=float)
    command = np.zeros((n, 4), dtype=float)
    rho_true = np.empty((n, 4), dtype=float)
    rho_dot_true = np.zeros((n, 4), dtype=float)
    for k, now in enumerate(time):
        for arm in active:
            start = starts[int(arm)]
            retract = retracts[int(arm)]
            if now < start:
                rate = 0.0
            elif now >= retract:
                rate = -MORPH_SPEED_MPS if rho[arm] > 0.15 + 1e-12 else 0.0
            else:
                rate = MORPH_SPEED_MPS if rho[arm] < target[arm] - 1e-12 else 0.0
            rho_dot_true[k, arm] = rate
            command[k, arm] = rate / MORPH_SPEED_MPS
        rho_true[k] = rho
        rho = np.clip(rho + DT * rho_dot_true[k], 0.15, 0.25)
    return {
        "command": command, "rho_true": rho_true, "rhoDot_true": rho_dot_true,
        "rho_hat": np.tile(np.asarray(ARM_INITIAL_M), (n, 1)),
        "rhoDot_hat": np.zeros((n, 4), dtype=float),
    }


def make_scene(spec: dict) -> dict:
    time = np.arange(round(DURATION_S / DT) + 1, dtype=float) * DT
    w = spec["wind"]
    az, el = math.radians(w["direction_azimuth_deg"]), math.radians(w["direction_elevation_deg"])
    direction = np.array([math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)], dtype=float)
    direction /= np.linalg.norm(direction)
    low = w["A1_mps"] * np.sin(2 * math.pi * w["f1_hz"] * time + w["phi1_rad"])
    high = w["A2_mps"] * np.sin(2 * math.pi * w["f2_hz"] * time + w["phi2_rad"])
    beta = np.ones_like(time)
    rising = time < w["rise_time_s"]
    beta[rising] = 0.5 * (1 - np.cos(math.pi * time[rising] / w["rise_time_s"]))
    speed = beta * (w["V0_mps"] + low + high)
    scene = {
        "scene_id": spec["scene_id"], "time": time[:, None],
        "initial_state": np.zeros((12, 1), dtype=float),
        "reference": make_reference(spec["task"], time),
        "arms": make_morphology(spec, time),
        "environment_wind_I": speed[:, None] * direction[None, :],
        "reference_contract_id": REFERENCE_CONTRACT,
    }
    validate_scene(scene, spec, time, direction)
    return scene


def validate_scene(scene: dict, spec: dict, time: np.ndarray, direction: np.ndarray) -> None:
    n = len(time)
    assert set(scene) == SCENE_FIELDS
    assert scene["scene_id"] == spec["scene_id"] and scene["reference_contract_id"] == REFERENCE_CONTRACT
    assert scene["time"].shape == (n, 1) and scene["initial_state"].shape == (12, 1)
    assert np.all(np.isfinite(scene["time"])) and np.all(np.diff(scene["time"], axis=0) > 0)
    assert np.allclose(scene["time"][:, 0], time) and np.all(scene["initial_state"] == 0)
    for key in ("position", "velocity", "acceleration"):
        assert scene["reference"][key].shape == (n, 3) and np.all(np.isfinite(scene["reference"][key]))
    for key in ("yaw", "yaw_rate", "yaw_acceleration"):
        assert scene["reference"][key].shape == (n, 1) and np.all(scene["reference"][key] == 0)
    assert scene["arms"].keys() == {"command", "rho_true", "rhoDot_true", "rho_hat", "rhoDot_hat"}
    for value in scene["arms"].values():
        assert value.shape == (n, 4) and np.all(np.isfinite(value))
    assert np.min(scene["arms"]["rho_true"]) >= 0.15 - 1e-12
    assert np.max(scene["arms"]["rho_true"]) <= 0.25 + 1e-12
    assert np.max(np.abs(scene["arms"]["rhoDot_true"])) <= MORPH_SPEED_MPS + 1e-12
    assert np.allclose(scene["arms"]["rho_true"][0], ARM_INITIAL_M)
    assert np.allclose(scene["arms"]["rho_true"][-1], ARM_INITIAL_M)
    assert np.allclose(scene["arms"]["rho_hat"], ARM_INITIAL_M)
    assert np.all(scene["arms"]["rhoDot_hat"] == 0)
    wind = scene["environment_wind_I"]
    assert wind.shape == (n, 3) and np.all(np.isfinite(wind))
    assert np.isclose(np.linalg.norm(direction), 1.0) and spec["wind"]["f1_hz"] > 0 and spec["wind"]["f2_hz"] > 0
    assert spec["wind"]["f1_hz"] != spec["wind"]["f2_hz"]
    w = spec["wind"]
    beta = np.ones(n)
    ramp = time < w["rise_time_s"]
    beta[ramp] = 0.5 * (1 - np.cos(math.pi * time[ramp] / w["rise_time_s"]))
    speed = beta * (w["V0_mps"] + w["A1_mps"] * np.sin(2 * math.pi * w["f1_hz"] * time + w["phi1_rad"])
                    + w["A2_mps"] * np.sin(2 * math.pi * w["f2_hz"] * time + w["phi2_rad"]))
    assert np.allclose(wind, speed[:, None] * direction[None, :])
    roll, pitch, yaw = scene["initial_state"][6:9, 0]
    cr, sr, cp, sp, cy, sy = np.cos(roll), np.sin(roll), np.cos(pitch), np.sin(pitch), np.cos(yaw), np.sin(yaw)
    rotation = np.array([[cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
                         [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
                         [-sp, cp * sr, cp * cr]])
    assert np.allclose(rotation.T @ rotation, np.eye(3)) and np.isclose(np.linalg.det(rotation), 1.0)


def write_mat(path: Path, scene: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".mat", delete=False) as temp:
        temp_path = Path(temp.name)
    try:
        savemat(temp_path, {"scene": scene}, do_compression=True, oned_as="column", format="5")
        header = b"MATLAB 5.0 MAT-file, Frozen DUALN4_EVAL72 scene payload v1".ljust(116, b" ")
        with temp_path.open("r+b") as stream:
            stream.write(header)
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def validate_saved_mat(path: Path, spec: dict, expected: dict | None = None) -> None:
    data = loadmat(path, variable_names=["scene"], squeeze_me=False, struct_as_record=False)
    saved = data["scene"][0, 0]
    reference = saved.reference[0, 0]
    arms = saved.arms[0, 0]
    n = int(round(DURATION_S / DT)) + 1
    assert str(saved.scene_id[0]) == spec["scene_id"]
    assert saved.time.shape == (n, 1) and saved.initial_state.shape == (12, 1)
    assert reference.position.shape == (n, 3)
    assert reference.velocity.shape == (n, 3)
    assert reference.acceleration.shape == (n, 3)
    assert arms.rho_true.shape == (n, 4) and arms.rho_hat.shape == (n, 4)
    assert saved.environment_wind_I.shape == (n, 3)
    for values in (saved.time, saved.initial_state, saved.environment_wind_I,
                   reference.position, reference.velocity, reference.acceleration,
                   arms.command, arms.rho_true, arms.rhoDot_true,
                   arms.rho_hat, arms.rhoDot_hat):
        assert np.all(np.isfinite(values))
    if expected is not None:
        assert np.array_equal(saved.time, expected["time"])
        assert np.array_equal(saved.initial_state, expected["initial_state"])
        assert np.array_equal(saved.environment_wind_I, expected["environment_wind_I"])
        for key in ("position", "velocity", "acceleration", "yaw", "yaw_rate", "yaw_acceleration"):
            assert np.array_equal(getattr(reference, key), expected["reference"][key])
        for key in ("command", "rho_true", "rhoDot_true", "rho_hat", "rhoDot_hat"):
            assert np.array_equal(getattr(arms, key), expected["arms"][key])


def input_hashes() -> dict[str, str]:
    paths = {
        "run_comparison.m": ROOT / "run_comparison.m",
        "make_paired_dev58_scene.m": ROOT / "experiments/dl_attitude_replacement_20261028/causal_n4_gate_train24_batch_v2/candidate_runner_work/matlab/scenes/make_paired_dev58_scene.m",
        "wind_velocity_profile.m": ROOT / "experiments/dl_attitude_replacement_20261028/causal_n4_gate_train24_batch_v2/candidate_runner_work/matlab/core/wind_velocity_profile.m",
        "tcn0916_morphology_scenario.m": ROOT / "experiments/dl_attitude_replacement_20261028/causal_n4_gate_train24_batch_v2/candidate_runner_work/matlab/core/tcn0916_morphology_scenario.m",
        "tcn0916_topologies.m": ROOT / "experiments/dl_attitude_replacement_20261028/causal_n4_gate_train24_batch_v2/candidate_runner_work/matlab/core/tcn0916_topologies.m",
    }
    return {name: sha256_file(path) for name, path in paths.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload-limit", type=int, default=1, help="Build this many payloads from the frozen 72-spec list; use 0 for source-only checks, 72 for the full queue.")
    args = parser.parse_args()
    if not 0 <= args.payload_limit <= 72:
        parser.error("--payload-limit must be between 0 and 72")

    specs = make_specs()
    config_path = HERE / "GENERATOR_CONFIG_v1.json"
    specs_path = HERE / "SCENE_SPECS_v1.json"
    context_path = HERE / "SOURCE_CONTEXT_v1.json"
    write_frozen_json(config_path, BASE_CONFIG)
    write_frozen_json(context_path, SOURCE_CONTEXT)
    write_frozen_json(specs_path, {
        "schema": "DUALN4_EVAL72_SCENE_SPECS_V1",
        "status": "FROZEN_PENDING_CANDIDATE_SEAL",
        "study_id": BASE_CONFIG["study_id"],
        "spec_count": len(specs),
        "task_count": len(TASKS),
        "wind_spectrum_count": len(WIND_SPECTRA),
        "morphology_schedule_count": len(MORPHOLOGY),
        "controller_input_policy": BASE_CONFIG["controller_input_policy"],
        "cases": specs,
    })

    payload_dir = HERE / "payloads"
    payload_dir.mkdir(exist_ok=True)
    for spec in specs[:args.payload_limit]:
        path = HERE / spec["payload_path"]
        scene = make_scene(spec)
        if path.exists():
            validate_saved_mat(path, spec, scene)
        else:
            write_mat(path, scene)
            validate_saved_mat(path, spec, scene)

    expected_payloads = {s["scene_id"] + ".mat": HERE / s["payload_path"] for s in specs}
    payload_hashes = {name: sha256_file(path) for name, path in expected_payloads.items() if path.exists()}
    source_hashes = input_hashes()
    script_hash = sha256_file(Path(__file__))
    source_lock = {
        "schema": "DUALN4_EVAL72_SOURCE_LOCK_V1",
        "status": "FROZEN_SCENES_PENDING_CANDIDATE_FREEZE",
        "spec_sha256": sha256_file(specs_path),
        "generator_config_sha256": sha256_file(config_path),
        "source_context_sha256": sha256_file(context_path),
        "builder_sha256": script_hash,
        "formula_source_sha256": source_hashes,
        "payload_sha256": payload_hashes,
        "controller_input_policy": BASE_CONFIG["controller_input_policy"],
        "Plant_calls": 0,
        "controller_calls": 0,
        "score_calls": 0,
        "modified_current_batch": False,
    }
    (HERE / "SOURCE_LOCK_v1.json").write_bytes(canonical_json(source_lock))
    audit = {
        "schema": "DUALN4_EVAL72_GENERATION_AUDIT_V1",
        "status": "PASS_SOURCE_ONLY" if not payload_hashes else ("PASS_FULL_PAYLOADS" if len(payload_hashes) == 72 else "PASS_SINGLE_SCENE_SOURCE_VALIDATION"),
        "frozen_spec_count": len(specs),
        "generated_payload_count": len(payload_hashes),
        "requested_payload_limit": args.payload_limit,
        "sample_shape": {"time_samples": 20001, "dt_s": DT, "duration_s": DURATION_S, "initial_state": [12, 1], "wind": [20001, 3], "reference_xyz": [20001, 3], "arms": [20001, 4]},
        "data_validation": "finite arrays, scene schema, morphology bounds/speed/hold, unit wind direction, and proper initial rotation",
        "Plant_calls": 0,
        "controller_calls": 0,
        "score_calls": 0,
        "modified_current_batch": False,
    }
    (HERE / "GENERATION_AUDIT_v1.json").write_bytes(canonical_json(audit))
    print(json.dumps({"status": audit["status"], "spec_count": len(specs), "payload_count": len(payload_hashes), "spec_sha256": source_lock["spec_sha256"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
