from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "experiments/training_data_structure_compare_v2"
FAMILIES = ("MIXED_KAN", "TEACHER_KAN", "DEEP_KAN", "HISTORY_KAN", "WIDE_MLP")


def main() -> None:
    frames = []
    for family in FAMILIES:
        path = OUT / "reports" / f"D5_BRIDGE6_{family}.csv"
        frame = pd.read_csv(path)
        if len(frame) != 6 or frame.scene_id.nunique() != 6:
            raise RuntimeError(f"{family} must contain exactly six unique BRIDGE6 scenes")
        frame["candidate_family"] = family
        frames.append(frame)
    paired = pd.concat(frames, ignore_index=True)
    paired.to_csv(OUT / "reports" / "CANARY_PAIRED.csv", index=False)

    mixed = paired[paired.candidate_family == "MIXED_KAN"]
    mixed_macro = float(mixed.Q_0_20_m.mean())
    final_macro = float(mixed.Final_Q_0_20_m.mean())
    summary = []
    by_task = []
    for family in FAMILIES:
        d = paired[paired.candidate_family == family].copy()
        task = d.groupby("task", sort=False).agg(
            candidate_A=("A_0_20_rad", "mean"), B_A=("B_A_0_20_rad", "mean"),
            candidate_Q=("Q_0_20_m", "mean"), B_Q=("B_Q_0_20_m", "mean"),
            Final_Q=("Final_Q_0_20_m", "mean"),
        )
        task["pose_limit_rad"] = 1.10 * task.B_A + 0.002
        task["pose_guard_pass"] = task.candidate_A <= task.pose_limit_rad
        for name, row in task.iterrows():
            by_task.append({"candidate_family": family, "task": name, **row.to_dict()})
        q = float(d.Q_0_20_m.mean())
        q_vs_mixed = q - mixed_macro
        q_vs_final = q - final_macro
        complete = bool(d.status.eq("STABLE").all() and d.complete.all() and d.finite.all() and
                        d.transitions.eq(20_000).all())
        saturation = bool((d.motor_saturation_fraction <= 0.005).all())
        clipping = bool((d.generalized_clip_fraction <= 0.005).all())
        timing = bool((d.controller_p99_ms < 10).all())
        pose = bool(task.pose_guard_pass.all())
        beats_required = q < final_macro if family == "MIXED_KAN" else (q < mixed_macro and q < final_macro)
        metrics_gate = bool(complete and pose and saturation and clipping and timing and beats_required)
        fit_complete = bool(d.fit_status.eq("COMPLETE").all())
        summary.append({
            "candidate_family": family,
            "seed": int(d.seed.iloc[0]),
            "fit_status": str(d.fit_status.iloc[0]),
            "selected_step": int(d.selected_step.iloc[0]),
            "bridge_runs": len(d),
            "all_stable_complete_finite": complete,
            "macro_Q_0_20_m": q,
            "macro_B_Q_0_20_m": float(d.B_Q_0_20_m.mean()),
            "macro_Initial_Q_0_20_m": float(d.Initial_Q_0_20_m.mean()),
            "macro_Final_Q_0_20_m": float(d.Final_Q_0_20_m.mean()),
            "delta_macro_Q_vs_MIXED_m": q_vs_mixed,
            "delta_macro_Q_vs_Final_m": q_vs_final,
            "scenes_beating_B": int((d.delta_Q_vs_B_m < 0).sum()),
            "scenes_beating_Final": int((d.delta_Q_vs_Final_m < 0).sum()),
            "macro_A_0_20_rad": float(d.A_0_20_rad.mean()),
            "macro_B_A_0_20_rad": float(d.B_A_0_20_rad.mean()),
            "per_task_pose_guard_pass": pose,
            "max_motor_saturation_fraction": float(d.motor_saturation_fraction.max()),
            "max_generalized_clip_fraction": float(d.generalized_clip_fraction.max()),
            "max_controller_p99_ms": float(d.controller_p99_ms.max()),
            "max_inference_p99_ms": float(d.inference_p99_s.max() * 1000),
            "max_inference_single_event_ms": float(d.inference_max_s.max() * 1000),
            "inference_events_over_10ms": int(d.inference_over_10ms_count.sum()),
            "parameter_fit_complete": fit_complete,
            "meets_canary_metrics_gate": metrics_gate,
        })

    summary_frame = pd.DataFrame(summary)
    summary_frame.to_csv(OUT / "reports" / "CANARY_SUMMARY.csv", index=False)
    pd.DataFrame(by_task).to_csv(OUT / "reports" / "CANARY_POSE_GUARD_BY_TASK.csv", index=False)

    history = summary_frame[summary_frame.candidate_family == "HISTORY_KAN"].iloc[0]
    winners = summary_frame[summary_frame.meets_canary_metrics_gate]
    if len(winners) != 1 or winners.iloc[0].candidate_family != "HISTORY_KAN":
        raise RuntimeError(f"Unexpected canary qualification set: {winners.candidate_family.tolist()}")
    decision = {
        "status": "ADVANCE_FROZEN_HISTORY_CHECKPOINT_TO_EXPLORATORY_DEV",
        "selected_family": "HISTORY_KAN",
        "seed": 2026101911,
        "selected_step": 15000,
        "training_complete": False,
        "training_status": "PAUSED_BY_USER at 18000/60000; selected best checkpoint step 15000",
        "macro_Q_0_20_m": float(history.macro_Q_0_20_m),
        "macro_Q_vs_MIXED_m": float(history.delta_macro_Q_vs_MIXED_m),
        "macro_Q_vs_Final_m": float(history.delta_macro_Q_vs_Final_m),
        "per_task_pose_guard_pass": bool(history.per_task_pose_guard_pass),
        "new_dev_plant_starts_budget": 48,
        "original_G06_modified": False,
        "notes": [
            "History KAN is not a completed 60000-step fit; it advances only as the user-requested frozen-checkpoint exploratory candidate.",
            "The user-paused fit is not resumed. No second seed is run.",
            "The six-scene bridge is development evidence from previously seen TRAIN conditions, not generalization evidence.",
            "The original G06 failure remains unchanged; DEV results are written only to this experiment directory.",
        ],
    }
    (OUT / "reports" / "CANARY_MECHANISM_DECISION.json").write_text(
        json.dumps(decision, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = [
        "# BRIDGE6 同场决策",
        "",
        "## 预先规定的门槛",
        "",
        "六场全部 stable/complete/finite；六场宏观位置 RMSE 优于同期 MIXED_KAN 与原 Final；按任务平均姿态满足 A ≤ 1.10×B + 0.002 rad；无明显饱和/裁剪；控制器 p99 < 10 ms。原 G06 记录不改写。",
        "",
        "## 候选汇总",
        "",
        "| 候选 | 选中步 | 宏观 Q (m) | 同期 MIXED Q (m) | 原 Final Q (m) | 对 B 胜场 | 每任务姿态护栏 | 60k 拟合完成 |",
        "|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for r in summary:
        lines.append(f"| {r['candidate_family']} | {r['selected_step']} | {r['macro_Q_0_20_m']:.6f} | "
                     f"{mixed_macro:.6f} | {final_macro:.6f} | {r['scenes_beating_B']}/6 | "
                     f"{'通过' if r['per_task_pose_guard_pass'] else '未通过'} | "
                     f"{'是' if r['parameter_fit_complete'] else '否'} |")
    lines += [
        "",
        "宏观 Q 是六个固定场景的等权均值；每场细节见 `CANARY_PAIRED.csv`，按任务姿态护栏见 `CANARY_POSE_GUARD_BY_TASK.csv`。",
        "",
        "## 决策",
        "",
        f"History KAN 的六场宏观 Q 为 {history.macro_Q_0_20_m:.6f} m，比同期 MIXED_KAN 低 {-history.delta_macro_Q_vs_MIXED_m:.6f} m，比原 Final 低 {-history.delta_macro_Q_vs_Final_m:.6f} m；三个任务姿态护栏均通过，6/6 稳定完整有限。它是唯一达到 canary 数值门槛的候选。",
        "",
        "限制：该模型来自用户要求暂停的 HISTORY_KAN_SEED2026101911，拟合停在 18k/60k，选用最佳 step 15k checkpoint。按用户指示不恢复训练；因此它不伪装成完整正式 fit，而冻结该快照进入隔离的探索性 DEV。MLP 为用户额外要求的随机初始化探索候选，不能当作函数保持结构对照。",
        "",
        "History KAN 在六场只赢 B 2/6；进入 DEV 的依据是预注册的宏观改善门槛，不要求每场赢 B。所有六场都高于 B 的平均范围，故当前证据仍不支持替代 B。DEV 将用原 24 场、同时评价 P_F/P_A，并保持 48 次预算上限。",
        "",
        "## 逐场输出",
        "",
        "每场的 Q、B、Initial、Final、姿态、峰值、饱和、推理耗时与原始轨迹路径均保存在 `CANARY_PAIRED.csv` 及各模型的 `D5_BRIDGE6_<FAMILY>.csv`。",
    ]
    (OUT / "reports" / "CANARY_MECHANISM_DECISION.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(summary_frame[["candidate_family", "macro_Q_0_20_m", "delta_macro_Q_vs_MIXED_m",
                         "delta_macro_Q_vs_Final_m", "scenes_beating_B", "per_task_pose_guard_pass",
                         "parameter_fit_complete", "meets_canary_metrics_gate"]].to_string(index=False))
    print(json.dumps(decision, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
