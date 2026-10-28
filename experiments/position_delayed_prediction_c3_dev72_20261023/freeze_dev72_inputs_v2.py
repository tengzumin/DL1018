"""Assemble the frozen, read-only C3 DEV72 source/input lock from reviewed records."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PARENT = ROOT / "reports" / "delayed_prediction_c3_dev72_parent_20261023"
SCOPE_DIR = ROOT / "reports" / "delayed_prediction_c3_parent_20261023"
C3 = ROOT / "experiments" / "position_delayed_prediction_c3_20261023"
LOCK_OUT = HERE / "C3_DEV72_INPUT_LOCK_v2.json"
CONTRACT_OUT = HERE / "C3_DEV72_RUN_CONTRACT_v2.json"

PINS = {
    "authorization": (PARENT / "USER_AUTHORIZATION.json", "df887c68d29aa7d8d6f054a9b89e3722a7f55074deab2f147fd34f5a3892338d"),
    "taskbook": (SCOPE_DIR / "NEXT_DEV72_TASKBOOK_DRAFT_ZH.md", "8ca9e44022fdc5c0f6e7882ed94c4132d7979a6f453e721f5aa94e698ea20a1b"),
    "scope": (SCOPE_DIR / "DEV72_SCENE_SCOPE_DRAFT.json", "b9bd309ab6cbd74d4a46044c03744aab669b620aedbd23911e3d0a36e6cec100"),
    "history_manifest": (PARENT / "PARENT_HISTORICAL_216_MANIFEST.json", "8ba7c412452f35a727c862ec6ff5e7fa932d2c34d084574ce756bf63e5308dfe"),
    "history_review": (PARENT / "PARENT_HISTORICAL_216_RAW_REVIEW.json", "bc749164b9384f4b0bd875884e0e47d5fb318e236f1b6ac1a03fc0f5f04df98e"),
    "b_scene_payload_review": (PARENT / "PARENT_B72_SCENE_PAYLOAD_REVIEW.json", "76e8e4bfce0fd31ad2fb18dafc91b4669e558d9e49de5c111701d490449c4ce6"),
    "c3_source_lock": (C3 / "C3_SOURCE_LOCK.json", "863328963959c63d4628060fcff21e01d5322c487d077b5c20721d24ed9314a2"),
    "c3_run_contract": (C3 / "C3_RUN_CONTRACT.json", None),
    "c3_prepare_result": (C3 / "C3_PREPARE_RESULT.json", "b844c86de21d321d9cc03d1ef6dd69dfeecb9aa45e71f5589bf6eb7ec7602fb3"),
    "c3_snapshot": (C3 / "C3_PREPARED_CONFIG_OPTS.mat", "71c95e5cb9cc537fcc1fc2ea82f86c78c0f3f624de4de7a00951127950d4a64e"),
    "c3_probe_release": (C3 / "C3_PROBE_RELEASE.json", "ad457b2bb9515b3b7f2d66edcde9945d372b6ea168e43f21e7090cce0f5d54fb"),
    "c3_continue_release_v2": (C3 / "C3_CONTINUE_RELEASE_v2.json", "816baa148451c74b59cbb2f100cbdc5c1a122610ca2b6d582eb4635612cd600e"),
    "c3_continue_progress": (C3 / "C3_CONTINUE_PROGRESS.json", None),
    "c3_probe_raw_audit": (SCOPE_DIR / "PROBE_RAW_AUDIT.json", None),
    "all12_paired": (SCOPE_DIR / "PARENT_ALL12_PAIRED.csv", None),
    "all12_q_summary": (SCOPE_DIR / "PARENT_ALL12_Q_SUMMARY.json", None),
    "v1_input_lock": (HERE / "C3_DEV72_INPUT_LOCK.json", "cb951ae10e4e21ceb07e8491c9a41b0506f1c4dce6cf02937ca9ae8df945c251"),
    "v1_contract": (HERE / "C3_DEV72_RUN_CONTRACT.json", "84c1c54b286ccd2d074832c247b22e46e2861b9ccf390d587323f3f1d02352e5"),
    "v1_checkcode": (HERE / "C3_DEV72_CHECKCODE.mat", "5531c492fd2c935375312010439d48cdfcc76b5c21b22418394807a2f43ef172"),
    "failed_attempt_01": (HERE / "C3_DEV72_FAILED_PREPARE_ATTEMPT_01.json", "4b18b18b27918f990bc0e099519ebaa979a4dfb2d846e732c82b266e92e4e9c0"),
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def ref(path: Path, expected: str | None = None) -> dict:
    actual = sha256(path)
    if expected is not None and actual.lower() != expected.lower():
        raise RuntimeError(f"SHA mismatch: {path} expected={expected} actual={actual}")
    return {"path": str(path.resolve()), "sha256": actual}


def unique_by_scene(rows: list[dict], label: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in rows:
        key = row["scene_id"]
        if key in out:
            raise RuntimeError(f"duplicate {label} scene: {key}")
        out[key] = row
    return out


def main() -> None:
    if LOCK_OUT.exists() or CONTRACT_OUT.exists():
        raise RuntimeError("Refusing to overwrite frozen contract/input lock")

    refs = {name: ref(path, expected) for name, (path, expected) in PINS.items()}
    auth = read_json(PINS["authorization"][0])
    scope = read_json(PINS["scope"][0])
    hist = read_json(PINS["history_manifest"][0])
    review = read_json(PINS["history_review"][0])
    payload_review = read_json(PINS["b_scene_payload_review"][0])
    c3_lock = read_json(PINS["c3_source_lock"][0])
    c3_contract = read_json(PINS["c3_run_contract"][0])
    c3_prepare = read_json(PINS["c3_prepare_result"][0])
    c3_probe_release = read_json(PINS["c3_probe_release"][0])
    c3_continue_release = read_json(PINS["c3_continue_release_v2"][0])
    c3_progress = read_json(PINS["c3_continue_progress"][0])
    failed_attempt = read_json(PINS["failed_attempt_01"][0])
    v1_lock = read_json(PINS["v1_input_lock"][0])

    if auth.get("status") != "USER_AUTHORIZED_MAX_60_FROZEN_C3_DEV72_SORTIES" or auth.get("max_new_Plant") != 60:
        raise RuntimeError("The active user authorization does not authorize exactly the requested 60-sortie stage")
    if auth.get("new_training") != 0 or auth.get("parameter_or_seed_search") or auth.get("new_B_sorties") != 0 or auth.get("TEST_authorized"):
        raise RuntimeError("Authorization scope unexpectedly includes training, search, new B, or TEST")
    if scope.get("n_total") != 72 or scope.get("n_reuse_C3") != 12 or scope.get("n_proposed_new_C3") != 60:
        raise RuntimeError("Frozen scope counts differ from 72=12+60")
    scope_rows = scope["rows"]
    ids = [row["scene_id"] for row in scope_rows]
    if len(set(ids)) != 72 or ids != sorted(ids):
        raise RuntimeError("Scope IDs must be 72 unique canonical IDs in dictionary order")
    new_ids = [r["scene_id"] for r in scope_rows if r["candidate_action"] == "PROPOSE_NEW_C3_RUN"]
    reuse_ids = [r["scene_id"] for r in scope_rows if r["candidate_action"] == "REUSE_C3_SCREEN"]
    if len(new_ids) != 60 or len(reuse_ids) != 12:
        raise RuntimeError("Scope action counts are not exactly 60 new and 12 reused")
    if hist.get("scope") != "HISTORICAL_DEV72_ONLY_NO_TEST" or len(hist.get("rows", [])) != 216:
        raise RuntimeError("Historical manifest is not the audited DEV72-only 216-row inventory")
    if review.get("status") != "PASS_RAW_IDENTITIES_METRICS_AND_PAIRED_EXTERNAL_INPUTS" or len(review.get("rows", [])) != 216:
        raise RuntimeError("Independent historical raw review is not PASS for all 216 records")
    if review.get("manifest_sha256", "").lower() != refs["history_manifest"]["sha256"].lower():
        raise RuntimeError("Historical raw review does not bind the pinned 216-row manifest")
    if payload_review.get("status") != "PASS_ALL72_REPLAY_SCENE_EQUALS_SCORED_B_INPUTS" or len(payload_review.get("rows", [])) != 72:
        raise RuntimeError("B replay source-to-scored-input identity review is not PASS for all 72 scenes")

    hist_by_scene: dict[str, dict[str, dict]] = {}
    review_by_key: dict[tuple[str, str], dict] = {}
    for row in hist["rows"]:
        hist_by_scene.setdefault(row["scene_id"], {})[row["method"]] = row
    for row in review["rows"]:
        review_by_key[(row["scene_id"], row["method"])] = row
    payload_by_scene = unique_by_scene(payload_review["rows"], "B payload review")
    if set(hist_by_scene) != set(ids) or set(payload_by_scene) != set(ids):
        raise RuntimeError("Historical raw or B payload identities do not cover the exact scope IDs")
    methods = {"B", "DSSM14", "KAN14"}
    for scene_id in ids:
        methods_here = hist_by_scene[scene_id]
        if set(methods_here) != methods:
            raise RuntimeError(f"Missing/extra historical methods for {scene_id}: {sorted(methods_here)}")
        external = set()
        for method, item in methods_here.items():
            audited = review_by_key.get((scene_id, method))
            if not audited or audited["path"] != item["path"] or audited["sha256"].lower() != item["sha256"].lower():
                raise RuntimeError(f"Independent review path/SHA mismatch: {scene_id}/{method}")
            external.add(audited["external_identity_sha256"])
        if len(external) != 1:
            raise RuntimeError(f"B/DSSM/KAN external input identity differs: {scene_id}")
        b = methods_here["B"]
        payload = payload_by_scene[scene_id]
        if payload["path"] != b["path"] or payload["sha256"].lower() != b["sha256"].lower():
            raise RuntimeError(f"B payload review does not refer to historical B source: {scene_id}")
        if len(payload.get("matching_fields", [])) != 14:
            raise RuntimeError(f"Expected 14 physical fields in B-to-scored-log review: {scene_id}")

    if c3_lock.get("schema") != "C3_DELAYED_PREDICTION_SOURCE_LOCK_V1":
        raise RuntimeError("Frozen C3 source lock schema differs")
    if c3_prepare.get("status") != "PREPARED_WAIT_PARENT_PROBE_RELEASE" or c3_prepare.get("plant_calls") != 0:
        raise RuntimeError("Frozen C3 no-Plant preparation evidence is missing")
    if c3_probe_release.get("state") != "APPROVED_C3_PROBE" or c3_continue_release.get("state") != "APPROVED_C3_CONTINUE":
        raise RuntimeError("Frozen C3 probe/continue releases are not the reviewed successful versions")
    if c3_progress.get("status") != "ALL_11_COMPLETE_RAW_PENDING_AUDIT" or c3_progress.get("completed_scene_count") != 11:
        raise RuntimeError("Frozen C3 continuation does not document exactly 11 completed scenes")
    if failed_attempt.get("status") != "FAILED_NO_PLANT_CONTRACT_SHA_MISMATCH" or failed_attempt.get("plant_calls") != 0:
        raise RuntimeError("The preserved v1 failure record is missing or records a Plant call")
    if failed_attempt.get("contract_sha256_pinned", "").lower() != v1_lock["source_files"]["contract"]["sha256"].lower() or \
            failed_attempt.get("contract_sha256_actual", "").lower() != refs["v1_contract"]["sha256"].lower():
        raise RuntimeError("The preserved v1 failed contract identity does not match its lock and actual file")
    if failed_attempt.get("checkcode_sha256", "").lower() != refs["v1_checkcode"]["sha256"].lower():
        raise RuntimeError("The preserved v1 checkcode record does not bind its actual output")
    c3_ids = list(c3_lock["scene_ids"])
    if len(c3_ids) != 12 or set(c3_ids) != set(reuse_ids):
        raise RuntimeError("Reused scope IDs differ from the frozen C3 VAL12 identities")
    if list(c3_progress["scene_ids"]) != c3_ids[1:] or len(c3_progress["runs"]) != 11:
        raise RuntimeError("C3 continuation scene order/status inventory differs")

    c1_lock = read_json(Path(c3_lock["c1_source_lock"]["path"]))
    c1_scenes = unique_by_scene(c1_lock["shared_scenes"], "C1 C3 scene")
    if set(c1_scenes) != set(c3_ids):
        raise RuntimeError("C1 frozen source does not cover exact C3 reused scene IDs")
    c3_statuses: dict[str, dict] = {}
    probe_id = c3_ids[0]
    probe_dir = C3 / "runs_c3" / probe_id / c3_contract["candidate_condition_id"] / "attempt_01"
    c3_statuses[probe_id] = read_json(probe_dir / "run_status.json")
    for row in c3_progress["runs"]:
        c3_statuses[row["scene_id"]] = row
    if set(c3_statuses) != set(c3_ids):
        raise RuntimeError("C3 status records do not cover all 12 reused scenes")

    scene_records = []
    for scope_row in scope_rows:
        scene_id = scope_row["scene_id"]
        method_rows = hist_by_scene[scene_id]
        b_row = method_rows["B"]
        rec = {
            "scene_id": scene_id,
            "source_split": scope_row["source_split"],
            "task": scope_row["task"],
            "candidate_action": scope_row["candidate_action"],
            "B_source": {"path": b_row["path"], "sha256": b_row["sha256"], "expected_Q_m": b_row["expected_Q_m"]},
            "historical_comparators": {
                m: {"path": method_rows[m]["path"], "sha256": method_rows[m]["sha256"], "expected_Q_m": method_rows[m]["expected_Q_m"]}
                for m in ("B", "DSSM14", "KAN14")
            },
            "external_identity_sha256": next(iter({review_by_key[(scene_id, m)]["external_identity_sha256"] for m in methods})),
            "b_scene_to_scored_log": {"path": payload_by_scene[scene_id]["path"], "sha256": payload_by_scene[scene_id]["sha256"], "matching_fields": payload_by_scene[scene_id]["matching_fields"]},
            "C3_reuse": None,
        }
        if scene_id in reuse_ids:
            b_input = c1_scenes[scene_id]
            status = c3_statuses[scene_id]
            c3_status_path = Path(status["run_status_path"])
            status_ref = ref(c3_status_path, scope_row["C3_status_sha256"])
            expected_raw_sha = status["raw_sha256"]
            if status.get("status") != "RUN_COMPLETE_RAW_PENDING_AUDIT" or status.get("log_status") != "STABLE" or int(status.get("plant_calls", 1)) != 1:
                raise RuntimeError(f"C3 reused status not complete/stable/one-call: {scene_id}")
            c3_b_sha = status.get("B_raw_sha256", b_input["b_raw_sha256"])
            if c3_b_sha.lower() != b_row["sha256"].lower() or b_input["b_raw_sha256"].lower() != b_row["sha256"].lower():
                raise RuntimeError(f"Reused C3 input B raw SHA differs from historical B raw: {scene_id}")
            if status["raw_path"] != scope_row["C3_existing_raw_path"] or expected_raw_sha.lower() != scope_row["C3_existing_raw_sha256"].lower():
                raise RuntimeError(f"C3 reused raw/status differs from the frozen scope row: {scene_id}")
            raw_path = Path(status["raw_path"])
            if not raw_path.is_file() or raw_path.stat().st_size != int(status["raw_bytes"]) or sha256(raw_path).lower() != scope_row["C3_existing_raw_sha256"].lower():
                raise RuntimeError(f"C3 reused raw actual SHA/size differs from the frozen scope row: {scene_id}")
            for fkey, sha_key in (("run_start_path", "run_start_sha256"), ("first_plant_step_marker_path", "first_plant_step_marker_sha256")):
                path = Path(status[fkey])
                if not path.is_file() or sha256(path).lower() != status[sha_key].lower():
                    raise RuntimeError(f"C3 reused {fkey} hash mismatch: {scene_id}")
            rec["C3_reuse"] = {
                "status_path": str(c3_status_path.resolve()), "status_sha256": status_ref["sha256"],
                "raw_path": status["raw_path"], "raw_sha256": expected_raw_sha,
                "scope_raw_path": scope_row["C3_existing_raw_path"], "scope_raw_sha256": scope_row["C3_existing_raw_sha256"],
                "scope_status_sha256": scope_row["C3_status_sha256"],
                "run_start_path": status["run_start_path"], "run_start_sha256": status["run_start_sha256"],
                "first_plant_step_marker_path": status["first_plant_step_marker_path"],
                "first_plant_step_marker_sha256": status["first_plant_step_marker_sha256"],
                "B_raw_path": status.get("B_raw_path", b_input["b_raw_path"]),
                "B_raw_sha256": c3_b_sha,
                "source_lock_sha256": status["source_lock_sha256"],
                "release_sha256": status.get("continuation_release_sha256", status.get("release_sha256", c3_probe_release.get("sha256", ""))),
            }
        scene_records.append(rec)

    contract = {
        "schema": "C3_DELAYED_PREDICTION_DEV72_RUN_CONTRACT_V1",
        "state": "FIXED_60_PLUS_12_REUSE_NO_PLANT_PENDING_RELEASE",
        "candidate_condition_id": c3_contract["candidate_condition_id"],
        "candidate": c3_contract["candidate"],
        "scene_ids_all_72": ids,
        "scene_ids_new_60": new_ids,
        "scene_ids_reuse_12": reuse_ids,
        "authorization": {"max_new_Plant": 60, "new_training": 0, "parameter_or_seed_search": False, "new_B_sorties": 0, "TEST_authorized": False, "new_output_cap_bytes": auth["new_output_cap_bytes"], "minimum_free_bytes": auth["minimum_free_bytes"], "hard_deadline_utc": auth["hard_deadline_utc"]},
        "execution": {"attempts_per_new_scene": 1, "fixed_order": "canonical_scene_id_dictionary_order", "stop_on_failure_or_non_STABLE": True, "automatic_retry": False, "shared_lock": "try_only", "plant_authorized_by_this_contract": False},
    }
    for path in (HERE / "run_c3_dev72_v2.m", HERE / "prepare_c3_dev72_v2.m", HERE / "run_episode_dl1018.m", HERE / "run_dl1018_closed_loop.m", HERE / "delayed_prediction_step_candidate.m"):
        if not path.is_file():
            raise RuntimeError(f"Required frozen source/entry does not exist: {path}")
    copied = []
    for filename, role in (("run_episode_dl1018.m", "episode_wrapper"), ("run_dl1018_closed_loop.m", "runtime_core"), ("delayed_prediction_step_candidate.m", "prediction_helper")):
        copied.append({"role": role, **ref(HERE / filename)})
    contract_bytes = (json.dumps(contract, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    contract_sha = hashlib.sha256(contract_bytes).hexdigest()
    source_files = {
        "runner": {"path": str((HERE / "run_c3_dev72_v2.m").resolve()), "sha256": sha256(HERE / "run_c3_dev72_v2.m")},
        "prepare_entry": {"path": str((HERE / "prepare_c3_dev72_v2.m").resolve()), "sha256": sha256(HERE / "prepare_c3_dev72_v2.m")},
        "input_lock_builder": {"path": str(Path(__file__).resolve()), "sha256": sha256(Path(__file__).resolve())},
        "contract": {"path": str(CONTRACT_OUT.resolve()), "sha256": contract_sha},
        "isolated_c3_sources": copied,
    }
    c3_refs = {name: ref(path, expected) for name, (path, expected) in PINS.items() if name.startswith("c3_")}
    lock = {
        "schema": "C3_DELAYED_PREDICTION_DEV72_INPUT_LOCK_V1",
        "state": "LOCKED_INPUTS_AND_SOURCES_NO_PLANT_PARENT_REVIEW_REQUIRED",
        "plant_authorized_by_this_lock": False,
        "repo_root": str(ROOT.resolve()),
        "created_utc": "2026-10-23",
        "authorization_and_scope_refs": {name: refs[name] for name in ("authorization", "taskbook", "scope")},
        "historical_review_refs": {name: refs[name] for name in ("history_manifest", "history_review", "b_scene_payload_review")},
        "c3_reference_refs": c3_refs,
        "previous_attempt_refs": {name: refs[name] for name in ("v1_input_lock", "v1_contract", "v1_checkcode", "failed_attempt_01")},
        "candidate_condition_id": c3_contract["candidate_condition_id"],
        "candidate_identity": c3_prepare["model_identity"],
        "source_files": source_files,
        "frozen_runtime_files": c3_lock["frozen_runtime_files"],
        "frozen_plant_files": c3_lock["frozen_plant_files"],
        "shared_input_files": c3_lock["shared_input_files"],
        "c3_source_lock": c3_lock,
        "scene_ids_all_72": ids,
        "scene_ids_new_60": new_ids,
        "scene_ids_reuse_12": reuse_ids,
        "counts": {"total": 72, "new": 60, "reuse": 12, "historical_raw_rows": 216, "physical_fields_per_scene": 14},
        "limitations": [
            "The historical B run-level runtime-source identity gap remains disclosed by user authorization/taskbook.",
            "No C2 run_start exists for the remaining 60 historical B scenes; frozen C3 cfg/opts identity is compared against all 12 available C2 run_start records. B runtime options are not asserted equal to the C3/C2 controller options.",
            "Historical raw Q values and 216 raw hashes are bound to the independent parent review; they are not recalculated by this input-lock builder.",
        ],
        "scenes": scene_records,
    }
    CONTRACT_OUT.write_bytes(contract_bytes)
    LOCK_OUT.write_bytes((json.dumps(lock, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(json.dumps({"status": "LOCK_ASSEMBLED_NO_PLANT", "scenes": len(scene_records), "new": len(new_ids), "reuse": len(reuse_ids), "history_raw_rows": len(hist["rows"]), "input_lock": str(LOCK_OUT), "input_lock_sha256": sha256(LOCK_OUT), "contract_sha256": sha256(CONTRACT_OUT), "runner_sha256": source_files["runner"]["sha256"], "prepare_sha256": source_files["prepare_entry"]["sha256"]}, indent=2))


if __name__ == "__main__":
    main()
