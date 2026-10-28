"""Read-only paired SCREEN12 scoring; absent scenes remain explicitly incomplete."""
import json,pathlib,hashlib,h5py,numpy as np
from scipy.spatial.transform import Rotation
ROOT=pathlib.Path.cwd(); REPORT=ROOT/'reports/attitude_cm18_a1_20261024'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def score(p):
 with h5py.File(p,'r') as f:
  g=f['log'];x=np.asarray(g['state']).T[:-1];t=np.asarray(g['time']).reshape(-1)[:-1];ref=np.asarray(g['filtered_attitude_reference']).T;rate=np.asarray(g['filtered_attitude_rate']).T;pos=np.asarray(g['reference']['position']).T[:-1]
  assert x.shape==(20000,12) and ref.shape==rate.shape==(20000,3) and pos.shape==(20000,3) and np.isfinite(x).all()
  actual=Rotation.from_euler('ZYX',x[:,[8,7,6]]);desired=Rotation.from_euler('ZYX',ref[:,[2,1,0]]);delta=actual.inv()*desired;angle=delta.magnitude();phi,theta=ref[:,:2].T;a,b,c=rate.T;wr=np.column_stack((a-np.sin(theta)*c,np.cos(phi)*b+np.sin(phi)*np.cos(theta)*c,-np.sin(phi)*b+np.cos(phi)*np.cos(theta)*c));we=x[:,9:12]-delta.apply(wr);e=x[:,:3]-pos
  metrics={}
  for name,m in [('all',(t>=0)&(t<20)),('pre',(t>=0)&(t<5)),('post',(t>=5)&(t<20))]:
   metrics[name]=dict(n=int(m.sum()),position_Q_m=float(np.sqrt(np.mean(np.sum(e[m]**2,axis=1)))),position_axis_RMSE_m=np.sqrt(np.mean(e[m]**2,axis=0)).tolist(),position_peak_m=float(np.linalg.norm(e[m],axis=1).max()),SO3_RMSE_deg=float(np.rad2deg(np.sqrt(np.mean(angle[m]**2)))),SO3_peak_deg=float(np.rad2deg(angle[m].max())),body_rate_RMSE_rads=float(np.sqrt(np.mean(np.sum(we[m]**2,axis=1)))))
  metrics['motor_saturated_transitions']=int(np.count_nonzero(np.any(np.asarray(g['motor_saturated']).T,axis=1)))
  if 'cm18_event_flag' in g:metrics['cm18_events']=int(np.count_nonzero(np.asarray(g['cm18_event_flag'])));assert metrics['cm18_events']==1999
 return dict(raw_sha256=sha(p),metrics=metrics)
def main():
 manifest=REPORT/'CM18_A1_DEV_SCREEN12_v1.json';m=json.loads(manifest.read_text(encoding='utf-8-sig'));rows=[];missing=[]
 for item in m['scenes']:
  sid=item['scene_id'];sub='first_flight_preparation_v1' if sid==m['first_engineering_scene'] else 'screen12_remaining_v1';p=ROOT/'experiments/attitude_cm18_a1_20261024'/sub/'runs'/sid/'attempt_01/raw_run.mat'
  if not p.exists():missing.append(sid);continue
  baseline=pathlib.Path(item['baseline_C5_raw_path']);assert sha(baseline)==item['baseline_C5_raw_sha256'];new=score(p);old=score(baseline);rows.append(dict(scene_id=sid,task=item['task'],category=item['category'],C5_RBF=old,CM18_A1=new))
 result=dict(schema='ROOT_CM18_SCREEN12_PAIRED_SCORE_V1',status='COMPLETE_SCORED_PENDING_REVIEW' if not missing else 'INCOMPLETE',manifest_sha256=sha(manifest),completed=len(rows),missing=missing,rows=rows)
 if not missing:
  result['aggregate']=dict(SO3_win_scenes=sum(r['CM18_A1']['metrics']['all']['SO3_RMSE_deg']<r['C5_RBF']['metrics']['all']['SO3_RMSE_deg']-1e-12 for r in rows),position_win_scenes=sum(r['CM18_A1']['metrics']['all']['position_Q_m']<r['C5_RBF']['metrics']['all']['position_Q_m']-1e-12 for r in rows),mean_SO3_deg={key:float(np.mean([r[key]['metrics']['all']['SO3_RMSE_deg'] for r in rows])) for key in ['C5_RBF','CM18_A1']},mean_position_Q_m={key:float(np.mean([r[key]['metrics']['all']['position_Q_m'] for r in rows])) for key in ['C5_RBF','CM18_A1']})
 out=REPORT/'ROOT_SCREEN12_PAIRED_METRICS_v1.json';assert not out.exists(),'Do not overwrite prior scores';out.write_text(json.dumps(result,indent=2),encoding='utf8');print(json.dumps({k:v for k,v in result.items() if k!='rows'},indent=2))
if __name__=='__main__':main()
