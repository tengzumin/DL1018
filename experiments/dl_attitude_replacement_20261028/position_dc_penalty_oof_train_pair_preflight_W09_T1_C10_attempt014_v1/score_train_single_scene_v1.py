#!/usr/bin/env python3
"""Score the one TRAIN attempt with the frozen Full72 score_raw definition."""
import hashlib
import importlib.util
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
AUDIT=HERE/"audits"
OUT=AUDIT/"TRAIN_SINGLE_SCENE_PAIRED_SCORE_v1.json"
SCORE_SOURCE=ROOT/"experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_full72_v1/audits/score_full72_candidate_v1.py"
CONSTANTS=ROOT/"experiments/dl_attitude_replacement_20261026/mlp15_composite_dev_v3/RELEASE.json"

def sha(p):
    h=hashlib.sha256()
    with Path(p).open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""):h.update(b)
    return h.hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding="utf-8-sig"))
def require(ok,msg):
    if not ok:raise RuntimeError(msg)
def main():
    if OUT.exists():raise RuntimeError(f"Refusing to overwrite {OUT}")
    binding=read(HERE/"TRAIN_SCENE_BINDING_v1.json")
    release=read(HERE/"RELEASE.json")
    attempt=HERE/"runs"/binding["selected_scene_id"]/"attempt_01"
    status_path=attempt/"run_status.json";raw=attempt/"raw_run.mat"
    require(raw.is_file() and status_path.is_file(),"Single TRAIN attempt raw/status is missing")
    status=read(status_path)
    require(status.get("state")=="COMPLETED" and status.get("status_value")=="STABLE" and
            status.get("transitions")==20000 and status.get("state_samples")==20001 and
            status.get("Plant_calls")==1 and status.get("VAL_data_read") is False and
            status.get("TEST_read") is False,"Candidate attempt is incomplete, unsafe, or out of scope")
    require(status.get("scene_id")==binding["selected_scene_id"] and
            status.get("fold_id")==binding["fold_id"] and
            status.get("weights_sha256")==release["weights_sha256"] and
            status.get("parent_cosine_gru_raw_sha256")==binding["parent_raw_sha256"] and
            status.get("c5_raw_sha256")==binding["c5_raw_sha256"] and
            status.get("B_raw_sha256")==binding["b72_scoring_raw_sha256"],
            "Candidate attempt run status differs from the frozen same-scene source binding")
    require(sha(raw)==status["raw_sha256"],"Candidate raw/status hash mismatch")
    specs={
        "B":(Path(binding["b72_scoring_raw_path"]),Path(binding["b72_scoring_status_path"]),
             binding["b72_scoring_raw_sha256"],binding["b72_scoring_status_sha256"]),
        "C5":(Path(binding["c5_raw_path"]),Path(binding["c5_status_path"]),
              binding["c5_raw_sha256"],binding["c5_status_sha256"]),
        "parent_GRU":(Path(binding["parent_raw_path"]),Path(binding["parent_status_path"]),
                      binding["parent_raw_sha256"],binding["parent_status_sha256"]),
        "candidate":(raw,status_path,status["raw_sha256"],sha(status_path)),
    }
    for name,(raw_path,st_path,raw_sha,status_sha) in specs.items():
        require(raw_path.is_file() and st_path.is_file(),f"Missing same-scene {name} raw/status")
        require(sha(raw_path)==raw_sha and sha(st_path)==status_sha,f"Same-scene {name} hash mismatch")
        st=read(st_path)
        require(st.get("scene_id")==binding["selected_scene_id"],f"{name} raw/status is not the selected TRAIN scene")
        for key in ("TEST_read","TEST_accessed","test_data_read"):
            require(st.get(key) is not True,f"{name} status reports TEST access")
    score_module_spec=importlib.util.spec_from_file_location("frozen_full72_score",SCORE_SOURCE)
    module=importlib.util.module_from_spec(score_module_spec);score_module_spec.loader.exec_module(module)
    constants=read(CONSTANTS);gravity=float(constants["gravity_mps2"]);max_tilt=float(constants["max_tilt_rad"])
    methods={}
    for name,(raw_path,st_path,raw_sha,status_sha) in specs.items():
        score=module.score_raw(raw_path,gravity,max_tilt)
        score.update({"raw_path":str(raw_path.resolve()),"raw_sha256":raw_sha,
                      "status_path":str(st_path.resolve()),"status_sha256":status_sha})
        methods[name]=score
    metrics=module.MAIN
    relative={}
    for other in ("B","C5","parent_GRU"):
        relative[other]={}
        for metric in metrics:
            b=float(methods[other][metric]);x=float(methods["candidate"][metric])
            relative[other][metric]={"candidate_minus_comparator":x-b,
                "candidate_relative_change_percent":100.0*(x-b)/b if b else None,
                "candidate_win":x<b}
    out={"schema":"POSITION_DC_OOF_TRAIN_SINGLE_SCENE_FROZEN_PAIRED_SCORE_V1",
        "status":"PASS_SCORED_SAME_SCENE_TRAIN_DIAGNOSTIC","scene_id":binding["selected_scene_id"],
        "source_split":"TRAIN_C5_24","fold_id":binding["fold_id"],
        "interpretation":"One previously unseen-to-this-fold TRAIN scene; diagnostic pair only, not independent validation.",
        "methods":methods,"candidate_vs_same_scene_comparator":relative,
        "safety":{"candidate_state":status["state"],"candidate_status_value":status["status_value"],
            "transitions":status["transitions"],"Plant_calls":status["Plant_calls"],
            "first_plant_step_marker_created":status.get("first_plant_step_marker_created"),
            "motor_saturation_samples":methods["candidate"]["safety"]["motor_saturation_samples"],
            "generalized_clip_samples":methods["candidate"]["safety"]["generalized_clip_samples"],
            "tilt_limited_samples":methods["candidate"]["safety"]["tilt_limited_samples"],
            "VAL_data_read":False,"TEST_read":False,"inertia_reconstruction_enabled":False},
        "source_binding":{"release_sha256":sha(HERE/"RELEASE.json"),
            "source_lock_sha256":sha(HERE/"SOURCE_LOCK_SINGLE_CALL_v1.json"),
            "train_scene_binding_sha256":sha(HERE/"TRAIN_SCENE_BINDING_v1.json"),
            "weights_sha256":release["weights_sha256"],"prior_no_plant_preflight_sha256":release["prior_no_plant_preflight_sha256"],
            "scorer_path":str(SCORE_SOURCE.resolve()),"scorer_sha256":sha(SCORE_SOURCE),
            "score_constants_path":str(CONSTANTS.resolve()),"score_constants_sha256":sha(CONSTANTS),
            "gravity_mps2":gravity,"max_tilt_rad":max_tilt},
        "TEST_read":False,"VAL_raw_read":False}
    OUT.write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"output":str(OUT.resolve()),"scene_id":out["scene_id"],
        "candidate":{k:methods["candidate"][k] for k in metrics},"vs_B":relative["B"]},indent=2))

if __name__=="__main__":main()
