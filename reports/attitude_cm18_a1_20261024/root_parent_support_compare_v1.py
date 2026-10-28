import pathlib,json,numpy as np,h5py
root=pathlib.Path.cwd();rep=root/'reports/attitude_cm18_a1_20261024';bounds=json.loads((rep/'ROOT_TRAIN_SUPPORT_MARGINAL_REVIEW_v1.json').read_text())['bounds'];m=json.loads((rep/'CM18_A1_DEV_SCREEN12_v1.json').read_text(encoding='utf-8-sig'));rows=[]
def reconstruct(p,J,mass):
 with h5py.File(p) as f:
  g=f['log'];state=np.asarray(g['state']).T;req=np.asarray(g['requested_generalized']).T;t=np.asarray(g['time']).reshape(-1);cmd=np.asarray(g['arms/command']).T;nom=np.asarray(g['attitude_bs_nominal_torque_Nm']).T;idx=np.arange(10,20000,10);dt=np.diff(t);w=state[idx,9:12];alpha=np.linalg.solve(J,(nom[idx]-np.cross(w,w@J.T)).T).T;z=np.vstack((np.zeros((1,4)),np.cumsum(cmd[:-1]*dt[:,None],axis=0)));a=np.array([np.sum(req[k-10:k,1:4]*dt[k-10:k,None],axis=0)/sum(dt[k-10:k]) for k in idx]);x=np.column_stack((w,alpha,req[idx,0]/mass,cmd[idx],z[idx],a));assert x.shape==(1999,18)
  delta=None
  if 'cm18_event_input_18' in g:delta=float(np.max(np.abs(x-np.asarray(g['cm18_event_input_18']).T[idx])));assert delta<1e-10,delta
 return x,delta
for r in m['scenes']:
 sid=r['scene_id'];p=root/'experiments/attitude_cm18_a1_20261024'/('first_flight_preparation_v1' if sid==m['first_engineering_scene'] else 'screen12_remaining_v1')/'runs'/sid/'attempt_01/raw_run.mat'
 with h5py.File(p) as f:
  g=f['log'];J=np.asarray(g['cm18_fixed_inertia_J0_kgm2']).T;mass=float(np.asarray(g['requested_generalized'])[0,10]/np.asarray(g['cm18_event_input_18'])[6,10])
 for method,path in [('CM18_A1',p),('C5_RBF',pathlib.Path(r['baseline_C5_raw_path']))]:
  x,delta=reconstruct(path,J,mass);coverage={}
  for name,b in bounds.items():
   lo=np.array(b['minimum']);hi=np.array(b['maximum']);out=(x<lo-1e-10)|(x>hi+1e-10);coverage[name]=dict(outside_events=int(np.any(out,axis=1).sum()),outside_by_feature=out.sum(axis=0).tolist(),first_outside_time_s=float(np.arange(.01,20,.01)[np.any(out,axis=1)][0]) if np.any(out) else None)
  rows.append(dict(scene_id=sid,method=method,new_log_X18_reconstruction_max_delta=delta,coverage=coverage))
p=rep/'ROOT_C5_PARENT_VS_NEW_SUPPORT_v1.json';assert not p.exists();p.write_text(json.dumps(dict(scope='X18 marginal coverage; alphaBS inferred from fixed J0/zero Jdot0 nominal torque, not independent BS reevaluation',rows=rows),indent=2));print(json.dumps([r for r in rows if 'C15_W14' in r['scene_id']],indent=2))
