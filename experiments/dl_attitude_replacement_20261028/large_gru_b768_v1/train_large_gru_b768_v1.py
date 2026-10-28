#!/usr/bin/env python3
"""TRAIN-only GRU13->32->3 teacher fit for the B-only 768/48 cohort."""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
import numpy as np
import torch
from scipy.io import savemat
from torch.nn import functional as F

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "experiments/dl_attitude_replacement_20261028/large_attitude_b768_root_v1/DATASET.npz"
TASK = Path(__file__).resolve().parent
OUT = TASK / "runs/GRU13_B768_COSINE_S2026102001"
SCREEN = ROOT / "experiments/dl_attitude_replacement_20261026/architecture_screen_v1"
SEED, STEPS, BATCH, TBPTT = 2026102001, 60000, 4, 128
EVENTS, D_IN, HIDDEN, D_OUT = 1999, 13, 32, 3
LR_START, LR_END = 1e-3, 1e-5
TASKS = ("FIG8_3D", "HELIX", "SQUARE")


def model_class():
    sys.path.insert(0, str(SCREEN))
    from screen_attitude_architectures_v1 import GRU15
    return GRU15


def stream(model, x, hidden=None):
    seq, hidden = model.gru(x, hidden)
    return model.head(seq), hidden


def lr(step):
    if not 1 <= step <= STEPS:
        raise ValueError("step must be 1..60000")
    return LR_END + (LR_START - LR_END) * (1 + math.cos(math.pi * (step - 1) / (STEPS - 1))) / 2


def fit_normalizer(x, y):
    """Fit exclusively from supplied TRAIN arrays; target is RMS-scaled, not centered."""
    mean = x.mean(axis=(0, 1), dtype=np.float64)
    std = x.std(axis=(0, 1), dtype=np.float64)
    rms = np.sqrt(np.mean(np.square(y, dtype=np.float64), axis=(0, 1)))
    std[std < 1e-8] = 1.0
    rms[rms < 1e-8] = 1.0
    return mean.astype(np.float32), std.astype(np.float32), rms.astype(np.float32)


def load_data(path):
    if "TEST" in str(path).upper():
        raise ValueError("dataset path may not reference TEST")
    with np.load(path, allow_pickle=False) as z:
        required = ("train_x", "train_y", "val_x", "val_y", "train_ids", "val_ids",
                    "train_scene_ids", "val_scene_ids", "train_role_ids", "val_role_ids",
                    "train_task_ids", "val_task_ids")
        if set(z.files) != set(required):
            raise ValueError(f"unexpected NPZ schema: {z.files}")
        d = {k: np.asarray(z[k]) for k in required}
    for split, n in (("train", 768), ("val", 48)):
        x, y = d[f"{split}_x"], d[f"{split}_y"]
        if x.shape != (n, EVENTS, D_IN) or y.shape != (n, EVENTS, D_OUT):
            raise ValueError(f"{split} array shape mismatch: {x.shape}, {y.shape}")
        if x.dtype != np.float32 or y.dtype != np.float32 or not np.isfinite(x).all() or not np.isfinite(y).all():
            raise ValueError(f"{split} arrays must be finite float32")
        for suffix in ("ids", "scene_ids", "role_ids", "task_ids"):
            if d[f"{split}_{suffix}"].shape != (n,):
                raise ValueError(f"bad {split}_{suffix} metadata shape")
    if len(set(d["train_ids"].tolist())) != 768 or len(set(d["val_ids"].tolist())) != 48:
        raise ValueError("episode IDs must be unique within each split")
    train_scenes, val_scenes = set(d["train_scene_ids"].tolist()), set(d["val_scene_ids"].tolist())
    if len(train_scenes) != 768 or len(val_scenes) != 48 or train_scenes & val_scenes:
        raise ValueError("physical source scenes must be unique and TRAIN/VAL disjoint")
    for split, n_per_task in (("train", 256), ("val", 16)):
        if set(d[f"{split}_role_ids"].tolist()) != {"B"}:
            raise ValueError(f"{split} must satisfy the explicit B-only contract")
        counts = {t: int(np.count_nonzero(d[f"{split}_task_ids"] == t)) for t in TASKS}
        if counts != {t: n_per_task for t in TASKS}:
            raise ValueError(f"unexpected {split} task distribution: {counts}")
    if set(d["train_ids"].tolist()) & set(d["val_ids"].tolist()):
        raise ValueError("episode IDs overlap between TRAIN and VAL")
    return d


def determinism():
    random.seed(SEED); np.random.seed(SEED); torch.manual_seed(SEED)
    torch.use_deterministic_algorithms(True)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(SEED)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False


