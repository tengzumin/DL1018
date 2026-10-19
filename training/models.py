"""DL1018's two fixed X-KAN regressors, extracted from the V2/V3.6 sources."""
from __future__ import annotations

import torch
from torch import nn
from torch.nn import functional as F


KNOTS = (-4.0,) * 4 + (-2.4, -0.8, 0.8, 2.4) + (4.0,) * 4


def cubic_bspline_basis(x: torch.Tensor, knots: torch.Tensor) -> torch.Tensor:
    xx = x.unsqueeze(-1)
    lo, hi = knots[:-1], knots[1:]
    basis = ((xx >= lo) & (xx < hi)).to(x.dtype)
    for degree in range(1, 4):
        count = len(knots) - degree - 1
        left_den = knots[degree:degree + count] - knots[:count]
        right_den = knots[degree + 1:degree + 1 + count] - knots[1:1 + count]
        left_num = xx - knots[:count]
        right_num = knots[degree + 1:degree + 1 + count] - xx
        left = torch.where(left_den > 0, left_num / left_den.clamp_min(1e-12), 0.0) * basis[..., :count]
        right = torch.where(right_den > 0, right_num / right_den.clamp_min(1e-12), 0.0) * basis[..., 1:count + 1]
        basis = left + right
    basis = torch.where(xx == 4.0,
                        F.one_hot(torch.full_like(x, 7, dtype=torch.long), 8).to(x.dtype), basis)
    return basis


class KANModel(nn.Module):
    """Position X14 or attitude X29 KAN; sequence input uses its newest event."""

    def __init__(self, input_dim: int, mu, sigma, *, position_unclipped_silu: bool):
        super().__init__()
        if input_dim not in (14, 29):
            raise ValueError(f"DL1018 KAN input must be X14 or X29, got {input_dim}")
        self.input_dim = int(input_dim)
        self.position_unclipped_silu = bool(position_unclipped_silu)
        self.register_buffer("input_mu", torch.as_tensor(mu, dtype=torch.float32).reshape(1, input_dim, 1))
        self.register_buffer("input_sigma", torch.as_tensor(sigma, dtype=torch.float32).reshape(1, input_dim, 1))
        self.register_buffer("knots", torch.tensor(KNOTS, dtype=torch.float32))
        self.spline_W = nn.Parameter(torch.empty(32, input_dim, 8))
        nn.init.normal_(self.spline_W, std=0.04)
        self.linear_W = nn.Parameter(torch.empty(32, input_dim))
        nn.init.xavier_uniform_(self.linear_W)
        self.feature_b = nn.Parameter(torch.zeros(32))
        self.readout = nn.Linear(33, 3, bias=False)

    def encode(self, x: torch.Tensor) -> torch.Tensor:
        if x.ndim == 2:
            if x.shape[1] != self.input_dim:
                raise ValueError(f"Expected [batch,{self.input_dim}], got {tuple(x.shape)}")
            current = (x - self.input_mu[:, :, 0]) / self.input_sigma[:, :, 0]
        elif x.ndim == 3:
            if x.shape[1] != self.input_dim or x.shape[2] != 32:
                raise ValueError(f"Expected [batch,{self.input_dim},32], got {tuple(x.shape)}")
            current = ((x - self.input_mu) / self.input_sigma)[:, :, -1]
        else:
            raise ValueError("KAN input must be a feature row or 32-event window")
        clipped = current.clamp(-4.0, 4.0)
        basis = cubic_bspline_basis(clipped, self.knots)
        silu_input = current if self.input_dim == 14 and self.position_unclipped_silu else clipped
        h = torch.tanh(torch.einsum("nib,oib->no", basis, self.spline_W)
                       + F.linear(F.silu(silu_input), self.linear_W) + self.feature_b)
        one = torch.ones((h.shape[0], 1), device=h.device, dtype=h.dtype)
        phi = torch.cat((h, one), dim=1)
        return phi / torch.sqrt(1.0 + torch.sum(h * h, dim=1, keepdim=True))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.readout(self.encode(x))


def PositionModel(mu, sigma) -> KANModel:
    return KANModel(14, mu, sigma, position_unclipped_silu=True)


def AttitudeModel(mu, sigma) -> KANModel:
    return KANModel(29, mu, sigma, position_unclipped_silu=False)
