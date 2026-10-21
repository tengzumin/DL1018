from __future__ import annotations

import math
import os
import sys
from pathlib import Path

import numpy as np
os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
import torch
from torch import nn
from torch.nn import functional as F

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "training"))
from models import KANModel  # noqa: E402


def phi_from_hidden(h: torch.Tensor) -> torch.Tensor:
    one = torch.ones((h.shape[0], 1), dtype=h.dtype, device=h.device)
    v = torch.cat((h, one), dim=1)
    return v / torch.sqrt(1.0 + torch.sum(h * h, dim=1, keepdim=True))


class FeatureBase(nn.Module):
    sequence = False
    family = ""

    def __init__(self, input_dim: int, mu: np.ndarray, sigma: np.ndarray):
        super().__init__()
        self.input_dim = int(input_dim)
        self.register_buffer("input_mu", torch.as_tensor(mu, dtype=torch.float32).reshape(1, input_dim))
        self.register_buffer("input_sigma", torch.as_tensor(sigma, dtype=torch.float32).reshape(1, input_dim))
        self.readout = nn.Linear(33, 3, bias=False)

    def normalize(self, x: torch.Tensor) -> torch.Tensor:
        if x.ndim == 3:
            return (x - self.input_mu[:, None, :]) / self.input_sigma[:, None, :]
        return (x - self.input_mu) / self.input_sigma

    def hidden(self, x: torch.Tensor) -> torch.Tensor:
        raise NotImplementedError

    def encode(self, x: torch.Tensor) -> torch.Tensor:
        return phi_from_hidden(self.hidden(x))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.readout(self.encode(x))


class MLPFeature(FeatureBase):
    family = "MLP"

    def __init__(self, input_dim: int, mu: np.ndarray, sigma: np.ndarray):
        super().__init__(input_dim, mu, sigma)
        self.fc1 = nn.Linear(input_dim, 64)
        self.fc2 = nn.Linear(64, 32)
        self.fc3 = nn.Linear(32, 32)

    def hidden(self, x: torch.Tensor) -> torch.Tensor:
        if x.ndim == 3:
            x = x[:, -1, :]
        z = self.normalize(x)
        return torch.tanh(self.fc3(F.silu(self.fc2(F.silu(self.fc1(z))))))


class TCNResidualBlock(nn.Module):
    def __init__(self, width: int, dilation: int):
        super().__init__()
        self.dilation = int(dilation)
        self.conv = nn.Conv1d(width, width, kernel_size=3, dilation=dilation)
        self.mix = nn.Conv1d(width, width, kernel_size=1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        left = 2 * self.dilation
        y = self.conv(F.pad(x, (left, 0)))
        y = self.mix(F.silu(y))
        return F.silu(x + y)


class TCNFeature(FeatureBase):
    sequence = True
    family = "TCN"

    def __init__(self, input_dim: int, mu: np.ndarray, sigma: np.ndarray, window: int):
        super().__init__(input_dim, mu, sigma)
        self.window = int(window)
        dilations = (1, 2, 4, 8, 16) if window == 32 else (1, 2, 4, 8, 16, 32, 64)
        self.dilations = tuple(dilations)
        self.receptive_field = 1 + 2 * sum(dilations)
        self.stem = nn.Conv1d(input_dim, 16, kernel_size=1)
        self.blocks = nn.ModuleList(TCNResidualBlock(16, d) for d in dilations)
        self.project = nn.Linear(16, 32)

    def hidden(self, x: torch.Tensor) -> torch.Tensor:
        if x.ndim != 3 or x.shape[1:] != (self.window, self.input_dim):
            raise ValueError(f"TCN expects [batch,{self.window},{self.input_dim}], got {tuple(x.shape)}")
        z = self.normalize(x).transpose(1, 2)
        h = self.stem(z)
        for block in self.blocks:
            h = block(h)
        return torch.tanh(self.project(h[:, :, -1]))


class GRUFeature(FeatureBase):
    sequence = True
    family = "GRU"

    def __init__(self, input_dim: int, mu: np.ndarray, sigma: np.ndarray, window: int = 32):
        super().__init__(input_dim, mu, sigma)
        self.window = int(window)
        self.gru = nn.GRU(input_dim, 32, num_layers=1, batch_first=True)
        self.project = nn.Linear(32, 32)

    def hidden(self, x: torch.Tensor) -> torch.Tensor:
        if x.ndim != 3 or x.shape[1:] != (self.window, self.input_dim):
            raise ValueError(f"GRU expects [batch,{self.window},{self.input_dim}], got {tuple(x.shape)}")
        z = self.normalize(x)
        _, h_n = self.gru(z)  # zero initial state: each episode-window is independent
        return torch.tanh(self.project(h_n[-1]))


class DSSMFeature(FeatureBase):
    sequence = True
    family = "DSSM"

    def __init__(self, input_dim: int, mu: np.ndarray, sigma: np.ndarray, window: int = 32):
        super().__init__(input_dim, mu, sigma)
        self.window = int(window)
        self.input_encoder = nn.Linear(input_dim, 32)
        self.project = nn.Linear(32, 32)
        tau = torch.logspace(math.log10(0.02), math.log10(1.28), 32)
        self.log_tau = nn.Parameter(torch.log(tau))

    def hidden(self, x: torch.Tensor) -> torch.Tensor:
        if x.ndim != 3 or x.shape[1:] != (self.window, self.input_dim):
            raise ValueError(f"DSSM expects [batch,{self.window},{self.input_dim}], got {tuple(x.shape)}")
        z = self.normalize(x)
        drive = torch.tanh(self.input_encoder(z))
        tau = torch.exp(self.log_tau).clamp(0.005, 5.0)
        alpha = torch.exp(-0.01 / tau)  # exact diagonal discretization at dt=0.01 s
        state = torch.zeros_like(drive[:, 0, :])
        for t in range(self.window):
            state = alpha * state + (1.0 - alpha) * drive[:, t, :]
        return torch.tanh(self.project(state))


class KANFeature(KANModel):
    family = "KAN"
    sequence = False

    def __init__(self, mu: np.ndarray, sigma: np.ndarray):
        super().__init__(14, mu, sigma, position_unclipped_silu=True)

    def hidden(self, x: torch.Tensor) -> torch.Tensor:
        # Existing DL1018 KAN implementation returns the required normalized phi.
        if x.ndim == 3:
            x = x[:, -1, :]
        return self.encode(x)
