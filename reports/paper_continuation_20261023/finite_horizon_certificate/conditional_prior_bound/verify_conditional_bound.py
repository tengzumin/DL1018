#!/usr/bin/env python3
"""Exact small certificates for the fixed conditional prior-bound constants."""

from fractions import Fraction as Q
from hashlib import sha256
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SOURCES = {
    "taskbook": (
        "reports/paper_continuation_20261023/CONDITIONAL_ERROR_BOUND_TASKBOOK_ZH.md",
        "336C89F493F41D1C529F429EFDC1444229C3F5CEE819CDF7AE9C43C23A204383",
    ),
    "frozen_perturbation_report": (
        "reports/paper_continuation_20261023/finite_horizon_certificate/delay_storage_perturbation/DELAY_STORAGE_PERTURBATION_BOUND_ZH.md",
        "8F406230D647B89E91C6495777402BB6B24EA4BEE7F400E6E3751B499D97F604",
    ),
    "frozen_perturbation_exact_certificate": (
        "reports/paper_continuation_20261023/finite_horizon_certificate/delay_storage_perturbation/PERTURBATION_EXACT_CERTIFICATE.json",
        "8E92FCA3D02584BCA289942BDB7946BE494FFB50AC944B6BD694DBD7EFCF2307",
    ),
    "c5_core": (
        "experiments/position_axis_coordinate_c5_20261023/run_dl1018_closed_loop.m",
        "48350037B66EFE00301B138068F187C62CF92583F0F9BA2FABC9B24F248A963C",
    ),
    "c5_controller_helper": (
        "experiments/position_axis_coordinate_c5_20261023/delayed_prediction_step_candidate.m",
        "48FEEBF934B8EB90B4424F2286AA857C48213D229714F30AF99AACF53329549D",
    ),
    "pcf_filter_helper": (
        "matlab/models/position_filter_realization_pcf_step_v3_5.m",
        "B4AE22DB5BD444A162D0CD01A3A59A589F2E37077B089BB33693401B660228D0",
    ),
    "sampled_equation_taskbook": (
        "reports/paper_continuation_20261023/EXACT_SAMPLED_ERROR_ACCOUNTING_TASKBOOK_ZH.md",
        "104B9DA52F2885BD53C2D122BA84ED09ED121D79AF6215F9E59593C0EEF0E606",
    ),
    "fixed_mask_addendum": (
        "reports/paper_continuation_20261023/finite_horizon_certificate/CONSTANT_DIAGONAL_M_ADDENDUM_ZH.md",
        "32E5B41673A5E7FDF8555AE2B4B5B1BE63F2E10C5783EF184DC53F65C530EEFC",
    ),
}
FROZEN_P = ROOT / (
    "reports/paper_continuation_20261023/finite_horizon_certificate/"
    "delay_storage_perturbation/PERTURBATION_EXACT_CERTIFICATE.json"
)


def digest(path):
    return sha256(path.read_bytes()).hexdigest().upper()


def qstr(value):
    return f"{value.numerator}/{value.denominator}"


def mm(a, b):
    return [
        [sum(a[i][k] * b[k][j] for k in range(len(b))) for j in range(len(b[0]))]
        for i in range(len(a))
    ]


def transpose(a):
    return [list(row) for row in zip(*a)]


def det2(a):
    return a[0][0] * a[1][1] - a[0][1] * a[1][0]


def exp_minus_alternating_bounds(x, last_odd=9):
    """For 0<x<1, S_odd < exp(-x) < S_even by alternating-series bounds."""
    assert 0 < x < 1 and last_odd % 2 == 1
    partials = []
    term = Q(1)
    total = Q(1)
    partials.append(total)
    for k in range(1, last_odd + 1):
        term *= -x / k
        total += term
        partials.append(total)
    lower = partials[last_odd]
    upper = partials[last_odd - 1]
    assert lower < upper
    return lower, upper


