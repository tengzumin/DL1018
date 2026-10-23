"""Small synthetic algebra check; no rollout, model, training data or TEST."""
import json
from pathlib import Path

import numpy as np


def main():
    output = Path(__file__).with_name("ALGEBRA_PRECHECK.json")
    assert not output.exists()
    rng = np.random.default_rng(20261023)
    rho = .01
    W = rng.normal(0, .2, (33, 3))
    W[0] = [59.99, -59.99, 59.99]
    comparator = W.copy()
    initial_distance = 0.
    total_loss = total_comparator_loss = total_H = total_H2 = 0.
    max_distance = 0.
    projection_events = 0
    max_identity_error = 0.
    for event in range(100):
        phi = rng.normal(size=33)
        phi /= np.linalg.norm(phi)
        surface = np.clip(rng.normal(size=3), -np.array([7, 8, 10]), [7, 8, 10])
        beta = min((event + 33) / 180, 1.)
        target = rng.normal(size=3)
        if event == 0:
            phi = np.eye(33)[0]
            surface = np.array([-7., 8., -10.])
            target = W.T @ phi + [10., -10., 10.]
        error = W.T @ phi - target
        comparator_error = comparator.T @ phi - target
        G = np.outer(phi, error)
        H = .12 * beta * np.outer(phi, surface) + .00002 * W
        candidate = W - rho * G - H
        following = np.clip(candidate, -60, 60)
        projection = following - candidate
        E = W - comparator
        distance = np.linalg.norm(E)
        max_distance = max(max_distance, distance)
        loss = .5 * np.dot(error, error)
        loss_star = .5 * np.dot(comparator_error, comparator_error)
        q = E.T @ phi
        exact_change = -2*rho*(loss-loss_star+.5*np.dot(q,q)) - 2*np.sum(H*E) + np.sum((rho*G+H)**2)
        # Before projection the expansion is an equality; after projection it is an upper bound.
        before_change = np.sum((candidate-comparator)**2) - np.sum(E**2)
        max_identity_error = max(max_identity_error, abs(before_change-exact_change))
        actual_change = np.sum((following-comparator)**2) - np.sum(E**2)
        assert actual_change <= exact_change - np.sum(projection**2) + 2e-11
        total_loss += loss
        total_comparator_loss += loss_star
        total_H += np.linalg.norm(H)
        total_H2 += np.sum(H**2)
        projection_events += int(np.any(projection != 0))
        W = following
    bound_rhs = (initial_distance + 2*rho*total_comparator_loss + 2*max_distance*total_H
                 + (1+2*rho/(1-rho))*total_H2)
    bound_lhs = rho*(1-rho)*total_loss
    assert bound_lhs <= bound_rhs + 2e-11
    assert projection_events > 0 and max_identity_error < 2e-11
    result = dict(status="PASS_SYNTHETIC_ALGEBRA_ONLY", events=100,
                  projection_events=projection_events, max_expansion_abs_error=max_identity_error,
                  cumulative_bound_lhs=bound_lhs, cumulative_bound_rhs=bound_rhs,
                  comparator="fixed initial W inside projection box; synthetic, not deployed W0",
                  limitation="Only checks proposed parameter-loss algebra; no position bound or closed-loop stability theorem", Plant=0, TEST_accessed=False)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
