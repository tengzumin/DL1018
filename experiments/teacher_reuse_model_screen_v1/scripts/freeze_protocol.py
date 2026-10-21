from __future__ import annotations

import hashlib
import csv
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "experiments" / "teacher_reuse_model_screen_v1"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    protocol_path = OUT / "protocol.json"
    if protocol_path.exists():
        raise RuntimeError("protocol.json already exists; the frozen protocol must not be regenerated")
    if any((OUT / "models").rglob("*.pt")) or (OUT / "runs").exists():
        raise RuntimeError("A fit checkpoint or Plant run exists before protocol freeze")

    audit_path = OUT / "reports/data_interface_audit.json"
    preflight_path = OUT / "reports/model_performance_preflight.json"
    audit, preflight = read_json(audit_path), read_json(preflight_path)
    upstream = read_json(ROOT / "experiments/position_only_closed_loop_search_v1/reports/FINAL_RESULT.json")
    groups = read_json(ROOT / "experiments/position_only_closed_loop_search_v1/reports/SEARCH_GROUP_SCORES.json")["groups"]
    if audit.get("status") != "PASS_DATA_PREFLIGHT" or preflight.get("status") != "PASS_MODEL_PERFORMANCE_PREFLIGHT":
        raise RuntimeError("Required data and performance preflights have not passed")
    if upstream.get("status") != "PASS_POSITION_DEV_BEATS_B":
        raise RuntimeError("The preceding position search is not complete")
    eligible = [g for g in groups if g["complete_stable"] and g["kappa"] > 0]
    head = min(eligible, key=lambda g: g["macro_Q_0_20_m"])
    selected = upstream["selected_candidate"]
    if (head["group_id"] != "FEATURE_G12_K1" or selected["head_type"] != "FEATURE"
            or selected["gamma"] != 12 or selected["kappa"] != 1 or not selected["pcf_enabled"]):
        raise RuntimeError("Upstream head selection does not match the verified FEATURE_G12_K1 result")

    prior_protocol = Path(r"C:\Users\35326\Downloads\DL1018_教师数据复用_五模型选型与位置闭环实验Prompt.md")
    source_files = [
        prior_protocol,
        ROOT / "configs/contract_dl1018.json",
        ROOT / "configs/scene_specs.csv",
        ROOT / "configs/effective_config.mat",
        ROOT / "models/position/initial/normalizer.npz",
        ROOT / "experiments/position_causal_repair_v1/scripts/d4_sequence_data.py",
        ROOT / "experiments/position_only_closed_loop_search_v1/reports/FINAL_RESULT.json",
        ROOT / "experiments/position_only_closed_loop_search_v1/reports/SEARCH_GROUP_SCORES.json",
        OUT / "manifests/teacher_reuse_manifest.csv",
        OUT / "manifests/small_teacher_pool.csv",
        audit_path,
        preflight_path,
        OUT / "scripts/teacher_data.py",
        OUT / "scripts/teacher_models.py",
        OUT / "scripts/fit_models.py",
        OUT / "scripts/model_preflight.py",
        OUT / "scripts/raw_sample_parity.m",
        OUT / "scripts/freeze_protocol.py",
    ]
    missing = [str(p) for p in source_files if not p.is_file()]
    if missing:
        raise FileNotFoundError("Cannot freeze without source evidence: " + ", ".join(missing))

    configs = preflight["models"]
    seeds = [2026102001, 2026102002]
    budget = {
        "new_plant_cap_total": 198,
        "small_screen_main_mode": 48,
        "full_fit_checkpoint_main_mode": 48,
        "two_selected_config_frozen_mode": 12,
        "dev24_first_and_optional_second": 48,
        "missing_baseline_references_only": 30,
        "engineering_retry_reserve": 12,
        "new_teacher_runs": 0,
        "new_student_runs": 0,
        "test_runs": 0,
        "old_package_bridge_runs": 0,
    }
    protocol = {
        "task": "DL1018_TEACHER_REUSE_MODEL_SCREEN_V1",
        "status": "FROZEN_BEFORE_FIRST_FIT",
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "project_root": str(ROOT),
        "git_at_freeze": {
            "branch": subprocess.run(["git", "branch", "--show-current"], cwd=ROOT,
                                      capture_output=True, text=True, check=True).stdout.strip(),
            "commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                      capture_output=True, text=True, check=True).stdout.strip(),
            "working_tree_has_local_changes": bool(subprocess.run(
                ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True,
                text=True, check=True).stdout.strip()),
        },
        "source_sha256": {p.relative_to(ROOT).as_posix() if p.is_relative_to(ROOT) else str(p): digest(p)
                          for p in source_files},
        "upstream_position_head": {
            "source": "experiments/position_only_closed_loop_search_v1/reports/FINAL_RESULT.json",
            "selected_complete_six_scene_group": head["group_id"],
            "head_type": selected["head_type"], "gamma": selected["gamma"],
            "kappa": selected["kappa"], "PCF": selected["pcf_enabled"],
            "six_scene_macro_Q_0_20_m": head["macro_Q_0_20_m"],
            "state_bound": 60, "leakage": 0.002,
            "beta_rise_s": selected["beta_rise_s"], "output_limit_mps2": [3, 3, 3],
            "position_rbf_output_and_update": False,
            "attitude_controller": "original_B_RBF_unchanged",
            "new_model_W0": "each model uses its own trained 33x3 readout; no upstream W0 or encoder weights are loaded",
            "implementation_source": "experiments/position_only_closed_loop_search_v1/local_runtime/position_only_search_head_step.m",
        },
        "fixed_system": {
            "contract_id": read_json(ROOT / "configs/contract_dl1018.json")["contract_id"],
            "contract_path": "configs/contract_dl1018.json",
            "plant": read_json(ROOT / "configs/contract_dl1018.json")["plant"],
            "position_bs_k1": read_json(ROOT / "configs/contract_dl1018.json")["controller"]["position_bs_k1"],
            "position_bs_k2": read_json(ROOT / "configs/contract_dl1018.json")["controller"]["position_bs_k2"],
            "attitude_bs_k1": read_json(ROOT / "configs/contract_dl1018.json")["controller"]["attitude_bs_k1"],
            "attitude_bs_k2": read_json(ROOT / "configs/contract_dl1018.json")["controller"]["attitude_bs_k2"],
            "nominal_C0": read_json(ROOT / "configs/contract_dl1018.json")["controller"]["nominal_C0"],
            "nominal_J0": read_json(ROOT / "configs/contract_dl1018.json")["controller"]["nominal_J0_kg_m2"],
            "command_filter": read_json(ROOT / "configs/contract_dl1018.json")["command_filter"],
            "plant_dt_s": 0.001, "position_event_hz": 100,
            "no_B_or_formal_contract_changes": True,
        },
        "data": {
            "accepted_teacher_manifest": "manifests/teacher_reuse_manifest.csv",
            "small_teacher_pool": "manifests/small_teacher_pool.csv",
            "audit": "reports/data_interface_audit.json",
            "accepted_teacher_runs": audit["index_counts"]["accepted_teacher_rows"],
            "train_runs": audit["index_counts"]["accepted_teacher_train_rows"],
            "val_runs": audit["index_counts"]["accepted_teacher_val_rows"],
            "train_B": audit["index_counts"]["train_B"],
            "train_POS_OFF": audit["index_counts"]["train_POS_OFF"],
            "val_B": audit["index_counts"]["val_B"],
            "val_POS_OFF": audit["index_counts"]["val_POS_OFF"],
            "paired_physical_train_scenes": audit["index_counts"]["paired_physical_train_scenes"],
            "paired_physical_val_scenes": audit["index_counts"]["paired_physical_val_scenes"],
            "student_records_excluded": audit["index_counts"]["student_records_excluded"],
            "normalizer_id": "TEACHER_TRAIN_INITIAL_X14_PLUS_TRAIN_X20_EXTRAS",
            "normalizer_values": audit["normalizer"],
            "small_pool_selection_seed": 2026102000,
            "small_pool_runs": audit["small_pool"]["rows"],
            "small_pool_physical_scenes": audit["small_pool"]["physical_scenes"],
            "small_pool_label_blind": True,
            "window_stride_events": 5,
            "L32_train_windows_full": audit["windows"]["L32_train_full"],
            "L32_val_windows": audit["windows"]["L32_val_teacher"],
            "L32_small_pool_windows": audit["windows"]["L32_small_teacher"],
            "L128_train_windows_full": audit["windows"]["L128_train_full"],
            "L128_val_windows": audit["windows"]["L128_val_teacher"],
            "target": "clip(a_actual - (a_nominal_without_learning - a_applied), -3, 3) m/s^2; output then update",
            "training_roles": ["B", "POS_OFF"],
            "validation_roles": ["B", "POS_OFF"],
            "excluded_from_training_validation_and_normalizer": ["P_INIT_STUDENT", "other Student records", "DEV", "TEST"],
        },
        "input_contract": {
            "X14": audit["input_contract"]["x14"],
            "X20_extra": audit["input_contract"]["x20_extra"],
            "X20_causal_source": audit["input_contract"]["causal_source"],
            "forbidden_inputs": ["current actual acceleration", "residual target", "true wind", "true morphology", "scene/task/wind ID"],
            "normalization": "X14 first ten dimensions use accepted teacher TRAIN statistics; last four arm commands remain raw. X20 adds six teacher TRAIN standardized dimensions.",
        },
        "models": {
            "predeclared_configs": configs,
            "seeds": seeds,
            "all_random_initialized": True,
            "forbidden_weight_sources": ["Initial", "Final", "HISTORY", "previous position candidate"],
            "common_output": "h in R^32; phi=[h;1]/sqrt(1+sum(h^2)); 33x3 readout in m/s^2",
            "TCN_dilations_L32": [1, 2, 4, 8, 16],
            "TCN_dilations_L128": [1, 2, 4, 8, 16, 32, 64],
            "TCN_receptive_field_events": {"L32": 63, "L128": 255},
            "GRU_state": "single layer, hidden 32; zero initial state for each independent window",
            "DSSM": {"state_dim": 32, "dt_s": 0.01, "tau_init_s_logspace": [0.02, 1.28], "tau_clamp_s": [0.005, 5.0]},
            "context_reset": "each sampled window is independent; no state carried between episodes or windows",
        },
        "training": {
            "optimizer": "Adam", "learning_rate": 0.001, "weight_decay": 1e-5, "batch_size": 256,
            "loss": "mean-axis SmoothL1(pred/3,target_clip/3), multiplied once by hierarchical sample weight; uniform shuffled endpoints and N/actual_batch unbiased scale",
            "hierarchical_weights": "role 0.5, task 1/3, class 1/16, equally weighted scenes per role/task/class, equal mass per observed phase within scene, uniform endpoints within phase",
            "fast_screen_steps": preflight["training_schedule"]["fast_screen_steps"],
            "fast_eval_interval": preflight["training_schedule"]["fast_eval_interval"],
            "shortened_uniform_budget_reason": "TCN14_L128 same-device 4000-step estimate exceeds 30 minutes",
            "full_train_from_scratch": True,
            "full_models": {"current_frame_group": 1, "temporal_group": 1},
            "full_fit_seeds_per_config": 2,
            "official_step_gate": preflight["training_schedule"]["official_step_gate_40k"],
            "official_max_steps": preflight["training_schedule"]["official_max_steps"],
            "official_eval_interval": preflight["training_schedule"]["official_eval_interval"],
            "official_uniform_extension_rule": preflight["training_schedule"]["official_extension_rule"],
            "best_checkpoint": "lowest positive-step teacher VAL RMSE",
            "final_checkpoint": "checkpoint at final scheduled step",
            "step0": "diagnostic only; never eligible for selection",
        },
        "canary": {
            "scene_ids": [
                "DL1018_TRAIN_T1_C02_W08", "DL1018_TRAIN_T1_C02_W15",
                "DL1018_TRAIN_T2_C01_W08", "DL1018_TRAIN_T2_C01_W15",
                "DL1018_TRAIN_T3_C03_W08", "DL1018_TRAIN_T3_C03_W15",
            ],
            "small_screen_seed": seeds[0],
            "small_screen_checkpoint": "teacher VAL best positive-step checkpoint",
            "second_seed_use": "offline direction comparison only; does not replace seed1 Plant model",
            "group_selection": "rank complete stable six-scene equal-weight Q_0_20; advance top current-frame and top temporal config; exceeding B is not required to enter full training",
            "full_stage": "two selected configs, two seeds each trained from scratch on all 1536 accepted teacher TRAIN runs; canary each best and final checkpoint, then freeze best canary package for six-scene comparison",
            "dev24": "predeclare first and optional second model/config/mode/checkpoint/normalizer/Head before running DEV; stop after first candidate if complete stable and macro Q_0_20 < same-scene B",
        },
        "metrics": {
            "primary": "equal-scene arithmetic mean of each scene's 3D position RMSE over 0 <= t < 20 s, Q_0_20_m",
            "secondary": ["Q_5_20_m", "per-scene/task/axis RMSE", "peak and p95", "attitude error", "motor TV", "saturation", "clip fraction", "runtime P99"],
            "position_win": "all 24 DEV scenes complete, finite and stable with no hard stop, and macro Q_0_20_m strictly below same-scene B",
            "real_time_claim_threshold_ms_p99": 10,
            "dev_is_blind_test": False,
        },
        "new_plant_budget": budget,
        "known_references_m": {
            "current_B_DEV24_Q_0_20": 0.016958918397443207,
            "old_Final_online_DEV24_Q_0_20": 0.028083902704153924,
            "previous_task_best_DEV24_Q_0_20": 0.0151714813076377,
            "previous_task_best_same_scene_B_Q_0_20": 0.016958918397443207,
            "scope": "historical reference only; do not identify the previous task winner as a newly trained model or substitute for this task's same-scene comparisons",
        },
        "preflight": {
            "data_status": audit["status"], "raw_export_parity": "PASS_SIX_RAW_REEXPORT_PARITY",
            "X20_raw_source_parity": audit["x20_raw_source_parity"]["status"],
            "model_performance_status": preflight["status"],
            "device": preflight["device"], "torch_version": preflight["torch_version"],
            "cuda_version": preflight["cuda_version"], "model_measurements": configs,
            "zero_plant_model_matlab_parity_required_before_plant": True,
            "plant_starts_at_freeze": 0,
            "resolved_preflight_issues": [
                "Set CUBLAS_WORKSPACE_CONFIG before importing torch to allow deterministic CUDA operations.",
                "Kept TCN model input in [batch,time,feature] order; TCN performs its own channel/time transpose.",
                "Selected the 128-event small-pool window for the L128 performance preflight.",
            ],
        },
        "recovery": {
            "fit_directive": "python experiments/teacher_reuse_model_screen_v1/scripts/fit_models.py --stage FAST_SCREEN",
            "state_path": "experiments/teacher_reuse_model_screen_v1/state/state.json",
            "checkpoint_rule": "stage-specific checkpoint folder; continue only matching run/protocol checkpoints; full fit starts from a new random initialization and does not load the screen checkpoint",
            "no_git_push_or_commit": True,
        },
        "software": {"python": sys.version, "torch": torch.__version__, "cuda": torch.version.cuda},
    }
    protocol_path.write_text(json.dumps(protocol, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                             encoding="utf-8")
    (OUT / "state").mkdir(exist_ok=True)
    initial_state = {
        "task": protocol["task"], "phase": "FROZEN_BEFORE_FIRST_FIT", "status": "IN_PROGRESS",
        "protocol_sha256": digest(protocol_path), "fits_started": 0, "fits_completed": [],
        "optimizer_steps_completed_total": 0, "plant_starts": 0, "teacher_runs": 0,
        "student_runs": 0, "test_runs": 0, "old_package_bridge_runs": 0,
        "preflight_errors": [
            {"status": "RESOLVED_BEFORE_FIT", "issue": issue}
            for issue in protocol["preflight"]["resolved_preflight_issues"]
        ],
        "updated_at_utc": protocol["frozen_at_utc"],
    }
    (OUT / "state/state.json").write_text(
        json.dumps(initial_state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    ledger = OUT / "RESOURCE_LEDGER.csv"
    with ledger.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(("timestamp_utc", "phase", "resource_type", "identity", "count", "status", "notes"))
        for i, issue in enumerate(protocol["preflight"]["resolved_preflight_issues"], start=1):
            writer.writerow((protocol["frozen_at_utc"], "MODEL_PREFLIGHT", "preflight",
                             f"ISSUE_{i}", 1, "RESOLVED", issue))
    (OUT / "reports/training_results.csv").write_text(
        "fit_id,stage,model_id,family,group,input_dim,window,seed,status,selected_step,last_step,train_samples,val_samples,parameters,weighted_val_rmse_mps2,natural_time_val_rmse_mps2,final_val_rmse_mps2,steps_per_s_mean,positive_step_improved_vs_step0,protocol_sha256,fit_report_path,best_checkpoint_path,final_checkpoint_path\n",
        encoding="utf-8")
    (OUT / "reports/closed_loop_results.csv").write_text(
        "run_id,stage,config_id,fit_id,checkpoint,mode,head_type,gamma,kappa,pcf,scene_id,task,status,complete,finite,transitions,plant_started,Q_0_20_m,Q_5_20_m,B_run_id,B_raw_path,B_Q_0_20_m,delta_Q_vs_B_m,position_axis_rmse_m,attitude_axis_rmse_rad,position_peak_m,position_p95_m,motor_TV_normalized_per_s,motor_saturation_fraction,generalized_clip_fraction,controller_p99_ms,controller_worst_ms,safety_stop_reason,wall_seconds,raw_path,run_start_path\n",
        encoding="utf-8")
    print(f"PROTOCOL_FROZEN sha256={digest(protocol_path)} fast_steps={protocol['training']['fast_screen_steps']} "
          f"eval={protocol['training']['fast_eval_interval']} plant_starts=0", flush=True)


if __name__ == "__main__":
    main()
