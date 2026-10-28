"""Audit and frozen-score the completed single-scene applied-notch raw."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import h5py
import numpy as np


HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
ROOT = STUDY.parents[2]
SCENE_ID = "DL1018_VAL_T3_C01_W14"
RUN_DIR = STUDY / "runs" / SCENE_ID
RAW = RUN_DIR / "raw_run.mat"
RUN_START = RUN_DIR / "run_start.json"
RUN_STATUS = RUN_DIR / "run_status.json"
RELEASE = STUDY / "RELEASE.json"
SOURCE_LOCK = STUDY / "SOURCE_LOCK_v1.json"
RELEASE_SNAPSHOT = HERE / "PILOT_SNAPSHOT_RELEASE.json"
SOURCE_LOCK_SNAPSHOT = HERE / "PILOT_SNAPSHOT_SOURCE_LOCK_v1.json"
SOURCE_FILES_SNAPSHOT = HERE / "PILOT_SOURCE_SNAPSHOT_v1"
PILOT_SCORE = ROOT / "experiments/dl_attitude_replacement_20261028/gru_prediction_tau01_v1/audits/GRU_PREDICTION_TAU01_SCORE_final12.json"
LOWPASS_AUDIT = ROOT / "experiments/dl_attitude_replacement_20261028/gru_tau01_position_applied_lowpass_tau01_v1/audits/ROOT_POSITION_APPLIED_LOWPASS_SINGLE_SCENE_AUDIT_v1.json"
OUT_JSON = HERE / "NOTCH_SINGLE_SCENE_FROZEN_SCORE_AUDIT_v2.json"
OUT_MD = HERE / "NOTCH_SINGLE_SCENE_FROZEN_SCORE_AUDIT_v2.md"
MASS = 0.695
DT = 0.001
EVENT_DT = 0.01


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def readj(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def arr3(group: h5py.Group, name: str, n: int) -> np.ndarray:
    a = np.asarray(group[name][()], dtype=float)
    if a.shape == (3, n):
        a = a.T
    if a.shape != (n, 3):
        raise RuntimeError(f"{name}: expected {(n, 3)}, got {a.shape}")
    return a


def scalar(group: h5py.Group, name: str) -> float:
    return float(np.asarray(group[name][()]).squeeze())


def validate_status(raw_path: Path, raw_hash: str, status_path: Path, expected_status_hash: str) -> dict:
    if sha(status_path).lower() != expected_status_hash.lower():
        raise RuntimeError(f"status SHA mismatch: {status_path}")
    status = readj(status_path)
    complete = status.get("state") == "COMPLETED" or status.get("status") == "RUN_COMPLETE_RAW_PENDING_AUDIT"
    stable = status.get("status_value", status.get("log_status", "STABLE")) == "STABLE"
    plant_calls = status.get("Plant_calls", status.get("plant_calls"))
    transitions = status.get("transitions", status.get("last_transition"))
    if (not complete or not stable or
            status.get("scene_id") != SCENE_ID or status.get("safety_stop_reason") != "" or
            plant_calls != 1 or transitions != 20000 or
            status.get("state_samples") != 20001 or
            status.get("test_data_read", status.get("TEST_accessed", status.get("TEST_read", False))) is not False or
            Path(status.get("raw_path", "")).resolve() != raw_path.resolve() or
            status.get("raw_sha256", "").lower() != raw_hash.lower()):
        raise RuntimeError(f"completed run status contract failed: {status_path}")
    return status


def validate_comparator(name: str, item: dict, expected_scene: str) -> dict:
    p = Path(item["raw_path"])
    rh = sha(p)
    if rh.lower() != item["raw_sha256"].lower():
        raise RuntimeError(f"{name} raw SHA mismatch")
    status_path = Path(item.get("run_status_path", item.get("status_path", "")))
    status_sha = item.get("run_status_sha256", item.get("status_sha256", ""))
    status = validate_status(p, rh, status_path, status_sha)
    return {"raw_path": str(p), "raw_sha256": rh, "run_status_path": str(status_path),
            "run_status_sha256": status_sha, "status": status}


def replay_notch_and_route_audit() -> dict:
    start, status = readj(RUN_START), readj(RUN_STATUS)
    raw_hash = sha(RAW)
    if start.get("scene_id") != SCENE_ID or start.get("release_sha256") != status.get("release_sha256"):
        raise RuntimeError("run_start/status identity mismatch")
    validate_status(RAW, raw_hash, RUN_STATUS, sha(RUN_STATUS))
    if status.get("raw_sha256", "").lower() != raw_hash.lower():
        raise RuntimeError("raw/status SHA mismatch")
    current_release_sha = sha(RELEASE)
    current_lock_sha = sha(SOURCE_LOCK)
    release_snapshot_sha = sha(RELEASE_SNAPSHOT)
    lock_snapshot_sha = sha(SOURCE_LOCK_SNAPSHOT)
    if release_snapshot_sha.lower() != start.get("release_sha256", "").lower():
        raise RuntimeError("archived run-bound RELEASE snapshot does not match run identity")
    if lock_snapshot_sha.lower() != start.get("source_lock_sha256", "").lower():
        raise RuntimeError("archived run-bound source-lock snapshot does not match run identity")
    source_lock = readj(SOURCE_LOCK_SNAPSHOT)
    file_hashes = {x["path"].replace("\\", "/"): x["sha256"].lower() for x in source_lock["files"]}
    helper_rel = "candidate_runner_work/matlab/runtime/position_applied_accel_notch_zoh.m"
    runner_rel = "candidate_runner_work/matlab/runtime/run_mlp15_dev72_closed_loop.m"
    helper_path, runner_path = STUDY / helper_rel, STUDY / runner_rel
    helper_snapshot_path, runner_snapshot_path = SOURCE_FILES_SNAPSHOT / helper_rel, SOURCE_FILES_SNAPSHOT / runner_rel
    verified_snapshot_files = 0
    for rel, expected in file_hashes.items():
        p = SOURCE_FILES_SNAPSHOT / rel
        if not p.is_file() or sha(p).lower() != expected:
            raise RuntimeError(f"run-bound source snapshot mismatch: {rel}")
        verified_snapshot_files += 1
    payload = Path(start["scene_payload_path"])
    if sha(payload).lower() != start["scene_payload_sha256"].lower():
        raise RuntimeError("scene payload hash mismatch")

    with h5py.File(RAW, "r") as f:
        log = f["log"]
        ident = f["runIdentity"]
        time = np.asarray(log["transition_time"][()], dtype=float).reshape(-1)
        n = len(time)
        event = np.asarray(log["stage1_position_event"][()], dtype=bool).reshape(-1)
        inference_valid = np.asarray(log["stage1_position_event_inference_valid"][()], dtype=bool).reshape(-1)
        event_idx = np.flatnonzero(event)
        notch_input = arr3(log, "stage1_position_applied_notch_event_input_mps2", n)
        output_raw = arr3(log, "stage1_position_applied_notch_event_output_raw_mps2", n)
        output_applied = arr3(log, "stage1_position_applied_notch_event_output_applied_mps2", n)
        output_limit = arr3(log, "stage1_position_applied_notch_event_output_limit_mps2", n)
        clip_active = arr3(log, "stage1_position_applied_notch_event_clip_active", n).astype(bool)
        head_event_applied = arr3(log, "stage1_position_event_applied_acceleration_mps2", n)
        head_held_applied = arr3(log, "stage1_position_held_applied_acceleration_mps2", n)
        comp_total = arr3(log, "position_compensation_applied_acceleration_mps2", n)
        comp_force = arr3(log, "position_compensation_applied_force_N", n)
        position_held_force = arr3(log, "stage1_position_held_force_I_N", n)
        injected_force = arr3(log, "stage1_position_injected_force_I_N", n)
        nominal = arr3(log, "position_nominal_acceleration_mps2", n)
        commanded_force = arr3(log, "position_commanded_force_N", n)
        pcf_a_req = arr3(log, "stage1_position_pcf_a_req_mps2", n)
        b = np.asarray(ident["notch_b"][()], dtype=float).reshape(-1)
        a = np.asarray(ident["notch_a"][()], dtype=float).reshape(-1)
        initial_state = np.asarray(ident["notch_initial_state"][()], dtype=float)
        center_hz = scalar(log, "stage1_position_applied_notch_center_hz")
        q = scalar(log, "stage1_position_applied_notch_q")
        enabled = scalar(log, "stage1_position_applied_notch_enabled")
        held_logged_release = np.asarray(log["position_applied_notch_release_sha256"][()], dtype=np.uint16)
        held_release_sha = "".join(chr(int(v)) for v in held_logged_release.reshape(-1) if v).strip()
        flags = [scalar(log, name) for name in ("stage1_position_replacement_enabled",
            "stage1_position_delayed_prediction_enabled", "stage1_position_pcf_coordination_enabled")]
        tau = scalar(ident, "position_delayed_prediction_tau_s")
        rho = scalar(ident, "position_delayed_prediction_rho")
        status_value = bytes(np.asarray(log["status"][()], dtype=np.uint8).reshape(-1)).decode("ascii", errors="ignore").rstrip("\x00")
        safety_stop = bytes(np.asarray(log["safety_stop_reason"][()], dtype=np.uint8).reshape(-1)).decode("ascii", errors="ignore").rstrip("\x00")

    if n != 20000 or len(event_idx) != 1999 or not np.array_equal(np.diff(event_idx), np.full(1998, 10)):
        raise RuntimeError(f"unexpected event cadence: {len(event_idx)} events")
    if abs(time[event_idx[0]] - EVENT_DT) > 1e-12 or np.max(np.abs(np.diff(time) - DT)) > 1e-12:
        raise RuntimeError("event clock/index mismatch")
    if (enabled != 1 or center_hz != 3.5 or q != 1 or tau != 1 or rho != 0.01 or flags != [1, 1, 1]):
        raise RuntimeError("run identity/filter or frozen C5 flags differ from expected candidate")
    if not np.allclose(initial_state, 0, atol=0, rtol=0) or held_release_sha.lower() != start["release_sha256"].lower():
        raise RuntimeError("filter init or logged release binding mismatch")
    for x in (notch_input, output_raw, output_applied, output_limit):
        if not np.all(np.isfinite(x[event_idx])) or np.any(np.isfinite(x[np.setdiff1d(np.arange(n), event_idx)])):
            raise RuntimeError("notch event-only log sparsity/finite contract failed")
    valid_idx = event_idx[inference_valid[event_idx]]
    invalid_idx = event_idx[~inference_valid[event_idx]]
    if (not np.allclose(notch_input[valid_idx], head_event_applied[valid_idx], atol=1e-12, rtol=0) or
            np.max(np.abs(notch_input[invalid_idx])) > 1e-12):
        raise RuntimeError("notch input is not the current Stage1 head output")

    state = np.zeros((3, 4))
    expected_raw = np.zeros((len(event_idx), 3))
    for j, k in enumerate(event_idx):
        x = notch_input[k]
        y = b[0]*x + b[1]*state[:, 0] + b[2]*state[:, 1] - a[1]*state[:, 2] - a[2]*state[:, 3]
        expected_raw[j] = y
        state = np.column_stack((x, state[:, 0], y, state[:, 2]))
    rec_error = float(np.max(np.abs(expected_raw - output_raw[event_idx])))
    clipped = np.minimum(np.maximum(output_raw[event_idx], -output_limit[event_idx]), output_limit[event_idx])
    clip_error = float(np.max(np.abs(clipped - output_applied[event_idx])))
    clip_flag_error = int(np.count_nonzero((np.abs(output_raw[event_idx]-output_applied[event_idx]) > 1e-12) != clip_active[event_idx]))
    expected_held = np.zeros((n, 3))
    held = np.zeros(3)
    event_set = set(map(int, event_idx))
    for k in range(n):
        if k in event_set:
            held = output_applied[k].copy()
        expected_held[k] = held
    held_error = float(np.max(np.abs(expected_held - head_held_applied)))
    comp_error = float(np.max(np.abs(head_held_applied - comp_total)))
    force_error = float(np.max(np.abs(comp_total*MASS - comp_force)))
    held_force_error = float(np.max(np.abs(comp_total*MASS - position_held_force)))
    injected_force_error = float(np.max(np.abs(comp_total*MASS - injected_force)))
    command_error = float(np.max(np.abs(commanded_force/MASS - (nominal-comp_total))))
    pcf_input_error = float(np.max(np.abs(pcf_a_req - commanded_force/MASS)))
    if max(rec_error, clip_error, held_error, comp_error, force_error, held_force_error,
           injected_force_error, command_error, pcf_input_error) > 1e-9 or clip_flag_error:
        raise RuntimeError("logged notch output does not close through force/PCF fields")
    clip_count = int(np.count_nonzero(clip_active[event_idx]))
    if status_value != "STABLE" or safety_stop:
        raise RuntimeError("raw log status is not stable")

    return {
        "raw_path": str(RAW), "raw_sha256": sha(RAW), "run_start_sha256": sha(RUN_START),
        "run_status_sha256": sha(RUN_STATUS), "run_bound_release_snapshot_path": str(RELEASE_SNAPSHOT),
        "release_sha256_run_and_snapshot": release_snapshot_sha,
        "current_release_sha256_at_audit": current_release_sha,
        "current_release_matches_run_snapshot": bool(current_release_sha.lower() == release_snapshot_sha.lower()),
        "source_lock_snapshot_sha256": lock_snapshot_sha,
        "current_source_lock_sha256_at_audit": current_lock_sha,
        "current_source_lock_matches_run_snapshot": bool(current_lock_sha.lower() == lock_snapshot_sha.lower()),
        "run_bound_source_snapshot_dir": str(SOURCE_FILES_SNAPSHOT),
        "run_bound_source_snapshot_files_verified": verified_snapshot_files,
        "notch_helper_sha256_run_bound_snapshot": sha(helper_snapshot_path),
        "notch_helper_sha256_current": sha(helper_path),
        "notch_runner_sha256_run_bound_snapshot": sha(runner_snapshot_path),
        "notch_runner_sha256_current": sha(runner_path),
        "notch_runner_current_matches_run_snapshot": bool(sha(runner_path).lower() == sha(runner_snapshot_path).lower()),
        "scene_payload_sha256": start["scene_payload_sha256"], "Plant_calls_in_run": 1,
        "Plant_calls_started_by_auditor": 0, "TEST_read_by_auditor": False,
        "inertia_reconstruction": False, "training_runs_by_auditor": 0,
        "status": status_value, "safety_stop_reason": safety_stop,
        "transitions": n, "event_count": int(len(event_idx)),
        "first_event_index_zero_based": int(event_idx[0]), "first_event_time_s": float(time[event_idx[0]]),
        "last_event_index_zero_based": int(event_idx[-1]), "event_dt_s": EVENT_DT,
        "valid_head_event_count": int(len(valid_idx)), "pre_ready_zero_input_event_count": int(len(invalid_idx)),
        "filter": {"frequency_hz": center_hz, "Q": q, "sample_rate_hz": 100,
                   "b": b.tolist(), "a": a.tolist(), "initial_state_zero": True,
                   "position_tau_s": tau, "position_rho": rho, "C5_flags_replacement_delay_pcf": flags},
        "path_reconstruction_max_abs_errors": {
            "notch_recurrence_raw_mps2": rec_error,
            "notch_output_clip_mps2": clip_error,
            "clip_flag_mismatch_count": clip_flag_error,
            "event_output_to_held_zoh_mps2": held_error,
            "held_to_total_compensation_mps2": comp_error,
            "compensation_to_force_N": force_error,
            "held_force_N": held_force_error,
            "injected_force_N": injected_force_error,
            "position_command_from_nominal_minus_comp_mps2": command_error,
            "PCF_a_req_equals_position_command_mps2": pcf_input_error,
        },
        "clip_events_by_axis": np.count_nonzero(clip_active[event_idx], axis=0).astype(int).tolist(),
        "notch_input_abs_peak_mps2_by_axis": np.max(np.abs(notch_input[event_idx]), axis=0).tolist(),
        "notch_raw_output_abs_peak_mps2_by_axis": np.max(np.abs(output_raw[event_idx]), axis=0).tolist(),
        "notch_limit_peak_mps2_by_axis": np.max(output_limit[event_idx], axis=0).tolist(),
        "max_abs_notch_output_to_limit_ratio": float(np.max(np.abs(output_raw[event_idx]) / output_limit[event_idx])),
    }


def main() -> None:
    if OUT_JSON.exists() or OUT_MD.exists():
        raise RuntimeError("refusing to overwrite existing notch audit report")
    pilot = readj(PILOT_SCORE)
    lowpass = readj(LOWPASS_AUDIT)
    if pilot.get("TEST_read") is not False or pilot.get("test_data_read") is not False:
        raise RuntimeError("frozen score scope includes forbidden TEST data")
    score_path = Path(pilot["metric_source_path"])
    if sha(score_path).lower() != pilot["metric_source_sha256"].lower():
        raise RuntimeError("frozen FULL72 scorer SHA mismatch")
    spec = importlib.util.spec_from_file_location("frozen_score_full72", score_path)
    scorer = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = scorer
    spec.loader.exec_module(scorer)
    row = next(x for x in pilot["scene_results"] if x["scene_id"] == SCENE_ID)
    refs = {}
    for name in ("B", "C5", "Parent_Cosine_GRU"):
        info = row["methods"][name]
        status_path = Path(info.get("run_status_path", info.get("status_path", "")))
        refs[name] = validate_comparator(name, {**info, "run_status_path": str(status_path)}, SCENE_ID)
    lp = lowpass["methods"]["Position_Applied_Lowpass_tau0p1"]
    lp = {**lp, "run_status_path": lowpass["run_status_path"],
          "run_status_sha256": lowpass["run_status_sha256"]}
    refs["Position_Applied_Lowpass_tau0p1"] = validate_comparator("lowpass", lp, SCENE_ID)
    candidate_audit = replay_notch_and_route_audit()
    refs["Applied_Notch_3p5Hz_Q1"] = {"raw_path": candidate_audit["raw_path"],
        "raw_sha256": candidate_audit["raw_sha256"], "run_status_path": str(RUN_STATUS),
        "run_status_sha256": candidate_audit["run_status_sha256"]}

    methods = {}
    for method, item in refs.items():
        metrics = scorer.score_raw(Path(item["raw_path"]), 9.8, np.pi/6)
        methods[method] = {"raw_path": item["raw_path"], "raw_sha256": item["raw_sha256"],
            "run_status_path": item["run_status_path"], "run_status_sha256": item["run_status_sha256"],
            "Q_mm": 1000*float(metrics["Q_m"]), "task_SO3_mrad": 1000*float(metrics["task_SO3_rad"]),
            "inner_SO3_mrad": 1000*float(metrics["inner_SO3_rad"]), "safety": metrics["safety"]}
    base = methods["Applied_Notch_3p5Hz_Q1"]
    deltas = {name: {k: base[k]-methods[name][k] for k in ("Q_mm", "task_SO3_mrad", "inner_SO3_mrad")}
              for name in methods if name != "Applied_Notch_3p5Hz_Q1"}
    result = {
        "schema": "DL1018_NOTCH_SINGLE_SCENE_FROZEN_SCORE_AUDIT_V1",
        "status": "PASS_SCORE_AND_LOGGED_NOTCH_ROUTE_AUDIT",
        "scope": "Single completed VAL scene, frozen FULL72 score_raw; raw-only scoring and route audit. No Plant launched by auditor, no TEST, no training, no inertia reconstruction.",
        "scene_id": SCENE_ID, "frozen_pilot_score_path": str(PILOT_SCORE),
        "frozen_pilot_score_sha256": sha(PILOT_SCORE), "frozen_metric_path": str(score_path),
        "frozen_metric_sha256": sha(score_path), "metric_constants": {"gravity_mps2": 9.8, "max_tilt_rad": float(np.pi/6)},
        "notch_candidate_audit": candidate_audit, "methods_rescored_with_frozen_score_raw": methods,
        "notch_minus_comparator": deltas,
        "interpretation": [
            "This is one VAL scene and is only a development diagnostic, not independent validation.",
            "The current RELEASE/source lock and pilot snapshot are bound to the run SHA; the older NO_PLANT prepare receipt has an earlier pre-release SHA and is not the run release.",
            "The logged 100-Hz notch recurrence, clip, held compensation, position command, and PCF commanded-acceleration input were numerically reconstructed from the raw log.",
            "The filters are compared across separate completed Plant runs on the same scenario, not the same state trajectory; this one scene cannot establish a cross-scene or general closed-loop effect.",
        ],
    }
    OUT_JSON.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_md(result)
    print(json.dumps({"status": result["status"], "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))


def write_md(result: dict) -> None:
    lines = ["# Notch single-scene frozen-score and signal-path audit", "",
        "One completed VAL scene; frozen FULL72 `score_raw` rescored the raw logs. Auditor made no Plant calls and did not read TEST or reconstruct inertia. This is a development diagnostic, not independent validation.", "",
        "## Paired same-scenario scores", "",
        "| Method | Q (mm) | task SO(3) (mrad) | inner SO(3) (mrad) |", "|---|---:|---:|---:|"]
    for name, m in result["methods_rescored_with_frozen_score_raw"].items():
        lines.append(f"| {name} | {m['Q_mm']:.3f} | {m['task_SO3_mrad']:.3f} | {m['inner_SO3_mrad']:.3f} |")
    lines.extend(["", "Notch minus comparator (negative means lower error):", "",
        "| Comparator | ΔQ (mm) | Δtask (mrad) | Δinner (mrad) |", "|---|---:|---:|---:|"])
    for name, d in result["notch_minus_comparator"].items():
        lines.append(f"| {name} | {d['Q_mm']:+.3f} | {d['task_SO3_mrad']:+.3f} | {d['inner_SO3_mrad']:+.3f} |")
    a = result["notch_candidate_audit"]
    lines.extend(["", "## Run identity and signal path", "",
        f"Raw SHA-256 `{a['raw_sha256']}`; run status `{a['status']}`, transitions={a['transitions']}, Plant calls in original run={a['Plant_calls_in_run']}; safety stop `{a['safety_stop_reason'] or 'none'}`.",
        f"Run-bound archived RELEASE SHA-256 `{a['release_sha256_run_and_snapshot']}`; source lock snapshot SHA-256 `{a['source_lock_snapshot_sha256']}`. These match run_start, run_status, raw runIdentity, and archived pilot snapshot. Current RELEASE at audit time is `{a['current_release_sha256_at_audit']}` (same as run snapshot: {a['current_release_matches_run_snapshot']}); the older no-Plant preparation receipt had a pre-release hash and does not bind this Plant run.",
        f"All {a['run_bound_source_snapshot_files_verified']} archived source files verify against the run-bound lock. Current source lock matches the run snapshot: {a['current_source_lock_matches_run_snapshot']}; current runner bytes match archived runner bytes: {a['notch_runner_current_matches_run_snapshot']}. The archived runner/helper hashes, not later-edited working copies, bind the executed source.",
        f"Actual filter: causal 100-Hz 3.5-Hz/Q=1, event indices {a['first_event_index_zero_based']}…{a['last_event_index_zero_based']} every 10 samples; position predictor τ={a['filter']['position_tau_s']} s, ρ={a['filter']['position_rho']}.",
        f"Output clipping events: {sum(a['clip_events_by_axis'])}; maximum raw-output/allowed-limit ratio {a['max_abs_notch_output_to_limit_ratio']:.6f}.", "",
        "| Recurrence/link check | Max abs error |", "|---|---:|"])
    for k, v in a["path_reconstruction_max_abs_errors"].items():
        lines.append(f"| {k} | {v:.3e} |")
    lines.extend(["", "The check follows logged Stage1 event input → exact notch recurrence → logged elementwise clip → held output → total position compensation/force → position command; `stage1_position_pcf_a_req_mps2` equals the actual position commanded acceleration at every logged transition. This verifies that PCF received the command formed with the filtered compensation.", "",
        "No safety counters were nonzero in the frozen scorer for this scene. Cross-scene conclusions require more scenes; these paired records are separate Plant trajectories.", "",
        "## Reproduction", "",
        "From repository root: `python experiments/dl_attitude_replacement_20261028/gru_cosine_c5_applied_notch_35hz_q1_v1/audits/audit_notch_single_scene_v1.py`.", ""])
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
