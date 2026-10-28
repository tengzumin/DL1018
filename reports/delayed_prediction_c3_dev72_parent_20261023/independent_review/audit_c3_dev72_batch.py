from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EXP = ROOT / "experiments" / "position_delayed_prediction_c3_dev72_20261023"
OWN = ROOT / "reports" / "delayed_prediction_c3_dev72_parent_20261023" / "independent_review"
LOCK_PATH = EXP / "C3_DEV72_INPUT_LOCK_v2.json"
CONTRACT_PATH = EXP / "C3_DEV72_RUN_CONTRACT_v2.json"
RUNNER_PATH = EXP / "run_c3_dev72_v2.m"
PREPARE_PATH = EXP / "prepare_c3_dev72_v2.m"
PREPARE_RESULT_PATH = EXP / "C3_DEV72_PREPARE_RESULT_v2.json"
SNAPSHOT_PATH = EXP / "C3_DEV72_PREPARED_CONFIG_OPTS_v2.mat"
RELEASE_PATH = EXP / "C3_DEV72_RELEASE_v2.json"
PROGRESS_PATH = EXP / "C3_DEV72_PROGRESS_v2.json"
SUMMARY_PATH = EXP / "C3_DEV72_SUMMARY_v2.json"
RUN_ROOT = EXP / "runs_dev72_v2"
VERIFIER_PATH = OWN / "verify_c3_dev72_events.py"
OUTPUT_PATH = OWN / "C3_DEV72_NEW60_EVENT_AUDIT.json"
USER_CAP = 5 * 1024**3


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def require(test: bool, message: str) -> None:
    if not test:
        raise AssertionError(message)


