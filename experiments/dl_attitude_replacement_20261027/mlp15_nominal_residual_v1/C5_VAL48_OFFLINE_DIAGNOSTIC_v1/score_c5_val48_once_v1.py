#!/usr/bin/env python3
"""One-shot C5_VAL48 residual reconstruction and fixed-checkpoint offline score."""
from __future__ import annotations
import argparse,hashlib,json,sys,time
import inspect
from pathlib import Path
from typing import Any
import numpy as np
import torch

ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parent
STUDY=OUT.parent
BUILDER_PATH=STUDY/"prepare_train_data_v1.py"
FEATURE_ORDER=["wrapped_attitude_error_euler_rad_x3","body_rate_rad_s_x3","nominal_bs_body_torque_Nm_x3","morph_command_x4"]
AXES=("roll_x","pitch_y","yaw_z")
EVENTS=np.arange(10,20000,10,dtype=np.int64)


def sha(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda:f.read(8*1024*1024),b""):h.update(block)
    return h.hexdigest()


def write_new_json(path:Path,value:dict[str,Any])->None:
    if path.exists():raise FileExistsError(f"refusing to overwrite {path}")
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")


def silu(x:np.ndarray)->np.ndarray:
    return x/(1.0+np.exp(-np.clip(x,-700.0,700.0)))


def model_predict_once(features:np.ndarray,checkpoint:dict[str,Any],batch_size:int=4096)->np.ndarray:
    mean=checkpoint["input_mean"].detach().cpu().numpy().astype(np.float64).reshape(13)
    std=checkpoint["input_std"].detach().cpu().numpy().astype(np.float64).reshape(13)
    rms=checkpoint["target_rms"].detach().cpu().numpy().astype(np.float64).reshape(3)
    state=checkpoint["state_dict"]
    w1=state["net.0.weight"].detach().cpu().numpy().astype(np.float64);b1=state["net.0.bias"].detach().cpu().numpy().astype(np.float64)
    w2=state["net.2.weight"].detach().cpu().numpy().astype(np.float64);b2=state["net.2.bias"].detach().cpu().numpy().astype(np.float64)
    w3=state["net.4.weight"].detach().cpu().numpy().astype(np.float64);b3=state["net.4.bias"].detach().cpu().numpy().astype(np.float64)
    normalized=((features.astype(np.float64)-mean)/std)
    scenes,event_count,_=normalized.shape
    padded=np.pad(normalized,((0,0),(14,0),(0,0)),mode="constant")
    total=scenes*event_count
    prediction=np.empty((scenes,event_count,3),dtype=np.float64)
    offsets=np.arange(15,dtype=np.int64)
    for first in range(0,total,batch_size):
        stop=min(first+batch_size,total)
        flat=np.arange(first,stop,dtype=np.int64)
        scene_ix=flat//event_count;step_ix=flat%event_count
        windows=padded[scene_ix[:,None],step_ix[:,None]+offsets[None,:],:]
        x=windows.reshape(-1,195)
        h=silu(x@w1.T+b1)
        h=silu(h@w2.T+b2)
        prediction.reshape(-1,3)[first:stop]=(h@w3.T+b3)*rms
    return prediction


def stats(a:np.ndarray)->dict[str,Any]:
    q=np.percentile(a,[1,50,99],axis=(0,1))
    return {"mean":np.mean(a,axis=(0,1)).tolist(),"std":np.std(a,axis=(0,1)).tolist(),
      "rms":np.sqrt(np.mean(a*a,axis=(0,1))).tolist(),"min":np.min(a,axis=(0,1)).tolist(),
      "max":np.max(a,axis=(0,1)).tolist(),"p01":q[0].tolist(),"p50":q[1].tolist(),"p99":q[2].tolist()}


def metric_summary(error:np.ndarray,scene_ids:list[str])->dict[str,Any]:
    def calculate(ix:list[int])->dict[str,Any]:
        sub=error[ix]
        return {"scene_count":len(ix),
          "axis_pooled_rmse_rad_s2":dict(zip(AXES,np.sqrt(np.mean(sub**2,axis=(0,1))).tolist())),
          "axis_scene_macro_rmse_rad_s2":dict(zip(AXES,np.mean(np.sqrt(np.mean(sub**2,axis=1)),axis=0).tolist())),
          "scene_macro_rmse_rad_s2":float(np.mean(np.sqrt(np.mean(sub**2,axis=(1,2))))) }
    overall=calculate(list(range(len(scene_ids))))
    winds={}
    for wind in sorted({sid.rsplit("_",1)[-1] for sid in scene_ids}):
        ix=[i for i,sid in enumerate(scene_ids) if sid.rsplit("_",1)[-1]==wind]
        winds[wind]=calculate(ix)
    return {**overall,"by_wind_group":winds}


