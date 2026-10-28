"""Independent identity and NumPy arithmetic audit for the C5 VAL48 C* relabel.

This checks saved event arrays, source/cache identities and arithmetic consistency.
It does not independently reconstruct physical E0/G or rerun the MATLAB allocator.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import sys
from pathlib import Path

import h5py
import numpy as np
from scipy.io import loadmat, savemat


ROOT = Path(__file__).resolve().parents[2]
V3_PATH = ROOT / "reports/attitude_cm18_datarepair_20261024/c5_val48_c5_teacher_v3/C5_VAL48_EVENT_CACHE_MANIFEST_v3.json"
V3_SHA = "3e72f4726219cfd0e89476c70d24796a06c8f8447d4064cfdc471433a863a501"
CANDIDATE_PATH = ROOT / "reports/attitude_position_context_probe_20261024/C5_MATCHED_VAL_REUSE_CANDIDATES_v1.json"
CANDIDATE_SHA = "80ef7a37cb0fff237086ccc138772c71494cacd50a916ed2dba4037d4f833494"
RELABELER_PATH = ROOT / "experiments/attitude_position_context_probe_20261024/c5_val48_cstar_v1/relabel_c5_val48_cstar_v1.m"
RELABELER_SHA = "D41DC283ED5277B28A4F7A022B7550DF5B1F1674E4E2D729DE9843C43101120B"
BASE = ROOT / "reports/attitude_position_context_probe_20261024/c5_val48_cstar_v1/attempt_03"
RELABEL_MANIFEST = BASE / "C5_VAL48_CSTAR_RELABEL_v1.json"
OUTPUT = BASE / "ROOT_C5_VAL48_CSTAR_NUMPY_AUDIT_v1.json"
N = 1999
DT = 0.001
TOL = 1e-8
PARITY_TOL = 1e-10
TIME_TOL = 1e-12


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def resolve_path(value: str | Path) -> Path:
    p = Path(str(value))
    return p if p.is_absolute() else (ROOT / p).resolve()


def same_path(a: str | Path, b: str | Path) -> bool:
    return os.path.normcase(str(resolve_path(a))) == os.path.normcase(str(resolve_path(b)))


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def verify_file(path: str | Path, expected_sha: str, label: str, expected_bytes: int | None = None) -> Path:
    p = resolve_path(path)
    if not p.is_file():
        raise FileNotFoundError(f"{label}: {p}")
    actual = sha256(p)
    if actual.lower() != str(expected_sha).lower():
        raise ValueError(f"{label}: SHA mismatch at {p}: {actual}")
    if expected_bytes is not None and p.stat().st_size != int(expected_bytes):
        raise ValueError(f"{label}: byte count mismatch at {p}")
    return p


def field(obj, name: str):
    if isinstance(obj, dict):
        return obj[name]
    return getattr(obj, name)


def mat_text(value) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8").rstrip("\x00")
    if isinstance(value, str):
        return value.rstrip("\x00")
    a = np.asarray(value)
    if a.dtype.kind == "U":
        return "".join(a.reshape(-1).tolist()).rstrip("\x00")
    if a.dtype.kind == "S":
        return b"".join(a.reshape(-1).tolist()).decode("utf-8").rstrip("\x00")
    if a.size == 1:
        item = a.reshape(-1)[0]
        return item.decode("utf-8").rstrip("\x00") if isinstance(item, bytes) else str(item)
    return str(value)


def scalar_bool(value) -> bool:
    a = np.asarray(value)
    if a.size != 1:
        raise ValueError(f"Expected scalar logical, got shape {a.shape}")
    return bool(a.reshape(-1)[0])


def max_abs(value: np.ndarray) -> float:
    a = np.asarray(value, dtype=np.float64)
    if not a.size or not np.isfinite(a).all():
        raise ValueError("Arithmetic array is empty or nonfinite")
    return float(np.max(np.abs(a)))


def check_arrays(
    flat_g,
    e0,
    cstar,
    raw,
    action,
    beta,
    idx,
    stored_solve_residual,
    stored_linear,
    full,
    stored_full_minus,
    dmax,
    beta_rise_s,
):
    flat_g = np.asarray(flat_g, dtype=np.float64)
    e0 = np.asarray(e0, dtype=np.float64)
    cstar = np.asarray(cstar, dtype=np.float64)
    raw = np.asarray(raw, dtype=np.float64)
    action = np.asarray(action, dtype=np.float64)
    beta = np.asarray(beta, dtype=np.float64).reshape(-1, 1)
    idx = np.asarray(idx, dtype=np.float64).reshape(-1)
    stored_solve_residual = np.asarray(stored_solve_residual, dtype=np.float64)
    stored_linear = np.asarray(stored_linear, dtype=np.float64)
    full = np.asarray(full, dtype=np.float64)
    stored_full_minus = np.asarray(stored_full_minus, dtype=np.float64)
    dmax = np.asarray(dmax, dtype=np.float64).reshape(1, 3)

    expected_idx = np.arange(11, 19992, 10, dtype=np.int64)
    if flat_g.shape != (N, 9) or e0.shape != (N, 3) or cstar.shape != (N, 3):
        raise ValueError("Unexpected G/E0/cstar event shape")
    if raw.shape != (N, 3) or action.shape != (N, 3) or full.shape != (N, 3):
        raise ValueError("Unexpected raw/action/full-allocator event shape")
    if any(a.shape != (N, 3) for a in (stored_solve_residual, stored_linear, stored_full_minus)):
        raise ValueError("Unexpected stored residual shape")
    if beta.shape != (N, 1) or not np.array_equal(idx, expected_idx):
        raise ValueError("Unexpected beta shape or canonical event index sequence")
    arrays = (flat_g, e0, cstar, raw, action, beta, stored_solve_residual, stored_linear, full, stored_full_minus)
    if not all(np.isfinite(a).all() for a in arrays) or not np.isfinite(dmax).all():
        raise ValueError("Nonfinite saved event arithmetic")
    if np.any(beta <= 0.0) or not np.isfinite(beta_rise_s) or beta_rise_s <= 0:
        raise ValueError("Canonical VAL events must have positive beta and rise time")

    # MATLAB stores each G row by reshape(G.',1,9); this is row-major flattening.
    g = flat_g.reshape(N, 3, 3, order="C")
    solved = np.linalg.solve(g, e0)
    beta_expected = np.minimum(idx[:, None] * DT / beta_rise_s, 1.0)
    clipped = np.clip(raw, -dmax, dmax)
    linear = e0 - np.einsum("nij,nj->ni", g, action)
    full_minus_linear = full - linear
    clip_mask = np.abs(raw - clipped) > 1e-12
    errors = {
        "max_abs_cstar_solve_delta": max_abs(cstar - solved),
        "max_abs_E0_minus_G_cstar": max_abs(e0 - np.einsum("nij,nj->ni", g, cstar)),
        "max_abs_stored_solve_residual_delta": max_abs(stored_solve_residual - (e0 - np.einsum("nij,nj->ni", g, cstar))),
        "max_abs_beta_formula_delta": max_abs(beta - beta_expected),
        "max_abs_beta_raw_minus_cstar": max_abs(beta * raw - cstar),
        "max_abs_clipped_action_delta": max_abs(action - beta * clipped),
        "max_abs_E0_minus_G_action_delta": max_abs(linear - stored_linear),
        "max_abs_full_minus_linear_delta": max_abs(full_minus_linear - stored_full_minus),
    }
    return errors, clip_mask, g


def read_cache(path: Path):
    loaded = loadmat(path, variable_names=["cache"], squeeze_me=True, struct_as_record=False)
    if "cache" not in loaded:
        raise ValueError(f"MAT file lacks top-level cache variable: {path}")
    return loaded["cache"]


def audit_scene(scene: dict, v3_row: dict, candidate_row: dict, dmax: np.ndarray, beta_rise: float) -> dict:
    scene_id = scene["scene_id"]
    candidate = candidate_row["C5_candidate"]
    if scene.get("split") != "VAL" or scene.get("status") != "PASS" or not scene.get("qualified"):
        raise ValueError(f"{scene_id}: relabel manifest row is not PASS/qualified VAL")
    if scene.get("training_eligible") is not False:
        raise ValueError(f"{scene_id}: VAL scene must remain training_eligible=false")
    if not scene_id.startswith("DL1018_VAL_") or candidate_row.get("split") != "VAL":
        raise ValueError(f"{scene_id}: noncanonical VAL identity")
    if scene.get("source_classification") != v3_row["source_classification"]:
        raise ValueError(f"{scene_id}: source classification mismatch")
    if bool(scene.get("reused_screen")) != bool(v3_row["reused_screen"]):
        raise ValueError(f"{scene_id}: reused-screen flag mismatch")

    raw_path = verify_file(scene["raw_path"], scene["raw_sha256"], f"{scene_id} candidate raw", candidate_row["C5_candidate"].get("raw_bytes"))
    start_path = verify_file(scene["run_start_path"], scene["run_start_sha256"], f"{scene_id} run_start")
    status_path = verify_file(scene["run_status_path"], scene["run_status_sha256"], f"{scene_id} run_status")
    old_cache_path = verify_file(scene["old_cache_path"], scene["old_cache_sha256"], f"{scene_id} old cache", v3_row["cache_bytes"])
    new_cache_path = verify_file(scene["cache_path"], scene["cache_sha256"], f"{scene_id} C* cache", scene["cache_bytes"])

    if not same_path(scene["raw_path"], candidate["raw_path"]) or scene["raw_sha256"].lower() != candidate["raw_sha256"].lower():
        raise ValueError(f"{scene_id}: candidate raw identity mismatch")
    if not same_path(scene["run_start_path"], candidate["run_start_path"]) or scene["run_start_sha256"].lower() != candidate["run_start_sha256"].lower():
        raise ValueError(f"{scene_id}: candidate run_start identity mismatch")
    if not same_path(scene["run_status_path"], candidate["run_status_path"]) or scene["run_status_sha256"].lower() != candidate["run_status_sha256"].lower():
        raise ValueError(f"{scene_id}: candidate run_status identity mismatch")
    if not same_path(scene["old_cache_path"], v3_row["cache_path_relative"]) or scene["old_cache_sha256"].lower() != v3_row["cache_sha256"].lower():
        raise ValueError(f"{scene_id}: V3 old cache identity mismatch")
    if int(scene["event_count"]) != N or int(v3_row["attitude_event_count"]) != N or int(candidate_row["C5_candidate"]["parent_audit_event_count"]) != 1968:
        raise ValueError(f"{scene_id}: attitude or parent position event count mismatch")

    cache = read_cache(new_cache_path)
    if mat_text(field(cache, "schema")) != "CM18_C5_VAL48_CSTAR_EVENT_CACHE_V1":
        raise ValueError(f"{scene_id}: unexpected new MAT cache schema")
    ident = field(cache, "identity")
    events = field(cache, "events")
    if mat_text(field(ident, "schema")) != "CM18_C5_VAL48_CSTAR_CACHE_IDENTITY_V1":
        raise ValueError(f"{scene_id}: unexpected cache identity schema")
    if mat_text(field(events, "schema")) != "CM18_C5_VAL48_CSTAR_EVENTS_V1":
        raise ValueError(f"{scene_id}: unexpected cache events schema")

    identity_pairs = {
        "scene_id": scene_id,
        "split": "VAL",
        "candidate_manifest_sha256": CANDIDATE_SHA,
        "C5_event_manifest_sha256": V3_SHA,
        "candidate_raw_sha256": scene["raw_sha256"],
        "candidate_run_start_sha256": scene["run_start_sha256"],
        "candidate_run_status_sha256": scene["run_status_sha256"],
        "old_cache_sha256": scene["old_cache_sha256"],
        "C5_snapshot_sha256": scene["C5_snapshot_sha256"],
        "C5_source_binding_sha256": scene["C5_source_binding_sha256"],
        "extractor_sha256": scene["extractor_sha256"],
    }
    if scalar_bool(field(ident, "training_eligible")):
        raise ValueError(f"{scene_id}: cache identity must be validation-only")
    for name, expected in identity_pairs.items():
        if mat_text(field(ident, name)) != str(expected):
            raise ValueError(f"{scene_id}: cache identity field {name} differs")

    def arr(name, dtype=np.float64):
        return np.asarray(field(events, name), dtype=dtype)

    idx = arr("plant_index").reshape(-1).astype(np.int64)
    event_idx = arr("event_index").reshape(-1).astype(np.int64)
    event_time = arr("event_time_s").reshape(-1)
    phase = arr("phase_code").reshape(-1).astype(np.int64)
    x18 = arr("X18")
    beta = arr("beta").reshape(-1)
    if idx.shape != (N,) or event_idx.shape != (N,) or event_time.shape != (N,) or phase.shape != (N,):
        raise ValueError(f"{scene_id}: event metadata does not contain 1999 samples")
    if not np.array_equal(event_idx, np.arange(1, N + 1)) or not np.array_equal(idx, np.arange(11, 19992, 10)):
        raise ValueError(f"{scene_id}: event index/time order is not canonical")
    if x18.shape != (N, 18) or not np.isfinite(x18).all():
        raise ValueError(f"{scene_id}: X18 is not finite 1999x18")
    if not np.isfinite(event_time).all() or not np.isfinite(phase).all() or not np.isfinite(beta).all():
        raise ValueError(f"{scene_id}: event metadata contains nonfinite values")

    old = read_cache(old_cache_path)
    old_ident = field(old, "identity")
    old_events = field(old, "events")
    if mat_text(field(old, "schema")) != "CM18_VAL_C5_EVENT_CACHE_V2":
        raise ValueError(f"{scene_id}: unexpected legacy C5 event cache schema")
    if mat_text(field(old_ident, "scene_id")) != scene_id or mat_text(field(old_ident, "split")) != "VAL":
        raise ValueError(f"{scene_id}: old cache identity mismatch")
    if scalar_bool(field(old_ident, "training_eligible")):
        raise ValueError(f"{scene_id}: old C5 VAL cache unexpectedly training-eligible")
    old_x18 = np.asarray(field(old_events, "X18"), dtype=np.float64)
    old_target = np.asarray(field(old_events, "target_raw"), dtype=np.float64)
    old_idx = np.asarray(field(old_events, "plant_index"), dtype=np.int64).reshape(-1)
    old_event_idx = np.asarray(field(old_events, "event_index"), dtype=np.int64).reshape(-1)
    old_time = np.asarray(field(old_events, "event_time_s"), dtype=np.float64).reshape(-1)
    old_phase = np.asarray(field(old_events, "phase_code"), dtype=np.int64).reshape(-1)
    if old_x18.shape != (N, 18) or old_target.shape != (N, 3):
        raise ValueError(f"{scene_id}: old cache event array shapes changed")
    parity_x = max_abs(x18 - old_x18)
    parity_target = max_abs(arr("target_behavior_residual_rad_s2") - old_target)
    parity_time = max_abs(event_time - old_time)
    if max(parity_x, parity_target) > PARITY_TOL or parity_time > TIME_TOL:
        raise ValueError(f"{scene_id}: new events do not preserve old-cache X18/behavior/time parity")
    if not np.array_equal(idx, old_idx) or not np.array_equal(event_idx, old_event_idx) or not np.array_equal(phase, old_phase):
        raise ValueError(f"{scene_id}: old/new event metadata differs")

    with h5py.File(raw_path, "r") as f:
        raw_time = np.asarray(f["scene/time"], dtype=np.float64).reshape(-1)
        flags = np.asarray(f["log/attitude_event_flag"]).reshape(-1).astype(bool)
    if raw_time.shape != (20001,) or flags.shape != (20000,):
        raise ValueError(f"{scene_id}: raw 20s time/attitude event shapes changed")
    raw_idx = np.flatnonzero(flags).astype(np.int64) + 1
    if not np.array_equal(raw_idx, idx):
        raise ValueError(f"{scene_id}: cached events differ from raw attitude_event_flag")
    raw_event_time = raw_time[idx - 1]
    raw_time_delta = max_abs(event_time - raw_event_time)
    if raw_time_delta > TIME_TOL or max_abs(np.diff(raw_time) - DT) > TIME_TOL:
        raise ValueError(f"{scene_id}: cached event time does not match raw 1ms timebase")

    needed = (
        "E0_rad_s2", "G_row_major", "target_applied_acceleration_rad_s2",
        "target_raw_output_rad_s2", "target_after_clip_beta_rad_s2",
        "ideal_linear_solve_residual_rad_s2", "postclip_linear_residual_rad_s2",
        "postclip_full_allocator_residual_rad_s2", "full_allocator_minus_linear_residual_rad_s2",
        "target_raw_output_reachable", "output_clip_mask", "beta_zero_unreachable_mask",
    )
    arrays = {name: arr(name) for name in needed}
    errors, clip_mask, _ = check_arrays(
        flat_g=arrays["G_row_major"],
        e0=arrays["E0_rad_s2"],
        cstar=arrays["target_applied_acceleration_rad_s2"],
        raw=arrays["target_raw_output_rad_s2"],
        action=arrays["target_after_clip_beta_rad_s2"],
        beta=beta,
        idx=idx,
        stored_solve_residual=arrays["ideal_linear_solve_residual_rad_s2"],
        stored_linear=arrays["postclip_linear_residual_rad_s2"],
        full=arrays["postclip_full_allocator_residual_rad_s2"],
        stored_full_minus=arrays["full_allocator_minus_linear_residual_rad_s2"],
        dmax=dmax,
        beta_rise_s=beta_rise,
    )
    if max(errors.values()) >= TOL:
        raise ValueError(f"{scene_id}: NumPy arithmetic mismatch: {errors}")
    raw_reachable = arrays["target_raw_output_reachable"].astype(bool)
    zero_unreachable = arrays["beta_zero_unreachable_mask"].astype(bool)
    saved_clip = arrays["output_clip_mask"].astype(bool)
    if raw_reachable.shape != (N, 3) or zero_unreachable.shape != (N, 3) or saved_clip.shape != (N, 3):
        raise ValueError(f"{scene_id}: target mask shape mismatch")
    if not raw_reachable.all() or zero_unreachable.any() or not np.array_equal(saved_clip, clip_mask):
        raise ValueError(f"{scene_id}: beta-zero reachability or output clip mask mismatch")

    phase_names = ("STATIC", "PRE", "EXTEND", "HOLD", "RETRACT", "RECOVERY")
    phase_counts = {name: int(np.count_nonzero(phase == code)) for code, name in enumerate(phase_names)}
    if sum(phase_counts.values()) != N:
        raise ValueError(f"{scene_id}: phase grouping does not cover 1999 events")
    saved_phase_counts = scene["phase_event_count"]
    if any(int(saved_phase_counts[name]) != phase_counts[name] for name in phase_names):
        raise ValueError(f"{scene_id}: phase summary differs from event phase codes")

    clip_by_axis = np.count_nonzero(clip_mask, axis=0).astype(int)
    return {
        "scene_id": scene_id,
        "status": "PASS",
        "event_count": N,
        "raw_sha256": scene["raw_sha256"],
        "run_start_sha256": scene["run_start_sha256"],
        "run_status_sha256": scene["run_status_sha256"],
        "old_cache_sha256": scene["old_cache_sha256"],
        "new_cache_sha256": scene["cache_sha256"],
        "x18_old_cache_max_abs_delta": parity_x,
        "old_behavior_target_max_abs_delta": parity_target,
        "event_time_old_and_raw_max_abs_delta_s": max(parity_time, raw_time_delta),
        "clip_active_by_axis": clip_by_axis.tolist(),
        "clip_active_event_count": int(np.count_nonzero(np.any(clip_mask, axis=1))),
        "beta_zero_unreachable_count": int(np.count_nonzero(zero_unreachable)),
        "max_arithmetic_errors": errors,
        "phase_event_count": phase_counts,
    }


def run_audit() -> dict:
    for path, expected, label in (
        (V3_PATH, V3_SHA, "V3 source manifest"),
        (CANDIDATE_PATH, CANDIDATE_SHA, "candidate manifest"),
        (RELABELER_PATH, RELABELER_SHA, "frozen VAL relabeler"),
    ):
        verify_file(path, expected, label)
    manifest = read_json(RELABEL_MANIFEST)
    if manifest.get("schema") != "CM18_C5_VAL48_CSTAR_RELABEL_MANIFEST_V1" or manifest.get("status") != "PASS":
        raise ValueError("C* VAL48 relabel manifest is not PASS")
    if manifest.get("training_eligible") is not False or manifest.get("TEST_accessed") is not False:
        raise ValueError("C* VAL48 must remain validation-only and TEST-free")
    if manifest.get("source_manifest_sha256") != V3_SHA or manifest.get("candidate_manifest_sha256") != CANDIDATE_SHA:
        raise ValueError("Relabel input manifest pins changed")
    if manifest.get("entry_sha256", "").lower() != RELABELER_SHA.lower():
        raise ValueError("Relabeler source hash differs from frozen source")
    if not same_path(manifest.get("output_directory", ""), BASE):
        raise ValueError("Relabel output directory is not the isolated attempt_03 location")
    v3 = read_json(V3_PATH)
    candidates = read_json(CANDIDATE_PATH)
    if v3.get("schema") != "C5_MATCHED_VAL48_EVENT_CACHE_MANIFEST_V3" or v3.get("status") != "PASS":
        raise ValueError("Pinned V3 VAL source manifest is not PASS")
    if candidates.get("schema") != "ROOT_C5_MATCHED_VAL_REUSE_CANDIDATES_V1" or candidates.get("status") != "CANDIDATE_METADATA_ONLY_FULL_RAW_CFG_CERTIFICATION_PENDING":
        raise ValueError("Pinned candidate manifest schema/status changed")
    if len(v3.get("scenes", [])) != 48 or len(candidates.get("scenes", [])) != 48 or len(manifest.get("scenes", [])) != 48:
        raise ValueError("Expected exactly 48 rows in all pinned VAL manifests")
    v3_rows = {r["scene_id"]: r for r in v3["scenes"]}
    candidate_rows = {r["scene_id"]: r for r in candidates["scenes"]}
    if len(v3_rows) != 48 or len(candidate_rows) != 48:
        raise ValueError("Duplicate canonical scene IDs in input manifests")
    out_rows = manifest["scenes"]
    scene_ids = [r["scene_id"] for r in out_rows]
    if len(set(scene_ids)) != 48 or scene_ids != [r["scene_id"] for r in v3["scenes"]] or scene_ids != [r["scene_id"] for r in candidates["scenes"]]:
        raise ValueError("Output rows do not preserve canonical VAL48 scene order")
    if not all(sid.startswith("DL1018_VAL_") for sid in scene_ids):
        raise ValueError("Non-VAL canonical identity in output rows")
    summary = manifest.get("summary", {})
    if (
        int(summary.get("scene_count", -1)) != 48
        or int(summary.get("qualified_count", -1)) != 48
        or int(summary.get("failed_count", -1)) != 0
        or int(summary.get("event_count", -1)) != 48 * N
        or int(summary.get("split_counts", {}).get("TRAIN", -1)) != 0
        or int(summary.get("split_counts", {}).get("VAL", -1)) != 48
    ):
        raise ValueError("Relabel manifest summary does not show complete VAL-only coverage")
    dmax = np.asarray(manifest["dmax_rad_s2"], dtype=np.float64).reshape(3)
    beta_rise = float(manifest["beta_rise_time_s"])
    results = [audit_scene(s, v3_rows[s["scene_id"]], candidate_rows[s["scene_id"]], dmax, beta_rise) for s in out_rows]
    beta_zero_unreachable = sum(r["beta_zero_unreachable_count"] for r in results)
    if beta_zero_unreachable != 0:
        raise ValueError(f"VAL C* targets contain {beta_zero_unreachable} unreachable beta-zero components")
    err_max = max(value for r in results for value in r["max_arithmetic_errors"].values())
    if err_max >= TOL:
        raise ValueError(f"Batch arithmetic error exceeds {TOL}: {err_max}")
    clip_axis = np.sum([r["clip_active_by_axis"] for r in results], axis=0).astype(int)
    clip_scenes = sum(bool(r["clip_active_event_count"]) for r in results)
    return {
        "schema": "ROOT_C5_VAL48_CSTAR_NUMPY_AUDIT_V1",
        "status": "PASS",
        "source_manifest_sha256": V3_SHA,
        "candidate_manifest_sha256": CANDIDATE_SHA,
        "relabeler_sha256": RELABELER_SHA,
        "relabel_manifest_sha256": sha256(RELABEL_MANIFEST),
        "scene_count": 48,
        "event_count_per_scene": N,
        "total_event_count": 48 * N,
        "max_arithmetic_error": err_max,
        "clip_active_by_axis": clip_axis.tolist(),
        "clip_active_event_count": sum(r["clip_active_event_count"] for r in results),
        "scenes_with_active_clip": clip_scenes,
        "beta_zero_unreachable_count": sum(r["beta_zero_unreachable_count"] for r in results),
        "scenes": results,
        "scope": "Independent SHA/identity/event-index/time/phase/X18-parity and NumPy arithmetic audit of the exported C* arrays. It does not independently reconstruct raw physical G/E0, simulation_parameters, or the full MATLAB allocator; full-allocator residual is checked only through the stored full-minus-linear identity. VAL remains training_eligible=false.",
        "Plant_calls": 0,
        "optimizer_steps": 0,
        "TEST_accessed": False,
        "audit_source_sha256": sha256(Path(__file__)),
    }


def synthetic_check() -> None:
    g0 = np.array([[2.0, 0.2, 0.0], [-0.1, 1.5, 0.3], [0.4, 0.1, 0.5]])
    g = np.tile(g0, (N, 1, 1))
    e0 = np.tile([100.0, 4.0, 1.0], (N, 1))
    idx = np.arange(11, 19992, 10)
    beta = np.minimum(idx[:, None] * DT / 2.2, 1.0)
    cstar = np.linalg.solve(g, e0)
    raw = cstar / beta
    action = beta * np.clip(raw, -np.array([[45.0, 45.0, 4.7124]]), np.array([[45.0, 45.0, 4.7124]]))
    ideal_resid = e0 - np.einsum("nij,nj->ni", g, cstar)
    linear = e0 - np.einsum("nij,nj->ni", g, action)
    full = linear + np.tile([0.2, -0.3, 0.4], (N, 1))
    flat = g.reshape(N, 9, order="C")
    errors, mask, decoded = check_arrays(
        flat, e0, cstar, raw, action, beta, idx, ideal_resid, linear, full,
        full - linear, np.array([45.0, 45.0, 4.7124]), 2.2,
    )
    assert max(errors.values()) < 1e-12 and mask.any()
    assert np.array_equal(decoded, g)

    # Exercise scipy's classic MAT scalar-struct field/shape decoding in memory.
    buffer = io.BytesIO()
    savemat(buffer, {"cache": {"schema": "CM18_C5_VAL48_CSTAR_EVENT_CACHE_V1", "identity": {"scene_id": "SYNTH"}, "events": {"G_row_major": flat}}})
    buffer.seek(0)
    loaded = loadmat(buffer, squeeze_me=True, struct_as_record=False)["cache"]
    assert mat_text(field(loaded, "schema")) == "CM18_C5_VAL48_CSTAR_EVENT_CACHE_V1"
    assert mat_text(field(field(loaded, "identity"), "scene_id")) == "SYNTH"
    assert np.array_equal(np.asarray(field(field(loaded, "events"), "G_row_major")), flat)
    print("SELF_CHECK=PASS rowmajor/solve/beta/clip/residual/MAT-v7-shape")


def main() -> int:
    if sys.argv[1:] == ["--self-check"]:
        synthetic_check()
        return 0
    if sys.argv[1:]:
        raise SystemExit("Usage: root_audit_c5_val48_cstar_independent_v1.py [--self-check]")
    if not RELABEL_MANIFEST.is_file():
        print(json.dumps({"status": "INCOMPLETE", "missing_manifest": str(RELABEL_MANIFEST)}))
        return 2
    audit = run_audit()
    if OUTPUT.exists():
        raise FileExistsError(f"Refusing to overwrite {OUTPUT}")
    with OUTPUT.open("x", encoding="utf-8") as f:
        json.dump(audit, f, indent=2)
    print(json.dumps({"status": audit["status"], "scene_count": audit["scene_count"], "max_arithmetic_error": audit["max_arithmetic_error"], "output": str(OUTPUT)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
