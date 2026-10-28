#!/usr/bin/env python3
"""Independent read-only binding/action-chain audit for the completed single pilot."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import h5py
import numpy as np
import torch
from torch import nn

HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
ROOT = HERE.parents[3]
SCENE = "DL1018_VAL_T3_C01_W14"
ATTEMPT = STUDY / "runs" / SCENE / "attempt_002"
RAW = ATTEMPT / "raw_run.mat"
STATUS = ATTEMPT / "run_status.json"
RUN_START = ATTEMPT / "run_start.json"
RELEASE_PATH = STUDY / "RELEASE.json"
NO_PLANT_RELEASE = STUDY / "RELEASE_NO_PLANT_v1.json"
LOCK_PATH = STUDY / "SOURCE_LOCK_v1.json"
MODEL_PT = STUDY / "position_balanced_full24.pt"
PARITY = HERE / "MATLAB_EVENTWISE_PARITY_RESULT_v1.json"
SCORE = HERE / "SINGLE_PILOT_SCORE_v1.json"
OUT = HERE / "PILOT_RUN_BINDING_AND_ACTION_CHAIN_AUDIT_v1.json"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def readj(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def scalar(log, name: str) -> float:
    return float(np.asarray(log[name][()]).reshape(-1)[0])


def vec(log, name: str) -> np.ndarray:
    return np.asarray(log[name][()]).reshape(-1)


def mat(log, name: str) -> np.ndarray:
    return np.asarray(log[name][()]).T


class ResidualGRU(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.gru = nn.GRU(input_size=14, hidden_size=32, num_layers=1, batch_first=True)
        self.head = nn.Linear(32, 3)

    def forward(self, x):
        h, _ = self.gru(x)
        return self.head(h)


def main() -> None:
    if OUT.exists():
        raise RuntimeError(f"Refusing to overwrite {OUT}")
    release, status, run_start = readj(RELEASE_PATH), readj(STATUS), readj(RUN_START)
    source_lock = readj(LOCK_PATH)
    if sha(LOCK_PATH) != release["source_lock_sha256"] or status["source_lock_sha256"] != release["source_lock_sha256"]:
        raise RuntimeError("Run/source-lock binding mismatch")
    for rec in source_lock["files"]:
        path = STUDY / rec["relative_path"]
        if not path.is_file() or sha(path).lower() != rec["sha256"].lower():
            raise RuntimeError(f"Locked source file changed: {rec['relative_path']}")
    for rec in source_lock["external_inputs"]:
        path = Path(rec["path"])
        if not path.is_file() or sha(path).lower() != rec["sha256"].lower():
            raise RuntimeError(f"Locked external input changed: {rec['name']}")
    if sha(RELEASE_PATH) != status["release_sha256"] or status["release_sha256"] != run_start["release_sha256"]:
        raise RuntimeError("Run/release binding mismatch")
    if (status.get("state") != "COMPLETED" or status.get("status_value") != "STABLE" or
            status.get("scene_id") != SCENE or status.get("transitions") != 20000 or
            status.get("state_samples") != 20001 or status.get("plant_calls") != 1 or
            status.get("test_data_read") is not False or status.get("inertia_reconstruction_enabled") is not False):
        raise RuntimeError("Pilot status is not one complete stable non-TEST run")
    if sha(RAW) != status["raw_sha256"] or run_start["scene_id"] != SCENE:
        raise RuntimeError("Raw/run-start scene identity or SHA mismatch")
    no_plant = readj(STUDY / "NO_PLANT_PREPARE_RESULT_v1.json")
    if (no_plant.get("status") != "PASS_STOPPED_BEFORE_PLANT" or
            no_plant.get("source_lock_sha256") != release["source_lock_sha256"] or
            sha(NO_PLANT_RELEASE) != no_plant["release_sha256"] or
            status["release_no_plant_sha256"] != no_plant["release_sha256"]):
        raise RuntimeError("Prior no-Plant proof is not bound to this run")
    if sha(MODEL_PT) != release["position_residual_gru"]["checkpoint_sha256"]:
        raise RuntimeError("Checkpoint hash differs from the released candidate")
    weights_path = STUDY / release["position_residual_gru"]["weights_relative_path"]
    if sha(weights_path) != release["position_residual_gru"]["weights_sha256"]:
        raise RuntimeError("Runtime MAT weights differ from the release")
    if not (ATTEMPT / "first_plant_step.marker").is_file():
        raise RuntimeError("Attempt_002 lacks evidence of the first Plant transition")
    prior_status = readj(STUDY / "runs" / SCENE / "attempt_001" / "run_status.json")
    if (prior_status.get("state") != "FAILED" or prior_status.get("plant_calls") != 0 or
            (STUDY / "runs" / SCENE / "attempt_001" / "first_plant_step.marker").exists() or
            (STUDY / "runs" / SCENE / "attempt_001" / "raw_run.mat").exists()):
        raise RuntimeError("Attempt_001 does not prove a pre-Plant failure")

    with h5py.File(RAW, "r") as f:
        log = f["log"]
        t = vec(log, "time")[:-1]
        state = mat(log, "state")
        events = vec(log, "stage1_position_event").astype(bool)
        residual_events = vec(log, "stage1_position_residual_gru_event").astype(bool)
        ready = vec(log, "stage1_position_residual_gru_ready").astype(bool)
        raw_delta = mat(log, "stage1_position_residual_gru_raw_delta_mps2")
        clipped_delta = mat(log, "stage1_position_residual_gru_clipped_delta_mps2")
        beta = vec(log, "stage1_position_residual_gru_beta")
        base_action = mat(log, "stage1_position_residual_gru_base_action_mps2")
        action = mat(log, "stage1_position_residual_gru_action_mps2")
        correction = mat(log, "stage1_position_residual_gru_applied_correction_mps2")
        c5_event_action = mat(log, "stage1_position_event_applied_acceleration_mps2")
        held_action = mat(log, "stage1_position_held_applied_acceleration_mps2")
        held_force = mat(log, "stage1_position_held_force_I_N")
        injected_force = mat(log, "stage1_position_injected_force_I_N")
        x14 = mat(log, "stage1_position_feature_14")
        total_clip_active = vec(log, "stage1_position_residual_gru_total_clip_active")
        weights_utf16 = np.asarray(log["stage1_position_residual_gru_weights_sha256"][()]).reshape(-1)
        runtime_weights_sha = "".join(chr(int(x)) for x in weights_utf16 if int(x))
        event_count_logged = int(round(scalar(log, "stage1_position_residual_gru_event_count")))
        residual_enabled = bool(round(scalar(log, "stage1_position_residual_gru_enabled")))
    event_idx = np.flatnonzero(events)
    if (not residual_enabled or event_count_logged != int(events.sum()) or
            not np.array_equal(events, residual_events) or np.any(ready & ~events)):
        raise RuntimeError("Residual-GRU call/event/readiness flags disagree")
    if runtime_weights_sha.lower() != release["position_residual_gru"]["weights_sha256"].lower():
        raise RuntimeError("Weights SHA in raw log differs from released MAT")
    if len(event_idx) != 1999 or not np.allclose(t[event_idx[:4]], [0.01, 0.02, 0.03, 0.04], atol=1e-12, rtol=0):
        raise RuntimeError("100-Hz event clock differs from the declared event contract")
    ready_event_idx = event_idx[ready[event_idx]]
    if (len(ready_event_idx) != 1968 or event_idx[31] != ready_event_idx[0] or
            abs(t[ready_event_idx[0]] - 0.32) > 1e-12 or np.any(ready[event_idx[:31]])):
        raise RuntimeError("Warmup count/first-ready timing mismatch")
    if np.any(clipped_delta[event_idx[:31]] != 0) or np.any(action[event_idx[:31]] != 0):
        raise RuntimeError("Warmup residual/action is not exactly zero")

    # Recompute the deployed checkpoint on the actual logged causal X14 event stream.
    checkpoint = torch.load(MODEL_PT, map_location="cpu", weights_only=False)
    model = ResidualGRU().cpu().eval()
    model.load_state_dict(checkpoint["state_dict"])
    feature = x14[event_idx].astype(np.float32)
    mean = np.asarray(checkpoint["normalizer_mean"], np.float32)
    std = np.asarray(checkpoint["normalizer_std"], np.float32)
    if feature.shape != (1999, 14) or not np.isfinite(feature).all():
        raise RuntimeError("Logged runtime X14 stream is invalid")
    normalized = ((feature - mean) / std).astype(np.float32)
    with torch.no_grad():
        py_raw = model(torch.from_numpy(normalized[None, :, :])).numpy()[0].astype(np.float64)
    py_err = py_raw - raw_delta[event_idx]
    py_raw_max = float(np.max(np.abs(py_err)))
    print(f"CHECKPOINT_REPLAY max={py_raw_max:.9g} pred_shape={py_raw.shape} logged_shape={raw_delta[event_idx].shape}", flush=True)
    if py_raw_max > 2e-5:
        raise RuntimeError("Logged runtime GRU outputs disagree with released PyTorch checkpoint")

    beta_expected = np.clip(t[event_idx] / 1.8, 0, 1)
    delta_expected = np.clip(raw_delta[event_idx], -0.5, 0.5)
    delta_expected[~ready[event_idx]] = 0.0
    action_expected = np.clip(base_action[event_idx] + beta_expected[:, None] * delta_expected, -3, 3)
    action_expected[~ready[event_idx]] = 0.0
    beta_max = float(np.max(np.abs(beta[event_idx] - beta_expected)))
    delta_max = float(np.max(np.abs(clipped_delta[event_idx] - delta_expected)))
    action_max = float(np.max(np.abs(action[event_idx] - action_expected)))
    correction_max = float(np.max(np.abs(correction[event_idx] - (action_expected - base_action[event_idx]))))
    base_c5_max = float(np.max(np.abs(base_action[ready_event_idx] - c5_event_action[ready_event_idx])))
    if max(beta_max, delta_max, action_max, correction_max, base_c5_max) > 1e-12:
        raise RuntimeError("Logged event-time/delta/action/base formula mismatch")
    if np.any(total_clip_active != 0):
        raise RuntimeError("Unexpected total-action clipping occurred")

    # Verify the actual held 1-ms action and its force realization/injection, not just event logs.
    forward_hold = np.zeros_like(held_action)
    last = np.zeros(3)
    event_to_action = {int(k): action[k] for k in event_idx}
    for k in range(len(t)):
        if k in event_to_action:
            last = event_to_action[k]
        forward_hold[k] = last
    held_action_max = float(np.max(np.abs(held_action - forward_hold)))
    inj_held_max = float(np.max(np.abs(injected_force - held_force)))
    norm2 = float(np.sum(held_action ** 2))
    inferred_mass = float(np.sum(held_action * held_force) / norm2)
    force_relation_max = float(np.max(np.abs(held_force - inferred_mass * held_action)))
    if max(held_action_max, inj_held_max, force_relation_max) > 1e-12 or abs(inferred_mass - 0.695) > 1e-12:
        raise RuntimeError("Held action -> mass force -> injected force chain mismatch")

    parity = readj(PARITY)
    score = readj(SCORE)
    candidate_score = score["scores"]["PositionBalancedFull24"]
    safety = candidate_score["safety"]
    if any(int(safety[k]) != 0 for k in ("motor_saturation_samples", "generalized_clip_samples", "tilt_limited_samples")):
        raise RuntimeError("Pilot safety counters are nonzero")
    report = {
        "schema": "POSITION_TEACHER_POSITION_BALANCED_FULL24_RUN_BINDING_ACTION_CHAIN_AUDIT_V1",
        "status": "PASS_BINDING_EVENTWISE_AND_ACTION_CHAIN",
        "scope": "Post-run read-only audit of one VAL scene; no TEST, no Plant rerun, no inertia reconstruction.",
        "study_id": release["study_id"], "scene_id": SCENE,
        "attempt": "attempt_002", "plant_calls_actual": 1,
        "attempt_001_actual_plant_calls": 0,
        "raw_path": str(RAW.resolve()), "raw_sha256": sha(RAW),
        "run_status_path": str(STATUS.resolve()), "run_status_sha256": sha(STATUS),
        "release_sha256": sha(RELEASE_PATH), "release_no_plant_sha256": sha(NO_PLANT_RELEASE),
        "source_lock_sha256": sha(LOCK_PATH), "weights_mat_sha256": release["position_residual_gru"]["weights_sha256"],
        "checkpoint_sha256": sha(MODEL_PT), "training_data_sha256": release["training_data_sha256"],
        "source_lock_file_count_verified": len(source_lock["files"]),
        "source_lock_external_input_count_verified": len(source_lock["external_inputs"]),
        "teacher_npz_sha256": release["position_residual_gru"]["teacher_npz_sha256"],
        "runtime_log_weights_sha256_matches_release": True,
        "matlab_eventwise_train24_parity": parity,
        "event_clock": {
            "dt_s": float(np.median(np.diff(t))), "event_rate_hz": 100,
            "event_count": int(events.sum()), "residual_gru_event_count": event_count_logged,
            "first_event_time_s": float(t[event_idx[0]]),
            "first_ready_zero_based_event_index": 31,
            "first_ready_time_s": float(t[ready_event_idx[0]]),
            "ready_event_count": int(ready_event_idx.size),
            "hidden_updates_during_warmup": True,
        },
        "independent_checkpoint_replay_on_logged_X14": {
            "checkpoint": "DEPLOYMENT_MODEL_v1.pt copied into isolated study",
            "event_count": 1999, "max_abs_raw_delta_error_mps2": py_raw_max,
            "tolerance_mps2": 2e-5,
        },
        "action_chain": {
            "beta_formula": "clip(event_time_s/1.8,0,1)",
            "delta_formula": "clip(raw_delta,-0.5,0.5) if ready else 0",
            "action_formula": "clip(C5 post-PCF applied event action + beta*delta,-3,3) if ready else 0",
            "beta_max_abs_error": beta_max, "delta_max_abs_error_mps2": delta_max,
            "action_max_abs_error_mps2": action_max,
            "applied_correction_max_abs_error_mps2": correction_max,
            "C5_post_PCF_base_vs_residual_base_max_abs_error_mps2": base_c5_max,
            "warmup_action_exact_zero": True,
            "total_clip_samples": int(np.count_nonzero(total_clip_active)),
            "held_1ms_action_forward_hold_max_abs_error_mps2": held_action_max,
            "inferred_mass_kg_from_action_force": inferred_mass,
            "held_force_vs_mass_action_max_abs_error_N": force_relation_max,
            "injected_force_vs_held_force_max_abs_error_N": inj_held_max,
            "first_plant_step_marker_exists": True,
        },
        "score_path": str(SCORE.resolve()), "score_sha256": sha(SCORE),
        "scores": score["scores"], "comparisons": score["comparisons"],
        "safety": safety,
        "TEST_read": False, "inertia_reconstruction_enabled": False,
        "audit_script_path": str(Path(__file__).resolve()), "audit_script_sha256": sha(Path(__file__)),
        "audit_script_postrun_only": True,
    }
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"done": True, "report": str(OUT), "event_clock": report["event_clock"],
                      "action_chain": report["action_chain"],
                      "checkpoint_raw_max": py_raw_max}, indent=2), flush=True)


if __name__ == "__main__":
    main()
