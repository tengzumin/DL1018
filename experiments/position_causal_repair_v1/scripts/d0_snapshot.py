from __future__ import annotations

import csv
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "experiments" / "position_causal_repair_v1"


def run(args: list[str], cwd: Path) -> str:
    p = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)
    return (p.stdout or p.stderr).strip()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name in ("scripts", "local_runtime", "manifests", "derived_events", "models",
                 "runs", "reports", "figures", "state"):
        (OUT / name).mkdir(parents=True, exist_ok=True)

    git = {
        "head": run(["git", "rev-parse", "HEAD"], ROOT),
        "branch": run(["git", "branch", "--show-current"], ROOT),
        "remote_v": run(["git", "remote", "-v"], ROOT),
        "porcelain_status": run(["git", "status", "--porcelain=v1", "-uno"], ROOT),
        "tracked_worktree_clean": not bool(run(["git", "status", "--porcelain=v1", "-uno"], ROOT)),
    }
    protected = [
        "configs/contract_dl1018.json", "configs/scene_specs.csv", "configs/selected_models.json",
        "logs/gate_status.json", "logs/attempt_index.csv", "logs/episode_index.csv",
        "reports/G00_MIGRATION.json", "reports/G01_SCENES.json", "reports/G02_P_TEACHER.json",
        "reports/G03_P_INITIAL.json", "reports/G04_P_STUDENT.json", "reports/G05_P_FINAL.json",
        "reports/G06_P_DEV.json", "training/data.py", "training/models.py", "training/common.py",
        "training/train_position.py", "training/export_matlab.py",
        "matlab/runtime/collect_position_role_dl1018.m", "matlab/runtime/collect_position_dev_dl1018.m",
        "matlab/runtime/controller_options_dl1018.m", "matlab/data/export_position_events_dl1018.m",
        "matlab/metrics/metrics_dl1018.m",
    ]
    files = []
    for rel in protected:
        p = ROOT / rel
        if p.is_file():
            st = p.stat()
            files.append({"path": rel.replace("\\", "/"), "size_bytes": st.st_size,
                          "mtime_utc": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(),
                          "sha256": sha256(p)})
        else:
            files.append({"path": rel.replace("\\", "/"), "missing": True})

    py = {
        "executable": sys.executable,
        "version": sys.version,
        "platform": platform.platform(),
    }
    try:
        import torch
        py.update({"torch": torch.__version__, "cuda_available": torch.cuda.is_available(),
                   "cuda_version": torch.version.cuda,
                   "devices": [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())]})
    except Exception as exc:
        py["torch_error"] = repr(exc)

    matlab = run(["where.exe", "matlab"], ROOT)
    dl1009 = ROOT.parent / "DL1009" / "RBF-BS0"
    ref = {"path": str(dl1009), "exists": dl1009.is_dir(),
           "expected_branch": "codex/kan-position-repair-code",
           "expected_head": "3671d2d212af927abdb6d9149a1b249c372ac55e"}
    if dl1009.is_dir():
        ref.update({"head": run(["git", "rev-parse", "HEAD"], dl1009),
                    "branch": run(["git", "branch", "--show-current"], dl1009),
                    "worktree_dirty": bool(run(["git", "status", "--porcelain=v1", "-uno"], dl1009)),
                    "remote_v": run(["git", "remote", "-v"], dl1009)})

    gate = json.loads((ROOT / "logs/gate_status.json").read_text(encoding="utf-8"))
    attempts = list(csv.DictReader((ROOT / "logs/attempt_index.csv").open(encoding="utf-8-sig", newline="")))
    episode = list(csv.DictReader((ROOT / "logs/episode_index.csv").open(encoding="utf-8-sig", newline="")))
    pids = run(["powershell.exe", "-NoProfile", "-Command",
                r"Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^(python|pythonw|matlab)(\.exe)?$' } |"
                " Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Depth 3"], ROOT)

    manifest = {
        "task": "DL1018_POSITION_CAUSAL_REPAIR_V1", "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "dl1018_root": str(ROOT), "review_base": "12bce70c5f69fd5055bc6cf798303cf2c6d80050",
        "git": git, "dl1009_reference": ref,
        "runtime": {"python": py, "matlab_where": matlab,
                    "matlab_version": "25.2.0.2978516 (R2025b; prior local verification)",
                    "active_python_matlab_processes_query": pids},
        "authorization_and_budget": {"plant_starts_max": 80, "fits_max": 6,
                                      "planned_d3": 6, "planned_d5_max": 18,
                                      "planned_d6_max": 48, "extra_plant_reserve": 8,
                                      "no_main_pipeline_restart": True, "no_auto_git_publish": True},
        "current_state": {"gate_status": gate, "attempt_rows": len(attempts),
                          "accepted_complete_attempts": sum(r.get("status") == "COMPLETE" and r.get("accepted_for_training", "").lower() == "true" for r in attempts),
                          "episode_rows": len(episode)},
        "protected_paths": ["data/raw/**", "data/events/**", "models/**", "logs/**", "reports/G00-G06*",
                             "configs/contract_dl1018.json", "configs/scene_specs.csv", "configs/selected_models.json",
                             "B/controller/Plant/scene generator/attitude RBF/safety and frozen gates"],
        "protected_file_fingerprints": files,
        "source_worktree_policy": "No modifications to original source/data/config/log/report paths; all derived work under experiments/position_causal_repair_v1/.",
        "dl1009_policy": "Read-only; worktree was found dirty before this experiment; no cleanup or edits."
    }
    (OUT / "manifests/SOURCE_AND_PROTECTION.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    (OUT / "state/state.json").write_text(json.dumps({
        "task": "DL1018_POSITION_CAUSAL_REPAIR_V1", "phase": "D0_COMPLETE", "next": "D1_G04_PAIRED_ANALYSIS",
        "status": "IN_PROGRESS", "plant_starts_new": 0, "fits_new": 0,
        "completed_run_ids": [], "completed_fit_ids": [], "active_process": None,
        "notes": ["G06 remains STOP_POSITION_NOT_QUALIFIED; no historical status is changed.",
                  "G04 contains 432 accepted P_INIT_STUDENT episodes; D1 will reuse exact same-scene B/POS_OFF/P_INIT logs."],
        "updated_at_utc": datetime.now(timezone.utc).isoformat()
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    (OUT / "reports/D0_CURRENT_STATE.md").write_text(
        "# D0 当前状态\n\n"
        f"- 时间：{datetime.now(timezone.utc).isoformat()}\n"
        f"- DL1018：HEAD `{git['head']}`，分支 `{git['branch']}`；受跟踪文件工作树清洁：`{git['tracked_worktree_clean']}`。\n"
        f"- DL1009：`{ref.get('head')}` / `{ref.get('branch')}`；只读参考，工作区含未提交变化（未清理、未修改）。\n"
        f"- 原运行状态：{gate.get('current_gate', gate.get('currentGate', '字段见原始 gate_status.json'))}；G06 的 `STOP_POSITION_NOT_QUALIFIED` 保持不变。\n"
        f"- 原台账：{len(attempts)} attempt 行，{len(episode)} episode 行。G04 报告为 PASS，432/432 稳定验收；这只代表航次可用，不代表 Student 胜过 B。\n"
        "- D1 配对范围固定为全部 G04 TRAIN384 + VAL48，每场精确连接 B、POS_OFF、P_INIT_STUDENT；缺失时报告，不补采。\n"
        "- 运行环境与原始小文件 SHA-256 在 `manifests/SOURCE_AND_PROTECTION.json`。\n"
        "- 新增资源：Plant 0，fit 0。当前无主流水线启动授权；只做离线分析。\n",
        encoding="utf-8")

    ledger = OUT / "RESOURCE_LEDGER.csv"
    if not ledger.exists():
        with ledger.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["timestamp_utc", "phase", "resource_type", "identity", "count", "status", "notes"])
            w.writerow([datetime.now(timezone.utc).isoformat(), "D0", "Plant", "new_plant_starts", 0, "COMPLETED", "No Plant started in D0."])
            w.writerow([datetime.now(timezone.utc).isoformat(), "D0", "fit", "new_encoder_fits", 0, "COMPLETED", "No fit started in D0."])
            w.writerow([datetime.now(timezone.utc).isoformat(), "D0", "reuse", "G04 paired historical runs", 1296, "REUSED", "432 scenes x B/POS_OFF/P_INIT_STUDENT; reuse does not count as new Plant."])

    print(json.dumps({"root": str(ROOT), "out": str(OUT), "head": git["head"],
                      "attempt_rows": len(attempts), "episode_rows": len(episode),
                      "matlab_process_query": pids}, ensure_ascii=False))


if __name__ == "__main__":
    main()
