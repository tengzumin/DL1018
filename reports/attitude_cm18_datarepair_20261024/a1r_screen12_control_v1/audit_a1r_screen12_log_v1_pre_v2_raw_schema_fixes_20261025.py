"""Independent read-only audit for one released A1R SCREEN12 raw log.

This reads an already completed MATLAB v7.3 run. It never imports the runner,
engine, episode wrapper, training code, or Plant. A missing raw is an error and
does not create an audit result.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import h5py
import numpy as np
from scipy.spatial.transform import Rotation

SCENE_IDS = (
    "DL1018_DEV_T1_C01_W15", "DL1018_DEV_T1_C00_W03",
    "DL1018_DEV_T1_C15_W14", "DL1018_DEV_T1_C05_W06",
    "DL1018_DEV_T2_C00_W04", "DL1018_DEV_T2_C02_W15",
    "DL1018_VAL_T2_C15_W09", "DL1018_DEV_T2_C06_W07",
    "DL1018_DEV_T3_C00_W05", "DL1018_DEV_T3_C03_W15",
    "DL1018_DEV_T3_C15_W14", "DL1018_DEV_T3_C05_W02",
)
FIRST_SCENE = SCENE_IDS[0]
REPORT_REL = "reports/attitude_cm18_datarepair_20261024/a1r_screen12_control_v1"
RUNNER_REL = "experiments/attitude_cm18_datarepair_20261024/a1r_screen12_control_v1"
MANIFEST_REL = "reports/attitude_cm18_a1_20261024/CM18_A1_DEV_SCREEN12_v1.json"
PREP_REL = f"{REPORT_REL}/A1R_SCREEN12_CONTROL_PREPARATION_RESULT_v1.json"
APPROVAL_REL = f"{REPORT_REL}/A1R_SCREEN12_CONTROL_IMPLEMENTATION_APPROVAL_v1.json"
TASKBOOK_REL = f"{REPORT_REL}/A1R_SCREEN12_CONTROL_PREPARATION_TASKBOOK_v1_ZH.md"
C5_SNAPSHOT_REL = "experiments/position_axis_coordinate_c5_dev72_20261023/C5_DEV72_PREPARED_CFG_OPTS_v3.mat"
DEPLOYMENT_REL = "experiments/attitude_cm18_datarepair_20261024/postselection_a1r_v1/deployment_parameters_v1.json"
FIXTURE_REL = f"experiments/attitude_cm18_datarepair_20261024/a1r_screen12_control_v1/artifacts/a1r_forward_parity_fixture_v1.json"
PARITY_REL = "reports/attitude_cm18_datarepair_20261024/ROOT_A1R_ACTUAL_MATLAB_PARITY_v1.json"
ENGINE_REL = "experiments/attitude_cm18_a1_20261024/run_cm18_closed_loop_v1.m"
FORWARD_REL = "experiments/attitude_cm18_a1_20261024/matlab/cm18_a1_forward_v1.m"
PREDICTION_REL = "experiments/attitude_cm18_a1_20261024/delayed_prediction_step_candidate.m"
PREPARE_REL = f"{RUNNER_REL}/prepare_a1r_screen12_control_v1.m"
PREPARED_RUNNER_REL = f"{RUNNER_REL}/run_a1r_screen12_control_v1.m"
RUNNER_SOURCE_REL = f"{RUNNER_REL}/run_a1r_screen12_control_v2.m"

PINS = {
    "manifest": "fdca3f17c0f39d19eb5b08e94e7e5b1f148ec03cf861eacec64d86ab7922f923",
    "c5_snapshot": "842ef395569e675db6e139c2684d72b976946915e5e0a58b9b7f24ec10c1d24a",
    "deployment": "b3ab7a3d99df639d4cc0a10ec2b6fcd4622388f58c90c25424e472164ef38d23",
    "checkpoint": "5fa4308b6220e530e6c2e7a6f45c4b6e22ddddef80d1bc5cafdcf58564bc5ef3",
    "normalizer": "faf8748f640c944c745406247ab8486825966abd763088ad1f4e0cde626ad14c",
    "fixture": "04f79f473232341e5495ee77d19af09650e56976881b9cccf24901e7c1fae7f5",
    "parity": "32d7313954f415182166d3b8060ec8cd3f632e08c8139d48ac6439c6e5e92d55",
    "engine": "4f72db75f176e76de03f77b45e0b82f05ff0e3206907714f3c7faf786ba1092a",
    "forward": "1ff450f9be6a5c16fe98cb4f169ef9930f1b806fecfc10ad664c11ce940f42e9",
    "prediction": "48feebf934b8eb90b4424f2286aa857c48213d229714f30af99aacf53329549d",
}
EVENT_INDICES = np.arange(10, 19991, 10, dtype=np.int64)  # zero-based; MATLAB 11:10:19991
TOL = 1e-10
EXPECTED_J0 = np.array(
    [[0.003257553333333334, -2.168404344971009e-19, 0.0],
     [-2.168404344971009e-19, 0.0032575533333333334, 0.0],
     [0.0, 0.0, 0.006360648333333333]], dtype=np.float64
)

LOG_REQUIRED = (
    "time", "transition_time", "state", "reference/position", "reference/velocity",
    "reference/acceleration", "reference/yaw", "filtered_attitude_reference",
    "filtered_attitude_rate", "command_filter_acceleration_applied_rads2", "arms/command",
    "requested_generalized", "realized_generalized", "attitude_bs_nominal_torque_Nm",
    "attitude_compensation_applied_torque_Nm", "motor_saturated", "generalized_clipped",
    "tilt_limited", "status", "last_transition", "safety_stop_reason",
    "safety_position_error_persistence_s", "safety_tilt_persistence_s",
    "safety_body_rate_persistence_s", "cm18_attitude_enabled", "cm18_model_profile",
    "cm18_rbf_attitude_runtime_enabled", "cm18_rbf_attitude_output_enabled",
    "cm18_rbf_attitude_update_enabled", "cm18_dmax_rad_s2", "cm18_beta_rise_time_s",
    "cm18_fixed_inertia_J0_kgm2", "cm18_event_flag", "cm18_event_count",
    "cm18_event_input_18", "cm18_event_z_before_4", "cm18_event_u_current_4",
    "cm18_event_a_previous_requested_torque_mean_Nm", "cm18_event_raw_acceleration_rad_s2",
    "cm18_event_clipped_acceleration_rad_s2", "cm18_applied_acceleration_held_rad_s2",
    "cm18_beta_held", "cm18_compensation_torque_held_Nm", "cm18_clip_flag_held",
    "cm18_event_interval_s", "rbf_update_flag", "rbf_update_dt", "rbf_output_raw",
    "rbf_output_unclipped", "rbf_output_held", "rbf_attitude_output_limit_active",
    "attitude_rbf_compensation_torque_Nm", "attitude_fusion_enabled", "attitude_head_enabled",
    "stage1_position_coordinate_mask", "stage1_position_delayed_prediction_enabled",
    "stage1_position_beta_scale", "stage1_position_update_enabled",
    "stage1_position_update_dt_scale", "stage1_position_search_head_enabled",
    "stage1_position_search_head_type", "stage1_position_search_gamma",
    "stage1_position_search_kappa", "stage1_position_model_context_length",
    "stage1_position_pcf_coordination_enabled", "stage1_position_replacement_enabled",
    "stage1_position_search_initial_weight", "stage1_position_weight_initial",
)
POSITION_STATIC_LOG_FIELDS = (
    "stage1_position_coordinate_mask", "stage1_position_delayed_prediction_enabled",
    "stage1_position_beta_scale", "stage1_position_update_enabled",
    "stage1_position_update_dt_scale", "stage1_position_search_head_enabled",
    "stage1_position_search_head_type", "stage1_position_search_gamma",
    "stage1_position_search_kappa", "stage1_position_model_context_length",
    "stage1_position_pcf_coordination_enabled", "stage1_position_replacement_enabled",
    "stage1_position_search_initial_weight", "stage1_position_weight_initial",
)
ALLOWED_C5_OPTION_CHANGES = frozenset({
    "cm18_attitude_v1", "r2e_first_plant_step_marker", "rbf_attitude_enabled",
    "rbf_attitude_output_enabled", "rbf_attitude_update_enabled",
})


def need(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def repo_path(root: Path, value: str | Path) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = root / candidate
    result = candidate.resolve()
    if not result.is_relative_to(root.resolve()):
        raise ValueError(f"path escapes repository: {value}")
    return result


def same_path(a: str | Path, b: str | Path) -> bool:
    return os.path.normcase(os.path.normpath(str(a))).casefold() == os.path.normcase(os.path.normpath(str(b))).casefold()


def h5_text(dataset: h5py.Dataset) -> str:
    if bool(dataset.attrs.get("MATLAB_empty", False)):
        return ""
    array = np.asarray(dataset)
    if array.dtype.kind in "ui":
        return "".join(chr(int(x)) for x in array.reshape(-1) if int(x)).rstrip("\x00").strip()
    if array.dtype.kind in "US":
        return "".join(x.decode() if isinstance(x, bytes) else str(x) for x in array.reshape(-1)).rstrip("\x00").strip()
    raise ValueError(f"expected a MATLAB text dataset, got {dataset.name} ({array.dtype})")


def h5_scalar(file: h5py.File, path: str) -> Any:
    array = np.asarray(file[path])
    if array.size != 1:
        raise ValueError(f"expected one value at {path}, got {array.shape}")
    return array.reshape(-1)[0].item()


def h5_array(file: h5py.File, path: str, dtype: Any = np.float64) -> np.ndarray:
    value = file[path]
    if not isinstance(value, h5py.Dataset) or h5py.check_dtype(ref=value.dtype) is not None:
        raise ValueError(f"expected a numeric dataset at {path}")
    array = np.asarray(value)
    if array.ndim == 2:
        array = array.T
    return np.asarray(array, dtype=dtype)


def h5_bool(file: h5py.File, path: str) -> bool:
    value = h5_scalar(file, path)
    if value not in (0, 1, False, True):
        raise ValueError(f"expected a logical scalar at {path}")
    return bool(value)


def h5_text_at(file: h5py.File, path: str) -> str:
    value = file[path]
    if not isinstance(value, h5py.Dataset):
        raise ValueError(f"expected text dataset at {path}")
    return h5_text(value)


def max_abs(value: Any) -> float:
    array = np.asarray(value, dtype=np.float64)
    return float(np.max(np.abs(array))) if array.size else 0.0


def assert_close(actual: Any, expected: Any, tolerance: float, label: str) -> float:
    a, b = np.asarray(actual, dtype=np.float64), np.asarray(expected, dtype=np.float64)
    if a.shape != b.shape:
        raise ValueError(f"{label}: shape {a.shape} != {b.shape}")
    delta = max_abs(a - b)
    if not np.isfinite(delta) or delta > tolerance:
        raise ValueError(f"{label}: max_abs_delta={delta:.17g} > {tolerance:.17g}")
    return delta


def _same_h5_node(a: h5py.Group | h5py.Dataset, b: h5py.Group | h5py.Dataset,
                  label: str, seen: set[tuple[str, str]] | None = None) -> None:
    if seen is None:
        seen = set()
    pair = (a.name, b.name)
    if pair in seen:
        return
    seen.add(pair)
    if isinstance(a, h5py.Group) != isinstance(b, h5py.Group):
        raise ValueError(f"{label}: HDF5 node kinds differ")
    if isinstance(a, h5py.Group):
        if set(a.keys()) != set(b.keys()):
            raise ValueError(f"{label}: HDF5 child fields differ")
        for key in a.keys():
            _same_h5_node(a[key], b[key], f"{label}/{key}", seen)
        return
    if a.shape != b.shape:
        raise ValueError(f"{label}: HDF5 shapes differ: {a.shape} != {b.shape}")
    ref_a, ref_b = h5py.check_dtype(ref=a.dtype), h5py.check_dtype(ref=b.dtype)
    if ref_a is not None or ref_b is not None:
        if ref_a is None or ref_b is None:
            raise ValueError(f"{label}: one HDF5 dataset is a reference array and the other is not")
        refs_a, refs_b = np.asarray(a[()]).reshape(-1), np.asarray(b[()]).reshape(-1)
        for index, (ra, rb) in enumerate(zip(refs_a, refs_b, strict=True)):
            if bool(ra) != bool(rb):
                raise ValueError(f"{label}[{index}]: null reference mismatch")
            if bool(ra):
                _same_h5_node(a.file[ra], b.file[rb], f"{label}[{index}]", seen)
        return
    left, right = np.asarray(a[()]), np.asarray(b[()])
    try:
        equal = np.array_equal(left, right, equal_nan=True)
    except TypeError:
        equal = np.array_equal(left, right)
    if not equal:
        raise ValueError(f"{label}: values differ")


def assert_h5_equal(file_a: h5py.File, path_a: str, file_b: h5py.File, path_b: str,
                    label: str, ignore_children: frozenset[str] = frozenset()) -> None:
    a, b = file_a[path_a], file_b[path_b]
    if not isinstance(a, h5py.Group) or not isinstance(b, h5py.Group):
        _same_h5_node(a, b, label)
        return
    keys_a = set(a.keys()) - set(ignore_children)
    keys_b = set(b.keys()) - set(ignore_children)
    if keys_a != keys_b:
        raise ValueError(f"{label}: fields differ: {sorted(keys_a ^ keys_b)}")
    for key in sorted(keys_a):
        _same_h5_node(a[key], b[key], f"{label}/{key}")


def verify_inventory(root: Path, inventory: list[dict[str, Any]]) -> int:
    if not inventory:
        raise ValueError("C5 active source inventory is empty")
    seen: set[str] = set()
    for entry in inventory:
        if not isinstance(entry, dict) or not entry.get("path") or not entry.get("sha256"):
            raise ValueError("malformed C5 source inventory entry")
        path = repo_path(root, str(entry["path"]))
        key = str(path).casefold()
        if key in seen:
            raise ValueError(f"duplicate C5 source inventory path: {path}")
        seen.add(key)
        if not path.is_file() or sha256(path).lower() != str(entry["sha256"]).lower():
            raise ValueError(f"C5 source inventory SHA mismatch: {path}")
    return len(inventory)


def forward(x: np.ndarray, parameters: dict[str, Any]) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64)
    w1, b1 = np.asarray(parameters["W1"], float), np.asarray(parameters["b1"], float).reshape(32)
    w2, b2 = np.asarray(parameters["W2"], float), np.asarray(parameters["b2"], float).reshape(32)
    w3, b3 = np.asarray(parameters["W3"], float), np.asarray(parameters["b3"], float).reshape(24)
    mean = np.asarray(parameters["input_mean"], float).reshape(18)
    std = np.asarray(parameters["input_std"], float).reshape(18)
    axis_rms = np.asarray(parameters["train_axis_rms_rad_s2"], float).reshape(3)
    if (x.ndim != 2 or x.shape[1] != 18 or w1.shape != (32, 18) or w2.shape != (32, 32)
            or w3.shape != (24, 32) or std.shape != (18,) or np.any(std <= 0)):
        raise ValueError("A1R deployment forward parameter shape/value mismatch")
    h1 = np.tanh((x - mean) / std @ w1.T + b1)
    h2 = np.tanh(h1 @ w2.T + b2)
    coeff = (h2 @ w3.T + b3).reshape(-1, 3, 8)
    basis = np.column_stack((x[:, 11:15] / 2.0, x[:, 7:11]))
    return np.einsum("nck,nk->nc", coeff, basis) * axis_rms


def attitude_bs_alpha(state: np.ndarray, eta_ref: np.ndarray, rate_ref: np.ndarray,
                      acc_ref: np.ndarray, k1: np.ndarray, k2: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Mirror attitude_bs_step.m with fixed Jdot handled by caller as zero."""
    phi, theta = float(state[6]), float(np.clip(state[7], -np.pi / 2 + 1e-4, np.pi / 2 - 1e-4))
    omega = state[9:12]
    sphi, cphi = np.sin(phi), np.cos(phi)
    ttheta, sectheta = np.tan(theta), 1.0 / np.cos(theta)
    t = np.array([[1.0, sphi * ttheta, cphi * ttheta],
                  [0.0, cphi, -sphi],
                  [0.0, sphi * sectheta, cphi * sectheta]])
    eta_rate = t @ omega
    tphi = np.array([[0.0, cphi * ttheta, -sphi * ttheta],
                     [0.0, -sphi, -cphi],
                     [0.0, cphi * sectheta, -sphi * sectheta]])
    ttheta_d = np.array([[0.0, sphi * sectheta**2, cphi * sectheta**2],
                         [0.0, 0.0, 0.0],
                         [0.0, sphi * sectheta * ttheta, cphi * sectheta * ttheta]])
    tdot = tphi * eta_rate[0] + ttheta_d * eta_rate[1]
    error = np.arctan2(np.sin(eta_ref - state[6:9]), np.cos(eta_ref - state[6:9]))
    de = rate_ref - eta_rate
    alpha = rate_ref + k1 * error
    z2 = alpha - eta_rate
    alpha_dot = acc_ref + k1 * de
    eta_acc = alpha_dot + error + k2 * z2
    return np.linalg.solve(t, eta_acc - tdot @ omega), omega


