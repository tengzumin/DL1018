#!/usr/bin/env python3
"""Read-only, pinned subgroup summary for the frozen C5 review batch and TEST48 results."""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import math
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

import h5py
import numpy as np


ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
TOL_M = 1e-12
BASELINE_M = 0.15
INPUTS = {
    "scene_specs": ("configs/scene_specs.csv", "d116b74dc6d9ce3c21a40fcd48b4153a0adc09e98a6c8d341c0f1b6ba680b4e3"),
    "dev_input_lock": ("experiments/position_axis_coordinate_c5_dev72_20261023/C5_DEV72_INPUT_LOCK_v3.json",
                       "82024c01276cc4bfbd9b7772cf5332dee3fdfcbed422969589b68f1c90ed2d75"),
    "dev_parent_review": ("reports/paper_continuation_20261023/c5_dev72_parent_review/C5_DEV72_RAW_PARENT_REVIEW_v3.json",
                          "bb34889559d95a1c995d4d420e3b3d7a702908b58b47cce969dc508a1c697fab"),
    "test_long_metrics": ("reports/paper_continuation_20261023/test_results_final_v1/paired_complete_48x6_long.csv",
                          "178f29fb3732a5eda5cb4f0d4a9ba17f72b2f470ad7418f7a829fe525be64db2"),
    "test_wide_crosscheck": ("reports/paper_continuation_20261023/test_results_final_v1/paired_Q_48x6_wide_mm.csv",
                             "8da2901ede8034388b6e512ef04fa53bd9dc7fdae0a1e41657047c8930641ce3"),
    "test_input_index": ("experiments/c5_test48_v3/input/TEST_INPUT_INDEX_v1.json",
                         "90940a818d293c66c34423a63088113557518c5ecdfd528a3f37867f391eef68"),
    "test48_producer": ("experiments/c5_test48_v3/test48_entry_v1.m",
                        "0490da98749b114ed9e9553fc7cb44349e0c5c9d182551d8a05c844a009b9bf2"),
    "test_shared_scenes": ("experiments/c5_test48_v3/input/TEST_SCENES_SHARED_v1.mat",
                           "da207d858e8918f27c19fef30d4ad57206e20f1971e743515043d1a88a995d5c"),
    "pinned_hdf5_reader": ("reports/paper_continuation_20261023/c5_dev72_parent_review/audit_c5_dev72_raw_parent_v4.py",
                           "d82e089c7d41f39c620daea63d95315632e6fb2f80addf4dc12e6a4603b8e57e"),
}
SCENE_RE = re.compile(r"^DL1018_(?:DEV|VAL|TEST)_T([123])_C(\d{2})_W(\d{2})$")
TASK_NAME = {"T1": "HELIX", "T2": "FIG8_3D", "T3": "SQUARE"}
DEV_BATCH_DATASET = "DEV72_PARENT_REVIEW_BATCH"
ARM_GROUPS = (0, 1, 2, 3, 4)
TASK_GROUPS = ("ALL", "T1", "T2", "T3")


