#!/usr/bin/env python3
"""Exact-rational fixed-margin and finite-bound coefficient check."""

from fractions import Fraction as Q
from functools import reduce
from hashlib import sha256
from math import lcm
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
FROZEN = ROOT / "reports/paper_continuation_20261023/finite_horizon_certificate/delay_aware_energy_diagnosis/DELAY_STORAGE_EXACT_CERTIFICATE.json"
FROZEN_SHA = "f785307fc7d6ce20f7a6267b50dfba8dda33dc1d072ea2323c91ea4930f858d7"


def det(a):
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


def qstr(x):
    return f"{x.numerator}/{x.denominator}"


def mm(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(len(b))) for j in range(len(b[0]))]
            for i in range(len(a))]


def main():
    frozen_bytes = FROZEN.read_bytes()
    frozen_sha = sha256(frozen_bytes).hexdigest()
    assert frozen_sha == FROZEN_SHA, (frozen_sha, FROZEN_SHA)
    cert = json.loads(frozen_bytes)
    K = [[Q(x) for x in row] for row in cert["K_abs_upper_exact"]]
    F = [[Q(x) for x in row] for row in cert["F_A10"]]
    g = [Q(x) for x in cert["g_sum_Aj_q_j0to9"]]

    mu = Q(1, 25000)       # 4e-5 certified nominal margin
    zeta = Q(1, 50000)     # reserve half the margin for perturbation cross terms
    alpha = Q(1, 24)
    kappa = Q(1, 2500)
    d0 = Q(49999, 50000)
    rho = Q(1, 100)
    c = Q(3, 25)
    nu_w = alpha * (1 - d0 * d0)
    nu_R = alpha - kappa
    assert nu_w == Q(33333, 20000000000)
    assert nu_R == Q(619, 15000)

    P = [[-K[i][j] - (mu if i == j else 0) for j in range(4)] for i in range(4)]
    D = reduce(lcm, (x.denominator for row in P for x in row), 1)
    P_int = [[int(x * D) for x in row] for row in P]
    minors = [det([row[:k] for row in P_int[:k]]) for k in range(1, 5)]
    assert all(x.denominator == 1 and x > 0 for x in minors), "-Kbar - 4e-5 I is not certified positive definite"

    # Rational upper bounds: ||F||_2 <= ||F||_F <= sum(abs(F_ij));
    # ||g||_2 <= sum(abs(g_i)). All disturbance coefficients are exact.
    Lx = sum(abs(x) for row in F for x in row) + sum(abs(x) for x in g)
    LX = d0 + rho + c
    Cz = kappa * LX + 2 * alpha * c
    Bw = 2 * alpha * (d0 + rho)
    Cdx = Q(1, 2) + Lx * Lx / (2 * zeta)
    Cdw = alpha + Cz * Cz / (2 * zeta) + Bw * Bw / (2 * nu_w)

    A = [[Q(999, 1000), Q(1, 1000)], [Q(-1, 1000), Q(996, 1000)]]
    power = [[Q(1), Q(0)], [Q(0), Q(1)]]
    chi_x_squared = Q(0)
    for _ in range(10):
        chi_x_squared += sum(x * x for row in power for x in row)
        power = mm(power, A)

    out = {
        "method": "stdlib fractions; exact rational matrix and Sylvester leading principal minors",
        "frozen_ideal_certificate_sha256": frozen_sha,
        "fixed_margin_mu": qstr(mu),
        "reserved_state_cross_term_budget_zeta": qstr(zeta),
        "remaining_state_dissipation_mu_minus_zeta": qstr(mu - zeta),
        "negative_K_minus_mu_I_common_denominator": str(D),
        "negative_K_minus_mu_I_scaled_integer_matrix": P_int,
        "negative_K_minus_mu_I_scaled_leading_principal_minors": [str(int(x)) for x in minors],
        "negative_K_minus_mu_I_positive_definite": True,
        "base_weight_leak_dissipation_nu_w": qstr(nu_w),
        "remaining_weight_dissipation_after_Young_nu_w_over_2": qstr(nu_w / 2),
        "projection_residual_dissipation_nu_R": qstr(nu_R),
        "norm_bounds": {
            "Lx_upper_for_norm_Fx_plus_g_beta_a": qstr(Lx),
            "LX_upper_for_delayed_memory_scalar_vector": qstr(LX),
            "Cz_memory_plus_weight_z_cross": qstr(Cz),
            "Bw_weight_w_cross": qstr(Bw),
            "C_dx_squared": qstr(Cdx),
            "C_dw_squared": qstr(Cdw),
            "event_lift_sample_forcing_gain_squared_chi_x": qstr(chi_x_squared),
        },
        "scope": "fixed A, gamma/leak/rho, unit feature, 0<=beta<=1, diagonal fixed M; finite pathwise inputs d_x,d_w, not a closed-loop stability result",
    }
    target = Path(__file__).with_name("PERTURBATION_EXACT_CERTIFICATE.json")
    target.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