def run(config_path:Path,freeze_path:Path,source_freeze_path:Path,identity_path:Path,rules_path:Path,score_lock_path:Path,preflight_only:bool=False)->None:
    config=json.loads(config_path.read_text(encoding="utf-8")); train_freeze=json.loads(freeze_path.read_text(encoding="utf-8"))
    source_freeze=json.loads(source_freeze_path.read_text(encoding="utf-8")); identity=json.loads(identity_path.read_text(encoding="utf-8")); rules=json.loads(rules_path.read_text(encoding="utf-8")); score_lock=json.loads(score_lock_path.read_text(encoding="utf-8"))
    script=Path(__file__).resolve()
    if sha(script)!=score_lock["score_script_sha256"]:raise ValueError("score script SHA mismatch")
    if sha(source_freeze_path)!=score_lock["source_freeze_manifest_sha256"]:raise ValueError("VAL source freeze SHA mismatch")
    if sha(identity_path)!=score_lock["identity_check_sha256"] or identity.get("status")!="PASS" or identity.get("all_sha_match") is not True or identity.get("source_freeze_manifest_sha256")!=sha(source_freeze_path):raise ValueError("144-file VAL identity check missing or failed")
    if sha(rules_path)!=score_lock["eval_rules_sha256"]:raise ValueError("VAL eval rules SHA mismatch")
    if config.get("status")!="FROZEN" or train_freeze.get("status")!="FROZEN_PRETRAIN":raise ValueError("training config/freeze not frozen")
    if sha(config_path)!=train_freeze["training_config_sha256"] or sha(freeze_path)!=score_lock["training_freeze_manifest_sha256"]:raise ValueError("training config/freeze SHA mismatch")
    if rules.get("fixed_zero_compensation_baseline",{}).get("prediction_rad_s2")!=[0.0,0.0,0.0]:raise ValueError("zero-compensation rule mismatch")
    if rules.get("use_boundary","").find("no checkpoint/model selection")<0:raise ValueError("VAL use boundary missing")
    add4=ROOT/score_lock["addendum04_path"]
    if sha(add4)!=score_lock["addendum04_sha256"]:raise ValueError("ADDENDUM04 SHA mismatch")
    root_review=ROOT/score_lock["root_val_review_path"]
    if sha(root_review)!=score_lock["root_val_review_sha256"]:raise ValueError("root VAL rules review SHA mismatch")
    training_review=ROOT/score_lock["training_result_review_path"]
    if sha(training_review)!=score_lock["training_result_review_sha256"]:raise ValueError("root training result review SHA mismatch")
    lock=ROOT/score_lock["source_lock_path"]
    if sha(lock)!=source_freeze["source_lock_sha256"]:raise ValueError("source lock SHA mismatch")
    if sha(BUILDER_PATH)!=score_lock["train_builder_sha256"]:raise ValueError("locked TRAIN builder SHA mismatch")
    for relative,expected in score_lock["feature_code_hashes"].items():
        if sha(ROOT/relative)!=expected:raise ValueError(f"locked feature source SHA mismatch: {relative}")
    checkpoint_path=ROOT/score_lock["checkpoint_path"]
    weights_path=ROOT/score_lock["matlab_weights_path"]
    checkpoint_hash=sha(checkpoint_path);weights_hash=sha(weights_path)
    if checkpoint_hash!=score_lock["checkpoint_sha256"] or weights_hash!=score_lock["matlab_weights_sha256"]:raise ValueError("model/weights SHA mismatch")
    if checkpoint_hash!="9c924f1566447644287595253026e035b2fcb716a57be0e60d6f04bafdd8ed74":raise ValueError("unexpected model checkpoint")
    if weights_hash!="dfbad11dbc7ed19b42d3b536bb4b019cbf29209d69c904b0b5000a168af58819":raise ValueError("unexpected MATLAB weights")
    if len(source_freeze.get("records",[]))!=48 or source_freeze.get("validation_split")!="C5_VAL48":raise ValueError("VAL source freeze is not exactly 48 scenes")
    if identity.get("files_checked")!=144 or identity.get("failures"):raise ValueError("VAL raw/status/run_start identities are not clean")
    if "TEST" in str(OUT).upper():raise ValueError("TEST path is prohibited")
    start_path=OUT/"C5_VAL48_SCORE_STARTED_v1.json"
    progress_path=OUT/"VAL_BUILD_PROGRESS_v1.jsonl"
    causal_gate_path=OUT/"VAL_CAUSAL_GATE_v1.json"
    arrays_path=OUT/"C5_VAL48_RESIDUAL_DIAGNOSTIC_v1.npz"
    score_path=OUT/"C5_VAL48_SCORE_RESULT_v1.json"
    summary_path=OUT/"C5_VAL48_SCORE_SUMMARY_v1.json"
    receipt_path=OUT/"C5_VAL48_DIAGNOSTIC_RECEIPT_v1.json"
    for p in (start_path,progress_path,causal_gate_path,arrays_path,score_path,summary_path,receipt_path):
        if p.exists():raise FileExistsError(f"one-shot score output already exists: {p}")
    # Rehash every locked raw/status/run_start file as bytes before numeric array access.
    for rec in source_freeze["records"]:
        for path_key,hash_key in (("raw_path","raw_sha256"),("status_path","status_sha256"),("run_start_path","run_start_sha256")):
            source=ROOT/rec[path_key]
            if not source.is_file() or sha(source)!=rec[hash_key]:raise ValueError(f"VAL source SHA changed for {rec['scene_id']} {path_key}")
    checkpoint=torch.load(checkpoint_path,map_location="cpu",weights_only=True)
    if int(checkpoint.get("step",-1))!=60000 or int(checkpoint.get("seed",-1))!=2026102001 or checkpoint.get("train_split")!="TRAIN_C5_24":raise ValueError("candidate checkpoint identity mismatch")
    if checkpoint.get("config_sha256")!=sha(config_path) or checkpoint.get("freeze_manifest_sha256")!=sha(freeze_path):raise ValueError("checkpoint binding mismatch")
    if not np.allclose(checkpoint["input_mean"].numpy(),np.asarray(config["input_mean"],dtype=np.float64),rtol=0,atol=1e-12):raise ValueError("input mean is not the frozen TRAIN normalizer")
    if not np.allclose(checkpoint["input_std"].numpy(),np.asarray(config["input_std"],dtype=np.float64),rtol=0,atol=1e-12):raise ValueError("input std is not the frozen TRAIN normalizer")
    if not np.allclose(checkpoint["target_rms"].numpy(),np.asarray(config["target_rms_from_train_only_rad_s2"],dtype=np.float64),rtol=0,atol=1e-12):raise ValueError("target RMS is not the frozen TRAIN normalizer")
    sys.path.insert(0,str(STUDY))
    from prepare_train_data_v1 import build_scene
    builder_source=inspect.getsource(build_scene)
    required_builder_contract=("def build_scene(", '"record": record, "time": time[EVENTS]',
      '"start_indices": EVENTS - 10', '"issued_torque_last_indices": EVENTS - 1')
    if any(fragment not in builder_source for fragment in required_builder_contract):
        raise ValueError("TRAIN builder build_scene return-info/causal event contract changed")
    builder_info_contract={"info_keys":["record","time","start_indices","issued_torque_last_indices"],
      "feature_event_indices":"EVENTS=10..19990 step 10; feature rows at state sample e",
      "residual_state_endpoints":"[e-10,e] inclusive","issued_torque_transition_indices":"[e-10,e-1] inclusive"}
    if preflight_only:
        print(json.dumps({"status":"PREFLIGHT_PASS","source_scenes":48,"identity_files_checked":144,
          "all_identity_hashes_match":True,"checkpoint_sha256":checkpoint_hash,"matlab_weights_sha256":weights_hash,
          "score_script_sha256":sha(script),"score_lock_sha256":sha(score_lock_path),
          "eval_rules_sha256":sha(rules_path),"builder_info_contract":builder_info_contract,
          "numeric_VAL_arrays_read":False,"score_start_marker_created":False,
          "TEST_accessed":False,"Plant_called":False,"training_run":False},ensure_ascii=False),flush=True)
        return
    parity_manifest_path=ROOT/score_lock["matlab_parity_manifest_path"]
    parity_manifest_sha=sha(parity_manifest_path)
    if parity_manifest_sha!=score_lock["matlab_parity_manifest_sha256"]:raise ValueError("MATLAB parity manifest SHA mismatch")
    if score_lock.get("matlab_parity_status")!="PASS_NO_PLANT":raise ValueError("root-bound MATLAB no-Plant parity is not approved")
    try: parity_manifest_path.resolve().relative_to(OUT.resolve())
    except ValueError as exc: raise ValueError("MATLAB parity manifest must be under the isolated diagnostic folder") from exc
    parity_artifacts=score_lock.get("matlab_parity_artifacts",[])
    if len(parity_artifacts)<3:raise ValueError("MATLAB parity output hashes are incomplete")
    for item in parity_artifacts:
        artifact_path=ROOT/item["path"]
        try: artifact_path.resolve().relative_to(OUT.resolve())
        except ValueError as exc: raise ValueError("MATLAB parity artifact must be inside the diagnostic folder") from exc
        if sha(artifact_path)!=item["sha256"]:raise ValueError(f"MATLAB parity output SHA mismatch: {item['path']}")
    write_new_json(start_path,{"schema":"DL1018_MLP15_C5_VAL48_SCORE_START_V1","status":"STARTED_ONE_SHOT",
      "score_script_sha256":sha(script),"score_lock_sha256":sha(score_lock_path),"source_freeze_sha256":sha(source_freeze_path),
      "eval_rules_sha256":sha(rules_path),"matlab_parity_manifest_sha256":parity_manifest_sha,
      "started_unix_time":time.time(),"numeric_VAL_read_started":True,
      "scores_completed_at_start":0,"TEST_accessed":False,"Plant_called":False,"training_run":False})
    J0=np.diag(np.asarray(config["fixed_J0_diagonal_kg_m2"],dtype=np.float64))
    rows=[]; feature_parts=[]; target_parts=[]; time_parts=[]; gate_records=[]
    with progress_path.open("x",encoding="utf-8") as progress:
        for index,row in enumerate(source_freeze["records"],start=1):
            features,targets,info=build_scene(row,J0)
            record=info["record"]
            record["split"]="C5_VAL48"
            if record["scene_id"]!=row["scene_id"] or record["raw_sha256"]!=row["raw_sha256"]:raise ValueError("builder source identity drift")
            if features.shape!=(1999,13) or targets.shape!=(1999,3) or info["time"].shape!=(1999,):raise ValueError(f"VAL array shape mismatch: {row['scene_id']}")
            if not np.isfinite(features).all() or not np.isfinite(targets).all():raise ValueError(f"non-finite reconstructed VAL array: {row['scene_id']}")
            event_ix=np.asarray(EVENTS,dtype=np.int64)
            start_ix=np.asarray(info["start_indices"],dtype=np.int64)
            issued_last=np.asarray(info["issued_torque_last_indices"],dtype=np.int64)
            if not (np.array_equal(event_ix,EVENTS) and np.array_equal(start_ix,event_ix-10)
                    and np.array_equal(issued_last,event_ix-1)
                    and record["label_endpoint_max_state_sample_index"]==int(event_ix[-1])
                    and record["label_endpoint_max_issued_torque_transition_index"]==int(event_ix[-1]-1)
                    and float(info["time"][-1])==record["max_label_time_s"]):
                raise ValueError(f"VAL residual endpoint/command causality check failed: {row['scene_id']}")
            if record["max_endpoint_formula_equivalence_abs_error_rad_s2"]>1e-9:raise ValueError(f"VAL endpoint formula mismatch: {row['scene_id']}")
            rows.append(record);feature_parts.append(features);target_parts.append(targets);time_parts.append(info["time"])
            gate_records.append({"scene_id":row["scene_id"],"events":len(event_ix),
              "feature_time_first_last_s":[float(info["time"][0]),float(info["time"][-1])],
              "state_endpoint_indices_first_last":[int(event_ix[0]),int(event_ix[-1])],
              "issued_torque_transition_indices_first_last":[int(issued_last[0]),int(issued_last[-1])],
              "endpoint_formula_equiv_max_abs_error_rad_s2":record["max_endpoint_formula_equivalence_abs_error_rad_s2"],
              "generalized_clipped_true_count":record["generalized_clipped_true_count"],
              "motor_saturated_true_count":record["motor_saturated_true_count"],
              "controller_clip_command_max_abs_error":record["controller_clip_command_max_abs_error"]})
            progress.write(json.dumps({"scene_index":index,"scene_id":row["scene_id"],"status":"FEATURE_LABEL_BUILD_PASS"})+"\n");progress.flush()
            print(json.dumps({"scene_index":index,"scene_id":row["scene_id"],"status":"FEATURE_LABEL_BUILD_PASS"}),flush=True)
    if len(rows)!=48:raise ValueError("not all 48 VAL scenes were reconstructed")
    X=np.stack(feature_parts,axis=0).astype(np.float64);Y=np.stack(target_parts,axis=0).astype(np.float64)
    event_time=np.stack(time_parts,axis=0).astype(np.float64)
    ids=[r["scene_id"] for r in rows]
    if ids!=source_freeze["scene_ids"]:raise ValueError("VAL scene order differs from frozen source lock")
    causal_gate={"schema":"DL1018_MLP15_C5_VAL48_CAUSAL_GATE_V1","status":"PASS_CAUSAL_PRECONDITIONS",
      "scene_count":48,"event_count":int(X.shape[0]*X.shape[1]),"causal_records":gate_records,
      "all_endpoint_indices_equal_feature_event":True,"all_issued_torque_last_indices_endpoint_minus_one":True,
      "all_endpoint_equivalence_errors_le_1e_9":True,"all_allocator_motor_clip_checks_passed":True,
      "numeric_VAL_read":True,"causal_checks_passed_before_scoring":True,
      "scoring_started":False,"scoring_completed":False,"scores_completed":0,
      "TEST_accessed":False,"Plant_called":False}
    # Store VAL-only arrays; this is never concatenated with or used to update TRAIN data/statistics.
    np.savez_compressed(arrays_path,x_val=X,y_val=Y,scene_ids=np.asarray(ids,dtype="U32"),
      event_indices=EVENTS,label_start_state_indices=EVENTS-10,label_endpoint_state_indices=EVENTS,
      issued_torque_last_transition_indices=EVENTS-1,event_time_s=event_time)
    # Exactly one model forward pass across all 48 x 1999 events.
    raw_prediction=model_predict_once(X,checkpoint)
    dmax=np.asarray(config["runtime_output_clip_rad_s2"],dtype=np.float64)
    clipped_prediction=np.clip(raw_prediction,-dmax,dmax)
    candidate_error=clipped_prediction-Y
    zero_prediction=np.zeros_like(Y)
    zero_error=zero_prediction-Y
    candidate_metrics=metric_summary(candidate_error,ids)
    zero_metrics=metric_summary(zero_error,ids)
    causal_gate.update({"status":"PASS_SCORE_COMPLETED","scoring_started":True,
      "scoring_completed":True,"scores_completed":1,"score_result_path":score_path.name})
    write_new_json(causal_gate_path,causal_gate)
    def clip_info(pred):
        count=np.count_nonzero(np.abs(pred)>dmax,axis=(0,1))
        total=pred.shape[0]*pred.shape[1]
        return {axis:{"count":int(count[i]),"fraction":float(count[i]/total)} for i,axis in enumerate(AXES)}
    per_scene=[]
    for i,sid in enumerate(ids):
        per_scene.append({"scene_id":sid,"wind_group":sid.rsplit("_",1)[-1],
          "candidate_axis_rmse_rad_s2":dict(zip(AXES,np.sqrt(np.mean(candidate_error[i]**2,axis=0)).tolist())),
          "zero_baseline_axis_rmse_rad_s2":dict(zip(AXES,np.sqrt(np.mean(zero_error[i]**2,axis=0)).tolist())),
          "candidate_scene_rmse_rad_s2":float(np.sqrt(np.mean(candidate_error[i]**2))),
          "zero_baseline_scene_rmse_rad_s2":float(np.sqrt(np.mean(zero_error[i]**2)))})
    result={"schema":"DL1018_MLP15_C5_VAL48_SCORE_RESULT_V1","status":"PASS_ONE_SHOT_OFFLINE_SCORE",
      "source_freeze_manifest_sha256":sha(source_freeze_path),"identity_check_sha256":sha(identity_path),
      "eval_rules_sha256":sha(rules_path),"score_lock_sha256":sha(score_lock_path),
      "matlab_parity_manifest_path":str(parity_manifest_path.relative_to(ROOT)).replace("\\","/"),
      "matlab_parity_manifest_sha256":parity_manifest_sha,
      "matlab_parity_status":"PASS_NO_PLANT",
      "matlab_parity_artifacts":parity_artifacts,
      "checkpoint_sha256":checkpoint_hash,"validation_split":"C5_VAL48","scene_count":48,"event_count":95952,
      "candidate":"frozen MLP15 base output, TRAIN-only normalization, fixed dmax clipping, pre-beta; no online-head adaptation",
      "candidate_metrics":candidate_metrics,"zero_compensation_baseline_metrics":zero_metrics,
      "candidate_clipping":clip_info(raw_prediction),"zero_baseline_clipping":clip_info(zero_prediction),
      "target_distribution_by_axis":stats(Y),"candidate_raw_output_distribution_by_axis":stats(raw_prediction),
      "candidate_clipped_output_distribution_by_axis":stats(clipped_prediction),"zero_baseline_output_distribution_by_axis":stats(zero_prediction),
      "target_outside_runtime_dmax_count_by_axis":clip_info(Y),"per_scene":per_scene,
      "source_records":rows,"validation_used_for_fit":False,"validation_used_for_normalization":False,
      "checkpoint_selection":False,"hyperparameter_search":False,"code_changed_after_validation":False,
      "TEST_accessed":False,"Plant_called":False,"training_run":False,
      "claim_boundary":"reused C5_VAL48 offline diagnostic; not independent TEST evidence and not a closed-loop result"}
    write_new_json(score_path,result)
    score_summary={"schema":"DL1018_MLP15_C5_VAL48_SCORE_SUMMARY_V1","status":"PASS",
      "scores_completed":1,"scene_count":48,"event_count":95952,"candidate_scene_macro_rmse_rad_s2":candidate_metrics["scene_macro_rmse_rad_s2"],
      "zero_baseline_scene_macro_rmse_rad_s2":zero_metrics["scene_macro_rmse_rad_s2"],
      "candidate_axis_pooled_rmse_rad_s2":candidate_metrics["axis_pooled_rmse_rad_s2"],
      "zero_baseline_axis_pooled_rmse_rad_s2":zero_metrics["axis_pooled_rmse_rad_s2"],
      "TEST_accessed":False,"Plant_called":False}
    write_new_json(summary_path,score_summary)
    output_paths=(start_path,progress_path,causal_gate_path,arrays_path,score_path,summary_path)
    receipt={"schema":"DL1018_MLP15_C5_VAL48_DIAGNOSTIC_RECEIPT_V1","status":"PASS_ONE_SHOT_OFFLINE_DIAGNOSTIC",
      "score_script_path":str(script.relative_to(ROOT)).replace("\\","/"),"score_script_sha256":sha(script),
      "score_lock_sha256":sha(score_lock_path),"source_freeze_manifest_sha256":sha(source_freeze_path),
      "identity_check_sha256":sha(identity_path),"eval_rules_sha256":sha(rules_path),
      "checkpoint_sha256":checkpoint_hash,"matlab_weights_sha256":weights_hash,
      "matlab_parity_manifest_path":str(parity_manifest_path.relative_to(ROOT)).replace("\\","/"),
      "matlab_parity_manifest_sha256":parity_manifest_sha,
      "matlab_parity_artifacts":parity_artifacts,
      "candidate_vs_zero_compensation_baseline":score_summary,
      "output_sha256":{p.name:sha(p) for p in output_paths},
      "validation_score_count":1,"training_run":False,"TEST_accessed":False,"Plant_called":False,
      "reused_validation_not_independent_test":True,"closed_loop_claim":False}
    write_new_json(receipt_path,receipt)
    receipt_hash=sha(receipt_path)
    score_summary["receipt_sha256"]=receipt_hash
    print(json.dumps(score_summary,ensure_ascii=False),flush=True)


def main()->None:
    p=argparse.ArgumentParser()
    for name in ("config","freeze_manifest","source_freeze","identity_check","eval_rules","score_lock"):
        p.add_argument("--"+name.replace("_","-"),type=Path,required=True)
    p.add_argument("--preflight",action="store_true",help="check identity/config/API only; does not read numeric VAL data")
    a=p.parse_args()
    run(a.config,a.freeze_manifest,a.source_freeze,a.identity_check,a.eval_rules,a.score_lock,a.preflight)
if __name__=="__main__":main()
