#!/usr/bin/env python3
"""Read-only same-state replay of the pinned VAL W15 controller chain."""
from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path

import h5py
import numpy as np


ROOT = Path(__file__).resolve().parents[3]
HELPER = ROOT / "reports" / "paper14_v2" / "phase1" / "audit_w15_position_replay.py"
HELPER_SHA256 = "372d92cb17da99884e742d3fa0c877200c3bb2bc6fac7f10e7a1a046b97a76af"
TOL = 1e-12
SOURCE_SHA256 = {
    "matlab/core/baseline_force_to_attitude.m": "ef42d1d08af24ed82da307a4d886b0c205e28e754177765a2584e3e9bb0cd039",
    "matlab/core/command_filter_step.m": "15c7eb27162e1971a1164304830f4afd3af35eb9bd709291e969dbfefd0d262b",
    "matlab/core/attitude_bs_step.m": "cf6b20ffc4df2625d9316a80340d69542e380d14feaed66ef8498e793fdaccbc",
    "matlab/core/allocate_control.m": "5ac26d8c5ba6243f755bcf6ad3a07e98e503c213e4c95edbee7dd2c2627f3d53",
    "matlab/core/controller_parameters.m": "4fad5e78c0bd4177461647af167e7c86a7defa628b43d523b0b7da2ef5556398",
    "matlab/core/simulation_parameters.m": "962b5434c23d5ac1a9ac568f136635a8ea651a775165d84b7d95250ca88bb9ae",
    "matlab/core/arm_mass_properties.m": "8ec66e107156b5219f7e41aca2464eef1ec8043eb7f67df313c0f23ef4b551f5",
    "matlab/core/distributed_mass_properties.m": "db380b506e4bacc37bc398d5726c5ebd25be8ebc08b6c9e76ff59bc78fd45d3a",
    "matlab/core/allocation_matrix.m": "5886c00b3f8800301a324159e534b4c65e857cdd00392a3231af22c6dbba517d",
    "matlab/core/arm_directions.m": "517bbfcd0df9526b189f64bff067a49551f573ad96e682ee005533ab510e686c",
    "matlab/runtime/run_dl1018_closed_loop.m": "20913227a365a78e759e5f4f8ba8e91d3f4ac2a5899927ac03e9d707b9b5c0a3",
    "experiments/paper14_v2_round3_xy_pcf_screen/runtime/run_dl1018_closed_loop.m": "86e7f7ec42492341e58daf30879f7aec9153924e80a76f6f029fce2a628c38d9",
    "experiments/paper14_v2_round3_xy_pcf_screen/runtime/run_episode_dl1018.m": "fcc1f5de659541e692483f8395d93fd2a251256286ebade5e510ed4c7a2e2330",
    "experiments/paper14_v2_round3_xy_pcf_screen/runtime/position_stage1_model_forward_v2.m": "dc803aa102c49d67dd687ae941f8a60bb0c465f74fd01e5ae93ad1ea1a293676",
    "experiments/paper14_v2_round3_xy_pcf_screen/runtime/position_only_search_head_step.m": "3bd0fe9686c3b75793575e517d4cc5f08de58ab6a26a2bc7516aa690422bb7dc",
    "experiments/paper14_v2_round3_xy_pcf_screen/runtime/position_only_search_options.m": "4e8322934ddb524961fa762426800564f6c758e00b943b622c9143ed734f19bf",
    "experiments/paper14_v2_round3_xy_pcf_screen/runtime/controller_options_dl1018.m": "93633a5fd95f73d33982045c2fa372d49b1a0df8ea0cfb5ca4461208ca9d53b1",
    "experiments/paper14_v2_round3_xy_pcf_screen/runtime/position_filter_realization_pcf_step_v3_5.m": "b4ae22db5bd444a162d0cd01a3a59a589f2e37077b089bb33693401b660228d0",
}
R3_PLANT_IDENTITY_SHA256 = {
    "allocate_control": "5ac26d8c5ba6243f755bcf6ad3a07e98e503c213e4c95edbee7dd2c2627f3d53",
    "allocation_matrix": "5886c00b3f8800301a324159e534b4c65e857cdd00392a3231af22c6dbba517d",
    "arm_directions": "517bbfcd0df9526b189f64bff067a49551f573ad96e682ee005533ab510e686c",
    "arm_mass_properties": "8ec66e107156b5219f7e41aca2464eef1ec8043eb7f67df313c0f23ef4b551f5",
    "attitude_bs_step": "cf6b20ffc4df2625d9316a80340d69542e380d14feaed66ef8498e793fdaccbc",
    "baseline_force_to_attitude": "ef42d1d08af24ed82da307a4d886b0c205e28e754177765a2584e3e9bb0cd039",
    "command_filter_step": "15c7eb27162e1971a1164304830f4afd3af35eb9bd709291e969dbfefd0d262b",
    "controller_parameters": "4fad5e78c0bd4177461647af167e7c86a7defa628b43d523b0b7da2ef5556398",
    "distributed_mass_properties": "db380b506e4bacc37bc398d5726c5ebd25be8ebc08b6c9e76ff59bc78fd45d3a",
    "simulation_parameters": "962b5434c23d5ac1a9ac568f136635a8ea651a775165d84b7d95250ca88bb9ae",
}
FIELDS = (
    "position_commanded_force_N",
    "position_bs_nominal_force_N",
    "position_compensation_applied_force_N",
    "raw_outer_attitude",
    "command_filter_target_euler",
    "command_filter_acceleration_request_unclamped_rads2",
    "command_filter_acceleration_applied_rads2",
    "filtered_attitude_reference",
    "filtered_attitude_rate",
    "attitude_bs_nominal_torque_Nm",
    "attitude_compensation_applied_torque_Nm",
    "requested_generalized",
    "controller_clipped_generalized",
    "generalized_clipped",
    "allocated_generalized",
    "motor_squared_requested",
    "motor_setpoint",
    "motor_command",
    "motor_saturated",
    "tilt_limited",
)


