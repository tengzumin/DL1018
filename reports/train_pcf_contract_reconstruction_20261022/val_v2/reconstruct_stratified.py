from __future__ import annotations
import argparse, csv, hashlib, json, re, time, traceback
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import h5py
import numpy as np
from scipy.io import loadmat

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2].resolve()
ARCHIVE=(ROOT.parent/'REFERENCE_FIX_FULL72_20261021_022342_313').resolve()
BASE=ARCHIVE/'corrected_reference_training_v1'
TRAIN_INDEX=BASE/'corrected_pair_training/manifests/PAIR_TRAINING_INPUT_INDEX.csv'
RAW_INDEX=BASE/'g3_collection/reports/G3_D4_CACHE_INDEX_1632.csv'
AVAILABILITY=ROOT/'reports/hf_w15_reinvestigation_20261022/training_raw_availability.csv'
MANIFEST=OUT/'stratified_sample_manifest.csv'
RESULTS=OUT/'stratified_reconstruction_checks.csv'
STATE=OUT/'PHASE_STATE.json'
FAILURES=OUT/'FAILURES.csv'
RUNTIME_SOURCE=BASE/'sources/local_runtime/run_dl1018_closed_loop.m'
RUNTIME_SOURCE_SHA='01d83dec95aea5d30feef3afd0628a2ce0911f70465f0773a4f568a01b08450b'
EXPECTED={
 TRAIN_INDEX:'257089f1dc455b7bc97bf1c772be31d1d8ae83079e7ec41f591d96e31fed39ca',
 RAW_INDEX:'3c8291c12628acfb9d950fb67cb84b56fe09cdaeaeac38706e8903291873e84e'}
EXPECTED_MANIFEST='4019aac3a23f1aef4a70f5d37b364d1ca09bfd1bcfe9ce39e486b3772af18b49'
M=np.array([1.,1.,0.])[:,None]
CHUNK=8<<20


def now(): return datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds')
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(CHUNK),b''): h.update(b)
 return h.hexdigest()
def scoped(p):
 p=Path(p).resolve()
 if not (p.is_relative_to(ROOT) or p.is_relative_to(ARCHIVE)): raise RuntimeError(f'outside ROOT/ARCHIVE input scope: {p}')
 return p
def signature(p):
 p=scoped(p); s0=p.stat(); t=time.perf_counter(); h=sha(p); sec=time.perf_counter()-t; s1=p.stat()
 if (s0.st_size,s0.st_mtime_ns)!=(s1.st_size,s1.st_mtime_ns): raise RuntimeError(f'file changed while hashing: {p}')
 return {'sha256':h,'bytes':s1.st_size,'mtime_ns':s1.st_mtime_ns,'hash_seconds':sec}
def read_csv(p):
 with scoped(p).open('r',newline='',encoding='utf-8-sig') as f: return list(csv.DictReader(f))
def wind_band(cell):
 if cell<=8:return 'W00_W08'
 if cell<=14:return 'W09_W14'
 if cell==15:return 'W15'
 raise ValueError(f'wind_cell outside 0..15: {cell}')
