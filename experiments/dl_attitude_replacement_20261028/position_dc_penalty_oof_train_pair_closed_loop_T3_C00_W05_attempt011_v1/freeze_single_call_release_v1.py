#!/usr/bin/env python3
"""Freeze one TRAIN-only closed-loop call after a matching no-Plant preflight."""
import hashlib
import json
from pathlib import Path

import torch

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
RUNNER=HERE/"candidate_runner_work"
LOCK=HERE/"SOURCE_LOCK_SINGLE_CALL_v1.json"
RELEASE=HERE/"RELEASE.json"
PRIOR=ROOT/"experiments/dl_attitude_replacement_20261028/position_dc_penalty_oof_train_pair_preflight_T3_C00_W05_attempt008_v1/audits/NO_PLANT_PREFLIGHT_v1.json"

def sha(p):
    h=hashlib.sha256()
    with Path(p).open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""):h.update(b)
    return h.hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding="utf-8-sig"))
def write_new(p,obj):
    if p.exists():raise RuntimeError(f"Refusing to overwrite frozen artifact {p}")
    p.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def main():
    if LOCK.exists() or RELEASE.exists():raise RuntimeError("Single-call source/release already frozen")
    binding_path=HERE/"TRAIN_SCENE_BINDING_v1.json"
    model_path=HERE/"OOF_FOLD_MODEL_MANIFEST_v1.json"
    parity_json=HERE/"MATLAB_EVENTWISE_PARITY_INPUTS_v1.json"
    parity_mat=HERE/"MATLAB_EVENTWISE_PARITY_INPUTS_v1.mat"
    weights=RUNNER/"matlab/models/position_dc_oof_holdout_W00_05.mat"
    ckpt=HERE/"OOF_HOLDOUT_CHECKPOINT_v1.pt"
    binding=read(binding_path);model=read(model_path);prior=read(PRIOR)
    scene=binding["selected_scene_id"]
    if (binding["fold_id"]!="holdout_W00_05" or
        scene in binding["fold_train_scene_ids"] or scene not in binding["fold_holdout_scene_ids"]):
        raise RuntimeError("Single-call authorization must use the fixed TRAIN scene held out by its fold")
    if (prior.get("status")!="PASS" or prior.get("scene_id")!=scene or prior.get("fold_id")!=binding["fold_id"] or
        prior.get("Plant_calls")!=0 or prior.get("weights_sha256")!=sha(weights) or
        prior.get("parent_raw_sha256")!=binding["parent_raw_sha256"] or prior.get("c5_raw_sha256")!=binding["c5_raw_sha256"]):
        raise RuntimeError("Matching no-Plant preflight did not pass for this model/scene/source pair")
    for p in [binding_path,model_path,parity_json,parity_mat,weights,ckpt,PRIOR]:
        if not p.is_file():raise RuntimeError(f"Missing locked input {p}")
    checkpoint=torch.load(ckpt,map_location="cpu",weights_only=False)
    if checkpoint.get("fold_id")!=binding["fold_id"] or scene not in checkpoint["holdout_scene_ids"]:
        raise RuntimeError("Selected model is not the exact heldout fold checkpoint")
    required=[
        RUNNER/"matlab/runtime/run_mlp15_dev72_closed_loop.m",
        RUNNER/"matlab/runtime/prepare_train_scene_no_plant.m",
        RUNNER/"matlab/runtime/run_train_pair_preflight_no_plant.m",
        RUNNER/"matlab/runtime/run_train_scene_single_attempt.m",
        RUNNER/"matlab/runtime/verify_train_oof_fold_matlab_parity.m",
        RUNNER/"matlab/runtime/validate_train_scene_binding_v1.m",
    ]
    if any(not p.is_file() for p in required):raise RuntimeError("A locked single-call runner source is missing")
    main_text=required[0].read_text(encoding="utf-8-sig")
    if ("position_dc_penalty_oof_train_pair_closed_loop_T3_C00_W05_attempt011_v1" not in main_text or
        "TRAINPair:NoOverwrite" not in required[3].read_text(encoding="utf-8-sig") or
        "no-plant preflight reached the main-loop boundary" not in main_text.lower()):
        raise RuntimeError("Single-call runner identity or no-Plant gate is not present")
    files=[]
    for p in sorted(RUNNER.rglob("*.m")):
        files.append({"path":str(p.resolve()),"relative_path":p.relative_to(HERE).as_posix(),"sha256":sha(p)})
    for p in [HERE/"export_train_oof_fold_v1.py",HERE/"finalize_partial_export_v1.py",
              HERE/"freeze_single_call_release_v1.py",HERE/"score_train_single_scene_v1.py",
              HERE/"SCENE_VALIDATION_EQUIVALENCE_v1.md"]:
        files.append({"path":str(p.resolve()),"relative_path":p.relative_to(HERE).as_posix(),"sha256":sha(p)})
    constants=ROOT/"experiments/dl_attitude_replacement_20261026/mlp15_composite_dev_v3/RELEASE.json"
    scorer=ROOT/"experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_full72_v1/audits/score_full72_candidate_v1.py"
    source_lock={"schema":"POSITION_DC_OOF_TRAIN_SINGLE_CALL_SOURCE_LOCK_V1",
        "scope":"One fold-heldout TRAIN scene, one Plant call; candidate source and scorer frozen.",
        "study_root":str(HERE.resolve()),"runner_root":str(RUNNER.resolve()),"scene_id":scene,
        "fold_id":binding["fold_id"],"fold_checkpoint_sha256":sha(ckpt),"weights_sha256":sha(weights),
        "prior_no_plant_preflight_sha256":sha(PRIOR),"file_count":len(files),"files":files,
        "TEST_read":False,"VAL_raw_read":False,"Plant_calls_executed_at_lock":0,
        "authorized_Plant_calls":1}
    write_new(LOCK,source_lock)
    release={"schema":"DL1018_POSITION_C5_RESIDUAL_GRU_NOPLANT_V1",
        "study_id":"position_dc_penalty_oof_train_pair_closed_loop_T3_C00_W05_attempt011_v1",
        "status":"RELEASED","authorized_Plant_calls":1,"Plant_calls":1,"potential_budget_calls":1,
        "authorized_scenes":[scene],"fixed_scene_id":scene,"one_attempt_only":True,
        "training_seed":int(checkpoint["seed"]),"training_started_by_this_study":False,
        "training_runs":0,"optimizer_updates_by_this_study":0,
        "position_residual_gru":{"enabled":True,"weights_sha256":sha(weights),"fold_id":binding["fold_id"],
            "teacher_used_at_inference":False,
            "action_contract":"clip(C5_action + clip(t/1.8,0,1)*clip(delta,-0.5,0.5),-3,3); delta=0 until event 31 readiness."},
        "source_lock_path":str(LOCK.resolve()),"source_lock_sha256":sha(LOCK),
        "train_scene_binding_path":str(binding_path.resolve()),"train_scene_binding_sha256":sha(binding_path),
        "model_manifest_path":str(model_path.resolve()),"model_manifest_sha256":sha(model_path),
        "parity_inputs_mat_path":str(parity_mat.resolve()),"parity_inputs_mat_sha256":sha(parity_mat),
        "fold_checkpoint_path":str(ckpt.resolve()),"fold_checkpoint_sha256":sha(ckpt),
        "weights_path":str(weights.resolve()),"weights_sha256":sha(weights),
        "prior_no_plant_preflight_path":str(PRIOR.resolve()),"prior_no_plant_preflight_sha256":sha(PRIOR),
        "candidate_runner_closed_loop_sha256":sha(required[0]),
        "prepare_wrapper_sha256":sha(required[1]),"no_plant_preflight_wrapper_sha256":sha(required[2]),
        "single_attempt_wrapper_sha256":sha(required[3]),"eventwise_parity_script_sha256":sha(required[4]),
        "dataset_sha256":binding["dataset_sha256"],"dataset_manifest_sha256":binding["dataset_manifest_sha256"],
        "oof_sha256":binding["oof_sha256"],"parent_cosine_model_sha256":binding["parent_cosine_model_sha256"],
        "parent_raw_sha256":binding["parent_raw_sha256"],"parent_status_sha256":binding["parent_status_sha256"],
        "parent_run_start_sha256":binding["parent_run_start_sha256"],
        "b72_scoring_raw_sha256":binding["b72_scoring_raw_sha256"],
        "b72_scoring_status_sha256":binding["b72_scoring_status_sha256"],
        "c5_raw_sha256":binding["c5_raw_sha256"],"c5_status_sha256":binding["c5_status_sha256"],
        "c5_run_start_sha256":binding["c5_run_start_sha256"],"c5_snapshot_sha256":binding["c5_snapshot_sha256"],
        "position_model_sha256":binding["position_model_sha256"],
        "scene_payload_sha256":binding["local_scene_payload_sha256"],
        "prior_preflight_release_sha256":prior["release_sha256"],
        "scorer_path":str(scorer.resolve()),"scorer_sha256":sha(scorer),
        "score_constants_path":str(constants.resolve()),"score_constants_sha256":sha(constants),
        "parent_controller":"cosine GRU + frozen C5 M110, same-scene completed TRAIN raw",
        "source_split":"TRAIN_C5_24 only","TEST_read":False,"VAL_data_read":False,
        "inertia_reconstruction_enabled":False,"Plant_truth_deployment_input":False}
    write_new(RELEASE,release)
    print(json.dumps({"release":str(RELEASE.resolve()),"study_id":release["study_id"],
        "scene_id":scene,"fold_id":binding["fold_id"],"authorized_Plant_calls":1,
        "source_lock_sha256":sha(LOCK),"prior_no_plant_preflight_sha256":sha(PRIOR)},indent=2))

if __name__=="__main__":main()
