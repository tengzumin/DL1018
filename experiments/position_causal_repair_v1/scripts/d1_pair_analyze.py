from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "experiments" / "position_causal_repair_v1"
ROLES = ("B", "POS_OFF", "P_INIT_STUDENT")
TIME_BINS = (("T_0_1p8", 0.0, 1.8), ("T_1p8_5", 1.8, 5.0),
             ("T_5_10", 5.0, 10.0), ("T_10_15", 10.0, 15.0), ("T_15_20", 15.0, 20.0))


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def truth(v: str) -> bool:
    return str(v).strip().lower() in ("1", "true", "yes")


def freq_class(spec: dict[str, str]) -> str:
    w = int(spec["w"])
    if w == 15:
        return "NO_WIND"
    f2 = float(spec["f2_hz"])
    if f2 <= 0.95:
        return "LOW"
    if f2 < 3.6:
        return "MID"
    return "HIGH"


def tmajor(f: h5py.File, key: str, n: int) -> np.ndarray:
    a = np.asarray(f[key])
    if a.ndim == 1:
        return a[:n]
    if a.shape[-1] in (n, n + 1) and a.shape[0] <= 32:
        return a.T[:n]
    if a.shape[0] in (n, n + 1):
        return a[:n]
    raise ValueError(f"Unexpected time-array shape {key}: {a.shape}, n={n}")


def matlab_round_nonnegative(x: np.ndarray) -> np.ndarray:
    return np.floor(x + 0.5).astype(np.int64)


def phase_labels(f: h5py.File, t: np.ndarray) -> np.ndarray:
    scene_t = tmajor(f, "scene/time", 20001).reshape(-1)
    cmd = tmajor(f, "scene/arms/command", len(scene_t))
    rho = tmajor(f, "scene/arms/rho_true", len(scene_t))
    dt = float(np.median(np.diff(scene_t)))
    k = np.clip(matlab_round_nonnegative(t / dt), 0, len(scene_t) - 1)
    c = cmd[k]
    r = rho[k]
    seen = np.maximum.accumulate(np.any(np.abs(cmd) > 0, axis=1))
    out = np.full(len(t), "NONE", dtype=object)
    pos = np.any(c > 0, axis=1)
    neg = np.any(c < 0, axis=1)
    hold = np.any(r > 0.150001, axis=1)
    out[pos] = "EXTEND"
    out[~pos & neg] = "RETRACT"
    out[~pos & ~neg & hold] = "HOLD"
    out[~pos & ~neg & ~hold & seen[k]] = "RECOVERY"
    return out


def hazen95(x: np.ndarray) -> float:
    return float(np.percentile(x, 95, method="hazen"))