def check_manifest():
 for p,h in EXPECTED.items():
  if sha(p)!=h: raise RuntimeError(f'frozen index SHA mismatch: {p}')
 if sha(MANIFEST)!=EXPECTED_MANIFEST: raise RuntimeError('frozen sample manifest SHA mismatch')
 train=[r for r in read_csv(TRAIN_INDEX) if r['split'].lower()=='train']
 raw=[r for r in read_csv(RAW_INDEX) if r['split'].upper()=='TRAIN']
 avail=read_csv(AVAILABILITY)
 if not(len(train)==len(raw)==len(avail)==1536): raise RuntimeError('TRAIN source row count is not 1536')
 rb={r['run_id']:r for r in raw}; ab={r['run_id']:r for r in avail}
 if len(rb)!=1536 or len(ab)!=1536: raise RuntimeError('duplicate run_id in input indexes')
 groups={}
 for t in train:
  rid=t['run_id']; r=rb[rid]; a=ab[rid]; cell=int(t['wind_cell'])
  m=re.search(r'_W(\d{2})(?:_|$)',r['runtime_scene_id'])
  if not m or int(m.group(1))!=cell or int(a['wind_cell'])!=cell: raise RuntimeError(f'wind-cell join mismatch: {rid}')
  if (t['task'],t['role'])!=(r['task'],r['role']) or (t['task'],t['role'])!=(a['task'],a['role']): raise RuntimeError(f'task/role join mismatch: {rid}')
  for kind in ('raw','event_h5','cache'):
   if t[f'{kind}_sha256']!=r[f'{kind}_sha256']: raise RuntimeError(f'{kind} SHA join mismatch: {rid}')
  for kind in ('raw','run_start','event_h5'):
   if scoped(r[f'{kind}_path'])!=scoped(a[f'{kind}_path']) or not Path(r[f'{kind}_path']).is_file(): raise RuntimeError(f'{kind} availability mismatch: {rid}')
  if not Path(t['cache_path']).is_file(): raise RuntimeError(f'missing cache: {rid}')
  row=dict(t); row.update(raw_path=r['raw_path'],raw_path_sha256=r['raw_sha256'],run_start_path=r['run_start_path'],run_start_path_sha256=r['run_start_sha256'],event_h5_path=r['event_h5_path'],event_h5_path_sha256=r['event_h5_sha256'],cache_path=t['cache_path'])
  groups.setdefault((t['task'],t['role'],wind_band(cell)),[]).append(row)
 selected=[]
 for key,rs in sorted(groups.items()): selected.append(sorted(rs,key=lambda x:x['run_id'])[0])
 frozen=read_csv(MANIFEST)
 if len(selected)!=18 or len(frozen)!=18 or [x['run_id'] for x in selected]!=[x['run_id'] for x in frozen]: raise RuntimeError('manifest differs from first-run-id 18-stratum selection')
 by_id={x['run_id']:x for x in selected}
 enriched=[]
 for row in frozen:
  row=dict(row);row['runtime_scene_id']=by_id[row['run_id']]['runtime_scene_id'];enriched.append(row)
 return enriched,sha(AVAILABILITY)

def scalar_bool(x): return bool(np.asarray(x).reshape(-1)[0])
def h5_option_flag(f,name,opts_path):
 base=f.get(opts_path)
 if base is None or name not in base:return None
 obj=base[name]
 if isinstance(obj,h5py.Group):
  if 'enabled' not in obj:return None
  return scalar_bool(obj['enabled'][()])
 val=obj[()]
 if isinstance(val,np.ndarray) and val.dtype.kind=='O' and val.size==1:
  ref=val.reshape(-1)[0]
  if not ref:return None
  obj=f[ref]
  if isinstance(obj,h5py.Group):
   if 'enabled' not in obj:return None
   return scalar_bool(obj['enabled'][()])
  val=obj[()]
 return scalar_bool(val)
