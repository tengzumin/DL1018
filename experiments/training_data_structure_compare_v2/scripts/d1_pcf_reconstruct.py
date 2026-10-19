from __future__ import annotations

import json
import sys
from pathlib import Path

import h5py
import numpy as np
import pandas as pd
import torch

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "experiments" / "training_data_structure_compare_v2"
sys.path.insert(0, str(ROOT / "training"))
from models import PositionModel  # noqa: E402

BRIDGE = ROOT / "experiments/position_causal_repair_v1/manifests/BRIDGE6.csv"
OLD_BRIDGE = ROOT / "experiments/position_causal_repair_v1/reports/D3_INITIAL_FINAL_BRIDGE.csv"
DT = 0.001
K2 = np.array([4.0, 4.0, 4.0])
K1 = np.array([1.0, 1.0, 1.0])
G = float(json.loads((ROOT / "configs/contract_dl1018.json").read_text(encoding="utf-8"))["plant"]["gravity_mps2"])
MASS = float(json.loads((ROOT / "configs/contract_dl1018.json").read_text(encoding="utf-8"))["plant"]["mass_kg"])
TIME_BINS = ((0.0, 1.8, "T_0_1p8"), (1.8, 5.0, "T_1p8_5"), (5.0, 10.0, "T_5_10"),
             (10.0, 15.0, "T_10_15"), (15.0, 20.0 + 1e-9, "T_15_20"))


def tm(f: h5py.File, key: str, n: int, width: int | None = None) -> np.ndarray:
    a = np.asarray(f[key], dtype=np.float64)
    if a.ndim == 2 and a.shape[1] in (n, n + 1) and (width is None or a.shape[0] == width):
        a = a.T
    if a.ndim != 2 or a.shape[0] not in (n, n + 1) or (width is not None and a.shape[1] != width):
        raise ValueError(f"Unexpected matrix {key}: {a.shape}; expected {n}x{width}")
    return a


def vec(f: h5py.File, key: str, n: int) -> np.ndarray:
    return np.asarray(f[key], dtype=np.float64).reshape(-1)[:n]


def rotz(e: np.ndarray) -> np.ndarray:
    p, q, y = e
    cp, sp, cq, sq, cy, sy = np.cos(p), np.sin(p), np.cos(q), np.sin(q), np.cos(y), np.sin(y)
    return np.array([[cy*cq, cy*sq*sp-sy*cp, cy*sq*cp+sy*sp],
                     [sy*cq, sy*sq*sp+cy*cp, sy*sq*cp-cy*sp],
                     [-sq, cq*sp, cq*cp]])


def corr(x: np.ndarray, y: np.ndarray) -> float:
    x = np.asarray(x, dtype=np.float64).reshape(-1)
    y = np.asarray(y, dtype=np.float64).reshape(-1)
    xc, yc = x - x.mean(), y - y.mean()
    den = np.sqrt(np.sum(xc * xc) * np.sum(yc * yc))
    return float(np.sum(xc * yc) / den) if den > 0 else np.nan


