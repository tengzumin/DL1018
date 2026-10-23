"""Small exact-mechanics matrix probe; not a closed-loop stability proof."""
import json
from pathlib import Path

import numpy as np

DT, H, GAMMA, RHO, LAMBDA = 0.001, 0.01, 12.0, 0.01, 0.002
A = np.array([[0.999, 0.001], [-0.001, 0.996]], dtype=float)
F = np.linalg.matrix_power(A, 10)
b_u = np.array([[0.0], [DT]])
g = sum((np.linalg.matrix_power(A, 9 - r) @ b_u for r in range(10)),
        start=np.zeros((2, 1)))
e_s = np.array([[0.0, 1.0]])
c = H * GAMMA


def event_matrix(phi, psi):
    phi = np.asarray(phi, dtype=float).reshape(-1, 1)
    psi = np.asarray(psi, dtype=float).reshape(-1, 1)
    eye = np.eye(phi.shape[0])
    d_psi = (1.0 - H * LAMBDA) * eye - RHO * (psi @ psi.T)
    return np.block([[F, g @ phi.T], [-c * phi @ e_s, d_psi]])


def eig_pairs(matrix):
    vals = sorted(np.linalg.eigvals(matrix), key=abs, reverse=True)
    return [[float(v.real), float(v.imag)] for v in vals]


# Frozen-feature, one-axis necessary subcase: phi=psi=1, y=0, beta=1,
# no clipping/projection, eta and sampling remainders zero.
constant = event_matrix([1.0], [1.0])
constant_eigs = eig_pairs(constant)
q_identity = np.eye(constant.shape[0])
p_vec = np.linalg.solve(
    np.eye(constant.size) - np.kron(constant.T, constant.T),
    q_identity.reshape(-1, order="F"),
)
lyap_p = p_vec.reshape(constant.shape, order="F")
lyap_residual = constant.T @ lyap_p @ constant - lyap_p + q_identity

# Distinct current/previous unit features, alternating e1/e2 in R^3.
# Their covariance has rank 2<3, so this path is not PE in the full feature space.
e1, e2 = [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]
m_e1_e2 = event_matrix(e1, e2)
m_e2_e1 = event_matrix(e2, e1)
period2 = m_e2_e1 @ m_e1_e2
period2_eigs = eig_pairs(period2)
feature_covariance = np.mean(np.array([e1, e2])[:, :, None]
                             * np.array([e1, e2])[:, None, :], axis=0)

result = {
    "scope": "ideal necessary subcases only; no deployment-stability claim",
    "constants": {"dt": DT, "event_h": H, "gamma": GAMMA,
                  "rho": RHO, "leak_lambda": LAMBDA,
                  "weight_tracking_gain_h_gamma": c},
    "A_1ms": A.tolist(),
    "A_10": F.tolist(),
    "held_unit_input_lift_g": g.ravel().tolist(),
    "constant_feature_joint_matrix_x_z_w": constant.tolist(),
    "constant_feature_eigenvalues_real_imag": constant_eigs,
    "constant_feature_spectral_radius": float(max(abs(v[0] + 1j * v[1])
                                                   for v in constant_eigs)),
    "constant_feature_lyapunov_P_for_JtPJ_minus_P_eq_minus_I": lyap_p.tolist(),
    "constant_feature_lyapunov_P_min_eigenvalue": float(
        np.linalg.eigvalsh((lyap_p + lyap_p.T) / 2.0)[0]),
    "constant_feature_lyapunov_residual_fro": float(np.linalg.norm(lyap_residual)),
    "different_feature_case": {
        "sequence": [e1, e2],
        "feature_covariance": feature_covariance.tolist(),
        "feature_covariance_rank": int(np.linalg.matrix_rank(feature_covariance)),
        "feature_dimension": 3,
        "two_event_product_eigenvalues_real_imag": period2_eigs,
        "two_event_product_spectral_radius": float(max(abs(v[0] + 1j * v[1])
                                                       for v in period2_eigs)),
        "largest_per_event_rate": float(max(abs(v[0] + 1j * v[1])
                                            for v in period2_eigs) ** 0.5),
    },
}

assert constant.shape == (3, 3)
assert max(abs(v[0] + 1j * v[1]) for v in constant_eigs) < 1.0
assert result["constant_feature_lyapunov_P_min_eigenvalue"] > 0.0
assert result["constant_feature_lyapunov_residual_fro"] < 1e-10
assert result["different_feature_case"]["feature_covariance_rank"] == 2
assert period2.shape == (5, 5)
Path(__file__).with_name("joint_state_weight_matrix_results.json").write_text(
    json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, indent=2))
