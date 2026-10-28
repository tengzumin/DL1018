"""Small derived tables from existing DEV/VAL CSVs; no binary/TEST access."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


inputs = [ROOT / 'reports/corrected14_full72_benchmark_20261021/PAIR14_SCENE_RESULTS_VS_B.csv',
          ROOT / 'experiments/paper14_v2_round3_xy_pcf_screen/reports/round3_xy_screen_results.csv',
          OUT / 'target_contract_by_scene.csv']
assert sha(inputs[0]) == 'b2264145e9d18896f5764ffe38302576dd08c80e7cce1c277323246092169137'
pairs = pd.read_csv(inputs[0])
assert len(pairs) == 144 and set(pairs.split) == {'DEV', 'VAL'}
assert pairs.groupby('method_id').source_scene_id.nunique().eq(72).all()
pairs['wind_index'] = pairs.source_scene_id.str.extract(r'_W(\d+)$').astype(int)
pairs['band'] = np.select([pairs.wind_index <= 8, pairs.wind_index <= 14], ['W00-W08', 'W09-W14'], default='W15')
pairs['delta_mm_recomputed'] = 1000 * (pairs.candidate_Q_0_20_m - pairs.B_Q_0_20_m)
assert np.max(np.abs(pairs.delta_mm_recomputed - pairs.delta_candidate_minus_B_mm)) < 1e-9


def score(g):
    d = g.delta_mm_recomputed
    return {'n': len(g), 'B_mean_Q_mm': 1000*g.B_Q_0_20_m.mean(),
            'candidate_mean_Q_mm': 1000*g.candidate_Q_0_20_m.mean(), 'delta_mean_mm': d.mean(),
            'wins': int((d < -1e-9).sum()), 'ties': int((d.abs() <= 1e-9).sum()),
            'losses': int((d > 1e-9).sum()), 'max_loss_mm': d.max(),
            'abs_delta_below_1mm': int((d.abs() < 1).sum())}


rows = []
for keys in [('method_id', 'band'), ('method_id', 'band', 'task'), ('method_id',)]:
    for name, g in pairs.groupby(list(keys)):
        name = name if isinstance(name, tuple) else (name,)
        rows.append(dict(zip(keys, name)) | score(g))
pd.DataFrame(rows).fillna('ALL').to_csv(OUT/'paired_summary.csv', index=False)
pairs.loc[pairs.delta_mm_recomputed > 1e-9].sort_values(['method_id','band','delta_mm_recomputed'], ascending=[True,True,False]).to_csv(OUT/'all_losses_70.csv',index=False)
rows=[]
for (method, band), g in pairs.groupby(['method_id', 'band']):
    for tol in (0.0, 0.01, 0.1, 1.0):
        d = g.delta_mm_recomputed
        threshold = max(tol, 1e-9)
        rows.append({'method_id':method,'band':band,'sensitivity_threshold_mm':tol,'n':len(g),
                     'wins':int((d < -threshold).sum()),'within_threshold':int((d.abs()<=threshold).sum()),
                     'losses':int((d>threshold).sum())})
pd.DataFrame(rows).to_csv(OUT/'win_sensitivity.csv',index=False)
screen=pd.read_csv(inputs[1])
assert len(screen)==12 and set(screen.split)=={'VAL'}
screen['band']=screen.band.replace({'W09_W11':'W09-W14','W12_W14':'W09-W14','W00_W08':'W00-W08'})
rows=[]
for band,g in screen.groupby('band'):
    for method in ('on','off','xy'):
        q=g[f'{method}_q_0_20_m']; b=g.b_q_0_20_m
        rows.append({'band':band,'method':method,'n':len(g),'Q_mm':1000*q.mean(),
                     'delta_vs_B_mm':1000*(q-b).mean(),'wins_vs_B':int((q < b-1e-12).sum()),
                     'delta_vs_ON_mm':1000*(q-g.on_q_0_20_m).mean(),
                     'wins_vs_ON':int((q<g.on_q_0_20_m-1e-12).sum())})
pd.DataFrame(rows).to_csv(OUT/'screen_comparison.csv',index=False)
target=pd.read_csv(inputs[2])
rows=[]
for name,g in target.groupby(['band','phase','target','axis']):
    rows.append(dict(zip(['band','phase','target','axis'],name))|{'n':len(g),
                 'prior_worse_than_zero_count':int((g.prior_rmse_mps2>g.target_rms_mps2).sum()),
                 'online_better_than_prior_count':int((g.before_rmse_mps2<g.prior_rmse_mps2).sum()),
                 'one_step_positive_mse_gain_count':int((g.one_step_mse_gain>0).sum())})
pd.DataFrame(rows).to_csv(OUT/'prior_vs_zero_counts.csv',index=False)
rows=[]
for f in (2.2,3.2,3.7,4.8):
    z=np.exp(-2j*np.pi*f*.02)
    r=2*np.pi*f/18
    rows.append({'frequency_Hz':f,'DATT_estimator_LPF_magnitude':abs(.01/(1-.99*z)),
                 'DL_command_filter_ideal_continuous_magnitude':1/(1+r*r),
                 'DL_command_filter_ideal_continuous_phase_deg':-2*np.degrees(np.arctan(r))})
pd.DataFrame(rows).to_csv(OUT/'descriptive_filter_response.csv',index=False)
(OUT/'summary_metadata.json').write_text(json.dumps({'inputs':{str(p.relative_to(ROOT)):sha(p) for p in inputs},
    'script_sha256':sha(Path(__file__)),'raw_read':False,'test_accessed':False,
    'scope':'Existing development results only; response calculations describe isolated filters, not closed-loop transfer functions.'},indent=2)+'\n',encoding='utf8')
print(pd.DataFrame([r for r in pd.read_csv(OUT/'paired_summary.csv').to_dict('records') if r['task']=='ALL']).to_string(index=False))
print(pd.read_csv(OUT/'descriptive_filter_response.csv').to_string(index=False))
