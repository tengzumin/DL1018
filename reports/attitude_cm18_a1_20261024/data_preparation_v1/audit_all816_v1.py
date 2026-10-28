"""Independent, read-only CM18 ALL816 cache audit; SCREEN4-only self-check is explicit."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[3]
PREP = Path("reports/attitude_cm18_a1_20261024/data_preparation_v1")
INPUT_REL = PREP / "INPUT_MANIFEST_v1.json"
SCREEN4_REL = PREP / "events_screen4_v1/DATASET_MANIFEST_v1.json"
ALL816_REL = PREP / "events_all816_v1/DATASET_MANIFEST_v1.json"
INPUT_SHA = "a5f7fea9b0918c1449af6fa83929177d3bf7d5e70cb3b71711c40f6338d210a5"
SCREEN4_SHA = "b36a9027202a15408d69676c5e16f7993652c4c7a82c6a8695a64eb77961ef7c"
SCREEN4_IDS = {
    "DL1018_TRAIN_T1_C00_W00", "DL1018_TRAIN_T1_C01_W00",
    "DL1018_VAL_T1_C00_W07", "DL1018_VAL_T1_C01_W08",
}
PHASES = ("STATIC", "PRE", "EXTEND", "HOLD", "RETRACT", "RECOVERY")
PHASE_NAMES = dict(enumerate(PHASES))
DMAX = np.array([45.0, 45.0, 4.7124], dtype=np.float64)
VARIABLES = ("X18", "target_raw", "event_time_s", "phase_code", "plant_index",
             "scene_id", "split", "input_identity", "export_meta")
INPUT_ID_FIELDS = {"input_manifest_sha256", "event_h5_path", "event_h5_sha256",
                   "event_h5_size_bytes", "raw_run_path", "raw_run_sha256",
                   "raw_run_size_bytes", "run_start_path", "run_start_sha256",
                   "run_start_size_bytes"}
META_FIELDS = {"schema", "scene_id", "split", "event_count", "plant_index_matlab_1based",
               "max_abs_label_delta_vs_h5_rad_s2", "max_abs_label_delta_by_axis_rad_s2",
               "axis_rms_label_rad_s2", "phase_summary",
               "requested_torque_vs_nominal_minus_applied_max_abs_Nm",
               "true_dynamics_equation_residual_max_abs_Nm", "physical_feature_crosscheck",
               "tolerances", "failure_reasons", "qualified", "status"}
EXPECTED_TOLERANCES = {
    "label_vs_h5_max_abs_rad_s2": 1e-8,
    "omega_max_abs": 1e-10,
    "alpha_BS_max_abs_rad_s2": 1e-7,
    "thrust_over_mass_max_abs_m_s2": 1e-8,
    "time_max_abs_s": 1e-12,
    "torque_request_closure_max_abs_Nm": 1e-8,
    "true_dynamics_equation_residual_max_abs_Nm": 1e-12,
}


class AuditError(ValueError):
    pass


RUN_STATE = {"stage": "not_started", "cache_reads": 0, "cache_audit_attempts": 0}

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def json_file(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    try:
        obj = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise AuditError(f"invalid JSON: {path}: {exc}") from exc
    if not isinstance(obj, dict):
        raise AuditError(f"expected JSON object: {path}")
    return obj, hashlib.sha256(raw).hexdigest()


def safe_repo_file(root: Path, relative: str, *, strict: bool = True) -> Path:
    rel = Path(relative)
    if rel.is_absolute():
        raise AuditError(f"absolute repository path rejected: {relative}")
    path = (root / rel).resolve(strict=strict)
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise AuditError(f"path escapes current repository: {relative}") from exc
    return path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AuditError(message)


def matlab_text(value: Any, name: str) -> str:
    a = np.asarray(value)
    if a.dtype.kind in "US":
        return "".join(str(x) for x in a.reshape(-1)).strip()
    if a.dtype.kind in "ui":
        return "".join(chr(int(x)) for x in a.reshape(-1) if int(x)).strip()
    raise AuditError(f"{name}: expected MATLAB text, got {a.dtype}")


def mat_struct(value: Any, name: str) -> Any:
    a = np.asarray(value)
    if a.shape != (1, 1) or not hasattr(a[0, 0], "_fieldnames"):
        raise AuditError(f"{name}: expected 1x1 MATLAB struct")
    return a[0, 0]


def number(value: Any, name: str) -> float:
    a = np.asarray(value)
    if a.size != 1 or not np.issubdtype(a.dtype, np.number):
        raise AuditError(f"{name}: expected numeric scalar")
    result = float(a.reshape(-1)[0])
    if not math.isfinite(result):
        raise AuditError(f"{name}: expected finite scalar")
    return result


def vector(value: Any, size: int, name: str) -> np.ndarray:
    a = np.asarray(value)
    if not np.issubdtype(a.dtype, np.number) or a.size != size:
        raise AuditError(f"{name}: expected {size} numeric values")
    result = a.reshape(-1).astype(np.float64)
    if not np.isfinite(result).all():
        raise AuditError(f"{name}: contains non-finite values")
    return result


def input_manifest(root: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    path = safe_repo_file(root, INPUT_REL.as_posix())
    obj, actual_sha = json_file(path)
    require(actual_sha == INPUT_SHA, "INPUT_MANIFEST SHA256 differs from the pinned value")
    require(obj.get("schema") == "ATTITUDE_CM18_A1_INPUT_MANIFEST_V1", "unexpected input manifest schema")
    scope = obj.get("scope", {})
    require(scope.get("train_scenes") == 768 and scope.get("val_scenes") == 48,
            "input manifest split counts differ from 768 TRAIN + 48 VAL")
    require(scope.get("test_accessed") is False and scope.get("raw_numeric_arrays_read") is False
            and scope.get("h5_numeric_arrays_read") is False, "input manifest scope is not isolated")
    scenes = obj.get("scenes")
    require(isinstance(scenes, list) and len(scenes) == 816, "input manifest must list 816 scenes")
    by_id: dict[str, dict[str, Any]] = {}
    for scene in scenes:
        sid = scene.get("scene_id")
        require(isinstance(sid, str) and sid not in by_id, "input manifest has invalid/duplicate scene_id")
        require(scene.get("split") in ("TRAIN", "VAL") and scene.get("collector") == "B",
                f"{sid}: unexpected split or collector")
        files = scene.get("files")
        require(isinstance(files, list) and len(files) == 3, f"{sid}: expected three input files")
        roles: dict[str, dict[str, Any]] = {}
        for row in files:
            role = row.get("role")
            require(role in ("event_h5", "raw_run", "run_start") and role not in roles,
                    f"{sid}: invalid/duplicate input role")
            require(isinstance(row.get("path"), str) and isinstance(row.get("sha256"), str)
                    and len(row["sha256"]) == 64, f"{sid}: malformed input identity")
            require(isinstance(row.get("size_bytes"), int) and row["size_bytes"] > 0,
                    f"{sid}: malformed input byte count")
            roles[role] = row
        require(set(roles) == {"event_h5", "raw_run", "run_start"}, f"{sid}: missing input role")
        scene["_roles"] = roles
        by_id[sid] = scene
    require(sum(s["split"] == "TRAIN" for s in by_id.values()) == 768
            and sum(s["split"] == "VAL" for s in by_id.values()) == 48,
            "input manifest scene rows do not match 768/48")
    return {**obj, "_sha256": actual_sha}, by_id


def validate_manifest_rows(obj: dict[str, Any], mode: str) -> list[dict[str, Any]]:
    want = 4 if mode == "SCREEN4" else 816
    require(obj.get("schema") == "CM18_A1_DATASET_MANIFEST_V1", "unexpected dataset manifest schema")
    require(obj.get("mode") == mode, f"dataset manifest mode must be {mode}")
    require(obj.get("input_manifest_sha256", "").lower() == INPUT_SHA,
            "dataset manifest does not pin the approved input manifest")
    require(obj.get("TEST_accessed") is False and obj.get("raw_files_copied") is False,
            "dataset manifest does not certify TEST/raw-copy isolation")
    rows = obj.get("rows")
    require(isinstance(rows, list) and len(rows) == want, f"{mode} manifest must have {want} rows")
    require(obj.get("scene_count") == want and obj.get("qualified_count") == want
            and obj.get("failed_count") == 0, f"{mode} manifest is incomplete or has failures")
    ids = [r.get("scene_id") for r in rows]
    require(all(isinstance(s, str) for s in ids) and len(set(ids)) == want,
            f"{mode} manifest has invalid or duplicate scene IDs")
    require(all(r.get("qualified") is True and r.get("status") == "PASS" for r in rows),
            f"{mode} manifest contains a non-PASS row")
    require(sum(r.get("split") == "TRAIN" for r in rows) == (2 if mode == "SCREEN4" else 768)
            and sum(r.get("split") == "VAL" for r in rows) == (2 if mode == "SCREEN4" else 48),
            f"{mode} split counts are not correct")
    if mode == "ALL816":
        require(obj.get("unique_event_cache_bytes") == sum(int(r.get("cache_bytes", -1)) for r in rows),
                "ALL816 unique cache byte total differs from row totals")
    return rows


def validate_cache_references(root: Path, rows: list[dict[str, Any]], mode: str,
                              input_by_id: dict[str, dict[str, Any]], screen_rows: dict[str, dict[str, Any]]) -> None:
    paths: set[str] = set()
    for row in rows:
        sid, split = row["scene_id"], row["split"]
        source = input_by_id.get(sid)
        require(source is not None and source["split"] == split, f"{sid}: absent/mismatched input manifest scene")
        require(row.get("input_sha256") == {role: source["_roles"][role]["sha256"]
                                           for role in ("event_h5", "raw_run", "run_start")},
                f"{sid}: manifest input SHA map differs from INPUT_MANIFEST")
        expected_reuse = sid in SCREEN4_IDS
        if mode == "ALL816":
            require(row.get("reused_screen4_cache") is expected_reuse,
                    f"{sid}: unexpected SCREEN4 reuse flag")
        folder = "events_screen4_v1" if (mode == "SCREEN4" or expected_reuse) else "events_all816_v1"
        expected = (PREP / folder / f"{split}_{sid}.mat").as_posix()
        rel = str(row.get("cache_path", "")).replace("\\", "/")
        require(rel == expected, f"{sid}: cache path must be {expected}")
        path = safe_repo_file(root, rel, strict=False)
        require(path.parent == (root / PREP / folder).resolve(strict=False), f"{sid}: cache parent escaped expected folder")
        require(rel not in paths, f"{sid}: duplicate cache path")
        paths.add(rel)
        require(isinstance(row.get("cache_sha256"), str) and len(row["cache_sha256"]) == 64,
                f"{sid}: malformed cache SHA256")
        require(isinstance(row.get("cache_bytes"), int) and row["cache_bytes"] > 0,
                f"{sid}: malformed cache byte count")
        if mode == "ALL816" and expected_reuse:
            old = screen_rows.get(sid)
            require(old is not None and all(row.get(k) == old.get(k)
                    for k in ("cache_path", "cache_sha256", "cache_bytes", "input_sha256")),
                    f"{sid}: ALL816 reused cache differs from pinned SCREEN4 row")
    if mode == "ALL816":
        require(set(r["scene_id"] for r in rows) == set(input_by_id),
                "ALL816 scene IDs differ from INPUT_MANIFEST")
    else:
        require(set(r["scene_id"] for r in rows) == SCREEN4_IDS, "SCREEN4 scene IDs differ from approved scene set")

def verify_input_identity(mat: dict[str, Any], row: dict[str, Any], source: dict[str, Any]) -> None:
    ident = mat_struct(mat["input_identity"], "input_identity")
    require(set(ident._fieldnames) == INPUT_ID_FIELDS, "input_identity fields differ from observed SCREEN4 schema")
    require(matlab_text(ident.input_manifest_sha256, "input_identity.input_manifest_sha256") == INPUT_SHA,
            f"{row['scene_id']}: embedded input manifest SHA mismatch")
    for role, stem in (("event_h5", "event_h5"), ("raw_run", "raw_run"), ("run_start", "run_start")):
        expected = source["_roles"][role]
        require(matlab_text(getattr(ident, f"{stem}_path"), f"{stem}_path") == expected["path"],
                f"{row['scene_id']}: embedded {stem} path differs from INPUT_MANIFEST")
        require(matlab_text(getattr(ident, f"{stem}_sha256"), f"{stem}_sha256") == expected["sha256"],
                f"{row['scene_id']}: embedded {stem} SHA differs from INPUT_MANIFEST")
        require(int(number(getattr(ident, f"{stem}_size_bytes"), f"{stem}_size_bytes")) == expected["size_bytes"],
                f"{row['scene_id']}: embedded {stem} size differs from INPUT_MANIFEST")
        require(row["input_sha256"].get(role) == expected["sha256"],
                f"{row['scene_id']}: row {role} SHA differs from INPUT_MANIFEST")


def audit_scene(root: Path, row: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    sid, split = row["scene_id"], row["split"]
    path = safe_repo_file(root, row["cache_path"])
    actual_size = path.stat().st_size
    actual_sha = sha256(path)
    RUN_STATE["cache_reads"] += 1
    require(actual_size == row["cache_bytes"], f"{sid}: cache byte count mismatch")
    require(actual_sha == row["cache_sha256"].lower(), f"{sid}: cache SHA256 mismatch")
    mat = loadmat(path, squeeze_me=False, struct_as_record=False, variable_names=VARIABLES)
    require(set(VARIABLES).issubset(mat), f"{sid}: missing cache variables")
    x, y = np.asarray(mat["X18"]), np.asarray(mat["target_raw"])
    t, phase, idx = np.asarray(mat["event_time_s"]), np.asarray(mat["phase_code"]), np.asarray(mat["plant_index"])
    n = 1999
    require(x.shape == (n, 18) and x.dtype == np.float64, f"{sid}: X18 must be float64 (1999,18)")
    require(y.shape == (n, 3) and y.dtype == np.float64, f"{sid}: target_raw must be float64 (1999,3)")
    require(t.shape == (n, 1) and t.dtype == np.float64, f"{sid}: event_time_s must be float64 (1999,1)")
    require(phase.shape == (n, 1) and phase.dtype == np.uint8, f"{sid}: phase_code must be uint8 (1999,1)")
    require(idx.shape == (n, 1) and np.issubdtype(idx.dtype, np.integer), f"{sid}: plant_index must be integer (1999,1)")
    require(all(np.isfinite(a).all() for a in (x, y, t)), f"{sid}: non-finite X18/target_raw/event_time_s")
    idx1, t1, p1 = idx.reshape(-1).astype(np.int64), t.reshape(-1), phase.reshape(-1)
    expected_idx = np.arange(11, 20000, 10, dtype=np.int64)
    require(np.array_equal(idx1, expected_idx), f"{sid}: plant_index must be 11:10:19991")
    time_error = float(np.max(np.abs(t1 - (idx1 - 1) * 0.001)))
    require(time_error <= EXPECTED_TOLERANCES["time_max_abs_s"] and np.all(np.diff(t1) > 0),
            f"{sid}: event_time_s is not aligned/strictly increasing")
    require(int(p1.min()) >= 0 and int(p1.max()) <= 5, f"{sid}: phase_code outside 0..5")
    require(matlab_text(mat["scene_id"], "scene_id") == sid and matlab_text(mat["split"], "split") == split,
            f"{sid}: embedded scene/split identity mismatch")
    verify_input_identity(mat, row, source)
    meta = mat_struct(mat["export_meta"], "export_meta")
    require(set(meta._fieldnames) == META_FIELDS, "export_meta fields differ from observed SCREEN4 schema")
    require(matlab_text(meta.schema, "export_meta.schema") == "CM18_EVENT_EXPORT_META_V1",
            f"{sid}: unexpected export_meta schema")
    require(matlab_text(meta.scene_id, "export_meta.scene_id") == sid
            and matlab_text(meta.split, "export_meta.split") == split,
            f"{sid}: export_meta identity mismatch")
    require(int(number(meta.event_count, "event_count")) == n
            and int(number(meta.qualified, "qualified")) == 1
            and matlab_text(meta.status, "status") == "PASS", f"{sid}: export_meta is not qualified")
    require(np.asarray(meta.failure_reasons).size == 0, f"{sid}: failure_reasons must be empty on PASS")

    tol = mat_struct(meta.tolerances, "tolerances")
    require(set(tol._fieldnames) == set(EXPECTED_TOLERANCES), "export tolerance fields differ from SCREEN4 schema")
    for name, expected in EXPECTED_TOLERANCES.items():
        require(number(getattr(tol, name), name) == expected, f"{sid}: unexpected {name} tolerance")
    label_max = number(meta.max_abs_label_delta_vs_h5_rad_s2, "max_abs_label_delta_vs_h5_rad_s2")
    label_axes = vector(meta.max_abs_label_delta_by_axis_rad_s2, 3, "max_abs_label_delta_by_axis_rad_s2")
    torque = number(meta.requested_torque_vs_nominal_minus_applied_max_abs_Nm,
                    "requested_torque_vs_nominal_minus_applied_max_abs_Nm")
    residual = number(meta.true_dynamics_equation_residual_max_abs_Nm,
                      "true_dynamics_equation_residual_max_abs_Nm")
    require(label_max <= EXPECTED_TOLERANCES["label_vs_h5_max_abs_rad_s2"]
            and np.max(label_axes) <= EXPECTED_TOLERANCES["label_vs_h5_max_abs_rad_s2"],
            f"{sid}: label-vs-H5 closure exceeds 1e-8 rad/s^2")
    require(abs(label_max - float(label_axes.max())) <= 1e-12,
            f"{sid}: label max and per-axis maxima are inconsistent")
    require(torque <= EXPECTED_TOLERANCES["torque_request_closure_max_abs_Nm"],
            f"{sid}: requested torque closure exceeds 1e-8 N m")
    require(residual <= EXPECTED_TOLERANCES["true_dynamics_equation_residual_max_abs_Nm"],
            f"{sid}: linear equation residual exceeds 1e-12 N m")

    cross = mat_struct(meta.physical_feature_crosscheck, "physical_feature_crosscheck")
    cross_names = ("omega_B_max_abs", "alpha_BS_max_abs", "thrust_over_mass_max_abs")
    cross_tols = ("omega_max_abs", "alpha_BS_max_abs_rad_s2", "thrust_over_mass_max_abs_m_s2")
    feature_checks: dict[str, float] = {}
    for name, tol_name in zip(cross_names, cross_tols):
        value = number(getattr(cross, name), name)
        require(value <= EXPECTED_TOLERANCES[tol_name], f"{sid}: {name} exceeds its recorded tolerance")
        feature_checks[name] = value

    phase_summary = np.asarray(meta.phase_summary).reshape(-1)
    require(len(phase_summary) == 6, f"{sid}: phase_summary must have six rows")
    actual_phase_counts = np.bincount(p1.astype(np.int64), minlength=6)
    summary_counts: dict[str, int] = {}
    phase_rms: dict[str, list[float] | None] = {}
    phase_label_max: list[float] = []
    phase_label_axes: list[np.ndarray] = []
    for code, item in enumerate(phase_summary):
        require(hasattr(item, "_fieldnames"), f"{sid}: phase_summary entry is not a struct")
        require(set(item._fieldnames) == {"phase_code", "phase", "event_count", "max_abs_label_delta_rad_s2",
                "max_abs_label_delta_by_axis_rad_s2", "axis_rms_label_rad_s2"},
                f"{sid}: phase_summary fields differ from SCREEN4 schema")
        name = matlab_text(item.phase, f"phase_summary[{code}].phase")
        count = int(number(item.event_count, f"phase_summary[{code}].event_count"))
        require(int(number(item.phase_code, f"phase_summary[{code}].phase_code")) == code
                and name == PHASE_NAMES[code] and count == int(actual_phase_counts[code]),
                f"{sid}: phase_summary {code} count/name does not match phase_code array")
        summary_counts[name] = count
        if count:
            mask = p1 == code
            rms = np.sqrt(np.mean(np.square(y[mask], dtype=np.float64), axis=0, dtype=np.float64))
            meta_rms = vector(item.axis_rms_label_rad_s2, 3, f"phase {name} axis RMS")
            require(np.allclose(rms, meta_rms, rtol=1e-12, atol=1e-10),
                    f"{sid}: phase {name} target RMS differs from export_meta")
            phase_rms[name] = rms.tolist()
            phase_delta = number(item.max_abs_label_delta_rad_s2, f"phase {name} max label delta")
            phase_delta_axes = vector(item.max_abs_label_delta_by_axis_rad_s2, 3, f"phase {name} label delta axes")
            require(phase_delta <= EXPECTED_TOLERANCES["label_vs_h5_max_abs_rad_s2"]
                    and np.max(phase_delta_axes) <= EXPECTED_TOLERANCES["label_vs_h5_max_abs_rad_s2"],
                    f"{sid}: phase {name} label-vs-H5 closure exceeds tolerance")
            phase_label_max.append(phase_delta)
            phase_label_axes.append(phase_delta_axes)
        else:
            require(np.isnan(np.asarray(item.axis_rms_label_rad_s2, dtype=np.float64)).all()
                    and np.isnan(np.asarray(item.max_abs_label_delta_rad_s2, dtype=np.float64)).all()
                    and np.isnan(np.asarray(item.max_abs_label_delta_by_axis_rad_s2, dtype=np.float64)).all(),
                    f"{sid}: empty phase summary must use NaN statistics")
            phase_rms[name] = None
    meta_rms = vector(meta.axis_rms_label_rad_s2, 3, "axis_rms_label_rad_s2")
    actual_rms = np.sqrt(np.mean(np.square(y, dtype=np.float64), axis=0, dtype=np.float64))
    require(np.allclose(actual_rms, meta_rms, rtol=1e-12, atol=1e-10),
            f"{sid}: full-scene target RMS differs from export_meta")
    require(abs(max(phase_label_max, default=0.0) - label_max) <= 1e-12
            and np.allclose(np.max(np.stack(phase_label_axes), axis=0) if phase_label_axes else np.zeros(3),
                            label_axes, rtol=0, atol=1e-12),
            f"{sid}: phase label closure summaries do not roll up to scene totals")

    result: dict[str, Any] = {
        "scene_id": sid, "split": split, "cache_path": row["cache_path"],
        "cache_bytes": actual_size, "cache_sha256_actual": actual_sha,
        "cache_sha256_matches_manifest": True, "input_identity_matches_INPUT_MANIFEST": True,
        "X18_shape": list(x.shape), "target_raw_shape": list(y.shape),
        "event_time_s_shape": list(t.shape), "phase_code_shape": list(phase.shape),
        "plant_index_shape": list(idx.shape), "all_required_arrays_finite": True,
        "event_count": n, "event_time_s_first": float(t1[0]), "event_time_s_last": float(t1[-1]),
        "max_time_alignment_error_s": time_error,
        "phase_event_counts": summary_counts,
        "target_axis_rms_rad_s2_actual": actual_rms.tolist(), "phase_target_axis_rms_rad_s2_actual": phase_rms,
        "label_vs_h5_max_abs_rad_s2_metadata": label_max,
        "label_vs_h5_max_abs_by_axis_rad_s2_metadata": label_axes.tolist(),
        "label_vs_h5_tolerance_rad_s2": EXPECTED_TOLERANCES["label_vs_h5_max_abs_rad_s2"],
        "requested_torque_closure_max_abs_Nm_metadata": torque,
        "requested_torque_closure_tolerance_Nm": EXPECTED_TOLERANCES["torque_request_closure_max_abs_Nm"],
        "true_dynamics_equation_residual_max_abs_Nm_metadata": residual,
        "true_dynamics_equation_residual_tolerance_Nm": EXPECTED_TOLERANCES["true_dynamics_equation_residual_max_abs_Nm"],
        "physical_feature_crosscheck_metadata": feature_checks,
        "target_abs_exceedance_counts_by_axis_dmax_45_45_4p7124":
            np.count_nonzero(np.abs(y) > DMAX, axis=0).astype(int).tolist(),
        "target_abs_exceedance_rates_by_axis_dmax_45_45_4p7124":
            (np.count_nonzero(np.abs(y) > DMAX, axis=0) / n).tolist(),
    }
    if split == "TRAIN":
        fit_x, fit_y = x[0::5], y[0::5]
        require(len(fit_x) == 400, f"{sid}: TRAIN offset 0,5,...,1995 must yield 400 rows")
        result["_fit_x"], result["_fit_y"] = fit_x, fit_y
    result["_target"], result["_phase_counts"] = y, actual_phase_counts
    return result


def aggregate(results: list[dict[str, Any]], mode: str, manifest_sha: str,
              input_sha: str, screen_sha: str, source_hashes: dict[str, str]) -> dict[str, Any]:
    passed = [r for r in results if "error" not in r]
    splits = ("TRAIN", "VAL")
    target_summary: dict[str, Any] = {}
    phase_totals: dict[str, dict[str, int]] = {s: {name: 0 for name in PHASES} for s in splits}
    exceed: dict[str, dict[str, Any]] = {s: {"counts": [0, 0, 0], "events": 0} for s in splits}
    all_targets = {s: [] for s in splits}
    fit_x: list[np.ndarray] = []
    fit_y: list[np.ndarray] = []
    label_max, label_axes = 0.0, np.zeros(3)
    torque_max = residual_max = 0.0
    feature_max = {"omega_B_max_abs": 0.0, "alpha_BS_max_abs": 0.0, "thrust_over_mass_max_abs": 0.0}
    event_totals = {s: 0 for s in splits}
    for r in passed:
        split = r["split"]
        event_totals[split] += r["event_count"]
        all_targets[split].append(r["_target"])
        for name, count in r["phase_event_counts"].items():
            phase_totals[split][name] += count
        exceed[split]["events"] += r["event_count"]
        exceed[split]["counts"] = (np.asarray(exceed[split]["counts"]) +
                                    np.asarray(r["target_abs_exceedance_counts_by_axis_dmax_45_45_4p7124"])).tolist()
        label_max = max(label_max, r["label_vs_h5_max_abs_rad_s2_metadata"])
        label_axes = np.maximum(label_axes, r["label_vs_h5_max_abs_by_axis_rad_s2_metadata"])
        torque_max = max(torque_max, r["requested_torque_closure_max_abs_Nm_metadata"])
        residual_max = max(residual_max, r["true_dynamics_equation_residual_max_abs_Nm_metadata"])
        for key, value in r["physical_feature_crosscheck_metadata"].items():
            feature_max[key] = max(feature_max[key], value)
        if split == "TRAIN" and "_fit_x" in r:
            fit_x.append(r.pop("_fit_x"))
            fit_y.append(r.pop("_fit_y"))
    for split in splits:
        if all_targets[split]:
            y = np.concatenate(all_targets[split], axis=0)
            target_summary[split] = {
                "events": len(y),
                "axis_rms_rad_s2_all_events": np.sqrt(np.mean(np.square(y, dtype=np.float64), axis=0)).tolist(),
                "axis_min_rad_s2": np.min(y, axis=0).tolist(), "axis_max_rad_s2": np.max(y, axis=0).tolist(),
            }
    target_summary["dmax_diagnostic"] = {
        "dmax_rad_s2": DMAX.tolist(),
        "meaning": "absolute label exceedance only; diagnostic, no clipping or limit change",
        "by_split": {s: {"events": exceed[s]["events"], "counts_by_axis": exceed[s]["counts"],
                          "rates_by_axis": (np.asarray(exceed[s]["counts"], dtype=float) /
                                            max(exceed[s]["events"], 1)).tolist()} for s in splits},
    }
    training_scale: dict[str, Any] = {}
    if fit_x and fit_y:
        xs, ys = np.concatenate(fit_x, axis=0), np.concatenate(fit_y, axis=0)
        mean = np.mean(xs, axis=0, dtype=np.float64)
        raw_std = np.std(xs, axis=0, dtype=np.float64, ddof=0)
        std = np.maximum(raw_std, 1e-6)
        target_rms = np.sqrt(np.mean(np.square(ys, dtype=np.float64), axis=0, dtype=np.float64))
        training_scale = {
            "source": "TRAIN only, event row offsets 0,5,...,1995; float64; input std ddof=0",
            "fit_rows": int(len(xs)), "input_mean_float64": mean.tolist(),
            "input_std_raw_float64": raw_std.tolist(), "input_std_after_1e-6_floor_float64": std.tolist(),
            "target_axis_rms_rad_s2_float64": target_rms.tolist(),
            "target_axis_rms_all_strictly_positive": bool(np.all(target_rms > 0)),
            "zero_morphology_output_scale_rad_s2": target_rms.tolist(),
            "zero_morphology_basis": "[z/2,u]=0 implies model physical output exactly [0,0,0] rad/s^2; axis RMS is its physical output multiplier",
        }
        require(np.all(target_rms > 0), "TRAIN-only target axis RMS must be strictly positive")
    clean_results = [{k: v for k, v in r.items() if not k.startswith("_")} for r in results]
    failures = [r for r in clean_results if r.get("audit_status") == "FAIL"]
    return {
        "schema": "CM18_A1_INDEPENDENT_DATA_AUDIT_V1", "audit_mode": mode,
        "status": "PASS" if not failures and len(passed) == len(results) else "FAIL",
        "dataset_manifest_sha256": manifest_sha, "input_manifest_sha256_actual": input_sha,
        "screen4_manifest_sha256_actual": screen_sha,
        "dataset_counts": {"scenes": len(results), "passed_cache_audits": len(passed),
                            "failed_cache_audits": len(failures), "event_count_by_split": event_totals,
                            "phase_counts_by_split": phase_totals},
        "target_summary": target_summary, "train_only_normalizer_preview": training_scale,
        "closure_summary": {
            "label_vs_h5_max_abs_rad_s2_metadata": label_max,
            "label_vs_h5_max_abs_by_axis_rad_s2_metadata": label_axes.tolist(),
            "requested_torque_closure_max_abs_Nm_metadata": torque_max,
            "true_dynamics_equation_residual_max_abs_Nm_metadata": residual_max,
            "physical_feature_crosscheck_maxima_metadata": feature_max,
            "interpretation": "These are export_meta closure claims audited against recorded tolerances; this script does not reopen H5/raw inputs or independently prove physical dynamics. The true-dynamics residual is the same linear solve residual, not independent physical evidence.",
        },
        "legacy_B_source_gap": {"disclosed": True,
            "note": "Original B-data production source is unavailable. This is current-equation relabeling of behavior data, not new acquisition or independent testing."},
        "source_sha256": source_hashes,
        "execution_scope": {"cache_reads": len(results), "all816_cache_reads": len(results) if mode == "ALL816" else 0,
                            "screen4_cache_reads": len(results) if mode == "SCREEN4_SELF_CHECK" else len(SCREEN4_IDS),
                            "raw_or_h5_numeric_data_read": False, "TEST_accessed": False,
                            "optimizer_steps": 0, "training_runs": 0, "Plant_calls": 0},
        "scenes": clean_results,
    }


def hash_sources(root: Path) -> dict[str, str]:
    rels = {
        "cache_reader_cm18_v1.py": "experiments/attitude_cm18_a1_20261024/cache_reader_cm18_v1.py",
        "model_cm18_v1.py": "experiments/attitude_cm18_a1_20261024/model_cm18_v1.py",
        "torch_model_cm18_v1.py": "experiments/attitude_cm18_a1_20261024/torch_model_cm18_v1.py",
    }
    return {name: sha256(safe_repo_file(root, rel)) for name, rel in rels.items()}


def write_exclusive(root: Path, relative: Path, obj: dict[str, Any]) -> Path:
    out = safe_repo_file(root, relative.as_posix(), strict=False)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        with out.open("x", encoding="utf-8", newline="\n") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.write("\n")
    except FileExistsError as exc:
        raise AuditError(f"refusing to overwrite existing audit output: {relative.as_posix()}") from exc
    return out


def run(root: Path, screen4_only: bool) -> tuple[dict[str, Any], Path]:
    RUN_STATE.update(stage="manifest_gate", cache_reads=0, cache_audit_attempts=0)
    root = root.resolve(strict=True)
    mode = "SCREEN4_SELF_CHECK" if screen4_only else "ALL816"
    manifest_rel = SCREEN4_REL if screen4_only else ALL816_REL
    manifest_path = safe_repo_file(root, manifest_rel.as_posix())
    manifest, manifest_sha = json_file(manifest_path)
    # All manifest completeness gates run before any cache is opened.
    rows = validate_manifest_rows(manifest, "SCREEN4" if screen4_only else "ALL816")
    if not screen4_only:
        require(len(rows) == 816 and sum(r["split"] == "TRAIN" for r in rows) == 768
                and sum(r["split"] == "VAL" for r in rows) == 48,
                "ALL816 manifest is not the final 768 TRAIN + 48 VAL dataset")
    inputs, input_by_id = input_manifest(root)
    screen_path = safe_repo_file(root, SCREEN4_REL.as_posix())
    screen_manifest, screen_sha = json_file(screen_path)
    require(screen_sha == SCREEN4_SHA, "SCREEN4 manifest SHA256 differs from pinned value")
    screen_rows_list = validate_manifest_rows(screen_manifest, "SCREEN4")
    screen_rows = {r["scene_id"]: r for r in screen_rows_list}
    require(set(screen_rows) == SCREEN4_IDS, "SCREEN4 manifest does not match approved scene set")
    validate_cache_references(root, screen_rows_list, "SCREEN4", input_by_id, {})
    validate_cache_references(root, rows, "SCREEN4" if screen4_only else "ALL816", input_by_id, screen_rows)

    RUN_STATE["stage"] = "source_hashes"
    source_hashes = hash_sources(root)
    RUN_STATE["stage"] = "cache_audit"
    results: list[dict[str, Any]] = []
    for row in rows:
        RUN_STATE["cache_audit_attempts"] += 1
        try:
            results.append(audit_scene(root, row, input_by_id[row["scene_id"]]))
        except Exception as exc:
            results.append({"scene_id": row.get("scene_id"), "split": row.get("split"),
                            "audit_status": "FAIL", "error": f"{type(exc).__name__}: {exc}"})
    RUN_STATE["stage"] = "aggregate"
    report = aggregate(results, mode, manifest_sha, inputs["_sha256"], screen_sha, source_hashes)
    output_rel = (PREP / "SCREEN4_INDEPENDENT_AUDIT_SELF_CHECK_v1.json" if screen4_only
                  else PREP / "ROOT_ALL816_INDEPENDENT_AUDIT_v1.json")
    RUN_STATE["stage"] = "write_output"
    output = write_exclusive(root, output_rel, report)
    RUN_STATE["stage"] = "complete"
    return report, output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--screen4-self-check", action="store_true",
                        help="read only the four pinned SCREEN4 caches and write a separate self-check report")
    args = parser.parse_args()
    try:
        report, output = run(args.repo_root, args.screen4_self_check)
    except Exception as exc:
        print(json.dumps({"status": "BLOCKED", "stage": RUN_STATE["stage"],
                          "error": f"{type(exc).__name__}: {exc}",
                          "cache_reads": RUN_STATE["cache_reads"],
                          "cache_audit_attempts": RUN_STATE["cache_audit_attempts"],
                          "cache_read_count_semantics": "cache_reads counts cache files whose SHA256 stream completed; see stage and attempts for partial audit failures",
                          "optimizer_steps": 0, "training_runs": 0, "Plant_calls": 0},
                         ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps({"status": report["status"], "audit_mode": report["audit_mode"],
                      "output": output.relative_to(args.repo_root.resolve()).as_posix(),
                      "scenes": report["dataset_counts"]["scenes"],
                      "failed_cache_audits": report["dataset_counts"]["failed_cache_audits"],
                      "optimizer_steps": 0, "training_runs": 0, "Plant_calls": 0}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

