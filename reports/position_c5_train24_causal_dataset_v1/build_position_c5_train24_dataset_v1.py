#!/usr/bin/env python3
"""Read-only alignment and causal packaging for the fixed C5 TRAIN24 cohort."""
from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path

import h5py
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
TRAIN24 = ROOT / "reports/attitude_position_context_probe_20261024/c5_matched_train24_v1"
DT = 0.001
EVENT_DT = 0.01
LIMIT = 3.0


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def dset(group: h5py.Group, name: str) -> np.ndarray:
    if name not in group:
        raise KeyError(f"Missing HDF5 dataset: {group.name}/{name}")
    return np.asarray(group[name])


def raw_series(raw_path: Path) -> dict[str, np.ndarray]:
    """Read logged position signals only; deliberately never loads scene/physics."""
    with h5py.File(raw_path, "r") as f:
        g = f["log"]
        out = {name: dset(g, name) for name in (
            "state", "transition_time", "position_event_flag",
            "position_nominal_acceleration_mps2",
            "position_compensation_applied_acceleration_mps2",
        )}
        for optional in (
            "stage1_position_feature_14", "stage1_position_feature_input",
            "stage1_position_event_inference_valid",
            "stage1_position_event_applied_acceleration_mps2",
        ):
            if optional in g:
                out[optional] = np.asarray(g[optional])
    return out


def interval_residual(raw: dict[str, np.ndarray], event_idx: np.ndarray) -> dict[str, np.ndarray]:
    """10 ms empirical residual; event index is a 0-based transition column."""
    state = raw["state"]
    time = raw["transition_time"].reshape(-1)
    nominal = raw["position_nominal_acceleration_mps2"]
    applied = raw["position_compensation_applied_acceleration_mps2"]
    if state.shape != (12, 20001) or nominal.shape != (3, 20000) or applied.shape != (3, 20000):
        raise ValueError(f"Unexpected logged position shapes: {state.shape}, {nominal.shape}, {applied.shape}")
    offsets = np.arange(10, dtype=np.int64)
    spans = event_idx[:, None] + offsets[None, :]
    if spans.max(initial=0) >= 20000 or (event_idx + 10).max(initial=0) >= state.shape[1]:
        raise ValueError("An event lacks a complete following 10 ms interval")
    v = state[3:6]
    a_emp = (v[:, event_idx + 10] - v[:, event_idx]) / EVENT_DT
    nominal_mean = nominal[:, spans].mean(axis=2)
    applied_mean = applied[:, spans].mean(axis=2)
    y = a_emp - (nominal_mean - applied_mean)
    return {
        "event_time_s": time[event_idx],
        "interval_end_time_s": time[event_idx + 9] + DT,
        "actual_acceleration_interval_mean_mps2": a_emp.T,
        "nominal_acceleration_interval_mean_mps2": nominal_mean.T,
        "applied_acceleration_interval_mean_mps2": applied_mean.T,
        "applied_acceleration_event_mps2": applied[:, event_idx].T,
        "applied_acceleration_interval_span_mps2": (applied[:, spans].max(axis=2)
                                                       - applied[:, spans].min(axis=2)).T,
        "target_interval_raw_mps2": y.T,
    }


def label_error(y: np.ndarray, target: np.ndarray) -> dict:
    e = y - target
    corr = []
    for axis in range(3):
        if np.std(y[:, axis]) == 0 or np.std(target[:, axis]) == 0:
            corr.append(None)
        else:
            corr.append(float(np.corrcoef(y[:, axis], target[:, axis])[0, 1]))
    return {
        "bias_by_axis_mps2": e.mean(axis=0).tolist(),
        "rmse_by_axis_mps2": np.sqrt(np.mean(e * e, axis=0)).tolist(),
        "abs_error_p95_by_axis_mps2": np.quantile(np.abs(e), 0.95, axis=0).tolist(),
        "corr_by_axis": corr,
        "target_rms_by_axis_mps2": np.sqrt(np.mean(target * target, axis=0)).tolist(),
        "interval_target_rms_by_axis_mps2": np.sqrt(np.mean(y * y, axis=0)).tolist(),
        "n_events": int(len(y)),
    }


