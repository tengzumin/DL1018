from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "experiments" / "gru14_dssm14_student_refine_v1"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    temp.replace(path)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def bridge_rows() -> pd.DataFrame:
    path = OUT / "bridge6" / "all_runs.csv"
    if not path.is_file():
        return pd.DataFrame()
    return pd.read_csv(path)


def lock_candidates() -> None:
    lock_path = OUT / "state/LOCKED_CANDIDATES.json"
    if lock_path.is_file():
        previous = json.loads(lock_path.read_text(encoding="utf-8"))
        if previous.get("status") == "LOCKED_BEFORE_DEV":
            print(f"STUDENT_BRIDGE_SELECTION_ALREADY_FROZEN locked={previous.get('locked_count')}/4; preserving existing lock")
            return
    manifest = pd.read_csv(OUT / "manifests/canonical_packages.csv")
    runs = bridge_rows()
    if runs.empty:
        raise RuntimeError("BRIDGE6 has no persisted run rows")
    by_package = {}
    for row in manifest.to_dict("records"):
        candidate = runs.loc[runs.package_id == row["package_id"]].copy()
        candidate = candidate.drop_duplicates("scene_id")
        stable = bool(len(candidate) == 6 and candidate.scene_id.nunique() == 6 and \
            candidate.complete.astype(bool).all() and candidate.finite.astype(bool).all() and \
            (candidate.status.astype(str) == "STABLE").all())
        losses = int((candidate.Q_0_20_m > candidate.B_Q_0_20_m).sum()) if len(candidate) else 6
        relative = (candidate.Q_0_20_m - candidate.B_Q_0_20_m) / candidate.B_Q_0_20_m
        worst_positive = float(relative.clip(lower=0).max()) if len(candidate) else float("inf")
        macro_q = float(candidate.Q_0_20_m.mean()) if len(candidate) else float("inf")
        macro_b = float(candidate.B_Q_0_20_m.mean()) if len(candidate) else float("inf")
        by_package[row["package_id"]] = {
            **row, "stable_six": stable, "bridge_rows": int(len(candidate)),
            "losses_vs_B": losses, "worst_positive_relative_degradation": worst_positive,
            "bridge_macro_Q_m": macro_q, "bridge_macro_B_m": macro_b,
            "bridge_delta_Q_m": macro_q - macro_b,
        }
    all_scores = list(by_package.values())
    groups = sorted({(str(r["model_id"]), str(r["group"])) for r in all_scores})
    locked = []
    for model, group in groups:
        choices = [r for r in all_scores if r["model_id"] == model and r["group"] == group and r["stable_six"]]
        if not choices:
            continue
        choices.sort(key=lambda r: (r["losses_vs_B"], r["worst_positive_relative_degradation"],
                                    r["bridge_macro_Q_m"], float(r["common_val_rmse_mps2"]),
                                    int(r["seed"]), str(r["checkpoint_kind"]), str(r["package_id"])))
        chosen = dict(choices[0])
        chosen["selection_rank"] = 1
        chosen["locked_at_utc"] = utcnow()
        locked.append(chosen)
    score_rows = pd.DataFrame(all_scores).sort_values(["model_id", "group", "losses_vs_B",
        "worst_positive_relative_degradation", "bridge_macro_Q_m", "common_val_rmse_mps2", "seed", "package_id"])
    score_rows.to_csv(OUT / "reports/bridge6_package_scores.csv", index=False)
    selection = {"status": "LOCKED_BEFORE_DEV" if len(locked) == 4 else "LOCK_INCOMPLETE_NO_DEV",
                 "locked_count": len(locked), "required_count": 4, "selection_metric": "BRIDGE6 position Q only",
                 "tie_break_order": ["fewest losses vs same-scene B", "lowest worst positive relative degradation",
                                     "lowest six-scene macro Q", "lowest common validation", "ascending seed", "checkpoint name"],
                 "locked_at_utc": utcnow(), "candidates": locked,
                 "bridge_scores_sha256": sha256(OUT / "reports/bridge6_package_scores.csv"),
                 "dev_started_before_lock": False}
    if len(locked) == 4 and any((OUT / "dev24").rglob("plant_started.marker")):
        raise RuntimeError("DEV Plant exists before candidate lock; refusing to replace lock")
    write_json(lock_path, selection)
    if locked:
        pd.DataFrame(locked).to_csv(OUT / "manifests/locked_candidates.csv", index=False)
    if len(locked) == 4:
        append_ledger("LOCK_CANDIDATES", "LOCKED", "four model-by-training-group packages selected before DEV")
    print(f"STUDENT_BRIDGE_SELECTION {selection['status']} locked={len(locked)}/4")
    for r in locked:
        print(f"  {r['model_id']} {r['group']} {r['package_id']} losses={r['losses_vs_B']}/6 worst_pos_rel={r['worst_positive_relative_degradation']:.6g} Q={r['bridge_macro_Q_m']:.8g} B={r['bridge_macro_B_m']:.8g}")


