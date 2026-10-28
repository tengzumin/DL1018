"""Frozen-score and logged signal-route audit for the completed notch+tau01 run."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import h5py
import numpy as np


HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
ROOT = STUDY.parents[2]
SCENE = "DL1018_VAL_T3_C01_W14"
RUN = STUDY / "runs" / SCENE
RAW = RUN / "raw_run.mat"
START = RUN / "run_start.json"
STATUS = RUN / "run_status.json"
RELEASE = STUDY / "RELEASE.json"
LOCK = STUDY / "SOURCE_LOCK_v1.json"
SCORE = ROOT / "experiments/dl_attitude_replacement_20261028/gru_prediction_tau01_v1/audits/GRU_PREDICTION_TAU01_SCORE_final12.json"
SINGLE_NOTCH_AUDIT = ROOT / "experiments/dl_attitude_replacement_20261028/gru_cosine_c5_applied_notch_35hz_q1_v1/audits/NOTCH_SINGLE_SCENE_FROZEN_SCORE_AUDIT_v2.json"
OUT_JSON = HERE / "NOTCH_TAU01_SINGLE_SCENE_SCORE_ROUTE_AUDIT_v1.json"
OUT_MD = HERE / "NOTCH_TAU01_SINGLE_SCENE_SCORE_ROUTE_AUDIT_v1.md"
MASS, DT, EVENT_DT = 0.695, 0.001, 0.01


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with Path(p).open("rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def readj(p: Path) -> dict:
    return json.loads(Path(p).read_text(encoding="utf-8-sig"))


def arr3(g: h5py.Group, name: str, n: int) -> np.ndarray:
    x = np.asarray(g[name][()], dtype=float)
    if x.shape == (3, n):
        x = x.T
    if x.shape != (n, 3):
        raise RuntimeError(f"{name} shape mismatch: {x.shape}")
    return x


def audit_run() -> dict:
    start, status = readj(START), readj(STATUS)
    raw_hash, release_hash, lock_hash = sha(RAW), sha(RELEASE), sha(LOCK)
    if (start["scene_id"] != SCENE or status["scene_id"] != SCENE or
        status["state"] != "COMPLETED" or status["status_value"] != "STABLE" or
        status["safety_stop_reason"] != "" or status["transitions"] != 20000 or
        status["state_samples"] != 20001 or status["Plant_calls"] != 1 or
        status["TEST_read"] is not False or status["raw_sha256"].lower() != raw_hash.lower() or
        Path(status["raw_path"]).resolve() != RAW.resolve()):
        raise RuntimeError("raw/status completion binding failed")
    if (sha(STATUS) == "" or status["release_sha256"].lower() != start["release_sha256"].lower() or
        release_hash.lower() != start["release_sha256"].lower() or
        lock_hash.lower() != start["source_lock_sha256"].lower()):
        raise RuntimeError("run release/source-lock SHA binding failed")
    lock = readj(LOCK)
    verified = 0
    for rec in lock["files"]:
        p = STUDY / rec["path"]
        if not p.is_file() or sha(p).lower() != rec["sha256"].lower():
            raise RuntimeError(f"locked source file mismatch: {rec['path']}")
        verified += 1
    payload = Path(start["scene_payload_path"])
    if sha(payload).lower() != start["scene_payload_sha256"].lower():
        raise RuntimeError("scene payload hash mismatch")
    parent_notch_release = Path(readj(RELEASE)["parent_notch_hf6_release_path"])
    parent_notch_lock = Path(readj(RELEASE)["parent_notch_hf6_source_lock_path"])
    if (sha(parent_notch_release).lower() != start["parent_notch_hf6_release_sha256"].lower() or
        sha(parent_notch_lock).lower() != start["parent_notch_hf6_source_lock_sha256"].lower()):
        raise RuntimeError("parent notch run binding mismatch")

    with h5py.File(RAW, "r") as f:
        l, ident = f["log"], f["runIdentity"]
        time = np.asarray(l["transition_time"][()], dtype=float).reshape(-1)
        n = len(time)
        event = np.asarray(l["stage1_position_event"][()], dtype=bool).reshape(-1)
        valid = np.asarray(l["stage1_position_event_inference_valid"][()], dtype=bool).reshape(-1)
        idx = np.flatnonzero(event)
        x = arr3(l, "stage1_position_applied_notch_event_input_mps2", n)
        yraw = arr3(l, "stage1_position_applied_notch_event_output_raw_mps2", n)
        yapplied = arr3(l, "stage1_position_applied_notch_event_output_applied_mps2", n)
        limit = arr3(l, "stage1_position_applied_notch_event_output_limit_mps2", n)
        clip_flag = arr3(l, "stage1_position_applied_notch_event_clip_active", n).astype(bool)
        head_event = arr3(l, "stage1_position_event_applied_acceleration_mps2", n)
        head_held = arr3(l, "stage1_position_held_applied_acceleration_mps2", n)
        comp = arr3(l, "position_compensation_applied_acceleration_mps2", n)
        comp_force = arr3(l, "position_compensation_applied_force_N", n)
        held_force = arr3(l, "stage1_position_held_force_I_N", n)
        injected_force = arr3(l, "stage1_position_injected_force_I_N", n)
        nominal = arr3(l, "position_nominal_acceleration_mps2", n)
        commanded_force = arr3(l, "position_commanded_force_N", n)
        pcf_areq = arr3(l, "stage1_position_pcf_a_req_mps2", n)
        b = np.asarray(ident["notch_b"][()], float).reshape(-1)
        a = np.asarray(ident["notch_a"][()], float).reshape(-1)
        initial = np.asarray(ident["notch_initial_state"][()], float)
        tau = float(np.asarray(ident["position_delayed_prediction_tau_s"][()]).squeeze())
        rho = float(np.asarray(ident["position_delayed_prediction_rho"][()]).squeeze())
        mode_chars = np.asarray(ident["position_delayed_prediction_mode"][()], dtype=np.uint16).reshape(-1)
        mode = "".join(chr(int(c)) for c in mode_chars if c).strip()
        flags = [int(np.asarray(l[k][()]).squeeze()) for k in (
            "stage1_position_replacement_enabled", "stage1_position_delayed_prediction_enabled",
            "stage1_position_pcf_coordination_enabled")]
        release_text = np.asarray(l["position_applied_notch_tau01_release_sha256"][()], np.uint16).reshape(-1)
        log_release_sha = "".join(chr(int(c)) for c in release_text if c)
        center = float(np.asarray(l["stage1_position_applied_notch_center_hz"][()]).squeeze())
        q = float(np.asarray(l["stage1_position_applied_notch_q"][()]).squeeze())

    if n != 20000 or len(idx) != 1999 or not np.array_equal(np.diff(idx), np.full(1998, 10)):
        raise RuntimeError("Stage1 event cadence mismatch")
    if np.max(np.abs(np.diff(time)-DT)) > 1e-12 or abs(time[idx[0]]-EVENT_DT) > 1e-12:
        raise RuntimeError("transition/event timing mismatch")
    if (tau != .1 or rho != .1 or mode != "FIXED_NO_RAMP" or flags != [1,1,1] or
        center != 3.5 or q != 1 or np.any(initial != 0) or
        log_release_sha.lower() != start["release_sha256"].lower()):
        raise RuntimeError("run identity or logged parameter mismatch")
    valid_idx, invalid_idx = idx[valid[idx]], idx[~valid[idx]]
    if not np.allclose(x[valid_idx], head_event[valid_idx], atol=1e-12, rtol=0) or np.max(np.abs(x[invalid_idx])) > 1e-12:
        raise RuntimeError("notch input differs from valid head output / zero pre-ready input")
    for z in (x,yraw,yapplied,limit):
        if not np.all(np.isfinite(z[idx])) or np.any(np.isfinite(z[np.setdiff1d(np.arange(n),idx)])):
            raise RuntimeError("event-only notch telemetry has unexpected finite values")

    state = np.zeros((3,4)); expected_y = np.empty((len(idx),3))
    for j,k in enumerate(idx):
        xx=x[k]
        yy=b[0]*xx+b[1]*state[:,0]+b[2]*state[:,1]-a[1]*state[:,2]-a[2]*state[:,3]
        expected_y[j]=yy
        state=np.column_stack((xx,state[:,0],yy,state[:,2]))
    rec_err=float(np.max(np.abs(expected_y-yraw[idx])))
    clipped=np.minimum(np.maximum(yraw[idx],-limit[idx]),limit[idx])
    clip_err=float(np.max(np.abs(clipped-yapplied[idx])))
    clip_flag_mismatch=int(np.count_nonzero((np.abs(yraw[idx]-yapplied[idx])>1e-12)!=clip_flag[idx]))
    expected_held=np.zeros((n,3)); held=np.zeros(3); event_set=set(map(int,idx))
    for k in range(n):
        if k in event_set: held=yapplied[k].copy()
        expected_held[k]=held
    errors={
        "notch_recurrence_mps2":rec_err,
        "notch_clip_mps2":clip_err,
        "clip_flag_mismatches":clip_flag_mismatch,
        "event_to_held_zoh_mps2":float(np.max(np.abs(expected_held-head_held))),
        "held_to_total_compensation_mps2":float(np.max(np.abs(head_held-comp))),
        "compensation_to_force_N":float(np.max(np.abs(comp*MASS-comp_force))),
        "held_force_N":float(np.max(np.abs(comp*MASS-held_force))),
        "injected_force_N":float(np.max(np.abs(comp*MASS-injected_force))),
        "command_from_nominal_minus_comp_mps2":float(np.max(np.abs(commanded_force/MASS-(nominal-comp)))),
        "PCF_a_req_from_actual_command_mps2":float(np.max(np.abs(pcf_areq-commanded_force/MASS)),),
    }
    if max(float(v) for v in errors.values())>1e-9 or clip_flag_mismatch:
        raise RuntimeError("notch/force/PCF route reconstruction failed")
    return {"raw_path":str(RAW),"raw_sha256":raw_hash,"run_start_sha256":sha(START),"run_status_sha256":sha(STATUS),
        "release_sha256":release_hash,"source_lock_sha256":lock_hash,"source_files_verified":verified,
        "payload_sha256":start["scene_payload_sha256"],"plant_calls_original_run":1,"plant_calls_by_auditor":0,
        "TEST_read_by_auditor":False,"inertia_reconstruction":False,"training_runs_by_auditor":0,
        "status_value":status["status_value"],"transitions":n,"safety_stop_reason":status["safety_stop_reason"],
        "position_tau_s":tau,"position_rho":rho,"position_delayed_mode":mode,"notch_center_hz":center,"notch_Q":q,
        "stage1_event_count":len(idx),"valid_head_event_count":len(valid_idx),"pre_ready_zero_input_events":len(invalid_idx),
        "event_first_index":int(idx[0]),"event_last_index":int(idx[-1]),"event_period_s":EVENT_DT,
        "clip_events_by_axis":np.count_nonzero(clip_flag[idx],axis=0).astype(int).tolist(),
        "max_raw_output_to_limit_ratio":float(np.max(np.abs(yraw[idx])/limit[idx])),"max_abs_errors":errors}


def main() -> None:
    if OUT_JSON.exists() or OUT_MD.exists(): raise RuntimeError("refusing to overwrite score audit")
    frozen=readj(SCORE); one_notch=readj(SINGLE_NOTCH_AUDIT)
    if frozen.get("TEST_read") is not False or frozen.get("test_data_read") is not False:
        raise RuntimeError("frozen score indicates TEST access")
    metric=Path(frozen["metric_source_path"])
    if sha(metric).lower()!=frozen["metric_source_sha256"].lower(): raise RuntimeError("score_raw hash mismatch")
    spec=importlib.util.spec_from_file_location("frozen_score_raw",metric)
    scorer=importlib.util.module_from_spec(spec); sys.modules[spec.name]=scorer; spec.loader.exec_module(scorer)
    row=next(r for r in frozen["scene_results"] if r["scene_id"]==SCENE)
    refs={k:row["methods"][k] for k in ("B","C5","Parent_Cosine_GRU")}
    notch=one_notch["methods_rescored_with_frozen_score_raw"]["Applied_Notch_3p5Hz_Q1"]
    refs["Applied_Notch_3p5Hz_Q1"]=notch
    refs["Applied_Notch_plus_tau01"]= {"raw_path":str(RAW),"raw_sha256":sha(RAW)}
    methods={}
    for name,item in refs.items():
        p=Path(item["raw_path"]); h=sha(p)
        if h.lower()!=item["raw_sha256"].lower(): raise RuntimeError(f"{name} raw hash mismatch")
        s=scorer.score_raw(p,9.8,np.pi/6)
        methods[name]={"raw_path":str(p),"raw_sha256":h,"Q_mm":1000*float(s["Q_m"]),
            "task_SO3_mrad":1000*float(s["task_SO3_rad"]),"inner_SO3_mrad":1000*float(s["inner_SO3_rad"]),"safety":s["safety"]}
    candidate=methods["Applied_Notch_plus_tau01"]
    deltas={k:{metric:candidate[metric]-v[metric] for metric in ("Q_mm","task_SO3_mrad","inner_SO3_mrad")}
        for k,v in methods.items() if k!="Applied_Notch_plus_tau01"}
    route=audit_run()
    result={"schema":"DL1018_NOTCH_TAU01_SINGLE_SCENE_SCORE_ROUTE_AUDIT_V1","status":"PASS_FROZEN_SCORE_AND_ROUTE_RECONSTRUCTION",
        "scene_id":SCENE,"frozen_score_path":str(SCORE),"frozen_score_sha256":sha(SCORE),
        "frozen_metric_path":str(metric),"frozen_metric_sha256":sha(metric),"methods":methods,
        "candidate_minus_comparator":deltas,"route_audit":route,
        "interpretation":["Single VAL scene is a development diagnostic, not independent validation.",
            "The combined notch+tau01 run is a separate Plant trajectory from each comparator; paired scene does not isolate a causal contribution.",
            "The raw output path is numerically verified from notch event recurrence through clipping, position force/command and PCF input."]}
    OUT_JSON.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    write_md(result)
    print(json.dumps({"status":result["status"],"json":str(OUT_JSON),"markdown":str(OUT_MD)},indent=2))


def write_md(r: dict) -> None:
    lines=["# Notch + tau=0.1 single-scene score and route audit","",
        "Frozen FULL72 `score_raw` on one completed VAL scene. The auditor made no Plant calls and did not read TEST or reconstruct inertia. Development diagnostic only; not independent validation.","",
        "| Method | Q (mm) | task SO(3) (mrad) | inner SO(3) (mrad) |","|---|---:|---:|---:|"]
    for k,v in r["methods"].items(): lines.append(f"| {k} | {v['Q_mm']:.3f} | {v['task_SO3_mrad']:.3f} | {v['inner_SO3_mrad']:.3f} |")
    lines.extend(["","Candidate minus comparator (negative means lower error):","","| Comparator | ΔQ (mm) | Δtask (mrad) | Δinner (mrad) |","|---|---:|---:|---:|"])
    for k,v in r["candidate_minus_comparator"].items(): lines.append(f"| {k} | {v['Q_mm']:+.3f} | {v['task_SO3_mrad']:+.3f} | {v['inner_SO3_mrad']:+.3f} |")
    a=r["route_audit"]
    lines.extend(["","## Run binding and route","",f"Raw SHA `{a['raw_sha256']}`; status `{a['status_value']}`; {a['transitions']} transitions; original run Plant calls={a['plant_calls_original_run']}; auditor Plant calls=0.",
        f"Release `{a['release_sha256']}`, source lock `{a['source_lock_sha256']}`; {a['source_files_verified']} locked source files verified. τ={a['position_tau_s']} s, ρ={a['position_rho']}, `{a['position_delayed_mode']}`; notch {a['notch_center_hz']} Hz, Q={a['notch_Q']}.",
        f"Stage1 events={a['stage1_event_count']} (indices {a['event_first_index']}–{a['event_last_index']} every 10 ms); valid head outputs={a['valid_head_event_count']}, pre-ready zero-input events={a['pre_ready_zero_input_events']}. Clip events by axis={a['clip_events_by_axis']}; peak raw/limit={a['max_raw_output_to_limit_ratio']:.4f}.","",
        "| Check | Max abs error |","|---|---:|"])
    for k,v in a["max_abs_errors"].items(): lines.append(f"| {k} | {v:.3e} |")
    lines.extend(["","The exact logged IIR recurrence and clip reproduce the held compensation; force, position command, and PCF `a_req` match the notch-filtered path. See JSON for raw hashes and frozen-score source bindings.","",
        "Reproduce from repository root: `python experiments/dl_attitude_replacement_20261028/gru_cosine_c5_notch35_tau01_v1/audits/score_audit_notch_tau01_single_v1.py`.",""])
    OUT_MD.write_text("\n".join(lines),encoding="utf-8")


if __name__=="__main__": main()
