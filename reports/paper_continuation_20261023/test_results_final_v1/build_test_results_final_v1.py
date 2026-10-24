from __future__ import annotations
import csv
import hashlib
import json
import math
from pathlib import Path
from statistics import fmean

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
INPUTS = {
    "raw_audit": Path("reports/paper_continuation_20261023/test_handoff_incident_v1/recovery_v1/raw_review_v5/RECOVERY288_FULL_RAW_AUDIT_v5.json"),
    "statistics": Path("reports/paper_continuation_20261023/test_handoff_incident_v1/recovery_v1/statistics_v5/RECOVERY288_FINAL_STATISTICS_v5.json"),
    "parent_review": Path("reports/paper_continuation_20261023/test_handoff_incident_v1/recovery_v1/statistics_v5/PARENT_INDEPENDENT_PERFORMANCE_REVIEW_v1.json"),
    "dev72": Path("reports/paper_continuation_20261023/c5_dev72_parent_review/C5_DEV72_RAW_METRICS_v3.csv"),
    "historical_incident": Path("reports/paper_continuation_20261023/c5_eight_loss_recovery/v2/HISTORICAL_TEST_EXPOSURE_INCIDENT_v1.json"),
    "raw_audit_source": Path("reports/paper_continuation_20261023/test_handoff_incident_v1/recovery_v1/raw_review_v5/audit_test48_raw_recovery288_v5.py"),
    "statistics_source": Path("reports/paper_continuation_20261023/test_handoff_incident_v1/recovery_v1/statistics_v5/test48_statistics_recovery288_v5.py"),
}
EXPECTED_SHA256 = {
    "raw_audit": "3ae6d02fb36beb6690696c4b34b63106169bd98acd0fc5191140ef39329ab6a2",
    "statistics": "d7e3af0215e159a885691c8a4ab755333b90345650afc5370b65814f9498e1a8",
    "parent_review": "5315c7cd1cbef22fff407746837c02344e8e4473602da44b9082a2f1fce95f8d",
    "dev72": "3986e5ed42986c317b64fecfa508d5791709812f5c8443bf04cbce52e04a3a4c",
    "historical_incident": "42f1c2f672091ce46040222f1878cbf537adb647081f342a6378f353ed616c2b",
    "raw_audit_source": "7d81d3274801b6a33e18900c7da938d5db45c26ecd728517a585da2fbaef6495",
    "statistics_source": "679c36785a4d8cdaea0d63a70f716a123528dc39fd9a95d43912e8521f9e90b8",
}
METHODS = ["B_TRACEABLE", "CORRECTED_DSSM14_G12_R32", "CORRECTED_KAN14_G12_R32", "C5_M110", "C5_FREEZE_TRAINED_W0", "C5_NO_DELAYED_PREDICTION"]
COMPARATORS = [m for m in METHODS if m != "C5_M110"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_json(path: Path):
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def write_csv(path: Path, fieldnames, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def mm(x):
    return None if x is None else float(x) * 1000.0


def safe_float(x):
    if x is None:
        return None
    return float(x)


def validate_inputs():
    meta = {}
    for name, rel in INPUTS.items():
        path = ROOT / rel
        if not path.is_file():
            raise FileNotFoundError(path)
        got = sha256(path)
        expected = EXPECTED_SHA256[name]
        if got != expected:
            raise ValueError(f"SHA-256 mismatch for {name}: expected {expected}, got {got}")
        meta[name] = {"path": rel.as_posix(), "sha256": got, "bytes": path.stat().st_size}
    return meta


def main():
    input_meta = validate_inputs()
    raw = read_json(ROOT / INPUTS["raw_audit"])
    stats = read_json(ROOT / INPUTS["statistics"])
    parent = read_json(ROOT / INPUTS["parent_review"])
    incident = read_json(ROOT / INPUTS["historical_incident"])
    if raw.get("scene_count") != 48 or raw.get("method_count") != 6 or len(raw.get("rows", [])) != 288:
        raise ValueError("Unexpected raw audit dimensions")
    if stats.get("status") != "COMPUTED_RECOVERY288_STATISTICS_WITH_DSSM_HISTORY_DISCLOSED":
        raise ValueError("Unexpected statistics status")
    if parent.get("status") != "PASS_INDEPENDENT_AGGREGATE_RECOMPUTATION":
        raise ValueError("Parent independent recomputation did not pass")
    scenes = stats["per_scene_metrics_and_raw_identities"]
    if len(scenes) != 48:
        raise ValueError("Expected 48 paired TEST scenes")
    scene_meta = {r["scene_id"]: {"scene_index": i + 1, "task": r["task"], "wind": r["wind"]} for i, r in enumerate(scenes)}
    if set(scene_meta) != set(raw["scene_ids"]):
        raise ValueError("Scene sets differ between audit and statistics")
    if incident.get("status") != "HISTORICAL_TEST_METRICS_ACCIDENTALLY_DISPLAYED_DO_NOT_USE":
        raise ValueError("Unexpected historical-exposure incident status")

    # Complete long form: each audited raw row, enriched only with scene/method ordering metadata.
    long_rows = []
    q_by_scene = {scene: {} for scene in scene_meta}
    method_index = {m: i + 1 for i, m in enumerate(METHODS)}
    for row in raw["rows"]:
        meta = scene_meta[row["scene_id"]]
        if row["method"] not in method_index:
            raise ValueError(f"Unexpected method {row['method']}")
        item = {"scene_index": meta["scene_index"], "task": meta["task"], "wind": meta["wind"],
                "method_index": method_index[row["method"]], **row}
        long_rows.append(item)
        q_by_scene[row["scene_id"]][row["method"]] = row["Q_0_20_m"]
    if any(set(q_by_scene[s]) != set(METHODS) for s in q_by_scene):
        raise ValueError("Incomplete method pairing")
    long_fields = ["scene_index", "scene_id", "task", "wind", "method_index", "method", "path", "sha256", "external_identity_sha256",
                   "Q_0_20_m", "Q_0_5_m", "Q_5_20_m", "rmse_x_0_20_m", "rmse_y_0_20_m", "rmse_z_0_20_m",
                   "rmse_x_0_5_m", "rmse_y_0_5_m", "rmse_z_0_5_m", "rmse_x_5_20_m", "rmse_y_5_20_m", "rmse_z_5_20_m",
                   "peak_m", "p95_m", "motor_saturated_fraction", "generalized_clipped_fraction",
                   "controller_mean_s", "controller_p50_s", "controller_p95_s", "controller_p99_s", "controller_max_s",
                   "controller_over_1ms_fraction", "controller_ready_calls", "controller_nonready_calls", "controller_ready_mean_s",
                   "controller_ready_p50_s", "controller_ready_p95_s", "controller_ready_p99_s", "controller_ready_max_s",
                   "controller_ready_over_1ms_fraction", "controller_nonready_mean_s", "controller_nonready_p50_s",
                   "controller_nonready_p95_s", "controller_nonready_p99_s", "controller_nonready_max_s",
                   "controller_nonready_over_1ms_fraction", "status", "safety_stop", "safety_stop_reason", "complete", "actuator_finite_complete"]
    write_csv(OUT / "paired_complete_48x6_long.csv", long_fields, long_rows)

    wide_rows = []
    for s in scenes:
        r = {"scene_index": scene_meta[s["scene_id"]]["scene_index"], "scene_id": s["scene_id"], "task": s["task"], "wind": s["wind"]}
        for m in METHODS:
            r[f"Q_0_20_mm__{m}"] = mm(q_by_scene[s["scene_id"]][m])
        wide_rows.append(r)
    write_csv(OUT / "paired_Q_48x6_wide_mm.csv", list(wide_rows[0]), wide_rows)

    # Every loss row against every comparator, directly from the frozen stats JSON.
    loss_rows = []
    for comp in COMPARATORS:
        block = stats["C5_vs_other_methods"][comp]
        for loss in block["all_C5_losses_at_1e-12_m"]:
            loss_rows.append({"scene_id": loss["scene_id"], "task": loss["task"], "wind": loss["wind"], "comparator": comp,
                              "C5_Q_mm": mm(loss["Q_C5_m"]), "comparator_Q_mm": mm(loss["Q_other_m"]),
                              "C5_minus_comparator_mm": mm(loss["C5_minus_other_m"]), "tie_tolerance_m": stats["tie_tolerance_m"]})
    loss_rows.sort(key=lambda r: (METHODS.index(r["comparator"]), r["scene_id"]))
    write_csv(OUT / "C5_M110_losses_all_comparators.csv",
              ["scene_id", "task", "wind", "comparator", "C5_Q_mm", "comparator_Q_mm", "C5_minus_comparator_mm", "tie_tolerance_m"], loss_rows)

    sensitivity_rows = []
    for comp in COMPARATORS:
        sens = stats["C5_vs_other_methods"][comp]["sensitivity_wlt"]
        for key, threshold_um in [("1e-06_m", 1), ("1e-05_m", 10)]:
            v = sens[key]
            sensitivity_rows.append({"comparator": comp, "tie_threshold_um": threshold_um,
                                     "wins": v["wins"], "losses": v["losses"], "ties": v["ties"], "n_scenes": 48})
    write_csv(OUT / "paired_sensitivity_wlt_1_10um.csv", ["comparator", "tie_threshold_um", "wins", "losses", "ties", "n_scenes"], sensitivity_rows)

    # Grouped metrics are read from the existing statistics output; only unit conversion is applied.
    group_order = list(stats["summary_groups"].keys())
    group_rows = []
    axis_rows = []
    axis_groups = {"ALL48", "T1", "T2", "T3", "HF_W09_W14", "W15"}
    for group in group_order:
        g = stats["summary_groups"][group]
        for method in METHODS:
            metrics = g["metrics_by_method"][method]
            r = {"group": group, "n_scenes": g["n_scenes"], "method": method}
            for key, value in metrics.items():
                if key.endswith("_m"):
                    r[key.replace("_m", "_mm")] = mm(value["mean"])
                elif key.endswith("_s"):
                    r[key.replace("_s", "_ms")] = float(value["mean"]) * 1000.0
                else:
                    r[key] = value["mean"]
            group_rows.append(r)
            if group in axis_groups:
                for axis in "xyz":
                    for phase, metric in [("0_20", f"rmse_{axis}_0_20_m"), ("0_5", f"rmse_{axis}_0_5_m"), ("5_20", f"rmse_{axis}_5_20_m")]:
                        axis_rows.append({"group": group, "n_scenes": g["n_scenes"], "method": method,
                                          "axis": axis, "phase_s": phase.replace("_", "–"), "rmse_mean_mm": mm(metrics[metric]["mean"])})
    if group_rows:
        write_csv(OUT / "task_wind_axis_safety_saturation_timing_summary.csv", list(group_rows[0]), group_rows)
    write_csv(OUT / "axis_early_late_summary.csv", ["group", "n_scenes", "method", "axis", "phase_s", "rmse_mean_mm"], axis_rows)

    # Scene-paired bootstrap CIs are copied from the existing statistics JSON; no resampling here.
    ci_rows = []
    bootstrap = stats["bootstrap"]
    for group in bootstrap["group_order"]:
        gb = bootstrap["confidence_intervals"][group]
        for comp in COMPARATORS:
            c = gb["contrasts_C5_minus_other"][comp]
            ci_rows.append({"group": group, "n_scenes": gb["n_scenes"], "contrast": f"C5_M110 minus {comp}",
                            "mean_delta_mm": mm(c["mean_delta_Q_0_20_m"]), "ci95_low_mm": mm(c["ci95_m"][0]),
                            "ci95_high_mm": mm(c["ci95_m"][1]), "bootstrap_replicates": bootstrap["replicates"],
                            "seed": bootstrap["seed"], "interval_method": bootstrap["interval"]})
    write_csv(OUT / "paired_scene_bootstrap_ci.csv", list(ci_rows[0]), ci_rows)

    # Read-only DEV72 contextual summary; kept separate from TEST48.
    with (ROOT / INPUTS["dev72"]).open("r", encoding="utf-8-sig", newline="") as f:
        dev = list(csv.DictReader(f))
    if len(dev) != 72:
        raise ValueError(f"Expected 72 DEV rows, got {len(dev)}")
    dev_c5 = [float(r["Q_C5_0_20_m"]) for r in dev]
    dev_b = [float(r["Q_B_0_20_m"]) for r in dev]
    dev_c3 = [float(r["Q_C3_0_20_m"]) for r in dev]
    dev_delta = [float(r["Q_C5_minus_B_m"]) for r in dev]
    dev_summary = [{"dataset": "C5_DEV72 (context only)", "n_scenes": len(dev), "C5_mean_Q_mm": mm(fmean(dev_c5)),
                    "B_mean_Q_mm": mm(fmean(dev_b)), "C3_mean_Q_mm": mm(fmean(dev_c3)),
                    "C5_minus_B_mean_mm": mm(fmean(dev_delta)),
                    "C5_wins_vs_B": sum(x < -1e-12 for x in dev_delta), "losses": sum(x > 1e-12 for x in dev_delta),
                    "ties_at_1e-12_m": sum(abs(x) <= 1e-12 for x in dev_delta),
                    "source_note": "Separate DEV context; not merged with TEST48 and not an independent generalization claim."}]
    write_csv(OUT / "DEV72_reference_summary.csv", list(dev_summary[0]), dev_summary)

    # Publication figures: paired raw-scene points, grouped mean comparison, and precomputed paired CIs.
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.titlesize": 11,
                         "axes.labelsize": 9, "legend.fontsize": 8, "figure.dpi": 120,
                         "savefig.dpi": 300, "axes.spines.top": False, "axes.spines.right": False})
    colors = {"B_TRACEABLE": "#0072B2", "CORRECTED_DSSM14_G12_R32": "#E69F00", "CORRECTED_KAN14_G12_R32": "#009E73",
              "C5_M110": "#D55E00", "C5_FREEZE_TRAINED_W0": "#CC79A7", "C5_NO_DELAYED_PREDICTION": "#56B4E9"}
    display = {"B_TRACEABLE": "B", "CORRECTED_DSSM14_G12_R32": "DSSM", "CORRECTED_KAN14_G12_R32": "KAN",
               "C5_M110": "C5-M110", "C5_FREEZE_TRAINED_W0": "C5-freeze", "C5_NO_DELAYED_PREDICTION": "C5-no-delay"}
    bq = np.array([q_by_scene[s["scene_id"]]["B_TRACEABLE"] * 1000.0 for s in scenes])
    c5q = np.array([q_by_scene[s["scene_id"]]["C5_M110"] * 1000.0 for s in scenes])
    loss_ids = {x["scene_id"] for x in parent["all_C5_vs_B_losses"]}
    loss_mask = np.array([s["scene_id"] in loss_ids for s in scenes])
    fig, ax = plt.subplots(figsize=(5.2, 4.4), constrained_layout=True)
    ax.scatter(bq[~loss_mask], c5q[~loss_mask], s=28, color="#0072B2", alpha=.78, label="C5 wins vs B")
    ax.scatter(bq[loss_mask], c5q[loss_mask], s=72, marker="D", color="#D55E00", edgecolor="black", linewidth=.5, label="C5 losses vs B")
    lim = (0, max(float(max(bq.max(), c5q.max()) * 1.06), 1.0))
    ax.plot(lim, lim, color="#666666", linewidth=1, linestyle="--", label="equal Q")
    for i, s in enumerate(scenes):
        if loss_mask[i]:
            tag = f"{s['task']} C14 {s['wind']}"
            offset = (-68, 17) if s["task"] == "T1" else (8, -22)
            ax.annotate(tag, (bq[i], c5q[i]), xytext=offset, textcoords="offset points", fontsize=7,
                        arrowprops={"arrowstyle": "-", "color": "#555555", "lw": 0.6},
                        bbox={"boxstyle": "round,pad=0.15", "facecolor": "white", "alpha": 0.88, "linewidth": 0})
    ax.set(xlim=lim, ylim=lim, xlabel="B_TRACEABLE Q (mm)", ylabel="C5-M110 Q (mm)", title="Paired TEST48 scene Q")
    ax.legend(frameon=False, loc="upper left")
    for ext in ("png", "pdf"):
        fig.savefig(OUT / f"fig1_paired_Q_C5_vs_B.{ext}", bbox_inches="tight")
    plt.close(fig)

    groups_for_plot = ["ALL48", "HF_W09_W14", "W15"]
    fig, ax = plt.subplots(figsize=(8.0, 4.8), constrained_layout=True)
    x = np.arange(len(groups_for_plot))
    width = 0.125
    for i, method in enumerate(METHODS):
        vals = [stats["summary_groups"][g]["metrics_by_method"][method]["Q_0_20_m"]["mean"] * 1000 for g in groups_for_plot]
        ax.bar(x + (i - (len(METHODS)-1)/2) * width, vals, width, color=colors[method], label=display[method])
    ax.set_xticks(x, ["All 48", "High-frequency W09–W14", "W15"])
    ax.set_ylabel("Mean Q (mm; lower is better)")
    ax.set_title("Mean paired-design error by prespecified TEST group")
    ax.legend(frameon=False, ncol=3, loc="upper left")
    ax.grid(axis="y", color="#dddddd", linewidth=.6)
    ax.set_axisbelow(True)
    for ext in ("png", "pdf"):
        fig.savefig(OUT / f"fig2_grouped_Q_comparison.{ext}", bbox_inches="tight")
    plt.close(fig)

    all_ci = bootstrap["confidence_intervals"]["ALL48"]["contrasts_C5_minus_other"]
    ci_order = ["B_TRACEABLE", "CORRECTED_DSSM14_G12_R32", "CORRECTED_KAN14_G12_R32", "C5_NO_DELAYED_PREDICTION", "C5_FREEZE_TRAINED_W0"]
    y = np.arange(len(ci_order))
    means = np.array([all_ci[m]["mean_delta_Q_0_20_m"] * 1000 for m in ci_order])
    lows = np.array([all_ci[m]["ci95_m"][0] * 1000 for m in ci_order])
    highs = np.array([all_ci[m]["ci95_m"][1] * 1000 for m in ci_order])
    fig, ax = plt.subplots(figsize=(7.0, 4.2), constrained_layout=True)
    ax.axvline(0, color="#555555", linestyle="--", linewidth=1)
    ax.errorbar(means, y, xerr=[means-lows, highs-means], fmt="o", capsize=3, color="#0072B2", ecolor="#0072B2")
    ax.set_yticks(y, [display[m] for m in ci_order])
    ax.invert_yaxis()
    ax.set_xlabel("C5-M110 minus comparator mean Q (mm; negative favors C5)")
    ax.set_title("TEST48 scene-paired bootstrap 95% intervals")
    ax.grid(axis="x", color="#dddddd", linewidth=.6)
    ax.set_axisbelow(True)
    for ext in ("png", "pdf"):
        fig.savefig(OUT / f"fig3_paired_bootstrap_CI_ALL48.{ext}", bbox_inches="tight")
    plt.close(fig)

    # Produce a compact evidence note with exact immutable inputs and disclosed boundaries.
    all48 = stats["summary_groups"]["ALL48"]["metrics_by_method"]
    gates = parent["performance_gates"]
    b_vs = stats["C5_vs_other_methods"]["B_TRACEABLE"]
    wlt = b_vs["wlt_1e-12_m"]
    losses_b = parent["all_C5_vs_B_losses"]
    hf = stats["summary_groups"]["HF_W09_W14"]
    w15 = stats["summary_groups"]["W15"]
    task_counts = {t: stats["summary_groups"][t]["C5_vs"]["B_TRACEABLE"]["wlt_1e-12_m"] for t in ("T1", "T2", "T3")}
    exit_codes = []
    for block in raw["provenance"]["method_blocks"]:
        for field in ("natural_os_exit_receipt", "tail16_natural_os_exit_receipt", "recovery_natural_os_exit_receipt"):
            rec = block.get(field)
            if isinstance(rec, dict):
                exit_codes.append({"method": block.get("method_id"), "field": field, "code": rec.get("matlab_os_exit_code")})
    exit_summary = "; ".join(f"{r['method']}={r['code']}" + (" (DSSM tail16)" if r["field"] == "tail16_natural_os_exit_receipt" else "") for r in exit_codes)

    manifest = {
        "schema": "C5_TEST48_FINAL_RESULTS_DELIVERY_MANIFEST_V1",
        "input_files": input_meta,
        "derived_artifacts": {},
        "analysis_constraints": {
            "no_rescoring_or_bootstrap_recomputation": True,
            "bootstrap_values_copied_from_statistics_json": True,
            "dev72_kept_separate_from_test48": True,
            "historical_incident_only_read_as_incident_record": True,
            "matlab_plant_or_training_invoked": False,
        },
    }
    report = f'''# C5 TEST48 原始结果整理

## 结果

对预先登记的 48 个 TEST 场景、6 个方法的 288 条原始记录，审核器状态为 `{raw['status']}`；统计文件状态为 `{stats['status']}`。父级独立汇总复算为 `{parent['status']}`。C5-M110 的平均全程 Q 为 **{all48['C5_M110']['Q_0_20_m']['mean']*1000:.6f} mm**，B_TRACEABLE 为 **{all48['B_TRACEABLE']['Q_0_20_m']['mean']*1000:.6f} mm**；C5-M110 相对 B 为 **{wlt['wins']} 胜、{wlt['losses']} 负、{wlt['ties']} 平**。C5-M110 在高频组（high-frequency，HF W09–W14） 对 B 为 {hf['C5_vs']['B_TRACEABLE']['wlt_1e-12_m']['wins']}/{hf['n_scenes']} 胜、{hf['C5_vs']['B_TRACEABLE']['wlt_1e-12_m']['losses']} 负；W15 为 {w15['C5_vs']['B_TRACEABLE']['wlt_1e-12_m']['wins']}/{w15['n_scenes']} 胜。分任务胜负为 T1 {task_counts['T1']['wins']}/{stats['summary_groups']['T1']['n_scenes']}、T2 {task_counts['T2']['wins']}/{stats['summary_groups']['T2']['n_scenes']}、T3 {task_counts['T3']['wins']}/{stats['summary_groups']['T3']['n_scenes']}；T2 对应汇报中的 16 场中 C5 胜 15 场。

按父级审核中列出的四项预设表现检查（至少 41 胜、总体均值低于 B、高频组不高于 B、W15 不高于 B），四项均通过：`{gates}`。该结果是固定仿真设计下的配对统计；`paper_result_qualified` 为 `{parent['paper_result_qualified']}`，不能据此宣称论文证据门已达标。

C5-M110 对 B 的两场输场为：{losses_b[0]['scene_id']}（差 {losses_b[0]['delta_m']*1000:.6f} mm）和 {losses_b[1]['scene_id']}（差 {losses_b[1]['delta_m']*1000:.6f} mm）。完整的全部 comparator 输场见 `C5_M110_losses_all_comparators.csv`。1 µm 与 10 µm ties 敏感性见 `paired_sensitivity_wlt_1_10um.csv`；配对场景 bootstrap 区间直接取自冻结统计 JSON，未在本整理中重采样。

## 配对统计与复算边界

bootstrap 使用 10,000 次有放回的场景配对抽样，seed={bootstrap['seed']}，在每组内抽样并让各 comparator 共用索引；区间为场景等权平均配对 Q 差的 2.5% 与 97.5% quantile（`{bootstrap['interval']}`）。这些区间只描述当前固定仿真设计，不作多重比较校正，也不代表跨训练 seed 的推断。DEV72 汇总单列为上下文对照，不与 TEST48 合并。

完整长表 `paired_complete_48x6_long.csv` 保留 288 条原始审核指标及路径、SHA 和外部身份指纹；`paired_Q_48x6_wide_mm.csv` 提供 48×6 的配对主指标。`task_wind_axis_safety_saturation_timing_summary.csv` 包含任务、各风组及风组分箱上的逐方法均值，距离单位为 mm、计时单位为 ms、占比为 fraction；`axis_early_late_summary.csv` 给出全程/早段 0–5 s/后段 5–20 s 的逐轴 RMSE。图 1 标记了 C5 对 B 的两场输场；图 2 比较整体、高频组和 W15；图 3 展示 ALL48 配对区间。

## 审核限制与历史暴露披露

原始 DSSM 全 48 场进程的自然退出记录为 UNKNOWN；scene32 缺少 `runIdentity`；历史六进程 OS0 gate 为 UNMET。恢复后的 DSSM tail16 有 OS0 退出凭据，B 与 KAN/C5 恢复方法块的自然退出码为 0（{exit_summary}）。因此不把全 DSSM 原运行改称 OS0，也不把历史 gate 重新分类。

历史 incident 记录称，两条旧 TEST 场景摘要曾被意外展示。该记录同时称 C5 模型与选择在本分支接触该摘要前已冻结，当前 TEST48 性能未被用于本分支选型；与当前 TEST48 的物理场景重叠 **UNKNOWN**。此处仅引用 incident 事实，未读取或复制旧混合报告的任何指标。故不声称历史上从未看到任何 TEST 信息。当前结果是已冻结 C5-M110 对这次 48 场仿真的审核统计；不构成新实机验证或跨 seed 泛化证明。C6 仍为冻结的 DEV 实验，不应依据本次两场 TEST 输场挑场或调参。

## 输入、源码与可复算命令

输入与源码 SHA-256 固定在 `INPUT_MANIFEST_v1.json`。原始审核 JSON：`{input_meta['raw_audit']['sha256']}`；统计 JSON：`{input_meta['statistics']['sha256']}`；父级独立复核：`{input_meta['parent_review']['sha256']}`；DEV72 CSV：`{input_meta['dev72']['sha256']}`；历史 incident：`{input_meta['historical_incident']['sha256']}`。审核器源码 SHA-256：`{input_meta['raw_audit_source']['sha256']}`；统计器源码 SHA-256：`{input_meta['statistics_source']['sha256']}`。

PowerShell 7 中从仓库根目录复算整理产物：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:OPENBLAS_NUM_THREADS='1'
$env:OMP_NUM_THREADS='1'
python reports/paper_continuation_20261023/test_results_final_v1/build_test_results_final_v1.py
```

脚本会校验所有固定输入 SHA；只整理既有 JSON/CSV、做单位换算并生成图表，不调用 MATLAB/Plant、不重算评分或 bootstrap。
'''
    (OUT / "RESULTS_REPORT_ZH.md").write_text(report, encoding="utf-8")
    (OUT / "INPUT_MANIFEST_v1.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Hash all generated files except the manifest itself; then write final manifest.
    for p in sorted(OUT.iterdir()):
        if p.is_file() and p.name != "INPUT_MANIFEST_v1.json":
            manifest["derived_artifacts"][p.name] = {"sha256": sha256(p), "bytes": p.stat().st_size}
    (OUT / "INPUT_MANIFEST_v1.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output_dir": str(OUT), "outputs": manifest["derived_artifacts"],
                      "loss_rows_all_comparators": len(loss_rows), "group_rows": len(group_rows), "bootstrap_ci_rows": len(ci_rows),
                      "dev_rows": len(dev)}, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()




