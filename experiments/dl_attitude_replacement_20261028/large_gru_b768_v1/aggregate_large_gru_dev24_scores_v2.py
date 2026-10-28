#!/usr/bin/env python3
"""Canonical DEV24 score views; repairs JSON int/float hash spelling only."""
from __future__ import annotations
import argparse, csv, hashlib, importlib.util, json
from decimal import Decimal
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
PHASE_DIR=HERE/"paired_results/DEV24"
SOURCE_SCORE_DIR=PHASE_DIR/"scores"
CANON_DIR=PHASE_DIR/"canonical_scores_v2"
SOURCE_SNAP_DIR=PHASE_DIR/"source_scores_v2"
TRAIN24=ROOT/"experiments/dl_attitude_replacement_20261028/causal_n4_gate_train24_batch_v2/TRAIN24_SCORE_SUMMARY_v2.json"
PILOT_DIR=HERE/"paired_results/PILOT/scores"
SCORE_SCRIPT=ROOT/"experiments/dl_attitude_replacement_20261028/large_gru_dual_loop_dev_v1/score_large_gru_single_scene_v1.py"
METHODS=("B","C5","legacy_parent_cosine","frozen_gateN4_72","new_GRU_B768_N4")
PREFIX="GRU13_B768_COSINE_S2026102001_N4_"

def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda:f.read(1<<20),b""): h.update(block)
    return h.hexdigest()

def read(path): return json.loads(Path(path).read_text(encoding="utf-8-sig"))

def write_json(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(obj,indent=2,ensure_ascii=False,allow_nan=False)+"\n",encoding="utf-8")
    tmp.replace(path)

def canonical_number(x):
    d=Decimal(str(x))
    if not d.is_finite(): raise ValueError("non-finite numeric config value")
    if d==0: return "0"
    return format(d.normalize(),"f")

def canonicalize(value):
    # Tag numbers so numeric 1 and string "1" remain distinct; 1 and 1.0 unify.
    if isinstance(value,bool) or value is None or isinstance(value,str): return value
    if isinstance(value,(int,float,Decimal)): return {"$number":canonical_number(value)}
    if isinstance(value,list): return [canonicalize(x) for x in value]
    if isinstance(value,dict): return {k:canonicalize(v) for k,v in sorted(value.items())}
    raise TypeError(f"unsupported config type: {type(value).__name__}")

def canonical_sha(value):
    payload=json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()

def legacy_hash(value):
    # Reproduce immutable V1 hash from the raw parsed object before normalization.
    payload=json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()

def self_check():
    # JSON's 1 vs 1.0 spelling must disappear, but real precision and bools must survive.
    assert canonicalize({"x":1})==canonicalize({"x":1.0})
    assert canonical_sha(canonicalize({"x":1}))==canonical_sha(canonicalize({"x":1.0}))
    assert canonical_sha(canonicalize({"x":1.000000000001}))!=canonical_sha(canonicalize({"x":1}))
    assert canonicalize({"x":True})!=canonicalize({"x":1})

def verify_v1_card(score):
    cfg=score["numeric_config"]
    numeric_sha=legacy_hash(cfg)
    if numeric_sha!=score["numeric_config_sha256"]:
        raise ValueError(f"V1 numeric-config hash mismatch for {score['scene_id']}")
    identity={"model_sha256":score["candidate_model_sha256"],
              "runner_identity_sha256":score["runner_identity_sha256"],
              "numeric_config_sha256":numeric_sha}
    old_key=PREFIX+legacy_hash(identity)[:16]
    if old_key!=score["scorecard_key"]:
        raise ValueError(f"V1 scorecard key mismatch for {score['scene_id']}")

def load_or_score(scene,candidate_dir,expected_ids,hf_ids):
    source=SOURCE_SCORE_DIR/f"{scene}.json"
    if source.is_file():
        return read(source),source,sha(source)
    # The locked scorer remains untouched. Invoke only its scoring function; do not run Plant.
    spec=importlib.util.spec_from_file_location("locked_large_gru_scorer",SCORE_SCRIPT)
    scorer=importlib.util.module_from_spec(spec); spec.loader.exec_module(scorer)
    result=scorer.score_scene(scene,"DEV24",24,hf_ids,candidate_dir)
    SOURCE_SNAP_DIR.mkdir(parents=True,exist_ok=True)
    source=SOURCE_SNAP_DIR/f"{scene}.json"
    if source.exists(): raise FileExistsError(f"source score snapshot already exists: {source}")
    write_json(source,result)
    return result,source,sha(source)

