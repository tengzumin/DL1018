#!/usr/bin/env python3
"""Build independent, locked T1/T3 no-Plant copies with position residual GRU absent."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SCHEMA = "DL1018_POSITION_C5_DUAL_NOTCH_NO_POSITION_GRU_NOPLANT_V1"
ID_ROOT = "position_compensation_dual_notch_no_residual_gru_ablation"
TEMPLATE_T1 = ROOT / "experiments/dl_attitude_replacement_20261028/position_compensation_dual_notch_train_diag_online_noPlant_v1"
TEMPLATE_T3 = ROOT / "experiments/dl_attitude_replacement_20261028/position_compensation_dual_notch_train_diag_online_noPlant_T3_v1"
PREFILTERS = {
    "T1": ROOT / "experiments/dl_attitude_replacement_20261028/position_dc_penalty_oof_train_pair_preflight_W09_T1_C10_attempt014_v1",
    "T3": ROOT / "experiments/dl_attitude_replacement_20261028/position_dc_penalty_oof_train_pair_preflight_W09_T3_C09_attempt015_v1",
}
TEMPLATES = {"T1": TEMPLATE_T1, "T3": TEMPLATE_T3}
SCENES = {"T1": "DL1018_DEV_T1_C10_W09", "T3": "DL1018_DEV_T3_C09_W09"}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def patch_one(text: str, old: str, new: str, label: str, count: int = 1) -> str:
    found = text.count(old)
    if found != count:
        raise RuntimeError(f"Expected {count} {label} anchors, found {found}.")
    return text.replace(old, new)


def patch_study(arm: str, target: Path, study_id: str, old_id: str) -> None:
    runner = target / "candidate_runner_work/matlab/runtime/run_mlp15_dev72_closed_loop.m"
    text = runner.read_text(encoding="utf-8")
    text = patch_one(
        text,
        "dualNotchIdentityOk=strcmp(releaseSchema,'DL1018_POSITION_C5_RESIDUAL_GRU_NOPLANT_V1')&& ...",
        "dualNotchIdentityOk=any(strcmp(releaseSchema,{'DL1018_POSITION_C5_RESIDUAL_GRU_NOPLANT_V1','" + SCHEMA + "'}))&& ...",
        "dual-notch-only release identity",
    )
    text = text.replace(old_id, study_id)
    runner.write_text(text, encoding="utf-8", newline="\n")

    prepare = target / "candidate_runner_work/matlab/runtime/prepare_train_scene_no_plant.m"
    text = prepare.read_text(encoding="utf-8")
    text = text.replace(old_id, study_id)
    text = patch_one(
        text,
        "strcmp(char(release.schema),'DL1018_POSITION_C5_RESIDUAL_GRU_NOPLANT_V1')",
        "strcmp(char(release.schema),'" + SCHEMA + "')",
        "ablation prepare schema",
    )
    start = text.index("weightsPath=char(binding.weights_mat_path);w=load(weightsPath);")
    end = text.index("opts.no_plant_boundary_check=preflightRelease;", start) + len("opts.no_plant_boundary_check=preflightRelease;")
    text = text[:start] + """weightsPath=char(binding.weights_mat_path);
assert(~logical(release.position_residual_gru.enabled)&& ...
    strcmpi(sha256_file(weightsPath),char(release.weights_sha256))&& ...
    strcmpi(char(modelManifest.weights_mat_sha256),char(release.weights_sha256))&& ...
    strcmp(char(modelManifest.fold_id),char(binding.fold_id)), ...
    'NoPositionGRU:ReferenceWeights','Fold weights are hash-bound for provenance only; do not load or evaluate them.');
assert(~isfield(opts.stage1_position_runtime,'residual_gru'), ...
    'NoPositionGRU:Runtime','Do not pass a residual-GRU runtime field in this ablation.');
opts.no_plant_boundary_check=preflightRelease;""" + text[end:]
    prepare.write_text(text, encoding="utf-8", newline="\n")

    no_plant = target / "candidate_runner_work/matlab/runtime/run_train_pair_preflight_no_plant.m"
    text = no_plant.read_text(encoding="utf-8")
    text = patch_one(
        text,
        "parity=verify_train_oof_fold_matlab_parity(studyRoot);",
        """parity=struct('schema','POSITION_GRU_REFERENCE_ONLY_PARITY_NOT_RUN_V1', ...
    'status','SKIPPED_DISABLED_MODEL_NOT_LOADED','position_residual_gru_weights_deserialized',false, ...
    'weights_sha256',char(release.weights_sha256),'fold_id',char(release.position_residual_gru.fold_id), ...
    'interpretation','Weights are lineage references only; no residual-GRU forward pass was run.');
