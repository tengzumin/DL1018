import csv, h5py, numpy as np, scipy.io as sio
from pathlib import Path
root=Path.cwd(); out=root/'reports/train_pcf_contract_reconstruction_20261022'
rows=list(csv.DictReader((out/'stratified_sample_manifest.csv').open(encoding='utf-8-sig')))
for r in rows:
    rp=Path(r['raw_path']); hp=Path(r['event_h5_path']); cp=Path(r['cache_path']); sp=Path(r['run_start_path'])
    print('\nSAMPLE',r['run_id'],r['role'],r['wind_band'])
    with h5py.File(rp,'r') as f:
        print('raw root',list(f.keys()))
        o=f['log']
        want=[k for k in o.keys() if any(s in k.lower() for s in ('time','position','force','generalized','attitude','state','wind','pcf','stage1'))]
        print('target log fields',[(k, type(o[k]).__name__, list(o[k].shape) if isinstance(o[k],h5py.Dataset) else list(o[k].keys())[:6],str(o[k].dtype) if isinstance(o[k],h5py.Dataset) else '') for k in want])
        for grp in ['cfg','opts']:
            if grp in f:
                print('group',grp, list(f[grp].keys())[:40])
                if 'plant' in f[grp]:
                    q=f[grp]['plant']; print('plant',list(q.keys())[:50]);
                    for k in ['mass','g']:
                        if k in q and isinstance(q[k],h5py.Dataset): print(k,q[k][()])
    with h5py.File(hp,'r') as f:
        print('event root',list(f.keys()))
        print('event shapes',[(k,list(f[k].shape),str(f[k].dtype)) for k in f.keys() if isinstance(f[k],h5py.Dataset)])
    with np.load(cp,allow_pickle=False) as z:
        print('cache keys',z.files)
        print('cache shapes',[(k,z[k].shape,str(z[k].dtype)) for k in z.files])
    if sp.open('rb').read(128)[124:128] != b'\x00\x02IM':
        print('whosmat',sio.whosmat(sp))
        d=sio.loadmat(sp,variable_names=['runStart'],squeeze_me=False,struct_as_record=False)
        rs=d.get('runStart'); print('runStart type',type(rs),np.shape(rs))
        print('fields',getattr(rs,'_fieldnames',None))
        cfg=getattr(rs,'cfg',None)
        print('cfg',type(cfg),np.shape(cfg),getattr(cfg,'_fieldnames',None))
        plant=getattr(cfg,'plant',None)
        print('plant',type(plant),np.shape(plant),getattr(plant,'_fieldnames',None))
        for k in ['mass','g']:
            x=getattr(plant,k,None)
            if x is not None: print('cfg plant',k,np.asarray(x).shape,np.asarray(x).dtype,np.asarray(x).reshape(-1)[:3])
print('\nMODEL SUMMARY:')
print((root/'reports/paper14_v2/phase1/mechanism_components_summary.json').read_text(encoding='utf-8')[:6000])
