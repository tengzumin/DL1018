"""Offline parent audit for the locked C5_NO_DELAYED_PREDICTION DEV72 raws."""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PREP_DIR = Path(__file__).resolve().parent
EXP_DIR = ROOT / "experiments/position_c5_matched_ablations_dev72_v3_20261023/C5_NO_DELAYED_PREDICTION"
REVIEW_DIR = ROOT / "reports/paper_continuation_20261023/c5_matched_ablation_parent_raw_review"
SCORE_TABLE = ROOT / "reports/paper_continuation_20261023/c5_all_method_dev_comparison/SCENE_METHOD_METRICS.csv"
VARIANT = "C5_NO_DELAYED_PREDICTION"
CANDIDATE = "C5_AXIS_MIXED_COORDINATE_M110"
W0_SHA = "88f8c4f2495438c3797655c48bab1bf0c11ac2e27bff1f5f2a7423a8f0a2cf53"
NORMALIZER_SHA = "533aad9a2c66874cfa67f5d268661835e81e58b797cba7d6fc1c12d4013de5f0"
C5_M110_PARENT_AUDIT_SHA = "bb34889559d95a1c995d4d420e3b3d7a702908b58b47cce969dc508a1c697fab"
EXPECTED_HASHES = {
    "experiments/position_c5_matched_ablations_dev72_v3_20261023/C5_NO_DELAYED_PREDICTION/C5_ABLATION_DEV72_INPUT_LOCK_v3.json": "e0020306b8b7e7fba2948b93cbde30e0ec8f8470ede5dcef5e128d20c8728074",
    "experiments/position_c5_matched_ablations_dev72_v3_20261023/C5_NO_DELAYED_PREDICTION/C5_ABLATION_DEV72_REUSE12_BINDING_v3.json": "123f56a288469b5fdf403db09d9d63cab2ca3300283a9fbda6a54df833d83494",
    "experiments/position_c5_matched_ablations_dev72_v3_20261023/C5_NO_DELAYED_PREDICTION/C5_ABLATION_DEV72_REMAINING60_BATCH_STATUS_v3.json": "4527c178d5d3cfe10ff3c4546bae5cb9fdfd7d8fbb2531bedd119dfaf9b91cc9",
    "experiments/position_c5_matched_ablations_dev72_v3_20261023/C5_NO_DELAYED_PREDICTION/C5_ABLATION_DEV72_REMAINING60_BODY_COMPLETE_v3.json": "f54d3f1cbe80da43e73cc90d1cebbb8fb397d3d1cf862d9941097eec4d756577",
    "experiments/position_c5_matched_ablations_dev72_v3_20261023/C5_NO_DELAYED_PREDICTION/C5_ABLATION_DEV72_SOURCE_BINDING_v3.json": "db605d55641ddda3c34d3cb6694a678678b683076951f836b58edc79db6ec06f",
    "experiments/position_c5_matched_ablations_dev72_v3_20261023/C5_NO_DELAYED_PREDICTION/C5_ABLATION_DEV72_RUN_CONTRACT_v3.json": "91669018d3d5f19a29c7162f4ed307f7f7371850ff0ffe647fe86bc49825bbcc",
    "experiments/position_c5_matched_ablations_dev72_v3_20261023/C5_NO_DELAYED_PREDICTION/C5_ABLATION_DEV72_PREPARE_RESULT_v3.json": "a2354004c3dd4b73eadf7a425e4fdaab7245b8b526728f6eb846e5cb74a36d4a",
    "experiments/position_c5_matched_ablations_dev72_v3_20261023/C5_NO_DELAYED_PREDICTION/C5_ABLATION_DEV72_RUNNER_PREFLIGHT_v3.json": "69af04e654c076781774994d04b6a11d709f8eb1a49f4da30aaf93ef9feda43a",
    "experiments/position_c5_matched_ablations_dev72_v3_20261023/C5_NO_DELAYED_PREDICTION/C5_ABLATION_DEV72_PARENT_RELEASE_CONTRACT_v3.json": "3f2b7071d69d41a7ccc56620939ea3e6bb12aefab753eb51c861899044289988",
    "experiments/position_c5_matched_ablations_dev72_v3_20261023/C5_NO_DELAYED_PREDICTION/C5_ABLATION_DEV72_REMAINING60_PARENT_RELEASE_v3.json": "e100d3db73248cd870e62a7d48cf1cf304099a3b2adc81f5cd3f27eca91415cf",
    "reports/paper_continuation_20261023/c5_matched_ablation_parent_raw_review/C5_NO_DELAYED_PREDICTION_SCREEN12_RAW_PARENT_AUDIT_v1.json": "807aaedda90638fe03915293f80cc7ed979366d7de94e5a3f68b1d68f3660343",
    "reports/paper_continuation_20261023/c5_matched_ablation_parent_raw_review/C5_NO_DELAYED_PREDICTION_FIRST_RAW_PARENT_AUDIT_v1.json": "d0d0f3f2fa38f5499aca53c642a1ec65d20758bbc18e67cba2d55fede6e6289d",
    "reports/paper_continuation_20261023/c5_matched_ablation_parent_raw_review/event_audit_c5_matched_ablation.py": "1a8106ca6df7bb75ecb7a9cf5a09b9f91bc6eaa38547917a1fab677092c3755a",
    "reports/paper_continuation_20261023/c5_matched_ablation_parent_raw_review/audit_c5_matched_ablation_screen12_raw.py": "426e1dc6f380b2a9caa95cea748f1db8d64ac7ac6d3c91d3bd22011a7f6e7380",
    "reports/paper_continuation_20261023/c5_dev72_parent_review/audit_c5_dev72_raw_parent_v4.py": "d82e089c7d41f39c620daea63d95315632e6fb2f80addf4dc12e6a4603b8e57e",
    "reports/paper14_v2/phase1/audit_w15_position_replay.py": "372d92cb17da99884e742d3fa0c877200c3bb2bc6fac7f10e7a1a046b97a76af",
    "reports/delayed_prediction_c3_dev72_parent_20261023/parent_raw_metrics.py": "c64482d0adbc4358417648ec08351bd78f1d3dbdb38950435fa71b9cb0f531b1",
    "reports/paper_continuation_20261023/c5_all_method_dev_comparison/SCENE_METHOD_METRICS.csv": "a96f1754ba11acf760f6c0490d9452d8e5f03bac6ef49f9e1e78e82318d71416",
}

