"""Single-scene DEV audit for the frozen C6 first run; reads only the fixed C6/C5/B pair."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path

for _name in ("OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "OMP_NUM_THREADS"):
    os.environ[_name] = "1"

import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
TASK = ROOT / "experiments/c5_eight_loss_recovery_20261024/c6_startup_ramp"
REPORT = ROOT / "reports/paper_continuation_20261023/c5_eight_loss_recovery/c6_startup_ramp"
SCENE = "DL1018_VAL_T1_C00_W07"
C6_CANDIDATE = "C6_STARTUP_PREDICTION_RAMP"
C5_CANDIDATE = "C5_AXIS_MIXED_COORDINATE_M110"
EXPECTED_C6_LOCK_SHA = "919de01ed9a111f24f4028b5436bdfa46d817f32c475bbf18e70b87d2eb37c06"
EXPECTED_C6_CONTRACT_SHA = "6b75d40ff257d38a8aa6c9d7e1384dacbaee5b89d9a218a19bbe3037b7d7a463"
EXPECTED_C6_BINDING_SHA = "dd834d6c354cc27f0493ce715a0dfe677d9e0ba574ddf899ececf0c2661eb964"
EXPECTED_C6_RUNNER_SHA = "aeec013bd2bf2d869f71b9b2318436d20ec53e85375adcea056ef10591605a99"
C6_HELPER_SHA = "53e5c2fa8098769b84952c93469625eae9abedccb199a1c57d3746b8005bd067"
C6_KERNEL_SHA = "0ad47c691f5411e36d75ab5f1f78ecb0a945564371ecfb2fc18066b47ae2bcac"
EXPECTED_SNAPSHOT_SHA = "f6ad61507b1d9027abb6bb2e4f5fc30d8558c0820fe663e0a2deb3a62b84255b"
C5_EVENT_SOURCE = ROOT / "reports/paper_continuation_20261023/c5_dev72_parent_review/audit_c5_dev72_raw_parent_v4.py"
C5_EVENT_SOURCE_SHA = "d82e089c7d41f39c620daea63d95315632e6fb2f80addf4dc12e6a4603b8e57e"
SCORER_PATH = ROOT / "reports/delayed_prediction_c3_dev72_parent_20261023/parent_raw_metrics.py"
SCORER_SHA = "c64482d0adbc4358417648ec08351bd78f1d3dbdb38950435fa71b9cb0f531b1"
DECODER_PATH = ROOT / "reports/paper14_v2/phase1/audit_w15_position_replay.py"
DECODER_SHA = "372d92cb17da99884e742d3fa0c877200c3bb2bc6fac7f10e7a1a046b97a76af"
PHYSICAL_FIELDS = [
    "initial_state", "time", "environment_wind_I", "arms/command", "arms/rho_true",
    "arms/rhoDot_true", "arms/rho_hat", "arms/rhoDot_hat", "reference/acceleration",
    "reference/position", "reference/velocity", "reference/yaw",
    "reference/yaw_acceleration", "reference/yaw_rate",
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def sha(path: Path | str) -> str:
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load_json(path: Path | str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, f"cannot import pinned source: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def matlab_text(value) -> str:
    if isinstance(value, tuple) and len(value) == 3 and value[0] == "__matlab_char__":
        return str(value[2])
    return str(value)


def finite_diff(a, b) -> float:
    left, right = np.asarray(a), np.asarray(b)
    require(left.shape == right.shape, f"shape mismatch: {left.shape} != {right.shape}")
    require(np.isfinite(left).all() and np.isfinite(right).all(), "non-finite event check input")
    return float(np.max(np.abs(left - right), initial=0.0))


def event_audit(raw_path: Path, cfg: dict, expected_w0_sha256: str, kernel) -> dict:
    """C5 v4 event audit with the sole C6 law change: rho * beta * prediction_gradient."""
    with h5py.File(raw_path, "r") as file:
        g = file["log"]

        def read(key):
            value = np.asarray(g[key])
            return value.T if value.ndim == 2 else value

        ids = np.flatnonzero(read("stage1_position_event_inference_valid").ravel())
        require(np.array_equal(ids, np.arange(320, 19991, 10)) and len(ids) == 1968,
                "C6 event index sequence/count mismatch")
        for key in ("stage1_position_delayed_prediction_enabled", "stage1_position_replacement_enabled",
                    "stage1_position_pcf_coordination_enabled", "stage1_position_update_enabled"):
            require(read(key).item() == 1, f"disabled C6 event path: {key}")
        require(np.array_equal(read("stage1_position_coordinate_mask").ravel(), [1, 1, 0]),
                "C6 coordinate mask mismatch")
        require(read("stage1_position_search_gamma").item() == 12, "C6 gamma mismatch")
        require(read("stage1_position_search_kappa").item() == 1, "C6 kappa mismatch")
        initial = read("stage1_position_search_initial_weight")
        require(np.array_equal(initial, read("stage1_position_weight_initial")), "initial W logs disagree")
        require(hashlib.sha256(np.asarray(initial, dtype="<f8").tobytes(order="F")).hexdigest()
                == expected_w0_sha256.lower(), "initial W0 does not match C6 contract")

        phi = read("stage1_position_event_phi_33")[ids]
        wb = np.asarray(g["stage1_position_event_weight_before_33x3"]).transpose(0, 2, 1)
        wa = np.asarray(g["stage1_position_event_weight_after_33x3"]).transpose(0, 2, 1)
        require(wb.shape == wa.shape == (len(ids), 33, 3) and np.array_equal(wb[0], initial),
                "C6 event weight-array shape or initial value mismatch")
        state = read("state")
        req = read("stage1_position_pcf_a_req_mps2")
        af = read("stage1_position_pcf_a_f_mps2")
        rf = read("stage1_position_pcf_r_f_mps2")
        eta = read("stage1_position_pcf_eta_before_mps")
        roll, pitch, yaw = read("filtered_attitude_reference").T
        thrust_axis = np.column_stack((
            np.cos(yaw)*np.sin(pitch)*np.cos(roll) + np.sin(yaw)*np.sin(roll),
            np.sin(yaw)*np.sin(pitch)*np.cos(roll) - np.cos(yaw)*np.sin(roll),
            np.cos(pitch)*np.cos(roll)))
        mass = float(np.asarray(cfg["plant"]["mass"]).item())
        gravity = float(np.asarray(cfg["plant"]["g"]).item())
        nameplate_af = read("requested_generalized")[:, 0, None] / mass * thrust_axis - np.array([0, 0, gravity])
        target = read("stage1_position_delayed_prediction_target_mps2")[ids]
        previous = read("stage1_position_delayed_prediction_prev_index_zero_based").ravel()[ids]
        require(np.isnan(previous[0]) and np.isnan(target[0]).all(), "first ready event must have no prior target")
        require(np.array_equal(previous[1:], ids[:-1]), "delayed prediction event pairing is not j=n-10")
        reference = af.copy()
        reference[:, 2] = req[:, 2]
        y = np.array([((state[k, 3:6] - state[j, 3:6]) - .001 * reference[j:k].sum(axis=0)) / .01
                      for j, k in zip(ids[:-1], ids[1:])])
        beta = np.minimum((ids + 1) * .001 / 1.8, 1.0)
        raw = np.einsum("nfi,nf->ni", wb, phi)
        gradient = np.zeros_like(wb)
        gradient[1:] = phi[:-1, :, None] * (np.einsum("nfi,nf->ni", wb[1:], phi[:-1]) - y)[:, None, :]
        surface = (read("reference/velocity")[:-1] - state[:-1, 3:6]
                   + read("reference/position")[:-1] - state[:-1, :3])[ids]
        coordinated = surface - eta[ids] * np.array([1, 1, 0])
        effective = np.clip(coordinated, -np.array([7, 8, 10]), np.array([7, 8, 10]))
        event_times = read("transition_time").ravel()[ids]

        kernel_beta = np.empty(len(ids))
        kernel_raw = np.empty((len(ids), 3))
        kernel_applied = np.empty((len(ids), 3))
        kernel_gradient = np.zeros_like(wb)
        kernel_next = np.empty_like(wb)
        for i, n in enumerate(ids):
            if i == 0:
                step = kernel.delayed_prediction_step(wb[i], phi[i], effective[i], int(n), float(event_times[i]))
            else:
                step = kernel.delayed_prediction_step(
                    wb[i], phi[i], effective[i], int(n), float(event_times[i]),
                    phi_prev=phi[i - 1], y_prev=target[i], previous_index=int(ids[i - 1]),
                    previous_time_s=float(event_times[i - 1]))
            kernel_beta[i], kernel_raw[i], kernel_applied[i] = step["beta"], step["raw"], step["applied"]
            kernel_gradient[i], kernel_next[i] = step["prediction_gradient"], step["W_next"]

        unscaled_reference = .01 * np.linalg.norm(gradient, axis=(1, 2))
        actual_beta_scaled_norm = beta * unscaled_reference
        held = np.zeros((20000, 3))
        applied = beta[:, None] * np.clip(raw, -3, 3)
        for index, k in enumerate(ids):
            held[k:min(k + 10, 20000)] = applied[index]
        reference_integral = np.vstack((np.zeros((1, 3)), np.cumsum(.001 * reference, axis=0)))[:-1]
        af_integral = np.vstack((np.zeros((1, 3)), np.cumsum(.001 * af, axis=0)))[:-1]

        checks = {
            "phi_unit_norm": finite_diff(np.linalg.norm(phi, axis=1), np.ones(len(ids))),
            "past_mixed_reference_target": finite_diff(target[1:], y),
            "surface_original_from_actual_state": finite_diff(read("stage1_position_pcf_event_s_original_mps")[ids], surface),
            "surface_M110": finite_diff(read("stage1_position_pcf_event_s_coord_mps")[ids], coordinated),
            "surface_clip_M110": finite_diff(read("stage1_position_pcf_event_s_coord_eff_mps")[ids], effective),
            "eta_event_before": finite_diff(read("stage1_position_pcf_event_eta_before_mps")[ids], eta[ids]),
            "output_before_update": finite_diff(read("stage1_position_event_raw_acceleration_mps2")[ids], raw),
            "applied_beta_clip": finite_diff(read("stage1_position_event_applied_acceleration_mps2")[ids], applied),
            "beta_clock": finite_diff(read("stage1_position_event_beta").ravel()[ids], beta),
            "event_period": finite_diff(read("stage1_position_event_dt_s").ravel()[ids], np.full(len(ids), .01)),
            "C6_kernel_beta": finite_diff(kernel_beta, beta),
            "C6_kernel_output_before_update": finite_diff(kernel_raw, raw),
            "C6_kernel_applied_output": finite_diff(kernel_applied, applied),
            "C6_kernel_prediction_gradient": finite_diff(kernel_gradient, gradient),
            "C6_beta_scaled_joint_update": finite_diff(kernel_next, wa),
            "weight_continuity": finite_diff(wb[1:], wa[:-1]),
            "stage1DelayedTermNorm_unscaled_reference": finite_diff(
                read("stage1_position_delayed_prediction_term_norm").ravel()[ids], unscaled_reference),
            "C6_actual_prediction_norm_equals_beta_times_reference": finite_diff(
                actual_beta_scaled_norm, beta * (.01 * np.linalg.norm(gradient, axis=(1, 2)))),
            "separate_actual_af_integral": finite_diff(
                read("stage1_position_delayed_prediction_af_integral_before_step_mps"), af_integral),
            "M110_reference_integral": finite_diff(
                read("stage1_position_delayed_prediction_reference_integral_before_step_mps"), reference_integral),
            "event_reference_integral": finite_diff(
                read("stage1_position_delayed_prediction_event_reference_integral_mps")[ids], reference_integral[ids]),
            "event_velocity": finite_diff(read("stage1_position_delayed_prediction_event_velocity_mps")[ids], state[ids, 3:6]),
            "held_compensation": finite_diff(read("position_compensation_applied_acceleration_mps2"), held),
            "request_contains_applied_compensation": finite_diff(
                req, read("position_nominal_acceleration_mps2") - held),
            "rf_definition": finite_diff(rf, req - af),
            "nameplate_af_from_actual_thrust_filtered_attitude": finite_diff(af, nameplate_af),
            "direct_mixed_reference": finite_diff(read("stage1_position_pcf_prediction_reference_mps2"), reference),
            "eta_initial_zero": finite_diff(eta[0], np.zeros(3)),
            "eta_continuity": finite_diff(eta[1:], read("stage1_position_pcf_eta_after_mps")[:-1]),
            "eta_exact_held_step": finite_diff(read("stage1_position_pcf_eta_after_mps"),
                np.exp(-.004) * eta + (-np.expm1(-.004)/4) * rf),
        }
        require(max(checks.values()) < 1e-10, f"C6 event check exceeded tolerance: {checks}")
        return {
            "event_count": int(len(ids)), "checks_max_abs": checks,
            "max_unscaled_stage1DelayedTermNorm": float(np.max(unscaled_reference)),
            "max_beta_scaled_actual_prediction_step_norm": float(np.max(actual_beta_scaled_norm)),
            "stage1DelayedTermNorm_semantics": (
                "Unscaled reference norm rho*||prediction_gradient||; actual C6 step norm is beta times this field."
            ),
            "event_audit_source_sha256": C5_EVENT_SOURCE_SHA,
            "C6_MATLAB_helper_sha256": C6_HELPER_SHA,
            "C6_Python_kernel_sha256": C6_KERNEL_SHA,
        }


def exact_tree(left, right) -> bool:
    if isinstance(left, np.ndarray) or isinstance(right, np.ndarray):
        return np.array_equal(np.asarray(left), np.asarray(right))
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(exact_tree(left[key], right[key]) for key in left)
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        return len(left) == len(right) and all(exact_tree(a, b) for a, b in zip(left, right))
    if isinstance(left, np.generic):
        left = left.item()
    if isinstance(right, np.generic):
        right = right.item()
    return left == right


def raw_shape_finite_audit(raw_path: Path) -> dict:
    """Use the logger's transition (20,000) versus state/input (20,001) indexing."""
    with h5py.File(raw_path, "r") as file:
        g = file["log"]

        def read(key):
            value = np.asarray(g[key])
            return value.T if value.ndim == 2 else value

        samples = {"time": (20001,), "state": (20001, 12), "environment_wind_I": (20001, 3),
                   "reference/position": (20001, 3), "reference/velocity": (20001, 3),
                   "reference/acceleration": (20001, 3), "reference/yaw": (20001, 1),
                   "reference/yaw_rate": (20001, 1), "reference/yaw_acceleration": (20001, 1),
                   "arms/command": (20001, 4), "arms/rho_true": (20001, 4),
                   "arms/rhoDot_true": (20001, 4), "arms/rho_hat": (20001, 4),
                   "arms/rhoDot_hat": (20001, 4)}
        transitions = {"requested_generalized": (20000, 4), "controller_clipped_generalized": (20000, 4),
                       "allocated_generalized": (20000, 4), "realized_generalized": (20000, 4),
                       "motor_saturated": (20000, 4), "generalized_clipped": (20000, 4),
                       "tilt_limited": (20000, 1), "motor_command": (20000, 4),
                       "motor_squared_requested": (20000, 4), "motor_setpoint": (20000, 4),
                       "controller_call_time_s": (20000,)}
        for key, shape in {**samples, **transitions}.items():
            value = read(key)
            if len(shape) == 1 and value.size == shape[0]:
                value = value.reshape(-1)
            require(value.shape == shape, f"{raw_path.name}:{key} shape {value.shape}, expected {shape}")
            require(np.isfinite(value).all(), f"{raw_path.name}:{key} contains non-finite values")
        initial = read("initial_state").reshape(-1)
        transition_time = read("transition_time").reshape(-1)
        require(initial.shape == (12,) and np.isfinite(initial).all(), "initial state must be finite 12-vector")
        require(np.max(np.abs(initial - read("state")[0])) < 1e-12,
                "initial_state does not match first logged state sample")
        require(transition_time.shape == (20000,) and np.isfinite(transition_time).all(),
                "transition_time must be 20,000 finite transition stamps")
        require(np.max(np.abs(read("time").reshape(-1) - np.arange(20001) * .001)) < 4e-15,
                "state-sample time grid mismatch")
        require(np.max(np.abs(transition_time - np.arange(20000) * .001)) < 4e-15,
                "transition time grid mismatch")
        flag_counts = {key: int(np.count_nonzero(read(key)))
                       for key in ("motor_saturated", "generalized_clipped", "tilt_limited")}
        return {"state_samples": 20001, "transitions": 20000,
                "finite_sample_fields": sorted(samples), "finite_transition_fields": sorted(transitions),
                "arms_command_shape": [20001, 4], "transition_limit_flag_counts": flag_counts}


