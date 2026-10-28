import pathlib,json,hashlib,numpy as np,h5py
from scipy.io import loadmat
root=pathlib.Path.cwd();rep=root/'reports/attitude_cm18_a1_20261024';mp=rep/'data_preparation_v1/events_all816_v1/DATASET_MANIFEST_v1.json';manifest=json.loads(mp.read_text());train=[r for r in manifest['rows'] if r['split']=='TRAIN'];assert len(train)==768
bounds={k:[np.full(18,np.inf),np.full(18,-np.inf)] for k in ['all1999','fit_stride5']}
for r in train:
 p=root/r['cache_path'];assert hashlib.sha256(p.read_bytes()).hexdigest()==r['cache_sha256'];x=loadmat(p,variable_names=['X18'])['X18'];assert x.shape==(1999,18)
 for name,a in [('all1999',x),('fit_stride5',x[::5])]:
  bounds[name][0]=np.minimum(bounds[name][0],a.min(axis=0));bounds[name][1]=np.maximum(bounds[name][1],a.max(axis=0))
m=json.loads((rep/'CM18_A1_DEV_SCREEN12_v1.json').read_text(encoding='utf-8-sig'));rows=[]
for r in m['scenes']:
 sid=r['scene_id'];p=root/'experiments/attitude_cm18_a1_20261024'/('first_flight_preparation_v1' if sid==m['first_engineering_scene'] else 'screen12_remaining_v1')/'runs'/sid/'attempt_01/raw_run.mat'
 with h5py.File(p) as f:
  g=f['log'];ev=np.asarray(g['cm18_event_flag']).reshape(-1).astype(bool);x=np.asarray(g['cm18_event_input_18']).T[ev]
 d={}
 for name,(lo,hi) in bounds.items():
  out=(x<lo-1e-10)|(x>hi+1e-10);d[name]=dict(any_feature_outside_events=int(np.any(out,axis=1).sum()),outside_by_feature=out.sum(axis=0).tolist(),max_beyond_span_by_feature=np.maximum(np.maximum(lo-x,0),np.maximum(x-hi,0)).max(axis=0).tolist())
 rows.append(dict(scene_id=sid,event_count=len(x),coverage=d))
result=dict(status='TRAIN768_MARGINAL_BOUNDS_COMPUTED',manifest_sha256=hashlib.sha256(mp.read_bytes()).hexdigest(),scope='Marginal min/max only; being inside does not prove joint support; full1999 bounds include non-fit points',bounds={k:dict(minimum=v[0].tolist(),maximum=v[1].tolist()) for k,v in bounds.items()},rows=rows);out=rep/'ROOT_TRAIN_SUPPORT_MARGINAL_REVIEW_v1.json';assert not out.exists();out.write_text(json.dumps(result,indent=2));print(json.dumps([r for r in rows if 'C15_W14' in r['scene_id']],indent=2))
