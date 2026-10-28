"""Fixed-structure TRAIN24 audit: compare LP2 and AC-only 0.5-2 Hz denominators."""
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
NPZ_PATH = OUT / "CAUSAL_N4_GATE_TRAIN24_ACDEN_V2_PER_EVENT.npz"
JSON_PATH = OUT / "CAUSAL_N4_GATE_TRAIN24_ACDEN_V2.json"
MD_PATH = OUT / "CAUSAL_N4_GATE_TRAIN24_ACDEN_V2.md"

FS = 100.0
DT = 1.0 / FS
ENERGY_TAU_S = 1.0
GATE_TAU_S = 0.3
STARTUP_S = 2.0
RATIO_LOW = 0.35
RATIO_SPAN = 0.30
EPS = 1e-8

BP_2_5_SOS = butter(2, [2.0, 5.0], btype="bandpass", fs=FS, output="sos")
LP_0_2_SOS = butter(2, 2.0, btype="lowpass", fs=FS, output="sos")
BP_0P5_2_SOS = butter(2, [0.5, 2.0], btype="bandpass", fs=FS, output="sos")


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


def ema_energy(signal: np.ndarray, alpha: float) -> np.ndarray:
    power = np.sum(np.asarray(signal, dtype=np.float64) ** 2, axis=1)
    out = np.zeros(len(power), dtype=np.float64)
    for i, p in enumerate(power):
        out[i] = alpha * (out[i - 1] if i else 0.0) + (1.0 - alpha) * p
    return out


