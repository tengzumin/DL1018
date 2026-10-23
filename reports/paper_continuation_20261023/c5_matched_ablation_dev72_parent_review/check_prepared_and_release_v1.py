"""Review actual v3 snapshots and create exact, separately launched remaining60 releases."""
from pathlib import Path
import hashlib
import importlib.util
import json
from datetime import datetime,timezone,timedelta
import shutil

import h5py
import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
EXP=ROOT/"experiments/position_c5_matched_ablations_dev72_v3_20261023"
EXEC=ROOT/"reports/paper_continuation_20261023/c5_matched_ablation_execution/dev72_v3"
OUT=HERE/"PARENT_DEV72_NOPLANT_SNAPSHOT_REVIEW_v1.json"
assert not OUT.exists()

def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))

def module(path,name,expected):
    assert sha(path)==expected
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

base=module(ROOT/"reports/paper_continuation_20261023/c5_dev72_parent_review/audit_c5_dev72_raw_parent_v4.py",
            "box_abl_parent_base","d82e089c7d41f39c620daea63d95315632e6fb2f80addf4dc12e6a4603b8e57e")
decoder=module(ROOT/"reports/paper14_v2/phase1/audit_w15_position_replay.py",
               "box_abl_parent_decoder","372d92cb17da99884e742d3fa0c877200c3bb2bc6fac7f10e7a1a046b97a76af")
def snapshot(path):
    with h5py.File(path,"r") as mat:
        return {key:base.h5_tree_cell_safe(mat[key]) for key in
                ("cfg","opts","W0","modelIdentity","sceneIdentity","sourceIdentity")}