def append_ledger(identity: str, status: str, note: str) -> None:
    path = OUT / "RESOURCE_LEDGER.csv"
    if identity in path.read_text(encoding="utf-8"):
        return
    with path.open("a", encoding="utf-8", newline="") as f:
        f.write(f"{utcnow()},CandidateLock,{identity},0,{status},{note.replace(',', ';')}\n")


def paired_student() -> pd.DataFrame:
    import sys
    import numpy as np
    sys.path.insert(0, str(OUT / "scripts"))
    from live_pair_metrics import raw_metrics

    manifest_path = OUT / "manifests/student_episode_manifest.csv"
    manifest = pd.read_csv(manifest_path, keep_default_na=False)
    teachers = pd.read_csv(OUT / "manifests/teacher_reuse_manifest.csv", keep_default_na=False)
    teachers = teachers.loc[teachers.role == "B"].drop_duplicates("scene_id").set_index("scene_id")
    scene_task = pd.read_csv(ROOT / "configs/scene_specs.csv").set_index("scene_id").task.astype(str).to_dict()
    old_path = ROOT / "experiments/position_causal_repair_v1/reports/D1_G04_PAIRED_ALL.csv"
    old = pd.read_csv(old_path) if old_path.is_file() else pd.DataFrame()
    rows = []
    for r in manifest.itertuples(index=False):
        if str(r.status) != "STABLE" or not bool(r.eligible_for_training):
            continue
        student_path = ROOT / Path(str(r.raw_path).replace("/", "\\"))
        student = raw_metrics(student_path)
        bmeta = teachers.loc[str(r.scene_id)]
        b = raw_metrics(ROOT / Path(str(bmeta.raw_path).replace("/", "\\")))
        if not old.empty and str(r.scene_id) in set(old.scene_id.astype(str)):
            oldb = float(old.loc[old.scene_id.astype(str) == str(r.scene_id), "B_Q_0_20_m"].iloc[0])
            if abs(oldb - b["position_Q_0_20_m"]) > 1e-8:
                raise RuntimeError(f"Same-scene B mismatch for {r.scene_id}")
        if abs(float(r.position_Q_0_20_m) - student["position_Q_0_20_m"]) > 1e-10:
            raise RuntimeError(f"Student raw/Q mismatch for {r.scene_id}")
        rows.append({"model_id": r.model_id, "split": r.split, "scene_id": r.scene_id,
                     "task": scene_task[str(r.scene_id)], "status": r.status,
                     "position_Q_0_20_m": student["position_Q_0_20_m"],
                     "same_scene_B_Q_0_20_m": b["position_Q_0_20_m"],
                     "delta_Q_vs_B_m": student["position_Q_0_20_m"] - b["position_Q_0_20_m"],
                     "position_axis_rmse_m": json.dumps(student["position_axis_rmse_m"]),
                     "attitude_Q_0_20_rad": student["attitude_Q_0_20_rad"],
                     "attitude_axis_rmse_rad": json.dumps(student["attitude_axis_rmse_rad"]),
                     "transitions": student["transition_count"], "raw_path": r.raw_path,
                     "same_scene_B_raw_path": bmeta.raw_path})
    result = pd.DataFrame(rows)
    result.to_csv(OUT / "reports/STUDENT_PAIRED_240.csv", index=False)
    return result


