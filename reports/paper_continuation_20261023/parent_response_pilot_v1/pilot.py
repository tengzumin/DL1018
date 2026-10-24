from pathlib import Path
import json, hashlib
import h5py
import numpy as np
ROOT=Path(__file__).resolve().parents[3]
parent=ROOT/'reports/paper_continuation_20261023/c5_dev72_parent_review/C5_DEV72_RAW_PARENT_REVIEW_v3.json'
assert hashlib.sha256(parent.read_bytes()).hexdigest()=='bb34889559d95a1c995d4d420e3b3d7a702908b58b47cce969dc508a1c697fab'
r=json.loads(parent.read_text(encoding='utf-8-sig'))['rows'][0]; metric=r['C5_metrics'];raw=Path(metric['path'])
assert hashlib.sha256(raw.read_bytes()).hexdigest()==metric['sha256']
with h5py.File(raw,'r') as f:
 l=f['log']
 def get(k):
  a=np.asarray(l[k]);return a.T if a.ndim==2 else a
 x=get('state');rp=get('reference/position');rv=get('reference/velocity');ra=get('reference/acceleration');req=get('stage1_position_pcf_a_req_mps2');rf=get('stage1_position_pcf_r_f_mps2');u=get('position_compensation_applied_acceleration_mps2')
 ids=np.flatnonzero(get('stage1_position_event_inference_valid').ravel());assert np.array_equal(ids,np.arange(320,19991,10))
 phi=get('stage1_position_event_phi_33')[ids];w=np.asarray(l['stage1_position_event_weight_before_33x3']).transpose(0,2,1)
 z=np.einsum('nfi,nf->ni',w,phi);beta=get('stage1_position_event_beta').ravel()[ids];y=get('stage1_position_delayed_prediction_target_mps2')[ids][1:]
e=rp-x[:,:3];s=rv+e-x[:,3:6];d0=np.diff(x[:,3:6],axis=0)/.001-req
rhop=np.diff(rp,axis=0)-.001*rv[:-1]-(np.diff(x[:,:3],axis=0)-.001*x[:-1,3:6]);rhos=np.diff(rv,axis=0)-.001*ra[:-1]+rhop
names=['initial','sampling_position','sampling_surface','pre_ready','tail','prediction','ramp_and_interval','head_clip','masked_pcf']
b=np.zeros((20000,9,2,3));b[:,1,0]=rhop;b[:,2,1]=rhos;b[:320,3,1]=.001*(u-d0)[:320];b[19990:,4,1]=.001*(u-d0)[19990:]
zz=np.repeat(z[:-1],10,axis=0);yy=np.repeat(y,10,axis=0);bb=np.repeat(beta[:-1],10)[:,None];mask=rf[320:19990]*[1,1,0];dm=d0[320:19990]+mask
terms=[bb*(zz-yy),bb*yy-dm,bb*(np.clip(zz,-3,3)-zz),mask]
for i,t in enumerate(terms):b[320:19990,5+i,1]=.001*t
h=np.zeros((20001,9,2,3));h[0,0,0]=e[0];h[0,0,1]=s[0]
for n in range(20000):
 h[n+1,:,0]=.999*h[n,:,0]+.001*h[n,:,1]+b[n,:,0]
 h[n+1,:,1]=-.001*h[n,:,0]+.996*h[n,:,1]+b[n,:,1]
err=float(np.max(np.abs(h[:,:,0].sum(axis=1)-e)));assert err<1e-10,err
v=h[:20000,:,0];gram=np.einsum('nci,ndi->cd',v,v)/20000
q2=float(np.mean(np.sum(e[:20000]**2,axis=1)));assert abs(gram.sum()-q2)<1e-12
out={'status':'PASS_ONE_RAW_RESPONSE_RECONSTRUCTION','scene_id':r['scene_id'],'raw_sha256':metric['sha256'],'channels':names,'position_reconstruction_max_m':err,'gram_m2':gram.tolist(),'Q_reconstructed_m':float(np.sqrt(gram.sum())),'Q_parent_m':metric['Q_0_20_m'],'scope':'One existing DEV C5 path, descriptive decomposition; not causal ablation or full72 verification.','Plant_calls':0,'training_steps':0}
assert abs(out['Q_reconstructed_m']-out['Q_parent_m'])<1e-10
out['source_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
target=Path(__file__).with_name('PILOT_RESULT_v1.json');assert not target.exists();target.write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in out.items() if k!='gram_m2'}))
