#!/usr/bin/env python3
"""Read-only causal pairs from the exact locked physical TRAIN_C5_24 IDs."""
from __future__ import annotations
import hashlib, json, re
from pathlib import Path
import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
PHYS = ROOT / "experiments/dl_attitude_replacement_20261027/mlp15_nominal_residual_v1/TRAIN_C5_24_PHYSICAL_RESIDUAL_MANIFEST_v1.json"
PARENT = ROOT / "experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_full72_v1"
PARENT_RELEASE = PARENT / "RELEASE.json"
PARENT_LOCK = PARENT / "SOURCE_LOCK_v1.json"
PARENT_MANIFEST = PARENT / "MANIFEST.json"
PARENT_LEDGER = PARENT / "audits/FULL72_PROGRESS_LEDGER_v02.json"
OTHER_C5 = ROOT / "reports/position_c5_train24_causal_dataset_v1/C5_TRAIN24_POSITION_CAUSAL_MANIFEST_v1.json"
EVENTS, EVENT_DT, LIMIT = 1999, 0.010, 3.0
WIND_FOLDS = ((0, 5), (6, 10), (11, 13), (14, 15))

def sha(p: Path) -> str:
    h = hashlib.sha256()
    with Path(p).open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()

def j(p: Path) -> dict:
    return json.loads(Path(p).read_text(encoding="utf-8-sig"))

def must(ok: bool, msg: str) -> None:
    if not ok: raise RuntimeError(msg)

def bind(p: Path, expected: str, label: str) -> str:
    must(p.is_file(), f"missing {label}: {p}")
    got = sha(p)
    must(got.lower() == str(expected).lower(), f"{label} SHA mismatch: {p}")
    return got

def ds(g: h5py.Group, name: str) -> np.ndarray:
    must(name in g, f"missing /log/{name}")
    return np.asarray(g[name][()])

def meta(sid: str) -> dict:
    m = re.fullmatch(r"DL1018_DEV_(T[123])_C(\d{2})_W(\d{2})", sid)
    must(m is not None, f"unexpected physical TRAIN24 ID: {sid}")
    return {"task": m.group(1), "class_index": int(m.group(2)), "wind_cell": int(m.group(3))}

