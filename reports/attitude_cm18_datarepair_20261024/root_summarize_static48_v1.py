"""Summarize all frozen static-action replay scenes, including losses."""
import csv
import json
from pathlib import Path
import numpy as np

BASE = Path(__file__).resolve().parent


def main():
    output = BASE / 'ROOT_STATIC48_SUMMARY_v1.json'
    table = BASE / 'ROOT_STATIC48_PAIRED_v1.csv'
    assert not output.exists() and not table.exists()
    paths = [BASE / 'ROOT_STATIC_SCREEN4_INDEPENDENT_AUDIT_v1.json',
             BASE / 'ROOT_STATIC_REMAINING44_INDEPENDENT_AUDIT_v1.json']
    rows = []
    for path in paths:
        report = json.loads(path.read_text(encoding='utf-8'))
        assert report['status'] == 'PASS'
        rows.extend(report['scenes'])
    rows.sort(key=lambda r:r['scene_id'])
    assert len(rows) == len({r['scene_id'] for r in rows}) == 48
    groups = {'ALL48':rows}
    for task in ('T1','T2','T3'):
        groups[task] = [r for r in rows if f'_{task}_' in r['scene_id']]
    groups['HF_W09_W14'] = [r for r in rows if 9 <= int(r['scene_id'][-2:]) <= 14]
    groups['NO_WIND_W15'] = [r for r in rows if r['scene_id'].endswith('W15')]
    summaries = {}
    for name, group in groups.items():
        values = {}
        for model in ('RBF','A1R','A1T'):
            values[model] = {
                'macro_vector_rmse_rad_s2':float(np.mean([r['metrics'][model]['vector_rmse_rad_s2'] for r in group])),
                'macro_axis_rmse_rad_s2':np.mean([r['metrics'][model]['axis_rmse_rad_s2'] for r in group],axis=0).tolist()}
        for baseline in ('RBF','A1R'):
            diffs = np.array([r['metrics']['A1T']['vector_rmse_rad_s2']-r['metrics'][baseline]['vector_rmse_rad_s2'] for r in group])
            values[f'A1T_vs_{baseline}'] = {'wins':int(np.sum(diffs < -1e-12)),
                'ties':int(np.sum(abs(diffs)<=1e-12)),'losses':int(np.sum(diffs>1e-12)),
                'loss_scene_ids':[r['scene_id'] for r,d in zip(group,diffs) if d>1e-12]}
        summaries[name] = {'scene_count':len(group),'results':values}
    fields = ['scene_id'] + [f'{m}_{v}' for m in ('RBF','A1R','A1T') for v in ('vector','roll','pitch','yaw')]
    with table.open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for r in rows:
            row={'scene_id':r['scene_id']}
            for m in ('RBF','A1R','A1T'):
                row[f'{m}_vector']=r['metrics'][m]['vector_rmse_rad_s2']
                row.update({f'{m}_{a}':v for a,v in zip(('roll','pitch','yaw'),r['metrics'][m]['axis_rmse_rad_s2'])})
            writer.writerow(row)
    result={'schema':'ROOT_STATIC48_SUMMARY_V1','status':'PASS','groups':summaries,
            'Plant_calls':0,'TEST_accessed':False,'units':'rad/s^2',
            'scope':'Same recorded C5 states; single-action counterfactual error, not tracking or new trajectories. Scene macro means; no training seed generalization.'}
    output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
