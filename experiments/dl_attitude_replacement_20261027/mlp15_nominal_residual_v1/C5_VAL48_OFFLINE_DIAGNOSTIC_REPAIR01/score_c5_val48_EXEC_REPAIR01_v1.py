#!/usr/bin/env python3
"""Single-use, root-gated executor for the frozen C5_VAL48 offline score.

This file is preparation only until REPAIR01_EXECUTION_LOCK_v1.json is
explicitly changed by root to ROOT_RELEASED_FOR_ONE_SHOT_SCORE with
score_execution_authorized=true. It never trains, uses TEST, calls Plant, or
runs closed-loop code. When released, it repeats metadata audit and the frozen
scorer preflight, then invokes the frozen scorer exactly once.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
DIAG = ROOT / "experiments/dl_attitude_replacement_20261027/mlp15_nominal_residual_v1/C5_VAL48_OFFLINE_DIAGNOSTIC_v1"
STUDY = DIAG.parent
EXECUTOR_PATH = Path(__file__).resolve()
EXECUTION_LOCK_PATH = HERE / "REPAIR01_EXECUTION_LOCK_v1.json"
ADAPTER_PATH = HERE / "metadata_identity_adapter_REPAIR01_v1.py"
PREFLIGHT_WRAPPER_PATH = HERE / "score_c5_val48_REPAIR01_v1.py"
REPAIR_SCORE_LOCK_PATH = HERE / "REPAIR01_SCORE_LOCK_v1.json"
BASE_SCORER_PATH = DIAG / "score_c5_val48_once_v1.py"
BASE_SCORE_LOCK_PATH = DIAG / "C5_VAL48_SCORE_LOCK_v1.json"
ROOT_REVIEW_PATH = STUDY / "ROOT_VAL48_REPAIR01_REVIEW_v1.md"
ADDENDUM05_PATH = STUDY / "TASKBOOK_ROOT_v1_ADDENDUM05.md"

SCORE_OUTPUT_NAMES = (
    "C5_VAL48_SCORE_STARTED_v1.json",
    "VAL_BUILD_PROGRESS_v1.jsonl",
    "VAL_CAUSAL_GATE_v1.json",
    "C5_VAL48_RESIDUAL_DIAGNOSTIC_v1.npz",
    "C5_VAL48_SCORE_RESULT_v1.json",
    "C5_VAL48_SCORE_SUMMARY_v1.json",
    "C5_VAL48_DIAGNOSTIC_RECEIPT_v1.json",
)
EXECUTION_LOG = HERE / "REPAIR01_EXECUTION_LOG_v1.txt"
EXECUTION_RECEIPT = HERE / "REPAIR01_EXECUTION_RECEIPT_v1.json"
EXECUTION_HASHES = HERE / "REPAIR01_EXECUTION_HASHES_v1.json"

EXPECTED = {
    "root_review_sha256": "cb6942fb15fdec8bc6ae006d519ec13a3b17cd7023a7621063096e104a55acb8",
    "addendum05_sha256": "c021b25451677458c7e4e750b4bc502ebaa6b62470c6b86e320e541c784b35b5",
    "checkpoint_sha256": "9c924f1566447644287595253026e035b2fcb716a57be0e60d6f04bafdd8ed74",
    "matlab_weights_sha256": "dfbad11dbc7ed19b42d3b536bb4b019cbf29209d69c904b0b5000a168af58819",
    "eval_rules_sha256": "85011ab4c15c41f227a81eb810149c976a09547b67e7bcf847b486bd8657e627",
}


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


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def verify_execution_lock(lock: dict[str, Any]) -> None:
    require(lock.get("schema") == "DL1018_MLP15_C5_VAL48_EXECUTION_LOCK_V1",
            "unexpected execution lock schema")
    require(lock.get("status") in ("FROZEN_AWAITING_ROOT_EXECUTION_REVIEW",
                                    "ROOT_RELEASED_FOR_ONE_SHOT_SCORE"),
            "execution lock status is invalid")
    require(lock.get("executor_script_sha256") == sha256(EXECUTOR_PATH),
            "executor script SHA mismatch")
    expected_paths = {
        "executor_script_path": EXECUTOR_PATH.relative_to(ROOT).as_posix(),
        "adapter_script_path": ADAPTER_PATH.relative_to(ROOT).as_posix(),
        "preflight_wrapper_path": PREFLIGHT_WRAPPER_PATH.relative_to(ROOT).as_posix(),
        "repair_score_lock_path": REPAIR_SCORE_LOCK_PATH.relative_to(ROOT).as_posix(),
        "base_scorer_path": BASE_SCORER_PATH.relative_to(ROOT).as_posix(),
        "base_score_lock_path": BASE_SCORE_LOCK_PATH.relative_to(ROOT).as_posix(),
        "output_directory": HERE.relative_to(ROOT).as_posix(),
    }
    for key, value in expected_paths.items():
        require(lock.get(key) == value, f"execution lock {key} mismatch")
    require(lock.get("root_review_path") == ROOT_REVIEW_PATH.relative_to(ROOT).as_posix()
            and lock.get("root_review_sha256") == EXPECTED["root_review_sha256"]
            and sha256(ROOT_REVIEW_PATH) == EXPECTED["root_review_sha256"],
            "root repair review path/SHA mismatch")
    require(lock.get("addendum05_path") == ADDENDUM05_PATH.relative_to(ROOT).as_posix()
            and lock.get("addendum05_sha256") == EXPECTED["addendum05_sha256"]
            and sha256(ADDENDUM05_PATH) == EXPECTED["addendum05_sha256"],
            "ADDENDUM05 path/SHA mismatch")
    require(lock.get("score_execution_authorized") is True,
            "executor is prepared but score execution has not been released by root")
    require(lock.get("one_shot_score_count") == 1 and lock.get("preflight_then_score_same_call") is True,
            "execution lock does not bind the one-shot sequence")
    require(lock.get("score_output_names") == list(SCORE_OUTPUT_NAMES)
            and lock.get("executor_output_names") == [EXECUTION_LOG.name, EXECUTION_RECEIPT.name, EXECUTION_HASHES.name]
            and lock.get("refuse_if_any_output_exists") is True and lock.get("no_overwrite") is True,
            "execution lock output inventory/one-shot guard mismatch")
    require(lock.get("checkpoint_sha256") == EXPECTED["checkpoint_sha256"]
            and lock.get("matlab_weights_sha256") == EXPECTED["matlab_weights_sha256"]
            and lock.get("eval_rules_sha256") == EXPECTED["eval_rules_sha256"],
            "execution lock candidate or evaluation binding changed")
    require(lock.get("plant_authorized") is False and lock.get("TEST_accessed") is False
            and lock.get("training_run") is False and lock.get("closed_loop_run") is False,
            "execution lock contains a prohibited action")
    for entry in lock.get("bound_files", []):
        path = ROOT / entry["path"]
        if not path.is_file() or sha256(path) != entry["sha256"]:
            raise ValueError(f"execution-lock bound SHA mismatch: {entry['path']}")
    require(lock.get("adapter_script_sha256") == sha256(ADAPTER_PATH), "adapter SHA mismatch")
    require(lock.get("preflight_wrapper_sha256") == sha256(PREFLIGHT_WRAPPER_PATH),
            "metadata preflight wrapper SHA mismatch")
    require(lock.get("repair_score_lock_sha256") == sha256(REPAIR_SCORE_LOCK_PATH),
            "REPAIR01 metadata lock SHA mismatch")
    require(lock.get("base_scorer_sha256") == sha256(BASE_SCORER_PATH), "base scorer SHA mismatch")
    require(lock.get("base_score_lock_sha256") == sha256(BASE_SCORE_LOCK_PATH),
            "base scorer lock SHA mismatch")
    base_lock = read_json(BASE_SCORE_LOCK_PATH)
    critical = {
        base_lock["source_freeze_manifest_path"]: base_lock["source_freeze_manifest_sha256"],
        base_lock["identity_check_path"]: base_lock["identity_check_sha256"],
        base_lock["eval_rules_path"]: base_lock["eval_rules_sha256"],
        base_lock["training_config_path"]: base_lock["training_config_sha256"],
        base_lock["training_freeze_manifest_path"]: base_lock["training_freeze_manifest_sha256"],
        base_lock["checkpoint_path"]: base_lock["checkpoint_sha256"],
        base_lock["matlab_weights_path"]: base_lock["matlab_weights_sha256"],
        base_lock["source_lock_path"]: base_lock["source_lock_sha256"],
    }
    locked_files = {item["path"]: item["sha256"] for item in lock.get("bound_files", [])}
    for path, digest in critical.items():
        require(locked_files.get(path) == digest, f"execution lock omitted base-critical input: {path}")


def refuse_existing_outputs() -> None:
    existing = [HERE / name for name in SCORE_OUTPUT_NAMES]
    existing.extend((EXECUTION_LOG, EXECUTION_RECEIPT, EXECUTION_HASHES))
    present = [str(path) for path in existing if path.exists()]
    if present:
        raise FileExistsError("one-shot REPAIR01 score output already exists: " + ", ".join(present))


class Tee(io.TextIOBase):
    def __init__(self, *streams):
        self.streams = streams

    def write(self, value: str) -> int:
        for stream in self.streams:
            stream.write(value)
            stream.flush()
        return len(value)

    def flush(self) -> None:
        for stream in self.streams:
            stream.flush()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-once", action="store_true", required=True,
                        help="execute the one-shot score only after root changes the execution lock to authorized")
    parser.add_argument("--config", type=Path, default=STUDY / "TRAINING_CONFIG_v1r1.json")
    parser.add_argument("--freeze-manifest", type=Path, default=STUDY / "TRAINING_FREEZE_MANIFEST_v1r1.json")
    parser.add_argument("--source-freeze", type=Path, default=DIAG / "C5_VAL48_SOURCE_FREEZE_v1.json")
    parser.add_argument("--identity-check", type=Path, default=DIAG / "C5_VAL48_IDENTITY_CHECK_v1.json")
    parser.add_argument("--eval-rules", type=Path, default=DIAG / "C5_VAL48_EVAL_RULES_v1.json")
    args = parser.parse_args()

    execution_lock = read_json(EXECUTION_LOCK_PATH)
    verify_execution_lock(execution_lock)
    refuse_existing_outputs()

    adapter = load_module("metadata_identity_adapter_REPAIR01_v1", ADAPTER_PATH)
    audit = adapter.audit_all()
    require(audit.get("status") == "PASS_METADATA_ONLY_IDENTITY_ADAPTER"
            and audit.get("source_scene_count") == 48
            and audit.get("raw_status_run_start_byte_hashes_revalidated") is True,
            "REPAIR01 metadata audit failed")
    context = adapter.load_context()
    hash_cache = {canonical_path(Path(path)): digest for path, digest in audit["hash_cache_for_preflight"].items()}

    # Install only the identity gate replacement; build_scene and scoring logic
    # remain the original frozen implementations.
    sys.path.insert(0, str(STUDY))
    import prepare_train_data_v1 as train_builder
    train_builder.verify_run_identity = adapter.builder_verifier(context)
    frozen_scorer = load_module("score_c5_val48_once_v1_frozen", BASE_SCORER_PATH)
    frozen_scorer.OUT = HERE
    original_sha = frozen_scorer.sha

    def sha_with_audited_source_cache(path: Path) -> str:
        key = canonical_path(Path(path))
        return hash_cache[key] if key in hash_cache else original_sha(Path(path))

    frozen_scorer.sha = sha_with_audited_source_cache
    base_lock = BASE_SCORE_LOCK_PATH
    preflight_output = io.StringIO()
    with contextlib.redirect_stdout(preflight_output):
        frozen_scorer.run(args.config, args.freeze_manifest, args.source_freeze,
                          args.identity_check, args.eval_rules, base_lock,
                          preflight_only=True)
    preflight = json.loads(preflight_output.getvalue().strip().splitlines()[-1])
    require(preflight.get("status") == "PREFLIGHT_PASS"
            and preflight.get("source_scenes") == 48
            and preflight.get("identity_files_checked") == 144
            and preflight.get("all_identity_hashes_match") is True
            and preflight.get("numeric_VAL_arrays_read") is False
            and preflight.get("score_start_marker_created") is False,
            "frozen base scorer metadata preflight failed")
    refuse_existing_outputs()

    started_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    score_stdout = io.StringIO()
    score_error: str | None = None
    try:
        with EXECUTION_LOG.open("x", encoding="utf-8") as log:
            log.write(json.dumps({"status": "PREFLIGHT_PASS_SCORE_CALL_STARTING",
                                  "started_utc": started_utc,
                                  "base_scorer_sha256": sha256(BASE_SCORER_PATH),
                                  "execution_lock_sha256": sha256(EXECUTION_LOCK_PATH)}) + "\n")
            log.flush()
            tee = Tee(sys.stdout, log, score_stdout)
            with contextlib.redirect_stdout(tee):
                # The only numerical scoring call in this executor.
                frozen_scorer.run(args.config, args.freeze_manifest, args.source_freeze,
                                  args.identity_check, args.eval_rules, base_lock,
                                  preflight_only=False)
    except Exception as exc:
        score_error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        # A failed one-shot remains visible as the original scorer's partial
        # outputs/log; this executor never retries or clears them.
        if score_error:
            sys.stderr.write(f"REPAIR01 one-shot score failed: {score_error}\n")

    score_result_path = HERE / "C5_VAL48_SCORE_RESULT_v1.json"
    summary_path = HERE / "C5_VAL48_SCORE_SUMMARY_v1.json"
    base_receipt_path = HERE / "C5_VAL48_DIAGNOSTIC_RECEIPT_v1.json"
    causal_gate_path = HERE / "VAL_CAUSAL_GATE_v1.json"
    for path in (score_result_path, summary_path, base_receipt_path, causal_gate_path):
        require(path.is_file(), f"frozen scorer omitted expected output: {path.name}")
    score_result = read_json(score_result_path)
    score_summary = read_json(summary_path)
    base_receipt = read_json(base_receipt_path)
    causal_gate = read_json(causal_gate_path)
    require(score_result.get("status") == "PASS_ONE_SHOT_OFFLINE_SCORE"
            and score_result.get("scene_count") == 48 and score_result.get("event_count") == 95_952,
            "frozen scorer result does not show exactly one complete VAL48 score")
    require(score_summary.get("scores_completed") == 1 and score_summary.get("scene_count") == 48
            and score_summary.get("event_count") == 95_952,
            "score summary does not show exactly one complete VAL48 score")
    require(base_receipt.get("validation_score_count") == 1
            and base_receipt.get("training_run") is False
            and base_receipt.get("TEST_accessed") is False
            and base_receipt.get("Plant_called") is False,
            "base diagnostic receipt failed one-shot/no-Plant/no-TEST checks")
    require(causal_gate.get("status") == "PASS_SCORE_COMPLETED"
            and causal_gate.get("scoring_started") is True
            and causal_gate.get("scores_completed") == 1
            and causal_gate.get("TEST_accessed") is False
            and causal_gate.get("Plant_called") is False,
            "causal gate receipt failed one-shot/no-Plant/no-TEST checks")

    output_hashes = {name: sha256(HERE / name) for name in SCORE_OUTPUT_NAMES}
    receipt = {
        "schema": "DL1018_MLP15_C5_VAL48_EXECUTION_RECEIPT_REPAIR01_V1",
        "status": "PASS_ONE_SHOT_OFFLINE_SCORE",
        "started_utc": started_utc,
        "executor_script_sha256": sha256(EXECUTOR_PATH),
        "execution_lock_sha256": sha256(EXECUTION_LOCK_PATH),
        "root_review_sha256": EXPECTED["root_review_sha256"],
        "addendum05_sha256": EXPECTED["addendum05_sha256"],
        "metadata_audit_status": audit["status"],
        "source_scene_count": audit["source_scene_count"],
        "schema_counts": audit["schema_counts"],
        "acc_fix_alias_count": audit["acc_fix_alias_count"],
        "preflight_status": preflight["status"],
        "preflight_numeric_VAL_arrays_read": preflight["numeric_VAL_arrays_read"],
        "score_call_count": 1,
        "checkpoint_sha256": EXPECTED["checkpoint_sha256"],
        "matlab_weights_sha256": EXPECTED["matlab_weights_sha256"],
        "eval_rules_sha256": EXPECTED["eval_rules_sha256"],
        "score_summary": score_summary,
        "score_result_sha256": output_hashes["C5_VAL48_SCORE_RESULT_v1.json"],
        "base_receipt_sha256": output_hashes["C5_VAL48_DIAGNOSTIC_RECEIPT_v1.json"],
        "execution_log_path": str(EXECUTION_LOG.relative_to(ROOT)).replace("\\", "/"),
        "execution_log_sha256": sha256(EXECUTION_LOG),
        "score_outputs_sha256": output_hashes,
        "numeric_VAL_read": True,
        "training_run": False,
        "TEST_accessed": False,
        "Plant_called": False,
        "closed_loop_run": False,
        "reused_validation_not_independent_test": True,
    }
    write_new_json(EXECUTION_RECEIPT, receipt)
    hash_manifest = {
        "schema": "DL1018_MLP15_C5_VAL48_EXECUTION_HASHES_REPAIR01_V1",
        "executor_script_sha256": sha256(EXECUTOR_PATH),
        "execution_lock_sha256": sha256(EXECUTION_LOCK_PATH),
        "execution_receipt_sha256": sha256(EXECUTION_RECEIPT),
        "execution_log_sha256": sha256(EXECUTION_LOG),
        "score_outputs_sha256": output_hashes,
    }
    write_new_json(EXECUTION_HASHES, hash_manifest)
    print(json.dumps({"status": receipt["status"], "score_call_count": 1,
                      "score_summary": score_summary,
                      "execution_receipt_sha256": sha256(EXECUTION_RECEIPT),
                      "execution_hashes_sha256": sha256(EXECUTION_HASHES)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
