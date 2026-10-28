"""Pair audited A1T SCREEN12 raws with the frozen A1R/C5/A1 result tables.

This scorer is intentionally not run until all twelve A1T raw logs have a
matching independent PASS audit. It does not launch MATLAB, Plant, or training.
"""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path
from typing import Any

REPORT_REL = "reports/attitude_cm18_datarepair_20261024/a1t_screen12_control_v1"
RUN_REL = "experiments/attitude_cm18_datarepair_20261024/a1t_screen12_control_v1/runs"
AUDITOR_REL = f"{REPORT_REL}/audit_a1t_screen12_log_v1.py"
AUDITOR_REVIEW_REL = f"{REPORT_REL}/ROOT_A1T_RAW_AUDITOR_REVIEW_v2.json"
MANIFEST_REL = "reports/attitude_cm18_a1_20261024/CM18_A1_DEV_SCREEN12_v1.json"
BASELINE_REL = "reports/attitude_cm18_a1_20261024/ROOT_SCREEN12_PAIRED_METRICS_v1.json"
SCORER_REL = "reports/attitude_cm18_a1_20261024/root_screen12_metrics_v1.py"
A1R_DIR_REL = "reports/attitude_cm18_datarepair_20261024/a1r_screen12_control_v1"
A1R_JSON_REL = f"{A1R_DIR_REL}/ROOT_A1R_SCREEN12_PAIRED_SCORE_v1.json"
A1R_CSV_REL = f"{A1R_DIR_REL}/ROOT_A1R_SCREEN12_PAIRED_SCENES_clean_v2.csv"

SCENE_ORDER = (
    "DL1018_DEV_T1_C01_W15", "DL1018_DEV_T1_C00_W03",
    "DL1018_DEV_T1_C15_W14", "DL1018_DEV_T1_C05_W06",
    "DL1018_DEV_T2_C00_W04", "DL1018_DEV_T2_C02_W15",
    "DL1018_VAL_T2_C15_W09", "DL1018_DEV_T2_C06_W07",
    "DL1018_DEV_T3_C00_W05", "DL1018_DEV_T3_C03_W15",
    "DL1018_DEV_T3_C15_W14", "DL1018_DEV_T3_C05_W02",
)
FIRST_SCENE = SCENE_ORDER[0]
PERIODS = ("all", "pre", "post")
METHODS = ("A1T", "A1R", "C5_RBF", "A1")
BASELINES = ("A1R", "C5_RBF", "A1")
METRICS = (
    "position_Q_m", "position_peak_m", "position_x_RMSE_m",
    "position_y_RMSE_m", "position_z_RMSE_m", "SO3_RMSE_deg",
    "SO3_peak_deg", "body_rate_RMSE_rads",
)
PAIRED_METRICS = ("SO3_RMSE_deg", "position_Q_m", "body_rate_RMSE_rads")

