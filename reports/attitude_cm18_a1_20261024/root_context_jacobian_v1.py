import pathlib,json,h5py,numpy as np
root=pathlib.Path.cwd();rep=root/'reports/attitude_cm18_a1_20261024';p=json.loads((root/'experiments/attitude_cm18_a1_20261024/deployment_v1/deployment_parameters_v1.json').read_text())['parameters'];w1,w2,w3=[np.array(p[k]) for k in ['W1','W2','W3']];b1,b2,b3=[np.array(p[k]).reshape(-1) for k in ['b1','b2','b3']];mu=np.array(p['input_mean']).reshape(-1);std=np.array(p['input_std']).reshape(-1);rms=np.array(p['train_axis_rms_rad_s2']).reshape(-1);manifest=json.loads((rep/'CM18_A1_DEV_SCREEN12_v1.json').read_text(encoding='utf-8-sig'));rows=[]
def fn(x):
 h1=np.tanh(w1@((x-mu)/std)+b1);h2=np.tanh(w2@h1+b2);c=(w3@h2+b3).reshape(3,8);basis=np.r_[x[11:15]/2,x[7:11]];return (c@basis)*rms
def jac(x):
 h1=np.tanh(w1@((x-mu)/std)+b1);h2=np.tanh(w2@h1+b2);d=(w3@((1-h2*h2)[:,None]*(w2@((1-h1*h1)[:,None]*(w1/std))))).reshape(3,8,18);basis=np.r_[x[11:15]/2,x[7:11]];return np.einsum('abi,b->ai',d,basis)*rms[:,None]
check=0.
for r in manifest['scenes']:
 sid=r['scene_id'];sub='first_flight_preparation_v1' if sid==manifest['first_engineering_scene'] else 'screen12_remaining_v1';path=root/'experiments/attitude_cm18_a1_20261024'/sub/'runs'/sid/'attempt_01/raw_run.mat'
 with h5py.File(path) as f:
  g=f['log'];ev=np.asarray(g['cm18_event_flag']).reshape(-1).astype(bool);x=np.asarray(g['cm18_event_input_18']).T[ev];t=np.asarray(g['transition_time']).reshape(-1)[ev];J0=np.asarray(g['cm18_fixed_inertia_J0_kgm2']).T
 ja=[];jd=[]
 for q,v in enumerate(x):
  d=jac(v);ja.append(np.linalg.norm(d[:,3:6],2));jd.append(np.linalg.norm(J0@d[:,15:18],2))
  if q==700:
   for k in [3,4,5,15,16,17]:
    eps=1e-7;z=np.zeros(18);z[k]=eps;err=np.max(np.abs((fn(v+z)-fn(v-z))/(2*eps)-d[:,k]));check=max(check,float(err))
 ja=np.array(ja);jd=np.array(jd);mask=t>=5;rows.append(dict(scene_id=sid,post5_alpha_sensitivity_norm_quantiles=np.quantile(ja[mask],[0,.5,.9,.99,1]).tolist(),post5_past_torque_feedback_norm_quantiles=np.quantile(jd[mask],[0,.5,.9,.99,1]).tolist(),post5_past_torque_norm_gt1_events=int((jd[mask]>1).sum())))
assert check<1e-6,check
out=rep/'ROOT_CM18_CONTEXT_JACOBIAN_DIAGNOSTIC_v1.json';assert not out.exists();out.write_text(json.dumps(dict(finite_difference_max_delta=check,scope='Frozen map raw output sensitivity; excludes clip, beta, held dynamics and BS/state coupling; norm>1 is not proof of instability',rows=rows),indent=2));print(json.dumps(dict(check=check,rows=[r for r in rows if 'C15' in r['scene_id']]),indent=2))