def cfg_and_opts(path):
 with path.open('rb') as f: prefix=f.read(128)
 if prefix[124:128]==b'\x00\x02IM':
  with h5py.File(path,'r') as f:
   runstart_cfg=f.get('runStart/cfg')
   if isinstance(runstart_cfg,h5py.Group):
    cfg_path='runStart/cfg'; opts_path='runStart/opts'; fmt='MATLAB_7.3_RUNSTART_CFG_OPTS'
   else:
    root_cfg=f.get('cfg')
    if not isinstance(root_cfg,h5py.Group): raise RuntimeError(f'{path}: HDF5 run_start has neither /runStart/cfg nor top-level /cfg group')
    cfg_path='cfg'; opts_path='opts'; fmt='MATLAB_7.3_ROOT_CFG_OPTS'
   cfg=f[cfg_path]; plant=cfg['plant']; pos=cfg['control/bs/position']
   flags={n:h5_option_flag(f,n,opts_path) for n in ('physical_impulse_force_I','rbf_disturbance_diagnostic','state_perturbation')}
   mass=np.asarray(plant['mass'],dtype=np.float64); gravity=np.asarray(plant['g'],dtype=np.float64)
   k1=np.asarray(pos['k1'],dtype=np.float64).reshape(-1); k2=np.asarray(pos['k2'],dtype=np.float64).reshape(-1)
   if mass.size!=1 or gravity.size!=1 or k1.size!=3 or k2.size!=3 or not all(np.isfinite(x).all() for x in (mass,gravity,k1,k2)) or mass.reshape(-1)[0]<=0 or gravity.reshape(-1)[0]<=0:
    raise RuntimeError(f'{path}: invalid shape/value in same-run cfg fields mass/g/k1/k2')
   vals={'mass_kg':float(mass.reshape(-1)[0]),'gravity_mps2':float(gravity.reshape(-1)[0]),'k1':k1,'k2':k2,
         'cfg_source':'same-run /'+cfg_path,'opts_source':('same-run /'+opts_path) if isinstance(f.get(opts_path),h5py.Group) else 'same-run runtime defaults for missing /'+opts_path}
 else:
  fmt='MATLAB_5'; rs=loadmat(path,variable_names=['runStart'],simplify_cells=True)['runStart']; cfg=rs['cfg']; opts=rs.get('opts',{})
  flags={}
  for n in ('physical_impulse_force_I','rbf_disturbance_diagnostic','state_perturbation'):
   opt=opts.get(n) if isinstance(opts,dict) else None
   flags[n]=None if not isinstance(opt,dict) or 'enabled' not in opt else scalar_bool(opt['enabled'])
  plant=cfg['plant']; pos=cfg['control']['bs']['position']
  mass=float(plant['mass']); gravity=float(plant['g']); k1=np.asarray(pos['k1'],dtype=np.float64).reshape(3); k2=np.asarray(pos['k2'],dtype=np.float64).reshape(3)
  if not(np.isfinite(mass) and np.isfinite(gravity) and np.isfinite(k1).all() and np.isfinite(k2).all() and mass>0 and gravity>0):
   raise RuntimeError(f'{path}: invalid value in same-run cfg fields mass/g/k1/k2')
  vals={'mass_kg':mass,'gravity_mps2':gravity,'k1':k1,'k2':k2,'cfg_source':'same-run runStart.cfg','opts_source':'same-run runStart.opts' if isinstance(opts,dict) else 'same-run runtime defaults for missing runStart.opts'}
 for n,v in flags.items():
  vals[n+'_opts_enabled']=v
  vals[n+'_default_source']='archive runtime run_dl1018_closed_loop.m SHA '+RUNTIME_SOURCE_SHA+'; field_or(...,struct), enabled field_or(...,false), lines 300-303,336' if v is None else 'runStart.opts.'+n+'.enabled'
 return vals,fmt

def z_axis(e):
 r,p,y=e
 return np.vstack((np.cos(y)*np.sin(p)*np.cos(r)+np.sin(y)*np.sin(r),np.sin(y)*np.sin(p)*np.cos(r)-np.cos(y)*np.sin(r),np.cos(p)*np.cos(r)))
def maxabs(x):return float(np.max(np.abs(x))) if np.size(x) else 0.
def rms(x):return float(np.sqrt(np.mean(np.asarray(x,dtype=np.float64)**2))) if np.size(x) else 0.
def event_major(ds,n,w):
 a=np.asarray(ds,dtype=np.float64)
 if a.shape==(n,w):return a
 if a.shape==(w,n):return a.T
 raise RuntimeError(f'unexpected H5 shape {ds.name}: {a.shape}')
