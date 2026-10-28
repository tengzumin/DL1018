#!/usr/bin/env python3
"""Read-only reproducibility check for the FULL72 B/C5 source audit."""

import csv
import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SCORE_PATH = ROOT / "experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_full72_v1/audits/FULL72_PAIRED_SCORE_v1.json"
STUDY_MANIFEST_PATH = ROOT / "experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_full72_v1/MANIFEST.json"
B_PARENT_PATH = ROOT / "reports/paper_continuation_20261023/baseline_b_dev72_parent_review/PARENT_B72_RAW_REVIEW.json"
B_MANIFEST_PATH = ROOT / "reports/paper_continuation_20261023/baseline_b_dev72_parent_review/PARENT_TRACEABLE_B72_MANIFEST.json"
C5_PARENT_PATH = ROOT / "reports/paper_continuation_20261023/c5_dev72_parent_review/C5_DEV72_RAW_PARENT_REVIEW_v3.json"
C5_REUSE_AUDIT_PATH = ROOT / "reports/paper_continuation_20261023/c5_axis_coordinate_parent_review/screen12_parent_review/SUMMARY.json"
C5_DIR = ROOT / "experiments/position_axis_coordinate_c5_dev72_20261023"
C5_LOCK_PATH = C5_DIR / "C5_DEV72_INPUT_LOCK_v3.json"
C5_BATCH_PATH = C5_DIR / "C5_DEV72_BATCH_STATUS_v3.json"

errors = []


def check(condition, message):
    if not condition:
        errors.append(message)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def same_hash(actual, expected):
    return bool(expected) and actual.lower() == expected.lower()


