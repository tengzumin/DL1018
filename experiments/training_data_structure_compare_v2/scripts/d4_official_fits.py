from __future__ import annotations

import csv
import hashlib
import json
import os
import random
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.nn import functional as F

torch.set_num_threads(1)
torch.set_num_interop_threads(1)

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "experiments/training_data_structure_compare_v2"
sys.path.insert(0, str(ROOT / "training"))
sys.path.insert(0, str(OUT / "scripts"))
from data_runtime import (MIXED_MASS, TEACHER_MASS, Episode, assign_weights,
                          endpoint_indices, load_episodes)
from models import PositionModel, cubic_bspline_basis

SEEDS = (2026101911, 2026101912)
FAMILIES = ("MIXED_KAN", "TEACHER_KAN", "DEEP_KAN", "HISTORY_KAN")
CHINESE = {
    "MIXED_KAN": "原结构混合数据续训",
    "TEACHER_KAN": "原结构教师数据续训",
    "DEEP_KAN": "加深KAN特征分支",
    "HISTORY_KAN": "短时序特征分支",
}
STEPS = 60_000
EVAL_EVERY = 3_000
CHECKPOINT_EVERY = 1_000
BATCH = 256
LR = 1e-3
WEIGHT_DECAY = 1e-5
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


class DeepResidualKAN(nn.Module):
    """Zero-initialized 32-to-32 cubic B-spline plus SiLU feature residual."""

    def __init__(self):
        super().__init__()
        self.spline_W = nn.Parameter(torch.zeros(32, 32, 8))
        self.linear_W = nn.Parameter(torch.zeros(32, 32))
        self.bias = nn.Parameter(torch.zeros(32))

    def forward(self, h0: torch.Tensor, knots: torch.Tensor) -> torch.Tensor:
        basis = cubic_bspline_basis(h0.clamp(-1.0, 1.0) * 4.0, knots)
        g = torch.einsum("nib,oib->no", basis, self.spline_W)
        g = g + F.linear(F.silu(h0), self.linear_W) + self.bias
        return torch.tanh(g)


class CausalHistoryBranch(nn.Module):
    """Four left-padded causal Conv1d blocks; only the current endpoint is read."""

    def __init__(self):
        super().__init__()
        self.dilations = (1, 2, 4, 8)
        self.convs = nn.ModuleList((nn.Conv1d(10, 16, 3, dilation=1),
                                    nn.Conv1d(16, 16, 3, dilation=2),
                                    nn.Conv1d(16, 16, 3, dilation=4),
                                    nn.Conv1d(16, 16, 3, dilation=8)))
        self.proj = nn.Linear(16, 32)
        nn.init.zeros_(self.proj.weight)
        nn.init.zeros_(self.proj.bias)

    def forward(self, x10_history: torch.Tensor) -> torch.Tensor:
        q = x10_history
        for conv, dilation in zip(self.convs, self.dilations):
            q = F.silu(conv(F.pad(q, (2 * dilation, 0))))
        return torch.tanh(self.proj(q[:, :, -1]))


class Candidate(nn.Module):
    def __init__(self, family: str, mu: np.ndarray, sigma: np.ndarray):
        super().__init__()
        self.family = family
        self.kan = PositionModel(mu, sigma)
        if family == "DEEP_KAN":
            self.deep = DeepResidualKAN()
        elif family == "HISTORY_KAN":
            self.history = CausalHistoryBranch()

    def _h0(self, x14: torch.Tensor) -> torch.Tensor:
        if x14.ndim == 3:
            if x14.shape[1] != 14 or x14.shape[2] != 32:
                raise ValueError(f"Expected [batch,14,32], got {tuple(x14.shape)}")
            current = ((x14 - self.kan.input_mu) / self.kan.input_sigma)[:, :, -1]
        elif x14.ndim == 2 and x14.shape[1] == 14:
            current = (x14 - self.kan.input_mu[:, :, 0]) / self.kan.input_sigma[:, :, 0]
        else:
            raise ValueError(f"Expected X14 row/window, got {tuple(x14.shape)}")
        clipped = current.clamp(-4.0, 4.0)
        basis = cubic_bspline_basis(clipped, self.kan.knots)
        h0 = torch.einsum("nib,oib->no", basis, self.kan.spline_W)
        h0 = h0 + F.linear(F.silu(current), self.kan.linear_W) + self.kan.feature_b
        return torch.tanh(h0)

    def features(self, x14: torch.Tensor, x10_history: torch.Tensor | None = None) -> torch.Tensor:
        if self.family in ("MIXED_KAN", "TEACHER_KAN"):
            return self.kan.encode(x14)
        h0 = self._h0(x14)
        if self.family == "DEEP_KAN":
            h = h0 + self.deep(h0, self.kan.knots)
        else:
            if x10_history is None or x10_history.shape[1:] != (10, 32):
                raise ValueError("HISTORY_KAN requires a real episode-local [batch,10,32] window")
            mu = self.kan.input_mu[:, :10, :]
            sigma = self.kan.input_sigma[:, :10, :]
            normalized = (x10_history - mu) / sigma
            h = h0 + self.history(normalized)
        phi = torch.cat((h, torch.ones_like(h[:, :1])), dim=1)
        return phi / torch.sqrt(1.0 + torch.sum(h * h, dim=1, keepdim=True))

    def forward(self, x14: torch.Tensor, x10_history: torch.Tensor | None = None) -> torch.Tensor:
        return self.kan.readout(self.features(x14, x10_history))


