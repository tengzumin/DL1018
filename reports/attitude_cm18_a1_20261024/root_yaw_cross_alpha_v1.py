import json,pathlib,h5py,numpy as np
root=pathlib.Path.cwd();d=root/'reports/attitude_cm18_a1_20261024';p=json.loads((root/'experiments/attitude_cm18_a1_20261024/deployment_v1/deployment_parameters_v1.json').read_text())['parameters'];w1,w2,w3=[np.array(p[k]) for k in ['W1','W2','W3']];b1,b2=[np.array(p[k]).reshape(-1) for k in ['b1','b2']];mu=np.array(p['input_mean']).reshape(-1);std=np.array(p['input_std']).reshape(-1);rms=np.array(p['train_axis_rms_rad_s2']).reshape(-1);m=json.loads((d/'CM18_A1_DEV_SCREEN12_v1.json').read_text(encoding='utf-8-sig'));rows=[]
for r in m['scenes']:
 sid=r['scene_id'];sub='first_flight_preparation_v1' if sid==m['first_engineering_scene'] else 'screen12_remaining_v1';path=root/'experiments/attitude_cm18_a1_20261024'/sub/'runs'/sid/'attempt_01/raw_run.mat'
 with h5py.File(path) as f:
  g=f['log'];ev=np.asarray(g['cm18_event_flag']).reshape(-1).astype(bool);x=np.asarray(g['cm18_event_input_18']).T[ev];t=np.asarray(g['transition_time']).reshape(-1)[ev]
 vals=[]
 for a in x[t>=5]:
  h1=np.tanh(w1@((a-mu)/std)+b1);h2=np.tanh(w2@h1+b2);dc=(w3@((1-h2*h2)[:,None]*(w2@((1-h1*h1)[:,None]*(w1/std))))).reshape(3,8,18);basis=np.r_[a[11:15]/2,a[7:11]];j=np.einsum('abi,b->ai',dc,basis)*rms[:,None];vals.append(j[2,3:6])
 v=np.array(vals);rows.append(dict(scene_id=sid,post5_yaw_dprediction_dalpha_xyz_abs_quantiles=np.quantile(abs(v),[.5,.95,1],axis=0).tolist(),yaw_cross_alpha_xy_norm_quantiles=np.quantile(np.linalg.norm(v[:,:2],axis=1),[.5,.95,1]).tolist()))
p=d/'ROOT_YAW_CROSS_ALPHA_SENSITIVITY_v1.json';assert not p.exists();p.write_text(json.dumps(dict(scope='Frozen network local input sensitivity only; must compare to same-state physical ideal-action sensitivity before calling spurious',rows=rows),indent=2));print(json.dumps([r for r in rows if 'C15' in r['scene_id']],indent=2))
