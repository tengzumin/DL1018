from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

import fit_models as fit
from teacher_data import EpisodeBank, normalizers

OUT = fit.OUT
AUTH = OUT / "reports" / "rbf_qualified_extension_authorization.json"
PROGRESS = OUT / "reports" / "rbf_qualified_official_fit_progress.json"
MODEL_IDS = ("KAN14", "DSSM14", "GRU20", "DSSM20")
X20_CONFIGS = (
    {"model_id": "GRU20", "family": "GRU", "input_dim": 20, "window": 32, "group": "TEMPORAL"},
    {"model_id": "DSSM20", "family": "DSSM", "input_dim": 20, "window": 32, "group": "TEMPORAL"},
)


def write_json(path: Path, value: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def main() -> None:
    authorization = json.loads(AUTH.read_text(encoding="utf-8"))
    if authorization.get("status") != "USER_AUTHORIZED_SCOPE_EXTENSION":
        raise RuntimeError("Missing user-authorized below-RBF extension")
    protocol_path = OUT / "protocol.json"
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    if protocol.get("status") != "FROZEN_BEFORE_FIRST_FIT":
        raise RuntimeError("The original frozen teacher-reuse protocol is required")
    configs = tuple(next(c for c in fit.CONFIGS if c["model_id"] == mid) for mid in ("KAN14", "DSSM14")) + X20_CONFIGS
    if tuple(c["model_id"] for c in configs) != MODEL_IDS:
        raise RuntimeError("The authorized configuration list changed")

    train, val = EpisodeBank("train").windows(32), EpisodeBank("val").windows(32)
    counts = (len(train.bank.meta), len(val.bank.meta), len(train.weights), len(val.weights))
    if counts != (1536, 96, 605184, 37824):
        raise RuntimeError(f"Teacher-only full split changed: {counts}")
    schedule = protocol["training"]
    gate = int(schedule["official_step_gate"])
    if gate != 40000 or int(schedule["official_eval_interval"]) != 2000:
        raise RuntimeError("The frozen official 40k/2k schedule changed")
    norms = normalizers()
    protocol_hash = fit.sha256_file(protocol_path)
    record = {
        "status": "IN_PROGRESS",
        "authorization_path": AUTH.relative_to(fit.ROOT).as_posix(),
        "protocol_sha256": protocol_hash,
        "model_ids": list(MODEL_IDS), "seeds": list(fit.SEEDS),
        "train_runs": counts[0], "val_runs": counts[1],
        "train_windows": counts[2], "val_windows": counts[3],
        "step_gate": gate, "eval_interval": int(schedule["official_eval_interval"]),
        "plant_starts": 0,
        "source_sha256": {"fit_models.py": fit.sha256_file(Path(fit.__file__)),
                           "teacher_models.py": fit.sha256_file(OUT / "scripts" / "teacher_models.py"),
                           "teacher_data.py": fit.sha256_file(OUT / "scripts" / "teacher_data.py")},
        "started_at_utc": datetime.now(timezone.utc).isoformat(), "completed_fits": []
    }
    write_json(PROGRESS, record)
    results = []
    for config in configs:
        for seed in fit.SEEDS:
            print(f"BELOW_RBF_OFFICIAL_FIT_START model={config['model_id']} seed={seed} steps={gate}", flush=True)
            report = fit.fit_one(config, seed, train, val, norms, schedule, protocol_hash, "OFFICIAL", gate)
            item = {"fit_id": report["fit_id"], "model_id": config["model_id"], "seed": seed,
                    "status": report["status"], "last_step": report["last_step"],
                    "selected_step": report["selected_step"],
                    "best_teacher_val_rmse_mps2": report["selected_teacher_val_rmse_mps2"],
                    "final_teacher_val_rmse_mps2": report["final_step_teacher_val_rmse_mps2"],
                    "steps_per_s_mean": report["steps_per_s_mean"]}
            results.append(item)
            write_json(PROGRESS, {**record, "completed_fits": results,
                                  "completed": len(results), "updated_at_utc": datetime.now(timezone.utc).isoformat()})

    evidence = []
    for item in results:
        history = pd.read_csv(OUT / "models" / "official" / item["model_id"]
                              / f"seed{item['seed']}" / "training_history.csv")
        valid = history[history.kind == "POSITIVE_STEP_EVALUATION"]
        through30 = valid.loc[valid.step <= 30000, "teacher_val_weighted_rmse_mps2"]
        band30to40 = valid.loc[(valid.step > 30000) & (valid.step <= 40000), "teacher_val_weighted_rmse_mps2"]
        if through30.empty or band30to40.empty:
            raise RuntimeError(f"Missing 30k/40k extension evidence: {item['fit_id']}")
        best30, best30to40 = float(through30.min()), float(band30to40.min())
        improvement = (best30 - best30to40) / best30
        evidence.append({"fit_id": item["fit_id"], "model_id": item["model_id"], "seed": item["seed"],
                         "best_through_30k_mps2": best30, "best_30k_to_40k_mps2": best30to40,
                         "relative_improvement": improvement, "triggered": improvement >= 0.01})
    extend = any(item["triggered"] for item in evidence)
    decision = {"status": "UNIFORM_60K_EXTENSION_REQUIRED" if extend else "40K_GATE_FINAL",
                "protocol_sha256": protocol_hash,
                "rule": "Apply the frozen extension rule to all eight fits: if any improves by at least 1% during steps 30001-40000 over its best through 30000, extend all to 60000.",
                "fit_evidence": evidence, "decision_at_utc": datetime.now(timezone.utc).isoformat()}
    write_json(OUT / "reports" / "rbf_qualified_fit_extension_decision.json", decision)
    if extend:
        for config in configs:
            for seed in fit.SEEDS:
                print(f"BELOW_RBF_OFFICIAL_FIT_EXTEND_START model={config['model_id']} seed={seed} steps=40000->60000", flush=True)
                report = fit.fit_one(config, seed, train, val, norms, schedule, protocol_hash, "OFFICIAL", 60000)
                item = next(x for x in results if x["model_id"] == config["model_id"] and x["seed"] == seed)
                item.update({"status": report["status"], "last_step": report["last_step"],
                             "selected_step": report["selected_step"],
                             "best_teacher_val_rmse_mps2": report["selected_teacher_val_rmse_mps2"],
                             "final_teacher_val_rmse_mps2": report["final_step_teacher_val_rmse_mps2"],
                             "steps_per_s_mean": report["steps_per_s_mean"]})
                print(f"BELOW_RBF_OFFICIAL_FIT_EXTEND_COMPLETE model={config['model_id']} seed={seed} step={report['last_step']}", flush=True)

    final = {**record, "status": "OFFICIAL_FITS_AT_60K" if extend else "OFFICIAL_FITS_AT_40K",
             "completed": len(results), "fits": results, "extension_decision": decision,
             "finished_at_utc": datetime.now(timezone.utc).isoformat()}
    write_json(OUT / "reports" / "rbf_qualified_official_fits.json", final)
    write_json(PROGRESS, final)
    print(json.dumps(final, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