def check_extra_inputs(log,cfg):
 report={}
 def flag(name):
  if name not in log:return None
  return scalar_bool(log[name][()])
 for name in ('physical_impulse_enabled','state_perturbation_enabled','diagnostic_oracle_enabled','rbf_disturbance_diagnostic_enabled'):
  report['log_'+name]=flag(name)
 for name in ('physical_impulse_force_I_N','diagnostic_external_force_I'):
  if name in log:
   a=np.asarray(log[name],dtype=np.float64)
   if not np.isfinite(a).all(): raise RuntimeError(f'nonfinite extra-input log: {name}')
   mx=maxabs(a); report['log_'+name+'_max_abs_N']=mx
   if mx>0.: raise RuntimeError(f'nonzero extra force logged in {name}: max_abs={mx}')
  else: report['log_'+name+'_max_abs_N']='ABSENT'
 enabled_opts=[name for name in ('physical_impulse_force_I','rbf_disturbance_diagnostic','state_perturbation') if cfg[name+'_opts_enabled'] is True]
 if enabled_opts: raise RuntimeError(f'extra-input option enabled; sample excluded: {enabled_opts}')
 enabled_logs=[name for name in ('physical_impulse_enabled','state_perturbation_enabled','diagnostic_oracle_enabled','rbf_disturbance_diagnostic_enabled') if report['log_'+name] is True]
 if enabled_logs: raise RuntimeError(f'extra-input log flag enabled; sample excluded: {enabled_logs}')
 return report