def main() -> None:
    require(not OUTPUT_PATH.exists(), f"Refusing to overwrite {OUTPUT_PATH}")
    for path in (LOCK_PATH, CONTRACT_PATH, RUNNER_PATH, PREPARE_PATH, PREPARE_RESULT_PATH,
                 SNAPSHOT_PATH, RELEASE_PATH, PROGRESS_PATH, SUMMARY_PATH, VERIFIER_PATH):
        require(path.is_file(), f"Missing frozen input: {path}")

    input_hashes = {p.name: sha256(p) for p in (
        LOCK_PATH, CONTRACT_PATH, RUNNER_PATH, PREPARE_PATH, PREPARE_RESULT_PATH,
        SNAPSHOT_PATH, RELEASE_PATH, PROGRESS_PATH, SUMMARY_PATH, VERIFIER_PATH)}
    lock, contract = read_json(LOCK_PATH), read_json(CONTRACT_PATH)
    prepare, release = read_json(PREPARE_RESULT_PATH), read_json(RELEASE_PATH)
    progress, summary = read_json(PROGRESS_PATH), read_json(SUMMARY_PATH)

    require(input_hashes[PROGRESS_PATH.name] == input_hashes[SUMMARY_PATH.name],
            "Progress and summary bytes differ")
    require(progress == summary, "Progress and summary JSON differ")
    require(progress["status"] == "ALL_60_COMPLETE_RAW_PENDING_AUDIT" and
            progress["completed_scene_count"] == 60, "Batch is not terminal ALL_60_COMPLETE")
    require(progress["scene_ids_new_60"] == lock["scene_ids_new_60"],
            "Progress scene set differs from frozen lock")
    require(len(progress["runs"]) == 60, "Expected exactly 60 run records")
    require(len(set(progress["scene_ids_new_60"])) == 60, "New scene IDs are not unique")
    require(set(progress["scene_ids_new_60"]).isdisjoint(lock["scene_ids_reuse_12"]),
            "New and reused C3 scene sets overlap")
    require(set(progress["scene_ids_new_60"]) | set(lock["scene_ids_reuse_12"]) == set(lock["scene_ids_all_72"]),
            "New and reused scenes do not exactly cover the frozen 72")

    lock_sha = input_hashes[LOCK_PATH.name]
    contract_sha = input_hashes[CONTRACT_PATH.name]
    runner_sha = input_hashes[RUNNER_PATH.name]
    prepare_sha = input_hashes[PREPARE_RESULT_PATH.name]
    snapshot_sha = input_hashes[SNAPSHOT_PATH.name]
    release_sha = input_hashes[RELEASE_PATH.name]
    require(prepare["source_lock_sha256"] == lock_sha and prepare["contract_sha256"] == contract_sha and
            prepare["runner_sha256"] == runner_sha and prepare["snapshot_sha256"] == snapshot_sha,
            "PREPARE result does not bind the frozen lock/contract/runner/snapshot")
    require(release["input_lock_sha256"] == lock_sha and release["contract_sha256"] == contract_sha and
            release["runner_sha256"] == runner_sha and release["prepare_result_sha256"] == prepare_sha and
            release["cfg_opts_snapshot_sha256"] == snapshot_sha,
            "Release does not bind the v2 source and PREPARE artifacts")
    require(release["plant_authorized"] is True and release["max_new_Plant"] == 60 and
            len(release["scene_ids"]) == 60 and release["total_development_unique_scenes"] == 72 and
            release["reused_C3_sorties"] == 12, "Release scope differs from approved 60+12 scope")
    require(release["new_training"] == 0 and release["optimizer_steps"] == 0 and
            release["parameter_or_seed_search"] is False and release["new_B_sorties"] == 0 and
            release["TEST_authorized"] is False and release["automatic_retry"] is False,
            "Release violates no-training/no-search/no-TEST/no-retry limits")
    require(release["new_output_cap_bytes"] <= USER_CAP and
            release["batch_reserved_bytes"] <= USER_CAP, "Release exceeds the 5 GiB user cap")
    require(progress["release_sha256"] == release_sha and progress["input_lock_sha256"] == lock_sha and
            progress["runner_sha256"] == runner_sha and progress["prepare_result_sha256"] == prepare_sha,
            "Progress is not bound to the frozen release and source")

    # The lock's scene records are the authority for each expected B/raw identity.
    lock_scenes = {item["scene_id"]: item for item in lock["scenes"]}
    require(len(lock_scenes) == 72, "Lock does not contain 72 unique scene records")
    require(set(lock_scenes) == set(lock["scene_ids_all_72"]), "Lock scene records differ from scene list")

    # Exactly one attempt and one marker per new scene; no retry directories.
    attempt_dirs = sorted(p for p in RUN_ROOT.rglob("attempt_*") if p.is_dir())
    marker_paths = sorted(RUN_ROOT.rglob("first_plant_step.marker"))
    require(len(attempt_dirs) == 60 and all(p.name == "attempt_01" for p in attempt_dirs),
            "Unexpected attempt count or a retry attempt directory exists")
    require(len(marker_paths) == 60, "Expected exactly one Plant marker per new scene")

    verifier_spec = importlib.util.spec_from_file_location("verify_c3_dev72_events", VERIFIER_PATH)
    require(verifier_spec is not None and verifier_spec.loader is not None, "Cannot load event verifier")
    verifier = importlib.util.module_from_spec(verifier_spec)
    verifier_spec.loader.exec_module(verifier)

    check_max = {name: 0.0 for name in (
        "unit_phi", "finite_event_arrays", "beta_clock", "event_dt", "past_interval_target",
        "output_before_update", "applied_beta_clip", "joint_projected_update",
        "weight_continuity", "prediction_term_norm")}
    rows = []
    total_raw_bytes = 0
    total_event_count = 0
    for index, (scene_id, record) in enumerate(zip(lock["scene_ids_new_60"], progress["runs"]), start=1):
        require(record["scene_index_1based"] == index and record["scene_id"] == scene_id,
                f"Run ordering/scene mismatch at index {index}")
        frozen = lock_scenes[scene_id]
        require(scene_id not in set(lock["scene_ids_reuse_12"]), f"New scene overlaps reuse set: {scene_id}")
        require(record["condition"] == lock["candidate_condition_id"] and
                record["status"] == "RUN_COMPLETE_RAW_PENDING_AUDIT" and
                record["log_status"] == "STABLE" and not record["safety_stop_reason"],
                f"Run is not a clean STABLE completion: {scene_id}")
        require(record["release_sha256"] == release_sha and record["input_lock_sha256"] == lock_sha and
                record["prepare_result_sha256"] == prepare_sha and
                record["cfg_opts_snapshot_sha256"] == snapshot_sha,
                f"Run release/lock/PREPARE/snapshot binding mismatch: {scene_id}")
        require(record["B_raw_path"] == frozen["B_source"]["path"] and
                record["B_raw_sha256"] == frozen["B_source"]["sha256"] and
                record["external_identity_sha256"] == frozen["external_identity_sha256"],
                f"Run B/external input identity differs from lock: {scene_id}")
        require(record["plant_invocation_entered"] is True and record["plant_start_confirmed"] is True and
                record["plant_calls"] == 1 and record["training_steps"] == 0 and
                record["optimizer_steps"] == 0 and record["parameter_or_seed_search"] is False and
                record["new_B_sorties"] == 0 and record["TEST_accessed"] is False,
                f"Run side-effect/scope guard mismatch: {scene_id}")

        status_path, run_start_path = Path(record["run_status_path"]), Path(record["run_start_path"])
        raw_path, marker_path = Path(record["raw_path"]), Path(record["first_plant_step_marker_path"])
        status = read_json(status_path)
        for key in ("schema", "status", "scene_index_1based", "scene_id", "source_scene_id", "condition",
                    "log_status", "safety_stop_reason", "raw_path", "raw_sha256", "raw_bytes",
                    "run_start_path", "run_start_sha256", "first_plant_step_marker_path",
                    "first_plant_step_marker_sha256", "release_sha256", "input_lock_sha256",
                    "prepare_result_sha256", "cfg_opts_snapshot_sha256", "B_raw_path", "B_raw_sha256",
                    "external_identity_sha256", "plant_invocation_entered", "plant_start_confirmed",
                    "plant_calls", "training_steps", "optimizer_steps", "parameter_or_seed_search",
                    "new_B_sorties", "TEST_accessed"):
            require(status.get(key) == record.get(key), f"run_status differs from progress at {scene_id}:{key}")
        require(status.get("schema") == "C3_DELAYED_PREDICTION_DEV72_RUN_STATUS_V1",
                f"Unexpected status schema: {scene_id}")
        require(run_start_path.is_file() and sha256(run_start_path) == record["run_start_sha256"],
                f"run_start SHA mismatch: {scene_id}")
        require(marker_path.is_file() and sha256(marker_path) == record["first_plant_step_marker_sha256"],
                f"Plant marker SHA mismatch: {scene_id}")
        require(raw_path.is_file() and raw_path.stat().st_size == int(record["raw_bytes"]),
                f"Raw missing or size mismatch: {scene_id}")
        expected_sha = str(status["raw_sha256"]).lower()  # expected SHA comes from actual saved status.
        require(expected_sha == str(record["raw_sha256"]).lower(), f"Raw SHA ledger mismatch: {scene_id}")

        audited = verifier.verify(raw_path, expected_sha, scene_id)
        require(audited["status"] == "PASS_C3_EVENT_AUDIT" and
                audited["run_identity_schema"] == "C3_DELAYED_PREDICTION_DEV72_RUN_IDENTITY_V1" and
                audited["event_count"] == 1968, f"Candidate event audit failed: {scene_id}")
        for name, value in audited["checks_max_abs"].items():
            check_max[name] = max(check_max[name], float(value))
        total_event_count += audited["event_count"]
        total_raw_bytes += int(record["raw_bytes"])
        rows.append({
            "scene_id": scene_id,
            "raw_sha256": audited["raw_sha256"],
            "run_start_sha256": record["run_start_sha256"],
            "run_status_sha256": sha256(status_path),
            "marker_sha256": record["first_plant_step_marker_sha256"],
            "event_count": audited["event_count"],
            "run_identity_schema": audited["run_identity_schema"],
            "checks_max_abs": audited["checks_max_abs"],
        })

    tree_bytes = sum(p.stat().st_size for p in RUN_ROOT.rglob("*") if p.is_file())
    require(total_raw_bytes <= release["batch_reserved_bytes"] <= release["new_output_cap_bytes"] <= USER_CAP,
            "Raw bytes exceed reserved/output/user cap")
    require(tree_bytes <= release["batch_reserved_bytes"] <= release["new_output_cap_bytes"] <= USER_CAP,
            "Actual run directory exceeds reserved/output/user cap")
    require(total_event_count == 60 * 1968, "Unexpected total candidate event count")

    # Protect the terminal ledgers during the audit.
    for path, expected in ((LOCK_PATH, lock_sha), (CONTRACT_PATH, contract_sha), (RUNNER_PATH, runner_sha),
                           (PREPARE_RESULT_PATH, prepare_sha), (SNAPSHOT_PATH, snapshot_sha),
                           (RELEASE_PATH, release_sha), (PROGRESS_PATH, input_hashes[PROGRESS_PATH.name]),
                           (SUMMARY_PATH, input_hashes[SUMMARY_PATH.name])):
        require(sha256(path) == expected, f"Input changed during audit: {path.name}")

    output = {
        "schema": "C3_DEV72_NEW60_EVENT_AUDIT_V1",
        "status": "PASS_ALL_60_NEW_EVENT_AUDITS",
        "audit_script_sha256": sha256(Path(__file__).resolve()),
        "event_verifier_path": str(VERIFIER_PATH),
        "event_verifier_sha256": input_hashes[VERIFIER_PATH.name],
        "input_hashes": input_hashes,
        "scope": {"new_scenes": 60, "reused_scenes_not_reread": 12, "unique_dev72": 72,
                  "events_per_new_scene": 1968, "total_new_events": total_event_count,
                  "attempt_dirs": len(attempt_dirs), "first_plant_markers": len(marker_paths)},
        "budget": {"raw_bytes": total_raw_bytes, "run_tree_bytes": tree_bytes,
                   "reserved_bytes": release["batch_reserved_bytes"],
                   "output_cap_bytes": release["new_output_cap_bytes"], "user_cap_bytes": USER_CAP,
                   "within_caps": True},
        "max_abs_check_error_by_field": check_max,
        "rows": rows,
    }
    with OUTPUT_PATH.open("x", encoding="utf-8", newline="\n") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")

    print(json.dumps({
        "status": output["status"],
        "rows": len(rows),
        "events": total_event_count,
        "raw_bytes": total_raw_bytes,
        "tree_bytes": tree_bytes,
        "max_abs_error": max(check_max.values()),
        "output_path": str(OUTPUT_PATH),
        "output_sha256": sha256(OUTPUT_PATH),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