@dataclass
class EventTable:
    x: np.ndarray
    y: np.ndarray
    raw: np.ndarray
    weights: np.ndarray
    role: np.ndarray
    task: np.ndarray
    config: np.ndarray
    wind: np.ndarray
    scene: np.ndarray
    phase: np.ndarray
    time_s: np.ndarray
    run_id: np.ndarray
    end_index: np.ndarray
    history_index: np.ndarray

    def subset(self, keep: np.ndarray, weights: np.ndarray | None = None) -> "EventTable":
        return EventTable(**{
            name: (weights if name == "weights" and weights is not None else getattr(self, name)[keep])
            for name in self.__dataclass_fields__
        })


def offsets_for(episodes: list[Episode]) -> dict[str, int]:
    out, pos = {}, 0
    for ep in episodes:
        out[ep.run_id] = pos
        pos += len(endpoint_indices(ep))
    return out


def ensure_history_cache(split: str, episodes: list[Episode], offsets: dict[str, int]) -> tuple[Path, np.ndarray]:
    manifest = pd.read_csv(OUT / "manifests/REUSED_SEQUENCE_CACHE.csv", keep_default_na=False)
    sha_by_run = dict(zip(manifest.run_id.astype(str), manifest.sha256.astype(str)))
    identity = {"split": split, "window": 32, "features": "X14[0:10] raw cached values",
                "run_cache_sha256": {ep.run_id: sha_by_run[ep.run_id] for ep in episodes},
                "row_order": "manifest episode order; endpoint indices 31,36,...,1996"}
    total = sum(len(endpoint_indices(ep)) for ep in episodes)
    data_path = OUT / "derived" / f"{split.upper()}_X10_HISTORY_32.npy"
    meta_path = OUT / "derived" / f"{split.upper()}_X10_HISTORY_32.identity.json"
    if data_path.is_file() and meta_path.is_file():
        old = json.loads(meta_path.read_text(encoding="utf-8"))
        if old.get("identity") != identity or old.get("shape") != [total, 10, 32]:
            raise RuntimeError(f"History cache identity mismatch; preserving existing file: {data_path}")
        arr = np.load(data_path, mmap_mode="r", allow_pickle=False)
        if arr.shape != (total, 10, 32) or arr.dtype != np.float32:
            raise RuntimeError(f"Malformed history cache: {arr.shape}, {arr.dtype}")
        return data_path, arr
    arr = np.lib.format.open_memmap(data_path, mode="w+", dtype=np.float32, shape=(total, 10, 32))
    for n, ep in enumerate(episodes, start=1):
        ids = endpoint_indices(ep)
        windows = np.lib.stride_tricks.sliding_window_view(ep.x14[:, :10], window_shape=32, axis=0)
        row0 = offsets[ep.run_id]
        arr[row0:row0 + len(ids)] = windows[ids - 31]
        if n % 240 == 0 or n == len(episodes):
            print(f"HISTORY_CACHE {split} episodes={n}/{len(episodes)} rows={row0 + len(ids)}/{total}", flush=True)
    arr.flush()
    del arr
    identity_path = {"identity": identity, "shape": [total, 10, 32], "dtype": "float32",
                     "size_bytes": data_path.stat().st_size, "sha256": sha256(data_path)}
    write_json(meta_path, identity_path)
    return data_path, np.load(data_path, mmap_mode="r", allow_pickle=False)


def assemble(episodes: list[Episode], offsets: dict[str, int]) -> EventTable:
    chunks: dict[str, list[np.ndarray]] = {k: [] for k in
        ("x", "y", "raw", "weights", "role", "task", "config", "wind", "scene", "phase", "time_s", "run_id", "end_index", "history_index")}
    for ep in episodes:
        ids = endpoint_indices(ep)
        n = len(ids)
        chunks["x"].append(ep.x14[ids].astype(np.float32))
        chunks["y"].append(ep.y[ids].astype(np.float32))
        chunks["raw"].append(ep.raw[ids].astype(np.float32))
        chunks["weights"].append(ep.weights[ids].astype(np.float64))
        chunks["role"].append(np.full(n, ep.role, dtype=object))
        chunks["task"].append(np.full(n, ep.task, dtype=object))
        chunks["config"].append(np.full(n, ep.class_index, dtype=np.int16))
        chunks["wind"].append(np.full(n, ep.wind_cell, dtype=np.int16))
        chunks["scene"].append(np.full(n, ep.scene_id, dtype=object))
        chunks["phase"].append(ep.phase[ids].astype(np.int16))
        chunks["time_s"].append(ep.event_time_s[ids].astype(np.float32))
        chunks["run_id"].append(np.full(n, ep.run_id, dtype=object))
        chunks["end_index"].append(ids.astype(np.int16))
        chunks["history_index"].append(np.arange(offsets[ep.run_id], offsets[ep.run_id] + n, dtype=np.int64))
    return EventTable(**{k: np.concatenate(v) for k, v in chunks.items()})


def build_order(n: int, seed: int) -> np.ndarray:
    path = OUT / "derived" / f"BATCH_ORDER_N{n}_SEED{seed}.npy"
    if path.is_file():
        arr = np.load(path, mmap_mode="r", allow_pickle=False)
        if arr.shape != (STEPS * BATCH,) or arr.dtype != np.int32:
            raise RuntimeError(f"Saved order has wrong identity: {path}")
        return arr
    arr = np.lib.format.open_memmap(path, mode="w+", dtype=np.int32, shape=(STEPS * BATCH,))
    rng = np.random.default_rng(seed)
    pos = 0
    while pos < len(arr):
        perm = rng.permutation(n)
        take = min(n, len(arr) - pos)
        arr[pos:pos + take] = perm[:take]
        pos += take
    arr.flush()
    return np.load(path, mmap_mode="r", allow_pickle=False)


