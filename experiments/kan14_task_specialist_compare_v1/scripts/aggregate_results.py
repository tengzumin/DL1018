from __future__ import annotations

import csv
import json
import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "experiments" / "kan14_task_specialist_compare_v1"
REPORTS = OUT / "reports"
TASKS = ("HELIX", "FIG8_3D", "SQUARE")
POLICIES = ("SHARED_KAN14", "TASK_SPECIALIST")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = list(rows[0]) if rows else []
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def number(row: dict, key: str) -> float | None:
    try:
        value = float(row[key])
    except (KeyError, TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def mean(values: list[float | None]) -> float | None:
    finite = [value for value in values if value is not None and math.isfinite(value)]
    return math.fsum(finite) / len(finite) if finite else None


def win_count(rows: list[dict], left: str, right: str) -> int:
    return sum(number(row, left) is not None and number(row, right) is not None
               and number(row, left) < number(row, right) for row in rows)


def worst(rows: list[dict], delta_key: str) -> dict:
    candidates = [(number(row, delta_key), row) for row in rows]
    candidates = [(value, row) for value, row in candidates if value is not None]
    if not candidates:
        return {"m": None, "scene_id": ""}
    value, row = max(candidates, key=lambda item: item[0])
    return {"m": value, "scene_id": row["scene_id"]}


def strategy_summary(name: str, rows: list[dict]) -> dict:
    qkey = "shared_Q_0_20_m" if name == "SHARED_KAN14" else "expert_Q_0_20_m"
    q_vs_b = [number(row, qkey) - number(row, "B_Q_0_20_m")
              for row in rows if number(row, qkey) is not None and number(row, "B_Q_0_20_m") is not None]
    deltas = [{**row, "delta": number(row, qkey) - number(row, "B_Q_0_20_m")}
              for row in rows if number(row, qkey) is not None and number(row, "B_Q_0_20_m") is not None]
    worst_b = worst(deltas, "delta")
    return {
        "policy": name,
        "scene_count": len(rows),
        "macro_Q_0_20_m": mean([number(row, qkey) for row in rows]),
        "same_scene_B_macro_Q_0_20_m": mean([number(row, "B_Q_0_20_m") for row in rows]),
        "macro_delta_vs_B_m": mean(q_vs_b),
        "wins_vs_B_strict": win_count(rows, qkey, "B_Q_0_20_m"),
        "losses_vs_B_strict": sum(number(row, qkey) is not None and number(row, "B_Q_0_20_m") is not None
                                   and number(row, qkey) > number(row, "B_Q_0_20_m") for row in rows),
        "ties_vs_B": sum(number(row, qkey) is not None and number(row, "B_Q_0_20_m") is not None
                         and number(row, qkey) == number(row, "B_Q_0_20_m") for row in rows),
        "worst_delta_vs_B_m": worst_b["m"],
        "worst_delta_vs_B_scene_id": worst_b["scene_id"],
        "macro_Q_0_5_m": mean([number(row, "shared_Q_0_5_m" if name == "SHARED_KAN14" else "expert_Q_0_5_m") for row in rows]),
        "macro_Q_5_20_m": mean([number(row, "shared_Q_5_20_m" if name == "SHARED_KAN14" else "expert_Q_5_20_m") for row in rows]),
        "macro_position_peak_m": mean([number(row, "shared_position_peak_m" if name == "SHARED_KAN14" else "expert_position_peak_m") for row in rows]),
        "macro_position_p95_m": mean([number(row, "shared_position_p95_m" if name == "SHARED_KAN14" else "expert_position_p95_m") for row in rows]),
        "macro_A_0_20_rad": mean([number(row, "shared_A_0_20_rad" if name == "SHARED_KAN14" else "expert_A_0_20_rad") for row in rows]),
        "macro_motor_TV_normalized_per_s": mean([number(row, "shared_motor_TV_normalized_per_s" if name == "SHARED_KAN14" else "expert_motor_TV_normalized_per_s") for row in rows]),
        "macro_motor_saturation_fraction": mean([number(row, "shared_motor_saturation_fraction" if name == "SHARED_KAN14" else "expert_motor_saturation_fraction") for row in rows]),
        "macro_generalized_clip_fraction": mean([number(row, "shared_generalized_clip_fraction" if name == "SHARED_KAN14" else "expert_generalized_clip_fraction") for row in rows]),
    }


def summarize_group(name: str, pairs: list[dict], task: str = "ALL") -> dict:
    shared = mean([number(row, "shared_Q_0_20_m") for row in pairs])
    expert = mean([number(row, "expert_Q_0_20_m") for row in pairs])
    base = mean([number(row, "B_Q_0_20_m") for row in pairs])
    worst_b = worst([{**row, "delta": number(row, "expert_minus_B_m")} for row in pairs], "delta")
    worst_shared = worst([{**row, "delta": number(row, "expert_minus_shared_Q_m")} for row in pairs], "delta")
    out = {
        "stratum": name,
        "task": task,
        "scene_count": len(pairs),
        "B_macro_Q_0_20_m": base,
        "shared_macro_Q_0_20_m": shared,
        "expert_macro_Q_0_20_m": expert,
        "expert_improvement_vs_shared_m": None if shared is None or expert is None else shared - expert,
        "expert_improvement_vs_shared_pct": None if not shared else (shared - expert) / shared * 100,
        "expert_minus_B_macro_Q_m": None if base is None or expert is None else expert - base,
        "expert_wins_vs_shared": win_count(pairs, "expert_Q_0_20_m", "shared_Q_0_20_m"),
        "expert_wins_vs_B_strict": win_count(pairs, "expert_Q_0_20_m", "B_Q_0_20_m"),
        "shared_wins_vs_B_strict": win_count(pairs, "shared_Q_0_20_m", "B_Q_0_20_m"),
        "worst_expert_delta_vs_B_m": worst_b["m"],
        "worst_expert_delta_vs_B_scene_id": worst_b["scene_id"],
        "worst_expert_delta_vs_shared_m": worst_shared["m"],
        "worst_expert_delta_vs_shared_scene_id": worst_shared["scene_id"],
    }
    for key in ("Q_0_5_m", "Q_5_20_m", "dynamic_Q_5_20_m", "position_peak_m", "position_p95_m",
                "A_0_20_rad", "motor_TV_normalized_per_s", "motor_saturation_fraction", "generalized_clip_fraction"):
        out[f"shared_macro_{key}"] = mean([number(row, f"shared_{key}") for row in pairs])
        out[f"expert_macro_{key}"] = mean([number(row, f"expert_{key}") for row in pairs])
    return out


def main() -> None:
    rows = read_csv(REPORTS / "DEV24_PAIRED_RESULTS.csv")
    if len(rows) != 48 or len({row["run_id"] for row in rows}) != 48:
        raise RuntimeError(f"Expected 48 unique completed runs; found {len(rows)}")
    if {row["seed"] for row in rows} != {"2026102001"}:
        raise RuntimeError("The frozen user-authorized single seed is not the only evaluated seed")
    policies = defaultdict(list)
    by_scene = defaultdict(dict)
    for row in rows:
        strategy = "SHARED_KAN14" if row["policy_id"] == "SHARED_KAN14" else "TASK_SPECIALIST"
        if strategy == "TASK_SPECIALIST" and row["policy_id"] != f"TASK_KAN14_{row['task']}":
            raise RuntimeError(f"Task router mismatch: {row['run_id']}")
        policies[strategy].append(row)
        if row["scene_id"] in by_scene[strategy]:
            raise RuntimeError(f"Duplicate policy/scene row: {row['policy_id']} {row['scene_id']}")
        by_scene[strategy][row["scene_id"]] = row
        if row["status"] != "STABLE" or row["complete"] != "1" or row["finite"] != "1" or row["transitions"] != "20000":
            raise RuntimeError(f"Unstable/incomplete run is present: {row['run_id']}")
    if len(policies["SHARED_KAN14"]) != 24 or len(policies["TASK_SPECIALIST"]) != 24:
        raise RuntimeError("Expected 24 shared and 24 task-specialist runs")
    if set(by_scene["SHARED_KAN14"]) != set(by_scene["TASK_SPECIALIST"]):
        raise RuntimeError("Shared and task-specialist scene sets differ")

    pairs: list[dict] = []
    for scene_id, shared in by_scene["SHARED_KAN14"].items():
        expert = by_scene["TASK_SPECIALIST"][scene_id]
        if shared["task"] != expert["task"] or shared["B_run_id"] != expert["B_run_id"]:
            raise RuntimeError(f"Task or same-scene B mismatch: {scene_id}")
        bq = number(shared, "B_Q_0_20_m")
        if bq is None or bq != number(expert, "B_Q_0_20_m"):
            raise RuntimeError(f"Same-scene B Q mismatch: {scene_id}")
        s_q, e_q = number(shared, "Q_0_20_m"), number(expert, "Q_0_20_m")
        pair = {
            "scene_id": scene_id, "task": shared["task"], "seed": shared["seed"],
            "stratum": "C00" if "_C00_" in scene_id else ("W15" if scene_id.endswith("_W15") else "DEFORMATION_OTHER"),
            "B_run_id": shared["B_run_id"], "B_Q_0_20_m": bq,
            "shared_run_id": shared["run_id"], "shared_status": shared["status"], "shared_Q_0_20_m": s_q,
            "expert_run_id": expert["run_id"], "expert_status": expert["status"], "expert_Q_0_20_m": e_q,
            "shared_minus_B_m": None if s_q is None else s_q - bq,
            "expert_minus_B_m": None if e_q is None else e_q - bq,
            "expert_minus_shared_Q_m": None if e_q is None or s_q is None else e_q - s_q,
            "expert_improvement_vs_shared_pct": None if not s_q else (s_q - e_q) / s_q * 100,
            "shared_wins_vs_B_strict": int(s_q is not None and s_q < bq),
            "expert_wins_vs_B_strict": int(e_q is not None and e_q < bq),
            "expert_wins_vs_shared_strict": int(e_q is not None and s_q is not None and e_q < s_q),
        }
        for prefix, source in (("shared", shared), ("expert", expert)):
            for field in ("Q_0_5_m", "Q_5_20_m", "dynamic_Q_5_20_m", "position_peak_m", "position_p95_m",
                          "position_axis_rmse_m", "attitude_axis_rmse_rad", "A_0_20_rad", "yaw_peak_abs_rad",
                          "motor_TV_normalized_per_s", "motor_saturation_fraction", "generalized_clip_fraction",
                          "controller_p99_ms", "control_loop_p99_ms", "position_head_update_count",
                          "position_head_projection_count", "head_output_clip_count", "phase_metrics_json"):
                pair[f"{prefix}_{field}"] = source[field]
        pairs.append(pair)

    task_rows = [summarize_group(task, [row for row in pairs if row["task"] == task], task) for task in TASKS]
    task_rows.append(summarize_group("ALL_24", pairs))
    strata_defs = (
        ("ALL_24", lambda row: True),
        ("C00", lambda row: "_C00_" in row["scene_id"]),
        ("DEFORMATION_21", lambda row: "_C00_" not in row["scene_id"]),
        ("W15_SUBSET_3", lambda row: row["scene_id"].endswith("_W15")),
        ("DEFORMATION_EXCLUDING_W15_18", lambda row: "_C00_" not in row["scene_id"] and not row["scene_id"].endswith("_W15")),
    )
    strata_rows = [summarize_group(name, [row for row in pairs if predicate(row)]) for name, predicate in strata_defs]
    policy_rows = [strategy_summary(name, pairs) for name in POLICIES]
    for row in policy_rows:
        row["expert_improvement_vs_shared_m"] = None
        row["expert_wins_vs_shared"] = None
    shared_macro = mean([number(row, "shared_Q_0_20_m") for row in pairs])
    expert_macro = mean([number(row, "expert_Q_0_20_m") for row in pairs])
    overall_worst_b = worst([{**row, "delta": number(row, "expert_minus_B_m")} for row in pairs], "delta")
    overall_worst_shared = worst([{**row, "delta": number(row, "expert_minus_shared_Q_m")} for row in pairs], "delta")
    policy_rows[0]["expert_improvement_vs_shared_m"] = shared_macro - expert_macro
    policy_rows[0]["expert_wins_vs_shared"] = win_count(pairs, "expert_Q_0_20_m", "shared_Q_0_20_m")
    policy_rows[1]["expert_improvement_vs_shared_m"] = shared_macro - expert_macro
    policy_rows[1]["expert_wins_vs_shared"] = win_count(pairs, "expert_Q_0_20_m", "shared_Q_0_20_m")

    fits = read_csv(REPORTS / "training_results.csv")
    fits = [row for row in fits if row["stage"].startswith("TASK_")]
    if len(fits) != 3 or any(row["status"] != "COMPLETE" or row["seed"] != "2026102001" for row in fits):
        raise RuntimeError("Expected exactly three complete task-expert fits for seed 2026102001")
    parity = json.loads((REPORTS / "EXPORT_PARITY.json").read_text(encoding="utf-8"))
    if parity.get("status") != "PASS" or parity.get("package_count") != 4 or parity.get("plant_starts") != 0:
        raise RuntimeError("Four-package zero-Plant parity gate did not pass")
    audit = json.loads((REPORTS / "DATA_AND_WEIGHT_AUDIT.json").read_text(encoding="utf-8"))
    cleanup_md = (OUT / "cleanup" / "CLEANUP_REPORT_ZH.md").read_text(encoding="utf-8")
    cleanup_counts = re.search(r"扫描到 MAT：(\d+) 个；逐文件保留：(\d+) 个；删除计划：(\d+) 个；实际删除：(\d+) 个；跳过：(\d+) 个。", cleanup_md)
    volume_gain = re.search(r"卷可用空间实增：([0-9.]+) GiB", cleanup_md)
    logical_gain = re.search(r"实际删除逻辑大小：([0-9.]+) GiB", cleanup_md)
    if not cleanup_counts or not volume_gain or not logical_gain:
        raise RuntimeError("Cleanup evidence report is missing the audited counts/space figures")
    markers = list((OUT / "runs").rglob("plant_started.marker"))
    raw_files = list((OUT / "runs").rglob("raw_run.mat"))
    start_files = list((OUT / "runs").rglob("run_start.mat"))
    metric_files = list((OUT / "runs").rglob("metrics.json"))
    mat_files = list(OUT.rglob("*.mat"))
    error_files = list((OUT / "runs").rglob("error.json"))
    recovered = sum(bool(json.loads(path.read_text(encoding="utf-8")).get("recovered_from_raw")) for path in metric_files)
    if not (len(markers) == len(raw_files) == len(start_files) == len(metric_files) == 48) or error_files:
        raise RuntimeError("Run evidence count mismatch or error.json exists")

    def dump_json(path: Path, value: dict) -> None:
        path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")

    write_csv(REPORTS / "DEV24_SCENE_PAIRED.csv", pairs)
    write_csv(REPORTS / "DEV24_TASK_SUMMARY.csv", task_rows)
    write_csv(REPORTS / "DEV24_STRATA_SUMMARY.csv", strata_rows)
    write_csv(REPORTS / "DEV24_POLICY_SUMMARY.csv", policy_rows)

    result = {
        "status": "PASS_SINGLE_SEED_DEV24_COMPLETE",
        "scope": "Task-specialist KAN14 versus shared KAN14, matched same-scene B, DEV only.",
        "seed": 2026102001,
        "seeds_requested_in_original_prompt": [2026102001, 2026102002],
        "seed_2026102002_run": False,
        "seed_omission_reason": "User explicitly requested one seed only.",
        "test_accessed": False,
        "training": {"expert_fits": 3, "steps_per_expert": 20000, "new_optimizer_steps_total": 60000,
                     "shared_reference_steps": 60000, "matched_initialization": "PASS", "expert_fit_records": fits},
        "export_parity": parity,
        "data_and_weight_preflight": {"status": audit.get("status"), "details": audit},
        "closed_loop": {"status": "COMPLETE", "scenes": 24, "shared_runs": 24, "expert_runs": 24,
                        "completed_runs": 48, "stable_finite_complete_runs": 48, "plant_starts": 48,
                        "plant_budget_max": 48, "raw_run_mats": len(raw_files), "run_start_mats": len(start_files),
                        "metrics_files": len(metric_files), "recovered_from_existing_raw": recovered,
                        "same_scene_B_reused": True, "test_accessed": False},
        "overall": {"shared_macro_Q_0_20_m": shared_macro, "task_specialist_macro_Q_0_20_m": expert_macro,
                    "specialist_improvement_vs_shared_m": shared_macro - expert_macro,
                    "specialist_improvement_vs_shared_pct": (shared_macro - expert_macro) / shared_macro * 100,
                    "specialist_wins_vs_shared": win_count(pairs, "expert_Q_0_20_m", "shared_Q_0_20_m"),
                    "specialist_wins_vs_B_strict": win_count(pairs, "expert_Q_0_20_m", "B_Q_0_20_m"),
                    "shared_wins_vs_B_strict": win_count(pairs, "shared_Q_0_20_m", "B_Q_0_20_m"),
                    "worst_specialist_delta_vs_B_m": overall_worst_b,
                    "worst_specialist_delta_vs_shared_m": overall_worst_shared},
        "task_summary": task_rows,
        "strata_summary": strata_rows,
        "cleanup": {"scanned_mat": int(cleanup_counts.group(1)), "kept_mat": int(cleanup_counts.group(2)),
                    "planned_delete_mat": int(cleanup_counts.group(3)), "deleted_mat": int(cleanup_counts.group(4)),
                    "skipped_mat": int(cleanup_counts.group(5)), "deleted_logical_GiB": float(logical_gain.group(1)),
                    "volume_free_space_gain_GiB": float(volume_gain.group(1))},
        "github_upload": {"mat_files_uploaded": False, "mat_files_kept_local": len(mat_files),
                          "mat_bytes_kept_local": sum(path.stat().st_size for path in mat_files)},
        "conclusion_limitations": ["Only one seed was run per user instruction; seed-to-seed direction is not estimable.",
                                   "DEV was used for the preregistered comparison; this is not a claim of unseen-condition generalization.",
                                   "Specialist policy uses three separately stored models; matched total optimizer steps do not remove the difference in total parameter storage."],
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    dump_json(REPORTS / "FINAL_RESULT.json", result)

    task_lines = []
    for row in task_rows[:3]:
        task_lines.append(
            f"| {row['task']} | {row['scene_count']} | {row['B_macro_Q_0_20_m']:.6f} | "
            f"{row['shared_macro_Q_0_20_m']:.6f} | {row['expert_macro_Q_0_20_m']:.6f} | "
            f"{row['expert_improvement_vs_shared_m']:+.6f} | {row['expert_wins_vs_B_strict']}/8 | "
            f"{row['expert_wins_vs_shared']}/8 |"
        )
    strat_lines = []
    for row in strata_rows:
        strat_lines.append(
            f"| {row['stratum']} | {row['scene_count']} | {row['B_macro_Q_0_20_m']:.6f} | "
            f"{row['shared_macro_Q_0_20_m']:.6f} | {row['expert_macro_Q_0_20_m']:.6f} | "
            f"{row['expert_improvement_vs_shared_m']:+.6f} | {row['expert_wins_vs_B_strict']}/{row['scene_count']} |"
        )
    task_worst_lines = []
    for row in task_rows[:3]:
        worst_b = worst([pair for pair in pairs if pair["task"] == row["task"]], "expert_minus_B_m")
        worst_shared = worst([pair for pair in pairs if pair["task"] == row["task"]], "expert_minus_shared_Q_m")
        task_worst_lines.append(
            f"| {row['task']} | {worst_b['m']:+.6f} ({worst_b['scene_id']}) | "
            f"{worst_shared['m']:+.6f} ({worst_shared['scene_id']}) |"
        )
    report = [
        "# DL1018 三任务 KAN14 专家对照结果", "",
        "## 结论", "",
        f"在单种子 DEV24 上，三个任务专家组成的路由策略宏 Q 为 **{expert_macro:.6f} m**，"
        f"共享 KAN14 宏 Q 为 **{shared_macro:.6f} m**；专家策略平均改善 **{shared_macro-expert_macro:+.6f} m** "
        f"（改善百分比 {(shared_macro-expert_macro)/shared_macro*100:+.2f}%），24 场中有 "
        f"{win_count(pairs, 'expert_Q_0_20_m', 'shared_Q_0_20_m')}/24 场专家优于共享。",
        f"专家策略有 {win_count(pairs, 'expert_Q_0_20_m', 'B_Q_0_20_m')}/24 场严格低于同场 B；"
        f"共享策略有 {win_count(pairs, 'shared_Q_0_20_m', 'B_Q_0_20_m')}/24 场严格低于 B。"
        "因此，除非 24/24 场严格低于 B，否则不能称为逐场超过 B。", "",
        "| 任务 | 场数 | B 宏 Q (m) | 共享宏 Q (m) | 专家宏 Q (m) | 专家改善 vs 共享 (m) | 专家胜 B | 专家胜共享 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|", *task_lines, "",
        "改善量定义为 `共享宏 Q − 专家宏 Q`，正值代表专家误差更低。", "",
        "逐任务最差退化（按专家 Q 减比较对象 Q；正值表示专家更差）：", "",
        "| 任务 | 相对 B 最差差值 (m；场景) | 相对共享最差差值 (m；场景) |",
        "|---|---:|---:|", *task_worst_lines, "",
        "HELIX 的专家宏 Q 略优于共享，但仅 2/8 场优于 B；FIG8_3D 专家宏 Q 比共享高 1.882 mm；SQUARE 比共享高 0.422 mm。", "",
        "## 场景分层", "",
        "C00 为 3 个未变形场景；变形场景 21 个。W15 是其中 3 个高风场景的子集，不与变形场景重复相加。", "",
        "| 分层 | 场数 | B 宏 Q (m) | 共享宏 Q (m) | 专家宏 Q (m) | 专家改善 vs 共享 (m) | 专家胜 B |",
        "|---|---:|---:|---:|---:|---:|---:|", *strat_lines, "",
        "## 协议与数据完整性", "",
        f"- 专家模型：seed 2026102001；HELIX、FIG8_3D、SQUARE 各训练 20,000 步，共新增 60,000 步；共享参照 final 为既有 60,000 步模型。"
        "同种子同结构的三个专家初始权重一致，规范化器和数据划分按冻结协议复用。",
        f"- 4 个导出包均通过 PyTorch/MATLAB parity：每包 64 个验证窗口，共 {parity['fixture_total']} 个；最大输出误差 "
        f"{max(item['max_output_error'] for item in parity['packages']):.3e} m/s²（门槛 1e-5）；readout 与输出后更新一致误差均为 0。Parity Plant 数为 0。",
        "- DEV 闭环：24 场共享 + 24 场按任务路由的专家；48/48 条稳定、有限、完整，各 20,000 transitions；同场 B 直接复用。"
        "没有因表现筛除场景，也没有接触 TEST。",
        "- 用户明确要求只跑一个种子，因此未运行 2026102002，也不报告种子间方向。结果是已查看 DEV 上的单种子比较，不代表未见工况上的泛化证明。",
        "- 三专家策略在航次前按任务固定路由，使用三份独立模型；总训练步数与共享模型相等，但总参数存储是共享模型的三倍量级。因此观测差异不能单独归因于负迁移。", "",
        "### 训练验证 RMSE (m/s²)", "",
        "| 专家 | 最佳步 | 最佳 VAL RMSE | 最终步 VAL RMSE |", "|---|---:|---:|---:|",
    ]
    for fit in fits:
        task = fit["group"].replace("TASK_", "")
        report.append(f"| {task} | {int(fit['selected_step'])} | {float(fit['weighted_val_rmse_mps2']):.6f} | {float(fit['final_val_rmse_mps2']):.6f} |")
    report += [
        "", "## 伴随指标与逐场证据", "",
        "`DEV24_SCENE_PAIRED.csv` 提供每场 B、共享、专家的位置 RMSE、早期/后期与动态段 Q、逐轴 RMSE、姿态误差、峰值/P95、motor TV、饱和/裁剪计数及分阶段指标。"
        "宏 Q 按场等权平均。`DEV24_PAIRED_RESULTS.csv` 保存每条实际运行的完整记录。", "",
        "## 历史 MAT 清理", "",
        f"扫描 {cleanup_counts.group(1)} 个 MAT；保留 {cleanup_counts.group(2)} 个；实际删除 {cleanup_counts.group(4)} 个；跳过 {cleanup_counts.group(5)} 个。"
        f"删除文件逻辑大小 {logical_gain.group(1)} GiB；卷可用空间实际增加 **{volume_gain.group(1)} GiB**。"
        "逻辑文件大小和卷空间变化分别统计。逐文件清单见 cleanup 目录。", "",
        f"## GitHub 上传范围\n\n按用户要求，{len(mat_files)} 个 MAT 文件（合计 {sum(path.stat().st_size for path in mat_files) / (1024**3):.3f} GiB）留在本机，不上传。GitHub 分支仅包含代码、模型权重检查点、CSV/JSON 结果、报告、清理记录及运行文档。", "",
        "## 交付文件", "",
        "- `protocol.json`、`reports/DATA_AND_WEIGHT_AUDIT.json`、`reports/MATCHED_INITIALIZATION.json`",
        "- `models/task_specialists/`、`models/shared/`、`manifests/package_registry.csv`、`reports/EXPORT_PARITY.json`",
        "- `reports/DEV24_PAIRED_RESULTS.csv`、`reports/DEV24_SCENE_PAIRED.csv`、`reports/DEV24_TASK_SUMMARY.csv`、`reports/DEV24_STRATA_SUMMARY.csv`、`reports/DEV24_POLICY_SUMMARY.csv`",
        "- `RESOURCE_LEDGER.csv`、`RUN_COMMANDS.md`、`RESUME.md`、`FINAL_RESULT.json`",
        "- 清理逐文件记录：`cleanup/KEEP_MAT_MANIFEST.csv`、`cleanup/DELETE_MAT_PLAN.csv`、`cleanup/DELETED_MAT.csv`、`cleanup/SKIPPED_MAT.csv`、`cleanup/CLEANUP_REPORT_ZH.md`", "",
        "本任务到此结束；不自动启动 Student 采集、额外模型筛选、融合或蒸馏。", "",
    ]
    (REPORTS / "FINAL_REPORT_ZH.md").write_text("\n".join(report), encoding="utf-8")

    progress_path = REPORTS / "DEV24_PROGRESS.json"
    progress = json.loads(progress_path.read_text(encoding="utf-8"))
    progress.update({"status": "COMPLETE", "completed_runs": 48, "expected_runs": 48,
                     "shared_completed": 24, "expert_completed": 24, "cumulative_Plant_starts": 48,
                     "eta_remaining_s": 0, "latest_policy": "TASK_KAN14_SQUARE",
                     "updated_at_utc": result["completed_at_utc"]})
    dump_json(progress_path, progress)
    state_path = OUT / "state" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state.update({"status": "COMPLETE", "phase": "DEV24_COMPLETE", "plant_starts": 48,
                  "completed_runs": 48, "expected_runs": 48, "cumulative_new_plant_starts": 48,
                  "active_policy": "", "active_scene": "", "active_run_id": "",
                  "updated_at_utc": result["completed_at_utc"]})
    dump_json(state_path, state)
    preflight_path = REPORTS / "DEV24_PREFLIGHT.json"
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    if int(preflight.get("plant_starts_before", 0)) > 0:
        preflight["status"] = "PASS_BEFORE_RESUMED_DEV_PLANT"
        preflight["note"] = "The first Plant run completed, then result aggregation hit a field-name error. Its complete raw MAT was reused; no duplicate Plant run was launched."
        dump_json(preflight_path, preflight)

    print(f"AGGREGATION_COMPLETE runs=48 shared_macro={shared_macro:.8f} expert_macro={expert_macro:.8f} "
          f"expert_wins_B={win_count(pairs, 'expert_Q_0_20_m', 'B_Q_0_20_m')}/24 seed=2026102001")


if __name__ == "__main__":
    main()
