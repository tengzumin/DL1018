"""Independently recompute paired macro outcomes and check every A1T audit."""
import csv
import hashlib
import json
from pathlib import Path
import numpy as np

BASE=Path(__file__).resolve().parent/'a1t_screen12_control_v1'


def main():
    source=BASE/'ROOT_A1T_SCREEN12_PAIRED_SCENES_v1.csv'
    out=BASE/'ROOT_A1T_SCREEN12_MACRO_REVIEW_v1.json'
    assert not out.exists()
    report=json.loads((BASE/'ROOT_A1T_SCREEN12_PAIRED_SCORE_v1.json').read_text(encoding='utf-8'))
    with source.open(encoding='utf-8',newline='') as stream:
        reader=csv.DictReader(stream)
        assert len(reader.fieldnames)==len(set(reader.fieldnames))
        rows=list(reader)
    assert len(rows)==len({r['scene_id'] for r in rows})==12
    assert hashlib.sha256(source.read_bytes()).hexdigest()==report['tables']['scenes']['sha256']
    aliases={'SO3_RMSE_deg':'SO3_rmse_deg','position_Q_m':'position_Q_rmse_m',
             'body_rate_RMSE_rads':'transported_body_rate_vector_rmse_rad_s',
             'SO3_peak_deg':'SO3_peak_deg','position_peak_m':'position_peak_m'}
    for r in rows:
        audit=json.loads((BASE/f"A1T_SCREEN12_LOG_AUDIT_{r['scene_id']}_v1.json").read_text(encoding='utf-8'))
        assert audit['status']=='PASS' and audit['raw_sha256']==r['A1T_raw_sha256']
        for period,window in (('all','ALL_0_20'),('pre','PRE_0_5'),('post','POST_5_20')):
            metrics=audit['scoring']['position_Q_and_filtered_reference_SO3'][window]
            for key,alias in aliases.items():
                assert abs(float(r[f'A1T_{period}_{key}'])-metrics[alias])<1e-12
    groups={'ALL12':rows}
    groups.update({t:[r for r in rows if r['task']==t] for t in ('T1','T2','T3')})
    groups['HF_W09_W14']=[r for r in rows if 9<=int(r['scene_id'][-2:])<=14]
    groups['NO_WIND_W15']=[r for r in rows if r['scene_id'].endswith('W15')]
    results={}
    for name,group in groups.items():
        result={'scene_count':len(group),'means':{},'comparisons':{}}
        for method in ('C5_RBF','A1','A1R','A1T'):
            result['means'][method]={}
            for metric in aliases:
                value=float(np.mean([float(r[f'{method}_all_{metric}']) for r in group]))
                assert abs(value-report['aggregates'][name]['means_by_period']['all'][method][metric])<1e-12
                result['means'][method][metric]=value
        for baseline in ('C5_RBF','A1R','A1'):
            result['comparisons'][baseline]={}
            for metric in ('SO3_RMSE_deg','position_Q_m','body_rate_RMSE_rads'):
                delta=np.array([float(r[f'A1T_all_{metric}'])-float(r[f'{baseline}_all_{metric}']) for r in group])
                counts={'wins':int(np.sum(delta < -1e-12)), 'ties':int(np.sum(abs(delta)<=1e-12)), 'losses':int(np.sum(delta>1e-12))}
                assert counts==report['aggregates'][name]['A1T_paired_outcomes_by_period']['all'][baseline][metric]
                counts['loss_scene_ids']=[r['scene_id'] for r,d in zip(group,delta) if d>1e-12]
                result['comparisons'][baseline][metric]=counts
        results[name]=result
    result={'schema':'ROOT_A1T_SCREEN12_MACRO_REVIEW_V1','status':'PASS',
            'source_csv_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'groups':results,
            'scope':'Independent CSV aggregation and all-scene audit cross-check, not full development or independent TEST validation.'}
    out.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))


if __name__=='__main__':
    main()
