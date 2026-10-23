"""Generate deterministic Python reference fixtures for the C4 MATLAB helper."""
from __future__ import annotations
import hashlib
import importlib.util
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT = HERE / 'C4_CROSSLANG_FIXTURE_v1.json'
KERNEL = ROOT / 'reports/delayed_prediction_proposal_20261023/construction/delayed_prediction_kernel.py'
HELPER = HERE / 'delayed_prediction_step_candidate.m'
TOL = 2e-12

def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def plain(x):
    if isinstance(x, np.ndarray):
        return x.tolist()
    if isinstance(x, (np.floating, np.integer)):
        return x.item()
    if isinstance(x, dict):
        return {k: plain(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [plain(v) for v in x]
    return x

def expected_out(out: dict) -> dict:
    return {key: plain(out[key]) for key in (
        'raw', 'applied', 'beta', 'has_previous', 'previous_raw',
        'previous_residual', 'prediction_gradient', 'preprojection_candidate', 'W_next')}

def main() -> None:
    if OUT.exists():
        raise FileExistsError(f'refusing to overwrite {OUT}')
    spec = importlib.util.spec_from_file_location('delayed_prediction_kernel', KERNEL)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'cannot import {KERNEL}')
    kernel = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(kernel)

    i = np.arange(33, dtype=np.float64)
    W0 = np.column_stack((0.006*np.sin(0.37*(i+1)),
                          0.005*np.cos(0.29*(i+1)),
                          0.004*np.sin(0.17*(i+3))))
    phi320 = np.sin(0.23*(i+1)); phi320 /= np.linalg.norm(phi320)
    phi330 = np.cos(0.19*(i+2)); phi330 /= np.linalg.norm(phi330)
    surfaces = [np.array([8.4, -9.0, 11.0]), np.array([2.2, -2.7, 3.4])]
    etas = [np.array([0.7, -0.5, 1.2]), np.array([0.5, -0.45, 0.8])]
    rows = np.arange(11, dtype=np.float64)
    a_req = np.column_stack((0.21 + 0.004*rows,
                             -0.16 + 0.003*rows,
                             0.07 - 0.002*rows))
    r_f = np.column_stack((0.023 + 0.0003*rows,
                           -0.031 + 0.0002*rows,
                           0.017 - 0.0001*rows))
    a_f = a_req - r_f
    # Row 11 is the transition at n=330; it must not enter target y[320:330].
    a_req[10] = np.array([800.0, -900.0, 1000.0])
    a_f[10] = np.array([-1100.0, 1200.0, -1300.0])
    v_j = np.array([0.12, -0.24, 0.36])
    v_k = np.array([0.134, -0.251, 0.373])
    limits = np.array([7.0, 8.0, 10.0])
    cases = []
    for m in (1, 0):
        s_eff_320 = np.clip(surfaces[0] - m*etas[0], -limits, limits)
        e320 = kernel.delayed_prediction_step(W0, phi320, s_eff_320, 320, 0.320)
        ref_rows = a_f if m == 1 else a_req  # m=1 is the direct legacy a_f path.
        integral = np.zeros(3)
        for q in range(10):
            integral = integral + ref_rows[q] * 0.001
        target = ((v_k - v_j) - integral) / 0.01
        s_eff_330 = np.clip(surfaces[1] - m*etas[1], -limits, limits)
        e330 = kernel.delayed_prediction_step(
            e320['W_next'], phi330, s_eff_330, 330, 0.330,
            phi_prev=phi320, y_prev=target, previous_index=320,
            previous_time_s=0.320)
        wrong_integral = np.zeros(3)
        for q in range(11):
            wrong_integral = wrong_integral + ref_rows[q] * 0.001
        sentinel_target = ((v_k - v_j) - wrong_integral) / 0.01
        cases.append({
            'm': m,
            'events': [
                {'n': 320, 'time_s': 0.320, 'surface': surfaces[0], 'eta_before': etas[0],
                 's_eff': s_eff_320, 'has_previous_input': False,
                 'expected': expected_out(e320)},
                {'n': 330, 'time_s': 0.330, 'surface': surfaces[1], 'eta_before': etas[1],
                 's_eff': s_eff_330, 'has_previous_input': True, 'previous_index': 320,
                 'previous_time_s': 0.320, 'prediction_reference': 'a_f' if m == 1 else 'a_req',
                 'reference_integral_mps': integral, 'target_mps2': target,
                 'sentinel_target_if_current_row_were_wrongly_included_mps2': sentinel_target,
                 'W_input': e320['W_next'], 'expected': expected_out(e330)},
            ],
        })
    assert np.max(np.abs(cases[0]['events'][1]['target_mps2'] -
                         cases[1]['events'][1]['target_mps2'])) > 1e-3
    fixture = {
        'schema': 'C4_CROSSLANG_SYNTHETIC_FIXTURE_V1',
        'tolerance_abs': TOL,
        'plant_dt_s': 0.001,
        'event_period_s': 0.01,
        'W0': W0,
        'phi_320': phi320,
        'phi_330': phi330,
        'a_req_rows_n320_to_n330_N11_by_3': a_req,
        'a_f_rows_n320_to_n330_N11_by_3': a_f,
        'r_f_rows_n320_to_n330_N11_by_3': a_req - a_f,
        'v_320_mps': v_j,
        'v_330_mps': v_k,
        'cases': cases,
        'python_kernel_path': str(KERNEL.resolve()),
        'python_kernel_sha256': digest(KERNEL),
        'matlab_helper_sha256': digest(HELPER),
        'provenance': 'synthetic arrays only; no Plant, raw MAT, model checkpoint, training, or TEST',
    }
    OUT.write_text(json.dumps(plain(fixture), indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'status': 'FIXTURE_GENERATED', 'path': str(OUT.resolve()),
                      'sha256': digest(OUT), 'kernel_sha256': digest(KERNEL),
                      'helper_sha256': digest(HELPER), 'events': 4, 'transition_rows': 11}, indent=2))

if __name__ == '__main__':
    main()
