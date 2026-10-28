import pathlib,json,numpy as np,h5py
from scipy.signal import welch,csd,coherence
root=pathlib.Path.cwd();rep=root/'reports/attitude_cm18_a1_20261024';m=json.loads((rep/'CM18_A1_DEV_SCREEN12_v1.json').read_text(encoding='utf-8-sig'));rows=[]
for r in m['scenes']:
 if 'C15' not in r['scene_id']:continue
 sid=r['scene_id'];p=root/'experiments/attitude_cm18_a1_20261024/screen12_remaining_v1/runs'/sid/'attempt_01/raw_run.mat'
 for method,path in [('CM18_A1',p),('C5_RBF',pathlib.Path(r['baseline_C5_raw_path']))]:
  with h5py.File(path) as f:
   g=f['log'];t=np.asarray(g['transition_time']).reshape(-1);x=np.asarray(g['state']).T[:-1];ref=np.asarray(g['filtered_attitude_reference']).T;err=np.arctan2(np.sin(ref[:,2]-x[:,8]),np.cos(ref[:,2]-x[:,8]));comp=np.asarray(g['attitude_compensation_applied_torque_Nm']).T;nom=np.asarray(g['attitude_bs_nominal_torque_Nm']).T;mask=(t>=5)&(t<15);signals={'yaw_error_rad':err[mask],'comp_torque_yaw_Nm':comp[mask,2],'nominal_torque_yaw_Nm':nom[mask,2]}
   metrics={}
   for name,a in signals.items():
    freq,psd=welch(a,fs=1000,nperseg=4096);sel=(freq>.25)&(freq<40);peak=np.flatnonzero(sel)[np.argmax(psd[sel])];metrics[name]=dict(rms=float(np.sqrt(np.mean(a*a))),peak_frequency_Hz=float(freq[peak]),fraction_power_above10Hz=float(np.sum(psd[freq>10])/np.sum(psd)) if psd.sum()>0 else 0)
  rows.append(dict(scene_id=sid,method=method,period='5<=t<15; Welch nperseg4096,fs1000Hz; peak search(.25,40)Hz',signals=metrics))
p=rep/'ROOT_C15_TEMPORAL_SPECTRUM_v1.json';assert not p.exists();p.write_text(json.dumps(dict(scope='Descriptive recorded closed-loop spectra; not a component causal or stability proof',rows=rows),indent=2));print(json.dumps(rows,indent=2))
