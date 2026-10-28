"""Compare saved weights on two fixed hosts; no rollout or online updates."""
import argparse
import hashlib
import json
from pathlib import Path

import h5py
import numpy as np


def read(path, expected_sha):
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected_sha
    before = path.stat()
    with h5py.File(path, 'r') as f:
        g = f['log']
        def r(key):
            return np.asarray(g[key]).T
        ids = np.flatnonzero(r('stage1_position_event_inference_valid').ravel())
        assert np.array_equal(ids, np.arange(320, 19991, 10))
        data = dict(ids=ids, phi=r('stage1_position_event_phi_33')[ids],
                    W=np.asarray(g['stage1_position_event_weight_before_33x3']).transpose(0, 2, 1),
                    v=r('state')[:, 3:6], af=r('stage1_position_pcf_a_f_mps2'))
        assert all(np.isfinite(a).all() for a in data.values())
    after = path.stat()
    assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
    return data


def compare(status):
    a = read(Path(status['raw_path']), status['raw_sha256'])
    b = read(Path(status['C2_raw_path']), status['C2_raw_sha256'])
    assert np.array_equal(a['ids'], b['ids'])
    rows = []
    for host, h in [('C2', b), ('C3', a)]:
        ids = h['ids']
        y = np.array([(h['v'][k]-h['v'][j])/.01-h['af'][j:k].mean(0)
                      for j, k in zip(ids[:-1], ids[1:])])
        for method, w in [('C2', b['W']), ('C3', a['W'])]:
            error = np.einsum('nfi,nf->ni', w[1:], h['phi'][:-1])-y
            for phase, lo, hi in [('early', .33, 5), ('late', 5, 20)]:
                mask = (ids[1:]*.001 >= lo) & (ids[1:]*.001 < hi)
                rows.append(dict(host=host, method_weights=method, phase=phase,
                                 n=int(mask.sum()), axis_rmse_mps2=np.sqrt(np.mean(error[mask]**2, axis=0)).tolist()))
    return dict(scene_id=status['scene_id'], rows=rows, new_Plant=0,
                limitation='Local replay of saved weights on fixed host features and interval targets; no counterfactual rollout, causal proof, or independent sample from the second host.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('run_status', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    assert not args.output.exists(), 'Preserve earlier evidence'
    result = compare(json.loads(args.run_status.read_text(encoding='utf-8-sig')))
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf-8')