def reconstruct(path: Path, scene_id: str, role: str) -> dict:
    with h5py.File(path, "r") as f:
        lg = f["log"]
        n = 20000
        state = tm(f, "log/state", n, 12)[:n]
        refp = tm(f, "log/reference/position", n, 3)[:n]
        refv = tm(f, "log/reference/velocity", n, 3)[:n]
        force_cmd = tm(f, "log/position_commanded_force_N", n, 3)
        force_applied = tm(f, "log/position_compensation_applied_force_N", n, 3)
        event_mask = vec(f, "log/position_event_flag", n).astype(bool)
        time = vec(f, "log/transition_time", n)
        euler_f = tm(f, "log/filtered_attitude_reference", n, 3)
        realized = tm(f, "log/realized_generalized", n, 4)
        wind = tm(f, "log/wind_force_I", n, 3)
        coordination = bool(np.asarray(lg["stage1_position_pcf_coordination_enabled"]).reshape(-1)[0])
        a_req_log = tm(f, "log/stage1_position_pcf_a_req_mps2", n, 3)
        a_f_log = tm(f, "log/stage1_position_pcf_a_f_mps2", n, 3)
        rf_log = tm(f, "log/stage1_position_pcf_r_f_mps2", n, 3)
        eta_before_log = tm(f, "log/stage1_position_pcf_eta_before_mps", n, 3)
        eta_after_log = tm(f, "log/stage1_position_pcf_eta_after_mps", n, 3)
        eta_event_log = tm(f, "log/stage1_position_pcf_event_eta_before_mps", n, 3)
        s_event_log = tm(f, "log/stage1_position_pcf_event_s_original_mps", n, 3)
        x14_log = tm(f, "log/stage1_position_feature_14", n, 14)

    # Exact outer-loop requested acceleration is commanded force / mass. For active
    # PCF logs, independently compare it to the logged a_req field.
    a_req = force_cmd / MASS
    active_req_err = float(np.nanmax(np.abs(a_req_log - a_req))) if np.isfinite(a_req_log).any() else np.nan
    # The nameplate filter's thrust magnitude is unchanged by tilt limiting. Use
    # the actually filtered Euler reference and the requested acceleration.
    thrust_per_mass = np.linalg.norm(a_req + np.array([0.0, 0.0, G]), axis=1)
    a_f = np.empty((n, 3), dtype=np.float64)
    for i in range(n):
        a_f[i] = thrust_per_mass[i] * rotz(euler_f[i])[:, 2] - np.array([0.0, 0.0, G])
    rf = a_req - a_f
    active_af_err = float(np.nanmax(np.abs(a_f_log - a_f))) if np.isfinite(a_f_log).any() else np.nan
    active_rf_err = float(np.nanmax(np.abs(rf_log - rf))) if np.isfinite(rf_log).any() else np.nan

    # Rebuild the virtual auxiliary state across every 1 kHz Plant transition.
    xi = np.zeros((n + 1, 3), dtype=np.float64)
    decay = np.exp(-K2 * DT)
    integral = -np.expm1(-K2 * DT) / K2
    for i in range(n):
        xi[i + 1] = decay * xi[i] + integral * rf[i]
    xi_before = xi[:-1]
    eta_replay_error = np.nan
    if coordination and np.isfinite(eta_before_log).all() and np.isfinite(eta_after_log).all():
        eta_replay_error = float(max(np.max(np.abs(xi_before - eta_before_log)),
                                     np.max(np.abs(xi[1:] - eta_after_log))))

    # Independent translational Plant acceleration from force, realized thrust,
    # orientation and gravity; this reconstructs d_train = a_actual - a_req.
    a_actual = np.empty((n, 3), dtype=np.float64)
    for i in range(n):
        a_actual[i] = (rotz(state[i, 6:9])[:, 2] * realized[i, 0] / MASS
                       - np.array([0.0, 0.0, G]) + wind[i] / MASS)
    d_train = a_actual - a_req
    err = refp - state[:n, :3]
    surface = refv + K1 * err - state[:n, 3:6]
    event_idx = np.flatnonzero(event_mask)
    if len(event_idx) != 1999:
        raise ValueError(f"Expected 1999 position events in {scene_id}/{role}; got {len(event_idx)}")
    # Align PCF state and surface only after updating it over the full 1 kHz log.
    rows = []
    for ordinal, j in enumerate(event_idx, start=1):
        rows.append({"scene_id": scene_id, "role": role, "event_index": ordinal,
                     "plant_index_zero_based": int(j), "time_s": float(time[j]),
                     "coordination_enabled": coordination,
                     "a_req_x_mps2": a_req[j, 0], "a_req_y_mps2": a_req[j, 1], "a_req_z_mps2": a_req[j, 2],
                     "a_f_x_mps2": a_f[j, 0], "a_f_y_mps2": a_f[j, 1], "a_f_z_mps2": a_f[j, 2],
                     "r_f_x_mps2": rf[j, 0], "r_f_y_mps2": rf[j, 1], "r_f_z_mps2": rf[j, 2],
                     "d_train_x_mps2": d_train[j, 0], "d_train_y_mps2": d_train[j, 1], "d_train_z_mps2": d_train[j, 2],
                     "d_coord_x_mps2": d_train[j, 0] + rf[j, 0],
                     "d_coord_y_mps2": d_train[j, 1] + rf[j, 1],
                     "d_coord_z_mps2": d_train[j, 2] + rf[j, 2],
                     "xi_virtual_x_mps": xi_before[j, 0], "xi_virtual_y_mps": xi_before[j, 1], "xi_virtual_z_mps": xi_before[j, 2],
                     "xi_logged_x_mps": eta_event_log[j, 0], "xi_logged_y_mps": eta_event_log[j, 1], "xi_logged_z_mps": eta_event_log[j, 2],
                     "s_x_mps": surface[j, 0], "s_y_mps": surface[j, 1], "s_z_mps": surface[j, 2],
                     "s_coord_virtual_x_mps": surface[j, 0] - xi_before[j, 0],
                     "s_coord_virtual_y_mps": surface[j, 1] - xi_before[j, 1],
                     "s_coord_virtual_z_mps": surface[j, 2] - xi_before[j, 2],
                     "s_logged_x_mps": s_event_log[j, 0], "s_logged_y_mps": s_event_log[j, 1], "s_logged_z_mps": s_event_log[j, 2]})
    return {"rows": rows, "time": time, "a_req": a_req, "a_f": a_f, "rf": rf,
            "d_train": d_train, "xi_before": xi_before, "eta_before_log": eta_before_log,
            "a_req_log": a_req_log, "a_f_log": a_f_log, "rf_log": rf_log,
            "eta_replay_error": eta_replay_error, "active_req_error": active_req_err,
            "active_af_error": active_af_err, "active_rf_error": active_rf_err,
            "event_idx": event_idx, "x14_log": x14_log, "event_mask": event_mask,
            "force_applied": force_applied, "state": state, "realized": realized, "wind": wind,
            "surface": surface, "coordination": coordination, "path": path}


