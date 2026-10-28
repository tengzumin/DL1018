"""Lead-aware replay plus the frozen SO(3)/Q score for the single TRAIN run."""
from pathlib import Path
import hashlib
import importlib.util
import json
import sys

import h5py
import numpy as np

HERE = Path(__file__).resolve().parent
SCENE = "DL1018_DEV_T1_C00_W03"
TOL = 2e-10
SCORE_SOURCE = HERE.parents[2] / "experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_full72_v1/audits/score_full72_candidate_v1.py"
CONSTANTS = HERE.parents[2] / "experiments/dl_attitude_replacement_20261026/mlp15_composite_dev_v3/RELEASE.json"


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def data(log, name):
    return np.asarray(log[name][()], dtype=np.float64).T


def maxerr(x, y):
    return float(np.max(np.abs(np.asarray(x) - np.asarray(y))))


def main():
    sys.path.insert(0, str(HERE / "parity"))
    from helper_parity_v1 import expected

    release = read(HERE / "RELEASE.json")
    lock_path = HERE / "SOURCE_LOCK_SINGLE_v2.json"
    lock = read(lock_path)
    assert release["schema"] == "DL1018_CAUSAL_N4_LEAD_GATE_SINGLE_CALL_V1"
    assert release["fixed_scene_id"] == SCENE and sha(lock_path) == release["source_lock_sha256"]
    for item in lock["files"]:
        path = Path(item["path"])
        assert path.is_file() and sha(path) == item["sha256"], f"Locked source changed: {path}"

    attempt = HERE / "runs" / SCENE / "attempt_01"
    raw, status_path = attempt / "raw_run.mat", attempt / "run_status.json"
    status = read(status_path)
    assert status["scene_id"] == SCENE and status["Plant_calls"] == 1 and status["raw_sha256"] == sha(raw)
    binding = read(HERE / "bindings" / f"{SCENE}.json")

    spec = importlib.util.spec_from_file_location("frozen_score", SCORE_SOURCE)
    scorer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scorer)
    constants = read(CONSTANTS)
    paths = {
        "candidate": raw,
        "B": Path(binding["b72_scoring_raw_path"]),
        "C5": Path(binding["c5_raw_path"]),
        "parent": Path(binding["parent_raw_path"]),
    }
    scores = {name: scorer.score_raw(path, float(constants["gravity_mps2"]), float(constants["max_tilt_rad"]))
              for name, path in paths.items()}

    with h5py.File(raw, "r") as f:
        log = f["log"]
        t = data(log, "transition_time").reshape(-1)
        event = data(log, "stage1_position_event").reshape(-1).astype(bool)
        valid = data(log, "stage1_position_event_inference_valid").reshape(-1).astype(bool)
        before = data(log, "stage1_position_event_applied_acceleration_mps2")
        u = data(log, "stage1_position_applied_static_n4_event_input_mps2")[event]
        n4 = data(log, "stage1_position_applied_static_n4_event_output_raw_mps2")[event]
        applied = data(log, "stage1_position_applied_static_n4_event_output_applied_mps2")[event]
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
    rows = [[float(tt[i]), 1, *u[i].tolist()] for i in range(len(tt))]
    replay = np.asarray(expected(rows), dtype=np.float64)
    replay_out, replay_n4, replay_lead = replay[:, 5:8], replay[:, 8:11], replay[:, 11:14]
    replay_diag = replay[:, 14:19]
    replay_clips = replay[:, 19:22].astype(bool)
    sample_idx = np.cumsum(event) - 1
    replay_hold = np.zeros_like(held)
    replay_hold[sample_idx >= 0] = replay_out[sample_idx[sample_idx >= 0]]
    event_before = before[event]
    parent_input = np.where(valid[event, None], event_before, 0.0)
    errors = {
        "input_from_C5": maxerr(u, parent_input),
        "n4_raw": maxerr(n4, replay_n4),
        "gate_diagnostics": maxerr(gate, replay_diag),
        "lead_gated_event_output": maxerr(applied, replay_out),
        "held_1ms": maxerr(held, replay_hold),
        "position_bs_step_argument": maxerr(force, residual_arg),
        "reported_compensation": maxerr(residual_arg, actual_force),
    }
    checks = {
        "event_count_and_warmup": bool(t.size == 20000 and event.sum() == 1999 and valid[event].sum() == 1968 and
                                        np.all(~valid[event][:31]) and np.all(u[:31] == 0) and
                                        np.allclose(tt, np.arange(1, 2000) * .01, atol=2e-8, rtol=0)),
        "lead_aware_action_replay": bool(max(errors.values()) <= TOL and np.array_equal(clips, replay_clips)),
        "no_extra_position_gru": bool(extra == 0 and extra_events == 0),
        "startup_gate_zero": bool(np.all(replay_diag[tt < 2, 3:] == 0)),
        "stable_20k_one_call": bool(status["state"] == "COMPLETED" and status["status_value"] == "STABLE" and
                                     status["transitions"] == 20000 and status["state_samples"] == 20001 and
                                     status["first_plant_step_marker_created"]),
        "Q_over_C5_le_1p05": bool(scores["candidate"]["Q_m"] <= 1.05 * scores["C5"]["Q_m"]),
        "safety_counters_zero": bool(all(v == 0 for v in scores["candidate"]["safety"].values())),
        "high_task_le_B": bool(SCENE.endswith("_T1_C00_W03") or
                                scores["candidate"]["task_SO3_rad"] <= scores["B"]["task_SO3_rad"]),
        "low_gate_zero_identity": bool(not SCENE.endswith("_T1_C00_W03") or
                                       (np.all(replay_diag[:, 4] == 0) and
                                        maxerr(applied, np.clip(u, -3, 3)) <= TOL)),
    }
    score_summary = {name: {k: value[k] for k in ("Q_m", "task_SO3_rad", "inner_SO3_rad", "safety")}
                     for name, value in scores.items()}
    use = tt >= 2
    result = {
        "status": "PASS_LEAD_SINGLE_TRAIN_SCENE" if all(checks.values()) else "FAIL_LEAD_SINGLE_TRAIN_SCENE",
        "scene_id": SCENE,
        "source_split": "TRAIN_C5_24 (canonical ID prefix DEV)",
        "Plant_calls": 1,
        "raw_sha256": sha(raw),
        "run_status_sha256": sha(status_path),
        "release_sha256": sha(HERE / "RELEASE.json"),
        "source_lock_sha256": sha(lock_path),
        "lead_coefficients": {"b": [17 / 7, -15 / 7], "a": [1, -5 / 7], "sample_rate_hz": 100},
        "scores": score_summary,
        "Q_over_C5": scores["candidate"]["Q_m"] / scores["C5"]["Q_m"],
        "criteria": checks,
        "action_chain_max_errors": errors,
        "event_output_clip_count": int(clips.sum()),
        "gate": {"event_count": int(event.sum()), "ready_event_count": int(valid[event].sum()),
                 "Ebp_mean": float(np.mean(replay_diag[use, 0])),
                 "Elo_mean": float(np.mean(replay_diag[use, 1])),
                 "ratio_mean": float(np.mean(replay_diag[use, 2])),
                 "g_mean": float(np.mean(replay_diag[use, 4])),
                 "g_min": float(np.min(replay_diag[:, 4])), "g_max": float(np.max(replay_diag[:, 4])),
                 "first_g_above_0p1_s": float(tt[np.flatnonzero((tt >= 2) & (replay_diag[:, 4] > .1))[0]])
                 if np.any((tt >= 2) & (replay_diag[:, 4] > .1)) else None},
        "lead_output_peak_abs": float(np.max(np.abs(replay_lead))),
        "score_source_sha256": sha(SCORE_SOURCE),
        "score_constants_sha256": sha(CONSTANTS),
        "parity_reference_sha256": sha(HERE / "parity" / "helper_parity_v1.py"),
        "scorer_sha256": sha(Path(__file__)),
        "TEST_read": False,
        "VAL_read": False,
        "inertia_reconstruction_enabled": False,
    }
    out = HERE / "SCORE_LEAD_v1.json"
    if out.exists():
        raise RuntimeError("Refusing to overwrite lead score")
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "scene_id": SCENE, "scores": score_summary,
                      "Q_over_C5": result["Q_over_C5"], "action_chain_max_errors": errors,
                      "event_output_clip_count": int(clips.sum()), "criteria": checks}, indent=2))
    if not all(checks.values()):
        raise SystemExit("Lead single-scene score failed; stop further Plant calls")


if __name__ == "__main__":
    main()
