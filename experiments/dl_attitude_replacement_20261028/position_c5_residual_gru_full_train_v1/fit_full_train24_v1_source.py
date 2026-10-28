#!/usr/bin/env python3
"""Fit the fixed lambda=.01 residual GRU on all 24 audited TRAIN scenes."""
from __future__ import annotations

import hashlib
import json
import os
import random
import shutil
import time
from pathlib import Path

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

import numpy as np
import torch
from scipy.io import savemat
from torch import nn
from torch.nn import functional as F


ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "reports/position_c5_train24_causal_dataset_v1"
NPZ = DATA_DIR / "dataset/C5_TRAIN24_POSITION_CAUSAL_PAIRS_v1.npz"
MANIFEST = DATA_DIR / "C5_TRAIN24_POSITION_CAUSAL_MANIFEST_v1.json"
ALIGNMENT = DATA_DIR / "POSITION_TRAIN24_LABEL_ALIGNMENT_v1.json"
SEED = 20261028
STEPS = 300
LR = 1e-3
LAMBDA = 0.01
DT = 0.01
TIME_TOL = 2e-6
BETA_RISE_S = 1.8
ACTION_LIMIT = 3.0
DELTA_LIMIT = 0.5


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def rmse(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.sqrt(np.mean((a.astype(np.float64) - b.astype(np.float64)) ** 2)))


