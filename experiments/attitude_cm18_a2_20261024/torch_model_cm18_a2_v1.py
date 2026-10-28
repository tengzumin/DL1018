"""Trainable CM18-A2 module with shared full-input and yaw-masked forwards."""

from __future__ import annotations

from typing import Any

import numpy as np
import torch
from torch import nn


class TorchCM18A2(nn.Module):
    """18 -> 32 -> 32 -> 24 shared network; yaw uses raw alphaBS x/y = 0."""

    def __init__(self, input_mean: Any, input_std: Any, train_axis_rms_rad_s2: Any) -> None:
        super().__init__()
        self.fc1 = nn.Linear(18, 32)
        self.fc2 = nn.Linear(32, 32)
        self.fc3 = nn.Linear(32, 24)
        mean = self._buffer_vector(input_mean, 18, "input_mean")
        std = self._buffer_vector(input_std, 18, "input_std")
        axis_rms = self._buffer_vector(train_axis_rms_rad_s2, 3, "train_axis_rms_rad_s2")
        if torch.any(std < 1e-6) or torch.any(axis_rms <= 0):
            raise ValueError("invalid normalizer or TRAIN target scale")
        self.register_buffer("input_mean", mean)
        self.register_buffer("input_std", std)
        self.register_buffer("train_axis_rms_rad_s2", axis_rms)
        self.double()

    @staticmethod
    def _buffer_vector(value: Any, size: int, name: str) -> torch.Tensor:
        result = torch.as_tensor(value, dtype=torch.float64, device="cpu").reshape(-1)
        if result.shape != (size,) or not torch.isfinite(result).all():
            raise ValueError(f"{name} must be a finite vector of length {size}")
        return result

    def load_numpy_parameters(self, parameters: dict[str, Any]) -> None:
        expected = {"W1": (32, 18), "b1": (32,), "W2": (32, 32), "b2": (32,),
                    "W3": (24, 32), "b3": (24,), "input_mean": (18,), "input_std": (18,),
                    "train_axis_rms_rad_s2": (3,)}
        destination = {"W1": self.fc1.weight, "b1": self.fc1.bias,
                      "W2": self.fc2.weight, "b2": self.fc2.bias,
                      "W3": self.fc3.weight, "b3": self.fc3.bias,
                      "input_mean": self.input_mean, "input_std": self.input_std,
                      "train_axis_rms_rad_s2": self.train_axis_rms_rad_s2}
        values = {}
        for name, shape in expected.items():
            if name not in parameters:
                raise ValueError(f"missing NumPy parameter {name}")
            value = torch.as_tensor(np.asarray(parameters[name]), dtype=destination[name].dtype,
                                    device=destination[name].device)
            if tuple(value.shape) != shape or not torch.isfinite(value).all():
                raise ValueError(f"{name} must be finite with shape {shape}")
            values[name] = value
        if torch.any(values["input_std"] < 1e-6) or torch.any(values["train_axis_rms_rad_s2"] <= 0):
            raise ValueError("invalid normalizer or TRAIN target scale")
        with torch.no_grad():
            for name, value in values.items():
                destination[name].copy_(value)

    def numpy_parameters(self) -> dict[str, np.ndarray]:
        return {"W1": self.fc1.weight.detach().cpu().numpy().copy(),
                "b1": self.fc1.bias.detach().cpu().numpy().copy(),
                "W2": self.fc2.weight.detach().cpu().numpy().copy(),
                "b2": self.fc2.bias.detach().cpu().numpy().copy(),
                "W3": self.fc3.weight.detach().cpu().numpy().copy(),
                "b3": self.fc3.bias.detach().cpu().numpy().copy(),
                "input_mean": self.input_mean.detach().cpu().numpy().copy(),
                "input_std": self.input_std.detach().cpu().numpy().copy(),
                "train_axis_rms_rad_s2": self.train_axis_rms_rad_s2.detach().cpu().numpy().copy()}

    def _coefficients(self, raw: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        normalized = (raw - self.input_mean) / self.input_std
        if not torch.isfinite(normalized).all():
            raise FloatingPointError("normalized input contains non-finite values")
        h1 = torch.tanh(self.fc1(normalized))
        h2 = torch.tanh(self.fc2(h1))
        coefficients = self.fc3(h2).reshape(-1, 3, 8)
        if not torch.isfinite(coefficients).all():
            raise FloatingPointError("coefficient matrix contains non-finite values")
        return coefficients, normalized

    def forward(self, raw_features: Any) -> dict[str, torch.Tensor]:
        if isinstance(raw_features, torch.Tensor):
            if raw_features.device != self.input_mean.device:
                raise ValueError("raw_features and model must use the same device")
            x = raw_features.to(dtype=self.input_mean.dtype)
        else:
            x = torch.as_tensor(raw_features, dtype=self.input_mean.dtype, device=self.input_mean.device)
        single = x.ndim == 1
        if single:
            x = x.unsqueeze(0)
        if x.ndim != 2 or x.shape[1] != 18 or not torch.isfinite(x).all():
            raise ValueError("raw_features must be finite with shape (18,) or (N, 18)")

        full, full_norm = self._coefficients(x)
        yaw_raw = x.clone()
        yaw_raw[:, 3:5] = 0.0
        yaw, yaw_norm = self._coefficients(yaw_raw)
        coefficients = torch.cat((full[:, :2, :], yaw[:, 2:3, :]), dim=1)
        basis = torch.cat((x[:, 11:15] / 2.0, x[:, 7:11]), dim=1)
        if not torch.isfinite(basis).all():
            raise FloatingPointError("morphology basis contains non-finite values")
        normalized_output = torch.bmm(coefficients, basis.unsqueeze(-1)).squeeze(-1)
        if not torch.isfinite(normalized_output).all():
            raise FloatingPointError("normalized output contains non-finite values")
        physical_output = normalized_output * self.train_axis_rms_rad_s2
        if not torch.isfinite(physical_output).all():
            raise FloatingPointError("physical output contains non-finite values")
        result = {"coefficients_3x8": coefficients,
                  "full_coefficients_3x8": full,
                  "yaw_masked_coefficients_3x8": yaw,
                  "basis_8": basis,
                  "normalized_output": normalized_output,
                  "physical_output_rad_s2": physical_output,
                  "yaw_masked_raw_features": yaw_raw,
                  "yaw_masked_normalized_features": yaw_norm}
        if single:
            return {key: value[0] for key, value in result.items()}
        return result
