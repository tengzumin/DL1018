from __future__ import annotations
import csv, hashlib, json, math, re
from pathlib import Path
import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[4]
RAW = ROOT/'experiments/attitude_physics_inertia_observer_20261025/paired_runner/dev3_v1/attempts/DEV3_20261025_A01/01_DL1018_DEV_T1_C00_W03_candidate/run_raw.mat'
LOCK = ROOT/'experiments/attitude_physics_inertia_observer_20261025/paired_runner/dev3_v1/source_lock_paired_runner_v1.json'
SCENE = RAW.parent/'scene_audit.json'
HELPER = ROOT/'experiments/attitude_physics_inertia_observer_20261025/phys_attitude_replacement_candidate_v2.m'
RUNTIME = ROOT/'experiments/attitude_physics_inertia_observer_20261025/paired_runner/matlab/runtime/phys_attitude_replacement_candidate_v2.m'
CONFIG = ROOT/'experiments/attitude_physics_inertia_observer_20261025/paired_runner/matlab/core/default_config.m'
MASS = ROOT/'experiments/attitude_physics_inertia_observer_20261025/paired_runner/matlab/core/arm_mass_properties.m'
DIST_MASS = ROOT/'experiments/attitude_physics_inertia_observer_20261025/paired_runner/matlab/core/distributed_mass_properties.m'
OUT = Path(__file__).resolve().parent/'final'

def sha256(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''): h.update(b)
    return h.hexdigest()
def write_new(name,s):
    with (OUT/name).open('x',encoding='utf-8',newline='') as f: f.write(s)
def vals(g,k): return np.asarray(g[k][()],dtype=np.float64).reshape(-1)
def find_unique(obj,key):
    hits=[]
    def walk(x):
        if isinstance(x,dict):
            if key in x: hits.append(x[key])
            for v in x.values(): walk(v)
        elif isinstance(x,list):
            for v in x: walk(v)
    walk(obj)
    if len(hits)!=1: raise ValueError(f'{key}: expected one match, found {len(hits)}')
    return hits[0]
def simpson(y,h):
    n=len(y)-1
    if n<=0:return np.zeros(y.shape[1])
    if n==1:return h*(y[0]+y[1])/2
    if n%2==0:return h/3*(y[0]+y[-1]+4*y[1:-1:2].sum(0)+2*y[2:-1:2].sum(0))
    if n==3:return 3*h/8*(y[0]+3*y[1]+3*y[2]+y[3])
    m=n-3
    return h/3*(y[0]+y[m]+4*y[1:m:2].sum(0)+2*y[2:m:2].sum(0))+3*h/8*(y[m]+3*y[m+1]+3*y[m+2]+y[m+3])

inputs=(RAW,LOCK,SCENE,HELPER,RUNTIME,CONFIG,MASS,DIST_MASS)
for p in inputs:
    if not p.is_file(): raise FileNotFoundError(p)
lock=json.loads(LOCK.read_text(encoding='utf-8-sig'))
J0=np.asarray(find_unique(lock,'J0_controller_fixed_kgm2'),dtype=np.float64)
ct=CONFIG.read_text(encoding='utf-8-sig')
am=re.search(r"cfg\.rbf\.attitude\s*=\s*struct\(.*?'dmax',\s*\[([^\]]+)\].*?'beta_rise_time',\s*([0-9.eE+-]+)",ct,re.S)
dm=re.search(r"cfg\.plant\.dt\s*=\s*([0-9.eE+-]+)\s*;",ct)
if not (am and dm):raise ValueError('cannot parse frozen dt/dmax/beta')
dmax=np.array([float(x) for x in re.split(r'[;,\s]+',am.group(1).strip()) if x])
beta_rise=float(am.group(2));dt_cfg=float(dm.group(1));T_lpf=.10
raw_hash=sha256(RAW)
source_hashes={str(p.relative_to(ROOT)):sha256(p) for p in inputs[1:]}

