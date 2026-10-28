#!/usr/bin/env python3
"""Freeze a separate one-call T1 W09 release from the passing no-Plant study."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
STUDY_ID = "position_compensation_dual_notch_train_diag_single_call_T1_v1"
SINGLE_SCHEMA = "DL1018_POSITION_C5_DUAL_NOTCH_SINGLE_CALL_V1"
TARGET = ROOT / "experiments/dl_attitude_replacement_20261028" / STUDY_ID
SOURCE_T1 = ROOT / "experiments/dl_attitude_replacement_20261028/position_dc_penalty_oof_train_pair_preflight_W09_T1_C10_attempt014_v1"
NO_PLANT = HERE
REPLAY = ROOT / "experiments/dl_attitude_replacement_20261028/position_compensation_dual_notch_train_replay_v1"
LOCK = TARGET / "SOURCE_LOCK_SINGLE_CALL_v1.json"
RELEASE = TARGET / "RELEASE.json"
RUNNER = TARGET / "candidate_runner_work/matlab/runtime/run_mlp15_dev72_closed_loop.m"
PREPARE = TARGET / "candidate_runner_work/matlab/runtime/prepare_train_scene_no_plant.m"
SINGLE_WRAPPER = TARGET / "candidate_runner_work/matlab/runtime/run_train_scene_single_attempt.m"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def replace_required(text: str, old: str, new: str, label: str, expected: int = 1) -> str:
    count = text.count(old)
    if count != expected:
        raise RuntimeError(f"Expected {expected} {label} anchors, found {count}.")
    return text.replace(old, new)


def patch_runner() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    no_plant_id = "position_compensation_dual_notch_train_diag_online_noPlant_v1"
    text = text.replace(no_plant_id, STUDY_ID)
    text = replace_required(
        text,
        "strcmp(releaseSchema,'DL1018_POSITION_C5_RESIDUAL_GRU_NOPLANT_V1')",
        "any(strcmp(releaseSchema,{'DL1018_POSITION_C5_RESIDUAL_GRU_NOPLANT_V1','" + SINGLE_SCHEMA + "'}))",
        "dual/residual release schema",
        expected=2,
    )
    text = replace_required(
        text,
        "dualNotchCandidateReleaseOk=dualNotchNoPlantReleaseOk;",
        """dualNotchSinglePlantReleaseOk=dualNotchIdentityOk&& ...
        strcmp(char(field_or(release,'status','')),'RELEASED')&& ...
        double(field_or(release,'authorized_Plant_calls',-1))==1&& ...
        double(field_or(release,'Plant_calls',-1))==1&&~noPlantBoundaryRequested;
    dualNotchCandidateReleaseOk=dualNotchNoPlantReleaseOk||dualNotchSinglePlantReleaseOk;""",
        "single-call dual-notch release gate",
    )
    guard = """    if dualNotchNoPlantReleaseOk
        assert(noPlantBoundaryRequested,'DualNotch:NoPlantOnly','Prepared release must stop before the Plant loop.');
    elseif dualNotchSinglePlantReleaseOk
        assert(~noPlantBoundaryRequested,'DualNotch:PlantRelease','Single-call release must enter the Plant runner.');
        opts.r2e_first_plant_step_marker=fullfile(fileparts(markerPath),'first_plant_step.marker');
    end
