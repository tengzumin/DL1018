"""Score the four fixed position-probe exports with frozen canonical-double A1."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
from typing import Any

import h5py
import numpy as np
from scipy.spatial.transform import Rotation

ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT = ROOT / "experiments/attitude_position_context_probe_20261024"
REPORT = ROOT / "reports/attitude_position_context_probe_20261024"
DEPLOYMENT = ROOT / "experiments/attitude_cm18_a1_20261024/deployment_v1/deployment_parameters_v1.json"
MODEL_SOURCE = ROOT / "experiments/attitude_cm18_a1_20261024/model_cm18_v1.py"
RAW_AUDIT = REPORT / "ROOT_ALL4_RAW_AUDIT_v1.json"
TASKBOOK = ROOT / "reports/attitude_cm18_a2_20261024/ROOT_MATCHED_POSITION_PROBE_TASKBOOK_v1_ZH.md"
EVENT_DIR = REPORT / "offline_events_v2"
OUT_DIR = REPORT / "frozen_a1_evaluation_v1"

PINS = {
    "deployment_sha256": "ee00c46af42cbce83a630ae9b03eaf1a86bfc6047910ed68bc4e7b8b020aa6ae",
    "raw_audit_sha256": "9225d2dec302d8fc988c8c47cf93bb87868901961d2bcb193c400dd07d34a440",
    "taskbook_sha256": "69c329de945bced5ba67adc23baa243b50074e0b8625ff86b9f8a78bcaf3b945",
    "exporter_sha256": "ddb1684b1d720d9bee80b3bcda2c95bf855faee1220fc54e9ba764695c5a54a9",
    "checkpoint_sha256": "105585385157da3f1b404ab24606d0717287638e4a1ca710790633cd16d233a4",
    "normalizer_sha256": "7d969a9144ed9cfd519348ba831014981942f93b491539bc2c5732b8401c8592",
    "normalizer_float64_arrays_sha256": "9a150eb8c5fc005ed9b20d890f0f815c8eeaf107add543f3453eebf3c85a48ef",
    "input_manifest_sha256": "a5f7fea9b0918c1449af6fa83929177d3bf7d5e70cb3b71711c40f6338d210a5",
    "dataset_manifest_sha256": "7dd3e1f786f6095ecc2ba56473e5cf0fab6b92cdd42e38a184d6ad1223f36271",
    "model_sources": {
        "experiments/attitude_cm18_a1_20261024/train_cm18_a1_v1.py": "7544a04329bc1e06ff5d7a113a077033a65f0b7c2de8a6f1b25ac54710e62c76",
        "experiments/attitude_cm18_a1_20261024/cache_reader_cm18_v1.py": "a2867cbf516d7ed655a6f50e05b8600ffb7582e0f2164b1ce21d5e647adf2b47",
        "experiments/attitude_cm18_a1_20261024/model_cm18_v1.py": "ad32c4f97bf96c63172547c944d80c45062502f1062b774934e0f7a868720cf6",
        "experiments/attitude_cm18_a1_20261024/torch_model_cm18_v1.py": "bc9fe34fe957cb624438eeccfdfe2ddd38ad40cc9a4e706ce58863c9271d5aa0",
    },
}
FLIGHTS = {
    "T1_B": ("DL1018_TRAIN_T1_C15_W14", "B_POSITION_RBF", 2),
    "T1_C5": ("DL1018_TRAIN_T1_C15_W14", "C5_POSITION_M110", 1),
    "T3_B": ("DL1018_TRAIN_T3_C15_W14", "B_POSITION_RBF", 1),
    "T3_C5": ("DL1018_TRAIN_T3_C15_W14", "C5_POSITION_M110", 1),
}
PHASES = {0: "STATIC", 1: "PRE", 2: "EXTEND", 3: "HOLD", 4: "RETRACT", 5: "RECOVERY"}
AXES = ["roll", "pitch", "yaw"]
EVENT_INDEX = np.arange(1, 2000, dtype=np.int64)
PLANT_INDEX = np.arange(11, 19992, 10, dtype=np.int64)
FEATURE_NAMES = [
    "omega_B_x", "omega_B_y", "omega_B_z", "alpha_BS_x", "alpha_BS_y", "alpha_BS_z",
    "thrust_over_mass", "u1", "u2", "u3", "u4", "z1", "z2", "z3", "z4", "a_x", "a_y", "a_z",
]
JSON_EVENT_ARRAY_FIELDS = ("event_index", "plant_index", "event_time_s", "phase_code", "X18", "target")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def need(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def same_path(left: str | Path, right: str | Path) -> bool:
    a = os.path.normcase(os.path.normpath(str(left))).casefold()
    b = os.path.normcase(os.path.normpath(str(right))).casefold()
    return a == b


def finite_array(value: Any, shape: tuple[int, ...], name: str) -> np.ndarray:
    array = np.asarray(value, dtype=np.float64)
    need(array.shape == shape and np.isfinite(array).all(), f"{name} shape/value mismatch: {array.shape}")
    return array


def json_ready_event(event: dict[str, Any]) -> dict[str, Any]:
    serializable = dict(event)
    for key in JSON_EVENT_ARRAY_FIELDS:
        serializable[key] = serializable[key].tolist()
    return serializable


def load_frozen_model():
    need(sha256(DEPLOYMENT) == PINS["deployment_sha256"], "A1 deployment JSON SHA mismatch")
    need(sha256(MODEL_SOURCE) == PINS["model_sources"]["experiments/attitude_cm18_a1_20261024/model_cm18_v1.py"], "A1 NumPy model source SHA mismatch")
    deployment = read_json(DEPLOYMENT)
    identity = deployment.get("identity", {})
    need(deployment.get("schema") == "CM18_A1_DEPLOYMENT_PARAMETERS_V1", "Unexpected A1 deployment schema")
    need(identity.get("selected_step") == 30000 and identity.get("checkpoint_sha256", "").lower() == PINS["checkpoint_sha256"], "A1 checkpoint/step mismatch")
    need(identity.get("normalizer_sha256", "").lower() == PINS["normalizer_sha256"], "A1 normalizer identity mismatch")
    need(identity.get("normalizer_float64_arrays_sha256", "").lower() == PINS["normalizer_float64_arrays_sha256"], "Canonical float64 normalizer mismatch")
    need(identity.get("source_files") == PINS["model_sources"], "A1 deployment source identity differs from the frozen source set")
    source_hashes = {}
    for relative, expected in PINS["model_sources"].items():
        path = ROOT / relative
        need(path.is_file() and sha256(path) == expected, f"A1 source missing or changed: {relative}")
        source_hashes[relative] = expected
    spec = importlib.util.spec_from_file_location("cm18_a1_frozen_model", MODEL_SOURCE)
    need(spec is not None and spec.loader is not None, "Cannot load pinned A1 NumPy forward")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return deployment, module.forward, source_hashes


def load_audit() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    need(sha256(RAW_AUDIT) == PINS["raw_audit_sha256"], "Root all-four raw audit SHA mismatch")
    audit = read_json(RAW_AUDIT)
    need(audit.get("schema") == "ROOT_MATCHED_ALL4_RAW_AUDIT_V1" and audit.get("status") == "PASS", "All-four raw audit is not PASS")
    rows = audit.get("rows", [])
    by_flight = {row.get("flight_id"): row for row in rows}
    need(set(by_flight) == set(FLIGHTS) and len(rows) == 4, "All-four raw audit flight set mismatch")
    for flight, (_, _, attempt) in FLIGHTS.items():
        row = by_flight[flight]
        need(int(row.get("attempt", -1)) == attempt and int(row.get("attitude_events", -1)) == 1999 and
             int(row.get("transitions", -1)) == 20000 and int(row.get("state_samples", -1)) == 20001 and
             row.get("initial_identity_pass") is True and row.get("exogenous_scene_exact") is True,
             f"{flight}: all-four raw audit identity/event check failed")
    return audit, by_flight


def load_export(flight: str, contract: tuple[str, str, int], audit_row: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    scene, mode, attempt = contract
    path = EVENT_DIR / f"events_{flight}_v2.json"
    need(path.is_file(), f"Missing event export: {path}")
    event_sha = sha256(path)
    exported = read_json(path)
    need(exported.get("schema") == "MATCHED_POSITION_PROBE_EVENT_EXPORT_V2" and exported.get("status") == "PASS", f"{flight}: event export is not PASS")
    identity = exported.get("identity", {})
    need(identity.get("flight_id") == flight and int(identity.get("attempt_id", -1)) == attempt and
         identity.get("scene_id") == scene and identity.get("position_mode") == mode and identity.get("split") == "TRAIN",
         f"{flight}: event export scene/attempt identity mismatch")
    need(identity.get("exporter_source_sha256", "").lower() == PINS["exporter_sha256"] and
         sha256(EXPERIMENT / "export_matched_position_probe_events_v2.m") == PINS["exporter_sha256"],
         "Event exporter source pin mismatch")
    need(identity.get("input_manifest_sha256", "").lower() == PINS["input_manifest_sha256"] and
         identity.get("all816_manifest_sha256", "").lower() == PINS["dataset_manifest_sha256"],
         f"{flight}: source manifests mismatch")

    status_path = Path(identity["status_path"]).resolve()
    expected_status = REPORT / "runs" / flight / f"attempt_{attempt:02d}" / "run_status.json"
    need(same_path(status_path, expected_status) and status_path.is_file(), f"{flight}: status path is not the fixed successful attempt")
    status_sha = sha256(status_path)
    need(status_sha == identity.get("status_sha256", "").lower(), f"{flight}: run_status SHA mismatch")
    status = read_json(status_path)
    need(status.get("schema") == "MATCHED_POSITION_PROBE_RUN_STATUS_V1" and
         status.get("status") == "RUN_COMPLETE_STABLE" and status.get("engine_status") == "STABLE" and
         status.get("flight_id") == flight and int(status.get("attempt_id", -1)) == attempt and
         status.get("scene_id") == scene and status.get("position_mode") == mode and
         int(status.get("transitions", -1)) == 20000 and int(status.get("state_samples", -1)) == 20001 and
         int(status.get("plant_calls", -1)) == 1 and int(status.get("training_steps", -1)) == 0 and
         int(status.get("optimizer_steps", -1)) == 0 and status.get("TEST_accessed") is False and
         status.get("safety_stop_reason") == "", f"{flight}: status is incomplete or unsafe")
    raw_path = Path(identity["raw_path"]).resolve()
    expected_raw = status_path.parent / "raw_run.mat"
    need(same_path(raw_path, expected_raw) and same_path(status.get("raw_path", ""), raw_path), f"{flight}: raw path is not adjacent to the pinned status")
    raw_sha = sha256(raw_path)
    need(raw_sha == status.get("raw_sha256", "").lower() and raw_sha == identity.get("raw_sha256", "").lower(),
         f"{flight}: raw SHA mismatch; refusing to open raw")
    need(int(audit_row["attempt"]) == attempt and int(audit_row["motor_saturated_steps"]) == 0 and
         int(audit_row["generalized_clipped_steps"]) == 0,
         f"{flight}: Root raw audit attempt or saturation/clipping gate failed")

    # Raw HDF5 is opened only after the signed status path and raw SHA pass above.
    with h5py.File(raw_path, "r") as raw:
        need("log" in raw and all(key in raw["log"] for key in ("state", "time", "filtered_attitude_reference", "reference")),
             f"{flight}: raw lacks state/time/reference fields")
        log = raw["log"]
        state = np.asarray(log["state"][()], dtype=np.float64).T
        time = np.asarray(log["time"][()], dtype=np.float64).reshape(-1)
        filt = np.asarray(log["filtered_attitude_reference"][()], dtype=np.float64).T
        pos_ref = np.asarray(log["reference"]["position"][()], dtype=np.float64).T
    need(state.shape == (20001, 12) and time.shape == (20001,) and filt.shape == (20000, 3) and
         pos_ref.shape == (20001, 3) and all(np.isfinite(v).all() for v in (state, time, filt, pos_ref)),
         f"{flight}: raw state/reference shape or finite gate failed")
    need(np.max(np.abs(np.diff(time) - 0.001)) <= 1e-12 and abs(time[0]) <= 1e-12 and abs(time[-1] - 20.0) <= 1e-12,
         f"{flight}: raw timebase mismatch")
    # Same left-transition alignment and SO(3) metric as the existing SCREEN12 metrics audit.
    left_state = state[:-1]
    actual = Rotation.from_euler("ZYX", left_state[:, [8, 7, 6]])
    desired = Rotation.from_euler("ZYX", filt[:, [2, 1, 0]])
    so3_angle = (actual.inv() * desired).magnitude()
    position_error = state[:, :3] - pos_ref
    position_norm = np.linalg.norm(position_error, axis=1)
    tilt = np.arccos(np.clip(np.cos(left_state[:, 6]) * np.cos(left_state[:, 7]), -1.0, 1.0))
    body_rate = np.linalg.norm(left_state[:, 9:12], axis=1)
    time_groups = {
        "ALL_0_20": (time[:-1] >= 0.0) & (time[:-1] < 20.0),
        "PRE_0_5": (time[:-1] >= 0.0) & (time[:-1] < 5.0),
        "POST_5_20": (time[:-1] >= 5.0) & (time[:-1] < 20.0),
    }
    position_time_groups = {
        "ALL_0_20": (time >= 0.0) & (time <= 20.0),
        "PRE_0_5": (time >= 0.0) & (time < 5.0),
        "POST_5_20": (time >= 5.0) & (time <= 20.0),
    }
    tracking = {}
    for name, mask in time_groups.items():
        need(np.any(mask), f"{flight}: empty tracking interval {name}")
        position_mask = position_time_groups[name]
        tracking[name] = {
            "SO3_transition_sample_count": int(np.count_nonzero(mask)),
            "SO3_tracking_RMSE_deg": float(np.rad2deg(np.sqrt(np.mean(so3_angle[mask] ** 2)))),
            "SO3_tracking_peak_deg": float(np.rad2deg(np.max(so3_angle[mask]))),
            "position_state_sample_count": int(np.count_nonzero(position_mask)),
            "position_Q_m": float(np.sqrt(np.mean(np.sum(position_error[position_mask] ** 2, axis=1)))),
            "position_axis_RMSE_m": np.sqrt(np.mean(position_error[position_mask] ** 2, axis=0)).tolist(),
            "position_peak_m": float(np.max(position_norm[position_mask])),
        }
    need(abs(tracking["ALL_0_20"]["position_Q_m"] - float(audit_row["position_Q_m"])) <= 1e-10,
         f"{flight}: recomputed position Q differs from Root raw audit")
    event = {
        "file_path": str(path), "file_sha256": event_sha, "identity": identity,
        "event_index": np.asarray(exported["event_index"], dtype=np.int64).reshape(-1),
        "plant_index": np.asarray(exported["plant_index"], dtype=np.int64).reshape(-1),
        "event_time_s": np.asarray(exported["event_time_s"], dtype=np.float64).reshape(-1),
        "phase": np.asarray(exported["phase"], dtype=object).reshape(-1).tolist(),
        "phase_code": np.asarray(exported["phase_code"], dtype=np.int64).reshape(-1),
        "X18": finite_array(exported["X18"], (1999, 18), f"{flight}.X18"),
        "target": finite_array(exported["target_raw"], (1999, 3), f"{flight}.target_raw"),
    }
    need(np.array_equal(event["event_index"], EVENT_INDEX) and np.array_equal(event["plant_index"], PLANT_INDEX) and
         event["event_time_s"].shape == (1999,) and np.isfinite(event["event_time_s"]).all() and
         event["phase_code"].shape == (1999,) and np.all((0 <= event["phase_code"]) & (event["phase_code"] <= 5)) and
         len(event["phase"]) == 1999 and all(PHASES[int(code)] == phase for code, phase in zip(event["phase_code"], event["phase"])),
         f"{flight}: event alignment, phase, or count mismatch")
    need(np.max(np.abs(event["event_time_s"] - np.arange(0.01, 20.0, 0.01))) <= 1e-12,
         f"{flight}: exported event times do not match the 10 ms schedule")
    need(exported.get("closure", {}).get("requested_torque_vs_nominal_minus_applied_max_abs_Nm", math.inf) <= 1e-8 and
         exported.get("closure", {}).get("true_dynamics_equation_residual_max_abs_Nm", math.inf) <= 1e-12,
         f"{flight}: exporter physical closure failed")
    event["tracking_metrics"] = tracking
    event["raw_tracking_indicators"] = {
        "terminal_status": status["engine_status"], "safety_stop_reason": status["safety_stop_reason"],
        "motor_saturated_transition_count": int(audit_row["motor_saturated_steps"]),
        "generalized_clipped_transition_count": int(audit_row["generalized_clipped_steps"]),
        "position_Q_m_from_ROOT_raw_audit": float(audit_row["position_Q_m"]),
        "peak_tilt_rad": float(np.max(tilt)), "peak_body_rate_rad_s": float(np.max(body_rate)),
    }
    event["alpha_BS_xy_probe_range_rad_s2"] = {
        axis: {"min": float(np.min(event["X18"][:, index])), "max": float(np.max(event["X18"][:, index]))}
        for axis, index in (("roll", 3), ("pitch", 4))
    }
    return event, status_sha, raw_sha


def rmse_rows(error: np.ndarray, phase_code: np.ndarray, mask: np.ndarray | None = None) -> dict[str, Any]:
    if mask is None:
        mask = np.ones(error.shape[0], dtype=bool)
    n = int(np.count_nonzero(mask))
    if n == 0:
        return {"event_count": 0, "axis_rmse_rad_s2": None, "vector_rmse_rad_s2": None, "yaw_rmse_rad_s2": None}
    axis = np.sqrt(np.mean(error[mask] ** 2, axis=0))
    return {"event_count": n, "axis_rmse_rad_s2": axis.tolist(),
            "vector_rmse_rad_s2": float(np.sqrt(np.mean(np.sum(error[mask] ** 2, axis=1)))),
            "yaw_rmse_rad_s2": float(axis[2])}


def run() -> tuple[dict[str, Any], str]:
    need(sha256(TASKBOOK) == PINS["taskbook_sha256"], "Matched-position taskbook SHA mismatch")
    need(sha256(EXPERIMENT / "export_matched_position_probe_events_v2.m") == PINS["exporter_sha256"], "Frozen event exporter SHA mismatch")
    audit, audit_rows = load_audit()
    deployment, forward, model_sources = load_frozen_model()
    parameters = deployment["parameters"]
    rows: dict[str, dict[str, Any]] = {}
    status_hashes: dict[str, str] = {}
    raw_hashes: dict[str, str] = {}
    for flight, contract in FLIGHTS.items():
        event, status_sha, raw_sha = load_export(flight, contract, audit_rows[flight])
        prediction = np.asarray(forward(event["X18"], parameters)["physical_output_rad_s2"], dtype=np.float64)
        need(prediction.shape == (1999, 3) and np.isfinite(prediction).all(), f"{flight}: A1 forward output invalid")
        error = prediction - event["target"]
        all_scores = rmse_rows(error, event["phase_code"])
        phase_scores = {
            name: rmse_rows(error, event["phase_code"], event["phase_code"] == code)
            for code, name in PHASES.items()
        }
        event["prediction_raw_rad_s2"] = prediction.tolist()
        event["prediction_error_raw_rad_s2"] = error.tolist()
        event["prediction_metrics"] = {"ALL": all_scores, "phase": phase_scores}
        rows[flight] = json_ready_event(event)
        status_hashes[flight] = status_sha
        raw_hashes[flight] = raw_sha
    pairs = []
    for name, b_flight, c5_flight in (("T1", "T1_B", "T1_C5"), ("T3", "T3_B", "T3_C5")):
        r_b = rows[b_flight]["prediction_metrics"]["ALL"]["yaw_rmse_rad_s2"]
        r_c5 = rows[c5_flight]["prediction_metrics"]["ALL"]["yaw_rmse_rad_s2"]
        delta = r_c5 - r_b
        pairs.append({
            "pair": name, "B_flight": b_flight, "C5_flight": c5_flight,
            "all_1999_event_yaw_RMSE_B_rad_s2": r_b,
            "all_1999_event_yaw_RMSE_C5_rad_s2": r_c5,
            "delta_C5_minus_B_rad_s2": delta,
            "ratio_C5_over_B": (r_c5 / r_b) if r_b > 0.0 else None,
            "delta_gate_ge_0_02": delta >= 0.02,
            "ratio_gate_ge_1_25_no_division": r_c5 >= 1.25 * r_b,
            "pair_gate_pass": delta >= 0.02 and r_c5 >= 1.25 * r_b,
            "comparison_basis": "Each 1,999-event raw trajectory is scored against its own physically reconstructed target; paired intervention tests context transfer, not neural-component causality.",
        })
    gate_pass = all(pair["pair_gate_pass"] for pair in pairs)
    source_files = {
        str(Path(__file__).resolve().relative_to(ROOT)).replace("\\", "/"): sha256(Path(__file__).resolve()),
        "experiments/attitude_position_context_probe_20261024/export_matched_position_probe_events_v2.m": PINS["exporter_sha256"],
        "experiments/attitude_cm18_a1_20261024/deployment_v1/deployment_parameters_v1.json": PINS["deployment_sha256"],
        "reports/attitude_position_context_probe_20261024/ROOT_ALL4_RAW_AUDIT_v1.json": PINS["raw_audit_sha256"],
        "reports/attitude_cm18_a2_20261024/ROOT_MATCHED_POSITION_PROBE_TASKBOOK_v1_ZH.md": PINS["taskbook_sha256"],
        **model_sources,
    }
    result = {
        "schema": "ROOT_MATCHED_POSITION_FROZEN_A1_EVALUATION_V1",
        "status": "PASS_GATES" if gate_pass else "FAIL_GATES",
        "interpretation": "Frozen A1 canonical-double offline prediction across two fixed matched position-probe scene pairs; tracking metrics describe each trajectory against its own filtered reference.",
        "identity": {
            "deployment_path": str(DEPLOYMENT), "deployment_sha256": PINS["deployment_sha256"],
            "checkpoint_sha256": PINS["checkpoint_sha256"], "selected_step": 30000,
            "normalizer_sha256": PINS["normalizer_sha256"],
            "normalizer_float64_arrays_sha256": PINS["normalizer_float64_arrays_sha256"],
            "dtype": "canonical float64 deployment arrays; trained float32 W/b promoted to float64",
            "model_source_files": model_sources, "event_exporter_sha256": PINS["exporter_sha256"],
            "event_exporter_path": "experiments/attitude_position_context_probe_20261024/export_matched_position_probe_events_v2.m",
            "raw_audit_sha256": PINS["raw_audit_sha256"], "taskbook_sha256": PINS["taskbook_sha256"],
            "input_manifest_sha256": PINS["input_manifest_sha256"],
            "dataset_manifest_sha256": PINS["dataset_manifest_sha256"],
            "status_sha256_by_flight": status_hashes, "raw_sha256_by_flight": raw_hashes,
            "event_export_sha256_by_flight": {flight: rows[flight]["file_sha256"] for flight in FLIGHTS},
            "source_files": source_files,
        },
        "scope": {
            "flights": list(FLIGHTS), "events_per_flight": 1999, "training_steps": 0,
            "optimizer_steps": 0, "plant_calls": 0, "TEST_accessed": False,
            "prediction_mode": "canonical-double NumPy A1 forward; no retraining or refit",
            "tracking_comparison": "SO3 uses 20,000 left transition states against filtered attitude reference; position uses 20,001 full states against position reference, with sample counts recorded per interval; metrics are per-trajectory descriptive, not shared-reference causal comparisons",
        },
        "flight_metrics": {
            flight: {
                "scene_id": rows[flight]["identity"]["scene_id"],
                "position_mode": rows[flight]["identity"]["position_mode"],
                "attempt_id": rows[flight]["identity"]["attempt_id"],
                "all_event_prediction": rows[flight]["prediction_metrics"]["ALL"],
                "phase_prediction": rows[flight]["prediction_metrics"]["phase"],
                "tracking_by_time": rows[flight]["tracking_metrics"],
                "raw_tracking_indicators": rows[flight]["raw_tracking_indicators"],
                "alpha_BS_xy_probe_range_rad_s2": rows[flight]["alpha_BS_xy_probe_range_rad_s2"],
            } for flight in FLIGHTS
        },
        "paired_preregistered_gate": {
            "definition": "For each scene, all 1,999 events: Delta = yaw_RMSE(C5) - yaw_RMSE(B); require Delta >= 0.02 rad/s^2 and yaw_RMSE(C5) >= 1.25*yaw_RMSE(B).",
            "pairs": pairs, "both_pairs_pass": gate_pass,
        },
        "deferred_taskbook_items": [
            "AlphaXY TRAIN support min/max was not recomputed; this script deliberately does not scan the 768 TRAIN caches.",
            "Wind/old-action label decomposition is not included; the exporter JSON contains X18/target/closure, and this evaluator does not read additional torque/wind arrays.",
            "Position/attitude metrics are descriptive per trajectory; they do not isolate a neural component or compare against a shared trajectory.",
        ],
        "raw_event_exports": rows,
    }
    short = render_markdown(result)
    return result, short


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Frozen A1 matched-position evaluation",
        "",
        f"Status: **{result['status']}**. A1 checkpoint step 30000, canonical float64 deployment, all 1,999 events per flight.",
        "",
        "| Flight | Position mode | Yaw RMSE (rad/s²) | Roll / pitch / yaw RMSE (rad/s²) | SO(3) RMSE (deg, left 20,000) | Position Q (m, full 20,001 states) | Motor sat. | Generalized clip |",
        "|---|---|---:|---|---:|---:|---:|---:|",
    ]
    for flight, item in result["flight_metrics"].items():
        pred = item["all_event_prediction"]
        tracking = item["tracking_by_time"]["ALL_0_20"]
        raw = item["raw_tracking_indicators"]
        axis = ", ".join(f"{v:.6g}" for v in pred["axis_rmse_rad_s2"])
        lines.append(f"| {flight} | {item['position_mode']} | {pred['yaw_rmse_rad_s2']:.6g} | {axis} | {tracking['SO3_tracking_RMSE_deg']:.6g} | {tracking['position_Q_m']:.6g} | {raw['motor_saturated_transition_count']} | {raw['generalized_clipped_transition_count']} |")
    lines.extend(["", "| Pair | B yaw RMSE | C5 yaw RMSE | Δ C5−B | Δ ≥ 0.02 | C5 ≥ 1.25×B | Pass |", "|---|---:|---:|---:|---|---|---|"])
    for pair in result["paired_preregistered_gate"]["pairs"]:
        lines.append(f"| {pair['pair']} | {pair['all_1999_event_yaw_RMSE_B_rad_s2']:.6g} | {pair['all_1999_event_yaw_RMSE_C5_rad_s2']:.6g} | {pair['delta_C5_minus_B_rad_s2']:.6g} | {pair['delta_gate_ge_0_02']} | {pair['ratio_gate_ge_1_25_no_division']} | {pair['pair_gate_pass']} |")
    lines.extend([
        "", "SO(3)/position tracking values are per-flight descriptive metrics against each flight's own filtered/reference trajectory. The paired offline prediction gate is the preregistered context-transfer test; neither metric establishes component causality or shared-reference control performance.",
        "", "Deferred from the frozen taskbook: all-TRAIN alphaXY support range and wind/old-action decomposition. See the JSON `deferred_taskbook_items` for scope.", "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    output = args.output_dir if args.output_dir.is_absolute() else (ROOT / args.output_dir).resolve()
    json_path = output / "ROOT_FROZEN_A1_EVALUATION_v1.json"
    md_path = output / "ROOT_FROZEN_A1_EVALUATION_v1.md"
    need(not json_path.exists() and not md_path.exists(), f"Refusing to overwrite evaluation outputs in {output}")
    result, markdown = run()
    output.mkdir(parents=True, exist_ok=True)
    with json_path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    with md_path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(markdown)
    print(json.dumps({"status": result["status"], "report": str(json_path), "short_report": str(md_path), "pairs": result["paired_preregistered_gate"]["pairs"]}, indent=2))


if __name__ == "__main__":
    main()
