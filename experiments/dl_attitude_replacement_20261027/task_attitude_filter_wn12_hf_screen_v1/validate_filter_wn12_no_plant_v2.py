from __future__ import annotations
import copy,hashlib,json,pathlib,re,sys
ROOT=pathlib.Path(__file__).resolve().parent
PARENT=ROOT.parents[1]/'dl_attitude_replacement_20261026'/'gru_stream_cosine_tracking_head_full72_v1'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
def j(path):return json.loads(path.read_text(encoding='utf-8'))
def check(ok,msg):
 if not ok:errors.append(msg)
errors=[]
manifest=j(ROOT/'MANIFEST.json');lock=j(ROOT/'SOURCE_LOCK_v1.json');lock2=j(ROOT/'SOURCE_LOCK_v2.json');cfg=j(ROOT/'LOCKED_CFG.json');release=j(ROOT/'RELEASE.json');diff=j(ROOT/'SOURCE_DIFF_v1.json');diff2=j(ROOT/'SOURCE_DIFF_v2.json');input_lock=j(ROOT/'INPUT_LOCK_v1.json');dep=j(ROOT/'DEPENDENCY_EXTERNAL_LOCK_v1.json')
check(len(manifest['records'])==12,'manifest record count')
ids=[r['scene_id'] for r in manifest['records']]
check(ids==['DL1018_DEV_T1_C10_W09','DL1018_VAL_T1_C07_W14','DL1018_DEV_T2_C09_W10','DL1018_VAL_T2_C04_W14','DL1018_DEV_T3_C09_W09','DL1018_VAL_T3_C01_W14','DL1018_DEV_T1_C01_W15','DL1018_VAL_T2_C05_W15','DL1018_VAL_T3_C02_W15','DL1018_VAL_T1_C00_W07','DL1018_DEV_T2_C00_W04','DL1018_DEV_T3_C00_W05'],'locked 12-scene order')
check(sum(r['source_split']=='DEV' for r in manifest['records'])==6 and sum(r['source_split']=='VAL' for r in manifest['records'])==6,'DEV/VAL balance')
check(sum(r['screen_band']=='HF' for r in manifest['records'])==6 and sum(r['wind_index']==15 for r in manifest['records'])==3 and sum(0<=r['wind_index']<=8 for r in manifest['records'])==3,'band counts')
check(manifest['TEST_read'] is False and release['TEST_read'] is False and release['status']=='DRAFT' and release['authorized_Plant_calls']==0 and not release['authorized_scenes'],'TEST/authorization boundary')
check(release['schema']=='DL1018_GRU_STREAM_DEV_RELEASE_V1','release schema compatibility')
check(release['source_lock_sha256']==sha(ROOT/'SOURCE_LOCK_v2.json') and release['source_diff_sha256']==sha(ROOT/'SOURCE_DIFF_v2.json'),'active v2 source locks')
check(release['historical_source_lock_v1_sha256']==sha(ROOT/'SOURCE_LOCK_v1.json') and release['historical_source_diff_v1_sha256']==sha(ROOT/'SOURCE_DIFF_v1.json'),'historical v1 lineage locks')
check(release['driver_sha256']==sha(ROOT/'run_gru_stream_tracking_head_filter_wn12_attempt.m'),'active wrapper release SHA')
check(release['preflight_script_sha256']==sha(ROOT/'validate_filter_wn12_no_plant_v2.py'),'v2 preflight release SHA')
check(cfg['command_filter']['wn']==[12,12,12] and cfg['command_filter']['damping']==[1,1,1] and cfg['command_filter']['acceleration_limit_numeric_labels']==['Inf','Inf',6],'filter config')
check(diff['candidate_runner_work_changed_files']==1 and diff['candidate_runner_work_added_files']==0 and diff['candidate_runner_work_files_copied']==59,'source diff counts')
parent_lock_path=pathlib.Path(lock['direct_parent_source_lock_path']);parent_lock_ok=parent_lock_path.is_file() and sha(parent_lock_path)==lock['direct_parent_source_lock_sha256']
check(parent_lock_ok,'parent source lock SHA')
if parent_lock_ok:
 parent_files={x['relative_path']:x['sha256'] for x in j(parent_lock_path)['files']}
 new_files={x['relative_path']:x['sha256'] for x in lock['files']}
 check(set(parent_files)==set(new_files),'source path set differs from parent')
 for rel,oldsha in parent_files.items():
  item=next(x for x in lock['files'] if x['relative_path']==rel)
  if rel=='matlab/runtime/prepare_mlp15_dev72_no_plant.m':check(lock['source_exception']['parent_sha256']==oldsha,'prepare parent SHA');check(item['sha256']==lock['source_exception']['new_sha256'],'prepare adjusted SHA')
  else:check(item['sha256']==oldsha,'unapproved source delta '+rel)
parent_cfg_path=PARENT/'LOCKED_CFG.json';check(parent_cfg_path.is_file() and sha(parent_cfg_path)==cfg['provenance']['inherited_sha256'],'parent config SHA')
if parent_cfg_path.is_file():
 parent_cfg=j(parent_cfg_path);cur=copy.deepcopy(cfg);orig=copy.deepcopy(parent_cfg)
 for obj in (cur,orig):obj.pop('filter_change',None);obj.pop('study_id',None);obj.pop('schema',None);obj.pop('provenance',None)
 cur['command_filter']['wn']=orig['command_filter']['wn'];check(cur==orig,'only config delta is command_filter.wn')
for f in lock['files']:
 p=ROOT/'candidate_runner_work'/pathlib.Path(f['relative_path']);check(p.is_file() and sha(p)==f['sha256'],'source '+f['relative_path'])
