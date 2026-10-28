"""Check actual replay scene payload against every historical B scored log."""
import hashlib
import json
from pathlib import Path

import h5py
import numpy as np

here = Path(__file__).resolve().parent
manifest = here / 'PARENT_HISTORICAL_216_MANIFEST.json'
out = here / 'PARENT_B72_SCENE_PAYLOAD_REVIEW.json'
assert not out.exists(), 'Preserve earlier evidence'
rows = []
for item in json.loads(manifest.read_text())['rows']:
    if item['method'] != 'B':
        continue
    path = Path(item['path'])
    before = path.stat()
    with path.open('rb') as stream:
        assert hashlib.file_digest(stream, 'sha256').hexdigest() == item['sha256']
    with h5py.File(path, 'r') as file:
        assert 'scene' in file
        keys = ['initial_state', 'time', 'environment_wind_I']
        keys += ['arms/' + k for k in ('command', 'rho_true', 'rhoDot_true', 'rho_hat', 'rhoDot_hat')]
        keys += ['reference/' + k for k in file['scene/reference']]
        for key in keys:
            a, b = np.asarray(file['scene/' + key]), np.asarray(file['log/' + key])
            assert a.dtype == b.dtype and np.array_equal(a, b), (item['scene_id'], key)
    after = path.stat()
    assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
    rows.append(dict(scene_id=item['scene_id'], path=item['path'], sha256=item['sha256'], matching_fields=keys))
assert len(rows) == 72
out.write_text(json.dumps(dict(status='PASS_ALL72_REPLAY_SCENE_EQUALS_SCORED_B_INPUTS',
                              rows=rows, new_Plant=0, TEST_accessed=False), indent=2), encoding='utf-8')
print(json.dumps(dict(status='PASS', scene_count=len(rows), fields_per_scene=len(rows[0]['matching_fields']))))