PINS = {
    "screen12_manifest": "fdca3f17c0f39d19eb5b08e94e7e5b1f148ec03cf861eacec64d86ab7922f923",
    "baseline_score": "6c6a1eb8d2b499d211a5f57379ac6d4a5f3cb7ae560d5bbad070b4bc8d649e27",
    "frozen_scorer": "3b345050b31cabdfcb08dab405d9e34b736e1f65c02bc9fd22d3a0f08c9aeb52",
    "a1r_score_json": "5f943414d7c48bb4c4ef399521320c27fbbb1b4989d846d87425318719dc40e7",
    "a1r_clean_scenes_csv": "c0fb53c49c2577434df86d5c13e04be6863f52249dd0014ddc627e330589ea35",
    "a1r_auditor": "8e99eedfa8c02229cb456e165d1dccf243a7357d4a276e7869620a6498715210",
    "a1t_taskbook": "060ae7dbd36df7000711c961967a694186239af3520bdd581cf7d04b7b3e75fd",
    "a1t_preparation": "970b5015d0cb0d251c2993ba8fdff2c57eda5e02bf27e35d7a29a5a80a234c04",
    "a1t_runner": "4af417293df84070869ae1a72288225f5c324629edf23e3a41dcbdfed7e9ade7",
    "a1t_deployment": "dd5375623cf47abed1db1e620a7d00358aff71b5985ead13e88ba05218952b42",
    "a1t_checkpoint": "58c72450fcc1e9aaa04f7454ad2a8aa551f161a95e52bb9946f0c99c23957cea",
    "a1t_normalizer": "12c864b9c2404235e0ea3f313bb0801a99902eca7cfdfbf43f0d8d584d5d609a",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def repo_path(root: Path, value: str | Path) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = root / candidate
    result = candidate.resolve()
    if not result.is_relative_to(root.resolve()):
        raise ValueError(f"path escapes repository: {value}")
    return result


def same_repo_path(root: Path, left: str | Path, right: str | Path) -> bool:
    return repo_path(root, left) == repo_path(root, right)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def finite_float(value: Any, field: str) -> float:
    result = float(value)
    require(math.isfinite(result), f"non-finite value in {field}")
    return result


def load_frozen_inputs(root: Path) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, str]], dict[str, dict[str, Any]]]:
    paths = {
        "manifest": repo_path(root, MANIFEST_REL),
        "baseline": repo_path(root, BASELINE_REL),
        "scorer": repo_path(root, SCORER_REL),
        "a1r_json": repo_path(root, A1R_JSON_REL),
        "a1r_csv": repo_path(root, A1R_CSV_REL),
    }
    pin_by_input = {
        "manifest": PINS["screen12_manifest"], "baseline": PINS["baseline_score"],
        "scorer": PINS["frozen_scorer"], "a1r_json": PINS["a1r_score_json"],
        "a1r_csv": PINS["a1r_clean_scenes_csv"],
    }
    for key, path in paths.items():
        require(path.is_file(), f"missing frozen input {key}: {path}")
        require(sha256(path).lower() == pin_by_input[key],
                f"frozen input SHA mismatch: {key}")

    manifest = read_json(paths["manifest"])
    baseline = read_json(paths["baseline"])
    a1r_score = read_json(paths["a1r_json"])
    require(manifest.get("schema") == "CM18_A1_FUTURE_DEVELOPMENT_SCREEN12_V1"
            and manifest.get("first_engineering_scene") == FIRST_SCENE
            and len(manifest.get("scenes", [])) == 12,
            "SCREEN12 manifest schema/order/count mismatch")
    scene_rows = manifest["scenes"]
    require({str(row["scene_id"]) for row in scene_rows} == set(SCENE_ORDER),
            "SCREEN12 scene set differs from fixed A1T order")
    require(baseline.get("schema") == "ROOT_CM18_SCREEN12_PAIRED_SCORE_V1"
            and baseline.get("manifest_sha256", "").lower() == PINS["screen12_manifest"]
            and baseline.get("completed") == 12 and baseline.get("missing") == [],
            "frozen C5/A1 score is not a complete SCREEN12 result")
    require(a1r_score.get("schema") == "ROOT_A1R_SCREEN12_PAIRED_SCORE_V1"
            and a1r_score.get("scene_count") == 12
            and a1r_score.get("a1r_independent_audit_pass_count") == 12
            and a1r_score.get("prior_c5_a1_score_sha256", "").lower() == PINS["baseline_score"]
            and a1r_score.get("frozen_scorer_sha256", "").lower() == PINS["frozen_scorer"],
            "frozen A1R score JSON identity/count mismatch")

    with paths["a1r_csv"].open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames is not None and len(reader.fieldnames) == len(set(reader.fieldnames)),
                "A1R clean_v2 CSV has duplicate column names")
        a1r_rows = list(reader)
        require(len(a1r_rows) == 12, "A1R clean_v2 CSV does not have twelve scene rows")

    a1r_by_scene = {row["scene_id"]: row for row in a1r_rows}
    baseline_by_scene = {row["scene_id"]: row for row in baseline["rows"]}
    a1r_json_by_scene = {row["scene_id"]: row for row in a1r_score["per_scene"]}
    require(len(a1r_by_scene) == len(baseline_by_scene) == len(a1r_json_by_scene) == 12
            and set(a1r_by_scene) == set(baseline_by_scene) == set(a1r_json_by_scene) == set(SCENE_ORDER),
            "paired result inputs do not contain the exact twelve scene IDs")

    manifest_by_scene = {row["scene_id"]: row for row in scene_rows}
    for scene_id, clean in a1r_by_scene.items():
        prior = baseline_by_scene[scene_id]
        identity = a1r_json_by_scene[scene_id]
        manifest_row = manifest_by_scene[scene_id]
        require(clean["task"] == manifest_row["task"] and clean["category"] == manifest_row["category"],
                f"{scene_id}: A1R clean_v2 task/category mismatch")
        require(clean["A1R_audit_status"] == "PASS"
                and clean["A1R_audit_source_sha256"].lower() == PINS["a1r_auditor"]
                and clean["A1R_raw_sha256"].lower() == identity["a1r_raw_sha256"].lower()
                and clean["A1R_audit_sha256"].lower() == identity["a1r_audit_sha256"].lower()
                and identity["a1r_audit_status"] == "PASS",
                f"{scene_id}: A1R JSON/clean_v2 identity mismatch")
        require(clean["C5_RBF_raw_sha256"].lower() == manifest_row["baseline_C5_raw_sha256"].lower()
                == prior["C5_RBF"]["raw_sha256"].lower()
                and clean["A1_raw_sha256"].lower() == prior["CM18_A1"]["raw_sha256"].lower(),
                f"{scene_id}: C5/A1 raw identity differs from the frozen paired baseline")
        require(int(clean["A1R_cm18_events"]) == 1999,
                f"{scene_id}: clean_v2 A1R row does not contain 1,999 events")
        for method, prior_key in (("C5_RBF", "C5_RBF"), ("A1", "CM18_A1")):
            validate_clean_against_baseline(clean, method, prior[prior_key], scene_id)
    return manifest, baseline, a1r_rows, a1r_by_scene


