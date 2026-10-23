"""Exact rational checks for the physical-residual tracking lemma.

This is a standard-library-only algebra check. It reads only frozen source and
proof/taskbook files; it does not open experiment data or start MATLAB.
"""
from __future__ import annotations

from fractions import Fraction as F
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent / "EXACT_CHECK_RESULT.json"
DELTA = F(1, 1000)
M_VALUES = (F(0), F(1))
SOURCE_SHA256 = {
    "taskbook": (
        "reports/paper_continuation_20261023/"
        "PHYSICAL_RESIDUAL_TRACKING_LEMMA_TASKBOOK_ZH.md",
        "6fd08c0e8250f4075fa33933a8c89d32995bbc75fef09ad1ba54e1bb2f72af91",
    ),
    "sampled_equations": (
        "reports/paper_continuation_20261023/"
        "EXACT_SAMPLED_ERROR_ACCOUNTING_TASKBOOK_ZH.md",
        "104b9da52f2885bd53c2d122ba84ed09ed121d79af6215f9e59593c0eef0e606",
    ),
    "bs_step": (
        "matlab/core/position_bs_step.m",
        "ea533c3ae97cbc552208287e7f8d9b0a0f5a018f36fb5c8bd45520e19e73c681",
    ),
    "pcf_step": (
        "matlab/models/position_filter_realization_pcf_step_v3_5.m",
        "b4ae22db5bd444a162d0cd01a3a59a589f2e37077b089bb33693401b660228d0",
    ),
    "c5_core": (
        "experiments/position_axis_coordinate_c5_dev72_20261023/"
        "run_dl1018_closed_loop.m",
        "48350037b66efe00301b138068f187c62cf92583f0f9ba2fabc9b24f248a963c",
    ),
    "delay_storage_proof": (
        "reports/paper_continuation_20261023/finite_horizon_certificate/"
        "delay_storage_perturbation/DELAY_STORAGE_PERTURBATION_BOUND_ZH.md",
        "8f406230d647b89e91c6495777402bb6b24ea4bee7f400e6e3751b499d97f604",
    ),
    "conditional_prior_proof": (
        "reports/paper_continuation_20261023/finite_horizon_certificate/"
        "conditional_prior_bound/CONDITIONAL_PRIOR_ERROR_BOUND_ZH.md",
        "6ff1d3155095f48ac5ae06bc9caf54a9eed8e52312a354034ce9446ae50fd8db",
    ),
    "metric_definition": (
        "reports/delayed_prediction_c3_dev72_parent_20261023/"
        "parent_raw_metrics.py",
        "c64482d0adbc4358417648ec08351bd78f1d3dbdb38950435fa71b9cb0f531b1",
    ),
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def matrix_mul(left, right):
    return [
        [
            sum((left[i][k] * right[k][j] for k in range(len(right))), F(0))
            for j in range(len(right[0]))
        ]
        for i in range(len(left))
    ]


def matrix_equal(left, right):
    return len(left) == len(right) and all(
        len(a) == len(b) and all(x == y for x, y in zip(a, b))
        for a, b in zip(left, right)
    )


def matrix_vec(matrix, vector):
    return [
        sum((a * b for a, b in zip(row, vector)), F(0))
        for row in matrix
    ]


def add_poly(*polys):
    out = {}
    for poly in polys:
        for monomial, coefficient in poly.items():
            out[monomial] = out.get(monomial, F(0)) + coefficient
    return {m: c for m, c in out.items() if c}


def scale_poly(poly, coefficient):
    return {m: c * coefficient for m, c in poly.items() if c * coefficient}


def mul_poly(left, right):
    out = {}
    for lm, lc in left.items():
        for rm, rc in right.items():
            powers = dict(lm)
            for name, exponent in rm:
                powers[name] = powers.get(name, 0) + exponent
            monomial = tuple(sorted((name, power) for name, power in powers.items() if power))
            out[monomial] = out.get(monomial, F(0)) + lc * rc
    return {m: c for m, c in out.items() if c}


def symbol(name):
    return {((name, 1),): F(1)}


def main() -> None:
    assert not OUT.exists(), "Preserve prior exact-check evidence."
    source_hashes = {}
    for name, (relative, expected) in SOURCE_SHA256.items():
        actual = sha256(ROOT / relative)
        assert actual == expected, (name, actual, expected)
        source_hashes[name] = actual

    dlt = DELTA
    a = 1 - dlt
    b = dlt
    c = -dlt
    d = 1 - 4 * dlt
    A = [[a, b], [c, d]]
    det_a = a * d - b * c
    trace_a = a + d
    assert trace_a == F(399, 200)
    assert det_a == F(199001, 200000)
    discriminant = trace_a * trace_a - 4 * det_a
    assert discriminant == F(1, 200000)

    # Exact state-coordinate map q=[e, sigma-M*eta, eta] and its inverse.
    # For M in {0,1}, verify S A_ext S^-1 and S times every forcing term.
    A_ext = [
        [a, b, F(0)],
        [c, d, F(0)],
        [F(0), F(0), d],
    ]
    augmented_by_mask = {}
    for mask in M_VALUES:
        S = [[F(1), F(0), F(0)],
             [F(0), F(1), -mask],
             [F(0), F(0), F(1)]]
        S_inv = [[F(1), F(0), F(0)],
                 [F(0), F(1), mask],
                 [F(0), F(0), F(1)]]
        transformed = matrix_mul(matrix_mul(S, A_ext), S_inv)
        expected = [
            [a, b, b * mask],
            [c, d, F(0)],
            [F(0), F(0), d],
        ]
        assert matrix_equal(transformed, expected)
        augmented_by_mask[str(int(mask))] = [[str(x) for x in row] for row in transformed]

        rho_p, rho_s, rho_eta = F(7, 13), F(-2, 9), F(5, 17)
        eps_m, rf = F(3, 11), F(-4, 15)
        physical_forcing = [
            rho_p,
            rho_s + dlt * (eps_m + mask * rf),
            dlt * rf + rho_eta,
        ]
        actual = matrix_vec(S, physical_forcing)
        expected_forcing = [
            rho_p,
            rho_s + dlt * eps_m - mask * rho_eta,
            dlt * rf + rho_eta,
        ]
        assert actual == expected_forcing

    # Symbolic polynomial identity proves cancellation for arbitrary PCF alpha,beta:
    # beta(z-d)-beta(alpha-d)-(beta-delta)(z-alpha)=delta(z-alpha).
    z, alpha, beta, delta, d_sym = (
        symbol("z"), symbol("alpha"), symbol("beta"),
        symbol("delta"), symbol("d"),
    )
    z_minus_d = add_poly(z, scale_poly(d_sym, -1))
    alpha_minus_d = add_poly(alpha, scale_poly(d_sym, -1))
    z_minus_alpha = add_poly(z, scale_poly(alpha, -1))
    beta_minus_delta = add_poly(beta, scale_poly(delta, -1))
    cancellation_lhs = add_poly(
        mul_poly(beta, z_minus_d),
        scale_poly(mul_poly(beta, alpha_minus_d), -1),
        scale_poly(mul_poly(beta_minus_delta, z_minus_alpha), -1),
    )
    cancellation_rhs = mul_poly(delta, z_minus_alpha)
    assert cancellation_lhs == cancellation_rhs

    # Exact direct-resolvent channels and the finite/infinite absolute L1 sums.
    one_minus_A = [
        [F(1) - a, -b],
        [-c, F(1) - d],
    ]
    determinant_one_minus_A = (
        one_minus_A[0][0] * one_minus_A[1][1]
        - one_minus_A[0][1] * one_minus_A[1][0]
    )
    assert determinant_one_minus_A == F(1, 200000)
    inv11 = one_minus_A[1][1] / determinant_one_minus_A
    inv12 = -one_minus_A[0][1] / determinant_one_minus_A
    assert inv11 == 800 and inv12 == 200

    # The exact roots are 399/400 +/- sqrt(5)/2000. The inequalities below
    # certify 0 < lambda_- < lambda_+ < a < 1 without floating-point sampling.
    assert trace_a > 0 and trace_a * trace_a > discriminant
    assert 2 * a - trace_a > 0
    assert (2 * a - trace_a) ** 2 > discriminant
    # A11^k > 0 follows from a>lambda_+>lambda_->0 and its two-root formula;
    # A12^k >= 0 follows from b>0 and lambda_+>lambda_-.
    assert a == F(999, 1000) and d == F(249, 250)
    assert F(399, 400) == trace_a / 2

    # The exact determinant and numerator of the physical transfer matrix.
    assert trace_a == F(399, 200)
    assert det_a == F(199001, 200000)
    # (z-d)/D, delta/D, delta^2/D, including the unilateral initial-state term.
    transfer = {
        "D(z)": "z^2 - (399/200) z + 199001/200000",
        "rho_p_to_e": "z - 249/250 over D(z)",
        "T0_rho_s_to_e": "1/1000 over D(z)",
        "T0^2_(epsilon_M+M_rf)_to_e": "1/1000000 over D(z)",
        "initial": "z*((z-249/250)*e0+(1/1000)*sigma0)/D(z)",
    }

    result = {
        "schema": "PHYSICAL_RESIDUAL_TRACKING_LEMMA_EXACT_CHECK_V1",
        "status": "PASS_EXACT_RATIONAL_AND_SYMBOLIC_ALGEBRA",
        "plant_or_matlab_started": False,
        "raw_or_test_data_read": False,
        "training_started": False,
        "normalization": {
            "T0_s": "1",
            "delta": str(dlt),
            "state": "[e, sigma=T0*s]",
            "eta": "eta_tilde=T0*eta",
            "acceleration_inputs": "T0^2 times physical acceleration",
        },
        "A2": [[str(v) for v in row] for row in A],
        "augmented_A_by_M": augmented_by_mask,
        "determinant": str(det_a),
        "trace": str(trace_a),
        "discriminant": str(discriminant),
        "resolvent_channels": transfer,
        "exact_symbolic_identity": (
            "beta*(z-d)-beta*(alpha-d)-(beta-delta)*(z-alpha)"
            "=delta*(z-alpha)"
        ),
        "nonnegative_kernel_l1_sums": {
            "rho_p_to_e": str(inv11),
            "normalized_second_state_increment_to_e": str(inv12),
            "finite_horizon_N": 20000,
            "finite_horizon_upper_bounds": "800 and 200; partial positive sums <= infinite sums",
        },
        "scored_Q_definition": (
            "sqrt(sum_{n=0}^{N-1} ||e_n||_2^2 / N), N=20000; "
            "three axes are summed, not divided by 3"
        ),
        "finite_horizon_bound": (
            "Q_N <= (J_N + 800||rho_p||_2 + 200||T0*rho_s||_2 "
            "+ 200*delta||T0^2*(epsilon_M+M*r_f)||_2)/sqrt(N); "
            "200*delta=1/5"
        ),
        "source_sha256": source_hashes,
    }
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "determinant": result["determinant"],
        "kernel_l1": result["nonnegative_kernel_l1_sums"],
        "result_path": str(OUT),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
