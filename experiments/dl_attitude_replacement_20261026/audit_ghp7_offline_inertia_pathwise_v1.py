from datetime import datetime
import hashlib
import json
from pathlib import Path

import h5py
import numpy as np

root = Path.cwd()
base = root / "experiments/dl_attitude_replacement_20261026"
manifest_path = base / "GHP7_PILOT_PAYLOAD_MANIFEST_v1.json"
config_path = root / "experiments/position_axis_coordinate_c5_dev72_20261023/C5_DEV72_PREPARED_CFG_OPTS_v3.mat"
j0_audit_path = base / "CONTROLLER_J0_AUDIT_VAL48_v1.json"
mass_source = base / "pilot_runner_v4_teacher_distill/candidate_runner_work/matlab/core/distributed_mass_properties.m"
direction_source = base / "pilot_runner_v4_teacher_distill/candidate_runner_work/matlab/core/arm_directions.m"
output_path = base / "GHP7_SIX_PAYLOAD_OFFLINE_INERTIA_PATHWISE_DIAGNOSTIC_v1.json"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def scalar(dataset):
    return float(np.asarray(dataset[()]).squeeze())


def cuboid(mass, length, width, height):
    return mass / 12 * np.diag([width**2 + height**2,
                                length**2 + height**2,
                                length**2 + width**2])


def cylinder(mass, radius, height):
    return np.diag([mass / 12 * (3 * radius**2 + height**2),
                    mass / 12 * (3 * radius**2 + height**2),
                    0.5 * mass * radius**2])


def rotation_z(angle):
    c, s = np.cos(angle), np.sin(angle)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])


with h5py.File(config_path, "r") as file:
    plant = file["cfg"]["plant"]
    masses = {name: scalar(plant["component_masses"][name])
              for name in ("body", "battery", "arm", "motor", "rotor", "servo")}
    dimensions = {
        group: {name: scalar(plant["component_dimensions"][group][name])
                for name in plant["component_dimensions"][group]}
        for group in ("body", "arm", "motor", "rotor", "servo")
    }
    angles = np.asarray(plant["arm_angles"][()]).reshape(-1)
    directions = np.stack([np.cos(angles), np.sin(angles),
                           np.zeros(4)], axis=1)
    total_mass = scalar(plant["mass"])
    root_radius = scalar(plant["arm_root_radius"])
    arm_min, arm_max = scalar(plant["arm_length_min"]), scalar(plant["arm_length_max"])
    nominal_lengths = np.asarray(plant["arm_initial"][()]).reshape(-1)

expected_mass = masses["body"] + masses["battery"] + 4 * sum(masses[name] for name in ("arm", "motor", "rotor", "servo"))
assert abs(expected_mass - total_mass) < 1e-12

body_i = cuboid(masses["body"], dimensions["body"]["length"],
                dimensions["body"]["width"], dimensions["body"]["height"])
motor_i = cylinder(masses["motor"], dimensions["motor"]["radius"],
                   dimensions["motor"]["height"])
rotor_i = cylinder(masses["rotor"], dimensions["rotor"]["inertia_equivalent_radius"],
                   dimensions["rotor"]["height"])
servo_i = cuboid(masses["servo"], dimensions["servo"]["length"],
                 dimensions["servo"]["width"], dimensions["servo"]["height"])


def mass_properties(lengths, rates):
    lengths, rates = np.asarray(lengths, float), np.asarray(rates, float)
    arm_pos = directions.T * (0.5 * (root_radius + lengths))
    arm_rate = directions.T * (0.5 * rates)
    motor_pos = directions.T * lengths
    motor_rate = directions.T * rates
    servo_radius = root_radius + 0.5 * dimensions["servo"]["length"]
    servo_pos = directions.T * servo_radius
    cog = (masses["arm"] * arm_pos.sum(axis=1)
           + (masses["motor"] + masses["rotor"]) * motor_pos.sum(axis=1)
           + masses["servo"] * servo_pos.sum(axis=1)) / total_mass
    cog_rate = (masses["arm"] * arm_rate.sum(axis=1)
                + (masses["motor"] + masses["rotor"]) * motor_rate.sum(axis=1)) / total_mass
    inertia, inertia_dot = np.zeros((3, 3)), np.zeros((3, 3))

    def add(local_i, local_idot, mass, pos, posdot):
        nonlocal inertia, inertia_dot
        r, rdot = pos - cog, posdot - cog_rate
        inertia += local_i + mass * ((r @ r) * np.eye(3) - np.outer(r, r))
        inertia_dot += local_idot + mass * (
            2 * (r @ rdot) * np.eye(3) - np.outer(rdot, r) - np.outer(r, rdot))

    zero = np.zeros(3)
    add(body_i, np.zeros((3, 3)), masses["body"], zero, zero)
    add(np.zeros((3, 3)), np.zeros((3, 3)), masses["battery"], zero, zero)
    for i, angle in enumerate(angles):
        rot = rotation_z(angle)
        effective_length = lengths[i] - root_radius
        arm_i = cuboid(masses["arm"], effective_length,
                       dimensions["arm"]["width"], dimensions["arm"]["height"])
        arm_idot = (masses["arm"] / 6 * effective_length * rates[i]
                    * np.diag([0, 1, 1]))
        add(rot @ arm_i @ rot.T, rot @ arm_idot @ rot.T,
            masses["arm"], arm_pos[:, i], arm_rate[:, i])
        add(motor_i, np.zeros((3, 3)), masses["motor"],
            motor_pos[:, i], motor_rate[:, i])
        add(rotor_i, np.zeros((3, 3)), masses["rotor"],
            motor_pos[:, i], motor_rate[:, i])
        add(rot @ servo_i @ rot.T, np.zeros((3, 3)), masses["servo"],
            directions[i] * servo_radius, zero)
    return 0.5 * (inertia + inertia.T), 0.5 * (inertia_dot + inertia_dot.T)


