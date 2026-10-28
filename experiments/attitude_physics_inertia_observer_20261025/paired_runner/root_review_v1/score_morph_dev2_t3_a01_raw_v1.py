from __future__ import annotations
import csv, hashlib, json, math
from pathlib import Path
import h5py
import numpy as np
from scipy.spatial.transform import Rotation

ROOT=Path(__file__).resolve().parents[4]
BASE=ROOT/'experiments/attitude_physics_inertia_observer_20261025/paired_runner/morph_dev2_t3_continuation_v1/attempts/MORPH_DEV2_T3_CONT_20261025_A01'
SCENE='DL1018_DEV_T3_C10_W11'
N=20000
OUT=Path(__file__).resolve().parent/'t3_a01_independent_v1'
OUT.mkdir(exist_ok=False)

def sha(p:Path)->str:
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''): h.update(b)
    return h.hexdigest()
def arr(g,k): return np.asarray(g[k][()],dtype=np.float64)
def scalar(g,k): return float(arr(g,k).reshape(-1)[0])
def score(raw:Path,run_status:Path):
    with h5py.File(raw,'r') as f:
        log=f['log']
        time=arr(log,'time').reshape(-1)
        transition=arr(log,'transition_time').reshape(-1)
        state=arr(log,'state')
        ref=arr(log['reference'],'position')
        filt=arr(log,'filtered_attitude_reference')
        assert state.shape==(12,N+1) and ref.shape==(3,N+1) and filt.shape==(3,N)
        assert time.shape==(N+1,) and transition.shape==(N,)
        assert np.all(np.diff(time)>0) and np.all(np.diff(transition)>0)
        e=(state[:3,:]-ref).T
        en=np.linalg.norm(e,axis=1)
        early=time<2.2; late=time>=2.2
        assert int(early.sum())==2200 and int(late.sum())==17801
        q=float(np.sqrt(np.mean(np.sum(e*e,axis=1))))
        actual=Rotation.from_euler('xyz',state[6:9,:N].T).as_matrix()
        desired=Rotation.from_euler('xyz',filt.T).as_matrix()
        rel=np.einsum('nji,njk->nik',desired,actual)
        cos=np.clip((np.trace(rel,axis1=1,axis2=2)-1)*.5,-1.,1.)
        anti=np.stack([rel[:,2,1]-rel[:,1,2],rel[:,0,2]-rel[:,2,0],rel[:,1,0]-rel[:,0,1]],axis=1)
        sin=np.linalg.norm(anti,axis=1)*.5
        theta=np.arctan2(sin,cos)
        eearly=transition<2.2; elate=transition>=2.2
        assert int(eearly.sum())==2200 and int(elate.sum())==17800
        sat=arr(log,'motor_saturated'); clip=arr(log,'generalized_clipped'); tilt=arr(log,'tilt_limited').reshape(-1)
        score={
          'q_rmse_m':q,'q_axis_rmse_m':np.sqrt(np.mean(e*e,axis=0)).tolist(),'q_peak_m':float(en.max()),
          'q_early_rmse_m':float(np.sqrt(np.mean(np.sum(e[early]**2,axis=1)))),
          'q_early_axis_rmse_m':np.sqrt(np.mean(e[early]**2,axis=0)).tolist(),'q_early_peak_m':float(en[early].max()),
          'q_late_rmse_m':float(np.sqrt(np.mean(np.sum(e[late]**2,axis=1)))),
          'q_late_axis_rmse_m':np.sqrt(np.mean(e[late]**2,axis=0)).tolist(),'q_late_peak_m':float(en[late].max()),
          'so3_rmse_rad':float(np.sqrt(np.mean(theta**2))),'so3_peak_rad':float(theta.max()),
          'so3_early_rmse_rad':float(np.sqrt(np.mean(theta[eearly]**2))),'so3_early_peak_rad':float(theta[eearly].max()),
          'so3_late_rmse_rad':float(np.sqrt(np.mean(theta[elate]**2))),'so3_late_peak_rad':float(theta[elate].max()),
          'motor_saturation_count':int(np.any(sat!=0,axis=0).sum()),
          'generalized_clip_count':int(np.any(clip!=0,axis=0).sum()),
          'tilt_limited_count':int(np.count_nonzero(tilt)),
          'state_points':N+1,'transitions':N,
          'controller_call_time_s_mean':float(np.mean(arr(log,'controller_call_time_s'))),
          'controller_call_time_excludes_candidate_post_allocator_commit':True
        }
        trace_audit=None
        if 'candidate' in raw.parent.name:
          flags={k:arr(log,k) for k in ['attitude_fusion_rbf_output_enabled','attitude_fusion_rbf_update_enabled']}
          series={k:arr(log,k) for k in ['rbf_output_held','rbf_weight_norm','rbf_weight_max','rbf_weight_derivative_norm','attitude_rbf_estimate_acceleration_rads2','attitude_rbf_compensation_torque_Nm']}
          refs=log['phys_attitude_trace'][0,:]
          assert len(refs)==N
          event=arr(log,'attitude_event_flag').reshape(-1).astype(bool)
          arms=arr(log['arms'],'command')
          clipped=arr(log,'controller_clipped_generalized')
          counters={'sample_index':0,'prepare_time':0,'commit_time':0,'morph_command':0,'omega_body':0,'clipped_torque':0,'estimate_sign':0,'event_flag':0,'rbf_trace_flags':0,'observer_event':0,'numeric_nonfinite':0}
          max_abs={'morph_command':0.,'omega_body':0.,'clipped_torque':0.,'estimate_sign':0.}
          event_count=0
          for i,refobj in enumerate(refs):
            tr=f[refobj]; pr=tr['prepare']; cm=tr['commit']; ob=pr['observer']
            def v(g,k): return np.asarray(g[k][()],dtype=np.float64).reshape(-1)
            vals={'sample_index':v(tr,'sample_index'),'pt':v(pr,'time_s'),'ct':v(cm,'time_s'),
                  'morph':v(tr,'morph_command'),'omega':v(tr,'omega_body'),'tau':v(cm,'tau_cmd_clipped_Nm'),
                  'est':v(pr,'estimateTorque_Nm'),'comp':v(pr,'tau_comp_Nm'),'is_event':v(tr,'is_attitude_event'),
                  'rbf_out':v(tr,'rbf_output_enabled'),'rbf_update':v(tr,'rbf_update_enabled'),
                  'updated':v(ob,'updated'),'delta':v(ob,'delta_s'),'event_delta':v(tr,'event_delta_s')}
            if int(vals['sample_index'][0])!=i+1: counters['sample_index']+=1
            if vals['pt'][0]!=transition[i]: counters['prepare_time']+=1
            if vals['ct'][0]!=transition[i]: counters['commit_time']+=1
            tests=[('morph_command',vals['morph'],arms[:,i]),('omega_body',vals['omega'],state[9:12,i]),('clipped_torque',vals['tau'],clipped[1:4,i]),('estimate_sign',vals['est'],-vals['comp'])]
            for name,a,b in tests:
                diff=float(np.max(np.abs(a-b))) if a.shape==b.shape else math.inf
                max_abs[name]=max(max_abs[name],diff)
                if not np.array_equal(a,b): counters[name]+=1
            if bool(vals['is_event'][0])!=bool(event[i]): counters['event_flag']+=1
            if bool(vals['rbf_out'][0]) or bool(vals['rbf_update'][0]): counters['rbf_trace_flags']+=1
            if bool(vals['updated'][0]):
                event_count+=1
                if not bool(vals['is_event'][0]) or vals['delta'][0]<=0 or abs(vals['delta'][0]-vals['event_delta'][0])>=1e-10: counters['observer_event']+=1
            for key in tr:
                obj=tr[key]
                def finite(g):
                    if isinstance(g,h5py.Dataset):
                        a=np.asarray(g[()])
                        return not (np.issubdtype(a.dtype,np.number) and not np.all(np.isfinite(a)))
                    if isinstance(g,h5py.Group): return all(finite(g[x]) for x in g)
                    return True
                if not finite(obj): counters['numeric_nonfinite']+=1
          trace_audit={'trace_count':len(refs),'event_count':event_count,'top_level_rbf_flags':{k:{'shape':list(v.shape),'values':np.unique(v).tolist()} for k,v in flags.items()},
             'rbf_series':{k:{'shape':list(v.shape),'nonzero_count':int(np.count_nonzero(v))} for k,v in series.items()},
             'mismatch_counts':counters,'max_abs_reconstruction':max_abs,'all_rbf_off':all(not np.any(v) for v in flags.values()) and all(np.count_nonzero(v)==0 for v in series.values()),
             'all_trace_checks_pass':all(v==0 for v in counters.values())}
        status=json.loads(run_status.read_text(encoding='utf-8-sig'))
        stored=status.get('score',{})
        diffs={}
        for k in ['q_rmse_m','q_peak_m','so3_rmse_rad','so3_peak_rad','q_early_rmse_m','q_late_rmse_m','so3_early_rmse_rad','so3_late_rmse_rad']:
            if k in stored: diffs[k+'_abs_diff']=abs(float(score[k])-float(stored[k]))
        return {'arm':raw.parent.name.rsplit('_',1)[-1],'raw_path':str(raw.relative_to(ROOT)),'raw_sha256':sha(raw),'raw_bytes':raw.stat().st_size,
                'run_status_sha256':sha(run_status),'stored_status':status['status'],'runner_status':status['runner_status'],
                'engineering_gate':status.get('engineering_gate'),'safety_gate':status.get('safety_gate'),
                'independent_score':score,'stored_score_abs_differences':diffs,'trace_audit':trace_audit}