def phase_summary(path: Path, name: str) -> dict:
    if not path.is_file():
        return {"phase": name, "status": "NOT_RUN", "rows": 0}
    d = pd.read_csv(path)
    if d.empty:
        return {"phase": name, "status": "EMPTY", "rows": 0}
    stable = d.loc[(d.status.astype(str) == "STABLE") & d.complete.astype(bool) & d.finite.astype(bool)]
    return {"phase": name, "rows": int(len(d)), "stable_rows": int(len(stable)),
            "same_scene_pairs": int(d.scene_id.nunique()), "macro_Q_m": float(stable.Q_0_20_m.mean()) if len(stable) else None,
            "macro_B_m": float(stable.B_Q_0_20_m.mean()) if len(stable) else None,
            "wins_vs_B": int((stable.Q_0_20_m < stable.B_Q_0_20_m).sum()),
            "losses_vs_B": int((stable.Q_0_20_m > stable.B_Q_0_20_m).sum()),
            "attitude_macro_rmse_rad": float(stable.attitude_Q_0_20_rad.mean()) if len(stable) else None}


def write_resume_docs(state: dict) -> None:
    resume = f"""# 续跑说明\n\n任务：`DL1018_GRU14_DSSM14_STUDENT_REFINE_V1`。当前阶段：`{state.get('phase','UNKNOWN')}`；状态：`{state.get('status','UNKNOWN')}`。\n\n## 恢复原则\n\n- 只在确认没有同阶段 Python/MATLAB 进程后恢复，避免重复 Plant。\n- 每个轨迹目录中的 `plant_started.marker`、`raw_run.mat`、`metrics.json`、`manifest_row.json` 是该轨迹的恢复依据。marker 存在但 raw 不存在时先调查，不能盲目重跑。\n- Student 采集复用原始 B/控制器与特征头；采集完成前不启动训练。训练中断从每 1000 步保存的 `latest_checkpoint.pt` 恢复。\n- DEV 前必须有 `state/LOCKED_CANDIDATES.json`，此后不改变候选。TEST 不读取。\n\n查看状态：`python experiments/gru14_dssm14_student_refine_v1/scripts/refine.py resume`。\n"""
    (OUT / "RESUME.md").write_text(resume, encoding="utf-8")
    commands = """# 运行命令\n\n在 DL1018 项目根目录执行。每一步会复用已完成的轨迹/检查点；启动前先确认同阶段没有活动进程。\n\n```powershell\npython experiments/gru14_dssm14_student_refine_v1/scripts/refine.py collect\npython experiments/gru14_dssm14_student_refine_v1/scripts/refine.py train\npython experiments/gru14_dssm14_student_refine_v1/scripts/refine.py export\npython experiments/gru14_dssm14_student_refine_v1/scripts/refine.py canary\npython experiments/gru14_dssm14_student_refine_v1/scripts/refine.py dev\npython experiments/gru14_dssm14_student_refine_v1/scripts/refine.py report\n```\n\n`canary` 完成 BRIDGE6 后按冻结门槛锁定四个包；`dev` 会先要求锁定文件存在，再跑满四组各 24 场。禁止在此任务中访问 TEST。\n"""
    (OUT / "RUN_COMMANDS.md").write_text(commands, encoding="utf-8")


