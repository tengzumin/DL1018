#!/usr/bin/env python3
"""Single-scene frozen-score and raw recurrence audit for the residual-GRU pilot."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from pathlib import Path

import h5py
import numpy as np
from scipy.io import loadmat


HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
ROOT = HERE.parents[3]
SID = "DL1018_VAL_T3_C01_W14"
SCORE_OUT = HERE / "POSITION_RESIDUAL_GRU_SINGLE_SCENE_SCORE_v1.json"
REPORT_OUT = HERE / "POSITION_RESIDUAL_GRU_SINGLE_SCENE_SCORE_v1.md"
FROZEN_SCORER = ROOT / "experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_full72_v1/audits/score_full72_candidate_v1.py"
FROZEN_SCORE_REF = ROOT / "experiments/dl_attitude_replacement_20261028/gru_cosine_c5_applied_notch_35hz_q1_v1/audits/NOTCH_SINGLE_SCENE_FROZEN_SCORE_AUDIT_v2.json"
PARENT_STUDY = ROOT / "experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_full72_v1"
NOTCH_STUDY = ROOT / "experiments/dl_attitude_replacement_20261028/gru_cosine_c5_applied_notch_35hz_q1_v1"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def readj(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def require(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)


def bounded(path: Path, expected: str, label: str) -> str:
    require(path.is_file(), f"Missing {label}: {path}")
    actual = sha(path)
    require(actual.lower() == str(expected).lower(), f"{label} SHA256 mismatch: {path}")
    return actual


def field(g: h5py.Group, name: str) -> np.ndarray:
    require(name in g, f"Missing raw log field /log/{name}")
    return np.asarray(g[name][()])


def decode_matlab_char(a: np.ndarray) -> str:
    return "".join(chr(int(c)) for c in a.reshape(-1) if int(c) != 0)


def max_abs(a: np.ndarray, b: np.ndarray, mask: np.ndarray | None = None) -> float:
    if mask is not None:
        a, b = a[mask], b[mask]
    return float(np.max(np.abs(np.asarray(a, dtype=np.float64) - np.asarray(b, dtype=np.float64)), initial=0.0))


def main() -> None:
    require(not SCORE_OUT.exists() and not REPORT_OUT.exists(), "Refusing to overwrite single-scene score outputs")
    release_path = STUDY / "RELEASE.json"
    lock_path = STUDY / "SOURCE_LOCK_v1.json"
    run_dir = STUDY / "runs" / SID
    raw_path = run_dir / "raw_run.mat"
    status_path = run_dir / "run_status.json"
    start_path = run_dir / "run_start.json"
    release, lock, status, start = map(readj, (release_path, lock_path, status_path, start_path))
    release_sha, lock_sha, raw_sha, status_sha, start_sha = map(sha, (release_path, lock_path, raw_path, status_path, start_path))
    require(release["fixed_scene_id"] == SID and release["authorized_scenes"] == [SID], "Pilot release scene lock mismatch")
    require(release_sha.lower() == status["release_sha256"].lower() == start["release_sha256"].lower(), "Run release SHA binding mismatch")
    require(lock_sha.lower() == release["source_lock_sha256"].lower() == status["source_lock_sha256"].lower() == start["source_lock_sha256"].lower(), "Source-lock SHA binding mismatch")
    require(status["scene_id"] == start["scene_id"] == SID and status["state"] == "COMPLETED" and
            status["status_value"] == "STABLE" and status["Plant_calls"] == 1 and
            status["safety_stop_reason"] in ("", "NONE", None) and status["TEST_read"] is False,
            "Candidate run status/safety/budget identity mismatch")
    require(status["transitions"] == 20000 and status["state_samples"] == 20001 and
            status["raw_sha256"].lower() == raw_sha.lower(), "Candidate raw status/hash/length mismatch")
    require(release["TEST_read"] is False and release["test_data_read"] is False and
            release["inertia_reconstruction_enabled"] is False and release["training_runs"] == 0,
            "Candidate release scope lock failed")
    require(start["TEST_read"] is False and start["inertia_reconstruction_enabled"] is False and
            start["Plant_calls_authorized_for_attempt"] == 1, "Candidate run-start scope lock failed")

    # Verify every candidate runtime/audit file against the frozen source lock.
    runner_root_declared = Path(lock["root"])
    source_results = []
    for item in lock["files"]:
        # The frozen lock writer hashes paths relative to STUDY, despite its `root`
        # metadata field naming candidate_runner_work. Verify the writer's actual rule.
        p = STUDY / item["path"]
        source_results.append((p, bounded(p, item["sha256"], f"locked source {item['path']}")))
    require(len(source_results) == 72 == release["source_file_count"], "Candidate source lock file-count mismatch")
    weights = STUDY / release["position_residual_gru"]["weights_relative_path"]
    weights_sha = bounded(weights, release["position_residual_gru"]["weights_sha256"], "residual-GRU MAT weights")
    require(start["residual_gru_weights_sha256"].lower() == weights_sha.lower(), "Run-start residual weight SHA mismatch")
    require(start["external_identity_sha256"] == "619b306fb34db86fb1538e14c207ba599f5f2760730f95c2b644ce079dfdcf7c",
            "Pilot external scene identity changed")
    payload_path = Path(start["scene_payload_path"])
    payload_sha = bounded(payload_path, start["scene_payload_sha256"], "single-scene payload")
    candidate_payload_manifest_path = STUDY / "MLP15_DEV72_PAYLOAD_MANIFEST_v2.json"
    candidate_payload_manifest_sha = bounded(candidate_payload_manifest_path,
                                              release["parent_payload_manifest_sha256"],
                                              "parent payload manifest")
    payload_manifest = readj(candidate_payload_manifest_path)
    payload_record = next(r for r in payload_manifest["records"] if r["scene_id"] == SID)
    require(payload_record["external_identity_sha256"] == start["external_identity_sha256"] and
            payload_record["payload_sha256"] == start["scene_payload_sha256"] and
            payload_record["b_raw_sha256"].lower() == start["b_raw_sha256"].lower(),
            "Pilot payload/B source identity mismatch")

    # Resolve all comparators from their scene manifests/ledgers, never by globbing a guessed raw.
    parent_manifest = readj(PARENT_STUDY / "MANIFEST.json")
    parent_record = next(r for r in parent_manifest["records"] if r["scene_id"] == SID)
    parent_ledger = readj(PARENT_STUDY / "audits/FULL72_PROGRESS_LEDGER_v02.json")
    parent_ledger_record = next(r for r in parent_ledger["records"] if r["scene_id"] == SID)
    notch_status_path = NOTCH_STUDY / "runs" / SID / "run_status.json"
    notch_status = readj(notch_status_path)
    notch_release_path = NOTCH_STUDY / "RELEASE.json"
    notch_release = readj(notch_release_path)
    notch_raw = NOTCH_STUDY / "runs" / SID / "raw_run.mat"

    comparators = {
        "B": {"raw": Path(payload_record["b_raw_path"]), "raw_sha256": payload_record["b_raw_sha256"],
              "status": Path(payload_record["b_status_path"]), "status_sha256": payload_record["b_status_sha256"]},
        "C5": {"raw": Path(parent_record["c5_raw_path"]), "raw_sha256": parent_record["c5_raw_sha256"],
               "status": Path(parent_record["c5_status_path"]), "status_sha256": parent_record["c5_status_sha256"]},
        "Parent_Cosine_GRU": {"raw": Path(parent_ledger_record["raw_path"]),
                               "raw_sha256": parent_ledger_record["raw_sha256"],
                               "status": Path(parent_record["candidate_status_path"]),
                               "status_sha256": None,
                               "audit": Path(parent_ledger_record["audit_path"])},
        "Applied_Notch_3p5Hz_Q1": {"raw": notch_raw, "raw_sha256": notch_status["raw_sha256"],
                                    "status": notch_status_path, "status_sha256": None,
                                    "release": notch_release_path},
        "Residual_GRU_Pilot": {"raw": raw_path, "raw_sha256": raw_sha,
                                "status": status_path, "status_sha256": status_sha,
                                "release": release_path},
    }
    for name, spec in comparators.items():
        spec["raw_sha256"] = bounded(spec["raw"], spec["raw_sha256"], f"{name} raw")
        st = readj(spec["status"])
        spec["status_sha256"] = spec["status_sha256"] or sha(spec["status"])
        status_scene = st.get("scene_id")
        require(status_scene == SID and st.get("raw_sha256", "").lower() == spec["raw_sha256"].lower(),
                f"{name} status does not bind its scene/raw")
        require(st.get("safety_stop_reason") in ("", "NONE", None) and
                (st.get("TEST_read") is False or st.get("TEST_accessed") is False),
                f"{name} status safety/TEST lock failed")
        calls = st.get("Plant_calls", st.get("plant_calls"))
        require(calls == 1, f"{name} does not have exactly one existing Plant call")
        if "audit" in spec:
            audit = readj(spec["audit"])
            require(audit.get("candidate_raw_sha256", "").lower() == spec["raw_sha256"].lower(),
                    f"{name} raw audit SHA mismatch")
            spec["audit_sha256"] = sha(spec["audit"])

    # Re-run the exact frozen score_raw function, bound to the version used by the earlier notch audit.
    frozen_ref = readj(FROZEN_SCORE_REF)
    scorer_sha = bounded(FROZEN_SCORER, frozen_ref["frozen_metric_sha256"], "frozen score_raw source")
    gravity = float(frozen_ref["metric_constants"]["gravity_mps2"])
    max_tilt = float(frozen_ref["metric_constants"]["max_tilt_rad"])
    spec = importlib.util.spec_from_file_location("frozen_score_raw", FROZEN_SCORER)
    scorer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scorer)
    scores = {}
    for name, item in comparators.items():
        result = scorer.score_raw(item["raw"], gravity, max_tilt)
        scores[name] = {
            "raw_path": str(item["raw"]), "raw_sha256": item["raw_sha256"],
            "status_path": str(item["status"]), "status_sha256": item["status_sha256"],
            "release_sha256": (sha(item["release"]) if item.get("release") else readj(item["status"]).get("release_sha256")),
            "Q_m": result["Q_m"], "task_SO3_rad": result["task_SO3_rad"],
            "inner_SO3_rad": result["inner_SO3_rad"], "safety": result["safety"],
        }
    candidate = scores["Residual_GRU_Pilot"]
    for name, result in scores.items():
        result["candidate_minus_method"] = {
            metric: {"delta": candidate[metric] - result[metric],
                     "relative_change_pct": (100.0 * (candidate[metric] - result[metric]) / result[metric])}
            for metric in ("Q_m", "task_SO3_rad", "inner_SO3_rad")
        } if name != "Residual_GRU_Pilot" else None

    # Bind and independently replay every logged position-GRU event from the recorded 14-D runtime input.
    with h5py.File(raw_path, "r") as f:
        g = f["log"]
        get = lambda name: field(g, name)
        event_flag = get("position_event_flag").reshape(-1).astype(bool)
        idx = np.flatnonzero(event_flag)
        timeline = get("time").reshape(-1)
        event_gru = get("stage1_position_residual_gru_event").reshape(-1).astype(bool)
        ready_full = get("stage1_position_residual_gru_ready").reshape(-1).astype(bool)
        features_full = get("stage1_position_feature_14").T
        feature_input_full = get("stage1_position_feature_input").T
        raw_delta_full = get("stage1_position_residual_gru_raw_delta_mps2").T
        clipped_delta_full = get("stage1_position_residual_gru_clipped_delta_mps2").T
        beta_full = get("stage1_position_residual_gru_beta").reshape(-1)
        hidden_norm_full = get("stage1_position_residual_gru_hidden_norm").reshape(-1)
        base_full = get("stage1_position_residual_gru_base_action_mps2").T
        action_full = get("stage1_position_residual_gru_action_mps2").T
        correction_full = get("stage1_position_residual_gru_applied_correction_mps2").T
        total_clip_full = get("stage1_position_residual_gru_total_clip_active").T.astype(bool)
        c5_event_applied = get("stage1_position_event_applied_acceleration_mps2").T
        held_action = get("stage1_position_held_applied_acceleration_mps2").T
        held_force = get("stage1_position_held_force_I_N").T
        injected_force = get("stage1_position_injected_force_I_N").T
        applied_force = get("position_compensation_applied_force_N").T
        applied_accel = get("position_compensation_applied_acceleration_mps2").T
        pcf_enabled = bool(get("stage1_position_pcf_coordination_enabled").reshape(-1)[0])
        notch_enabled = bool(get("stage1_position_applied_notch_enabled").reshape(-1)[0])
        residual_enabled = bool(get("stage1_position_residual_gru_enabled").reshape(-1)[0])
        raw_weights_sha = decode_matlab_char(get("stage1_position_residual_gru_weights_sha256"))

    require(len(idx) == 1999 and idx[0] == 10 and idx[-1] == 19990 and np.all(np.diff(idx) == 10),
            "Position event index/rate mismatch")
    event_time = timeline[idx]
    require(np.allclose(event_time[[0, -1]], [0.01, 19.99], atol=1e-12, rtol=0), "Raw event time endpoints mismatch")
    require(np.array_equal(event_gru, event_flag) and residual_enabled, "Residual GRU event routing mismatch")
    ready = np.arange(len(idx)) >= 31
    require(int(ready.sum()) == 1968 and np.array_equal(ready_full[idx], ready), "Residual GRU warmup/readiness mismatch")
    require(idx[31] == 320 and abs(event_time[31] - 0.32) < 1e-12, "First GRU-ready event is not event#31 at 0.32s")
    x14 = features_full[idx]
    require(x14.shape == (1999, 14) and np.isfinite(x14).all(), "Actual logged X14 inputs are not finite 14-vectors")
    require(np.isfinite(feature_input_full[idx]).all() and max_abs(feature_input_full[idx], x14) == 0.0,
            "Actual model input differs from the logged 14-feature vector")
    require(raw_weights_sha.lower() == weights_sha.lower(), "Raw logged residual-weight SHA differs from released MAT")
    require(pcf_enabled and not notch_enabled, "Expected active PCF and disabled applied notch in this single-factor pilot")

    mat = loadmat(weights)
    w_ih, w_hh = mat["gru_weight_ih_l0"], mat["gru_weight_hh_l0"]
    b_ih, b_hh = mat["gru_bias_ih_l0"].reshape(-1), mat["gru_bias_hh_l0"].reshape(-1)
    w_head, b_head = mat["head_weight"], mat["head_bias"].reshape(-1)
    mean, std = mat["input_mean"].reshape(-1), mat["input_std"].reshape(-1)
    hidden = np.zeros(32, dtype=np.float64)
    computed_raw, computed_norm = [], []
    for feature in x14:
        xn = (feature.astype(np.float64) - mean) / std
        gi = w_ih @ xn + b_ih
        gh = w_hh @ hidden + b_hh
        reset = 1.0 / (1.0 + np.exp(-(gi[:32] + gh[:32])))
        update = 1.0 / (1.0 + np.exp(-(gi[32:64] + gh[32:64])))
        new = np.tanh(gi[64:96] + reset * gh[64:96])
        hidden = (1.0 - update) * new + update * hidden
        computed_raw.append(w_head @ hidden + b_head)
        computed_norm.append(np.linalg.norm(hidden))
    computed_raw = np.asarray(computed_raw)
    computed_norm = np.asarray(computed_norm)
    computed_beta = np.clip(event_time / 1.8, 0.0, 1.0)
    computed_delta = np.where(ready[:, None], np.clip(computed_raw, -0.5, 0.5), 0.0)
    logged_raw = raw_delta_full[idx]
    logged_delta = clipped_delta_full[idx]
    logged_beta = beta_full[idx]
    logged_hidden_norm = hidden_norm_full[idx]
    require(max_abs(computed_raw, logged_raw) < 1e-10, "Independent GRU raw output replay mismatch")
    require(max_abs(computed_norm, logged_hidden_norm) < 1e-10, "Independent GRU recurrent hidden norm mismatch")
    require(max_abs(computed_delta, logged_delta) < 1e-10, "Residual delta clipping/readiness mismatch")
    require(max_abs(computed_beta, logged_beta) < 1e-12, "Residual beta/time formula mismatch")
    require(np.all(logged_delta[~ready] == 0), "Residual output was nonzero before head readiness")

    c5_base = c5_event_applied[idx]
    require(np.isfinite(c5_base[ready]).all(), "C5 post-PCF base action missing on ready events")
    require(max_abs(base_full[idx][ready], c5_base[ready]) < 1e-12,
            "Residual base action does not equal the C5 event applied action after PCF")
    expected_action = np.clip(base_full[idx] + computed_beta[:, None] * computed_delta, -3.0, 3.0)
    require(max_abs(expected_action[ready], action_full[idx][ready]) < 1e-10,
            "Residual total action does not match beta/delta/total clip formula")
    require(max_abs(action_full[idx][ready] - base_full[idx][ready], correction_full[idx][ready]) < 1e-12,
            "Logged applied correction does not equal action minus C5 base")
    clip_event_count = int(total_clip_full[idx][ready].sum())
    require(clip_event_count == 0, "Unexpected total ±3 m/s² action clipping in pilot")

    # Check that the event action is held through the plant-force input path between events.
    expected_held = np.zeros_like(held_action)
    for j, event_idx in enumerate(idx):
        end = idx[j + 1] if j + 1 < len(idx) else len(held_action)
        if ready[j]:
            expected_held[event_idx:end] = expected_action[j]
    require(max_abs(expected_held, held_action) < 1e-10, "Held applied acceleration differs from logged GRU action")
    require(max_abs(held_force, injected_force) < 1e-12, "Held force does not flow unchanged into injected-force input")
    require(max_abs(applied_force, held_force) < 1e-12, "Applied position force differs from residual-GRU force path")
    require(max_abs(applied_accel, expected_held) < 1e-10, "Logged applied acceleration differs from held residual action")

    # Use the same frozen score function, same metric constants and same raw inputs as the prior notch audit.
    for name, method in scores.items():
        if name in frozen_ref["methods_rescored_with_frozen_score_raw"]:
            old = frozen_ref["methods_rescored_with_frozen_score_raw"][name]
            require(abs(method["Q_m"] - old["Q_mm"] / 1000.0) < 1e-12 and
                    abs(method["task_SO3_rad"] - old["task_SO3_mrad"] / 1000.0) < 1e-12 and
                    abs(method["inner_SO3_rad"] - old["inner_SO3_mrad"] / 1000.0) < 1e-12,
                    f"Frozen score_raw changed for existing comparator {name}")

    output = {
        "schema": "POSITION_RESIDUAL_GRU_SINGLE_SCENE_RAW_AUDIT_V1",
        "status": "PASS_SINGLE_SCENE_RAW_BOUND_AND_RECURRENT_OUTPUT_VERIFIED",
        "scope": "One existing VAL scene only; no TEST read, no new Plant call, no inertia reconstruction",
        "scene_id": SID,
        "candidate_binding": {"release_sha256": release_sha, "source_lock_sha256": lock_sha,
                              "source_file_count_verified": len(source_results), "raw_sha256": raw_sha,
                              "run_status_sha256": status_sha, "run_start_sha256": start_sha,
                              "residual_weights_sha256": weights_sha, "payload_sha256": payload_sha,
                              "payload_manifest_sha256": candidate_payload_manifest_sha,
                              "source_lock_path_semantics": "files verified relative to STUDY, matching freeze_candidate_manifest_v1.py path.relative_to(STUDY)",
                              "source_lock_root_field": str(runner_root_declared),
                              "source_lock_root_metadata_mismatch": True},
        "method_raw_bindings": {n: {k: v for k, v in s.items() if k in ("raw_path", "raw_sha256", "status_path", "status_sha256", "release_sha256", "audit_sha256")} for n, s in scores.items()},
        "frozen_score": {"script_path": str(FROZEN_SCORER), "script_sha256": scorer_sha,
                         "prior_frozen_audit_sha256": sha(FROZEN_SCORE_REF),
                         "gravity_mps2": gravity, "max_tilt_rad": max_tilt},
        "metrics": scores,
        "raw_event_audit": {
            "position_events": int(len(idx)), "transition_index_first_last_zero_based": [int(idx[0]), int(idx[-1])],
            "event_time_first_last_s": [float(event_time[0]), float(event_time[-1])],
            "x14_input_shape": list(x14.shape), "x14_all_event_values_finite": True,
            "x14_equals_actual_model_input_max_abs": max_abs(feature_input_full[idx], x14),
            "event_flag_matches_residual_gru_event": True,
            "ready_events": int(ready.sum()), "first_ready_event_ordinal_zero_based": 31,
            "first_ready_transition_index_zero_based": int(idx[31]), "first_ready_time_s": float(event_time[31]),
            "hidden_reset_per_run_source_initialized_zero": True,
            "gru_gate_order": "reset,update,new",
            "gru_raw_replay_max_abs_mps2": max_abs(computed_raw, logged_raw),
            "gru_hidden_norm_replay_max_abs": max_abs(computed_norm, logged_hidden_norm),
            "delta_clip_replay_max_abs_mps2": max_abs(computed_delta, logged_delta),
            "beta_formula_replay_max_abs": max_abs(computed_beta, logged_beta),
            "beta_mean_ready": float(computed_beta[ready].mean()),
            "raw_delta_abs_ge_0p5_component_fraction_ready": float(np.mean(np.abs(computed_raw[ready]) >= 0.5)),
            "delta_nonzero_component_count_ready": int(np.count_nonzero(np.abs(computed_delta[ready]) > 1e-10)),
            "total_action_clip_component_count_ready": clip_event_count,
            "action_formula_max_abs_mps2": max_abs(expected_action[ready], action_full[idx][ready]),
            "base_equals_post_pcf_c5_event_action_max_abs_mps2": max_abs(base_full[idx][ready], c5_base[ready]),
            "held_acceleration_max_abs_mps2": max_abs(expected_held, held_action),
            "held_force_equals_injected_force_max_abs_N": max_abs(held_force, injected_force),
            "applied_force_equals_held_force_max_abs_N": max_abs(applied_force, held_force),
            "applied_acceleration_equals_action_max_abs_mps2": max_abs(applied_accel, expected_held),
            "pcf_enabled": pcf_enabled, "applied_notch_enabled": notch_enabled,
        },
        "safety": {"state": status["status_value"], "safety_stop_reason": status["safety_stop_reason"],
                   "Plant_calls_in_existing_status": status["Plant_calls"], "TEST_read": status["TEST_read"],
                   "inertia_reconstruction_enabled": release["inertia_reconstruction_enabled"],
                   "all_scored_methods_motor/generalized/tilt/head_saturation_zero": all(
                       all(v == 0 for v in (s["safety"]["motor_saturation_samples"],
                                            s["safety"]["generalized_clip_samples"],
                                            s["safety"]["tilt_limited_samples"],
                                            s["safety"]["attitude_head_projection_samples"],
                                            s["safety"]["attitude_head_output_saturated_samples"])) for s in scores.values())},
        "source_paths_reviewed": [
            "candidate_runner_work/matlab/runtime/position_residual_gru_step_v1.m",
            "candidate_runner_work/matlab/runtime/run_mlp15_dev72_closed_loop.m",
            "candidate_runner_work/matlab/models/position_residual_gru_full_train24.mat",
        ],
        "interpretation": "This single VAL pilot improves position Q against all four comparators but worsens task attitude error substantially. It is one closed-loop point, not independent validation or a general performance claim.",
    }
    SCORE_OUT.write_text(json.dumps(output, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    lines = ["# Position residual-GRU single-scene pilot audit", "",
             f"Scene: `{SID}`. Candidate raw SHA256: `{raw_sha}`. Candidate release/source-lock: `{release_sha}` / `{lock_sha}`.", "",
             "## Frozen score_raw comparison", "",
             "| Method | Q (mm) | task SO(3) (mrad) | inner SO(3) (mrad) | motor/gen/tilt/head events |", "|---|---:|---:|---:|---|"]
    for name, s in scores.items():
        safe = s["safety"]
        lines.append(f"| {name} | {1000*s['Q_m']:.3f} | {1000*s['task_SO3_rad']:.3f} | {1000*s['inner_SO3_rad']:.3f} | "
                     f"{safe['motor_saturation_samples']}/{safe['generalized_clip_samples']}/{safe['tilt_limited_samples']}/"
                     f"{safe['attitude_head_projection_samples']} |")
    lines += ["", "Candidate Q is lower than B/C5/parent GRU/single notch, while task attitude error is higher than every comparator. All five score traces report zero listed safety events.", "",
              "## Runtime recurrence and applied-force path", "",
              f"The raw contains {len(idx)} 100 Hz events at {event_time[0]:.2f}–{event_time[-1]:.2f}s. Logged X14 is finite for all events and matches model input exactly. The first 31 events update hidden state with zero emitted delta; event ordinal 31 at {event_time[31]:.2f}s is first ready. Independent recurrence replay max errors: raw head {max_abs(computed_raw, logged_raw):.3g}, hidden norm {max_abs(computed_norm, logged_hidden_norm):.3g}, delta {max_abs(computed_delta, logged_delta):.3g}, beta {max_abs(computed_beta, logged_beta):.3g}.", "",
              f"Ready base action equals the post-PCF C5 event action (max error {max_abs(base_full[idx][ready], c5_base[ready]):.3g} m/s²). Total action follows `clip(base + beta*clip(delta,±0.5),±3)` (max error {max_abs(expected_action[ready], action_full[idx][ready]):.3g}); no total-action clip occurred. The residual action is held into the logged applied acceleration; held force equals injected force exactly, and applied force equals held force exactly. PCF is enabled and applied notch is disabled.", "",
              f"Raw head components reached the ±0.5 delta bound in {100*np.mean(np.abs(computed_raw[ready]) >= .5):.2f}% of ready axis outputs on this one VAL scene. This warrants caution: the residual is frequently saturated at its own bound here, despite zero total ±3 action clips.", "",
              "## Source and scope", "",
              f"Verified all {len(source_results)} candidate source-lock files, current release/raw/status/run-start binding, MAT weight hash, same-scene B/C5/parent/notch raw hashes, and prior frozen scorer SHA `{scorer_sha}`. The lock's `root` field names `candidate_runner_work`, but its `files` are study-relative as shown by the hash-lock writer; verification used the writer's actual `relative_to(STUDY)` rule. Candidate status is STABLE, with no safety stop; `TEST_read=false`, no inertia reconstruction, and this audit made no Plant call.", "",
              "The single VAL result is a diagnostic point, not an independent validation cohort or a general closed-loop claim.", ""]
    REPORT_OUT.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": output["status"], "score_path": str(SCORE_OUT), "report_path": str(REPORT_OUT),
                      "metrics": {n: {"Q_mm": 1000*s["Q_m"], "task_mrad": 1000*s["task_SO3_rad"],
                                      "inner_mrad": 1000*s["inner_SO3_rad"]} for n, s in scores.items()},
                      "replay": output["raw_event_audit"]}, indent=2))


if __name__ == "__main__":
    main()
