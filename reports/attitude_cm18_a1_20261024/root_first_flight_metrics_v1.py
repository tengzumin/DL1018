import json,hashlib,pathlib,h5py,numpy as np
from scipy.spatial.transform import Rotation
root=pathlib.Path.cwd(); sid='DL1018_DEV_T1_C01_W15'
paths={'C5_RBF':root/f'experiments/position_axis_coordinate_c5_dev72_20261023/runs_dev72_v3/{sid}/C5_AXIS_MASK_M110/attempt_01/raw_run.mat','CM18_A1':root/f'experiments/attitude_cm18_a1_20261024/first_flight_preparation_v1/runs/{sid}/attempt_01/raw_run.mat'}
out=[]
for method,p in paths.items():
 with h5py.File(p,'r') as f:
  g=f['log'];x=np.asarray(g['state']).T[:-1]; ref=np.asarray(g['filtered_attitude_reference']).T; rate=np.asarray(g['filtered_attitude_rate']).T; pos=np.asarray(g['reference']['position']).T[:-1];t=np.asarray(g['time']).reshape(-1)[:-1]
  assert x.shape==(20000,12) and ref.shape==rate.shape==(20000,3) and pos.shape==(20000,3)
  r=Rotation.from_euler('ZYX',x[:,[8,7,6]]); rr=Rotation.from_euler('ZYX',ref[:,[2,1,0]]); delta=r.inv()*rr;angle=delta.magnitude();phi,theta=ref[:,0],ref[:,1];a,b,c=rate.T;wr=np.column_stack((a-np.sin(theta)*c,np.cos(phi)*b+np.sin(phi)*np.cos(theta)*c,-np.sin(phi)*b+np.cos(phi)*np.cos(theta)*c));we=x[:,9:12]-delta.apply(wr);e=x[:,:3]-pos
  for period,m in [('ALL',t<20),('PRE',t<5),('POST',t>=5)]:
   out.append(dict(method=method,period=period,n=int(m.sum()),position_Q_m=float(np.sqrt(np.mean(np.sum(e[m]**2,axis=1)))),position_peak_m=float(np.linalg.norm(e[m],axis=1).max()),SO3_RMSE_deg=float(np.rad2deg(np.sqrt(np.mean(angle[m]**2)))),SO3_peak_deg=float(np.rad2deg(angle[m].max())),body_rate_vector_RMSE_rads=float(np.sqrt(np.mean(np.sum(we[m]**2,axis=1))))))
  print(method,'sat',np.count_nonzero(np.any(np.asarray(g['motor_saturated']).T,axis=1)))
result=dict(scene_id=sid,scope='one engineering DEV flight; no full development or independent test claim',raw_sha256={k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in paths.items()},metrics=out)
p=root/'reports/attitude_cm18_a1_20261024/ROOT_FIRST_FLIGHT_METRICS_v1.json';assert not p.exists();p.write_text(json.dumps(result,indent=2),encoding='utf8');print(json.dumps(result,indent=2))
