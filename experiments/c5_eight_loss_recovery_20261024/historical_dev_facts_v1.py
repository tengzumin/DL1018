"""Explicit DEV text-table audit. No Plant, training, or raw MAT read."""
import csv
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports/paper_continuation_20261023/c5_eight_loss_recovery"
OLD = ROOT.parent / "DL1009/RBF-BS0/experiments/position_advantage_stage1_v1"
TRANSFER = ROOT / "experiments/old_kan_fig8_transfer_compare_v1"
FIX = ROOT.parent / "FIG8_ACC_FIX_CAUSAL_20261021_010512"
FULL = ROOT.parent / "REFERENCE_FIX_FULL72_20261021_022342_313"
inputs = []

def sha(p):
    with p.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()

def record(p):
    p = p.resolve()
    if not any(r["path"] == str(p) for r in inputs):
        inputs.append({"path": str(p), "sha256": sha(p), "bytes": p.stat().st_size})
    return p

def rows(p):
    with record(p).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))

def data(p):
    return json.loads(record(p).read_text(encoding="utf-8-sig"))

def write_json(name, value):
    with (OUT / name).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)

def write_csv(name, value):
    with (OUT / name).open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(value[0]))
        writer.writeheader()
        writer.writerows(value)

def stats(rr, b, c):
    return {"n": len(rr), "wins": sum(float(r[c]) < float(r[b]) - 1e-12 for r in rr),
            "B_macro_m": math.fsum(float(r[b]) for r in rr) / len(rr),
            "candidate_macro_m": math.fsum(float(r[c]) for r in rr) / len(rr),
            "loss_scene_ids": [r["scene_id"] for r in rr if float(r[c]) > float(r[b]) + 1e-12]}

old32 = rows(OLD / "reports/paired_metrics_DEV.csv")
assert len(old32) == 32 and {r["split"] for r in old32} == {"DEV"}
assert {r["architecture"] for r in old32} == {"N_KAN"}
old32stats = {"main_5_20": stats(old32, "B_Q", "C_Q"),
              "full_0_20": stats(old32, "B_full", "C_full")}
assert old32stats["main_5_20"]["wins"] == 32
assert old32stats["full_0_20"]["wins"] == 31
old_manifest = rows(OLD / "configs/scene_manifest.csv")
old_dev_manifest = [r for r in old_manifest if r["split"] == "DEV"]
assert {r["scene_id"] for r in old_dev_manifest} == {r["scene_id"] for r in old32}
old_config = data(OLD / "configs/contract.json")
old_fit = data(OLD / "models/final/N_KAN/fit_status.json")
for name in ("methods/stage1_metrics.m", "methods/stage1_scenes.m", "methods/stage1_evaluation.m",
             "methods/stage1_run_case.m", "methods/position_stage1_update_head.m",
             "run_position_stage1.m", "models/final/N_KAN/matlab_model_and_parity.mat",
             "models/final/N_KAN/normalizer.json"):
    record(OLD / name)
write_csv("OLD32_DEV_ALL_ROWS_v1.csv", old32)
write_csv("OLD32_DEV_SCENE_IDENTITY_v1.csv", old_dev_manifest)

old8 = [r for r in rows(TRANSFER / "reports/FIG8_MODEL_GAMMA_PAIRED.csv") if float(r["gamma"]) == 12]
assert len(old8) == 8
transfer_identity = data(TRANSFER / "audit/SOURCE_IDENTITY.json")
record(TRANSFER / "protocol.md")
c5_pairs_path = ROOT / "reports/paper_continuation_20261023/c5_matched_ablation_dev72_parent_review/MATCHED_ABLATION_DEV72_ALL_PAIRS_v1.csv"
pairs = [r for r in rows(c5_pairs_path) if r["variant"] == "C5_NO_DELAYED_PREDICTION"]
assert len(pairs) == 72
by_scene = {r["scene_id"]: r for r in pairs}
comparison = []
for r in old8:
    current = by_scene[r["scene_id"]]
    comparison.append({
        "scene_id": r["scene_id"], "historical_B_m": r["B_Q_0_20_m"],
        "historical_OLD_N_KAN_G12_R32_m": r["OLD_Q_0_20_m"],
        "historical_old_wins": int(float(r["OLD_Q_0_20_m"]) < float(r["B_Q_0_20_m"])),
        "current_B_m": current["B_TRACEABLE_Q_0_20_m"],
        "current_C5_m": current["C5_M110_Q_0_20_m"],
        "current_NO_PRED_m": current["variant_Q_0_20_m"],
        "current_C5_wins": int(float(current["C5_M110_Q_0_20_m"]) < float(current["B_TRACEABLE_Q_0_20_m"])),
        "same_physical_condition_claimed": False,
    })
write_csv("OLD8_CURRENT8_COMPARISON_v1.csv", comparison)
small = rows(ROOT / "experiments/teacher_reuse_model_screen_v1/reports/small_canary_results.csv")
small_dssm_fig8 = [r for r in small if r["phase"] == "SMALL_DSSM14" and r["task"] == "FIG8_3D"]
assert len(small_dssm_fig8) == 2
write_csv("SMALL_DSSM14_FIG8_TWO_ROWS_v1.csv",
          [{k: r[k] for k in ("phase", "scene_id", "Q_0_20_m", "B_Q_0_20_m", "delta_Q_vs_B_m")}
           for r in small_dssm_fig8])
