#!/usr/bin/env python3
"""Create an isolated T1 runner copy with the frozen dual-notch hook and zero-Plant release."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
STUDY_ID = "position_compensation_dual_notch_train_diag_online_noPlant_v1"
SOURCE = ROOT / "experiments/dl_attitude_replacement_20261028/position_dc_penalty_oof_train_pair_preflight_W09_T1_C10_attempt014_v1"
REPLAY = ROOT / "experiments/dl_attitude_replacement_20261028/position_compensation_dual_notch_train_replay_v1"
RUNNER = HERE / "candidate_runner_work/matlab/runtime/run_mlp15_dev72_closed_loop.m"
PREPARE = HERE / "candidate_runner_work/matlab/runtime/prepare_train_scene_no_plant.m"
LOCK = HERE / "SOURCE_LOCK_NO_PLANT_v1.json"
RELEASE = HERE / "RELEASE.json"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one {label} insertion anchor, found {count}.")
    return text.replace(old, new, 1)


def patch_runner_copy() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    old_id = "position_dc_penalty_oof_train_pair_preflight_W09_T1_C10_attempt014_v1"
    text = text.replace(old_id, STUDY_ID)
    anchor = "    noPlantBoundaryRequested=logical(field_or(opts,'no_plant_boundary_check',false));\n"
    addition = anchor + """    dualNotchRelease=field_or(release,'applied_acceleration_dual_notch',struct);
    dualNotchRuntime=field_or(field_or(opts,'stage1_position_runtime',struct), ...
        'applied_acceleration_dual_notch',struct);
    dualNotchReleaseB=double(field_or(dualNotchRelease,'b',[]));
    dualNotchReleaseA=double(field_or(dualNotchRelease,'a',[]));
    dualNotchRuntimeB=double(field_or(dualNotchRuntime,'b',[]));
    dualNotchRuntimeA=double(field_or(dualNotchRuntime,'a',[]));
    dualNotchReleaseCenters=double(field_or(dualNotchRelease,'centers_hz',[]));
    dualNotchReleaseQ=double(field_or(dualNotchRelease,'quality_factor_each',[]));
    dualNotchIdentityOk=strcmp(releaseSchema,'DL1018_POSITION_C5_RESIDUAL_GRU_NOPLANT_V1')&& ...
        strcmp(char(field_or(release,'study_id','')),'""" + STUDY_ID + """')&& ...
        any(strcmp(authorizedScenes,sceneId))&&logical(field_or(dualNotchRelease,'enabled',false))&& ...
        logical(field_or(dualNotchRuntime,'enabled',false))&& ...
        abs(double(field_or(dualNotchRelease,'sample_rate_hz',NaN))-100)<1e-12&& ...
        isequal(dualNotchReleaseCenters(:),[2.2;3.2])&& ...
        isequal(dualNotchReleaseQ(:),[4;4])&& ...
        abs(double(field_or(dualNotchRelease,'action_limit_mps2',NaN))-3)<1e-12&& ...
        isequal(size(dualNotchReleaseB),[2,3])&&isequal(size(dualNotchReleaseA),[2,3])&& ...
        isequal(size(dualNotchRuntimeB),[2,3])&&isequal(size(dualNotchRuntimeA),[2,3])&& ...
        max(abs(dualNotchRuntimeB(:)-dualNotchReleaseB(:)))<1e-12&& ...
        max(abs(dualNotchRuntimeA(:)-dualNotchReleaseA(:)))<1e-12;
    dualNotchNoPlantReleaseOk=dualNotchIdentityOk&& ...
        strcmp(char(field_or(release,'status','')),'PREPARED_NO_PLANT_PENDING_ROOT_AUDIT')&& ...
        double(field_or(release,'authorized_Plant_calls',-1))==0&& ...
        double(field_or(release,'Plant_calls',-1))==0&&noPlantBoundaryRequested;
    dualNotchCandidateReleaseOk=dualNotchNoPlantReleaseOk;