def score_predictions(tab: EventTable, prediction: np.ndarray) -> dict:
    pred = np.clip(prediction.astype(np.float64), -3.0, 3.0)
    err = pred - tab.y.astype(np.float64)
    w = tab.weights

    def group(mask: np.ndarray) -> dict:
        wg = w[mask]
        eg = err[mask]
        denom = float(wg.sum())
        if denom <= 0:
            return {"mass": 0.0}
        return {"mass": denom,
                "rmse_mps2": float(np.sqrt(np.sum(wg * np.mean(eg * eg, axis=1)) / denom)),
                "axis_rmse_mps2": [float(np.sqrt(np.sum(wg * eg[:, j] ** 2) / denom)) for j in range(3)],
                "bias_mps2": [float(np.sum(wg * eg[:, j]) / denom) for j in range(3)]}

    result = group(np.ones(len(w), dtype=bool))
    result["raw_clip_fraction"] = float(np.mean(np.abs(prediction) > 3.0))
    result["by_source"] = {str(k): group(tab.role == k) for k in sorted(set(tab.role))}
    result["by_task"] = {str(k): group(tab.task == k) for k in sorted(set(tab.task))}
    result["by_source_task"] = {f"{r}/{t}": group((tab.role == r) & (tab.task == t))
                                for r in sorted(set(tab.role)) for t in sorted(set(tab.task))}
    result["by_wind"] = {str(int(k)): group(tab.wind == k) for k in sorted(set(tab.wind.tolist()))}
    result["by_phase"] = {str(int(k)): group(tab.phase == k) for k in sorted(set(tab.phase.tolist()))}
    bands = (("1.8_5s", 1.8, 5.0), ("5_10s", 5.0, 10.0), ("10_20s", 10.0, 20.0001))
    result["by_time_band"] = {name: group((tab.time_s >= lo) & (tab.time_s < hi)) for name, lo, hi in bands}
    return result


def eval_table(model: Candidate, tab: EventTable, history: np.ndarray, device: torch.device,
               batch_size: int = 2048) -> tuple[dict, np.ndarray]:
    model.eval()
    x = torch.as_tensor(tab.x, dtype=torch.float32, device=device)
    preds = []
    with torch.no_grad():
        for lo in range(0, len(tab.x), batch_size):
            hi = min(lo + batch_size, len(tab.x))
            hist = None
            if model.family == "HISTORY_KAN":
                idx = tab.history_index[lo:hi]
                h_np = np.array(history[idx], dtype=np.float32, copy=True)
                hist = torch.from_numpy(h_np).to(device)
            preds.append(model(x[lo:hi], hist).cpu().numpy())
    pred = np.concatenate(preds).astype(np.float32)
    return score_predictions(tab, pred), pred


def count_parameters(model: nn.Module) -> int:
    return int(sum(p.numel() for p in model.parameters()))


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    torch.save(state, tmp)
    tmp.replace(path)


def ledger(identity: str, status: str, note: str) -> None:
    path = OUT / "RESOURCE_LEDGER.csv"
    with path.open("r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    matching = [r for r in rows if r["phase"] == "D3_OFFICIAL" and r["resource_type"] == "fit"]
    hit = False
    for r in matching:
        if r["identity"] == identity:
            r["status"] = status
            r["notes"] = note
            hit = True
    if not hit:
        if len(matching) >= 8:
            raise RuntimeError("The eight-fit official comparison budget is exhausted")
        rows.append({"timestamp_utc": utcnow(), "phase": "D3_OFFICIAL", "resource_type": "fit",
                     "identity": identity, "count": "1", "status": status, "notes": note})
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=("timestamp_utc", "phase", "resource_type", "identity", "count", "status", "notes"))
        writer.writeheader()
        writer.writerows(rows)


def state_update(active: str | None, status: str) -> None:
    state_path = OUT / "state/state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    with (OUT / "RESOURCE_LEDGER.csv").open("r", newline="", encoding="utf-8") as f:
        fit_rows = [r for r in csv.DictReader(f)
                    if r["phase"] == "D3_OFFICIAL" and r["resource_type"] == "fit"]
    completed = []
    for family in FAMILIES:
        for seed in SEEDS:
            p = OUT / "models" / family / f"seed{seed}" / "fit_report.json"
            if p.is_file() and json.loads(p.read_text(encoding="utf-8")).get("status") == "COMPLETE":
                completed.append(f"{family}_SEED{seed}")
    state.update({"phase": "D3_OFFICIAL_FITS", "status": status,
                  "next": "STEP4_CANARY" if len(completed) == 8 else "RESUME_STEP3_OFFICIAL_FITS",
                  "fits_started": len(fit_rows), "fits_completed": completed,
                  "active_fit": active, "active_run": None, "plant_started": 0,
                  "updated_at_utc": utcnow()})
    write_json(state_path, state)