BASE_AUDITOR = ROOT / "reports/paper_continuation_20261023/c5_dev72_parent_review/audit_c5_dev72_raw_parent_v4.py"
DECODER = ROOT / "reports/paper14_v2/phase1/audit_w15_position_replay.py"
SCORER = ROOT / "reports/delayed_prediction_c3_dev72_parent_20261023/parent_raw_metrics.py"
EVENT_AUDIT = REVIEW_DIR / "event_audit_c5_matched_ablation.py"


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def pinned_path(relative: str) -> Path:
    return ROOT / Path(relative)


def verify_pins() -> dict[str, Path]:
    files = {}
    for relative, expected in EXPECTED_HASHES.items():
        path = pinned_path(relative)
        require(path.is_file(), f"missing pinned input: {path}")
        actual = sha(path)
        require(actual == expected, f"pinned SHA-256 mismatch: {path}: {actual}")
        files[Path(relative).name] = path
    return files


def import_pinned(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    require(spec is not None and spec.loader is not None, f"cannot load helper: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def same_path(left: str | Path, right: str | Path) -> bool:
    return Path(left).resolve() == Path(right).resolve()


def score_table(path: Path, lock: dict) -> dict[tuple[str, str], dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    require(len(rows) == 360, f"expected 360 baseline score rows, got {len(rows)}")
    result = {}
    for row in rows:
        key = (row["scene_id"], row["method_id"])
        require(key not in result, f"duplicate baseline score row: {key}")
        result[key] = row
    for method in ("B_TRACEABLE", "C3", "C5_M110"):
        require(sum(method_id == method for _, method_id in result) == 72,
                f"baseline score table row count is not 72 for {method}")
    for scene in lock["scenes"]:
        sid = scene["scene_id"]
        for method, locked in (
            ("B_TRACEABLE", scene["B72_scoring"]),
            ("C3", scene["C3_reference"]),
            ("C5_M110", scene["C5_reuse"]),
        ):
            row = result[(sid, method)]
            if method != "C5_M110" or locked["C5_reuse"]["reused"]:
                require(row["raw_sha256"].lower() == locked["raw_sha256"].lower(),
                        f"{sid} {method} raw SHA differs from locked identity")
            else:
                require(row["score_source"] == "C5_DEV72_RAW_PARENT_AUDIT_V3_METRICS"
                        and row["parent_audit_sha256"].lower() == C5_M110_PARENT_AUDIT_SHA
                        and row["event_check_sha256"].lower() == EXPECTED_HASHES[
                            "reports/paper_continuation_20261023/c5_dev72_parent_review/audit_c5_dev72_raw_parent_v4.py"],
                        f"{sid} C5_M110 score row is not bound to the frozen parent audit")
            require(row["external_identity_sha256"].lower() == scene["external_identity_sha256"].lower(),
                    f"{sid} {method} external identity mismatch")
            require(row["replay_cell_status"] == "REPLAY_VALID" and row["valid_replay_events"] == "1968",
                    f"{sid} {method} baseline row is not replay-valid")
    return result


def validate_reuse(lock: dict, binding: dict, screen: dict, first: dict, table: dict) -> list[dict]:
    require(binding["variant_id"] == VARIANT and binding["plant_calls_in_audit"] == 0,
            "reuse binding variant or Plant count mismatch")
    require(binding["TEST_accessed"] is False and binding["training_steps"] == binding["optimizer_steps"] == 0,
            "reuse binding includes TEST or training")
    require(binding["screen12_order"] == lock["scene_ids_reuse_12"], "reuse12 order differs from input lock")
    require(len(binding["records"]) == 12, "reuse binding must contain exactly 12 rows")
    require(screen["status"] == "PASS_C5_MATCHED_ABLATION_SCREEN12_ALL_EVENTS" and screen["screen12_complete"],
            "screen12 parent audit is not a complete pass")
    require(len(screen["screen12_rows"]) == 12 and len(screen["phase_rows"]) == 11,
            "screen12 audit row counts differ from the frozen scope")
    require(first["status"] == "PASS_C5_MATCHED_ABLATION_FIRST_RAW_ALL_EVENTS",
            "first raw audit is not a pass")
    audit_by_scene = {row["scene_id"]: row for row in screen["screen12_rows"]}
    require(len(audit_by_scene) == 12, "duplicate scene in screen12 audit")
    lock_by_scene = {row["scene_id"]: row for row in lock["scenes"]}
    reused = []
    for record in binding["records"]:
        sid = record["scene_id"]
        locked = lock_by_scene[sid]
        audited = audit_by_scene[sid]
        metric = audited["methods"][VARIANT]
        require(locked["C5_ABLATION_REUSE"]["reused"] is True, f"{sid} is not a locked C5 reuse")
        require(locked["C5_ABLATION_REUSE"]["variant_id"] == VARIANT, f"{sid} reuse variant mismatch")
        require(record["audit_status"] == "PASS_C5_MATCHED_ABLATION_SCREEN12_ALL_EVENTS" and record["event_count"] == 1968,
                f"{sid} reuse row is not event-audited")
        require(record["raw_sha256"].lower() == metric["sha256"].lower(), f"{sid} reused raw SHA mismatch")
        require(same_path(record["raw_path"], metric["path"]), f"{sid} reused raw path mismatch")
        require(audited["event_checks"]["event_count"] == 1968, f"{sid} reused event count mismatch")
        require(audited["provenance"]["external_identity_sha256"].lower() == locked["external_identity_sha256"].lower(),
                f"{sid} reused external identity mismatch")
        if record["phase"] == "FIRST_PILOT_REUSE":
            require(record["first_parent_audit_sha256"].lower() == EXPECTED_HASHES[
                "reports/paper_continuation_20261023/c5_matched_ablation_parent_raw_review/C5_NO_DELAYED_PREDICTION_FIRST_RAW_PARENT_AUDIT_v1.json"],
                f"{sid} first pilot audit SHA mismatch")
            require(record["raw_sha256"].lower() == first["run_artifacts"]["raw_sha256"].lower(),
                    f"{sid} first pilot raw SHA mismatch")
            require(record["run_status_sha256"].lower() == audited["provenance"]["pilot_status_sha256"].lower(),
                    f"{sid} first pilot run-status SHA mismatch")
        else:
            require(record["run_status_sha256"].lower() == audited["provenance"]["run_status_sha256"].lower(),
                    f"{sid} reused run-status SHA mismatch")
            require(record["run_start_sha256"].lower() == audited["provenance"]["run_start_sha256"].lower(),
                    f"{sid} reused run-start SHA mismatch")
        base_rows = {method: table[(sid, method)] for method in ("B_TRACEABLE", "C3", "C5_M110")}
        for method in base_rows:
            require(abs(float(metric["Q_0_20_m"]) - float(base_rows[method]["Q_0_20_m"]) - audited["deltas_Q_m"][method]) < 1e-12,
                    f"{sid} reused {method} score differs from the current score table")
        reused.append(make_score_row(sid, "PASS_REUSE_SHA", record["raw_sha256"], metric["Q_0_20_m"],
                                     base_rows, audited["event_checks"], record["run_status_sha256"],
                                     record["run_start_sha256"], metric["path"], 0))
    return reused


def make_score_row(sid: str, audit_status: str, raw_sha: str, q_value: float,
                   baseline: dict, event_checks: dict | None, status_sha: str,
                   start_sha: str, raw_path: str, batch_index: int) -> dict:
    q = float(q_value)
    values = {method: float(baseline[method]["Q_0_20_m"]) for method in ("B_TRACEABLE", "C3", "C5_M110")}
    deltas = {method: q - values[method] for method in values}
    return {
        "scene_id": sid, "audit_status": audit_status, "raw_path": str(raw_path),
        "raw_sha256": raw_sha.lower(), "run_status_sha256": status_sha.lower(),
        "run_start_sha256": start_sha.lower(), "event_count": 1968 if event_checks else 0,
        "batch_index": batch_index, "Q_0_20_m": q,
        "B_TRACEABLE_Q_0_20_m": values["B_TRACEABLE"], "C3_Q_0_20_m": values["C3"],
        "C5_M110_Q_0_20_m": values["C5_M110"],
        "delta_vs_B_TRACEABLE_m": deltas["B_TRACEABLE"], "delta_vs_C3_m": deltas["C3"],
        "delta_vs_C5_M110_m": deltas["C5_M110"], "event_checks": event_checks,
    }


def check_source_artifacts(base, row: dict) -> None:
    c3 = row["C3_reference"]
    require(c3["kind"] == "C3_DEV72_NEW", f"{row['scene_id']} is not bound to the new C3 DEV72 source")
    c3_status = base.verify_status_file(c3["run_status_path"], c3["run_status_sha256"],
                                        scene_id=row["scene_id"], raw_path=c3["raw_path"],
                                        raw_sha=c3["raw_sha256"])
    require(c3_status["schema"] == "C3_DELAYED_PREDICTION_DEV72_RUN_STATUS_V1",
            f"{row['scene_id']} C3 source status schema mismatch")
    for path_key, sha_key in (("raw_path", "raw_sha256"), ("run_start_path", "run_start_sha256"),
                              ("attempt_started_marker_path", "attempt_started_marker_sha256"),
                              ("first_plant_step_marker_path", "first_plant_step_marker_sha256")):
        path = Path(c3[path_key])
        require(path.is_file() and sha(path).lower() == c3[sha_key].lower(),
                f"{row['scene_id']} C3 {path_key} SHA mismatch")
        require(c3_status[path_key] == c3[path_key] and c3_status[sha_key].lower() == c3[sha_key].lower(),
                f"{row['scene_id']} C3 status {path_key}/SHA mismatch")
    b = row["B72_scoring"]
    b_status = base.verify_status_file(b["run_status_path"], b["run_status_sha256"],
                                       scene_id=row["scene_id"], raw_path=b["raw_path"], raw_sha=b["raw_sha256"])
    require(b_status["schema"] in ("B_TRACEABLE_C3CORE_RUN_STATUS_V2", "B_TRACEABLE_C3CORE_DEV72_RUN_STATUS_V3"),
            f"{row['scene_id']} B72 source status schema mismatch")
    physical = row["B_source"]
    require(Path(physical["path"]).is_file() and sha(physical["path"]).lower() == physical["sha256"].lower(),
            f"{row['scene_id']} physical B source SHA mismatch")


def audit_new_row(record: dict, lock_row: dict, batch: dict, digests: dict,
                  snapshot: dict, base, decoder, event_audit, scorer,
                  baseline_table: dict) -> dict:
    import numpy as np

    sid = record["scene_id"]
    require(record["status"] == "RUN_COMPLETE_RAW_PENDING_AUDIT" and record["plant_calls"] == 1,
            f"{sid} row is not a single completed run")
    require(record["batch_index"] >= 1, f"{sid} has an invalid batch index")
    expected_attempt = EXP_DIR / "runs_c5_matched_ablation_dev72_v3" / sid / VARIANT / "attempt_01"
    raw_path = Path(record["raw_path"])
    require(same_path(raw_path, expected_attempt / "raw_run.mat"), f"{sid} raw path escaped the v3 run tree")
    status_path = expected_attempt / "run_status.json"
    start_path = expected_attempt / "run_start.mat"
    require(same_path(record["run_status_path"], status_path), f"{sid} run-status path mismatch")
    require(same_path(record["run_start_path"], start_path), f"{sid} run-start path mismatch")
    require(raw_path.is_file() and sha(raw_path).lower() == record["raw_sha256"].lower(),
            f"{sid} raw SHA mismatch")
    status = base.verify_status_file(status_path, record["run_status_sha256"], scene_id=sid,
                                     raw_path=raw_path, raw_sha=record["raw_sha256"],
                                     require_event_counts=True,
                                     required_markers=("raw", "run_start", "attempt_started_marker", "first_plant_step_marker"))
    require(status["schema"] == "C5_MATCHED_ABLATION_RUN_STATUS_V1", f"{sid} run-status schema mismatch")
    require(status["phase"] == "REMAINING60" and status["variant_id"] == status["ablation_mode"] == VARIANT,
            f"{sid} run-status phase/variant mismatch")
    require(status["batch_id"] == batch["batch_id"] and status["batch_index"] == record["batch_index"],
            f"{sid} run-status batch identity mismatch")
    require(status["actual_weight_update_enabled"] is True and status["actual_prediction_gradient_enabled"] is False,
            f"{sid} run-status intervention flags mismatch")
    require(status["training_steps"] == status["optimizer_steps"] == 0 and status["TEST_accessed"] is False,
            f"{sid} run-status records training or TEST access")
    require(status["source_scene_id"] == sid and status["plant_calls"] == 1,
            f"{sid} run-status source scene or Plant count mismatch")
    for key, expected in digests.items():
        require(status[key].lower() == expected.lower(), f"{sid} run-status {key} mismatch")
    for key, expected in (("raw_path", raw_path), ("run_start_path", start_path)):
        require(same_path(status[key], expected), f"{sid} status {key} mismatch")
    for marker in ("attempt_started_marker", "first_plant_step_marker"):
        require(same_path(status[f"{marker}_path"], expected_attempt / f"{marker}.marker"),
                f"{sid} {marker} path mismatch")
        require(record[f"{marker}_sha256"].lower() == status[f"{marker}_sha256"].lower(),
                f"{sid} {marker} SHA differs between batch and run status")
    require(record["physical_B_source_sha256"].lower() == lock_row["B_source"]["sha256"].lower(),
            f"{sid} batch physical B SHA differs from lock")
    require(record["C3_raw_sha256"].lower() == lock_row["C3_reference"]["raw_sha256"].lower(),
            f"{sid} batch C3 SHA differs from lock")
    for key, ref in (("physical_B_source_path", lock_row["B_source"]),
                     ("C3_raw_path", lock_row["C3_reference"])):
        path_key = "path" if key == "physical_B_source_path" else "raw_path"
        sha_key = "sha256" if key == "physical_B_source_path" else "raw_sha256"
        require(same_path(status[key], ref[path_key]) and status[key.replace("_path", "_sha256")].lower() == ref[sha_key].lower(),
                f"{sid} run-status source {key} mismatch")
    require(start_path.is_file() and sha(start_path).lower() == record["run_start_sha256"].lower()
            == status["run_start_sha256"].lower(), f"{sid} run-start SHA mismatch")
    check_source_artifacts(base, lock_row)

    start = base.matlab_section_safe(start_path, "runStart", decoder)
    require(base.matlab_text(start["schema"]) == "C5_MATCHED_ABLATION_RUN_START_V1", f"{sid} run-start schema mismatch")
    require(base.matlab_text(start["batch_id"]) == batch["batch_id"]
            and base.matlab_scalar(start["batch_index"]) == record["batch_index"], f"{sid} run-start batch mismatch")
    require(base.matlab_text(start["phase"]) == "REMAINING60" and base.matlab_text(start["scene_id"]) == sid,
            f"{sid} run-start scene/phase mismatch")
    require(base.matlab_text(start["source_scene_id"]) == base.matlab_text(start["scene_identity"]["raw_scene_id"]) == sid,
            f"{sid} run-start source scene mismatch")
    require(base.matlab_text(start["variant_id"]) == base.matlab_text(start["ablation_mode"]) == VARIANT,
            f"{sid} run-start variant mismatch")
    require(base.matlab_text(start["candidate"]) == CANDIDATE and base.matlab_flat(start["coordinate_mask"]) == [1.0, 1.0, 0.0],
            f"{sid} run-start candidate/mask mismatch")
    require(base.matlab_text(start["W0_sha256"]).lower() == W0_SHA, f"{sid} run-start W0 mismatch")
    for key, expected in digests.items():
        start_key = {"source_binding_sha256": "source_binding_sha256", "release_sha256": "release_sha256",
                     "preflight_sha256": "preflight_sha256", "input_lock_sha256": "input_lock_sha256",
                     "run_contract_sha256": "run_contract_sha256", "prepare_result_sha256": "prepare_result_sha256",
                     "snapshot_sha256": "cfg_opts_snapshot_sha256"}[key]
        require(base.matlab_text(start[start_key]).lower() == expected.lower(), f"{sid} run-start {start_key} mismatch")
    require(base.matlab_scalar(start["plant_calls_before_invocation"]) == 0
            and base.matlab_scalar(start["training_steps"]) == base.matlab_scalar(start["optimizer_steps"]) == 0
            and base.matlab_scalar(start["TEST_accessed"]) in (0, False), f"{sid} run-start has Plant/training/TEST mismatch")
    expected_flags = {"actual_weight_update_enabled": True, "actual_prediction_gradient_enabled": False,
                      "legacy_stage1_update_enabled": True}
    for key, expected in expected_flags.items():
        require(bool(base.matlab_scalar(start[key])) is expected, f"{sid} run-start {key} mismatch")
    require(bool(base.matlab_scalar(start["initial_weight_reset_from_W0"]))
            and bool(base.matlab_scalar(start["controller_state_reset_for_scene"]),), f"{sid} reset flags mismatch")
    require(base.equal_tree(snapshot["cfg"], start["cfg"], decoder) == 120, f"{sid} cfg snapshot differs")
    require(base.equal_tree(snapshot["opts"], start["opts"], decoder, ignore_marker=True) == 43, f"{sid} opts snapshot differs")
    source_leaves = base.equal_tree(snapshot["sourceIdentity"], start["source_identity"], decoder)
    require(source_leaves > 0 and base.equal_tree(snapshot["modelIdentity"], start["model_identity"], decoder) == 6,
            f"{sid} model/source identity differs from snapshot")
    require(base.matlab_flat(snapshot["opts"]["position_coordinate_mask"]) == [1.0, 1.0, 0.0]
            and bool(base.matlab_scalar(snapshot["opts"]["position_delayed_prediction_enabled"]))
            and bool(base.matlab_scalar(snapshot["opts"]["stage1_position_runtime"]["update_enabled"]),),
            f"{sid} snapshot options differ from frozen intervention")
    active = lock_row["_active_source_inventory"]
    expected_paths = [item["path"] for item in active]
    expected_shas = [item["sha256"].lower() for item in active]
    source_identity = start["source_identity"]
    got_paths = [str(base.matlab_text(value)) for value in base.matlab_flat(source_identity["active_paths"])]
    got_shas = [str(base.matlab_text(value)).lower() for value in base.matlab_flat(source_identity["active_sha256"])]
    require(len(expected_paths) == len(got_paths) == len(got_shas) == 32, f"{sid} active source count mismatch")
    require([Path(p).resolve() for p in got_paths] == [Path(p).resolve() for p in expected_paths]
            and got_shas == expected_shas, f"{sid} run-start active sources differ from lock")
    w0 = np.asarray(snapshot["W0"], dtype=float)
    require(w0.shape == (33, 3) and np.array_equal(w0, np.asarray(start["W0"], dtype=float)),
            f"{sid} run-start initial W0 differs")
    require(hashlib.sha256(np.asarray(w0, dtype="<f8").tobytes(order="F")).hexdigest() == W0_SHA,
            f"{sid} W0 values do not match locked SHA")
    identity = snapshot["modelIdentity"]
    require(base.matlab_text(identity["model_id"]) == "DSSM14"
            and base.matlab_text(identity["W0_sha256"]).lower() == W0_SHA
            and base.matlab_text(identity["normalizer_arrays_sha256"]).lower() == NORMALIZER_SHA,
            f"{sid} model identity differs from contract")
    require(all(base.matlab_scalar(identity[key]) == value for key, value in
                (("input_dim", 14), ("window", 32), ("selected_step", 60000))), f"{sid} DSSM identity differs")
    scene_row = lock_row
    require(base.matlab_text(start["physical_B_source_path"]) == scene_row["B_source"]["path"]
            and base.matlab_text(start["physical_B_source_sha256"]).lower() == scene_row["B_source"]["sha256"].lower(),
            f"{sid} run-start physical B source mismatch")
    require(base.matlab_text(start["scene_identity"]["B_raw_path"]) == scene_row["B_source"]["path"]
            and base.matlab_text(start["scene_identity"]["B_raw_sha256"]).lower() == scene_row["B_source"]["sha256"].lower(),
            f"{sid} scene identity physical B mismatch")
    c3 = scene_row["C3_reference"]
    require(base.matlab_text(start["C3_raw_path"]) == c3["raw_path"]
            and base.matlab_text(start["C3_raw_sha256"]).lower() == c3["raw_sha256"].lower(),
            f"{sid} run-start C3 reference mismatch")
    scene_names = [str(base.matlab_text(value)) for value in base.matlab_flat(snapshot["sceneIdentity"]["scene_id"])]
    require(sid in scene_names, f"{sid} is absent from snapshot scene identity")
    base.compare_scene_identity(start["scene_identity"], base.scene_identity_row(snapshot["sceneIdentity"], scene_names.index(sid)), decoder)

    raw_identity = base.matlab_section_safe(raw_path, "runIdentity", decoder)
    for key, expected in expected_flags.items():
        require(bool(base.matlab_scalar(raw_identity[key])) is expected, f"{sid} raw identity {key} mismatch")
    for key, expected in (("schema", "C5_MATCHED_ABLATION_RUN_IDENTITY_V1"), ("variant_id", VARIANT),
                          ("ablation_mode", VARIANT), ("scene_id", sid), ("candidate", CANDIDATE)):
        require(base.matlab_text(raw_identity[key]) == expected, f"{sid} raw identity {key} mismatch")
    require(base.matlab_flat(raw_identity["coordinate_mask"]) == [1.0, 1.0, 0.0]
            and base.matlab_text(raw_identity["W0_sha256"]).lower() == W0_SHA, f"{sid} raw identity mask/W0 mismatch")
    for key, expected in digests.items():
        raw_key = {"source_binding_sha256": "source_binding_sha256", "release_sha256": "release_sha256",
                   "preflight_sha256": "preflight_sha256", "input_lock_sha256": "input_lock_sha256",
                   "run_contract_sha256": "run_contract_sha256", "prepare_result_sha256": "prepare_result_sha256",
                   "snapshot_sha256": "cfg_opts_snapshot_sha256"}[key]
        require(base.matlab_text(raw_identity[raw_key]).lower() == expected.lower(), f"{sid} raw identity {raw_key} mismatch")
    require(base.matlab_text(raw_identity["run_start_sha256"]).lower() == record["run_start_sha256"].lower(),
            f"{sid} raw identity run-start SHA mismatch")
    require(base.matlab_text(raw_identity["external_identity_sha256"]).lower()
            == lock_row["external_identity_sha256"].lower(), f"{sid} raw external identity mismatch")
    require(base.equal_tree(snapshot["modelIdentity"], raw_identity["model_identity"], decoder) == 6
            and base.equal_tree(snapshot["sourceIdentity"], raw_identity["source_identity"], decoder) == source_leaves,
            f"{sid} raw source/model identity differs from snapshot")
    require(base.matlab_text(raw_identity["physical_B_source_path"]) == scene_row["B_source"]["path"]
            and base.matlab_text(raw_identity["physical_B_source_sha256"]).lower() == scene_row["B_source"]["sha256"].lower(),
            f"{sid} raw physical B source mismatch")
    require(base.matlab_text(raw_identity["C3_raw_path"]) == c3["raw_path"]
            and base.matlab_text(raw_identity["C3_raw_sha256"]).lower() == c3["raw_sha256"].lower(),
            f"{sid} raw C3 reference mismatch")
    require(base.matlab_scalar(raw_identity["training_steps"]) == base.matlab_scalar(raw_identity["optimizer_steps"]) == 0
            and base.matlab_scalar(raw_identity["TEST_accessed"]) in (0, False), f"{sid} raw identity records training or TEST")
    event_result = event_audit.audit_events(raw_path, start["cfg"], VARIANT, w0, W0_SHA)
    require(event_result["event_count"] == 1968 and event_result["actual_prediction_norm_max"] == 0,
            f"{sid} C5 event audit did not pass")
    candidate = scorer.score({"scene_id": sid, "method": VARIANT, "path": str(raw_path),
                              "sha256": record["raw_sha256"]})
    require(candidate["external_identity_sha256"].lower() == lock_row["external_identity_sha256"].lower(),
            f"{sid} rescored external identity mismatch")
    baseline = {method: baseline_table[(sid, method)] for method in ("B_TRACEABLE", "C3", "C5_M110")}
    return make_score_row(sid, "PASS_NEW_RAW_AUDIT", record["raw_sha256"], candidate["Q_0_20_m"],
                          baseline, event_result, record["run_status_sha256"], record["run_start_sha256"],
                          str(raw_path), record["batch_index"]), event_result


def preflight(output_dir: Path):
    require(__debug__, "run Python without -O; pinned helpers use assertions")
    require(output_dir.is_absolute(), "--output-dir must be absolute")
    require(output_dir.parent.resolve() == PREP_DIR.resolve(), "output must be a dedicated child of the audit-preparation folder")
    require(output_dir.name.startswith("audit_run_"), "output folder name must begin audit_run_")
    require(not output_dir.exists(), f"refusing existing output directory: {output_dir}")
    pinned = verify_pins()
    lock = load_json(pinned["C5_ABLATION_DEV72_INPUT_LOCK_v3.json"])
    binding = load_json(pinned["C5_ABLATION_DEV72_REUSE12_BINDING_v3.json"])
    batch = load_json(pinned["C5_ABLATION_DEV72_REMAINING60_BATCH_STATUS_v3.json"])
    body = load_json(pinned["C5_ABLATION_DEV72_REMAINING60_BODY_COMPLETE_v3.json"])
    source_binding = load_json(pinned["C5_ABLATION_DEV72_SOURCE_BINDING_v3.json"])
    contract = load_json(pinned["C5_ABLATION_DEV72_RUN_CONTRACT_v3.json"])
    prepare = load_json(pinned["C5_ABLATION_DEV72_PREPARE_RESULT_v3.json"])
    preflight_record = load_json(pinned["C5_ABLATION_DEV72_RUNNER_PREFLIGHT_v3.json"])
    release_contract = load_json(pinned["C5_ABLATION_DEV72_PARENT_RELEASE_CONTRACT_v3.json"])
    release = load_json(pinned["C5_ABLATION_DEV72_REMAINING60_PARENT_RELEASE_v3.json"])
    screen = load_json(pinned["C5_NO_DELAYED_PREDICTION_SCREEN12_RAW_PARENT_AUDIT_v1.json"])
    first = load_json(pinned["C5_NO_DELAYED_PREDICTION_FIRST_RAW_PARENT_AUDIT_v1.json"])
    require(lock["schema"] == "C5_MATCHED_ABLATION_DEV72_INPUT_LOCK_V2"
            and lock["state"] == "LOCKED_C5_MATCHED_ABLATION_DEV72_NO_PLANT_WAIT_PARENT_REVIEW_V2",
            "wrong v3 input lock")
    require(lock["variant_id"] == lock["ablation_mode"] == contract["variant_id"] == VARIANT,
            "locked variant mismatch")
    require(contract["candidate"] == CANDIDATE and contract["model"]["W0_sha256"].lower() == W0_SHA,
            "frozen candidate identity mismatch")
    require(contract["model"]["id"] == "DSSM14" and contract["model"]["seed"] == 2026102001
            and contract["model"]["selected_step"] == 60000 and contract["model"]["input_dim"] == 14
            and contract["model"]["window"] == 32
            and contract["model"]["normalizer_arrays_sha256"].lower() == NORMALIZER_SHA,
            "frozen DSSM model identity mismatch")
    require(lock["plant_authorized_by_this_lock"] is False
            and contract["prohibitions"]["TEST_accessed"] is False,
            "input lock unexpectedly authorizes Plant or TEST access")
    require(lock["scene_ids"] == lock["scene_ids_all_72"] and len(lock["scene_ids"] ) == 72
            and len(set(lock["scene_ids"])) == 72, "lock must contain 72 unique ordered scenes")
    require(contract["scene_ids_all_72"] == lock["scene_ids_all_72"]
            and contract["scene_ids_remaining_60"] == lock["scene_ids_remaining_60"]
            and contract["scene_ids_reuse_12"] == lock["scene_ids_reuse_12"],
            "run contract scene lists differ from the input lock")
    require([scene["scene_id"] for scene in lock["scenes"]] == lock["scene_ids"], "scene rows differ from locked order")
    require(len(lock["scene_ids_remaining_60"]) == 60 and len(lock["scene_ids_reuse_12"]) == 12,
            "locked 60+12 row counts mismatch")
    require(lock["source_counts"]["total"] == len(lock["active_source_inventory"]) == 32,
            "active source inventory count mismatch")
    require(contract["actual_weight_update_enabled"] is True and contract["actual_prediction_gradient_enabled"] is False
            and contract["position_delayed_prediction_enabled"] is True, "frozen intervention flags mismatch")
    require(batch["schema"] == "C5_MATCHED_ABLATION_DEV72_BATCH_V2"
            and batch["status"] == "COMPLETE_RAW_PENDING_PARENT_AUDIT" and batch["phase"] == "REMAINING60",
            "60-run batch is not in the expected complete pending-audit state")
    require(batch["variant_id"] == VARIANT and batch["plant_calls"] == 60
            and batch["training_steps"] == batch["optimizer_steps"] == 0 and batch["TEST_accessed"] is False,
            "batch summary contains unexpected scope")
    require(body["schema"] == "C5_MATCHED_ABLATION_DEV72_BODY_COMPLETE_V2"
            and body["status"] == batch["status"] and body["scene_count"] == 60,
            "body-complete summary mismatch")
    require(batch["scene_ids_remaining_60"] == body["scene_ids_remaining_60"] == lock["scene_ids_remaining_60"]
            and batch["scene_ids_all_72"] == body["scene_ids_all_72"] == lock["scene_ids_all_72"]
            and batch["scene_ids_reuse_12"] == body["scene_ids_reuse_12"] == lock["scene_ids_reuse_12"],
            "batch/body scene lists differ from the input lock")
    require(batch["records"] == body["records"], "batch/body rows differ")
    require([record["scene_id"] for record in batch["records"]] == lock["scene_ids_remaining_60"],
            "60 run rows differ from the locked remaining scene order")
    require(len({record["scene_id"] for record in batch["records"]}) == 60, "duplicate remaining scene row")
    require([record["batch_index"] for record in batch["records"]] == list(range(1, 61)),
            "60 run batch indices are not sequential")
    require(release["plant_authorized"] is True and release["max_new_Plant"] == 60
            and release["TEST_accessed"] is False and release["training_steps"] == release["optimizer_steps"] == 0,
            "release does not match the frozen 60-row offline audit scope")
    require(source_binding["input_lock_sha256"].lower() == EXPECTED_HASHES[next(k for k in EXPECTED_HASHES if k.endswith("INPUT_LOCK_v3.json"))]
            and source_binding["run_contract_sha256"].lower() == EXPECTED_HASHES[next(k for k in EXPECTED_HASHES if k.endswith("RUN_CONTRACT_v3.json"))],
            "source binding lock/contract hash mismatch")
    lock_sha = EXPECTED_HASHES["experiments/position_c5_matched_ablations_dev72_v3_20261023/C5_NO_DELAYED_PREDICTION/C5_ABLATION_DEV72_INPUT_LOCK_v3.json"]
    contract_sha = EXPECTED_HASHES["experiments/position_c5_matched_ablations_dev72_v3_20261023/C5_NO_DELAYED_PREDICTION/C5_ABLATION_DEV72_RUN_CONTRACT_v3.json"]
    binding_sha = EXPECTED_HASHES["experiments/position_c5_matched_ablations_dev72_v3_20261023/C5_NO_DELAYED_PREDICTION/C5_ABLATION_DEV72_SOURCE_BINDING_v3.json"]
    prepare_sha = EXPECTED_HASHES["experiments/position_c5_matched_ablations_dev72_v3_20261023/C5_NO_DELAYED_PREDICTION/C5_ABLATION_DEV72_PREPARE_RESULT_v3.json"]
    preflight_sha = EXPECTED_HASHES["experiments/position_c5_matched_ablations_dev72_v3_20261023/C5_NO_DELAYED_PREDICTION/C5_ABLATION_DEV72_RUNNER_PREFLIGHT_v3.json"]
    release_sha = EXPECTED_HASHES["experiments/position_c5_matched_ablations_dev72_v3_20261023/C5_NO_DELAYED_PREDICTION/C5_ABLATION_DEV72_REMAINING60_PARENT_RELEASE_v3.json"]
    reuse_sha = EXPECTED_HASHES["experiments/position_c5_matched_ablations_dev72_v3_20261023/C5_NO_DELAYED_PREDICTION/C5_ABLATION_DEV72_REUSE12_BINDING_v3.json"]
    screen_sha = EXPECTED_HASHES["reports/paper_continuation_20261023/c5_matched_ablation_parent_raw_review/C5_NO_DELAYED_PREDICTION_SCREEN12_RAW_PARENT_AUDIT_v1.json"]
    require(binding["input_lock_sha256"].lower() == lock_sha
            and binding["contract_sha256"].lower() == contract_sha
            and binding["screen12_parent_audit_sha256"].lower() == screen_sha,
            "reuse binding is not attached to the locked inputs")
    require(binding["screen12_parent_audit_event_audit_sha256"].lower() == EXPECTED_HASHES[
            "reports/paper_continuation_20261023/c5_matched_ablation_parent_raw_review/event_audit_c5_matched_ablation.py"]
            and binding["screen12_parent_audit_entry_sha256"].lower() == EXPECTED_HASHES[
            "reports/paper_continuation_20261023/c5_matched_ablation_parent_raw_review/audit_c5_matched_ablation_screen12_raw.py"],
            "reuse binding checker provenance mismatch")
    require(batch["source_binding_sha256"].lower() == body["source_binding_sha256"].lower() == binding_sha
            and batch["release_sha256"].lower() == body["release_sha256"].lower() == release_sha
            and batch["preflight_sha256"].lower() == body["preflight_sha256"].lower() == preflight_sha,
            "batch/body source, release, or preflight pin mismatch")
    require(batch["reuse12_binding_sha256"].lower() == reuse_sha
            and batch["screen12_parent_audit_sha256"].lower() == screen_sha,
            "batch reuse12 pin mismatch")
    require(batch["runner_sha256"].lower() == source_binding["runner_sha256"].lower(),
            "batch runner identity differs from source binding")
    require(prepare["input_lock_sha256"].lower() == lock_sha and prepare["contract_sha256"].lower() == contract_sha
            and prepare["reuse12_binding_sha256"].lower() == reuse_sha,
            "prepare result lock/contract/reuse binding mismatch")
    require(preflight_record["input_lock_sha256"].lower() == lock_sha
            and preflight_record["contract_sha256"].lower() == contract_sha
            and preflight_record["source_binding_sha256"].lower() == binding_sha
            and preflight_record["prepare_result_sha256"].lower() == prepare_sha,
            "runner preflight source-chain mismatch")
    require(release["input_lock_sha256"].lower() == lock_sha
            and release["run_contract_sha256"].lower() == contract_sha
            and release["source_binding_sha256"].lower() == binding_sha
            and release["prepare_result_sha256"].lower() == prepare_sha
            and release["runner_preflight_sha256"].lower() == preflight_sha
            and release["reuse12_binding_sha256"].lower() == reuse_sha
            and release["reuse12_parent_screen_audit_sha256"].lower() == screen_sha,
            "parent release source-chain mismatch")
    require(same_path(binding["screen12_parent_audit_path"], pinned["C5_NO_DELAYED_PREDICTION_SCREEN12_RAW_PARENT_AUDIT_v1.json"])
            and same_path(binding["first_parent_audit_path"], pinned["C5_NO_DELAYED_PREDICTION_FIRST_RAW_PARENT_AUDIT_v1.json"]),
            "reuse audit path differs from locked manifest")
    require(screen["audit_entry_sha256"].lower() == binding["screen12_parent_audit_entry_sha256"].lower()
            and screen["event_audit_sha256"].lower() == binding["screen12_parent_audit_event_audit_sha256"].lower(),
            "screen12 audit code provenance mismatch")
    require(prepare["snapshot_sha256"].lower() == preflight_record["snapshot_sha256"].lower()
            and release["snapshot_sha256"].lower() == prepare["snapshot_sha256"].lower(),
            "prepared snapshot identity mismatch")
    require(release_contract["plant_authorized"] is False and release_contract["max_new_Plant"] == 0,
            "release contract unexpectedly grants Plant authority")
    table = score_table(SCORE_TABLE, lock)
    reuse_rows = validate_reuse(lock, binding, screen, first, table)
    return (pinned, lock, binding, batch, source_binding, contract, prepare, preflight_record,
            release, screen, table, reuse_rows)


def write_exclusive(output_dir: Path, rows: list[dict], summary: dict) -> None:
    output_dir.mkdir()
    json_path = output_dir / "C5_NO_DELAYED_DEV72_PARENT_RAW_AUDIT_v1.json"
    with json_path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(summary, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
    csv_path = output_dir / "C5_NO_DELAYED_DEV72_PARENT_RAW_AUDIT_v1.csv"
    fields = ["scene_id", "audit_status", "raw_path", "raw_sha256", "run_status_sha256", "run_start_sha256",
              "event_count", "batch_index", "Q_0_20_m", "B_TRACEABLE_Q_0_20_m", "C3_Q_0_20_m",
              "C5_M110_Q_0_20_m", "delta_vs_B_TRACEABLE_m", "delta_vs_C3_m", "delta_vs_C5_M110_m"]
    with csv_path.open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path,
                        help="new absolute audit_run_* directory directly under this folder")
    args = parser.parse_args()
    try:
        (pinned, lock, binding, batch, source_binding, contract, prepare, preflight_record,
         release, screen, baseline_table, reused_rows) = preflight(args.output_dir)
        import h5py  # noqa: F401 - fail before raw access if the offline MAT reader is unavailable
        base = import_pinned(BASE_AUDITOR, "pinned_c5_dev72_parent_auditor")
        decoder = import_pinned(DECODER, "pinned_matlab_decoder")
        scorer = import_pinned(SCORER, "pinned_raw_metric_scorer")
        event_audit = import_pinned(EVENT_AUDIT, "pinned_c5_matched_ablation_event_audit")
        require(sha(BASE_AUDITOR).lower() == EXPECTED_HASHES["reports/paper_continuation_20261023/c5_dev72_parent_review/audit_c5_dev72_raw_parent_v4.py"],
                "base C5 auditor changed after preflight")
        require(sha(EVENT_AUDIT).lower() == EXPECTED_HASHES["reports/paper_continuation_20261023/c5_matched_ablation_parent_raw_review/event_audit_c5_matched_ablation.py"],
                "C5 event auditor changed after preflight")
        snapshot_path = Path(prepare["snapshot_path"])
        require(snapshot_path.is_file() and sha(snapshot_path).lower() == prepare["snapshot_sha256"].lower(),
                "prepared snapshot SHA mismatch")
        active_sources = lock["active_source_inventory"]
        for ref in source_binding["file_refs"]:
            path = Path(ref["path"])
            require(path.is_file() and sha(path).lower() == ref["sha256"].lower(),
                    f"locked source file SHA mismatch: {path}")
        with h5py.File(snapshot_path, "r") as mat:
            snapshot = {key: base.h5_tree_cell_safe(mat[key])
                        for key in ("cfg", "opts", "W0", "modelIdentity", "sceneIdentity", "sourceIdentity")}
        digests = {
            "input_lock_sha256": EXPECTED_HASHES["experiments/position_c5_matched_ablations_dev72_v3_20261023/C5_NO_DELAYED_PREDICTION/C5_ABLATION_DEV72_INPUT_LOCK_v3.json"],
            "run_contract_sha256": EXPECTED_HASHES["experiments/position_c5_matched_ablations_dev72_v3_20261023/C5_NO_DELAYED_PREDICTION/C5_ABLATION_DEV72_RUN_CONTRACT_v3.json"],
            "source_binding_sha256": EXPECTED_HASHES["experiments/position_c5_matched_ablations_dev72_v3_20261023/C5_NO_DELAYED_PREDICTION/C5_ABLATION_DEV72_SOURCE_BINDING_v3.json"],
            "release_sha256": EXPECTED_HASHES["experiments/position_c5_matched_ablations_dev72_v3_20261023/C5_NO_DELAYED_PREDICTION/C5_ABLATION_DEV72_REMAINING60_PARENT_RELEASE_v3.json"],
            "prepare_result_sha256": EXPECTED_HASHES["experiments/position_c5_matched_ablations_dev72_v3_20261023/C5_NO_DELAYED_PREDICTION/C5_ABLATION_DEV72_PREPARE_RESULT_v3.json"],
            "preflight_sha256": EXPECTED_HASHES["experiments/position_c5_matched_ablations_dev72_v3_20261023/C5_NO_DELAYED_PREDICTION/C5_ABLATION_DEV72_RUNNER_PREFLIGHT_v3.json"],
            "snapshot_sha256": prepare["snapshot_sha256"],
        }
        lock_by_scene = {row["scene_id"]: row for row in lock["scenes"]}
        for row in lock_by_scene.values():
            row["_active_source_inventory"] = active_sources
        new_rows, event_rows = [], []
        for record in batch["records"]:
            audited, event_result = audit_new_row(record, lock_by_scene[record["scene_id"]], batch, digests,
                                                  snapshot, base, decoder, event_audit, scorer, baseline_table)
            new_rows.append(audited)
            event_rows.append({"scene_id": record["scene_id"], "event_count": event_result["event_count"],
                               "checks": event_result})
        all_rows = sorted(reused_rows + new_rows, key=lambda row: lock["scene_ids"].index(row["scene_id"]))
        require(len(all_rows) == 72 and len({row["scene_id"] for row in all_rows}) == 72,
                "combined audit does not contain exactly the locked 72 scenes")
        require(sum(row["event_count"] for row in all_rows) == 72 * 1968,
                "combined audited event count mismatch")
        summary = {
            "schema": "C5_NO_DELAYED_DEV72_PARENT_RAW_AUDIT_V1",
            "status": "PASS_C5_NO_DELAYED_DEV72_PARENT_RAW_AUDIT",
            "variant_id": VARIANT, "candidate": CANDIDATE,
            "new_raws_audited": len(new_rows), "reused_raws_by_sha": len(reused_rows),
            "scene_count": len(all_rows), "event_count_total": sum(row["event_count"] for row in all_rows),
            "Plant_calls_by_auditor": 0, "training_steps": 0, "optimizer_steps": 0, "TEST_accessed": False,
            "input_hashes": {name: digest for name, digest in EXPECTED_HASHES.items()},
            "active_source_count": len(active_sources), "score_table": str(SCORE_TABLE),
            "score_table_sha256": sha(SCORE_TABLE),
            "reused_raws": [{"scene_id": row["scene_id"], "raw_sha256": row["raw_sha256"]}
                            for row in all_rows if row["audit_status"] == "PASS_REUSE_SHA"],
            "new_event_rows": event_rows, "rows": all_rows,
        }
        write_exclusive(args.output_dir, all_rows, summary)
        print(json.dumps({"status": summary["status"], "new_raws_audited": len(new_rows),
                          "reused_raws_by_sha": len(reused_rows), "output_dir": str(args.output_dir)},
                         ensure_ascii=False))
        return 0
    except Exception as error:
        print(f"AUDIT REFUSED/FAILED: {type(error).__name__}: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
