"""Audit a C5 matched-ablation FIRST or TAIL11 phase and summarize the fixed 12-scene screen."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path

import h5py
import numpy as np


ROOT = Path(__file__).resolve().parents[3]
REVIEW_DIR = Path(__file__).resolve().parent
V2_ENTRY = REVIEW_DIR / "audit_c5_matched_ablation_first_raw_v2.py"
V2_ENTRY_SHA = "b64f7d69c45ac713fa57022fc6bfcf0a35ff50f85d973673bd00f2cd7f6ae91f"
EVENT_AUDIT_SHA = "1a8106ca6df7bb75ecb7a9cf5a09b9f91bc6eaa38547917a1fab677092c3755a"
PILOT_REPORTS = {
    "C5_FREEZE_TRAINED_W0": ("C5_FREEZE_TRAINED_W0_FIRST_RAW_PARENT_AUDIT_v1.json",
                             "727031d9107da1636b7d27fb7a0e04f6a6761a4507fc2a0d5a299df2b08dfa97"),
    "C5_NO_DELAYED_PREDICTION": ("C5_NO_DELAYED_PREDICTION_FIRST_RAW_PARENT_AUDIT_v1.json",
                                 "d0d0f3f2fa38f5499aca53c642a1ec65d20758bbc18e67cba2d55fede6e6289d"),
}
FIRST_SCENE = "DL1018_VAL_T1_C00_W07"
VARIANTS = tuple(PILOT_REPORTS)
TIE_TOLERANCE_M = 1e-12
WIND_BANDS = {
    "W00_W08": set(range(0, 9)),
    "W09_W11": set(range(9, 12)),
    "W12_W14": set(range(12, 15)),
    "W15": {15},
}


def sha(path: Path | str) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load(path: Path | str):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def module_at(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def resolve(root: Path, path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else root / p


def same_path(a: str | Path, b: str | Path) -> bool:
    return Path(a).resolve() == Path(b).resolve()


def normalize_records(value, phase: str, expected_count: int) -> list[dict]:
    if isinstance(value, dict):
        assert phase == "FIRST", "a single JSON object is only valid for FIRST"
        records = [value]
    elif isinstance(value, list):
        records = value
    else:
        raise TypeError(f"records must be a dict or list, got {type(value).__name__}")
    assert len(records) == expected_count
    assert all(isinstance(record, dict) for record in records)
    return records


def scene_parts(scene_id: str) -> tuple[str, str, int]:
    parts = scene_id.split("_")
    task = next(part for part in parts if len(part) == 2 and part[0] == "T" and part[1].isdigit())
    wind = next(part for part in parts if len(part) == 3 and part[0] == "W" and part[1:].isdigit())
    return task, wind, int(wind[1:])


def compare(delta_m: float) -> str:
    if delta_m < -TIE_TOLERANCE_M:
        return "WIN"
    if delta_m > TIE_TOLERANCE_M:
        return "LOSS"
    return "TIE"


def metric_mean(items: list[dict]) -> dict:
    numeric_keys = sorted({key for item in items for key, value in item.items()
                           if isinstance(value, (int, float)) and not isinstance(value, bool)})
    return {key: math.fsum(float(item[key]) for item in items) / len(items)
            for key in numeric_keys if all(key in item and isinstance(item[key], (int, float))
                                           and not isinstance(item[key], bool) for item in items)}


def one_comparison(rows: list[dict], baseline: str) -> dict:
    outcomes = []
    for row in rows:
        delta = row["deltas_Q_m"][baseline]
        outcomes.append((row["scene_id"], delta, compare(delta)))
    return {
        "wins": sum(outcome == "WIN" for _, _, outcome in outcomes),
        "losses": sum(outcome == "LOSS" for _, _, outcome in outcomes),
        "ties": sum(outcome == "TIE" for _, _, outcome in outcomes),
        "wins_improved_gt_1um": sum(delta < -1e-6 for _, delta, _ in outcomes),
        "wins_improved_gt_10um": sum(delta < -10e-6 for _, delta, _ in outcomes),
        "loss_scenes": [scene for scene, _, outcome in outcomes if outcome == "LOSS"],
        "tie_scenes": [scene for scene, _, outcome in outcomes if outcome == "TIE"],
    }


def summarize_screen(rows: list[dict], variant: str, scene_order: list[str]) -> dict:
    assert [row["scene_id"] for row in rows] == scene_order
    assert len(rows) == 12 and len({row["scene_id"] for row in rows}) == 12
    groups: dict[str, list[dict]] = {"ALL12": list(rows)}
    for task in ("T1", "T2", "T3"):
        groups[task] = [row for row in rows if row["task"] == task]
    for band, winds in WIND_BANDS.items():
        groups[band] = [row for row in rows if row["wind_number"] in winds]
    hf = [row for row in rows if 9 <= row["wind_number"] <= 14]
    w15 = [row for row in rows if row["wind_number"] == 15]
    groups["HF_W09_W14"] = hf
    groups["W15"] = w15
    for wind in sorted({row["wind"] for row in rows}):
        groups[wind] = [row for row in rows if row["wind"] == wind]

    summaries = {}
    for name, selected in groups.items():
        assert selected
        methods = [variant, "B_TRACEABLE", "C3", "C5_M110"]
        means = {method: metric_mean([row["methods"][method] for row in selected]) for method in methods}
        summaries[name] = {
            "scene_count": len(selected),
            "scene_ids": [row["scene_id"] for row in selected],
            "equal_scene_weighted_mean_metrics": means,
            "candidate_vs_B": one_comparison(selected, "B_TRACEABLE"),
            "candidate_vs_C3": one_comparison(selected, "C3"),
            "candidate_vs_C5_M110": one_comparison(selected, "C5_M110"),
        }
    return {
        "scene_count": len(rows),
        "scene_order": scene_order,
        "tie_tolerance_m": TIE_TOLERANCE_M,
        "wind_band_definitions": {name: sorted(winds) for name, winds in WIND_BANDS.items()},
        "groups": summaries,
        "all_losses_vs_B": [row for row in rows if compare(row["deltas_Q_m"]["B_TRACEABLE"]) == "LOSS"],
        "all_losses_vs_C3": [row for row in rows if compare(row["deltas_Q_m"]["C3"]) == "LOSS"],
        "all_losses_vs_C5_M110": [row for row in rows if compare(row["deltas_Q_m"]["C5_M110"]) == "LOSS"],
    }


def audited_pilot_rows(pilot_dir: Path, variant: str, contract: dict, parent_review: dict) -> tuple[list[dict], dict]:
    filename, expected_sha = PILOT_REPORTS[variant]
    path = pilot_dir / filename
    assert path.is_file() and sha(path).lower() == expected_sha
    report = load(path)
    assert report["schema"] == "C5_MATCHED_ABLATION_FIRST_RAW_PARENT_AUDIT_V1"
    assert report["status"] == "PASS_C5_MATCHED_ABLATION_FIRST_RAW_ALL_EVENTS"
    assert report["variant_id"] == variant and report["scene_id"] == contract["first_scene_id"] == FIRST_SCENE
    assert report["event_count"] == 1968 and report["plant_calls_in_audit"] == 0
    assert report["TEST_accessed"] is False and report["training_steps"] == report["optimizer_steps"] == 0
    assert report["cfg_opts_leaf_counts"]["cfg"] == 120 and report["cfg_opts_leaf_counts"]["opts"] == 43
    assert report["W0_sha256"].lower() == contract["model"]["W0_sha256"].lower()
    assert report["natural_os_exit"]["exit_code"] == 0
    os_path = Path(report["natural_os_exit"]["path"])
    assert os_path.is_file() and sha(os_path).lower() == report["natural_os_exit"]["sha256"].lower()
    os_exit = load(os_path)
    assert os_exit["matlab_os_exit_code"] == 0 and os_exit["variant_id"] == variant and os_exit["phase"] == "FIRST"
    parent_row = next(row for row in parent_review["rows"] if row["scene_id"] == FIRST_SCENE)
    assert parent_row["status"] == "PASS_REUSED_C5_SCREEN_AUDIT" and parent_row["event_count"] == 1968
    methods = {variant: report["run_metrics"],
               "B_TRACEABLE": report["baseline_parent_audit_methods"]["B_TRACEABLE"],
               "C3": report["baseline_parent_audit_methods"]["C3"],
               "C5_M110": report["baseline_parent_audit_methods"]["C5_M110"]}
    for name, metric_key in (("B_TRACEABLE", "B_metrics"), ("C3", "C3_metrics"), ("C5_M110", "C5_metrics")):
        assert methods[name]["Q_0_20_m"] == parent_row[metric_key]["Q_0_20_m"]
        assert methods[name]["sha256"].lower() == parent_row[metric_key]["sha256"].lower()
    assert report["run_metrics"]["sha256"].lower() == report["run_artifacts"]["raw_sha256"].lower()
    identities = {item["external_identity_sha256"] for item in methods.values()}
    assert len(identities) == 1
    delta_q = {name: methods[variant]["Q_0_20_m"] - methods[name]["Q_0_20_m"]
               for name in ("B_TRACEABLE", "C3", "C5_M110")}
    task, wind, wind_number = scene_parts(FIRST_SCENE)
    return ([{
        "scene_id": FIRST_SCENE, "task": task, "wind": wind, "wind_number": wind_number,
        "phase": "FIRST_PILOT_REUSE", "new_raw_audit": False,
        "methods": methods, "deltas_Q_m": delta_q,
        "comparisons": {name: compare(value) for name, value in delta_q.items()},
        "event_checks": report["event_checks"],
        "provenance": {"pilot_audit_path": str(path), "pilot_audit_sha256": expected_sha,
                       "pilot_raw_sha256": report["run_metrics"]["sha256"],
                       "pilot_status_sha256": report["run_artifacts"]["run_status_sha256"],
                       "external_identity_sha256": next(iter(identities))},
    }], report)


def read_snapshot(path: Path, expected_sha: str, base) -> dict:
    assert path.is_file() and sha(path).lower() == expected_sha.lower()
    with h5py.File(path, "r") as mat:
        return {key: base.h5_tree_cell_safe(mat[key])
                for key in ("cfg", "opts", "W0", "modelIdentity", "sceneIdentity", "sourceIdentity")}


def verify_first_tail_snapshot_pair(variant: str, pilot: dict, lock: dict, contract: dict,
                                    tail_snapshot: dict, tail_snapshot_path: Path,
                                    digest: dict, base, decoder) -> dict:
    first_lock_ref = pilot["source_files"]["lock"]
    first_lock_path = Path(first_lock_ref["path"])
    assert first_lock_path.is_file() and sha(first_lock_path).lower() == first_lock_ref["sha256"].lower()
    first_lock = load(first_lock_path)
    assert first_lock["variant_id"] == variant
    first_inventory = first_lock["active_source_inventory"]
    tail_inventory = lock["active_source_inventory"]
    assert len(first_inventory) == len(tail_inventory) == 32
    first_role_sha = [(item["role"], item["sha256"].lower()) for item in first_inventory]
    tail_role_sha = [(item["role"], item["sha256"].lower()) for item in tail_inventory]
    assert first_role_sha == tail_role_sha

    first_snapshot_ref = pilot["source_files"]["snapshot"]
    first_snapshot = read_snapshot(Path(first_snapshot_ref["path"]), first_snapshot_ref["sha256"], base)
    assert base.equal_tree(first_snapshot["cfg"], tail_snapshot["cfg"], decoder) == 120
    assert base.equal_tree(first_snapshot["opts"], tail_snapshot["opts"], decoder, ignore_marker=True) == 43
    assert base.equal_tree(first_snapshot["modelIdentity"], tail_snapshot["modelIdentity"], decoder) == 6
    assert np.array_equal(np.asarray(first_snapshot["W0"]), np.asarray(tail_snapshot["W0"]))
    assert base.matlab_text(first_snapshot["modelIdentity"]["W0_sha256"]).lower() == \
        base.matlab_text(tail_snapshot["modelIdentity"]["W0_sha256"]).lower() == contract["model"]["W0_sha256"].lower()
    source_arrays = []
    for snapshot, own_inventory in ((first_snapshot, first_inventory), (tail_snapshot, tail_inventory)):
        paths = [str(base.matlab_text(x)) for x in base.matlab_flat(snapshot["sourceIdentity"]["active_paths"])]
        shas = [str(base.matlab_text(x)).lower() for x in base.matlab_flat(snapshot["sourceIdentity"]["active_sha256"])]
        assert len(paths) == len(shas) == 32
        assert [Path(x).resolve() for x in paths] == [Path(item["path"]).resolve() for item in own_inventory]
        assert shas == [item["sha256"].lower() for item in own_inventory]
        source_arrays.append((paths, shas))
    path_differences = [
        {"role": first_inventory[i]["role"], "first_path": source_arrays[0][0][i],
         "tail_path": source_arrays[1][0][i]}
        for i in range(32)
        if Path(source_arrays[0][0][i]).resolve() != Path(source_arrays[1][0][i]).resolve()
    ]
    assert source_arrays[0][1] == source_arrays[1][1]
    return {"same_variant": variant, "first_snapshot_sha256": first_snapshot_ref["sha256"],
            "tail_snapshot_sha256": digest["snapshot"], "cfg_leaf_count_equal": 120,
            "opts_leaf_count_equal_ignore_marker": 43, "modelIdentity_leaf_count_equal": 6,
            "active_source_count": 32,
            "active_source_roles_and_sha256_equal": True,
            "each_snapshot_paths_sha256_match_own_lock": True,
            "cross_root_path_differences": path_differences,
            "W0_sha256": contract["model"]["W0_sha256"],
            "tail_snapshot_path": str(tail_snapshot_path)}


def audit_record(record: dict, scene_id: str, batch_index: int, phase: str, variant: str,
                 config: Path, files: dict, digest: dict, batch: dict, lock: dict,
                 contract: dict, flags: dict, snapshot: dict, leaves: dict,
                 base, decoder, scorer, event_module, parent_review: dict) -> dict:
    assert record["scene_id"] == scene_id and record["batch_index"] == batch_index
    assert record["status"] == "RUN_COMPLETE_RAW_PENDING_AUDIT" and record["plant_calls"] == 1
    raw_path = Path(record["raw_path"]).resolve()
    attempt_dir = raw_path.parent
    assert raw_path.name == "raw_run.mat" and attempt_dir.name == "attempt_01"
    assert attempt_dir.parent.name == variant and attempt_dir.parent.parent.name == scene_id
    assert attempt_dir.parent.parent.parent.parent.resolve() == config.resolve()
    assert attempt_dir.parent.parent.parent.name.startswith("runs_c5_matched_ablation_")
    status_path = attempt_dir / "run_status.json"
    run_start_path = attempt_dir / "run_start.mat"
    assert same_path(record["run_status_path"], status_path)
    assert same_path(record["run_start_path"], run_start_path)
    assert raw_path.is_file() and sha(raw_path).lower() == record["raw_sha256"].lower()

    status = base.verify_status_file(
        status_path, record["run_status_sha256"], scene_id=scene_id, raw_path=raw_path,
        raw_sha=record["raw_sha256"], coordinate_mask=None, require_event_counts=True,
        required_markers=("raw", "run_start", "attempt_started_marker", "first_plant_step_marker"))
    assert status["schema"] == "C5_MATCHED_ABLATION_RUN_STATUS_V1"
    assert status["phase"] == phase and status["variant_id"] == status["ablation_mode"] == variant
    assert status["batch_id"] == batch["batch_id"] and status["batch_index"] == batch_index
    for key, sha_key in (("source_binding_sha256", "binding"), ("release_sha256", "release"),
                         ("input_lock_sha256", "lock"), ("run_contract_sha256", "contract"),
                         ("prepare_result_sha256", "prepare"), ("snapshot_sha256", "snapshot"),
                         ("preflight_sha256", "preflight")):
        assert status[key].lower() == digest[sha_key]
    for key in ("actual_weight_update_enabled", "actual_prediction_gradient_enabled"):
        assert bool(status[key]) is flags[key]
    assert status["physical_B_source_sha256"].lower() == record["physical_B_source_sha256"].lower()
    assert status["C3_raw_sha256"].lower() == record["C3_raw_sha256"].lower()

    run_start = base.matlab_section_safe(run_start_path, "runStart", decoder)
    assert base.matlab_text(run_start["schema"]) == "C5_MATCHED_ABLATION_RUN_START_V1"
    assert base.matlab_text(run_start["batch_id"]) == batch["batch_id"]
    assert base.matlab_scalar(run_start["batch_index"]) == batch_index
    assert base.matlab_text(run_start["phase"]) == phase and base.matlab_text(run_start["scene_id"]) == scene_id
    assert base.matlab_text(run_start["variant_id"]) == base.matlab_text(run_start["ablation_mode"]) == variant
    assert base.matlab_text(run_start["W0_sha256"]).lower() == contract["model"]["W0_sha256"].lower()
    assert base.matlab_text(run_start["source_scene_id"]) == base.matlab_text(run_start["scene_identity"]["raw_scene_id"])
    assert base.matlab_flat(run_start["coordinate_mask"]) == [1.0, 1.0, 0.0]
    for key, sha_key in (("source_binding_sha256", "binding"), ("release_sha256", "release"),
                         ("preflight_sha256", "preflight"), ("input_lock_sha256", "lock"),
                         ("run_contract_sha256", "contract"), ("prepare_result_sha256", "prepare"),
                         ("cfg_opts_snapshot_sha256", "snapshot")):
        assert base.matlab_text(run_start[key]).lower() == digest[sha_key]
    assert base.matlab_scalar(run_start["plant_calls_before_invocation"]) == 0
    assert base.matlab_scalar(run_start["training_steps"]) == base.matlab_scalar(run_start["optimizer_steps"]) == 0
    assert base.matlab_scalar(run_start["TEST_accessed"]) in (0, False)
    for key, expected in flags.items():
        assert bool(base.matlab_scalar(run_start[key])) is expected
    assert base.equal_tree(snapshot["cfg"], run_start["cfg"], decoder) == 120
    assert base.equal_tree(snapshot["opts"], run_start["opts"], decoder, ignore_marker=True) == 43
    assert base.equal_tree(snapshot["modelIdentity"], run_start["model_identity"], decoder) == 6
    assert base.equal_tree(snapshot["sourceIdentity"], run_start["source_identity"], decoder) == leaves["sourceIdentity"]
    assert base.matlab_flat(snapshot["opts"]["position_coordinate_mask"]) == [1.0, 1.0, 0.0]
    assert bool(base.matlab_scalar(snapshot["opts"]["position_delayed_prediction_enabled"]))
    assert bool(base.matlab_scalar(snapshot["opts"]["stage1_position_runtime"]["update_enabled"]))

    active = lock["active_source_inventory"]
    expected_paths = [x["path"] for x in active]
    expected_shas = [x["sha256"].lower() for x in active]
    for source_identity in (snapshot["sourceIdentity"], run_start["source_identity"]):
        paths = [str(base.matlab_text(x)) for x in base.matlab_flat(source_identity["active_paths"])]
        shas = [str(base.matlab_text(x)).lower() for x in base.matlab_flat(source_identity["active_sha256"])]
        assert len(paths) == len(shas) == 32
        assert [Path(x).resolve() for x in paths] == [Path(x).resolve() for x in expected_paths]
        assert shas == expected_shas

    w0 = np.asarray(snapshot["W0"], dtype=float)
    assert w0.shape == (33, 3) and np.array_equal(w0, np.asarray(run_start["W0"], dtype=float))
    assert hashlib.sha256(np.asarray(w0, dtype="<f8").tobytes(order="F")).hexdigest() == contract["model"]["W0_sha256"].lower()
    model_identity = snapshot["modelIdentity"]
    assert base.matlab_text(model_identity["model_id"]) == contract["model"]["id"]
    assert base.matlab_text(model_identity["W0_sha256"]).lower() == contract["model"]["W0_sha256"].lower()
    assert base.matlab_text(model_identity["normalizer_arrays_sha256"]).lower() == contract["model"]["normalizer_arrays_sha256"].lower()
    for key in ("input_dim", "window", "selected_step"):
        assert base.matlab_scalar(model_identity[key]) == contract["model"][key]
    assert bool(base.matlab_scalar(run_start["initial_weight_reset_from_W0"]))
    assert bool(base.matlab_scalar(run_start["controller_state_reset_for_scene"]))

    scene_row = next(x for x in lock["scenes"] if x["scene_id"] == scene_id)
    assert base.matlab_text(run_start["physical_B_source_path"]) == scene_row["B_source"]["path"]
    assert base.matlab_text(run_start["physical_B_source_sha256"]).lower() == scene_row["B_source"]["sha256"].lower()
    assert base.matlab_text(run_start["scene_identity"]["B_raw_path"]) == scene_row["B_source"]["path"]
    assert base.matlab_text(run_start["scene_identity"]["B_raw_sha256"]).lower() == scene_row["B_source"]["sha256"].lower()
    assert base.matlab_text(run_start["C3_raw_path"]) == scene_row["C3_reuse"]["raw_path"]
    assert base.matlab_text(run_start["C3_raw_sha256"]).lower() == scene_row["C3_reuse"]["raw_sha256"].lower()
    assert same_path(base.matlab_text(run_start["C3_raw_path"]), scene_row["C3_reuse"]["raw_path"])
    scene_names = [str(base.matlab_text(x)) for x in base.matlab_flat(snapshot["sceneIdentity"]["scene_id"])]
    scene_index = scene_names.index(scene_id)
    base.compare_scene_identity(run_start["scene_identity"], base.scene_identity_row(snapshot["sceneIdentity"], scene_index), decoder)

    assert Path(status["run_start_path"]).resolve() == run_start_path.resolve()
    assert sha(run_start_path).lower() == status["run_start_sha256"].lower() == record["run_start_sha256"].lower()
    raw_identity = base.matlab_section_safe(raw_path, "runIdentity", decoder)
    for key, expected in flags.items():
        assert bool(base.matlab_scalar(raw_identity[key])) is expected
    for key, expected in (("schema", "C5_MATCHED_ABLATION_RUN_IDENTITY_V1"), ("variant_id", variant),
                          ("ablation_mode", variant), ("scene_id", scene_id), ("candidate", contract["candidate"])):
        assert base.matlab_text(raw_identity[key]) == expected
    assert base.matlab_flat(raw_identity["coordinate_mask"]) == [1.0, 1.0, 0.0]
    assert base.matlab_text(raw_identity["W0_sha256"]).lower() == contract["model"]["W0_sha256"].lower()
    for key, sha_key in (("source_binding_sha256", "binding"), ("release_sha256", "release"),
                         ("preflight_sha256", "preflight"), ("input_lock_sha256", "lock"),
                         ("run_contract_sha256", "contract"), ("prepare_result_sha256", "prepare"),
                         ("cfg_opts_snapshot_sha256", "snapshot")):
        assert base.matlab_text(raw_identity[key]).lower() == digest[sha_key]
    assert base.matlab_text(raw_identity["run_start_sha256"]).lower() == sha(run_start_path).lower()
    assert base.equal_tree(snapshot["W0"], raw_identity["W0"], decoder) > 0
    assert base.equal_tree(snapshot["modelIdentity"], raw_identity["model_identity"], decoder) == 6
    assert base.equal_tree(snapshot["sourceIdentity"], raw_identity["source_identity"], decoder) == leaves["sourceIdentity"]
    assert base.equal_tree(run_start["scene_identity"], raw_identity["scene_identity"], decoder) > 0
    assert base.matlab_text(raw_identity["physical_B_source_path"]) == scene_row["B_source"]["path"]
    assert base.matlab_text(raw_identity["physical_B_source_sha256"]).lower() == scene_row["B_source"]["sha256"].lower()
    assert base.matlab_text(raw_identity["C3_raw_path"]) == scene_row["C3_reuse"]["raw_path"]
    assert base.matlab_text(raw_identity["C3_raw_sha256"]).lower() == scene_row["C3_reuse"]["raw_sha256"].lower()
    assert base.matlab_scalar(raw_identity["training_steps"]) == base.matlab_scalar(raw_identity["optimizer_steps"]) == 0
    assert base.matlab_scalar(raw_identity["TEST_accessed"]) in (0, False)

    raw_score = scorer.score({"scene_id": scene_id, "method": variant, "path": str(raw_path), "sha256": record["raw_sha256"]})
    parent_row = next(row for row in parent_review["rows"] if row["scene_id"] == scene_id)
    assert parent_row["status"] == "PASS_REUSED_C5_SCREEN_AUDIT" and parent_row["event_count"] == 1968
    baseline = {name: parent_row[key] for name, key in (("B_TRACEABLE", "B_metrics"), ("C3", "C3_metrics"),
                                                          ("C5_M110", "C5_metrics"))}
    assert same_path(baseline["C3"]["path"], scene_row["C3_reuse"]["raw_path"])
    assert baseline["C3"]["sha256"].lower() == scene_row["C3_reuse"]["raw_sha256"].lower()
    # The lock's B_scene mapping is the legacy physical input; scored traceable B
    # has separate parent-review provenance, so the two lineages need not share a path.
    physical_b_path = Path(scene_row["B_source"]["path"])
    assert physical_b_path.is_file() and sha(physical_b_path).lower() == scene_row["B_source"]["sha256"].lower()
    identities = {item["external_identity_sha256"] for item in baseline.values()}
    identities.add(raw_score["external_identity_sha256"])
    assert len(identities) == 1
    for metric in baseline.values():
        assert metric["scene_id"] == scene_id
        path = Path(metric["path"])
        assert path.is_file() and sha(path).lower() == metric["sha256"].lower()

    event_result = event_module.audit_events(raw_path, run_start["cfg"], variant, w0, contract["model"]["W0_sha256"])
    assert event_result["event_count"] == 1968 and event_result["actual_prediction_norm_max"] == 0
    methods = {variant: raw_score, **baseline}
    deltas = {name: raw_score["Q_0_20_m"] - metric["Q_0_20_m"] for name, metric in baseline.items()}
    task, wind, wind_number = scene_parts(scene_id)
    return {
        "scene_id": scene_id, "task": task, "wind": wind, "wind_number": wind_number,
        "phase": phase, "new_raw_audit": True, "methods": methods, "deltas_Q_m": deltas,
        "comparisons": {name: compare(value) for name, value in deltas.items()},
        "event_count": event_result["event_count"], "event_checks": event_result,
        "provenance": {"raw_path": str(raw_path), "raw_sha256": record["raw_sha256"],
                       "run_status_sha256": record["run_status_sha256"], "run_start_sha256": record["run_start_sha256"],
                       "external_identity_sha256": next(iter(identities)), "batch_index": batch_index},
    }


def audit_phase(variant: str, phase: str, scene_id: str | None, experiment_root: Path,
                execution_report_root: Path, pilot_audit_dir: Path) -> dict:
    config = experiment_root / variant
    helper = module_at(V2_ENTRY, "c5_matched_ablation_first_raw_v2_helpers")
    assert sha(V2_ENTRY).lower() == V2_ENTRY_SHA
    assert sha(helper.EVENT_AUDIT).lower() == EVENT_AUDIT_SHA
    assert sha(helper.BASE_AUDITOR).lower() == helper.BASE_AUDITOR_SHA
    assert sha(helper.DECODER).lower() == helper.DECODER_SHA
    assert sha(helper.SCORER).lower() == helper.SCORER_SHA
    assert sha(helper.C5_DEV72_REVIEW).lower() == helper.C5_DEV72_REVIEW_SHA
    base = helper.module_at(helper.BASE_AUDITOR, "pinned_c5_dev72_parent_auditor")
    decoder = helper.module_at(helper.DECODER, "pinned_matlab_decoder")
    scorer = helper.module_at(helper.SCORER, "pinned_raw_metric_scorer")
    event_module = helper.module_at(helper.EVENT_AUDIT, "c5_matched_ablation_event_audit")

    files = {
        "lock": config / "C5_ABLATION_INPUT_LOCK_v1.json",
        "contract": config / "C5_ABLATION_RUN_CONTRACT_v1.json",
        "binding": config / "C5_ABLATION_SOURCE_BINDING_v1.json",
        "prepare": config / "C5_ABLATION_PREPARE_RESULT_v1.json",
        "snapshot": config / "C5_ABLATION_PREPARED_CFG_OPTS_v1.mat",
        "preflight": config / "C5_ABLATION_RUNNER_PREFLIGHT_v1.json",
        "release_contract": config / "C5_ABLATION_PARENT_RELEASE_CONTRACT_v1.json",
        "release": config / f"C5_ABLATION_{phase}_PARENT_RELEASE_v1.json",
        "batch": config / f"C5_ABLATION_{phase}_BATCH_STATUS_v1.json",
        "body": config / f"C5_ABLATION_{phase}_BODY_COMPLETE_v1.json",
    }
    exit_path = execution_report_root / f"C5_{variant}_{phase}_MATLAB_OS_EXIT_v1.json"
    assert exit_path.is_file(), f"natural {phase} OS exit record is not present"
    os_exit = load(exit_path)
    assert os_exit.get("matlab_os_exit_code") == 0, (phase, os_exit.get("matlab_os_exit_code"))
    assert all(path.is_file() for key, path in files.items() if key not in ("batch", "body")), files

    lock, contract, binding, prep, preflight, parent_contract, release = (
        load(files[key]) for key in ("lock", "contract", "binding", "prepare", "preflight", "release_contract", "release"))
    assert contract["scene_ids"][0] == contract["first_scene_id"] == FIRST_SCENE and len(contract["scene_ids"]) == 12
    expected_scenes = [contract["scene_ids"][0]] if phase == "FIRST" else contract["scene_ids"][1:]
    expected_count = 1 if phase == "FIRST" else 11
    assert len(expected_scenes) == expected_count
    if scene_id is not None:
        assert scene_id in expected_scenes
        if phase == "FIRST":
            assert scene_id == contract["first_scene_id"]

    digest = {key: sha(path) for key, path in files.items() if key not in ("batch", "body")}
    assert lock["schema"] == "C5_MATCHED_ABLATION_INPUT_LOCK_V1"
    assert lock["state"] == "LOCKED_C5_MATCHED_ABLATION_NO_PLANT_PARENT_REVIEW_REQUIRED_V1"
    assert lock["variant_id"] == lock["ablation_mode"] == variant and lock["plant_authorized_by_this_lock"] is False
    assert lock["scene_ids"] == contract["scene_ids"] and lock["first_scene_id"] == contract["first_scene_id"]
    assert [row["scene_id"] for row in lock["scenes"]] == contract["scene_ids"]
    assert contract["schema"] == "C5_MATCHED_ABLATION_RUN_CONTRACT_V1" and contract["state"] == lock["state"]
    assert contract["candidate"] == "C5_AXIS_MIXED_COORDINATE_M110"
    assert len(lock["scenes"]) == 12
    assert len(lock["active_source_inventory"]) == lock["source_counts"]["total"] == 32
    assert lock["source_counts"]["total"] == 32
    mode = variant == "C5_NO_DELAYED_PREDICTION"
    flags = {"actual_weight_update_enabled": mode, "actual_prediction_gradient_enabled": False,
             "legacy_stage1_update_enabled": True}
    for key, expected in flags.items():
        assert bool(lock[key]) is expected and bool(contract[key]) is expected and bool(binding[key]) is expected
        assert bool(prep[key]) is expected and bool(preflight[key]) is expected and bool(release[key]) is expected
    assert lock["coordinate_mask"] == [1, 1, 0]
    assert lock["position_delayed_prediction_enabled"] is True and lock["stage1_update_enabled"] is True
    assert contract["position_delayed_prediction_enabled"] is True and contract["stage1_update_enabled"] is True
    assert binding["coordinate_mask"] == release["coordinate_mask"] == [1, 1, 0]
    assert binding["state"] == "SOURCE_BOUND_NO_PLANT_PARENT_REVIEW_REQUIRED_V1" and binding["plant_authorized"] is False
    assert binding["input_lock_sha256"].lower() == digest["lock"]
    assert binding["contract_sha256"].lower() == digest["contract"]
    assert binding["prepare_sha256"].lower() == lock["source_files"]["prepare_entry"]["sha256"].lower()
    assert binding["runner_sha256"].lower() == lock["source_files"]["runner_entry"]["sha256"].lower()
    assert prep["status"] == "PREPARED_C5_MATCHED_ABLATION_NO_PLANT_WAIT_PARENT_RELEASE_V1"
    assert prep["input_lock_sha256"].lower() == digest["lock"] and prep["contract_sha256"].lower() == digest["contract"]
    assert prep["snapshot_sha256"].lower() == digest["snapshot"] and prep["plant_calls"] == 0
    assert prep["TEST_accessed"] is False
    assert preflight["input_lock_sha256"].lower() == digest["lock"]
    assert preflight["contract_sha256"].lower() == digest["contract"]
    assert preflight["source_binding_sha256"].lower() == digest["binding"]
    assert preflight["prepare_result_sha256"].lower() == digest["prepare"]
    assert preflight["snapshot_sha256"].lower() == digest["snapshot"]
    assert preflight["runner_sha256"].lower() == binding["runner_sha256"].lower()
    assert preflight["status"] == "PREFLIGHT_COMPLETE_NO_PLANT_WAIT_PARENT_RELEASE_V1"
    assert preflight["plant_calls"] == 0 and preflight["TEST_accessed"] is False
    assert binding["active_source_count"] == preflight["active_source_count"] == preflight["which_checks"] == 32
    assert release["schema"] == "C5_MATCHED_ABLATION_PARENT_RELEASE_V1"
    assert release["state"] == f"APPROVED_C5_ABLATION_{phase}_V1" and release["phase"] == phase
    assert release["plant_authorized"] is True and release["scene_ids"] == expected_scenes
    assert release["first_scene_id"] == contract["first_scene_id"]
    assert release["max_new_Plant"] == expected_count
    assert release["parent_release_contract_sha256"].lower() == digest["release_contract"]
    for key in ("input_lock_sha256", "run_contract_sha256", "source_binding_sha256", "prepare_result_sha256",
                "snapshot_sha256", "runner_preflight_sha256"):
        expected = {"input_lock_sha256": "lock", "run_contract_sha256": "contract", "source_binding_sha256": "binding",
                    "prepare_result_sha256": "prepare", "snapshot_sha256": "snapshot", "runner_preflight_sha256": "preflight"}[key]
        assert release[key].lower() == digest[expected]
    assert release["runner_sha256"].lower() == binding["runner_sha256"].lower()
    assert release["launcher_sha256"].lower() == lock["source_files"]["parent_launcher"]["sha256"].lower()
    assert parent_contract["schema"] == "C5_MATCHED_ABLATION_PARENT_RELEASE_CONTRACT_V1"
    assert release["training_steps"] == release["optimizer_steps"] == release["new_B_sorties"] == 0
    assert release["TEST_accessed"] is False and release["automatic_retry"] is False
    assert release["parameter_or_seed_search"] is False

    helper.verify_ref_tree(lock.get("source_files", {}))
    helper.verify_ref_tree(lock.get("active_source_inventory", []))
    helper.verify_ref_tree(lock.get("shared_input_files", []))
    helper.verify_ref_tree(lock.get("upstream_refs", {}))
    helper.verify_ref_tree(binding.get("file_refs", []))
    assert same_path(binding["input_lock_path"], files["lock"])
    assert os_exit["schema"] == "C5_MATCHED_ABLATION_MATLAB_OS_EXIT_V1"
    assert os_exit["variant_id"] == variant and os_exit["phase"] == phase and os_exit["plant_authorized"] is True
    assert os_exit["release_sha256"].lower() == digest["release"]
    assert os_exit["runner_sha256"].lower() == binding["runner_sha256"].lower()
    assert os_exit["preflight_sha256"].lower() == digest["preflight"]
    launcher_ref = lock["source_files"]["parent_launcher"]
    assert same_path(os_exit["command_file"], launcher_ref["path"])
    assert os_exit["command_sha256"].lower() == launcher_ref["sha256"].lower()

    # Load both phase ledgers only after the matching phase has a natural OS0 record.
    batch, body = load(files["batch"]), load(files["body"])
    digest["batch"] = sha(files["batch"])
    digest["body"] = sha(files["body"])
    assert batch["schema"] == "C5_MATCHED_ABLATION_BATCH_V1" and body["schema"] == "C5_MATCHED_ABLATION_BODY_COMPLETE_V1"
    for obj in (batch, body):
        assert obj["status"] == "COMPLETE_RAW_PENDING_PARENT_AUDIT"
        assert obj["phase"] == phase and obj["variant_id"] == variant
        assert obj["plant_calls"] == expected_count and obj["training_steps"] == obj["optimizer_steps"] == 0
        assert obj["TEST_accessed"] is False
    assert batch["ablation_mode"] == variant
    assert batch["completed_scenes"] == expected_count and body["scene_count"] == expected_count
    assert batch["scene_ids"] == body["scene_ids"] == expected_scenes
    batch_records = normalize_records(batch["records"], phase, expected_count)
    body_records = normalize_records(body["records"], phase, expected_count)
    assert batch_records == body_records
    for record, expected_scene in zip(batch_records, expected_scenes):
        assert record["scene_id"] == expected_scene
    for obj in (batch, body):
        assert obj["source_binding_sha256"].lower() == digest["binding"]
        assert obj["release_sha256"].lower() == digest["release"]
        assert obj["runner_sha256"].lower() == binding["runner_sha256"].lower()
        assert obj["preflight_sha256"].lower() == digest["preflight"]

    with h5py.File(files["snapshot"], "r") as mat:
        snapshot = {key: base.h5_tree_cell_safe(mat[key])
                    for key in ("cfg", "opts", "W0", "modelIdentity", "sceneIdentity", "sourceIdentity")}
    leaves = {"cfg": base.equal_tree(snapshot["cfg"], snapshot["cfg"], decoder),
              "opts": base.equal_tree(snapshot["opts"], snapshot["opts"], decoder, ignore_marker=True),
              "modelIdentity": base.equal_tree(snapshot["modelIdentity"], snapshot["modelIdentity"], decoder),
              "sourceIdentity": base.equal_tree(snapshot["sourceIdentity"], snapshot["sourceIdentity"], decoder)}
    assert leaves["cfg"] == 120 and leaves["opts"] == 43 and leaves["modelIdentity"] == 6
    assert leaves["sourceIdentity"] > 0
    pilot_dir = pilot_audit_dir
    parent_review = load(helper.C5_DEV72_REVIEW)
    assert parent_review["status"] == "PASS_C5_DEV72_RAW_ALL_EVENTS_PARENT_AUDIT"
    assert sha(helper.C5_DEV72_REVIEW).lower() == helper.C5_DEV72_REVIEW_SHA
    pilots, pilot_rows_by_variant = {}, {}
    for pilot_variant in VARIANTS:
        pilot_rows, pilot = audited_pilot_rows(pilot_dir, pilot_variant, contract, parent_review)
        pilots[pilot_variant] = pilot
        pilot_rows_by_variant[pilot_variant] = pilot_rows
    assert pilots["C5_FREEZE_TRAINED_W0"]["scene_id"] == pilots["C5_NO_DELAYED_PREDICTION"]["scene_id"] == FIRST_SCENE

    cross_phase = None
    if phase == "TAIL11":
        pilot = pilots[variant]
        cross_phase = verify_first_tail_snapshot_pair(variant, pilot, lock, contract, snapshot,
                                                     files["snapshot"], digest, base, decoder)
        pilot_release = pilot["source_files"]["release"]
        assert release["pilot_raw_sha256"].lower() == pilot["run_artifacts"]["raw_sha256"].lower()
        assert same_path(release["pilot_raw_path"], pilot["run_artifacts"]["raw_path"])
        assert release["pilot_run_status_sha256"].lower() == pilot["run_artifacts"]["run_status_sha256"].lower()
        assert same_path(release["pilot_run_status_path"], pilot["run_artifacts"]["run_status_path"])
        assert release["pilot_release_sha256"].lower() == pilot_release["sha256"].lower()

    scene_rows = []
    for index, (record, expected_scene) in enumerate(zip(batch_records, expected_scenes), start=1):
        scene_rows.append(audit_record(record, expected_scene, index, phase, variant, config, files,
                                       digest, batch, lock, contract, flags, snapshot, leaves,
                                       base, decoder, scorer, event_module, parent_review))
    if phase == "TAIL11":
        full_rows = pilot_rows_by_variant[variant] + scene_rows
        summary = summarize_screen(full_rows, variant, contract["scene_ids"])
    else:
        full_rows = scene_rows
        summary = None

    return {
        "schema": "C5_MATCHED_ABLATION_SCREEN12_RAW_PARENT_AUDIT_V1" if phase == "TAIL11"
                  else "C5_MATCHED_ABLATION_PHASE_RAW_PARENT_AUDIT_V1",
        "status": "PASS_C5_MATCHED_ABLATION_SCREEN12_ALL_EVENTS" if phase == "TAIL11"
                 else "PASS_C5_MATCHED_ABLATION_FIRST_ALL_EVENTS",
        "variant_id": variant, "phase_audited": phase, "scene_count_newly_audited": len(scene_rows),
        "scene_id_assertion": scene_id,
        "screen12_complete": phase == "TAIL11", "batch_scene_order": expected_scenes,
        "phase_release_sha256": digest["release"], "natural_os_exit": {"path": str(exit_path),
            "sha256": sha(exit_path), "matlab_os_exit_code": 0},
        "source_files": {key: {"path": str(path), "sha256": digest[key]} for key, path in files.items()},
        "pilot_reports": {v: {"path": str(pilot_dir / PILOT_REPORTS[v][0]),
                              "sha256": PILOT_REPORTS[v][1]} for v in VARIANTS},
        "cross_phase_source_and_snapshot_check": cross_phase,
        "phase_rows": scene_rows,
        "screen12_rows": full_rows if phase == "TAIL11" else None,
        "screen12_summary": summary,
        "plant_calls_in_audit": 0, "TEST_accessed": False, "training_steps": 0, "optimizer_steps": 0,
        "audit_entry_sha256": sha(Path(__file__)),
        "event_audit_sha256": sha(helper.EVENT_AUDIT),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=VARIANTS, required=True)
    parser.add_argument("--phase", choices=("FIRST", "TAIL11"), required=True)
    parser.add_argument("--scene-id", help="assert a scene belongs to this phase; TAIL11 still audits the full ordered batch")
    parser.add_argument("--experiment-root", type=Path,
                        default=ROOT / "experiments/position_c5_matched_ablations_v4_20261023")
    parser.add_argument("--execution-report-root", type=Path,
                        default=ROOT / "reports/paper_continuation_20261023/c5_matched_ablation_execution/v4")
    parser.add_argument("--pilot-audit-dir", type=Path, default=REVIEW_DIR)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = resolve(ROOT, args.output)
    assert not output.exists(), f"refusing to overwrite existing output: {output}"
    result = audit_phase(args.variant, args.phase, args.scene_id,
                         resolve(ROOT, args.experiment_root), resolve(ROOT, args.execution_report_root),
                         resolve(ROOT, args.pilot_audit_dir))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")
    print(json.dumps({"status": result["status"], "variant_id": args.variant, "phase": args.phase,
                      "scene_count": result["scene_count_newly_audited"], "output": str(output),
                      "output_sha256": sha(output), "audit_entry_sha256": result["audit_entry_sha256"]},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
