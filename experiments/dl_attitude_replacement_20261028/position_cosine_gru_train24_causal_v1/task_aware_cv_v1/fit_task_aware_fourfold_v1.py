#!/usr/bin/env python3
"""Fit the fixed task-aware residual-GRU arm on grouped cosine-GRU TRAIN_C5_24 scenes."""
from __future__ import annotations

import hashlib
import json
import math
import os
import random
import time
from pathlib import Path

# Required by deterministic cuBLAS on CUDA 10.2+; set before importing/initializing torch.
os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

import numpy as np
import torch
from scipy.spatial.transform import Rotation
from torch import nn
from torch.autograd import Function
from torch.nn import functional as F

from task_aware_common import (
    DATA_DIR, DT_S, EVENT_DT_S, FILTER_DAMPING, FILTER_LIMIT, FILTER_WN, ROOT,
    force_to_euler, load_locked_inputs, replay_filter, sha256, wrap,
)


OUT = Path(__file__).resolve().parent
AUDIT_PATH = OUT / "PARENT_TASK_FILTER_REPLAY_AUDIT_v1.json"
FORECAST_DIR = OUT.parent / "gru_residual_cv_v1"
NO_TASK_OOF_PATH = FORECAST_DIR / "CV_OOF_PREDICTIONS_v1.npz"
NO_TASK_LOCK_PATH = FORECAST_DIR / "SOURCE_LOCK_v1.json"
NO_TASK_RESULTS_PATH = FORECAST_DIR / "RESULTS_v1.json"
NO_TASK_CHECKPOINTS = FORECAST_DIR / "checkpoints"
OOF_OUT = OUT / "TASK_AWARE_CV_OOF_v1.npz"
RESULTS_OUT = OUT / "TASK_AWARE_CV_RESULTS_v1.json"
LOCK_OUT = OUT / "TASK_AWARE_SOURCE_LOCK_v1.json"
CHECKPOINT_DIR = OUT / "checkpoints"
SEED = 20261028
STEPS = 300
LR = 1e-3
LAMBDA_SMOOTH = 0.01
LAMBDA_TASK = 0.1
TASK_WEIGHT_DEFINITION = "0.1 * mean(theta_SO3_rad^2) over all 20,000 frozen 1-ms transitions; no normalization or adaptive threshold"
BETA_RISE_S = 1.8
ACTION_LIMIT = 3.0
DELTA_LIMIT = 0.5
TIME_TOL_S = 2e-6


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def quat_xyz(e: torch.Tensor) -> torch.Tensor:
    r, p, y = e.unbind(-1)
    cr, sr = torch.cos(r / 2), torch.sin(r / 2)
    cp, sp = torch.cos(p / 2), torch.sin(p / 2)
    cy, sy = torch.cos(y / 2), torch.sin(y / 2)
    return torch.stack((cr * cp * cy + sr * sp * sy,
                        sr * cp * cy - cr * sp * sy,
                        cr * sp * cy + sr * cp * sy,
                        cr * cp * sy - sr * sp * cy), dim=-1)


def quat_mul(a: torch.Tensor, b: torch.Tensor) -> torch.Tensor:
    aw, ax, ay, az = a.unbind(-1)
    bw, bx, by, bz = b.unbind(-1)
    return torch.stack((aw * bw - ax * bx - ay * by - az * bz,
                        aw * bx + ax * bw + ay * bz - az * by,
                        aw * by - ax * bz + ay * bw + az * bx,
                        aw * bz + ax * by - ay * bx + az * bw), dim=-1)


def so3_angle_torch(a: torch.Tensor, b: torch.Tensor) -> torch.Tensor:
    """Geodesic angle between SciPy Rotation.from_euler('xyz', ...) conventions."""
    qa, qb = quat_xyz(a), quat_xyz(b)
    qac = qa * torch.tensor([1.0, -1.0, -1.0, -1.0], dtype=qa.dtype, device=qa.device)
    qr = quat_mul(qac, qb)
    return 2.0 * torch.atan2(torch.linalg.vector_norm(qr[..., 1:], dim=-1),
                             qr[..., 0].abs().clamp_min(torch.finfo(qr.dtype).tiny))


def torch_force_to_euler(acc: torch.Tensor, adapter_yaw: torch.Tensor,
                         output_yaw: torch.Tensor) -> torch.Tensor:
    z = acc[..., 2] + 9.8
    a = torch.cos(adapter_yaw) * acc[..., 0] + torch.sin(adapter_yaw) * acc[..., 1]
    b = torch.sin(adapter_yaw) * acc[..., 0] - torch.cos(adapter_yaw) * acc[..., 1]
    roll = torch.atan2(b, torch.hypot(z, a))
    pitch = torch.atan2(a, z)
    tilt = torch.hypot(roll, pitch)
    scale = torch.minimum(torch.ones_like(tilt), (math.pi / 6) / tilt.clamp_min(1e-12))
    return torch.stack((roll * scale, pitch * scale, output_yaw), dim=-1)


