#!/usr/bin/env python3
"""REPAIR01 metadata-only preflight wrapper for the frozen C5_VAL48 scorer.

The wrapper installs the independent identity adapter into the frozen TRAIN
builder, then invokes only the original scorer's no-numeric-VAL preflight.
There is deliberately no score execution CLI path in this repair script.
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import importlib.util
import io
import json
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
DIAG = ROOT / "experiments/dl_attitude_replacement_20261027/mlp15_nominal_residual_v1/C5_VAL48_OFFLINE_DIAGNOSTIC_v1"
STUDY = DIAG.parent
ADAPTER_PATH = HERE / "metadata_identity_adapter_REPAIR01_v1.py"
REPAIR_LOCK_PATH = HERE / "REPAIR01_SCORE_LOCK_v1.json"
BASE_SCORER_PATH = DIAG / "score_c5_val48_once_v1.py"
BASE_SCORE_LOCK_PATH = DIAG / "C5_VAL48_SCORE_LOCK_v1.json"
AUDIT_JSON = HERE / "C5_VAL48_METADATA_AUDIT_REPAIR01_v1.json"
MAPPING_CSV = HERE / "C5_VAL48_IDENTITY_MAPPING_REPAIR01_v1.csv"
PREFLIGHT_RECEIPT = HERE / "C5_VAL48_PREFLIGHT_RECEIPT_REPAIR01_v1.json"
HASH_MANIFEST = HERE / "REPAIR01_HASH_MANIFEST_v1.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def write_new_json(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def canonical_path(path: Path) -> str:
    return os.path.normcase(os.path.normpath(str(path.resolve())))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def verify_repair_lock(lock: dict[str, Any]) -> None:
    if lock.get("schema") != "DL1018_MLP15_C5_VAL48_METADATA_REPAIR_LOCK_V1":
        raise ValueError("unexpected REPAIR01 lock schema")
    if lock.get("status") != "FROZEN_METADATA_ONLY_AWAITING_ROOT_REVIEW":
        raise ValueError("REPAIR01 lock is not frozen for metadata-only review")
    if lock.get("score_execution_authorized") is not False:
        raise ValueError("REPAIR01 must remain score-disabled")
    if sha256(Path(__file__).resolve()) != lock.get("repair_script_sha256"):
        raise ValueError("REPAIR01 wrapper SHA mismatch")
    if sha256(ADAPTER_PATH) != lock.get("adapter_script_sha256"):
        raise ValueError("REPAIR01 identity adapter SHA mismatch")
    if sha256(BASE_SCORER_PATH) != lock.get("base_scorer_sha256"):
        raise ValueError("frozen base scorer SHA mismatch")
    if sha256(BASE_SCORE_LOCK_PATH) != lock.get("base_score_lock_sha256"):
        raise ValueError("frozen base score lock SHA mismatch")
    for entry in lock.get("bound_files", []):
        path = ROOT / entry["path"]
        if sha256(path) != entry["sha256"]:
            raise ValueError(f"REPAIR01 bound file SHA mismatch: {entry['path']}")
    need = lock.get("required_schema_counts")
    if need != {
        "C5_TAIL11_RUN_IDENTITY_V2": 11,
        "C5_AXIS_COORDINATE_DEV72_RUN_IDENTITY_V3": 36,
        "C5_AXIS_COORDINATE_RUN_IDENTITY_V1": 1,
    } or lock.get("required_acc_fix_alias_count") != 16:
        raise ValueError("REPAIR01 lock schema/alias contract differs from reviewed metadata audit")


def write_mapping_csv(rows: list[dict[str, Any]]) -> None:
    if MAPPING_CSV.exists():
        raise FileExistsError(f"refusing to overwrite {MAPPING_CSV}")
    with MAPPING_CSV.open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            converted = dict(row)
            converted["coordinate_mask"] = json.dumps(converted["coordinate_mask"])
            writer.writerow(converted)


def run_preflight(args: argparse.Namespace) -> dict[str, Any]:
    repair_lock = read_json(REPAIR_LOCK_PATH)
    verify_repair_lock(repair_lock)
    for output in (AUDIT_JSON, MAPPING_CSV, PREFLIGHT_RECEIPT, HASH_MANIFEST):
        if output.exists():
            raise FileExistsError(f"REPAIR01 output already exists: {output}")

    adapter = load_module("metadata_identity_adapter_REPAIR01_v1", ADAPTER_PATH)
    audit = adapter.audit_all()
    context = adapter.load_context()
    rows = audit["rows"]
    hash_cache = {canonical_path(Path(path)): digest for path, digest in audit["hash_cache_for_preflight"].items()}

    # This is the same builder function the frozen scorer uses. Only its
    # identity gate is replaced; scoring is not enabled by this wrapper.
    sys.path.insert(0, str(STUDY))
    import prepare_train_data_v1 as train_builder
    train_builder.verify_run_identity = adapter.builder_verifier(context)

    # The frozen scorer's preflight hashes source bytes again. Reuse the fresh
    # hashes computed above for those exact paths; other files are hashed now.
    frozen_scorer = load_module("score_c5_val48_once_v1_frozen", BASE_SCORER_PATH)
    frozen_scorer.OUT = HERE
    original_sha = frozen_scorer.sha

    def sha_with_verified_source_cache(path: Path) -> str:
        key = canonical_path(Path(path))
        return hash_cache[key] if key in hash_cache else original_sha(Path(path))

    frozen_scorer.sha = sha_with_verified_source_cache
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        frozen_scorer.run(args.config, args.freeze_manifest, args.source_freeze,
                          args.identity_check, args.eval_rules, BASE_SCORE_LOCK_PATH,
                          preflight_only=True)
    base_result = json.loads(captured.getvalue().strip().splitlines()[-1])
    if base_result.get("status") != "PREFLIGHT_PASS" or base_result.get("numeric_VAL_arrays_read") is not False:
        raise ValueError("frozen scorer metadata preflight did not PASS")

    clean_audit = {key: value for key, value in audit.items() if key != "hash_cache_for_preflight"}
    clean_audit["adapter_script_path"] = str(ADAPTER_PATH.relative_to(ROOT)).replace("\\", "/")
    clean_audit["adapter_script_sha256"] = sha256(ADAPTER_PATH)
    write_new_json(AUDIT_JSON, clean_audit)
    write_mapping_csv(rows)

    receipt = {
        "schema": "DL1018_MLP15_C5_VAL48_METADATA_PREFLIGHT_RECEIPT_REPAIR01_V1",
        "status": "PASS_METADATA_ONLY_PREFLIGHT_AWAITING_ROOT_REVIEW",
        "repair_script_path": str(Path(__file__).resolve().relative_to(ROOT)).replace("\\", "/"),
        "repair_script_sha256": sha256(Path(__file__).resolve()),
        "adapter_script_path": str(ADAPTER_PATH.relative_to(ROOT)).replace("\\", "/"),
        "adapter_script_sha256": sha256(ADAPTER_PATH),
        "repair_lock_path": str(REPAIR_LOCK_PATH.relative_to(ROOT)).replace("\\", "/"),
        "repair_lock_sha256": sha256(REPAIR_LOCK_PATH),
        "base_scorer_path": str(BASE_SCORER_PATH.relative_to(ROOT)).replace("\\", "/"),
        "base_scorer_sha256": sha256(BASE_SCORER_PATH),
        "base_score_lock_sha256": sha256(BASE_SCORE_LOCK_PATH),
        "adapter_audit_status": audit["status"],
        "source_scene_count": audit["source_scene_count"],
        "schema_counts": audit["schema_counts"],
        "acc_fix_alias_count": audit["acc_fix_alias_count"],
        "reused_scene_count": audit["reused_scene_count"],
        "fresh_batch_scene_count": audit["fresh_batch_scene_count"],
        "all_144_raw_status_run_start_byte_hashes_match": audit["raw_status_run_start_byte_hashes_revalidated"],
        "base_scorer_preflight": base_result,
        "metadata_audit_path": str(AUDIT_JSON.relative_to(ROOT)).replace("\\", "/"),
        "metadata_mapping_path": str(MAPPING_CSV.relative_to(ROOT)).replace("\\", "/"),
        "numeric_log_or_command_arrays_opened": False,
        "numeric_VAL_features_or_labels_read": False,
        "checkpoint_weights_loaded_by_frozen_preflight": True,
        "score_start_marker_created": False,
        "scoring_started": False,
        "training_run": False,
        "TEST_accessed": False,
        "Plant_called": False,
        "closed_loop_run": False,
        "old_failed_score_marker_and_report_modified": False,
        "score_execution_authorized": False,
    }
    write_new_json(PREFLIGHT_RECEIPT, receipt)
    hashes = {
        "repair_wrapper": {"path": str(Path(__file__).resolve().relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(Path(__file__).resolve())},
        "identity_adapter": {"path": str(ADAPTER_PATH.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(ADAPTER_PATH)},
        "repair_lock": {"path": str(REPAIR_LOCK_PATH.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(REPAIR_LOCK_PATH)},
        "metadata_audit": {"path": str(AUDIT_JSON.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(AUDIT_JSON)},
        "identity_mapping_csv": {"path": str(MAPPING_CSV.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(MAPPING_CSV)},
        "preflight_receipt": {"path": str(PREFLIGHT_RECEIPT.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(PREFLIGHT_RECEIPT)},
    }
    write_new_json(HASH_MANIFEST, {"schema": "DL1018_MLP15_C5_VAL48_REPAIR01_HASH_MANIFEST_V1", "files": hashes})
    return {**receipt, "hash_manifest_path": str(HASH_MANIFEST.relative_to(ROOT)).replace("\\", "/"),
            "hash_manifest_sha256": sha256(HASH_MANIFEST)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight", action="store_true", required=True,
                        help="run identity/contract preflight only; scoring is disabled")
    parser.add_argument("--config", type=Path, default=STUDY / "TRAINING_CONFIG_v1r1.json")
    parser.add_argument("--freeze-manifest", type=Path, default=STUDY / "TRAINING_FREEZE_MANIFEST_v1r1.json")
    parser.add_argument("--source-freeze", type=Path, default=DIAG / "C5_VAL48_SOURCE_FREEZE_v1.json")
    parser.add_argument("--identity-check", type=Path, default=DIAG / "C5_VAL48_IDENTITY_CHECK_v1.json")
    parser.add_argument("--eval-rules", type=Path, default=DIAG / "C5_VAL48_EVAL_RULES_v1.json")
    args = parser.parse_args()
    result = run_preflight(args)
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
