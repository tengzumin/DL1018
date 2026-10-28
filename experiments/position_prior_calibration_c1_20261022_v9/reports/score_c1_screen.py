"""Read-only primary scoring/reporting for the fixed 12-scene C1 screen.

The existing primary raw scorer is reused for its pure score()/fingerprint() helpers;
this is not a second numerical implementation.  The script never runs Plant or fits.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parents[1]
REPORTS = HERE / "reports"
CONDITIONS = ("B", "ON1", "ONC")
PAIRS = (("ONC", "ON1"), ("ONC", "B"))
TOL = 1e-12
AXES = ("x", "y", "z")
PHASES = ("0_20", "0_5", "5_20")


def sha256(path: Path) -> str:
    before = path.stat()
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    after = path.stat()
    assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns), path
    return h.hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_file(path: Path, expected: str) -> None:
    assert path.is_file() and sha256(path) == expected.lower(), f"SHA mismatch: {path}"


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def primary_scorer():
    path = ROOT / "reports/low_residual_parent_review_20261022/independent_c1_score.py"
    spec = importlib.util.spec_from_file_location("c1_primary_score_helpers", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def frozen_inputs() -> tuple[dict, dict, dict, dict]:
    lock_path = HERE / "C1_SOURCE_LOCK_v2.json"
    release_path = HERE / "C1_RELEASE_v9.json"
    lock, release = read_json(lock_path), read_json(release_path)
    verify_file(lock_path, release["source_lock_sha256"])
    assert sha256(HERE / "run_c1_screen.m") == release["runner_sha256"]
    verify_file(Path(release["prior_rescore_path"]), release["prior_rescore_sha256"])
    r2_path = Path(lock["r2_lock"]["path"])
    verify_file(r2_path, lock["r2_lock"]["sha256"])
    r2 = read_json(r2_path)
    for item in (r2["scene_list"], r2["scene_payload_identity"], r2["reuse_manifest"]):
        verify_file(Path(item["path"]), item["sha256"])
    scene_list = csv_rows(Path(r2["scene_list"]["path"]))
    payload = csv_rows(Path(r2["scene_payload_identity"]["path"]))
    reuse = csv_rows(Path(r2["reuse_manifest"]["path"]))
    scenes = lock["shared_scenes"]
    assert len(scenes) == len(scene_list) == len(payload) == 12
    assert [s["scene_id"] for s in scenes] == [r["scene_id"] for r in scene_list]
    assert [s["scene_id"] for s in scenes] == [r["scene_id"] for r in payload]
    assert [(s["task"], s["band"]) for s in scenes] == [(r["task"], r["band"]) for r in scene_list]
    assert all(r["status"] == "IDENTICAL" and r["physical_field_count"] == "14" and
               r["time_samples"] == "20001" and float(r["max_abs_physical_scene_diff"]) == 0
               for r in payload)
    assert len(reuse) == 24 and all(r["split"] == "VAL" for r in reuse)
    assert Counter(r["role"] for r in reuse) == {"B_BASELINE": 12, "ON_CANDIDATE": 12}
    assert {r["scene_id"] for r in reuse} == {s["scene_id"] for s in scenes}
    calibration = read_json(Path(lock["calibration"]["result_path"]))
    verify_file(Path(lock["calibration"]["result_path"]), lock["calibration"]["result_sha256"])
    assert calibration["status"] == "PASS_C1_TRAIN_CALIBRATION_GATE"
    assert abs(float(calibration["solver"]["c_star"]) - float(lock["calibration"]["c_star"])) <= 1e-15
    return lock, release, r2


def load_summaries(full: bool, lock: dict, release: dict) -> tuple[list[dict], dict]:
    probe_path = REPORTS / "probe_c1_v9.json"
    probe = read_json(probe_path)
    assert probe["status"] == "PROBE_RECOVERED_COMPLETE" and probe["mode"] == "PROBE"
    assert probe["source_lock_sha256"] == release["source_lock_sha256"]
    assert probe["release_sha256"] == sha256(HERE / "C1_RELEASE_v9.json")
    assert abs(float(probe["c_star"]) - float(lock["calibration"]["c_star"])) <= 1e-15
    scenes = lock["shared_scenes"]
    assert probe["scene_ids"] == [scenes[0]["scene_id"]]
    assert probe["completed_runs"] == probe["expected_runs"] == 3
    assert probe["reused_prior_runs"] == 1 and probe["new_attempt_runs"] == 2
    summaries = [probe]
    if full:
        cont_path = REPORTS / "continue_c1_v9.json"
        approval_path = REPORTS / "C1_CONTINUE_APPROVAL_v9.json"
        pf_path = REPORTS / "preflight_c1_continue_v9.json"
        assert cont_path.is_file() and approval_path.is_file() and pf_path.is_file()
        cont, approval, pf = read_json(cont_path), read_json(approval_path), read_json(pf_path)
        assert cont["status"] == "CONTINUE_COMPLETE" and cont["mode"] == "CONTINUE"
        assert cont["source_lock_sha256"] == release["source_lock_sha256"]
        assert cont["release_sha256"] == sha256(HERE / "C1_RELEASE_v9.json")
        assert cont["scene_ids"] == [s["scene_id"] for s in scenes[1:]]
        assert cont["completed_runs"] == cont["expected_runs"] == 33
        assert cont["new_attempt_runs"] == 33
        assert approval["status"] == "APPROVED_CONTINUE" and approval["mode"] == "CONTINUE"
        assert approval["source_lock_sha256"] == release["source_lock_sha256"]
        assert approval["release_sha256"] == sha256(HERE / "C1_RELEASE_v9.json")
        assert approval["probe_summary_sha256"] == sha256(probe_path)
        assert pf["status"] == "PASS" and pf["mode"] == "CONTINUE"
        assert pf["release_sha256"] == sha256(HERE / "C1_RELEASE_v9.json")
        verify_file(pf_path, cont["preflight_sha256"])
        summaries.append(cont)
    assert all(s["formal_timing_authorized"] is False and s["optimizer_steps"] == 0 and
               s["gpu_jobs"] == 0 and s["test_accessed"] is False and
               s["dev_labels_used"] is False for s in summaries)
    rows = [dict(row, summary_mode=s["mode"], summary_preflight_sha256=s["preflight_sha256"])
            for s in summaries for row in s["run_rows"]]
    expected = [(s["scene_id"], c) for s in scenes[:1] for c in CONDITIONS]
    if full:
        expected += [(s["scene_id"], c) for s in scenes[1:] for c in CONDITIONS]
    keys = [(r["scene_id"], r["condition"]) for r in rows]
    assert keys == expected, "summary rows must match the exact fixed scene×condition order"
    assert all(r["status"] == "STABLE" for r in rows)
    return rows, {"probe": probe, "continue": summaries[1] if full else None}


def verify_reuse_b(row: dict, release: dict) -> Path:
    auth_path = Path(release["reuse_authorization_path"])
    verify_file(auth_path, release["reuse_authorization_sha256"])
    auth = read_json(auth_path)
    rescore = read_json(Path(release["prior_rescore_path"]))
    assert auth["status"] == "APPROVED_REUSE_EXACT_COMPLETED_B_NO_RERUN"
    assert auth["scene_id"] == row["scene_id"] and auth["condition"] == "B"
    assert auth["original_release_v8_sha256"] == release["prior_release_sha256"]
    files = {f["name"]: f for f in auth["files"]}
    assert set(files) == {"attempt_started.marker", "raw_run.mat", "run_start.mat", "run_status.json"}
    assert row["reused_prior_run"] is True and row["actual_run_release"] == release["prior_release_sha256"]
    assert row["raw_sha256"] == files["raw_run.mat"]["sha256"]
    assert row["run_start_sha256"] == files["run_start.mat"]["sha256"]
    assert row["run_status_sha256"] == files["run_status.json"]["sha256"]
    raw = Path(files["raw_run.mat"]["path"])
    assert raw == Path(release["reused_b_runs_root"]) / row["scene_id"] / "B" / "attempt_01" / "raw_run.mat"
    for f in files.values():
        verify_file(Path(f["path"]), f["sha256"])
    assert rescore["status"] == "PASS_PRIMARY_NUMERICAL_RAW_RESCORE" and len(rescore["rows"]) == 1
    rescore_row = rescore["rows"][0]
    assert rescore_row["raw_sha256"] == row["raw_sha256"] and rescore_row["scene_id"] == row["scene_id"]
    assert rescore_row["safe_complete_finite"] is True
    assert abs(float(rescore_row["Q_0_20_m"]) - float(auth["independent_Q_m"])) <= 1e-15
    return raw


def score_rows(rows: list[dict], lock: dict, release: dict, r2: dict) -> list[dict]:
    module = primary_scorer()
    scene_meta = {s["scene_id"]: s for s in lock["shared_scenes"]}
    out, references = [], {}
    b_auth = read_json(Path(release["reuse_authorization_path"]))
    expected_release = sha256(HERE / "C1_RELEASE_v9.json")
    for source in rows:
        row = dict(source)
        meta = scene_meta[row["scene_id"]]
        reused = row["scene_id"] == lock["shared_scenes"][0]["scene_id"] and row["condition"] == "B"
        if reused:
            raw = verify_reuse_b(row, release)
            expected_pf = release["prior_preflight_sha256"]
        else:
            raw = HERE / "runs_v9" / row["scene_id"] / row["condition"] / "attempt_01" / "raw_run.mat"
            expected_pf = REPORTS / ("preflight_c1_probe_v9.json" if row["summary_mode"] == "PROBE"
                                     else "preflight_c1_continue_v9.json")
            expected_pf_sha = sha256(expected_pf)
            assert row["preflight_sha256"] == expected_pf_sha
            assert row["actual_run_release"] == expected_release and row["reused_prior_run"] is False
        assert row["summary_preflight_sha256"] == (sha256(REPORTS / "preflight_c1_probe_v9.json")
                    if row["summary_mode"] == "PROBE" else sha256(REPORTS / "preflight_c1_continue_v9.json"))
        assert row["preflight_sha256"] == expected_pf if reused else True
        attempt = raw.parent
        assert sorted(p.name for p in attempt.iterdir() if p.is_file()) == [
            "attempt_started.marker", "raw_run.mat", "run_start.mat", "run_status.json"]
        status_path = attempt / "run_status.json"
        start_path = attempt / "run_start.mat"
        marker_path = attempt / "attempt_started.marker"
        verify_file(raw, row["raw_sha256"])
        verify_file(status_path, row["run_status_sha256"])
        verify_file(start_path, row["run_start_sha256"])
        assert marker_path.is_file()
        status = read_json(status_path)
        assert status["status"] == "STABLE" and status["condition"] == row["condition"]
        assert status["scene_id"] == row["scene_id"] and status["completed_transition"] == 20000
        assert status["source_lock_sha256"] == release["source_lock_sha256"]
        assert status["scene_source_raw_sha256"] == meta["b_raw_sha256"]
        assert status["timing_isolated"] == row["timing_isolated"]
        assert status["formal_timing_qualified"] == row["formal_timing_qualified"]
        assert status["preflight_sha256"] == row["preflight_sha256"]
        assert abs(float(status["c_star"]) - float(lock["calibration"]["c_star"])) <= 1e-15
        assert status["output_before_update_validation"] == ("NOT_APPLICABLE_B" if row["condition"] == "B" else "PASS")
        assert sum(p.stat().st_size for p in attempt.iterdir() if p.is_file()) == int(row["attempt_output_bytes"])
        if reused:
            assert status["release_sha256"] == release["prior_release_sha256"]
            assert status["model_mat_sha256"] == b_auth["model_mat_sha256"]
            assert status["normalizer_npz_sha256"] == b_auth["normalizer_npz_sha256"]
        else:
            assert status["release_sha256"] == expected_release
            assert status["model_mat_sha256"] == r2["model"]["mat_sha256"]
            assert status["normalizer_npz_sha256"] == r2["normalizer"]["npz_file_sha256"]
        result, ref = module.score(raw)
        assert result["raw_sha256"] == row["raw_sha256"] and result["scene_id"] == row["scene_id"]
        if row["scene_id"] in references:
            assert (ref == references[row["scene_id"]]).all(), f"Reference mismatch: {row['scene_id']}"
        else:
            references[row["scene_id"]] = ref
        item = {"scene_id": row["scene_id"], "task": meta["task"], "wind_band": meta["band"],
                "condition": row["condition"], "role": row["condition"], "summary_mode": row["summary_mode"],
                "reused_prior_run": reused, "actual_run_release": row["actual_run_release"],
                "source_lock_sha256": row["source_lock_sha256"], "preflight_sha256": row["preflight_sha256"],
                "raw_path": str(raw), "raw_sha256": result["raw_sha256"],
                "run_start_sha256": row["run_start_sha256"], "run_status_sha256": row["run_status_sha256"],
                "status": "STABLE", "safe_complete_finite": result["safe_complete_finite"],
                "completed_transition": 20000, "c_star": float(lock["calibration"]["c_star"]),
                "timing_isolated": bool(row["timing_isolated"]),
                "formal_timing_qualified": bool(row["formal_timing_qualified"]),
                "timing_mark": row["timing_mark"],
                "episode_runtime_seconds": float(row["episode_runtime_seconds"]),
                "attempt_execution_and_raw_persistence_seconds": float(row["attempt_execution_and_raw_persistence_seconds"]),
                "attempt_output_bytes": int(row["attempt_output_bytes"]),
                "motor_saturated_fraction": result["motor_saturated_fraction"],
                "generalized_clipped_fraction": result["generalized_clipped_fraction"],
                "peak_m": result["peak_m"], "p95_m": result["p95_m"],
                "controller_mean_s": result["controller_mean_s"],
                "controller_p95_s": result["controller_p95_s"], "controller_max_s": result["controller_max_s"]}
        for phase in PHASES:
            item[f"Q_{phase}_m"] = result[f"Q_{phase}_m"]
            for axis, value in zip(AXES, result[f"axis_rmse_{phase}_m"]):
                item[f"rmse_{axis}_{phase}_m"] = float(value)
        out.append(item)
    return out


def grouping(rows: list[dict]) -> list[tuple[str, str, list[dict]]]:
    groups = [("task_x_wind_band", f"{t}|{b}", [r for r in rows if r["task"] == t and r["wind_band"] == b])
              for t, b in sorted({(r["task"], r["wind_band"]) for r in rows})]
    groups += [("task", t, [r for r in rows if r["task"] == t]) for t in sorted({r["task"] for r in rows})]
    groups += [("wind_band", b, [r for r in rows if r["wind_band"] == b]) for b in
               ("W00_W08", "W09_W11", "W12_W14", "W15")]
    groups.append(("wind_band_merged", "HF_W09_W14",
                   [r for r in rows if r["wind_band"] in ("W09_W11", "W12_W14")]))
    groups.append(("macro", "ALL_12_SCENES", rows))
    return groups


def aggregate_rows(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    group_rows, pair_rows = [], []
    for group_type, group_name, subset in grouping(rows):
        for condition in CONDITIONS:
            cond = [r for r in subset if r["condition"] == condition]
            if not cond:
                continue
            row = {"group_type": group_type, "group": group_name, "condition": condition,
                   "n_runs": len(cond), "Q_rule": "arithmetic mean of per-run RMSE; no pooled square-root"}
            metrics = [f"Q_{p}_m" for p in PHASES] + ["peak_m", "p95_m", "motor_saturated_fraction",
                      "generalized_clipped_fraction", "episode_runtime_seconds",
                      "attempt_execution_and_raw_persistence_seconds", "controller_mean_s",
                      "controller_p95_s", "controller_max_s"]
            metrics += [f"rmse_{a}_{p}_m" for p in PHASES for a in AXES]
            for metric in metrics:
                values = [float(r[metric]) for r in cond]
                row[f"mean_{metric}"] = math.fsum(values) / len(values)
                if metric in ("peak_m", "motor_saturated_fraction", "generalized_clipped_fraction"):
                    row[f"max_{metric}"] = max(values)
            row["all_timing_isolated"] = all(r["timing_isolated"] for r in cond)
            row["all_formal_timing_qualified"] = all(r["formal_timing_qualified"] for r in cond)
            group_rows.append(row)
        by_scene = {scene_id: {r["condition"]: r for r in subset if r["scene_id"] == scene_id} for scene_id in
                    sorted({r["scene_id"] for r in subset})}
        for pair_name, (candidate, baseline) in enumerate(PAIRS):
            del pair_name
            comparisons = []
            for scene_id, values in by_scene.items():
                if candidate not in values or baseline not in values:
                    continue
                a, b = values[candidate], values[baseline]
                d = float(a["Q_0_20_m"] - b["Q_0_20_m"])
                outcome = "WIN" if d < -TOL else "LOSS" if d > TOL else "TIE"
                delta = {"group_type": group_type, "group": group_name, "scene_id": scene_id,
                         "task": a["task"], "wind_band": a["wind_band"], "candidate": candidate,
                         "baseline": baseline, "delta_Q_0_20_m": d, "outcome_tol_1e-12m": outcome,
                         "improved_at_least_1um": d <= -1e-6, "improved_at_least_10um": d <= -1e-5}
                for phase in PHASES:
                    delta[f"delta_Q_{phase}_m"] = a[f"Q_{phase}_m"] - b[f"Q_{phase}_m"]
                    for axis in AXES:
                        delta[f"delta_rmse_{axis}_{phase}_m"] = a[f"rmse_{axis}_{phase}_m"] - b[f"rmse_{axis}_{phase}_m"]
                comparisons.append(delta)
            if comparisons:
                pair_rows.append({"group_type": group_type, "group": group_name,
                    "candidate": candidate, "baseline": baseline, "n_pairs": len(comparisons),
                    "mean_delta_Q_0_20_m": math.fsum(x["delta_Q_0_20_m"] for x in comparisons)/len(comparisons),
                    "wins": sum(x["outcome_tol_1e-12m"] == "WIN" for x in comparisons),
                    "losses": sum(x["outcome_tol_1e-12m"] == "LOSS" for x in comparisons),
                    "ties": sum(x["outcome_tol_1e-12m"] == "TIE" for x in comparisons),
                    "improved_at_least_1um": sum(x["improved_at_least_1um"] for x in comparisons),
                    "improved_at_least_10um": sum(x["improved_at_least_10um"] for x in comparisons),
                    "sensitivity_is_descriptive_only": True})
    return group_rows, pair_rows


def write_csv(path: Path, rows: list[dict], empty_fieldnames: list[str] | None = None) -> None:
    assert not path.exists(), f"Refusing overwrite output: {path}"
    assert rows or empty_fieldnames, f"Cannot write an empty CSV without a schema: {path}"
    keys = list(rows[0]) if rows else list(empty_fieldnames)
    with path.open("x", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def final_report(rows: list[dict], pairs: list[dict], losses: list[dict], inputs: dict) -> str:
    lines = ["# C1 固定 12 场筛查结果", "",
        "本报告按冻结 12 场 × B/ON1/ONC 共 36 条运行评分；B 的首场只读复用 v8，其他行来自 v9。",
        "Q 为每场 0–20 s 三维 RMSE；组 Q 是逐场 RMSE 的算术平均，不是 pooled SSE 开方。",
        "胜负容差为 1e-12 m；1 μm/10 μm 改善计数仅作描述敏感性。固定 VAL12 分数用于开发筛查，不是 TEST。",
        "本 scorer 复用既有 primary raw score helper，不代表第二套独立数值实现；主审另已独立复核 probe 原始 Q。",
        "所有计时受 preflight 桌面负载影响，正式计时未获授权。", "",
        f"- c* = {inputs['c_star']:.15g}; source lock SHA256 = `{inputs['source_lock_sha256']}`",
        f"- runs = {len(rows)}；finite/stable = {sum(r['safe_complete_finite'] and r['status']=='STABLE' for r in rows)}/{len(rows)}；TEST=0；optimizer=0；GPU jobs=0。", "",
        "## 宏平均与配对计数", "", "| 配对 | 平均 ΔQ (m) | 胜 | 负 | 平 | ≥1 μm改善 | ≥10 μm改善 |", "|---|---:|---:|---:|---:|---:|---:|"]
    for p in pairs:
        if p["group_type"] == "macro":
            lines.append(f"| ONC−{p['baseline']} | {p['mean_delta_Q_0_20_m']:.9g} | {p['wins']} | {p['losses']} | {p['ties']} | {p['improved_at_least_1um']} | {p['improved_at_least_10um']} |")
    lines += ["", f"全部输场记录在 `C1_SCREEN_LOSSES.csv`（共 {len(losses)} 条比较）；逐场、任务/风带组、早晚段、轴、峰值及饱和指标见 CSV。", "",
        "## 重点分组", "", "| 分组 | 配对 | 平均 ΔQ (m) | 胜 | 负 | 平 | ≥1 μm改善 | ≥10 μm改善 |", "|---|---|---:|---:|---:|---:|---:|---:|"]
    focus = [p for p in pairs if p["group_type"] == "macro" or
             (p["group_type"] == "wind_band" and p["group"] == "W15") or
             (p["group_type"] == "wind_band_merged" and p["group"] == "HF_W09_W14")]
    names = {"macro": "ALL12", "wind_band": "W15", "wind_band_merged": "HF_W09_W14"}
    for p in focus:
        lines.append(f"| {names[p['group_type']]} | ONC−{p['baseline']} | {p['mean_delta_Q_0_20_m']:.9g} | {p['wins']} | {p['losses']} | {p['ties']} | {p['improved_at_least_1um']} | {p['improved_at_least_10um']} |")
    lines += ["", "## 各任务输场", ""]
    tasks = sorted({r["task"] for r in rows})
    for task in tasks:
        for baseline in ("ON1", "B"):
            scene_ids = [x["scene_id"] for x in losses if x["task"] == task and x["candidate"] == "ONC" and x["baseline"] == baseline]
            lines.append(f"- {task}，ONC 相对 {baseline}：" + (", ".join(scene_ids) if scene_ids else "无输场"))
    lines += ["", "计时字段保留原值并标记为受干扰的诊断，不作为正式速度结论。", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("probe-smoke", "full"), default="full")
    args = parser.parse_args()
    full = args.mode == "full"
    lock, release, r2 = frozen_inputs()
    rows_src, summaries = load_summaries(full, lock, release)
    rows = score_rows(rows_src, lock, release, r2)
    if not full:
        assert len(rows) == 3 and [r["condition"] for r in rows] == list(CONDITIONS)
        assert all(r["safe_complete_finite"] and r["status"] == "STABLE" for r in rows)
        result = {"status": "PASS_PROBE_SCORE_SMOKE", "scene_id": rows[0]["scene_id"],
                  "source_lock_sha256": release["source_lock_sha256"],
                  "probe_summary_sha256": sha256(REPORTS / "probe_c1_v9.json"),
                  "c_star": float(lock["calibration"]["c_star"]),
                  "rows": [{"condition": r["condition"], "Q_0_20_m": r["Q_0_20_m"],
                            "raw_sha256": r["raw_sha256"], "safe_complete_finite": r["safe_complete_finite"]}
                           for r in rows], "continue_authorized": False,
                  "plant_called_by_scorer": False, "optimizer_steps": 0, "TEST_accessed": False}
        out = REPORTS / "C1_PROBE_SCORE_SMOKE_FINAL.json"
        assert not out.exists()
        out.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2, allow_nan=False))
        return
    assert len(rows) == 36 and all(r["safe_complete_finite"] for r in rows)
    assert sum(r["condition"] == "B" and r["reused_prior_run"] for r in rows) == 1
    assert sum(r["condition"] != "B" and r["reused_prior_run"] for r in rows) == 0
    groups, pair_groups = aggregate_rows(rows)
    comparisons = []
    for scene in lock["shared_scenes"]:
        cell = {r["condition"]: r for r in rows if r["scene_id"] == scene["scene_id"]}
        for candidate, baseline in PAIRS:
            a, b = cell[candidate], cell[baseline]
            d = a["Q_0_20_m"] - b["Q_0_20_m"]
            outcome = "WIN" if d < -TOL else "LOSS" if d > TOL else "TIE"
            item = {"scene_id": scene["scene_id"], "task": scene["task"], "wind_band": scene["band"],
                    "candidate": candidate, "baseline": baseline, "delta_Q_0_20_m": d,
                    "outcome_tol_1e-12m": outcome, "improved_at_least_1um": d <= -1e-6,
                    "improved_at_least_10um": d <= -1e-5}
            for phase in PHASES:
                item[f"delta_Q_{phase}_m"] = a[f"Q_{phase}_m"] - b[f"Q_{phase}_m"]
                for axis in AXES:
                    item[f"delta_rmse_{axis}_{phase}_m"] = a[f"rmse_{axis}_{phase}_m"] - b[f"rmse_{axis}_{phase}_m"]
            comparisons.append(item)
    outputs = {
        "C1_SCREEN_PER_RUN.csv": rows,
        "C1_SCREEN_GROUP_SUMMARY.csv": groups,
        "C1_SCREEN_PAIRED_DELTAS.csv": comparisons,
        "C1_SCREEN_PAIRWISE_GROUPS.csv": pair_groups,
        "C1_SCREEN_LOSSES.csv": [r for r in comparisons if r["outcome_tol_1e-12m"] == "LOSS"],
    }
    paths = {name: REPORTS / name for name in outputs}
    for path in paths.values():
        assert not path.exists(), f"Refusing overwrite: {path}"
    for name, data in outputs.items():
        write_csv(paths[name], data, list(comparisons[0]) if name == "C1_SCREEN_LOSSES.csv" else None)
    losses = [r for r in comparisons if r["outcome_tol_1e-12m"] == "LOSS"]
    report = final_report(rows, pair_groups, losses, {"c_star": lock["calibration"]["c_star"],
                                                      "source_lock_sha256": release["source_lock_sha256"]})
    report_path = REPORTS / "C1_SCREEN_REPORT_ZH.md"
    audit_path = REPORTS / "C1_SCREEN_AUDIT.json"
    assert not report_path.exists() and not audit_path.exists()
    report_path.write_text(report, encoding="utf-8")
    audit = {"status": "PASS_FIXED_12_SCENE_SCORE", "created_utc": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "source_lock_sha256": release["source_lock_sha256"], "release_sha256": sha256(HERE / "C1_RELEASE_v9.json"),
        "probe_summary_sha256": sha256(REPORTS / "probe_c1_v9.json"),
        "continue_summary_sha256": sha256(REPORTS / "continue_c1_v9.json"),
        "scene_count": 12, "run_count": 36, "conditions": list(CONDITIONS), "c_star": float(lock["calibration"]["c_star"]),
        "q_rule": "Arithmetic mean of per-run RMSE; no pooled SSE square-root.",
        "win_tolerance_m": TOL, "sensitivity_thresholds_m": [1e-6, 1e-5],
        "formal_timing_authorized": False, "optimizer_steps": 0, "gpu_jobs": 0,
        "TEST_accessed": False, "development_labels_used_for_calibration": False,
        "development_scores_used_for_screen": True,
        "numerical_algorithm_note": "Reuses the existing primary raw score helper; not a separately implemented second algorithm. Parent independently recalculated probe Q from raw files.",
        "inputs": {name: sha256(Path(item["path"])) for name, item in
                   (("scene_list", r2["scene_list"]), ("payload_identity", r2["scene_payload_identity"]),
                    ("reuse_manifest", r2["reuse_manifest"]))},
        "outputs": {name: sha256(path) for name, path in paths.items()} |
                    {report_path.name: sha256(report_path)}}
    audit_path.write_text(json.dumps(audit, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": audit["status"], "scene_count": 12, "run_count": 36,
                      "outputs": [str(p) for p in [*paths.values(), report_path, audit_path]]}, indent=2))


if __name__ == "__main__":
    main()