"""
    text = replace_once(text, anchor, addition, "no-Plant release")
    text = replace_once(
        text,
        "assert(parentReleaseOk||notchCandidateReleaseOk||residualCandidateReleaseOk, ...",
        "assert(parentReleaseOk||notchCandidateReleaseOk||residualCandidateReleaseOk||dualNotchCandidateReleaseOk, ...",
        "candidate release gate",
    )
    text = replace_once(
        text,
        "    if residualCandidateReleaseOk\n        assert(isfield(effectiveOptions.stage1_position_runtime,'residual_gru')&& ...",
        """    if dualNotchCandidateReleaseOk
        assert(isfield(effectiveOptions.stage1_position_runtime,'applied_acceleration_dual_notch')&& ...
            logical(effectiveOptions.stage1_position_runtime.applied_acceleration_dual_notch.enabled), ...
            'DualNotch:Runtime','The fixed dual-notch diagnostic must be enabled.');
        effectiveOptions.stage1_position_runtime=rmfield( ...
            effectiveOptions.stage1_position_runtime,'applied_acceleration_dual_notch');
    end
    if residualCandidateReleaseOk
        assert(isfield(effectiveOptions.stage1_position_runtime,'residual_gru')&& ...""",
        "strip runtime-only notch option",
    )
    text = replace_once(
        text,
        "    identityOpts=rmfield(identityOpts,'composite_attempt_marker');\n",
        """    identityOpts=rmfield(identityOpts,'composite_attempt_marker');
    if isfield(identityOpts.stage1_position_runtime,'applied_acceleration_dual_notch')
        identityOpts.stage1_position_runtime=rmfield( ...
            identityOpts.stage1_position_runtime,'applied_acceleration_dual_notch');
    end
""",
        "identity-only options",
    )
    text = replace_once(
        text,
        "    stage1PositionAppliedNotch=field_or(stage1PositionRuntime,'applied_acceleration_notch',struct);\n",
        """    stage1PositionDualNotch=field_or(stage1PositionRuntime,'applied_acceleration_dual_notch',struct);
    stage1PositionDualNotchEnabled=isstruct(stage1PositionDualNotch)&& ...
        logical(field_or(stage1PositionDualNotch,'enabled',false));
    stage1PositionDualNotchCenters=double(field_or(stage1PositionDualNotch,'centers_hz',[]));
    stage1PositionDualNotchQ=double(field_or(stage1PositionDualNotch,'quality_factor_each',[]));
    stage1PositionAppliedNotch=field_or(stage1PositionRuntime,'applied_acceleration_notch',struct);
""",
        "dual-notch runtime option",
    )
    text = replace_once(
        text,
        "    if stage1PositionAppliedNotchEnabled\n        assert(isequal(size(stage1PositionNotchB),[1,3])",
        """    if stage1PositionDualNotchEnabled
        assert(dualNotchCandidateReleaseOk&&stage1PositionActive&& ...
            abs(double(field_or(stage1PositionDualNotch,'sample_rate_hz',NaN))-100)<1e-12&& ...
            isequal(stage1PositionDualNotchCenters(:),[2.2;3.2])&& ...
            isequal(stage1PositionDualNotchQ(:),[4;4]), ...
            'DualNotch:RuntimeContract','Dual notch must match the fixed W09 diagnostic release.');
    end
    if stage1PositionAppliedNotchEnabled
        assert(isequal(size(stage1PositionNotchB),[1,3])""",
        "dual-notch runtime contract",
    )
    text = replace_once(
        text,
        "    if stage1PositionAppliedNotchEnabled\n        assert(stage1PositionActive&&abs(dt-.001)<1e-12&&abs(rbfFullHz-100)<1e-12, ...",
        """    if stage1PositionDualNotchEnabled
        assert(stage1PositionActive&&abs(dt-.001)<1e-12&&abs(rbfFullHz-100)<1e-12, ...
            'DualNotch:RuntimeContract','Dual notch requires active Stage-1 output, 1-kHz steps, and 100-Hz events.');
        helperPath=which('position_compensation_dual_notch_init');
        assert(strcmpi(helperPath,fullfile(isolatedRoot,'matlab','runtime', ...
            'position_compensation_dual_notch_init.m')), ...
            'DualNotch:HelperPath','The dual-notch helper must resolve inside the isolated runner copy.');
    end
    if stage1PositionAppliedNotchEnabled
        assert(stage1PositionActive&&abs(dt-.001)<1e-12&&abs(rbfFullHz-100)<1e-12, ...""",
        "dual-notch scheduler contract",
    )
    text = replace_once(
        text,
        "    stage1PositionAppliedNotchState=zeros(3,4);\n",
        """    stage1PositionAppliedNotchState=zeros(3,4);
    stage1PositionDualNotchState=position_compensation_dual_notch_init();
    assert(max(abs(stage1PositionDualNotchState.b(:)-dualNotchReleaseB(:)))<1e-12&& ...
        max(abs(stage1PositionDualNotchState.a(:)-dualNotchReleaseA(:)))<1e-12, ...
        'DualNotch:CoefficientContract','Runtime helper coefficients differ from the frozen release.');
    stage1PositionDualNotchEventInput=nan(n,3);stage1PositionDualNotchEventRaw=nan(n,3);
    stage1PositionDualNotchEventApplied=nan(n,3);stage1PositionDualNotchEventClip=false(n,3);
""",
        "dual-notch state initialization",
    )
    text = replace_once(
        text,
        "                            stage1PositionWeightNorm(k)=norm(stage1PositionWeight,'fro');\n",
        """                            if stage1PositionDualNotchEnabled
                                notchInput=stage1PositionHeldAppliedCache;
                                assert(all(abs(notchInput)<=3+1e-10)&&abs(rbfFullDt-.01)<1e-10, ...
                                    'DualNotch:InputOrRate','Final action exceeded bounds or event period is not 10 ms.');
                                [stage1PositionDualNotchState,notchApplied,notchRaw,notchClip]= ...
                                    position_compensation_dual_notch_step( ...
                                    stage1PositionDualNotchState,notchInput,true);
                                stage1PositionDualNotchEventInput(k,:)=notchInput.';
                                stage1PositionDualNotchEventRaw(k,:)=notchRaw.';
                                stage1PositionDualNotchEventApplied(k,:)=notchApplied.';
                                stage1PositionDualNotchEventClip(k,:)=notchClip.';
                                stage1PositionHeldAppliedCache=notchApplied;
                                stage1PositionHeldForce=P.mass*notchApplied;
                            end
                            stage1PositionWeightNorm(k)=norm(stage1PositionWeight,'fro');
""",
        "post-GRU/pre-force online insertion",
    )
    text = replace_once(
        text,
        "            'stage1_position_applied_notch_event_clip_active',stage1PositionNotchEventClipActive(q,:), ...\n",
        """            'stage1_position_applied_notch_event_clip_active',stage1PositionNotchEventClipActive(q,:), ...
            'stage1_position_applied_dual_notch_enabled',stage1PositionDualNotchEnabled, ...
            'stage1_position_applied_dual_notch_centers_hz',[2.2,3.2], ...
            'stage1_position_applied_dual_notch_q',[4,4], ...
            'stage1_position_applied_dual_notch_event_input_mps2',stage1PositionDualNotchEventInput(q,:), ...
            'stage1_position_applied_dual_notch_event_output_raw_mps2',stage1PositionDualNotchEventRaw(q,:), ...
            'stage1_position_applied_dual_notch_event_output_applied_mps2',stage1PositionDualNotchEventApplied(q,:), ...
            'stage1_position_applied_dual_notch_event_clip_active',stage1PositionDualNotchEventClip(q,:), ...
""",
        "dual-notch result logging",
    )
    RUNNER.write_text(text, encoding="utf-8", newline="\n")


def main() -> None:
    if RELEASE.exists() or LOCK.exists():
        raise RuntimeError("Refusing to overwrite the independent runner release or lock.")
    if not (HERE / "candidate_runner_work").exists():
        shutil.copytree(SOURCE / "candidate_runner_work", HERE / "candidate_runner_work")
    for name in (
        "TRAIN_SCENE_BINDING_v1.json", "OOF_FOLD_MODEL_MANIFEST_v1.json",
        "OOF_HOLDOUT_CHECKPOINT_v1.pt", "MATLAB_EVENTWISE_PARITY_INPUTS_v1.mat",
        "MATLAB_EVENTWISE_PARITY_INPUTS_v1.json", "RELEASE_NO_PLANT_PREFLIGHT_v1.json",
    ):
        shutil.copy2(SOURCE / name, HERE / name)
    (HERE / "audits").mkdir(exist_ok=True)
    (HERE / "runs").mkdir(exist_ok=True)

    # Add the fixed helpers to the isolated runner copy, never to the source study.
    target_runtime = HERE / "candidate_runner_work/matlab/runtime"
    for name in ("position_compensation_dual_notch_init.m", "position_compensation_dual_notch_step.m"):
        shutil.copy2(HERE / "matlab" / name, target_runtime / name)
    if "dualNotchIdentityOk=" not in RUNNER.read_text(encoding="utf-8"):
        patch_runner_copy()
    prepare = PREPARE.read_text(encoding="utf-8")
    old_id = "position_dc_penalty_oof_train_pair_preflight_W09_T1_C10_attempt014_v1"
    if old_id in prepare:
        prepare = prepare.replace(old_id, STUDY_ID)
        PREPARE.write_text(prepare, encoding="utf-8", newline="\n")
    prepare = PREPARE.read_text(encoding="utf-8")
    anchor = "opts.gate_identity_lock=identity;\n"
    if "opts.stage1_position_runtime.applied_acceleration_dual_notch=" not in prepare:
        prepare = replace_once(
            prepare,
            anchor,
            anchor + """assert(isfield(release,'applied_acceleration_dual_notch'), ...
    'DualNotch:Release','Missing fixed dual-notch diagnostic contract.');
opts.stage1_position_runtime.applied_acceleration_dual_notch= ...
    release.applied_acceleration_dual_notch;
""",
            "dual-notch frozen runtime config",
        )
        PREPARE.write_text(prepare, encoding="utf-8", newline="\n")

    # Freeze a no-Plant release from the prior no-Plant contract and the unchanged W09 replay coefficients.
    release = json.loads((SOURCE / "RELEASE_NO_PLANT_PREFLIGHT_v1.json").read_text(encoding="utf-8-sig"))
    replay = json.loads((REPLAY / "TRAIN_FROZEN_DUAL_NOTCH_REPLAY_v1.json").read_text(encoding="utf-8-sig"))
    binding_path = HERE / "TRAIN_SCENE_BINDING_v1.json"
    manifest_path = HERE / "OOF_FOLD_MODEL_MANIFEST_v1.json"
    release.update({
        "study_id": STUDY_ID,
        "status": "PREPARED_NO_PLANT_PENDING_ROOT_AUDIT",
        "authorized_Plant_calls": 0,
        "Plant_calls": 0,
        "potential_budget_calls": 0,
        "source_lock_path": str(LOCK.resolve()),
        "train_scene_binding_path": str(binding_path.resolve()),
        "train_scene_binding_sha256": sha256(binding_path),
        "model_manifest_path": str(manifest_path.resolve()),
        "model_manifest_sha256": sha256(manifest_path),
        "parity_inputs_mat_path": str((HERE / "MATLAB_EVENTWISE_PARITY_INPUTS_v1.mat").resolve()),
        "parity_inputs_mat_sha256": sha256(HERE / "MATLAB_EVENTWISE_PARITY_INPUTS_v1.mat"),
        "parity_inputs_json_path": str((HERE / "MATLAB_EVENTWISE_PARITY_INPUTS_v1.json").resolve()),
        "parity_inputs_json_sha256": sha256(HERE / "MATLAB_EVENTWISE_PARITY_INPUTS_v1.json"),
        "candidate_runner_closed_loop_sha256": sha256(RUNNER),
        "prepare_wrapper_sha256": sha256(PREPARE),
        "no_plant_wrapper_sha256": sha256(HERE / "candidate_runner_work/matlab/runtime/run_train_pair_preflight_no_plant.m"),
        "eventwise_parity_script_sha256": sha256(HERE / "candidate_runner_work/matlab/runtime/verify_train_oof_fold_matlab_parity.m"),
        "TEST_read": False,
        "VAL_data_read": False,
        "inertia_reconstruction_enabled": False,
        "Plant_truth_deployment_input": False,
        "applied_acceleration_dual_notch": {
            "enabled": True,
            "sample_rate_hz": 100.0,
            "centers_hz": [2.2, 3.2],
            "quality_factor_each": [4.0, 4.0],
            "action_limit_mps2": 3.0,
            "b": [replay["filter"]["b_a_coefficients"][str(f)]["b"] for f in (2.2, 3.2)],
            "a": [replay["filter"]["b_a_coefficients"][str(f)]["a"] for f in (2.2, 3.2)],
            "filter_location": "Post-residual-GRU final action, pre-force injection.",
            "event_update_hz": 100.0,
            "held_between_events": True,
            "parameter_sweep": False,
        },
        "frozen_replay_status": replay["status"],
        "diagnostic_only_no_plant": True,
    })

    locked_paths = []
    locked_paths.extend(sorted((HERE / "candidate_runner_work/matlab").rglob("*.m")))
    locked_paths.extend(sorted((HERE / "candidate_runner_work/matlab/models").glob("*.mat")))
    locked_paths.extend([
        binding_path, manifest_path, HERE / "OOF_HOLDOUT_CHECKPOINT_v1.pt",
        HERE / "MATLAB_EVENTWISE_PARITY_INPUTS_v1.mat", HERE / "MATLAB_EVENTWISE_PARITY_INPUTS_v1.json",
        HERE / "DIAGNOSTIC_PROTOCOL_v1.json", HERE / "RUNNER_INTEGRATION_CONTRACT_v1.json",
        HERE / "MATLAB_EVENTWISE_PARITY_INPUTS_v1.mat", HERE / "DUAL_NOTCH_EVENTWISE_PARITY_INPUTS_v1.mat",
        HERE / "DUAL_NOTCH_EVENTWISE_PARITY_INPUTS_v1.json",
        HERE / "matlab/position_compensation_dual_notch_init.m",
        HERE / "matlab/position_compensation_dual_notch_step.m",
        HERE / "matlab/run_dual_notch_no_plant_parity_v1.m",
        HERE / "prepare_matlab_parity_inputs.py", HERE / "prepare_full_runner_no_plant_v1.py",
        HERE / "verify_full_runner_no_plant_v1.py",
    ])
    unique_paths = sorted({p.resolve() for p in locked_paths if p.is_file()}, key=lambda p: str(p).lower())
    lock = {
        "schema": "POSITION_COMPENSATION_DUAL_NOTCH_RUNNER_SOURCE_LOCK_NOPLANT_V1",
        "study_id": STUDY_ID,
        "files": [{"path": str(path), "relative_path": path.relative_to(HERE.resolve()).as_posix(), "sha256": sha256(path)} for path in unique_paths],
        "Plant_calls": 0,
        "TEST_read": False,
        "VAL_read": False,
    }
    LOCK.write_text(json.dumps(lock, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    release["source_lock_sha256"] = sha256(LOCK)
    release["source_lock_file_count"] = len(unique_paths)
    RELEASE.write_text(json.dumps(release, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "study_id": STUDY_ID,
        "runner_copy": str(RUNNER.resolve()),
        "runner_sha256": sha256(RUNNER),
        "source_lock": str(LOCK.resolve()),
        "source_lock_sha256": sha256(LOCK),
        "source_lock_file_count": len(unique_paths),
        "release_status": release["status"],
        "Plant_calls": release["Plant_calls"],
    }, indent=2))


if __name__ == "__main__":
    main()
