#!/usr/bin/env python3
"""One fixed causal tau=0.5 s washout replay on locked TRAIN24 OOF rows."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "experiments/dl_attitude_replacement_20261028/position_cosine_gru_train24_causal_v1"
SOURCE = DATA_DIR / "task_aware_cv_v1"
NO_DC = DATA_DIR / "teacher_position_balanced_cv_v1"
DC = DATA_DIR / "teacher_position_balanced_dc_penalty_cv_v1"
sys.path.insert(0, str(SOURCE))
sys.path.insert(0, str(NO_DC))

import fit_task_aware_fourfold_v1 as fit  # noqa: E402
from task_aware_common import DATA_PATH, load_locked_inputs, sha256  # noqa: E402
from train_teacher_position_balanced_oof_v1 import scene_metrics  # noqa: E402

TAU_S = 0.5
DT_S = 0.01
THRESHOLDS = {
    "scene_dc_bias_macro_mps2_max": 0.010,
    "one_second_bias_norm_macro_mps2_max": 0.025,
    "frozen_so3_macro_rad_max": 0.054,
    "position_residual_macro_mps2_max": 0.197,
}


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read_oof(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as z:
        return {k: z[k] for k in z.files}


def action_bias(action: np.ndarray, base: np.ndarray, ready: np.ndarray,
                event_time: np.ndarray) -> dict:
    delta = (action - base).astype(np.float64)
    delta[~ready] = 0.0
    r = delta[ready]
    bins = np.floor(event_time).astype(np.int64)
    means = np.stack([delta[bins == b].mean(axis=0) for b in range(20)])
    return {
        "scene_dc_bias_norm_mps2": float(np.linalg.norm(r.mean(axis=0))),
        "one_second_bias_norm_macro_mps2": float(np.mean(np.linalg.norm(means, axis=1))),
        "one_second_bias_norm_max_mps2": float(np.max(np.linalg.norm(means, axis=1))),
        "action_delta_rms_mps2": float(np.sqrt(np.mean(r * r))),
    }


def check_oof_binding(oof: dict[str, np.ndarray], ids: list[str], folds: list[str],
                      ready: np.ndarray, event_time: np.ndarray,
                      target: np.ndarray, base: np.ndarray, label: str) -> None:
    if (oof["scene_ids"].astype(str).tolist() != ids or
            oof["fold_id"].astype(str).tolist() != folds or
            not np.array_equal(oof["ready_mask"].astype(bool), ready) or
            not np.array_equal(oof["event_time_s"].astype(np.float32), event_time) or
            not np.array_equal(oof["target_clip_mps2"].astype(np.float32), target) or
            not np.array_equal(oof["c5_baseline_action_mps2"].astype(np.float32), base)):
        raise RuntimeError(f"{label}: OOF does not bind to exact locked TRAIN24 rows")


def main() -> None:
    out_npz = OUT / "WASHOUT_TAU05_OOF_v1.npz"
    out_json = OUT / "WASHOUT_TAU05_RESULTS_v1.json"
    out_report = OUT / "REPORT_v1.md"
    out_lock = OUT / "SOURCE_LOCK_v1.json"
    if any(p.exists() for p in (out_npz, out_json, out_report, out_lock)):
        raise RuntimeError("Refusing to overwrite washout results")

    bundle = load_locked_inputs()
    data = bundle["arrays"]
    ids = data["scene_ids"].astype(str).tolist()
    if len(ids) != 24 or any(not sid.startswith("DL1018_DEV_") for sid in ids):
        raise RuntimeError("Expected only the 24 locked DEV training scenes")
    ready = data["ready_mask"].astype(bool)
    event_time = data["event_time_s"].astype(np.float32)
    target = data["target_interval_clip_mps2"].astype(np.float32)
    base = np.clip(data["applied_acceleration_event_mps2"].astype(np.float32),
                   -fit.ACTION_LIMIT, fit.ACTION_LIMIT)
    expected_ready = np.broadcast_to(np.arange(1999) >= 31, (24, 1999))
    expected_time = np.broadcast_to(np.arange(1, 2000, dtype=np.float32) * DT_S, (24, 1999))
    if (ready.shape != (24, 1999) or not np.array_equal(ready, expected_ready) or
            not np.allclose(event_time, expected_time, atol=2e-6, rtol=0) or
            not np.array_equal(data["event_index_zero_based"],
                               np.broadcast_to(np.arange(10, 20000, 10), (24, 1999)))):
        raise RuntimeError("Unexpected 100-Hz event timing/readiness")

    no_dc_path = NO_DC / "TEACHER_POSITION_BALANCED_OOF_v1.npz"
    dc_path = DC / "DC_PENALTY_OOF_v1.npz"
    no_dc_lock = json.loads((NO_DC / "TEACHER_POSITION_BALANCED_SOURCE_LOCK_v1.json").read_text(encoding="utf-8"))
    dc_lock = json.loads((DC / "DC_PENALTY_SOURCE_LOCK_v1.json").read_text(encoding="utf-8"))
    if (no_dc_lock.get("dataset_sha256") != sha256(DATA_PATH) or
            no_dc_lock.get("oof_sha256") != file_sha(no_dc_path) or
            dc_lock.get("input_hashes", {}).get("dataset_sha256") != sha256(DATA_PATH) or
            dc_lock.get("oof_sha256") != file_sha(dc_path)):
        raise RuntimeError("An OOF artifact is stale or not bound to locked TRAIN24")
    no_dc = read_oof(no_dc_path)
    dc = read_oof(dc_path)
    folds = data["fold_id"].astype(str).tolist()
    check_oof_binding(no_dc, ids, folds, ready, event_time, target, base, "no-DC")
    check_oof_binding(dc, ids, folds, ready, event_time, target, base, "DC-penalty")

    raw_delta = no_dc["student_delta_mps2"].astype(np.float32)
    if (raw_delta.shape != (24, 1999, 3) or not np.isfinite(raw_delta).all() or
            np.max(np.abs(raw_delta)) > 0.5 + 1e-7 or np.any(raw_delta[~ready] != 0)):
        raise RuntimeError("No-DC OOF student residual violates finite/clip/ready constraints")
    beta = np.clip(event_time / np.float32(fit.BETA_RISE_S), 0.0, 1.0).astype(np.float32)[..., None]
    alpha = np.float32(np.exp(-DT_S / TAU_S))
    one_minus_alpha = np.float32(1.0) - alpha
    washout_delta = np.zeros_like(raw_delta)
    for i in range(24):
        state = np.zeros(3, dtype=np.float32)  # reset at scene start
        for k in range(1999):
            if ready[i, k]:
                state = alpha * state + one_minus_alpha * raw_delta[i, k]
                washout_delta[i, k] = np.clip(raw_delta[i, k] - state, -0.5, 0.5)
    washout_action = np.clip(base + beta * washout_delta, -fit.ACTION_LIMIT,
                             fit.ACTION_LIMIT).astype(np.float32)
    if (not np.isfinite(washout_delta).all() or not np.isfinite(washout_action).all() or
            np.max(np.abs(washout_delta)) > 0.5 + 1e-7 or
            np.any(washout_delta[~ready] != 0) or
            np.max(np.abs(washout_action)) > fit.ACTION_LIMIT + 1e-7):
        raise RuntimeError("Washout output violates clip, ready, or total-action bounds")

    # Confirm the existing no-DC and DC action arrays use the same declared beta/clip path.
    for label, oof in (("no-DC", no_dc), ("DC-penalty", dc)):
        d = oof["student_delta_mps2"].astype(np.float32)
        expected = np.clip(base + beta * np.where(ready[..., None], d, 0.0),
                           -fit.ACTION_LIMIT, fit.ACTION_LIMIT).astype(np.float32)
        error = float(np.max(np.abs(expected - oof["student_action_mps2"].astype(np.float32))))
        if error > 2e-7:
            raise RuntimeError(f"{label}: stored action does not match beta/clip replay ({error})")

    actions = {
        "C5_baseline": base,
        "no_DC_student": no_dc["student_action_mps2"].astype(np.float32),
        "DC_penalty_student": dc["student_action_mps2"].astype(np.float32),
        "tau05_washout_student": washout_action,
    }
    results = {}
    for name, action in actions.items():
        scene = scene_metrics(action, target, ready, ids, bundle["trajectories"])
        per_scene_bias = {sid: action_bias(action[i], base[i], ready[i], event_time[i])
                          for i, sid in enumerate(ids)}
        scene["scene_dc_bias_norm_macro_mps2"] = float(np.mean([
            v["scene_dc_bias_norm_mps2"] for v in per_scene_bias.values()]))
        scene["one_second_bias_norm_macro_mps2"] = float(np.mean([
            v["one_second_bias_norm_macro_mps2"] for v in per_scene_bias.values()]))
        scene["one_second_bias_norm_max_mps2"] = float(np.max([
            v["one_second_bias_norm_max_mps2"] for v in per_scene_bias.values()]))
        scene["per_scene_action_bias"] = per_scene_bias
        results[name] = scene

    w = results["tau05_washout_student"]
    checks = {
        "scene_dc_bias_macro_mps2": w["scene_dc_bias_norm_macro_mps2"] <= THRESHOLDS["scene_dc_bias_macro_mps2_max"],
        "one_second_bias_norm_macro_mps2": w["one_second_bias_norm_macro_mps2"] <= THRESHOLDS["one_second_bias_norm_macro_mps2_max"],
        "frozen_so3_macro_rad": w["task_frozen_SO3_rmse_scene_macro_rad"] <= THRESHOLDS["frozen_so3_macro_rad_max"],
        "position_residual_macro_mps2": w["position_residual_rmse_scene_macro_mps2"] <= THRESHOLDS["position_residual_macro_mps2_max"],
    }
    fold_results = {}
    for fold in sorted(set(folds)):
        ix = [i for i, f in enumerate(folds) if f == fold]
        fold_results[fold] = {
            "scene_count": len(ix),
            "position_residual_macro_mps2": float(np.mean([
                w["per_scene_position_residual_rmse_mps2"][ids[i]] for i in ix])),
            "frozen_so3_macro_rad": float(np.mean([
                w["per_scene_task_frozen_SO3_rmse_rad"][ids[i]] for i in ix])),
            "scene_dc_bias_macro_mps2": float(np.mean([
                w["per_scene_action_bias"][ids[i]]["scene_dc_bias_norm_mps2"] for i in ix])),
            "one_second_bias_norm_macro_mps2": float(np.mean([
                w["per_scene_action_bias"][ids[i]]["one_second_bias_norm_macro_mps2"] for i in ix])),
        }

    payload = {
        "schema": "COSINE_GRU_C5_TRAIN24_CAUSAL_WASHOUT_TAU05_OOF_RESULTS_V1",
        "scope": "Locked TRAIN_C5_24 scene-group OOF only; no VAL/TEST read, no Plant, no inertia reconstruction.",
        "method": {
            "input": "Prior no-DC student_delta_mps2 OOF; already masked to zero when not ready and clipped to +/-0.5 m/s^2.",
            "filter": "Per scene, l[k]=alpha*l[k-1]+(1-alpha)*r[k]; hp[k]=clip(r[k]-l[k],-0.5,+0.5); l starts at zero; warmup rows force zero input/output.",
            "tau_s": TAU_S, "dt_s": DT_S, "alpha_float32": float(alpha),
            "beta": f"clip(event_time_s/{fit.BETA_RISE_S},0,1)",
            "action": "clip(C5_action + beta*washout_delta, -3, +3)",
            "filter_state_reset": "Each scene; no future samples used.",
        },
        "thresholds": THRESHOLDS, "threshold_checks": checks,
        "all_four_thresholds_pass": bool(all(checks.values())),
        "metrics": results, "washout_fold_metrics": fold_results,
        "integrity": {
            "dataset_sha256": sha256(DATA_PATH),
            "no_dc_oof_sha256": file_sha(no_dc_path),
            "dc_penalty_oof_sha256": file_sha(dc_path),
            "no_dc_source_lock_sha256": file_sha(NO_DC / "TEACHER_POSITION_BALANCED_SOURCE_LOCK_v1.json"),
            "dc_source_lock_sha256": file_sha(DC / "DC_PENALTY_SOURCE_LOCK_v1.json"),
            "scene_count": len(ids), "scene_ids": ids,
            "fold_id_by_scene": dict(zip(ids, folds)),
            "ready_rows_per_scene": int(ready.sum(axis=1)[0]),
            "first_ready_event_index_zero_based": int(np.flatnonzero(ready[0])[0]),
            "max_abs_washout_delta_mps2": float(np.max(np.abs(washout_delta))),
            "max_abs_total_action_mps2": float(np.max(np.abs(washout_action))),
        },
        "interpretation_limits": [
            "Position residual is acceleration-target residual (m/s^2), not geometric position error.",
            "Frozen SO(3) is a replay on fixed C5 state/yaw/reference histories, not candidate closed-loop performance.",
            "This is a development replay on previously used TRAIN24 OOF scenes, not an independent validation set.",
        ],
    }
    np.savez_compressed(out_npz, scene_ids=np.asarray(ids), fold_id=np.asarray(folds),
                        ready_mask=ready, event_time_s=event_time, target_clip_mps2=target,
                        c5_baseline_action_mps2=base,
                        source_student_delta_mps2=raw_delta,
                        washout_student_delta_mps2=washout_delta,
                        washout_student_action_mps2=washout_action)
    out_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    lines = [
        "# Fixed tau=0.5 s causal washout TRAIN24 OOF replay", "",
        "- Source: exact 24-scene TRAIN_C5_24 OOF student; fixed four scene-group folds; no retraining.",
        f"- Filter: `alpha=exp(-0.01/0.5)={float(alpha):.10f}`; scene reset; readiness starts at zero-based event 31; original beta rise {fit.BETA_RISE_S:g} s; residual and total action clips retained.",
        "- No VAL/TEST raw, Plant call, or inertia reconstruction.", "",
        "| Method | Position residual macro (m/s²) | Position pooled (m/s²) | Frozen SO(3) macro (rad) | Scene DC bias macro (m/s²) | 1-s bias macro (m/s²) |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name in actions:
        m = results[name]
        lines.append(f"| {name} | {m['position_residual_rmse_scene_macro_mps2']:.6f} | {m['position_residual_rmse_pooled_mps2']:.6f} | {m['task_frozen_SO3_rmse_scene_macro_rad']:.6f} | {m['scene_dc_bias_norm_macro_mps2']:.6f} | {m['one_second_bias_norm_macro_mps2']:.6f} |")
    lines += ["", "## Predeclared thresholds", "",
              f"All four pass: **{all(checks.values())}**", "",
              "| Metric | Limit | Observed | Pass |", "|---|---:|---:|---|",
              f"| Scene DC bias macro (m/s²) | ≤{THRESHOLDS['scene_dc_bias_macro_mps2_max']:.3f} | {w['scene_dc_bias_norm_macro_mps2']:.6f} | {checks['scene_dc_bias_macro_mps2']} |",
              f"| 1-s bias macro (m/s²) | ≤{THRESHOLDS['one_second_bias_norm_macro_mps2_max']:.3f} | {w['one_second_bias_norm_macro_mps2']:.6f} | {checks['one_second_bias_norm_macro_mps2']} |",
              f"| Frozen SO(3) macro (rad) | ≤{THRESHOLDS['frozen_so3_macro_rad_max']:.3f} | {w['task_frozen_SO3_rmse_scene_macro_rad']:.6f} | {checks['frozen_so3_macro_rad']} |",
              f"| Position residual macro (m/s²) | ≤{THRESHOLDS['position_residual_macro_mps2_max']:.3f} | {w['position_residual_rmse_scene_macro_mps2']:.6f} | {checks['position_residual_macro_mps2']} |",
              "", "## Fold-level washout metrics", "",
              "| Fold | Scenes | Position macro (m/s²) | Frozen SO(3) macro (rad) | DC bias macro (m/s²) | 1-s bias macro (m/s²) |",
              "|---|---:|---:|---:|---:|---:|"]
    for fold, m in fold_results.items():
        lines.append(f"| {fold} | {m['scene_count']} | {m['position_residual_macro_mps2']:.6f} | {m['frozen_so3_macro_rad']:.6f} | {m['scene_dc_bias_macro_mps2']:.6f} | {m['one_second_bias_norm_macro_mps2']:.6f} |")
    lines += ["", "## Limits", "",
              "Position residual is acceleration-target residual, not geometric position error. Frozen SO(3) is scored by replaying the candidate action against fixed C5 states/yaw/reference and does not estimate closed-loop state feedback. This is a development replay on previously used TRAIN24 OOF scenes, not an independent validation.", ""]
    out_report.write_text("\n".join(lines), encoding="utf-8")
    lock = {
        "schema": "COSINE_GRU_C5_TRAIN24_CAUSAL_WASHOUT_TAU05_SOURCE_LOCK_V1",
        "dataset_sha256": sha256(DATA_PATH),
        "no_dc_oof_sha256": file_sha(no_dc_path),
        "dc_penalty_oof_sha256": file_sha(dc_path),
        "script_sha256": file_sha(Path(__file__)),
        "results_npz_sha256": file_sha(out_npz),
        "results_json_sha256": file_sha(out_json),
        "results_report_sha256": file_sha(out_report),
        "tau_s": TAU_S, "thresholds": THRESHOLDS,
        "scope": payload["scope"],
    }
    out_lock.write_text(json.dumps(lock, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"metrics": {k: {
        "position_macro_mps2": v["position_residual_rmse_scene_macro_mps2"],
        "position_pooled_mps2": v["position_residual_rmse_pooled_mps2"],
        "frozen_so3_macro_rad": v["task_frozen_SO3_rmse_scene_macro_rad"],
        "scene_dc_bias_macro_mps2": v["scene_dc_bias_norm_macro_mps2"],
        "one_second_bias_macro_mps2": v["one_second_bias_norm_macro_mps2"],
    } for k, v in results.items()}, "threshold_checks": checks}, indent=2), flush=True)


if __name__ == "__main__":
    main()
