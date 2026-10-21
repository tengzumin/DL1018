from __future__ import annotations

import csv
import json
import os
import sys
import time
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
from models import PositionModel  # noqa: E402
from data_runtime import Episode, load_episodes  # noqa: E402

SEED = 2026101909
STEPS = 6000
BATCH = 256
EVAL_STEPS = (0, 1000, 3000, 6000)


class WideCurrentMLP(nn.Module):
    def __init__(self, mu: np.ndarray, sigma: np.ndarray):
        super().__init__()
        self.register_buffer("mu", torch.as_tensor(mu, dtype=torch.float32).reshape(1, 14))
        self.register_buffer("sigma", torch.as_tensor(sigma, dtype=torch.float32).reshape(1, 14))
        self.fc1 = nn.Linear(14, 128)
        self.fc2 = nn.Linear(128, 128)
        self.fc3 = nn.Linear(128, 32)
        self.head = nn.Linear(33, 3, bias=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if x.ndim == 3:
            x = x[:, :, -1]
        z = (x - self.mu) / self.sigma
        h = torch.tanh(self.fc3(F.silu(self.fc2(F.silu(self.fc1(z))))))
        phi = torch.cat((h, torch.ones_like(h[:, :1])), dim=1)
        phi = phi / torch.sqrt(1.0 + (h * h).sum(dim=1, keepdim=True))
        return self.head(phi)


def seed_everything() -> None:
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    torch.cuda.manual_seed_all(SEED)
    torch.use_deterministic_algorithms(True)


def load_pool() -> tuple[np.ndarray, np.ndarray, list[dict]]:
    frozen = pd.read_csv(OUT / "manifests/MICRO_POOL.csv", keep_default_na=False)
    if len(frozen) != 12 or set(frozen.wind_cell.astype(int)) != {4, 8}:
        raise AssertionError("Frozen micro pool must contain the taskbook's 12 W04/W08 episodes")
    eps = {e.run_id: e for e in load_episodes("train", ("B", "POS_OFF"))}
    xs, ys, rows = [], [], []
    for r in frozen.itertuples(index=False):
        ep = eps[str(r.run_id)]
        ids = np.arange(31, len(ep.ready), 5, dtype=np.int64)
        if len(ids) != 394 or not ep.ready[ids].all():
            raise AssertionError(f"Unexpected micro endpoints for {ep.run_id}")
        windows = np.lib.stride_tricks.sliding_window_view(ep.x14, window_shape=32, axis=0)
        xs.append(windows[ids - 31])
        ys.append(ep.y[ids])
        rows.append({"run_id": ep.run_id, "scene_id": ep.scene_id, "role": ep.role,
                     "task": ep.task, "endpoint_count": len(ids)})
    x, y = np.concatenate(xs).astype(np.float32), np.concatenate(ys).astype(np.float32)
    if x.shape != (4728, 14, 32) or y.shape != (4728, 3):
        raise AssertionError(f"Unexpected fixed micro dataset shapes: {x.shape}, {y.shape}")
    return x, y, rows


def build_order(n: int) -> np.ndarray:
    rng = np.random.default_rng(SEED + 1)
    out = np.empty(STEPS * BATCH, dtype=np.int32)
    pos = 0
    perm = rng.permutation(n)
    cursor = 0
    while pos < len(out):
        take = min(len(out) - pos, n - cursor)
        out[pos:pos + take] = perm[cursor:cursor + take]
        pos += take
        cursor += take
        if cursor == n:
            perm = rng.permutation(n)
            cursor = 0
    return out


def rel_l2(after: list[torch.Tensor], before: list[torch.Tensor]) -> float:
    num = sum(float(((a.detach() - b) ** 2).sum().item()) for a, b in zip(after, before))
    den = sum(float((b ** 2).sum().item()) for b in before)
    return float(np.sqrt(num) / max(np.sqrt(den), 1e-12))


def evaluate(model: nn.Module, x: torch.Tensor, y: torch.Tensor, device: torch.device,
             fit_id: str, step: int, last_grad_norms: list[float], start_params: list[torch.Tensor]) -> dict:
    model.eval()
    preds = []
    with torch.no_grad():
        for lo in range(0, len(x), 512):
            preds.append(model(x[lo:lo + 512].to(device)).cpu())
    pred = torch.cat(preds).numpy().astype(np.float64)
    target = y.numpy().astype(np.float64)
    err = pred - target
    target_rms = np.sqrt(np.mean(target**2, axis=0))
    pred_std = np.std(pred, axis=0)
    return {"fit_id": fit_id, "step": step,
            "train_rmse_mps2": float(np.sqrt(np.mean(err**2))),
            "train_rmse_x_mps2": float(np.sqrt(np.mean(err[:, 0]**2))),
            "train_rmse_y_mps2": float(np.sqrt(np.mean(err[:, 1]**2))),
            "train_rmse_z_mps2": float(np.sqrt(np.mean(err[:, 2]**2))),
            "bias_x_mps2": float(np.mean(err[:, 0])), "bias_y_mps2": float(np.mean(err[:, 1])),
            "bias_z_mps2": float(np.mean(err[:, 2])),
            "label_rms_x_mps2": float(target_rms[0]), "label_rms_y_mps2": float(target_rms[1]),
            "label_rms_z_mps2": float(target_rms[2]),
            "prediction_std_x_mps2": float(pred_std[0]), "prediction_std_y_mps2": float(pred_std[1]),
            "prediction_std_z_mps2": float(pred_std[2]),
            "prediction_to_label_std_ratio_min": float(np.min(pred_std / np.maximum(target_rms, 1e-12))),
            "constant_collapse": bool(np.min(pred_std / np.maximum(target_rms, 1e-12)) < .05),
            "mean_last_interval_grad_norm": float(np.mean(last_grad_norms)) if last_grad_norms else np.nan,
            "initial_parameter_relative_l2_change": rel_l2(list(model.parameters()), start_params)}


def state_update(active: str | None, completed: list[str], started: list[str], status: str) -> None:
    p = OUT / "state/state.json"
    state = json.loads(p.read_text(encoding="utf-8"))
    state.update({"phase": "D2_MICRO_FIT", "status": status,
                  "next": "STEP3_OFFICIAL_FITS" if len(completed) == 2 else "COMPLETE_MICRO_FITS",
                  "fits_started": len(started), "fits_completed": completed,
                  "active_fit": active, "active_run": None, "plant_started": 0,
                  "updated_at_utc": datetime.now(timezone.utc).isoformat()})
    p.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def ledger(fit_id: str, status: str, note: str) -> None:
    p = OUT / "RESOURCE_LEDGER.csv"
    with p.open("r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    hit = False
    for r in rows:
        if r["phase"] == "D2_MICRO" and r["resource_type"] == "fit" and r["identity"] == fit_id:
            r["status"] = status
            r["notes"] = note
            hit = True
    if not hit:
        rows.append({"timestamp_utc": datetime.now(timezone.utc).isoformat(), "phase": "D2_MICRO",
                     "resource_type": "fit", "identity": fit_id, "count": "1", "status": status,
                     "notes": note})
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=("timestamp_utc", "phase", "resource_type", "identity", "count", "status", "notes"))
        w.writeheader(); w.writerows(rows)


def update_running_state(active_fit: str) -> None:
    fit_families = {"MICRO_KAN_SEED2026101909": "KAN", "MICRO_MLP_SEED2026101909": "MLP"}
    completed = []
    for fit_id, family in fit_families.items():
        p = OUT / "models" / f"MICRO_{family}" / "seed2026101909/fit_report.json"
        if p.is_file() and json.loads(p.read_text(encoding="utf-8")).get("status") == "COMPLETE":
            completed.append(fit_id)
    with (OUT / "RESOURCE_LEDGER.csv").open("r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    started = [r["identity"] for r in rows if r["phase"] == "D2_MICRO" and r["resource_type"] == "fit"]
    state_update(active_fit, completed, started, "IN_PROGRESS")


def fit_one(fit_id: str, family: str, x_cpu: torch.Tensor, y_cpu: torch.Tensor,
            order: np.ndarray, mu: np.ndarray, sigma: np.ndarray, device: torch.device) -> list[dict]:
    folder = OUT / "models" / f"MICRO_{family}" / f"seed{SEED}"
    folder.mkdir(parents=True, exist_ok=True)
    report_path = folder / "fit_report.json"
    if report_path.is_file():
        old = json.loads(report_path.read_text(encoding="utf-8"))
        if old.get("status") == "COMPLETE" and old.get("optimizer_steps") == STEPS:
            print(f"SKIP_COMPLETE {fit_id}", flush=True)
            return old["history"]
    seed_everything()
    model = PositionModel(mu, sigma) if family == "KAN" else WideCurrentMLP(mu, sigma)
    model.to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
    start_params = [p.detach().clone() for p in model.parameters()]
    ckpt_path = folder / "latest_checkpoint.pt"
    history = []
    step0 = 0
    elapsed_before = 0.0
    if ckpt_path.is_file():
        ck = torch.load(ckpt_path, map_location=device, weights_only=False)
        model.load_state_dict(ck["model"])
        optimizer.load_state_dict(ck["optimizer"])
        step0 = int(ck["step"])
        history = ck["history"]
        elapsed_before = float(ck.get("elapsed_seconds", 0.0))
    ledger(fit_id, "RUNNING", "Random-init diagnostic only; 6000 steps; no VAL/DEV/Plant.")
    update_running_state(fit_id)
    x, y = x_cpu.to(device), y_cpu.to(device)
    last_grad: list[float] = []
    if step0 == 0:
        history.append(evaluate(model, x_cpu, y_cpu, device, fit_id, 0, [], start_params))
        print(f"{fit_id} step=0/{STEPS} rmse={history[-1]['train_rmse_mps2']:.6f}", flush=True)
    tic = time.perf_counter()
    for step in range(step0 + 1, STEPS + 1):
        lo = (step - 1) * BATCH
        ids = torch.as_tensor(order[lo:lo + BATCH].astype(np.int64), dtype=torch.long, device=device)
        pred = model(x.index_select(0, ids))
        loss = F.smooth_l1_loss(pred / 3.0, y.index_select(0, ids) / 3.0, reduction="mean")
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        grad_sq = sum(float((p.grad.detach() ** 2).sum().item()) for p in model.parameters() if p.grad is not None)
        last_grad.append(float(np.sqrt(grad_sq)))
        optimizer.step()
        if step in EVAL_STEPS[1:]:
            row = evaluate(model, x_cpu, y_cpu, device, fit_id, step, last_grad[-1000:], start_params)
            elapsed_before += time.perf_counter() - tic
            row["wall_seconds_cumulative"] = elapsed_before
            history.append(row)
            model.eval()
            torch.save({"step": step, "model": model.state_dict(), "optimizer": optimizer.state_dict(),
                        "history": history, "elapsed_seconds": elapsed_before}, ckpt_path)
            tic = time.perf_counter()
            pd.DataFrame(history).to_csv(OUT / "reports/MICRO_FIT_CHECK.csv", index=False)
            print(f"{fit_id} step={step}/{STEPS} rmse={row['train_rmse_mps2']:.6f} "
                  f"grad={row['mean_last_interval_grad_norm']:.4g} "
                  f"pred_std_ratio={row['prediction_to_label_std_ratio_min']:.3f}", flush=True)
    model_path = folder / "step6000.pt"
    torch.save({"state_dict": model.cpu().state_dict(), "family": family, "seed": SEED,
                "diagnostic_only": True}, model_path)
    report = {"fit_id": fit_id, "family": family, "seed": SEED, "status": "COMPLETE",
              "input": "real 32-event X14 windows supplied; both micro families consume the current frame only",
              "training_episodes": 12, "training_endpoints": len(x_cpu),
              "optimizer_steps": STEPS, "optimizer": {"name": "Adam", "lr": 1e-3,
              "weight_decay": 1e-5, "batch_size": BATCH},
              "parameter_count": sum(p.numel() for p in model.parameters()),
              "normalizer": "frozen DL1018 Initial TRAIN-only X14 normalizer",
              "model_path": str(model_path.relative_to(ROOT)).replace("\\", "/"),
              "history": history, "diagnostic_only": True, "no_val_dev_plant": True}
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    ledger(fit_id, "COMPLETED", f"6000 updates, {len(x_cpu)} fixed TRAIN endpoints; DIAGNOSTIC_ONLY.")
    return history


def main() -> None:
    x, y, pool_rows = load_pool()
    (OUT / "manifests/MICRO_POOL.csv").is_file()
    pd.DataFrame(pool_rows).to_csv(OUT / "derived/MICRO_POOL_ENDPOINTS.csv", index=False)
    norm = np.load(ROOT / "models/position/initial/normalizer.npz")
    mu, sigma = np.asarray(norm["mu"], dtype=np.float32), np.maximum(np.asarray(norm["sigma"], dtype=np.float32), 1e-4)
    np.savez(OUT / "derived/MICRO_SHARED_NORMALIZER.npz", mu=mu, sigma=sigma,
             source=np.asarray("DL1018 Initial TRAIN-only X14 normalizer"))
    x_cpu, y_cpu = torch.from_numpy(x), torch.from_numpy(y)
    order = build_order(len(x))
    np.save(OUT / "derived/MICRO_SHARED_BATCH_ORDER.npy", order)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    fit_one("MICRO_KAN_SEED2026101909", "KAN", x_cpu, y_cpu, order, mu, sigma, device)
    fit_one("MICRO_MLP_SEED2026101909", "MLP", x_cpu, y_cpu, order, mu, sigma, device)
    reports = []
    for family in ("KAN", "MLP"):
        q = json.loads((OUT / "models" / f"MICRO_{family}" / f"seed{SEED}" / "fit_report.json").read_text(encoding="utf-8"))
        reports.extend(q["history"])
    pd.DataFrame(reports).to_csv(OUT / "reports/MICRO_FIT_CHECK.csv", index=False)
    kan = json.loads((OUT / "models/MICRO_KAN" / f"seed{SEED}" / "fit_report.json").read_text(encoding="utf-8"))
    mlp = json.loads((OUT / "models/MICRO_MLP" / f"seed{SEED}" / "fit_report.json").read_text(encoding="utf-8"))
    final_kan, final_mlp = kan["history"][-1], mlp["history"][-1]
    interpret = ("宽MLP明显更好" if final_mlp["train_rmse_mps2"] < .8 * final_kan["train_rmse_mps2"] else
                 "两者均达到较低训练误差" if max(final_kan["train_rmse_mps2"], final_mlp["train_rmse_mps2"]) < .15 else
                 "两者均未充分拟合该微型池")
    text = f"""# 微型可拟合性探针

固定池：HELIX / FIG8_3D / SQUARE，C00，W04/W08，B/POS_OFF，共12条 TRAIN episode、4,728个stride-5终点。随机种子{SEED}，两模型使用相同预生成窗口顺序、相同 TRAIN-only Initial normalizer、Adam 1e-3、weight decay 1e-5、batch256、6,000步。没有读取VAL/DEV，模型均标为DIAGNOSTIC_ONLY，不进入Plant。

KAN参数量{kan['parameter_count']:,}；MLP参数量{mlp['parameter_count']:,}。6000步训练物理RMSE：KAN {final_kan['train_rmse_mps2']:.6f} m/s²，MLP {final_mlp['train_rmse_mps2']:.6f} m/s²。结论：**{interpret}**。参数漂移、梯度范数、逐轴偏置、标签RMS及预测标准差/塌缩标记见`MICRO_FIT_CHECK.csv`。

本探针只回答已见小池上的优化与拟合能力。它不是外推成绩、等参数容量对照或闭环证据，也不用于修改标签/删除样本。
"""
    (OUT / "reports/MICRO_FIT_INTERPRETATION.md").write_text(text, encoding="utf-8")
    state_update(None, ["MICRO_KAN_SEED2026101909", "MICRO_MLP_SEED2026101909"],
                 ["MICRO_KAN_SEED2026101909", "MICRO_MLP_SEED2026101909"], "COMPLETE")
    print(f"MICRO_COMPLETE device={device} KAN={final_kan['train_rmse_mps2']:.6f} "
          f"MLP={final_mlp['train_rmse_mps2']:.6f} interpretation={interpret}", flush=True)


if __name__ == "__main__":
    main()
