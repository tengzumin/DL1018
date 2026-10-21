from __future__ import annotations

import csv
import os
import shutil
import stat
import argparse
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "experiments" / "kan14_task_specialist_compare_v1"
CLEANUP = OUT / "cleanup"
KEEP_CSV = CLEANUP / "KEEP_MAT_MANIFEST.csv"
PLAN_CSV = CLEANUP / "DELETE_MAT_PLAN.csv"
DELETED_CSV = CLEANUP / "DELETED_MAT.csv"
SKIPPED_CSV = CLEANUP / "SKIPPED_MAT.csv"
REPORT_MD = CLEANUP / "CLEANUP_REPORT_ZH.md"


def csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, fields: tuple[str, ...], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def is_reparse(st: os.stat_result) -> bool:
    attrs = getattr(st, "st_file_attributes", 0)
    return stat.S_ISLNK(st.st_mode) or bool(attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def inventory_mat_files() -> tuple[list[Path], list[dict]]:
    found: list[Path] = []
    skipped_links: list[dict] = []
    stack = [ROOT]
    while stack:
        folder = stack.pop()
        try:
            entries = list(os.scandir(folder))
        except OSError as exc:
            skipped_links.append({"path": rel(folder), "bytes": "", "reason": f"无法扫描目录：{exc}", "evidence": ""})
            continue
        for entry in entries:
            path = Path(entry.path)
            try:
                st = entry.stat(follow_symlinks=False)
            except OSError as exc:
                if path.suffix.lower() == ".mat":
                    skipped_links.append({"path": rel(path), "bytes": "", "reason": f"无法读取文件属性：{exc}", "evidence": ""})
                continue
            if is_reparse(st):
                if path.suffix.lower() == ".mat" or entry.is_dir(follow_symlinks=False):
                    skipped_links.append({"path": rel(path), "bytes": st.st_size if path.is_file() else "",
                                          "reason": "符号链接／重解析点；未跟随也未删除", "evidence": ""})
                continue
            if entry.is_dir(follow_symlinks=False):
                if path == OUT:
                    continue
                stack.append(path)
            elif entry.is_file(follow_symlinks=False) and path.suffix.lower() == ".mat":
                found.append(path)
    return sorted(found), skipped_links


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan-only", action="store_true", help="write and inspect manifests without unlinking MAT files")
    args = parser.parse_args()
    before = shutil.disk_usage(ROOT)
    attempts = csv_rows(ROOT / "logs" / "attempt_index.csv")
    teacher = csv_rows(ROOT / "experiments" / "teacher_reuse_model_screen_v1" / "manifests" / "teacher_reuse_manifest.csv")
    students = csv_rows(ROOT / "experiments" / "gru14_dssm14_student_refine_v1" / "manifests" / "student_episode_manifest.csv")
    accepted: dict[str, str] = {}
    failed_unaccepted: dict[str, str] = {}
    for row in attempts:
        raw = row.get("raw_path", "").replace("\\", "/")
        if raw:
            if row.get("accepted_for_training", "").strip().lower() == "true":
                accepted[raw] = f"accepted {row.get('collector_id')} {row.get('split')} source; logs/attempt_index.csv"
                accepted[(PurePosixPath(raw).parent / "run_start.mat").as_posix()] = (
                    f"run_start for accepted {row.get('collector_id')} {row.get('split')} source; logs/attempt_index.csv")
            elif row.get("status", "").upper() == "ENGINEERING_ERROR":
                failed_unaccepted[raw] = "明确记录为未验收 ENGINEERING_ERROR；不进入训练／验证集"
                failed_unaccepted[(PurePosixPath(raw).parent / "run_start.mat").as_posix()] = (
                    "明确记录为未验收 ENGINEERING_ERROR 的 run_start；不进入训练／验证集")
    student_refs: dict[str, str] = {}
    for row in students:
        if row.get("eligible_for_training", "").strip() != "1":
            continue
        for field in ("raw_path", "run_start_path", "sequence_cache_path"):
            value = row.get(field, "").replace("\\", "/")
            if value:
                student_refs[value] = f"locked GRU14/DSSM14 Student TRAIN/VAL; student_episode_manifest.csv"
    teacher_missing = [r.get("raw_path", "").replace("\\", "/") for r in teacher
                       if r.get("raw_path", "").replace("\\", "/") not in accepted]
    student_missing = [p for p in student_refs if not (ROOT / Path(p)).is_file()]
    if teacher_missing:
        raise RuntimeError(f"Accepted teacher manifest contains {len(teacher_missing)} raw path(s) absent from accepted attempt index")
    if student_missing:
        raise RuntimeError(f"Locked Student manifest contains {len(student_missing)} missing MAT dependency/dependencies")

    mats, link_skips = inventory_mat_files()
    keep: list[dict] = []
    plan: list[dict] = []
    skip: list[dict] = list(link_skips)

    protected_dev_groups = (
        "experiments/teacher_reuse_model_screen_v1/runs/LOCKED_DEV_FIRST_GRU14_ONLINE/",
        "experiments/teacher_reuse_model_screen_v1/runs/POSTHOC_LOCKED_DEV_DSSM14_ONLINE/",
        "experiments/gru14_dssm14_student_refine_v1/dev24/",
    )
    for path in mats:
        relpath = rel(path)
        size = path.stat().st_size
        parts = relpath.split("/")
        reason = ""
        evidence = ""
        if relpath in student_refs:
            reason, evidence = student_refs[relpath], "experiments/gru14_dssm14_student_refine_v1/manifests/student_episode_manifest.csv"
        elif relpath in accepted:
            reason, evidence = accepted[relpath], "logs/attempt_index.csv; logs/episode_index.csv"
        elif relpath.startswith("data/raw/dev/"):
            reason, evidence = "保留全部 DEV 原始记录；含 24 场同场 B 基线及可复算评估证据", "reports/POSITION_DEV.csv; DEV24 配对报告"
        elif parts[0] in {"configs", "matlab", "models"}:
            reason, evidence = "正式配置、模型包或 MATLAB 确定性夹具；保留运行／部署依赖", "项目配置和模型目录"
        elif "models" in parts or path.name == "matlab_model_and_parity.mat":
            reason, evidence = "模型导出包；保留模型定义、归一化与 parity 输入", "对应 fit_report.json／模型选择锁"
        elif any(relpath.startswith(prefix) for prefix in protected_dev_groups):
            reason, evidence = "保留指定 GRU14/DSSM14 原包与四个 Student 锁定候选的 DEV24 原始证据", "DEV24 配对结果 CSV 与 locked_candidates.csv"
        elif relpath.startswith("data/raw/"):
            if relpath in failed_unaccepted:
                plan.append({"path": relpath, "bytes": size, "experiment": "G02_P_TEACHER",
                             "delete_reason": failed_unaccepted[relpath],
                             "evidence": "logs/attempt_index.csv; reports/G02_P_TEACHER.json"})
                continue
            reason, evidence = "原始数据依赖状态不完全明确；按保守策略暂留", "logs/attempt_index.csv; 原始数据目录"
        else:
            lower = relpath.lower()
            metrics = path.parent / "metrics.json"
            if any(relpath.startswith(prefix) for prefix in protected_dev_groups):
                reason, evidence = "保留指定 DEV24 原始证据", "配对结果 CSV"
            elif "experiments/" in relpath and metrics.is_file():
                try:
                    resolved_root = ROOT.resolve(strict=True)
                    resolved_path = path.resolve(strict=True)
                    if not resolved_path.is_relative_to(resolved_root):
                        raise RuntimeError("resolved path escaped project root")
                    cur = path.parent
                    while cur != ROOT:
                        if is_reparse(cur.lstat()):
                            raise RuntimeError("path traverses a reparse point")
                        cur = cur.parent
                    result = __import__("json").loads(metrics.read_text(encoding="utf-8"))
                    status = str(result.get("metrics_row", {}).get("status", result.get("status", "")))
                    if not status or status.upper() not in {"STABLE", "COMPLETE", "PASS"}:
                        raise RuntimeError(f"no stable completed result in metrics.json (status={status!r})")
                    plan.append({"path": relpath, "bytes": size,
                                 "experiment": "/".join(parts[:2]) if len(parts) > 1 else parts[0],
                                 "delete_reason": "已完成历史闭环航次；同场指标已落盘，不属当前训练或指定 DEV24 保留项",
                                 "evidence": rel(metrics)})
                    continue
                except Exception as exc:
                    skip.append({"path": relpath, "bytes": size,
                                 "reason": f"有指标文件但无法证明是稳定完成记录，暂留：{exc}", "evidence": rel(metrics)})
                    continue
            else:
                skip.append({"path": relpath, "bytes": size,
                             "reason": "来源／依赖不明确，暂留；不按目录名猜测删除", "evidence": ""})
                continue
        keep.append({"path": relpath, "bytes": size, "reason": reason, "evidence": evidence})

    # Before any unlink: validate every delete target, project containment, and disjointness.
    keep_paths = {row["path"] for row in keep}
    plan_paths = [row["path"] for row in plan]
    if len(plan_paths) != len(set(plan_paths)) or keep_paths.intersection(plan_paths):
        raise RuntimeError("MAT deletion plan has duplicate entries or intersects KEEP manifest")
    root_resolved = ROOT.resolve(strict=True)
    for item in plan:
        target = ROOT / Path(item["path"])
        if not target.is_file() or not target.resolve(strict=True).is_relative_to(root_resolved):
            raise RuntimeError(f"Unsafe or missing deletion target: {item['path']}")
        if is_reparse(target.lstat()):
            raise RuntimeError(f"Deletion target is a reparse point: {item['path']}")
        cur = target.parent
        while cur != ROOT:
            if is_reparse(cur.lstat()):
                raise RuntimeError(f"Deletion path traverses a reparse point: {item['path']}")
            cur = cur.parent

    fields_keep = ("path", "bytes", "reason", "evidence")
    fields_plan = ("path", "bytes", "experiment", "delete_reason", "evidence")
    fields_skip = ("path", "bytes", "reason", "evidence")
    write_csv(KEEP_CSV, fields_keep, keep)
    write_csv(PLAN_CSV, fields_plan, plan)

    deleted: list[dict] = []
    if not args.plan_only:
        for item in plan:
            target = ROOT / Path(item["path"])
            try:
                target.unlink()
                deleted.append({**item, "deleted_at_utc": datetime.now(timezone.utc).isoformat(), "result": "DELETED"})
            except OSError as exc:
                skip.append({"path": item["path"], "bytes": item["bytes"], "reason": f"逐文件删除失败／占用，已跳过：{exc}", "evidence": item["evidence"]})
    after = shutil.disk_usage(ROOT)
    write_csv(DELETED_CSV, (*fields_plan, "deleted_at_utc", "result"), deleted)
    write_csv(SKIPPED_CSV, fields_skip, skip)

    planned_bytes = sum(int(x["bytes"]) for x in plan)
    deleted_bytes = sum(int(x["bytes"]) for x in deleted)
    keep_bytes = sum(int(x["bytes"]) for x in keep)
    report = [
        "# 历史 MAT 清理报告", "",
        f"清理时间：{datetime.now(timezone.utc).isoformat()}",
        f"扫描到 MAT：{len(mats)} 个；逐文件保留：{len(keep)} 个；删除计划：{len(plan)} 个；实际删除：{len(deleted)} 个；跳过：{len(skip)} 个。",
        f"保留 MAT 逻辑大小：{keep_bytes / 1024**3:.3f} GiB。",
        f"删除计划逻辑大小：{planned_bytes / 1024**3:.3f} GiB；实际删除逻辑大小：{deleted_bytes / 1024**3:.3f} GiB。",
        f"C: 清理前可用空间：{before.free / 1024**3:.3f} GiB；清理后：{after.free / 1024**3:.3f} GiB；卷可用空间实增：{(after.free-before.free) / 1024**3:.3f} GiB。",
        "逻辑文件大小与卷可用空间实增分别统计；两者可能因压缩、硬链接、卷记账和并行系统活动不同。",
        "", "## 保留范围", "",
        "教师 TRAIN/VAL 原始 MAT、已有 Student TRAIN/VAL 清单中的原始/起始/缓存 MAT、全部 DEV 原始记录、正式模型导出、有效配置和 MATLAB fixtures 均保留。",
        "指定 GRU14/DSSM14 原包 DEV24 与四个锁定 Student 候选 DEV24 原始记录均保留。",
        "历史闭环 MAT 仅在同场 `metrics.json` 明确记录 STABLE/COMPLETE/PASS，且路径逐项通过项目边界、重解析点与 KEEP/DELETE 不相交检查后删除；报告、CSV、代码和非 MAT 文件均未删除。",
        "", "## 尚未删除", "",
        f"跳过 {len(skip)} 项。每项原因见 `SKIPPED_MAT.csv`；包括来源不明、结果非稳定、无逐场完整指标、文件占用或重解析点。",
        "", "## 保留文件索引", "", "逐文件保留依据见 `KEEP_MAT_MANIFEST.csv`。",
        "", "## 删除文件索引", "", "逐文件计划与成功记录见 `DELETE_MAT_PLAN.csv` 和 `DELETED_MAT.csv`。", ""
    ]
    REPORT_MD.write_text("\n".join(report), encoding="utf-8")
    status = "CLEANUP_PLAN_READY" if args.plan_only else "CLEANUP_COMPLETE"
    print(f"{status} scanned={len(mats)} keep={len(keep)} planned={len(plan)} deleted={len(deleted)} skipped={len(skip)} logical_deleted_GiB={deleted_bytes/1024**3:.3f} volume_gain_GiB={(after.free-before.free)/1024**3:.3f}", flush=True)


if __name__ == "__main__":
    main()
