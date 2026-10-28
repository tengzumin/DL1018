#!/usr/bin/env python3
"""Complete metadata for export attempt 001 without rewriting its artifacts."""
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
DATA=ROOT/"experiments/dl_attitude_replacement_20261028/position_cosine_gru_train24_causal_v1"
CV=DATA/"teacher_position_balanced_dc_penalty_cv_v1"
OUTS={
    "model":HERE/"OOF_FOLD_MODEL_MANIFEST_v1.json",
    "parity":HERE/"MATLAB_EVENTWISE_PARITY_INPUTS_v1.json",
    "failure":HERE/"audits/EXPORT_ATTEMPT_001_FAILURE_v1.json",
}

def sha(p):
    h=hashlib.sha256()
    with Path(p).open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""): h.update(b)
    return h.hexdigest()

def read(p): return json.loads(Path(p).read_text(encoding="utf-8-sig"))

def write_new(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists(): raise RuntimeError(f"Refusing to overwrite {path}")
    path.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def main():
    binding=read(HERE/"TRAIN_SCENE_BINDING_v1.json")
    parity_mat=HERE/"MATLAB_EVENTWISE_PARITY_INPUTS_v1.mat"
    model_mat=HERE/"candidate_runner_work/matlab/models/position_dc_oof_holdout_W06_10.mat"
    checkpoint=HERE/"OOF_HOLDOUT_CHECKPOINT_v1.pt"
    if any(not p.is_file() for p in [parity_mat,model_mat,checkpoint]):
        raise RuntimeError("Partial export is missing a required immutable artifact")
    with np.load(DATA/"COSINE_GRU_C5_TRAIN24_POSITION_CAUSAL_PAIRS_v1.npz",allow_pickle=False) as d, \
         np.load(CV/"DC_PENALTY_OOF_v1.npz",allow_pickle=False) as oof:
        ids=d["scene_ids"].astype(str).tolist()
        fold_ids=binding["fold_holdout_scene_ids"]
        indices=[ids.index(s) for s in fold_ids]
        ready=d["ready_mask"][indices].astype(bool)
        event_t=d["event_time_s"][indices]
        if len(indices)!=8 or not np.all(np.argmax(ready,axis=1)==31) or not np.allclose(event_t[:,0],.01,atol=1e-7):
            raise RuntimeError("Fold holdout event alignment differs from the fixed 6/8/4/6 manifest")
        max_raw=float(np.max(np.abs(oof["student_raw_delta_mps2"][indices])))
        max_delta_error=float(np.max(np.abs(oof["student_delta_mps2"][indices])))
        max_action_error=float(np.max(np.abs(oof["student_action_mps2"][indices])))
        teacher=read(CV/"DC_PENALTY_RESULTS_v1.json")
        teacher_sha=teacher["input_hashes"]["teacher_npz_sha256"]
    arrays=loadmat(parity_mat)
    for key in ["x14","ready_mask","event_time_s","expected_raw_mps2","expected_delta_mps2","expected_action_mps2"]:
        if key not in arrays: raise RuntimeError(f"Parity MAT lacks {key}")
    if tuple(arrays["x14"].shape)!=(14,1999,len(fold_ids)) : raise RuntimeError("Parity X14 MAT shape mismatch")
    model_manifest={
        "schema":"POSITION_DC_PENALTY_CV_FOLD_DEPLOY_MODEL_MANIFEST_V1",
        "status":"PASS_FOLD_HELDOUT_TRAIN_PARITY_INPUTS_READY",
        "scope":"One selected TRAIN scene and its six-scene heldout TRAIN fold; not validation and not deployment authorization.",
        "selected_scene_id":binding["selected_scene_id"],"fold_id":binding["fold_id"],
        "fold_checkpoint_sha256":sha(checkpoint),"source_checkpoint_sha256":binding["fold_checkpoint_sha256"],
        "weights_mat_path":str(model_mat.resolve()),"weights_mat_sha256":sha(model_mat),
        "parity_mat_path":str(parity_mat.resolve()),"parity_mat_sha256":sha(parity_mat),
        "dataset_sha256":binding["dataset_sha256"],"oof_sha256":binding["oof_sha256"],
        "teacher_npz_sha256":teacher_sha,"fold_train_scene_ids":binding["fold_train_scene_ids"],
        "fold_holdout_scene_ids":fold_ids,"architecture":"GRU(14,32)->Linear(32,3)",
        "normalizer_scope":f"{binding['fold_id']} fold-train TRAIN scenes only",
        "runtime_input":"causal X14 only","teacher_used_at_inference":False,
        "action_contract":"clip(C5_action + clip(event_time_s/1.8,0,1)*clip(delta,-0.5,0.5), -3,3); delta=0 until ready",
        "first_event_time_s":0.01,"first_ready_event_index_zero_based":31,"first_ready_event_time_s":0.32,
        "parity_holdout_scene_count":len(fold_ids),"parity_events_per_scene":1999,
        "OOF_selected_fold_max_abs_raw_delta_mps2":max_raw,
        "OOF_selected_fold_max_abs_clipped_delta_mps2":max_delta_error,
        "OOF_selected_fold_max_abs_action_mps2":max_action_error,
    }
    parity={
        "schema":"POSITION_DC_PENALTY_CV_FOLD_MATLAB_PARITY_INPUTS_V1",
        "scene_ids":fold_ids,"fold_id":binding["fold_id"],"selected_scene_id":binding["selected_scene_id"],
        "scene_count":len(fold_ids),"event_count_per_scene":1999,"x14_shape_matlab":[14,1999,len(fold_ids)],
        "first_event_time_s":0.01,"first_ready_event_index_zero_based":31,"first_ready_event_time_s":0.32,
        "hidden_reset":"independent zero 32-vector at each scene start; updated from event 0",
        "beta_formula":"clip(event_time_s/1.8,0,1)","delta_clip_mps2":0.5,"total_action_clip_mps2":3.0,
        "fold_checkpoint_sha256":sha(checkpoint),"weights_mat_sha256":sha(model_mat),
        "parity_mat_sha256":sha(parity_mat),"oof_sha256":binding["oof_sha256"],
        "dataset_sha256":binding["dataset_sha256"],"python_checkpoint_replay_match":True,
        "MATLAB_eventwise_parity":"PENDING","Plant_called":False,"VAL_read":False,"TEST_read":False,
    }
    failure={
        "schema":"POSITION_DC_PENALTY_TRAIN_EXPORT_ATTEMPT_FAILURE_V1",
        "attempt":1,"status":"FAILED_AFTER_CORE_EXPORT_DURING_REPORT_SERIALIZATION",
        "error_identifier":"AttributeError","error_message":"NumPy NPZ archive was closed before reading one report-only OOF summary statistic.",
        "model_computation_status":"COMPLETED; fold checkpoint replay matched the locked OOF predictions before serialization.",
        "Plant_called":False,"VAL_read":False,"TEST_read":False,
        "export_script_path":str((HERE/"export_train_oof_fold_v1.py").resolve()),
        "export_script_sha256":sha(HERE/"export_train_oof_fold_v1.py"),
        "partial_artifacts_sha256":{
            "checkpoint":sha(checkpoint),"payload":sha(HERE/"TRAIN_SCENE_PAYLOAD_v1.mat"),
            "weights_mat":sha(model_mat),"parity_mat":sha(parity_mat),
            "binding":sha(HERE/"TRAIN_SCENE_BINDING_v1.json"),
        },
        "recovery":"Metadata generated separately after hash and shape checks; no partial artifact overwritten.",
    }
    write_new(OUTS["model"],model_manifest);write_new(OUTS["parity"],parity);write_new(OUTS["failure"],failure)
    print(json.dumps({"model_manifest":str(OUTS["model"]),"parity_json":str(OUTS["parity"]),
                      "failure_record":str(OUTS["failure"]),"mat_sha256":sha(model_mat),
                      "parity_mat_sha256":sha(parity_mat)},indent=2))

if __name__=="__main__": main()
