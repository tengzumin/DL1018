from __future__ import annotations

import csv
import importlib.util
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

import reconstruct_val_worker as worker


OUT = Path(__file__).resolve().parent
FROZEN_CORE = worker.FROZEN_CORE
SMOKE_IDS = ("G02_P_TEACHER_DL1018_VAL_T1_C00_W07_B",)
RESULTS = OUT / "VAL_V2_SMOKE_RESULTS.json"
METRICS = OUT / "VAL_V2_SMOKE_METRICS.csv"


def now() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")


def import_frozen_core():
    spec = importlib.util.spec_from_file_location("frozen_train_reconstruct_stratified", FROZEN_CORE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load frozen legacy core: {FROZEN_CORE}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> None:
    if RESULTS.exists() or METRICS.exists():
        raise RuntimeError("smoke outputs already exist; refusing overwrite")
    train_pin = worker.check_train_gate()
    rows, index_identity = worker.split_rows("VAL")
    by_id = {row["run_id"]: row for row in rows}
    if set(SMOKE_IDS) - by_id.keys():
        raise RuntimeError("one or more explicitly selected smoke IDs are absent from frozen VAL")
    model, model_info = worker.load_model()
    runtime_before = worker.core.signature(worker.core.RUNTIME_SOURCE)
    if runtime_before["sha256"] != worker.core.RUNTIME_SOURCE_SHA:
        raise RuntimeError("frozen runtime source SHA mismatch")
    legacy_core = import_frozen_core()
    output_rows = []
    metrics = []
    for run_id in SMOKE_IDS:
        sample = by_id[run_id]
        result, arrays = worker.core.reconstruct(sample, return_arrays=True)
        pred_raw = worker.infer_w0(arrays["x14"], model)
        beta_candidate = np.clip(arrays["event_time_s"] / worker.RUNTIME_BETA_RISE_S, 0., 1.)
        pred_applied = beta_candidate[worker.MODEL_VALID_START:, None] * np.clip(pred_raw, -3., 3.)
        if not np.isfinite(pred_applied).all():
            raise RuntimeError(f"{run_id}: fixed W0 inference returned nonfinite values")
        metrics.extend(worker.metric_rows(sample, arrays, pred_applied))

        legacy_compare = {"performed": False}
        if result["run_start_format"] == "MATLAB_5":
            old_result, old_arrays = legacy_core.reconstruct(sample, return_arrays=True)
            array_max_abs = {}
            for key in ("x14", "event_time_s", "event_index", "plant_index", "raw_index", "phase_code", "ready", "beta_teacher",
                        "Y_raw", "Y_clip", "r_f", "mixed_raw", "mixed_clip", "a_req", "a_f", "a_actual"):
                new_value = np.asarray(arrays[key])
                old_value = np.asarray(old_arrays[key])
                if new_value.shape != old_value.shape or not np.array_equal(new_value, old_value):
                    if new_value.shape != old_value.shape:
                        raise RuntimeError(f"{run_id}: frozen-core array shape differs for {key}")
                    delta = float(np.max(np.abs(new_value.astype(np.float64) - old_value.astype(np.float64)))) if new_value.size else 0.
                    raise RuntimeError(f"{run_id}: frozen-core array values differ for {key}: max_abs={delta}")
                array_max_abs[key] = 0.
            old_pred_raw = worker.infer_w0(old_arrays["x14"], model)
            if not np.array_equal(pred_raw, old_pred_raw):
                delta = float(np.max(np.abs(pred_raw - old_pred_raw)))
                raise RuntimeError(f"{run_id}: frozen-core fixed-model output differs: max_abs={delta}")
            old_beta = np.clip(old_arrays["event_time_s"] / worker.RUNTIME_BETA_RISE_S, 0., 1.)
            old_applied = old_beta[worker.MODEL_VALID_START:, None] * np.clip(old_pred_raw, -3., 3.)
            old_metrics = worker.metric_rows(sample, old_arrays, old_applied)
            new_metrics = worker.metric_rows(sample, arrays, pred_applied)
            if len(old_metrics) != len(new_metrics):
                raise RuntimeError(f"{run_id}: frozen-core metric row count differs")
            metric_numeric_max_abs = 0.
            metric_fields = ("valid_events", "target_rms_mps2", "prior_applied_rms_mps2", "zero_rmse_mps2", "prior_applied_rmse_mps2",
                             "prior_to_zero_rmse_ratio", "relative_sse_reduction_vs_zero", "prior_error_bias_mps2", "zero_error_bias_mps2")
            for old_row, new_row in zip(old_metrics, new_metrics):
                if (old_row["run_id"], old_row["target"], old_row["axis"]) != (new_row["run_id"], new_row["target"], new_row["axis"]):
                    raise RuntimeError(f"{run_id}: frozen-core metric row identity differs")
                for key in metric_fields:
                    metric_numeric_max_abs = max(metric_numeric_max_abs, abs(float(old_row[key]) - float(new_row[key])))
            if metric_numeric_max_abs != 0.:
                raise RuntimeError(f"{run_id}: frozen-core metric values differ: max_abs={metric_numeric_max_abs}")
            compare_fields = (
                "mass_kg", "gravity_mps2",
                "a0_replay_max_abs_mps2", "a_req_vs_a0_minus_u_max_abs_mps2", "physical_Y_vs_event_H5_max_abs_mps2",
                "X14_vs_event_H5_max_abs", "mixed_identity_max_abs_mps2", "event_time_vs_transition_max_abs_s",
                "raw_log_teacher_beta_vs_event_H5_max_abs", "Y_clip_vs_event_H5_max_abs_mps2", "rf_rms_all_axes_mps2",
                "Y_rms_all_axes_mps2", "Y_plus_M_rf_rms_all_axes_mps2",
            )
            for key in compare_fields:
                if result.get(key) != old_result.get(key):
                    raise RuntimeError(f"{run_id}: frozen-core result differs for {key}: {result.get(key)!r} vs {old_result.get(key)!r}")
            legacy_compare = {"performed": True, "frozen_core_sha256": worker.core.sha(FROZEN_CORE),
                              "all_return_arrays_bitwise_equal": True, "array_max_abs": array_max_abs,
                              "fixed_model_raw_output_bitwise_equal": True,"fixed_model_applied_output_bitwise_equal": bool(np.array_equal(pred_applied,old_applied)),
                              "metric_numeric_max_abs":metric_numeric_max_abs,
                              "compared_result_fields": list(compare_fields)}
        else:
            if result["cfg_source"] != "same-run /cfg" or result["opts_source"] != "same-run /opts":
                raise RuntimeError(f"{run_id}: root-schema cfg/opts provenance mismatch")
        output_rows.append({
            "run_id": run_id,
            "split": "VAL",
            "run_start_format": result["run_start_format"],
            "cfg_source": result["cfg_source"],
            "opts_source": result["opts_source"],
            "events": result["events"],
            "valid_inference_events": len(pred_raw),
            "a0_replay_max_abs_mps2": result["a0_replay_max_abs_mps2"],
            "a_req_vs_a0_minus_u_max_abs_mps2": result["a_req_vs_a0_minus_u_max_abs_mps2"],
            "physical_Y_vs_event_H5_max_abs_mps2": result["physical_Y_vs_event_H5_max_abs_mps2"],
            "X14_vs_event_H5_max_abs": result["X14_vs_event_H5_max_abs"],
            "mixed_identity_max_abs_mps2": result["mixed_identity_max_abs_mps2"],
            "event_time_vs_transition_max_abs_s": result["event_time_vs_transition_max_abs_s"],
            "raw_log_teacher_beta_vs_event_H5_max_abs": result["raw_log_teacher_beta_vs_event_H5_max_abs"],
            "Y_clip_vs_event_H5_max_abs_mps2": result["Y_clip_vs_event_H5_max_abs_mps2"],
            "rf_rms_all_axes_mps2": result["rf_rms_all_axes_mps2"],
            "Y_rms_all_axes_mps2": result["Y_rms_all_axes_mps2"],
            "Y_plus_M_rf_rms_all_axes_mps2": result["Y_plus_M_rf_rms_all_axes_mps2"],
            "legacy_frozen_core_comparison": legacy_compare,
            "run_start_sha256": result["run_start_sha256_after"],
            "raw_sha256": result["raw_sha256_after"],
            "event_h5_sha256": result["event_h5_sha256_after"],
            "cache_sha256": result["cache_sha256_after"],
            "source_sha_stat_unchanged": result["source_sha_stat_unchanged"],
        })
        print(f"PASS {run_id} {result['run_start_format']}", flush=True)

    runtime_after = worker.core.signature(worker.core.RUNTIME_SOURCE)
    model_after = worker.core.signature(worker.MODEL_SOURCE)
    if (runtime_before["sha256"], runtime_before["bytes"], runtime_before["mtime_ns"]) != (runtime_after["sha256"], runtime_after["bytes"], runtime_after["mtime_ns"]):
        raise RuntimeError("runtime source SHA/stat changed during smoke")
    if (model_info["file_sha256"], model_info["bytes"], model_info["mtime_ns"]) != (model_after["sha256"], model_after["bytes"], model_after["mtime_ns"]):
        raise RuntimeError("fixed model source SHA/stat changed during smoke")
    for path, expected in worker.core.EXPECTED.items():
        if worker.core.sha(path) != expected:
            raise RuntimeError(f"frozen index SHA changed during smoke: {path}")
    state = {"phase": "VAL_V2_FIXED_MODEL_MAT5_SMOKE", "status": "PASS_SMOKE", "completed_local": now(),
             "command": "python -B reports/train_pcf_contract_reconstruction_val_v2_20261022/smoke_val_v2.py",
             "core_script": str(worker.core.__file__), "core_script_sha256": worker.core.sha(worker.core.__file__),
             "worker_script": str(worker.__file__), "worker_script_sha256": worker.core.sha(worker.__file__),
             "model": model_info, "pinned_train_gate": train_pin, "source_indices": index_identity,
             "run_start_schema_audit_csv_sha256": worker.SCHEMA_AUDIT_CSV_SHA,
             "results": output_rows, "optimizer_steps": 0, "plant_calls": 0, "gpu_jobs": 0,
             "test_accessed": False, "dev_labels_used": False}
    with RESULTS.open("x", encoding="utf-8") as f:
        f.write(json.dumps(state, indent=2, ensure_ascii=False) + "\n")
    with METRICS.open("x", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(metrics[0]), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(metrics)
    print(json.dumps({"status": "PASS_SMOKE", "runs": list(SMOKE_IDS), "metrics_rows": len(metrics),
                      "results": str(RESULTS.resolve()), "metrics": str(METRICS.resolve())}, ensure_ascii=False))


if __name__ == "__main__":
    main()