def report() -> None:
    protocol = json.loads((OUT / "protocol.json").read_text(encoding="utf-8"))
    manifest_path = OUT / "manifests/student_episode_manifest.csv"
    if not manifest_path.is_file():
        raise RuntimeError("Student episode manifest is missing")
    current = pd.read_csv(manifest_path, keep_default_na=False)
    stable_count = int(((current.status == "STABLE") & current.eligible_for_training.map(
        lambda x: str(x).lower() in {"true", "1"})).sum())
    if stable_count != 240:
        raise RuntimeError(f"Refusing final report before all 240 Student trajectories are stable; found {stable_count}")
    student = paired_student()
    bridge = phase_summary(OUT / "bridge6/all_runs.csv", "BRIDGE6")
    dev = phase_summary(OUT / "dev24/all_runs.csv", "DEV24")
    if (OUT / "bridge6/all_runs.csv").is_file():
        pd.read_csv(OUT / "bridge6/all_runs.csv").to_csv(OUT / "reports/BRIDGE6_ALL_PACKAGES.csv", index=False)
    if (OUT / "dev24/all_runs.csv").is_file():
        pd.read_csv(OUT / "dev24/all_runs.csv").to_csv(OUT / "reports/DEV_PAIRED_24.csv", index=False)
    fit_reports = []
    for p in sorted((OUT / "models").glob("*/**/fit_report.json")):
        fit_reports.append(json.loads(p.read_text(encoding="utf-8")))
    state = json.loads((OUT / "state/state.json").read_text(encoding="utf-8")) if (OUT / "state/state.json").is_file() else {}
    extension_path = OUT / "reports/training_extension_plan.json"
    extension_plan = json.loads(extension_path.read_text(encoding="utf-8")) if extension_path.is_file() else None
    lock_path = OUT / "state/LOCKED_CANDIDATES.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8")) if lock_path.is_file() else None
    dev_candidates = []
    if dev.get("rows") and lock:
        all_dev = pd.read_csv(OUT / "dev24/all_runs.csv")
        for candidate in lock.get("candidates", []):
            g = all_dev.loc[all_dev.package_id.astype(str) == str(candidate["package_id"])]
            stable = g.loc[(g.status.astype(str) == "STABLE") & g.complete.astype(bool) & g.finite.astype(bool)]
            q = float(stable.Q_0_20_m.mean()) if len(stable) else None
            b = float(stable.B_Q_0_20_m.mean()) if len(stable) else None
            dev_candidates.append({"model_id": candidate["model_id"], "group": candidate["group"],
                "package_id": candidate["package_id"], "stable_pairs": int(len(stable)), "required_pairs": 24,
                "macro_Q_m": q, "same_scene_B_macro_Q_m": b,
                "delta_Q_vs_B_m": q - b if q is not None and b is not None else None,
                "wins_vs_B": int((stable.Q_0_20_m < stable.B_Q_0_20_m).sum()),
                "attitude_macro_rmse_rad": float(stable.attitude_Q_0_20_rad.mean()) if len(stable) else None,
                "macro_beats_B": bool(q < b) if q is not None and b is not None and len(stable) == 24 else None})
    marker_count = sum(1 for _ in OUT.rglob("plant_started.marker"))
    package_manifest = OUT / "manifests/canonical_packages.csv"
    expected_bridge_rows = 6 * len(pd.read_csv(package_manifest)) if package_manifest.is_file() else 0
    model_counts = student.groupby("model_id").size().to_dict() if len(student) else {}
    complete = len(student) == 240 and model_counts == {"DSSM14": 120, "GRU14": 120} and \
        len(fit_reports) == 8 and all(r.get("status") == "COMPLETE" for r in fit_reports) and \
        bridge.get("rows", 0) == expected_bridge_rows and \
        dev.get("rows") == 96 and lock is not None and lock.get("status") == "LOCKED_BEFORE_DEV"
    result = {"task_id": protocol["task_id"], "status": "COMPLETE" if complete else "PARTIAL",
              "student_stable_episodes": int(len(student)), "student_required_episodes": 240,
              "student_by_model": student.groupby("model_id").size().to_dict() if len(student) else {},
              "training_fits": len(fit_reports), "training_required_fits": 8,
              "optimizer_steps_completed_total": int(state.get("optimizer_steps_completed_total", 0)),
              "training_extension_plan": extension_plan,
              "bridge6": bridge, "dev24": dev, "plant_starts_total": marker_count,
              "plant_budget_max": 432, "test_accessed": False,
              "locked_candidates": lock, "dev_candidate_results": dev_candidates,
              "generated_at_utc": utcnow()}
    write_json(OUT / "reports/FINAL_RESULT.json", result)
    lines = ["# GRU14 / DSSM14 Student 采集与续训对照", "", f"任务状态：**{result['status']}**。",
             f"Student 配对轨迹：{len(student)}/240；训练 fit：{len(fit_reports)}/8；总 Plant 启动：{result['plant_starts_total']}/432（含已记录工程重试）。",
             "只比较位置 Q；B 为同场 DL1018 B 原始轨迹。姿态 RMSE 作为记录量，不参与选择。原始 B、原 Final 编码器、G06/合同文件均未覆盖。TEST 未访问。", "",
             "## 四组 DEV24 配对结果", "", "| 模型与训练组 | 稳定配对场数 | Student 宏Q (m) | 同场B宏Q (m) | 胜B场数 | 姿态宏RMSE (rad) |", "|---|---:|---:|---:|---:|---:|"]
    if dev.get("rows"):
        d = pd.read_csv(OUT / "dev24/all_runs.csv")
        locked_ids = {str(r["package_id"]) for r in (lock or {}).get("candidates", [])}
        d = d.loc[d.package_id.astype(str).isin(locked_ids)]
        for (model, group), g in d.groupby(["model_id", "group"]):
            s = g.loc[(g.status == "STABLE") & g.complete.astype(bool) & g.finite.astype(bool)]
            macro_q = s.Q_0_20_m.mean() if len(s) else float("nan")
            macro_b = s.B_Q_0_20_m.mean() if len(s) else float("nan")
            macro_a = s.attitude_Q_0_20_rad.mean() if len(s) else float("nan")
            lines.append(f"| {model} / {group} | {len(s)}/24 | {macro_q:.8g} | {macro_b:.8g} | {(s.Q_0_20_m < s.B_Q_0_20_m).sum()} | {macro_a:.8g} |")
    else:
        lines.append("| 尚未完成 | — | — | — | — | — |")
    if dev_candidates:
        lines += ["", "按 24 场宏位置 Q 与同场 B 比较："]
        for r in dev_candidates:
            delta = "尚未完整" if r["delta_Q_vs_B_m"] is None else f"差值 {r['delta_Q_vs_B_m']:.8g} m，宏Q低于B：{r['macro_beats_B']}"
            lines.append(f"- {r['model_id']} / {r['group']}：稳定配对 {r['stable_pairs']}/24，{delta}。")
    if extension_plan and extension_plan.get("extensions"):
        lines += ["", "## 训练步数扩展", "", f"共完成 {result['optimizer_steps_completed_total']:,} 个优化步。按用户要求，将终点最优的 fit 按 10,000 步扩展，直到最佳点不再位于区间终点："]
        for extension in extension_plan["extensions"]:
            lines.append(f"- {extension['fit_id']}：{extension['from_steps']:,}→{extension['to_steps']:,} 步，最佳点 {extension['new_best_step']:,} 步；共同验证 RMSE {extension['new_best_common_val_rmse_mps2']:.8g}。")
    lines += ["", "## Student 逐条同场配对", "", "逐条数据见 `reports/STUDENT_PAIRED_240.csv`；包含模型、split、scene、位置Q、同场B、差值、位置轴RMSE、姿态Q/轴RMSE和原始路径。", "",
              "## BRIDGE6 候选筛选", "", "候选逐场评分见 `reports/bridge6_package_scores.csv` 和 `reports/BRIDGE6_ALL_PACKAGES.csv`，锁定记录及锁定时序见 `state/LOCKED_CANDIDATES.json`。", "",
              "DEV 全部逐场配对见 `reports/DEV_PAIRED_24.csv`（四组共96行）。", "",
              "## 训练与复现", "", "训练曲线见各 fit 目录的 `training_history.csv`；加载审计为 `reports/student_loader_check.json`。断点续跑步骤见 `RESUME.md` 和 `RUN_COMMANDS.md`。"]
    (OUT / "reports/FINAL_REPORT_ZH.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if complete:
        state.update({"phase": "COMPLETE", "status": "COMPLETE", "active_fit": "", "active_model": "",
                      "active_group": "", "active_scene": "", "active_package": "",
                      "cumulative_plant_starts": marker_count, "updated_at_utc": utcnow()})
        write_json(OUT / "state/state.json", state)
    write_resume_docs(state)
    print(f"STUDENT_FINAL_REPORT status={result['status']} student={len(student)}/240 fits={len(fit_reports)}/8 bridge={bridge.get('rows',0)} dev={dev.get('rows',0)}")


def status() -> None:
    path = OUT / "manifests/student_episode_manifest.csv"
    if path.is_file():
        d = pd.read_csv(path, keep_default_na=False)
        stable = d.loc[(d.status == "STABLE") & d.eligible_for_training.map(lambda x: str(x).lower() in {"true", "1"})]
        print(f"STUDENT_COLLECTION stable={len(stable)}/240 by_model={stable.groupby('model_id').size().to_dict()}")
    state_path = OUT / "state/state.json"
    if state_path.is_file():
        s = json.loads(state_path.read_text(encoding="utf-8"))
        print(f"STATE phase={s.get('phase')} status={s.get('status')} active={s.get('active_scene','')} plants={s.get('plant_starts',0)}")
    for pattern in ("*/TEACHER_CONTINUE/seed*/fit_report.json", "*/STUDENT_MIX20/seed*/fit_report.json"):
        reports = list((OUT / "models").glob(pattern))
        print(f"FIT_REPORTS {pattern}={len(reports)}")
    print("Resume stages are sequential: collect -> train -> export -> canary/lock -> dev -> report.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("lock", "report", "status"))
    args = parser.parse_args()
    if args.command == "lock":
        lock_candidates()
    elif args.command == "report":
        report()
    else:
        status()


if __name__ == "__main__":
    main()
