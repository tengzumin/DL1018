"""Independent hand oracle and fixture preparation, without fitting or rollouts."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--expected-model-sha', required=True)
    args = ap.parse_args()
    here = Path(__file__).resolve().parent
    root = here.parents[2]
    source = root / 'experiments/attitude_cm18_a1_20261024/model_cm18_v1.py'
    assert sha(source) == args.expected_model_sha.lower()
    names = ['ROOT_RANDOM_FIXTURE_v1.json', 'ROOT_Z_BASIS_FIXTURE_v1.json',
             'ROOT_U_BASIS_FIXTURE_v1.json', 'ROOT_PYTHON_MODEL_CHECK_v1.json']
    assert not any((here / n).exists() for n in names), 'Refuse to overwrite audit outputs'
    spec = importlib.util.spec_from_file_location('cm18_reviewed', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    p = module.initialize_random_parameters(17, np.linspace(-.25, .25, 18), np.ones(18), [1., 2., 3.])
    for key in ['W1', 'b1', 'W2', 'b2', 'W3']:
        p[key][:] = 0
    p['b3'] = np.arange(1., 25.)
    coefficients = np.arange(1., 25.).reshape(3, 8)
    xz, xu, x0 = np.zeros(18), np.zeros(18), np.zeros(18)
    xz[11] = 2.  # z_1/2 = 1: first coefficient column.
    xu[7] = 1.   # u_1 = 1: fifth coefficient column.
    expected = np.array([[1., 18., 51.], [5., 26., 63.], [0., 0., 0.]])
    got = module.forward(np.stack([xz, xu, x0]), p)
    assert np.array_equal(got['physical_output_rad_s2'], expected)
    assert np.array_equal(got['coefficients_3x8'], np.repeat(coefficients[None], 3, axis=0))
    assert sum(p[k].size for k in ['W1', 'b1', 'W2', 'b2', 'W3', 'b3']) == 2456
    module.write_parity_fixture(here / names[0])
    for name, x, basis, normalized, physical in [
        (names[1], xz, [1,0,0,0,0,0,0,0], [1,9,17], [1,18,51]),
        (names[2], xu, [0,0,0,0,1,0,0,0], [5,13,21], [5,26,63])]:
        fixture = {'schema': 'CM18_A1_PARITY_FIXTURE_V1', 'raw_features': x.tolist(),
                   'zero_basis_features': x0.tolist(), 'parameters': {k: v.tolist() for k,v in p.items()},
                   'expected': {'coefficients_3x8': coefficients.tolist(), 'basis_8': basis,
                                'normalized_output': normalized, 'physical_output_rad_s2': physical,
                                'zero_physical_output_rad_s2': [0,0,0]}, 'tolerance_abs': 1e-11}
        with (here / name).open('x', encoding='utf-8') as f:
            json.dump(fixture, f, indent=2, allow_nan=False)
    result = {'schema': 'ROOT_CM18_PYTHON_ORACLE_V1', 'status': 'PASS',
              'model_sha256': sha(source), 'audit_script_sha256': sha(Path(__file__)),
              'hand_oracle': 'Constant coefficient rows 1..8,9..16,17..24; z1/2 and u1 select columns 1 and 5.',
              'batch_physical_output': got['physical_output_rad_s2'].tolist(),
              'trainable_parameters': 2456, 'optimizer_steps': 0, 'new_rollouts': 0,
              'fixtures': [{'path': str(here/n), 'sha256': sha(here/n)} for n in names[:3]]}
    with (here / names[3]).open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