def make_pairs(raw: Path, sid: str) -> dict[str, np.ndarray]:
    with h5py.File(raw, "r") as f:
        g=f["log"]
        state=ds(g,"state"); time=ds(g,"time").reshape(-1)
        ev=ds(g,"position_event_flag").reshape(-1).astype(bool)
        xlog=ds(g,"stage1_position_feature_14").T
        xin=ds(g,"stage1_position_feature_input").T
        readyall=ds(g,"stage1_position_event_inference_valid").reshape(-1).astype(bool)
        applied=ds(g,"position_compensation_applied_acceleration_mps2").T
        nominal=ds(g,"position_nominal_acceleration_mps2").T
        event_action=ds(g,"stage1_position_event_applied_acceleration_mps2").T
        notch=bool(ds(g,"stage1_position_applied_notch_enabled").reshape(-1)[0]) if "stage1_position_applied_notch_enabled" in g else False
        residual=bool(ds(g,"stage1_position_residual_gru_enabled").reshape(-1)[0]) if "stage1_position_residual_gru_enabled" in g else False
    idx=np.flatnonzero(ev)
    must(state.shape==(12,20001) and len(time)==20001 and len(ev)==20000, f"bad raw shapes: {sid}")
    must(np.array_equal(idx,np.arange(10,20000,10)), f"bad 100Hz event schedule: {sid}")
    must(xlog.shape==xin.shape==(20000,14) and np.array_equal(xlog[idx],xin[idx]), f"actual X14/input mismatch: {sid}")
    x=xin[idx].astype(np.float32); must(np.isfinite(x).all(), f"non-finite actual X14: {sid}")
    ready=readyall[idx]; expected_ready=np.arange(EVENTS)>=31
    must(np.array_equal(ready,expected_ready), f"readiness mismatch: {sid}")
    spans=idx[:,None]+np.arange(10)[None,:]
    v=state[3:6]
    actual=((v[:,idx+10]-v[:,idx])/EVENT_DT).T
    nominal_mean=nominal[spans].mean(axis=1)
    applied_mean=applied[spans].mean(axis=1)
    action_raw=applied[idx]
    action=action_raw.astype(np.float32)
    y=actual-(nominal_mean-applied_mean); yc=np.clip(y,-LIMIT,LIMIT)
    delta=yc-action; delta[~ready]=np.nan
    must(np.isfinite(actual).all() and np.isfinite(nominal_mean).all() and np.isfinite(applied_mean).all() and np.isfinite(action).all(), f"non-finite labels/action: {sid}")
    must(np.isfinite(event_action[idx[ready]]).all() and not np.isfinite(event_action[idx[~ready]]).any() and np.max(np.abs(event_action[idx[ready]]-action_raw[ready]))<1e-9, f"C5 event/applied action mismatch: {sid}")
    must(not notch and not residual, f"raw is not the no-notch/no-new-residual parent arm: {sid}")
    end=time[idx+10]
    must(np.allclose(time[idx][[0,-1]],[.01,19.99],atol=1e-12,rtol=0) and np.allclose(end-time[idx],EVENT_DT,atol=1e-12,rtol=0), f"bad future interval alignment: {sid}")
    return {"x14_logged":x,"x14_model_input":x.copy(),"target_interval_raw_mps2":y.astype(np.float32),
            "target_interval_clip_mps2":yc.astype(np.float32),"delta_target_post_clip_mps2":delta.astype(np.float32),
            "applied_acceleration_event_mps2":action,"applied_acceleration_interval_mean_mps2":applied_mean.astype(np.float32),
            "applied_acceleration_interval_span_mps2":(applied[spans].max(axis=1)-applied[spans].min(axis=1)).astype(np.float32),
            "actual_acceleration_interval_mean_mps2":actual.astype(np.float32),
            "nominal_acceleration_interval_mean_mps2":nominal_mean.astype(np.float32),
            "event_time_s":time[idx].astype(np.float64),"interval_end_time_s":end.astype(np.float64),
            "ready_mask":ready,"event_index_zero_based":idx.astype(np.int32)}

