from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat


ROOT = Path(__file__).resolve().parents[2]
ATTEMPT = ROOT / "reports/attitude_cm18_datarepair_20261024/cstar_screen4_attempt02_v1"
INPUT = ATTEMPT / "CSTAR_RELABEL_SCREEN4_ATTEMPT02_v1.json"
OUTPUT = ATTEMPT / "CSTAR_SCREEN4_INDEPENDENT_CACHE_AUDIT_v1.json"
SOURCE_SHA = "0f86b47d01940e7b556b78a9664470531572809aa6857a59fc77d88a33681ec5"
DATASET_SHA = "3f51a1cd0e2e8c3eae79a16df363f2f8d47b0d5dbd876ecd95f1571d9e70a5e0"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def repo_file(relative: str) -> Path:
    path = (ROOT / relative).resolve()
    if ROOT not in path.parents:
        raise ValueError(f"path escaped repository: {relative}")
    return path


def mat_text(value) -> str:
    a = np.asarray(value)
    if a.size == 1:
        value = a.item()
        return value.decode("utf-8") if isinstance(value, bytes) else str(value)
    if a.dtype.kind in "US":
        return "".join(str(x) for x in a.reshape(-1))
    raise ValueError("expected MATLAB text scalar")


def vec(data, key, n=None, dtype=float):
    a = np.asarray(data[key], dtype=dtype).reshape(-1)
    if n is not None and a.size != n:
        raise ValueError(f"{key}: expected {n} values, got {a.size}")
    return a


def matrix(data, key, shape, dtype=float):
    a = np.asarray(data[key], dtype=dtype)
    if a.shape != shape:
        raise ValueError(f"{key}: expected shape {shape}, got {a.shape}")
    return a


def near(a, b, tol=1e-12):
    a, b = np.asarray(a), np.asarray(b)
    return a.shape == b.shape and np.all(np.isfinite(a)) and np.all(np.isfinite(b)) and (
        a.size == 0 or np.max(np.abs(a - b)) <= tol
    )


