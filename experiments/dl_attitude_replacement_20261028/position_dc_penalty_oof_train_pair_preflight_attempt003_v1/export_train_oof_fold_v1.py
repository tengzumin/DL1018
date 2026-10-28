#!/usr/bin/env python3
"""Select the first locked TRAIN scene and export its held-out DC-fold model."""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import torch
from scipy.io import savemat

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
DATA=ROOT/"experiments/dl_attitude_replacement_20261028/position_cosine_gru_train24_causal_v1"
CV=DATA/"teacher_position_balanced_dc_penalty_cv_v1"
TASK=DATA/"task_aware_cv_v1"
PARENT=ROOT/"experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_full72_v1"
C5ROOT=ROOT/"experiments/position_axis_coordinate_c5_dev72_20261023"
C5_RECEIPT=ROOT/"experiments/attitude_physics_inertia_observer_20261025/holdout_gate_inspection_v2/C5_R_TASK_BINDING_PILOT_RECEIPT_v5.json"
PHYSICAL=DATA/"TRAIN_C5_24_PHYSICAL_RESIDUAL_MANIFEST_source_v1.json"
DATASET=DATA/"COSINE_GRU_C5_TRAIN24_POSITION_CAUSAL_PAIRS_v1.npz"
DATA_MANIFEST=DATA/"DATASET_MANIFEST_v1.json"
DATA_LOCK=DATA/"SOURCE_LOCK_v1.json"
OOF=CV/"DC_PENALTY_OOF_v1.npz"
PLAN=CV/"PREDECLARED_CONFIG_v1.json"
RESULT=CV/"DC_PENALTY_RESULTS_v1.json"
CV_LOCK=CV/"DC_PENALTY_SOURCE_LOCK_v1.json"
CHECKPOINT_DIR=CV/"checkpoints"
LOCAL_CHECKPOINT=HERE/"OOF_HOLDOUT_CHECKPOINT_v1.pt"
LOCAL_PAYLOAD=HERE/"TRAIN_SCENE_PAYLOAD_v1.mat"
MAT=HERE/"candidate_runner_work/matlab/models/position_dc_oof_holdout_W00_05.mat"
PARITY_MAT=HERE/"MATLAB_EVENTWISE_PARITY_INPUTS_v1.mat"
BINDING=HERE/"TRAIN_SCENE_BINDING_v1.json"
MODEL_MANIFEST=HERE/"OOF_FOLD_MODEL_MANIFEST_v1.json"
PARITY_JSON=HERE/"MATLAB_EVENTWISE_PARITY_INPUTS_v1.json"
sys.path.insert(0,str(TASK))
import fit_task_aware_fourfold_v1 as fit  # noqa:E402

def sha(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""):h.update(b)
    return h.hexdigest()
def read(path:Path)->dict:return json.loads(path.read_text(encoding="utf-8-sig"))
def abs_path(path:str|Path)->Path:
    p=Path(path)
    return p if p.is_absolute() else ROOT/p

