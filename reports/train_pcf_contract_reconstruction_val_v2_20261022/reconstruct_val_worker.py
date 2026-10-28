from __future__ import annotations
import argparse, csv, hashlib, importlib.util, json, sys, time, traceback
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
TRAIN_OUTPUT=core.ROOT/'reports/train_pcf_contract_reconstruction_20261022'
TRAIN_GATE=core.ROOT/'reports/train_pcf_contract_parent_review_20261022/TRAIN_COMPLETED_PHASE_PARENT_GATE.json'
FROZEN_CORE=TRAIN_OUTPUT/'reconstruct_stratified.py'
TRAIN_STATE=TRAIN_OUTPUT/'TRAIN_FIXED_MODEL_5ca776c5f476_PHASE_STATE.json'
TRAIN_RUNS=TRAIN_OUTPUT/'TRAIN_FIXED_MODEL_5ca776c5f476_RUNS.csv'
TRAIN_METRICS=TRAIN_OUTPUT/'TRAIN_FIXED_MODEL_5ca776c5f476_METRICS.csv'
TRAIN_GATE_SHA='b0be7a622dd3ea0cfa402e3fb3eddc0d3eaed37df4ed1760abd1c1370477c501'
TRAIN_CORE_SHA='d2e2c807b8119b32eddba8f765c6c566bee40d5e37c0590363f9091d30a47f70'
TRAIN_WORKER_SHA='5ca776c5f476c8e7ad824c11ab1381d48b6fdf0b385f9471522a8f5826a8021a'
TRAIN_STATE_SHA='b5fb66aafc7f934ae199037bd318c85974d1e41724bc54c805ed14900beaf002'
TRAIN_RUNS_SHA='4a072c8006042cbffa5e653e450432c748f337fa45790c330b9aa58a8ac32190'
TRAIN_METRICS_SHA='c4d5fa3092266daf133977b8ffc97e30a1616516845f080032d97e19af0c0866'
SCHEMA_AUDIT_CSV=OUT/'VAL96_RUNSTART_SCHEMA_AUDIT.csv'
SCHEMA_AUDIT_STATE=OUT/'VAL96_RUNSTART_SCHEMA_AUDIT.json'
SCHEMA_AUDIT_CSV_SHA='fe189518e238200cb572c8825fac8c435036ba4cbb6ef4c9669a57ccad3d59d5'
SCHEMA_AUDIT_STATE_SHA='dee6e30248e55653cda3fde2d0f3019f1fc56f8c7be4a5e62ff410747f4e07cd'


def now(): return datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds')
def read_csv(path):
    with Path(path).open('r',newline='',encoding='utf-8-sig') as f: return list(csv.DictReader(f))
def write_csv(path,rows):
    if not rows: return
    with Path(path).open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),extrasaction='ignore'); w.writeheader(); w.writerows(rows)