def reconstruct(sample,return_arrays=False):
 paths={k:scoped(sample[k+'_path']) for k in ('raw','run_start','event_h5','cache')}
 expected={'raw':sample['raw_path_sha256'],'run_start':sample['run_start_path_sha256'],'event_h5':sample['event_h5_path_sha256'],'cache':sample['cache_sha256']}
 t0=time.perf_counter(); sig0={k:signature(p) for k,p in paths.items()}; hash_before=time.perf_counter()-t0
 for k in paths:
  if sig0[k]['sha256']!=expected[k]:raise RuntimeError(f'{sample["run_id"]}: {k} frozen SHA mismatch')
 tnum=time.perf_counter(); cfg,matfmt=cfg_and_opts(paths['run_start'])
 with h5py.File(paths['raw'],'r') as f:
  log=f['log']; extra=check_extra_inputs(log,cfg)
  idx=np.flatnonzero(np.asarray(log['position_event_flag']).reshape(-1)>0); n=len(idx)
  if n!=1999:raise RuntimeError(f'{sample["run_id"]}: event count {n}, expected 1999')
  get=lambda name:np.asarray(log[name],dtype=np.float64)
  state=get('state')[:,idx]; rp=get('reference/position')[:,idx]; rv=get('reference/velocity')[:,idx]; ra=get('reference/acceleration')[:,idx]
  ep=rp-state[:3]; ev=rv-state[3:6]; surface=ev+cfg['k1'][:,None]*ep
  a0=ra+cfg['k1'][:,None]*ev+ep+cfg['k2'][:,None]*surface
  u=get('position_compensation_applied_acceleration_mps2')[:,idx]
  nominal=get('position_nominal_acceleration_mps2')[:,idx]
  a_req=get('position_commanded_force_N')[:,idx]/cfg['mass_kg']
  req_gen=get('requested_generalized')[:,idx]; real_gen=get('realized_generalized')[:,idx]
  filt=get('filtered_attitude_reference')[:,idx]; wind=get('wind_force_I')[:,idx]
  trans=get('transition_time').reshape(-1)[idx]
  if 'position_event_beta' not in log: raise RuntimeError(f'{sample["run_id"]}: missing raw position_event_beta')
  raw_beta=get('position_event_beta')[:,idx]
  arms=np.asarray(f['scene/arms/command'],dtype=np.float64)[:,idx]
  a_actual=real_gen[0][None,:]*z_axis(state[6:9])/cfg['mass_kg']+wind/cfg['mass_kg']; a_actual[2]-=cfg['gravity_mps2']
  y=a_actual-a_req
  a_f=req_gen[0][None,:]*z_axis(filt)/cfg['mass_kg']; a_f[2]-=cfg['gravity_mps2']
  rf=a_req-a_f; mixed=y+M*rf; rhs=a_actual-(1-M)*a_req-M*a_f
  x14=np.vstack((ep,surface,state[6:9],np.linalg.norm(a0+np.array([0.,0.,cfg['gravity_mps2']])[:,None],axis=0),arms))
  pcf_enabled=scalar_bool(log['stage1_position_pcf_coordination_enabled'][()])
  pcf_req=get('stage1_position_pcf_a_req_mps2')[:,idx]; pcf_af=get('stage1_position_pcf_a_f_mps2')[:,idx]; pcf_rf=get('stage1_position_pcf_r_f_mps2')[:,idx]
  pcf_finite=(int(np.isfinite(pcf_req).sum()),int(np.isfinite(pcf_af).sum()),int(np.isfinite(pcf_rf).sum()))
  pcf_errors={}
  if pcf_enabled:
   if min(pcf_finite)<3*n:raise RuntimeError('PCF enabled but logged PCF arrays are nonfinite')
   pcf_errors={'logged_pcf_a_req_max_abs_mps2':maxabs(pcf_req-a_req),'logged_pcf_a_f_max_abs_mps2':maxabs(pcf_af-a_f),'logged_pcf_r_f_max_abs_mps2':maxabs(pcf_rf-rf)}
   if max(pcf_errors.values())>1e-9:raise RuntimeError(f'PCF enabled log does not match reconstructed helper inputs: {pcf_errors}')
 with h5py.File(paths['event_h5'],'r') as f:
  hi=np.asarray(f['event_index'],dtype=np.int64).reshape(-1); pi=np.asarray(f['plant_index'],dtype=np.int64).reshape(-1); ht=np.asarray(f['event_time_s'],dtype=np.float64).reshape(-1)
  hy=event_major(f['target_raw'],n,3); hc=event_major(f['target_clip'],n,3); hx=event_major(f['x14'],n,14)
  hcode=np.asarray(f['phase_code']).reshape(-1); hready=np.asarray(f['ready']).reshape(-1)
  hbeta=np.asarray(f['beta'],dtype=np.float64).reshape(-1)
 if not np.array_equal(hi,np.arange(1,n+1)):raise RuntimeError(f'{sample["run_id"]}: H5 event_index is not contiguous one-based')
 if not np.array_equal(pi,idx+1):raise RuntimeError(f'{sample["run_id"]}: H5 plant_index/raw-event mapping mismatch')
 with np.load(paths['cache'],allow_pickle=False) as z:
  meta={k:str(np.asarray(z[k]).item()) for k in ('run_id','scene_id','split','role','task')}
  cy=np.asarray(z['raw']); cy_clip=np.asarray(z['y']); cx=np.asarray(z['x14']); ct=np.asarray(z['event_time_s']); cpi=np.asarray(z['plant_index']); cphase=np.asarray(z['phase']); cread=np.asarray(z['ready']); cbeta=np.asarray(z['beta'])
  expected_split=str(sample.get('split','TRAIN')).upper()
  if expected_split not in ('TRAIN','VAL'): raise RuntimeError(f'cache split must be TRAIN or VAL, got {expected_split}')
 if (meta['run_id']!=sample['run_id'] or meta['split'].upper()!=expected_split or meta['role']!=sample['role'] or meta['task']!=sample['task'] or meta['scene_id']!=sample['runtime_scene_id']):raise RuntimeError(f'cache identity mismatch: {meta}; expected run_id/task/role/runtime_scene_id={sample["run_id"]}/{sample["task"]}/{sample["role"]}/{sample["runtime_scene_id"]}')
 finite_arrays={'cfg_k1':cfg['k1'],'cfg_k2':cfg['k2'],'state_event':state,'reference_position':rp,'reference_velocity':rv,'reference_acceleration':ra,'compensation_applied_acceleration':u,'nominal_acceleration':nominal,'a_req':a_req,'requested_generalized':req_gen,'realized_generalized':real_gen,'filtered_euler':filt,'wind_force':wind,'transition_time':trans,'raw_log_beta':raw_beta,'arms':arms,'a0':a0,'a_actual':a_actual,'Y':y,'a_f':a_f,'r_f':rf,'mixed_target':mixed,'X14':x14,'H5_event_time':ht,'H5_target_raw':hy,'H5_target_clip':hc,'H5_X14':hx,'H5_beta':hbeta,'cache_raw':cy,'cache_clip':cy_clip,'cache_X14':cx,'cache_event_time':ct,'cache_beta':cbeta}
 for name,array in finite_arrays.items():
  if not np.isfinite(array).all():raise RuntimeError(f'{sample["run_id"]}: nonfinite value in {name}')
 errs={'a0_replay_max_abs_mps2':maxabs(nominal-a0),'a_req_vs_a0_minus_u_max_abs_mps2':maxabs(a_req-(a0-u)),'physical_Y_vs_event_H5_max_abs_mps2':maxabs(y-hy.T),'X14_vs_event_H5_max_abs':maxabs(x14-hx.T),'mixed_identity_max_abs_mps2':maxabs(mixed-rhs),'event_time_vs_transition_max_abs_s':maxabs(trans-ht),'raw_log_teacher_beta_vs_event_H5_max_abs':maxabs(raw_beta-hbeta),'Y_clip_vs_event_H5_max_abs_mps2':maxabs(np.clip(y.T,-3,3)-hc)}
 if max(errs.values())>1e-9:raise RuntimeError(f'{sample["run_id"]}: closure failure {errs}')
 if not(np.array_equal(cpi.astype(np.int64),idx) and np.array_equal(ct,ht.astype(np.float32)) and np.array_equal(cy,hy.astype(np.float32)) and np.array_equal(cy_clip,hc.astype(np.float32)) and np.array_equal(cx,hx.astype(np.float32)) and np.array_equal(cphase,hcode.astype(cphase.dtype)) and np.array_equal(cread.astype(bool),hready.astype(bool)) and np.array_equal(cbeta,hbeta.astype(np.float32))):raise RuntimeError(f'{sample["run_id"]}: H5-to-cache mapping/float32 identity failed')
 cache_y_alias_match=bool(np.array_equal(cy_clip,hc.astype(np.float32)))
 numeric_seconds=time.perf_counter()-tnum
 t1=time.perf_counter(); sig1={k:signature(p) for k,p in paths.items()}; hash_after=time.perf_counter()-t1
 for k in paths:
  if sig0[k]['sha256']!=sig1[k]['sha256'] or sig0[k]['bytes']!=sig1[k]['bytes'] or sig0[k]['mtime_ns']!=sig1[k]['mtime_ns']:raise RuntimeError(f'{sample["run_id"]}: {k} source SHA/stat changed during read')
 result={'run_id':sample['run_id'],'task':sample['task'],'role':sample['role'],'wind_cell':sample['wind_cell'],'wind_band':sample['wind_band'],'status':'PASS','events':n,'raw_event_index_first_0based':int(idx[0]),'raw_event_index_last_0based':int(idx[-1]),'h5_event_index_first':int(hi[0]),'h5_event_index_last':int(hi[-1]),'plant_index_first_1based':int(pi[0]),'plant_index_last_1based':int(pi[-1]),'event_time_first_s':float(ht[0]),'event_time_last_s':float(ht[-1]),'run_start_format':matfmt,'cfg_source':cfg['cfg_source'],'opts_source':cfg['opts_source'],'mass_kg':cfg['mass_kg'],'gravity_mps2':cfg['gravity_mps2'],'position_k1':';'.join(map(str,cfg['k1'])),'position_k2':';'.join(map(str,cfg['k2'])),'pcf_coordination_enabled':pcf_enabled,'stage1_pcf_a_req_finite_values':pcf_finite[0],'stage1_pcf_a_f_finite_values':pcf_finite[1],'stage1_pcf_r_f_finite_values':pcf_finite[2],'rf_rms_all_axes_mps2':rms(rf),'rf_rms_x_mps2':rms(rf[0]),'rf_rms_y_mps2':rms(rf[1]),'rf_rms_z_mps2':rms(rf[2]),'Y_rms_all_axes_mps2':rms(y),'Y_plus_M_rf_rms_all_axes_mps2':rms(mixed),'cache_y_matches_H5_target_clip':cache_y_alias_match,'raw_to_H5_Y_float32_rounding_max_abs_mps2':maxabs(y.T.astype(np.float32).astype(np.float64)-hy),'H5_to_cache_Y_float32_exact':True,'H5_to_cache_X14_float32_exact':True,'H5_to_cache_time_float32_exact':True,'cache_identity_match':True,'hash_before_seconds':hash_before,'hash_after_seconds':hash_after,'numeric_read_compute_seconds':numeric_seconds,'sample_wall_seconds':hash_before+hash_after+numeric_seconds,'runtime_source_sha256':RUNTIME_SOURCE_SHA,'source_sha_stat_unchanged':True,'cache_scene_id':meta['scene_id'],'runtime_scene_id':sample['runtime_scene_id']}
 for k,v in cfg.items():
  if k.endswith('_opts_enabled'): result[k]=v if v is not None else 'MISSING_DEFAULT_FALSE'
  if k.endswith('_default_source') and cfg[k.removesuffix('_default_source')+'_opts_enabled'] is None: result[k]=v
 for k,v in extra.items():result[k]=v
 for k,v in errs.items():result[k]=v
 for k,v in pcf_errors.items():result[k]=v
 for kind in paths:
  result[kind+'_sha256_before']=sig0[kind]['sha256'];result[kind+'_sha256_after']=sig1[kind]['sha256'];result[kind+'_bytes']=sig0[kind]['bytes'];result[kind+'_mtime_ns_before']=sig0[kind]['mtime_ns'];result[kind+'_mtime_ns_after']=sig1[kind]['mtime_ns'];result[kind+'_hash_before_seconds']=sig0[kind]['hash_seconds'];result[kind+'_hash_after_seconds']=sig1[kind]['hash_seconds']
 if return_arrays:
  arrays={'x14':cx,'event_time_s':ht,'event_index':hi,'plant_index':pi,'raw_index':idx,'phase_code':hcode,'ready':hready,'beta_teacher':hbeta,'Y_raw':y.T,'Y_clip':hc,'r_f':rf.T,'mixed_raw':mixed.T,'mixed_clip':np.clip(mixed.T,-3.,3.),'a_req':a_req.T,'a_f':a_f.T,'a_actual':a_actual.T}
  return result,arrays
 return result