def smooth_gate(ratio: np.ndarray, times: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    target = np.clip((ratio - RATIO_LOW) / RATIO_SPAN, 0.0, 1.0)
    alpha = float(np.exp(-DT / GATE_TAU_S))
    gate = np.zeros(len(times), dtype=np.float64)
    state = 0.0
    for i, t in enumerate(times):
        if t < STARTUP_S:
            state = 0.0
            gate[i] = 0.0
        else:
            state = alpha * state + (1.0 - alpha) * target[i]
            gate[i] = state
    return target, gate


def compute_features(signal: np.ndarray, times: np.ndarray) -> dict[str, np.ndarray]:
    """All filters and EMAs are causal, zero-state, and run at position events."""
    signal = np.asarray(signal, dtype=np.float64)
    if signal.shape != (len(times), 3) or not np.isfinite(signal).all():
        raise ValueError(f"Invalid event signal shape/values: {signal.shape}")
    alpha_e = float(np.exp(-DT / ENERGY_TAU_S))
    bp = sosfilt(BP_2_5_SOS, signal, axis=0)
    lp = sosfilt(LP_0_2_SOS, signal, axis=0)
    aclo = sosfilt(BP_0P5_2_SOS, signal, axis=0)
    ebp = ema_energy(bp, alpha_e)
    elp = ema_energy(lp, alpha_e)
    eaclo = ema_energy(aclo, alpha_e)

    # Diagnostic only: a causal EMA vector mean and energy after subtracting it.
    mean = np.zeros_like(signal)
    ecentered = np.zeros(len(times), dtype=np.float64)
    mean_state = np.zeros(3, dtype=np.float64)
    centered_energy_state = 0.0
    for i, u in enumerate(signal):
        mean_state = alpha_e * mean_state + (1.0 - alpha_e) * u
        mean[i] = mean_state
        centered = u - mean_state
        centered_energy_state = alpha_e * centered_energy_state + (1.0 - alpha_e) * float(centered @ centered)
        ecentered[i] = centered_energy_state
    emean = np.sum(mean * mean, axis=1)

    ratio_lp = ebp / (ebp + elp + EPS)
    ratio_ac = ebp / (ebp + eaclo + EPS)
    target_lp, gate_lp = smooth_gate(ratio_lp, times)
    target_ac, gate_ac = smooth_gate(ratio_ac, times)
    return {
        "Ebp_2_5": ebp, "Elp_0_2": elp, "Eaclo_0p5_2": eaclo,
        "ratio_lp": ratio_lp, "g_target_lp": target_lp, "gate_lp": gate_lp,
        "ratio_ac": ratio_ac, "g_target_ac": target_ac, "gate_ac": gate_ac,
        "causal_mean": mean, "mean_energy": emean, "demeaned_energy": ecentered,
        "bp_signal": bp, "lp_signal": lp, "aclo_signal": aclo,
    }


def group_for_w(w: int) -> str:
    if 9 <= w <= 14:
        return "W09-W14_high"
    if w == 15:
        return "W15_no_tone"
    return "W00-W08_lower"


def qsummary(values: list[float] | np.ndarray) -> dict:
    x = np.asarray(values, dtype=np.float64)
    return {"median": float(np.median(x)), "q25": float(np.quantile(x, .25)),
            "q75": float(np.quantile(x, .75)), "min": float(np.min(x)), "max": float(np.max(x))}


def pairwise_probability(rows: list[dict], key: str) -> float:
    hi = [r[key] for r in rows if r["group"] == "W09-W14_high"]
    other = [r[key] for r in rows if r["group"] != "W09-W14_high"]
    return float((sum(a > b for a in hi for b in other) + .5 * sum(a == b for a in hi for b in other)) / (len(hi) * len(other)))


def event_stats(scene_id: str, w: int, times: np.ndarray, ready: np.ndarray,
                af: dict[str, np.ndarray], rf: dict[str, np.ndarray]) -> dict:
    use = times >= STARTUP_S
    def med(key: str) -> float:
        return float(np.median(af[key][use]))
    def frac(key: str, threshold: float) -> float:
        return float(np.mean(af[key][use] >= threshold))
    def first(key: str, threshold: float) -> float | None:
        ix = np.flatnonzero(use & (af[key] >= threshold))
        return float(times[ix[0]]) if len(ix) else None
    return {
        "scene_id": scene_id, "w_group_offline": f"W{w:02d}", "group": group_for_w(w),
        "events": int(len(times)), "ready_events": int(ready.sum()), "unready_events_as_zero": int((~ready).sum()),
        "startup_forced_zero_events": int(np.sum(times < STARTUP_S)),
        "Ebp_2_5_median": med("Ebp_2_5"), "Elp_0_2_median": med("Elp_0_2"),
        "Eaclo_0p5_2_median": med("Eaclo_0p5_2"),
        "mean_energy_median": med("mean_energy"), "demeaned_energy_median": med("demeaned_energy"),
        "mean_energy_fraction_median": float(np.median(af["mean_energy"][use] /
            (af["mean_energy"][use] + af["demeaned_energy"][use] + EPS))),
        "mean_to_Elp_median": float(np.median(af["mean_energy"][use] / (af["Elp_0_2"][use] + EPS))),
        "ratio_lp_median": med("ratio_lp"), "ratio_lp_p90": float(np.quantile(af["ratio_lp"][use], .90)),
        "gate_lp_mean": float(np.mean(af["gate_lp"][use])), "gate_lp_p90": float(np.quantile(af["gate_lp"][use], .90)),
        "gate_lp_fraction_gt_0p1": float(np.mean(af["gate_lp"][use] > .1)),
        "gate_lp_fraction_ge_0p5": frac("gate_lp", .5), "first_gate_lp_gt_0p1_s": first("gate_lp", .1),
        "ratio_ac_median": med("ratio_ac"), "ratio_ac_p90": float(np.quantile(af["ratio_ac"][use], .90)),
        "gate_ac_mean": float(np.mean(af["gate_ac"][use])), "gate_ac_p90": float(np.quantile(af["gate_ac"][use], .90)),
        "gate_ac_fraction_gt_0p1": float(np.mean(af["gate_ac"][use] > .1)),
        "gate_ac_fraction_ge_0p5": frac("gate_ac", .5), "first_gate_ac_gt_0p1_s": first("gate_ac", .1),
        "ref_ratio_lp_median": float(np.median(rf["ratio_lp"][use])),
        "ref_gate_lp_fraction_gt_0p1": float(np.mean(rf["gate_lp"][use] > .1)),
        "ref_ratio_ac_median": float(np.median(rf["ratio_ac"][use])),
        "ref_gate_ac_fraction_gt_0p1": float(np.mean(rf["gate_ac"][use] > .1)),
    }


def main() -> None:
    binding_sha = sha256_file(BINDINGS_PATH)
    doc = json.loads(BINDINGS_PATH.read_text(encoding="utf-8"))
    if doc.get("schema") != "NO_POSITION_GRU_NOTCH_TRAIN24_BATCH_BINDINGS_V1" or doc.get("status") != "PREPARED_NO_PLANT_INPUTS_LOCKED":
        raise RuntimeError("Unexpected TRAIN24 binding")
    if "TRAIN_C5_24 only" not in doc.get("scope", "") or len(doc.get("bindings", [])) != 24:
        raise RuntimeError("Input manifest is not exactly physical TRAIN24")
    if doc["fixed_controller"].get("attitude") != "parent cosine-GRU" or doc["fixed_controller"].get("inertia_reconstruction_enabled") is not False:
        raise RuntimeError("The locked raw cohort is not the fixed-J0 parent cosine-GRU")

    event_times, ready_rows, action_rows = [], [], []
    action_features = {k: [] for k in ("Ebp_2_5", "Elp_0_2", "Eaclo_0p5_2", "ratio_lp", "g_target_lp", "gate_lp",
                                        "ratio_ac", "g_target_ac", "gate_ac", "causal_mean", "mean_energy", "demeaned_energy")}
    reference_features = {k: [] for k in ("Ebp_2_5", "Elp_0_2", "Eaclo_0p5_2", "ratio_lp", "g_target_lp", "gate_lp",
                                          "ratio_ac", "g_target_ac", "gate_ac")}
    w_codes, rows, raw_sources = [], [], []

    for binding in doc["bindings"]:
        scene_id = str(binding["scene_id"])
        m = re.search(r"_W(\d{2})$", scene_id)
        if not m or not scene_id.startswith("DL1018_DEV_"):
            raise RuntimeError(f"Unexpected cohort ID: {scene_id}")
        w = int(m.group(1))  # Offline grouping only; not passed to either filter.
        src = binding["same_scene_comparators"]["parent_cosine_gru"]
        raw_path = Path(src["raw_path"])
        raw_sha = sha256_file(raw_path)
        if raw_sha.lower() != str(src["raw_sha256"]).lower():
            raise RuntimeError(f"Parent raw changed: {scene_id}")
        raw_sources.append({"scene_id": scene_id, "raw_path": str(raw_path), "sha256": raw_sha})

        with h5py.File(raw_path, "r") as h5:
            transition_t = read_array(h5, "log/transition_time").reshape(-1)
            event = read_array(h5, "log/stage1_position_event").reshape(-1) > .5
            event_u = row_major_3xn(read_array(h5, "log/stage1_position_event_applied_acceleration_mps2"))
            ix = np.flatnonzero(event)
            times = transition_t[ix]
            u = event_u[ix]
            ready = np.isfinite(u).all(axis=1)
            u = np.where(ready[:, None], u, 0.0)  # Preserve all 1,999 events; 31 warmup NaNs are actual zero output.

            ref_t = read_array(h5, "scene/time").reshape(-1)
            ref_a = row_major_3xn(read_array(h5, "scene/reference/acceleration"))
            ref_event_a = np.column_stack([np.interp(times, ref_t, ref_a[:, axis]) for axis in range(3)])

        if len(times) != 1999 or int(ready.sum()) != 1968 or int((~ready).sum()) != 31:
            raise RuntimeError(f"Unexpected event/readiness count: {scene_id}, {len(times)}, {ready.sum()}")
        if not np.allclose(np.diff(times), DT, atol=2e-8, rtol=0.0):
            raise RuntimeError(f"Expected 100-Hz event clock: {scene_id}")
        if not np.isfinite(u).all() or not np.isfinite(ref_event_a).all():
            raise RuntimeError(f"Nonfinite causal input: {scene_id}")

        af = compute_features(u, times)
        rf = compute_features(ref_event_a, times)
        event_times.append(times)
        ready_rows.append(ready)
        action_rows.append(u)
        w_codes.append(w)
        for k in action_features:
            action_features[k].append(af[k])
        for k in reference_features:
            reference_features[k].append(rf[k])
        rows.append(event_stats(scene_id, w, times, ready, af, rf))

    # Invariants keep this a fixed-protocol rerun, not a sweep.
    assert len(rows) == 24 and len(raw_sources) == 24
    assert all(r["startup_forced_zero_events"] == 199 for r in rows)
    assert np.all(np.stack(ready_rows).sum(axis=1) == 1968)
    assert np.all(np.stack([action_features["gate_lp"]])[0][:, :199] == 0)
    assert np.all(np.stack([action_features["gate_ac"]])[0][:, :199] == 0)

    arrays = {
        "scene_ids": np.asarray([b["scene_id"] for b in doc["bindings"]], dtype="U40"),
        "w_codes_offline_only": np.asarray(w_codes, dtype=np.int8),
        "event_time_s": np.stack(event_times),
        "ready_mask": np.stack(ready_rows),
        "parent_action_used_mps2": np.stack(action_rows),
    }
    for k, seq in action_features.items():
        arrays[f"action_{k}"] = np.stack(seq)
    for k, seq in reference_features.items():
        arrays[f"reference_{k}"] = np.stack(seq)
    np.savez_compressed(NPZ_PATH, **arrays)
    npz_sha = sha256_file(NPZ_PATH)

    w_summary = {}
    for w in range(16):
        rr = [r for r in rows if r["w_group_offline"] == f"W{w:02d}"]
        if not rr:
            continue
        keys = [
            "Ebp_2_5_median", "Elp_0_2_median", "Eaclo_0p5_2_median",
            "mean_energy_median", "demeaned_energy_median", "mean_energy_fraction_median", "mean_to_Elp_median",
            "ratio_lp_median", "ratio_lp_p90", "gate_lp_mean", "gate_lp_p90", "gate_lp_fraction_gt_0p1", "gate_lp_fraction_ge_0p5",
            "ratio_ac_median", "ratio_ac_p90", "gate_ac_mean", "gate_ac_p90", "gate_ac_fraction_gt_0p1", "gate_ac_fraction_ge_0p5",
            "ref_gate_lp_fraction_gt_0p1", "ref_gate_ac_fraction_gt_0p1",
        ]
        w_summary[f"W{w:02d}"] = {"scene_count": len(rr), **{k: qsummary([r[k] for r in rr]) for k in keys}}

    result = {
        "schema": "CAUSAL_N4_GATE_TRAIN24_ACDEN_V2",
        "status": "PASS_TRAIN_ONLY_FIXED_STRUCTURE_AUDIT_NO_MODEL_TRAINED_NO_PLANT",
        "source": {"bindings_path": str(BINDINGS_PATH), "bindings_sha256": binding_sha,
                   "binding_schema": doc["schema"], "parent_model": "DSSM14 position + cosineGRU attitude",
                   "scene_count": 24, "parent_raw_hash_verified_count": len(raw_sources), "parent_raw_sources": raw_sources,
                   "per_event_npz_path": str(NPZ_PATH), "per_event_npz_sha256": npz_sha},
        "fixed_protocol": {
            "sample_rate_hz": FS, "event_count_per_scene": 1999, "ready_events": 1968,
            "unready_nan_events_as_zero": 31, "startup_forced_zero_events": 199,
            "event_clock": "log.transition_time selected exactly where stage1_position_event=1; each update is 100 Hz; non-event 1-ms interval is ZOH and is not fed to estimators.",
            "action_input": "same parent cosine-GRU raw stage1_position_event_applied_acceleration_mps2 as v1; only 24 TRAIN_C5_24 raw files bound by BATCH_BINDINGS.",
            "filters": {"bandpass_2_5": {"family": "Butterworth", "order": 2, "band_hz": [2.0, 5.0], "zero_initial_state": True},
                        "original_lowpass_0_2": {"family": "Butterworth", "order": 2, "cutoff_hz": 2.0, "zero_initial_state": True},
                        "new_ac_low_0p5_2": {"family": "Butterworth", "order": 2, "band_hz": [0.5, 2.0], "zero_initial_state": True}},
            "energy_tau_s": ENERGY_TAU_S, "ratio_lp": "Ebp_2_5/(Ebp_2_5+Elp_0_2+1e-8)",
            "ratio_ac_only": "Ebp_2_5/(Ebp_2_5+Eaclo_0p5_2+1e-8)",
            "gate_target_both": "clip((ratio-0.35)/0.30,0,1)", "gate_tau_s": GATE_TAU_S,
            "startup_s": STARTUP_S, "gate_state_start": "zero at first event >=2 s; output is zero before 2 s",
            "thresholds_and_taus_unchanged_from_v1": True,
            "action_mean_diagnostic": "causal vector EMA tau=1 s, initialized zero; store mu[k], ||mu[k]||^2, and EMA_1s(||u[k]-mu[k]||^2); diagnostics do not enter either gate.",
            "reference_gates": "Reference acceleration is resampled to the same 100-Hz event times and evaluated separately through both fixed estimators; it never enters the action gate.",
            "offline_grouping": "W is parsed from scene_id only after computing action/reference features; it is not a filter or threshold input.",
            "deployment_blend_contract": "N4 state updates continuously; output contract remains clip(u_C5+g*(u_N4-u_C5), -3, 3) per axis.",
        },
        "per_w_summary": w_summary,
        "scenes": rows,
        "per_event_arrays": {"archive": str(NPZ_PATH), "format": "compressed NumPy NPZ",
            "keys": sorted(arrays), "shape_convention": "scene x 1,999 events [x 3 axes for vector arrays]"},
        "scope": {"training": False, "Plant": False, "VAL_or_TEST_read": False,
                  "wind_truth_decoded": False, "inertia_reconstruction": False, "new_gate_sweep": False,
                  "N4_action_replayed": False, "raw_re_read_count": 24},
        "source_hashes": {"audit_script_sha256": sha256_file(Path(__file__))},
    }
    JSON_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")

    md = [
        "# 固定结构 AC-only 分母门控审计 v2（TRAIN24）", "",
        "## 范围与输入", "",
        "为比较固定结构而重读并核验 24 条 TRAIN_C5_24 physical parent cosine-GRU raw。只取 parent applied action、scene reference acceleration 和事件时间；W 仅在完成特征计算后用于离线分组。没有训练、Plant、VAL/TEST、风真值或惯量重建；没有重新设计/扫描门参数。首版 v1 未修改。",
        "", "## 协议锁", "",
        "- 保留 2–5 Hz 二阶 Butterworth 带通和原 0–2 Hz 二阶低通；新增唯一对照分母为二阶因果 Butterworth 0.5–2 Hz 带通能量。三轴分别处理、零初态 SOS。",
        "- 每场沿用全部 1,999 个 100 Hz 位置事件；31 个 pre-ready NaN 输出按零动作处理，1,968 个 ready 事件保留。非事件 1 ms 只由部署 ZOH 保持，不进入估计器。",
        "- 两 ratio 分别为 `Ebp/(Ebp+Elp+1e-8)` 与 `Ebp/(Ebp+Eaclo+1e-8)`。两者的能量 EMA `tau=1 s`、`g_target=clip((ratio-.35)/.30,0,1)`、`g` EMA `tau=.3 s`、`t<2 s` 强制零，均与 v1 相同；无阈值或时间常数搜索。",
        "- 原 lowpass `Elp`、新增 `Eaclo`、`Ebp`、动作因果 EMA 向量均值、均值能量和去均值能量逐事件存于压缩 NPZ。动作均值/去均值项仅作诊断，不作为门输入。参考加速度也独立计算两套门，不输入 action gate。",
        "", "## 按 W 离线结果", "",
        "表中每场先在 `t>=2 s` 上求时间中位数，再对该 W 的场景取中位数；能量单位为 (m/s²)²。W 仅用于下面的分组。",
        "", "| W | n | Ebp | Elp | Eaclo | 因果均值能量 | 去均值能量 | 均值占均值+去均值 | LP2 ratio | LP2 g均值 | AC ratio | AC g均值 | ref LP g>0.1 | ref AC g>0.1 |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
    ]
    for wname, s in w_summary.items():
        def f(key: str) -> str:
            return f"{s[key]['median']:.5g}"
        md.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
            wname, s["scene_count"], f("Ebp_2_5_median"), f("Elp_0_2_median"), f("Eaclo_0p5_2_median"),
            f("mean_energy_median"), f("demeaned_energy_median"), f("mean_energy_fraction_median"),
            f("ratio_lp_median"), f("gate_lp_mean"), f("ratio_ac_median"), f("gate_ac_mean"),
            f("ref_gate_lp_fraction_gt_0p1"), f("ref_gate_ac_fraction_gt_0p1")))
    md += ["", "## 解释边界", "",
           "- 两个 ratio/g 都按固定阈值原样计算并逐事件保存；AC-only 版本是唯一结构对照，不是调参结果。高频风组标签仅用于本表，不用于任何门更新。",
           "- 2 Hz 低通对 DC 的稳态幅度增益为 1，因此其能量包含动作均值和慢变化；新 0.5–2 Hz 带通理论上 DC 增益为 0，可以避免均值直接占用分母，但有限时域初态仍会有滤波过渡。0.5–2Hz 仍包含任务慢变动作，且在 2Hz 边界附近滤波器不正交。",
           "- 因果 EMA 均值的平方与去均值能量是 DC/慢变贡献的代理，不是严格频域功率分解；不能将 `||mu||²/Elp` 解释为精确 DC 百分比。",
           "- 参考加速度单独门只诊断参考直接误触发风险。若动作门开启，仍不能断言能量来自风，而非任务诱发的闭环动作；24 场是已见 parent 的开发轨迹，不提供独立泛化或因果闭环效果证据。",
           "- N4 内部持续更新、`g=0` 时按 blend 回到 C5 的运行契约只作设计约束；本次没有执行 N4 action replay。", "",
           "## 来源与哈希", "",
           f"- BATCH_BINDINGS SHA-256：`{binding_sha}`。",
           f"- parent raw 哈希核验：{len(raw_sources)}/24。逐场路径/哈希见 JSON。",
           f"- per-event NPZ SHA-256：`{npz_sha}`。",
           f"- 审计脚本 SHA-256：`{result['source_hashes']['audit_script_sha256']}`。", ""]
    MD_PATH.write_text("\n".join(md), encoding="utf-8")
    print(json.dumps({"status": result["status"], "scenes": 24, "event_count_per_scene": 1999,
                      "ready_events": 1968, "unready_zero_events": 31, "w_groups": w_summary,
                      "npz_sha256": npz_sha, "script_sha256": result["source_hashes"]["audit_script_sha256"],
                      "json": str(JSON_PATH), "markdown": str(MD_PATH)}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