def write_json(path,obj): Path(path).write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def check_train_gate():
    if core.sha(TRAIN_GATE)!=TRAIN_GATE_SHA: raise RuntimeError('pinned completed TRAIN parent gate SHA mismatch')
    gate=json.loads(TRAIN_GATE.read_text(encoding='utf-8'))
    expected={str(TRAIN_STATE):TRAIN_STATE_SHA,str(TRAIN_RUNS):TRAIN_RUNS_SHA,str(TRAIN_METRICS):TRAIN_METRICS_SHA}
    if gate.get('status')!='PASS_PARENT_COMPLETED_PHASE_GATE' or gate.get('split')!='TRAIN' or gate.get('episodes')!=EXPECTED_TRAIN or gate.get('metric_rows')!=EXPECTED_TRAIN*16 or not gate.get('sidecars_all_hash_verified') or not gate.get('recorded_source_hash_stat_unchanged') or gate.get('MAT_read') is not False or gate.get('inputs_sha256')!=expected:
        raise RuntimeError('pinned completed TRAIN parent gate contents mismatch')
    for path,digest in ((TRAIN_STATE,TRAIN_STATE_SHA),(TRAIN_RUNS,TRAIN_RUNS_SHA),(TRAIN_METRICS,TRAIN_METRICS_SHA)):
        if core.sha(path)!=digest: raise RuntimeError(f'pinned completed TRAIN artifact SHA mismatch: {path}')
    train=json.loads(TRAIN_STATE.read_text(encoding='utf-8'))
    if train.get('status')!='PASS_TRAIN_1536' or train.get('worker_script_sha256')!=TRAIN_WORKER_SHA or train.get('core_script_sha256')!=TRAIN_CORE_SHA or train.get('split')!='TRAIN' or len(train.get('completed_run_ids',[]))!=EXPECTED_TRAIN or train.get('sidecar_count')!=EXPECTED_TRAIN or train.get('sidecar_bytes_written')!=769172595 or train.get('model',{}).get('model_array_identity')!=MODEL_ARRAY_ID:
        raise RuntimeError('pinned TRAIN state does not match the reviewed frozen release')
    runs=read_csv(TRAIN_RUNS); metrics=read_csv(TRAIN_METRICS)
    if len(runs)!=EXPECTED_TRAIN or len({r['run_id'] for r in runs})!=EXPECTED_TRAIN or any(r.get('status')!='PASS' or r.get('worker_script_sha256')!=TRAIN_WORKER_SHA or r.get('core_script_sha256')!=TRAIN_CORE_SHA for r in runs):
        raise RuntimeError('pinned TRAIN run table does not match the completed gate')
    if len(metrics)!=EXPECTED_TRAIN*16: raise RuntimeError('pinned TRAIN metric row count mismatch')
    if core.sha(SCHEMA_AUDIT_CSV)!=SCHEMA_AUDIT_CSV_SHA: raise RuntimeError('pinned VAL96 run_start schema audit CSV SHA mismatch')
    schema=json.loads(SCHEMA_AUDIT_STATE.read_text(encoding='utf-8'))
    if core.sha(SCHEMA_AUDIT_STATE)!='dee6e30248e55653cda3fde2d0f3019f1fc56f8c7be4a5e62ff410747f4e07cd' or schema.get('status')!='PASS_SCHEMA_AUDIT' or schema.get('samples')!=EXPECTED_VAL or schema.get('raw_files_read')!=0:
        raise RuntimeError('pinned VAL96 run_start schema audit state mismatch')
    return {'parent_gate_sha256':TRAIN_GATE_SHA,'phase_state_sha256':TRAIN_STATE_SHA,'runs_csv_sha256':TRAIN_RUNS_SHA,
        'metrics_csv_sha256':TRAIN_METRICS_SHA,'model_array_identity':MODEL_ARRAY_ID,
        'schema_audit_csv_sha256':SCHEMA_AUDIT_CSV_SHA,'schema_audit_state_sha256':core.sha(SCHEMA_AUDIT_STATE)}
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
    if split!='VAL': raise ValueError('this isolated peer worker is restricted to VAL only')
    for p,h in core.EXPECTED.items():
        if core.sha(p)!=h: raise RuntimeError(f'frozen index SHA mismatch: {p}')
    availability_sha=core.sha(core.AVAILABILITY)
    train_index=read_csv(core.TRAIN_INDEX); raw_index=read_csv(core.RAW_INDEX)
    selected=[r for r in train_index if r['split'].upper()==split]
    raw_selected=[r for r in raw_index if r['split'].upper()==split]
    expected_n=EXPECTED_VAL
    if len(selected)!=expected_n or len(raw_selected)!=expected_n: raise RuntimeError(f'{split} index count mismatch')
    rb={r['run_id']:r for r in raw_selected}
    if len(rb)!=expected_n: raise RuntimeError(f'{split} raw index has duplicate run_id')
    availability={}
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
        for key in ('raw_path','run_start_path','event_h5_path','cache_path'):
            if not Path(row[key]).is_file(): raise RuntimeError(f'missing {split} input {key}: {row[key]}')
        out.append(row)
    out.sort(key=lambda x:x['run_id'])
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

