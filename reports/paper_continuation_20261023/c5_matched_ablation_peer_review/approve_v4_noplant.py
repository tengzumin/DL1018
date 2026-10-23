"""Verify v4 is only isolated bookkeeping; no MATLAB/Plant is launched."""
from pathlib import Path
import hashlib
import json
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
manifest=ROOT/'reports/paper_continuation_20261023/c5_matched_ablation_execution/v4/C5_V4_CODE_READY_MANIFEST_v1.json'
out=HERE/'PARENT_CODE_NOPLANT_RELEASE_v5.json'
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
assert sha(manifest)=='df855e98ac0292cf949b8aa956366d33726c44a1c34bb4a7e8c7b186c2ae5a70'
assert not out.exists()
count=0
for mode in ('C5_FREEZE_TRAINED_W0','C5_NO_DELAYED_PREDICTION'):
    old=ROOT/'experiments/position_c5_matched_ablations_v3_20261023'/mode
    new=ROOT/'experiments/position_c5_matched_ablations_v4_20261023'/mode
    for name in ('run_c5_matched_ablation_v1.m','prepare_c5_matched_ablation_v1.m',
                 'run_dl1018_closed_loop.m','run_episode_dl1018.m','delayed_prediction_step_candidate.m',
                 'C5_ABLATION_CROSSLANG_FIXTURE_v2.json','check_c5_matched_ablation_synthetic_v1.m'):
        assert (old/name).read_bytes()==(new/name).read_bytes(),name
    assert sha(new/'run_c5_matched_ablation_v1.m')=='eb9e6a94beaaf7588c6b4e9ddfe109dddbc3c4ac8c4e88397d34ce3922bf2223'
    for name in ('RUN_C5_ABLATION_NOPLANT_EXACT_v1.ps1','RUN_C5_ABLATION_PARENT_EXACT_v1.ps1'):
        assert (new/name).read_bytes()==(old/name).read_bytes().replace(b'c5_matched_ablation_execution/v3',b'c5_matched_ablation_execution/v4')
    a=load(old/'C5_ABLATION_INPUT_LOCK_v1.json');b=load(new/'C5_ABLATION_INPUT_LOCK_v1.json')
    for key in ('scenes','scene_ids','candidate_identity','shared_input_files','coordinate_mask','scope'):
        assert a[key]==b[key],key
    binding=load(new/'C5_ABLATION_SOURCE_BINDING_v1.json')
    assert len(binding['file_refs'])==69
    for ref in binding['file_refs']:
        assert sha(ref['path'])==ref['sha256'],ref['path']
        count+=1
result={'status':'APPROVED_V4_SEQUENTIAL_TWO_NOPLANT_CHECKS_ONLY','created_utc':datetime.now(timezone.utc).isoformat(),
        'manifest_sha256':sha(manifest),'binding_refs_verified':count,'scientific_sources_identical_to_v3':True,
        'launcher_change_exactly_report_directory':True,'reuse_two_v3_pilots_required':True,'new_Plant_authorized':False,
        'TEST_authorized':False,'required_tail_pilot_fields':['pilot_raw_path','pilot_raw_sha256','pilot_run_status_path','pilot_run_status_sha256','pilot_release_sha256']}
out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':result['status'],'refs':count,'receipt_sha256':sha(out)}))
