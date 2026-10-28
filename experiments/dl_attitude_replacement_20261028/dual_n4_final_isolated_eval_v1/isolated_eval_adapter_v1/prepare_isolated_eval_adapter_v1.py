#!/usr/bin/env python
"""Lock-check and statically adapt the isolated 72 scene payloads; never runs a controller."""
from collections import Counter
import hashlib
import json
import re
from pathlib import Path

import numpy as np
from scipy.io import loadmat


HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
REPO = HERE.parents[3]
CG48 = REPO / "experiments/dl_attitude_replacement_20261028/cg48_v2"
TRAIN = REPO / "experiments/dl_attitude_replacement_20261028/causal_n4_gate_train24_batch_v2"
TASK_NAMES = {"T1": "HELIX", "T2": "FIG8_3D", "T3": "SQUARE"}
ID_RE = re.compile(r"^DUALN4_EVAL72_V1_(T[123])_(LOW|MID|HIGH|CONSTANT|FREQ_SHIFT|AMP_SHIFT)_(M0[1-4])$")
N = 20001
DT = 0.001


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def finite_shape(value, shape, label):
    a = np.asarray(value)
    require(a.shape == shape, f"{label}: shape {a.shape}, expected {shape}")
    require(np.isfinite(a).all(), f"{label}: non-finite values")
    return a


def get_struct(parent, name):
    value = getattr(parent, name)
    return value


def controller_variants():
    return [
        {
            "method_id": "B_RBF_POS_RBF_ATT",
            "label": "B",
            "position": "legacy RBF position",
            "attitude": "RBF attitude",
            "current_entry_reference": "run_episode_dl1018(scene, 'B', cfg, controller_options_dl1018(cfg, 'B'))",
            "freeze_required": True,
        },
        {
            "method_id": "C5_DSSM14_RBF_ATT",
            "label": "C5",
            "position": "DSSM14 C5 M110",
            "attitude": "RBF attitude",
            "current_entry_reference": "run_episode_dl1018(scene, 'C5', cfg, frozen_C5_opts)",
            "freeze_required": True,
        },
        {
            "method_id": "PARENT_DSSM14_GRU_ATT",
            "label": "parent",
            "position": "DSSM14 C5 M110",
            "attitude": "frozen GRU_STREAM",
            "current_entry_reference": "run_mlp15_dev72_closed_loop(scene, cfg, parent_opts)",
            "freeze_required": True,
        },
        {
            "method_id": "GATEN4_DUAL_LOOP",
            "label": "gateN4 dual-loop",
            "position": "DSSM14 C5 M110 plus frozen N4 gate runtime",
            "attitude": "GRU_STREAM unless the frozen dual-loop contract specifies otherwise",
            "current_entry_reference": "run_mlp15_dev72_closed_loop(scene, cfg, gated_opts)",
            "current_runner_hook": "Stage-1 position applied_acceleration_static_n4; current copied runtime does not expose a separate attitude N4 hook.",
            "freeze_required": True,
            "root_contract_check_required": "Confirm whether dual-loop means N4 acts in both position and attitude loops; existing VAL48 code evidences the position-side hook only.",
        },
        {
            "method_id": "C5_GATEN4_NO_GRU_ATT",
            "label": "C5 + gateN4, no GRU attitude",
            "position": "DSSM14 C5 M110 plus the same frozen N4 gate runtime",
            "attitude": "RBF attitude; GRU model/runtime absent",
            "current_entry_reference": "run_mlp15_dev72_closed_loop(scene, cfg, C5_RBF_gated_opts)",
            "current_runner_hook": "Stage-1 position applied_acceleration_static_n4; use C5_RBF arm and assert no GRU model/runtime field.",
            "freeze_required": True,
        },
    ]