def validate_model(model):
    expected = {"gru.weight_ih_l0": (96, 13), "gru.weight_hh_l0": (96, 32),
                "gru.bias_ih_l0": (96,), "gru.bias_hh_l0": (96,),
                "head.weight": (3, 32), "head.bias": (3,)}
    got = model.state_dict()
    if set(got) != set(expected) or any(tuple(got[k].shape) != v for k, v in expected.items()):
        raise ValueError("model is not the frozen GRU13->32->3 layout")


def self_check():
    determinism(); model = model_class()().cpu().eval(); validate_model(model)
    x = torch.randn(2, 257, D_IN)
    with torch.no_grad():
        full, _ = stream(model, x)
        h = None; pieces = []
        for start in (0, 128, 256):
            y, h = stream(model, x[:, start:min(start + TBPTT, 257)], h)
            pieces.append(y)
        chunked = torch.cat(pieces, dim=1)
    if not torch.allclose(full, chunked, atol=2e-6, rtol=2e-5):
        raise AssertionError("stream/chunk output mismatch")
    if lr(1) != LR_START or lr(STEPS) != LR_END or not lr(30000) > lr(40000):
        raise AssertionError("cosine schedule check failed")
    a = np.arange(2 * 3 * 13, dtype=np.float32).reshape(2, 3, 13)
    b = np.ones((2, 3, 3), dtype=np.float32)
    mean, std, rms = fit_normalizer(a, b)
    if not np.allclose(mean, a.mean((0, 1))) or not np.allclose(rms, 1):
        raise AssertionError("TRAIN-only normalizer check failed")
    if OUT.exists():
        raise AssertionError("self-check must not create or inspect the training output")
    print("SELF_CHECK=PASS; GRU13/32/3; streaming chunks 128/128/1; cosine endpoints; TRAIN-only normalizer; no optimizer step")


def val_diagnostic(model, d, mean, std, rms, device):
    model.eval(); total = np.zeros(3, dtype=np.float64); count = 0
    xv, yv = d["val_x"], d["val_y"]
    xn = torch.as_tensor(((xv - mean) / std).astype(np.float32), device=device)
    with torch.inference_mode():
        for first in range(0, len(xv), BATCH):
            ids = slice(first, first + BATCH); h = None
            for start in range(0, EVENTS, TBPTT):
                end = min(start + TBPTT, EVENTS)
                out, h = stream(model, xn[ids, start:end], h)
                err = out.cpu().numpy().astype(np.float64) * rms - yv[ids, start:end]
                total += np.square(err).sum(axis=(0, 1)); count += err.shape[0] * err.shape[1]
                h = h.detach()
    return {"val_rmse_raw_rad_s2_by_axis": np.sqrt(total / count).tolist(), "val_events": count}