with h5py.File(RAW,'r') as f:
    log=f['log'];refs=log['phys_attitude_trace'][0,:];n=len(refs)
    t=np.empty(n);sample=np.empty(n);event=np.zeros(n,bool);updated=np.zeros(n,bool)
    omega=np.empty((n,3));alpha=np.empty((n,3));u=np.empty((n,4));cmd=np.empty((n,3))
    rho=np.empty((n,4));J=np.empty((n,3,3));Jdot=np.empty((n,3,3));shape=np.empty((n,3));aextra=np.empty((n,3))
    beta=np.empty(n);comp=np.empty((n,3));est=np.empty((n,3));dhat_a=np.empty((n,3));dhat_tau=np.empty((n,3))
    rt=np.zeros((n,3));ra=np.zeros((n,3));bar=np.zeros((n,3));delta=np.zeros(n);gamma=np.zeros(n)
    for i,ref in enumerate(refs):
        s=f[ref];pr=s['prepare'];ob=pr['observer'];cm=s['commit']
        t[i]=vals(pr,'time_s')[0];sample[i]=vals(s,'sample_index')[0]
        event[i]=bool(vals(s,'is_attitude_event')[0]);updated[i]=bool(vals(ob,'updated')[0])
        omega[i]=vals(s,'omega_body');alpha[i]=vals(s,'alpha_bs_body');u[i]=vals(s,'morph_command');cmd[i]=vals(cm,'tau_cmd_clipped_Nm')
        rho[i]=vals(pr,'rho_hat_m');J[i]=np.asarray(pr['Jhat_kgm2'][()]).reshape(3,3);Jdot[i]=np.asarray(pr['Jdothat_kgm2ps'][()]).reshape(3,3)
        shape[i]=vals(pr,'tau_shape_Nm');aextra[i]=vals(pr,'a_extra_rads2');beta[i]=vals(pr,'beta')[0]
        comp[i]=vals(pr,'tau_comp_Nm');est[i]=vals(pr,'estimateTorque_Nm');dhat_a[i]=vals(pr,'dhat_a_rads2');dhat_tau[i]=vals(pr,'dhat_tau_Nm')
        if updated[i]:
            rt[i]=vals(ob,'r_tau_Nm');ra[i]=vals(ob,'r_a_rads2');bar[i]=vals(ob,'tau_cmd_bar_Nm');delta[i]=vals(ob,'delta_s')[0]
            gamma[i]=vals(ob,'gamma')[0] if 'gamma' in ob else np.nan
    wind=np.asarray(log['wind_torque_B'][()],dtype=float).reshape(3,n)
    realized=np.asarray(log['realized_generalized'][()],dtype=float).reshape(4,n)
    clipped=np.asarray(log['controller_clipped_generalized'][()],dtype=float).reshape(4,n)

# Offline-only physics truth; never available to the deployed helper.
truth=wind+realized[1:4]-clipped[1:4]
dt=float(np.median(np.diff(t)))
if abs(dt-dt_cfg)>1e-12 or np.max(np.abs(np.diff(t)-dt))>1e-10:raise ValueError('unexpected timestep')

# Replay prepare math and observer LPF/projection from logged state and helper formulas.
shape_r=np.empty((n,3));ae_r=np.empty((n,3));comp_r=np.empty((n,3));est_r=np.empty((n,3));beta_r=np.minimum(sample*dt/beta_rise,1.)
dhat_r=np.empty((n,3));prev=np.zeros(3);lp_hits=0;ae_hits=0
for i in range(n):
    dJ=J[i]-J0
    shape_r[i]=dJ@alpha[i]+np.cross(omega[i],dJ@omega[i])+Jdot[i]@omega[i]
    raw=np.linalg.solve(J0,shape_r[i]-dhat_tau[i]);ae_r[i]=np.clip(raw,-dmax,dmax)
    ae_hits+=int(np.any(np.abs(raw)>dmax+1e-14))
    comp_r[i]=J0@(beta_r[i]*ae_r[i]);est_r[i]=-comp_r[i]
    if updated[i]:
        g=1-math.exp(-delta[i]/T_lpf);raw_d=(1-g)*prev+g*np.linalg.solve(J0,rt[i])
        prev=np.clip(raw_d,-dmax,dmax);lp_hits+=int(np.any(np.abs(raw_d)>dmax+1e-14))
    dhat_r[i]=prev

rows=[];start=0; replay_err=[];bar_err=[]
for j in np.flatnonzero(updated):
    inds=np.arange(start,j+1);h=np.diff(t[inds]);D=float(t[j]-t[start])
    if len(h)==0 or D<=0:raise ValueError('empty interval')
    gvals=np.cross(omega[inds],np.einsum('nij,nj->ni',J[inds],omega[inds]))
    gtrap=np.sum(.5*(gvals[:-1]+gvals[1:])*h[:,None],axis=0)
    if np.max(np.abs(h-h[0]))>1e-10:raise ValueError('nonuniform event interval')
    gsimp=simpson(gvals,float(h[0]));cmdbar=np.sum(cmd[start:j]*h[:,None],axis=0)/D
    r=(J[j]@omega[j]-J[start]@omega[start])/D+gtrap/D-cmdbar
    truebar=np.sum(truth[:,start:j]*h[None,:],axis=1)/D
    qdiff=(gtrap-gsimp)/D
    replay_err.append(r-rt[j]);bar_err.append(cmdbar-bar[j])
    row={'event_sample_index':int(sample[j]),'time_s':float(t[j]),'start_s':float(t[start]),'delta_s':D,'n_intervals':int(j-start)}
    r_simpson=r-qdiff
    for key,v in [('r_tau',r),('r_tau_logged',rt[j]),('tau_truth_bar',truebar),('r_minus_truth',r-truebar),('trapz_minus_simpson',qdiff),('r_tau_simpson',r_simpson),('r_simpson_minus_truth',r_simpson-truebar),('tau_cmd_bar',cmdbar),('dhat_tau',dhat_tau[j]),('estimate_torque',est[j])]:
        for ax,val in zip('xyz',v):row[f'{key}_{ax}_Nm']=float(val)
    row['gamma_logged']=float(gamma[j]);row['gamma_reconstructed']=1-math.exp(-D/T_lpf)
    row['r_reconstruction_max_abs_Nm']=float(np.max(np.abs(r-rt[j])))
    rows.append(row);start=j

