from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[3]
OUT = ROOT / "experiments" / "teacher_reuse_model_screen_v1"
sys.path.insert(0, str(HERE.parent))

import fit_models as fit  # noqa: E402
from teacher_data import EpisodeBank, normalizers  # noqa: E402
from x20_extension import KANFeature20  # noqa: E402

EXTENSION = OUT / "reports" / "x20_extension_authorization.json"
PROGRESS = OUT / "reports" / "x20_extension_fit_progress.json"
CONFIGS = (
    {"model_id": "KAN20", "family": "KAN", "input_dim": 20, "window": 32, "group": "CURRENT"},
    {"model_id": "GRU20", "family": "GRU", "input_dim": 20, "window": 32, "group": "TEMPORAL"},
    {"model_id": "DSSM20", "family": "DSSM", "input_dim": 20, "window": 32, "group": "TEMPORAL"},
)


def write_json(path: Path, value: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def main() -> None:
    protocol_path = OUT / "protocol.json"
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    if protocol.get("status") != "FROZEN_BEFORE_FIRST_FIT":
        raise RuntimeError("The original frozen teacher-reuse protocol is required")
    authorization = json.loads(EXTENSION.read_text(encoding="utf-8"))
    if authorization.get("status") != "USER_AUTHORIZED_EXTENSION":
        raise RuntimeError("Missing separate user-authorized X20 extension record")

    original_make_model = fit.make_model

    def make_model(config: dict, norms: dict):
        if config["model_id"] == "KAN20":
            return KANFeature20(norms["X20"]["mu"], norms["X20"]["sigma"])
        return original_make_model(config, norms)

    fit.make_model = make_model
    train_manifest = OUT / "manifests" / "small_teacher_pool.csv"
    import pandas as pd
    pool = pd.read_csv(train_manifest, keep_default_na=False)
    train = EpisodeBank("train", set(pool.run_id.astype(str))).windows(32)
    val = EpisodeBank("val").windows(32)
    if len(train.bank.meta) != 192 or len(val.bank.meta) != 96:
        raise RuntimeError("X20 extension must use the same 192-run subset and 96-run teacher VAL")
    norms = normalizers()
    schedule = protocol["training"]
    steps = int(schedule["fast_screen_steps"])
    if steps != 2000 or int(schedule["fast_eval_interval"]) != 500:
        raise RuntimeError("The uniform 2000-step/tick schedule differs from the frozen screening schedule")

    results = []
    record = {
        "status": "X20_EXTENSION_FITS_IN_PROGRESS",
        "original_protocol_sha256": fit.sha256_file(protocol_path),
        "extension_source_sha256": {
            "x20_extension.py": fit.sha256_file(HERE.parent / "x20_extension.py"),
            "fit_x20_extension.py": fit.sha256_file(HERE),
            "export_x20_extension.py": fit.sha256_file(HERE.parent / "export_x20_extension.py"),
            "run_teacher_reuse_canaries.m": fit.sha256_file(OUT / "local_runtime" / "run_teacher_reuse_canaries.m"),
            "run_x20_extension_parity.m": fit.sha256_file(OUT / "local_runtime" / "run_x20_extension_parity.m"),
        },
        "authorization_path": EXTENSION.relative_to(ROOT).as_posix(),
        "configs": list(CONFIGS), "seeds": list(fit.SEEDS),
        "train_runs": 192, "val_runs": 96, "train_windows": len(train.weights),
        "val_windows": len(val.weights), "steps_per_fit": steps,
        "uniform_training": {"optimizer": "Adam", "lr": fit.LR, "weight_decay": fit.WEIGHT_DECAY,
                             "batch_size": fit.BATCH, "eval_interval": 500},
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    write_json(PROGRESS, record)
    total = len(CONFIGS) * len(fit.SEEDS)
    for config in CONFIGS:
        for seed in fit.SEEDS:
            fit_id = f"FAST_SCREEN_{config['model_id']}_SEED{seed}"
            print(f"X20_EXTENSION_FIT_START model={config['model_id']} seed={seed} "
                  f"progress={len(results)+1}/{total} steps={steps}", flush=True)
            report = fit.fit_one(config, seed, train, val, norms, schedule,
                                 record["original_protocol_sha256"], "FAST_SCREEN", steps)
            results.append({"fit_id": fit_id, "model_id": config["model_id"], "seed": seed,
                            "status": report["status"], "last_step": report["last_step"],
                            "selected_step": report["selected_step"],
                            "best_teacher_val_rmse_mps2": report["selected_teacher_val_rmse_mps2"],
                            "final_teacher_val_rmse_mps2": report["final_step_teacher_val_rmse_mps2"],
                            "steps_per_s_mean": report["steps_per_s_mean"],
                            "fit_report_path": (OUT / "models" / "fast_screen" / config["model_id"]
                                                / f"seed{seed}" / "fit_report.json").relative_to(ROOT).as_posix()})
            write_json(PROGRESS, {**record, "completed_fits": results,
                                  "completed": len(results), "updated_at_utc": datetime.now(timezone.utc).isoformat()})
    final = {**record, "status": "X20_EXTENSION_FITS_COMPLETE", "completed": len(results),
             "fits": results, "finished_at_utc": datetime.now(timezone.utc).isoformat(), "plant_starts": 0}
    write_json(OUT / "reports" / "x20_extension_fit_screen.json", final)
    write_json(PROGRESS, final)
    print(json.dumps(final, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