j0, j0dot = mass_properties(nominal_lengths, np.zeros(4))
j0_audit = json.loads(j0_audit_path.read_text(encoding="utf-8"))
expected_j0 = np.asarray(j0_audit["records"][0]["controller_fixed_J0"], float)
assert j0_audit["status"] == "PASS"
assert np.max(np.abs(j0 - expected_j0)) < 1e-12
assert np.max(np.abs(j0dot)) < 1e-12

manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
assert manifest["status"] == "PASS" and manifest["scene_count"] == 6
receipt_path = Path(manifest["source_receipt_path"])
assert sha256(receipt_path).lower() == manifest["source_receipt_sha256"].lower()
receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
assert receipt["status"] == "PASS_NO_PLANT_PILOT_PAYLOADS_ONLY"
scene_builder = Path(receipt["scene_builder_path"])
assert sha256(scene_builder).lower() == receipt["scene_builder_sha256"].lower()
records = []
for item in manifest["records"]:
    payload = Path(item["payload_path"])
    digest = sha256(payload)
    assert digest.lower() == item["payload_file_sha256"].lower()
    with h5py.File(payload, "r") as file:
        arms = file["scene"]["arms"]
        lengths = np.asarray(arms["rho_true"][()]).T
        rates = np.asarray(arms["rhoDot_true"][()]).T
        command = np.asarray(arms["command"][()]).T
    assert lengths.shape == rates.shape == command.shape and lengths.shape[1] == 4
    assert np.max(np.abs(rates - 0.05 * command)) < 1e-12
    assert np.isfinite(lengths).all() and np.isfinite(rates).all()
    assert lengths.min() >= arm_min - 1e-12 and lengths.max() <= arm_max + 1e-12
    row = {"scene_id": item["scene_id"], "payload_sha256": digest,
           "sample_count": int(lengths.shape[0]),
           "arm_min_m": float(lengths.min()), "arm_max_m": float(lengths.max()),
           "arm_rate_max_mps": float(np.abs(rates).max()),
           "max_spectral_norm_J_minus_J0_kgm2": 0.0,
           "max_spectral_norm_Jdot_kgm2ps": 0.0,
           "min_eigenvalue_J_kgm2": float("inf")}
    for length, rate in zip(lengths, rates):
        inertia, inertia_dot = mass_properties(length, rate)
        row["max_spectral_norm_J_minus_J0_kgm2"] = max(
            row["max_spectral_norm_J_minus_J0_kgm2"],
            float(np.linalg.norm(inertia - j0, 2)))
        row["max_spectral_norm_Jdot_kgm2ps"] = max(
            row["max_spectral_norm_Jdot_kgm2ps"],
            float(np.linalg.norm(inertia_dot, 2)))
        row["min_eigenvalue_J_kgm2"] = min(
            row["min_eigenvalue_J_kgm2"], float(np.linalg.eigvalsh(inertia)[0]))
    records.append(row)

report = {
    "schema": "DL1018_GHP7_SIX_PAYLOAD_INERTIA_PATHWISE_DIAGNOSTIC_V1",
    "status": "PASS_OFFLINE_MODEL_RECONSTRUCTION_ONLY",
    "created_local": datetime.now().astimezone().isoformat(timespec="seconds"),
    "source_hashes": {
        "payload_manifest": sha256(manifest_path),
        "payload_source_receipt": sha256(receipt_path),
        "scene_builder": sha256(scene_builder),
        "config_mat": sha256(config_path),
        "j0_audit": sha256(j0_audit_path),
        "distributed_mass_properties_m": sha256(mass_source),
        "arm_directions_m": sha256(direction_source),
        "audit_script": sha256(__file__),
    },
    "nominal_J0_reconstruction_fro_error": float(np.linalg.norm(j0 - expected_j0, "fro")),
    "plant_calls_by_this_audit": 0,
    "test_data_read_by_this_audit": False,
    "runtime_candidate_input_use": False,
    "interpretation": "Offline reconstruction from rho_true/rhoDot_true in six pre-frozen GHP7 payloads using the source-bound distributed_v1 formulas. These are pathwise diagnostics for these six inputs, not bounds for unseen scenes and not controller or TCN inputs.",
    "records": records,
}
output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, indent=2))



