"""One-scene A1R/A1T map comparison on the same audited A1T event inputs."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import h5py
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
TASKBOOK_REL = "reports/attitude_cm18_datarepair_20261024/ROOT_SAME_INPUT_MAP_COMPARISON_TASKBOOK_v1.json"
TASKBOOK_SHA = "cf54be549a7853280309fe35592559382c412f1c490523b5746275cb4a9340ff"
AGGREGATE_REL = "reports/attitude_cm18_datarepair_20261024/root_aggregate_decomposition12_v1/A1T_SAME_STATE_DECOMPOSITION12_v1.json"
AGGREGATE_SHA = "6a2e1186f18c0f24d24f88bed5c1fb84888b199c89f892bd22ae70e892e62ae2"
A1R_DEPLOY_REL = "experiments/attitude_cm18_datarepair_20261024/postselection_a1r_v1/deployment_parameters_v1.json"
A1R_DEPLOY_SHA = "b3ab7a3d99df639d4cc0a10ec2b6fcd4622388f58c90c25424e472164ef38d23"
A1T_DEPLOY_REL = "experiments/attitude_cm18_datarepair_20261024/postselection_a1t_v1/deployment_parameters_v1.json"
A1T_DEPLOY_SHA = "dd5375623cf47abed1db1e620a7d00358aff71b5985ead13e88ba05218952b42"
NUMPY_MODEL_REL = "experiments/attitude_cm18_a1_20261024/model_cm18_v1.py"
NUMPY_MODEL_SHA = "ad32c4f97bf96c63172547c944d80c45062502f1062b774934e0f7a868720cf6"
AUDIT_SOURCE_REL = "reports/attitude_cm18_datarepair_20261024/a1t_screen12_control_v1/audit_a1t_screen12_log_v1.py"
AUDIT_SOURCE_SHA = "14de8af50058ebfb39b1d7ca484561b50adf5086bdfacd0dc3a541fd6871f6be"
D_MAX = np.array([45.0, 45.0, 4.7124], dtype=np.float64)
EVENT_COUNT = 1999
TRANSITION_COUNT = 20000
WINDOWS = {
    "ALL_0_20": (0.0, 20.0),
    "PRE_0_5": (0.0, 5.0),
    "POST_5_20": (5.0, 20.0),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def repo_file(relative: str, expected_sha: str | None = None) -> Path:
    root = ROOT.resolve(strict=True)
    path = (root / relative).resolve(strict=True)
    require(path.is_relative_to(root), f"path escapes repository: {relative}")
    require(path.is_file(), f"not a file: {relative}")
    if expected_sha is not None:
        require(sha256(path).lower() == expected_sha.lower(), f"SHA256 mismatch: {relative}")
    return path


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    require(isinstance(value, dict), f"expected JSON object: {path}")
    return value


def h5_numeric(file: h5py.File, name: str, dtype: Any = np.float64) -> np.ndarray:
    value = file[name]
    require(isinstance(value, h5py.Dataset), f"expected numeric dataset: {name}")
    require(h5py.check_dtype(ref=value.dtype) is None, f"unexpected reference array: {name}")
    array = np.asarray(value)
    if array.ndim == 2:
        array = array.T
    return np.asarray(array, dtype=dtype)


def summary(error: np.ndarray) -> dict[str, Any]:
    value = np.asarray(error, dtype=np.float64)
    require(value.ndim == 2 and value.shape[1] == 3 and value.shape[0] > 0,
            "metric input must have shape (N,3)")
    require(np.isfinite(value).all(), "metric input contains non-finite values")
    return {
        "count": int(value.shape[0]),
        "signed_mean_rad_s2": np.mean(value, axis=0).tolist(),
        "axis_rms_rad_s2": np.sqrt(np.mean(value * value, axis=0)).tolist(),
        "vector_rms_rad_s2": float(np.sqrt(np.mean(np.sum(value * value, axis=1)))),
        "max_abs_rad_s2": np.max(np.abs(value), axis=0).tolist(),
    }


def load_model_module(path: Path):
    spec = importlib.util.spec_from_file_location("cm18_same_input_model", path)
    require(spec is not None and spec.loader is not None, "cannot import pinned NumPy model")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_scene(scene_id: str, taskbook: dict[str, Any], aggregate: dict[str, Any],
              a1r: dict[str, Any], a1t: dict[str, Any], model: Any) -> dict[str, Any]:
    task_scenes = taskbook.get("inputs", {}).get("scenes")
    agg_scenes = aggregate.get("per_scene")
    require(isinstance(task_scenes, list) and len(task_scenes) == 12, "taskbook must pin 12 scenes")
    require(isinstance(agg_scenes, list) and len(agg_scenes) == 12, "aggregate must contain 12 scenes")
    task_matches = [row for row in task_scenes if row.get("scene_id") == scene_id]
    agg_matches = [row for row in agg_scenes if row.get("scene_id") == scene_id]
    require(len(task_matches) == len(agg_matches) == 1, f"scene not uniquely pinned: {scene_id}")
    task_row, agg_row = task_matches[0], agg_matches[0]
    require(agg_row.get("status") == "PASS_SINGLE_SCENE_ONLY", f"decomposition report is not PASS: {scene_id}")
    require(agg_row.get("task") == task_row.get("task") and agg_row.get("category") == task_row.get("category"),
            f"scene task/category mismatch: {scene_id}")

    report_path = repo_file(task_row["report_path"], task_row["report_sha256"])
    audit_path = repo_file(task_row["audit_path"], task_row["audit_sha256"])
    raw_path = repo_file(task_row["raw_path"], task_row["raw_sha256"])
    report = read_json(report_path)
    audit = read_json(audit_path)
    identity = report.get("identity", {})
    agg_identity = agg_row.get("identity", {})
    require(report.get("status") == "PASS_SINGLE_SCENE_ONLY"
            and report.get("schema") in {
                "A1T_SAME_STATE_ERROR_DECOMPOSITION_SINGLE_SCENE_V1",
                "A1T_SAME_STATE_ERROR_DECOMPOSITION_SINGLE_SCENE_V2",
            },
            f"unexpected decomposition report status/schema: {scene_id}")
    require(identity.get("scene_id", scene_id) == scene_id, f"decomposition scene mismatch: {scene_id}")
    require(str(identity.get("raw_sha256", "")).lower() == task_row["raw_sha256"].lower(),
            f"decomposition raw SHA mismatch: {scene_id}")
    require(str(identity.get("independent_audit_sha256", "")).lower() == task_row["audit_sha256"].lower(),
            f"decomposition audit SHA mismatch: {scene_id}")
    require(str(agg_identity.get("raw_sha256", "")).lower() == task_row["raw_sha256"].lower()
            and str(agg_identity.get("independent_audit_sha256", "")).lower() == task_row["audit_sha256"].lower(),
            f"aggregate raw/audit binding mismatch: {scene_id}")
    require(audit.get("status") == "PASS" and audit.get("scene_id") == scene_id
            and str(audit.get("raw_sha256", "")).lower() == task_row["raw_sha256"].lower(),
            f"independent raw audit is not PASS or has wrong identity: {scene_id}")
    require(str(audit.get("deployment_parameters_sha256", "")).lower() == A1T_DEPLOY_SHA
            and int(audit.get("selected_step", -1)) == 40000,
            f"raw audit model identity mismatch: {scene_id}")

    release_meta = agg_row.get("independent_audit_and_run_release", {})
    release_path = repo_file(release_meta["run_release_path"], release_meta["run_release_sha256"])
    release = read_json(release_path)
    require(release.get("schema") == "A1T_SCREEN12_CONTROL_ROOT_RELEASE_V1"
            and release.get("scene_id") == scene_id and release.get("plant_authorized") is True,
            f"run release identity mismatch: {scene_id}")
    require(str(identity.get("root_release_sha256", "")).lower() == release_meta["run_release_sha256"].lower(),
            f"decomposition does not bind the actual run release: {scene_id}")

    events = report.get("event_records")
    require(isinstance(events, list) and len(events) == EVENT_COUNT, f"wrong event record count: {scene_id}")
    plant_index = np.asarray([int(row["plant_index"]) for row in events], dtype=np.int64)
    time_s = np.asarray([float(row["time_s"]) for row in events], dtype=np.float64)
    expected_index = np.arange(11, 20000, 10, dtype=np.int64)
    expected_time = (expected_index - 1) * 0.001
    require(np.array_equal(plant_index, expected_index), f"plant_index sequence mismatch: {scene_id}")
    require(np.max(np.abs(time_s - expected_time)) <= 1e-12, f"event time sequence mismatch: {scene_id}")

    with h5py.File(raw_path, "r") as raw:
        event_flag = h5_numeric(raw, "log/cm18_event_flag").reshape(-1) != 0
        raw_input = h5_numeric(raw, "log/cm18_event_input_18")
        logged_raw = h5_numeric(raw, "log/cm18_event_raw_acceleration_rad_s2")
        logged_clip = h5_numeric(raw, "log/cm18_event_clipped_acceleration_rad_s2")
        logged_applied = h5_numeric(raw, "log/cm18_applied_acceleration_held_rad_s2")
        logged_beta = h5_numeric(raw, "log/cm18_beta_held").reshape(-1)
        dmax = h5_numeric(raw, "log/cm18_dmax_rad_s2").reshape(-1)
    require(event_flag.shape == (TRANSITION_COUNT,) and raw_input.shape == (TRANSITION_COUNT, 18),
            f"raw event/input layout mismatch: {scene_id}")
    event_rows = np.flatnonzero(event_flag)
    require(event_rows.size == EVENT_COUNT and np.array_equal(event_rows, np.arange(10, 20000, 10)),
            f"raw event positions mismatch: {scene_id}")
    require(np.array_equal(dmax, D_MAX), f"raw output limits mismatch: {scene_id}")
    x18 = raw_input[event_rows]
    require(np.isfinite(x18).all(), f"non-finite event input: {scene_id}")
    require(logged_raw.shape == logged_clip.shape == logged_applied.shape == (TRANSITION_COUNT, 3)
            and logged_beta.shape == (TRANSITION_COUNT,), f"raw event output layout mismatch: {scene_id}")

    params_r = a1r["parameters"]
    params_t = a1t["parameters"]
    require(np.array_equal(np.asarray(params_r["input_mean"], dtype=np.float64),
                           np.asarray(params_t["input_mean"], dtype=np.float64))
            and np.array_equal(np.asarray(params_r["input_std"], dtype=np.float64),
                               np.asarray(params_t["input_std"], dtype=np.float64)),
            "A1R/A1T input normalizers differ")
    pred_r = model.forward(x18, params_r)["physical_output_rad_s2"]
    pred_t = model.forward(x18, params_t)["physical_output_rad_s2"]
    require(pred_r.shape == pred_t.shape == (EVENT_COUNT, 3)
            and np.isfinite(pred_r).all() and np.isfinite(pred_t).all(),
            f"model output shape/non-finite mismatch: {scene_id}")

    records = {
        name: np.asarray([row[field] for row in events], dtype=np.float64)
        for name, field in (
            ("A1T_report_raw_output", "raw_output"),
            ("beta", "beta"),
            ("target_raw", "raw_target_Cstar_over_beta"),
            ("cstar", "Cstar_rad_s2"),
            ("e0", "E0_rad_s2"),
            ("g_flat", "G_row_major"),
        )
    }
    beta = records["beta"].reshape(EVENT_COUNT)
    require(np.all(beta > 0) and np.max(np.abs(logged_beta[event_rows] - beta)) <= 1e-12,
            f"beta disagrees with event report/log: {scene_id}")
    target = records["target_raw"]
    cstar = records["cstar"]
    e0 = records["e0"]
    g = records["g_flat"].reshape(EVENT_COUNT, 3, 3)
    require(np.max(np.abs(target - cstar / beta[:, None])) <= 1e-10,
            f"C*/beta differs from stored raw target: {scene_id}")
    a1t_report_output = records["A1T_report_raw_output"]
    require(a1t_report_output.shape == (EVENT_COUNT, 3)
            and np.max(np.abs(pred_t - a1t_report_output)) <= 1e-9,
            f"A1T NumPy forward does not reproduce decomposition report output: {scene_id}")
    require(np.max(np.abs(logged_raw[event_rows] - pred_t)) <= 1e-9,
            f"A1T NumPy forward does not reproduce raw event output: {scene_id}")
    clipped_t = np.clip(pred_t, -D_MAX, D_MAX)
    applied_t = beta[:, None] * clipped_t
    require(np.max(np.abs(logged_clip[event_rows] - clipped_t)) <= 1e-9,
            f"A1T clip does not reproduce raw event log: {scene_id}")
    require(np.max(np.abs(logged_applied[event_rows] - applied_t)) <= 1e-9,
            f"A1T beta/clip action does not reproduce raw event log: {scene_id}")

    windows: dict[str, Any] = {}
    for name, (left, right) in WINDOWS.items():
        mask = (time_s >= left) & (time_s < right)
        require(mask.sum() == {"ALL_0_20": 1999, "PRE_0_5": 499, "POST_5_20": 1500}[name],
                f"event count differs in {name}: {scene_id}")
        model_rows: dict[str, Any] = {}
        for model_name, prediction in (("A1R", pred_r), ("A1T", pred_t)):
            clipped = np.clip(prediction, -D_MAX, D_MAX)
            applied = beta[:, None] * clipped
            linear_residual = e0 - np.einsum("nij,nj->ni", g, applied)
            model_rows[model_name] = {
                "raw_prediction_minus_Cstar_over_beta": summary((prediction - target)[mask]),
                "applied_beta_clip_action_minus_Cstar": summary((applied - cstar)[mask]),
                "linear_surrogate_E0_minus_G_action": summary(linear_residual[mask]),
                "raw_clip_count_by_axis": np.count_nonzero(np.abs(prediction[mask]) > D_MAX, axis=0).astype(int).tolist(),
            }
        windows[name] = {"event_count": int(mask.sum()), "models": model_rows}

    return {
        "schema": "ROOT_CM18_SAME_INPUT_MAP_COMPARISON_SCENE_V1",
        "status": "PASS_SINGLE_SCENE_DIAGNOSTIC",
        "scope": {
            "scene_id": scene_id,
            "event_count": EVENT_COUNT,
            "transitions": TRANSITION_COUNT,
            "plant_calls": 0,
            "engine_calls": 0,
            "training_steps": 0,
            "optimizer_steps": 0,
            "TEST_accessed": False,
            "full_allocator_replayed": False,
        },
        "identity": {
            "taskbook_path": TASKBOOK_REL,
            "taskbook_sha256": TASKBOOK_SHA,
            "aggregate_path": AGGREGATE_REL,
            "aggregate_sha256": AGGREGATE_SHA,
            "raw_path": task_row["raw_path"],
            "raw_sha256": sha256(raw_path),
            "decomposition_report_path": task_row["report_path"],
            "decomposition_report_sha256": task_row["report_sha256"],
            "independent_audit_path": task_row["audit_path"],
            "independent_audit_sha256": task_row["audit_sha256"],
            "run_release_path": release_meta["run_release_path"],
            "run_release_sha256": release_meta["run_release_sha256"],
            "A1R_deployment_sha256": A1R_DEPLOY_SHA,
            "A1T_deployment_sha256": A1T_DEPLOY_SHA,
            "numpy_model_path": NUMPY_MODEL_REL,
            "numpy_model_sha256": NUMPY_MODEL_SHA,
            "A1R_checkpoint_sha256": a1r["identity"]["checkpoint_sha256"],
            "A1T_checkpoint_sha256": a1t["identity"]["checkpoint_sha256"],
            "A1R_selected_step": int(a1r["identity"]["selected_step"]),
            "A1T_selected_step": int(a1t["identity"]["selected_step"]),
            "A1R_axis_rms_rad_s2": params_r["train_axis_rms_rad_s2"],
            "A1T_axis_rms_rad_s2": params_t["train_axis_rms_rad_s2"],
            "input_normalizers_exactly_equal": True,
        },
        "parity": {
            "A1T_forward_vs_report_max_abs_rad_s2": float(np.max(np.abs(pred_t - a1t_report_output))),
            "A1T_forward_vs_raw_log_max_abs_rad_s2": float(np.max(np.abs(pred_t - logged_raw[event_rows]))),
            "A1T_clip_vs_raw_log_max_abs_rad_s2": float(np.max(np.abs(clipped_t - logged_clip[event_rows]))),
            "A1T_beta_clip_vs_raw_log_max_abs_rad_s2": float(np.max(np.abs(applied_t - logged_applied[event_rows]))),
            "tolerance_abs_rad_s2": 1e-9,
        },
        "windows": windows,
        "interpretation": (
            "Same recorded A1T event inputs isolate pointwise A1R/A1T map differences on this state set. "
            "Errors use the existing C*/beta target and G/E0 linear surrogate; no full allocator, new trajectory, "
            "or closed-loop inference is performed. Label semantics and label-derived target RMS changed together, "
            "so this does not identify either as a separate cause."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene-id", default="DL1018_DEV_T1_C01_W15")
    args = parser.parse_args()
    taskbook_path = repo_file(TASKBOOK_REL, TASKBOOK_SHA)
    aggregate_path = repo_file(AGGREGATE_REL, AGGREGATE_SHA)
    a1r_path = repo_file(A1R_DEPLOY_REL, A1R_DEPLOY_SHA)
    a1t_path = repo_file(A1T_DEPLOY_REL, A1T_DEPLOY_SHA)
    model_path = repo_file(NUMPY_MODEL_REL, NUMPY_MODEL_SHA)
    repo_file(AUDIT_SOURCE_REL, AUDIT_SOURCE_SHA)
    taskbook = read_json(taskbook_path)
    aggregate = read_json(aggregate_path)
    a1r, a1t = read_json(a1r_path), read_json(a1t_path)
    require(taskbook.get("schema") == "ROOT_CM18_SAME_INPUT_MAP_COMPARISON_TASKBOOK_V1"
            and taskbook.get("decision") == "IMPLEMENTATION_APPROVED_EXECUTION_REQUIRES_ROOT_SOURCE_REVIEW",
            "unexpected taskbook schema/decision")
    require(aggregate.get("status") == "COMPLETE_ALL12_DIAGNOSTIC_NO_WINNER_GATE",
            "same-state decomposition aggregate is not complete")
    require(a1r.get("schema") == "CM18_A1R_DEPLOYMENT_PARAMETERS_V1"
            and a1t.get("schema") == "CM18_A1T_DEPLOYMENT_PARAMETERS_V1",
            "unexpected deployment schema")
    require(str(a1r["identity"]["numpy_model_sha256"]).lower() == NUMPY_MODEL_SHA
            and str(a1t["identity"]["numpy_model_sha256"]).lower() == NUMPY_MODEL_SHA,
            "deployments do not bind the same NumPy forward source")
    require(int(a1r["identity"]["selected_step"]) == int(a1t["identity"]["selected_step"]) == 40000,
            "unexpected selected model step")
    model = load_model_module(model_path)
    result = run_scene(args.scene_id, taskbook, aggregate, a1r, a1t, model)
    result["identity"]["source_path"] = str(Path(__file__).resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    result["identity"]["source_sha256"] = sha256(Path(__file__).resolve())

    out_dir = ROOT / "reports/attitude_cm18_datarepair_20261024/same_input_map_comparison_v1"
    out_path = out_dir / f"{args.scene_id}.json"
    if out_path.exists():
        raise FileExistsError(out_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    with out_path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": result["status"], "scene_id": args.scene_id,
                      "output": str(out_path.relative_to(ROOT)),
                      "source_sha256": result["identity"]["source_sha256"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
