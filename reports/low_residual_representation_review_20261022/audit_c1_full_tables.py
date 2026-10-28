"""Independent table/provenance audit for the frozen 36-run C1 screen.

This checks the scorer's small CSV/JSON outputs and run_status/run_start files.
It never reads raw_run.mat, launches simulations, or fits parameters.
Run only after all 36 rows and the parent's raw-Q review are complete.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "experiments/position_prior_calibration_c1_20261022_v9"
REPORTS = RUN / "reports"
OUTDIR = Path(__file__).resolve().parent
CONDITIONS = ("B", "ON1", "ONC")
BASELINES = ("ON1", "B")
PHASES = ("0_20", "0_5", "5_20")
AXES = ("x", "y", "z")
TOL = 1e-12
EXPECTED_RELEASE = "7aa072835b0e633f9e40d0e471a17870735d32ddf079eafc61ac6790ea7974d0"
EXPECTED_LOCK = "02668f6268944715e65e6d2cffa52b395417506132212b00e7d273d88df164e5"
EXPECTED_C = 0.2802979648061464


def sha_small(path: Path) -> str:
    assert path.is_file(), f"Missing file: {path}"
    assert path.name.lower() != "raw_run.mat", "This table audit must never hash/read raw_run.mat"
    before = path.stat()
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    after = path.stat()
    assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns), path
    return h.hexdigest()


def load_json(path: Path) -> dict:
    before = path.stat()
    value = json.loads(path.read_text(encoding="utf-8"))
    after = path.stat()
    assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns), path
    return value


def load_csv(path: Path) -> list[dict[str, str]]:
    before = path.stat()
    with path.open(newline="", encoding="utf-8-sig") as f:
        value = list(csv.DictReader(f))
    after = path.stat()
    assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns), path
    return value


def close(a: float, b: float, atol: float = 2e-15, rtol: float = 2e-13) -> bool:
    return math.isfinite(a) and math.isfinite(b) and abs(a - b) <= atol + rtol * abs(b)


def bval(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    assert value in ("True", "False"), f"Not a serialized bool: {value!r}"
    return value == "True"


def fval(row: dict, key: str) -> float:
    value = float(row[key])
    assert math.isfinite(value), f"Non-finite {key}: {row}"
    return value


def fixed_groupings(scenes: list[dict]) -> list[tuple[str, str, list[str]]]:
    scene_ids = [s["scene_id"] for s in scenes]
    groupings = [("task_x_wind_band", f"{task}|{band}", [s["scene_id"] for s in scenes
                  if s["task"] == task and s["band"] == band])
                 for task, band in sorted({(s["task"], s["band"]) for s in scenes})]
    groupings += [("task", task, [s["scene_id"] for s in scenes if s["task"] == task])
                  for task in sorted({s["task"] for s in scenes})]
    groupings += [("wind_band", band, [s["scene_id"] for s in scenes if s["band"] == band])
                  for band in ("W00_W08", "W09_W11", "W12_W14", "W15")]
    groupings.append(("wind_band_merged", "HF_W09_W14",
                      [s["scene_id"] for s in scenes if s["band"] in ("W09_W11", "W12_W14")]))
    groupings.append(("macro", "ALL_12_SCENES", scene_ids))
    assert all(ids for _, _, ids in groupings)
    return groupings


def grouped_pairs(rows: list[dict], groupings: list[tuple[str, str, list[str]]]) -> list[dict]:
    by_key = {(r["scene_id"], r["condition"]): r for r in rows}
    result = []
    for kind, name, scene_ids in groupings:
        for baseline in BASELINES:
            deltas = [fval(by_key[(sid, "ONC")], "Q_0_20_m") -
                      fval(by_key[(sid, baseline)], "Q_0_20_m") for sid in scene_ids]
            result.append({
                "group_type": kind, "group": name, "candidate": "ONC", "baseline": baseline,
                "n_pairs": len(deltas), "mean_delta_Q_0_20_m": math.fsum(deltas) / len(deltas),
                "wins": sum(d < -TOL for d in deltas), "losses": sum(d > TOL for d in deltas),
                "ties": sum(abs(d) <= TOL for d in deltas),
                "improved_at_least_1um": sum(d <= -1e-6 for d in deltas),
                "improved_at_least_10um": sum(d <= -1e-5 for d in deltas),
            })
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--full-36", action="store_true", required=True,
                        help="Explicitly acknowledge this is the final full-screen table audit")
    args = parser.parse_args()
    del args
    output_json = OUTDIR / "C1_FINAL_TABLE_REVIEW.json"
    output_md = OUTDIR / "C1_FINAL_TABLE_REVIEW_ZH.md"
    assert not output_json.exists() and not output_md.exists(), "Refusing to overwrite a prior review"

    release_path = RUN / "C1_RELEASE_v9.json"
    lock_path = RUN / "C1_SOURCE_LOCK_v2.json"
    release, lock = load_json(release_path), load_json(lock_path)
    release_sha, lock_sha = sha_small(release_path), sha_small(lock_path)
    assert release_sha == EXPECTED_RELEASE and lock_sha == EXPECTED_LOCK
    assert release["source_lock_sha256"] == lock_sha
    assert release["c_star"] == EXPECTED_C and lock["calibration"]["c_star"] == EXPECTED_C
    assert release["max_total_sorties"] == 36 and release["prior_completed_sorties"] == 1
    assert release["recovery_probe_new_attempts"] == 2 and release["remaining_continue_attempts"] == 33
    assert release["optimizer_steps"] == 0 and release["test_accessed"] is False

    taskbook = lock["taskbook"]
    assert sha_small(Path(taskbook["path"])) == taskbook["sha256"]
    r2_lock = lock["r2_lock"]
    assert sha_small(Path(r2_lock["path"])) == r2_lock["sha256"]
    r2 = load_json(Path(r2_lock["path"]))
    scenes = lock["shared_scenes"]
    assert len(scenes) == 12 and len({s["scene_id"] for s in scenes}) == 12
    assert [(s["task"], s["band"]) for s in scenes] == [
        (r["task"], r["band"]) for r in load_csv(Path(r2["scene_list"]["path"]))]
    for key in ("scene_list", "scene_payload_identity", "reuse_manifest"):
        assert sha_small(Path(r2[key]["path"])) == r2[key]["sha256"]
    assert r2["model"]["mat_sha256"] == lock["model"]["mat_sha256"]
    assert r2["normalizer"]["npz_file_sha256"] == lock["normalizer"]["npz_file_sha256"]

    probe_path = REPORTS / "probe_c1_v9.json"
    cont_path = REPORTS / "continue_c1_v9.json"
    probe, cont = load_json(probe_path), load_json(cont_path)
    assert probe["status"] == "PROBE_RECOVERED_COMPLETE" and probe["mode"] == "PROBE"
    assert cont["status"] == "CONTINUE_COMPLETE" and cont["mode"] == "CONTINUE"
    assert probe["completed_runs"] == probe["expected_runs"] == 3
    assert cont["completed_runs"] == cont["expected_runs"] == 33
    assert probe["scene_ids"] == [scenes[0]["scene_id"]]
    assert cont["scene_ids"] == [s["scene_id"] for s in scenes[1:]]
    for summary in (probe, cont):
        assert summary["source_lock_sha256"] == lock_sha
        assert summary["release_sha256"] == release_sha
        assert float(summary["c_star"]) == EXPECTED_C
        assert summary["formal_timing_authorized"] is False
        assert summary["formal_timing_qualified"] is False
        assert summary["timing_isolated"] is False
        assert summary["optimizer_steps"] == summary["gpu_jobs"] == 0
        assert summary["test_accessed"] is False and summary["dev_labels_used"] is False
        assert len(summary["run_rows"]) == summary["expected_runs"]

    audit_path = REPORTS / "C1_SCREEN_AUDIT.json"
    audit = load_json(audit_path)
    per_path = REPORTS / "C1_SCREEN_PER_RUN.csv"
    group_path = REPORTS / "C1_SCREEN_GROUP_SUMMARY.csv"
    paired_path = REPORTS / "C1_SCREEN_PAIRED_DELTAS.csv"
    pair_group_path = REPORTS / "C1_SCREEN_PAIRWISE_GROUPS.csv"
    losses_path = REPORTS / "C1_SCREEN_LOSSES.csv"
    report_path = REPORTS / "C1_SCREEN_REPORT_ZH.md"
    rows = load_csv(per_path)
    group_rows = load_csv(group_path)
    paired_rows = load_csv(paired_path)
    pair_group_rows = load_csv(pair_group_path)
    loss_rows = load_csv(losses_path)
    assert audit["status"] == "PASS_FIXED_12_SCENE_SCORE"
    assert audit["source_lock_sha256"] == lock_sha and audit["release_sha256"] == release_sha
    assert audit["probe_summary_sha256"] == sha_small(probe_path)
    assert audit["continue_summary_sha256"] == sha_small(cont_path)
    assert audit["scene_count"] == 12 and audit["run_count"] == 36
    assert audit["conditions"] == list(CONDITIONS)
    assert audit["formal_timing_authorized"] is False and audit["optimizer_steps"] == 0
    assert audit["gpu_jobs"] == 0 and audit["TEST_accessed"] is False
    for name, path in ((per_path.name, per_path), (group_path.name, group_path),
                       (paired_path.name, paired_path), (pair_group_path.name, pair_group_path),
                       (losses_path.name, losses_path), (report_path.name, report_path)):
        assert audit["outputs"][name] == sha_small(path), f"Score output hash mismatch: {name}"

    expected_keys = [(s["scene_id"], c) for s in scenes for c in CONDITIONS]
    assert [(r["scene_id"], r["condition"]) for r in rows] == expected_keys
    assert len(rows) == 36 and len({(r["scene_id"], r["condition"]) for r in rows}) == 36
    assert len({r["raw_path"] for r in rows}) == 36
    scene_meta = {s["scene_id"]: s for s in scenes}
    probe_map = {(r["scene_id"], r["condition"]): r for r in probe["run_rows"]}
    cont_map = {(r["scene_id"], r["condition"]): r for r in cont["run_rows"]}
    summary_map = {**probe_map, **cont_map}
    assert len(summary_map) == 36
    first_id = scenes[0]["scene_id"]
    reuse_path = Path(release["reuse_authorization_path"])
    assert sha_small(reuse_path) == release["reuse_authorization_sha256"]
    assert sha_small(Path(release["prior_release_path"])) == release["prior_release_sha256"]
    reuse = load_json(reuse_path)
    assert reuse["status"] == "APPROVED_REUSE_EXACT_COMPLETED_B_NO_RERUN"
    assert reuse["scene_id"] == first_id and reuse["condition"] == "B"
    assert reuse["original_release_v8_sha256"] == release["prior_release_sha256"]
    reuse_files = {entry["name"]: entry for entry in reuse["files"]}
    assert set(reuse_files) == {"attempt_started.marker", "raw_run.mat", "run_start.mat", "run_status.json"}

    metric_names = [f"Q_{p}_m" for p in PHASES]
    metric_names += [f"rmse_{a}_{p}_m" for p in PHASES for a in AXES]
    metric_names += ["peak_m", "p95_m", "motor_saturated_fraction", "generalized_clipped_fraction",
                     "episode_runtime_seconds", "attempt_execution_and_raw_persistence_seconds",
                     "controller_mean_s", "controller_p95_s", "controller_max_s"]
    input_stats = {}
    for row in rows:
        sid, condition = row["scene_id"], row["condition"]
        reused = sid == first_id and condition == "B"
        assert bval(row["reused_prior_run"]) == reused
        assert row["actual_run_release"] == (release["prior_release_sha256"] if reused else release_sha)
        assert row["source_lock_sha256"] == lock_sha
        assert row["status"] == "STABLE" and bval(row["safe_complete_finite"])
        assert int(row["completed_transition"]) == 20000
        assert not bval(row["timing_isolated"]) and not bval(row["formal_timing_qualified"])
        assert "CONTAMINATED" in row["timing_mark"]
        assert abs(float(row["c_star"]) - EXPECTED_C) < 1e-15
        for metric in metric_names:
            fval(row, metric)
        meta = scene_meta[sid]
        if reused:
            attempt = Path(release["reused_b_runs_root"]) / sid / "B" / "attempt_01"
        else:
            attempt = RUN / "runs_v9" / sid / condition / "attempt_01"
        raw = attempt / "raw_run.mat"
        status_path = attempt / "run_status.json"
        start_path = attempt / "run_start.mat"
        marker_path = attempt / "attempt_started.marker"
        assert Path(row["raw_path"]).resolve() == raw.resolve()
        assert sorted(p.name for p in attempt.iterdir() if p.is_file()) == [
            "attempt_started.marker", "raw_run.mat", "run_start.mat", "run_status.json"]
        raw_before = raw.stat()
        status_sha, start_sha = sha_small(status_path), sha_small(start_path)
        assert marker_path.is_file()
        assert status_sha == row["run_status_sha256"] and start_sha == row["run_start_sha256"]
        status = load_json(status_path)
        assert status["status"] == "STABLE" and status["scene_id"] == sid
        assert status["condition"] == condition and status["completed_transition"] == 20000
        assert status["raw_sha256"] == row["raw_sha256"]
        assert status["run_start_sha256"] == row["run_start_sha256"]
        assert status["source_lock_sha256"] == lock_sha
        assert status["release_sha256"] == row["actual_run_release"]
        assert status["model_mat_sha256"] == lock["model"]["mat_sha256"]
        assert status["normalizer_npz_sha256"] == lock["normalizer"]["npz_file_sha256"]
        assert status["scene_source_raw_sha256"] == meta["b_raw_sha256"]
        assert status["preflight_sha256"] == row["preflight_sha256"]
        assert status["timing_isolated"] is False and status["formal_timing_qualified"] is False
        assert status["timing_mark"] == row["timing_mark"]
        assert close(float(status["c_star"]), EXPECTED_C, atol=1e-15, rtol=0)
        assert status["output_before_update_validation"] == ("NOT_APPLICABLE_B" if condition == "B" else "PASS")
        assert int(float(row["attempt_output_bytes"])) == sum(p.stat().st_size for p in attempt.iterdir() if p.is_file())
        assert raw.stat().st_size > 0 and row["raw_sha256"]
        assert raw.stat().st_size < 150_000_000, "Unexpectedly large raw artifact"
        assert (raw_before.st_size, raw_before.st_mtime_ns) == (raw.stat().st_size, raw.stat().st_mtime_ns)
        summary_row = summary_map[(sid, condition)]
        for key in ("scene_id", "condition", "status", "raw_sha256", "run_status_sha256", "run_start_sha256",
                    "source_lock_sha256", "actual_run_release", "preflight_sha256", "timing_mark"):
            assert row[key] == summary_row[key], (sid, condition, key)
        assert summary_row["scene_source_raw_sha256"] == meta["b_raw_sha256"]
        for key in ("reused_prior_run", "timing_isolated", "formal_timing_qualified"):
            assert bval(row[key]) is summary_row[key], (sid, condition, key)
        assert close(fval(row, "attempt_output_bytes"), float(summary_row["attempt_output_bytes"]))
        assert close(fval(row, "episode_runtime_seconds"), float(summary_row["episode_runtime_seconds"]))
        assert close(fval(row, "attempt_execution_and_raw_persistence_seconds"),
                     float(summary_row["attempt_execution_and_raw_persistence_seconds"]))
        input_stats[str(status_path)] = {"sha256": status_sha, "bytes": status_path.stat().st_size}
        input_stats[str(start_path)] = {"sha256": start_sha, "bytes": start_path.stat().st_size}

    # Explicitly bind the single historical B reuse to the reviewed v8 authorization.
    first_b = next(r for r in rows if r["scene_id"] == first_id and r["condition"] == "B")
    attempt_b = Path(first_b["raw_path"]).parent
    for name, path in (("attempt_started.marker", attempt_b / "attempt_started.marker"),
                       ("run_start.mat", attempt_b / "run_start.mat"),
                       ("run_status.json", attempt_b / "run_status.json")):
        assert sha_small(path) == reuse_files[name]["sha256"]
    assert first_b["raw_sha256"] == reuse_files["raw_run.mat"]["sha256"]
    assert first_b["run_start_sha256"] == reuse_files["run_start.mat"]["sha256"]
    assert first_b["run_status_sha256"] == reuse_files["run_status.json"]["sha256"]

    groupings = fixed_groupings(scenes)
    run_map = {(r["scene_id"], r["condition"]): r for r in rows}
    expected_group_rows = {}
    for kind, name, scene_ids in groupings:
        for condition in CONDITIONS:
            cell = [run_map[(sid, condition)] for sid in scene_ids]
            expected_group_rows[kind, name, condition] = cell
    actual_groups = {(r["group_type"], r["group"], r["condition"]): r for r in group_rows}
    assert len(actual_groups) == len(group_rows) == len(expected_group_rows)
    for key, cell in expected_group_rows.items():
        group = actual_groups[key]
        assert int(group["n_runs"]) == len(cell)
        for metric in metric_names:
            want = math.fsum(fval(r, metric) for r in cell) / len(cell)
            assert close(float(group[f"mean_{metric}"]), want), (key, metric, group[f"mean_{metric}"], want)
        for metric in ("peak_m", "motor_saturated_fraction", "generalized_clipped_fraction"):
            want = max(fval(r, metric) for r in cell)
            assert close(float(group[f"max_{metric}"]), want)
        assert bval(group["all_timing_isolated"]) is False
        assert bval(group["all_formal_timing_qualified"]) is False

    # Recompute per-scene paired deltas, outcome counts, and the complete loss set.
    expected_paired = []
    for scene in scenes:
        for baseline in BASELINES:
            a, b = run_map[(scene["scene_id"], "ONC")], run_map[(scene["scene_id"], baseline)]
            delta = fval(a, "Q_0_20_m") - fval(b, "Q_0_20_m")
            outcome = "WIN" if delta < -TOL else "LOSS" if delta > TOL else "TIE"
            item = (scene["scene_id"], "ONC", baseline)
            expected_paired.append((item, delta, outcome))
    assert len(paired_rows) == 24
    actual_paired = {(r["scene_id"], r["candidate"], r["baseline"]): r for r in paired_rows}
    assert set(actual_paired) == {x[0] for x in expected_paired}
    for key, delta, outcome in expected_paired:
        row = actual_paired[key]
        assert close(float(row["delta_Q_0_20_m"]), delta)
        assert row["outcome_tol_1e-12m"] == outcome
        for phase in PHASES:
            a = run_map[(key[0], key[1])]
            b = run_map[(key[0], key[2])]
            qd = fval(a, f"Q_{phase}_m") - fval(b, f"Q_{phase}_m")
            assert close(float(row[f"delta_Q_{phase}_m"]), qd)
            for axis in AXES:
                axis_key = f"rmse_{axis}_{phase}_m"
                assert close(float(row[f"delta_{axis_key}"]), fval(a, axis_key) - fval(b, axis_key))
    losses = [r for r in paired_rows if r["outcome_tol_1e-12m"] == "LOSS"]
    assert len(loss_rows) == len(losses)
    loss_keys = {(r["scene_id"], r["candidate"], r["baseline"]) for r in losses}
    assert loss_keys == {(r["scene_id"], r["candidate"], r["baseline"]) for r in loss_rows}
    for loss in loss_rows:
        original = actual_paired[(loss["scene_id"], loss["candidate"], loss["baseline"])]
        assert original["outcome_tol_1e-12m"] == "LOSS"
        assert close(float(loss["delta_Q_0_20_m"]), float(original["delta_Q_0_20_m"]))

    # Verify every scorer group-pair aggregate, including each task×band and each HF sub-band.
    expected_pair_groups = grouped_pairs(rows, groupings)
    actual_pair_groups = {(r["group_type"], r["group"], r["candidate"], r["baseline"]): r
                          for r in pair_group_rows}
    assert len(actual_pair_groups) == len(pair_group_rows) == len(expected_pair_groups)
    for want in expected_pair_groups:
        key = (want["group_type"], want["group"], want["candidate"], want["baseline"])
        got = actual_pair_groups[key]
        for metric in ("n_pairs", "wins", "losses", "ties", "improved_at_least_1um", "improved_at_least_10um"):
            assert int(got[metric]) == want[metric], (key, metric, got[metric], want[metric])
        assert close(float(got["mean_delta_Q_0_20_m"]), want["mean_delta_Q_0_20_m"])

    group_q = {}
    for kind, name, ids in groupings:
        group_q[kind, name] = {}
        for condition in CONDITIONS:
            values = [fval(run_map[(sid, condition)], "Q_0_20_m") for sid in ids]
            group_q[kind, name][condition] = math.fsum(values) / len(values)
    gate_values = {
        "W15_mean_ONC_le_B": group_q["wind_band", "W15"]["ONC"] <= group_q["wind_band", "W15"]["B"],
        "W15_mean_ONC_le_ON1": group_q["wind_band", "W15"]["ONC"] <= group_q["wind_band", "W15"]["ON1"],
        "HF_W09_W14_mean_ONC_le_B": group_q["wind_band_merged", "HF_W09_W14"]["ONC"] <= group_q["wind_band_merged", "HF_W09_W14"]["B"],
        "HF_W09_W14_mean_ONC_le_ON1": group_q["wind_band_merged", "HF_W09_W14"]["ONC"] <= group_q["wind_band_merged", "HF_W09_W14"]["ON1"],
        "ALL12_mean_ONC_le_ON1": group_q["macro", "ALL_12_SCENES"]["ONC"] <= group_q["macro", "ALL_12_SCENES"]["ON1"],
    }
    deltas = {
        f"{kind}:{name}:ONC-{baseline}": group_q[kind, name]["ONC"] - group_q[kind, name][baseline]
        for kind, name in (("wind_band", "W15"), ("wind_band_merged", "HF_W09_W14"), ("macro", "ALL_12_SCENES"))
        for baseline in BASELINES
    }
    all_losses = [{"scene_id": r["scene_id"], "task": r["task"], "wind_band": r["wind_band"],
                   "baseline": r["baseline"], "delta_Q_0_20_m": float(r["delta_Q_0_20_m"])}
                  for r in losses]
    all_losses.sort(key=lambda x: (x["task"], x["wind_band"], x["scene_id"], x["baseline"]))

    result = {
        "status": "PASS_TABLE_AND_PROVENANCE_REVIEW" if all(gate_values.values()) else "STOP_FROZEN_PERFORMANCE_GATE_FAILED",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "release_sha256": release_sha, "source_lock_sha256": lock_sha,
        "calibration_c_star": EXPECTED_C,
        "rows": {"scenes": 12, "runs": len(rows), "conditions": list(CONDITIONS),
                 "v8_reused_runs": 1, "v9_new_runs": 35, "reuse_scene": first_id,
                 "reuse_condition": "B", "probe_rows": len(probe["run_rows"]),
                 "continue_rows": len(cont["run_rows"])},
        "checks": {"scene_condition_order": True, "score_csv_output_hashes": True,
                   "summary_to_table_identity": True, "status_start_hashes": True,
                   "raw_files_opened_or_hashed_by_this_reviewer": False,
                   "all_rows_stable_complete_transition_finite": True,
                   "timing_qualified": False, "timing_interference_preserved": True,
                   "group_means_and_group_pair_tables_recomputed": True,
                   "per_run_pairwise_and_losses_recomputed": True},
        "strict_frozen_performance_gates": gate_values,
        "exact_group_mean_deltas_m": deltas,
        "mean_Q_m": {f"{kind}:{name}": vals for (kind, name), vals in group_q.items()},
        "all_pairwise_losses": all_losses,
        "limitations": [
            "此复核独立重算CSV分组、配对和门；未读取/重哈希36份raw_run.mat，也未独立重算物理Q。原始Q与安全完整性依赖主审原始记录复核及冻结评分器证据。",
            "严格组均值门按冻结任务书的ONC <= comparator判定；1e-12 m只用于逐场WIN/LOSS/TIE，不把容差用于放宽组门。",
            "C1是固定VAL12开发筛查；PASS不构成独立TEST、普遍因果保证或论文资格。所有计时均非正式隔离耗时。",
        ],
        "input_sha256": {
            "release": release_sha, "source_lock": lock_sha,
            "probe_summary": sha_small(probe_path), "continue_summary": sha_small(cont_path),
            "screen_audit": sha_small(audit_path), "per_run_csv": sha_small(per_path),
            "group_csv": sha_small(group_path), "paired_csv": sha_small(paired_path),
            "pairwise_group_csv": sha_small(pair_group_path), "losses_csv": sha_small(losses_path),
            "score_report": sha_small(report_path), "review_script": sha_small(Path(__file__)),
        },
        "run_status_and_start_sha256": input_stats,
    }
    output_json.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    lines = [
        "# C1 固定 12 场独立表级复核", "",
        "本复核只读冻结CSV/JSON、run_status.json和run_start.mat；不打开或重哈希raw_run.mat，不启动仿真。",
        "组均值和逐场配对从per-run表独立重算，并核对worker的全部task×wind-band、风带、HF合并及宏平均表。", "",
        f"- 结果：**{result['status']}**。场景12、条件B/ON1/ONC共36条；复用v8首场B一条，v9新运行35条。",
        f"- 源锁SHA256：`{lock_sha}`；v9 release SHA256：`{release_sha}`；固定c*={EXPECTED_C:.15g}。",
        f"- 行级输场比较：ONC−ON1 {sum(x['baseline']=='ON1' for x in all_losses)}条，ONC−B {sum(x['baseline']=='B' for x in all_losses)}条；完整列表见JSON。", "",
        "## 固定组门", "",
        "组门采用冻结规则的严格未舍入均值 `ONC <= 对照`；1e-12 m 仅用于逐场胜负分类。", "",
    ]
    gate_to_delta = {
        "W15_mean_ONC_le_B": "wind_band:W15:ONC-B",
        "W15_mean_ONC_le_ON1": "wind_band:W15:ONC-ON1",
        "HF_W09_W14_mean_ONC_le_B": "wind_band_merged:HF_W09_W14:ONC-B",
        "HF_W09_W14_mean_ONC_le_ON1": "wind_band_merged:HF_W09_W14:ONC-ON1",
        "ALL12_mean_ONC_le_ON1": "macro:ALL_12_SCENES:ONC-ON1",
    }
    for name, passed in gate_values.items():
        delta_key = gate_to_delta[name]
        lines.append(f"- {'PASS' if passed else 'FAIL'} `{name}`；ΔQ={deltas[delta_key]:.17g} m。")
    lines += ["", "## 结论边界", "",
              "该脚本独立核对表格汇总和来源/运行小型元数据，但没有第二次读取原始轨迹计算Q。原始数值、物理安全门仍以主审raw复核为依据；计时保留桌面负载干扰标记，不能作正式效率结论。",
              "筛查通过也只允许后续另行审核，不自动授权72场、第二个c或TEST。", ""]
    output_md.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": result["status"], "gates": gate_values,
                      "outputs": [str(output_json), str(output_md)]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