def run_durations(mask: np.ndarray, dt_s: float) -> tuple[float, float]:
    value = np.asarray(mask, dtype=bool).reshape(-1)
    edges = np.diff(np.r_[False, value, False].astype(np.int8))
    starts, ends = np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)
    runs = ends - starts
    return (float(runs.max() * dt_s) if runs.size else 0.0,
            float(runs[-1] * dt_s) if runs.size and value[-1] else 0.0)


def scoring(state: np.ndarray, ref_pos: np.ndarray, eta_ref: np.ndarray,
            rate_ref: np.ndarray, time: np.ndarray) -> dict[str, Any]:
    n = len(time)
    state_left = state[:n]
    pos_error = ref_pos[:n] - state_left[:, :3]
    actual_euler = state_left[:, 6:9]
    # The frozen scorer compares actual and filtered reference rotations in ZYX order.
    actual = Rotation.from_euler("ZYX", actual_euler[:, [2, 1, 0]])
    desired = Rotation.from_euler("ZYX", eta_ref[:n, [2, 1, 0]])
    relative = actual.inv() * desired
    angle = relative.magnitude()
    phi, theta = eta_ref[:n, 0], eta_ref[:n, 1]
    a, b, c = rate_ref[:n].T
    ref_body_rate = np.column_stack((a - np.sin(theta) * c,
                                     np.cos(phi) * b + np.sin(phi) * np.cos(theta) * c,
                                     -np.sin(phi) * b + np.cos(phi) * np.cos(theta) * c))
    rate_error = state_left[:, 9:12] - relative.apply(ref_body_rate)
    euler_error = np.arctan2(np.sin(eta_ref[:n] - actual_euler), np.cos(eta_ref[:n] - actual_euler))
    periods = {"ALL_0_20": (time >= 0) & (time < 20),
               "PRE_0_5": (time >= 0) & (time < 5),
               "POST_5_20": (time >= 5) & (time < 20)}
    rows: dict[str, Any] = {}
    for name, mask in periods.items():
        p, e, w = pos_error[mask], angle[mask], rate_error[mask]
        rows[name] = {
            "samples": int(mask.sum()),
            "position_Q_rmse_m": float(np.sqrt(np.mean(np.sum(p * p, axis=1)))),
            "position_axis_rmse_m": np.sqrt(np.mean(p * p, axis=0)).tolist(),
            "position_peak_m": float(np.linalg.norm(p, axis=1).max()),
            "SO3_rmse_rad": float(np.sqrt(np.mean(e * e))),
            "SO3_rmse_deg": float(np.rad2deg(np.sqrt(np.mean(e * e)))),
            "SO3_peak_deg": float(np.rad2deg(e.max())),
            "Euler_axis_rmse_rad": np.sqrt(np.mean(euler_error[mask] ** 2, axis=0)).tolist(),
            "transported_body_rate_vector_rmse_rad_s": float(np.sqrt(np.mean(np.sum(w * w, axis=1)))),
            "transported_body_rate_axis_rmse_rad_s": np.sqrt(np.mean(w * w, axis=0)).tolist(),
        }
    return rows


