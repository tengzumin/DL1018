"""Root read-only first teacher telemetry check; no simulation or training."""
from pathlib import Path
import hashlib,json
import h5py
import numpy as np
root=Path.cwd()
base=root/'reports/attitude_position_context_probe_20261024/c5_matched_train24_v1'
p=base/'runs/DL1018_TRAIN_T1_C00_W00/attempt_01/raw_run.mat'
s=json.loads((p.parent/'run_status.json').read_text(encoding='utf-8-sig'))
sha=hashlib.sha256(p.read_bytes()).hexdigest()
assert sha==s['raw_sha256'] and s['status']=='RUN_COMPLETE_STABLE'
assert s['safety_stop_reason']=='' and s['plant_calls']==1
with h5py.File(p,'r') as f:
    g=f['log']; a=g['rbf_event_audit']
    count=int(np.array(g['rbf_event_count']).item())
    updates=int(np.array(g['rbf_update_flag']).sum())
    times=np.array(a['time']).ravel()
    w0=np.array(a['weight_before'])[0]
    assert count==updates==1999
    assert np.array(g['state']).shape==(12,20001)
    assert times.shape==(8,) and np.max(np.abs(times-np.arange(1,9)*.01))<1e-12
    assert np.all(w0==0)
out=base/'ROOT_FIRST_RAW_TELEMETRY_PREFLIGHT_v1.json'
assert not out.exists()
r={'schema':'ROOT_FIRST_RAW_TELEMETRY_PREFLIGHT_V1','status':'PASS','raw_sha256':sha,'event_count':count,'update_count':updates,'stored_audit_events':len(times),'first_event_time_s':float(times[0]),'initial_rbf_weight_max_abs':float(np.abs(w0).max()),'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'scope':'Independent raw telemetry and integrity only; not target-label correctness or full runtime history reset audit.','Plant_calls':0,'optimizer_steps':0,'TEST_accessed':False}
out.write_text(json.dumps(r,indent=2),encoding='utf-8')
print(json.dumps(r))
