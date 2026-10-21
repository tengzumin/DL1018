from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "experiments" / "position_causal_repair_v1"


def main() -> None:
    for candidate, family in (("C1", "C1_X20_FIXED_INFORMATION"), ("C2", "C2_X14_ADAPTATION_AWARE")):
        seed = 2026101901
        package = OUT / "models" / family / f"seed{seed}"
        pre_path = OUT / "reports" / f"D5_PREFLIGHT_{candidate}.json"
        exp_path = package / "export_report.json"
        pre = json.loads(pre_path.read_text(encoding="utf-8"))
        exp = json.loads(exp_path.read_text(encoding="utf-8"))
        if pre.get("status") != "PASS" or pre.get("plant_starts") != 0:
            raise RuntimeError(f"{candidate} zero-Plant preflight not passed")
        if exp.get("status") != "EXPORTED_AWAITING_MATLAB_PARITY":
            raise RuntimeError(f"Unexpected export status for {candidate}: {exp.get('status')}")
        pre["checkpoint_sha256"] = exp["checkpoint_sha256"]
        exp.update({"status": "MATLAB_PARITY_PASS", "max_phi_abs_error": pre["max_phi_abs_error"],
                    "max_output_abs_error": pre["max_output_abs_error"],
                    "matlab_forward_path": pre["isolated_forward_path"],
                    "plant_starts": 0})
        pre_path.write_text(json.dumps(pre, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        exp_path.write_text(json.dumps(exp, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    ledger = OUT / "RESOURCE_LEDGER.csv"
    existing = ledger.read_text(encoding="utf-8")
    stamp = datetime.now(timezone.utc).isoformat()
    entries = []
    if "CUDA_CUBLAS_WORKSPACE_CONFIG" not in existing:
        entries.append(f"{stamp},D4,engineering_error,CUDA_CUBLAS_WORKSPACE_CONFIG,0,RESOLVED,Initial C2 setup stopped before fit registration; deterministic CUDA env set and the same fit identity completed.\n")
    if "isolated_feature_and_batch_path_resolution" not in existing:
        entries.append(f"{stamp},D5,engineering_error,isolated_feature_and_batch_path_resolution,0,RESOLVED,No Plant was started; candidate feature construction was inlined in the isolated runtime and each zero-Plant preflight passed in a separate MATLAB process.\n")
    if entries:
        with ledger.open("a", encoding="utf-8", newline="") as f:
            f.writelines(entries)
    state_path = OUT / "state/state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    d3 = __import__("pandas").read_csv(OUT / "reports/D3_INITIAL_FINAL_BRIDGE.csv", keep_default_na=False)
    completed_ids = list(state.get("completed_run_ids", []))
    for run_id in d3.run_id.astype(str):
        if run_id not in completed_ids:
            completed_ids.append(run_id)
    state.update({"phase": "D5_PREFLIGHT_COMPLETE", "next": "D5_RUN_C2_SEED2026101901",
                  "d5_plant_starts_new": 0, "plant_starts_new": int(state.get("d3_plant_starts_new", 0)),
                  "completed_run_ids": completed_ids,
                  "updated_at_utc": stamp})
    tmp = state_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(state_path)
    print("D5 preflight manifests finalized: C1/C2 MATLAB parity PASS; Plant=0; resolved engineering setup issues logged.")


if __name__ == "__main__":
    main()
