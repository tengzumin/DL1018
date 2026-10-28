"""CM18-A1 inference and deterministic cross-language fixture export.

Input order: omega_B(3), alpha_BS(3), thrust/mass(1), current u(4),
past-only command integral z(4), previous-complete-interval torque mean a(3).
The network predicts 24 row-major coefficients reshaped to A[3, 8]. Its
output is A @ [z/2, u], so it has no independent physical-output bias.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np


INPUT_DIM = 18


def _vector(value: Any, size: int, name: str) -> np.ndarray:
    result = np.asarray(value, dtype=np.float64)
    if result.shape != (size,) or not np.isfinite(result).all():
        raise ValueError(f"{name} must be a finite vector of length {size}")
    return result


def initialize_random_parameters(
    seed: int,
    input_mean: Any,
    input_std: Any,
    train_axis_rms_rad_s2: Any,
) -> dict[str, np.ndarray]:
    """Create fresh Xavier-uniform weights; this does not train the model."""
    if isinstance(seed, bool) or not isinstance(seed, (int, np.integer)):
        raise ValueError("seed must be an integer")
    mean = _vector(input_mean, INPUT_DIM, "input_mean")
    std = _vector(input_std, INPUT_DIM, "input_std")
    if np.any(std < 1e-6):
        raise ValueError("input_std must include the 1e-6 TRAIN-only floor")
    axis_rms = _vector(train_axis_rms_rad_s2, 3, "train_axis_rms_rad_s2")
    if np.any(axis_rms <= 0):
        raise ValueError("train_axis_rms_rad_s2 must be positive")

    rng = np.random.default_rng(int(seed))

    def xavier(fan_in: int, fan_out: int) -> np.ndarray:
        bound = np.sqrt(6.0 / (fan_in + fan_out))
        return rng.uniform(-bound, bound, size=(fan_out, fan_in))

    return {
        "W1": xavier(18, 32),
        "b1": np.zeros(32, dtype=np.float64),
        "W2": xavier(32, 32),
        "b2": np.zeros(32, dtype=np.float64),
        "W3": xavier(32, 24),
        "b3": np.zeros(24, dtype=np.float64),
        "input_mean": mean.copy(),
        "input_std": std.copy(),
        "train_axis_rms_rad_s2": axis_rms.copy(),
    }


def forward(raw_features: Any, parameters: dict[str, Any]) -> dict[str, np.ndarray]:
    """Return coefficient matrix, normalized output, and physical rad/s^2."""
    required = {
        "W1": (32, 18),
        "b1": (32,),
        "W2": (32, 32),
        "b2": (32,),
        "W3": (24, 32),
        "b3": (24,),
        "input_mean": (18,),
        "input_std": (18,),
        "train_axis_rms_rad_s2": (3,),
    }
    arrays: dict[str, np.ndarray] = {}
    for name, shape in required.items():
        if name not in parameters:
            raise ValueError(f"missing parameter {name}")
        value = np.asarray(parameters[name], dtype=np.float64)
        if value.shape != shape or not np.isfinite(value).all():
            raise ValueError(f"{name} must be finite with shape {shape}")
        arrays[name] = value
    if np.any(arrays["input_std"] < 1e-6):
        raise ValueError("input_std must include the 1e-6 TRAIN-only floor")
    if np.any(arrays["train_axis_rms_rad_s2"] <= 0):
        raise ValueError("train_axis_rms_rad_s2 must be positive")

    x = np.asarray(raw_features, dtype=np.float64)
    single = x.ndim == 1
    if single:
        x = x[None, :]
    if x.ndim != 2 or x.shape[1] != INPUT_DIM or not np.isfinite(x).all():
        raise ValueError("raw_features must be finite with shape (18,) or (N, 18)")

    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        x_norm = (x - arrays["input_mean"]) / arrays["input_std"]
    if not np.isfinite(x_norm).all():
        raise FloatingPointError("normalized input contains non-finite values")
    h1 = np.tanh(x_norm @ arrays["W1"].T + arrays["b1"])
    h2 = np.tanh(h1 @ arrays["W2"].T + arrays["b2"])
    flat_coefficients = h2 @ arrays["W3"].T + arrays["b3"]
    coefficients = flat_coefficients.reshape((-1, 3, 8), order="C")
    if not np.isfinite(coefficients).all():
        raise FloatingPointError("coefficient matrix contains non-finite values")

    u = x[:, 7:11]
    z = x[:, 11:15]
    basis = np.concatenate((z / 2.0, u), axis=1)
    if not np.isfinite(basis).all():
        raise FloatingPointError("morphology basis contains non-finite values")
    with np.errstate(over="ignore", invalid="ignore"):
        normalized_output = np.einsum("nij,nj->ni", coefficients, basis)
    if not np.isfinite(normalized_output).all():
        raise FloatingPointError("normalized output contains non-finite values")
    with np.errstate(over="ignore", invalid="ignore"):
        physical_output = normalized_output * arrays["train_axis_rms_rad_s2"]
    if not np.isfinite(physical_output).all():
        raise FloatingPointError("physical output contains non-finite values")

    if single:
        return {
            "coefficients_3x8": coefficients[0],
            "basis_8": basis[0],
            "normalized_output": normalized_output[0],
            "physical_output_rad_s2": physical_output[0],
        }
    return {
        "coefficients_3x8": coefficients,
        "basis_8": basis,
        "normalized_output": normalized_output,
        "physical_output_rad_s2": physical_output,
    }


def write_parity_fixture(path: Path) -> None:
    """Write shared synthetic parameters and Python references; never overwrite."""
    path = Path(path)
    if not path.parent.is_dir():
        raise FileNotFoundError(f"fixture directory does not exist: {path.parent}")
    if path.exists():
        raise FileExistsError(path)

    parameters = initialize_random_parameters(
        seed=0xA1C018,
        input_mean=np.linspace(-0.2, 0.2, 18),
        input_std=np.linspace(0.5, 1.5, 18),
        train_axis_rms_rad_s2=np.array([9.040297262964435, 8.610649916022812, 0.5009756743917716]),
    )
    x = np.linspace(-0.75, 0.8, 18)
    x[7:11] = [-1.0, 0.0, 1.0, -1.0]
    x[11:15] = [0.02, 0.04, 0.01, 0.03]
    nonzero = forward(x, parameters)

    x_zero = x.copy()
    x_zero[7:15] = 0.0
    zero = forward(x_zero, parameters)
    if not np.array_equal(zero["physical_output_rad_s2"], np.zeros(3)):
        raise AssertionError("zero morphology basis must produce exactly zero output")

    fixture = {
        "schema": "CM18_A1_PARITY_FIXTURE_V1",
        "seed": 0xA1C018,
        "raw_features": x.tolist(),
        "zero_basis_features": x_zero.tolist(),
        "parameters": {key: value.tolist() for key, value in parameters.items()},
        "expected": {
            "coefficients_3x8": nonzero["coefficients_3x8"].tolist(),
            "basis_8": nonzero["basis_8"].tolist(),
            "normalized_output": nonzero["normalized_output"].tolist(),
            "physical_output_rad_s2": nonzero["physical_output_rad_s2"].tolist(),
            "zero_physical_output_rad_s2": zero["physical_output_rad_s2"].tolist(),
        },
        "tolerance_abs": 1e-11,
    }
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(fixture, stream, indent=2, allow_nan=False)
        stream.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export-parity-fixture", type=Path, required=True)
    args = parser.parse_args()
    write_parity_fixture(args.export_parity_fixture)


if __name__ == "__main__":
    main()
