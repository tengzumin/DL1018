"""Fixed-model CPU inference on existing W15 TRAIN/VAL cache; no fitting."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ['OMP_NUM_THREADS']='1'

import json
from pathlib import Path
import h5py
import numpy as np
import pandas as pd
from audit_target_contract import low_band_rms, sha

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
ARCHIVE=ROOT.parent/'REFERENCE_FIX_FULL72_20261021_022342_313'
INDEX=ARCHIVE/'corrected_reference_training_v1/corrected_pair_training/manifests/PAIR_TRAINING_INPUT_INDEX.csv'
MODEL_INDEX=ROOT/'reports/paper14_v2/phase1/mechanism_components_by_scene.csv'
assert sha(INDEX)=='257089f1dc455b7bc97bf1c772be31d1d8ae83079e7ec41f591d96e31fed39ca'
assert sha(MODEL_INDEX)=='f1ba9ff2335ea75e992436f753fb75ff1678271f33bf6d2fe706db4b45572e3b'
source=pd.read_csv(MODEL_INDEX).iloc[0]
p=Path(source.raw_path).resolve()
assert p.is_relative_to(ARCHIVE.resolve()) and sha(p)==source.raw_sha256_before
stat0=(p.stat().st_size,p.stat().st_mtime_ns)
with h5py.File(p,'r') as f:
    model={k:np.asarray(f['opts/stage1_position_runtime/model/'+k],dtype=np.float64)
           for k in ('input_mu','input_sigma','input_W','input_b','project_W','project_b','output_W','ssm_tau')}
    flags=np.flatnonzero(np.asarray(f['log/position_event_flag']).reshape(-1)>0)
    x_check=np.asarray(f['log/stage1_position_feature_14'],dtype=np.float64)[:,flags].T
    valid=np.flatnonzero(np.asarray(f['log/stage1_position_event_inference_valid']).reshape(-1)>0)
    phi_check=np.asarray(f['log/stage1_position_event_phi_33'],dtype=np.float64)[:,valid].T
assert len(flags)==1999 and len(valid)==1968 and np.array_equal(flags[31:],valid)


def encode(x):
    """Exact finite 32-event, zero-initialized diagonal recurrence in batch form."""
    drive=np.tanh(((x-model['input_mu'])/model['input_sigma'])@model['input_W']+model['input_b'])
    alpha=np.exp(-.01/model['ssm_tau'])
    state=np.zeros((len(x)-31,32))
    for lag in range(32):
        state+=(1-alpha)*alpha**lag*drive[31-lag:len(x)-lag]
    h=np.tanh(state@model['project_W']+model['project_b'])
    v=np.column_stack((h,np.ones(len(h))))
    return v/np.sqrt(1+np.sum(h*h,axis=1,keepdims=True))


parity=float(np.max(np.abs(encode(x_check)-phi_check)))
assert parity<1e-12, parity
assert (p.stat().st_size,p.stat().st_mtime_ns)==stat0 and sha(p)==source.raw_sha256_before
index=pd.read_csv(INDEX)
selected=index.loc[index.wind_cell.eq(15) & index.split.str.lower().isin(['train','val'])]
assert len(selected)==102 and selected.groupby('split').size().to_dict()=={'train':96,'val':6}
rows=[]
identities=[]
for rec in selected.to_dict('records'):
    cache=Path(rec['cache_path']).resolve()
    assert any(cache.is_relative_to(base.resolve()) for base in (ROOT,ARCHIVE))
    st=(cache.stat().st_size,cache.stat().st_mtime_ns)
    assert sha(cache)==rec['cache_sha256']
    with np.load(cache,allow_pickle=False) as z:
        x=np.asarray(z['x14'],dtype=np.float64)
        y=np.asarray(z['raw'],dtype=np.float64)[31:]
        clipped=np.asarray(z['y'],dtype=np.float64)[31:]
        times=np.asarray(z['event_time_s'],dtype=np.float64)[31:]
    assert x.shape==(1999,14) and y.shape==clipped.shape==(1968,3)
    assert np.max(np.abs(clipped-np.clip(y,-3,3)))<1e-6
    raw=encode(x)@model['output_W'].T
    beta=np.clip(times[:,None]/1.8,0,1)
    applied=beta*np.clip(raw,-3,3)
    for phase,take in (('all_valid_0p32_20',np.ones(len(times),bool)),
                       ('beta1_1p8_20',times>=1.8-1e-5),('late_5_20',times>=5-1e-5)):
        for axis,label in enumerate('xyz'):
            err=(applied-y)[take,axis]
            rows.append({'run_id':rec['run_id'],'split':rec['split'],'task':rec['task'],'role':rec['role'],
                         'phase':phase,'axis':label,'n_events':int(take.sum()),
                         'target_rms_mps2':float(np.sqrt(np.mean(y[take,axis]**2))),
                         'prior_applied_rmse_mps2':float(np.sqrt(np.mean(err**2))),
                         'prior_error_mean_mps2':float(np.mean(err)),
                         'prior_error_low_0_1Hz_rms_mps2':low_band_rms(err),
                         'unclipped_prior_vs_clipped_label_rmse_mps2':float(np.sqrt(np.mean((raw-clipped)[take,axis]**2)))})
    assert (cache.stat().st_size,cache.stat().st_mtime_ns)==st and sha(cache)==rec['cache_sha256']
    identities.append({'run_id':rec['run_id'],'cache_sha256':rec['cache_sha256'],'unchanged':True})
df=pd.DataFrame(rows)
df.to_csv(OUT/'w15_source_prior_by_episode.csv',index=False)
numeric=[c for c in df if c.endswith('mps2')]
grouped=df.groupby(['split','task','role','phase','axis'])
summary=grouped[numeric].mean().reset_index()
summary['episode_count']=grouped.run_id.nunique().to_numpy()
summary['prior_worse_than_zero_count']=grouped.apply(lambda g:int((g.prior_applied_rmse_mps2>g.target_rms_mps2).sum()),include_groups=False).to_numpy()
summary.to_csv(OUT/'w15_source_prior_groups.csv',index=False)
metadata={'status':'PASS_FIXED_MODEL_W15_SOURCE_INFERENCE','model_source_raw_sha256':source.raw_sha256_before,
          'index_sha256':sha(INDEX),'script_sha256':sha(Path(__file__)),'encoder_phi_parity_max_abs':parity,
          'TRAIN_episodes':96,'VAL_episodes':6,'raw_target_definition':'Physical Y from the frozen source cache, not reconstructed Y+rf.',
          'all_source_sha_and_stat_unchanged':True,'cache_identities':identities,
          'optimizer_steps':0,'plant_calls':0,'GPU_used':False,'TEST_accessed':False,
          'scope':'Unweighted episode macro residual fit on original B/POS_OFF source trajectories; not the weighted training loss and not new closed-loop performance.'}
(OUT/'w15_source_prior_metadata.json').write_text(json.dumps(metadata,indent=2)+'\n',encoding='utf8')
print(json.dumps({k:v for k,v in metadata.items() if k!='cache_identities'}))
print(df.loc[df.phase.eq('late_5_20')].groupby(['split','task','axis'])[['target_rms_mps2','prior_applied_rmse_mps2']].mean().to_string())