def main()->None:
    outputs=(LOCAL_CHECKPOINT,LOCAL_PAYLOAD,MAT,PARITY_MAT,BINDING,MODEL_MANIFEST,PARITY_JSON)
    if any(p.exists() for p in outputs):raise RuntimeError("Refusing to overwrite an existing TRAIN pair export")
    dm=read(DATA_MANIFEST);dl=read(DATA_LOCK);plan=read(PLAN);cv_result=read(RESULT);cv_lock=read(CV_LOCK)
    scene_ids=list(dm["source_scene_ids"])
    if len(scene_ids)!=24 or dm["scene_count"]!=24:raise RuntimeError("Expected exact manifest TRAIN24 list")
    first=scene_ids[0]
    rows=dl.get("scene_rows",[])
    if not rows or rows[0].get("scene_id")!=first:raise RuntimeError("Manifest first scene differs from locked source row")
    fold_matches=[f for f in plan["folds"] if first in f["holdout_scene_ids"]]
    if len(fold_matches)!=1:raise RuntimeError("First TRAIN scene does not map to exactly one held-out fold")
    fold=fold_matches[0];fold_id=fold["fold_id"]
    if fold_id!="holdout_W00_05":raise RuntimeError("Unexpected first-scene DC fold identity")
    ckpt_source=CHECKPOINT_DIR/f"{fold_id}_dc_penalty.pt"
    expected_ckpt=cv_lock["checkpoint_sha256_by_fold"][fold_id]
    if sha(ckpt_source)!=expected_ckpt or cv_result["folds"][fold_id]["checkpoint_sha256"]!=expected_ckpt:
        raise RuntimeError("DC OOF checkpoint hash is not bound by results and source lock")
    ih=cv_result.get("input_hashes",{})
    if not (sha(DATASET)==dm["dataset_sha256"]==ih.get("dataset_sha256")==dl["data_sha256"] and
            sha(DATA_MANIFEST)==ih.get("dataset_manifest_sha256") and
            sha(DATA_LOCK)==ih.get("dataset_source_lock_sha256")==dm["source_lock_sha256"] and
            sha(OOF)==cv_result["oof_sha256"]==cv_lock["oof_sha256"] and
            sha(PLAN)==cv_result["config_sha256"]==cv_lock["config_sha256"] and
            cv_lock["input_hashes"]==ih and
            sha(CHECKPOINT_DIR/f"{fold_id}_dc_penalty.pt")==cv_lock["checkpoint_sha256_by_fold"][fold_id]):
        raise RuntimeError("TRAIN24/OOF lineage does not match the locked DC experiment")
    if cv_lock.get("oof_sha256")!=sha(OOF) or cv_lock.get("config_sha256")!=sha(PLAN) or cv_lock.get("checkpoint_sha256_by_fold",{}).get(fold_id)!=sha(ckpt_source):
        raise RuntimeError("OOF source lock does not bind selected fold")

    parent_manifest=read(PARENT/"MANIFEST.json");parent_release=read(PARENT/"RELEASE.json")
    parent_rows=[r for r in parent_manifest["records"] if r.get("scene_id")==first]
    if len(parent_rows)!=1:raise RuntimeError("First TRAIN scene absent or duplicated in parent cosine manifest")
    pr=parent_rows[0]
    parent_raw=abs_path(pr["candidate_raw_path"]);parent_status=abs_path(pr["candidate_status_path"])
    parent_start=parent_raw.parent/"run_start.json"
    dlrow=rows[0]
    if (dlrow.get("scene_id")!=first or
        abs_path(dlrow["parent_cosine_gru_raw_path"])!=parent_raw or
        abs_path(dlrow["parent_status_path"])!=parent_status):
        raise RuntimeError("TRAIN source lock paths differ from the selected parent record")
    c5_lock=read(C5ROOT/"C5_DEV72_INPUT_LOCK_v3.json")
    c5_rows=[r for r in c5_lock["scenes"] if r.get("scene_id")==first]
    physical=read(PHYSICAL);physical_rows=[r for r in physical["records"] if r.get("scene_id")==first]
    if len(c5_rows)!=1 or len(physical_rows)!=1:raise RuntimeError("Selected TRAIN scene lacks unique C5 physical/raw binding")
    cr=c5_rows[0];phys=physical_rows[0]
    c5_raw=abs_path(phys["raw_path"]);c5_status=abs_path(phys["status_path"]);c5_start=abs_path(phys["run_start_path"])
    if (abs_path(dlrow["physical_c5_raw_path"])!=c5_raw or
        dlrow["physical_c5_raw_sha256"]!=phys["raw_sha256"] or
        dlrow["physical_c5_status_sha256"]!=phys["status_sha256"] or
        dlrow["physical_c5_run_start_sha256"]!=phys["run_start_sha256"] or
        dlrow["parent_cosine_gru_raw_sha256"]!=sha(parent_raw) or
        dlrow["parent_status_sha256"]!=sha(parent_status) or
        dlrow["parent_run_start_sha256"]!=sha(parent_start)):
        raise RuntimeError("TRAIN source-lock scene hashes do not match selected physical records")
    payload=abs_path(pr["payload_path"])
    if not (parent_raw.is_file() and parent_status.is_file() and parent_start.is_file() and
            c5_raw.is_file() and c5_status.is_file() and c5_start.is_file() and payload.is_file()):
        raise RuntimeError("Selected TRAIN pair is missing parent/C5 raw/status/start or payload")
    ps=read(parent_status);cs=read(c5_status);pst=read(parent_start);crp=cr
    for label,path,expected in (("parent raw",parent_raw,ps.get("raw_sha256")),
        ("parent status",parent_status,pr.get("candidate_status_sha256")),("parent start",parent_start,None),
        ("C5 raw",c5_raw,phys.get("raw_sha256")),("C5 status",c5_status,phys.get("status_sha256")),
        ("C5 start",c5_start,phys.get("run_start_sha256")),("payload",payload,pr.get("payload_sha256"))):
        if expected and sha(path).lower()!=str(expected).lower():raise RuntimeError(f"{label} SHA mismatch")
    if (ps.get("scene_id")!=first or ps.get("state")!="COMPLETED" or ps.get("status_value")!="STABLE" or
        ps.get("transitions")!=20000 or ps.get("state_samples")!=20001 or ps.get("TEST_read") is True or
        cs.get("scene_id")!=first or (cs.get("state") not in (None,"COMPLETED")) or
        cs.get("TEST_accessed") is True or cs.get("test_data_read") is True or
        pst.get("scene_id")!=first or pst.get("b_raw_sha256")!=cr["B72_scoring"]["raw_sha256"] or
        pst.get("c5_raw_sha256")!=phys["raw_sha256"] or pst.get("payload_sha256")!=pr.get("payload_sha256") or
        pst.get("gru_model_sha256")!=parent_manifest["candidate_model_sha256"]):
        raise RuntimeError("Parent/C5 selected TRAIN raw/status/start are incomplete or do not share identity")
    c5_receipt=read(C5_RECEIPT)
    if (c5_receipt.get("status")!="PASS_NO_PLANT_PILOT_PAYLOADS_ONLY" or c5_receipt.get("plant_calls")!=0 or
        c5_receipt.get("training_runs")!=0 or c5_receipt.get("tests_data_read") is not False):
        raise RuntimeError("Fixed C5 config/model receipt is outside read-only scope")
    c5_snap=abs_path(c5_receipt["input_records"]["c5_snapshot_mat"]["path"])
    position_model=abs_path(c5_receipt["input_records"]["model_mat"]["path"])
    c5_lock_path=abs_path(c5_receipt["input_records"]["c5_input_lock"]["path"])
    for name,path,record in (("C5 snapshot",c5_snap,c5_receipt["input_records"]["c5_snapshot_mat"]),
        ("C5 position model",position_model,c5_receipt["input_records"]["model_mat"]),
        ("C5 input lock",c5_lock_path,c5_receipt["input_records"]["c5_input_lock"])):
        if not path.is_file() or sha(path).lower()!=record["sha256"].lower():raise RuntimeError(f"{name} receipt hash mismatch")
    parent_model=abs_path(parent_manifest["candidate_model_path"])
    if sha(parent_model).lower()!=parent_manifest["candidate_model_sha256"].lower():raise RuntimeError("Parent cosine model SHA mismatch")
    payload_sha=sha(payload)
    if payload_sha!=pr["payload_sha256"] or payload_sha!=pst["payload_sha256"]:raise RuntimeError("Selected TRAIN payload hashes disagree")
    binding={
        "schema":"POSITION_DC_PENALTY_TRAIN_SCENE_PAIR_BINDING_V1","status":"PASS_TRAIN_ONLY_PAIR_BINDING",
        "scope":"Only the first locked TRAIN_C5_24 scene; no VAL/TEST raw, no Plant, no inertia reconstruction.",
        "selected_scene_id":first,"source_order_zero_based":0,"source_split":"TRAIN_C5_24 (canonical ID prefix DEV)",
        "fold_id":fold_id,"fold_index_zero_based":0,"fold_train_scene_ids":fold["train_scene_ids"],
        "fold_holdout_scene_ids":fold["holdout_scene_ids"],"fold_checkpoint_path":str(ckpt_source.resolve()),
        "fold_checkpoint_sha256":sha(ckpt_source),"dataset_path":str(DATASET.resolve()),"dataset_sha256":sha(DATASET),
        "dataset_manifest_path":str(DATA_MANIFEST.resolve()),"dataset_manifest_sha256":sha(DATA_MANIFEST),
        "dataset_source_lock_path":str(DATA_LOCK.resolve()),"dataset_source_lock_sha256":sha(DATA_LOCK),
        "oof_path":str(OOF.resolve()),"oof_sha256":sha(OOF),"oof_plan_path":str(PLAN.resolve()),"oof_plan_sha256":sha(PLAN),
        "oof_result_path":str(RESULT.resolve()),"oof_result_sha256":sha(RESULT),"oof_source_lock_path":str(CV_LOCK.resolve()),"oof_source_lock_sha256":sha(CV_LOCK),
        "parent_cosine_release_path":str((PARENT/"RELEASE.json").resolve()),"parent_cosine_release_sha256":sha(PARENT/"RELEASE.json"),
        "parent_cosine_manifest_path":str((PARENT/"MANIFEST.json").resolve()),"parent_cosine_manifest_sha256":sha(PARENT/"MANIFEST.json"),
        "parent_cosine_source_lock_path":str((PARENT/"SOURCE_LOCK_v1.json").resolve()),"parent_cosine_source_lock_sha256":sha(PARENT/"SOURCE_LOCK_v1.json"),
        "parent_cosine_model_path":str(parent_model.resolve()),"parent_cosine_model_sha256":sha(parent_model),
        "parent_raw_path":str(parent_raw.resolve()),"parent_raw_sha256":sha(parent_raw),
        "parent_status_path":str(parent_status.resolve()),"parent_status_sha256":sha(parent_status),
        "parent_run_start_path":str(parent_start.resolve()),"parent_run_start_sha256":sha(parent_start),
        "c5_input_lock_path":str(c5_lock_path.resolve()),"c5_input_lock_sha256":sha(c5_lock_path),
        "c5_raw_path":str(c5_raw.resolve()),"c5_raw_sha256":sha(c5_raw),
        "c5_status_path":str(c5_status.resolve()),"c5_status_sha256":sha(c5_status),
        "c5_run_start_path":str(c5_start.resolve()),"c5_run_start_sha256":sha(c5_start),
        "scene_payload_source_path":str(payload.resolve()),"scene_payload_source_sha256":payload_sha,
        "c5_snapshot_path":str(c5_snap.resolve()),"c5_snapshot_sha256":sha(c5_snap),
        "position_model_path":str(position_model.resolve()),"position_model_sha256":sha(position_model),
        "c5_receipt_path":str(C5_RECEIPT.resolve()),"c5_receipt_sha256":sha(C5_RECEIPT),
        "external_identity_sha256":cr["external_identity_sha256"],"TEST_read":False,"VAL_data_read":False,
        "inertia_reconstruction_enabled":False,"Plant_calls":0,
    }
    shutil.copyfile(ckpt_source,LOCAL_CHECKPOINT);shutil.copyfile(payload,LOCAL_PAYLOAD)
    checkpoint=torch.load(LOCAL_CHECKPOINT,map_location="cpu",weights_only=False)
    if (checkpoint.get("fold_id")!=fold_id or checkpoint.get("holdout_scene_ids")!=fold["holdout_scene_ids"] or
        checkpoint.get("train_scene_ids")!=fold["train_scene_ids"] or first in checkpoint["train_scene_ids"] or
        checkpoint.get("teacher_npz_sha256")!=cv_result["input_hashes"]["teacher_npz_sha256"]):
        raise RuntimeError("Selected checkpoint is not the exact held-out fold model")
    with np.load(DATASET,allow_pickle=False) as d, np.load(OOF,allow_pickle=False) as oof:
        if d["scene_ids"].astype(str).tolist()!=scene_ids or oof["scene_ids"].astype(str).tolist()!=scene_ids:
            raise RuntimeError("TRAIN/OOF scene order mismatch")
        ids_idx=[scene_ids.index(s) for s in fold["holdout_scene_ids"]]
        x=d["x14_model_input"][ids_idx].astype(np.float32);ready=d["ready_mask"][ids_idx].astype(bool)
        base=np.clip(d["applied_acceleration_event_mps2"][ids_idx].astype(np.float32),-3,3)
        event_t=d["event_time_s"][ids_idx].astype(np.float32)
        mean=np.asarray(checkpoint["normalizer_mean"],np.float32);std=np.asarray(checkpoint["normalizer_std"],np.float32)
        if mean.shape!=(14,) or std.shape!=(14,) or np.any(std<=0):raise RuntimeError("Fold X14 normalizer invalid")
        xn=((x-mean[None,None,:])/std[None,None,:]).astype(np.float32)
        model=fit.ResidualGRU().cpu().eval();model.load_state_dict(checkpoint["state_dict"])
        with torch.no_grad():raw,delta=model(torch.from_numpy(xn))
        raw=raw.numpy().astype(np.float64);delta=delta.numpy().astype(np.float64)
        delta[~ready]=0.0;beta=np.clip(event_t.astype(np.float64)/1.8,0,1)
        action=np.clip(base.astype(np.float64)+beta[...,None]*delta,-3,3);action[~ready]=0.0
        for local_i,source_i in enumerate(ids_idx):
            if (not np.allclose(raw[local_i],oof["student_raw_delta_mps2"][source_i],atol=1e-6,rtol=0) or
                not np.allclose(delta[local_i],oof["student_delta_mps2"][source_i],atol=1e-6,rtol=0) or
                not np.allclose(action[local_i],oof["student_action_mps2"][source_i],atol=1e-6,rtol=0)):
                raise RuntimeError("Fold checkpoint replay differs from its fixed OOF predictions")
        state=checkpoint["state_dict"]
        mat_values={"gru_weight_ih_l0":state["gru.weight_ih_l0"].numpy(),"gru_weight_hh_l0":state["gru.weight_hh_l0"].numpy(),
            "gru_bias_ih_l0":state["gru.bias_ih_l0"].numpy(),"gru_bias_hh_l0":state["gru.bias_hh_l0"].numpy(),
            "head_weight":state["head.weight"].numpy(),"head_bias":state["head.bias"].numpy(),
            "input_mean":mean,"input_std":std,"fold_id":fold_id,"seed":np.int64(checkpoint["seed"]),
            "pytorch_gru_gate_order":"reset,update,new","teacher_used_at_inference":np.uint8(0),
            "beta_rise_time_s":np.float64(1.8),"delta_limit_mps2":np.float64(.5),"action_limit_mps2":np.float64(3.0)}
        savemat(MAT,mat_values,do_compression=True)
        savemat(PARITY_MAT,{
            "x14":np.transpose(x,(2,1,0)),"ready_mask":ready,"event_time_s":event_t,
            "expected_beta":beta,"base_applied_mps2":np.transpose(base,(2,1,0)),
            "expected_raw_mps2":np.transpose(raw,(2,1,0)),"expected_delta_mps2":np.transpose(delta,(2,1,0)),
            "expected_action_mps2":np.transpose(action,(2,1,0)),
        },do_compression=True)
    binding["local_fold_checkpoint_path"]=str(LOCAL_CHECKPOINT.resolve());binding["local_fold_checkpoint_sha256"]=sha(LOCAL_CHECKPOINT)
    binding["local_scene_payload_path"]=str(LOCAL_PAYLOAD.resolve());binding["local_scene_payload_sha256"]=sha(LOCAL_PAYLOAD)
    binding["weights_mat_path"]=str(MAT.resolve());binding["weights_mat_sha256"]=sha(MAT)
    BINDING.write_text(json.dumps(binding,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    model_manifest={
        "schema":"POSITION_DC_PENALTY_CV_FOLD_DEPLOY_MODEL_MANIFEST_V1","scope":"one fold-heldout TRAIN scene; not validation; not a deployment authorization",
        "scene_id":first,"fold_id":fold_id,"fold_checkpoint_sha256":sha(LOCAL_CHECKPOINT),"source_checkpoint_sha256":sha(ckpt_source),
        "weights_mat_sha256":sha(MAT),"dataset_sha256":sha(DATASET),"dataset_manifest_sha256":sha(DATA_MANIFEST),
        "dataset_source_lock_sha256":sha(DATA_LOCK),"oof_sha256":sha(OOF),"oof_plan_sha256":sha(PLAN),
        "oof_result_sha256":sha(RESULT),"oof_source_lock_sha256":sha(CV_LOCK),
        "fold_train_scene_ids":fold["train_scene_ids"],"fold_holdout_scene_ids":fold["holdout_scene_ids"],
        "architecture":"GRU(14,32)->Linear(32,3)","normalizer_scope":"holdout_W00_05 training scenes only; 18 scene rows, all causal events",
        "runtime_input":"causal X14 only","teacher_used_at_inference":False,
        "action_contract":"clip(C5_action + clip(event_time_s/1.8,0,1)*clip(delta,-0.5,0.5), -3,3); delta=0 until ready",
        "first_event_time_s":float(event_t[0,0]),"first_ready_event_index_zero_based":31,
        "first_ready_event_time_s":float(event_t[0,31]),"parity_holdout_scene_count":len(fold["holdout_scene_ids"]),
        "parity_events_per_scene":1999,"checkpoint_vs_oof_max_abs_raw_delta_error_mps2":float(np.max(np.abs(raw-oof["student_raw_delta_mps2"][ids_idx]))),
    }
    MODEL_MANIFEST.write_text(json.dumps(model_manifest,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    parity={"schema":"POSITION_DC_PENALTY_CV_FOLD_MATLAB_PARITY_INPUTS_V1","scene_ids":fold["holdout_scene_ids"],
        "fold_id":fold_id,"selected_scene_id":first,"source_order_zero_based":0,"event_count_per_scene":1999,
        "scene_count":len(fold["holdout_scene_ids"]),"x14_shape_matlab":[14,1999,len(fold["holdout_scene_ids"])],
        "first_event_time_s":float(event_t[0,0]),"first_ready_event_index_zero_based":31,
        "first_ready_event_time_s":float(event_t[0,31]),"beta_formula":"clip(event_time_s/1.8,0,1)",
        "delta_clip_mps2":.5,"total_action_clip_mps2":3,"fold_checkpoint_sha256":sha(LOCAL_CHECKPOINT),
        "weights_mat_sha256":sha(MAT),"oof_sha256":sha(OOF),"dataset_sha256":sha(DATASET),
        "holdout_checkpoint_replay_match":True,"plant_called":False,"VAL_read":False,"TEST_read":False}
    PARITY_JSON.write_text(json.dumps(parity,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"scene_id":first,"fold_id":fold_id,"checkpoint_sha256":sha(LOCAL_CHECKPOINT),
        "mat_sha256":sha(MAT),"parity_input_sha256":sha(PARITY_MAT),"holdout_scene_count":len(fold["holdout_scene_ids"]),
        "source_binding":str(BINDING)},indent=2),flush=True)

if __name__=="__main__":main()