runs=[]
for arm in ['baseline','candidate']:
    d=BASE/f'01_{SCENE}_{arm}'
    runs.append(score(d/'run_raw.mat',d/'run_status.json'))
a,b=runs
metric_keys=['q_rmse_m','q_peak_m','q_early_rmse_m','q_late_rmse_m','so3_rmse_rad','so3_peak_rad','so3_early_rmse_rad','so3_late_rmse_rad','motor_saturation_count','generalized_clip_count','tilt_limited_count','controller_call_time_s_mean']
delta={k:b['independent_score'][k]-a['independent_score'][k] for k in metric_keys}
report={'schema':'ROOT_MORPH_DEV2_T3_A01_RAW_REVIEW_V1','scope':'offline independent scoring and trace audit of only T3 A01 baseline/candidate raws; no Plant, TEST, or rerun',
 'scene_id':SCENE,'seed':2026123971,'scene_sha256_expected':'e06aa4dde902603f390554f4d8b022760b44a450b2c9868d68344d44ea5a809f',
 'batch_status_sha256':sha(BASE/'batch_status.json'),'pair_audit_sha256':sha(BASE/'pair_01_audit.json'),'batch_receipt_sha256':sha(BASE/'batch_receipt.json'),
 'runs':runs,'candidate_minus_baseline_independent_delta':delta,
 'conclusion':'T3 raw scores and full candidate traces are independently recomputed here. The MATLAB batch completed both safe arms; the outer launcher receipt stopped because its success predicate expected two non-complete result rows instead of zero. Preserve both the COMPLETE batch status and STOPPED launcher receipt.'}
