import csv
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import h5py
import numpy as np

HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
BASE = STUDY.parent
SCENES = (
    "DL1018_VAL_T1_C08_W15", "DL1018_VAL_T2_C05_W15", "DL1018_VAL_T3_C02_W15",
    "DL1018_VAL_T1_C05_W12", "DL1018_VAL_T2_C02_W12", "DL1018_VAL_T3_C00_W13",
)
METHODS = ("ncmd_GRU", "cosine_GRU", "constant_GRU", "B", "C5")
COMPARE = METHODS[1:]
MAIN = ("Q_m", "SO3_rad", "inner_tracking_rad")
COSINE_DIR = BASE / "gru_stream_cosine_dev_v1" / "audits"
COSINE_SUMMARY = COSINE_DIR / "COSINE_SIX_SCENE_SUMMARY_v1.json"
COSINE_HELPER = COSINE_DIR / "summarize_cosine_six_scene_v1.py"
FIRST_APPROVAL = STUDY / "ROOT_FIRST_FLIGHT_APPROVAL_v1.json"
REST_APPROVAL = STUDY / "ROOT_REMAINING_FIVE_APPROVAL_v1.json"
FIRST_SCORE = STUDY / "ROOT_FIRST_SCENE_PYTHON_METRICS_v1.json"


