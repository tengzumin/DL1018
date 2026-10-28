"""Exercise the trainer's release gate using in-memory fixtures only."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
TRAINER = "experiments/attitude_cm18_a1_20261024/train_cm18_a1_v1.py"
TRAINER_SHA256 = "7544a04329bc1e06ff5d7a113a077033a65f0b7c2de8a6f1b25ac54710e62c76"
RELEASE_SHA256 = "f" * 64
DATASET_SHA256 = "c" * 64


def load_trainer():
    path = ROOT / TRAINER
    if hashlib.sha256(path.read_bytes()).hexdigest() != TRAINER_SHA256:
        raise RuntimeError("trainer SHA256 differs from the reviewed source")
    spec = importlib.util.spec_from_file_location("cm18_trainer_gate_under_test", path)
    if spec is None or spec.loader is None:
        raise ImportError(TRAINER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def path_key(path: Path | str) -> str:
    return Path(path).as_posix()


def mock_manifest(module: object) -> dict:
    rows = []
    for split, count in (("TRAIN", 768), ("VAL", 48)):
        for index in range(count):
            rows.append({"scene_id": f"MOCK_{split}_{index:03d}", "split": split,
                         "qualified": True, "status": "PASS"})
    return {"schema": "CM18_A1_DATASET_MANIFEST_V1", "mode": "ALL816",
            "TEST_accessed": False, "rows": rows, "scene_count": 816,
            "qualified_count": 816, "failed_count": 0,
            "input_manifest_sha256": module.INPUT_MANIFEST_SHA256}


def base_fixture(module: object, release_path: Path) -> tuple[dict, dict, dict, dict, dict]:
    source_sha = {relative: hashlib.sha256(("mock:" + relative).encode()).hexdigest()
                  for relative in (module.TRAINER, module.READER, module.NUMPY_MODEL, module.TORCH_MODEL)}
    taskbook_sha, audit_sha = "b" * 64, "a" * 64
    pseudo = lambda relative: (Path("__CM18_IN_MEMORY__") / relative).as_posix()
    audit = {
        "status": "PASS", "audit_mode": "ALL816",
        "dataset_counts": {"scenes": 816, "passed_cache_audits": 816,
                            "failed_cache_audits": 0,
                            "event_count_by_split": {"TRAIN": 768 * 1999, "VAL": 48 * 1999}},
        "dataset_manifest_sha256": DATASET_SHA256,
        "input_manifest_sha256_actual": module.INPUT_MANIFEST_SHA256,
    }
    manifest = mock_manifest(module)
    release = {
        "schema": "CM18_A1_TRAINING_RELEASE_V1",
        "decision": "APPROVE_ONE_FORMAL_TRAINING",
        "seed": module.SEED, "optimizer_steps": module.STEPS, "device": "cuda:0",
        "output_directory": module.FORMAL_OUTPUT, "gpu_background_rows": [],
        "source_files": [{"path": path, "sha256": digest} for path, digest in source_sha.items()],
        "taskbook": {"path": module.TASKBOOK, "sha256": taskbook_sha},
        "data_audit": {"path": module.AUDIT, "sha256": audit_sha},
        "input_manifest": {"path": module.INPUT_MANIFEST,
                            "sha256": module.INPUT_MANIFEST_SHA256},
        "dataset_manifest": {"path": "__CM18_IN_MEMORY__/ALL816_manifest.json",
                             "sha256": DATASET_SHA256},
    }
    objects = {
        path_key(release_path): release,
        pseudo(module.AUDIT): audit,
        pseudo("__CM18_IN_MEMORY__/ALL816_manifest.json"): manifest,
    }
    hashes = {
        path_key(release_path): RELEASE_SHA256,
        pseudo(module.AUDIT): audit_sha,
        pseudo(module.TASKBOOK): taskbook_sha,
        pseudo(module.INPUT_MANIFEST): module.INPUT_MANIFEST_SHA256,
        pseudo("__CM18_IN_MEMORY__/ALL816_manifest.json"): DATASET_SHA256,
    }
    hashes.update({pseudo(path): digest for path, digest in source_sha.items()})
    return release, audit, manifest, objects, hashes


def main() -> int:
    module = load_trainer()
    release_path = Path(__file__).resolve(strict=True)
    original = (module._load_json, module._sha256, module._safe_path)
    cases = []

    def exercise(name: str, mutate, expected_error: str | None) -> None:
        release, audit, manifest, objects, hashes = base_fixture(module, release_path)
        mutate(release, audit, manifest)
        module._load_json = lambda path: copy.deepcopy(objects[path_key(path)])
        module._sha256 = lambda path: hashes[path_key(path)]
        module._safe_path = lambda root, relative: Path("__CM18_IN_MEMORY__") / relative
        try:
            pinned, checked_manifest = module._check_release(ROOT, release_path, RELEASE_SHA256)
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            if expected_error is None or expected_error not in message:
                raise AssertionError(f"{name}: unexpected rejection: {message}") from exc
            cases.append({"case": name, "result": "REJECTED_AS_EXPECTED", "error": message})
            return
        if expected_error is not None:
            raise AssertionError(f"{name}: expected rejection containing {expected_error!r}")
        if pinned["dataset_manifest_sha256"] != DATASET_SHA256 or len(checked_manifest["rows"]) != 816:
            raise AssertionError(f"{name}: accepted fixture did not preserve the ALL816 identity")
        cases.append({"case": name, "result": "ACCEPTED_AS_EXPECTED",
                      "dataset_scenes": len(checked_manifest["rows"])})

    try:
        exercise("valid_nested_ALL816", lambda r, a, m: None, None)
        exercise("SCREEN4_audit", lambda r, a, m: a.update(audit_mode="SCREEN4"),
                 "must be PASS for ALL816")
        exercise("failed_cache_count", lambda r, a, m: a["dataset_counts"].update(
            passed_cache_audits=815, failed_cache_audits=1), "pass all 816 cache audits")
        exercise("wrong_dataset_manifest_SHA", lambda r, a, m: a.update(
            dataset_manifest_sha256="d" * 64), "dataset manifest identity mismatch")
        exercise("wrong_release_input_SHA", lambda r, a, m: r["input_manifest"].update(
            sha256="0" * 64), "does not match the frozen identity")
        exercise("wrong_audit_input_SHA", lambda r, a, m: a.update(
            input_manifest_sha256_actual="0" * 64), "audit input manifest identity mismatch")
        exercise("wrong_split_event_count", lambda r, a, m: a["dataset_counts"][
            "event_count_by_split"].update(VAL=48 * 1999 - 1), "event counts do not match")
    finally:
        module._load_json, module._sha256, module._safe_path = original

    report = {
        "status": "PASS", "trainer_path": TRAINER, "trainer_sha256": TRAINER_SHA256,
        "scope": "_check_release only; all release/audit/manifest objects and file hashes are in-memory mocks",
        "all816_manifest_or_cache_read": False, "release_file_created": False,
        "optimizer_calls": 0, "cases": cases,
    }
    output = Path(__file__).with_name("ROOT_RELEASE_GATE_MOCK_CHECK_v1.json")
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": report["status"], "cases": len(cases),
                      "output": output.relative_to(ROOT).as_posix(),
                      "optimizer_calls": 0, "all816_manifest_or_cache_read": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
