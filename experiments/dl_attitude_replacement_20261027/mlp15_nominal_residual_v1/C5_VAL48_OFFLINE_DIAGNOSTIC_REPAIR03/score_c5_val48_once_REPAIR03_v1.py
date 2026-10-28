from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
DIAG = STUDY / "C5_VAL48_OFFLINE_DIAGNOSTIC_v1"
REPAIR01 = STUDY / "C5_VAL48_OFFLINE_DIAGNOSTIC_REPAIR01"
ADAPTER_PATH = REPAIR01 / "metadata_identity_adapter_REPAIR01_v1.py"
SCORE_PATH = DIAG / "score_c5_val48_once_v1.py"
LOCK_PATH = HERE / "C5_VAL48_SCORE_LOCK_REPAIR03_v1.json"
RECEIPT_PATH = HERE / "REPAIR03_EXECUTION_RECEIPT_v1.json"
FAILURE_PATH = HERE / "REPAIR03_EXECUTION_FAILURE_v1.json"
OUTPUTS = (
    "C5_VAL48_SCORE_STARTED_v1.json", "VAL_BUILD_PROGRESS_v1.jsonl",
    "VAL_CAUSAL_GATE_v1.json", "C5_VAL48_RESIDUAL_DIAGNOSTIC_v1.npz",
    "C5_VAL48_SCORE_RESULT_v1.json", "C5_VAL48_SCORE_SUMMARY_v1.json",
    "C5_VAL48_DIAGNOSTIC_RECEIPT_v1.json",
)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def canonical_path(path: Path) -> str:
    return os.path.normcase(os.path.normpath(str(path.resolve())))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main() -> None:
    if any((HERE / name).exists() for name in (*OUTPUTS, RECEIPT_PATH.name, FAILURE_PATH.name)):
        raise FileExistsError("REPAIR03 one-shot score output already exists")
    adapter = load_module("metadata_identity_adapter_REPAIR03_v1", ADAPTER_PATH)
    audit = adapter.audit_all()
    if (audit.get("status") != "PASS_METADATA_ONLY_IDENTITY_ADAPTER"
            or audit.get("source_scene_count") != 48
            or audit.get("raw_status_run_start_byte_hashes_revalidated") is not True
            or audit.get("numeric_log_or_command_arrays_opened") is not False
            or audit.get("numeric_VAL_features_or_labels_read") is not False):
        raise RuntimeError("REPAIR03 metadata-only identity audit failed")
    context = adapter.load_context()
    sys.path.insert(0, str(STUDY))
    import prepare_train_data_v1 as builder
    builder.verify_run_identity = adapter.builder_verifier(context)
    scorer = load_module("score_c5_val48_REPAIR03_frozen", SCORE_PATH)
    scorer.OUT = HERE
    old_sha = scorer.sha
    cache = {canonical_path(Path(p)): v for p, v in audit["hash_cache_for_preflight"].items()}

    def sha_with_verified_cache(path: Path) -> str:
        key = canonical_path(Path(path))
        return cache[key] if key in cache else old_sha(Path(path))

    scorer.sha = sha_with_verified_cache
    config = STUDY / "TRAINING_CONFIG_v1r1.json"
    freeze = STUDY / "TRAINING_FREEZE_MANIFEST_v1r1.json"
    source = DIAG / "C5_VAL48_SOURCE_FREEZE_v1.json"
    identity = DIAG / "C5_VAL48_IDENTITY_CHECK_v1.json"
    rules = DIAG / "C5_VAL48_EVAL_RULES_v1.json"
    captured = io.StringIO()
    try:
        with contextlib.redirect_stdout(captured):
            scorer.run(config, freeze, source, identity, rules, LOCK_PATH, preflight_only=True)
        preflight = json.loads(captured.getvalue().strip().splitlines()[-1])
        if (preflight.get("status") != "PREFLIGHT_PASS"
                or preflight.get("source_scenes") != 48
                or preflight.get("identity_files_checked") != 144
                or preflight.get("all_identity_hashes_match") is not True
                or preflight.get("numeric_VAL_arrays_read") is not False
                or preflight.get("score_start_marker_created") is not False):
            raise RuntimeError("frozen scorer preflight failed")
        print(json.dumps({"status": "PREFLIGHT_PASS", "scenes": 48,
                          "identity_files_checked": 144, "numeric_VAL_arrays_read": False,
                          "checkpoint_sha256": preflight["checkpoint_sha256"],
                          "score_script_sha256": preflight["score_script_sha256"]}), flush=True)
        scorer.run(config, freeze, source, identity, rules, LOCK_PATH, preflight_only=False)
        summary = json.loads((HERE / "C5_VAL48_SCORE_SUMMARY_v1.json").read_text(encoding="utf-8"))
        receipt = {
            "schema": "DL1018_MLP15_C5_VAL48_EXECUTION_RECEIPT_REPAIR03_V1",
            "status": "PASS_ONE_SHOT_OFFLINE_SCORE_REPAIR03",
            "executor_sha256": sha(Path(__file__).resolve()),
            "base_scorer_sha256": sha(SCORE_PATH),
            "score_lock_sha256": sha(LOCK_PATH),
            "checkpoint_sha256": preflight["checkpoint_sha256"],
            "source_scene_count": 48,
            "identity_files_checked": 144,
            "preflight_status": preflight["status"],
            "score_summary": summary,
            "validation_used_for_fit": False,
            "training_run": False,
            "TEST_accessed": False,
            "Plant_called": False,
            "closed_loop_run": False,
        }
        RECEIPT_PATH.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps(receipt, ensure_ascii=False), flush=True)
    except Exception as exc:
        if any((HERE / name).exists() for name in OUTPUTS):
            FAILURE_PATH.write_text(json.dumps({
                "schema": "DL1018_MLP15_C5_VAL48_EXECUTION_FAILURE_REPAIR03_V1",
                "status": "ONE_SHOT_INTERRUPTED_NO_SCORE_CLAIM",
                "error": f"{type(exc).__name__}: {exc}",
                "score_started": (HERE / OUTPUTS[0]).exists(),
                "progress_bytes": (HERE / OUTPUTS[1]).stat().st_size if (HERE / OUTPUTS[1]).exists() else 0,
                "TEST_accessed": False, "Plant_called": False, "training_run": False,
            }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        raise


if __name__ == "__main__":
    main()
