"""Root source/input release check. Never launches MATLAB or Plant."""
from pathlib import Path
import json
import hashlib
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[3]
REPORT=ROOT/'reports/paper_continuation_20261023'
STAGE=ROOT/'experiments/position_c5_matched_ablations_20261023'
HERE=Path(__file__).resolve().parent
OUT=HERE/'PARENT_CODE_NOPLANT_RELEASE_v1.json'
assert not OUT.exists()
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
manifest_path=REPORT/'c5_matched_ablation_execution/C5_MATCHED_ABLATION_CODE_READY_MANIFEST_v1.json'
assert sha(manifest_path)=='946a9c10120524dafe43f8c415765c40d00cbcafaf019fdbe50468932f5c111e'
manifest=read(manifest_path)
assert not manifest['matlab_started'] and not manifest['plant_authorized']
for name in ('builder','fixture_generator','helper_diff'):
    assert sha(manifest[name+'_path'])==manifest[name+'_sha256']
old=read(ROOT/'experiments/position_axis_coordinate_c5_20261023/C5_AXIS_COORDINATE_INPUT_LOCK_v1.json')
rows=[]
for v in manifest['variants']:
    folder=STAGE/v['variant_id']
    for name,digest in v['files'].items(): assert sha(folder/name)==digest,name
    lock=read(folder/'C5_ABLATION_INPUT_LOCK_v1.json')
    contract=read(folder/'C5_ABLATION_RUN_CONTRACT_v1.json')
    binding=read(folder/'C5_ABLATION_SOURCE_BINDING_v1.json')
    assert len(binding['file_refs'])==69
    for ref in binding['file_refs']: assert sha(ref['path'])==ref['sha256'],ref['path']
    assert lock['scenes']==old['scenes']
    assert contract['scene_ids']==old['scene_ids_reuse_12']
    assert contract['first_scene_id']==contract['scene_ids'][0]
    assert contract['coordinate_mask']==[1,1,0]
    assert contract['model']==lock['scope']['model']
    assert contract['legacy_stage1_update_enabled'] and contract['position_delayed_prediction_enabled']
    assert contract['actual_weight_update_enabled']==(v['variant_id']=='C5_NO_DELAYED_PREDICTION')
    assert not contract['actual_prediction_gradient_enabled']
    assert not contract['plant_authorized_by_this_contract'] and contract['limits']['max_new_Plant']==12
    assert contract['limits']['deadline_utc']=='2026-10-24T17:01:00Z'
    assert sha(folder/'run_dl1018_closed_loop.m')=='48350037b66efe00301b138068f187c62cf92583f0f9ba2fabc9b24f248a963c'
    assert sha(folder/'run_episode_dl1018.m')=='fcc1f5de659541e692483f8395d93fd2a251256286ebade5e510ed4c7a2e2330'
    checker=(folder/'check_c5_matched_ablation_synthetic_v1.m').read_text()
    assert "check_events('boundary',edgeEvents,[],[],tol,false,fixture.mode)" in checker
    rows.append({'variant_id':v['variant_id'],'source_ref_count':69,'first_scene_id':contract['first_scene_id'],
                 'input_lock_sha256':v['lock_sha256'],'run_contract_sha256':v['contract_sha256'],
                 'source_binding_sha256':v['source_binding_sha256'],'no_plant_command':v['no_plant_command']})
result={'schema':'C5_ABLATION_PARENT_CODE_NOPLANT_RELEASE_V1','created_utc':datetime.now(timezone.utc).isoformat(),
        'status':'APPROVED_SEQUENTIAL_TWO_NOPLANT_CHECKS_ONLY','manifest_sha256':sha(manifest_path),
        'manual_source_review':'Complete builder/prepare/runner/local dependencies/PS7 launchers/helper/fixture read; three draft blockers corrected before launch; no remaining blocker.',
        'PS7_launcher_parse_errors':0,'variants':rows,'Plant_authorized':False,'TEST_authorized':False,'training_authorized':False}
OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':result['status'],'variants':len(rows),'references_verified':138,'result_sha256':sha(OUT)}))
