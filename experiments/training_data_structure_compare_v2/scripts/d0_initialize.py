from __future__ import annotations

import csv
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "experiments" / "training_data_structure_compare_v2"
PROTECTED = [
    "configs/contract_dl1018.json", "configs/scene_specs.csv", "configs/selected_models.json",
    "logs/gate_status.json", "logs/attempt_index.csv", "logs/episode_index.csv",
    "reports/G00_MIGRATION.json", "reports/G01_SCENES.json", "reports/G02_P_TEACHER.json",
    "reports/G03_P_INITIAL.json", "reports/G04_P_STUDENT.json", "reports/G05_P_FINAL.json",
    "reports/G06_P_DEV.json", "training/data.py", "training/models.py", "training/common.py",
    "training/train_position.py", "training/export_matlab.py",
    "matlab/runtime/collect_position_role_dl1018.m", "matlab/runtime/collect_position_dev_dl1018.m",
    "matlab/runtime/controller_options_dl1018.m", "matlab/data/export_position_events_dl1018.m",
    "matlab/metrics/metrics_dl1018.m",
    "experiments/position_causal_repair_v1/manifests/SOURCE_AND_PROTECTION.json",
    "experiments/position_causal_repair_v1/reports/FINAL_CAUSAL_REPORT_ZH.md",
    "experiments/position_causal_repair_v1/reports/D4_TRAINING_COMPARISON.csv",
]


def cmd(args: list[str]) -> str:
    p = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, check=False)
    return (p.stdout or p.stderr).strip()


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    for name in ("scripts", "local_runtime", "manifests", "derived", "models", "runs", "reports", "state"):
        (OUT / name).mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    git = {
        "head": cmd(["git", "rev-parse", "HEAD"]),
        "branch": cmd(["git", "branch", "--show-current"]),
        "origin": cmd(["git", "remote", "get-url", "origin"]),
        "tracked_worktree_status": cmd(["git", "status", "--porcelain=v1", "-uno"]),
        "untracked_status": cmd(["git", "status", "--porcelain=v1", "--untracked-files=all"]),
    }
    fingerprints = []
    for rel in PROTECTED:
        p = ROOT / rel
        fingerprints.append({"path": rel, "exists": p.is_file(),
                             "size_bytes": p.stat().st_size if p.is_file() else None,
                             "sha256": sha(p) if p.is_file() else None})
    try:
        import torch
        runtime = {"python_executable": sys.executable, "python_version": sys.version,
                   "platform": platform.platform(), "torch": torch.__version__,
                   "cuda_available": torch.cuda.is_available(), "cuda": torch.version.cuda,
                   "devices": [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())]}
    except Exception as e:
        runtime = {"python_executable": sys.executable, "python_version": sys.version,
                   "platform": platform.platform(), "torch_error": repr(e)}
    try:
        import pandas as pd
        attempts = pd.read_csv(ROOT / "logs/attempt_index.csv", keep_default_na=False)
        episodes = pd.read_csv(ROOT / "logs/episode_index.csv", keep_default_na=False)
        split_counts = episodes.loc[episodes.accepted.astype(str).str.lower().isin(("true", "1"))].groupby(
            ["split", "source_role"]).size().to_dict()
        data_index = {"attempt_rows": len(attempts), "episode_rows": len(episodes),
                      "accepted_split_role_counts": {"/".join(map(str, k)): int(v) for k, v in split_counts.items()}}
    except Exception as e:
        data_index = {"error": repr(e)}
    pcf = subprocess.run(["powershell.exe", "-NoProfile", "-Command",
                          "Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^(python|pythonw|matlab)(\\.exe)?$' -and $_.CommandLine -match 'DL1018|run_dl1018.py' } | Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Depth 3"],
                         cwd=ROOT, capture_output=True, text=True, check=False)
    try:
        procs = json.loads(pcf.stdout) if pcf.stdout.strip() else []
    except Exception:
        procs = pcf.stdout.strip()
    (OUT / "manifests/SOURCE_AND_PROTECTION.json").write_text(json.dumps({
        "task": "DL1018_TRAINING_DATA_STRUCTURE_COMPARE_V2", "captured_at_utc": now,
        "root": str(ROOT), "git": git,
        "review_bases": {"DL1018_main": "12bce70c5f69fd5055bc6cf798303cf2c6d80050",
                         "causal_diagnosis": "7b5ec35605f7a49316e4a905e5afa2c26320998d",
                         "DL1009_reference": "3671d2d212af927abdb6d9149a1b249c372ac55e"},
        "runtime": runtime, "data_index": data_index, "relevant_processes": procs,
        "resource_budget": {"micro_fits_max": 2, "official_fits_max": 8,
                             "canary_plants_max": 24, "dev_plants_max": 48,
                             "total_new_plants_max": 80},
        "protected_files": fingerprints,
        "protected_paths": ["configs/contract_dl1018.json", "B", "Plant", "data/raw/**",
                            "data/events/**", "models/**", "logs/**", "reports/G00-G06*",
                            "experiments/position_causal_repair_v1/**"],
        "policy": "All generated material remains under experiments/training_data_structure_compare_v2/. No push/commit/merge."
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "state/state.json").write_text(json.dumps({
        "task": "DL1018_TRAINING_DATA_STRUCTURE_COMPARE_V2", "phase": "D0_COMPLETE",
        "status": "IN_PROGRESS", "next": "STEP1_AUDIT_AND_FREEZE_MICRO_POOL",
        "fits_started": 0, "fits_completed": [], "plant_started": 0, "plant_completed": [],
        "active_fit": None, "active_run": None, "updated_at_utc": now,
        "notes": ["Original contract, B, Plant, source data, formal artifacts and causal repair experiment are read-only.",
                  "G06 failure remains unchanged.", "Existing data only; no new data collection authorized."]
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ledger = OUT / "RESOURCE_LEDGER.csv"
    if not ledger.exists():
        with ledger.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["timestamp_utc", "phase", "resource_type", "identity", "count", "status", "notes"])
            w.writerow([now, "D0", "Plant", "new_plant_starts", 0, "COMPLETED", "No Plant in D0."])
            w.writerow([now, "D0", "fit", "encoder_fits", 0, "COMPLETED", "No fit in D0."])
            w.writerow([now, "D0", "reuse", "source_records", "existing", "READ_ONLY", "No original data copied or modified."])
    (OUT / "README_EXECUTION.md").write_text(
        "# DL1018 训练数据与结构对照 v2\n\n"
        "本目录只保存本轮脚本、清单、派生数据、模型、运行记录和报告。原合同、B、Plant、源数据、正式输出及 `position_causal_repair_v1` 均只读。\n\n"
        "- 任务书：`DL1018_训练数据与结构对照Prompt_v2.md`（本机 Downloads；完整内容已由执行者审阅）。\n"
        "- D0 来源与保护指纹：`manifests/SOURCE_AND_PROTECTION.json`。\n"
        "- 可恢复状态：`state/state.json`；资源：`RESOURCE_LEDGER.csv`。\n"
        "- 不提交、不推送、不合并。所有 fit/run 使用固定 identity；重连先读状态和对应 resume/checkpoint。\n",
        encoding="utf-8")
    print(json.dumps({"out": str(OUT), "head": git["head"], "branch": git["branch"],
                      "data_index": data_index, "runtime": runtime, "processes": procs}, ensure_ascii=False))


if __name__ == "__main__":
    main()