metrics=('r_tau','tau_truth_bar','r_minus_truth','trapz_minus_simpson','r_tau_simpson','r_simpson_minus_truth')
phase_rows=[]
for phase,select in [('0-2.2 s',lambda x:x<=2.2),('2.2-20 s',lambda x:x>2.2 and x<=20.)]:
    ev=[r for r in rows if select(r['time_s'])]
    for met in metrics:
        for ax in 'xyz':
            v=np.array([r[f'{met}_{ax}_Nm'] for r in ev])
            phase_rows.append({'phase':phase,'metric':met,'axis':ax,'event_count':len(ev),'rms_Nm':float(np.sqrt(np.mean(v*v))) if len(v) else None,'max_abs_Nm':float(np.max(np.abs(v))) if len(v) else None,'mean_Nm':float(np.mean(v)) if len(v) else None})

def metric(v):return {'rms_by_axis':np.sqrt(np.mean(v*v,axis=0)).tolist(),'max_abs_by_axis':np.max(np.abs(v),axis=0).tolist()}
def row_summary(ev,met):
    return {ax:{'rms_Nm':next(x['rms_Nm'] for x in phase_rows if x['phase']==ev and x['metric']==met and x['axis']==ax),'max_abs_Nm':next(x['max_abs_Nm'] for x in phase_rows if x['phase']==ev and x['metric']==met and x['axis']==ax)} for ax in 'xyz'}
Jdev=J-J0[None,:,:];rho_span=np.ptp(rho,axis=0);act=realized[1:4]-clipped[1:4]
summary={'scope':'offline candidate-only; no baseline/TEST/old MAT; no MATLAB or Plant; physical truth only post-run',
 'raw_path':str(RAW.relative_to(ROOT)),'raw_sha256':raw_hash,'raw_bytes':RAW.stat().st_size,'source_hashes_sha256':source_hashes,
 'n_samples':int(n),'time_s':[float(t[0]),float(t[-1])],'dt_s':dt,'event_count':len(rows),'event_flag_updated_mismatch_count':int(np.count_nonzero(event!=updated)),
 'J0_kgm2':J0.tolist(),'dmax_rads2':dmax.tolist(),'beta_rise_time_s':beta_rise,'observer_lpf_tau_s':T_lpf,
 'C00_invariants':{'max_abs_Jhat_minus_J0_kgm2':float(np.max(np.abs(Jdev))),'Jhat_constant_from_first_max_abs_kgm2':float(np.max(np.abs(J-J[0]))),'rho_hat_initial_m':rho[0].tolist(),'rho_hat_span_m_by_axis':rho_span.tolist(),'max_abs_morph_command':float(np.max(np.abs(u))),'max_abs_Jdothat_kgm2ps':float(np.max(np.abs(Jdot))),'tau_shape':metric(shape),'tau_shape_reconstruction_max_abs_Nm':float(np.max(np.abs(shape_r-shape)))},
 'helper_reconstruction':{'r_tau_max_abs_Nm':float(max(np.max(np.abs(x)) for x in replay_err)),'tau_cmd_bar_max_abs_Nm':float(max(np.max(np.abs(x)) for x in bar_err)),
  'gamma_max_abs':float(np.max(np.abs((1-np.exp(-delta[updated]/T_lpf))-gamma[updated]))),'dhat_a_max_abs_rads2':float(np.max(np.abs(dhat_r-dhat_a))),
  'observer_projection_hit_events':lp_hits,'a_extra_projection_hit_samples':ae_hits,'a_extra_max_abs_reconstruction_rads2':float(np.max(np.abs(ae_r-aextra)),),
  'beta_max_abs':float(np.max(np.abs(beta_r-beta))),'tau_comp_max_abs_Nm':float(np.max(np.abs(comp_r-comp))),'estimateTorque_max_abs_Nm':float(np.max(np.abs(est_r-est))),
  'estimateTorque_rms_Nm_by_axis':metric(est)['rms_by_axis'],'estimateTorque_max_abs_Nm_by_axis':metric(est)['max_abs_by_axis'],'dhat_tau_rms_Nm_by_axis':metric(dhat_tau)['rms_by_axis']},
 'offline_physics_truth':{'definition':'wind_torque_B + realized_generalized[1:4] - controller_clipped_generalized[1:4]; post-run diagnostic only',
  'wind_torque_rms_Nm_by_axis':np.sqrt(np.mean(wind*wind,axis=1)).tolist(),'actuator_realized_minus_clipped_max_abs_Nm_by_axis':np.max(np.abs(act),axis=1).tolist(),
  'per_step_truth_max_abs_Nm_by_axis':np.max(np.abs(truth),axis=1).tolist(),
  'phase_metrics':{p:{m:row_summary(p,m) for m in metrics} for p in ('0-2.2 s','2.2-20 s')}}}