"""
    text = replace_required(
        text,
        "    formalRbfBaseline=logical(field_or(opts,'formal_rbf_baseline',false));\n",
        guard + "    formalRbfBaseline=logical(field_or(opts,'formal_rbf_baseline',false));\n",
        "Plant marker guard",
    )
    RUNNER.write_text(text, encoding="utf-8", newline="\n")

    prepare = PREPARE.read_text(encoding="utf-8")
    prepare = prepare.replace(no_plant_id, STUDY_ID)
    prepare = replace_required(
        prepare,
        "strcmp(char(release.schema),'DL1018_POSITION_C5_RESIDUAL_GRU_NOPLANT_V1')",
        "any(strcmp(char(release.schema),{'DL1018_POSITION_C5_RESIDUAL_GRU_NOPLANT_V1','" + SINGLE_SCHEMA + "'}))",
        "prepare release schema",
    )
    PREPARE.write_text(prepare, encoding="utf-8", newline="\n")

    wrapper = SINGLE_WRAPPER.read_text(encoding="utf-8")
    wrapper = wrapper.replace("position_dc_penalty_oof_train_pair_preflight_W09_T1_C10_attempt014_v1", STUDY_ID)
    wrapper = replace_required(
        wrapper,
        "strcmp(char(release.schema),'DL1018_POSITION_C5_RESIDUAL_GRU_NOPLANT_V1')",
        "strcmp(char(release.schema),'" + SINGLE_SCHEMA + "')",
        "single-call release schema",
    )
    SINGLE_WRAPPER.write_text(wrapper, encoding="utf-8", newline="\n")


def main() -> None:
    if TARGET.exists():
        raise RuntimeError(f"Refusing to reuse an existing single-call study: {TARGET}")
    no_plant_audit = NO_PLANT / "audits/NO_PLANT_PREFLIGHT_v1.json"
    no_plant_static_audit = NO_PLANT / "audits/DUAL_NOTCH_FULL_RUNNER_NO_PLANT_SOURCE_AUDIT_v1.json"
    prior = json.loads(no_plant_audit.read_text(encoding="utf-8-sig"))
    static = json.loads(no_plant_static_audit.read_text(encoding="utf-8-sig"))
    if prior.get("status") != "PASS" or prior.get("Plant_calls") != 0 or \
            static.get("status") != "PASS_FULL_RUNNER_NOPLANT_BOUNDARY_AND_HOOK_ORDER" or static.get("Plant_calls") != 0:
        raise RuntimeError("The frozen no-Plant gate is not a complete zero-call PASS.")

    shutil.copytree(NO_PLANT / "candidate_runner_work", TARGET / "candidate_runner_work")
    (TARGET / "audits").mkdir(parents=True)
    (TARGET / "references").mkdir()
    (TARGET / "runs").mkdir()
    for name in ("TRAIN_SCENE_BINDING_v1.json", "OOF_FOLD_MODEL_MANIFEST_v1.json",
                 "OOF_HOLDOUT_CHECKPOINT_v1.pt", "MATLAB_EVENTWISE_PARITY_INPUTS_v1.mat",
                 "MATLAB_EVENTWISE_PARITY_INPUTS_v1.json"):
        shutil.copy2(SOURCE_T1 / name, TARGET / name)
    for name, src in (
        ("ORIGINAL_CANDIDATE_FROZEN_SCORE_v1.json", SOURCE_T1 / "audits/TRAIN_SINGLE_SCENE_PAIRED_SCORE_v1.json"),
        ("W09_FIXED_NOTCH_FROZEN_REPLAY_v1.json", REPLAY / "TRAIN_FROZEN_DUAL_NOTCH_REPLAY_v1.json"),
        ("PRIOR_NO_PLANT_PREFLIGHT_v1.json", no_plant_audit),
        ("PRIOR_FULL_RUNNER_NO_PLANT_SOURCE_AUDIT_v1.json", no_plant_static_audit),
    ):
        shutil.copy2(src, TARGET / "references" / name)
    shutil.copy2(HERE / "SINGLE_CALL_PLAN_T1_v1.json", TARGET / "SINGLE_CALL_PLAN_T1_v1.json")
    shutil.copy2(HERE / "score_single_call_diagnostic_T1_v1.py", TARGET / "score_single_call_diagnostic_T1_v1.py")
    shutil.copy2(HERE / "prepare_single_call_study_T1_v1.py", TARGET / "prepare_single_call_study_T1_v1.py")
    shutil.copy2(HERE / "DIAGNOSTIC_PROTOCOL_v1.json", TARGET / "references/DIAGNOSTIC_PROTOCOL_NOPLANT_v1.json")
    contract_path = TARGET / "RUNNER_INTEGRATION_CONTRACT_v1.json"
    shutil.copy2(HERE / "RUNNER_INTEGRATION_CONTRACT_v1.json", contract_path)
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["study_id"] = STUDY_ID
    contract["isolated_runner_copy_path"] = str((TARGET / "candidate_runner_work/matlab/runtime/run_mlp15_dev72_closed_loop.m").resolve())
    contract["original_runner_modified"] = False
    contract_path.write_text(json.dumps(contract, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    shutil.copy2(HERE / "MATLAB_NOPLANT_PARITY_v1.json", TARGET / "PRIOR_MATLAB_HELPER_PARITY_NOPLANT_v1.json")

    plan_path = TARGET / "SINGLE_CALL_PLAN_T1_v1.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    baseline_score = SOURCE_T1 / "audits/TRAIN_SINGLE_SCENE_PAIRED_SCORE_v1.json"
    plan["frozen_score"]["baseline_score_sha256"] = sha256(baseline_score)
    plan["frozen_score"]["frozen_score_source_sha256"] = sha256(
        ROOT / "experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_full72_v1/audits/score_full72_candidate_v1.py")
    plan["entry_reason"]["prior_no_plant_audit_sha256"] = sha256(no_plant_audit)
    binding_for_spectrum = json.loads((TARGET / "TRAIN_SCENE_BINDING_v1.json").read_text(encoding="utf-8-sig"))
    replay_for_spectrum = json.loads((TARGET / "references/W09_FIXED_NOTCH_FROZEN_REPLAY_v1.json").read_text(encoding="utf-8-sig"))
    pre_row_for_spectrum = next(row for row in replay_for_spectrum["results"] if row["scene_id"] == binding_for_spectrum["selected_scene_id"])
    scorer_spec = importlib.util.spec_from_file_location("fixed_single_call_score", HERE / "score_single_call_diagnostic_T1_v1.py")
    if scorer_spec is None or scorer_spec.loader is None:
        raise RuntimeError("Cannot load the frozen W09 spectrum calculation.")
    scorer_module = importlib.util.module_from_spec(scorer_spec)
    scorer_spec.loader.exec_module(scorer_module)
    constants = json.loads((ROOT / "experiments/dl_attitude_replacement_20261026/mlp15_composite_dev_v3/RELEASE.json").read_text(encoding="utf-8-sig"))
    max_tilt = float(constants["max_tilt_rad"])
    baseline_paths = {
        "B": Path(binding_for_spectrum["b72_scoring_raw_path"]),
        "C5": Path(binding_for_spectrum["c5_raw_path"]),
        "parent_GRU": Path(binding_for_spectrum["parent_raw_path"]),
        "candidate_pre_dual_notch": Path(pre_row_for_spectrum["candidate_raw_path"]),
    }
    plan["measured_baseline_spectra"] = {
        name: scorer_module.spectrum_for_raw(path, max_tilt) for name, path in baseline_paths.items()
    }
    plan["measured_baseline_raw_sha256"] = {
        "B": binding_for_spectrum["b72_scoring_raw_sha256"],
        "C5": binding_for_spectrum["c5_raw_sha256"],
        "parent_GRU": binding_for_spectrum["parent_raw_sha256"],
        "candidate_pre_dual_notch": pre_row_for_spectrum["candidate_raw_sha256"],
    }
    plan_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    patch_runner()

    # Freeze a single-use release tied to the completed, independently audited no-Plant gate.
    release = json.loads((NO_PLANT / "RELEASE.json").read_text(encoding="utf-8-sig"))
    release.update({
        "schema": SINGLE_SCHEMA,
        "study_id": STUDY_ID,
        "status": "RELEASED",
        "authorized_Plant_calls": 1,
        "Plant_calls": 1,
        "potential_budget_calls": 1,
        "one_attempt_only": True,
        "source_lock_path": str(LOCK.resolve()),
        "train_scene_binding_path": str((TARGET / "TRAIN_SCENE_BINDING_v1.json").resolve()),
        "train_scene_binding_sha256": sha256(TARGET / "TRAIN_SCENE_BINDING_v1.json"),
        "model_manifest_path": str((TARGET / "OOF_FOLD_MODEL_MANIFEST_v1.json").resolve()),
        "model_manifest_sha256": sha256(TARGET / "OOF_FOLD_MODEL_MANIFEST_v1.json"),
        "parity_inputs_mat_path": str((TARGET / "MATLAB_EVENTWISE_PARITY_INPUTS_v1.mat").resolve()),
        "parity_inputs_mat_sha256": sha256(TARGET / "MATLAB_EVENTWISE_PARITY_INPUTS_v1.mat"),
        "parity_inputs_json_path": str((TARGET / "MATLAB_EVENTWISE_PARITY_INPUTS_v1.json").resolve()),
        "parity_inputs_json_sha256": sha256(TARGET / "MATLAB_EVENTWISE_PARITY_INPUTS_v1.json"),
        "candidate_runner_closed_loop_sha256": sha256(RUNNER),
        "prepare_wrapper_sha256": sha256(PREPARE),
        "single_attempt_wrapper_sha256": sha256(SINGLE_WRAPPER),
        "prior_no_plant_preflight_path": str(no_plant_audit.resolve()),
        "prior_no_plant_preflight_sha256": sha256(no_plant_audit),
        "prior_full_runner_no_plant_source_audit_path": str(no_plant_static_audit.resolve()),
        "prior_full_runner_no_plant_source_audit_sha256": sha256(no_plant_static_audit),
        "single_call_plan_path": str(plan_path.resolve()),
        "single_call_plan_sha256": sha256(plan_path),
        "baseline_score_path": str(baseline_score.resolve()),
        "baseline_score_sha256": sha256(baseline_score),
        "single_call_scorer_path": str((TARGET / "score_single_call_diagnostic_T1_v1.py").resolve()),
        "single_call_scorer_sha256": sha256(TARGET / "score_single_call_diagnostic_T1_v1.py"),
        "TEST_read": False,
        "VAL_data_read": False,
        "inertia_reconstruction_enabled": False,
        "Plant_truth_deployment_input": False,
        "diagnostic_only": True,
        "frozen_replay_status": "FAIL_FIXED_FROZEN_REPLAY",
    })

    binding = json.loads((TARGET / "TRAIN_SCENE_BINDING_v1.json").read_text(encoding="utf-8-sig"))
    replay = json.loads((TARGET / "references/W09_FIXED_NOTCH_FROZEN_REPLAY_v1.json").read_text(encoding="utf-8-sig"))
    pre_row = next(row for row in replay["results"] if row["scene_id"] == binding["selected_scene_id"])
    locked_paths = []
    locked_paths.extend(sorted((TARGET / "candidate_runner_work/matlab").rglob("*.m")))
    locked_paths.extend(sorted((TARGET / "candidate_runner_work/matlab/models").glob("*.mat")))
    locked_paths.extend([
        TARGET / "TRAIN_SCENE_BINDING_v1.json", TARGET / "OOF_FOLD_MODEL_MANIFEST_v1.json",
        TARGET / "OOF_HOLDOUT_CHECKPOINT_v1.pt", TARGET / "MATLAB_EVENTWISE_PARITY_INPUTS_v1.mat",
        TARGET / "MATLAB_EVENTWISE_PARITY_INPUTS_v1.json", plan_path,
        TARGET / "score_single_call_diagnostic_T1_v1.py", TARGET / "prepare_single_call_study_T1_v1.py",
        TARGET / "references/DIAGNOSTIC_PROTOCOL_NOPLANT_v1.json", TARGET / "RUNNER_INTEGRATION_CONTRACT_v1.json",
        TARGET / "references/ORIGINAL_CANDIDATE_FROZEN_SCORE_v1.json",
        TARGET / "references/W09_FIXED_NOTCH_FROZEN_REPLAY_v1.json",
        TARGET / "references/PRIOR_NO_PLANT_PREFLIGHT_v1.json",
        TARGET / "references/PRIOR_FULL_RUNNER_NO_PLANT_SOURCE_AUDIT_v1.json",
        TARGET / "PRIOR_MATLAB_HELPER_PARITY_NOPLANT_v1.json",
        no_plant_audit, no_plant_static_audit, baseline_score,
        pre_row_path := Path(pre_row["candidate_raw_path"]),
        pre_row_path.with_name("run_status.json"),
        Path(binding["b72_scoring_raw_path"]), Path(binding["b72_scoring_status_path"]),
        Path(binding["c5_raw_path"]), Path(binding["c5_status_path"]),
        Path(binding["parent_raw_path"]), Path(binding["parent_status_path"]),
        ROOT / "experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_full72_v1/audits/score_full72_candidate_v1.py",
        ROOT / "experiments/dl_attitude_replacement_20261026/mlp15_composite_dev_v3/RELEASE.json",
    ])
    unique_paths = sorted({p.resolve(strict=True) for p in locked_paths if p.is_file()}, key=lambda p: str(p).lower())
    lock = {
        "schema": "POSITION_COMPENSATION_DUAL_NOTCH_SINGLE_CALL_SOURCE_LOCK_V1",
        "study_id": STUDY_ID,
        "files": [{"path": str(path), "relative_path": os.path.relpath(path, TARGET.resolve()).replace(os.sep, "/"), "sha256": sha256(path)} for path in unique_paths],
        "Plant_calls_authorized": 1,
        "TEST_read": False,
        "VAL_read": False,
    }
    LOCK.write_text(json.dumps(lock, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    release["source_lock_sha256"] = sha256(LOCK)
    release["source_lock_file_count"] = len(unique_paths)
    RELEASE.write_text(json.dumps(release, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"study": str(TARGET.resolve()), "release_status": release["status"],
                      "authorized_Plant_calls": release["authorized_Plant_calls"],
                      "prior_no_plant_sha256": release["prior_no_plant_preflight_sha256"],
                      "runner_sha256": sha256(RUNNER), "source_lock_sha256": sha256(LOCK),
                      "source_lock_file_count": len(unique_paths)}, indent=2))


if __name__ == "__main__":
    main()