spec = importlib.util.spec_from_file_location("position_replay", HELPER)
if spec is None or spec.loader is None:
    raise RuntimeError("cannot load the pinned position replay helper")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def checked_error(actual: np.ndarray, expected: np.ndarray, label: str, tol: float = TOL) -> float:
    actual = np.asarray(actual, dtype=np.float64)
    expected = np.asarray(expected, dtype=np.float64)
    require(actual.shape == expected.shape, f"{label}: shape {actual.shape} != {expected.shape}")
    error = float(np.max(np.abs(actual - expected))) if actual.size else 0.0
    require(error <= tol, f"{label}: max error {error:.17g} exceeds {tol:.3g}")
    return error


def scalar(cfg: dict, path: str) -> float:
    return float(audit.get_path(cfg, path)[0])


def vector(cfg: dict, path: str) -> np.ndarray:
    return audit.get_path(cfg, path)


def nested(cfg: dict, path: str):
    value = cfg
    for key in path.split("/"):
        value = value[key]
    return value


def cuboid(mass: float, length: float, width: float, height: float) -> np.ndarray:
    return mass / 12 * np.diag([width**2 + height**2, length**2 + height**2, length**2 + width**2])


def cylinder(mass: float, radius: float, height: float) -> np.ndarray:
    return np.diag([
        mass / 12 * (3 * radius**2 + height**2),
        mass / 12 * (3 * radius**2 + height**2),
        0.5 * mass * radius**2,
    ])


