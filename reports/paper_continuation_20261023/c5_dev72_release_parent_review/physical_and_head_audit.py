"""Additional physical/learned saturation observations from already audited raws."""
import argparse
import hashlib
import json
from pathlib import Path

import h5py
import numpy as np


def audit(source, output):
    assert not output.exists()
    data=json.loads(source.read_text(encoding='utf-8-sig'))
    assert data['scene_count']==72 and data['matlab_os_exit_code']==0 and not data['TEST_accessed']
    rows=[]
    for row in data['rows']:
        for method in ('B','C3','C5'):
            item=row[method+'_metrics'];path=Path(item['path'])
            with path.open('rb') as raw:
                assert hashlib.file_digest(raw,'sha256').hexdigest()==item['sha256']
            with h5py.File(path,'r') as f:
                g=f['log']
                def read(key):
                    x=np.asarray(g[key])
                    return x.T if x.ndim==2 else x
                state=read('state')
                assert state.shape==(20001,12) and np.isfinite(state).all()
                r=dict(scene_id=row['scene_id'],method=method,path=str(path),sha256=item['sha256'],
                       max_actual_tilt_rad=float(np.linalg.norm(state[:,6:8],axis=1).max()),
                       max_actual_body_rate_norm_rad_s=float(np.linalg.norm(state[:,9:12],axis=1).max()))
                for key in ('tilt_limited','motor_saturated','generalized_clipped'):
                    x=read(key)
                    assert x.shape[0]==20000 and np.isfinite(x).all()
                    r[key+'_fraction']=float(np.mean(np.any(x.reshape(20000,-1)!=0,axis=1)))
                for key in ('requested_generalized','controller_clipped_generalized','allocated_generalized','realized_generalized'):
                    x=read(key)
                    assert x.shape[0]==20000 and np.isfinite(x).all(),key
                if method=='C5':
                    ids=np.flatnonzero(read('stage1_position_event_inference_valid').ravel())
                    assert np.array_equal(ids,np.arange(320,19991,10))
                    raw=read('stage1_position_event_raw_acceleration_mps2')[ids]
                    surface=read('stage1_position_pcf_event_s_coord_mps')[ids]
                    r.update(head_output_clip_events=int(np.any(abs(raw)>3,axis=1).sum()),
                             tracking_surface_clip_events=int(np.any(abs(surface)>[7,8,10],axis=1).sum()),
                             max_abs_raw_head_mps2=float(abs(raw).max()),
                             max_abs_coordinated_surface_mps=float(abs(surface).max()),
                             event_count=len(ids))
                rows.append(r)
    payload=dict(status='PASS_EXTRA_PHYSICAL_ARRAY_CHECKS_OBSERVATIONS_ONLY',rows=rows,
                 scope='DEV72; peak values and clip fractions are observations, not an invariant-domain proof',
                 TEST_accessed=False,new_Plant=0,
                 source=dict(path=str(source.resolve()),sha256=hashlib.sha256(source.read_bytes()).hexdigest()),
                 script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    with output.open('x',encoding='utf-8') as f:
        json.dump(payload,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
    c5=[r for r in rows if r['method']=='C5']
    print(json.dumps(dict(status=payload['status'],raw_count=len(rows),
                         C5_head_clip_events=sum(r['head_output_clip_events'] for r in c5),
                         C5_surface_clip_events=sum(r['tracking_surface_clip_events'] for r in c5))))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    audit(args.source,args.output)
