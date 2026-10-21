#!/usr/bin/env python3
"""Single, ordered entry point for the DL1018 research Gates."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

import h5py
import numpy as np

CONTRACT = "DL1018_V311_R2E_PAPER_FINAL"
REFERENCE_CONTRACT_ID = "DL1018_SCENE_REF_FIG8_A2_V2"
GATES = [
    "G00_MIGRATION", "G01_SCENES", "G02_P_TEACHER", "G03_P_INITIAL",
    "G04_P_STUDENT", "G05_P_FINAL", "G06_P_DEV", "G07_A_TEACHER",
    "G08_A_INITIAL", "G09_A_STUDENT", "G10_A_FINAL", "G11_PA_DEV",
    "G12_FINAL_TEST", "G13_FINAL_REPORT",
]
EXIT_OK, EXIT_CONTRACT, EXIT_BLOCKED, EXIT_RUNTIME = 0, 10, 20, 40
EXIT_SCIENCE = 30
TRAINING_GATES = {"G03_P_INITIAL", "G05_P_FINAL", "G08_A_INITIAL", "G10_A_FINAL"}
ATTEMPT_COLUMNS = [
    "run_id", "gate_id", "split", "scene_id", "task", "class_index", "wind_cell",
    "collector_id", "model_id", "contract_version", "runtime_mode", "attempt_no",
    "status", "plant_started", "returned_transitions", "complete", "finite",
    "safety_stop_reason", "error_kind", "error_message", "raw_path",
    "position_event_path", "attitude_event_path", "started_at", "finished_at",
    "elapsed_s", "accepted_for_training",
]
EPISODE_COLUMNS = [
    "run_id", "split", "scene_id", "task", "class_index", "wind_cell",
    "source_role", "collector_id", "behavior_model_id", "contract_version",
    "position_event_path", "attitude_event_path", "complete", "finite",
    "transition_count", "event_count_position", "event_count_attitude",
    "ready_count_position", "ready_count_attitude", "accepted", "rejection_reason",
]


class GateError(RuntimeError):
    def __init__(self, message: str, code: int = EXIT_CONTRACT):
        super().__init__(message)
        self.code = code


def _safe_print(*args, **kwargs) -> bool:
    try:
        print(*args, **kwargs)
        return True
    except (OSError, ValueError):
        return False


def _stream_process_output(process: subprocess.Popen) -> int:
    assert process.stdout is not None
    forward_output = True
    with process.stdout:
        for line in process.stdout:
            if not forward_output:
                continue
            encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
            safe_line = line.encode(encoding, errors="replace").decode(encoding, errors="replace")
            forward_output = _safe_print(safe_line, end="", flush=True)
    return process.wait()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GateError(f"无法读取有效 JSON：{path}: {exc}", EXIT_RUNTIME) from exc
    return value if isinstance(value, dict) else None


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def gate_report(root: Path, gate: str) -> dict | None:
    return read_json(root / "reports" / f"{gate}.json")


def _has_legacy_scene_artifacts(root: Path) -> bool:
    if any((root / "reports" / f"{gate}.json").is_file() for gate in GATES[2:]):
        return True
    if any((root / "configs" / name).is_file() for name in ("scene_specs.csv", "dataset_plan.json")):
        return True
    if any((root / relative).is_file() and _csv_has_data_rows(root / relative)
           for relative in ("logs/attempt_index.csv", "logs/episode_index.csv")):
        return True
    if any(path.is_dir() and next(path.iterdir(), None) is not None for path in (
        root / "data" / "raw", root / "data" / "events" / "position",
        root / "data" / "events" / "attitude")):
        return True
    models = root / "models"
    return models.is_dir() and any(path.is_file() for path in models.rglob("*"))


def _csv_has_data_rows(path: Path) -> bool:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        next(stream, None)
        return any(line.strip() for line in stream)


def _assert_scene_buildable(root: Path) -> None:
    report = gate_report(root, "G01_SCENES")
    if report is not None:
        if report.get("reference_contract_id") != REFERENCE_CONTRACT_ID:
            raise GateError("G01 属于旧场景参考；请使用没有旧场景/采集产物的新输出根目录。", EXIT_CONTRACT)
        return
    if _has_legacy_scene_artifacts(root):
        raise GateError("G01 缺失但已有场景或下游产物；拒绝为旧数据根目录盖新身份。", EXIT_CONTRACT)


def _assert_scene_reference(root: Path) -> None:
    report = gate_report(root, "G01_SCENES")
    if (report is None or report.get("reference_contract_id") != REFERENCE_CONTRACT_ID or
            report.get("status") != "PASS" or not report.get("next_gate_allowed")):
        raise GateError("当前 G01 场景参考身份缺失或不匹配；下游 Gate 已 fail-closed。", EXIT_CONTRACT)


def report_statuses(root: Path) -> dict[str, str]:
    return {gate: (report.get("status", "NOT_STARTED") if (report := gate_report(root, gate)) else "NOT_STARTED")
            for gate in GATES}


def derive_state(root: Path) -> dict:
    statuses = report_statuses(root)
    saved = read_json(root / "logs" / "gate_status.json") or {}
    saved_statuses = saved.get("gate_status", {})
    for gate in GATES:
        if statuses[gate] == "NOT_STARTED" and saved_statuses.get(gate) == "RUNNING":
            statuses[gate] = "RUNNING"
    current = next((g for g in GATES if statuses[g] != "PASS" and not
                    (g == "G12_FINAL_TEST" and statuses[g] == "COMPLETE_WITH_NEGATIVE_TEST_RESULT")), None)
    return {
        "contract_version": CONTRACT,
        "updated_at": now(),
        "current_gate": current,
        "gate_status": statuses,
        "upstream_status": {g: {p: statuses[p] for p in GATES[:i]} for i, g in enumerate(GATES)},
        "actual_artifact_paths": [
            str(p.relative_to(root)).replace("\\", "/")
            for p in sorted((root / "reports").glob("G*.json"))
        ] if (root / "reports").is_dir() else [],
        "next_allowed_action": current or "COMPLETE",
    }


def save_state(root: Path, current: str | None = None, running: str | None = None,
               failed: str | None = None, error: str | None = None) -> None:
    state = derive_state(root)
    if current is not None:
        state["current_gate"] = current
    if running:
        state["gate_status"][running] = "RUNNING"
        state["current_gate"] = running
    if failed:
        state["gate_status"][failed] = "FAIL_RUNTIME_CONTRACT"
        state["current_gate"] = failed
        state["execution_error"] = error or "Unclassified execution error"
    state["updated_at"] = now()
    state["next_allowed_action"] = state["current_gate"] or "COMPLETE"
    atomic_json(root / "logs" / "gate_status.json", state)


def ensure_layout(root: Path) -> None:
    for relative in (
        "data/raw", "data/events/position", "data/events/attitude",
        "models/position/initial", "models/position/final_candidate", "models/position/selected",
        "models/attitude/initial", "models/attitude/final_candidate", "models/attitude/selected",
        "reports", "logs",
    ):
        (root / relative).mkdir(parents=True, exist_ok=True)
    for name, columns in (("attempt_index.csv", ATTEMPT_COLUMNS), ("episode_index.csv", EPISODE_COLUMNS)):
        path = root / "logs" / name
        if not path.exists():
            path.write_text(",".join(columns) + "\n", encoding="utf-8")


def matlab_executable() -> str:
    configured = os.environ.get("MATLAB_EXE")
    candidates = [configured, shutil.which("matlab"),
                  r"C:\Program Files\MATLAB\R2025b\bin\matlab.exe"]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate))
    raise GateError("找不到 MATLAB。设置 MATLAB_EXE 指向可执行文件。", EXIT_BLOCKED)


def matlab_quote(value: Path | str) -> str:
    return str(value).replace("'", "''")


def verify_g00_h5_layout(root: Path) -> dict:
    path = root / "reports" / "G00_H5_ORIENTATION_FIXTURE.h5"
    if not path.is_file():
        raise GateError(f"G00 HDF5 orientation fixture is missing: {path}", EXIT_RUNTIME)
    with h5py.File(path, "r") as handle:
        actual = np.asarray(handle["x"])
        expected = np.column_stack([np.asarray(handle[f"x29_{i}"]).reshape(-1) for i in range(1, 30)])
        scene_id = handle.attrs.get("scene_id", "")
        if isinstance(scene_id, bytes):
            scene_id = scene_id.decode("utf-8")
        if actual.shape != (expected.shape[0], 29) or not np.array_equal(actual, expected):
            raise GateError(f"HDF5 X29 cross-language layout mismatch: x={actual.shape}, scalar columns={expected.shape}", EXIT_CONTRACT)
        if scene_id != "G00_SYNTHETIC_EXPORT_FIXTURE":
            raise GateError(f"HDF5 scene_id metadata mismatch: {scene_id!r}", EXIT_CONTRACT)
    return {"shape": list(actual.shape), "scalar_column_round_trip": True,
            "scene_id": scene_id, "file": "reports/G00_H5_ORIENTATION_FIXTURE.h5"}


def record_h5_contract_check(root: Path, result: dict) -> None:
    check = {"field": "HDF5 X29 event-major cross-language layout", "expected": [3, 29],
             "actual": result["shape"], "source": "MATLAB writer read by Python h5py against scalar event columns",
             "pass": True}
    contract_path = root / "reports" / "contract_check.json"
    contract = read_json(contract_path)
    if contract:
        checks = contract.setdefault("checks", [])
        checks[:] = [item for item in checks if item.get("field") != check["field"]]
        checks.append(check)
        contract["status"] = "PASS" if all(item.get("pass") for item in checks) else "FAIL"
        atomic_json(contract_path, contract)
    gate_path = root / "reports" / "G00_MIGRATION.json"
    gate = read_json(gate_path)
    if gate:
        gate.setdefault("checks", {})["h5_cross_language_matrix_round_trip"] = True
        gate["artifacts"] = sorted(set(gate.get("artifacts", [])) | {result["file"]})
        atomic_json(gate_path, gate)


def run_matlab_gate(root: Path, source_root: Path | None, gate: str) -> dict:
    if gate not in {"G00_MIGRATION", "G01_SCENES", "G02_P_TEACHER", "G04_P_STUDENT", "G06_P_DEV",
                    "G07_A_TEACHER", "G09_A_STUDENT", "G11_PA_DEV", "G12_FINAL_TEST"}:
        raise GateError(f"{gate} 的执行器尚未实现；没有启动 Plant 或训练。", EXIT_BLOCKED)
    if gate == "G00_MIGRATION" and source_root is None:
        raise GateError("G00_MIGRATION 需要 --source-root。", EXIT_BLOCKED)
    source = source_root or root.parent / "DL1009"
    expression = (
        f"addpath('{matlab_quote(root / 'matlab' / 'runtime')}');"
        f"report=run_gate_dl1018('{gate}','{matlab_quote(root)}','{matlab_quote(source)}');"
        "assert(report.next_gate_allowed,'DL1018:GateFailed','Gate did not unlock its next permitted action.');"
    )
    command = [matlab_executable(), "-batch", expression]
    _safe_print("运行：" + subprocess.list2cmdline(command), flush=True)
    process = subprocess.Popen(command, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, encoding="utf-8", errors="replace", bufsize=1)
    return_code = _stream_process_output(process)
    report = gate_report(root, gate)
    if return_code != 0:
        raise GateError(f"MATLAB 退出码 {return_code}；Gate={report.get('status') if report else '无报告'}。", EXIT_RUNTIME)
    if not report or report.get("gate_id") != gate:
        raise GateError("MATLAB 返回 0，但 Gate 报告缺失或 Gate ID 不匹配。", EXIT_RUNTIME)
    if report.get("status") != "PASS" and not (gate == "G12_FINAL_TEST" and
                                                   report.get("status") == "COMPLETE_WITH_NEGATIVE_TEST_RESULT"):
        reason = report.get("blocking_reason") or report.get("status")
        raise GateError(f"{gate} 未通过科学门槛：{reason}", EXIT_SCIENCE)
    if gate == "G00_MIGRATION":
        try:
            h5_result = verify_g00_h5_layout(root)
        except GateError as exc:
            failed_check = {"field": "HDF5 X29 event-major cross-language layout", "expected": [3, 29],
                            "actual": str(exc), "source": "MATLAB writer read by Python h5py", "pass": False}
            contract = read_json(root / "reports" / "contract_check.json")
            if contract:
                checks = contract.setdefault("checks", [])
                checks[:] = [item for item in checks if item.get("field") != failed_check["field"]]
                checks.append(failed_check); contract["status"] = "FAIL"
                atomic_json(root / "reports" / "contract_check.json", contract)
            report["status"] = "FAIL_DATA_CONTRACT"
            report["next_gate_allowed"] = False
            report["blocking_reason"] = str(exc)
            report.setdefault("checks", {})["h5_cross_language_matrix_round_trip"] = False
            atomic_json(root / "reports" / f"{gate}.json", report)
            raise
        record_h5_contract_check(root, h5_result)
        _safe_print(f"Python h5py cross-language HDF5 check PASS: x={h5_result['shape']}", flush=True)
    return report


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    import csv
    with path.open("r", encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _control_summary(rows: list[dict[str, str]]) -> dict:
    def values(name: str) -> list[float]:
        result = []
        for row in rows:
            try:
                value = float(row.get(name, ""))
            except (TypeError, ValueError):
                continue
            if np.isfinite(value):
                result.append(value)
        return result

    def mean_max(name: str) -> str:
        xs = values(name)
        return "NA" if not xs else f"{sum(xs) / len(xs):.5g}/{max(xs):.5g}"

    reasons: dict[str, int] = {}
    for row in rows:
        reason = row.get("safety_stop_reason", "").strip()
        if reason:
            reasons[reason] = reasons.get(reason, 0) + 1
    complete = sum(row.get("status", "").upper() == "STABLE"
                   and row.get("complete", "").lower() in {"true", "1"} for row in rows)
    return {
        "n": len(rows), "complete": complete, "unsafe": len(rows) - complete,
        "peak_max": mean_max("position_peak_m").split("/")[-1],
        "p95_max": mean_max("position_p95_m").split("/")[-1],
        "sat_mean_max": mean_max("motor_saturation_fraction"),
        "clip_mean_max": mean_max("generalized_clip_fraction"),
        "tv_mean_max": mean_max("motor_TV_normalized_per_s"),
        "step_max": mean_max("max_motor_step_rad_s").split("/")[-1],
        "event_p99_max": mean_max("controller_p99_ms").split("/")[-1],
        "event_worst_max": mean_max("controller_worst_ms").split("/")[-1],
        "loop_p99_max": mean_max("control_loop_p99_ms").split("/")[-1],
        "motor_range": ("NA" if not values("motor_min_rad_s") or not values("motor_max_rad_s")
                        else f"{min(values('motor_min_rad_s')):.5g}–{max(values('motor_max_rad_s')):.5g}"),
        "safety_reasons": "; ".join(f"{name}×{count}" for name, count in sorted(reasons.items())) or "无",
    }


def run_final_report(root: Path) -> dict:
    statuses = report_statuses(root)
    if statuses["G12_FINAL_TEST"] not in {"PASS", "COMPLETE_WITH_NEGATIVE_TEST_RESULT"}:
        raise GateError("G13 requires a completed G12 TEST result.", EXIT_CONTRACT)
    reports = {gate: gate_report(root, gate) for gate in GATES[:-1]}
    attempts = _read_csv(root / "logs" / "attempt_index.csv")
    episodes = _read_csv(root / "logs" / "episode_index.csv")
    failures = [row for row in attempts if row.get("status") not in {"COMPLETE", "STABLE", "RUNNING"}]
    test = reports.get("G12_FINAL_TEST") or {}
    position_selection = read_json(root / "configs" / "selected_models.json") or {}
    lines = [
        "# DL1018 最终实验报告", "",
        f"合同：`{CONTRACT}`。本报告由已落盘的 Gate 结果和索引生成。", "",
        "## Gate 状态", "",
        "| Gate | 状态 | Plant 调用 | 完整样本 | 物理失败 | 工程错误 |", "|---|---:|---:|---:|---:|---:|",
    ]
    for gate in GATES[:-1]:
        report = reports.get(gate) or {}
        count = report.get("actual_counts", {})
        lines.append(f"| {gate} | {statuses[gate]} | {count.get('plant_started', 0)} | "
                     f"{count.get('complete', count.get('episodes_complete', 0))} | "
                     f"{count.get('physical_failures', 0)} | {count.get('engineering_errors', 0)} |")
    lines.extend(["", "## 模型与选择", "",
                  f"- 位置 Selected：{position_selection.get('position_selection', {}).get('selected_model_id', '未锁定')}；"
                  f"来源：{position_selection.get('position_selection', {}).get('selected_origin', '未锁定')}；"
                  f"Student 是否改变 Selected：{position_selection.get('position_selection', {}).get('student_changed_selected', '未记录')}。",
                  f"- P_STAR：{position_selection.get('position_star_method', '未锁定')}，"
                  f"位置 Head：{position_selection.get('position_selected_head_mode', '未锁定')}。",
                  f"- 姿态 Selected：{position_selection.get('attitude_selection', {}).get('selected_model_id', '未锁定')}；"
                  f"来源：{position_selection.get('attitude_selection', {}).get('selected_origin', '未锁定')}；"
                  f"Student 是否改变 Selected：{position_selection.get('attitude_selection', {}).get('student_changed_selected', '未记录')}。",
                  f"- 最终双环模式：{position_selection.get('final_dual_method', '未锁定')}。", "",
                  "离线残差分数的单位为位置 m/s²、姿态 rad/s²；闭环 Q/A 的单位为 m、rad。" ])
    for gate in ("G03_P_INITIAL", "G05_P_FINAL", "G08_A_INITIAL", "G10_A_FINAL"):
        report = reports.get(gate) or {};checks = report.get("checks", {})
        if checks:
            lines.append(f"- {gate}：best={checks.get('score_initial_or_best', '未记录')}，"
                         f"epoch0={checks.get('epoch0_score', '未记录')}，epoch={checks.get('best_epoch', '未记录')}。")
    lines.extend(["", "## DEV 与 TEST", ""])
    g06 = (reports.get("G06_P_DEV") or {}).get("checks", {})
    if g06:
        for name in ("P_F", "P_A"):
            score = g06.get(name, {})
            lines.append(f"- {name} DEV：pass={score.get('pass')}，macro_Q={score.get('macro_Q')} m，"
                         f"胜场={score.get('total_wins')}，peak warnings={score.get('peak_warnings')}。")
    g11 = (reports.get("G11_PA_DEV") or {}).get("checks", {})
    if g11:
        for name in ("PA_F", "PA_A"):
            score = g11.get(name, {})
            lines.append(f"- {name} DEV：pass={score.get('pass')}，macro_Q={score.get('macro_Q')} m，"
                         f"macro_A={score.get('macro_A')} rad。")
    checks = test.get("checks", {})
    lines.append(f"- FINAL_TEST 状态：{statuses['G12_FINAL_TEST']}；"
                 f"执行完成={checks.get('test_execution_complete')}；"
                 f"锁定位置通过={checks.get('locked_position_test_pass')}；"
                 f"锁定双环通过={checks.get('locked_dual_test_pass')}。")
    if checks.get("PA_A_minus_PA_F_macro_A_rad") is not None:
        lines.append(f"- PA_A−PA_F 配对增量：macro_A={checks.get('PA_A_minus_PA_F_macro_A_rad')} rad，"
                     f"macro_Q={checks.get('PA_A_minus_PA_F_macro_Q_m')} m；未因在线Head身份预设其更优。")
    for method, eligible in (checks.get("dev_safety_eligibility") or {}).items():
        if not eligible:
            lines.append(f"- {method} 因 DEV 安全准入失败而排除于 TEST；未替换场景。")
    lines.extend(["", "## 安全、峰值、饱和、TV 与时延", "",
                  "下表汇总逐场数据；`完整/不完整/未运行`按状态、20000步标志和固定场数统计。饱和、裁剪和TV列为均值/最大值；"
                  "计时列为该方法各场最大值。每场原值保存在对应CSV。", "",
                  "| 数据集 | 方法 | 场数/预定 | 完整/不完整/未运行 | 峰值最大 m | p95最大 m | 饱和均值/最大 | 裁剪均值/最大 | TV均值/最大 | "
                  "最大电机步进 rad/s | event p99最大 ms | event worst最大 ms | 1ms loop p99最大 ms | 电机范围 rad/s | 安全原因 |",
                  "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"])
    for label, filename in (("DEV_POSITION", "POSITION_DEV.csv"),
                            ("DEV_ATTITUDE", "ATTITUDE_DEV.csv"),
                            ("FINAL_TEST", "FINAL_TEST.csv")):
        table_rows = _read_csv(root / "reports" / filename)
        for method in sorted({row.get("method", "") for row in table_rows} - {""}):
            method_rows = [row for row in table_rows if row.get("method") == method]
            summary = _control_summary(method_rows)
            expected = 48 if label == "FINAL_TEST" else 24
            lines.append(f"| {label} | {method} | {summary['n']}/{expected} | "
                         f"{summary['complete']}/{summary['unsafe']}/{max(0, expected-summary['n'])} | "
                         f"{summary['peak_max']} | {summary['p95_max']} | {summary['sat_mean_max']} | "
                         f"{summary['clip_mean_max']} | {summary['tv_mean_max']} | {summary['step_max']} | "
                         f"{summary['event_p99_max']} | {summary['event_worst_max']} | {summary['loop_p99_max']} | "
                         f"{summary['motor_range']} | {summary['safety_reasons']} |")
    lines.append("逐场明细：`reports/POSITION_DEV.csv`、`reports/ATTITUDE_DEV.csv`、`reports/FINAL_TEST.csv`。")
    lines.extend(["", "## 失败与未完成事项", ""])
    if failures:
        lines.append(f"attempt_index 中记录 {len(failures)} 条非成功 attempt。具体场次和原因见 `logs/attempt_index.csv`。")
    else:
        lines.append("没有已记录的非成功 attempt。")
    unrun = [g for g, status in statuses.items() if status == "NOT_STARTED"]
    lines.append("未启动 Gate：" + (", ".join(unrun) if unrun else "无。"))
    lines.extend(["", "闭环数据按 scene 逐场配对；DEV 用于选择，TEST 不参与选模。"
                  "本工程未进行实机验证、SITL、完整稳定性证明或训练 seed 横评。", ""])
    report_path = root / "FINAL_REPORT.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    actual = {"plant_started": sum(row.get("plant_started", "").lower() in {"true", "1"} for row in attempts),
              "episodes_indexed": len(episodes), "failed_attempts": len(failures)}
    report = {"gate_id": "G13_FINAL_REPORT", "status": "PASS", "contract_version": CONTRACT,
              "upstream_passed": True, "actual_counts": actual,
              "checks": {"gate_statuses": statuses, "test_result": statuses["G12_FINAL_TEST"],
                         "offline_units_explicit": True, "dev_test_separated": True,
                         "limitations_explicit": True},
              "artifacts": ["FINAL_REPORT.md", "reports/G13_FINAL_REPORT.json"],
              "next_gate_allowed": False, "blocking_reason": ""}
    atomic_json(root / "reports" / "G13_FINAL_REPORT.json", report)
    return report


def _stream_process(command: list[str], cwd: Path, label: str) -> None:
    _safe_print("运行：" + subprocess.list2cmdline(command), flush=True)
    process = subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, encoding="utf-8", errors="replace", bufsize=1)
    code = _stream_process_output(process)
    if code:
        raise GateError(f"{label} 退出码 {code}。", EXIT_SCIENCE)


def run_model_parity(root: Path, modality: str, package: str) -> dict:
    expression = (
        f"addpath('{matlab_quote(root / 'matlab' / 'runtime')}');"
        f"addpath('{matlab_quote(root / 'matlab' / 'models')}');"
        f"addpath('{matlab_quote(root / 'matlab' / 'tests')}');"
        f"report=check_model_export_dl1018('{matlab_quote(root)}','{modality}','{package}');"
        "assert(strcmp(report.status,'PASS'),'DL1018:ModelParity','Model export parity failed.');"
    )
    _stream_process([matlab_executable(), "-batch", expression], root, f"{modality}/{package} MATLAB parity")
    path = root / "models" / modality / package / "matlab_parity.json"
    report = read_json(path)
    if not report or report.get("status") != "PASS" or report.get("fixture_count") != 64:
        raise GateError(f"{modality}/{package} MATLAB parity report is absent or failed.", EXIT_SCIENCE)
    return report


def run_training_gate(root: Path, gate: str) -> dict:
    mapping = {
        "G03_P_INITIAL": ("position", "initial", 2026101801),
        "G05_P_FINAL": ("position", "final", 2026101802),
        "G08_A_INITIAL": ("attitude", "initial", 2026101803),
        "G10_A_FINAL": ("attitude", "final", 2026101804),
    }
    modality, mode, seed = mapping[gate]
    script = root / "training" / f"train_{modality}.py"
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    _stream_process([sys.executable, str(script), "--root", str(root), "--mode", mode], root, gate)
    report_path = root / "reports" / f"{gate}.json"
    report = read_json(report_path)
    if not report or not report.get("training_passed"):
        raise GateError(f"{gate} fit report is missing or did not meet its training criterion.", EXIT_SCIENCE)
    package = "initial" if mode == "initial" else "final_candidate"
    export_command = [sys.executable, str(root / "training" / "export_matlab.py"),
                      "--root", str(root), "--modality", modality, "--package", package]
    _stream_process(export_command, root, f"{gate} MATLAB package export")
    candidate_parity = run_model_parity(root, modality, package)
    parity_records = [candidate_parity]
    if mode == "final":
        from training.common import lock_final_model
        best_epoch = int(report["checks"]["best_epoch"])
        initial_path = root / "models" / modality / "initial" / "best_model.pt"
        lock_final_model(root, modality, best_epoch, initial_path,
                         float(report["checks"]["score_initial_or_best"]))
        _stream_process([sys.executable, str(root / "training" / "export_matlab.py"),
                         "--root", str(root), "--modality", modality, "--package", "selected"],
                        root, f"{gate} Selected package export")
        selected_parity = run_model_parity(root, modality, "selected")
        parity_records.append(selected_parity)
        initial_info = read_json(root / "models" / modality / "initial" / "model.json") or {}
        candidate_info = read_json(root / "models" / modality / "final_candidate" / "model.json") or {}
        config_path = root / "configs" / "selected_models.json"
        config = read_json(config_path) or {"contract_version": CONTRACT}
        detail = report["checks"].get("score_detail", {})
        if modality == "position":
            grouped = detail.get("by_source_task_mps2", {})
            role_mse = {role: sum(float(grouped.get(f"{role}/{task}", 0.0)) ** 2 for task in
                                  ("HELIX", "FIG8_3D", "SQUARE")) / 3.0
                        for role in ("B", "POS_OFF", "P_INIT_STUDENT")}
            teacher_score = float(np.sqrt((0.25 * role_mse["B"] + 0.25 * role_mse["POS_OFF"]) / 0.5))
            student_score = float(np.sqrt(role_mse["P_INIT_STUDENT"]))
        else:
            grouped = detail.get("by_source_rads2", {})
            teacher_score = 0.5 * (float(grouped.get("B", 0.0)) + float(grouped.get("P_STAR", 0.0)))
            student_score = float(grouped.get("A_INIT_STUDENT", 0.0))
        config[f"{modality}_selection"] = {
            "initial_model_id": initial_info.get("model_id"),
            "final_candidate_model_id": candidate_info.get("model_id"),
            "normalizer_id": f"{modality.upper()}_INITIAL_TRAIN_ONLY",
            "epoch0_score_on_current_val": report["checks"]["epoch0_score"],
            "best_epoch": best_epoch,
            "best_score_on_current_val": report["checks"]["score_initial_or_best"],
            "selected_model_id": f"DL1018_{modality.upper()}_SELECTED",
            "selected_origin": "FINAL" if best_epoch > 0 else "INITIAL",
            "student_changed_selected": best_epoch > 0,
            "teacher_val_score": teacher_score,
            "student_val_score": student_score,
            "score_detail": report["checks"].get("score_detail", {}),
        }
        atomic_json(config_path, config)
        selection_path = root / "models" / modality / "final_candidate" / "selection.json"
        atomic_json(selection_path, config[f"{modality}_selection"])
    report["status"] = "PASS"
    report["next_gate_allowed"] = True
    report["checks"]["matlab_export_parity"] = parity_records
    report["artifacts"] = sorted(set(report.get("artifacts", [])) |
                                 {f"models/{modality}/{package}/matlab_model_and_parity.mat",
                                  f"models/{modality}/{package}/matlab_parity.json"})
    atomic_json(report_path, report)
    return report


def run_gate(root: Path, source_root: Path | None, gate: str, resume: bool = False) -> dict:
    if gate == "G01_SCENES":
        _assert_scene_buildable(root)
    elif GATES.index(gate) > GATES.index("G01_SCENES"):
        _assert_scene_reference(root)
    ensure_layout(root)
    index = GATES.index(gate)
    statuses = report_statuses(root)
    failed = [name for name in GATES[:index] if statuses[name] != "PASS"]
    if gate == "G13_FINAL_REPORT" and statuses.get("G12_FINAL_TEST") == "COMPLETE_WITH_NEGATIVE_TEST_RESULT":
        failed = [name for name in failed if name != "G12_FINAL_TEST"]
    if failed:
        raise GateError(f"Gate 未解锁：{gate} 的上游尚未 PASS：{', '.join(failed)}", EXIT_CONTRACT)
    existing = gate_report(root, gate)
    needs_h5_fixture = gate == "G00_MIGRATION" and not (root / "reports" / "G00_H5_ORIENTATION_FIXTURE.h5").is_file()
    if existing and (existing.get("status") == "PASS" or
                     (gate == "G12_FINAL_TEST" and existing.get("status") == "COMPLETE_WITH_NEGATIVE_TEST_RESULT")) \
            and not needs_h5_fixture:
        _safe_print(f"{gate} 已 PASS，跳过已完成阶段。", flush=True)
        save_state(root)
        return existing
    prior_state = read_json(root / "logs" / "gate_status.json") or {}
    prior_status = prior_state.get("gate_status", {}).get(gate, "NOT_STARTED")
    if prior_status == "RUNNING":
        if not resume:
            raise GateError(f"{gate} 上次处于 RUNNING；检查现有产物后使用 --resume。", EXIT_RUNTIME)
        if gate == "G02_P_TEACHER":
            attempt_path = root / "logs" / "attempt_index.csv"
            unresolved = False
            if attempt_path.is_file():
                import csv
                with attempt_path.open("r", encoding="utf-8", newline="") as stream:
                    unresolved = any(row.get("gate_id") == gate and row.get("status") == "RUNNING"
                                     for row in csv.DictReader(stream))
            if unresolved:
                raise GateError("G02 有未决 RUNNING attempt；先核对 Plant 标记与 raw，再恢复。", EXIT_RUNTIME)
        if gate not in {"G00_MIGRATION", "G01_SCENES"}:
            if gate != "G02_P_TEACHER":
                modality = "position" if "_P_" in gate else "attitude"
                fit_folder = "initial" if "INITIAL" in gate else "final_candidate"
                resumable_fit = (root / "models" / modality / fit_folder / "resume.pt").is_file()
                recoverable_collector = gate in {"G04_P_STUDENT", "G06_P_DEV", "G07_A_TEACHER",
                                                  "G09_A_STUDENT", "G11_PA_DEV", "G12_FINAL_TEST"}
                if gate not in TRAINING_GATES and not recoverable_collector:
                    raise GateError(f"{gate} 有未决 Plant/训练状态；需先核对 attempt_index 与完整产物。", EXIT_RUNTIME)
                if gate in TRAINING_GATES and not resumable_fit:
                    raise GateError(f"{gate} 有未决 Plant/训练状态；需先核对 attempt_index 与完整产物。", EXIT_RUNTIME)
    if existing and existing.get("status") in {"FAIL_DATA_CONTRACT", "FAIL_RUNTIME_CONTRACT",
                                                "FAIL_PERFORMANCE", "STOPPED_UNSAFE",
                                                "BLOCKED_MISSING_SOURCE", "BLOCKED_CONTRACT_CONFLICT"}:
        recoverable = (resume and gate == "G02_P_TEACHER" and
                       existing.get("status") == "FAIL_RUNTIME_CONTRACT" and
                       int(existing.get("actual_counts", {}).get("engineering_errors", 0)) == 1 and
                       int(existing.get("actual_counts", {}).get("physical_failures", 0)) == 0)
        recoverable = recoverable or (resume and gate == "G00_MIGRATION" and
                                      existing.get("status") == "FAIL_DATA_CONTRACT" and
                                      "HDF5" in str(existing.get("blocking_reason", "")) and
                                      int(existing.get("actual_counts", {}).get("plant_started", 0)) == 0)
        recoverable = recoverable or (resume and gate in {"G04_P_STUDENT", "G06_P_DEV", "G07_A_TEACHER",
                                                           "G09_A_STUDENT", "G11_PA_DEV", "G12_FINAL_TEST"} and
                                      existing.get("status") == "FAIL_RUNTIME_CONTRACT" and
                                      int(existing.get("actual_counts", {}).get("engineering_errors", 0)) == 1 and
                                      int(existing.get("actual_counts", {}).get("physical_failures", 0)) == 0)
        if not recoverable:
            raise GateError(f"{gate} 已有终态 {existing['status']}；需先复核其证据，禁止自动重跑。", EXIT_CONTRACT)
    save_state(root, running=gate)
    try:
        if gate in TRAINING_GATES:
            report = run_training_gate(root, gate)
        elif gate == "G13_FINAL_REPORT":
            report = run_final_report(root)
        else:
            report = run_matlab_gate(root, source_root, gate)
    except GateError as exc:
        report = gate_report(root, gate)
        if report:
            save_state(root, current=gate)
        else:
            save_state(root, failed=gate, error=str(exc))
        raise
    except Exception as exc:
        save_state(root, failed=gate, error=f"{type(exc).__name__}: {exc}")
        raise GateError(f"{gate} 执行异常：{type(exc).__name__}: {exc}", EXIT_RUNTIME) from exc
    save_state(root)
    return report


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按固定顺序执行 DL1018 Gate。")
    parser.add_argument("--source-root", type=Path, help="DL1009 只读合同源目录")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="DL1018 工程根目录")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--stage", choices=GATES, help="执行一个 Gate，不绕过上游状态")
    group.add_argument("--through", choices=GATES, help="按顺序执行到指定 Gate")
    group.add_argument("--status", action="store_true", help="只读显示 Gate 状态")
    parser.add_argument("--resume", action="store_true", help="跳过已 PASS 阶段并恢复已记录进度")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    root = args.root.expanduser().resolve()
    if not (root / "configs" / "contract_dl1018.json").is_file():
        _safe_print(f"不是 DL1018 工程根目录：{root}", file=sys.stderr)
        return EXIT_BLOCKED
    contract = read_json(root / "configs" / "contract_dl1018.json")
    if not contract or contract.get("contract_id") != CONTRACT:
        _safe_print("contract_dl1018.json 与锁定合同标识不匹配。", file=sys.stderr)
        return EXIT_CONTRACT
    if args.status:
        _safe_print(json.dumps(derive_state(root), ensure_ascii=False, indent=2))
        return EXIT_OK
    try:
        if args.stage == "G01_SCENES":
            _assert_scene_buildable(root)
        elif args.stage and GATES.index(args.stage) > GATES.index("G01_SCENES"):
            _assert_scene_reference(root)
        elif args.through and GATES.index(args.through) >= GATES.index("G01_SCENES"):
            _assert_scene_buildable(root)
    except GateError as exc:
        _safe_print(str(exc), file=sys.stderr)
        return exc.code
    source = args.source_root.expanduser().resolve() if args.source_root else None
    if source is not None and not source.is_dir():
        _safe_print(f"源目录不存在：{source}", file=sys.stderr)
        return EXIT_BLOCKED
    if args.stage:
        try:
            report = run_gate(root, source, args.stage, args.resume)
            _safe_print(f"{args.stage}: {report['status']}")
            return EXIT_OK
        except GateError as exc:
            _safe_print(str(exc), file=sys.stderr)
            return exc.code
    end = GATES.index(args.through)
    for gate in GATES[:end + 1]:
        try:
            report = run_gate(root, source, gate, args.resume)
            _safe_print(f"{gate}: {report['status']}", flush=True)
        except GateError as exc:
            _safe_print(str(exc), file=sys.stderr)
            return exc.code
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