def main():
    ap=argparse.ArgumentParser(description='VAL-only fixed W0 inference and offline target reconstruction; no training, Plant calls, or resume.')
    ap.add_argument('--split',choices=('VAL',),default='VAL')
    ap.add_argument('--execute-after-audit',action='store_true',help='execute the fixed-model VAL96 pass after source review; default is plan-only')
    args=ap.parse_args()
    split='VAL'
    command='python -B reports/train_pcf_contract_reconstruction_val_v2_20261022/reconstruct_val_worker.py --execute-after-audit'
    train_pin=check_train_gate()
    samples,index_ids=split_rows(split)
    schema_audit={'csv_path':str(SCHEMA_AUDIT_CSV.resolve()),'csv_sha256':SCHEMA_AUDIT_CSV_SHA,
        'state_path':str(SCHEMA_AUDIT_STATE.resolve()),'state_sha256':SCHEMA_AUDIT_STATE_SHA}
    worker_sha=core.sha(Path(__file__)); core_sha=core.sha(Path(core.__file__))
    state_path,runs_path,metrics_path=state_paths(split,worker_sha)
    sidecar_raw,sidecar_conservative,sidecar_layout=estimate_storage(samples)
    if sidecar_conservative>=TWO_GIB: raise RuntimeError(f'VAL sidecar estimate alone exceeds 2 GiB: {sidecar_conservative} bytes')
    existing_dirs=(TRAIN_OUTPUT/'fixed_model_sidecars',TRAIN_OUTPUT/'val_v2'/'fixed_model_sidecars',SIDECAR_DIR)
    existing_sidecars=[p for folder in existing_dirs if folder.exists() for p in folder.glob('*.npz')]
    existing_bytes=sum(p.stat().st_size for p in existing_sidecars)
    if existing_bytes+sidecar_conservative>=TWO_GIB:
        raise RuntimeError(f'combined existing derived sidecars and conservative VAL bound exceed 2 GiB: {existing_bytes}+{sidecar_conservative}')
    plan={'split':'VAL','samples':len(samples),'command':command,'worker_script':str(Path(__file__).resolve()),'worker_script_sha256':worker_sha,'core_script':str(Path(core.__file__).resolve()),'core_script_sha256':core_sha,
        'source_indices':index_ids,'pinned_train_gate':train_pin,'val_runstart_schema_audit':schema_audit,
        'fixed_model_source_expected_sha256':MODEL_SOURCE_SHA,'fixed_model_id':MODEL_ID,'fixed_model_array_identity':MODEL_ARRAY_ID,
        'sidecar_array_payload_uncompressed_bytes':sidecar_raw,'sidecar_conservative_upper_bound_bytes':sidecar_conservative,'sidecar_layout':sidecar_layout,
        'existing_sidecar_bytes_across_report_dirs':existing_bytes,'existing_sidecar_file_count_across_report_dirs':len(existing_sidecars),
        'combined_derived_data_upper_bound_bytes':existing_bytes+sidecar_conservative,'sidecar_budget_bytes':TWO_GIB,
        'execution_authorized_by_this_flag':bool(args.execute_after_audit),'optimizer_steps':0,'plant_calls':0,'gpu_jobs':0,'test_accessed':False,'dev_labels_used':False,'resume_supported':False}
    if not args.execute_after_audit:
        print(json.dumps(plan,indent=2,ensure_ascii=False)); return
    for output in (state_path,runs_path,metrics_path):
        if output.exists(): raise RuntimeError(f'VAL output already exists; refusing overwrite or implicit resume: {output}')
    runtime_before=core.signature(core.RUNTIME_SOURCE)
    if runtime_before['sha256']!=core.RUNTIME_SOURCE_SHA: raise RuntimeError('frozen runtime source SHA mismatch')
    model,model_info=load_model(); start=time.perf_counter(); started=now()
    done=[]; done_metrics=[]; sample_wall=[]
    state={'phase':'VAL_FIXED_MODEL_INFERENCE_AND_OFFLINE_TARGET_RECONSTRUCTION','status':'RUNNING','started_local':started,'command':command,
        'worker_script':str(Path(__file__).resolve()),'worker_script_sha256':worker_sha,'core_script':str(Path(core.__file__).resolve()),'core_script_sha256':core_sha,
        'source_indices':index_ids,'pinned_train_gate':train_pin,'val_runstart_schema_audit':schema_audit,
        'runtime_source_path':str(core.RUNTIME_SOURCE.resolve()),'runtime_source_sha256_before':runtime_before['sha256'],'model':model_info,'split':'VAL','expected_samples':len(samples),'completed_run_ids':[],'failures':[],
        'optimizer_steps':0,'plant_calls':0,'gpu_jobs':0,'test_accessed':False,'dev_labels_used':False,'resume_supported':False,
        'sidecar_array_payload_uncompressed_bytes':sidecar_raw,'sidecar_conservative_upper_bound_bytes':sidecar_conservative,'sidecar_layout':sidecar_layout,
        'existing_sidecar_bytes_across_report_dirs':existing_bytes,'combined_derived_data_upper_bound_bytes':existing_bytes+sidecar_conservative,
        'sidecar_budget_bytes':TWO_GIB,'full_96':'RUNNING'}
    write_json(state_path,state); SIDECAR_DIR.mkdir(parents=True,exist_ok=True)
    for i,sample in enumerate(samples,1):
        try:
            sample_start=time.perf_counter()
            result,arrays=core.reconstruct(sample,return_arrays=True)
            pred_raw=infer_w0(arrays['x14'],model)
            beta_candidate=np.clip(arrays['event_time_s']/RUNTIME_BETA_RISE_S,0.,1.)
            beta_valid=beta_candidate[MODEL_VALID_START:,None]
            pred_applied=beta_valid*np.clip(pred_raw,-3.,3.)
            if not np.isfinite(pred_applied).all(): raise RuntimeError('candidate-clock W0 output is nonfinite')
            fit=metric_rows(sample,arrays,pred_applied)
            payload=sidecar_payload(sample,arrays,pred_raw,pred_applied,beta_candidate)
            sidecar=SIDECAR_DIR/f'VAL_{sample["run_id"]}_{worker_sha[:12]}.npz'
            tmp=sidecar.with_suffix('.npz.tmp')
            if sidecar.exists() or tmp.exists(): raise RuntimeError(f'VAL sidecar already exists; refusing overwrite: {sidecar}')
            with tmp.open('xb') as f: np.savez_compressed(f,**payload)
            tmp.replace(sidecar)
            sidecar_sha=core.sha(sidecar); sidecar_bytes=sidecar.stat().st_size
            run_row={**result,'status':'PASS','split':'VAL','worker_script_sha256':worker_sha,'core_script_sha256':core_sha,'model_id':MODEL_ID,'model_source_sha256':model_info['file_sha256'],'model_array_identity':MODEL_ARRAY_ID,
                'candidate_beta_formula':'clip(event_time_s/1.8,0,1)','teacher_beta_source':'same-run raw log.position_event_beta, verified through H5/cache','teacher_candidate_beta_max_abs':float(np.max(np.abs(arrays['beta_teacher']-beta_candidate))),
                'valid_inference_events':len(pred_raw),'sidecar_path':str(sidecar.resolve()),'sidecar_sha256':sidecar_sha,'sidecar_bytes':sidecar_bytes,'completed_local':now()}
            for k in ('raw','run_start','event_h5','cache'):
                run_row[k+'_sha256_after']=result[k+'_sha256_after'];run_row[k+'_bytes']=result[k+'_bytes'];run_row[k+'_mtime_ns_after']=result[k+'_mtime_ns_after']
            done.append(run_row);done_metrics.extend(fit)
            write_csv(runs_path,done);write_csv(metrics_path,done_metrics)
            sample_wall.append(time.perf_counter()-sample_start)
            state['completed_run_ids'].append(sample['run_id']);state['progress']=f'{i}/{len(samples)}';state['last_completed_run_id']=sample['run_id'];state['sidecars_written']=len(done);state['sidecar_bytes_written']=sum(int(r['sidecar_bytes']) for r in done);state['updated_local']=now();write_json(state_path,state)
            print(f'[{i}/{len(samples)}] PASS {sample["run_id"]}',flush=True)
        except Exception as e:
            error=f'{type(e).__name__}: {e}'
            core.fail_record(command,'VAL_fixed_model_full_worker',error,'current sample may have a partial temporary sidecar; source data remain read-only; completed peer outputs are preserved; this worker has no resume path','inspect the exact failure and use a new reviewed worker version; do not overwrite or resume this run')
            state.update(status='FAILED',failed_run_id=sample['run_id'],error=error,traceback=traceback.format_exc(),updated_local=now(),wall_seconds=time.perf_counter()-start);write_json(state_path,state);raise
    try:
        model_after=core.signature(MODEL_SOURCE);runtime_after=core.signature(core.RUNTIME_SOURCE)
        if (model_after['sha256'],model_after['bytes'],model_after['mtime_ns'])!=(model_info['file_sha256'],model_info['bytes'],model_info['mtime_ns']): raise RuntimeError('fixed model source SHA/stat changed during VAL')
        if (runtime_after['sha256'],runtime_after['bytes'],runtime_after['mtime_ns'])!=(runtime_before['sha256'],runtime_before['bytes'],runtime_before['mtime_ns']): raise RuntimeError('frozen runtime source SHA/stat changed during VAL')
        for p,h in core.EXPECTED.items():
            if core.sha(p)!=h: raise RuntimeError(f'frozen index SHA changed during VAL: {p}')
        if core.sha(core.AVAILABILITY)!=index_ids['availability_sha256']: raise RuntimeError('availability index SHA changed during VAL')
    except Exception as e:
        error=f'{type(e).__name__}: {e}';core.fail_record(command,'VAL_final_input_identity',error,'VAL outputs remain checkpointed; source data are read-only','inspect the exact source identity mismatch; do not resume or overwrite')
        state.update(status='FAILED',error=error,traceback=traceback.format_exc(),updated_local=now(),wall_seconds=time.perf_counter()-start);write_json(state_path,state);raise
    state['runtime_source_sha256_after']=runtime_after['sha256'];state['model_source_sha256_after']=model_after['sha256'];state['all_fixed_sources_sha_stat_unchanged']=True
    state.update(status='PASS_VAL_96',completed_local=now(),wall_seconds=time.perf_counter()-start,runs_csv=str(runs_path.resolve()),metrics_csv=str(metrics_path.resolve()),all_samples_passed=(len(done)==len(samples)),sidecar_count=len(done),sidecar_bytes_written=sum(int(r['sidecar_bytes']) for r in done),sidecar_hashes_present=True,sidecar_budget_stayed_within_2GiB=(existing_bytes+sum(int(r['sidecar_bytes']) for r in done)<TWO_GIB),sample_wall_seconds_mean=float(np.mean(sample_wall)) if sample_wall else None)
    write_json(state_path,state)
    print(json.dumps({'status':'PASS_VAL_96','samples':len(done),'wall_seconds':state['wall_seconds'],'sidecar_bytes_written':state['sidecar_bytes_written'],'phase_state':str(state_path.resolve())},ensure_ascii=False))

if __name__=='__main__': main()
