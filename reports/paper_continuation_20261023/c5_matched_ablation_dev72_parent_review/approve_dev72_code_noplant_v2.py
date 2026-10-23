"""Parent source/input approval for isolated DEV72 v2 no-Plant checks only."""
from pathlib import Path
import hashlib
import json
import re
import argparse
import h5py

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
EXP = ROOT / "experiments/position_c5_matched_ablations_dev72_v3_20261023"
OLD = ROOT / "experiments/position_c5_matched_ablations_v4_20261023"
OUT = HERE / "PARENT_CODE_NOPLANT_RELEASE_v2.json"
assert not OUT.exists()

def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))

verified = {}
def verify(item):
    if isinstance(item,dict):
        if "path" in item and "sha256" in item:
            path=Path(item["path"])
            key=str(path.resolve())
            digest=verified.setdefault(key,sha(path))
            assert digest.lower()==item["sha256"].lower(),key
        else:
            for value in item.values(): verify(value)
    elif isinstance(item,list):
        for value in item: verify(value)

manifest_path=EXP/"C5_ABLATION_DEV72_CODE_INPUT_MANIFEST_v3.json"
manifest_sha=sha(manifest_path)
parser=argparse.ArgumentParser()
parser.add_argument("--manifest-sha256",required=True)
args=parser.parse_args()
assert manifest_sha==args.manifest_sha256
manifest=load(manifest_path)
assert manifest["plant_authorized"] is False
c3_path=ROOT/"experiments/position_delayed_prediction_c3_dev72_20261023/C3_DEV72_INPUT_LOCK_v2.json"
assert sha(c3_path)=="a95eda8e6ab8b45408d24b560366636bab62f72ea619bf46fa602142b6708730"
c3=load(c3_path)
closed_path=ROOT/"experiments/position_axis_coordinate_c5_dev72_20261023/C5_DEV72_INPUT_LOCK_v3.json"
assert sha(closed_path)=="82024c01276cc4bfbd9b7772cf5332dee3fdfcbed422969589b68f1c90ed2d75"
closed=load(closed_path)
closed_by_id={row["scene_id"]:row for row in closed["scenes"]}
original_fields={"B_raw_path","B_raw_sha256","alias_normalized_in_memory","canonical_scene_id","payload_review_sha256","raw_scene_id","scene_id"}
snapshot=ROOT/"experiments/position_delayed_prediction_c3_dev72_20261023/C3_DEV72_PREPARED_CONFIG_OPTS_v2.mat"
with h5py.File(snapshot,"r") as mat:
    assert set(mat["sceneIdentity"].keys())==original_fields
    assert mat["sceneIdentity/scene_id"].size==72
