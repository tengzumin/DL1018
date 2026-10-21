from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import h5py
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "experiments" / "teacher_reuse_model_screen_v1"
TASKS = ("HELIX", "FIG8_3D", "SQUARE")
ROLES = ("B", "POS_OFF")
PHASES = ("STATIC", "PRE", "EXTEND", "HOLD", "RETRACT", "RECOVERY")
FEATURES = [
    ("e_x", "m"), ("e_y", "m"), ("e_z", "m"),
    ("s_x", "m/s"), ("s_y", "m/s"), ("s_z", "m/s"),
    ("roll", "rad"), ("pitch", "rad"), ("yaw", "rad"),
    ("preview_thrust_per_mass", "m/s^2"),
    ("arm_command_1", "dimensionless {-1,0,1}"),
    ("arm_command_2", "dimensionless {-1,0,1}"),
    ("arm_command_3", "dimensionless {-1,0,1}"),
    ("arm_command_4", "dimensionless {-1,0,1}"),
]
EXTRA_FEATURES = [
    ("inertial_velocity_x", "m/s"), ("inertial_velocity_y", "m/s"),
    ("inertial_velocity_z", "m/s"), ("nominal_acceleration_x", "m/s^2"),
    ("nominal_acceleration_y", "m/s^2"), ("nominal_acceleration_z", "m/s^2"),
]


def truth(x: object) -> bool:
    return str(x).strip().lower() in {"true", "1", "yes"}


def local_path(x: str) -> Path:
    return ROOT / Path(str(x).replace("/", "\\"))


def summarize(x: np.ndarray) -> dict:
    return {"mean": x.mean(axis=0).tolist(), "std_population": x.std(axis=0).tolist(),
            "min": x.min(axis=0).tolist(), "max": x.max(axis=0).tolist()}


def time_major(dataset: h5py.Dataset, nt: int) -> np.ndarray:
    a = np.asarray(dataset, dtype=np.float64)
    if a.ndim == 2 and a.shape[1] in (nt, nt + 1) and a.shape[0] <= 64:
        a = a.T
    if a.ndim != 2 or a.shape[0] not in (nt, nt + 1):
        raise ValueError(f"Expected time-major raw data with {nt} transitions: {dataset.name} {a.shape}")
    return a


