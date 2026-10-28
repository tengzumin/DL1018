#!/usr/bin/env python
"""Independent Python reconstruction audit for the 24 C5_COVERAGE33 caches.

Read-only inputs: frozen C5 raw/status/run_start/config plus the MATLAB caches.
The only output is the isolated JSON report under reports/coverage33.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
from pathlib import Path

import h5py
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
EXP = ROOT / "experiments" / "attitude_cm18_c524_coverage33_20261025"
DATA = EXP / "data"
REPORT = ROOT / "reports" / "attitude_cm18_c524_coverage33_20261025" / "C524_COVERAGE33_PYTHON_SOURCE_PARITY_v1.json"
MANIFEST = DATA / "C524_COVERAGE33_RELABEL_MANIFEST_v1.json"
C5 = ROOT / "experiments" / "position_axis_coordinate_c5_dev72_20261023"
TASKBOOK = ROOT / "reports" / "attitude_cm18_c524_screen12_20261025" / "C524_COVERAGE33_TASKBOOK_v2_ZH.md"
RELABELER = EXP / "relabel_c524_coverage33_v1.m"
EXTRACTOR = ROOT / "experiments" / "attitude_cm18_datarepair_20261024" / "extract_cm18_events_v1.m"
ATOL = 1e-9
RTOL = 1e-10
MANIFEST_SHA256 = "7d6a7d079d32120849cee62eadecd8e69a68d5a538608dd8959849ac5fe2dd8c"
SUPERSEDED_REPORTS = [
    {"report_sha256": "172d80eb5ac846f3809695b01c8f18ff3589fc74df63b28f19edcceac7bdc575",
     "status": "FAIL", "reason": "Checker draft used the wrong G flatten order and treated the valid _ACC_FIX_V1 source-scene alias as a mismatch; both checker defects were corrected, with no input data changed."},
    {"report_sha256": "170025336ed34458174d674beb8f9d63b33f8924c937fe238d8b327a6da3d63b",
     "status": "FAIL", "reason": "All 24 scenes passed, but the checker had a transcription typo in the pinned manifest SHA-256 constant; corrected against the actual SHA-256 of the unchanged manifest."},
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def check_hash(path: Path | str, expected: str) -> dict:
    p = Path(path)
    actual = sha256(p) if p.is_file() else None
    return {"path": str(p), "expected_sha256": expected.lower(), "actual_sha256": actual,
            "ok": actual is not None and actual.lower() == expected.lower()}


def text_attr(obj, name: str) -> str:
    value = obj.attrs.get(name, b"")
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


def mat_value(f: h5py.File, obj):
    """Decode the simple MATLAB v7.3 values used by these frozen files."""
    if isinstance(obj, h5py.Group):
        return {k: mat_value(f, obj[k]) for k in obj.keys()}
    cls = text_attr(obj, "MATLAB_class")
    raw = obj[()]
    if cls == "char":
        return "".join(chr(int(x)) for x in np.asarray(raw).ravel(order="F") if int(x))
    if cls == "cell" or (isinstance(raw, np.ndarray) and raw.dtype == object):
        refs = np.asarray(raw)
        if refs.ndim > 1:
            refs = refs.transpose(tuple(range(refs.ndim - 1, -1, -1)))
        return [None if not ref else mat_value(f, f[ref]) for ref in refs.ravel(order="F")]
    arr = np.asarray(raw)
    if arr.ndim > 1:
        arr = arr.transpose(tuple(range(arr.ndim - 1, -1, -1)))
    if arr.size == 1:
        return arr.reshape(-1)[0].item()
    return np.squeeze(arr)


def mat_group(path: Path, group_name: str) -> dict:
    with h5py.File(path, "r") as f:
        return mat_value(f, f[group_name])


def load_mat(path: Path, group_name: str, field: str):
    with h5py.File(path, "r") as f:
        return mat_value(f, f[group_name][field])


def arr(path: Path, group: str, field: str, dtype=float) -> np.ndarray:
    value = load_mat(path, group, field)
    return np.asarray(value, dtype=dtype)


def norm3(v: np.ndarray) -> float:
    return float(np.max(np.abs(v))) if np.size(v) else 0.0


def cuboid(mass: float, length: float, width: float, height: float) -> np.ndarray:
    return mass / 12.0 * np.diag([width**2 + height**2, length**2 + height**2,
                                  length**2 + width**2])


def cylinder(mass: float, radius: float, height: float) -> np.ndarray:
    xy = mass / 12.0 * (3.0 * radius**2 + height**2)
    return np.diag([xy, xy, 0.5 * mass * radius**2])


def mass_properties(lengths: np.ndarray, rates: np.ndarray, plant: dict):
    """NumPy transcription of distributed_mass_properties.m, including Jdot."""
    lengths = np.asarray(lengths, dtype=float).reshape(4)
    rates = np.asarray(rates, dtype=float).reshape(4)
    masses = plant["component_masses"]
    dims = plant["component_dimensions"]
    root = float(plant["arm_root_radius"])
    angles = np.asarray(plant["arm_angles"], dtype=float).reshape(4)
    directions = np.vstack([np.cos(angles), np.sin(angles), np.zeros(4)])
    total = masses["body"] + masses["battery"] + 4.0 * sum(
        masses[k] for k in ("arm", "motor", "rotor", "servo"))
    assert abs(total - float(plant["mass"])) <= 1e-12
    zero = np.zeros(3)
    positions = {
        "body": zero,
        "battery": zero,
        "arm": directions * (0.5 * (root + lengths))[None, :],
        "motor": directions * lengths[None, :],
        "rotor": directions * lengths[None, :],
        "servo": directions * (root + 0.5 * float(dims["servo"]["length"])),
    }
    pos_rates = {
        "body": zero,
        "battery": zero,
        "arm": directions * (0.5 * rates)[None, :],
        "motor": directions * rates[None, :],
        "rotor": directions * rates[None, :],
        "servo": np.zeros((3, 4)),
    }
    cog_num = (masses["body"] * positions["body"] + masses["battery"] * positions["battery"])
    cogdot_num = (masses["body"] * pos_rates["body"] + masses["battery"] * pos_rates["battery"])
    for key in ("arm", "motor", "rotor", "servo"):
        cog_num = cog_num + masses[key] * np.sum(positions[key], axis=1)
        cogdot_num = cogdot_num + masses[key] * np.sum(pos_rates[key], axis=1)
    cog, cogdot = cog_num / total, cogdot_num / total
    inertia = np.zeros((3, 3))
    inertia_dot = np.zeros((3, 3))
    Ibody = cuboid(masses["body"], dims["body"]["length"], dims["body"]["width"], dims["body"]["height"])

    def add(local_i, local_idot, mass, position, velocity):
        nonlocal inertia, inertia_dot
        r = position - cog
        rd = velocity - cogdot
        shift = (r @ r) * np.eye(3) - np.outer(r, r)
        shift_dot = 2.0 * (r @ rd) * np.eye(3) - np.outer(rd, r) - np.outer(r, rd)
        inertia += local_i + mass * shift
        inertia_dot += local_idot + mass * shift_dot

    add(Ibody, np.zeros((3, 3)), masses["body"], positions["body"], pos_rates["body"])
    add(np.zeros((3, 3)), np.zeros((3, 3)), masses["battery"], positions["battery"], pos_rates["battery"])
    for i, angle in enumerate(angles):
        ca, sa = np.cos(angle), np.sin(angle)
        R = np.array([[ca, -sa, 0.0], [sa, ca, 0.0], [0.0, 0.0, 1.0]])
        effective = lengths[i] - root
        arm_local = cuboid(masses["arm"], effective, dims["arm"]["width"], dims["arm"]["height"])
        arm_local_dot = masses["arm"] / 6.0 * effective * rates[i] * np.diag([0.0, 1.0, 1.0])
        motor_local = cylinder(masses["motor"], dims["motor"]["radius"], dims["motor"]["height"])
        rotor_local = cylinder(masses["rotor"], dims["rotor"]["inertia_equivalent_radius"], dims["rotor"]["height"])
        servo_local = cuboid(masses["servo"], dims["servo"]["length"], dims["servo"]["width"], dims["servo"]["height"])
        add(R @ arm_local @ R.T, R @ arm_local_dot @ R.T, masses["arm"], positions["arm"][:, i], pos_rates["arm"][:, i])
        add(motor_local, np.zeros((3, 3)), masses["motor"], positions["motor"][:, i], pos_rates["motor"][:, i])
        add(rotor_local, np.zeros((3, 3)), masses["rotor"], positions["rotor"][:, i], pos_rates["rotor"][:, i])
        add(R @ servo_local @ R.T, np.zeros((3, 3)), masses["servo"], positions["servo"][:, i], pos_rates["servo"][:, i])
    return 0.5 * (inertia + inertia.T), cog, 0.5 * (inertia_dot + inertia_dot.T), directions


def allocation(lengths: np.ndarray, cog: np.ndarray, plant: dict) -> np.ndarray:
    angles = np.asarray(plant["arm_angles"], dtype=float).reshape(4)
    directions = np.vstack([np.cos(angles), np.sin(angles), np.zeros(4)])
    relative = directions * np.asarray(lengths, dtype=float).reshape(1, 4) - cog.reshape(3, 1)
    return np.vstack([np.full(4, float(plant["kf"])),
                      float(plant["kf"]) * relative[1],
                      -float(plant["kf"]) * relative[0],
                      float(plant["km"]) * np.array([1.0, -1.0, 1.0, -1.0])])


def compare(name: str, expected: np.ndarray, actual: np.ndarray, atol=ATOL, rtol=RTOL) -> dict:
    a, b = np.asarray(expected), np.asarray(actual)
    same_shape = a.shape == b.shape
    diff = norm3(a.astype(float) - b.astype(float)) if same_shape else None
    ok = same_shape and bool(np.allclose(a, b, atol=atol, rtol=rtol, equal_nan=False))
    return {"field": name, "shape_expected": list(a.shape), "shape_cache": list(b.shape),
            "max_abs_diff": diff, "atol": atol, "rtol": rtol, "ok": ok}


def reconstruct(scene_id: str, split: str, raw_path: Path, run_start_path: Path,
                cache_path: Path, plant: dict, beta_rise: float, dmax: np.ndarray,
                b_raw_path: Path, b_raw_sha256: str, b_scene_id_raw: str) -> dict:
    raw = raw_path
    state = arr(raw, "log", "state")
    request = arr(raw, "log", "requested_generalized")
    realized = arr(raw, "log", "realized_generalized")
    tau_nom = arr(raw, "log", "attitude_bs_nominal_torque_Nm")
    tau_comp = arr(raw, "log", "attitude_compensation_applied_torque_Nm")
    wind = arr(raw, "log", "wind_torque_B")
    transition_time = arr(raw, "log", "transition_time").reshape(-1)
    full_time = arr(raw, "log", "time").reshape(-1)
    event_flags = arr(raw, "log", "attitude_event_flag", dtype=bool).reshape(-1)
    scene_time = arr(raw, "scene", "time").reshape(-1)
    command = arr(raw, "scene/arms", "command")
    rho = arr(raw, "scene/arms", "rho_true")
    rho_dot = arr(raw, "scene/arms", "rhoDot_true")
    assert load_mat(raw, "scene", "scene_id") == scene_id
    assert state.shape == (20001, 12) and request.shape == realized.shape == (20000, 4)
    assert tau_nom.shape == tau_comp.shape == wind.shape == (20000, 3)
    assert command.shape == rho.shape == rho_dot.shape == (20001, 4)
    assert transition_time.shape == (20000,) and full_time.shape == scene_time.shape == (20001,)
    assert np.array_equal(np.flatnonzero(event_flags) + 1, np.arange(11, 19992, 10))
    dt_vec = np.diff(scene_time)
    assert np.max(np.abs(dt_vec - 0.001)) <= 1e-12
    assert np.max(np.abs(full_time - scene_time)) <= 1e-12
    assert np.max(np.abs(transition_time - full_time[:-1])) <= 1e-12

    plant_index = np.arange(11, 19992, 10, dtype=np.int64)
    row = plant_index - 1
    omega = state[row, 9:12]
    j0, cog0, jdot0, _ = mass_properties(np.asarray(plant["arm_initial"]), np.zeros(4), plant)
    c0 = allocation(np.asarray(plant["arm_initial"]), cog0, plant)
    alpha_bs = np.linalg.solve(j0, (tau_nom[row] - np.cross(omega, (j0 @ omega.T).T) - (jdot0 @ omega.T).T).T).T
    thrust_mass = request[row, 0] / float(plant["mass"])
    prior_request = np.stack([request[k - 11:k - 1, 1:4] for k in plant_index])
    prior_dt = np.stack([dt_vec[k - 11:k - 1] for k in plant_index])
    a_feature = np.sum(prior_request * prior_dt[:, :, None], axis=1) / np.sum(prior_dt, axis=1)[:, None]
    u = command[row]
    z_all = np.vstack([np.zeros((1, 4)), np.cumsum(command[:-1] * dt_vec[:, None], axis=0)])
    z = z_all[row]
    x18 = np.column_stack([omega, alpha_bs, thrust_mass, u, z, a_feature])

    phase = np.zeros(plant_index.size, dtype=np.uint8)
    any_command = bool(np.any(np.abs(command) > 0))
    for q, k in enumerate(plant_index):
        if not any_command:
            code = 0
        elif np.any(command[k - 1] > 0):
            code = 2
        elif np.any(command[k - 1] < 0):
            code = 4
        elif np.any(rho[k - 1] > 0.150001):
            code = 3
        elif np.any(np.abs(command[:k]) > 0) and not np.any(np.abs(command[k - 1:]) > 0):
            code = 5
        else:
            code = 1
        phase[q] = code

    n = plant_index.size
    beta = np.minimum(plant_index * float(plant["dt"]) / beta_rise, 1.0)
    cstar = np.zeros((n, 3))
    e0_rows = np.zeros((n, 3))
    g_rows = np.zeros((n, 9))
    target_raw = np.zeros((n, 3))
    after_clip = np.zeros((n, 3))
    for q, k in enumerate(plant_index):
        j, cog, jdot, _ = mass_properties(rho[k - 1], rho_dot[k - 1], plant)
        ct = allocation(rho[k - 1], cog, plant)
        w = state[k - 1, 9:12]
        tn = tau_nom[k - 1]
        alpha_bsq = np.linalg.solve(j0, tn - np.cross(w, j0 @ w) - jdot0 @ w)
        l = np.vstack([np.zeros((1, 3)), j0])
        transfer = ct @ np.linalg.solve(c0, l)
        g = np.linalg.solve(j, transfer[1:4])
        wrench0 = ct @ np.linalg.solve(c0, np.r_[request[k - 1, 0], tn])
        e0 = np.linalg.solve(j, wrench0[1:4] + wind[k - 1] - np.cross(w, j @ w) - jdot @ w) - alpha_bsq
        cs = np.linalg.solve(g, e0)
        target = cs / beta[q]
        cstar[q], e0_rows[q], g_rows[q] = cs, e0, g.reshape(-1)
        target_raw[q] = target
        after_clip[q] = beta[q] * np.clip(target, -dmax, dmax)

    cache = cache_path
    cached_scene = load_mat(cache, "events", "scene_id")
    cached_split = load_mat(cache, "events", "split")
    identity = mat_group(cache, "events/identity")
    cache_identity_ok = (cached_scene == scene_id and cached_split == split
                         and Path(identity["c5_raw_path"]) == raw_path
                         and identity["c5_raw_sha256"].lower() == sha256(raw_path)
                         and Path(identity["c5_run_start_path"]) == run_start_path
                         and identity["c5_run_start_sha256"].lower() == sha256(run_start_path)
                         and Path(identity["b_raw_path"]) == b_raw_path
                         and identity["b_raw_sha256"].lower() == b_raw_sha256.lower()
                         and identity["b_scene_id_raw"] == b_scene_id_raw
                         and bool(identity["b_scene_id_alias"]) == (b_scene_id_raw != scene_id))
    # Event matrices are transposed by MATLAB's HDF5 layout and restored by mat_value.
    checks = [
        compare("event_index", np.arange(1, 2000), load_mat(cache, "events", "event_index")),
        compare("plant_index", plant_index, load_mat(cache, "events", "plant_index")),
        compare("event_time_s", transition_time[row], load_mat(cache, "events", "event_time_s")),
        compare("phase_code", phase, load_mat(cache, "events", "phase_code"), atol=0.0, rtol=0.0),
        compare("X18", x18, load_mat(cache, "events", "X18")),
        compare("E0_rad_s2", e0_rows, load_mat(cache, "events", "E0_rad_s2")),
        compare("G_row_major", g_rows, load_mat(cache, "events", "G_row_major")),
        compare("target_applied_cStar", cstar, load_mat(cache, "events", "target_applied_acceleration_rad_s2")),
        compare("beta", beta, load_mat(cache, "events", "beta")),
        compare("target_raw_cStar_over_beta", target_raw, load_mat(cache, "events", "target_raw_output_rad_s2")),
        compare("target_after_clip_beta", after_clip, load_mat(cache, "events", "target_after_clip_beta_rad_s2")),
    ]
    requested_closure = norm3(request[row, 1:4] - (tau_nom[row] - tau_comp[row]))
    closure = {"event_count": int(n), "event_clock_max_abs_s": norm3(transition_time[row] - ((plant_index - 1) * float(plant["dt"]))),
               "request_torque_closure_max_abs_Nm": requested_closure,
               "E0_minus_GcStar_max_abs": norm3(e0_rows - np.einsum("nij,nj->ni", g_rows.reshape(n, 3, 3), cstar)),
               "target_beta_closure_max_abs": norm3(target_raw * beta[:, None] - cstar),
               "cache_identity_ok": bool(cache_identity_ok),
               "all_fields_within_tolerance": all(c["ok"] for c in checks)}
    return {"scene_id": scene_id, "split": split, "cache_sha256": sha256(cache),
            "raw_sha256": sha256(raw), "run_start_sha256": sha256(run_start_path),
            "status": "PASS" if closure["all_fields_within_tolerance"] and cache_identity_ok else "FAIL",
            "closure": closure, "fields": checks}


def main() -> int:
    replace_report = "--replace-report" in sys.argv[1:]
    if REPORT.exists():
        if not replace_report:
            raise FileExistsError(f"Refusing to overwrite {REPORT}; pass --replace-report only for this checker's own report")
        previous = json.loads(REPORT.read_text(encoding="utf-8"))
        if previous.get("schema") != "C524_COVERAGE33_INDEPENDENT_PYTHON_SOURCE_PARITY_V1":
            raise ValueError(f"Refusing to replace an unrelated report: {REPORT}")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    lock_path = Path(manifest["c5_lock_path"])
    snapshot_path = Path(manifest["c5_snapshot_path"])
    taskbook_path = Path(manifest["taskbook_path"])
    extractor_path = Path(manifest["extractor_path"])
    evidence_hashes = [
        check_hash(MANIFEST, MANIFEST_SHA256),
        check_hash(taskbook_path, manifest["taskbook_sha256"]),
        check_hash(RELABELER, manifest["relabeler_sha256"]),
        check_hash(extractor_path, manifest["extractor_sha256"]),
        check_hash(lock_path, manifest["c5_lock_sha256"]),
        check_hash(snapshot_path, manifest["c5_snapshot_sha256"]),
    ]
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    release_path = C5 / "C5_DEV72_RELEASE_v3.json"
    contract_path = C5 / "C5_DEV72_RUN_CONTRACT_v3.json"
    prepare_path = C5 / "C5_DEV72_PREPARE_RESULT_v3.json"
    binding_path = C5 / "C5_DEV72_SOURCE_BINDING_v3.json"
    parent_contract_path = C5 / "C5_DEV72_PARENT_RELEASE_CONTRACT_v3.json"
    preflight_path = C5 / "C5_DEV72_RUNNER_PREFLIGHT_RESULT_v3.json"
    release = json.loads(release_path.read_text(encoding="utf-8"))
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    binding = json.loads(binding_path.read_text(encoding="utf-8"))
    prepare = json.loads(prepare_path.read_text(encoding="utf-8"))
    release_hashes = {"input_lock_sha256": sha256(lock_path), "run_contract_sha256": sha256(contract_path),
                      "prepare_result_sha256": sha256(prepare_path), "prepared_snapshot_sha256": sha256(snapshot_path),
                      "source_binding_sha256": sha256(binding_path), "parent_release_contract_sha256": sha256(parent_contract_path),
                      "runner_preflight_result_sha256": sha256(preflight_path)}
    release_chain_checks = {
        "release_references_input_lock_contract_prepare_snapshot_source_binding_parent_contract_preflight": all(
            release.get(k) == v for k, v in release_hashes.items()),
        "source_binding_references_input_lock_and_run_contract": (
            binding.get("input_lock_sha256") == release_hashes["input_lock_sha256"]
            and binding.get("run_contract_sha256") == release_hashes["run_contract_sha256"]),
        "source_binding_references_parent_release_contract": (
            binding.get("release_contract_sha256") == release_hashes["parent_release_contract_sha256"]),
        "prepare_result_references_input_lock_contract_and_source_binding": (
            prepare.get("input_lock_sha256") == release_hashes["input_lock_sha256"]
            and prepare.get("run_contract_sha256") == release_hashes["run_contract_sha256"]
            and prepare.get("source_binding_sha256") == release_hashes["source_binding_sha256"]
            and prepare.get("snapshot_sha256") == release_hashes["prepared_snapshot_sha256"]),
        "frozen_contract_candidate_and_coordinate_mask": (
            contract.get("schema") == "C5_AXIS_COORDINATE_DEV72_RUN_CONTRACT_V3"
            and contract.get("candidate") == release.get("candidate")
            and contract.get("coordinate_mask") == release.get("coordinate_mask")),
    }
    release_chain_ok = all(release_chain_checks.values())

    snapshot = mat_group(snapshot_path, "cfg")
    plant = snapshot["plant"]
    beta_rise = float(snapshot["rbf"]["attitude"]["beta_rise_time"])
    dmax = np.asarray(snapshot["rbf"]["attitude"]["dmax"], dtype=float).reshape(3)
    src = mat_group(snapshot_path, "sourceIdentity")
    source_paths = list(src["active_paths"])
    source_shas = [str(x).lower() for x in src["active_sha256"]]
    if len(source_paths) != 32 or len(source_shas) != 32:
        raise AssertionError("Frozen C5 active source inventory is not 32 entries")
    inventory_parts = []
    source_hashes = []
    for i, (path, expected) in enumerate(zip(source_paths, source_shas), 1):
        inventory_parts.extend([path, expected, str(i)])
        source_hashes.append(check_hash(path, expected))
    inventory_sha = hashlib.sha256("\n".join(inventory_parts).encode("utf-8")).hexdigest()
    inventory_ok = inventory_sha == manifest["active_source_inventory_sha256"] and all(x["ok"] for x in source_hashes)

    frozen_rows = {x["scene_id"]: x for x in lock["scenes"]}
    scene_identity = mat_group(snapshot_path, "sceneIdentity")
    snapshot_ids = [str(x) for x in scene_identity["scene_id"]]
    snapshot_b_paths = list(scene_identity["B_raw_path"])
    snapshot_b_shas = [str(x).lower() for x in scene_identity["B_raw_sha256"]]
    snapshot_raw_scene_ids = [str(x) for x in scene_identity["raw_scene_id"]]
    scene_identity_ok = len(snapshot_ids) == len(snapshot_b_paths) == len(snapshot_b_shas) == len(snapshot_raw_scene_ids) == 72
    cache_records = manifest["extra_dev_scenes"] + manifest["holdout_dev_scenes"]
    if len(cache_records) != 24:
        raise AssertionError("Manifest does not contain exactly 24 new caches")

    per_scene = []
    source_file_checks = []
    for record in cache_records:
        sid, split = record["scene_id"], record["split"]
        lock_row = frozen_rows[sid]
        assert lock_row["source_split"] == "DEV"
        assert sid in snapshot_ids
        j = snapshot_ids.index(sid)
        b_source = lock_row["B_source"]
        assert Path(snapshot_b_paths[j]) == Path(b_source["path"])
        assert snapshot_b_shas[j] == b_source["sha256"].lower()
        assert snapshot_raw_scene_ids[j] == record["b_scene_id_raw"]
        raw_path = Path(record["c5_raw_path"])
        status_path = Path(record["c5_run_status_path"])
        start_path = Path(record["c5_run_start_path"])
        cache_path = Path(record["event_cache_path"])
        checks = [check_hash(raw_path, record["c5_raw_sha256"]),
                  check_hash(status_path, record["c5_run_status_sha256"]),
                  check_hash(start_path, record["c5_run_start_sha256"]),
                  check_hash(cache_path, record["event_cache_sha256"]),
                  check_hash(b_source["path"], b_source["sha256"])]
        source_file_checks.extend(checks)
        status = json.loads(status_path.read_text(encoding="utf-8"))
        run_start = mat_group(start_path, "runStart")
        raw_identity = mat_group(raw_path, "runIdentity")
        expected_identity_hashes = {
            "input_lock_sha256": release_hashes["input_lock_sha256"],
            "release_sha256": sha256(release_path),
            "run_contract_sha256": sha256(contract_path),
            "prepare_result_sha256": sha256(prepare_path),
            "cfg_opts_snapshot_sha256": sha256(snapshot_path),
        }
        row_identity_ok = (
            Path(status["raw_path"]) == raw_path and Path(status["run_start_path"]) == start_path
            and status["scene_id"] == sid and status["source_scene_id"] == record["b_scene_id_raw"]
            and status["raw_sha256"].lower() == checks[0]["actual_sha256"]
            and status["run_start_sha256"].lower() == checks[2]["actual_sha256"]
            and status["candidate"] == release["candidate"]
            and status["coordinate_mask"] == release["coordinate_mask"]
            and status["training_steps"] == 0 and status["optimizer_steps"] == 0
            and not status["TEST_accessed"]
            and run_start["scene_id"] == sid and run_start["source_scene_id"] == record["b_scene_id_raw"]
            and run_start["input_lock_sha256"] == release_hashes["input_lock_sha256"]
            and run_start["release_sha256"] == sha256(release_path)
            and run_start["run_contract_sha256"] == sha256(contract_path)
            and run_start["prepare_result_sha256"] == sha256(prepare_path)
            and run_start["cfg_opts_snapshot_sha256"] == sha256(snapshot_path)
            and raw_identity["scene_id"] == sid and raw_identity["input_lock_sha256"] == release_hashes["input_lock_sha256"]
            and raw_identity["release_sha256"] == sha256(release_path)
            and raw_identity["prepare_result_sha256"] == sha256(prepare_path)
            and raw_identity["candidate"] == release["candidate"]
            and np.array_equal(np.asarray(raw_identity["coordinate_mask"], dtype=float).reshape(3), np.asarray(release["coordinate_mask"], dtype=float))
            and raw_identity["TEST_accessed"] == 0 and raw_identity["optimizer_steps"] == 0
        )
        row_identity_ok &= all(status.get(k, "").lower() == v.lower() for k, v in expected_identity_hashes.items())
        source_identity = run_start["scene_identity"]
        row_identity_ok &= (source_identity["scene_id"] == sid
                            and source_identity["source_scene_id"] == record["b_scene_id_raw"]
                            and source_identity["external_identity_sha256"] == lock_row["external_identity_sha256"])
        # Confirm run_start's copied physics values are the same as the frozen prepared cfg.
        start_cfg = run_start["cfg"]
        for key in ("mass", "dt", "kf", "km", "arm_root_radius"):
            row_identity_ok &= np.array_equal(np.asarray(start_cfg["plant"][key]), np.asarray(plant[key]))
        for key in ("arm_angles", "arm_initial"):
            row_identity_ok &= np.array_equal(np.asarray(start_cfg["plant"][key]), np.asarray(plant[key]))
        row_identity_ok &= start_cfg["controller_morphology_mode"] == snapshot["controller_morphology_mode"]
        row_identity_ok &= np.array_equal(np.asarray(start_cfg["rbf"]["attitude"]["dmax"]), dmax)
        row_identity_ok &= float(start_cfg["rbf"]["attitude"]["beta_rise_time"]) == beta_rise
        b_status_hash = check_hash(b_source["path"], b_source["sha256"])
        row_identity_ok &= run_start["B_physical_source_path"] == b_source["path"]
        row_identity_ok &= run_start["B_physical_source_sha256"].lower() == b_source["sha256"].lower()
        row_identity_ok &= snapshot_raw_scene_ids[j] == record["b_scene_id_raw"]
        start_paths = [str(x) for x in run_start["source_paths"]]
        start_shas = [str(x).lower() for x in run_start["source_sha256"]]
        row_identity_ok &= start_paths == source_paths and start_shas == source_shas
        reconstructed = reconstruct(sid, split, raw_path, start_path, cache_path, plant, beta_rise, dmax,
                                    Path(record["b_raw_path"]), record["b_raw_sha256"], record["b_scene_id_raw"])
        reconstructed["frozen_identity_ok"] = bool(row_identity_ok and b_status_hash["ok"])
        if not reconstructed["frozen_identity_ok"]:
            reconstructed["status"] = "FAIL"
        per_scene.append(reconstructed)

    global_ok = (all(x["ok"] for x in evidence_hashes) and release_chain_ok and inventory_ok
                 and scene_identity_ok and all(x["ok"] for x in source_file_checks)
                 and all(x["status"] == "PASS" and x["frozen_identity_ok"] for x in per_scene))
    field_max = {}
    for row in per_scene:
        for f in row["fields"]:
            field_max[f["field"]] = max(field_max.get(f["field"], 0.0), f["max_abs_diff"] or 0.0)
    report = {
        "schema": "C524_COVERAGE33_INDEPENDENT_PYTHON_SOURCE_PARITY_V1",
        "status": "PASS" if global_ok else "FAIL",
        "created_utc": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "execution_command": os.environ.get("C5_COVERAGE33_PARITY_COMMAND", "python check_c524_coverage33_python_source_parity_v1.py"),
        "checker_identity": {"path": str(Path(__file__).resolve()), "sha256": sha256(Path(__file__).resolve())},
        "supersedes": SUPERSEDED_REPORTS,
        "environment": {"python": sys.version, "platform": platform.platform(), "numpy": np.__version__,
                        "h5py": h5py.__version__, "matlab_called": False, "plant_called": False,
                        "optimizer_steps": 0, "C5_VAL48_read": False, "TEST_read": False},
        "tolerance": {"numerical_atol": ATOL, "numerical_rtol": RTOL,
                      "event_index_plant_index_phase_atol": 0.0, "event_index_plant_index_phase_rtol": 0.0},
        "source_identity": {"evidence_hashes": evidence_hashes, "release_chain_hashes": release_hashes,
                            "release_chain_checks": release_chain_checks,
                            "release_chain_ok": bool(release_chain_ok),
                            "active_source_inventory_expected_sha256": manifest["active_source_inventory_sha256"],
                            "active_source_inventory_computed_sha256": inventory_sha,
                            "active_source_count": len(source_hashes), "active_source_ok_count": sum(x["ok"] for x in source_hashes),
                            "active_source_failures": [x for x in source_hashes if not x["ok"]],
                            "cache_raw_status_start_b_hash_checks": len(source_file_checks),
                            "cache_raw_status_start_b_hash_failures": [x for x in source_file_checks if not x["ok"]],
                            "snapshot_scene_identity_count": len(snapshot_ids), "snapshot_scene_identity_ok": bool(scene_identity_ok),
                            "scene_identity_binding": "C5 lock DEV row + frozen prepared snapshot sceneIdentity + B-source SHA + per-scene C5 run_start/runIdentity"},
        "reconstruction": {"events_per_scene": 1999, "scenes": len(per_scene),
                           "event_count_total": sum(x["closure"]["event_count"] for x in per_scene),
                           "max_abs_diff_by_field": field_max,
                           "closed_formulas": ["X18=[omega, alphaBS, T/m, command, z_integral, 10-transition mean requested torque]",
                                               "distributed_v1 J/Jdot and CoG-aware allocation reconstructed from frozen cfg and raw rho/rhoDot",
                                               "G=J^-1*(Ctrue*C0^-1*[0;J0])[moments,:]",
                                               "E0=J^-1*(Ctrue*C0^-1*[T;tauNom] moments + wind - omega×Jomega - Jdot*omega)-alphaBS",
                                               "cStar=solve(G,E0), beta=min(plant_index*dt/beta_rise,1), target=cStar/beta, clipped=beta*clip(target,±dmax)"]},
        "scenes": per_scene,
        "conclusion": ("All 24 MATLAB caches independently match source-reconstructed clock, phase, X18, G/E0/cStar, beta, target and clip within tolerance; frozen C5 source identities are consistent."
                       if global_ok else "One or more source identity, reconstruction, or cache parity checks failed; do not treat this audit as a pass."),
    }
    with REPORT.open("w" if replace_report else "x", encoding="utf-8", newline="\n") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, allow_nan=False)
        f.write("\n")
    print(json.dumps({"status": report["status"], "report": str(REPORT),
                      "scenes": len(per_scene), "event_count": report["reconstruction"]["event_count_total"],
                      "max_abs_diff_by_field": field_max,
                      "failed_scenes": [x["scene_id"] for x in per_scene if x["status"] != "PASS" or not x["frozen_identity_ok"]]},
                     indent=2, ensure_ascii=False))
    return 0 if global_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
