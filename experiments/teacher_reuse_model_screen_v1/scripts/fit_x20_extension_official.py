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

from fit_x20_extension import CONFIGS, write_json  # noqa: E402


def main() -> None:
    selection_path = OUT / "reports" / "x20_extension_canary_selection.json"
    if not selection_path.is_file():
        raise RuntimeError("Both-seed six-scene X20 canary is required before full training")
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    if selection.get("status") != "X20_EXTENSION_CANARY_COMPLETE":
        raise RuntimeError("X20 extension canary has not completed")
    selected_ids = list(selection.get("advance_to_full_training", []))
    if not selected_ids:
        report = {"status": "NO_COMPETITIVE_X20_CANDIDATES", "selection_path": selection_path.relative_to(ROOT).as_posix(),
                  "plant_starts": 0, "fits": [], "finished_at_utc": datetime.now(timezone.utc).isoformat()}
        write_json(OUT / "reports" / "x20_extension_official_fits.json", report)
        print(json.dumps(report, ensure_ascii=False), flush=True)
        return
    if len(set(selected_ids)) != len(selected_ids) or any(i not in {c["model_id"] for c in CONFIGS} for i in selected_ids):
        raise RuntimeError(f"Invalid X20 extension selection: {selected_ids}")

    original_make_model = fit.make_model

    def make_model(config: dict, norms: dict):
        if config["model_id"] == "KAN20":
            return KANFeature20(norms["X20"]["mu"], norms["X20"]["sigma"])
        return original_make_model(config, norms)

    fit.make_model = make_model
    train, val = EpisodeBank("train").windows(32), EpisodeBank("val").windows(32)
    if (len(train.bank.meta), len(val.bank.meta), len(train.weights), len(val.weights)) != (1536, 96, 605184, 37824):
        raise RuntimeError("X20 extension full training must reuse the accepted 1536/96 teacher split")
    protocol_path = OUT / "protocol.json"
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    protocol_hash = fit.sha256_file(protocol_path)
    gate = int(protocol["training"]["official_step_gate"])
    if gate != 40000 or int(protocol["training"]["official_eval_interval"]) != 2000:
        raise RuntimeError("X20 full training must use the same 40k/2k schedule")
    norms = normalizers()
    record = {"status": "X20_EXTENSION_OFFICIAL_FITS_IN_PROGRESS", "original_protocol_sha256": protocol_hash,
              "selection_path": selection_path.relative_to(ROOT).as_posix(), "model_ids": selected_ids,
              "seeds": list(fit.SEEDS), "train_runs": 1536, "val_runs": 96,
              "train_windows": len(train.weights), "val_windows": len(val.weights), "step_gate": gate,
              "eval_interval": 2000, "plant_starts": 0,
              "started_at_utc": datetime.now(timezone.utc).isoformat()}
    write_json(OUT / "reports" / "x20_extension_official_fit_progress.json", record)
    results = []
    for model_id in selected_ids:
        config = next(c for c in CONFIGS if c["model_id"] == model_id)
        for seed in fit.SEEDS:
            fit_id = f"OFFICIAL_{model_id}_SEED{seed}"
            print(f"X20_OFFICIAL_FIT_START model={model_id} seed={seed} steps={gate}", flush=True)
            report = fit.fit_one(config, seed, train, val, norms, protocol["training"], protocol_hash,
                                 "OFFICIAL", gate)
            result = {"fit_id": fit_id, "model_id": model_id, "seed": seed,
                      "status": report["status"], "last_step": report["last_step"],
                      "selected_step": report["selected_step"],
                      "best_teacher_val_rmse_mps2": report["selected_teacher_val_rmse_mps2"],
                      "final_teacher_val_rmse_mps2": report["final_step_teacher_val_rmse_mps2"],
                      "steps_per_s_mean": report["steps_per_s_mean"]}
            results.append(result)
            write_json(OUT / "reports" / "x20_extension_official_fit_progress.json",
                       {**record, "completed": len(results), "fits": results,
                        "updated_at_utc": datetime.now(timezone.utc).isoformat()})
            print(f"X20_OFFICIAL_FIT_COMPLETE model={model_id} seed={seed} "
                  f"step={report['last_step']} best={report['selected_teacher_val_rmse_mps2']:.8g}", flush=True)
    final = {**record, "status": "X20_EXTENSION_OFFICIAL_FITS_AT_40K", "completed": len(results),
             "fits": results, "finished_at_utc": datetime.now(timezone.utc).isoformat()}
    write_json(OUT / "reports" / "x20_extension_official_fits.json", final)
    write_json(OUT / "reports" / "x20_extension_official_fit_progress.json", final)
    print(json.dumps(final, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