def fixed_controller_mass_properties(cfg: dict) -> tuple[np.ndarray, np.ndarray]:
    """Mirror distributed_mass_properties for fixed nominal arms with zero arm rates."""
    plant = nested(cfg, "plant")
    masses = plant["component_masses"]
    dims = plant["component_dimensions"]
    arms = vector(cfg, "plant/arm_initial")
    angles = vector(cfg, "plant/arm_angles")
    dirs = np.vstack([np.cos(angles), np.sin(angles), np.zeros(4)])
    root = scalar(cfg, "plant/arm_root_radius")
    m_total = scalar(cfg, "plant/mass")
    positions = {
        "body": np.zeros((3, 1)),
        "battery": np.zeros((3, 1)),
        "arm": dirs * (0.5 * (root + arms))[None, :],
        "motor": dirs * arms[None, :],
        "rotor": dirs * arms[None, :],
        "servo": dirs * (root + 0.5 * scalar(cfg, "plant/component_dimensions/servo/length")),
    }
    cog = sum(float(masses[name][0][0]) * np.sum(pos, axis=1) for name, pos in positions.items()) / m_total

    inertia = np.zeros((3, 3))
    I3 = np.eye(3)
    for name, mass0 in (("body", 1), ("battery", 1)):
        mass = float(masses[name][0][0])
        local = cuboid(mass, scalar(cfg, "plant/component_dimensions/body/length"),
                       scalar(cfg, "plant/component_dimensions/body/width"),
                       scalar(cfg, "plant/component_dimensions/body/height")) if name == "body" else np.zeros((3, 3))
        r = positions[name][:, 0] - cog
        inertia += local + mass * ((r @ r) * I3 - np.outer(r, r))
    for i, angle in enumerate(angles):
        rotation = np.array([[np.cos(angle), -np.sin(angle), 0], [np.sin(angle), np.cos(angle), 0], [0, 0, 1]])
        components = (
            ("arm", cuboid(float(masses["arm"][0][0]), arms[i] - root,
                            scalar(cfg, "plant/component_dimensions/arm/width"),
                            scalar(cfg, "plant/component_dimensions/arm/height")), rotation),
            ("motor", cylinder(float(masses["motor"][0][0]),
                                scalar(cfg, "plant/component_dimensions/motor/radius"),
                                scalar(cfg, "plant/component_dimensions/motor/height")), I3),
            ("rotor", cylinder(float(masses["rotor"][0][0]),
                                scalar(cfg, "plant/component_dimensions/rotor/inertia_equivalent_radius"),
                                scalar(cfg, "plant/component_dimensions/rotor/height")), I3),
            ("servo", cuboid(float(masses["servo"][0][0]),
                             scalar(cfg, "plant/component_dimensions/servo/length"),
                             scalar(cfg, "plant/component_dimensions/servo/width"),
                             scalar(cfg, "plant/component_dimensions/servo/height")), rotation),
        )
        for name, local0, rot in components:
            local = rot @ local0 @ rot.T
            r = positions[name][:, i] - cog
            inertia += local + float(masses[name][0][0]) * ((r @ r) * I3 - np.outer(r, r))
    return 0.5 * (inertia + inertia.T), cog


def allocation_matrix(cfg: dict, cog: np.ndarray) -> np.ndarray:
    arm_lengths = vector(cfg, "plant/arm_initial")
    angles = vector(cfg, "plant/arm_angles")
    directions = np.vstack([np.cos(angles), np.sin(angles), np.zeros(4)])
    relative = directions * arm_lengths[None, :] - cog[:, None]
    kf, km = scalar(cfg, "plant/kf"), scalar(cfg, "plant/km")
    C = np.zeros((4, 4))
    C[0, :] = kf
    C[1, :] = kf * relative[1, :]
    C[2, :] = -kf * relative[0, :]
    C[3, :] = km * np.array([1, -1, 1, -1])
    return C


