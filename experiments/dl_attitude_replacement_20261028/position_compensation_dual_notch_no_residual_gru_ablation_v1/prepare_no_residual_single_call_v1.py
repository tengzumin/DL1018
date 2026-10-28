#!/usr/bin/env python3
"""Freeze independent one-call T1/T3 no-position-GRU ablation releases."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
STUDY_ROOT = "position_compensation_dual_notch_no_residual_gru_ablation"
NORES_NOPLANT_SCHEMA = "DL1018_POSITION_C5_DUAL_NOTCH_NO_POSITION_GRU_NOPLANT_V1"
SINGLE_SCHEMA = "DL1018_POSITION_C5_DUAL_NOTCH_NO_POSITION_GRU_SINGLE_CALL_V1"
SCENES = {"T1": "DL1018_DEV_T1_C10_W09", "T3": "DL1018_DEV_T3_C09_W09"}
TARGET_DIRS = {"T1": "no_position_gru_notch_T1_single_v1", "T3": "no_position_gru_notch_T3_single_v1"}
PREFILTERS = {
    "T1": ROOT / "experiments/dl_attitude_replacement_20261028/position_dc_penalty_oof_train_pair_preflight_W09_T1_C10_attempt014_v1",
    "T3": ROOT / "experiments/dl_attitude_replacement_20261028/position_dc_penalty_oof_train_pair_preflight_W09_T3_C09_attempt015_v1",
}
WITH_GRU_STUDIES = {
    "T1": ROOT / "experiments/dl_attitude_replacement_20261028/position_compensation_dual_notch_train_diag_single_call_T1_v1",
    "T3": ROOT / "experiments/dl_attitude_replacement_20261028/position_compensation_dual_notch_train_diag_single_call_T3_v1",
}
REPLAY = ROOT / "experiments/dl_attitude_replacement_20261028/position_compensation_dual_notch_train_replay_v1/TRAIN_FROZEN_DUAL_NOTCH_REPLAY_v1.json"
SCORE_SOURCE = ROOT / "experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_full72_v1/audits/score_full72_candidate_v1.py"
SCORE_CONSTANTS = ROOT / "experiments/dl_attitude_replacement_20261026/mlp15_composite_dev_v3/RELEASE.json"
LOCKED_FROZEN_SCORE = ROOT / "score_no_residual_gru_ablation_v1.py"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def replace_once(text: str, old: str, new: str, label: str, count: int = 1) -> str:
    found = text.count(old)
    if found != count:
        raise RuntimeError(f"Expected {count} {label} anchors, found {found}.")
    return text.replace(old, new)


def patch_runner(target: Path, no_plant_id: str, study_id: str) -> None:
    runner = target / "candidate_runner_work/matlab/runtime/run_mlp15_dev72_closed_loop.m"
    text = runner.read_text(encoding="utf-8")
    old = (
        "dualNotchIdentityOk=any(strcmp(releaseSchema,{'DL1018_POSITION_C5_RESIDUAL_GRU_NOPLANT_V1',"
        "'DL1018_POSITION_C5_DUAL_NOTCH_NO_POSITION_GRU_NOPLANT_V1'}))&& ..."
    )
    new = (
        "dualNotchIdentityOk=any(strcmp(releaseSchema,{'DL1018_POSITION_C5_RESIDUAL_GRU_NOPLANT_V1',"
        "'DL1018_POSITION_C5_DUAL_NOTCH_NO_POSITION_GRU_NOPLANT_V1','" + SINGLE_SCHEMA + "'}))&& ..."
    )
    text = replace_once(text, old, new, "single-call dual-notch schema")
    text = text.replace(no_plant_id, study_id)
    text = replace_once(
        text,
        "dualNotchCandidateReleaseOk=dualNotchNoPlantReleaseOk;",
        """dualNotchSinglePlantReleaseOk=dualNotchIdentityOk&& ...
        strcmp(char(field_or(release,'status','')),'RELEASED')&& ...
        double(field_or(release,'authorized_Plant_calls',-1))==1&& ...
        double(field_or(release,'Plant_calls',-1))==1&&~noPlantBoundaryRequested;
    dualNotchCandidateReleaseOk=dualNotchNoPlantReleaseOk||dualNotchSinglePlantReleaseOk;""",
        "single-call dual-notch budget gate",
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
        "single-call first-Plant marker guard",
    )
    runner.write_text(text, encoding="utf-8", newline="\n")

    prepare = target / "candidate_runner_work/matlab/runtime/prepare_train_scene_no_plant.m"
    text = prepare.read_text(encoding="utf-8")
    text = text.replace(no_plant_id, study_id)
    text = replace_once(
        text,
        "strcmp(char(release.schema),'" + NORES_NOPLANT_SCHEMA + "')",
        "any(strcmp(char(release.schema),{'" + NORES_NOPLANT_SCHEMA + "','" + SINGLE_SCHEMA + "'}))",
        "single-call prepare schema",
    )
    prepare.write_text(text, encoding="utf-8", newline="\n")

    wrapper = target / "candidate_runner_work/matlab/runtime/run_train_scene_single_attempt.m"
    text = wrapper.read_text(encoding="utf-8")
    text = text.replace("position_dc_penalty_oof_train_pair_preflight_W09_T1_C10_attempt014_v1", study_id)
    text = replace_once(
        text,
        "strcmp(char(release.schema),'DL1018_POSITION_C5_RESIDUAL_GRU_NOPLANT_V1')",
        "strcmp(char(release.schema),'" + SINGLE_SCHEMA + "')",
        "single-call wrapper schema",
    )
    text = replace_once(
        text,
        "prepared=prepare_train_scene_no_plant();\nassert(~logical(prepared.opts.no_plant_boundary_check)&& ...",
        "prepared=prepare_train_scene_no_plant();\n"
        "assert(~isfield(prepared.opts.stage1_position_runtime,'residual_gru'), ...\n"
        "    'NoPositionGRU:Runtime','No position residual-GRU runtime field may be passed.');\n"
        "assert(~logical(prepared.opts.no_plant_boundary_check)&& ...",
        "single-call no-position-GRU runtime assertion",
    )
    wrapper.write_text(text, encoding="utf-8", newline="\n")


def build(arm: str) -> None:
    scene_id = SCENES[arm]
    no_plant = HERE / arm
    study_id = f"{STUDY_ROOT}_{arm}_single_call_v1"
    # Keep the physical path short enough for MATLAB/Python on Windows; the full
    # immutable study identity remains in the release and plan.
    target = ROOT / "experiments/dl_attitude_replacement_20261028" / TARGET_DIRS[arm]
    if target.exists():
        raise RuntimeError(f"Refusing to reuse {target}")
    prior_path = no_plant / "audits/NO_PLANT_PREFLIGHT_v1.json"
    prior_static_path = no_plant / "audits/DUAL_NOTCH_FULL_RUNNER_NO_PLANT_SOURCE_AUDIT_v1.json"
    prior = json.loads(prior_path.read_text(encoding="utf-8-sig"))
    prior_static = json.loads(prior_static_path.read_text(encoding="utf-8-sig"))
    if (prior.get("status") != "PASS" or prior.get("Plant_calls") != 0 or
            prior.get("position_residual_gru_weights_deserialized") is not False or
            prior.get("no_position_gru_model_load_or_forward_call") is not True or
            prior.get("frozen_C5_exact_options_match") is not True or
            prior_static.get("status") != "PASS_FULL_RUNNER_NOPLANT_BOUNDARY_HOOK_ORDER_AND_NO_POSITION_GRU" or
            prior.get("scene_id") != scene_id):
        raise RuntimeError("Single-call release requires the final reference-only no-Plant pass.")

    shutil.copytree(no_plant / "candidate_runner_work", target / "candidate_runner_work")
    for name in ("audits", "runs", "references"):
        (target / name).mkdir()
    for name in ("TRAIN_SCENE_BINDING_v1.json", "OOF_FOLD_MODEL_MANIFEST_v1.json",
                 "OOF_HOLDOUT_CHECKPOINT_v1.pt", "MATLAB_EVENTWISE_PARITY_INPUTS_v1.mat",
                 "MATLAB_EVENTWISE_PARITY_INPUTS_v1.json", "DUAL_NOTCH_EVENTWISE_PARITY_INPUTS_v1.mat",
                 "DUAL_NOTCH_EVENTWISE_PARITY_INPUTS_v1.json", "ABLATION_PROTOCOL_v1.json"):
        shutil.copy2(no_plant / name, target / name)
    for name, src in (
        ("PRIOR_NO_PLANT_PREFLIGHT_v1.json", prior_path),
        ("PRIOR_FULL_RUNNER_NO_PLANT_SOURCE_AUDIT_v1.json", prior_static_path),
        ("PRIOR_NO_PLANT_RELEASE_v1.json", no_plant / "RELEASE.json"),
        ("PRIOR_NO_PLANT_SOURCE_LOCK_v1.json", no_plant / "SOURCE_LOCK_NO_PLANT_v1.json"),
        ("DUAL_NOTCH_HELPER_PARITY_v1.json", no_plant / "MATLAB_NOPLANT_PARITY_v1.json"),
    ):
        shutil.copy2(src, target / "references" / name)
    shutil.copy2(HERE / "validate_no_residual_gru_raw_v1.py", target / "validate_no_residual_gru_raw_v1.py")
    score_script = target / "score_no_residual_gru_ablation_v1.py"
    shutil.copy2(HERE / "score_no_residual_gru_ablation_v1.py", score_script)

    binding = json.loads((target / "TRAIN_SCENE_BINDING_v1.json").read_text(encoding="utf-8-sig"))
    prefilter = PREFILTERS[arm]
    baseline_score = prefilter / "audits/TRAIN_SINGLE_SCENE_PAIRED_SCORE_v1.json"
    baseline = json.loads(baseline_score.read_text(encoding="utf-8-sig"))
    replay = json.loads(REPLAY.read_text(encoding="utf-8-sig"))
    replay_row = next(row for row in replay["results"] if row["scene_id"] == scene_id)
    with_gru_study = WITH_GRU_STUDIES[arm]
    with_gru_raw = with_gru_study / "runs" / scene_id / "attempt_01/raw_run.mat"
    with_gru_status = with_gru_raw.with_name("run_status.json")
    with_gru_score = with_gru_study / "audits" / f"DUAL_NOTCH_SINGLE_CALL_{arm}_SCORE_v1.json"
    score_inputs = {
        "B": (binding["b72_scoring_raw_path"], binding["b72_scoring_status_path"],
              binding["b72_scoring_raw_sha256"], binding["b72_scoring_status_sha256"]),
        "C5": (binding["c5_raw_path"], binding["c5_status_path"],
               binding["c5_raw_sha256"], binding["c5_status_sha256"]),
        "parent_GRU": (binding["parent_raw_path"], binding["parent_status_path"],
                       binding["parent_raw_sha256"], binding["parent_status_sha256"]),
        "candidate_pre_dual_notch": (replay_row["candidate_raw_path"],
                                     str(Path(replay_row["candidate_raw_path"]).with_name("run_status.json")),
                                     replay_row["candidate_raw_sha256"],
                                     sha(Path(replay_row["candidate_raw_path"]).with_name("run_status.json"))),
        "dual_notch_with_position_residual_gru": (str(with_gru_raw), str(with_gru_status),
                                                  sha(with_gru_raw), sha(with_gru_status)),
    }
    plan = {
        "schema": "POSITION_DUAL_NOTCH_NO_POSITION_RESIDUAL_GRU_SINGLE_CALL_PLAN_V1",
        "study_id": study_id, "status": "PREDECLARED_BEFORE_SINGLE_CALL",
        "scene_id": scene_id, "source_split": "TRAIN_C5_24", "fold_id": binding["fold_id"],
        "wind_group": "W09, dominant tones 2.2/3.2 Hz",
        "claim_limit": "One fixed W09 TRAIN scene; no cross-wind-spectrum generalization.",
        "purpose": "Measure the incremental position residual-GRU effect with the parent cosine-attitude-GRU, frozen C5 position controller and dual notch held fixed.",
        "entry_reason": {
            "prior_frozen_replay_status": "FAIL_FIXED_FROZEN_REPLAY",
            "why_one_call_is_authorized": "The no-residual-GRU arm has passed independent R2025b helper parity, source-lock, exact-options and full-runner noPlant checks. This fixed scene call isolates the added position-GRU contribution against the previously completed same-scene, same-filter arm.",
            "parameters_or_thresholds_changed": False,
        },
        "fixed_intervention": {
            "sample_rate_hz": 100.0, "centers_hz": [2.2, 3.2], "quality_factor_each": [4.0, 4.0],
            "action_limit_mps2": 3.0, "filter_location": "after final C5 action, before force injection",
            "held_between_events": True, "position_residual_gru_enabled": False,
        },
        "frozen_score": {
            "implementation": "score_full72_candidate_v1.score_raw",
            "metrics": ["Q_m", "task_SO3_rad", "inner_SO3_rad", "safety counters"],
            "spectrum_sample_rate_hz": 1000.0, "transitions": 20000,
            "window": "symmetric Hann", "detrend": "constant per channel",
            "bands_hz": {"peak_2p2": [1.5, 2.5], "peak_3p2": [2.5, 3.5]},
            "spectrum_units": "vector RMS mrad",
            "same_scene_comparators": ["B", "C5", "parent_GRU", "candidate_pre_dual_notch",
                                       "dual_notch_with_position_residual_gru", "dual_notch_no_position_residual_gru"],
            "baseline_score_path": str(baseline_score.resolve()), "baseline_score_sha256": sha(baseline_score),
            "with_position_gru_score_path": str(with_gru_score.resolve()), "with_position_gru_score_sha256": sha(with_gru_score),
        },
        "score_inputs": {
            name: {"raw_path": str(Path(values[0]).resolve()), "status_path": str(Path(values[1]).resolve()),
                   "raw_sha256": values[2], "status_sha256": values[3]}
            for name, values in score_inputs.items()
        },
        "measured_baseline_Q_task_inner": {
            name: {key: baseline["methods"][name][key] for key in ("Q_m", "task_SO3_rad", "inner_SO3_rad")}
            for name in ("B", "C5", "parent_GRU")
        } | {"candidate_pre_dual_notch": {
            key: baseline["methods"]["candidate"][key] for key in ("Q_m", "task_SO3_rad", "inner_SO3_rad")}},
        "one_call_only": True, "authorized_Plant_calls": 1,
        "TEST_read": False, "VAL_read": False, "inertia_reconstruction_enabled": False,
        "no_parameter_change_after_result": True,
    }
    plan_path = target / "SINGLE_CALL_PLAN_v1.json"
    plan_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    patch_runner(target, no_plant_id=json.loads((no_plant / "RELEASE.json").read_text(encoding="utf-8-sig"))["study_id"],
                 study_id=study_id)
    single_schema = SINGLE_SCHEMA
    release = json.loads((no_plant / "RELEASE.json").read_text(encoding="utf-8-sig"))
    runner = target / "candidate_runner_work/matlab/runtime/run_mlp15_dev72_closed_loop.m"
    prepare = target / "candidate_runner_work/matlab/runtime/prepare_train_scene_no_plant.m"
    wrapper = target / "candidate_runner_work/matlab/runtime/run_train_scene_single_attempt.m"
    contract_path = target / "RUNNER_INTEGRATION_CONTRACT_v1.json"
    shutil.copy2(no_plant / "RUNNER_INTEGRATION_CONTRACT_v1.json", contract_path)
    contract = json.loads(contract_path.read_text(encoding="utf-8-sig"))
    contract.update({"study_id": study_id, "isolated_runner_copy_path": str(runner.resolve()),
                     "original_runner_modified": False, "position_residual_gru_enabled": False,
                     "position_residual_gru_weights_deserialized": False,
                     "exact_options_check_preserved": True})
    contract_path.write_text(json.dumps(contract, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    release.update({
        "schema": single_schema, "study_id": study_id, "status": "RELEASED",
        "authorized_Plant_calls": 1, "Plant_calls": 1, "potential_budget_calls": 1, "one_attempt_only": True,
        "source_lock_path": str((target / "SOURCE_LOCK_SINGLE_CALL_v1.json").resolve()),
        "position_residual_gru": {**release["position_residual_gru"], "enabled": False,
                                  "disabled_for_ablation": True, "runtime_field_present": False,
                                  "weights_deserialized": False},
        "position_residual_gru_enabled": False, "position_residual_gru_weights_deserialized": False,
        "prior_no_plant_preflight_path": str(prior_path.resolve()), "prior_no_plant_preflight_sha256": sha(prior_path),
        "prior_full_runner_no_plant_source_audit_path": str(prior_static_path.resolve()),
        "prior_full_runner_no_plant_source_audit_sha256": sha(prior_static_path),
        "prior_no_plant_release_path": str((no_plant / "RELEASE.json").resolve()),
        "prior_no_plant_release_sha256": sha(no_plant / "RELEASE.json"),
        "prior_no_plant_source_lock_path": str((no_plant / "SOURCE_LOCK_NO_PLANT_v1.json").resolve()),
        "prior_no_plant_source_lock_sha256": sha(no_plant / "SOURCE_LOCK_NO_PLANT_v1.json"),
        "single_call_plan_path": str(plan_path.resolve()), "single_call_plan_sha256": sha(plan_path),
        "single_call_score_path": str((target / "score_no_residual_gru_ablation_v1.py").resolve()),
        "single_call_score_sha256": sha(target / "score_no_residual_gru_ablation_v1.py"),
        "raw_validator_path": str((target / "validate_no_residual_gru_raw_v1.py").resolve()),
        "raw_validator_sha256": sha(target / "validate_no_residual_gru_raw_v1.py"),
        "candidate_runner_closed_loop_sha256": sha(runner), "prepare_wrapper_sha256": sha(prepare),
        "single_attempt_wrapper_sha256": sha(wrapper),
        "baseline_score_path": str(baseline_score.resolve()), "baseline_score_sha256": sha(baseline_score),
        "with_position_gru_raw_path": str(with_gru_raw.resolve()), "with_position_gru_raw_sha256": sha(with_gru_raw),
        "with_position_gru_status_path": str(with_gru_status.resolve()), "with_position_gru_status_sha256": sha(with_gru_status),
        "TEST_read": False, "VAL_data_read": False, "inertia_reconstruction_enabled": False,
        "Plant_truth_deployment_input": False, "diagnostic_only": True,
        "frozen_replay_status": "FAIL_FIXED_FROZEN_REPLAY",
    })
    (target / "RELEASE.json").write_text(json.dumps(release, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lock_paths = list((target / "candidate_runner_work/matlab").rglob("*.m"))
    lock_paths += list((target / "candidate_runner_work/matlab/models").glob("*.mat"))
    lock_paths += [target / name for name in (
        "TRAIN_SCENE_BINDING_v1.json", "OOF_FOLD_MODEL_MANIFEST_v1.json", "OOF_HOLDOUT_CHECKPOINT_v1.pt",
        "MATLAB_EVENTWISE_PARITY_INPUTS_v1.mat", "MATLAB_EVENTWISE_PARITY_INPUTS_v1.json",
        "DUAL_NOTCH_EVENTWISE_PARITY_INPUTS_v1.mat", "DUAL_NOTCH_EVENTWISE_PARITY_INPUTS_v1.json",
        "ABLATION_PROTOCOL_v1.json", "SINGLE_CALL_PLAN_v1.json", "RUNNER_INTEGRATION_CONTRACT_v1.json",
        "score_no_residual_gru_ablation_v1.py", "validate_no_residual_gru_raw_v1.py",
        "references/PRIOR_NO_PLANT_PREFLIGHT_v1.json", "references/PRIOR_FULL_RUNNER_NO_PLANT_SOURCE_AUDIT_v1.json",
        "references/PRIOR_NO_PLANT_RELEASE_v1.json", "references/PRIOR_NO_PLANT_SOURCE_LOCK_v1.json",
        "references/DUAL_NOTCH_HELPER_PARITY_v1.json")]
    lock_paths.append(HERE / "prepare_no_residual_single_call_v1.py")
    lock_paths += [no_plant / name for name in ("verify_full_runner_no_plant_v1.py", "DIAGNOSTIC_PROTOCOL_v1.json")]
    lock_paths += [prior_path, prior_static_path, no_plant / "RELEASE.json", no_plant / "SOURCE_LOCK_NO_PLANT_v1.json",
                   baseline_score, with_gru_score, with_gru_raw, with_gru_status,
                   SCORE_SOURCE, SCORE_CONSTANTS, REPLAY]
    lock_paths += [Path(v[0]) for v in score_inputs.values()]
    lock_paths += [Path(v[1]) for v in score_inputs.values()]
    for key, value in binding.items():
        if key.endswith("_path") and isinstance(value, str) and Path(value).is_file():
            lock_paths.append(Path(value))
    locked = sorted({p.resolve(strict=True) for p in lock_paths if p.is_file()}, key=lambda p: str(p).lower())
    lock = {"schema": "POSITION_DUAL_NOTCH_NO_POSITION_RESIDUAL_GRU_SINGLE_CALL_SOURCE_LOCK_V1",
            "study_id": study_id,
            "files": [{"path": str(p), "relative_path": os.path.relpath(p, target.resolve()).replace(os.sep, "/"), "sha256": sha(p)} for p in locked],
            "Plant_calls_authorized": 1, "TEST_read": False, "VAL_read": False}
    lock_path = target / "SOURCE_LOCK_SINGLE_CALL_v1.json"
    lock_path.write_text(json.dumps(lock, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    release["source_lock_sha256"] = sha(lock_path)
    release["source_lock_file_count"] = len(locked)
    (target / "RELEASE.json").write_text(json.dumps(release, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"arm": arm, "study": str(target.resolve()), "scene_id": scene_id,
                      "status": "RELEASED", "Plant_calls_authorized": 1,
                      "weights_reference_sha256": release["weights_sha256"],
                      "source_lock_sha256": sha(lock_path), "locked_files": len(locked),
                      "same_filter_with_gru_raw_sha256": sha(with_gru_raw)}, indent=2))


def main() -> None:
    build("T1")
    build("T3")


if __name__ == "__main__":
    main()