def make_view(score,source_path,source_sha,expected_ids):
    verify_v1_card(score)
    scene=score["scene_id"]
    if scene not in expected_ids: raise ValueError(f"non-TRAIN24 scene rejected: {scene}")
    config=canonicalize(score["numeric_config"])
    config_sha=canonical_sha(config)
    model_sha=score["candidate_model_sha256"]
    runner_sha=score["runner_identity_sha256"]
    key=PREFIX+canonical_sha({"model_sha256":model_sha,"runner_identity_sha256":runner_sha,
                              "numeric_config_sha256":config_sha})[:16]
    view={"schema":"DL1018_LARGE_GRU_DEV24_CANONICAL_SCENE_SCORE_V2",
          "phase":"DEV24","scene_id":scene,"task":score["task"],"wind_code":score["wind_code"],
          "HF_W09_W14":bool(score["HF_W09_W14"]),"same_scene_pair":True,
          "source_score_path":str(source_path.resolve()),"source_score_sha256":source_sha,
          "source_scorecard_key_v1":score["scorecard_key"],"source_numeric_config_sha256_v1":score["numeric_config_sha256"],
          "scorecard_key":key,"candidate_model_sha256":model_sha,
          "candidate_model_path":score["candidate_model_identity"]["new_candidate"]["model_path"],
          "runner_identity_sha256":runner_sha,"numeric_config_sha256_canonical":config_sha,
          "numeric_config_canonical":config,
          "single_call_release_sha256":score.get("single_call_release_sha256",score.get("release_sha256")),
          "single_call_source_lock_sha256":score.get("single_call_source_lock_sha256",score.get("source_lock_sha256")),
          "candidate_raw_path":score["raw_path"],"candidate_raw_sha256":score["raw_sha256"],
          "action_replay":score["action_replay"],"scores":score["scores"],
          "TEST_read":False,"VAL_data_read":False,"inertia_reconstruction_enabled":False}
    pilot=PILOT_DIR/f"{scene}.json"
    view["same_raw_as_pilot"]=(read(pilot).get("raw_sha256")==score["raw_sha256"]) if pilot.is_file() else False
    return view

def strict_variant(views):
    if not views: return None
    fields=("scorecard_key","candidate_model_sha256","runner_identity_sha256","numeric_config_sha256_canonical")
    first=views[0]
    for view in views[1:]:
        for field in fields:
            if view[field]!=first[field]:
                raise ValueError(f"mixed DEV24 variant: {field} differs for {view['scene_id']}")
        if view["numeric_config_canonical"]!=first["numeric_config_canonical"]:
            raise ValueError(f"true numeric configuration difference for {view['scene_id']}")
    return {k:first[k] for k in fields}

def relative_pct(value,baseline):
    return None if baseline==0 else 100.0*(value/baseline-1.0)

