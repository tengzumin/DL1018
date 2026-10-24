"""Read only named external scene arrays; never read old metrics or log/state."""
from pathlib import Path
import json, hashlib
import h5py
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FIELDS = ('time', 'initial_state', 'reference/position', 'reference/velocity',
          'reference/acceleration', 'reference/yaw', 'reference/yaw_rate',
          'reference/yaw_acceleration', 'arms/command', 'arms/rho_true',
          'arms/rhoDot_true', 'environment_wind_I')
def sha(p):
    with Path(p).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()
def arrays(group):
    return {k: np.asarray(group[k]) for k in FIELDS}
def main():
    report = json.loads((HERE/'HISTORICAL_TEST_OVERLAP_METADATA_v1.json').read_text(encoding='utf-8-sig'))
    shared = ROOT/report['current_inputs']['shared_scene_mat']
    assert sha(shared) == report['current_inputs']['shared_scene_mat_sha256']
    with h5py.File(shared, 'r') as h:
        refs = np.asarray(h['scenePacks']).ravel()
        assert len(refs) == 48
        current = [arrays(h[ref]['scene']) for ref in refs]
    rows = []
    for source in report['old_sources']:
        for role, key, group, hash_key in (
            ('config','config_mat','s','config_file_sha256'),
            ('executed','executed_run_start_mat','scene','run_start_file_sha256')):
            p = Path(source[key]); assert sha(p) == source[hash_key]
            with h5py.File(p, 'r') as h:
                old = arrays(h[group])
            counts = {k: 0 for k in FIELDS}; matches = []
            for n, scene in enumerate(current):
                equal = {k: old[k].shape == scene[k].shape and old[k].dtype == scene[k].dtype
                         and np.array_equal(old[k], scene[k]) for k in FIELDS}
                for k, value in equal.items():
                    counts[k] += int(value)
                if all(equal.values()):
                    matches.append(n)
            assert not matches
            assert all(counts[k] == 0 for k in ('reference/position','reference/velocity',
                       'reference/acceleration','environment_wind_I','arms/command',
                       'arms/rho_true','arms/rhoDot_true'))
            rows.append(dict(scene_id=source['scene_id'], source_role=role,
                             matching_current_indices=matches, per_field_match_counts=counts))
    out = HERE/'PARENT_EXTERNAL_OVERLAP_REVIEW_v1.json'; assert not out.exists()
    result = dict(status='PASS_NO_COMPLETE_EXTERNAL_MATCH_OLD_TWO_SCENES_TO_CURRENT48',
                  old_source_instances=4, current_scenes=48, common_fields=12,
                  comparisons=2304, rows=rows, historical_exposure_erased=False,
                  scope='These two identified config/executed inputs only; not every historical scene.',
                  old_missing_fields=['arms/rho_hat','arms/rhoDot_hat'],
                  old_scores_read=False, Plant_calls=0, script_sha256=sha(Path(__file__)))
    out.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(result['status'])
if __name__ == '__main__':
    main()
