"""Independent arithmetic audit of the saved offline-probe NPZ/JSON only."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
RESULT = HERE / "OFFLINE_INPUT_PROBE_RESULT_v1.json"
ARCHIVE = HERE / "OFFLINE_INPUT_PROBE_ARRAYS_v1.npz"
EXECUTION = HERE / "ROOT_EXECUTION_RECEIPT_v1.json"
RELEASE = HERE / "ROOT_FIT_RELEASE_v1.json"
PARAMETERS = HERE / "PARAMETERS_v1.json"
OUTPUT = HERE / "INDEPENDENT_SAVED_PROBE_AUDIT_v1.json"

EXPECTED = {
    "probe_source_sha256": "84c7af0db511b9ef9121c0af5b9807dafc2553e26324177f513d4583975d93e6",
    "result_sha256": "b4a7e0d5bf3040de07140ec26b2e56f6ff8a43867cb791c2ca566af8eb438fa6",
    "archive_sha256": "3ca0f7bfb303ae04fac92454dece574d4ec8c1966b3cd372c48fa461eb690770",
    "parameters_sha256": "fc9337492ecde5545c826451cfab2d5f715cce06a5b41739ce93a25197899e56",
}
GROUPS = {
    "G0_B7": list(range(7)),
    "G1_B7_u4": list(range(7)) + list(range(7, 11)),
    "G2_B7_z4": list(range(7)) + list(range(11, 15)),
    "G3_B7_z4_u4": list(range(7)) + list(range(11, 15)) + list(range(7, 11)),
    "G4_B7_z4_u4_a3": list(range(7)) + list(range(11, 15)) + list(range(7, 11)) + list(range(15, 18)),
}
MODELS = ["ZERO", *GROUPS]
METRIC_KEYS = (
    "axis_rmse_rad_s2", "physical_vector_rmse_rad_s2", "normalized_vector_rmse",
    "peak_vector_error_rad_s2", "output_amplitude_rms_rad_s2",
    "target_amplitude_rms_rad_s2", "output_peak_rad_s2",
)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def metrics(pred: np.ndarray, target: np.ndarray, target_scale: np.ndarray) -> dict:
    e = pred - target
    return {
        "axis_rmse_rad_s2": np.sqrt(np.mean(e**2, axis=0)),
        "physical_vector_rmse_rad_s2": float(np.sqrt(np.mean(np.sum(e**2, axis=1)))),
        "normalized_vector_rmse": float(np.sqrt(np.mean(np.sum((e / target_scale) ** 2, axis=1)))),
        "peak_vector_error_rad_s2": float(np.max(np.linalg.norm(e, axis=1))),
        "output_amplitude_rms_rad_s2": float(np.sqrt(np.mean(np.sum(pred**2, axis=1)))),
        "target_amplitude_rms_rad_s2": float(np.sqrt(np.mean(np.sum(target**2, axis=1)))),
        "output_peak_rad_s2": float(np.max(np.linalg.norm(pred, axis=1))),
    }


def phi(x: np.ndarray) -> np.ndarray:
    i, j = np.triu_indices(x.shape[1])
    return np.column_stack((np.ones(len(x)), x, x[:, i] * x[:, j]))


def require(ok: bool, message: str) -> None:
    if not ok:
        raise AssertionError(message)


def aggregate(mask: np.ndarray, event_ids: np.ndarray, pred: np.ndarray, target: np.ndarray,
              scale: np.ndarray) -> dict:
    by_scene = []
    for sid in np.unique(event_ids[mask]):
        rows = mask & (event_ids == sid)
        if rows.any():
            by_scene.append(metrics(pred[rows], target[rows], scale))
    require(bool(by_scene), "empty metric group")
    out = {}
    for key in METRIC_KEYS:
        values = np.asarray([row[key] for row in by_scene], dtype=float)
        out[key] = np.mean(values, axis=0).tolist() if values.ndim == 2 else float(values.mean())
    out["normalized_axis_rmse"] = (
        np.asarray(out["axis_rmse_rad_s2"]) / scale
    ).tolist()
    out["scene_count"] = len(by_scene)
    out["event_count"] = int(mask.sum())
    return out


def main() -> None:
    if OUTPUT.exists():
        raise FileExistsError(f"refusing to overwrite {OUTPUT}")
    for path, expected in (
        (RESULT, EXPECTED["result_sha256"]), (ARCHIVE, EXPECTED["archive_sha256"]),
        (PARAMETERS, EXPECTED["parameters_sha256"]),
    ):
        require(sha(path) == expected, f"pinned hash mismatch: {path.name}")

    result = json.loads(RESULT.read_text(encoding="utf-8"))
    execution = json.loads(EXECUTION.read_text(encoding="utf-8"))
    release = json.loads(RELEASE.read_text(encoding="utf-8"))
    require(execution["actual_os_exit_code"] == 0 and execution["actual_closed_form_fit_calls"] == 5,
            "root execution receipt is not a completed five-fit run")
    require(execution["source_sha256"] == EXPECTED["probe_source_sha256"]
            and result["script_sha256"] == EXPECTED["probe_source_sha256"], "probe source identity mismatch")
    require(release["source_sha256"] == EXPECTED["probe_source_sha256"]
            and release["parameters_sha256"] == EXPECTED["parameters_sha256"]
            and release["TEST_access"] is False, "fit release identity/scope mismatch")
    require(result["fit_samples"] == {"stride": 5, "train_rows": 19200}, "unexpected fit-sample count")
    require(result["estimator"]["closed_form_fit_calls"] == 5 and result["estimator"]["optimizer_steps"] == 0,
            "unexpected estimator/optimizer count")

    with np.load(ARCHIVE, allow_pickle=False) as z:
        scene_ids = z["scene_ids"]
        scene_split = z["scene_split"]
        event_ids = z["event_scene_id"]
        event_split = z["event_split"]
        event_condition = z["event_condition"]
        phase = z["phase_code"]
        raw_x = z["features_raw_B7_u4_z4_a3"]
        target = z["target_raw_rad_s2"]
        scale = z["target_scale_train_fit_rms_rad_s2"]
        fit_mask = z["fit_sample_mask"]
        require(len(scene_ids) == 96 and np.count_nonzero(scene_split == "VAL") == 48
                and np.count_nonzero(scene_split == "TRAIN") == 48, "scene counts differ from locked pool")
        require(raw_x.shape == (191904, 18) and target.shape == (191904, 3), "unexpected archive shapes")
        require(len(np.unique(event_ids[event_split == "VAL"])) == 48, "VAL event scene count is not 48")
        fit_rows = (event_split == "TRAIN") & fit_mask
        require(int(fit_rows.sum()) == 19200 and not np.any(fit_mask[event_split == "VAL"]),
                "fit mask is not TRAIN-only at stride 5")
        expected_scale = np.maximum(np.sqrt(np.mean(target[fit_rows] ** 2, axis=0)), 1e-6)
        target_scale_err = float(np.max(np.abs(scale - expected_scale)))
        target_norm_err = float(np.max(np.abs(z["target_normalized_train_rms"] - target / scale)))
        require(target_scale_err <= 1e-12 and target_norm_err <= 1e-12, "target scaling does not match TRAIN fit rows")

        normalizers, normal_equations = {}, {}
        fit_y_normalized = target[fit_rows] / scale
        n_fit = int(fit_rows.sum())
        for name, cols in GROUPS.items():
            x = raw_x[:, cols]
            mean = x[fit_rows].mean(axis=0)
            std = np.maximum(x[fit_rows].std(axis=0), 1e-6)
            saved_mean, saved_std = z[f"feature_mean_{name}"], z[f"feature_std_{name}"]
            saved_normalized = z[f"normalized_features_{name}"]
            normalized_err = float(np.max(np.abs(saved_normalized - (x - saved_mean) / saved_std)))
            mean_err = float(np.max(np.abs(saved_mean - mean)))
            std_err = float(np.max(np.abs(saved_std - std)))
            train_mean_err = float(np.max(np.abs(((x[fit_rows] - saved_mean) / saved_std).mean(axis=0))))
            normalizers[name] = {
                "max_abs_mean_error": mean_err,
                "max_abs_std_error": std_err,
                "max_abs_saved_normalized_feature_error": normalized_err,
                "max_abs_train_normalized_mean": train_mean_err,
            }
            require(max(mean_err, std_err, normalized_err) <= 1e-12, f"feature scaler mismatch: {name}")

            design = phi((x[fit_rows] - saved_mean) / saved_std)
            coef = z[f"coefficients_{name}"]
            penalty = np.ones(design.shape[1]); penalty[0] = 0.0
            residual = ((design.T @ design) / n_fit + 1e-3 * np.diag(penalty)) @ coef
            residual -= (design.T @ fit_y_normalized) / n_fit
            max_abs = float(np.max(np.abs(residual)))
            relative_fro = float(np.linalg.norm(residual) / max(np.linalg.norm((design.T @ fit_y_normalized) / n_fit), 1e-30))
            normal_equations[name] = {
                "design_shape": list(design.shape),
                "coefficient_shape": list(coef.shape),
                "normal_equation_max_abs_residual": max_abs,
                "normal_equation_relative_frobenius_residual": relative_fro,
                "re_solved_or_refit": False,
            }
            require(max_abs <= 1e-8 and relative_fro <= 1e-8, f"stored coefficients fail normal equation: {name}")

        metric_groups = {
            "VAL_ALL": event_split == "VAL",
            "VAL_HOLD": (event_split == "VAL") & (phase == 3),
            "VAL_C00_ALL": (event_split == "VAL") & (event_condition == "C00"),
        }
        saved = result["group_metrics_scene_equal"]
        group_keys = {
            "VAL_ALL": ("split", {"split": "VAL"}),
            "VAL_HOLD": ("phase_code", {"split": "VAL", "phase_code": 3}),
            "VAL_C00_ALL": ("condition", {"split": "VAL", "condition": "C00"}),
        }
        metrics_recomputed = {}
        for group_name, mask in metric_groups.items():
            label, want = group_keys[group_name]
            model_rows = {}
            for model in MODELS:
                if model == "ZERO":
                    pred = z["prediction_ZERO_rad_s2"]
                else:
                    pred = z[f"prediction_{model}_rad_s2"]
                calc = aggregate(mask, event_ids, pred, target, scale)
                stored_rows = [r for r in saved if r["model"] == model and r["group_by"] == label
                               and all(r.get(k) == v for k, v in want.items())]
                require(len(stored_rows) == 1, f"missing/duplicate saved metric row: {group_name}/{model}")
                stored = stored_rows[0]
                require(calc["scene_count"] == stored["scene_count"] and calc["event_count"] == stored["event_count"],
                        f"scene/event count mismatch: {group_name}/{model}")
                errors = {}
                for key in METRIC_KEYS:
                    err = float(np.max(np.abs(np.asarray(calc[key]) - np.asarray(stored[key]))))
                    errors[key] = err
                    require(err <= 1e-10, f"metric mismatch {group_name}/{model}/{key}: {err}")
                calc["stored_metric_max_abs_difference"] = errors
                model_rows[model] = calc
            metrics_recomputed[group_name] = model_rows

        require(metrics_recomputed["VAL_ALL"]["ZERO"]["scene_count"] == 48, "VAL ALL must include 48 scenes")
        require(metrics_recomputed["VAL_C00_ALL"]["ZERO"]["scene_count"] == 3, "VAL C00 must include three scenes")
        axis_diagnostic = {
            model: {
                "physical_axis_rmse_rad_s2": metrics_recomputed["VAL_ALL"][model]["axis_rmse_rad_s2"],
                "normalized_axis_rmse": metrics_recomputed["VAL_ALL"][model]["normalized_axis_rmse"],
                "normalized_vector_rmse": metrics_recomputed["VAL_ALL"][model]["normalized_vector_rmse"],
                "physical_vector_rmse_rad_s2": metrics_recomputed["VAL_ALL"][model]["physical_vector_rmse_rad_s2"],
            }
            for model in ("ZERO", "G2_B7_z4")
        }

        output = {
            "schema": "INDEPENDENT_SAVED_PROBE_AUDIT_V1",
            "scope": "read-only arithmetic audit of saved NPZ/JSON and root execution receipts; no raw/H5/TEST access, no fit/refit",
            "source_sha256": sha(Path(__file__)),
            "probe_source_sha256": EXPECTED["probe_source_sha256"],
            "result_sha256": sha(RESULT),
            "archive_sha256": sha(ARCHIVE),
            "execution_receipt_sha256": sha(EXECUTION),
            "fit_release_sha256": sha(RELEASE),
            "parameters_sha256": sha(PARAMETERS),
            "counts": {
                "scenes_total": int(len(scene_ids)), "train_scenes": int(np.count_nonzero(scene_split == "TRAIN")),
                "val_scenes": int(np.count_nonzero(scene_split == "VAL")), "train_fit_events": n_fit,
                "val_fit_events": int(np.count_nonzero(fit_mask & (event_split == "VAL"))),
            },
            "train_only_scaling": {
                "target_axis_rms_scale_rad_s2": scale.tolist(),
                "target_scale_max_abs_recomputation_error": target_scale_err,
                "target_normalized_array_max_abs_error": target_norm_err,
                "features": normalizers,
            },
            "stored_coefficient_normal_equation_checks": normal_equations,
            "scene_equal_val_metrics": metrics_recomputed,
            "val_axis_diagnostic_zero_vs_G2": axis_diagnostic,
            "fit_calls_repeated": 0,
            "test_accessed": False,
            "raw_or_h5_accessed": False,
        }

    OUTPUT.write_text(json.dumps(output, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"PASS read-only saved-output audit: {OUTPUT.name}")


if __name__ == "__main__":
    main()
