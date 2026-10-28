#!/usr/bin/env python3
"""Freeze a separate DC-penalty model preflight study; authorizes no Plant call."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DL_DIR = HERE.parent
DATA = DL_DIR / "position_cosine_gru_train24_causal_v1"
MODEL_SOURCE = DATA / "teacher_position_balanced_dc_penalty_full24_deploy_v1"
TEACHER_DIR = DATA / "task_aware_cv_v1"
CV_DIR = DATA / "teacher_position_balanced_dc_penalty_cv_v1"
TAU = DL_DIR / "gru_prediction_tau01_v1"
COSINE_RELEASE = ROOT / "experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_full72_v1/RELEASE.json"
LOCK_PATH = HERE / "SOURCE_LOCK_v1.json"
RELEASE_PATH = HERE / "RELEASE.json"

EXCLUDED = {"SOURCE_LOCK_v1.json", "RELEASE.json", "NO_PLANT_PREPARE_RESULT_v1.json",
            "MATLAB_EVENTWISE_PARITY_RESULT_v1.json", "RELEASE_NO_PLANT_v1.json",
            "SINGLE_PILOT_AUTHORIZATION_v1.json", "DC_PENALTY_SINGLE_PILOT_SCORE_v1.json"}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    if LOCK_PATH.exists() or RELEASE_PATH.exists():
        raise RuntimeError("Refusing to overwrite an existing release or source lock")
    model = read(HERE / "MODEL_MANIFEST_v1.json")
    train_lock = read(HERE / "FULL24_SOURCE_LOCK_v1.json")
    result = read(HERE / "FULL24_TRAINING_RESULT_v1.json")
    config = read(HERE / "PREDECLARED_FULL24_CONFIG_v1.json")
    teacher = read(TEACHER_DIR / "TRAIN24_FEASIBILITY_TEACHER_MANIFEST_v1.json")
    cv_lock = read(CV_DIR / "DC_PENALTY_SOURCE_LOCK_v1.json")
    tau_path = TAU / "RELEASE.json"
    tau = read(tau_path)
    tau_lock_path = TAU / "SOURCE_LOCK_v1.json"
    tau_lock = read(tau_lock_path)
    parent_manifest = Path(tau["parent_manifest_path"])
    cosine_release = read(COSINE_RELEASE)

    copies = {
        HERE / "DEPLOYMENT_MODEL_v1.mat": model["weights_mat_sha256"],
        HERE / "candidate_runner_work/matlab/models/position_balanced_full24.mat": model["weights_mat_sha256"],
        HERE / "DEPLOYMENT_MODEL_v1.pt": model["checkpoint_sha256"],
        HERE / "DEPLOYMENT_WEIGHTS_v1.npz": model["weights_export_npz_sha256"],
        HERE / "FULL24_TRAINING_RESULT_v1.json": model["training_result_sha256"],
        HERE / "FULL24_SOURCE_LOCK_v1.json": model["training_source_lock_sha256"],
        HERE / "PREDECLARED_FULL24_CONFIG_v1.json": model["training_config_sha256"],
        HERE / "train_full24_dc_penalty_deployment_v1.py": model["training_script_sha256"],
    }
    for path, expected in copies.items():
        if sha(path) != expected:
            raise RuntimeError(f"DC model artifact mismatch: {path}")
    if model["schema"] != "POSITION_C5_TEACHER_POSITION_DC_PENALTY_FULL24_DEPLOY_MODEL_MANIFEST_V1":
        raise RuntimeError("Unexpected DC deployment model manifest")
    if result["checkpoint_sha256"] != model["checkpoint_sha256"] or result["config_sha256"] != model["training_config_sha256"]:
        raise RuntimeError("Training result does not bind the model/config")
    if train_lock["checkpoint_sha256"] != model["checkpoint_sha256"] or train_lock["training_result_sha256"] != model["training_result_sha256"]:
        raise RuntimeError("Full24 lock does not bind the checkpoint/result")
    if config["training_scene_ids"] != model["training_scene_ids"] or len(model["training_scene_ids"]) != 24:
        raise RuntimeError("Full24 scene list mismatch")
    if (sha(DATA / "COSINE_GRU_C5_TRAIN24_POSITION_CAUSAL_PAIRS_v1.npz") != model["dataset_sha256"] or
            sha(TEACHER_DIR / "TRAIN24_FEASIBILITY_TEACHER_DELTAS_v1.npz") != model["teacher_npz_sha256"] or
            teacher["teacher_delta_npz_sha256"] != model["teacher_npz_sha256"] or
            sha(CV_DIR / "DC_PENALTY_OOF_v1.npz") != model["cv_oof_sha256"] or
            cv_lock["oof_sha256"] != model["cv_oof_sha256"]):
        raise RuntimeError("TRAIN24, teacher or CV lineage does not match model manifest")
    if (tau.get("study_id") != "gru_prediction_tau01_v1" or tau.get("position_delayed_prediction_tau_s") != 0.1 or
            tau_lock.get("schema") != "DL1018_GRU_PREDICTION_TAU01_SOURCE_LOCK_V1" or tau_lock.get("status") != "FROZEN" or
            sha(parent_manifest) != tau["parent_manifest_sha256"] or
            cosine_release.get("study_id") != "gru_stream_cosine_tracking_head_full72_v1"):
        raise RuntimeError("Frozen parent tau01/cosine lineage mismatch")
    payload_copy = HERE / "MLP15_DEV72_PAYLOAD_MANIFEST_v2.json"
    payload_source = DL_DIR / "position_teacher_position_balanced_full24_pilot_v1/MLP15_DEV72_PAYLOAD_MANIFEST_v2.json"
    if sha(payload_copy) != sha(payload_source):
        raise RuntimeError("Copied DEV/VAL payload manifest differs from the reviewed copy")

    data_lock_path = DATA / "SOURCE_LOCK_v1.json"
    teacher_manifest_path = TEACHER_DIR / "TRAIN24_FEASIBILITY_TEACHER_MANIFEST_v1.json"
    external_paths = {
        "training_data": DATA / "COSINE_GRU_C5_TRAIN24_POSITION_CAUSAL_PAIRS_v1.npz",
        "training_data_manifest": DATA / "DATASET_MANIFEST_v1.json",
        "training_data_source_lock": data_lock_path,
        "teacher_labels": TEACHER_DIR / "TRAIN24_FEASIBILITY_TEACHER_DELTAS_v1.npz",
        "teacher_manifest": teacher_manifest_path,
        "teacher_generator_script": TEACHER_DIR / "fit_teacher_distillation_oof_v1.py",
        "dc_cv_plan": CV_DIR / "PREDECLARED_CONFIG_v1.json",
        "dc_cv_oof": CV_DIR / "DC_PENALTY_OOF_v1.npz",
        "dc_cv_results": CV_DIR / "DC_PENALTY_RESULTS_v1.json",
        "dc_cv_source_lock": CV_DIR / "DC_PENALTY_SOURCE_LOCK_v1.json",
        "model_source_mat": MODEL_SOURCE / "DEPLOYMENT_MODEL_v1.mat",
        "model_source_pt": MODEL_SOURCE / "DEPLOYMENT_MODEL_v1.pt",
        "model_source_npz": MODEL_SOURCE / "DEPLOYMENT_WEIGHTS_v1.npz",
        "model_source_manifest": MODEL_SOURCE / "MODEL_MANIFEST_v1.json",
        "model_source_lock": MODEL_SOURCE / "FULL24_SOURCE_LOCK_v1.json",
        "parent_tau01_release": tau_path,
        "parent_tau01_source_lock": tau_lock_path,
        "parent_cosine_release": COSINE_RELEASE,
        "parent_cosine_manifest": parent_manifest,
        "parent_dev72_payload_manifest": payload_source,
    }
    expected_external = {
        "training_data": model["dataset_sha256"],
        "training_data_manifest": train_lock["input_hashes"]["dataset_manifest_sha256"],
        "training_data_source_lock": train_lock["input_hashes"]["dataset_source_lock_sha256"],
        "teacher_labels": model["teacher_npz_sha256"],
        "teacher_manifest": train_lock["input_hashes"]["teacher_manifest_sha256"],
        "teacher_generator_script": teacher["teacher_script_sha256"],
        "dc_cv_plan": train_lock["input_hashes"]["cv_plan_sha256"],
        "dc_cv_oof": model["cv_oof_sha256"],
        "dc_cv_results": train_lock["input_hashes"]["cv_results_sha256"],
        "dc_cv_source_lock": train_lock["input_hashes"]["cv_source_lock_sha256"],
        "model_source_mat": model["weights_mat_sha256"],
        "model_source_pt": model["checkpoint_sha256"],
        "model_source_npz": model["weights_export_npz_sha256"],
        "model_source_manifest": sha(MODEL_SOURCE / "MODEL_MANIFEST_v1.json"),
        "model_source_lock": model["training_source_lock_sha256"],
        "parent_tau01_source_lock": tau["source_lock_sha256"],
        "parent_cosine_manifest": tau["parent_manifest_sha256"],
        "parent_dev72_payload_manifest": sha(payload_source),
    }
    external = []
    for name, path in external_paths.items():
        digest = sha(path)
        if name in expected_external and digest != expected_external[name]:
            raise RuntimeError(f"External source binding mismatch: {name}")
        external.append({"name": name, "path": str(path.resolve()), "sha256": digest})

    records = []
    for path in sorted(HERE.rglob("*")):
        if not path.is_file() or path.name in EXCLUDED or "__pycache__" in path.parts:
            continue
        if path.parent.name == "audits" and path.name.startswith("NO_PLANT_ATTEMPT_"):
            continue
        records.append({"relative_path": path.relative_to(HERE).as_posix(), "sha256": sha(path), "bytes": path.stat().st_size})
    expected_runtime = "candidate_runner_work/matlab/runtime/run_mlp15_dev72_closed_loop.m"
    if not any(x["relative_path"] == expected_runtime for x in records):
        raise RuntimeError("Isolated closed-loop runtime is not in source lock")
    lock = {
        "schema": "POSITION_TEACHER_DC_PENALTY_FULL24_PREFLIGHT_SOURCE_LOCK_V1",
        "study_id": "position_teacher_dc_penalty_full24_preflight_v1",
        "scope": "isolated candidate runtime, DC-penalty TRAIN24 model, eventwise parity and no-Plant check",
        "files": records, "file_count": len(records), "external_inputs": external,
        "weights_mat_sha256": sha(HERE / "candidate_runner_work/matlab/models/position_balanced_full24.mat"),
        "checkpoint_sha256": sha(HERE / "DEPLOYMENT_MODEL_v1.pt"),
        "model_manifest_sha256": sha(HERE / "MODEL_MANIFEST_v1.json"),
        "training_data_sha256": model["dataset_sha256"], "teacher_npz_sha256": model["teacher_npz_sha256"],
        "dc_cv_oof_sha256": model["cv_oof_sha256"],
        "parent_tau01_release_sha256": sha(tau_path), "parent_cosine_release_sha256": sha(COSINE_RELEASE),
        "plant_calls_authorized": 0,
    }
    dump(LOCK_PATH, lock)

    release = {
        "schema": "DL1018_POSITION_C5_RESIDUAL_GRU_NOPLANT_V1",
        "study_id": "position_teacher_dc_penalty_full24_preflight_v1",
        "candidate_arm_id": "COSINE_GRU_C5_PLUS_TRAIN24_POSITION_DC_PENALTY_FULL24_V1",
        "status": "PREPARED_NO_PLANT_PENDING_ROOT_AUDIT",
        "authorization_phase": "NO_PLANT_REVIEW_ONLY",
        "fixed_scene_id": "DL1018_VAL_T3_C01_W14", "authorized_scenes": ["DL1018_VAL_T3_C01_W14"],
        "authorized_Plant_calls": 0, "Plant_calls": 0, "training_runs": 0,
        "TEST_read": False, "test_data_read": False, "inertia_reconstruction_enabled": False,
        "parent_tau01_release_path": str(tau_path.resolve()), "parent_tau01_release_sha256": sha(tau_path),
        "parent_tau01_model_sha256": tau["model_sha256"], "parent_tau01_source_lock_sha256": tau["source_lock_sha256"],
        "parent_cosine_release_path": str(COSINE_RELEASE.resolve()), "parent_cosine_release_sha256": sha(COSINE_RELEASE),
        "parent_cosine_manifest_path": str(parent_manifest.resolve()), "parent_cosine_manifest_sha256": sha(parent_manifest),
        "payload_manifest_sha256": sha(payload_copy),
        "training_data_path": str(external_paths["training_data"].resolve()), "training_data_sha256": model["dataset_sha256"],
        "training_data_manifest_sha256": expected_external["training_data_manifest"],
        "training_data_source_lock_sha256": expected_external["training_data_source_lock"],
        "teacher_npz_path": str(external_paths["teacher_labels"].resolve()),
        "teacher_manifest_path": str(external_paths["teacher_manifest"].resolve()),
        "teacher_generator_script_path": str(external_paths["teacher_generator_script"].resolve()),
        "dc_cv_oof_path": str(external_paths["dc_cv_oof"].resolve()), "dc_cv_oof_sha256": model["cv_oof_sha256"],
        "position_method_id": "C5_AXIS_MIXED_COORDINATE_M110", "position_path_changed": True,
        "position_delayed_prediction_h_s": 0.01, "position_delayed_prediction_tau_s": 0.1,
        "position_delayed_prediction_rho": 0.1, "notch_enabled": False,
        "position_residual_gru": {
            "enabled": True, "architecture": model["architecture"],
            "objective": model["objective"],
            "weights_relative_path": "candidate_runner_work/matlab/models/position_balanced_full24.mat",
            "weights_sha256": sha(HERE / "candidate_runner_work/matlab/models/position_balanced_full24.mat"),
            "checkpoint_sha256": sha(HERE / "DEPLOYMENT_MODEL_v1.pt"),
            "model_manifest_sha256": sha(HERE / "MODEL_MANIFEST_v1.json"),
            "training_result_sha256": model["training_result_sha256"],
            "training_source_lock_sha256": model["training_source_lock_sha256"],
            "training_data_sha256": model["dataset_sha256"], "teacher_npz_sha256": model["teacher_npz_sha256"],
            "dc_cv_oof_sha256": model["cv_oof_sha256"], "training_scene_count": 24,
            "seed": result.get("seed", 20261028), "optimizer_steps": result.get("optimizer_steps", 300),
            "normalizer_scope": model["normalizer_scope"], "input_scope": "causal X14 only",
            "event_rate_hz": 100, "first_event_time_s": 0.01,
            "first_ready_event_index_zero_based": 31, "first_ready_event_time_s": 0.32,
            "hidden_reset_per_scene": True, "hidden_updates_during_warmup": True,
            "beta_formula": "clip(event_time_s/1.8,0,1)", "delta_clip_mps2": 0.5,
            "total_action_clip_mps2": 3.0,
            "apply_after": "causal C5 final applied acceleration, post-PCF, pre-mass force conversion",
            "teacher_future_trajectory_runtime_input": False,
        },
        "source_lock_path": "SOURCE_LOCK_v1.json", "source_lock_sha256": sha(LOCK_PATH),
        "source_file_count": lock["file_count"],
        "release_notes": "No-Plant preparation only. Separate DC-penalty full24 weights; TRAIN24 eventwise parity and no-Plant boundary must pass. No closed-loop pilot is authorized.",
    }
    dump(RELEASE_PATH, release)
    print(json.dumps({"study_id": lock["study_id"], "source_lock_sha256": sha(LOCK_PATH),
                      "release_sha256": sha(RELEASE_PATH), "source_file_count": lock["file_count"],
                      "weights_sha256": release["position_residual_gru"]["weights_sha256"],
                      "plant_calls_authorized": 0}, indent=2))


if __name__ == "__main__":
    main()
