"""Read-only comparison of available historical B cfg snapshots to frozen C3."""
import hashlib
import importlib.util
import json
from pathlib import Path

import h5py

here = Path(__file__).resolve().parent
root = here.parents[1]
helper = root / 'reports/c2_comparator_config_audit_20261023/audit_b_on1_records.py'
spec = importlib.util.spec_from_file_location('reviewed_cfg_decoder', helper)
decoder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(decoder)
snapshot = root / 'experiments/position_delayed_prediction_c3_20261023/C3_PREPARED_CONFIG_OPTS.mat'
assert hashlib.sha256(snapshot.read_bytes()).hexdigest() == '71c95e5cb9cc537fcc1fc2ea82f86c78c0f3f624de4de7a00951127950d4a64e'
with h5py.File(snapshot, 'r') as file:
    frozen = decoder.decode_h5_value(file, file['cfg'])
assert 'value_omitted' not in json.dumps(frozen) and '<MAX_DEPTH>' not in json.dumps(frozen)
out = here / 'PARENT_AVAILABLE_B_CFG_REVIEW.json'
assert not out.exists(), 'Preserve earlier evidence'
rows = []
for item in json.loads((here / 'PARENT_HISTORICAL_216_MANIFEST.json').read_text())['rows']:
    if item['method'] != 'B':
        continue
    path = Path(item['path'])
    before = path.stat()
    with h5py.File(path, 'r') as file:
        present = 'cfg' in file
        actual = decoder.decode_h5_value(file, file['cfg']) if present else None
        if present:
            assert actual == frozen, item['scene_id']
    after = path.stat()
    assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
    rows.append(dict(scene_id=item['scene_id'], path=item['path'], raw_sha256=item['sha256'],
                     cfg_present=present, cfg_matches_frozen_C3=present if present else None))
result = dict(status='PASS_AVAILABLE_CFG_ONLY_MISSING_SNAPSHOTS_DISCLOSED',
              available_cfg_count=sum(r['cfg_present'] for r in rows),
              missing_cfg_count=sum(not r['cfg_present'] for r in rows), rows=rows,
              decoder_path=str(helper), decoder_sha256=hashlib.sha256(helper.read_bytes()).hexdigest(),
              limitation='Matching available cfg does not prove missing per-run cfg or runtime-source provenance.',
              new_Plant=0, TEST_accessed=False)
out.write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps({k: v for k, v in result.items() if k not in ('rows', 'decoder_path', 'decoder_sha256')}))