def load_scene_row(root: Path, scene_id: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    manifest_path = repo_path(root, MANIFEST_REL)
    prep_path = repo_path(root, PREP_REL)
    manifest = read_json(manifest_path)
    prep = read_json(prep_path)
    need(sha256(manifest_path).lower() == PINS["manifest"], "SCREEN12 manifest SHA mismatch")
    need(manifest.get("schema") == "CM18_A1_FUTURE_DEVELOPMENT_SCREEN12_V1", "SCREEN12 manifest schema mismatch")
    manifest_rows = [row for row in manifest.get("scenes", []) if row.get("scene_id") == scene_id]
    prep_rows = [row for row in prep.get("scene_rows", []) if row.get("scene_id") == scene_id]
    need(len(manifest_rows) == len(prep_rows) == 1, f"scene {scene_id} is not uniquely bound")
    row, prep_row = manifest_rows[0], prep_rows[0]
    need(row.get("baseline_C5_raw_sha256", "").lower() == prep_row.get("baseline_C5_raw_sha256", "").lower(),
         "preparation baseline SHA differs from SCREEN12 manifest")
    need(same_path(row["baseline_C5_raw_path"], prep_row["baseline_C5_raw_path"]),
         "preparation baseline path differs from SCREEN12 manifest")
    need(prep.get("schema") == "CM18_A1R_SCREEN12_CONTROL_PREPARATION_V1"
         and prep.get("status") == "PREPARED_A1R_SCREEN12_CONTROL_NO_PLANT_V1"
         and prep.get("scene_count") == 12 and prep.get("plant_calls") == 0
         and prep.get("engine_calls") == 0 and prep.get("training_steps") == 0
         and prep.get("optimizer_steps") == 0 and prep.get("TEST_accessed") is False,
         "A1R preparation scope/status mismatch")
    return row, prep_row, prep


def verify_release(root: Path, scene_id: str, index: int, prep: dict[str, Any],
                   prep_row: dict[str, Any]) -> tuple[dict[str, Any], Path, dict[str, str]]:
    report = repo_path(root, REPORT_REL)
    release_path = report / f"ROOT_A1R_SCREEN12_CONTROL_RELEASE_{scene_id}_v2.json"
    release = read_json(release_path)
    release_sha = sha256(release_path).lower()
    need(release.get("schema") == "A1R_SCREEN12_CONTROL_ROOT_RELEASE_V2"
         and release.get("decision") == "APPROVE_ONE_A1R_SCREEN12_FLIGHT"
         and release.get("plant_authorized") is True
         and release.get("scene_id") == scene_id and release.get("sequence_index") == index + 1
         and release.get("training_authorized") is False
         and release.get("optimizer_steps_authorized") == 0
         and release.get("TEST_accessed") is False,
         "ROOT release scope does not approve exactly this scene")
    identity_files = {
        "taskbook_sha256": TASKBOOK_REL,
        "approval_sha256": APPROVAL_REL,
        "preparation_result_sha256": PREP_REL,
        "screen12_manifest_sha256": MANIFEST_REL,
        "c5_snapshot_sha256": C5_SNAPSHOT_REL,
        "deployment_parameters_sha256": DEPLOYMENT_REL,
        "forward_fixture_sha256": FIXTURE_REL,
        "matlab_parity_receipt_sha256": PARITY_REL,
        "engine_sha256": ENGINE_REL,
        "forward_sha256": FORWARD_REL,
        "prediction_helper_sha256": PREDICTION_REL,
        "prepare_script_sha256": PREPARE_REL,
        "runner_sha256": RUNNER_SOURCE_REL,
    }
    actual: dict[str, str] = {}
    for field, relative in identity_files.items():
        path = repo_path(root, relative)
        if not path.is_file():
            raise FileNotFoundError(f"released identity file is missing: {relative}")
        actual[field] = sha256(path).lower()
        need(actual[field] == str(release.get(field, "")).lower(), f"ROOT release pin mismatch: {field}")
    for field, pin_name in (("screen12_manifest_sha256", "manifest"), ("c5_snapshot_sha256", "c5_snapshot"),
                            ("deployment_parameters_sha256", "deployment"),
                            ("forward_fixture_sha256", "fixture"), ("matlab_parity_receipt_sha256", "parity"),
                            ("engine_sha256", "engine"), ("forward_sha256", "forward"),
                            ("prediction_helper_sha256", "prediction")):
        need(actual[field] == PINS[pin_name], f"fixed taskbook pin mismatch: {field}")
    need(str(release.get("c5_active_source_inventory_sha256", "")).lower()
         == str(prep.get("c5_active_source_inventory_sha256", "")).lower(),
         "ROOT release does not bind the prepared C5 active-source inventory")
    model = prep.get("model_identity", {})
    need(model.get("selected_step") == 40000
         and str(model.get("checkpoint_sha256", "")).lower() == PINS["checkpoint"]
         and str(model.get("normalizer_float64_sha256", "")).lower() == PINS["normalizer"]
         and str(release.get("checkpoint_sha256", "")).lower() == PINS["checkpoint"]
         and release.get("selected_step") == 40000
         and str(release.get("normalizer_float64_sha256", "")).lower() == PINS["normalizer"],
         "released A1R checkpoint/step/normalizer identity mismatch")
    prepared_runner = repo_path(root, PREPARED_RUNNER_REL)
    need(prepared_runner.is_file()
         and sha256(prepared_runner).lower() == str(prep.get("runner_sha256", "")).lower()
         and str(release.get("prepared_runner_sha256", "")).lower() == str(prep.get("runner_sha256", "")).lower(),
         "historical preparation runner identity mismatch")
    need(str(release.get("baseline_C5_raw_sha256", "")).lower()
         == str(prep_row.get("baseline_C5_raw_sha256", "")).lower(),
         "ROOT release scene-specific baseline raw pin mismatch")
    need(str(release.get("prepared_snapshot_sha256", "")).lower()
         == str(prep_row.get("prepared_snapshot_sha256", "")).lower(),
         "ROOT release prepared snapshot SHA mismatch")
    prior = release.get("prior_audit_sha256", [])
    need(isinstance(prior, list) and len(prior) == index, "ROOT release prior-audit list is incomplete")
    for prior_index, prior_scene in enumerate(SCENE_IDS[:index]):
        prior_path = repo_path(root, f"{REPORT_REL}/A1R_SCREEN12_LOG_AUDIT_{prior_scene}_v1.json")
        prior_attempt = "attempt_02" if prior_scene == FIRST_SCENE else "attempt_01"
        prior_status = repo_path(root, f"{RUNNER_REL}/runs/{prior_scene}/{prior_attempt}/run_status.json")
        need(prior_path.is_file() and prior_status.is_file(), f"prior scene evidence is missing: {prior_scene}")
        need(sha256(prior_path).lower() == str(prior[prior_index]).lower(), f"prior audit SHA mismatch: {prior_scene}")
        audit, status = read_json(prior_path), read_json(prior_status)
        need(audit.get("status") == "PASS" and audit.get("scene_id") == prior_scene
             and status.get("schema") == "A1R_SCREEN12_CONTROL_RUN_STATUS_V2"
             and status.get("status") == "RUN_COMPLETE_PENDING_ROOT_AUDIT"
             and status.get("scene_id") == prior_scene
             and status.get("prepared_runner_sha256", "").lower() == str(prep.get("runner_sha256", "")).lower()
             and status.get("execution_runner_sha256", "").lower() == actual["runner_sha256"]
             and status.get("plant_calls") == 1 and status.get("training_steps") == 0
             and status.get("optimizer_steps") == 0 and status.get("TEST_accessed") is False
             and str(audit.get("raw_sha256", "")).lower() == str(status.get("raw_sha256", "")).lower(),
             f"prior scene is not independently audited PASS: {prior_scene}")
    return release, release_path, actual


def event_audit(root: Path, scene_id: str, manifest_row: dict[str, Any], prep_row: dict[str, Any],
                prep: dict[str, Any], release: dict[str, Any], release_path: Path,
                identity_sha: dict[str, str]) -> dict[str, Any]:
    run_root = repo_path(root, RUNNER_REL)
    attempt_name = "attempt_02" if scene_id == FIRST_SCENE else "attempt_01"
    attempt = run_root / "runs" / scene_id / attempt_name
    raw_path, start_path = attempt / "raw_run.mat", attempt / "run_start.mat"
    status_path, first_marker = attempt / "run_status.json", attempt / "first_plant_step.marker"
    for required in (raw_path, start_path, status_path, first_marker):
        if not required.is_file():
            raise FileNotFoundError(f"required completed-run artifact is missing: {required}")
    raw_sha, start_sha = sha256(raw_path).lower(), sha256(start_path).lower()
    status = read_json(status_path)
    need(status.get("schema") == "A1R_SCREEN12_CONTROL_RUN_STATUS_V2"
         and status.get("status") == "RUN_COMPLETE_PENDING_ROOT_AUDIT"
         and status.get("scene_id") == scene_id
         and status.get("log_status") == "STABLE"
         and status.get("safety_stop_reason") == ""
         and status.get("transitions") == 20000 and status.get("state_samples") == 20001
         and status.get("cm18_events") == 1999
         and str(status.get("raw_sha256", "")).lower() == raw_sha
         and str(status.get("run_start_sha256", "")).lower() == start_sha
         and status.get("first_plant_step_confirmed") is True
         and status.get("plant_invocation_entered") is True and status.get("plant_calls") == 1
         and status.get("training_steps") == 0 and status.get("optimizer_steps") == 0
         and status.get("TEST_accessed") is False,
         "runner status does not describe one complete released run")
    need(same_path(status.get("raw_path", ""), raw_path), "runner status raw_path mismatch")
    need("first_plant_transition=1" in first_marker.read_text(encoding="utf-8-sig"),
         "first-Plant-transition marker is absent or malformed")
    baseline_path = repo_path(root, manifest_row["baseline_C5_raw_path"])
    snapshot_path = repo_path(root, prep_row["prepared_snapshot_path"])
    need(sha256(baseline_path).lower() == str(manifest_row["baseline_C5_raw_sha256"]).lower()
         and sha256(snapshot_path).lower() == str(prep_row["prepared_snapshot_sha256"]).lower(),
         "baseline C5 raw or prepared snapshot SHA mismatch")
    need(sha256(baseline_path).lower() == str(release["baseline_C5_raw_sha256"]).lower()
         and sha256(snapshot_path).lower() == str(release["prepared_snapshot_sha256"]).lower(),
         "per-scene ROOT release does not bind these raw/snapshot bytes")
    deployment = read_json(repo_path(root, DEPLOYMENT_REL))
    parameters = deployment.get("parameters", {})
    need(deployment.get("schema") == "CM18_A1R_DEPLOYMENT_PARAMETERS_V1"
         and str(deployment.get("identity", {}).get("checkpoint_sha256", "")).lower() == PINS["checkpoint"]
         and deployment.get("identity", {}).get("selected_step") == 40000,
         "deployment parameter file identity mismatch")
    inventory = prep.get("c5_source_identity", {}).get("c5_active_source_inventory", [])
    inventory_count = verify_inventory(root, inventory)

    with h5py.File(raw_path, "r") as raw, h5py.File(start_path, "r") as standalone, \
            h5py.File(baseline_path, "r") as baseline, h5py.File(snapshot_path, "r") as snapshot, \
            h5py.File(repo_path(root, C5_SNAPSHOT_REL), "r") as c5_snapshot:
        for path in ("log", "scene", "runStart", "runIdentity"):
            need(path in raw, f"raw MAT missing top-level {path}")
        need("runStart" in standalone, "standalone run_start MAT has no runStart variable")
        # The raw embeds the exact runStart record also saved separately by the runner.
        assert_h5_equal(raw, "runStart", standalone, "runStart", "raw versus standalone runStart")
        run_start, run_identity, log = raw["runStart"], raw["runIdentity"], raw["log"]
        need(h5_text_at(raw, "scene/scene_id") == scene_id
             and h5_text_at(raw, "log/scene_id") == scene_id
             and h5_text_at(raw, "runStart/scene_id") == scene_id
             and h5_text_at(raw, "runIdentity/scene_id") == scene_id,
             "raw scene_id is inconsistent across scene/log/start/identity")
        need(h5_text_at(raw, "runStart/schema") == "A1R_SCREEN12_CONTROL_RUN_START_V2"
             and h5_text_at(raw, "runIdentity/schema") == "A1R_SCREEN12_CONTROL_RUN_IDENTITY_V2",
             "raw run-start or run-identity schema mismatch")
        sequence_index = SCENE_IDS.index(scene_id) + 1
        need(int(h5_scalar(raw, "runStart/sequence_index")) == sequence_index
             and int(h5_scalar(raw, "runIdentity/sequence_index")) == sequence_index,
             "raw sequence index mismatch")
        expected_release_sha = sha256(release_path).lower()
        for path in ("runStart/root_release_sha256", "runIdentity/root_release_sha256"):
            need(h5_text_at(raw, path).lower() == expected_release_sha, f"raw is not bound to ROOT release: {path}")
        need(h5_text_at(raw, "runStart/prepared_runner_sha256").lower()
             == str(release.get("prepared_runner_sha256", "")).lower()
             and h5_text_at(raw, "runIdentity/prepared_runner_sha256").lower()
             == str(release.get("prepared_runner_sha256", "")).lower()
             and h5_text_at(raw, "runStart/execution_runner_sha256").lower()
             == identity_sha["runner_sha256"]
             and h5_text_at(raw, "runIdentity/execution_runner_sha256").lower()
             == identity_sha["runner_sha256"]
             and str(status.get("prepared_runner_sha256", "")).lower()
             == str(release.get("prepared_runner_sha256", "")).lower()
             and str(status.get("execution_runner_sha256", "")).lower()
             == identity_sha["runner_sha256"],
             "V2 prepared-versus-execution runner identities are inconsistent")
        need(same_path(h5_text_at(raw, "runStart/root_release_path"), release_path),
             "runStart root release path mismatch")
        for path, digest in (("runStart/preparation_result_sha256", identity_sha["preparation_result_sha256"]),
                             ("runStart/screen12_manifest_sha256", identity_sha["screen12_manifest_sha256"]),
                             ("runStart/baseline_C5_raw_sha256", str(manifest_row["baseline_C5_raw_sha256"]).lower()),
                             ("runStart/prepared_snapshot_sha256", str(prep_row["prepared_snapshot_sha256"]).lower())):
            need(h5_text_at(raw, path).lower() == digest.lower(), f"runStart identity mismatch: {path}")
        need(same_path(h5_text_at(raw, "runStart/baseline_C5_raw_path"), baseline_path)
             and same_path(h5_text_at(raw, "runStart/prepared_snapshot_path"), snapshot_path),
             "runStart baseline or prepared-snapshot path mismatch")
        need(int(h5_scalar(raw, "runStart/training_steps")) == 0
             and int(h5_scalar(raw, "runStart/optimizer_steps")) == 0
             and not h5_bool(raw, "runStart/TEST_accessed")
             and int(h5_scalar(raw, "runIdentity/training_steps")) == 0
             and int(h5_scalar(raw, "runIdentity/optimizer_steps")) == 0
             and not h5_bool(raw, "runIdentity/TEST_accessed"),
             "raw run identity has training/optimizer/TEST activity")
        # cfg is byte-for-value identical to the frozen C5 snapshot. Only A1R's model,
        # marker and three RBF-off switches are allowed to differ in opts.
        assert_h5_equal(raw, "runStart/cfg", c5_snapshot, "cfg", "C5 cfg")
        assert_h5_equal(raw, "runStart/opts", c5_snapshot, "opts", "C5 options",
                        ignore_children=ALLOWED_C5_OPTION_CHANGES)
        assert_h5_equal(raw, "runStart/cfg", snapshot, "cfg", "prepared cfg")
        assert_h5_equal(raw, "runStart/opts", snapshot, "opts", "prepared options",
                        ignore_children=frozenset({"r2e_first_plant_step_marker"}))
        assert_h5_equal(raw, "scene", baseline, "scene", "C5 original scene")
        assert_h5_equal(raw, "scene", snapshot, "scene", "prepared scene")
        assert_h5_equal(raw, "runStart/scene_identity", snapshot, "sceneIdentity", "prepared scene identity")
        assert_h5_equal(raw, "runIdentity/scene_identity", snapshot, "sceneIdentity", "run scene identity")
        assert_h5_equal(raw, "runStart/model_identity", snapshot, "modelIdentity", "prepared model identity")
        assert_h5_equal(raw, "runIdentity/model_identity", snapshot, "modelIdentity", "run model identity")

        for flag in ("rbf_attitude_enabled", "rbf_attitude_output_enabled", "rbf_attitude_update_enabled"):
            need(not h5_bool(raw, f"runStart/opts/{flag}"), f"RBF option {flag} is enabled")
        need(h5_bool(raw, "runStart/opts/cm18_attitude_v1/enabled"), "CM18 A1R model is not enabled")
        runtime_model = raw["runStart/opts/cm18_attitude_v1/model"]
        for name, expected in parameters.items():
            actual = h5_array(raw, f"runStart/opts/cm18_attitude_v1/model/{name}")
            expected_array = np.asarray(expected, dtype=np.float64)
            if actual.size and expected_array.size and actual.ndim <= 2 and expected_array.ndim <= 2:
                if actual.size == expected_array.size and (actual.ndim == 1 or 1 in actual.shape) and (expected_array.ndim == 1 or 1 in expected_array.shape):
                    actual, expected_array = actual.reshape(-1), expected_array.reshape(-1)
            assert_close(actual, expected_array, 0.0, f"runtime deployment parameter {name}")
        identity = prep.get("model_identity", {})
        for field, expected in (("checkpoint_sha256", PINS["checkpoint"]),
                                ("deployment_parameters_sha256", PINS["deployment"]),
                                ("normalizer_float64_sha256", PINS["normalizer"])):
            need(h5_text_at(raw, f"runStart/model_identity/{field}").lower() == expected,
                 f"raw model identity mismatch: {field}")
        need(int(h5_scalar(raw, "runStart/model_identity/selected_step")) == 40000
             and identity.get("selected_step") == 40000,
             "raw selected model step is not 40000")

        for name in LOG_REQUIRED:
            need(name in log, f"engine log is missing required field: log/{name}")
        n, dt_s = 20000, 0.001
        time = h5_array(raw, "log/time").reshape(-1)
        transition_time = h5_array(raw, "log/transition_time").reshape(-1)
        state = h5_array(raw, "log/state")
        ref_position = h5_array(raw, "log/reference/position")
        filtered_attitude = h5_array(raw, "log/filtered_attitude_reference")
        filtered_rate = h5_array(raw, "log/filtered_attitude_rate")
        requested = h5_array(raw, "log/requested_generalized")
        realized = h5_array(raw, "log/realized_generalized")
        nominal_torque = h5_array(raw, "log/attitude_bs_nominal_torque_Nm")
        applied_torque = h5_array(raw, "log/attitude_compensation_applied_torque_Nm")
        command = h5_array(raw, "scene/arms/command")
        logged_command = h5_array(raw, "log/arms/command")
        ref_velocity = h5_array(raw, "log/reference/velocity")
        ref_acceleration = h5_array(raw, "log/reference/acceleration")
        ref_yaw = h5_array(raw, "log/reference/yaw").reshape(-1)
        arrays = (time, transition_time, state, ref_position, filtered_attitude, filtered_rate,
                  requested, realized, nominal_torque, applied_torque, command, logged_command,
                  ref_velocity, ref_acceleration, ref_yaw)
        need(all(np.isfinite(value).all() for value in arrays), "non-finite value in a required trajectory/log array")
        need(time.shape == (n + 1,) and transition_time.shape == (n,)
             and state.shape == (n + 1, 12) and ref_position.shape == (n + 1, 3)
             and filtered_attitude.shape == (n, 3) and filtered_rate.shape == (n, 3)
             and requested.shape == realized.shape == (n, 4)
             and nominal_torque.shape == applied_torque.shape == (n, 3)
             and command.shape == logged_command.shape == (n + 1, 4)
             and ref_velocity.shape == ref_acceleration.shape == (n + 1, 3)
             and ref_yaw.shape == (n + 1,),
             "trajectory/log array shape mismatch")
        need(abs(float(h5_scalar(raw, "runStart/cfg/plant/dt")) - dt_s) < 1e-15
             and abs(time[0]) < 1e-12 and abs(time[-1] - 20.0) < 1e-12
             and max_abs(np.diff(time) - dt_s) < 1e-12
             and max_abs(transition_time - time[:-1]) < 1e-12,
             "expected 20,001 states and 20,000 left-aligned 1 ms transitions")
        assert_close(logged_command, command, 0.0, "scene versus logged morphology command")
        assert_close(h5_array(raw, "log/reference/position"), h5_array(raw, "scene/reference/position"), 0.0,
                     "logged reference position versus original C5 scene")
        assert_close(h5_array(raw, "log/reference/velocity"), h5_array(raw, "scene/reference/velocity"), 0.0,
                     "logged reference velocity versus original C5 scene")
        assert_close(h5_array(raw, "log/reference/acceleration"), h5_array(raw, "scene/reference/acceleration"), 0.0,
                     "logged reference acceleration versus original C5 scene")
        assert_close(h5_array(raw, "log/reference/yaw"), h5_array(raw, "scene/reference/yaw"), 0.0,
                     "logged yaw reference versus original C5 scene")
        need(h5_text_at(raw, "log/status") == "STABLE"
             and int(h5_scalar(raw, "log/last_transition")) == n
             and h5_text_at(raw, "log/safety_stop_reason") == "",
             "engine log is not a complete stable run")

        # Both run options and the actual engine log must show all three legacy RBF paths off.
        for field in ("cm18_rbf_attitude_runtime_enabled", "cm18_rbf_attitude_output_enabled",
                      "cm18_rbf_attitude_update_enabled", "attitude_fusion_enabled", "attitude_head_enabled"):
            need(not h5_bool(raw, f"log/{field}"), f"actual engine log shows enabled legacy path: {field}")
        for field in ("rbf_update_flag", "rbf_attitude_output_limit_active"):
            need(not np.any(h5_array(raw, f"log/{field}", dtype=bool)), f"legacy RBF activity flag is nonzero: {field}")
        for field in ("rbf_update_dt", "rbf_output_raw", "rbf_output_unclipped", "rbf_output_held",
                      "attitude_rbf_compensation_torque_Nm"):
            value = h5_array(raw, f"log/{field}")
            need(np.all(value == 0.0), f"legacy RBF output/update data is nonzero: {field}")
        need(h5_bool(raw, "log/cm18_attitude_enabled")
             and h5_text_at(raw, "log/cm18_model_profile") == "CM18_A1_MLP32x32_TO24_FIXED_J0",
             "CM18 A1R model profile or enabled flag mismatch")

        # Position controller stays C5-identical in cfg/options/source and static runtime fields.
        need(np.array_equal(h5_array(raw, "runStart/opts/position_coordinate_mask").reshape(-1),
                            np.array([1.0, 1.0, 0.0]))
             and np.array_equal(h5_array(raw, "log/stage1_position_coordinate_mask").reshape(-1),
                                np.array([1.0, 1.0, 0.0])),
             "C5 position-coordinate mask changed")
        for field in POSITION_STATIC_LOG_FIELDS:
            assert_h5_equal(raw, f"log/{field}", baseline, f"log/{field}", f"C5 position static log {field}")

        event_flag = h5_array(raw, "log/cm18_event_flag", dtype=bool).reshape(-1)
        event_rows = np.flatnonzero(event_flag)
        need(np.array_equal(event_rows, EVENT_INDICES)
             and int(h5_scalar(raw, "log/cm18_event_count")) == len(EVENT_INDICES),
             "expected exactly 1,999 CM18 events at MATLAB transitions 11:10:19991")
        need(max_abs(transition_time[event_rows] - (event_rows * dt_s)) < 1e-12,
             "CM18 event times do not match the 100 Hz transition grid")
        event_interval = h5_array(raw, "log/cm18_event_interval_s").reshape(-1)
        need(np.all(event_interval[~event_flag] == 0.0)
             and max_abs(event_interval[event_flag] - 0.01) < 1e-12,
             "CM18 event interval is not 10 ms")

        dmax = h5_array(raw, "log/cm18_dmax_rad_s2").reshape(-1)
        expected_dmax = h5_array(raw, "runStart/cfg/rbf/attitude/dmax").reshape(-1)
        assert_close(dmax, expected_dmax, 0.0, "CM18 dmax versus pinned config")
        beta_rise = float(h5_scalar(raw, "log/cm18_beta_rise_time_s"))
        assert_close(beta_rise, float(h5_scalar(raw, "runStart/cfg/rbf/attitude/beta_rise_time")),
                     0.0, "CM18 beta rise time versus pinned config")
        j0 = h5_array(raw, "log/cm18_fixed_inertia_J0_kgm2")
        assert_close(j0, EXPECTED_J0, 1e-12, "fixed C5 controller inertia J0")
        need(np.linalg.eigvalsh((j0 + j0.T) * 0.5).min() > 0.0,
             "fixed J0 is not positive definite")
        need(h5_text_at(raw, "runStart/cfg/controller_morphology_mode").lower() == "fixed"
             and h5_text_at(raw, "runStart/cfg/controller_inertia_derivative_mode").lower() == "fixed",
             "BS reconstruction requires the pinned fixed-morphology/fixed-Jdot controller")
        k1 = h5_array(raw, "runStart/cfg/control/bs/attitude/k1").reshape(3)
        k2 = h5_array(raw, "runStart/cfg/control/bs/attitude/k2").reshape(3)
        mass = float(h5_scalar(raw, "runStart/cfg/plant/mass"))
        z_all = np.vstack((np.zeros(4), np.cumsum(command[:-1] * dt_s, axis=0)))
        input_log = h5_array(raw, "log/cm18_event_input_18")
        z_log = h5_array(raw, "log/cm18_event_z_before_4")
        u_log = h5_array(raw, "log/cm18_event_u_current_4")
        a_log = h5_array(raw, "log/cm18_event_a_previous_requested_torque_mean_Nm")
        raw_log = h5_array(raw, "log/cm18_event_raw_acceleration_rad_s2")
        clipped_log = h5_array(raw, "log/cm18_event_clipped_acceleration_rad_s2")
        event_arrays = (("X18", input_log, 18), ("z", z_log, 4), ("u", u_log, 4),
                        ("a_previous", a_log, 3), ("raw", raw_log, 3), ("clipped", clipped_log, 3))
        for label, value, width in event_arrays:
            need(value.shape == (n, width), f"CM18 {label} has wrong shape {value.shape}")
            need(np.isfinite(value[event_flag]).all() and np.isnan(value[~event_flag]).all(),
                 f"CM18 {label} must be finite only on event rows")

        held_acc = np.zeros((n, 3)); held_beta = np.zeros(n); held_torque = np.zeros((n, 3))
        held_clip = np.zeros(n, dtype=bool)
        current_acc = np.zeros(3); current_beta = 0.0; current_torque = np.zeros(3); current_clip = False
        max_delta = {name: 0.0 for name in ("X18", "z", "u", "a_previous", "BS_alpha",
                                                   "BS_nominal_torque", "forward", "clip", "beta",
                                                   "held_acceleration", "held_torque", "nominal_minus_comp")}
        clip_by_axis = np.zeros(3, dtype=np.int64)
        phase_errors = {"PRE_0_5": [], "POST_5_20": []}
        for i in event_rows:
            past_start = i - 10
            weights = np.diff(time[past_start:i + 1])
            need(len(weights) == 10 and np.all(weights > 0.0), f"event {i+1}: invalid 10-transition history")
            previous_torque_mean = np.average(requested[past_start:i, 1:4], axis=0, weights=weights)
            acc_ref = h5_array(raw, "log/command_filter_acceleration_applied_rads2")[i]
            alpha_bs, omega = attitude_bs_alpha(state[i], filtered_attitude[i], filtered_rate[i],
                                                acc_ref, k1, k2)
            nominal_rebuilt = j0 @ alpha_bs + np.cross(omega, j0 @ omega)
            max_delta["BS_alpha"] = max(max_delta["BS_alpha"], max_abs(input_log[i, 3:6] - alpha_bs))
            max_delta["BS_nominal_torque"] = max(max_delta["BS_nominal_torque"],
                                                   max_abs(nominal_torque[i] - nominal_rebuilt))
            thrust_per_mass = requested[i, 0] / mass
            x = np.r_[omega, alpha_bs, thrust_per_mass, command[i], z_all[i], previous_torque_mean]
            max_delta["X18"] = max(max_delta["X18"], max_abs(input_log[i] - x))
            max_delta["z"] = max(max_delta["z"], max_abs(z_log[i] - z_all[i]))
            max_delta["u"] = max(max_delta["u"], max_abs(u_log[i] - command[i]))
            max_delta["a_previous"] = max(max_delta["a_previous"], max_abs(a_log[i] - previous_torque_mean))
            raw_forward = forward(x[None, :], parameters)[0]
            max_delta["forward"] = max(max_delta["forward"], max_abs(raw_log[i] - raw_forward))
            clipped = np.clip(raw_forward, -dmax, dmax)
            max_delta["clip"] = max(max_delta["clip"], max_abs(clipped_log[i] - clipped))
            beta = min((i + 1) * dt_s / beta_rise, 1.0)
            current_acc = beta * clipped
            current_torque = j0 @ current_acc
            current_beta = beta
            current_clip = bool(np.any(raw_forward != clipped))
            clip_by_axis += (raw_forward != clipped)
            phase = "PRE_0_5" if transition_time[i] < 5.0 else "POST_5_20"
            phase_errors[phase].append(raw_forward - clipped)
            max_delta["beta"] = max(max_delta["beta"], abs(float(h5_array(raw, "log/cm18_beta_held").reshape(-1)[i]) - beta))
            max_delta["nominal_minus_comp"] = max(max_delta["nominal_minus_comp"],
                max_abs(requested[i, 1:4] - (nominal_torque[i] - current_torque)))
            held_acc[i], held_beta[i], held_torque[i], held_clip[i] = current_acc, current_beta, current_torque, current_clip

        logged_held_acc = h5_array(raw, "log/cm18_applied_acceleration_held_rad_s2")
        logged_held_beta = h5_array(raw, "log/cm18_beta_held").reshape(-1)
        logged_held_torque = h5_array(raw, "log/cm18_compensation_torque_held_Nm")
        logged_held_clip = h5_array(raw, "log/cm18_clip_flag_held", dtype=bool).reshape(-1)
        max_delta["held_acceleration"] = max_abs(logged_held_acc - held_acc)
        max_delta["held_torque"] = max_abs(logged_held_torque - held_torque)
        max_delta["beta"] = max(max_delta["beta"], max_abs(logged_held_beta - held_beta))
        need(max_delta["nominal_minus_comp"] <= TOL
             and max_delta["BS_nominal_torque"] <= 1e-9
             and all(value <= TOL for key, value in max_delta.items() if key != "BS_nominal_torque"),
             f"CM18 forward/BS/hold closure exceeds tolerance: {max_delta}")
        assert_close(logged_held_acc, held_acc, TOL, "100 Hz held acceleration")
        assert_close(logged_held_torque, held_torque, TOL, "J0 held torque")
        assert_close(applied_torque, held_torque, TOL, "logged applied torque versus held J0 output")
        need(max_abs(logged_held_beta - held_beta) <= 1e-12
             and np.array_equal(logged_held_clip, held_clip),
             "100 Hz held beta/clip flag does not match event reconstruction")

        position_sat = h5_array(raw, "log/motor_saturated", dtype=bool)
        generalized_clip = h5_array(raw, "log/generalized_clipped", dtype=bool)
        tilt_limit = h5_array(raw, "log/tilt_limited", dtype=bool).reshape(-1)
        need(position_sat.shape == generalized_clip.shape == (n, 4) and tilt_limit.shape == (n,),
             "actuator/safety flag dimensions mismatch")
        metrics = scoring(state, ref_position, filtered_attitude, filtered_rate, time[:-1])
        position_error = np.linalg.norm(ref_position[:-1] - state[:-1, :3], axis=1)
        tilt = np.arccos(np.clip(np.cos(state[:-1, 6]) * np.cos(state[:-1, 7]), -1.0, 1.0))
        body_rate = np.linalg.norm(state[:-1, 9:12], axis=1)
        position_longest, position_tail = run_durations(position_error > 1.0, dt_s)
        tilt_longest, tilt_tail = run_durations(tilt > np.pi / 3.0, dt_s)
        rate_longest, rate_tail = run_durations(body_rate > 20.0, dt_s)
        logged_tail = [float(h5_scalar(raw, "log/safety_position_error_persistence_s")),
                       float(h5_scalar(raw, "log/safety_tilt_persistence_s")),
                       float(h5_scalar(raw, "log/safety_body_rate_persistence_s"))]
        computed_tail = [position_tail, tilt_tail, rate_tail]
        need(position_longest < 0.2 and tilt_longest < 0.1 and rate_longest < 0.05
             and max_abs(np.asarray(logged_tail) - np.asarray(computed_tail)) <= 1e-12,
             "recomputed safety persistence disagrees or reaches engine stop threshold")
        finite_state = bool(np.isfinite(state).all())
        need(finite_state, "non-finite state in raw trajectory")
        return {
            "status": "PASS", "scene_id": scene_id, "raw_path": str(raw_path.relative_to(root)),
            "raw_sha256": raw_sha, "run_start_sha256": start_sha,
            "release_path": str(release_path.relative_to(root)),
            "release_sha256": sha256(release_path).lower(), "deployment_parameters_sha256": PINS["deployment"],
            "checkpoint_sha256": PINS["checkpoint"], "selected_step": 40000,
            "normalizer_float64_sha256": PINS["normalizer"], "engine_sha256": PINS["engine"],
            "c5_active_source_file_count_sha_verified": inventory_count,
            "counts": {"transitions": n, "state_samples": n + 1, "cm18_events": int(event_flag.sum()),
                       "event_first_last_matlab_index": [11, 19991], "event_stride_transitions": 10,
                       "event_pre_0_5": int(np.sum(transition_time[event_rows] < 5.0)),
                       "event_post_5_20": int(np.sum(transition_time[event_rows] >= 5.0)),
                       "clip_by_axis": clip_by_axis.tolist(),
                       "motor_saturation_by_motor": position_sat.sum(axis=0).astype(int).tolist(),
                       "generalized_clip_by_axis": generalized_clip.sum(axis=0).astype(int).tolist(),
                       "tilt_limit_transitions": int(tilt_limit.sum())},
            "rbf_off": {"three_options_false": True, "three_runtime_log_flags_false": True,
                        "fusion_and_head_false": True, "update_flags_zero": True,
                        "raw_unclipped_held_outputs_zero": True, "attitude_rbf_compensation_torque_zero": True},
            "position_controller": {"scope": "C5 configuration, source, mask, and initial weights matched; trajectory-dependent outputs are not expected to match.",
                                     "mask": [1, 1, 0], "cfg_exact_to_C5": True,
                                     "opts_exact_except_A1R_model_marker_and_three_RBF_off_flags": True,
                                     "scene_exact_to_C5_baseline": True,
                                     "static_position_log_fields_exact_to_C5": list(POSITION_STATIC_LOG_FIELDS)},
            "max_abs_reconstruction_delta": max_delta,
            "phase_clip_delta_rad_s2": {name: (np.max(np.abs(np.asarray(values)), axis=0).tolist()
                                                  if values else [0.0, 0.0, 0.0])
                                        for name, values in phase_errors.items()},
            "scoring": {"method": "frozen A1 scorer; 20,000 left-aligned transition samples, terminal t=20 s excluded",
                        "position_Q_and_filtered_reference_SO3": metrics},
            "safety": {"position_error_peak_m": float(position_error.max()),
                       "position_error_longest_run_s": position_longest,
                       "tilt_peak_deg": float(np.rad2deg(tilt.max())),
                       "tilt_longest_run_s": tilt_longest,
                       "body_rate_peak_rad_s": float(body_rate.max()),
                       "body_rate_longest_run_s": rate_longest,
                       "logged_trailing_persistence_s": logged_tail,
                       "recomputed_trailing_persistence_s": computed_tail},
            "scope_note": "This is one fixed closed-loop scene audit. It does not establish full SCREEN12 performance or causal model benefit.",
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--scene-id", choices=SCENE_IDS, default=FIRST_SCENE)
    args = parser.parse_args()
    root = args.repo_root.resolve()
    scene_id = args.scene_id
    attempt_name = "attempt_02" if scene_id == FIRST_SCENE else "attempt_01"
    run_dir = repo_path(root, f"{RUNNER_REL}/runs/{scene_id}/{attempt_name}")
    raw_path = run_dir / "raw_run.mat"
    if not raw_path.is_file():
        raise FileNotFoundError(f"A1R raw is absent; no audit was run and no PASS report was written: {raw_path}")
    out = repo_path(root, f"{REPORT_REL}/A1R_SCREEN12_LOG_AUDIT_{scene_id}_v1.json")
    if out.exists():
        raise FileExistsError(f"refusing to overwrite existing audit evidence: {out}")
    index = SCENE_IDS.index(scene_id)
    try:
        row, prep_row, prep = load_scene_row(root, scene_id)
        release, release_path, identity_sha = verify_release(root, scene_id, index, prep, prep_row)
        result = event_audit(root, scene_id, row, prep_row, prep, release, release_path, identity_sha)
    except Exception as exc:
        result = {"status": "FAIL", "scene_id": scene_id, "raw_path": str(raw_path.relative_to(root)),
                  "raw_sha256": sha256(raw_path).lower(), "error": f"{type(exc).__name__}: {exc}",
                  "audit_source_sha256": sha256(Path(__file__).resolve()).lower(),
                  "scope": "read-only independent A1R SCREEN12 raw audit; no Plant/training/TEST"}
    result["schema"] = "A1R_SCREEN12_INDEPENDENT_LOG_AUDIT_V1"
    result["created_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    result["audit_source_path"] = str(Path(__file__).resolve().relative_to(root))
    result["audit_source_sha256"] = sha256(Path(__file__).resolve()).lower()
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": result["status"], "scene_id": scene_id,
                      "raw_sha256": result["raw_sha256"], "audit_path": str(out.relative_to(root))},
                     sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