check(lock2['schema']=='DL1018_GRU_FILTER_WN12_SCREEN_SOURCE_LOCK_V2' and lock2['root']==str(ROOT.resolve()) and lock2['file_count']==60 and len(lock2['files'])==60,'v2 source lock schema/root/count')
check(lock2['parent_source_lock_v1_sha256']==sha(ROOT/'SOURCE_LOCK_v1.json'),'v2 parent lock SHA')
v2_paths={x['relative_path'] for x in lock2['files']}
v2_runtime={x for x in v2_paths if x.startswith('candidate_runner_work/')}
check(len(v2_runtime)==59 and v2_paths-v2_runtime=={'run_gru_stream_tracking_head_filter_wn12_attempt.m'},'v2 lock scopes 59 runtime files plus wrapper')
for f in lock2['files']:
 p=ROOT/pathlib.Path(f['relative_path']);check(p.is_file() and sha(p)==f['sha256'],'v2 source '+f['relative_path'])
v1_runtime={x['relative_path']:x['sha256'] for x in lock['files']}
for f in lock2['files']:
 if f['relative_path'].startswith('candidate_runner_work/'):
  rel=f['relative_path'].removeprefix('candidate_runner_work/')
  check(v1_runtime.get(rel)==f['sha256'],'v2 runtime differs from historical v1 lock '+rel)
wrapper_old=lock['study_artifacts'][0]['sha256'];wrapper_now=sha(ROOT/'run_gru_stream_tracking_head_filter_wn12_attempt.m')
check(diff2['schema']=='DL1018_GRU_FILTER_WN12_SCREEN_SOURCE_DIFF_V2' and diff2['parent_source_lock_v1_sha256']==sha(ROOT/'SOURCE_LOCK_v1.json'),'v2 source diff lineage')
check(diff2['candidate_runner_work_file_count']==59 and diff2['candidate_runner_work_changed_files_vs_v1']==0 and diff2['current_wrapper_sha256']==wrapper_now,'v2 diff runtime/wrapper identity')
check(lock2['historical_wrapper_lineage']['v1_recorded_wrapper_sha256']==wrapper_old and lock2['historical_wrapper_lineage']['v1_wrapper_bytes_available'] is False and lock2['historical_wrapper_lineage']['current_wrapper_sha256']==wrapper_now,'v1/v2 wrapper boundary')
for md in dep['copied_metadata']:
 src=pathlib.Path(md['source_path']);dst=ROOT/md['study_relative_copy']
 check(src.is_file() and sha(src)==md['sha256'],'metadata parent SHA '+md['study_relative_copy'])
 check(dst.is_file() and sha(dst)==md['copied_sha256']==md['sha256'],'metadata copied SHA '+md['study_relative_copy'])
parent_payload=j(ROOT/'MLP15_DEV72_PAYLOAD_MANIFEST_v2.json')
check(parent_payload['scene_count']==72 and parent_payload['test_data_read'] is False and all(r['scene_id'].startswith(('DL1018_DEV_','DL1018_VAL_')) for r in parent_payload['records']),'runtime metadata DEV/VAL-only')
for e in dep['external_files']:
 p=pathlib.Path(e['path']);check(p.is_file() and sha(p)==e['sha256'],'external SHA '+e['role'])
for r in manifest['records']:
 for pk,hk in [('payload_path','payload_sha256'),('b_raw_path','b_raw_sha256'),('b_status_path','b_status_sha256'),('c5_raw_path','c5_raw_sha256'),('c5_status_path','c5_status_sha256')]:
  p=pathlib.Path(r[pk]);check(p.is_file() and sha(p)==r[hk],r['scene_id']+' '+pk)
check(input_lock['screen_gates']['Q_m']['candidate_must_be_lte_B'] and input_lock['screen_gates']['Q_m']['candidate_must_be_lte_1_05_times_C5'],'Q gates')
check(input_lock['screen_gates']['task_SO3']['candidate_must_be_strictly_lt_B'] and input_lock['screen_gates']['task_SO3']['candidate_must_be_strictly_lt_C5'],'task SO3 gates')
raw=ROOT/'runs'/'DL1018_DEV_T1_C10_W09'/'raw_run.mat';status_path=raw.with_name('run_status.json')
check(raw.is_file() and status_path.is_file(),'engineering-gate raw/status present')
if status_path.is_file():
 status=j(status_path);check(sha(raw)==status['raw_sha256'] and status['state']=='COMPLETED' and status['TEST_read'] is False,'engineering-gate raw/status identity')
raws=list((ROOT/'runs').rglob('raw_run.mat')) if (ROOT/'runs').exists() else []
check(raws==[raw],'only the authorized first candidate raw exists')
files=[p for p in ROOT.rglob('*') if p.is_file()]
check(not any(p.suffix.lower() in {'.h5','.hdf5','.pt','.pth','.ckpt'} for p in files),'no copied model/checkpoint artifacts')
check(not any(re.search(r'test',str(p.relative_to(ROOT)),re.I) for p in files),'TEST artifact path present')
for k,v in release['execution_input_hashes'].items():check(sha(ROOT/k)==v,'release input '+k)
if errors:
 print('FAIL_NO_PLANT_VALIDATION')
 for e in errors:print(' - '+e)
 sys.exit(1)
print('PASS_NO_PLANT_VALIDATION_V2: 12 selected inputs, 3 byte-identical parent metadata files, 9 shared external dependency SHAs, 59 locked runtime files plus current wrapper, v1 first-run lineage retained, wn-only controller config delta, only first raw present, DRAFT/0 Plant, TEST=false.')