def validate_clean_against_baseline(clean: dict[str, str], method: str,
                                    prior: dict[str, Any], scene_id: str) -> None:
    for period in PERIODS:
        expected = prior["metrics"][period]
        for name, csv_suffix in (("position_Q_m", "position_Q_m"), ("position_peak_m", "position_peak_m"),
                                 ("SO3_RMSE_deg", "SO3_RMSE_deg"), ("SO3_peak_deg", "SO3_peak_deg"),
                                 ("body_rate_RMSE_rads", "body_rate_RMSE_rads")):
            value = finite_float(clean[f"{method}_{period}_{csv_suffix}"], f"{scene_id}/{method}/{period}/{name}")
            require(abs(value - float(expected[name])) <= 1e-14,
                    f"{scene_id}: {method}/{period}/{name} differs from frozen baseline")
        axes = [finite_float(clean[f"{method}_{period}_position_{axis}_RMSE_m"],
                             f"{scene_id}/{method}/{period}/position_{axis}") for axis in "xyz"]
        require(len(axes) == 3 and max(abs(a - float(b)) for a, b in zip(
                    axes, expected["position_axis_RMSE_m"], strict=True)) <= 1e-14,
                f"{scene_id}: {method}/{period} axis metrics differ from frozen baseline")
        require(int(clean[f"{method}_{period}_n"]) == int(expected["n"]),
                f"{scene_id}: {method}/{period} sample count differs from frozen baseline")


