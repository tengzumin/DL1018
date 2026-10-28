from __future__ import annotations
import argparse, csv, hashlib, json, sys, time, traceback
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import h5py
import numpy as np

OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT))
import reconstruct_stratified as core

MODEL_SOURCE=core.scoped(core.BASE/'corrected_pair_eval_v1/runs/r098/attempt_01/raw_run.mat')
MODEL_SOURCE_SHA='f6fc258dbee1d33dbac608d94f690b23e5329d375d2806d9bb0601a667506ea5'
MODEL_ID='CORRECTED_DSSM14_SEED2026102001_FINAL60000'
MODEL_ARRAY_ID='8de4d6548316c7b6f97382ecc9d5fbce8c00dbf6d10dc4187789b34c9205eb26'
NORMALIZER_ID='533aad9a2c66874cfa67f5d268661835e81e58b797cba7d6fc1c12d4013de5f0'
MODEL_NAMES=('input_mu','input_sigma','input_W','input_b','project_W','project_b','output_W','ssm_tau')
ARRAY_ID_ORDER=('input_W','input_b','input_mu','input_sigma','output_W','project_W','project_b','ssm_tau')
RUNTIME_BETA_RISE_S=1.8
SIDECAR_DIR=OUT/'fixed_model_sidecars'
FAILURES=core.FAILURES
EXPECTED_TRAIN=1536
EXPECTED_VAL=96
EVENTS=1999
MODEL_VALID_START=31
TWO_GIB=2*(1<<30)


def now(): return datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds')
def read_csv(path):
    with Path(path).open('r',newline='',encoding='utf-8-sig') as f: return list(csv.DictReader(f))
def write_csv(path,rows):
    if not rows: return
    with Path(path).open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),extrasaction='ignore'); w.writeheader(); w.writerows(rows)
def write_json(path,obj): Path(path).write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def array_set_id(model,names):
    h=hashlib.sha256()
    for name in names:
        a=np.ascontiguousarray(model[name])
        h.update(name.encode('utf-8')+b'\0')
        h.update(repr((a.shape,str(a.dtype))).encode('ascii')+b'\0')
        h.update(a.tobytes(order='C'))
    return h.hexdigest()

def load_model():
    before=core.signature(MODEL_SOURCE)
    if before['sha256']!=MODEL_SOURCE_SHA: raise RuntimeError('fixed model raw source SHA mismatch')
    with h5py.File(MODEL_SOURCE,'r') as f:
        group=f['opts/stage1_position_runtime/model']
        model={name:np.asarray(group[name],dtype=np.float64) for name in MODEL_NAMES}
    after=core.signature(MODEL_SOURCE)
    if (before['sha256'],before['bytes'],before['mtime_ns'])!=(after['sha256'],after['bytes'],after['mtime_ns']):
        raise RuntimeError('fixed model source SHA/stat changed during read')
    shapes={'input_mu':(1,14),'input_sigma':(1,14),'input_W':(14,32),'input_b':(1,32),
            'project_W':(32,32),'project_b':(1,32),'output_W':(3,33),'ssm_tau':(1,32)}
    for name,a in model.items():
        if a.shape!=shapes[name] or not np.isfinite(a).all(): raise RuntimeError(f'fixed model field shape/nonfinite mismatch: {name} {a.shape}')
    if np.any(model['input_sigma']<=0) or np.any(model['ssm_tau']<=0): raise RuntimeError('fixed model has nonpositive normalizer/tau')
    model_id=array_set_id(model,ARRAY_ID_ORDER)
    normalizer_id=array_set_id(model,('input_mu','input_sigma'))
    if model_id!=MODEL_ARRAY_ID or normalizer_id!=NORMALIZER_ID: raise RuntimeError('fixed model array identity mismatch')
    return model,{'path':str(MODEL_SOURCE),'file_sha256':after['sha256'],'bytes':after['bytes'],'mtime_ns':after['mtime_ns'],
        'model_id':MODEL_ID,'model_array_identity':model_id,'normalizer_identity':normalizer_id,
        'source_sha_stat_unchanged':True,'source_hash_before_seconds':before['hash_seconds'],'source_hash_after_seconds':after['hash_seconds']}