def main():
    checked_sources = {}
    for name, (relative, expected) in SOURCES.items():
        actual = digest(ROOT / relative)
        assert actual == expected, (name, actual, expected)
        checked_sources[name] = {"path": relative, "sha256": actual}

    frozen = json.loads(FROZEN_P.read_text(encoding="utf-8"))
    assert frozen["negative_K_minus_mu_I_positive_definite"] is True
    assert all(int(value) > 0 for value in frozen["negative_K_minus_mu_I_scaled_leading_principal_minors"])
    cx = Q(frozen["norm_bounds"]["C_dx_squared"])
    cw = Q(frozen["norm_bounds"]["C_dw_squared"])
    chi2 = Q(frozen["norm_bounds"]["event_lift_sample_forcing_gain_squared_chi_x"])

    alpha = Q(1, 24)
    alpha_minus_kappa = Q(619, 15000)
    mu_z = Q(1, 50000)
    nu_w = Q(33333, 20000000000)
    nu_w_after_young = nu_w / 2
    decay_rate = min(2 * mu_z, nu_w_after_young / alpha)
    theta = 1 - decay_rate
    assert alpha_minus_kappa > 0 and 0 < theta < 1
    assert decay_rate == Q(99999, 5000000000)
    assert theta == Q(4999900001, 5000000000)

    # Exact contraction certificate for A2: I - A2' A2 is positive definite.
    a2 = [[Q(999, 1000), Q(1, 1000)], [Q(-1, 1000), Q(996, 1000)]]
    at_a = mm(transpose(a2), a2)
    contraction_gap = [
        [(Q(1) if i == j else Q(0)) - at_a[i][j] for j in range(2)]
        for i in range(2)
    ]
    gap_minors = [contraction_gap[0][0], det2(contraction_gap)]
    assert all(value > 0 for value in gap_minors)

    delta = Q(1, 1000)
    power = [[Q(1), Q(0)], [Q(0), Q(1)]]
    input_column = [Q(0), delta]
    g = [Q(0), Q(0)]
    for _ in range(10):
        g = [g[i] + sum(power[i][j] * input_column[j] for j in range(2)) for i in range(2)]
        power = mm(power, a2)
    g_l1 = sum((abs(value) for value in g), Q(0))
    filter_x = 4 * delta
    a_lower, a_upper = exp_minus_alternating_bounds(filter_x)
    c_eta_lower = a_lower - 1 + filter_x
    c_eta_upper = a_upper - 1 + filter_x
    assert 0 < c_eta_lower < c_eta_upper
    b_lower = (1 - a_upper) / 4
    b_upper = (1 - a_lower) / 4

    n_first = 320
    event_period = 10
    beta_rise = Q(9, 5)
    n_events = 1968
    beta = [min(Q(n_first + event_period * q + 1, 1000) / beta_rise, Q(1))
            for q in range(n_events)]
    ramp_indices = [q for q, value in enumerate(beta) if value < 1]
    assert beta[0] == Q(107, 600)
    assert ramp_indices == list(range(148))
    assert beta[147] == Q(199, 200)
    assert beta[148] == 1 and beta[-1] == 1
    beta_deficit_sum = sum((1 - value for value in beta), Q(0))
    beta_deficit_sq_sum = sum(((1 - value) ** 2 for value in beta), Q(0))

    result = {
        "method": "Python standard library; Fraction exact arithmetic; alternating-series exponential enclosure",
        "checked_sources": checked_sources,
        "fixed_storage": {
            "alpha": qstr(alpha),
            "alpha_minus_kappa": qstr(alpha_minus_kappa),
            "mu_z_after_perturbation_budget": qstr(mu_z),
            "nu_w_after_young": qstr(nu_w_after_young),
            "contraction_rate_1_minus_theta": qstr(decay_rate),
            "theta_exact": qstr(theta),
            "theta_decimal": float(theta),
            "Cx_exact": qstr(cx),
            "Cw_exact": qstr(cw),
            "chi_x_squared_exact": qstr(chi2),
            "event_dx_squared_bound_factor_10_chi_x_squared": qstr(10 * chi2),
            "weight_energy_sum_factor_inverse_nu_w": qstr(1 / nu_w_after_young),
            "event_state_feedback_gain_g_l1_upper": qstr(g_l1),
            "frozen_nominal_matrix_pd_minors_positive": True,
        },
        "sample_matrix_contraction": {
            "A2_exact": [[qstr(x) for x in row] for row in a2],
            "I_minus_AT_A_exact": [[qstr(x) for x in row] for row in contraction_gap],
            "leading_principal_minors_exact": [qstr(x) for x in gap_minors],
            "strict_contraction_certified": True,
        },
        "filter_step": {
            "delta": qstr(delta),
            "decay_a_lower": qstr(a_lower),
            "decay_a_upper": qstr(a_upper),
            "integral_b_lower": qstr(b_lower),
            "integral_b_upper": qstr(b_upper),
            "rho_eta_coefficient_lower": qstr(c_eta_lower),
            "rho_eta_coefficient_upper": qstr(c_eta_upper),
            "initial_eta_is_zero_in_frozen_runner": True,
            "eta_sup_bound_normalized": "R_f_tilde/4",
            "rho_eta_sup_bound_normalized": f"({qstr(c_eta_upper)})*R_f_tilde/2",
        },
        "beta_clock": {
            "beta_q_exact": "min((321+10*q)/1800,1)",
            "beta_0": qstr(beta[0]),
            "last_ramped_event_q": ramp_indices[-1],
            "first_fully_ramped_event_q": 148,
            "sum_one_minus_beta_q0_to_q1967": qstr(beta_deficit_sum),
            "sum_one_minus_beta_squared_q0_to_q1967": qstr(beta_deficit_sq_sum),
        },
        "conditional_bound_formulas": {
            "event_representation_bound": "E_q=E+(1-beta_q)*||U||_F",
            "sample_forcing_bound": "F_q^2=(delta*R_eta+R_p)^2+(delta*E_q+R_s+R_rho_eta)^2",
            "dx_q_bound": "||d_x,q||^2 <= 10*chi_x_squared*F_q^2",
            "dw_q_bound_q_ge_1": "||d_w,q|| <= h_e*lambda_e*||U||_F + rho*(E+Xi)",
            "V_input_q": "u_q=Cx*D_x,q^2+Cw*D_w^2",
            "V_geometric_convolution": "V_q <= theta^(q-1)*V_1 + sum_{j=1}^{q-1} theta^(q-1-j)*u_j",
            "local_domain_sufficient_threshold": "V_q <= min(49/2, (alpha-kappa)*(3-u_star)^2), u_star=max_k ||U[:,k]||_2 < 3",
        },
        "scope": "conditional local theorem only; hypotheses are not established for the real Plant; no MATLAB/Plant/raw/TEST run",
    }
    out_path = Path(__file__).with_name("CONDITIONAL_EXACT_CERTIFICATE.json")
    out_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
