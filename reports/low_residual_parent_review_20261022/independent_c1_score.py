"""Primary numerical rescore, independent of the implementation scorer.

Read only the new C1 raw files explicitly supplied on the command line.
Source/options/physical scene identity are separate review gates.
"""
import argparse
import hashlib
import json
from pathlib import Path

import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
RUN_ROOTS = [ROOT / 'experiments/position_prior_calibration_c1_20261022/runs_v8',
             ROOT / 'experiments/position_prior_calibration_c1_20261022_v9/runs_v9']


def fingerprint(path):
    before = path.stat()
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    after = path.stat()
    assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
    return digest, after.st_size, after.st_mtime_ns


def read(log, key):
    a = np.asarray(log[key])
    return a.T if a.ndim >= 2 else a


def text(log, key):
    return ''.join(chr(int(v)) for v in read(log, key).ravel() if v)


def score(path):
    path = path.resolve()
    assert any(path.is_relative_to(root.resolve()) for root in RUN_ROOTS) and path.name == 'raw_run.mat'
    before = fingerprint(path)
    with h5py.File(path, 'r') as f:
        log = f['log']
        t = read(log, 'transition_time').ravel()
        state, ref = read(log, 'state'), read(log, 'reference/position')
        assert len(t) == 20000 and t[0] == 0 and t[-1] == 19.999
        assert np.allclose(t, np.arange(20000) * .001, rtol=0, atol=4e-15)
        assert state.shape[0] == 20001 and state.shape[1] >= 9 and ref.shape == (20001, 3)
        assert np.isfinite(state).all() and np.isfinite(ref).all()
        assert text(log, 'status') == 'STABLE' and not text(log, 'safety_stop_reason')
        assert read(log, 'last_transition').item() == 20000
        ctrl = read(log, 'controller_call_time_s').ravel()
        assert len(ctrl) == 20000 and np.isfinite(ctrl).all() and (ctrl >= 0).all()
        error = ref[:20000] - state[:20000, :3]
        result = {'raw_path': str(path), 'raw_sha256': before[0], 'scene_id': text(log, 'scene_id'),
                  'safe_complete_finite': True}
        for phase, mask in [('0_20', (t >= 0) & (t < 20)),
                            ('0_5', (t >= 0) & (t < 5)), ('5_20', (t >= 5) & (t < 20))]:
            e = error[mask]
            result['Q_' + phase + '_m'] = float(np.sqrt(np.mean(np.sum(e * e, axis=1))))
            result['axis_rmse_' + phase + '_m'] = np.sqrt(np.mean(e * e, axis=0)).tolist()
        norms = np.linalg.norm(error, axis=1)
        result.update(peak_m=float(norms.max()), p95_m=float(np.quantile(norms, .95)),
                      controller_mean_s=float(ctrl.mean()), controller_p95_s=float(np.quantile(ctrl, .95)),
                      controller_max_s=float(ctrl.max()))
        for key in ['motor_saturated', 'generalized_clipped']:
            a = read(log, key)
            assert a.shape[0] == 20000 and np.isfinite(a).all()
            result[key + '_fraction'] = float(np.mean(np.any(a != 0, axis=1)))
    assert fingerprint(path) == before
    return result, ref


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('raws', nargs='+', type=Path)
    args = parser.parse_args()
    assert args.output.resolve().parent == Path(__file__).resolve().parent
    assert not args.output.exists()
    assert len({p.resolve() for p in args.raws}) == len(args.raws), 'Duplicate raw argument'
    scored = [score(p) for p in args.raws]
    references = {}
    for row, ref in scored:
        scene = row['scene_id']
        if scene in references:
            assert np.array_equal(ref, references[scene]), 'Paired reference inputs differ'
        else:
            references[scene] = ref
    result = {'status': 'PASS_PRIMARY_NUMERICAL_RAW_RESCORE',
              'rule': '20000 transitions at [0,20), reference minus state XYZ; no rounding',
              'limitation': 'Explicit input subset only, no full-screen coverage assertion; source/options/physical identity reviewed separately',
              'rows': [s[0] for s in scored]}
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2, allow_nan=False))
