from __future__ import annotations
import csv, hashlib, json, re
from collections import defaultdict
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
source = ROOT / 'reports/corrected14_full72_benchmark_20261021/PAIR14_SCENE_RESULTS_VS_B.csv'
expected = 'b2264145e9d18896f5764ffe38302576dd08c80e7cce1c277323246092169137'
source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
if source_sha != expected:
    raise SystemExit(f'frozen source SHA mismatch: {source_sha}')
all_rows = list(csv.DictReader(source.open(newline='', encoding='utf-8-sig')))
rows = [r for r in all_rows if r['method_id'] == 'CORRECTED_TRAIN_DSSM14_G12_R32']
if len(rows) != 72 or len({r['source_scene_id'] for r in rows}) != 72:
    raise SystemExit(f'expected 72 unique corrected DSSM14 scenes; got {len(rows)}')
parsed = []
for r in rows:
    match = re.search(r'_W(\d{2})$', r['source_scene_id'])
    if not match:
        raise SystemExit(f'bad scene ID: {r["source_scene_id"]}')
    w = int(match.group(1))
    b = float(r['B_Q_0_20_m'])
    c = float(r['candidate_Q_0_20_m'])
    if abs((c-b)*1000-float(r['delta_candidate_minus_B_mm'])) > 1e-9:
        raise SystemExit(f'paired delta mismatch: {r["source_scene_id"]}')
    parsed.append((r,w,b,c))
groups = defaultdict(list)
for row in parsed:
    r,w,b,c=row
    groups['ALL'].append(row)
    groups[f'SPLIT:{r["split"]}'].append(row)
    groups[f'TASK:{r["task"]}'].append(row)
    groups[f'SPLIT_TASK:{r["split"]}:{r["task"]}'].append(row)
    groups[f'WIND_INDEX:W{w:02}'].append(row)
    groups[f'WIND_BAND:{w//3}'].append(row)
    if 9 <= w <= 14: groups['W09_W14_HIGH'].append(row)
    if w == 15: groups['W15_ZERO'].append(row)
result=[]
for name, vals in sorted(groups.items()):
    wins=sum(c < b - 1e-12 for _,_,b,c in vals)
    ties=sum(abs(c-b) <= 1e-12 for _,_,b,c in vals)
    result.append({'group':name,'n':len(vals),'wins':wins,'ties':ties,'losses':len(vals)-wins-ties,
                   'B_macro_Q_mm':1000*sum(x[2] for x in vals)/len(vals),
                   'DSSM14_macro_Q_mm':1000*sum(x[3] for x in vals)/len(vals),
                   'delta_mm':1000*sum(x[3]-x[2] for x in vals)/len(vals)})
out=Path(__file__).resolve().parent
with (out/'initial_corrected14_groups.csv').open('w',newline='',encoding='utf-8-sig') as f:
    wri=csv.DictWriter(f,fieldnames=list(result[0]));wri.writeheader();wri.writerows(result)
payload={'source':str(source),'source_sha256':source_sha,'method_id':'CORRECTED_TRAIN_DSSM14_G12_R32','scene_count':len(parsed),'unique_scenes':len({x[0]['source_scene_id'] for x in parsed}),'scope':'existing corrected VAL/DEV table only; no raw files and no TEST','threshold_m':1e-12,'groups':result}
(out/'initial_corrected14_groups.json').write_text(json.dumps(payload,indent=2),encoding='utf-8')
print(json.dumps([x for x in result if x['group'] in ('ALL','W09_W14_HIGH','W15_ZERO')],indent=2))
