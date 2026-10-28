"""Read only TRAIN cache archive member names, without loading numeric arrays."""
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

import pandas as pd

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
ARCHIVE=ROOT.parent/'REFERENCE_FIX_FULL72_20261021_022342_313'
INDEX=ARCHIVE/'corrected_reference_training_v1/corrected_pair_training/manifests/PAIR_TRAINING_INPUT_INDEX.csv'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


index_sha=sha(INDEX)
index=pd.read_csv(INDEX)
train=index.loc[index.split.str.lower().eq('train')].copy()
assert len(train)==1536 and train.run_id.nunique()==1536
rows=[]
schemas=set()
for record in train.to_dict('records'):
    p=Path(record['cache_path']).resolve()
    assert any(p.is_relative_to(base.resolve()) for base in (ARCHIVE,ROOT)), f'Cache outside declared project inputs: {p}'
    stat0=(p.stat().st_size,p.stat().st_mtime_ns)
    assert sha(p)==record['cache_sha256']
    with ZipFile(p,'r') as z:
        names=tuple(sorted(Path(n).stem for n in z.namelist()))
    schemas.add(names)
    assert (p.stat().st_size,p.stat().st_mtime_ns)==stat0
    rows.append({'run_id':record['run_id'],'task':record['task'],'wind_cell':record['wind_cell'],
                 'role':record['role'],'cache_sha256':record['cache_sha256'],
                 'rf_explicit':any(n in names for n in ('r_f','rf','pcf_r_f','stage1_position_pcf_r_f_mps2')),
                 'a_req_explicit':any(n in names for n in ('a_req','a_requested','stage1_position_pcf_a_req_mps2')),
                 'a_f_explicit':any(n in names for n in ('a_f','a_filtered','stage1_position_pcf_a_f_mps2')),
                 'eta_present':'eta' in names,'source_unchanged':True})
assert sha(INDEX)==index_sha
pd.DataFrame(rows).to_csv(OUT/'training_cache_field_availability.csv',index=False)
meta={'status':'PASS_TRAIN_ONLY_MEMBER_NAME_AUDIT','index_sha256':index_sha,'TRAIN_caches':len(rows),
      'unique_schemas':[list(x) for x in sorted(schemas)],'explicit_rf_count':sum(r['rf_explicit'] for r in rows),
      'explicit_a_req_count':sum(r['a_req_explicit'] for r in rows),'explicit_a_f_count':sum(r['a_f_explicit'] for r in rows),
      'numeric_arrays_loaded':False,'TEST_accessed':False,'raw_MAT_read':False,'optimizer_steps':0,'plant_calls':0,
      'script_sha256':sha(Path(__file__)),
      'limitation':'Only explicit stored field names were checked. Event-sampled eta is not an exact pointwise r_f; no claim is made here about raw-MAT availability or possible reconstruction from other records.'}
(OUT/'training_cache_field_availability.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps(meta,ensure_ascii=False))