def main() -> None:
    data_out=OUT/"COSINE_GRU_C5_TRAIN24_POSITION_CAUSAL_PAIRS_v1.npz"
    man_out=OUT/"DATASET_MANIFEST_v1.json"; lock_out=OUT/"SOURCE_LOCK_v1.json"
    must(not data_out.exists() and not man_out.exists() and not lock_out.exists(), "refusing to overwrite derived data")
    phys=j(PHYS); phys_sha=sha(PHYS)
    must(phys["status"]=="PASS_TRAIN_ONLY_SOURCE_AND_CAUSALITY_AUDIT" and phys["train_split"]=="TRAIN_C5_24" and phys["train_scene_count"]==24 and phys["TEST_read"] is False and phys["Plant_called"] is False and phys["C5_VAL48_loaded_for_training"] is False, "physical TRAIN24 scope lock failed")
    phys_lock=ROOT/phys["source_lock_path"]; phys_lock_sha=bind(phys_lock,phys["source_lock_sha256"],"physical TRAIN24 source lock")
    must(sha(ROOT/phys["dataset_path"]).lower()==phys["dataset_sha256"].lower(), "physical TRAIN24 list dataset hash mismatch")
    rel=j(PARENT_RELEASE); pm=j(PARENT_MANIFEST); led=j(PARENT_LEDGER)
    rel_sha=sha(PARENT_RELEASE); lock_sha=bind(PARENT_LOCK,rel["source_lock_sha256"],"parent source lock")
    pm_sha=bind(PARENT_MANIFEST,rel["manifest_sha256"],"parent full72 manifest"); led_sha=sha(PARENT_LEDGER)
    must(rel["TEST_read"] is False and rel["true_inertia_reconstructed"] is False and rel["training_status"]=="INHERITED_COMPLETED_60000_STEPS" and rel["payload_scene_count"]==72 and rel["dev_scene_count"]==24 and rel["val_scene_count"]==48, "parent GRU scope mismatch")
    must(led["TEST_read"] is False and led["status"]=="PASS_ALL_66_NEW_CANDIDATE_RAW_AUDITS", "parent raw ledger scope/status mismatch")
    parent={r["scene_id"]:r for r in pm["records"]}; ledger={r["scene_id"]:r for r in led["records"]}
    ids=[r["scene_id"] for r in phys["records"]]
    parent_dev={r["scene_id"] for r in pm["records"] if r["source_split"]=="DEV"}
    must(len(ids)==len(set(ids))==24 and set(ids)==parent_dev, "physical TRAIN24 IDs are not exactly parent DEV24")
    keys=("x14_logged","x14_model_input","target_interval_raw_mps2","target_interval_clip_mps2","delta_target_post_clip_mps2","applied_acceleration_event_mps2","applied_acceleration_interval_mean_mps2","applied_acceleration_interval_span_mps2","actual_acceleration_interval_mean_mps2","nominal_acceleration_interval_mean_mps2","event_time_s","interval_end_time_s","ready_mask","event_index_zero_based")
    arrays={k:[] for k in keys}; rows=[]
    for pr in phys["records"]:
        sid=pr["scene_id"]; must(pr["split"]=="TRAIN_C5_24",f"bad physical split: {sid}")
        c5raw=ROOT/pr["raw_path"]; c5st=ROOT/pr["status_path"]; c5start=ROOT/pr["run_start_path"]
        c5sha=bind(c5raw,pr["raw_sha256"],f"physical C5 raw {sid}"); c5stsha=bind(c5st,pr["status_sha256"],f"physical C5 status {sid}"); c5startsha=bind(c5start,pr["run_start_sha256"],f"physical C5 run-start {sid}")
        c5status=j(c5st)
        # Physical run_start is a hash-locked MATLAB .mat file, not JSON.
        must(c5status["raw_sha256"].lower()==c5sha.lower() and c5status.get("TEST_accessed",False) is False, f"physical C5 identity/status mismatch: {sid}")
        r=parent[sid]; l=ledger[sid]; raw=Path(l["raw_path"]); status=Path(r["candidate_status_path"]); start=raw.parent/"run_start.json"; audit=Path(l["audit_path"])
        rawsha=bind(raw,l["raw_sha256"],f"parent cosine-GRU raw {sid}"); stsha=sha(status); startsha=sha(start); audsha=sha(audit)
        st=j(status); run=j(start); au=j(audit)
        must(l["state"]=="PASS_RAW_AUDITED" and l["audit_status"]=="PASS_INDEPENDENT_GRU_STREAM_TRACKING_HEAD_RAW_REPLAY" and Path(r["candidate_raw_path"])==raw and st["state"]=="COMPLETED" and st["status_value"]=="STABLE" and st["Plant_calls"]==1 and st["TEST_read"] is False and st["safety_stop_reason"] in ("",None,"NONE") and st["raw_sha256"].lower()==rawsha.lower(), f"parent raw/status/audit mismatch: {sid}")
        must(run["release_sha256"].lower()==rel_sha.lower() and st["release_sha256"].lower()==rel_sha.lower() and run["source_lock_sha256"].lower()==lock_sha.lower() and st["source_lock_sha256"].lower()==lock_sha.lower() and au["candidate_raw_sha256"].lower()==rawsha.lower() and au["release_sha256"].lower()==rel_sha.lower() and au["TEST_read"]==0 and au["training_calls_by_audit"]==0, f"parent run identity/audit binding mismatch: {sid}")
        must(r["external_identity_sha256"]==pr["scene_identity_sha256"] and r["c5_raw_sha256"].lower()==c5sha.lower() and run["c5_raw_sha256"].lower()==c5sha.lower() and run["payload_sha256"].lower()==r["payload_sha256"].lower() and run["attitude_arm"]=="GRU_STREAM" and run["rbf_attitude_output_enabled"] is False and run["rbf_attitude_update_enabled"] is False and run["TEST_read"] is False, f"same physical scene/payload/controller identity mismatch: {sid}")
        pair=make_pairs(raw,sid)
        for k in keys: arrays[k].append(pair[k])
        rows.append({"scene_id":sid,**meta(sid),"declared_split":pr["split"],"scene_identity_sha256":pr["scene_identity_sha256"],"physical_c5_raw_path":str(c5raw),"physical_c5_raw_sha256":c5sha,"physical_c5_status_sha256":c5stsha,"physical_c5_run_start_sha256":c5startsha,"parent_cosine_gru_raw_path":str(raw),"parent_cosine_gru_raw_sha256":rawsha,"parent_status_path":str(status),"parent_status_sha256":stsha,"parent_run_start_sha256":startsha,"parent_raw_audit_path":str(audit),"parent_raw_audit_sha256":audsha,"payload_path":r["payload_path"],"payload_sha256":r["payload_sha256"],"ready_events":int(pair["ready_mask"].sum())})
    stacked={k:np.stack(v) for k,v in arrays.items()}
    must(stacked["x14_model_input"].shape==(24,EVENTS,14) and np.all(stacked["ready_mask"].sum(axis=1)==1968), "packed causal data shape/readiness mismatch")
    wind=np.asarray([meta(s)["wind_cell"] for s in ids],dtype=np.int16)
    fold_rows=[]
    for lo,hi in WIND_FOLDS:
        hold=np.flatnonzero((wind>=lo)&(wind<=hi)); train=np.flatnonzero((wind<lo)|(wind>hi))
        fold_rows.append({"fold_id":f"holdout_W{lo:02d}_{hi:02d}","wind_code_range":[lo,hi],"holdout_scene_ids":[ids[i] for i in hold],"train_scene_ids":[ids[i] for i in train],"holdout_scene_count":len(hold),"train_scene_count":len(train),"holdout_task_counts":{t:sum(meta(ids[i])["task"]==t for i in hold) for t in ("T1","T2","T3")}})
    other=j(OTHER_C5); other_status_identity={j(ROOT/s["status_path"]).get("external_identity_sha256") for s in other["scenes"]}
    phys_identity={r["scene_identity_sha256"] for r in phys["records"]}
    alias={"other_C5_pairs_manifest_path":str(OTHER_C5.relative_to(ROOT)).replace("\\","/"),"other_C5_pairs_manifest_sha256":sha(OTHER_C5),"other_scene_count":len(other["scenes"]),"scene_id_overlap":len(set(ids)&{s["scene_id"] for s in other["scenes"]}),"external_identity_overlap":len(phys_identity&other_status_identity),"used_for_new_features_or_labels":False}
    must(alias["scene_id_overlap"]==0 and alias["external_identity_overlap"]==0,"different C5 TRAIN24 cohort unexpectedly aliases physical TRAIN24")
    data_out=OUT/"COSINE_GRU_C5_TRAIN24_POSITION_CAUSAL_PAIRS_v1.npz"
    fold_ids=np.asarray([next(f["fold_id"] for f in fold_rows if f["wind_code_range"][0]<=meta(s)["wind_cell"]<=f["wind_code_range"][1]) for s in ids],dtype="U24")
    np.savez_compressed(data_out,scene_ids=np.asarray(ids,dtype="U32"),wind_cells=wind,fold_id=fold_ids,**stacked)
    data_sha=sha(data_out)
    manifest={"schema":"COSINE_GRU_C5_TRAIN24_POSITION_CAUSAL_DATASET_V1","status":"PASS_READ_ONLY_PARENT_RAW_CAUSAL_DATASET_BUILT","dataset_path":str(data_out.relative_to(ROOT)).replace("\\","/"),"dataset_sha256":data_sha,"builder_path":str(Path(__file__).relative_to(ROOT)).replace("\\","/"),"builder_sha256":sha(Path(__file__)),"scene_count":24,"events_per_scene":EVENTS,"ready_events_per_scene":1968,"source_scene_ids":ids,"scene_id_note":"These IDs are declared TRAIN_C5_24 by the physical manifest, although canonical IDs begin DL1018_DEV_. This exact 24-ID set equals parent DEV24 by external identity.","other_C5_pairs_non_alias_check":alias,"parent_model_exposure":{"training_status":rel["training_status"],"payload_scene_count":rel["payload_scene_count"],"dev_scene_count":rel["dev_scene_count"],"val_scene_count":rel["val_scene_count"],"physical_train24_is_parent_dev24":True,"limit":"Parent cosine-GRU has seen the same DEV24 scenes and VAL48; these trajectories are in-sample with respect to the frozen parent. This derived head dataset is for development, not independent validation."},"features":"Actual logged stage1_position_feature_14 / stage1_position_feature_input at event t; 14D and equal on all event rows.","target":"(v[e+10]-v[e])/0.010 - mean_10ms(position_nominal_acceleration-position_compensation_applied_acceleration), m/s^2; feature event is t and label ends t+10ms.","current_applied":"Logged parent cosine-GRU/C5 position_compensation_applied_acceleration at event t.","ready_mask":"Logged C5 stage1_position_event_inference_valid; 1968/1999 events, first ready event ordinal 31 at t=0.32s.","scene_folds":fold_rows,"wind_code_distribution":{str(int(w)):int(np.sum(wind==w)) for w in sorted(set(wind.tolist()))},"scope":{"only_physical_train24_ids":True,"VAL_raw_read":False,"TEST_read":False,"Plant_called_by_builder":False,"inertia_reconstruction":False},"scope_limits":["Parent model was trained/evaluated on DEV24+VAL48; all derived scenes are in its DEV24 and are not an independent test.","The newer TRAIN-prefixed C5 causal cohort is a different external-identity set and was not used for features or targets.","The four whole-scene wind folds have nonuniform counts 6/8/4/6 based on observed IDs; no Cartesian wind grid is assumed."]}
    lock={"schema":"COSINE_GRU_C5_TRAIN24_POSITION_CAUSAL_SOURCE_LOCK_V1","scope":"TRAIN_C5_24 physical IDs only; no VAL/TEST raw, Plant, training, or inertia reconstruction.","physical_manifest_path":str(PHYS.relative_to(ROOT)).replace("\\","/"),"physical_manifest_sha256":phys_sha,"physical_source_lock_path":str(phys_lock.relative_to(ROOT)).replace("\\","/"),"physical_source_lock_sha256":phys_lock_sha,"parent_release_sha256":rel_sha,"parent_source_lock_sha256":lock_sha,"parent_manifest_sha256":pm_sha,"parent_ledger_sha256":led_sha,"data_path":str(data_out.relative_to(ROOT)).replace("\\","/"),"data_sha256":data_sha,"builder_sha256":sha(Path(__file__)),"scene_rows":rows}
    (OUT/"SOURCE_LOCK_v1.json").write_text(json.dumps(lock,indent=2,ensure_ascii=False,allow_nan=False)+"\n",encoding="utf-8")
    manifest["source_lock_path"]=str((OUT/"SOURCE_LOCK_v1.json").relative_to(ROOT)).replace("\\","/");manifest["source_lock_sha256"]=sha(OUT/"SOURCE_LOCK_v1.json")
    (OUT/"TRAIN_C5_24_PHYSICAL_RESIDUAL_MANIFEST_source_v1.json").write_bytes(PHYS.read_bytes())
    (OUT/"DATASET_MANIFEST_v1.json").write_text(json.dumps(manifest,indent=2,ensure_ascii=False,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({"status":manifest["status"],"scene_count":24,"data_sha256":data_sha,"folds":[{k:f[k] for k in ("fold_id","train_scene_count","holdout_scene_count")} for f in fold_rows],"dataset_path":str(data_out)},indent=2))

if __name__=="__main__": main()
