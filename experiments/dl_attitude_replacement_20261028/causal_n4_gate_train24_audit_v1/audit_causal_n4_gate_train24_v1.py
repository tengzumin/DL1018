"""Read-only, TRAIN24-only audit of a fixed causal N4 blend gate."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import h5py
import numpy as np
from scipy.signal import butter, sosfilt

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
BINDINGS_PATH = ROOT / "experiments/dl_attitude_replacement_20261028/no_position_gru_notch_train24_batch_prepare_v1/BATCH_BINDINGS_v1.json"
JSON_PATH = OUT / "CAUSAL_N4_GATE_TRAIN24_AUDIT_v1.json"
MD_PATH = OUT / "CAUSAL_N4_GATE_TRAIN24_AUDIT_v1.md"
FS = 100.0
DT = 1.0 / FS
ENERGY_TAU_S = 1.0
GATE_TAU_S = 0.3
STARTUP_S = 2.0
RATIO_LOW = 0.35
RATIO_SPAN = 0.30
EPS = 1e-8

BP_SOS = butter(2, [2.0, 5.0], btype="bandpass", fs=FS, output="sos")
LP_SOS = butter(2, 2.0, btype="lowpass", fs=FS, output="sos")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_array(h5: h5py.File, key: str) -> np.ndarray:
    return np.asarray(h5[key][()], dtype=np.float64)


def row_major_3xn(a: np.ndarray) -> np.ndarray:
    if a.ndim != 2:
        raise ValueError(f"Expected 2-D signal, got {a.shape}")
    if a.shape[0] == 3:
        return a.T.copy()
    if a.shape[1] == 3:
        return a.copy()
    raise ValueError(f"Expected three axes, got {a.shape}")


def causal_ratio_and_gate(signal: np.ndarray, times: np.ndarray) -> dict[str, np.ndarray]:
    """Zero-state SOS + 1-s EMA; gate EMA starts from zero at the 2-s unlock."""
    signal = np.asarray(signal, dtype=np.float64)
    if signal.shape != (len(times), 3) or not np.isfinite(signal).all():
        raise ValueError(f"Invalid causal input shape/values: {signal.shape}")
    bp = sosfilt(BP_SOS, signal, axis=0)
    lp = sosfilt(LP_SOS, signal, axis=0)
    alpha_e = float(np.exp(-DT / ENERGY_TAU_S))
    p_bp = np.sum(bp * bp, axis=1)
    p_lp = np.sum(lp * lp, axis=1)
    e_bp = np.zeros(len(times), dtype=np.float64)
    e_lp = np.zeros(len(times), dtype=np.float64)
    for i in range(len(times)):
        prev_bp = e_bp[i - 1] if i else 0.0
        prev_lp = e_lp[i - 1] if i else 0.0
        e_bp[i] = alpha_e * prev_bp + (1.0 - alpha_e) * p_bp[i]
        e_lp[i] = alpha_e * prev_lp + (1.0 - alpha_e) * p_lp[i]
    ratio = e_bp / (e_bp + e_lp + EPS)
    target = np.clip((ratio - RATIO_LOW) / RATIO_SPAN, 0.0, 1.0)
    alpha_g = float(np.exp(-DT / GATE_TAU_S))
    gate = np.zeros(len(times), dtype=np.float64)
    g_state = 0.0
    for i, t in enumerate(times):
        if t < STARTUP_S:
            g_state = 0.0
            gate[i] = 0.0
        else:
            g_state = alpha_g * g_state + (1.0 - alpha_g) * target[i]
            gate[i] = g_state
    return {"ratio": ratio, "target": target, "gate": gate,
            "e_bp": e_bp, "e_lp": e_lp, "bp": bp, "lp": lp}


def interp3(times_src: np.ndarray, signal_src: np.ndarray, times_dst: np.ndarray) -> np.ndarray:
    return np.column_stack([np.interp(times_dst, times_src, signal_src[:, j]) for j in range(3)])


def scene_group(w: int) -> str:
    if 9 <= w <= 14:
        return "W09-W14_high"
    if w == 15:
        return "W15_no_tone"
    return "W00-W08_lower"


def auc_high_vs_other(rows: list[dict], key: str) -> float | None:
    hi = [r[key] for r in rows if r["group"] == "W09-W14_high"]
    lo = [r[key] for r in rows if r["group"] != "W09-W14_high"]
    if not hi or not lo:
        return None
    # Pairwise probability with ties worth one half; no threshold is selected.
    return float((sum(x > y for x in hi for y in lo) + 0.5 * sum(x == y for x in hi for y in lo)) / (len(hi) * len(lo)))


def summarize(rows: list[dict], key: str) -> dict:
    values = np.asarray([r[key] for r in rows], dtype=np.float64)
    return {"n_scenes": int(len(values)), "median": float(np.median(values)),
            "q25": float(np.quantile(values, 0.25)), "q75": float(np.quantile(values, 0.75)),
            "min": float(np.min(values)), "max": float(np.max(values))}


def main() -> None:
    bindings_sha = sha256_file(BINDINGS_PATH)
    doc = json.loads(BINDINGS_PATH.read_text(encoding="utf-8"))
    if doc.get("schema") != "NO_POSITION_GRU_NOTCH_TRAIN24_BATCH_BINDINGS_V1" or doc.get("status") != "PREPARED_NO_PLANT_INPUTS_LOCKED":
        raise RuntimeError("Unexpected TRAIN24 source binding schema/status")
    if "TRAIN_C5_24 only" not in doc.get("scope", "") or len(doc.get("bindings", [])) != 24:
        raise RuntimeError("Source binding is not exactly the expected physical TRAIN24 cohort")
    if doc["fixed_controller"].get("attitude") != "parent cosine-GRU" or doc["fixed_controller"].get("inertia_reconstruction_enabled") is not False:
        raise RuntimeError("The locked source is not the parent cosine-GRU with fixed J0")

    rows: list[dict] = []
    source_hashes: list[dict] = []
    for binding in doc["bindings"]:
        scene_id = str(binding["scene_id"])
        match = re.search(r"_W(\d{2})$", scene_id)
        if not match or not scene_id.startswith("DL1018_DEV_"):
            raise RuntimeError(f"Unexpected TRAIN24 ID: {scene_id}")
        w = int(match.group(1))  # Offline grouping only; never enters the estimator.
        source = binding["same_scene_comparators"]["parent_cosine_gru"]
        raw_path = Path(source["raw_path"])
        actual_sha = sha256_file(raw_path)
        if actual_sha.lower() != str(source["raw_sha256"]).lower():
            raise RuntimeError(f"Parent raw hash mismatch for {scene_id}")
        source_hashes.append({"scene_id": scene_id, "raw_path": str(raw_path), "sha256": actual_sha})

        with h5py.File(raw_path, "r") as h5:
            event_t_all = read_array(h5, "log/transition_time").reshape(-1)
            event_all = read_array(h5, "log/stage1_position_event").reshape(-1) > 0.5
            event_action_all = row_major_3xn(read_array(h5, "log/stage1_position_event_applied_acceleration_mps2"))
            event_idx = np.flatnonzero(event_all)
            times = event_t_all[event_idx]
            action = event_action_all[event_idx]
            ready = np.isfinite(action).all(axis=1)
            action = np.where(ready[:, None], action, 0.0)  # 31 pre-ready NaN event outputs are causal zero.

            scene_t = read_array(h5, "scene/time").reshape(-1)
            ref_pos = row_major_3xn(read_array(h5, "scene/reference/position"))
            ref_acc = row_major_3xn(read_array(h5, "scene/reference/acceleration"))
            ref_acc_evt = interp3(scene_t, ref_acc, times)
            ref_pos_evt = interp3(scene_t, ref_pos, times)

            state_t = read_array(h5, "log/time").reshape(-1)
            state = read_array(h5, "log/state")
            if state.shape[0] == 12 and state.shape[1] == len(state_t):
                state = state.T
            if state.shape != (len(state_t), 12):
                raise ValueError(f"Unexpected physical state shape for {scene_id}: {state.shape}")
            # The simulator state order is position, velocity, Euler angles, body rates.
            state_pos_evt = interp3(state_t, state[:, :3], times)
            tracking_error_evt = state_pos_evt - ref_pos_evt

        if len(times) != 1999 or int(ready.sum()) != 1968 or int((~ready).sum()) != 31:
            raise RuntimeError(f"Unexpected event/readiness count for {scene_id}: {len(times)}, {ready.sum()}")
        if not np.allclose(np.diff(times), DT, atol=2e-8, rtol=0.0):
            raise RuntimeError(f"Position events are not a regular 100-Hz clock for {scene_id}")
        if np.any(ready & ~event_all[event_idx]):
            raise RuntimeError(f"Non-event action sample found for {scene_id}")

        action_feat = causal_ratio_and_gate(action, times)
        ref_feat = causal_ratio_and_gate(ref_acc_evt, times)
        post = times >= STARTUP_S
        if not np.any(post):
            raise RuntimeError(f"No post-startup samples for {scene_id}")
        gate = action_feat["gate"]
        ratio = action_feat["ratio"]
        ref_gate = ref_feat["gate"]
        first_on = np.flatnonzero(post & (gate >= 0.1))
        first_half = np.flatnonzero(post & (gate >= 0.5))
        tracking_bp = sosfilt(BP_SOS, tracking_error_evt, axis=0)
        row = {
            "scene_id": scene_id, "w_group_offline": f"W{w:02d}", "group": scene_group(w),
            "event_count": int(len(times)), "ready_events": int(ready.sum()), "unready_events_as_zero": int((~ready).sum()),
            "startup_forced_zero_events": int(np.sum(times < STARTUP_S)),
            "ratio_median_t2_20": float(np.median(ratio[post])), "ratio_p90_t2_20": float(np.quantile(ratio[post], .90)),
            "ratio_max_t2_20": float(np.max(ratio[post])),
            "gate_mean_t2_20": float(np.mean(gate[post])), "gate_median_t2_20": float(np.median(gate[post])),
            "gate_p90_t2_20": float(np.quantile(gate[post], .90)), "gate_max_t2_20": float(np.max(gate[post])),
            "gate_fraction_gt_0p1_t2_20": float(np.mean(gate[post] > 0.1)),
            "gate_fraction_ge_0p5_t2_20": float(np.mean(gate[post] >= 0.5)),
            "first_gate_ge_0p1_s": float(times[first_on[0]]) if len(first_on) else None,
            "first_gate_ge_0p5_s": float(times[first_half[0]]) if len(first_half) else None,
            "ref_ratio_p90_t2_20": float(np.quantile(ref_feat["ratio"][post], .90)),
            "ref_gate_fraction_gt_0p1_t2_20": float(np.mean(ref_gate[post] > 0.1)),
            "ref_gate_max_t2_20": float(np.max(ref_gate[post])),
            "tracking_error_2_5hz_rms_m_t2_20": float(np.sqrt(np.mean(np.sum(tracking_bp[post] ** 2, axis=1)))),
            "action_gate_ref_gate_corr_t2_20": float(np.corrcoef(gate[post], ref_gate[post])[0, 1]) if np.std(gate[post]) > 0 and np.std(ref_gate[post]) > 0 else None,
        }
        rows.append(row)

    groups = {}
    for name in ("W09-W14_high", "W00-W08_lower", "W15_no_tone"):
        group_rows = [r for r in rows if r["group"] == name]
        if group_rows:
            groups[name] = {key: summarize(group_rows, key) for key in (
                "ratio_median_t2_20", "ratio_p90_t2_20", "gate_mean_t2_20", "gate_p90_t2_20",
                "gate_fraction_gt_0p1_t2_20", "gate_fraction_ge_0p5_t2_20",
                "ref_gate_fraction_gt_0p1_t2_20", "tracking_error_2_5hz_rms_m_t2_20")}
    auc = {key: auc_high_vs_other(rows, key) for key in (
        "gate_mean_t2_20", "gate_p90_t2_20", "gate_fraction_gt_0p1_t2_20", "gate_fraction_ge_0p5_t2_20")}

    result = {
        "schema": "CAUSAL_N4_GATE_TRAIN24_AUDIT_V1",
        "status": "PASS_TRAIN_ONLY_READONLY_GATE_AUDIT_NO_MODEL_TRAINED_NO_PLANT",
        "source": {"bindings_path": str(BINDINGS_PATH), "bindings_sha256": bindings_sha,
                   "bindings_schema": doc["schema"], "parent_model": "DSSM14 position + cosineGRU attitude",
                   "scene_count": len(rows), "parent_raw_hash_verified_count": len(source_hashes),
                   "parent_raw_hashes": source_hashes},
        "protocol": {
            "input": "parent raw log.stage1_position_event_applied_acceleration_mps2, sampled only where stage1_position_event=1",
            "event_alignment": "1999 logged position events per scene at transition_time; 31 pre-ready NaN outputs are treated as zero action; non-event 1-ms points are not resampled into the estimator (the deployed event output is ZOH between 100-Hz events).",
            "fs_hz": FS, "bandpass": {"family": "Butterworth", "order": 2, "band_hz": [2.0, 5.0], "causal_sos_zero_initial_state": True},
            "lowpass": {"family": "Butterworth", "order": 2, "cutoff_hz": 2.0, "causal_sos_zero_initial_state": True},
            "energy": "sum over 3 axes of filtered signal squared; EMA tau=1.0 s; E(0)=0",
            "ratio": "E_bp/(E_bp+E_lp+1e-8)", "g_target": "clip((ratio-0.35)/0.30,0,1)",
            "blend_gate": "EMA tau=0.3 s; g state starts at zero at first event >=2.0 s; g=0 for t<2.0 s",
            "deployment_blend_contract": "N4 internal states keep updating from startup; output is clip(u_C5 + g*(u_N4-u_C5), -3, 3) per axis; g=0 selects C5 before the common final clip.",
            "offline_only": "W labels are parsed from scene_id only after computing gate traces; they never enter any signal, threshold, or gate update. Reference and state are read only for offline false-trigger context.",
        },
        "group_summary": groups,
        "scene_level_pairwise_probability_high_exceeds_other": auc,
        "scenes": rows,
        "scope": {"training": False, "Plant": False, "VAL_or_TEST_read": False,
                  "wind_truth_decoded": False, "inertia_reconstruction": False,
                  "N4_action_replayed": False, "only_parent_raw_action_reference_state_read": True},
        "source_hashes": {"audit_script_sha256": sha256_file(Path(__file__))},
    }
    JSON_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")

    lines = [
        "# 固定因果 N4 blend 门 TRAIN24 信号审计 v1", "",
        "## 范围", "",
        "只读 24 条 TRAIN_C5_24 physical parent cosine-GRU raw 中的 100 Hz applied action、reference position/acceleration 和 state position；未训练、未运行 Plant、未读取 VAL/TEST 评分、未解码风真值、未做惯量重建。W 组别只在门轨迹计算完成后离线汇总。",
        "", "## 固定协议", "",
        "- 输入：`stage1_position_event_applied_acceleration_mps2`，只取 `stage1_position_event=1` 的时刻。每场 1,999 个位置事件；31 个未 ready NaN 事件按当时实际输出零动作，随后 1,968 个 ready 事件。非事件 1 ms 样本不参与估计；部署中门和滤波动作按 100 Hz 更新并 ZOH 保持。",
        "- 零初态因果 Butterworth：2 阶 2–5 Hz 带通和 2 阶 2 Hz 低通，三轴独立滤波。能量为三轴平方和，零初态 EMA `tau=1 s`。",
        "- `ratio=Ebp/(Ebp+Elp+1e-8)`；`g_target=clip((ratio-.35)/.30,0,1)`；blend 门 `tau=.3 s`。首个 `t>=2 s` 事件从 `g=0` 开始平滑；`t<2 s` 强制 `g=0`。N4 状态建议从启动持续更新，输出 `clip(u_C5+g*(u_N4-u_C5),-3,3)`。",
        "", "## 组级结果", "",
        "下表每场先汇总 `t>=2 s` 的时间门信号，再跨场报告中位数和四分位数；组别不参与门估计。",
        "", "| 离线场组 | 场数 | ratio中位数 Q2–20s | ratio P90 | g均值中位数 | g P90中位数 | g>0.1时间占比中位数 | g≥0.5时间占比中位数 | 参考自身g>0.1占比中位数 | 状态位置误差2–5Hz RMS中位数(m) |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
    ]
    for name, vals in groups.items():
        n = vals["gate_mean_t2_20"]["n_scenes"]
        def fmt(k: str, stat: str = "median") -> str:
            return f"{vals[k][stat]:.4f}"
        lines.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
            name, n, fmt("ratio_median_t2_20"), fmt("ratio_p90_t2_20"), fmt("gate_mean_t2_20"),
            fmt("gate_p90_t2_20"), fmt("gate_fraction_gt_0p1_t2_20"), fmt("gate_fraction_ge_0p5_t2_20"),
            fmt("ref_gate_fraction_gt_0p1_t2_20"), fmt("tracking_error_2_5hz_rms_m_t2_20")))
    lines += ["", "## 固定门的区分与风险", "",
              "- 逐场连续门信号对 W09–14 相对 W00–08/W15 的 pairwise exceedance probability（仅离线排序，不选阈值）：" + ", ".join(f"{k}={v:.3f}" for k, v in auc.items() if v is not None) + ".",
              "- `g>0.1`、`g>=0.5` 都按预先固定输出门直接统计，不以 W 组调节阈值；逐场轨迹和启动时间见 JSON。",
              "- Reference acceleration 用相同公式作误触发上下文诊断，不进入部署门。若 W15/低频组的 action gate 仍常打开，单靠该能量比不能把风频振荡和任务/控制器自身高频动作分开；即使 reference 自身 gate 低，task-induced control transients 仍可能造成误开。",
              "- 位置跟踪误差 2–5 Hz RMS 仅作同时段的状态佐证，不是新的门输入，也不是对滤波器闭环效果的估计。24 场小样本、不同 task/构型混杂且 parent 已见这些场景，不能据此宣称统计功效或跨风组因果识别。",
              "- 固定的低维策略是让 N4 常态更新，再用该 `g` 平滑混合；`g=0` 退回 C5，避免启用时滤波器状态重置。该门只依赖历史 C5 action；有限阶因果频带估计会有启动/过渡泄漏，固定 2 s inhibit 和 EMA 只能限制瞬态，不能证明风因果来源。",
              "", "## 输入锁与哈希", "",
              f"- BATCH_BINDINGS SHA-256：`{bindings_sha}`。",
              f"- 审计脚本 SHA-256：`{result['source_hashes']['audit_script_sha256']}`。",
              f"- parent raw SHA-256 已验证：{len(source_hashes)}/24。逐场 raw 路径/哈希见 JSON。",
              "- 不读取 `score_path`、wind truth、VAL/TEST、或任何候选 N4 raw；没有执行 N4 action replay。", ""]
    MD_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": result["status"], "scenes": len(rows), "groups": groups,
                      "auc": auc, "script_sha256": result["source_hashes"]["audit_script_sha256"],
                      "json": str(JSON_PATH), "markdown": str(MD_PATH)}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
