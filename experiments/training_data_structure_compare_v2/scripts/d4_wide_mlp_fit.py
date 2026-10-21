from __future__ import annotations

import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.nn import functional as F

HERE = Path(__file__).resolve()
OUT = HERE.parents[1]
ROOT = HERE.parents[3]
sys.path.insert(0, str(HERE.parent))
import d4_official_fits as base  # shared frozen data assembly, weights, and scoring

SEED = 2026101911
FAMILY = "WIDE_MLP"
IDENTITY = f"{FAMILY}_SEED{SEED}"
STEPS = base.STEPS
BATCH = base.BATCH
LR = base.LR
WEIGHT_DECAY = base.WEIGHT_DECAY


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


class WideCurrentMLP(nn.Module):
    """Random-init, current-event 14 -> 128 -> 128 -> 32 encoder plus shared-shape W0."""

    family = FAMILY

    def __init__(self, mu: np.ndarray, sigma: np.ndarray):
        super().__init__()
        self.register_buffer("mu", torch.as_tensor(mu, dtype=torch.float32).reshape(1, 14))
        self.register_buffer("sigma", torch.as_tensor(sigma, dtype=torch.float32).reshape(1, 14))
        self.fc1 = nn.Linear(14, 128)
        self.fc2 = nn.Linear(128, 128)
        self.fc3 = nn.Linear(128, 32)
        self.head = nn.Linear(33, 3, bias=False)

    def features(self, x14: torch.Tensor, _history: torch.Tensor | None = None) -> torch.Tensor:
        if x14.ndim == 3:
            if x14.shape[1] != 14:
                raise ValueError(f"Expected [batch,14,time], got {tuple(x14.shape)}")
            x14 = x14[:, :, -1]
        if x14.ndim != 2 or x14.shape[1] != 14:
            raise ValueError(f"Expected current X14, got {tuple(x14.shape)}")
        z = (x14 - self.mu) / self.sigma
        h = torch.tanh(self.fc3(F.silu(self.fc2(F.silu(self.fc1(z))))))
        phi = torch.cat((h, torch.ones_like(h[:, :1])), dim=1)
        return phi / torch.sqrt(1.0 + torch.sum(h * h, dim=1, keepdim=True))

    def forward(self, x14: torch.Tensor, history: torch.Tensor | None = None) -> torch.Tensor:
        return self.head(self.features(x14, history))


def resource_ledger(status: str, note: str) -> None:
    path = OUT / "RESOURCE_LEDGER.csv"
    columns = ("timestamp_utc", "phase", "resource_type", "identity", "count", "status", "notes")
    rows = list(csv.DictReader(path.open("r", newline="", encoding="utf-8"))) if path.is_file() else []
    rows = [r for r in rows if r.get("identity") != IDENTITY]
    rows.append({"timestamp_utc": utcnow(), "phase": "D3_MLP_EXPLORATORY", "resource_type": "fit",
                 "identity": IDENTITY, "count": "1", "status": status, "notes": note})
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def append_comparison(row: dict) -> None:
    path = OUT / "reports" / "TRAINING_COMPARISON.csv"
    old = pd.read_csv(path) if path.is_file() else pd.DataFrame()
    if not old.empty and "fit_id" in old:
        old = old.loc[old.fit_id.astype(str) != IDENTITY]
    pd.concat((old, pd.DataFrame([row])), ignore_index=True).to_csv(path, index=False)


def load_tables(mu: np.ndarray, sigma: np.ndarray):
    del mu, sigma
    train_eps = base.load_episodes("train")
    val_eps = base.load_episodes("val")
    if len(train_eps) != 1920 or len(val_eps) != 144:
        raise RuntimeError(f"Frozen task pool changed: TRAIN={len(train_eps)} VAL={len(val_eps)}")
    base.assign_weights(train_eps, base.MIXED_MASS)
    train_offsets = base.offsets_for(train_eps)
    train_hist_path, train_history = base.ensure_history_cache("train", train_eps, train_offsets)
    mixed = base.assemble(train_eps, train_offsets)
    base.assign_weights(val_eps, base.MIXED_MASS)
    val_offsets = base.offsets_for(val_eps)
    val_hist_path, val_history = base.ensure_history_cache("val", val_eps, val_offsets)
    val = base.assemble(val_eps, val_offsets)
    if len(mixed.x) != 756480 or len(val.x) != 56736:
        raise RuntimeError(f"Frozen endpoint counts changed: TRAIN={len(mixed.x)} VAL={len(val.x)}")
    if not np.isclose(mixed.weights.sum(), 1) or not np.isclose(val.weights.sum(), 1):
        raise RuntimeError("Mixed TRAIN/VAL source weights do not each sum to one")
    return mixed, val, train_hist_path, val_hist_path, train_history, val_history


