#!/usr/bin/env python3
"""Freeze an isolated one-call T3 study from its passing no-Plant copy."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
STUDY_ID = "position_compensation_dual_notch_train_diag_single_call_T3_v1"
SCENE_ID = "DL1018_DEV_T3_C09_W09"
SINGLE_SCHEMA = "DL1018_POSITION_C5_DUAL_NOTCH_SINGLE_CALL_V1"
TARGET = ROOT / "experiments/dl_attitude_replacement_20261028" / STUDY_ID
SOURCE = ROOT / "experiments/dl_attitude_replacement_20261028/position_dc_penalty_oof_train_pair_preflight_W09_T3_C09_attempt015_v1"
NO_PLANT = HERE
T1_TEMPLATE = ROOT / "experiments/dl_attitude_replacement_20261028/position_compensation_dual_notch_train_diag_online_noPlant_v1"
REPLAY = ROOT / "experiments/dl_attitude_replacement_20261028/position_compensation_dual_notch_train_replay_v1"
LOCK = TARGET / "SOURCE_LOCK_SINGLE_CALL_v1.json"
RELEASE = TARGET / "RELEASE.json"
RUNNER = TARGET / "candidate_runner_work/matlab/runtime/run_mlp15_dev72_closed_loop.m"
PREPARE = TARGET / "candidate_runner_work/matlab/runtime/prepare_train_scene_no_plant.m"
WRAPPER = TARGET / "candidate_runner_work/matlab/runtime/run_train_scene_single_attempt.m"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def replace_once(text: str, old: str, new: str, label: str, count: int = 1) -> str:
    found = text.count(old)
    if found != count:
        raise RuntimeError(f"Expected {count} {label} anchors; found {found}.")
    return text.replace(old, new)


def patch_runner() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    text = text.replace("position_compensation_dual_notch_train_diag_online_noPlant_T3_v1", STUDY_ID)
    text = replace_once(
        text,
        "strcmp(releaseSchema,'DL1018_POSITION_C5_RESIDUAL_GRU_NOPLANT_V1')",
        "any(strcmp(releaseSchema,{'DL1018_POSITION_C5_RESIDUAL_GRU_NOPLANT_V1','" + SINGLE_SCHEMA + "'}))",
        "dual/residual release schema", 2,
    )
    text = replace_once(
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
    text = replace_once(
        text,
        "    formalRbfBaseline=logical(field_or(opts,'formal_rbf_baseline',false));\n",
        guard + "    formalRbfBaseline=logical(field_or(opts,'formal_rbf_baseline',false));\n",
        "Plant marker guard",
    )
    RUNNER.write_text(text, encoding="utf-8", newline="\n")

    text = PREPARE.read_text(encoding="utf-8")
    text = text.replace("position_compensation_dual_notch_train_diag_online_noPlant_T3_v1", STUDY_ID)
    text = replace_once(
        text,
        "strcmp(char(release.schema),'DL1018_POSITION_C5_RESIDUAL_GRU_NOPLANT_V1')",
        "any(strcmp(char(release.schema),{'DL1018_POSITION_C5_RESIDUAL_GRU_NOPLANT_V1','" + SINGLE_SCHEMA + "'}))",
        "prepare release schema",
    )
    PREPARE.write_text(text, encoding="utf-8", newline="\n")

    text = WRAPPER.read_text(encoding="utf-8")
    text = text.replace("position_dc_penalty_oof_train_pair_preflight_W09_T1_C10_attempt014_v1", STUDY_ID)
    text = replace_once(
        text,
        "strcmp(char(release.schema),'DL1018_POSITION_C5_RESIDUAL_GRU_NOPLANT_V1')",
        "strcmp(char(release.schema),'" + SINGLE_SCHEMA + "')",
        "single-call release schema",
    )
    WRAPPER.write_text(text, encoding="utf-8", newline="\n")


def main() -> None:
    if TARGET.exists():
        raise RuntimeError(f"Refusing to reuse a single-call study: {TARGET}")
    no_plant_audit = NO_PLANT / "audits/NO_PLANT_PREFLIGHT_v1.json"
    static_audit = NO_PLANT / "audits/DUAL_NOTCH_FULL_RUNNER_NO_PLANT_SOURCE_AUDIT_v1.json"
    prior = json.loads(no_plant_audit.read_text(encoding="utf-8-sig"))
    static = json.loads(static_audit.read_text(encoding="utf-8-sig"))
    if (prior.get("status") != "PASS" or prior.get("Plant_calls") != 0 or
            static.get("status") != "PASS_FULL_RUNNER_NOPLANT_BOUNDARY_AND_HOOK_ORDER" or
            static.get("Plant_calls") != 0 or prior.get("scene_id") != SCENE_ID):
        raise RuntimeError("T3 no-Plant and full-runner audits must both be zero-call PASS.")

    shutil.copytree(NO_PLANT / "candidate_runner_work", TARGET / "candidate_runner_work")
    for subdir in ("audits", "references", "runs"):
        (TARGET / subdir).mkdir(parents=True)
    for name in ("TRAIN_SCENE_BINDING_v1.json", "OOF_FOLD_MODEL_MANIFEST_v1.json",
                 "OOF_HOLDOUT_CHECKPOINT_v1.pt", "MATLAB_EVENTWISE_PARITY_INPUTS_v1.mat",
                 "MATLAB_EVENTWISE_PARITY_INPUTS_v1.json"):
        shutil.copy2(NO_PLANT / name, TARGET / name)
    baseline_score = SOURCE / "audits/TRAIN_SINGLE_SCENE_PAIRED_SCORE_v1.json"
    replay = REPLAY / "TRAIN_FROZEN_DUAL_NOTCH_REPLAY_v1.json"
    refs = {
        "ORIGINAL_CANDIDATE_FROZEN_SCORE_v1.json": baseline_score,
        "W09_FIXED_NOTCH_FROZEN_REPLAY_v1.json": replay,
        "PRIOR_NO_PLANT_PREFLIGHT_v1.json": no_plant_audit,
        "PRIOR_FULL_RUNNER_NO_PLANT_SOURCE_AUDIT_v1.json": static_audit,
    }
    for name, source in refs.items():
        shutil.copy2(source, TARGET / "references" / name)
    plan_path = TARGET / "SINGLE_CALL_PLAN_T3_v1.json"
    scorer_path = TARGET / "score_single_call_diagnostic_T3_v1.py"
    prep_path = TARGET / "prepare_single_call_study_T3_v1.py"
    shutil.copy2(T1_TEMPLATE / "SINGLE_CALL_PLAN_T1_v1.json", plan_path)
    scorer_text = (T1_TEMPLATE / "score_single_call_diagnostic_T1_v1.py").read_text(encoding="utf-8")
    scorer_text = scorer_text.replace("position_dc_penalty_oof_train_pair_preflight_W09_T1_C10_attempt014_v1",
                                      "position_dc_penalty_oof_train_pair_preflight_W09_T3_C09_attempt015_v1")
    scorer_text = scorer_text.replace("DL1018_DEV_T1_C10_W09", SCENE_ID)
    scorer_text = scorer_text.replace("SINGLE_CALL_PLAN_T1_v1", "SINGLE_CALL_PLAN_T3_v1")
    scorer_text = scorer_text.replace("DUAL_NOTCH_SINGLE_CALL_T1_SCORE_v1", "DUAL_NOTCH_SINGLE_CALL_T3_SCORE_v1")
    scorer_text = scorer_text.replace("POSITION_COMPENSATION_DUAL_NOTCH_SINGLE_CALL_T1_FROZEN_SCORE_V1",
                                      "POSITION_COMPENSATION_DUAL_NOTCH_SINGLE_CALL_T3_FROZEN_SCORE_V1")
    scorer_text = scorer_text.replace("PASS_T1_SINGLE_CALL_FALSIFIER", "PASS_T3_SINGLE_CALL_FALSIFIER")
    scorer_text = scorer_text.replace("FAIL_T1_SINGLE_CALL_FALSIFIER", "FAIL_T3_SINGLE_CALL_FALSIFIER")
    scorer_text = scorer_text.replace("One T1 W09", "One T3 W09")
    scorer_path.write_text(scorer_text, encoding="utf-8", newline="\n")
    shutil.copy2(HERE / "DIAGNOSTIC_PROTOCOL_v1.json", TARGET / "references/DIAGNOSTIC_PROTOCOL_NOPLANT_v1.json")
    shutil.copy2(HERE / "RUNNER_INTEGRATION_CONTRACT_v1.json", TARGET / "RUNNER_INTEGRATION_CONTRACT_v1.json")
    shutil.copy2(HERE / "DUAL_NOTCH_TRAIN_HELPER_PARITY_v1.json", TARGET / "PRIOR_MATLAB_HELPER_PARITY_NOPLANT_v1.json")
    contract_path = TARGET / "RUNNER_INTEGRATION_CONTRACT_v1.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["study_id"] = STUDY_ID
    contract["isolated_runner_copy_path"] = str(RUNNER.resolve())
    contract["original_runner_modified"] = False
    contract_path.write_text(json.dumps(contract, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    baseline = json.loads(baseline_score.read_text(encoding="utf-8-sig"))
    replay_data = json.loads(replay.read_text(encoding="utf-8-sig"))
    row = next(r for r in replay_data["results"] if r["scene_id"] == SCENE_ID)
    plan.update({"schema": "POSITION_COMPENSATION_DUAL_NOTCH_SINGLE_CALL_T3_PLAN_V1", "study_id": STUDY_ID})
    plan["scope"]["scene_id"] = SCENE_ID
    plan["entry_reason"]["why_one_closed_loop_diagnostic_is_authorized"] = (
        "T1's fixed-parameter diagnostic showed that the W09 mechanism can reduce both target bands. "
        "This is one independent same-W09 T3 scene replication with parameters and falsifier unchanged. "
        "The frozen replay still fails its low-band action limit (3.116% vs 2.0%); this call is diagnostic only, "
        "does not convert that failure to a pass, and makes no cross-wind claim."
    )
    plan["frozen_score"]["baseline_score_path"] = str(baseline_score.resolve())
    plan["frozen_score"]["baseline_score_sha256"] = sha(baseline_score)
    plan["measured_baseline_Q_task_inner"] = {
        name: {key: baseline["methods"][name][key] for key in ("Q_m", "task_SO3_rad", "inner_SO3_rad")}
        for name in ("B", "C5", "parent_GRU")
    }
    c = baseline["methods"]["candidate"]
    plan["measured_baseline_Q_task_inner"]["candidate_pre_dual_notch"] = {
        key: c[key] for key in ("Q_m", "task_SO3_rad", "inner_SO3_rad")
    }
    plan["measured_baseline_spectra"] = {}
    spec = importlib.util.spec_from_file_location("t3_frozen_score", scorer_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load the frozen T3 spectrum calculation.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    constants = json.loads((ROOT / "experiments/dl_attitude_replacement_20261026/mlp15_composite_dev_v3/RELEASE.json").read_text(encoding="utf-8-sig"))
    max_tilt = float(constants["max_tilt_rad"])
    binding = json.loads((TARGET / "TRAIN_SCENE_BINDING_v1.json").read_text(encoding="utf-8-sig"))
    raw_paths = {
        "B": Path(binding["b72_scoring_raw_path"]), "C5": Path(binding["c5_raw_path"]),
        "parent_GRU": Path(binding["parent_raw_path"]), "candidate_pre_dual_notch": Path(row["candidate_raw_path"]),
    }
    plan["measured_baseline_spectra"] = {name: module.spectrum_for_raw(path, max_tilt) for name, path in raw_paths.items()}
    plan["measured_baseline_raw_sha256"] = {
        "B": binding["b72_scoring_raw_sha256"], "C5": binding["c5_raw_sha256"],
        "parent_GRU": binding["parent_raw_sha256"], "candidate_pre_dual_notch": row["candidate_raw_sha256"],
    }
    plan_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    patch_runner()
    release = json.loads((NO_PLANT / "RELEASE.json").read_text(encoding="utf-8-sig"))
    release.update({
        "schema": SINGLE_SCHEMA, "study_id": STUDY_ID, "status": "RELEASED",
        "authorized_Plant_calls": 1, "Plant_calls": 1, "potential_budget_calls": 1,
        "one_attempt_only": True, "source_lock_path": str(LOCK.resolve()),
        "train_scene_binding_path": str((TARGET / "TRAIN_SCENE_BINDING_v1.json").resolve()),
        "train_scene_binding_sha256": sha(TARGET / "TRAIN_SCENE_BINDING_v1.json"),
        "model_manifest_path": str((TARGET / "OOF_FOLD_MODEL_MANIFEST_v1.json").resolve()),
        "model_manifest_sha256": sha(TARGET / "OOF_FOLD_MODEL_MANIFEST_v1.json"),
        "parity_inputs_mat_path": str((TARGET / "MATLAB_EVENTWISE_PARITY_INPUTS_v1.mat").resolve()),
        "parity_inputs_mat_sha256": sha(TARGET / "MATLAB_EVENTWISE_PARITY_INPUTS_v1.mat"),
        "parity_inputs_json_path": str((TARGET / "MATLAB_EVENTWISE_PARITY_INPUTS_v1.json").resolve()),
        "parity_inputs_json_sha256": sha(TARGET / "MATLAB_EVENTWISE_PARITY_INPUTS_v1.json"),
        "candidate_runner_closed_loop_sha256": sha(RUNNER), "prepare_wrapper_sha256": sha(PREPARE),
        "single_attempt_wrapper_sha256": sha(WRAPPER),
        "prior_no_plant_preflight_path": str(no_plant_audit.resolve()), "prior_no_plant_preflight_sha256": sha(no_plant_audit),
        "prior_full_runner_no_plant_source_audit_path": str(static_audit.resolve()),
        "prior_full_runner_no_plant_source_audit_sha256": sha(static_audit),
        "single_call_plan_path": str(plan_path.resolve()), "single_call_plan_sha256": sha(plan_path),
        "baseline_score_path": str(baseline_score.resolve()), "baseline_score_sha256": sha(baseline_score),
        "single_call_scorer_path": str(scorer_path.resolve()), "single_call_scorer_sha256": sha(scorer_path),
        "TEST_read": False, "VAL_data_read": False, "inertia_reconstruction_enabled": False,
        "Plant_truth_deployment_input": False, "diagnostic_only": True,
        "frozen_replay_status": "FAIL_FIXED_FROZEN_REPLAY",
    })

    pre_raw = Path(row["candidate_raw_path"])
    locked = list((TARGET / "candidate_runner_work/matlab").rglob("*.m"))
    locked += list((TARGET / "candidate_runner_work/matlab/models").glob("*.mat"))
    locked += [TARGET / name for name in (
        "TRAIN_SCENE_BINDING_v1.json", "OOF_FOLD_MODEL_MANIFEST_v1.json", "OOF_HOLDOUT_CHECKPOINT_v1.pt",
        "MATLAB_EVENTWISE_PARITY_INPUTS_v1.mat", "MATLAB_EVENTWISE_PARITY_INPUTS_v1.json")]
    locked += [plan_path, scorer_path, prep_path, contract_path,
               TARGET / "references/DIAGNOSTIC_PROTOCOL_NOPLANT_v1.json",
               TARGET / "references/ORIGINAL_CANDIDATE_FROZEN_SCORE_v1.json",
               TARGET / "references/W09_FIXED_NOTCH_FROZEN_REPLAY_v1.json",
               TARGET / "references/PRIOR_NO_PLANT_PREFLIGHT_v1.json",
               TARGET / "references/PRIOR_FULL_RUNNER_NO_PLANT_SOURCE_AUDIT_v1.json",
               TARGET / "PRIOR_MATLAB_HELPER_PARITY_NOPLANT_v1.json",
               no_plant_audit, static_audit, baseline_score, pre_raw, pre_raw.with_name("run_status.json"),
               Path(binding["b72_scoring_raw_path"]), Path(binding["b72_scoring_status_path"]),
               Path(binding["c5_raw_path"]), Path(binding["c5_status_path"]),
               Path(binding["parent_raw_path"]), Path(binding["parent_status_path"]),
               ROOT / "experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_full72_v1/audits/score_full72_candidate_v1.py",
               ROOT / "experiments/dl_attitude_replacement_20261026/mlp15_composite_dev_v3/RELEASE.json"]
    unique = sorted({p.resolve(strict=True) for p in locked if p.is_file()}, key=lambda p: str(p).lower())
    lock = {"schema": "POSITION_COMPENSATION_DUAL_NOTCH_SINGLE_CALL_SOURCE_LOCK_V1", "study_id": STUDY_ID,
            "files": [{"path": str(p), "relative_path": os.path.relpath(p, TARGET.resolve()).replace(os.sep, "/"), "sha256": sha(p)} for p in unique],
            "Plant_calls_authorized": 1, "TEST_read": False, "VAL_read": False}
    LOCK.write_text(json.dumps(lock, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    release["source_lock_sha256"] = sha(LOCK)
    release["source_lock_file_count"] = len(unique)
    RELEASE.write_text(json.dumps(release, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"study": str(TARGET.resolve()), "scene_id": SCENE_ID,
                      "status": release["status"], "authorized_Plant_calls": release["authorized_Plant_calls"],
                      "no_plant_audit_sha256": release["prior_no_plant_preflight_sha256"],
                      "model_sha256": release["weights_sha256"], "source_lock_sha256": sha(LOCK),
                      "locked_files": len(unique), "frozen_replay_status": release["frozen_replay_status"]}, indent=2))


if __name__ == "__main__":
    main()