def main():
    score = read_json(SCORE_PATH)
    study_manifest = read_json(STUDY_MANIFEST_PATH)
    b_parent = read_json(B_PARENT_PATH)
    b_manifest = read_json(B_MANIFEST_PATH)
    c5_parent = read_json(C5_PARENT_PATH)
    c5_reuse_audit = read_json(C5_REUSE_AUDIT_PATH)
    c5_lock = read_json(C5_LOCK_PATH)
    c5_batch = read_json(C5_BATCH_PATH)
    summary = read_json(HERE / "SUMMARY.json")
    with (HERE / "SCENE_SOURCE_AUDIT.csv").open(encoding="utf-8-sig", newline="") as stream:
        audited_rows = list(csv.DictReader(stream))

    score_rows = {row["scene_id"]: row for row in score["rows"]}
    manifest_rows = {row["scene_id"]: row for row in study_manifest["records"]}
    b_manifest_rows = {row["scene_id"]: row for row in b_manifest["rows"]}
    b_parent_rows = {row["scene_id"]: row for row in b_parent["comparisons"]}
    c5_parent_rows = {row["scene_id"]: row for row in c5_parent["rows"]}
    c5_event_rows = {row["scene_id"]: row for row in c5_parent["event_check_rows"]}
    c5_reuse_rows = {row["scene_id"]: row for row in c5_reuse_audit["audits"]}
    c5_lock_rows = {row["scene_id"]: row for row in c5_lock["scenes"]}
    c5_batch_rows = {row["scene_id"]: row for row in c5_batch.get("records", [])}
    scene_ids = list(score_rows)

    check(len(scene_ids) == 72 and len(set(scene_ids)) == 72, "score is not 72 unique scenes")
    for name, mapping in (("study manifest", manifest_rows), ("B manifest", b_manifest_rows),
                          ("B parent review", b_parent_rows), ("C5 parent review", c5_parent_rows),
                          ("C5 event audit", c5_event_rows), ("C5 input lock", c5_lock_rows)):
        check(set(mapping) == set(scene_ids), f"scene IDs differ in {name}")
    check(len(audited_rows) == 72 and len({row["scene_id"] for row in audited_rows}) == 72,
          "SCENE_SOURCE_AUDIT.csv is not 72 unique rows")
    output_rows = {row["scene_id"]: row for row in audited_rows}
    check(set(output_rows) == set(scene_ids), "CSV scene IDs differ from the locked 72-scene cohort")
    check(not any("TEST" in sid.upper() for sid in scene_ids), "unexpected TEST scene in score cohort")

    paths = {}
    for sid in scene_ids:
        b_row = b_manifest_rows[sid]
        c5_raw = Path(score_rows[sid]["methods"]["C5"]["raw_path"])
        for path in (Path(b_row["path"]), Path(b_row["status_path"]),
                     c5_raw, c5_raw.with_name("run_status.json")):
            paths[str(path)] = path
    missing = [str(path) for path in paths.values() if not path.is_file()]
    check(not missing, "missing locked DEV/VAL raw/status file(s): " + ", ".join(missing[:5]))
    if missing:
        print(json.dumps({"status": "FAIL", "errors": errors}, ensure_ascii=False, indent=2))
        return 1

    with ThreadPoolExecutor(max_workers=4) as pool:
        actual_hashes = dict(zip(paths, pool.map(sha256, paths.values())))

    for sid in scene_ids:
        scored = score_rows[sid]
        locked = manifest_rows[sid]
        bm = b_manifest_rows[sid]
        out = output_rows.get(sid, {})
        b = scored["methods"]["B"]
        c5 = scored["methods"]["C5"]
        b_raw, b_status = Path(bm["path"]), Path(bm["status_path"])
        c5_raw = Path(c5["raw_path"])
        c5_status = c5_raw.with_name("run_status.json")
        b_raw_sha, b_status_sha = actual_hashes[str(b_raw)], actual_hashes[str(b_status)]
        c5_raw_sha, c5_status_sha = actual_hashes[str(c5_raw)], actual_hashes[str(c5_status)]
        bs, cs = read_json(b_status), read_json(c5_status)
        ba, ca, event = b_parent_rows[sid], c5_parent_rows[sid], c5_event_rows[sid]
        reuse_audit = c5_reuse_rows.get(sid)
        lock_scene = c5_lock_rows[sid]
        batch_row = c5_batch_rows.get(sid)

        b_ok = all((
            b["raw_path"] == bm["path"] == locked["b_raw_path"],
            same_hash(b["raw_sha256"], bm["sha256"]) and same_hash(b["raw_sha256"], locked["b_raw_sha256"]),
            same_hash(b["status_sha256"], bm["status_sha256"]) and same_hash(b["status_sha256"], locked["b_status_sha256"]),
            same_hash(b_raw_sha, bm["sha256"]) and same_hash(b_status_sha, bm["status_sha256"]),
            same_hash(bs.get("raw_sha256", ""), b_raw_sha) and bs.get("scene_id") == sid,
            bs.get("status") == "RUN_COMPLETE_RAW_PENDING_AUDIT" and bs.get("log_status") == "STABLE",
            bs.get("transitions") == 20000 and bs.get("state_samples") == 20001,
            bs.get("TEST_accessed") is False and bs.get("training_steps") == 0 and bs.get("optimizer_steps") == 0,
            lock_scene["B72_scoring"]["raw_path"] == bm["path"],
            same_hash(lock_scene["B72_scoring"]["raw_sha256"], bm["sha256"]),
            lock_scene["B72_scoring"]["run_status_path"] == bm["status_path"],
            same_hash(lock_scene["B72_scoring"]["run_status_sha256"], bm["status_sha256"]),
            ba.get("numeric_arrays") == 33 and ba.get("all_arrays_equal") is True and not ba.get("differing_arrays") and ba.get("Q_new_minus_old_m") == 0.0,
            out.get("b_raw_path") == str(b_raw) and same_hash(out.get("b_raw_sha256_current", ""), b_raw_sha),
            out.get("b_status_path") == str(b_status) and same_hash(out.get("b_status_sha256_current", ""), b_status_sha),
            out.get("b_status") == bs.get("status") and out.get("b_log_status") == bs.get("log_status"),
            out.get("b_source_chain_pass") == "True" and out.get("b_check_failures") == "[]",
        ))

        scope = scored["c5_audit_scope"]
        expected_event_source = "DEV72_NEW_RAW_PARENT_RECOMPUTATION" if scope == "RAW_PENDING_PARENT_AUDIT" else "C5_SCREEN_PARENT_AUDIT_REUSED"
        expected_parent_status = "PASS_C5_RAW_ALL_EVENTS" if scope == "RAW_PENDING_PARENT_AUDIT" else "PASS_REUSED_C5_SCREEN_AUDIT"
        c5_parent_raw_sha = ca.get("raw_sha256", ca.get("C5_metrics", {}).get("sha256", ""))
        c5_parent_status_sha = ca.get("run_status_sha256", (reuse_audit or {}).get("run_status_sha256", ""))
        c5_ok = all((
            c5["raw_path"] == locked["c5_raw_path"],
            same_hash(c5["raw_sha256"], locked["c5_raw_sha256"]) and same_hash(c5["status_sha256"], locked["c5_status_sha256"]),
            same_hash(c5_raw_sha, locked["c5_raw_sha256"]) and same_hash(c5_status_sha, locked["c5_status_sha256"]),
            same_hash(cs.get("raw_sha256", ""), c5_raw_sha) and cs.get("scene_id") == sid,
            cs.get("status") == "RUN_COMPLETE_RAW_PENDING_AUDIT" and cs.get("log_status") == "STABLE",
            cs.get("transitions") == 20000 and cs.get("state_samples") == 20001,
            cs.get("TEST_accessed") is False and cs.get("training_steps") == 0 and cs.get("optimizer_steps") == 0,
            ca.get("status") == expected_parent_status and same_hash(c5_parent_raw_sha, c5_raw_sha),
            same_hash(c5_parent_status_sha, c5_status_sha) and ca.get("C5_metrics", {}).get("path") == str(c5_raw),
            (scope == "RAW_PENDING_PARENT_AUDIT" and reuse_audit is None) or
            (scope == "PARENT_SCREEN_REUSE" and reuse_audit is not None and reuse_audit.get("status") == "PASS_C5_RAW_ALL_EVENTS" and same_hash(reuse_audit.get("raw_sha256", ""), c5_raw_sha) and same_hash(reuse_audit.get("run_status_sha256", ""), c5_status_sha)),
            event.get("status") == expected_parent_status and event.get("source") == expected_event_source and event.get("event_count") == 1968,
            (sid not in set(c5_lock["scene_ids_new_60"])) or (batch_row is not None and batch_row.get("raw_path") == locked["c5_raw_path"] and same_hash(batch_row.get("raw_sha256", ""), locked["c5_raw_sha256"]) and batch_row.get("run_status_path") == locked["c5_status_path"] and same_hash(batch_row.get("run_status_sha256", ""), locked["c5_status_sha256"])),
            out.get("c5_raw_path") == str(c5_raw) and same_hash(out.get("c5_raw_sha256_current", ""), c5_raw_sha),
            out.get("c5_status_path") == str(c5_status) and same_hash(out.get("c5_status_sha256_current", ""), c5_status_sha),
            out.get("c5_status") == cs.get("status") and out.get("c5_log_status") == cs.get("log_status"),
            out.get("c5_parent_audit_status") == ca.get("status") and out.get("c5_event_audit_status") == event.get("status"),
            out.get("c5_event_source") == event.get("source") and int(out.get("c5_event_count", "0")) == event.get("event_count"),
            out.get("c5_source_chain_pass") == "True" and out.get("c5_check_failures") == "[]",
        ))
        scene_ok = b_ok and c5_ok
        check(b_ok, f"B source check failed for {sid}")
        check(c5_ok, f"C5 source check failed for {sid}")
        check(scene_ok and out.get("overall_scene_result") == "PASS" and not out.get("scene_gap"),
              f"CSV result/gap does not match recomputed result for {sid}")

    # Recheck every locked artifact digest represented in SUMMARY.json.
    score_bind = score["input_bindings"]
    b_lim = score["B_baseline_audit_limitation"]
    refs = summary["artifact_refs"]
    expected_refs = {
        "score_json": (SCORE_PATH, None),
        "score_study_manifest": (STUDY_MANIFEST_PATH, score_bind["manifest_sha256"]),
        "b_parent_raw_review": (B_PARENT_PATH, b_lim["parent_raw_review_sha256"]),
        "b_traceable_manifest": (B_MANIFEST_PATH, b_parent["manifest_sha256"]),
        "c5_parent_raw_review": (C5_PARENT_PATH, None),
        "c5_input_lock": (C5_LOCK_PATH, score_bind["c5_input_lock_sha256"]),
        "c5_batch_status": (C5_BATCH_PATH, score_bind["c5_batch_status_sha256"]),
    }
    for name, (path, bound_sha) in expected_refs.items():
        actual = sha256(path)
        recorded = refs[name]
        check(recorded["path"] == str(path.resolve()) and same_hash(recorded["sha256"], actual),
              f"SUMMARY artifact reference changed: {name}")
        if bound_sha:
            check(same_hash(actual, bound_sha), f"locked SHA mismatch: {name}")
    check(same_hash(c5_parent["input_lock_sha256"], sha256(C5_LOCK_PATH)), "C5 parent audit input lock mismatch")
    check(same_hash(c5_parent["batch_sha256"], sha256(C5_BATCH_PATH)), "C5 parent audit batch status mismatch")

    for key, filename in {
        "run_contract_sha256": "C5_DEV72_RUN_CONTRACT_v3.json",
        "source_binding_sha256": "C5_DEV72_SOURCE_BINDING_v3.json",
        "release_sha256": "C5_DEV72_RELEASE_v3.json",
        "snapshot_sha256": "C5_DEV72_PREPARED_CFG_OPTS_v3.mat",
        "body_sha256": "C5_DEV72_BODY_COMPLETE_v3.json",
    }.items():
        check(same_hash(sha256(C5_DIR / filename), c5_parent[key]), f"C5 parent locked source mismatch: {filename}")

    lineage_path = Path(b_lim["lineage_review_path"])
    check(same_hash(sha256(lineage_path), b_lim["lineage_review_sha256"]), "B lineage review SHA mismatch")
    check(b_parent["status"] == "PASS_NEW_B72_TRACEABLE_EXACTLY_REPRODUCES_HISTORICAL_B" and len(b_parent_rows) == 72,
          "B parent review is not the locked 72-scene pass")
    check(c5_parent["status"] == "PASS_C5_DEV72_RAW_ALL_EVENTS_PARENT_AUDIT" and c5_parent["new_scenes_event_checked"] == 60 and c5_parent["reused_scenes_event_audit_refs"] == 12,
          "C5 parent review is not the 60-new/12-reused 72-scene pass")
    check(len(c5_reuse_rows) == 12 and set(c5_reuse_rows) == set(c5_lock["scene_ids_reuse_12"]),
          "C5 reused-scene audit set differs from the locked 12-scene list")
    check(same_hash(sha256(C5_REUSE_AUDIT_PATH), c5_parent["old12_parent_summary_sha256"]),
          "C5 reused 12-scene parent audit summary SHA mismatch")
    check(len(c5_parent_rows) == 72 and all(row.get("status") in ("PASS_C5_RAW_ALL_EVENTS", "PASS_REUSED_C5_SCREEN_AUDIT") for row in c5_parent_rows.values()),
          "C5 parent rows do not all pass")
    check(summary["scene_pass_count"] == 72 and summary["scene_fail_count"] == 0 and not summary["failing_scene_ids"],
          "SUMMARY scene totals are not 72 pass / 0 fail")
    check(summary["B"]["raw_hash_current_match_count"] == 72 and summary["B"]["status_hash_current_match_count"] == 72 and summary["B"]["parent_review_exact_array_matches"] == 72,
          "SUMMARY B counts disagree with rechecked sources")
    check(summary["C5"]["current_raw_sha_match_count"] == 72 and summary["C5"]["current_status_sha_match_count"] == 72 and summary["C5"]["per_scene_parent_audit_match_count"] == 72,
          "SUMMARY C5 counts disagree with rechecked sources")
    check(summary["C5"]["all_score_pending_ids_now_have_passed_parent_audit"] is True and score["c5_audit_limitation"]["pending_parent_audit_count"] == 60,
          "C5 stale pending caveat / later parent audit relationship changed")
    check(summary["B"]["reused_B1_scene_ids"] == ["DL1018_VAL_T2_C00_W10"] and b_parent["historical_runtime_identity_gap_closed"] is False,
          "B1 reuse or historical source qualification changed")
    check(score["study_scope"]["score_training_scene_overlap_count"] == 72 and score["study_scope"]["independent_validation"] is False and summary["test_accessed"] is False,
          "in-sample or TEST-access limitation changed")
    check(summary["metric_provenance"]["GRU_paired_score_scorer"] == score["scorer"] and summary["metric_provenance"]["C5_parent_review_metric_scorer_sha256"] == c5_parent["metric_scorer_sha256"],
          "scorer identity references changed")

    if errors:
        print(json.dumps({"status": "FAIL", "errors": errors}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({
        "status": "PASS",
        "scenes": 72,
        "raw_files_rehashed": 144,
        "status_files_rehashed": 144,
        "passing_scene_ids": len(scene_ids),
        "B_historical_identity_gap_preserved": True,
        "C5_pending_score_rows_with_existing_parent_pass": 60,
        "score_in_sample_overlap": 72,
        "test_accessed": False,
        "verified_output_files": ["SCENE_SOURCE_AUDIT.csv", "SUMMARY.json"],
        "errors": [],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
