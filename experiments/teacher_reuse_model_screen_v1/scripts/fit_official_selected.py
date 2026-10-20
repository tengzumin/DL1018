from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import fit_models as fit
from teacher_data import EpisodeBank, normalizers

ROOT = fit.ROOT
OUT = fit.OUT
SELECTION = OUT / "reports" / "small_canary_selection.json"


def write_json(path: Path, value: dict) -> None:
    fit.json_write(path, value)


def main() -> None:
    protocol_path = OUT / "protocol.json"
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    if protocol.get("status") != "FROZEN_BEFORE_FIRST_FIT":
        raise RuntimeError("The frozen training protocol is required")
    selection = json.loads(SELECTION.read_text(encoding="utf-8"))
    if selection.get("status") != "SMALL_SCREEN_CANARY_COMPLETE" or selection.get("plant_starts") != 48:
        raise RuntimeError("The complete 48-start small-screen canary is required")
    winners = [selection.get("current_frame_winner"), selection.get("temporal_winner")]
    if any(not item or not item.get("complete_stable") for item in winners):
        raise RuntimeError("Both current-frame and temporal group winners must be complete and stable")
    model_ids = [str(item["group_id"]).removeprefix("SMALL_") for item in winners]
    configs = [next((cfg for cfg in fit.CONFIGS if cfg["model_id"] == model_id), None) for model_id in model_ids]
    if any(cfg is None for cfg in configs) or len(set(model_ids)) != 2:
        raise RuntimeError(f"Invalid two-group model selection: {model_ids}")
    expected_groups = ["CURRENT", "TEMPORAL"]
    if [cfg["group"] for cfg in configs] != expected_groups:
        raise RuntimeError(f"Unexpected group order/configuration: {[(c['model_id'], c['group']) for c in configs]}")

    train = EpisodeBank("train").windows(32)
    val = EpisodeBank("val").windows(32)
    if (len(train.bank.meta), len(val.bank.meta), len(train.weights), len(val.weights)) != (1536, 96, 605184, 37824):
        raise RuntimeError("Full official training or teacher-only validation counts changed")
    norms = normalizers()
    schedule = protocol["training"]
    gate = int(schedule["official_step_gate"])
    if gate != 40000 or int(schedule["official_eval_interval"]) != 2000:
        raise RuntimeError("Official 40k/2k schedule differs from the frozen protocol")

    record = {
        "status": "OFFICIAL_SELECTED_FITS_IN_PROGRESS",
        "protocol_sha256": fit.sha256_file(protocol_path),
        "selection_source": "reports/small_canary_selection.json",
        "selection_metric": "complete stable six-scene equal-weight macro Q_0_20_m",
        "current_frame_winner": winners[0], "temporal_winner": winners[1],
        "model_ids": model_ids, "seeds": list(fit.SEEDS),
        "train_runs": len(train.bank.meta), "val_runs": len(val.bank.meta),
        "train_windows": len(train.weights), "val_windows": len(val.weights),
        "step_gate": gate, "eval_interval": int(schedule["official_eval_interval"]),
        "extension_rule": "At 40k, if any successful fit improves by >=1% during 30k-40k over the best score through 30k, extend all successful selected fits to 60k.",
        "selected_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    selection_path = OUT / "reports" / "official_fit_selection.json"
    if selection_path.is_file():
        previous = json.loads(selection_path.read_text(encoding="utf-8"))
        if previous.get("protocol_sha256") != record["protocol_sha256"] or previous.get("model_ids") != model_ids:
            raise RuntimeError("The previously frozen official fit selection differs; refusing to replace it")
        record["selected_at_utc"] = previous.get("selected_at_utc", record["selected_at_utc"])
    write_json(selection_path, record)

    completed: list[str] = []
    state_path = OUT / "state" / "state.json"
    for cfg in configs:
        for seed in fit.SEEDS:
            print(f"OFFICIAL_FIT_START model={cfg['model_id']} seed={seed} progress={len(completed)+1}/4 steps={gate}", flush=True)
            report = fit.fit_one(cfg, seed, train, val, norms, schedule,
                                 record["protocol_sha256"], "OFFICIAL", gate)
            if report.get("last_step", 0) < gate:
                raise RuntimeError(f"Official fit did not reach its 40k gate: {report.get('fit_id')}")
            completed.append(str(report["fit_id"]))
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state.update({"phase": "OFFICIAL_FIT_40K_GATE", "status": "IN_PROGRESS",
                          "active_fit": None, "active_fit_step": 0, "active_fit_status": "FIT_AT_40K_GATE",
                          "fits_completed": completed, "plant_starts": 48,
                          "cumulative_new_plant_starts": 48, "plant_budget_max": 198,
                          "updated_at_utc": datetime.now(timezone.utc).isoformat()})
            write_json(state_path, state)
    reports = []
    for cfg in configs:
        for seed in fit.SEEDS:
            report_path = OUT / "models" / "official" / cfg["model_id"] / f"seed{seed}" / "fit_report.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            reports.append({"fit_id": report["fit_id"], "model_id": report["model_id"], "seed": seed,
                            "status": report["status"], "last_step": report["last_step"],
                            "best_step": report["selected_step"],
                            "best_teacher_val_rmse_mps2": report["selected_teacher_val_rmse_mps2"],
                            "final_teacher_val_rmse_mps2": report["final_step_teacher_val_rmse_mps2"],
                            "steps_per_s_mean": report["steps_per_s_mean"]})
    result = {**record, "status": "OFFICIAL_FITS_AT_40K_GATE", "fits": reports}
    write_json(OUT / "reports" / "official_fit_40k_gate.json", result)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state.update({"phase": "OFFICIAL_FITS_AT_40K_GATE", "status": "IN_PROGRESS",
                  "active_fit": None, "active_fit_status": "FIT_AT_40K_GATE",
                  "fits_completed": completed, "cumulative_new_plant_starts": 48,
                  "updated_at_utc": datetime.now(timezone.utc).isoformat()})
    write_json(state_path, state)
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
