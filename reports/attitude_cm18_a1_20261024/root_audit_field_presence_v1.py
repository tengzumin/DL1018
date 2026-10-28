from pathlib import Path
import h5py,re
p=Path('experiments/attitude_cm18_a1_20261024/first_flight_preparation_v1/audit_a1_first_flight_v1.m');s=p.read_text(encoding='utf-8-sig');req=re.findall(r"'([^']+)'",s.split('requiredLog={',1)[1].split('};',1)[0]);
with h5py.File('experiments/attitude_cm18_a1_20261024/first_flight_preparation_v1/runs/DL1018_DEV_T1_C01_W15/attempt_01/raw_run.mat') as f:
 print('Missing required fields:',[k for k in req if k not in f['log']])
 for k in req:
  if k in f['log'] and isinstance(f['log'][k],h5py.Dataset): print(k,f['log'][k].shape)