def infer_w0(x,model):
    x=np.asarray(x,dtype=np.float64)
    if x.shape!=(EVENTS,14) or not np.isfinite(x).all(): raise RuntimeError(f'fixed inference requires finite ({EVENTS},14) X14, got {x.shape}')
    drive=np.tanh(((x-model['input_mu'])/model['input_sigma'])@model['input_W']+model['input_b'])
    alpha=np.exp(-.01/model['ssm_tau'])
    state=np.zeros((len(x)-MODEL_VALID_START,32),dtype=np.float64)
    for lag in range(32): state+=(1-alpha)*alpha**lag*drive[31-lag:len(x)-lag]
    h=np.tanh(state@model['project_W']+model['project_b'])
    phi=np.concatenate((h,np.ones((len(h),1),dtype=np.float64)),axis=1)
    phi/=np.sqrt(1.+np.sum(h*h,axis=1,keepdims=True))
    raw=phi@model['output_W'].T
    if raw.shape!=(EVENTS-MODEL_VALID_START,3) or not np.isfinite(raw).all(): raise RuntimeError('fixed W0 output shape/nonfinite mismatch')
    return raw

def split_rows(split):
    split=split.upper()
    if split not in ('TRAIN','VAL'): raise ValueError('split is restricted to TRAIN or VAL')
    for p,h in core.EXPECTED.items():
        if core.sha(p)!=h: raise RuntimeError(f'frozen index SHA mismatch: {p}')
    availability_sha=core.sha(core.AVAILABILITY)
    train_index=read_csv(core.TRAIN_INDEX); raw_index=read_csv(core.RAW_INDEX)
    selected=[r for r in train_index if r['split'].upper()==split]
    raw_selected=[r for r in raw_index if r['split'].upper()==split]
    expected_n=EXPECTED_TRAIN if split=='TRAIN' else EXPECTED_VAL
    if len(selected)!=expected_n or len(raw_selected)!=expected_n: raise RuntimeError(f'{split} index count mismatch')
    rb={r['run_id']:r for r in raw_selected}
    if len(rb)!=expected_n: raise RuntimeError(f'{split} raw index has duplicate run_id')
    availability={r['run_id']:r for r in read_csv(core.AVAILABILITY)} if split=='TRAIN' else {}
    out=[]
    for t in selected:
        r=rb.get(t['run_id'])
        if r is None or r['split'].upper()!=split: raise RuntimeError(f'{split} run_id missing from raw index: {t["run_id"]}')
        if (t['task'],t['role'],t['runtime_scene_id'])!=(r['task'],r['role'],r['runtime_scene_id']): raise RuntimeError(f'{split} task/role/scene mismatch: {t["run_id"]}')
        if (t['cache_path'],t['cache_sha256'],t['raw_sha256'],t['event_h5_sha256'])!=(r['cache_path'],r['cache_sha256'],r['raw_sha256'],r['event_h5_sha256']): raise RuntimeError(f'{split} cache/raw/H5 identity mismatch: {t["run_id"]}')
        cell=int(t['wind_cell']); m=__import__('re').search(r'_W(\d{2})(?:_|$)',r['runtime_scene_id'])
        if not m or int(m.group(1))!=cell: raise RuntimeError(f'{split} wind-cell/runtime-scene mismatch: {t["run_id"]}')
        row=dict(t); row.update(split=split,wind_cell=cell,wind_band=core.wind_band(cell),raw_path=r['raw_path'],raw_path_sha256=r['raw_sha256'],run_start_path=r['run_start_path'],run_start_path_sha256=r['run_start_sha256'],event_h5_path=r['event_h5_path'],event_h5_path_sha256=r['event_h5_sha256'],cache_path=r['cache_path'])
        for key in ('raw_path','run_start_path','event_h5_path','cache_path'): core.scoped(row[key])
        if split=='TRAIN':
            a=availability.get(t['run_id'])
            if not a or a['raw_path']!=r['raw_path'] or a['run_start_path']!=r['run_start_path'] or a['event_h5_path']!=r['event_h5_path']:
                raise RuntimeError(f'TRAIN availability join mismatch: {t["run_id"]}')
        for key in ('raw_path','run_start_path','event_h5_path','cache_path'):
            if not Path(row[key]).is_file(): raise RuntimeError(f'missing {split} input {key}: {row[key]}')
        out.append(row)
    out.sort(key=lambda x:x['run_id'])
    if split=='TRAIN':
        frozen,_=core.check_manifest()
        if len(frozen)!=18: raise RuntimeError('18-sample frozen-strata validation failed')
    return out,{'training_index_sha256':core.sha(core.TRAIN_INDEX),'raw_index_sha256':core.sha(core.RAW_INDEX),'availability_sha256':availability_sha,'sample_count':len(out)}

