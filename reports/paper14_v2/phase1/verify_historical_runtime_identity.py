#!/usr/bin/env python3
"""Read-only audit of archived DSSM run identities and missing B runtime bindings."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ARCHIVE = ROOT.parent / "REFERENCE_FIX_FULL72_20261021_022342_313" / "corrected_reference_training_v1"
LINEAGE = ROOT / "reports" / "paper14_v2" / "phase1" / "mechanism_run_start_lineage.csv"
DSSM_METHOD = "CORRECTED_TRAIN_DSSM14_G12_R32"
SESSIONS = ("corrected_pair_eval_v1", "corrected_pair_eval_tail21_v1")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def frozen_runtime_tree(root: Path) -> tuple[int, str]:
    # Match the archived MATLAB sha256_tree implementation: sort by name and
    # hash absolute path, file SHA-256, and newline for every .m file.
    files = sorted(root.rglob("*.m"), key=lambda path: path.name)
    payload = "".join(f"{path.resolve()}:{sha256(path)}\n" for path in files)
    return len(files), hashlib.sha256(payload.encode("utf-8")).hexdigest()


def main() -> None:
    if not ARCHIVE.is_dir():
        raise FileNotFoundError(f"required read-only sibling archive not found: {ARCHIVE}")
    lineage = read_csv(LINEAGE)
    if len(lineage) != 72 or len({row["raw_sha256"].lower() for row in lineage}) != 72:
        raise AssertionError("expected 72 unique frozen DSSM lineage raw SHA values")

    frozen_ids = {}
    for session in SESSIONS:
        identity_path = ARCHIVE / session / "reports" / "PAIR_EVAL_FROZEN_IDENTITIES.json"
        identity = read_json(identity_path)
        if identity.get("status") != "PASS_FROZEN_PAIR_EVAL_IDENTITIES":
            raise AssertionError(f"frozen identity gate failed: {identity_path}")
        frozen_ids[session] = identity["identities"]["runtime_tree_sha256"].lower()

    status_by_raw: dict[str, tuple[dict, Path, str]] = {}
    session_counts = {session: 0 for session in SESSIONS}
    for session in SESSIONS:
        for status_path in (ARCHIVE / session / "runs").rglob("run_status.json"):
            status = read_json(status_path)
            if (status.get("method_id") != DSSM_METHOD
                    or status.get("status") != "RUN_COMPLETE_STABLE"
                    or not status.get("raw_sha256")):
                continue
            raw_sha = status["raw_sha256"].lower()
            if raw_sha in status_by_raw:
                raise AssertionError(f"duplicate DSSM raw identity: {status_path}")
            status_by_raw[raw_sha] = (status, status_path, session)
            session_counts[session] += 1

    expected_counts = {"corrected_pair_eval_v1": 61, "corrected_pair_eval_tail21_v1": 11}
    if session_counts != expected_counts or len(status_by_raw) != 72:
        raise AssertionError(f"unexpected stable DSSM status counts: {session_counts}")

    for row in lineage:
        raw_sha = row["raw_sha256"].lower()
        if raw_sha not in status_by_raw:
            raise AssertionError(f"no archived stable status for {row['scene_id']}")
        status, _, session = status_by_raw[raw_sha]
        expected_tree = frozen_ids[session]
        if (status.get("runtime_status") != "STABLE" or not status.get("complete")
                or not status.get("finite") or status.get("runtime_tree_sha256", "").lower() != expected_tree
                or status.get("model_id") != row["run_start_model_id"]
                or status.get("model_sha256", "").lower() != row["run_start_model_sha256"].lower()
                or status.get("source_scene_id") != row["run_start_source_scene_id"]
                or status.get("runtime_scene_id") != row["run_start_runtime_scene_id"]):
            raise AssertionError(f"run_status/lineage identity mismatch: {row['scene_id']}")
        run_start = Path(row["run_start_path"])
        if (not run_start.is_file()
                or sha256(run_start) != row["run_start_sha256_before"].lower()
                or row["run_start_sha256_before"].lower() != row["run_start_sha256_after"].lower()):
            raise AssertionError(f"run_start byte SHA mismatch: {row['scene_id']}")

    tree_results = {}
    for session in SESSIONS:
        count, digest = frozen_runtime_tree(ARCHIVE / session / "sources" / "local_runtime")
        if count != 8 or digest != frozen_ids[session]:
            raise AssertionError(f"archived source tree hash mismatch: {session}")
        tree_results[session] = {"m_file_count": count, "runtime_tree_sha256": digest}

    # The baseline ledger has row-level raw/run_start identities but no
    # runtime-tree column; report the historical code gap without guessing.
    baseline = read_csv(ARCHIVE / SESSIONS[0] / "manifests" / "PAIR_EVAL_BASELINE_REUSE_288.csv")
    b_rows = [row for row in baseline if row.get("method_id") == "B"]
    if (len(b_rows) != 72 or any(not row.get("raw_sha256") or not row.get("source_run_start_sha256")
                                 or row.get("model_id") != "B" for row in b_rows)
            or "runtime_tree_sha256" in baseline[0]):
        raise AssertionError("unexpected B baseline manifest schema or row count")

    output = {
        "status": "PASS_DSSM72_IDENTITY_B_UNCLOSED",
        "dssm_scene_count": len(lineage),
        "dssm_status_counts": session_counts,
        "dssm_runtime_tree_hashes": tree_results,
        "dssm_run_start_byte_sha_matches": 72,
        "b_manifest_rows": len(b_rows),
        "b_per_run_runtime_tree_sha_present": False,
        "raw_run_mat_opened": False,
        "test_accessed": False,
        "plant_or_training_started": False,
        "note": "Run-start files were hashed as opaque bytes; no MAT variables or raw_run.mat contents were read.",
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
