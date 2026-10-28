"""TRAIN-only spectral robustness audit for the locked HF10 paired raws."""

import importlib.util
import json
from pathlib import Path

import h5py
import numpy as np
from scipy.signal import butter, sosfiltfilt, welch


HERE = Path(__file__).resolve().parent


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hf = load_module("hf_task_budget_helper", HERE / "hf_task_budget_with_b_v2.py")
scorer = load_module("frozen_score_full72", hf.SCORER)
ROOT = hf.ROOT
SUMMARY = hf.SUMMARY
OUT_JSON = HERE / "SPECTRAL_ROBUSTNESS_AUDIT_v1.json"
OUT_MD = HERE / "SPECTRAL_ROBUSTNESS_AUDIT_v1.md"
FS = 1000.0
DT = 1.0 / FS
NSEG = 2000
NOVERLAP = NSEG // 2
WINDOWS = {
    "whole_0_20s": lambda t: (t >= 0.0) & (t <= 20.0),
    "0_2s": lambda t: (t >= 0.0) & (t < 2.0),
    "2_5s": lambda t: (t >= 2.0) & (t < 5.0),
    "5_20s": lambda t: (t >= 5.0) & (t <= 20.0),
}
BANDS = {
    "2_to_5_Hz": lambda f: (f >= 2.0) & (f <= 5.0),
    "above_5_Hz": lambda f: f > 5.0,
}


def need(condition, message):
    if not condition:
        raise ValueError(message)


def read_raw(path):
    with h5py.File(path, "r") as f:
        log = f["log"]
        ref = f["scene/reference"]
        t = np.asarray(log["time"][()], dtype=np.float64).reshape(-1)
        state = np.asarray(log["state"][()], dtype=np.float64).T
        acc = np.asarray(ref["acceleration"][()], dtype=np.float64).T
        yaw = np.asarray(ref["yaw"][()], dtype=np.float64).reshape(-1)
    need(state.shape == (20001, 12) and acc.shape == (20001, 3) and yaw.shape == (20001,),
         f"Unexpected raw shape: {path}")
    need(np.max(np.abs(np.diff(t) - DT)) < 1e-10 and abs(t[0]) < 1e-12 and abs(t[-1] - 20.0) < 1e-10,
         f"Unexpected time grid: {path}")
    need(np.isfinite(state).all() and np.isfinite(acc).all() and np.isfinite(yaw).all(),
         f"Non-finite raw values: {path}")
    return t, state, acc, yaw


def band_power(psd, freq, mask):
    df = float(freq[1] - freq[0])
    return float(np.sum(psd[:, mask]) * df)