(OUT/'review.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
fields=['arm','q_rmse_m','q_x_rmse_m','q_y_rmse_m','q_z_rmse_m','q_peak_m','q_early_rmse_m','q_late_rmse_m','so3_rmse_rad','so3_peak_rad','so3_early_rmse_rad','so3_late_rmse_rad','motor_saturation_count','generalized_clip_count','tilt_limited_count','controller_call_time_s_mean','wall_seconds','raw_sha256']
with (OUT/'scores.csv').open('x',newline='',encoding='utf-8') as f:
 w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
 for r in runs:
  s=r['independent_score']; row={'arm':r['arm'],'raw_sha256':r['raw_sha256'],'wall_seconds':json.loads((BASE/f'01_{SCENE}_{r["arm"]}'/'run_status.json').read_text())['wall_seconds']}
  row.update({k:s[k] for k in fields if k in s})
  for i,ax in enumerate('xyz'):row[f'q_{ax}_rmse_m']=s['q_axis_rmse_m'][i]
  w.writerow(row)
print(json.dumps({'review_path':str((OUT/'review.json').relative_to(ROOT)),'review_sha256':sha(OUT/'review.json'),'scores_csv':str((OUT/'scores.csv').relative_to(ROOT)),'runs':[{k:r[k] for k in ['arm','raw_sha256','raw_bytes','stored_status','runner_status','independent_score','stored_score_abs_differences','trace_audit']} for r in runs],'delta':delta},indent=2,ensure_ascii=False))