#!/usr/bin/env python3
"""Audit and score the six-method TEST48 raw package after its six natural OS0 exits.

This wrapper is intentionally inert on import. Its CLI reads the frozen TEST package
only when explicitly run; this deliverable's self-check uses small synthetic arrays.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import h5py
import numpy as np


ROOT = Path(__file__).resolve().parents[3]
TASK = ROOT / "experiments" / "c5_test48_v3"
REPORT = ROOT / "reports" / "paper_continuation_20261023" / "test_entry_v3"
OUTPUT_DIR = ROOT / "reports" / "paper_continuation_20261023" / "test_raw_review_v1"
ROOT_INPUT_REVIEW = (ROOT / "reports" / "paper_continuation_20261023" / "test_input_review_v1"
                     / "PARENT_FROZEN_TEST_INPUT_REVIEW_v1.json")
ROOT_INPUT_REVIEW_SHA256 = "98a93686a1bdd00b64031fa5c1518fd63b62847cfad2e31019b27845e2eb8da1"

ENTRY = TASK / "test48_entry_v1.m"
LAUNCHER = TASK / "RUN_TEST48_EXACT_v1.ps1"
SCORER = ROOT / "reports" / "delayed_prediction_c3_dev72_parent_20261023" / "parent_raw_metrics.py"
C5_REVIEWER = ROOT / "reports" / "paper_continuation_20261023" / "c5_dev72_parent_review" / "audit_c5_dev72_raw_parent_v4.py"
ABLATION_AUDITOR = ROOT / "reports" / "paper_continuation_20261023" / "c5_matched_ablation_parent_raw_review" / "event_audit_c5_matched_ablation.py"
DECODER = ROOT / "reports" / "paper14_v2" / "phase1" / "audit_w15_position_replay.py"

CONTRACT = TASK / "TEST48_RUN_CONTRACT_v1.json"
SOURCE_MANIFEST = REPORT / "TEST_METHOD_SOURCE_MANIFEST_v1.json"
LOCKED_RELEASE = REPORT / "LOCKED_TEST48_PARENT_RELEASE_v1.json"
FREEZE_RELEASE = REPORT / "TEST_INPUT_FREEZE_PARENT_RELEASE_v1.json"
FREEZE_RESULT = REPORT / "TEST_INPUT_FREEZE_RESULT_v1.json"
FREEZE_EXIT = REPORT / "TEST_INPUT_FREEZE_MATLAB_OS_EXIT_v1.json"
INPUT_INDEX = TASK / "input" / "TEST_INPUT_INDEX_v1.json"
SHARED_SCENES = TASK / "input" / "TEST_SCENES_SHARED_v1.mat"
CFG_OPTS = TASK / "input" / "TEST_METHOD_CFG_OPTS_v1.mat"

EXPECTED_METHODS = (
    "B_TRACEABLE",
    "CORRECTED_DSSM14_G12_R32",
    "CORRECTED_KAN14_G12_R32",
    "C5_M110",
    "C5_FREEZE_TRAINED_W0",
    "C5_NO_DELAYED_PREDICTION",
)
C5_METHODS = {"C5_M110", "C5_FREEZE_TRAINED_W0", "C5_NO_DELAYED_PREDICTION"}
ABLATED_METHODS = {"C5_FREEZE_TRAINED_W0", "C5_NO_DELAYED_PREDICTION"}
CORRECTED_METHODS = {"CORRECTED_DSSM14_G12_R32", "CORRECTED_KAN14_G12_R32"}
EXPECTED_SHA256 = {
    "entry": "0490da98749b114ed9e9553fc7cb44349e0c5c9d182551d8a05c844a009b9bf2",
    "launcher": "a5bd7682752a258b9b1ef891e42369e93d033fa5416dba6be89800dbec2559f9",
    "scorer": "c64482d0adbc4358417648ec08351bd78f1d3dbdb38950435fa71b9cb0f531b1",
    "c5_reviewer": "d82e089c7d41f39c620daea63d95315632e6fb2f80addf4dc12e6a4603b8e57e",
    "ablation_auditor": "1a8106ca6df7bb75ecb7a9cf5a09b9f91bc6eaa38547917a1fab677092c3755a",
    "decoder": "372d92cb17da99884e742d3fa0c877200c3bb2bc6fac7f10e7a1a046b97a76af",
}
TIE_AND_TIMING_SCOPE = {
    "samples_per_flight": 20_000,
    "time_grid_s": "transition_time = 0:0.001:19.999",
    "nonready_window": "transition_time < 0.320 s",
    "ready_window": "transition_time >= 0.320 s",
    "all_calls_retained": True,
    "over_1ms_definition": "controller_call_time_s > 0.001 s",
}
REQUIRED_ACTUATOR_FIELDS = (
    "requested_generalized", "controller_clipped_generalized",
    "allocated_generalized", "realized_generalized", "tilt_limited",
    "motor_saturated", "generalized_clipped", "arms/command",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha256_file(path: Path) -> str:
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    def no_duplicate_keys(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, f"Duplicate JSON key {key!r} in {path}")
            result[key] = value
        return result

    def reject_constant(value):
        raise ValueError(f"Non-finite JSON constant {value} in {path}")

    with Path(path).open("r", encoding="utf-8-sig") as stream:
        value = json.load(stream, object_pairs_hook=no_duplicate_keys, parse_constant=reject_constant)
    require(isinstance(value, dict), f"Expected JSON object: {path}")
    return value


def resolve_repo_path(value: str | Path) -> Path:
    path = Path(value)
    return (path if path.is_absolute() else ROOT / path).resolve(strict=True)


def verify_file(path: Path, expected_sha: str, label: str) -> dict[str, str]:
    path = Path(path).resolve(strict=True)
    require(path.is_file(), f"{label} is not a file: {path}")
    actual = sha256_file(path)
    require(actual.lower() == str(expected_sha).lower(), f"{label} SHA mismatch: {path}")
    return {"path": str(path), "sha256": actual}


def module_at(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, f"Cannot import pinned helper: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_helpers():
    paths = {
        "entry": ENTRY, "launcher": LAUNCHER, "scorer": SCORER,
        "c5_reviewer": C5_REVIEWER, "ablation_auditor": ABLATION_AUDITOR,
        "decoder": DECODER,
    }
    observed = {}
    for name, path in paths.items():
        actual = sha256_file(path)
        require(actual.lower() == EXPECTED_SHA256[name], f"Frozen helper changed: {path}")
        observed[name] = {"path": str(path.resolve()), "sha256": actual}
    scorer = module_at(SCORER, "test48_pinned_parent_raw_metrics")
    c5 = module_at(C5_REVIEWER, "test48_pinned_c5_raw_review")
    ablation = module_at(ABLATION_AUDITOR, "test48_pinned_ablation_events")
    decoder = module_at(DECODER, "test48_pinned_mat_decoder")
    require(getattr(c5, "SCORER_SHA", "").lower() == EXPECTED_SHA256["scorer"], "DEV reviewer scorer pin changed")
    require(getattr(c5, "DECODER_SHA", "").lower() == EXPECTED_SHA256["decoder"], "DEV reviewer decoder pin changed")
    require(callable(getattr(scorer, "score", None)), "Pinned parent scorer lacks score()")
    require(callable(getattr(c5, "matlab_section_safe", None)), "Pinned DEV reviewer lacks cell-safe MAT decoder")
    require(callable(getattr(c5, "event_audit", None)), "Pinned C5 event auditor is unavailable")
    require(callable(getattr(ablation, "audit_events", None)), "Pinned ablation event auditor is unavailable")
    return scorer, c5, ablation, decoder, observed


def plain(value, c5_review):
    value = c5_review.matlab_text(value)
    if isinstance(value, np.ndarray):
        return [plain(item, c5_review) for item in value.tolist()]
    if isinstance(value, np.generic):
        return plain(value.item(), c5_review)
    if isinstance(value, dict):
        return {str(key): plain(item, c5_review) for key, item in value.items()}
    if isinstance(value, list):
        return [plain(item, c5_review) for item in value]
    if isinstance(value, tuple):
        return [plain(item, c5_review) for item in value]
    return value


def flat_cell(value, c5_review) -> list[Any]:
    return c5_review.matlab_flat(value)


def scalar(value, c5_review, label: str):
    value = c5_review.matlab_scalar(value)
    value = c5_review.matlab_text(value)
    require(isinstance(value, (str, bool, int, float, np.generic)), f"Expected scalar {label}")
    if isinstance(value, np.generic):
        value = value.item()
    return value


def as_text(value, c5_review, label: str) -> str:
    value = scalar(value, c5_review, label)
    require(isinstance(value, str) and value != "", f"Expected nonempty text {label}")
    return value


def as_bool(value, c5_review, label: str) -> bool:
    value = scalar(value, c5_review, label)
    require(value in (True, False, 1, 0), f"Expected boolean {label}")
    return bool(value)


def as_int(value, c5_review, label: str) -> int:
    value = scalar(value, c5_review, label)
    require(not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(float(value))
            and float(value).is_integer(), f"Expected integer {label}")
    return int(value)


def mat_section(path: Path, name: str, c5_review, decoder):
    return c5_review.matlab_section_safe(path, name, decoder)


def equal_mat(left, right, c5_review, decoder, label: str, *, ignore_marker=False) -> None:
    try:
        c5_review.equal_tree(left, right, decoder, ignore_marker=ignore_marker)
    except Exception as error:
        raise ValueError(f"MATLAB tree mismatch at {label}: {error}") from error


def file_ref_list(refs, label: str, root: Path) -> list[dict[str, str]]:
    require(isinstance(refs, list), f"Expected {label} list")
    checked = []
    for ref in refs:
        require(isinstance(ref, dict) and "path" in ref and "sha256" in ref, f"Malformed {label} reference")
        checked.append(verify_file(resolve_repo_path(ref["path"]), ref["sha256"], label))
    return checked


def sha256_tree_matlab(path: Path) -> str:
    files = sorted(path.rglob("*.m"), key=lambda item: item.name)
    require(files, f"Runtime tree contains no .m files: {path}")
    names = [item.name.casefold() for item in files]
    require(len(names) == len(set(names)), f"Runtime tree has duplicate .m basenames: {path}")
    chunks = []
    for file_path in files:
        resolved = file_path.resolve(strict=True)
        chunks.append(f"{resolved}:{sha256_file(resolved)}\n")
    return hashlib.sha256("".join(chunks).encode("utf-8")).hexdigest()


def verify_manifest_sources(manifest: dict, root: Path) -> dict:
    require(manifest.get("schema") == "TEST48_METHOD_SOURCE_MANIFEST_V1", "Unknown method source manifest schema")
    require(manifest.get("test_accessed") is False and manifest.get("plant_started") is False,
            "Method source manifest must remain the frozen pre-run manifest")
    methods = manifest.get("methods")
    require(isinstance(methods, list) and len(methods) == len(EXPECTED_METHODS), "Expected six manifest methods")
    require(tuple(m.get("method_id") for m in methods) == EXPECTED_METHODS, "Manifest method order/identity changed")
    refs = []
    model_refs = []
    source_ref_by_method = {}
    for method in methods:
        mid = method["method_id"]
        refs_for_method = method.get("source_refs")
        require(isinstance(refs_for_method, list) and refs_for_method, f"Missing source_refs for {mid}")
        source_ref_by_method[mid] = refs_for_method
        refs.extend((mid, ref) for ref in refs_for_method)
        model_refs.extend((mid, ref) for ref in method.get("model_refs", []))
        for field, hash_field in (("cfg_opts_snapshot_path", "cfg_opts_snapshot_sha256"),
                                  ("run_contract_path", "run_contract_sha256")):
            path_value = method.get(field, "")
            if path_value:
                verify_file(resolve_repo_path(path_value), method[hash_field], f"{mid} {field}")
        runtime_path = method.get("runtime_tree_path", "")
        if runtime_path:
            runtime = resolve_repo_path(runtime_path)
            require(sha256_tree_matlab(runtime).lower() == str(method.get("runtime_tree_sha256", "")).lower(),
                    f"Runtime source tree SHA mismatch for {mid}")
    shared_refs = manifest.get("shared_source_refs")
    require(isinstance(shared_refs, list) and shared_refs, "Missing shared_source_refs")
    refs.extend(("SHARED", ref) for ref in shared_refs)
    code_ref_rows = []
    unique = {}
    for owner, ref in refs:
        require(isinstance(ref, dict) and "path" in ref and "sha256" in ref, "Malformed source reference")
        checked = verify_file(resolve_repo_path(ref["path"]), ref["sha256"], f"source reference for {owner}")
        key = str(Path(checked["path"]).resolve()).casefold()
        if key in unique:
            require(unique[key] == checked["sha256"].lower(), f"Same source path has conflicting hashes: {checked['path']}")
        unique[key] = checked["sha256"].lower()
        code_ref_rows.append({"owner": owner, **checked})
    model_ref_rows = []
    for owner, ref in model_refs:
        require(isinstance(ref, dict) and "path" in ref and "sha256" in ref, f"Malformed model reference for {owner}")
        checked = verify_file(resolve_repo_path(ref["path"]), ref["sha256"], f"model reference for {owner}")
        key = str(Path(checked["path"]).resolve()).casefold()
        if key in unique:
            require(unique[key] == checked["sha256"].lower(), f"Code/model path has conflicting hashes: {checked['path']}")
        unique[key] = checked["sha256"].lower()
        model_ref_rows.append({"owner": owner, "role": ref.get("role", ""), **checked})
    require(len(code_ref_rows) == 200 and len(model_ref_rows) == 12 and len(unique) == 79,
            f"Expected 200 code/shared refs + 12 model refs / 79 unique files; observed "
            f"{len(code_ref_rows)} + {len(model_ref_rows)} / {len(unique)}")
    return {
        "method_ids": list(EXPECTED_METHODS),
        "method_and_shared_source_reference_count": len(code_ref_rows),
        "model_reference_count": len(model_ref_rows),
        "unique_code_and_model_files": len(unique),
        "method_and_shared_source_references": code_ref_rows,
        "model_references": model_ref_rows,
        "source_refs_by_method": source_ref_by_method,
        "methods": methods,
    }


def verify_input_package(contract: dict, manifest: dict, source_manifest_sha: str) -> tuple[dict, dict, dict, dict, list[str], list[str]]:
    require(contract.get("schema") == "TEST48_RUN_CONTRACT_V1", "Unknown run contract schema")
    require(contract.get("state") == "CODE_ONLY_WAITING_FOR_SEPARATE_STAGE_RELEASES", "Unexpected run contract state")
    require(contract.get("method_source_manifest_sha256", "").lower() == source_manifest_sha.lower(),
            "Run contract does not bind the method source manifest")
    execution = contract.get("execution", {})
    require(execution.get("scene_count") == 48 and execution.get("max_unique_plant_calls") == 288
            and execution.get("test_accessed_flag_for_TEST_freeze_and_run") is True,
            "Frozen run scope is not exactly TEST48/288")
    method_order = contract.get("method_order")
    manifest_methods = manifest.get("methods")
    require(isinstance(method_order, list) and len(method_order) == 6, "Run contract needs six methods")
    require(tuple(row.get("id") for row in method_order) == EXPECTED_METHODS, "Run contract method order changed")
    require(tuple(row.get("method_id") for row in manifest_methods) == EXPECTED_METHODS,
            "Manifest method order changed")
    for order, (c_row, m_row) in enumerate(zip(method_order, manifest_methods), start=1):
        require(c_row.get("alias") == m_row.get("alias") and m_row.get("order") == order,
                f"Contract/manifest alias or order mismatch for {EXPECTED_METHODS[order - 1]}")

    index = load_json(INPUT_INDEX)
    freeze = load_json(FREEZE_RESULT)
    freeze_exit = load_json(FREEZE_EXIT)
    freeze_release = load_json(FREEZE_RELEASE)
    release = load_json(LOCKED_RELEASE)
    require(index.get("schema") == "TEST48_INPUT_INDEX_V1" and index.get("status") == "FROZEN_SHARED_TEST_INPUTS",
            "Unknown or incomplete TEST input index")
    scene_ids = index.get("scene_ids")
    scene_digests = index.get("scene_digests")
    require(isinstance(scene_ids, list) and len(scene_ids) == 48 and len(set(scene_ids)) == 48
            and scene_ids == sorted(scene_ids), "Input index scene list is not the unique sorted 48-scene set")
    require(isinstance(scene_digests, list) and len(scene_digests) == 48, "Input index lacks 48 scene digests")
    for scene_id in scene_ids:
        require("_TEST_" in scene_id, f"Non-TEST scene ID in TEST package: {scene_id}")
        task = re.findall(r"(?:^|_)(T[123])(?=_|$)", scene_id)
        wind = re.findall(r"(?:^|_)(W\d{2})(?=_|$)", scene_id)
        require(len(task) == len(wind) == 1 and int(wind[0][1:]) <= 15, f"Unknown frozen scene ID schema: {scene_id}")
    cells = []
    for scene_id in scene_ids:
        task = re.findall(r"(?:^|_)(T[123])(?=_|$)", scene_id)[0]
        wind = re.findall(r"(?:^|_)(W\d{2})(?=_|$)", scene_id)[0]
        cells.append((task, wind))
    require(len(set(cells)) == 48 and set(cells) == {(f"T{i}", f"W{j:02d}") for i in range(1, 4) for j in range(16)},
            "Expected one frozen TEST scene for every task x W00-W15 cell")
    require(index.get("scene_count") == 48 and index.get("TEST_accessed") is True and index.get("plant_calls") == 0,
            "Input index flags or scene count changed")
    require(index.get("scene_set_sha256") and len(index["scene_set_sha256"]) == 64,
            "Input index scene-set SHA is absent")
    shared_sha = verify_file(SHARED_SCENES, index.get("shared_scenes_mat_sha256", ""), "shared scene package")["sha256"]
    cfg_sha = verify_file(CFG_OPTS, index.get("method_cfg_opts_sha256", ""), "method cfg/opts package")["sha256"]
    index_sha = sha256_file(INPUT_INDEX)
    require(index.get("method_source_manifest_sha256", "").lower() == source_manifest_sha.lower(),
            "Input index is not bound to the current source manifest")
    require(freeze.get("schema") == "TEST48_INPUT_FREEZE_RESULT_V1"
            and freeze.get("status") == "PREPARED_TEST48_INPUTS_NO_PLANT"
            and freeze.get("TEST_accessed") is True and freeze.get("plant_calls") == 0
            and freeze.get("scene_count") == 48, "Frozen input result is not complete")
    require(freeze.get("input_index_sha256", "").lower() == index_sha.lower()
            and freeze.get("shared_scenes_mat_sha256", "").lower() == shared_sha.lower()
            and freeze.get("method_cfg_opts_sha256", "").lower() == cfg_sha.lower(),
            "Frozen input result does not bind the index and MAT packages")
    require(freeze_exit.get("schema") == "TEST48_MATLAB_OS_EXIT_V1"
            and freeze_exit.get("mode") == "TEST_INPUT_FREEZE_ONLY"
            and freeze_exit.get("stage") == "TEST_INPUT_FREEZE_ONLY"
            and freeze_exit.get("matlab_os_exit_code") == 0
            and freeze_exit.get("natural_wait_used") is True
            and freeze_exit.get("TEST_accessed") is True
            and freeze_exit.get("plant_authorized") is False,
            "TEST input freeze did not naturally exit MATLAB with OS0")
    freeze_exit_sha = sha256_file(FREEZE_EXIT)
    freeze_result_sha = sha256_file(FREEZE_RESULT)
    freeze_release_sha = sha256_file(FREEZE_RELEASE)
    require(freeze_release.get("schema") == "TEST48_INPUT_FREEZE_RELEASE_V1"
            and freeze_release.get("status") == "APPROVED_TEST_INPUT_FREEZE_ONLY"
            and freeze_release.get("TEST_accessed") is True
            and freeze_release.get("plant_authorized") is False
            and freeze_release.get("scene_generation_authorized") is True
            and freeze_release.get("training_authorized") is False,
            "TEST input-freeze release has unexpected scope")
    require(index.get("freeze_release_sha256", "").lower() == freeze_release_sha.lower(),
            "Input index does not bind the freeze release")
    require(freeze.get("freeze_release_sha256", "").lower() == freeze_release_sha.lower(),
            "Frozen input result does not bind its freeze release")
    require(release.get("schema") == "TEST48_LOCKED_RUN_RELEASE_V1"
            and release.get("status") == "APPROVED_LOCKED_TEST48_PARENT_V1"
            and release.get("plant_authorized") is True
            and release.get("scene_generation_authorized") is False
            and release.get("TEST_accessed") is True
            and release.get("training_authorized") is False,
            "Locked run parent release has unexpected scope")
    require(release.get("scene_count") == 48 and release.get("max_plant_calls") == 288
            and tuple(release.get("method_ids", [])) == EXPECTED_METHODS
            and release.get("scene_set_sha256", "").lower() == index["scene_set_sha256"].lower(),
            "Locked run release does not bind the frozen 48-scene/six-method set")
    require(release.get("input_index_sha256", "").lower() == index_sha.lower()
            and release.get("shared_scenes_mat_sha256", "").lower() == shared_sha.lower()
            and release.get("method_cfg_opts_sha256", "").lower() == cfg_sha.lower()
            and release.get("freeze_result_sha256", "").lower() == freeze_result_sha.lower()
            and release.get("freeze_os_exit_sha256", "").lower() == freeze_exit_sha.lower(),
            "Locked run release does not bind input index, MAT packages, or freeze receipt")
    require(release.get("contract_sha256", "").lower() == sha256_file(CONTRACT).lower()
            and release.get("method_source_manifest_sha256", "").lower() == source_manifest_sha.lower()
            and release.get("entry_sha256", "").lower() == EXPECTED_SHA256["entry"]
            and release.get("launcher_sha256", "").lower() == EXPECTED_SHA256["launcher"],
            "Locked run release does not bind frozen entry/source inputs")
    root_input_review = verify_file(ROOT_INPUT_REVIEW, ROOT_INPUT_REVIEW_SHA256,
                                    "root-frozen TEST input identity/roundtrip audit")
    bound = {
        "contract": {"path": str(CONTRACT.resolve()), "sha256": sha256_file(CONTRACT)},
        "source_manifest": {"path": str(SOURCE_MANIFEST.resolve()), "sha256": source_manifest_sha},
        "parent_release": {"path": str(LOCKED_RELEASE.resolve()), "sha256": sha256_file(LOCKED_RELEASE)},
        "freeze_release": {"path": str(FREEZE_RELEASE.resolve()), "sha256": freeze_release_sha},
        "freeze_result": {"path": str(FREEZE_RESULT.resolve()), "sha256": freeze_result_sha},
        "freeze_os_exit": {"path": str(FREEZE_EXIT.resolve()), "sha256": freeze_exit_sha},
        "input_index": {"path": str(INPUT_INDEX.resolve()), "sha256": index_sha},
        "shared_scenes_mat": {"path": str(SHARED_SCENES.resolve()), "sha256": shared_sha},
        "method_cfg_opts_mat": {"path": str(CFG_OPTS.resolve()), "sha256": cfg_sha},
        "root_input_review": root_input_review,
    }
    optional_paths = {
        "scene_specs": index.get("scene_specs_path"),
        "effective_config": index.get("effective_config_path"),
    }
    for name, path in optional_paths.items():
        require(path, f"Input index lacks {name} path")
        expected = index.get(f"{name}_sha256", "")
        bound[name] = verify_file(resolve_repo_path(path), expected, name)
    require(freeze_release.get("contract_sha256", "").lower() == bound["contract"]["sha256"].lower()
            and freeze_release.get("method_source_manifest_sha256", "").lower() == source_manifest_sha.lower(),
            "Freeze release does not bind contract/source manifest")
    return index, freeze, release, bound, scene_ids, scene_digests


def read_mat_cell_list(path: Path, variable: str, c5_review, decoder, expected_count: int) -> list[Any]:
    raw = mat_section(path, variable, c5_review, decoder)
    values = flat_cell(raw, c5_review)
    require(len(values) == expected_count, f"{variable} cell count mismatch: {len(values)}")
    return values


def verify_scene_and_snapshots(index, scene_ids, scene_digests, c5_review, decoder):
    scene_packs = read_mat_cell_list(SHARED_SCENES, "scenePacks", c5_review, decoder, 48)
    # MATLAB string values in the shared package can be opaque uint32 references in v7.3.
    # Bind scene IDs/digests through the frozen JSON index and each run_start.meta char field.
    snapshots = read_mat_cell_list(CFG_OPTS, "methodSnapshots", c5_review, decoder, 6)
    for idx, (method_id, snapshot) in enumerate(zip(EXPECTED_METHODS, snapshots)):
        require(isinstance(snapshot, dict) and as_text(snapshot.get("method_id"), c5_review, "snapshot.method_id") == method_id,
                f"Config/opts snapshot order mismatch at {idx + 1}")
    cfg0 = snapshots[0]["cfg"]
    for method_id, snapshot in zip(EXPECTED_METHODS, snapshots):
        equal_mat(cfg0, snapshot["cfg"], c5_review, decoder, f"common physical cfg {method_id}")
    c5_w0 = {}
    model_summary = {}
    for method_id, snapshot in zip(EXPECTED_METHODS, snapshots):
        model_identity = snapshot.get("modelIdentity")
        if method_id in C5_METHODS:
            w0 = get_w0(snapshot["opts"], c5_review, method_id)
            identity = plain(model_identity, c5_review)
            require(isinstance(identity, dict) and identity.get("W0_sha256"), f"Missing frozen W0 identity for {method_id}")
            digest = w0_sha256(w0)
            require(digest.lower() == str(identity["W0_sha256"]).lower(), f"Snapshot W0 SHA mismatch for {method_id}")
            c5_w0[method_id] = w0
            model_summary[method_id] = {"model_identity": identity, "W0_sha256": digest}
        elif method_id.startswith("CORRECTED_"):
            identity = plain(model_identity, c5_review)
            require(isinstance(identity, dict) and identity.get("W0_sha256"), f"Missing corrected-model W0 identity for {method_id}")
            w0 = get_w0(snapshot["opts"], c5_review, method_id)
            digest = w0_sha256(w0)
            require(digest.lower() == str(identity["W0_sha256"]).lower(), f"Corrected model W0 SHA mismatch for {method_id}")
            model_summary[method_id] = {"model_identity": identity, "W0_sha256": digest}
        else:
            model_summary[method_id] = {"model_identity": None, "W0_sha256": None,
                                        "note": "B has no C5/native learned-head W0 identity; no head is synthesized."}
    reference_w0 = c5_w0["C5_M110"]
    for method_id, w0 in c5_w0.items():
        require(np.array_equal(reference_w0, w0), f"C5 M110/freeze/no-pred W0 differs in {method_id}")
    return scene_packs, snapshots, model_summary, {key: w0_sha256(value) for key, value in c5_w0.items()}


def get_w0(opts, c5_review, method_id: str) -> np.ndarray:
    require(isinstance(opts, dict), f"Malformed opts for {method_id}")
    runtime = opts.get("stage1_position_runtime")
    require(isinstance(runtime, dict), f"Missing stage1_position_runtime for learned method {method_id}")
    head = runtime.get("position_only_search_head")
    if isinstance(head, dict) and head.get("W0") is not None:
        value = head["W0"]
    elif runtime.get("weight") is not None:
        value = runtime["weight"]
    elif isinstance(runtime.get("model"), dict) and runtime["model"].get("output_W") is not None:
        value = runtime["model"]["output_W"]
    else:
        raise ValueError(f"No explicit model W0/weight in locked opts for {method_id}")
    array = np.asarray(plain(value, c5_review), dtype=np.float64)
    require(array.shape == (33, 3) and np.isfinite(array).all(), f"Invalid 33x3 W0 for {method_id}")
    return array


def w0_sha256(w0: np.ndarray) -> str:
    return hashlib.sha256(np.asarray(w0, dtype="<f8").tobytes(order="F")).hexdigest()


def audit_corrected_initial_weight(raw_path: Path, method_id: str, snapshot: dict, c5_review) -> dict[str, Any]:
    require(method_id in CORRECTED_METHODS, f"Initial-weight raw audit is not applicable to {method_id}")
    expected = get_w0(snapshot["opts"], c5_review, method_id)
    with h5py.File(raw_path, "r") as file:
        require("log" in file and "stage1_position_weight_initial" in file["log"],
                f"Raw log lacks stage1_position_weight_initial for {method_id}")
        actual = get_log_array(file["log"], "stage1_position_weight_initial")
    actual = np.asarray(actual, dtype=np.float64)
    require(actual.shape == expected.shape == (33, 3) and np.isfinite(actual).all(),
            f"Raw initial weight shape/non-finite mismatch for {method_id}")
    require(np.array_equal(actual, expected),
            f"Raw stage1 initial weight differs from the frozen snapshot W0 for {method_id}")
    return {
        "scene_method_status": "PASS_EXACT_INITIAL_WEIGHT_MATCH",
        "raw_field": "log.stage1_position_weight_initial",
        "shape": [33, 3],
        "exact_elementwise_match": True,
        "snapshot_W0_sha256": w0_sha256(expected),
        "raw_initial_W0_sha256": w0_sha256(actual),
    }


def expected_method_tags(method: dict) -> tuple[str, str]:
    method_id = method["method_id"]
    contract_path = method.get("run_contract_path", "")
    if not contract_path:
        legacy = {"CORRECTED_DSSM14_G12_R32": "DSSM14_G12_R32",
                  "CORRECTED_KAN14_G12_R32": "NEW_KAN14_G12_R32"}
        require(method_id in legacy, f"Missing run contract for nonhistorical method {method_id}")
        return legacy[method_id], legacy[method_id]
    contract = load_json(resolve_repo_path(contract_path))
    candidate = contract.get("candidate") or contract.get("method") or method_id
    collector = contract.get("collector_tag") or method_id
    require(isinstance(candidate, str) and candidate and isinstance(collector, str) and collector,
            f"Unknown candidate/collector contract for {method_id}")
    return candidate, collector


def records_from_matlab(value, c5_review, label: str) -> list[dict]:
    value = plain(value, c5_review)
    return records_from_plain_matlab(value, label)


def records_from_plain_matlab(value, label: str) -> list[dict]:
    if isinstance(value, list) and all(isinstance(item, dict) for item in value):
        return [{key: unbox_matlab_struct_field(key, item, label, row_index)
                 for key, item in row.items()} for row_index, row in enumerate(value)]
    if isinstance(value, dict):
        keys = list(value)
        require(keys and all(isinstance(value[key], list) for key in keys),
                f"MATLAB struct-array columns are not all row-preserving lists for {label}")
        lengths = {len(value[key]) for key in keys}
        require(len(lengths) == 1, f"MATLAB struct-array column lengths differ for {label}")
        size = next(iter(lengths))
        rows = []
        for row_index in range(size):
            row = {}
            for key in keys:
                row[key] = unbox_matlab_struct_field(key, value[key][row_index], label, row_index)
            rows.append(row)
        return rows
    raise ValueError(f"Unknown MATLAB struct-array schema for {label}")


def unbox_matlab_struct_field(key: str, item, label: str, row_index: int):
    if key == "which_all_paths":
        if isinstance(item, list) and len(item) == 1 and isinstance(item[0], list):
            item = item[0]
    elif isinstance(item, list) and len(item) == 1:
        item = item[0]
    require(key == "which_all_paths" or not isinstance(item, list),
            f"Unexpected nested MATLAB struct field {label}.{key}[{row_index}]")
    return item


def struct_column_self_check() -> dict[str, Any]:
    synthetic = {
        "batch_index": [[1], [2]],
        "scene_id": [["SYNTHETIC_A"], ["SYNTHETIC_B"]],
        "which_all_paths": [[["locked/a.m", "shadow/a.m"]], [["locked/b.m"]]],
    }
    rows = records_from_plain_matlab(synthetic, "synthetic_column_struct")
    require(rows == [
        {"batch_index": 1, "scene_id": "SYNTHETIC_A", "which_all_paths": ["locked/a.m", "shadow/a.m"]},
        {"batch_index": 2, "scene_id": "SYNTHETIC_B", "which_all_paths": ["locked/b.m"]},
    ], "MATLAB Nx1 struct-column unboxing self-check failed")
    return {"rows_preserved": len(rows), "singleton_columns_unboxed": True,
            "nested_path_cell_preserved": True, "synthetic_only": True}


def validate_bindings(identity, method, c5_review):
    bindings = records_from_matlab(identity.get("which_bindings"), c5_review, "runIdentity.which_bindings")
    refs = method.get("source_refs", [])
    expected_by_name = {}
    for ref in refs:
        path = resolve_repo_path(ref["path"])
        if path.suffix.lower() == ".m":
            key = path.stem.casefold()
            require(key not in expected_by_name or expected_by_name[key] == path,
                    f"Ambiguous locked MATLAB source basename {path.stem}")
            expected_by_name[key] = path
    require(len(bindings) == len(expected_by_name), "which_bindings count differs from locked MATLAB sources")
    seen = set()
    for row in bindings:
        name = str(row.get("function_name", "")).casefold()
        require(name in expected_by_name and name not in seen, f"Unexpected/duplicate which binding {name}")
        expected = expected_by_name[name]
        for key in ("expected_path", "resolved_first_path"):
            actual = resolve_repo_path(row.get(key, ""))
            require(actual == expected, f"MATLAB which binding {key} differs for {name}")
        all_paths = row.get("which_all_paths")
        require(isinstance(all_paths, list) and all_paths, f"Missing which -all paths for {name}")
        require(resolve_repo_path(all_paths[0]) == expected, f"First which -all path differs for {name}")
        seen.add(name)


def strict_equal_json(a, b) -> bool:
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(strict_equal_json(a[key], b[key]) for key in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(strict_equal_json(x, y) for x, y in zip(a, b))
    return a == b


def verify_batch_body(method_id: str, alias: str, method_index: int, scene_ids: list[str], source_sha: str,
                      index_sha: str, shared_sha: str, cfg_sha: str, parent_release_sha: str):
    method_root = TASK / "runs" / alias
    batch_path = method_root / "METHOD_BATCH_STATUS_v1.json"
    body_path = method_root / "METHOD_BODY_COMPLETE_v1.json"
    batch = load_json(batch_path)
    body = load_json(body_path)
    require(batch.get("schema") == "TEST48_METHOD_BATCH_STATUS_V1"
            and batch.get("status") == "COMPLETE_RAW_PENDING_PARENT_AUDIT"
            and batch.get("method_id") == method_id and batch.get("alias") == alias,
            f"Method batch schema/status/identity mismatch for {method_id}")
    require(body.get("schema") == "TEST48_METHOD_BODY_COMPLETE_V1"
            and body.get("status") == "RUN_COMPLETE_RAW_PENDING_PARENT_AUDIT"
            and body.get("method_id") == method_id and body.get("alias") == alias,
            f"Method body schema/status/identity mismatch for {method_id}")
    for source, label in ((batch, "batch"), (body, "body")):
        require(source.get("scene_count") == source.get("completed_scenes") == 48
                and source.get("plant_calls") == 48 and source.get("training_steps") == 0
                and source.get("optimizer_steps") == 0 and source.get("TEST_accessed") is True,
                f"Incomplete {label} counts or run flags for {method_id}")
        require(source.get("parent_release_sha256", "").lower() == parent_release_sha.lower()
                and source.get("input_index_sha256", "").lower() == index_sha.lower()
                and source.get("shared_scenes_mat_sha256", "").lower() == shared_sha.lower()
                and source.get("method_cfg_opts_sha256", "").lower() == cfg_sha.lower()
                and source.get("method_source_manifest_sha256", "").lower() == source_sha.lower(),
                f"{label} does not bind the frozen run inputs for {method_id}")
    require(batch.get("phase") == "LOCKED_TEST48_PARENT_APPROVED", f"Batch phase changed for {method_id}")
    require(batch.get("thread_argument") == "-singleCompThread"
            and batch.get("controller_timer_boundary") ==
            "Frozen controller_call_time_s source unchanged; ends before allocator/Plant/MAT save.",
            f"Frozen timer boundary/thread argument changed for {method_id}")
    require(batch.get("completed_scenes") == 48 and body.get("completed_scenes") == 48, "Method body incomplete")
    require(body.get("scene_ids") == scene_ids, f"Body scene order differs for {method_id}")
    batch_records, body_records = batch.get("records"), body.get("records")
    require(isinstance(batch_records, list) and isinstance(body_records, list)
            and len(batch_records) == len(body_records) == 48, f"Expected 48 records for {method_id}")
    require(strict_equal_json(batch_records, body_records), f"Batch/body record lists differ for {method_id}")
    require(batch.get("runner_sha256", "").lower() == EXPECTED_SHA256["entry"].lower()
            and body.get("runner_sha256", "").lower() == EXPECTED_SHA256["entry"].lower(),
            f"Runner SHA changed for {method_id}")
    return batch, body, batch_records


def verify_os_receipt(method_id: str, alias: str, source_manifest_sha: str, contract_sha: str) -> dict:
    path = REPORT / f"{alias}_MATLAB_OS_EXIT_v1.json"
    receipt = load_json(path)
    require(receipt.get("schema") == "TEST48_MATLAB_OS_EXIT_V1"
            and receipt.get("mode") == "LOCKED_TEST48_PARENT_APPROVED"
            and receipt.get("stage") == "LOCKED_TEST48_PARENT_APPROVED"
            and receipt.get("method_id") == method_id,
            f"Unknown natural MATLAB exit receipt for {method_id}")
    require(receipt.get("process_scope") == "ONE_SEQUENTIAL_METHOD_MATLAB_PROCESS"
            and receipt.get("matlab_os_exit_code") == 0 and receipt.get("natural_wait_used") is True,
            f"Method did not naturally exit OS0: {method_id}")
    require(receipt.get("TEST_accessed") is True and receipt.get("plant_authorized") is True
            and receipt.get("thread_argument") == "-singleCompThread",
            f"Method process receipt flags changed: {method_id}")
    require(receipt.get("command_sha256", "").lower() == EXPECTED_SHA256["launcher"].lower()
            and receipt.get("contract_sha256", "").lower() == contract_sha.lower()
            and receipt.get("source_manifest_sha256", "").lower() == source_manifest_sha.lower(),
            f"Method OS receipt does not bind frozen command/contract/manifest: {method_id}")
    for path_key, sha_key in (("stdout_path", "stdout_sha256"), ("stderr_path", "stderr_sha256")):
        path_value = receipt.get(path_key, "")
        require(path_value, f"Missing {path_key} for {method_id}")
        verify_file(resolve_repo_path(path_value), receipt.get(sha_key, ""), f"{method_id} {path_key}")
    receipt["receipt_path"] = str(path.resolve())
    receipt["receipt_sha256"] = sha256_file(path)
    return receipt


def utc_instant(value: str) -> datetime:
    require(isinstance(value, str) and value, "Missing process timestamp")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    require(parsed.tzinfo is not None and parsed.utcoffset().total_seconds() == 0, "Process timestamp is not UTC")
    return parsed


def validate_receipt_sequence(receipts: list[dict]) -> list[tuple[datetime, datetime]]:
    require(len(receipts) == 6 and tuple(item.get("method_id") for item in receipts) == EXPECTED_METHODS,
            "Expected six natural OS receipts in the frozen method order")
    times = [(utc_instant(item.get("started_utc")), utc_instant(item.get("completed_utc")))
             for item in receipts]
    require(all(start <= end for start, end in times)
            and all(times[i][1] <= times[i + 1][0] for i in range(5)),
            "Natural OS receipts do not prove six sequential method blocks")
    return times


def ensure_scene_id(scene_id: str) -> tuple[str, str]:
    require("_TEST_" in scene_id, f"Unexpected non-TEST scene id {scene_id}")
    tasks = re.findall(r"(?:^|_)(T[123])(?=_|$)", scene_id)
    winds = re.findall(r"(?:^|_)(W\d{2})(?=_|$)", scene_id)
    require(len(tasks) == len(winds) == 1 and int(winds[0][1:]) <= 15,
            f"Unknown TEST scene id schema: {scene_id}")
    return tasks[0], winds[0]


def get_log_array(group, key: str) -> np.ndarray:
    require(key in group, f"Required raw log channel missing: {key}")
    value = np.asarray(group[key])
    return value.T if value.ndim == 2 else value


def audit_actuators(raw_path: Path) -> dict:
    with h5py.File(raw_path, "r") as file:
        require("log" in file and isinstance(file["log"], h5py.Group), f"Raw MAT lacks /log group: {raw_path}")
        log = file["log"]
        shapes = {}
        for key in REQUIRED_ACTUATOR_FIELDS:
            value = get_log_array(log, key)
            require(value.ndim >= 1 and value.shape[0] == 20_000 and value.size > 0,
                    f"Actuator channel has incomplete transition coverage: {key}")
            require(np.issubdtype(value.dtype, np.number) or value.dtype == np.bool_,
                    f"Actuator channel has unknown dtype: {key}")
            require(np.isfinite(value).all(), f"Non-finite actuator channel: {key}")
            shapes[key] = list(value.shape)
        return {"all_required_channels_finite": True, "sample_count_each": 20_000,
                "channel_shapes": shapes}


def timing_summary(transition_time: np.ndarray, calls: np.ndarray) -> dict[str, float | int]:
    t = np.asarray(transition_time, dtype=np.float64).reshape(-1)
    values = np.asarray(calls, dtype=np.float64).reshape(-1)
    require(t.shape == values.shape == (20_000,), "Timing arrays must contain all 20,000 transitions")
    require(np.isfinite(t).all() and np.isfinite(values).all() and np.all(values >= 0),
            "Timing array is non-finite or negative")
    ready = t >= 0.320
    nonready = t < 0.320
    require(int(ready.sum()) == 19_680 and int(nonready.sum()) == 320,
            "The frozen common ready/nonready window has unexpected sample counts")

    return summarize_timing_values(t, values)


def summarize_timing_values(transition_time: np.ndarray, calls: np.ndarray) -> dict[str, float | int]:
    t = np.asarray(transition_time, dtype=np.float64).reshape(-1)
    values = np.asarray(calls, dtype=np.float64).reshape(-1)
    require(t.shape == values.shape and values.size > 0, "Timing values must be nonempty paired vectors")
    require(np.isfinite(t).all() and np.isfinite(values).all() and np.all(values >= 0),
            "Timing values are non-finite or negative")
    ready = t >= 0.320
    nonready = t < 0.320

    def summarize(prefix: str, subset: np.ndarray) -> dict[str, float]:
        require(subset.size > 0, f"Empty timing subset: {prefix}")
        return {
            f"controller_{prefix}mean_s": float(np.mean(subset)),
            f"controller_{prefix}p50_s": float(np.quantile(subset, 0.50)),
            f"controller_{prefix}p95_s": float(np.quantile(subset, 0.95)),
            f"controller_{prefix}p99_s": float(np.quantile(subset, 0.99)),
            f"controller_{prefix}max_s": float(np.max(subset)),
            f"controller_{prefix}over_1ms_fraction": float(np.mean(subset > 0.001)),
        }

    result = {
        "controller_mean_s": float(np.mean(values)),
        "controller_p50_s": float(np.quantile(values, 0.50)),
        "controller_p95_s": float(np.quantile(values, 0.95)),
        "controller_p99_s": float(np.quantile(values, 0.99)),
        "controller_max_s": float(np.max(values)),
        "controller_over_1ms_fraction": float(np.mean(values > 0.001)),
        "controller_ready_calls": int(ready.sum()),
        "controller_nonready_calls": int(nonready.sum()),
    }
    result.update(summarize("ready_", values[ready]))
    result.update(summarize("nonready_", values[nonready]))
    require(all(math.isfinite(float(value)) for value in result.values()), "Timing summary contains non-finite value")
    return result


def native_numeric_vector(debug_group, key: str, c5_review) -> np.ndarray:
    require(key in debug_group, f"Native forward_debug field is missing: {key}")
    decoded = c5_review.h5_tree_cell_safe(debug_group[key])
    decoded = c5_review.matlab_text(decoded)
    value = np.asarray(decoded)
    require(value.dtype.kind in "biuf", f"Native forward_debug field has unknown numeric schema: {key}")
    value = value.astype(np.float64, copy=False).reshape(-1)
    require(value.size > 0 and np.isfinite(value).all(), f"Native forward_debug field is empty/non-finite: {key}")
    return value


def native_scalar_field(debug_group, key: str, c5_review) -> float:
    require(key in debug_group, f"Native forward_debug scalar is missing: {key}")
    decoded = c5_review.matlab_text(c5_review.h5_tree_cell_safe(debug_group[key]))
    value = np.asarray(decoded)
    require(value.dtype.kind in "biuf" and value.size == 1,
            f"Native forward_debug scalar has unknown schema: {key}")
    scalar_value = float(value.reshape(-1)[0])
    require(math.isfinite(scalar_value), f"Native forward_debug scalar is non-finite: {key}")
    return scalar_value


def numeric_summary(values: np.ndarray) -> dict[str, float | int | None]:
    values = np.asarray(values, dtype=np.float64).reshape(-1)
    require(np.isfinite(values).all(), "Native telemetry summary received non-finite values")
    if not values.size:
        return {"count": 0, "mean_s": None, "p50_s": None, "p95_s": None,
                "p99_s": None, "max_s": None, "over_1ms_fraction": None}
    return {"count": int(values.size), "mean_s": float(np.mean(values)),
            "p50_s": float(np.quantile(values, 0.50)), "p95_s": float(np.quantile(values, 0.95)),
            "p99_s": float(np.quantile(values, 0.99)), "max_s": float(np.max(values)),
            "over_1ms_fraction": float(np.mean(values > 0.001))}


def native_readiness(raw_path: Path, method_id: str, c5_review) -> dict[str, Any]:
    observed = {}
    with h5py.File(raw_path, "r") as file:
        log = file["log"]
        key = "stage1_position_event_inference_valid"
        valid = None
        if key in log:
            value = get_log_array(log, key).reshape(-1)
            require(value.shape == (20_000,) and np.isfinite(value).all(),
                    "Native event-valid marker is incomplete/non-finite")
            require(np.all(np.isin(value, (0, 1))), "Native event-valid vector is not boolean")
            positions = np.flatnonzero(value)
            valid = value.astype(bool)
            observed[key] = {"available": True, "semantics": "event inference-valid marker; not a continuous readiness signal",
                             "sample_count": int(value.size), "positive_count": int(len(positions)),
                             "first_positive_transition_index_zero_based": int(positions[0]) if len(positions) else None,
                             "last_positive_transition_index_zero_based": int(positions[-1]) if len(positions) else None}
        stage1_time_key = "stage1_position_inference_time_s"
        if stage1_time_key in log and valid is not None:
            inference_time = get_log_array(log, stage1_time_key).reshape(-1)
            transition_time = get_log_array(log, "transition_time").reshape(-1)
            require(inference_time.shape == transition_time.shape == valid.shape == (20_000,),
                    "Stage1 event timer/mask/transition vectors have unknown shapes")
            require(np.isfinite(inference_time).all() and np.all(inference_time >= 0)
                    and np.isfinite(transition_time).all(),
                    "Stage1 event timing contains non-finite or negative values")
            cutoff_ready = transition_time >= 0.320
            observed["stage1_position_inference_time_s"] = {
                "available": True,
                "semantics": "event-call timing selected by stage1_position_event_inference_valid; not the 20,000-call controller timer",
                "valid_event_count": int(valid.sum()),
                "valid_event_calls_before_0_320_s": int(np.count_nonzero(valid & ~cutoff_ready)),
                "valid_event_calls_at_or_after_0_320_s": int(np.count_nonzero(valid & cutoff_ready)),
                "valid_event_call_time_s": {
                    "all_valid_events": numeric_summary(inference_time[valid]),
                    "before_0_320_s": numeric_summary(inference_time[valid & ~cutoff_ready]),
                    "at_or_after_0_320_s": numeric_summary(inference_time[valid & cutoff_ready]),
                },
            }
        elif stage1_time_key in log:
            observed[stage1_time_key] = {"available": False,
                                         "reason": "stage1_position_event_inference_valid mask missing; event-call timing cannot be selected"}
        elif valid is not None:
            observed[stage1_time_key] = {"available": False,
                                         "reason": "stage1_position_inference_time_s is absent from this raw log"}
        else:
            observed["stage1_position_event_inference"] = {
                "available": False,
                "reason": "stage1_position_event_inference_valid mask is absent from this raw log",
            }
        debug_nodes = []
        for container_name, container in (("/log", log), ("/", file)):
            for debug_name in ("learned_forward_debug", "forward_debug"):
                if debug_name in container:
                    debug_nodes.append((container_name, debug_name, container[debug_name]))
        require(len(debug_nodes) <= 1, "Ambiguous/duplicate forward_debug native telemetry locations")
        if debug_nodes:
            container_name, debug_name, debug_group = debug_nodes[0]
            require(isinstance(debug_group, h5py.Group), "Native forward_debug is not a MATLAB struct group")
            if "enabled" in debug_group or "count" in debug_group:
                require("enabled" in debug_group and "count" in debug_group,
                        "Native forward_debug enabled/count metadata is incomplete")
                enabled_value = native_scalar_field(debug_group, "enabled", c5_review)
                count_value = native_scalar_field(debug_group, "count", c5_review)
                require(enabled_value in (0.0, 1.0) and count_value >= 0 and count_value.is_integer(),
                        "Native forward_debug enabled/count values are invalid")
                if enabled_value == 0.0 and count_value == 0.0:
                    require(set(debug_group.keys()) == {"enabled", "count"},
                            "Only the exact enabled=false,count=0 disabled-debug schema is accepted")
                    observed[f"{container_name}/{debug_name}"] = {
                        "available": False, "status": "native_debug_disabled",
                        "enabled": False, "count": 0,
                    }
                    debug_group = None
                else:
                    require(enabled_value == 1.0 and count_value > 0,
                            "Unknown native forward_debug enabled/count state")
                    expected_debug_count = int(count_value)
            else:
                raise ValueError("Unknown native forward_debug schema: missing enabled/count metadata")
            if debug_group is not None:
                event_time = native_numeric_vector(debug_group, "time", c5_review)
                history_ready = native_numeric_vector(debug_group, "history_ready", c5_review)
                model_call = native_numeric_vector(debug_group, "model_call", c5_review)
                call_time = native_numeric_vector(debug_group, "network_call_time_s", c5_review)
                require(event_time.shape == history_ready.shape == model_call.shape == call_time.shape
                        and event_time.size == expected_debug_count,
                        "Native forward_debug vector lengths differ from each other/count")
                require(np.all(np.isin(history_ready, (0, 1))) and np.all(np.isin(model_call, (0, 1))),
                        "Native forward_debug readiness/model-call fields are not boolean")
                require(np.all(event_time >= 0) and np.all(call_time >= 0),
                        "Native forward_debug contains negative time values")
                ready = history_ready.astype(bool)
                called = model_call.astype(bool)
                after_cutoff = event_time >= 0.320
                call_mask = called
                observed[f"{container_name}/{debug_name}"] = {
                    "available": True, "status": "native_forward_debug_present",
                    "sample_count": int(event_time.size),
                    "history_ready_count": int(ready.sum()),
                    "model_call_count": int(called.sum()),
                    "model_calls_with_history_ready": int(np.count_nonzero(called & ready)),
                    "model_calls_before_0_320_s": int(np.count_nonzero(called & ~after_cutoff)),
                    "model_calls_at_or_after_0_320_s": int(np.count_nonzero(called & after_cutoff)),
                    "network_call_time_s": {
                        "all_model_calls": numeric_summary(call_time[call_mask]),
                        "before_0_320_s": numeric_summary(call_time[call_mask & ~after_cutoff]),
                        "at_or_after_0_320_s": numeric_summary(call_time[call_mask & after_cutoff]),
                    },
                }
    has_debug = any(detail.get("status") == "native_forward_debug_present" for detail in observed.values())
    debug_disabled = any(detail.get("status") == "native_debug_disabled" for detail in observed.values())
    event_valid_count = int(observed.get(key, {}).get("positive_count", 0))
    if method_id == "B_TRACEABLE" and not has_debug and event_valid_count == 0:
        status = "native_not_applicable"
    elif has_debug:
        status = "native_forward_debug_present"
    elif key in observed:
        status = "event_marker_only"
    elif debug_disabled:
        status = "native_debug_disabled"
    else:
        status = "native_unavailable"
    return {"available": any(bool(detail.get("available")) for detail in observed.values()),
            "status": status, "sources": observed}


def get_path_field(mapping, *keys):
    value = mapping
    for key in keys:
        require(isinstance(value, dict) and key in value, f"Missing locked opts field: {'/'.join(keys)}")
        value = value[key]
    return value


def verify_run_identity_and_start(raw_path, start_path, record, method, method_index, scene_id, scene_pack,
                                  snapshot, hashes, scene_digest, c5_review, decoder):
    identity = mat_section(raw_path, "runIdentity", c5_review, decoder)
    meta = mat_section(start_path, "meta", c5_review, decoder)
    require(isinstance(identity, dict) and isinstance(meta, dict), "runIdentity or run_start meta has unknown schema")
    method_id = method["method_id"]
    alias = method["alias"]
    expected_candidate, expected_collector = expected_method_tags(method)
    identity_checks = {
        "schema": "TEST48_RUN_IDENTITY_V1", "method_id": method_id, "alias": alias,
        "scene_id": scene_id, "scene_digest_sha256": scene_digest,
        "method_source_manifest_sha256": hashes["source_manifest"],
        "method_cfg_opts_snapshot_sha256": hashes["method_cfg_opts_mat"],
        "parent_release_sha256": hashes["parent_release"],
        "input_index_sha256": hashes["input_index"],
        "runner_sha256": EXPECTED_SHA256["entry"],
        "thread_argument": "-singleCompThread",
    }
    for key, expected in identity_checks.items():
        actual = scalar(identity.get(key), c5_review, f"runIdentity.{key}")
        require(str(actual).lower() == str(expected).lower(), f"runIdentity {key} mismatch for {method_id}/{scene_id}")
    require(as_bool(identity.get("TEST_accessed"), c5_review, "runIdentity.TEST_accessed")
            and as_int(identity.get("plant_calls"), c5_review, "runIdentity.plant_calls") == 1
            and as_int(identity.get("training_steps"), c5_review, "runIdentity.training_steps") == 0
            and as_int(identity.get("optimizer_steps"), c5_review, "runIdentity.optimizer_steps") == 0
            and not as_bool(identity.get("parameter_or_seed_search"), c5_review, "runIdentity.parameter_or_seed_search"),
            f"runIdentity execution flags invalid for {method_id}/{scene_id}")
    require(as_int(identity.get("method_block_order"), c5_review, "runIdentity.method_block_order") == method_index,
            f"Method block order mismatch for {method_id}/{scene_id}")
    require(as_text(identity.get("runner_path"), c5_review, "runIdentity.runner_path").casefold()
            == str(ENTRY.resolve()).casefold(), f"Runner path mismatch for {method_id}/{scene_id}")
    require(as_text(identity.get("run_start_sha256"), c5_review, "runIdentity.run_start_sha256").lower()
            == sha256_file(start_path).lower(), f"run_start SHA mismatch for {method_id}/{scene_id}")
    marker_path = Path(record["first_plant_step_marker_path"]).resolve(strict=True)
    require(as_text(identity.get("first_plant_step_marker_sha256"), c5_review, "runIdentity.first_plant_step_marker_sha256").lower()
            == sha256_file(marker_path).lower(), f"Plant marker SHA mismatch for {method_id}/{scene_id}")
    require(re.fullmatch(r"[0-9a-fA-F]{64}", as_text(identity.get("pre_identity_append_sha256"), c5_review,
                                                        "runIdentity.pre_identity_append_sha256")) is not None,
            f"Missing pre-identity append raw SHA for {method_id}/{scene_id}")
    for key, expected in (("schema", "TEST48_RUN_START_METADATA_V1"), ("method_id", method_id), ("alias", alias),
                          ("scene_id", scene_id), ("method_source_manifest_sha256", hashes["source_manifest"]),
                          ("method_cfg_opts_snapshot_sha256", hashes["method_cfg_opts_mat"]),
                          ("input_index_sha256", hashes["input_index"]), ("parent_release_sha256", hashes["parent_release"])):
        actual = scalar(meta.get(key), c5_review, f"run_start.meta.{key}")
        require(str(actual).lower() == str(expected).lower(), f"run_start meta {key} mismatch for {method_id}/{scene_id}")
    require(as_bool(meta.get("TEST_accessed"), c5_review, "run_start.meta.TEST_accessed")
            and as_int(meta.get("plant_calls_before_invocation"), c5_review, "run_start.meta.plant_calls_before_invocation") == 0
            and as_int(meta.get("training_steps"), c5_review, "run_start.meta.training_steps") == 0
            and as_int(meta.get("optimizer_steps"), c5_review, "run_start.meta.optimizer_steps") == 0
            and as_int(meta.get("batch_index"), c5_review, "run_start.meta.batch_index") == int(record["batch_index"])
            and as_int(meta.get("batch_total"), c5_review, "run_start.meta.batch_total") == 48,
            f"run_start metadata execution flags invalid for {method_id}/{scene_id}")
    require(as_int(meta.get("method_block_order"), c5_review, "run_start.meta.method_block_order") == method_index
            and as_text(meta.get("thread_argument"), c5_review, "run_start.meta.thread_argument") == "-singleCompThread",
            f"run_start block/thread binding invalid for {method_id}/{scene_id}")
    attempt_dir = raw_path.parent
    for key, expected_path in (("attempt_started_marker_path", attempt_dir / "attempt_started.marker"),
                               ("first_plant_step_marker_path", attempt_dir / "first_plant_step.marker"),
                               ("raw_path", raw_path), ("run_status_path", attempt_dir / "run_status.json")):
        actual_path = Path(as_text(meta.get(key), c5_review, f"run_start.meta.{key}")).resolve()
        require(actual_path == expected_path.resolve(),
                f"run_start meta {key} mismatch for {method_id}/{scene_id}")
    require(as_text(meta.get("candidate"), c5_review, "run_start.meta.candidate") == expected_candidate
            and as_text(meta.get("collector_tag"), c5_review, "run_start.meta.collector_tag") == expected_collector,
            f"Run candidate/collector identity mismatch for {method_id}/{scene_id}")
    require(str(scalar(meta.get("scene_digest_sha256"), c5_review, "run_start.meta.scene_digest_sha256")).lower()
            == scene_digest.lower(), f"run_start scene digest mismatch for {method_id}/{scene_id}")
    equal_mat(snapshot["cfg"], mat_section(start_path, "cfg", c5_review, decoder), c5_review, decoder,
              f"run_start.cfg {method_id}/{scene_id}")
    opts = mat_section(start_path, "opts", c5_review, decoder)
    equal_mat(snapshot["opts"], opts, c5_review, decoder, f"run_start.opts {method_id}/{scene_id}", ignore_marker=True)
    marker_in_opts = opts.get("r2e_first_plant_step_marker") if isinstance(opts, dict) else None
    require(str(plain(marker_in_opts, c5_review)).casefold() == str(marker_path).casefold(),
            f"run_start opts marker path mismatch for {method_id}/{scene_id}")
    equal_mat(scene_pack["scene"], mat_section(start_path, "scene", c5_review, decoder), c5_review, decoder,
              f"scene pack scene {method_id}/{scene_id}")
    equal_mat(scene_pack["metadata"], mat_section(start_path, "sceneMeta", c5_review, decoder), c5_review, decoder,
              f"scene pack metadata {method_id}/{scene_id}")
    equal_mat(scene_pack["spec"], mat_section(start_path, "spec", c5_review, decoder), c5_review, decoder,
              f"scene pack spec {method_id}/{scene_id}")
    equal_mat(identity.get("which_bindings"), meta.get("which_bindings"), c5_review, decoder,
              f"which bindings in runIdentity and run_start {method_id}/{scene_id}")
    equal_mat(identity.get("model_identity"), meta.get("modelIdentity"), c5_review, decoder,
              f"model identity in runIdentity and run_start {method_id}/{scene_id}")
    equal_mat(snapshot.get("modelIdentity"), meta.get("modelIdentity"), c5_review, decoder,
              f"frozen model identity {method_id}/{scene_id}")
    model_refs = {ref.get("role"): ref for ref in method.get("model_refs", [])}
    expected_model_sha = model_refs.get("model_mat", {}).get("sha256", "")
    expected_normalizer_sha = model_refs.get("normalizer", {}).get("sha256", "")
    require(str(scalar(identity.get("model_mat_sha256"), c5_review, "model_mat_sha256")).lower()
            == str(expected_model_sha).lower()
            and str(scalar(identity.get("normalizer_sha256"), c5_review, "normalizer_sha256")).lower()
            == str(expected_normalizer_sha).lower(), f"Model/normalizer source SHA mismatch for {method_id}/{scene_id}")
    equal_mat(identity.get("machine_info"), meta.get("machine_info"), c5_review, decoder,
              f"machine metadata {method_id}/{scene_id}")
    snapshot_identity = plain(snapshot.get("modelIdentity"), c5_review)
    expected_initial_weight_identity = snapshot_identity.get("W0_sha256", "") if isinstance(snapshot_identity, dict) else ""
    actual_initial_weight_identity = scalar(identity.get("initial_weight_identity"), c5_review, "initial_weight_identity")
    require(str(actual_initial_weight_identity) == str(expected_initial_weight_identity),
            f"Initial W0 identity mismatch for {method_id}/{scene_id}")
    validate_bindings(identity, method, c5_review)
    return identity, meta, opts


def verify_record_files(record, method_id, alias, method_index, scene_id, scene_digest, source_sha,
                        index_sha, shared_sha, cfg_sha, parent_release_sha):
    attempt = TASK / "runs" / alias / scene_id / "attempt_01"
    expected_paths = {
        "raw_path": attempt / "raw_run.mat",
        "run_start_path": attempt / "run_start.mat",
        "run_status_path": attempt / "run_status.json",
        "attempt_started_marker_path": attempt / "attempt_started.marker",
        "first_plant_step_marker_path": attempt / "first_plant_step.marker",
    }
    require(record.get("batch_index") == int(scene_ids_index(scene_id)), "Internal scene index lookup failure")
    require(record.get("scene_id") == scene_id and record.get("status") == "RUN_COMPLETE_RAW_PENDING_PARENT_AUDIT"
            and record.get("plant_calls") == 1 and record.get("TEST_accessed") is True,
            f"Body record identity/status flags invalid for {method_id}/{scene_id}")
    require(method_index in range(1, 7), "Invalid method process order")
    for path_key, expected_path in expected_paths.items():
        actual = Path(record.get(path_key, "")).resolve(strict=True)
        require(actual == expected_path.resolve(), f"Unexpected {path_key} for {method_id}/{scene_id}")
        sha_key = path_key.replace("_path", "_sha256")
        verify_file(actual, record.get(sha_key, ""), f"{method_id}/{scene_id} {path_key}")
    raw_path = expected_paths["raw_path"].resolve()
    run_start_path = expected_paths["run_start_path"].resolve()
    status_path = expected_paths["run_status_path"].resolve()
    status = load_json(status_path)
    require(status.get("schema") == "TEST48_RUN_STATUS_V1"
            and status.get("status") == "RUN_COMPLETE_RAW_PENDING_PARENT_AUDIT"
            and status.get("method_id") == method_id and status.get("alias") == alias
            and status.get("scene_id") == scene_id,
            f"Run status schema/status/identity invalid for {method_id}/{scene_id}")
    require(status.get("plant_calls") == 1 and status.get("training_steps") == 0
            and status.get("optimizer_steps") == 0 and status.get("TEST_accessed") is True
            and status.get("log_status") == "STABLE" and status.get("last_transition") == 20_000
            and status.get("transition_count") == 20_000 and status.get("state_sample_count") == 20_001,
            f"Run status incomplete or unsafe for {method_id}/{scene_id}")
    for key, expected in (("raw_path", raw_path), ("run_start_path", run_start_path),
                          ("attempt_started_marker_path", expected_paths["attempt_started_marker_path"].resolve()),
                          ("first_plant_step_marker_path", expected_paths["first_plant_step_marker_path"].resolve())):
        require(Path(status.get(key, "")).resolve() == expected,
                f"Run status {key} mismatch for {method_id}/{scene_id}")
    require(status.get("raw_sha256", "").lower() == record.get("raw_sha256", "").lower()
            and status.get("run_start_sha256", "").lower() == record.get("run_start_sha256", "").lower()
            and status.get("attempt_started_marker_sha256", "").lower() == record.get("attempt_started_marker_sha256", "").lower()
            and status.get("first_plant_step_marker_sha256", "").lower() == record.get("first_plant_step_marker_sha256", "").lower(),
            f"Status/body SHA bindings differ for {method_id}/{scene_id}")
    require(not (attempt / "FAILURE_NO_RETRY_v1.json").exists(), f"Failure marker exists for {method_id}/{scene_id}")
    return raw_path, run_start_path, status


def scene_ids_index(scene_id: str) -> int:
    # Filled for each method immediately before record verification.
    return _SCENE_INDEX[scene_id]


_SCENE_INDEX: dict[str, int] = {}


def score_one(raw_path: Path, scene_id: str, method_id: str, item_sha: str, scorer, c5_review) -> tuple[dict, dict, dict]:
    item = {"scene_id": scene_id, "method": method_id, "path": str(raw_path), "sha256": item_sha}
    metrics = scorer.score(item)
    actuator = audit_actuators(raw_path)
    with h5py.File(raw_path, "r") as file:
        log = file["log"]
        transition = get_log_array(log, "transition_time").reshape(-1)
        timing = get_log_array(log, "controller_call_time_s").reshape(-1)
        timing_fields = timing_summary(transition, timing)
    readiness = native_readiness(raw_path, method_id, c5_review)
    row = {**metrics, **timing_fields,
           "status": "STABLE", "safety_stop": False, "safety_stop_reason": "",
           "complete": True, "actuator_finite_complete": True}
    require(row["scene_id"] == scene_id and row["method"] == method_id, "Scorer returned a different row identity")
    require(row["sha256"].lower() == item_sha.lower(), "Scorer returned a different raw SHA")
    require(actuator["all_required_channels_finite"], "Actuator channel audit failed")
    return row, actuator, readiness


def json_safe(value):
    if isinstance(value, np.ndarray):
        return json_safe(value.tolist())
    if isinstance(value, np.generic):
        return json_safe(value.item())
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, float):
        require(math.isfinite(value), "Refusing to serialize a non-finite value")
    return value


def self_check() -> dict[str, Any]:
    t = np.array([0.319, 0.320, 0.321, 0.322], dtype=float)
    calls = np.array([0.0010, 0.0011, 0.0020, 0.0005], dtype=float)
    summary = summarize_timing_values(t, calls)
    assert summary["controller_ready_calls"] == 3
    assert summary["controller_nonready_calls"] == 1
    assert summary["controller_nonready_over_1ms_fraction"] == 0.0
    assert abs(summary["controller_ready_over_1ms_fraction"] - (2 / 3)) < 1e-12
    struct_check = struct_column_self_check()
    return {
        "schema": "DEV_OR_SYNTHETIC_SELF_CHECK_V1",
        "status": "DEV_OR_SYNTHETIC_SELF_CHECK",
        "TEST_accessed": False,
        "synthetic_only": True,
        "checks": {"ready_cutoff": "t>=0.320 s", "ready_calls_in_synthetic_check": 3,
                    "nonready_calls_in_synthetic_check": 1, "all_call_window_retained": True,
                    "overall_over1ms_definition": "strictly greater than 0.001 s",
                    "struct_column_self_check": struct_check},
        "note": "Only small in-memory numeric vectors and non-TEST synthetic struct columns were used; no TEST IDs, files, MAT values, or TEST-shaped rows were read or fabricated.",
    }


def run_review(output_path: Path) -> dict:
    require(not output_path.exists(), f"Refusing to overwrite existing output: {output_path}")
    contract = load_json(CONTRACT)
    manifest = load_json(SOURCE_MANIFEST)
    contract_sha = sha256_file(CONTRACT)
    manifest_sha = sha256_file(SOURCE_MANIFEST)
    # Reject a bad/missing process receipt before any MAT file or score data is opened.
    preflight_methods = manifest.get("methods")
    require(isinstance(preflight_methods, list) and len(preflight_methods) == 6
            and tuple(row.get("method_id") for row in preflight_methods) == EXPECTED_METHODS,
            "Cannot establish the frozen six-method order for the OS preflight")
    preflight_receipts = []
    for method in preflight_methods:
        alias = method.get("alias")
        require(isinstance(alias, str) and re.fullmatch(r"[A-Za-z0-9_-]+", alias) is not None,
                f"Unsafe/missing method alias in OS preflight for {method.get('method_id')}")
        preflight_receipts.append(verify_os_receipt(method["method_id"], alias, manifest_sha, contract_sha))
    receipt_times = validate_receipt_sequence(preflight_receipts)
    scorer, c5_review, ablation, decoder, helper_hashes = verify_helpers()
    source_bindings = verify_manifest_sources(manifest, ROOT)
    require(manifest.get("taskbook_sha256", "").lower() == "e0b58545fda8d779f2672afa50de976596ac510f82f6aa83493ed7583216130b"
            and manifest.get("code_only_release_sha256", "").lower() == "75f32b259ab3fe901b52ac1f4162f0ea04ee3bb1145c9b958fb5e311a24f1b58",
            "Run contract taskbook/code-only release binding changed")
    index, freeze, release, bound_files, scene_ids, scene_digests = verify_input_package(contract, manifest, manifest_sha)
    source_bindings["method_source_manifest_sha256"] = manifest_sha
    source_bindings["source_manifest_path"] = str(SOURCE_MANIFEST.resolve())
    scene_packs, snapshots, model_summary, c5_w0_hashes = verify_scene_and_snapshots(index, scene_ids, scene_digests, c5_review, decoder)
    _SCENE_INDEX.clear()
    _SCENE_INDEX.update({scene_id: index for index, scene_id in enumerate(scene_ids, start=1)})
    method_by_id = {method["method_id"]: method for method in manifest["methods"]}
    release_sha = sha256_file(LOCKED_RELEASE)
    index_sha = sha256_file(INPUT_INDEX)
    shared_sha = sha256_file(SHARED_SCENES)
    cfg_sha = sha256_file(CFG_OPTS)
    method_rows = []
    os_receipts = preflight_receipts
    rows = []
    event_audits = []
    actuator_summary = []
    initial_weight_audits = []
    native_by_method = {}
    physical_by_scene = {scene_id: [] for scene_id in scene_ids}
    for method_index, method_id in enumerate(EXPECTED_METHODS, start=1):
        method = method_by_id[method_id]
        alias = str(method["alias"])
        require(re.fullmatch(r"[A-Za-z0-9_-]+", alias) is not None, f"Unsafe method alias: {alias}")
        receipt = os_receipts[method_index - 1]
        batch, body, records = verify_batch_body(method_id, alias, method_index, scene_ids, manifest_sha,
                                                  index_sha, shared_sha, cfg_sha, release_sha)
        snapshot = snapshots[method_index - 1]
        method_native = []
        record_provenance = []
        for scene_index, (scene_id, scene_digest, record) in enumerate(zip(scene_ids, scene_digests, records), start=1):
            raw_path, start_path, run_status = verify_record_files(record, method_id, alias, method_index, scene_id,
                                                                    scene_digest, manifest_sha, index_sha,
                                                                    shared_sha, cfg_sha, release_sha)
            identity, meta, _ = verify_run_identity_and_start(raw_path, start_path, record, method,
                                                              method_index, scene_id, scene_packs[scene_index - 1],
                                                              snapshot, {"source_manifest": manifest_sha,
                                                                         "method_cfg_opts_mat": cfg_sha,
                                                                         "parent_release": release_sha,
                                                                         "input_index": index_sha},
                                                              scene_digest, c5_review, decoder)
            if method_id in CORRECTED_METHODS:
                initial_weight_audits.append({
                    "scene_id": scene_id, "method": method_id,
                    **audit_corrected_initial_weight(raw_path, method_id, snapshot, c5_review),
                })
            record_provenance.append({key: record[key] for key in (
                "batch_index", "scene_id", "raw_path", "raw_sha256", "run_start_path", "run_start_sha256",
                "run_status_path", "run_status_sha256", "attempt_started_marker_path",
                "attempt_started_marker_sha256", "first_plant_step_marker_path",
                "first_plant_step_marker_sha256", "plant_calls", "TEST_accessed")})
            item_sha = str(record["raw_sha256"]).lower()
            scored, actuator, native = score_one(raw_path, scene_id, method_id, item_sha, scorer, c5_review)
            physical_by_scene[scene_id].append(scored["external_identity_sha256"].lower())
            row = {key: scored[key] for key in (
                "scene_id", "method", "path", "sha256", "external_identity_sha256",
                "Q_0_20_m", "Q_0_5_m", "Q_5_20_m",
                "rmse_x_0_20_m", "rmse_y_0_20_m", "rmse_z_0_20_m",
                "rmse_x_0_5_m", "rmse_y_0_5_m", "rmse_z_0_5_m",
                "rmse_x_5_20_m", "rmse_y_5_20_m", "rmse_z_5_20_m",
                "peak_m", "p95_m", "motor_saturated_fraction", "generalized_clipped_fraction",
                "controller_mean_s", "controller_p50_s", "controller_p95_s", "controller_p99_s",
                "controller_max_s", "controller_over_1ms_fraction", "controller_ready_calls",
                "controller_nonready_calls", "controller_ready_mean_s", "controller_ready_p50_s",
                "controller_ready_p95_s", "controller_ready_p99_s", "controller_ready_max_s",
                "controller_ready_over_1ms_fraction", "controller_nonready_mean_s",
                "controller_nonready_p50_s", "controller_nonready_p95_s", "controller_nonready_p99_s",
                "controller_nonready_max_s", "controller_nonready_over_1ms_fraction",
            )}
            row.update(status="STABLE", safety_stop=False, safety_stop_reason="", complete=True,
                       actuator_finite_complete=True)
            rows.append(row)
            actuator_summary.append({"scene_id": scene_id, "method": method_id, **actuator})
            method_native.append({"scene_id": scene_id, **native})
            if method_id in C5_METHODS:
                cfg = snapshot["cfg"]
                if method_id == "C5_M110":
                    event_result = c5_review.event_audit(raw_path, cfg, expected_w0=get_w0(snapshot["opts"], c5_review, method_id),
                                                         expected_w0_sha256=c5_w0_hashes[method_id])
                elif method_id in ABLATED_METHODS:
                    event_result = ablation.audit_events(raw_path, cfg, method_id,
                                                         get_w0(snapshot["opts"], c5_review, method_id),
                                                         c5_w0_hashes[method_id])
                else:
                    raise ValueError(f"No frozen C5 event auditor for {method_id}")
                require(event_result.get("event_count") == 1_968 and event_result.get("log_status") == "STABLE",
                        f"C5 event audit incomplete for {method_id}/{scene_id}")
                event_result.pop("initial_weight", None)
                event_audits.append({"scene_id": scene_id, "method": method_id, **json_safe(event_result)})
        require(len(method_native) == 48, f"Native-readiness scan incomplete for {method_id}")
        native_by_method[method_id] = summarize_native(method_native)
        method_rows.append({
            "method_id": method_id, "alias": alias, "method_block_order": method_index,
            "natural_os_exit_receipt": receipt,
            "batch_path": str((TASK / "runs" / alias / "METHOD_BATCH_STATUS_v1.json").resolve()),
            "batch_sha256": sha256_file(TASK / "runs" / alias / "METHOD_BATCH_STATUS_v1.json"),
            "body_path": str((TASK / "runs" / alias / "METHOD_BODY_COMPLETE_v1.json").resolve()),
            "body_sha256": sha256_file(TASK / "runs" / alias / "METHOD_BODY_COMPLETE_v1.json"),
            "machine_info": batch.get("machine_info"),
            "thread_argument": batch.get("thread_argument"),
            "controller_timer_boundary": batch.get("controller_timer_boundary"),
            "runtime_tree_sha256": batch.get("runtime_tree_sha256", ""),
            "scene_records": 48,
            "plant_calls": 48,
            "records": record_provenance,
            "native_readiness": native_by_method[method_id],
            "model_identity": model_summary[method_id],
        })
    require(len(rows) == 288 and len({(row["scene_id"], row["method"]) for row in rows}) == 288,
            "Final result does not contain 288 unique scene/method score rows")
    require(all(len(hashes) == 6 for hashes in physical_by_scene.values()), "A scene lacks six paired physical identity rows")
    require(all(len(set(hashes)) == 1 for hashes in physical_by_scene.values()),
            "Raw physical inputs/reference identity differs across methods within a scene")
    require(len(event_audits) == 144 and sum(row["event_count"] for row in event_audits) == 144 * 1_968,
            "C5 plus two ablations did not independently audit 1968 events on every flight")
    require(len(initial_weight_audits) == 96
            and all(row["scene_method_status"] == "PASS_EXACT_INITIAL_WEIGHT_MATCH"
                    and row["exact_elementwise_match"] is True for row in initial_weight_audits),
            "Corrected DSSM/KAN raw initial weights did not match their frozen 33x3 W0 on all 96 flights")
    require(sum(row["plant_calls"] for row in method_rows) == 288 and len(os_receipts) == 6
            and all(row["natural_os_exit_receipt"]["matlab_os_exit_code"] == 0 for row in method_rows),
            "Six natural OS0 method blocks/288 completed calls are not proven")
    require(all(row["status"] == "STABLE" and row["safety_stop"] is False
                and row["complete"] is True and row["actuator_finite_complete"] is True for row in rows),
            "A score row failed explicit safety/completeness status")
    result = {
        "schema": "TEST48_RAW_IDENTITIES_PHYSICS_ALL_METHODS_V1",
        "status": "PASS_TEST48_RAW_IDENTITIES_PHYSICS_ALL_METHODS",
        "TEST_accessed": True,
        "plant_calls": 288,
        "training_steps": 0,
        "optimizer_steps": 0,
        "scene_count": 48,
        "method_count": 6,
        "rows": rows,
        "methods_order": list(EXPECTED_METHODS),
        "scene_ids": scene_ids,
        "provenance": {
            "frozen_helpers": helper_hashes,
            "bound_files": bound_files,
            "source_manifest": source_bindings,
            "method_blocks": method_rows,
            "common_scene_set_sha256": index["scene_set_sha256"],
            "external_identity_hashes_match_by_scene_across_all_methods": True,
        },
        "event_audit": {
            "method_scope": sorted(C5_METHODS),
            "audited_flights": len(event_audits),
            "events_per_flight": 1_968,
            "event_count_total": 144 * 1_968,
            "rows": event_audits,
        },
        "learned_initial_weight_integrity": {
            "raw_field": "log.stage1_position_weight_initial",
            "corrected_method_ids": sorted(CORRECTED_METHODS),
            "checked_corrected_flights": len(initial_weight_audits),
            "corrected_method_rows": initial_weight_audits,
            "C5_initial_weight_check": "Covered by the independent C5/ablation event auditors on all 144 flights.",
            "B_initial_weight_check": "NOT_APPLICABLE_NO_LEARNED_HEAD",
        },
        "actuator_integrity": {
            "all_288_rows_finite_and_complete": True,
            "required_channels": list(REQUIRED_ACTUATOR_FIELDS),
            "flight_channels": actuator_summary,
        },
        "native_readiness_telemetry": {
            "definition": "Only actual stage1_position_event_inference_valid markers, stage1_position_inference_time_s valid-event timing, and selected forward_debug history_ready/model_call/timing arrays are summarized. Event-valid is not continuous readiness; exact enabled=false,count=0 debug structs are recorded as disabled; B with no positive native event/head is native_not_applicable and no head is synthesized.",
            "by_method": native_by_method,
        },
        "timing_qualification": {
            **TIE_AND_TIMING_SCOPE,
            "measurement_boundary": "Frozen controller_call_time_s ends before allocator, Plant and MAT save.",
            "method_block_order": list(EXPECTED_METHODS),
            "machine_info_and_method_process_receipts_retained": True,
            "thread_argument_interpretation": "-singleCompThread sets MATLAB numerical-computation thread behavior; runtime worker threads can remain and the root observer records them.",
            "sysnoise": "Six method processes ran sequentially while avoiding known heavy system load; timing has no OS-level isolation and includes initial calls/JIT effects.",
            "formal_1khz_loop_claim": False,
            "natural_os_receipt_order_checked_before_mat_or_score_reads": True,
        },
        "score_source": {"path": str(SCORER.resolve()), "sha256": EXPECTED_SHA256["scorer"]},
        "paper_gate_or_goal_decision": "NOT_AUTOMATED_BY_RAW_AUDIT",
    }
    return json_safe(result)


def summarize_native(records: list[dict]) -> dict:
    all_sources = {}
    for row in records:
        for source, detail in row["sources"].items():
            entry = all_sources.setdefault(source, {"present_scene_count": 0, "per_scene": []})
            entry["present_scene_count"] += 1
            entry["per_scene"].append({"scene_id": row["scene_id"], **detail})
    return {
        "scene_count": len(records),
        "scenes_with_any_native_readiness_telemetry": sum(bool(row["available"]) for row in records),
        "native_record_available": bool(all_sources),
        "status_counts": {status: sum(row.get("status") == status for row in records)
                          for status in sorted({row.get("status", "unknown") for row in records})},
        "sources": all_sources,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-json", type=Path, required=True,
                        help="New raw-audit output path; existing files are refused")
    args = parser.parse_args()
    output_path = args.output_json if args.output_json.is_absolute() else ROOT / args.output_json
    output_path = output_path.resolve()
    require(output_path.parent == OUTPUT_DIR.resolve(), f"Output must stay inside {OUTPUT_DIR}")
    require(not output_path.exists(), f"Refusing to overwrite existing output: {output_path}")
    try:
        result = run_review(output_path)
        serialized = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        with output_path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(serialized)
    except (OSError, KeyError, TypeError, ValueError, AssertionError) as error:
        raise SystemExit(f"TEST48 raw review failed; no PASS output written: {error}") from error
    print(json.dumps({"status": result["status"], "rows": len(result["rows"]),
                      "event_audited_flights": result["event_audit"]["audited_flights"],
                      "output_json": str(output_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