write_json_new(fullfile(studyRoot,'audits','MATLAB_EVENTWISE_PARITY_v1.json'),parity);""",
        "skip disabled position-GRU model evaluation",
    )
    text = patch_one(
        text,
        "prepared=prepare_train_scene_no_plant();\nmarkerPath=prepared.marker_path;",
        """prepared=prepare_train_scene_no_plant();
assert(~isfield(prepared.opts.stage1_position_runtime,'residual_gru'), ...
    'NoPositionGRU:Runtime','Position residual GRU must be absent from the prepared runtime.');
dual=prepared.opts.stage1_position_runtime.applied_acceleration_dual_notch;
assert(logical(dual.enabled)&&isequal(double(dual.centers_hz(:)),[2.2;3.2])&& ...
    isequal(double(dual.quality_factor_each(:)),[4;4])&& ...
    abs(double(dual.sample_rate_hz)-100)<1e-12&&abs(double(dual.action_limit_mps2)-3)<1e-12, ...
    'NoPositionGRU:Filter','The fixed W09 dual-notch contract changed.');
markerPath=prepared.marker_path;""",
        "no-Plant runtime ablation assertions",
    )
    text = patch_one(
        text,
        "'inertia_reconstruction_enabled',false,'attempt_markers',0,'first_plant_step_markers',0, ...",
        "'inertia_reconstruction_enabled',false,'attempt_markers',0,'first_plant_step_markers',0, ...\n"
        "    'position_residual_gru_enabled',false,'residual_gru_runtime_field_present',false, ...\n"
        "    'position_residual_gru_weights_deserialized',false, ...\n"
        "    'no_position_gru_model_load_or_forward_call',true, ...\n"
        "    'frozen_C5_exact_options_match',true,'fixed_notch_centers_hz',[2.2 3.2], ...\n"
        "    'fixed_notch_quality_factor_each',[4 4],'fixed_notch_sample_rate_hz',100, ...",
        "ablation fields in no-Plant audit",
    )
    no_plant.write_text(text, encoding="utf-8", newline="\n")

    verifier = target / "verify_full_runner_no_plant_v1.py"
    text = verifier.read_text(encoding="utf-8")
    text = patch_one(
        text,
        "audit.get(\"first_plant_step_markers\") != 0):",
        "audit.get(\"first_plant_step_markers\") != 0 or\n"
        "            release.get(\"position_residual_gru\", {}).get(\"enabled\") is not False or\n"
        "            audit.get(\"position_residual_gru_enabled\") is not False or\n"
        "            audit.get(\"residual_gru_runtime_field_present\") is not False or\n"
        "            audit.get(\"position_residual_gru_weights_deserialized\") is not False or\n"
        "            audit.get(\"frozen_C5_exact_options_match\") is not True):",
        "residual-GRU ablation gate",
    )
    text = text.replace(
        '"hook_order": ["final C5+residual-GRU action", "dual-notch update", "force hold assignment", "position_bs_step"],',
        '"hook_order": ["frozen C5 action (position residual GRU absent)", "dual-notch update", "force hold assignment", "position_bs_step"],',
    )
    text = text.replace(
        '    prepare_text = PREPARE.read_text(encoding="utf-8")\n',
        '    prepare_text = PREPARE.read_text(encoding="utf-8")\n'
        '    no_plant_text = (HERE / "candidate_runner_work/matlab/runtime/run_train_pair_preflight_no_plant.m").read_text(encoding="utf-8")\n'
        '    if ("w=load(weightsPath)" in prepare_text or "opts.stage1_position_runtime.residual_gru=" in prepare_text or\n'
        '            "verify_train_oof_fold_matlab_parity(studyRoot)" in no_plant_text):\n'
        '        raise RuntimeError("Disabled position GRU must remain hash-reference-only; no load or forward parity.")\n',
    )
    text = text.replace('"status": "PASS_FULL_RUNNER_NOPLANT_BOUNDARY_AND_HOOK_ORDER",',
                        '"status": "PASS_FULL_RUNNER_NOPLANT_BOUNDARY_HOOK_ORDER_AND_NO_POSITION_GRU",')
    text = patch_one(
        text,
        '"frozen_replay_status_preserved": "FAIL_FIXED_FROZEN_REPLAY",',
        '"position_residual_gru_loaded": False,\n        "position_residual_gru_runtime_field_present": False,\n'
        '        "position_residual_gru_weights_deserialized": False,\n'
        '        "no_position_gru_model_load_or_forward_call": True,\n'
        '        "frozen_C5_exact_options_match": True,\n        "frozen_replay_status_preserved": "FAIL_FIXED_FROZEN_REPLAY",',
        "no-position-GRU static audit fields",
    )
    verifier.write_text(text, encoding="utf-8", newline="\n")


def build(arm: str) -> None:
    template = TEMPLATES[arm]
    scene = SCENES[arm]
    study_id = f"{ID_ROOT}_{arm}_noPlant_v1"
    target = HERE / arm
    old_id = json.loads((template / "RELEASE.json").read_text(encoding="utf-8-sig"))["study_id"]
    if target.exists():
        raise RuntimeError(f"Refusing to reuse {target}")
    shutil.copytree(template / "candidate_runner_work", target / "candidate_runner_work")
    for name in ("audits", "runs", "references", "matlab"):
        (target / name).mkdir()
    prefilter = PREFILTERS[arm]
    for name in ("TRAIN_SCENE_BINDING_v1.json", "OOF_FOLD_MODEL_MANIFEST_v1.json",
                 "OOF_HOLDOUT_CHECKPOINT_v1.pt", "MATLAB_EVENTWISE_PARITY_INPUTS_v1.mat",
                 "MATLAB_EVENTWISE_PARITY_INPUTS_v1.json"):
        shutil.copy2(template / name, target / name)
    for name in ("position_compensation_dual_notch_init.m", "position_compensation_dual_notch_step.m",
                 "run_dual_notch_no_plant_parity_v1.m"):
        src = template / "matlab" / name
        if not src.is_file():
            src = TEMPLATE_T1 / "matlab" / name
        shutil.copy2(src, target / "matlab" / name)
    for name in ("DUAL_NOTCH_EVENTWISE_PARITY_INPUTS_v1.mat", "DUAL_NOTCH_EVENTWISE_PARITY_INPUTS_v1.json"):
        shutil.copy2(TEMPLATE_T1 / name, target / name)
    meta_path = target / "DUAL_NOTCH_EVENTWISE_PARITY_INPUTS_v1.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8-sig"))
    meta["study_id"] = study_id
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    shutil.copy2(HERE / "ABLATION_PROTOCOL_v1.json", target / "ABLATION_PROTOCOL_v1.json")
    protocol = {
        "schema": "POSITION_DUAL_NOTCH_NO_POSITION_RESIDUAL_GRU_NOPLANT_PROTOCOL_V1",
        "study_id": study_id,
        "entry_reason": {"prior_frozen_replay_status": "FAIL_FIXED_FROZEN_REPLAY"},
        "diagnostic_baseline_measured": {},
        "parity_contract": {"max_abs_action_error_mps2": 1e-10, "max_abs_coefficient_error": 1e-12},
        "plant_calls_allowed": 0, "plant_calls_made": 0,
        "TEST_read": False, "VAL_read": False, "inertia_reconstruction_enabled": False,
        "position_residual_gru_enabled": False, "position_residual_gru_weights_deserialized": False,
    }
    (target / "DIAGNOSTIC_PROTOCOL_v1.json").write_text(json.dumps(protocol, indent=2) + "\n", encoding="utf-8")
    shutil.copy2(template / "RUNNER_INTEGRATION_CONTRACT_v1.json", target / "RUNNER_INTEGRATION_CONTRACT_v1.json")
    contract_path = target / "RUNNER_INTEGRATION_CONTRACT_v1.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8-sig"))
    contract.update({"study_id": study_id,
                     "isolated_runner_copy_path": str((target / "candidate_runner_work/matlab/runtime/run_mlp15_dev72_closed_loop.m").resolve()),
                     "original_runner_modified": False,
                     "position_residual_gru_enabled": False,
                     "exact_options_check_preserved": True})
    contract_path.write_text(json.dumps(contract, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    shutil.copy2(HERE / "validate_no_residual_gru_raw_v1.py", target / "validate_no_residual_gru_raw_v1.py")
    shutil.copy2(template / "verify_full_runner_no_plant_v1.py", target / "verify_full_runner_no_plant_v1.py")
    binding = json.loads((target / "TRAIN_SCENE_BINDING_v1.json").read_text(encoding="utf-8-sig"))
    baseline = json.loads((prefilter / "audits/TRAIN_SINGLE_SCENE_PAIRED_SCORE_v1.json").read_text(encoding="utf-8-sig"))
    for source, destination in (
        (prefilter / "audits/TRAIN_SINGLE_SCENE_PAIRED_SCORE_v1.json", target / "references/ORIGINAL_CANDIDATE_SCORE_v1.json"),
        (TEMPLATE_T1 / "MATLAB_NOPLANT_PARITY_v1.json", target / "references/DUAL_NOTCH_HELPER_PARITY_BOTH_SCENES_v1.json"),
    ):
        shutil.copy2(source, destination)
    protocol["diagnostic_baseline_measured"] = {
        "Q_m": baseline["methods"]["candidate"]["Q_m"],
        "task_SO3_rad": baseline["methods"]["candidate"]["task_SO3_rad"],
        "inner_SO3_rad": baseline["methods"]["candidate"]["inner_SO3_rad"],
    }
    (target / "DIAGNOSTIC_PROTOCOL_v1.json").write_text(json.dumps(protocol, indent=2) + "\n", encoding="utf-8")

    patch_study(arm, target, study_id, old_id)
    runner = target / "candidate_runner_work/matlab/runtime/run_mlp15_dev72_closed_loop.m"
    prepare = target / "candidate_runner_work/matlab/runtime/prepare_train_scene_no_plant.m"
    no_plant = target / "candidate_runner_work/matlab/runtime/run_train_pair_preflight_no_plant.m"
    release = json.loads((template / "RELEASE.json").read_text(encoding="utf-8-sig"))
    release.update({
        "schema": SCHEMA, "study_id": study_id, "status": "PREPARED_NO_PLANT_PENDING_ROOT_AUDIT",
        "authorized_Plant_calls": 0, "Plant_calls": 0, "potential_budget_calls": 0,
        "source_lock_path": str((target / "SOURCE_LOCK_NO_PLANT_v1.json").resolve()),
        "train_scene_binding_path": str((target / "TRAIN_SCENE_BINDING_v1.json").resolve()),
        "train_scene_binding_sha256": sha(target / "TRAIN_SCENE_BINDING_v1.json"),
        "model_manifest_path": str((target / "OOF_FOLD_MODEL_MANIFEST_v1.json").resolve()),
        "model_manifest_sha256": sha(target / "OOF_FOLD_MODEL_MANIFEST_v1.json"),
        "parity_inputs_mat_path": str((target / "MATLAB_EVENTWISE_PARITY_INPUTS_v1.mat").resolve()),
        "parity_inputs_mat_sha256": sha(target / "MATLAB_EVENTWISE_PARITY_INPUTS_v1.mat"),
        "parity_inputs_json_path": str((target / "MATLAB_EVENTWISE_PARITY_INPUTS_v1.json").resolve()),
        "parity_inputs_json_sha256": sha(target / "MATLAB_EVENTWISE_PARITY_INPUTS_v1.json"),
        "candidate_runner_closed_loop_sha256": sha(runner), "prepare_wrapper_sha256": sha(prepare),
        "no_plant_wrapper_sha256": sha(no_plant),
        "eventwise_parity_script_sha256": sha(target / "candidate_runner_work/matlab/runtime/verify_train_oof_fold_matlab_parity.m"),
        "dual_notch_helper_parity_input_sha256": sha(target / "DUAL_NOTCH_EVENTWISE_PARITY_INPUTS_v1.mat"),
        "dual_notch_helper_parity_metadata_sha256": sha(target / "DUAL_NOTCH_EVENTWISE_PARITY_INPUTS_v1.json"),
        "position_residual_gru": {**release["position_residual_gru"], "enabled": False,
                                   "disabled_for_ablation": True, "runtime_field_present": False,
                                   "weights_deserialized": False},
        "position_residual_gru_enabled": False,
        "position_residual_gru_weights_deserialized": False,
        "exact_options_check_preserved": True,
        "ablation_protocol_path": str((target / "ABLATION_PROTOCOL_v1.json").resolve()),
        "ablation_protocol_sha256": sha(target / "ABLATION_PROTOCOL_v1.json"),
        "no_residual_raw_validator_path": str((target / "validate_no_residual_gru_raw_v1.py").resolve()),
        "no_residual_raw_validator_sha256": sha(target / "validate_no_residual_gru_raw_v1.py"),
        "TEST_read": False, "VAL_data_read": False, "inertia_reconstruction_enabled": False,
        "Plant_truth_deployment_input": False, "frozen_replay_status": "FAIL_FIXED_FROZEN_REPLAY",
    })
    release["authorized_scenes"] = [scene]
    release["fixed_scene_id"] = scene
    release["source_split"] = "TRAIN_C5_24 only; canonical DEV ID"
    (target / "RELEASE.json").write_text(json.dumps(release, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lock_paths = list((target / "candidate_runner_work/matlab").rglob("*.m"))
    lock_paths += list((target / "candidate_runner_work/matlab/models").glob("*.mat"))
    lock_paths += list((target / "matlab").glob("*.m"))
    lock_paths += [target / name for name in (
        "TRAIN_SCENE_BINDING_v1.json", "OOF_FOLD_MODEL_MANIFEST_v1.json", "OOF_HOLDOUT_CHECKPOINT_v1.pt",
        "MATLAB_EVENTWISE_PARITY_INPUTS_v1.mat", "MATLAB_EVENTWISE_PARITY_INPUTS_v1.json",
        "DUAL_NOTCH_EVENTWISE_PARITY_INPUTS_v1.mat", "DUAL_NOTCH_EVENTWISE_PARITY_INPUTS_v1.json",
        "DIAGNOSTIC_PROTOCOL_v1.json", "ABLATION_PROTOCOL_v1.json", "RUNNER_INTEGRATION_CONTRACT_v1.json",
        "verify_full_runner_no_plant_v1.py", "validate_no_residual_gru_raw_v1.py")]
    lock_paths.append(HERE / "prepare_ablation_no_plant_v1.py")
    lock_paths += [target / "references/ORIGINAL_CANDIDATE_SCORE_v1.json",
                   target / "references/DUAL_NOTCH_HELPER_PARITY_BOTH_SCENES_v1.json"]
    # Bind every TRAIN lineage file named by the selected scene record; no TEST or VAL sources are used.
    for key, value in binding.items():
        if key.endswith("_path") and isinstance(value, str):
            p = Path(value)
            if p.is_file():
                lock_paths.append(p)
    unique = sorted({p.resolve(strict=True) for p in lock_paths if p.is_file()}, key=lambda p: str(p).lower())
    lock = {"schema": "POSITION_DUAL_NOTCH_NO_POSITION_RESIDUAL_GRU_SOURCE_LOCK_NOPLANT_V1",
            "study_id": study_id,
            "files": [{"path": str(p), "relative_path": os.path.relpath(p, target.resolve()).replace(os.sep, "/"), "sha256": sha(p)} for p in unique],
            "Plant_calls": 0, "TEST_read": False, "VAL_read": False}
    lock_path = target / "SOURCE_LOCK_NO_PLANT_v1.json"
    lock_path.write_text(json.dumps(lock, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    release["source_lock_sha256"] = sha(lock_path)
    release["source_lock_file_count"] = len(unique)
    (target / "RELEASE.json").write_text(json.dumps(release, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"arm": arm, "study": str(target.resolve()), "scene_id": scene,
                      "weights_sha256": release["weights_sha256"], "source_lock_sha256": sha(lock_path),
                      "locked_files": len(unique), "Plant_calls": 0,
                      "position_residual_gru_enabled": release["position_residual_gru"]["enabled"],
                      "dual_notch_centers_hz": release["applied_acceleration_dual_notch"]["centers_hz"],
                      "dual_notch_q_each": release["applied_acceleration_dual_notch"]["quality_factor_each"]}, indent=2))


def main() -> None:
    build("T1")
    build("T3")


if __name__ == "__main__":
    main()
