import csv,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; OUT=Path(__file__).resolve().parent
PARENT=ROOT/'reports/delayed_prediction_c3_parent_20261023'
C1=ROOT/'experiments/position_prior_calibration_c1_20261022_v9/C1_SOURCE_LOCK_v2.json'
src=PARENT/'PARENT_ALL12_COMMON_INPUT.json'; data=json.loads(src.read_text(encoding='utf-8-sig')); c1=json.loads(C1.read_text(encoding='utf-8-sig'))
meta={x['scene_id']:x for x in c1['shared_scenes']}; by={(x['scene_id'],x['host'],x['method_weights'],x['phase']):x for x in data['rows']}
assert len(by)==96
scenes=list(meta)
groups={'ALL':scenes,'HF_W09_W14':[s for s in scenes if meta[s]['band'] in ('W09_W11','W12_W14')],
'W15':[s for s in scenes if meta[s]['band']=='W15'],'LOW_W00_W08':[s for s in scenes if meta[s]['band']=='W00_W08']}
for task in sorted({x['task'] for x in meta.values()}): groups[task]=[s for s in scenes if meta[s]['task']==task]
out=[]
for gn,ss in groups.items():
 for host in ('C2','C3'):
  for phase in ('early','late'):
   for axis,ai in zip('xyz',range(3)):
    a=[by[(s,host,'C2',phase)]['axis_rmse_mps2'][ai] for s in ss]
    b=[by[(s,host,'C3',phase)]['axis_rmse_mps2'][ai] for s in ss]
    out.append(dict(group=gn,host=host,phase=phase,axis=axis,n_scenes=len(ss),
      C2_mean_rmse_mps2=sum(a)/len(a),C3_mean_rmse_mps2=sum(b)/len(b),
      C3_better_scene_count=sum(y<x for x,y in zip(a,b)),
      mean_abs_reduction_mps2=sum(x-y for x,y in zip(a,b))/len(a)))
fields=list(out[0])
with (OUT/'COMMON_INPUT_GROUP_SUMMARY.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(out)
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
script=Path(__file__)
manifest={'status':'AGGREGATED_FROM_PARENT_FULL_12_SCENE_FIXED_INPUT_REPLAY','source':str(src),'source_sha256':sha(src),
'c1_metadata':str(C1),'c1_metadata_sha256':sha(C1),'method':'means of per-scene axis RMSE; C2 and C3 hosts kept separate; paired lower-error counts are not treated as independent samples',
'rows':len(out),'scenes_by_group':{k:len(v) for k,v in groups.items()},'aggregator_sha256':sha(script),'new_Plant':0}
(OUT/'COMMON_INPUT_GROUP_MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':manifest['status'],'rows':len(out),'groups':manifest['scenes_by_group'],'outputs':[str(OUT/'COMMON_INPUT_GROUP_SUMMARY.csv'),str(OUT/'COMMON_INPUT_GROUP_MANIFEST.json')]},indent=2))
