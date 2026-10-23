"""Independent preparation audit, then release exactly one pilot per ablation."""
from pathlib import Path
from datetime import datetime, timezone
import importlib.util
import json
import numpy as np

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
REPORT=ROOT/'reports/paper_continuation_20261023'
STAGE=ROOT/'experiments/position_c5_matched_ablations_20261023'
basepath=REPORT/'c5_dev72_parent_review/audit_c5_dev72_raw_parent_v4.py'
spec=importlib.util.spec_from_file_location('frozen_parent_audit',basepath)
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
assert base.sha(basepath)=='d82e089c7d41f39c620daea63d95315632e6fb2f80addf4dc12e6a4603b8e57e'
decoder=base.module_at(base.DECODER_PATH,'frozen_decoder')
assert base.sha(base.DECODER_PATH)==base.DECODER_SHA
oldpath=ROOT/'experiments/position_axis_coordinate_c5_20261023/C5_AXIS_COORDINATE_PREPARED_CFG_OPTS_v1.mat'
sections=('cfg','opts','W0','modelIdentity','sceneIdentity','sourceIdentity')
old={s:base.matlab_section_safe(oldpath,s,decoder) for s in sections}
out=HERE/'PARENT_NOPLANT_REVIEW_v2.json'
assert not out.exists()
rows=[]
for variant in ('C5_FREEZE_TRAINED_W0','C5_NO_DELAYED_PREDICTION'):
    folder=STAGE/variant
    lp=folder/'C5_ABLATION_INPUT_LOCK_v1.json';cp=folder/'C5_ABLATION_RUN_CONTRACT_v1.json'
    bp=folder/'C5_ABLATION_SOURCE_BINDING_v1.json';pp=folder/'C5_ABLATION_PREPARE_RESULT_v1.json'
    sp=folder/'C5_ABLATION_PREPARED_CFG_OPTS_v1.mat';fp=folder/'C5_ABLATION_RUNNER_PREFLIGHT_v1.json'
    yp=folder/'C5_ABLATION_CROSSLANG_RESULT_v1.json'
    ep=REPORT/f'c5_matched_ablation_execution/{variant}_NOPLANT_OS_EXIT_v1.json'
    lock,contract,binding,prep,preflight,synthetic,osrec=map(base.load,(lp,cp,bp,pp,fp,yp,ep))
    for ref in binding['file_refs']: assert base.sha(ref['path'])==ref['sha256']
    assert osrec['matlab_os_exit_code']==0 and not osrec['plant_authorized']
    assert osrec['variant_id']==variant and osrec['command_sha256']==base.sha(osrec['command_file'])
    assert prep['plant_calls']==preflight['plant_calls']==0 and not prep['TEST_accessed'] and not preflight['TEST_accessed']
    assert prep['status']=='PREPARED_C5_MATCHED_ABLATION_NO_PLANT_WAIT_PARENT_RELEASE_V1'
    assert preflight['status']=='PREFLIGHT_COMPLETE_NO_PLANT_WAIT_PARENT_RELEASE_V1'
    assert preflight['returned_before_shared_lock_or_episode'] and preflight['which_checks']==32
    expected_refs={'input_lock_sha256':lp,'contract_sha256':cp,'source_binding_sha256':bp,
                   'prepare_result_sha256':pp,'snapshot_sha256':sp,'synthetic_result_sha256':yp,
                   'runner_sha256':folder/'run_c5_matched_ablation_v1.m'}
    for key,path in expected_refs.items(): assert preflight[key]==base.sha(path),key
    assert synthetic['status']=='PASS_SYNTHETIC_CROSSLANGUAGE_ONLY'
    assert synthetic['max_abs_error']<=2e-12 and not synthetic['plant_or_real_data_used']
    assert synthetic['variant_id']==variant and synthetic['matlab_helper_sha256']==base.sha(folder/'delayed_prediction_step_candidate.m')
    pack={s:base.matlab_section_safe(sp,s,decoder) for s in sections}
    leaves={s:base.equal_tree(old[s],pack[s],decoder) for s in ('cfg','opts','modelIdentity','sceneIdentity')}
    assert leaves['cfg']==120 and leaves['opts']==43 and leaves['modelIdentity']==6
    assert np.array_equal(pack['W0'],old['W0']) and np.max(abs(np.asarray(pack['W0'],dtype=float)))<=60
    si=pack['sourceIdentity']
    paths=[base.matlab_text(x) for x in base.matlab_flat(si['active_paths'])]
    hashes=[base.matlab_text(x) for x in base.matlab_flat(si['active_sha256'])]
    assert paths==[r['path'] for r in lock['active_source_inventory']]
    assert hashes==[r['sha256'] for r in lock['active_source_inventory']]
    assert base.matlab_text(si['ablation_mode'])==variant
    assert bool(base.matlab_scalar(si['actual_weight_update_enabled']))==(variant=='C5_NO_DELAYED_PREDICTION')
    assert not (folder/'C5_ABLATION_FIRST_PARENT_RELEASE_v1.json').exists()
    assert not (folder/'runs_c5_matched_ablation_v1').exists()
    rows.append({'variant_id':variant,'leaf_counts':leaves,'binding_refs_verified':len(binding['file_refs']),
                 'synthetic_max_error':synthetic['max_abs_error'],'natural_MATLAB_OS_exit':0,
                 'noPlant_OS_record_sha256':base.sha(ep),
                 **{key:base.sha(path) for key,path in expected_refs.items()}})
