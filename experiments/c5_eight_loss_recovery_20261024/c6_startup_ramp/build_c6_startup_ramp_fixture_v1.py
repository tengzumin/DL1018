"""Build four synthetic, deterministic C6 inputs and expected one-step outputs."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import delayed_prediction_kernel as kernel

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "C6_CROSSLANG_FIXTURE_v1.json"
CASES = []
SEED = 2026102406


def one_hot(i: int) -> np.ndarray:
    x = np.zeros(33, dtype=np.float64)
    x[i] = 1.0
    return x


def add_case(name, W, phi, s, n, previous=None):
    args = {
        "W": np.asarray(W, dtype=np.float64),
        "phi": np.asarray(phi, dtype=np.float64),
        "s_eff": np.asarray(s, dtype=np.float64),
        "n": int(n),
        "t_n": n * 0.001,
    }
    if previous is not None:
        old_phi, y_prev, j = previous
        args.update(
            phi_prev=np.asarray(old_phi, dtype=np.float64),
            y_prev=np.asarray(y_prev, dtype=np.float64),
            previous_index=int(j),
            previous_time_s=j * 0.001,
        )
    result = kernel.delayed_prediction_step(
        args["W"], args["phi"], args["s_eff"], args["n"], args["t_n"],
        **{k: v for k, v in args.items()
           if k not in {"W", "phi", "s_eff", "n", "t_n"}},
    )
    case = {
        "name": name,
        "input": {
            "W": args["W"].tolist(),
            "phi": args["phi"].tolist(),
            "s_eff": args["s_eff"].tolist(),
            "n": args["n"],
            "t_n": args["t_n"],
        },
        "expected": {
            "beta": result["beta"],
            "raw": result["raw"].tolist(),
            "applied": result["applied"].tolist(),
            "prediction_gradient": result["prediction_gradient"].tolist(),
            "preprojection_candidate": result["preprojection_candidate"].tolist(),
            "W_next": result["W_next"].tolist(),
        },
    }
    if previous is not None:
        case["input"].update(
            phi_prev=args["phi_prev"].tolist(),
            y_prev=args["y_prev"].tolist(),
            previous_index=args["previous_index"],
            previous_time_s=args["previous_time_s"],
        )
    CASES.append(case)


rng = np.random.default_rng(SEED)
W = np.zeros((33, 3), dtype=np.float64)
W[0] = [0.25, -0.5, 0.75]
W[1] = [-0.2, 0.15, 0.1]
W[7] = [0.03, -0.04, 0.02]
W[32] = [-0.1, 0.08, -0.05]
add_case("first_ready_no_history", W.copy(), one_hot(0), [1.0, -2.0, 3.0], 320)
add_case(
    "fractional_beta_prediction_update", W.copy(), one_hot(1), [-2.0, 0.5, 1.5], 330,
    (one_hot(0), [0.1, -0.2, 0.05], 320),
)

W_box = np.zeros((33, 3), dtype=np.float64)
W_box[0] = [59.9, -59.9, 0.25]
W_box[1] = [0.03, -0.04, 0.02]
add_case(
    "fractional_beta_joint_projection", W_box, one_hot(0), [-7.0, 7.0, 0.0], 900,
    (one_hot(1), [-15.0, 15.0, 0.0], 890),
)
add_case(
    "beta_one_same_formula", W.copy(), one_hot(1), [0.2, -0.4, 0.6], 1800,
    (one_hot(0), [-0.3, 0.1, 0.2], 1790),
)

# Fixture invariants that distinguish the intended C6 factor and preserve C5's clock.
assert CASES[0]["expected"]["beta"] == 321 * 0.001 / 1.8
assert CASES[1]["expected"]["beta"] == 331 * 0.001 / 1.8
assert CASES[3]["expected"]["beta"] == 1.0
assert CASES[2]["expected"]["preprojection_candidate"][0][0] > 60
assert CASES[2]["expected"]["preprojection_candidate"][0][1] < -60

matlab_path = HERE / "delayed_prediction_step_candidate.m"
python_path = HERE / "delayed_prediction_kernel.py"
fixture = {
    "schema": "C6_STARTUP_RAMP_CROSSLANG_FIXTURE_V1",
    "candidate": "C6_STARTUP_PREDICTION_RAMP",
    "tolerance_abs": 2e-12,
    "plant_dt_s": 0.001,
    "event_period_s": 0.01,
    "beta_rise_s": 1.8,
    "gamma": 12.0,
    "lambda_per_s": 0.002,
    "tau_s": 1.0,
    "rho": 0.01,
    "prediction_clip": 3.0,
    "weight_clip": 60.0,
    "seed": SEED,
    "python_kernel_sha256": hashlib.sha256(python_path.read_bytes()).hexdigest(),
    "matlab_helper_sha256": hashlib.sha256(matlab_path.read_bytes()).hexdigest(),
    "cases": CASES,
    "provenance": "Synthetic fixed arrays only; no MAT/raw data, Plant, training, GPU, or TEST data.",
}
FIXTURE.write_text(json.dumps(fixture, indent=2, allow_nan=False) + "\n", encoding="utf-8")
print(json.dumps({
    "status": "FIXTURE_BUILT_SYNTHETIC_ONLY",
    "case_count": len(CASES),
    "fixture_sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
    "python_kernel_sha256": fixture["python_kernel_sha256"],
    "matlab_helper_sha256": fixture["matlab_helper_sha256"],
}, indent=2))