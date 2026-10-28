"""Frozen per-scene and cohort score for the fixed VAL48 N4 batch."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import h5py
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
N4 = HERE.parent / "n4cg_v2"
sys.path.insert(0, str(N4))
from helper_parity_v2 import reference, sha  # noqa: E402

PLAN_PATH = HERE / "BATCH_PLAN_v2.json"
LOCK_PATH = HERE / "SOURCE_LOCK_VAL48_v1.json"
CONTRACT_PATH = HERE / "BATCH_SCORE_CONTRACT_v2.json"
RESULT_PATH = N4 / "THREE_SCENE_RESULT_v2.json"
SCORE_SOURCE = ROOT / "experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_full72_v1/audits/score_full72_candidate_v1.py"
CONSTANTS = ROOT / "experiments/dl_attitude_replacement_20261026/mlp15_composite_dev_v3/RELEASE.json"
TOL = 2e-10


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def data(log, name):
    return np.asarray(log[name][()], dtype=np.float64).T


def maxerr(x, y):
    return float(np.max(np.abs(np.asarray(x) - np.asarray(y))))


def all_finite(value):
    if isinstance(value, dict):
        return all(all_finite(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return all(all_finite(v) for v in value)
    if isinstance(value, (int, float, np.number)) and not isinstance(value, (bool, np.bool_)):
        return bool(np.isfinite(value))
    return True


def import_scorer():
    spec = importlib.util.spec_from_file_location("frozen_full72_score", SCORE_SOURCE)
    scorer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scorer)
    return scorer


def scene_source(scene_id: str, plan_by_id: dict, bindings: dict, prior_by_id: dict):
    entry = plan_by_id[scene_id]
    if entry.get("mode") == "REUSE_EXISTING_RAW_AND_SCORE":
        files = prior_by_id[scene_id]["files"]
        raw = Path(files["raw_run"]["path"])
        status = Path(files["run_status"]["path"])
        score = Path(files["score"]["path"])
        for key, path in (("raw_run", raw), ("run_status", status), ("score", score)):
            if sha(path).lower() != files[key]["sha256"].lower():
                raise RuntimeError(f"reused {key} hash mismatch for {scene_id}")
        return raw, status, read(score), read(Path(entry["binding_path"]))
    binding = read(Path(entry["binding_path"]))
    attempt = binding["candidate_attempt"]
    raw, status = Path(attempt["raw_path"]), Path(attempt["status_path"])
    out = Path(attempt["score_path"])
    if out.exists():
        raise RuntimeError(f"refusing to overwrite score: {out}")
    return raw, status, None, binding


def score_one(scene_id: str, plan: dict, scorer, constants: dict, prior_by_id: dict):
    plan_by_id = {x["scene_id"]: x for x in plan["entries"]}
    raw, status_path, prior_score, binding = scene_source(scene_id, plan_by_id, {}, prior_by_id)
    status = read(status_path)
    if status.get("scene_id") != scene_id or int(status.get("Plant_calls", -1)) != 1:
        raise RuntimeError(f"run status does not identify one call for {scene_id}")
    if status.get("raw_sha256", "").lower() != sha(raw).lower():
        raise RuntimeError(f"raw hash mismatch for {scene_id}")
    if prior_score is not None:
        return prior_score

    comparators = {"B": "b72_scoring", "C5": "c5", "parent": "parent"}
    paths = {"candidate": raw}
    for name, prefix in comparators.items():
        rp = Path(binding[prefix + "_raw_path"])
        sp = Path(binding[prefix + "_status_path"])
        if sha(rp).lower() != binding[prefix + "_raw_sha256"].lower() or \
                sha(sp).lower() != binding[prefix + "_status_sha256"].lower():
            raise RuntimeError(f"{name} source hash mismatch for {scene_id}")
        if read(sp).get("scene_id") != scene_id:
            raise RuntimeError(f"{name} comparator scene mismatch for {scene_id}")
        paths[name] = rp
    scores = {name: scorer.score_raw(path, float(constants["gravity_mps2"]),
                                     float(constants["max_tilt_rad"]))
              for name, path in paths.items()}

    with h5py.File(raw, "r") as f:
        log = f["log"]
        t = data(log, "transition_time").reshape(-1)
        event = data(log, "stage1_position_event").reshape(-1).astype(bool)
        valid = data(log, "stage1_position_event_inference_valid").reshape(-1).astype(bool)
        before = data(log, "stage1_position_event_applied_acceleration_mps2")
        u = data(log, "stage1_position_applied_static_n4_event_input_mps2")[event]
        n4 = data(log, "stage1_position_applied_static_n4_event_output_raw_mps2")[event]
        blend = data(log, "stage1_position_applied_static_n4_event_output_applied_mps2")[event]
        gate = data(log, "stage1_position_causal_n4_gate_diagnostics")[event]
        clips = data(log, "stage1_position_applied_static_n4_event_clip_active")[event].astype(bool)
        held = data(log, "stage1_position_held_applied_acceleration_mps2")
        force = data(log, "stage1_position_held_force_I_N")
        residual_arg = data(log, "stage1_position_injected_force_I_N")
        actual_force = data(log, "position_compensation_applied_force_N")
        state = data(log, "state")
        extra = float(data(log, "stage1_position_residual_gru_enabled").reshape(-1)[0])
        extra_events = float(data(log, "stage1_position_residual_gru_event_count").reshape(-1)[0])
    tt = t[event]
    event_contract = (t.size == 20000 and event.sum() == 1999 and valid[event].sum() == 1968 and
                      np.all(~valid[event][:31]) and np.all(valid[event][31:]) and
                      np.allclose(tt, np.arange(1, 2000) * .01, atol=2e-8, rtol=0))
    if u.shape != (1999, 3) or n4.shape != u.shape or blend.shape != u.shape or gate.shape != (1999, 5):
        event_contract = False
    parent_input = np.where(valid[event, None], before[event], 0.)
    finite = all(np.isfinite(x).all() for x in (u, n4, blend, gate, held, force,
                                                residual_arg, actual_force, state))
    replay_out, replay_n4, replay_diag = reference(u, tt)
    sample_idx = np.cumsum(event) - 1
    replay_hold = np.zeros_like(held)
    replay_hold[sample_idx >= 0] = replay_out[sample_idx[sample_idx >= 0]]
    unclipped = u + replay_diag[:, 4, None] * (replay_n4 - u)
    expected_clips = np.abs(unclipped - replay_out) > 1e-12
    errors = {"input_from_C5": maxerr(u, parent_input), "n4_raw": maxerr(n4, replay_n4),
              "gate_diagnostics": maxerr(gate, replay_diag), "event_output": maxerr(blend, replay_out),
              "held_1ms": maxerr(held, replay_hold), "position_bs_step_argument": maxerr(force, residual_arg),
              "reported_compensation": maxerr(residual_arg, actual_force)}
    safety = scores["candidate"]["safety"]
    safety_clear = all(float(v) == 0 for v in safety.values())
    stable = (status.get("state") == "COMPLETED" and status.get("status_value") == "STABLE" and
              status.get("transitions") == 20000 and status.get("state_samples") == 20001 and
              status.get("first_plant_step_marker_created") is True)
    finite = finite and all_finite(scores)
    fatal = not (stable and safety_clear and finite)
    w = int(scene_id.rsplit("W", 1)[1])
    hf = 9 <= w <= 14
    checks = {
        "event_count_and_warmup": bool(event_contract and np.all(u[:31] == 0)),
        "action_chain_replay_at_2e_10": bool(finite and max(errors.values()) <= TOL and
                                              np.array_equal(clips, expected_clips)),
        "no_extra_position_gru": bool(extra == 0 and extra_events == 0),
        "startup_gate_zero": bool(np.all(gate[tt < 2, 3:] == 0)) if gate.size else False,
        "stable_20k_one_call": bool(stable),
        "Q_over_C5_le_1p05_target": bool(scores["candidate"]["Q_m"] <= 1.05 * scores["C5"]["Q_m"]),
        "safety_counters_zero": bool(safety_clear),
        "HF_W09_W14_task_le_B_target": bool(not hf or scores["candidate"]["task_SO3_rad"] <= scores["B"]["task_SO3_rad"]),
    }
    with h5py.File(paths["parent"], "r") as f:
        parent_state = data(f["log"], "state")
        parent_action = data(f["log"], "stage1_position_held_applied_acceleration_mps2")
    parent_errors = {"state": maxerr(state, parent_state), "held_action": maxerr(held, parent_action)}
    use = tt >= 2
    ratio, g, target = gate[:, 2], gate[:, 4], gate[:, 3]
    switches = lambda v, threshold: int(np.count_nonzero(np.diff((v >= threshold).astype(np.int8))))
    activation = np.flatnonzero(use & (g > .1))
    windows = []
    for lo, hi in ((2, 8), (8, 14), (14, 20)):
        m = (tt >= lo) & (tt < hi)
        windows.append({"time_s": [lo, hi], "ratio_mean": float(np.mean(ratio[m])),
                        "g_mean": float(np.mean(g[m])), "target_mean": float(np.mean(target[m]))})
    result = {
        "schema": "DL1018_CAUSAL_N4_VAL48_SCENE_SCORE_V2",
        "status": "SCORED_FATAL_STOP" if fatal else "SCORED_COMPLETE",
        "fatal_stop": fatal, "scene_id": scene_id, "task": scene_id.split("_")[2],
        "wind_code": f"W{w:02d}", "HF_W09_W14": hf,
        "source_split": "VAL48", "Plant_calls": 1,
        "raw_path": str(raw), "raw_sha256": sha(raw),
        "run_status_path": str(status_path), "run_status_sha256": sha(status_path),
        "scores": scores,
        "ratios": {"candidate_over_C5_Q": scores["candidate"]["Q_m"] / scores["C5"]["Q_m"],
                   "candidate_over_B_Q": scores["candidate"]["Q_m"] / scores["B"]["Q_m"],
                   "candidate_over_B_task": scores["candidate"]["task_SO3_rad"] / scores["B"]["task_SO3_rad"]},
        "criteria": checks, "diagnostic_only_metric_misses": [k for k, v in checks.items() if not v and k not in ("safety_counters_zero", "stable_20k_one_call")],
        "action_chain_max_errors": errors, "parent_pointwise_max_abs_errors": parent_errors,
        "event_output_clip_count": int(clips.sum()), "finite_values": bool(finite),
        "gate": {"event_count": int(event.sum()), "ready_event_count": int(valid[event].sum()),
                 "ratio_mean": float(np.mean(ratio[use])), "ratio_median": float(np.median(ratio[use])),
                 "g_mean": float(np.mean(g[use])), "g_min": float(np.min(g)), "g_max": float(np.max(g)),
                 "g_above_0p1_fraction": float(np.mean(g[use] > .1)),
                 "g_ge_0p5_fraction": float(np.mean(g[use] >= .5)),
                 "first_g_above_0p1_s": float(tt[activation[0]]) if len(activation) else None,
                 "g_0p1_crossings": switches(g[use], .1), "g_0p5_crossings": switches(g[use], .5),
                 "target_0p5_crossings": switches(target[use], .5), "time_windows": windows},
        "score_source_sha256": sha(SCORE_SOURCE), "score_constants_sha256": sha(CONSTANTS),
        "release_sha256": sha(HERE / "RELEASE.json"),
        "source_lock_sha256": sha(LOCK_PATH),
        "TEST_read": False, "VAL_data_read": True, "inertia_reconstruction_enabled": False,
    }
    out = Path(binding["candidate_attempt"]["score_path"])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"scene_id": scene_id, "status": result["status"],
                      "Q_over_C5": result["ratios"]["candidate_over_C5_Q"],
                      "candidate_task": scores["candidate"]["task_SO3_rad"],
                      "B_task": scores["B"]["task_SO3_rad"], "fatal_stop": fatal}, indent=2))
    return result


def summarize(plan: dict, prior_by_id: dict, allow_partial: bool = False):
    plan_by_id = {x["scene_id"]: x for x in plan["entries"]}
    rows = []
    for scene_id in plan["ordered_scene_ids"]:
        entry = plan_by_id[scene_id]
        if entry.get("mode") == "REUSE_EXISTING_RAW_AND_SCORE":
            files = prior_by_id[scene_id]["files"]
            if sha(Path(files["score"]["path"])).lower() != files["score"]["sha256"].lower():
                raise RuntimeError(f"reused score hash mismatch: {scene_id}")
            old = read(Path(files["score"]["path"]))
            w = int(scene_id.rsplit("W", 1)[1])
            row = {
                "scene_id": scene_id, "task": scene_id.split("_")[2],
                "wind_code": f"W{w:02d}", "HF_W09_W14": 9 <= w <= 14,
                "scores": old["scores"], "gate": old.get("gate"),
                "event_output_clip_count": old.get("event_output_clip_count"),
                "criteria": old.get("criteria"),
                "ratios": {
                    "candidate_over_C5_Q": old["scores"]["candidate"]["Q_m"] / old["scores"]["C5"]["Q_m"],
                    "candidate_over_B_Q": old["scores"]["candidate"]["Q_m"] / old["scores"]["B"]["Q_m"],
                    "candidate_over_B_task": old["scores"]["candidate"]["task_SO3_rad"] / old["scores"]["B"]["task_SO3_rad"],
                },
                "fatal_stop": (not bool(old.get("criteria", {}).get("stable_20k_one_call", False)) or
                               not bool(old.get("criteria", {}).get("safety_counters_zero", False))),
            }
        else:
            out = Path(read(Path(entry["binding_path"]))["candidate_attempt"]["score_path"])
            if not out.is_file():
                if allow_partial:
                    continue
                raise RuntimeError(f"missing scene score: {scene_id}")
            row = read(out)
        rows.append(row)

    def agg(group_rows):
        if not group_rows:
            return {"scene_count": 0}
        methods = ("candidate", "B", "C5", "parent")
        out = {"scene_count": len(group_rows), "methods": {}}
        for method in methods:
            out["methods"][method] = {
                key: float(np.mean([r["scores"][method][key] for r in group_rows]))
                for key in ("Q_m", "task_SO3_rad", "inner_SO3_rad")
            }
        out["ratio_of_summed_Q_candidate_over_C5"] = float(
            sum(r["scores"]["candidate"]["Q_m"] for r in group_rows) /
            sum(r["scores"]["C5"]["Q_m"] for r in group_rows))
        out["mean_candidate_over_C5_Q"] = float(np.mean([r["ratios"]["candidate_over_C5_Q"] for r in group_rows]))
        out["median_candidate_over_C5_Q"] = float(np.median([r["ratios"]["candidate_over_C5_Q"] for r in group_rows]))
        out["ratio_of_summed_Q_candidate_over_B"] = float(
            sum(r["scores"]["candidate"]["Q_m"] for r in group_rows) /
            sum(r["scores"]["B"]["Q_m"] for r in group_rows))
        hf = [r for r in group_rows if r.get("HF_W09_W14")]
        out["HF_W09_W14_task_le_B_count"] = sum(
            r["scores"]["candidate"]["task_SO3_rad"] <= r["scores"]["B"]["task_SO3_rad"] for r in hf)
        out["HF_W09_W14_task_le_B_scene_count"] = len(hf)
        return out

    tasks = sorted({r["task"] for r in rows})
    winds = sorted({r["wind_code"] for r in rows})
    grouped = {
        "by_task": {task: agg([r for r in rows if r["task"] == task]) for task in tasks},
        "by_wind": {wind: agg([r for r in rows if r["wind_code"] == wind]) for wind in winds},
        "HF_W09_W14": agg([r for r in rows if r.get("HF_W09_W14")]),
    }
    results = {"schema": "DL1018_CAUSAL_N4_VAL48_BATCH_SCORE_SUMMARY_V2",
               "status": "PARTIAL_DIAGNOSTIC" if len(rows) != 48 else "COMPLETE_VAL48_DIAGNOSTIC",
               "source_split": "VAL48", "scene_count_scored": len(rows), "scene_count_expected": 48,
               "overall": agg(rows), "groups": grouped,
               "safety_fault_scene_count": sum(not all(float(v) == 0 for v in r["scores"]["candidate"]["safety"].values()) for r in rows),
               "fatal_stop_scene_ids": [r["scene_id"] for r in rows if r.get("fatal_stop", False)],
               "scenes": [{"scene_id": r["scene_id"], "task": r["task"], "wind_code": r["wind_code"],
                           "HF_W09_W14": r["HF_W09_W14"], "Q_m": {m:r["scores"][m]["Q_m"] for m in ("candidate","B","C5","parent")},
                           "task_SO3_rad": {m:r["scores"][m]["task_SO3_rad"] for m in ("candidate","B","C5","parent")},
                           "inner_SO3_rad": {m:r["scores"][m]["inner_SO3_rad"] for m in ("candidate","B","C5","parent")},
                           "ratios": r["ratios"], "safety": r["scores"]["candidate"]["safety"],
                           "gate": r.get("gate"), "event_output_clip_count": r.get("event_output_clip_count"),
                           "criteria": r.get("criteria"), "fatal_stop": r.get("fatal_stop", False)} for r in rows],
               "interpretation":"All 48 fixed VAL scenes are evaluation diagnostics; score-target misses are reported without scene selection or parameter changes.",
               "TEST_read":False,"VAL_data_read":True,"inertia_reconstruction_enabled":False}
    out = HERE / "VAL48_SCORE_SUMMARY_v2.json"
    if out.exists():
        raise RuntimeError(f"refusing to overwrite {out}")
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status":results["status"],"scene_count":len(rows),
                      "overall_Q_over_C5":results["overall"].get("ratio_of_summed_Q_candidate_over_C5"),
                      "HF_count":results["groups"]["HF_W09_W14"].get("scene_count"),
                      "HF_task_le_B":results["groups"]["HF_W09_W14"].get("HF_W09_W14_task_le_B_count"),
                      "summary_path":str(out)},indent=2))
    return results


def main(argv):
    if argv in (["--help"], ["-h"]):
        print("usage: score_val48_batch_v2.py --scene <scene_id> | --summary [--partial]")
        return
    plan = read(PLAN_PATH)
    lock = read(LOCK_PATH)
    locked = {str(Path(x["path"]).resolve()).lower(): x["sha256"].lower() for x in lock["files"]}
    for p in (SCORE_SOURCE, CONSTANTS, Path(__file__).resolve()):
        key = str(p.resolve()).lower()
        if key not in locked or sha(p).lower() != locked[key]:
            raise RuntimeError(f"locked scoring source changed: {p}")
    prior_by_id = {}
    if len(argv) == 2 and argv[0] == "--scene":
        scene_id = argv[1]
        if scene_id not in plan["ordered_scene_ids"]:
            raise SystemExit("scene is outside the fixed VAL48 cohort")
        if scene_id in prior_by_id:
            raise SystemExit("reuse scene already has an immutable score")
        scorer = import_scorer()
        scored = score_one(scene_id, plan, scorer, read(CONSTANTS), prior_by_id)
        if scored.get("fatal_stop"):
            raise SystemExit(2)
    elif argv == ["--summary"]:
        summarize(plan, prior_by_id)
    elif argv == ["--summary", "--partial"]:
        summarize(plan, prior_by_id, allow_partial=True)
    else:
        raise SystemExit("usage: score_val48_batch_v2.py --scene <scene_id> | --summary [--partial]")


if __name__ == "__main__":
    main(sys.argv[1:])
