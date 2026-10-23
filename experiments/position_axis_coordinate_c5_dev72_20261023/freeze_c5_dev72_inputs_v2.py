"""Freeze the one C5 M110 DEV72 completion scope from audited upstream records."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parents[2]
EXP = Path(__file__).resolve().parent
REPORT = ROOT / "reports/paper_continuation_20261023/c5_dev72_execution"
C5 = ROOT / "experiments/position_axis_coordinate_c5_20261023"
C3 = ROOT / "experiments/position_delayed_prediction_c3_dev72_20261023"
B72 = ROOT / "experiments/b_traceable_c3core_dev72_20261023"
PARENT = ROOT / "reports/paper_continuation_20261023/c5_axis_coordinate_parent_review"
SCREEN = PARENT / "screen12_parent_review"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def ref(path: Path) -> dict:
    assert path.is_file(), f"missing file {path}"
    return {"path": str(path.resolve()), "sha256": sha(path)}


def verify_ref(item: dict) -> None:
    p = Path(item["path"])
    assert p.is_file(), f"missing referenced file {p}"
    assert sha(p).lower() == item["sha256"].lower(), f"SHA mismatch {p}"


def same_path(a: str | Path, b: str | Path) -> bool:
    return Path(a).resolve().as_posix().lower() == Path(b).resolve().as_posix().lower()


def checked_json(path: Path, expected_sha: str | None = None) -> dict:
    if expected_sha:
        assert sha(path).lower() == expected_sha.lower(), f"JSON source SHA mismatch {path}"
    return read_json(path)


def verify_complete_status(path: str, digest: str, scene_id: str, raw_path: str, raw_sha: str,
                           *, mask: bool = False, event_counts: bool = False) -> dict:
    p = Path(path)
    assert p.is_file() and sha(p).lower() == digest.lower(), f"status SHA mismatch: {p}"
    s = read_json(p)
    expected_fields = [("scene_id", scene_id), ("status", "RUN_COMPLETE_RAW_PENDING_AUDIT"),
                       ("log_status", "STABLE"), ("plant_calls", 1), ("raw_path", raw_path),
                       ("raw_sha256", raw_sha)]
    if event_counts:
        expected_fields.extend([("last_transition", 20000), ("transitions", 20000), ("state_samples", 20001)])
    for key, expected in expected_fields:
        assert key in s and s[key] == expected, f"{p}: {key} disagrees with locked identity"
    assert s.get("training_steps") == 0 and s.get("optimizer_steps") == 0
    assert s.get("TEST_accessed") is False
    if mask:
        assert s.get("coordinate_mask") == [1, 1, 0]
    return s


def main() -> None:
    taskbook = ref(ROOT / "reports/paper_continuation_20261023/C5_DEV72_COMPLETION_CONDITIONAL_TASKBOOK_ZH.md")
    assert taskbook["sha256"] == "6b28880fee55278202875b252bf2486731ed00b9637f9038587553e389e46057"

    c3_lock_path = C3 / "C3_DEV72_INPUT_LOCK_v2.json"
    c3_ledger_path = C3 / "C3_DEV72_EXECUTION_LEDGER_v2.json"
    c3_prep_path = C3 / "C3_DEV72_PREPARE_RESULT_v2.json"
    c3_snapshot_path = C3 / "C3_DEV72_PREPARED_CONFIG_OPTS_v2.mat"
    c3_contract_path = C3 / "C3_DEV72_RUN_CONTRACT_v2.json"
    c3_release_path = C3 / "C3_DEV72_RELEASE_v2.json"
    c3_lock = checked_json(c3_lock_path, "a95eda8e6ab8b45408d24b560366636bab62f72ea619bf46fa602142b6708730")
    c3_ledger = checked_json(c3_ledger_path, "b815dc7d4de6a7c7f53755ff8659a63c9507e6f6c22f5b9e49d94cfc69e3c866")
    c5_lock_path = C5 / "C5_AXIS_COORDINATE_INPUT_LOCK_v1.json"
    c5_contract_path = C5 / "C5_AXIS_COORDINATE_RUN_CONTRACT_v1.json"
    c5_prep_path = C5 / "C5_AXIS_COORDINATE_PREPARE_RESULT_v1.json"
    c5_snapshot_path = C5 / "C5_AXIS_COORDINATE_PREPARED_CFG_OPTS_v1.mat"
    c5_lock = checked_json(c5_lock_path, "10a7eea144e3574e05eea7b4f7b56112595eac0c81d27b5e8c7a5a41499f84b0")
    c5_contract = checked_json(c5_contract_path, "2861f8a49b76c5d244b9019a01c8b83a6f7b627f6fc6a392ec794c01037fdf4f")
    c5_prep = checked_json(c5_prep_path, "c3f5bba0f8e0c1bca7d6d76c7f0778a583db98fd971ecc4a023391640ca4257d")

    assert c3_lock["schema"] == "C3_DELAYED_PREDICTION_DEV72_INPUT_LOCK_V1"
    assert c3_lock["counts"] == {"total": 72, "new": 60, "reuse": 12,
                                 "historical_raw_rows": 216, "physical_fields_per_scene": 14}
    all_ids = c3_lock["scene_ids_all_72"]
    reuse_ids = c3_lock["scene_ids_reuse_12"]
    reuse_set = set(reuse_ids)
    new_ids = [scene_id for scene_id in all_ids if scene_id not in reuse_set]
    assert new_ids == c3_lock["scene_ids_new_60"]
    assert len(all_ids) == 72 and len(new_ids) == 60 and len(reuse_ids) == 12
    assert len(set(all_ids)) == 72 and len(reuse_set) == 12
    assert new_ids == [scene_id for scene_id in all_ids if scene_id not in reuse_set]
    assert reuse_ids == [scene_id for scene_id in all_ids if scene_id in reuse_set]
    assert [s["scene_id"] for s in c3_lock["scenes"]] == all_ids
    assert [s["scene_id"] for s in c5_lock["scenes"]] == reuse_ids
    assert c5_lock["scene_ids_reuse_12"] == reuse_ids

    assert c3_ledger["status"] == "ALL_60_COMPLETE_RAW_PENDING_AUDIT"
    assert c3_ledger["plant_budget_used"] == 60 and c3_ledger["plant_budget_remaining"] == 0
    assert c3_ledger["training_steps_total"] == 0 and c3_ledger["optimizer_steps_total"] == 0
    assert c3_ledger["new_B_sorties"] == 0 and c3_ledger["TEST_accessed"] is False
    ledger_rows = c3_ledger["rows"]
    assert len(ledger_rows) == 60 and [r["scene_id"] for r in ledger_rows] == new_ids
    assert all(r["status"] == "RUN_COMPLETE_RAW_PENDING_AUDIT" and r["log_status"] == "STABLE" and
               r["plant_calls"] == 1 and r["plant_invocation_entered"] and r["plant_start_confirmed"] and
               r["training_steps"] == 0 and r["optimizer_steps"] == 0 and r["TEST_accessed"] is False and
               r["input_lock_sha256"] == sha(c3_lock_path) for r in ledger_rows)

    b72_manifest_path = PARENT / "C5_B72_SCORING_MANIFEST_v1.json"
    b72_manifest = read_json(b72_manifest_path)
    b72_lock_path = B72 / "B_TRACEABLE_DEV72_INPUT_LOCK_v3.json"
    b72_contract_path = B72 / "B_TRACEABLE_DEV72_RUN_CONTRACT_v3.json"
    b72_prep_path = B72 / "B_TRACEABLE_DEV72_PREPARE_RESULT_v3.json"
    b72_snapshot_path = B72 / "B_TRACEABLE_DEV72_PREPARED_CFG_OPTS_v3.mat"
    b72_release_path = B72 / "B_TRACEABLE_DEV72_RELEASE_v3.json"
    b72_body_path = B72 / "B_TRACEABLE_DEV72_BODY_COMPLETE_v3.json"
    b72_os_path = B72 / "B_TRACEABLE_DEV72_BATCH_OS_EXIT_v3.json"
    b72_lock = checked_json(b72_lock_path, "8d738e5c70ba2fc8697550549d1a0537f08eadb49b99bc5684e5c26f6222f452")
    b72_release = checked_json(b72_release_path, "f8fd7865a394d7195948d6a47d6769b0c5c64ce28cd0ccc19e9d47d02506f3d1")
    b72_body = checked_json(b72_body_path, "16875fcf8ff4901659c5b1ed2dd595c43963bead074ec7eedf7c111387a6050b")
    b72_parent_path = Path(b72_manifest["canonical_parent_audit"]["path"])
    b72_manifest_canonical_path = Path(b72_manifest["canonical_manifest"]["path"])
    b72_parent = checked_json(b72_parent_path, b72_manifest["canonical_parent_audit"]["sha256"])
    assert b72_parent["status"] == "PASS_NEW_B72_TRACEABLE_EXACTLY_REPRODUCES_HISTORICAL_B" and b72_parent["scene_count"] == 72
    assert b72_manifest["schema"] == "C5_B72_SCORING_MANIFEST_V1"
    assert b72_manifest["state"] == "PASS_C5_B72_ALL72_PARENT_AUDIT"
    b_rows = b72_manifest["records"]
    assert len(b_rows) == 72 and [r["scene_id"] for r in b_rows] == all_ids
    b_by_scene = {r["scene_id"]: r for r in b_rows}
    for row in b_rows:
        assert row["plant_calls"] == 1
        assert Path(row["raw_path"]).is_file(), f"missing B72 raw {row['scene_id']}"
        verify_complete_status(row["run_status_path"], row["run_status_sha256"], row["scene_id"],
                              row["raw_path"], row["raw_sha256"], event_counts=True)

    c5_screen_summary_path = SCREEN / "SUMMARY.json"
    c5_screen_summary = checked_json(c5_screen_summary_path,
                                    "fe217ac8b259706b1953e07dd44586b6a64368a6d4f5e0145e8f507863d82ad8")
    assert c5_screen_summary["status"] == "C5_SCREEN_PASS"
    assert all(c5_screen_summary["gates"].values()) and len(c5_screen_summary["audits"]) == 12
    assert c5_screen_summary["event_count"] == 23616
    assert c5_screen_summary["B_identity_status"] == "PARENT_AUDITED_NEW_TRACEABLE_B72"
    c5_first_receipt_path = ROOT / "reports/paper_continuation_20261023/c5_axis_coordinate_execution/C5_FIRST_EXECUTION_RECEIPT_v1.json"
    c5_first_receipt = read_json(c5_first_receipt_path)
    c5_tail_batch_path = C5 / "C5_TAIL11_BATCH_STATUS_v2.json"
    c5_tail_body_path = C5 / "C5_TAIL11_BODY_COMPLETE_v2.json"
    c5_tail_batch = read_json(c5_tail_batch_path)
    c5_tail_body = read_json(c5_tail_body_path)
    assert c5_tail_batch["status"] == "COMPLETE_RAW_PENDING_PARENT_AUDIT" and c5_tail_batch["plant_calls"] == 11
    assert c5_tail_body["status"] == "COMPLETE_RAW_PENDING_PARENT_AUDIT" and c5_tail_body["plant_calls"] == 11
    assert c5_first_receipt["scene_id"] in reuse_ids and c5_first_receipt["run_status"] == "RUN_COMPLETE_RAW_PENDING_AUDIT"
    assert c5_first_receipt["transitions"] == 20000 and c5_first_receipt["state_samples"] == 20001
    assert c5_first_receipt["matlab_os_exit_code"] == 0 and c5_first_receipt["shell_natural_exit_code"] == 0
    assert c5_first_receipt["plant_calls"] == 1 and c5_first_receipt["training_steps"] == 0
    assert c5_first_receipt["optimizer_steps"] == 0 and c5_first_receipt["TEST_accessed"] is False
    assert c5_first_receipt["safety_stop_reason"] == ""
    assert len(c5_tail_batch["records"]) == 11 and c5_tail_batch["completed_scenes"] == 11
    assert c5_tail_body["completed_scenes"] == 11 and c5_tail_body["per_scene_exit_record_count"] == 11
    assert c5_tail_body["batch_scope_scene_ids"] == c5_tail_batch["tail_scene_ids"]
    assert [r["scene_id"] for r in c5_tail_batch["records"]] == c5_tail_batch["tail_scene_ids"]
    c5_run_by_scene: dict[str, dict] = {}
    fr = c5_first_receipt["artifacts"]
    for artifact in ("command", "launcher", "release", "input_lock", "runner", "run_start",
                     "run_status", "attempt_started_marker", "first_plant_step_marker", "matlab_os_exit",
                     "stdout", "stderr"):
        verify_ref(fr[artifact])
    c5_run_by_scene[c5_first_receipt["scene_id"]] = {
        "raw_path": fr["raw"]["path"], "raw_sha256": fr["raw"]["sha256"],
        "run_status_path": fr["run_status"]["path"], "run_status_sha256": fr["run_status"]["sha256"],
        "run_start_path": fr["run_start"]["path"], "run_start_sha256": fr["run_start"]["sha256"],
        "attempt_started_marker_path": fr["attempt_started_marker"]["path"],
        "attempt_started_marker_sha256": fr["attempt_started_marker"]["sha256"],
        "first_plant_step_marker_path": fr["first_plant_step_marker"]["path"],
        "first_plant_step_marker_sha256": fr["first_plant_step_marker"]["sha256"],
    }
    for row in c5_tail_batch["records"]:
        c5_run_by_scene[row["scene_id"]] = {k: row[k] for k in (
            "raw_path", "raw_sha256", "run_status_path", "run_status_sha256", "run_start_path",
            "run_start_sha256", "attempt_started_marker_path", "attempt_started_marker_sha256",
            "first_plant_step_marker_path", "first_plant_step_marker_sha256")}
    assert set(c5_run_by_scene) == set(reuse_ids)
    assert len(c5_run_by_scene) == 12 and c5_first_receipt["scene_id"] not in {r["scene_id"] for r in c5_tail_batch["records"]}
    for scene_id, record in c5_run_by_scene.items():
        verify_complete_status(record["run_status_path"], record["run_status_sha256"], scene_id,
                               record["raw_path"], record["raw_sha256"], mask=True, event_counts=True)
    audit_by_scene = {r["scene_id"]: r for r in c5_screen_summary["audits"]}
    assert set(audit_by_scene) == set(reuse_ids)
    for scene_id, audit in audit_by_scene.items():
        run = c5_run_by_scene[scene_id]
        assert audit["status"] == "PASS_C5_RAW_ALL_EVENTS" and audit["event_count"] == 1968
        assert audit["raw_sha256"] == run["raw_sha256"]
        assert audit["run_status_sha256"] == run["run_status_sha256"]
        assert audit["C5_metrics"]["path"] == run["raw_path"] and audit["C5_metrics"]["sha256"] == run["raw_sha256"]
        assert audit["B_metrics"]["sha256"] == b_by_scene[scene_id]["raw_sha256"]
        assert audit["C3_metrics"]["sha256"] == next(r["C3_reuse"]["raw_sha256"] for r in c3_lock["scenes"] if r["scene_id"] == scene_id)

    c3_by_scene = {s["scene_id"]: s for s in c3_lock["scenes"]}
    c3_new_by_scene = {r["scene_id"]: r for r in ledger_rows}
    c5_by_scene = {s["scene_id"]: s for s in c5_lock["scenes"]}
    scenes = []
    for index, scene_id in enumerate(all_ids, 1):
        c3row = c3_by_scene[scene_id]
        assert c3row["scene_id"] == scene_id and c3row["B_source"]["path"] and c3row["B_source"]["sha256"]
        assert Path(c3row["B_source"]["path"]).is_file()
        b = b_by_scene[scene_id]
        if scene_id in c3_new_by_scene:
            c = c3_new_by_scene[scene_id]
            c3_ref = {"kind": "C3_DEV72_NEW", "raw_path": c["raw_path"], "raw_sha256": c["raw_sha256_actual"],
                      "run_status_path": c["run_status_path"], "run_status_sha256": c["run_status_sha256_actual"],
                      "run_start_path": c["run_start_path"], "run_start_sha256": c["run_start_sha256_actual"],
                      "attempt_started_marker_path": c["attempt_started_marker_path"],
                      "attempt_started_marker_sha256": c["attempt_started_marker_sha256"],
                      "first_plant_step_marker_path": c["first_plant_step_marker_path"],
                      "first_plant_step_marker_sha256": c["first_plant_step_marker_sha256_actual"],
                      "plant_calls": c["plant_calls"]}
            assert Path(c3_ref["raw_path"]).is_file()
            verify_complete_status(c3_ref["run_status_path"], c3_ref["run_status_sha256"], scene_id,
                                  c3_ref["raw_path"], c3_ref["raw_sha256"])
            c5_reuse = {"reused": False, "raw_path": "", "raw_sha256": "", "run_status_path": "",
                        "run_status_sha256": "", "run_start_path": "", "run_start_sha256": "",
                        "attempt_started_marker_path": "", "attempt_started_marker_sha256": "",
                        "first_plant_step_marker_path": "", "first_plant_step_marker_sha256": "",
                        "parent_screen_event_count": 0, "parent_screen_status": ""}
            action = "PROPOSE_NEW_C5_M110_RUN"
        else:
            c = c3row["C3_reuse"]
            c3_ref = {"kind": "C3_REUSED_SCREEN", "raw_path": c["raw_path"], "raw_sha256": c["raw_sha256"],
                      "run_status_path": c["status_path"], "run_status_sha256": c["status_sha256"],
                      "run_start_path": c["run_start_path"], "run_start_sha256": c["run_start_sha256"],
                      "attempt_started_marker_path": "", "attempt_started_marker_sha256": "",
                      "first_plant_step_marker_path": c["first_plant_step_marker_path"],
                      "first_plant_step_marker_sha256": c["first_plant_step_marker_sha256"],
                      "plant_calls": 1}
            assert Path(c3_ref["raw_path"]).is_file()
            verify_complete_status(c3_ref["run_status_path"], c3_ref["run_status_sha256"], scene_id,
                                  c3_ref["raw_path"], c3_ref["raw_sha256"])
            run = c5_run_by_scene[scene_id]
            c5_reuse = {"reused": True, "raw_path": run["raw_path"], "raw_sha256": run["raw_sha256"],
                        "run_status_path": run["run_status_path"], "run_status_sha256": run["run_status_sha256"],
                        "run_start_path": run["run_start_path"], "run_start_sha256": run["run_start_sha256"],
                        "attempt_started_marker_path": run["attempt_started_marker_path"],
                        "attempt_started_marker_sha256": run["attempt_started_marker_sha256"],
                        "first_plant_step_marker_path": run["first_plant_step_marker_path"],
                        "first_plant_step_marker_sha256": run["first_plant_step_marker_sha256"],
                        "parent_screen_event_count": 1968,
                        "parent_screen_status": audit_by_scene[scene_id]["status"]}
            action = "REUSE_AUDITED_C5_SCREEN"
        scenes.append({"scene_id": scene_id, "original_index_1based": index,
                       "source_split": c3row["source_split"], "candidate_action": action,
                       "c3_candidate_action": c3row["candidate_action"],
                       "external_identity_sha256": c3row["external_identity_sha256"],
                       "B_source": c3row["B_source"],
                       "B72_scoring": {k: b[k] for k in ("scene_id", "raw_path", "raw_sha256", "run_status_path", "run_status_sha256", "plant_calls")},
                       "C3_reference": c3_ref, "C5_reuse": c5_reuse})
    assert [s["scene_id"] for s in scenes] == all_ids
    assert all(set(s["C3_reference"]) == set(scenes[0]["C3_reference"]) and
               set(s["C5_reuse"]) == set(scenes[0]["C5_reuse"]) for s in scenes)

    taskbook_path = Path(taskbook["path"])
    assert taskbook_path.is_file()
    source_files = {
        "input_lock_builder": ref(EXP / "freeze_c5_dev72_inputs_v2.py"),
        "prepare_entry": ref(EXP / "prepare_c5_dev72_v2.m"),
        "batch_runner": ref(EXP / "run_c5_dev72_v2.m"),
        "no_plant_launcher": ref(EXP / "RUN_C5_DEV72_NOPLANT_EXACT_v2.ps1"),
        "plant_launcher": ref(EXP / "RUN_C5_DEV72_EXACT_v2.ps1"),
        "isolated_sources": [ref(EXP / name) for name in ("run_dl1018_closed_loop.m", "run_episode_dl1018.m", "delayed_prediction_step_candidate.m")],
        "c5_crosslang_fixture": dict(c5_lock["source_files"]["synthetic_fixture"]),
        "c5_crosslang_checker": dict(c5_lock["source_files"]["synthetic_check"]),
        "c5_crosslang_generator": dict(c5_lock["source_files"]["synthetic_generator"]),
        "c5_crosslang_result": ref(C5 / "C5_CROSSLANG_SYNTHETIC_RESULT_v1.json"),
    }
    for k in ("prepare_entry", "batch_runner", "no_plant_launcher", "plant_launcher"):
        assert Path(source_files[k]["path"]).is_file(), f"write required source before lock: {k}"

    c5_screen_refs = [ref(c5_screen_summary_path)] + [
        {"path": x["path"], "sha256": x["sha256"]} for x in c5_screen_summary["refs"]]
    for x in c5_screen_refs:
        verify_ref(x)
    for key in ("c5_crosslang_fixture", "c5_crosslang_checker", "c5_crosslang_generator", "c5_crosslang_result"):
        verify_ref(source_files[key])

    upstream_refs = {
        "taskbook": taskbook,
        "c3_input_lock": ref(c3_lock_path), "c3_run_contract": ref(c3_contract_path),
        "c3_prepare_result": ref(c3_prep_path), "c3_prepared_snapshot": ref(c3_snapshot_path),
        "c3_execution_ledger": ref(c3_ledger_path), "c3_release": ref(c3_release_path),
        "c5_input_lock": ref(c5_lock_path), "c5_run_contract": ref(c5_contract_path),
        "c5_prepare_result": ref(c5_prep_path), "c5_prepared_snapshot": ref(c5_snapshot_path),
        "c5_screen_summary": ref(c5_screen_summary_path), "c5_first_receipt": ref(c5_first_receipt_path),
        "c5_tail_batch": ref(c5_tail_batch_path), "c5_tail_body": ref(c5_tail_body_path),
        "b72_input_lock": ref(b72_lock_path), "b72_run_contract": ref(b72_contract_path),
        "b72_prepare_result": ref(b72_prep_path), "b72_prepared_snapshot": ref(b72_snapshot_path),
        "b72_release": ref(b72_release_path), "b72_batch_body": ref(b72_body_path),
        "b72_batch_os_exit": ref(b72_os_path), "b72_scoring_manifest": ref(b72_manifest_path),
        "b72_canonical_manifest": ref(b72_manifest_canonical_path),
        "b72_parent_review": ref(b72_parent_path),
        "shared_heavy_job_release": c5_lock["upstream_refs"]["shared_job_release"],
        "screen_evidence_refs": c5_screen_refs,
    }
    for item in upstream_refs.values():
        if isinstance(item, dict) and "path" in item:
            verify_ref(item)
        elif isinstance(item, list):
            for child in item:
                verify_ref(child)

    active = []
    copied = {"runtime_core": "run_dl1018_closed_loop.m",
              "episode_wrapper": "run_episode_dl1018.m",
              "prediction_helper": "delayed_prediction_step_candidate.m"}
    for item in c5_lock["active_source_inventory"]:
        if item["role"] in copied:
            path = EXP / copied[item["role"]]
            assert sha(path) == item["sha256"]
            active.append({"role": item["role"], "path": str(path.resolve()), "sha256": item["sha256"]})
        else:
            verify_ref(item)
            active.append(dict(item))
    assert len(active) == 32 and sum(Path(x["path"]).suffix.lower() == ".m" for x in active) == 31
    assert sum(Path(x["path"]).suffix.lower() == ".mat" for x in active) == 1
    shared_inputs = [dict(x) for x in c5_lock["shared_input_files"]]
    assert len(shared_inputs) == 6
    for item in shared_inputs:
        verify_ref(item)

    c5_model = c5_contract["model"]
    c5_fixed = c5_contract["fixed_parameters"]
    contract = {
        "schema": "C5_AXIS_COORDINATE_DEV72_RUN_CONTRACT_V2",
        "state": "LOCKED_C5_M110_DEV72_NO_PLANT_WAIT_PARENT_RELEASE_V2",
        "candidate": c5_contract["candidate"], "output_condition_id": "C5_AXIS_MASK_M110",
        "coordinate_mask": [1, 1, 0],
        "pcf_auxiliary_enabled": True, "model": c5_model,
        "fixed_parameters": c5_fixed,
        "scene_ids_all_72": all_ids, "scene_ids_new_60": new_ids, "scene_ids_reuse_12": reuse_ids,
        "scoring_comparator": "B_TRACEABLE_DEV72",
        "limits": {"max_new_Plant": 60, "max_total_scenes": 72,
                   "max_output_bytes": 5 * 1024**3, "minimum_free_bytes": 30_000_000_000,
                   "per_scene_output_reserve_bytes": 80_000_000,
                   "deadline_utc": "2026-10-24T17:01:00Z",
                   "seconds_per_remaining_scene_for_deadline_guard": 180,
                   "process_exit_buffer_seconds": 600},
        "prohibitions": {"training_steps": 0, "optimizer_steps": 0,
                         "parameter_or_seed_search": False, "new_B_sorties": 0,
                         "TEST_accessed": False, "automatic_retry": False,
                         "mask_scan": False, "scenario_or_metric_switching": False,
                         "B_output_input_or_concatenation": False},
        "reuse_rule": "Reuse the parent-audited C5 raw for the exact locked twelve scenes; run only the original C3 DEV72 order's other sixty.",
        "scene_source_rule": "C3 B_source is physical input only; score only the new parent-audited B72 row as comparator.",
        "c5_screen_parent_summary_sha256": sha(c5_screen_summary_path),
        "b72_scoring_manifest_sha256": sha(b72_manifest_path),
    }
    contract_path = EXP / "C5_DEV72_RUN_CONTRACT_v2.json"
    if contract_path.is_file():
        assert read_json(contract_path) == contract, "Existing contract differs; preserve and version rather than overwrite."
    else:
        contract_path.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
    contract_ref = ref(contract_path)
    source_files["run_contract"] = contract_ref

    release_contract = {
        "schema": "C5_AXIS_COORDINATE_DEV72_PARENT_RELEASE_CONTRACT_V2",
        "state": "RELEASE_REQUIRED_AFTER_CODE_AND_NOPLANT_REVIEW_V2",
        "required_fields": ["schema", "state", "plant_authorized", "max_new_Plant",
                            "parent_release_contract_sha256", "candidate", "coordinate_mask",
                            "input_lock_sha256", "run_contract_sha256", "prepare_result_sha256",
                            "prepared_snapshot_sha256", "source_binding_sha256", "runner_sha256",
                            "launcher_sha256",
                            "scene_ids_new_60", "c5_screen_summary_sha256", "b72_manifest_sha256",
                            "training_steps", "optimizer_steps", "parameter_or_seed_search",
                            "new_B_sorties", "TEST_accessed", "automatic_retry"],
        "exact_scene_order_source": {"path": str(c3_lock_path.resolve()), "sha256": sha(c3_lock_path), "field": "scene_ids_all_72 filtered to exclude scene_ids_reuse_12 while preserving order"},
        "plant_authorized_by_this_contract": False,
    }
    release_contract_path = EXP / "C5_DEV72_PARENT_RELEASE_CONTRACT_v2.json"
    if release_contract_path.is_file():
        assert read_json(release_contract_path) == release_contract
    else:
        release_contract_path.write_text(json.dumps(release_contract, indent=2) + "\n", encoding="utf-8")
    source_files["parent_release_contract"] = ref(release_contract_path)

    lock = {
        "schema": "C5_AXIS_COORDINATE_DEV72_INPUT_LOCK_V2",
        "state": "LOCKED_C5_M110_DEV72_NO_PLANT_WAIT_PARENT_RELEASE_V2",
        "plant_authorized_by_this_lock": False,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "repo_root": str(ROOT.resolve()),
        "taskbook_sha256": taskbook["sha256"],
        "c3_input_lock_sha256": sha(c3_lock_path),
        "c5_input_lock_sha256": sha(c5_lock_path),
        "b72_input_lock_sha256": sha(b72_lock_path),
        "c5_screen_summary_sha256": sha(c5_screen_summary_path),
        "b72_scoring_manifest_sha256": sha(b72_manifest_path),
        "candidate_identity": dict(c5_lock["candidate_identity"]),
        "candidate": contract["candidate"], "coordinate_mask": [1, 1, 0],
        "pcf_auxiliary_enabled": True,
        "source_files": source_files,
        "source_counts": {"total": len(active), "matlab": 31, "mat": 1},
        "active_source_inventory": active,
        "upstream_refs": upstream_refs,
        "shared_input_files": shared_inputs,
        "scene_ids_all_72": all_ids, "scene_ids_new_60": new_ids, "scene_ids_reuse_12": reuse_ids,
        "counts": {"total": 72, "new_c5_plants": 60, "c5_reuse": 12, "physical_fields_per_scene": 14},
        "c5_screen_gates": c5_screen_summary["gates"],
        "json_audit": {"c3_ledger_rows": len(ledger_rows), "b72_manifest_rows": len(b_rows),
                       "c5_screen_audits": len(c5_screen_summary["audits"]),
                       "status_jsons_checked": 60 + 72 + 12 + 12,
                       "all_screen_events": c5_screen_summary["event_count"],
                       "c5_gate_status": c5_screen_summary["status"]},
        "scenes": scenes,
        "limitations": ["This lock authorizes no Plant calls.",
                        "The 60-scene batch still requires a distinct parent release.",
                        "C3 B_source entries are physical inputs only, never B comparator outputs."]}

    lock_path = EXP / "C5_DEV72_INPUT_LOCK_v2.json"
    assert not lock_path.exists(), "Preserve an existing lock and use a new version."
    lock_path.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")

    binding = {
        "schema": "C5_AXIS_COORDINATE_DEV72_SOURCE_BINDING_V2",
        "state": "SOURCE_BOUND_C5_DEV72_WAIT_PARENT_REVIEW_V2",
        "input_lock_path": str(lock_path.resolve()), "input_lock_sha256": sha(lock_path),
        "run_contract_path": str(contract_path.resolve()), "run_contract_sha256": sha(contract_path),
        "prepare_entry_path": source_files["prepare_entry"]["path"],
        "prepare_entry_sha256": source_files["prepare_entry"]["sha256"],
        "runner_path": source_files["batch_runner"]["path"],
        "runner_sha256": source_files["batch_runner"]["sha256"],
        "plant_launcher_path": source_files["plant_launcher"]["path"],
        "plant_launcher_sha256": source_files["plant_launcher"]["sha256"],
        "no_plant_launcher_path": source_files["no_plant_launcher"]["path"],
        "no_plant_launcher_sha256": source_files["no_plant_launcher"]["sha256"],
        "release_contract_sha256": source_files["parent_release_contract"]["sha256"],
        "active_source_count": len(active), "shared_input_count": len(shared_inputs),
        "scene_ids_all_72": all_ids, "scene_ids_new_60": new_ids, "scene_ids_reuse_12": reuse_ids,
        "coordinate_mask": [1, 1, 0], "source_files": source_files,
        "upstream_ref_sha256": {k: v["sha256"] for k, v in upstream_refs.items() if isinstance(v, dict) and "sha256" in v},
    }
    binding_path = EXP / "C5_DEV72_SOURCE_BINDING_v2.json"
    assert not binding_path.exists(), "Preserve an existing source binding and version it."
    binding_path.write_text(json.dumps(binding, indent=2) + "\n", encoding="utf-8")

    for item in source_files.values():
        if isinstance(item, dict) and "path" in item:
            verify_ref(item)
    print(json.dumps({"status": "INPUTS_FROZEN_WAIT_PARENT_REVIEW", "input_lock": ref(lock_path),
                      "contract": ref(contract_path), "source_binding": ref(binding_path),
                      "scenes": len(scenes), "new": len(new_ids), "reuse": len(reuse_ids),
                      "checked_status_jsons": lock["json_audit"]["status_jsons_checked"]}, indent=2))


if __name__ == "__main__":
    main()
