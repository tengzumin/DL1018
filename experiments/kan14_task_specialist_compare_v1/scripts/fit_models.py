from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import time
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
import torch
from torch.nn import functional as F

from teacher_data import EpisodeBank, normalizers
from teacher_models import DSSMFeature, GRUFeature, KANFeature, MLPFeature, TCNFeature

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "experiments" / "teacher_reuse_model_screen_v1"
SEEDS = (2026102001, 2026102002)
CONFIGS = (
    {"model_id": "MLP14", "family": "MLP", "input_dim": 14, "window": 32, "group": "CURRENT"},
    {"model_id": "KAN14", "family": "KAN", "input_dim": 14, "window": 32, "group": "CURRENT"},
    {"model_id": "TCN14", "family": "TCN", "input_dim": 14, "window": 32, "group": "TEMPORAL"},
    {"model_id": "GRU14", "family": "GRU", "input_dim": 14, "window": 32, "group": "TEMPORAL"},
    {"model_id": "DSSM14", "family": "DSSM", "input_dim": 14, "window": 32, "group": "TEMPORAL"},
    {"model_id": "MLP20", "family": "MLP", "input_dim": 20, "window": 32, "group": "CURRENT"},
    {"model_id": "TCN20", "family": "TCN", "input_dim": 20, "window": 32, "group": "TEMPORAL"},
    {"model_id": "TCN14_L128", "family": "TCN", "input_dim": 14, "window": 128, "group": "TEMPORAL"},
)
BATCH = 256
LR = 1e-3
WEIGHT_DECAY = 1e-5


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def seed_all(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


def make_model(config: dict, norms: dict):
    key = "X14" if config["input_dim"] == 14 else "X20"
    mu, sigma = norms[key]["mu"], norms[key]["sigma"]
    family = config["family"]
    if family == "MLP":
        return MLPFeature(config["input_dim"], mu, sigma)
    if family == "KAN":
        if config["input_dim"] != 14:
            raise ValueError("The pre-registered KAN supports X14 only")
        return KANFeature(mu, sigma)
    if family == "TCN":
        return TCNFeature(config["input_dim"], mu, sigma, config["window"])
    if family == "GRU":
        return GRUFeature(config["input_dim"], mu, sigma, config["window"])
    if family == "DSSM":
        return DSSMFeature(config["input_dim"], mu, sigma, config["window"])
    raise ValueError(f"Unknown family: {family}")


def model_input(model, batch: np.ndarray, device: torch.device) -> torch.Tensor:
    if not model.sequence:
        batch = batch[:, -1, :]
    return torch.from_numpy(np.ascontiguousarray(batch)).to(device, dtype=torch.float32)


def score_model(model, data, device: torch.device, batch_size: int = 256) -> tuple[float, dict]:
    model.eval()
    preds = np.empty_like(data.target, dtype=np.float32)
    with torch.no_grad():
        for start in range(0, len(data.weights), batch_size):
            ids = np.arange(start, min(start + batch_size, len(data.weights)), dtype=np.int64)
            xb = model_input(model, data.batch_numpy(ids, model.input_dim), device)
            preds[start:start + len(ids)] = model(xb).detach().cpu().numpy()
    clipped = np.clip(preds.astype(np.float64), -3.0, 3.0)
    err = clipped - data.target.astype(np.float64)
    axis_mse = err * err
    vector_mse = axis_mse.mean(axis=1)
    w = data.weights.astype(np.float64)
    value = float(np.sqrt(np.sum(w * vector_mse) / w.sum()))

    def group_rmse(values: np.ndarray, mask: np.ndarray) -> float:
        denom = float(w[mask].sum())
        return float(np.sqrt(np.sum(w[mask] * values[mask]) / denom)) if denom > 0 else float("nan")

    by_axis = {name: group_rmse(axis_mse[:, axis], np.ones(len(w), dtype=bool))
               for axis, name in enumerate(("x", "y", "z"))}
    details = {
        "weighted_clipped_rmse_mps2": value,
        "natural_time_weighted_rmse_mps2": float(np.sqrt(vector_mse.mean())),
        "by_axis_weighted_rmse_mps2": by_axis,
        "by_role_weighted_rmse_mps2": {r: group_rmse(vector_mse, data.role == r)
                                       for r in sorted(set(data.role.tolist()))},
        "by_task_weighted_rmse_mps2": {t: group_rmse(vector_mse, data.task == t)
                                       for t in sorted(set(data.task.tolist()))},
        "by_wind_weighted_rmse_mps2": {str(int(v)): group_rmse(vector_mse, data.wind == v)
                                        for v in sorted(set(data.wind.tolist()))},
        "by_phase_weighted_rmse_mps2": {str(int(v)): group_rmse(vector_mse, data.phase == v)
                                         for v in sorted(set(data.phase.tolist()))},
        "prediction_raw_clip_fraction": float(np.mean(np.abs(preds) > 3.0)),
        "target_raw_clip_fraction": float(np.mean(np.abs(data.raw_target) > 3.0)),
    }
    model.train()
    return value, details


def state_cpu(model) -> dict:
    return {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}


def append_ledger(phase: str, resource: str, identity: str, count: int, status: str, notes: str) -> None:
    path = OUT / "RESOURCE_LEDGER.csv"
    columns = ("timestamp_utc", "phase", "resource_type", "identity", "count", "status", "notes")
    if path.is_file():
        with path.open("r", newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    else:
        rows = []
    rows = [r for r in rows if not (r.get("phase") == phase and r.get("resource_type") == resource
                                    and r.get("identity") == identity)]
    rows.append({"timestamp_utc": utcnow(), "phase": phase, "resource_type": resource,
                 "identity": identity, "count": str(count), "status": status, "notes": notes})
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def upsert_csv(path: Path, row: dict, identity_key: str) -> None:
    old = []
    if path.is_file():
        with path.open("r", newline="", encoding="utf-8") as f:
            old = list(csv.DictReader(f))
    old = [r for r in old if r.get(identity_key) != str(row[identity_key])]
    fields = list(dict.fromkeys([*row.keys(), *(k for r in old for k in r.keys())]))
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(old)
        w.writerow(row)


def write_training_history(path: Path, history: list[dict]) -> None:
    fields = ("step", "teacher_val_weighted_rmse_mps2", "teacher_val_natural_time_rmse_mps2",
              "interval_steps_per_s", "interval_wall_s", "train_loss_smoothl1_normalized", "best_so_far", "kind")
    with (path / "training_history.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in history:
            w.writerow({k: json.dumps(row[k], ensure_ascii=False) if k == "best_so_far" and k in row
                        else row.get(k, "") for k in fields})


def record_fit_outputs(config: dict, report: dict, folder: Path, protocol_hash: str) -> None:
    fit_id = report["fit_id"]
    detail = report["selected_teacher_val_detail"]
    protocol = json.loads((OUT / "protocol.json").read_text(encoding="utf-8"))
    frozen_hashes = protocol["source_sha256"]
    report.setdefault("fit_runner_source_sha256",
                      frozen_hashes["experiments/teacher_reuse_model_screen_v1/scripts/fit_models.py"])
    report.setdefault("model_source_sha256",
                      frozen_hashes["experiments/teacher_reuse_model_screen_v1/scripts/teacher_models.py"])
    report.setdefault("data_source_sha256",
                      frozen_hashes["experiments/teacher_reuse_model_screen_v1/scripts/teacher_data.py"])
    json_write(folder / "fit_report.json", report)
    result_row = {
        "fit_id": fit_id, "stage": report["stage"], "model_id": config["model_id"],
        "family": config["family"], "group": config["group"], "input_dim": config["input_dim"],
        "window": config["window"], "seed": report["seed"], "status": report["status"],
        "selected_step": report["selected_step"], "last_step": report["last_step"],
        "train_samples": report["train_sample_count"], "val_samples": report["val_sample_count"],
        "parameters": report["parameter_count"],
        "weighted_val_rmse_mps2": report["selected_teacher_val_rmse_mps2"],
        "natural_time_val_rmse_mps2": detail["natural_time_weighted_rmse_mps2"],
        "final_val_rmse_mps2": report["final_step_teacher_val_rmse_mps2"],
        "steps_per_s_mean": report["steps_per_s_mean"],
        "positive_step_improved_vs_step0": report["positive_step_improved_vs_step0"],
        "protocol_sha256": protocol_hash,
        "fit_runner_source_sha256": report["fit_runner_source_sha256"],
        "model_source_sha256": report["model_source_sha256"],
        "data_source_sha256": report["data_source_sha256"],
        "fit_report_path": (folder / "fit_report.json").relative_to(ROOT).as_posix(),
        "best_checkpoint_path": (folder / "best_teacher_val.pt").relative_to(ROOT).as_posix(),
        "final_checkpoint_path": (folder / "final_step.pt").relative_to(ROOT).as_posix(),
    }
    upsert_csv(OUT / "reports/training_results.csv", result_row, "fit_id")
    append_ledger(report["stage"], "fit", fit_id, int(report["last_step"]), report["status"],
                  f"train windows={report['train_sample_count']} val windows={report['val_sample_count']}; "
                  f"best={report['selected_teacher_val_rmse_mps2']:.10g}")


def update_state(stage: str, fit_id: str, completed: list[str], active_step: int,
                 fit_status: str, fit_count: int) -> None:
    path = OUT / "state/state.json"
    state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    ledger = OUT / "RESOURCE_LEDGER.csv"
    completed_steps: dict[str, int] = {}
    plant_starts = 0
    if ledger.is_file():
        with ledger.open("r", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("resource_type") == "fit":
                    key = row.get("identity", "")
                    completed_steps[key] = max(completed_steps.get(key, 0), int(row.get("count", 0)))
                elif row.get("resource_type") in {"plant_start", "Plant"}:
                    plant_starts += int(row.get("count", 0))
    fit_ids = set(completed_steps)
    if fit_id:
        fit_ids.add(fit_id)
    committed_steps = sum(completed_steps.values())
    active_uncommitted = max(0, int(active_step) - completed_steps.get(fit_id, 0)) if fit_id else 0
    state.update({"task": "DL1018_TEACHER_REUSE_MODEL_SCREEN_V1", "phase": stage,
                  "status": "IN_PROGRESS", "active_fit": fit_id or None,
                  "active_fit_step": int(active_step), "active_fit_status": fit_status,
                  "fits_started": len(fit_ids), "fits_completed": completed,
                  "optimizer_steps_completed_total": committed_steps + active_uncommitted,
                  "plant_starts": plant_starts,
                  "updated_at_utc": utcnow()})
    json_write(path, state)


def fit_one(config: dict, seed: int, train_data, val_data, norms: dict, schedule: dict,
            protocol_hash: str, stage: str, stop_steps: int) -> dict:
    fit_id = f"{stage}_{config['model_id']}_SEED{seed}"
    folder = OUT / "models" / stage.lower() / config["model_id"] / f"seed{seed}"
    folder.mkdir(parents=True, exist_ok=True)
    latest_path = folder / "latest_checkpoint.pt"
    report_path = folder / "fit_report.json"
    if report_path.is_file():
        old = json.loads(report_path.read_text(encoding="utf-8"))
        if old.get("protocol_sha256") != protocol_hash:
            raise RuntimeError(f"Protocol hash changed for existing fit {fit_id}")
        if old.get("status") == "COMPLETE" or (stage == "OFFICIAL" and old.get("last_step", 0) >= stop_steps):
            if not latest_path.is_file():
                raise RuntimeError(f"Completed report has no resumable checkpoint for {fit_id}")
            completed_ck = torch.load(latest_path, map_location="cpu", weights_only=False)
            write_training_history(folder, completed_ck["history"])
            record_fit_outputs(config, old, folder, protocol_hash)
            return old

    seed_all(seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = make_model(config, norms).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)
    steps_per_eval = int(schedule["official_eval_interval"] if stage == "OFFICIAL"
                          else schedule["fast_eval_interval"])
    fit_started_wall = time.perf_counter()
    history: list[dict] = []
    best_val = float("inf")
    best_step = 0
    best_state = None
    step0_detail = None
    start_step = 0
    cursor = 0
    order = np.empty(0, dtype=np.int64)
    rng = np.random.default_rng(seed)
    elapsed_prior = 0.0

    if latest_path.is_file():
        ck = torch.load(latest_path, map_location=device, weights_only=False)
        if ck.get("fit_id") != fit_id or ck.get("protocol_sha256") != protocol_hash:
            raise RuntimeError(f"Checkpoint identity/protocol mismatch for {fit_id}")
        model.load_state_dict(ck["model_state"])
        optimizer.load_state_dict(ck["optimizer_state"])
        start_step = int(ck["step"])
        best_val, best_step, best_state = float(ck["best_val"]), int(ck["best_step"]), ck["best_state"]
        history, step0_detail = ck["history"], ck["step0_detail"]
        order, cursor = np.asarray(ck["order"], dtype=np.int64), int(ck["cursor"])
        rng.bit_generator.state = ck["numpy_rng"]
        torch.set_rng_state(ck["torch_rng_cpu"].cpu())
        if torch.cuda.is_available() and ck.get("torch_rng_cuda") is not None:
            torch.cuda.set_rng_state_all([state.cpu() for state in ck["torch_rng_cuda"]])
        elapsed_prior = float(ck.get("elapsed_seconds", 0.0))
    else:
        zero, step0_detail = score_model(model, val_data, device)
        history.append({"step": 0, "teacher_val_weighted_rmse_mps2": zero,
                        "teacher_val_natural_time_rmse_mps2": step0_detail["natural_time_weighted_rmse_mps2"],
                        "kind": "RANDOM_STEP0_DIAGNOSTIC_ONLY"})
        order = rng.permutation(len(train_data.weights))
        if zero == 0 or not np.isfinite(zero):
            raise RuntimeError(f"Non-finite random step0 score in {fit_id}")

    update_state(stage, fit_id, [], start_step, "RUNNING", 0)
    if best_state is None:
        best_state = None
    interval_start = time.perf_counter()
    interval_steps = 0
    train_n = len(train_data.weights)
    total_steps = int(stop_steps)
    eval_steps: list[int] = []
    step = start_step
    while step < total_steps:
        if cursor >= train_n:
            order = rng.permutation(train_n)
            cursor = 0
        end = min(cursor + BATCH, train_n)
        ids = order[cursor:end]
        cursor = end
        xb = model_input(model, train_data.batch_numpy(ids, model.input_dim), device)
        yb = torch.from_numpy(train_data.target[ids]).to(device, dtype=torch.float32)
        wb = torch.from_numpy(train_data.weights[ids]).to(device, dtype=torch.float32)
        pred = model(xb)
        per_sample = F.smooth_l1_loss(pred / 3.0, yb / 3.0, reduction="none").mean(dim=1)
        loss = (train_n / len(ids)) * torch.sum(wb * per_sample)
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
        step += 1
        interval_steps += 1
        do_eval = step % steps_per_eval == 0 or step == total_steps
        if not do_eval:
            continue
        if device.type == "cuda":
            torch.cuda.synchronize()
        elapsed = time.perf_counter() - interval_start
        sps = interval_steps / max(elapsed, 1e-9)
        val_score, val_detail = score_model(model, val_data, device)
        eval_steps.append(step)
        improved = val_score < best_val
        if improved:
            best_val, best_step = val_score, step
            best_state = state_cpu(model)
            torch.save({"fit_id": fit_id, "model_id": config["model_id"], "seed": seed,
                        "state_dict": best_state, "selected_step": best_step,
                        "teacher_val_score_mps2": best_val, "protocol_sha256": protocol_hash},
                       folder / "best_teacher_val.pt")
        history.append({"step": step, "teacher_val_weighted_rmse_mps2": val_score,
                        "teacher_val_natural_time_rmse_mps2": val_detail["natural_time_weighted_rmse_mps2"],
                        "teacher_val_detail": val_detail, "interval_steps_per_s": sps,
                        "interval_wall_s": elapsed, "train_loss_smoothl1_normalized": float(loss.detach().cpu()),
                        "best_so_far": bool(improved), "kind": "POSITIVE_STEP_EVALUATION"})
        interval_start = time.perf_counter()
        interval_steps = 0

        cumulative_elapsed = elapsed_prior + time.perf_counter() - fit_started_wall
        latest = {"fit_id": fit_id, "model_id": config["model_id"], "seed": seed,
                  "stage": stage, "protocol_sha256": protocol_hash, "step": step,
                  "model_state": state_cpu(model), "optimizer_state": optimizer.state_dict(),
                  "best_val": best_val, "best_step": best_step, "best_state": best_state,
                  "history": history, "step0_detail": step0_detail, "order": order,
                  "cursor": cursor, "numpy_rng": rng.bit_generator.state,
                  "torch_rng_cpu": torch.get_rng_state(),
                  "torch_rng_cuda": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else None,
                  "elapsed_seconds": cumulative_elapsed}
        torch.save(latest, latest_path)
        update_state(stage, fit_id, [], step, "RUNNING", 0)
        print(f"TEACHER_FIT_PROGRESS model={config['model_id']} seed={seed} step={step}/{total_steps} "
              f"sps={sps:.3f} val={val_score:.8g} best={best_val:.8g} best_step={best_step}", flush=True)

    if best_state is None or best_step <= 0:
        raise RuntimeError(f"No positive-step checkpoint available for {fit_id}")
    model.load_state_dict(best_state)
    best_score, best_detail = score_model(model, val_data, device)
    model.load_state_dict(state_cpu(model) if step == 0 else torch.load(latest_path, map_location=device,
                                                                      weights_only=False)["model_state"])
    final_score, final_detail = score_model(model, val_data, device)
    final_state = state_cpu(model)
    torch.save({"fit_id": fit_id, "model_id": config["model_id"], "seed": seed,
                "state_dict": final_state, "selected_step": step,
                "teacher_val_score_mps2": final_score, "protocol_sha256": protocol_hash},
               folder / "final_step.pt")
    final_best_positive = min((r["teacher_val_weighted_rmse_mps2"] for r in history
                               if r.get("kind") == "POSITIVE_STEP_EVALUATION"), default=float("inf"))
    step0_score = float(history[0]["teacher_val_weighted_rmse_mps2"])
    status = "COMPLETE" if stage == "FAST_SCREEN" else (
        "AT_40K_STAGE_GATE" if stop_steps == 40000 else "COMPLETE")
    report = {
        "status": status, "fit_id": fit_id, "stage": stage,
        "model_id": config["model_id"], "model_group": config["group"],
        "family": config["family"], "input_dim": config["input_dim"], "window": config["window"],
        "seed": seed, "initialization": "random; no DL1018 Initial/Final/HISTORY weights or optimizer loaded",
        "train_sample_count": len(train_data.weights), "val_sample_count": len(val_data.weights),
        "train_episode_count": len(train_data.bank.meta), "val_episode_count": len(val_data.bank.meta),
        "parameter_count": sum(p.numel() for p in model.parameters()),
        "optimizer": {"name": "Adam", "lr": LR, "weight_decay": WEIGHT_DECAY, "batch_size": BATCH},
        "loss": "mean_axis SmoothL1(pred/3,target_clip/3), one hierarchical sample weight; uniform shuffled endpoints; N/batch unbiased scaling",
        "step0_weighted_val_rmse_mps2": step0_score,
        "positive_step_improved_vs_step0": bool(final_best_positive < step0_score),
        "selected_step": best_step, "selected_teacher_val_rmse_mps2": best_score,
        "selected_teacher_val_detail": best_detail,
        "last_step": step, "final_step_teacher_val_rmse_mps2": final_score,
        "final_step_teacher_val_detail": final_detail,
        "steps_per_s_mean": float(sum(r.get("interval_steps_per_s", 0.0) for r in history
                                       if r.get("kind") == "POSITIVE_STEP_EVALUATION") /
                                   max(1, sum(r.get("kind") == "POSITIVE_STEP_EVALUATION" for r in history))),
        "eval_steps": [int(r["step"]) for r in history if r.get("kind") == "POSITIVE_STEP_EVALUATION"],
        "history_rows": len(history), "protocol_sha256": protocol_hash,
        "fit_runner_source_sha256": sha256_file(Path(__file__)),
        "model_source_sha256": sha256_file(OUT / "scripts/teacher_models.py"),
        "data_source_sha256": sha256_file(OUT / "scripts/teacher_data.py"),
        "normalizer_id": "TEACHER_TRAIN_INITIAL_X14_PLUS_TRAIN_X20_EXTRAS",
        "started_or_resumed_at_utc": utcnow(), "fit_elapsed_s_this_invocation": time.perf_counter() - fit_started_wall,
        "preflight_step_count": None,
    }
    json_write(report_path, report)
    write_training_history(folder, history)
    record_fit_outputs(config, report, folder, protocol_hash)
    print(f"TEACHER_FIT_COMPLETE model={config['model_id']} seed={seed} status={status} "
          f"step={step} best={best_score:.8g}@{best_step} final={final_score:.8g} "
          f"sps={report['steps_per_s_mean']:.3f}", flush=True)
    return report


def run_stage(stage: str, stop_steps: int | None = None) -> None:
    protocol_path = OUT / "protocol.json"
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    if protocol.get("status") != "FROZEN_BEFORE_FIRST_FIT":
        raise RuntimeError("Training protocol is not frozen")
    protocol_hash = sha256_file(protocol_path)
    norms = normalizers()
    print("Loading accepted teacher-only episode arrays...", flush=True)
    full_train = EpisodeBank("train")
    full_val = EpisodeBank("val")
    pool_df = pd.read_csv(OUT / "manifests/small_teacher_pool.csv", keep_default_na=False)
    small_train_bank = EpisodeBank("train", set(pool_df.run_id.astype(str)))
    if len(full_train.meta) != 1536 or len(full_val.meta) != 96 or len(small_train_bank.meta) != 192:
        raise RuntimeError("Teacher-only split counts changed before fitting")
    train_sets = {
        "small": small_train_bank.windows(32),
        "small128": small_train_bank.windows(128),
        "full32": full_train.windows(32),
        "full128": full_train.windows(128),
    }
    val_sets = {32: full_val.windows(32), 128: full_val.windows(128)}
    schedule = protocol["training"]
    step_limit = int(stop_steps or (schedule["fast_screen_steps"] if stage == "FAST_SCREEN"
                                    else schedule["official_step_gate_40k"]))
    completed = []
    fit_configs = CONFIGS
    total = len(fit_configs) * len(SEEDS)
    for i, cfg in enumerate(fit_configs):
        train_data = train_sets[("small128" if cfg["window"] == 128 else "small") if stage == "FAST_SCREEN"
                                else ("full128" if cfg["window"] == 128 else "full32")]
        val_data = val_sets[cfg["window"]]
        for seed in SEEDS:
            fit_id = f"{stage}_{cfg['model_id']}_SEED{seed}"
            existing = OUT / "models" / stage.lower() / cfg["model_id"] / f"seed{seed}" / "fit_report.json"
            if stage == "FAST_SCREEN" and existing.is_file():
                old = json.loads(existing.read_text(encoding="utf-8"))
                if old.get("status") == "COMPLETE" and old.get("protocol_sha256") == protocol_hash:
                    fit_one(cfg, seed, train_data, val_data, norms, schedule, protocol_hash, stage, step_limit)
                    completed.append(fit_id)
                    update_state(stage, "", completed, 0, "FIT_COMPLETE", len(completed))
                    continue
            print(f"TEACHER_FIT_START stage={stage} config={cfg['model_id']} seed={seed} "
                  f"progress={len(completed)+1}/{total} train={len(train_data.weights)} val={len(val_data.weights)} "
                  f"steps={step_limit}", flush=True)
            fit_one(cfg, seed, train_data, val_data, norms, schedule, protocol_hash, stage, step_limit)
            completed.append(fit_id)
            update_state(stage, "", completed, 0, "FIT_COMPLETE", len(completed))
    state = json.loads((OUT / "state/state.json").read_text(encoding="utf-8"))
    state.update({"phase": f"{stage}_FITS_COMPLETE", "status": "IN_PROGRESS",
                  "active_fit": None, "fits_completed": completed, "updated_at_utc": utcnow()})
    json_write(OUT / "state/state.json", state)
    print(f"TEACHER_STAGE_COMPLETE stage={stage} fits={len(completed)}/{total}", flush=True)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--stage", choices=("FAST_SCREEN", "OFFICIAL"), required=True)
    p.add_argument("--stop-steps", type=int)
    args = p.parse_args()
    run_stage(args.stage, args.stop_steps)


if __name__ == "__main__":
    main()
