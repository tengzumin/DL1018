import hashlib,json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
D=ROOT/'reports/attitude_position_context_probe_20261024'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
mp=ROOT/'experiments/attitude_cm18_a1_20261024/deployment_v1/deployment_parameters_v1.json'
assert sha(mp)=='ee00c46af42cbce83a630ae9b03eaf1a86bfc6047910ed68bc4e7b8b020aa6ae'
m=json.loads(mp.read_text(encoding='utf-8-sig')); p={k:np.asarray(v,dtype=np.float64) for k,v in m['parameters'].items()}
rows={}
for fid in ['T1_B','T1_C5','T3_B','T3_C5']:
 path=D/'offline_events_v2'/f'events_{fid}_v2.json'
 a=json.loads(path.read_text(encoding='utf-8-sig'))
 assert isinstance(a,dict) and a['schema']=='MATCHED_POSITION_PROBE_EVENT_EXPORT_V2' and a['status']=='PASS'
 assert a['identity']['flight_id']==fid and a['identity']['exporter_source_sha256']=='ddb1684b1d720d9bee80b3bcda2c95bf855faee1220fc54e9ba764695c5a54a9'
 x=np.asarray(a['X18'],dtype=np.float64); y=np.asarray(a['target_raw'],dtype=np.float64)
 assert x.shape==(1999,18) and y.shape==(1999,3) and np.isfinite(x).all() and np.isfinite(y).all()
 h1=np.tanh(((x-p['input_mean'])/p['input_std'])@p['W1'].T+p['b1'])
 h2=np.tanh(h1@p['W2'].T+p['b2'])
 coeff=(h2@p['W3'].T+p['b3']).reshape(1999,3,8)
 basis=np.concatenate([x[:,11:15]/2,x[:,7:11]],axis=1)
 pred=np.sum(coeff*basis[:,None,:],axis=2)*p['train_axis_rms_rad_s2']
 err=pred-y; phase=np.asarray(a['phase_code']).reshape(-1)
 rms=np.sqrt(np.mean(err**2,axis=0))
 rows[fid]={'axis_rmse_rad_s2':rms.tolist(),'yaw_rmse_rad_s2':float(rms[2]),'export_sha256':sha(path),'phase_yaw_rmse_rad_s2':{str(int(k)):float(np.sqrt(np.mean(err[phase==k,2]**2))) for k in np.unique(phase)}}
pairs=[]
for task in ['T1','T3']:
 b=rows[task+'_B']['yaw_rmse_rad_s2']; c=rows[task+'_C5']['yaw_rmse_rad_s2']
 pairs.append({'task':task,'B':b,'C5':c,'delta':c-b,'ratio':c/b if b>0 else None,'pass':c-b>=.02 and c>=1.25*b})
r={'schema':'ROOT_INDEPENDENT_FROZEN_A1_PAIR_RECALC_V1','model_sha256':sha(mp),'source_sha256':sha(Path(__file__)),'rows':rows,'pairs':pairs,'both_pairs_pass':all(x['pass'] for x in pairs),'scope':'Manual NumPy recurrence on all1999 events; no evaluator import, training, Plant, TEST or causal overclaim'}
out=D/'ROOT_INDEPENDENT_A1_PAIRS_v1.json'
with out.open('x',encoding='utf-8') as f: json.dump(r,f,indent=2,allow_nan=False)
print(json.dumps({'pairs':pairs,'both_pairs_pass':r['both_pairs_pass']},indent=2))