class ExactCommandFilter(Function):
    """Exact 1-ms semi-implicit filter, NumPy forward and manually reversed adjoint."""

    @staticmethod
    def forward(ctx, target: torch.Tensor, initial_euler: torch.Tensor,
                initial_rate: torch.Tensor, wn: torch.Tensor,
                damping: torch.Tensor, limit: torch.Tensor) -> torch.Tensor:
        target_np = target.detach().to(device="cpu", dtype=torch.float64).numpy()
        euler = initial_euler.detach().to(device="cpu", dtype=torch.float64).numpy().copy()
        rate = initial_rate.detach().to(device="cpu", dtype=torch.float64).numpy().copy()
        wn_np = wn.detach().to(device="cpu", dtype=torch.float64).numpy()
        damping_np = damping.detach().to(device="cpu", dtype=torch.float64).numpy()
        limit_np = limit.detach().to(device="cpu", dtype=torch.float64).numpy()
        batch, n, _ = target_np.shape
        out = np.empty_like(target_np)
        active = np.empty_like(target_np, dtype=bool)
        # Save the recurrent states needed by the O(T) reverse pass, not an autograd graph per tick.
        rate_before = np.empty_like(target_np)
        for i in range(n):
            out[:, i] = euler
            rate_before[:, i] = rate
            err = np.arctan2(np.sin(target_np[:, i] - euler), np.cos(target_np[:, i] - euler))
            req = wn_np * wn_np * err - 2.0 * damping_np * wn_np * rate
            # Match torch.clamp's derivative convention: pass gradients at exact bounds.
            active[:, i] = np.abs(req) <= limit_np
            applied = np.clip(req, -limit_np, limit_np)
            rate = rate + DT_S * applied
            euler = np.arctan2(np.sin(euler + DT_S * rate), np.cos(euler + DT_S * rate))
        ctx.rate_before = rate_before
        ctx.active = active
        ctx.wn = wn_np
        ctx.damping = damping_np
        ctx.target_device = target.device
        ctx.target_dtype = target.dtype
        return torch.as_tensor(out, device=target.device, dtype=target.dtype)

    @staticmethod
    def backward(ctx, grad_out: torch.Tensor):
        grad_y = grad_out.detach().to(device="cpu", dtype=torch.float64).numpy()
        active = ctx.active
        wn, damping = ctx.wn, ctx.damping
        batch, n, _ = grad_y.shape
        grad_target = np.zeros_like(grad_y)
        adj_e = np.zeros((batch, 3), dtype=np.float64)
        adj_r = np.zeros((batch, 3), dtype=np.float64)
        for i in range(n - 1, -1, -1):
            # e_next=e+dt*r_next, r_next=r+dt*clip(wn^2*(target-e)-2*zeta*wn*r)
            adj_r_total = adj_r + DT_S * adj_e
            adj_req = DT_S * adj_r_total * active[:, i]
            grad_target[:, i] = wn * wn * adj_req
            e_now = grad_y[:, i] + adj_e - wn * wn * adj_req
            r_now = adj_r_total - 2.0 * damping * wn * adj_req
            adj_e, adj_r = e_now, r_now
        grad_target_t = torch.as_tensor(grad_target, device=ctx.target_device, dtype=ctx.target_dtype)
        return grad_target_t, None, None, None, None, None