def need(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def pinned_input(name: str) -> tuple[Path, str]:
    rel, expected = INPUTS[name]
    path = ROOT / rel
    actual = sha256(path)
    need(actual == expected, f"Pinned input changed: {rel} ({actual})")
    return path, actual


def scene_parts(scene_id: str) -> tuple[str, int, int]:
    match = SCENE_RE.fullmatch(scene_id)
    need(match is not None, f"Unexpected scene ID: {scene_id}")
    task, class_code, wind = match.groups()
    return f"T{task}", int(class_code), int(wind)


def finite_float(value: object, label: str) -> float:
    number = float(value)
    need(math.isfinite(number), f"Nonfinite {label}")
    return number


def active_count_from_spec(row: dict[str, str]) -> int:
    targets = [finite_float(row[f"target_a{i}_m"], f"{row['scene_id']} target_a{i}") for i in range(1, 5)]
    return sum(abs(target - BASELINE_M) > TOL_M for target in targets)


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def format_float(value: float | None) -> str:
    return "" if value is None else format(value, ".17g")


def load_shared_packs(mat_path: Path, reader_path: Path) -> list[dict]:
    spec = importlib.util.spec_from_file_location("pinned_c5_hdf5_reader", reader_path)
    need(spec is not None and spec.loader is not None, "Could not load pinned HDF5 reader")
    reader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    need(h5py.is_hdf5(mat_path), "Pinned TEST shared MAT is not MATLAB v7.3/HDF5")
    with h5py.File(mat_path, "r") as mat:
        need("scenePacks" in mat, "TEST shared MAT lacks scenePacks")
        packs = reader.matlab_flat(reader.h5_tree_cell_safe(mat["scenePacks"]))
    need(len(packs) == 48 and all(isinstance(pack, dict) for pack in packs),
         f"Expected 48 decoded scenePacks, observed {len(packs)}")
    return packs


def numeric_array(value: object, shape: tuple[int, ...], label: str) -> np.ndarray:
    array = np.asarray(value, dtype=np.float64)
    need(array.shape == shape, f"{label} shape {array.shape}, expected {shape}")
    need(bool(np.isfinite(array).all()), f"Nonfinite values in {label}")
    return array


def scalar_number(value: object, label: str) -> float:
    flattened = np.asarray(value, dtype=np.float64).reshape(-1)
    need(flattened.size == 1 and np.isfinite(flattened[0]), f"Expected finite scalar {label}")
    return float(flattened[0])


def collect_test_scene_features(index: dict, specs: dict[str, dict[str, str]], mat_path: Path,
                                reader_path: Path) -> tuple[list[dict], dict]:
    scene_ids = index.get("scene_ids")
    need(index.get("schema") == "TEST48_INPUT_INDEX_V1" and index.get("status") == "FROZEN_SHARED_TEST_INPUTS",
         "Unexpected TEST input index identity")
    need(isinstance(scene_ids, list) and len(scene_ids) == 48 and scene_ids == sorted(scene_ids),
         "TEST input index must contain 48 sorted scene IDs")
    packs = load_shared_packs(mat_path, reader_path)
    rows, task_peaks = [], defaultdict(list)
    all_hat, all_hat_rate, all_amplitudes, all_arm_rates = [], [], [], []
    for scene_id, pack in zip(scene_ids, packs):
        task, class_code, wind = scene_parts(scene_id)
        need(scene_id in specs and specs[scene_id]["split"] == "TEST", f"No TEST config row for {scene_id}")
        spec_row = specs[scene_id]
        need(int(spec_row["t"]) == int(task[1]) - 1 and int(spec_row["c"]) == class_code
             and int(spec_row["w"]) == wind, f"TEST config identity mismatch for {scene_id}")
        # The frozen MATLAB producer saves `spec` as a one-row table. The
        # pinned generic HDF5 reader exposes groups as dictionaries but does
        # not decode MATLAB table variables. The pinned producer sorts sceneIds
        # and writes packs in that same loop order; both index IDs and MAT SHA
        # are pinned inputs.
        scene = pack.get("scene", {})
        arms = scene.get("arms", {})
        expected_count = active_count_from_spec(spec_row)
        targets = np.array([float(spec_row[f"target_a{i}_m"]) for i in range(1, 5)])
        command = numeric_array(arms.get("command"), (20001, 4), f"{scene_id}.arms.command")
        rho = numeric_array(arms.get("rho_true"), (20001, 4), f"{scene_id}.arms.rho_true")
        rho_rate = numeric_array(arms.get("rhoDot_true"), (20001, 4), f"{scene_id}.arms.rhoDot_true")
        rho_hat = numeric_array(arms.get("rho_hat"), (20001, 4), f"{scene_id}.arms.rho_hat")
        rho_hat_rate = numeric_array(arms.get("rhoDot_hat"), (20001, 4), f"{scene_id}.arms.rhoDot_hat")
        moved = np.ptp(rho, axis=0) > 1e-9
        expected_moved = np.abs(targets - BASELINE_M) > TOL_M
        need(np.array_equal(moved, expected_moved), f"Actual rho_true active arms disagree with config: {scene_id}")
        need(int(moved.sum()) == expected_count, f"Active-arm count mismatch: {scene_id}")
        for arm_i in np.flatnonzero(moved):
            need(abs(float(np.max(rho[:, arm_i])) - targets[arm_i]) <= 1e-8,
                 f"rho_true target differs from config for {scene_id}, arm {arm_i + 1}")
            all_amplitudes.append(float(np.max(rho[:, arm_i]) - np.min(rho[:, arm_i])))
            all_arm_rates.append(float(np.max(np.abs(rho_rate[:, arm_i]))))
        need(bool(np.all(np.ptp(rho_hat, axis=0) == 0.0)), f"rho_hat changes over time in {scene_id}")
        need(bool(np.all(np.ptp(rho_hat_rate, axis=0) == 0.0)), f"rhoDot_hat changes over time in {scene_id}")
        all_hat.extend(rho_hat.reshape(-1).tolist())
        all_hat_rate.extend(rho_hat_rate.reshape(-1).tolist())
        reference = scene.get("reference", {})
        time_s = numeric_array(scene.get("time"), (20001, 1), f"{scene_id}.time")[:, 0]
        need(bool(np.all(np.diff(time_s) > 0.0)), f"Nonmonotone time vector in {scene_id}")
        velocity = numeric_array(reference.get("velocity"), (20001, 3), f"{scene_id}.reference.velocity")
        acceleration = numeric_array(reference.get("acceleration"), (20001, 3), f"{scene_id}.reference.acceleration")
        velocity_norm = np.linalg.norm(velocity, axis=1)
        acceleration_norm = np.linalg.norm(acceleration, axis=1)
        need(bool(np.isfinite(velocity_norm).all() and np.isfinite(acceleration_norm).all()),
             f"Nonfinite reference peak in {scene_id}")
        vpeak_i, apeak_i = int(np.argmax(velocity_norm)), int(np.argmax(acceleration_norm))
        task_peaks[task].append({
            "scene_id": scene_id,
            "velocity_peak_norm_mps": float(velocity_norm[vpeak_i]),
            "velocity_peak_time_s": float(time_s[vpeak_i]),
            "acceleration_peak_norm_mps2": float(acceleration_norm[apeak_i]),
            "acceleration_peak_time_s": float(time_s[apeak_i]),
        })
        active_ids = [f"a{i + 1}" for i in np.flatnonzero(moved)]
        rows.append({
            "scene_id": scene_id, "task": task, "wind": f"W{wind:02d}", "class_code": f"C{class_code:02d}",
            "active_arm_count": int(moved.sum()), "active_arm_count_source": "TEST scenePacks.scene.arms.rho_true",
            "config_target_active_arm_count": expected_count, "active_arm_count_config_match": True,
            "active_arms": ";".join(active_ids),
            "max_active_extension_m": max((float(np.max(rho[:, i]) - np.min(rho[:, i])) for i in np.flatnonzero(moved)), default=0.0),
            "max_abs_active_rhoDot_true_mps": max((float(np.max(np.abs(rho_rate[:, i]))) for i in np.flatnonzero(moved)), default=0.0),
            "rho_hat_min_m": float(np.min(rho_hat)), "rho_hat_max_m": float(np.max(rho_hat)),
            "rhoDot_hat_min_mps": float(np.min(rho_hat_rate)), "rhoDot_hat_max_mps": float(np.max(rho_hat_rate)),
            "command_nonzero_sample_count": int(np.count_nonzero(command)),
            "velocity_peak_norm_mps": float(velocity_norm[vpeak_i]),
            "velocity_peak_time_s": float(time_s[vpeak_i]),
            "acceleration_peak_norm_mps2": float(acceleration_norm[apeak_i]),
            "acceleration_peak_time_s": float(time_s[apeak_i]),
        })
    need(len(rows) == 48, "TEST morphology feature count is not 48")
    hat_values, hat_rate_values = np.unique(np.asarray(all_hat)), np.unique(np.asarray(all_hat_rate))
    need(hat_values.size == 1 and hat_rate_values.size == 1,
         "rho_hat/rhoDot_hat are not globally constant across TEST")
    peak_summary = {}
    for task, values in task_peaks.items():
        peak_summary[task] = {
            "scene_count": len(values),
            "max_velocity_peak_norm_mps": max(row["velocity_peak_norm_mps"] for row in values),
            "max_acceleration_peak_norm_mps2": max(row["acceleration_peak_norm_mps2"] for row in values),
            "per_scene": values,
        }
    morphology = {
        "scene_count": len(rows), "arm_array_shape": [20001, 4], "reference_array_shape": [20001, 3],
        "active_arm_instance_count": len(all_amplitudes),
        "active_extension_amplitude_range_m": [min(all_amplitudes), max(all_amplitudes)],
        "max_abs_rhoDot_true_active_range_mps": [min(all_arm_rates), max(all_arm_rates)],
        "rho_hat_unique_count_global": int(hat_values.size), "rho_hat_min_m": float(hat_values[0]),
        "rho_hat_max_m": float(hat_values[-1]), "rhoDot_hat_unique_count_global": int(hat_rate_values.size),
        "rhoDot_hat_value_mps": float(hat_rate_values[0]), "reference_peak_norms_by_task": peak_summary,
        "subgroup_counts_by_task": {
            task: {str(count): sum(row["task"] == task and row["active_arm_count"] == count for row in rows)
                   for count in ARM_GROUPS}
            for task in ("T1", "T2", "T3")
        },
    }
    return rows, morphology


def validate_dev_batch_contract(lock: dict, dev_review: dict) -> dict:
    need(lock.get("schema") == "C5_AXIS_COORDINATE_DEV72_INPUT_LOCK_V3"
         and lock.get("state") == "LOCKED_C5_M110_DEV72_NO_PLANT_WAIT_PARENT_RELEASE_V3",
         "Unexpected C5 DEV72 input lock identity")
    all_ids = lock.get("scene_ids_all_72")
    new_ids = lock.get("scene_ids_new_60")
    reuse_ids = lock.get("scene_ids_reuse_12")
    need(isinstance(all_ids, list) and len(all_ids) == 72
         and all(isinstance(scene_id, str) for scene_id in all_ids) and len(set(all_ids)) == 72,
         "DEV parent-review lock must contain 72 unique ordered scene IDs")
    need(isinstance(new_ids, list) and len(new_ids) == 60
         and all(isinstance(scene_id, str) for scene_id in new_ids) and len(set(new_ids)) == 60,
         "DEV parent-review lock must contain 60 unique new C5 scene IDs")
    need(isinstance(reuse_ids, list) and len(reuse_ids) == 12
         and all(isinstance(scene_id, str) for scene_id in reuse_ids) and len(set(reuse_ids)) == 12,
         "DEV parent-review lock must contain 12 unique reused scene IDs")
    counts = lock.get("counts", {})
    need(counts.get("total") == 72 and counts.get("new_c5_plants") == 60 and counts.get("c5_reuse") == 12,
         "Unexpected C5 DEV72 input-lock counts")
    all_set, new_set, reuse_set = set(all_ids), set(new_ids), set(reuse_ids)
    need(not new_set.intersection(reuse_set) and new_set.union(reuse_set) == all_set,
         "DEV new/reuse scene lists must be disjoint and partition all_72")
    need(new_ids == [scene_id for scene_id in all_ids if scene_id in new_set]
         and reuse_ids == [scene_id for scene_id in all_ids if scene_id in reuse_set],
         "DEV new/reuse scene lists must preserve all_72 order")
    need(all(isinstance(scene_id, str) and SCENE_RE.fullmatch(scene_id) is not None
             and not scene_id.startswith("DL1018_TEST_") for scene_id in all_ids),
         "DEV parent-review lock contains an invalid or TEST scene ID")

    lock_rows = lock.get("scenes")
    need(isinstance(lock_rows, list) and len(lock_rows) == 72 and all(isinstance(row, dict) for row in lock_rows)
         and [row.get("scene_id") for row in lock_rows] == all_ids,
         "DEV input-lock scene rows must match all_72 in order")
    split_by_id = {}
    candidate_action_by_id = {}
    for row in lock_rows:
        scene_id, source_split = row["scene_id"], row.get("source_split")
        expected_action = ("PROPOSE_NEW_C5_M110_RUN" if scene_id in new_set
                           else "REUSE_AUDITED_C5_SCREEN")
        candidate_action = row.get("candidate_action")
        need(candidate_action == expected_action,
             f"DEV lock candidate_action does not match new/reuse list for {scene_id}: {candidate_action}")
        need(source_split in ("DEV", "VAL") and source_split == scene_id.split("_")[1],
             f"Unexpected original split for {scene_id}: {source_split}")
        split_by_id[scene_id] = source_split
        candidate_action_by_id[scene_id] = candidate_action

    original_counts = Counter(split_by_id.values())
    new_split_counts = Counter(split_by_id[scene_id] for scene_id in new_ids)
    reuse_split_counts = Counter(split_by_id[scene_id] for scene_id in reuse_ids)
    need(dict(original_counts) == {"DEV": 24, "VAL": 48}
         and dict(new_split_counts) == {"DEV": 24, "VAL": 36}
         and dict(reuse_split_counts) == {"VAL": 12},
         "Unexpected original DEV/VAL split across new and reused C5 rows")

    need(dev_review.get("status") == "PASS_C5_DEV72_RAW_ALL_EVENTS_PARENT_AUDIT"
         and dev_review.get("scope") == "DEV_ONLY_NO_TEST" and dev_review.get("scene_count") == 72,
         "Unexpected DEV72 parent review identity")
    review_rows = dev_review.get("rows")
    need(isinstance(review_rows, list) and len(review_rows) == 72 and all(isinstance(row, dict) for row in review_rows)
         and [row.get("scene_id") for row in review_rows] == all_ids,
         "DEV parent-review rows must match all_72 in exact order")
    by_scene = {}
    expected_status_counts = {"PASS_C5_RAW_ALL_EVENTS": 60, "PASS_REUSED_C5_SCREEN_AUDIT": 12}
    for row in review_rows:
        scene_id = row["scene_id"]
        expected_status = "PASS_C5_RAW_ALL_EVENTS" if scene_id in new_set else "PASS_REUSED_C5_SCREEN_AUDIT"
        need(row.get("status") == expected_status,
             f"DEV review status does not match new/reuse list for {scene_id}: {row.get('status')}")
        by_scene[scene_id] = {"source_review_status": row["status"],
                              "original_scene_split": split_by_id[scene_id],
                              "candidate_action": candidate_action_by_id[scene_id]}
    need(dict(Counter(row["status"] for row in review_rows)) == expected_status_counts,
         "DEV parent-review status counts do not match the new/reuse contract")
    return {
        "by_scene": by_scene,
        "provenance": {
            "review_row_count": len(review_rows),
            "original_split_counts": {split: original_counts[split] for split in ("DEV", "VAL")},
            "review_status_counts": expected_status_counts,
            "new_run_count": len(new_ids),
            "new_run_original_split_counts": {split: new_split_counts[split] for split in ("DEV", "VAL")},
            "reused_count": len(reuse_ids),
            "reused_original_split_counts": {split: reuse_split_counts[split] for split in ("DEV", "VAL")},
            "candidate_action_counts": {
                "PROPOSE_NEW_C5_M110_RUN": len(new_ids),
                "REUSE_AUDITED_C5_SCREEN": len(reuse_ids),
            },
            "candidate_action_by_scene": candidate_action_by_id,
            "not_72_independent_dev_scenes": True,
        },
    }


def performance_rows(dev_review: dict, dev_scene_contract: dict[str, dict],
                     long_rows: list[dict[str, str]], wide_rows: list[dict[str, str]],
                     specs: dict[str, dict[str, str]], index: dict) -> tuple[list[dict], dict]:
    need(dev_review.get("status") == "PASS_C5_DEV72_RAW_ALL_EVENTS_PARENT_AUDIT"
         and dev_review.get("scope") == "DEV_ONLY_NO_TEST" and dev_review.get("scene_count") == 72,
         "Unexpected DEV72 parent review identity")
    dev_rows = []
    for row in dev_review.get("rows", []):
        scene_id = row["scene_id"]
        need(scene_id in specs, f"No scene_specs row for DEV scene {scene_id}")
        provenance = dev_scene_contract[scene_id]
        need(row.get("status") == provenance["source_review_status"],
             f"DEV review status changed after contract validation: {scene_id}")
        need(specs[scene_id]["split"] == provenance["original_scene_split"],
             f"scene_specs original split mismatch for {scene_id}")
        active_count = active_count_from_spec(specs[scene_id])
        dev_rows.append({
            "dataset": DEV_BATCH_DATASET, "scene_id": scene_id, "task": scene_parts(scene_id)[0],
            **provenance,
            "active_arm_count": active_count,
            "active_arm_count_source": "scene_specs.csv target_a1_m..target_a4_m",
            "config_target_active_arm_count": active_count,
            "active_arm_count_config_match": None,
            "Q_B_m": finite_float(row["B_metrics"]["Q_0_20_m"], f"{scene_id} B Q"),
            "Q_C5_m": finite_float(row["C5_metrics"]["Q_0_20_m"], f"{scene_id} C5 Q"),
        })
    need(len(dev_rows) == 72 and len({row["scene_id"] for row in dev_rows}) == 72,
         "DEV72 parent review must have 72 unique paired scene rows")

    index_ids = index["scene_ids"]
    need(len(long_rows) == 288, f"Expected reviewed six-method TEST long table with 288 rows, found {len(long_rows)}")
    wide_by_id = {row["scene_id"]: row for row in wide_rows}
    need(len(wide_by_id) == 48 and set(wide_by_id) == set(index_ids), "TEST wide CSV does not match input index")
    grouped = defaultdict(dict)
    for row in long_rows:
        if row["method"] in ("B_TRACEABLE", "C5_M110"):
            scene_id = row["scene_id"]
            need(scene_id in index_ids, f"Unexpected TEST metric scene {scene_id}")
            slot = grouped[scene_id]
            need(row["method"] not in slot, f"Duplicate TEST method row {scene_id}/{row['method']}")
            slot[row["method"]] = finite_float(row["Q_0_20_m"], f"{scene_id} {row['method']} Q")
    need(len(grouped) == 48 and all(set(v) == {"B_TRACEABLE", "C5_M110"} for v in grouped.values()),
         "TEST long CSV must supply paired B/C5 meter-valued Q for all 48 scenes")
    max_crosscheck_m = 0.0
    test_rows = []
    for scene_id in index_ids:
        need(scene_id in specs and specs[scene_id]["split"] == "TEST", f"No TEST config row for {scene_id}")
        values = grouped[scene_id]
        wide = wide_by_id[scene_id]
        need(wide["task"] == scene_parts(scene_id)[0], f"TEST wide task mismatch: {scene_id}")
        for method, column in (("B_TRACEABLE", "Q_0_20_mm__B_TRACEABLE"), ("C5_M110", "Q_0_20_mm__C5_M110")):
            difference = abs(values[method] - finite_float(wide[column], f"{scene_id} wide {method} Q") * 1e-3)
            max_crosscheck_m = max(max_crosscheck_m, difference)
            need(difference <= 1e-12, f"TEST wide/long Q mismatch {scene_id}/{method}: {difference} m")
        test_rows.append({
            "dataset": "TEST48", "scene_id": scene_id, "task": scene_parts(scene_id)[0],
            "active_arm_count": active_count_from_spec(specs[scene_id]),
            "Q_B_m": values["B_TRACEABLE"], "Q_C5_m": values["C5_M110"],
        })
    return dev_rows + test_rows, {"test_long_paired_scene_count": len(grouped),
                                  "wide_long_max_abs_difference_m": max_crosscheck_m}


def summarize(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    result, losses = [], []
    for dataset in (DEV_BATCH_DATASET, "TEST48"):
        dataset_rows = [row for row in rows if row["dataset"] == dataset]
        for arm_count in ARM_GROUPS:
            for task in TASK_GROUPS:
                selected = [row for row in dataset_rows if row["active_arm_count"] == arm_count
                            and (task == "ALL" or row["task"] == task)]
                delta = [row["Q_C5_m"] - row["Q_B_m"] for row in selected]
                group_losses = []
                wins = ties = group_loss_count = 0
                for row, difference in zip(selected, delta):
                    if difference < -TOL_M:
                        wins += 1
                    elif difference > TOL_M:
                        ties += 0
                        group_loss_count += 1
                        group_losses.append(row["scene_id"])
                        losses.append({**row, "delta_Q_C5_minus_B_m": difference,
                                       "analysis_active_arm_group": "NONE" if arm_count == 0 else str(arm_count),
                                       "analysis_task_group": task})
                    else:
                        ties += 1
                result.append({
                    "dataset": dataset, "active_arm_count": arm_count,
                    "active_arm_group": "NONE" if arm_count == 0 else str(arm_count), "task": task,
                    "n": len(selected), "mean_Q_B_m": (sum(r["Q_B_m"] for r in selected) / len(selected)) if selected else None,
                    "mean_Q_C5_m": (sum(r["Q_C5_m"] for r in selected) / len(selected)) if selected else None,
                    "mean_delta_Q_C5_minus_B_m": (sum(delta) / len(delta)) if delta else None,
                    "wins": wins, "losses": group_loss_count, "ties_within_1e-12m": ties,
                    "loss_scene_ids": ";".join(group_losses),
                })
    return result, losses


def write_csv_atomic(path: Path, rows: list[dict]) -> None:
    need(not path.exists(), f"Refusing to overwrite existing output: {path}")
    columns = list(rows[0]) if rows else []
    temp = path.with_suffix(path.suffix + ".tmp")
    need(not temp.exists(), f"Refusing to overwrite temporary output: {temp}")
    with temp.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: format_float(value) if isinstance(value, float) else value for key, value in row.items()})
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def write_text_atomic(path: Path, content: str) -> None:
    need(not path.exists(), f"Refusing to overwrite existing output: {path}")
    temp = path.with_suffix(path.suffix + ".tmp")
    need(not temp.exists(), f"Refusing to overwrite temporary output: {temp}")
    with temp.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def main() -> None:
    verified = {name: pinned_input(name) for name in INPUTS}
    dev_review = json.loads(verified["dev_parent_review"][0].read_text(encoding="utf-8-sig"))
    dev_lock = json.loads(verified["dev_input_lock"][0].read_text(encoding="utf-8-sig"))
    dev_contract = validate_dev_batch_contract(dev_lock, dev_review)
    specs_path = verified["scene_specs"][0]
    specs_rows = csv_rows(specs_path)
    specs = {row["scene_id"]: row for row in specs_rows}
    need(len(specs) == len(specs_rows), "Duplicate scene_id in scene_specs.csv")
    for row in specs_rows:
        count = active_count_from_spec(row)
        need(row["class_id"] != "NONE" or count == 0, f"Config NONE class has moving arms: {row['scene_id']}")
    index = json.loads(verified["test_input_index"][0].read_text(encoding="utf-8-sig"))
    need(index.get("shared_scenes_mat_sha256", "").lower() == verified["test_shared_scenes"][1],
         "TEST input index does not bind the expected shared MAT")
    wide = csv_rows(verified["test_wide_crosscheck"][0])
    long = csv_rows(verified["test_long_metrics"][0])
    performance, crosscheck = performance_rows(dev_review, dev_contract["by_scene"], long, wide, specs, index)
    feature_rows, morph = collect_test_scene_features(index, specs, verified["test_shared_scenes"][0],
                                                       verified["pinned_hdf5_reader"][0])
    morphology_by_id = {row["scene_id"]: row for row in feature_rows}
    for row in performance:
        if row["dataset"] == "TEST48":
            row["active_arm_count"] = morphology_by_id[row["scene_id"]]["active_arm_count"]
            row["active_arm_count_source"] = morphology_by_id[row["scene_id"]]["active_arm_count_source"]
            row["config_target_active_arm_count"] = morphology_by_id[row["scene_id"]]["config_target_active_arm_count"]
            row["active_arm_count_config_match"] = morphology_by_id[row["scene_id"]]["active_arm_count_config_match"]
    summary, loss_rows = summarize(performance)
    manifest = {
        "schema": "C5_ACTIVE_MORPH_SUBGROUP_AUDIT_V1", "status": "PASS_READ_ONLY_PINNED_INPUTS",
        "source_sha256": sha256(Path(__file__)), "input_files": {
            name: {"path": str(path.resolve()), "sha256": digest, "bytes": path.stat().st_size}
            for name, (path, digest) in verified.items()
        },
        "grouping": {"active_arms": {"NONE": 0, "1": 1, "2": 2, "3": 3, "4": 4},
                     "task_groups": list(TASK_GROUPS), "wlt_tolerance_m": TOL_M,
                     "active_arm_count_derivation": {
                         DEV_BATCH_DATASET: {
                             "source": "configs/scene_specs.csv target_a1_m..target_a4_m",
                             "criterion": "count(abs(target - 0.15 m) > 1e-12 m)",
                         },
                         "TEST48": {
                             "source": "TEST_SCENES_SHARED_v1.mat scenePacks.scene.arms.rho_true",
                             "criterion": "count(ptp(rho_true, axis=0) > 1e-9 m)",
                             "validation": "per-scene observed active-arm mask equals config target mask; counts must match",
                         },
                     },
                     "win": "Q_C5 - Q_B < -1e-12 m", "loss": "Q_C5 - Q_B > 1e-12 m",
                     "tie": "abs(Q_C5 - Q_B) <= 1e-12 m", "scene_equal_means": True,
                     "TEST_statistics_source": "paired_complete_48x6_long.csv (unrounded meter Q)",
                     "wide_csv_role": "cross-check only"},
        "counts": {DEV_BATCH_DATASET: len([r for r in performance if r["dataset"] == DEV_BATCH_DATASET]),
                   "TEST48": len([r for r in performance if r["dataset"] == "TEST48"])},
        "test_pack_order_contract": {
            "index_scene_ids_are_sorted": True,
            "producer_path": str(verified["test48_producer"][0].resolve()),
            "producer_sha256": verified["test48_producer"][1],
            "producer_order": "test48_entry_v1.m sorts sceneIds, then generates and stores scenePacks in the same loop order",
            "shared_mat_sha256": verified["test_shared_scenes"][1],
        },
        "dev_parent_review_batch_provenance": dev_contract["provenance"],
        "test_long_wide_crosscheck": crosscheck, "performance_groups": summary,
        "loss_scene_ids": {
            dataset: {
                ("NONE" if arm_count == 0 else str(arm_count)): {
                    task: [row["scene_id"] for row in loss_rows
                           if row["dataset"] == dataset
                           and row["analysis_active_arm_group"] == ("NONE" if arm_count == 0 else str(arm_count))
                           and row["analysis_task_group"] == task]
                    for task in TASK_GROUPS
                }
                for arm_count in ARM_GROUPS
            }
            for dataset in (DEV_BATCH_DATASET, "TEST48")
        },
        "test_shared_morphology_and_reference": morph,
        "interpretation_limits": [
            "C5's adaptation is position-loop compensation; the original B attitude inner loop is unchanged and is not evaluated here as an improvement.",
            "TEST active-arm subgrouping is post-hoc and is not a preregistered acceptance criterion.",
            "Active and NONE rows are different frozen scenes; they are not same-scene morphology-on/off counterfactuals.",
            "These grouped Q results do not establish morphology planning, obstacle clearance, energy savings, or morphology estimation benefits.",
        ],
    }
    all_outputs = ["morph_active_count_performance.csv", "morph_active_count_losses.csv",
                   "test_scene_morphology_reference.csv", "audit_summary_v1.json", "FINDINGS_ZH.md"]
    need(all(not (OUT / name).exists() for name in all_outputs), "Refusing to overwrite existing audit outputs")
    write_csv_atomic(OUT / all_outputs[0], [
        {**row, "mean_Q_B_mm": None if row["mean_Q_B_m"] is None else row["mean_Q_B_m"] * 1000,
         "mean_Q_C5_mm": None if row["mean_Q_C5_m"] is None else row["mean_Q_C5_m"] * 1000,
         "mean_delta_Q_mm": None if row["mean_delta_Q_C5_minus_B_m"] is None else row["mean_delta_Q_C5_minus_B_m"] * 1000}
        for row in summary
    ])
    write_csv_atomic(OUT / all_outputs[1], loss_rows)
    write_csv_atomic(OUT / all_outputs[2], feature_rows)
    write_text_atomic(OUT / all_outputs[3], json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    findings = [
        "# C5 主动变形应用分层核查",
        "",
        f"输入包含 {manifest['counts'][DEV_BATCH_DATASET]} 条 C5 parent-review batch 记录（原始 split 为 DEV {dev_contract['provenance']['original_split_counts']['DEV']} 场 + VAL {dev_contract['provenance']['original_split_counts']['VAL']} 场；其中 {dev_contract['provenance']['new_run_count']} 条新运行记录为 DEV {dev_contract['provenance']['new_run_original_split_counts']['DEV']} + VAL {dev_contract['provenance']['new_run_original_split_counts']['VAL']}，{dev_contract['provenance']['reused_count']} 条复用记录均为 VAL）及 {manifest['counts']['TEST48']} 场 TEST；这不是 72 场独立 DEV。TEST 统计使用米制未舍入 Q，W/L/T 按 ±{TOL_M:.0e} m 判定。完整分组数值见 `morph_active_count_performance.csv`，输场见 `morph_active_count_losses.csv`；该表以 `analysis_active_arm_group` 和 `analysis_task_group` 标明分组，因此同一场景可在 ALL 与具体任务组中各出现一次。JSON 中的 `loss_scene_ids` 按数据集×活动臂组×任务组保存名单。",
        "活动臂数口径：DEV72 batch 由 scene_specs.csv 的四个 target_a*_m 相对 0.15 m 基准计算；TEST48 由冻结 scenePacks 的 rho_true 实际变化计算，并逐场验证活动臂掩码和配置目标一致。",
        "",
        f"冻结 TEST 共享场景中记录了 {morph['active_arm_instance_count']} 个实际活动臂实例；实际伸展幅度范围为 {morph['active_extension_amplitude_range_m'][0]:.6g}–{morph['active_extension_amplitude_range_m'][1]:.6g} m，活动段 `rhoDot_true` 峰值范围为 {morph['max_abs_rhoDot_true_active_range_mps'][0]:.6g}–{morph['max_abs_rhoDot_true_active_range_mps'][1]:.6g} m/s。全 TEST 的 `rho_hat` 为常值 {morph['rho_hat_min_m']:.6g} m，`rhoDot_hat` 为常值 {morph['rhoDot_hat_value_mps']:.6g} m/s。各任务参考速度/加速度范数峰值详见 JSON 和逐场 CSV。",
        "",
        "方法范围是位置环补偿；原 B 姿态内环保持不变。本核查不声称姿态精度或双环学习收益。",
        "",
        "TEST 分层是在冻结场景上的事后描述，不是预注册验收。`NONE` 与变形组对应不同场景，不能解释为同一轨迹/风场下的形态开关反事实；分组表现也不能单独证明形态规划、净空、能耗或形态估计收益。",
        "",
        "复现命令（PowerShell 7）：",
        "```powershell",
        "$env:OPENBLAS_NUM_THREADS='1'; $env:OMP_NUM_THREADS='1'; $env:MKL_NUM_THREADS='1'; $env:PYTHONDONTWRITEBYTECODE='1'",
        "python reports/c5_active_morph_application_20261024/data_audit_v1/audit_active_morph_subgroups_v1.py",
        "```",
    ]
    write_text_atomic(OUT / all_outputs[4], "\n".join(findings) + "\n")


if __name__ == "__main__":
    main()