def load_model(path: Path, device: torch.device):
    q = torch.load(path, map_location="cpu", weights_only=False)
    model = PositionModel(q["state_dict"]["input_mu"].cpu().numpy().reshape(-1),
                          q["state_dict"]["input_sigma"].cpu().numpy().reshape(-1))
    model.load_state_dict(q["state_dict"])
    model.eval().to(device)
    return model


def main() -> None:
    bridge = pd.read_csv(BRIDGE, keep_default_na=False)
    old = pd.read_csv(OLD_BRIDGE, keep_default_na=False)
    accepted = pd.read_csv(ROOT / "logs/episode_index.csv", keep_default_na=False)
    accepted = accepted[(accepted.split.str.lower() == "train") &
                        accepted.accepted.astype(str).str.lower().isin(("true", "1"))]
    attempts = pd.read_csv(ROOT / "logs/attempt_index.csv", keep_default_na=False)
    attempts = attempts.drop_duplicates("run_id", keep="last").set_index("run_id")
    event_by_run = accepted.set_index("run_id")["position_event_path"].to_dict()
    records: dict[tuple[str, str], dict] = {}
    derived: list[dict] = []
    for scene_id in bridge.scene_id.drop_duplicates().tolist():
        for row in bridge[bridge.scene_id == scene_id].itertuples(index=False):
            raw_rel = attempts.loc[row.run_id, "raw_path"]
            d = reconstruct(ROOT / Path(str(raw_rel).replace("/", "\\")), scene_id, row.role)
            records[(scene_id, row.role)] = d
            if row.run_id not in event_by_run:
                raise KeyError(f"Accepted event index lacks {row.run_id}")
            ep = ROOT / Path(str(event_by_run[row.run_id]).replace("/", "\\"))
            with h5py.File(ep, "r") as f:
                x14 = np.asarray(f["x14"], dtype=np.float64)
                if x14.shape == (14, 1999):
                    x14 = x14.T
                idx = np.asarray(f["plant_index"], dtype=np.int64).reshape(-1) - 1
                y = np.asarray(f["target_raw"], dtype=np.float64)
                if y.shape == (3, 1999):
                    y = y.T
            derived.extend(d["rows"])
            rows = d["rows"]
            if len(rows) != len(x14) or not np.array_equal(idx, d["event_idx"]):
                raise ValueError(f"H5/Plant event alignment mismatch for {scene_id}/{row.role}")
            pred = d["d_train"][idx]
            d["h5_label_max_abs"] = float(np.max(np.abs(pred - y)))
            d["x14"] = x14
            d["y_h5"] = y
        # Reuse old selected-Final run on the same six fixed bridge scenes.
        fin = old.loc[old.scene_id == scene_id].iloc[0]
        final_path = ROOT / Path(str(fin.raw_path).replace("/", "\\"))
        d = reconstruct(final_path, scene_id, "FINAL")
        records[(scene_id, "FINAL")] = d
        derived.extend(d["rows"])
        d["x14"] = d["x14_log"][d["event_idx"]]
        d["y_h5"] = d["d_train"][d["event_idx"]]

    pd.DataFrame(derived).to_csv(OUT / "reports/PCF_RECONSTRUCTION.csv", index=False)
    summary = []
    for (scene, role), d in records.items():
        t = d["time"]
        for lo, hi, label in TIME_BINS:
            mask = (t >= lo) & (t < hi)
            rv, dv = d["rf"][mask], d["d_train"][mask]
            pooled_corr = corr(rv, dv) if rv.size else np.nan
            for axis, name in enumerate(("x", "y", "z")):
                cor = corr(rv[:, axis], dv[:, axis])
                summary.append({"scene_id": scene, "role": role, "time_bin": label, "axis": name,
                                "n_1khz": int(mask.sum()), "r_f_rms_mps2": float(np.sqrt(np.mean(rv[:, axis]**2))),
                                "r_f_bias_mps2": float(np.mean(rv[:, axis])),
                                "d_train_rms_mps2": float(np.sqrt(np.mean(dv[:, axis]**2))),
                                "d_train_bias_mps2": float(np.mean(dv[:, axis])),
                                "corr_r_f_d_train_axis": cor, "corr_r_f_d_train_pooled": pooled_corr,
                                "rf_over_dtrain_rms": float(np.sqrt(np.mean(rv[:, axis]**2)) /
                                                             max(np.sqrt(np.mean(dv[:, axis]**2)), 1e-12))})
    summary_df = pd.DataFrame(summary)
    summary_df.to_csv(OUT / "reports/PCF_RECONSTRUCTION_SUMMARY.csv", index=False)

    # Evaluate original Initial and Final packages under exactly the same two
    # clipped offline residual objectives. This is not a newly flown result.
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    models = {"INITIAL": load_model(ROOT / "models/position/initial/best_model.pt", device),
              "FINAL": load_model(ROOT / "models/position/selected/selected_model.pt", device)}
    score_rows = []
    for (scene, role), d in records.items():
        ids = d["event_idx"]
        x = np.asarray(d["x14"], dtype=np.float32)
        if len(x) != len(ids):
            raise ValueError(f"X14/event mismatch {scene}/{role}")
        rf_event = d["rf"][ids]
        raw = d["d_train"][ids]
        y_train = np.clip(raw, -3, 3)
        y_coord = np.clip(raw + rf_event, -3, 3)
        xt = torch.as_tensor(x, dtype=torch.float32, device=device)
        with torch.no_grad():
            for model_id, model in models.items():
                pred = model(xt).detach().cpu().numpy().astype(np.float64)
                score_rows.append({"scene_id": scene, "role": role, "model_id": model_id,
                                   "d_train_rmse_mps2": float(np.sqrt(np.mean((pred-y_train)**2))),
                                   "d_coord_rmse_mps2": float(np.sqrt(np.mean((pred-y_coord)**2))),
                                   "d_train_bias_x": float(np.mean(pred[:, 0]-y_train[:, 0])),
                                   "d_train_bias_y": float(np.mean(pred[:, 1]-y_train[:, 1])),
                                   "d_train_bias_z": float(np.mean(pred[:, 2]-y_train[:, 2])),
                                   "d_coord_bias_x": float(np.mean(pred[:, 0]-y_coord[:, 0])),
                                   "d_coord_bias_y": float(np.mean(pred[:, 1]-y_coord[:, 1])),
                                   "d_coord_bias_z": float(np.mean(pred[:, 2]-y_coord[:, 2])),
                                   "target_clip_fraction_d_train": float(np.mean(np.abs(raw) > 3)),
                                   "target_clip_fraction_d_coord": float(np.mean(np.abs(raw+rf_event) > 3)),
                                   "online_or_closed_loop": False})
    score_df = pd.DataFrame(score_rows)
    score_df.to_csv(OUT / "reports/PCF_SAME_MODEL_TWO_OBJECTIVES.csv", index=False)

    active = [d for d in records.values() if d["coordination"]]
    closure = {
        "max_a_req_force_crosscheck_mps2": max((d["active_req_error"] for d in active if np.isfinite(d["active_req_error"])), default=np.nan),
        "max_a_f_physics_crosscheck_mps2": max((d["active_af_error"] for d in active if np.isfinite(d["active_af_error"])), default=np.nan),
        "max_r_f_crosscheck_mps2": max((d["active_rf_error"] for d in active if np.isfinite(d["active_rf_error"])), default=np.nan),
        "max_virtual_vs_logged_xi_1khz_m": max((d["eta_replay_error"] for d in active if np.isfinite(d["eta_replay_error"])), default=np.nan),
        "max_physics_dtrain_vs_h5_target_mps2": max((d.get("h5_label_max_abs", np.nan) for d in records.values() if "h5_label_max_abs" in d), default=np.nan),
        "roles": sorted(set(role for _, role in records)), "scenes": bridge.scene_id.drop_duplicates().tolist(),
        "sample_period_s": DT, "mass_kg": MASS, "gravity_mps2": G, "position_k2_s_inv": K2.tolist()}
    (OUT / "derived/PCF_RECONSTRUCTION_CLOSURE.json").write_text(json.dumps(closure, indent=2) + "\n", encoding="utf-8")

    # Bridge facts are presented separately from the new residual statistics.
    old_summary = old[["scene_id", "B_Q_0_20_m", "Initial_Q_0_20_m", "Final_Q_0_20_m",
                       "B_T_1p8_5_Q_m", "Initial_T_1p8_5_Q_m", "Final_T_1p8_5_Q_m",
                       "B_T_5_10_Q_m", "Initial_T_5_10_Q_m", "Final_T_5_10_Q_m"]]
    old_summary.to_csv(OUT / "derived/BRIDGE6_EXISTING_CLOSED_LOOP.csv", index=False)
    r18_10 = np.concatenate([summary_df.loc[(summary_df.scene_id == s) & (summary_df.role == r) &
                                      (summary_df.time_bin.isin(("T_1p8_5", "T_5_10"))) &
                                      (summary_df.axis.isin(("x", "y", "z"))), "r_f_rms_mps2"].to_numpy()
                               for s in bridge.scene_id.drop_duplicates() for r in ("B", "POS_OFF", "P_INIT_STUDENT", "FINAL")])
    report = f"""# PCF 假设核验（本轮独立复建）

## 推导：先区分两种误差面

真实位置外环写为 `e = p_ref - p`、`s = v_ref + K1 e - v`，`a_nom = alpha_dot + e + K2 s`。位置网络施加的补偿加速度记为 `a_comp`，故外环送往姿态/推力转换的请求为 `a_req = a_nom - a_comp`。按 Plant 平动方程，`a_actual = a_req + d_train`，其中 `d_train = a_actual - a_req` 正是事件导出监督目标所用的跟踪残差。

PCF 用 `r_f = a_req - a_f`，其中 `a_f` 是以滤波后姿态与名义推力合成的可实现参考加速度；其 1 kHz 精确零阶保持更新是 `xi[k+1] = exp(-K2*dt) xi[k] + (1-exp(-K2*dt))/K2 * r_f[k]`。控制器只在100 Hz事件上使用 `s_c = s - xi`。代入可得：

`dot(s_c) = -e - K2*s_c + a_comp - (d_train + r_f)`。

因此，在协调坐标下，未建模项对应 `d_coord = d_train + r_f`；原始 `d_train` 仍是未加 PCF 的跟踪残差。用 `d_train` 初始化离线 Head 是可解释的初始化选择，而不是自动的标签错误：启用协调状态后，在线 Head 更新看到 `s_c`，其更新和闭环误差会进一步改变参数与作用对象。离线回归目标与在线协调目标不完全相同，这是设计取舍，是否重要须看量级和闭环，不能只凭代数差异认定重复补偿。

这里的代数式按实际 `position_bs_step`、实际 `a_req`、PCF 实现及输出事件更新顺序推导。离散训练/事件值不能把连续式当精确事件导数；本轮辅助态使用全体 1 kHz 样本按运行器的 exact-ZOH 公式重放，再对齐100 Hz事件。B/POS_OFF原记录中的PCF关闭/零值仅作为原日志保留；`xi_virtual` 是在其已记录轨迹上以同一定义重建的反事实状态，不代表它们实际运行了PCF闭环。

## 独立复建闭合

- 六场桥接、四角色（B、POS_OFF、Initial、Final），读取24条20秒raw日志；新建 `PCF_RECONSTRUCTION.csv`，包含事件级 `a_req/a_f/r_f/d_train/d_coord/xi/s/s_c`。按每条轨迹完整1 kHz更新辅助态后再抽取事件。
- 实际加速度由原始状态、姿态、实现总推力、风力、合同质量/重力按Plant平动方程独立计算；与现有 B/POS_OFF/Initial H5 未裁剪目标的最大差见 closure JSON。活动PCF日志上的 `a_req/a_f/r_f/xi` 重放闭合最大误差也列于同一文件。
- 1.8–10 s 实际复建的 `r_f` 量级跨角色/轴的分位范围为 {np.nanpercentile(r18_10, 10):.4g} 到 {np.nanpercentile(r18_10, 90):.4g} m/s²；完整分场、分轴、分时段 RMS/偏置和与 `d_train` 相关性见 `PCF_RECONSTRUCTION_SUMMARY.csv`。`r_f` 只有在具体轴/时段与残差方向、幅度同时足够时才可能解释已见差距；相关性不是干预因果证据。
- Initial 与 Final 原冻结模型在每一条相同记录轨迹上分别计算裁剪 `d_train` 和 `d_coord` 目标的同口径物理 RMSE，见 `PCF_SAME_MODEL_TWO_OBJECTIVES.csv`。这是记录轨迹离线目标，不是闭环复飞。
- 已见闭环桥接仍以既有同场记录为准：宏Q与1.8–10 s分段指标保存在 `derived/BRIDGE6_EXISTING_CLOSED_LOOP.csv`；新残差回归不能改写这些实飞结果。

## 诊断字段纠正

本轮只读原日志字段 `stage1_position_pcf_event_eta_before_mps`。旧 D2 导出脚本候选名 `stage1_position_event_eta_before_mps` 与实际名不一致；旧 C2 序列缓存读取的是正确正式字段 `stage1_position_pcf_eta_before_mps`，因此没有证据把 C2 监督数据标为受该列名影响。本报告没有改旧脚本或旧报告，也没有把空诊断列升级成标签污染结论。

## 结论等级

**待本轮统计结果完成后判定**。当前唯一可先确认的是：`d_train` 是可复现的物理跟踪残差；在PCF坐标下自然出现 `d_train+r_f`，这本身是坐标变换结果，不足以称作原标签算错。应根据 `PCF_RECONSTRUCTION_SUMMARY.csv` 的实际量级和同场模型评分决定它是否足以解释主要差距。
"""
    (OUT / "reports/PCF_HYPOTHESIS_CHECK.md").write_text(report, encoding="utf-8")
    print(json.dumps({"episodes": len(records), "event_rows": len(derived), "closure": closure,
                      "pcf_summary": str(OUT / "reports/PCF_RECONSTRUCTION_SUMMARY.csv"),
                      "scores": len(score_rows), "status": "PCF_REBUILT"}, ensure_ascii=False, default=float))


if __name__ == "__main__":
    main()
