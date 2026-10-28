"""Extract only causal attitude teacher fields from the explicit C5 TRAIN/VAL cohort."""
import csv
import hashlib
import json
import sys
from pathlib import Path
import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
EXT = ROOT.parent / 'REFERENCE_FIX_FULL72_20261021_022342_313/corrected_reference_training_v1'
COHORT = EXT / 'g3_collection/manifests/G3_COHORT_1632.csv'
OUT = Path(__file__).parent / 'large_attitude_data_root_v1'
B_ONLY = '--b-only' in sys.argv
if B_ONLY:
    OUT = Path(__file__).parent / 'large_attitude_b768_root_v1'

def main():
    OUT.mkdir(exist_ok=True)
    assert not (OUT/'DATASET.npz').exists(), 'Refuse overwrite'
    rows = list(csv.DictReader(COHORT.open(encoding='utf-8-sig', newline='')))
    assert len(rows)==1632 and {r['split'] for r in rows}=={'TRAIN','VAL'}
    physical = {s:{r['source_scene_id'] for r in rows if r['split']==s} for s in ['TRAIN','VAL']}
    assert not physical['TRAIN'] & physical['VAL']
    arrays, records = {}, []
    for split, count in [('TRAIN',768 if B_ONLY else 1536),('VAL',48 if B_ONLY else 96)]:
        subset = [r for r in rows if r['split']==split and (not B_ONLY or r['role']=='B')]
        assert len(subset)==count
        prefix=split.lower(); xs=[]; ys=[]
        for i,r in enumerate(subset):
            assert r['g3_action'] in {'RUN_PLANT','PILOT6_IMPORT','REUSE_HS_ACCEPTED','REUSE_FULL72_B_REBUILD_D2_D4'}
            source_key='g3_raw_path' if r['g3_action']=='RUN_PLANT' else 'raw_source_path'
            p=Path(r[source_key])
            assert p.is_file(), ('Missing action-bound raw',r['planned_run_id'],p)
            assert 'test' not in str(p).lower()
            with h5py.File(p) as f:
                g=f['log']; ev=np.flatnonzero(g['attitude_event_flag'][()].reshape(-1))
                t=g['transition_time'][()].reshape(-1)
                assert len(ev)==1999 and np.max(abs(t[ev]-np.arange(1,2000)*.01))<1e-10
                state=g['state'][()].T; ref=g['filtered_attitude_reference'][()].T
                e=ref[ev]-state[ev,6:9]
                x=np.concatenate([np.arctan2(np.sin(e),np.cos(e)),state[ev,9:12],g['attitude_bs_nominal_torque_Nm'][()].T[ev],f['scene/arms/command'][()].T[ev]],axis=1)
                y=g['rbf_output_raw'][()].T[ev]
                assert np.all(g['rbf_update_flag'][()].reshape(-1)[ev]==1)
                assert x.shape==(1999,13) and y.shape==(1999,3)
                assert np.isfinite(x).all() and np.isfinite(y).all()
            xs.append(x.astype('float32'));ys.append(y.astype('float32'))
            records.append({'episode_id':r['planned_run_id'],'scene_id':r['source_scene_id'],'split':split,'role':r['role'],'task':r['task'],'raw_path':str(p),'selected_xy_sha256':hashlib.sha256(xs[-1].tobytes()+ys[-1].tobytes()).hexdigest()})
            if (i+1)%32==0 or i+1==count:
                (OUT/'PROGRESS.json').write_text(json.dumps({'split':split,'completed':i+1,'expected':count}))
                print(split,i+1,'/',count,flush=True)
        arrays[prefix+'_x']=np.stack(xs);arrays[prefix+'_y']=np.stack(ys)
        for key,col in [('ids','planned_run_id'),('scene_ids','source_scene_id'),('role_ids','role'),('task_ids','task')]:
            arrays[prefix+'_'+key]=np.asarray([r[col] for r in subset])
        assert len(set(arrays[prefix+'_ids']))==count
    np.savez_compressed(OUT/'DATASET.npz',**arrays)
    manifest={'status':'EXTRACTED_PENDING_INDEPENDENT_UNIT_AND_PROVENANCE_AUDIT','cohort_path':str(COHORT),'cohort_sha256':hashlib.sha256(COHORT.read_bytes()).hexdigest(),'features':['wrapped_attitude_error_rad_x3','body_rate_rad_s_x3','nominal_torque_Nm_x3','morph_command_x4'],'target':'rbf_output_raw; rad/s^2; post-limit/pre-beta; contract audit pending','raw_full_hash_verified':False,'TEST_read':False,'inertia_fields_read':False,'normalizer_fitted':False,'records':records}
    manifest['cohort_policy']='B-only: all independent physical scenes, TRAIN768/VAL48; missing POS_OFF not substituted' if B_ONLY else 'Full B+POS_OFF TRAIN1536/VAL96'
    (OUT/'DATASET_MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('EXTRACTION_COMPLETE',OUT,flush=True)

if __name__=='__main__':
    main()