def main():
    specs_path = STUDY / "SCENE_SPECS_v1.json"
    config_path = STUDY / "GENERATOR_CONFIG_v1.json"
    context_path = STUDY / "SOURCE_CONTEXT_v1.json"
    audit_path = STUDY / "GENERATION_AUDIT_v1.json"
    builder_path = STUDY / "build_scene_queue.py"
    source_lock_path = STUDY / "SOURCE_LOCK_v1.json"
    specs, config = read_json(specs_path), read_json(config_path)
    context, generation_audit = read_json(context_path), read_json(audit_path)
    source_lock = read_json(source_lock_path)

    source_files = {
        "run_comparison.m": REPO / "run_comparison.m",
        "make_paired_dev58_scene.m": TRAIN / "candidate_runner_work/matlab/scenes/make_paired_dev58_scene.m",
        "wind_velocity_profile.m": TRAIN / "candidate_runner_work/matlab/core/wind_velocity_profile.m",
        "tcn0916_morphology_scenario.m": TRAIN / "candidate_runner_work/matlab/core/tcn0916_morphology_scenario.m",
        "tcn0916_topologies.m": TRAIN / "candidate_runner_work/matlab/core/tcn0916_topologies.m",
    }
    require(specs["schema"] == "DUALN4_EVAL72_SCENE_SPECS_V1" and specs["spec_count"] == 72,
            "Unexpected scene spec schema/count")
    require(config["schema"] == "DUALN4_EVAL72_GENERATOR_CONFIG_V1", "Unexpected generator config schema")
    require(source_lock["schema"] == "DUALN4_EVAL72_SOURCE_LOCK_V1", "Unexpected source lock schema")
    require(source_lock["status"] == "FROZEN_SCENES_PENDING_CANDIDATE_FREEZE", "Source lock is not in expected sealed state")
    require(generation_audit["status"] == "PASS_FULL_PAYLOADS" and generation_audit["generated_payload_count"] == 72,
            "Generation audit does not certify all 72 payloads")
    require(all(source_lock[k] == 0 for k in ("Plant_calls", "controller_calls", "score_calls")),
            "Generation SOURCE_LOCK reports a nonzero run/score call")
    require(generation_audit["Plant_calls"] == generation_audit["controller_calls"] == generation_audit["score_calls"] == 0,
            "Generation audit reports a nonzero run/score call")
    require(source_lock["modified_current_batch"] is False and generation_audit["modified_current_batch"] is False,
            "Generation modified an existing batch")
    policy = specs["controller_input_policy"]
    require(policy["environment_wind_exposed_to_controller"] is False
            and policy["future_samples_exposed_to_controller"] is False
            and policy["model_weights_in_scene_payload"] is False,
            "Scene input policy is not causal/model-free")
    require(source_lock["spec_sha256"] == sha256(specs_path), "Scene spec hash mismatch")
    require(source_lock["generator_config_sha256"] == sha256(config_path), "Generator config hash mismatch")
    require(source_lock["source_context_sha256"] == sha256(context_path), "Source context hash mismatch")
    require(source_lock["builder_sha256"] == sha256(builder_path), "Scene builder hash mismatch")
    for name, path in source_files.items():
        require(path.is_file() and source_lock["formula_source_sha256"].get(name) == sha256(path),
                f"Formula source hash mismatch: {name}")

    cases = specs["cases"]
    require(len(cases) == 72 and len({c["scene_id"] for c in cases}) == 72, "Scene IDs are not unique 72")
    require(set(source_lock["payload_sha256"]) == {Path(c["payload_path"]).name for c in cases},
            "Payload inventory differs from frozen specs")
    require({(c["task_code"], c["wind_class"], c["morph_id"]) for c in cases}
            == {(t, w, m) for t in TASK_NAMES for w in ("LOW", "MID", "HIGH", "CONSTANT", "FREQ_SHIFT", "AMP_SHIFT")
                for m in ("M01", "M02", "M03", "M04")},
            "Scene spec does not cover the complete task/wind/morphology product")

    records, shape_counts = [], Counter()
    for case in cases:
        sid = case["scene_id"]
        match = ID_RE.fullmatch(sid)
        require(match is not None, f"Unsupported isolated scene ID: {sid}")
        task_code, wind_class, morph_id = match.groups()
        require((task_code, wind_class, morph_id) == (case["task_code"], case["wind_class"], case["morph_id"]),
                f"ID/spec metadata mismatch for {sid}")
        require(case["task"] == TASK_NAMES[task_code], f"Task-name mismatch for {sid}")
        payload_path = (STUDY / case["payload_path"]).resolve()
        require(payload_path.parent == (STUDY / "payloads").resolve() and payload_path.is_file(),
                f"Missing or out-of-root payload for {sid}")
        payload_sha = sha256(payload_path)
        require(payload_sha == source_lock["payload_sha256"][payload_path.name], f"Payload hash mismatch: {sid}")

        mat = loadmat(payload_path, squeeze_me=True, struct_as_record=False)
        require(set(k for k in mat if not k.startswith("__")) == {"scene"}, f"MAT fields mismatch: {sid}")
        scene = mat["scene"]
        require(scene.scene_id == sid, f"Payload scene_id mismatch: {sid}")
        require(scene.reference_contract_id == config["reference_contract_id"], f"Reference contract mismatch: {sid}")
        time = np.asarray(scene.time).reshape(-1)
        require(time.size == N and np.isfinite(time).all() and np.max(np.abs(time - np.arange(N) * DT)) < 1e-12,
                f"Time vector mismatch: {sid}")
        finite_shape(scene.initial_state, (12,), f"{sid}.initial_state")
        ref = scene.reference
        for key in ("position", "velocity", "acceleration"):
            finite_shape(get_struct(ref, key), (N, 3), f"{sid}.reference.{key}")
        for key in ("yaw", "yaw_rate", "yaw_acceleration"):
            require(np.asarray(get_struct(ref, key)).size == N and np.isfinite(get_struct(ref, key)).all(),
                    f"{sid}.reference.{key} malformed")
        arms = scene.arms
        for key in ("command", "rho_true", "rho_hat", "rhoDot_true", "rhoDot_hat"):
            finite_shape(get_struct(arms, key), (N, 4), f"{sid}.arms.{key}")
        rho = np.asarray(arms.rho_true)
        require(float(rho.min()) >= 0.15 - 1e-12 and float(rho.max()) <= 0.25 + 1e-12,
                f"{sid}.rho_true violates geometry bounds")
        require(float(np.max(np.abs(arms.rhoDot_true))) <= 0.05 + 1e-12,
                f"{sid}.rhoDot_true violates speed bound")
        finite_shape(scene.environment_wind_I, (N, 3), f"{sid}.environment_wind_I")
        expected_fields = {"scene_id", "time", "initial_state", "reference", "arms",
                           "environment_wind_I", "reference_contract_id"}
        require(set(scene._fieldnames) == expected_fields, f"Unexpected payload field/weight: {sid}")

        shape_counts["time_20001"] += 1
        shape_counts["reference_20001x3"] += 3
        shape_counts["arms_20001x4"] += 5
        records.append({
            "scene_id": sid,
            "task_code": task_code,
            "task": case["task"],
            "wind_class": wind_class,
            "morph_id": morph_id,
            "seed": case["seed"],
            "payload_path": case["payload_path"],
            "payload_sha256": payload_sha,
            "reference_contract_id": scene.reference_contract_id,
            "time_samples": N,
            "dt_s": DT,
            "state_shape": [12, 1],
            "reference_shape_xyz": [N, 3],
            "arms_shape": [N, 4],
            "environment_wind_shape": [N, 3],
        })

    # Pin the exact existing cg48 inputs inspected for later adapter review.
    reused_paths = [
        CG48 / "run_val48_batch_v2.m",
        CG48 / "runtime/prepare_cg48_val48_scene_no_plant.m",
        CG48 / "candidate_runner_work/matlab/runtime/validate_val48_scene_binding_v1.m",
        CG48 / "candidate_runner_work/matlab/runtime/run_mlp15_dev72_closed_loop.m",
        CG48 / "candidate_runner_work/matlab/runtime/run_gate_holdout_closed_loop.m",
        CG48 / "candidate_runner_work/matlab/runtime/make_gate_holdout_options.m",
        CG48 / "candidate_runner_work/matlab/runtime/make_paired_c5_options.m",
        CG48 / "score_val48_batch_v2.py",
        REPO / "run_comparison.m",
    ]
    cg48_lock = read_json(CG48 / "SOURCE_LOCK_VAL48_v1.json")
    locked_by_path = {str(Path(x["path"]).resolve()).lower(): x["sha256"] for x in cg48_lock.get("files", [])}
    reused = []
    for path in reused_paths:
        require(path.is_file(), f"Missing runner source: {path}")
        digest = sha256(path)
        lock_digest = locked_by_path.get(str(path.resolve()).lower())
        # run_comparison is a pinned upstream source; the other copied sources must be in cg48's file inventory.
        if path != REPO / "run_comparison.m":
            require(lock_digest == digest, f"cg48 lock mismatch for runner source: {path.name}")
        reused.append({"path": path.relative_to(REPO).as_posix(), "sha256": digest,
                       "cg48_source_lock_sha256": lock_digest})

    index = {
        "schema": "ISOLATED_EVAL_ADAPTER_SCENE_INDEX_V1",
        "status": "PASS_STATIC_INPUT_VALIDATION_NOT_RUN_AUTHORIZED",
        "study_id": specs["study_id"],
        "source_namespace": config["id_namespace"],
        "source_lock_sha256": sha256(source_lock_path),
        "spec_sha256": sha256(specs_path),
        "generator_config_sha256": sha256(config_path),
        "source_context_sha256": sha256(context_path),
        "controller_input_policy": policy,
        "record_count": len(records),
        "records": records,
    }
    plan = {
        "schema": "ISOLATED_EVAL_ADAPTER_BATCH_PLAN_V1",
        "status": "PREPARED_PENDING_TRAIN_FREEZE_AND_ROOT_RELEASE",
        "source_split": "ISOLATED_EVAL72",
        "scene_count": 72,
        "method_count": 5,
        "planned_runs_if_released": 360,
        "authorized_Plant_calls": 0,
        "Plant_calls": 0,
        "controller_calls": 0,
        "score_calls": 0,
        "TEST_read": False,
        "new72_used_for_training_or_tuning": False,
        "training_and_candidate_source_freeze_required_before_release": True,
        "per_scene_method_order": [x["method_id"] for x in controller_variants()],
        "variants": controller_variants(),
        "controller_source_freeze_status": "PENDING; this prep does not load model weights or authorise a run.",
    }
    outputs = {
        "SCENE_INDEX_v1.json": index,
        "BATCH_PLAN_PREP_v1.json": plan,
    }
    for name, value in outputs.items():
        (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    audit = {
        "schema": "ISOLATED_EVAL_ADAPTER_STATIC_AUDIT_V1",
        "status": "PASS_STATIC_PAYLOAD_SHAPES",
        "source_lock_status": source_lock["status"],
        "scene_count": len(records),
        "task_counts": dict(Counter(r["task"] for r in records)),
        "task_code_counts": dict(Counter(r["task_code"] for r in records)),
        "wind_class_counts": dict(Counter(r["wind_class"] for r in records)),
        "morphology_counts": dict(Counter(r["morph_id"] for r in records)),
        "payload_hashes_verified": len(records),
        "payload_shape_checks": dict(shape_counts),
        "cg48_runner_sources_checked": reused,
        "limitations": {
            "new72_controller_or_score_run": False,
            "raw_run_or_score_outputs_read": False,
            "MATLAB_invoked": False,
            "baseline_weights_loaded": False,
            "Plant_calls": 0,
            "controller_calls": 0,
            "score_calls": 0,
            "TEST_read": False,
            "inertia_reconstruction": False,
            "new72_used_for_training_or_tuning": False,
        },
    }
    audit_path = HERE / "STATIC_ADAPTER_AUDIT_v1.json"
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lock_files = [
        {"path": path.relative_to(REPO).as_posix(), "sha256": sha256(path)}
        for path in (specs_path, config_path, context_path, audit_path, builder_path, source_lock_path,
                     HERE / "load_isolated_eval_scene_no_plant.m", HERE / "SCENE_INDEX_v1.json",
                     HERE / "BATCH_PLAN_PREP_v1.json", HERE / "STATIC_ADAPTER_AUDIT_v1.json")
    ]
    lock_files += [{"path": r["payload_path"], "sha256": r["payload_sha256"]} for r in records]
    lock_files += reused
    adapter_lock = {
        "schema": "ISOLATED_EVAL_ADAPTER_SOURCE_LOCK_V1",
        "status": "STATIC_VALIDATION_ONLY_NO_RUN_AUTHORIZATION",
        "study_id": specs["study_id"],
        "source_namespace": config["id_namespace"],
        "files": lock_files,
        "scene_count": 72,
        "method_count": 5,
        "planned_runs_if_released": 360,
        "authorized_Plant_calls": 0,
        "Plant_calls": 0,
        "controller_calls": 0,
        "score_calls": 0,
        "TEST_read": False,
        "new72_used_for_training_or_tuning": False,
    }
    lock_path = HERE / "ADAPTER_SOURCE_LOCK_v1.json"
    lock_path.write_text(json.dumps(adapter_lock, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": audit["status"], "scene_count": len(records),
                      "payload_hashes_verified": len(records), "planned_runs_if_released": 360,
                      "authorized_Plant_calls": 0, "adapter_lock": str(lock_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
