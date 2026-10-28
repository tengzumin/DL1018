#!/usr/bin/env python3
"""Build an isolated T3 no-Plant copy with its own binding, fold weights and parity inputs."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
TARGET_ID = "position_compensation_dual_notch_train_diag_online_noPlant_T3_v1"
TARGET = ROOT / "experiments/dl_attitude_replacement_20261028" / TARGET_ID
SOURCE_T3 = ROOT / "experiments/dl_attitude_replacement_20261028/position_dc_penalty_oof_train_pair_preflight_W09_T3_C09_attempt015_v1"
BASE = HERE
LOCK = TARGET / "SOURCE_LOCK_NO_PLANT_v1.json"
RELEASE = TARGET / "RELEASE.json"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    if TARGET.exists():
        raise RuntimeError(f"Refusing to reuse T3 no-Plant study: {TARGET}")
    shutil.copytree(BASE / "candidate_runner_work", TARGET / "candidate_runner_work")
    (TARGET / "audits").mkdir(parents=True)
    (TARGET / "runs").mkdir()
    for name in ("TRAIN_SCENE_BINDING_v1.json", "OOF_FOLD_MODEL_MANIFEST_v1.json",
                 "OOF_HOLDOUT_CHECKPOINT_v1.pt", "MATLAB_EVENTWISE_PARITY_INPUTS_v1.mat",
                 "MATLAB_EVENTWISE_PARITY_INPUTS_v1.json", "RELEASE_NO_PLANT_PREFLIGHT_v1.json"):
        shutil.copy2(SOURCE_T3 / name, TARGET / name)
    # Keep the local parity runner's fold checkpoint exactly aligned with the T3 binding.
    shutil.copytree(SOURCE_T3 / "candidate_runner_work/matlab/models",
                    TARGET / "candidate_runner_work/matlab/models", dirs_exist_ok=True)
    for name in ("position_compensation_dual_notch_init.m", "position_compensation_dual_notch_step.m"):
        shutil.copy2(BASE / "candidate_runner_work/matlab/runtime" / name,
                     TARGET / "candidate_runner_work/matlab/runtime" / name)
    for name in ("run_mlp15_dev72_closed_loop.m", "prepare_train_scene_no_plant.m"):
        p = TARGET / "candidate_runner_work/matlab/runtime" / name
        text = p.read_text(encoding="utf-8")
        text = text.replace("position_compensation_dual_notch_train_diag_online_noPlant_v1", TARGET_ID)
        p.write_text(text, encoding="utf-8", newline="\n")
    # The T3 prepare wrapper differs from T1 only in its diagnostic error wording after scene-order checks.
    prepare = TARGET / "candidate_runner_work/matlab/runtime/prepare_train_scene_no_plant.m"
    text = prepare.read_text(encoding="utf-8")
    anchor = "opts.gate_identity_lock=identity;\n"
    addition = anchor + """assert(isfield(release,'applied_acceleration_dual_notch'), ...
    'DualNotch:Release','Missing fixed dual-notch diagnostic contract.');
opts.stage1_position_runtime.applied_acceleration_dual_notch= ...
    release.applied_acceleration_dual_notch;
