#!/usr/bin/env python3
"""Review the mixed v3-B48 / v9-five-method TEST48 raw package.

Import is inert. The real reviewer CLI is intended for use only after every
formal method process has a natural OS0 receipt. --self-check uses synthetic
in-memory metadata and the frozen v1 reader's small-vector checks only.
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
V1_READER = ROOT / "reports" / "paper_continuation_20261023" / "test_raw_review_v1" / "audit_test48_raw_v1.py"
V1_READER_SHA256 = "31229d1b9d137ec2847b25b7a32c3d0183e517fac963dc2ed01de74bcde11d45"
TASKBOOK = ROOT / "reports" / "paper_continuation_20261023" / "TEST_STAGE_PATH_CONTRACT_REPAIR_TASKBOOK_v2_ZH.md"
TASKBOOK_SHA256 = "3d93cd4419cc86d8e1fa7e9e64b34399320f4a8a46726a2423e403e4093c0d9f"
DEPENDENCY_REVIEW = ROOT / "reports" / "paper_continuation_20261023" / "test_dependency_review_v1" / "DEPENDENCY_REVIEW_v1.json"
DEPENDENCY_REVIEW_SHA256 = "dc9d9ab261bc13ee08fd733b961acf56396e1da8eb945fc15455a1b2b2d3d4b7"

V3_TASK = ROOT / "experiments" / "c5_test48_v3"
V3_REPORT = ROOT / "reports" / "paper_continuation_20261023" / "test_entry_v3"
V9_TASK = ROOT / "experiments" / "c5_test48_v9"
V9_REPORT = ROOT / "reports" / "paper_continuation_20261023" / "test_entry_v9"
V9_OUTPUT = V9_TASK / "runs"
V9_ENTRY = V9_TASK / "test48_entry_v4.m"
V9_LAUNCHER = V9_TASK / "RUN_TEST48_EXACT_v1.ps1"
V9_CONTRACT = V9_TASK / "TEST48_RUN_CONTRACT_v4.json"
V9_MANIFEST = V9_REPORT / "TEST_METHOD_SOURCE_MANIFEST_v4.json"
V9_RUN_RELEASE = V9_REPORT / "RUN_UNSTARTED_TEST_PARENT_RELEASE_v1.json"
V9_RUN_RELEASE_SHA256 = "59fae7920eb498d06f29c5c8d7eb1191843de79a640b6ec46e5c40fd32b1d06a"
# Filled from the final root-reviewed v9 source bundle before the reader is frozen.
V9_ENTRY_SHA256 = "b9906578088319c8108a360c140c163b8af9080f311613489a20a48a8f609fd1"
V9_LAUNCHER_SHA256 = "7034e2e6d5459fb33e9a66dcc2ad32c80677b7850a1eacd510b6d1648d631c8c"
V9_CONTRACT_SHA256 = "d4132d2a00693bde5ca234e4ac7cf07ba2695971a086b2275539842d7f5c3210"
V9_MANIFEST_SHA256 = "f8998debf70835d0fb4dcab8c9d8fe77ef1702be80559622badd3dafa1b77d80"
V9_CODE_ONLY_RELEASE = ROOT / "reports" / "paper_continuation_20261023" / "TEST_STAGE_PATH_CONTRACT_REPAIR_CODE_ONLY_RELEASE_v2.json"
V9_CODE_ONLY_RELEASE_SHA256 = "9f4876e732d00415b8be5a14383e36f74dab961f1aabd7a9571377ace9bd7732"

# Failed v4 preparation and its diagnostic are preserved as separate history;
# neither belongs to the v9 success batch or the 288 scored rows.
V4_HISTORY_TASK = ROOT / "experiments" / "c5_test48_v4"
V4_HISTORY_REPORT = ROOT / "reports" / "paper_continuation_20261023" / "test_entry_v4"
V4_HISTORY_ENTRY_SHA256 = "b87848d474c2f30d7774a9833a61d54d4629595ae445e556010abef2995541f6"
V4_HISTORY_LAUNCHER_SHA256 = "72cf5d66241f34b1e0213145f922c30cf40896328b15807a7d521d67658874f3"
V4_HISTORY_CONTRACT_SHA256 = "d2453edf4da67dda2e0e481fb56f5eb168cf1928188fe5f35b58d1dca4758b62"
V4_HISTORY_MANIFEST_SHA256 = "404e713a875d0b9069ea38f3f441c25bd33db7d3457f1ac974d5977bd808142b"
V4_FAILURE_RESULT_SHA256 = "dced4024a33851389082681b4226077738244c9f4384a4a0eca4c1c91e183346"
V4_FAILURE_OS_SHA256 = "cdcf7e307d1855d478d594728d62d3ce39ca8611f9a7168f4f791c66b241b599"
V4_FAILURE_RELEASE_SHA256 = "da71a9b64ee8052c1d12e2a212798b1b2c509835e6fd29b20828a30a39363a5d"
PATH_DIAGNOSTIC_REPORT = ROOT / "reports" / "paper_continuation_20261023" / "test_path_diagnostic_v1"
PATH_DIAGNOSTIC_RESULT_SHA256 = "eaae3bf66870116413e3efdd8f5f659612372ad9035ccae8619c98d121879139"
PATH_DIAGNOSTIC_OS_SHA256 = "43bed0c650ce2f6c99c4251ca40759d19bf92393abc3dac7d76dd773c403ae36"
PATH_DIAGNOSTIC_REVIEW_SHA256 = "8edd898f958b475b2af8bd110fbfecd38dcb17784e2964e113d443bef9ab9643"

EXPECTED_METHODS = (
    "B_TRACEABLE",
    "CORRECTED_DSSM14_G12_R32",
    "CORRECTED_KAN14_G12_R32",
    "C5_M110",
    "C5_FREEZE_TRAINED_W0",
    "C5_NO_DELAYED_PREDICTION",
)
V4_METHODS = EXPECTED_METHODS[1:]
V3_MANIFEST_SHA256 = "b9ed7fef91bf61b03e4f51d8a9cbaf7233484ac6faa4750827aefb7e247f9633"
V3_CONTRACT_SHA256 = "4ef328f0ffc1997dbfd64c86d0cb804f7fd054064a7283979f0cff466712f9ef"
V3_B_OS_RECEIPT_SHA256 = "32a86e4a16574f7eef4d447ef8bf0ed7bac78ebb15e7fe03ef9d1814183cf506"
V3_DSSM_FAILURE_OS_RECEIPT_SHA256 = "b6bee28f012250f21020757984ae2cda601ce56f37161eefad820b6bf3058f1a"
FILTER_HELPER_SHA256 = "b4ae22db5bd444a162d0cd01a3a59a589f2e37077b089bb33693401b660228d0"
EXPECTED_FROZEN_INPUTS = {
    "shared_scenes_sha256": "da207d858e8918f27c19fef30d4ad57206e20f1971e743515043d1a88a995d5c",
    "cfg_opts_sha256": "389fdfabd9fbd350d3bdd6df934cfe718eb7208bef2b7b4af02f1192cbb1b9e4",
    "index_sha256": "90940a818d293c66c34423a63088113557518c5ecdfd528a3f37867f391eef68",
    "freeze_result_sha256": "7b6edd167dff5e7ee05cc29814ff007dbd5e4cacb6fe3a8b23668fef57f6c1e9",
    "freeze_os_sha256": "5a75bf1317e2a4888e853a31105859f08b6e68024d9fc0fa5fde984bf5cce544",
    "scene_set_sha256": "90e59e5461650cf718a2eeb48b68a4f3c38e3e5b4046ca721116d143b731769e",
}
OLD_DSSM_FAILURE_SCENE = "DL1018_TEST_T1_C00_W11"
OLD_DSSM_FAILURE_RELATIVE = Path("DSSM") / OLD_DSSM_FAILURE_SCENE / "attempt_01"
OLD_DSSM_FAILURE_CAUSE = "position_filter_realization_pcf_step_v3_5"
V4_METHOD_PHASE = "RUN_UNSTARTED_TEST_PARENT_APPROVED"
READY_CUTOFF_S = 0.320


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


def module_at(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, f"Cannot import pinned module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_v1():
    require(sha256_file(V1_READER).lower() == V1_READER_SHA256, "Frozen v1 raw reviewer SHA changed")
    return module_at(V1_READER, "frozen_test48_raw_review_v1")


def canonical_path(value: str | Path, v1) -> Path:
    return v1.resolve_repo_path(value)


def require_sha_binding(owner: dict, field: str, path: Path, label: str) -> str:
    require(field in owner and isinstance(owner[field], str) and re.fullmatch(r"[0-9a-fA-F]{64}", owner[field]) is not None,
            f"Missing/invalid {label} SHA binding field {field}")
    actual = sha256_file(path.resolve(strict=True))
    require(actual.lower() == owner[field].lower(), f"{label} SHA does not match release field {field}")
    return actual


def ref_key(ref: dict, v1) -> tuple[str, str, str]:
    require(isinstance(ref, dict) and isinstance(ref.get("path"), str) and isinstance(ref.get("sha256"), str),
            "Malformed source/model reference")
    path = canonical_path(ref["path"], v1)
    require(path.is_file(), f"Missing locked source/model file: {path}")
    actual = sha256_file(path)
    require(actual.lower() == ref["sha256"].lower(), f"Locked source/model SHA changed: {path}")
    return str(path).casefold(), actual.lower(), str(ref.get("role", ""))


def refs_map(refs: list[dict], v1, label: str) -> dict[str, tuple[tuple[str, str], ...]]:
    require(isinstance(refs, list), f"{label} must be a list")
    result: dict[str, list[tuple[str, str]]] = {}
    for ref in refs:
        path, sha, role = ref_key(ref, v1)
        result.setdefault(path, []).append((sha, role))
    for path, items in result.items():
        require(len({sha for sha, _ in items}) == 1, f"Conflicting hashes for one source path in {label}: {path}")
    return {path: tuple(sorted(items)) for path, items in result.items()}


def assert_only_filter_helper_added(old_refs: list[dict], new_refs: list[dict], v1, label: str) -> None:
    old = refs_map(old_refs, v1, f"v3 {label} sources")
    new = refs_map(new_refs, v1, f"v4 {label} sources")
    helper_path = str(canonical_path("matlab/models/position_filter_realization_pcf_step_v3_5.m", v1)).casefold()
    require(helper_path in new, f"v4 {label} lacks the active PCF filter helper")
    require(len(new[helper_path]) == 1 and new[helper_path][0][0] == FILTER_HELPER_SHA256,
            f"v4 {label} filter helper SHA/uniqueness changed")
    expected = dict(old)
    if helper_path in expected:
        require(expected[helper_path] == new[helper_path], f"Existing helper reference changed in {label}")
    else:
        expected[helper_path] = new[helper_path]
    require(expected == new, f"v4 {label} source lineage is not exactly v3 plus the locked PCF filter helper")


def validate_method_lineage(v3_manifest: dict, v4_manifest: dict, v1) -> dict[str, Any]:
    old_methods = v3_manifest.get("methods")
    new_methods = v4_manifest.get("methods")
    require(isinstance(old_methods, list) and isinstance(new_methods, list)
            and len(old_methods) == len(new_methods) == 6, "v3/v4 method manifests must each have six rows")
    require(tuple(row.get("method_id") for row in old_methods) == EXPECTED_METHODS
            and tuple(row.get("method_id") for row in new_methods) == EXPECTED_METHODS,
            "v3/v4 method order or identity changed")
    source_refs_by_method = {}
    method_ref_count = 0
    model_ref_count = 0
    for i, (old, new) in enumerate(zip(old_methods, new_methods), start=1):
        mid = EXPECTED_METHODS[i - 1]
        require(old.get("alias") == new.get("alias") and int(new.get("order", -1)) == i
                and new.get("v3_method_id") == mid and int(new.get("v3_order", -1)) == i,
                f"v3/v4 method identity or order changed: {mid}")
        # Deployed contracts/models stay frozen; only the two historical references were corrected.
        for key in ("run_contract_path", "run_contract_sha256"):
            require(str(old.get(key, "")) == str(new.get(key, "")), f"v3/v9 {mid} changed {key}")
        corrected_shas = {
            "CORRECTED_DSSM14_G12_R32": ("1b6417b4369f5b5618d1ee81ac8595de1bb6d607e0fdd04ad2913748f6986cde",
                                       "3b798c8624cc10cc1ddf3b3b1000099bc62e42e8430af92a42b0fa467385743e"),
            "CORRECTED_KAN14_G12_R32": ("b10d1de1a0a0307659c3e1bb0f608aa8a4e0da109991493dbc327104404bbda9",
                                      "0012bf34074ac2f034517fbb65237bd667b31e7e539987601e4d16e0b26c9525"),
        }
        if mid in corrected_shas:
            superseded = [row for row in v4_manifest.get("v6_incorrect_dk_reference_bindings", [])
                          if row.get("method_id") == mid]
            corrected = [row for row in v4_manifest.get("engineering_dev2", []) if row.get("method_id") == mid]
            require(len(superseded) == len(corrected) == 1, f"Missing exact corrected reference bridge: {mid}")
            before, after = corrected_shas[mid]
            require(old.get("cfg_opts_snapshot_sha256", "").lower() == before
                    and superseded[0].get("cfg_opts_snapshot_sha256", "").lower() == before
                    and canonical_path(old["cfg_opts_snapshot_path"], v1)
                        == canonical_path(superseded[0]["cfg_opts_snapshot_path"], v1),
                    f"Superseded historical reference identity changed: {mid}")
            require(new.get("cfg_opts_snapshot_sha256", "").lower() == after
                    and corrected[0].get("run_start_sha256", "").lower() == after
                    and canonical_path(new["cfg_opts_snapshot_path"], v1)
                        == canonical_path(corrected[0]["run_start_path"], v1),
                    f"Corrected historical reference identity changed: {mid}")
        else:
            for key in ("cfg_opts_snapshot_path", "cfg_opts_snapshot_sha256"):
                require(str(old.get(key, "")) == str(new.get(key, "")), f"v3/v9 {mid} changed {key}")
        require(refs_map(old.get("model_refs", []), v1, f"v3 {mid} model refs")
                == refs_map(new.get("model_refs", []), v1, f"v4 {mid} model refs"),
                f"v3/v4 {mid} model or normalizer identity changed")
        if mid in {"CORRECTED_DSSM14_G12_R32", "CORRECTED_KAN14_G12_R32"}:
            assert_only_filter_helper_added(old.get("source_refs", []), new.get("source_refs", []), v1, mid)
        else:
            require(refs_map(old.get("source_refs", []), v1, f"v3 {mid} sources")
                    == refs_map(new.get("source_refs", []), v1, f"v4 {mid} sources"),
                    f"v4 changed a non-D/K method's frozen source set: {mid}")
        if mid == "B_TRACEABLE":
            reuse = new.get("v3_reuse_binding")
            require(isinstance(reuse, dict) and reuse.get("method_id") == mid
                    and reuse.get("action") == "reuse all 48 v3 raw records; never rerun B"
                    and int(reuse.get("scene_count", 0)) == 48 and int(reuse.get("plant_calls", 0)) == 48,
                    "v4 does not bind exact B48 reuse/no-rerun scope")
            require(canonical_path(reuse.get("run_root", ""), v1)
                    == V3_TASK / "runs" / str(old.get("alias")), "v4 B48 reuse route differs from frozen v3 path")
        source_refs_by_method[mid] = new.get("source_refs", [])
        method_ref_count += len(new.get("source_refs", []))
        model_ref_count += len(new.get("model_refs", []))

    require(refs_map(v3_manifest.get("shared_source_refs", []), v1, "v3 shared sources")
            == refs_map(v4_manifest.get("shared_source_refs", []), v1, "v4 shared sources"),
            "v4 changed shared v3 source references")
    global_refs = v4_manifest.get("global_platform_refs")
    require(isinstance(global_refs, list) and len(global_refs) == 32,
            "v4 global platform lock must retain all 32 explicit references")
    global_map = refs_map(global_refs, v1, "v4 global platform refs")
    canonical = "".join(f"{ref['path']}:{ref['sha256']}\n" for ref in global_refs)
    global_sha = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    require(global_sha.lower() == str(v4_manifest.get("global_platform_lock_sha256", "")).lower(),
            "v4 canonical global platform lock SHA is invalid")
    b_source_map = refs_map(new_methods[0].get("source_refs", []), v1, "v4 B sources")
    require(all(path in b_source_map and all(sha in {item[0] for item in b_source_map[path]}
                                               for sha, _ in refs) for path, refs in global_map.items()),
            "Global frozen platform references are not a subset of B's source lock")
    for mid in V4_METHODS[:2]:
        refs = source_refs_by_method[mid]
        pcf = [ref for ref in refs if Path(str(ref.get("path", ""))).name.casefold()
               == "position_filter_realization_pcf_step_v3_5.m"]
        require(len(pcf) == 1 and pcf[0].get("sha256", "").lower() == FILTER_HELPER_SHA256,
                f"Active D/K filter helper identity is not uniquely locked for {mid}")
    return {
        "methods": list(EXPECTED_METHODS),
        "method_source_reference_count": method_ref_count,
        "model_reference_count": model_ref_count,
        "shared_source_reference_count": len(v4_manifest.get("shared_source_refs", [])),
        "method_and_shared_source_reference_count": method_ref_count + len(v4_manifest.get("shared_source_refs", [])),
        "global_platform_reference_count": len(global_refs),
        "global_platform_lock_sha256": global_sha,
        "D_K_source_change": "Each corrected method adds exactly the locked PCF helper. Only the two historical reference paths/SHAs are corrected to r002/r001; frozen TEST cfgpack bytes and all model/source identities stay unchanged.",
        "B_behavior": "Reuse all 48 v3 raw records; no B rerun.",
    }


def verify_v4_code_and_manifest(v1) -> tuple[dict, dict, dict, dict]:
    require(sha256_file(TASKBOOK).lower() == TASKBOOK_SHA256, "v9 taskbook SHA changed")
    require(sha256_file(DEPENDENCY_REVIEW).lower() == DEPENDENCY_REVIEW_SHA256,
            "Independent dependency review SHA changed")
    require(sha256_file(V9_ENTRY).lower() == V9_ENTRY_SHA256
            and sha256_file(V9_LAUNCHER).lower() == V9_LAUNCHER_SHA256
            and sha256_file(V9_CONTRACT).lower() == V9_CONTRACT_SHA256
            and sha256_file(V9_MANIFEST).lower() == V9_MANIFEST_SHA256,
            "Final root-reviewed v9 source/contract/manifest SHA lock changed")
    v4_contract = load_json(V9_CONTRACT)
    v4_manifest = load_json(V9_MANIFEST)
    v3_manifest = load_json(v1.SOURCE_MANIFEST)
    v3_contract = load_json(v1.CONTRACT)
    require(v4_contract.get("schema") == "TEST48_RUN_CONTRACT_V4"
            and v4_contract.get("state") == "CODE_ONLY_WAITING_FOR_SEPARATE_STAGE_RELEASES",
            "Unknown/mutated v4 run contract")
    require(v4_manifest.get("schema") == "TEST48_METHOD_SOURCE_MANIFEST_V4"
            and v4_manifest.get("test_accessed") is False and v4_manifest.get("plant_started") is False,
            "v4 source manifest is not a pre-run source lock")
    v3_manifest_sha = sha256_file(v1.SOURCE_MANIFEST)
    v4_manifest_sha = sha256_file(V9_MANIFEST)
    v4_contract_sha = sha256_file(V9_CONTRACT)
    require(v3_manifest_sha.lower() == V3_MANIFEST_SHA256
            and sha256_file(v1.CONTRACT).lower() == V3_CONTRACT_SHA256,
            "Frozen v3 source manifest or contract SHA changed")
    require(v4_contract.get("method_source_manifest_sha256", "").lower() == v4_manifest_sha.lower()
            and v4_manifest.get("v3_source_manifest_sha256", "").lower() == v3_manifest_sha.lower(),
            "v9 contract/manifest no longer bind the exact v3 source identity")
    require(v4_contract.get("v3_source_manifest_sha256", "").lower() == v3_manifest_sha.lower(),
            "v9 contract does not bind the v3 source manifest")
    for owner, key_path, key_sha, path, expected_sha, label in (
        (v4_contract, "taskbook_path", "taskbook_sha256", TASKBOOK, TASKBOOK_SHA256, "v9 taskbook"),
        (v4_contract, "dependency_review_path", "dependency_review_sha256", DEPENDENCY_REVIEW,
         DEPENDENCY_REVIEW_SHA256, "dependency review"),
    ):
        require(canonical_path(owner.get(key_path, ""), v1) == path.resolve(strict=True)
                and owner.get(key_sha, "").lower() == expected_sha.lower(), f"v4 {label} binding changed")
    v3_inputs = v4_manifest.get("v3_frozen_inputs")
    require(isinstance(v3_inputs, dict), "v4 manifest lacks exact v3 frozen-input binding")
    for field, expected in EXPECTED_FROZEN_INPUTS.items():
        require(str(v3_inputs.get(field, "")).lower() == expected.lower(),
                f"v9 source manifest changed frozen-input identity {field}")
    contract_inputs = v4_contract.get("v3_frozen_inputs")
    require(isinstance(contract_inputs, dict), "v9 contract lacks inherited v3 frozen-input binding")
    contract_input_aliases = {
        "shared_scenes_sha256": "shared_scenes_sha256",
        "cfg_opts_sha256": "cfg_opts_sha256",
        "index_sha256": "index_sha256",
        "freeze_result_sha256": "freeze_result_sha256",
        "freeze_os_sha256": "freeze_os_sha256",
        "scene_set_sha256": "scene_set_sha256",
    }
    for key, manifest_field in contract_input_aliases.items():
        require(str(contract_inputs.get(key, "")).lower() == str(v3_inputs.get(manifest_field, "")).lower(),
                f"v9 contract/manifest input binding differs for {key}")
    execution = v4_contract.get("execution", {})
    manifest_execution = v4_manifest.get("v4_execution", {})
    require(execution.get("unstarted_method_ids") == list(V4_METHODS)
            and execution.get("B48_reused") is True
            and int(execution.get("max_unique_plant_calls", -1)) == 240
            and manifest_execution.get("run_unstarted_method_ids") == list(V4_METHODS)
            and manifest_execution.get("B48_reused") is True
            and int(manifest_execution.get("max_unique_plant_calls", -1)) == 240,
            "v9 execution scope must contain only five unstarted methods and reuse B48")
    require(v4_contract.get("method_order") and tuple(row.get("id") for row in v4_contract["method_order"]) == EXPECTED_METHODS,
            "v9 contract method order changed")
    require(tuple(row.get("alias") for row in v4_contract["method_order"])
            == tuple(row.get("alias") for row in v4_manifest["methods"]),
            "v9 contract/manifest method aliases changed")
    lineage = validate_method_lineage(v3_manifest, v4_manifest, v1)
    require(v4_contract.get("global_platform_lock_sha256", "").lower()
            == v4_manifest.get("global_platform_lock_sha256", "").lower()
            and int(v4_contract.get("global_platform_ref_count", -1)) == len(v4_manifest.get("global_platform_refs", [])),
            "v9 contract and manifest global platform lock/count differ")
    # This code-only release grants no runtime permission; separate stage releases bind the final files.
    code_release_path = canonical_path(v4_contract.get("code_only_release_path", ""), v1)
    require(code_release_path == V9_CODE_ONLY_RELEASE.resolve(strict=True),
            "v9 contract points at an unexpected code-only release")
    require_sha_binding(v4_contract, "code_only_release_sha256", code_release_path, "v9 code-only release")
    require(sha256_file(code_release_path).lower() == V9_CODE_ONLY_RELEASE_SHA256,
            "v9 code-only release SHA differs from the approved code-only record")
    code_release = load_json(code_release_path)
    require(code_release.get("schema") == "TEST_STAGE_PATH_CONTRACT_REPAIR_CODE_ONLY_RELEASE_V2"
            and code_release.get("status") == "APPROVED_CODE_ONLY"
            and not any(bool(code_release.get(key, False)) for key in
                        ("MATLAB_authorized", "Plant_authorized", "TEST_generation_authorized", "training_authorized")),
            "v9 code-only parent release contains execution authorization")
    require(code_release.get("taskbook_sha256", "").lower() == TASKBOOK_SHA256,
            "v9 code-only parent does not bind the taskbook")
    require(code_release.get("allowed_write_directories") == [
                "experiments/c5_test48_v9", "reports/paper_continuation_20261023/test_entry_v9"],
            "v9 code-only release write scope differs from the isolated code directories")
    entry_path = canonical_path(v4_contract.get("entry_path", ""), v1)
    require(entry_path == V9_ENTRY.resolve(strict=True), "v9 contract entry path differs from the isolated v9 entry")
    require(v4_contract.get("entry_sha256", "").lower() == V9_ENTRY_SHA256,
            "v9 contract entry SHA does not bind the final pinned entry")
    launcher = resolve_v4_launcher(code_release, v4_manifest, v1, v4_contract)
    require(path_equal(launcher, V9_LAUNCHER.resolve(strict=True)),
            "v9 launcher path differs from the final root-reviewed launcher")
    require(v4_contract.get("launcher_sha256", "").lower() == V9_LAUNCHER_SHA256,
            "v9 contract launcher SHA does not bind the final pinned launcher")
    require(sha256_file(launcher).lower() == V9_LAUNCHER_SHA256,
            "v9 launcher SHA differs from the final root-reviewed launcher")
    require(canonical_path(v4_contract.get("method_source_manifest_path", ""), v1)
            == V9_MANIFEST.resolve(strict=True), "v9 contract points to a different source manifest")
    require(v4_contract.get("method_source_manifest_sha256", "").lower() == V9_MANIFEST_SHA256,
            "v9 contract manifest SHA does not bind the final pinned manifest")
    require(v4_manifest.get("taskbook_sha256", "").lower() == TASKBOOK_SHA256
            and v4_manifest.get("code_only_release_sha256", "").lower() == V9_CODE_ONLY_RELEASE_SHA256,
            "v9 manifest does not bind its taskbook and code-only release")
    # Bind manifest to the contract's approved v3 inputs and exact method rows.
    old_input_index = v1.load_json(v1.INPUT_INDEX)
    require(old_input_index.get("scene_set_sha256", "").lower() == EXPECTED_FROZEN_INPUTS["scene_set_sha256"],
            "v3 scene set index identity changed")
    return v4_contract, v4_manifest, v3_contract, {
        "v3_source_manifest_sha256": v3_manifest_sha,
        "v9_source_manifest_sha256": v4_manifest_sha,
        "v3_run_contract_sha256": sha256_file(v1.CONTRACT),
        "v9_run_contract_sha256": v4_contract_sha,
        "v9_entry_sha256": sha256_file(V9_ENTRY),
        "v9_launcher_path": str(launcher.resolve()),
        "v9_launcher_sha256": sha256_file(launcher),
        "v9_contract_sha256": sha256_file(V9_CONTRACT),
        "lineage": lineage,
        "code_only_release_path": str(code_release_path),
        "code_only_release_sha256": sha256_file(code_release_path),
    }


def resolve_v4_launcher(code_release: dict, manifest: dict, v1, contract: dict | None = None) -> Path:
    candidates = []
    for owner in (code_release, manifest, contract or {}):
        for key in ("launcher_path", "runner_launcher_path"):
            value = owner.get(key)
            if isinstance(value, str) and value:
                candidates.append(canonical_path(value, v1))
    if not candidates:
        candidates = sorted(V9_TASK.glob("*.ps1"))
    unique = {str(path.resolve(strict=True)).casefold(): path.resolve(strict=True) for path in candidates if path.is_file()}
    require(len(unique) == 1, "v4 launcher path must be explicit or resolve to one locked .ps1")
    return next(iter(unique.values()))


def verify_v4_run_release(v4_contract: dict, code_info: dict, v1) -> tuple[dict, dict]:
    require(sha256_file(V9_RUN_RELEASE).lower() == V9_RUN_RELEASE_SHA256,
            "Final v9 formal TEST release SHA changed")
    release = load_json(V9_RUN_RELEASE)
    release_sha = sha256_file(V9_RUN_RELEASE)
    require(release.get("schema") == "TEST48_V4_UNSTARTED_TEST_RELEASE_V1"
            and release.get("status") == "APPROVED_RUN_UNSTARTED_TEST_V4",
            "Missing or invalid root-approved v4 unstarted TEST release")
    for field, expected in (
        ("taskbook_sha256", TASKBOOK_SHA256),
        ("contract_sha256", code_info["v9_run_contract_sha256"]),
        ("method_source_manifest_sha256", code_info["v9_source_manifest_sha256"]),
        ("entry_sha256", code_info["v9_entry_sha256"]),
        ("launcher_sha256", code_info["v9_launcher_sha256"]),
    ):
        require(str(release.get(field, "")).lower() == expected.lower(),
                f"v4 root release does not bind {field}")
    require(release.get("plant_authorized") is True and release.get("scene_generation_authorized") is False
            and release.get("TEST_accessed") is True and release.get("training_authorized") is False
            and release.get("no_retry") is True, "v4 root release flags/scope changed")
    require(int(release.get("scene_count", -1)) == 48 and int(release.get("max_plant_calls", -1)) == 240
            and tuple(release.get("method_ids", [])) == V4_METHODS,
            "v4 root release must authorize only the exact five-method/48-scene block")
    index = v1.load_json(v1.INPUT_INDEX)
    require(release.get("scene_set_sha256", "").lower() == index.get("scene_set_sha256", "").lower(),
            "v4 root release does not bind the exact v3 scene set")
    for field, expected in (
        ("input_index_sha256", EXPECTED_FROZEN_INPUTS["index_sha256"]),
        ("shared_scenes_mat_sha256", EXPECTED_FROZEN_INPUTS["shared_scenes_sha256"]),
        ("method_cfg_opts_sha256", EXPECTED_FROZEN_INPUTS["cfg_opts_sha256"]),
        ("freeze_result_sha256", EXPECTED_FROZEN_INPUTS["freeze_result_sha256"]),
        ("freeze_os_exit_sha256", EXPECTED_FROZEN_INPUTS["freeze_os_sha256"]),
    ):
        require(str(release.get(field, "")).lower() == expected.lower(), f"v4 release changed frozen input binding {field}")
    return release, {"path": str(V9_RUN_RELEASE.resolve()), "sha256": release_sha}


def verify_v3_failure_history(v1) -> dict[str, Any]:
    receipt_path = V3_REPORT / "DSSM_MATLAB_OS_EXIT_v1.json"
    require(sha256_file(receipt_path).lower() == V3_DSSM_FAILURE_OS_RECEIPT_SHA256,
            "The original v3 DSSM OS1 receipt changed; do not rewrite or reinterpret it")
    receipt = v1.load_json(receipt_path)
    require(receipt.get("schema") == "TEST48_MATLAB_OS_EXIT_V1"
            and receipt.get("method_id") == V4_METHODS[0]
            and receipt.get("mode") == "LOCKED_TEST48_PARENT_APPROVED"
            and receipt.get("stage") == "LOCKED_TEST48_PARENT_APPROVED"
            and receipt.get("matlab_os_exit_code") == 1 and receipt.get("natural_wait_used") is True
            and receipt.get("TEST_accessed") is True and receipt.get("plant_authorized") is True
            and receipt.get("source_manifest_sha256", "").lower() == V3_MANIFEST_SHA256
            and receipt.get("contract_sha256", "").lower() == V3_CONTRACT_SHA256,
            "Original v3 DSSM failure receipt identity/status changed")
    for key_path, key_sha in (("stdout_path", "stdout_sha256"), ("stderr_path", "stderr_sha256")):
        v1.verify_file(v1.resolve_repo_path(receipt[key_path]), receipt[key_sha], f"original v3 DSSM {key_path}")
    attempt = V3_TASK / "runs" / OLD_DSSM_FAILURE_RELATIVE
    failure = v1.load_json(attempt / "FAILURE_NO_RETRY_v1.json")
    status = v1.load_json(attempt / "run_status.json")
    batch = v1.load_json(attempt.parent.parent / "METHOD_BATCH_STATUS_v1.json")
    require(failure.get("status") == "FAILED_NO_RETRY" and failure.get("method_id") == V4_METHODS[0]
            and failure.get("scene_id") == OLD_DSSM_FAILURE_SCENE
            and failure.get("identifier") == "MATLAB:UndefinedFunction"
            and OLD_DSSM_FAILURE_CAUSE in str(failure.get("message", ""))
            and failure.get("plant_start_confirmed") is False and failure.get("partial_raw_preserved") is False
            and failure.get("partial_raw_sha256") == "", "Original v3 DSSM first-scene failure record changed")
    require(status.get("status") == "FAILED_NO_RETRY" and status.get("plant_calls") == 0
            and status.get("method_source_manifest_sha256", "").lower() == V3_MANIFEST_SHA256
            and status.get("input_index_sha256", "").lower() == EXPECTED_FROZEN_INPUTS["index_sha256"],
            "Original v3 DSSM failure status is inconsistent")
    require(batch.get("status") == "FAILED_STOP_NO_RETRY" and batch.get("completed_scenes") == 0
            and batch.get("plant_calls") == 0 and batch.get("records") == [],
            "Original v3 DSSM batch failure must remain an OS1/0-Plant block")
    raw_path = attempt / "raw_run.mat"
    first_plant_path = attempt / "first_plant_step.marker"
    require(not raw_path.exists() and not first_plant_path.exists(),
            "Original v3 DSSM failure unexpectedly has raw output or a first-Plant marker")
    return {
        "receipt_path": str(receipt_path.resolve()), "receipt_sha256": sha256_file(receipt_path),
        "method_id": V4_METHODS[0], "scene_id": OLD_DSSM_FAILURE_SCENE,
        "natural_os_exit_code": 1, "plant_calls": 0, "raw_exists": False,
        "first_plant_marker_exists": False, "status": "PRESERVED_PREVIOUS_FAILED_STARTUP_NOT_PART_OF_V9_BATCH",
        "failure_identifier": failure["identifier"], "failure_cause": OLD_DSSM_FAILURE_CAUSE,
        "failure_record_sha256": sha256_file(attempt / "FAILURE_NO_RETRY_v1.json"),
        "batch_record_sha256": sha256_file(attempt.parent.parent / "METHOD_BATCH_STATUS_v1.json"),
    }


def verify_v4_failure_and_path_diagnostic_history(v1) -> dict[str, Any]:
    failure_path = V4_HISTORY_REPORT / "PREPARE_NO_PLANT_FAILURE_v1.json"
    failure_os_path = V4_HISTORY_REPORT / "PREPARE_NO_PLANT_MATLAB_OS_EXIT_v1.json"
    failure_release_path = V4_HISTORY_REPORT / "PREPARE_NO_PLANT_PARENT_RELEASE_v1.json"
    require(sha256_file(failure_path).lower() == V4_FAILURE_RESULT_SHA256
            and sha256_file(failure_os_path).lower() == V4_FAILURE_OS_SHA256
            and sha256_file(failure_release_path).lower() == V4_FAILURE_RELEASE_SHA256,
            "Original v4 no-Plant failure artifacts changed")
    failure = v1.load_json(failure_path)
    receipt = v1.load_json(failure_os_path)
    release = v1.load_json(failure_release_path)
    require(failure.get("schema") == "TEST48_V4_PREPARE_FAILURE_V1"
            and failure.get("status") == "FAILED_NO_RETRY"
            and failure.get("identifier") == "TEST48V4:GlobalPlatformWhich"
            and failure.get("plant_calls") == 0 and failure.get("training_steps") == 0
            and failure.get("TEST_accessed") is True,
            "Original v4 preparation failure status/scope changed")
    require(receipt.get("schema") == "TEST48V4_MATLAB_OS_EXIT_V1"
            and receipt.get("mode") == "PREPARE_NO_PLANT"
            and receipt.get("stage") == "PREPARE_NO_PLANT"
            and receipt.get("method_id") == ""
            and receipt.get("process_scope") == "ONE_STAGE_MATLAB_PROCESS"
            and receipt.get("matlab_os_exit_code") == 1
            and receipt.get("natural_wait_used") is True
            and receipt.get("plant_authorized") is False
            and receipt.get("TEST_accessed") is True
            and receipt.get("command_sha256", "").lower() == V4_HISTORY_LAUNCHER_SHA256
            and receipt.get("contract_sha256", "").lower() == V4_HISTORY_CONTRACT_SHA256
            and receipt.get("source_manifest_sha256", "").lower() == V4_HISTORY_MANIFEST_SHA256
            and path_equal(Path(str(receipt.get("command_file", ""))).resolve(),
                           (V4_HISTORY_TASK / "RUN_TEST48_EXACT_v1.ps1").resolve())
            and receipt.get("stdout_sha256", "").lower() == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
            and receipt.get("stderr_sha256", "").lower() == "c4d1b0db28636d48ee2a63cc4adc2aad71ea2b881a08caea422bc01494fef87f",
            "Original v4 preparation OS1 receipt is not the expected no-Plant failure")
    require(release.get("schema") == "TEST48_V4_PREPARE_NO_PLANT_RELEASE_V1"
            and release.get("status") == "APPROVED_PREPARE_NO_PLANT_V1"
            and release.get("plant_authorized") is False
            and release.get("scene_generation_authorized") is False
            and release.get("TEST_accessed") is True
            and release.get("training_authorized") is False
            and release.get("no_retry") is True
            and release.get("max_plant_calls") == 0
            and release.get("entry_sha256", "").lower() == V4_HISTORY_ENTRY_SHA256
            and release.get("launcher_sha256", "").lower() == V4_HISTORY_LAUNCHER_SHA256
            and release.get("contract_sha256", "").lower() == V4_HISTORY_CONTRACT_SHA256
            and release.get("method_source_manifest_sha256", "").lower() == V4_HISTORY_MANIFEST_SHA256,
            "Original v4 preparation release scope/identities changed")
    for key_path, key_sha in (("stdout_path", "stdout_sha256"), ("stderr_path", "stderr_sha256")):
        v1.verify_file(v1.resolve_repo_path(receipt[key_path]), receipt[key_sha], f"v4 failed preparation {key_path}")
    v4_history = {
        "failure_path": str(failure_path.resolve()), "failure_sha256": sha256_file(failure_path),
        "release_path": str(failure_release_path.resolve()), "release_sha256": sha256_file(failure_release_path),
        "receipt_path": str(failure_os_path.resolve()), "receipt_sha256": sha256_file(failure_os_path),
        "status": "PRESERVED_V4_PREPARE_OS1_ZERO_PLANT_NOT_A_FORMAL_METHOD_BLOCK",
        "natural_os_exit_code": 1, "plant_calls": 0, "training_steps": 0,
        "failure_identifier": failure["identifier"],
    }

    diagnostic_path = PATH_DIAGNOSTIC_REPORT / "PATH_DIAGNOSTIC_RESULT_v1.json"
    diagnostic_os_path = PATH_DIAGNOSTIC_REPORT / "MATLAB_OS_EXIT_v1.json"
    review_path = PATH_DIAGNOSTIC_REPORT / "PARENT_PATH_ROOT_CAUSE_v1.json"
    require(sha256_file(diagnostic_path).lower() == PATH_DIAGNOSTIC_RESULT_SHA256
            and sha256_file(diagnostic_os_path).lower() == PATH_DIAGNOSTIC_OS_SHA256
            and sha256_file(review_path).lower() == PATH_DIAGNOSTIC_REVIEW_SHA256,
            "The isolated v4 path-diagnostic result or receipt changed")
    diagnostic = v1.load_json(diagnostic_path)
    diagnostic_os = v1.load_json(diagnostic_os_path)
    root_review = v1.load_json(review_path)
    require(diagnostic.get("schema") == "TEST48_V4_PATH_DIAGNOSTIC_V1"
            and diagnostic.get("status") == "DIAGNOSTIC_COMPLETE"
            and diagnostic.get("method_count") == 6
            and diagnostic.get("global_rows_total") == 168
            and diagnostic.get("global_same_path_mismatch_rows") == 6
            and diagnostic.get("TEST_shared_scene_loaded") is False
            and diagnostic.get("TEST_raw_loaded") is False
            and diagnostic.get("TEST_outcomes_read") is False
            and diagnostic.get("plant_calls") == 0
            and diagnostic.get("training_steps") == 0,
            "The v4 path diagnostic no longer records the expected no-Plant, no-raw scope and 6/168 mismatch")
    provenance = diagnostic.get("source_provenance", {})
    require(provenance.get("v4_entry_sha256", "").lower() == V4_HISTORY_ENTRY_SHA256
            and provenance.get("contract_sha256", "").lower() == V4_HISTORY_CONTRACT_SHA256
            and provenance.get("method_source_manifest_sha256", "").lower() == V4_HISTORY_MANIFEST_SHA256,
            "The v4 path diagnostic is not tied to the failed v4 source bundle")
    require(diagnostic_os.get("schema") == "TEST48_V4_PATH_DIAGNOSTIC_OS_EXIT_V1"
            and diagnostic_os.get("mode") == "PATH_DIAGNOSTIC_ONLY"
            and diagnostic_os.get("matlab_os_exit_code") == 0
            and diagnostic_os.get("natural_wait_used") is True
            and diagnostic_os.get("diagnostic_script_sha256", "").lower()
                == diagnostic.get("diagnostic_script_sha256", "").lower(),
            "The isolated path diagnostic did not naturally exit OS0")
    for key_path, key_sha in (("stdout_path", "stdout_sha256"), ("stderr_path", "stderr_sha256"),
                              ("extracted_source_manifest_path", "extracted_source_manifest_sha256")):
        v1.verify_file(v1.resolve_repo_path(diagnostic_os[key_path]), diagnostic_os[key_sha],
                       f"v4 path diagnostic {key_path}")
    require(root_review.get("schema") == "PARENT_PATH_ROOT_CAUSE_V1"
            and root_review.get("status") == "CONFIRMED_VERIFIER_REORDERS_LOCKED_PATHS"
            and root_review.get("diagnostic_result_sha256", "").lower() == PATH_DIAGNOSTIC_RESULT_SHA256
            and root_review.get("diagnostic_natural_OS0_receipt_sha256", "").lower() == PATH_DIAGNOSTIC_OS_SHA256
            and root_review.get("six_snapshot_preflight_identities_match_v3_DEV") is True
            and root_review.get("global_rows") == 168 and root_review.get("mismatches") == 6
            and root_review.get("remaining_matches") == 162
            and root_review.get("TEST_performance_accessed") is False
            and root_review.get("Plant_calls") == 0 and root_review.get("training_steps") == 0,
            "The parent path-root-cause review no longer confirms the isolated no-Plant diagnosis")
    return {
        "v4_failed_prepare": v4_history,
        "v4_path_diagnostic": {
            "result_path": str(diagnostic_path.resolve()), "result_sha256": sha256_file(diagnostic_path),
            "os_receipt_path": str(diagnostic_os_path.resolve()), "os_receipt_sha256": sha256_file(diagnostic_os_path),
            "parent_root_cause_review_path": str(review_path.resolve()),
            "parent_root_cause_review_sha256": sha256_file(review_path),
            "status": "PRESERVED_V4_PATH_DIAGNOSTIC_OS0_ZERO_PLANT_NOT_A_FORMAL_METHOD_BLOCK",
            "natural_os_exit_code": 0, "plant_calls": 0, "training_steps": 0,
            "global_rows": 168, "mismatches": 6, "remaining_matches": 162,
            "TEST_raw_loaded": False, "TEST_outcomes_read": False,
        },
    }


def verify_v5_v8_history(v1, manifest: dict) -> list[dict[str, Any]]:
    # Fixed prior processes only; none contributes a successful TEST row.
    pins = (
        (5, "PREPARE_NO_PLANT", 0, 0, "6b5b205532f8a9cbca6251ac0882762f2f981e9b04162615b89961dceff08e71"),
        (5, "ENGINEERING_DSSM", 1, 0, "5d906af25595288e3b94351bd60c7c75544c3fb748513fbfb0f0acc47ec5f661"),
        (6, "PREPARE_NO_PLANT", 0, 0, "f3ef16282c6479a79adfe20c5b9a73924dc2e48ebbdd2b611d6d5d4a88eb5beb"),
        (6, "ENGINEERING_DSSM", 1, 1, "33204ba01c1796c7e71497402088ecf501e70cc2c4adc4202c673746116669f5"),
        (7, "PREPARE_NO_PLANT", 1, 0, "355a6d7373dd3e64d8fa06d2fd911927a9014cca45be21229a294646b4cba3d8"),
        (8, "PREPARE_NO_PLANT", 1, 0, "004e93d8d3fb094acdb4cee3d4a4b147294fc3c7402b5cf7acf80c6a71ba5878"),
    )
    prepare_shas = {5: "07ede6782702e6f5e82fdbc05e73c1f299e8dd96174a12e8043d9942e66bc183",
                    6: "41eadace795daa0bc7b1bf0a6ea83daeeddb2251b4db74ad57c2f25cc62372c1"}
    rows = []
    for version, phase, exit_code, plant_calls, receipt_sha in pins:
        task = ROOT / "experiments" / f"c5_test48_v{version}"
        report = ROOT / "reports" / "paper_continuation_20261023" / f"test_entry_v{version}"
        path = report / f"{phase}_MATLAB_OS_EXIT_v1.json"
        v1.verify_file(path, receipt_sha, f"preserved v{version} {phase} OS receipt")
        receipt = v1.load_json(path)
        prepare = phase == "PREPARE_NO_PLANT"
        require(receipt.get("schema") == "TEST48V4_MATLAB_OS_EXIT_V1"
                and receipt.get("mode") == ("PREPARE_NO_PLANT" if prepare else "ENGINEERING_DEV2")
                and receipt.get("stage") == receipt.get("mode")
                and receipt.get("method_id") == ("" if prepare else V4_METHODS[0])
                and receipt.get("matlab_os_exit_code") == exit_code and receipt.get("natural_wait_used") is True
                and receipt.get("TEST_accessed") is prepare and receipt.get("plant_authorized") is (not prepare),
                f"Preserved v{version} {phase} process identity/scope changed")
        require(path_equal(canonical_path(receipt.get("command_file", ""), v1),
                           task / "RUN_TEST48_EXACT_v1.ps1"), "Historical launcher path changed")
        for source, field in ((task / "RUN_TEST48_EXACT_v1.ps1", "command_sha256"),
                              (task / "TEST48_RUN_CONTRACT_v4.json", "contract_sha256"),
                              (report / "TEST_METHOD_SOURCE_MANIFEST_v4.json", "source_manifest_sha256")):
            v1.verify_file(source, receipt.get(field, ""), f"v{version} preserved {field}")
        for field in ("stdout", "stderr"):
            v1.verify_file(canonical_path(receipt[f"{field}_path"], v1), receipt[f"{field}_sha256"],
                           f"v{version} preserved {phase} {field}")
        if prepare and exit_code == 0:
            result_path = report / "PREPARE_NO_PLANT_RESULT_v1.json"
            v1.verify_file(result_path, prepare_shas[version], f"v{version} prior prepare result")
            result = v1.load_json(result_path)
            require(result.get("status") == "PASS_PREPARE_NO_PLANT" and result.get("plant_calls") == 0
                    and result.get("training_steps") == 0, "Prior preparation scope changed")
        elif prepare:
            evidence = manifest[f"v{version}_prepare_failure_evidence"]
            require(evidence.get("os_exit_sha256", "").lower() == receipt_sha and evidence.get("plant_calls") == 0,
                    f"v{version} failed prepare is not retained by the final manifest")
            require(not (report / "PREPARE_NO_PLANT_RESULT_v1.json").exists()
                    and not (report / "PREPARE_NO_PLANT_FAILURE_v1.json").exists(),
                    "Failed pre-body preparation acquired new outputs")
        else:
            attempt = task / "engineering_dev2" / "DSSM" / "DL1018_VAL_T1_C00_W07" / "attempt_01"
            require(not (report / "ENGINEERING_DSSM_RESULT_v1.json").exists(),
                    "A failed engineering attempt was rewritten as a success")
            if version == 5:
                evidence = manifest["v5_dev2_failure_evidence"]
                require(evidence.get("os_exit_sha256", "").lower() == receipt_sha
                        and evidence.get("plant_calls") == 0 and not (attempt / "raw_run.mat").exists()
                        and not (attempt / "run_start.mat").exists()
                        and not (attempt / "first_plant_step.marker").exists(), "v5 pre-Plant failure changed")
            else:
                evidence = manifest["v6_dev2_failure_evidence"]
                failure_path = canonical_path(evidence["failure_path"], v1)
                v1.verify_file(failure_path, evidence["failure_sha256"], "preserved v6 engineering failure")
                failure = v1.load_json(failure_path)
                require(failure.get("status") == "FAILED_NO_RETRY" and failure.get("plant_calls") == 1
                        and failure.get("TEST_accessed") is False and failure.get("training_steps") == 0
                        and failure.get("plant_start_confirmed") is True and failure.get("partial_raw_preserved") is True
                        and (attempt / "first_plant_step.marker").is_file(), "v6 genuine VAL Plant failure changed")
                v1.verify_file(canonical_path(evidence["partial_raw_path"], v1), evidence["partial_raw_sha256"],
                               "preserved failed v6 VAL raw; excluded from TEST scores")
        rows.append({"method_id": "" if prepare else V4_METHODS[0], "phase": f"PRESERVED_V{version}_{phase}",
                     "receipt": receipt, "receipt_path": str(path.resolve()), "receipt_sha256": receipt_sha,
                     "natural_os_exit_code": exit_code, "plant_calls": plant_calls, "training_steps": 0,
                     "formal_method_block": False, "TEST_performance_row": False})
    return rows


def verify_stage_preconditions(release: dict, v1, manifest: dict) -> dict[str, Any]:
    prepare_result_path = V9_REPORT / "PREPARE_NO_PLANT_RESULT_v1.json"
    prepare_os_path = V9_REPORT / "PREPARE_NO_PLANT_MATLAB_OS_EXIT_v1.json"
    prepare_result = v1.load_json(prepare_result_path)
    prepare_os = v1.load_json(prepare_os_path)
    require(prepare_result.get("schema") == "TEST48_V4_PREPARE_RESULT_V1"
            and prepare_result.get("status") == "PASS_PREPARE_NO_PLANT"
            and prepare_result.get("TEST_accessed") is True
            and prepare_result.get("plant_calls") == 0 and prepare_result.get("training_steps") == 0
            and prepare_os.get("matlab_os_exit_code") == 0 and prepare_os.get("natural_wait_used") is True,
            "v9 no-Plant preparation result/OS0 receipt is incomplete")
    require(prepare_os.get("schema") == "TEST48V4_MATLAB_OS_EXIT_V1"
            and prepare_os.get("mode") == "PREPARE_NO_PLANT" and prepare_os.get("stage") == "PREPARE_NO_PLANT"
            and prepare_os.get("method_id") == "" and prepare_os.get("process_scope") == "ONE_STAGE_MATLAB_PROCESS"
            and prepare_os.get("plant_authorized") is False and prepare_os.get("TEST_accessed") is True
            and prepare_os.get("thread_argument") == "-singleCompThread"
            and prepare_os.get("command_sha256", "").lower() == V9_LAUNCHER_SHA256
            and str(prepare_os.get("command_file", "")).casefold() == str(V9_LAUNCHER.resolve()).casefold()
            and prepare_os.get("contract_sha256", "").lower() == V9_CONTRACT_SHA256
            and prepare_os.get("source_manifest_sha256", "").lower() == V9_MANIFEST_SHA256,
            "v9 preparation process receipt mode/Plant scope changed")
    require_sha_binding(release, "prepare_result_sha256", prepare_result_path, "v9 prepare result")
    require_sha_binding(release, "prepare_os_exit_sha256", prepare_os_path, "v9 prepare OS receipt")
    stages = [{"name": "PREPARE_NO_PLANT", "result_path": str(prepare_result_path.resolve()),
               "result_sha256": sha256_file(prepare_result_path), "os_receipt_path": str(prepare_os_path.resolve()),
               "os_receipt_sha256": sha256_file(prepare_os_path), "natural_os_exit_code": 0}]
    intervals = []
    stage_times = [(v1.utc_instant(prepare_os.get("started_utc")), v1.utc_instant(prepare_os.get("completed_utc")))]
    helper_refs = []
    for method in manifest["methods"]:
        if method["method_id"] in V4_METHODS[:2]:
            helper_refs.extend(ref for ref in method["source_refs"]
                               if Path(str(ref["path"])).name.casefold() == "position_filter_realization_pcf_step_v3_5.m")
    require(len(helper_refs) == 2 and all(ref.get("sha256", "").lower() == FILTER_HELPER_SHA256 for ref in helper_refs),
            "v9 engineering helper path/SHA is not uniquely bound for DSSM and KAN")
    helper_path = v1.resolve_repo_path(helper_refs[0]["path"])
    for alias, mid in (("DSSM", V4_METHODS[0]), ("KAN", V4_METHODS[1])):
        result_path = V9_REPORT / f"ENGINEERING_{alias}_RESULT_v1.json"
        os_path = V9_REPORT / f"ENGINEERING_{alias}_MATLAB_OS_EXIT_v1.json"
        result = v1.load_json(result_path)
        receipt = v1.load_json(os_path)
        require(result.get("schema") == "TEST48V4_ENGINEERING_RESULT_V1"
                and result.get("status") == "PASS_ENGINEERING_DEV2_FULL_RAW"
                and result.get("method_id") == mid and result.get("scene_id") == "DL1018_VAL_T1_C00_W07"
                and result.get("plant_calls") == 1 and result.get("TEST_accessed") is False
                and result.get("training_steps") == 0 and result.get("optimizer_steps") == 0
                and result.get("full_raw_numeric_comparison_pass") is True
                and float(result.get("max_abs_numeric_difference", math.inf)) <= 1e-12
                and int(result.get("compared_numeric_field_count", 0)) > 0
                and int(result.get("compared_numeric_element_count", 0)) > 0
                and isinstance(result.get("numeric_field_audits"), list)
                and len(result["numeric_field_audits"]) == int(result["compared_numeric_field_count"])
                and result.get("global_platform_lock_sha256", "").lower()
                    == manifest.get("global_platform_lock_sha256", "").lower()
                and receipt.get("matlab_os_exit_code") == 0 and receipt.get("natural_wait_used") is True,
                f"{alias} v9 DEV2 engineering replay did not pass its complete numeric comparison and natural OS0")
        require(receipt.get("schema") == "TEST48V4_MATLAB_OS_EXIT_V1"
                and receipt.get("mode") == "ENGINEERING_DEV2" and receipt.get("stage") == "ENGINEERING_DEV2"
                and receipt.get("method_id") == mid and receipt.get("plant_authorized") is True
                and receipt.get("process_scope") == "ONE_SEQUENTIAL_METHOD_MATLAB_PROCESS"
                and receipt.get("TEST_accessed") is False and receipt.get("thread_argument") == "-singleCompThread"
                and receipt.get("command_sha256", "").lower() == V9_LAUNCHER_SHA256
                and str(receipt.get("command_file", "")).casefold() == str(V9_LAUNCHER.resolve()).casefold()
                and receipt.get("contract_sha256", "").lower() == V9_CONTRACT_SHA256
                and receipt.get("source_manifest_sha256", "").lower() == V9_MANIFEST_SHA256,
                f"{alias} v9 DEV2 process receipt does not identify its fixed engineering-only scope")
        engineering = [row for row in manifest.get("engineering_dev2", []) if row.get("method_id") == mid]
        require(len(engineering) == 1, f"Missing exact {alias} engineering reference")
        spec = engineering[0]
        for path_key, sha_key, source_path, source_sha in (
            ("v3_snapshot_path", "v3_snapshot_sha256", "run_start_path", "run_start_sha256"),
            ("v3_raw_path", "v3_raw_sha256", "raw_path", "raw_sha256"),
        ):
            require(canonical_path(result.get(path_key, ""), v1) == canonical_path(spec[source_path], v1)
                    and result.get(sha_key, "").lower() == spec[source_sha].lower(),
                    f"{alias} DEV2 source reference differs from the corrected manifest")
        verify_engineering_helper_binding(result.get("which_bindings"), helper_path)
        require_sha_binding(release, f"engineering_{alias}_result_sha256", result_path,
                            f"{alias} engineering result")
        require_sha_binding(release, f"engineering_{alias}_os_exit_sha256", os_path,
                            f"{alias} engineering OS receipt")
        stages.append({"name": f"ENGINEERING_{alias}", "method_id": mid,
                       "result_path": str(result_path.resolve()), "result_sha256": sha256_file(result_path),
                       "os_receipt_path": str(os_path.resolve()), "os_receipt_sha256": sha256_file(os_path),
                       "natural_os_exit_code": 0, "max_abs_numeric_difference": result["max_abs_numeric_difference"],
                       "full_raw_numeric_comparison_pass": True})
        stage_times.append((v1.utc_instant(receipt.get("started_utc")), v1.utc_instant(receipt.get("completed_utc"))))
    require(all(a[1] <= b[0] for a, b in zip(stage_times, stage_times[1:])),
            "v4 prepare/DEV2 MATLAB receipts are not sequential in the authorized stage order")
    return {"stage_artifacts": stages, "chronological_intervals_utc": [
        {"started_utc": a.isoformat(), "completed_utc": b.isoformat()} for a, b in stage_times],
        "scope_note": "v9 preparation is zero-Plant. The two engineering DEV2 flights are fixed VAL engineering replays, not TEST outcomes."}


def verify_engineering_helper_binding(value, helper_path: Path) -> None:
    rows = value if isinstance(value, list) else ([value] if isinstance(value, dict) else [])
    matches = [row for row in rows if isinstance(row, dict)
               and str(row.get("function_name", "")).casefold() == "position_filter_realization_pcf_step_v3_5"]
    require(len(matches) == 1, "Engineering result must contain exactly one resolved active PCF helper binding")
    row = matches[0]
    for key in ("expected_path", "resolved_first_path"):
        require(path_equal(Path(str(row.get(key, ""))).resolve(), helper_path),
                f"Engineering PCF helper {key} differs from the locked v4 helper path")
    all_paths = row.get("which_all_paths")
    require(isinstance(all_paths, list) and all_paths
            and path_equal(Path(str(all_paths[0])).resolve(), helper_path),
            "Engineering MATLAB which -all did not resolve the locked PCF helper first")


def verify_v4_os_receipt(method: dict, v4_contract: dict, v4_manifest_sha: str,
                         v4_contract_sha: str, release_sha: str, launcher_path: Path,
                         launcher_sha: str, v1) -> dict[str, Any]:
    alias = str(method.get("alias", ""))
    method_id = str(method.get("method_id", ""))
    path = V9_REPORT / f"RUN_{alias}_MATLAB_OS_EXIT_v1.json"
    receipt = v1.load_json(path)
    require(receipt.get("schema") == "TEST48V4_MATLAB_OS_EXIT_V1"
            and receipt.get("mode") == V4_METHOD_PHASE and receipt.get("stage") == V4_METHOD_PHASE
            and receipt.get("method_id") == method_id, f"Unknown v4 natural OS receipt for {method_id}")
    require(receipt.get("process_scope") == "ONE_SEQUENTIAL_METHOD_MATLAB_PROCESS"
            and receipt.get("matlab_os_exit_code") == 0 and receipt.get("natural_wait_used") is True,
            f"v4 method did not naturally exit OS0: {method_id}")
    require(receipt.get("TEST_accessed") is True and receipt.get("plant_authorized") is True
            and receipt.get("thread_argument") == "-singleCompThread"
            and receipt.get("command_sha256", "").lower() == launcher_sha.lower()
            and receipt.get("contract_sha256", "").lower() == v4_contract_sha.lower()
            and receipt.get("source_manifest_sha256", "").lower() == v4_manifest_sha.lower(),
            f"v4 method receipt does not bind the frozen command/contract/manifest for {method_id}")
    require(path_equal(Path(str(receipt.get("command_file", ""))).resolve(), launcher_path.resolve()),
            f"v4 method receipt command path changed for {method_id}")
    if "parent_release_sha256" in receipt:
        require(receipt["parent_release_sha256"].lower() == release_sha.lower(),
                f"v4 method receipt is bound to another run release: {method_id}")
    for key_path, key_sha in (("stdout_path", "stdout_sha256"), ("stderr_path", "stderr_sha256")):
        require(isinstance(receipt.get(key_path), str) and receipt[key_path], f"Missing v4 {key_path} for {method_id}")
        v1.verify_file(v1.resolve_repo_path(receipt[key_path]), receipt.get(key_sha, ""),
                       f"v4 {method_id} {key_path}")
    receipt["receipt_path"] = str(path.resolve())
    receipt["receipt_sha256"] = sha256_file(path)
    receipt["release_sha256"] = release_sha
    return receipt


def verify_mixed_receipt_order(v3_b_receipt: dict, v3_failure: dict, v4_history: dict,
                               stage_history: dict, v9_receipts: list[dict], v1,
                               prior_v5_v8: list[dict]) -> list[dict[str, Any]]:
    receipts = [v3_b_receipt, *v9_receipts]
    times = v1.validate_receipt_sequence(receipts)
    fail = v1.load_json(Path(v3_failure["receipt_path"]))
    process_rows = [{"method_id": "B_TRACEABLE", "phase": "V3_REUSED_B48", "receipt": v3_b_receipt}]
    process_rows.append({"method_id": v3_failure["method_id"], "phase": "PRESERVED_V3_FAILED_STARTUP",
                         "receipt": fail, "receipt_path": v3_failure["receipt_path"],
                         "receipt_sha256": v3_failure["receipt_sha256"],
                         "natural_os_exit_code": 1, "plant_calls": 0, "raw_exists": False})
    v4_failure = v1.load_json(Path(v4_history["v4_failed_prepare"]["receipt_path"]))
    process_rows.append({"method_id": "", "phase": "PRESERVED_V4_PREPARE_OS1_ZERO_PLANT",
                         "receipt": v4_failure, "receipt_path": v4_history["v4_failed_prepare"]["receipt_path"],
                         "receipt_sha256": v4_history["v4_failed_prepare"]["receipt_sha256"],
                         "natural_os_exit_code": 1, "plant_calls": 0,
                         "formal_method_block": False})
    path_diag = v1.load_json(Path(v4_history["v4_path_diagnostic"]["os_receipt_path"]))
    process_rows.append({"method_id": "", "phase": "V4_PATH_DIAGNOSTIC_OS0_ZERO_PLANT",
                         "receipt": path_diag,
                         "receipt_path": v4_history["v4_path_diagnostic"]["os_receipt_path"],
                         "receipt_sha256": v4_history["v4_path_diagnostic"]["os_receipt_sha256"],
                         "natural_os_exit_code": 0, "plant_calls": 0,
                         "formal_method_block": False})
    process_rows.extend(prior_v5_v8)
    for artifact in stage_history["stage_artifacts"]:
        process_rows.append({"method_id": artifact.get("method_id", ""), "phase": artifact["name"],
                             "receipt": v1.load_json(Path(artifact["os_receipt_path"])),
                             "receipt_path": artifact["os_receipt_path"],
                             "receipt_sha256": artifact["os_receipt_sha256"]})
    process_rows.extend({"method_id": item["method_id"], "phase": "V9_FORMAL_METHOD_BLOCK", "receipt": item}
                        for item in v9_receipts)
    intervals = []
    for row in process_rows:
        receipt = row["receipt"]
        intervals.append((v1.utc_instant(receipt.get("started_utc")), v1.utc_instant(receipt.get("completed_utc"))))
    require(all(start <= end for start, end in intervals)
            and all(intervals[i][1] <= intervals[i + 1][0] for i in range(len(intervals) - 1)),
            "v3/v4 historical failures, diagnostic, v9 prepare/DEV2, and formal receipts are not in strict sequential order")
    require(tuple(item["method_id"] for item in v9_receipts) == V4_METHODS,
            "v9 formal method receipt order differs from the five fixed unstarted methods")
    output = []
    for index, (row, (start, end)) in enumerate(zip(process_rows, intervals)):
        receipt = row["receipt"]
        gap = None if index == 0 else (start - intervals[index - 1][1]).total_seconds()
        output.append({"method_id": row["method_id"], "phase": row["phase"],
                       "receipt_path": receipt.get("receipt_path") or row.get("receipt_path"),
                       "receipt_sha256": receipt.get("receipt_sha256") or row.get("receipt_sha256"),
                       "started_utc": start.isoformat(), "completed_utc": end.isoformat(),
                       "gap_since_previous_process_seconds": gap,
                       **{key: value for key, value in row.items() if key not in {"method_id", "phase", "receipt"}}})
    return output


def verify_v3_b_artifacts(v1, v3_methods: dict[str, dict], scene_ids: list[str],
                          v3_release: dict, v3_source_sha: str, input_hashes: dict[str, str]) -> tuple[dict, list[dict]]:
    method = v3_methods[EXPECTED_METHODS[0]]
    reuse = load_json(V9_MANIFEST).get("methods", [])[0].get("v3_reuse_binding", {})
    for field, expected_path in (("method_batch_path", V3_TASK / "runs" / "BTR" / "METHOD_BATCH_STATUS_v1.json"),
                                 ("method_body_path", V3_TASK / "runs" / "BTR" / "METHOD_BODY_COMPLETE_v1.json")):
        require(canonical_path(reuse.get(field, ""), v1) == expected_path.resolve(strict=True),
                f"v4 B reuse path mismatch: {field}")
        v1.verify_file(expected_path, reuse.get(field.replace("path", "sha256"), ""), f"v4 B reuse {field}")
    batch, body, records = v1.verify_batch_body(EXPECTED_METHODS[0], "BTR", 1, scene_ids,
                                                 v3_source_sha, input_hashes["index"], input_hashes["shared"],
                                                 input_hashes["cfg"], sha256_file(v1.LOCKED_RELEASE))
    require(batch.get("phase") == "LOCKED_TEST48_PARENT_APPROVED", "Reused v3 B block did not use its original v3 release")
    return {"batch": batch, "body": body, "records": records}, records


def verify_v4_method_block(method: dict, method_index: int, scene_ids: list[str], scene_digests: list[str],
                           source_sha: str, input_hashes: dict[str, str], release_sha: str,
                           runner_sha: str, v1) -> tuple[dict, list[dict]]:
    alias = str(method["alias"])
    method_id = str(method["method_id"])
    root = V9_OUTPUT / alias
    batch_path = root / "METHOD_BATCH_STATUS_v4.json"
    body_path = root / "METHOD_BODY_COMPLETE_v4.json"
    batch, body = v1.load_json(batch_path), v1.load_json(body_path)
    require(batch.get("schema") == "TEST48V4_METHOD_BATCH_STATUS_V1"
            and batch.get("status") == "COMPLETE_RAW_PENDING_PARENT_AUDIT"
            and batch.get("method_id") == method_id and batch.get("alias") == alias
            and batch.get("phase") == V4_METHOD_PHASE,
            f"v4 batch schema/status/order/identity mismatch for {method_id}")
    require(body.get("schema") == "TEST48V4_METHOD_BODY_COMPLETE_V1"
            and body.get("status") == "RUN_COMPLETE_RAW_PENDING_PARENT_AUDIT"
            and body.get("method_id") == method_id and body.get("alias") == alias,
            f"v4 body schema/status/identity mismatch for {method_id}")
    for label, source in (("batch", batch), ("body", body)):
        require(source.get("scene_count") == source.get("completed_scenes") == 48
                and source.get("plant_calls") == 48 and source.get("training_steps") == 0
                and source.get("optimizer_steps") == 0 and source.get("TEST_accessed") is True,
                f"v4 {label} counts or run flags invalid for {method_id}")
        expected_bindings = {
            "parent_release_sha256": release_sha,
            "input_index_sha256": input_hashes["index"],
            "shared_scenes_mat_sha256": input_hashes["shared"],
            "method_cfg_opts_sha256": input_hashes["cfg"],
            "method_source_manifest_sha256": source_sha,
            "runner_sha256": runner_sha,
        }
        for key, expected in expected_bindings.items():
            require(str(source.get(key, "")).lower() == expected.lower(),
                    f"v4 {label} does not bind {key} for {method_id}")
    require(batch.get("thread_argument") == "-singleCompThread"
            and batch.get("controller_timer_boundary") ==
            "Frozen controller_call_time_s source unchanged; ends before allocator/Plant/MAT save.",
            f"v4 timer boundary/thread setting changed for {method_id}")
    require(body.get("scene_ids") == scene_ids, f"v4 body scene order differs from frozen input order for {method_id}")
    records = batch.get("records")
    body_records = body.get("records")
    require(isinstance(records, list) and isinstance(body_records, list)
            and len(records) == len(body_records) == 48 and v1.strict_equal_json(records, body_records),
            f"v4 batch/body record rows differ or are incomplete for {method_id}")
    for index, (scene_id, digest, row) in enumerate(zip(scene_ids, scene_digests, records), start=1):
        require(row.get("batch_index") == index and row.get("scene_id") == scene_id
                and row.get("status") == "RUN_COMPLETE_RAW_PENDING_PARENT_AUDIT"
                and row.get("plant_calls") == 1 and row.get("TEST_accessed") is True,
                f"v4 body record order/status mismatch for {method_id}/{scene_id}")
        attempt = root / scene_id / "attempt_01"
        expected_paths = {
            "raw_path": attempt / "raw_run.mat",
            "run_start_path": attempt / "run_start.mat",
            "run_status_path": attempt / "run_status_v4.json",
            "attempt_started_marker_path": attempt / "attempt_started.marker",
            "first_plant_step_marker_path": attempt / "first_plant_step.marker",
        }
        for path_key, expected_path in expected_paths.items():
            actual_path = Path(str(row.get(path_key, ""))).resolve(strict=True)
            require(path_equal(actual_path, expected_path.resolve(strict=True)),
                    f"v4 record path mismatch at {path_key}: {method_id}/{scene_id}")
            sha_key = path_key.replace("_path", "_sha256")
            v1.verify_file(actual_path, row.get(sha_key, ""), f"v4 {method_id}/{scene_id} {path_key}")
        status = v1.load_json(expected_paths["run_status_path"])
        require(status.get("schema") == "TEST48V4_RUN_STATUS_V1"
                and status.get("status") == "RUN_COMPLETE_RAW_PENDING_PARENT_AUDIT"
                and status.get("method_id") == method_id and status.get("alias") == alias
                and status.get("scene_id") == scene_id and status.get("batch_index") == index,
                f"v4 run status schema/identity mismatch for {method_id}/{scene_id}")
        require(status.get("plant_calls") == 1 and status.get("training_steps") == 0
                and status.get("optimizer_steps") == 0 and status.get("TEST_accessed") is True
                and status.get("log_status") == "STABLE" and status.get("last_transition") == 20_000
                and status.get("transition_count") == 20_000 and status.get("state_sample_count") == 20_001,
                f"v4 run status incomplete/unsafe for {method_id}/{scene_id}")
        for key, expected_path in expected_paths.items():
            status_key = key
            require(path_equal(Path(str(status.get(status_key, ""))).resolve(), expected_path.resolve()),
                    f"v4 status {status_key} mismatch for {method_id}/{scene_id}")
        for sha_key in ("raw_sha256", "run_start_sha256", "attempt_started_marker_sha256", "first_plant_step_marker_sha256"):
            require(str(status.get(sha_key, "")).lower() == str(row.get(sha_key, "")).lower(),
                    f"v4 run status/body {sha_key} mismatch for {method_id}/{scene_id}")
        require(not (attempt / "FAILURE_NO_RETRY_v4.json").exists(),
                f"v4 no-retry failure marker exists for a claimed successful row {method_id}/{scene_id}")
    require(body.get("parent_release_sha256", "").lower() == release_sha.lower(),
            f"v4 method body parent release mismatch for {method_id}")
    return {"batch": batch, "body": body, "paths": {"batch": str(batch_path.resolve()), "body": str(body_path.resolve())},
            "shas": {"batch": sha256_file(batch_path), "body": sha256_file(body_path)}}, records


def path_equal(a: Path, b: Path) -> bool:
    return str(a.resolve()).casefold() == str(b.resolve()).casefold()


def verify_spec_storage_identity(expected, start_path: Path, v1, c5_review, decoder, label: str) -> None:
    # The frozen decoder returns integer storage headers for opaque MATLAB tables.
    # Equality of these headers is not independent decoding of table contents.
    with h5py.File(start_path, "r") as file:
        node = file["spec"]
        opaque_table = isinstance(node, h5py.Dataset) and node.attrs.get("MATLAB_class") == b"table"
        if opaque_table:
            require(node.dtype.kind in "ui" and "MATLAB_object_decode" in node.attrs,
                    f"Unknown opaque MATLAB table representation: {label}")
    actual = v1.mat_section(start_path, "spec", c5_review, decoder)
    v1.equal_mat(expected, actual, c5_review, decoder,
                 ("opaque spec storage header only " if opaque_table else "decoded spec metadata ") + label)


def verify_v4_run_identity(raw_path: Path, start_path: Path, record: dict, method: dict,
                           method_index: int, scene_id: str, scene_digest: str, scene_pack: dict,
                           snapshot: dict, source_sha: str, cfg_sha: str, release_sha: str,
                           input_index_sha: str, runner_path: Path, runner_sha: str,
                           global_refs: list[dict], v1, c5_review, decoder) -> tuple[dict, dict, dict]:
    identity = v1.mat_section(raw_path, "runIdentity", c5_review, decoder)
    meta = v1.mat_section(start_path, "meta", c5_review, decoder)
    require(isinstance(identity, dict) and isinstance(meta, dict), "v4 runIdentity/run_start meta has unknown schema")
    mid, alias = method["method_id"], method["alias"]
    candidate, collector = v1.expected_method_tags(method)
    expected = {
        "schema": "TEST48V4_RUN_IDENTITY_V1", "method_id": mid, "alias": alias,
        "scene_id": scene_id, "scene_digest_sha256": scene_digest,
        "method_source_manifest_sha256": source_sha,
        "method_cfg_opts_snapshot_sha256": cfg_sha,
        "parent_release_sha256": release_sha,
        "input_index_sha256": input_index_sha,
        "runner_sha256": runner_sha,
        "thread_argument": "-singleCompThread",
        "method_block_order": method_index,
    }
    for key, value in expected.items():
        actual = v1.scalar(identity.get(key), c5_review, f"v4 runIdentity.{key}")
        require(str(actual).lower() == str(value).lower(), f"v4 runIdentity {key} mismatch for {mid}/{scene_id}")
    require(path_equal(Path(v1.as_text(identity.get("runner_path"), c5_review, "runner_path")).resolve(), runner_path.resolve()),
            f"v4 runner path mismatch for {mid}/{scene_id}")
    require(v1.as_bool(identity.get("TEST_accessed"), c5_review, "TEST_accessed")
            and v1.as_int(identity.get("plant_calls"), c5_review, "plant_calls") == 1
            and v1.as_int(identity.get("training_steps"), c5_review, "training_steps") == 0
            and v1.as_int(identity.get("optimizer_steps"), c5_review, "optimizer_steps") == 0
            and not v1.as_bool(identity.get("parameter_or_seed_search"), c5_review, "parameter_or_seed_search"),
            f"v4 execution flags invalid for {mid}/{scene_id}")
    require(v1.as_text(identity.get("run_start_sha256"), c5_review, "run_start_sha256").lower()
            == sha256_file(start_path).lower(), f"v4 run_start SHA mismatch for {mid}/{scene_id}")
    attempt = raw_path.parent
    marker_path = attempt / "first_plant_step.marker"
    require(v1.as_text(identity.get("first_plant_step_marker_sha256"), c5_review, "marker SHA").lower()
            == sha256_file(marker_path).lower(), f"v4 first-Plant marker SHA mismatch for {mid}/{scene_id}")
    require(re.fullmatch(r"[0-9a-fA-F]{64}", v1.as_text(identity.get("pre_identity_append_sha256"), c5_review,
                                                          "pre_identity_append_sha256")) is not None,
            f"Missing pre-identity raw SHA for {mid}/{scene_id}")
    meta_expected = {
        "schema": "TEST48V4_RUN_START_METADATA_V1", "method_id": mid, "alias": alias,
        "scene_id": scene_id, "candidate": candidate, "collector_tag": collector,
        "method_source_manifest_sha256": source_sha,
        "method_cfg_opts_snapshot_sha256": cfg_sha,
        "input_index_sha256": input_index_sha,
        "parent_release_sha256": release_sha,
        "batch_index": int(record["batch_index"]), "batch_total": 48,
        "method_block_order": method_index, "thread_argument": "-singleCompThread",
    }
    for key, value in meta_expected.items():
        actual = v1.scalar(meta.get(key), c5_review, f"run_start.meta.{key}")
        require(str(actual).lower() == str(value).lower(), f"v4 run_start meta {key} mismatch for {mid}/{scene_id}")
    require(v1.as_bool(meta.get("TEST_accessed"), c5_review, "meta.TEST_accessed")
            and v1.as_int(meta.get("plant_calls_before_invocation"), c5_review, "meta.plant_calls_before_invocation") == 0
            and v1.as_int(meta.get("training_steps"), c5_review, "meta.training_steps") == 0
            and v1.as_int(meta.get("optimizer_steps"), c5_review, "meta.optimizer_steps") == 0,
            f"v4 run_start execution flags invalid for {mid}/{scene_id}")
    paths = {
        "attempt_started_marker_path": attempt / "attempt_started.marker",
        "first_plant_step_marker_path": marker_path,
        "raw_path": raw_path,
        "run_status_path": attempt / "run_status_v4.json",
    }
    for key, expected_path in paths.items():
        actual = Path(v1.as_text(meta.get(key), c5_review, f"run_start.meta.{key}")).resolve()
        require(path_equal(actual, expected_path.resolve()), f"v4 run_start meta {key} path mismatch for {mid}/{scene_id}")
    require(str(v1.scalar(meta.get("scene_digest_sha256"), c5_review, "meta scene digest")).lower() == scene_digest.lower(),
            f"v4 run_start scene digest mismatch for {mid}/{scene_id}")
    v1.equal_mat(snapshot["cfg"], v1.mat_section(start_path, "cfg", c5_review, decoder), c5_review, decoder,
                 f"v4 run_start.cfg {mid}/{scene_id}")
    opts = v1.mat_section(start_path, "opts", c5_review, decoder)
    v1.equal_mat(snapshot["opts"], opts, c5_review, decoder, f"v4 run_start.opts {mid}/{scene_id}", ignore_marker=True)
    marker_in_opts = opts.get("r2e_first_plant_step_marker") if isinstance(opts, dict) else None
    require(str(v1.plain(marker_in_opts, c5_review)).casefold() == str(marker_path.resolve()).casefold(),
            f"v4 opts first-Plant marker path mismatch for {mid}/{scene_id}")
    for source_key, mat_name in (("scene", "scene"), ("metadata", "sceneMeta")):
        v1.equal_mat(scene_pack[source_key], v1.mat_section(start_path, mat_name, c5_review, decoder),
                     c5_review, decoder, f"v4 {mat_name} identity {mid}/{scene_id}")
    verify_spec_storage_identity(scene_pack["spec"], start_path, v1, c5_review, decoder, f"{mid}/{scene_id}")
    v1.equal_mat(identity.get("which_bindings"), meta.get("which_bindings"), c5_review, decoder,
                 f"v4 which bindings {mid}/{scene_id}")
    v1.equal_mat(identity.get("model_identity"), meta.get("modelIdentity"), c5_review, decoder,
                 f"v4 model identity {mid}/{scene_id}")
    v1.equal_mat(snapshot.get("modelIdentity"), meta.get("modelIdentity"), c5_review, decoder,
                 f"v4 frozen model identity {mid}/{scene_id}")
    model_refs = {ref.get("role"): ref for ref in method.get("model_refs", [])}
    expected_model_sha = model_refs.get("model_mat", {}).get("sha256", "")
    expected_normalizer_sha = model_refs.get("normalizer", {}).get("sha256", "")
    require(str(v1.scalar(identity.get("model_mat_sha256"), c5_review, "model_mat_sha256")).lower()
            == str(expected_model_sha).lower()
            and str(v1.scalar(identity.get("normalizer_sha256"), c5_review, "normalizer_sha256")).lower()
            == str(expected_normalizer_sha).lower(), f"v4 model/normalizer SHA mismatch for {mid}/{scene_id}")
    v1.equal_mat(identity.get("machine_info"), meta.get("machine_info"), c5_review, decoder,
                 f"v4 machine metadata {mid}/{scene_id}")
    snapshot_identity = v1.plain(snapshot.get("modelIdentity"), c5_review)
    expected_w0 = snapshot_identity.get("W0_sha256", "") if isinstance(snapshot_identity, dict) else ""
    require(str(v1.scalar(identity.get("initial_weight_identity"), c5_review, "initial_weight_identity"))
            == str(expected_w0), f"v4 initial W0 identity mismatch for {mid}/{scene_id}")
    v1.validate_bindings(identity, method, c5_review)
    verify_global_bindings(identity.get("global_platform_which_bindings"), global_refs, v1, c5_review)
    if "global_platform_which_bindings" in meta:
        v1.equal_mat(identity.get("global_platform_which_bindings"), meta.get("global_platform_which_bindings"),
                     c5_review, decoder, f"v4 global platform bindings {mid}/{scene_id}")
    return identity, meta, opts


def verify_global_bindings(actual_value, refs: list[dict], v1, c5_review) -> None:
    rows = v1.records_from_matlab(actual_value, c5_review, "runIdentity.global_platform_which_bindings")
    expected = {}
    for ref in refs:
        if ref.get("role") not in {"frozen_plant", "frozen_runtime"}:
            continue
        path = canonical_path(ref["path"], v1)
        if path.suffix.lower() == ".m":
            name = path.stem.casefold()
            require(name not in expected, f"Duplicate global platform function basename {name}")
            expected[name] = (path, ref["role"])
    require(len(rows) == len(expected), "Global platform which binding count differs from the locked runtime set")
    seen = set()
    for row in rows:
        name = str(row.get("function_name", "")).casefold()
        require(name in expected and name not in seen, f"Unexpected/duplicate global platform function {name}")
        path, role = expected[name]
        for field in ("expected_path", "resolved_first_path"):
            require(path_equal(Path(str(row.get(field, ""))).resolve(), path),
                    f"Global platform binding {field} changed for {name}")
        require(row.get("source_role") == role, f"Global platform source role changed for {name}")
        seen.add(name)


def run_review(output_path: Path) -> dict[str, Any]:
    require(not output_path.exists(), f"Refusing to overwrite output: {output_path}")
    v1 = load_v1()
    v4_contract, v4_manifest, v3_contract, code_info = verify_v4_code_and_manifest(v1)
    release, release_info = verify_v4_run_release(v4_contract, code_info, v1)
    failure_history = verify_v3_failure_history(v1)
    v4_history = verify_v4_failure_and_path_diagnostic_history(v1)
    prior_v5_v8 = verify_v5_v8_history(v1, v4_manifest)

    # This complete OS0 preflight is deliberately before any TEST MAT or score file is opened.
    v3_b_receipt = v1.verify_os_receipt("B_TRACEABLE", "BTR", V3_MANIFEST_SHA256, V3_CONTRACT_SHA256)
    require(v3_b_receipt.get("receipt_sha256", "").lower() == V3_B_OS_RECEIPT_SHA256,
            "Reused v3 B48 natural OS0 receipt SHA changed")
    v9_methods = v4_manifest["methods"][1:]
    v9_receipts = [verify_v4_os_receipt(method, v4_contract, code_info["v9_source_manifest_sha256"],
                                        code_info["v9_run_contract_sha256"], release_info["sha256"],
                                        Path(code_info["v9_launcher_path"]),
                                        code_info["v9_launcher_sha256"], v1) for method in v9_methods]
    stage_history = verify_stage_preconditions(release, v1, v4_manifest)
    receipt_history = verify_mixed_receipt_order(v3_b_receipt, failure_history, v4_history,
                                                 stage_history, v9_receipts, v1, prior_v5_v8)

    scorer, c5_review, ablation, decoder, helper_hashes = v1.verify_helpers()
    v3_source_bindings = v1.verify_manifest_sources(load_json(v1.SOURCE_MANIFEST), ROOT)
    require(v1.sha256_file(v1.SOURCE_MANIFEST).lower() == V3_MANIFEST_SHA256,
            "The B/v3 source manifest changed before the mixed audit")
    v9_source_bindings = verify_v4_source_files(v4_manifest, v1)

    # Preserve v1's frozen TEST input decoder/round-trip checks, using its v3 manifest.
    index, freeze, v3_release, bound_files, scene_ids, scene_digests = v1.verify_input_package(
        v3_contract, load_json(v1.SOURCE_MANIFEST), V3_MANIFEST_SHA256)
    require(index["scene_set_sha256"].lower() == EXPECTED_FROZEN_INPUTS["scene_set_sha256"],
            "v3 shared scene-set identity differs from v9's inherited lock")
    for field, expected in EXPECTED_FROZEN_INPUTS.items():
        if field in {"shared_scenes_sha256", "cfg_opts_sha256", "index_sha256", "freeze_result_sha256", "freeze_os_sha256"}:
            actual_key = {"shared_scenes_sha256": "shared_scenes_mat_sha256", "cfg_opts_sha256": "method_cfg_opts_sha256",
                          "index_sha256": "index_sha256", "freeze_result_sha256": "freeze_result_sha256",
                          "freeze_os_sha256": "freeze_os_exit_sha256"}[field]
            if field in {"index_sha256", "freeze_result_sha256", "freeze_os_sha256"}:
                actual = {"index_sha256": sha256_file(v1.INPUT_INDEX),
                          "freeze_result_sha256": sha256_file(v1.FREEZE_RESULT),
                          "freeze_os_sha256": sha256_file(v1.FREEZE_EXIT)}[field]
            else:
                actual = v3_release.get(actual_key, "")
            require(str(actual).lower() == expected.lower(), f"v3/v9 frozen input binding mismatch for {field}")
    snapshots_scene, snapshots, model_summary, c5_w0_hashes = v1.verify_scene_and_snapshots(
        index, scene_ids, scene_digests, c5_review, decoder)
    # The scene package is read once above for identity check; reuse it for all subsequent comparisons.
    scene_packs = snapshots_scene
    v1._SCENE_INDEX.clear()
    v1._SCENE_INDEX.update({scene_id: i for i, scene_id in enumerate(scene_ids, start=1)})

    v3_methods = {row["method_id"]: row for row in load_json(v1.SOURCE_MANIFEST)["methods"]}
    v9_methods_by_id = {row["method_id"]: row for row in v4_manifest["methods"]}
    input_hashes = {"index": sha256_file(v1.INPUT_INDEX), "shared": sha256_file(v1.SHARED_SCENES),
                    "cfg": sha256_file(v1.CFG_OPTS)}
    b_artifacts, b_records = verify_v3_b_artifacts(v1, v3_methods, scene_ids, v3_release,
                                                   V3_MANIFEST_SHA256, input_hashes)
    method_records = {EXPECTED_METHODS[0]: b_records}
    method_blocks = []
    b_raw_root = V3_TASK / "runs" / "BTR"
    method_blocks.append({
        "method_id": EXPECTED_METHODS[0], "alias": "BTR", "method_block_order": 1,
        "source_version": "v3_REUSED", "natural_os_exit_receipt": v3_b_receipt,
        "batch_path": str((b_raw_root / "METHOD_BATCH_STATUS_v1.json").resolve()),
        "batch_sha256": sha256_file(b_raw_root / "METHOD_BATCH_STATUS_v1.json"),
        "body_path": str((b_raw_root / "METHOD_BODY_COMPLETE_v1.json").resolve()),
        "body_sha256": sha256_file(b_raw_root / "METHOD_BODY_COMPLETE_v1.json"),
        "plant_calls": 48, "scene_records": 48,
        "runtime_tree_sha256": b_artifacts["batch"].get("runtime_tree_sha256", ""),
        "machine_info": b_artifacts["batch"].get("machine_info"),
        "thread_argument": b_artifacts["batch"].get("thread_argument"),
        "controller_timer_boundary": b_artifacts["batch"].get("controller_timer_boundary"),
        "records": [], "model_identity": model_summary[EXPECTED_METHODS[0]],
    })
    for method_id in V4_METHODS:
        method = v9_methods_by_id[method_id]
        block, records = verify_v4_method_block(method, EXPECTED_METHODS.index(method_id) + 1,
                                                scene_ids, scene_digests,
                                                code_info["v9_source_manifest_sha256"], input_hashes,
                                                release_info["sha256"], code_info["v9_entry_sha256"], v1)
        method_records[method_id] = records
        block["natural_os_exit_receipt"] = next(r for r in v9_receipts if r["method_id"] == method_id)
        batch_summary = block.pop("batch")
        block.pop("body")
        block.update(method_id=method_id, alias=method["alias"],
                     method_block_order=EXPECTED_METHODS.index(method_id) + 1,
                     source_version="v9_NEW_UNSTARTED_V4_SCHEMA", plant_calls=48, scene_records=48,
                     machine_info=batch_summary.get("machine_info"),
                     thread_argument=batch_summary.get("thread_argument"),
                     controller_timer_boundary=batch_summary.get("controller_timer_boundary"),
                     runtime_tree_sha256=batch_summary.get("runtime_tree_sha256", ""),
                     model_identity=model_summary[method_id], records=[])
        method_blocks.append(block)

    hashes_for_identity = {
        "source_manifest": V3_MANIFEST_SHA256,
        "method_cfg_opts_mat": input_hashes["cfg"],
        "parent_release": sha256_file(v1.LOCKED_RELEASE),
        "input_index": input_hashes["index"],
    }
    rows, event_audits, actuator_summary, initial_weight_audits = [], [], [], []
    native_by_method = {}
    physical_by_scene = {scene_id: [] for scene_id in scene_ids}
    for method_index, method_id in enumerate(EXPECTED_METHODS, start=1):
        method = (v3_methods if method_index == 1 else v9_methods_by_id)[method_id]
        version = "v3" if method_index == 1 else "v9"
        alias = str(method["alias"])
        snapshot = snapshots[method_index - 1]
        method_native = []
        record_provenance = []
        for scene_index, (scene_id, digest, record) in enumerate(zip(scene_ids, scene_digests,
                                                                      method_records[method_id]), start=1):
            if version == "v3":
                raw_path, start_path, run_status = v1.verify_record_files(
                    record, method_id, alias, method_index, scene_id, digest, V3_MANIFEST_SHA256,
                    input_hashes["index"], input_hashes["shared"], input_hashes["cfg"],
                    sha256_file(v1.LOCKED_RELEASE))
                identity, meta, _ = v1.verify_run_identity_and_start(
                    raw_path, start_path, record, method, method_index, scene_id,
                    scene_packs[scene_index - 1], snapshot, hashes_for_identity, digest, c5_review, decoder)
            else:
                raw_path = Path(record["raw_path"]).resolve(strict=True)
                start_path = Path(record["run_start_path"]).resolve(strict=True)
                run_status = v1.load_json(record["run_status_path"])
                identity, meta, _ = verify_v4_run_identity(
                    raw_path, start_path, record, method, method_index, scene_id, digest,
                    scene_packs[scene_index - 1], snapshot, code_info["v9_source_manifest_sha256"],
                    input_hashes["cfg"], release_info["sha256"], input_hashes["index"], V9_ENTRY,
                    code_info["v9_entry_sha256"], v4_manifest["global_platform_refs"],
                    v1, c5_review, decoder)
            if method_id in v1.CORRECTED_METHODS:
                initial_weight_audits.append({"scene_id": scene_id, "method": method_id,
                                              **v1.audit_corrected_initial_weight(raw_path, method_id, snapshot, c5_review)})
            record_provenance.append({key: record[key] for key in (
                "batch_index", "scene_id", "raw_path", "raw_sha256", "run_start_path", "run_start_sha256",
                "run_status_path", "run_status_sha256", "attempt_started_marker_path",
                "attempt_started_marker_sha256", "first_plant_step_marker_path",
                "first_plant_step_marker_sha256", "plant_calls", "TEST_accessed")})
            item_sha = str(record["raw_sha256"]).lower()
            scored, actuator, native = v1.score_one(raw_path, scene_id, method_id, item_sha, scorer, c5_review)
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
            if method_id in v1.C5_METHODS:
                cfg = snapshot["cfg"]
                if method_id == "C5_M110":
                    event_result = c5_review.event_audit(raw_path, cfg,
                        expected_w0=v1.get_w0(snapshot["opts"], c5_review, method_id),
                        expected_w0_sha256=c5_w0_hashes[method_id])
                elif method_id in v1.ABLATED_METHODS:
                    event_result = ablation.audit_events(raw_path, cfg, method_id,
                        v1.get_w0(snapshot["opts"], c5_review, method_id), c5_w0_hashes[method_id])
                else:
                    raise ValueError(f"No frozen C5 event auditor for {method_id}")
                require(event_result.get("event_count") == 1_968 and event_result.get("log_status") == "STABLE",
                        f"C5 event audit incomplete for {method_id}/{scene_id}")
                event_result.pop("initial_weight", None)
                event_audits.append({"scene_id": scene_id, "method": method_id, **v1.json_safe(event_result)})
        require(len(method_native) == 48, f"Native-readiness scan incomplete for {method_id}")
        native_by_method[method_id] = v1.summarize_native(method_native)
        method_blocks[method_index - 1]["records"] = record_provenance

    require(len(rows) == 288 and len({(r["scene_id"], r["method"]) for r in rows}) == 288,
            "Final result does not contain 288 unique scene/method score rows")
    require(tuple(dict.fromkeys(r["method"] for r in rows)) == EXPECTED_METHODS,
            "Score rows do not follow the exact six-method block order")
    require(all(len(values) == 6 and len(set(values)) == 1 for values in physical_by_scene.values()),
            "A scene does not have six equal external physical identity hashes")
    require(len(event_audits) == 144 and sum(r["event_count"] for r in event_audits) == 144 * 1_968,
            "C5 plus matched ablations did not audit 1,968 events on all 144 flights")
    require(len(initial_weight_audits) == 96
            and all(r["scene_method_status"] == "PASS_EXACT_INITIAL_WEIGHT_MATCH"
                    and r["exact_elementwise_match"] is True for r in initial_weight_audits),
            "DSSM/KAN initial raw W0 does not exactly match the frozen 33x3 weights on all 96 flights")
    require(sum(block["plant_calls"] for block in method_blocks) == 288
            and all(r["natural_os_exit_receipt"]["matlab_os_exit_code"] == 0 for r in method_blocks),
            "Mixed six-method output lacks 288 calls and six natural OS0 method receipts")
    require(all(r["status"] == "STABLE" and r["safety_stop"] is False and r["complete"] is True
                and r["actuator_finite_complete"] is True for r in rows),
            "A score row failed safety/completeness status")
    return v1.json_safe({
        "schema": "TEST48_RAW_IDENTITIES_PHYSICS_ALL_METHODS_V1",
        "status": "PASS_TEST48_RAW_IDENTITIES_PHYSICS_ALL_METHODS",
        "TEST_accessed": True, "plant_calls": 288, "training_steps": 0, "optimizer_steps": 0,
        "scene_count": 48, "method_count": 6, "rows": rows, "methods_order": list(EXPECTED_METHODS),
        "scene_ids": scene_ids,
        "provenance": {
            "mixed_method_sources": {"B_TRACEABLE": "v3_reused", "five_remaining_methods": "v9_path_repair_v4_schema"},
            "frozen_helpers": helper_hashes,
            "v3_source_manifest": v3_source_bindings,
            "v9_source_manifest": v9_source_bindings,
            "v3_bound_files": bound_files,
            "v9_run_release": release_info,
            "v9_code_and_input_bindings": code_info,
            "v3_failed_startup_preserved": failure_history,
            "v4_failed_prepare_and_path_diagnostic_preserved": v4_history,
            "v5_v8_prior_prepare_and_failed_attempts": prior_v5_v8,
            "v9_prepare_and_DEV2_history": stage_history,
            "chronological_process_receipts": receipt_history,
            "method_blocks": method_blocks,
            "common_scene_set_sha256": index["scene_set_sha256"],
            "external_identity_hashes_match_by_scene_across_all_methods": True,
            "historical_helper_identity_limitation": (
                "The old v3 DSSM/KAN raw carries no historical MATLAB which SHA; the v9 dependency lock and active which "
                "bind the pre-existing PCF helper. The fixed DEV2 replays are a behavioral/full-raw bridge, not retroactive proof of old source identity."
            ),
        },
        "event_audit": {"method_scope": sorted(v1.C5_METHODS), "audited_flights": len(event_audits),
                        "events_per_flight": 1_968, "event_count_total": 144 * 1_968, "rows": event_audits},
        "learned_initial_weight_integrity": {
            "raw_field": "log.stage1_position_weight_initial",
            "corrected_method_ids": sorted(v1.CORRECTED_METHODS),
            "checked_corrected_flights": len(initial_weight_audits),
            "corrected_method_rows": initial_weight_audits,
            "C5_initial_weight_check": "Covered by the independent C5/ablation event auditors on all 144 flights.",
            "B_initial_weight_check": "NOT_APPLICABLE_NO_LEARNED_HEAD",
        },
        "actuator_integrity": {"all_288_rows_finite_and_complete": True,
                               "required_channels": list(v1.REQUIRED_ACTUATOR_FIELDS),
                               "flight_channels": actuator_summary},
        "native_readiness_telemetry": {
            "definition": "Only actual stage1_position_event_inference_valid markers, valid-event timing, and selected native history_ready/model_call/timing arrays are summarized; event-valid is not continuous readiness. Disabled debug and B native_not_applicable remain explicit.",
            "by_method": native_by_method,
        },
        "timing_qualification": {
            **v1.TIE_AND_TIMING_SCOPE,
            "measurement_boundary": "Frozen controller_call_time_s ends before allocator, Plant and MAT save.",
            "method_block_order": list(EXPECTED_METHODS),
            "method_pause_and_failure_note": (
                "The original v3 DSSM startup and the v4 preparation both failed before Plant (OS1, 0 calls) and remain separate history. "
                "The isolated v4 path diagnostic then exited OS0 with zero Plant calls and is not a method block. "
                "The preserved v5 pre-Plant DEV2 failure, v6 one-VAL-Plant DEV2 failure, and v7/v8 zero-Plant prepare failures are disclosed separately. "
                "The v9 five-method blocks follow the successful fixed DEV2 replays and are the only new TEST combinations; process gaps and timestamps are retained above."
            ),
            "thread_argument_interpretation": "-singleCompThread sets MATLAB numerical-computation thread behavior; runtime worker threads may remain.",
            "sysnoise": "Sequential method processes; no OS-level timing isolation; initial calls/JIT effects included.",
            "formal_1khz_loop_claim": False,
            "natural_os_receipt_order_checked_before_mat_or_score_reads": True,
        },
        "serialization_scope": {
            "MATLAB_char_identity": "Actual scene/method/candidate/collector strings are checked through frozen char-field decoding.",
            "MATLAB_cells": "Frozen cell-safe decoder and record normalization remain unchanged.",
            "opaque_spec_table": "Only opaque integer storage-header equality is checked where spec is a MATLAB table; its table contents are not independently semantically decoded. Spec is saved metadata, not a controller input. B uses the unchanged pinned v1 representation check.",
            "opaque_table_semantic_equality_claimed": False,
            "frozen_input_metadata": "The original cfgpack and its metadata remain byte-frozen; corrected historical run_start references are a distinct manifest lineage, not replacement cfgpack bytes.",
        },
        "score_source": {"path": str(v1.SCORER.resolve()), "sha256": v1.EXPECTED_SHA256["scorer"]},
        "paper_gate_or_goal_decision": "NOT_AUTOMATED_BY_RAW_AUDIT",
    })


def verify_v4_source_files(manifest: dict, v1) -> dict[str, Any]:
    methods = manifest["methods"]
    method_ref_rows, model_ref_rows, unique = [], [], {}
    for method in methods:
        for key in ("input_lock_path", "run_contract_path", "cfg_opts_snapshot_path"):
            value = method.get(key, "")
            if value:
                path = canonical_path(value, v1)
                sha_field = key.replace("_path", "_sha256")
                v1.verify_file(path, method.get(sha_field, ""), f"{method['method_id']} {key}")
        for ref in method.get("source_refs", []):
            path, sha, role = ref_key(ref, v1)
            unique[path] = sha
            method_ref_rows.append({"method_id": method["method_id"], "path": str(canonical_path(ref["path"], v1)),
                                   "sha256": sha, "role": role})
        for ref in method.get("model_refs", []):
            path, sha, role = ref_key(ref, v1)
            unique[path] = sha
            model_ref_rows.append({"method_id": method["method_id"], "path": str(canonical_path(ref["path"], v1)),
                                   "sha256": sha, "role": role})
        runtime_path = method.get("runtime_tree_path", "")
        if runtime_path:
            resolved = canonical_path(runtime_path, v1)
            require(v1.sha256_tree_matlab(resolved).lower() == str(method.get("runtime_tree_sha256", "")).lower(),
                    f"v4 runtime tree SHA changed for {method['method_id']}")
    shared = manifest.get("shared_source_refs", [])
    for ref in shared:
        path, sha, role = ref_key(ref, v1)
        unique[path] = sha
        method_ref_rows.append({"method_id": "SHARED", "path": str(canonical_path(ref["path"], v1)),
                                "sha256": sha, "role": role})
    global_rows = []
    for ref in manifest.get("global_platform_refs", []):
        path, sha, role = ref_key(ref, v1)
        global_rows.append({"path": str(canonical_path(ref["path"], v1)), "sha256": sha, "role": role})
    require(len(unique) == 79, f"v4 unique source/model file count changed: {len(unique)}")
    return {"method_plus_shared_reference_count": len(method_ref_rows),
            "model_reference_count": len(model_ref_rows), "unique_code_and_model_file_count": len(unique),
            "method_and_shared_source_references": method_ref_rows,
            "model_references": model_ref_rows, "global_platform_references": global_rows}


def synthetic_self_check() -> dict[str, Any]:
    v1 = load_v1()
    inherited = {"path": str(V9_ENTRY), "sha256": sha256_file(V9_ENTRY), "role": "synthetic_existing_source"}
    helper_path = ROOT / "matlab" / "models" / "position_filter_realization_pcf_step_v3_5.m"
    helper = {"path": str(helper_path), "sha256": FILTER_HELPER_SHA256, "role": "active_pcf_filter_helper"}
    # Exercise the actual path/hash lineage guard using two existing source files only.
    assert_only_filter_helper_added([inherited], [inherited, helper], v1, "synthetic")
    rejected_extra = False
    try:
        assert_only_filter_helper_added([inherited], [inherited, helper, inherited], v1, "synthetic_with_extra_ref")
    except ValueError:
        rejected_extra = True
    require(rejected_extra, "Synthetic lineage guard accepted an extra duplicate source reference")
    v1_check = v1.self_check()
    require(v1_check.get("status") == "DEV_OR_SYNTHETIC_SELF_CHECK"
            and v1_check.get("TEST_accessed") is False, "Frozen v1 synthetic self-check failed")
    require(callable(verify_v3_failure_history) and callable(verify_v4_failure_and_path_diagnostic_history),
            "Historical v3/v4 failures and the v4 path diagnosis must remain separate audit paths")
    return {"schema": "DEV_OR_SYNTHETIC_SELF_CHECK_V1", "status": "DEV_OR_SYNTHETIC_SELF_CHECK",
            "TEST_accessed": False, "synthetic_only": True,
            "checks": {"mixed_method_order_count": len(EXPECTED_METHODS),
                       "v3_B_reuse_count": 1, "v9_unstarted_method_count": len(V4_METHODS),
                       "single_PCF_helper_addition": True, "unexpected_extra_reference_rejected": True,
                       "separate_historical_v3_v4_and_path_diagnostic_audit_paths_present": True,
                       "frozen_v1_timing_and_struct_checks": v1_check["checks"]},
            "note": "No TEST ID, TEST-shaped row, TEST raw, performance score, MATLAB, Plant, or training was used."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--self-check", action="store_true", help="run only the synthetic/in-memory check")
    group.add_argument("--output-json", type=Path, help="new final raw-audit JSON path inside the v4 reader folder")
    args = parser.parse_args()
    output_dir = Path(__file__).resolve().parent
    output_path = output_dir / "SELF_CHECK_DEV_OR_SYNTHETIC_v1.json" if args.self_check else args.output_json
    if not output_path.is_absolute():
        output_path = ROOT / output_path
    output_path = output_path.resolve()
    require(output_path.parent == output_dir.resolve(), f"Output must stay inside {output_dir}")
    require(not output_path.exists(), f"Refusing to overwrite existing output: {output_path}")
    if args.self_check:
        result = synthetic_self_check()
    else:
        result = run_review(output_path)
    serialized = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    output_path.write_text(serialized, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