def train(data_path, output, device_name):
    d = load_data(data_path)
    if output.exists(): raise FileExistsError(f"refusing to overwrite {output}")
    if device_name.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError("CUDA requested but unavailable")
    device = torch.device(device_name); determinism()
    mean, std, rms = fit_normalizer(d["train_x"], d["train_y"])
    model = model_class()().to(device); validate_model(model)
    opt = torch.optim.Adam(model.parameters(), lr=LR_START, weight_decay=1e-5)
    x = torch.as_tensor(((d["train_x"] - mean) / std).astype(np.float32), device=device)
    y = torch.as_tensor((d["train_y"] / rms).astype(np.float32), device=device)
    output.mkdir(parents=True)
    np.savez_compressed(output / "train_only_normalizer.npz", input_mean=mean, input_std=std, target_rms=rms)
    config = {"status": "RUNNING", "cohort_contract": "B-only; TRAIN768/VAL48; all 768 independent TRAIN scenes",
              "architecture": "GRU(13,32,batch_first=True)+Linear(32,3)", "seed": SEED, "steps": STEPS,
              "batch_scenes": BATCH, "tbptt_events": TBPTT, "optimizer": "Adam", "weight_decay": 1e-5,
              "loss": "SmoothL1(beta=1)", "lr": "cosine 1e-3 to 1e-5 per optimizer update",
              "normalizer_fit_split": "TRAIN only", "validation_use": "final diagnostic only; no fit or selection",
              "train_episodes": 768, "train_events": 768 * EVENTS, "val_episodes": 48,
              "train_role_counts": {"B": 768}, "train_task_counts": {t: 256 for t in TASKS},
              "val_role_counts": {"B": 48}, "val_task_counts": {t: 16 for t in TASKS},
              "dataset": str(data_path.resolve()), "dataset_sha256": __import__("hashlib").sha256(data_path.read_bytes()).hexdigest(),
              "created_utc": datetime.now(timezone.utc).isoformat(), "device": str(device)}
    (output / "training_config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    history = (output / "training_history.jsonl").open("w", encoding="utf-8", buffering=1)
    rng = np.random.default_rng(SEED); step = seen = 0; losses = 0.; start_time = time.time()
    progress = {"status": "RUNNING", "completed_steps": 0, "target_steps": STEPS}
    (output / "training_progress.json").write_text(json.dumps(progress, indent=2) + "\n")
    try:
        epoch = 0
        while step < STEPS:
            epoch += 1; order = rng.permutation(len(x))
            for first in range(0, len(order), BATCH):
                cohort = order[first:first + BATCH]
                if len(cohort) != BATCH: raise AssertionError("TRAIN count must divide into batches of four")
                idx = torch.as_tensor(cohort.copy(), device=device); hidden = None
                for offset in range(0, EVENTS, TBPTT):
                    if step == STEPS: break
                    end = min(offset + TBPTT, EVENTS); opt.zero_grad(set_to_none=True)
                    pred, next_hidden = stream(model, x[idx, offset:end], hidden)
                    loss = F.smooth_l1_loss(pred, y[idx, offset:end], beta=1.)
                    if not torch.isfinite(loss): raise FloatingPointError(f"nonfinite loss at step {step + 1}")
                    rate = lr(step + 1)
                    for group in opt.param_groups: group["lr"] = rate
                    loss.backward(); opt.step(); hidden = next_hidden.detach()
                    step += 1; n = BATCH * (end - offset); seen += n; losses += float(loss.item())
                    row = {"step": step, "epoch": epoch, "lr": rate, "loss": float(loss.item()),
                           "cohort_ids": d["train_ids"][cohort].tolist(), "chunk_start": offset,
                           "chunk_end_exclusive": end, "valid_samples": n, "cumulative_valid_samples": seen}
                    history.write(json.dumps(row) + "\n")
                    if step % 1000 == 0 or step == STEPS:
                        progress = {"status": "RUNNING", "completed_steps": step, "target_steps": STEPS,
                                    "latest_loss": float(loss.item()), "mean_loss_last_1000": losses / min(step % 1000 or 1000, 1000),
                                    "cumulative_valid_samples": seen, "elapsed_seconds": time.time() - start_time}
                        (output / "training_progress.json").write_text(json.dumps(progress, indent=2) + "\n")
                        print(json.dumps(progress), flush=True); losses = 0.
                if step == STEPS: break
    except Exception as e:
        progress = {"status": "FAILED", "completed_steps": step, "error": f"{type(e).__name__}: {e}"}
        (output / "training_progress.json").write_text(json.dumps(progress, indent=2) + "\n")
        raise
    finally: history.close()
    model.eval(); state = model.state_dict()
    ckpt = {**config, "status": "PASS", "step": STEPS, "state_dict": state,
            "input_mean": torch.tensor(mean), "input_std": torch.tensor(std), "target_rms": torch.tensor(rms)}
    torch.save(ckpt, output / "final_step_60000.pt")
    savemat(output / "gru_stream_large_b768_weights_v1.mat", {
        "input_mean": mean.reshape(1, -1), "input_std": std.reshape(1, -1), "target_rms": rms.reshape(1, -1),
        "gru_weight_ih": state["gru.weight_ih_l0"].cpu().numpy().astype(np.float64),
        "gru_weight_hh": state["gru.weight_hh_l0"].cpu().numpy().astype(np.float64),
        "gru_bias_ih": state["gru.bias_ih_l0"].cpu().numpy().astype(np.float64),
        "gru_bias_hh": state["gru.bias_hh_l0"].cpu().numpy().astype(np.float64),
        "head_weight": state["head.weight"].cpu().numpy().astype(np.float64),
        "head_bias": state["head.bias"].cpu().numpy().astype(np.float64)}, do_compression=True, oned_as="row")
    diagnostic = val_diagnostic(model, d, mean, std, rms, device)
    (output / "VAL_DIAGNOSTIC.json").write_text(json.dumps(diagnostic, indent=2) + "\n", encoding="utf-8")
    config["status"] = "PASS"; config["final_validation_diagnostic"] = diagnostic
    (output / "training_config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    progress = {"status": "PASS", "completed_steps": STEPS, "target_steps": STEPS, "cumulative_valid_samples": seen}
    (output / "training_progress.json").write_text(json.dumps(progress, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-check", action="store_true")
    ap.add_argument("--train", action="store_true")
    ap.add_argument("--data", type=Path, default=DATA)
    ap.add_argument("--output", type=Path, default=OUT)
    ap.add_argument("--device", default="cuda:0")
    args = ap.parse_args()
    if args.self_check == args.train: ap.error("choose exactly one of --self-check or --train")
    self_check() if args.self_check else train(args.data, args.output, args.device)
