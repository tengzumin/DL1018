from pathlib import Path
import hashlib,importlib.util,json,math
import h5py,numpy as np
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent
NEW=ROOT/'experiments/position_split_target_c7_20261024/C7_SPLIT_TARGET_PREPARED_CFG_OPTS_v1.mat'
LOCK=NEW.with_name('C7_SPLIT_TARGET_INPUT_LOCK_v1.json')
DECODER=ROOT/'reports/paper14_v2/phase1/audit_w15_position_replay.py'
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
assert sha(DECODER)=='372d92cb17da99884e742d3fa0c877200c3bb2bc6fac7f10e7a1a046b97a76af'
spec=importlib.util.spec_from_file_location('pinned_decoder',DECODER);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
lock=json.loads(LOCK.read_text(encoding='utf-8-sig'));OLD=Path(lock['refs']['c5_prepared_snapshot']['path']);assert sha(OLD)==lock['refs']['c5_prepared_snapshot']['sha256']
oldprep=json.loads(Path(lock['refs']['c5_prepare_result']['path']).read_text(encoding='utf-8-sig'));assert oldprep['snapshot_sha256']==sha(OLD)
def read(p):
 with h5py.File(p,'r') as f:return {n:m.h5_tree(f[n]) for n in ['cfg','opts','W0','modelIdentity','sceneIdentity']}
a,b=read(OLD),read(NEW)
def same(x,y,path='root'):
 if isinstance(x,dict):
  assert isinstance(y,dict) and set(x)==set(y),path
  for k in x:same(x[k],y[k],path+'/'+k)
 elif isinstance(x,(list,tuple)):
  assert isinstance(y,(list,tuple)) and len(x)==len(y),path
  for i,(v,w) in enumerate(zip(x,y)):same(v,w,path+'/'+str(i))
 elif isinstance(x,float) and math.isnan(x):assert isinstance(y,float) and math.isnan(y),path
 else:assert x==y,(path,str(x)[:80],str(y)[:80])
same(a['cfg'],b['cfg'],'cfg');same(a['W0'],b['W0'],'W0');same(a['modelIdentity'],b['modelIdentity'],'modelIdentity');same(a['sceneIdentity'],b['sceneIdentity'],'sceneIdentity')
oldopts=dict(a['opts']);newopts=dict(b['opts']);assert np.array_equal(np.array(oldopts.pop('position_coordinate_mask')).reshape(-1),[1,1,0]);assert np.array_equal(np.array(newopts.pop('tracking_mask')).reshape(-1),[1,1,0]);assert np.array_equal(np.array(newopts.pop('target_mask')).reshape(-1),[0,0,0]);same(oldopts,newopts,'opts_except_masks')
model=b['opts']['stage1_position_runtime']['model'];W0=np.asarray(b['W0'],dtype='<f8');assert W0.shape==(33,3)
wsha=hashlib.sha256(W0.tobytes(order='F')).hexdigest();assert wsha=='88f8c4f2495438c3797655c48bab1bf0c11ac2e27bff1f5f2a7423a8f0a2cf53'
assert np.array_equal(np.asarray(model['output_W']),W0)
h=hashlib.sha256()
for name in ['input_mu','input_sigma']:
 v=np.asarray(model[name],dtype='<f8').reshape(1,14);assert np.isfinite(v).all()
 h.update((name+"\0((1, 14), 'float64')\0").encode());h.update(v.tobytes(order='F'))
normalizer=h.hexdigest();assert normalizer=='533aad9a2c66874cfa67f5d268661835e81e58b797cba7d6fc1c12d4013de5f0'
res={'status':'PASS_PARENT_ACTUAL_MAT_SNAPSHOT_SINGLE_FACTOR_AND_MODEL_ARRAY_IDENTITIES','old_snapshot_sha256':sha(OLD),'new_snapshot_sha256':sha(NEW),'input_lock_sha256':sha(LOCK),'source_sha256':sha(Path(__file__)),'decoder_sha256':sha(DECODER),'W0_actual_arrays_sha256':wsha,'normalizer_actual_arrays_sha256':normalizer,'cfg_equal':True,'opts_equal_except_Ms_My':True,'sceneIdentity_equal':True,'modelIdentity_equal':True,'c5_prepare_binds_actual_old_snapshot':True,'Plant_calls':0,'training_steps':0,'TEST_accessed':False,'scope':'Actual old/new MAT content comparison. No simulation or counterfactual performance claim.'}
out=HERE/'PARENT_ACTUAL_SNAPSHOT_COMPARISON_v1.json';assert not out.exists();out.write_text(json.dumps(res,indent=2)+'\n',encoding='utf-8');print(json.dumps(res))