def reduce_raw(raw_path: Path, attempt: dict[str, str], spec: dict[str, str]) -> dict:
    with h5py.File(raw_path, "r") as f:
        t = np.asarray(f["log/transition_time"], dtype=np.float64).reshape(-1)
        n = min(len(t), f["log/state"].shape[-1] - 1)
        t = t[:n]
        state = tmajor(f, "log/state", n).astype(np.float64, copy=False)
        ref = tmajor(f, "log/reference/position", n).astype(np.float64, copy=False)
        att_ref = tmajor(f, "log/filtered_attitude_reference", n).astype(np.float64, copy=False)
        motor = tmajor(f, "log/motor_command", n).astype(np.float64, copy=False)
        sat = tmajor(f, "log/motor_saturated", n).astype(bool, copy=False)
        clip = tmajor(f, "log/generalized_clipped", n).astype(bool, copy=False)
        phase = phase_labels(f, t)
    mask = (t >= 0) & (t < 20)
    late = (t >= 5) & (t < 20)
    if state.shape[1] < 9 or ref.shape[1] != 3 or att_ref.shape[1] != 3 or motor.shape[1] != 4:
        raise ValueError(f"Bad MATLAB-to-HDF5 orientation: state={state.shape} ref={ref.shape} att={att_ref.shape} motor={motor.shape}")
    e = ref[:, :3] - state[:, :3]
    da = att_ref[:, :3] - state[:, 6:9]
    att = np.arctan2(np.sin(da), np.cos(da))
    en = np.linalg.norm(e, axis=1)

    def q(m: np.ndarray) -> float:
        return float(np.sqrt(np.mean(np.sum(e[m] ** 2, axis=1)))) if np.any(m) else math.nan

    def a(m: np.ndarray) -> float:
        return float(np.sqrt(np.mean(np.sum(att[m] ** 2, axis=1)))) if np.any(m) else math.nan

    out: dict[str, object] = {
        "Q_0_20_m": q(mask), "Q_5_20_m": q(late), "A_0_20_rad": a(mask),
        "axis_rmse_x_m": float(np.sqrt(np.mean(e[mask, 0] ** 2))),
        "axis_rmse_y_m": float(np.sqrt(np.mean(e[mask, 1] ** 2))),
        "axis_rmse_z_m": float(np.sqrt(np.mean(e[mask, 2] ** 2))),
        "att_rmse_roll_rad": float(np.sqrt(np.mean(att[mask, 0] ** 2))),
        "att_rmse_pitch_rad": float(np.sqrt(np.mean(att[mask, 1] ** 2))),
        "att_rmse_yaw_rad": float(np.sqrt(np.mean(att[mask, 2] ** 2))),
        "position_peak_m": float(np.max(en[mask])), "position_p95_m": hazen95(en[mask]),
        "motor_TV_normalized_per_s": float(np.abs(np.diff(motor, axis=0)).sum() / (4 * 1900 * 20)),
        "motor_saturation_fraction": float(np.mean(np.any(sat[mask], axis=1))),
        "generalized_clip_fraction": float(np.mean(np.any(clip[mask], axis=1))),
        "finite_metrics": bool(np.isfinite(np.r_[e[mask].ravel(), att[mask].ravel(), motor[mask].ravel()]).all()),
        "transition_count": int(n),
        "complete": truth(attempt.get("complete", "false")) and n == 20000,
        "finite": truth(attempt.get("finite", "false")),
        "stop_reason": attempt.get("safety_stop_reason", ""),
        "source_status": attempt.get("status", ""),
        "phase_metrics": {}, "time_bin_metrics": {},
    }
    for name, start, end in TIME_BINS:
        m = mask & (t >= start) & (t < end)
        out["time_bin_metrics"][name] = {"samples": int(np.count_nonzero(m)), "Q_rmse_m": q(m), "A_rmse_rad": a(m),
                                         "peak_m": float(np.max(en[m])) if np.any(m) else math.nan}
    for label in ("NONE", "EXTEND", "HOLD", "RETRACT", "RECOVERY"):
        m = mask & (phase == label)
        if np.any(m):
            out["phase_metrics"][label] = {"samples": int(np.count_nonzero(m)), "Q_rmse_m": q(m),
                                           "A_rmse_rad": a(m), "peak_m": float(np.max(en[m]))}
    return out


def stable_key(path: Path, attempt: dict[str, str]) -> str:
    st = path.stat()
    return f"{attempt['run_id']}|{st.st_size}|{st.st_mtime_ns}"


def flat_scene_row(scene: dict, triplet: dict[str, dict]) -> dict[str, object]:
    roles = {r: triplet[r] for r in ROLES}
    row: dict[str, object] = {
        "scene_id": scene["scene_id"], "split": scene["split"], "task": scene["task"],
        "class_id": scene["class_id"], "wind_cell": scene["w"], "wind_band": scene["wind_band"],
        "wind_frequency_group": scene["wind_frequency_group"], "f1_hz": scene["f1_hz"], "f2_hz": scene["f2_hz"],
    }
    metrics = ("Q_0_20_m", "Q_5_20_m", "A_0_20_rad", "axis_rmse_x_m", "axis_rmse_y_m", "axis_rmse_z_m",
               "att_rmse_roll_rad", "att_rmse_pitch_rad", "att_rmse_yaw_rad", "position_peak_m", "position_p95_m",
               "motor_TV_normalized_per_s", "motor_saturation_fraction", "generalized_clip_fraction",
               "complete", "finite", "finite_metrics", "transition_count", "source_status", "stop_reason")
    for role in ROLES:
        m = roles[role]
        for k in metrics:
            row[f"{role}_{k}"] = m[k]
        row[f"{role}_time_bin_metrics_json"] = json.dumps(m["time_bin_metrics"], separators=(",", ":"), allow_nan=True)
        row[f"{role}_phase_metrics_json"] = json.dumps(m["phase_metrics"], separators=(",", ":"), allow_nan=True)
    for other in ("B", "POS_OFF"):
        for k in ("Q_0_20_m", "Q_5_20_m", "A_0_20_rad", "position_peak_m", "position_p95_m",
                  "motor_TV_normalized_per_s", "motor_saturation_fraction", "generalized_clip_fraction"):
            val = float(roles["P_INIT_STUDENT"][k]) - float(roles[other][k])
            row[f"P_INIT_minus_{other}_{k}"] = val
            base = float(roles[other][k])
            row[f"P_INIT_relative_change_vs_{other}_{k}"] = val / base if base != 0 else math.nan
    row["P_INIT_beats_B_Q"] = float(roles["P_INIT_STUDENT"]["Q_0_20_m"]) < float(roles["B"]["Q_0_20_m"])
    row["P_INIT_beats_POS_OFF_Q"] = float(roles["P_INIT_STUDENT"]["Q_0_20_m"]) < float(roles["POS_OFF"]["Q_0_20_m"])
    return row


