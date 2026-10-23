"""One-scene parent audit; refuses to open run artifacts until the exact launcher OS exit is 0."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import h5py
import numpy as np


ROOT = Path(__file__).resolve().parents[3]
REVIEW_DIR = Path(__file__).resolve().parent
BASE_AUDITOR = ROOT / "reports/paper_continuation_20261023/c5_dev72_parent_review/audit_c5_dev72_raw_parent_v4.py"
BASE_AUDITOR_SHA = "d82e089c7d41f39c620daea63d95315632e6fb2f80adDF4DC12E6A4603B8E57E".lower()
DECODER = ROOT / "reports/paper14_v2/phase1/audit_w15_position_replay.py"
DECODER_SHA = "372d92cb17da99884e742d3fa0c877200c3bb2bc6fac7f10e7a1a046b97a76af"
SCORER = ROOT / "reports/delayed_prediction_c3_dev72_parent_20261023/parent_raw_metrics.py"
SCORER_SHA = "c64482d0adbc4358417648ec08351bd78f1d3dbdb38950435fa71b9cb0f531b1"
C5_DEV72_REVIEW = ROOT / "reports/paper_continuation_20261023/c5_dev72_parent_review/C5_DEV72_RAW_PARENT_REVIEW_v3.json"
C5_DEV72_REVIEW_SHA = "bb34889559d95a1c995d4d420e3b3d7a702908b58b47cce969dc508a1c697fab"
EVENT_AUDIT = REVIEW_DIR / "event_audit_c5_matched_ablation.py"
FIRST_SCENE = "DL1018_VAL_T1_C00_W07"
VARIANTS = ("C5_FREEZE_TRAINED_W0", "C5_NO_DELAYED_PREDICTION")


def sha(path: Path | str) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def module_at(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def verify_ref_tree(value):
    if isinstance(value, dict):
        if {"path", "sha256"} <= value.keys():
            p = Path(value["path"])
            assert p.is_file() and sha(p).lower() == value["sha256"].lower(), (p, value["sha256"])
        else:
            for child in value.values():
                verify_ref_tree(child)
    elif isinstance(value, list):
        for child in value:
            verify_ref_tree(child)


def jsonable(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    return value


def same_path(a, b):
    return Path(a).resolve() == Path(b).resolve()


def audit_one(variant: str, experiment_root: Path, execution_report_root: Path) -> dict:
    assert variant in VARIANTS
    config = experiment_root / variant
    files = {
        "lock": config / "C5_ABLATION_INPUT_LOCK_v1.json",
        "contract": config / "C5_ABLATION_RUN_CONTRACT_v1.json",
        "binding": config / "C5_ABLATION_SOURCE_BINDING_v1.json",
        "prepare": config / "C5_ABLATION_PREPARE_RESULT_v1.json",
        "snapshot": config / "C5_ABLATION_PREPARED_CFG_OPTS_v1.mat",
        "preflight": config / "C5_ABLATION_RUNNER_PREFLIGHT_v1.json",
        "release_contract": config / "C5_ABLATION_PARENT_RELEASE_CONTRACT_v1.json",
        "release": config / "C5_ABLATION_FIRST_PARENT_RELEASE_v1.json",
        "batch": config / "C5_ABLATION_FIRST_BATCH_STATUS_v1.json",
        "body": config / "C5_ABLATION_FIRST_BODY_COMPLETE_v1.json",
    }
    exit_path = execution_report_root / f"C5_{variant}_FIRST_MATLAB_OS_EXIT_v1.json"
    assert exit_path.is_file(), f"natural FIRST OS exit record not present: {exit_path}"
    os_exit = load(exit_path)
    assert os_exit.get("matlab_os_exit_code") == 0, (variant, os_exit.get("matlab_os_exit_code"))

    # The OS gate comes before reading batch/body/status/raw, so failed or live pilots are untouched.
    assert all(path.is_file() for key, path in files.items() if key not in ("batch", "body")), files
    lock, contract, binding, prep, preflight, parent_contract, release = (
        load(files[k]) for k in ("lock", "contract", "binding", "prepare", "preflight", "release_contract", "release"))
    digest = {k: sha(v) for k, v in files.items() if k not in ("batch", "body")}
    assert sha(BASE_AUDITOR) == BASE_AUDITOR_SHA
    assert sha(DECODER) == DECODER_SHA and sha(SCORER) == SCORER_SHA
    assert sha(C5_DEV72_REVIEW) == C5_DEV72_REVIEW_SHA
    assert EVENT_AUDIT.is_file()
    mode = variant == "C5_NO_DELAYED_PREDICTION"
    flags = {
        "actual_weight_update_enabled": mode,
        "actual_prediction_gradient_enabled": False,
        "legacy_stage1_update_enabled": True,
    }
    assert lock["schema"] == "C5_MATCHED_ABLATION_INPUT_LOCK_V1" and lock["state"] == "LOCKED_C5_MATCHED_ABLATION_NO_PLANT_PARENT_REVIEW_REQUIRED_V1"
    assert lock["variant_id"] == lock["ablation_mode"] == variant and lock["plant_authorized_by_this_lock"] is False
    assert lock["coordinate_mask"] == [1, 1, 0]
    assert contract["schema"] == "C5_MATCHED_ABLATION_RUN_CONTRACT_V1" and contract["state"] == lock["state"]
    assert contract["candidate"] == "C5_AXIS_MIXED_COORDINATE_M110"
    assert contract["first_scene_id"] == FIRST_SCENE and contract["scene_ids"][0] == FIRST_SCENE
    assert lock["first_scene_id"] == FIRST_SCENE and lock["scene_ids"][0] == FIRST_SCENE
    assert len(lock["scenes"]) == len(contract["scene_ids"]) == 12
    for key, expected in flags.items():
        assert bool(lock[key]) is expected and bool(contract[key]) is expected and bool(binding[key]) is expected
        assert bool(prep[key]) is expected and bool(preflight[key]) is expected and bool(release[key]) is expected
    assert lock["position_delayed_prediction_enabled"] is True and lock["stage1_update_enabled"] is True
    assert contract["position_delayed_prediction_enabled"] is True and contract["stage1_update_enabled"] is True
    assert binding["coordinate_mask"] == release["coordinate_mask"] == [1, 1, 0]
    assert binding["state"] == "SOURCE_BOUND_NO_PLANT_PARENT_REVIEW_REQUIRED_V1" and binding["plant_authorized"] is False
    assert prep["status"] == "PREPARED_C5_MATCHED_ABLATION_NO_PLANT_WAIT_PARENT_RELEASE_V1"
    assert preflight["status"] == "PREFLIGHT_COMPLETE_NO_PLANT_WAIT_PARENT_RELEASE_V1"
    assert lock["source_counts"]["total"] == 32 and len(lock["active_source_inventory"]) == 32
    assert binding["active_source_count"] == preflight["active_source_count"] == preflight["which_checks"] == 32
    assert prep["plant_calls"] == preflight["plant_calls"] == 0
    assert prep["TEST_accessed"] is False and preflight["TEST_accessed"] is False
    assert parent_contract["schema"] == "C5_MATCHED_ABLATION_PARENT_RELEASE_CONTRACT_V1"
    assert release["schema"] == "C5_MATCHED_ABLATION_PARENT_RELEASE_V1"
    assert release["state"] == "APPROVED_C5_ABLATION_FIRST_V1" and release["phase"] == "FIRST"
    assert release["plant_authorized"] is True and release["scene_ids"] == [FIRST_SCENE]
    assert release["first_scene_id"] == FIRST_SCENE and release["max_new_Plant"] == 1
    assert release["training_steps"] == release["optimizer_steps"] == release["new_B_sorties"] == 0
    assert release["TEST_accessed"] is False and release["automatic_retry"] is False
    assert release["parameter_or_seed_search"] is False

    # Bind exact frozen references before opening the actual run artifacts.
    verify_ref_tree(lock.get("source_files", {}))
    verify_ref_tree(lock.get("active_source_inventory", []))
    verify_ref_tree(lock.get("shared_input_files", []))
    verify_ref_tree(lock.get("upstream_refs", {}))
    verify_ref_tree(binding.get("file_refs", []))
    assert binding["input_lock_sha256"].lower() == digest["lock"]
    assert binding["contract_sha256"].lower() == digest["contract"]
    assert binding["prepare_sha256"].lower() == lock["source_files"]["prepare_entry"]["sha256"].lower()
    assert binding["runner_sha256"].lower() == lock["source_files"]["runner_entry"]["sha256"].lower()
    assert same_path(binding["input_lock_path"], files["lock"])
    assert prep["input_lock_sha256"].lower() == digest["lock"] and prep["contract_sha256"].lower() == digest["contract"]
    assert prep["snapshot_sha256"].lower() == digest["snapshot"]
    assert preflight["input_lock_sha256"].lower() == digest["lock"]
    assert preflight["contract_sha256"].lower() == digest["contract"]
    assert preflight["source_binding_sha256"].lower() == digest["binding"]
    assert preflight["prepare_result_sha256"].lower() == digest["prepare"]
    assert preflight["snapshot_sha256"].lower() == digest["snapshot"]
    assert preflight["runner_sha256"].lower() == binding["runner_sha256"].lower()
    assert release["parent_release_contract_sha256"].lower() == digest["release_contract"]
    assert release["input_lock_sha256"].lower() == digest["lock"]
    assert release["run_contract_sha256"].lower() == digest["contract"]
    assert release["source_binding_sha256"].lower() == digest["binding"]
    assert release["prepare_result_sha256"].lower() == digest["prepare"]
    assert release["snapshot_sha256"].lower() == digest["snapshot"]
    assert release["runner_preflight_sha256"].lower() == digest["preflight"]
    assert release["runner_sha256"].lower() == binding["runner_sha256"].lower()
    assert release["launcher_sha256"].lower() == lock["source_files"]["parent_launcher"]["sha256"].lower()
    assert os_exit["schema"] == "C5_MATCHED_ABLATION_MATLAB_OS_EXIT_V1"
    assert os_exit["variant_id"] == variant and os_exit["phase"] == "FIRST"
    assert os_exit["plant_authorized"] is True
    assert os_exit["release_sha256"].lower() == digest["release"]
    assert os_exit["runner_sha256"].lower() == binding["runner_sha256"].lower()
    assert os_exit["preflight_sha256"].lower() == digest["preflight"]
    launcher_ref = lock["source_files"]["parent_launcher"]
    assert same_path(os_exit["command_file"], launcher_ref["path"])
    assert os_exit["command_sha256"].lower() == launcher_ref["sha256"].lower()

    batch, body = load(files["batch"]), load(files["body"])
    assert batch["schema"] == "C5_MATCHED_ABLATION_BATCH_V1" and body["schema"] == "C5_MATCHED_ABLATION_BODY_COMPLETE_V1"
    for obj in (batch, body):
        assert obj["status"] == "COMPLETE_RAW_PENDING_PARENT_AUDIT"
        assert obj["phase"] == "FIRST" and obj["variant_id"] == variant
        assert obj["plant_calls"] == 1 and obj["training_steps"] == obj["optimizer_steps"] == 0
        assert obj["TEST_accessed"] is False
    assert batch["ablation_mode"] == variant
    assert batch["completed_scenes"] == 1 and body["scene_count"] == 1
    assert batch["scene_ids"] == body["scene_ids"] == [FIRST_SCENE]
    assert len(batch["records"]) == len(body["records"]) == 1 and batch["records"] == body["records"]
    for obj in (batch, body):
        assert obj["source_binding_sha256"].lower() == digest["binding"]
        assert obj["release_sha256"].lower() == digest["release"]
        assert obj["runner_sha256"].lower() == binding["runner_sha256"].lower()
        assert obj["preflight_sha256"].lower() == digest["preflight"]

    record = batch["records"][0]
    assert record["scene_id"] == FIRST_SCENE and record["batch_index"] == 1
    assert record["status"] == "RUN_COMPLETE_RAW_PENDING_AUDIT" and record["plant_calls"] == 1
    raw_path = Path(record["raw_path"]).resolve()
    attempt_dir = raw_path.parent
    assert raw_path.name == "raw_run.mat" and attempt_dir.name == "attempt_01"
    assert attempt_dir.parent.name == variant and attempt_dir.parent.parent.name == FIRST_SCENE
    assert attempt_dir.parent.parent.parent.parent.resolve() == config.resolve()
    assert attempt_dir.parent.parent.parent.name.startswith("runs_c5_matched_ablation_")
    status_path = attempt_dir / "run_status.json"
    run_start_path = attempt_dir / "run_start.mat"
    assert same_path(record["run_status_path"], status_path) and same_path(record["run_start_path"], run_start_path)

    base = module_at(BASE_AUDITOR, "pinned_c5_dev72_parent_auditor")
    decoder = module_at(DECODER, "pinned_matlab_decoder")
    scorer = module_at(SCORER, "pinned_raw_metric_scorer")
    event_module = module_at(EVENT_AUDIT, "c5_matched_ablation_event_audit")
    status = base.verify_status_file(status_path, record["run_status_sha256"], scene_id=FIRST_SCENE,
                                    raw_path=raw_path, raw_sha=record["raw_sha256"],
                                    coordinate_mask=None, require_event_counts=True,
                                    required_markers=("raw", "run_start", "attempt_started_marker", "first_plant_step_marker"))
    assert status["schema"] == "C5_MATCHED_ABLATION_RUN_STATUS_V1"
    assert status["phase"] == "FIRST" and status["variant_id"] == status["ablation_mode"] == variant
    assert status["batch_id"] == batch["batch_id"] and status["batch_index"] == 1
    assert status["source_binding_sha256"].lower() == digest["binding"]
    assert status["release_sha256"].lower() == digest["release"]
    assert status["input_lock_sha256"].lower() == digest["lock"]
    assert status["run_contract_sha256"].lower() == digest["contract"]
    assert status["prepare_result_sha256"].lower() == digest["prepare"]
    assert status["snapshot_sha256"].lower() == digest["snapshot"]
    assert status["preflight_sha256"].lower() == digest["preflight"]
    for key in ("actual_weight_update_enabled", "actual_prediction_gradient_enabled"):
        expected = flags[key]
        assert bool(status[key]) is expected
    assert status["physical_B_source_sha256"].lower() == record["physical_B_source_sha256"].lower()
    assert status["C3_raw_sha256"].lower() == record["C3_raw_sha256"].lower()
    run_start = base.matlab_section_safe(run_start_path, "runStart", decoder)
    assert base.matlab_text(run_start["schema"]) == "C5_MATCHED_ABLATION_RUN_START_V1"
    assert base.matlab_text(run_start["batch_id"]) == batch["batch_id"]
    assert base.matlab_scalar(run_start["batch_index"]) == 1 and base.matlab_text(run_start["phase"]) == "FIRST"
    assert base.matlab_text(run_start["scene_id"]) == FIRST_SCENE
    assert base.matlab_text(run_start["variant_id"]) == base.matlab_text(run_start["ablation_mode"]) == variant
    assert base.matlab_text(run_start["source_scene_id"]) == base.matlab_text(run_start["scene_identity"]["raw_scene_id"])
    assert base.matlab_flat(run_start["coordinate_mask"]) == [1.0, 1.0, 0.0]
    assert base.matlab_text(run_start["source_binding_sha256"]).lower() == digest["binding"]
    assert base.matlab_text(run_start["release_sha256"]).lower() == digest["release"]
    assert base.matlab_text(run_start["preflight_sha256"]).lower() == digest["preflight"]
    assert base.matlab_text(run_start["input_lock_sha256"]).lower() == digest["lock"]
    assert base.matlab_text(run_start["run_contract_sha256"]).lower() == digest["contract"]
    assert base.matlab_text(run_start["prepare_result_sha256"]).lower() == digest["prepare"]
    assert base.matlab_text(run_start["cfg_opts_snapshot_sha256"]).lower() == digest["snapshot"]
    assert base.matlab_scalar(run_start["plant_calls_before_invocation"]) == 0
    assert base.matlab_scalar(run_start["training_steps"]) == base.matlab_scalar(run_start["optimizer_steps"]) == 0
    assert base.matlab_scalar(run_start["TEST_accessed"]) in (0, False)
    for key, expected in flags.items():
        assert bool(base.matlab_scalar(run_start[key])) is expected

    # MATLAB snapshot stores the named top-level variables; decode them individually as runStart does.
    with h5py.File(files["snapshot"], "r") as mat:
        snapshot = {key: base.h5_tree_cell_safe(mat[key]) for key in ("cfg", "opts", "W0", "modelIdentity", "sceneIdentity", "sourceIdentity")}
    leaves = {"cfg": base.equal_tree(snapshot["cfg"], run_start["cfg"], decoder),
              "opts": base.equal_tree(snapshot["opts"], run_start["opts"], decoder, ignore_marker=True),
              "modelIdentity": base.equal_tree(snapshot["modelIdentity"], run_start["model_identity"], decoder),
              "sourceIdentity": base.equal_tree(snapshot["sourceIdentity"], run_start["source_identity"], decoder)}
    assert leaves["cfg"] == 120 and leaves["opts"] == 43 and leaves["modelIdentity"] == 6
    assert leaves["sourceIdentity"] > 0
    assert base.matlab_flat(snapshot["opts"]["position_coordinate_mask"]) == [1.0, 1.0, 0.0]
    assert bool(base.matlab_scalar(snapshot["opts"]["position_delayed_prediction_enabled"]))
    assert bool(base.matlab_scalar(snapshot["opts"]["stage1_position_runtime"]["update_enabled"]))
    active = lock["active_source_inventory"]
    expected_paths = [x["path"] for x in active]
    expected_shas = [x["sha256"].lower() for x in active]
    snap_paths = [str(base.matlab_text(x)) for x in base.matlab_flat(snapshot["sourceIdentity"]["active_paths"])]
    snap_shas = [str(base.matlab_text(x)).lower() for x in base.matlab_flat(snapshot["sourceIdentity"]["active_sha256"])]
    start_paths = [str(base.matlab_text(x)) for x in base.matlab_flat(run_start["source_identity"]["active_paths"])]
    start_shas = [str(base.matlab_text(x)).lower() for x in base.matlab_flat(run_start["source_identity"]["active_sha256"])]
    assert len(expected_paths) == len(expected_shas) == len(snap_paths) == len(snap_shas) == len(start_paths) == len(start_shas) == 32
    assert [Path(x).resolve() for x in snap_paths] == [Path(x).resolve() for x in expected_paths]
    assert [Path(x).resolve() for x in start_paths] == [Path(x).resolve() for x in expected_paths]
    assert snap_shas == start_shas == expected_shas
    w0 = np.asarray(snapshot["W0"], dtype=float)
    assert w0.shape == (33, 3) and np.array_equal(w0, np.asarray(run_start["W0"], dtype=float))
    assert hashlib.sha256(np.asarray(w0, dtype="<f8").tobytes(order="F")).hexdigest() == contract["model"]["W0_sha256"].lower()
    assert base.matlab_text(run_start["W0_sha256"]).lower() == contract["model"]["W0_sha256"].lower()
    model_identity = snapshot["modelIdentity"]
    assert base.matlab_text(model_identity["model_id"]) == contract["model"]["id"]
    assert base.matlab_text(model_identity["W0_sha256"]).lower() == contract["model"]["W0_sha256"].lower()
    assert base.matlab_text(model_identity["normalizer_arrays_sha256"]).lower() == contract["model"]["normalizer_arrays_sha256"].lower()
    for key in ("input_dim", "window", "selected_step"):
        assert base.matlab_scalar(model_identity[key]) == contract["model"][key]
    assert bool(base.matlab_scalar(run_start["initial_weight_reset_from_W0"]))
    assert bool(base.matlab_scalar(run_start["controller_state_reset_for_scene"]))

    scene_row = next(x for x in lock["scenes"] if x["scene_id"] == FIRST_SCENE)
    assert base.matlab_text(run_start["physical_B_source_path"]) == scene_row["B_source"]["path"]
    assert base.matlab_text(run_start["physical_B_source_sha256"]).lower() == scene_row["B_source"]["sha256"].lower()
    assert base.matlab_text(run_start["scene_identity"]["B_raw_path"]) == scene_row["B_source"]["path"]
    assert base.matlab_text(run_start["scene_identity"]["B_raw_sha256"]).lower() == scene_row["B_source"]["sha256"].lower()
    assert base.matlab_text(run_start["C3_raw_path"]) == scene_row["C3_reuse"]["raw_path"]
    assert base.matlab_text(run_start["C3_raw_sha256"]).lower() == scene_row["C3_reuse"]["raw_sha256"].lower()
    assert same_path(base.matlab_text(run_start["C3_raw_path"]), scene_row["C3_reuse"]["raw_path"])
    scene_names = [str(base.matlab_text(x)) for x in base.matlab_flat(snapshot["sceneIdentity"]["scene_id"])]
    scene_index = scene_names.index(FIRST_SCENE)
    expected_scene_identity = base.scene_identity_row(snapshot["sceneIdentity"], scene_index)
    base.compare_scene_identity(run_start["scene_identity"], expected_scene_identity, decoder)
    assert base.matlab_text(run_start["scene_identity"]["scene_id"]) == FIRST_SCENE

    assert Path(status["run_start_path"]).resolve() == run_start_path.resolve()
    assert sha(run_start_path) == status["run_start_sha256"].lower() == record["run_start_sha256"].lower()
    raw_identity = base.matlab_section_safe(raw_path, "runIdentity", decoder)
    for key, expected in flags.items():
        assert bool(base.matlab_scalar(raw_identity[key])) is expected
    for key, value in (("schema", "C5_MATCHED_ABLATION_RUN_IDENTITY_V1"), ("variant_id", variant),
                       ("ablation_mode", variant), ("scene_id", FIRST_SCENE), ("candidate", contract["candidate"])):
        assert base.matlab_text(raw_identity[key]) == value
    assert base.matlab_flat(raw_identity["coordinate_mask"]) == [1.0, 1.0, 0.0]
    for key, key_sha in (("source_binding_sha256", "binding"), ("release_sha256", "release"),
                         ("preflight_sha256", "preflight"), ("input_lock_sha256", "lock"),
                         ("run_contract_sha256", "contract"), ("prepare_result_sha256", "prepare"),
                         ("cfg_opts_snapshot_sha256", "snapshot"), ("run_start_sha256", None)):
        want = digest[key_sha] if key_sha else sha(run_start_path)
        assert base.matlab_text(raw_identity[key]).lower() == want
    assert base.equal_tree(snapshot["W0"], raw_identity["W0"], decoder) > 0
    assert base.equal_tree(snapshot["modelIdentity"], raw_identity["model_identity"], decoder) == 6
    assert base.equal_tree(snapshot["sourceIdentity"], raw_identity["source_identity"], decoder) == leaves["sourceIdentity"]
    assert base.equal_tree(run_start["scene_identity"], raw_identity["scene_identity"], decoder) > 0
    assert base.matlab_text(raw_identity["W0_sha256"]).lower() == contract["model"]["W0_sha256"].lower()
    assert base.matlab_text(raw_identity["physical_B_source_path"]) == scene_row["B_source"]["path"]
    assert base.matlab_text(raw_identity["physical_B_source_sha256"]).lower() == scene_row["B_source"]["sha256"].lower()
    assert base.matlab_text(raw_identity["C3_raw_path"]) == scene_row["C3_reuse"]["raw_path"]
    assert base.matlab_text(raw_identity["C3_raw_sha256"]).lower() == scene_row["C3_reuse"]["raw_sha256"].lower()
    assert base.matlab_scalar(raw_identity["training_steps"]) == base.matlab_scalar(raw_identity["optimizer_steps"]) == 0
    assert base.matlab_scalar(raw_identity["TEST_accessed"]) in (0, False)

    raw_score = scorer.score({"scene_id": FIRST_SCENE, "method": variant, "path": str(raw_path), "sha256": record["raw_sha256"]})
    parent_review = load(C5_DEV72_REVIEW)
    assert parent_review["status"] == "PASS_C5_DEV72_RAW_ALL_EVENTS_PARENT_AUDIT"
    parent_row = next(x for x in parent_review["rows"] if x["scene_id"] == FIRST_SCENE)
    assert parent_row["status"] == "PASS_REUSED_C5_SCREEN_AUDIT" and parent_row["event_count"] == 1968
    baseline = {name: parent_row[key] for name, key in (("B_TRACEABLE", "B_metrics"), ("C3", "C3_metrics"), ("C5_M110", "C5_metrics"))}
    assert same_path(baseline["C3"]["path"], scene_row["C3_reuse"]["raw_path"])
    assert baseline["C3"]["sha256"].lower() == scene_row["C3_reuse"]["raw_sha256"].lower()
    identities = {item["external_identity_sha256"] for item in baseline.values()}
    identities.add(raw_score["external_identity_sha256"])
    assert len(identities) == 1
    for name, item in baseline.items():
        assert item["scene_id"] == FIRST_SCENE
        assert Path(item["path"]).is_file() and sha(item["path"]).lower() == item["sha256"].lower()
    event_result = event_module.audit_events(raw_path, run_start["cfg"], variant, w0, contract["model"]["W0_sha256"])
    assert event_result["event_count"] == 1968 and event_result["actual_prediction_norm_max"] == 0
    comparison = {name: {"Q_0_20_m": item["Q_0_20_m"],
                         "pilot_minus_method_Q_m": raw_score["Q_0_20_m"] - item["Q_0_20_m"],
                         "raw_sha256": item["sha256"], "external_identity_sha256": item["external_identity_sha256"]}
                  for name, item in baseline.items()}
    return {
        "schema": "C5_MATCHED_ABLATION_FIRST_RAW_PARENT_AUDIT_V1",
        "status": "PASS_C5_MATCHED_ABLATION_FIRST_RAW_ALL_EVENTS",
        "variant_id": variant, "scene_id": FIRST_SCENE, "event_count": 1968,
        "plant_calls_in_audit": 0, "TEST_accessed": False, "training_steps": 0, "optimizer_steps": 0,
        "actual_weight_update_enabled": mode, "actual_prediction_gradient_enabled": False,
        "source_files": {k: {"path": str(v), "sha256": sha(v)} for k, v in files.items()},
        "natural_os_exit": {"path": str(exit_path), "sha256": sha(exit_path), "exit_code": 0},
        "run_artifacts": {"raw_path": str(raw_path), "raw_sha256": sha(raw_path),
                          "run_status_path": str(status_path), "run_status_sha256": sha(status_path),
                          "run_start_path": str(run_start_path), "run_start_sha256": sha(run_start_path),
                          "batch_sha256": sha(files["batch"]), "body_sha256": sha(files["body"])},
        "pinned_reuse": {"base_auditor_sha256": BASE_AUDITOR_SHA, "decoder_sha256": DECODER_SHA,
                         "scorer_sha256": SCORER_SHA, "event_audit_sha256": sha(EVENT_AUDIT),
                         "C5_DEV72_parent_review_sha256": C5_DEV72_REVIEW_SHA},
        "cfg_opts_leaf_counts": leaves, "source_count": 32,
        "W0_sha256": contract["model"]["W0_sha256"],
        "run_metrics": jsonable(raw_score), "baseline_parent_audit_methods": jsonable(baseline),
        "Q_comparison": jsonable(comparison), "event_checks": jsonable(event_result),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=VARIANTS, required=True)
    parser.add_argument("--experiment-root", type=Path,
                        default=ROOT / "experiments/position_c5_matched_ablations_v2_20261023")
    parser.add_argument("--execution-report-root", type=Path,
                        default=ROOT / "reports/paper_continuation_20261023/c5_matched_ablation_execution/v2")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    experiment_root = args.experiment_root if args.experiment_root.is_absolute() else ROOT / args.experiment_root
    execution_report_root = args.execution_report_root if args.execution_report_root.is_absolute() else ROOT / args.execution_report_root
    assert not output.exists(), f"refusing to overwrite existing output: {output}"
    result = audit_one(args.variant, experiment_root, execution_report_root)
    result["audit_script_sha256"] = sha(Path(__file__))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")
    print(json.dumps({"status": result["status"], "variant_id": args.variant,
                      "scene_id": FIRST_SCENE, "output": str(output), "output_sha256": sha(output),
                      "audit_script_sha256": result["audit_script_sha256"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
