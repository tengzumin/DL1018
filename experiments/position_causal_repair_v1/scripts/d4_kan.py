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


class PositionKAN(nn.Module):
    """Isolated X14/X20 replica of the frozen DL1018 position KAN."""

    def __init__(self, input_dim: int, mu, sigma):
        super().__init__()
        if input_dim not in (14, 20):
            raise ValueError(input_dim)
        self.input_dim = input_dim
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
        if x.ndim == 3:
            if x.shape[1] != self.input_dim or x.shape[2] != 32:
                raise ValueError(f"Expected [batch,{self.input_dim},32], got {tuple(x.shape)}")
            cur = ((x - self.input_mu) / self.input_sigma)[:, :, -1]
        elif x.ndim == 2:
            if x.shape[1] != self.input_dim:
                raise ValueError(f"Expected [batch,{self.input_dim}], got {tuple(x.shape)}")
            cur = (x - self.input_mu[:, :, 0]) / self.input_sigma[:, :, 0]
        else:
            raise ValueError(f"Unsupported input shape {tuple(x.shape)}")
        clipped = cur.clamp(-4.0, 4.0)
        basis = cubic_bspline_basis(clipped, self.knots)
        h = torch.tanh(torch.einsum("nib,oib->no", basis, self.spline_W)
                       + F.linear(F.silu(cur), self.linear_W) + self.feature_b)
        one = torch.ones((h.shape[0], 1), dtype=h.dtype, device=h.device)
        phi = torch.cat((h, one), dim=1)
        return phi / torch.sqrt(1.0 + torch.sum(h * h, dim=1, keepdim=True))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.readout(self.encode(x))


def from_initial(checkpoint_path, norm_path, input_dim: int, mu=None, sigma=None) -> PositionKAN:
    n = __import__("numpy").load(norm_path)
    old_mu, old_sigma = n["mu"].astype("float32"), n["sigma"].astype("float32")
    if input_dim == 14:
        model = PositionKAN(14, old_mu, old_sigma)
        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
        model.load_state_dict(checkpoint["state_dict"])
        return model
    if input_dim != 20 or mu is None or sigma is None:
        raise ValueError("X20 initialization requires its TRAIN-only normalizer")
    model = PositionKAN(20, mu, sigma)
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    base = checkpoint["state_dict"]
    with torch.no_grad():
        model.input_mu.copy_(torch.as_tensor(mu, dtype=torch.float32).reshape(1, 20, 1))
        model.input_sigma.copy_(torch.as_tensor(sigma, dtype=torch.float32).reshape(1, 20, 1))
        model.knots.copy_(base["knots"])
        model.spline_W[:, :14].copy_(base["spline_W"])
        model.spline_W[:, 14:].zero_()
        model.linear_W[:, :14].copy_(base["linear_W"])
        model.linear_W[:, 14:].zero_()
        model.feature_b.copy_(base["feature_b"])
        model.readout.weight.copy_(base["readout.weight"])
    return model