def audit_scene(scene, report, dmax):
    sid = report["scene_id"]
    n = 1999
    new_path = repo_file(report["new_cache_path"])
    old_path = repo_file(report["old_cache_path"])
    if sha256(new_path) != report["new_cache_sha256"] or new_path.stat().st_size != report["new_cache_bytes"]:
        raise ValueError(f"{sid}: new cache identity mismatch")
    if sha256(old_path) != report["old_cache_sha256"]:
        raise ValueError(f"{sid}: old cache SHA mismatch")

    new = loadmat(new_path, squeeze_me=True, chars_as_strings=True)
    old = loadmat(old_path, squeeze_me=True, chars_as_strings=True)
    if mat_text(new["scene_id"]) != sid or mat_text(new["split"]) != report["split"]:
        raise ValueError(f"{sid}: new cache scene/split mismatch")
    if mat_text(old["scene_id"]) != sid or mat_text(old["split"]) != report["split"]:
        raise ValueError(f"{sid}: old cache scene/split mismatch")
    for key, expected in (("old_cache_path", report["old_cache_path"]),
                          ("old_cache_sha256", report["old_cache_sha256"])):
        if mat_text(new[key]) != expected:
            raise ValueError(f"{sid}: embedded {key} mismatch")
    if mat_text(new["source_manifest_sha256"]).lower() != SOURCE_SHA:
        raise ValueError(f"{sid}: embedded source manifest SHA mismatch")
    if mat_text(new["dataset_manifest_sha256"]).lower() != DATASET_SHA:
        raise ValueError(f"{sid}: embedded dataset manifest SHA mismatch")
    if "X18" in new:
        raise ValueError(f"{sid}: relabel cache unexpectedly copied X18")

    x = matrix(old, "X18", (n, 18))
    y_old = matrix(old, "target_raw", (n, 3))
    if not np.isfinite(x).all() or not np.isfinite(y_old).all():
        raise ValueError(f"{sid}: old cache contains nonfinite inputs/targets")
    event = vec(new, "event_index", n, np.int64)
    plant = vec(new, "plant_index", n, np.int64)
    old_plant = vec(old, "plant_index", n, np.int64)
    time = vec(new, "event_time_s", n)
    old_time = vec(old, "event_time_s", n)
    phase = vec(new, "phase_code", n, np.int64)
    old_phase = vec(old, "phase_code", n, np.int64)
    if not np.array_equal(event, np.arange(1, n + 1)):
        raise ValueError(f"{sid}: event_index is not the ordered 1..1999 sequence")
    if not np.array_equal(plant, old_plant) or not np.array_equal(phase, old_phase) or not near(time, old_time):
        raise ValueError(f"{sid}: new cache indices/time/phase differ from its bound old cache")
    if not np.isfinite(time).all() or np.any(np.diff(time) <= 0):
        raise ValueError(f"{sid}: event time is nonfinite or not strictly increasing")

    cstar = matrix(new, "target_applied_acceleration_rad_s2", (n, 3))
    raw = matrix(new, "target_raw_output_rad_s2", (n, 3))
    applied = matrix(new, "target_after_clip_beta_rad_s2", (n, 3))
    beta = vec(new, "beta", n)
    raw_mask = matrix(new, "output_clip_mask", (n, 3), bool)
    zero_mask = matrix(new, "beta_zero_unreachable_mask", (n, 3), bool)
    alloc_mask = matrix(new, "allocator_clip_mask", (n, 4), bool)
    motor_mask = matrix(new, "motor_saturation_mask", (n, 4), bool)
    reachable = matrix(new, "target_raw_output_reachable", (n, 3), bool)
    if not np.isfinite(cstar).all() or not np.isfinite(beta).all() or np.any((beta < 0) | (beta > 1)):
        raise ValueError(f"{sid}: c* or beta is nonfinite/out of range")
    if np.any(np.diff(beta) < -1e-14):
        raise ValueError(f"{sid}: beta is not monotone")
    gflat = matrix(new, "G_column_major", (n, 9))
    if not np.isfinite(gflat).all():
        raise ValueError(f"{sid}: G contains nonfinite entries")
    gmat = gflat.reshape(n, 3, 3, order="F")
    rconds = np.empty(n)
    for i, g in enumerate(gmat):
        s = np.linalg.svd(g, compute_uv=False)
        rconds[i] = s[-1] / s[0] if s[0] else 0.0
    if np.any(np.linalg.matrix_rank(gmat) != 3) or np.any(rconds <= 1e-12):
        raise ValueError(f"{sid}: G is not numerically full rank")

    positive = beta > 0
    expected_raw = np.full((n, 3), np.nan)
    expected_raw[positive] = cstar[positive] / beta[positive, None]
    if not near(raw[positive], expected_raw[positive]):
        raise ValueError(f"{sid}: raw output does not equal c*/beta")
    clipped = np.clip(raw[positive], -dmax, dmax)
    expected_clip_mask = np.abs(raw[positive] - clipped) > 1e-12
    if not np.array_equal(raw_mask[positive], expected_clip_mask):
        raise ValueError(f"{sid}: output clip mask mismatch")
    expected_applied = np.zeros((n, 3))
    expected_applied[positive] = beta[positive, None] * clipped
    if not near(applied, expected_applied):
        raise ValueError(f"{sid}: applied target does not match beta times clipped raw output")
    reachable_expected = np.ones((n, 3), dtype=bool)
    reachable_expected[~positive] = np.abs(cstar[~positive]) <= 1e-10
    if not np.array_equal(reachable, reachable_expected) or not np.array_equal(zero_mask, ~reachable):
        raise ValueError(f"{sid}: zero-beta reachability mask mismatch")
    if np.any(np.isfinite(raw[~positive]) != reachable[~positive]) or np.any(np.isfinite(raw[~positive][~reachable[~positive]])):
        raise ValueError(f"{sid}: zero-beta raw output sentinel mismatch")

    zero_basis = np.all(x[:, 7:15] == 0, axis=1)
    zero_target = cstar[zero_basis]
    axis = {a["axis"]: a for a in report["axis_summary"]}
    axis_names = ("roll", "pitch", "yaw")
    for j, name in enumerate(axis_names):
        if int(raw_mask[:, j].sum()) != int(axis[name]["cstar_raw_output_clip_count"]):
            raise ValueError(f"{sid}: raw clip count differs for {name}")
        if int(zero_mask[:, j].sum()) != int(axis[name]["beta_zero_unreachable_count"]):
            raise ValueError(f"{sid}: zero-beta unreachable count differs for {name}")
    if not np.array_equal(alloc_mask.sum(axis=0), report["cstar_actual_beta_allocator_clip_count_by_channel"]):
        raise ValueError(f"{sid}: allocator clip counts differ from summary")
    if not np.array_equal(motor_mask.sum(axis=0), report["cstar_actual_beta_motor_saturation_count_by_motor"]):
        raise ValueError(f"{sid}: motor saturation counts differ from summary")
    if int(zero_basis.sum()) != int(report["zero_morphology_basis_event_count"]):
        raise ValueError(f"{sid}: zero-basis event count differs from old X18")
    zero_max = float(np.max(np.abs(zero_target))) if zero_target.size else 0.0
    zero_nonzero = int(np.any(np.abs(zero_target) > 1e-8, axis=1).sum()) if zero_target.size else 0
    if zero_nonzero != int(report["zero_basis_nonzero_applied_target_count_gt_1e_8"]):
        raise ValueError(f"{sid}: zero-basis target count differs from summary")
    if abs(zero_max - float(report["zero_basis_target_applied_max_abs_rad_s2"])) > 1e-12:
        raise ValueError(f"{sid}: zero-basis target maximum differs from summary")
    if not np.array_equal(beta[[0, -1]], np.asarray(report["beta_first_last"], dtype=float)):
        raise ValueError(f"{sid}: beta endpoints differ from summary")
    if int(np.count_nonzero(beta == 0)) != int(report["beta_zero_count"]):
        raise ValueError(f"{sid}: beta-zero count differs from summary")
    if int(np.count_nonzero(beta < 1)) != int(report["beta_below_one_count"]):
        raise ValueError(f"{sid}: beta-below-one count differs from summary")

    return {
        "scene_id": sid, "split": report["split"], "status": "PASS", "event_count": n,
        "event_index_first_last": [int(event[0]), int(event[-1])],
        "plant_index_first_last": [int(plant[0]), int(plant[-1])],
        "event_time_first_last_s": [float(time[0]), float(time[-1])],
        "old_cache_sha256_verified": report["old_cache_sha256"],
        "new_cache_sha256_verified": report["new_cache_sha256"],
        "G_layout": "3x3 per row, Fortran/column-major reshape; all finite and numerical rank 3",
        "minimum_singular_value_ratio_G": float(rconds.min()),
        "raw_clip_count_by_axis": raw_mask.sum(axis=0).astype(int).tolist(),
        "zero_beta_unreachable_count_by_axis": zero_mask.sum(axis=0).astype(int).tolist(),
        "allocator_clip_count_by_channel": alloc_mask.sum(axis=0).astype(int).tolist(),
        "motor_saturation_count_by_motor": motor_mask.sum(axis=0).astype(int).tolist(),
        "zero_morphology_basis_event_count": int(zero_basis.sum()),
        "zero_basis_nonzero_cstar_count_gt_1e_8": zero_nonzero,
        "max_abs_zero_basis_cstar_rad_s2": zero_max,
    }