"""
    if text.count(anchor) != 1:
        raise RuntimeError("T3 prepare wrapper identity insertion point is not unique.")
    text = text.replace(anchor, addition, 1)
    prepare.write_text(text, encoding="utf-8", newline="\n")

    no_plant_protocol = json.loads((BASE / "DIAGNOSTIC_PROTOCOL_v1.json").read_text(encoding="utf-8"))
    no_plant_protocol["study_id"] = TARGET_ID
    protocol_path = TARGET / "DIAGNOSTIC_PROTOCOL_v1.json"
    protocol_path.write_text(json.dumps(no_plant_protocol, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    integration = json.loads((BASE / "RUNNER_INTEGRATION_CONTRACT_v1.json").read_text(encoding="utf-8"))
    integration["study_id"] = TARGET_ID
    integration["isolated_runner_copy_path"] = str((TARGET / "candidate_runner_work/matlab/runtime/run_mlp15_dev72_closed_loop.m").resolve())
    integration_path = TARGET / "RUNNER_INTEGRATION_CONTRACT_v1.json"
    integration_path.write_text(json.dumps(integration, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    shutil.copy2(BASE / "MATLAB_NOPLANT_PARITY_v1.json", TARGET / "DUAL_NOTCH_TRAIN_HELPER_PARITY_v1.json")
    shutil.copy2(BASE / "verify_full_runner_no_plant_v1.py", TARGET / "verify_full_runner_no_plant_v1.py")
    shutil.copy2(BASE / "prepare_T3_no_plant_study_v1.py", TARGET / "prepare_T3_no_plant_study_v1.py")

    binding = json.loads((TARGET / "TRAIN_SCENE_BINDING_v1.json").read_text(encoding="utf-8-sig"))
    manifest = TARGET / "OOF_FOLD_MODEL_MANIFEST_v1.json"
    weights_path = Path(binding["weights_mat_path"]).resolve(strict=True)
    weights_hash = sha(weights_path)
    release = json.loads((TARGET / "RELEASE_NO_PLANT_PREFLIGHT_v1.json").read_text(encoding="utf-8-sig"))
    replay = json.loads((ROOT / "experiments/dl_attitude_replacement_20261028/position_compensation_dual_notch_train_replay_v1/TRAIN_FROZEN_DUAL_NOTCH_REPLAY_v1.json").read_text(encoding="utf-8-sig"))
    release.update({
        "study_id": TARGET_ID,
        "status": "PREPARED_NO_PLANT_PENDING_ROOT_AUDIT",
        "authorized_Plant_calls": 0,
        "Plant_calls": 0,
        "potential_budget_calls": 0,
        "source_lock_path": str(LOCK.resolve()),
        "train_scene_binding_path": str((TARGET / "TRAIN_SCENE_BINDING_v1.json").resolve()),
        "train_scene_binding_sha256": sha(TARGET / "TRAIN_SCENE_BINDING_v1.json"),
        "model_manifest_path": str(manifest.resolve()),
        "model_manifest_sha256": sha(manifest),
        "parity_inputs_mat_path": str((TARGET / "MATLAB_EVENTWISE_PARITY_INPUTS_v1.mat").resolve()),
        "parity_inputs_mat_sha256": sha(TARGET / "MATLAB_EVENTWISE_PARITY_INPUTS_v1.mat"),
        "parity_inputs_json_path": str((TARGET / "MATLAB_EVENTWISE_PARITY_INPUTS_v1.json").resolve()),
        "parity_inputs_json_sha256": sha(TARGET / "MATLAB_EVENTWISE_PARITY_INPUTS_v1.json"),
        "weights_path": str(weights_path),
        "weights_sha256": weights_hash,
        "position_residual_gru": {**release["position_residual_gru"], "weights_sha256": weights_hash},
        "candidate_runner_closed_loop_sha256": sha(TARGET / "candidate_runner_work/matlab/runtime/run_mlp15_dev72_closed_loop.m"),
        "prepare_wrapper_sha256": sha(prepare),
        "no_plant_wrapper_sha256": sha(TARGET / "candidate_runner_work/matlab/runtime/run_train_pair_preflight_no_plant.m"),
        "eventwise_parity_script_sha256": sha(TARGET / "candidate_runner_work/matlab/runtime/verify_train_oof_fold_matlab_parity.m"),
        "TEST_read": False, "VAL_data_read": False, "inertia_reconstruction_enabled": False,
        "Plant_truth_deployment_input": False, "frozen_replay_status": replay["status"],
        "applied_acceleration_dual_notch": {
            "enabled": True, "sample_rate_hz": 100.0, "centers_hz": [2.2, 3.2],
            "quality_factor_each": [4.0, 4.0], "action_limit_mps2": 3.0,
            "b": [replay["filter"]["b_a_coefficients"][str(f)]["b"] for f in (2.2, 3.2)],
            "a": [replay["filter"]["b_a_coefficients"][str(f)]["a"] for f in (2.2, 3.2)],
            "filter_location": "Post-residual-GRU final action, pre-force injection.",
            "event_update_hz": 100.0, "held_between_events": True, "parameter_sweep": False,
        },
    })

    lock_paths = []
    lock_paths.extend(sorted((TARGET / "candidate_runner_work/matlab").rglob("*.m")))
    lock_paths.extend(sorted((TARGET / "candidate_runner_work/matlab/models").glob("*.mat")))
    lock_paths.extend([
        TARGET / "TRAIN_SCENE_BINDING_v1.json", manifest, TARGET / "OOF_HOLDOUT_CHECKPOINT_v1.pt",
        TARGET / "MATLAB_EVENTWISE_PARITY_INPUTS_v1.mat", TARGET / "MATLAB_EVENTWISE_PARITY_INPUTS_v1.json",
        protocol_path, integration_path, TARGET / "DUAL_NOTCH_TRAIN_HELPER_PARITY_v1.json",
        TARGET / "verify_full_runner_no_plant_v1.py", TARGET / "prepare_T3_no_plant_study_v1.py",
    ])
    unique = sorted({p.resolve(strict=True) for p in lock_paths}, key=lambda p: str(p).lower())
    lock = {"schema": "POSITION_COMPENSATION_DUAL_NOTCH_RUNNER_SOURCE_LOCK_NOPLANT_V1",
            "study_id": TARGET_ID,
            "files": [{"path": str(p), "relative_path": p.relative_to(TARGET.resolve()).as_posix(), "sha256": sha(p)} for p in unique],
            "Plant_calls": 0, "TEST_read": False, "VAL_read": False}
    LOCK.write_text(json.dumps(lock, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    release["source_lock_sha256"] = sha(LOCK)
    release["source_lock_file_count"] = len(unique)
    RELEASE.write_text(json.dumps(release, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"study": str(TARGET.resolve()), "scene_id": binding["selected_scene_id"],
                      "weights_sha256": weights_hash, "release_status": release["status"],
                      "source_lock_sha256": sha(LOCK), "source_lock_file_count": len(unique)}, indent=2))


if __name__ == "__main__":
    main()