class ResidualGRU(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.gru = nn.GRU(input_size=14, hidden_size=32, num_layers=1, batch_first=True)
        self.head = nn.Linear(32, 3)
        nn.init.zeros_(self.head.weight)
        nn.init.zeros_(self.head.bias)

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        h, _ = self.gru(x)  # one independent batch item per scene; hidden is reset at each scene start
        raw = self.head(h)
        return raw, raw.clamp(-DELTA_LIMIT, DELTA_LIMIT)


def torch_replay_filter(target: torch.Tensor, initial_euler: torch.Tensor,
                        initial_rate: torch.Tensor, wn: torch.Tensor,
                        damping: torch.Tensor, limit: torch.Tensor) -> torch.Tensor:
    euler, rate = initial_euler, initial_rate
    out = []
    for i in range(target.shape[1]):
        out.append(euler)
        err = torch.atan2(torch.sin(target[:, i] - euler), torch.cos(target[:, i] - euler))
        req = wn * wn * err - 2.0 * damping * wn * rate
        acc = torch.clamp(req, min=-limit, max=limit)
        rate = rate + DT_S * acc
        euler = torch.atan2(torch.sin(euler + DT_S * rate), torch.cos(euler + DT_S * rate))
    return torch.stack(out, dim=1)


def filter_adjoint_check() -> dict:
    torch.manual_seed(SEED)
    dtype = torch.float64
    cases = {}
    for name, length, amplitude, limits, boundary in (
        ("unsaturated", 240, 0.025, FILTER_LIMIT, False),
        ("saturated", 240, 0.025, np.array([0.02, 0.015, 0.01]), False),
        ("exact_limit_boundary", 8, 0.05, np.array([0.05, 0.05, 0.05]), True),
    ):
        if boundary:
            target0 = torch.full((1, length, 3), amplitude, dtype=dtype)
            initial = torch.zeros((1, 3), dtype=dtype)
            initial_rate = torch.zeros((1, 3), dtype=dtype)
            wn = torch.ones(3, dtype=dtype)
            damping = torch.ones(3, dtype=dtype)
        else:
            target0 = amplitude * torch.randn(2, length, 3, dtype=dtype)
            initial = 0.01 * torch.randn(2, 3, dtype=dtype)
            initial_rate = 0.03 * torch.randn(2, 3, dtype=dtype)
            wn = torch.tensor(FILTER_WN, dtype=dtype)
            damping = torch.tensor(FILTER_DAMPING, dtype=dtype)
        target_a = target0.clone().requires_grad_(True)
        target_b = target0.clone().requires_grad_(True)
        limit = torch.tensor(limits, dtype=dtype)
        custom_out = ExactCommandFilter.apply(target_a, initial, initial_rate, wn, damping, limit)
        ref_out = torch_replay_filter(target_b, initial, initial_rate, wn, damping, limit)
        if boundary:
            # Weight only post-update outputs; the first pre-update output must be input-independent.
            weights = torch.arange(length, dtype=dtype).reshape(1, length, 1).expand_as(custom_out)
            custom_loss = (custom_out * weights).sum()
            ref_loss = (ref_out * weights).sum()
        else:
            task = 0.02 * torch.randn(*custom_out.shape, dtype=dtype)
            custom_loss = so3_angle_torch(task, custom_out).square().mean()
            ref_loss = so3_angle_torch(task, ref_out).square().mean()
        grad_a = torch.autograd.grad(custom_loss, target_a)[0]
        grad_b = torch.autograd.grad(ref_loss, target_b)[0]
        cases[name] = {
            "steps": length,
            "max_output_abs_rad": float((custom_out - ref_out).abs().max()),
            "loss_abs": float((custom_loss - ref_loss).abs()),
            "max_input_gradient_abs": float((grad_a - grad_b).abs().max()),
            "custom_gradient_norm": float(torch.linalg.vector_norm(grad_a)),
            "passed": bool(torch.allclose(custom_out, ref_out, atol=1e-13, rtol=0) and
                            torch.allclose(grad_a, grad_b, atol=1e-11, rtol=1e-9)),
        }
        if not cases[name]["passed"]:
            raise RuntimeError(f"Exact filter adjoint {name} check failed: {cases[name]}")

    # Check 100-Hz action hold indexing and gradients through the 1-ms filter.
    base = torch.zeros((1, 10, 3), dtype=dtype)
    event_a = torch.tensor([[[0.35, -0.1, 0.0], [0.0, 0.0, 0.0],
                             [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]]], dtype=dtype, requires_grad=True)
    event_b = event_a.detach().clone().requires_grad_(True)
    applied_a = build_applied_1ms(base, event_a)
    applied_b = build_applied_1ms(base, event_b)
    nominal = torch.zeros_like(applied_a)
    nominal[..., 0] = 0.2
    nominal[..., 1] = -0.1
    yaw = torch.zeros(applied_a.shape[:2], dtype=dtype)
    target_a = torch_force_to_euler(nominal - applied_a, yaw, yaw)
    target_b = torch_force_to_euler(nominal - applied_b, yaw, yaw)
    wn, damping, limit = (torch.tensor(v, dtype=dtype) for v in (FILTER_WN, FILTER_DAMPING, FILTER_LIMIT))
    initial = torch.zeros((1, 3), dtype=dtype)
    rate = torch.zeros_like(initial)
    out_a = ExactCommandFilter.apply(target_a, initial, rate, wn, damping, limit)
    out_b = torch_replay_filter(target_b, initial, rate, wn, damping, limit)
    weights = torch.linspace(0.1, 1.0, out_a.numel(), dtype=dtype).reshape_as(out_a)
    loss_a, loss_b = (out_a * weights).sum(), (out_b * weights).sum()
    grad_a, grad_b = (torch.autograd.grad(loss_a, event_a, retain_graph=True)[0],
                      torch.autograd.grad(loss_b, event_b, retain_graph=True)[0])
    hold_ok = (torch.equal(applied_a[:, :10], base) and
               all(torch.equal(applied_a[:, 10 + 10 * i:20 + 10 * i],
                               event_a[:, i:i + 1].expand(-1, 10, -1)) for i in range(4)))
    grad_pre = torch.autograd.grad(out_a[:, 10].sum(), event_a, retain_graph=True)[0]
    grad_post = torch.autograd.grad(out_a[:, 11].sum(), event_a, retain_graph=True)[0]
    preupdate_ok = bool(torch.count_nonzero(grad_pre) == 0) and bool(torch.count_nonzero(grad_post) > 0)
    cases["event_zoh_and_preupdate"] = {
        "transition_count": int(applied_a.shape[1]), "event_count": 4,
        "first_event_transition_index": 10, "action_hold_10ms_exact": bool(hold_ok),
        "event0_has_no_effect_on_preupdate_output_at_transition_10": bool(torch.count_nonzero(grad_pre) == 0),
        "event0_affects_output_by_transition_11": bool(torch.count_nonzero(grad_post) > 0),
        "max_output_abs_rad": float((out_a - out_b).abs().max()),
        "max_event_action_gradient_abs": float((grad_a - grad_b).abs().max()),
        "passed": bool(hold_ok and preupdate_ok and
                        torch.allclose(out_a, out_b, atol=1e-13, rtol=0) and
                        torch.allclose(grad_a, grad_b, atol=1e-11, rtol=1e-9)),
    }
    if not all(x["passed"] for x in cases.values()):
        raise RuntimeError(f"Exact filter/ZOH adjoint checks failed: {cases}")
    return {"cases": cases, "passed": True,
            "saturation_derivative_convention": "matches torch.clamp: derivative 1 exactly at the limit, 0 outside"}


def build_applied_1ms(base_first_10: torch.Tensor, event_action: torch.Tensor) -> torch.Tensor:
    return torch.cat((base_first_10, event_action.repeat_interleave(10, dim=1)), dim=1)


def make_candidate_task_loss(event_action: torch.Tensor, nominal: torch.Tensor,
                             base_first_10: torch.Tensor, state_yaw: torch.Tensor,
                             reference_yaw: torch.Tensor, initial_euler: torch.Tensor,
                             task_target: torch.Tensor, device: torch.device) -> torch.Tensor:
    applied = build_applied_1ms(base_first_10, event_action)
    commanded_acc = nominal - applied
    target_euler = torch_force_to_euler(commanded_acc, state_yaw, reference_yaw)
    wn = torch.tensor(FILTER_WN, dtype=target_euler.dtype, device=device)
    damping = torch.tensor(FILTER_DAMPING, dtype=target_euler.dtype, device=device)
    limit = torch.tensor(FILTER_LIMIT, dtype=target_euler.dtype, device=device)
    initial_rate = torch.zeros_like(initial_euler)
    filtered = ExactCommandFilter.apply(target_euler, initial_euler, initial_rate, wn, damping, limit)
    return so3_angle_torch(task_target, filtered).square().mean()


def action_metrics(indices: list[int], ids: list[str], ready: np.ndarray,
                   target: np.ndarray, base: np.ndarray, candidate: np.ndarray) -> dict:
    per = {}
    for i in indices:
        m = ready[i]
        e0, e1 = base[i, m] - target[i, m], candidate[i, m] - target[i, m]
        per[ids[i]] = {"baseline_rmse_mps2": float(np.sqrt(np.mean(e0.astype(np.float64) ** 2))),
                       "candidate_rmse_mps2": float(np.sqrt(np.mean(e1.astype(np.float64) ** 2))),
                       "baseline_axis_rmse_mps2": np.sqrt(np.mean(e0.astype(np.float64) ** 2, axis=0)).tolist(),
                       "candidate_axis_rmse_mps2": np.sqrt(np.mean(e1.astype(np.float64) ** 2, axis=0)).tolist()}
    return {
        "scene_count": len(indices),
        "pooled_baseline_rmse_mps2": float(np.sqrt(np.mean((np.concatenate([base[i, ready[i]] for i in indices]) -
                                                                         np.concatenate([target[i, ready[i]] for i in indices])) ** 2))),
        "pooled_candidate_rmse_mps2": float(np.sqrt(np.mean((np.concatenate([candidate[i, ready[i]] for i in indices]) -
                                                                           np.concatenate([target[i, ready[i]] for i in indices])) ** 2))),
        "scene_macro_baseline_rmse_mps2": float(np.mean([x["baseline_rmse_mps2"] for x in per.values()])),
        "scene_macro_candidate_rmse_mps2": float(np.mean([x["candidate_rmse_mps2"] for x in per.values()])),
        "candidate_wins_ties_losses_vs_baseline": [
            int(sum(v["candidate_rmse_mps2"] < v["baseline_rmse_mps2"] - 1e-12 for v in per.values())),
            int(sum(abs(v["candidate_rmse_mps2"] - v["baseline_rmse_mps2"]) <= 1e-12 for v in per.values())),
            int(sum(v["candidate_rmse_mps2"] > v["baseline_rmse_mps2"] + 1e-12 for v in per.values()))],
        "per_scene": per,
    }


def evaluate_task_action(scene_index: int, event_action: np.ndarray,
                         trajectory: dict) -> float:
    applied = np.concatenate((trajectory["applied_acc_1ms"][:10],
                              np.repeat(event_action, 10, axis=0)), axis=0).astype(np.float64)
    cmd = trajectory["nominal_acc_1ms"].astype(np.float64) - applied
    target_euler = force_to_euler(cmd, trajectory["state_yaw_1ms"],
                                  trajectory["reference_yaw_1ms"])
    filtered, _, _ = replay_filter(target_euler, trajectory["initial_euler"].astype(np.float64))
    task_target = trajectory["task_target_euler"].astype(np.float64)
    theta = (Rotation.from_euler("xyz", task_target).inv() *
             Rotation.from_euler("xyz", filtered)).magnitude()
    return float(np.sqrt(np.mean(theta * theta)))


def main() -> None:
    for p in (OOF_OUT, RESULTS_OUT, LOCK_OUT):
        if p.exists():
            raise RuntimeError(f"Refusing to overwrite {p}")
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    if any(CHECKPOINT_DIR.iterdir()):
        raise RuntimeError("Refusing to overwrite existing task-aware checkpoints")
    if not AUDIT_PATH.is_file():
        raise RuntimeError("Run parent target/filter audit first")
    preflight = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
    bundle = load_locked_inputs()
    audit = bundle["audit"]
    if preflight.get("dataset_sha256") != audit["dataset_sha256"] or \
            preflight.get("source_lock_sha256") != audit["source_lock_sha256"] or \
            max(audit["maximum_replay_errors"].values()) > 2e-10:
        raise RuntimeError("Parent raw replay audit is stale or exceeds parity tolerance")

    data = bundle["arrays"]
    manifest = bundle["manifest"]
    ids = data["scene_ids"].astype(str).tolist()
    x = data["x14_model_input"].astype(np.float32)
    ready = data["ready_mask"].astype(bool)
    event_t = data["event_time_s"].astype(np.float64)
    event_idx = data["event_index_zero_based"].astype(np.int64)
    base_event = data["applied_acceleration_event_mps2"].astype(np.float32)
    target = data["target_interval_clip_mps2"].astype(np.float32)
    if not np.allclose(np.diff(event_t, axis=1), EVENT_DT_S, atol=TIME_TOL_S, rtol=0):
        raise RuntimeError("Causal event interval differs from 10 ms")
    if not np.allclose(data["interval_end_time_s"] - event_t, EVENT_DT_S, atol=TIME_TOL_S, rtol=0):
        raise RuntimeError("Position label does not end 10 ms after its feature event")
    if not np.array_equal(event_idx, np.broadcast_to(np.arange(10, 20000, 10), (24, 1999))):
        raise RuntimeError("Unexpected raw event index mapping")

    # Verify and load the already-completed matched no-task arm; do not retrain it.
    no_task_lock = json.loads(NO_TASK_LOCK_PATH.read_text(encoding="utf-8"))
    no_task_result = json.loads(NO_TASK_RESULTS_PATH.read_text(encoding="utf-8"))
    no_task_sha = sha256(NO_TASK_OOF_PATH)
    expected_no_task_sha = no_task_result.get("oof_prediction_sha256")
    if (no_task_lock.get("npz_sha256", "").lower() != audit["dataset_sha256"].lower() or
            no_task_lock.get("lambda_values") != [0.01] or
            (expected_no_task_sha and expected_no_task_sha.lower() != no_task_sha.lower())):
        raise RuntimeError("Existing λ=.01 control arm does not bind the same dataset/protocol")
    with np.load(NO_TASK_OOF_PATH, allow_pickle=False) as z:
        no_task_ids = z["scene_ids"].astype(str).tolist()
        no_task_fold = z["fold_id"].astype(str)
        no_task_ready = z["ready_mask"].astype(bool)
        no_task_target = z["target_clip_mps2"].astype(np.float32)
        no_task_action = z["prediction_lambda_0_01"].astype(np.float32)
    if (no_task_ids != ids or not np.array_equal(no_task_ready, ready) or
            not np.array_equal(no_task_target, target) or not np.isfinite(no_task_action).all()):
        raise RuntimeError("Existing no-task OOF predictions do not align with this dataset")

    # Scene batch items carry separate hidden states. All per-scene 1-ms command data is frozen.
    trj = bundle["trajectories"]
    nominal = torch.as_tensor(np.stack([s["nominal_acc_1ms"] for s in trj]), dtype=torch.float32)
    applied1 = torch.as_tensor(np.stack([s["applied_acc_1ms"] for s in trj]), dtype=torch.float32)
    state_yaw = torch.as_tensor(np.stack([s["state_yaw_1ms"] for s in trj]), dtype=torch.float32)
    ref_yaw = torch.as_tensor(np.stack([s["reference_yaw_1ms"] for s in trj]), dtype=torch.float32)
    task_target = torch.as_tensor(np.stack([s["task_target_euler"] for s in trj]), dtype=torch.float32)
    init_euler = torch.as_tensor(np.stack([s["initial_euler"] for s in trj]), dtype=torch.float32)
    tx_base = torch.as_tensor(x)
    tb = torch.as_tensor(np.clip(event_t / BETA_RISE_S, 0.0, 1.0)[..., None], dtype=torch.float32)
    tm = torch.as_tensor(ready)
    ta = torch.as_tensor(base_event)
    ty = torch.as_tensor(target)
    adjoint_check = filter_adjoint_check()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    torch.set_num_threads(1)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    torch.use_deterministic_algorithms(True)
    tx_base, tb, tm, ta, ty = (v.to(device) for v in (tx_base, tb, tm, ta, ty))
    nominal, applied1, state_yaw, ref_yaw, task_target, init_euler = (
        v.to(device) for v in (nominal, applied1, state_yaw, ref_yaw, task_target, init_euler))

    task_action = np.full_like(base_event, np.nan, dtype=np.float32)
    raw_oof = np.full_like(base_event, np.nan, dtype=np.float32)
    delta_oof = np.full_like(base_event, np.nan, dtype=np.float32)
    fold_results = {}
    fold_specs = manifest["scene_folds"]
    if [f["holdout_scene_count"] for f in fold_specs] != [6, 8, 4, 6]:
        raise RuntimeError("Fold sizes differ from the fixed 6/8/4/6 protocol")
    t0 = time.time()

    for fold_i, spec in enumerate(fold_specs):
        fold_id = spec["fold_id"]
        tr = [ids.index(s) for s in spec["train_scene_ids"]]
        ho = [ids.index(s) for s in spec["holdout_scene_ids"]]
        if len(tr) != spec["train_scene_count"] or len(ho) != spec["holdout_scene_count"] or set(tr) & set(ho):
            raise RuntimeError(f"Scene fold membership invalid: {fold_id}")

        # Fold-only X14 normalizer: held-out scenes never contribute statistics.
        mu = x[tr].reshape(-1, 14).mean(axis=0)
        sd = x[tr].reshape(-1, 14).std(axis=0)
        sd[sd < 1e-6] = 1.0
        xn = ((x - mu[None, None, :]) / sd[None, None, :]).astype(np.float32)
        tx = torch.as_tensor(xn, device=device)
        tri = torch.as_tensor(tr, dtype=torch.long, device=device)
        beta_tr = tb[tri]
        loss_log = []

        seed = SEED + fold_i
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
        model = ResidualGRU().to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=LR)

        for step in range(STEPS):
            model.train()
            optimizer.zero_grad(set_to_none=True)
            raw, delta = model(tx[tri])
            d = torch.where(tm[tri, :, None], delta, torch.zeros_like(delta))
            pred_event = torch.clamp(ta[tri] + beta_tr * d, -ACTION_LIMIT, ACTION_LIMIT)
            position_loss = F.smooth_l1_loss(pred_event[tm[tri]], ty[tri][tm[tri]], reduction="mean")
            d2 = d[:, 2:] - 2.0 * d[:, 1:-1] + d[:, :-2]
            adjacent = tm[tri, 2:] & tm[tri, 1:-1] & tm[tri, :-2]
            smooth_loss = d2[adjacent].square().mean()
            task_loss = make_candidate_task_loss(
                pred_event, nominal[tri, :, :], applied1[tri, :10, :], state_yaw[tri],
                ref_yaw[tri], init_euler[tri], task_target[tri], device)
            loss = position_loss + LAMBDA_SMOOTH * smooth_loss + LAMBDA_TASK * task_loss
            if not torch.isfinite(loss):
                raise RuntimeError(f"Non-finite objective at {fold_id} step {step + 1}")
            loss.backward()
            optimizer.step()
            if (step + 1) % 50 == 0 or step == 0:
                loss_log.append({"step": step + 1,
                                 "position_smooth_l1": float(position_loss.detach().cpu()),
                                 "smoothness_mean_d2_sq": float(smooth_loss.detach().cpu()),
                                 "task_mean_so3_sq_rad2": float(task_loss.detach().cpu()),
                                 "total_objective": float(loss.detach().cpu())})
            if (step + 1) % 50 == 0:
                print(f"{fold_id}: step {step+1}/{STEPS}, pos={position_loss.item():.6g}, "
                      f"task={task_loss.item():.6g} rad^2, total={loss.item():.6g}", flush=True)

        model.eval()
        with torch.no_grad():
            raw_all, d_all = model(torch.as_tensor(xn, device=device))
            d_all = torch.where(tm[:, :, None], d_all, torch.zeros_like(d_all))
            p_all = torch.clamp(ta + tb * d_all, -ACTION_LIMIT, ACTION_LIMIT)
        raw_np = raw_all.cpu().numpy()
        d_np = d_all.cpu().numpy()
        p_np = p_all.cpu().numpy()
        raw_oof[ho] = raw_np[ho]
        delta_oof[ho] = d_np[ho]
        task_action[ho] = p_np[ho]

        ckpt_path = CHECKPOINT_DIR / f"{fold_id}_task_aware.pt"
        torch.save({"state_dict": model.cpu().state_dict(), "normalizer_mean": mu,
                    "normalizer_std": sd, "fold_id": fold_id,
                    "train_scene_ids": spec["train_scene_ids"],
                    "holdout_scene_ids": spec["holdout_scene_ids"],
                    "seed": seed, "optimizer_steps": STEPS, "learning_rate": LR,
                    "lambda_smooth": LAMBDA_SMOOTH, "lambda_task": LAMBDA_TASK,
                    "task_loss_definition": TASK_WEIGHT_DEFINITION,
                    "dataset_sha256": audit["dataset_sha256"]}, ckpt_path)

        def position_fold(indices: list[int], pred_action: np.ndarray) -> dict:
            vals = []
            for i in indices:
                m = ready[i]
                vals.append(float(np.sqrt(np.mean((pred_action[i, m].astype(np.float64) - target[i, m]) ** 2))))
            y = np.concatenate([target[i, ready[i]] for i in indices], axis=0)
            base = np.concatenate([np.clip(base_event[i, ready[i]], -ACTION_LIMIT, ACTION_LIMIT) for i in indices], axis=0)
            pred = np.concatenate([pred_action[i, ready[i]] for i in indices], axis=0)
            return {"scene_count": len(indices),
                    "pooled_rmse_mps2": float(np.sqrt(np.mean((pred.astype(np.float64) - y) ** 2))),
                    "scene_macro_rmse_mps2": float(np.mean(vals))}

        delta_ready = d_np[ho][ready[ho]]
        raw_ready = raw_np[ho][ready[ho]]
        action_preclip = base_event[ho] + tb.detach().cpu().numpy()[ho] * d_np[ho]
        fold_results[fold_id] = {
            "train_scene_count": len(tr), "holdout_scene_count": len(ho),
            "train_scene_ids": spec["train_scene_ids"], "holdout_scene_ids": spec["holdout_scene_ids"],
            "seed": seed, "normalizer_fit_scope": "train scenes only, all 1999 causal X14 rows",
            "normalizer_mean": mu.tolist(), "normalizer_std": sd.tolist(),
            "loss_log": loss_log,
            "position": {"train": position_fold(tr, p_np), "holdout": position_fold(ho, p_np)},
            "holdout_head_abs_ge_0_5_fraction": float(np.mean(np.abs(raw_ready) >= DELTA_LIMIT)),
            "holdout_clipped_delta_abs_ge_0_5_fraction": float(np.mean(np.abs(delta_ready) >= DELTA_LIMIT)),
            "holdout_preclip_total_action_abs_ge_3_fraction": float(np.mean(np.abs(action_preclip[ready[ho]]) >= ACTION_LIMIT)),
            "holdout_final_action_at_limit_fraction": float(np.mean(np.isclose(np.abs(p_np[ho][ready[ho]]), ACTION_LIMIT, atol=1e-7))),
            "checkpoint_path": str(ckpt_path.relative_to(ROOT)).replace("\\", "/"),
            "checkpoint_sha256": sha256(ckpt_path),
        }
        print(f"{fold_id}: finished. holdout position macro RMSE="
              f"{fold_results[fold_id]['position']['holdout']['scene_macro_rmse_mps2']:.6g}", flush=True)

    if not np.isfinite(task_action).all() or not np.isfinite(raw_oof).all() or not np.isfinite(delta_oof).all():
        raise RuntimeError("Missing task-aware OOF predictions")

    baseline_action = np.clip(base_event, -ACTION_LIMIT, ACTION_LIMIT)
    position = {
        "baseline_c5": action_metrics(list(range(24)), ids, ready, target, baseline_action, baseline_action),
        "no_task_lambda_0_01": action_metrics(list(range(24)), ids, ready, target, baseline_action, no_task_action),
        "task_aware_lambda_task_0_1": action_metrics(list(range(24)), ids, ready, target, baseline_action, task_action),
    }
    task_so3 = {"c5_baseline": [], "no_task_lambda_0_01": [], "task_aware_lambda_task_0_1": []}
    for i in range(24):
        task_so3["c5_baseline"].append(evaluate_task_action(i, baseline_action[i], trj[i]))
        task_so3["no_task_lambda_0_01"].append(evaluate_task_action(i, no_task_action[i], trj[i]))
        task_so3["task_aware_lambda_task_0_1"].append(evaluate_task_action(i, task_action[i], trj[i]))
    task_metrics = {
        method: {"scene_count": 24,
                 "pooled_SO3_RMSE_rad": float(np.sqrt(np.mean(np.square(values)))),
                 "scene_macro_SO3_RMSE_rad": float(np.mean(values)),
                 "per_scene_SO3_RMSE_rad": dict(zip(ids, values))}
        for method, values in task_so3.items()
    }
    position_delta_vs_no_task = np.array([
        action_metrics([i], ids, ready, target, baseline_action, task_action)["scene_macro_candidate_rmse_mps2"] -
        action_metrics([i], ids, ready, target, baseline_action, no_task_action)["scene_macro_candidate_rmse_mps2"]
        for i in range(24)])
    task_delta_vs_no_task = np.asarray(task_so3["task_aware_lambda_task_0_1"]) - np.asarray(task_so3["no_task_lambda_0_01"])

    oof_data_path = OOF_OUT
    np.savez_compressed(oof_data_path, scene_ids=np.asarray(ids),
                        fold_id=data["fold_id"].astype(str), event_time_s=event_t.astype(np.float32),
                        ready_mask=ready, target_clip_mps2=target, baseline_action_mps2=baseline_action,
                        no_task_action_lambda_0_01=no_task_action, task_action_lambda_task_0_1=task_action,
                        task_raw_delta_mps2=raw_oof, task_clipped_delta_mps2=delta_oof)
    no_task_fold_summaries = no_task_result.get("folds", {})
    results = {
        "schema": "COSINE_GRU_C5_POSITION_RESIDUAL_GRU_TASK_AWARE_CV_RESULTS_V1",
        "scope": "Locked TRAIN_C5_24 development cohort only; no VAL/TEST raw, no new Plant, no real-wind fields, no inertia reconstruction/use.",
        "dataset_sha256": audit["dataset_sha256"],
        "parent_replay_audit_sha256": sha256(AUDIT_PATH),
        "no_task_control": {"source_lock_sha256": sha256(NO_TASK_LOCK_PATH),
                             "results_sha256": sha256(NO_TASK_RESULTS_PATH),
                             "oof_sha256": no_task_sha,
                             "lambda_smooth": 0.01,
                             "training_repeated": False,
                             "source_fold_ids": list(no_task_fold_summaries.keys())},
        "model": "GRU(14,32) -> Linear(32,3), zero-initialized output; per-scene hidden reset",
        "training": {"seed_base": SEED, "steps_per_fold": STEPS, "optimizer": "Adam", "learning_rate": LR,
                     "normalizer": "per-fold mean/std computed from training scenes only across 1999 causal X14 rows",
                     "position_loss": "SmoothL1(clamp(a_C5 + beta*clip(delta,-0.5,0.5),-3,3), y_10ms_clipped) on ready events",
                     "smoothness_loss": "0.01 * mean(second_difference(clipped_delta)^2) on contiguous ready triples",
                     "task_loss": "0.1 * mean(SO3 geodesic angle in radians squared) over the exact 1-ms filtered command trajectory on frozen parent-C5 states; no normalization, threshold, or adaptive gate",
                     "task_weight": LAMBDA_TASK,
                     "gradient_adjoint_check": adjoint_check,
                     "filter": {"dt_s": DT_S, "wn_rad_s": FILTER_WN.tolist(), "damping": FILTER_DAMPING.tolist(),
                                "acceleration_limit_rad_s2": ["Inf", "Inf", 6],
                                "initial_state": "parent raw initial Euler and zero Euler-rate",
                                "filter_reference_timing": "pre-update; roll/pitch from current yaw, target yaw from reference"},
                     "state_frozen_limit": "The loss measures command/target consistency on fixed C5 state, yaw, and reference trajectories. It does not propagate residual-induced state changes or establish closed-loop performance."},
        "folds": fold_results,
        "position_oof": position,
        "task_so3_oof": task_metrics,
        "task_minus_no_task_per_scene_position_rmse_mps2": dict(zip(ids, position_delta_vs_no_task.tolist())),
        "task_minus_no_task_per_scene_SO3_rmse_rad": dict(zip(ids, task_delta_vs_no_task.tolist())),
        "paired_scene_wins_task_vs_no_task": {
            "position": [int(sum(position_delta_vs_no_task < -1e-12)),
                         int(sum(abs(position_delta_vs_no_task) <= 1e-12)),
                         int(sum(position_delta_vs_no_task > 1e-12))],
            "task_SO3": [int(sum(task_delta_vs_no_task < -1e-12)),
                         int(sum(abs(task_delta_vs_no_task) <= 1e-12)),
                         int(sum(task_delta_vs_no_task > 1e-12))]},
        "limits": ["Development OOF of residual head on parent-seen DEV24 trajectories; not independent full-system validation.",
                   "Task-aware objective is a frozen-state surrogate; changes to position/yaw states and their later task commands are not modeled."],
        "runtime_seconds": time.time() - t0,
        "oof_path": str(oof_data_path.relative_to(ROOT)).replace("\\", "/"),
        "oof_sha256": sha256(oof_data_path),
    }
    write_json(RESULTS_OUT, results)
    source_lock = {
        "schema": "COSINE_GRU_C5_POSITION_RESIDUAL_GRU_TASK_AWARE_SOURCE_LOCK_V1",
        "scope": results["scope"],
        "dataset_sha256": audit["dataset_sha256"],
        "dataset_manifest_sha256": sha256(DATA_DIR / "DATASET_MANIFEST_v1.json"),
        "dataset_source_lock_sha256": sha256(DATA_DIR / "SOURCE_LOCK_v1.json"),
        "parent_task_filter_replay_audit_sha256": sha256(AUDIT_PATH),
        "no_task_oof_sha256": no_task_sha,
        "no_task_source_lock_sha256": sha256(NO_TASK_LOCK_PATH),
        "script_sha256": sha256(Path(__file__)),
        "seed_base": SEED, "steps_per_fold": STEPS,
        "lambda_smooth": LAMBDA_SMOOTH, "lambda_task": LAMBDA_TASK,
        "fold_ids": [f["fold_id"] for f in fold_specs],
        "checkpoint_sha256_by_fold": {k: v["checkpoint_sha256"] for k, v in fold_results.items()},
        "oof_sha256": sha256(oof_data_path), "results_sha256": sha256(RESULTS_OUT),
    }
    write_json(LOCK_OUT, source_lock)
    print(json.dumps({"runtime_seconds": results["runtime_seconds"],
                      "position_macro": {k: v["scene_macro_candidate_rmse_mps2"]
                                         for k, v in position.items()},
                      "task_macro_mrad": {k: 1000 * v["scene_macro_SO3_RMSE_rad"]
                                          for k, v in task_metrics.items()},
                      "task_vs_no_task_wins": results["paired_scene_wins_task_vs_no_task"]}, indent=2), flush=True)


if __name__ == "__main__":
    main()
