"""Root independent cross-term calculation on all fixed event reports."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'reports/attitude_cm18_datarepair_20261024'
OUT = BASE / 'ROOT_INDEPENDENT_CLIP_EFFECT12_v1.json'
assert not OUT.exists()
manifest = json.loads((ROOT/'reports/attitude_cm18_a1_20261024/CM18_A1_DEV_SCREEN12_v1.json').read_text(encoding='utf-8-sig'))
rows = []
max_closure = 0.0
for s in manifest['scenes']:
    sid = s['scene_id']
    v = 1 if sid == manifest['first_engineering_scene'] else 2
    p = BASE/f'a1t_same_state_decomposition_v{v}'/sid/f'A1T_SAME_STATE_DECOMPOSITION_{sid}_v{v}.json'
    j = json.loads(p.read_text(encoding='utf-8-sig'))
    assert j['status'] == 'PASS_SINGLE_SCENE_ONLY' and j['scope']['scene_id'] == sid
    es = j['event_records']
    assert len(es) == 1999
    windows = []
    for name, select in [('ALL', lambda e: True), ('PRE', lambda e: e['time_s'] < 5), ('POST', lambda e: e['time_s'] >= 5)]:
        selected = [e for e in es if select(e)]
        sums = dict(fit=0.0, clip=0.0, cross=0.0, actual=0.0)
        for e in selected:
            for a in range(3):
                f, c, r = (e[k][a] for k in ('linear_fit_error_rad_s2', 'linear_clip_error_rad_s2', 'linear_actual_residual_rad_s2'))
                max_closure = max(max_closure, abs(r-f-c))
                sums['fit'] += f*f
                sums['clip'] += c*c
                sums['cross'] += 2*f*c
                sums['actual'] += r*r
        ms = {k: val/len(selected) for k, val in sums.items()}
        assert abs(ms['actual']-ms['fit']-ms['clip']-ms['cross']) < 1e-8
        ms['net_clip_increment'] = ms['clip'] + ms['cross']
        ms['oracle_full_vector_rms'] = (sum(sum(x*x for x in e['full_allocator_cproj_error_rad_s2']) for e in selected)/len(selected))**.5
        windows.append(dict(window=name, event_count=len(selected), **ms))
    rows.append(dict(scene_id=sid, task=s['task'], category=s['category'], report_sha256=hashlib.sha256(p.read_bytes()).hexdigest(), windows=windows))
assert max_closure < 1e-9
report = dict(schema='ROOT_INDEPENDENT_CLIP_EFFECT12_V1', status='PASS_ALL12_EVENT_ARITHMETIC', scenes=rows,
              max_fit_clip_closure=max_closure, source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              scope='Existing reports only; eventwise static comparison. No raw reads, Plant, training, TEST, or closed-loop causal conclusion.')
OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(dict(status=report['status'], scenes=len(rows), max_closure=max_closure,
                     clip_nonzero_scenes=[dict(scene_id=r['scene_id'], net_clip_increment=r['windows'][0]['net_clip_increment']) for r in rows if r['windows'][0]['clip'] > 0])))
