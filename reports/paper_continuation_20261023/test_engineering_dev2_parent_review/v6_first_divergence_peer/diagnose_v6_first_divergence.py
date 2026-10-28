"""Read-only, pinned h5py review of the first DSSM engineering-DEV replay."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[4]
REPORT = ROOT / "reports/paper_continuation_20261023"
MANIFEST = REPORT / "test_entry_v3/TEST_METHOD_SOURCE_MANIFEST_v1.json"
OLD_AUDIT = REPORT / "test_engineering_dev2_parent_review/audit_dev2_reproduction_v5.py"
NEW_RAW = ROOT / "experiments/c5_test48_v6/engineering_dev2/DSSM/DL1018_VAL_T1_C00_W07/attempt_01/raw_run.mat"
EXPECTED = {
    "manifest": "b9ed7fef91bf61b03e4f51d8a9cbaf7233484ac6faa4750827aefb7e247f9633",
    "old_raw": "e54111ca11559ccb5d1e7c9ca9824db0b225234b2cff3497d5cfe71e1878c8d8",
    "new_raw": "c3305039bbcae69c59051236e13a02295831c676984cebedad7772f7fc51fa81",
    "old_start": "1b6417b4369f5b5618d1ee81ac8595de1bb6d607e0fdd04ad2913748f6986cde",
    "new_start": "65915d6b1d84d4aec2c5042ef29b601346a7769bafc792a9f8d20fb4e87b5c13",
}
WALL_TIMERS = {
    "controller_call_time_s", "network_call_time_s",
    "stage1_position_inference_time_s", "stage1_position_event_inference_time_s",
}
FIRST_EVENT_FIELDS = {
    "stage1_position_feature_input": "model-input X14 at first ready event",
    "stage1_position_feature_14": "causal X14 feature at first ready event",
    "stage1_position_event_phi_33": "normalized 33D encoder output",
    "stage1_position_event_raw_acceleration_mps2": "position-head raw output",
    "stage1_position_event_applied_acceleration_mps2": "position-head applied output",
    "stage1_position_pcf_a_req_mps2": "PCF commanded-acceleration input",
    "stage1_position_pcf_a_f_mps2": "PCF filtered acceleration",
    "stage1_position_pcf_r_f_mps2": "PCF residual forcing",
    "stage1_position_pcf_eta_before_mps": "PCF coordination state before filter step",
    "stage1_position_pcf_eta_after_mps": "PCF coordination state after filter step",
    "stage1_position_pcf_event_s_coord_mps": "search update's PCF-coordinate input",
    "stage1_position_event_beta": "event learning-rate schedule",
    "stage1_position_event_dt_s": "event interval",
}


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def import_pinned_audit():
    spec = importlib.util.spec_from_file_location("pinned_dev2_audit", OLD_AUDIT)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot import the read-only pinned DEV decoder.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _, helpers = module.load_wrapper()
    _, c5_review, _, decoder, _ = helpers
    return module, c5_review, decoder


def numeric_datasets(group: h5py.Group) -> dict[str, h5py.Dataset]:
    result: dict[str, h5py.Dataset] = {}

    def visit(name: str, obj: h5py.Dataset | h5py.Group) -> None:
        if not isinstance(obj, h5py.Dataset) or obj.dtype.kind not in "fiub":
            return
        matlab_class = obj.attrs.get("MATLAB_class", b"")
        if isinstance(matlab_class, bytes):
            matlab_class = matlab_class.decode("ascii", errors="ignore")
        if str(matlab_class).casefold() in {"char", "string"}:
            return
        result[name] = obj

    group.visititems(visit)
    return result


def first_index(mask: np.ndarray) -> list[int] | None:
    locations = np.argwhere(mask)
    return [int(v) for v in locations[0]] if locations.size else None


def value_at(array: np.ndarray, index: list[int] | None):
    if index is None:
        return None
    value = np.asarray(array)[tuple(index)]
    return value.item() if isinstance(value, np.generic) else value


def to_numeric_array(value) -> np.ndarray:
    return np.asarray(value, dtype=np.float64)


def dssm_phi(model: dict, feature_window: np.ndarray) -> np.ndarray:
    """Pure NumPy transcription of the pinned DSSM branch in model_forward_v2.m."""
    mu = to_numeric_array(model["input_mu"]).reshape(-1)
    sigma = np.maximum(to_numeric_array(model["input_sigma"]).reshape(-1), 1e-4)
    x = (feature_window - mu[:, None]) / sigma[:, None]
    tau = to_numeric_array(model["ssm_tau"]).reshape(-1)
    alpha = np.exp(-0.01 / tau)
    input_w = to_numeric_array(model["input_W"])
    input_b = to_numeric_array(model["input_b"]).reshape(-1)
    state = np.zeros(32, dtype=np.float64)
    for k in range(x.shape[1]):
        drive = np.tanh(input_w @ x[:, k] + input_b)
        state = alpha * state + (1.0 - alpha) * drive
    h = np.tanh(to_numeric_array(model["project_W"]) @ state
                + to_numeric_array(model["project_b"]).reshape(-1))
    return np.concatenate((h, [1.0])) / np.sqrt(1.0 + np.dot(h, h))


def scalar_or_vector_delta(a: np.ndarray, b: np.ndarray) -> dict:
    aa = np.asarray(a)
    bb = np.asarray(b)
    if aa.shape != bb.shape:
        return {"same_shape": False, "shape_a": list(aa.shape), "shape_b": list(bb.shape)}
    if aa.dtype.kind in "fc" or bb.dtype.kind in "fc":
        valid = np.isfinite(aa) & np.isfinite(bb)
        delta = np.abs(aa.astype(np.float64) - bb.astype(np.float64))
        max_abs = float(np.max(delta[valid])) if np.any(valid) else None
        exact_mask = ((aa != bb) & valid) | (np.isnan(aa) != np.isnan(bb))
        over_mask = valid & (delta > 1e-12)
    else:
        exact_mask = aa != bb
        over_mask = exact_mask
        max_abs = float(np.max(np.abs(aa.astype(np.float64) - bb.astype(np.float64))))
    return {
        "same_shape": True,
        "max_abs": max_abs,
        "n_exact_value_mismatches": int(np.count_nonzero(exact_mask)),
        "first_exact_value_mismatch_index": first_index(exact_mask),
        "first_gt_1e-12_index": first_index(over_mask),
    }


def time_for_index(name: str, index: list[int] | None, data_shape: tuple[int, ...], times: np.ndarray):
    if index is None:
        return None
    if name in {"state", "initial_state"} and data_shape[-1] == times.size:
        return float(times[index[-1]])
    if data_shape and data_shape[-1] == times.size - 1:
        return float(times[index[-1]])
    return None


def main() -> None:
    assert sha(MANIFEST) == EXPECTED["manifest"], "Frozen v3 manifest SHA changed."
    audit, c5_review, decoder = import_pinned_audit()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
    method = next(item for item in manifest["methods"] if item["alias"] == "DSSM")
    old_start = Path(method["cfg_opts_snapshot_path"]).resolve(strict=True)
    old_raw = old_start.with_name("raw_run.mat").resolve(strict=True)
    new_raw = NEW_RAW.resolve(strict=True)
    new_start = new_raw.with_name("run_start.mat").resolve(strict=True)
    assert sha(old_start) == EXPECTED["old_start"]
    assert sha(old_raw) == EXPECTED["old_raw"]
    assert sha(new_start) == EXPECTED["new_start"]
    assert sha(new_raw) == EXPECTED["new_raw"]
    assert new_raw.is_relative_to(ROOT / "experiments/c5_test48_v6/engineering_dev2")
    assert "TEST_accessed" not in str(new_raw)

    old_opts = c5_review.matlab_section_safe(old_start, "opts", decoder)["stage1_position_runtime"]
    new_opts = c5_review.matlab_section_safe(new_start, "opts", decoder)["stage1_position_runtime"]
    old_model, new_model = old_opts["model"], new_opts["model"]
    model_differences = []
    for name in sorted(set(old_model) | set(new_model)):
        if name not in old_model or name not in new_model:
            model_differences.append({"field": name, "kind": "missing"})
            continue
        try:
            a, b = to_numeric_array(old_model[name]), to_numeric_array(new_model[name])
        except (TypeError, ValueError):
            if repr(old_model[name]) != repr(new_model[name]):
                model_differences.append({"field": name, "kind": "nonnumeric_value_mismatch"})
            continue
        if a.shape != b.shape or not np.array_equal(a, b, equal_nan=True):
            row = {"field": name, "shape_old": list(a.shape), "shape_new": list(b.shape)}
            if a.shape == b.shape:
                row["max_abs"] = float(np.max(np.abs(a - b)))
                row["n_unequal"] = int(np.count_nonzero(a != b))
            model_differences.append(row)

    old_w0 = to_numeric_array(old_opts["position_only_search_head"]["W0"])
    new_w0 = to_numeric_array(new_opts["position_only_search_head"]["W0"])
    w0_hashes = {
        "old_historical_run_start": hashlib.sha256(old_w0.reshape(-1, order="F").tobytes()).hexdigest(),
        "new_engineering_run_start": hashlib.sha256(new_w0.reshape(-1, order="F").tobytes()).hexdigest(),
    }

    with h5py.File(old_raw, "r") as old_file, h5py.File(new_raw, "r") as new_file:
        old_log, new_log = old_file["log"], new_file["log"]
        old_numeric, new_numeric = numeric_datasets(old_log), numeric_datasets(new_log)
        if set(old_numeric) != set(new_numeric):
            raise AssertionError({"missing_new": sorted(set(old_numeric) - set(new_numeric)),
                                  "extra_new": sorted(set(new_numeric) - set(old_numeric))})
        raw_differences = []
        identical_count = 0
        for name in sorted(old_numeric):
            if name in WALL_TIMERS:
                continue
            a, b = np.asarray(old_numeric[name]), np.asarray(new_numeric[name])
            if a.shape != b.shape or a.dtype != b.dtype:
                raw_differences.append({"field": name, "kind": "shape_or_dtype_mismatch",
                                        "shape_old": list(a.shape), "shape_new": list(b.shape),
                                        "dtype_old": str(a.dtype), "dtype_new": str(b.dtype)})
                continue
            d = scalar_or_vector_delta(a, b)
            if d["n_exact_value_mismatches"] == 0:
                identical_count += 1
                continue
            item = {"field": name, "shape": list(a.shape), "dtype": str(a.dtype), **d}
            item["first_exact_time_s"] = time_for_index(name, d["first_exact_value_mismatch_index"], a.shape,
                                                         np.asarray(old_log["time"]).reshape(-1))
            item["first_gt_1e-12_time_s"] = time_for_index(name, d["first_gt_1e-12_index"], a.shape,
                                                            np.asarray(old_log["time"]).reshape(-1))
            if name == "stage1_position_event_weight_before_33x3":
                event_step = int(np.asarray(old_log["stage1_position_event_step_index"]).reshape(-1)[0])
                item["first_event_call_time_s"] = float(np.asarray(old_log["time"]).reshape(-1)[event_step - 1])
            raw_differences.append(item)

        times = np.asarray(old_log["time"]).reshape(-1)
        event = np.asarray(old_log["stage1_position_event"]).reshape(-1).astype(bool)
        inference_valid = np.asarray(old_log["stage1_position_event_inference_valid"]).reshape(-1).astype(bool)
        inference_index = int(np.flatnonzero(inference_valid)[0])
        event_rows = np.flatnonzero(event & (np.arange(event.size) <= inference_index))[-32:]
        old_window = np.asarray(old_log["stage1_position_feature_input"])[:, event_rows]
        new_window = np.asarray(new_log["stage1_position_feature_input"])[:, event_rows]
        old_phi_recorded = np.asarray(old_log["stage1_position_event_phi_33"])[:, inference_index]
        new_phi_recorded = np.asarray(new_log["stage1_position_event_phi_33"])[:, inference_index]
        old_phi_recomputed = dssm_phi(old_model, old_window)
        new_phi_recomputed = dssm_phi(new_model, new_window)
        old_raw_output = np.asarray(old_log["stage1_position_event_raw_acceleration_mps2"])[:, inference_index]
        new_raw_output = np.asarray(new_log["stage1_position_event_raw_acceleration_mps2"])[:, inference_index]
        cross_outputs = {
            "old_W0_old_encoder": old_w0.T @ old_phi_recomputed,
            "old_W0_new_encoder": old_w0.T @ new_phi_recomputed,
            "new_W0_old_encoder": new_w0.T @ old_phi_recomputed,
            "new_W0_new_encoder": new_w0.T @ new_phi_recomputed,
        }
        first_event = {}
        for name, description in FIRST_EVENT_FIELDS.items():
            a = np.asarray(old_log[name])
            b = np.asarray(new_log[name])
            if a.ndim == 2 and a.shape[-1] == times.size - 1:
                a, b = a[:, inference_index], b[:, inference_index]
            first_event[name] = {
                "description": description,
                "same_exactly": bool(np.array_equal(a, b, equal_nan=True)),
                "max_abs": float(np.nanmax(np.abs(a.astype(float) - b.astype(float)))),
            }
        state_old = np.asarray(old_log["state"])
        state_new = np.asarray(new_log["state"])
        state_diff = np.abs(state_old - state_new)
        exact_state = np.argwhere(state_old != state_new)[0]
        tol_state = np.argwhere(state_diff > 1e-12)[0]
        same_state_through_event = np.array_equal(state_old[:, :inference_index + 1],
                                                  state_new[:, :inference_index + 1], equal_nan=True)

        results = {
            "schema": "V6_FIRST_DSSM_DEV_DIVERGENCE_PEER_V1",
            "scope": "Read-only comparison of one historical DEV raw and the completed v6 engineering DEV raw. No MATLAB, Plant, training, TEST result, or retry was run/read.",
            "status": "DIVERGENCE_CONFIRMED_INITIAL_MODEL_IDENTITY_MISMATCH",
            "manifest_path": str(MANIFEST.resolve()),
            "manifest_sha256": sha(MANIFEST),
            "old_start_path": str(old_start),
            "old_start_sha256": sha(old_start),
            "old_raw_path": str(old_raw),
            "old_raw_sha256": sha(old_raw),
            "new_start_path": str(new_start),
            "new_start_sha256": sha(new_start),
            "new_raw_path": str(new_raw),
            "new_raw_sha256": sha(new_raw),
            "pinned_model_mat_path": method["model_identity"]["model_mat_path"],
            "pinned_model_mat_sha256": method["model_identity"]["model_mat_sha256"],
            "pinned_W0_sha256": method["model_identity"]["W0_sha256"],
            "old_new_W0_max_abs": float(np.max(np.abs(old_w0 - new_w0))),
            "W0_hashes_float64_column_major": w0_hashes,
            "numeric_model_parameter_differences": model_differences,
            "raw_numeric_log_comparison": {
                "compared_numeric_arrays_excluding_four_walltimers": len(old_numeric) - len(WALL_TIMERS),
                "identical_arrays": identical_count,
                "different_arrays": [item for item in raw_differences if item.get("kind") != "shape_or_dtype_mismatch"],
                "schema_mismatches": [item for item in raw_differences if item.get("kind") == "shape_or_dtype_mismatch"],
                "excluded_walltimers": sorted(WALL_TIMERS),
            },
            "first_ready_event": {
                "call_time_s": float(times[inference_index]),
                "log_axis_zero_based_index": inference_index,
                "event_rows_used_for_model_history_zero_based": [int(x) for x in event_rows],
                "event_window_inputs_exactly_equal": bool(np.array_equal(old_window, new_window, equal_nan=True)),
                "event_window_inputs_max_abs": float(np.max(np.abs(old_window - new_window))),
                "state_identical_through_call_sample": bool(same_state_through_event),
                "x14_feature_identical_at_call": bool(first_event["stage1_position_feature_14"]["same_exactly"]),
                "recorded_phi_max_abs_difference": float(np.max(np.abs(old_phi_recorded - new_phi_recorded))),
                "python_forward_recompute_max_abs_error_old": float(np.max(np.abs(old_phi_recomputed - old_phi_recorded))),
                "python_forward_recompute_max_abs_error_new": float(np.max(np.abs(new_phi_recomputed - new_phi_recorded))),
                "recomputed_phi_old_new_max_abs_difference": float(np.max(np.abs(old_phi_recomputed - new_phi_recomputed))),
                "recorded_head_raw_output_old": old_raw_output.tolist(),
                "recorded_head_raw_output_new": new_raw_output.tolist(),
                "crossed_W0_encoder_outputs": {k: np.asarray(v).tolist() for k, v in cross_outputs.items()},
                "pcf_and_update_inputs_at_call": first_event,
            },
            "state_divergence": {
                "first_exact_value_mismatch_index": [int(x) for x in exact_state],
                "first_exact_value_mismatch_time_s": float(times[int(exact_state[-1])]),
                "first_exact_value_difference": float(state_diff[tuple(exact_state)]),
                "first_gt_1e-12_index": [int(x) for x in tol_state],
                "first_gt_1e-12_time_s": float(times[int(tol_state[-1])]),
                "first_gt_1e-12_difference": float(state_diff[tuple(tol_state)]),
                "max_abs_difference": float(np.max(state_diff)),
            },
            "source_code_anchors": {
                "entry_model_overwrite": "experiments/c5_test48_v6/test48_entry_v4.m:503-517",
                "initial_weight_from_runtime_opts": "experiments/position_delayed_prediction_c3_dev72_20261023/run_dl1018_closed_loop.m:666-681",
                "X14_history_and_forward_inference": "experiments/position_delayed_prediction_c3_dev72_20261023/run_dl1018_closed_loop.m:1964-1988",
                "same_event_head_update_and_held_force": "experiments/position_delayed_prediction_c3_dev72_20261023/run_dl1018_closed_loop.m:2028-2103",
                "PCF_filter_input_and_outputs": "experiments/position_delayed_prediction_c3_dev72_20261023/run_dl1018_closed_loop.m:2228-2235",
                "DSSM_feature_equation": "REFERENCE_FIX_FULL72_20261021_022342_313/corrected_reference_training_v1/corrected_pair_eval_v1/sources/local_runtime/position_stage1_model_forward_v2.m:54-64,136",
                "feature_head_output_and_update_equation": "REFERENCE_FIX_FULL72_20261021_022342_313/corrected_reference_training_v1/corrected_pair_eval_v1/sources/local_runtime/position_only_search_head_step.m:12-18",
            },
            "checker_path": str(Path(__file__).resolve()),
            "checker_sha256": sha(Path(__file__).resolve()),
        }
    out = Path(__file__).with_name("V6_FIRST_DSSM_DEV_DIVERGENCE_PEER_v1.json")
    if out.exists():
        raise FileExistsError(out)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": results["status"], "output": str(out), "sha256": sha(out),
                      "different_numeric_arrays": len(results["raw_numeric_log_comparison"]["different_arrays"]),
                      "first_inference_t_s": results["first_ready_event"]["call_time_s"],
                      "state_first_exact_t_s": results["state_divergence"]["first_exact_value_mismatch_time_s"],
                      "state_first_gt_1e-12_t_s": results["state_divergence"]["first_gt_1e-12_time_s"]},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
