#!/usr/bin/env python3
"""Freeze only the isolated TRAIN-fold preflight source and zero-call release."""
import hashlib
import json
from pathlib import Path

import torch

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
RUNNER=HERE/"candidate_runner_work"
LOCK=HERE/"SOURCE_LOCK_NO_PLANT_v1.json"
RELEASE=HERE/"RELEASE.json"

def sha(p):
    h=hashlib.sha256()
    with Path(p).open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""): h.update(b)
    return h.hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding="utf-8-sig"))
def write_new(p,obj):
    if p.exists():raise RuntimeError(f"Refusing to overwrite frozen artifact {p}")
    p.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def main():
    if LOCK.exists() or RELEASE.exists():raise RuntimeError("Preflight source/release already frozen")
    binding_path=HERE/"TRAIN_SCENE_BINDING_v1.json"
    model_path=HERE/"OOF_FOLD_MODEL_MANIFEST_v1.json"
    parity_inputs_json=HERE/"MATLAB_EVENTWISE_PARITY_INPUTS_v1.json"
    parity_inputs_mat=HERE/"MATLAB_EVENTWISE_PARITY_INPUTS_v1.mat"
    weights_path=RUNNER/"matlab/models/position_dc_oof_holdout_W00_05.mat"
    ckpt_path=HERE/"OOF_HOLDOUT_CHECKPOINT_v1.pt"
    binding=read(binding_path);model=read(model_path);parity=read(parity_inputs_json)
    scene=binding["selected_scene_id"]
    if (scene!="DL1018_DEV_T1_C00_W03" or binding["fold_id"]!="holdout_W00_05" or
        scene in binding["fold_train_scene_ids"] or scene not in binding["fold_holdout_scene_ids"]):
        raise RuntimeError("Only manifest-first TRAIN scene with its heldout fold is permitted")
    if any((not p.is_file()) for p in [binding_path,model_path,parity_inputs_json,parity_inputs_mat,weights_path,ckpt_path]):
        raise RuntimeError("Required heldout TRAIN artifacts are missing")
    checkpoint=torch.load(ckpt_path,map_location="cpu",weights_only=False)
    if checkpoint.get("fold_id")!=binding["fold_id"] or checkpoint.get("seed") is None:
        raise RuntimeError("Fold checkpoint identity/seed is invalid")
    required_runner=[
        RUNNER/"matlab/runtime/run_mlp15_dev72_closed_loop.m",
        RUNNER/"matlab/runtime/prepare_train_scene_no_plant.m",
        RUNNER/"matlab/runtime/run_train_pair_preflight_no_plant.m",
        RUNNER/"matlab/runtime/verify_train_oof_fold_matlab_parity.m",
        RUNNER/"matlab/runtime/position_residual_gru_step_v1.m",
    ]
    if any(not p.is_file() for p in required_runner):raise RuntimeError("Required isolated MATLAB entry/runtime file missing")
    runner_text=required_runner[0].read_text(encoding="utf-8-sig")
    if ("position_dc_penalty_oof_train_pair_preflight_v1" not in runner_text or
        "PositionNotch:NoPlantPreflightStop" not in runner_text or
        "no-plant preflight reached the main-loop boundary" not in runner_text.lower()):
        raise RuntimeError("Isolated runner no-Plant gate is not the reviewed variant")
    files=[]
    for p in sorted(RUNNER.rglob("*.m")):
        files.append({"path":str(p.resolve()),"relative_path":p.relative_to(HERE).as_posix(),"sha256":sha(p)})
    for p in [HERE/"export_train_oof_fold_v1.py",HERE/"finalize_partial_export_v1.py",HERE/"freeze_train_pair_preflight_v1.py"]:
        files.append({"path":str(p.resolve()),"relative_path":p.relative_to(HERE).as_posix(),"sha256":sha(p)})
    for p in [binding_path,model_path,parity_inputs_json,parity_inputs_mat,ckpt_path,weights_path]:
        if sha(p) != (binding.get("weights_mat_sha256") if p==weights_path else sha(p)):
            raise RuntimeError(f"Frozen artifact hash inconsistency: {p}")
    source_lock={
        "schema":"POSITION_DC_OOF_TRAIN_PAIR_PREFLIGHT_SOURCE_LOCK_V1",
        "scope":"Isolated candidate MATLAB runtime and no-Plant wrapper; first fold-heldout TRAIN scene only.",
        "study_root":str(HERE.resolve()),"runner_root":str(RUNNER.resolve()),
        "selected_scene_id":scene,"fold_id":binding["fold_id"],"fold_checkpoint_sha256":sha(ckpt_path),
        "weights_mat_sha256":sha(weights_path),"file_count":len(files),"files":files,
        "TEST_read":False,"VAL_raw_read":False,"Plant_calls":0,
    }
    write_new(LOCK,source_lock)
    release={
        "schema":"DL1018_POSITION_C5_RESIDUAL_GRU_NOPLANT_V1",
        "study_id":"position_dc_penalty_oof_train_pair_preflight_attempt002_v1",
        "status":"PREPARED_NO_PLANT_PENDING_ROOT_AUDIT",
        "authorized_Plant_calls":0,"Plant_calls":0,"potential_budget_calls":0,
        "authorized_scenes":[scene],"fixed_scene_id":scene,
        "training_seed":int(checkpoint["seed"]),
        "position_residual_gru":{"enabled":True,"weights_sha256":sha(weights_path),
            "fold_id":binding["fold_id"],"teacher_used_at_inference":False,
            "action_contract":"clip(C5_action + clip(t/1.8,0,1)*clip(delta,-0.5,0.5),-3,3); delta=0 until event 31 readiness."},
        "source_lock_path":str(LOCK.resolve()),"source_lock_sha256":sha(LOCK),
        "train_scene_binding_path":str(binding_path.resolve()),"train_scene_binding_sha256":sha(binding_path),
        "model_manifest_path":str(model_path.resolve()),"model_manifest_sha256":sha(model_path),
        "parity_inputs_json_path":str(parity_inputs_json.resolve()),"parity_inputs_json_sha256":sha(parity_inputs_json),
        "parity_inputs_mat_path":str(parity_inputs_mat.resolve()),"parity_inputs_mat_sha256":sha(parity_inputs_mat),
        "fold_checkpoint_path":str(ckpt_path.resolve()),"fold_checkpoint_sha256":sha(ckpt_path),
        "weights_path":str(weights_path.resolve()),"weights_sha256":sha(weights_path),
        "candidate_runner_closed_loop_sha256":sha(required_runner[0]),
        "prepare_wrapper_sha256":sha(required_runner[1]),"no_plant_wrapper_sha256":sha(required_runner[2]),
        "eventwise_parity_script_sha256":sha(required_runner[3]),
        "dataset_sha256":binding["dataset_sha256"],"oof_sha256":binding["oof_sha256"],
        "parent_cosine_model_sha256":binding["parent_cosine_model_sha256"],
        "parent_raw_sha256":binding["parent_raw_sha256"],"parent_status_sha256":binding["parent_status_sha256"],
        "c5_raw_sha256":binding["c5_raw_sha256"],"c5_status_sha256":binding["c5_status_sha256"],
        "c5_snapshot_sha256":binding["c5_snapshot_sha256"],"position_model_sha256":binding["position_model_sha256"],
        "scene_payload_sha256":binding["local_scene_payload_sha256"],
        "parent_controller":"cosine GRU + C5 M110, same scene's existing completed raw for comparison",
        "source_split":"TRAIN_C5_24 only; canonical scene id prefix DEV",
        "TEST_read":False,"VAL_data_read":False,"inertia_reconstruction_enabled":False,
        "Plant_truth_deployment_input":False,
    }
    write_new(RELEASE,release)
    print(json.dumps({"source_lock":str(LOCK.resolve()),"source_lock_sha256":sha(LOCK),
        "release":str(RELEASE.resolve()),"study_id":release["study_id"],
        "scene_id":scene,"fold_id":binding["fold_id"],"zero_call":True,
        "locked_matlab_files":sum(x["relative_path"].endswith(".m") for x in files)},indent=2))

if __name__=="__main__":main()
