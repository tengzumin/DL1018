#!/usr/bin/env python3
"""Exact-rational certificate for the fixed ideal delay-aware storage bound."""

from fractions import Fraction as Q
from functools import reduce
from math import lcm
import json
from pathlib import Path


def mm(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(len(b))) for j in range(len(b[0]))]
            for i in range(len(a))]


def mt(a):
    return [list(row) for row in zip(*a)]


def madd(a, b):
    return [[a[i][j] + b[i][j] for j in range(len(a[0]))] for i in range(len(a))]


def mscale(s, a):
    return [[s * x for x in row] for row in a]


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def det(a):
    """Fraction-preserving determinant by exact Gaussian elimination."""
    m = [[Q(x) for x in row] for row in a]
    sign = 1
    value = Q(1)
    for k in range(len(m)):
        pivot = next((i for i in range(k, len(m)) if m[i][k] != 0), None)
        if pivot is None:
            return Q(0)
        if pivot != k:
            m[k], m[pivot] = m[pivot], m[k]
            sign = -sign
        p = m[k][k]
        value *= p
        for i in range(k + 1, len(m)):
            factor = m[i][k] / p
            for j in range(k + 1, len(m)):
                m[i][j] -= factor * m[k][j]
    return sign * value


def qs(x):
    return f"{x.numerator}/{x.denominator}"


def main():
    A = [[Q(999, 1000), Q(1, 1000)], [Q(-1, 1000), Q(996, 1000)]]
    T0_s = Q(1)
    dt_norm = Q(1, 1000) / T0_s
    h_norm = Q(1, 100) / T0_s
    lambda_norm = Q(1, 500) * T0_s
    gamma_norm = Q(12)
    q = [Q(0), dt_norm]
    I = [[Q(1), Q(0)], [Q(0), Q(1)]]
    F = I
    for _ in range(10):
        F = mm(F, A)
    power = I
    g = [Q(0), Q(0)]
    for _ in range(10):
        aq = [sum(power[i][j] * q[j] for j in range(2)) for i in range(2)]
        g = [g[i] + aq[i] for i in range(2)]
        power = mm(power, A)

    rho = Q(1, 100)
    d0 = 1 - h_norm * lambda_norm
    c, alpha, kappa = h_norm * gamma_norm, 1 / (2 * gamma_norm), Q(1, 2500)
    assert c == Q(3, 25) and alpha == Q(1, 24) and d0 == Q(49999, 50000)
    dgram = madd(mm(mt(F), F), mscale(Q(-1), I))
    ftg = [sum(mt(F)[i][j] * g[j] for j in range(2)) for i in range(2)]
    g2 = dot(g, g)

    # Uniform comparison for z=(e,s,a,b), beta in [0,1], |r|<=1.
    # Diagonal coefficients increase with beta^2 where beta occurs; each
    # off-diagonal magnitude is bounded by its beta=1, |r|=1 endpoint.
    K = [[Q(0) for _ in range(4)] for _ in range(4)]
    K[0][0] = dgram[0][0] / 2
    K[1][1] = dgram[1][1] / 2 + (alpha + kappa) * c * c
    K[0][1] = K[1][0] = abs(dgram[0][1]) / 2
    K[2][2] = g2 / 2 - kappa * d0 * d0 / 4
    K[3][3] = alpha * (-2 * d0 * rho + rho * rho) + kappa * rho * rho + kappa
    K[0][2] = K[2][0] = abs(ftg[0]) / 2
    K[1][2] = K[2][1] = abs(ftg[1] / 2 - alpha * c * d0)
    K[1][3] = K[3][1] = alpha * c * rho

    negK = mscale(Q(-1), K)
    minors = [det([row[:k] for row in negK[:k]]) for k in range(1, 5)]
    assert all(v > 0 for v in minors), "Sylvester certificate failed"

    entries = [x for row in negK for x in row]
    D = reduce(lcm, (x.denominator for x in entries), 1)
    integer_negK = [[int(x * D) for x in row] for row in negK]
    integer_minors = [det([row[:k] for row in integer_negK[:k]]) for k in range(1, 5)]
    assert all(x.denominator == 1 and x > 0 for x in integer_minors)

    out = {
        "method": "stdlib fractions; exact rational arithmetic; Sylvester leading principal minors",
        "A": [[qs(x) for x in row] for row in A],
        "normalization": {
            "T0_seconds": qs(T0_s), "dt_over_T0": qs(dt_norm), "h_phys_over_T0": qs(h_norm),
            "lambda_phys_times_T0": qs(lambda_norm), "gamma_phys_times_T0_squared": qs(gamma_norm),
            "alpha_equals_1_over_2_gamma_norm": qs(alpha), "c_equals_h_norm_gamma_norm": qs(c),
            "w_norm_equals_T0_squared_times_W": True,
        },
        "F_A10": [[qs(x) for x in row] for row in F],
        "g_sum_Aj_q_j0to9": [qs(x) for x in g],
        "constants": {
            "d0": qs(d0), "rho": qs(rho), "c": qs(c), "alpha": qs(alpha), "kappa": qs(kappa),
            "alpha_minus_kappa_storage_floor": qs(alpha - kappa),
            "alpha_times_d0_squared_minus_one_weight_leak": qs(alpha * (d0 * d0 - 1)),
            "projection_residual_coefficient_upper_bound": qs(-(alpha - kappa)),
        },
        "K_abs_upper_exact": [[qs(x) for x in row] for row in K],
        "negative_K_common_denominator": str(D),
        "negative_K_scaled_integer_matrix": integer_negK,
        "negative_K_leading_principal_minors_exact": [qs(x) for x in minors],
        "negative_K_scaled_integer_leading_principal_minors": [str(int(x)) for x in integer_minors],
        "negative_K_positive_definite": True,
        "scope": "ideal fixed model, zero residual, beta in [0,1], unit features; projection is onto an origin-containing convex box and its residual inequality is retained (R=0 when inactive); no deployment stability claim",
    }
    target = Path(__file__).with_name("DELAY_STORAGE_EXACT_CERTIFICATE.json")
    target.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