def append_rows(path: Path, rows: list[dict], keys: tuple[str, ...] = ()) -> None:
    old = pd.read_csv(path) if path.is_file() else pd.DataFrame()
    if keys and not old.empty:
        for row in rows:
            mask = np.ones(len(old), dtype=bool)
            for key in keys:
                mask &= old[key].astype(str).to_numpy() == str(row[key])
            old = old.loc[~mask]
    pd.concat((old, pd.DataFrame(rows)), ignore_index=True).to_csv(path, index=False)


def evaluate_baselines(val: EventTable, val_hist: np.ndarray, mu: np.ndarray, sigma: np.ndarray) -> None:
    rows = []
    for name, path in (("INITIAL", ROOT / "models/position/initial/best_model.pt"),
                       ("OLD_FINAL", ROOT / "models/position/final_candidate/best_model.pt")):
        checkpoint = torch.load(path, map_location="cpu", weights_only=False)
        model = Candidate("MIXED_KAN", mu, sigma)
        model.kan.load_state_dict(checkpoint["state_dict"])
        model.to(DEVICE)
        detail, _ = eval_table(model, val, val_hist, DEVICE)
        rows.append({"model_id": name, "family": name, "seed": "", "step": 0,
                     "score_mps2": detail["rmse_mps2"], "detail_json": json.dumps(detail, ensure_ascii=False)})
        print(f"BASELINE {name} common_val={detail['rmse_mps2']:.8f}", flush=True)
    append_rows(OUT / "reports/COMMON_OBJECTIVE_EVALUATION.csv", rows, ("model_id", "step"))


def build_model(family: str, seed: int, mu: np.ndarray, sigma: np.ndarray) -> Candidate:
    seed_everything(seed)
    model = Candidate(family, mu, sigma)
    initial = torch.load(ROOT / "models/position/initial/best_model.pt", map_location="cpu", weights_only=False)
    model.kan.load_state_dict(initial["state_dict"])
    return model


