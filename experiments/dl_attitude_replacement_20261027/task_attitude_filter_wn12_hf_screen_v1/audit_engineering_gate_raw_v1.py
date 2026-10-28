"""Read-only audit of the single authorized filter-wn12 engineering-gate raw.

This scores only the first candidate raw and the same-scene locked B/C5 raws.
It does not launch MATLAB/Plant, read TEST data, or alter any input.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import h5py
import numpy as np


ROOT = Path(__file__).resolve().parents[3]
STUDY = Path(__file__).resolve().parent
SCENE_ID = "DL1018_DEV_T1_C10_W09"
RAW = STUDY / "runs" / SCENE_ID / "raw_run.mat"
STATUS_PATH = RAW.with_name("run_status.json")
START_PATH = RAW.with_name("run_start.json")
MANIFEST_PATH = STUDY / "MANIFEST.json"
INPUT_LOCK_PATH = STUDY / "INPUT_LOCK_v1.json"
RELEASE_PATH = STUDY / "RELEASE.json"
SOURCE_LOCK_PATH = STUDY / "SOURCE_LOCK_v1.json"
SOURCE_DIFF_PATH = STUDY / "SOURCE_DIFF_v1.json"
LOCKED_CFG_PATH = STUDY / "LOCKED_CFG.json"
EXTERNAL_LOCK_PATH = STUDY / "DEPENDENCY_EXTERNAL_LOCK_v1.json"
PATH_ADDENDUM_PATH = STUDY / "PATH_RECONCILIATION_ADDENDUM_v1.md"
OUTPUT_JSON = STUDY / "ENGINEERING_GATE_RAW_AUDIT_v1.json"
OUTPUT_MD = STUDY / "ENGINEERING_GATE_RAW_AUDIT_v1.md"
SCORER_PATH = (ROOT / "experiments" / "dl_attitude_replacement_20261026" /
               "gru_stream_cosine_tracking_head_full72_v1" / "audits" /
               "score_full72_candidate_v1.py")
CONSTANTS_PATH = (ROOT / "experiments" / "dl_attitude_replacement_20261026" /
                  "mlp15_composite_dev_v3" / "RELEASE.json")
PARENT_RELEASE_PATH = (ROOT / "experiments" / "dl_attitude_replacement_20261026" /
                       "gru_stream_cosine_tracking_head_full72_v1" / "RELEASE.json")


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def readj(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def matstr(ds) -> str:
    a = np.asarray(ds[()]).reshape(-1)
    if a.dtype.kind in "ui":
        return "".join(chr(int(x)) for x in a if int(x))
    return "".join(x.decode("utf-8") if isinstance(x, bytes) else str(x) for x in a)


def h5_value(path: Path, field: str):
    with h5py.File(path, "r") as f:
        v = f[field]
        if isinstance(v, h5py.Dataset) and v.attrs.get("MATLAB_class", b"") == b"char":
            return matstr(v)
        return np.asarray(v[()])


def diagnostic_nonfinites(group) -> dict:
    bad, floats, datasets = [], 0, 0
    def visit(name, obj):
        nonlocal floats, datasets
        if not isinstance(obj, h5py.Dataset):
            return
        datasets += 1
        if np.issubdtype(obj.dtype, np.floating):
            floats += 1
            values = np.asarray(obj[()])
            if not np.isfinite(values).all():
                bad.append(name)
    group.visititems(visit)
    return {"datasets_checked": datasets, "floating_datasets_checked": floats,
            "nonfinite_dataset_paths": bad}


def count_any(arr) -> int:
    a = np.asarray(arr, dtype=bool)
    if a.ndim == 1:
        return int(a.sum())
    return int(np.any(a, axis=0).sum())


def digest_sources(lock: dict) -> dict:
    results = []
    for rec in lock["files"]:
        path = STUDY / "candidate_runner_work" / Path(rec["relative_path"])
        actual = sha(path) if path.is_file() else None
        results.append({"relative_path": rec["relative_path"], "expected_sha256": rec["sha256"],
                        "actual_sha256": actual, "pass": actual == rec["sha256"]})
    return {"count": len(results), "pass_count": sum(x["pass"] for x in results),
            "mismatches": [x for x in results if not x["pass"]]}


def digest_external(lock: dict) -> dict:
    results = []
    for rec in lock.get("copied_metadata", []):
        source = Path(rec["source_path"])
        copy = STUDY / rec["study_relative_copy"]
        source_sha = sha(source) if source.is_file() else None
        copy_sha = sha(copy) if copy.is_file() else None
        results.append({"role": rec["role"], "expected_sha256": rec["sha256"],
                        "source_sha256": source_sha, "copy_sha256": copy_sha,
                        "pass": source_sha == rec["sha256"] == copy_sha})
    for rec in lock.get("external_files", []):
        p = Path(rec["path"])
        actual = sha(p) if p.is_file() else None
        results.append({"role": rec["role"], "expected_sha256": rec["sha256"],
                        "actual_sha256": actual, "pass": actual == rec["sha256"]})
    return {"count": len(results), "pass_count": sum(x["pass"] for x in results),
            "mismatches": [x for x in results if not x["pass"]]}


def main():
    scorer_spec = importlib.util.spec_from_file_location("frozen_gru_paired_scorer", SCORER_PATH)
    scorer = importlib.util.module_from_spec(scorer_spec)
    scorer_spec.loader.exec_module(scorer)

    manifest = readj(MANIFEST_PATH)
    row = next(x for x in manifest["records"] if x["scene_id"] == SCENE_ID)
    input_lock = readj(INPUT_LOCK_PATH)
    input_row = next(x for x in input_lock["records"] if x["scene_id"] == SCENE_ID)
    release = readj(RELEASE_PATH)
    start = readj(START_PATH)
    status = readj(STATUS_PATH)
    source_lock = readj(SOURCE_LOCK_PATH)
    source_diff = readj(SOURCE_DIFF_PATH)
    locked_cfg = readj(LOCKED_CFG_PATH)
    external_lock = readj(EXTERNAL_LOCK_PATH)
    constants = readj(CONSTANTS_PATH)
    parent_release = readj(PARENT_RELEASE_PATH)
    locked_model_id = Path(parent_release["model_path"]).parent.name

    actual_raw_sha = sha(RAW)
    actual_release_sha = sha(RELEASE_PATH)
    actual_manifest_sha = sha(MANIFEST_PATH)
    actual_source_lock_sha = sha(SOURCE_LOCK_PATH)
    actual_source_diff_sha = sha(SOURCE_DIFF_PATH)
    actual_locked_cfg_sha = sha(LOCKED_CFG_PATH)
    actual_addendum_sha = sha(PATH_ADDENDUM_PATH)
    actual_payload_sha = sha(Path(row["payload_path"]))
    actual_model_sha = sha(Path(release["model_path"]))
    b_path, c5_path = Path(row["b_raw_path"]), Path(row["c5_raw_path"])
    b_sha, c5_sha = sha(b_path), sha(c5_path)

    with h5py.File(RAW, "r") as f:
        log = f["log"]
        identity = {k: matstr(v) if v.attrs.get("MATLAB_class", b"") == b"char"
                    else bool(np.asarray(v[()]).reshape(-1)[0])
                    if v.attrs.get("MATLAB_class", b"") == b"logical"
                    else float(np.asarray(v[()]).reshape(-1)[0])
                    for k, v in f["runIdentity"].items() if isinstance(v, h5py.Dataset)}
        scene_id_raw = matstr(f["scene/scene_id"])
        state = np.asarray(log["state"][()], dtype=float).T
        time = np.asarray(log["time"][()], dtype=float).reshape(-1)
        transitions = int(np.asarray(log["actual_transition_count"][()]).reshape(-1)[0])
        samples = int(np.asarray(log["actual_state_sample_count"][()]).reshape(-1)[0])
        complete = bool(np.asarray(log["complete_transitions"][()]).reshape(-1)[0])
        safety_counts = {
            "motor_saturation_samples": count_any(log["motor_saturated"][()]),
            "generalized_clip_samples": count_any(log["generalized_clipped"][()]),
            "tilt_limited_samples": count_any(log["tilt_limited"][()]),
            "attitude_head_projection_samples": count_any(log["attitude_head_projection_active"][()]),
            "attitude_head_output_saturated_samples": count_any(log["attitude_head_output_saturated"][()]),
        }
        diagnostic_nonfinite = {"log": diagnostic_nonfinites(log), "scene": diagnostic_nonfinites(f["scene"])}
        hard_finite_fields = {
            key: bool(np.isfinite(f[key][()]).all())
            for key in ("log/state", "log/time", "scene/reference/position",
                        "scene/reference/acceleration", "scene/reference/yaw",
                        "log/command_filter_target_euler", "log/command_filter_acceleration_applied_rads2",
                        "log/filtered_attitude_reference", "log/filtered_attitude_rate")
        }
        dt_max_abs_error = float(np.max(np.abs(np.diff(time) - 0.001)))
        target_shape = tuple(log["command_filter_target_euler"].shape)
        filtered_shape = tuple(log["filtered_attitude_reference"].shape)
        filter_target_finite = bool(np.isfinite(log["command_filter_target_euler"][()]).all())
        filter_output_finite = bool(np.isfinite(log["filtered_attitude_reference"][()]).all())

    gravity, max_tilt = float(constants["gravity_mps2"]), float(constants["max_tilt_rad"])
    scores = {
        "candidate": scorer.score_raw(RAW, gravity, max_tilt),
        "B": scorer.score_raw(b_path, gravity, max_tilt),
        "C5": scorer.score_raw(c5_path, gravity, max_tilt),
    }

    # Confirm all three raws use precisely the same scene reference and identifier.
    reference_equal = {"scene_id": [], "reference_position": [], "reference_acceleration": [], "reference_yaw": []}
    for key, path in (("candidate", RAW), ("B", b_path), ("C5", c5_path)):
        reference_equal["scene_id"].append((key, h5_value(path, "scene/scene_id")))
    for key, field in (("reference_position", "scene/reference/position"),
                       ("reference_acceleration", "scene/reference/acceleration"),
                       ("reference_yaw", "scene/reference/yaw")):
        arrays = [(name, np.asarray(h5_value(path, field)))
                  for name, path in (("candidate", RAW), ("B", b_path), ("C5", c5_path))]
        reference_equal[key] = bool(np.array_equal(arrays[0][1], arrays[1][1]) and
                                    np.array_equal(arrays[0][1], arrays[2][1]))
    reference_equal["scene_id"] = {k: v for k, v in reference_equal["scene_id"]}
    reference_equal["all_equal"] = (len(set(reference_equal["scene_id"].values())) == 1 and
                                    all(reference_equal[k] for k in
                                        ("reference_position", "reference_acceleration", "reference_yaw")))

    expected_identity = {
        "scene_id": SCENE_ID,
        "candidate": release["candidate"],
        "authorization_phase": "ENGINEERING_GATE",
        "frozen_model_candidate": locked_model_id,
        "release_sha256": start["release_sha256"],
        "manifest_sha256": actual_manifest_sha,
        "source_lock_sha256": actual_source_lock_sha,
        "source_diff_sha256": actual_source_diff_sha,
        "locked_cfg_sha256": actual_locked_cfg_sha,
        "b_raw_sha256": row["b_raw_sha256"],
        "c5_raw_sha256": row["c5_raw_sha256"],
        "payload_sha256": actual_payload_sha,
        "gru_model_sha256": release["model_sha256"],
        "c5_input_lock_sha256": locked_cfg["c5_input_lock_sha256"],
        "c5_snapshot_sha256": locked_cfg["c5_snapshot_sha256"],
        "position_model_sha256": locked_cfg["position_model_sha256"],
        "common_position_options_sha256": locked_cfg["common_position_options_sha256"],
        "TEST_read": False,
        "Plant_truth_deployment_input": False,
        "base_model_weights_fixed": True,
        "tracking_delta_weights_online": True,
        "hidden_state_reset_per_scene": True,
    }
    identity_checks = {k: {"actual": identity.get(k), "expected": v,
                           "pass": identity.get(k) == v} for k, v in expected_identity.items()}

    source_hashes = digest_sources(source_lock)
    external_hashes = digest_external(external_lock)
    j0 = np.asarray(locked_cfg["J0_kgm2"], dtype=float)
    j0_check = {"matrix": j0.tolist(), "symmetric": bool(np.allclose(j0, j0.T, atol=1e-18)),
                "principal_values_positive": bool(np.all(np.linalg.eigvalsh(j0) > 0)),
                "sha256_recorded": locked_cfg["J0_sha256"],
                "fixed_inertia_matches": bool(np.array_equal(j0, np.asarray(locked_cfg["Pfixed_inertia_kgm2"], dtype=float))),
                "fixed_inertia_dot_is_zero": bool(np.array_equal(
                    np.asarray(locked_cfg["Pfixed_inertia_dot_for_bs_kgm2_s"], dtype=float), np.zeros((3, 3))))}

    checks = {
        "raw_scene_identity": scene_id_raw == SCENE_ID,
        "raw_sha_matches_run_status": actual_raw_sha == status["raw_sha256"],
        "status_raw_path_matches_produced_raw": Path(status["raw_path"]).resolve() == RAW.resolve(),
        "run_status_completed_stable": status["state"] == "COMPLETED" and status["status_value"] == "STABLE",
        "run_status_counts": status["transitions"] == transitions == 20000 and status["state_samples"] == samples == 20001,
        "complete_transition_flag": complete,
        "status_safety_stop_empty": status["safety_stop_reason"] == "",
        "timebase_1ms": dt_max_abs_error < 1e-10,
        "state_shape_20001x12": state.shape == (20001, 12),
        "state_finite": bool(np.isfinite(state).all()),
        "scorer_filter_and_output_arrays_finite": all(hard_finite_fields.values()),
        "scorer_metrics_finite": all(np.isfinite(scores["candidate"][k]) for k in scorer.MAIN),
        "filter_target_output_shapes": target_shape == (3, 20000) and filtered_shape == (3, 20000),
        "filter_target_output_finite": filter_target_finite and filter_output_finite,
        "status_and_identity_run_release_sha_agree": status["release_sha256"] == start["release_sha256"] == identity.get("release_sha256"),
        "run_start_manifest_sha_matches_current": start["manifest_sha256"] == actual_manifest_sha,
        "run_start_source_lock_sha_matches_current": start["source_lock_sha256"] == actual_source_lock_sha,
        "run_start_source_diff_sha_matches_current": start["source_diff_sha256"] == actual_source_diff_sha,
        "run_start_locked_cfg_sha_matches_current": start["locked_cfg_sha256"] == actual_locked_cfg_sha,
        "run_start_model_sha_matches_current": start["gru_model_sha256"] == actual_model_sha,
        "run_start_candidate_matches_release_candidate": start["candidate"] == release["candidate"],
        "release_base_candidate_matches_locked_parent_arm": release["base_candidate"] == parent_release["candidate"],
        "locked_parent_model_sha_matches_candidate_model": parent_release["model_sha256"] == release["model_sha256"] == actual_model_sha,
        "run_start_frozen_model_candidate_matches_locked_parent_model_id": start["frozen_model_candidate"] == locked_model_id,
        "B_C5_sha_matches_manifest": b_sha == row["b_raw_sha256"] and c5_sha == row["c5_raw_sha256"],
        "payload_sha_matches_manifest": actual_payload_sha == row["payload_sha256"],
        "scene_references_match_across_candidate_B_C5": reference_equal["all_equal"],
        "source_files_match_lock": not source_hashes["mismatches"],
        "external_dependencies_match_lock": not external_hashes["mismatches"],
        "locked_cfg_filter_is_12_12_12": locked_cfg["command_filter"]["wn"] == [12, 12, 12],
        "J0_binding_sane": j0_check["symmetric"] and j0_check["principal_values_positive"] and j0_check["fixed_inertia_matches"] and j0_check["fixed_inertia_dot_is_zero"],
        "current_release_is_postrun_DRAFT": release["status"] == "DRAFT" and release["authorized_Plant_calls"] == 0 and release["Plant_calls_completed"] == 1 and release["engineering_gate_raw_sha256"] == actual_raw_sha,
        "release_resource_ledger_matches_record": (release["MATLAB_runs"] == release["MATLAB_processes_started"] == 5 and
            release["pre_marker_failed_launches"] == 2 and release["MATLAB_prepare_only_runs"] == 2 and
            release["closed_loop_runs_started"] == 1 and release["Plant_calls_completed"] == 1),
        "path_addendum_matches_release_lock": release["path_reconciliation_addendum_sha256"] == actual_addendum_sha,
    }

    manifest_path = Path(row["candidate_raw_path"])
    input_lock_raw_path = Path(input_row["candidate_raw_path"])
    candidate_path_reconciliation = {
        "manifest_and_input_lock_paths_agree": str(manifest_path) == str(input_lock_raw_path),
        "locked_planned_candidate_path": str(manifest_path),
        "actual_first_candidate_raw_path": str(RAW),
        "actual_status_raw_path": status["raw_path"],
        "planned_candidate_path_matches_first_output": manifest_path.resolve() == RAW.resolve(),
        "raw_sha_matches_status_and_identity_scene_matches_run_start": actual_raw_sha == status["raw_sha256"] and identity.get("scene_id") == start["scene_id"],
        "resolution": "First raw remains in its original wrapper-created location; subsequent scene outputs follow record.candidate_raw_path after in-study canonical path validation.",
    }
    checks.update({f"run_identity_{k}": v["pass"] for k, v in identity_checks.items()})

    comparisons = {}
    for metric in ("Q_m", "task_SO3_rad", "inner_SO3_rad"):
        comparisons[metric] = {name: scores[name][metric] for name in ("candidate", "B", "C5")}
    for comparator in ("B", "C5"):
        comparisons[f"candidate_minus_{comparator}"] = {
            metric: scores["candidate"][metric] - scores[comparator][metric]
            for metric in ("Q_m", "task_SO3_rad", "inner_SO3_rad")}

    audit = {
        "schema": "DL1018_FILTER_WN12_SINGLE_ENGINEERING_GATE_RAW_AUDIT_V1",
        "scene_id": SCENE_ID,
        "audit_scope": "candidate raw plus same-scene locked B/C5 raws only; no TEST, no reruns",
        "raw_path": str(RAW),
        "raw_sha256": actual_raw_sha,
        "raw_bytes": RAW.stat().st_size,
        "run_status_sha256": sha(STATUS_PATH),
        "run_start_sha256": sha(START_PATH),
        "release_current_sha256": actual_release_sha,
        "run_release_sha256": start["release_sha256"],
        "run_identity": identity,
        "manifest_candidate_raw_path": str(manifest_path),
        "actual_candidate_raw_path": str(RAW),
        "raw_counts": {"transitions": transitions, "state_samples": samples,
                        "status_value": status["status_value"], "complete_transitions": complete,
                        "timebase_max_abs_dt_error_s": dt_max_abs_error,
                        "state_shape": list(state.shape), "state_finite": bool(np.isfinite(state).all()),
                        "hard_finite_fields": hard_finite_fields,
                        "diagnostic_nonfinite_fields": diagnostic_nonfinite},
        "safety_counts": safety_counts,
        "resource_ledger": {"MATLAB_processes_started": release["MATLAB_processes_started"],
                             "MATLAB_runs": release["MATLAB_runs"],
                             "pre_marker_failed_launches": release["pre_marker_failed_launches"],
                             "prepare_only_runs": release["MATLAB_prepare_only_runs"],
                             "closed_loop_runs_started": release["closed_loop_runs_started"],
                             "Plant_calls_completed": release["Plant_calls_completed"],
                             "authorized_Plant_calls": release["authorized_Plant_calls"],
                             "RELEASE_status": release["status"]},
        "binding_hashes": {
            "manifest": {"actual": actual_manifest_sha, "run_start": start["manifest_sha256"]},
            "source_lock": {"actual": actual_source_lock_sha, "run_start": start["source_lock_sha256"], "files": source_hashes},
            "source_diff": {"actual": actual_source_diff_sha, "run_start": start["source_diff_sha256"]},
            "locked_cfg": {"actual": actual_locked_cfg_sha, "run_start": start["locked_cfg_sha256"]},
            "path_reconciliation_addendum": {"actual": actual_addendum_sha, "release": release["path_reconciliation_addendum_sha256"]},
            "payload": {"actual": actual_payload_sha, "manifest": row["payload_sha256"]},
            "gru_model": {"actual": actual_model_sha, "release": release["model_sha256"], "run_start": start["gru_model_sha256"]},
            "parent_model_lineage": {"parent_release_path": str(PARENT_RELEASE_PATH),
                                      "parent_release_sha256": sha(PARENT_RELEASE_PATH),
                                      "parent_arm_candidate": parent_release["candidate"],
                                      "locked_model_id_from_model_path": locked_model_id,
                                      "locked_model_sha256": parent_release["model_sha256"]},
            "B_raw": {"actual": b_sha, "manifest": row["b_raw_sha256"], "run_start": start["b_raw_sha256"]},
            "C5_raw": {"actual": c5_sha, "manifest": row["c5_raw_sha256"], "run_start": start["c5_raw_sha256"]},
            "external_dependencies": external_hashes,
            "J0": j0_check,
            "position_model_sha256": {"locked_cfg": locked_cfg["position_model_sha256"], "run_start": start["position_model_sha256"]},
            "common_position_options_sha256": {"locked_cfg": locked_cfg["common_position_options_sha256"], "run_start": start["common_position_options_sha256"]},
            "C5_input_lock_sha256": {"locked_cfg": locked_cfg["c5_input_lock_sha256"], "run_start": start["c5_input_lock_sha256"]},
            "C5_snapshot_sha256": {"locked_cfg": locked_cfg["c5_snapshot_sha256"], "run_start": start["c5_snapshot_sha256"]},
            "source_identity_fields": identity_checks,
        },
        "same_scene_reference_identity": reference_equal,
        "score_definition": {
            "scorer_path": str(SCORER_PATH), "scorer_sha256": sha(SCORER_PATH),
            "gravity_mps2": gravity, "max_tilt_rad": max_tilt,
            "constants_path": str(CONSTANTS_PATH), "constants_sha256": sha(CONSTANTS_PATH),
            "Q_m": "sqrt(mean over state samples of sum_xyz((position-reference)^2))",
            "task_SO3_rad": "RMSE geodesic SO(3) between Euler xyz state and tilt-limited acceleration+yaw task reference",
            "inner_SO3_rad": "RMSE geodesic SO(3) between Euler xyz state and filtered attitude reference over 20,000 transitions",
        },
        "scores": scores,
        "comparisons": comparisons,
        "checks": checks,
        "candidate_path_reconciliation": candidate_path_reconciliation,
        "result": ("PASS_METRICS_AND_IDENTITY_WITH_FIRST_OUTPUT_PATH_MISMATCH"
                   if all(checks.values()) and not candidate_path_reconciliation["planned_candidate_path_matches_first_output"]
                   else "PASS_ALL_CHECKS" if all(checks.values()) else "FAIL"),
        "limitations": [
            "This Python audit does not execute the MATLAB independent GRU replay auditor.",
            "The historic run-time RELEASE bytes are not preserved as a separate file; run_start/runIdentity carry the same SHA, while the current RELEASE is a post-run DRAFT with authorization withdrawn.",
            "The first raw was written at the scene root rather than its planned attempt_01 directory; status SHA and run identity bind the produced raw, and the addendum records the location. The wrapper now routes remaining scene outputs to the locked record path.",
        ],
    }
    OUTPUT_JSON.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        "# Engineering-gate raw audit — filter wn12",
        "",
        f"Scene: `{SCENE_ID}`. Result: **{audit['result']}**.",
        "",
        f"Candidate raw SHA-256: `{actual_raw_sha}` ({RAW.stat().st_size:,} bytes).",
        f"Status: {status['status_value']}; {transitions:,} transitions / {samples:,} states; time step max error {dt_max_abs_error:.3g} s.",
        f"Scorer, filter and output arrays finite: {checks['scorer_filter_and_output_arrays_finite']}; {len(diagnostic_nonfinite['log']['nonfinite_dataset_paths'])} log diagnostic fields contain non-finite values (full field paths are listed in the JSON).",
        "",
        "## Safety counts",
        "",
        *[f"- {k}: {v}" for k, v in safety_counts.items()],
        "",
        "## Frozen paired scorer results",
        "",
        f"Constants: gravity {gravity:g} m/s²; max tilt {max_tilt:.12g} rad. Scorer SHA-256: `{sha(SCORER_PATH)}`.",
        "",
        "| Metric | Candidate | B | C5 | Candidate − B | Candidate − C5 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for metric in ("Q_m", "task_SO3_rad", "inner_SO3_rad"):
        lines.append(f"| {metric} | {scores['candidate'][metric]:.12g} | {scores['B'][metric]:.12g} | {scores['C5'][metric]:.12g} | {comparisons['candidate_minus_B'][metric]:.12g} | {comparisons['candidate_minus_C5'][metric]:.12g} |")
    lines += [
        "",
        "## Binding and caveats",
        "",
        f"- Run start and raw identity release SHA agree: {checks['status_and_identity_run_release_sha_agree']}; current release SHA `{actual_release_sha}` differs from the recorded run-time SHA `{start['release_sha256']}` because the current release is DRAFT/0 after the call.",
        f"- Source lock files: {source_hashes['pass_count']}/{source_hashes['count']} SHA matches; external dependency files: {external_hashes['pass_count']}/{external_hashes['count']} SHA matches.",
        f"- Resource ledger: MATLAB process/run count {release['MATLAB_processes_started']}/{release['MATLAB_runs']}; pre-marker failures {release['pre_marker_failed_launches']}; prepare-only {release['MATLAB_prepare_only_runs']}; closed-loop {release['closed_loop_runs_started']}; Plant completed {release['Plant_calls_completed']}; authorized now {release['authorized_Plant_calls']} (RELEASE {release['status']}).",
        f"- Candidate / B / C5 scene ID and reference arrays match exactly: {reference_equal['all_equal']}.",
        f"- **First output path mismatch:** planned candidate path is `{manifest_path}`; produced raw remains at `{RAW}`. No file was moved or copied. `run_status.json` SHA and raw identity bind the produced file; see `PATH_RECONCILIATION_ADDENDUM_v1.md`.",
        f"- Model identities are distinct by role: run candidate `{start['candidate']}`, parent tracking-head arm `{release['base_candidate']}`, frozen weights id `{start['frozen_model_candidate']}`; the frozen weights id is checked against the locked parent model path and SHA.",
        "- This audit did not run MATLAB, Plant, B/C5 simulations, remaining scenes, or access TEST data. MATLAB replay closure remains for root's separate review.",
        "",
        "## Checks",
        "",
        *[f"- {'PASS' if v else 'FAIL'} — {k}" for k, v in checks.items()],
        "",
    ]
    OUTPUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"result": audit["result"], "json": str(OUTPUT_JSON), "markdown": str(OUTPUT_MD),
                      "scores": comparisons, "failed_checks": [k for k, v in checks.items() if not v]}, indent=2))


if __name__ == "__main__":
    main()