def readj(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def load_helper():
    spec = importlib.util.spec_from_file_location("cosine_score_helper", COSINE_HELPER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def peak_metrics(helper, path, gravity, max_tilt):
    with h5py.File(path, "r") as raw:
        log = raw["log"]
        state = helper.a(log, "state").T
        time = helper.a(log, "time").reshape(-1)
        reference = raw["scene/reference"]
        pos_ref = helper.a(reference, "position").T
        accel = helper.a(reference, "acceleration").T.copy()
        yaw = helper.a(reference, "yaw").reshape(-1)
        inner_ref = helper.a(log, "filtered_attitude_reference").T
    assert state.shape == (20001, 12) and pos_ref.shape == accel.shape == (20001, 3)
    assert inner_ref.shape == (20000, 3) and time.shape == (20001,)
    accel[:, 2] += gravity
    aa = np.cos(yaw) * accel[:, 0] + np.sin(yaw) * accel[:, 1]
    bb = np.sin(yaw) * accel[:, 0] - np.cos(yaw) * accel[:, 1]
    roll = np.arctan2(bb, np.hypot(accel[:, 2], aa))
    pitch = np.arctan2(aa, accel[:, 2])
    scale = np.minimum(1.0, max_tilt / np.maximum(np.hypot(roll, pitch), np.finfo(float).eps))
    task_ref = np.column_stack((roll * scale, pitch * scale, yaw))
    pos_err = state[:, :3] - pos_ref
    task_euler = helper.wrap(task_ref - state[:, 6:9])
    inner_euler = helper.wrap(inner_ref - state[:20000, 6:9])
    task_so3 = helper.so3(state[:, 6:9], task_ref)
    inner_so3 = helper.so3(state[:20000, 6:9], inner_ref)
    masks = {
        "all": (np.ones(20001, dtype=bool), np.ones(20000, dtype=bool)),
        "0_5s": (time < 5.0, time[:20000] < 5.0),
        "15_20s": (time >= 15.0, time[:20000] >= 15.0),
    }
    peaks = {}
    for phase, (sm, im) in masks.items():
        peaks[phase] = {
            "position_xyz_peak_abs_m": np.max(np.abs(pos_err[sm]), axis=0).tolist(),
            "position_norm_peak_m": float(np.max(np.linalg.norm(pos_err[sm], axis=1))),
            "task_wrapped_euler_peak_abs_rad": np.max(np.abs(task_euler[sm]), axis=0).tolist(),
            "task_SO3_peak_rad": float(np.max(task_so3[sm])),
            "inner_wrapped_euler_peak_abs_rad": np.max(np.abs(inner_euler[im]), axis=0).tolist(),
            "inner_SO3_peak_rad": float(np.max(inner_so3[im])),
        }
    return peaks


def write_csv(path, rows):
    with path.open("x", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    helper = load_helper()
    cached = readj(COSINE_SUMMARY)
    first_approval, rest_approval = readj(FIRST_APPROVAL), readj(REST_APPROVAL)
    gravity = float(cached["metric_constants"]["gravity_mps2"])
    max_tilt = float(cached["metric_constants"]["max_tilt_rad"])
    old_rows = {r["scene_id"]: r for r in cached["rows"]}
    assert tuple(cached["scene_order"]) == SCENES

    rows, pending, input_hashes = [], [], {}
    for sid in SCENES:
        status_path = STUDY / "runs" / sid / "run_status.json"
        if not status_path.is_file():
            pending.append({"scene_id": sid, "state": "NO_STATUS"})
            continue
        status = readj(status_path)
        if status.get("state") != "COMPLETED":
            pending.append({"scene_id": sid, "state": status.get("state"), "status_value": status.get("status_value")})
            continue
        raw_path = Path(status["raw_path"])
        audit_path = HERE / f"{sid}_GRU_STREAM_RAW_AUDIT.json"
        if not raw_path.is_file() or not audit_path.is_file():
            raise FileNotFoundError(f"{sid}: completed status lacks raw/audit")
        raw_sha, status_sha, audit_sha = helper.sha(raw_path), helper.sha(status_path), helper.sha(audit_path)
        audit = readj(audit_path)
        expected_release = first_approval["release_sha256"] if sid == SCENES[0] else rest_approval["release_sha256"]
        assert status["candidate"] == "GRU32_STREAM72_NCMD_S2026102001"
        assert status["Plant_calls"] == 1 and not status["TEST_read"]
        assert status["transitions"] == 20000 and status["state_samples"] == 20001
        assert status["raw_sha256"].lower() == raw_sha.lower()
        assert status["release_sha256"].lower() == expected_release.lower()
        assert audit["status"] == "PASS_INDEPENDENT_GRU_STREAM_RAW_REPLAY"
        assert audit["candidate_raw_sha256"].lower() == raw_sha.lower()
        assert audit["model_sha256"].lower() == "cd5870a48deac9eb3540c3662c59ec4212965c333669b730cdd4f6519d364de6"

        candidate = helper.score(raw_path, gravity, max_tilt)
        candidate["peak_phase"] = peak_metrics(helper, raw_path, gravity, max_tilt)
        candidate.update({
            "raw_path": str(raw_path), "raw_sha256": raw_sha,
            "raw_audit_sha256": audit_sha, "run_status_sha256": status_sha,
            "release_sha256": status["release_sha256"], "audit_status": audit["status"],
            "run_status": status.get("status_value"),
            "safety_stop_reason": status.get("safety_stop_reason", ""),
            "Plant_calls": status["Plant_calls"],
        })
        methods = {"ncmd_GRU": candidate}
        for method in ("cosine_GRU", "constant_GRU", "B", "C5"):
            old = old_rows[sid]["methods"][method]
            old_raw = Path(old["raw_path"])
            assert helper.sha(old_raw).lower() == old["raw_sha256"].lower()
            methods[method] = dict(old)
            methods[method]["peak_phase"] = peak_metrics(helper, old_raw, gravity, max_tilt)

        comparisons = {}
        for other in COMPARE:
            comparisons[other] = {}
            for metric in MAIN:
                delta = candidate[metric] - methods[other][metric]
                comparisons[other][metric] = {
                    "delta": float(delta),
                    "relative_change_pct": float(100 * delta / methods[other][metric]),
                    "win": bool(delta < -1e-12), "loss": bool(delta > 1e-12),
                    "tie": bool(abs(delta) <= 1e-12),
                }
        rows.append({"scene_id": sid, "stratum": "W15" if sid.endswith("W15") else "HF",
                     "methods": methods, "ncmd_vs": comparisons})
        input_hashes.update({str(raw_path): raw_sha, str(status_path): status_sha, str(audit_path): audit_sha})

        if sid == SCENES[0] and FIRST_SCORE.is_file():
            golden = readj(FIRST_SCORE)["candidate"]
            for metric in MAIN:
                assert abs(candidate[metric] - golden[metric]) <= 2e-10, (sid, metric, candidate[metric], golden[metric])

    if not rows:
        raise RuntimeError(f"No completed audited NCMD scenes; pending={pending}")
    full = len(rows) == len(SCENES)
    prefix = "NCMD_SIX_SCENE" if full else "NCMD_PROGRESS"
    outputs = [HERE / f"{prefix}_SUMMARY_v1.json", HERE / f"{prefix}_PAIRED_v1.csv",
               HERE / f"{prefix}_AXIS_PHASE_v1.csv", HERE / f"{prefix}_SUMMARY_v1.md"]
    for path in outputs:
        if path.exists():
            raise FileExistsError(path)

    groups = {}
    for group, selected in (("COMPLETED", rows), ("W15", [r for r in rows if r["stratum"] == "W15"]),
                            ("HF", [r for r in rows if r["stratum"] == "HF"])):
        groups[group] = {
            "scene_count": len(selected),
            "macro_mean": {m: {k: float(np.mean([r["methods"][m][k] for r in selected])) for k in MAIN} for m in METHODS},
            "relative_change_pct": {
                o: {k: float(100 * (np.mean([r["methods"]["ncmd_GRU"][k] for r in selected])
                                      - np.mean([r["methods"][o][k] for r in selected]))
                              / np.mean([r["methods"][o][k] for r in selected])) for k in MAIN}
                for o in COMPARE},
            "wins": {o: {k: sum(r["ncmd_vs"][o][k]["win"] for r in selected) for k in MAIN} for o in COMPARE},
            "losses": {o: {k: sum(r["ncmd_vs"][o][k]["loss"] for r in selected) for k in MAIN} for o in COMPARE},
            "worst_scene_peak": {
                m: {k: float(max(r["methods"][m]["peak_phase"]["all"][k] for r in selected))
                    for k in ("position_norm_peak_m", "task_SO3_peak_rad", "inner_SO3_peak_rad")}
                for m in METHODS},
        }
    wins = {o: {k: [r["scene_id"] for r in rows if r["ncmd_vs"][o][k]["win"]] for k in MAIN} for o in COMPARE}
    losses = {o: {k: [r["scene_id"] for r in rows if r["ncmd_vs"][o][k]["loss"]] for k in MAIN} for o in COMPARE}
    safety = {m: {k: int(sum(r["methods"][m]["safety"][k] for r in rows))
                  for k in ("motor_saturation_samples", "generalized_clip_samples", "tilt_limited_samples")}
              for m in METHODS}

    paired, axes = [], []
    for row in rows:
        flat = {"scene_id": row["scene_id"], "stratum": row["stratum"]}
        for method in METHODS:
            result = row["methods"][method]
            for metric in MAIN:
                flat[f"{method}_{metric}"] = result[metric]
            for key in ("motor_saturation_samples", "generalized_clip_samples", "tilt_limited_samples"):
                flat[f"{method}_{key}"] = result["safety"][key]
            if method == "ncmd_GRU":
                for key in ("raw_sha256", "raw_audit_sha256", "run_status_sha256", "release_sha256"):
                    flat[f"ncmd_{key}"] = result.get(key)
            else:
                flat[f"{method}_raw_sha256"] = result["raw_sha256"]
            for phase, vals in result["axis_phase"].items():
                peak = result["peak_phase"][phase]
                axes.append({
                    "scene_id": row["scene_id"], "stratum": row["stratum"], "method": method, "phase": phase,
                    "state_samples": vals["state_samples"], "inner_samples": vals["inner_samples"],
                    "position_x_rmse_m": vals["position_xyz_rmse_m"][0],
                    "position_y_rmse_m": vals["position_xyz_rmse_m"][1],
                    "position_z_rmse_m": vals["position_xyz_rmse_m"][2],
                    "position_x_peak_abs_m": peak["position_xyz_peak_abs_m"][0],
                    "position_y_peak_abs_m": peak["position_xyz_peak_abs_m"][1],
                    "position_z_peak_abs_m": peak["position_xyz_peak_abs_m"][2],
                    "position_norm_peak_m": peak["position_norm_peak_m"],
                    "task_roll_wrapped_euler_rmse_rad": vals["task_wrapped_euler_rmse_rad"][0],
                    "task_pitch_wrapped_euler_rmse_rad": vals["task_wrapped_euler_rmse_rad"][1],
                    "task_yaw_wrapped_euler_rmse_rad": vals["task_wrapped_euler_rmse_rad"][2],
                    "task_roll_peak_abs_rad": peak["task_wrapped_euler_peak_abs_rad"][0],
                    "task_pitch_peak_abs_rad": peak["task_wrapped_euler_peak_abs_rad"][1],
                    "task_yaw_peak_abs_rad": peak["task_wrapped_euler_peak_abs_rad"][2],
                    "task_SO3_peak_rad": peak["task_SO3_peak_rad"],
                    "inner_roll_wrapped_euler_rmse_rad": vals["inner_wrapped_euler_rmse_rad"][0],
                    "inner_pitch_wrapped_euler_rmse_rad": vals["inner_wrapped_euler_rmse_rad"][1],
                    "inner_yaw_wrapped_euler_rmse_rad": vals["inner_wrapped_euler_rmse_rad"][2],
                    "inner_roll_peak_abs_rad": peak["inner_wrapped_euler_peak_abs_rad"][0],
                    "inner_pitch_peak_abs_rad": peak["inner_wrapped_euler_peak_abs_rad"][1],
                    "inner_yaw_peak_abs_rad": peak["inner_wrapped_euler_peak_abs_rad"][2],
                    "inner_SO3_peak_rad": peak["inner_SO3_peak_rad"],
                })
        for other in COMPARE:
            for metric in MAIN:
                flat[f"ncmd_win_vs_{other}_{metric}"] = row["ncmd_vs"][other][metric]["win"]
                flat[f"ncmd_loss_vs_{other}_{metric}"] = row["ncmd_vs"][other][metric]["loss"]
        paired.append(flat)

    release_path = STUDY / "RELEASE.json"
    release_sha = helper.sha(release_path)
    stage2 = readj(STUDY / "ROOT_RELEASE_STAGE2_SNAPSHOT_v1.json")
    resource = {
        "authorized_calls_stage1": int(first_approval["authorized_Plant_calls"]),
        "authorized_calls_stage2": int(stage2["authorized_Plant_calls"]),
        "completed_candidate_calls": sum(r["methods"]["ncmd_GRU"]["Plant_calls"] for r in rows),
        "completed_scene_count": len(rows), "pending_scenes": pending,
        "first_release_sha256": first_approval["release_sha256"],
        "remaining_five_release_sha256": rest_approval["release_sha256"],
        "current_release_sha256": release_sha,
        "current_release_Plant_calls": int(readj(release_path)["Plant_calls"]),
        "training_jobs_in_deployment_study": 0, "TEST_read": False,
    }
    report = {
        "schema": "GRU_STREAM_NCMD_SIX_SCENE_METRICS_V1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_READ_ONLY_SIX_SCENE_SUMMARY" if full else "PASS_READ_ONLY_PARTIAL_SCENE_SUMMARY",
        "candidate": "GRU32_STREAM72_NCMD_S2026102001",
        "model_sha256": "cd5870a48deac9eb3540c3662c59ec4212965c333669b730cdd4f6519d364de6",
        "expected_scene_order": list(SCENES), "completed_scenes": [r["scene_id"] for r in rows],
        "groups": groups, "wins": wins, "losses": losses, "safety_totals": safety,
        "resource_ledger": resource,
        "metric_definitions": {
            "primary": "Q uses 20001 top-level scene/reference position states; SO3 is geodesic RMSE to top-level scene/reference-derived task attitude; inner is geodesic RMSE over 20000 transitions.",
            "axis_note": "wrapped Euler roll/pitch/yaw values are coordinate-axis errors, not SO(3) components and do not replace SO(3).",
            "windows": "0-5s is [0,5); 15-20s uses state [15,20] and inner [15,20).",
            "peaks": "per-scene maxima of position norm, task SO3, inner SO3, and absolute wrapped Euler axes, full and by phase.",
            "score_source": "Reuses the reviewed cosine score() helper; candidate and comparison raw are checked as 20001 states / 20000 transitions.",
        },
        "metric_constants": cached["metric_constants"],
        "provenance_sha256": {
            "cosine_summary": helper.sha(COSINE_SUMMARY), "cosine_helper": helper.sha(COSINE_HELPER),
            "first_approval": helper.sha(FIRST_APPROVAL), "remaining_approval": helper.sha(REST_APPROVAL),
            "first_scene_root_score": helper.sha(FIRST_SCORE), "current_release": release_sha,
        },
        "input_sha256": input_hashes, "rows": rows,
        "interpretation_limit": "Read-only paired scoring of completed audited runs; not a stability proof and does not authorize additional flights.",
    }
    lines = [
        "# NCMD GRU 配对结果", "",
        f"状态：{report['status']}；已完成 {len(rows)}/6 场。只读使用现有raw与比较缓存。",
        "",
        "SO(3)为测地角RMSE；wrapped Euler轴误差是坐标分解，不是SO(3)分量。",
        "",
        "| 分组 | 方法 | Q (mm) | Task SO(3) (mrad) | Inner (mrad) |",
        "|---|---|---:|---:|---:|",
    ]
    for group in ("COMPLETED", "W15", "HF"):
        for method in METHODS:
            values = groups[group]["macro_mean"][method]
            lines.append(f"| {group} | {method} | {1000*values['Q_m']:.4f} | {1000*values['SO3_rad']:.4f} | {1000*values['inner_tracking_rad']:.4f} |")
    lines += ["", "## 输赢", ""]
    for other in COMPARE:
        lines.append(f"{other}: " + "; ".join(
            f"{metric} wins {len(wins[other][metric])}/{len(rows)}, losses {','.join(losses[other][metric]) or 'none'}"
            for metric in MAIN))
    lines += ["", "逐轴RMSE、逐轴峰值、SO(3)峰值、raw/audit/release SHA见CSV。报告不是稳定性证明。", ""]
    report_path, paired_path, axes_path, md_path = outputs
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_csv(paired_path, paired)
    write_csv(axes_path, axes)
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": report["status"], "completed_scenes": report["completed_scenes"],
                      "pending": pending, "groups": groups, "wins": wins, "losses": losses,
                      "safety": safety, "outputs": [str(p) for p in outputs]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