result={'schema':'C5_MATCHED_ABLATION_PARENT_NOPLANT_REVIEW_V1','status':'PASS_BOTH_EXACT_CFG_OPTS_W0_MODEL_SCENES_SOURCES',
        'created_utc':datetime.now(timezone.utc).isoformat(),'rows':rows,'new_Plant':0,'TEST_accessed':False,
        'parent_check_preoutput_repair':'First read-only check stopped on abs(list) before output or releases; explicit ndarray conversion repaired. No MATLAB/Plant invoked.',
        'previous_release_builder_failure':'v1 noPlant review passed and was retained; required-fields assertion stopped before any pilot release. v2 includes parent-release-contract SHA, candidate and mask required by the actual frozen contract.',
        'decision':'Authorize one original locked first scene per configuration; no tail11 or DEV72 release.'}
out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
for row in rows:
    folder=STAGE/row['variant_id'];contract=base.load(folder/'C5_ABLATION_RUN_CONTRACT_v1.json')
    release={
        'schema':'C5_MATCHED_ABLATION_PARENT_RELEASE_V1','state':'APPROVED_C5_ABLATION_FIRST_V1',
        'created_utc':datetime.now(timezone.utc).isoformat(),'phase':'FIRST','plant_authorized':True,
        'variant_id':row['variant_id'],'ablation_mode':row['variant_id'],
        'actual_weight_update_enabled':row['variant_id']=='C5_NO_DELAYED_PREDICTION',
        'actual_prediction_gradient_enabled':False,'legacy_stage1_update_enabled':True,
        'candidate':contract['candidate'],'coordinate_mask':contract['coordinate_mask'],
        'parent_release_contract_sha256':base.sha(folder/'C5_ABLATION_PARENT_RELEASE_CONTRACT_v1.json'),
        'input_lock_sha256':row['input_lock_sha256'],'run_contract_sha256':row['contract_sha256'],
        'source_binding_sha256':row['source_binding_sha256'],'prepare_result_sha256':row['prepare_result_sha256'],
        'snapshot_sha256':row['snapshot_sha256'],'synthetic_result_sha256':row['synthetic_result_sha256'],
        'synthetic_fixture_sha256':base.sha(folder/'C5_ABLATION_CROSSLANG_FIXTURE_v2.json'),
        'runner_preflight_sha256':base.sha(folder/'C5_ABLATION_RUNNER_PREFLIGHT_v1.json'),
        'runner_sha256':row['runner_sha256'],'launcher_sha256':base.sha(folder/'RUN_C5_ABLATION_PARENT_EXACT_v1.ps1'),
        'first_scene_id':contract['first_scene_id'],'scene_ids':[contract['first_scene_id']],'max_new_Plant':1,
        'training_steps':0,'optimizer_steps':0,'new_B_sorties':0,'TEST_accessed':False,
        'automatic_retry':False,'parameter_or_seed_search':False,
        'parent_review_path':str(out),'parent_review_sha256':base.sha(out),
        **{key:contract['limits'][key] for key in ('deadline_utc','minimum_free_bytes','per_scene_output_reserve_bytes','max_output_bytes')},
    }
    required=base.load(folder/'C5_ABLATION_PARENT_RELEASE_CONTRACT_v1.json')['required_fields']
    assert set(required)<=release.keys()
    with (folder/'C5_ABLATION_FIRST_PARENT_RELEASE_v1.json').open('x',encoding='utf-8') as stream:
        json.dump(release,stream,ensure_ascii=False,indent=2);stream.write('\n')
print(json.dumps({'status':result['status'],'parent_review_sha256':base.sha(out),'pilot_releases':2,'max_new_Plant':2}))
