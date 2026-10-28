import csv,h5py,scipy.io as sio,numpy as np
from pathlib import Path
out=Path.cwd()/'reports/train_pcf_contract_reconstruction_20261022'; rows=list(csv.DictReader((out/'stratified_sample_manifest.csv').open(encoding='utf-8-sig')))
ix=[0,7,14]
fields=['time','transition_time','position_event_flag','position_bs_nominal_force_N','position_nominal_acceleration_mps2','position_compensation_applied_force_N','position_compensation_applied_acceleration_mps2','position_commanded_force_N','requested_generalized','realized_generalized','controller_clipped_generalized','filtered_attitude_reference','raw_outer_attitude','state','wind_force_I','stage1_position_pcf_coordination_enabled','stage1_position_pcf_a_req_mps2','stage1_position_pcf_a_f_mps2','stage1_position_pcf_r_f_mps2','stage1_position_event']
for i in ix:
 r=rows[i]; print('\nSAMPLE',i,r['run_id'])
 for label,path in [('raw',r['raw_path']),('run_start',r['run_start_path'])]:
  p=Path(path)
  if p.read_bytes()[:128][124:128]==b'\x00\x02IM':
   with h5py.File(p,'r') as f:
    print(label,'MAT73',list(f.keys()))
    if label=='raw':
     for k in ['cfg','opts']:
      if k in f: print(k,'keys',list(f[k].keys())[:30])
     print('cfg plant existence','cfg/plant',('plant' in f.get('cfg',{})))
     if 'cfg/plant' in f:
      print('plant keys',list(f['cfg/plant'].keys()))
      for k in ['mass','g','k1','k2']:
       if k in f['cfg/plant']:
        x=f['cfg/plant'][k]; print('cfg/plant/'+k,x.shape,x.dtype,x[()] if x.size<5 else '')
     g=f['log']
     for k in fields:
      if k in g:
       x=g[k]
       if isinstance(x,h5py.Dataset): print(k,x.shape,x.dtype, (x[()].reshape(-1)[:3].tolist() if x.size<=4 and x.dtype.kind in 'biuf' else ''))
  else:
   print(label,'MAT5',sio.whosmat(p))
   d=sio.loadmat(p,variable_names=['runStart'],simplify_cells=True)
   print('runStart type',type(d.get('runStart')))
   rs=d.get('runStart'); print('runStart keys',list(rs)[:30] if isinstance(rs,dict) else getattr(rs,'_fieldnames',None))
   cfg=rs.get('cfg') if isinstance(rs,dict) else None
   print('cfg keys',list(cfg)[:40] if isinstance(cfg,dict) else type(cfg))
   plant=cfg.get('plant') if isinstance(cfg,dict) else None
   print('plant keys',list(plant)[:30] if isinstance(plant,dict) else type(plant))
   if isinstance(plant,dict): print('plant vals',{k:plant.get(k) for k in ['mass','g','k1','k2']})
 with h5py.File(r['event_h5_path'],'r') as f:
  print('H5 keys',[k for k in f.keys() if isinstance(f[k],h5py.Dataset)])
  for k in ['event_index','plant_index','event_time_s','target_raw','target_clip','x14','phi']:
   if k in f: print(' ',k,f[k].shape,f[k].dtype)
 with np.load(r['cache_path'],allow_pickle=False) as z:
  print('cache keys/shapes',[(k,z[k].shape,str(z[k].dtype)) for k in z.files])
