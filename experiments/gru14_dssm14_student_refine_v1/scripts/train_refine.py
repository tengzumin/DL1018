from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch.nn import functional as F

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "experiments" / "gru14_dssm14_student_refine_v1"
SOURCE = ROOT / "experiments" / "teacher_reuse_model_screen_v1"
sys.path.insert(0, str(SOURCE / "scripts"))
import fit_models as fit  # noqa: E402
from teacher_data import normalizers  # noqa: E402
from student_data import build as build_data  # noqa: E402

SEEDS = (2026102011, 2026102012)
GROUPS = ("TEACHER_CONTINUE", "STUDENT_MIX20")
TOTAL_STEPS = 10000
EVAL_INTERVAL = 1000
BATCH = 256
LR = 1e-4
WEIGHT_DECAY = 1e-5


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    temp.replace(path)


def score_common(model, teacher_val, student_val, device) -> tuple[float, dict]:
    teacher_score, teacher_detail = fit.score_model(model, teacher_val, device)
    student_score, student_detail = fit.score_model(model, student_val, device)
    common = float(np.sqrt(0.8 * teacher_score**2 + 0.2 * student_score**2))
    return common, {"common_val_rmse_mps2": common,
                    "teacher_val_rmse_mps2": teacher_score,
                    "student_val_rmse_mps2": student_score,
                    "teacher_val_detail": teacher_detail,
                    "student_val_detail": student_detail}


def append_ledger(fit_id: str, status: str, steps: int, notes: str) -> None:
    path = OUT / "RESOURCE_LEDGER.csv"
    if not path.is_file():
        path.write_text("timestamp_utc,resource,identity,count,status,notes\n", encoding="utf-8")
    with path.open("a", encoding="utf-8", newline="") as f:
        f.write(f"{utcnow()},OptimizerStep,{fit_id},{steps},{status},{notes.replace(',', ';')}\n")


