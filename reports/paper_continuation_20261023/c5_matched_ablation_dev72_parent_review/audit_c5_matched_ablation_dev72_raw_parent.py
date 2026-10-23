"""Audit the two matched C5 ablations over the frozen 12+60 DEV72 scene set.

The 12 screen scenes are reused from their pinned parent audits without opening
their raw files. The remaining 60 are read only after both exact batch OS exits
are naturally recorded as zero.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
from pathlib import Path

import h5py
import numpy as np
import scipy.io


ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
EXP_ROOT = ROOT / "experiments/position_c5_matched_ablations_dev72_v3_20261023"
DEFAULT_EXEC_ROOT = ROOT / "reports/paper_continuation_20261023/c5_matched_ablation_execution/dev72_v3"
BASE_PATH = ROOT / "reports/paper_continuation_20261023/c5_dev72_parent_review/audit_c5_dev72_raw_parent_v4.py"
DECODER_PATH = ROOT / "reports/paper14_v2/phase1/audit_w15_position_replay.py"
SCORER_PATH = ROOT / "reports/delayed_prediction_c3_dev72_parent_20261023/parent_raw_metrics.py"
ABLACTION_HELPER = ROOT / "reports/paper_continuation_20261023/c5_matched_ablation_parent_raw_review/audit_c5_matched_ablation_first_raw_v2.py"
SCREEN12_AUDITOR = ROOT / "reports/paper_continuation_20261023/c5_matched_ablation_parent_raw_review/audit_c5_matched_ablation_screen12_raw.py"
EVENT_AUDIT = ROOT / "reports/paper_continuation_20261023/c5_matched_ablation_parent_raw_review/event_audit_c5_matched_ablation.py"
C5_PARENT = ROOT / "reports/paper_continuation_20261023/c5_dev72_parent_review/C5_DEV72_RAW_PARENT_REVIEW_v3.json"
MANIFEST = EXP_ROOT / "C5_ABLATION_DEV72_CODE_INPUT_MANIFEST_v3.json"
C5_DEV72_LOCK_SHA = "82024c01276cc4bfbd9b7772cf5332dee3fdfcbed422969589b68f1c90ed2d75"

PINNED = {
    "manifest": "51d1b428c5b7a29a47cb7c8a564a82b8a9529c61dd62e6b79a0c448859a1023f",
    "base_auditor": "d82e089c7d41f39c620daea63d95315632e6fb2f80addf4dc12e6a4603b8e57e",
    "decoder": "372d92cb17da99884e742d3fa0c877200c3bb2bc6fac7f10e7a1a046b97a76af",
    "scorer": "c64482d0adbc4358417648ec08351bd78f1d3dbdb38950435fa71b9cb0f531b1",
    "ablation_helper": "b64f7d69c45ac713fa57022fc6bfcf0a35ff50f85d973673bd00f2cd7f6ae91f",
    "screen12_auditor": "426e1dc6f380b2a9caa95cea748f1db8d64ac7ac6d3c91d3bd22011a7f6e7380",
    "event_audit": "1a8106ca6df7bb75ecb7a9cf5a09b9f91bc6eaa38547917a1fab677092c3755a",
    "c5_parent_review": "bb34889559d95a1c995d4d420e3b3d7a702908b58b47cce969dc508a1c697fab",
    "freeze_lock": "28b2d3b99a20a2390b31db0a07aa1cd76a581fb0134b881e7f4ffc861b8670b3",
    "freeze_contract": "31fd63333e1edfb93b06bf2cdcf11517fb4c42952d97cae67ad0625b6e77f9fa",
    "freeze_binding": "7b24881172848442554327286372dc0e478c909f3ccbf6f7c4465b06d67b70d4",
    "freeze_reuse": "aba2d6c73777612788c2c4dbdd68ca56aa7f200a5dff720a4b8b7c744eb80833",
    "no_pred_lock": "e0020306b8b7e7fba2948b93cbde30e0ec8f8470ede5dcef5e128d20c8728074",
    "no_pred_contract": "91669018d3d5f19a29c7162f4ed307f7f7371850ff0ffe647fe86bc49825bbcc",
    "no_pred_binding": "db605d55641ddda3c34d3cb6694a678678b683076951f836b58edc79db6ec06f",
    "no_pred_reuse": "123f56a288469b5fdf403db09d9d63cab2ca3300283a9fbda6a54df833d83494",
}
VARIANTS = ("C5_FREEZE_TRAINED_W0", "C5_NO_DELAYED_PREDICTION")
TIE_TOLERANCE_M = 1e-12
WIND_BANDS = {
    "W00_W08": set(range(0, 9)),
    "W09_W11": set(range(9, 12)),
    "W12_W14": set(range(12, 15)),
    "W15": {15},
}


def sha(path: Path | str) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load(path: Path | str):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def module_at(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def same_path(a: str | Path, b: str | Path) -> bool:
    return Path(a).resolve() == Path(b).resolve()


def file_ref(path: str | Path, expected_sha: str, *, hash_file: bool = True):
    p = Path(path)
    assert p.is_file(), p
    if hash_file:
        actual = sha(p)
        assert actual.lower() == expected_sha.lower(), (p, actual, expected_sha)
    return p


def records_as_list(value, count: int):
    if isinstance(value, dict):
        records = [value]
    elif isinstance(value, list):
        records = value
    else:
        raise TypeError(f"records must be an object or list, got {type(value).__name__}")
    assert len(records) == count and all(isinstance(row, dict) for row in records)
    return records


def scene_parts(scene_id: str):
    match = re.fullmatch(r"DL1018_(DEV|VAL)_T([1-3])_C\d\d_W(\d\d)", scene_id)
    assert match, scene_id
    return match.group(1), int(match.group(2)), int(match.group(3))


def assert_metric_refs(metric: dict, scene_id: str, external_identity: str):
    assert metric["scene_id"] == scene_id
    assert metric["external_identity_sha256"].lower() == external_identity.lower()
    assert Path(metric["path"]).is_file() and len(metric["sha256"]) == 64
    for value in metric.values():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            assert math.isfinite(float(value)), (scene_id, value)


def metric_refs_match(metric: dict, ref: dict, *, path_key: str, sha_key: str):
    assert same_path(metric["path"], ref[path_key])
    assert metric["sha256"].lower() == ref[sha_key].lower()


def upstream_c5_lock_for(lock: dict):
    refs = lock.get("upstream_refs", {})
    matches = [ref for ref in refs.values()
               if isinstance(ref, dict) and Path(ref.get("path", "")).name == "C5_DEV72_INPUT_LOCK_v3.json"]
    assert len(matches) == 1, "expected exactly one closed C5 DEV72 v3 input-lock reference"
    ref = matches[0]
    path = file_ref(ref["path"], ref["sha256"])
    assert sha(path).lower() == C5_DEV72_LOCK_SHA
    upstream = load(path)
    assert upstream["schema"] == "C5_AXIS_COORDINATE_DEV72_INPUT_LOCK_V3"
    return path, upstream


def verify_closed_c3_reference(scene_id: str, lock_row: dict, upstream_c5_lock: dict,
                               parent_row: dict, external_identity: str,
                               reuse12_scene_ids: list[str]):
    upstream_rows = {row["scene_id"]: row for row in upstream_c5_lock["scenes"]}
    assert scene_id in upstream_rows
    upstream_row = upstream_rows[scene_id]
    assert upstream_row["external_identity_sha256"].lower() == external_identity.lower()
    upstream_ref = upstream_row["C3_reference"]
    c3_ref = lock_row["C3_reference"]
    assert c3_ref == upstream_ref, (scene_id, "C3_reference differs from closed C5_DEV72 lock")
    metric = parent_row["C3_metrics"]
    assert_metric_refs(metric, scene_id, external_identity)
    metric_refs_match(metric, c3_ref, path_key="raw_path", sha_key="raw_sha256")
    legacy_marker_omitted = (c3_ref["kind"] == "C3_REUSED_SCREEN" and
                             scene_id in reuse12_scene_ids and
                             c3_ref["attempt_started_marker_path"] == "" and
                             c3_ref["attempt_started_marker_sha256"] == "")
    marker_check = {"status": "VERIFIED_PRESENT_AND_SHA256_BOUND",
                    "kind": c3_ref["kind"], "scene_id": scene_id}
    if legacy_marker_omitted:
        marker_check = {"status": "LEGACY_C3_REUSED_SCREEN_MARKER_ABSENT_BY_SCHEMA",
                        "kind": c3_ref["kind"], "scene_id": scene_id,
                        "attempt_started_marker_path": "", "attempt_started_marker_sha256": ""}
    for path_key, sha_key in (("run_status_path", "run_status_sha256"),
                              ("run_start_path", "run_start_sha256"),
                              ("attempt_started_marker_path", "attempt_started_marker_sha256"),
                              ("first_plant_step_marker_path", "first_plant_step_marker_sha256")):
        if path_key == "attempt_started_marker_path" and legacy_marker_omitted:
            continue
        file_ref(c3_ref[path_key], c3_ref[sha_key])
    return marker_check


def baseline_methods(scene_id: str, lock_row: dict, parent_row: dict, reused: bool,
                     upstream_c5_lock: dict, reuse12_scene_ids: list[str]):
    external = lock_row["external_identity_sha256"]
    assert parent_row["scene_id"] == scene_id
    expected_status = "PASS_REUSED_C5_SCREEN_AUDIT" if reused else "PASS_C5_RAW_ALL_EVENTS"
    assert parent_row["status"] == expected_status, (scene_id, parent_row["status"], expected_status)
    methods = {"B_TRACEABLE": parent_row["B_metrics"], "C3": parent_row["C3_metrics"],
               "C5_M110": parent_row["C5_metrics"]}
    c3_marker_check = verify_closed_c3_reference(
        scene_id, lock_row, upstream_c5_lock, parent_row, external, reuse12_scene_ids)
    for metric in methods.values():
        assert_metric_refs(metric, scene_id, external)
        file_ref(metric["path"], metric["sha256"])
    file_ref(lock_row["B_source"]["path"], lock_row["B_source"]["sha256"])
    assert not same_path(methods["B_TRACEABLE"]["path"], lock_row["B_source"]["path"]), \
        "historical physical B scene source and traceable B scored raw must retain separate lineage"
    metric_refs_match(methods["B_TRACEABLE"], lock_row["B72_scoring"],
                      path_key="raw_path", sha_key="raw_sha256")
    metric_refs_match(methods["C3"], lock_row["C3_reference"],
                      path_key="raw_path", sha_key="raw_sha256")
    if reused:
        assert lock_row["C5_reuse"]["reused"] is True
        metric_refs_match(methods["C5_M110"], lock_row["C5_reuse"],
                          path_key="raw_path", sha_key="raw_sha256")
    else:
        assert lock_row["C5_reuse"]["reused"] is False
    assert len({m["external_identity_sha256"] for m in methods.values()}) == 1
    return methods, c3_marker_check


def read_snapshot(path: Path, base):
    with h5py.File(path, "r") as mat:
        return {key: base.h5_tree_cell_safe(mat[key])
                for key in ("cfg", "opts", "W0", "modelIdentity", "sceneIdentity", "sourceIdentity")}


def verify_model_contract(snapshot: dict, contract: dict, lock: dict, base, decoder):
    model = contract["model"]
    identity = snapshot["modelIdentity"]
    expected_keys = {"model_id", "W0_sha256", "normalizer_arrays_sha256",
                     "input_dim", "window", "selected_step"}
    assert set(identity) == expected_keys
    assert base.matlab_text(identity["model_id"]) == model["id"]
    assert base.matlab_text(identity["W0_sha256"]).lower() == model["W0_sha256"].lower()
    assert base.matlab_text(identity["normalizer_arrays_sha256"]).lower() == model["normalizer_arrays_sha256"].lower()
    for key in ("input_dim", "window", "selected_step"):
        assert base.matlab_scalar(identity[key]) == model[key]

    model_refs = [ref for ref in lock["shared_input_files"] if ref["role"] == "model_mat"]
    assert len(model_refs) == 1
    model_ref = model_refs[0]
    file_ref(model_ref["path"], model_ref["sha256"])
    source = scipy.io.loadmat(model_ref["path"], variable_names=["model"],
                              squeeze_me=True, struct_as_record=False)["model"]
    assert str(source.model_id) == model["id"]
    for key in ("seed", "input_dim", "window", "selected_step"):
        assert int(getattr(source, key)) == model[key]
    w0 = np.asarray(snapshot["W0"], dtype=float)
    assert np.array_equal(np.asarray(source.output_W, dtype=float), w0)
    assert base.equal_tree(identity, identity, decoder) == 6
    assert hashlib.sha256(np.asarray(w0, dtype="<f8").tobytes(order="F")).hexdigest() == model["W0_sha256"].lower()


def verify_prepare_metadata(prep: dict, snapshot: dict, scene_ids: list[str], base):
    model_identity = snapshot["modelIdentity"]
    prep_model = prep["model_identity"]
    assert set(prep_model) == set(model_identity)
    assert prep_model["model_id"] == base.matlab_text(model_identity["model_id"])
    for key in ("W0_sha256", "normalizer_arrays_sha256"):
        assert prep_model[key].lower() == base.matlab_text(model_identity[key]).lower()
    for key in ("input_dim", "window", "selected_step"):
        assert float(prep_model[key]) == float(base.matlab_scalar(model_identity[key]))

    scene_rows = prep["scene_identity"]
    assert len(scene_rows) == len(scene_ids) == 72
    for index, (row, scene_id) in enumerate(zip(scene_rows, scene_ids)):
        expected = base.scene_identity_row(snapshot["sceneIdentity"], index)
        assert set(row) == set(expected) == {"scene_id", "raw_scene_id", "canonical_scene_id",
                                             "alias_normalized_in_memory", "B_raw_path",
                                             "B_raw_sha256", "payload_review_sha256"}
        assert row["scene_id"] == scene_id
        for key, value in expected.items():
            if key == "alias_normalized_in_memory":
                expected_alias = base.matlab_scalar(value)
                assert row[key] in (0, 1, False, True) and expected_alias in (0, 1, False, True)
                assert int(row[key]) == int(expected_alias)
            else:
                assert row[key] == base.matlab_text(value)


def make_common_context(variant: str, experiment_root: Path, execution_root: Path, base):
    config = experiment_root / variant
    files = {
        "lock": config / "C5_ABLATION_DEV72_INPUT_LOCK_v3.json",
        "contract": config / "C5_ABLATION_DEV72_RUN_CONTRACT_v3.json",
        "binding": config / "C5_ABLATION_DEV72_SOURCE_BINDING_v3.json",
        "reuse": config / "C5_ABLATION_DEV72_REUSE12_BINDING_v3.json",
        "prepare": config / "C5_ABLATION_DEV72_PREPARE_RESULT_v3.json",
        "snapshot": config / "C5_ABLATION_DEV72_PREPARED_CFG_OPTS_v3.mat",
        "fixture": config / "C5_ABLATION_CROSSLANG_FIXTURE_v3.json",
        "synthetic": config / "C5_ABLATION_CROSSLANG_RESULT_DEV72_v3.json",
        "preflight": config / "C5_ABLATION_DEV72_RUNNER_PREFLIGHT_v3.json",
        "release_contract": config / "C5_ABLATION_DEV72_PARENT_RELEASE_CONTRACT_v3.json",
        "release": config / "C5_ABLATION_DEV72_REMAINING60_PARENT_RELEASE_v3.json",
        "batch": config / "C5_ABLATION_DEV72_REMAINING60_BATCH_STATUS_v3.json",
        "body": config / "C5_ABLATION_DEV72_REMAINING60_BODY_COMPLETE_v3.json",
    }
    exit_path = execution_root / f"{variant}_REMAINING60_MATLAB_OS_EXIT_v3.json"
    assert exit_path.is_file(), f"natural REMAINING60 OS exit record missing: {exit_path}"
    exit_sha = sha(exit_path)
    os_exit = load(exit_path)
    assert os_exit["schema"] == "C5_MATCHED_ABLATION_DEV72_MATLAB_OS_EXIT_V2"
    assert os_exit["variant_id"] == variant and os_exit["phase"] == "REMAINING60"
    assert os_exit["matlab_os_exit_code"] == 0, (variant, os_exit["matlab_os_exit_code"])
    assert all(path.is_file() for path in files.values()), files

    digests = {key: sha(path) for key, path in files.items()}
    expected_lock_sha = PINNED["freeze_lock" if variant == VARIANTS[0] else "no_pred_lock"]
    expected_contract_sha = PINNED["freeze_contract" if variant == VARIANTS[0] else "no_pred_contract"]
    expected_binding_sha = PINNED["freeze_binding" if variant == VARIANTS[0] else "no_pred_binding"]
    expected_reuse_sha = PINNED["freeze_reuse" if variant == VARIANTS[0] else "no_pred_reuse"]
    assert digests["lock"] == expected_lock_sha and digests["contract"] == expected_contract_sha
    assert digests["binding"] == expected_binding_sha and digests["reuse"] == expected_reuse_sha

    lock, contract, binding, reuse = (load(files[key]) for key in ("lock", "contract", "binding", "reuse"))
    c5_lock_path, c5_dev72_lock = upstream_c5_lock_for(lock)
    prep, preflight, release_contract, release = (load(files[key]) for key in
                                                   ("prepare", "preflight", "release_contract", "release"))
    expected_weight_update = variant == "C5_NO_DELAYED_PREDICTION"
    expected_flags = {"actual_weight_update_enabled": expected_weight_update,
                      "actual_prediction_gradient_enabled": False,
                      "legacy_stage1_update_enabled": True}
    assert lock["schema"] == "C5_MATCHED_ABLATION_DEV72_INPUT_LOCK_V2"
    assert lock["state"] == "LOCKED_C5_MATCHED_ABLATION_DEV72_NO_PLANT_WAIT_PARENT_REVIEW_V2"
    assert lock["variant_id"] == lock["ablation_mode"] == variant
    assert lock["plant_authorized_by_this_lock"] is False
    assert contract["schema"] == "C5_MATCHED_ABLATION_DEV72_RUN_CONTRACT_V2"
    assert contract["variant_id"] == contract["ablation_mode"] == variant
    assert contract["candidate"] == "C5_AXIS_MIXED_COORDINATE_M110"
    assert binding["schema"] == "C5_MATCHED_ABLATION_DEV72_SOURCE_BINDING_V2"
    assert binding["variant_id"] == binding["ablation_mode"] == variant
    assert binding["state"] == "SOURCE_BOUND_NO_PLANT_PARENT_REVIEW_REQUIRED_V2"
    assert binding["plant_authorized"] is False
    for key, value in expected_flags.items():
        assert bool(lock[key]) is value and bool(contract[key]) is value and bool(binding[key]) is value
        assert bool(prep[key]) is value and bool(preflight[key]) is value and bool(release[key]) is value
    assert lock["coordinate_mask"] == contract["coordinate_mask"] == [1, 1, 0]
    assert contract["position_delayed_prediction_enabled"] and contract["stage1_update_enabled"]
    assert lock["position_delayed_prediction_enabled"] and lock["stage1_update_enabled"]
    assert contract["pcf_auxiliary_enabled"] and lock["pcf_auxiliary_enabled"]
    assert contract["scene_ids_all_72"] == lock["scene_ids_all_72"]
    assert contract["scene_ids_remaining_60"] == lock["scene_ids_remaining_60"]
    assert contract["scene_ids_reuse_12"] == lock["scene_ids_reuse_12"]
    all_ids = contract["scene_ids_all_72"]
    reuse_ids = contract["scene_ids_reuse_12"]
    remaining_ids = contract["scene_ids_remaining_60"]
    assert len(all_ids) == len(set(all_ids)) == 72 and len(reuse_ids) == 12 and len(remaining_ids) == 60
    # The execution batch starts with the first new DEV scene; reuse starts at
    # the separate first screen VAL scene.
    assert all_ids[0] == remaining_ids[0] == contract["first_scene_id"]
    assert lock["first_scene_id"] == contract["first_scene_id"]
    assert reuse_ids[0] == reuse["screen12_order"][0]
    assert reuse_ids[0] != contract["first_scene_id"]
    assert remaining_ids == [sid for sid in all_ids if sid not in set(reuse_ids)]
    assert [row["scene_id"] for row in lock["scenes"]] == all_ids
    assert c5_dev72_lock["scene_ids_all_72"] == all_ids
    assert [row["scene_id"] for row in c5_dev72_lock["scenes"]] == all_ids
    assert len(lock["active_source_inventory"]) == lock["source_counts"]["total"] == 32
    assert lock["source_counts"]["matlab"] == 31 and lock["source_counts"]["mat"] == 1
    assert len(lock["shared_input_files"]) == binding["shared_input_count"] == 6
    assert binding["active_source_count"] == 32 and binding["reused_scene_count"] == 12
    assert binding["remaining_scene_count"] == 60 and binding["all_scene_count"] == 72
    assert prep["schema"] == "C5_MATCHED_ABLATION_DEV72_PREPARE_RESULT_V2"
    assert prep["status"] == "PREPARED_C5_MATCHED_ABLATION_DEV72_NO_PLANT_WAIT_PARENT_RELEASE_V2"
    assert preflight["schema"] == "C5_MATCHED_ABLATION_DEV72_RUNNER_PREFLIGHT_V2"
    assert preflight["status"] == "PREFLIGHT_COMPLETE_C5_MATCHED_ABLATION_DEV72_NO_PLANT_WAIT_PARENT_RELEASE_V2"
    assert release["schema"] == "C5_MATCHED_ABLATION_DEV72_PARENT_RELEASE_V2"
    # The runner explicitly requires this legacy state string under its V2 schema.
    assert release["state"] == "APPROVED_C5_ABLATION_DEV72_REMAINING60_V1"
    assert release["phase"] == "REMAINING60" and release["variant_id"] == variant
    assert release["first_scene_id"] == contract["first_scene_id"]
    assert release["plant_authorized"] is True and release["max_new_Plant"] == 60
    assert release["scene_ids_all_72"] == all_ids and release["scene_ids_remaining_60"] == remaining_ids
    assert release["scene_ids_reuse_12"] == reuse_ids
    assert release["training_steps"] == release["optimizer_steps"] == release["new_B_sorties"] == 0
    assert release["TEST_accessed"] is False and release["automatic_retry"] is False
    assert release["parameter_or_seed_search"] is False

    helper = module_at(ABLACTION_HELPER, "pinned_c5_ablation_helpers")
    assert sha(MANIFEST).lower() == PINNED["manifest"]
    for path, key in ((BASE_PATH, "base_auditor"), (DECODER_PATH, "decoder"), (SCORER_PATH, "scorer"),
                      (ABLACTION_HELPER, "ablation_helper"), (SCREEN12_AUDITOR, "screen12_auditor"),
                      (EVENT_AUDIT, "event_audit"), (C5_PARENT, "c5_parent_review")):
        assert sha(path).lower() == PINNED[key], (path, sha(path), PINNED[key])
    assert helper.sha(ABLACTION_HELPER).lower() == PINNED["ablation_helper"]
    assert sha(helper.BASE_AUDITOR).lower() == helper.BASE_AUDITOR_SHA.lower() == PINNED["base_auditor"]
    assert sha(helper.DECODER).lower() == helper.DECODER_SHA.lower() == PINNED["decoder"]
    assert sha(helper.SCORER).lower() == helper.SCORER_SHA.lower() == PINNED["scorer"]
    assert sha(helper.EVENT_AUDIT).lower() == PINNED["event_audit"]
    helper.verify_ref_tree(lock.get("source_files", {}))
    helper.verify_ref_tree(lock.get("active_source_inventory", []))
    helper.verify_ref_tree(lock.get("shared_input_files", []))
    helper.verify_ref_tree(lock.get("upstream_refs", {}))
    helper.verify_ref_tree(binding.get("file_refs", []))
    assert same_path(lock["reuse12_binding"]["path"], files["reuse"])
    assert lock["reuse12_binding"]["sha256"].lower() == digests["reuse"]
    assert binding["reuse12_binding_sha256"].lower() == digests["reuse"]
    assert binding["input_lock_sha256"].lower() == digests["lock"]
    assert binding["contract_sha256"].lower() == digests["contract"]
    assert binding["prepare_sha256"].lower() == lock["source_files"]["prepare_entry"]["sha256"].lower()
    assert binding["runner_sha256"].lower() == lock["source_files"]["runner_entry"]["sha256"].lower()
    assert prep["input_lock_sha256"].lower() == digests["lock"]
    assert prep["contract_sha256"].lower() == digests["contract"]
    assert prep["snapshot_sha256"].lower() == digests["snapshot"]
    assert preflight["input_lock_sha256"].lower() == digests["lock"]
    assert preflight["contract_sha256"].lower() == digests["contract"]
    assert preflight["source_binding_sha256"].lower() == digests["binding"]
    assert preflight["prepare_result_sha256"].lower() == digests["prepare"]
    assert preflight["snapshot_sha256"].lower() == digests["snapshot"]
    assert preflight["runner_sha256"].lower() == binding["runner_sha256"].lower()
    assert preflight["reuse12_binding_sha256"].lower() == digests["reuse"]
    assert preflight["plant_calls"] == preflight["training_steps"] == preflight["optimizer_steps"] == 0
    assert preflight["TEST_accessed"] is False and preflight["scene_ids_remaining_60"] == remaining_ids
    assert release["input_lock_sha256"].lower() == digests["lock"]
    assert release["run_contract_sha256"].lower() == digests["contract"]
    assert release["source_binding_sha256"].lower() == digests["binding"]
    assert release["prepare_result_sha256"].lower() == digests["prepare"]
    assert release["snapshot_sha256"].lower() == digests["snapshot"]
    assert release["parent_release_contract_sha256"].lower() == digests["release_contract"]
    assert release["synthetic_fixture_sha256"].lower() == digests["fixture"]
    assert release["synthetic_result_sha256"].lower() == digests["synthetic"]
    assert release["runner_preflight_sha256"].lower() == digests["preflight"]
    assert release["runner_sha256"].lower() == binding["runner_sha256"].lower()
    assert release["launcher_sha256"].lower() == lock["source_files"]["parent_launcher"]["sha256"].lower()
    assert release["reuse12_binding_sha256"].lower() == digests["reuse"]
    assert release["reuse12_parent_screen_audit_sha256"].lower() == reuse["screen12_parent_audit_sha256"].lower()
    assert release["reuse12_first_audit_sha256"].lower() == reuse["first_parent_audit_sha256"].lower()
    assert release["screen12_event_audit_sha256"].lower() == reuse["screen12_parent_audit_event_audit_sha256"].lower()
    assert release["c3_dev72_lock_sha256"].lower() == lock["upstream_refs"]["c3_dev72_input_lock"]["sha256"].lower()
    assert release["c3_dev72_contract_sha256"].lower() == lock["upstream_refs"]["c3_dev72_run_contract"]["sha256"].lower()
    assert release["c3_dev72_snapshot_sha256"].lower() == lock["upstream_refs"]["c3_dev72_prepared_snapshot"]["sha256"].lower()
    assert os_exit["release_sha256"].lower() == digests["release"]
    assert os_exit["runner_sha256"].lower() == binding["runner_sha256"].lower()
    assert os_exit["preflight_sha256"].lower() == digests["preflight"]
    assert same_path(os_exit["command_file"], lock["source_files"]["parent_launcher"]["path"])
    assert os_exit["command_sha256"].lower() == lock["source_files"]["parent_launcher"]["sha256"].lower()

    snapshot = read_snapshot(files["snapshot"], base)
    decoder = module_at(DECODER_PATH, "pinned_c5_mat_decoder")
    leaves = {"cfg": base.equal_tree(snapshot["cfg"], snapshot["cfg"], decoder),
              "opts": base.equal_tree(snapshot["opts"], snapshot["opts"], decoder, ignore_marker=True),
              "modelIdentity": base.equal_tree(snapshot["modelIdentity"], snapshot["modelIdentity"], decoder),
              "sourceIdentity": base.equal_tree(snapshot["sourceIdentity"], snapshot["sourceIdentity"], decoder)}
    assert leaves["cfg"] == 120 and leaves["opts"] == 43 and leaves["modelIdentity"] == 6
    assert leaves["sourceIdentity"] > 0
    w0 = np.asarray(snapshot["W0"], dtype=float)
    assert w0.shape == (33, 3)
    model = contract["model"]
    verify_model_contract(snapshot, contract, lock, base, decoder)
    verify_prepare_metadata(prep, snapshot, all_ids, base)
    active = lock["active_source_inventory"]
    snapshot_scene_ids = [str(base.matlab_text(value))
                          for value in base.matlab_flat(snapshot["sceneIdentity"]["scene_id"])]
    assert snapshot_scene_ids == all_ids
    for index, lock_row in enumerate(lock["scenes"]):
        identity = base.scene_identity_row(snapshot["sceneIdentity"], index)
        assert same_path(lock_row["B_source"]["path"], base.matlab_text(identity["B_raw_path"]))
        assert lock_row["B_source"]["sha256"].lower() == base.matlab_text(identity["B_raw_sha256"]).lower()
        assert not same_path(lock_row["B72_scoring"]["raw_path"], lock_row["B_source"]["path"])
    source_ids = snapshot["sourceIdentity"]
    paths = [str(base.matlab_text(value)) for value in base.matlab_flat(source_ids["active_paths"])]
    shas = [str(base.matlab_text(value)).lower() for value in base.matlab_flat(source_ids["active_sha256"])]
    assert len(paths) == len(shas) == len(active) == 32
    assert [Path(path).resolve() for path in paths] == [Path(row["path"]).resolve() for row in active]
    assert shas == [row["sha256"].lower() for row in active]

    return {"variant": variant, "config": config, "files": files, "digests": digests,
            "c5_dev72_lock_path": c5_lock_path, "c5_dev72_lock": c5_dev72_lock,
            "exit_path": exit_path, "exit_sha": exit_sha, "os_exit": os_exit,
            "lock": lock, "contract": contract, "binding": binding, "reuse": reuse,
            "prep": prep, "preflight": preflight, "release": release, "snapshot": snapshot,
            "leaves": leaves, "w0": w0, "decoder": decoder, "helper": helper}


def load_batch_records(ctx):
    files, digests = ctx["files"], ctx["digests"]
    batch, body = load(files["batch"]), load(files["body"])
    variant = ctx["variant"]
    expected = ctx["contract"]["scene_ids_remaining_60"]
    for obj, schema in ((batch, "C5_MATCHED_ABLATION_DEV72_BATCH_V2"),
                        (body, "C5_MATCHED_ABLATION_DEV72_BODY_COMPLETE_V2")):
        assert obj["schema"] == schema and obj["status"] == "COMPLETE_RAW_PENDING_PARENT_AUDIT"
        assert obj["phase"] == "REMAINING60" and obj["variant_id"] == variant
        assert obj["plant_calls"] == 60
        assert obj["training_steps"] == obj["optimizer_steps"] == 0 and obj["TEST_accessed"] is False
        assert obj["scene_ids_remaining_60"] == expected
        assert obj["scene_ids_all_72"] == ctx["contract"]["scene_ids_all_72"]
        assert obj["scene_ids_reuse_12"] == ctx["contract"]["scene_ids_reuse_12"]
        assert obj["source_binding_sha256"].lower() == digests["binding"]
        assert obj["release_sha256"].lower() == digests["release"]
        assert obj["runner_sha256"].lower() == ctx["binding"]["runner_sha256"].lower()
        assert obj["preflight_sha256"].lower() == digests["preflight"]
    assert batch["ablation_mode"] == variant
    assert batch["batch_id"] == body["batch_id"]
    assert batch["completed_scenes"] == body["scene_count"] == batch["plant_calls"] == body["plant_calls"] == 60
    assert batch["scene_ids_remaining_60"] == body["scene_ids_remaining_60"] == expected
    assert batch["reuse12_binding_sha256"].lower() == ctx["digests"]["reuse"]
    assert batch["screen12_parent_audit_sha256"].lower() == ctx["reuse"]["screen12_parent_audit_sha256"].lower()
    records = records_as_list(batch["records"], 60)
    body_records = records_as_list(body["records"], 60)
    assert records == body_records, "batch/body records must match exactly"
    for index, (record, scene_id) in enumerate(zip(records, expected), start=1):
        assert record["batch_id"] == batch["batch_id"] and record["batch_index"] == index
        assert record["scene_id"] == scene_id and record["status"] == "RUN_COMPLETE_RAW_PENDING_AUDIT"
        assert record["plant_calls"] == 1
    ctx["batch"] = batch
    ctx["batch_records"] = records
    ctx["batch_body_digests"] = {"batch": sha(files["batch"]), "body": sha(files["body"])}


def baseline_row_index(parent_review):
    assert parent_review["status"] == "PASS_C5_DEV72_RAW_ALL_EVENTS_PARENT_AUDIT"
    rows = parent_review["rows"]
    ids = [row["scene_id"] for row in rows]
    assert len(ids) == len(set(ids)) == 72
    return {row["scene_id"]: row for row in rows}, ids


def load_reuse_screen_rows(ctx, parent_rows):
    reuse = ctx["reuse"]
    contract, lock = ctx["contract"], ctx["lock"]
    helper = ctx["helper"]
    assert reuse["schema"] == "C5_MATCHED_ABLATION_DEV72_REUSE12_BINDING_V2"
    assert reuse["state"] == "PARENT_AUDITED_SCREEN12_REUSE_ONLY_V2"
    assert reuse["variant_id"] == ctx["variant"] and reuse["records"]
    assert [row["scene_id"] for row in reuse["records"]] == contract["scene_ids_reuse_12"]
    screen_path = Path(reuse["screen12_parent_audit_path"])
    first_path = Path(reuse["first_parent_audit_path"])
    file_ref(screen_path, reuse["screen12_parent_audit_sha256"])
    file_ref(first_path, reuse["first_parent_audit_sha256"])
    screen = load(screen_path)
    first = load(first_path)
    assert screen["schema"] == "C5_MATCHED_ABLATION_SCREEN12_RAW_PARENT_AUDIT_V1"
    assert screen["status"] == "PASS_C5_MATCHED_ABLATION_SCREEN12_ALL_EVENTS"
    assert screen["screen12_complete"] is True and screen["scene_count_newly_audited"] == 11
    reuse_ids = contract["scene_ids_reuse_12"]
    assert screen["variant_id"] == ctx["variant"] and screen["batch_scene_order"] == reuse_ids[1:]
    assert screen["event_audit_sha256"].lower() == PINNED["event_audit"]
    assert first["schema"] == "C5_MATCHED_ABLATION_FIRST_RAW_PARENT_AUDIT_V1"
    assert first["status"] == "PASS_C5_MATCHED_ABLATION_FIRST_RAW_ALL_EVENTS"
    assert first["variant_id"] == ctx["variant"] and first["scene_id"] == reuse_ids[0]
    assert first["event_count"] == 1968 and first["natural_os_exit"]["exit_code"] == 0
    screen_rows = screen["screen12_rows"]
    assert len(screen_rows) == 12 and [row["scene_id"] for row in screen_rows] == reuse_ids
    assert len(reuse["records"]) == 12
    method_name = ctx["variant"]
    results = {}
    for binding_row, screen_row in zip(reuse["records"], screen_rows):
        sid = binding_row["scene_id"]
        lock_row = next(row for row in lock["scenes"] if row["scene_id"] == sid)
        assert lock_row["C5_ABLATION_REUSE"]["reused"] is True
        assert lock_row["C5_ABLATION_REUSE"]["variant_id"] == method_name
        assert binding_row["audit_status"] == "PASS_C5_MATCHED_ABLATION_SCREEN12_ALL_EVENTS"
        assert binding_row["event_count"] == 1968
        assert binding_row["external_identity_sha256"].lower() == lock_row["external_identity_sha256"].lower()
        assert screen_row["scene_id"] == sid and screen_row["methods"][method_name]["scene_id"] == sid
        assert screen_row["methods"][method_name]["path"] == binding_row["raw_path"]
        assert screen_row["methods"][method_name]["sha256"].lower() == binding_row["raw_sha256"].lower()
        assert screen_row["phase"] == binding_row["phase"]
        if binding_row["phase"] == "FIRST_PILOT_REUSE":
            assert sid == reuse_ids[0] and screen_row["new_raw_audit"] is False
            assert screen_row["provenance"]["pilot_raw_sha256"].lower() == binding_row["raw_sha256"].lower()
            assert screen_row["provenance"]["pilot_status_sha256"].lower() == binding_row["run_status_sha256"].lower()
            assert same_path(screen_row["provenance"]["pilot_audit_path"], first_path)
            assert screen_row["provenance"]["pilot_audit_sha256"].lower() == sha(first_path).lower()
        else:
            assert binding_row["phase"] == "TAIL11" and screen_row["new_raw_audit"] is True
            for field in ("raw_sha256", "run_status_sha256", "run_start_sha256", "external_identity_sha256"):
                assert screen_row["provenance"][field].lower() == binding_row[field].lower()
        for key in ("run_status_path", "run_start_path", "attempt_started_marker_path", "first_plant_step_marker_path",
                    "phase_release_path", "phase_batch_path", "phase_body_path", "natural_os_exit_path",
                    "first_parent_audit_path", "screen12_parent_audit_path"):
            sha_key = key.replace("_path", "_sha256")
            file_ref(binding_row[key], binding_row[sha_key])
        assert same_path(binding_row["screen12_parent_audit_path"], screen_path)
        assert binding_row["screen12_parent_audit_sha256"].lower() == sha(screen_path).lower()
        assert same_path(binding_row["first_parent_audit_path"], first_path)
        assert binding_row["first_parent_audit_sha256"].lower() == sha(first_path).lower()
        os_exit = load(binding_row["natural_os_exit_path"])
        assert os_exit["matlab_os_exit_code"] == 0
        assert os_exit["variant_id"] == method_name
        parent_row = parent_rows[sid]
        assert parent_row["status"] == "PASS_REUSED_C5_SCREEN_AUDIT"
        baselines, c3_marker_check = baseline_methods(
            sid, lock_row, parent_row, True, ctx["c5_dev72_lock"], contract["scene_ids_reuse_12"])
        for name, metric in baselines.items():
            screen_metric = screen_row["methods"][name]
            assert metric["path"] == screen_metric["path"]
            assert metric["sha256"].lower() == screen_metric["sha256"].lower()
            assert metric["Q_0_20_m"] == screen_metric["Q_0_20_m"]
        candidate = screen_row["methods"][method_name]
        assert_metric_refs(candidate, sid, lock_row["external_identity_sha256"])
        methods = {method_name: candidate, **baselines}
        assert len({item["external_identity_sha256"] for item in methods.values()}) == 1
        results[sid] = make_scene_row(sid, methods, "SCREEN12_AUDIT_REUSE", False,
                                      binding_row["phase"], binding_row["external_identity_sha256"],
                                      event_checks=screen_row["event_checks"],
                                      baseline_identity_checks={"C3_reference_attempt_marker": c3_marker_check})
    return results, {"path": str(screen_path), "sha256": sha(screen_path),
                     "first_path": str(first_path), "first_sha256": sha(first_path)}


def make_scene_row(scene_id: str, methods: dict, source: str, new_raw_audit: bool,
                   phase: str, external_identity: str, event_checks=None, raw_provenance=None,
                   baseline_identity_checks=None):
    split, task_num, wind_num = scene_parts(scene_id)
    candidate = next(name for name in VARIANTS if name in methods)
    deltas = {baseline: methods[candidate]["Q_0_20_m"] - methods[baseline]["Q_0_20_m"]
              for baseline in ("B_TRACEABLE", "C3", "C5_M110")}
    return {"scene_id": scene_id, "split": split, "task": f"T{task_num}", "wind": f"W{wind_num:02d}",
            "wind_number": wind_num, "candidate_method": candidate, "phase": phase,
            "data_origin": source, "new_raw_audit": new_raw_audit, "methods": methods,
            "deltas_Q_m": deltas,
            "comparisons": {name: compare_delta(value) for name, value in deltas.items()},
            "external_identity_sha256": external_identity,
            "event_checks": event_checks, "raw_provenance": raw_provenance,
            "baseline_identity_checks": baseline_identity_checks}


def compare_delta(delta: float):
    if delta < -TIE_TOLERANCE_M:
        return "WIN"
    if delta > TIE_TOLERANCE_M:
        return "LOSS"
    return "TIE"


def audit_new_record(ctx, record: dict, batch_index: int, scene_id: str,
                     parent_row: dict, base, scorer, event_module):
    variant, lock, contract = ctx["variant"], ctx["lock"], ctx["contract"]
    files, digests, batch = ctx["files"], ctx["digests"], ctx["batch"]
    lock_row = next(row for row in lock["scenes"] if row["scene_id"] == scene_id)
    assert lock_row["C5_ABLATION_REUSE"]["reused"] is False
    assert record["scene_id"] == scene_id and record["batch_index"] == batch_index
    assert record["batch_id"] == batch["batch_id"] and record["status"] == "RUN_COMPLETE_RAW_PENDING_AUDIT"
    assert record["plant_calls"] == 1
    config = ctx["config"]
    raw_path = Path(record["raw_path"]).resolve()
    attempt_dir = raw_path.parent
    assert raw_path.name == "raw_run.mat" and attempt_dir.name == "attempt_01"
    assert attempt_dir.parent.name == variant and attempt_dir.parent.parent.name == scene_id
    assert attempt_dir.parent.parent.parent.name == "runs_c5_matched_ablation_dev72_v3"
    assert attempt_dir.parent.parent.parent.parent.resolve() == config.resolve()
    status_path = attempt_dir / "run_status.json"
    run_start_path = attempt_dir / "run_start.mat"
    assert same_path(record["run_status_path"], status_path)
    assert same_path(record["run_start_path"], run_start_path)
    assert sha(raw_path).lower() == record["raw_sha256"].lower()

    status = base.verify_status_file(
        status_path, record["run_status_sha256"], scene_id=scene_id,
        raw_path=raw_path, raw_sha=record["raw_sha256"], coordinate_mask=None,
        require_event_counts=True,
        required_markers=("raw", "run_start", "attempt_started_marker", "first_plant_step_marker"))
    assert status["schema"] == "C5_MATCHED_ABLATION_RUN_STATUS_V1"
    assert status["phase"] == "REMAINING60" and status["variant_id"] == status["ablation_mode"] == variant
    assert status["batch_id"] == batch["batch_id"] and status["batch_index"] == batch_index
    for key, digest_key in (("source_binding_sha256", "binding"), ("release_sha256", "release"),
                            ("input_lock_sha256", "lock"), ("run_contract_sha256", "contract"),
                            ("prepare_result_sha256", "prepare"), ("snapshot_sha256", "snapshot"),
                            ("preflight_sha256", "preflight")):
        assert status[key].lower() == digests[digest_key]
    expected_weight_update = variant == "C5_NO_DELAYED_PREDICTION"
    assert bool(status["actual_weight_update_enabled"]) is expected_weight_update
    assert bool(status["actual_prediction_gradient_enabled"]) is False
    assert status["physical_B_source_sha256"].lower() == lock_row["B_source"]["sha256"].lower()
    assert same_path(status["physical_B_source_path"], lock_row["B_source"]["path"])
    assert status["C3_raw_sha256"].lower() == lock_row["C3_reference"]["raw_sha256"].lower()
    assert same_path(status["C3_raw_path"], lock_row["C3_reference"]["raw_path"])

    rec_marker_keys = (("attempt_started_marker_path", "attempt_started_marker_sha256"),
                       ("first_plant_step_marker_path", "first_plant_step_marker_sha256"))
    for path_key, sha_key in rec_marker_keys:
        assert same_path(record[path_key], status[path_key])
        assert record[sha_key].lower() == status[sha_key].lower()
    assert record["physical_B_source_sha256"].lower() == lock_row["B_source"]["sha256"].lower()
    assert record["C3_raw_sha256"].lower() == lock_row["C3_reference"]["raw_sha256"].lower()

    run_start = base.matlab_section_safe(run_start_path, "runStart", ctx["decoder"])
    assert base.matlab_text(run_start["schema"]) == "C5_MATCHED_ABLATION_RUN_START_V1"
    assert base.matlab_text(run_start["batch_id"]) == batch["batch_id"]
    assert base.matlab_scalar(run_start["batch_index"]) == batch_index
    assert base.matlab_text(run_start["phase"]) == "REMAINING60"
    assert base.matlab_text(run_start["scene_id"]) == scene_id
    assert base.matlab_text(run_start["variant_id"]) == base.matlab_text(run_start["ablation_mode"]) == variant
    assert base.matlab_flat(run_start["coordinate_mask"]) == [1.0, 1.0, 0.0]
    assert base.matlab_text(run_start["W0_sha256"]).lower() == contract["model"]["W0_sha256"].lower()
    for key, digest_key in (("source_binding_sha256", "binding"), ("release_sha256", "release"),
                            ("preflight_sha256", "preflight"), ("input_lock_sha256", "lock"),
                            ("run_contract_sha256", "contract"), ("prepare_result_sha256", "prepare"),
                            ("cfg_opts_snapshot_sha256", "snapshot")):
        assert base.matlab_text(run_start[key]).lower() == digests[digest_key]
    assert base.matlab_scalar(run_start["plant_calls_before_invocation"]) == 0
    assert base.matlab_scalar(run_start["training_steps"]) == base.matlab_scalar(run_start["optimizer_steps"]) == 0
    assert base.matlab_scalar(run_start["TEST_accessed"]) in (0, False)
    assert bool(base.matlab_scalar(run_start["legacy_stage1_update_enabled"])) is True
    assert bool(base.matlab_scalar(run_start["actual_weight_update_enabled"])) is expected_weight_update
    assert bool(base.matlab_scalar(run_start["actual_prediction_gradient_enabled"])) is False
    assert bool(base.matlab_scalar(run_start["initial_weight_reset_from_W0"]))
    assert bool(base.matlab_scalar(run_start["controller_state_reset_for_scene"]))
    assert base.equal_tree(ctx["snapshot"]["cfg"], run_start["cfg"], ctx["decoder"]) == 120
    assert base.equal_tree(ctx["snapshot"]["opts"], run_start["opts"], ctx["decoder"], ignore_marker=True) == 43
    assert base.equal_tree(ctx["snapshot"]["modelIdentity"], run_start["model_identity"], ctx["decoder"]) == 6
    assert base.equal_tree(ctx["snapshot"]["sourceIdentity"], run_start["source_identity"], ctx["decoder"]) == ctx["leaves"]["sourceIdentity"]
    assert base.matlab_flat(ctx["snapshot"]["opts"]["position_coordinate_mask"]) == [1.0, 1.0, 0.0]
    assert bool(base.matlab_scalar(ctx["snapshot"]["opts"]["position_delayed_prediction_enabled"]))
    assert bool(base.matlab_scalar(ctx["snapshot"]["opts"]["stage1_position_runtime"]["update_enabled"]))

    active = lock["active_source_inventory"]
    for identity in (ctx["snapshot"]["sourceIdentity"], run_start["source_identity"]):
        paths = [str(base.matlab_text(value)) for value in base.matlab_flat(identity["active_paths"])]
        shas = [str(base.matlab_text(value)).lower() for value in base.matlab_flat(identity["active_sha256"])]
        assert len(paths) == len(shas) == len(active) == 32
        assert [Path(value).resolve() for value in paths] == [Path(item["path"]).resolve() for item in active]
        assert shas == [item["sha256"].lower() for item in active]

    w0 = np.asarray(ctx["snapshot"]["W0"], dtype=float)
    assert np.array_equal(w0, np.asarray(run_start["W0"], dtype=float))
    assert hashlib.sha256(np.asarray(w0, dtype="<f8").tobytes(order="F")).hexdigest() == contract["model"]["W0_sha256"].lower()
    assert base.matlab_text(run_start["source_scene_id"]) == base.matlab_text(run_start["scene_identity"]["raw_scene_id"])
    scene_ids = [str(base.matlab_text(value)) for value in base.matlab_flat(ctx["snapshot"]["sceneIdentity"]["scene_id"])]
    assert scene_ids == contract["scene_ids_all_72"]
    scene_ix = scene_ids.index(scene_id)
    expected_identity = base.scene_identity_row(ctx["snapshot"]["sceneIdentity"], scene_ix)
    # scene_identity has seven source fields only; external identity is bound
    # separately by the lock and each scored raw metric below.
    base.compare_scene_identity(run_start["scene_identity"], expected_identity, ctx["decoder"])
    assert base.matlab_text(run_start["scene_identity"]["scene_id"]) == scene_id
    assert same_path(run_start["physical_B_source_path"], lock_row["B_source"]["path"])
    assert base.matlab_text(run_start["physical_B_source_sha256"]).lower() == lock_row["B_source"]["sha256"].lower()
    assert same_path(run_start["C3_raw_path"], lock_row["C3_reference"]["raw_path"])
    assert base.matlab_text(run_start["C3_raw_sha256"]).lower() == lock_row["C3_reference"]["raw_sha256"].lower()

    # C3 status versions do not all log transition counters; bind only actual fields.
    c3_ref = lock_row["C3_reference"]
    for key, path_key in (("raw_path", "raw_path"), ("run_status_path", "run_status_path"),
                          ("run_start_path", "run_start_path"),
                          ("first_plant_step_marker_path", "first_plant_step_marker_path")):
        file_ref(c3_ref[path_key], c3_ref[key.replace("_path", "_sha256")])
    c3_status = load(c3_ref["run_status_path"])
    assert c3_status["scene_id"] == scene_id and c3_status["status"] == "RUN_COMPLETE_RAW_PENDING_AUDIT"
    assert c3_status["log_status"] == "STABLE" and c3_status["plant_calls"] == 1
    assert c3_status["raw_sha256"].lower() == c3_ref["raw_sha256"].lower()
    assert c3_status["TEST_accessed"] is False and c3_status["training_steps"] == c3_status["optimizer_steps"] == 0
    assert file_ref(lock_row["B_source"]["path"], lock_row["B_source"]["sha256"])

    run_identity = base.matlab_section_safe(raw_path, "runIdentity", ctx["decoder"])
    assert base.matlab_text(run_identity["schema"]) == "C5_MATCHED_ABLATION_RUN_IDENTITY_V1"
    assert base.matlab_text(run_identity["batch_id"]) == batch["batch_id"]
    assert base.matlab_scalar(run_identity["batch_index"]) == batch_index
    assert base.matlab_text(run_identity["phase"]) == "REMAINING60"
    assert base.matlab_text(run_identity["scene_id"]) == scene_id
    assert base.matlab_text(run_identity["candidate"]) == contract["candidate"]
    assert base.matlab_text(run_identity["variant_id"]) == base.matlab_text(run_identity["ablation_mode"]) == variant
    assert base.matlab_flat(run_identity["coordinate_mask"]) == [1.0, 1.0, 0.0]
    for key, digest_key in (("source_binding_sha256", "binding"), ("release_sha256", "release"),
                            ("preflight_sha256", "preflight"), ("input_lock_sha256", "lock"),
                            ("run_contract_sha256", "contract"), ("prepare_result_sha256", "prepare"),
                            ("cfg_opts_snapshot_sha256", "snapshot")):
        assert base.matlab_text(run_identity[key]).lower() == digests[digest_key]
    assert base.matlab_text(run_identity["run_start_sha256"]).lower() == sha(run_start_path).lower()
    assert base.matlab_text(run_identity["W0_sha256"]).lower() == contract["model"]["W0_sha256"].lower()
    assert bool(base.matlab_scalar(run_identity["legacy_stage1_update_enabled"]))
    assert bool(base.matlab_scalar(run_identity["actual_weight_update_enabled"])) is expected_weight_update
    assert bool(base.matlab_scalar(run_identity["actual_prediction_gradient_enabled"])) is False
    assert base.equal_tree(ctx["snapshot"]["W0"], run_identity["W0"], ctx["decoder"]) > 0
    assert base.equal_tree(ctx["snapshot"]["modelIdentity"], run_identity["model_identity"], ctx["decoder"]) == 6
    assert base.equal_tree(ctx["snapshot"]["sourceIdentity"], run_identity["source_identity"], ctx["decoder"]) == ctx["leaves"]["sourceIdentity"]
    base.compare_scene_identity(run_identity["scene_identity"], expected_identity, ctx["decoder"])
    assert same_path(run_identity["physical_B_source_path"], lock_row["B_source"]["path"])
    assert base.matlab_text(run_identity["physical_B_source_sha256"]).lower() == lock_row["B_source"]["sha256"].lower()
    assert same_path(run_identity["C3_raw_path"], c3_ref["raw_path"])
    assert base.matlab_text(run_identity["C3_raw_sha256"]).lower() == c3_ref["raw_sha256"].lower()
    assert base.matlab_scalar(run_identity["training_steps"]) == base.matlab_scalar(run_identity["optimizer_steps"]) == 0
    assert base.matlab_scalar(run_identity["TEST_accessed"]) in (0, False)

    raw_score = scorer.score({"scene_id": scene_id, "method": variant,
                              "path": str(raw_path), "sha256": record["raw_sha256"]})
    assert_metric_refs(raw_score, scene_id, lock_row["external_identity_sha256"])
    event_result = event_module.audit_events(raw_path, run_start["cfg"], variant, w0,
                                             contract["model"]["W0_sha256"])
    assert event_result["event_count"] == 1968 and event_result["actual_prediction_norm_max"] == 0

    baselines, c3_marker_check = baseline_methods(
        scene_id, lock_row, parent_row, False, ctx["c5_dev72_lock"], contract["scene_ids_reuse_12"])
    methods = {variant: raw_score, **baselines}
    assert len({metric["external_identity_sha256"] for metric in methods.values()}) == 1
    assert methods["B_TRACEABLE"]["path"] != lock_row["B_source"]["path"]
    return make_scene_row(
        scene_id, methods, "NEW_REMAINING60_RAW", True, "REMAINING60",
        lock_row["external_identity_sha256"], event_checks=event_result,
        raw_provenance={"raw_path": str(raw_path), "raw_sha256": record["raw_sha256"],
                        "run_status_path": str(status_path), "run_status_sha256": record["run_status_sha256"],
                        "run_start_path": str(run_start_path), "run_start_sha256": record["run_start_sha256"],
                        "batch_index": batch_index},
        baseline_identity_checks={"C3_reference_attempt_marker": c3_marker_check})


def metric_mean(metrics: list[dict]):
    common = set.intersection(*(set(item) for item in metrics))
    numeric = sorted(key for key in common if all(isinstance(item[key], (int, float)) and
                                                  not isinstance(item[key], bool) for item in metrics))
    return {key: math.fsum(float(item[key]) for item in metrics) / len(metrics) for key in numeric}


def comparison_summary(rows: list[dict], baseline: str):
    deltas = [(row["scene_id"], row["deltas_Q_m"][baseline]) for row in rows]
    return {"wins": sum(compare_delta(delta) == "WIN" for _, delta in deltas),
            "losses": sum(compare_delta(delta) == "LOSS" for _, delta in deltas),
            "ties_within_1e_12_m": sum(compare_delta(delta) == "TIE" for _, delta in deltas),
            "wins_improved_gt_1um": sum(delta < -1e-6 for _, delta in deltas),
            "wins_improved_gt_10um": sum(delta < -10e-6 for _, delta in deltas),
            "loss_scenes": [scene for scene, delta in deltas if compare_delta(delta) == "LOSS"],
            "tie_scenes": [scene for scene, delta in deltas if compare_delta(delta) == "TIE"]}


def summarize(rows: list[dict], variant: str, scene_order: list[str]):
    assert [row["scene_id"] for row in rows] == scene_order and len(rows) == 72
    split, task, wind = {}, {}, {}
    for row in rows:
        split.setdefault(row["split"], []).append(row)
        task.setdefault(row["task"], []).append(row)
        wind.setdefault(row["wind_number"], []).append(row)
    groups = {"ALL72": rows, "DEV": split["DEV"], "VAL": split["VAL"],
              "HF_W09_W14": [row for row in rows if 9 <= row["wind_number"] <= 14],
              "W15": wind[15]}
    groups.update(task)
    for name, values in WIND_BANDS.items():
        groups[name] = [row for row in rows if row["wind_number"] in values]
    for number in range(16):
        groups[f"W{number:02d}"] = wind[number]
    methods = (variant, "B_TRACEABLE", "C3", "C5_M110")
    summaries = {}
    for name, subset in groups.items():
        assert subset
        method_means = {method: metric_mean([row["methods"][method] for row in subset]) for method in methods}
        summaries[name] = {"scene_count": len(subset), "scene_ids": [row["scene_id"] for row in subset],
                           "equal_scene_weighted_mean_metrics": method_means,
                           "candidate_vs_B_TRACEABLE": comparison_summary(subset, "B_TRACEABLE"),
                           "candidate_vs_C3": comparison_summary(subset, "C3"),
                           "candidate_vs_C5_M110": comparison_summary(subset, "C5_M110")}
    all_losses = {baseline: [row for row in rows if compare_delta(row["deltas_Q_m"][baseline]) == "LOSS"]
                  for baseline in ("B_TRACEABLE", "C3", "C5_M110")}
    return {"scene_count": len(rows), "scene_order": scene_order,
            "tie_tolerance_m": TIE_TOLERANCE_M,
            "wind_band_definitions": {name: sorted(value) for name, value in WIND_BANDS.items()},
            "groups": summaries, "all_losses_with_full_scene_metrics": all_losses}


def run_audit(experiment_root: Path, execution_root: Path, output: Path):
    assert not output.exists(), f"refusing to overwrite: {output}"
    for path, key in ((MANIFEST, "manifest"), (BASE_PATH, "base_auditor"), (DECODER_PATH, "decoder"),
                      (SCORER_PATH, "scorer"), (ABLACTION_HELPER, "ablation_helper"),
                      (SCREEN12_AUDITOR, "screen12_auditor"), (EVENT_AUDIT, "event_audit"),
                      (C5_PARENT, "c5_parent_review")):
        assert sha(path).lower() == PINNED[key]
    base = module_at(BASE_PATH, "pinned_c5_dev72_raw_parent")
    decoder_module = module_at(DECODER_PATH, "pinned_c5_raw_decoder")
    scorer = module_at(SCORER_PATH, "pinned_c5_raw_scorer")
    event_module = module_at(EVENT_AUDIT, "pinned_c5_ablation_event_audit")
    parent_review = load(C5_PARENT)
    parent_rows, parent_order = baseline_row_index(parent_review)

    # Gate both sequential batch processes before opening any new raw file.
    contexts = [make_common_context(variant, experiment_root, execution_root, base) for variant in VARIANTS]
    for ctx in contexts:
        assert ctx["contract"]["scene_ids_all_72"] == parent_order
        load_batch_records(ctx)

    variants = {}
    for ctx in contexts:
        variant = ctx["variant"]
        reuse_rows, reuse_sources = load_reuse_screen_rows(ctx, parent_rows)
        new_rows = []
        for index, (record, scene_id) in enumerate(zip(ctx["batch_records"], ctx["contract"]["scene_ids_remaining_60"]), start=1):
            new_rows.append(audit_new_record(ctx, record, index, scene_id, parent_rows[scene_id],
                                             base, scorer, event_module))
        row_map = {**reuse_rows, **{row["scene_id"]: row for row in new_rows}}
        assert len(row_map) == 72 and set(row_map) == set(ctx["contract"]["scene_ids_all_72"])
        rows = [row_map[sid] for sid in ctx["contract"]["scene_ids_all_72"]]
        summary = summarize(rows, variant, ctx["contract"]["scene_ids_all_72"])
        variants[variant] = {
            "scene_count": 72, "new_raw_audits": 60, "screen12_audit_reuse": 12,
            "batch_exit_scope": "SHARED_BATCH_PROCESS_NOT_INDIVIDUAL_SCENE_PROCESS",
            "natural_os_exit": {"path": str(ctx["exit_path"]), "sha256": ctx["exit_sha"],
                                "matlab_os_exit_code": 0},
            "input_file_sha256": {key: value for key, value in ctx["digests"].items()},
            "closed_c5_dev72_input_lock": {"path": str(ctx["c5_dev72_lock_path"]),
                                            "sha256": sha(ctx["c5_dev72_lock_path"])},
            "batch_body_sha256": ctx["batch_body_digests"],
            "screen12_parent_evidence": reuse_sources,
            "leaf_counts": ctx["leaves"], "active_source_count": 32,
            "rows": rows, "summary": summary,
            "plant_calls_in_audit": 0, "training_steps": 0, "optimizer_steps": 0, "TEST_accessed": False,
        }
    result = {"schema": "C5_MATCHED_ABLATION_DEV72_BOTH_RAW_PARENT_AUDIT_V1",
              "status": "PASS_C5_MATCHED_ABLATION_DEV72_ALL_EVENTS",
              "dataset": {"scene_count": 72, "new_scenes_per_variant": 60, "screen12_reused_per_variant": 12,
                          "scene_order": contexts[0]["contract"]["scene_ids_all_72"],
                          "candidate_variants": list(VARIANTS), "baseline_methods": ["B_TRACEABLE", "C3", "C5_M110"]},
              "tie_tolerance_m": TIE_TOLERANCE_M,
              "source_files": {"manifest": {"path": str(MANIFEST), "sha256": sha(MANIFEST)},
                               "C5_DEV72_parent_review": {"path": str(C5_PARENT), "sha256": sha(C5_PARENT)},
                               "auditor_sha256": sha(Path(__file__)),
                               "base_auditor_sha256": sha(BASE_PATH), "decoder_sha256": sha(DECODER_PATH),
                               "scorer_sha256": sha(SCORER_PATH), "screen12_auditor_sha256": sha(SCREEN12_AUDITOR),
                               "event_audit_sha256": sha(EVENT_AUDIT)},
              "variants": variants,
              "Plant_started_by_auditor": False, "training_started": False, "TEST_accessed": False}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-root", type=Path, default=EXP_ROOT)
    parser.add_argument("--execution-report-root", type=Path, default=DEFAULT_EXEC_ROOT)
    parser.add_argument("--output", type=Path,
                        default=HERE / "C5_MATCHED_ABLATION_DEV72_BOTH_RAW_PARENT_AUDIT_v1.json")
    args = parser.parse_args()
    root = ROOT.resolve()
    experiment_root = args.experiment_root if args.experiment_root.is_absolute() else root / args.experiment_root
    execution_root = args.execution_report_root if args.execution_report_root.is_absolute() else root / args.execution_report_root
    output = args.output if args.output.is_absolute() else root / args.output
    result = run_audit(experiment_root.resolve(), execution_root.resolve(), output.resolve())
    print(json.dumps({"status": result["status"], "scene_count": 72,
                      "variants": list(result["variants"]), "output": str(output.resolve()),
                      "output_sha256": sha(output), "auditor_sha256": sha(Path(__file__))}, ensure_ascii=False))


if __name__ == "__main__":
    main()
