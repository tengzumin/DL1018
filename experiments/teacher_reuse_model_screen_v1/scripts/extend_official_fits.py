from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

import fit_models as fit
from teacher_data import EpisodeBank, normalizers

ROOT = fit.ROOT
OUT = fit.OUT


def write_json(path: Path, value: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def main() -> None:
    protocol_path = OUT / "protocol.json"
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    selection = json.loads((OUT / "reports" / "official_fit_selection.json").read_text(encoding="utf-8"))
    gate_path = OUT / "reports" / "official_fit_40k_gate.json"
    if not gate_path.is_file():
        raise RuntimeError("All selected 40k fits must reach their gate before applying the extension rule")
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    if gate.get("status") != "OFFICIAL_FITS_AT_40K_GATE" or len(gate.get("fits", [])) != 4:
        raise RuntimeError("The official four-fit 40k gate report is incomplete")
    histories = []
    for item in gate["fits"]:
        model_id, seed = item["model_id"], int(item["seed"])
        path = OUT / "models" / "official" / model_id / f"seed{seed}" / "training_history.csv"
        history = pd.read_csv(path)
        through30 = history.loc[(history.step <= 30000) & (history.kind == "POSITIVE_STEP_EVALUATION"),
                                "teacher_val_weighted_rmse_mps2"]
        band30to40 = history.loc[(history.step > 30000) & (history.step <= 40000)
                                 & (history.kind == "POSITIVE_STEP_EVALUATION"),
                                 "teacher_val_weighted_rmse_mps2"]
        if through30.empty or band30to40.empty:
            raise RuntimeError(f"Missing required 30k/40k evaluation history: {model_id} seed {seed}")
        best30 = float(through30.min())
        best30to40 = float(band30to40.min())
        improvement = (best30 - best30to40) / best30
        histories.append({"model_id": model_id, "seed": seed,
                          "best_through_30k_mps2": best30,
                          "best_30k_to_40k_mps2": best30to40,
                          "relative_improvement": improvement,
                          "triggered": improvement >= 0.01})
    triggered = any(row["triggered"] for row in histories)
    decision = {"status": "UNIFORM_60K_EXTENSION_REQUIRED" if triggered else "40K_GATE_FINAL",
                "protocol_sha256": fit.sha256_file(protocol_path),
                "rule": "If any successful selected fit improves by at least 1% in steps 30001-40000 over its best score through 30000, extend every successful selected fit to 60000.",
                "fit_evidence": histories, "decision_at_utc": datetime.now(timezone.utc).isoformat()}
    write_json(OUT / "reports" / "official_fit_extension_decision.json", decision)
    print(json.dumps(decision, ensure_ascii=False), flush=True)
    if not triggered:
        return

    train = EpisodeBank("train").windows(32)
    val = EpisodeBank("val").windows(32)
    if (len(train.bank.meta), len(val.bank.meta), len(train.weights), len(val.weights)) != (1536, 96, 605184, 37824):
        raise RuntimeError("The full teacher-only train/validation counts changed")
    norms = normalizers()
    schedule = protocol["training"]
    output = []
    for model_id in selection["model_ids"]:
        config = next(c for c in fit.CONFIGS if c["model_id"] == model_id)
        for seed in selection["seeds"]:
            path = OUT / "models" / "official" / model_id / f"seed{seed}" / "fit_report.json"
            prior = json.loads(path.read_text(encoding="utf-8"))
            if int(prior.get("last_step", 0)) != 40000:
                raise RuntimeError(f"Expected exact 40k resumable checkpoint for {model_id} seed {seed}")
            print(f"OFFICIAL_FIT_EXTEND_START model={model_id} seed={seed} steps=40000->60000", flush=True)
            report = fit.fit_one(config, int(seed), train, val, norms, schedule,
                                 decision["protocol_sha256"], "OFFICIAL", 60000)
            output.append({"fit_id": report["fit_id"], "model_id": model_id, "seed": int(seed),
                           "last_step": report["last_step"], "selected_step": report["selected_step"],
                           "best_teacher_val_rmse_mps2": report["selected_teacher_val_rmse_mps2"],
                           "final_teacher_val_rmse_mps2": report["final_step_teacher_val_rmse_mps2"],
                           "steps_per_s_mean": report["steps_per_s_mean"], "status": report["status"]})
            print(f"OFFICIAL_FIT_EXTEND_COMPLETE model={model_id} seed={seed} "
                  f"step={report['last_step']} best={report['selected_teacher_val_rmse_mps2']:.8g}", flush=True)
    final = {**decision, "status": "OFFICIAL_FITS_AT_60K", "fits": output,
             "finished_at_utc": datetime.now(timezone.utc).isoformat(), "plant_starts": 0}
    write_json(OUT / "reports" / "official_fit_60k_extension.json", final)
    print(json.dumps(final, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
