"""Exact axis/time error accounting; no component-causality inference."""
import csv
import json
from pathlib import Path

here = Path(__file__).resolve().parent
with (here / 'PARENT_ALL288_METRICS.csv').open(newline='') as stream:
    raw = list(csv.DictReader(stream))
data = {(r['scene_id'], r['method']): r for r in raw}
rows = []
for sid in sorted({r['scene_id'] for r in raw}):
    b, c = data[sid, 'B'], data[sid, 'C3']
    delta = float(c['Q_0_20_m']) ** 2 - float(b['Q_0_20_m']) ** 2
    row = dict(scene_id=sid, task=sid.split('_')[2], wind=sid[-3:],
               Q_C3_minus_B_mm=1000 * (float(c['Q_0_20_m']) - float(b['Q_0_20_m'])),
               result='WIN' if float(c['Q_0_20_m']) - float(b['Q_0_20_m']) < -1e-12 else 'LOSS',
               delta_Q_squared_m2=delta)
    for axis in 'xyz':
        row[f'{axis}_delta_MSE_m2'] = float(c[f'rmse_{axis}_0_20_m']) ** 2 - float(b[f'rmse_{axis}_0_20_m']) ** 2
    for phase, weight in [('0_5', .25), ('5_20', .75)]:
        row[f'{phase}_weighted_delta_MSE_m2'] = weight * (float(c[f'Q_{phase}_m']) ** 2 - float(b[f'Q_{phase}_m']) ** 2)
    assert abs(sum(row[f'{a}_delta_MSE_m2'] for a in 'xyz') - delta) < 1e-16
    assert abs(row['0_5_weighted_delta_MSE_m2'] + row['5_20_weighted_delta_MSE_m2'] - delta) < 1e-16
    row['largest_worsening_axis'] = max('xyz', key=lambda a: row[f'{a}_delta_MSE_m2'])
    row['peak_C3_minus_B_mm'] = 1000 * (float(c['peak_m']) - float(b['peak_m']))
    row['p95_C3_minus_B_mm'] = 1000 * (float(c['p95_m']) - float(b['p95_m']))
    rows.append(row)
for name, subset in [('ALL72_B_AXIS_PHASE_ACCOUNTING.csv', rows),
                     ('ALL11_B_LOSS_AXIS_PHASE_ACCOUNTING.csv', [r for r in rows if r['result'] == 'LOSS'])]:
    out = here / name
    assert not out.exists(), 'Preserve earlier evidence'
    with out.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(subset)
summary = {}
for task in ['T1', 'T2', 'T3']:
    selected = [r for r in rows if r['task'] == task and r['result'] == 'LOSS']
    summary[task] = dict(n_loss=len(selected),
        axis_sum_delta_MSE_m2={a: sum(r[f'{a}_delta_MSE_m2'] for r in selected) for a in 'xyz'},
        phase_sum_weighted_delta_MSE_m2={p: sum(r[f'{p}_weighted_delta_MSE_m2'] for r in selected) for p in ['0_5', '5_20']})
out = here / 'B_LOSS_ERROR_ACCOUNTING_SUMMARY.json'
assert not out.exists()
out.write_text(json.dumps(dict(tasks=summary, limitation='Post-outcome error accounting; not component causal evidence or a tuning authorization'), indent=2), encoding='utf-8')
print(json.dumps(summary, indent=2))
