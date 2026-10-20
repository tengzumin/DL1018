from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "training"))
from models import KNOTS, cubic_bspline_basis  # noqa: E402


class KANFeature20(nn.Module):
    """The existing single-frame KAN encoder widened to the frozen X20 input."""

    family = "KAN"
    sequence = False
    input_dim = 20

    def __init__(self, mu: np.ndarray, sigma: np.ndarray):
        super().__init__()
        self.register_buffer("input_mu", torch.as_tensor(mu, dtype=torch.float32).reshape(1, 20, 1))
        self.register_buffer("input_sigma", torch.as_tensor(sigma, dtype=torch.float32).reshape(1, 20, 1))
        self.register_buffer("knots", torch.tensor(KNOTS, dtype=torch.float32))
        self.spline_W = nn.Parameter(torch.empty(32, 20, 8))
        nn.init.normal_(self.spline_W, std=0.04)
        self.linear_W = nn.Parameter(torch.empty(32, 20))
        nn.init.xavier_uniform_(self.linear_W)
        self.feature_b = nn.Parameter(torch.zeros(32))
        self.readout = nn.Linear(33, 3, bias=False)

    def encode(self, x: torch.Tensor) -> torch.Tensor:
        if x.ndim != 2 or x.shape[1] != 20:
            raise ValueError(f"KAN20 expects [batch,20], got {tuple(x.shape)}")
        current = (x - self.input_mu[:, :, 0]) / self.input_sigma[:, :, 0]
        clipped = current.clamp(-4.0, 4.0)
        basis = cubic_bspline_basis(clipped, self.knots)
        h = torch.tanh(torch.einsum("nib,oib->no", basis, self.spline_W)
                       + F.linear(F.silu(clipped), self.linear_W) + self.feature_b)
        one = torch.ones((h.shape[0], 1), device=h.device, dtype=h.dtype)
        return torch.cat((h, one), dim=1) / torch.sqrt(1.0 + torch.sum(h * h, dim=1, keepdim=True))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.readout(self.encode(x))
