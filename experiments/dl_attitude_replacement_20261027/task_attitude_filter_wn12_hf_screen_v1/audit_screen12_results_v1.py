"""Read-only scoring and provenance audit for the locked 12-scene wn12 screen.

Reads only the 12 DEV/VAL candidate raws and their locked same-scene B/C5 raws.
It never starts MATLAB/Plant/training, accesses TEST inputs, or alters raw files.
"""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import re
from pathlib import Path

import h5py
import numpy as np


STUDY = Path(__file__).resolve().parent
PROJECT = STUDY.parents[2]
PARENT = PROJECT / "experiments" / "dl_attitude_replacement_20261026" / "gru_stream_cosine_tracking_head_full72_v1"
PARENT_DEV = PROJECT / "experiments" / "dl_attitude_replacement_20261026" / "gru_stream_cosine_tracking_head_dev_v1"
SCORER_PATH = PARENT / "audits" / "score_full72_candidate_v1.py"
PARENT_MANIFEST_PATH = PARENT / "MANIFEST.json"
CONSTANTS_PATH = PROJECT / "experiments" / "dl_attitude_replacement_20261026" / "mlp15_composite_dev_v3" / "RELEASE.json"
SNAPSHOT_PATH = STUDY / "RELEASE_REMAINING11_RUNTIME_SNAPSHOT.json"
EXPECTED_SNAPSHOT_SHA = "65607eb089c214bfce0a7d2359d1d873f4b39af04ca310f6db3a2533bf2ab67f"
GATE_RELEASE_SHA = "06c8aba11fbaec0fc35d7e23397a362b38d0583decd99182793b912d4b43118e"
GATE_SOURCE_LOCK_SHA = "afd4c4727f1b7d84df5991033f227d38bba0cb86e553182640f855527cc239b2"
OUTPUT_JSON = STUDY / "SCREEN12_RESULTS_v1.json"
OUTPUT_CSV = STUDY / "SCREEN12_RESULTS_v1.csv"
OUTPUT_MD = STUDY / "SCREEN12_RESULTS_v1.md"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def readj(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def matstr(ds) -> str:
    a = np.asarray(ds[()]).reshape(-1)
    if a.dtype.kind in "ui":
        return "".join(chr(int(x)) for x in a if int(x))
    return "".join(x.decode("utf-8") if isinstance(x, bytes) else str(x) for x in a)


def h5str(f, path: str) -> str:
    return matstr(f[path])


def h5bool(f, path: str) -> bool:
    return bool(np.asarray(f[path][()]).reshape(-1)[0])


def filesha(path_text: str) -> tuple[Path, str | None]:
    p = Path(path_text)
    return p, sha(p) if p.is_file() else None


def row_status_paths(scene_id: str) -> tuple[Path, Path, Path, Path]:
    scene_root = STUDY / "runs" / scene_id
    candidates = [scene_root / "run_status.json", scene_root / "attempt_01" / "run_status.json"]
    found = [p for p in candidates if p.is_file()]
    if len(found) != 1:
        raise RuntimeError(f"Expected one run_status for {scene_id}; found {len(found)}")
    status_path = found[0]
    run_dir = status_path.parent
    return status_path, run_dir / "run_start.json", run_dir / "attempt_started.marker", run_dir


def raw_identity(raw_path: Path) -> dict:
    with h5py.File(raw_path, "r") as f:
        result = {}
        for key, ds in f["runIdentity"].items():
            cls = ds.attrs.get("MATLAB_class", b"")
            if cls == b"char":
                result[key] = matstr(ds)
            elif cls == b"logical":
                result[key] = bool(np.asarray(ds[()]).reshape(-1)[0])
            else:
                v = np.asarray(ds[()]).reshape(-1)
                result[key] = float(v[0]) if v.size == 1 else v.tolist()
        log = f["log"]
        for key in (
            "gru_stream_variable_inertia_reconstruction_used",
            "gru_stream_base_model_weight_update_enabled",
            "gru_stream_tracking_head_enabled",
            "gru_stream_tracking_delta_weight_update_enabled",
            "gru_stream_base_model_weights_fixed",
            "gru_stream_rbf_output_enabled",
            "gru_stream_rbf_update_enabled",
            "gate_feedforward_enabled",
            "gate_observer_enabled",
        ):
            if key in log:
                result[f"log.{key}"] = bool(np.asarray(log[key][()]).reshape(-1)[0])
        if "method" in log:
            result["log.method"] = matstr(log["method"])
        if "gru_stream_protocol" in log:
            result["log.gru_stream_protocol"] = matstr(log["gru_stream_protocol"])
        result["scene.scene_id"] = matstr(f["scene/scene_id"])
        result["raw.complete_transitions"] = h5bool(f, "log/complete_transitions")
        result["raw.actual_transition_count"] = int(np.asarray(log["actual_transition_count"][()]).reshape(-1)[0])
        result["raw.actual_state_sample_count"] = int(np.asarray(log["actual_state_sample_count"][()]).reshape(-1)[0])
        result["raw.last_transition"] = int(np.asarray(log["last_transition"][()]).reshape(-1)[0])
        if "rbf_update_flag" in log:
            result["raw.rbf_update_flag_any"] = bool(np.any(log["rbf_update_flag"][()]))
        if "attitude_rbf_compensation_torque_Nm" in log:
            a = np.asarray(log["attitude_rbf_compensation_torque_Nm"][()], dtype=float)
            result["raw.max_abs_attitude_rbf_compensation_torque_Nm"] = float(np.max(np.abs(a)))
    return result


def verify_source_tree() -> dict:
    v1_path = STUDY / "SOURCE_LOCK_v1.json"
    v2_path = STUDY / "SOURCE_LOCK_v2.json"
    v1 = readj(v1_path)
    v2 = readj(v2_path)
    v1_results, v2_results = [], []
    runner = STUDY / "candidate_runner_work"
    for rec in v1["files"]:
        p = runner / Path(rec["relative_path"])
        actual = sha(p) if p.is_file() else None
        v1_results.append({"relative_path": rec["relative_path"], "expected_sha256": rec["sha256"],
                           "actual_sha256": actual, "pass": actual == rec["sha256"]})
    for rec in v2["files"]:
        p = STUDY / Path(rec["relative_path"])
        actual = sha(p) if p.is_file() else None
        v2_results.append({"relative_path": rec["relative_path"], "expected_sha256": rec["sha256"],
                           "actual_sha256": actual, "pass": actual == rec["sha256"]})
    v1_artifact = v1["study_artifacts"][0]
    current_wrapper = STUDY / "run_gru_stream_tracking_head_filter_wn12_attempt.m"
    return {
        "v1_lock_sha256": sha(v1_path), "v1_runtime_files_checked": len(v1_results),
        "v1_runtime_files_pass": sum(x["pass"] for x in v1_results),
        "v1_runtime_mismatches": [x for x in v1_results if not x["pass"]],
        "v1_recorded_wrapper_sha256": v1_artifact["sha256"],
        "v1_wrapper_bytes_available": False,
        "current_wrapper_sha256": sha(current_wrapper),
        "current_wrapper_matches_v1_recorded_sha": sha(current_wrapper) == v1_artifact["sha256"],
        "v2_lock_sha256": sha(v2_path), "v2_files_checked": len(v2_results),
        "v2_files_pass": sum(x["pass"] for x in v2_results),
        "v2_mismatches": [x for x in v2_results if not x["pass"]],
    }


def relation_values(identity: dict, start: dict, release: dict, rec: dict, scene_id: str) -> dict:
    if start["authorization_phase"] == "ENGINEERING_GATE":
        expected_lock = GATE_SOURCE_LOCK_SHA
    else:
        expected_lock = release["source_lock_sha256"]
    checks = {
        "scene_id": identity.get("scene_id") == scene_id == start.get("scene_id"),
        "candidate": identity.get("candidate") == start.get("candidate") == release["candidate"],
        "authorization_phase": identity.get("authorization_phase") == start.get("authorization_phase"),
        "run_release_sha": identity.get("release_sha256") == start.get("release_sha256"),
        "manifest_sha": identity.get("manifest_sha256") == start.get("manifest_sha256"),
        "source_lock_sha": identity.get("source_lock_sha256") == start.get("source_lock_sha256") == expected_lock,
        "source_diff_sha": identity.get("source_diff_sha256") == start.get("source_diff_sha256"),
        "locked_cfg_sha": identity.get("locked_cfg_sha256") == start.get("locked_cfg_sha256"),
        "payload_sha": identity.get("payload_sha256") == start.get("payload_sha256") == rec["payload_sha256"],
        "B_raw_sha": identity.get("b_raw_sha256") == start.get("b_raw_sha256") == rec["b_raw_sha256"],
        "C5_raw_sha": identity.get("c5_raw_sha256") == start.get("c5_raw_sha256") == rec["c5_raw_sha256"],
        "GRU_model_sha": identity.get("gru_model_sha256") == start.get("gru_model_sha256") == release["model_sha256"],
        "frozen_model_candidate_id": identity.get("frozen_model_candidate") == start.get("frozen_model_candidate") == Path(release["model_path"]).parent.name,
        "C5_input_lock_sha": identity.get("c5_input_lock_sha256") == start.get("c5_input_lock_sha256"),
        "C5_snapshot_sha": identity.get("c5_snapshot_sha256") == start.get("c5_snapshot_sha256"),
        "position_model_sha": identity.get("position_model_sha256") == start.get("position_model_sha256"),
        "common_position_options_sha": identity.get("common_position_options_sha256") == start.get("common_position_options_sha256"),
        "TEST_false": identity.get("TEST_read") is False and start.get("TEST_read") is False,
        "Plant_truth_false": identity.get("Plant_truth_deployment_input") is False,
        "inertia_reconstruction_false": identity.get("inertia_reconstruction_enabled") is False and identity.get("log.gru_stream_variable_inertia_reconstruction_used") is False,
        "base_weights_fixed": identity.get("base_model_weights_fixed") is True and identity.get("log.gru_stream_base_model_weights_fixed") is True,
        "base_weight_update_false": identity.get("log.gru_stream_base_model_weight_update_enabled") is False,
        "tracking_head_enabled": identity.get("log.gru_stream_tracking_head_enabled") is True,
        "tracking_delta_update_enabled": identity.get("tracking_delta_weights_online") is True and identity.get("log.gru_stream_tracking_delta_weight_update_enabled") is True,
        "RBF_output_update_false": identity.get("rbf_attitude_output_enabled") is False and identity.get("rbf_attitude_update_enabled") is False and identity.get("log.gru_stream_rbf_output_enabled") is False and identity.get("log.gru_stream_rbf_update_enabled") is False and identity.get("raw.rbf_update_flag_any") is False,
        "gate_networks_false": identity.get("log.gate_feedforward_enabled") is False and identity.get("log.gate_observer_enabled") is False,
        "attitude_RBF_torque_zero": identity.get("raw.max_abs_attitude_rbf_compensation_torque_Nm", float("inf")) < 1e-12,
        "GRU_method_protocol": identity.get("log.method") == "GRU_STREAM" and "GRU32_COSINE_PLUS_TRACKING_DELTAW33_OUTPUT_BEFORE_UPDATE" in identity.get("log.gru_stream_protocol", ""),
        "raw_complete_counts": identity.get("raw.complete_transitions") is True and identity.get("raw.actual_transition_count") == 20000 and identity.get("raw.actual_state_sample_count") == 20001 and identity.get("raw.last_transition") == 20000,
    }
    return {k: bool(v) for k, v in checks.items()}


def main() -> None:
    spec = importlib.util.spec_from_file_location("frozen_gru_paired_scorer", SCORER_PATH)
    scorer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scorer)

    manifest = readj(STUDY / "MANIFEST.json")
    input_lock = readj(STUDY / "INPUT_LOCK_v1.json")
    runtime_release = readj(SNAPSHOT_PATH)
    parent_manifest = readj(PARENT_MANIFEST_PATH)
    parent_full_release = readj(PARENT / "RELEASE.json")
    constants = readj(CONSTANTS_PATH)
    locked_cfg = readj(STUDY / "LOCKED_CFG.json")
    parent_cfg = readj(PARENT / "LOCKED_CFG.json")
    external_lock = readj(STUDY / "DEPENDENCY_EXTERNAL_LOCK_v1.json")
    expected_snapshot = sha(SNAPSHOT_PATH)
    gravity = float(constants["gravity_mps2"])
    max_tilt = float(constants["max_tilt_rad"])
    rows = manifest["records"]
    manifest_ids = [r["scene_id"] for r in rows]
    rows_by_id = {r["scene_id"]: r for r in rows}
    input_by_id = {r["scene_id"]: r for r in input_lock["records"]}
    parent_rows_by_id = {r["scene_id"]: r for r in parent_manifest["records"]}
    authorized = list(runtime_release["authorized_scenes"])
    launcher_text = (STUDY / "RUN_FILTER_WN12_SCREEN_EXACT_v1.ps1").read_text(encoding="utf-8")
    rem = re.search(r"else\s*\{\s*\$sceneIds\s*=\s*@\((.*?)\)\s*if", launcher_text, re.S)
    launcher_ids = re.findall(r"'(DL1018_[^']+)'", rem.group(1)) if rem else []
    source_tree = verify_source_tree()
    parent_full_lock_path = PARENT / "SOURCE_LOCK_v1.json"
    parent_dev_lock_path = PARENT_DEV / "SOURCE_LOCK_v1.json"
    parent_full_lock, parent_dev_lock = readj(parent_full_lock_path), readj(parent_dev_lock_path)
    full_runtime_map = {x["relative_path"]: x["sha256"] for x in parent_full_lock["files"]}
    dev_runtime_map = {x["relative_path"]: x["sha256"] for x in parent_dev_lock["files"]}
    parent_runtime_source_equal = full_runtime_map == dev_runtime_map and len(full_runtime_map) == 59
    parent_cfg_full_sha = sha(PARENT / "LOCKED_CFG.json")
    parent_cfg_dev_sha = sha(PARENT_DEV / "LOCKED_CFG.json")
    parent_model_sha = sha(Path(parent_full_release["model_path"]))

    scene_records = []
    audit_failures = []
    marker_records = []
    for sid in manifest_ids:
        rec = rows_by_id[sid]
        irec = input_by_id[sid]
        status_path, start_path, marker_path, run_dir = row_status_paths(sid)
        status, start, marker = readj(status_path), readj(start_path), readj(marker_path)
        candidate_raw_path = Path(status["raw_path"])
        candidate_raw_sha = sha(candidate_raw_path) if candidate_raw_path.is_file() else None
        identity = raw_identity(candidate_raw_path) if candidate_raw_sha else {}
        raw_row_checks = {}

        def ck(name: str, condition: bool):
            raw_row_checks[name] = bool(condition)

        ck("candidate_raw_exists_and_status_sha", candidate_raw_sha is not None and candidate_raw_sha == status.get("raw_sha256"))
        ck("status_completed_stable", status.get("state") == "COMPLETED" and status.get("status_value") == "STABLE" and status.get("safety_stop_reason", "") == "")
        ck("status_count_and_test", status.get("transitions") == 20000 and status.get("state_samples") == 20001 and status.get("Plant_calls") == 1 and status.get("TEST_read") is False)
        ck("raw_path_status_same_directory", candidate_raw_path.resolve() == (run_dir / "raw_run.mat").resolve())
        ck("raw_path_inside_scene_run_root", candidate_raw_path.resolve().is_relative_to((STUDY / "runs" / sid).resolve()))
        planned_path = Path(rec["candidate_raw_path"])
        ck("input_lock_matches_manifest", irec["candidate_raw_path"] == rec["candidate_raw_path"] and irec["b_raw_sha256"] == rec["b_raw_sha256"] and irec["c5_raw_sha256"] == rec["c5_raw_sha256"])
        ck("raw_scene_identity", identity.get("scene.scene_id") == sid)
        ck("start_status_marker_scene", start.get("scene_id") == sid and status.get("scene_id") == sid and marker.get("scene_id") == sid)
        ck("run_identity_candidate", identity.get("candidate") == runtime_release["candidate"] and start.get("candidate") == status.get("candidate") == runtime_release["candidate"])
        ck("run_release_sha_chain", status.get("release_sha256") == start.get("release_sha256") == marker.get("release_sha256") == identity.get("release_sha256"))
        ck("run_start_raw_status_identity_sha", candidate_raw_sha == status.get("raw_sha256"))
        ck("status_source_lock_chain", status.get("source_lock_sha256") == start.get("source_lock_sha256") == identity.get("source_lock_sha256"))
        ck("status_TEST_false", status.get("TEST_read") is False and start.get("TEST_read") is False and identity.get("TEST_read") is False)
        ck("run_status_file_hash_matches_record", sha(status_path) == rec["candidate_status_sha256"] if "candidate_status_sha256" in rec else True)
        ck("start_release_manifest_sha", start.get("manifest_sha256") == sha(STUDY / "MANIFEST.json"))
        ck("locked_cfg_sha", start.get("locked_cfg_sha256") == sha(STUDY / "LOCKED_CFG.json"))
        ck("payload_sha", sha(Path(rec["payload_path"])) == rec["payload_sha256"] == start.get("payload_sha256"))
        ck("B_raw_sha", sha(Path(rec["b_raw_path"])) == rec["b_raw_sha256"] == start.get("b_raw_sha256"))
        ck("C5_raw_sha", sha(Path(rec["c5_raw_path"])) == rec["c5_raw_sha256"] == start.get("c5_raw_sha256"))
        ck("B_status_sha", sha(Path(rec["b_status_path"])) == rec["b_status_sha256"])
        ck("C5_status_sha", sha(Path(rec["c5_status_path"])) == rec["c5_status_sha256"])
        # The engineering-gate raw was deliberately retained at its original path.
        # Record a plan mismatch as a reconciliation finding, not as a data identity failure.
        raw_row_checks["candidate_path_matches_plan"] = candidate_raw_path.resolve() == planned_path.resolve()

        phase = start.get("authorization_phase")
        if phase == "ENGINEERING_GATE":
            ck("phase_runtime_release_hash", start.get("release_sha256") == GATE_RELEASE_SHA)
            ck("phase_source_lock_v1", start.get("source_lock_sha256") == GATE_SOURCE_LOCK_SHA)
            ck("phase_gate_scene", sid == "DL1018_DEV_T1_C10_W09")
        elif phase == "REMAINING11":
            ck("phase_runtime_release_snapshot", start.get("release_sha256") == expected_snapshot)
            ck("phase_source_lock_v2", start.get("source_lock_sha256") == runtime_release.get("source_lock_sha256"))
            ck("phase_scene_authorized", sid in authorized)
        else:
            ck("phase_valid", False)

        checks = relation_values(identity, start, runtime_release, rec, sid)
        raw_row_checks.update({f"identity.{k}": v for k, v in checks.items()})

        b_path, c5_path = Path(rec["b_raw_path"]), Path(rec["c5_raw_path"])
        parent_rec = parent_rows_by_id[sid]
        parent_raw_path = Path(parent_rec["candidate_raw_path"])
        parent_status_path = Path(parent_rec["candidate_status_path"])
        parent_start_path = parent_status_path.parent / "run_start.json"
        parent_status = readj(parent_status_path)
        parent_start = readj(parent_start_path)
        parent_raw_sha = sha(parent_raw_path) if parent_raw_path.is_file() else None
        parent_identity = raw_identity(parent_raw_path) if parent_raw_sha else {}
        parent_expected_lock_sha = sha(parent_dev_lock_path if parent_rec.get("candidate_reuse") else parent_full_lock_path)
        parent_audit_path = Path(parent_rec.get("candidate_audit_path", ""))
        parent_audit_sha_actual = sha(parent_audit_path) if parent_audit_path.is_file() else None
        reused_raw_audit_pass = (not parent_rec.get("candidate_reuse") or
            (parent_rec.get("candidate_parent_audit_status") == "PASS_INDEPENDENT_GRU_STREAM_TRACKING_HEAD_RAW_REPLAY"
             and parent_audit_sha_actual == parent_rec.get("candidate_audit_sha256")))
        parent_checks = {
            "raw_exists_and_status_sha": parent_raw_sha is not None and parent_raw_sha == parent_status.get("raw_sha256"),
            "status_completed_stable": parent_status.get("state") == "COMPLETED" and parent_status.get("status_value") == "STABLE",
            "status_complete_counts": parent_status.get("transitions") == 20000 and parent_status.get("state_samples") == 20001 and parent_status.get("Plant_calls") == 1,
            "TEST_false": parent_status.get("TEST_read") is False and parent_start.get("TEST_read") is False and parent_identity.get("TEST_read") is False,
            "run_identity_scene_candidate": parent_identity.get("scene_id") == sid == parent_start.get("scene_id") == parent_status.get("scene_id") and parent_identity.get("candidate") == parent_start.get("candidate") == parent_full_release.get("candidate"),
            "frozen_model_candidate_id": parent_identity.get("frozen_model_candidate") == parent_start.get("frozen_model_candidate") == Path(parent_full_release["model_path"]).parent.name,
            "run_release_sha_chain": parent_status.get("release_sha256") == parent_start.get("release_sha256") == parent_identity.get("release_sha256"),
            "source_lock_expected_for_raw_lineage": parent_start.get("source_lock_sha256") == parent_expected_lock_sha and parent_identity.get("source_lock_sha256") == parent_expected_lock_sha,
            "59_runtime_sources_identical": parent_runtime_source_equal,
            "WN18_locked_cfg_bound_and_wn18": parent_cfg_full_sha == parent_cfg_dev_sha == parent_start.get("locked_cfg_sha256") == parent_identity.get("locked_cfg_sha256") and parent_cfg.get("command_filter", {}).get("wn") == [18, 18, 12],
            "GRU_model_sha_equal_and_bound": parent_model_sha == parent_full_release.get("model_sha256") == runtime_release.get("model_sha256") == parent_start.get("gru_model_sha256") == parent_identity.get("gru_model_sha256"),
            "manifest_reuse_flag_matches_source": bool(parent_rec.get("candidate_reuse")) == (parent_start.get("source_lock_sha256") == sha(parent_dev_lock_path)),
            "reused_raw_parent_replay_audit_sha": reused_raw_audit_pass,
        }
        try:
            scores = {
                "candidate": scorer.score_raw(candidate_raw_path, gravity, max_tilt),
                "B": scorer.score_raw(b_path, gravity, max_tilt),
                "C5": scorer.score_raw(c5_path, gravity, max_tilt),
                "WN18": scorer.score_raw(parent_raw_path, gravity, max_tilt),
            }
        except Exception as exc:
            scores = None
            audit_failures.append({"scene_id": sid, "stage": "score", "error": f"{type(exc).__name__}: {exc}"})

        marker_has_phase = "authorization_phase" in marker
        marker_records.append({"scene_id": marker.get("scene_id"), "path": str(marker_path),
                               "authorization_phase_present": marker_has_phase,
                               "release_sha256": marker.get("release_sha256"),
                               "stage": marker.get("stage")})
        scene_records.append({
            "scene_id": sid, "screen_band": rec["screen_band"], "source_split": rec["source_split"],
            "wind_index": rec["wind_index"], "authorization_phase": phase,
            "run_dir": str(run_dir), "candidate_raw_path_planned": str(planned_path),
            "candidate_raw_path_actual": str(candidate_raw_path), "candidate_raw_path_mismatch": not raw_row_checks["candidate_path_matches_plan"],
            "candidate_raw_sha256": candidate_raw_sha, "run_status_path": str(status_path),
            "run_status_sha256": sha(status_path), "run_start_sha256": sha(start_path),
            "payload_path": rec["payload_path"], "payload_sha256_actual": sha(Path(rec["payload_path"])),
            "B_raw_path": str(b_path), "B_raw_sha256_actual": sha(b_path),
            "B_status_path": rec["b_status_path"], "B_status_sha256_actual": sha(Path(rec["b_status_path"])),
            "C5_raw_path": str(c5_path), "C5_raw_sha256_actual": sha(c5_path),
            "C5_status_path": rec["c5_status_path"], "C5_status_sha256_actual": sha(Path(rec["c5_status_path"])),
            "marker_path": str(marker_path), "marker_sha256": sha(marker_path),
            "marker_authorization_phase_present": marker_has_phase,
            "start_release_sha256": start.get("release_sha256"),
            "source_lock_sha256": start.get("source_lock_sha256"),
            "source_diff_sha256": start.get("source_diff_sha256"),
            "model_sha256": start.get("gru_model_sha256"),
            "payload_sha256": start.get("payload_sha256"),
            "B_raw_sha256": rec["b_raw_sha256"], "C5_raw_sha256": rec["c5_raw_sha256"],
            "identity": identity, "checks": raw_row_checks,
            "integrity_pass": all(v for k, v in raw_row_checks.items() if k != "candidate_path_matches_plan"),
            "parent_WN18_source": {
                "raw_path": str(parent_raw_path), "raw_sha256": parent_raw_sha,
                "status_sha256": sha(parent_status_path), "start_sha256": sha(parent_start_path),
                "source_study": "gru_stream_cosine_tracking_head_dev_v1" if parent_rec.get("candidate_reuse") else "gru_stream_cosine_tracking_head_full72_v1",
                "candidate_reuse": bool(parent_rec.get("candidate_reuse")),
                "source_lock_sha256": parent_start.get("source_lock_sha256"),
                "parent_raw_audit_path": str(parent_audit_path) if parent_rec.get("candidate_reuse") else None,
                "parent_raw_audit_status": parent_rec.get("candidate_parent_audit_status"),
                "parent_raw_audit_sha256_expected": parent_rec.get("candidate_audit_sha256"),
                "parent_raw_audit_sha256_actual": parent_audit_sha_actual,
                "checks": {k: bool(v) for k, v in parent_checks.items()},
                "integrity_pass": all(parent_checks.values()),
            },
            "scores": scores,
        })
        if not all(v for k, v in raw_row_checks.items() if k != "candidate_path_matches_plan"):
            audit_failures.append({"scene_id": sid, "stage": "integrity", "failed_checks": [k for k, v in raw_row_checks.items() if k != "candidate_path_matches_plan" and not v]})
        if not all(parent_checks.values()):
            audit_failures.append({"scene_id": sid, "stage": "WN18_source_integrity", "failed_checks": [k for k, v in parent_checks.items() if not v]})

    # The runtime RELEASE authorizes exactly the 11 remaining IDs. Compare it against both
    # the fixed launcher order and the unique completed REMAINING11 run_start records.
    remaining_started = [x["scene_id"] for x in scene_records if x["authorization_phase"] == "REMAINING11"]
    marker_ids = [x["scene_id"] for x in marker_records]
    launcher_and_snapshot_order_match = launcher_ids == authorized
    remaining_runstart_set_match = len(remaining_started) == 11 and set(remaining_started) == set(authorized) and len(set(remaining_started)) == 11
    all_scenes_once = (len(scene_records) == 12 and len({x["scene_id"] for x in scene_records}) == 12
                       and len(marker_ids) == 12 and len(set(marker_ids)) == 12 and set(marker_ids) == set(manifest_ids))

    score_complete = all(x["scores"] is not None for x in scene_records)
    methods = ("candidate", "B", "C5", "WN18")
    metrics = ("Q_m", "task_SO3_rad", "inner_SO3_rad")
    groups = {
        "ALL12": manifest_ids,
        "HF_W09_W14": [x["scene_id"] for x in scene_records if x["screen_band"] == "HF"],
        "W15": [x["scene_id"] for x in scene_records if x["screen_band"] == "W15"],
        "W00_W08": [x["scene_id"] for x in scene_records if x["screen_band"] == "W00_W08"],
    }
    score_by_id = {x["scene_id"]: x["scores"] for x in scene_records}
    group_means = {}
    if score_complete:
        for gname, ids in groups.items():
            group_means[gname] = {m: {metric: float(np.mean([score_by_id[sid][m][metric] for sid in ids])) for metric in metrics} for m in methods}
    else:
        group_means = {g: None for g in groups}

    gates = {"status": "NOT_EVALUATED"}
    wins = {}
    if score_complete:
        macro = group_means["ALL12"]
        gates = {
            "Q_candidate_lte_B": macro["candidate"]["Q_m"] <= macro["B"]["Q_m"],
            "Q_candidate_lte_1_05_C5": macro["candidate"]["Q_m"] <= 1.05 * macro["C5"]["Q_m"],
            "task_SO3_candidate_strictly_lt_B": macro["candidate"]["task_SO3_rad"] < macro["B"]["task_SO3_rad"],
            "task_SO3_candidate_strictly_lt_C5": macro["candidate"]["task_SO3_rad"] < macro["C5"]["task_SO3_rad"],
            "safety_zero_all_12_candidate_raws": all(
                all(v == 0 for v in x["scores"]["candidate"]["safety"].values()) for x in scene_records),
            "all_12_integrity_checks": all(x["integrity_pass"] for x in scene_records),
            "all_12_scores_available": True,
        }
        gates["overall_pass"] = all(gates.values())
        for comparator in ("B", "C5"):
            wins[comparator] = {}
            for metric in metrics:
                counts = {"strict_wins": 0, "ties_within_1e-12": 0, "strict_losses": 0}
                for sid in manifest_ids:
                    a = score_by_id[sid]["candidate"][metric]
                    b = score_by_id[sid][comparator][metric]
                    if a < b - 1e-12:
                        counts["strict_wins"] += 1
                    elif a > b + 1e-12:
                        counts["strict_losses"] += 1
                    else:
                        counts["ties_within_1e-12"] += 1
                wins[comparator][metric] = counts
    wn12_minus_wn18 = ({g: {metric: group_means[g]["candidate"][metric] - group_means[g]["WN18"][metric] for metric in metrics}
                        for g in groups} if score_complete else None)

    external_results = []
    for rec in external_lock.get("external_files", []):
        p = Path(rec["path"])
        actual = sha(p) if p.is_file() else None
        external_results.append({"role": rec["role"], "path": str(p), "expected_sha256": rec["sha256"],
                                 "actual_sha256": actual, "pass": actual == rec["sha256"]})

    snapshot_scenes_pass = (runtime_release.get("status") == "RELEASED" and
        runtime_release.get("authorization_phase") == "REMAINING11" and
        runtime_release.get("authorized_Plant_calls") == 11 and runtime_release.get("TEST_read") is False and
        len(authorized) == 11 and len(set(authorized)) == 11)
    audit = {
        "schema": "DL1018_FILTER_WN12_SCREEN12_RESULTS_V1",
        "audit_script_path": str(Path(__file__).resolve()),
        "audit_script_sha256": sha(Path(__file__).resolve()),
        "audit_scope": "12 locked DEV/VAL candidate raws and same-scene locked B/C5 comparator raws only; no reruns; no TEST",
        "status": "PASS_SCREEN_GATES" if score_complete and gates.get("overall_pass") else "SCREEN_GATE_FAIL" if score_complete else "INCOMPLETE_AUDIT",
        "study_id": runtime_release["study_id"], "candidate": runtime_release["candidate"],
        "snapshot_path": str(SNAPSHOT_PATH), "snapshot_sha256": expected_snapshot,
        "snapshot_expected_sha256": EXPECTED_SNAPSHOT_SHA, "snapshot_sha_matches_expected": expected_snapshot == EXPECTED_SNAPSHOT_SHA,
        "run_time_release_candidate": runtime_release["candidate"], "run_time_release_sha256": expected_snapshot,
        "model_path": runtime_release["model_path"], "model_sha256": runtime_release["model_sha256"],
        "model_actual_sha256": sha(Path(runtime_release["model_path"])),
        "metric_scorer_path": str(SCORER_PATH), "metric_scorer_sha256": sha(SCORER_PATH),
        "metric_constants_path": str(CONSTANTS_PATH), "metric_constants_sha256": sha(CONSTANTS_PATH),
        "metric_constants": {"gravity_mps2": gravity, "max_tilt_rad": max_tilt},
        "screen_scene_ids": manifest_ids, "remaining11_authorized_ids": authorized,
        "remaining11_launcher_ids": launcher_ids,
        "authorization_and_duplicate_guard": {
            "snapshot_has_exact_11_unique_ids": snapshot_scenes_pass,
            "launcher_order_matches_snapshot_exactly": launcher_and_snapshot_order_match,
            "remaining11_run_start_ids_unique_and_equal_snapshot": remaining_runstart_set_match,
            "all_12_scene_ids_have_one_run_start_and_marker": all_scenes_once,
            "marker_authorization_phase_missing_count": sum(not x["authorization_phase_present"] for x in marker_records),
            "markers": marker_records,
            "finding": "Markers omit authorization_phase, so the wrapper's phase-specific stageMarkerCount does not count these attempts. However, the 11 run_start IDs exactly match the 11 unique runtime-authorized IDs and the wrapper rejects a prior run_start with the same scene_id; the fixed Remaining11 launcher order also matches exactly. This is a bookkeeping weakness in the phase counter, not evidence of duplicate or out-of-scope runs in this 12-scene batch.",
        },
        "source_lineage": {
            "first_raw_run_source_lock_sha256": GATE_SOURCE_LOCK_SHA,
            "first_raw_historical_release_sha256": GATE_RELEASE_SHA,
            "first_raw_v1_wrapper_bytes_available": False,
            "remaining11_source_lock_sha256": runtime_release.get("source_lock_sha256"),
            "remaining11_source_diff_sha256": runtime_release.get("source_diff_sha256"),
            "current_source_tree": source_tree,
            "external_dependencies": external_results,
        },
        "phase_counts": {phase: sum(x["authorization_phase"] == phase for x in scene_records) for phase in ("ENGINEERING_GATE", "REMAINING11")},
        "safety_counts": {x["scene_id"]: x["scores"]["candidate"]["safety"] if x["scores"] else None for x in scene_records},
        "group_sizes": {k: len(v) for k, v in groups.items()},
        "group_macro_means": group_means,
        "WN12_minus_WN18_macro_delta": wn12_minus_wn18,
        "WN18_parent_lineage": {
            "parent_manifest_sha256": sha(PARENT_MANIFEST_PATH),
            "full72_release_sha256": sha(PARENT / "RELEASE.json"),
            "full72_source_lock_sha256": sha(parent_full_lock_path),
            "reused_dev_source_lock_sha256": sha(parent_dev_lock_path),
            "runtime_59_file_maps_identical": parent_runtime_source_equal,
            "full72_locked_cfg_sha256": parent_cfg_full_sha,
            "reused_dev_locked_cfg_sha256": parent_cfg_dev_sha,
            "wn12_locked_cfg_sha256": sha(STUDY / "LOCKED_CFG.json"),
            "WN18_command_filter_wn": parent_cfg.get("command_filter", {}).get("wn"),
            "WN12_command_filter_wn": locked_cfg.get("command_filter", {}).get("wn"),
            "model_sha256": parent_model_sha,
            "candidate_reuse_scenes": [x["scene_id"] for x in scene_records if x["parent_WN18_source"]["candidate_reuse"]],
            "reuse_note": "The two W15 candidate_reuse rows reference the existing gru_stream_cosine_tracking_head_dev_v1 raw/status/start; their parent raw-audit status and SHA, 59 runtime file hashes, LOCKED_CFG and model hashes are checked against full72 lineage.",
        },
        "candidate_vs_comparator_scene_wins": wins,
        "screen_gates": gates,
        "scenes": scene_records,
        "audit_failures": audit_failures,
        "limitations": [
            "The first raw's historical RELEASE and v1 wrapper bytes are not archived; run-time SHA consistency and the v1 59-file runtime lock are checked, but the current wrapper is not claimed as the first raw's execution source.",
            "The marker JSON omits authorization_phase; the report documents the counter impact and checks unique run_start IDs against the runtime snapshot and launcher list.",
        ],
    }

    csv_fields = ["scene_id", "screen_band", "source_split", "authorization_phase", "integrity_pass",
        "candidate_path_mismatch", "candidate_raw_sha256", "Q_candidate_m", "Q_B_m", "Q_C5_m",
        "task_SO3_candidate_rad", "task_SO3_B_rad", "task_SO3_C5_rad",
        "inner_SO3_candidate_rad", "inner_SO3_B_rad", "inner_SO3_C5_rad", "Q_WN18_m",
        "task_SO3_WN18_rad", "inner_SO3_WN18_rad", "candidate_minus_WN18_Q_m",
        "candidate_minus_WN18_task_SO3_rad", "candidate_minus_WN18_inner_SO3_rad",
        "candidate_minus_B_Q_m", "candidate_minus_C5_Q_m",
        "candidate_minus_B_task_SO3_rad", "candidate_minus_C5_task_SO3_rad",
        "candidate_minus_B_inner_SO3_rad", "candidate_minus_C5_inner_SO3_rad",
        "motor_saturation_samples", "generalized_clip_samples", "tilt_limited_samples",
        "attitude_head_projection_samples", "attitude_head_output_saturated_samples"]
    csv_rows = []
    for x in scene_records:
        sc = x["scores"]
        out = {"scene_id": x["scene_id"], "screen_band": x["screen_band"], "source_split": x["source_split"],
               "authorization_phase": x["authorization_phase"], "integrity_pass": x["integrity_pass"],
               "candidate_path_mismatch": x["candidate_raw_path_mismatch"], "candidate_raw_sha256": x["candidate_raw_sha256"]}
        if sc:
            for m in methods:
                out[f"Q_{m}_m"] = sc[m]["Q_m"]
                out[f"task_SO3_{m}_rad"] = sc[m]["task_SO3_rad"]
                out[f"inner_SO3_{m}_rad"] = sc[m]["inner_SO3_rad"]
            for comp in ("B", "C5"):
                out[f"candidate_minus_{comp}_Q_m"] = sc["candidate"]["Q_m"] - sc[comp]["Q_m"]
                out[f"candidate_minus_{comp}_task_SO3_rad"] = sc["candidate"]["task_SO3_rad"] - sc[comp]["task_SO3_rad"]
                out[f"candidate_minus_{comp}_inner_SO3_rad"] = sc["candidate"]["inner_SO3_rad"] - sc[comp]["inner_SO3_rad"]
            out["candidate_minus_WN18_Q_m"] = sc["candidate"]["Q_m"] - sc["WN18"]["Q_m"]
            out["candidate_minus_WN18_task_SO3_rad"] = sc["candidate"]["task_SO3_rad"] - sc["WN18"]["task_SO3_rad"]
            out["candidate_minus_WN18_inner_SO3_rad"] = sc["candidate"]["inner_SO3_rad"] - sc["WN18"]["inner_SO3_rad"]
            out.update(sc["candidate"]["safety"])
        csv_rows.append(out)

    OUTPUT_JSON.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=csv_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(csv_rows)

    lines = [
        "# Filter wn12: 12-scene screen audit",
        "",
        f"Status: **{audit['status']}**. Runtime release snapshot SHA: `{expected_snapshot}`.",
        f"Scenes: {len(scene_records)} total; {audit['phase_counts']['ENGINEERING_GATE']} engineering gate + {audit['phase_counts']['REMAINING11']} remaining11. Snapshot/launcher exact-ID checks: {snapshot_scenes_pass and launcher_and_snapshot_order_match}; unique run starts: {remaining_runstart_set_match}.",
        f"Metric scorer: `{SCORER_PATH}` (SHA `{audit['metric_scorer_sha256']}`); gravity {gravity:g} m/s², max tilt {max_tilt:.12g} rad.",
        "",
        "## Macro means and group means",
        "",
        "| Cohort | n | Method | Q (m) | task SO(3) (rad) | inner SO(3) (rad) |",
        "|---|---:|---|---:|---:|---:|",
    ]
    if score_complete:
        for gname, ids in groups.items():
            for method in methods:
                m = group_means[gname][method]
                lines.append(f"| {gname} | {len(ids)} | {method} | {m['Q_m']:.12g} | {m['task_SO3_rad']:.12g} | {m['inner_SO3_rad']:.12g} |")
        lines += ["", "WN12 minus parent WN18 (same frozen scorer; negative means lower error):", ""]
        for gname in groups:
            d = wn12_minus_wn18[gname]
            lines.append(f"- {gname} (n={len(groups[gname])}): ΔQ={d['Q_m']:.12g} m; Δtask SO(3)={d['task_SO3_rad']:.12g} rad; Δinner SO(3)={d['inner_SO3_rad']:.12g} rad.")
        lines += ["", "## TASKBOOK screen gates", ""]
        for k, v in gates.items():
            lines.append(f"- {'PASS' if v else 'FAIL'} — `{k}`")
        lines += ["", "## Candidate safety counts", "", "| Scene | Motor sat | Generalized clip | Tilt limit | Head projection | Head saturated |", "|---|---:|---:|---:|---:|---:|"]
        for x in scene_records:
            safe = x["scores"]["candidate"]["safety"]
            lines.append(f"| {x['scene_id']} | {safe['motor_saturation_samples']} | {safe['generalized_clip_samples']} | {safe['tilt_limited_samples']} | {safe['attitude_head_projection_samples']} | {safe['attitude_head_output_saturated_samples']} |")
        lines += ["", "## Strict per-scene wins (ties within 1e-12)", ""]
        for comp in ("B", "C5"):
            for metric in metrics:
                w = wins[comp][metric]
                lines.append(f"- Candidate vs {comp}, {metric}: {w['strict_wins']} wins, {w['ties_within_1e-12']} ties, {w['strict_losses']} losses.")
    lines += [
        "",
        "## Audit findings",
        "",
        f"- Candidate raw path differs from the locked planned output path in {sum(x['candidate_raw_path_mismatch'] for x in scene_records)} scene(s); the first engineering-gate raw remains status/SHA-bound at its original location.",
        f"- Parent WN18 comparator raw replay lineage: {sum(x['parent_WN18_source']['integrity_pass'] for x in scene_records)}/12 pass; two W15 rows reuse the existing dev_v1 raw lineage.",
        f"- Attempt markers missing `authorization_phase`: {audit['authorization_and_duplicate_guard']['marker_authorization_phase_missing_count']}/12. See JSON for the phase-counter impact and run_start/launcher duplicate guard evidence.",
        f"- Source tree: v1 runtime files {source_tree['v1_runtime_files_pass']}/{source_tree['v1_runtime_files_checked']}; v2 files {source_tree['v2_files_pass']}/{source_tree['v2_files_checked']}. v1 wrapper bytes remain unavailable.",
        "- No MATLAB/Plant/training was launched by this audit; no TEST inputs were read; raw files were not changed.",
        "",
        f"Full provenance, per-scene metrics, all checks and findings: `{OUTPUT_JSON.name}`. Per-scene table: `{OUTPUT_CSV.name}`.",
        "",
    ]
    OUTPUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": audit["status"], "json": str(OUTPUT_JSON), "csv": str(OUTPUT_CSV),
                      "markdown": str(OUTPUT_MD), "gates": gates, "failed_integrity_scenes": [x["scene_id"] for x in scene_records if not x["integrity_pass"]],
                      "audit_failures": audit_failures}, indent=2))


if __name__ == "__main__":
    main()
