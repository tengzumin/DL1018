#!/usr/bin/env python3
"""Convert the audited zero-call release into the root-authorized one-call release."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
STUDY=HERE.parent
RELEASE=STUDY/"RELEASE.json"
NO_PLANT_RELEASE=STUDY/"RELEASE_NO_PLANT_v1.json"
NO_PLANT_RESULT=STUDY/"NO_PLANT_PREPARE_RESULT_v1.json"
LOCK=STUDY/"SOURCE_LOCK_v1.json"
OUT=HERE/"SINGLE_PILOT_AUTHORIZATION_v1.json"

def sha(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda:f.read(1<<20),b""):h.update(block)
    return h.hexdigest()

def main()->None:
    if OUT.exists():raise RuntimeError("Refusing to overwrite authorization receipt")
    rel=json.loads(RELEASE.read_text(encoding="utf-8"));lock=json.loads(LOCK.read_text(encoding="utf-8"))
    pre=json.loads(NO_PLANT_RESULT.read_text(encoding="utf-8"))
    if (rel.get("study_id")!="position_teacher_dc_penalty_full24_preflight_v1" or
        rel.get("status")!="PREPARED_NO_PLANT_PENDING_ROOT_AUDIT" or
        rel.get("authorized_Plant_calls")!=0 or rel.get("Plant_calls")!=0 or
        sha(LOCK)!=rel.get("source_lock_sha256") or
        pre.get("status")!="PASS_STOPPED_BEFORE_PLANT" or
        pre.get("source_lock_sha256")!=rel.get("source_lock_sha256") or
        sha(RELEASE)!=pre.get("release_sha256") or sha(NO_PLANT_RELEASE)!=pre.get("release_sha256")):
        raise RuntimeError("Pre-Plant release receipt is stale or unbound")
    for rec in lock["files"]:
        p=STUDY/rec["relative_path"]
        if not p.is_file() or sha(p).lower()!=rec["sha256"].lower():
            raise RuntimeError(f"Locked source changed: {rec['relative_path']}")
    for rec in lock["external_inputs"]:
        p=Path(rec["path"])
        if not p.is_file() or sha(p).lower()!=rec["sha256"].lower():
            raise RuntimeError(f"External source changed: {rec['name']}")
    rel["status"]="RELEASED"
    rel["authorization_phase"]="ROOT_REVIEWED_SINGLE_SCENE_DIAGNOSTIC"
    rel["authorized_Plant_calls"]=1
    rel["Plant_calls"]=1
    rel["release_notes"]=("Root-authorized single fixed VAL diagnostic on DL1018_VAL_T3_C01_W14. "
        "This scene has been used for development diagnosis; not independent validation. "
        "No retuning is authorized from this result. No TEST or inertia reconstruction.")
    RELEASE.write_text(json.dumps(rel,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    receipt={"schema":"POSITION_TEACHER_DC_PENALTY_SINGLE_PILOT_AUTHORIZATION_V1",
        "status":"ROOT_AUTHORIZED_SINGLE_DIAGNOSTIC_CALL","study_id":rel["study_id"],
        "scene_id":rel["fixed_scene_id"],"authorized_Plant_calls":1,"Plant_calls_reserved":1,
        "no_plant_release_sha256":sha(NO_PLANT_RELEASE),"no_plant_result_sha256":sha(NO_PLANT_RESULT),
        "source_lock_sha256":sha(LOCK),"single_call_release_sha256":sha(RELEASE),
        "weights_sha256":rel["position_residual_gru"]["weights_sha256"],
        "TEST_read":False,"inertia_reconstruction_enabled":False,
        "independent_validation":False,"no_retuning_from_this_scene":True}
    OUT.write_text(json.dumps(receipt,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps(receipt,indent=2),flush=True)

if __name__=="__main__":main()
