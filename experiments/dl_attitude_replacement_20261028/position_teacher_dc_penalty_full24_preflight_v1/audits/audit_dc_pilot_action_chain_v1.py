#!/usr/bin/env python3
"""Post-run read-only check of DC residual, C5 base, ZOH hold, and force path."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import h5py
import numpy as np

HERE=Path(__file__).resolve().parent;STUDY=HERE.parent
SCENE="DL1018_VAL_T3_C01_W14";ATTEMPT=STUDY/"runs"/SCENE/"attempt_001"
RAW=ATTEMPT/"raw_run.mat";STATUS=ATTEMPT/"run_status.json";START=ATTEMPT/"run_start.json"
RELEASE=STUDY/"RELEASE.json";LOCK=STUDY/"SOURCE_LOCK_v1.json"
SCORE=HERE/"DC_PENALTY_SINGLE_PILOT_SCORE_v1.json"
OUT=HERE/"DC_PENALTY_PILOT_ACTION_CHAIN_AUDIT_v1.json"

def sha(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""):h.update(b)
    return h.hexdigest()
def read(path:Path)->dict:return json.loads(path.read_text(encoding="utf-8-sig"))
def scalar(log,n):return float(np.asarray(log[n][()]).reshape(-1)[0])
def vec(log,n):return np.asarray(log[n][()]).reshape(-1)
def mat(log,n):return np.asarray(log[n][()]).T

def main()->None:
    if OUT.exists():raise RuntimeError(f"Refusing to overwrite {OUT}")
    rel,status,start=read(RELEASE),read(STATUS),read(START);lock=read(LOCK)
    if (sha(LOCK)!=rel["source_lock_sha256"] or status.get("source_lock_sha256")!=rel["source_lock_sha256"] or
        status.get("state")!="COMPLETED" or status.get("status_value")!="STABLE" or
        status.get("plant_calls")!=1 or status.get("transitions")!=20000 or
        status.get("state_samples")!=20001 or status.get("test_data_read") is not False or
        sha(RAW)!=status.get("raw_sha256") or sha(RELEASE)!=status.get("release_sha256") or
        start.get("release_sha256")!=sha(RELEASE) or not (ATTEMPT/"first_plant_step.marker").is_file()):
        raise RuntimeError("Single-call raw/status/release binding failed")
    for rec in lock["files"]:
        p=STUDY/rec["relative_path"]
        if not p.is_file() or sha(p).lower()!=rec["sha256"].lower():raise RuntimeError(f"Locked source changed: {rec['relative_path']}")
    for rec in lock["external_inputs"]:
        p=Path(rec["path"])
        if not p.is_file() or sha(p).lower()!=rec["sha256"].lower():raise RuntimeError(f"External source changed: {rec['name']}")
    with h5py.File(RAW,"r") as f:
        log=f["log"];t=vec(log,"time")[:-1]
        event=vec(log,"stage1_position_event").astype(bool)
        residual_event=vec(log,"stage1_position_residual_gru_event").astype(bool)
        ready=vec(log,"stage1_position_residual_gru_ready").astype(bool)
        beta=vec(log,"stage1_position_residual_gru_beta")
        raw_delta=mat(log,"stage1_position_residual_gru_raw_delta_mps2")
        delta=mat(log,"stage1_position_residual_gru_clipped_delta_mps2")
        base=mat(log,"stage1_position_residual_gru_base_action_mps2")
        action=mat(log,"stage1_position_residual_gru_action_mps2")
        correction=mat(log,"stage1_position_residual_gru_applied_correction_mps2")
        c5=mat(log,"stage1_position_event_applied_acceleration_mps2")
        held=mat(log,"stage1_position_held_applied_acceleration_mps2")
        held_force=mat(log,"stage1_position_held_force_I_N")
        injected_force=mat(log,"stage1_position_injected_force_I_N")
        total_clip=vec(log,"stage1_position_residual_gru_total_clip_active")
        logged_weights=np.asarray(log["stage1_position_residual_gru_weights_sha256"][()]).reshape(-1)
        weights_sha="".join(chr(int(v)) for v in logged_weights if int(v))
        event_count=int(round(scalar(log,"stage1_position_residual_gru_event_count")))
        enabled=bool(round(scalar(log,"stage1_position_residual_gru_enabled")))
    idx=np.flatnonzero(event);ready_idx=idx[ready[idx]]
    if not enabled or not np.array_equal(event,residual_event) or len(idx)!=1999 or len(ready_idx)!=1968 or event_count!=1999:
        raise RuntimeError("Event flags or ready count mismatch")
    if weights_sha.lower()!=rel["position_residual_gru"]["weights_sha256"].lower():
        raise RuntimeError("Raw log model identity differs from release")
    beta_expected=np.clip(t[idx]/1.8,0,1)
    delta_expected=np.clip(raw_delta[idx],-.5,.5);delta_expected[~ready[idx]]=0
    action_expected=np.clip(base[idx]+beta_expected[:,None]*delta_expected,-3,3);action_expected[~ready[idx]]=0
    e_beta=float(np.max(np.abs(beta[idx]-beta_expected)))
    e_delta=float(np.max(np.abs(delta[idx]-delta_expected)))
    e_action=float(np.max(np.abs(action[idx]-action_expected)))
    e_correction=float(np.max(np.abs(correction[idx]-(action_expected-base[idx]))))
    e_base=float(np.max(np.abs(base[ready_idx]-c5[ready_idx])))
    if max(e_beta,e_delta,e_action,e_correction,e_base)>1e-12 or np.any(total_clip!=0):
        raise RuntimeError("Residual/C5 output action chain differs from declared formula")
    event_actions={int(k):action[k] for k in idx};forward=np.zeros_like(held);last=np.zeros(3)
    for k in range(len(t)):
        if k in event_actions:last=event_actions[k]
        forward[k]=last
    e_hold=float(np.max(np.abs(held-forward)));e_injection=float(np.max(np.abs(injected_force-held_force)))
    mass=float(np.sum(held*held_force)/np.sum(held**2))
    e_force=float(np.max(np.abs(held_force-mass*held)))
    if max(e_hold,e_injection,e_force)>1e-12 or abs(mass-.695)>1e-12:
        raise RuntimeError("Actual event-ZOH/force injection chain mismatch")
    score=read(SCORE);safety=score["safety"]
    if any(int(safety[k])!=0 for k in ("motor_saturation_samples","generalized_clip_samples","tilt_limited_samples",
                                        "attitude_head_projection_samples","attitude_head_output_saturated_samples")):
        raise RuntimeError("Scored safety counters are nonzero")
    report={"schema":"POSITION_TEACHER_DC_PENALTY_PILOT_ACTION_CHAIN_AUDIT_V1",
        "status":"PASS_BINDING_EVENTWISE_ACTION_AND_FORCE_CHAIN","scope":"Post-run read-only audit; one fixed VAL diagnostic, not independent validation.",
        "study_id":rel["study_id"],"scene_id":SCENE,"plant_calls_actual":1,
        "raw_path":str(RAW.resolve()),"raw_sha256":sha(RAW),"status_path":str(STATUS.resolve()),"status_sha256":sha(STATUS),
        "release_sha256":sha(RELEASE),"source_lock_sha256":sha(LOCK),"source_lock_file_count":len(lock["files"]),
        "weights_sha256_logged":weights_sha,"event_count":int(len(idx)),"ready_event_count":int(len(ready_idx)),
        "first_event_time_s":float(t[idx[0]]),"first_ready_event_index_zero_based":31,"first_ready_time_s":float(t[ready_idx[0]]),
        "action_chain_max_abs_errors":{"beta":e_beta,"clipped_delta_mps2":e_delta,"action_mps2":e_action,
            "applied_correction_mps2":e_correction,"C5_post_PCF_base_vs_stage1_event_action_mps2":e_base},
        "held_1ms_action_forward_zoh_max_abs_error_mps2":e_hold,
        "injected_force_vs_held_force_max_abs_error_N":e_injection,"force_vs_inferred_mass_action_max_abs_error_N":e_force,
        "inferred_mass_kg":mass,"total_action_clip_event_count":int(np.count_nonzero(total_clip)),
        "safety":safety,"TEST_read":False,"inertia_reconstruction_enabled":False,
        "audit_script_path":str(Path(__file__).resolve()),"audit_script_sha256":sha(Path(__file__)),"postrun_only":True}
    OUT.write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2),flush=True)
if __name__=="__main__":main()