def welch_power(error, time_s, detrend):
    freq, psd = welch(
        error.T, fs=FS, window="hann", nperseg=NSEG, noverlap=NOVERLAP,
        detrend=detrend, scaling="density", axis=-1,
    )
    return {
        "frequency_bin_width_Hz": float(freq[1] - freq[0]),
        "segment_count": int(1 + (len(time_s) - NSEG) // (NSEG - NOVERLAP)),
        "bands_mse_rad2": {name: band_power(psd, freq, mask(freq)) for name, mask in BANDS.items()},
    }


def ratio(a, b):
    return float(a / b) if b else None


def main():
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    need(summary["schema"] == "DL1018_CAUSAL_N4_TRAIN24_BATCH_SCORE_SUMMARY_V2", "Wrong TRAIN summary schema")
    scenes = [s for s in summary["scenes"] if s.get("HF_W09_W14") is True]
    need(len(scenes) == 10, f"Expected exactly 10 locked HF TRAIN scenes, found {len(scenes)}")
    constants = json.loads(hf.RELEASE.read_text(encoding="utf-8"))
    gravity = float(constants["gravity_mps2"])
    max_tilt = float(constants["max_tilt_rad"])

    per_scene = []
    raw_rows = []
    gate_checks = []
    for scene in scenes:
        sid = scene["scene_id"]
        binding_path = hf.TRAIN / "bindings" / f"{sid}.json"
        binding = json.loads(binding_path.read_text(encoding="utf-8"))
        need(binding["TEST_read"] is False and binding["VAL_data_read"] is False and
             binding["inertia_reconstruction_enabled"] is False and binding["Plant_calls"] == 0,
             f"Scope flags failed for {sid}")
        paths = {
            "candidate": hf.candidate_path(sid),
            "parent": Path(binding["parent_raw_path"]),
            "B": Path(binding["b72_scoring_raw_path"]),
        }
        for key, raw_path in paths.items():
            need(raw_path.is_file(), f"Missing {key} raw for {sid}: {raw_path}")
            expected = binding.get({"parent": "parent_raw_sha256", "B": "b72_scoring_raw_sha256"}.get(key, ""))
            if expected:
                need(hf.sha256(raw_path).lower() == expected.lower(), f"{key} SHA mismatch for {sid}")

        errors, scores, states, t_ref = {}, {}, {}, None
        reference_signature = None
        scene_data = {"scene_id": sid, "raws": {}}
        for method, raw_path in paths.items():
            t, state, acc, yaw = read_raw(raw_path)
            if t_ref is None:
                t_ref, reference_signature = t, (acc, yaw)
            else:
                need(np.array_equal(t, t_ref) and np.array_equal(acc, reference_signature[0]) and
                     np.array_equal(yaw, reference_signature[1]), f"Paired raw references/time differ for {sid}")
            t2, err, local_score = hf.task_error(raw_path, gravity, max_tilt)
            need(np.array_equal(t, t2), f"Helper time mismatch for {sid}/{method}")
            official = float(scorer.score_raw(raw_path, gravity, max_tilt)["task_SO3_rad"])
            need(abs(local_score - official) <= 1e-12, f"Helper/scorer mismatch for {sid}/{method}")
            expected_summary = float(scene["task_SO3_rad"][method])
            need(abs(official - expected_summary) <= 1e-10, f"Frozen summary mismatch for {sid}/{method}")
            errors[method], scores[method], states[method] = err, official, state
            scene_data["raws"][method] = {
                "path": str(raw_path), "sha256": hf.sha256(raw_path),
                "official_task_SO3_rmse_rad": official,
            }
        scene_data["reference_and_time_exact_across_pair"] = True
        scene_data["windows_task_rmse_rad"] = {}
        for wname, selector in WINDOWS.items():
            mask = selector(t_ref)
            scene_data["windows_task_rmse_rad"][wname] = {
                method: float(np.sqrt(np.mean(np.sum(err[mask] ** 2, axis=1))))
                for method, err in errors.items()
            }

        early = t_ref < 2.0
        early_err_diff = float(np.max(np.abs(errors["candidate"][early] - errors["parent"][early])))
        with h5py.File(paths["candidate"], "r") as f:
            log = f["log"]
            event = np.asarray(log["stage1_position_event"][()], dtype=bool).reshape(-1)
            tt = np.asarray(log["transition_time"][()], dtype=np.float64).reshape(-1)
            early_event = event & (tt < 2.0)
            gate_diag = np.asarray(log["stage1_position_causal_n4_gate_diagnostics"][()], dtype=np.float64).T
            n4_input = np.asarray(log["stage1_position_applied_static_n4_event_input_mps2"][()], dtype=np.float64).T
            n4_applied = np.asarray(log["stage1_position_applied_static_n4_event_output_applied_mps2"][()], dtype=np.float64).T
            gate = gate_diag[early_event, 4]
            u = n4_input[early_event]
            u_applied = n4_applied[early_event]
        gate_row = {
            "scene_id": sid,
            "early_event_count_t_lt_2s": int(early_event.sum()),
            "max_abs_recorded_gate_t_lt_2s": float(np.max(np.abs(gate))),
            "max_abs_gate_applied_minus_parent_input_mps2_t_lt_2s": float(np.max(np.abs(u_applied - u))),
            "candidate_parent_state_max_abs_t_lt_2s": float(np.max(np.abs(states["candidate"][early] - states["parent"][early]))),
            "candidate_parent_error_rotvec_max_abs_rad_t_lt_2s": early_err_diff,
        }
        need(gate_row["max_abs_recorded_gate_t_lt_2s"] <= 1e-12 and
             gate_row["max_abs_gate_applied_minus_parent_input_mps2_t_lt_2s"] <= 1e-12 and
             gate_row["candidate_parent_state_max_abs_t_lt_2s"] <= 1e-12 and
             early_err_diff <= 1e-12, f"Startup parent parity failed for {sid}")
        gate_checks.append(gate_row)
        per_scene.append(scene_data)

        # Re-run the independent spectral estimators on the exact same SO(3) log-vector error.
        method_rows = {}
        for method, err in errors.items():
            method_rows[method] = {"welch": {}, "zero_phase_bandpass": {}}
            for detrend in ("constant", "linear"):
                key = "hann_demean" if detrend == "constant" else "hann_linear_detrend"
                method_rows[method]["welch"][key] = {}
                for wname, selector in WINDOWS.items():
                    mask = selector(t_ref)
                    need(int(mask.sum()) >= NSEG, f"Window shorter than Welch segment: {sid}/{wname}")
                    method_rows[method]["welch"][key][wname] = welch_power(err[mask], t_ref[mask], detrend)

            # Filter the full record so the 2--5 s slice is not given a new filter boundary.
            bp = sosfiltfilt(butter(4, [2.0, 5.0], btype="bandpass", fs=FS, output="sos"), err, axis=0)
            hp = sosfiltfilt(butter(4, 5.0, btype="highpass", fs=FS, output="sos"), err, axis=0)
            filter_bands = {"2_to_5_Hz": bp, "above_5_Hz": hp}
            filter_windows = {
                "whole_0_20s": (1.0, 19.0, "[1,19] s; 1 s guard at both record ends"),
                "2_5s": (2.0, 5.0, "[2,5) s; interior slice of full-record filtering"),
                "5_20s": (5.0, 19.0, "[5,19] s; 1 s guard at the record end"),
            }
            for band_name, filtered in filter_bands.items():
                method_rows[method]["zero_phase_bandpass"][band_name] = {}
                for wname, (lo, hi, support) in filter_windows.items():
                    mask = (t_ref >= lo) & (t_ref <= hi if hi == 19.0 else t_ref < hi)
                    method_rows[method]["zero_phase_bandpass"][band_name][wname] = {
                        "mse_rad2": float(np.mean(np.sum(filtered[mask] ** 2, axis=1))),
                        "sample_count": int(mask.sum()),
                        "evaluation_support": support,
                    }
        raw_rows.append(method_rows)

    spectral_summary = {}
    for estimator in ("welch", "zero_phase_bandpass"):
        spectral_summary[estimator] = {}
        if estimator == "welch":
            configs = ("hann_demean", "hann_linear_detrend")
            for config in configs:
                spectral_summary[estimator][config] = {}
                for wname in WINDOWS:
                    spectral_summary[estimator][config][wname] = {}
                    for band_name in BANDS:
                        scene_mse = {
                            method: [row[method]["welch"][config][wname]["bands_mse_rad2"][band_name]
                                     for row in raw_rows]
                            for method in ("candidate", "B", "parent")
                        }
                        pooled_rmse = {m: float(np.sqrt(np.mean(vals))) for m, vals in scene_mse.items()}
                        mean_scene_rmse = {m: float(np.mean(np.sqrt(vals))) for m, vals in scene_mse.items()}
                        spectral_summary[estimator][config][wname][band_name] = {
                            "mean_scene_band_mse_rad2": {m: float(np.mean(v)) for m, v in scene_mse.items()},
                            "pooled_band_rmse_rad": pooled_rmse,
                            "mean_scene_band_rmse_rad": mean_scene_rmse,
                            "candidate_over_B_pooled_rmse_ratio": ratio(pooled_rmse["candidate"], pooled_rmse["B"]),
                            "candidate_over_parent_pooled_rmse_ratio": ratio(pooled_rmse["candidate"], pooled_rmse["parent"]),
                            "candidate_scenes_with_more_band_mse_than_B": int(sum(c > b for c, b in zip(scene_mse["candidate"], scene_mse["B"]))),
                            "welch_resolution_Hz": 0.5,
                            "welch_segments_by_window": int(raw_rows[0]["candidate"]["welch"][config][wname]["segment_count"]),
                        }
        else:
            for band_name in ("2_to_5_Hz", "above_5_Hz"):
                spectral_summary[estimator][band_name] = {}
                for wname in ("whole_0_20s", "2_5s", "5_20s"):
                    scene_mse = {
                        method: [row[method]["zero_phase_bandpass"][band_name][wname]["mse_rad2"]
                                 for row in raw_rows]
                        for method in ("candidate", "B", "parent")
                    }
                    pooled_rmse = {m: float(np.sqrt(np.mean(vals))) for m, vals in scene_mse.items()}
                    spectral_summary[estimator][band_name][wname] = {
                        "mean_scene_band_mse_rad2": {m: float(np.mean(v)) for m, v in scene_mse.items()},
                        "pooled_band_rmse_rad": pooled_rmse,
                        "candidate_over_B_pooled_rmse_ratio": ratio(pooled_rmse["candidate"], pooled_rmse["B"]),
                        "candidate_over_parent_pooled_rmse_ratio": ratio(pooled_rmse["candidate"], pooled_rmse["parent"]),
                        "candidate_scenes_with_more_band_mse_than_B": int(sum(c > b for c, b in zip(scene_mse["candidate"], scene_mse["B"]))),
                        "filter_order_one_pass": 4,
                        "filter_type": "Butterworth SOS; sosfiltfilt zero-phase; 2-5 Hz bandpass or >5 Hz high-pass",
                    }

    old_budget = json.loads((HERE / "HF_TRAIN10_WITH_B_ROOT_v1.json").read_text(encoding="utf-8"))
    old_windows = json.loads((HERE / "HF_TRAIN10_TIME_WINDOWS_ROOT_v1.json").read_text(encoding="utf-8"))
    old_mse = old_budget["paired_candidate_vs_same_scene_B"]
    old_full_ratio = float(np.sqrt(
        old_mse["candidate"]["mean_scene_band_mse_rad2"]["2_le_f_le_5_Hz"] /
        old_mse["B"]["mean_scene_band_mse_rad2"]["2_le_f_le_5_Hz"]
    ))
    old_window_ratios = {"_".join(map(str, row["window"])): row["candidate_over_B_band_rms"] for row in old_windows["summary"]}

    # Aggregate score summaries using the scorer's exact SO(3) definition and existing TRAIN rows.
    startup = {
        "gate_diagnostics": gate_checks,
        "max_abs_recorded_gate_t_lt_2s_over_10_scenes": max(x["max_abs_recorded_gate_t_lt_2s"] for x in gate_checks),
        "max_abs_applied_minus_parent_input_mps2_t_lt_2s_over_10_scenes": max(x["max_abs_gate_applied_minus_parent_input_mps2_t_lt_2s"] for x in gate_checks),
        "max_candidate_parent_state_abs_t_lt_2s_over_10_scenes": max(x["candidate_parent_state_max_abs_t_lt_2s"] for x in gate_checks),
        "max_candidate_parent_error_rotvec_abs_rad_t_lt_2s_over_10_scenes": max(x["candidate_parent_error_rotvec_max_abs_rad_t_lt_2s"] for x in gate_checks),
        "macro_window_task_rmse_rad": {},
        "candidate_over_B_macro_window_rmse_ratio": {},
    }
    for wname in WINDOWS:
        vals = {m: [row["windows_task_rmse_rad"][wname][m] for row in per_scene] for m in ("candidate", "parent", "B")}
        macros = {m: float(np.mean(x)) for m, x in vals.items()}
        startup["macro_window_task_rmse_rad"][wname] = macros
        startup["candidate_over_B_macro_window_rmse_ratio"][wname] = ratio(macros["candidate"], macros["B"])

    prior = {
        "unwindowed_whole_record_2_to_5_Hz_candidate_over_B_pooled_rmse_ratio": old_full_ratio,
        "unwindowed_time_window_2_to_5_Hz_candidate_over_B_rmse_ratios": old_window_ratios,
        "interpretation": "The prior finite-window FFT had no taper. The 0-2 s and 5-20 s values are historical spectral estimates, not task-score RMSE ratios.",
    }
    out = {
        "schema": "HF_TRAIN10_SPECTRAL_ROBUSTNESS_AUDIT_V1",
        "status": "COMPLETED_TRAIN_ONLY_ROBUSTNESS_AUDIT",
        "scope": "Exactly 10 HF_W09_W14 TRAIN candidate raws, their SHA-bound same-scene B raws, and SHA-bound parent cosine-GRU raws. No Plant calls, TEST or VAL reads, tuning, or inertia reconstruction.",
        "score_definition": "Frozen score_full72 task_SO3_rad = sqrt(mean(theta^2)), theta = norm(Log(R_task^T R_actual)); the analysis reuses hf_task_budget_with_b_v2.task_error (SO(3) rotvec) and confirms every whole-record score against frozen score_raw and TRAIN24 summary.",
        "paired_reference_check": "For each scene, all three raw files have exactly equal 1 kHz time grids and reference acceleration/yaw arrays.",
        "prior_unwindowed_estimates": prior,
        "methods": {
            "welch": "Welch PSD summed across the three SO(3) log-vector components; Hann window; nperseg=2000 samples, 50% overlap (2 s segments, 0.5 Hz bins); run separately with per-segment constant/demean and linear detrending. Integrate bins 2<=f<=5 Hz and f>5 Hz.",
            "zero_phase_bandpass": "Fourth-order Butterworth SOS, applied by sosfiltfilt to the full 20.001-sample trace, then score mean squared vector magnitude in each time slice. 2-5 Hz bandpass and >5 Hz high-pass are offline/noncausal; one-second edge guards are used at the record ends.",
            "aggregation": "Equal-scene pooling: pooled RMSE = sqrt(mean of 10 per-scene band MSEs); also report per-scene sensitivity counts. Ratios above 1 mean the candidate has more band energy than B.",
        },
        "spectral_results": spectral_summary,
        "startup_parent_vs_gate": startup,
        "per_scene_raw_and_task_scores": per_scene,
        "limitations": [
            "Welch reduces endpoint leakage but does not eliminate leakage; 0.5 Hz resolution and a 2 s Hann segment soften the 2 Hz/5 Hz boundaries.",
            "The 2-5 s window has only two overlapping 2 s Welch segments, so its estimate has low averaging and should be read descriptively.",
            "Zero-phase filtering uses future samples and is not deployable evidence. Its band edges are smooth, not brick-wall; the 5-20 s filtered score excludes [19,20] s to avoid end transients.",
            "These offline error spectra diagnose recorded trajectories only. They do not prove causal controller improvement or identify physical mechanism.",
        ],
        "input_sha256": {
            "train24_score_summary": hf.sha256(SUMMARY),
            "frozen_score_full72": hf.sha256(hf.SCORER),
            "frozen_constants_release": hf.sha256(hf.RELEASE),
            "original_helper": hf.sha256(HERE / "hf_task_budget_with_b_v2.py"),
            "audit_script": hf.sha256(Path(__file__)),
            "prior_full_window_report": hf.sha256(HERE / "HF_TRAIN10_WITH_B_ROOT_v1.json"),
            "prior_time_windows_report": hf.sha256(HERE / "HF_TRAIN10_TIME_WINDOWS_ROOT_v1.json"),
            "scene_bindings": {row["scene_id"]: hf.sha256(hf.TRAIN / "bindings" / f"{row['scene_id']}.json") for row in per_scene},
            "raws": {row["scene_id"]: {m: row["raws"][m]["sha256"] for m in row["raws"]} for row in per_scene},
        },
    }

    c2 = spectral_summary["welch"]["hann_demean"]["whole_0_20s"]["2_to_5_Hz"]["candidate_over_B_pooled_rmse_ratio"]
    h2 = spectral_summary["zero_phase_bandpass"]["2_to_5_Hz"]["whole_0_20s"]["candidate_over_B_pooled_rmse_ratio"]
    out["conclusion"] = {
        "original_unwindowed_2_to_5_Hz_estimate": "WITHDRAW_EXACT_MAGNITUDE; independent methods confirm candidate residual energy exceeds B",
        "original_5_to_20_s_near_parity_characterization": "RETRACTED_AS_TOO_STRONG; independent ratios span 1.026 to 1.106, with candidate above B",
        "robust_full_record_2_to_5_Hz_candidate_over_B_rmse_ratio_welch": c2,
        "robust_full_record_2_to_5_Hz_candidate_over_B_rmse_ratio_zero_phase_filter": h2,
        "startup_attribution": "The 0-2 s candidate error trace and gate-applied position input are identical to the parent cosine-GRU on all 10 scenes (gate=0); any candidate-vs-B startup spectral gap is inherited from the parent-vs-B trajectories, not introduced by N4 gating.",
        "causal_claim": "No causal improvement claim is supported by these offline diagnostics.",
    }
    OUT_JSON.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def pct(x):
        return f"{x:.3f}x"

    def pair_text(result):
        rms = result["pooled_band_rmse_rad"]
        return f"{result['candidate_over_B_pooled_rmse_ratio']:.3f}x ({rms['candidate']:.2e}/{rms['B']:.2e} rad)"

    whole_high_welch = spectral_summary["welch"]["hann_demean"]["whole_0_20s"]["above_5_Hz"]
    whole_high_filter = spectral_summary["zero_phase_bandpass"]["above_5_Hz"]["whole_0_20s"]
    high_gap_welch_deg = (whole_high_welch["pooled_band_rmse_rad"]["candidate"] -
                          whole_high_welch["pooled_band_rmse_rad"]["B"]) * 180.0 / np.pi
    md = [
        "# TRAIN-only HF10 \u9891\u8c31\u7a33\u5065\u6027\u5ba1\u8ba1 v1",
        "",
        "## Decision",
        "",
        f"独立方法确认 2–5 Hz 仍有候选残余缺口：无窗 DFT 的候选/B RMSE 比为 {pct(old_full_ratio)}，Hann 去均值 Welch 为 {pct(c2)}，零相位滤波为 {pct(h2)}（>1 均表示候选频带误差高于 B）。保留“候选在 2–5 Hz 高于 B”的方向；撤回无窗 DFT 的精确幅值作为稳健估计。",
        "",
        f"撤回仅凭无窗 DFT 将 5–20 s 描述为近持平的强归因：Hann Welch 与零相位滤波分别给出 {spectral_summary['welch']['hann_demean']['5_20s']['2_to_5_Hz']['candidate_over_B_pooled_rmse_ratio']:.3f}x 与 {spectral_summary['zero_phase_bandpass']['2_to_5_Hz']['5_20s']['candidate_over_B_pooled_rmse_ratio']:.3f}x；方向一致为候选略高，但幅值受估计器影响。旧 0–2 s 的 {old_window_ratios.get('0_2', float('nan')):.3f}x 比值则由 parent-vs-B 基线差解释，见启动归因。",
        "",
        "## 诊断设置与结果",
        "",
        "评分沿用冻结 `score_full72_candidate_v1.score_raw`：`sqrt(mean(theta^2))`，`theta = ||Log(R_task^T R_actual)||`；审计将每个候选、同场景 B、parent 的全程分数与冻结 scorer 和 TRAIN24 汇总逐项核对。频谱输入为同一 SO(3) log rotvec。",
        "",
        "Welch 用 2 s Hann 分段、50% 重叠、0.5 Hz 频率间隔，分别做每段去均值和线性去趋势；比较 2–5 Hz 与 >5 Hz。第二种估计把四阶 Butterworth 2–5 Hz bandpass 和 >5 Hz high-pass 用 `sosfiltfilt` 离线零相位施加到完整轨迹，再按时间窗积分。下表是等场景合并 RMSE 比值，>1 表示候选高于 B。",
        "\u6ce8\uff1aWelch 0\u20132 s \u4ec5\u67091\u6bb5\uff0c2\u20135 s \u4ec52\u4e2a\u91cd\u53e0\u6bb5\uff0c\u4f30\u8ba1\u7a33\u5b9a\u6027\u4f4e\u3002",
        "",
        "| 方法 | 窗口 | 2–5 Hz 候选/B（RMSE 候选/B） | >5 Hz 候选/B（RMSE 候选/B） | 备注 |",
        "|---|---:|---:|---:|---|",
    ]
    for method, config in (("Welch Hann 去均值", "hann_demean"), ("Welch Hann 线性去趋势", "hann_linear_detrend")):
        for wname, label in (("whole_0_20s", "0–20 s"), ("0_2s", "0–2 s"), ("2_5s", "2–5 s"), ("5_20s", "5–20 s")):
            bands = spectral_summary["welch"][config][wname]
            md.append(f"| {method} | {label} | {pair_text(bands['2_to_5_Hz'])} | {pair_text(bands['above_5_Hz'])} | 0.5 Hz；{bands['2_to_5_Hz']['welch_segments_by_window']} 段 |")
    for wname, window_label, note in (("whole_0_20s", "0–20 s", "裁去两端各 1 s"),
                                      ("2_5s", "2–5 s", "完整内部窗"),
                                      ("5_20s", "5–20 s", "计分至 19 s")):
        bp = spectral_summary["zero_phase_bandpass"]["2_to_5_Hz"][wname]
        hp = spectral_summary["zero_phase_bandpass"]["above_5_Hz"][wname]
        md.append(f"| 零相位滤波 | {window_label} | {pair_text(bp)} | {pair_text(hp)} | 非因果；{note} |")
    md += [
        "",
        f"全记录 Welch 的 2–5 Hz 分辨率为 0.5 Hz；2–5 s 仅有两个重叠的 2 s 段，统计稳定性低。Hann 可压低端点旁瓣但不能消除泄漏；滤波截止是平滑过渡，不等价于砖墙频带。零相位滤波使用未来数据，5–20 s 结果裁去记录末端 1 s。",
        f">5 Hz 的绝对量很小：全记录 Welch 候选/B pooled RMSE 为 {whole_high_welch['pooled_band_rmse_rad']['candidate']:.2e}/{whole_high_welch['pooled_band_rmse_rad']['B']:.2e} rad（差 {high_gap_welch_deg:.3g}°），零相位滤波为 {whole_high_filter['pooled_band_rmse_rad']['candidate']:.2e}/{whole_high_filter['pooled_band_rmse_rad']['B']:.2e} rad；不应只强调大比值。",
        "",
        "## 启动归因",
        "",
        f"10/10 场景在 `t < 2 s` 的 candidate 与 parent 全部 state 最大差为 {startup['max_candidate_parent_state_abs_t_lt_2s_over_10_scenes']:.3g}，SO(3) log-vector 最大差为 {startup['max_candidate_parent_error_rotvec_abs_rad_t_lt_2s_over_10_scenes']:.3g} rad；候选 raw 内记录的 gate 最大值为 {startup['max_abs_recorded_gate_t_lt_2s_over_10_scenes']:.3g}，gate 输出与 parent 输入最大差为 {startup['max_abs_applied_minus_parent_input_mps2_t_lt_2s_over_10_scenes']:.3g} m/s²。启动期 candidate 与 parent 完全一致，2–5 Hz 的旧 0–2 s candidate/B 差已存在于 parent-vs-B，不能归因于 N4 gate。",
        "",
        f"\u542f\u52a8\u671f\u5168\u9891 task RMSE\uff1acandidate=parent {startup['macro_window_task_rmse_rad']['0_2s']['candidate']:.5f} rad\uff0cB {startup['macro_window_task_rmse_rad']['0_2s']['B']:.5f} rad\uff0ccandidate/B={startup['candidate_over_B_macro_window_rmse_ratio']['0_2s']:.3f}\uff1b\u65e7 2.904x \u662f2\u20135 Hz \u65e0\u7a97DFT\u9891\u5e26\u6bd4\uff0c\u4e0d\u80fd\u4e0e\u5168\u9891task score \u7b49\u540c\u3002",
        "",
        "## 下一步训练侧检验",
        "",
        "用现有 TRAIN_C5_24 做按场景/风况分组的 out-of-fold 训练核验：只在其他 TRAIN folds 拟合任何 2–5 Hz 因果修正，在留出 TRAIN fold 上同时记录 parent、N4 candidate、B 的每场景绝对 2–5 Hz RMSE、>5 Hz 绝对 RMSE 与全程 task SO(3) RMSE。固定启动前 2 s 为 parent 旁路，不对 gate 做启动调参；以全程任务分数不退化作为和频带指标并列的检查。不要用上述同一 HF10 窗口选超参。",
        "## 范围与限制",
        "",
        "仅读取锁定 TRAIN HF10 的 candidate、绑定的同场景 B 和 parent raw、TRAIN 汇总、冻结评分代码/常数与已有 TRAIN 审计 JSON；无 Plant、TEST、VAL、惯量重建或调参。频谱诊断只描述已记录误差轨迹，不能证明闭环因果改善。",
        "",
        f"可复现脚本：`{Path(__file__).name}`。机器可读明细：`{OUT_JSON.name}`。",
    ]
    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps({
        "json": str(OUT_JSON), "markdown": str(OUT_MD), "scenes": len(per_scene),
        "old_full_dft_ratio": old_full_ratio, "welch_2_5_ratio": c2,
        "zero_phase_2_5_ratio": h2,
        "startup_candidate_parent_max_rotvec_diff": startup["max_candidate_parent_error_rotvec_abs_rad_t_lt_2s_over_10_scenes"],
    }, indent=2))


if __name__ == "__main__":
    main()