def aggregate(expected_ids):
    views=[]
    for p in sorted(CANON_DIR.glob("*.json")):
        view=read(p)
        if view["scene_id"]!=p.stem: raise ValueError(f"canonical view filename mismatch: {p}")
        views.append(view)
    scene_ids=[v["scene_id"] for v in views]
    if len(scene_ids)!=len(set(scene_ids)): raise ValueError("duplicate scene in canonical results")
    if not set(scene_ids).issubset(set(expected_ids)): raise ValueError("canonical result outside DEV24")
    variant=strict_variant(views)
    rows=[]
    for v in sorted(views,key=lambda x:expected_ids.index(x["scene_id"])):
        s=v["scores"]; b=s["B"]; c5=s["C5"]
        for method in METHODS:
            m=s[method]
            row={"phase":"DEV24","scene_id":v["scene_id"],"task":v["task"],"wind_code":v["wind_code"],
                 "HF_W09_W14":v["HF_W09_W14"],"method":method,
                 "Q_m":m["Q_m"],"task_SO3_rad":m["task_SO3_rad"],"inner_SO3_rad":m["inner_SO3_rad"],
                 "Q_vs_B_pct":relative_pct(m["Q_m"],b["Q_m"]),"Q_vs_C5_pct":relative_pct(m["Q_m"],c5["Q_m"]),
                 "task_vs_B_pct":relative_pct(m["task_SO3_rad"],b["task_SO3_rad"]),
                 "task_vs_C5_pct":relative_pct(m["task_SO3_rad"],c5["task_SO3_rad"]),
                 "inner_vs_B_pct":relative_pct(m["inner_SO3_rad"],b["inner_SO3_rad"]),
                 "inner_vs_C5_pct":relative_pct(m["inner_SO3_rad"],c5["inner_SO3_rad"]),
                 "safety_fault_count":m["safety_fault_count"],"raw_path":m["raw_path"],"raw_sha256":m["raw_sha256"],
                 "model_path":m["model_path"],"model_sha256":m["model_sha256"],
                 "scorecard_key":v["scorecard_key"],"runner_identity_sha256":v["runner_identity_sha256"],
                 "numeric_config_sha256":v["numeric_config_sha256_canonical"],
                 "source_score_sha256":v["source_score_sha256"],"same_scene_pair":True,
                 "completed_scenes":len(views),"expected_scenes":24}
            rows.append(row)
    csv_path=PHASE_DIR/"paired_metrics_v2.csv"
    fields=list(rows[0]) if rows else ["phase","scene_id","task","wind_code","HF_W09_W14","method"]
    tmp=csv_path.with_suffix(".csv.tmp")
    with tmp.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
    tmp.replace(csv_path)
    hf_expected=sum(bool(r["HF_W09_W14"]) for r in read(TRAIN24)["scenes"])
    progress={"schema":"DL1018_LARGE_GRU_DEV24_PAIRED_PROGRESS_V2",
        "status":"COMPLETE" if len(views)==24 else "PARTIAL",
        "completed_scene_count":len(views),"expected_scene_count":24,
        "completed_scene_ids":scene_ids,"expected_scene_ids":expected_ids,
        "hf_completed_scene_count":sum(bool(v["HF_W09_W14"]) for v in views),
        "hf_expected_scene_count":hf_expected,"scorecard_key":variant["scorecard_key"] if variant else None,
        "runner_identity_sha256":variant["runner_identity_sha256"] if variant else None,
        "numeric_config_sha256_canonical":variant["numeric_config_sha256_canonical"] if variant else None,
        "scene_metrics_only":True,"macro_means_emitted":False,
        "pilot_duplicate_policy":"DEV24 C09 source is counted once; same raw as PILOT is tagged in canonical view",
        "paired_metrics_csv":str(csv_path)}
    write_json(PHASE_DIR/"paired_progress_v2.json",progress)
    return progress

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--scene",required=True)
    ap.add_argument("--candidate-dir",type=Path,required=True)
    args=ap.parse_args()
    self_check()
    plan=read(TRAIN24)
    expected_ids=[row["scene_id"] for row in plan["scenes"]]
    if args.scene not in expected_ids: ap.error("DEV24-only: scene is not in frozen TRAIN24 queue")
    hf_ids={row["scene_id"] for row in plan["scenes"] if row["HF_W09_W14"]}
    score,source_path,source_sha=load_or_score(args.scene,args.candidate_dir.resolve(),expected_ids,hf_ids)
    view=make_view(score,source_path,source_sha,expected_ids)
    out=CANON_DIR/f"{args.scene}.json"
    if out.exists():
        current=read(out)
        if current.get("source_score_sha256")!=source_sha or current.get("scorecard_key")!=view["scorecard_key"]:
            raise FileExistsError(f"refusing to replace canonical scene result: {out}")
    else: write_json(out,view)
    progress=aggregate(expected_ids)
    print(json.dumps({"status":"PASS_CANONICAL_SCENE_SCORE","scene_id":args.scene,
        "scorecard_key":view["scorecard_key"],"same_raw_as_pilot":view["same_raw_as_pilot"],
        "completed_scene_count":progress["completed_scene_count"],"expected_scene_count":24,
        "hf_completed_scene_count":progress["hf_completed_scene_count"],"hf_expected_scene_count":progress["hf_expected_scene_count"],
        "paired_metrics_csv":progress["paired_metrics_csv"]},indent=2))

if __name__=="__main__": main()
