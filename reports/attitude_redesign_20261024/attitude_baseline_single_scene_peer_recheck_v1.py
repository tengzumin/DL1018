import hashlib, json
from pathlib import Path
import h5py
import numpy as np
from scipy.spatial.transform import Rotation

ROOT = Path(r'C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018')
RAW = ROOT / r'experiments\position_axis_coordinate_c5_dev72_20261023\runs_dev72_v3\DL1018_DEV_T1_C01_W15\C5_AXIS_MASK_M110\attempt_01\raw_run.mat'
OUT = ROOT / r'reports\attitude_redesign_20261024\ATTITUDE_BASELINE_SINGLE_SCENE_PEER_RECHECK_v1.json'
EXPECTED_SHA = 'b61f01ab5920de766b8596512490b596e3959fa87368cd40a3b30758831fe651'

def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(1<<20),b''):
            h.update(block)
    return h.hexdigest()

raw_sha=digest(RAW)
assert raw_sha==EXPECTED_SHA, (raw_sha, EXPECTED_SHA)
with h5py.File(RAW,'r') as f:
    g=f['log']
    x=np.asarray(g['state'][()],dtype=np.float64).T[:-1]
    eta_ref=np.asarray(g['filtered_attitude_reference'][()],dtype=np.float64).T
    eta_rate=np.asarray(g['filtered_attitude_rate'][()],dtype=np.float64).T
    time=np.asarray(g['time'][()],dtype=np.float64).reshape(-1)[:-1]
assert x.shape==(20000,12) and eta_ref.shape==eta_rate.shape==(20000,3) and time.shape==(20000,)
assert np.isfinite(x).all() and np.isfinite(eta_ref).all() and np.isfinite(eta_rate).all()
R=Rotation.from_euler('ZYX',x[:,[8,7,6]])
Rref=Rotation.from_euler('ZYX',eta_ref[:,[2,1,0]])
angle=(R.inv()*Rref).magnitude()
phi,theta=eta_ref[:,0],eta_ref[:,1]
a,b,c=eta_rate.T
omega_ref=np.column_stack((a-np.sin(theta)*c,
                           np.cos(phi)*b+np.sin(phi)*np.cos(theta)*c,
                           -np.sin(phi)*b+np.cos(phi)*np.cos(theta)*c))
transported=(R.inv()*Rref).apply(omega_ref)
rate_err=x[:,9:12]-transported
euler_err=np.arctan2(np.sin(eta_ref-x[:,6:9]),np.cos(eta_ref-x[:,6:9]))
rows=[]
for name,mask in [('ALL',np.ones(time.size,dtype=bool)),('PRE_0_5',time<5),('POST_5',time>=5)]:
    rows.append({'period':name,'n':int(mask.sum()),
      'SO3_RMSE_deg':float(np.rad2deg(np.sqrt(np.mean(angle[mask]**2)))),
      'SO3_peak_deg':float(np.rad2deg(np.max(angle[mask]))),
      'Euler_axis_RMSE_deg':np.rad2deg(np.sqrt(np.mean(euler_err[mask]**2,axis=0))).tolist(),
      'transported_body_rate_RMSE_rads':np.sqrt(np.mean(rate_err[mask]**2,axis=0)).tolist()})
result={'schema':'ATTITUDE_BASELINE_SINGLE_SCENE_PEER_RECHECK_V1',
 'scope':'One selected C5 DEV active-morphology scene only; read-only raw replay, no TEST, fitting, training, runner, integration, or Plant.',
 'scene_id':'DL1018_DEV_T1_C01_W15','raw_path':str(RAW),'raw_sha256':raw_sha,
 'alignment':'first 20,000 transition-left state rows aligned same-row to filtered attitude reference/rate; terminal state excluded.',
 'rotation_error':'geodesic angle of R_actual^T R_ref',
 'body_rate_error':'omega_actual - R_actual^T R_ref omega_ref; omega_ref=T(eta_ref)^-1 eta_rate_ref',
 'metrics':rows}
with OUT.open('x',encoding='utf-8') as f: json.dump(result,f,ensure_ascii=False,indent=2)
print(json.dumps(result,ensure_ascii=False,indent=2))