with (OUT/'event_diagnostics.csv').open('x',encoding='utf-8',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
with (OUT/'phase_summary.csv').open('x',encoding='utf-8',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(phase_rows[0]));w.writeheader();w.writerows(phase_rows)
write_new('summary.json',json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def fmt(m,p):
    return '; '.join(f"{a.upper()} RMS={summary['offline_physics_truth']['phase_metrics'][p][m][a]['rms_Nm']:.3e}, max={summary['offline_physics_truth']['phase_metrics'][p][m][a]['max_abs_Nm']:.3e}" for a in 'xyz')
report=f"""# DEV3 A01 C00 candidate 离线残差诊断

仅读 candidate raw、该 run scene audit、release lock 与 helper/config 源；未读 baseline/TEST/旧 MAT，未运行 MATLAB/Plant。物理真值仅离线计算。Raw SHA-256：`{raw_hash}`。

C00 退化检查：全程 max|Jhat−J0|=`{np.max(np.abs(Jdev)):.3e}` kg·m²，rho_hat 跨度最大 `{np.max(rho_span):.3e}` m，max|Jdothat|=`{np.max(np.abs(Jdot)):.3e}`，tau_shape RMS XYZ=`{metric(shape)['rms_by_axis']}` Nm。按 init/prepare/commit 重放，事件 r_tau 与命令均值误差最大 `{summary['helper_reconstruction']['r_tau_max_abs_Nm']:.3e}` / `{summary['helper_reconstruction']['tau_cmd_bar_max_abs_Nm']:.3e}` Nm；LPF/projected d_hat 误差 `{summary['helper_reconstruction']['dhat_a_max_abs_rads2']:.3e}` rad/s²，beta/compensation torque误差 `{summary['helper_reconstruction']['beta_max_abs']:.3e}` / `{summary['helper_reconstruction']['estimateTorque_max_abs_Nm']:.3e}`。observer 和 a_extra 投影命中分别 `{lp_hits}` 与 `{ae_hits}`。

离线物理真值按 `wind_torque_B + realized_generalized[:,2:4] − controller_clipped_generalized[:,2:4]` 算；逐样本 max|truth| XYZ=`{np.max(np.abs(truth),axis=1)}` Nm。事件窗 r_tau−真值：

- 0–2.2 s：r_tau−真值 {fmt('r_minus_truth','0-2.2 s')} Nm；trapz−Simpson 修正 {fmt('trapz_minus_simpson','0-2.2 s')} Nm；替换为 Simpson 后残差 {fmt('r_simpson_minus_truth','0-2.2 s')} Nm。
- 2.2–20 s：r_tau−真值 {fmt('r_minus_truth','2.2-20 s')} Nm；trapz−Simpson 修正 {fmt('trapz_minus_simpson','2.2-20 s')} Nm；替换为 Simpson 后残差 {fmt('r_simpson_minus_truth','2.2-20 s')} Nm。

解释边界：物理真值低于 r_tau 数个数量级；用 Simpson 替换梯形项并未降低残差，反而产生更大的残差。因此证据排除了“真实扰动/估计滞后是主要信号”，但不能把剩余数值项单独归因于 trapz，可能包含离散Plant积分与记录时序误差。本记录不建立跨 arm 因果，也不改变严格 gate FAIL。

脚本 `analyze_c00_candidate.py`；逐事件表 `event_diagnostics.csv`；阶段统计及实现重放/输入 hash 见 `phase_summary.csv`、`summary.json`。命令见 `command.txt`。
"""
write_new('conclusion_zh.md',report)
print(json.dumps({'raw_sha256':raw_hash,'samples':n,'events':len(rows),'r_tau_replay_maxerr_Nm':summary['helper_reconstruction']['r_tau_max_abs_Nm'],'Jhat_minus_J0_max_kgm2':float(np.max(np.abs(Jdev))),'rho_span_max_m':float(np.max(rho_span)),'estimateTorque_rms_Nm_xyz':metric(est)['rms_by_axis'],'truth_step_max_Nm_xyz':np.max(np.abs(truth),axis=1).tolist()},ensure_ascii=False))
