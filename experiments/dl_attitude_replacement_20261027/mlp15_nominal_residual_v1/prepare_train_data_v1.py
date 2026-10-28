#!/usr/bin/env python3
"""Build an identity-locked, TRAIN_C5_24-only MLP15 residual dataset."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
LOCK_PATH = ROOT / "experiments/dl_attitude_replacement_20261026/mlp15_c5_teacher_full72_v1/MLP15_C5_TEACHER_FULL72_SOURCE_LOCK_v1.json"
CONFIG_PATH = ROOT / "experiments/dl_attitude_replacement_20261026/mlp15_c5_teacher_full72_v1/runs/C5_MLP15_FULL72_SEED2026102001/training_config.json"
DATA_PATH = ROOT / "experiments/dl_attitude_replacement_20261026/mlp15_c5_teacher_redistill_v1/matched_teacher_data_v1.npz"
DATA_MANIFEST_PATH = ROOT / "experiments/dl_attitude_replacement_20261026/mlp15_c5_teacher_redistill_v1/DATASET_MANIFEST_v1.json"
CAUSAL_RELEASE_PATH = ROOT / "experiments/dl_attitude_replacement_20261026/mlp15_causal_head_v1/RELEASE.json"
OUTPUT_NPZ = HERE / "TRAIN_C5_24_PHYSICAL_RESIDUAL_v1.npz"
OUTPUT_MANIFEST = HERE / "TRAIN_C5_24_PHYSICAL_RESIDUAL_MANIFEST_v1.json"

FEATURE_ORDER = [
    "wrapped_attitude_error_euler_rad_x3",
    "body_rate_rad_s_x3",
    "nominal_bs_body_torque_Nm_x3",
    "morph_command_x4",
]
FEATURE_CODE = "experiments/dl_attitude_replacement_20261026/mlp15_c5_teacher_redistill_v1/build_matched_teacher_dataset_v1.py"
REFERENCE_FEATURE_CODE = "experiments/dl_attitude_replacement_20261026/prepare_tcn_teacher_dataset_v2.py"
MLP_CODE = "experiments/dl_attitude_replacement_20261026/architecture_screen_v1/screen_attitude_architectures_v1.py"
N_STATES, N_TRANSITIONS = 20_001, 20_000
EVENTS = np.arange(10, 20_000, 10, dtype=np.int64)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def repo_path(value: str) -> Path:
    path = Path(value)
    return (path if path.is_absolute() else ROOT / path).resolve()


def h5_text(group: h5py.Group, key: str) -> str:
    values = np.asarray(group[key]).reshape(-1)
    if values.dtype.kind in "ui":
        return "".join(chr(int(value)) for value in values if int(value) != 0)
    if values.dtype.kind in "SU":
        return "".join(value.decode() if isinstance(value, bytes) else str(value)
                        for value in values).rstrip("\x00")
    return str(values[0]) if len(values) == 1 else ""


def h5_optional_text(group: h5py.Group, key: str) -> str:
    return h5_text(group, key) if key in group else ""


def ordered_ids_sha(ids: list[str]) -> str:
    return hashlib.sha256(json.dumps(ids, separators=(",", ":")).encode("utf-8")).hexdigest()


def verify_source_bindings(lock: dict[str, Any], config: dict[str, Any], data_manifest: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if sha256(LOCK_PATH) != config["dataset_identity"]["source_lock_sha256"]:
        raise ValueError("full72 source-lock SHA differs from frozen training_config")
    if config.get("dataset_identity", {}).get("source_lock_sha256") != sha256(LOCK_PATH):
        raise ValueError("training_config does not bind current source lock")
    if lock.get("status") != "APPROVED_FOR_TRAINING":
        raise ValueError("C5 source lock is not identity-approved")

    locked_sources = lock.get("source_file_sha256", {})
    config_sources = config["dataset_identity"].get("source_file_sha256", {})
    code_hashes: dict[str, str] = {}
    for relative in (FEATURE_CODE, REFERENCE_FEATURE_CODE, MLP_CODE):
        expected = locked_sources.get(relative)
        if not expected or config_sources.get(relative) != expected:
            raise ValueError(f"source lock/config do not bind {relative}")
        actual = sha256(repo_path(relative))
        if actual != expected:
            raise ValueError(f"locked source-code SHA mismatch: {relative}")
        code_hashes[relative] = actual

    lock_rows = [row for row in lock.get("scene_sources", [])
                 if row.get("source_split") == "TRAIN_C5_24"]
    config_rows = [row for row in config["dataset_identity"].get("scene_sources", [])
                   if row.get("source_split") == "TRAIN_C5_24"]
    data_rows = [row for row in data_manifest.get("rows", [])
                 if row.get("split") == "TRAIN_C5_24"]
    if not (len(lock_rows) == len(config_rows) == len(data_rows) == 24):
        raise ValueError("TRAIN_C5_24 must contain exactly 24 identity-locked scenes")
    expected_ids = [row["scene_id"] for row in lock_rows]
    if (expected_ids != config["dataset_identity"]["scene_ids_in_training_order"][:24]
            or expected_ids != [row["scene_id"] for row in data_rows]
            or ordered_ids_sha(expected_ids) != "f3f70c47c5bef1d29181246a9d53fb8e90c3ec3d163bb6d67b18793756656616"):
        raise ValueError("TRAIN_C5_24 scene identity/order differs from the reviewed split")

    config_by_id = {row["scene_id"]: row for row in config_rows}
    manifest_by_id = {row["scene_id"]: row for row in data_rows}
    bound_rows = []
    for row in lock_rows:
        scene_id = row["scene_id"]
        cfg_row, manifest_row = config_by_id[scene_id], manifest_by_id[scene_id]
        for key in ("teacher_source", "raw_sha256", "status_sha256", "run_start_sha256",
                    "scene_identity_sha256", "event_count", "feature_shape", "target_shape",
                    "status_trace_audit_state", "source_split", "raw_path", "status_path", "run_start_path"):
            if row.get(key) != cfg_row.get(key):
                raise ValueError(f"source lock/config {key} mismatch for {scene_id}")
        for source_key, manifest_key in (("raw_sha256", "raw_sha256"),
                                         ("status_sha256", "status_sha256"),
                                         ("run_start_sha256", "run_start_sha256"),
                                         ("scene_identity_sha256", "scene_identity_sha256"),
                                         ("event_count", "event_count")):
            if row.get(source_key) != manifest_row.get(manifest_key):
                raise ValueError(f"source lock/data manifest {source_key} mismatch for {scene_id}")
        for source_key in ("raw_path", "status_path", "run_start_path"):
            if repo_path(row[source_key]) != repo_path(manifest_row[source_key]):
                raise ValueError(f"source path differs between lock and data manifest for {scene_id}")
        bound_row = dict(row)
        bound_row["manifest_source_scene_id"] = manifest_row.get("source_scene_id", scene_id)
        bound_rows.append(bound_row)
    return bound_rows, {"feature_code_sha256": code_hashes,
                       "source_lock_sha256": sha256(LOCK_PATH),
                       "training_config_sha256": sha256(CONFIG_PATH),
                       "data_manifest_sha256": sha256(DATA_MANIFEST_PATH)}


def verify_run_identity(row: dict[str, Any], raw_path: Path, status_path: Path,
                        start_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    for path, field in ((raw_path, "raw_sha256"), (status_path, "status_sha256"),
                        (start_path, "run_start_sha256")):
        if sha256(path) != row[field]:
            raise ValueError(f"actual {field} mismatch for {row['scene_id']}")
    status = read_json(status_path)
    expected_source_scene_id = row.get("manifest_source_scene_id", row["scene_id"])
    if (status.get("scene_id") != row["scene_id"]
            or status.get("raw_sha256", "").lower() != row["raw_sha256"].lower()
            or repo_path(status.get("raw_path", "")) != raw_path
            or int(status.get("transitions", -1)) != N_TRANSITIONS
            or int(status.get("state_samples", -1)) != N_STATES
            or status.get("log_status") != "STABLE"
            or status.get("safety_stop_reason", "") not in ("", None)
            or status.get("source_scene_id", row["scene_id"]) != expected_source_scene_id):
        raise ValueError(f"run_status identity/completion mismatch for {row['scene_id']}")

    with h5py.File(raw_path, "r") as raw:
        identity = raw["runIdentity"]
        raw_id = {"scene_id": h5_optional_text(identity, "scene_id"),
                  "candidate": h5_optional_text(identity, "candidate"),
                  "external_identity_sha256": h5_optional_text(identity, "external_identity_sha256"),
                  "coordinate_mask": np.asarray(identity["coordinate_mask"], dtype=np.float64).reshape(-1).tolist()}
    with h5py.File(start_path, "r") as start:
        root = start["runStart"] if "runStart" in start else start
        scene_identity = root["scene_identity"]
        start_id = {"source_scene_id": h5_optional_text(scene_identity, "source_scene_id"),
                    "external_identity_sha256": h5_optional_text(scene_identity, "external_identity_sha256")}
    if (raw_id["scene_id"] != row["scene_id"]
            or raw_id["candidate"] != "C5_AXIS_MIXED_COORDINATE_M110"
            or raw_id["coordinate_mask"] != [1.0, 1.0, 0.0]
            or raw_id["external_identity_sha256"] != row["scene_identity_sha256"]
            or start_id["source_scene_id"] not in (row["scene_id"], expected_source_scene_id)
            or start_id["external_identity_sha256"] != row["scene_identity_sha256"]):
        raise ValueError(f"raw/run_start scene identity mismatch for {row['scene_id']}")
    return status, {"raw": raw_id, "run_start": start_id}


def build_scene(row: dict[str, Any], J0: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    raw_path, status_path, start_path = (repo_path(row[key]) for key in
                                         ("raw_path", "status_path", "run_start_path"))
    status, identity = verify_run_identity(row, raw_path, status_path, start_path)
    with h5py.File(start_path, "r") as start:
        root = start["runStart"] if "runStart" in start else start
        cfg = root["cfg"] if "cfg" in root else start["cfg"]
        mode = h5_text(cfg, "controller_morphology_mode").lower()
        dmax = np.asarray(cfg["rbf/attitude/dmax"], dtype=np.float64).reshape(-1)
        beta_rise = float(np.asarray(cfg["rbf/attitude/beta_rise_time"], dtype=np.float64).reshape(-1)[0])
    if mode != "fixed" or not np.array_equal(dmax, [45.0, 45.0, 4.7124]) or beta_rise != 2.2:
        raise ValueError(f"unexpected locked C5 controller contract for {row['scene_id']}")

    with h5py.File(raw_path, "r") as raw:
        log = raw["log"]
        time = np.asarray(log["time"], dtype=np.float64).reshape(-1)
        transition_time = np.asarray(log["transition_time"], dtype=np.float64).reshape(-1)
        state = np.asarray(log["state"], dtype=np.float64).T
        reference = np.asarray(log["filtered_attitude_reference"], dtype=np.float64).T
        event_flag = np.asarray(log["attitude_event_flag"]).reshape(-1).astype(bool)
        nominal_torque = np.asarray(log["attitude_bs_nominal_torque_Nm"], dtype=np.float64).T
        requested = np.asarray(log["requested_generalized"], dtype=np.float64).T
        generalized_clipped = np.asarray(log["generalized_clipped"]).T.astype(bool)
        motor_saturated = np.asarray(log["motor_saturated"]).T.astype(bool)
        clipped_request = np.asarray(log["controller_clipped_generalized"], dtype=np.float64).T
        morph_command = np.asarray(raw["scene/arms/command"], dtype=np.float64).T

    if (time.shape != (N_STATES,) or transition_time.shape != (N_TRANSITIONS,)
            or state.shape != (N_STATES, 12) or reference.shape != (N_TRANSITIONS, 3)
            or event_flag.shape != (N_TRANSITIONS,) or nominal_torque.shape != (N_TRANSITIONS, 3)
            or requested.shape != (N_TRANSITIONS, 4)
            or generalized_clipped.shape != (N_TRANSITIONS, 4)
            or motor_saturated.ndim != 2 or motor_saturated.shape[0] != N_TRANSITIONS
            or clipped_request.shape != (N_TRANSITIONS, 4)
            or morph_command.shape != (N_STATES, 4)):
        raise ValueError(f"raw log dimensions changed for {row['scene_id']}")
    if (not np.array_equal(np.flatnonzero(event_flag), EVENTS)
            or abs(time[0]) > 1e-12 or abs(time[-1] - 20.0) > 1e-12
            or np.max(np.abs(np.diff(time) - 0.001)) > 1e-12
            or np.max(np.abs(transition_time - time[:-1])) > 1e-12):
        raise ValueError(f"event/time contract changed for {row['scene_id']}")
    tau_issued = requested[:, 1:4]
    generalized_clip_count = int(np.count_nonzero(generalized_clipped))
    motor_saturation_count = int(np.count_nonzero(motor_saturated))
    clipping_error = float(np.max(np.abs(clipped_request - requested)))
    if generalized_clip_count or motor_saturation_count or clipping_error > 1e-12:
        raise ValueError(f"allocator/motor saturation or clipping in TRAIN raw {row['scene_id']}: "
                         f"generalized_clipped={generalized_clip_count}, motor_saturated={motor_saturation_count}, "
                         f"controller_clip_error={clipping_error}")
    if not np.isfinite(np.concatenate((time, transition_time, state.ravel(), reference.ravel(),
                                      nominal_torque.ravel(), tau_issued.ravel(), morph_command.ravel()))).all():
        raise ValueError(f"non-finite legal raw values for {row['scene_id']}")
    if np.max(np.abs(morph_command)) > 1.0 + 1e-12:
        raise ValueError(f"normalized morph command outside [-1,1] for {row['scene_id']}")

    omega = state[EVENTS, 9:12]
    error = reference[EVENTS] - state[EVENTS, 6:9]
    error = np.arctan2(np.sin(error), np.cos(error))
    features = np.concatenate((error, omega, nominal_torque[EVENTS], morph_command[EVENTS]), axis=1)

    residuals = np.empty((len(EVENTS), 3), dtype=np.float64)
    endpoint_equiv_error = 0.0
    for n, end in enumerate(EVENTS):
        start = int(end - 10)
        interval_time = time[start:end + 1]
        interval_omega = state[start:end + 1, 9:12]
        dt = np.diff(interval_time)
        omega_dot = np.diff(interval_omega, axis=0) / dt[:, None]
        gyro = np.cross(interval_omega[:-1], interval_omega[:-1] @ J0.T)
        # requested_generalized is the controller command at transition start;
        # exclude row=end because it is issued at the feature timestamp.
        tau = tau_issued[start:end]
        sample_residual = np.linalg.solve(J0, (omega_dot @ J0.T + gyro - tau).T).T
        residuals[n] = sample_residual.mean(axis=0)
        endpoint = ((interval_omega[-1] - interval_omega[0]) / (interval_time[-1] - interval_time[0])
                    + np.linalg.solve(J0, (gyro - tau).T).T.mean(axis=0))
        endpoint_equiv_error = max(endpoint_equiv_error,
                                   float(np.max(np.abs(endpoint - residuals[n]))))
        if (int(EVENTS[n]) != end or end > EVENTS[n] or start < 0
                or interval_time[-1] != time[end]
                or int(end - 1) >= end
                or not np.all(transition_time[start:end] < time[end])):
            raise ValueError(f"residual label uses a future/wrongly aligned source for {row['scene_id']} event {end}")
    if endpoint_equiv_error > 1e-9 or features.shape != (1999, 13) or residuals.shape != (1999, 3):
        raise ValueError(f"feature/residual construction self-check failed for {row['scene_id']}")

    record = {
        "scene_id": row["scene_id"], "split": "TRAIN_C5_24",
        "raw_path": row["raw_path"], "raw_sha256": row["raw_sha256"],
        "status_path": row["status_path"], "status_sha256": row["status_sha256"],
        "run_start_path": row["run_start_path"], "run_start_sha256": row["run_start_sha256"],
        "scene_identity_sha256": row["scene_identity_sha256"],
        "candidate": "C5_AXIS_MIXED_COORDINATE_M110", "coordinate_mask": [1, 1, 0],
        "event_count": len(EVENTS), "event_index_zero_based_first_last": [int(EVENTS[0]), int(EVENTS[-1])],
        "event_time_s_first_last": [float(time[EVENTS[0]]), float(time[EVENTS[-1]])],
        "feature_shape": list(features.shape), "target_shape": list(residuals.shape),
        "requested_torque_source": "log/requested_generalized[:,1:4], command issued at transition start",
        "requested_torque_static_contract": "runtime sets command=[thrust; moments], requested_generalized=command, and attitude_bs_step sets moments=nominalMoment-estimateTorque",
        "generalized_clipped_true_count": generalized_clip_count,
        "motor_saturated_true_count": motor_saturation_count,
        "controller_clip_command_max_abs_error": clipping_error,
        "max_endpoint_formula_equivalence_abs_error_rad_s2": endpoint_equiv_error,
        "label_endpoint_max_state_sample_index": int(EVENTS[-1]),
        "label_endpoint_max_issued_torque_transition_index": int(EVENTS[-1] - 1),
        "max_label_time_s": float(time[EVENTS[-1]]),
        "morph_command_min_max": [float(morph_command.min()), float(morph_command.max())],
        "status": status.get("status"),
        "status_source_scene_id": status.get("source_scene_id", row["scene_id"]),
        "identity": identity,
    }
    return features, residuals, {"record": record, "time": time[EVENTS],
                                 "start_indices": EVENTS - 10, "issued_torque_last_indices": EVENTS - 1}


def synthetic_sign_check(J0: np.ndarray) -> dict[str, Any]:
    dt = 0.001
    tau_issued = np.array([0.013, -0.008, 0.005], dtype=np.float64)
    disturbance_accel = np.array([0.7, -0.4, 0.2], dtype=np.float64)
    disturbance_torque = J0 @ disturbance_accel

    def integrate(disturbance: np.ndarray) -> np.ndarray:
        omega = np.zeros((11, 3), dtype=np.float64)
        for i in range(10):
            gyro = np.cross(omega[i], J0 @ omega[i])
            omega_dot = np.linalg.solve(J0, tau_issued + disturbance - gyro)
            omega[i + 1] = omega[i] + dt * omega_dot
        return omega

    def estimate(omega: np.ndarray, disturbance: np.ndarray) -> np.ndarray:
        omega_dot = np.diff(omega, axis=0) / dt
        gyro = np.cross(omega[:-1], omega[:-1] @ J0.T)
        samples = np.linalg.solve(J0, (omega_dot @ J0.T + gyro - tau_issued).T).T
        result = samples.mean(axis=0)
        assert np.max(np.abs(result - np.linalg.solve(J0, disturbance))) < 1e-10
        return result

    recovered = estimate(integrate(disturbance_torque), disturbance_torque)
    zero = estimate(integrate(np.zeros(3)), np.zeros(3))
    assert np.allclose(recovered, disturbance_accel, rtol=0, atol=1e-10)
    assert np.allclose(zero, 0, rtol=0, atol=1e-10)
    return {"known_disturbance_torque_Nm": disturbance_torque.tolist(),
            "known_compensation_acceleration_rad_s2": disturbance_accel.tolist(),
            "recovered_residual_rad_s2": recovered.tolist(),
            "zero_disturbance_residual_rad_s2": zero.tolist(),
            "sign": "positive disturbance gives positive compensation-acceleration label; controller subtracts J0*estimate"}


def main() -> None:
    if OUTPUT_NPZ.exists() or OUTPUT_MANIFEST.exists():
        raise FileExistsError("refusing to overwrite an existing isolated artifact")
    lock, config, data_manifest = (read_json(path) for path in
                                   (LOCK_PATH, CONFIG_PATH, DATA_MANIFEST_PATH))
    lock_rows, identities = verify_source_bindings(lock, config, data_manifest)
    fixed_ref = data_manifest["fixed_J0_reference"]
    J0 = np.diag(np.asarray(fixed_ref["diagonal_kg_m2"], dtype=np.float64))
    old_release = read_json(CAUSAL_RELEASE_PATH)
    old_J0 = np.asarray(old_release["fixed_J0_kgm2"], dtype=np.float64)
    if np.max(np.abs(old_J0 - J0)) > 1e-14:
        raise ValueError("fixed-J0 reference differs from the locked causal-head parent")
    fixed_audit = repo_path(fixed_ref["source_audit_path"])
    if sha256(fixed_audit) != fixed_ref["source_audit_sha256"]:
        raise ValueError("fixed-J0 source audit SHA mismatch")

    reference_x = np.load(DATA_PATH, allow_pickle=False)["c5_train_x"]
    reference_ids = np.load(DATA_PATH, allow_pickle=False)["c5_train_scene_ids"].astype(str).tolist()
    ids = [row["scene_id"] for row in lock_rows]
    if reference_x.shape != (24, 1999, 13) or reference_ids != ids:
        raise ValueError("TRAIN-only reference feature array identity/shape mismatch")

    x_rows, y_rows, records, times = [], [], [], []
    start_indices = issued_last_indices = None
    feature_max_error = 0.0
    for i, row in enumerate(lock_rows):
        x, y, audit = build_scene(row, J0)
        difference = np.abs(x.astype(np.float32) - reference_x[i])
        feature_max_error = max(feature_max_error, float(difference.max(initial=0.0)))
        if not np.array_equal(x.astype(np.float32), reference_x[i]):
            raise ValueError(f"reconstructed features differ from locked TRAIN feature row: {row['scene_id']}")
        x_rows.append(x.astype(np.float32)); y_rows.append(y.astype(np.float32))
        records.append(audit["record"]); times.append(audit["time"])
        if start_indices is None:
            start_indices = audit["start_indices"]
            issued_last_indices = audit["issued_torque_last_indices"]

    X, Y = np.stack(x_rows), np.stack(y_rows)
    event_times = np.stack(times)
    sign_audit = synthetic_sign_check(J0)
    if X.shape != (24, 1999, 13) or Y.shape != (24, 1999, 3):
        raise ValueError("final TRAIN-only dataset dimensions are incorrect")
    if not np.isfinite(X).all() or not np.isfinite(Y).all():
        raise ValueError("final TRAIN-only dataset contains non-finite values")

    ids_sha = ordered_ids_sha(ids)
    np.savez_compressed(OUTPUT_NPZ, x_train=X, y_train=Y,
                        scene_ids=np.asarray(ids, dtype="U32"), event_indices=EVENTS,
                        event_time_s=event_times, label_start_state_indices=start_indices,
                        label_endpoint_state_indices=EVENTS,
                        issued_torque_last_transition_indices=issued_last_indices,
                        fixed_J0_kg_m2=J0)
    target_rms = np.sqrt(np.mean(Y.astype(np.float64) ** 2, axis=(0, 1)))
    manifest = {
        "schema": "DL1018_MLP15_TRAIN_C5_24_FIXED_J0_RESIDUAL_V1",
        "status": "PASS_TRAIN_ONLY_SOURCE_AND_CAUSALITY_AUDIT",
        "dataset_path": OUTPUT_NPZ.relative_to(ROOT).as_posix(),
        "dataset_sha256": sha256(OUTPUT_NPZ), "dataset_bytes": OUTPUT_NPZ.stat().st_size,
        "source_lock_path": LOCK_PATH.relative_to(ROOT).as_posix(),
        "source_lock_sha256": identities["source_lock_sha256"],
        "legacy_training_config_path": CONFIG_PATH.relative_to(ROOT).as_posix(),
        "legacy_training_config_sha256": identities["training_config_sha256"],
        "legacy_config_split_note": "legacy full72 model fit used TRAIN_C5_24 plus C5_VAL48_AS_DEV_TRAIN; it is identity metadata only here",
        "feature_code_sha256": identities["feature_code_sha256"],
        "reference_c5_data_manifest_sha256": identities["data_manifest_sha256"],
        "reference_feature_members_read": ["c5_train_x", "c5_train_scene_ids"],
        "reference_val_members_read": False, "reference_rbf_target_members_read": False,
        "train_split": "TRAIN_C5_24", "train_scene_count": len(ids),
        "events_per_scene": len(EVENTS), "train_event_count": int(X.shape[0] * X.shape[1]),
        "ordered_train_scene_ids_sha256": ids_sha, "scene_ids": ids,
        "feature_order": FEATURE_ORDER,
        "feature_definition": "At each event: wrapped(filtered_attitude_reference - state Euler), body omega, logged nominal BS body torque, scene/arms/command.",
        "feature_shape": list(X.shape), "target_shape": list(Y.shape),
        "target_definition": "For each event endpoint e: mean over transitions i=e-10..e-1 of J0^-1*(J0*delta_omega_i/dt_i + omega_i x (J0*omega_i) - tau_issued_i).",
        "target_units": "rad/s^2; compensation acceleration, subtracted through the existing fixed-J0 path",
        "fixed_J0_kg_m2": J0.tolist(),
        "fixed_J0_source_audit_path": fixed_ref["source_audit_path"],
        "fixed_J0_source_audit_sha256": fixed_ref["source_audit_sha256"],
        "target_rms_from_train_only_rad_s2": target_rms.tolist(),
        "target_rms_rule": "sqrt(mean(y_train**2, axes=(scene,event))); TRAIN_C5_24 only",
        "event_schedule": {"sample_dt_s": 0.001, "event_stride_transitions": 10,
                           "zero_based_state_indices_first_last": [int(EVENTS[0]), int(EVENTS[-1])],
                           "matlab_state_indices_first_last": [int(EVENTS[0] + 1), int(EVENTS[-1] + 1)],
                           "event_time_s_first_last": [float(event_times[0, 0]), float(event_times[0, -1])],
                           "event_timestamp_sha256_per_scene": [hashlib.sha256(np.ascontiguousarray(t).tobytes()).hexdigest() for t in event_times]},
        "label_causality": {"state_window_per_event": "[e-10, e], endpoint equals feature event sample e",
                            "issued_torque_transition_indices": "[e-10, e-1]; row e is excluded because it is issued at feature time",
                            "max_label_state_index": int(EVENTS[-1]),
                            "max_issued_torque_index": int(EVENTS[-1] - 1),
                            "future_samples_used": False},
        "feature_reconstruction_max_abs_error_vs_locked_train_x_float32": feature_max_error,
        "synthetic_sign_and_units_check": sign_audit,
        "records": records,
        "C5_VAL48_loaded_for_training": False, "TEST_read": False,
        "Plant_called": False, "Plant_truth_read": False,
        "RBF_outputs_or_hidden_states_read_for_target_or_features": False,
    }
    OUTPUT_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": manifest["status"], "train_scenes": len(ids),
                      "train_events": manifest["train_event_count"],
                      "feature_max_abs_error": feature_max_error,
                      "target_rms_rad_s2": target_rms.tolist(),
                      "dataset_sha256": manifest["dataset_sha256"],
                      "manifest_sha256": sha256(OUTPUT_MANIFEST),
                      "val_loaded": False, "test_read": False, "plant_called": False}, indent=2))


if __name__ == "__main__":
    main()