def audit_gate(root: Path, manifest_rows: list[dict[str, Any]],
               a1r_by_scene: dict[str, dict[str, str]]) -> tuple[list[dict[str, Any]], list[dict[str, str]], str | None]:
    qualified: list[dict[str, Any]] = []
    incomplete: list[dict[str, str]] = []
    source_hashes: set[str] = set()
    auditor_path = repo_path(root, AUDITOR_REL)
    current_auditor_sha = sha256(auditor_path).lower() if auditor_path.is_file() else ""
    review_path = repo_path(root, AUDITOR_REVIEW_REL)
    if not review_path.is_file():
        incomplete.append({"scene_id": "ALL", "state": "MISSING", "artifacts": "ROOT_A1T_RAW_AUDITOR_REVIEW_v2.json"})
    else:
        review = read_json(review_path)
        review_source = str(review.get("source", "")).replace("\\", "/")
        if (review.get("schema") != "ROOT_A1T_RAW_AUDITOR_REVIEW_V2"
                or review.get("status") != "PASS" or review_source != AUDITOR_REL
                or str(review.get("sha256", "")).lower() != current_auditor_sha
                or review.get("Plant_calls") != 0
                or review.get("supersedes")
                != f"{REPORT_REL}/ROOT_A1T_RAW_AUDITOR_REVIEW_v1.json"):
            incomplete.append({"scene_id": "ALL", "state": "REJECTED",
                               "reasons": "ROOT_signed_auditor_source_review_mismatch"})
    sequence = {scene: index + 1 for index, scene in enumerate(SCENE_ORDER)}

    for row in manifest_rows:
        scene = str(row["scene_id"])
        attempt = repo_path(root, f"{RUN_REL}/{scene}/attempt_01")
        raw_path, start_path = attempt / "raw_run.mat", attempt / "run_start.mat"
        status_path, marker_path = attempt / "run_status.json", attempt / "first_plant_step.marker"
        audit_path = repo_path(root, f"{REPORT_REL}/A1T_SCREEN12_LOG_AUDIT_{scene}_v1.json")
        release_path = repo_path(root, f"{REPORT_REL}/ROOT_A1T_SCREEN12_CONTROL_RELEASE_{scene}_v1.json")
        required = (raw_path, start_path, status_path, marker_path, audit_path, release_path)
        absent = [p.name for p in required if not p.is_file()]
        if absent:
            incomplete.append({"scene_id": scene, "state": "MISSING", "artifacts": ",".join(absent)})
            continue
        audit, status, release = read_json(audit_path), read_json(status_path), read_json(release_path)
        reasons: list[str] = []
        source_sha = str(audit.get("audit_source_sha256", "")).lower()
        source_hashes.add(source_sha)
        if audit.get("schema") != "A1T_SCREEN12_INDEPENDENT_LOG_AUDIT_V1" or audit.get("status") != "PASS":
            reasons.append("independent_audit_not_PASS")
        if audit.get("scene_id") != scene or status.get("scene_id") != scene:
            reasons.append("scene_identity_mismatch")
        if (audit.get("audit_source_path", "").replace("\\", "/") != AUDITOR_REL
                or len(source_sha) != 64 or any(ch not in "0123456789abcdef" for ch in source_sha)
                or source_sha != current_auditor_sha):
            reasons.append("audit_source_identity_mismatch")
        if audit.get("deployment_parameters_sha256", "").lower() != PINS["a1t_deployment"]:
            reasons.append("deployment_sha_mismatch")
        if audit.get("checkpoint_sha256", "").lower() != PINS["a1t_checkpoint"]:
            reasons.append("checkpoint_sha_mismatch")
        if audit.get("selected_step") != 40000:
            reasons.append("selected_step_mismatch")
        if audit.get("canonical_normalizer_float64_sha256", "").lower() != PINS["a1t_normalizer"]:
            reasons.append("normalizer_sha_mismatch")
        if audit.get("engine_sha256", "").lower() != "4f72db75f176e76de03f77b45e0b82f05ff0e3206907714f3c7faf786ba1092a":
            reasons.append("engine_sha_mismatch")
        if (not same_repo_path(root, audit.get("raw_path", ""), raw_path)
                or audit.get("raw_sha256", "").lower() != status.get("raw_sha256", "").lower()
                or audit.get("counts", {}).get("cm18_events") != 1999):
            reasons.append("audit_raw_identity_or_event_count_mismatch")
        if (status.get("schema") != "A1T_SCREEN12_CONTROL_RUN_STATUS_V1"
                or status.get("status") != "RUN_COMPLETE_PENDING_ROOT_AUDIT"
                or status.get("log_status") != "STABLE" or status.get("safety_stop_reason") != ""
                or status.get("transitions") != 20000 or status.get("state_samples") != 20001
                or status.get("cm18_events") != 1999 or status.get("first_plant_step_confirmed") is not True
                or status.get("engine_invocation_entered") is not True or status.get("plant_calls") != 1
                or status.get("training_steps") != 0 or status.get("optimizer_steps") != 0
                or status.get("TEST_accessed") is not False
                or status.get("sequence_index") != sequence[scene]):
            reasons.append("runner_status_scope_or_sequence_mismatch")
        if not same_repo_path(root, status.get("raw_path", ""), raw_path):
            reasons.append("status_raw_path_mismatch")
        start_sha = sha256(start_path).lower()
        release_sha = sha256(release_path).lower()
        if (status.get("run_start_sha256", "").lower() != start_sha
                or audit.get("run_start_sha256", "").lower() != start_sha):
            reasons.append("run_start_sha_mismatch")
        if (status.get("root_release_sha256", "").lower() != release_sha
                or audit.get("release_sha256", "").lower() != release_sha):
            reasons.append("release_sha_mismatch")
        if (release.get("schema") != "A1T_SCREEN12_CONTROL_ROOT_RELEASE_V1"
                or release.get("decision") != "APPROVE_ONE_A1T_SCREEN12_FLIGHT"
                or release.get("plant_authorized") is not True
                or release.get("scene_id") != scene
                or release.get("sequence_index") != sequence[scene]
                or release.get("training_authorized") is not False
                or release.get("optimizer_steps_authorized") != 0
                or release.get("TEST_accessed") is not False
                or release.get("taskbook_sha256", "").lower() != PINS["a1t_taskbook"]
                or release.get("preparation_result_sha256", "").lower() != PINS["a1t_preparation"]
                or release.get("deployment_parameters_sha256", "").lower() != PINS["a1t_deployment"]
                or release.get("checkpoint_sha256", "").lower() != PINS["a1t_checkpoint"]
                or release.get("selected_step") != 40000
                or release.get("canonical_normalizer_float64_sha256", "").lower() != PINS["a1t_normalizer"]
                or release.get("screen12_manifest_sha256", "").lower() != PINS["screen12_manifest"]
                or release.get("runner_sha256", "").lower() != PINS["a1t_runner"]
                or release.get("baseline_C5_raw_sha256", "").lower()
                != str(row.get("baseline_C5_raw_sha256", "")).lower()
                or release.get("same_scene_a1r_raw_sha256", "").lower()
                != a1r_by_scene[scene]["A1R_raw_sha256"].lower()
                or release.get("same_scene_a1r_audit_sha256", "").lower()
                != a1r_by_scene[scene]["A1R_audit_sha256"].lower()):
            reasons.append("root_release_identity_or_scope_mismatch")
        if reasons:
            incomplete.append({"scene_id": scene, "state": "REJECTED", "reasons": ";".join(reasons)})
            continue
        qualified.append({
            "scene_id": scene, "attempt": "attempt_01", "raw_path": raw_path,
            "raw_sha256_reported": str(audit["raw_sha256"]).lower(),
            "run_start_sha256": start_sha, "audit_path": audit_path,
            "audit_sha256": sha256(audit_path).lower(), "audit_source_sha256": source_sha,
            "release_path": release_path, "release_sha256": release_sha,
        })
    if len(source_hashes) > 1:
        incomplete.append({"scene_id": "ALL", "state": "REJECTED", "reasons": "auditor_source_SHA_differs_across_scenes"})
    return qualified, incomplete, next(iter(source_hashes)) if len(source_hashes) == 1 else None


