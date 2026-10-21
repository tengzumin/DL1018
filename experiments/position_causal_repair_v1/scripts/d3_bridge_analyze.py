from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "experiments" / "position_causal_repair_v1"
TIME_BINS = ("T_0_1p8", "T_1p8_5", "T_5_10", "T_10_15", "T_15_20")
COMPONENTS = ("d_wind", "d_allocation", "d_attitude_realization", "d_mapping", "d_effective", "d_applied")


def time_values(raw: str) -> dict[str, float]:
    d = json.loads(raw)
    return {k: float(v["Q_rmse_m"]) for k, v in d.items()}


def vector_rms(frame: pd.DataFrame, prefix: str) -> float:
    cols = [f"{prefix}_{axis}_mps2" for axis in "xyz"]
    return float(np.sqrt(np.mean(np.sum(frame[cols].to_numpy(float) ** 2, axis=1))))


def safe_round(v: float, n: int = 6) -> float:
    return round(float(v), n)


def main() -> None:
    d1 = pd.read_csv(OUT / "reports/D1_G04_PAIRED_ALL.csv")
    final = pd.read_csv(OUT / "reports/D3_FINAL_INITIAL_BRIDGE_MATLAB.csv")
    comps = pd.read_csv(OUT / "reports/D3_FINAL_LABEL_COMPONENTS.csv")
    hist = pd.read_csv(OUT / "reports/D2_LABEL_COMPONENTS.csv")
    scenes = final.scene_id.tolist()
    assert len(scenes) == 6 and len(set(scenes)) == 6
    assert set(scenes) <= set(d1.scene_id)
    assert (final.status == "STABLE").all() and final.complete.astype(bool).all() and final.finite.astype(bool).all()

    joined: list[dict] = []
    for _, fr in final.iterrows():
        sid = fr.scene_id
        old = d1.loc[d1.scene_id == sid].iloc[0]
        tb = time_values(old.P_INIT_STUDENT_time_bin_metrics_json)
        ftb = json.loads(fr.time_bin_Q_json)
        row = {
            "scene_id": sid, "task": old.task, "class_id": int(old.class_id), "wind_cell": int(old.wind_cell),
            "status_final": fr.status, "complete_final": bool(fr.complete), "finite_final": bool(fr.finite),
            "B_Q_0_20_m": old.B_Q_0_20_m, "POS_OFF_Q_0_20_m": old.POS_OFF_Q_0_20_m,
            "Initial_Q_0_20_m": old.P_INIT_STUDENT_Q_0_20_m, "Final_Q_0_20_m": fr.Q_0_20_m,
            "Initial_minus_B_Q_m": old.P_INIT_minus_B_Q_0_20_m,
            "Final_minus_Initial_Q_m": fr.Q_0_20_m - old.P_INIT_STUDENT_Q_0_20_m,
            "Final_minus_B_Q_m": fr.Q_0_20_m - old.B_Q_0_20_m,
            "Final_minus_POS_OFF_Q_m": fr.Q_0_20_m - old.POS_OFF_Q_0_20_m,
            "Final_beats_Initial_Q": bool(fr.Q_0_20_m < old.P_INIT_STUDENT_Q_0_20_m),
            "Final_beats_B_Q": bool(fr.Q_0_20_m < old.B_Q_0_20_m),
            "B_A_0_20_rad": old.B_A_0_20_rad, "Initial_A_0_20_rad": old.P_INIT_STUDENT_A_0_20_rad,
            "Final_A_0_20_rad": fr.A_0_20_rad, "Final_minus_Initial_A_rad": fr.A_0_20_rad - old.P_INIT_STUDENT_A_0_20_rad,
            "Final_minus_B_A_rad": fr.A_0_20_rad - old.B_A_0_20_rad,
            "B_axis_rmse_x_m": old.B_axis_rmse_x_m, "B_axis_rmse_y_m": old.B_axis_rmse_y_m,
            "B_axis_rmse_z_m": old.B_axis_rmse_z_m,
            "Initial_axis_rmse_x_m": old.P_INIT_STUDENT_axis_rmse_x_m,
            "Initial_axis_rmse_y_m": old.P_INIT_STUDENT_axis_rmse_y_m,
            "Initial_axis_rmse_z_m": old.P_INIT_STUDENT_axis_rmse_z_m,
            "Final_axis_rmse_x_m": fr.axis_rmse_x_m, "Final_axis_rmse_y_m": fr.axis_rmse_y_m,
            "Final_axis_rmse_z_m": fr.axis_rmse_z_m, "Final_position_peak_m": fr.position_peak_m,
            "Final_position_p95_m": fr.position_p95_m, "Final_motor_TV_normalized_per_s": fr.motor_TV_normalized_per_s,
            "Final_motor_saturation_fraction": fr.motor_saturation_fraction,
            "Final_generalized_clip_fraction": fr.generalized_clip_fraction,
            "transitions": int(fr.transitions), "run_id": fr.run_id, "raw_path": fr.raw_path,
        }
        initial_bins = time_values(old.P_INIT_STUDENT_time_bin_metrics_json)
        baseline_bins = time_values(old.B_time_bin_metrics_json)
        final_bins = {k: float(ftb[k]) for k in TIME_BINS}
        for b in TIME_BINS:
            row[f"B_{b}_Q_m"] = baseline_bins[b]
            row[f"Initial_{b}_Q_m"] = initial_bins[b]
            row[f"Final_{b}_Q_m"] = final_bins[b]
            row[f"Final_minus_Initial_{b}_Q_m"] = final_bins[b] - initial_bins[b]
            row[f"Final_minus_B_{b}_Q_m"] = final_bins[b] - baseline_bins[b]
        joined.append(row)

    bridge = pd.DataFrame(joined)
    bridge.to_csv(OUT / "reports/D3_INITIAL_FINAL_BRIDGE.csv", index=False, float_format="%.12g")

    # Compare causal residual components on matching recorded event indices.
    final_records: list[dict] = []
    comp_rows: list[dict] = []
    for sid in scenes:
        f = comps.loc[comps.scene_id == sid].sort_values("event_index").copy()
        i = hist.loc[(hist.scene_id == sid) & (hist.role == "P_INIT_STUDENT")].sort_values("event_index").copy()
        i["time_bin"] = pd.cut(i.time_s, bins=[0.0, 1.8, 5.0, 10.0, 15.0, 20.0],
                               labels=TIME_BINS, right=False, include_lowest=True).astype("string")
        assert len(f) == len(i) == 1999, (sid, len(f), len(i))
        assert np.array_equal(f.event_index.to_numpy(), i.event_index.to_numpy())
        assert np.array_equal(f.plant_index.to_numpy(), i.plant_index.to_numpy())
        assert np.max(np.abs(f.time_s.to_numpy(float) - i.time_s.to_numpy(float))) <= 1e-12
        paired = f.merge(i, on=["scene_id", "event_index", "plant_index"], suffixes=("_Final", "_Initial"), validate="one_to_one")
        for role, g in (("Initial", i), ("Final", f)):
            for b, gb in g.groupby("time_bin" if role == "Final" else "time_bin", sort=False):
                if b == "OUTSIDE":
                    continue
                for c in COMPONENTS:
                    comp_rows.append({"scene_id": sid, "role": role, "time_bin": b, "component": c,
                                      "vector_rms_mps2": vector_rms(gb, c), "events": len(gb)})
            for c in COMPONENTS:
                final_records.append({"scene_id": sid, "role": role, "time_bin": "ALL_READY", "component": c,
                                      "vector_rms_mps2": vector_rms(g, c), "events": len(g)})
        for b, gb in paired.groupby("time_bin_Final", sort=False):
            if b == "OUTSIDE":
                continue
            for c in COMPONENTS:
                left = [f"{c}_{axis}_mps2_Final" for axis in "xyz"]
                right = [f"{c}_{axis}_mps2_Initial" for axis in "xyz"]
                final_r = float(np.sqrt(np.mean(np.sum(gb[left].to_numpy(float) ** 2, axis=1))))
                initial_r = float(np.sqrt(np.mean(np.sum(gb[right].to_numpy(float) ** 2, axis=1))))
                final_records.append({"scene_id": sid, "role": "Final_minus_Initial", "time_bin": b,
                                      "component": c, "vector_rms_mps2": final_r - initial_r, "events": len(gb)})

    csummary = pd.DataFrame(final_records)
    csummary.to_csv(OUT / "reports/D3_COMPONENT_SUMMARY.csv", index=False, float_format="%.12g")
    allcomp = pd.DataFrame(comp_rows)
    allcomp.to_csv(OUT / "reports/D3_COMPONENT_BY_SCENE_TIME.csv", index=False, float_format="%.12g")

    # Persist event-paired residual and state evidence so the six-scene comparisons are reproducible.
    pair_cols = ["scene_id", "event_index", "plant_index", "time_s_Final", "time_s_Initial", "time_bin_Final"]
    for c in COMPONENTS:
        for axis in "xyz":
            pair_cols.extend([f"{c}_{axis}_mps2_Final", f"{c}_{axis}_mps2_Initial"])
    pair_rows = []
    for sid in scenes:
        f = comps.loc[comps.scene_id == sid].sort_values("event_index")
        i = hist.loc[(hist.scene_id == sid) & (hist.role == "P_INIT_STUDENT")].sort_values("event_index").copy()
        i["time_bin"] = pd.cut(i.time_s, bins=[0.0, 1.8, 5.0, 10.0, 15.0, 20.0],
                               labels=TIME_BINS, right=False, include_lowest=True).astype("string")
        pair_rows.append(f.merge(i, on=["scene_id", "event_index", "plant_index"], suffixes=("_Final", "_Initial"), validate="one_to_one")[pair_cols])
    pd.concat(pair_rows, ignore_index=True).to_csv(OUT / "reports/D3_PAIRED_EVENT_COMPONENTS.csv", index=False, float_format="%.12g")

    # Compact figures with paired scene and time-window evidence.
    plt.figure(figsize=(10, 5.5))
    x = np.arange(len(bridge)); w = .25
    plt.bar(x - w, bridge.B_Q_0_20_m, width=w, label="B")
    plt.bar(x, bridge.Initial_Q_0_20_m, width=w, label="Initial")
    plt.bar(x + w, bridge.Final_Q_0_20_m, width=w, label="Final")
    plt.xticks(x, [s.replace("DL1018_TRAIN_", "") for s in bridge.scene_id], rotation=25, ha="right")
    plt.ylabel("Position RMSE, 0–20 s (m)"); plt.legend(); plt.tight_layout()
    plt.savefig(OUT / "figures/D3_BRIDGE6_PAIRED_Q.png", dpi=180); plt.close()

    time_summary = []
    for b in TIME_BINS:
        time_summary.append({"time_bin": b, "B_Q_m": bridge[f"B_{b}_Q_m"].mean(),
                             "Initial_Q_m": bridge[f"Initial_{b}_Q_m"].mean(),
                             "Final_Q_m": bridge[f"Final_{b}_Q_m"].mean(),
                             "Final_minus_Initial_Q_m": bridge[f"Final_minus_Initial_{b}_Q_m"].mean(),
                             "Final_better_than_Initial_scenes": int((bridge[f"Final_minus_Initial_{b}_Q_m"] < 0).sum())})
    ts = pd.DataFrame(time_summary)
    ts.to_csv(OUT / "reports/D3_TIMEBIN_SUMMARY.csv", index=False, float_format="%.12g")
    plt.figure(figsize=(8.5, 4.8))
    x = np.arange(len(ts)); w = .25
    plt.bar(x - w, ts.B_Q_m, width=w, label="B")
    plt.bar(x, ts.Initial_Q_m, width=w, label="Initial")
    plt.bar(x + w, ts.Final_Q_m, width=w, label="Final")
    plt.xticks(x, ts.time_bin, rotation=20, ha="right"); plt.ylabel("Mean paired time-bin position RMSE (m)")
    plt.legend(); plt.tight_layout(); plt.savefig(OUT / "figures/D3_BRIDGE6_TIMEBINS.png", dpi=180); plt.close()

    def macro(col: str) -> float:
        return float(bridge[col].mean())

    mean_delta = macro("Final_minus_Initial_Q_m")
    wins = int(bridge.Final_beats_Initial_Q.sum())
    mean_delta_b = macro("Final_minus_B_Q_m")
    wins_b = int(bridge.Final_beats_B_Q.sum())
    attitude_delta = macro("Final_minus_Initial_A_rad")
    comp_all = csummary.loc[csummary.time_bin == "ALL_READY"]
    comp_means = comp_all.groupby("role").apply(lambda g: dict(zip(g.component, g.vector_rms_mps2)), include_groups=False).to_dict()

    lines = [
        "# D3：六场 Initial/Final 同场桥接",
        "",
        "本阶段在预登记 BRIDGE6 上实际运行 Selected Final 的 P_A 在线模式；新增 Plant=6，六场均 STABLE、20,000 transitions、finite。其余 B、POS_OFF、Initial 均来自相同 scene_id 的历史配对记录。六场场景数组、初始状态、风、参考、臂命令、冻结 cfg/C0、姿态 RBF 与 selected model 身份在 Plant 前逐项核验；预检零 Plant 通过。",
        "",
        "## 直接结果",
        "",
        f"- Final 相对 Initial：等场宏 Q **{macro('Initial_Q_0_20_m'):.6f} → {macro('Final_Q_0_20_m'):.6f} m**，平均变化 **{mean_delta:+.6f} m**；Final 在 **{wins}/6** 场胜 Initial。",
        f"- Final 相对 B：等场宏 Q **{macro('B_Q_0_20_m'):.6f} → {macro('Final_Q_0_20_m'):.6f} m**，平均变化 **{mean_delta_b:+.6f} m**；Final 仅在 **{wins_b}/6** 场胜 B。Initial 在这六场的宏 Q 为 **{macro('Initial_Q_0_20_m'):.6f} m**。",
        f"- 姿态宏 A：B **{macro('B_A_0_20_rad'):.6f}**、Initial **{macro('Initial_A_0_20_rad'):.6f}**、Final **{macro('Final_A_0_20_rad'):.6f} rad**；Final−Initial **{attitude_delta:+.6f} rad**。",
        "- 六场都是稳定完成；位置差异不是由某一场物理硬停造成。下面位置 RMSE 是逐场 0–20 s 单条指标；宏值只是六场等权汇总。",
        "",
        "## 每场配对结果",
        "",
        "| Scene | Task | Wind | B Q | Initial Q | Final Q | Final−Initial | Final A | Δ Final−Initial A | Final vs B |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for _, r in bridge.iterrows():
        lines.append(f"| {r.scene_id} | {r.task} | {int(r.wind_cell)} | {r.B_Q_0_20_m:.6f} | {r.Initial_Q_0_20_m:.6f} | {r.Final_Q_0_20_m:.6f} | {r.Final_minus_Initial_Q_m:+.6f} | {r.Final_A_0_20_rad:.6f} | {r.Final_minus_Initial_A_rad:+.6f} | {'胜' if r.Final_beats_B_Q else '负'} |")
    lines += ["", "## 差异出现时段", "", "| 时段 | B 宏 Q | Initial 宏 Q | Final 宏 Q | Final−Initial | Final 胜 Initial |", "|---|---:|---:|---:|---:|---:|"]
    for _, r in ts.iterrows():
        lines.append(f"| {r.time_bin} | {r.B_Q_m:.6f} | {r.Initial_Q_m:.6f} | {r.Final_Q_m:.6f} | {r.Final_minus_Initial_Q_m:+.6f} | {int(r.Final_better_than_Initial_scenes)}/6 |")
    lines += ["", "## 同轨迹残差分量 RMS", "", "分量 RMS 按三个轴合成 `sqrt(mean(sum(component^2,axis=1)))`；不同分量含交叉项，不能把 RMS 直接相加。Final/Initial 的状态轨迹不同，因此分量变化是同场、实际闭环下的关联证据，不是独立干预效应。", "", "| Component | Initial RMS | Final RMS | Final−Initial |", "|---|---:|---:|---:|"]
    for c in COMPONENTS:
        a = float(comp_all.loc[comp_all.role == "Initial"].query("component == @c").vector_rms_mps2.mean())
        b = float(comp_all.loc[comp_all.role == "Final"].query("component == @c").vector_rms_mps2.mean())
        lines.append(f"| {c} | {a:.6f} | {b:.6f} | {b-a:+.6f} |")
    lines += ["", "## 定位边界与含义", "", "- D1 已显示 Initial 在多数 G04 场景优于 POS_OFF，但明显落后 B；D3 若 Final 与 Initial 接近或更差，不能把全部差距归因于 Final warm-fit。", "- 该桥接控制了同一场景/C0/姿态环，只切换位置学生完整 Initial/Final 包，故可回答这六场实际闭环中的 Final→Initial 总体效应；它不能单独分离权重重训、归一化、校准、epoch 选择等完整包内变化。", "- D2 的运行链重放/H5 重导出未发现已抽查运行的标签、Head 更新、PCF、ZOH、beta 或力质量闭合错误；仍限定为抽查样本，不扩写成全历史无错误。", "- 残差组件按真实动力学恒等式闭合，最大误差记录在 `D3_COMPONENT_EXPORT.json`；不同轨迹会改变姿态实现、风、分配等项，所以这些分量用于定位实际差异，不自动构成单一机制的因果证明。", "- 完整逐场/分时/分轴数据见 `D3_INITIAL_FINAL_BRIDGE.csv`、`D3_COMPONENT_SUMMARY.csv`、`D3_COMPONENT_BY_SCENE_TIME.csv`、`D3_PAIRED_EVENT_COMPONENTS.csv` 和 D3 图。", ""]
    (OUT / "reports/D3_INITIAL_FINAL_BRIDGE.md").write_text("\n".join(lines), encoding="utf-8")

    summary = {
        "phase": "D3_COMPLETE", "scenes": len(bridge), "new_plant_starts": 6,
        "all_stable": bool((bridge.status_final == "STABLE").all()),
        "macro_Q_B_m": macro("B_Q_0_20_m"), "macro_Q_initial_m": macro("Initial_Q_0_20_m"),
        "macro_Q_final_m": macro("Final_Q_0_20_m"), "final_vs_initial_delta_m": mean_delta,
        "final_beats_initial": wins, "final_beats_B": wins_b,
        "macro_A_B_rad": macro("B_A_0_20_rad"), "macro_A_initial_rad": macro("Initial_A_0_20_rad"),
        "macro_A_final_rad": macro("Final_A_0_20_rad"), "component_label_closure_max_mps2": 2.7027e-15,
    }
    (OUT / "state/D3_SUMMARY.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    state_path = OUT / "state/state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state.update({"phase": "D3_COMPLETE", "status": "IN_PROGRESS", "next": "D3_CAUSE_MATRIX_AND_D4_BRANCH",
                  "d3_completed_runs": 6, "d3_plant_starts_new": 6,
                  "active_run_id": None, "updated_at_utc": pd.Timestamp.now(tz="UTC").isoformat()})
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
