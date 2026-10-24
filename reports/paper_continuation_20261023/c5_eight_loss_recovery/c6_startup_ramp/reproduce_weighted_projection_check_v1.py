"""Deterministic algebra diagnostics only; no Plant or closed-loop stability claim."""
from pathlib import Path
import csv
import json
import numpy as np


def run():
    rng = np.random.default_rng(2026102401)
    rows = []
    for k in range(600):
        W = rng.uniform(-60, 60, (33, 3))
        U = rng.uniform(-60, 60, (33, 3))
        phi = rng.normal(size=33); phi /= np.linalg.norm(phi)
        psi = rng.normal(size=33); psi /= np.linalg.norm(psi)
        beta = min((331 + 10*k)*.001/1.8, 1)
        surface = rng.uniform(-1, 1, 3)*np.array([7, 8, 10])
        y = rng.normal(size=3)*(400 if k % 3 == 0 else 2)
        e = W.T@psi-y
        grad = np.outer(psi, e)
        bias = .12*beta*np.outer(phi, surface)+.00002*W
        G = .01*beta*grad+bias
        bar = W-G; Z = np.clip(bar, -60, 60); R = Z-bar
        loss = .5*np.sum(e**2)
        other = .5*np.sum((U.T@psi-y)**2)
        quadratic = np.sum((psi@(W-U))**2)
        lhs = 2*.01*beta*(loss-other)+.01*beta*quadratic
        terms = [np.sum((W-U)**2), -np.sum((Z-U)**2), np.sum(G**2), -2*np.sum(bias*(W-U)), -np.sum(R**2)]
        rhs = sum(terms)
        identity = np.sum(grad*(W-U))-(loss-other+.5*quadratic)
        scale = abs(lhs)+sum(abs(v) for v in terms)+1
        tolerance = 64*np.finfo(float).eps*scale
        assert rhs-lhs >= -tolerance, (k, rhs-lhs, tolerance)
        rows.append(dict(case=k, beta=beta, projected=int(np.any(R != 0)), slack=float(rhs-lhs), quadratic_identity_residual=float(identity), arithmetic_scale=float(scale), diagnostic_tolerance=float(tolerance)))
    base = Path(__file__).resolve().parent
    historical = json.loads((base/'PARENT_C6_WEIGHTED_BOUND_SYNTHETIC_v1.json').read_text(encoding='utf-8-sig'))
    assert sum(r['projected'] for r in rows) == historical['projected_cases']
    assert abs(min(r['slack'] for r in rows)-historical['min_projection_inequality_slack']) < 1e-12
    assert abs(max(abs(r['quadratic_identity_residual']) for r in rows)-historical['max_quadratic_identity_residual']) < 1e-12
    csv_path = base/'PARENT_C6_WEIGHTED_BOUND_CASES_v2.csv'
    result_path = base/'PARENT_C6_WEIGHTED_BOUND_REPRODUCTION_v2.json'
    assert not csv_path.exists() and not result_path.exists()
    with csv_path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    result = dict(status='PASS_REPRODUCIBLE_SYNTHETIC_ALGEBRA_NOT_INTERVAL_PROOF', seed=2026102401, cases=len(rows), historical_aggregate_reproduced=True, projected_cases=sum(r['projected'] for r in rows), min_slack=min(r['slack'] for r in rows), max_identity_residual=max(abs(r['quadratic_identity_residual']) for r in rows), plant_calls=0, TEST_raw_accessed=False, tolerance_scope='64 eps times arithmetic scale, diagnostic only, no rigorous floating-point certification')
    result_path.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    run()
