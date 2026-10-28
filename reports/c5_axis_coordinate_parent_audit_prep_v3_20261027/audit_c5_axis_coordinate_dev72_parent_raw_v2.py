"""Prepared v2, fail-closed C5 axis-coordinate DEV72 parent raw auditor.

This file is intentionally inert unless --execute-after-root-review is passed.
It reads only the v3 axis-coordinate C5 batch, reuses the locked prior 12 C5
screen audits by raw/status SHA, and audits the remaining 60 in one sequential
loop. It never launches MATLAB/Plant, training, retries, or TEST access.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import h5py
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
PREP = Path(__file__).resolve().parent
C5 = ROOT / "experiments" / "position_axis_coordinate_c5_dev72_20261023"
FULL72_AUDIT = (ROOT / "experiments" / "dl_attitude_replacement_20261026" /
                "gru_stream_cosine_tracking_head_full72_v1" / "audits")
PRIOR_AUDIT = (ROOT / "reports" / "paper_continuation_20261023" /
               "c5_axis_coordinate_parent_review")
PRIOR_SCREEN = PRIOR_AUDIT / "screen12_parent_review" / "SUMMARY.json"
METRIC_SCORER = (ROOT / "reports" / "delayed_prediction_c3_dev72_parent_20261023" /
                 "parent_raw_metrics.py")
MAT_DECODER = ROOT / "reports" / "paper14_v2" / "phase1" / "audit_w15_position_replay.py"

LOCK_PATH = C5 / "C5_DEV72_INPUT_LOCK_v3.json"
STATUS_PATH = C5 / "C5_DEV72_BATCH_STATUS_v3.json"
SOURCE_PATH = C5 / "C5_DEV72_SOURCE_BINDING_v3.json"
RELEASE_PATH = C5 / "C5_DEV72_RELEASE_v3.json"
CONTRACT_PATH = C5 / "C5_DEV72_RUN_CONTRACT_v3.json"
PARENT_RELEASE_PATH = C5 / "C5_DEV72_PARENT_RELEASE_CONTRACT_v3.json"
PREPARE_PATH = C5 / "C5_DEV72_PREPARE_RESULT_v3.json"
BODY_PATH = C5 / "C5_DEV72_BODY_COMPLETE_v3.json"
FULL72_SCORE_PATH = FULL72_AUDIT / "FULL72_PAIRED_SCORE_v1.json"
FULL72_SCORER_PATH = FULL72_AUDIT / "score_full72_candidate_v1.py"

EXPECTED_SHA256 = {
    "c5_input_lock": "82024c01276cc4bfbd9b7772cf5332dee3fdfcbed422969589b68f1c90ed2d75",
    "c5_batch_status": "20cc9caca553ebf676fd7b39087fe0a2640fcd976aaf7c8cdb0030c76b5bea22",
    "c5_source_binding": "360fe096bdcdfefcdb320469736596c44587f07cc7e40c97e61ed318ecf95934",
    "c5_release": "4177f92a83a2a2ba80a98b3a8fb2f7806d64c3e6322ff3ce637a605db319f053",
    "c5_run_contract": "6ac3cd505dc13fc5b7e6e0cdef966b21225b54d6f847d32177d43f7c678c8150",
    "c5_parent_release_contract": "3e7106037c4176027ec07e8769284ac39007c634d307839d5e36da2726adc27e",
    "c5_prepare_result": "ca1fbd9bdf2d7a7b02b15d36ed010fbb1851b4607394c426f6d4d6d408ce3095",
    "c5_body_complete": "ea205a0cdd46026112d5381910887f71f3103d71d495980b504c06be3772b4c5",
    "full72_score": "d197cd0e7fc580b6b575ec193571dc595a4527f3bbba2c0e7e0b48daf021b0ff",
    "full72_scorer": "6baf689802f4d73ead813449e52a8fe85cb0be92c3185850c93646da2d54dd16",
    "prior_screen12_audit": "fe217ac8b259706b1953e07dd44586b6a64368a6d4f5e0145e8f507863d82ad8",
    "legacy_c5_raw_checker": "59cb79f91d49e3d5ca3c268007038a66a3692f75a2cd354535f13cb8ad39fdcb",
    "position_metric_scorer": "c64482d0adbc4358417648ec08351bd78f1d3dbdb38950435fa71b9cb0f531b1",
    "matlab_v73_decoder": "372d92cb17da99884e742d3fa0c877200c3bb2bc6fac7f10e7a1a046b97a76af",
    # This is the upstream C5 screen lock bound by the 12 reused v1 audits;
    # it is not the SHA-256 of C5_DEV72_INPUT_LOCK_v3.json above.
    "prior_screen_input_lock": "10a7eea144e3574e05eea7b4f7b56112595eac0c81d27b5e8c7a5a41499f84b0",
    "c5_prepared_snapshot": "842ef395569e675db6e139c2684d72b976946915e5e0a58b9b7f24ec10c1d24a",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256(path: Path) -> str:
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def bind(path: Path, expected: str, label: str) -> str:
    require(Path(path).is_file(), f"Missing {label}: {path}")
    actual = sha256(path)
    require(actual.lower() == expected.lower(),
            f"{label} SHA mismatch: expected {expected}, got {actual}")
    return actual


def read_json(path: Path) -> dict:
    with Path(path).open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def same_path(left: str | Path, right: str | Path) -> bool:
    return Path(left).resolve() == Path(right).resolve()


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_metadata_bindings() -> dict:
    """Validate only locked JSON/source identities before any raw is opened."""
    inputs = {
        "c5_input_lock": bind(LOCK_PATH, EXPECTED_SHA256["c5_input_lock"], "C5 v3 input lock"),
        "c5_batch_status": bind(STATUS_PATH, EXPECTED_SHA256["c5_batch_status"], "C5 v3 batch status"),
        "c5_source_binding": bind(SOURCE_PATH, EXPECTED_SHA256["c5_source_binding"], "C5 v3 source binding"),
        "c5_release": bind(RELEASE_PATH, EXPECTED_SHA256["c5_release"], "C5 v3 release"),
        "c5_run_contract": bind(CONTRACT_PATH, EXPECTED_SHA256["c5_run_contract"], "C5 v3 run contract"),
        "c5_parent_release_contract": bind(PARENT_RELEASE_PATH,
            EXPECTED_SHA256["c5_parent_release_contract"], "C5 v3 parent release contract"),
        "c5_prepare_result": bind(PREPARE_PATH, EXPECTED_SHA256["c5_prepare_result"], "C5 v3 prepare result"),
        "c5_body_complete": bind(BODY_PATH, EXPECTED_SHA256["c5_body_complete"], "C5 v3 body-complete receipt"),
        "full72_score": bind(FULL72_SCORE_PATH, EXPECTED_SHA256["full72_score"], "Full72 paired score"),
        "full72_scorer": bind(FULL72_SCORER_PATH, EXPECTED_SHA256["full72_scorer"], "Full72 scorer"),
        "prior_screen12_audit": bind(PRIOR_SCREEN, EXPECTED_SHA256["prior_screen12_audit"], "Prior C5 screen12 parent audit"),
        "legacy_c5_raw_checker": bind(PRIOR_AUDIT / "check_c5_raw_parent.py",
            EXPECTED_SHA256["legacy_c5_raw_checker"], "Legacy C5 parent checker"),
        "position_metric_scorer": bind(METRIC_SCORER,
            EXPECTED_SHA256["position_metric_scorer"], "Position metric scorer"),
        "matlab_v73_decoder": bind(MAT_DECODER,
            EXPECTED_SHA256["matlab_v73_decoder"], "MATLAB v7.3 decoder"),
    }
    lock = read_json(LOCK_PATH)
    status = read_json(STATUS_PATH)
    source = read_json(SOURCE_PATH)
    release = read_json(RELEASE_PATH)
    contract = read_json(CONTRACT_PATH)
    parent_release = read_json(PARENT_RELEASE_PATH)
    prepare = read_json(PREPARE_PATH)
    body = read_json(BODY_PATH)
    score = read_json(FULL72_SCORE_PATH)
    prior = read_json(PRIOR_SCREEN)

    require(lock.get("schema") == "C5_AXIS_COORDINATE_DEV72_INPUT_LOCK_V3" and
            lock.get("state") == "LOCKED_C5_M110_DEV72_NO_PLANT_WAIT_PARENT_RELEASE_V3",
            "Wrong C5 experiment/schema; expected axis-coordinate C5 DEV72 v3")
    require(lock.get("candidate") == "C5_AXIS_MIXED_COORDINATE_M110" and
            lock.get("coordinate_mask") == [1, 1, 0] and
            lock.get("counts") == {"total": 72, "new_c5_plants": 60, "c5_reuse": 12,
                                    "physical_fields_per_scene": 14},
            "C5 candidate identity/counts differ from the v3 lock")
    require(len(lock["scene_ids_all_72"]) == 72 and
            len(set(lock["scene_ids_all_72"])) == 72 and
            len(lock["scene_ids_new_60"]) == 60 and
            len(lock["scene_ids_reuse_12"]) == 12 and
            set(lock["scene_ids_new_60"]).isdisjoint(lock["scene_ids_reuse_12"]) and
            set(lock["scene_ids_all_72"]) == set(lock["scene_ids_new_60"]) | set(lock["scene_ids_reuse_12"]),
            "C5 lock scene partition is inconsistent")
    require(not any("TEST" in sid for sid in lock["scene_ids_all_72"]),
            "Non-DEV/VAL scene found in C5 lock")
    require("NO_DELAYED_PREDICTION" not in str(LOCK_PATH) and
            "matched_ablations" not in str(LOCK_PATH).lower(),
            "Wrong C5 experiment path")

    require(status.get("schema") == "C5_AXIS_COORDINATE_DEV72_BATCH_STATUS_V3" and
            status.get("status") == "COMPLETE_RAW_PENDING_PARENT_AUDIT" and
            status.get("completed_scenes") == 60 and status.get("plant_calls") == 60 and
            status.get("training_steps") == 0 and status.get("optimizer_steps") == 0 and
            status.get("TEST_accessed") is False and
            status.get("scene_ids_new_60") == lock["scene_ids_new_60"] and
            len(status.get("records", [])) == 60,
            "C5 batch status is not the locked completed 60-scene v3 batch")
    require(status.get("input_lock_sha256", "").lower() == inputs["c5_input_lock"].lower() and
            status.get("release_sha256", "").lower() == inputs["c5_release"].lower() and
            status.get("source_binding_sha256", "").lower() == inputs["c5_source_binding"].lower() and
            status.get("runner_sha256", "").lower() == source.get("runner_sha256", "").lower(),
            "C5 status does not bind the pinned input lock/release/source/runner")

    require(source.get("schema") == "C5_AXIS_COORDINATE_DEV72_SOURCE_BINDING_V3" and
            source.get("input_lock_sha256", "").lower() == inputs["c5_input_lock"].lower() and
            source.get("run_contract_sha256", "").lower() == inputs["c5_run_contract"].lower() and
            source.get("release_contract_sha256", "").lower() == inputs["c5_parent_release_contract"].lower(),
            "C5 source binding does not match pinned lock/contracts")
    require(release.get("schema") == "C5_AXIS_COORDINATE_DEV72_PARENT_RELEASE_V3" and
            release.get("state") == "APPROVED_C5_M110_DEV72_V3" and
            release.get("plant_authorized") is True and release.get("max_new_Plant") == 60 and
            release.get("input_lock_sha256", "").lower() == inputs["c5_input_lock"].lower() and
            release.get("run_contract_sha256", "").lower() == inputs["c5_run_contract"].lower() and
            release.get("parent_release_contract_sha256", "").lower() ==
                inputs["c5_parent_release_contract"].lower() and
            release.get("source_binding_sha256", "").lower() == inputs["c5_source_binding"].lower() and
            release.get("TEST_accessed") is False and
            release.get("scene_ids_new_60") == lock["scene_ids_new_60"],
            "C5 v3 release does not match the pinned candidate and batch")
    require(contract.get("schema") == "C5_AXIS_COORDINATE_DEV72_RUN_CONTRACT_V3" and
            parent_release.get("schema") == "C5_AXIS_COORDINATE_DEV72_PARENT_RELEASE_CONTRACT_V3",
            "Unexpected C5 v3 contract schema")
    require(prepare.get("schema") == "C5_AXIS_COORDINATE_DEV72_PREPARE_RESULT_V3" and
            prepare.get("status") == "PREPARED_C5_M110_DEV72_NO_PLANT_WAIT_PARENT_RELEASE_V3" and
            prepare.get("input_lock_sha256", "").lower() == inputs["c5_input_lock"].lower() and
            prepare.get("source_binding_sha256", "").lower() == inputs["c5_source_binding"].lower() and
            prepare.get("snapshot_sha256", "").lower() == EXPECTED_SHA256["c5_prepared_snapshot"] and
            prepare.get("TEST_accessed") is False,
            "C5 v3 prepare receipt does not bind the current lock/snapshot")
    require(body.get("schema") == "C5_AXIS_COORDINATE_DEV72_BODY_COMPLETE_V3" and
            body.get("status") == "COMPLETE_RAW_PENDING_PARENT_AUDIT" and
            body.get("completed_scene_count") == 60 and body.get("plant_calls") == 60 and
            body.get("scene_ids_new_60") == lock["scene_ids_new_60"] and
            body.get("training_steps") == 0 and body.get("optimizer_steps") == 0 and
            body.get("TEST_accessed") is False,
            "C5 v3 completion receipt does not match the locked batch")

    # Check the locked non-raw source inventory. The sole MAT here is the
    # immutable effective-config input; raw_run.mat/run_start.mat are forbidden.
    for ref in lock.get("active_source_inventory", []):
        path = Path(ref["path"])
        require(path.name.lower() not in {"raw_run.mat", "run_start.mat"} and
                "runs_dev72_v3" not in str(path).lower(),
                f"Unexpected raw-run path inside source inventory: {path}")
        bind(path, ref["sha256"], f"locked active source {path.name}")

    require(score.get("schema") == "DL1018_GRU_STREAM_TRACKING_HEAD_FULL72_PAIRED_SCORE_V1" and
            score.get("scene_count") == 72 and len(score.get("rows", [])) == 72,
            "Unexpected Full72 paired-score artifact")
    require(same_path(score.get("scorer", {}).get("path", ""), FULL72_SCORER_PATH) and
            score.get("scorer", {}).get("sha256", "").lower() == inputs["full72_scorer"].lower(),
            "Full72 score does not bind the pinned scorer")
    score_binding = score.get("input_bindings", {})
    require(same_path(score_binding.get("c5_input_lock_path", ""), LOCK_PATH) and
            score_binding.get("c5_input_lock_sha256", "").lower() == inputs["c5_input_lock"].lower() and
            same_path(score_binding.get("c5_batch_status_path", ""), STATUS_PATH) and
            score_binding.get("c5_batch_status_sha256", "").lower() == inputs["c5_batch_status"].lower() and
            score_binding.get("c5_pending_status_records_verified") == 60,
            "Full72 score is not bound to the pinned C5 v3 lock/status")
    score_pending = score.get("c5_audit_limitation", {})
    require(score_pending.get("status") == "PROVISIONAL_COMPARISON_ONLY" and
            score_pending.get("pending_parent_audit_count") == 60 and
            set(score_pending.get("pending_scene_ids", [])) == set(lock["scene_ids_new_60"]),
            "Full72 score's C5 pending rows differ from the current 60-scene batch")

    current_scene = {row["scene_id"]: row for row in lock["scenes"]}
    batch_scene = {row["scene_id"]: row for row in status["records"]}
    score_scene = {row["scene_id"]: row for row in score["rows"]}
    require(len(current_scene) == len(score_scene) == 72 and len(batch_scene) == 60 and
            set(current_scene) == set(score_scene) and
            set(batch_scene) == set(lock["scene_ids_new_60"]),
            "Lock/status/Full72 score scene IDs do not line up")
    for sid in lock["scene_ids_new_60"]:
        src = batch_scene[sid]
        c5 = score_scene[sid]["methods"]["C5"]
        require(current_scene[sid]["candidate_action"] == "PROPOSE_NEW_C5_M110_RUN" and
                same_path(src["raw_path"], c5["raw_path"]) and
                src["raw_sha256"].lower() == c5["raw_sha256"].lower() and
                same_path(src["run_status_path"], str(Path(src["raw_path"]).with_name("run_status.json"))) and
                src["run_status_sha256"].lower() == c5["status_sha256"].lower() and
                c5["audit_status"] == "RUN_COMPLETE_RAW_PENDING_AUDIT",
                f"C5 v3 lock/status/Full72 binding mismatch for {sid}")
        require("position_axis_coordinate_c5_dev72_20261023" in src["raw_path"].lower() and
                "no_delayed_prediction" not in src["raw_path"].lower() and
                "matched_ablations" not in src["raw_path"].lower() and
                "test" not in sid.lower(),
                f"Wrong experiment/split path for {sid}")

    require(prior.get("status") == "C5_SCREEN_PASS" and
            len(prior.get("audits", [])) == 12 and
            prior.get("event_count") == 23616 and
            prior.get("new_Plant_in_audit") == 0 and prior.get("TEST_accessed") is False and
            all(prior.get("gates", {}).values()),
            "Prior axis-coordinate C5 screen12 audit is not the expected all-pass review")
    prior_scene = {row["scene_id"]: row for row in prior["audits"]}
    require(set(prior_scene) == set(lock["scene_ids_reuse_12"]),
            "Prior screen12 audit scene IDs differ from v3 reuse12")
    for sid in lock["scene_ids_reuse_12"]:
        reuse = current_scene[sid]["C5_reuse"]
        audit = prior_scene[sid]
        c5 = score_scene[sid]["methods"]["C5"]
        require(reuse.get("reused") is True and
                audit.get("status") == "PASS_C5_RAW_ALL_EVENTS" and
                audit.get("event_count") == 1968 and
                audit.get("raw_sha256", "").lower() == reuse["raw_sha256"].lower() ==
                    c5["raw_sha256"].lower() and
                audit.get("run_status_sha256", "").lower() == reuse["run_status_sha256"].lower() ==
                    c5["status_sha256"].lower() and
                same_path(audit["C5_metrics"]["path"], reuse["raw_path"]) and
                audit.get("input_lock_sha256", "").lower() ==
                    EXPECTED_SHA256["prior_screen_input_lock"] and
                audit.get("script_sha256", "").lower() == EXPECTED_SHA256["legacy_c5_raw_checker"] and
                audit.get("metric_scorer_sha256", "").lower() ==
                    EXPECTED_SHA256["position_metric_scorer"] and
                audit.get("mat_decoder_sha256", "").lower() == EXPECTED_SHA256["matlab_v73_decoder"] and
                max(audit.get("checks", {}).values()) < 1e-10,
                f"Cannot reuse prior C5 raw audit by raw/status SHA for {sid}")
        require(c5.get("audit_status") == "PASS_C5_RAW_ALL_EVENTS",
                f"Full72 scorer does not carry the prior C5 audit for {sid}")

    snapshot_path = Path(prepare["snapshot_path"])
    require(snapshot_path.is_file(), f"Missing locked prepared snapshot: {snapshot_path}")
    inputs["c5_prepared_snapshot"] = bind(snapshot_path,
        EXPECTED_SHA256["c5_prepared_snapshot"], "C5 v3 prepared cfg/opts snapshot")
    return {"lock": lock, "status": status, "source": source, "release": release,
            "prepare": prepare, "body": body, "score": score, "prior": prior,
            "current_scene": current_scene, "batch_scene": batch_scene,
            "score_scene": score_scene, "prior_scene": prior_scene,
            "snapshot_path": snapshot_path, "input_sha256": inputs}


def audit_new_scene(sid: str, status_record: dict, lock_record: dict,
                    score_record: dict, context: dict, metric_scorer, decoder) -> dict:
    """Audit exactly one locked C5 v3 raw, then return its evidence row."""
    raw_path = Path(status_record["raw_path"])
    status_path = Path(status_record["run_status_path"])
    start_path = Path(status_record["run_start_path"])
    require("position_axis_coordinate_c5_dev72_20261023" in str(raw_path).lower() and
            raw_path.name == "raw_run.mat" and "test" not in sid.lower(),
            f"Refusing non-C5-v3 or TEST raw path: {raw_path}")
    require(status_record["status"] == "RUN_COMPLETE_RAW_PENDING_AUDIT" and
            status_record["plant_calls"] == 1 and
            status_record["raw_sha256"].lower() == score_record["methods"]["C5"]["raw_sha256"].lower(),
            f"Unexpected batch row for {sid}")
    require(status_path.is_file() and start_path.is_file() and raw_path.is_file(),
            f"Missing locked run evidence for {sid}")
    status_file_sha = bind(status_path, status_record["run_status_sha256"], f"{sid} run status")
    start_file_sha = bind(start_path, status_record["run_start_sha256"], f"{sid} run start")
    marker_shas = {}
    for name in ("attempt_started_marker", "first_plant_step_marker"):
        path = Path(status_record[f"{name}_path"])
        marker_shas[name] = bind(path, status_record[f"{name}_sha256"], f"{sid} {name}")
    # Work only on this scene until its event replay and metric scorer finish.
    # The scorer rereads and rehashes this same raw before the loop advances.
    raw_file_sha = bind(raw_path, status_record["raw_sha256"], f"{sid} C5 raw")
    run_status = read_json(status_path)
    require(run_status.get("schema") == "C5_AXIS_COORDINATE_DEV72_RUN_STATUS_V3" and
            run_status.get("scene_id") == sid and
            run_status.get("status") == "RUN_COMPLETE_RAW_PENDING_AUDIT" and
            run_status.get("log_status") == "STABLE" and
            run_status.get("safety_stop_reason") in (None, "", "NONE") and
            run_status.get("transitions") == 20000 and run_status.get("state_samples") == 20001 and
            run_status.get("plant_calls") == 1 and run_status.get("training_steps") == 0 and
            run_status.get("optimizer_steps") == 0 and run_status.get("TEST_accessed") is False and
            run_status.get("coordinate_mask") == [1, 1, 0] and
            same_path(run_status.get("raw_path", ""), raw_path) and
            same_path(run_status.get("run_status_path", ""), status_path) and
            same_path(run_status.get("run_start_path", ""), start_path) and
            run_status.get("run_start_sha256", "").lower() == start_file_sha.lower() and
            run_status.get("attempt_started_marker_sha256", "").lower() ==
                status_record["attempt_started_marker_sha256"].lower() and
            run_status.get("first_plant_step_marker_sha256", "").lower() ==
                status_record["first_plant_step_marker_sha256"].lower() and
            run_status.get("raw_sha256", "").lower() == raw_file_sha.lower() and
            run_status.get("input_lock_sha256", "").lower() ==
                context["input_sha256"]["c5_input_lock"].lower() and
            run_status.get("release_sha256", "").lower() ==
                context["input_sha256"]["c5_release"].lower() and
            run_status.get("run_contract_sha256", "").lower() ==
                context["input_sha256"]["c5_run_contract"].lower() and
            run_status.get("prepare_result_sha256", "").lower() ==
                context["input_sha256"]["c5_prepare_result"].lower(),
            f"Run status fails closed for {sid}")

    start = decoder.matlab_section(start_path, "runStart")
    cfg_snapshot_sha = run_status.get("cfg_opts_snapshot_sha256", "")
    require(cfg_snapshot_sha.lower() == context["input_sha256"]["c5_prepared_snapshot"].lower(),
            f"Run-status cfg/opts snapshot identity differs for {sid}")
    match_entries = {}
    for section in ("cfg", "opts"):
        expected_flat = decoder.flatten(decoder.matlab_section(context["snapshot_path"], section))
        actual_flat = decoder.flatten(start[section])
        if section == "opts":
            actual_flat.pop("r2e_first_plant_step_marker")
        require(expected_flat.keys() == actual_flat.keys(),
                f"runStart/snapshot {section} leaves differ for {sid}")
        require(all(decoder.same_value(actual_flat[k], expected_flat[k]) for k in expected_flat),
                f"runStart/snapshot {section} values differ for {sid}")
        match_entries[section] = len(expected_flat)
    source_identity = decoder.matlab_section(context["snapshot_path"], "sourceIdentity")
    for run_field, snapshot_field in (("source_paths", "active_paths"),
                                      ("source_sha256", "active_sha256")):
        expected_flat = decoder.flatten(source_identity[snapshot_field])
        actual_flat = decoder.flatten(start[run_field])
        require(expected_flat.keys() == actual_flat.keys(),
                f"runStart/snapshot {run_field} leaves differ for {sid}")
        require(all(decoder.same_value(actual_flat[k], expected_flat[k]) for k in expected_flat),
                f"runStart/snapshot {run_field} values differ for {sid}")
        match_entries[run_field] = len(expected_flat)
    require(match_entries["cfg"] == 120 and match_entries["opts"] == 43,
            f"C5 v3 cfg/opts leaf counts differ from the adapted C5 checker for {sid}")
    cfg = start["cfg"]
    require(np.array_equal(np.asarray(cfg["control"]["bs"]["position"]["k1"]).ravel(), [1, 1, 1]) and
            np.array_equal(np.asarray(cfg["control"]["bs"]["position"]["k2"]).ravel(), [4, 4, 4]),
            f"M110 C5 cfg identity differs for {sid}")

    with h5py.File(raw_path, "r") as file:
        require("log" in file, f"Missing log group in {sid} raw")
        group = file["log"]

        def read(key):
            require(key in group, f"Missing expected C5 v3 log field {key} in {sid}")
            value = np.asarray(group[key])
            return value.T if value.ndim == 2 else value

        ids = np.flatnonzero(read("stage1_position_event_inference_valid").ravel())
        require(np.array_equal(ids, np.arange(320, 19991, 10)),
                f"C5 M110 event clock differs for {sid}")
        for key in ("stage1_position_delayed_prediction_enabled", "stage1_position_replacement_enabled",
                    "stage1_position_pcf_coordination_enabled", "stage1_position_update_enabled"):
            require(read(key).item() == 1, f"C5 feature {key} is disabled for {sid}")
        require(np.array_equal(read("stage1_position_coordinate_mask").ravel(), [1, 1, 0]) and
                read("stage1_position_search_gamma").item() == 12 and
                read("stage1_position_search_kappa").item() == 1,
                f"C5 M110 coordinate/search identity differs for {sid}")
        initial = read("stage1_position_search_initial_weight")
        require(np.array_equal(initial, read("stage1_position_weight_initial")),
                f"C5 initial weights differ for {sid}")
        initial_sha = hashlib.sha256(np.asarray(initial, dtype="<f8").tobytes(order="F")).hexdigest()
        require(initial_sha == context["lock"]["candidate_identity"]["W0_sha256"].lower(),
                f"C5 W0 identity differs for {sid}")
        phi = read("stage1_position_event_phi_33")[ids]
        weight_before = np.asarray(group["stage1_position_event_weight_before_33x3"]).transpose(0, 2, 1)
        weight_after = np.asarray(group["stage1_position_event_weight_after_33x3"]).transpose(0, 2, 1)
        require(weight_before.shape == weight_after.shape == (len(ids), 33, 3),
                f"C5 event weight shape differs for {sid}")
        require(np.array_equal(weight_before[0], initial), f"C5 first event weight differs for {sid}")
        state = read("state")
        score_position_reference = np.asarray(file["scene/reference/position"])
        if score_position_reference.ndim == 2:
            score_position_reference = score_position_reference.T
        require(state.shape[0] == score_position_reference.shape[0] == 20001 and
                score_position_reference.shape[1] == 3 and
                np.isfinite(score_position_reference).all(),
                f"Full72 scoring-reference shape differs for {sid}")
        full72_position_q = float(np.sqrt(np.mean(np.sum(
            (state[:, :3] - score_position_reference) ** 2, axis=1))))
        requested = read("stage1_position_pcf_a_req_mps2")
        actual_force = read("stage1_position_pcf_a_f_mps2")
        residual_force = read("stage1_position_pcf_r_f_mps2")
        eta = read("stage1_position_pcf_eta_before_mps")
        roll, pitch, yaw = read("filtered_attitude_reference").T
        thrust_axis = np.column_stack((
            np.cos(yaw) * np.sin(pitch) * np.cos(roll) + np.sin(yaw) * np.sin(roll),
            np.sin(yaw) * np.sin(pitch) * np.cos(roll) - np.cos(yaw) * np.sin(roll),
            np.cos(pitch) * np.cos(roll)))
        mass = float(np.asarray(cfg["plant"]["mass"]).item())
        gravity = float(np.asarray(cfg["plant"]["g"]).item())
        nameplate_actual_force = (read("requested_generalized")[:, 0, None] / mass * thrust_axis -
                                  np.array([0, 0, gravity]))
        target = read("stage1_position_delayed_prediction_target_mps2")[ids]
        previous = read("stage1_position_delayed_prediction_prev_index_zero_based").ravel()[ids]
        require(np.isnan(previous[0]) and np.isnan(target[0]).all() and
                np.array_equal(previous[1:], ids[:-1]),
                f"C5 past-target index convention differs for {sid}")
        reference = actual_force.copy()
        reference[:, 2] = requested[:, 2]
        target_recomputed = np.array([
            ((state[k, 3:6] - state[j, 3:6]) - .001 * reference[j:k].sum(axis=0)) / .01
            for j, k in zip(ids[:-1], ids[1:])])
        beta = np.minimum((ids + 1) * .001 / 1.8, 1)
        raw_output = np.einsum("nfi,nf->ni", weight_before, phi)
        gradient = np.zeros_like(weight_before)
        gradient[1:] = phi[:-1, :, None] * (
            np.einsum("nfi,nf->ni", weight_before[1:], phi[:-1]) - target_recomputed)[:, None, :]
        surface = (read("reference/velocity")[:-1] - state[:-1, 3:6] +
                   read("reference/position")[:-1] - state[:-1, :3])[ids]
        coordinated = surface - eta[ids] * np.array([1, 1, 0])
        effective = np.clip(coordinated, -np.array([7, 8, 10]), np.array([7, 8, 10]))
        expected_after = np.clip(weight_before - .12 * beta[:, None, None] *
                                 phi[:, :, None] * effective[:, None, :] - .00002 * weight_before -
                                 .01 * gradient, -60, 60)
        held = np.zeros((20000, 3))
        applied = beta[:, None] * np.clip(raw_output, -3, 3)
        for index, k in enumerate(ids):
            held[k:min(k + 10, 20000)] = applied[index]
        reference_integral = np.vstack((np.zeros((1, 3)), np.cumsum(.001 * reference, axis=0)))[:-1]
        actual_force_integral = np.vstack((np.zeros((1, 3)), np.cumsum(.001 * actual_force, axis=0)))[:-1]

        def diff(left, right):
            require(np.isfinite(left).all() and np.isfinite(right).all(), f"Nonfinite array in {sid}")
            return float(np.max(np.abs(left - right)))

        checks = {
            "phi_unit_norm": diff(np.linalg.norm(phi, axis=1), np.ones(len(ids))),
            "past_mixed_reference_target": diff(target[1:], target_recomputed),
            "surface_original_from_actual_state": diff(read("stage1_position_pcf_event_s_original_mps")[ids], surface),
            "surface_M110": diff(read("stage1_position_pcf_event_s_coord_mps")[ids], coordinated),
            "surface_clip_M110": diff(read("stage1_position_pcf_event_s_coord_eff_mps")[ids], effective),
            "eta_event_before": diff(read("stage1_position_pcf_event_eta_before_mps")[ids], eta[ids]),
            "output_before_update": diff(read("stage1_position_event_raw_acceleration_mps2")[ids], raw_output),
            "applied_beta_clip": diff(read("stage1_position_event_applied_acceleration_mps2")[ids], applied),
            "beta_clock": diff(read("stage1_position_event_beta").ravel()[ids], beta),
            "event_period": diff(read("stage1_position_event_dt_s").ravel()[ids], np.full(len(ids), .01)),
            "joint_update_once": diff(weight_after, expected_after),
            "weight_continuity": diff(weight_before[1:], weight_after[:-1]),
            "prediction_term_norm": diff(read("stage1_position_delayed_prediction_term_norm").ravel()[ids],
                                          .01 * np.linalg.norm(gradient, axis=(1, 2))),
            "separate_actual_af_integral": diff(
                read("stage1_position_delayed_prediction_af_integral_before_step_mps"), actual_force_integral),
            "M110_reference_integral": diff(
                read("stage1_position_delayed_prediction_reference_integral_before_step_mps"), reference_integral),
            "event_reference_integral": diff(
                read("stage1_position_delayed_prediction_event_reference_integral_mps")[ids],
                reference_integral[ids]),
            "event_velocity": diff(read("stage1_position_delayed_prediction_event_velocity_mps")[ids],
                                   state[ids, 3:6]),
            "held_compensation": diff(read("position_compensation_applied_acceleration_mps2"), held),
            "request_contains_applied_compensation": diff(
                requested, read("position_nominal_acceleration_mps2") - held),
            "rf_definition": diff(residual_force, requested - actual_force),
            "nameplate_af_from_actual_thrust_filtered_attitude": diff(actual_force, nameplate_actual_force),
            "direct_mixed_reference": diff(read("stage1_position_pcf_prediction_reference_mps2"), reference),
            "eta_initial_zero": diff(eta[0], np.zeros(3)),
            "eta_continuity": diff(eta[1:], read("stage1_position_pcf_eta_after_mps")[:-1]),
            "eta_exact_held_step": diff(read("stage1_position_pcf_eta_after_mps"),
                np.exp(-.004) * eta + (-np.expm1(-.004) / 4) * residual_force),
        }
        require(len(ids) == 1968 and max(checks.values()) < 1e-10,
                f"C5 event replay checks failed for {sid}: {checks}")

    candidate = {"scene_id": sid, "method": "C5_M110",
                 "path": str(raw_path), "sha256": raw_file_sha}
    metrics = metric_scorer.score(candidate)
    full72_c5 = score_record["methods"]["C5"]
    require(metrics["external_identity_sha256"].lower() ==
            lock_record["external_identity_sha256"].lower() and
            abs(full72_position_q - full72_c5["Q_m"]) <= 1e-12,
            f"C5 raw metric/source identity differs from the Full72 score for {sid}")
    require(full72_c5["raw_sha256"].lower() == raw_file_sha.lower() and
            full72_c5["run_status"] == "RUN_COMPLETE_RAW_PENDING_AUDIT" and
            full72_c5["audit_status"] == "RUN_COMPLETE_RAW_PENDING_AUDIT",
            f"Full72 C5 score row changed while auditing {sid}")
    return {
        "status": "PASS_C5_RAW_ALL_EVENTS",
        "scene_id": sid,
        "audit_source": "NEW_SEQUENTIAL_C5_AXIS_COORDINATE_DEV72_V3_RAW_AUDIT",
        "raw_path": str(raw_path),
        "raw_sha256": raw_file_sha,
        "run_status_path": str(status_path),
        "run_status_sha256": status_file_sha,
        "run_start_path": str(start_path),
        "run_start_sha256": start_file_sha,
        "marker_sha256": marker_shas,
        "input_lock_sha256": context["input_sha256"]["c5_input_lock"],
        "source_binding_sha256": context["input_sha256"]["c5_source_binding"],
        "release_sha256": context["input_sha256"]["c5_release"],
        "batch_status_sha256": context["input_sha256"]["c5_batch_status"],
        "full72_score_sha256": context["input_sha256"]["full72_score"],
        "full72_scorer_sha256": context["input_sha256"]["full72_scorer"],
        "checks": checks,
        "event_count": len(ids),
        "C5_metrics": metrics,
        "Full72_C5_Q_m_from_raw": full72_position_q,
        "Full72_C5_Q_m": full72_c5["Q_m"],
        "run_start_snapshot_match_entries": match_entries,
        "prepared_snapshot_sha256": context["input_sha256"]["c5_prepared_snapshot"],
        "mat_decoder_sha256": EXPECTED_SHA256["matlab_v73_decoder"],
        "metric_scorer_sha256": EXPECTED_SHA256["position_metric_scorer"],
        "new_Plant_in_audit": 0,
        "training_steps": 0,
        "TEST_accessed": False,
    }


def write_exclusive(path: Path, value: dict) -> str:
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    return sha256(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-after-root-review", action="store_true",
                        help="required safeguard: root must review this prepared auditor before raw access")
    args = parser.parse_args()
    require(args.execute_after_root_review,
            "No raw access: pass --execute-after-root-review only after independent root review")

    output_dir = PREP / "audit_output_v2"
    require(not output_dir.exists(), f"Refusing existing output directory: {output_dir}")
    context = verify_metadata_bindings()
    metric_scorer = load_module(METRIC_SCORER, "c5_axis_parent_metric_scorer")
    decoder = load_module(MAT_DECODER, "c5_axis_parent_mat_decoder")
    output_dir.mkdir(exist_ok=False)

    records = []
    batch_by_id = context["batch_scene"]
    score_by_id = context["score_scene"]
    prior_by_id = context["prior_scene"]
    # One scene at a time in the immutable v3 lock order. Reuse rows only copy
    # existing audit metadata after raw/status SHA matches; they open no MAT.
    for sid in context["lock"]["scene_ids_all_72"]:
        if sid in context["lock"]["scene_ids_reuse_12"]:
            prior = prior_by_id[sid]
            row = {
                "status": "PASS_C5_RAW_ALL_EVENTS",
                "scene_id": sid,
                "audit_source": "REUSED_PRIOR_AXIS_COORDINATE_C5_SCREEN12_AUDIT_BY_RAW_AND_STATUS_SHA",
                "prior_audit_summary_path": str(PRIOR_SCREEN),
                "prior_audit_summary_sha256": context["input_sha256"]["prior_screen12_audit"],
                "raw_path": context["current_scene"][sid]["C5_reuse"]["raw_path"],
                "raw_sha256": prior["raw_sha256"],
                "run_status_path": context["current_scene"][sid]["C5_reuse"]["run_status_path"],
                "run_status_sha256": prior["run_status_sha256"],
                "event_count": prior["event_count"],
                "checks": prior["checks"],
                "C5_metrics": prior["C5_metrics"],
                "Full72_C5_Q_m": score_by_id[sid]["methods"]["C5"]["Q_m"],
                "new_raw_opened_or_hashed": False,
                "new_Plant_in_audit": 0,
                "training_steps": 0,
                "TEST_accessed": False,
            }
        else:
            row = audit_new_scene(sid, batch_by_id[sid], context["current_scene"][sid],
                                  score_by_id[sid], context, metric_scorer, decoder)
        artifact = output_dir / f"{sid}_C5_RAW_PARENT_AUDIT.json"
        artifact_sha = write_exclusive(artifact, row)
        records.append({"scene_id": sid, "status": row["status"],
                        "audit_path": str(artifact), "audit_sha256": artifact_sha,
                        "raw_sha256": row["raw_sha256"],
                        "run_status_sha256": row["run_status_sha256"],
                        "audit_source": row["audit_source"]})
        print(json.dumps({"scene_id": sid, "status": row["status"],
                          "audit_source": row["audit_source"]}, ensure_ascii=False))

    require(len(records) == 72 and sum(r["audit_source"].startswith("NEW_") for r in records) == 60 and
            sum(r["audit_source"].startswith("REUSED_") for r in records) == 12,
            "Final C5 scene count/source partition is incomplete")
    summary = {
        "schema": "C5_AXIS_COORDINATE_DEV72_PARENT_RAW_AUDIT_V2",
        "status": "PASS_C5_AXIS_COORDINATE_DEV72_PARENT_RAW_AUDIT",
        "candidate": "C5_AXIS_MIXED_COORDINATE_M110",
        "coordinate_mask": [1, 1, 0],
        "complete_scene_count": 72,
        "new_raw_audited_scene_count": 60,
        "reused_prior_audit_count": 12,
        "sequential_raw_audit_order": context["lock"]["scene_ids_new_60"],
        "records": records,
        "input_sha256": context["input_sha256"],
        "auditor_path": str(Path(__file__).resolve()),
        "auditor_sha256": sha256(Path(__file__)),
        "new_Plant_in_audit": 0,
        "training_steps": 0,
        "optimizer_steps": 0,
        "TEST_accessed": False,
        "output_policy": "EXCLUSIVE_CREATE_ONLY",
    }
    summary_path = output_dir / "C5_AXIS_COORDINATE_DEV72_PARENT_RAW_AUDIT_v2.json"
    summary_sha = write_exclusive(summary_path, summary)
    print(json.dumps({"status": summary["status"], "summary_path": str(summary_path),
                      "summary_sha256": summary_sha, "scene_count": len(records)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