def euler_kinematics(eta: np.ndarray, omega: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    phi = eta[0]
    theta = max(min(eta[1], math.pi / 2 - 1e-4), -math.pi / 2 + 1e-4)
    T = np.array([
        [1, math.sin(phi) * math.tan(theta), math.cos(phi) * math.tan(theta)],
        [0, math.cos(phi), -math.sin(phi)],
        [0, math.sin(phi) / math.cos(theta), math.cos(phi) / math.cos(theta)],
    ])
    eta_rate = T @ omega
    sphi, cphi = math.sin(phi), math.cos(phi)
    ttheta, sectheta = math.tan(theta), 1 / math.cos(theta)
    Tphi = np.array([[0, cphi * ttheta, -sphi * ttheta], [0, -sphi, -cphi],
                     [0, cphi * sectheta, -sphi * sectheta]])
    Ttheta = np.array([[0, sphi * sectheta**2, cphi * sectheta**2], [0, 0, 0],
                       [0, sphi * sectheta * ttheta, cphi * sectheta * ttheta]])
    Tdot = Tphi * eta_rate[0] + Ttheta * eta_rate[1]
    return T, Tdot


def wrap(x: np.ndarray) -> np.ndarray:
    return np.arctan2(np.sin(x), np.cos(x))


def controller_replay(cfg: dict, state: np.ndarray, force: np.ndarray, yaw_reference: float,
                      filtered_eta: np.ndarray, filtered_rate: np.ndarray,
                      filter_acceleration: np.ndarray, attitude_compensation: np.ndarray) -> dict:
    mass, gravity = scalar(cfg, "plant/mass"), scalar(cfg, "plant/g")
    accel = force / mass
    yaw_state = float(state[8])
    specific = accel + np.array([0.0, 0.0, gravity])
    A = math.cos(yaw_state) * specific[0] + math.sin(yaw_state) * specific[1]
    B = math.sin(yaw_state) * specific[0] - math.cos(yaw_state) * specific[1]
    euler = np.array([math.atan2(B, math.hypot(specific[2], A)),
                      math.atan2(A, specific[2]), yaw_reference])
    tilt = float(np.hypot(euler[0], euler[1]))
    max_tilt = scalar(cfg, "control/limits/max_tilt")
    tilt_limited = tilt > max_tilt
    if tilt_limited:
        euler[:2] *= max_tilt / tilt
    thrust = mass * float(np.linalg.norm(specific))

    wn = vector(cfg, "control/command_filter/wn")
    zeta = vector(cfg, "control/command_filter/damping")
    request = wn**2 * wrap(euler - filtered_eta) - 2 * zeta * wn * filtered_rate
    limit = vector(cfg, "control/command_filter/acceleration_limit")
    applied_accel = np.minimum(np.maximum(request, -limit), limit)

    inertia, cog = fixed_controller_mass_properties(cfg)
    eta, omega = state[6:9], state[9:12]
    T, Tdot = euler_kinematics(eta, omega)
    eta_rate = T @ omega
    error = wrap(filtered_eta - eta)
    rate_error = filtered_rate - eta_rate
    k1 = vector(cfg, "control/bs/attitude/k1")
    k2 = vector(cfg, "control/bs/attitude/k2")
    alpha = filtered_rate + k1 * error
    surface = alpha - eta_rate
    alpha_dot = applied_accel + k1 * rate_error
    eta_accel = alpha_dot + error + k2 * surface
    body_accel = np.linalg.solve(T, eta_accel - Tdot @ omega)
    nominal_torque = inertia @ body_accel + np.cross(omega, inertia @ omega)

    requested = np.concatenate([[thrust], nominal_torque - attitude_compensation])
    limits_min = vector(cfg, "plant/limits/generalized_min")
    limits_max = vector(cfg, "plant/limits/generalized_max")
    clipped = np.minimum(np.maximum(requested, limits_min), limits_max)
    C = allocation_matrix(cfg, cog)
    motor_squared = np.linalg.solve(C, clipped)
    motor = np.sqrt(np.maximum(motor_squared, 0))
    motor_min = scalar(cfg, "plant/limits/motor_min")
    motor_max = scalar(cfg, "plant/limits/motor_max")
    motor = np.minimum(np.maximum(motor, motor_min), motor_max)
    allocated = C @ (motor**2)
    return {
        "target_euler": euler,
        "thrust": thrust,
        "filter_request": request,
        "filter_applied": applied_accel,
        "nominal_torque": nominal_torque,
        "requested_generalized": requested,
        "clipped_generalized": clipped,
        "motor_squared_requested": motor_squared,
        "motor_setpoint": motor,
        "allocated_generalized": allocated,
        "tilt_limited": tilt_limited,
        "inertia": inertia,
        "allocation_matrix": C,
    }


def matlab_cell_strings(group, name: str) -> list[str]:
    refs = np.transpose(np.asarray(group[name][()]))
    values = []
    for ref in refs.flat:
        if not ref:
            continue
        item = audit.h5_tree(group.file[ref])
        require(isinstance(item, tuple) and item[0] == "__matlab_char__",
                f"{name} cell does not contain a MATLAB char array")
        values.append(str(item[2]))
    return values


def main() -> None:
    require(audit.sha256(HELPER) == HELPER_SHA256, "pinned helper SHA mismatch")
    input_hashes = {}
    for relative, expected in audit.INPUT_TABLE_SHA256.items():
        actual = audit.sha256(ROOT / relative)
        require(actual == expected, f"locked input-table SHA mismatch: {relative}")
        input_hashes[relative] = actual
    source_hashes = {}
    for relative, expected in {**audit.SOURCE_SHA256, **SOURCE_SHA256}.items():
        actual = audit.sha256(ROOT / relative)
        require(actual == expected, f"source SHA mismatch: {relative}")
        source_hashes[relative] = actual

    phase1 = ROOT / "reports" / "paper14_v2" / "phase1"
    r3_reports = ROOT / "experiments" / "paper14_v2_round3_xy_pcf_screen" / "reports"
    candidate_rows = audit.rows(phase1 / "candidate_dssm_raw_rescore.csv")
    baseline_rows = audit.rows(phase1 / "baseline_b_raw_rescore.csv")
    lineage_rows = audit.rows(phase1 / "mechanism_run_start_lineage.csv")
    r3_rows = audit.rows(r3_reports / "round3_attempt_hashes.csv")
    results = []

    for scene in audit.SCENES:
        require("_VAL_" in scene and "TEST" not in scene.upper(), f"forbidden scope: {scene}")
        candidate = audit.select(candidate_rows, scene_id=scene)
        baseline = audit.select(baseline_rows, scene_id=scene)
        lineage = audit.select(lineage_rows, scene_id=scene)
        r3_identity = audit.select(r3_rows, scene_id=scene)
        require(candidate["split"] == "VAL" and baseline["split"] == "VAL",
                f"non-VAL rescore row: {scene}")
        b_raw = Path(baseline["resolved_raw_path"])
        d_raw = Path(candidate["raw_path"])
        r3_dir = ROOT / "experiments" / "paper14_v2_round3_xy_pcf_screen" / "runs" / scene / "attempt_01"
        r3_raw = r3_dir / "raw_run.mat"
        starts = {
            "B": b_raw.parent / "run_start.mat",
            "DSSM": Path(lineage["run_start_path"]),
            "R3": r3_dir / "run_start.mat",
        }
        raw_files = {"B": b_raw, "DSSM": d_raw, "R3": r3_raw}
        expected_raw = {
            "B": baseline["resolved_raw_sha256_expected"],
            "DSSM": candidate["raw_sha256_expected"],
            "R3": r3_identity["raw_sha256"],
        }
        for role, path in raw_files.items():
            require(path.is_file() and "TEST" not in str(path).upper(), f"missing/forbidden {role} raw")
            require(audit.sha256(path).lower() == expected_raw[role].lower(), f"raw SHA mismatch: {scene} {role}")
        expected_start = {
            "B": audit.B_RUN_START_SHA256[scene],
            "DSSM": lineage["run_start_sha256_before"],
            "R3": r3_identity["run_start_sha256"],
        }
        for role, path in starts.items():
            require(path.is_file() and audit.sha256(path).lower() == expected_start[role].lower(),
                    f"run-start SHA mismatch: {scene} {role}")

        b_cfg = audit.matlab_section(starts["B"], "cfg")
        d_cfg = audit.matlab_section(starts["DSSM"], "cfg")
        flat_b, flat_d = audit.flatten(b_cfg), audit.flatten(d_cfg)
        common = [key for key in flat_b.keys() & flat_d.keys()
                  if any(key.startswith(prefix) for prefix in audit.CORE_CFG_PREFIXES)]
        missing = [key for key in flat_b.keys() ^ flat_d.keys()
                   if any(key.startswith(prefix) for prefix in audit.CORE_CFG_PREFIXES)]
        mismatches = [key for key in common if not audit.same_value(flat_b[key], flat_d[key])]
        require(len(common) == 60 and not missing and not mismatches,
                f"B/DSSM core cfg mismatch: {scene}; common={len(common)}, missing={missing}, mismatches={mismatches}")

        r3_runtime = None
        with h5py.File(starts["R3"], "r") as mat:
            runtime = mat["input/runtime_source_identity"]
            runtime_hashes = matlab_cell_strings(runtime, "sha256")
            runtime_names = matlab_cell_strings(runtime, "name")
            require(len(runtime_names) == 7 and len(runtime_hashes) == 7,
                    f"unexpected R3 runtime identity shape: {scene}")
            for name, digest in zip(runtime_names, runtime_hashes):
                relative = f"experiments/paper14_v2_round3_xy_pcf_screen/runtime/{name}"
                require(SOURCE_SHA256.get(relative) == digest,
                        f"R3 runtime identity differs from pinned isolated source: {scene} {name}")
            plant = mat["input/plant_source_identity"]
            plant_names = matlab_cell_strings(plant, "name")
            plant_hashes = matlab_cell_strings(plant, "sha256")
            plant_identity = dict(zip(plant_names, plant_hashes))
            for name, expected in R3_PLANT_IDENTITY_SHA256.items():
                require(plant_identity.get(name) == expected,
                        f"R3 plant source identity mismatch: {scene} {name}")
            r3_runtime = {"names": runtime_names, "sha256": runtime_hashes,
                          "upstream_sha256": matlab_cell_strings(runtime, "upstream_sha256"),
                          "plant_identity_verified_count": len(R3_PLANT_IDENTITY_SHA256)}

        arrays = {role: {} for role in raw_files}
        motor_time_constants = {}
        for role, path in raw_files.items():
            with h5py.File(path, "r") as mat:
                motor_time_constants[role] = float(audit.log_array(mat, "motor_time_constant_s").reshape(-1)[0])
                arrays[role]["transition_time"] = audit.log_array(mat, "transition_time").reshape(-1)
                arrays[role]["time"] = audit.log_array(mat, "time").reshape(-1)
                arrays[role]["state"] = audit.log_array(mat, "state")
                arrays[role]["initial_state"] = audit.log_array(mat, "initial_state").reshape(-1)
                for field in audit.REFERENCE_FIELDS:
                    arrays[role][f"reference/{field}"] = audit.log_array(mat, f"reference/{field}")
                for field in FIELDS:
                    arrays[role][field] = audit.log_array(mat, field)
        for role in ("B", "R3"):
            audit.assert_equal(arrays["DSSM"]["transition_time"], arrays[role]["transition_time"], f"{scene} {role} transition clock")
            audit.assert_equal(arrays["DSSM"]["time"], arrays[role]["time"], f"{scene} {role} state clock")
            audit.assert_equal(arrays["DSSM"]["initial_state"], arrays[role]["initial_state"], f"{scene} {role} initial state")
        transition = arrays["DSSM"]["transition_time"]
        state_time = arrays["DSSM"]["time"]
        j = int(np.argmin(np.abs(transition - 0.020)))
        k = int(np.argmin(np.abs(state_time - 0.020)))
        require(abs(transition[j] - 0.020) <= 1e-12 and abs(state_time[k] - 0.020) <= 1e-12,
                f"{scene}: no exact 20 ms transition/state sample")
        for role in ("B", "R3"):
            audit.assert_equal(arrays["DSSM"]["state"][:, k], arrays[role]["state"][:, k], f"{scene} {role} state at 20 ms")
            for field in audit.REFERENCE_FIELDS:
                audit.assert_equal(arrays["DSSM"][f"reference/{field}"], arrays[role][f"reference/{field}"], f"{scene} {role} reference {field}")
        for field in ("position_bs_nominal_force_N", "filtered_attitude_reference", "filtered_attitude_rate",
                      "attitude_compensation_applied_torque_Nm"):
            audit.assert_equal(arrays["B"][field][:, j], arrays["DSSM"][field][:, j],
                               f"{scene} B/DSSM common controller input {field}")

        replayed = {}
        per_role_errors = {}
        for role in ("B", "DSSM"):
            log = arrays[role]
            state = log["state"][:, k]
            yaw_ref = float(log["reference/yaw"].reshape(-1)[j])
            filtered_eta = log["filtered_attitude_reference"][:, j]
            filtered_rate = log["filtered_attitude_rate"][:, j]
            compensation = log["attitude_compensation_applied_torque_Nm"][:, j]
            replay = controller_replay(b_cfg, state, log["position_commanded_force_N"][:, j], yaw_ref,
                                       filtered_eta, filtered_rate,
                                       log["command_filter_acceleration_applied_rads2"][:, j], compensation)
            replayed[role] = replay
            errors = {
                "target_euler_rad": checked_error(replay["target_euler"], log["command_filter_target_euler"][:, j], f"{scene} {role} target Euler"),
                "filter_request_rad_s2": checked_error(replay["filter_request"], log["command_filter_acceleration_request_unclamped_rads2"][:, j], f"{scene} {role} filter request"),
                "filter_applied_rad_s2": checked_error(replay["filter_applied"], log["command_filter_acceleration_applied_rads2"][:, j], f"{scene} {role} filter applied"),
                "nominal_torque_Nm": checked_error(replay["nominal_torque"], log["attitude_bs_nominal_torque_Nm"][:, j], f"{scene} {role} nominal torque"),
                "requested_generalized": checked_error(replay["requested_generalized"], log["requested_generalized"][:, j], f"{scene} {role} requested generalized"),
                "clipped_generalized": checked_error(replay["clipped_generalized"], log["controller_clipped_generalized"][:, j], f"{scene} {role} clipping"),
                "motor_squared": checked_error(replay["motor_squared_requested"], log["motor_squared_requested"][:, j], f"{scene} {role} motor squared", 1e-7),
                "motor_setpoint": checked_error(replay["motor_setpoint"], log["motor_setpoint"][:, j], f"{scene} {role} motor setpoint", 1e-10),
                "motor_command": checked_error(replay["motor_setpoint"], log["motor_command"][:, j], f"{scene} {role} motor command", 1e-10),
                "allocated_generalized": checked_error(replay["allocated_generalized"], log["allocated_generalized"][:, j], f"{scene} {role} allocated generalized", 1e-10),
            }
            require(motor_time_constants[role] == 0.0, f"{scene} {role} motor lag is nonzero at replay")
            require(replay["tilt_limited"] == bool(log["tilt_limited"].reshape(-1)[j]), f"{scene} {role} tilt flag mismatch")
            require(not replay["tilt_limited"] and not np.any(log["tilt_limited"][:, j]),
                    f"{scene} {role} tilt limit at replay point")
            require(not np.any(log["generalized_clipped"][:, j]), f"{scene} {role} generalized clipping at replay point")
            require(not np.any(log["motor_saturated"][:, j]), f"{scene} {role} motor saturation at replay point")
            per_role_errors[role] = errors

        r3_vs_d = {field: float(np.max(np.abs(arrays["R3"][field][:, j] - arrays["DSSM"][field][:, j])))
                   for field in FIELDS}
        require(max(r3_vs_d.values()) == 0.0, f"{scene}: R3 and DSSM 20 ms logged chain differs")
        deltas = {}
        for key, unit in (("position_commanded_force_N", "N"), ("raw_outer_attitude", "rad"),
                          ("command_filter_acceleration_request_unclamped_rads2", "rad/s^2"),
                          ("attitude_bs_nominal_torque_Nm", "N m"), ("requested_generalized", "N,N m"),
                          ("motor_squared_requested", "rad^2/s^2"), ("motor_setpoint", "rad/s")):
            delta = arrays["B"][key][:, j] - arrays["DSSM"][key][:, j]
            deltas[key] = {"max_abs": float(np.max(np.abs(delta))), "unit": unit, "components": delta.tolist()}

        results.append({
            "scene_id": scene,
            "time_s": 0.020,
            "matched_core_config_fields_B_vs_DSSM": len(common),
            "state_and_six_references_equal_at_replay": True,
            "common_B_DSSM_control_inputs_equal": ["position_bs_nominal_force_N", "filtered_attitude_reference", "filtered_attitude_rate", "attitude_compensation_applied_torque_Nm"],
            "R3_runtime_identity": r3_runtime,
            "R3_independent_cfg_replay": False,
            "replay_max_abs_errors": per_role_errors,
            "B_minus_DSSM_chain_differences": deltas,
            "no_tilt_limit_or_motor_saturation": True,
            "R3_DSSM_logged_chain_exactly_equal_at_20ms": True,
        })

    print(json.dumps({
        "scope": "SHA-hash five complete metadata/input files; scan CSV rows by scene_id and select only three pinned VAL W15 records for analysis; read only their raw/run-start/source files; no new simulation, training, Plant, or TEST access",
        "audit_script_sha256": audit.sha256(Path(__file__).resolve()),
        "pinned_helper_sha256": HELPER_SHA256,
        "input_table_sha256": input_hashes,
        "source_sha256": source_hashes,
        "results": results,
    }, indent=2))


if __name__ == "__main__":
    main()