def clean_method_score(row: dict[str, str], method: str) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for period in PERIODS:
        metrics[period] = {
            "n": int(row[f"{method}_{period}_n"]),
            "position_Q_m": finite_float(row[f"{method}_{period}_position_Q_m"], f"{method}/{period}/Q"),
            "position_axis_RMSE_m": [finite_float(row[f"{method}_{period}_position_{axis}_RMSE_m"],
                                                        f"{method}/{period}/{axis}") for axis in "xyz"],
            "position_peak_m": finite_float(row[f"{method}_{period}_position_peak_m"], f"{method}/{period}/peak position"),
            "SO3_RMSE_deg": finite_float(row[f"{method}_{period}_SO3_RMSE_deg"], f"{method}/{period}/SO3"),
            "SO3_peak_deg": finite_float(row[f"{method}_{period}_SO3_peak_deg"], f"{method}/{period}/SO3 peak"),
            "body_rate_RMSE_rads": finite_float(row[f"{method}_{period}_body_rate_RMSE_rads"], f"{method}/{period}/body rate"),
        }
    event_cell = row.get(f"{method}_cm18_events", "")
    return {
        "raw_sha256": row[f"{method}_raw_sha256"], "metrics": metrics,
        "motor_saturated_transitions": int(row[f"{method}_motor_saturated_transitions"]),
        "cm18_events": int(event_cell) if event_cell else None,
    }


