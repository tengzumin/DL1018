from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import h5py
import numpy as np


HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
ROOT = HERE.parents[3]
SCENE = "DL1018_VAL_T3_C01_W14"
RUN = STUDY / "runs" / f"{SCENE}_retry_005"
OUTPUT = HERE / "ROOT_POSITION_APPLIED_LOWPASS_SINGLE_SCENE_AUDIT_v1.json"
HF6_SCORE = ROOT / "experiments/dl_attitude_replacement_20261028/gru_tau01_delayed_start_v1/audits/ROOT_HF6_SCORE_v1.json"
METRIC = ROOT / "experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_full72_v1/audits/score_full72_candidate_v1.py"
GRAVITY = 9.8
MAX_TILT = np.pi / 6


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def readj(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def check(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)


def bound(path: Path, expected: str, label: str) -> str:
    check(path.is_file(), f"Missing {label}: {path}")
    actual = sha(path)
    check(actual.lower() == str(expected).lower(), f"{label} SHA-256 mismatch: {path}")
    return actual


def log_array(log, name: str) -> np.ndarray:
    return np.asarray(log[name][()]).T


def text_field(group, name: str) -> str:
    return "".join(chr(int(value)) for value in np.asarray(group[name][()]).reshape(-1) if value)


def main() -> None:
    check(not OUTPUT.exists(), f"Refusing to overwrite existing audit: {OUTPUT}")
    release_path = HERE / "RELEASE_PILOT_ARCHIVE_v1.json"
    current_release_path = STUDY / "RELEASE.json"
    lock_path = STUDY / "SOURCE_LOCK_v1.json"
    manifest_path = STUDY / "SOURCE_HASH_MANIFEST_v1.json"
    run_start_path = RUN / "run_start.json"
    run_status_path = RUN / "run_status.json"
    raw_path = RUN / "raw_run.mat"
    release, start, status = map(readj, (release_path, run_start_path, run_status_path))
    release_sha = sha(release_path)
    check(release["status"] == "RELEASED" and release["study_id"] == STUDY.name,
          "Candidate release identity/status mismatch")
    check(release["fixed_scene_id"] == SCENE and SCENE in release["authorized_scenes"],
          "Run-bound release is not bound to this fixed VAL scene")
    check(release["TEST_data_read"] is False and release["inertia_reconstruction_enabled"] is False,
          "Release violates the no-TEST/no-inertia boundary")
    check(release["Plant_calls"] <= release["authorized_Plant_calls"] and
          release["authorized_Plant_calls"] >= 1,
          "Release Plant authorization/counter mismatch")
    check(start["release_sha256"] == release_sha and status["release_sha256"] == release_sha,
          "Run start/status do not match the archived release used by this run")
    run_lock_sha = release["source_lock_sha256"]
    run_manifest_sha = release["source_hash_manifest_sha256"]
    check(start["source_lock_sha256"] == run_lock_sha and status["source_lock_sha256"] == run_lock_sha,
          "Run start/status source-lock hash differs from its archived release")
    check(start["source_hash_manifest_sha256"] == run_manifest_sha,
          "Run start source-manifest hash differs from its archived release")

    current_release = readj(current_release_path)
    current_release_sha = sha(current_release_path)
    current_lock_sha = bound(lock_path, current_release["source_lock_sha256"], "current source lock")
    current_manifest_sha = bound(manifest_path, current_release["source_hash_manifest_sha256"],
                                 "current source manifest")
    manifest = readj(manifest_path)
    source_records = manifest["files"]
    check(manifest["status"] == "FROZEN_PENDING_ROOT_REVIEW" and
          len(source_records) == manifest["source_file_count"], "Current source manifest state/count mismatch")
    source_file_hashes = {}
    for record in source_records:
        source_file_hashes[record["path"]] = bound(STUDY / record["path"], record["sha256"], record["path"])
    check(len(source_file_hashes) == manifest["source_file_count"], "Source manifest contains duplicate paths")

    check(status["state"] == "COMPLETED" and status["scene_id"] == SCENE and
          status["status_value"] == "STABLE" and status["safety_stop_reason"] == "",
          "Candidate run is incomplete, unsafe, or bound to a different scene")
    check(status["TEST_data_read"] is False and status["Plant_calls"] == 1 and
          status["transitions"] == 20000 and status["state_samples"] == 20001,
          "Candidate run counts or TEST/Plant declaration mismatch")
    check(start["scene_id"] == SCENE and start["candidate_study_id"] == STUDY.name and
          start["TEST_data_read"] is False and start["inertia_reconstruction_enabled"] is False,
          "Run-start identity/safety declaration mismatch")
    raw_sha = bound(raw_path, status["raw_sha256"], "candidate raw")

    hf6 = readj(HF6_SCORE)
    check(hf6["status"] == "COMPLETE_HF6_SCREEN" and hf6["TEST_read"] is False and
          hf6["inertia_reconstruction"] is False, "Locked comparator score is not an eligible DEV/VAL audit")
    row = next(r for r in hf6["scene_results"] if r["scene_id"] == SCENE)
    check(row["completed"] is True and row["status_value"] == "STABLE" and
          row["test_data_read"] is False, "Comparator row is not a completed safe VAL record")

    spec = importlib.util.spec_from_file_location("frozen_full72_score", METRIC)
    metric = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(metric)
    baseline_methods = ("B", "C5", "Parent_Cosine_GRU", "Delayed_Start_Candidate")
    methods = {"Position_Applied_Lowpass_tau0p1": {"raw_path": str(raw_path), "raw_sha256": raw_sha}}
    for name in baseline_methods:
        entry = row["methods"][name]
        method_path = Path(entry["raw_path"])
        bound(method_path, entry["raw_sha256"], f"{name} raw")
        if "run_status_path" in entry and "run_status_sha256" in entry:
            bound(Path(entry["run_status_path"]), entry["run_status_sha256"], f"{name} status")
        score = metric.score_raw(method_path, GRAVITY, MAX_TILT)
        for key in ("Q_m", "task_SO3_rad", "inner_SO3_rad"):
            check(abs(score[key] - entry[key]) < 1e-12, f"Frozen score replay mismatch for {name}/{key}")
        methods[name] = {"raw_path": entry["raw_path"], "raw_sha256": entry["raw_sha256"], **score}
    candidate_score = metric.score_raw(raw_path, GRAVITY, MAX_TILT)
    methods["Position_Applied_Lowpass_tau0p1"].update(candidate_score)
    comparisons = {}
    for name, entry in methods.items():
        if name == "Position_Applied_Lowpass_tau0p1":
            continue
        comparisons[name] = {
            key: {"candidate": candidate_score[key], "comparator": entry[key],
                  "candidate_minus_comparator": candidate_score[key] - entry[key]}
            for key in ("Q_m", "task_SO3_rad", "inner_SO3_rad")
        }

    with h5py.File(raw_path, "r") as raw:
        log = raw["log"]
        identity = raw["runIdentity"]
        check(text_field(identity, "scene_id") == SCENE and
              text_field(identity, "candidate_study_id") == STUDY.name,
              "Raw runIdentity scene/study mismatch")
        check(text_field(identity, "release_sha256") == release_sha and
              text_field(identity, "source_lock_sha256") == run_lock_sha and
              text_field(identity, "source_hash_manifest_sha256") == run_manifest_sha,
              "Raw runIdentity does not match its run-bound release/source hashes")
        check(bool(identity["TEST_data_read"][()][0, 0]) is False and
              bool(identity["inertia_reconstruction_enabled"][()][0, 0]) is False and
              bool(identity["position_force_and_pcf_use_same_filtered_output"][()][0, 0]) is True and
              abs(float(identity["applied_acceleration_lowpass_tau_s"][()][0, 0]) - 0.1) < 1e-12 and
              abs(float(identity["applied_acceleration_lowpass_event_rate_hz"][()][0, 0]) - 100) < 1e-12,
              "Raw runIdentity filter/TEST/inertia declaration mismatch")
        events = log_array(log, "stage1_position_event").reshape(-1).astype(bool)
        valid = log_array(log, "stage1_position_event_inference_valid").reshape(-1).astype(bool)
        tau = float(log["stage1_position_applied_lowpass_tau_s"][()][0, 0])
        enabled = bool(log["stage1_position_applied_lowpass_enabled"][()][0, 0])
        pcf_enabled = bool(log["stage1_position_pcf_coordination_enabled"][()][0, 0])
        event_dt = log_array(log, "stage1_position_event_dt_s").reshape(-1)
        alpha = log_array(log, "stage1_position_applied_lowpass_event_alpha").reshape(-1)
        event_input = log_array(log, "stage1_position_applied_lowpass_event_input_mps2").astype(float)
        event_output = log_array(log, "stage1_position_applied_lowpass_event_output_mps2").astype(float)
        head_applied = log_array(log, "stage1_position_event_applied_acceleration_mps2").astype(float)
        held = log_array(log, "stage1_position_held_applied_acceleration_mps2").astype(float)
        held_force = log_array(log, "stage1_position_held_force_I_N").astype(float)
        injected_force = log_array(log, "stage1_position_injected_force_I_N").astype(float)
        nominal_force = log_array(log, "position_bs_nominal_force_N").astype(float)
        commanded_force = log_array(log, "position_commanded_force_N").astype(float)
        pcf_a_req = log_array(log, "stage1_position_pcf_a_req_mps2").astype(float)
        pcf_a_f = log_array(log, "stage1_position_pcf_a_f_mps2").astype(float)
        pcf_r_f = log_array(log, "stage1_position_pcf_r_f_mps2").astype(float)
        time = log_array(log, "time").reshape(-1)[:len(events)]
        check(enabled and abs(tau - 0.1) < 1e-12 and pcf_enabled,
              "Raw does not show enabled tau=0.1 low-pass and PCF coordination")
        check(np.all(valid <= events), "Valid inference row is not a Stage-1 event")
        idx = np.flatnonzero(events)
        check(len(idx) > 1 and np.all(np.diff(idx) == 10), "Stage-1 event schedule is not exactly 100 Hz")
        check(np.all(np.isfinite(alpha[events])) and np.all(np.isnan(alpha[~events])),
              "Logged low-pass alpha is not event-only")
        check(np.all(np.isfinite(event_input[events])) and np.all(np.isnan(event_input[~events])),
              "Logged low-pass input is not event-only")
        check(np.all(np.isfinite(event_output[events])) and np.all(np.isnan(event_output[~events])),
              "Logged low-pass output is not event-only")
        check(np.all(np.isfinite(event_dt[events])) and np.all(np.abs(event_dt[events] - 0.01) < 2e-12),
              "Actual Stage-1 event dt is not 10 ms")
        check(np.nanmax(np.abs(event_input[valid] - head_applied[valid])) < 1e-12,
              "Low-pass input differs from the post-head applied acceleration")

        state = np.zeros(3)
        expected_held = np.zeros_like(held)
        recurrence_error = 0.0
        alpha_error = 0.0
        for i in range(len(events)):
            if events[i]:
                expected_alpha = -np.expm1(-event_dt[i] / tau)
                alpha_error = max(alpha_error, abs(expected_alpha - alpha[i]))
                predicted = state + expected_alpha * (event_input[i] - state)
                recurrence_error = max(recurrence_error, float(np.max(np.abs(predicted - event_output[i]))))
                state = event_output[i].copy()
            expected_held[i] = state
        held_replay_error = float(np.max(np.abs(expected_held - held)))
        check(recurrence_error < 1e-12 and alpha_error < 1e-12 and held_replay_error < 1e-12,
              "Recorded output does not match 100-Hz exact-ZOH recurrence plus hold")

        nonzero = np.abs(held) > 1e-8
        mass = float(np.median(held_force[nonzero] / held[nonzero]))
        force_scale_error = float(np.max(np.abs(held_force - mass * held)))
        injection_error = float(np.max(np.abs(injected_force - held_force)))
        position_force_error = float(np.max(np.abs(commanded_force - (nominal_force - injected_force))))
        pcf_input_error = float(np.max(np.abs(pcf_a_req - commanded_force / mass)))
        check(abs(mass - 0.695) < 1e-12 and force_scale_error < 1e-12 and injection_error < 1e-12,
              "Filtered acceleration is not the force actually injected into the position loop")
        check(position_force_error < 1e-10 and pcf_input_error < 1e-10,
              "Position command/PCF input does not use the filtered force path")
        first_valid = int(np.flatnonzero(valid)[0])
        actual_output = {
            "enabled": enabled, "tau_s": tau, "event_rate_hz": 100,
            "initial_state_mps2": [0.0, 0.0, 0.0],
            "scheduled_event_count": int(events.sum()), "valid_inference_event_count": int(valid.sum()),
            "first_scheduled_event_time_s": float(time[idx[0]]),
            "first_valid_inference_time_s": float(time[first_valid]),
            "first_valid_event_input_mps2": event_input[first_valid].tolist(),
            "first_valid_event_output_mps2": event_output[first_valid].tolist(),
            "first_event_alpha": float(alpha[idx[0]]), "valid_event_alpha_minmax": [
                float(np.min(alpha[events])), float(np.max(alpha[events]))],
            "max_recurrence_error_mps2": recurrence_error,
            "max_alpha_error": alpha_error, "max_held_trace_replay_error_mps2": held_replay_error,
            "mass_from_logged_force_over_acceleration_kg": mass,
            "max_filtered_force_identity_error_N": force_scale_error,
            "max_actual_injection_vs_filtered_force_error_N": injection_error,
            "max_position_command_force_equation_error_N": position_force_error,
            "pcf_coordination_enabled": pcf_enabled,
            "max_pcf_requested_accel_vs_commanded_force_error_mps2": pcf_input_error,
            "pcf_filtered_acceleration_rms_mps2": float(np.sqrt(np.mean(pcf_a_f ** 2))),
            "pcf_residual_acceleration_rms_mps2": float(np.sqrt(np.mean(pcf_r_f ** 2))),
        }

    metric_sha = sha(METRIC)
    output = {
        "schema": "DL1018_POSITION_APPLIED_LOWPASS_SINGLE_SCENE_AUDIT_V1",
        "status": "PASS_FROZEN_SCORE_AND_OUTPUT_PATH_AUDIT",
        "scope": "One completed VAL scene only; read-only raw scoring and logged-output validation.",
        "scene_id": SCENE,
        "candidate_raw_path": str(raw_path), "candidate_raw_sha256": raw_sha,
        "run_status_path": str(run_status_path), "run_status_sha256": sha(run_status_path),
        "candidate_status": status["status_value"], "safety_stop_reason": status["safety_stop_reason"],
        "Plant_calls_in_completed_run": status["Plant_calls"],
        "release_authorized_Plant_calls": release["authorized_Plant_calls"],
        "Plant_calls_started_by_auditor": 0, "TEST_data_read_by_auditor": False,
        "inertia_reconstruction": False, "training_runs_by_auditor": 0,
        "run_bound_release_archive_path": str(release_path), "run_bound_release_archive_sha256": release_sha,
        "run_bound_source_lock_sha256": run_lock_sha,
        "run_bound_source_hash_manifest_sha256": run_manifest_sha,
        "run_bound_source_lock_file_retained": current_lock_sha == run_lock_sha,
        "run_bound_source_manifest_file_retained": current_manifest_sha == run_manifest_sha,
        "current_release_path": str(current_release_path), "current_release_sha256": current_release_sha,
        "current_source_lock_sha256": current_lock_sha,
        "current_source_hash_manifest_sha256": current_manifest_sha,
        "current_source_files_verified_against_current_manifest": len(source_file_hashes),
        "frozen_metric_path": str(METRIC), "frozen_metric_sha256": metric_sha,
        "auditor_script_sha256": sha(Path(__file__)),
        "metric_constants": {"gravity_mps2": GRAVITY, "max_tilt_rad": float(MAX_TILT)},
        "methods": methods, "candidate_minus_comparator": comparisons,
        "actual_100hz_filter_and_position_pcf_path": actual_output,
        "interpretation": "This is one real closed-loop VAL run and a same-scene frozen-score comparison; it is not cohort-level evidence.",
    }
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": output["status"], "output": str(OUTPUT),
                      "candidate": {k: candidate_score[k] for k in ("Q_m", "task_SO3_rad", "inner_SO3_rad")},
                      "safety": candidate_score["safety"], "actual_output": actual_output}, ensure_ascii=False))


if __name__ == "__main__":
    main()