fix_preflight = data(FIX / "reports/ZERO_PLANT_PREFLIGHT.json")
causal = data(FULL / "supporting_rescore/causal_dev_fig8/outputs/CAUSAL_FINAL.json")
record(FULL / "review/CAUSAL_FINAL_INDEPENDENT_REVIEW.json")
for p in (FIX / "sources/reference_original/make_scenes_dl1018.m",
          FIX / "sources/reference_fixed/make_scenes_dl1018.m",
          ROOT / "matlab/scenes/make_scenes_dl1018.m",
          ROOT / "reports/integration_next14_v1/PARENT_MATLAB_VERIFICATION.json",
          ROOT / "reports/integration_next14_v1/engineering/A_CORRECTED_REFERENCE_CACHE_GUARD_ZH.md"):
    record(p)
fix_evidence = {
    "initial_fix_preflight_created_local": fix_preflight["created_local"],
    "initial_fix_scene_checks": [{k: r[k] for k in (
        "scene_id", "fixed_scene_id", "source_scene_fields_equal",
        "only_scene_id_and_accY_accZ_changed", "original_reference_matches_B_raw",
        "fixed_reference_matches_generator")} for r in fix_preflight["scene_results"]],
    "source_original_sha256_recorded": fix_preflight["source_generator_sha256"],
    "source_fixed_sha256_recorded": fix_preflight["fixed_generator_sha256"],
    "original_dvdt_error_xyz_mps2": fix_preflight["original_acceleration_derivative_error_xyz"],
    "fixed_dvdt_error_xyz_mps2": fix_preflight["fixed_acceleration_derivative_error_xyz"],
    "full8_meta": causal["meta"],
    "scope_note": "Read existing independent array checks; this script did not decode old/fixed raws. Different B-Q alone is not an attribution.",
}
write_json("REFERENCE_FIX_EVIDENCE_v1.json", fix_evidence)
current_lock = data(ROOT / "experiments/position_axis_coordinate_c5_dev72_20261023/C5_DEV72_INPUT_LOCK_v3.json")
incident_path = ROOT.parent / "DL1009/RBF-BS0/experiments/kan_position_attitude_followup_v2/reports/D1_report_v2.md"
incident = {
    "status": "HISTORICAL_TEST_METRICS_ACCIDENTALLY_DISPLAYED_DO_NOT_USE",
    "path": str(incident_path), "sha256": sha(incident_path),
    "tool_time_observed_immediately_after_utc": "2026-10-23T17:18:56Z",
    "time_precision_note": "Clock read immediately after the tool result; exact file-read instant not separately logged.",
    "exposed_historical_scene_ids": ["TEST_C10_34_J2", "TEST_C10_34_J1"],
    "purpose": "Find the older N_KAN diagnostic and model lineage; file name did not identify mixed TEST content.",
    "containment": "Stopped reading the mixed report; no metrics copied here, used for candidate/parameter choice, or used as independent evidence.",
    "current_C5_TEST_performance_accessed": False,
    "physical_overlap_with_current_TEST48": "UNKNOWN; not established from metadata in this branch.",
    "frozen_C5_selection": "Frozen before this exposure. No model/controller edit or parameter selection in this branch.",
}
write_json("HISTORICAL_TEST_EXPOSURE_INCIDENT_v1.json", incident)
summary = {
    "status": "TEXT_EVIDENCE_PASS_PENDING_TARGETED_SAME_STATE_REPLAY",
    "created_utc": datetime.now(timezone.utc).isoformat(),
    "new_Plant": 0, "MATLAB_invocations": 0, "training_steps": 0,
    "current_C5_TEST_performance_accessed": False,
    "historical_TEST_exposure_incident": "HISTORICAL_TEST_EXPOSURE_INCIDENT_v1.json",
    "old32": {"stats": old32stats, "all_same_fig8_source": str(OLD / "methods/stage1_scenes.m"),
              "all32_reference": "cubic h=3s^2-2s^3, theta=2*pi*h; p=[1.5sin(theta),sin(2theta),.5(1-cos(theta))]",
              "canonical_seen_dev_rows": sum(r["canonical_seen"] in ("1", "true", "True") for r in old_dev_manifest),
              "method_contract": old_config, "final_fit": old_fit,
              "mapping_to_current_eight_losses": "NO scene-id or physical-input equivalence. Old DEV_C11_123_J2 is not current DEV/VAL T2 scene ID."},
    "old8": {"stats": stats(old8, "B_Q_0_20_m", "OLD_Q_0_20_m"), "identity": transfer_identity},
    "small_DSSM_fig8": stats(small_dssm_fig8, "B_Q_0_20_m", "Q_0_20_m"),
    "current_C5_model": current_lock["candidate_identity"],
    "inputs": inputs,
}
write_json("HISTORICAL_DEV_FACTS_v1.json", summary)
print(json.dumps({"old32": old32stats, "old8": summary["old8"]["stats"],
                  "small_dssm_fig8": summary["small_DSSM_fig8"],
                  "outputs": str(OUT)}, ensure_ascii=False, indent=2))
