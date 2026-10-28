from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import h5py
import numpy as np


ROOT = Path(__file__).resolve().parents[3]
TASK_ROOT = Path(__file__).resolve().parent
SOURCE_TASK_ROOT = ROOT / "experiments/dl_attitude_replacement_20261026/gru_stream_c5_teacher_v1"
SOURCE_LOCK_PATH = SOURCE_TASK_ROOT / "GRU_STREAM_C5_TEACHER_SOURCE_LOCK_v1.json"
LOCKED_CFG_PATH = ROOT / "experiments/dl_attitude_replacement_20261026/gru_stream_dev_v1/LOCKED_CFG.json"
OUTPUT_NPZ = TASK_ROOT / "nominal_command_target_v1.npz"
STATS_CSV = TASK_ROOT / "TARGET_STATS_v1.csv"
MANIFEST_PATH = TASK_ROOT / "MANIFEST_v1.json"
RECEIPT_PATH = TASK_ROOT / "PREPARATION_RECEIPT_v1.json"
DT = 0.001
EVENT_STARTS = np.arange(10, 19991, 10, dtype=np.int64)
EVENT_COUNT = 1999
PHASES = (
    ("all", 0.0, 20.0),
    ("0-5s", 0.0, 5.0),
    ("5-15s", 5.0, 15.0),
    ("15-20s", 15.0, 20.0),
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def sha256_array(array: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def decode_matlab_u16(value: np.ndarray) -> str:
    return "".join(chr(int(v)) for v in np.asarray(value).reshape(-1) if int(v)).rstrip("\x00")


def rms(value: np.ndarray) -> float:
    value = np.asarray(value, dtype=np.float64)
    return float(np.sqrt(np.mean(value * value)))


def main() -> None:
    for path in (OUTPUT_NPZ, STATS_CSV, MANIFEST_PATH, RECEIPT_PATH):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite prepared data: {path}")

    lock = json.loads(SOURCE_LOCK_PATH.read_text(encoding="utf-8"))
    if lock.get("status") != "APPROVED_FOR_TRAINING":
        raise ValueError("the bound C5 source lock is not the approved historical source lock")
    if (lock.get("data_read_flags", {}).get("B24_values_read") is not False
            or lock.get("data_read_flags", {}).get("TEST48_read") is not False):
        raise ValueError("historical C5 lock does not exclude B24/TEST48")
    source_lock_sha = sha256_file(SOURCE_LOCK_PATH)
    dataset_path = ROOT / lock["dataset"]["path"]
    dataset_manifest_path = ROOT / lock["dataset"]["manifest_path"]
    if sha256_file(dataset_path) != lock["dataset"]["sha256"]:
        raise ValueError("source NPZ SHA-256 differs from the approved C5 lock")
    if sha256_file(dataset_manifest_path) != lock["dataset"]["manifest_sha256"]:
        raise ValueError("source dataset-manifest SHA-256 differs from the approved C5 lock")

    # Load only C5 feature and ID members. The NPZ's B24 and old teacher-Y members stay unopened.
    with np.load(dataset_path, allow_pickle=False) as archive:
        train_x = np.asarray(archive["c5_train_x"])
        train_ids = np.asarray(archive["c5_train_scene_ids"])
        val_x = np.asarray(archive["c5_val_x"])
        val_ids = np.asarray(archive["c5_val_scene_ids"])
    if train_x.shape != (24, EVENT_COUNT, 13) or train_x.dtype != np.float32:
        raise ValueError(f"unexpected C5 train feature shape/dtype: {train_x.shape}/{train_x.dtype}")
    if val_x.shape != (48, EVENT_COUNT, 13) or val_x.dtype != np.float32:
        raise ValueError(f"unexpected C5 val feature shape/dtype: {val_x.shape}/{val_x.dtype}")
    if train_ids.shape != (24,) or val_ids.shape != (48,):
        raise ValueError("unexpected C5 scene-ID shape")
    if not np.isfinite(train_x).all() or not np.isfinite(val_x).all():
        raise ValueError("C5 input features contain non-finite values")
    if (sha256_array(train_x) != lock["dataset"]["selected_array_sha256"]["c5_train_x"]
            or sha256_array(val_x) != lock["dataset"]["selected_array_sha256"]["c5_val_x"]):
        raise ValueError("C5 X arrays differ from the approved source-lock hashes")

    source_cfg = json.loads(LOCKED_CFG_PATH.read_text(encoding="utf-8"))
    cfg_snapshot_path = Path(source_cfg["cfg_snapshot_path"])
    if sha256_file(cfg_snapshot_path) != source_cfg["c5_snapshot_sha256"]:
        raise ValueError("bound C5 cfg snapshot SHA-256 mismatch")
    J0 = np.asarray(source_cfg["J0_kgm2"], dtype=np.float64)
    if J0.shape != (3, 3) or not np.isfinite(J0).all() or np.linalg.eigvalsh(J0).min() <= 0:
        raise ValueError("locked nominal J0 is invalid")
    # Read only the allowed DMAX node from the bound C5 cfg snapshot; do not load other cfg fields.
    with h5py.File(cfg_snapshot_path, "r") as cfg_file:
        dmax = np.asarray(cfg_file["cfg/rbf/attitude/dmax"], dtype=np.float64).reshape(-1)
    if dmax.shape != (3,) or not np.isfinite(dmax).all() or np.any(dmax <= 0):
        raise ValueError("locked attitude DMAX is invalid")

    sources = lock["scene_sources"]
    source_by_id = {row["scene_id"]: row for row in sources}
    expected_train_ids = [row["scene_id"] for row in sources if row["source_split"] == "TRAIN_C5_24"]
    expected_val_ids = [row["scene_id"] for row in sources if row["source_split"] == "C5_VAL48"]
    train_ids_text, val_ids_text = [str(v) for v in train_ids], [str(v) for v in val_ids]
    if train_ids_text != expected_train_ids or val_ids_text != expected_val_ids:
        raise ValueError("C5 NPZ scene IDs/order differ from the locked raw/status scene order")
    if len(source_by_id) != 72 or len(train_ids_text) != 24 or len(val_ids_text) != 48:
        raise ValueError("the locked C5 source identity must contain exactly TRAIN24+VAL48")

    train_y64 = np.empty((24, EVENT_COUNT, 3), dtype=np.float64)
    val_y64 = np.empty((48, EVENT_COUNT, 3), dtype=np.float64)
    train_y32 = np.empty((24, EVENT_COUNT, 3), dtype=np.float32)
    val_y32 = np.empty((48, EVENT_COUNT, 3), dtype=np.float32)
    source_records: list[dict[str, Any]] = []
    stat_rows: list[dict[str, Any]] = []
    intervals_for = np.arange(EVENT_COUNT, dtype=np.int64)
    event_times_reference: np.ndarray | None = None

    for split_name, ids, y64_out, y32_out in (
        ("TRAIN_C5_24", train_ids_text, train_y64, train_y32),
        ("C5_VAL48_AS_DEV_TRAIN", val_ids_text, val_y64, val_y32),
    ):
        source_split = "TRAIN_C5_24" if split_name == "TRAIN_C5_24" else "C5_VAL48"
        for scene_index, scene_id in enumerate(ids):
            source = source_by_id[scene_id]
            if source["source_split"] != source_split:
                raise ValueError(f"source split mismatch for {scene_id}")
            raw_path, status_path = ROOT / source["raw_path"], ROOT / source["status_path"]
            if (not raw_path.is_file() or sha256_file(raw_path) != source["raw_sha256"]
                    or not status_path.is_file() or sha256_file(status_path) != source["status_sha256"]):
                raise ValueError(f"C5 raw/status SHA mismatch for {scene_id}")

            with h5py.File(raw_path, "r") as raw_file:
                raw_id = decode_matlab_u16(np.asarray(raw_file["runIdentity/scene_id"]))
                if raw_id != scene_id:
                    raise ValueError(f"raw scene identity mismatch: {scene_id} vs {raw_id}")
                if int(np.asarray(raw_file["runIdentity/TEST_accessed"]).reshape(-1)[0]) != 0:
                    raise ValueError(f"C5 raw marks TEST access: {scene_id}")
                log = raw_file["log"]
                state = np.asarray(log["state"], dtype=np.float64)
                time = np.asarray(log["time"], dtype=np.float64).reshape(-1)
                requested = np.asarray(log["requested_generalized"], dtype=np.float64)
                event_flag = np.asarray(log["attitude_event_flag"]).reshape(-1).astype(bool)
                # Historical teacher output is read only for a diagnostic comparison, never to form labels.
                teacher_at_events = np.asarray(log["rbf_output_raw"], dtype=np.float64)[:, EVENT_STARTS].T

            if state.shape != (12, 20001) or time.shape != (20001,) or requested.shape != (4, 20000):
                raise ValueError(f"raw interval shape mismatch for {scene_id}")
            if not np.array_equal(np.flatnonzero(event_flag), EVENT_STARTS):
                raise ValueError(f"raw event indices do not match zero-based 10:10:19990 for {scene_id}")
            if not np.isfinite(state).all() or not np.isfinite(time).all() or not np.isfinite(requested).all():
                raise ValueError(f"non-finite permitted raw field for {scene_id}")
            if teacher_at_events.shape != (EVENT_COUNT, 3) or not np.isfinite(teacher_at_events).all():
                raise ValueError(f"historical teacher event trace shape/value mismatch for {scene_id}")
            dt = np.diff(time)
            if not np.allclose(dt, DT, rtol=0.0, atol=1e-12):
                raise ValueError(f"raw time step is not 1 ms for {scene_id}")
            if not np.allclose(time[EVENT_STARTS + 10] - time[EVENT_STARTS], 10 * DT, rtol=0.0, atol=1e-12):
                raise ValueError(f"event interval duration mismatch for {scene_id}")
            if event_times_reference is None:
                event_times_reference = time[EVENT_STARTS].copy()
            elif not np.array_equal(event_times_reference, time[EVENT_STARTS]):
                raise ValueError("C5 scene event schedules differ")

            omega = state[9:12, :].T
            tau_req = requested[1:4, :].T
            coriolis_minus_requested = np.cross(omega[:-1], omega[:-1] @ J0.T) - tau_req
            nominal_accel_rhs = np.linalg.solve(J0, coriolis_minus_requested.T).T
            interval_mean = np.stack([
                np.mean(nominal_accel_rhs[e:e + 10], axis=0) for e in EVENT_STARTS
            ])
            endpoint_derivative = (
                omega[EVENT_STARTS + 10] - omega[EVENT_STARTS]
            ) / (time[EVENT_STARTS + 10] - time[EVENT_STARTS])[:, None]
            target = endpoint_derivative + interval_mean
            clipped = np.clip(target, -dmax[None, :], dmax[None, :]).astype(np.float32)
            if not np.isfinite(target).all() or not np.isfinite(clipped).all():
                raise ValueError(f"non-finite nominal command residual for {scene_id}")
            y64_out[scene_index] = target
            y32_out[scene_index] = clipped

            # Cross-check the first 1998 intervals against the approved next-event residual convention.
            # This independent diagonal-J0 form mirrors the earlier target-semantics audit.
            diag_J0 = np.diag(J0)
            end_indices = EVENT_STARTS[1:]
            start_indices = end_indices - 10
            omega_windows = omega[start_indices[:, None] + np.arange(10)[None, :]]
            gyro_diag = np.cross(omega_windows, omega_windows * diag_J0[None, None, :])
            torque_windows = tau_req[start_indices[:, None] + np.arange(10)[None, :]]
            legacy_next = (
                (omega[end_indices] - omega[start_indices]) /
                (time[end_indices] - time[start_indices])[:, None]
                + np.mean((gyro_diag - torque_windows) / diag_J0[None, None, :], axis=1)
            )
            legacy_alignment_max = float(np.max(np.abs(target[:-1] - legacy_next)))
            if legacy_alignment_max > 1e-10:
                raise ValueError(f"first-1998 next-event alignment error {legacy_alignment_max:g} for {scene_id}")

            starts_time = time[EVENT_STARTS]
            for phase, lo, hi in PHASES:
                mask = np.ones(EVENT_COUNT, dtype=bool) if phase == "all" else ((starts_time >= lo) & (starts_time < hi))
                for axis in range(3):
                    old_teacher = teacher_at_events[mask, axis]
                    raw_axis = target[mask, axis]
                    clipped_axis = clipped[mask, axis].astype(np.float64)
                    err_raw = raw_axis - old_teacher
                    err_clip = clipped_axis - old_teacher
                    clip_mask = np.abs(target[:, axis]) > dmax[axis]
                    stat_rows.append({
                        "scene_id": scene_id, "training_split": split_name, "source_split": source_split,
                        "phase": phase, "samples": int(mask.sum()), "axis": axis + 1,
                        "clip_count": int(np.count_nonzero(clip_mask & mask)),
                        "clip_ratio": float(np.count_nonzero(clip_mask & mask) / mask.sum()),
                        "dmax": float(dmax[axis]),
                        "unclipped_rms": rms(raw_axis), "unclipped_bias": float(np.mean(raw_axis)),
                        "clipped_float32_rms": rms(clipped_axis), "clipped_float32_bias": float(np.mean(clipped_axis)),
                        "old_teacher_post_dmax_pre_beta_rms": rms(old_teacher),
                        "unclipped_minus_old_teacher_rms": rms(err_raw),
                        "unclipped_minus_old_teacher_bias": float(np.mean(err_raw)),
                        "clipped_minus_old_teacher_rms": rms(err_clip),
                        "clipped_minus_old_teacher_bias": float(np.mean(err_clip)),
                        "legacy_next_event_max_abs_error_first1998": legacy_alignment_max,
                    })

            source_records.append({
                "scene_id": scene_id, "training_split": split_name, "source_split": source_split,
                "raw_path": source["raw_path"], "raw_sha256": source["raw_sha256"],
                "status_path": source["status_path"], "status_sha256": source["status_sha256"],
                "event_count": EVENT_COUNT, "state_shape": [12, 20001], "time_shape": [20001],
                "requested_generalized_shape": [4, 20000],
                "event_indices_zero_based_sha256": sha256_array(EVENT_STARTS),
                "X_array_sha256": sha256_array(train_x[scene_index] if split_name == "TRAIN_C5_24" else val_x[scene_index]),
                "unclipped_R_cmd_sha256": sha256_array(target),
                "clipped_R_cmd_float32_sha256": sha256_array(clipped),
                "historical_teacher_comparison_field": "log/rbf_output_raw sampled at attitude_event_flag; not used to construct target",
                "legacy_next_event_alignment_max_abs_error_first1998": legacy_alignment_max,
                "additional_final_interval": "19990->20000 included",
            })

    np.savez_compressed(
        OUTPUT_NPZ,
        c5_train_y_unclipped_float64=train_y64,
        c5_train_y_clipped_float32=train_y32,
        c5_val_y_unclipped_float64=val_y64,
        c5_val_y_clipped_float32=val_y32,
        c5_train_scene_ids=train_ids,
        c5_val_scene_ids=val_ids,
        event_start_indices_zero_based=EVENT_STARTS.astype(np.int32),
    )
    with STATS_CSV.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(stat_rows[0]))
        writer.writeheader()
        writer.writerows(stat_rows)

    summary = {}
    for split_name, y64, y32 in (
        ("TRAIN_C5_24", train_y64, train_y32),
        ("C5_VAL48_AS_DEV_TRAIN", val_y64, val_y32),
    ):
        count = y64.shape[0] * y64.shape[1]
        clipped64 = y32.astype(np.float64)
        clip_count = np.count_nonzero(np.abs(y64) > dmax[None, None, :], axis=(0, 1))
        summary[split_name] = {
            "scene_count": int(y64.shape[0]), "events_per_scene": EVENT_COUNT,
            "unclipped_rms_by_axis": np.sqrt(np.mean(y64 * y64, axis=(0, 1))).tolist(),
            "unclipped_bias_by_axis": np.mean(y64, axis=(0, 1)).tolist(),
            "clipped_float32_rms_by_axis": np.sqrt(np.mean(clipped64 * clipped64, axis=(0, 1))).tolist(),
            "clipped_float32_bias_by_axis": np.mean(clipped64, axis=(0, 1)).tolist(),
            "clip_count_by_axis": clip_count.astype(int).tolist(),
            "clip_ratio_by_axis": (clip_count / count).tolist(),
            "unclipped_array_sha256": sha256_array(y64),
            "clipped_float32_array_sha256": sha256_array(y32),
            "scene_id_array_sha256": sha256_array(train_ids if split_name == "TRAIN_C5_24" else val_ids),
        }

    manifest = {
        "schema": "DL1018_NOMINAL_COMMAND_TARGET_DATA_V1",
        "status": "PASS_OFFLINE_C5_LABEL_PREPARATION",
        "candidate_for_future_training": "GRU32_STREAM72_COSINE_S2026102001_WITH_NOMINAL_COMMAND_TARGET",
        "source_lock": {"path": SOURCE_LOCK_PATH.resolve().relative_to(ROOT).as_posix(), "sha256": source_lock_sha},
        "source_npz": {"path": dataset_path.resolve().relative_to(ROOT).as_posix(),
                        "sha256": lock["dataset"]["sha256"], "bytes": dataset_path.stat().st_size,
                        "loaded_members_only": ["c5_train_x", "c5_train_scene_ids", "c5_val_x", "c5_val_scene_ids"],
                        "B24_arrays_loaded": False, "old_c5_teacher_Y_arrays_loaded": False},
        "source_dataset_manifest": {"path": dataset_manifest_path.resolve().relative_to(ROOT).as_posix(),
                                     "sha256": lock["dataset"]["manifest_sha256"]},
        "source_locked_cfg": {"path": LOCKED_CFG_PATH.resolve().relative_to(ROOT).as_posix(),
                               "sha256": sha256_file(LOCKED_CFG_PATH),
                               "cfg_snapshot_path": str(cfg_snapshot_path),
                               "cfg_snapshot_sha256": source_cfg["c5_snapshot_sha256"],
                               "dmax_source": source_cfg["dmax_source"],
                               "dmax_exact_float64": dmax.tolist(),
                               "J0_kgm2_exact_float64": J0.tolist(), "J0_sha256": source_cfg["J0_sha256"]},
        "splits": {
            "TRAIN_C5_24": {"count": 24, "scene_ids": train_ids_text,
                            "X_shape": list(train_x.shape), "X_dtype": str(train_x.dtype),
                            "X_sha256": sha256_array(train_x)},
            "C5_VAL48_AS_DEV_TRAIN": {"source_split": "C5_VAL48", "count": 48,
                                      "scene_ids": val_ids_text, "X_shape": list(val_x.shape),
                                      "X_dtype": str(val_x.dtype), "X_sha256": sha256_array(val_x)},
        },
        "target_contract": {
            "name": "nominal requested-command port residual",
            "equation": "R_cmd[e]=(omega[e+10]-omega[e])/(t[e+10]-t[e])+mean_i solve(J0,cross(omega[i],J0*omega[i])-tau_req[i]); i=e..e+9",
            "tau_req": "requested_generalized rows MATLAB 2:4 (Python 1:4); realized_generalized is not read or used",
            "units": "rad/s^2", "post_clip_stage": "post-DMAX/pre-beta",
            "dmax_clip": "independent axis-wise clip to the exact locked DMAX, then cast to float32",
            "stored_unclipped_dtype": "float64", "stored_training_dtype": "float32",
        },
        "event_schedule": {
            "zero_based_event_starts": {"start": 10, "step": 10, "end_inclusive": 19990, "count_per_scene": EVENT_COUNT},
            "interval": "[e,e+10); includes final 19990->20000 interval",
            "raw_shape_per_scene": {"state": [12, 20001], "time": [20001], "requested_generalized": [4, 20000]},
            "time_step_s": DT, "endpoint_span_s": 0.01,
            "first1998_alignment": "matches prior next-event residual convention; per-scene max error in source_records",
            "final_interval_is_new": True,
        },
        "phase_definitions": {"all": "all 1999 event starts", "0-5s": "0<=t<5",
                              "5-15s": "5<=t<15", "15-20s": "15<=t<20"},
        "label_summary_by_split": summary,
        "source_records": source_records,
        "raw_fields_read": ["log/state", "log/time", "log/requested_generalized", "log/attitude_event_flag",
                            "log/rbf_output_raw (offline comparison only)"],
        "prohibited_sources_not_read": ["B24 values", "TEST values", "Jtrue", "Jhat", "Jdot", "Ctrue", "realized_generalized values", "wind", "mass"],
        "deploy_input_contract": "X is reused byte-identically from C5 NPZ. Future interval data is label-only and is not a deployment feature.",
        "approximations_and_limits": [
            "Finite 10 ms gyro endpoint difference plus interval-mean nominal gyroscopic/requested-torque term; not instantaneous aerodynamic torque.",
            "Residual lumps allocator/command-port mismatch and unmodelled dynamics relative to fixed J0 command model.",
            "Ideal noiseless recorded state and requested command; no sensor noise or interpolation model.",
            "C5_VAL48_AS_DEV_TRAIN is included in training and is not independent validation.",
        ],
        "outputs": {
            "target_npz_path": OUTPUT_NPZ.resolve().relative_to(ROOT).as_posix(),
            "target_npz_sha256": sha256_file(OUTPUT_NPZ), "target_npz_bytes": OUTPUT_NPZ.stat().st_size,
            "stats_csv_path": STATS_CSV.resolve().relative_to(ROOT).as_posix(),
            "stats_csv_sha256": sha256_file(STATS_CSV),
            "train_unclipped_shape": list(train_y64.shape), "train_unclipped_dtype": str(train_y64.dtype),
            "train_clipped_shape": list(train_y32.shape), "train_clipped_dtype": str(train_y32.dtype),
            "val_unclipped_shape": list(val_y64.shape), "val_unclipped_dtype": str(val_y64.dtype),
            "val_clipped_shape": list(val_y32.shape), "val_clipped_dtype": str(val_y32.dtype),
            "total_output_bytes": OUTPUT_NPZ.stat().st_size + STATS_CSV.stat().st_size,
            "budget_bytes": 1024**3,
        },
        "builder_source": {"path": Path(__file__).resolve().relative_to(ROOT).as_posix(),
                           "sha256": sha256_file(Path(__file__).resolve())},
        "training_started": False, "optimizer_steps": 0, "Plant_called": False, "TEST_read": False,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    receipt = {
        "schema": "DL1018_NOMINAL_COMMAND_TARGET_PREPARATION_RECEIPT_V1",
        "status": "PASS_OFFLINE_C5_LABEL_PREPARATION",
        "command": "python experiments/dl_attitude_replacement_20261026/nominal_command_target_data_v1/build_nominal_command_target_v1.py",
        "exit_code": 0, "source_lock_sha256": source_lock_sha,
        "manifest_sha256": sha256_file(MANIFEST_PATH), "target_npz_sha256": sha256_file(OUTPUT_NPZ),
        "stats_csv_sha256": sha256_file(STATS_CSV), "training_started": False,
        "optimizer_steps": 0, "Plant_called": False, "TEST_read": False,
        "B24_values_loaded": False, "realized_generalized_used": False,
        "output_bytes": manifest["outputs"]["total_output_bytes"], "budget_bytes": 1024**3,
    }
    RECEIPT_PATH.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": manifest["status"], "scenes": len(source_records),
                      "events_per_scene": EVENT_COUNT, "target_shape_train": list(train_y64.shape),
                      "target_shape_val": list(val_y64.shape), "raw_status_identity_pairs": len(source_records),
                      "legacy_first1998_max_error": max(r["legacy_next_event_alignment_max_abs_error_first1998"] for r in source_records),
                      "clip_count_total_by_axis": (np.count_nonzero(np.abs(np.concatenate((train_y64, val_y64), axis=0)) > dmax[None, None, :], axis=(0, 1))).tolist(),
                      "npz_sha256": sha256_file(OUTPUT_NPZ), "manifest_sha256": sha256_file(MANIFEST_PATH),
                      "Plant_called": False, "TEST_read": False}, indent=2))


if __name__ == "__main__":
    main()
