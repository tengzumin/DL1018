"""Score the frozen GRU tracking-head candidate against locked B/C5 raws.

Read-only with respect to inputs; creates new JSON/CSV/Markdown score artifacts.
Run only after the authorized full72 batch ledger is complete and audited.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import h5py
import numpy as np
from scipy.spatial.transform import Rotation


HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
ROOT = HERE.parents[3]
AUDIT = HERE
SCRIPT_PATH = Path(__file__).resolve()
LEDGER_PATH = AUDIT / "FULL72_PROGRESS_LEDGER_v02.json"
B_LINEAGE_REVIEW = (ROOT / "experiments" / "attitude_physics_inertia_observer_20261025" /
                    "paired_runner" / "morph_dev2_dev72_v1" / "review" /
                    "B72_LINEAGE_INDEPENDENT_REVIEW.md")
B_LINEAGE_REVIEW_SHA = "3083d9402224116b17bb2152bea2c39764c9a459d9d113aa603bff48c2a90130"
B_PARENT_RAW_REVIEW = (ROOT / "reports" / "paper_continuation_20261023" /
                       "baseline_b_dev72_parent_review" / "PARENT_B72_RAW_REVIEW.json")
B_PARENT_RAW_REVIEW_SHA = "d74725ef3b1e4957b7c813486a2ae95cc1f1ec13e82370545f7ec3c54d5b029e"
OUTPUTS = [AUDIT / name for name in (
    "FULL72_PAIRED_SCORE_v1.json",
    "FULL72_PAIRED_SCORE_v1.csv",
    "FULL72_AXES_PHASE_v1.csv",
    "FULL72_PAIRED_SCORE_v1.md",
)]
MAIN = ("Q_m", "task_SO3_rad", "inner_SO3_rad")
COMPARATORS = ("B", "C5")
WIN_TOL = 1e-12
MICRO_TOLS = (1e-6, 1e-5, 1e-4)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def readj(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def require(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)


def bound(path: Path, expected: str, label: str) -> str:
    require(path.is_file(), f"Missing {label}: {path}")
    actual = sha(path)
    require(actual.lower() == str(expected).lower(), f"{label} SHA-256 mismatch: {path}")
    return actual


def array(group, key: str, dtype=np.float64):
    return np.asarray(group[key][()], dtype=dtype)


def so3(a, b):
    return (Rotation.from_euler("xyz", b).inv() * Rotation.from_euler("xyz", a)).magnitude()


def wrap(a):
    return np.arctan2(np.sin(a), np.cos(a))


def classify(scene_id: str, split: str) -> list[str]:
    m = re.search(r"_W(\d{2})$", scene_id)
    require(m is not None, f"Cannot parse wind group from {scene_id}")
    w = int(m.group(1))
    wind_group = "HF_W09_W14" if 9 <= w <= 14 else ("W15" if w == 15 else "W00_W08")
    return ["ALL72", split, wind_group]


def score_raw(path: Path, gravity: float, max_tilt: float):
    with h5py.File(path, "r") as f:
        log = f["log"]
        state = array(log, "state").T
        time = array(log, "time").reshape(-1)
        ref_pos = array(f["scene/reference"], "position").T
        ref_acc = array(f["scene/reference"], "acceleration").T.copy()
        yaw = array(f["scene/reference"], "yaw").reshape(-1)
        inner = array(log, "filtered_attitude_reference").T
        motor = array(log, "motor_saturated", bool).T
        clipped = array(log, "generalized_clipped", bool).T
        tilt_limited = array(log, "tilt_limited", bool).reshape(-1)
        head_projected = (array(log, "attitude_head_projection_active", bool).reshape(-1)
                          if "attitude_head_projection_active" in log else None)
        head_saturated = (array(log, "attitude_head_output_saturated", bool).reshape(-1)
                          if "attitude_head_output_saturated" in log else None)

    require(state.shape == (20001, 12), f"Unexpected state shape in {path}: {state.shape}")
    require(ref_pos.shape == ref_acc.shape == (20001, 3), f"Unexpected reference shape in {path}")
    require(yaw.shape == (20001,) and inner.shape == (20000, 3), f"Unexpected attitude trace shape in {path}")
    require(time.shape == (20001,) and np.max(np.abs(np.diff(time) - 0.001)) < 1e-10,
            f"Unexpected time base in {path}")
    for name, value in (("state", state), ("time", time), ("position reference", ref_pos),
                        ("acceleration reference", ref_acc), ("yaw", yaw), ("inner reference", inner)):
        require(np.isfinite(value).all(), f"Non-finite {name} in {path}")

    ref_acc[:, 2] += gravity
    a = np.cos(yaw) * ref_acc[:, 0] + np.sin(yaw) * ref_acc[:, 1]
    b = np.sin(yaw) * ref_acc[:, 0] - np.cos(yaw) * ref_acc[:, 1]
    roll = np.arctan2(b, np.hypot(ref_acc[:, 2], a))
    pitch = np.arctan2(a, ref_acc[:, 2])
    scale = np.minimum(1.0, max_tilt / np.maximum(np.hypot(roll, pitch), np.finfo(float).eps))
    task = np.column_stack((roll * scale, pitch * scale, yaw))
    pos_error = state[:, :3] - ref_pos
    task_euler = wrap(task - state[:, 6:9])
    inner_euler = wrap(inner - state[:20000, 6:9])
    inner_time = time[:20000]
    masks = {
        "ALL": (np.ones(20001, dtype=bool), np.ones(20000, dtype=bool)),
        "0_5s": (time < 5.0, inner_time < 5.0),
        "15_20s": (time >= 15.0, inner_time >= 15.0),
    }
    phase = {}
    for name, (sm, im) in masks.items():
        phase[name] = {
            "state_samples": int(sm.sum()), "inner_samples": int(im.sum()),
            "position_xyz_rmse_m": np.sqrt(np.mean(pos_error[sm] ** 2, axis=0)).tolist(),
            "task_wrapped_euler_rmse_rad": np.sqrt(np.mean(task_euler[sm] ** 2, axis=0)).tolist(),
            "inner_wrapped_euler_rmse_rad": np.sqrt(np.mean(inner_euler[im] ** 2, axis=0)).tolist(),
        }
    result = {
        "Q_m": float(np.sqrt(np.mean(np.sum(pos_error ** 2, axis=1)))),
        "task_SO3_rad": float(np.sqrt(np.mean(so3(state[:, 6:9], task) ** 2))),
        "inner_SO3_rad": float(np.sqrt(np.mean(so3(state[:20000, 6:9], inner) ** 2))),
        "axis_phase": phase,
        "safety": {
            "motor_saturation_samples": int(np.any(motor, axis=1).sum()),
            "generalized_clip_samples": int(np.any(clipped, axis=1).sum()),
            "tilt_limited_samples": int(tilt_limited.sum()),
            "attitude_head_projection_samples": (int(head_projected.sum()) if head_projected is not None else None),
            "attitude_head_output_saturated_samples": (int(head_saturated.sum()) if head_saturated is not None else None),
        },
    }
    require(all(np.isfinite(result[k]) for k in MAIN), f"Non-finite score in {path}")
    return result


def validate_release():
    release_path = STUDY / "RELEASE.json"
    release = readj(release_path)
    require(release["status"] == "RELEASED" and release["study_id"] == "gru_stream_cosine_tracking_head_full72_v1",
            "Full72 release is not the expected active release")
    require(release["authorized_Plant_calls"] == 66 and release["Plant_calls"] == 0,
            "Release call authorization/counter mismatch")
    require(release["TEST_read"] is False and release["training_started_by_this_study"] is False,
            "Release violates no-TEST/no-new-training boundary")
    require(release["Plant_truth_deployment_input"] is False and release["true_inertia_reconstructed"] is False,
            "Release includes a disallowed Plant-truth or inertia input")
    model_sha = bound(Path(release["model_path"]), release["model_sha256"], "frozen model")
    training_config_path = Path(release["training_config_path"])
    training_config_sha = bound(training_config_path, release["training_config_sha256"], "training config")
    training_config = readj(training_config_path)
    decision_path = Path(release["root_release_decision_path"])
    decision_sha = bound(decision_path, release["root_release_decision_sha256"], "root decision")
    decision = readj(decision_path)
    require(decision["decision"] == "APPROVED_FOR_FROZEN_CANDIDATE_DEV72_SCREEN" and
            decision["approved_candidate_calls"] == 66 and decision["TEST_read"] is False and
            decision["training_runs"] == 0, "Root decision does not authorize this frozen DEV72 screen")
    require(decision["batch_runner_sha256"] == release["batch_runner_sha256"] and
            decision["approved_taskbook_sha256"] == release["taskbook_sha256"] and
            decision["precheck_sha256"] == release["full72_scene_array_precheck_sha256"] and
            decision["input_identity_sha256"] == release["full72_input_identity_sha256"] and
            decision["source_lock_sha256"] == release["source_lock_sha256"],
            "Decision and release bindings disagree")
    taskbook = STUDY / "IMPLEMENTATION_TASKBOOK_v1.md"
    bound(taskbook, release["taskbook_sha256"], "taskbook")
    manifest_path = STUDY / "MANIFEST.json"
    bound(manifest_path, release["manifest_sha256"], "manifest")
    precheck_path = Path(release["full72_scene_array_precheck_path"])
    precheck_sha = bound(precheck_path, release["full72_scene_array_precheck_sha256"], "scene-array precheck")
    precheck = readj(precheck_path)
    require(precheck["status"] == "PASS_NO_PLANT_ALL72_SCENE_ARRAY_EQUALITY" and
            precheck["scene_count"] == 72 and precheck["TEST_read"] is False and
            precheck["Plant_calls"] == 0 and precheck["training_runs"] == 0,
            "Scene-array precheck is not the locked no-Plant 72-scene pass")
    lock_path = STUDY / "SOURCE_LOCK_v1.json"
    bound(lock_path, release["source_lock_sha256"], "source lock")
    bound(STUDY / "SOURCE_DIFF_v1.json", release["source_diff_sha256"], "source diff")
    bound(AUDIT / "FULL72_INPUT_IDENTITY_POWERSHELL_v1.json", release["full72_input_identity_sha256"],
          "PowerShell input identity")
    bound(STUDY / "IMPLEMENTATION_STATUS_v1.json", release["implementation_status_sha256"],
          "implementation status")
    batch_path = Path(release["batch_runner_path"])
    bound(batch_path, release["batch_runner_sha256"], "batch runner")
    bound(Path(release["batch_runner_checkcode_log_path"]), release["batch_runner_checkcode_log_sha256"],
          "batch runner checkcode log")
    bound(Path(release["raw_audit_script_path"]), release["raw_audit_script_sha256"], "raw auditor")
    manifest = readj(manifest_path)
    require(manifest["status"] == "PASS_READ_ONLY_VALIDATION_BINDINGS" and len(manifest["records"]) == 72 and
            manifest["TEST_read"] is False, "Manifest is not the locked DEV/VAL cohort")
    require(len({r["scene_id"] for r in manifest["records"]}) == 72, "Manifest scene IDs are not unique")
    require(not any("TEST" in r["scene_id"] for r in manifest["records"]), "TEST scene found in manifest")
    training_identity = training_config["dataset_identity"]
    training_ids = training_identity["scene_ids_in_training_order"]
    manifest_ids = [r["scene_id"] for r in manifest["records"]]
    require(len(training_ids) == 72 and len(set(training_ids)) == 72 and set(training_ids) == set(manifest_ids),
            "Frozen model training scene IDs do not exactly match the 72-scene score cohort")
    require(set(training_identity["train_splits"]) == {"TRAIN_C5_24", "C5_VAL48_AS_DEV_TRAIN"} and
            training_config["TEST48_read"] is False and training_identity["TEST48_read"] is False,
            "Training provenance/split or TEST48-read declaration differs from the locked evidence")
    expected_ids = [r["scene_id"] for r in manifest["records"] if not r["candidate_reuse"]]
    require(release["authorized_scenes"] == decision["authorized_scene_order"] and
            len(expected_ids) == 66 and set(expected_ids) == set(release["authorized_scenes"]),
            "Release/decision scene order does not match the 66 unreused DEV/VAL rows")
    c5_lock_path = Path(release["c5_input_lock_path"])
    c5_lock_sha = bound(c5_lock_path, release["c5_input_lock_sha256"], "C5 input lock")
    c5_status_path = Path(release["c5_batch_status_path"])
    c5_status_sha = bound(c5_status_path, release["c5_batch_status_sha256"], "C5 batch status")
    c5_lock, c5_status = readj(c5_lock_path), readj(c5_status_path)
    pending = [r for r in manifest["records"] if r.get("c5_audit_status") == "RUN_COMPLETE_RAW_PENDING_AUDIT"]
    pending_by_id = {r["scene_id"]: r for r in pending}
    status_records = c5_status.get("records", [])
    require(len(pending) == 60 and len(pending_by_id) == 60 and len(status_records) == 60 and
            c5_status["status"] == "COMPLETE_RAW_PENDING_PARENT_AUDIT" and
            c5_status["completed_scenes"] == 60 and c5_status["plant_calls"] == 60 and
            c5_status["training_steps"] == 0 and c5_status["optimizer_steps"] == 0 and
            c5_status["TEST_accessed"] is False and
            c5_status["input_lock_sha256"].lower() == c5_lock_sha.lower(),
            "C5 batch status is not the locked 60-scene raw-pending record")
    pending_ids = set(pending_by_id)
    require(set(c5_lock["scene_ids_new_60"]) == pending_ids and
            set(c5_status["scene_ids_new_60"]) == pending_ids,
            "C5 lock/status/manifest do not identify the same 60 pending scenes")
    status_by_id = {r["scene_id"]: r for r in status_records}
    require(len(status_by_id) == 60 and set(status_by_id) == pending_ids,
            "C5 source status records do not exactly match the 60 pending manifest rows")
    for sid, rec in pending_by_id.items():
        source = status_by_id[sid]
        require(source["status"] == "RUN_COMPLETE_RAW_PENDING_AUDIT" and
                source["raw_path"] == rec["c5_raw_path"] and
                source["raw_sha256"].lower() == rec["c5_raw_sha256"].lower() and
                source["run_status_path"] == rec["c5_status_path"] and
                source["run_status_sha256"].lower() == rec["c5_status_sha256"].lower(),
                f"C5 source status record does not match pending manifest row {sid}")
    lineage_review_sha = bound(B_LINEAGE_REVIEW, B_LINEAGE_REVIEW_SHA, "B72 lineage review")
    parent_review_sha = bound(B_PARENT_RAW_REVIEW, B_PARENT_RAW_REVIEW_SHA, "B72 parent raw review")
    parent_review = readj(B_PARENT_RAW_REVIEW)
    parent_rows = parent_review.get("comparisons", [])
    manifest_ids = {r["scene_id"] for r in manifest["records"]}
    require(parent_review["status"] == "PASS_NEW_B72_TRACEABLE_EXACTLY_REPRODUCES_HISTORICAL_B" and
            parent_review["scene_count"] == 72 and parent_review["new_Plant_in_this_audit"] == 0 and
            parent_review["actual_new_batch_Plant"] == 71 and parent_review["reused_B1"] == 1 and
            parent_review["all_new_source_inventory_sha_verified"] is True and
            parent_review["TEST_accessed"] is False and parent_review["training_steps"] == 0 and
            parent_review["historical_runtime_identity_gap_closed"] is False and len(parent_rows) == 72 and
            {r["scene_id"] for r in parent_rows} == manifest_ids and
            all(r["numeric_arrays"] == 33 and r["all_arrays_equal"] is True and
                not r["differing_arrays"] and r["Q_new_minus_old_m"] == 0.0 for r in parent_rows),
            "B72 parent raw review is not the bound 72-scene exact numeric-array equivalence pass")
    return (release_path, release, decision_sha, manifest, precheck_sha, c5_lock_sha,
            c5_status_sha, model_sha, training_config_sha, training_config,
            lineage_review_sha, parent_review_sha, parent_review)


def main():
    for p in OUTPUTS:
        require(not p.exists(), f"Refusing to overwrite score output: {p}")
    (release_path, release, decision_sha, manifest, precheck_sha, c5_lock_sha,
     c5_status_sha, model_sha, training_config_sha, training_config,
     lineage_review_sha, parent_review_sha, parent_review) = validate_release()
    release_sha = sha(release_path)
    ledger = readj(LEDGER_PATH)
    ledger_sha = sha(LEDGER_PATH)
    require(ledger["status"] == "PASS_ALL_66_NEW_CANDIDATE_RAW_AUDITS" and
            ledger["authorized_calls"] == 66 and ledger["Plant_calls_started"] == 66 and
            ledger["completed_and_audited"] == 66 and ledger["failed_or_incomplete"] == 0 and
            ledger["TEST_read"] is False and ledger["release_sha256"].lower() == release_sha.lower(),
            "Full72 progress ledger is not a complete, audited 66-call run")
    ledger_rows = {r["scene_id"]: r for r in ledger["records"]}
    require(len(ledger_rows) == 66, "Ledger does not have exactly 66 unique new scene rows")

    constants_path = ROOT / "experiments" / "dl_attitude_replacement_20261026" / "mlp15_composite_dev_v3" / "RELEASE.json"
    constants = readj(constants_path)
    gravity = float(constants["gravity_mps2"])
    max_tilt = float(constants["max_tilt_rad"])
    formula_path = ROOT / "experiments" / "dl_attitude_replacement_20261026" / "mlp15_composite_dev_v3" / "audits" / "audit_composite_dev_raw.m"
    require(formula_path.is_file(), f"Missing established attitude formula: {formula_path}")
    constants_sha, formula_sha = sha(constants_path), sha(formula_path)

    rows = []
    c5_pending = []
    total_candidate_calls = 0
    for rec in manifest["records"]:
        sid = rec["scene_id"]
        methods = {}
        if rec["candidate_reuse"]:
            candidate_raw = Path(rec["candidate_raw_path"])
            candidate_status = Path(rec["candidate_status_path"])
            candidate_audit = Path(rec["candidate_audit_path"])
            cand_raw_sha = bound(candidate_raw, rec["candidate_raw_sha256"], f"reused candidate raw {sid}")
            cand_status_sha = bound(candidate_status, rec["candidate_status_sha256"], f"reused candidate status {sid}")
            cand_audit_sha = bound(candidate_audit, rec["candidate_audit_sha256"], f"reused candidate audit {sid}")
            status = readj(candidate_status)
            audit = readj(candidate_audit)
            require(status["state"] == "COMPLETED" and status["Plant_calls"] == 1 and
                    status["status_value"] == "STABLE" and status["TEST_read"] is False and
                    status["raw_sha256"].lower() == cand_raw_sha.lower(),
                    f"Invalid reused candidate status for {sid}")
            require(audit["status"] == "PASS_INDEPENDENT_GRU_STREAM_TRACKING_HEAD_RAW_REPLAY" and
                    audit["candidate_raw_sha256"].lower() == cand_raw_sha.lower() and
                    audit["model_sha256"].lower() == release["model_sha256"].lower() and
                    audit["release_sha256"].lower() == status["release_sha256"].lower() and
                    audit["TEST_read"] == 0 and audit["training_calls_by_audit"] == 0,
                    f"Invalid reused candidate audit for {sid}")
            candidate_call = int(status["Plant_calls"])
            candidate_release_sha = status["release_sha256"]
        else:
            lr = ledger_rows.get(sid)
            require(lr is not None and lr["state"] == "PASS_RAW_AUDITED" and lr["Plant_calls"] == 1,
                    f"Candidate scene is not completed and audited: {sid}")
            candidate_raw = Path(lr["raw_path"])
            candidate_status = candidate_raw.with_name("run_status.json")
            candidate_audit = Path(lr["audit_path"])
            cand_raw_sha = bound(candidate_raw, lr["raw_sha256"], f"candidate raw {sid}")
            cand_status_sha = sha(candidate_status)
            cand_audit_sha = sha(candidate_audit)
            status = readj(candidate_status)
            audit = readj(candidate_audit)
            require(lr["audit_status"] == "PASS_INDEPENDENT_GRU_STREAM_TRACKING_HEAD_RAW_REPLAY" and
                    status["state"] == "COMPLETED" and status["status_value"] == "STABLE" and
                    status["Plant_calls"] == 1 and status["TEST_read"] is False and
                    status["raw_sha256"].lower() == cand_raw_sha.lower() and
                    status["release_sha256"].lower() == release_sha.lower(),
                    f"Candidate run status mismatch for {sid}")
            require(audit["status"] == lr["audit_status"] and
                    audit["candidate_raw_sha256"].lower() == cand_raw_sha.lower() and
                    audit["model_sha256"].lower() == release["model_sha256"].lower() and
                    audit["release_sha256"].lower() == release_sha.lower() and
                    audit["TEST_read"] == 0 and audit["Plant_calls_by_audit"] == 0 and
                    audit["training_calls_by_audit"] == 0,
                    f"Candidate raw audit mismatch for {sid}")
            candidate_call = 1
            candidate_release_sha = status["release_sha256"]
        total_candidate_calls += candidate_call
        methods["Candidate"] = score_raw(candidate_raw, gravity, max_tilt)
        methods["Candidate"].update({
            "raw_path": str(candidate_raw), "raw_sha256": cand_raw_sha,
            "status_sha256": cand_status_sha, "audit_sha256": cand_audit_sha,
            "audit_status": audit["status"], "release_sha256": candidate_release_sha,
            "run_state": status["state"], "status_value": status["status_value"],
            "reused_parent_raw": bool(rec["candidate_reuse"]),
        })

        for name, raw_key, raw_sha_key, status_key, status_sha_key in (
            ("B", "b_raw_path", "b_raw_sha256", "b_status_path", "b_status_sha256"),
            ("C5", "c5_raw_path", "c5_raw_sha256", "c5_status_path", "c5_status_sha256"),
        ):
            raw_path, status_path = Path(rec[raw_key]), Path(rec[status_key])
            raw_sha = bound(raw_path, rec[raw_sha_key], f"{name} raw {sid}")
            status_sha = bound(status_path, rec[status_sha_key], f"{name} status {sid}")
            base_status = readj(status_path)
            test_flags_clear = (base_status.get("TEST_accessed") is False and
                                ("TEST_read" not in base_status or base_status["TEST_read"] is False))
            require(base_status.get("scene_id") == sid and
                    base_status.get("status") == "RUN_COMPLETE_RAW_PENDING_AUDIT" and
                    base_status.get("log_status") == "STABLE" and
                    base_status.get("safety_stop_reason") in (None, "", "NONE") and
                    base_status.get("transitions") == 20000 and base_status.get("state_samples") == 20001 and
                    base_status.get("plant_calls") == 1 and base_status.get("training_steps") == 0 and
                    base_status.get("optimizer_steps") == 0 and test_flags_clear and
                    base_status["raw_sha256"].lower() == raw_sha.lower(),
                    f"{name} run-status/scene/safety/budget/source identity mismatch for {sid}")
            methods[name] = score_raw(raw_path, gravity, max_tilt)
            methods[name].update({"raw_path": str(raw_path), "raw_sha256": raw_sha,
                                  "status_sha256": status_sha, "run_status": base_status["status"],
                                  "log_status": base_status["log_status"],
                                  "safety_stop_reason": base_status["safety_stop_reason"], "audit_status": rec.get(
                                      "c5_audit_status") if name == "C5" else "locked_B_source"})
            if name == "C5" and rec.get("c5_audit_status") == "RUN_COMPLETE_RAW_PENDING_AUDIT":
                c5_pending.append(sid)

        comp = {}
        for other in COMPARATORS:
            comp[other] = {}
            for metric in MAIN:
                delta = methods["Candidate"][metric] - methods[other][metric]
                comp[other][metric] = {
                    "delta_candidate_minus_comparator": float(delta),
                    "relative_change_pct": float(100 * delta / methods[other][metric]),
                    "win": bool(delta < -WIN_TOL), "loss": bool(delta > WIN_TOL),
                    "tie": bool(abs(delta) <= WIN_TOL),
                    "micro_sensitivity": {
                        f"tol_{tol:g}": {"win": bool(delta < -tol), "loss": bool(delta > tol),
                                         "tie": bool(abs(delta) <= tol)} for tol in MICRO_TOLS
                    },
                }
        groups = classify(sid, rec["source_split"])
        rows.append({"scene_id": sid, "split": rec["source_split"], "groups": groups,
                     "c5_audit_scope": rec.get("c5_audit_scope"), "methods": methods,
                     "candidate_vs": comp})

    require(len(rows) == 72 and total_candidate_calls == 72 and len(c5_pending) == 60,
            f"Expected 72 scored candidates (six reused), 72 total historical+new calls, and 60 pending C5 audits; got {len(rows)}, {total_candidate_calls}, {len(c5_pending)}")
    groups = {name: [r for r in rows if name in r["groups"]] for name in
              ("ALL72", "DEV", "VAL", "HF_W09_W14", "W15", "W00_W08")}
    expected_counts = {"ALL72": 72, "DEV": 24, "VAL": 48, "HF_W09_W14": 28, "W15": 6, "W00_W08": 38}
    for name, selected in groups.items():
        require(len(selected) == expected_counts[name], f"Unexpected {name} cohort size: {len(selected)}")

    summaries = {}
    for group, selected in groups.items():
        summaries[group] = {
            "scene_count": len(selected),
            "macro_mean": {method: {metric: float(np.mean([r["methods"][method][metric] for r in selected]))
                                     for metric in MAIN} for method in ("Candidate", "B", "C5")},
            "wins_losses_ties": {other: {metric: {
                outcome: sum(bool(r["candidate_vs"][other][metric][outcome]) for r in selected)
                for outcome in ("win", "loss", "tie")} for metric in MAIN} for other in COMPARATORS},
            "micro_sensitivity": {other: {metric: {tol: {
                outcome: sum(bool(r["candidate_vs"][other][metric]["micro_sensitivity"][f"tol_{tol:g}"][outcome])
                              for r in selected) for outcome in ("win", "loss", "tie")}
                for tol in MICRO_TOLS} for metric in MAIN} for other in COMPARATORS},
            "safety_sample_totals": {method: {
                key: (None if all(r["methods"][method]["safety"].get(key) is None for r in selected)
                      else int(sum((r["methods"][method]["safety"].get(key) or 0) for r in selected)))
                for key in ("motor_saturation_samples", "generalized_clip_samples", "tilt_limited_samples",
                            "attitude_head_projection_samples", "attitude_head_output_saturated_samples")}
                for method in ("Candidate", "B", "C5")},
        }

    wins_b_q = summaries["ALL72"]["wins_losses_ties"]["B"]["Q_m"]["win"]
    wins_b_so3 = summaries["ALL72"]["wins_losses_ties"]["B"]["task_SO3_rad"]["win"]
    all_safety = summaries["ALL72"]["safety_sample_totals"]["Candidate"]
    finite_audited = all(r["methods"]["Candidate"]["run_state"] == "COMPLETED" and
                         r["methods"]["Candidate"]["status_value"] == "STABLE" and
                         r["methods"]["Candidate"]["audit_status"] ==
                         "PASS_INDEPENDENT_GRU_STREAM_TRACKING_HEAD_RAW_REPLAY" and
                         r["methods"]["Candidate"]["safety"] is not None for r in rows)
    def mean_better(group, metric):
        return summaries[group]["macro_mean"]["Candidate"][metric] < \
               summaries[group]["macro_mean"]["B"][metric] - WIN_TOL
    def mean_no_worse(group, metric):
        return summaries[group]["macro_mean"]["Candidate"][metric] <= \
               summaries[group]["macro_mean"]["B"][metric] + WIN_TOL
    gates = {
        "at_least_62_of_72_wins_vs_B_Q": {"status": "PASS" if wins_b_q >= 62 else "FAIL", "observed": wins_b_q, "required": 62},
        "at_least_62_of_72_wins_vs_B_task_SO3": {"status": "PASS" if wins_b_so3 >= 62 else "FAIL", "observed": wins_b_so3, "required": 62},
        "ALL72_macro_Q_strictly_better_than_B": {"status": "PASS" if mean_better("ALL72", "Q_m") else "FAIL",
                                                  "candidate": summaries["ALL72"]["macro_mean"]["Candidate"]["Q_m"],
                                                  "B": summaries["ALL72"]["macro_mean"]["B"]["Q_m"]},
        "ALL72_macro_task_SO3_strictly_better_than_B": {"status": "PASS" if mean_better("ALL72", "task_SO3_rad") else "FAIL",
                                                        "candidate": summaries["ALL72"]["macro_mean"]["Candidate"]["task_SO3_rad"],
                                                        "B": summaries["ALL72"]["macro_mean"]["B"]["task_SO3_rad"]},
        "HF_macro_Q_no_worse_than_B": {"status": "PASS" if mean_no_worse("HF_W09_W14", "Q_m") else "FAIL",
                                        "candidate": summaries["HF_W09_W14"]["macro_mean"]["Candidate"]["Q_m"],
                                        "B": summaries["HF_W09_W14"]["macro_mean"]["B"]["Q_m"]},
        "HF_macro_task_SO3_no_worse_than_B": {"status": "PASS" if mean_no_worse("HF_W09_W14", "task_SO3_rad") else "FAIL",
                                               "candidate": summaries["HF_W09_W14"]["macro_mean"]["Candidate"]["task_SO3_rad"],
                                               "B": summaries["HF_W09_W14"]["macro_mean"]["B"]["task_SO3_rad"]},
        "W15_macro_Q_no_worse_than_B": {"status": "PASS" if mean_no_worse("W15", "Q_m") else "FAIL",
                                         "candidate": summaries["W15"]["macro_mean"]["Candidate"]["Q_m"],
                                         "B": summaries["W15"]["macro_mean"]["B"]["Q_m"]},
        "W15_macro_task_SO3_no_worse_than_B": {"status": "PASS" if mean_no_worse("W15", "task_SO3_rad") else "FAIL",
                                                "candidate": summaries["W15"]["macro_mean"]["Candidate"]["task_SO3_rad"],
                                                "B": summaries["W15"]["macro_mean"]["B"]["task_SO3_rad"]},
        "all_candidate_raws_complete_finite_and_audited": {"status": "PASS" if finite_audited else "FAIL", "scenes": len(rows)},
        "no_candidate_stop_motor_saturation_generalized_clip_or_tilt_limit": {
            "status": "PASS" if all(all_safety[k] == 0 for k in ("motor_saturation_samples", "generalized_clip_samples", "tilt_limited_samples")) else "FAIL",
            "sample_counts": {k: all_safety[k] for k in ("motor_saturation_samples", "generalized_clip_samples", "tilt_limited_samples")}},
    }
    gates["overall_frozen_DEV72_gate"] = {"status": "PASS" if all(g["status"] == "PASS" for k, g in gates.items() if k != "overall_frozen_DEV72_gate") else "FAIL",
                                          "basis": "Numeric frozen B-based DEV72 gates and candidate safety only. B parent raw-equivalence review passed; C5 pending audits do not affect this numeric result. This is not final paper evidence."}

    paired = []
    axes = []
    safety_keys = tuple(rows[0]["methods"]["Candidate"]["safety"].keys())
    for r in rows:
        flat = {"scene_id": r["scene_id"], "split": r["split"], "wind_group": next(g for g in r["groups"] if g not in ("ALL72", r["split"]))}
        for method in ("Candidate", "B", "C5"):
            m = r["methods"][method]
            for metric in MAIN:
                flat[f"{method}_{metric}"] = m[metric]
            for key in safety_keys:
                flat[f"{method}_{key}"] = m["safety"].get(key)
            flat[f"{method}_raw_sha256"] = m["raw_sha256"]
            flat[f"{method}_status_sha256"] = m["status_sha256"]
        for other in COMPARATORS:
            for metric in MAIN:
                c = r["candidate_vs"][other][metric]
                for outcome in ("win", "loss", "tie"):
                    flat[f"Candidate_{outcome}_vs_{other}_{metric}"] = c[outcome]
                flat[f"Candidate_delta_vs_{other}_{metric}"] = c["delta_candidate_minus_comparator"]
        paired.append(flat)
        for method in ("Candidate", "B", "C5"):
            for phase, values in r["methods"][method]["axis_phase"].items():
                pos, task, inner = values["position_xyz_rmse_m"], values["task_wrapped_euler_rmse_rad"], values["inner_wrapped_euler_rmse_rad"]
                axes.append({"scene_id": r["scene_id"], "split": r["split"], "method": method, "phase": phase,
                             "state_samples": values["state_samples"], "inner_samples": values["inner_samples"],
                             "position_x_rmse_m": pos[0], "position_y_rmse_m": pos[1], "position_z_rmse_m": pos[2],
                             "task_roll_wrapped_euler_rmse_rad": task[0], "task_pitch_wrapped_euler_rmse_rad": task[1],
                             "task_yaw_wrapped_euler_rmse_rad": task[2], "inner_roll_wrapped_euler_rmse_rad": inner[0],
                             "inner_pitch_wrapped_euler_rmse_rad": inner[1], "inner_yaw_wrapped_euler_rmse_rad": inner[2]})

    summary = {
        "schema": "DL1018_GRU_STREAM_TRACKING_HEAD_FULL72_PAIRED_SCORE_V1",
        "status": "SCORED_IN_SAMPLE_DEV_SCREEN_ONLY",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "candidate": release["candidate"], "model_sha256": release["model_sha256"],
        "scene_count": len(rows), "groups": summaries, "frozen_DEV72_gates": gates,
        "c5_audit_limitation": {"status": "PROVISIONAL_COMPARISON_ONLY",
            "pending_parent_audit_count": len(c5_pending), "pending_scene_ids": c5_pending,
            "note": "C5 paired values are computed from locked raw/status SHAs, but 60 sources remain RAW_PENDING_AUDIT; no C5 gate is claimed passed."},
        "resource_accounting": {"new_candidate_calls_authorized": 66, "new_candidate_calls_completed_and_audited": ledger["completed_and_audited"],
            "candidate_rows_including_six_reused": len(rows), "new_training_runs": 0,
            "inherited_frozen_training_steps": release["training_steps"], "baseline_reruns": 0,
            "TEST_read": False, "candidate_raw_bytes": int(sum(Path(r["methods"]["Candidate"]["raw_path"]).stat().st_size for r in rows))},
        "metric_definitions": {"Q_m": "RMS Euclidean position error across all 20001 states; scene-level macro averaging follows.",
            "task_SO3_rad": "Geodesic SO(3) RMSE of actual Euler attitude against task attitude reconstructed from reference acceleration, yaw, gravity and the frozen tilt cap.",
            "inner_SO3_rad": "Geodesic SO(3) RMSE of actual attitude against filtered_attitude_reference over 20000 transitions.",
            "axis_note": "Wrapped Euler axis RMSE is a coordinate diagnostic and does not replace SO(3).",
            "time_windows": "ALL: all states/transitions; 0_5s: t<5s; 15_20s: t>=15s, including state at 20s and transitions before 20s.",
            "win_tolerance": WIN_TOL, "micro_sensitivity_tolerances": list(MICRO_TOLS)},
        "metric_constants": {"gravity_mps2": gravity, "max_tilt_rad": max_tilt,
            "constants_release_path": str(constants_path), "constants_release_sha256": constants_sha,
            "formula_path": str(formula_path), "formula_sha256": formula_sha},
        "input_bindings": {"release_sha256": release_sha, "root_decision_sha256": decision_sha,
            "manifest_sha256": sha(STUDY / "MANIFEST.json"), "taskbook_sha256": sha(STUDY / "IMPLEMENTATION_TASKBOOK_v1.md"),
            "scene_array_precheck_sha256": precheck_sha, "source_lock_sha256": sha(STUDY / "SOURCE_LOCK_v1.json"),
            "progress_ledger_sha256": ledger_sha, "batch_runner_sha256": release["batch_runner_sha256"],
            "c5_input_lock_path": release["c5_input_lock_path"],
            "c5_input_lock_sha256": c5_lock_sha, "c5_batch_status_sha256": c5_status_sha,
            "c5_batch_status_path": release["c5_batch_status_path"],
            "c5_pending_status_records_verified": 60},
        "study_scope": {"label": "IN_SAMPLE_CLOSED_LOOP_DEVELOPMENT_SCREEN",
            "training_splits": training_config["dataset_identity"]["train_splits"],
            "training_scene_count": len(training_config["dataset_identity"]["scene_ids_in_training_order"]),
            "score_training_scene_overlap_count": 72, "model_sha256": model_sha,
            "training_config_path": release["training_config_path"], "training_config_sha256": training_config_sha,
            "independent_validation": False, "generalization_evidence": False, "TEST48_read": False,
            "interpretation": "All 72 DEV/VAL scenes in this closed-loop score were used to train the frozen model; treat this only as an in-sample development screen, not independent validation or generalization evidence. TEST48 remains sealed."},
        "B_baseline_audit_limitation": {"status": "PARENT_RAW_EQUIVALENCE_PASS_HISTORICAL_IDENTITY_GAP_REMAINS",
            "run_status_rows": len(rows),
            "run_complete_raw_pending_audit_rows": sum(r["methods"]["B"]["run_status"] == "RUN_COMPLETE_RAW_PENDING_AUDIT" for r in rows),
            "stable_log_status_rows": sum(r["methods"]["B"]["log_status"] == "STABLE" for r in rows),
            "raw_and_status_sha_verified_against_locked_manifest": True,
            "lineage_review_path": str(B_LINEAGE_REVIEW), "lineage_review_sha256": lineage_review_sha,
            "lineage_scope": "Independent lineage review validates 71 new B runs plus one completed reference and their locked raw/status sources.",
            "parent_raw_review_path": str(B_PARENT_RAW_REVIEW), "parent_raw_review_sha256": parent_review_sha,
            "parent_raw_review_status": parent_review["status"], "parent_review_scene_count": parent_review["scene_count"],
            "numeric_arrays_per_scene": 33, "all_72_new_vs_historical_arrays_equal": True,
            "new_batch_Plant_calls": parent_review["actual_new_batch_Plant"], "reused_B1_scenes": parent_review["reused_B1"],
            "historical_runtime_identity_gap_closed": False, "fresh_equation_derivation_completed": False,
            "limitation": "B raw/status lineage and the 72-scene parent raw-equivalence review pass are preserved; run-status labels remain RUN_COMPLETE_RAW_PENDING_AUDIT. The review shows exact equality across 33 numeric arrays per scene, but does not close historical runtime identity or provide a fresh equation derivation. B numeric gates may be reported with this qualification; C5 parent audit remains pending."},
        "paper_evidence_status": "INCOMPLETE_C5_PARENT_AUDIT_PENDING",
        "scorer": {"path": str(SCRIPT_PATH), "sha256": sha(SCRIPT_PATH)},
        "rows": rows,
    }
    with OUTPUTS[0].open("x", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
        f.write("\n")
    for path, values in ((OUTPUTS[1], paired), (OUTPUTS[2], axes)):
        with path.open("x", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=list(values[0]))
            writer.writeheader()
            writer.writerows(values)
    lines = ["# GRU tracking-head full72 paired score", "",
             "Read-only scoring of the frozen 72-scene DEV/VAL cohort; no baseline reruns, training, or TEST access.", "",
             "**Scope: in-sample closed-loop development screen only.** The frozen model was trained on the same 72 DEV/VAL scenes scored here, so these results are not independent validation or generalization evidence. TEST48 remains sealed.", "",
             f"Training model SHA-256: `{model_sha}`; training-config SHA-256: `{training_config_sha}`.", "",
             f"**B baseline qualification:** {summary['B_baseline_audit_limitation']['run_complete_raw_pending_audit_rows']}/72 run-status labels remain `RUN_COMPLETE_RAW_PENDING_AUDIT` (all stable; raw/status SHAs locked). The bound parent review passes exact new-vs-historical equality for 33 numeric arrays on all 72 scenes and the lineage review validates 71+1 sources. Historical runtime identity remains unclosed and no fresh equation derivation is claimed. C5 still has 60 raw-pending parent audits; the numeric B gate is not complete paper evidence.", "",
             "## Macro means", "", "| Group | N | Method | Q (mm) | Task SO(3) (mrad) | Inner SO(3) (mrad) |", "|---|---:|---|---:|---:|---:|"]
    for group in summaries:
        for method in ("Candidate", "B", "C5"):
            m = summaries[group]["macro_mean"][method]
            lines.append(f"| {group} | {summaries[group]['scene_count']} | {method} | {1000*m['Q_m']:.6f} | {1000*m['task_SO3_rad']:.6f} | {1000*m['inner_SO3_rad']:.6f} |")
    lines += ["", "## Frozen DEV72 gates", ""]
    lines += [f"- {key}: **{value['status']}**" for key, value in gates.items()]
    lines += ["", f"C5 comparison is provisional: {len(c5_pending)}/72 locked C5 sources remain pending parent raw audit; no C5 gate is claimed.",
              "SO(3) is the primary attitude metric. Wrapped Euler axes are diagnostics only.", "",
              f"Scorer SHA-256: `{summary['scorer']['sha256']}`.",
              f"Paired rows: `{OUTPUTS[1].name}`; phase/axis details: `{OUTPUTS[2].name}`.", ""]
    OUTPUTS[3].write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": summary["status"], "outputs": [str(p) for p in OUTPUTS],
                      "gates": gates, "groups": {g: summaries[g]["macro_mean"] for g in summaries},
                      "C5_pending_audits": len(c5_pending)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
