"""Independent NumPy arithmetic check of the 24 fixed C5-matched exports."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import h5py
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "reports/attitude_position_context_probe_20261024/c5_matched_train24_v1"
TASKBOOK = ROOT / "reports/attitude_cm18_datarepair_20261024/ROOT_C5_MATCHED_TRAIN24_PROTOCOL_TASKBOOK_v1.json"
TASKBOOK_SHA = "88d7312087025a331dd532410b0ef31ed2dcb7dd3175239ad1d47bc68dd65f0b"
SOURCE_MANIFEST_SHA = "0f86b47d01940e7b556b78a9664470531572809aa6857a59fc77d88a33681ec5"
EXPORTER = ROOT / "experiments/attitude_position_context_probe_20261024/c5_matched_train24_v1/export_c5_matched_train24_scene_v1.m"
EXPORTER_SHA = "8b77f32b80e82291c3d1ab4ce0bc60f5719c2b97801094a52dc275049fb54861"
OUTPUT = BASE / "ROOT_TRAIN24_CSTAR_BATCH_NUMPY_AUDIT_v1.json"
N = 1999
DT = 0.001
BETA_RISE_S = 2.2
DMAX = np.array([45.0, 45.0, 4.7124])


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def max_abs(x: np.ndarray) -> float:
    if x.size == 0 or not np.isfinite(x).all():
        raise ValueError("Empty or nonfinite arithmetic result")
    return float(np.max(np.abs(x)))


def check_arrays(flat_g, e0, cstar, raw, action, beta, idx, full, stored_linear, stored_full_minus):
    flat_g = np.asarray(flat_g, dtype=np.float64)
    e0 = np.asarray(e0, dtype=np.float64)
    cstar = np.asarray(cstar, dtype=np.float64)
    raw = np.asarray(raw, dtype=np.float64)
    action = np.asarray(action, dtype=np.float64)
    beta = np.asarray(beta, dtype=np.float64).reshape(-1, 1)
    idx_float = np.asarray(idx, dtype=np.float64).reshape(-1)
    full = np.asarray(full, dtype=np.float64)
    stored_linear = np.asarray(stored_linear, dtype=np.float64)
    stored_full_minus = np.asarray(stored_full_minus, dtype=np.float64)

    if flat_g.shape != (N, 9) or e0.shape != (N, 3) or cstar.shape != (N, 3):
        raise ValueError("Unexpected G/E0/cstar event shape")
    if raw.shape != (N, 3) or action.shape != (N, 3) or full.shape != (N, 3):
        raise ValueError("Unexpected raw/action/full-allocator event shape")
    if stored_linear.shape != (N, 3) or stored_full_minus.shape != (N, 3):
        raise ValueError("Unexpected residual event shape")
    if beta.shape != (N, 1) or not np.isfinite(idx_float).all() or not np.equal(idx_float, np.floor(idx_float)).all():
        raise ValueError("Nonfinite/noninteger event index or unexpected beta shape")
    idx = idx_float.astype(np.int64)
    if not np.array_equal(idx, np.arange(11, 19992, 10)):
        raise ValueError("Unexpected beta or canonical event index shape/order")
    values = (flat_g, e0, cstar, raw, action, beta, full, stored_linear, stored_full_minus)
    if not all(np.isfinite(x).all() for x in values):
        raise ValueError("Nonfinite exported event values")

    g = flat_g.reshape(N, 3, 3)  # G was stored row-major by MATLAB reshape(G.',1,9).
    solved = np.linalg.solve(g, e0)
    beta_expected = np.minimum(idx[:, None] * DT / BETA_RISE_S, 1.0)
    clipped = np.clip(raw, -DMAX, DMAX)
    linear = e0 - np.einsum("nij,nj->ni", g, action)
    full_minus_linear = full - linear
    errors = {
        "max_abs_cstar_solve_delta": max_abs(cstar - solved),
        "max_abs_E0_minus_G_cstar": max_abs(e0 - np.einsum("nij,nj->ni", g, cstar)),
        "max_abs_beta_formula_delta": max_abs(beta - beta_expected),
        "max_abs_beta_raw_minus_cstar": max_abs(beta * raw - cstar),
        "max_abs_clipped_action_delta": max_abs(action - beta * clipped),
        "max_abs_E0_minus_G_action_delta": max_abs(linear - stored_linear),
        "max_abs_full_minus_linear_delta": max_abs(full_minus_linear - stored_full_minus),
    }
    clip_mask = np.abs(raw - clipped) > 1e-12
    return errors, clip_mask, g


def read_export(scene_id: str, task_row: dict) -> dict:
    folder = BASE / "event_exports_v1" / scene_id
    audit_path = folder / f"{scene_id}_CSTAR_AUDIT_v1.json"
    if not audit_path.is_file():
        raise FileNotFoundError(str(audit_path))
    audit = json.loads(audit_path.read_text(encoding="utf-8-sig"))
    ident = audit["identity"]
    if audit.get("schema") != "C5_MATCHED_TRAIN24_EVENT_EXPORT_AUDIT_V1" or audit.get("status") != "PASS":
        raise ValueError(f"{scene_id}: export audit is not PASS")
    if audit.get("canonical_scene_id") != scene_id or audit.get("event_count") != N:
        raise ValueError(f"{scene_id}: export summary identity/count mismatch")
    if audit.get("transition_count") != 20000 or audit.get("state_sample_count") != 20001:
        raise ValueError(f"{scene_id}: export timebase mismatch")
    runtime_expected = scene_id if task_row["source_kind"] == "original_T1_T3_B_scene" else scene_id + "_ACC_FIX_V1"
    if ident.get("runtime_scene_id") != runtime_expected:
        raise ValueError(f"{scene_id}: runtime alias mismatch")
    if ident.get("taskbook_sha256") != TASKBOOK_SHA or ident.get("source_manifest_sha256") != SOURCE_MANIFEST_SHA:
        raise ValueError(f"{scene_id}: taskbook/source manifest pin mismatch")
    if ident.get("source_raw_sha256") != task_row["raw_sha256"] or ident.get("source_run_start_sha256") != task_row["run_start_sha256"]:
        raise ValueError(f"{scene_id}: source raw/run_start identity mismatch")
    if ident.get("C5_snapshot_sha256") != json.loads(TASKBOOK.read_text(encoding="utf-8-sig"))["C5_snapshot_sha256"]:
        raise ValueError(f"{scene_id}: C5 snapshot identity mismatch")

    raw_path = Path(ident["flight_raw_path"])
    cache_path = Path(audit["cache_path"])
    exporter_path = Path(ident["exporter_matlab_path"])
    if sha256(raw_path) != ident["flight_raw_sha256"]:
        raise ValueError(f"{scene_id}: flight raw SHA mismatch")
    if sha256(cache_path) != audit["cache_sha256"]:
        raise ValueError(f"{scene_id}: event cache SHA mismatch")
    if sha256(exporter_path) != EXPORTER_SHA or ident.get("exporter_matlab_sha256") != EXPORTER_SHA:
        raise ValueError(f"{scene_id}: frozen exporter SHA mismatch")

    with h5py.File(cache_path, "r") as f:
        e = f["events"]
        read = lambda key: np.asarray(e[key], dtype=np.float64).T
        arrays = {
            "flat_g": read("G_row_major"),
            "e0": read("E0_rad_s2"),
            "cstar": read("target_applied_acceleration_rad_s2"),
            "raw": read("target_raw_output_rad_s2"),
            "action": read("target_after_clip_beta_rad_s2"),
            "beta": read("beta"),
            "idx": read("plant_index"),
            "full": read("target_full_allocator_error_rad_s2"),
            "stored_linear": read("target_linear_residual_rad_s2"),
            "stored_full_minus": read("target_full_minus_linear_rad_s2"),
        }
    errors, clip_mask, g = check_arrays(**arrays)
    clip_by_axis = np.sum(clip_mask, axis=0).astype(int)
    cstar = arrays["cstar"]
    return {
        "scene_id": scene_id,
        "condition": "C00" if "_C00_" in scene_id else "C15",
        "raw_sha256": ident["flight_raw_sha256"],
        "event_cache_sha256": audit["cache_sha256"],
        "exporter_sha256": ident["exporter_matlab_sha256"],
        "event_count": N,
        "clip_active_by_axis": clip_by_axis.tolist(),
        "clip_active_event_count": int(np.count_nonzero(np.any(clip_mask, axis=1))),
        "cstar_nonzero_event_count_gt_1e_12": int(np.count_nonzero(np.max(np.abs(cstar), axis=1) > 1e-12)),
        "cstar_rms_by_axis": np.sqrt(np.mean(cstar**2, axis=0)).tolist(),
        "max_abs_G_entry": float(np.max(np.abs(g))),
        "max_arithmetic_errors": errors,
    }


def summarize_group(rows: list[dict]) -> dict:
    return {
        "scene_count": len(rows),
        "clip_active_event_count": sum(r["clip_active_event_count"] for r in rows),
        "clip_active_by_axis": np.sum([r["clip_active_by_axis"] for r in rows], axis=0).astype(int).tolist(),
        "scenes_with_active_clip": sum(r["clip_active_event_count"] > 0 for r in rows),
        "scenes_with_nonzero_cstar": sum(r["cstar_nonzero_event_count_gt_1e_12"] > 0 for r in rows),
        "max_error_by_check": {
            key: max(r["max_arithmetic_errors"][key] for r in rows)
            for key in rows[0]["max_arithmetic_errors"]
        },
    }


def self_check() -> None:
    n = N
    g = np.tile(np.array([[2.0, 0.2, 0.0], [-0.1, 1.5, 0.3], [0.4, 0.1, 0.5]]), (n, 1, 1))
    e0 = np.tile([100.0, 4.0, 1.0], (n, 1))
    cstar = np.linalg.solve(g, e0)
    beta = np.minimum(np.arange(11, 19992, 10)[:, None] * DT / BETA_RISE_S, 1.0)
    raw = cstar / beta
    action = beta * np.clip(raw, -DMAX, DMAX)
    linear = e0 - np.einsum("nij,nj->ni", g, action)
    full = linear + np.tile([0.2, -0.3, 0.4], (n, 1))
    errors, clip_mask, _ = check_arrays(
        g.reshape(n, 9), e0, cstar, raw, action, beta,
        np.arange(11, 19992, 10), full, linear, full - linear,
    )
    assert max(errors.values()) < 1e-12 and np.any(clip_mask)
    print("SELF_CHECK=PASS active_synthetic_clip=1")


def main() -> int:
    if sys.argv[1:] == ["--self-check"]:
        self_check()
        return 0
    if sys.argv[1:]:
        raise SystemExit("Usage: root_audit_train24_cstar_batch_v1.py [--self-check]")
    if sha256(TASKBOOK) != TASKBOOK_SHA or sha256(EXPORTER) != EXPORTER_SHA:
        raise ValueError("Pinned taskbook/exporter SHA changed")
    taskbook = json.loads(TASKBOOK.read_text(encoding="utf-8-sig"))
    if taskbook.get("schema") != "ROOT_C5_MATCHED_TRAIN24_PROTOCOL_TASKBOOK_V1" or taskbook.get("decision") != "IMPLEMENTATION_AND_NO_PLANT_PREPARATION_APPROVED_ONLY":
        raise ValueError("Frozen TRAIN24 taskbook schema/decision changed")
    rows = taskbook["scene_rows"]
    scene_ids = [r["canonical_scene_id"] for r in rows]
    if len(rows) != 24 or len(set(scene_ids)) != 24:
        raise ValueError("Frozen taskbook must contain 24 unique scenes")
    missing = [sid for sid in scene_ids if not (BASE / "event_exports_v1" / sid / f"{sid}_CSTAR_AUDIT_v1.json").is_file()]
    if missing:
        print(json.dumps({"status": "INCOMPLETE", "completed_exports": 24 - len(missing), "missing_scene_ids": missing}))
        return 2

    scene_results = [read_export(r["canonical_scene_id"], r) for r in rows]
    all_errors = [v for r in scene_results for v in r["max_arithmetic_errors"].values()]
    if not all(np.isfinite(all_errors)) or max(all_errors) >= 1e-8:
        raise ValueError(f"Arithmetic audit exceeded 1e-8 tolerance: {max(all_errors)}")
    groups = {g: summarize_group([r for r in scene_results if r["condition"] == g]) for g in ("C00", "C15")}
    if any(groups[g]["scene_count"] != 12 for g in groups):
        raise ValueError("Expected twelve fixed scenes in each C00/C15 group")
    payload = {
        "schema": "ROOT_TRAIN24_CSTAR_BATCH_NUMPY_AUDIT_V1",
        "status": "PASS",
        "taskbook_sha256": TASKBOOK_SHA,
        "exporter_sha256": EXPORTER_SHA,
        "scene_count": len(scene_results),
        "event_count_per_scene": N,
        "beta_rise_s": BETA_RISE_S,
        "clip_limit_by_axis": DMAX.tolist(),
        "overall_max_arithmetic_error": max(all_errors),
        "clip_coverage": "ACTIVE_CLIP_OBSERVED" if any(r["clip_active_event_count"] for r in scene_results) else "NO_ACTIVE_CLIP_OBSERVED",
        "C15_nonzero_target_coverage": "OBSERVED" if groups["C15"]["scenes_with_nonzero_cstar"] else "NO_NONZERO_C15_TARGET_OBSERVED",
        "groups": groups,
        "scenes": scene_results,
        "scope": "Independent NumPy arithmetic on exported G/E0/cache and SHA-bound raw files; this does not independently reconstruct the raw physical equations, allocate_control, or X18.",
        "Plant_calls": 0,
        "optimizer_steps": 0,
        "TEST_accessed": False,
        "audit_source_sha256": sha256(Path(__file__)),
    }
    with OUTPUT.open("x", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(json.dumps({"status": payload["status"], "output": str(OUTPUT), "scene_count": len(scene_results), "max_error": max(all_errors)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