def metric_rows(sample,arrays,pred_applied):
    targets={'Y_raw':arrays['Y_raw'][MODEL_VALID_START:],
        'Y_clip':arrays['Y_clip'][MODEL_VALID_START:].astype(np.float64),
        'Y_plus_Mrf_raw':arrays['mixed_raw'][MODEL_VALID_START:],
        'Y_plus_Mrf_clip':arrays['mixed_clip'][MODEL_VALID_START:]}
    axes={'X':(0,),'Y':(1,),'Z':(2,),'ALL':(0,1,2)}
    rows=[]
    for target_name,target in targets.items():
        if target.shape!=pred_applied.shape or not np.isfinite(target).all(): raise RuntimeError(f'{sample["run_id"]}: inference target invalid: {target_name}')
        for axis_name,axis_ids in axes.items():
            t=target[:,axis_ids].reshape(-1); p=pred_applied[:,axis_ids].reshape(-1)
            zero_rmse=float(np.sqrt(np.mean(t*t))); prior_rmse=float(np.sqrt(np.mean((p-t)**2)))
            rows.append({'run_id':sample['run_id'],'split':sample['split'],'task':sample['task'],'role':sample['role'],'wind_cell':sample['wind_cell'],'wind_band':sample['wind_band'],'target':target_name,'axis':axis_name,'valid_events':len(target),'target_rms_mps2':float(np.sqrt(np.mean(t*t))),'prior_applied_rms_mps2':float(np.sqrt(np.mean(p*p))),'zero_rmse_mps2':zero_rmse,'prior_applied_rmse_mps2':prior_rmse,'prior_to_zero_rmse_ratio':prior_rmse/zero_rmse if zero_rmse>0 else 'UNDEFINED_ZERO_ENERGY','relative_sse_reduction_vs_zero':1-(prior_rmse/zero_rmse)**2 if zero_rmse>0 else 'UNDEFINED_ZERO_ENERGY','prior_error_bias_mps2':float(np.mean(p-t)),'zero_error_bias_mps2':float(-np.mean(t))})
    return rows

def sidecar_payload(sample,arrays,pred_raw,pred_applied,beta_candidate):
    return {'X14':np.asarray(arrays['x14'],dtype=np.float32),'event_time_s':np.asarray(arrays['event_time_s'],dtype=np.float64),
        'event_index':np.asarray(arrays['event_index'],dtype=np.uint32),'plant_index':np.asarray(arrays['plant_index'],dtype=np.uint32),'raw_index':np.asarray(arrays['raw_index'],dtype=np.uint32),
        'phase_code':np.asarray(arrays['phase_code'],dtype=np.uint8),'ready':np.asarray(arrays['ready'],dtype=np.uint8),
        'beta_teacher':np.asarray(arrays['beta_teacher'],dtype=np.float64),'beta_candidate':np.asarray(beta_candidate,dtype=np.float32),
        'Y_raw':np.asarray(arrays['Y_raw'],dtype=np.float64),'Y_clip':np.asarray(arrays['Y_clip'],dtype=np.float32),'r_f':np.asarray(arrays['r_f'],dtype=np.float64),
        'mixed_raw':np.asarray(arrays['mixed_raw'],dtype=np.float64),'mixed_clip':np.asarray(arrays['mixed_clip'],dtype=np.float32),
        'a_req':np.asarray(arrays['a_req'],dtype=np.float64),'a_f':np.asarray(arrays['a_f'],dtype=np.float64),'a_actual':np.asarray(arrays['a_actual'],dtype=np.float64),
        'valid_start_zero_based':np.asarray(MODEL_VALID_START,dtype=np.uint32),'pred_raw_valid':np.asarray(pred_raw,dtype=np.float64),'pred_applied_valid':np.asarray(pred_applied,dtype=np.float64),
        'run_id':np.asarray(sample['run_id']),'split':np.asarray(sample['split']),'task':np.asarray(sample['task']),'role':np.asarray(sample['role']),'runtime_scene_id':np.asarray(sample['runtime_scene_id'])}