def main() -> None:
    out_reports = OUT / "reports"
    out_manifests = OUT / "manifests"
    out_reports.mkdir(parents=True, exist_ok=True)
    out_manifests.mkdir(parents=True, exist_ok=True)

    episodes = pd.read_csv(ROOT / "logs/episode_index.csv", keep_default_na=False, dtype=str)
    accepted = episodes.loc[
        episodes.accepted.map(truth)
        & episodes.split.str.lower().isin(("train", "val"))
        & episodes.source_role.isin(ROLES)
    ].copy()
    attempts = pd.read_csv(ROOT / "logs/attempt_index.csv", keep_default_na=False, dtype=str)
    attempts = attempts.loc[
        attempts.run_id.isin(accepted.run_id)
        & attempts.status.eq("COMPLETE")
        & attempts.accepted_for_training.map(truth)
        & attempts.raw_path.astype(str).str.len().gt(0)
    ].copy()
    attempts["attempt_no_int"] = attempts.attempt_no.astype(int)
    raw_map = (attempts.sort_values("attempt_no_int").drop_duplicates("run_id", keep="last")
               .set_index("run_id").raw_path.astype(str).to_dict())
    expected = {("train", "B"): 768, ("train", "POS_OFF"): 768,
                ("val", "B"): 48, ("val", "POS_OFF"): 48}
    got = {(str(k[0]).lower(), str(k[1])): int(v)
           for k, v in accepted.groupby(["split", "source_role"]).size().to_dict().items()}
    if got != expected:
        raise RuntimeError(f"Teacher accepted-index counts differ: {got}")
    if accepted.run_id.nunique() != len(accepted):
        raise RuntimeError("Duplicate accepted teacher run IDs")
    if accepted.duplicated(["split", "scene_id", "source_role"]).any():
        raise RuntimeError("Duplicate accepted teacher scene/role rows")
    paired = accepted.pivot(index=["split", "scene_id", "task", "class_index", "wind_cell"],
                            columns="source_role", values="run_id")
    if paired.isna().any().any() or len(paired) != 816:
        raise RuntimeError("Teacher B/POS_OFF pairing is incomplete")
    if set(accepted.loc[accepted.split.str.lower().eq("train"), "scene_id"]) & set(
            accepted.loc[accepted.split.str.lower().eq("val"), "scene_id"]):
        raise RuntimeError("Teacher TRAIN and VAL share a physical scene")

    cache_manifest = pd.read_csv(
        ROOT / "experiments/position_causal_repair_v1/manifests/D4_SEQUENCE_CACHE.csv",
        keep_default_na=False, dtype=str)
    cache_teacher = cache_manifest.loc[cache_manifest.run_id.isin(accepted.run_id)].copy()
    if set(cache_teacher.run_id) != set(accepted.run_id) or cache_teacher.run_id.duplicated().any():
        raise RuntimeError("Existing D4 sequence cache does not cover each accepted teacher episode once")
    cache_by_run = cache_teacher.set_index("run_id").to_dict(orient="index")

    normalizer_file = ROOT / "models/position/initial/normalizer.npz"
    with np.load(normalizer_file, allow_pickle=False) as z:
        initial_mu = np.asarray(z["mu"], dtype=np.float64).reshape(-1)
        initial_sigma = np.asarray(z["sigma"], dtype=np.float64).reshape(-1)
    if initial_mu.size != 14 or initial_sigma.size != 14:
        raise RuntimeError("Initial X14 normalizer is not 14-dimensional")

    input_count = np.zeros(20, dtype=np.int64)
    input_sum = np.zeros(20, dtype=np.float64)
    input_sumsq = np.zeros(20, dtype=np.float64)
    input_min = np.full(20, np.inf)
    input_max = np.full(20, -np.inf)
    target_cells: dict[tuple[str, str, int], dict] = defaultdict(
        lambda: {"count": 0, "sum": np.zeros(3), "sumsq": np.zeros(3), "clip_count": 0})
    manifest_rows: list[dict] = []
    h5_max_clip_error = 0.0
    h5_max_dt_error = 0.0
    cache_max_x14 = cache_max_y = cache_max_raw = 0.0
    cache_max_x20prefix = 0.0
    file_missing: list[str] = []

    for row in accepted.itertuples(index=False):
        run_id = str(row.run_id)
        split = str(row.split).lower()
        event_path = local_path(str(row.position_event_path))
        cmeta = cache_by_run[run_id]
        cache_path = local_path(str(cmeta["cache_path"]))
        raw_rel = raw_map.get(run_id, "")
        raw_path = local_path(raw_rel) if raw_rel else None
        for p in (event_path, cache_path, raw_path):
            if p is None or not p.is_file():
                file_missing.append(f"{run_id}: {p}")
        if file_missing:
            continue

        with h5py.File(event_path, "r") as f:
            x14 = np.asarray(f["x14"], dtype=np.float64)
            raw = np.asarray(f["target_raw"], dtype=np.float64)
            clipped = np.asarray(f["target_clip"], dtype=np.float64)
            ready = np.asarray(f["ready"], dtype=np.uint8).reshape(-1).astype(bool)
            phase = np.asarray(f["phase_code"], dtype=np.uint8).reshape(-1)
            event_time = np.asarray(f["event_time_s"], dtype=np.float64).reshape(-1)
            plant_index = np.asarray(f["plant_index"], dtype=np.float64).reshape(-1)
            beta = np.asarray(f["beta"], dtype=np.float64).reshape(-1)
            label_closure = float(np.asarray(f["label_closure_max_abs_mps2"]).reshape(-1)[0])
        if x14.shape != (1999, 14) or raw.shape != (1999, 3) or clipped.shape != (1999, 3):
            raise RuntimeError(f"Unexpected H5 event-major dimensions for {run_id}: {x14.shape}/{raw.shape}/{clipped.shape}")
        if ready.shape != (1999,) or ready.sum() != 1968 or not np.array_equal(ready, np.arange(1999) >= 31):
            raise RuntimeError(f"Incorrect 32-event readiness for {run_id}")
        if not (np.isfinite(x14).all() and np.isfinite(raw).all() and np.isfinite(clipped).all()
                and np.isfinite(event_time).all() and np.isfinite(beta).all()):
            raise RuntimeError(f"Non-finite H5 values for {run_id}")
        if not (np.diff(event_time) > 0).all() or not (np.diff(plant_index) > 0).all():
            raise RuntimeError(f"Non-increasing event/Plant clock in {run_id}")
        dt_error = float(np.max(np.abs(np.diff(event_time) - 0.01)))
        clip_error = float(np.max(np.abs(clipped - np.clip(raw, -3.0, 3.0))))
        if dt_error > 1e-9 or clip_error > 1e-12 or label_closure > 1e-9:
            raise RuntimeError(f"Event timing, clipping, or label closure check failed for {run_id}")
        h5_max_dt_error = max(h5_max_dt_error, dt_error)
        h5_max_clip_error = max(h5_max_clip_error, clip_error)

        with np.load(cache_path, allow_pickle=False) as z:
            cx14 = np.asarray(z["x14"], dtype=np.float32)
            cx20 = np.asarray(z["x20"], dtype=np.float32)
            cy = np.asarray(z["y"], dtype=np.float32)
            craw = np.asarray(z["raw"], dtype=np.float32)
            cready = np.asarray(z["ready"], dtype=bool).reshape(-1)
            cphase = np.asarray(z["phase"], dtype=np.uint8).reshape(-1)
            ctime = np.asarray(z["event_time_s"], dtype=np.float32).reshape(-1)
            cplant = np.asarray(z["plant_index"], dtype=np.int32).reshape(-1)
            if str(z["run_id"]) != run_id or cx20.shape != (1999, 20):
                raise RuntimeError(f"Cache identity/X20 shape mismatch for {run_id}")
        if not np.isfinite(cx20).all():
            raise RuntimeError(f"Non-finite X20 cache for {run_id}")
        cache_max_x14 = max(cache_max_x14, float(np.max(np.abs(cx14 - x14.astype(np.float32)))))
        cache_max_y = max(cache_max_y, float(np.max(np.abs(cy - clipped.astype(np.float32)))))
        cache_max_raw = max(cache_max_raw, float(np.max(np.abs(craw - raw.astype(np.float32)))))
        cache_max_x20prefix = max(cache_max_x20prefix, float(np.max(np.abs(cx20[:, :14] - cx14))))
        if not np.array_equal(cready, ready) or not np.array_equal(cphase, phase):
            raise RuntimeError(f"Cache readiness/phase differs from H5 for {run_id}")
        if np.max(np.abs(ctime - event_time)) > 1e-6 or not np.array_equal(cplant, plant_index.astype(np.int32) - 1):
            raise RuntimeError(f"Cache time or zero-based Plant index differs from H5 for {run_id}")

        if split == "train":
            a = cx20.astype(np.float64)
            input_count += len(a)
            input_sum += a.sum(axis=0)
            input_sumsq += np.square(a).sum(axis=0)
            input_min = np.minimum(input_min, a.min(axis=0))
            input_max = np.maximum(input_max, a.max(axis=0))
        for pcode in np.unique(phase[ready]):
            mask = ready & (phase == pcode)
            key = (str(row.source_role), str(row.task), int(pcode))
            item = target_cells[key]
            vals = raw[mask]
            item["count"] += len(vals)
            item["sum"] += vals.sum(axis=0)
            item["sumsq"] += np.square(vals).sum(axis=0)
            item["clip_count"] += int(np.count_nonzero(np.any(np.abs(vals) > 3.0, axis=1)))

        manifest_rows.append({
            "run_id": run_id, "scene_id": str(row.scene_id), "split": split,
            "role": str(row.source_role), "task": str(row.task), "class_index": int(row.class_index),
            "wind_cell": int(row.wind_cell), "position_event_path": event_path.relative_to(ROOT).as_posix(),
            "position_event_bytes": event_path.stat().st_size,
            "raw_path": raw_path.relative_to(ROOT).as_posix(), "raw_bytes": raw_path.stat().st_size,
            "sequence_cache_path": cache_path.relative_to(ROOT).as_posix(),
            "sequence_cache_bytes": cache_path.stat().st_size,
            "event_count": 1999, "ready_count": int(ready.sum()),
        })

    if file_missing:
        raise FileNotFoundError("Missing accepted teacher source files: " + "; ".join(file_missing[:20]))

    means = input_sum / input_count
    stds = np.sqrt(np.maximum(input_sumsq / input_count - means ** 2, 0.0))
    initial_norm_delta = {"mu_first10_max_abs": float(np.max(np.abs(initial_mu[:10] - means[:10]))),
                          "sigma_first10_max_abs": float(np.max(np.abs(initial_sigma[:10] - stds[:10])))}
    reuse_initial_norm = max(initial_norm_delta.values()) <= 1e-5
    x14_mu = initial_mu.copy() if reuse_initial_norm else np.r_[means[:10], np.zeros(4)]
    x14_sigma = initial_sigma.copy() if reuse_initial_norm else np.r_[np.maximum(stds[:10], 1e-4), np.ones(4)]
    x20_mu = np.r_[x14_mu, means[14:20]]
    x20_sigma = np.r_[x14_sigma, np.maximum(stds[14:20], 1e-4)]
    outside = np.zeros(20, dtype=np.int64)
    totals = 0
    for r in accepted.loc[accepted.split.str.lower().eq("train")].itertuples(index=False):
        cpath = local_path(cache_by_run[str(r.run_id)]["cache_path"])
        with np.load(cpath, allow_pickle=False) as z:
            x14 = np.asarray(z["x14"], dtype=np.float32)
            x20 = np.asarray(z["x20"], dtype=np.float32)
        z14 = (x14.astype(np.float64) - x14_mu) / x14_sigma
        z20 = (x20[:, 14:].astype(np.float64) - x20_mu[14:]) / x20_sigma[14:]
        outside[:14] += np.count_nonzero(np.abs(z14) > 4.0, axis=0)
        outside[14:] += np.count_nonzero(np.abs(z20) > 4.0, axis=0)
        totals += len(x14)
    target_report = []
    for (role, task, pcode), v in sorted(target_cells.items()):
        n = v["count"]
        mean = v["sum"] / n
        rms = np.sqrt(v["sumsq"] / n)
        target_report.append({"role": role, "task": task, "phase_code": pcode, "phase": PHASES[pcode],
                              "ready_event_count": n, "target_raw_bias_mps2": mean.tolist(),
                              "target_raw_rms_mps2": rms.tolist(),
                              "events_over_clip_limit_fraction": v["clip_count"] / n})

    # Deterministic, label-blind cycle matching: each task contains every one of
    # the 16 wind cells twice, and each class receives two distinct wind cells.
    specs = pd.read_csv(ROOT / "configs/scene_specs.csv", keep_default_na=False)
    train_specs = specs.loc[specs.split.astype(str).str.upper().eq("TRAIN")].copy()
    rng = np.random.default_rng(2026102000)
    pool_records: list[dict] = []
    index_by_scene_role = accepted.loc[accepted.split.str.lower().eq("train")].set_index(
        ["scene_id", "source_role"])
    wind_cells = list(range(16))
    for task in TASKS:
        perm = rng.permutation(wind_cells).tolist()
        for class_id in range(16):
            chosen_winds = (int(perm[class_id]), int(perm[(class_id + 1) % 16]))
            if chosen_winds[0] == chosen_winds[1]:
                raise AssertionError("Wind cycle produced a duplicate within a class")
            for wind in chosen_winds:
                s = train_specs.loc[(train_specs.task == task) & (train_specs.c.astype(int) == class_id)
                                    & (train_specs.w.astype(int) == wind)]
                if len(s) != 1:
                    raise RuntimeError(f"scene_specs does not identify one {task}/class={class_id}/wind={wind}")
                sr = s.iloc[0]
                scene_id = str(sr.scene_id)
                for role in ROLES:
                    ix = index_by_scene_role.loc[(scene_id, role)]
                    cache = cache_by_run[str(ix.run_id)]
                    pool_records.append({
                        "run_id": str(ix.run_id), "scene_id": scene_id, "split": "train", "role": role,
                        "task": task, "class_index": class_id, "wind_cell": wind,
                        "wind_band": int(sr.wind_band), "amplitude_level": int(sr.amplitude_level),
                        "azimuth_index": int(sr.azimuth_index), "azimuth_deg": float(sr.azimuth_deg),
                        "elevation_deg": float(sr.elevation_deg), "f1_hz": float(sr.f1_hz),
                        "f2_hz": float(sr.f2_hz), "position_event_path": str(ix.position_event_path),
                        "sequence_cache_path": str(cache["cache_path"]), "endpoint_count_L32": 394,
                        "selection_seed": 2026102000,
                        "selection_rule": "all wind_cell values twice per task; two distinct cells per class; label blind",
                    })
    pool = pd.DataFrame(pool_records)
    if len(pool) != 192 or pool.run_id.nunique() != 192 or pool.scene_id.nunique() != 96:
        raise RuntimeError("Small teacher pool is not 192 paired teacher runs / 96 physical scenes")
    scene_pool = pool.drop_duplicates("scene_id")
    wind_counts = scene_pool.groupby(["task", "wind_cell"]).size()
    if not (wind_counts == 2).all():
        raise RuntimeError(f"Small pool wind coverage is not exactly twice/task/cell: {wind_counts.to_dict()}")
    class_counts = scene_pool.groupby(["task", "class_index"]).wind_cell.nunique()
    if not (class_counts == 2).all():
        raise RuntimeError("Small pool class does not contain two distinct wind cells")
    pool_path = out_manifests / "small_teacher_pool.csv"
    pool.to_csv(pool_path, index=False, float_format="%.12g")

    x20_raw_checks = []
    for task in TASKS:
        for role in ROLES:
            r = (accepted.loc[accepted.split.str.lower().eq("train") & accepted.task.eq(task)
                              & accepted.source_role.eq(role)].sort_values("scene_id").iloc[0])
            ep_path = local_path(str(r.position_event_path))
            raw_path = local_path(raw_map[str(r.run_id)])
            cache_path = local_path(cache_by_run[str(r.run_id)]["cache_path"])
            with h5py.File(ep_path, "r") as f:
                x14 = np.asarray(f["x14"], dtype=np.float64)
                plant_idx = np.asarray(f["plant_index"], dtype=np.int64).reshape(-1) - 1
            with h5py.File(raw_path, "r") as f:
                state = time_major(f["log/state"], 20000)
                nominal = time_major(f["log/position_nominal_acceleration_mps2"], 20000)
            rebuilt = np.column_stack((x14, state[plant_idx, 3:6], nominal[plant_idx, :3])).astype(np.float32)
            with np.load(cache_path, allow_pickle=False) as z:
                cached = np.asarray(z["x20"], dtype=np.float32)
            delta = float(np.max(np.abs(rebuilt - cached)))
            if delta > 1e-6:
                raise RuntimeError(f"Raw MAT to cached X20 parity failed for {r.run_id}: {delta}")
            x20_raw_checks.append({"run_id": str(r.run_id), "scene_id": str(r.scene_id),
                                   "task": task, "role": role, "max_abs_difference": delta,
                                   "source_fields": ["log/state[plant_index,3:6]", "log/position_nominal_acceleration_mps2[plant_index,0:3]"],
                                   "uses_current_actual_acceleration_or_true_morphology": False})

    pd.DataFrame(manifest_rows).to_csv(out_manifests / "teacher_reuse_manifest.csv", index=False)
    pd.DataFrame(target_report).to_csv(out_reports / "TARGET_DISTRIBUTION_ROLE_TASK_PHASE.csv", index=False,
                                       float_format="%.12g")

    feature_table = []
    for i, (name, unit) in enumerate(FEATURES + EXTRA_FEATURES):
        feature_table.append({"index_zero_based": i, "name": name, "unit": unit,
                              "train_mean": float(means[i]), "train_std_population": float(stds[i]),
                              "train_min": float(input_min[i]), "train_max": float(input_max[i]),
                              "standardizer_mean": float(x20_mu[i]), "standardizer_std": float(x20_sigma[i]),
                              "kan_spline_abs_z_gt_4_fraction": float(outside[i] / totals)})
    audit = {
        "task": "DL1018_TEACHER_REUSE_MODEL_SCREEN_V1", "status": "PASS_DATA_PREFLIGHT",
        "index_counts": {"accepted_teacher_rows": len(accepted), "accepted_teacher_train_rows": 1536,
                         "accepted_teacher_val_rows": 96, "train_B": 768, "train_POS_OFF": 768,
                         "val_B": 48, "val_POS_OFF": 48, "paired_physical_train_scenes": 768,
                         "paired_physical_val_scenes": 48, "train_val_scene_overlap": 0,
                         "student_records_excluded": int(len(episodes) - len(accepted))},
        "source_integrity": {"all_accepted_event_h5_and_raw_mat_present": True,
                             "all_accepted_teacher_ids_in_existing_d4_cache": True,
                             "all_event_shapes": [1999, 14], "all_target_shapes": [1999, 3],
                             "all_event_major": True, "ready_events_per_episode": 1968,
                             "event_dt_s_target": 0.01, "max_event_dt_error_s": h5_max_dt_error,
                             "max_target_clip_identity_error_mps2": h5_max_clip_error,
                             "max_h5_vs_cache_x14_abs": cache_max_x14,
                             "max_h5_vs_cache_target_clip_abs": cache_max_y,
                             "max_h5_vs_cache_target_raw_abs": cache_max_raw,
                             "max_x20_prefix_vs_x14_abs": cache_max_x20prefix,
                             "x20_available_all_teacher": True},
        "normalizer": {"initial_teacher_normalizer_path": "models/position/initial/normalizer.npz",
                       "initial_normalizer_matches_full_accepted_teacher_train_first10": reuse_initial_norm,
                       "initial_vs_recomputed_train_max_abs": initial_norm_delta,
                       "selected_x14_mu": x14_mu.tolist(), "selected_x14_sigma": x14_sigma.tolist(),
                       "x20_mu": x20_mu.tolist(), "x20_sigma": x20_sigma.tolist(),
                       "new_x20_stats_source": "accepted B/POS_OFF TRAIN only"},
        "feature_distribution": feature_table,
        "target_distribution": target_report,
        "input_contract": {"x14": [f"{n} [{u}]" for n, u in FEATURES],
                           "x20_extra": [f"{n} [{u}]" for n, u in EXTRA_FEATURES],
                           "causal_source": "current X14 plus current raw command; X20 adds raw inertial velocity and zero-compensation nominal acceleration; no actual acceleration, residual, true wind, true morphology, or scene ID input"},
        "x20_raw_source_parity": {"status": "PASS", "six_samples_one_per_task_role": x20_raw_checks},
        "windows": {"L32_train_full": 1536 * 394, "L32_val_teacher": 96 * 394,
                    "L32_small_teacher": 192 * 394, "L128_train_full": 1536 * 375,
                    "L128_val_teacher": 96 * 375,
                    "L128_endpoint_rule": "zero-based 127,132,...,1997"},
        "small_pool": {"rows": len(pool), "physical_scenes": int(pool.scene_id.nunique()),
                       "selection_seed": 2026102000, "wind_cells_per_task": "each of 16 appears twice",
                       "wind_cells_per_class": "two distinct cells", "label_blind": True},
        "no_plant_or_training_performed": True,
    }
    (out_reports / "data_interface_audit.json").write_text(
        json.dumps(audit, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": audit["status"], "index_counts": audit["index_counts"],
                      "source_integrity": audit["source_integrity"], "normalizer": audit["normalizer"],
                      "small_pool": audit["small_pool"]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
