import csv,json
from pathlib import Path
import math
OUT=Path(__file__).resolve().parent
runs=list(csv.DictReader((OUT/'ALL36_SUPPLEMENTAL_METRICS.csv').open(encoding='utf-8-sig',newline='')))
pairs=list(csv.DictReader((OUT/'PAIRED_THRESHOLDS.csv').open(encoding='utf-8-sig',newline='')))
scenes={r['scene_id']:r for r in runs if r['method']=='C3'}
groups={'ALL':set(scenes),'HF_W09_W14':{s for s,r in scenes.items() if r['band'] in ('W09_W11','W12_W14')},
'W15':{s for s,r in scenes.items() if r['band']=='W15'},'LOW_W00_W08':{s for s,r in scenes.items() if r['band']=='W00_W08'}}
for task in sorted({r['task'] for r in scenes.values()}): groups[task]={s for s,r in scenes.items() if r['task']==task}
rows=[]
for name,ids in groups.items():
 if not ids: continue
 for m in ('B','C2','C3'):
  rr=[r for r in runs if r['scene_id'] in ids and r['method']==m]
  rows.append({'group':name,'n_scenes':len(ids),'method':m,
    'mean_Q_0_20_mm':sum(float(r['Q_0_20_m']) for r in rr)/len(rr)*1000,
    'mean_Q_0_5_mm':sum(float(r['Q_0_5_m']) for r in rr)/len(rr)*1000,
    'mean_Q_5_20_mm':sum(float(r['Q_5_20_m']) for r in rr)/len(rr)*1000,
    'mean_peak_mm':sum(float(r['peak_m']) for r in rr)/len(rr)*1000,
    'mean_p95_mm':sum(float(r['p95_m']) for r in rr)/len(rr)*1000,
    'mean_motor_saturated_fraction':sum(float(r['motor_saturated_fraction']) for r in rr)/len(rr),
    'mean_generalized_clipped_fraction':sum(float(r['generalized_clipped_fraction']) for r in rr)/len(rr),
    'mean_controller_time_ms_nonformal':sum(float(r['controller_time_mean_ms_nonformal']) for r in rr)/len(rr),
    'mean_controller_time_p95_ms_nonformal':sum(float(r['controller_time_p95_ms_nonformal']) for r in rr)/len(rr)})
 for cmp in ('B','C2'):
  pp=[p for p in pairs if p['scene_id'] in ids and p['comparator']==cmp]
  rows.append({'group':name,'n_scenes':len(ids),'method':f'C3_vs_{cmp}',
    'wins':sum(p['result']=='WIN' for p in pp),'losses':sum(p['result']=='LOSS' for p in pp),'ties':sum(p['result']=='TIE' for p in pp),
    'improvements_ge_1um':sum(p['improvement_ge_1um']=='True' for p in pp),
    'improvements_ge_10um':sum(p['improvement_ge_10um']=='True' for p in pp)})
with (OUT/'GROUP_Q_AND_SUPPLEMENT_SUMMARY.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rows for k in r)));w.writeheader();w.writerows(rows)
print(json.dumps({'output':str(OUT/'GROUP_Q_AND_SUPPLEMENT_SUMMARY.csv'),'rows':len(rows),'groups':{k:len(v) for k,v in groups.items()}},indent=2))
