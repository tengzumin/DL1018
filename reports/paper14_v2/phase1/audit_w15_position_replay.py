#!/usr/bin/env python3
"""Read-only W15 sidecar/config and same-state position-force replay audit."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import h5py
import numpy as np
from scipy.io import loadmat


ROOT = Path(__file__).resolve().parents[3]
SCENES = (
    "DL1018_VAL_T1_C08_W15",
    "DL1018_VAL_T2_C05_W15",
    "DL1018_VAL_T3_C02_W15",
)
B_RUN_START_SHA256 = {
    SCENES[0]: "ec4bf37dc6d333434e1016902ce1c4a551e5dec3adc7cfffbed4efd5c74dc8ef",
    SCENES[1]: "df4165f70ffffd44562f91c9972a6e2205c222b2f34fe5ccc7a1ff6d29252285",
    SCENES[2]: "fb764089dbb6fd35bd3820cde4ec50d6c6aead1d8ff9d53009980664c9885be0",
}
CORE_CFG_PREFIXES = (
    "plant/",
    "control/bs/",
    "control/command_filter/",
    "control/limits/",
    "control/morphology_mode",
    "controller_",
    "mass_model",
)
REFERENCE_FIELDS = (
    "position",
    "velocity",
    "acceleration",
    "yaw",
    "yaw_rate",
    "yaw_acceleration",
)
TOL = 1e-12
SOURCE_SHA256 = {
    "matlab/core/position_bs_step.m": "ea533c3ae97cbc552208287e7f8d9b0a0f5a018f36fb5c8bd45520e19e73c681",
    "matlab/runtime/controller_options_dl1018.m": "93633a5fd95f73d33982045c2fa372d49b1a0df8ea0cfb5ca4461208ca9d53b1",
}
INPUT_TABLE_SHA256 = {
    "experiments/paper14_v2_round3_xy_pcf_screen/frozen_inputs.json": "2557c553578fc7616ce79f7fb62505bb69b2ba6fac7ab83e60e283d0c1e92404",
    "reports/paper14_v2/phase1/candidate_dssm_raw_rescore.csv": "cf0a4dc078f0cb751877695cabc58aba05bd0933b022d948410d376133a974e0",
    "reports/paper14_v2/phase1/baseline_b_raw_rescore.csv": "27a77399470eda26fde5f1724d199de10235844c519e8d561547af6f1a8933b2",
    "reports/paper14_v2/phase1/mechanism_run_start_lineage.csv": "99f630dd3702e4ea3e9638b875dc1d3d621ffa22daf8b88baa0232d6860fda50",
    "experiments/paper14_v2_round3_xy_pcf_screen/reports/round3_attempt_hashes.csv": "e849bb496e5d71d97b9d488a1164494e2be4467dcd149aba8c982495c3ea1663",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def mat_format(path: Path) -> str:
    return "MAT v7.3/HDF5" if h5py.is_hdf5(path) else "MAT v5"


def rows(path: Path) -> list[dict[str, str]]:
    selected = []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        header_line = stream.readline()
        header = next(csv.reader([header_line]))
        scene_index = header.index("scene_id")
        if header[:scene_index] not in ([], ["split", "task"]):
            raise ValueError(f"unexpected columns before scene_id in {path}")
        for line in stream:
            if not line.strip():
                continue
            prefix = line.rstrip("\r\n").split(",", scene_index + 1)
            scene_id = prefix[scene_index].strip().strip('"')
            if scene_id in SCENES:
                selected.append(next(csv.DictReader([header_line, line])))
    return selected


def select(items: list[dict[str, str]], **criteria: str) -> dict[str, str]:
    hits = [item for item in items if all(item.get(k) == v for k, v in criteria.items())]
    if len(hits) != 1:
        raise ValueError(f"expected one row for {criteria}, got {len(hits)}")
    return hits[0]


def h5_tree(node):
    if isinstance(node, h5py.Group):
        return {key: h5_tree(value) for key, value in node.items()}
    value = node[()]
    matlab_class = node.attrs.get("MATLAB_class", b"")
    if isinstance(matlab_class, bytes):
        matlab_class = matlab_class.decode(errors="ignore")
    if matlab_class == "char":
        matlab_order = np.transpose(np.asarray(value))
        return (
            "__matlab_char__",
            tuple(matlab_order.shape),
            "".join(
            chr(int(code))
                for code in matlab_order.flatten(order="F")
            if int(code) != 0
            ),
        )
    if isinstance(value, np.ndarray) and value.dtype.kind == "O":
        matlab_order = np.transpose(value)
        items = [h5_tree(node.file[ref]) if ref else None for ref in matlab_order.flat]
        shaped = np.empty(matlab_order.shape, dtype=object)
        shaped.flat[:] = items
        return shaped.tolist()
    if isinstance(value, np.ndarray):
        # Keep the stored dimensions so configuration-array shape differences
        # cannot disappear. MATLAB v7.3 stores numeric dimensions in reverse
        # order in HDF5, so normalize back to MATLAB's logical axis order.
        return np.transpose(value).tolist()
    if isinstance(value, np.generic):
        return value.item()
    return value


def matlab_section(path: Path, name: str) -> dict:
    if h5py.is_hdf5(path):
        with h5py.File(path, "r") as mat:
            return h5_tree(mat[name])
    data = loadmat(path, simplify_cells=False, struct_as_record=False, squeeze_me=False)
    run_start = data["runStart"].item()
    return mat5_tree(getattr(run_start, name))


def mat5_tree(value):
    if hasattr(value, "_fieldnames"):
        return {key: mat5_tree(getattr(value, key)) for key in value._fieldnames}
    if isinstance(value, np.ndarray):
        if value.dtype.kind in "US":
            text = "".join(str(char) for char in value.flatten(order="F"))
            matlab_char_width = max((len(str(char)) for char in value.flat), default=0)
            return (
                "__matlab_char__",
                tuple(value.shape) + (matlab_char_width,),
                text,
            )
        if value.dtype.kind == "O":
            if value.size == 1 and hasattr(value.item(), "_fieldnames"):
                return mat5_tree(value.item())
            items = [mat5_tree(item) for item in value.flat]
            shaped = np.empty(value.shape, dtype=object)
            shaped.flat[:] = items
            return shaped.tolist()
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    return value


def matlab_value(path: Path, name: str):
    section, *children = name.split("/")
    value = matlab_section(path, section)
    for key in children:
        value = value[key]
    return value


def flatten(value, prefix="", result=None) -> dict[str, object]:
    if result is None:
        result = {}
    if isinstance(value, dict):
        for key, child in value.items():
            flatten(child, f"{prefix}/{key}" if prefix else str(key), result)
    else:
        result[prefix] = value
    return result


def same_value(left, right) -> bool:
    try:
        a = np.asarray(left)
        b = np.asarray(right)
        if a.shape != b.shape:
            return False
        a = a.astype(np.float64)
        b = b.astype(np.float64)
        if np.isnan(a).any() or np.isnan(b).any():
            return False
        return bool(np.all(np.isclose(a, b, rtol=0, atol=TOL, equal_nan=False)))
    except (TypeError, ValueError):
        return str(left) == str(right)


def get_path(value: dict, path: str):
    for key in path.split("/"):
        value = value[key]
    return np.asarray(value, dtype=np.float64).reshape(-1)


def scalar(path: Path, key: str) -> float:
    values = np.asarray(matlab_value(path, key), dtype=np.float64).reshape(-1)
    if values.size != 1:
        raise ValueError(f"expected scalar {key}, got {values.size} values")
    return float(values[0])


def log_array(mat: h5py.File, name: str) -> np.ndarray:
    value = np.asarray(mat[f"log/{name}"][()], dtype=np.float64)
    if not np.isfinite(value).all():
        raise ValueError(f"nonfinite log field: {name}")
    return value


def first_difference(a: np.ndarray, b: np.ndarray, timeline: np.ndarray) -> dict | None:
    if not (np.isfinite(a).all() and np.isfinite(b).all() and np.isfinite(timeline).all()):
        raise ValueError("nonfinite value in first-difference comparison")
    per_step = np.max(np.abs(a - b), axis=0) if a.ndim > 1 else np.abs(a - b)
    indices = np.flatnonzero(per_step > TOL)
    if not len(indices):
        return None
    index = int(indices[0])
    return {"time_s": float(timeline[index]), "max_abs": float(per_step[index])}


def assert_equal(a: np.ndarray, b: np.ndarray, label: str) -> float:
    if a.shape != b.shape:
        raise ValueError(f"{label}: shape mismatch {a.shape} != {b.shape}")
    error = float(np.max(np.abs(a - b)))
    if error != 0:
        raise ValueError(f"{label}: expected exact equality, max abs error {error:.17g}")
    return error


def main() -> None:
    phase1 = ROOT / "reports" / "paper14_v2" / "phase1"
    r3_reports = ROOT / "experiments" / "paper14_v2_round3_xy_pcf_screen" / "reports"
    input_table_hashes = {}
    for relative, expected in INPUT_TABLE_SHA256.items():
        source = ROOT / relative
        actual = sha256(source)
        if actual != expected:
            raise ValueError(f"locked input table SHA mismatch: {source}")
        input_table_hashes[relative] = actual
    source_hashes = {}
    for relative, expected in SOURCE_SHA256.items():
        source = ROOT / relative
        actual = sha256(source)
        if actual != expected:
            raise ValueError(f"locked source SHA mismatch: {source}")
        source_hashes[relative] = actual
    candidate_rows = rows(phase1 / "candidate_dssm_raw_rescore.csv")
    baseline_rows = rows(phase1 / "baseline_b_raw_rescore.csv")
    lineage_rows = rows(phase1 / "mechanism_run_start_lineage.csv")
    r3_rows = rows(r3_reports / "round3_attempt_hashes.csv")
    results = []

    for scene in SCENES:
        if "TEST" in scene.upper() or "_VAL_" not in scene:
            raise ValueError(f"forbidden scene scope: {scene}")
        candidate = select(candidate_rows, scene_id=scene)
        baseline = select(baseline_rows, scene_id=scene)
        candidate_lineage = select(lineage_rows, scene_id=scene)
        r3_identity = select(r3_rows, scene_id=scene)
        if candidate["split"] != "VAL" or baseline["split"] != "VAL":
            raise ValueError(f"non-VAL rescore row: {scene}")

        candidate_raw = Path(candidate["raw_path"])
        baseline_raw = Path(baseline["resolved_raw_path"])
        r3_dir = ROOT / "experiments" / "paper14_v2_round3_xy_pcf_screen" / "runs" / scene / "attempt_01"
        r3_raw = r3_dir / "raw_run.mat"
        candidate_start = Path(candidate_lineage["run_start_path"])
        baseline_start = baseline_raw.parent / "run_start.mat"
        r3_start = r3_dir / "run_start.mat"
        files = (candidate_raw, baseline_raw, r3_raw, candidate_start, baseline_start, r3_start)
        if any("TEST" in str(path).upper() or not path.is_file() for path in files):
            raise ValueError(f"missing or forbidden input for {scene}")

        expected_hashes = (
            ("current_DSSM_raw", candidate_raw, candidate["raw_sha256_expected"]),
            ("B_raw", baseline_raw, baseline["resolved_raw_sha256_expected"]),
            ("R3_raw", r3_raw, r3_identity["raw_sha256"]),
            ("current_DSSM_run_start", candidate_start, candidate_lineage["run_start_sha256_before"]),
            ("B_run_start", baseline_start, B_RUN_START_SHA256[scene]),
            ("R3_run_start", r3_start, r3_identity["run_start_sha256"]),
        )
        hashes = {}
        for role, path, expected in expected_hashes:
            actual = sha256(path)
            if actual.lower() != expected.lower():
                raise ValueError(f"SHA mismatch: {path} {actual} != {expected}")
            hashes[role] = actual

        cfg_candidate_tree = matlab_section(candidate_start, "cfg")
        cfg_baseline_tree = matlab_section(baseline_start, "cfg")
        cfg_candidate = flatten(cfg_candidate_tree)
        cfg_baseline = flatten(cfg_baseline_tree)
        common = [
            key for key in cfg_candidate.keys() & cfg_baseline.keys()
            if any(key.startswith(prefix) for prefix in CORE_CFG_PREFIXES)
        ]
        missing = [
            key for key in cfg_candidate.keys() ^ cfg_baseline.keys()
            if any(key.startswith(prefix) for prefix in CORE_CFG_PREFIXES)
        ]
        mismatches = [
            key for key in common if not same_value(cfg_candidate[key], cfg_baseline[key])
        ]
        if len(common) != 60 or missing or mismatches:
            raise ValueError(
                f"{scene}: core cfg is not matched (common={len(common)}, missing={missing}, mismatches={mismatches})"
            )
        if not (
            scalar(baseline_start, "opts/formal_rbf_baseline") == 1
            and scalar(baseline_start, "opts/rbf_position_output_enabled") == 1
            and scalar(baseline_start, "opts/rbf_position_update_enabled") == 1
            and scalar(candidate_start, "opts/formal_rbf_baseline") == 1
            and scalar(candidate_start, "opts/rbf_position_output_enabled") == 0
            and scalar(candidate_start, "opts/rbf_position_update_enabled") == 0
            and scalar(candidate_start, "opts/stage1_position_runtime/update_enabled") == 1
        ):
            raise ValueError(f"{scene}: logged controller option contract differs from B/DSSM comparison")

        mass = float(get_path(cfg_baseline_tree, "plant/mass")[0])
        k1 = get_path(cfg_baseline_tree, "control/bs/position/k1")
        k2 = get_path(cfg_baseline_tree, "control/bs/position/k2")
        with h5py.File(candidate_raw, "r") as on, h5py.File(baseline_raw, "r") as b, h5py.File(r3_raw, "r") as r3:
            t_transition = log_array(on, "transition_time").reshape(-1)
            t_state = log_array(on, "time").reshape(-1)
            for label, mat in (("B", b), ("R3", r3)):
                assert_equal(t_transition, log_array(mat, "transition_time").reshape(-1), f"{scene} {label} transition clock")
                assert_equal(t_state, log_array(mat, "time").reshape(-1), f"{scene} {label} state clock")
                assert_equal(
                    log_array(on, "initial_state").reshape(-1),
                    log_array(mat, "initial_state").reshape(-1),
                    f"{scene} {label} initial state",
                )
            j = int(np.argmin(np.abs(t_transition - 0.020)))
            k = int(np.argmin(np.abs(t_state - 0.020)))
            if abs(t_transition[j] - 0.020) > 1e-12 or abs(t_state[k] - 0.020) > 1e-12:
                raise ValueError(f"{scene}: expected 20 ms state and transition")

            state_on = log_array(on, "state")[:, k]
            state_b = log_array(b, "state")[:, k]
            assert_equal(state_on, state_b, f"{scene} B/current-DSSM state at 20 ms")
            assert_equal(state_on, log_array(r3, "state")[:, k], f"{scene} R3/current-DSSM state at 20 ms")
            for field in REFERENCE_FIELDS:
                left = log_array(on, f"reference/{field}")
                right = log_array(b, f"reference/{field}")
                assert_equal(left, right, f"{scene} B/current-DSSM reference {field}")
                assert_equal(left, log_array(r3, f"reference/{field}"), f"{scene} R3/current-DSSM reference {field}")

            position = state_on[:3]
            velocity = state_on[3:6]
            ref_position = log_array(on, "reference/position")[:, j]
            ref_velocity = log_array(on, "reference/velocity")[:, j]
            ref_acceleration = log_array(on, "reference/acceleration")[:, j]
            error = ref_position - position
            rate_error = ref_velocity - velocity
            surface = ref_velocity + k1 * error - velocity
            nominal_acceleration = ref_acceleration + k1 * rate_error + error + k2 * surface
            nominal_force = mass * nominal_acceleration

            nominal_b = log_array(b, "position_bs_nominal_force_N")[:, j]
            nominal_on = log_array(on, "position_bs_nominal_force_N")[:, j]
            compensation_b = log_array(b, "position_compensation_applied_force_N")[:, j]
            compensation_on = log_array(on, "position_compensation_applied_force_N")[:, j]
            commanded_b = log_array(b, "position_commanded_force_N")[:, j]
            commanded_on = log_array(on, "position_commanded_force_N")[:, j]
            held_on = log_array(on, "stage1_position_held_force_I_N")[:, j]

            nominal_replay_error = max(
                float(np.max(np.abs(nominal_force - nominal_b))),
                float(np.max(np.abs(nominal_force - nominal_on))),
            )
            command_replay_error = max(
                float(np.max(np.abs(nominal_force - compensation_b - commanded_b))),
                float(np.max(np.abs(nominal_force - compensation_on - commanded_on))),
            )
            branch_residual = float(np.max(np.abs(commanded_b - commanded_on + compensation_b)))
            if nominal_replay_error > TOL or command_replay_error > TOL or branch_residual > TOL:
                raise ValueError(f"{scene}: same-state force replay failed")
            if np.max(np.abs(compensation_on)) != 0 or np.max(np.abs(held_on)) != 0:
                raise ValueError(f"{scene}: DSSM Head should still be held at zero at 20 ms")

            first_b_on_command = first_difference(
                log_array(b, "position_commanded_force_N"),
                log_array(on, "position_commanded_force_N"),
                t_transition,
            )
            first_b_on_state = first_difference(
                log_array(b, "state"), log_array(on, "state"), t_state
            )
            first_on_r3_command = first_difference(
                log_array(on, "position_commanded_force_N"),
                log_array(r3, "position_commanded_force_N"),
                t_transition,
            )
            first_on_r3_state = first_difference(
                log_array(on, "state"), log_array(r3, "state"), t_state
            )
            if first_b_on_command["time_s"] != 0.020 or first_b_on_state["time_s"] != 0.021:
                raise ValueError(f"{scene}: unexpected B/current-DSSM first split")
            if first_on_r3_command["time_s"] != 0.330 or first_on_r3_state["time_s"] != 0.331:
                raise ValueError(f"{scene}: unexpected current-DSSM/R3 first split")

            results.append(
                {
                    "scene_id": scene,
                    "input_hashes": hashes,
                    "matched_core_config_fields": len(common),
                    "core_config_mismatches": len(mismatches),
                    "run_start_formats": {
                        "B": mat_format(baseline_start),
                        "current_DSSM": mat_format(candidate_start),
                        "R3": mat_format(r3_start),
                    },
                    "position_rbf_options": {
                        "B_output_update": [
                            scalar(baseline_start, "opts/rbf_position_output_enabled"),
                            scalar(baseline_start, "opts/rbf_position_update_enabled"),
                        ],
                        "DSSM_output_update": [
                            scalar(candidate_start, "opts/rbf_position_output_enabled"),
                            scalar(candidate_start, "opts/rbf_position_update_enabled"),
                        ],
                    },
                    "initial_state_and_full_reference_exact": True,
                    "nominal_force_replay_max_abs_N": nominal_replay_error,
                    "command_force_replay_max_abs_N": command_replay_error,
                    "B_minus_DSSM_plus_B_RBF_residual_N": branch_residual,
                    "B_position_compensation_N_at_20ms": compensation_b.tolist(),
                    "DSSM_head_held_force_N_at_20ms": held_on.tolist(),
                    "first_B_vs_DSSM_position_command_difference": first_b_on_command,
                    "first_B_vs_DSSM_state_difference": first_b_on_state,
                    "first_DSSM_vs_R3_position_command_difference": first_on_r3_command,
                    "first_DSSM_vs_R3_state_difference": first_on_r3_state,
                }
            )

    print(
        json.dumps(
            {
                "scope": "VAL W15 only; read-only MAT/sidecar replay; no Plant or TEST",
                "input_table_sha256": input_table_hashes,
                "source_sha256": source_hashes,
                "results": results,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
