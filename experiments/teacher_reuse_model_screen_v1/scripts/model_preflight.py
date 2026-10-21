from __future__ import annotations

import json
import os
import time
from pathlib import Path

import numpy as np
os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
import torch

from fit_models import BATCH, CONFIGS, LR, WEIGHT_DECAY, make_model, model_input, score_model, seed_all
from teacher_data import EpisodeBank, normalizers

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "experiments" / "teacher_reuse_model_screen_v1"


def sync(device: torch.device) -> None:
    if device.type == "cuda":
        torch.cuda.synchronize()


def main() -> None:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    norms = normalizers()
    print(f"MODEL_PREFLIGHT_DEVICE {device} "
          f"{torch.cuda.get_device_name(0) if device.type == 'cuda' else 'CPU'}", flush=True)
    full_train = EpisodeBank("train")
    val = EpisodeBank("val")
    import pandas as pd
    pool = pd.read_csv(OUT / "manifests/small_teacher_pool.csv", keep_default_na=False)
    small_train_bank = EpisodeBank("train", set(pool.run_id.astype(str)))
    small_train = small_train_bank.windows(32)
    small_train128 = small_train_bank.windows(128)
    val32, val128 = val.windows(32), val.windows(128)
    results = []
    for ci, cfg in enumerate(CONFIGS, start=1):
        seed_all(2026102001)
        model = make_model(cfg, norms).to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)
        window_set = val128 if cfg["window"] == 128 else val32
        train_window_set = small_train128 if cfg["window"] == 128 else small_train
        rng = np.random.default_rng(8000 + ci)
        ids = rng.integers(0, len(train_window_set.weights), size=BATCH, dtype=np.int64)
        xb = model_input(model, train_window_set.batch_numpy(ids, cfg["input_dim"]), device)
        yb = torch.from_numpy(train_window_set.target[ids]).to(device, dtype=torch.float32)
        for _ in range(12):
            pred = model(xb)
            loss = torch.nn.functional.smooth_l1_loss(pred / 3.0, yb / 3.0)
            optimizer.zero_grad(set_to_none=True); loss.backward(); optimizer.step()
        sync(device)
        start = time.perf_counter()
        measured_steps = 120
        for _ in range(measured_steps):
            pred = model(xb)
            loss = torch.nn.functional.smooth_l1_loss(pred / 3.0, yb / 3.0)
            optimizer.zero_grad(set_to_none=True); loss.backward(); optimizer.step()
        sync(device)
        elapsed = time.perf_counter() - start
        sps = measured_steps / max(elapsed, 1e-9)
        eval_start = time.perf_counter()
        val_score, val_detail = score_model(model, window_set, device)
        sync(device)
        val_seconds = time.perf_counter() - eval_start
        temporal = cfg["group"] == "TEMPORAL"
        fit_estimate_4000 = 4000 / sps + 4 * val_seconds
        results.append({"model_id": cfg["model_id"], "family": cfg["family"], "group": cfg["group"],
                        "input_dim": cfg["input_dim"], "window": cfg["window"],
                        "parameter_count": sum(p.numel() for p in model.parameters()),
                        "training_steps_per_s": sps, "measured_training_steps": measured_steps,
                        "teacher_val_evaluation_s": val_seconds,
                        "estimated_fast_fit_4000_steps_s": fit_estimate_4000,
                        "preflight_val_score_mps2_diagnostic_only": val_score,
                        "preflight_receptive_field_events": int(getattr(model, "receptive_field", 1)),
                        "effective_receptive_field_events": min(cfg["window"], int(getattr(model, "receptive_field", 1)))
                        if cfg["family"] == "TCN" else cfg["window"],
                        "device": str(device), "preflight_only_not_candidate_fit": True})
        print(f"MODEL_PREFLIGHT {cfg['model_id']} params={results[-1]['parameter_count']} "
              f"sps={sps:.3f} val_s={val_seconds:.3f} estimated_fit_min={fit_estimate_4000/60:.2f}", flush=True)
        del model, optimizer, xb, yb
        if device.type == "cuda":
            torch.cuda.empty_cache()

    temporal = [r for r in results if r["group"] == "TEMPORAL"]
    use_shorter_uniform_budget = any(r["estimated_fast_fit_4000_steps_s"] > 1800 for r in temporal)
    schedule = {"fast_screen_steps": 2000 if use_shorter_uniform_budget else 4000,
                "fast_eval_interval": 500 if use_shorter_uniform_budget else 1000,
                "official_step_gate_40k": 40000, "official_max_steps": 60000,
                "official_eval_interval": 2000,
                "official_extension_rule": "After all four full fits reach 40k, extend all successful fits to 60k only if any fit improved by >=1% during 30k-40k versus its best validation score through 30k.",
                "uniform_shorter_budget_trigger": "At least one temporal configuration has same-hardware estimated 4000-step fit >30 minutes."}
    report = {"status": "PASS_MODEL_PERFORMANCE_PREFLIGHT", "device": str(device),
              "torch_version": torch.__version__, "cuda_version": torch.version.cuda,
              "models": results, "training_schedule": schedule,
              "started_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "plant_starts": 0, "candidate_results_used_for_schedule": False}
    (OUT / "reports/model_performance_preflight.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(f"MODEL_PREFLIGHT_COMPLETE fast_steps={schedule['fast_screen_steps']} "
          f"eval_interval={schedule['fast_eval_interval']} temporal_over_30min={use_shorter_uniform_budget}", flush=True)


if __name__ == "__main__":
    main()