def main() -> None:
    c6_dir = TASK / "runs_c6_startup_ramp_v1" / SCENE / C6_CANDIDATE / "attempt_01"
    c5_dir = ROOT / "experiments/position_axis_coordinate_c5_20261023/runs_c5_v1" / SCENE / "C5_AXIS_MASK_M110/attempt_01"
    snapshot_path = TASK / "C6_STARTUP_RAMP_PREPARED_CFG_OPTS_v1.mat"
    require(sha(snapshot_path) == EXPECTED_SNAPSHOT_SHA, "C6 prepared snapshot hash changed")
    c6_status_path = c6_dir / "run_status.json"
    c5_status_path = c5_dir / "run_status.json"
    c6_status = load_json(c6_status_path)
    c5_status = load_json(c5_status_path)
    lock_path = TASK / "C6_STARTUP_RAMP_INPUT_LOCK_v1.json"
    contract_path = TASK / "C6_STARTUP_RAMP_RUN_CONTRACT_v1.json"
    release_path = TASK / "C6_FIRST_PARENT_RELEASE_v1.json"
    binding_path = TASK / "C6_SOURCE_BINDING_v1.json"
    snapshot_path = TASK / "C6_STARTUP_RAMP_PREPARED_CFG_OPTS_v1.mat"
    receipt_path = REPORT / "C6_FIRST_SCENE_EXECUTION_RECEIPT_v1.json"
    os_exit_path = REPORT / "C6_FIRST_SCENE_MATLAB_OS_EXIT_v1.json"
    history_path = REPORT / "C6_FIRST_SCENE_OUTER_INVOCATION_HISTORY_v1.json"
    raw_review_path = REPORT / "C6_FIRST_SCENE_RAW_REVIEW_v1.json"
    metadata_review_path = REPORT / "C6_FIRST_SCENE_METADATA_OS_REVIEW_v1.json"
    require(not raw_review_path.exists() and not metadata_review_path.exists(), "refusing to overwrite prior review")

    for path, expected in ((lock_path, EXPECTED_C6_LOCK_SHA), (contract_path, EXPECTED_C6_CONTRACT_SHA),
                           (binding_path, EXPECTED_C6_BINDING_SHA), (C5_EVENT_SOURCE, C5_EVENT_SOURCE_SHA),
                           (SCORER_PATH, SCORER_SHA), (DECODER_PATH, DECODER_SHA),
                           (TASK / "delayed_prediction_step_candidate.m", C6_HELPER_SHA),
                           (TASK / "delayed_prediction_kernel.py", C6_KERNEL_SHA)):
        require(sha(path) == expected, f"frozen source/input hash mismatch: {path}")
    lock, contract, release, binding = map(load_json, (lock_path, contract_path, release_path, binding_path))
    require(c6_status["TEST_accessed"] is False and c6_status["training_steps"] == 0
            and c6_status["optimizer_steps"] == 0 and c6_status["parameter_or_seed_search"] is False
            and c6_status["plant_calls"] == 1 and c6_status["plant_start_confirmed"] is True
            and c6_status["candidate"] == C6_CANDIDATE and c6_status["coordinate_mask"] == [1, 1, 0],
            "C6 status has unexpected TEST/training/search/Plant/candidate metadata")
    first_rows = [row for row in lock["scenes"] if row["scene_id"] == SCENE]
    require(len(first_rows) == 1, "C6 lock must contain exactly one first-scene row")
    first_row = first_rows[0]
    physical_source = first_row["B_source"]
    require(sha(release_path) == c6_status["release_sha256"], "C6 release hash differs from run status")
    require(release["schema"] == "C6_FIRST_PARENT_RELEASE_V1" and release["state"] == "APPROVED_C6_FIRST_SCENE_V1"
            and release["scene_id"] == SCENE and release["c6_runner_sha256"].lower() == EXPECTED_C6_RUNNER_SHA,
            "C6 first-scene release identity mismatch")
    require(sha(TASK / "run_c6_startup_ramp_first_v1.m") == EXPECTED_C6_RUNNER_SHA,
            "frozen C6 runner changed")
    require(binding["input_lock_sha256"].lower() == sha(lock_path)
            and binding["input_lock_path"].lower() == str(lock_path).lower()
            and binding["runner_path"].lower() == str(TASK / "run_c6_startup_ramp_first_v1.m").lower()
            and binding["runner_sha256"].lower() == EXPECTED_C6_RUNNER_SHA
            and binding["taskbook_sha256"].lower() == contract["taskbook_sha256"]
            and release["c6_input_lock_sha256"].lower() == sha(lock_path)
            and release["c6_run_contract_sha256"].lower() == sha(contract_path)
            and release["c6_source_binding_sha256"].lower() == sha(binding_path),
            "C6 source binding no longer matches release inputs")
    require(release["physical_B_source_sha256"].lower() == physical_source["sha256"].lower()
            and release["c6_runner_path"].lower() == str(TASK / "run_c6_startup_ramp_first_v1.m").lower()
            and release["c6_runner_sha256"].lower() == EXPECTED_C6_RUNNER_SHA
            and release["c6_snapshot_sha256"].lower() == EXPECTED_SNAPSHOT_SHA,
            "C6 release does not bind the prepared snapshot, runner, and physical source")
    require(contract["algorithm_change"]["prediction_gradient_scaled_by_beta"] is True
            and contract["fixed_parameters"]["rho"] == 0.01
            and contract["first_scene_id"] == SCENE and lock["first_scene_id"] == SCENE,
            "C6 contract is not the registered beta-ramped first scene")
    require(first_row["b_scene_to_scored_log"]["path"].lower() == physical_source["path"].lower()
            and first_row["b_scene_to_scored_log"]["sha256"].lower() == physical_source["sha256"].lower()
            and first_row["b_scene_to_scored_log"]["matching_fields"] == PHYSICAL_FIELDS,
            "C6 physical identity fields changed")
    require(sha(physical_source["path"]) == physical_source["sha256"].lower(), "locked physical B source changed")

    c5_lock_path = ROOT / "experiments/position_axis_coordinate_c5_20261023/C5_AXIS_COORDINATE_INPUT_LOCK_v1.json"
    b_lock_path = ROOT / "experiments/b_traceable_c3core_dev72_20261023/B_TRACEABLE_DEV72_INPUT_LOCK_v3.json"
    c5_lock, b_lock = load_json(c5_lock_path), load_json(b_lock_path)
    require(c5_status["status"] == "RUN_COMPLETE_RAW_PENDING_AUDIT"
            and c5_status["candidate"] == C5_CANDIDATE and c5_status["coordinate_mask"] == [1, 1, 0]
            and c5_status["physical_B_source_sha256"].lower() == physical_source["sha256"].lower()
            and c5_status["physical_B_source_path"].lower() == physical_source["path"].lower()
            and c5_status["scoring_B72_raw_path"].lower() == release["b72_first_scene_raw_path"].lower()
            and c5_status["scoring_B72_raw_sha256"].lower() == release["b72_first_scene_raw_sha256"].lower()
            and c5_status["scoring_B72_status_path"].lower() == release["b72_first_scene_status_path"].lower()
            and c5_status["scoring_B72_status_sha256"].lower() == release["b72_first_scene_status_sha256"].lower()
            and c5_status["input_lock_sha256"].lower() == sha(c5_lock_path)
            and c5_status["TEST_accessed"] is False and c5_status["training_steps"] == 0
            and c5_status["optimizer_steps"] == 0 and c5_status["parameter_or_seed_search"] is False,
            "C5 pair status/input lock/physical-B72 binding mismatch")
    c5_row = next(row for row in c5_lock["scenes"] if row["scene_id"] == SCENE)
    b_row = next(row for row in b_lock["scenes"] if row["scene_id"] == SCENE)
    require(c5_row["B_source"]["path"].lower() == physical_source["path"].lower()
            and c5_row["B_source"]["sha256"].lower() == physical_source["sha256"].lower(),
            "C5 physical source differs from C6 source")
    require(b_row["B_source"]["path"].lower() == physical_source["path"].lower()
            and b_row["B_source"]["sha256"].lower() == physical_source["sha256"].lower()
            and b_row["scored_log"]["path"].lower() == release["b72_first_scene_raw_path"].lower()
            and b_row["scored_log"]["sha256"].lower() == release["b72_first_scene_raw_sha256"].lower()
            and b_row["scored_log"]["matching_fields"] == PHYSICAL_FIELDS,
            "B72 input lock does not bind the same 14-field scene")
    require(c5_row["b_scene_to_scored_log"]["path"].lower() == physical_source["path"].lower()
            and c5_row["b_scene_to_scored_log"]["sha256"].lower() == physical_source["sha256"].lower()
            and c5_row["b_scene_to_scored_log"]["matching_fields"] == PHYSICAL_FIELDS,
            "C5 input lock physical-field list changed")

    receipt, os_exit, history = map(load_json, (receipt_path, os_exit_path, history_path))
    c6_raw_path = Path(c6_status["raw_path"])
    c5_raw_path = Path(c5_status["raw_path"])
    b_raw_path = Path(release["b72_first_scene_raw_path"])
    b_status_path = Path(release["b72_first_scene_status_path"])
    b_status = load_json(b_status_path)
    c6_raw_sha, c5_raw_sha, b_raw_sha = c6_status["raw_sha256"].lower(), c5_status["raw_sha256"].lower(), release["b72_first_scene_raw_sha256"].lower()
    require(all("TEST" not in str(path).upper() for path in (c6_raw_path, c5_raw_path, b_raw_path, physical_source["path"])),
            "fixed DEV audit path unexpectedly references TEST")
    require(c6_raw_path == c6_dir / "raw_run.mat" and c5_raw_path == c5_dir / "raw_run.mat"
            and sha(c6_raw_path) == c6_raw_sha and sha(c5_raw_path) == c5_raw_sha and sha(b_raw_path) == b_raw_sha,
            "C6/C5/B raw path or digest mismatch")
    require(c6_status["schema"] == "C6_STARTUP_RAMP_RUN_STATUS_V1"
            and c6_status["status"] == "RUN_COMPLETE_RAW_PENDING_AUDIT" and c6_status["scene_id"] == SCENE
            and c6_status["log_status"] == "STABLE" and not c6_status["safety_stop_reason"]
            and c6_status["plant_calls"] == 1 and c6_status["last_transition"] == 20000
            and c6_status["transitions"] == 20000 and c6_status["state_samples"] == 20001
            and c6_status["actual_prediction_gradient_enabled"] is True,
            "C6 run status is not the complete stable single-call scene")
    require(c5_status["scene_id"] == SCENE and c5_status["log_status"] == "STABLE"
            and not c5_status["safety_stop_reason"] and c5_status["plant_calls"] == 1
            and c5_status["last_transition"] == 20000 and c5_status["state_samples"] == 20001,
            "C5 pair is not complete, stable, and safe")
    require(b_status["scene_id"] == SCENE and b_status["status"] == "RUN_COMPLETE_RAW_PENDING_AUDIT"
            and b_status["log_status"] == "STABLE" and not b_status["safety_stop_reason"]
            and b_status["plant_calls"] == 1 and b_status["last_transition"] == 20000
            and b_status["state_samples"] == 20001 and b_status["input_lock_sha256"].lower() == sha(b_lock_path),
            "B72 pair is not complete, stable, and bound to its lock")
    require(b_status["raw_path"].lower() == str(b_raw_path).lower()
            and b_status["raw_sha256"].lower() == b_raw_sha
            and release["b72_input_lock_sha256"].lower() == sha(b_lock_path)
            and sha(b_status_path) == release["b72_first_scene_status_sha256"].lower()
            and b_status_path == Path(c5_status["scoring_B72_status_path"])
            and b_status["TEST_accessed"] is False and b_status["training_steps"] == 0
            and b_status["optimizer_steps"] == 0,
            "B72 status raw/TEST/training metadata mismatch")
    require(c6_status["input_lock_sha256"].lower() == sha(lock_path)
            and c6_status["run_start_sha256"].lower() == receipt["artifacts"]["run_start"]["sha256"].lower()
            and receipt["schema"] == "C6_FIRST_SCENE_EXECUTION_RECEIPT_V1"
            and receipt["status"] == "RUN_COMPLETE_RAW_PENDING_AUDIT"
            and receipt["artifacts"]["run_status"]["path"].lower() == str(c6_status_path).lower()
            and receipt["artifacts"]["run_status"]["sha256"].lower() == sha(c6_status_path)
            and receipt["artifacts"]["raw"]["path"].lower() == str(c6_raw_path).lower()
            and receipt["artifacts"]["run_start"]["path"].lower() == c6_status["run_start_path"].lower()
            and receipt["artifacts"]["first_plant_step_marker"]["path"].lower()
                == c6_status["first_plant_step_marker_path"].lower()
            and receipt["artifacts"]["first_plant_step_marker"]["sha256"].lower()
                == c6_status["first_plant_step_marker_sha256"].lower()
            and sha(c6_status["run_start_path"]) == c6_status["run_start_sha256"].lower()
            and sha(c6_status["first_plant_step_marker_path"]) == c6_status["first_plant_step_marker_sha256"].lower(),
            "C6 raw metadata is not bound to its start and Plant marker")
    require(receipt["natural_process_return"] is True and receipt["matlab_os_exit_code"] == 0
            and receipt["shell_natural_exit_code"] == 0 and receipt["plant_calls"] == 1
            and receipt["artifacts"]["raw"]["sha256"].lower() == c6_raw_sha
            and os_exit["schema"] == "C6_FIRST_SCENE_OS_EXIT_V1"
            and os_exit["status"] == "RUN_COMPLETE_RAW_PENDING_AUDIT"
            and os_exit["natural_process_return"] is True and os_exit["matlab_os_exit_code"] == 0
            and os_exit["plant_calls"] == 1
            and os_exit["raw_sha256"].lower() == c6_raw_sha
            and os_exit["run_status_path"].lower() == str(c6_status_path).lower()
            and os_exit["run_status_sha256"].lower() == sha(c6_status_path)
            and os_exit["raw_path"].lower() == str(c6_raw_path).lower()
            and os_exit["runner_sha256"].lower() == EXPECTED_C6_RUNNER_SHA,
            "C6 first-scene OS/receipt does not report natural exit 0")
    require(history["actual_execution"]["MATLAB_OS_exit_code"] == 0
            and history["actual_execution"]["natural_shell_process_exit_code"] == 0
            and history["actual_execution"]["plant_calls"] == 1,
            "C6 outer invocation history does not confirm a single natural run")

    b_manifest_path = Path(release["b72_raw_manifest_path"])
    b_manifest = load_json(b_manifest_path)
    require(sha(b_manifest_path) == release["b72_raw_manifest_sha256"].lower()
            and b_manifest["schema"] == "C5_B72_SCORING_MANIFEST_V1"
            and b_manifest["state"] == "PASS_C5_B72_ALL72_PARENT_AUDIT"
            and len(b_manifest["records"]) == 72, "frozen B72 scoring manifest mismatch")
    manifest_row = [r for r in b_manifest["records"] if r["scene_id"] == SCENE]
    require(len(manifest_row) == 1 and Path(manifest_row[0]["raw_path"]) == b_raw_path
            and manifest_row[0]["raw_sha256"].lower() == b_raw_sha, "B72 first-scene manifest row mismatch")
    require(sha(release["b72_parent_review_path"]) == release["b72_parent_review_sha256"].lower(),
            "B72 parent attestation changed")

    decoder = load_module(DECODER_PATH, "c6_first_scene_mat_decoder")
    kernel_path = TASK / "delayed_prediction_kernel.py"
    kernel = load_module(kernel_path, "c6_beta_scaled_prediction_kernel")
    run_start = decoder.matlab_section(Path(c6_status["run_start_path"]), "runStart")
    run_identity = decoder.matlab_section(c6_raw_path, "runIdentity")
    require(matlab_text(run_start["schema"]) == "C6_STARTUP_RAMP_RUN_START_V1"
            and matlab_text(run_start["method"]) == C6_CANDIDATE
            and matlab_text(run_start["scene_raw_sha256"]).lower() == physical_source["sha256"].lower()
            and int(np.asarray(run_start["training_steps"]).item()) == 0
            and int(np.asarray(run_start["optimizer_steps"]).item()) == 0
            and bool(np.asarray(run_start["TEST_accessed"]).item()) is False
            and bool(np.asarray(run_start["actual_weight_update_enabled"]).item()) is True
            and bool(np.asarray(run_start["actual_prediction_gradient_enabled"]).item()) is True
            and matlab_text(run_identity["scene_b_raw_sha256"]).lower() == physical_source["sha256"].lower()
            and matlab_text(run_identity["scene_id"]) == SCENE
            and matlab_text(run_identity["candidate"]) == C6_CANDIDATE,
            "C6 start/raw identity does not bind the locked physical source and candidate")
    for section in ("cfg", "opts"):
        snapshot_value = decoder.matlab_section(snapshot_path, section)
        start_value = run_start[section]
        if section == "opts":
            start_value = dict(start_value)
            start_value.pop("r2e_first_plant_step_marker", None)
        require(exact_tree(snapshot_value, start_value), f"runStart {section} differs from prepared snapshot")
    cfg = run_start["cfg"]
    event_result = event_audit(c6_raw_path, cfg, contract["model"]["W0_sha256"], kernel)

    scorer = load_module(SCORER_PATH, "c6_first_scene_pinned_scorer")
    raw_integrity = {
        "C6": raw_shape_finite_audit(c6_raw_path),
        "C5": raw_shape_finite_audit(c5_raw_path),
        "B72": raw_shape_finite_audit(b_raw_path),
    }
    scored = {
        "C6": scorer.score(dict(scene_id=SCENE, method=C6_CANDIDATE, path=str(c6_raw_path), sha256=c6_raw_sha)),
        "C5": scorer.score(dict(scene_id=SCENE, method=C5_CANDIDATE, path=str(c5_raw_path), sha256=c5_raw_sha)),
        "B72": scorer.score(dict(scene_id=SCENE, method="B_TRACEABLE", path=str(b_raw_path), sha256=b_raw_sha)),
    }
    identities = {item["external_identity_sha256"] for item in scored.values()}
    require(len(identities) == 1, "C6/C5/B72 14-field external physical identities differ")
    q = {name: float(item["Q_0_20_m"]) for name, item in scored.items()}
    statuses = {"C6": c6_status, "C5": c5_status, "B72": b_status}
    safety = {}
    for name, score in scored.items():
        run_status = statuses[name]
        safety[name] = {
            **raw_integrity[name], "log_status": run_status["log_status"],
            "safety_stop_reason": run_status["safety_stop_reason"],
            "safe_stop": bool(run_status["safety_stop_reason"]),
            "complete": run_status["last_transition"] == 20000 and run_status["state_samples"] == 20001,
            "plant_calls": run_status["plant_calls"],
            "motor_saturated_fraction": float(score["motor_saturated_fraction"]),
            "generalized_clipped_fraction": float(score["generalized_clipped_fraction"]),
        }
    pair = {
        "external_identity_sha256": next(iter(identities)),
        "identity_fields": PHYSICAL_FIELDS,
        "same_locked_physical_B_source_sha256": physical_source["sha256"].lower(),
        "metrics": {name: {key: item[key] for key in (
            "Q_0_20_m", "Q_0_5_m", "Q_5_20_m", "rmse_x_0_20_m", "rmse_y_0_20_m", "rmse_z_0_20_m",
            "peak_m", "p95_m", "motor_saturated_fraction", "generalized_clipped_fraction")}
            for name, item in scored.items()},
        "Q_differences_m": {"C6_minus_C5": q["C6"] - q["C5"], "C6_minus_B72": q["C6"] - q["B72"],
                            "C5_minus_B72": q["C5"] - q["B72"]},
        "interpretation": "One DEV scene only; descriptive paired values, not a screen gate or tail authorization.",
    }
    raw_review = {
        "schema": "C6_FIRST_SCENE_RAW_REVIEW_V1", "status": "PASS_C6_FIRST_RAW_ALL_EVENTS",
        "scope": "FIXED_DEV_FIRST_SCENE_ONLY", "scene_id": SCENE, "candidate": C6_CANDIDATE,
        "event_count": event_result["event_count"], "raw_path": str(c6_raw_path), "raw_sha256": c6_raw_sha,
        "prepared_snapshot_path": str(snapshot_path), "prepared_snapshot_sha256": sha(snapshot_path),
        "C6_event_audit": event_result, "paired_C6_C5_B72": pair, "safety_and_actuators": safety,
        "metric_scorer_sha256": SCORER_SHA, "mat_decoder_sha256": DECODER_SHA,
        "plant_calls_in_this_audit": 0, "TEST_accessed": False,
    }
    metadata_review = {
        "schema": "C6_FIRST_SCENE_METADATA_OS_REVIEW_V1", "status": "PASS_C6_FIRST_RAW_METADATA_NATURAL_OS0",
        "scene_id": SCENE, "event_count": event_result["event_count"],
        "natural_process_return": True, "natural_MATLAB_OS_exit_code": 0,
        "actual_candidate_Plant": int(c6_status["plant_calls"]), "new_Plant_in_this_audit": 0,
        "first_scene_review_is_tail_authorization": False, "TEST_accessed": False,
        "release_sha256": sha(release_path), "input_lock_sha256": sha(lock_path),
        "source_binding_sha256": sha(binding_path), "run_status_sha256": sha(c6_status_path),
        "raw_sha256": c6_raw_sha, "run_start_sha256": c6_status["run_start_sha256"].lower(),
        "first_plant_step_marker_sha256": c6_status["first_plant_step_marker_sha256"].lower(),
        "execution_receipt_sha256": sha(receipt_path), "os_exit_receipt_sha256": sha(os_exit_path),
        "outer_invocation_history_sha256": sha(history_path),
    }
    with raw_review_path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(raw_review, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    with metadata_review_path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(metadata_review, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"status": raw_review["status"], "scene_id": SCENE, "event_count": event_result["event_count"],
                      "raw_sha256": c6_raw_sha, "metadata_status": metadata_review["status"],
                      "tail_authorized": False}))


if __name__ == "__main__":
    main()

