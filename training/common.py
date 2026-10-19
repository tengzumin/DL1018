"""Shared deterministic fitting and scoring for the two prescribed KAN fits."""
from __future__ import annotations

import csv
import json
import random
import shutil
from pathlib import Path

import numpy as np
import torch
from torch.nn import functional as F

if __package__:
    from .data import EventSet, weight_report
    from .models import KANModel
else:
    from data import EventSet, weight_report
    from models import KANModel


MAX_EPOCHS = 60
PATIENCE = 8
BATCH_SIZE = 256
D_A = np.asarray([45.0, 45.0, 4.7124], dtype=np.float64)


def _json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def seed_all(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


def _predictions(model: KANModel, data: EventSet, device: torch.device) -> np.ndarray:
    model.eval()
    outputs = []
    with torch.no_grad():
        for start in range(0, len(data.x), 2048):
            xb = torch.from_numpy(data.x[start:start + 2048]).to(device)
            outputs.append(model(xb).cpu().numpy())
    return np.concatenate(outputs, axis=0)


def score(model: KANModel, data: EventSet, modality: str, device: torch.device) -> tuple[float, dict]:
    pred = _predictions(model, data, device).astype(np.float64)
    if modality == "position":
        clipped = np.clip(pred, -3.0, 3.0)
        error = clipped - data.y.astype(np.float64)
        value = float(np.sqrt(np.sum(data.weights * np.mean(error * error, axis=1))))
        def axis_scores(group: np.ndarray) -> dict[str, float]:
            out = {}
            for axis, name in enumerate(("x", "y", "z")):
                denom = data.weights[group].sum()
                out[name] = float(np.sqrt(np.sum(data.weights[group] * error[group, axis] ** 2) / denom))
            return out
        details = {}
        for role in np.unique(data.role):
            for task in np.unique(data.task):
                mask = (data.role == role) & (data.task == task)
                if np.any(mask):
                    details[f"{role}/{task}"] = float(np.sqrt(
                        np.sum(data.weights[mask] * np.mean(error[mask] ** 2, axis=1))
                        / data.weights[mask].sum()))
        by_task = {}
        for task in np.unique(data.task):
            mask = data.task == task
            by_task[str(task)] = float(np.sqrt(np.sum(data.weights[mask] * np.mean(error[mask] ** 2, axis=1))
                                               / data.weights[mask].sum()))
        by_wind = {}
        for wind in np.unique(data.wind_cell):
            mask = data.wind_cell == wind
            by_wind[str(int(wind))] = float(np.sqrt(np.sum(data.weights[mask] * np.mean(error[mask] ** 2, axis=1))
                                                     / data.weights[mask].sum()))
        by_phase = {}
        for phase in np.unique(data.phase):
            mask = data.phase == phase
            by_phase[str(int(phase))] = float(np.sqrt(np.sum(data.weights[mask] * np.mean(error[mask] ** 2, axis=1))
                                                      / data.weights[mask].sum()))
        return value, {"score_mps2": value, "by_source_task_mps2": details,
                       "by_task_mps2": by_task, "by_wind_mps2": by_wind,
                       "by_phase_mps2": by_phase, "by_axis_mps2": axis_scores(np.ones(len(error), dtype=bool)),
                       "prediction_raw_clip_fraction": float(np.mean(np.abs(pred) > 3.0)),
                       "target_raw_clip_fraction": float(np.mean(np.abs(data.raw) > 3.0))}

    pred_phys = np.clip(pred, -1.0, 1.0) * D_A
    target_phys = data.y.astype(np.float64) * D_A
    err2 = np.mean((pred_phys - target_phys) ** 2, axis=1)
    # First score each run × phase in physical units, then average those units
    # with their already-balanced source/task/configuration/scene/phase mass.
    total, phase_rows = 0.0, []
    for run in np.unique(data.run_id):
        run_mask = data.run_id == run
        for phase in np.unique(data.phase[run_mask]):
            mask = run_mask & (data.phase == phase)
            phase_score = float(np.sqrt(err2[mask].mean()))
            phase_weight = float(data.weights[mask].sum())
            total += phase_weight * phase_score
            phase_rows.append({"run_id": str(run), "phase": int(phase),
                               "rmse_rads2": phase_score, "weight": phase_weight})
    by_role = {}
    for role in np.unique(data.role):
        rows = [r for r in phase_rows if r["run_id"] in set(data.run_id[data.role == role])]
        denom = sum(r["weight"] for r in rows)
        by_role[str(role)] = float(sum(r["weight"] * r["rmse_rads2"] for r in rows) / denom)
    by_task, by_wind, by_phase = {}, {}, {}
    for task in np.unique(data.task):
        mask = data.task == task
        by_task[str(task)] = float(np.sqrt(np.sum(data.weights[mask] * err2[mask]) / data.weights[mask].sum()))
    for wind in np.unique(data.wind_cell):
        mask = data.wind_cell == wind
        by_wind[str(int(wind))] = float(np.sqrt(np.sum(data.weights[mask] * err2[mask]) / data.weights[mask].sum()))
    for phase in np.unique(data.phase):
        mask = data.phase == phase
        by_phase[str(int(phase))] = float(np.sqrt(np.sum(data.weights[mask] * err2[mask]) / data.weights[mask].sum()))
    by_axis = {}
    for axis, name in enumerate(("roll", "pitch", "yaw")):
        by_axis[name] = float(np.sqrt(np.sum(data.weights * (pred_phys[:, axis] - target_phys[:, axis]) ** 2)
                                      / data.weights.sum()))
    return float(total), {"score_rads2": float(total), "by_source_rads2": by_role,
                         "by_task_rads2": by_task, "by_wind_rads2": by_wind,
                         "by_phase_rads2": by_phase, "by_axis_rads2": by_axis,
                         "phase_count": len(phase_rows),
                         "prediction_raw_clip_fraction": float(np.mean(np.abs(pred) > 1.0)),
                         "target_raw_clip_fraction": float(np.mean(np.abs(data.raw) > D_A))}


def _state(model: KANModel) -> dict:
    return {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}


def _save_resume(path: Path, model, optimizer, *, seed, mode, modality, epoch, best, best_epoch,
                 best_state, stale, history, rng, fit_identity) -> None:
    state = {"seed": seed, "epoch": epoch, "model": _state(model),
             "mode": mode, "modality": modality,
             "optimizer": optimizer.state_dict(), "best": best,
             "best_epoch": best_epoch, "best_state": best_state,
             "stale": stale, "history": history,
             "fit_identity": fit_identity,
             "python_rng": random.getstate(), "numpy_rng": np.random.get_state(),
             "torch_rng": torch.get_rng_state(),
             "cuda_rng": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else None,
             "order_rng": rng.bit_generator.state}
    torch.save(state, path)


def fit(*, root: Path, modality: str, mode: str, seed: int,
        train: EventSet, val: EventSet, mu: np.ndarray, sigma: np.ndarray,
        initial_checkpoint: Path | None = None) -> dict:
    root = root.resolve()
    is_position = modality == "position"
    dim = 14 if is_position else 29
    package_name = f"{modality}_{'initial' if mode == 'initial' else 'final_candidate'}"
    out = root / "models" / modality / ("initial" if mode == "initial" else "final_candidate")
    out.mkdir(parents=True, exist_ok=True)
    report_path = root / "reports" / ("G03_P_INITIAL.json" if is_position and mode == "initial"
                                       else "G05_P_FINAL.json" if is_position
                                       else "G08_A_INITIAL.json" if mode == "initial"
                                       else "G10_A_FINAL.json")
    resume_path, best_path = out / "resume.pt", out / "best_model.pt"
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    seed_all(seed)
    model = KANModel(dim, mu, sigma, position_unclipped_silu=is_position)
    if mode == "final":
        if initial_checkpoint is None or not initial_checkpoint.is_file():
            raise FileNotFoundError("Final fit requires this run's Initial checkpoint")
        initial = torch.load(initial_checkpoint, map_location="cpu", weights_only=False)
        if initial.get("input_dim") != dim:
            raise ValueError("Initial checkpoint feature dimension mismatch")
        model.load_state_dict(initial["state_dict"])
    model.to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
    rng = np.random.default_rng(seed)
    fit_identity = {
        "fit_id": f"DL1018_{modality.upper()}_{mode.upper()}_{seed}",
        "contract_version": "DL1018_V311_R2E_PAPER_FINAL",
        "input_dim": dim, "architecture": "N_KAN" if is_position else "KAN_X29",
        "parameter_count": sum(p.numel() for p in model.parameters()),
        "train_episode_counts": {str(r): sum(e.role == r for e in train.episodes)
                                 for r in sorted(set(e.role for e in train.episodes))},
        "val_episode_counts": {str(r): sum(e.role == r for e in val.episodes)
                               for r in sorted(set(e.role for e in val.episodes))},
        "train_scene_ids_by_role": {str(r): sorted(e.scene_id for e in train.episodes if e.role == r)
                                    for r in sorted(set(e.role for e in train.episodes))},
        "val_scene_ids_by_role": {str(r): sorted(e.scene_id for e in val.episodes if e.role == r)
                                  for r in sorted(set(e.role for e in val.episodes))},
        "train_windows": len(train.weights), "val_windows": len(val.weights),
        "train_weight_summary": weight_report(train), "val_weight_summary": weight_report(val),
        "window_size": 32, "train_stride": 5,
        "validation_stride": 5 if is_position else 1,
        "optimizer": {"name": "Adam", "lr": 1e-3, "weight_decay": 1e-5,
                      "batch_size": BATCH_SIZE, "max_epochs": MAX_EPOCHS, "patience": PATIENCE},
        "normalizer_mu": np.asarray(mu, dtype=np.float64).tolist(),
        "normalizer_sigma": np.asarray(sigma, dtype=np.float64).tolist(),
    }
    history: list[dict] = []
    if is_position:
        zero_score = float(np.sqrt(np.sum(val.weights * np.mean(val.y.astype(np.float64) ** 2, axis=1))))
    else:
        zero_model = KANModel(dim, mu, sigma, position_unclipped_silu=False).to(device)
        with torch.no_grad():
            for parameter in zero_model.parameters():
                parameter.zero_()
        zero_score, _ = score(zero_model, val, modality, device)
        del zero_model
    score0, score0_detail = score(model, val, modality, device)
    best, best_epoch, stale = score0, 0, 0
    best_state = _state(model)
    start_epoch = 1
    if mode == "final":
        torch.save({"input_dim": dim, "state_dict": best_state, "epoch": 0,
                    "source": "same-run Initial checkpoint"}, out / "epoch0_initial_candidate.pt")
    if resume_path.is_file():
        state = torch.load(resume_path, map_location="cpu", weights_only=False)
        if state.get("seed") != seed or state.get("mode") != mode or state.get("modality") != modality \
                or state.get("fit_identity") != fit_identity:
            raise ValueError("Resume state does not match this fit")
        model.load_state_dict(state["model"])
        optimizer.load_state_dict(state["optimizer"])
        best, best_epoch, best_state = state["best"], state["best_epoch"], state["best_state"]
        stale, history, start_epoch = state["stale"], state["history"], int(state["epoch"]) + 1
        random.setstate(state["python_rng"]); np.random.set_state(state["numpy_rng"])
        torch.set_rng_state(state["torch_rng"])
        if torch.cuda.is_available() and state["cuda_rng"] is not None:
            torch.cuda.set_rng_state_all(state["cuda_rng"])
        rng.bit_generator.state = state["order_rng"]
    else:
        _save_resume(resume_path, model, optimizer, seed=seed, mode=mode, modality=modality, epoch=0, best=best,
                     best_epoch=0, best_state=best_state, stale=stale, history=history, rng=rng,
                     fit_identity=fit_identity)
    x = torch.from_numpy(train.x)
    y = torch.from_numpy(train.y)
    w = torch.from_numpy(train.weights.astype(np.float32))
    N = len(x)
    if stale >= PATIENCE:
        start_epoch = MAX_EPOCHS + 1
    for epoch in range(start_epoch, MAX_EPOCHS + 1):
        model.train()
        order = rng.permutation(N)
        train_weighted_sum = 0.0
        for start in range(0, N, BATCH_SIZE):
            ids = order[start:start + BATCH_SIZE]
            xb = x[ids].to(device); yb = y[ids].to(device); wb = w[ids].to(device)
            pred = model(xb)
            scale = 3.0 if is_position else 1.0
            per_sample = F.smooth_l1_loss(pred / scale, yb / scale, reduction="none").mean(dim=1)
            loss = (N / len(ids)) * torch.sum(wb * per_sample)
            optimizer.zero_grad(set_to_none=True); loss.backward(); optimizer.step()
            train_weighted_sum += float(torch.sum(wb * per_sample).detach().cpu())
        val_score, val_detail = score(model, val, modality, device)
        if not np.isfinite(val_score) or not np.isfinite(train_weighted_sum):
            raise FloatingPointError(f"Non-finite fit at epoch {epoch}")
        improved = val_score < best - 1e-10
        if improved:
            best, best_epoch, stale = val_score, epoch, 0
            best_state = _state(model)
            torch.save({"input_dim": dim, "state_dict": best_state, "epoch": epoch,
                        "seed": seed, "modality": modality,
                        "position_unclipped_silu": is_position}, best_path)
        else:
            stale += 1
        history.append({"epoch": epoch, "train_weighted_smooth_l1": train_weighted_sum,
                        "val_score": val_score, "val_detail": val_detail,
                        "train_weight_balance": weight_report(train),
                        "val_weight_balance": weight_report(val),
                        "improved": bool(improved), "stale_epochs": stale})
        _save_resume(resume_path, model, optimizer, seed=seed, mode=mode, modality=modality, epoch=epoch, best=best,
                     best_epoch=best_epoch, best_state=best_state, stale=stale, history=history, rng=rng,
                     fit_identity=fit_identity)
        print(f"[{package_name}] epoch={epoch:02d} score={val_score:.9g} best={best:.9g} stale={stale}", flush=True)
        if stale >= PATIENCE:
            break
    torch.save({"input_dim": dim, "state_dict": best_state, "epoch": best_epoch,
                "seed": seed, "modality": modality,
                "position_unclipped_silu": is_position}, best_path)
    model.load_state_dict(best_state)
    final_best, best_detail = score(model, val, modality, device)
    success = bool(final_best < zero_score - 1e-10) if mode == "initial" else True
    history_path = out / "training_history.csv"
    with history_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=("epoch", "train_weighted_smooth_l1", "val_score",
                                               "train_weight_balance", "val_weight_balance",
                                               "improved", "stale_epochs"))
        writer.writeheader()
        for row in history:
            writer.writerow({k: (json.dumps(row[k], ensure_ascii=False, separators=(",", ":"))
                                  if k.endswith("weight_balance") else row[k]) for k in writer.fieldnames})
    np.savez(out / "normalizer.npz", mu=np.asarray(mu, dtype=np.float64), sigma=np.asarray(sigma, dtype=np.float64))
    _json(out / "model.json", {"model_id": f"DL1018_{modality.upper()}_{mode.upper()}_SEED{seed}",
                               "input_dim": dim, "architecture": "X_KAN", "parameters": sum(p.numel() for p in model.parameters()),
                               "normalizer_source": "Teacher TRAIN only; population moments",
                               "seed": seed, "selected_epoch": best_epoch,
                               "score_units": "m/s^2" if is_position else "rad/s^2"})
    report = {"gate_id": report_path.stem, "status": "PASS_PENDING_PARITY" if success else "FAIL_TRAINING_SCORE",
              "contract_version": "DL1018_V311_R2E_PAPER_FINAL", "upstream_passed": True,
              "actual_counts": {"train_windows": len(train.weights), "val_windows": len(val.weights),
                                "epochs_complete": len(history), "plant_started": 0},
              "checks": {"input_dim": dim, "parameters": sum(p.numel() for p in model.parameters()),
                         "architecture": "N_KAN" if is_position else "KAN_X29",
                         "score_initial_or_best": final_best, "zero_prediction_score": zero_score,
                         "epoch0_score": score0, "best_epoch": best_epoch,
                         "score_detail": best_detail, "weight_balance_train": weight_report(train),
                         "weight_balance_val": weight_report(val),
                         "position_silu_unclipped": is_position,
                         "normalizer_reused": mode == "final"},
              "artifacts": [str(best_path.relative_to(root)).replace("\\", "/"),
                            str(history_path.relative_to(root)).replace("\\", "/"),
                            str((out / "normalizer.npz").relative_to(root)).replace("\\", "/")],
              "training_passed": success, "next_gate_allowed": False,
              "blocking_reason": "" if success else "Initial model did not beat zero prediction."}
    _json(report_path, report)
    return report


