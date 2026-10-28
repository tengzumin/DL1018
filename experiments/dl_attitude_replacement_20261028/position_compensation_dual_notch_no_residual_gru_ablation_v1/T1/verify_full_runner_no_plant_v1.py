#!/usr/bin/env python3
"""Verify the isolated runner's locked no-Plant boundary and hook ordering."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "audits/DUAL_NOTCH_FULL_RUNNER_NO_PLANT_SOURCE_AUDIT_v1.json"
RUNNER = HERE / "candidate_runner_work/matlab/runtime/run_mlp15_dev72_closed_loop.m"
PREPARE = HERE / "candidate_runner_work/matlab/runtime/prepare_train_scene_no_plant.m"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    if OUT.exists():
        raise RuntimeError(f"Refusing to overwrite {OUT}")
    lock_path = HERE / "SOURCE_LOCK_NO_PLANT_v1.json"
    release_path = HERE / "RELEASE.json"
    noplant_path = HERE / "audits/NO_PLANT_PREFLIGHT_v1.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8-sig"))
    release = json.loads(release_path.read_text(encoding="utf-8-sig"))
    audit = json.loads(noplant_path.read_text(encoding="utf-8-sig"))
    lock_rows = {row["relative_path"]: row for row in lock["files"]}
    runner_hash = sha256(RUNNER)
    prepare_hash = sha256(PREPARE)
    required = {
        "candidate_runner_work/matlab/runtime/run_mlp15_dev72_closed_loop.m": runner_hash,
        "candidate_runner_work/matlab/runtime/prepare_train_scene_no_plant.m": prepare_hash,
        "candidate_runner_work/matlab/runtime/position_compensation_dual_notch_init.m": sha256(HERE / "candidate_runner_work/matlab/runtime/position_compensation_dual_notch_init.m"),
        "candidate_runner_work/matlab/runtime/position_compensation_dual_notch_step.m": sha256(HERE / "candidate_runner_work/matlab/runtime/position_compensation_dual_notch_step.m"),
    }
    for rel, expected in required.items():
        if rel not in lock_rows or lock_rows[rel]["sha256"].lower() != expected.lower():
            raise RuntimeError(f"Runner lock is missing or stale for {rel}")
    source = RUNNER.read_text(encoding="utf-8")
    residual_pos = source.index("residualFinal=min(max(")
    notch_pos = source.index("position_compensation_dual_notch_step(")
    force_pos = source.index("dF=stage1PositionHeldForce;", notch_pos)
    position_pos = source.index("[~,positionInfo]=position_bs_step(x(k,:).',r,dF,P);", force_pos)
    prepare_text = PREPARE.read_text(encoding="utf-8")
    no_plant_text = (HERE / "candidate_runner_work/matlab/runtime/run_train_pair_preflight_no_plant.m").read_text(encoding="utf-8")
    if ("w=load(weightsPath)" in prepare_text or "opts.stage1_position_runtime.residual_gru=" in prepare_text or
            "verify_train_oof_fold_matlab_parity(studyRoot)" in no_plant_text):
        raise RuntimeError("Disabled position GRU must remain hash-reference-only; no load or forward parity.")
    identity_pos = prepare_text.index("opts.gate_identity_lock=identity;")
    runtime_pos = prepare_text.index("opts.stage1_position_runtime.applied_acceleration_dual_notch=")
    if not residual_pos < notch_pos < force_pos < position_pos or not identity_pos < runtime_pos:
        raise RuntimeError("Dual-notch hook or runtime-only identity ordering is invalid.")
    if (release.get("status") != "PREPARED_NO_PLANT_PENDING_ROOT_AUDIT" or
            release.get("authorized_Plant_calls") != 0 or release.get("Plant_calls") != 0 or
            release.get("TEST_read") is not False or release.get("VAL_data_read") is not False or
            release.get("inertia_reconstruction_enabled") is not False or
            audit.get("status") != "PASS" or audit.get("Plant_calls") != 0 or
            audit.get("stopped_before_main_loop") is not True or
            audit.get("attempt_markers") != 0 or audit.get("first_plant_step_markers") != 0 or
            release.get("position_residual_gru", {}).get("enabled") is not False or
            audit.get("position_residual_gru_enabled") is not False or
            audit.get("residual_gru_runtime_field_present") is not False or
            audit.get("position_residual_gru_weights_deserialized") is not False or
            audit.get("no_position_gru_model_load_or_forward_call") is not True or
            audit.get("frozen_C5_exact_options_match") is not True):
        raise RuntimeError("Full runner no-Plant boundary did not satisfy the zero-call contract.")
    current_lock_hash = sha256(lock_path)
    if release.get("source_lock_sha256", "").lower() != current_lock_hash.lower() or \
            audit.get("source_lock_sha256", "").lower() != current_lock_hash.lower():
        raise RuntimeError("Release/audit source-lock hashes do not match the current lock.")
    result = {
        "schema": "POSITION_COMPENSATION_DUAL_NOTCH_FULL_RUNNER_NO_PLANT_SOURCE_AUDIT_V1",
        "status": "PASS_FULL_RUNNER_NOPLANT_BOUNDARY_HOOK_ORDER_AND_NO_POSITION_GRU",
        "study_id": release["study_id"],
        "scene_id": audit["scene_id"],
        "matlab_release": "R2025b",
        "runner_sha256": runner_hash,
        "prepare_wrapper_sha256": prepare_hash,
        "source_lock_sha256": current_lock_hash,
        "no_plant_preflight_sha256": sha256(noplant_path),
        "hook_order": ["frozen C5 action (position residual GRU absent)", "dual-notch update", "force hold assignment", "position_bs_step"],
        "stopped_before_main_loop": True,
        "Plant_calls": 0,
        "TEST_read": False,
        "VAL_read": False,
        "inertia_reconstruction_enabled": False,
        "attempt_markers": 0,
        "first_plant_step_markers": 0,
        "baseline_Q_task_are_measured_current_candidate_only": True,
        "intervention_Q_task_measured": False,
        "position_residual_gru_loaded": False,
        "position_residual_gru_runtime_field_present": False,
        "position_residual_gru_weights_deserialized": False,
        "no_position_gru_model_load_or_forward_call": True,
        "frozen_C5_exact_options_match": True,
        "frozen_replay_status_preserved": "FAIL_FIXED_FROZEN_REPLAY",
    }
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
