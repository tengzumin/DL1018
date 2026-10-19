from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "experiments" / "position_causal_repair_v1"


def main() -> None:
    comparison = OUT / "reports/D4_TRAINING_COMPARISON.csv"
    rows = pd.read_csv(comparison, keep_default_na=False).to_dict("records")
    g05 = json.loads((ROOT / "reports/G05_P_FINAL.json").read_text(encoding="utf-8"))
    c0_detail = g05["checks"]["score_detail"]
    c0 = {
        "family": "C0_X14_FIXED_CONTROL", "seed": 2026101802,
        "status": "REUSED_G05_FINAL", "input_dim": 14,
        "best_epoch": g05["checks"]["best_epoch"],
        "train_windows": g05["actual_counts"]["train_windows"],
        "val_windows": g05["actual_counts"]["val_windows"],
        "optimizer_steps_total": 20 * 2955,
        "loss_endpoint_exposures": 20 * 756480,
        "recurrent_event_exposures": 0,
        "val_fixed_score": c0_detail["score_mps2"],
        "val_adaptive_score": "", "val_selected_score": c0_detail["score_mps2"],
        "best_val_detail_json": json.dumps(c0_detail, separators=(",", ":")),
        "training_seconds": "", "model_path": "models/position/final_candidate/best_model.pt",
        "normalizer_path": "models/position/final_candidate/normalizer.npz",
    }
    rows = [r for r in rows if r.get("family") != c0["family"]]
    rows.insert(0, c0)
    pd.DataFrame(rows).to_csv(comparison, index=False)

    reports = []
    for family in ("C1_X20_FIXED_INFORMATION", "C2_X14_ADAPTATION_AWARE"):
        for seed in (2026101901, 2026101902):
            p = OUT / "models" / family / f"seed{seed}" / "fit_report.json"
            r = json.loads(p.read_text(encoding="utf-8"))
            if r.get("status") != "COMPLETE":
                raise RuntimeError(f"D4 fit incomplete: {p}")
            reports.append(r)
    if len(reports) != 4:
        raise AssertionError("D4 fit count must be four: two seeds for C1 and C2")

    lines = [
        "# D4 修复候选训练与选择",
        "",
        "## 控制组与候选",
        "",
        "C0 复用 G05 Final：训练协议、TRAIN/VAL 角色与权重、X14 N_KAN、Initial warm start、优化器、预算、stride 和 756,480/56,736 计数均一致；G05 的 MATLAB 导出 parity 为 PASS。C0 的 VAL 固定头分数为 **%.6f m/s²**。" % c0_detail["score_mps2"],
        "",
        "C1 两个 seed 均从 DL1018 Initial X14 初始化，只新增 `v_I_xyz` 与 `a_nom_xyz` 六列；原 14 列归一化保留，新列统计仅来自 TRAIN。训练前 X20 的 φ 和输出与 X14 最大差均为 0。固定头 VAL 分数按冻结规则选 epoch。",
        "",
        "| Candidate | Seed | Best epoch | TRAIN/VAL windows | Optimizer steps | Endpoint exposures | Fixed VAL (m/s²) | Adaptive VAL (m/s²) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
        "| C0 reused G05 Final | 2026101802 | 12 | 756480 / 56736 | 59100 (historical 20 epochs) | 15129600 | %.6f | n/a |" % c0_detail["score_mps2"],
    ]
    for r in reports:
        family = "C1 X20 fixed" if r["family"].startswith("C1") else "C2 X14 adaptation-aware"
        fixed = "n/a" if r["val_fixed_score"] is None else f"{r['val_fixed_score']:.6f}"
        adaptive = "n/a" if r["val_adaptive_score"] is None else f"{r['val_adaptive_score']:.6f}"
        lines.append(f"| {family} | {r['seed']} | {r['best_epoch']} | {r['train_windows']} / {r['val_windows']} | {r['optimizer_steps_total']} | {r['loss_endpoint_exposures']} | {fixed} | {adaptive} |")
    c1 = [r for r in reports if r["family"].startswith("C1")]
    c2 = [r for r in reports if r["family"].startswith("C2")]
    lines += [
        "",
        "C2 每条 TRAIN episode 的 W 从共享可学习 W0 重置；每条 1,968 个 ready 事件均按原 100Hz 递推，stride 5 只抽稀损失端点。C2 训练目标是**记录轨迹上的适应导向训练**，不是完整可微闭环。两个 seed 的递推投影回退数均为 0。固定 W0 与适应后分数分开列出，依任务书仅用适应 VAL 选择 C2 epoch。",
        "",
        "| Candidate | Seed | Best epoch | Optimizer steps | Loss endpoint exposures | Recurrence event exposures | Fixed W0 VAL | Adaptive VAL | Projection fallback sequences |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in c2:
        lines.append(f"| C2 | {r['seed']} | {r['best_epoch']} | {r['optimizer_steps_total']} | {r['loss_endpoint_exposures']} | {r['recurrent_event_exposures']} | {r['val_fixed_score']:.6f} | {r['val_adaptive_score']:.6f} | {r['projection_fallback_sequences_total']} |")
    lines += [
        "",
        "## 冻结选择及解释边界",
        "",
        "- 预定飞行 seed 为 2026101901；2026101902 只做方向复核，不因结果更好而替换。",
        "- C1 seed1 固定 VAL 0.272568，seed2 0.273048，方向一致；相对 C0 的同口径 VAL 有改善，支持进入 D5，但不能据离线分数宣称闭环改善。",
        "- C2 seed1/seed2 的适应 VAL 分别为 %.6f / %.6f；C2 固定 W0 分别为 %.6f / %.6f。两个 seed 适应分数方向一致；固定 W0 与适应分数、C1/C0 与 C2 的不同目标不能混作同一指标排名。" % (c2[0]["val_adaptive_score"], c2[1]["val_adaptive_score"], c2[0]["val_fixed_score"], c2[1]["val_fixed_score"]),
        "- 因 D2 的 early-ridge 只在记录轨迹上显示可适应余地、且 D3 确认 Final 相比 Initial 有同场收益但仍输 B，本轮以 C1（增加合法状态/名义输入）与 C2（对齐在线递推目标）作为两个最小干预送零 Plant 部署检查。",
        "- C0 直接复用 D3 的六场 Final P_A 结果；身份/配置由 D3 预检验证，不能把 G05 离线分数当作 D5。",
        "- 新 fit=4/6 预算；D4 新 Plant=0。D5 预登记候选为 C1 seed 2026101901 与 C2 seed 2026101901；每个只跑固定 BRIDGE6。",
        "- 训练按 CUDA 确定性算法运行，`CUBLAS_WORKSPACE_CONFIG=:4096:8`；第一轮遇到环境缺项时 fit 尚未登记/未训练，补齐后同一身份启动。所有最终 fit 均 COMPLETE，无重训身份。",
        "",
        "源数据、原 G06、原选模及原始模型包未修改；G06 仍为 `STOP_POSITION_NOT_QUALIFIED`。",
    ]
    (OUT / "reports/D4_REPAIR_CANDIDATES.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    state_path = OUT / "state/state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state.update({"phase": "D4_COMPLETE", "next": "D5_ZERO_PLANT_PREFLIGHT",
                  "d4_fits_new": 4, "d4_completed_fits": 4, "active_fit_id": None,
                  "active_process": [], "d4_plant_starts_new": 0,
                  "updated_at_utc": pd.Timestamp.utcnow().isoformat()})
    tmp = state_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(state_path)
    print(f"D4 finalized: C0 reuse + {len(reports)} fits; new Plant=0")


if __name__ == "__main__":
    main()