def lock_final_model(root: Path, modality: str, best_epoch: int,
                     initial_checkpoint: Path, score_on_mixed_val: float) -> None:
    """Copy the parity-checked candidate or its epoch0 Initial into Selected."""
    root = root.resolve()
    selected_dir = root / "models" / modality / "selected"
    selected_dir.mkdir(parents=True, exist_ok=True)
    candidate_dir = root / "models" / modality / "final_candidate"
    initial_dir = root / "models" / modality / "initial"
    source_path = candidate_dir / "best_model.pt" if best_epoch > 0 else initial_checkpoint
    normalizer_dir = candidate_dir if best_epoch > 0 else initial_dir
    shutil.copy2(source_path, selected_dir / "selected_model.pt")
    shutil.copy2(normalizer_dir / "normalizer.npz", selected_dir / "normalizer.npz")
    config_path = root / "configs" / "selected_models.json"
    config = json.loads(config_path.read_text(encoding="utf-8")) if config_path.is_file() else {
        "contract_version": "DL1018_V311_R2E_PAPER_FINAL"}
    config[f"{modality}_selected"] = {
        "selected_model_id": f"DL1018_{modality.upper()}_SELECTED",
        "selected_origin": "FINAL" if best_epoch > 0 else "INITIAL",
        "best_epoch": int(best_epoch), "student_changed_selected": bool(best_epoch > 0),
        "score_on_mixed_val": float(score_on_mixed_val)}
    _json(config_path, config)
