"""Independent parent audit for the frozen C5 M110 DEV72 batch.

The 1968-event equations are carried forward from the immutable
check_c5_raw_parent.py (SHA pinned below). A reuse-only self-check is safe
before the new batch; the final DEV72 verdict is gated on its natural OS exit.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import re
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import h5py
import numpy as np


ROOT = Path(__file__).resolve().parents[3]
EXP = ROOT / "experiments/position_axis_coordinate_c5_dev72_20261023"
REPORT = ROOT / "reports/paper_continuation_20261023/c5_dev72_execution"
REVIEW = ROOT / "reports/paper_continuation_20261023/c5_dev72_parent_review"
OLD_AUDIT = ROOT / "reports/paper_continuation_20261023/c5_axis_coordinate_parent_review/check_c5_raw_parent.py"
SCORER_PATH = ROOT / "reports/delayed_prediction_c3_dev72_parent_20261023/parent_raw_metrics.py"
DECODER_PATH = ROOT / "reports/paper14_v2/phase1/audit_w15_position_replay.py"
OLD_SCREEN = ROOT / "reports/paper_continuation_20261023/c5_axis_coordinate_parent_review/screen12_parent_review/SUMMARY.json"
OLD_AUDIT_SHA = "59cb79f91d49e3d5ca3c268007038a66a3692f75a2cd354535f13cb8ad39fdcb"
SCORER_SHA = "c64482d0adbc4358417648ec08351bd78f1d3dbdb38950435fa71b9cb0f531b1"
DECODER_SHA = "372d92cb17da99884e742d3fa0c877200c3bb2bc6fac7f10e7a1a046b97a76af"
BATCH_VERSION = "v3"


def configure_version(version):
    global BATCH_VERSION, LOCK, CONTRACT, BINDING, PREP, SNAPSHOT, RELEASE, BATCH, BODY
    global OS_EXIT, NOPLANT_OS_EXIT, RUNNER, PLANT_LAUNCHER, NOPLANT_LAUNCHER, ATTEMPT_DIRNAME, RELEASE_CONTRACT
    assert version in ("v1", "v2", "v3")
    BATCH_VERSION = version
    LOCK = EXP / f"C5_DEV72_INPUT_LOCK_{version}.json"
    CONTRACT = EXP / f"C5_DEV72_RUN_CONTRACT_{version}.json"
    BINDING = EXP / f"C5_DEV72_SOURCE_BINDING_{version}.json"
    PREP = EXP / f"C5_DEV72_PREPARE_RESULT_{version}.json"
    SNAPSHOT = EXP / f"C5_DEV72_PREPARED_CFG_OPTS_{version}.mat"
    RELEASE = EXP / f"C5_DEV72_RELEASE_{version}.json"
    BATCH = EXP / f"C5_DEV72_BATCH_STATUS_{version}.json"
    BODY = EXP / f"C5_DEV72_BODY_COMPLETE_{version}.json"
    RELEASE_CONTRACT = EXP / f"C5_DEV72_PARENT_RELEASE_CONTRACT_{version}.json"
    OS_EXIT = REPORT / f"C5_DEV72_MATLAB_OS_EXIT_{version}.json"
    NOPLANT_OS_EXIT = REPORT / f"C5_DEV72_NOPLANT_OS_EXIT_{version}.json"
    RUNNER = EXP / f"run_c5_dev72_{version}.m"
    PLANT_LAUNCHER = EXP / f"RUN_C5_DEV72_EXACT_{version}.ps1"
    NOPLANT_LAUNCHER = EXP / f"RUN_C5_DEV72_NOPLANT_EXACT_{version}.ps1"
    ATTEMPT_DIRNAME = f"runs_dev72_{version}"


configure_version(BATCH_VERSION)


def sha(path: Path | str) -> str:
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def exact_utc_instant(value):
    assert isinstance(value, str)
    match = re.fullmatch(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d+))?(Z|\+00:00)", value)
    assert match, value
    parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    assert parsed.tzinfo is not None and parsed.utcoffset() == timedelta(0), value
    fraction = Decimal("0." + match.group(2)) if match.group(2) else Decimal(0)
    return parsed.replace(microsecond=0), fraction


def strict_json_equal(left, right):
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(strict_json_equal(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(strict_json_equal(a, b) for a, b in zip(left, right))
    return left == right


def compare_batch_body_records(batch_records, body_records):
    assert len(batch_records) == len(body_records) == 60
    differences = []
    for index, (batch_row, body_row) in enumerate(zip(batch_records, body_records)):
        assert isinstance(batch_row, dict) and isinstance(body_row, dict)
        assert batch_row.keys() == body_row.keys() and "created_utc" in batch_row
        assert all(strict_json_equal(batch_row[key], body_row[key])
                   for key in batch_row.keys() - {"created_utc"}), (index, batch_row, body_row)
        batch_text, body_text = batch_row["created_utc"], body_row["created_utc"]
        assert exact_utc_instant(batch_text) == exact_utc_instant(body_text), (index, batch_text, body_text)
        if batch_text != body_text:
            differences.append({"index": index, "scene_id": batch_row["scene_id"],
                                "batch_created_utc": batch_text, "body_created_utc": body_text,
                                "same_exact_utc_instant": True})
    assert len(differences) == 8, differences
    return differences


def load(path: Path | str):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def module_at(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(value)
    return value


def matlab_text(value):
    if isinstance(value, tuple) and len(value) == 3 and value[0] == "__matlab_char__":
        return value[2]
    return value


def h5_tree_cell_safe(node):
    """Decode MATLAB v7.3 values like the pinned decoder, boxing each cell ref."""
    if isinstance(node, h5py.Group):
        return {key: h5_tree_cell_safe(value) for key, value in node.items()}
    value = node[()]
    matlab_class = node.attrs.get("MATLAB_class", b"")
    if isinstance(matlab_class, bytes):
        matlab_class = matlab_class.decode(errors="ignore")
    if matlab_class == "char":
        matlab_order = np.transpose(np.asarray(value))
        return ("__matlab_char__", tuple(matlab_order.shape), "".join(
            chr(int(code)) for code in matlab_order.flatten(order="F") if int(code) != 0))
    if isinstance(value, np.ndarray) and value.dtype.kind == "O":
        matlab_order = np.transpose(value)
        shaped = np.empty(matlab_order.shape, dtype=object)
        for idx, ref in enumerate(matlab_order.flat):
            shaped.flat[idx] = h5_tree_cell_safe(node.file[ref]) if ref else None
        return shaped.tolist()
    if isinstance(value, np.ndarray):
        return np.transpose(value).tolist()
    if isinstance(value, np.generic):
        return value.item()
    return value


def matlab_section_safe(path: Path, name: str, decoder):
    """Use the corrected v7.3 cell boxing, retaining the pinned MAT5 fallback."""
    path = Path(path)
    if h5py.is_hdf5(path):
        with h5py.File(path, "r") as mat:
            return h5_tree_cell_safe(mat[name])
    return decoder.matlab_section(path, name)


def matlab_scalar(value):
    values = matlab_flat(value)
    assert len(values) == 1, (type(value).__name__, len(values))
    return values[0]


def matlab_flat(value):
    value = matlab_text(value)
    if isinstance(value, np.ndarray):
        value = value.ravel().tolist()
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, (list, tuple)):
        out = []
        for child in value:
            out.extend(matlab_flat(child))
        return out
    return [value]


def equal_tree(left, right, decoder, *, ignore_marker=False):
    a = decoder.flatten(left)
    b = decoder.flatten(right)
    if ignore_marker:
        b.pop("r2e_first_plant_step_marker", None)
    assert a.keys() == b.keys(), (sorted(a), sorted(b))
    assert all(decoder.same_value(b[k], a[k]) for k in a), "MATLAB tree differs"
    return len(a)


def scene_identity_row(scene_identity, index):
    row = {}
    for key, value in scene_identity.items():
        values = matlab_flat(value)
        assert index < len(values), (key, index, len(values))
        row[key] = values[index]
    return row


def scalar_equal(a, b, decoder):
    a = matlab_text(a)
    b = matlab_text(b)
    if isinstance(a, (str, bool, int)) and isinstance(b, (str, bool, int)):
        return a == b
    try:
        x, y = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
        return x.shape == y.shape and bool(np.allclose(x, y, rtol=0, atol=1e-12, equal_nan=False))
    except (TypeError, ValueError):
        return str(a) == str(b)


def compare_scene_identity(actual, expected, decoder):
    assert set(actual) == set(expected), (sorted(actual), sorted(expected))
    for key, expected_value in expected.items():
        if key == "alias_normalized_in_memory":
            actual_value = matlab_scalar(actual[key])
            expected_value = matlab_scalar(expected_value)
            assert actual_value in (0, 1, False, True) and expected_value in (0, 1, False, True)
            assert int(actual_value) == int(expected_value), (key, actual_value, expected_value)
        else:
            assert scalar_equal(actual[key], expected_value, decoder), (key, matlab_text(actual[key]), expected_value)


def verify_status_file(path, expected_sha, *, scene_id=None, raw_path=None, raw_sha=None,
                       coordinate_mask=None, require_event_counts=False,
                       required_markers=("raw", "run_start", "first_plant_step_marker")):
    path = Path(path)
    assert path.is_file() and sha(path) == expected_sha.lower(), path
    status = load(path)
    if scene_id is not None:
        assert status["scene_id"] == scene_id
    assert status["status"] == "RUN_COMPLETE_RAW_PENDING_AUDIT"
    assert status["plant_calls"] == 1 and status["training_steps"] == status["optimizer_steps"] == 0
    assert status["TEST_accessed"] is False and status["log_status"] == "STABLE"
    assert status["plant_invocation_entered"] and status["plant_start_confirmed"]
    assert status["parameter_or_seed_search"] is False and status.get("new_B_sorties", 0) == 0
    assert status["safety_stop_reason"] == ""
    if raw_path is not None:
        assert Path(status["raw_path"]).resolve() == Path(raw_path).resolve()
    if raw_sha is not None:
        assert status["raw_sha256"].lower() == raw_sha.lower()
    if coordinate_mask is not None:
        assert status["coordinate_mask"] == coordinate_mask
    if require_event_counts:
        assert all(k in status for k in ("last_transition", "transitions", "state_samples")), status.keys()
        assert (status["last_transition"], status["transitions"], status["state_samples"]) == (20000, 20000, 20001)
    required_markers = set(required_markers)
    for name in ("raw", "run_start", "attempt_started_marker", "first_plant_step_marker"):
        path_key, sha_key = f"{name}_path", f"{name}_sha256"
        present = path_key in status or sha_key in status
        if name not in required_markers and not present:
            continue
        assert path_key in status and sha_key in status, (name, sorted(status))
        p = Path(status[path_key])
        assert p.is_file() and sha(p) == status[sha_key].lower(), (name, p)
    return status


def checked_metric(item, scorer):
    return scorer.score(item)


def event_audit(raw_path: Path, cfg: dict, *, expected_w0=None, expected_w0_sha256=None):
    """Exact 1968-event numerical checks inherited from the pinned C5 checker."""
    with h5py.File(raw_path, "r") as file:
        g = file["log"]

        def read(key):
            value = np.asarray(g[key])
            return value.T if value.ndim == 2 else value

        ids = np.flatnonzero(read("stage1_position_event_inference_valid").ravel())
        assert np.array_equal(ids, np.arange(320, 19991, 10)) and len(ids) == 1968
        for key in ("stage1_position_delayed_prediction_enabled", "stage1_position_replacement_enabled",
                    "stage1_position_pcf_coordination_enabled", "stage1_position_update_enabled"):
            assert read(key).item() == 1, key
        assert np.array_equal(read("stage1_position_coordinate_mask").ravel(), [1, 1, 0])
        assert read("stage1_position_search_gamma").item() == 12
        assert read("stage1_position_search_kappa").item() == 1
        initial = read("stage1_position_search_initial_weight")
        assert np.array_equal(initial, read("stage1_position_weight_initial"))
        if expected_w0 is not None:
            assert np.array_equal(initial, np.asarray(expected_w0, dtype=float))
        if expected_w0_sha256 is not None:
            assert hashlib.sha256(np.asarray(initial, dtype="<f8").tobytes(order="F")).hexdigest() == expected_w0_sha256.lower()
        phi = read("stage1_position_event_phi_33")[ids]
        wb = np.asarray(g["stage1_position_event_weight_before_33x3"]).transpose(0, 2, 1)
        wa = np.asarray(g["stage1_position_event_weight_after_33x3"]).transpose(0, 2, 1)
        assert wb.shape == wa.shape == (len(ids), 33, 3) and np.array_equal(wb[0], initial)
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
        assert np.isnan(previous[0]) and np.isnan(target[0]).all()
        assert np.array_equal(previous[1:], ids[:-1])
        reference = af.copy()
        reference[:, 2] = req[:, 2]
        y = np.array([((state[k, 3:6] - state[j, 3:6]) - .001 * reference[j:k].sum(axis=0)) / .01
                      for j, k in zip(ids[:-1], ids[1:])])
        beta = np.minimum((ids + 1) * .001 / 1.8, 1)
        raw = np.einsum("nfi,nf->ni", wb, phi)
        gradient = np.zeros_like(wb)
        gradient[1:] = phi[:-1, :, None] * (np.einsum("nfi,nf->ni", wb[1:], phi[:-1]) - y)[:, None, :]
        surface = (read("reference/velocity")[:-1] - state[:-1, 3:6]
                   + read("reference/position")[:-1] - state[:-1, :3])[ids]
        coordinated = surface - eta[ids] * np.array([1, 1, 0])
        effective = np.clip(coordinated, -np.array([7, 8, 10]), np.array([7, 8, 10]))
        expected = np.clip(wb - .12 * beta[:, None, None] * phi[:, :, None] * effective[:, None, :]
                           - .00002 * wb - .01 * gradient, -60, 60)
        held = np.zeros((20000, 3))
        applied = beta[:, None] * np.clip(raw, -3, 3)
        for index, k in enumerate(ids):
            held[k:min(k + 10, 20000)] = applied[index]
        reference_integral = np.vstack((np.zeros((1, 3)), np.cumsum(.001 * reference, axis=0)))[:-1]
        af_integral = np.vstack((np.zeros((1, 3)), np.cumsum(.001 * af, axis=0)))[:-1]

        def diff(a, b):
            assert np.isfinite(a).all() and np.isfinite(b).all()
            return float(np.max(np.abs(a - b)))

        checks = {
            "phi_unit_norm": diff(np.linalg.norm(phi, axis=1), np.ones(len(ids))),
            "past_mixed_reference_target": diff(target[1:], y),
            "surface_original_from_actual_state": diff(read("stage1_position_pcf_event_s_original_mps")[ids], surface),
            "surface_M110": diff(read("stage1_position_pcf_event_s_coord_mps")[ids], coordinated),
            "surface_clip_M110": diff(read("stage1_position_pcf_event_s_coord_eff_mps")[ids], effective),
            "eta_event_before": diff(read("stage1_position_pcf_event_eta_before_mps")[ids], eta[ids]),
            "output_before_update": diff(read("stage1_position_event_raw_acceleration_mps2")[ids], raw),
            "applied_beta_clip": diff(read("stage1_position_event_applied_acceleration_mps2")[ids], applied),
            "beta_clock": diff(read("stage1_position_event_beta").ravel()[ids], beta),
            "event_period": diff(read("stage1_position_event_dt_s").ravel()[ids], np.full(len(ids), .01)),
            "joint_update_once": diff(wa, expected),
            "weight_continuity": diff(wb[1:], wa[:-1]),
            "prediction_term_norm": diff(read("stage1_position_delayed_prediction_term_norm").ravel()[ids], .01 * np.linalg.norm(gradient, axis=(1, 2))),
            "separate_actual_af_integral": diff(read("stage1_position_delayed_prediction_af_integral_before_step_mps"), af_integral),
            "M110_reference_integral": diff(read("stage1_position_delayed_prediction_reference_integral_before_step_mps"), reference_integral),
            "event_reference_integral": diff(read("stage1_position_delayed_prediction_event_reference_integral_mps")[ids], reference_integral[ids]),
            "event_velocity": diff(read("stage1_position_delayed_prediction_event_velocity_mps")[ids], state[ids, 3:6]),
            "held_compensation": diff(read("position_compensation_applied_acceleration_mps2"), held),
            "request_contains_applied_compensation": diff(req, read("position_nominal_acceleration_mps2") - held),
            "rf_definition": diff(rf, req - af),
            "nameplate_af_from_actual_thrust_filtered_attitude": diff(af, nameplate_af),
            "direct_mixed_reference": diff(read("stage1_position_pcf_prediction_reference_mps2"), reference),
            "eta_initial_zero": diff(eta[0], np.zeros(3)),
            "eta_continuity": diff(eta[1:], read("stage1_position_pcf_eta_after_mps")[:-1]),
            "eta_exact_held_step": diff(read("stage1_position_pcf_eta_after_mps"),
                                         np.exp(-.004) * eta + (-np.expm1(-.004)/4) * rf),
        }
        assert max(checks.values()) < 1e-10, checks
        return {"event_count": int(len(ids)), "checks": checks,
                "initial_weight": initial, "log_status": "STABLE"}


def verify_new_run(scene_id, row, record, lock, contract, binding, release, snapshot, decoder, scorer):
    expected_attempt = EXP / ATTEMPT_DIRNAME / scene_id / "C5_AXIS_MASK_M110" / "attempt_01"
    status_path = expected_attempt / "run_status.json"
    raw_path = expected_attempt / "raw_run.mat"
    run_start_path = expected_attempt / "run_start.mat"
    assert Path(record["run_status_path"]).resolve() == status_path.resolve()
    assert Path(record["raw_path"]).resolve() == raw_path.resolve()
    status = verify_status_file(status_path, record["run_status_sha256"], scene_id=scene_id,
                                raw_path=raw_path, raw_sha=record["raw_sha256"], coordinate_mask=[1, 1, 0],
                                require_event_counts=True,
                                required_markers=("raw", "run_start", "attempt_started_marker", "first_plant_step_marker"))
    assert status["schema"] == f"C5_AXIS_COORDINATE_DEV72_RUN_STATUS_{BATCH_VERSION.upper()}"
    assert record["status"] == status["status"] == "RUN_COMPLETE_RAW_PENDING_AUDIT"
    assert record["physical_B_source_sha256"].lower() == row["B_source"]["sha256"].lower()
    assert record["scoring_B72_raw_sha256"].lower() == row["B72_scoring"]["raw_sha256"].lower()
    assert record["scoring_B72_status_sha256"].lower() == row["B72_scoring"]["run_status_sha256"].lower()
    c3_status = verify_status_file(row["C3_reference"]["run_status_path"], row["C3_reference"]["run_status_sha256"],
                                   scene_id=scene_id, raw_path=row["C3_reference"]["raw_path"],
                                   raw_sha=row["C3_reference"]["raw_sha256"])
    assert c3_status["schema"] == "C3_DELAYED_PREDICTION_DEV72_RUN_STATUS_V1"
    for key in ("raw_path", "raw_sha256", "run_start_path", "run_start_sha256",
                "first_plant_step_marker_path", "first_plant_step_marker_sha256"):
        assert c3_status[key] == row["C3_reference"][key], (scene_id, key)
    for path_key, sha_key in (("raw_path", "raw_sha256"), ("run_start_path", "run_start_sha256"),
                              ("attempt_started_marker_path", "attempt_started_marker_sha256"),
                              ("first_plant_step_marker_path", "first_plant_step_marker_sha256")):
        ref_path = Path(row["C3_reference"][path_key])
        assert ref_path.is_file() and sha(ref_path) == row["C3_reference"][sha_key].lower()
    b72_status = verify_status_file(row["B72_scoring"]["run_status_path"], row["B72_scoring"]["run_status_sha256"],
                                   scene_id=scene_id, raw_path=row["B72_scoring"]["raw_path"],
                                   raw_sha=row["B72_scoring"]["raw_sha256"])
    assert b72_status["schema"] in ("B_TRACEABLE_C3CORE_RUN_STATUS_V2",
                                     "B_TRACEABLE_C3CORE_DEV72_RUN_STATUS_V3")
    assert sha(raw_path) == record["raw_sha256"].lower()
    assert status["candidate"] == contract["candidate"] and status["coordinate_mask"] == [1, 1, 0]
    assert status["plant_invocation_entered"] and status["plant_start_confirmed"]
    assert status["input_lock_sha256"].lower() == sha(LOCK)
    assert status["release_sha256"].lower() == sha(RELEASE)
    assert status["run_contract_sha256"].lower() == sha(CONTRACT)
    assert status["prepare_result_sha256"].lower() == sha(PREP)
    assert status["cfg_opts_snapshot_sha256"].lower() == sha(SNAPSHOT)
    assert status["parameter_or_seed_search"] is False
    assert status["physical_B_source_path"] == row["B_source"]["path"]
    assert status["physical_B_source_sha256"].lower() == row["B_source"]["sha256"].lower()
    assert status["scoring_B72_raw_path"] == row["B72_scoring"]["raw_path"]
    assert status["scoring_B72_raw_sha256"].lower() == row["B72_scoring"]["raw_sha256"].lower()
    assert status["scoring_B72_status_path"] == row["B72_scoring"]["run_status_path"]
    assert status["scoring_B72_status_sha256"].lower() == row["B72_scoring"]["run_status_sha256"].lower()
    assert status["C3_raw_path"] == row["C3_reference"]["raw_path"]
    assert status["C3_raw_sha256"].lower() == row["C3_reference"]["raw_sha256"].lower()
    assert Path(status["run_start_path"]).resolve() == run_start_path.resolve()
    assert sha(run_start_path) == status["run_start_sha256"].lower()
    start = matlab_section_safe(run_start_path, "runStart", decoder)
    assert matlab_text(start["schema"]) == f"C5_AXIS_COORDINATE_DEV72_RUN_START_{BATCH_VERSION.upper()}"
    assert sha(SNAPSHOT) == matlab_text(start["cfg_opts_snapshot_sha256"])
    assert matlab_text(start["scene_id"]) == scene_id and matlab_text(start["source_scene_id"]) == status["source_scene_id"]
    assert matlab_flat(start["coordinate_mask"]) == [1.0, 1.0, 0.0]
    assert matlab_text(start["initial_W0_sha256"]) == contract["model"]["W0_sha256"]
    assert matlab_text(start["input_lock_sha256"]).lower() == sha(LOCK)
    assert matlab_text(start["release_sha256"]).lower() == sha(RELEASE)
    assert matlab_text(start["run_contract_sha256"]).lower() == sha(CONTRACT)
    assert matlab_text(start["prepare_result_sha256"]).lower() == sha(PREP)
    assert matlab_text(start["B_physical_source_path"]) == row["B_source"]["path"]
    assert matlab_text(start["B_physical_source_sha256"]).lower() == row["B_source"]["sha256"].lower()
    assert matlab_text(start["B72_raw_path"]) == row["B72_scoring"]["raw_path"]
    assert matlab_text(start["B72_raw_sha256"]).lower() == row["B72_scoring"]["raw_sha256"].lower()
    assert matlab_text(start["B72_run_status_path"]) == row["B72_scoring"]["run_status_path"]
    assert matlab_text(start["B72_run_status_sha256"]).lower() == row["B72_scoring"]["run_status_sha256"].lower()
    assert matlab_text(start["C3_raw_path"]) == row["C3_reference"]["raw_path"]
    assert matlab_text(start["C3_raw_sha256"]).lower() == row["C3_reference"]["raw_sha256"].lower()
    assert Path(matlab_text(start["runner_path"])).resolve() == RUNNER.resolve()
    assert matlab_text(start["runner_sha256"]).lower() == sha(RUNNER)
    assert matlab_scalar(start["plant_calls_before_invocation"]) == 0
    assert matlab_scalar(start["training_steps"]) == matlab_scalar(start["optimizer_steps"]) == 0
    assert matlab_scalar(start["TEST_accessed"]) in (0, False)
    leaves = {"cfg": equal_tree(snapshot["cfg"], start["cfg"], decoder),
              "opts": equal_tree(snapshot["opts"], start["opts"], decoder, ignore_marker=True)}
    assert leaves == {"cfg": 120, "opts": 43}, leaves

    active = lock["active_source_inventory"]
    expected_paths = [x["path"] for x in active]
    expected_shas = [x["sha256"].lower() for x in active]
    got_paths = [str(matlab_text(x)) for x in matlab_flat(start["source_paths"])]
    got_shas = [str(matlab_text(x)).lower() for x in matlab_flat(start["source_sha256"])]
    snapshot_source = snapshot["sourceIdentity"]
    snapshot_paths = [str(matlab_text(x)) for x in matlab_flat(snapshot_source["active_paths"])]
    snapshot_shas = [str(matlab_text(x)).lower() for x in matlab_flat(snapshot_source["active_sha256"])]
    assert len(active) == len(got_paths) == len(got_shas) == len(snapshot_paths) == len(snapshot_shas) == 32
    assert [Path(x).resolve() for x in got_paths] == [Path(x).resolve() for x in expected_paths]
    assert got_shas == expected_shas and snapshot_paths == expected_paths and snapshot_shas == expected_shas
    assert equal_tree(snapshot["modelIdentity"], start["model_identity"], decoder) == 6

    scene_ids = [str(matlab_text(x)) for x in matlab_flat(snapshot["sceneIdentity"]["scene_id"])]
    ix = scene_ids.index(scene_id)
    expected_identity = scene_identity_row(snapshot["sceneIdentity"], ix)
    run_scene = start["scene_identity"]
    assert matlab_text(run_scene["scene_id"]) == scene_id and matlab_text(run_scene["source_scene_id"]) == status["source_scene_id"]
    compare_scene_identity(run_scene["identity"], expected_identity, decoder)
    assert matlab_text(run_scene["external_identity_sha256"]) == row["external_identity_sha256"]

    run_identity = matlab_section_safe(raw_path, "runIdentity", decoder)
    required_identity = {"schema", "scene_id", "candidate", "coordinate_mask", "release_sha256",
                         "input_lock_sha256", "prepare_result_sha256", "model_identity",
                         "initial_W0_sha256", "external_identity_sha256", "training_steps",
                         "optimizer_steps", "TEST_accessed"}
    assert set(run_identity) == required_identity, sorted(run_identity)
    assert matlab_text(run_identity["schema"]) == f"C5_AXIS_COORDINATE_DEV72_RUN_IDENTITY_{BATCH_VERSION.upper()}"
    assert matlab_text(run_identity["scene_id"]) == scene_id
    assert matlab_text(run_identity["candidate"]) == contract["candidate"]
    assert matlab_text(run_identity["release_sha256"]).lower() == sha(RELEASE)
    assert matlab_text(run_identity["input_lock_sha256"]).lower() == sha(LOCK)
    assert matlab_text(run_identity["prepare_result_sha256"]).lower() == sha(PREP)
    assert matlab_text(run_identity["initial_W0_sha256"]).lower() == contract["model"]["W0_sha256"].lower()
    assert matlab_text(run_identity["external_identity_sha256"]) == row["external_identity_sha256"]
    assert matlab_scalar(run_identity["training_steps"]) == 0 and matlab_scalar(run_identity["optimizer_steps"]) == 0
    assert matlab_scalar(run_identity["TEST_accessed"]) in (0, False)
    assert matlab_flat(run_identity["coordinate_mask"]) == [1.0, 1.0, 0.0]
    assert equal_tree(snapshot["modelIdentity"], run_identity["model_identity"], decoder) == 6
    raw_score = scorer.score(dict(scene_id=scene_id, method="C5_M110", path=str(raw_path), sha256=record["raw_sha256"]))
    assert raw_score["external_identity_sha256"] == row["external_identity_sha256"]
    events = event_audit(raw_path, start["cfg"], expected_w0=snapshot["W0"],
                         expected_w0_sha256=contract["model"]["W0_sha256"])
    return {"status": "PASS_C5_RAW_ALL_EVENTS", "scene_id": scene_id,
            "checks": events["checks"], "event_count": events["event_count"],
            "leaf_counts": leaves, "source_count": len(active),
            "C5_metrics": raw_score, "run_status_sha256": sha(status_path),
            "raw_sha256": sha(raw_path), "run_start_sha256": sha(run_start_path)}


def checked_reused_metrics(scene_id, row, summary_audit, scorer_sha):
    assert summary_audit["status"] == "PASS_C5_RAW_ALL_EVENTS" and summary_audit["event_count"] == 1968
    assert summary_audit["B_identity_status"] == "PARENT_AUDITED_NEW_TRACEABLE_B72"
    assert summary_audit["TEST_accessed"] is False and summary_audit["new_Plant_in_audit"] == 0
    assert max(summary_audit["checks"].values()) < 1e-10
    assert summary_audit["raw_sha256"].lower() == row["C5_reuse"]["raw_sha256"].lower()
    assert summary_audit["run_status_sha256"].lower() == row["C5_reuse"]["run_status_sha256"].lower()
    metrics = {}
    for name, obj in (("C5_metrics", row["C5_reuse"]), ("C3_metrics", row["C3_reference"]),
                      ("B_metrics", row["B72_scoring"])):
        m = summary_audit[name]
        assert m["scene_id"] == scene_id and Path(m["path"]).resolve() == Path(obj["raw_path"]).resolve()
        assert m["sha256"].lower() == obj["raw_sha256"].lower()
        assert m["external_identity_sha256"] == summary_audit["C5_metrics"]["external_identity_sha256"]
        metrics[name] = m
    return {"status": "PASS_REUSED_C5_SCREEN_AUDIT", "scene_id": scene_id,
            "event_count": 1968, "checks": summary_audit["checks"], **metrics,
            "Q_C5_minus_B_m": summary_audit["Q_C5_minus_B_m"],
            "Q_C5_minus_C3_m": summary_audit["Q_C5_minus_C3_m"],
            "Z_C5_minus_C3_m": summary_audit["Z_C5_minus_C3_m"],
            "legacy_event_audit_sha256": OLD_AUDIT_SHA, "metric_scorer_sha256": scorer_sha}


def group_summary(rows):
    assert rows
    keys = ["Q_0_20_m", "Q_0_5_m", "Q_5_20_m", "rmse_x_0_20_m", "rmse_y_0_20_m", "rmse_z_0_20_m",
            "rmse_x_0_5_m", "rmse_y_0_5_m", "rmse_z_0_5_m", "rmse_x_5_20_m", "rmse_y_5_20_m",
            "rmse_z_5_20_m", "peak_m", "p95_m", "motor_saturated_fraction", "generalized_clipped_fraction"]
    deltas = [r["C5_metrics"]["Q_0_20_m"] - r["B_metrics"]["Q_0_20_m"] for r in rows]
    out = {"scene_count": len(rows),
           "wins_vs_B": sum(delta < -1e-12 for delta in deltas),
           "losses_vs_B": sum(delta > 1e-12 for delta in deltas),
           "ties_vs_B_within_1e_12_m": sum(abs(delta) <= 1e-12 for delta in deltas),
           "wins_improved_gt_1um": sum(-delta > 1e-6 for delta in deltas),
           "wins_improved_gt_10um": sum(-delta > 10e-6 for delta in deltas)}
    for method_key, metric_key in (("C5", "C5_metrics"), ("C3", "C3_metrics"), ("B", "B_metrics")):
        out[method_key] = {k: float(np.mean([r[metric_key][k] for r in rows])) for k in keys}
    out["mean_Q_C5_minus_B_m"] = out["C5"]["Q_0_20_m"] - out["B"]["Q_0_20_m"]
    out["mean_Q_C5_minus_C3_m"] = out["C5"]["Q_0_20_m"] - out["C3"]["Q_0_20_m"]
    return out


def aggregate(rows):
    def scene_parts(sid):
        match = re.fullmatch(r"DL1018_(DEV|VAL)_T([1-3])_C\d\d_W(\d\d)", sid)
        assert match, sid
        return match.group(1), int(match.group(2)), int(match.group(3))
    parsed = {r["scene_id"]: scene_parts(r["scene_id"]) for r in rows}
    groups = {"ALL72": rows,
              "HF_W09_W14": [r for r in rows if 9 <= parsed[r["scene_id"]][2] <= 14],
              "W15": [r for r in rows if parsed[r["scene_id"]][2] == 15],
              "DEV": [r for r in rows if parsed[r["scene_id"]][0] == "DEV"],
              "VAL": [r for r in rows if parsed[r["scene_id"]][0] == "VAL"]}
    for t in range(1, 4):
        groups[f"T{t}"] = [r for r in rows if parsed[r["scene_id"]][1] == t]
    for w in range(16):
        groups[f"W{w:02d}"] = [r for r in rows if parsed[r["scene_id"]][2] == w]
    result = {k: group_summary(v) for k, v in groups.items()}
    assert result["ALL72"]["scene_count"] == 72 and result["HF_W09_W14"]["scene_count"] == 28
    return result


def final_batch_evidence(lock, contract, binding):
    runner_preflight_path = EXP / f"C5_DEV72_RUNNER_PREFLIGHT_RESULT_{BATCH_VERSION}.json"
    assert all(p.is_file() for p in (PREP, SNAPSHOT, RELEASE, BATCH, BODY, OS_EXIT,
                                     NOPLANT_OS_EXIT, runner_preflight_path))
    prep, release, batch, body, os_exit = map(load, (PREP, RELEASE, BATCH, BODY, OS_EXIT))
    runner_preflight = load(runner_preflight_path)
    noplant_os_exit = load(NOPLANT_OS_EXIT)
    assert prep["schema"] == f"C5_AXIS_COORDINATE_DEV72_PREPARE_RESULT_{BATCH_VERSION.upper()}"
    assert prep["input_lock_sha256"].lower() == sha(LOCK)
    assert prep["run_contract_sha256"].lower() == sha(CONTRACT)
    assert prep["source_binding_sha256"].lower() == sha(BINDING)
    assert prep["snapshot_sha256"].lower() == sha(SNAPSHOT)
    assert prep["status"] == f"PREPARED_C5_M110_DEV72_NO_PLANT_WAIT_PARENT_RELEASE_{BATCH_VERSION.upper()}"
    assert release["schema"] == f"C5_AXIS_COORDINATE_DEV72_PARENT_RELEASE_{BATCH_VERSION.upper()}"
    assert release["state"] == f"APPROVED_C5_M110_DEV72_{BATCH_VERSION.upper()}" and release["plant_authorized"] is True
    assert release["max_new_Plant"] == 60 and release["candidate"] == contract["candidate"]
    assert release["input_lock_sha256"].lower() == sha(LOCK)
    assert release["run_contract_sha256"].lower() == sha(CONTRACT)
    assert release["prepare_result_sha256"].lower() == sha(PREP)
    assert release["prepared_snapshot_sha256"].lower() == sha(SNAPSHOT)
    assert release["source_binding_sha256"].lower() == sha(BINDING)
    assert release["runner_sha256"].lower() == sha(RUNNER)
    assert release["launcher_sha256"].lower() == sha(PLANT_LAUNCHER)
    assert release["parent_release_contract_sha256"].lower() == sha(RELEASE_CONTRACT)
    assert release["runner_preflight_result_sha256"].lower() == sha(runner_preflight_path)
    assert release["scene_ids_new_60"] == lock["scene_ids_new_60"]
    assert runner_preflight["schema"] == f"C5_AXIS_COORDINATE_DEV72_RUNNER_PREFLIGHT_RESULT_{BATCH_VERSION.upper()}"
    assert runner_preflight["status"] == f"PREFLIGHT_PASS_WAIT_PARENT_RELEASE_{BATCH_VERSION.upper()}"
    assert runner_preflight["process_scope"] == "PREFLIGHT_ONLY_NO_PLANT"
    assert runner_preflight["release_presence_and_release_contract_validation_skipped"] is True
    assert runner_preflight["plant_calls"] == runner_preflight["training_steps"] == runner_preflight["optimizer_steps"] == 0
    assert runner_preflight["TEST_accessed"] is False and runner_preflight["scene_count"] == 72
    assert runner_preflight["new_scene_count"] == 60 and runner_preflight["reuse_scene_count"] == 12
    assert runner_preflight["runner_sha256"].lower() == sha(RUNNER)
    assert runner_preflight["input_lock_sha256"].lower() == sha(LOCK)
    assert runner_preflight["run_contract_sha256"].lower() == sha(CONTRACT)
    assert runner_preflight["prepare_result_sha256"].lower() == sha(PREP)
    assert runner_preflight["snapshot_sha256"].lower() == sha(SNAPSHOT)
    assert runner_preflight["source_binding_sha256"].lower() == sha(BINDING)
    assert noplant_os_exit["schema"] == f"C5_AXIS_COORDINATE_DEV72_NOPLANT_OS_EXIT_{BATCH_VERSION.upper()}"
    assert noplant_os_exit["matlab_os_exit_code"] == 0 and noplant_os_exit["matlab_called_once"] is True
    assert noplant_os_exit["release_check_skipped"] is True and noplant_os_exit["plant_authorized"] is False
    assert noplant_os_exit["plant_calls"] == 0
    assert noplant_os_exit["input_lock_sha256"].lower() == sha(LOCK)
    assert noplant_os_exit["prepare_entry_sha256"].lower() == sha(EXP / f"prepare_c5_dev72_{BATCH_VERSION}.m")
    assert noplant_os_exit["runner_sha256"].lower() == sha(RUNNER)
    assert noplant_os_exit["source_binding_sha256"].lower() == sha(BINDING)
    assert noplant_os_exit["prepare_result_status"] == prep["status"]
    assert noplant_os_exit["prepare_result_sha256"].lower() == sha(PREP)
    assert noplant_os_exit["snapshot_sha256"].lower() == sha(SNAPSHOT)
    assert noplant_os_exit["runner_preflight_status"] == runner_preflight["status"]
    assert noplant_os_exit["runner_preflight_sha256"].lower() == sha(runner_preflight_path)
    assert Path(noplant_os_exit["command_file"]).resolve() == NOPLANT_LAUNCHER.resolve()
    assert noplant_os_exit["command_sha256"].lower() == sha(NOPLANT_LAUNCHER)
    assert Path(noplant_os_exit["stdout_path"]).is_file() and Path(noplant_os_exit["stderr_path"]).is_file()
    assert batch["schema"] == f"C5_AXIS_COORDINATE_DEV72_BATCH_STATUS_{BATCH_VERSION.upper()}"
    assert batch["status"] == "COMPLETE_RAW_PENDING_PARENT_AUDIT" and batch["completed_scenes"] == 60
    assert batch["plant_calls"] == 60 and batch["training_steps"] == batch["optimizer_steps"] == 0
    assert batch["TEST_accessed"] is False and batch["scene_ids_new_60"] == lock["scene_ids_new_60"]
    assert len(batch["records"]) == 60 and [r["scene_id"] for r in batch["records"]] == lock["scene_ids_new_60"]
    assert body["schema"] == f"C5_AXIS_COORDINATE_DEV72_BODY_COMPLETE_{BATCH_VERSION.upper()}"
    assert body["status"] == "COMPLETE_RAW_PENDING_PARENT_AUDIT" and body["completed_scene_count"] == 60
    assert body["plant_calls"] == 60 and body["scene_ids_new_60"] == lock["scene_ids_new_60"]
    assert body["source_binding_sha256"].lower() == sha(BINDING)
    assert body["release_sha256"].lower() == sha(RELEASE)
    assert body["training_steps"] == body["optimizer_steps"] == 0 and body["TEST_accessed"] is False
    assert len(body["records"]) == 60 and [r["scene_id"] for r in body["records"]] == lock["scene_ids_new_60"]
    record_timestamp_differences = compare_batch_body_records(batch["records"], body["records"])
    assert batch["release_sha256"].lower() == sha(RELEASE)
    assert body["shared_matlab_os_exit_code"] == 0
    assert os_exit["schema"] == f"C5_AXIS_COORDINATE_DEV72_MATLAB_OS_EXIT_{BATCH_VERSION.upper()}"
    assert os_exit["matlab_os_exit_code"] == 0 and os_exit["matlab_process_count"] == 1
    assert os_exit["preflight_matlab_process_count"] == 0 and os_exit["plant_calls"] == 60
    assert os_exit["batch_status"] == body["status"] and os_exit["body_status"] == body["status"]
    assert os_exit["body_sha256_after_os_return"].lower() == sha(BODY)
    assert os_exit["release_sha256"].lower() == sha(RELEASE)
    command_path = REPORT / f"C5_DEV72_COMMAND_{BATCH_VERSION}.txt"
    assert command_path.is_file() and os_exit["command_path"] == str(command_path)
    assert sha(command_path) == os_exit["command_sha256"].lower()
    expected_invocation = f"& '{PLANT_LAUNCHER.resolve()}'"
    assert command_path.read_text(encoding="utf-8-sig").strip() == expected_invocation
    assert os_exit["outer_invocation"] == expected_invocation
    assert Path(os_exit["stdout_path"]).is_file() and sha(os_exit["stdout_path"]) == os_exit["stdout_sha256"].lower()
    assert Path(os_exit["stderr_path"]).is_file() and sha(os_exit["stderr_path"]) == os_exit["stderr_sha256"].lower()
    release_contract = load(RELEASE_CONTRACT)
    assert release_contract["schema"] == f"C5_AXIS_COORDINATE_DEV72_PARENT_RELEASE_CONTRACT_{BATCH_VERSION.upper()}"
    assert "runner_preflight_result_sha256" in release_contract["required_fields"]
    order_ref = lock["upstream_refs"]["c3_input_lock"]
    assert release_contract["exact_scene_order_source"]["field"] == (
        "scene_ids_all_72 filtered to exclude scene_ids_reuse_12 while preserving order")
    assert Path(release_contract["exact_scene_order_source"]["path"]).resolve() == Path(order_ref["path"]).resolve()
    assert release_contract["exact_scene_order_source"]["sha256"].lower() == order_ref["sha256"].lower()
    for ref in lock["source_files"].values():
        for item in ref if isinstance(ref, list) else [ref]:
            if isinstance(item, dict) and "path" in item:
                assert Path(item["path"]).is_file() and sha(item["path"]) == item["sha256"].lower()
    for item in lock["active_source_inventory"]:
        assert Path(item["path"]).is_file() and sha(item["path"]) == item["sha256"].lower()
    for name, ref in lock["upstream_refs"].items():
        for item in ref if isinstance(ref, list) else [ref]:
            if isinstance(item, dict) and "path" in item:
                assert Path(item["path"]).is_file() and sha(item["path"]) == item["sha256"].lower(), name
    return {"prep": prep, "release": release, "runner_preflight": runner_preflight,
            "noplant_os_exit": noplant_os_exit,
            "batch": batch, "body": body, "os_exit": os_exit,
            "batch_body_created_utc_raw_string_differences": record_timestamp_differences}


def full_audit(output: Path):
    assert not output.exists(), "Preserve prior parent-audit evidence; do not overwrite."
    assert sha(OLD_AUDIT) == OLD_AUDIT_SHA
    assert sha(SCORER_PATH) == SCORER_SHA and sha(DECODER_PATH) == DECODER_SHA
    lock, contract, binding = load(LOCK), load(CONTRACT), load(BINDING)
    assert lock["schema"] == f"C5_AXIS_COORDINATE_DEV72_INPUT_LOCK_{BATCH_VERSION.upper()}"
    assert lock["coordinate_mask"] == [1, 1, 0] and lock["plant_authorized_by_this_lock"] is False
    assert len(lock["scene_ids_all_72"]) == 72 and len(lock["scene_ids_new_60"]) == 60 and len(lock["scene_ids_reuse_12"]) == 12
    assert lock["scene_ids_new_60"] == [s for s in lock["scene_ids_all_72"] if s not in set(lock["scene_ids_reuse_12"])]
    assert lock["scene_ids_reuse_12"] == [s for s in lock["scene_ids_all_72"] if s in set(lock["scene_ids_reuse_12"])]
    assert contract["scene_ids_all_72"] == lock["scene_ids_all_72"]
    assert contract["scene_ids_new_60"] == lock["scene_ids_new_60"] and contract["scene_ids_reuse_12"] == lock["scene_ids_reuse_12"]
    assert binding["input_lock_sha256"].lower() == sha(LOCK) and binding["run_contract_sha256"].lower() == sha(CONTRACT)
    evidence = final_batch_evidence(lock, contract, binding)
    scorer = module_at(SCORER_PATH, "c5_dev72_metric_scorer")
    decoder = module_at(DECODER_PATH, "c5_dev72_mat_decoder")
    snapshot = {k: matlab_section_safe(SNAPSHOT, k, decoder) for k in
                ("cfg", "opts", "W0", "modelIdentity", "sceneIdentity", "sourceIdentity")}
    assert len(lock["active_source_inventory"]) == 32 and len(snapshot["sourceIdentity"]["active_paths"]) == 32
    assert len(matlab_flat(snapshot["sceneIdentity"]["scene_id"])) == 72
    old_summary = load(OLD_SCREEN)
    assert old_summary["status"] == "C5_SCREEN_PASS" and len(old_summary["audits"]) == 12
    assert all(old_summary["gates"].values())
    for ref in old_summary["refs"]:
        assert Path(ref["path"]).is_file() and sha(ref["path"]) == ref["sha256"].lower()
    audit_by_scene = {x["scene_id"]: x for x in old_summary["audits"]}
    rows_by_scene = {x["scene_id"]: x for x in lock["scenes"]}
    assert list(rows_by_scene) == lock["scene_ids_all_72"]
    new_records = {x["scene_id"]: x for x in evidence["batch"]["records"]}
    result_rows, event_rows = [], []
    for sid in lock["scene_ids_all_72"]:
        row = rows_by_scene[sid]
        if row["C5_reuse"]["reused"]:
            assert sid in audit_by_scene
            audited = checked_reused_metrics(sid, row, audit_by_scene[sid], SCORER_SHA)
            result_rows.append(audited)
            event_rows.append({"scene_id": sid, "status": audited["status"], "event_count": 1968,
                               "checks": audited["checks"], "source": "C5_SCREEN_PARENT_AUDIT_REUSED"})
        else:
            assert sid in new_records and row["candidate_action"] == "PROPOSE_NEW_C5_M110_RUN"
            c5_audit = verify_new_run(sid, row, new_records[sid], lock, contract, binding,
                                      evidence["release"], snapshot, decoder, scorer)
            c3_item = dict(scene_id=sid, method="C3", path=row["C3_reference"]["raw_path"],
                           sha256=row["C3_reference"]["raw_sha256"])
            b_item = dict(scene_id=sid, method="B_TRACEABLE", path=row["B72_scoring"]["raw_path"],
                          sha256=row["B72_scoring"]["raw_sha256"])
            c3_metrics, b_metrics = checked_metric(c3_item, scorer), checked_metric(b_item, scorer)
            assert c5_audit["C5_metrics"]["external_identity_sha256"] == c3_metrics["external_identity_sha256"]
            assert c5_audit["C5_metrics"]["external_identity_sha256"] == b_metrics["external_identity_sha256"]
            result_rows.append({"status": "PASS_C5_RAW_ALL_EVENTS", "scene_id": sid,
                                "C5_metrics": c5_audit["C5_metrics"], "C3_metrics": c3_metrics,
                                "B_metrics": b_metrics, "Q_C5_minus_B_m": c5_audit["C5_metrics"]["Q_0_20_m"]-b_metrics["Q_0_20_m"],
                                "Q_C5_minus_C3_m": c5_audit["C5_metrics"]["Q_0_20_m"]-c3_metrics["Q_0_20_m"],
                                "Z_C5_minus_C3_m": c5_audit["C5_metrics"]["rmse_z_0_20_m"]-c3_metrics["rmse_z_0_20_m"],
                                "event_check_sha256": sha(Path(__file__)), "run_status_sha256": c5_audit["run_status_sha256"],
                                "raw_sha256": c5_audit["raw_sha256"], "run_start_sha256": c5_audit["run_start_sha256"]})
            event_rows.append({"scene_id": sid, "status": c5_audit["status"], "event_count": c5_audit["event_count"],
                               "checks": c5_audit["checks"], "source": "DEV72_NEW_RAW_PARENT_RECOMPUTATION"})
    assert len(result_rows) == 72 and [x["scene_id"] for x in result_rows] == lock["scene_ids_all_72"]
    for row in result_rows:
        delta = row["C5_metrics"]["Q_0_20_m"] - row["B_metrics"]["Q_0_20_m"]
        assert abs(delta - row["Q_C5_minus_B_m"]) <= 1e-12, (row["scene_id"], delta, row["Q_C5_minus_B_m"])
        row["Q_C5_minus_B_m"] = delta
        row["comparison_vs_B"] = "WIN" if delta < -1e-12 else ("LOSS" if delta > 1e-12 else "TIE")
    groups = aggregate(result_rows)
    all72, hf, w15 = groups["ALL72"], groups["HF_W09_W14"], groups["W15"]
    performance = {"wins_vs_B_at_least_62": all72["wins_vs_B"] >= 62,
                   "all72_mean_Q_strictly_below_B": all72["C5"]["Q_0_20_m"] < all72["B"]["Q_0_20_m"],
                   "HF_W09_W14_mean_Q_not_above_B": hf["C5"]["Q_0_20_m"] <= hf["B"]["Q_0_20_m"],
                   "W15_mean_Q_not_above_B": w15["C5"]["Q_0_20_m"] <= w15["B"]["Q_0_20_m"]}
    losing = [r["scene_id"] for r in result_rows if r["comparison_vs_B"] == "LOSS"]
    ties = [r["scene_id"] for r in result_rows if r["comparison_vs_B"] == "TIE"]
    status = "PASS_C5_DEV72_RAW_ALL_EVENTS_PARENT_AUDIT" if all(performance.values()) else "REJECT_C5_FIXED_CANDIDATE"
    result = {"schema": "C5_AXIS_COORDINATE_DEV72_RAW_PARENT_AUDIT_V1", "status": status,
              "scope": "DEV_ONLY_NO_TEST", "input_lock_sha256": sha(LOCK), "run_contract_sha256": sha(CONTRACT),
              "source_binding_sha256": sha(BINDING), "release_sha256": sha(RELEASE),
              "snapshot_sha256": sha(SNAPSHOT), "batch_sha256": sha(BATCH), "body_sha256": sha(BODY),
              "matlab_os_exit_sha256": sha(OS_EXIT), "matlab_os_exit_code": 0,
              "batch_body_created_utc_raw_string_differences": evidence["batch_body_created_utc_raw_string_differences"],
              "legacy_event_audit_source_sha256": OLD_AUDIT_SHA, "new_event_audit_script_sha256": sha(Path(__file__)),
              "metric_scorer_sha256": SCORER_SHA, "mat_decoder_sha256": DECODER_SHA,
              "hdf5_cell_safe_adapter_sha256": sha(Path(__file__)),
              "hdf5_cell_safe_adapter_base_decoder_sha256": DECODER_SHA,
              "plant_calls_in_audit": 0, "TEST_accessed": False, "training_steps": 0, "optimizer_steps": 0,
              "timing_qualification": "NONISOLATED_NOT_FORMAL", "scene_count": 72,
              "new_scenes_event_checked": 60, "reused_scenes_event_audit_refs": 12,
              "event_check_rows": event_rows, "rows": result_rows, "groups": groups,
              "losing_scenes_vs_B": losing, "tie_scenes_vs_B": ties,
              "performance_gates": performance,
              "comparison_tie_tolerance_m": 1e-12,
              "all72_Q_C5_minus_B_m": all72["mean_Q_C5_minus_B_m"],
              "wins_vs_B": all72["wins_vs_B"], "wins_improved_gt_1um": all72["wins_improved_gt_1um"],
              "wins_improved_gt_10um": all72["wins_improved_gt_10um"],
              "losses_vs_B": all72["losses_vs_B"], "ties_vs_B_within_1e_12_m": all72["ties_vs_B_within_1e_12_m"],
              "old12_parent_summary_sha256": sha(OLD_SCREEN),
              "data_sources": {"C5_new": f"{ATTEMPT_DIRNAME} per-scene raw/status", "C5_reuse": str(OLD_SCREEN),
                               "C3": "lock.scenes[].C3_reference", "B": "lock.scenes[].B72_scoring"}}
    csv_path = REVIEW / f"C5_DEV72_RAW_METRICS_{BATCH_VERSION}.csv"
    losses_csv_path = REVIEW / f"C5_DEV72_ALL_LOSSES_{BATCH_VERSION}.csv"
    assert not output.exists() and not csv_path.exists() and not losses_csv_path.exists(), \
        "Preserve prior parent-audit evidence; do not overwrite."
    result["metrics_csv"] = str(csv_path)
    result["all_losses_csv"] = str(losses_csv_path)
    result["loss_scene_count"] = len(losing)
    fields = ["scene_id", "comparison_vs_B", "Q_C5_0_20_m", "Q_C3_0_20_m", "Q_B_0_20_m", "Q_C5_minus_B_m",
              "Q_C5_0_5_m", "Q_C5_5_20_m", "Q_B_0_5_m", "Q_B_5_20_m",
              "C5_x_0_20_m", "C5_y_0_20_m", "C5_z_0_20_m", "C3_x_0_20_m", "C3_y_0_20_m", "C3_z_0_20_m",
              "B_x_0_20_m", "B_y_0_20_m", "B_z_0_20_m", "C5_peak_m", "C5_p95_m", "B_peak_m", "B_p95_m",
              "C5_motor_saturated_fraction", "C5_generalized_clipped_fraction", "C5_controller_mean_s", "C5_controller_p95_s"]
    with csv_path.open("x", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for r in result_rows:
            c5, c3, b = r["C5_metrics"], r["C3_metrics"], r["B_metrics"]
            w.writerow({"scene_id": r["scene_id"], "comparison_vs_B": r["comparison_vs_B"],
                        "Q_C5_0_20_m": c5["Q_0_20_m"], "Q_C3_0_20_m": c3["Q_0_20_m"],
                        "Q_B_0_20_m": b["Q_0_20_m"], "Q_C5_minus_B_m": c5["Q_0_20_m"]-b["Q_0_20_m"],
                        "Q_C5_0_5_m": c5["Q_0_5_m"], "Q_C5_5_20_m": c5["Q_5_20_m"],
                        "Q_B_0_5_m": b["Q_0_5_m"], "Q_B_5_20_m": b["Q_5_20_m"],
                        **{f"C5_{a}_0_20_m": c5[f"rmse_{a}_0_20_m"] for a in "xyz"},
                        **{f"C3_{a}_0_20_m": c3[f"rmse_{a}_0_20_m"] for a in "xyz"},
                        **{f"B_{a}_0_20_m": b[f"rmse_{a}_0_20_m"] for a in "xyz"},
                        "C5_peak_m": c5["peak_m"], "C5_p95_m": c5["p95_m"], "B_peak_m": b["peak_m"], "B_p95_m": b["p95_m"],
                        "C5_motor_saturated_fraction": c5["motor_saturated_fraction"],
                        "C5_generalized_clipped_fraction": c5["generalized_clipped_fraction"],
                        "C5_controller_mean_s": c5["controller_mean_s"], "C5_controller_p95_s": c5["controller_p95_s"]})
    metric_fields = ["method", "path", "sha256", "external_identity_sha256", "Q_0_20_m",
                     "rmse_x_0_20_m", "rmse_y_0_20_m", "rmse_z_0_20_m",
                     "Q_0_5_m", "rmse_x_0_5_m", "rmse_y_0_5_m", "rmse_z_0_5_m",
                     "Q_5_20_m", "rmse_x_5_20_m", "rmse_y_5_20_m", "rmse_z_5_20_m",
                     "peak_m", "p95_m", "motor_saturated_fraction", "generalized_clipped_fraction",
                     "controller_mean_s", "controller_p95_s"]
    loss_fields = ["scene_id", "comparison_vs_B", "Q_C5_minus_B_m"] + [
        f"{method}_{key}" for method in ("C5", "C3", "B") for key in metric_fields]
    with losses_csv_path.open("x", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=loss_fields); w.writeheader()
        for r in result_rows:
            if r["comparison_vs_B"] != "LOSS":
                continue
            record = {"scene_id": r["scene_id"], "comparison_vs_B": r["comparison_vs_B"],
                      "Q_C5_minus_B_m": r["Q_C5_minus_B_m"]}
            for method, key in (("C5", "C5_metrics"), ("C3", "C3_metrics"), ("B", "B_metrics")):
                record.update({f"{method}_{field}": r[key][field] for field in metric_fields})
            w.writerow(record)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": status, "scene_count": 72, "new_event_checked": 60,
                      "reuse_audit_refs": 12, "wins_vs_B": all72["wins_vs_B"],
                      "losses_vs_B": len(losing), "ties_vs_B": len(ties), "json": str(output),
                      "csv": str(csv_path), "losses_csv": str(losses_csv_path)}))


def self_check_reuse(scene_id: str, output: Path):
    assert not output.exists(), "Preserve prior self-check; do not overwrite."
    assert sha(OLD_AUDIT) == OLD_AUDIT_SHA and sha(SCORER_PATH) == SCORER_SHA and sha(DECODER_PATH) == DECODER_SHA
    lock = load(LOCK)
    row = next(x for x in lock["scenes"] if x["scene_id"] == scene_id)
    assert row["C5_reuse"]["reused"] is True
    legacy = module_at(OLD_AUDIT, "legacy_c5_1968_event_audit")
    old_result = legacy.verify(Path(row["C5_reuse"]["run_status_path"]))
    decoder = module_at(DECODER_PATH, "selfcheck_mat_decoder")
    start = decoder.matlab_section(Path(row["C5_reuse"]["run_start_path"]), "runStart")
    new_checks = event_audit(Path(row["C5_reuse"]["raw_path"]), start["cfg"],
                             expected_w0=start["W0"], expected_w0_sha256=matlab_text(start["W0_sha256"]))
    assert new_checks["event_count"] == old_result["event_count"] == 1968
    assert old_result["checks"].keys() == new_checks["checks"].keys()
    max_delta = max(abs(old_result["checks"][k] - new_checks["checks"][k]) for k in new_checks["checks"])
    assert max_delta < 1e-15
    result = {"schema": "C5_DEV72_REUSE_ADAPTATION_SELF_CHECK_V1",
              "status": "PASS_ADAPTATION_SELF_CHECK_ONLY_NOT_DEV72_DECISION",
              "scene_id": scene_id, "event_count": 1968,
              "legacy_event_audit_sha256": OLD_AUDIT_SHA, "new_script_sha256": sha(Path(__file__)),
              "checks_match_legacy_within": 1e-15, "max_check_delta": max_delta, "checks": new_checks["checks"],
              "legacy_metrics": {k: old_result[k] for k in ("C5_metrics", "C3_metrics", "B_metrics")},
              "plant_calls_in_self_check": 0, "TEST_accessed": False,
              "final_dev72_verdict": "NOT_RUN_REQUIRES_BATCH_BODY_AND_NATURAL_OS0"}
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": result["status"], "scene_id": scene_id,
                      "event_count": 1968, "max_check_delta": max_delta, "output": str(output)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-version", choices=("v1", "v2", "v3"), default="v3")
    parser.add_argument("--self-check-reuse", help="Audit one already parent-audited C5 reuse scene; never a DEV72 verdict.")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    configure_version(args.batch_version)
    if args.self_check_reuse:
        self_check_reuse(args.self_check_reuse, args.output)
    else:
        full_audit(args.output)
