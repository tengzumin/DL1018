import json,pathlib,hashlib,h5py,numpy as np
from scipy.spatial.transform import Rotation
root=pathlib.Path.cwd(); rep=root/'reports/attitude_cm18_a1_20261024';m=json.loads((rep/'CM18_A1_DEV_SCREEN12_v1.json').read_text(encoding='utf-8-sig'));model=json.loads((root/'experiments/attitude_cm18_a1_20261024/deployment_v1/deployment_parameters_v1.json').read_text())['parameters'];mu=np.asarray(model['input_mean']).reshape(-1);std=np.asarray(model['input_std']).reshape(-1);out=[]
for row in m['scenes']:
 sid=row['scene_id'];p=root/'experiments/attitude_cm18_a1_20261024'/('first_flight_preparation_v1' if sid==m['first_engineering_scene'] else 'screen12_remaining_v1')/'runs'/sid/'attempt_01/raw_run.mat'
 with h5py.File(p) as f:
  g=f['log'];ev=np.asarray(g['cm18_event_flag']).reshape(-1).astype(bool);X=np.asarray(g['cm18_event_input_18']).T[ev];z=(X-mu)/std;context=dict(max_abs_z_by_feature=np.max(np.abs(z),axis=0).tolist(),events_any_abs_z_gt5=int(np.count_nonzero(np.any(np.abs(z)>5,axis=1))),events_any_abs_z_gt10=int(np.count_nonzero(np.any(np.abs(z)>10,axis=1))))
 for method,path in [('CM18_A1',p),('C5_RBF',pathlib.Path(row['baseline_C5_raw_path']))]:
  with h5py.File(path) as f:
   g=f['log'];x=np.asarray(g['state']).T[:-1];eta=np.asarray(g['filtered_attitude_reference']).T;t=np.asarray(g['time']).reshape(-1)[:-1];e=np.arctan2(np.sin(eta-x[:,6:9]),np.cos(eta-x[:,6:9]));rot=(Rotation.from_euler('ZYX',x[:,[8,7,6]]).inv()*Rotation.from_euler('ZYX',eta[:,[2,1,0]])).magnitude();bins=[]
   for name,mask in [('pre',t<5),('5_10',(t>=5)&(t<10)),('10_15',(t>=10)&(t<15)),('15_20',t>=15)]:bins.append(dict(period=name,Euler_axis_RMSE_deg=np.rad2deg(np.sqrt(np.mean(e[mask]**2,axis=0))).tolist(),SO3_RMSE_deg=float(np.rad2deg(np.sqrt(np.mean(rot[mask]**2))))))
  out.append(dict(scene_id=sid,method=method,bins=bins,context_zscore=context if method=='CM18_A1' else None))
result=dict(scope='Descriptive context z-scores relative to TRAIN normalizer; not empirical TRAIN support or causal component proof',rows=out);p=rep/'ROOT_SCREEN12_AXIS_CONTEXT_DIAGNOSTIC_v1.json';assert not p.exists();p.write_text(json.dumps(result,indent=2));print(json.dumps([r for r in out if 'C15_W14' in r['scene_id']],indent=2))
