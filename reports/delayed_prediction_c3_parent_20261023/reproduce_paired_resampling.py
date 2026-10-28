"""Reproduce the existing descriptive scene-pair bootstrap; no experiments."""
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
SOURCE = HERE / 'PARENT_ALL12_PAIRED.csv'
TARGET = HERE / 'PARENT_WIN_MARGIN_AND_PAIRED_RESAMPLING.json'
rows = list(csv.DictReader(SOURCE.open(encoding='utf-8-sig', newline='')))
assert len(rows) == len({r['scene_id'] for r in rows}) == 12
reported = json.loads(TARGET.read_text(encoding='utf-8'))
max_error = 0.0
for comparator in ('B', 'C2'):
    improvement = np.array([float(r[comparator+'_Q_m'])-float(r['C3_Q_m']) for r in rows])
    rng = np.random.default_rng(2026102001)
    estimates = improvement[rng.integers(0, 12, size=(10000, 12))].mean(axis=1)
    interval = np.quantile(estimates, [.025, .975])
    ref = reported['comparisons'][comparator]
    assert ref['bootstrap_replicates'] == 10000 and ref['bootstrap_seed'] == 2026102001
    assert ref['n_paired_scenes'] == 12 and ref['positive_means_C3_better'] is True
    errors = [abs(float(improvement.mean())-ref['mean_improvement_m'])]
    errors += np.abs(interval-ref['paired_scene_bootstrap_percentile_95_interval_m']).tolist()
    max_error = max(max_error, *errors)
    for label, threshold in [('1e-12_m', 1e-12), ('1_micrometre', 1e-6), ('10_micrometres', 1e-5)]:
        assert int((improvement > threshold).sum()) == ref['wins_by_strict_margin'][label]
assert max_error < 1e-15
result = dict(status='PASS_REPRODUCED_EXISTING_PAIRED_RESAMPLING', max_absolute_error_m=max_error,
              source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
              target_sha256=hashlib.sha256(TARGET.read_bytes()).hexdigest(),
              bootstrap_replicates=10000, bootstrap_seed=2026102001,
              scope='Post-outcome exploratory description of selected scenario pairs; no population, DEV72 or training-seed claim.')
print(json.dumps(result))
