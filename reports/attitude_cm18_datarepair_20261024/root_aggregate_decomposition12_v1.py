"""Aggregate the fixed A1T same-state decomposition SCREEN12 reports.

Reads only the frozen scene manifest and the twelve per-scene JSON reports.
It never opens raw MAT files, TEST data, or any live run output.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "reports/attitude_cm18_datarepair_20261024"
MANIFEST_REL = Path("reports/attitude_cm18_a1_20261024/CM18_A1_DEV_SCREEN12_v1.json")
MANIFEST_SHA256 = "fdca3f17c0f39d19eb5b08e94e7e5b1f148ec03cf861eacec64d86ab7922f923"
TASKBOOK_REL = Path(
    "reports/attitude_cm18_datarepair_20261024/a1t_screen12_control_v1/"
    "ROOT_A1T_SAME_STATE_ERROR_DECOMPOSITION_TASKBOOK_v2_ZH.md"
)
TASKBOOK_SHA256 = "0cfa431009729806a55b9f0a692c258e5b2d12380f57dba1b7c3eb6c23dace5f"
FIRST_SCENE = "DL1018_DEV_T1_C01_W15"
FIRST_REPORT_SHA256 = "03da4c2b2311da8db9274066945436fe395fba365bdc847944c3aea5e7f0248f"
REPORT_ROOTS = (
    BASE / "a1t_same_state_decomposition_v1",
    BASE / "a1t_same_state_decomposition_v2",
)
REPORT_RE = re.compile(r"^A1T_SAME_STATE_DECOMPOSITION_(.+)_v([0-9]+)\.json$")
FIRST_DECOMP_RELEASE_REL = Path(
    "reports/attitude_cm18_datarepair_20261024/a1t_screen12_control_v1/"
    "ROOT_DECOMPOSITION_FIRST_EXECUTION_RELEASE_v4.json"
)
REMAINING_DECOMP_RELEASE_REL = Path(
    "reports/attitude_cm18_datarepair_20261024/a1t_screen12_control_v1/"
    "ROOT_DECOMPOSITION_REMAINING11_RELEASE_v1.json"
)
OUT_DIR = BASE / "root_aggregate_decomposition12_v1"
OUT_JSON = OUT_DIR / "A1T_SAME_STATE_DECOMPOSITION12_v1.json"
OUT_SCENE_CSV = OUT_DIR / "scene_windows.csv"
OUT_GROUP_CSV = OUT_DIR / "group_windows.csv"

WINDOWS = (
    ("ALL_0_20", lambda t: 0.0 <= t < 20.0, 1999, 17991),
    ("PRE_0_5", lambda t: 0.0 <= t < 5.0, 499, 4491),
    ("POST_5_20", lambda t: 5.0 <= t < 20.0, 1500, 13500),
)
AXES = ("roll", "pitch", "yaw")
EVENT_VECTOR_FIELDS = {
    "raw_output_rad_s2": "raw_output",
    "ideal_raw_target_Cstar_over_beta_rad_s2": "raw_target_Cstar_over_beta",
    "raw_output_minus_target_rad_s2": "raw_output_minus_target",
    "actual_action_rad_s2": "actual_action_rad_s2",
    "Cstar_rad_s2": "Cstar_rad_s2",
    "cproj_feasible_action_rad_s2": "cproj_feasible_action_rad_s2",
    "fit_applied_rad_s2": "fit_applied_rad_s2",
    "clip_increment_rad_s2": "clip_increment_rad_s2",
    "linear_fit_error_rad_s2": "linear_fit_error_rad_s2",
    "linear_clip_error_rad_s2": "linear_clip_error_rad_s2",
    "linear_actual_residual_rad_s2": "linear_actual_residual_rad_s2",
    "full_allocator_actual_error_rad_s2": "full_allocator_actual_error_rad_s2",
    "full_allocator_minus_linear_residual_rad_s2": None,
    "full_allocator_cproj_error_rad_s2": "full_allocator_cproj_error_rad_s2",
}
FLAG_FIELDS = {
    "raw_output_clip_by_axis": (3, "raw_output_clip_by_axis"),
    "cstar_projection_clip_by_axis": (3, "cstar_projection_clip_by_axis"),
    "actual_allocator_clip_by_channel": (4, "actual_allocator_clip_by_channel"),
    "actual_motor_saturated_by_motor": (4, "actual_motor_saturated_by_motor"),
    "cproj_allocator_clip_by_channel": (4, "cproj_allocator_clip_by_channel"),
    "cproj_motor_saturated_by_motor": (4, "cproj_motor_saturated_by_motor"),
    "base_allocator_clip_by_channel": (4, "base_allocator_clip_by_channel"),
    "base_motor_saturated_by_motor": (4, "base_motor_saturated_by_motor"),
}
HOLD_METRICS = (
    "action_fresh_minus_held_rad_s2",
    "full_allocator_acceleration_fresh_minus_held_rad_s2",
    "linear_G_fresh_minus_held_rad_s2",
    "allocator_minus_linear_delta_rad_s2",
    "linear_held_minus_fresh_residual_rad_s2",
)
COMMON_IDENTITY_FIELDS = (
    "audit_source_sha256",
    "deployment_sha256",
    "checkpoint_sha256",
    "selected_step",
    "canonical_normalizer_sha256",
    "taskbook_sha256",
    "preparation_sha256",
    "screen12_manifest_sha256",
    "engine_sha256",
    "runner_sha256",
    "forward_sha256",
    "physics_source_sha256",
    "physics_result_sha256",
    "active_c5_source_inventory_sha256",
)
EXPECTED_COMMON_IDENTITY = {
    "audit_source_sha256": "14de8af50058ebfb39b1d7ca484561b50adf5086bdfacd0dc3a541fd6871f6be",
    "deployment_sha256": "dd5375623cf47abed1db1e620a7d00358aff71b5985ead13e88ba05218952b42",
    "checkpoint_sha256": "58c72450fcc1e9aaa04f7454ad2a8aa551f161a95e52bb9946f0c99c23957cea",
    "selected_step": 40000,
    "canonical_normalizer_sha256": "12c864b9c2404235e0ea3f313bb0801a99902eca7cfdfbf43f0d8d584d5d609a",
    "taskbook_sha256": TASKBOOK_SHA256,
    "screen12_manifest_sha256": MANIFEST_SHA256,
    "preparation_sha256": "970b5015d0cb0d251c2993ba8fdff2c57eda5e02bf27e35d7a29a5a80a234c04",
    "engine_sha256": "4f72db75f176e76de03f77b45e0b82f05ff0e3206907714f3c7faf786ba1092a",
    "runner_sha256": "4af417293df84070869ae1a72288225f5c324629edf23e3a41dcbdfed7e9ade7",
    "forward_sha256": "1ff450f9be6a5c16fe98cb4f169ef9930f1b806fecfc10ad664c11ce940f42e9",
    "physics_source_sha256": "fe48f2d9d812cfa92364bd859490858a0e3eec01b3e6e80c773c829f9975042c",
    "physics_result_sha256": "bdb0ba18cd9d81aa176157c58f665c6ca2a0eb8946e75c3f652ea18ccffabee3",
    "active_c5_source_inventory_sha256": "6790dc2e5d3bdc5afece8f2577e9e3fa9694bda94a26433f723f271f2850a804",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def read_json(path: Path) -> tuple[dict, str]:
    raw = path.read_bytes()
    return json.loads(raw.decode("utf-8-sig")), sha256_bytes(raw)


def repo_file(relative: str | Path, label: str) -> Path:
    normalized = str(relative).replace("\\", "/")
    candidate = Path(normalized)
    require(not candidate.is_absolute() and ".." not in candidate.parts,
            f"{label}: expected repository-relative path")
    full = (ROOT / candidate).resolve()
    try:
        full.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"{label}: path escapes repository") from exc
    require(full.is_file(), f"{label}: missing file {normalized}")
    return full


def load_diagnostic_releases(scene_ids: list[str]) -> dict:
    first_path = ROOT / FIRST_DECOMP_RELEASE_REL
    rest_path = ROOT / REMAINING_DECOMP_RELEASE_REL
    first, first_sha = read_json(first_path)
    rest, rest_sha = read_json(rest_path)
    require(first.get("schema") == "ROOT_A1T_DECOMPOSITION_FIRST_EXECUTION_RELEASE_V4",
            "unexpected first-scene diagnostic release schema")
    require(first.get("decision") == "APPROVE_SINGLE_OFFLINE_ENGINEERING_RETRY"
            and first.get("scene_id") == FIRST_SCENE
            and first.get("plant_calls_authorized") == 0
            and first.get("training_steps_authorized") == 0
            and first.get("TEST_access_authorized") is False,
            "first-scene diagnostic release scope/scene mismatch")
    rest_ids = scene_ids[:]
    rest_ids.remove(FIRST_SCENE)
    require(rest.get("schema") == "ROOT_A1T_DECOMPOSITION_REMAINING11_RELEASE_V1",
            "unexpected remaining-scenes diagnostic release schema")
    require(rest.get("decision") == "APPROVE_OFFLINE_REMAINING11_AFTER_FIRST_PASS"
            and rest.get("scene_ids") == rest_ids
            and rest.get("plant_calls_authorized") == 0
            and rest.get("training_steps_authorized") == 0
            and rest.get("TEST_access_authorized") is False,
            "remaining-scenes diagnostic release scope/order mismatch")
    source_records = {}
    for name, release, release_path, release_sha in (
        ("first", first, first_path, first_sha),
        ("remaining11", rest, rest_path, rest_sha),
    ):
        source = repo_file(release["source_path"], f"{name} diagnostic source")
        source_sha = sha256_file(source)
        require(source_sha == release.get("source_sha256"),
                f"{name} diagnostic source SHA mismatch")
        source_records[name] = {
            "release_path": release_path.relative_to(ROOT).as_posix(),
            "release_sha256": release_sha,
            "source_path": release["source_path"].replace("\\", "/"),
            "source_sha256": source_sha,
        }
    return {"first": first, "remaining11": rest, "source_records": source_records}


def audit_scene_identity(identity: dict, scene_id: str) -> dict:
    audit_path = repo_file(identity.get("independent_audit_path", ""), f"{scene_id} audit")
    audit, audit_sha = read_json(audit_path)
    require(audit_sha == identity.get("independent_audit_sha256"),
            f"{scene_id}: independent audit file SHA mismatch")
    require(audit.get("schema") == "A1T_SCREEN12_INDEPENDENT_LOG_AUDIT_V1"
            and audit.get("status") == "PASS"
            and audit.get("scene_id") == scene_id,
            f"{scene_id}: independent audit is not a matching PASS")
    for audit_key, identity_key in (
        ("raw_sha256", "raw_sha256"),
        ("run_start_sha256", "run_start_sha256"),
        ("release_sha256", "root_release_sha256"),
        ("deployment_parameters_sha256", "deployment_sha256"),
        ("checkpoint_sha256", "checkpoint_sha256"),
        ("selected_step", "selected_step"),
        ("canonical_normalizer_float64_sha256", "canonical_normalizer_sha256"),
        ("engine_sha256", "engine_sha256"),
        ("audit_source_sha256", "audit_source_sha256"),
    ):
        require(audit.get(audit_key) == identity.get(identity_key),
                f"{scene_id}: audit/scene identity mismatch at {audit_key}")
    auditor_source = repo_file(audit.get("audit_source_path", ""), f"{scene_id} audit source")
    require(sha256_file(auditor_source) == audit.get("audit_source_sha256"),
            f"{scene_id}: actual audit source SHA mismatch")
    require(audit.get("raw_path", "").replace("\\", "/") == identity.get("raw_path", "").replace("\\", "/"),
            f"{scene_id}: audit raw path differs from report identity")
    counts = audit.get("counts", {})
    require(counts.get("transitions") == 20000 and counts.get("state_samples") == 20001
            and counts.get("cm18_events") == 1999
            and counts.get("event_first_last_matlab_index") == [11, 19991]
            and counts.get("event_stride_transitions") == 10
            and counts.get("event_pre_0_5") == 499
            and counts.get("event_post_5_20") == 1500,
            f"{scene_id}: audit event/time counts differ from fixed protocol")
    rbf = audit.get("rbf_off", {})
    require(all(rbf.get(key) is True for key in (
        "three_options_false", "three_runtime_log_flags_false", "fusion_and_head_false",
        "update_flags_zero", "raw_unclipped_held_outputs_zero",
        "attitude_rbf_compensation_torque_zero",
    )), f"{scene_id}: independent audit RBF-off checks failed")
    run_release_path = repo_file(audit.get("release_path", ""), f"{scene_id} run release")
    run_release, run_release_sha = read_json(run_release_path)
    require(run_release_sha == audit.get("release_sha256"),
            f"{scene_id}: run release SHA mismatch")
    require(run_release.get("schema") == "A1T_SCREEN12_CONTROL_ROOT_RELEASE_V1"
            and run_release.get("decision") == "APPROVE_ONE_A1T_SCREEN12_FLIGHT"
            and run_release.get("scene_id") == scene_id
            and run_release.get("deployment_parameters_sha256") == identity.get("deployment_sha256")
            and run_release.get("checkpoint_sha256") == identity.get("checkpoint_sha256")
            and run_release.get("selected_step") == identity.get("selected_step")
            and run_release.get("canonical_normalizer_float64_sha256") == identity.get("canonical_normalizer_sha256")
            and run_release.get("engine_sha256") == identity.get("engine_sha256")
            and run_release.get("forward_sha256") == identity.get("forward_sha256")
            and run_release.get("runner_sha256") == identity.get("runner_sha256")
            and run_release.get("plant_authorized") is True
            and run_release.get("training_authorized") is False
            and run_release.get("optimizer_steps_authorized") == 0
            and run_release.get("TEST_accessed") is False,
            f"{scene_id}: run release identity/scope mismatch")
    return {
        "audit_path": audit_path.relative_to(ROOT).as_posix(),
        "audit_sha256": audit_sha,
        "run_release_path": run_release_path.relative_to(ROOT).as_posix(),
        "run_release_sha256": run_release_sha,
    }


def finite_number(value, label: str) -> float:
    x = float(value)
    require(math.isfinite(x), f"{label}: non-finite number")
    return x


def vector(value, size: int, label: str) -> list[float]:
    require(isinstance(value, list) and len(value) == size, f"{label}: expected {size} values")
    return [finite_number(x, label) for x in value]


def close(actual: float, expected: float, label: str, tol: float = 1e-8) -> None:
    require(abs(actual - expected) <= tol, f"{label}: {actual:.17g} != {expected:.17g}")


def norm(values: list[float]) -> float:
    return math.sqrt(sum(x * x for x in values))


def matvec3(flat: list[float], v: list[float]) -> list[float]:
    return [sum(flat[3 * i + j] * v[j] for j in range(3)) for i in range(3)]


def scene_stats(rows: list[list[float]]) -> dict:
    require(rows, "cannot summarize an empty event window")
    n, dim = len(rows), len(rows[0])
    require(all(len(row) == dim for row in rows), "ragged vectors in metric")
    return {
        "count": n,
        "signed_mean": [sum(row[j] for row in rows) / n for j in range(dim)],
        "rms": [math.sqrt(sum(row[j] ** 2 for row in rows) / n) for j in range(dim)],
        "vector_rms": math.sqrt(sum(sum(x * x for x in row) for row in rows) / n),
        "max_abs_by_component": [max(abs(row[j]) for row in rows) for j in range(dim)],
    }


def scalar_stats(values: list[float]) -> dict:
    require(values, "cannot summarize an empty scalar window")
    return {
        "count": len(values),
        "mean": sum(values) / len(values),
        "min": min(values),
        "max": max(values),
    }


def manifest_rows() -> tuple[list[dict], str]:
    path = ROOT / MANIFEST_REL
    require(path.is_file(), f"missing frozen SCREEN12 manifest: {MANIFEST_REL}")
    actual_sha = sha256_file(path)
    require(actual_sha == MANIFEST_SHA256, f"SCREEN12 manifest SHA mismatch: {actual_sha}")
    manifest, _ = read_json(path)
    rows = manifest.get("scenes")
    require(isinstance(rows, list) and len(rows) == 12, "manifest must have exactly 12 scenes")
    ids = [str(row.get("scene_id", "")) for row in rows]
    require(len(set(ids)) == 12 and all(ids), "manifest scene IDs are missing or duplicated")
    require(ids[1] == FIRST_SCENE, "fixed first engineering scene changed")
    return rows, actual_sha


def locate_reports(scene_ids: list[str]) -> dict[str, tuple[Path, dict, str]]:
    found: dict[str, list[tuple[Path, int]]] = {sid: [] for sid in scene_ids}
    allowed = set(scene_ids)
    for root in REPORT_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("A1T_SAME_STATE_DECOMPOSITION_*_v*.json"):
            match = REPORT_RE.match(path.name)
            if not match:
                continue
            sid, version_text = match.groups()
            require(sid in allowed, f"unexpected scene report in fixed report roots: {path}")
            version = int(version_text)
            expected_version = 1 if sid == FIRST_SCENE else 2
            require(version == expected_version, f"unexpected report version for {sid}: v{version}")
            found[sid].append((path, version))
    missing = [sid for sid, matches in found.items() if not matches]
    duplicates = {sid: [str(p) for p, _ in matches] for sid, matches in found.items() if len(matches) > 1}
    require(not missing, "missing audited per-scene reports: " + ", ".join(missing))
    require(not duplicates, "duplicate per-scene reports: " + json.dumps(duplicates, ensure_ascii=False))
    result = {}
    for sid in scene_ids:
        path = found[sid][0][0]
        data, digest = read_json(path)
        if sid == FIRST_SCENE:
            require(digest == FIRST_REPORT_SHA256,
                    f"{sid}: differs from the independently arithmetic-audited first report")
        result[sid] = (path, data, digest)
    return result


def validate_identity(report: dict, scene: dict, scene_id: str, report_sha: str,
                      common_reference: dict | None) -> dict:
    require(report.get("status") == "PASS_SINGLE_SCENE_ONLY", f"{scene_id}: report not PASS_SINGLE_SCENE_ONLY")
    require(str(report.get("schema", "")).startswith("A1T_SAME_STATE_ERROR_DECOMPOSITION_SINGLE_SCENE_V"),
            f"{scene_id}: unexpected report schema")
    scope = report.get("scope", {})
    require(scope.get("scene_id") == scene_id, f"{scene_id}: scope scene mismatch")
    require(scope.get("task") == scene.get("task"), f"{scene_id}: task mismatch")
    require(scope.get("category") == scene.get("category"), f"{scene_id}: category mismatch")
    require(scope.get("screen12_full_aggregate") is False, f"{scene_id}: input is not a single-scene report")
    require(scope.get("TEST_accessed") is False, f"{scene_id}: report TEST scope must be false")
    require(scope.get("diagnostic_plant_calls") == 0 and scope.get("engine_calls") == 0,
            f"{scene_id}: report scope includes engine/Plant calls")
    require(scope.get("training_steps") == 0 and scope.get("optimizer_steps") == 0,
            f"{scene_id}: report scope includes training")
    identity = report.get("identity", {})
    require(identity.get("selected_step") == 40000, f"{scene_id}: wrong selected step")
    for key, expected in EXPECTED_COMMON_IDENTITY.items():
        require(identity.get(key) == expected, f"{scene_id}: identity {key} mismatch")
    for key in COMMON_IDENTITY_FIELDS:
        require(key in identity, f"{scene_id}: identity missing {key}")
    if common_reference is not None:
        for key in COMMON_IDENTITY_FIELDS:
            require(identity[key] == common_reference[key], f"{scene_id}: shared identity differs at {key}")
    for key in ("raw_sha256", "run_start_sha256", "status_sha256",
                "independent_audit_sha256", "root_release_sha256"):
        value = identity.get(key)
        require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None,
                f"{scene_id}: invalid/missing per-scene identity {key}")
    require(report_sha != "", f"{scene_id}: report hash missing")
    return identity


def validate_event(event: dict, i: int, dmax: list[float], scene_id: str) -> dict:
    idx = int(event["plant_index"])
    require(idx == 11 + 10 * i, f"{scene_id}: event {i} plant_index {idx}")
    t = finite_number(event["time_s"], f"{scene_id} event {i} time")
    close(t, (idx - 1) * 0.001, f"{scene_id} event {i} time/index", 1e-10)
    beta = finite_number(event["beta"], f"{scene_id} event {i} beta")
    require(0.0 < beta <= 1.0, f"{scene_id} event {i}: expected positive beta")
    g = vector(event["G_row_major"], 9, f"{scene_id} event {i} G")
    e0 = vector(event["E0_rad_s2"], 3, f"{scene_id} event {i} E0")
    cstar = vector(event["Cstar_rad_s2"], 3, f"{scene_id} event {i} Cstar")
    y = vector(event["raw_output"], 3, f"{scene_id} event {i} raw output")
    target = vector(event["raw_target_Cstar_over_beta"], 3, f"{scene_id} event {i} raw target")
    raw_error = vector(event["raw_output_minus_target"], 3, f"{scene_id} event {i} raw error")
    actual_action = vector(event["actual_action_rad_s2"], 3, f"{scene_id} event {i} action")
    cproj = vector(event["cproj_feasible_action_rad_s2"], 3, f"{scene_id} event {i} cproj")
    fit = vector(event["fit_applied_rad_s2"], 3, f"{scene_id} event {i} fit")
    clipinc = vector(event["clip_increment_rad_s2"], 3, f"{scene_id} event {i} clip increment")
    lin_fit = vector(event["linear_fit_error_rad_s2"], 3, f"{scene_id} event {i} linear fit")
    lin_clip = vector(event["linear_clip_error_rad_s2"], 3, f"{scene_id} event {i} linear clip")
    lin_actual = vector(event["linear_actual_residual_rad_s2"], 3, f"{scene_id} event {i} linear residual")
    full_actual = vector(event["full_allocator_actual_error_rad_s2"], 3, f"{scene_id} event {i} full residual")
    full_cproj = vector(event["full_allocator_cproj_error_rad_s2"], 3, f"{scene_id} event {i} full cproj error")

    projected_y = [max(-dmax[j], min(dmax[j], y[j])) for j in range(3)]
    expected_target = [cstar[j] / beta for j in range(3)]
    expected_action = [beta * projected_y[j] for j in range(3)]
    expected_fit = [cstar[j] - beta * y[j] for j in range(3)]
    expected_clip = [beta * (y[j] - projected_y[j]) for j in range(3)]
    expected_cproj = [beta * max(-dmax[j], min(dmax[j], expected_target[j])) for j in range(3)]
    for j in range(3):
        close(sum(g[3 * j + k] * cstar[k] for k in range(3)), e0[j],
              f"{scene_id} event {i} G*Cstar=E0 axis{j}")
        close(target[j], expected_target[j], f"{scene_id} event {i} Cstar/beta axis{j}")
        close(raw_error[j], y[j] - expected_target[j], f"{scene_id} event {i} raw error axis{j}")
        close(actual_action[j], expected_action[j], f"{scene_id} event {i} beta-clip action axis{j}")
        close(fit[j], expected_fit[j], f"{scene_id} event {i} fit axis{j}")
        close(clipinc[j], expected_clip[j], f"{scene_id} event {i} clip axis{j}")
        close(cproj[j], expected_cproj[j], f"{scene_id} event {i} cproj axis{j}")
    expected_lin_fit = matvec3(g, fit)
    expected_lin_clip = matvec3(g, clipinc)
    expected_lin_actual = [e0[j] - matvec3(g, actual_action)[j] for j in range(3)]
    for j in range(3):
        close(lin_fit[j], expected_lin_fit[j], f"{scene_id} event {i} G*fit axis{j}")
        close(lin_clip[j], expected_lin_clip[j], f"{scene_id} event {i} G*clip axis{j}")
        close(lin_actual[j], expected_lin_actual[j], f"{scene_id} event {i} E0-G*action axis{j}")
        close(lin_actual[j], lin_fit[j] + lin_clip[j], f"{scene_id} event {i} fit+clip closure axis{j}")

    sigma = finite_number(event["sigma_min_G"], f"{scene_id} event {i} sigma_min_G")
    cond = finite_number(event["condition_G"], f"{scene_id} event {i} condition_G")
    require(sigma > 0 and cond >= 1.0 - 1e-10,
            f"{scene_id} event {i}: G rank/condition metadata invalid")
    lower = finite_number(event["cproj_linear_surrogate_lower_bound_rad_s2"], "projection lower bound")
    upper = finite_number(event["cproj_linear_surrogate_upper_bound_rad_s2"], "projection upper bound")
    require(lower >= -1e-10 and upper >= -1e-10 and lower <= upper + 1e-8,
            f"{scene_id} event {i}: invalid linear-surrogate bounds")
    close(lower, sigma * norm([cstar[j] - cproj[j] for j in range(3)]),
          f"{scene_id} event {i} sigma projection bound")
    close(upper, norm(matvec3(g, [cstar[j] - cproj[j] for j in range(3)])),
          f"{scene_id} event {i} G projection bound")

    mse_cross = vector(event["mse_fit_clip_cross_term_by_axis"], 3,
                       f"{scene_id} event {i} mse cross")
    mse_identity = vector(event["mse_identity_error_by_axis"], 3,
                          f"{scene_id} event {i} mse identity error")
    fit_clip_cross = [2.0 * lin_fit[j] * lin_clip[j] for j in range(3)]
    for j in range(3):
        close(mse_cross[j], fit_clip_cross[j], f"{scene_id} event {i} MSE cross axis{j}")
        close(mse_identity[j],
              lin_actual[j] ** 2 - lin_fit[j] ** 2 - lin_clip[j] ** 2 - fit_clip_cross[j],
              f"{scene_id} event {i} MSE identity axis{j}")
    expected_vector_cross = 2.0 * sum(lin_fit[j] * lin_clip[j] for j in range(3))
    close(finite_number(event["mse_fit_clip_cross_term_vector"], "vector MSE cross"),
          expected_vector_cross, f"{scene_id} event {i} vector MSE cross")

    base_delta = vector(event["base_matrix_delta_N"], 4, f"{scene_id} event {i} base allocator delta")
    prepared = {key: event[raw_key] for key, raw_key in EVENT_VECTOR_FIELDS.items()
                if raw_key is not None}
    prepared["full_allocator_minus_linear_residual_rad_s2"] = [
        full_actual[j] - lin_actual[j] for j in range(3)
    ]
    prepared["base_allocator_delta_generalized_mixed_units"] = base_delta
    prepared["_time_s"] = t
    prepared["_linear_fit"] = lin_fit
    prepared["_linear_clip"] = lin_clip
    prepared["_linear_actual"] = lin_actual
    prepared["_full_actual"] = full_actual
    prepared["_sigma_min_G"] = sigma
    prepared["_condition_G"] = cond
    prepared["_projection_lower"] = lower
    prepared["_projection_upper"] = upper
    prepared["_mse_cross"] = fit_clip_cross
    flags = {}
    for name, (size, source) in FLAG_FIELDS.items():
        value = event[source]
        require(isinstance(value, list) and len(value) == size and all(isinstance(x, bool) for x in value),
                f"{scene_id} event {i} invalid flags {source}")
        flags[name] = value
    prepared["_flags"] = flags
    return prepared


def summarize_event_window(events: list[dict], window: str, scene_id: str) -> dict:
    expected_events = {"ALL_0_20": 1999, "PRE_0_5": 499, "POST_5_20": 1500}[window]
    require(len(events) == expected_events, f"{scene_id} {window}: event count {len(events)}")
    metrics = {}
    metric_names = list(EVENT_VECTOR_FIELDS)
    metric_names.append("base_allocator_delta_generalized_mixed_units")
    for name in metric_names:
        metrics[name] = scene_stats([event[name] for event in events])
        if name == "base_allocator_delta_generalized_mixed_units":
            # Thrust is N and the other channels are Nm; do not combine these into a vector norm.
            metrics[name].pop("vector_rms")
            metrics[name]["channel_order"] = ["thrust_N", "torque_x_Nm", "torque_y_Nm", "torque_z_Nm"]
    n = len(events)
    mse_fit = [sum(event["_linear_fit"][j] ** 2 for event in events) / n for j in range(3)]
    mse_clip = [sum(event["_linear_clip"][j] ** 2 for event in events) / n for j in range(3)]
    mse_cross = [sum(event["_mse_cross"][j] for event in events) / n for j in range(3)]
    mse_actual = [sum(event["_linear_actual"][j] ** 2 for event in events) / n for j in range(3)]
    mse_closure = [mse_actual[j] - mse_fit[j] - mse_clip[j] - mse_cross[j] for j in range(3)]
    vector_fit = sum(mse_fit)
    vector_clip = sum(mse_clip)
    vector_cross = sum(mse_cross)
    vector_actual = sum(mse_actual)
    flags = {}
    for name, (size, _) in FLAG_FIELDS.items():
        flags[name] = [sum(int(event["_flags"][name][j]) for event in events) for j in range(size)]
    return {
        "window": window,
        "event_count": n,
        "metrics": metrics,
        "mse": {
            "axis_order": list(AXES),
            "fit": mse_fit,
            "clip": mse_clip,
            "cross_term": mse_cross,
            "actual": mse_actual,
            "closure_error": mse_closure,
            "clip_net_mse_increment": [mse_clip[j] + mse_cross[j] for j in range(3)],
            "vector": {
                "fit": vector_fit,
                "clip": vector_clip,
                "cross_term": vector_cross,
                "actual": vector_actual,
                "closure_error": vector_actual - vector_fit - vector_clip - vector_cross,
                "clip_net_mse_increment": vector_clip + vector_cross,
            },
            "definition": "MSE_actual=MSE_fit+MSE_clip+cross_term; clip_net_mse_increment=MSE_clip+cross_term; same-event static arithmetic, not closed-loop causality",
        },
        "clip_and_saturation_counts": flags,
        "projection_bounds": {
            "linear_surrogate_only": True,
            "lower_norm_mean": sum(event["_projection_lower"] for event in events) / n,
            "upper_norm_mean": sum(event["_projection_upper"] for event in events) / n,
        },
        "G_condition": {
            "minimum_sigma_min_G": min(event["_sigma_min_G"] for event in events),
            "maximum_condition_G": max(event["_condition_G"] for event in events),
        },
    }


def summarize_hold(source: dict, expected_count: int, scene_id: str, window: str) -> dict:
    require(source.get("window") == window, f"{scene_id}: hold window mismatch {window}")
    require(source.get("non_event_count") == expected_count,
            f"{scene_id} {window}: hold count {source.get('non_event_count')} != {expected_count}")
    metrics = {}
    for key in HOLD_METRICS:
        record = source.get(key)
        require(isinstance(record, dict) and record.get("count") == expected_count,
                f"{scene_id} {window}: missing/bad hold metric {key}")
        axes = record.get("axis")
        require(isinstance(axes, list) and len(axes) == 3, f"{scene_id} {window}: bad hold axes {key}")
        require([axis.get("axis") for axis in axes] == list(AXES),
                f"{scene_id} {window}: unexpected hold axis order {key}")
        metrics[key] = {
            "count": expected_count,
            "signed_mean": [finite_number(axis["signed_mean"], key) for axis in axes],
            "rms": [finite_number(axis["rms"], key) for axis in axes],
            "vector_rms": finite_number(record["vector_rms"], key),
        }
    flag_names = (
        "fresh_raw_clip_count_by_axis",
        "fresh_allocator_clip_count_by_channel",
        "fresh_motor_saturation_count_by_motor",
        "held_allocator_clip_count_by_channel",
        "held_motor_saturation_count_by_motor",
    )
    counts = {}
    for key in flag_names:
        value = source.get(key)
        require(isinstance(value, list) and len(value) in (3, 4), f"{scene_id} {window}: bad hold counts {key}")
        counts[key] = [int(x) for x in value]
    return {"window": window, "non_event_count": expected_count, "metrics": metrics, "counts": counts}


def load_scene_reports(manifest_scenes: list[dict], diagnostic_releases: dict) -> list[dict]:
    scene_ids = [row["scene_id"] for row in manifest_scenes]
    reports = locate_reports(scene_ids)
    first_identity = None
    per_scene = []
    for scene in manifest_scenes:
        sid = scene["scene_id"]
        report_path, report, digest = reports[sid]
        identity = validate_identity(report, scene, sid, digest, first_identity)
        audit_provenance = audit_scene_identity(identity, sid)
        if first_identity is None:
            first_identity = identity
        schedule = report.get("schedule", {})
        require(schedule.get("transition_count") == 20000 and schedule.get("state_count") == 20001,
                f"{sid}: unexpected fixed record horizon")
        require(schedule.get("event_count") == 1999 and schedule.get("event_stride") == 10,
                f"{sid}: unexpected event schedule")
        dmax = vector(schedule.get("dmax_rad_s2"), 3, f"{sid} dmax")
        require(dmax == [45.0, 45.0, 4.7124], f"{sid}: dmax changed")
        records = report.get("event_records")
        require(isinstance(records, list) and len(records) == 1999, f"{sid}: report must have 1999 events")
        checked = [validate_event(event, i, dmax, sid) for i, event in enumerate(records)]
        windows = {}
        hold_rows = report.get("zoh_same_state")
        require(isinstance(hold_rows, list) and len(hold_rows) == 3, f"{sid}: missing three hold windows")
        holds_by_name = {row.get("window"): row for row in hold_rows}
        require(len(holds_by_name) == 3, f"{sid}: duplicate hold windows")
        for name, select, event_count, hold_count in WINDOWS:
            selected = [event for event in checked if select(event["_time_s"])]
            event_summary = summarize_event_window(selected, name, sid)
            hold_summary = summarize_hold(holds_by_name[name], hold_count, sid, name)
            windows[name] = {"events": event_summary, "hold": hold_summary}
        wind_match = re.search(r"_W([0-9]{2})$", sid)
        require(wind_match is not None, f"{sid}: cannot derive fixed wind group from scene ID")
        wind_id = int(wind_match.group(1))
        per_scene.append({
            "scene_id": sid,
            "task": scene["task"],
            "category": scene["category"],
            "wind_id_from_scene_id": wind_id,
            "HF_rule": "wind suffix W09..W14 (fixed task instruction; not a manifest field)",
            "HF": 9 <= wind_id <= 14,
            "report_path": report_path.relative_to(ROOT).as_posix(),
            "report_sha256": digest,
            "source_report_schema": report["schema"],
            "status": report["status"],
            "identity": identity,
            "independent_audit_and_run_release": audit_provenance,
            "diagnostic_execution_release": diagnostic_releases["source_records"][
                "first" if sid == FIRST_SCENE else "remaining11"
            ],
            "event_record_count": len(records),
            "windows": windows,
        })
    return per_scene


def average_stats(stats: list[dict]) -> dict:
    require(stats, "empty group metric")
    n = len(stats)
    dim = len(stats[0]["signed_mean"])
    require(all(len(s["signed_mean"]) == dim and len(s["rms"]) == dim for s in stats),
            "group metric dimensions differ")
    output = {
        "scene_count": n,
        "signed_mean": [sum(s["signed_mean"][j] for s in stats) / n for j in range(dim)],
        "rms": [sum(s["rms"][j] for s in stats) / n for j in range(dim)],
        "aggregation": "unweighted arithmetic mean of per-scene statistics",
    }
    if "max_abs_by_component" in stats[0]:
        output["max_abs_by_component"] = [
            sum(s["max_abs_by_component"][j] for s in stats) / n for j in range(dim)
        ]
    if "vector_rms" in stats[0]:
        output["vector_rms"] = sum(s["vector_rms"] for s in stats) / n
    if "channel_order" in stats[0]:
        require(all(s.get("channel_order") == stats[0]["channel_order"] for s in stats),
                "mixed-unit channel labels differ in group")
        output["channel_order"] = stats[0]["channel_order"]
    return output


def average_hold_stats(stats: list[dict]) -> dict:
    return average_stats(stats)


def aggregate_window(scenes: list[dict], window: str) -> dict:
    event_rows = [scene["windows"][window]["events"] for scene in scenes]
    hold_rows = [scene["windows"][window]["hold"] for scene in scenes]
    metric_names = event_rows[0]["metrics"].keys()
    event_metrics = {
        name: average_stats([row["metrics"][name] for row in event_rows])
        for name in metric_names
    }
    hold_names = hold_rows[0]["metrics"].keys()
    hold_metrics = {
        name: average_hold_stats([row["metrics"][name] for row in hold_rows])
        for name in hold_names
    }
    flag_names = event_rows[0]["clip_and_saturation_counts"].keys()
    flag_counts = {
        name: {
            "per_scene_mean": [
                sum(row["clip_and_saturation_counts"][name][j] for row in event_rows) / len(scenes)
                for j in range(len(event_rows[0]["clip_and_saturation_counts"][name]))
            ],
            "total_across_scenes": [
                sum(row["clip_and_saturation_counts"][name][j] for row in event_rows)
                for j in range(len(event_rows[0]["clip_and_saturation_counts"][name]))
            ],
        }
        for name in flag_names
    }
    hold_count_names = hold_rows[0]["counts"].keys()
    hold_counts = {
        name: {
            "per_scene_mean": [
                sum(row["counts"][name][j] for row in hold_rows) / len(scenes)
                for j in range(len(hold_rows[0]["counts"][name]))
            ],
            "total_across_scenes": [
                sum(row["counts"][name][j] for row in hold_rows)
                for j in range(len(hold_rows[0]["counts"][name]))
            ],
        }
        for name in hold_count_names
    }
    mse = {
        key: [sum(row["mse"][key][j] for row in event_rows) / len(scenes)
              for j in range(3)]
        for key in ("fit", "clip", "cross_term", "actual", "closure_error",
                    "clip_net_mse_increment")
    }
    mse["vector"] = {
        key: sum(row["mse"]["vector"][key] for row in event_rows) / len(scenes)
        for key in ("fit", "clip", "cross_term", "actual", "closure_error",
                    "clip_net_mse_increment")
    }
    return {
        "window": window,
        "scene_count": len(scenes),
        "scene_ids": [scene["scene_id"] for scene in scenes],
        "event_count_per_scene": [row["event_count"] for row in event_rows],
        "event_count_total": sum(row["event_count"] for row in event_rows),
        "event_metrics_scene_mean": event_metrics,
        "mse_scene_mean": mse,
        "clip_and_saturation_counts": flag_counts,
        "projection_bounds_scene_mean": {
            key: sum(row["projection_bounds"][key] for row in event_rows) / len(scenes)
            for key in ("lower_norm_mean", "upper_norm_mean")
        },
        "G_condition_scene_summary": {
            "mean_of_scene_minimum_sigma_min_G": sum(
                row["G_condition"]["minimum_sigma_min_G"] for row in event_rows
            ) / len(scenes),
            "maximum_of_scene_maximum_condition_G": max(
                row["G_condition"]["maximum_condition_G"] for row in event_rows
            ),
        },
        "hold_non_event_count_per_scene": [row["non_event_count"] for row in hold_rows],
        "hold_non_event_count_total": sum(row["non_event_count"] for row in hold_rows),
        "hold_metrics_scene_mean": hold_metrics,
        "hold_clip_and_saturation_counts": hold_counts,
        "aggregation": "scene-level arithmetic means; no event-pooled weighting",
    }


def build_groups(scenes: list[dict]) -> list[dict]:
    groups: list[tuple[str, list[dict]]] = [("ALL", scenes)]
    groups.extend((task, [s for s in scenes if s["task"] == task]) for task in ("T1", "T2", "T3"))
    hf = [s for s in scenes if s["HF"]]
    w15 = [s for s in scenes if s["wind_id_from_scene_id"] == 15]
    all_arms = [s for s in scenes if s["category"] == "ALL_ARMS"]
    hf_all_arms = [s for s in hf if s["category"] == "ALL_ARMS"]
    require(len(hf) == 3 and len(w15) == 3 and len(all_arms) == 3 and len(hf_all_arms) == 3,
            "fixed HF/W15/ALL_ARMS group counts changed")
    groups.extend((
        ("HF_W09_W14", hf),
        ("W15", w15),
        ("CATEGORY_ALL_ARMS", all_arms),
        ("HF_ALL_ARMS", hf_all_arms),
    ))
    for task in ("T1", "T2", "T3"):
        for category in ("STATIC", "ACTIVE_NO_WIND", "ALL_ARMS", "MULTI_ARM"):
            selected = [s for s in scenes if s["task"] == task and s["category"] == category]
            require(len(selected) == 1, f"expected one fixed scene in {task}/{category}")
            groups.append((f"TASK_CATEGORY_{task}_{category}", selected))
    return [
        {
            "group_id": group_id,
            "scene_count": len(selected),
            "scene_ids": [scene["scene_id"] for scene in selected],
            "windows": {name: aggregate_window(selected, name) for name, *_ in WINDOWS},
        }
        for group_id, selected in groups
    ]


def flatten_window(scope_type: str, scope_id: str, scene_id: str, task: str,
                   category: str, window: str, event_summary: dict, hold_summary: dict) -> dict:
    row = {
        "scope_type": scope_type,
        "scope_id": scope_id,
        "scene_id": scene_id,
        "task": task,
        "category": category,
        "window": window,
        "event_count": event_summary["event_count"],
        "hold_non_event_count": hold_summary["non_event_count"],
    }
    for metric, stats in event_summary["metrics"].items():
        for j, axis in enumerate(AXES if len(stats["signed_mean"]) == 3 else
                                 ("thrust_N", "torque_x_Nm", "torque_y_Nm", "torque_z_Nm")):
            row[f"{metric}_signed_mean_{axis}"] = stats["signed_mean"][j]
            row[f"{metric}_rms_{axis}"] = stats["rms"][j]
            row[f"{metric}_max_abs_{axis}"] = stats["max_abs_by_component"][j]
        if "vector_rms" in stats:
            row[f"{metric}_vector_rms"] = stats["vector_rms"]
    for metric, stats in hold_summary["metrics"].items():
        for j, axis in enumerate(AXES):
            row[f"hold_{metric}_signed_mean_{axis}"] = stats["signed_mean"][j]
            row[f"hold_{metric}_rms_{axis}"] = stats["rms"][j]
        row[f"hold_{metric}_vector_rms"] = stats["vector_rms"]
    for axis, value in zip(AXES, event_summary["mse"]["fit"]):
        row[f"mse_fit_{axis}"] = value
    for axis, value in zip(AXES, event_summary["mse"]["clip"]):
        row[f"mse_clip_{axis}"] = value
    for axis, value in zip(AXES, event_summary["mse"]["cross_term"]):
        row[f"mse_cross_term_{axis}"] = value
    for axis, value in zip(AXES, event_summary["mse"]["actual"]):
        row[f"mse_actual_{axis}"] = value
    for axis, value in zip(AXES, event_summary["mse"]["closure_error"]):
        row[f"mse_closure_error_{axis}"] = value
    for axis, value in zip(AXES, event_summary["mse"]["clip_net_mse_increment"]):
        row[f"clip_net_mse_increment_{axis}"] = value
    for key, value in event_summary["mse"]["vector"].items():
        row[f"mse_{key}_vector"] = value
    for key, value in event_summary.get("projection_bounds", {}).items():
        if key != "linear_surrogate_only":
            row[f"projection_{key}"] = value
    for key, value in event_summary.get("G_condition", {}).items():
        row[f"G_{key}"] = value
    for key, counts in event_summary["clip_and_saturation_counts"].items():
        for i, value in enumerate(counts):
            row[f"count_{key}_{i}"] = value
    for key, counts in hold_summary.get("counts", {}).items():
        for i, value in enumerate(counts):
            row[f"hold_count_{key}_{i}"] = value
    for key, counts in hold_summary.get("count_summary", {}).items():
        for i, value in enumerate(counts["per_scene_mean"]):
            row[f"hold_count_mean_{key}_{i}"] = value
        for i, value in enumerate(counts["total_across_scenes"]):
            row[f"hold_count_total_{key}_{i}"] = value
    return row


def scene_csv_rows(scenes: list[dict]) -> list[dict]:
    rows = []
    for scene in scenes:
        for name, *_ in WINDOWS:
            record = scene["windows"][name]
            row = flatten_window("scene", scene["scene_id"], scene["scene_id"],
                                 scene["task"], scene["category"], name,
                                 record["events"], record["hold"])
            row["wind_id_from_scene_id"] = scene["wind_id_from_scene_id"]
            row["HF_by_W09_W14_rule"] = scene["HF"]
            row["report_path"] = scene["report_path"]
            row["report_sha256"] = scene["report_sha256"]
            row["audit_sha256"] = scene["independent_audit_and_run_release"]["audit_sha256"]
            row["run_release_sha256"] = scene["independent_audit_and_run_release"]["run_release_sha256"]
            rows.append(row)
    return rows


def group_csv_rows(groups: list[dict], report_scenes: list[dict]) -> list[dict]:
    rows = []
    for group in groups:
        for name, *_ in WINDOWS:
            record = group["windows"][name]
            # Group rows use scene-mean summaries with the same flattened metric layout.
            event_like = {
                "event_count": record["event_count_total"],
                "metrics": record["event_metrics_scene_mean"],
                "mse": record["mse_scene_mean"],
                "clip_and_saturation_counts": {
                    key: value["per_scene_mean"] for key, value in record["clip_and_saturation_counts"].items()
                },
                "projection_bounds": record["projection_bounds_scene_mean"],
                "G_condition": record["G_condition_scene_summary"],
            }
            hold_like = {
                "non_event_count": record["hold_non_event_count_total"],
                "metrics": record["hold_metrics_scene_mean"],
                "count_summary": record["hold_clip_and_saturation_counts"],
            }
            rows.append(flatten_window("group", group["group_id"], "",
                                       "", "", name, event_like, hold_like))
            rows[-1]["scene_count"] = group["scene_count"]
            rows[-1]["scene_ids"] = "|".join(group["scene_ids"])
            rows[-1]["report_sha256s"] = "|".join(
                next(s["report_sha256"] for s in report_scenes if s["scene_id"] == sid)
                for sid in group["scene_ids"]
            )
            rows[-1]["event_count_mean_per_scene"] = (
                record["event_count_total"] / group["scene_count"]
            )
            rows[-1]["hold_non_event_count_mean_per_scene"] = (
                record["hold_non_event_count_total"] / group["scene_count"]
            )
    return rows


def write_csv_exclusive(path: Path, rows: list[dict]) -> None:
    require(rows, f"no CSV rows for {path.name}")
    fields = list(rows[0])
    require(len(fields) == len(set(fields)), f"duplicate CSV field names in {path.name}")
    require(all(set(row) == set(fields) for row in rows), f"inconsistent CSV fields in {path.name}")
    with path.open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def build_report(manifest_scenes: list[dict], manifest_sha: str) -> dict:
    diagnostic_releases = load_diagnostic_releases([row["scene_id"] for row in manifest_scenes])
    per_scene = load_scene_reports(manifest_scenes, diagnostic_releases)
    groups = build_groups(per_scene)
    return {
        "schema": "ROOT_A1T_SAME_STATE_DECOMPOSITION12_AGGREGATE_V1",
        "status": "COMPLETE_ALL12_DIAGNOSTIC_NO_WINNER_GATE",
        "scope": {
            "scene_count": 12,
            "scene_order": [scene["scene_id"] for scene in per_scene],
            "manifest_path": MANIFEST_REL.as_posix(),
            "manifest_sha256": manifest_sha,
            "taskbook_path": TASKBOOK_REL.as_posix(),
            "taskbook_sha256": TASKBOOK_SHA256,
            "diagnostic_execution_releases": diagnostic_releases["source_records"],
            "report_input_roots": [p.relative_to(ROOT).as_posix() for p in REPORT_ROOTS],
            "report_semantics": "Per-event source records are retained in the pinned input reports; this output stores their arithmetic summaries and source hashes.",
            "aggregation_rule": "Compute each scene/window first, then average scene summaries equally; never pool event rows across scenes.",
            "HF_rule": "scene_id wind suffix W09..W14; fixed instruction override because the SCREEN12 manifest has no HF field.",
            "W15_rule": "scene_id suffix W15.",
            "TEST_accessed": False,
            "raw_or_live_run_data_accessed": False,
            "plant_or_engine_or_training_calls": 0,
            "interpretation_limit": "Mechanism arithmetic summary only; no causal verdict, model winner gate, or closed-loop performance claim.",
        },
        "aggregator_source": {
            "path": Path(__file__).resolve().relative_to(ROOT).as_posix(),
            "sha256": sha256_file(Path(__file__).resolve()),
        },
        "per_scene": per_scene,
        "groups": groups,
    }


def self_check() -> None:
    sample = scene_stats([[1.0, -2.0, 0.0], [3.0, 2.0, 0.0]])
    require(sample["signed_mean"] == [2.0, 0.0, 0.0], "self-check mean")
    require(sample["rms"] == [math.sqrt(5.0), 2.0, 0.0], "self-check RMS")
    sample_rows = [{"m": {"signed_mean": [1.0], "rms": [2.0], "vector_rms": 2.0}},
                   {"m": {"signed_mean": [3.0], "rms": [4.0], "vector_rms": 4.0}}]
    group = average_stats([x["m"] for x in sample_rows])
    require(group["signed_mean"] == [2.0] and group["rms"] == [3.0],
            "self-check equal-scene aggregation")
    print("SELF_CHECK_PASS")


def main() -> None:
    if sys.argv[1:] == ["--self-check"]:
        self_check()
        return
    require(not sys.argv[1:], "this fixed-input aggregator accepts no arguments")
    require(not OUT_DIR.exists(), f"refusing to overwrite existing output directory: {OUT_DIR}")
    taskbook = ROOT / TASKBOOK_REL
    require(taskbook.is_file() and sha256_file(taskbook) == TASKBOOK_SHA256,
            "frozen decomposition taskbook missing or SHA mismatch")
    manifest_scenes, manifest_sha = manifest_rows()
    report = build_report(manifest_scenes, manifest_sha)
    scene_rows = scene_csv_rows(report["per_scene"])
    group_rows = group_csv_rows(report["groups"], report["per_scene"])
    # Build all products in memory before creating the one-shot result directory.
    encoded = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
    OUT_DIR.mkdir()
    try:
        with OUT_JSON.open("x", encoding="utf-8") as stream:
            stream.write(encoded)
        write_csv_exclusive(OUT_SCENE_CSV, scene_rows)
        write_csv_exclusive(OUT_GROUP_CSV, group_rows)
    except Exception:
        # Preserve a failed output directory as an honest partial attempt.
        raise
    print(json.dumps({
        "status": report["status"],
        "scene_count": len(report["per_scene"]),
        "group_count": len(report["groups"]),
        "output_json": OUT_JSON.relative_to(ROOT).as_posix(),
        "scene_csv_rows": len(scene_rows),
        "group_csv_rows": len(group_rows),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