rows=[]
for entry in manifest["variants"]:
    variant=entry["variant_id"]
    folder=EXP/variant
    lock_path=Path(entry["lock_path"])
    contract_path=Path(entry["contract_path"])
    binding_path=Path(entry["source_binding_path"])
    for key,path in (("lock",lock_path),("contract",contract_path),("source_binding",binding_path)):
        assert sha(path)==entry[key+"_sha256"]
    lock,contract,binding=load(lock_path),load(contract_path),load(binding_path)
    old=load(OLD/variant/"C5_ABLATION_INPUT_LOCK_v1.json")
    assert lock["first_scene_id"]==contract["first_scene_id"]==contract["scene_ids_remaining_60"][0]
    assert contract["scene_ids_all_72"]==c3["scene_ids_all_72"]
    assert contract["scene_ids_reuse_12"]==old["scene_ids_reuse_12"]
    expected60=[s for s in c3["scene_ids_all_72"] if s not in set(old["scene_ids_reuse_12"])]
    assert len(expected60)==60 and contract["scene_ids_remaining_60"]==expected60
    assert [x["scene_id"] for x in lock["scenes"]]==c3["scene_ids_all_72"]
    for scene in lock["scenes"]:
        assert scene["C3_reference"]==closed_by_id[scene["scene_id"]]["C3_reference"]
    prepare_source=Path(lock["source_files"]["prepare_entry"]["path"]).read_text(encoding="utf-8")
    runner_source=Path(lock["source_files"]["runner_entry"]["path"]).read_text(encoding="utf-8")
    assert "sceneIdentity(ix).C3_raw_" not in prepare_source
    assert "identity.C3_raw_" not in runner_source
    assert "isequaln(c3ref,closedC5Lock.scenes" in prepare_source
    assert "isequaln(c3ref,closedC5Lock.scenes" in runner_source
    assert contract["model"]==old["scope"]["model"]
    assert contract["fixed_parameters"]==old["scope"]["fixed_parameters"]
    assert contract["coordinate_mask"]==[1,1,0]
    assert contract["actual_weight_update_enabled"] is (variant=="C5_NO_DELAYED_PREDICTION")
    assert contract["actual_prediction_gradient_enabled"] is False
    assert contract["stage1_update_enabled"] is True and contract["position_delayed_prediction_enabled"] is True
    assert [(i["role"],i["sha256"]) for i in lock["active_source_inventory"]]==[(i["role"],i["sha256"]) for i in old["active_source_inventory"]]
    assert len(lock["active_source_inventory"])==32
    for name in ("source_files","upstream_refs","shared_input_files","active_source_inventory"):
        verify(lock[name])
    verify(binding["file_refs"])
    for name in ("run_dl1018_closed_loop.m","run_episode_dl1018.m","delayed_prediction_step_candidate.m"):
        assert (folder/name).read_bytes()==(OLD/variant/name).read_bytes()
    reuse=load(folder/"C5_ABLATION_DEV72_REUSE12_BINDING_v3.json")
    assert len(reuse["records"])==12
    assert [r["scene_id"] for r in reuse["records"]]==contract["scene_ids_reuse_12"]
    for record in reuse["records"]:
        for key,value in record.items():
            if key.endswith("_path") and key[:-5]+"_sha256" in record:
                verify({"path":value,"sha256":record[key[:-5]+"_sha256"]})
    required=load(folder/"C5_ABLATION_DEV72_PARENT_RELEASE_CONTRACT_v3.json")["required_fields"]
    template=load(folder/"C5_ABLATION_DEV72_PARENT_RELEASE_TEMPLATE_v3.json")
    runner=(folder/"run_c5_matched_ablation_dev72_v3.m").read_text(encoding="utf-8")
    assert set(re.findall(r"\brelease\.([A-Za-z_]\w*)",runner))<=set(required)
    assert set(required)<=set(template) and len(required)==44
    assert template["plant_authorized"] is False and template["max_new_Plant"]==0
    assert "APPROVED_C5_ABLATION_DEV72_REMAINING60_V1" in runner
    noplant=(folder/"RUN_C5_ABLATION_DEV72_NOPLANT_EXACT_v3.ps1").read_text(encoding="utf-8")
    assert "[IO.Path]::GetDirectoryName($PSCommandPath)" in noplant
    assert "CreateDirectory($reportDir)" in noplant
    assert "check_c5_matched_ablation_dev72_synthetic_v2" in noplant
    for name in ("C5_ABLATION_CROSSLANG_RESULT_DEV72_v3.json", "C5_ABLATION_DEV72_PREPARE_RESULT_v3.json",
                 "C5_ABLATION_DEV72_PREPARED_CFG_OPTS_v3.mat", "C5_ABLATION_DEV72_RUNNER_PREFLIGHT_v3.json"):
        assert not (folder/name).exists(),name
    rows.append({"variant":variant,"lock_sha256":sha(lock_path),"contract_sha256":sha(contract_path),
                 "binding_sha256":sha(binding_path),"runner_sha256":sha(folder/"run_c5_matched_ablation_dev72_v3.m"),
                 "unchanged_algorithm_files":3,"active_sources":32,"all72":72,"reuse12":12,"new60":60,
                 "required_release_fields":len(required),
                 "release_state_exact_legacy_spelling":"APPROVED_C5_ABLATION_DEV72_REMAINING60_V1"})
builder=(EXP/"build_c5_matched_ablation_dev72_inputs_v3.py").read_text(encoding="utf-8")
assert "REFRESH_UNRELEASED" not in builder and "import os" not in builder
result={"status":"APPROVED_TWO_SEQUENTIAL_NOPLANT_CHECKS_ONLY", "manifest_sha256":manifest_sha,
        "refs_verified":len(verified),"rows":rows,"Plant_authorized":False,"TEST_accessed":False,
        "notes":["Parent read complete v4-to-DEV72 runner/prepare changes and v1-to-v2 repairs.",
                 "v1 unreleased drafts preserved; mixed PS logical guards and first-scene mismatch repaired before any MATLAB.",
                 "Global resource observation:15.659GB creation-time files+9.6GB reserve<80GB;free141.496GB.",
                 "Retry1 after v2 OS1/0Plant: actual seven-field MAT schema and closed C5 C3_reference all72 independently checked; original v2 preserved."]}
with OUT.open("x",encoding="utf-8") as stream:
    json.dump(result,stream,ensure_ascii=False,indent=2)
    stream.write("\n")
print(json.dumps({"status":result["status"],"refs_verified":len(verified),"output_sha256":sha(OUT)}))
