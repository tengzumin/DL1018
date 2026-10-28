"""Independent cache arithmetic audit of the first C5-matched teacher export."""
from pathlib import Path
import hashlib,json
import h5py
import numpy as np
root=Path.cwd(); base=root/'reports/attitude_position_context_probe_20261024/c5_matched_train24_v1'
scene='DL1018_TRAIN_T1_C00_W00'
folder=base/'event_exports_v1'/scene
ap=folder/(scene+'_CSTAR_AUDIT_v1.json')
a=json.loads(ap.read_text(encoding='utf-8-sig'))
assert a['status']=='PASS' and a['canonical_scene_id']==scene
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
cache=Path(a['cache_path']); assert sha(cache)==a['cache_sha256']
ident=a['identity']; raw=Path(ident['flight_raw_path'])
assert sha(raw)==ident['flight_raw_sha256']
assert sha(ident['exporter_matlab_path'])==ident['exporter_matlab_sha256']
with h5py.File(cache,'r') as f:
    e=f['events']
    read=lambda k:np.array(e[k],dtype=float).T
    g=read('G_row_major').reshape(-1,3,3)
    e0=read('E0_rad_s2'); c=read('target_applied_acceleration_rad_s2')
    y=read('target_raw_output_rad_s2'); action=read('target_after_clip_beta_rad_s2')
    beta=read('beta').reshape(-1,1); idx=read('plant_index').ravel()
    assert np.array_equal(idx,np.arange(11,19992,10))
    assert e0.shape==c.shape==y.shape==(1999,3)
    errs=[np.max(np.abs(e0-np.einsum('nij,nj->ni',g,c))),np.max(np.abs(beta-np.minimum(idx[:,None]*.001/2.2,1))),np.max(np.abs(y*beta-c))]
    expected=beta*np.clip(y,[-45,-45,-4.7124],[45,45,4.7124])
    errs.append(np.max(np.abs(action-expected)))
    lin=e0-np.einsum('nij,nj->ni',g,action)
    errs.append(np.max(np.abs(lin-read('target_linear_residual_rad_s2'))))
    full=read('target_full_allocator_error_rad_s2')
    errs.append(np.max(np.abs(full-lin-read('target_full_minus_linear_rad_s2'))))
    assert all(np.isfinite(x).all() for x in [g,e0,c,y,action,full])
    delta=float(max(errs)); assert delta<1e-8
out=base/'ROOT_FIRST_CSTAR_EXPORT_INDEPENDENT_AUDIT_v1.json'; assert not out.exists()
r={'schema':'ROOT_FIRST_CSTAR_EXPORT_INDEPENDENT_AUDIT_V1','status':'PASS','canonical_scene_id':scene,'raw_sha256':sha(raw),'exporter_sha256':ident['exporter_matlab_sha256'],'event_cache_sha256':sha(cache),'export_audit_sha256':sha(ap),'max_independent_delta':delta,'event_count':1999,'source_sha256':sha(__file__),'scope':'Independent NumPy solve/clip/beta/residual arithmetic on exported G/E0; physical helper reconstruction remains MATLAB audit, not independently reproduced physics.','Plant_calls':0,'optimizer_steps':0,'TEST_accessed':False}
out.write_text(json.dumps(r,indent=2),encoding='utf-8'); print(json.dumps(r))
