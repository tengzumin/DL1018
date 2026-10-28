"""Independent TRAIN-only label scale under the frozen hierarchical objective.

This measures a zero predictor's analytical loss, not trained-model loss,
gradients, a new fit, or closed-loop performance.
"""
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
ARCHIVE=ROOT.parent/'REFERENCE_FIX_FULL72_20261021_022342_313'
INDEX=ARCHIVE/'corrected_reference_training_v1/corrected_pair_training/manifests/PAIR_TRAINING_INPUT_INDEX.csv'


def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(4<<20),b''):h.update(b)
    return h.hexdigest()


assert sha(INDEX)=='257089f1dc455b7bc97bf1c772be31d1d8ae83079e7ec41f591d96e31fed39ca'
index=pd.read_csv(INDEX)
train=index[index.split.str.lower().eq('train')]
assert len(train)==1536 and train.run_id.is_unique
scene_counts=train.groupby(['role','task','class_index']).size().to_dict()
ends=np.arange(31,1999,5)
assert len(ends)==394
rows=[]
for rec in train.to_dict('records'):
    p=Path(rec['cache_path']).resolve()
    assert any(p.is_relative_to(x.resolve()) for x in (ROOT,ARCHIVE))
    st=(p.stat().st_size,p.stat().st_mtime_ns)
    assert sha(p)==rec['cache_sha256']
    with np.load(p,allow_pickle=False) as z:
        y=np.asarray(z['y'],dtype=float)[ends]
        raw=np.asarray(z['raw'],dtype=float)[ends]
        phase=np.asarray(z['phase'])[ends]
    assert np.isfinite(y).all() and np.isfinite(raw).all()
    assert np.array_equal(y,np.clip(raw,-3,3))
    labels,counts=np.unique(phase,return_counts=True)
    per_phase=dict(zip(labels,counts))
    base=.5/(3*16*scene_counts[(rec['role'],rec['task'],rec['class_index'])]*len(labels))
    weights=np.array([base/per_phase[x] for x in phase])
    for axis,label in enumerate('xyz'):
        rows.append({'run_id':rec['run_id'],'task':rec['task'],'role':rec['role'],'class_index':rec['class_index'],
                     'wind_cell':rec['wind_cell'],'axis':label,'window_count':394,'window_mass':float(weights.sum()),
                     'weighted_raw_target_power_m2s4':float(np.average(raw[:,axis]**2,weights=weights)),
                     'zero_predictor_axis_loss_contribution':float(np.sum(weights*y[:,axis]**2)/54),
                     'target_clip_fraction':float(np.mean(np.abs(raw[:,axis])>3))})
    assert st==(p.stat().st_size,p.stat().st_mtime_ns) and sha(p)==rec['cache_sha256']
d=pd.DataFrame(rows)
assert abs(d[d.axis.eq('x')].window_mass.sum()-1)<1e-10
d.to_csv(OUT/'zero_predictor_loss_by_episode_axis.csv',index=False)
g=d.groupby('wind_cell').agg(episode_axis_rows=('run_id','size'),window_mass_sum_three_axes=('window_mass','sum'),
                            zero_predictor_loss_contribution=('zero_predictor_axis_loss_contribution','sum')).reset_index()
g['window_mass']=g.window_mass_sum_three_axes/3
g['loss_share']=g.zero_predictor_loss_contribution/g.zero_predictor_loss_contribution.sum()
g.to_csv(OUT/'zero_predictor_loss_by_wind.csv',index=False)
meta={'status':'PASS_TRAIN_ZERO_PREDICTOR_LOSS_SCALE_AUDIT','TRAIN_episodes':1536,'windows':1536*394,
      'formula':'SmoothL1(0,y_clip/3), averaged across 3 axes; because abs(y_clip/3)<=1, each axis contributes y_clip^2/54.',
      'sample_weights':'Original role/task/class/scene/present-phase hierarchy, evaluated in double arithmetic; not a bitwise replay of Torch training.',
      'zero_predictor_total_loss':float(g.zero_predictor_loss_contribution.sum()),'script_sha256':sha(Path(__file__)),
      'index_sha256':sha(INDEX),'all_cache_sha_and_stat_unchanged':True,'optimizer_steps':0,'plant_calls':0,'TEST_accessed':False,
      'limitation':'Zero-predictor objective scale is not trained loss, gradient importance, evidence of a weighting bug, or proof of closed-loop causality.'}
(OUT/'zero_predictor_loss_metadata.json').write_text(json.dumps(meta,indent=2)+'\n',encoding='utf8')
print(g.to_string(index=False))
