#!/usr/bin/env python3
"""Read-only audit of the logged DC-fold action path for one TRAIN scene."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import h5py
import numpy as np
import torch

HERE = Path(__file__).resolve().parents[1]
PROJECT = Path(__file__).resolve().parents[4]
DATA = PROJECT / "experiments/dl_attitude_replacement_20261028/position_cosine_gru_train24_causal_v1"
TASK = DATA / "task_aware_cv_v1"
sys.path.insert(0, str(TASK))
import fit_task_aware_fourfold_v1 as fit  # noqa: E402


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def require(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)


def audit(study: Path) -> dict:
    release_path = study / "RELEASE.json"
    lock_path = study / "SOURCE_LOCK_SINGLE_CALL_v1.json"
    binding_path = study / "TRAIN_SCENE_BINDING_v1.json"
    release, lock, binding = read(release_path), read(lock_path), read(binding_path)
    scene = binding["selected_scene_id"]
    run = study / "runs" / scene / "attempt_01"
    raw_path, status_path, start_path = run / "raw_run.mat", run / "run_status.json", run / "run_start.json"
    status, start = read(status_path), read(start_path)
    score = read(study / "audits/TRAIN_SINGLE_SCENE_PAIRED_SCORE_v1.json")
    require(sha(lock_path) == release["source_lock_sha256"], "source-lock SHA differs from RELEASE")
    for item in lock["files"]:
        p = Path(item["path"])
        require(p.is_file() and sha(p) == item["sha256"], f"locked source hash mismatch: {p}")
    require(status["state"] == "COMPLETED" and status["status_value"] == "STABLE" and
            status["Plant_calls"] == 1 and status["transitions"] == 20000 and
            status["state_samples"] == 20001 and not status["TEST_read"] and
            not status["VAL_data_read"], "candidate raw/status is not one stable TRAIN call")
    require(sha(raw_path) == status["raw_sha256"] == score["methods"]["candidate"]["raw_sha256"],
            "raw hash disagrees across run status and frozen score")
    require(start["scene_id"] == scene and start["source_split"] == "TRAIN_C5_24" and
            start["fold_id"] == binding["fold_id"] and
            start["weights_sha256"] == release["weights_sha256"] and
            start["train_scene_binding_sha256"] == sha(binding_path) and
            start["source_lock_sha256"] == sha(lock_path), "run_start identity differs from release/binding")

    with h5py.File(raw_path, "r") as f:
        g = f["log"]
        vec = lambda k: np.asarray(g[k][()]).reshape(-1)
        mat = lambda k: np.asarray(g[k][()]).T
        event = vec("stage1_position_residual_gru_event").astype(bool)
        ready = vec("stage1_position_residual_gru_ready").astype(bool)
        event_ix = np.flatnonzero(event)
        ready_ix = np.flatnonzero(ready)
        t = vec("time")
        x = mat("stage1_position_feature_input")[event_ix].astype(np.float32)
        raw = mat("stage1_position_residual_gru_raw_delta_mps2")[event_ix]
        delta = mat("stage1_position_residual_gru_clipped_delta_mps2")[event_ix]
        beta = vec("stage1_position_residual_gru_beta")[event_ix]
        base = mat("stage1_position_residual_gru_base_action_mps2")[event_ix]
        action = mat("stage1_position_residual_gru_action_mps2")[event_ix]
        correction = mat("stage1_position_residual_gru_applied_correction_mps2")[event_ix]
        logged_weight = "".join(chr(int(c)) for c in
                                np.asarray(g["stage1_position_residual_gru_weights_sha256"][()])
                                .astype(np.uint16).reshape(-1) if c)
        held = mat("stage1_position_held_applied_acceleration_mps2")
        force = mat("stage1_position_held_force_I_N")
        action_clip = mat("stage1_position_residual_gru_total_clip_active")
        pcf = {k: mat(k) for k in (
            "stage1_position_pcf_a_req_mps2", "stage1_position_pcf_a_f_mps2",
            "stage1_position_pcf_r_f_mps2")}
        pcf_enabled = bool(np.asarray(g["stage1_position_pcf_coordination_enabled"][()]).reshape(-1)[0])

    require(logged_weight == release["position_residual_gru"]["weights_sha256"],
            "raw logged weights SHA differs from RELEASE")
    checkpoint = torch.load(study / "OOF_HOLDOUT_CHECKPOINT_v1.pt", map_location="cpu", weights_only=False)
    require(checkpoint["fold_id"] == binding["fold_id"] and scene in checkpoint["holdout_scene_ids"] and
            scene not in checkpoint["train_scene_ids"], "checkpoint is not the exact heldout fold")
    model = fit.ResidualGRU().cpu().eval()
    model.load_state_dict(checkpoint["state_dict"])
    mean = np.asarray(checkpoint["normalizer_mean"], dtype=np.float32)
    std = np.asarray(checkpoint["normalizer_std"], dtype=np.float32)
    with torch.no_grad():
        predicted_raw, predicted_delta = model(torch.from_numpy((((x - mean) / std)[None, :, :])))
    predicted_raw = predicted_raw.numpy()[0].astype(np.float64)
    predicted_delta = predicted_delta.numpy()[0].astype(np.float64)
    predicted_delta[~ready[event_ix]] = 0.0
    expected_beta = np.clip(t[event_ix] / 1.8, 0, 1)
    expected_action = np.clip(base + expected_beta[:, None] * delta, -3, 3)
    expected_action[~ready[event_ix]] = 0.0
    held_expected = np.zeros_like(held)
    last = np.zeros(3)
    event_lookup = {int(k): j for j, k in enumerate(event_ix)}
    for i in range(held.shape[0]):
        if i in event_lookup:
            last = action[event_lookup[i]].copy()
        held_expected[i] = last
    nonzero = np.abs(held) > 1e-8
    inferred_mass = float(np.median(force[nonzero] / held[nonzero]))

    report = {
        "schema": "POSITION_DC_OOF_TRAIN_ACTION_CHAIN_AUDIT_V1",
        "status": "PASS_LOGGED_ACTION_CHAIN_MATCH",
        "study_id": release["study_id"], "scene_id": scene,
        "source_split": "TRAIN_C5_24", "fold_id": binding["fold_id"],
        "release_sha256": sha(release_path), "source_lock_sha256": sha(lock_path),
        "train_scene_binding_sha256": sha(binding_path),
        "raw_path": str(raw_path.resolve()), "raw_sha256": sha(raw_path),
        "run_status_path": str(status_path.resolve()), "run_status_sha256": sha(status_path),
        "run_start_path": str(start_path.resolve()), "run_start_sha256": sha(start_path),
        "weights_release_sha256": release["weights_sha256"],
        "weights_raw_log_sha256": logged_weight, "weights_identity_match": True,
        "events": int(event.sum()), "ready_events": int(ready.sum()),
        "first_event_time_s": float(t[event_ix[0]]),
        "first_ready_row_zero_based": int(ready_ix[0]),
        "first_ready_event_index_zero_based": int(np.flatnonzero(ready[event_ix])[0]),
        "first_ready_time_s": float(t[ready_ix[0]]),
        "online_replay": {
            "event_X14_finite": bool(np.isfinite(x).all()),
            "max_abs_raw_delta_error_mps2": float(np.max(np.abs(predicted_raw - raw))),
            "max_abs_clipped_delta_error_mps2_after_ready_mask": float(np.max(np.abs(predicted_delta - delta))),
        },
        "action_formula": {
            "beta_max_abs_error": float(np.max(np.abs(expected_beta - beta))),
            "action_max_abs_error_mps2": float(np.max(np.abs(expected_action - action))),
            "correction_minus_action_base_max_abs_error_mps2": float(np.max(np.abs(correction - (action - base)))),
            "warmup_delta_max_abs_mps2": float(np.max(np.abs(delta[~ready[event_ix]]))),
            "warmup_action_max_abs_mps2": float(np.max(np.abs(action[~ready[event_ix]]))),
            "ready_raw_delta_fraction_over_0_5": float(np.mean(np.abs(raw[ready[event_ix]]) > .5)),
            "total_action_clip_samples": int(action_clip.sum()),
            "event_action_mean_mps2": np.mean(action, axis=0).tolist(),
            "mean_correction_mps2": np.mean(correction, axis=0).tolist(),
        },
        "downstream": {
            "held_action_ZOH_max_abs_error_mps2": float(np.max(np.abs(held - held_expected))),
            "held_force_equals_mass_times_action_max_abs_error_N": float(np.max(np.abs(force - inferred_mass * held))),
            "force_to_action_inferred_mass_kg": inferred_mass,
            "PCF_coordination_enabled": pcf_enabled,
            "PCF_fields_finite": all(bool(np.isfinite(v).all()) for v in pcf.values()),
            "PCF_RMS_mps2": {k: float(np.sqrt(np.mean(v * v))) for k, v in pcf.items()},
        },
        "frozen_score_sha256": sha(study / "audits/TRAIN_SINGLE_SCENE_PAIRED_SCORE_v1.json"),
        "frozen_score_methods": {
            k: {m: v[m] for m in ("Q_m", "task_SO3_rad", "inner_SO3_rad", "raw_sha256") if m in v}
            for k, v in score["methods"].items()
        },
        "scope": {"Plant_calls": status["Plant_calls"], "TEST_read": status["TEST_read"],
                  "VAL_data_read": status["VAL_data_read"], "inertia_reconstruction_enabled": False,
                  "interpretation": "TRAIN paired diagnostic only; not independent validation or causal attribution."},
    }
    require(report["online_replay"]["max_abs_raw_delta_error_mps2"] < 2e-6 and
            report["online_replay"]["max_abs_clipped_delta_error_mps2_after_ready_mask"] < 2e-6 and
            report["action_formula"]["beta_max_abs_error"] < 1e-12 and
            report["action_formula"]["action_max_abs_error_mps2"] < 1e-12 and
            report["downstream"]["held_action_ZOH_max_abs_error_mps2"] < 1e-12 and
            report["downstream"]["held_force_equals_mass_times_action_max_abs_error_N"] < 1e-12,
            "logged action path does not match the frozen recurrence/formula")
    out = study / "audits/TRAIN_SINGLE_SCENE_ACTION_CHAIN_AUDIT_v1.json"
    require(not out.exists(), f"refusing to overwrite audit: {out}")
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: audit_train_action_chain_v1.py STUDY_DIR")
    result = audit(Path(sys.argv[1]).resolve())
    print(json.dumps({k: result[k] for k in (
        "status", "study_id", "scene_id", "fold_id", "raw_sha256", "weights_identity_match",
        "online_replay", "action_formula", "downstream")}, indent=2))
