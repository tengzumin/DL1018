#!/usr/bin/env python3
"""Freeze an isolated no-Plant pilot package and bind it to its TRAIN24 model."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DL_DIR = HERE.parent
PROJECT_ROOT = HERE.parents[2]
TAU_STUDY = DL_DIR / "gru_prediction_tau01_v1"
COSINE_RELEASE = PROJECT_ROOT / "experiments" / "dl_attitude_replacement_20261026" / "gru_stream_cosine_tracking_head_full72_v1" / "RELEASE.json"
MODEL_JSON = HERE / "MODEL_MANIFEST_v1.json"
MODEL_MAT = HERE / "position_teacher_distill_full24.mat"
MODEL_PT = HERE / "position_teacher_distill_full24.pt"
INPUTS_MAT = HERE / "MATLAB_EVENTWISE_PARITY_INPUTS_v1.mat"
INPUTS_JSON = HERE / "MATLAB_EVENTWISE_PARITY_INPUTS_v1.json"
LOCK_PATH = HERE / "SOURCE_LOCK_v1.json"
RELEASE_PATH = HERE / "RELEASE.json"

EXCLUDED = {"SOURCE_LOCK_v1.json", "RELEASE.json", "NO_PLANT_PREPARE_RESULT_v1.json",
            "MATLAB_EVENTWISE_PARITY_RESULT_v1.json"}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def dump(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    if LOCK_PATH.exists() or RELEASE_PATH.exists():
        raise RuntimeError("Refusing to replace an existing source lock or release")
    model = json.loads(MODEL_JSON.read_text(encoding="utf-8"))
    parity = json.loads(INPUTS_JSON.read_text(encoding="utf-8"))
    tau_release_path = TAU_STUDY / "RELEASE.json"
    tau_release = json.loads(tau_release_path.read_text(encoding="utf-8"))
    cosine_release = json.loads(COSINE_RELEASE.read_text(encoding="utf-8"))
    manifest_path = Path(tau_release["parent_manifest_path"])
    data_dir = DL_DIR / "position_cosine_gru_train24_causal_v1"
    teacher_dir = data_dir / "task_aware_cv_v1"
    external_paths = {
        "training_data": data_dir / "COSINE_GRU_C5_TRAIN24_POSITION_CAUSAL_PAIRS_v1.npz",
        "training_data_manifest": data_dir / "DATASET_MANIFEST_v1.json",
        "training_data_source_lock": data_dir / "SOURCE_LOCK_v1.json",
        "teacher_labels": teacher_dir / "TRAIN24_FEASIBILITY_TEACHER_DELTAS_v1.npz",
        "teacher_manifest": teacher_dir / "TRAIN24_FEASIBILITY_TEACHER_MANIFEST_v1.json",
        "teacher_generator_script": teacher_dir / "fit_teacher_distillation_oof_v1.py",
        "parent_tau01_source_lock": TAU_STUDY / "SOURCE_LOCK_v1.json",
        "parent_cosine_manifest": manifest_path,
        "parent_dev72_payload_manifest": TAU_STUDY / "MLP15_DEV72_PAYLOAD_MANIFEST_v2.json",
    }
    external = [{"name": name, "path": str(path.resolve()), "sha256": sha(path)}
                for name, path in external_paths.items()]
    if sha(MODEL_MAT) != model["weights_mat_sha256"] or sha(MODEL_PT) != model["checkpoint_sha256"]:
        raise RuntimeError("Full24 model artifact SHA mismatch")
    if parity["weights_mat_sha256"] != sha(MODEL_MAT) or parity["model_checkpoint_sha256"] != sha(MODEL_PT):
        raise RuntimeError("Parity export is not bound to the frozen model")
    if tau_release.get("study_id") != "gru_prediction_tau01_v1" or tau_release.get("position_delayed_prediction_tau_s") != 0.1:
        raise RuntimeError("Expected the frozen causal C5 tau01 parent release")
    if cosine_release.get("study_id") != "gru_stream_cosine_tracking_head_full72_v1":
        raise RuntimeError("Unexpected parent cosine tracking release")
    if sha(manifest_path) != tau_release["parent_manifest_sha256"]:
        raise RuntimeError("Parent cosine manifest SHA mismatch")
    payload_manifest = json.loads(external_paths["parent_dev72_payload_manifest"].read_text(encoding="utf-8"))
    if (payload_manifest.get("status") != "PASS_NO_PLANT_REUSE" or
            payload_manifest.get("scene_count") != 72 or payload_manifest.get("test_data_read") is not False or
            sha(HERE / "MLP15_DEV72_PAYLOAD_MANIFEST_v2.json") != sha(external_paths["parent_dev72_payload_manifest"])):
        raise RuntimeError("Copied DEV/VAL payload manifest is not byte-identical or is outside locked scope")
    expected_external = {
        "training_data": model["dataset_sha256"],
        "training_data_manifest": model["dataset_manifest_sha256"],
        "training_data_source_lock": model["dataset_source_lock_sha256"],
        "teacher_labels": model["teacher_npz_sha256"],
        "teacher_manifest": model["teacher_manifest_sha256"],
        "teacher_generator_script": model["teacher_generator_script_sha256"],
        "parent_tau01_source_lock": tau_release["source_lock_sha256"],
        "parent_cosine_manifest": tau_release["parent_manifest_sha256"],
    }
    if any(next(x["sha256"] for x in external if x["name"] == name) != digest
           for name, digest in expected_external.items()):
        raise RuntimeError("An external TRAIN/teacher/parent source hash mismatches its lineage manifest")

    # Lock every copied paired-runner source plus all model/training/parity inputs and entrypoints.
    records = []
    for p in sorted(HERE.rglob("*")):
        if not p.is_file() or p.name in EXCLUDED or "__pycache__" in p.parts:
            continue
        rel = p.relative_to(HERE).as_posix()
        if rel.startswith("audits/") and p.name.startswith("NO_PLANT_ATTEMPT_"):
            continue
        records.append({"relative_path": rel, "sha256": sha(p), "bytes": p.stat().st_size})
    if not any(r["relative_path"] == "candidate_runner_work/matlab/runtime/run_mlp15_dev72_closed_loop.m" for r in records):
        raise RuntimeError("Copied candidate runner entry is not included in source lock")
    lock = {
        "schema": "POSITION_TEACHER_DISTILL_FULL24_PILOT_SOURCE_LOCK_V1",
        "scope": "isolated candidate runtime, TRAIN24 model, parity inputs and no-Plant checks",
        "study_id": "position_teacher_distill_full24_pilot_v1",
        "files": records,
        "file_count": len(records),
        "external_inputs": external,
        "weights_mat_sha256": sha(MODEL_MAT),
        "checkpoint_sha256": sha(MODEL_PT),
        "model_manifest_sha256": sha(MODEL_JSON),
        "training_data_sha256": model["dataset_sha256"],
        "teacher_npz_sha256": model["teacher_npz_sha256"],
        "parent_tau01_release_sha256": sha(tau_release_path),
        "parent_cosine_release_sha256": sha(COSINE_RELEASE),
        "plant_calls_authorized": 0,
    }
    dump(LOCK_PATH, lock)

    release = {
        "schema": "DL1018_POSITION_C5_RESIDUAL_GRU_NOPLANT_V1",
        "study_id": "position_teacher_distill_full24_pilot_v1",
        "candidate_arm_id": "COSINE_GRU_C5_PLUS_TRAIN24_FEASIBILITY_TEACHER_STUDENT_V1",
        "status": "PREPARED_NO_PLANT_PENDING_ROOT_AUDIT",
        "authorization_phase": "NO_PLANT_REVIEW_ONLY",
        "fixed_scene_id": "DL1018_VAL_T3_C01_W14",
        "authorized_scenes": ["DL1018_VAL_T3_C01_W14"],
        "authorized_Plant_calls": 0,
        "Plant_calls": 0,
        "training_runs": 0,
        "TEST_read": False,
        "test_data_read": False,
        "inertia_reconstruction_enabled": False,
        "parent_tau01_release_path": str(tau_release_path.resolve()),
        "parent_tau01_release_sha256": sha(tau_release_path),
        "parent_tau01_model_sha256": tau_release["model_sha256"],
        "parent_tau01_source_lock_sha256": tau_release["source_lock_sha256"],
        "parent_cosine_release_path": str(COSINE_RELEASE.resolve()),
        "parent_cosine_release_sha256": sha(COSINE_RELEASE),
        "parent_cosine_manifest_path": tau_release["parent_manifest_path"],
        "parent_cosine_manifest_sha256": tau_release["parent_manifest_sha256"],
        "payload_manifest_sha256": sha(HERE / "MLP15_DEV72_PAYLOAD_MANIFEST_v2.json"),
        "training_data_path": str(external_paths["training_data"].resolve()),
        "training_data_sha256": model["dataset_sha256"],
        "training_data_manifest_sha256": model["dataset_manifest_sha256"],
        "training_data_source_lock_sha256": model["dataset_source_lock_sha256"],
        "teacher_npz_path": str(external_paths["teacher_labels"].resolve()),
        "teacher_manifest_path": str(external_paths["teacher_manifest"].resolve()),
        "teacher_generator_script_path": str(external_paths["teacher_generator_script"].resolve()),
        "position_method_id": "C5_AXIS_MIXED_COORDINATE_M110",
        "position_path_changed": True,
        "position_delayed_prediction_h_s": 0.01,
        "position_delayed_prediction_tau_s": 0.1,
        "position_delayed_prediction_rho": 0.1,
        "notch_enabled": False,
        "position_residual_gru": {
            "enabled": True,
            "architecture": "GRU(14,32) -> Linear(32,3)",
            "weights_relative_path": "candidate_runner_work/matlab/models/position_teacher_distill_full24.mat",
            "weights_sha256": sha(HERE / "candidate_runner_work/matlab/models/position_teacher_distill_full24.mat"),
            "checkpoint_sha256": sha(MODEL_PT),
            "model_manifest_sha256": sha(MODEL_JSON),
            "training_data_sha256": model["dataset_sha256"],
            "teacher_npz_sha256": model["teacher_npz_sha256"],
            "teacher_manifest_sha256": model["teacher_manifest_sha256"],
            "teacher_generator_script_sha256": model["teacher_generator_script_sha256"],
            "seed": model["seed"],
            "optimizer_steps": model["optimizer_steps"],
            "normalizer_scope": "all 24 TRAIN scenes only",
            "input_scope": "causal X14 only",
            "event_rate_hz": 100,
            "first_event_time_s": 0.01,
            "first_ready_event_index_zero_based": 31,
            "first_ready_event_time_s": 0.32,
            "hidden_reset_per_scene": True,
            "hidden_updates_during_warmup": True,
            "beta_formula": "clip(event_time_s/1.8,0,1)",
            "delta_clip_mps2": 0.5,
            "total_action_clip_mps2": 3.0,
            "apply_after": "causal C5 final applied acceleration, post-PCF, pre-mass force conversion",
            "teacher_future_trajectory_runtime_input": False,
        },
        "source_lock_path": "SOURCE_LOCK_v1.json",
        "source_lock_sha256": sha(LOCK_PATH),
        "source_file_count": lock["file_count"],
        "release_notes": "No-Plant preparation only. The full24 student was fit on TRAIN teacher labels and has no independent validation or closed-loop evidence. The single fixed DEV/VAL scene remains unrun.",
    }
    dump(RELEASE_PATH, release)
    print(json.dumps({"source_lock_sha256": sha(LOCK_PATH), "release_sha256": sha(RELEASE_PATH),
                      "source_file_count": lock["file_count"], "weights_sha256": release["position_residual_gru"]["weights_sha256"]}, indent=2))


if __name__ == "__main__":
    main()