def bytes_per_event_upper():
    n=EVENTS;v=EVENTS-MODEL_VALID_START
    arrays={'x14':np.empty((n,14),np.float32),'event_time_s':np.empty(n,np.float64),'event_index':np.empty(n,np.uint32),
        'plant_index':np.empty(n,np.uint32),'raw_index':np.empty(n,np.uint32),'phase_code':np.empty(n,np.uint8),'ready':np.empty(n,np.uint8),
        'beta_teacher':np.empty(n,np.float64),'Y_raw':np.empty((n,3),np.float64),'Y_clip':np.empty((n,3),np.float32),
        'r_f':np.empty((n,3),np.float64),'mixed_raw':np.empty((n,3),np.float64),'mixed_clip':np.empty((n,3),np.float32),
        'a_req':np.empty((n,3),np.float64),'a_f':np.empty((n,3),np.float64),'a_actual':np.empty((n,3),np.float64)}
    payload=sidecar_payload({'run_id':'sample','split':'TRAIN','task':'task','role':'B','runtime_scene_id':'scene'},arrays,
        np.empty((v,3),np.float64),np.empty((v,3),np.float64),np.empty(n,np.float32))
    return sum(int(a.nbytes) for a in payload.values()),len(payload)

def estimate_storage(samples):
    per,arrays_per_run=bytes_per_event_upper()
    raw=int(len(samples)*per);npz_headers=len(samples)*16*(1<<10);tables=64*(1<<20)
    return raw,int(raw+npz_headers+tables),{'payload_bytes_per_run':per,'arrays_per_run':arrays_per_run,'npz_header_allowance_bytes':npz_headers,'table_and_state_allowance_bytes':tables}

def state_paths(split,worker_sha):
    name=f'{split}_FIXED_MODEL_{worker_sha[:12]}'
    return OUT/(name+'_PHASE_STATE.json'),OUT/(name+'_RUNS.csv'),OUT/(name+'_METRICS.csv')

def load_prior(path):
    if not path.is_file(): return {},[]
    runs={r['run_id']:r for r in read_csv(path)}
    return runs,list(runs.values())

def load_metrics(path): return read_csv(path) if path.is_file() else []

def source_matches(sample,record,script_sha,core_sha):
    if record.get('status')!='PASS' or record.get('worker_script_sha256')!=script_sha or record.get('core_script_sha256')!=core_sha: return False
    paths={k:core.scoped(sample[k+'_path']) for k in ('raw','run_start','event_h5','cache')}
    expected={'raw':sample['raw_path_sha256'],'run_start':sample['run_start_path_sha256'],'event_h5':sample['event_h5_path_sha256'],'cache':sample['cache_sha256']}
    current={k:core.signature(p) for k,p in paths.items()}
    if not all(current[k]['sha256']==expected[k]==record[k+'_sha256_after'] and current[k]['bytes']==int(record[k+'_bytes']) and current[k]['mtime_ns']==int(record[k+'_mtime_ns_after']) for k in paths): return False
    sidecar=Path(record['sidecar_path'])
    return sidecar.is_file() and core.sha(sidecar)==record['sidecar_sha256']

