import hashlib,json
from pathlib import Path
import numpy as np
D=Path(__file__).resolve().parent
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
ep=D/'frozen_a1_evaluation_v1/ROOT_FROZEN_A1_EVALUATION_v1.json'
sp=D/'ROOT_ALPHA_XY_TRAIN_SUPPORT_DIAGNOSTIC_v1.json'
assert sha(ep)=='2631153d3a8e502923617e4de098c8556ffdaa1d80a5e7138fd16e5637968f97'
e=json.loads(ep.read_text()); s=json.loads(sp.read_text()); rows={}
for fid,v in e['raw_event_exports'].items():
 x=np.asarray(v['X18']); err=np.asarray(v['prediction_error_raw_rad_s2']); y=np.asarray(v['target']); pred=np.asarray(v['prediction_raw_rad_s2'])
 rows[fid]={}
 for name in ['full_1999_event_support','stride_0_5_support']:
  b=s['train_support'][name]; outside=np.any((x[:,3:5]<np.asarray(b['min']))|(x[:,3:5]>np.asarray(b['max'])),axis=1)
  groups={}
  for g,m in [('inside',~outside),('outside',outside)]:
   n=int(m.sum()); energy=np.sum(err[m]**2,axis=0); total=np.sum(err**2,axis=0)
   groups[g]={'event_count':n,'axis_error_energy_fraction':np.divide(energy,total,out=np.zeros(3),where=total>0).tolist(),'axis_error_rmse':np.sqrt(np.mean(err[m]**2,axis=0)).tolist() if n else None,'target_axis_rms':np.sqrt(np.mean(y[m]**2,axis=0)).tolist() if n else None,'prediction_axis_rms':np.sqrt(np.mean(pred[m]**2,axis=0)).tolist() if n else None}
  rows[fid][name]=groups
r={'schema':'ROOT_SUPPORT_ERROR_GROUPS_V1','evaluation_sha256':sha(ep),'support_sha256':sha(sp),'source_sha256':sha(Path(__file__)),'rows':rows,'limits':'Secondary descriptive conditioning on upstream-changed trajectories. Marginal ranges and energy fractions are not causal attribution; original all-event paired gate unchanged.'}
with (D/'ROOT_SUPPORT_ERROR_GROUPS_v1.json').open('x') as f: json.dump(r,f,indent=2,allow_nan=False)
for fid in ['T1_C5','T3_C5']: print(fid,json.dumps(rows[fid]['full_1999_event_support']))
