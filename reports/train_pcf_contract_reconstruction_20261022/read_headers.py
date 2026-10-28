import csv
from pathlib import Path
root=Path.cwd(); archive=root.parent/'REFERENCE_FIX_FULL72_20261021_022342_313'/'corrected_reference_training_v1'
for p in [archive/'g3_collection/reports/G3_D4_CACHE_INDEX_1632.csv',root/'reports/hf_w15_reinvestigation_20261022/training_raw_availability.csv']:
 with p.open(encoding='utf-8-sig',newline='') as f:
  r=csv.DictReader(f); print(p.name,r.fieldnames); print(next(r))