def write_csv(rows):
 if not rows:return
 with RESULTS.open('w',newline='',encoding='utf-8-sig') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0].keys()),extrasaction='ignore');w.writeheader();w.writerows(rows)
def fail_record(cmd,stage,error,impact,correction):
 fields=['timestamp_local','command','stage','error','impact','correction']; exists=FAILURES.exists()
 with FAILURES.open('a',newline='',encoding='utf-8-sig') as f:
  w=csv.DictWriter(f,fieldnames=fields)
  if not exists or FAILURES.stat().st_size==0:w.writeheader()
  w.writerow({'timestamp_local':now(),'command':cmd,'stage':stage,'error':error,'impact':impact,'correction':correction})
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--resume',action='store_true');ap.add_argument('--limit',type=int,default=None);args=ap.parse_args()
 command='python -B reports/train_pcf_contract_reconstruction_20261022/reconstruct_stratified.py'+(' --resume' if args.resume else '')+(' --limit '+str(args.limit) if args.limit is not None else '')
 start=time.perf_counter(); wall_start=now(); rows,availability_sha=check_manifest()
 runtime_sig=signature(RUNTIME_SOURCE)
 if runtime_sig['sha256']!=RUNTIME_SOURCE_SHA:raise RuntimeError('frozen runtime source SHA mismatch')
 script_sha=sha(Path(__file__)); manifest_sha=sha(MANIFEST); old={}
 if args.resume and RESULTS.is_file():
  with RESULTS.open(newline='',encoding='utf-8-sig') as f:old={r['run_id']:r for r in csv.DictReader(f)}
 if args.limit is not None and (args.limit<1 or args.limit>len(rows)):raise ValueError('--limit must be 1..18')
 if args.limit is not None: rows=rows[:args.limit]
 state={'phase':'18_STRATIFIED_NUMERIC_RECONSTRUCTION','status':'RUNNING','started_local':wall_start,'command':command,'script_path':str(Path(__file__).resolve()),'script_sha256':script_sha,'manifest_sha256':manifest_sha,'availability_sha256':availability_sha,'source_indices':{str(p):EXPECTED[p] for p in EXPECTED},'runtime_source_path':str(RUNTIME_SOURCE.resolve()),'runtime_source_sha256_before':runtime_sig['sha256'],'optimizer_steps':0,'plant_calls':0,'gpu_jobs':0,'test_accessed':False,'full_1536':'NOT_STARTED_PENDING_MAIN_MODEL_APPROVAL','completed_run_ids':[],'failures':[]}
 STATE.write_text(json.dumps(state,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
 done=[]
 for i,sample in enumerate(rows,1):
  try:
   prior=old.get(sample['run_id']) if args.resume else None
   paths={k:scoped(sample[k+'_path']) for k in ('raw','run_start','event_h5','cache')}
   if prior and prior.get('status')=='PASS' and prior.get('script_sha256')==script_sha and prior.get('manifest_sha256')==manifest_sha:
    cur={k:signature(p) for k,p in paths.items()}
    expected={'raw':sample['raw_path_sha256'],'run_start':sample['run_start_path_sha256'],'event_h5':sample['event_h5_path_sha256'],'cache':sample['cache_sha256']}
    if all(cur[k]['sha256']==expected[k] and cur[k]['sha256']==prior[k+'_sha256_after'] and cur[k]['bytes']==int(prior[k+'_bytes']) and cur[k]['mtime_ns']==int(prior[k+'_mtime_ns_after']) for k in paths):
     prior['resumed_without_numeric_reread']=True;done.append(prior);write_csv(done)
     state['completed_run_ids'].append(sample['run_id']);state['progress']=f'{i}/18';state['last_completed_run_id']=sample['run_id'];STATE.write_text(json.dumps(state,indent=2,ensure_ascii=False)+'\n',encoding='utf-8');continue
   row=reconstruct(sample);row['script_sha256']=script_sha;row['manifest_sha256']=manifest_sha;row['resumed_without_numeric_reread']=False
   done.append(row);write_csv(done);state['completed_run_ids'].append(sample['run_id']);state['progress']=f'{i}/18';state['last_completed_run_id']=sample['run_id'];state['updated_local']=now();STATE.write_text(json.dumps(state,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
   print(f'[{i}/18] PASS {sample["run_id"]}',flush=True)
  except Exception as e:
   error=f'{type(e).__name__}: {e}';fail_record(command,'stratified_numeric_reconstruction',error,'current sample read may be incomplete; sources remain read-only; previous completed rows checkpointed','inspect the exact failure and rerun with --resume after a focused correction in this directory')
   state.update(status='FAILED',failed_run_id=sample['run_id'],error=error,traceback=traceback.format_exc(),updated_local=now(),wall_seconds=time.perf_counter()-start);STATE.write_text(json.dumps(state,indent=2,ensure_ascii=False)+'\n',encoding='utf-8');raise
 runtime_after=signature(RUNTIME_SOURCE)
 if runtime_after['sha256']!=runtime_sig['sha256'] or runtime_after['bytes']!=runtime_sig['bytes'] or runtime_after['mtime_ns']!=runtime_sig['mtime_ns']:raise RuntimeError('runtime source changed during audit')
 state.update(status=('PASS_18_FROZEN_STRATA' if len(done)==18 else f'PASS_SUBSET_{len(done)}_OF_18'),completed_local=now(),wall_seconds=time.perf_counter()-start,runtime_source_sha256_after=runtime_after['sha256'],all_source_sha_stat_unchanged=True,raw_bytes_sum=sum(int(r['raw_bytes']) for r in done),numeric_read_compute_seconds_sum=sum(float(r['numeric_read_compute_seconds']) for r in done),hash_before_seconds_sum=sum(float(r['hash_before_seconds']) for r in done),hash_after_seconds_sum=sum(float(r['hash_after_seconds']) for r in done),full_worker_sidecar_capacity_method='reconstruct_full_worker.py estimate_storage: sum(actual sidecar_payload ndarray.nbytes) + 16 KiB per NPZ + 64 MiB report/state allowance',full_1536_worker='NOT_STARTED_PENDING_MAIN_MODEL_REVIEW')
 STATE.write_text(json.dumps(state,indent=2,ensure_ascii=False)+'\n',encoding='utf-8');print(json.dumps({'status':state['status'],'samples':len(done),'wall_seconds':state['wall_seconds']},ensure_ascii=False))
if __name__=='__main__':main()