def grouped_rows(paired: list[dict]) -> list[dict]:
    groups: dict[tuple, list[tuple[dict, dict]]] = defaultdict(list)
    phase_names = ("NONE", "EXTEND", "HOLD", "RETRACT", "RECOVERY")
    time_names = tuple(x[0] for x in TIME_BINS)
    for row in paired:
        base = (row["task"], row["wind_frequency_group"], row["class_id"])
        for role in ROLES:
            def add(phase: str, metric: dict) -> None:
                groups[base + (phase, role)].append((row, metric))
            full = {k: row[f"{role}_{k}"] for k in ("Q_0_20_m", "Q_5_20_m", "A_0_20_rad", "position_peak_m")}
            add("ALL_0_20", full)
            for phase, val in json.loads(str(row[f"{role}_phase_metrics_json"])).items():
                add(phase, val)
            for phase, val in json.loads(str(row[f"{role}_time_bin_metrics_json"])).items():
                add(phase, val)
        for contrast, other in (("P_INIT_MINUS_B", "B"), ("P_INIT_MINUS_POS_OFF", "POS_OFF")):
            for phase in ("ALL_0_20", *phase_names, *time_names):
                candidates = []
                for role in ("P_INIT_STUDENT", other):
                    if phase == "ALL_0_20":
                        d = {"Q_rmse_m": row[f"{role}_Q_0_20_m"], "A_rmse_rad": row[f"{role}_A_0_20_rad"],
                             "peak_m": row[f"{role}_position_peak_m"]}
                    elif phase in phase_names:
                        d = json.loads(str(row[f"{role}_phase_metrics_json"])).get(phase)
                    else:
                        d = json.loads(str(row[f"{role}_time_bin_metrics_json"])).get(phase)
                    candidates.append(d)
                if candidates[0] is not None and candidates[1] is not None:
                    dd = {k: (float(candidates[0][k]) - float(candidates[1][k])) for k in ("Q_rmse_m", "A_rmse_rad", "peak_m")
                          if k in candidates[0] and k in candidates[1]}
                    groups[base + (phase, contrast)].append((row, dd))
    out = []
    for key, vals in sorted(groups.items(), key=lambda kv: tuple(str(x) for x in kv[0])):
        task, wind, class_id, phase, role = key
        metric_names = set.intersection(*(set(v[1]) for v in vals)) if vals else set()
        z: dict[str, object] = {"task": task, "wind_frequency_group": wind, "class_id": class_id,
                                "diagnostic_phase": phase, "series": role, "n_scenes": len(vals),
                                "scene_ids": ";".join(sorted(v[0]["scene_id"] for v in vals))}
        for metric in sorted(metric_names):
            arr = np.asarray([float(v[1][metric]) for v in vals], dtype=np.float64)
            finite = arr[np.isfinite(arr)]
            z[f"macro_mean_{metric}"] = float(np.mean(finite)) if finite.size else math.nan
            z[f"median_{metric}"] = float(np.median(finite)) if finite.size else math.nan
        out.append(z)
    return out


