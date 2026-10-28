import json
from pathlib import Path
import numpy as np

OUT = Path(__file__).with_name("ALGEBRA_CHECK.json")

# Fixed, synthetic 2-feature x 3-output case; this checks the identities only.
h, gamma, beta, lam, rho = 0.01, 12.0, 0.6, 0.002, 0.01
W_star = np.array([[4.0, -2.0, 1.0], [1.0, 3.0, -4.0]])
W = np.array([[59.999, 2.0, -1.0], [-1.0, 4.0, 2.0]])
phi_k = np.array([1.0, 1.0]) / np.sqrt(2.0)
phi_j = np.array([0.6, 0.8])
s_eff = np.array([1.2, -0.7, 0.9])
y = np.array([300.0, -260.0, 180.0])
Wtilde = W_star - W

T = h * gamma * beta * np.outer(phi_k, s_eff)
L = h * lam * W
e = W.T @ phi_j - y
P = rho * np.outer(phi_j, e)
A = T + L + P
candidate = W - A
W_next = np.clip(candidate, -60.0, 60.0)
R = W_next - candidate

direct_sq = float(np.sum(A * A))
expanded_sq = float(
    (h * gamma * beta) ** 2 * np.dot(phi_k, phi_k) * np.dot(s_eff, s_eff)
    + (h * lam) ** 2 * np.sum(W * W)
    + rho ** 2 * np.dot(phi_j, phi_j) * np.dot(e, e)
    + 2.0 * h ** 2 * gamma * beta * lam * (s_eff @ (W.T @ phi_k))
    + 2.0 * h * gamma * beta * rho * (phi_k @ phi_j) * (s_eff @ e)
    + 2.0 * h * lam * rho * (e @ (W.T @ phi_j))
)
assert abs(direct_sq - expanded_sq) <= 1e-10 * max(1.0, direct_sq)

E0 = float(np.sum((W_star - W) ** 2) / (2.0 * gamma))
E1 = float(np.sum((W_star - W_next) ** 2) / (2.0 * gamma))
delta_E = E1 - E0
joint_bound = float(
    np.sum(Wtilde * A) / gamma
    + (direct_sq - np.sum(R * R)) / (2.0 * gamma)
)
assert delta_E <= joint_bound + 1e-12

# Check output-error decomposition with all vectors in R^3.
z = W.T @ phi_k
d_star = W_star.T @ phi_k
clip_z = np.clip(z, -3.0, 3.0)
u = beta * clip_z
lhs_output = u - d_star
rhs_output = -beta * (Wtilde.T @ phi_k) + (beta - 1.0) * d_star + beta * (clip_z - z)
assert np.allclose(lhs_output, rhs_output, rtol=0.0, atol=1e-12)

# Isolated exact-label prediction step, with one projection after the whole step.
q = Wtilde.T @ phi_j
y_exact = W_star.T @ phi_j
e_exact = W.T @ phi_j - y_exact
P_exact = rho * np.outer(phi_j, e_exact)
candidate_exact = W - P_exact
W_exact_next = np.clip(candidate_exact, -60.0, 60.0)
R_exact = W_exact_next - candidate_exact
delta_E_exact = float(
    (np.sum((W_star - W_exact_next) ** 2) - np.sum((W_star - W) ** 2))
    / (2.0 * gamma)
)
contraction_coeff = rho - rho * rho / 2.0
isolated_bound = float(
    -contraction_coeff * np.dot(q, q) / gamma
    - np.sum(R_exact * R_exact) / (2.0 * gamma)
)
assert abs(contraction_coeff - 0.00995) < 1e-15
assert delta_E_exact <= isolated_bound + 1e-12

result = {
    "status": "PASS_SYNTHETIC_SINGLE_STEP_ALGEBRA_ONLY",
    "scope": "fixed synthetic arrays; no model, experiment raw, training, optimizer, Plant, or TEST data",
    "dimensions": {"W": [2, 3], "phi_current": [2], "phi_old": [2], "s_eff": [3], "y": [3]},
    "units": {
        "W_and_acceleration_outputs": "m/s^2",
        "s_eff": "m/s",
        "phi": "dimensionless",
        "h": "s",
        "gamma": "s^-2",
        "lambda": "s^-1",
        "rho": "dimensionless",
    },
    "parameters": {"h": h, "gamma": gamma, "beta": beta, "lambda": lam, "rho": rho},
    "joint_update": {
        "direct_norm_A_squared": direct_sq,
        "expanded_norm_A_squared": expanded_sq,
        "absolute_expansion_difference": abs(direct_sq - expanded_sq),
        "delta_E": delta_E,
        "projection_bound": joint_bound,
        "projection_bound_slack": joint_bound - delta_E,
        "projection_residual_norm": float(np.linalg.norm(R)),
        "output_decomposition_max_abs_difference": float(np.max(np.abs(lhs_output - rhs_output))),
    },
    "isolated_exact_label_prediction": {
        "rho_minus_rho_squared_over_2": contraction_coeff,
        "delta_E": delta_E_exact,
        "conditional_bound": isolated_bound,
        "bound_slack": isolated_bound - delta_E_exact,
        "projection_residual_norm": float(np.linalg.norm(R_exact)),
    },
}
OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, indent=2))

