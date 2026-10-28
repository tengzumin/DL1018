"""Exact index join and path availability only; does not open raw MATs."""
import json
from pathlib import Path
import pandas as pd
from audit_target_contract import sha

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
ARCHIVE=ROOT.parent/'REFERENCE_FIX_FULL72_20261021_022342_313'
BASE=ARCHIVE/'corrected_reference_training_v1'
train_index=BASE/'corrected_pair_training/manifests/PAIR_TRAINING_INPUT_INDEX.csv'
raw_index=BASE/'g3_collection/reports/G3_D4_CACHE_INDEX_1632.csv'
hashes={str(p):sha(p) for p in (train_index,raw_index)}
assert hashes[str(train_index)]=='257089f1dc455b7bc97bf1c772be31d1d8ae83079e7ec41f591d96e31fed39ca'
t=pd.read_csv(train_index)
t=t[t.split.str.lower().eq('train')]
r=pd.read_csv(raw_index)
r=r[r.split.str.upper().eq('TRAIN')]
assert len(t)==len(r)==1536 and t.run_id.is_unique and r.run_id.is_unique
joined=t.merge(r,on='run_id',suffixes=('_train','_source'),validate='one_to_one')
for name in ('raw_sha256','event_h5_sha256','cache_sha256'):
    assert joined[name+'_train'].eq(joined[name+'_source']).all()
rows=[]
for rec in joined.to_dict('records'):
    row={'run_id':rec['run_id'],'task':rec['task_train'],'wind_cell':rec['wind_cell'],'role':rec['role_train']}
    for kind in ('raw','run_start','event_h5'):
        p=Path(rec[kind+'_path']).resolve()
        assert any(p.is_relative_to(base.resolve()) for base in (ROOT,ARCHIVE)),p
        row[kind+'_path']=str(p)
        row[kind+'_exists']=p.is_file()
        row[kind+'_bytes']=p.stat().st_size if p.is_file() else 0
    rows.append(row)
df=pd.DataFrame(rows)
df.to_csv(OUT/'training_raw_availability.csv',index=False)
assert all(sha(Path(p))==h for p,h in hashes.items())
meta={'status':'PASS_TRAIN_INDEX_AVAILABILITY_AUDIT','TRAIN_episodes':1536,
      'index_join_identities_match':True,'index_sha256':hashes,'script_sha256':sha(Path(__file__)),
      'available_files':{k:int(df[k+'_exists'].sum()) for k in ('raw','run_start','event_h5')},
      'available_raw_GiB':float(df.raw_bytes.sum()/1024**3),'raw_MAT_opened':False,'TEST_accessed':False,
      'scope':'Existence and size do not verify content, source execution identity, or PCF field sufficiency.'}
(OUT/'training_raw_availability.json').write_text(json.dumps(meta,indent=2)+'\n',encoding='utf8')
print(json.dumps(meta))