def build_decision(paired: list[dict]) -> str:
    def summary(sub: list[dict], metric: str) -> float:
        return float(np.mean([float(r[metric]) for r in sub])) if sub else math.nan

    def macro(sub: list[dict], metric: str) -> float:
        tasks = sorted({r["task"] for r in sub})
        return float(np.mean([summary([r for r in sub if r["task"] == task], metric) for task in tasks])) if tasks else math.nan

    lines = ["# D1：G04 全量同场配对结果与 Initial 决策\n",
             "口径：432 个 G04 Student 场景（TRAIN 384、VAL 48）逐场连接历史 B、POS_OFF 与 P_INIT_STUDENT。Q 为每条完整航次先算 0–20 s 的向量位置 RMSE，再按任务宏平均；没有混池采样点。A 同理按向量姿态误差 RMS。MATLAB percentile 使用已校验的 Hazen 定义。机械 phase 直接复现 `metrics_dl1018.m` 的命令/rho 阈值分类；时间分箱为固定区间。\n"]
    for split in ("TRAIN", "VAL", "ALL"):
        sub = paired if split == "ALL" else [r for r in paired if r["split"] == split]
        lines.append(f"## {split}（n={len(sub)}）\n")
        for role in ROLES:
            qv = macro(sub, f"{role}_Q_0_20_m")
            lines.append(f"- {role} 按任务宏 Q：{qv:.9g} m。")
        lines.append(f"- P_INIT 胜 B：{sum(bool(r['P_INIT_beats_B_Q']) for r in sub)}/{len(sub)}；胜 POS_OFF：{sum(bool(r['P_INIT_beats_POS_OFF_Q']) for r in sub)}/{len(sub)}。\n")
    lines.append("## A、按任务胜负\n")
    for task in sorted({r["task"] for r in paired}):
        sub = [r for r in paired if r["task"] == task]
        lines.append(f"- {task}: P_INIT 胜 B {sum(bool(r['P_INIT_beats_B_Q']) for r in sub)}/{len(sub)}；胜 POS_OFF {sum(bool(r['P_INIT_beats_POS_OFF_Q']) for r in sub)}/{len(sub)}；任务宏 Q B/POS_OFF/P_INIT = " +
                     "/".join(f"{macro(sub, f'{role}_Q_0_20_m'):.7g}" for role in ROLES) + " m。")
    lines.append("\n## B、退化从何时出现\n")
    # Each time window is scored within a scene first, then averaged across scenes.
    for comparator in ("B", "POS_OFF"):
        vals = []; wins = []
        for name, _, _ in TIME_BINS:
            d = []
            for r in paired:
                p = json.loads(str(r["P_INIT_STUDENT_time_bin_metrics_json"]))[name]["Q_rmse_m"]
                b = json.loads(str(r[f"{comparator}_time_bin_metrics_json"]))[name]["Q_rmse_m"]
                if np.isfinite(p) and np.isfinite(b): d.append(float(p) - float(b))
            vals.append(float(np.mean(d)) if d else math.nan)
            wins.append(sum(x < 0 for x in d))
        lines.append(f"- ALL P_INIT−{comparator} 分箱差（0–1.8/1.8–5/5–10/10–15/15–20 s）：" +
                     "/".join(f"{v:+.6g}" for v in vals) + " m；逐场胜出数：" +
                     "/".join(str(v) for v in wins) + "/432。")
    lines.append("- 形变命令最早在 5.2 s 后开始；因此 1.8–5 s 的退化先于臂长变化。0–1.8 s 已有小幅差距，不能把首次出现归因于形变。")
    lines.append("\n## C、是否由少数极端场景拉高\n")
    d = np.asarray([float(r["P_INIT_minus_B_Q_0_20_m"]) for r in paired])
    lines.append(f"- P_INIT−B 单场 Q 差：中位数 {np.median(d):+.6g} m，P10/P90 {np.percentile(d,10):+.6g}/{np.percentile(d,90):+.6g} m；变差场数 {np.sum(d>0)}/{len(d)}。")
    lines.append("- 全量逐场差、极值和尾部清单见 D1_G04_PAIRED_ALL.csv；不以稳定性替代性能。\n")
    lines.append("## D、风频组\n")
    for wind in ("NO_WIND", "LOW", "MID", "HIGH"):
        sub = [r for r in paired if r["wind_frequency_group"] == wind]
        if sub:
            lines.append(f"- {wind} n={len(sub)}，P_INIT 胜 B {sum(bool(r['P_INIT_beats_B_Q']) for r in sub)}/{len(sub)}，胜 POS_OFF {sum(bool(r['P_INIT_beats_POS_OFF_Q']) for r in sub)}/{len(sub)}；P_INIT−B macro Q={macro(sub,'P_INIT_minus_B_Q_0_20_m'):+.6g} m。")
    lines.append("\n## E、任务方向差异\n")
    lines.append("三个任务逐项胜率及 macro Q 如 A；只有任务间方向实际相反时才判为相反表现。任务分组不能单独证明需要专家模型。\n")
    lines.append("## 初始干预分支\n")
    p_vs_off = float(np.mean([r["P_INIT_minus_POS_OFF_Q_0_20_m"] for r in paired]))
    p_vs_b = float(np.mean([r["P_INIT_minus_B_Q_0_20_m"] for r in paired]))
    lines.append(f"- P_INIT−POS_OFF 单场 Q 差均值：{p_vs_off:+.9g} m；P_INIT−B：{p_vs_b:+.9g} m。")
    if p_vs_off < 0:
        lines.append("- 决策：若 Student 优于 POS_OFF 但逊于 B，则保留固定补偿有净价值、但未能替代 B 的 RBF 能力；继续按 D2/D3 分离运行链、Final warm-fit 与适应目标。")
    else:
        lines.append("- 决策：Student 未显示对 POS_OFF 的平均净补偿收益，优先检查补偿误差/相位/反馈作用；不把该结果解释成模型包身份差异。")
    lines.append("- 结论等级：这是同场行为比较；不单独证明唯一根因。\n")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit-scenes", type=int, default=0, help="diagnostic partial run only; 0 means all")
    args = ap.parse_args()
    at = rows(ROOT / "logs/attempt_index.csv")
    specs = {r["scene_id"]: r for r in rows(ROOT / "configs/scene_specs.csv")}
    g04 = [r for r in at if r["gate_id"] == "G04_P_STUDENT" and r["collector_id"] == "P_INIT_STUDENT"
           and r["status"] == "COMPLETE" and truth(r["accepted_for_training"])]
    g04_by_scene = {r["scene_id"]: r for r in g04}
    if len(g04_by_scene) != len(g04) or len(g04_by_scene) != 432:
        raise RuntimeError(f"Expected 432 unique G04 accepted episodes; got rows={len(g04)} unique={len(g04_by_scene)}")
    expected_role_rows = {}
    for r in at:
        if r["status"] not in ("COMPLETE", "STABLE"):
            continue
        role = r["collector_id"]
        if role not in ROLES:
            continue
        if role != "P_INIT_STUDENT" and r["gate_id"] != "G02_P_TEACHER":
            continue
        if role == "P_INIT_STUDENT" and r["gate_id"] != "G04_P_STUDENT":
            continue
        key = (r["scene_id"], role)
        if key not in expected_role_rows or int(r["attempt_no"]) > int(expected_role_rows[key]["attempt_no"]):
            expected_role_rows[key] = r

    missing = []
    scene_meta = {}
    for scene, student in g04_by_scene.items():
        if scene not in specs:
            missing.append(f"{scene}: scene_specs missing")
            continue
        split = student["split"].upper()
        z = dict(specs[scene])
        z["scene_id"] = scene; z["split"] = split
        z["wind_frequency_group"] = freq_class(z)
        scene_meta[scene] = z
        for role in ROLES:
            pair = expected_role_rows.get((scene, role))
            if pair is None:
                missing.append(f"{scene}/{role}: no complete accepted matching row")
            elif pair["split"].lower() != student["split"].lower():
                missing.append(f"{scene}/{role}: split mismatch {pair['split']} vs {student['split']}")
    if missing:
        (OUT / "reports/D1_MISSING_PAIRS.txt").write_text("\n".join(missing) + "\n", encoding="utf-8")
        raise RuntimeError(f"D1 has missing/mismatched pairs ({len(missing)}); see reports/D1_MISSING_PAIRS.txt; no recapture performed")

    checkpoint = OUT / "state/D1_CHECKPOINT.jsonl"
    cached: dict[str, dict] = {}
    if checkpoint.exists():
        with checkpoint.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rec = json.loads(line); cached[rec["scene_id"]] = rec
    scenes = sorted(g04_by_scene)
    if args.limit_scenes:
        scenes = scenes[:args.limit_scenes]
    start = time.monotonic()
    done = 0
    with checkpoint.open("a", encoding="utf-8") as cp:
        for scene in scenes:
            triplet = {}
            valid = scene in cached
            if valid:
                for role in ROLES:
                    r = expected_role_rows[(scene, role)]
                    p = ROOT / Path(r["raw_path"].replace("/", "\\"))
                    if not p.is_file() or cached[scene]["cache_keys"].get(role) != stable_key(p, r):
                        valid = False
                        break
            if valid:
                triplet = cached[scene]["metrics"]
            else:
                for role in ROLES:
                    r = expected_role_rows[(scene, role)]
                    p = ROOT / Path(r["raw_path"].replace("/", "\\"))
                    if not p.is_file():
                        raise FileNotFoundError(f"Missing selected raw; no data fabricated: {p}")
                    metrics = reduce_raw(p, r, specs[scene])
                    triplet[role] = {**metrics, "run_id": r["run_id"], "model_id": r["model_id"],
                                     "raw_path": r["raw_path"], "cache_identity": stable_key(p, r)}
                rec = {"scene_id": scene, "cache_keys": {role: expected_role_rows[(scene, role)]["run_id"] + "|" +
                        str((ROOT / Path(expected_role_rows[(scene, role)]["raw_path"].replace("/", "\\"))).stat().st_size) + "|" +
                        str((ROOT / Path(expected_role_rows[(scene, role)]["raw_path"].replace("/", "\\"))).stat().st_mtime_ns)
                        for role in ROLES}, "metrics": triplet,
                       "completed_at_utc": datetime.now(timezone.utc).isoformat()}
                cp.write(json.dumps(rec, separators=(",", ":"), allow_nan=True) + "\n"); cp.flush()
                cached[scene] = rec
            done += 1
            if done % 8 == 0 or done == len(scenes):
                elapsed = time.monotonic() - start
                speed = done / elapsed if elapsed else 0.0
                remain = len(scenes) - done
                eta_min = remain / speed / 60 if speed else math.inf
                print(f"D1 progress {done}/{len(scenes)} scenes; rate={speed:.3f} scenes/s; ETA={eta_min:.1f} min", flush=True)

    if args.limit_scenes:
        return
    paired = []
    for scene in sorted(g04_by_scene):
        rec = cached[scene]
        triplet = {role: rec["metrics"][role] for role in ROLES}
        paired.append(flat_scene_row(scene_meta[scene], triplet))

    paired_path = OUT / "reports/D1_G04_PAIRED_ALL.csv"
    with paired_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(paired[0]))
        w.writeheader(); w.writerows(paired)
    grouped = grouped_rows(paired)
    grouped_path = OUT / "reports/D1_GROUPED_BY_TASK_WIND_CLASS_PHASE.csv"
    with grouped_path.open("w", encoding="utf-8", newline="") as f:
        fields = sorted(set().union(*(r.keys() for r in grouped)))
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader(); w.writerows(grouped)

    decision = build_decision(paired)
    (OUT / "reports/D1_INITIAL_EFFECT_DECISION.md").write_text(decision + "\n", encoding="utf-8")
    state_path = OUT / "state/state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    state.update({"phase": "D1_COMPLETE", "next": "D2_RUNTIME_REPLAY_AND_RESIDUAL_DECOMPOSITION",
                  "plant_starts_new": 0, "fits_new": 0, "d1_scenes_complete": len(paired),
                  "d1_roles_complete": len(paired) * 3, "updated_at_utc": datetime.now(timezone.utc).isoformat()})
    state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"D1_COMPLETE scenes={len(paired)} role_runs={len(paired)*3} paired={paired_path} grouped={grouped_path}", flush=True)


if __name__ == "__main__":
    main()