def function_preservation(train_eps: list[Episode], val_eps: list[Episode], mu: np.ndarray, sigma: np.ndarray) -> None:
    base_ck = torch.load(ROOT / "models/position/initial/best_model.pt", map_location="cpu", weights_only=False)
    ref = PositionModel(mu, sigma)
    ref.load_state_dict(base_ck["state_dict"])
    ref.eval()
    chosen = [train_eps[0], train_eps[len(train_eps) // 2], train_eps[-1],
              val_eps[0], val_eps[len(val_eps) // 2], val_eps[-1]]
    rows = []
    for family in FAMILIES:
        model = build_model(family, SEEDS[0], mu, sigma).cpu().eval()
        max_phi = 0.0
        max_y = 0.0
        event_count = 0
        with torch.no_grad():
            for ep in chosen:
                windows = np.lib.stride_tricks.sliding_window_view(ep.x14, window_shape=32, axis=0)
                # Every valid event in each fixture is evaluated; windows never cross episode boundaries.
                xw = torch.from_numpy(np.ascontiguousarray(windows.transpose(0, 1, 2), dtype=np.float32))
                if family == "HISTORY_KAN":
                    hw = np.lib.stride_tricks.sliding_window_view(ep.x14[:, :10], window_shape=32, axis=0)
                    h = torch.from_numpy(np.ascontiguousarray(hw, dtype=np.float32))
                else:
                    h = None
                for lo in range(0, len(xw), 512):
                    hi = min(lo + 512, len(xw))
                    hx = h[lo:hi] if h is not None else None
                    p0 = ref(xw[lo:hi])
                    p1 = model(xw[lo:hi], hx)
                    f0 = ref.encode(xw[lo:hi])
                    f1 = model.features(xw[lo:hi], hx)
                    max_phi = max(max_phi, float(torch.max(torch.abs(f0 - f1))))
                    max_y = max(max_y, float(torch.max(torch.abs(p0 - p1))))
                    event_count += hi - lo
        rows.append({"family": family, "seed": SEEDS[0], "fixture_episodes": len(chosen),
                     "valid_real_windows": event_count, "max_abs_phi_difference": max_phi,
                     "max_abs_head_output_difference_mps2": max_y,
                     "pass_1e-7": bool(max(max_phi, max_y) <= 1e-7),
                     "scope": "episode-local TRAIN/VAL windows; W0 fixed-head replay"})
        print(f"PREFLIGHT {family} windows={event_count} phi={max_phi:.3g} output={max_y:.3g}", flush=True)
        if max(max_phi, max_y) > 1e-7:
            raise RuntimeError(f"Function-preserving initialization failed for {family}")
    pd.DataFrame(rows).to_csv(OUT / "reports/FUNCTION_PRESERVATION_PREFLIGHT.csv", index=False)


def weighted_training_step(model: Candidate, x: torch.Tensor, y: torch.Tensor, w: torch.Tensor,
                           hist: torch.Tensor | None, indices: np.ndarray, optimizer: torch.optim.Optimizer,
                           dataset_size: int, device: torch.device) -> None:
    ids = torch.as_tensor(indices.astype(np.int64), dtype=torch.long, device=device)
    xb, yb, wb = x.index_select(0, ids), y.index_select(0, ids), w.index_select(0, ids)
    hb = hist
    pred = model(xb, hb)
    per = F.smooth_l1_loss(pred / 3.0, yb / 3.0, reduction="none").mean(dim=1)
    loss = (dataset_size / len(indices)) * torch.sum(wb * per)
    optimizer.zero_grad(set_to_none=True)
    loss.backward()
    optimizer.step()


def local_sensitivity(model: Candidate, tab: EventTable, history: np.ndarray) -> dict:
    ids = np.linspace(0, len(tab.x) - 1, min(96, len(tab.x)), dtype=np.int64)
    x = torch.as_tensor(tab.x[ids], dtype=torch.float32, device=DEVICE).detach().requires_grad_(True)
    h = None
    if model.family == "HISTORY_KAN":
        h = torch.from_numpy(np.array(history[tab.history_index[ids]], dtype=np.float32, copy=True)).to(DEVICE)
        h.requires_grad_(True)
    model.eval()
    per_output = []
    hist_norms = []
    for axis in range(3):
        pred = model(x, h)
        if h is None:
            (grad_x,) = torch.autograd.grad(pred[:, axis].sum(), (x,))
            grad_h = None
        else:
            grad_x, grad_h = torch.autograd.grad(pred[:, axis].sum(), (x, h), allow_unused=True)
        per_output.append(grad_x.detach().norm(dim=1).mean().item())
        if grad_h is not None:
            hist_norms.append(grad_h.detach().flatten(1).norm(dim=1).mean().item())
    return {"sample_count": int(len(ids)), "mean_output_gradient_l2_by_axis_per_current_X14": per_output,
            "mean_output_gradient_l2_by_axis_per_32x10_history": hist_norms or None,
            "interpretation": "local autograd sensitivity on common VAL inputs; not closed-loop gain"}


def cpu_inference_latency(model: Candidate, tab: EventTable, history: np.ndarray) -> dict:
    cpu_model = Candidate(model.family, model.kan.input_mu.detach().cpu().numpy().reshape(-1),
                          model.kan.input_sigma.detach().cpu().numpy().reshape(-1))
    cpu_model.load_state_dict({k: v.detach().cpu() for k, v in model.state_dict().items()})
    cpu_model.eval()
    x = torch.from_numpy(tab.x[:1].copy())
    h = None
    if model.family == "HISTORY_KAN":
        h = torch.from_numpy(np.array(history[tab.history_index[:1]], dtype=np.float32, copy=True))
    with torch.no_grad():
        for _ in range(30):
            cpu_model(x, h)
        times = []
        for _ in range(300):
            t0 = time.perf_counter()
            cpu_model(x, h)
            times.append((time.perf_counter() - t0) * 1000.0)
    return {"backend": "PyTorch CPU, batch=1, 30 warmups, 300 measurements",
            "mean_ms": float(np.mean(times)), "p50_ms": float(np.median(times)),
            "p95_ms": float(np.percentile(times, 95)),
            "limitation": "not MATLAB deployment timing"}


def fit_one(family: str, seed: int, mixed: EventTable, teacher: EventTable, val: EventTable,
            train_hist_path: Path, val_hist_path: Path, mu: np.ndarray, sigma: np.ndarray) -> dict:
    identity = f"{family}_SEED{seed}"
    folder = OUT / "models" / family / f"seed{seed}"
    folder.mkdir(parents=True, exist_ok=True)
    report_path = folder / "fit_report.json"
    if report_path.is_file():
        old = json.loads(report_path.read_text(encoding="utf-8"))
        if old.get("status") == "COMPLETE" and old.get("optimizer_steps") == STEPS:
            ledger(identity, "COMPLETED", "Resumed state already contains complete fixed-budget fit.")
            print(f"SKIP_COMPLETE {identity}", flush=True)
            return old
    tab = teacher if family == "TEACHER_KAN" else mixed
    train_history = np.load(train_hist_path, mmap_mode="r", allow_pickle=False)
    val_history = np.load(val_hist_path, mmap_mode="r", allow_pickle=False)
    order = build_order(len(tab.x), seed)
    x = torch.as_tensor(tab.x, dtype=torch.float32, device=DEVICE)
    y = torch.as_tensor(tab.y, dtype=torch.float32, device=DEVICE)
    w = torch.as_tensor(tab.weights, dtype=torch.float32, device=DEVICE)
    model = build_model(family, seed, mu, sigma).to(DEVICE)
    optimizer = torch.optim.Adam(model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)
    latest = folder / "latest_checkpoint.pt"
    ck = None
    if latest.is_file():
        ck = torch.load(latest, map_location=DEVICE, weights_only=False)
        if ck.get("identity") != identity or ck.get("batch_order_seed") != seed or ck.get("train_rows") != len(tab.x):
            raise RuntimeError(f"Checkpoint does not match fixed fit identity: {identity}")
        model.load_state_dict(ck["model"])
        optimizer.load_state_dict(ck["optimizer"])
        step0 = int(ck["step"])
        history_rows = ck["history"]
        best_score = float(ck["best_score"])
        best_step = int(ck["best_step"])
        best_state = ck["best_state"]
        elapsed_prior = float(ck.get("elapsed_seconds", 0.0))
        np.random.set_state(ck["numpy_rng"])
        torch.set_rng_state(ck["torch_rng"])
        if torch.cuda.is_available() and ck.get("cuda_rng") is not None:
            torch.cuda.set_rng_state_all(ck["cuda_rng"])
    else:
        step0, history_rows, best_step = 0, [], 0
        elapsed_prior = 0.0
        val0, _ = eval_table(model, val, val_history, DEVICE)
        best_score = val0["rmse_mps2"]
        best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
    ledger(identity, "RUNNING", f"Fixed 60000 optimizer steps, batch 256, common VAL every 3000; no Plant.")
    state_update(identity, "IN_PROGRESS")
    protocol = {"identity": identity, "family": family, "chinese_name": CHINESE[family], "seed": seed,
                "train_rows": len(tab.x), "train_run_ids": sorted(set(tab.run_id.tolist())),
                "val_rows": len(val.x), "val_run_ids": sorted(set(val.run_id.tolist())),
                "batch_order_seed": seed, "optimizer_steps": STEPS, "batch_size": BATCH,
                "learning_rate": LR, "weight_decay": WEIGHT_DECAY, "evaluation": "common fixed 144-run VAL, every 3000 steps including step0",
                "loss": "N/B * sum(sample_weight * mean(SmoothL1(pred/3, target_clip/3)))",
                "sampling": "uniform without replacement per generated permutation cycle; one weighted loss only; no weighted sampler",
                "optimizer": "Adam", "base_checkpoint_sha256": sha256(ROOT / "models/position/initial/best_model.pt"),
                "train_history_input": "real episode-local 32 event X14[0:10] windows" if family == "HISTORY_KAN" else "latest X14 event only",
                "selected_by": "lowest common VAL clipped physical RMSE; VAL is development information, not blind TEST"}
    write_json(folder / "fit_protocol.json", protocol)
    if ck is None:
        detail, _ = eval_table(model, val, val_history, DEVICE)
        row = {"model_id": identity, "family": family, "seed": seed, "step": 0,
               "score_mps2": detail["rmse_mps2"], "detail_json": json.dumps(detail, ensure_ascii=False)}
        append_rows(OUT / "reports/COMMON_OBJECTIVE_EVALUATION.csv", [row], ("model_id", "step"))
        history_rows.append({"fit_id": identity, "family": family, "seed": seed, "step": 0,
                             "common_val_score_mps2": detail["rmse_mps2"], "detail_json": row["detail_json"]})
        initial_state = {"identity": identity, "batch_order_seed": seed, "train_rows": len(tab.x), "step": 0,
                         "model": {k: v.detach().cpu().clone() for k, v in model.state_dict().items()},
                         "optimizer": optimizer.state_dict(), "history": history_rows,
                         "best_score": best_score, "best_step": 0, "best_state": best_state,
                         "elapsed_seconds": 0.0, "numpy_rng": np.random.get_state(),
                         "torch_rng": torch.get_rng_state(),
                         "cuda_rng": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else None}
        save_state(latest, initial_state)
        save_state(folder / "checkpoints" / "step_000000.pt", initial_state)
    tic = time.perf_counter()
    try:
        for step in range(step0 + 1, STEPS + 1):
            lo = (step - 1) * BATCH
            ids = np.asarray(order[lo:lo + BATCH], dtype=np.int64)
            hist_batch = None
            if family == "HISTORY_KAN":
                hist_np = np.array(train_history[tab.history_index[ids]], dtype=np.float32, copy=True)
                hist_batch = torch.from_numpy(hist_np).to(DEVICE)
            model.train()
            weighted_training_step(model, x, y, w, hist_batch, ids, optimizer, len(tab.x), DEVICE)
            do_eval = step % EVAL_EVERY == 0
            do_checkpoint = step % CHECKPOINT_EVERY == 0 or do_eval
            detail = None
            if do_eval:
                detail, _ = eval_table(model, val, val_history, DEVICE)
                val_score = detail["rmse_mps2"]
                if val_score < best_score - 1e-12:
                    best_score, best_step = val_score, step
                    best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
                interval_seconds = time.perf_counter() - tic
                elapsed_prior += interval_seconds
                tic = time.perf_counter()
                curve = {"fit_id": identity, "family": family, "seed": seed, "step": step,
                         "common_val_score_mps2": val_score,
                         "best_common_val_score_mps2": best_score, "best_step": best_step,
                         "detail_json": json.dumps(detail, ensure_ascii=False)}
                history_rows.append(curve)
                append_rows(OUT / "reports/TRAINING_CURVES.csv", [curve], ("fit_id", "step"))
                append_rows(OUT / "reports/COMMON_OBJECTIVE_EVALUATION.csv",
                            [{"model_id": identity, "family": family, "seed": seed, "step": step,
                              "score_mps2": val_score, "detail_json": curve["detail_json"]}],
                            ("model_id", "step"))
                write_json(folder / "fit_progress.json", {"fit_id": identity, "status": "RUNNING", "step": step,
                            "total_steps": STEPS, "latest_common_val_score_mps2": val_score,
                            "best_common_val_score_mps2": best_score, "best_step": best_step,
                            "recent_steps_per_second": EVAL_EVERY / max(interval_seconds, 1e-9),
                            "updated_at_utc": utcnow()})
                print(f"[{identity}] step={step}/{STEPS} val={val_score:.8f} best={best_score:.8f}@{best_step} "
                      f"rate={EVAL_EVERY/max(interval_seconds, 1e-9):.1f} steps/s elapsed={elapsed_prior/60:.1f}min", flush=True)
            if do_checkpoint:
                state = {"identity": identity, "batch_order_seed": seed, "train_rows": len(tab.x), "step": step,
                         "model": {k: v.detach().cpu().clone() for k, v in model.state_dict().items()},
                         "optimizer": optimizer.state_dict(), "history": history_rows,
                         "best_score": best_score, "best_step": best_step, "best_state": best_state,
                         "elapsed_seconds": elapsed_prior + time.perf_counter() - tic,
                         "numpy_rng": np.random.get_state(), "torch_rng": torch.get_rng_state(),
                         "cuda_rng": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else None}
                save_state(latest, state)
                if do_eval:
                    save_state(folder / "checkpoints" / f"step_{step:06d}.pt", state)
        model.load_state_dict(best_state)
        train_detail, train_pred = eval_table(model, tab, train_history, DEVICE, batch_size=4096)
        val_detail, _ = eval_table(model, val, val_history, DEVICE)
        sensitivity = local_sensitivity(model, val, val_history)
        latency = cpu_inference_latency(model, val, val_history)
        model_path = folder / "best_model.pt"
        torch.save({"family": family, "seed": seed, "selected_step": best_step,
                    "state_dict": {k: v.detach().cpu() for k, v in model.state_dict().items()},
                    "input_dim": 14, "modality": "position", "base_checkpoint": "DL1018 Initial",
                    "normalizer": "frozen Initial TRAIN-only X14", "common_val_score_mps2": val_detail["rmse_mps2"]}, model_path)
        report = {"fit_id": identity, "family": family, "chinese_name": CHINESE[family], "seed": seed,
                  "status": "COMPLETE", "optimizer": "Adam", "learning_rate": LR,
                  "weight_decay": WEIGHT_DECAY, "optimizer_steps": STEPS, "batch_size": BATCH,
                  "train_episodes": len(set(tab.run_id.tolist())), "train_windows": len(tab.x),
                  "train_endpoint_exposures": STEPS * BATCH, "val_episodes": len(set(val.run_id.tolist())),
                  "val_windows": len(val.x), "best_step": best_step,
                  "selected_common_val_score_mps2": val_detail["rmse_mps2"],
                  "selected_common_val_detail": val_detail,
                  "selected_training_physical_rmse": train_detail,
                  "parameter_count_total": count_parameters(model),
                  "parameter_count_added_branch": (count_parameters(model) - count_parameters(model.kan)),
                  "cpu_inference_latency": latency, "local_input_sensitivity": sensitivity,
                  "sample_weights_applied_once": True, "weighted_sampler_used": False,
                  "train_history_input": "episode-local raw X14[0:10] 32-event windows" if family == "HISTORY_KAN" else "current X14 only",
                  "model_path": str(model_path.relative_to(ROOT)).replace("\\", "/"),
                  "training_seconds": elapsed_prior, "common_validation_is_dev_not_blind_test": True,
                  "new_plant_starts": 0, "new_fits": 1}
        write_json(report_path, report)
        write_json(folder / "fit_progress.json", {"fit_id": identity, "status": "COMPLETE", "step": STEPS,
                    "total_steps": STEPS, "best_common_val_score_mps2": val_detail["rmse_mps2"],
                    "best_step": best_step, "updated_at_utc": utcnow()})
        write_json(folder / "model.json", {k: report[k] for k in ("fit_id", "family", "chinese_name", "seed",
                    "parameter_count_total", "parameter_count_added_branch", "best_step", "model_path")})
        pd.DataFrame(history_rows).to_csv(folder / "training_history.csv", index=False)
        ledger(identity, "COMPLETED", f"60000 optimizer steps; best={best_score:.8g}@{best_step}; 0 Plant")
        state_update(None, "IN_PROGRESS")
        append_rows(OUT / "reports/TRAINING_COMPARISON.csv", [{
            "fit_id": identity, "family": family, "chinese_name": CHINESE[family], "seed": seed,
            "train_episodes": report["train_episodes"], "train_windows": len(tab.x),
            "optimizer_steps": STEPS, "endpoint_exposures": STEPS * BATCH,
            "best_step": best_step, "common_val_score_mps2": val_detail["rmse_mps2"],
            "train_score_mps2": train_detail["rmse_mps2"], "parameter_count_total": count_parameters(model),
            "parameter_count_added_branch": report["parameter_count_added_branch"],
            "training_seconds": elapsed_prior, "model_path": report["model_path"],
            "common_val_detail_json": json.dumps(val_detail, ensure_ascii=False),
            "train_detail_json": json.dumps(train_detail, ensure_ascii=False)}], ("fit_id",))
        print(f"COMPLETE {identity} best_step={best_step} val={val_detail['rmse_mps2']:.8f} "
              f"train={train_detail['rmse_mps2']:.8f} params={count_parameters(model)}", flush=True)
        return report
    except Exception as exc:
        write_json(folder / "fit_failure.json", {"fit_id": identity, "status": "FAILED_ENGINEERING_OR_NUMERIC",
                    "step": int(step if "step" in locals() else step0), "error_type": type(exc).__name__,
                    "error": str(exc), "updated_at_utc": utcnow()})
        ledger(identity, "FAILED", f"step={step if 'step' in locals() else step0}; {type(exc).__name__}: {exc}")
        state_update(identity, "NEEDS_REVIEW")
        raise


def protocol_manifest(train: list[Episode], val: list[Episode], mixed: EventTable,
                      teacher: EventTable, val_tab: EventTable) -> None:
    data = {"task": "DL1018_TRAINING_DATA_STRUCTURE_COMPARE_V2", "phase": "D3_OFFICIAL_FITS",
            "seeds": list(SEEDS), "families": list(FAMILIES), "optimizer_steps_per_fit": STEPS,
            "max_official_fits": 8, "optimizer": {"name": "Adam", "lr": LR,
            "weight_decay": WEIGHT_DECAY, "batch_size": BATCH},
            "checkpoint_and_evaluation_steps": list(range(0, STEPS + 1, EVAL_EVERY)),
            "source_mass": {"MIXED": MIXED_MASS, "TEACHER": TEACHER_MASS,
                            "COMMON_VAL": MIXED_MASS},
            "rows": {"mixed_train_episodes": len(set(mixed.run_id.tolist())),
                    "mixed_train_endpoints": len(mixed.x), "teacher_train_episodes": len(set(teacher.run_id.tolist())),
                    "teacher_train_endpoints": len(teacher.x), "common_val_episodes": len(set(val_tab.run_id.tolist())),
                    "common_val_endpoints": len(val_tab.x)},
            "normalizer": "same frozen DL1018 Initial TRAIN-only X14 normalizer",
            "label": "existing target_clip in m/s^2; unchanged",
            "head": "same Initial 33x3 head initialization; all model parameters train offline; deployed online head remains unchanged",
            "source_weighting": "uniform sampling plus one hierarchical weighted loss; no WeightedRandomSampler",
            "selection": "lowest common VAL clipped physical RMSE; shared VAL includes B/POS_OFF/Student, is development data and not blind TEST",
            "no_plant_during_training": True, "no_contract_or_B_changes": True,
            "history_input": "first 10 raw X14 features, true current-plus-past 32 events from each single episode"}
    write_json(OUT / "manifests/FIT_PROTOCOL.json", data)


def main() -> None:
    norm = np.load(ROOT / "models/position/initial/normalizer.npz")
    mu = np.asarray(norm["mu"], dtype=np.float32).reshape(-1)
    sigma = np.maximum(np.asarray(norm["sigma"], dtype=np.float32).reshape(-1), 1e-4)
    train_eps = load_episodes("train")
    val_eps = load_episodes("val")
    if len(train_eps) != 1920 or len(val_eps) != 144:
        raise RuntimeError(f"Fixed task pool changed: TRAIN={len(train_eps)} VAL={len(val_eps)}")
    assign_weights(train_eps, MIXED_MASS)
    train_offsets = offsets_for(train_eps)
    train_history_path, train_history = ensure_history_cache("train", train_eps, train_offsets)
    mixed = assemble(train_eps, train_offsets)
    teacher_eps = [e for e in train_eps if e.role in TEACHER_MASS]
    assign_weights(teacher_eps, TEACHER_MASS)
    teacher = assemble(teacher_eps, train_offsets)
    if len(mixed.x) != 756480 or len(teacher.x) != 605184:
        raise RuntimeError(f"Unexpected train endpoint counts: mixed={len(mixed.x)}, teacher={len(teacher.x)}")
    assign_weights(val_eps, MIXED_MASS)
    val_offsets = offsets_for(val_eps)
    val_history_path, val_history = ensure_history_cache("val", val_eps, val_offsets)
    val = assemble(val_eps, val_offsets)
    if len(val.x) != 56736 or not np.isclose(mixed.weights.sum(), 1) or not np.isclose(teacher.weights.sum(), 1):
        raise RuntimeError("Training/validation weights or endpoint counts are invalid")
    protocol_manifest(train_eps, val_eps, mixed, teacher, val)
    function_preservation(train_eps, val_eps, mu, sigma)
    evaluate_baselines(val, val_history, mu, sigma)
    print(f"D3_READY device={DEVICE} mixed={len(mixed.x)} teacher={len(teacher.x)} val={len(val.x)} "
          f"history_bytes={train_history_path.stat().st_size + val_history_path.stat().st_size}", flush=True)
    for family in FAMILIES:
        for seed in SEEDS:
            fit_one(family, seed, mixed, teacher, val, train_history_path, val_history_path, mu, sigma)
    state_update(None, "COMPLETE")
    reports = []
    for family in FAMILIES:
        for seed in SEEDS:
            reports.append(json.loads((OUT / "models" / family / f"seed{seed}" / "fit_report.json").read_text(encoding="utf-8")))
    summary = pd.DataFrame([{k: r.get(k) for k in ("fit_id", "family", "chinese_name", "seed", "optimizer_steps",
                    "best_step", "selected_common_val_score_mps2", "parameter_count_total",
                    "parameter_count_added_branch", "training_seconds", "model_path")} for r in reports])
    summary.to_csv(OUT / "reports/TRAINING_COMPARISON.csv", index=False)
    means = summary.groupby("family").selected_common_val_score_mps2.agg(["mean", "std"]).reset_index()
    lines = ["# 种子方向复核", "", "两个预定 seed 均已完成固定预算。此表只汇报共同 VAL 开发分数，不视为盲测，也不替代同场闭环。", "",
             "| 方案 | seed 1911 | seed 1912 | 均值±标准差 |", "|---|---:|---:|---:|"]
    for family in FAMILIES:
        vals = [r["selected_common_val_score_mps2"] for r in reports if r["family"] == family]
        lines.append(f"| {family} | {vals[0]:.6f} | {vals[1]:.6f} | {np.mean(vals):.6f} ± {np.std(vals, ddof=1):.6f} |")
    lines += ["", "seed 1911 为预指定 canary 包；不得看 canary 后切换 seed。若两 seed 离线排序相反，记录为方向不稳定，不按较优 seed 重新选择。", ""]
    (OUT / "reports/SEED_DIRECTION_CHECK.md").write_text("\n".join(lines), encoding="utf-8")
    print("D3_OFFICIAL_FITS_COMPLETE", flush=True)


if __name__ == "__main__":
    main()
