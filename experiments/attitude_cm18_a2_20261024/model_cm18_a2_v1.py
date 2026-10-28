"""CM18-A2 inference: shared network with yaw-invariant current alphaBS input."""

from __future__ import annotations

from typing import Any

import numpy as np


INPUT_DIM = 18


def _vector(value: Any, size: int, name: str) -> np.ndarray:
    result = np.asarray(value, dtype=np.float64)
    if result.shape != (size,) or not np.isfinite(result).all():
        raise ValueError(f"{name} must be a finite vector of length {size}")
    return result


def initialize_random_parameters(seed: int, input_mean: Any, input_std: Any,
                                 train_axis_rms_rad_s2: Any) -> dict[str, np.ndarray]:
    """Create exactly the A1 Xavier initialization; this does not train."""
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
        "W1": xavier(18, 32), "b1": np.zeros(32, dtype=np.float64),
        "W2": xavier(32, 32), "b2": np.zeros(32, dtype=np.float64),
        "W3": xavier(32, 24), "b3": np.zeros(24, dtype=np.float64),
        "input_mean": mean.copy(), "input_std": std.copy(),
        "train_axis_rms_rad_s2": axis_rms.copy(),
    }


def _coefficients(raw: np.ndarray, p: dict[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    x_norm = (raw - p["input_mean"]) / p["input_std"]
    h1 = np.tanh(x_norm @ p["W1"].T + p["b1"])
    h2 = np.tanh(h1 @ p["W2"].T + p["b2"])
    coefficients = (h2 @ p["W3"].T + p["b3"]).reshape((-1, 3, 8), order="C")
    return coefficients, x_norm


def forward(raw_features: Any, parameters: dict[str, Any]) -> dict[str, np.ndarray]:
    """Full-input roll/pitch plus shared-weight RAW-zero-input yaw branch."""
    required = {"W1": (32, 18), "b1": (32,), "W2": (32, 32), "b2": (32,),
                "W3": (24, 32), "b3": (24,), "input_mean": (18,), "input_std": (18,),
                "train_axis_rms_rad_s2": (3,)}
    p: dict[str, np.ndarray] = {}
    for name, shape in required.items():
        if name not in parameters:
            raise ValueError(f"missing parameter {name}")
        value = np.asarray(parameters[name], dtype=np.float64)
        if value.shape != shape or not np.isfinite(value).all():
            raise ValueError(f"{name} must be finite with shape {shape}")
        p[name] = value
    if np.any(p["input_std"] < 1e-6) or np.any(p["train_axis_rms_rad_s2"] <= 0):
        raise ValueError("invalid normalizer or TRAIN target scale")

    x = np.asarray(raw_features, dtype=np.float64)
    single = x.ndim == 1
    if single:
        x = x[None, :]
    if x.ndim != 2 or x.shape[1] != INPUT_DIM or not np.isfinite(x).all():
        raise ValueError("raw_features must be finite with shape (18,) or (N, 18)")

    full, full_norm = _coefficients(x, p)
    yaw_raw = x.copy()
    yaw_raw[:, 3:5] = 0.0
    yaw, yaw_norm = _coefficients(yaw_raw, p)
    coefficients = full.copy()
    coefficients[:, 2, :] = yaw[:, 2, :]

    u, z = x[:, 7:11], x[:, 11:15]
    basis = np.concatenate((z / 2.0, u), axis=1)
    normalized_output = np.einsum("nij,nj->ni", coefficients, basis)
    physical_output = normalized_output * p["train_axis_rms_rad_s2"]
    if not all(np.isfinite(v).all() for v in (full_norm, yaw_norm, full, yaw, basis, normalized_output, physical_output)):
        raise FloatingPointError("A2 inference produced a non-finite value")

    result = {
        "coefficients_3x8": coefficients,
        "full_coefficients_3x8": full,
        "yaw_masked_coefficients_3x8": yaw,
        "basis_8": basis,
        "normalized_output": normalized_output,
        "physical_output_rad_s2": physical_output,
        "yaw_masked_raw_features": yaw_raw,
        "yaw_masked_normalized_features": yaw_norm,
    }
    if single:
        return {key: value[0] for key, value in result.items()}
    return result