def main() -> None:
    norm = np.load(ROOT / "models/position/initial/normalizer.npz")
    mu = np.asarray(norm["mu"], dtype=np.float32).reshape(-1)
    sigma = np.maximum(np.asarray(norm["sigma"], dtype=np.float32).reshape(-1), 1e-4)
    mixed, val, train_hist_path, val_hist_path, train_history, val_history = load_tables(mu, sigma)
    del train_history, val_history

    folder = OUT / "models" / FAMILY / f"seed{SEED}"
    folder.mkdir(parents=True, exist_ok=True)
    report_path = folder / "fit_report.json"
    if report_path.is_file() and json.loads(report_path.read_text(encoding="utf-8")).get("status") == "COMPLETE":
        print(f"SKIP_COMPLETE {IDENTITY}", flush=True)
        return

    base.seed_everything(SEED)
    order = base.build_order(len(mixed.x), SEED)
    x = torch.as_tensor(mixed.x, dtype=torch.float32, device=base.DEVICE)
    y = torch.as_tensor(mixed.y, dtype=torch.float32, device=base.DEVICE)
    w = torch.as_tensor(mixed.weights, dtype=torch.float32, device=base.DEVICE)
    model = WideCurrentMLP(mu, sigma).to(base.DEVICE)
    optimizer = torch.optim.Adam(model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)
    latest = folder / "latest_checkpoint.pt"
    history_rows: list[dict] = []
    best_step = 0
    best_score = float("inf")
    best_state = None
    elapsed_prior = 0.0

    if latest.is_file():
        ck = torch.load(latest, map_location=base.DEVICE, weights_only=False)
        if ck.get("identity") != IDENTITY or ck.get("train_rows") != len(mixed.x):
            raise RuntimeError(f"Checkpoint identity mismatch for {IDENTITY}")
        model.load_state_dict(ck["model"])
        optimizer.load_state_dict(ck["optimizer"])
        step0 = int(ck["step"])
        history_rows = ck["history"]
        best_step = int(ck["best_step"])
        best_score = float(ck["best_score"])
        best_state = ck["best_state"]
        elapsed_prior = float(ck.get("elapsed_seconds", 0.0))
        np.random.set_state(ck["numpy_rng"])
        torch.set_rng_state(ck["torch_rng"])
        if torch.cuda.is_available() and ck.get("cuda_rng") is not None:
            torch.cuda.set_rng_state_all(ck["cuda_rng"])
    else:
        step0 = 0
        detail, _ = base.eval_table(model, val, np.load(val_hist_path, mmap_mode="r", allow_pickle=False), base.DEVICE)
        best_score = float(detail["rmse_mps2"])
        best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        history_rows.append({"fit_id": IDENTITY, "family": FAMILY, "seed": SEED, "step": 0,
                             "common_val_score_mps2": best_score, "detail_json": json.dumps(detail)})
        torch.save({"identity": IDENTITY, "train_rows": len(mixed.x), "step": 0,
                    "model": {k: v.detach().cpu().clone() for k, v in model.state_dict().items()},
                    "optimizer": optimizer.state_dict(), "history": history_rows,
                    "best_score": best_score, "best_step": 0, "best_state": best_state,
                    "elapsed_seconds": 0.0, "numpy_rng": np.random.get_state(),
                    "torch_rng": torch.get_rng_state(),
                    "cuda_rng": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else None}, latest)

    val_history = np.load(val_hist_path, mmap_mode="r", allow_pickle=False)
    protocol = {"fit_id": IDENTITY, "family": FAMILY, "seed": SEED,
                "status": "USER_AUTHORIZED_ADDITIONAL_EXPLORATORY_CANDIDATE",
                "optimizer_steps": STEPS, "batch_size": BATCH, "learning_rate": LR,
                "weight_decay": WEIGHT_DECAY, "optimizer": "Adam",
                "architecture": "current-event X14 -> Linear(14,128), SiLU -> Linear(128,128), SiLU -> Linear(128,32), tanh, normalized 33D feature, linear 33x3 head",
                "initialization": "random initialization; does not preserve DL1018 Initial function",
                "training_pool": "same frozen mixed TRAIN, B/POS_OFF/Student masses 0.25/0.25/0.50",
                "loss_and_sampling": "shared fixed one-time weighted loss and uniform permutation batch order",
                "selection": "minimum shared fixed VAL clipped physical RMSE; VAL is development, not blind TEST",
                "new_data": 0, "new_plant_starts_during_fit": 0}
    write_json(folder / "fit_protocol.json", protocol)
    write_json(OUT / "state" / "mlp_state.json", {"phase": "D3_MLP_EXPLORATORY", "status": "IN_PROGRESS",
               "active_fit": IDENTITY, "step": step0, "total_steps": STEPS, "updated_at_utc": utcnow()})
    resource_ledger("RUNNING", "One user-authorized MLP exploratory fit; no second seed; no Plant during training.")
    train_hist = np.load(train_hist_path, mmap_mode="r", allow_pickle=False)
    tic = time.perf_counter()
    for step in range(step0 + 1, STEPS + 1):
        lo = (step - 1) * BATCH
        ids = np.asarray(order[lo:lo + BATCH], dtype=np.int64)
        base.weighted_training_step(model, x, y, w, None, ids, optimizer, len(mixed.x), base.DEVICE)
        do_eval = step % base.EVAL_EVERY == 0
        do_checkpoint = step % base.CHECKPOINT_EVERY == 0 or do_eval
        if do_eval:
            detail, _ = base.eval_table(model, val, val_history, base.DEVICE)
            score = float(detail["rmse_mps2"])
            if score < best_score - 1e-12:
                best_score, best_step = score, step
                best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            elapsed = time.perf_counter() - tic
            elapsed_prior += elapsed
            tic = time.perf_counter()
            curve = {"fit_id": IDENTITY, "family": FAMILY, "seed": SEED, "step": step,
                     "common_val_score_mps2": score, "best_common_val_score_mps2": best_score,
                     "best_step": best_step, "detail_json": json.dumps(detail, ensure_ascii=False)}
            history_rows.append(curve)
            base.append_rows(OUT / "reports/TRAINING_CURVES.csv", [curve], ("fit_id", "step"))
            base.append_rows(OUT / "reports/COMMON_OBJECTIVE_EVALUATION.csv",
                             [{"model_id": IDENTITY, "family": FAMILY, "seed": SEED, "step": step,
                               "score_mps2": score, "detail_json": curve["detail_json"]}], ("model_id", "step"))
            rate = base.EVAL_EVERY / max(elapsed, 1e-9)
            write_json(folder / "fit_progress.json", {"fit_id": IDENTITY, "status": "RUNNING", "step": step,
                       "total_steps": STEPS, "latest_common_val_score_mps2": score,
                       "best_common_val_score_mps2": best_score, "best_step": best_step,
                       "recent_steps_per_second": rate, "updated_at_utc": utcnow()})
            print(f"[{IDENTITY}] step={step}/{STEPS} val={score:.8f} best={best_score:.8f}@{best_step} rate={rate:.1f} steps/s", flush=True)
        if do_checkpoint:
            torch.save({"identity": IDENTITY, "train_rows": len(mixed.x), "step": step,
                        "model": {k: v.detach().cpu().clone() for k, v in model.state_dict().items()},
                        "optimizer": optimizer.state_dict(), "history": history_rows,
                        "best_score": best_score, "best_step": best_step, "best_state": best_state,
                        "elapsed_seconds": elapsed_prior + time.perf_counter() - tic,
                        "numpy_rng": np.random.get_state(), "torch_rng": torch.get_rng_state(),
                        "cuda_rng": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else None}, latest)

    model.load_state_dict(best_state)
    train_detail, _ = base.eval_table(model, mixed, train_hist, base.DEVICE, batch_size=4096)
    val_detail, _ = base.eval_table(model, val, val_history, base.DEVICE)
    sensitivity = base.local_sensitivity(model, val, val_history)
    cpu_model = WideCurrentMLP(mu, sigma).cpu()
    cpu_model.load_state_dict({k: v.detach().cpu() for k, v in model.state_dict().items()})
    cpu_model.eval()
    cpu_x = torch.from_numpy(val.x[:1].copy())
    with torch.no_grad():
        for _ in range(30):
            cpu_model(cpu_x)
        timings = []
        for _ in range(300):
            t0 = time.perf_counter()
            cpu_model(cpu_x)
            timings.append((time.perf_counter() - t0) * 1000)
    latency = {"backend": "PyTorch CPU batch=1; 30 warmups, 300 measurements",
               "mean_ms": float(np.mean(timings)), "p50_ms": float(np.median(timings)),
               "p95_ms": float(np.percentile(timings, 95)), "limitation": "not MATLAB deployment timing"}
    model_path = folder / "best_model.pt"
    torch.save({"family": FAMILY, "seed": SEED, "selected_step": best_step,
                "state_dict": {k: v.detach().cpu() for k, v in model.state_dict().items()},
                "input_dim": 14, "modality": "position", "normalizer": "frozen Initial TRAIN-only X14"}, model_path)
    report = {"fit_id": IDENTITY, "family": FAMILY, "seed": SEED, "status": "COMPLETE",
              "optimizer": "Adam", "learning_rate": LR, "weight_decay": WEIGHT_DECAY,
              "optimizer_steps": STEPS, "batch_size": BATCH, "train_episodes": len(set(mixed.run_id.tolist())),
              "train_windows": len(mixed.x), "train_endpoint_exposures": STEPS * BATCH,
              "val_episodes": len(set(val.run_id.tolist())), "val_windows": len(val.x),
              "best_step": best_step, "selected_common_val_score_mps2": val_detail["rmse_mps2"],
              "selected_common_val_detail": val_detail, "selected_training_physical_rmse": train_detail,
              "parameter_count_total": sum(p.numel() for p in model.parameters()),
              "cpu_inference_latency": latency, "local_input_sensitivity": sensitivity,
              "train_history_input": "current X14 only", "initialization": "random; no Initial function preservation",
              "model_path": str(model_path.relative_to(ROOT)).replace("\\", "/"),
              "training_seconds": elapsed_prior, "common_validation_is_dev_not_blind_test": True,
              "new_plant_starts": 0, "new_fits": 1}
    write_json(report_path, report)
    write_json(folder / "fit_progress.json", {"fit_id": IDENTITY, "status": "COMPLETE", "step": STEPS,
               "total_steps": STEPS, "best_common_val_score_mps2": best_score, "best_step": best_step,
               "updated_at_utc": utcnow()})
    pd.DataFrame(history_rows).to_csv(folder / "training_history.csv", index=False)
    append_comparison({"fit_id": IDENTITY, "family": FAMILY, "chinese_name": "宽MLP探索候选",
                       "seed": SEED, "train_episodes": report["train_episodes"], "train_windows": len(mixed.x),
                       "optimizer_steps": STEPS, "endpoint_exposures": STEPS * BATCH,
                       "best_step": best_step, "common_val_score_mps2": val_detail["rmse_mps2"],
                       "train_score_mps2": train_detail["rmse_mps2"],
                       "parameter_count_total": report["parameter_count_total"],
                       "parameter_count_added_branch": None, "training_seconds": elapsed_prior,
                       "model_path": report["model_path"],
                       "common_val_detail_json": json.dumps(val_detail, ensure_ascii=False),
                       "train_detail_json": json.dumps(train_detail, ensure_ascii=False)})
    resource_ledger("COMPLETED", f"{STEPS} optimizer steps; best={best_score:.8g}@{best_step}; 0 Plant; one seed only.")
    write_json(OUT / "state" / "mlp_state.json", {"phase": "D3_MLP_EXPLORATORY", "status": "COMPLETE",
               "active_fit": None, "step": STEPS, "total_steps": STEPS, "updated_at_utc": utcnow()})
    print(f"COMPLETE {IDENTITY} best_step={best_step} val={val_detail['rmse_mps2']:.8f} "
          f"train={train_detail['rmse_mps2']:.8f} params={report['parameter_count_total']}", flush=True)


if __name__ == "__main__":
    main()