code_path=HERE/"PARENT_CODE_NOPLANT_RELEASE_v3.json"
assert sha(code_path)=="f130a0b8f58b6d9bf58c461c8e08d5bcd731120c03dad5275f6fa29d98528fe0"
code=load(code_path)
assert code["status"]=="APPROVED_TWO_SEQUENTIAL_NOPLANT_CHECKS_ONLY" and not code["Plant_authorized"]
manifest_path=EXP/"C5_ABLATION_DEV72_CODE_INPUT_MANIFEST_v3.json"
assert sha(manifest_path)=="51d1b428c5b7a29a47cb7c8a564a82b8a9529c61dd62e6b79a0c448859a1023f"
manifest=load(manifest_path)
assert shutil.disk_usage(ROOT).free-120*80000000>=30000000000
assert datetime.now(timezone.utc)+timedelta(seconds=2*(60*180+600))<datetime(2026,10,24,17,1,tzinfo=timezone.utc)
rows,releases=[],[]
for entry in manifest["variants"]:
    variant=entry["variant_id"]
    folder=EXP/variant
    paths={name:folder/f"C5_ABLATION_DEV72_{file}_v3.{ext}" for name,file,ext in (
        ("lock","INPUT_LOCK","json"),("contract","RUN_CONTRACT","json"),("binding","SOURCE_BINDING","json"),
        ("prepare","PREPARE_RESULT","json"),("snapshot","PREPARED_CFG_OPTS","mat"),
        ("preflight","RUNNER_PREFLIGHT","json"),("release_contract","PARENT_RELEASE_CONTRACT","json"))}
    paths["synthetic"]=folder/"C5_ABLATION_CROSSLANG_RESULT_DEV72_v3.json"
    paths["fixture"]=folder/"C5_ABLATION_CROSSLANG_FIXTURE_v3.json"
    paths["OS"]=EXEC/f"{variant}_DEV72_NOPLANT_OS_EXIT_v3.json"
    assert all(path.is_file() for path in paths.values()),variant
    digest={key:sha(path) for key,path in paths.items()}
    assert digest["lock"]==entry["lock_sha256"] and digest["contract"]==entry["contract_sha256"]
    assert digest["binding"]==entry["source_binding_sha256"]
    lock,contract,binding,prep,preflight,syn,os_exit=[load(paths[name]) for name in
        ("lock","contract","binding","prepare","preflight","synthetic","OS")]
    assert os_exit["matlab_os_exit_code"]==0 and os_exit["plant_authorized"] is False
    assert os_exit["variant_id"]==variant and os_exit["input_lock_sha256"]==digest["lock"]
    assert os_exit["runner_sha256"]==binding["runner_sha256"]
    assert os_exit["command_sha256"]==lock["source_files"]["no_plant_launcher"]["sha256"]
    assert prep["status"]=="PREPARED_C5_MATCHED_ABLATION_DEV72_NO_PLANT_WAIT_PARENT_RELEASE_V2"
    assert preflight["status"]=="PREFLIGHT_COMPLETE_C5_MATCHED_ABLATION_DEV72_NO_PLANT_WAIT_PARENT_RELEASE_V2"
    assert preflight["returned_before_shared_lock_or_episode"] is True
    assert preflight["plant_calls"]==prep["plant_calls"]==syn["plant_calls"]==0
    assert syn["status"]=="PASS_SYNTHETIC_CROSSLANGUAGE_ONLY"
    for obj in (prep,preflight):
        assert obj["input_lock_sha256"]==digest["lock"] and obj["contract_sha256"]==digest["contract"]
        assert obj["snapshot_sha256"]==digest["snapshot"] and obj["TEST_accessed"] is False
        assert obj["actual_weight_update_enabled"] is contract["actual_weight_update_enabled"]
        assert obj["actual_prediction_gradient_enabled"] is False and obj["legacy_stage1_update_enabled"] is True
    assert preflight["source_binding_sha256"]==digest["binding"]
    assert preflight["prepare_result_sha256"]==digest["prepare"]
    assert preflight["active_source_count"]==preflight["which_checks"]==32
    assert preflight["scene_count"]==72 and preflight["remaining_scene_count"]==60 and preflight["reuse_scene_count"]==12
    pack=snapshot(paths["snapshot"])
    old=snapshot(ROOT/"experiments/position_c5_matched_ablations_v4_20261023"/variant/"C5_ABLATION_PREPARED_CFG_OPTS_v1.mat")
    c3=snapshot(Path(lock["upstream_refs"]["c3_dev72_prepared_snapshot"]["path"]))
    assert base.equal_tree(pack["cfg"],old["cfg"],decoder)==120
    assert base.equal_tree(pack["opts"],old["opts"],decoder,ignore_marker=True)==43
    assert base.equal_tree(pack["modelIdentity"],old["modelIdentity"],decoder)==6
    assert np.array_equal(np.asarray(pack["W0"]),np.asarray(old["W0"]))
    assert base.equal_tree(pack["sceneIdentity"],c3["sceneIdentity"],decoder)>0
    assert set(pack["sceneIdentity"])=={"B_raw_path","B_raw_sha256","alias_normalized_in_memory","canonical_scene_id","payload_review_sha256","raw_scene_id","scene_id"}
    w0_sha=hashlib.sha256(np.asarray(pack["W0"],dtype="<f8").tobytes(order="F")).hexdigest()
    assert w0_sha==contract["model"]["W0_sha256"]
    active=lock["active_source_inventory"]
    actual_paths=[base.matlab_text(x) for x in base.matlab_flat(pack["sourceIdentity"]["active_paths"])]
    actual_sha=[base.matlab_text(x).lower() for x in base.matlab_flat(pack["sourceIdentity"]["active_sha256"])]
    assert [Path(x).resolve() for x in actual_paths]==[Path(i["path"]).resolve() for i in active]
    assert actual_sha==[i["sha256"].lower() for i in active]
    reuse_path=Path(lock["source_files"]["reuse12_binding"]["path"])
    reuse=load(reuse_path)
    assert sha(reuse_path)==lock["source_files"]["reuse12_binding"]["sha256"]
    assert preflight["reuse12_binding_sha256"]==sha(reuse_path)
    release={"schema":"C5_MATCHED_ABLATION_DEV72_PARENT_RELEASE_V2","state":"APPROVED_C5_ABLATION_DEV72_REMAINING60_V1",
        "plant_authorized":True,"phase":"REMAINING60","variant_id":variant,"ablation_mode":variant,
        "actual_weight_update_enabled":contract["actual_weight_update_enabled"],"actual_prediction_gradient_enabled":False,
        "legacy_stage1_update_enabled":True,"input_lock_sha256":digest["lock"],"run_contract_sha256":digest["contract"],
        "source_binding_sha256":digest["binding"],"prepare_result_sha256":digest["prepare"],"snapshot_sha256":digest["snapshot"],
        "parent_release_contract_sha256":digest["release_contract"],"synthetic_fixture_sha256":digest["fixture"],
        "synthetic_result_sha256":digest["synthetic"],"runner_preflight_sha256":digest["preflight"],
        "runner_sha256":binding["runner_sha256"],"launcher_sha256":lock["source_files"]["parent_launcher"]["sha256"],
        "first_scene_id":contract["first_scene_id"],"max_new_Plant":60,"training_steps":0,"optimizer_steps":0,
        "new_B_sorties":0,"TEST_accessed":False,"automatic_retry":False,"parameter_or_seed_search":False,
        "candidate":contract["candidate"],"coordinate_mask":[1,1,0],
        "reuse12_binding_sha256":sha(reuse_path),"reuse12_parent_screen_audit_sha256":reuse["screen12_parent_audit_sha256"],
        "reuse12_first_audit_sha256":reuse["first_parent_audit_sha256"],"screen12_event_audit_sha256":reuse["screen12_parent_audit_event_audit_sha256"],
        "parent_code_review_sha256":sha(code_path),"manifest_sha256":sha(manifest_path)}
    for key in ("scene_ids_all_72","scene_ids_remaining_60","scene_ids_reuse_12"):
        release[key]=contract[key]
    for key in ("deadline_utc","minimum_free_bytes","per_scene_output_reserve_bytes","max_output_bytes"):
        release[key]=contract["limits"][key]
    for key,ref in (("lock","c3_dev72_input_lock"),("contract","c3_dev72_run_contract"),("snapshot","c3_dev72_prepared_snapshot")):
        release[f"c3_dev72_{key}_sha256"]=lock["upstream_refs"][ref]["sha256"]
    required=load(paths["release_contract"])["required_fields"]
    assert len(required)==44 and set(required)<=set(release)
    release_path=folder/"C5_ABLATION_DEV72_REMAINING60_PARENT_RELEASE_v3.json"
    assert not release_path.exists()
    releases.append((release_path,release))
    rows.append({"variant":variant,"digests":digest,"cfg_leaves":120,"opts_leaves":43,"model_leaves":6,
                 "W0_sha256":w0_sha,"sceneIdentity_fields":7,"scene_count":72,"active_sources":32,"required_release_fields":44})
review={"status":"PASS_BOTH_ACTUAL_NOPLANT_SNAPSHOTS_APPROVED_REMAINING60_RELEASES","rows":rows,
        "Plant_called_by_checker":False,"TEST_accessed":False,"checker_sha256":sha(Path(__file__)),"created_utc":datetime.now(timezone.utc).isoformat()}
with OUT.open("x",encoding="utf-8") as stream:
    json.dump(review,stream,ensure_ascii=False,indent=2);stream.write("\n")
written=[]
for path,release in releases:
    release["parent_noplant_snapshot_review_sha256"]=sha(OUT)
    with path.open("x",encoding="utf-8") as stream:
        json.dump(release,stream,ensure_ascii=False,indent=2);stream.write("\n")
    written.append({"path":str(path),"sha256":sha(path)})
print(json.dumps({"status":review["status"],"review_sha256":sha(OUT),"releases":written}))