def run_smoke(run_id,worker_sha,core_sha,sha_availability):
    samples,_=core.check_manifest()
    matches=[s for s in samples if s['run_id']==run_id] if run_id else samples[:1]
    if len(matches)!=1: raise RuntimeError(f'smoke run_id must select exactly one frozen stratum sample: {run_id}')
    sample=matches[0];sample['split']='TRAIN'
    model,model_info=load_model();runtime_before=core.signature(core.RUNTIME_SOURCE)
    if runtime_before['sha256']!=core.RUNTIME_SOURCE_SHA: raise RuntimeError('frozen runtime source SHA mismatch')
    result,arrays=core.reconstruct(sample,return_arrays=True)
    pred_raw=infer_w0(arrays['x14'],model);beta_candidate=np.clip(arrays['event_time_s']/RUNTIME_BETA_RISE_S,0.,1.)
    pred_applied=beta_candidate[MODEL_VALID_START:,None]*np.clip(pred_raw,-3.,3.)
    fit=metric_rows(sample,arrays,pred_applied);payload=sidecar_payload(sample,arrays,pred_raw,pred_applied,beta_candidate)
    SIDECAR_DIR.mkdir(parents=True,exist_ok=True)
    version=f'worker-{worker_sha[:8]}_core-{core_sha[:8]}'
    sidecar=SIDECAR_DIR/f'SMOKE_{sample["run_id"]}_{version}.npz'
    state_path=OUT/f'SMOKE_{sample["run_id"]}_{version}_STATE.json'
    metrics_path=OUT/f'SMOKE_{sample["run_id"]}_{version}_METRICS.csv'
    if sidecar.exists() or state_path.exists() or metrics_path.exists(): raise RuntimeError('smoke output already exists; refusing to overwrite')
    tmp=sidecar.with_suffix('.npz.tmp')
    with tmp.open('xb') as f: np.savez_compressed(f,**payload)
    tmp.replace(sidecar)
    model_after=core.signature(MODEL_SOURCE);runtime_after=core.signature(core.RUNTIME_SOURCE)
    if (model_after['sha256'],model_after['bytes'],model_after['mtime_ns'])!=(model_info['file_sha256'],model_info['bytes'],model_info['mtime_ns']): raise RuntimeError('fixed model source changed during smoke')
    if (runtime_after['sha256'],runtime_after['bytes'],runtime_after['mtime_ns'])!=(runtime_before['sha256'],runtime_before['bytes'],runtime_before['mtime_ns']): raise RuntimeError('runtime source changed during smoke')
    for p,h in core.EXPECTED.items():
        if core.sha(p)!=h: raise RuntimeError(f'frozen index SHA changed during smoke: {p}')
    if core.sha(core.AVAILABILITY)!=sha_availability: raise RuntimeError('availability SHA changed during smoke')
    write_csv(metrics_path,fit)
    state={'phase':'ONE_SAMPLE_FIXED_MODEL_SIDECAR_SMOKE','status':'PASS_SMOKE','completed_local':now(),'command':f'python -B reports/train_pcf_contract_reconstruction_20261022/reconstruct_full_worker.py --smoke --run-id {sample["run_id"]}',
        'worker_script':str(Path(__file__).resolve()),'worker_script_sha256':worker_sha,'core_script':str(Path(core.__file__).resolve()),'core_script_sha256':core_sha,
        'model':model_info,'run_id':sample['run_id'],'task':sample['task'],'role':sample['role'],'wind_cell':sample['wind_cell'],'runtime_scene_id':sample['runtime_scene_id'],
        'source_checks':{k:{'sha256_before':result[k+'_sha256_before'],'sha256_after':result[k+'_sha256_after'],'bytes':result[k+'_bytes'],'mtime_ns_before':result[k+'_mtime_ns_before'],'mtime_ns_after':result[k+'_mtime_ns_after']} for k in ('raw','run_start','event_h5','cache')},
        'source_sha_stat_unchanged':True,'closure_checks':{k:result[k] for k in ('a0_replay_max_abs_mps2','a_req_vs_a0_minus_u_max_abs_mps2','physical_Y_vs_event_H5_max_abs_mps2','X14_vs_event_H5_max_abs','mixed_identity_max_abs_mps2','event_time_vs_transition_max_abs_s','raw_log_teacher_beta_vs_event_H5_max_abs','Y_clip_vs_event_H5_max_abs_mps2')},
        'teacher_beta_source':'same-run raw log.position_event_beta, verified through H5/cache','candidate_beta_formula':'clip(event_time_s/1.8,0,1)','valid_inference_events':len(pred_raw),
        'sidecar_path':str(sidecar.resolve()),'sidecar_sha256':core.sha(sidecar),'sidecar_bytes':sidecar.stat().st_size,'sidecar_payload_uncompressed_bytes':sum(int(a.nbytes) for a in payload.values()),
        'metrics_csv':str(metrics_path.resolve()),'metrics_rows':len(fit),'optimizer_steps':0,'plant_calls':0,'gpu_jobs':0,'test_accessed':False,'dev_labels_used':False}
    with state_path.open('x',encoding='utf-8') as f:f.write(json.dumps(state,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({'status':'PASS_SMOKE','run_id':sample['run_id'],'sidecar_bytes':state['sidecar_bytes'],'state_path':str(state_path.resolve())},ensure_ascii=False))

def main():
    ap=argparse.ArgumentParser(description='Read-only fixed W0 inference and offline PCF target reconstruction; no training or plant calls.')
    ap.add_argument('--split',choices=('TRAIN','VAL'),default='TRAIN')
    ap.add_argument('--resume',action='store_true')
    ap.add_argument('--execute-after-audit',action='store_true',help='explicitly execute after source review; default is plan-only')
    ap.add_argument('--smoke',action='store_true',help='write exactly one fixed-model sidecar for a frozen 18-stratum TRAIN sample; does not start full TRAIN')
    ap.add_argument('--run-id',default=None,help='optional frozen TRAIN sample id for --smoke')
    args=ap.parse_args(); split=args.split
    if args.smoke:
        if split!='TRAIN' or args.execute_after_audit or args.resume: raise ValueError('--smoke is separate from full execution/resume and restricted to TRAIN')
        worker_sha=core.sha(Path(__file__));core_sha=core.sha(Path(core.__file__))
        sha_availability=core.sha(core.AVAILABILITY)
        try: run_smoke(args.run_id,worker_sha,core_sha,sha_availability)
        except Exception as e:
            core.fail_record(f'python -B reports/train_pcf_contract_reconstruction_20261022/reconstruct_full_worker.py --smoke --run-id {args.run_id or "FIRST_STRATUM"}','one_sample_fixed_model_sidecar_smoke',f'{type(e).__name__}: {e}','at most one frozen TRAIN sample was touched; source data remain read-only; a partial .npz.tmp may remain only in the new report directory','inspect the exact failure; keep it in the failure ledger; resume only after a focused fix with a new worker SHA')
            raise
        return
    if args.run_id is not None: raise ValueError('--run-id is only valid with --smoke')
    command=f'python -B reports/train_pcf_contract_reconstruction_20261022/reconstruct_full_worker.py --execute-after-audit --split {split}'+(' --resume' if args.resume else '')
    samples,index_ids=split_rows(split)
    worker_sha=core.sha(Path(__file__)); core_sha=core.sha(Path(core.__file__))
    state_path,runs_path,metrics_path=state_paths(split,worker_sha)
    sidecar_raw,sidecar_conservative,sidecar_layout=estimate_storage(samples)
    if sidecar_conservative>=TWO_GIB: raise RuntimeError(f'sidecar budget exceeded: conservative={sidecar_conservative} bytes')
    if split=='VAL':
        train_state=state_paths('TRAIN',worker_sha)[0]
        if not train_state.is_file(): raise RuntimeError('VAL is gated on successful TRAIN1536 completion')
        train=json.loads(train_state.read_text(encoding='utf-8'))
        if train.get('status')!='PASS_TRAIN_1536' or train.get('worker_script_sha256')!=worker_sha or train.get('core_script_sha256')!=core_sha or train.get('model',{}).get('model_array_identity')!=MODEL_ARRAY_ID:
            raise RuntimeError('VAL is gated on a matching PASS_TRAIN_1536 release')
    plan={'split':split,'samples':len(samples),'command':command,'worker_script':str(Path(__file__).resolve()),'worker_script_sha256':worker_sha,'core_script':str(Path(core.__file__).resolve()),'core_script_sha256':core_sha,
        'source_indices':index_ids,'fixed_model_source_expected_sha256':MODEL_SOURCE_SHA,'fixed_model_id':MODEL_ID,'fixed_model_array_identity':MODEL_ARRAY_ID,
        'sidecar_array_payload_uncompressed_bytes':sidecar_raw,'sidecar_conservative_upper_bound_bytes':sidecar_conservative,'sidecar_layout':sidecar_layout,
        'sidecar_budget_bytes':TWO_GIB,'execution_authorized_by_this_flag':bool(args.execute_after_audit),'optimizer_steps':0,'plant_calls':0,'gpu_jobs':0,'test_accessed':False,'dev_labels_used':False}
    if not args.execute_after_audit:
        print(json.dumps(plan,indent=2,ensure_ascii=False)); return
    runtime_before=core.signature(core.RUNTIME_SOURCE)
    if runtime_before['sha256']!=core.RUNTIME_SOURCE_SHA: raise RuntimeError('frozen runtime source SHA mismatch')
    model,model_info=load_model(); start=time.perf_counter(); started=now()
    old,records=load_prior(runs_path) if args.resume else ({},[])
    metrics=load_metrics(metrics_path) if args.resume else []
    done=[]; done_metrics=[]; sample_wall=[]
    state={'phase':f'{split}_FIXED_MODEL_INFERENCE_AND_OFFLINE_TARGET_RECONSTRUCTION','status':'RUNNING','started_local':started,'command':command,
        'worker_script':str(Path(__file__).resolve()),'worker_script_sha256':worker_sha,'core_script':str(Path(core.__file__).resolve()),'core_script_sha256':core_sha,
        'source_indices':index_ids,'runtime_source_path':str(core.RUNTIME_SOURCE.resolve()),'runtime_source_sha256_before':runtime_before['sha256'],'model':model_info,'split':split,'expected_samples':len(samples),'completed_run_ids':[],'failures':[],
        'optimizer_steps':0,'plant_calls':0,'gpu_jobs':0,'test_accessed':False,'dev_labels_used':False,'sidecar_array_payload_uncompressed_bytes':sidecar_raw,
        'sidecar_conservative_upper_bound_bytes':sidecar_conservative,'sidecar_layout':sidecar_layout,'sidecar_budget_bytes':TWO_GIB,'full_1536_or_96': 'RUNNING'}
    write_json(state_path,state); SIDECAR_DIR.mkdir(parents=True,exist_ok=True)
    # Refuse to exceed the derived-data budget before creating any sidecar.
    written=sum(p.stat().st_size for p in SIDECAR_DIR.glob('*.npz'))
    if written+sidecar_conservative>=TWO_GIB: raise RuntimeError('existing derived sidecars plus conservative bound exceed 2 GiB')
    for i,sample in enumerate(samples,1):
        try:
            prior=old.get(sample['run_id']) if args.resume else None
            if prior and source_matches(sample,prior,worker_sha,core_sha):
                done.append(prior); done_metrics.extend([r for r in metrics if r['run_id']==sample['run_id']])
                state['completed_run_ids'].append(sample['run_id']);state['progress']=f'{i}/{len(samples)}';write_csv(runs_path,done);write_csv(metrics_path,done_metrics);write_json(state_path,state)
                print(f'[{i}/{len(samples)}] RESUME {sample["run_id"]}',flush=True);continue
            sample_start=time.perf_counter()
            result,arrays=core.reconstruct(sample,return_arrays=True)
            pred_raw=infer_w0(arrays['x14'],model)
            beta_candidate=np.clip(arrays['event_time_s']/RUNTIME_BETA_RISE_S,0.,1.)
            beta_valid=beta_candidate[MODEL_VALID_START:,None]
            pred_applied=beta_valid*np.clip(pred_raw,-3.,3.)
            if not np.isfinite(pred_applied).all(): raise RuntimeError('candidate-clock W0 output is nonfinite')
            fit=metric_rows(sample,arrays,pred_applied)
            payload=sidecar_payload(sample,arrays,pred_raw,pred_applied,beta_candidate)
            sidecar=SIDECAR_DIR/f'{split}_{sample["run_id"]}_{worker_sha[:12]}.npz'
            tmp=sidecar.with_suffix('.npz.tmp')
            with tmp.open('wb') as f: np.savez_compressed(f,**payload)
            tmp.replace(sidecar)
            sidecar_sha=core.sha(sidecar); sidecar_bytes=sidecar.stat().st_size
            run_row={**result,'status':'PASS','split':split,'worker_script_sha256':worker_sha,'core_script_sha256':core_sha,'model_id':MODEL_ID,'model_source_sha256':model_info['file_sha256'],'model_array_identity':MODEL_ARRAY_ID,
                'candidate_beta_formula':'clip(event_time_s/1.8,0,1)','teacher_beta_source':'same-run raw log.position_event_beta, verified through H5/cache','teacher_candidate_beta_max_abs':float(np.max(np.abs(arrays['beta_teacher']-beta_candidate))),
                'valid_inference_events':len(pred_raw),'sidecar_path':str(sidecar.resolve()),'sidecar_sha256':sidecar_sha,'sidecar_bytes':sidecar_bytes,'completed_local':now()}
            for k in ('raw','run_start','event_h5','cache'):
                run_row[k+'_sha256_after']=result[k+'_sha256_after'];run_row[k+'_bytes']=result[k+'_bytes'];run_row[k+'_mtime_ns_after']=result[k+'_mtime_ns_after']
            done=[r for r in done if r['run_id']!=sample['run_id']]+[run_row]
            done_metrics=[r for r in done_metrics if r['run_id']!=sample['run_id']]+fit
            write_csv(runs_path,done);write_csv(metrics_path,done_metrics)
            sample_wall.append(time.perf_counter()-sample_start)
            state['completed_run_ids'].append(sample['run_id']);state['progress']=f'{i}/{len(samples)}';state['last_completed_run_id']=sample['run_id'];state['sidecars_written']=len(done);state['sidecar_bytes_written']=sum(int(r['sidecar_bytes']) for r in done);state['updated_local']=now();write_json(state_path,state)
            print(f'[{i}/{len(samples)}] PASS {sample["run_id"]}',flush=True)
        except Exception as e:
            error=f'{type(e).__name__}: {e}'
            core.fail_record(command,'fixed_model_full_worker',error,'current sample may have partial temporary sidecar only; source data remain read-only; completed samples checkpointed','inspect exact error; remove only the incomplete .npz.tmp generated in this report directory, then rerun with --resume after focused correction')
            state.update(status='FAILED',failed_run_id=sample['run_id'],error=error,traceback=traceback.format_exc(),updated_local=now(),wall_seconds=time.perf_counter()-start);write_json(state_path,state);raise
    try:
        model_after=core.signature(MODEL_SOURCE);runtime_after=core.signature(core.RUNTIME_SOURCE)
        if (model_after['sha256'],model_after['bytes'],model_after['mtime_ns'])!=(model_info['file_sha256'],model_info['bytes'],model_info['mtime_ns']): raise RuntimeError('fixed model source SHA/stat changed during phase')
        if (runtime_after['sha256'],runtime_after['bytes'],runtime_after['mtime_ns'])!=(runtime_before['sha256'],runtime_before['bytes'],runtime_before['mtime_ns']): raise RuntimeError('frozen runtime source SHA/stat changed during phase')
        for p,h in core.EXPECTED.items():
            if core.sha(p)!=h: raise RuntimeError(f'frozen index SHA changed during phase: {p}')
        if core.sha(core.AVAILABILITY)!=index_ids['availability_sha256']: raise RuntimeError('availability index SHA changed during phase')
    except Exception as e:
        error=f'{type(e).__name__}: {e}';core.fail_record(command,'full_worker_final_input_identity',error,'phase outputs remain checkpointed; source data are read-only','inspect the exact source identity mismatch before any resume')
        state.update(status='FAILED',error=error,traceback=traceback.format_exc(),updated_local=now(),wall_seconds=time.perf_counter()-start);write_json(state_path,state);raise
    state['runtime_source_sha256_after']=runtime_after['sha256'];state['model_source_sha256_after']=model_after['sha256'];state['all_fixed_sources_sha_stat_unchanged']=True
    status='PASS_TRAIN_1536' if split=='TRAIN' else 'PASS_VAL_96'
    state.update(status=status,completed_local=now(),wall_seconds=time.perf_counter()-start,runs_csv=str(runs_path.resolve()),metrics_csv=str(metrics_path.resolve()),all_samples_passed=(len(done)==len(samples)),sidecar_count=len(done),sidecar_bytes_written=sum(int(r['sidecar_bytes']) for r in done),sidecar_hashes_present=True,sidecar_budget_stayed_within_2GiB=(sum(int(r['sidecar_bytes']) for r in done)<TWO_GIB),sample_wall_seconds_mean=float(np.mean(sample_wall)) if sample_wall else None)
    write_json(state_path,state)
    print(json.dumps({'status':status,'samples':len(done),'wall_seconds':state['wall_seconds'],'sidecar_bytes_written':state['sidecar_bytes_written'],'phase_state':str(state_path.resolve())},ensure_ascii=False))

if __name__=='__main__': main()