def expected_ids() -> list[str]:
    return [f"DL1018_TRAIN_T{task}_C{morph}_W{wind}"
            for task in (1, 2, 3) for morph in ("00", "15")
            for wind in ("00", "09", "12", "15")]


def meta_from_id(scene_id: str) -> dict[str, object]:
    m = re.fullmatch(r"DL1018_TRAIN_T([123])_C(\d{2})_W(\d{2})", scene_id)
    if not m:
        raise ValueError(f"Unexpected TRAIN24 scene ID: {scene_id}")
    return {"task": f"T{m.group(1)}", "class_index": int(m.group(2)),
            "wind_cell": int(m.group(3)), "validation_fold": f"holdout_W{m.group(3)}"}


def main() -> None:
    out_dir = OUT / "dataset"
    out_dir.mkdir(parents=True, exist_ok=True)
    ids = expected_ids()

    # Audit the existing position teacher labels against a logged 10 ms state difference.
    episodes = read_csv(ROOT / "logs/episode_index.csv")
    attempts = read_csv(ROOT / "logs/attempt_index.csv")
    attempt_by_id = {r["run_id"]: r for r in attempts}
    source_rows = [r for r in episodes if r["split"].lower() == "train"
                   and r["scene_id"] in ids and r["source_role"] in ("B", "POS_OFF")
                   and r["accepted"].strip().lower() == "true"]
    if len(source_rows) != 48:
        raise ValueError(f"Expected 48 accepted B/POS_OFF TRAIN24 episodes, got {len(source_rows)}")
    alignment_rows = []
    align_pred, align_target = [], []
    align_roles: list[str] = []
    for row in sorted(source_rows, key=lambda r: (r["scene_id"], r["source_role"])):
        run = attempt_by_id[row["run_id"]]
        if run["status"] != "COMPLETE" or run["returned_transitions"] != "20000" or run["finite"].lower() != "true":
            raise ValueError(f"Unsafe/incomplete original teacher run: {row['run_id']}")
        raw_path = ROOT / run["raw_path"].replace("/", "\\")
        h5_path = ROOT / row["position_event_path"].replace("/", "\\")
        with h5py.File(h5_path, "r") as f:
            plant_index = dset(f, "plant_index").reshape(-1).astype(np.int64)
            event_time = dset(f, "event_time_s").reshape(-1)
            target = np.stack([dset(f, f"target_raw_{a}").reshape(-1) for a in (1, 2, 3)], axis=1)
            ready = dset(f, "ready").reshape(-1).astype(bool)
        if len(plant_index) != 1999 or not np.array_equal(plant_index, np.arange(11, 20000, 10)):
            raise ValueError(f"Unexpected H5 event indices: {row['run_id']}")
        if not np.array_equal(ready, np.arange(1999) >= 31):
            raise ValueError(f"Unexpected ready mask: {row['run_id']}")
        if not raw_path.is_file():
            alignment_rows.append({
                "scene_id": row["scene_id"], "role": row["source_role"], "run_id": row["run_id"],
                "raw_path": run["raw_path"], "raw_status": "MISSING_ON_DISK",
                "position_event_path": row["position_event_path"],
                "position_event_sha256": sha256(h5_path),
                "event_index_one_based_first_last": [int(plant_index[0]), int(plant_index[-1])],
                "time_s_first_last": [float(event_time[0]), float(event_time[-1])],
                "units": "m/s^2", "stats": None,
            })
            continue
        raw = raw_series(raw_path)
        event_idx = np.flatnonzero(raw["position_event_flag"].reshape(-1).astype(bool))
        if len(event_idx) != 1999 or not np.array_equal(event_idx + 1, plant_index):
            raise ValueError(f"Raw/H5 event indices differ: {row['run_id']}")
        interval = interval_residual(raw, event_idx)
        if np.max(np.abs(interval["event_time_s"] - event_time), initial=0.0) > 1e-12:
            raise ValueError(f"Event time mismatch: {row['run_id']}")
        stats = label_error(interval["target_interval_raw_mps2"], target)
        alignment_rows.append({
            "scene_id": row["scene_id"], "role": row["source_role"],
            "run_id": row["run_id"], "raw_path": run["raw_path"],
            "raw_status": "PRESENT_AND_ALIGNED",
            "raw_sha256": sha256(raw_path), "position_event_path": row["position_event_path"],
            "position_event_sha256": sha256(h5_path), "event_index_one_based_first_last":
                [int(plant_index[0]), int(plant_index[-1])],
            "time_s_first_last": [float(event_time[0]), float(event_time[-1])],
            "finite_difference_definition": "(v(t+0.010)-v(t))/0.010 - mean_10ms(a_nominal-a_applied)",
            "units": "m/s^2", "stats": stats,
        })
        align_pred.append(interval["target_interval_raw_mps2"])
        align_target.append(target)
        align_roles.extend([row["source_role"]] * len(target))

    alignment = np.concatenate(align_pred)
    teacher_target = np.concatenate(align_target)
    alignment_summary = label_error(alignment, teacher_target)
    align_roles_array = np.asarray(align_roles, dtype=object)
    alignment_by_role = {
        role: label_error(alignment[align_roles_array == role], teacher_target[align_roles_array == role])
        for role in ("B", "POS_OFF")
    }
    aligned_by_role = {role: sum(r["role"] == role and r["raw_status"] == "PRESENT_AND_ALIGNED"
                                 for r in alignment_rows) for role in ("B", "POS_OFF")}
    missing_by_role = {role: sum(r["role"] == role and r["raw_status"] == "MISSING_ON_DISK"
                                 for r in alignment_rows) for role in ("B", "POS_OFF")}

    # Package C5 on-policy X14/action/outcome pairs, preserving one sequence per scene.
    c5_rows = []
    arrays = {k: [] for k in (
        "x14_logged", "x14_model_input", "target_interval_raw_mps2",
        "target_interval_clip_mps2", "delta_target_post_clip_mps2",
        "applied_acceleration_event_mps2", "applied_acceleration_interval_mean_mps2",
        "applied_acceleration_interval_span_mps2", "actual_acceleration_interval_mean_mps2",
        "nominal_acceleration_interval_mean_mps2", "event_time_s", "interval_end_time_s", "ready_mask",
    )}
    scene_metadata = []
    for scene_id in ids:
        meta = meta_from_id(scene_id)
        attempt_dir = TRAIN24 / "runs" / scene_id / "attempt_01"
        status_path = attempt_dir / "run_status.json"
        raw_path = attempt_dir / "raw_run.mat"
        status = json.loads(status_path.read_text(encoding="utf-8"))
        if (status.get("status") != "RUN_COMPLETE_STABLE" or status.get("canonical_scene_id") != scene_id
                or status.get("transitions") != 20000 or status.get("state_samples") != 20001
                or status.get("safety_stop_reason") or status.get("TEST_accessed") is not False
                or status.get("training_steps") != 0 or status.get("optimizer_steps") != 0):
            raise ValueError(f"C5 status/safety/input lock failed: {scene_id}")
        raw_sha = sha256(raw_path)
        if raw_sha.lower() != str(status.get("raw_sha256", "")).lower():
            raise ValueError(f"C5 raw SHA mismatch: {scene_id}")
        raw = raw_series(raw_path)
        event_idx = np.flatnonzero(raw["position_event_flag"].reshape(-1).astype(bool))
        if len(event_idx) != 1999:
            raise ValueError(f"Expected 1999 position events, got {len(event_idx)}: {scene_id}")
        interval = interval_residual(raw, event_idx)
        with h5py.File(raw_path, "r") as f:
            g = f["log"]
            feature = dset(g, "stage1_position_feature_14")[:, event_idx].T
            model_input = dset(g, "stage1_position_feature_input")[:, event_idx].T
            ready = dset(g, "stage1_position_event_inference_valid").reshape(-1)[event_idx].astype(bool)
            action_event = dset(g, "position_compensation_applied_acceleration_mps2")[:, event_idx].T
            stage1_action = dset(g, "stage1_position_event_applied_acceleration_mps2")[:, event_idx].T
            event_flag = dset(g, "stage1_position_event").reshape(-1)[event_idx].astype(bool)
            step_index = dset(g, "stage1_position_event_step_index").reshape(-1).astype(np.int64)
            coordinate_mask = dset(g, "stage1_position_coordinate_mask").reshape(-1).tolist()
            feature_source_hash = status.get("release_sha256")
        if feature.shape != (1999, 14) or model_input.shape != (1999, 14):
            raise ValueError(f"Unexpected X14 shapes for {scene_id}: {feature.shape}, {model_input.shape}")
        if not np.isfinite(feature).all() or not np.isfinite(model_input).all() or not np.isfinite(action_event).all():
            raise ValueError(f"Non-finite C5 event features/actions: {scene_id}")
        if int(ready.sum()) != 1968 or not np.array_equal(ready, np.arange(1999) >= 31):
            raise ValueError(f"C5 readiness mismatch: {scene_id}")
        if int(event_flag.sum()) != 1999:
            raise ValueError(f"C5 stage1 event count mismatch: {scene_id}")
        if len(step_index) != 1968 or not np.array_equal(step_index, event_idx[ready] + 1):
            raise ValueError(f"C5 ready event step indices do not match feature columns: {scene_id}")
        if not np.isfinite(stage1_action[ready]).all() or np.isfinite(stage1_action[~ready]).any():
            raise ValueError(f"C5 stage1 action readiness values mismatch: {scene_id}")
        stage1_delta = np.max(np.abs(stage1_action[ready] - action_event[ready]), initial=0.0)
        if stage1_delta > 1e-9:
            raise ValueError(f"C5 event action differs from actual applied action: {scene_id}")
        feature_input_delta = np.max(np.abs(model_input - feature), initial=0.0)
        action_interval_delta = np.max(np.abs(interval["applied_acceleration_interval_mean_mps2"]
                                              - interval["applied_acceleration_event_mps2"]), initial=0.0)
        y = interval["target_interval_raw_mps2"]
        y_clip = np.clip(y, -LIMIT, LIMIT)
        delta = y_clip - action_event
        delta[~ready] = np.nan
        arrays["x14_logged"].append(feature.astype(np.float32))
        arrays["x14_model_input"].append(model_input.astype(np.float32))
        arrays["target_interval_raw_mps2"].append(y.astype(np.float32))
        arrays["target_interval_clip_mps2"].append(y_clip.astype(np.float32))
        arrays["delta_target_post_clip_mps2"].append(delta.astype(np.float32))
        arrays["applied_acceleration_event_mps2"].append(action_event.astype(np.float32))
        for key in ("applied_acceleration_interval_mean_mps2", "applied_acceleration_interval_span_mps2",
                    "actual_acceleration_interval_mean_mps2", "nominal_acceleration_interval_mean_mps2",
                    "event_time_s", "interval_end_time_s"):
            arrays[key].append(interval[key].astype(np.float32))
        arrays["ready_mask"].append(ready)
        scene_metadata.append({
            "scene_id": scene_id, **meta, "raw_path": str(raw_path.relative_to(ROOT)).replace("\\", "/"),
            "raw_sha256": raw_sha, "status_path": str(status_path.relative_to(ROOT)).replace("\\", "/"),
            "status_sha256": sha256(status_path), "run_start_path": str((attempt_dir / "run_start.mat").relative_to(ROOT)).replace("\\", "/"),
            "run_start_sha256": sha256(attempt_dir / "run_start.mat"),
            "release_sha256": feature_source_hash, "plant_calls": status.get("plant_calls"),
            "feature_shape": [1999, 14], "valid_events": int(ready.sum()),
            "stage1_event_count": int(event_flag.sum()), "coordinate_mask": coordinate_mask,
            "stage1_vs_actual_action_max_abs_mps2": float(stage1_delta),
            "feature_input_vs_logged_feature_max_abs": float(feature_input_delta),
            "event_applied_vs_following_10ms_mean_max_abs_mps2": float(action_interval_delta),
            "max_within_interval_applied_action_span_mps2":
                np.max(interval["applied_acceleration_interval_span_mps2"], axis=0).tolist(),
            "label_clip_fraction": float(np.mean(np.abs(y) > LIMIT)),
        })

    npz_path = out_dir / "C5_TRAIN24_POSITION_CAUSAL_PAIRS_v1.npz"
    np.savez_compressed(npz_path,
                        scene_ids=np.asarray(ids, dtype="U32"),
                        wind_cells=np.asarray([meta_from_id(s)["wind_cell"] for s in ids], dtype=np.int16),
                        **{k: np.stack(v) for k, v in arrays.items()})

    wind_folds = {}
    for wind in (0, 9, 12, 15):
        val_ids = [s for s in ids if meta_from_id(s)["wind_cell"] == wind]
        train_ids = [s for s in ids if s not in val_ids]
        wind_folds[f"holdout_W{wind:02d}"] = {"train_scene_ids": train_ids,
                                               "validation_scene_ids": val_ids,
                                               "train_scene_count": len(train_ids),
                                               "validation_scene_count": len(val_ids)}
    teacher_manifest = read_csv(ROOT / "experiments/teacher_reuse_model_screen_v1/manifests/teacher_reuse_manifest.csv")
    global_missing = {}
    for role in ("B", "POS_OFF"):
        rows = [r for r in teacher_manifest if r["split"] == "train" and r["role"] == role]
        if len(rows) != 768:
            raise ValueError(f"Expected 768 original TRAIN {role} teacher episodes, found {len(rows)}")
        global_missing[role] = sum(not (ROOT / r["raw_path"].replace("/", "\\")).is_file() for r in rows)
    alignment_report = {
        "schema": "POSITION_TRAIN24_H5_VS_10MS_FINITE_DIFFERENCE_ALIGNMENT_V1",
        "scope": "TRAIN24 B/POS_OFF only; no TEST, Plant, training, or inertia reconstruction",
        "episode_count": len(alignment_rows), "raw_aligned_episode_count": len(align_pred),
        "raw_missing_episode_count": sum(r.get("raw_status") == "MISSING_ON_DISK" for r in alignment_rows),
        "scene_count": len(ids),
        "raw_alignment_available_by_role": aligned_by_role,
        "raw_missing_by_role": missing_by_role,
        "units": "m/s^2", "event_indexing": {
            "H5_plant_index": "1-based transition index; first=11,last=19991",
            "raw_transition_column": "0-based HDF5 column = plant_index - 1; first=10,last=19990",
            "interval": "10 transitions beginning at the event column; state velocity difference uses columns i and i+10",
            "H5_event_time_equals_raw_transition_time_at_event": True,
        },
        "finite_difference_formula": "(v[i+10]-v[i])/0.010 - mean(nominal_acceleration[:,i:i+10] - applied_acceleration[:,i:i+10])",
        "pooled_stats": alignment_summary, "pooled_stats_by_role": alignment_by_role,
        "global_TRAIN_raw_availability_by_role": {
            role: {"episodes": 768, "present": 768 - global_missing[role], "missing": global_missing[role]}
            for role in ("B", "POS_OFF")
        },
        "episodes": alignment_rows,
    }
    align_path = OUT / "POSITION_TRAIN24_LABEL_ALIGNMENT_v1.json"
    align_path.write_text(json.dumps(alignment_report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")

    manifest = {
        "schema": "C5_TRAIN24_POSITION_CAUSAL_DATASET_V1", "status": "PASS_READ_ONLY_DATASET_BUILT",
        "data_path": str(npz_path.relative_to(ROOT)).replace("\\", "/"),
        "data_sha256": sha256(npz_path), "shape": {k: list(v.shape) for k, v in np.load(npz_path).items()},
        "created_by": str(Path(__file__).relative_to(ROOT)).replace("\\", "/"),
        "builder_sha256": sha256(Path(__file__)),
        "scope": {"scene_count": 24, "event_count_per_scene": 1999, "ready_event_count_per_scene": 1968,
                  "source": "C5 matched DSSM14/M110/PCF TRAIN24 raw trajectories",
                  "position_features": "logged stage1_position_feature_14 and stage1_position_feature_input (X14), read at event t",
                  "target_interval": "measured velocity 10ms difference minus mean logged nominal-minus-applied acceleration",
                  "current_applied": "logged position_compensation_applied_acceleration_mps2 at event t",
                  "delta_target": "clip(target_interval_raw,-3,3)-current_applied, only for 1968 ready events",
                  "units": "position feature mixed physical units; targets/actions m/s^2",
                  "no_inertia_reconstruction": True, "TEST_accessed": False, "Plant_calls": 0,
                  "optimizer_steps": 0},
        "teacher_label_alignment_path": str(align_path.relative_to(ROOT)).replace("\\", "/"),
        "teacher_label_alignment_sha256": sha256(align_path),
        "teacher_label_alignment_pooled_stats": alignment_summary,
        "teacher_label_alignment_raw_available_by_role": aligned_by_role,
        "teacher_label_alignment_raw_missing_by_role": missing_by_role,
        "teacher_B_POS_OFF_exact_scene_pairs": {"episodes": len(alignment_rows), "scenes": len(ids),
                                                  "roles": ["B", "POS_OFF"],
                                                  "same_canonical_ids_as_C5": True},
        "scene_folds": wind_folds, "scenes": scene_metadata,
        "interpretation_limits": [
            "The C5 interval target is a measured 10 ms average; the original B/POS_OFF H5 target is an instantaneous physical derivative. Their observed difference is reported, not assumed zero.",
            "A held-out scene in this manifest is held out by the new dataset fold only; any baseline model trained on all original TRAIN data must be disclosed when claiming independent validation.",
            "This package contains inputs, logged actions, and empirical interval labels; it does not establish a closed-loop performance gain.",
        ],
    }
    manifest_path = OUT / "C5_TRAIN24_POSITION_CAUSAL_MANIFEST_v1.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": manifest["status"], "episodes_aligned": len(alignment_rows),
                      "raw_alignment_available_by_role": aligned_by_role,
                      "raw_missing_by_role": missing_by_role,
                      "global_raw_missing_by_role": global_missing,
                      "alignment_pooled_stats_by_role": alignment_by_role,
                      "alignment_pooled_stats": alignment_summary, "C5_scenes": len(scene_metadata),
                      "C5_ready_events": int(sum(x["valid_events"] for x in scene_metadata)),
                      "max_C5_feature_input_delta": max(x["feature_input_vs_logged_feature_max_abs"] for x in scene_metadata),
                      "max_C5_event_vs_interval_applied_delta_mps2": max(x["event_applied_vs_following_10ms_mean_max_abs_mps2"] for x in scene_metadata),
                      "data_path": manifest["data_path"], "data_sha256": manifest["data_sha256"],
                      "manifest_path": str(manifest_path.relative_to(ROOT)).replace("\\", "/")},
                     indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