def main():
    if OUTPUT.exists():
        raise FileExistsError(f"refusing to overwrite {OUTPUT}")
    data = json.loads(INPUT.read_text(encoding="utf-8"))
    if data.get("status") != "PASS" or data.get("dataset_manifest_sha256", "").lower() != DATASET_SHA:
        raise ValueError("attempt02 report is not PASS or dataset identity differs")
    if data.get("source_manifest_sha256", "").lower() != SOURCE_SHA:
        raise ValueError("source manifest identity differs")
    scenes = data.get("scenes")
    if not isinstance(scenes, list) or len(scenes) != 4:
        raise ValueError("expected four scene results")
    dmax = np.asarray(data["dmax_rad_s2"], dtype=float).reshape(3)
    audited = [audit_scene(scene, scene, dmax) for scene in scenes]
    result = {
        "schema": "CM18_CSTAR_SCREEN4_INDEPENDENT_CACHE_AUDIT_V1",
        "status": "PASS", "input_report_sha256": sha256(INPUT),
        "source_manifest_sha256": SOURCE_SHA, "dataset_manifest_sha256": DATASET_SHA,
        "scope": {"scene_count": 4, "events": 7996, "raw_loaded": False,
                  "plant_calls": 0, "training_steps": 0, "TEST_accessed": False},
        "scenes": audited,
        "limits": ["This verifies serialized cache identity, indices/timing, masks, and stored G layout/rank.",
                   "It does not independently recompute raw physics or certify closed-loop behavior."],
    }
    OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(OUTPUT)


if __name__ == "__main__":
    main()