def checked_scorer(root: Path):
    path = repo_path(root, SCORER_REL)
    require(sha256(path).lower() == PINS["frozen_scorer"], "frozen score(path) source SHA mismatch")
    spec = importlib.util.spec_from_file_location("root_screen12_metrics_v1_a1t_paired", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load frozen scorer: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    require(callable(getattr(module, "score", None)), "frozen scorer has no score(path)")
    return module


def validate_a1t_scored(score: dict[str, Any], identity: dict[str, Any], scene: str) -> None:
    require(score.get("raw_sha256", "").lower() == identity["raw_sha256"],
            f"{scene}: scorer raw SHA differs from PASS audit")
    metrics = score["metrics"]
    require(metrics.get("cm18_events") == 1999, f"{scene}: scorer did not see 1,999 CM18 events")
    for period, samples in (("all", 20000), ("pre", 5000), ("post", 15000)):
        require(metrics[period]["n"] == samples, f"{scene}: unexpected {period} sample count")
        for key in ("position_Q_m", "position_peak_m", "SO3_RMSE_deg", "SO3_peak_deg", "body_rate_RMSE_rads"):
            finite_float(metrics[period][key], f"{scene}/A1T/{period}/{key}")
        axes = metrics[period]["position_axis_RMSE_m"]
        require(len(axes) == 3 and all(math.isfinite(float(value)) for value in axes),
                f"{scene}: non-finite or malformed position-axis score")


def scene_fields() -> list[str]:
    fields = ["scene_id", "task", "category", "A1T_audit_status", "A1T_audit_sha256",
              "A1T_audit_source_sha256", "A1T_run_start_sha256",
              "A1T_root_release_sha256"]
    for method in METHODS:
        fields.extend((f"{method}_motor_saturated_transitions", f"{method}_cm18_events", f"{method}_raw_sha256"))
        for period in PERIODS:
            fields.extend(f"{method}_{period}_{metric}" for metric in (
                "n", "position_Q_m", "position_peak_m", "position_x_RMSE_m", "position_y_RMSE_m",
                "position_z_RMSE_m", "SO3_RMSE_deg", "SO3_peak_deg", "body_rate_RMSE_rads"))
    for baseline in BASELINES:
        for period in PERIODS:
            fields.extend(f"delta_A1T_minus_{baseline}_{period}_{metric}" for metric in METRICS)
    require(len(fields) == len(set(fields)), "internal scene CSV columns are not unique")
    return fields


def group_fields() -> list[str]:
    fields = ["group_name", "group_kind", "scene_count", "period", "samples_per_scene"]
    for method in METHODS:
        fields.extend(f"mean_{method}_{metric}" for metric in METRICS)
    for baseline in BASELINES:
        for metric in PAIRED_METRICS:
            stem = "SO3" if metric == "SO3_RMSE_deg" else "position_Q" if metric == "position_Q_m" else "body_rate"
            fields.extend(f"A1T_{stem}_{outcome}_vs_{baseline}" for outcome in ("wins", "ties", "losses"))
    require(len(fields) == len(set(fields)), "internal group CSV columns are not unique")
    return fields


def scene_table_bytes(rows: list[dict[str, Any]]) -> bytes:
    buffer = io.StringIO(newline="")
    fields = scene_fields()
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n", extrasaction="raise")
    writer.writeheader()
    for row in rows:
        out: dict[str, Any] = {
            "scene_id": row["scene_id"], "task": row["task"], "category": row["category"],
            "A1T_audit_status": "PASS", "A1T_audit_sha256": row["audit"]["audit_sha256"],
            "A1T_audit_source_sha256": row["audit"]["audit_source_sha256"],
            "A1T_raw_sha256": row["scores"]["A1T"]["raw_sha256"],
            "A1T_run_start_sha256": row["audit"]["run_start_sha256"],
            "A1T_root_release_sha256": row["audit"]["release_sha256"],
        }
        for method in METHODS:
            scored = row["scores"][method]
            out[f"{method}_motor_saturated_transitions"] = scored["motor_saturated_transitions"]
            out[f"{method}_cm18_events"] = "" if scored["cm18_events"] is None else scored["cm18_events"]
            out[f"{method}_raw_sha256"] = scored["raw_sha256"]
            for period in PERIODS:
                metric = scored["metrics"][period]
                values = {
                    "n": metric["n"], "position_Q_m": metric["position_Q_m"],
                    "position_peak_m": metric["position_peak_m"],
                    "position_x_RMSE_m": metric["position_axis_RMSE_m"][0],
                    "position_y_RMSE_m": metric["position_axis_RMSE_m"][1],
                    "position_z_RMSE_m": metric["position_axis_RMSE_m"][2],
                    "SO3_RMSE_deg": metric["SO3_RMSE_deg"], "SO3_peak_deg": metric["SO3_peak_deg"],
                    "body_rate_RMSE_rads": metric["body_rate_RMSE_rads"],
                }
                for name, value in values.items():
                    out[f"{method}_{period}_{name}"] = value
        for baseline in BASELINES:
            for period in PERIODS:
                for metric in METRICS:
                    out[f"delta_A1T_minus_{baseline}_{period}_{metric}"] = (
                        flat_metric(row["scores"]["A1T"]["metrics"][period], metric)
                        - flat_metric(row["scores"][baseline]["metrics"][period], metric))
        require(set(out) == set(fields), f"{row['scene_id']}: scene CSV field mismatch")
        writer.writerow(out)
    return buffer.getvalue().encode("utf-8")


def flat_metric(metrics: dict[str, Any], name: str) -> float:
    if name == "position_x_RMSE_m":
        return float(metrics["position_axis_RMSE_m"][0])
    if name == "position_y_RMSE_m":
        return float(metrics["position_axis_RMSE_m"][1])
    if name == "position_z_RMSE_m":
        return float(metrics["position_axis_RMSE_m"][2])
    return float(metrics[name])


def grouped_scenes(rows: list[dict[str, Any]]) -> list[tuple[str, str, list[dict[str, Any]]]]:
    groups: list[tuple[str, str, list[dict[str, Any]]]] = [("ALL12", "all", rows)]
    for task in ("T1", "T2", "T3"):
        groups.append((task, "task", [row for row in rows if row["task"] == task]))
    hf = [row for row in rows if row["category"] == "ALL_ARMS"]
    no_wind = [row for row in rows if row["category"] == "ACTIVE_NO_WIND"]
    require(len(hf) == len(no_wind) == 3
            and all(row["scene_id"].endswith(("W09", "W14")) for row in hf)
            and all(row["scene_id"].endswith("W15") for row in no_wind),
            "SCREEN12 HF/no-wind scene membership differs from the frozen design")
    groups.extend((("HF_W09_W14", "condition", hf), ("NO_WIND_W15", "condition", no_wind)))
    return groups


def group_table_bytes(rows: list[dict[str, Any]]) -> bytes:
    buffer = io.StringIO(newline="")
    fields = group_fields()
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n", extrasaction="raise")
    writer.writeheader()
    for group_name, group_kind, members in grouped_scenes(rows):
        for period in PERIODS:
            sample_counts = {int(row["scores"]["A1T"]["metrics"][period]["n"]) for row in members}
            require(len(sample_counts) == 1, f"{group_name}/{period}: inconsistent period sample counts")
            out: dict[str, Any] = {"group_name": group_name, "group_kind": group_kind,
                                   "scene_count": len(members), "period": period,
                                   "samples_per_scene": next(iter(sample_counts))}
            for method in METHODS:
                for metric in METRICS:
                    out[f"mean_{method}_{metric}"] = sum(
                        flat_metric(row["scores"][method]["metrics"][period], metric) for row in members
                    ) / len(members)
            for baseline in BASELINES:
                for metric in PAIRED_METRICS:
                    stem = "SO3" if metric == "SO3_RMSE_deg" else "position_Q" if metric == "position_Q_m" else "body_rate"
                    wins = ties = losses = 0
                    for row in members:
                        a = float(row["scores"]["A1T"]["metrics"][period][metric])
                        b = float(row["scores"][baseline]["metrics"][period][metric])
                        if a < b - 1e-12:
                            wins += 1
                        elif b < a - 1e-12:
                            losses += 1
                        else:
                            ties += 1
                    out[f"A1T_{stem}_wins_vs_{baseline}"] = wins
                    out[f"A1T_{stem}_ties_vs_{baseline}"] = ties
                    out[f"A1T_{stem}_losses_vs_{baseline}"] = losses
            require(set(out) == set(fields), f"{group_name}/{period}: group CSV field mismatch")
            writer.writerow(out)
    return buffer.getvalue().encode("utf-8")


def output_result(root: Path, rows: list[dict[str, Any]], audit_source_sha: str,
                  manifest_path: Path, baseline_path: Path, scorer_path: Path,
                  a1r_json_path: Path, a1r_csv_path: Path) -> dict[str, Any]:
    report_dir = repo_path(root, REPORT_REL)
    scenes_path = report_dir / "ROOT_A1T_SCREEN12_PAIRED_SCENES_v1.csv"
    groups_path = report_dir / "ROOT_A1T_SCREEN12_PAIRED_GROUPS_v1.csv"
    score_path = report_dir / "ROOT_A1T_SCREEN12_PAIRED_SCORE_v1.json"
    if any(path.exists() for path in (scenes_path, groups_path, score_path)):
        raise FileExistsError("refusing to overwrite an A1T paired score artifact")
    scene_data, group_data = scene_table_bytes(rows), group_table_bytes(rows)
    aggregates = {}
    for name, _, members in grouped_scenes(rows):
        aggregates[name] = {
            "scene_count": len(members),
            "means_by_period": {
                period: {
                    method: {metric: sum(flat_metric(r["scores"][method]["metrics"][period], metric)
                                         for r in members) / len(members) for metric in METRICS}
                    for method in METHODS
                } for period in PERIODS
            },
            "A1T_paired_outcomes_by_period": {
                period: {
                    baseline: {
                        metric: outcome_counts(members, baseline, period, metric)
                        for metric in PAIRED_METRICS
                    } for baseline in BASELINES
                } for period in PERIODS
            },
        }
    report = {
        "schema": "ROOT_A1T_SCREEN12_PAIRED_SCORE_V1",
        "status": "COMPLETE_PENDING_ROOT_REVIEW",
        "scene_count": 12,
        "a1t_independent_audit_pass_count": 12,
        "score_scope": "Same-scene A1T/A1R/C5_RBF/original A1; all 20,000 left-aligned transition samples, terminal t=20 s excluded; PRE=[0,5), POST=[5,20). No outcome filtering.",
        "macro_scope": "Equal-scene arithmetic mean of each scene's metric; group membership is fixed by the SCREEN12 task/category/arm-wind labels. This is a mechanism screen, not independent paper validation.",
        "audit_source_sha256": audit_source_sha,
        "source_pins": {
            "root_auditor_source_review": {"path": AUDITOR_REVIEW_REL,
                                            "sha256": sha256(repo_path(root, AUDITOR_REVIEW_REL))},
            "screen12_manifest": {"path": MANIFEST_REL, "sha256": sha256(manifest_path)},
            "frozen_score_function": {"path": SCORER_REL, "sha256": sha256(scorer_path)},
            "original_c5_a1_paired_score": {"path": BASELINE_REL, "sha256": sha256(baseline_path)},
            "a1r_paired_score_json": {"path": A1R_JSON_REL, "sha256": sha256(a1r_json_path)},
            "a1r_clean_v2_scenes_csv": {"path": A1R_CSV_REL, "sha256": sha256(a1r_csv_path)},
        },
        "group_membership": {name: [row["scene_id"] for row in members]
                              for name, _, members in grouped_scenes(rows)},
        "aggregates": aggregates,
        "a1t_scene_audits": [
            {"scene_id": row["scene_id"], "raw_sha256": row["scores"]["A1T"]["raw_sha256"],
             "audit_sha256": row["audit"]["audit_sha256"],
             "run_start_sha256": row["audit"]["run_start_sha256"],
             "root_release_sha256": row["audit"]["release_sha256"], "audit_status": "PASS"}
            for row in rows
        ],
        "tables": {
            "scenes": {"path": str(scenes_path.relative_to(root)),
                       "sha256": hashlib.sha256(scene_data).hexdigest(), "bytes": len(scene_data), "rows": 12},
            "groups": {"path": str(groups_path.relative_to(root)),
                       "sha256": hashlib.sha256(group_data).hexdigest(), "bytes": len(group_data),
                       "rows": len(grouped_scenes(rows)) * len(PERIODS)},
        },
    }
    report_data = (json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    write_new(scenes_path, scene_data)
    write_new(groups_path, group_data)
    write_new(score_path, report_data)
    return report


def outcome_counts(rows: list[dict[str, Any]], baseline: str, period: str, metric: str) -> dict[str, int]:
    wins = ties = losses = 0
    for row in rows:
        a = float(row["scores"]["A1T"]["metrics"][period][metric])
        b = float(row["scores"][baseline]["metrics"][period][metric])
        if a < b - 1e-12:
            wins += 1
        elif b < a - 1e-12:
            losses += 1
        else:
            ties += 1
    return {"wins": wins, "ties": ties, "losses": losses}


def write_new(path: Path, data: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(data)


def main() -> int:
    root = Path(__file__).resolve().parents[3]
    manifest, baseline, _, a1r_by_scene = load_frozen_inputs(root)
    manifest_rows = manifest["scenes"]
    qualified, incomplete, audit_source_sha = audit_gate(root, manifest_rows, a1r_by_scene)
    if incomplete or len(qualified) != 12:
        print(json.dumps({"status": "INCOMPLETE", "a1t_audit_pass": len(qualified),
                          "expected": 12, "scenes": incomplete, "final_tables_written": False},
                         ensure_ascii=False, indent=2))
        return 2

    # Only after all twelve independent audits pass do we hash the A1T raw logs.
    for identity in qualified:
        actual = sha256(identity["raw_path"]).lower()
        if actual != identity["raw_sha256_reported"]:
            incomplete.append({"scene_id": identity["scene_id"], "state": "REJECTED",
                               "reasons": "raw_sha256_differs_from_PASS_audit"})
        identity["raw_sha256"] = actual
    if incomplete:
        print(json.dumps({"status": "INCOMPLETE", "a1t_audit_pass": 12,
                          "expected": 12, "scenes": incomplete, "final_tables_written": False},
                         ensure_ascii=False, indent=2))
        return 2

    report_dir = repo_path(root, REPORT_REL)
    out_paths = (report_dir / "ROOT_A1T_SCREEN12_PAIRED_SCENES_v1.csv",
                 report_dir / "ROOT_A1T_SCREEN12_PAIRED_GROUPS_v1.csv",
                 report_dir / "ROOT_A1T_SCREEN12_PAIRED_SCORE_v1.json")
    if any(path.exists() for path in out_paths):
        raise FileExistsError("refusing to overwrite an A1T paired score artifact")

    scorer = checked_scorer(root)
    qualified_by_scene = {row["scene_id"]: row for row in qualified}
    baseline_by_scene = {row["scene_id"]: row for row in baseline["rows"]}
    scored_rows: list[dict[str, Any]] = []
    for source in manifest_rows:
        scene = str(source["scene_id"])
        identity = qualified_by_scene[scene]
        a1t = scorer.score(identity["raw_path"])
        validate_a1t_scored(a1t, identity, scene)
        a1t["motor_saturated_transitions"] = a1t["metrics"]["motor_saturated_transitions"]
        a1t["cm18_events"] = a1t["metrics"].get("cm18_events")
        prior = baseline_by_scene[scene]
        a1r_clean = a1r_by_scene[scene]
        scores = {"A1T": a1t}
        for method in ("A1R", "C5_RBF", "A1"):
            scores[method] = clean_method_score(a1r_clean, method)
        require(scores["C5_RBF"]["raw_sha256"].lower() == source["baseline_C5_raw_sha256"].lower()
                and scores["A1"]["raw_sha256"].lower() == prior["CM18_A1"]["raw_sha256"].lower(),
                f"{scene}: paired raw identities changed after preflight")
        scored_rows.append({"scene_id": scene, "task": source["task"], "category": source["category"],
                            "audit": identity, "scores": scores})

    paths = {
        "manifest": repo_path(root, MANIFEST_REL), "baseline": repo_path(root, BASELINE_REL),
        "scorer": repo_path(root, SCORER_REL), "a1r_json": repo_path(root, A1R_JSON_REL),
        "a1r_csv": repo_path(root, A1R_CSV_REL),
    }
    result = output_result(root, scored_rows, str(audit_source_sha), paths["manifest"], paths["baseline"],
                           paths["scorer"], paths["a1r_json"], paths["a1r_csv"])
    print(json.dumps({"status": result["status"], "scene_count": 12,
                      "audit_source_sha256": audit_source_sha,
                      "scenes_csv": result["tables"]["scenes"],
                      "groups_csv": result["tables"]["groups"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
