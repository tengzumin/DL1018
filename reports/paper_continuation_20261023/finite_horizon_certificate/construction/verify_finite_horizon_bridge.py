#!/usr/bin/env python3
"""Stdlib-only synthetic check for the finite-horizon path-bound algebra."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def norm(a):
    return math.sqrt(dot(a, a))


def mat_frob(a):
    return math.sqrt(sum(x * x for row in a for x in row))


def mat_inner(a, b):
    return sum(x * y for ra, rb in zip(a, b) for x, y in zip(ra, rb))


def transpose_times(W, phi):
    return [sum(W[i][j] * phi[i] for i in range(len(phi))) for j in range(len(W[0]))]


def outer(a, b):
    return [[x * y for y in b] for x in a]


def loss(W, phi, y):
    r = [x - z for x, z in zip(transpose_times(W, phi), y)]
    return 0.5 * dot(r, r)


def add_scaled(A, B, scale):
    return [[x + scale * y for x, y in zip(ra, rb)] for ra, rb in zip(A, B)]


def box_project(A, limit):
    return [[min(limit, max(-limit, x)) for x in row] for row in A]


def matrix_state_step(x, f1, f2):
    return [0.999 * x[0] + 0.001 * x[1] + f1,
            -0.001 * x[0] + 0.996 * x[1] + f2]


def close(a, b, tol=2e-11):
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


def main():
    # One-step projected-gradient inequality, including a nonzero projection residual.
    rho = 0.01
    phi = [0.6, 0.8]
    W = [[0.95, -0.2], [0.3, 0.1]]
    U = [[-0.4, 0.25], [0.6, -0.3]]
    H = [[-0.8, 0.0], [0.0, 0.0]]
    y = [0.2, -0.5]
    residual = [a - b for a, b in zip(transpose_times(W, phi), y)]
    G = outer(phi, residual)
    candidate = add_scaled(add_scaled(W, G, -rho), H, -1.0)
    W_next = box_project(candidate, 1.0)
    p = [[W_next[i][j] - candidate[i][j] for j in range(2)] for i in range(2)]
    E = [[W[i][j] - U[i][j] for j in range(2)] for i in range(2)]
    gd_identity = mat_inner(E, G)
    # For the identity, use (W-U)'phi directly.
    wminusupred = [a - b for a, b in zip(transpose_times(W, phi), transpose_times(U, phi))]
    assert close(gd_identity, loss(W, phi, y) - loss(U, phi, y) + 0.5 * dot(wminusupred, wminusupred))
    assert dot(phi, phi) == 1.0
    assert mat_frob(W_next) <= math.sqrt(2.0) + 1e-12
    proj_rhs = mat_frob([[candidate[i][j] - U[i][j] for j in range(2)] for i in range(2)]) ** 2 - mat_frob(p) ** 2
    d_next = mat_frob([[W_next[i][j] - U[i][j] for j in range(2)] for i in range(2)]) ** 2
    assert d_next <= proj_rhs + 1e-12
    a_young = (1.0 - rho) / 2.0
    c_h = 1.0 + rho / a_young
    delta_d = d_next - mat_frob(E) ** 2
    rhs = (-rho * (1.0 - rho) * loss(W, phi, y) + 2.0 * rho * loss(U, phi, y)
           - rho * dot(wminusupred, wminusupred) - mat_frob(p) ** 2
           - 2.0 * mat_inner(E, H) + c_h * mat_frob(H) ** 2)
    assert delta_d <= rhs + 2e-12

    # Exact old-output / next-weight identity and ramp/clip decomposition.
    W0 = [[1.0, 5.0], [0.5, 0.2]]
    W1 = [[0.9, 4.5], [0.4, 0.1]]
    phi_out = [0.6, 0.8]
    y_out = [0.3, -0.2]
    raw = transpose_times(W0, phi_out)
    raw_next = transpose_times(W1, phi_out)
    delta_raw = transpose_times([[W1[i][j] - W0[i][j] for j in range(2)] for i in range(2)], phi_out)
    lhs = [x - z for x, z in zip(raw, y_out)]
    rhs_identity = [raw_next[j] - y_out[j] - delta_raw[j] for j in range(2)]
    assert all(close(x, z) for x, z in zip(lhs, rhs_identity))
    beta = 0.4
    clipped = [min(3.0, max(-3.0, x)) for x in raw]
    applied = [beta * x for x in clipped]
    decomposition = [raw[j] - y_out[j] + (beta - 1.0) * raw[j] + beta * (clipped[j] - raw[j])
                     for j in range(2)]
    applied_error = [x - z for x, z in zip(applied, y_out)]
    assert all(close(x, z) for x, z in zip(applied_error, decomposition))
    three_term_rhs = 3.0 * (dot(lhs, lhs)
                            + dot([(beta - 1.0) * x for x in raw], [(beta - 1.0) * x for x in raw])
                            + dot([beta * (clipped[j] - raw[j]) for j in range(2)],
                                  [beta * (clipped[j] - raw[j]) for j in range(2)]))
    assert dot(decomposition, decomposition) <= three_term_rhs + 1e-12

    # Exact held-block decomposition, retaining label/mean mismatch and within-window variation.
    d = [[0.1 * r - 0.02, -0.03 * r, 0.005 * (r * r)] for r in range(10)]
    ybar_target = [0.25, -0.1, 0.22]
    u = [0.8, 0.2, -0.3]
    dbar = [sum(row[j] for row in d) / 10.0 for j in range(3)]
    xi = [ybar_target[j] - dbar[j] for j in range(3)]
    delta = [u[j] - ybar_target[j] for j in range(3)]
    nu = [[dbar[j] - d[r][j] for j in range(3)] for r in range(10)]
    assert max(abs(sum(row[j] for row in nu)) for j in range(3)) < 1e-12
    actual_energy = 0.0
    rhs_energy = 10.0 * dot([u[j] - dbar[j] for j in range(3)], [u[j] - dbar[j] for j in range(3)])
    for r in range(10):
        eps = [u[j] - d[r][j] for j in range(3)]
        reconstructed = [delta[j] + xi[j] + nu[r][j] for j in range(3)]
        assert all(close(x, z) for x, z in zip(eps, reconstructed))
        actual_energy += dot(eps, eps)
        rhs_energy += dot(nu[r], nu[r])
    assert close(actual_energy, rhs_energy)

    # Fixed diagonal M blend: aReq - M r_f == M a_f + (I-M) aReq.
    areq = [0.7, -0.4, 0.2]
    af = [0.1, -0.2, 0.3]
    rf = [areq[i] - af[i] for i in range(3)]
    m = [1.0, 1.0, 0.0]
    lhs_m = [areq[i] - m[i] * rf[i] for i in range(3)]
    rhs_m = [m[i] * af[i] + (1.0 - m[i]) * areq[i] for i in range(3)]
    assert all(close(x, z) for x, z in zip(lhs_m, rhs_m))

    # Full scoring-horizon impulse taps and exact infinite geometric gains.
    taps = 19999  # e[0:20000] can see transition inputs 0:19999, excluding the final input.
    h1, h2 = [], []
    state1, state2 = [1.0, 0.0], [0.0, 1.0]
    for _ in range(taps):
        h1.append(state1[0])
        h2.append(state2[0])
        state1 = [0.999 * state1[0] + 0.001 * state1[1],
                  -0.001 * state1[0] + 0.996 * state1[1]]
        state2 = [0.999 * state2[0] + 0.001 * state2[1],
                  -0.001 * state2[0] + 0.996 * state2[1]]
    disc = 1.995**2 - 4.0 * 0.995005
    roots = [(1.995 + math.sqrt(disc)) / 2.0, (1.995 - math.sqrt(disc)) / 2.0]
    assert disc > 0.0 and all(0.0 < x < 1.0 for x in roots)
    assert min(h1) >= -1e-12 and min(h2) >= -1e-12
    det_i_minus_a = 0.001 * 0.004 + 0.001 * 0.001
    gain1_inf = 0.004 / det_i_minus_a
    gain2_inf = 0.001 / det_i_minus_a
    gain1_finite = 0.001 * sum(h1)
    gain2_finite = 0.001 * sum(h2)
    assert close(gain1_inf, 800.0) and close(gain2_inf, 200.0)
    assert abs(gain1_finite - 0.8) < 2e-9 and abs(gain2_finite - 0.2) < 2e-9

    # Compare direct recurrence with its causal convolution on a small synthetic trace.
    n_small = 40
    f1 = [0.03 * math.sin(0.31 * n) for n in range(n_small)]
    f2 = [0.02 * math.cos(0.23 * n) for n in range(n_small)]
    x0 = [0.12, -0.07]
    direct, state = [], x0[:]
    for n in range(n_small):
        direct.append(state[0])
        state = matrix_state_step(state, f1[n], f2[n])
    initial, state = [], x0[:]
    for _ in range(n_small):
        initial.append(state[0])
        state = matrix_state_step(state, 0.0, 0.0)
    conv = []
    for n in range(n_small):
        val = initial[n]
        for i in range(n):
            lag = n - 1 - i
            val += h1[lag] * f1[i] + h2[lag] * f2[i]
        conv.append(val)
    assert max(abs(a - b) for a, b in zip(direct, conv)) < 2e-12
    seq_norm = lambda x: math.sqrt(sum(v * v for v in x))
    conv_bound = (seq_norm(initial) + sum(h1[:n_small - 1]) * seq_norm(f1)
                  + sum(h2[:n_small - 1]) * seq_norm(f2))
    assert seq_norm(direct) <= conv_bound + 1e-12

    # Show why the box-only H cross-term bound is finite but uninformative.
    R_box = (60.0 + 1.336968183517456) * math.sqrt(99.0)
    H_box = 0.12 * math.sqrt(213.0) + 0.00002 * 60.0 * math.sqrt(99.0)
    updates = 1967
    denom = rho * (1.0 - rho)
    c_h = 1.0 + 2.0 * rho / (1.0 - rho)
    box_loss_without_comparator = (H_box**2 + 2.0 * R_box * H_box * updates
                                   + c_h * H_box**2 * updates) / denom

    result = {
        "status": "PASS_SYNTHETIC_ALGEBRA_ONLY",
        "checks": ["one_step_projected_gradient_young_bound", "old_output_next_weight_identity",
                   "ramp_clip_three_term_bound", "held_block_mean_and_variation_identity",
                   "fixed_diagonal_M_reference_blend", "impulse_poles_nonnegative_and_gains",
                   "direct_recurrence_equals_convolution", "finite_horizon_l2_convolution_bound"],
        "A2": [[0.999, 0.001], [-0.001, 0.996]],
        "poles": roots,
        "finite_impulse_terms_for_20000_scored_positions": taps,
        "finite_dt_l1_gains": [gain1_finite, gain2_finite],
        "infinite_l1_gains_without_dt": [gain1_inf, gain2_inf],
        "box_only_H_norm": H_box,
        "box_only_R_for_W0_comparator": R_box,
        "box_only_cumulative_loss_upper_excluding_comparator_loss": box_loss_without_comparator,
        "new_Plant": 0,
        "raw_read": False,
        "TEST_accessed": False,
        "closed_loop_stability_claim": False,
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    output = Path(__file__).with_name("SYNTHETIC_BRIDGE_CHECK.json")
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