class ResidualGRU(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.gru = nn.GRU(input_size=14, hidden_size=32, num_layers=1, batch_first=True)
        self.head = nn.Linear(32, 3)
        nn.init.zeros_(self.head.weight)
        nn.init.zeros_(self.head.bias)

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        h, _ = self.gru(x)
        raw = self.head(h)
        return raw, raw.clamp(-DELTA_LIMIT, DELTA_LIMIT)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    alignment = json.loads(ALIGNMENT.read_text(encoding="utf-8"))
    if sha256(NPZ).lower() != m["data_sha256"].lower():
        raise RuntimeError("TRAIN24 dataset SHA mismatch")
    if sha256(ALIGNMENT).lower() != m["teacher_label_alignment_sha256"].lower():
        raise RuntimeError("TRAIN24 label-alignment SHA mismatch")
    if sha256(DATA_DIR / "build_position_c5_train24_dataset_v1.py").lower() != m["builder_sha256"].lower():
        raise RuntimeError("Dataset builder SHA mismatch")
    if m["scope"].get("TEST_accessed") is not False or m["scope"].get("Plant_calls") != 0:
        raise RuntimeError("TRAIN24 manifest scope lock failed")
    if alignment.get("scope") != "TRAIN24 B/POS_OFF only; no TEST, Plant, training, or inertia reconstruction":
        raise RuntimeError("Alignment report scope lock failed")
    with np.load(NPZ, allow_pickle=False) as z:
        d = {k: z[k] for k in z.files}

    ids = d["scene_ids"].astype(str)
    winds = d["wind_cells"].astype(int)
    x_logged = d["x14_logged"].astype(np.float32)
    x = d["x14_model_input"].astype(np.float32)
    y = d["target_interval_clip_mps2"].astype(np.float32)
    a = d["applied_acceleration_event_mps2"].astype(np.float32)
    ready = d["ready_mask"].astype(bool)
    t = d["event_time_s"].astype(np.float64)
    t_end = d["interval_end_time_s"].astype(np.float64)
    if x.shape != (24, 1999, 14) or not np.array_equal(x, x_logged):
        raise RuntimeError("Expected 24 scenes of identical logged/model 14-feature inputs")
    if any("TRAIN" not in s for s in ids) or set(winds.tolist()) != {0, 9, 12, 15}:
        raise RuntimeError("Unexpected non-TRAIN or wind-group data")
    if not np.array_equal(ready, np.broadcast_to(np.arange(1999) >= 31, ready.shape)):
        raise RuntimeError("Readiness mask mismatch")
    if not np.allclose(np.diff(t, axis=1), DT, atol=TIME_TOL, rtol=0):
        raise RuntimeError("Event timestamps do not follow the 10ms event cadence")
    if not np.allclose(t_end - t, DT, atol=TIME_TOL, rtol=0):
        raise RuntimeError("Label interval does not end 10ms after its causal feature event")

    # This final fit intentionally uses all 24 TRAIN scenes; no VAL/TEST data is opened.
    mu = x.reshape(-1, 14).mean(axis=0)
    sd = x.reshape(-1, 14).std(axis=0)
    sd[sd < 1e-6] = 1.0
    xn = ((x - mu[None, None, :]) / sd[None, None, :]).astype(np.float32)
    beta = np.clip(t / BETA_RISE_S, 0.0, 1.0).astype(np.float32)

    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(SEED)
    torch.set_num_threads(1)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    torch.use_deterministic_algorithms(True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    tx = torch.as_tensor(xn, device=device)
    ta = torch.as_tensor(a, device=device)
    ty = torch.as_tensor(y, device=device)
    tb = torch.as_tensor(beta[..., None], device=device)
    tm = torch.as_tensor(ready, device=device)

    model = ResidualGRU().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=LR)
    loss_log = []
    t0 = time.time()
    for step in range(STEPS):
        optimizer.zero_grad(set_to_none=True)
        raw, delta = model(tx)
        delta = torch.where(tm[:, :, None], delta, torch.zeros_like(delta))
        action = torch.clamp(ta + tb * delta, -ACTION_LIMIT, ACTION_LIMIT)
        loss = F.smooth_l1_loss(action[tm], ty[tm], reduction="mean")
        d2 = delta[:, 2:] - 2.0 * delta[:, 1:-1] + delta[:, :-2]
        consecutive = tm[:, 2:] & tm[:, 1:-1] & tm[:, :-2]
        dt = torch.as_tensor(np.diff(t, axis=1)[:, 1:], device=device)
        consecutive &= torch.abs(dt - DT) < TIME_TOL
        loss = loss + LAMBDA * d2[consecutive].square().mean()
        loss.backward()
        optimizer.step()
        if (step + 1) % 50 == 0:
            loss_log.append({"step": step + 1, "objective": float(loss.detach().cpu())})

    model.eval()
    # CPU batch-sequence reference is the independent replay comparator.
    model = model.cpu()
    with torch.no_grad():
        raw_ref, delta_ref = model(torch.from_numpy(xn))
        delta_ref = torch.where(torch.from_numpy(ready)[:, :, None], delta_ref,
                                torch.zeros_like(delta_ref))
        action_ref = torch.clamp(torch.from_numpy(a) + torch.from_numpy(beta[..., None]) * delta_ref,
                                 -ACTION_LIMIT, ACTION_LIMIT)
    delta_np = delta_ref.numpy()
    action_np = action_ref.numpy()
    baseline = np.clip(a, -ACTION_LIMIT, ACTION_LIMIT)
    fit = {
        "training_only_in_sample": True,
        "ready_events": int(ready.sum()),
        "baseline_pooled_rmse_mps2": rmse(baseline[ready], y[ready]),
        "model_pooled_rmse_mps2": rmse(action_np[ready], y[ready]),
        "baseline_scene_macro_rmse_mps2": float(np.mean([rmse(baseline[i, ready[i]], y[i, ready[i]]) for i in range(24)])),
        "model_scene_macro_rmse_mps2": float(np.mean([rmse(action_np[i, ready[i]], y[i, ready[i]]) for i in range(24)])),
        "final_objective": loss_log[-1]["objective"],
        "final_action_clip_fraction": float(np.mean(np.isclose(np.abs(action_np[ready]), ACTION_LIMIT, atol=1e-7))),
        "head_delta_clip_fraction": float(np.mean(np.abs(raw_ref.numpy()[ready]) >= DELTA_LIMIT)),
    }

    ckpt_path = OUT / "position_residual_gru_full_train24.pt"
    payload = {
        "state_dict": model.state_dict(), "input_mean": mu.astype(np.float32),
        "input_std": sd.astype(np.float32), "input_size": 14, "hidden_size": 32,
        "output_size": 3, "seed": SEED, "optimizer_steps": STEPS, "learning_rate": LR,
        "smooth_lambda": LAMBDA, "beta_rise_time_s": BETA_RISE_S,
        "delta_limit_mps2": DELTA_LIMIT, "action_limit_mps2": ACTION_LIMIT,
        "data_sha256": sha256(NPZ), "train_scene_ids": ids.tolist(),
        "note": "TRAIN24 full fit for pilot preparation; not independent validation or closed-loop evidence",
    }
    torch.save(payload, ckpt_path)
    w = model.state_dict()
    savemat(OUT / "position_residual_gru_full_train24.mat", {
        "gru_weight_ih_l0": w["gru.weight_ih_l0"].numpy(),
        "gru_weight_hh_l0": w["gru.weight_hh_l0"].numpy(),
        "gru_bias_ih_l0": w["gru.bias_ih_l0"].numpy(),
        "gru_bias_hh_l0": w["gru.bias_hh_l0"].numpy(),
        "head_weight": w["head.weight"].numpy(), "head_bias": w["head.bias"].numpy(),
        "input_mean": mu.astype(np.float32), "input_std": sd.astype(np.float32),
        "input_size": np.int32(14), "hidden_size": np.int32(32), "output_size": np.int32(3),
        "seed": np.int64(SEED), "optimizer_steps": np.int32(STEPS),
        "smooth_lambda": np.float64(LAMBDA), "beta_rise_time_s": np.float64(BETA_RISE_S),
        "delta_limit_mps2": np.float64(DELTA_LIMIT), "action_limit_mps2": np.float64(ACTION_LIMIT),
        "pytorch_gru_gate_order": "reset,update,new",
    }, do_compression=True)
    ref_path = OUT / "BATCH_SEQUENCE_REFERENCE_v1.npz"
    np.savez_compressed(ref_path, scene_ids=ids, wind_cells=winds.astype(np.int16),
                        event_time_s=t.astype(np.float32), ready_mask=ready,
                        emitted_delta_mps2=delta_np, predicted_action_mps2=action_np)
    shutil.copy2(MANIFEST, OUT / MANIFEST.name)
    shutil.copy2(ALIGNMENT, OUT / ALIGNMENT.name)
    shutil.copy2(Path(__file__), OUT / "fit_full_train24_v1_source.py")
    write_json(OUT / "TRAIN_FIT_v1.json", {
        "scope": "TRAIN24 only; no TEST reads, Plant calls, or inertia reconstruction",
        "model": "GRU(14,32) -> zero-initialized Linear(32,3)",
        "training": {"seed": SEED, "steps": STEPS, "lr": LR, "lambda": LAMBDA,
                     "normalizer": "mean/std over all 24 TRAIN scenes and all causal event X14 rows",
                     "hidden_state": "independently reset per scene", "device": str(device),
                     "loss_log_every_50_steps": loss_log},
        "fit_metrics": fit,
        "runtime_seconds": time.time() - t0,
        "limit": "In-sample fit only. The frozen C5 backbone has seen more data; this package does not establish independent validation or closed-loop success.",
    })
    lock = {
        "schema": "POSITION_C5_RESIDUAL_GRU_FULL_TRAIN24_PACKAGE_V1",
        "source_data_path": str(NPZ.relative_to(ROOT)).replace("\\", "/"),
        "source_data_sha256": sha256(NPZ), "source_manifest_sha256": sha256(MANIFEST),
        "source_label_alignment_sha256": sha256(ALIGNMENT),
        "source_builder_sha256": sha256(DATA_DIR / "build_position_c5_train24_dataset_v1.py"),
        "fit_script_sha256": sha256(Path(__file__)),
        "checkpoint_sha256": sha256(ckpt_path),
        "mat_weights_sha256": sha256(OUT / "position_residual_gru_full_train24.mat"),
        "batch_reference_sha256": sha256(ref_path),
        "train_scenes": ids.tolist(), "scene_count": 24, "ready_events_per_scene": 1968,
        "seed": SEED, "steps": STEPS, "lambda": LAMBDA,
        "source_scope": "TRAIN24 only; no TEST, no Plant, no inertia reconstruction",
    }
    write_json(OUT / "MODEL_MANIFEST_v1.json", lock)
    print(json.dumps({"device": str(device), "runtime_seconds": time.time() - t0,
                      "fit_metrics": fit, "checkpoint_sha256": lock["checkpoint_sha256"]}, indent=2))


if __name__ == "__main__":
    main()
