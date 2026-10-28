#!/usr/bin/env python3
"""Build Causal-TCN attitude residual labels from identity-locked B raw data.

Only event-time attitude error, body rate, nominal BS acceleration, morph
command and the following 10 ms body-rate increment are read. Plant rho/J
truth fields and historical C* labels are deliberately never opened.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import h5py
import numpy as np
from scipy.io import loadmat


ROOT = Path(__file__).resolve().parents[2]
DATASET_MANIFEST = Path("reports/attitude_cm18_datarepair_20261024/repaired_all816_v1/DATASET_MANIFEST_v1.json")
SOURCE_MANIFEST = Path("reports/attitude_cm18_datarepair_20261024/B_REF_REPAIRED_SOURCE_MANIFEST_v1.json")
EVENT_DT = 0.010
STATE_DT = 0.001
EVENT_STRIDE = 10
EXPECTED_EVENTS = 1999


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, np.ndarray) and value.dtype.kind in "ui":
        return "".join(chr(int(x)) for x in value.reshape(-1) if int(x) != 0)
    return str(value)


def load_run_start(path: Path) -> tuple[np.ndarray, str]:
    if h5py.is_hdf5(path):
        with h5py.File(path, "r") as handle:
            if "runStart" in handle:
                cfg = handle["runStart"]["cfg"]
            elif "cfg" in handle:
                cfg = handle["cfg"]
            else:
                raise ValueError(f"MATLAB HDF5 run_start has no cfg group: {path}")
            mode_raw = np.asarray(cfg["controller_morphology_mode"]).reshape(-1)
            mode = "".join(chr(int(x)) for x in mode_raw if int(x) != 0).lower()
            inertia = np.asarray(cfg["plant"]["inertia"], dtype=np.float64).T
    else:
        root = loadmat(path, squeeze_me=True, struct_as_record=False)["runStart"]
        mode = text(root.cfg.controller_morphology_mode).lower()
        inertia = np.asarray(root.cfg.plant.inertia, dtype=np.float64)
    if inertia.shape != (3, 3) or not np.isfinite(inertia).all():
        raise ValueError(f"invalid nominal inertia in {path}")
    if mode != "fixed":
        raise ValueError(f"controller is not fixed nominal morphology in {path}: {mode}")
    if np.linalg.norm(inertia - inertia.T, ord="fro") > 1e-12 or np.min(np.linalg.eigvalsh(inertia)) <= 0:
        raise ValueError(f"nominal inertia is not SPD in {path}")
    return inertia, mode


def resolve_source(root: Path, row: dict[str, Any], source_row: dict[str, Any]) -> tuple[Path, str, Path, str, str]:
    if row["scene_id"] != source_row["scene_id"] or row["source_action"] != source_row["source_action"]:
        raise ValueError(f"repaired/source manifest identity mismatch for {row['scene_id']}")
    if row["source_action"] == "REBUILD_FROM_CORRECTED_T2_B_RAW":
        corrected = source_row.get("corrected_source", {})
        raw_ref, start_ref = corrected.get("raw", {}), corrected.get("run_start", {})
        for field in ("path", "sha256", "size_bytes"):
            if field not in raw_ref:
                raise ValueError(f"corrected raw manifest lacks {field} for {row['scene_id']}")
        for field in ("path", "sha256", "size_bytes"):
            if field not in start_ref:
                raise ValueError(f"corrected run_start manifest lacks {field} for {row['scene_id']}")
        if (row.get("corrected_raw_sha256", "").lower() != raw_ref["sha256"].lower()
                or row.get("corrected_run_start_sha256", "").lower() != start_ref["sha256"].lower()
                or row.get("corrected_raw_path") != raw_ref["path"]
                or row.get("corrected_run_start_path") != start_ref["path"]):
            raise ValueError(f"corrected raw path/hash differs across manifests for {row['scene_id']}")
        action = "CORRECTED_T2_B_RAW"
    else:
        source = row["original_a1_source"]
        raw_ref, start_ref = source["raw_run"], source["run_start"]
        action = "REUSE_CERTIFIED_ORIGINAL_B_RAW"
    raw_path = Path(raw_ref["path"])
    start_path = Path(start_ref["path"])
    if not raw_path.is_absolute():
        raw_path = root / raw_path
    if not start_path.is_absolute():
        start_path = root / start_path
    return raw_path, raw_ref["sha256"].lower(), start_path, start_ref["sha256"].lower(), action


def load_scene(root: Path, row: dict[str, Any], source_row: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    raw_path, raw_sha, start_path, start_sha, source_class = resolve_source(root, row, source_row)
    if not raw_path.is_file() or not start_path.is_file():
        raise FileNotFoundError(f"missing raw/run_start for {row['scene_id']}")
    raw_size = source_row["corrected_source"]["raw"]["size_bytes"] if source_class == "CORRECTED_T2_B_RAW" else row["original_a1_source"]["raw_run"]["size_bytes"]
    start_size = source_row["corrected_source"]["run_start"]["size_bytes"] if source_class == "CORRECTED_T2_B_RAW" else row["original_a1_source"]["run_start"]["size_bytes"]
    for path, expected_size, expected_sha in ((raw_path, raw_size, raw_sha), (start_path, start_size, start_sha)):
        if path.stat().st_size != int(expected_size):
            raise ValueError(f"size mismatch for {path}")
        if sha256(path) != expected_sha:
            raise ValueError(f"SHA-256 mismatch for {path}")

    inertia, mode = load_run_start(start_path)
    with h5py.File(raw_path, "r") as raw:
        log = raw["log"]
        scene = raw["scene"]
        required_log = ("time", "transition_time", "state", "raw_outer_attitude",
                        "filtered_attitude_reference", "attitude_event_flag",
                        "attitude_bs_nominal_torque_Nm")
        missing = [name for name in required_log if name not in log]
        if missing or "arms" not in scene or "command" not in scene["arms"]:
            raise ValueError(f"missing deployable raw fields for {row['scene_id']}: {missing}")

        time = np.asarray(log["time"], dtype=np.float64).reshape(-1)
        transitions = np.asarray(log["transition_time"], dtype=np.float64).reshape(-1)
        state = np.asarray(log["state"], dtype=np.float64).T
        filtered_ref = np.asarray(log["filtered_attitude_reference"], dtype=np.float64).T
        flags = np.asarray(log["attitude_event_flag"]).reshape(-1).astype(bool)
        nominal_torque = np.asarray(log["attitude_bs_nominal_torque_Nm"], dtype=np.float64).T
        morph_command = np.asarray(scene["arms"]["command"], dtype=np.float64).T

    if (time.shape != (20001,) or transitions.shape != (20000,) or state.shape != (20001, 12)
            or filtered_ref.shape != (20000, 3) or flags.shape != (20000,)
            or nominal_torque.shape != (20000, 3) or morph_command.shape != (20001, 4)):
        raise ValueError(f"raw dimensions changed for {row['scene_id']}")
    if (abs(time[0]) > 1e-12 or abs(time[-1] - 20.0) > 1e-12
            or np.max(np.abs(np.diff(time) - STATE_DT)) > 1e-12
            or np.max(np.abs(transitions - time[:-1])) > 1e-12):
        raise ValueError(f"raw timebase changed for {row['scene_id']}")
    events = np.flatnonzero(flags)
    expected = np.arange(10, 20000, EVENT_STRIDE, dtype=np.int64)
    if not np.array_equal(events, expected) or len(events) != EXPECTED_EVENTS:
        raise ValueError(f"event schedule changed for {row['scene_id']}")

    omega = state[events, 9:12]
    euler = state[events, 6:9]
    error = filtered_ref[events] - euler
    error = np.arctan2(np.sin(error), np.cos(error))
    # Fixed controller morphology has zero Jdot; this reconstructs only the
    # controller's logged nominal angular acceleration from its fixed J0.
    gyro = np.cross(omega, omega @ inertia.T)
    alpha_bs = np.linalg.solve(inertia, (nominal_torque[events] - gyro).T).T
    command = morph_command[events]
    x = np.concatenate((error, omega, alpha_bs, command), axis=1)
    alpha_measured = (state[events + EVENT_STRIDE, 9:12] - state[events, 9:12]) / EVENT_DT
    y = alpha_measured - alpha_bs
    if x.shape != (EXPECTED_EVENTS, 13) or y.shape != (EXPECTED_EVENTS, 3):
        raise AssertionError(f"feature/target shape mismatch for {row['scene_id']}")
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError(f"non-finite feature/target for {row['scene_id']}")
    report = {
        "scene_id": row["scene_id"], "split": row["split"],
        "source_class": source_class, "raw_path": str(raw_path), "raw_sha256": raw_sha,
        "run_start_path": str(start_path), "run_start_sha256": start_sha,
        "nominal_inertia_kg_m2": inertia.tolist(), "controller_morphology_mode": mode,
        "event_count": int(len(events)), "feature_shape": list(x.shape),
        "target_shape": list(y.shape), "feature_min": x.min(axis=0).tolist(),
        "feature_max": x.max(axis=0).tolist(), "target_rms": np.sqrt(np.mean(y * y, axis=0)).tolist(),
        "plant_truth_read": False, "old_cstar_read": False,
    }
    return x.astype(np.float32), y.astype(np.float32), inertia, report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="validate one raw scene without writing")
    parser.add_argument("--output", type=Path, default=Path("experiments/dl_attitude_replacement_20261026/dataset_v3_corrected"))
    args = parser.parse_args()
    root = ROOT
    manifest_path = root / DATASET_MANIFEST
    source_manifest_path = root / SOURCE_MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    if (manifest.get("status") != "PASS" or manifest.get("scene_count") != 816
            or manifest.get("qualified_count") != 816 or manifest.get("failed_count") != 0
            or manifest.get("split_counts") != {"TRAIN": 768, "VAL": 48}
            or manifest.get("TEST_accessed") is not False
            or source_manifest.get("schema") != "CM18_REFERENCE_REPAIRED_SOURCE_MANIFEST_V1"
            or len(source_manifest.get("scenes", [])) != 816):
        raise ValueError("B all816 manifest is not the expected PASS TRAIN/VAL-only source")
    source_rows = {r["scene_id"]: r for r in source_manifest["scenes"]}
    train_rows = [r for r in manifest["rows"] if r["split"] == "TRAIN"]
    val_rows = [r for r in manifest["rows"] if r["split"] == "VAL"]
    if len(train_rows) != 768 or len(val_rows) != 48:
        raise ValueError("unexpected scene split counts")

    if args.dry_run:
        corrected_t2 = next(r for r in train_rows if r["source_action"] == "REBUILD_FROM_CORRECTED_T2_B_RAW")
        corrected_val_t2 = next(r for r in val_rows if r["source_action"] == "REBUILD_FROM_CORRECTED_T2_B_RAW")
        for row in (train_rows[0], corrected_t2, val_rows[0], corrected_val_t2):
            x, y, inertia, report = load_scene(root, row, source_rows[row["scene_id"]])
            print(json.dumps({"scene_id": row["scene_id"], "x_shape": x.shape,
                              "y_shape": y.shape, "J0": inertia.tolist(),
                              "x_finite": bool(np.isfinite(x).all()),
                              "y_finite": bool(np.isfinite(y).all()),
                              "target_rms": np.sqrt(np.mean(y.astype(np.float64) ** 2, axis=0)).tolist(),
                              "source_class": report["source_class"],
                              "raw_sha256": report["raw_sha256"],
                              "plant_truth_read": report["plant_truth_read"]}, ensure_ascii=False))
        return

    output = (root / args.output).resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite dataset output: {output}")
    output.mkdir(parents=True)
    rows_out: list[dict[str, Any]] = []
    inertias: list[np.ndarray] = []
    arrays: dict[str, list[np.ndarray]] = {"TRAIN_x": [], "TRAIN_y": [], "VAL_x": [], "VAL_y": []}
    for split, rows in (("TRAIN", train_rows), ("VAL", val_rows)):
        for i, row in enumerate(rows, start=1):
            x, y, inertia, report = load_scene(root, row, source_rows[row["scene_id"]])
            arrays[f"{split}_x"].append(x)
            arrays[f"{split}_y"].append(y)
            inertias.append(inertia)
            rows_out.append(report)
            if i % 64 == 0 or i == len(rows):
                print(f"{split} {i}/{len(rows)} prepared", flush=True)

    inertia_stack = np.stack(inertias)
    max_j_delta = float(np.max(np.abs(inertia_stack - inertia_stack[0])))
    if max_j_delta > 1e-10:
        raise ValueError(f"fixed nominal J0 differs across the source cohort: {max_j_delta}")
    output_npz = output / "attitude_residual_train_val_v1.npz"
    np.savez_compressed(output_npz,
                        train_x=np.stack(arrays["TRAIN_x"]), train_y=np.stack(arrays["TRAIN_y"]),
                        val_x=np.stack(arrays["VAL_x"]), val_y=np.stack(arrays["VAL_y"]))
    manifest_out = {
        "schema": "DL1018_CAUSAL_TCN_ATTITUDE_RESIDUAL_DATASET_V1",
        "status": "PASS", "source_manifest": DATASET_MANIFEST.as_posix(),
        "source_manifest_sha256": sha256(manifest_path),
        "lineage_manifest": SOURCE_MANIFEST.as_posix(),
        "lineage_manifest_sha256": sha256(source_manifest_path),
        "split_counts": {"TRAIN": len(train_rows), "VAL": len(val_rows)},
        "events_per_scene": EXPECTED_EVENTS, "feature_order": ["attitude_error_euler_rad_x3",
          "body_rate_rad_s_x3", "nominal_bs_body_angular_acceleration_rad_s2_x3", "morph_command_x4"],
        "target": "(omega[k+10]-omega[k])/0.010-alpha_bs[k], rad/s^2",
        "event_stride_transitions": EVENT_STRIDE, "state_dt_s": STATE_DT,
        "nominal_inertia_kg_m2": inertia_stack[0].tolist(), "max_J0_cohort_delta": max_j_delta,
        "plant_truth_read": False, "old_cstar_read": False,
        "test_data_read": False, "npz_path": output_npz.relative_to(root).as_posix(),
        "npz_sha256": sha256(output_npz), "npz_bytes": output_npz.stat().st_size,
        "rows": rows_out,
    }
    manifest_out_path = output / "DATASET_MANIFEST_v1.json"
    manifest_out_path.write_text(json.dumps(manifest_out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "train_scenes": len(train_rows), "val_scenes": len(val_rows),
                      "npz": manifest_out["npz_path"], "npz_bytes": manifest_out["npz_bytes"],
                      "max_J0_cohort_delta": max_j_delta, "test_data_read": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
