"""Fixed-state local gain diagnostic for the pinned A1R/A1T maps.

Reports conditional Jacobians only. It does not replay an allocator or a
closed-loop trajectory.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
from pathlib import Path
from typing import Any

import h5py
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
LOCAL_TASKBOOK_REL = "reports/attitude_cm18_datarepair_20261024/ROOT_LOCAL_GAIN_DIAGNOSTIC_TASKBOOK_v1.json"
LOCAL_TASKBOOK_SHA = "aa873cdbc31c0004bc6d1b3b4123c872b37544105d94838990cda3d8fa1f9b82"
MATH_REL = "reports/attitude_cm18_datarepair_20261024/ROOT_LOCAL_COMPENSATION_GAIN_DERIVATION_v1_ZH.md"
MATH_SHA = "17b022613ed42b50c9542499c3d97fe0e81de3651218223bb6a7c065ab728181"
MAP_SOURCE_REL = "reports/attitude_cm18_datarepair_20261024/root_same_input_map_comparison_v1.py"
MAP_SOURCE_SHA = "3522198f93110c1301076505b0a39e75a78a0c67fe316c1ed7ea61d8ac5dbdb1"
MODEL_REL = "experiments/attitude_cm18_a1_20261024/model_cm18_v1.py"
MODEL_SHA = "ad32c4f97bf96c63172547c944d80c45062502f1062b774934e0f7a868720cf6"
A1R_REL = "experiments/attitude_cm18_datarepair_20261024/postselection_a1r_v1/deployment_parameters_v1.json"
A1R_SHA = "b3ab7a3d99df639d4cc0a10ec2b6fcd4622388f58c90c25424e472164ef38d23"
A1T_REL = "experiments/attitude_cm18_datarepair_20261024/postselection_a1t_v1/deployment_parameters_v1.json"
A1T_SHA = "dd5375623cf47abed1db1e620a7d00358aff71b5985ead13e88ba05218952b42"
EVENTS = 1999
TRANSITIONS = 20000
D_MAX = np.array([45.0, 45.0, 4.7124], dtype=np.float64)
ALPHA_COLUMNS = np.arange(3, 6)
FD_ORDINALS = (0, 499, 999, 1499, 1998)
WINDOWS = {"ALL_0_20": (0.0, 20.0), "PRE_0_5": (0.0, 5.0), "POST_5_20": (5.0, 20.0)}


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def analytic_forward_and_jacobian(x_raw: np.ndarray, p: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    """Return physical y and dy/d(raw alphaBS), with output-by-input axes."""
    x = np.asarray(x_raw, dtype=np.float64)
    require(x.ndim == 2 and x.shape[1] == 18 and np.isfinite(x).all(), "X18 must be finite (N,18)")
    mean = np.asarray(p["input_mean"], dtype=np.float64)
    std = np.asarray(p["input_std"], dtype=np.float64)
    axis_rms = np.asarray(p["train_axis_rms_rad_s2"], dtype=np.float64)
    w1, b1 = np.asarray(p["W1"], dtype=np.float64), np.asarray(p["b1"], dtype=np.float64)
    w2, b2 = np.asarray(p["W2"], dtype=np.float64), np.asarray(p["b2"], dtype=np.float64)
    w3, b3 = np.asarray(p["W3"], dtype=np.float64), np.asarray(p["b3"], dtype=np.float64)
    require(mean.shape == std.shape == (18,) and axis_rms.shape == (3,), "bad normalizer/output scale shape")
    require(w1.shape == (32, 18) and b1.shape == (32,) and w2.shape == (32, 32)
            and b2.shape == (32,) and w3.shape == (24, 32) and b3.shape == (24,), "bad network parameter shape")
    require(np.isfinite(np.concatenate((mean, std, axis_rms, w1.ravel(), b1, w2.ravel(), b2, w3.ravel(), b3))).all(),
            "non-finite model parameter")
    require(np.all(std >= 1e-6) and np.all(axis_rms > 0), "invalid canonical normalizer/output scale")

    xn = (x - mean) / std
    h1 = np.tanh(xn @ w1.T + b1)
    h2 = np.tanh(h1 @ w2.T + b2)
    flat = h2 @ w3.T + b3
    coefficients = flat.reshape((-1, 3, 8), order="C")
    basis = np.concatenate((x[:, 11:15] / 2.0, x[:, 7:11]), axis=1)
    y = np.einsum("nij,nj->ni", coefficients, basis) * axis_rms

    dh1 = (1.0 - h1 * h1)[:, :, None] * (w1[:, ALPHA_COLUMNS] / std[ALPHA_COLUMNS])[None, :, :]
    dh2 = (1.0 - h2 * h2)[:, :, None] * np.einsum("ij,njk->nik", w2, dh1)
    dflat = np.einsum("ij,njk->nik", w3, dh2)
    dcoefficients = dflat.reshape((-1, 3, 8, 3), order="C")
    dy_dalpha = axis_rms[None, :, None] * np.einsum("nijk,nj->nik", dcoefficients, basis)
    require(np.isfinite(y).all() and np.isfinite(dy_dalpha).all(), "non-finite forward/Jacobian")
    return y, dy_dalpha


def check_central_differences(x: np.ndarray, jy: np.ndarray, p: dict[str, Any], model: Any) -> dict[str, Any]:
    maximum = 0.0
    checks = 0
    for ordinal in FD_ORDINALS:
        base = x[ordinal]
        numeric = np.empty((3, 3), dtype=np.float64)
        for column, feature in enumerate(ALPHA_COLUMNS):
            h = 1e-4 * max(1.0, abs(float(base[feature])))
            plus, minus = base.copy(), base.copy()
            plus[feature] += h
            minus[feature] -= h
            yp = model.forward(plus, p)["physical_output_rad_s2"]
            ym = model.forward(minus, p)["physical_output_rad_s2"]
            numeric[:, column] = (yp - ym) / (2.0 * h)
        error = np.abs(jy[ordinal] - numeric)
        maximum = max(maximum, float(error.max()))
        require(np.allclose(jy[ordinal], numeric, atol=1e-6, rtol=1e-4),
                f"central-difference Jacobian mismatch at event ordinal {ordinal}")
        checks += 1
    return {"event_ordinals_zero_based": list(FD_ORDINALS), "component_checks": checks * 9,
            "max_abs_error": maximum, "atol": 1e-6, "rtol": 1e-4}


def matrix_summary(matrices: np.ndarray, target: np.ndarray, singular_values: bool = False) -> dict[str, Any]:
    a = np.asarray(matrices, dtype=np.float64)
    require(a.ndim == 3 and a.shape[1:] == (3, 3) and a.shape[0] > 0 and np.isfinite(a).all(),
            "matrix summary requires finite (N,3,3)")
    t = np.asarray(target, dtype=np.float64)
    delta = a - t
    fro = np.linalg.norm(delta, ord="fro", axis=(1, 2))
    out: dict[str, Any] = {
        "count": int(a.shape[0]),
        "mean_matrix": a.mean(axis=0).tolist(),
        "mean_delta_matrix": delta.mean(axis=0).tolist(),
        "mean_frobenius_delta": float(fro.mean()),
        "rms_frobenius_delta": float(np.sqrt(np.mean(fro * fro))),
        "max_frobenius_delta": float(fro.max()),
    }
    if singular_values:
        sv = np.linalg.svd(a, compute_uv=False)
        out.update({
            "singular_value_min_global": float(sv.min()),
            "singular_value_max_global": float(sv.max()),
            "mean_sigma_min": float(sv[:, -1].mean()),
            "mean_sigma_max": float(sv[:, 0].mean()),
        })
    return out


def scene_diagnostic(scene_id: str, helper: Any, taskbook: dict[str, Any], aggregate: dict[str, Any],
                     models: dict[str, Any], model: Any) -> dict[str, Any]:
    task_matches = [r for r in taskbook["inputs"]["scenes"] if r["scene_id"] == scene_id]
    agg_matches = [r for r in aggregate["per_scene"] if r["scene_id"] == scene_id]
    require(len(task_matches) == len(agg_matches) == 1, f"scene not uniquely pinned: {scene_id}")
    task_row, agg_row = task_matches[0], agg_matches[0]
    # Reuse the already reviewed input/raw/report identity and deployment parity path.
    map_check = helper.run_scene(scene_id, taskbook, aggregate, models["A1R"], models["A1T"], model)
    require(map_check["status"] == "PASS_SINGLE_SCENE_DIAGNOSTIC", f"same-input gate failed: {scene_id}")
    report = helper.read_json(helper.repo_file(task_row["report_path"], task_row["report_sha256"]))
    raw_path = helper.repo_file(task_row["raw_path"], task_row["raw_sha256"])
    events = report["event_records"]
    require(report["status"] == "PASS_SINGLE_SCENE_ONLY" and len(events) == EVENTS,
            f"decomposition report is incomplete: {scene_id}")
    with h5py.File(raw_path, "r") as raw:
        event_flag = helper.h5_numeric(raw, "log/cm18_event_flag").reshape(-1) != 0
        raw_input = helper.h5_numeric(raw, "log/cm18_event_input_18")
    rows = np.flatnonzero(event_flag)
    require(event_flag.shape == (TRANSITIONS,) and raw_input.shape == (TRANSITIONS, 18)
            and np.array_equal(rows, np.arange(10, TRANSITIONS, 10)) and rows.size == EVENTS,
            f"raw event input layout mismatch: {scene_id}")
    x = raw_input[rows]
    event_time = np.asarray([r["time_s"] for r in events], dtype=np.float64)
    event_index = np.asarray([r["plant_index"] for r in events], dtype=np.int64)
    require(np.array_equal(event_index, np.arange(11, 20000, 10, dtype=np.int64))
            and np.max(np.abs(event_time - (event_index - 1) * 0.001)) <= 1e-12,
            f"event timing/index mismatch: {scene_id}")
    beta = np.asarray([r["beta"] for r in events], dtype=np.float64)
    g = np.asarray([r["G_row_major"] for r in events], dtype=np.float64).reshape(EVENTS, 3, 3)
    require(np.isfinite(beta).all() and np.all(beta > 0.0) and np.isfinite(g).all(),
            f"invalid beta/G: {scene_id}")
    rank = np.asarray([np.linalg.matrix_rank(q) for q in g])
    require(np.all(rank == 3), f"G is not numerically full-rank: {scene_id}")
    inv_g = np.linalg.solve(g, np.broadcast_to(np.eye(3), g.shape))
    require(np.isfinite(inv_g).all(), f"non-finite inverse G: {scene_id}")
    condition_g = np.linalg.cond(g)

    by_model: dict[str, tuple[np.ndarray, np.ndarray, dict[str, Any]]] = {}
    fd_checks: dict[str, Any] = {}
    for name in ("A1R", "A1T"):
        params = models[name]["parameters"]
        y, jy = analytic_forward_and_jacobian(x, params)
        fwd = model.forward(x, params)["physical_output_rad_s2"]
        require(np.max(np.abs(y - fwd)) <= 1e-10, f"analytic forward differs from pinned model: {scene_id}/{name}")
        fd_checks[name] = check_central_differences(x, jy, params, model)
        by_model[name] = (y, jy, params)

    a1t_y = by_model["A1T"][0]
    report_y = np.asarray([r["raw_output"] for r in events], dtype=np.float64)
    require(report_y.shape == (EVENTS, 3) and np.max(np.abs(a1t_y - report_y)) <= 1e-9,
            f"A1T map output no longer matches pinned decomposition: {scene_id}")
    ideal_raw = (np.eye(3)[None, :, :] - inv_g) / beta[:, None, None]
    dmax = D_MAX[None, :]
    windows: dict[str, Any] = {}
    for window, (left, right) in WINDOWS.items():
        mask = (event_time >= left) & (event_time < right)
        require(int(mask.sum()) == {"ALL_0_20": 1999, "PRE_0_5": 499, "POST_5_20": 1500}[window],
                f"unexpected {window} event count: {scene_id}")
        models_out: dict[str, Any] = {}
        for name, (y, jy, _) in by_model.items():
            kink_by_axis = np.abs(np.abs(y) - dmax) <= 1e-9
            kink_event = np.any(kink_by_axis, axis=1)
            dclip = (np.abs(y) < dmax).astype(np.float64)
            identity = np.broadcast_to(np.eye(3), (EVENTS, 3, 3))
            unconstrained = np.einsum("nij,njk->nik", g, identity - beta[:, None, None] * jy)
            applied = np.einsum("nij,njk->nik", g, identity - beta[:, None, None] * dclip[:, :, None] * jy)
            raw_j = matrix_summary(jy[mask], np.zeros((3, 3)))
            raw_delta = matrix_summary(jy[mask], ideal_raw[mask])
            uresp = matrix_summary(unconstrained[mask], np.eye(3), singular_values=True)
            applied_mask = mask & ~kink_event
            aresp = matrix_summary(applied[applied_mask], np.eye(3), singular_values=True) if np.any(applied_mask) else None
            models_out[name] = {
                "raw_jacobian": raw_j,
                "raw_jacobian_minus_ideal": raw_delta,
                "unconstrained_response": uresp,
                "applied_response": aresp,
                "applied_response_excluded_clip_kink_events": int(np.count_nonzero(mask & kink_event)),
                "clip_kink_count_by_axis": np.count_nonzero(kink_by_axis[mask], axis=0).astype(int).tolist(),
                "strict_clip_count_by_axis": np.count_nonzero(np.abs(y[mask]) > dmax, axis=0).astype(int).tolist(),
            }
        windows[window] = {"event_count": int(mask.sum()), "models": models_out}

    suffix = re.search(r"W(\d+)$", scene_id)
    require(suffix is not None, f"scene wind suffix missing: {scene_id}")
    return {
        "scene_id": scene_id,
        "task": task_row["task"],
        "category": task_row["category"],
        "wind_id": int(suffix.group(1)),
        "event_count": EVENTS,
        "timing": {"event_index_first": int(event_index[0]), "event_index_last": int(event_index[-1]),
                   "first_time_s": float(event_time[0]), "last_time_s": float(event_time[-1])},
        "G_condition": {"minimum_sigma_min_G": float(np.linalg.svd(g, compute_uv=False)[:, -1].min()),
                        "maximum_condition_G": float(condition_g.max())},
        "finite_difference_checks": fd_checks,
        "A1T_forward_vs_report_max_abs": float(np.max(np.abs(a1t_y - report_y))),
        "windows": windows,
    }


def equal_scene_summary(scene_rows: list[dict[str, Any]], window: str) -> dict[str, Any]:
    result: dict[str, Any] = {"scene_count": len(scene_rows), "models": {}}
    for name in ("A1R", "A1T"):
        per_scene = [r["windows"][window]["models"][name] for r in scene_rows]
        model_out: dict[str, Any] = {}
        for metric in ("raw_jacobian", "raw_jacobian_minus_ideal", "unconstrained_response", "applied_response"):
            items = [x[metric] for x in per_scene if x[metric] is not None]
            if not items:
                model_out[metric] = None
                continue
            entry: dict[str, Any] = {
                "valid_scene_count": len(items),
                "equal_scene_mean_matrix": np.mean([x["mean_matrix"] for x in items], axis=0).tolist(),
                "equal_scene_mean_delta_matrix": np.mean([x["mean_delta_matrix"] for x in items], axis=0).tolist(),
                "mean_of_scene_mean_frobenius_delta": float(np.mean([x["mean_frobenius_delta"] for x in items])),
                "mean_of_scene_rms_frobenius_delta": float(np.mean([x["rms_frobenius_delta"] for x in items])),
                "maximum_scene_max_frobenius_delta": float(np.max([x["max_frobenius_delta"] for x in items])),
            }
            if "singular_value_min_global" in items[0]:
                entry.update({
                    "minimum_singular_value_min": float(min(x["singular_value_min_global"] for x in items)),
                    "maximum_singular_value_max": float(max(x["singular_value_max_global"] for x in items)),
                    "equal_scene_mean_sigma_min": float(np.mean([x["mean_sigma_min"] for x in items])),
                    "equal_scene_mean_sigma_max": float(np.mean([x["mean_sigma_max"] for x in items])),
                })
            model_out[metric] = entry
        model_out["clip_kink_events_sum"] = int(sum(x["applied_response_excluded_clip_kink_events"] for x in per_scene))
        model_out["clip_kink_count_by_axis_sum"] = np.sum([x["clip_kink_count_by_axis"] for x in per_scene], axis=0).astype(int).tolist()
        model_out["strict_clip_count_by_axis_sum"] = np.sum([x["strict_clip_count_by_axis"] for x in per_scene], axis=0).astype(int).tolist()
        result["models"][name] = model_out
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene-id", default="DL1018_DEV_T1_C01_W15", help="one pinned scene; default is the first review case")
    parser.add_argument("--all-scenes", action="store_true", help="after first-scene review, summarize all 12 pinned scenes")
    args = parser.parse_args()

    helper_path = (ROOT / MAP_SOURCE_REL).resolve(strict=True)
    require(helper_path.is_relative_to(ROOT.resolve()) and helper_path.is_file()
            and file_sha256(helper_path).lower() == MAP_SOURCE_SHA.lower(),
            "pinned same-input source path/SHA mismatch")
    raw_helper = importlib.util.spec_from_file_location("cm18_same_input_helpers", helper_path)
    require(raw_helper is not None and raw_helper.loader is not None, "cannot import pinned same-input source")
    helper = importlib.util.module_from_spec(raw_helper)
    raw_helper.loader.exec_module(helper)
    helper.repo_file(MAP_SOURCE_REL, MAP_SOURCE_SHA)
    taskbook = helper.read_json(helper.repo_file(helper.TASKBOOK_REL, helper.TASKBOOK_SHA))
    helper.repo_file(MATH_REL, MATH_SHA)
    local_taskbook = helper.read_json(helper.repo_file(LOCAL_TASKBOOK_REL, LOCAL_TASKBOOK_SHA))
    require(local_taskbook.get("schema") == "ROOT_LOCAL_GAIN_DIAGNOSTIC_TASKBOOK_V1"
            and local_taskbook.get("decision") == "IMPLEMENTATION_ONLY_ROOT_REVIEW_BEFORE_EXECUTION",
            "unexpected local-gain taskbook")
    require(local_taskbook.get("input_taskbook_path") == helper.TASKBOOK_REL
            and local_taskbook.get("input_taskbook_sha256") == helper.TASKBOOK_SHA
            and local_taskbook.get("math_path") == MATH_REL and local_taskbook.get("math_sha256") == MATH_SHA,
            "local-gain input taskbook identity mismatch")
    input_pins = taskbook.get("inputs", {})
    require(input_pins.get("A1R_deployment_path") == A1R_REL
            and input_pins.get("A1R_deployment_sha256") == A1R_SHA
            and input_pins.get("A1T_deployment_path") == A1T_REL
            and input_pins.get("A1T_deployment_sha256") == A1T_SHA,
            "input taskbook deployment pins mismatch")
    aggregate = helper.read_json(helper.repo_file(helper.AGGREGATE_REL, helper.AGGREGATE_SHA))
    a1r = helper.read_json(helper.repo_file(A1R_REL, A1R_SHA))
    a1t = helper.read_json(helper.repo_file(A1T_REL, A1T_SHA))
    model_path = helper.repo_file(MODEL_REL, MODEL_SHA)
    model = helper.load_model_module(model_path)
    require(a1r.get("schema") == "CM18_A1R_DEPLOYMENT_PARAMETERS_V1"
            and a1t.get("schema") == "CM18_A1T_DEPLOYMENT_PARAMETERS_V1"
            and int(a1r["identity"]["selected_step"]) == int(a1t["identity"]["selected_step"]) == 40000,
            "unexpected frozen deployment identity")
    require(aggregate.get("status") == "COMPLETE_ALL12_DIAGNOSTIC_NO_WINNER_GATE",
            "pinned decomposition aggregate is incomplete")
    models = {"A1R": a1r, "A1T": a1t}
    if args.all_scenes:
        scene_ids = [r["scene_id"] for r in taskbook["inputs"]["scenes"]]
    else:
        scene_ids = [args.scene_id]
    scene_results = [scene_diagnostic(sid, helper, taskbook, aggregate, models, model) for sid in scene_ids]
    if args.all_scenes:
        groups: dict[str, list[dict[str, Any]]] = {
            "ALL": scene_results,
            "HF_W09_W14": [r for r in scene_results if 9 <= r["wind_id"] <= 14],
            "W15": [r for r in scene_results if r["wind_id"] == 15],
        }
        for task in ("T1", "T2", "T3"):
            groups[f"TASK_{task}"] = [r for r in scene_results if r["task"] == task]
        summaries = {g: {w: equal_scene_summary(rows, w) for w in WINDOWS} for g, rows in groups.items()}
        result = {"schema": "ROOT_LOCAL_GAIN_DIAGNOSTIC_ALL12_V1", "status": "PASS_ALL12_LOCAL_DIAGNOSTIC",
                  "scope": {"plant_calls": 0, "engine_calls": 0, "training_steps": 0, "TEST_access": False},
                  "per_scene": scene_results, "equal_scene_groups": summaries}
        filename = "ALL12.json"
    else:
        result = {"schema": "ROOT_LOCAL_GAIN_DIAGNOSTIC_SCENE_V1", "status": "PASS_SINGLE_SCENE_LOCAL_DIAGNOSTIC",
                  "scope": {"plant_calls": 0, "engine_calls": 0, "training_steps": 0, "TEST_access": False},
                  "scene": scene_results[0]}
        filename = f"{args.scene_id}.json"
    result["identity"] = {"taskbook_path": LOCAL_TASKBOOK_REL, "taskbook_sha256": LOCAL_TASKBOOK_SHA,
                          "math_path": MATH_REL, "math_sha256": MATH_SHA,
                          "same_input_source_path": MAP_SOURCE_REL, "same_input_source_sha256": MAP_SOURCE_SHA,
                          "model_source_path": MODEL_REL, "model_source_sha256": MODEL_SHA,
                          "A1R_deployment_path": A1R_REL, "A1R_deployment_sha256": A1R_SHA,
                          "A1T_deployment_path": A1T_REL, "A1T_deployment_sha256": A1T_SHA}
    result["identity"].update({"source_path": Path(__file__).resolve().relative_to(ROOT.resolve()).as_posix(),
                               "source_sha256": file_sha256(Path(__file__).resolve())})
    result["interpretation"] = (
        "Jacobians condition on each recorded X18 while omega, thrust, morphology, beta, and past requested-torque "
        "history remain fixed. The applied response omits only events at a clip kink. These one-step local maps "
        "are not full allocator or discrete closed-loop stability evidence."
    )
    payload = json.dumps(result, indent=2, allow_nan=False).encode("utf-8") + b"\n"
    require(len(payload) <= 1024**3, "diagnostic output exceeds the 1 GiB taskbook budget")
    out_dir = ROOT / "reports/attitude_cm18_datarepair_20261024/local_gain_diagnostic_v1"
    out_path = out_dir / filename
    require(not out_path.exists(), f"refusing to overwrite {out_path}")
    out_dir.mkdir(parents=True, exist_ok=True)
    with out_path.open("xb") as stream:
        stream.write(payload)
    print(json.dumps({"status": result["status"], "output": out_path.relative_to(ROOT).as_posix(),
                      "source_sha256": helper.sha256(Path(__file__).resolve())}, ensure_ascii=False))


if __name__ == "__main__":
    main()
