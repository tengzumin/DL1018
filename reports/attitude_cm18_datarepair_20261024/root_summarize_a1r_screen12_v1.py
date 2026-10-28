"""Independent macro/group/loss recomputation from the frozen paired CSV."""
import csv
import hashlib
import json
from pathlib import Path
import numpy as np

BASE=Path(__file__).resolve().parent/'a1r_screen12_control_v1'


def main():
    source=BASE/'ROOT_A1R_SCREEN12_PAIRED_SCENES_v1.csv'
    out=BASE/'ROOT_A1R_SCREEN12_MACRO_REVIEW_v1.json'
    assert not out.exists()
    rows=list(csv.DictReader(source.open(encoding='utf-8',newline='')))
    assert len(rows)==len({r['scene_id'] for r in rows})==12
    groups={'ALL12':rows}
    groups.update({t:[r for r in rows if r['task']==t] for t in ('T1','T2','T3')})
    groups['HF_W09_W14']=[r for r in rows if 9<=int(r['scene_id'][-2:])<=14]
    groups['NO_WIND_W15']=[r for r in rows if r['scene_id'].endswith('W15')]
    results={}
    for name,group in groups.items():
        result={'scene_count':len(group),'means':{},'comparisons':{}}
        for controller in ('C5_RBF','A1','A1R'):
            result['means'][controller]={}
            for metric in ('SO3_RMSE_deg','position_Q_m','body_rate_RMSE_rads','SO3_peak_deg','position_peak_m'):
                result['means'][controller][metric]=float(np.mean([float(r[f'{controller}_all_{metric}']) for r in group]))
        for baseline in ('C5_RBF','A1'):
            result['comparisons'][baseline]={}
            for metric in ('SO3_RMSE_deg','position_Q_m','body_rate_RMSE_rads'):
                delta=np.array([float(r[f'A1R_all_{metric}'])-float(r[f'{baseline}_all_{metric}']) for r in group])
                result['comparisons'][baseline][metric]={'wins':int(np.sum(delta < -1e-12)),
                    'ties':int(np.sum(abs(delta)<=1e-12)),'losses':int(np.sum(delta>1e-12)),
                    'loss_scene_ids':[r['scene_id'] for r,d in zip(group,delta) if d>1e-12]}
        results[name]=result
    report={'schema':'ROOT_A1R_SCREEN12_MACRO_REVIEW_V1','status':'PASS',
            'source_csv_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'groups':results,
            'scope':'Fixed twelve development scenarios, frozen scorer, no candidate selection or TEST. A1R is a reference-repair control, not the A1T direct-target candidate.'}
    out.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))


if __name__=='__main__':
    main()