def write_history(path: Path, history: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        cols = ["step", "common_val_rmse_mps2", "teacher_val_rmse_mps2", "student_val_rmse_mps2",
                "steps_per_s", "elapsed_s", "loss_smoothl1_normalized", "selected_best"]
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        for row in history:
            writer.writerow({k: row.get(k, "") for k in cols})


def update_project_state(fit_id: str, model_id: str, group: str, seed: int, step: int,
                         status: str, fit_count: int) -> None:
    path = OUT / "state/state.json"
    state = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    state.update({"phase": "PAIRED_WARM_START_FITS", "status": status, "active_fit": fit_id,
                  "active_model": model_id, "active_group": group, "active_seed": seed,
                  "active_fit_step": step, "optimizer_steps_per_fit": TOTAL_STEPS,
                  "fits_completed": fit_count, "updated_at_utc": utcnow()})
    write_json(path, state)


def fit_one(model_id: str, group: str, seed: int, model_data: dict, norms: dict, completed_before: int) -> dict:
    fit_id = f"{group}_{model_id}_SEED{seed}"
    folder = OUT / "models" / model_id / group / f"seed{seed}"
    folder.mkdir(parents=True, exist_ok=True)
    latest_path = folder / "latest_checkpoint.pt"
    report_path = folder / "fit_report.json"
    original_path = SOURCE / "models" / "official" / model_id / f"seed{json.loads((OUT/'protocol.json').read_text())['checkpoints'][model_id]['original_seed']}" / "final_step.pt"
    original_hash = sha256(original_path)
    if report_path.is_file():
        old = json.loads(report_path.read_text(encoding="utf-8"))
        if old.get("status") == "COMPLETE" and old.get("last_step") == TOTAL_STEPS:
            print(f"FIT_ALREADY_COMPLETE {fit_id}", flush=True)
            return old
    cfg = next(c for c in fit.CONFIGS if c["model_id"] == model_id)
    fit.seed_all(seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = fit.make_model(cfg, norms).to(device)
    original = torch.load(original_path, map_location="cpu", weights_only=False)
    if original.get("model_id") != model_id or int(original.get("selected_step", -1)) != 60000:
        raise RuntimeError(f"Wrong warm-start identity for {fit_id}")
    model.load_state_dict(original["state_dict"], strict=True)
    optimizer = torch.optim.Adam(model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)
    train_data = model_data["train_teacher"] if group == "TEACHER_CONTINUE" else model_data["train_mix"]
    teacher_val, student_val = model_data["teacher_val"], model_data["student_val"]
    protocol_hash = sha256(OUT / "protocol.json")
    rng = np.random.default_rng(seed)
    history: list[dict] = []
    start_step = 0
    cursor = 0
    order = np.empty(0, dtype=np.int64)
    best_val = float("inf")
    best_step = 0
    best_state = None
    best_detail = None
    consumed = {r: 0 for r in sorted(set(train_data.role.tolist()))}
    student_nonzero_loss_samples = 0
    student_weighted_loss_sum = 0.0
    student_gradient_norm_probe = None
    elapsed_prior = 0.0
    if latest_path.is_file():
        ck = torch.load(latest_path, map_location=device, weights_only=False)
        if ck.get("fit_id") != fit_id or ck.get("protocol_sha256") != protocol_hash:
            raise RuntimeError(f"Checkpoint identity or protocol mismatch for {fit_id}")
        model.load_state_dict(ck["model_state"])
        optimizer.load_state_dict(ck["optimizer_state"])
        start_step, cursor = int(ck["step"]), int(ck["cursor"])
        order = np.asarray(ck["order"], dtype=np.int64)
        rng.bit_generator.state = ck["numpy_rng"]
        if ck.get("torch_rng_cpu") is not None:
            torch.set_rng_state(ck["torch_rng_cpu"].cpu())
        if torch.cuda.is_available() and ck.get("torch_rng_cuda") is not None:
            torch.cuda.set_rng_state_all([s.cpu() for s in ck["torch_rng_cuda"]])
        history = ck["history"]
        best_val, best_step, best_state = ck["best_val"], ck["best_step"], ck["best_state"]
        best_detail = ck.get("best_detail")
        consumed = ck["consumed"]
        student_nonzero_loss_samples = int(ck["student_nonzero_loss_samples"])
        student_weighted_loss_sum = float(ck["student_weighted_loss_sum"])
        student_gradient_norm_probe = ck.get("student_gradient_norm_probe")
        elapsed_prior = float(ck.get("elapsed_seconds", 0.0))
    else:
        base = fit.make_model(cfg, norms).to(device)
        base.load_state_dict(original["state_dict"], strict=True)
        x0 = fit.model_input(model, teacher_val.batch_numpy(np.arange(16), 14), device)
        with torch.no_grad():
            step0_error = float(torch.max(torch.abs(model(x0) - base(x0))).cpu())
        if step0_error != 0.0:
            raise RuntimeError(f"Warm-start step0 does not match original package: {fit_id} {step0_error}")
        common0, detail0 = score_common(model, teacher_val, student_val, device)
        history.append({"step": 0, **detail0, "steps_per_s": 0.0, "elapsed_s": 0.0,
                        "loss_smoothl1_normalized": 0.0, "selected_best": False})
        order = rng.permutation(len(train_data.weights))
    model.train()
    timer = time.perf_counter()
    interval_timer = timer
    interval_steps = 0
    step = start_step
    train_n = len(train_data.weights)
    roles = train_data.role
    while step < TOTAL_STEPS:
        if cursor >= train_n:
            order = rng.permutation(train_n)
            cursor = 0
        end = min(cursor + BATCH, train_n)
        ids = order[cursor:end]
        cursor = end
        xb = fit.model_input(model, train_data.batch_numpy(ids, 14), device)
        yb = torch.from_numpy(train_data.target[ids]).to(device, dtype=torch.float32)
        wb = torch.from_numpy(train_data.weights[ids]).to(device, dtype=torch.float32)
        pred = model(xb)
        per_sample = F.smooth_l1_loss(pred / 3.0, yb / 3.0, reduction="none").mean(dim=1)
        scale = train_n / len(ids)
        loss = scale * torch.sum(wb * per_sample)
        role_batch = roles[ids]
        for role in consumed:
            consumed[role] += int(np.count_nonzero(role_batch == role))
        student_mask_np = role_batch == "STUDENT"
        if np.any(student_mask_np):
            student_mask = torch.as_tensor(student_mask_np, device=device, dtype=torch.bool)
            selected_student_loss = per_sample[student_mask]
            student_nonzero_loss_samples += int(torch.count_nonzero(selected_student_loss.detach() > 0).item())
            student_weighted_loss_sum += float(torch.sum(wb[student_mask] * selected_student_loss.detach()).cpu())
            if student_gradient_norm_probe is None:
                student_component = scale * torch.sum(wb[student_mask] * selected_student_loss)
                grads = torch.autograd.grad(student_component, tuple(model.parameters()), retain_graph=True, allow_unused=True)
                grad_sq = sum(float(torch.sum(g.detach() * g.detach()).cpu()) for g in grads if g is not None)
                student_gradient_norm_probe = float(np.sqrt(grad_sq))
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
        step += 1
        interval_steps += 1
        if step % EVAL_INTERVAL and step != TOTAL_STEPS:
            continue
        if device.type == "cuda":
            torch.cuda.synchronize()
        interval_elapsed = time.perf_counter() - interval_timer
        sps = interval_steps / max(interval_elapsed, 1e-9)
        common, detail = score_common(model, teacher_val, student_val, device)
        improved = common < best_val
        if improved:
            best_val, best_step, best_state, best_detail = common, step, fit.state_cpu(model), detail
            torch.save({"fit_id": fit_id, "model_id": model_id, "group": group, "seed": seed,
                        "state_dict": best_state, "selected_step": step, "common_val_detail": detail,
                        "source_checkpoint_sha256": original_hash, "protocol_sha256": protocol_hash},
                       folder / "best_common_val.pt")
        history.append({"step": step, **detail, "steps_per_s": sps,
                        "elapsed_s": elapsed_prior + time.perf_counter() - timer,
                        "loss_smoothl1_normalized": float(loss.detach().cpu()), "selected_best": bool(improved)})
        interval_timer, interval_steps = time.perf_counter(), 0
        cumulative_elapsed = elapsed_prior + time.perf_counter() - timer
        torch.save({"fit_id": fit_id, "model_id": model_id, "group": group, "seed": seed,
                    "protocol_sha256": protocol_hash, "source_checkpoint_sha256": original_hash,
                    "step": step, "cursor": cursor, "order": order, "model_state": fit.state_cpu(model),
                    "optimizer_state": optimizer.state_dict(), "history": history,
                    "best_val": best_val, "best_step": best_step, "best_state": best_state,
                    "best_detail": best_detail, "numpy_rng": rng.bit_generator.state,
                    "torch_rng_cpu": torch.get_rng_state(),
                    "torch_rng_cuda": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else None,
                    "consumed": consumed, "student_nonzero_loss_samples": student_nonzero_loss_samples,
                    "student_weighted_loss_sum": student_weighted_loss_sum,
                    "student_gradient_norm_probe": student_gradient_norm_probe,
                    "elapsed_seconds": cumulative_elapsed}, latest_path)
        write_history(folder / "training_history.csv", history)
        update_project_state(fit_id, model_id, group, seed, step, "RUNNING", completed_before)
        print(f"FIT_PROGRESS {fit_id} step={step}/{TOTAL_STEPS} steps_s={sps:.1f} common={common:.8g} "
              f"teacher={detail['teacher_val_rmse_mps2']:.8g} student={detail['student_val_rmse_mps2']:.8g} "
              f"best={best_val:.8g}@{best_step}", flush=True)
    if best_state is None or best_step <= 0:
        raise RuntimeError(f"No positive-step best package saved: {fit_id}")
    final_common, final_detail = score_common(model, teacher_val, student_val, device)
    final_state = fit.state_cpu(model)
    torch.save({"fit_id": fit_id, "model_id": model_id, "group": group, "seed": seed,
                "state_dict": final_state, "selected_step": TOTAL_STEPS,
                "common_val_detail": final_detail, "source_checkpoint_sha256": original_hash,
                "protocol_sha256": protocol_hash}, folder / "final_step.pt")
    student_seen = int(consumed.get("STUDENT", 0))
    if group == "TEACHER_CONTINUE" and (student_seen != 0 or student_nonzero_loss_samples != 0):
        raise RuntimeError(f"Student leaked into pure teacher fit: {fit_id}")
    if group == "STUDENT_MIX20" and (student_seen <= 0 or student_nonzero_loss_samples <= 0
                                     or not student_gradient_norm_probe or student_gradient_norm_probe <= 0):
        raise RuntimeError(f"Student did not contribute nonzero loss and gradient: {fit_id}")
    report = {
        "status": "COMPLETE", "fit_id": fit_id, "model_id": model_id, "group": group, "seed": seed,
        "source_checkpoint": str(original_path.relative_to(ROOT).as_posix()),
        "source_checkpoint_sha256": original_hash, "original_model_step": 60000,
        "start_output_max_abs_error": 0.0, "normalizer_frozen": True,
        "train_window_count": train_n, "teacher_val_window_count": len(teacher_val.weights),
        "student_val_window_count": len(student_val.weights),
        "role_weight_mass": {r: float(train_data.weights[roles == r].sum()) for r in sorted(set(roles.tolist()))},
        "optimizer_samples_seen_by_role": consumed,
        "student_samples_seen": student_seen, "student_nonzero_loss_samples": student_nonzero_loss_samples,
        "student_weighted_loss_sum": student_weighted_loss_sum,
        "student_gradient_norm_probe": student_gradient_norm_probe,
        "student_optimization_contribution_verified": bool(group == "STUDENT_MIX20" and student_seen > 0
                                                              and student_nonzero_loss_samples > 0
                                                              and student_gradient_norm_probe > 0),
        "teacher_continue_student_samples_seen": 0 if group == "TEACHER_CONTINUE" else None,
        "optimizer": {"name": "Adam", "lr": LR, "weight_decay": WEIGHT_DECAY, "batch_size": BATCH,
                      "fresh_state": True},
        "loss": "mean_axis SmoothL1(pred/3,target_clip/3), one hierarchical sample weight, N/batch correction",
        "steps": TOTAL_STEPS, "selected_step": best_step, "best_common_val_rmse_mps2": best_val,
        "best_common_val_detail": best_detail, "final_step_common_val_rmse_mps2": final_common,
        "final_step_common_val_detail": final_detail, "eval_steps": [r["step"] for r in history],
        "steps_per_s_mean": float(np.mean([r["steps_per_s"] for r in history if r["step"] > 0])),
        "elapsed_s": elapsed_prior + time.perf_counter() - timer,
        "protocol_sha256": protocol_hash, "fit_source_sha256": sha256(Path(__file__)),
        "model_source_sha256": sha256(SOURCE / "scripts/teacher_models.py"),
        "data_source_sha256": sha256(Path(__file__).with_name("student_data.py")),
        "completed_at_utc": utcnow(),
    }
    write_json(report_path, report)
    added_steps = TOTAL_STEPS - start_step
    ledger_status = "COMPLETE" if start_step == 0 else "RESUMED_COMPLETE"
    append_ledger(fit_id, ledger_status, added_steps,
                  f"cumulative_steps={TOTAL_STEPS};selected_step={best_step};source={group}")
    update_project_state(fit_id, model_id, group, seed, TOTAL_STEPS, "FIT_COMPLETE", completed_before + 1)
    print(f"FIT_COMPLETE {fit_id} steps={TOTAL_STEPS} best_common={best_val:.8g}@{best_step} "
          f"final_common={final_common:.8g} sps={report['steps_per_s_mean']:.1f}", flush=True)
    return report


def main() -> None:
    fit_reports = []
    norms = normalizers()
    completed = 0
    for model_id in ("GRU14", "DSSM14"):
        model_data = build_data(model_id)
        for group in GROUPS:
            for seed in SEEDS:
                fit_id = f"{group}_{model_id}_SEED{seed}"
                report = fit_one(model_id, group, seed, model_data, norms, completed)
                fit_reports.append(report)
                completed += 1
                pd.DataFrame(fit_reports).to_csv(OUT / "reports/training_results.csv", index=False)
    state_path = OUT / "state/state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
    state.update({"phase": "PAIRED_WARM_START_FITS", "status": "COMPLETE", "active_fit": "",
                  "active_model": "", "active_group": "", "fits_completed": 8,
                  "optimizer_steps_completed_total": 80000, "updated_at_utc": utcnow()})
    write_json(state_path, state)
    print("TRAINING_COMPLETE fits=8 optimizer_steps=80000", flush=True)


def extend_edge_fits(chunk_steps: int = 10000) -> None:
    global TOTAL_STEPS
    if chunk_steps <= 0 or chunk_steps % EVAL_INTERVAL:
        raise ValueError(f"extension chunk must be a positive multiple of {EVAL_INTERVAL}")
    reports_dir = OUT / "reports"
    baseline_csv = reports_dir / "training_initial_10k.csv"
    results_csv = reports_dir / "training_results.csv"
    if results_csv.is_file() and not baseline_csv.exists():
        shutil.copy2(results_csv, baseline_csv)
    reports = sorted((OUT / "models").glob("*/**/fit_report.json"))
    rows = [(p, json.loads(p.read_text(encoding="utf-8"))) for p in reports]
    if len(rows) != 8 or any(r.get("status") != "COMPLETE" for _, r in rows):
        raise RuntimeError("Edge extension requires all eight initial fits to be complete")
    targets = [(p, r) for p, r in rows if int(r.get("selected_step", -1)) == int(r.get("steps", 0))]
    archive = reports_dir / "training_extension_baseline"
    archive.mkdir(parents=True, exist_ok=True)
    for path, report in targets:
        shutil.copy2(path, archive / f"{report['fit_id']}.json")
    plan_path = reports_dir / "training_extension_plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8")) if plan_path.is_file() else {
        "status": "PENDING", "trigger": "best validation step equals training endpoint",
        "user_directed": True, "chunk_steps": chunk_steps, "initial_steps": 10000,
        "target_fit_ids": [r["fit_id"] for _, r in targets], "extensions": []}
    if int(plan.get("chunk_steps", chunk_steps)) != chunk_steps:
        raise RuntimeError("Extension chunk differs from the recorded plan")
    if not targets:
        plan.update({"status": "NO_EDGE_BEST", "completed_at_utc": utcnow()})
        write_json(plan_path, plan)
        print("NO_EDGE_BEST_FITS_TO_EXTEND", flush=True)
        return
    plan.update({"status": "RUNNING", "updated_at_utc": utcnow()})
    write_json(plan_path, plan)
    model_data: dict[str, dict] = {}
    norms = normalizers()
    while True:
        pending = []
        for path, _ in targets:
            report = json.loads(path.read_text(encoding="utf-8"))
            if int(report.get("selected_step", -1)) == int(report.get("steps", 0)):
                pending.append((path, report))
        if not pending:
            break
        for path, before in pending:
            fit_id = str(before["fit_id"])
            model_id, group, seed = str(before["model_id"]), str(before["group"]), int(before["seed"])
            if model_id not in model_data:
                model_data[model_id] = build_data(model_id)
            previous_steps = int(before["steps"])
            previous_best = int(before["selected_step"])
            previous_score = float(before["best_common_val_rmse_mps2"])
            TOTAL_STEPS = previous_steps + chunk_steps
            print(f"FIT_EXTENSION_START {fit_id} steps={previous_steps}->{TOTAL_STEPS} "
                  f"previous_best={previous_best}@{previous_score:.8g}", flush=True)
            after = fit_one(model_id, group, seed, model_data[model_id], norms, completed_before=8)
            extension = {"fit_id": fit_id, "from_steps": previous_steps, "to_steps": TOTAL_STEPS,
                         "previous_best_step": previous_best, "previous_best_common_val_rmse_mps2": previous_score,
                         "new_best_step": int(after["selected_step"]),
                         "new_best_common_val_rmse_mps2": float(after["best_common_val_rmse_mps2"]),
                         "best_still_at_endpoint": int(after["selected_step"]) == TOTAL_STEPS,
                         "completed_at_utc": utcnow()}
            plan["extensions"].append(extension)
            plan.update({"status": "RUNNING", "updated_at_utc": utcnow()})
            write_json(plan_path, plan)
            latest = [json.loads(p.read_text(encoding="utf-8")) for p in
                      sorted((OUT / "models").glob("*/**/fit_report.json"))]
            pd.DataFrame(latest).to_csv(results_csv, index=False)
        targets = [(p, json.loads(p.read_text(encoding="utf-8"))) for p, _ in targets]
    final_reports = [json.loads(p.read_text(encoding="utf-8")) for p in
                     sorted((OUT / "models").glob("*/**/fit_report.json"))]
    plan.update({"status": "COMPLETE", "final_steps_by_fit": {r["fit_id"]: int(r["steps"])
                                                                 for r in final_reports},
                 "completed_at_utc": utcnow()})
    write_json(plan_path, plan)
    state_path = OUT / "state/state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
    state.update({"phase": "PAIRED_WARM_START_FITS", "status": "COMPLETE", "active_fit": "",
                  "active_model": "", "active_group": "", "fits_completed": 8,
                  "optimizer_steps_completed_total": int(sum(r["steps"] for r in final_reports)),
                  "training_extension_plan": str(plan_path.relative_to(ROOT).as_posix()),
                  "updated_at_utc": utcnow()})
    write_json(state_path, state)
    print(f"TRAINING_EXTENSIONS_COMPLETE initial_edge_fits={len(targets)} "
          f"extension_chunks={len(plan['extensions'])} total_optimizer_steps={state['optimizer_steps_completed_total']}",
          flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--extend-edge", action="store_true",
                        help="extend any fit whose best common validation checkpoint is at the current endpoint")
    parser.add_argument("--extension-chunk", type=int, default=10000)
    args = parser.parse_args()
    extend_edge_fits(args.extension_chunk) if args.extend_edge else main()
