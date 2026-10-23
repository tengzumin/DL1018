"""Audit v4 preparation and bind 11 new scenes to the already audited v3 pilot."""
from pathlib import Path
from datetime import datetime, timezone
import importlib.util
import json
import numpy as np

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
REPORT=ROOT/'reports/paper_continuation_20261023'
STAGE=ROOT/'experiments/position_c5_matched_ablations_v4_20261023'
OUT=HERE/'PARENT_V4_NOPLANT_AND_TAIL_RELEASE_REVIEW_v1.json'
PILOTS={'C5_FREEZE_TRAINED_W0':'727031d9107da1636b7d27fb7a0e04f6a6761a4507fc2a0d5a299df2b08dfa97',
        'C5_NO_DELAYED_PREDICTION':'d0d0f3f2fa38f5499aca53c642a1ec65d20758bbc18e67cba2d55fede6e6289d'}
basepath=REPORT/'c5_dev72_parent_review/audit_c5_dev72_raw_parent_v4.py'
spec=importlib.util.spec_from_file_location('frozen_parent',basepath)
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
assert base.sha(basepath)=='d82e089c7d41f39c620daea63d95315632e6fb2f80addf4dc12e6a4603b8e57e'
assert base.sha(base.DECODER_PATH)==base.DECODER_SHA
decoder=base.module_at(base.DECODER_PATH,'frozen_decoder')
oldpath=ROOT/'experiments/position_axis_coordinate_c5_20261023/C5_AXIS_COORDINATE_PREPARED_CFG_OPTS_v1.mat'
sections=('cfg','opts','W0','modelIdentity','sceneIdentity','sourceIdentity')
old={s:base.matlab_section_safe(oldpath,s,decoder) for s in sections}
assert not OUT.exists()
rows=[]; releases=[]
for variant,pilot_sha in PILOTS.items():
    folder=STAGE/variant
    files={key:folder/name for key,name in {
        'input_lock_sha256':'C5_ABLATION_INPUT_LOCK_v1.json','run_contract_sha256':'C5_ABLATION_RUN_CONTRACT_v1.json',
        'source_binding_sha256':'C5_ABLATION_SOURCE_BINDING_v1.json','prepare_result_sha256':'C5_ABLATION_PREPARE_RESULT_v1.json',
        'snapshot_sha256':'C5_ABLATION_PREPARED_CFG_OPTS_v1.mat','runner_preflight_sha256':'C5_ABLATION_RUNNER_PREFLIGHT_v1.json',
        'synthetic_result_sha256':'C5_ABLATION_CROSSLANG_RESULT_v1.json','synthetic_fixture_sha256':'C5_ABLATION_CROSSLANG_FIXTURE_v2.json',
        'runner_sha256':'run_c5_matched_ablation_v1.m','launcher_sha256':'RUN_C5_ABLATION_PARENT_EXACT_v1.ps1',
        'parent_release_contract_sha256':'C5_ABLATION_PARENT_RELEASE_CONTRACT_v1.json'}.items()}
    lock=base.load(files['input_lock_sha256']);contract=base.load(files['run_contract_sha256'])
    binding=base.load(files['source_binding_sha256']);prep=base.load(files['prepare_result_sha256'])
    pref=base.load(files['runner_preflight_sha256']);synth=base.load(files['synthetic_result_sha256'])
    os_path=REPORT/f'c5_matched_ablation_execution/v4/{variant}_NOPLANT_OS_EXIT_v1.json';osrec=base.load(os_path)
    assert osrec['matlab_os_exit_code']==0 and not osrec['plant_authorized']
    assert Path(osrec['command_file']).resolve()==(folder/'RUN_C5_ABLATION_NOPLANT_EXACT_v1.ps1').resolve()
    assert osrec['command_sha256']==base.sha(osrec['command_file'])
    for ref in binding['file_refs']: assert base.sha(ref['path'])==ref['sha256']
    assert prep['status']=='PREPARED_C5_MATCHED_ABLATION_NO_PLANT_WAIT_PARENT_RELEASE_V1'
    assert pref['status']=='PREFLIGHT_COMPLETE_NO_PLANT_WAIT_PARENT_RELEASE_V1' and pref['returned_before_shared_lock_or_episode']
    assert prep['plant_calls']==pref['plant_calls']==0 and not prep['TEST_accessed'] and not pref['TEST_accessed']
    pref_keys={'input_lock_sha256':'input_lock_sha256','run_contract_sha256':'contract_sha256',
               'source_binding_sha256':'source_binding_sha256','prepare_result_sha256':'prepare_result_sha256',
               'snapshot_sha256':'snapshot_sha256','synthetic_result_sha256':'synthetic_result_sha256','runner_sha256':'runner_sha256'}
    for key,prefkey in pref_keys.items(): assert pref[prefkey]==base.sha(files[key]),key
    assert synth['status']=='PASS_SYNTHETIC_CROSSLANGUAGE_ONLY' and synth['max_abs_error']<=2e-12
    assert synth['matlab_helper_sha256']==base.sha(folder/'delayed_prediction_step_candidate.m')
    pack={s:base.matlab_section_safe(files['snapshot_sha256'],s,decoder) for s in sections}
    leaves={s:base.equal_tree(old[s],pack[s],decoder) for s in ('cfg','opts','modelIdentity','sceneIdentity')}
    assert leaves['cfg']==120 and leaves['opts']==43 and leaves['modelIdentity']==6
    assert np.array_equal(pack['W0'],old['W0']) and np.max(abs(np.asarray(pack['W0'],dtype=float)))<=60
    assert [base.matlab_text(x) for x in base.matlab_flat(pack['sourceIdentity']['active_paths'])]==[x['path'] for x in lock['active_source_inventory']]
    assert [base.matlab_text(x) for x in base.matlab_flat(pack['sourceIdentity']['active_sha256'])]==[x['sha256'] for x in lock['active_source_inventory']]
    pilot_path=REPORT/f'c5_matched_ablation_parent_raw_review/{variant}_FIRST_RAW_PARENT_AUDIT_v1.json'
    assert base.sha(pilot_path)==pilot_sha
    pilot=base.load(pilot_path);assert pilot['status']=='PASS_C5_MATCHED_ABLATION_FIRST_RAW_ALL_EVENTS'
    assert pilot['natural_os_exit']['exit_code']==0 and pilot['event_count']==1968
    assert pilot['scene_id']==contract['first_scene_id'] and pilot['variant_id']==variant
    artifacts=pilot['run_artifacts'];raw=Path(artifacts['raw_path']);status_path=Path(artifacts['run_status_path'])
    assert base.sha(raw)==artifacts['raw_sha256'] and base.sha(status_path)==artifacts['run_status_sha256']
    pilot_release_path=Path(pilot['source_files']['release']['path']);pilot_release_sha=base.sha(pilot_release_path)
    assert pilot_release_sha==pilot['source_files']['release']['sha256']
    identity=base.matlab_section_safe(raw,'runIdentity',decoder)
    assert base.matlab_text(identity['release_sha256'])==pilot_release_sha
    assert base.matlab_text(identity['variant_id'])==variant and base.matlab_text(identity['scene_id'])==contract['first_scene_id']
    assert base.equal_tree(pack['modelIdentity'],identity['model_identity'],decoder)==6
    old_lock=base.load(pilot['source_files']['lock']['path'])
    assert [x['sha256'] for x in lock['active_source_inventory']]==[x['sha256'] for x in old_lock['active_source_inventory']]
    release={'schema':'C5_MATCHED_ABLATION_PARENT_RELEASE_V1','state':'APPROVED_C5_ABLATION_TAIL11_V1',
             'created_utc':datetime.now(timezone.utc).isoformat(),'phase':'TAIL11','plant_authorized':True,
             'variant_id':variant,'ablation_mode':variant,'candidate':contract['candidate'],'coordinate_mask':[1,1,0],
             'actual_weight_update_enabled':variant=='C5_NO_DELAYED_PREDICTION',
             'actual_prediction_gradient_enabled':False,'legacy_stage1_update_enabled':True,
             **{key:base.sha(path) for key,path in files.items()},
             'first_scene_id':contract['first_scene_id'],'scene_ids':contract['scene_ids'][1:],'max_new_Plant':11,
             'training_steps':0,'optimizer_steps':0,'new_B_sorties':0,'TEST_accessed':False,
             'automatic_retry':False,'parameter_or_seed_search':False,
             'pilot_raw_path':str(raw),'pilot_raw_sha256':base.sha(raw),
             'pilot_run_status_path':str(status_path),'pilot_run_status_sha256':base.sha(status_path),
             'pilot_release_sha256':pilot_release_sha,'pilot_parent_audit_path':str(pilot_path),'pilot_parent_audit_sha256':pilot_sha,
             **{key:contract['limits'][key] for key in ('deadline_utc','minimum_free_bytes','per_scene_output_reserve_bytes','max_output_bytes')}}
    required=base.load(files['parent_release_contract_sha256'])['required_fields']
    tail_required=('pilot_raw_path','pilot_raw_sha256','pilot_run_status_path','pilot_run_status_sha256','pilot_release_sha256')
    assert set(required)|set(tail_required)<=release.keys() and len(release['scene_ids'])==11
    release_path=folder/'C5_ABLATION_TAIL11_PARENT_RELEASE_v1.json';assert not release_path.exists()
    assert not (folder/'C5_ABLATION_FIRST_PARENT_RELEASE_v1.json').exists()
    rows.append({'variant_id':variant,'leaf_counts':leaves,'pilot_raw_sha256':base.sha(raw),
                 'pilot_release_sha256':pilot_release_sha,'pilot_parent_audit_sha256':pilot_sha,
                 'natural_noPlant_OS_exit':0,'noPlant_OS_record_sha256':base.sha(os_path),'new_scene_count':11})
    releases.append((release_path,release))
result={'status':'PASS_V4_NOPLANT_AND_EXACT_EXTERNAL_V3_PILOT_BINDINGS','created_utc':datetime.now(timezone.utc).isoformat(),
        'rows':rows,'reused_pilot_count':2,'authorized_new_Plant':22,'training':0,'TEST_accessed':False,
        'decision':'Run original remaining eleven scenes per configuration once; do not rerun pilots or open TEST.'}
OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
for path,release in releases:
    release['parent_review_path']=str(OUT);release['parent_review_sha256']=base.sha(OUT)
    with path.open('x',encoding='utf-8') as stream:
        json.dump(release,stream,ensure_ascii=False,indent=2);stream.write('\n')
print(json.dumps({'status':result['status'],'parent_review_sha256':base.sha(OUT),'new_Plant_authorized':22,'pilots_reused':2}))
