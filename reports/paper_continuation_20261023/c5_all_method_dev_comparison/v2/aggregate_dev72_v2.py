#!/usr/bin/env python3
"""Reaggregate only the five specified audited summary artifacts; never reads raw data."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any

getcontext().prec = 50

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
INPUTS = {
    "corrected14_scene_csv": ROOT / "reports/corrected14_full72_benchmark_20261021/PAIR14_SCENE_RESULTS_VS_B.csv",
    "corrected14_validation_json": ROOT / "reports/corrected14_full72_benchmark_20261021/VALIDATION_SUMMARY.json",
    "corrected14_report_md": ROOT / "reports/corrected14_full72_benchmark_20261021/RESULTS_14D_VS_B_ZH.md",
    "c5_metrics_csv": ROOT / "reports/paper_continuation_20261023/c5_dev72_parent_review/C5_DEV72_RAW_METRICS_v3.csv",
    "c5_raw_parent_review_json": ROOT / "reports/paper_continuation_20261023/c5_dev72_parent_review/C5_DEV72_RAW_PARENT_REVIEW_v3.json",
}
OUTPUTS = (
    "SCENE_METHOD_METRICS.csv",
    "GROUP_METHOD_VS_B_SUMMARY.csv",
    "PAIRWISE_SCENE_COMPARISONS.csv",
    "GROUP_PAIRWISE_SUMMARY.csv",
    "ALL_LOSSES.csv",
    "METHOD_PROVENANCE.csv",
    "B_Q_MATCH_AUDIT.csv",
    "SUMMARY.json",
    "README_ZH.md",
)
TIE_M = Decimal("1e-12")
ONE_UM_M = Decimal("1e-6")
TEN_UM_M = Decimal("1e-5")
METHOD_ORDER = (
    "C5_M110",
    "B_TRACEABLE",
    "C3",
    "CORRECTED_TRAIN_DSSM14_G12_R32",
    "CORRECTED_TRAIN_KAN14_G12_R32",
)
LABELS = {
    "C5_M110": "C5 M110",
    "B_TRACEABLE": "B traceable",
    "C3": "C3",
    "CORRECTED_TRAIN_DSSM14_G12_R32": "corrected DSSM14",
    "CORRECTED_TRAIN_KAN14_G12_R32": "corrected KAN14",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def need(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def dec(value: Any, label: str) -> Decimal:
    try:
        out = Decimal(str(value))
    except Exception as exc:
        raise ValueError(f"invalid decimal for {label}: {value!r}") from exc
    need(out.is_finite(), f"non-finite decimal for {label}: {value!r}")
    return out


def fmt(value: Decimal | int | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        if value == 0:
            return "0"
        return format(value, "f")
    return str(value)


def fmt_mm_readable(value: Any) -> str:
    """Round only human-facing README millimetre values; machine outputs stay exact."""
    return f"{dec(value, 'README mm value').quantize(Decimal('0.000001')):.6f}"


def dump_csv(rows: list[dict[str, Any]], fields: list[str]) -> bytes:
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="raise", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: fmt(row.get(k)) for k in fields})
    return buf.getvalue().encode("utf-8")


def dump_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def outcome(delta_m: Decimal) -> str:
    if delta_m < -TIE_M:
        return "WIN"
    if delta_m > TIE_M:
        return "LOSS"
    return "TIE"


def win_stats(deltas: list[Decimal]) -> dict[str, int]:
    return {
        "wins": sum(outcome(d) == "WIN" for d in deltas),
        "losses": sum(outcome(d) == "LOSS" for d in deltas),
        "ties": sum(outcome(d) == "TIE" for d in deltas),
        "wins_gt_1um": sum(d < -ONE_UM_M for d in deltas),
        "wins_gt_10um": sum(d < -TEN_UM_M for d in deltas),
    }


def mean(values: list[Decimal]) -> Decimal:
    need(bool(values), "cannot average an empty group")
    return sum(values, Decimal(0)) / Decimal(len(values))


def scene_parts(scene_id: str) -> tuple[str, str]:
    match = re.fullmatch(r"DL1018_(DEV|VAL)_T[123]_C\d{2}_(W\d{2})", scene_id)
    need(match is not None, f"unexpected scene id: {scene_id}")
    return match.group(1), match.group(2)


def make_groups(scene_ids: list[str], scene_info: dict[str, dict[str, str]]) -> list[tuple[str, str, list[str]]]:
    groups: list[tuple[str, str, list[str]]] = [("ALL", "ALL72", list(scene_ids))]
    hf = [s for s in scene_ids if 9 <= int(scene_info[s]["wind_group"][1:]) <= 14]
    w15 = [s for s in scene_ids if scene_info[s]["wind_group"] == "W15"]
    need(bool(hf) and bool(w15), "HF or W15 group is empty")
    groups.append(("HF", "W09_W14", hf))
    groups.append(("W15", "W15", w15))
    for task in sorted({scene_info[s]["task"] for s in scene_ids}):
        groups.append(("TASK", task, [s for s in scene_ids if scene_info[s]["task"] == task]))
    for wind in sorted({scene_info[s]["wind_group"] for s in scene_ids}):
        groups.append(("WIND", wind, [s for s in scene_ids if scene_info[s]["wind_group"] == wind]))
    return groups


def make_report(summary: dict[str, Any], output_hashes: dict[str, str], script_sha: str) -> bytes:
    all_methods = summary["overall_by_method_vs_B"]
    pairwise = summary["overall_C5_vs_methods"]
    lines = [
        "# C5 DEV72 五方法逐场二次汇总",
        "",
        "本文件由指定的五份已审核汇总文件再计算；没有重读 MAT/raw，没有重新评分，也没有重新审核历史 corrected14 raw。corrected DSSM14/KAN14 来自 2026-10-21 历史 PAIR14 汇总。对不同方法之间的同批次身份不作断言。",
        "",
        "## 身份与核对",
        "",
        f"- 五种方法各有 {summary['scene_count']} 个唯一场景，场景集合完全相同。输入 B 的未舍入 Q 与 traceable B：{summary['B_Q_identity_check']['exact_scene_matches']}/{summary['scene_count']} 个场景十进制值相等；最大绝对差为 `{summary['B_Q_identity_check']['max_abs_decimal_diff_m']} m`。历史 B scorer 来源仍保留在逐场表中；不同方法的同批次身份未作断言。",
        f"- C5 审核状态 `{summary['c5_parent_review']['status']}`；60 个新场景、12 个已审核复用场景。此次只复用报告/CSV中已有分数和身份字段。",
        f"- tie 容差为 `{summary['thresholds']['tie_tolerance_m']} m`；敏感性计数分别严格要求改善超过 1 μm、10 μm。各组对场景等权，不做 bootstrap。",
        "",
        "## ALL72 结果",
        "",
        "| 方法 | method_id | 平均 Q (mm) | 相对 traceable B 胜/平/负 | >1 μm / >10 μm 胜 |",
        "|---|---|---:|---:|---:|",
    ]
    for method_id in METHOD_ORDER:
        x = all_methods[method_id]
        lines.append(
            f"| {LABELS[method_id]} | `{method_id}` | {fmt_mm_readable(x['mean_Q_mm'])} | "
            f"{x['wins_vs_B']}/{x['ties_vs_B']}/{x['losses_vs_B']} | {x['wins_gt_1um']} / {x['wins_gt_10um']} |"
        )
    lines += ["", "## C5 对各方法的逐场比较", "", "| 对照方法 | C5 胜/平/负 | C5 >1 μm / >10 μm 胜 | C5−对照平均差 (mm) |", "|---|---:|---:|---:|"]
    for other in METHOD_ORDER:
        if other == "C5_M110":
            continue
        x = pairwise[other]
        lines.append(f"| {LABELS[other]} | {x['wins']}/{x['ties']}/{x['losses']} | {x['wins_gt_1um']} / {x['wins_gt_10um']} | {fmt_mm_readable(x['mean_delta_A_minus_B_mm'])} |")
    lines += [
        "",
        "## 分组和文件",
        "",
        "`GROUP_METHOD_VS_B_SUMMARY.csv` 给出 ALL、HF(W09–W14)、W15、各任务及各风组的等权均值和相对 B 胜负；`GROUP_PAIRWISE_SUMMARY.csv` 同样汇总所有方法两两比较，含 C5 对每个方法。`SCENE_METHOD_METRICS.csv` 保留逐场 Q 和方法身份；历史 DSSM14/KAN14 行保留完整 method_id、model_id、candidate scorer/raw-scan/rescore SHA、逐场 raw SHA，以及原始 B scorer/source 身份。`ALL_LOSSES.csv` 只收录每个无序方法对中方向列 `method_a` 判为 LOSS 的记录；反向方向的输者可在完整 `PAIRWISE_SCENE_COMPARISONS.csv` 中查看。`B_Q_MATCH_AUDIT.csv` 列出两套历史 B 与 traceable B 的逐场精确十进制差。README 的 mm 表格数字显示到 6 位小数；CSV/JSON 保留完整精度。",
        "",
        "## 来源 SHA256",
        "",
        f"脚本：`{script_sha}`",
    ]
    for name, value in summary["inputs"].items():
        lines.append(f"- `{name}`: `{value['sha256']}`")
    lines.append("")
    for name, sha in output_hashes.items():
        lines.append(f"- `{name}`: `{sha}`")
    lines += [
        "",
        "## 可重现命令",
        "",
        "在仓库根目录首次生成：",
        "",
        "```powershell",
        "python reports/paper_continuation_20261023/c5_all_method_dev_comparison/v2/aggregate_dev72_v2.py",
        "```",
        "",
        "在输出文件已存在时做无写入的逐字节复算核对：",
        "",
        "```powershell",
        "python reports/paper_continuation_20261023/c5_all_method_dev_comparison/v2/aggregate_dev72_v2.py --verify-existing",
        "```",
        "",
        "汇总范围仅限 DEV/VAL 开发场景；不含 TEST，不含新仿真、训练或 raw 重审。",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def build_artifacts() -> tuple[dict[str, bytes], dict[str, Any]]:
    for name, path in INPUTS.items():
        need(path.is_file(), f"missing specified input {name}: {path}")
    input_hashes = {name: {"path": path.relative_to(ROOT).as_posix(), "sha256": sha256_file(path)} for name, path in INPUTS.items()}
    old_rows = read_csv(INPUTS["corrected14_scene_csv"])
    validation = read_json(INPUTS["corrected14_validation_json"])
    report_text = INPUTS["corrected14_report_md"].read_text(encoding="utf-8")
    c5_rows_csv = read_csv(INPUTS["c5_metrics_csv"])
    c5_review = read_json(INPUTS["c5_raw_parent_review_json"])

    need(validation.get("status") == "FINAL_COMPLETE", "corrected14 validation is not FINAL_COMPLETE")
    need(validation.get("pair14_status") == "PASS_COMPOSED_144_ALL_STABLE_TWO_SESSIONS", "corrected14 PAIR14 status mismatch")
    need(validation.get("pair14_rows") == 144 and validation.get("result_rows_parsed") == 432, "corrected14 row-count metadata mismatch")
    need("corrected DSSM14" in report_text and "corrected KAN14" in report_text, "historical report identity text missing")
    need(c5_review.get("status") == "PASS_C5_DEV72_RAW_ALL_EVENTS_PARENT_AUDIT", "C5 parent audit is not PASS")
    need(c5_review.get("scope") == "DEV_ONLY_NO_TEST" and c5_review.get("TEST_accessed") is False, "C5 summary is outside DEV-only scope")
    need(c5_review.get("scene_count") == 72 and len(c5_rows_csv) == 72 and len(c5_review.get("rows", [])) == 72, "C5 row-count metadata mismatch")
    need(c5_review.get("new_scenes_event_checked") == 60 and c5_review.get("reused_scenes_event_audit_refs") == 12, "C5 new/reused scene counts mismatch")
    need(c5_review.get("plant_calls_in_audit") == 0 and c5_review.get("training_steps") == 0 and c5_review.get("optimizer_steps") == 0, "C5 audit reports prohibited activity")

    old_method_ids = {row["method_id"] for row in old_rows}
    expected_old_ids = {"CORRECTED_TRAIN_DSSM14_G12_R32", "CORRECTED_TRAIN_KAN14_G12_R32"}
    need(old_method_ids == expected_old_ids, f"unexpected historical method ids: {sorted(old_method_ids)}")
    old_by_method: dict[str, dict[str, dict[str, str]]] = {mid: {} for mid in expected_old_ids}
    scene_info: dict[str, dict[str, str]] = {}
    legacy_b_identity_by_scene: dict[str, tuple[str, ...]] = {}
    legacy_b_q_by_scene: dict[str, Decimal] = {}
    for row in old_rows:
        mid = row["method_id"]
        scene = row["source_scene_id"]
        need(scene not in old_by_method[mid], f"duplicate corrected14 method-scene: {mid}/{scene}")
        old_by_method[mid][scene] = row
        split_from_id, wind = scene_parts(scene)
        need(row["split"] == split_from_id, f"split and scene id disagree: {scene}")
        task_from_t = {"T1": "HELIX", "T2": "FIG8_3D", "T3": "SQUARE"}[scene.split("_")[2]]
        need(row["task"] == task_from_t, f"task and scene id disagree: {scene}")
        info = {"split": row["split"], "task": row["task"], "wind_group": wind, "contract_id": row["contract_id"]}
        if scene in scene_info:
            need(scene_info[scene] == info, f"corrected14 metadata differs by method for {scene}")
        else:
            scene_info[scene] = info
        b_identity = tuple(row[k] for k in ("B_score_source", "B_scorer_sha256", "B_raw_scan_sha256", "B_rescore_runner_sha256"))
        if scene in legacy_b_identity_by_scene:
            need(legacy_b_identity_by_scene[scene] == b_identity, f"historical B provenance differs by method for {scene}")
            need(legacy_b_q_by_scene[scene] == dec(row["B_Q_0_20_m"], "old B"), f"historical B Q differs by corrected method for {scene}")
        else:
            legacy_b_identity_by_scene[scene] = b_identity
            legacy_b_q_by_scene[scene] = dec(row["B_Q_0_20_m"], "old B")
    for mid, rows in old_by_method.items():
        need(len(rows) == 72, f"{mid} has {len(rows)} rows, expected 72")
        for field in ("model_id", "candidate_score_source", "candidate_scorer_sha256", "candidate_raw_scan_sha256", "candidate_rescore_runner_sha256", "replay_cell_status", "valid_replay_events", "external_arrays_sha256_match"):
            need(len({r[field] for r in rows.values()}) == 1, f"historical identity field varies within {mid}: {field}")
        need(next(iter(rows.values()))["candidate_score_source"] == "RAW_SCAN", f"unexpected candidate source for {mid}")
        need(all(r["replay_cell_status"] == "REPLAY_VALID" and r["valid_replay_events"] == "1968" and r["external_arrays_sha256_match"] == "True" for r in rows.values()), f"replay evidence failure for {mid}")

    c5_metrics_by_scene = {r["scene_id"]: r for r in c5_rows_csv}
    c5_review_by_scene = {r["scene_id"]: r for r in c5_review["rows"]}
    need(len(c5_metrics_by_scene) == len(c5_rows_csv) == 72, "duplicate C5 metrics scene ids")
    need(len(c5_review_by_scene) == len(c5_review["rows"]) == 72, "duplicate C5 review scene ids")
    scene_ids = sorted(scene_info)
    need(set(scene_ids) == set(c5_metrics_by_scene) == set(c5_review_by_scene), "the reviewed method scene sets are not identical")
    event_sources = {r["scene_id"]: r.get("source", "") for r in c5_review.get("event_check_rows", [])}
    need(len(event_sources) == 72, "C5 event-audit metadata does not cover all scenes")
    need(sum(v == "DEV72_NEW_RAW_PARENT_RECOMPUTATION" for v in event_sources.values()) == 60, "C5 new-scene event-source count mismatch")
    need(sum(v == "C5_SCREEN_PARENT_AUDIT_REUSED" for v in event_sources.values()) == 12, "C5 reused-scene event-source count mismatch")

    method_scores: dict[str, dict[str, Decimal]] = {mid: {} for mid in METHOD_ORDER}
    method_scene_rows: list[dict[str, Any]] = []
    for mid in sorted(expected_old_ids):
        for scene in scene_ids:
            row = old_by_method[mid][scene]
            q = dec(row["candidate_Q_0_20_m"], f"{mid} Q {scene}")
            method_scores[mid][scene] = q
            method_scene_rows.append({
                **scene_info[scene], "scene_id": scene, "method_id": mid, "method_label": LABELS[mid],
                "Q_0_20_m": row["candidate_Q_0_20_m"], "source_artifact": "corrected14_full72_benchmark_20261021/PAIR14_SCENE_RESULTS_VS_B.csv",
                "model_id": row["model_id"], "score_source": row["candidate_score_source"],
                "scorer_sha256": row["candidate_scorer_sha256"], "raw_scan_sha256": row["candidate_raw_scan_sha256"],
                "raw_sha256": row["candidate_raw_sha256"], "rescore_runner_sha256": row["candidate_rescore_runner_sha256"],
                "replay_cell_status": row["replay_cell_status"], "valid_replay_events": row["valid_replay_events"],
                "external_arrays_sha256_match": row["external_arrays_sha256_match"],
                "legacy_B_score_source": row["B_score_source"], "legacy_B_scorer_sha256": row["B_scorer_sha256"],
                "legacy_B_raw_scan_sha256": row["B_raw_scan_sha256"], "legacy_B_rescore_runner_sha256": row["B_rescore_runner_sha256"],
                "parent_audit_sha256": "", "event_check_source": "", "event_check_sha256": "",
                "parent_audit_input_lock_sha256": "", "parent_audit_run_contract_sha256": "", "parent_audit_source_binding_sha256": "", "parent_audit_release_sha256": "",
                "metric_scorer_sha256": "", "external_identity_sha256": "",
            })

    audit_rows = c5_review_by_scene
    metrics_rows = c5_metrics_by_scene
    for scene in scene_ids:
        ar = audit_rows[scene]
        mr = metrics_rows[scene]
        expected_status = "PASS_C5_RAW_ALL_EVENTS" if event_sources[scene] == "DEV72_NEW_RAW_PARENT_RECOMPUTATION" else "PASS_REUSED_C5_SCREEN_AUDIT"
        need(ar.get("status") == expected_status, f"C5 audit row status/source mismatch: {scene}")
        need(mr["comparison_vs_B"] == ar["comparison_vs_B"], f"C5 comparison labels disagree: {scene}")
        for key, field in (("C5_M110", "C5_metrics"), ("C3", "C3_metrics"), ("B_TRACEABLE", "B_metrics")):
            metric = ar[field]
            mid = metric.get("method")
            need(mid == key, f"unexpected metric method {mid!r} for {key}")
            q = dec(metric["Q_0_20_m"], f"{key} JSON Q {scene}")
            q_csv_field = {"C5_M110": "Q_C5_0_20_m", "C3": "Q_C3_0_20_m", "B_TRACEABLE": "Q_B_0_20_m"}[key]
            q_csv = dec(mr[q_csv_field], f"{key} CSV Q {scene}")
            need(q == q_csv, f"{key} Q differs between specified CSV and JSON for {scene}: {q} vs {q_csv}")
            method_scores[key][scene] = q
            if key == "C5_M110":
                c5_source_key = "C5_new" if event_sources.get(scene) == "DEV72_NEW_RAW_PARENT_RECOMPUTATION" else "C5_reuse"
                source_artifact = c5_review["data_sources"].get(c5_source_key, c5_source_key)
            else:
                source_artifact = c5_review["data_sources"].get({"C3": "C3", "B_TRACEABLE": "B"}[key], "C5_DEV72_RAW_PARENT_AUDIT_V3")
            method_scene_rows.append({
                **scene_info[scene], "scene_id": scene, "method_id": key, "method_label": LABELS[key],
                "Q_0_20_m": mr[q_csv_field],
                "source_artifact": source_artifact,
                "model_id": "", "score_source": "C5_DEV72_RAW_PARENT_AUDIT_V3_METRICS",
                "scorer_sha256": c5_review["metric_scorer_sha256"], "raw_scan_sha256": "",
                "raw_sha256": metric["sha256"], "rescore_runner_sha256": "",
                "replay_cell_status": "", "valid_replay_events": "", "external_arrays_sha256_match": "",
                "legacy_B_score_source": "", "legacy_B_scorer_sha256": "", "legacy_B_raw_scan_sha256": "", "legacy_B_rescore_runner_sha256": "",
                "parent_audit_sha256": input_hashes["c5_raw_parent_review_json"]["sha256"],
                "event_check_source": event_sources.get(scene, "") if key == "C5_M110" else "",
                "event_check_sha256": ar.get("event_check_sha256", "") if key == "C5_M110" else "",
                "parent_audit_input_lock_sha256": c5_review["input_lock_sha256"], "parent_audit_run_contract_sha256": c5_review["run_contract_sha256"],
                "parent_audit_source_binding_sha256": c5_review["source_binding_sha256"], "parent_audit_release_sha256": c5_review["release_sha256"],
                "metric_scorer_sha256": c5_review["metric_scorer_sha256"],
                "external_identity_sha256": metric.get("external_identity_sha256", ""),
            })
        external = [ar[k + "_metrics"].get("external_identity_sha256") for k in ("C5", "C3", "B")]
        need(len(set(external)) == 1 and external[0], f"external identity mismatch in C5 parent metrics for {scene}")

    need(all(len(method_scores[mid]) == 72 for mid in METHOD_ORDER), "not every method has exactly 72 unique scene scores")
    need(all(set(method_scores[mid]) == set(scene_ids) for mid in METHOD_ORDER), "method scene sets differ")

    b_match_rows: list[dict[str, Any]] = []
    b_exact_by_old_method: dict[str, int] = {}
    b_max_abs_by_old_method: dict[str, Decimal] = {}
    b_mismatches_by_method: dict[str, list[dict[str, str]]] = {}
    for mid in sorted(expected_old_ids):
        exact_count = 0
        diffs: list[Decimal] = []
        mismatch_rows: list[dict[str, str]] = []
        for scene in scene_ids:
            old_q = dec(old_by_method[mid][scene]["B_Q_0_20_m"], f"historical B Q {mid}/{scene}")
            new_q = method_scores["B_TRACEABLE"][scene]
            delta = old_q - new_q
            diffs.append(abs(delta))
            if delta == 0:
                exact_count += 1
            else:
                mismatch_rows.append({"scene_id": scene, "historical_B_minus_traceable_B_m": fmt(delta)})
        b_exact_by_old_method[mid] = exact_count
        b_max_abs_by_old_method[mid] = max(diffs)
        b_mismatches_by_method[mid] = mismatch_rows
    need(b_exact_by_old_method["CORRECTED_TRAIN_DSSM14_G12_R32"] == b_exact_by_old_method["CORRECTED_TRAIN_KAN14_G12_R32"], "historical B exact-match counts differ by candidate table")
    for scene in scene_ids:
        dssm_b = dec(old_by_method["CORRECTED_TRAIN_DSSM14_G12_R32"][scene]["B_Q_0_20_m"], "DSSM historical B")
        kan_b = dec(old_by_method["CORRECTED_TRAIN_KAN14_G12_R32"][scene]["B_Q_0_20_m"], "KAN historical B")
        new_b = method_scores["B_TRACEABLE"][scene]
        b_match_rows.append({
            **scene_info[scene], "scene_id": scene,
            "historical_B_Q_DSSM14_m": fmt(dssm_b), "historical_B_Q_KAN14_m": fmt(kan_b), "traceable_B_Q_m": fmt(new_b),
            "DSSM14_minus_traceable_B_m": fmt(dssm_b - new_b), "KAN14_minus_traceable_B_m": fmt(kan_b - new_b),
            "historical_B_Qs_equal": str(dssm_b == kan_b).lower(), "DSSM14_Q_exact_match": str(dssm_b == new_b).lower(),
            "KAN14_Q_exact_match": str(kan_b == new_b).lower(),
            "legacy_DSSM_B_score_source": old_by_method["CORRECTED_TRAIN_DSSM14_G12_R32"][scene]["B_score_source"],
            "legacy_DSSM_B_scorer_sha256": old_by_method["CORRECTED_TRAIN_DSSM14_G12_R32"][scene]["B_scorer_sha256"],
            "legacy_KAN_B_score_source": old_by_method["CORRECTED_TRAIN_KAN14_G12_R32"][scene]["B_score_source"],
            "legacy_KAN_B_scorer_sha256": old_by_method["CORRECTED_TRAIN_KAN14_G12_R32"][scene]["B_scorer_sha256"],
            "traceable_B_raw_sha256": audit_rows[scene]["B_metrics"]["sha256"],
        })

    groups = make_groups(scene_ids, scene_info)
    group_method_rows: list[dict[str, Any]] = []
    overall_by_method_vs_b: dict[str, dict[str, Any]] = {}
    for group_type, group_id, group_scenes in groups:
        b_values = [method_scores["B_TRACEABLE"][s] for s in group_scenes]
        for mid in METHOD_ORDER:
            values = [method_scores[mid][s] for s in group_scenes]
            deltas = [a - b for a, b in zip(values, b_values)]
            stats = win_stats(deltas)
            row = {
                "group_type": group_type, "group_id": group_id, "scene_count": len(group_scenes),
                "method_id": mid, "method_label": LABELS[mid], "mean_Q_mm": mean(values) * 1000,
                "mean_delta_vs_traceable_B_mm": mean(deltas) * 1000, "wins_vs_B": stats["wins"],
                "losses_vs_B": stats["losses"], "ties_vs_B": stats["ties"], "tie_tolerance_m": TIE_M,
                "wins_gt_1um": stats["wins_gt_1um"], "wins_gt_10um": stats["wins_gt_10um"],
            }
            group_method_rows.append(row)
            if group_type == "ALL":
                overall_by_method_vs_b[mid] = {k: fmt(v) if isinstance(v, Decimal) else v for k, v in row.items() if k not in ("group_type", "group_id", "method_label", "method_id", "tie_tolerance_m")}

    pair_rows: list[dict[str, Any]] = []
    pair_order: list[tuple[str, str]] = []
    for i, a in enumerate(METHOD_ORDER):
        for b in METHOD_ORDER[i + 1:]:
            pair_order.append((a, b))
    for scene in scene_ids:
        for a, b in pair_order:
            qa = method_scores[a][scene]
            qb = method_scores[b][scene]
            delta = qa - qb
            pair_rows.append({
                **scene_info[scene], "scene_id": scene, "method_a_id": a, "method_a_label": LABELS[a],
                "method_b_id": b, "method_b_label": LABELS[b], "Q_a_m": qa, "Q_b_m": qb,
                "delta_a_minus_b_m": delta, "delta_a_minus_b_mm": delta * 1000,
                "outcome_for_a": outcome(delta), "a_better_by_gt_1um": delta < -ONE_UM_M,
                "a_better_by_gt_10um": delta < -TEN_UM_M,
            })
    need(len(pair_rows) == 72 * 10, f"pairwise row count mismatch: {len(pair_rows)}")
    loss_rows = [r for r in pair_rows if r["outcome_for_a"] == "LOSS"]

    group_pair_rows: list[dict[str, Any]] = []
    for group_type, group_id, group_scenes in groups:
        scene_set = set(group_scenes)
        for a, b in pair_order:
            rows = [r for r in pair_rows if r["scene_id"] in scene_set and r["method_a_id"] == a and r["method_b_id"] == b]
            deltas = [r["delta_a_minus_b_m"] for r in rows]
            stats = win_stats(deltas)
            group_pair_rows.append({
                "group_type": group_type, "group_id": group_id, "scene_count": len(rows),
                "method_a_id": a, "method_a_label": LABELS[a], "method_b_id": b, "method_b_label": LABELS[b],
                "mean_Q_a_mm": mean([r["Q_a_m"] for r in rows]) * 1000,
                "mean_Q_b_mm": mean([r["Q_b_m"] for r in rows]) * 1000,
                "mean_delta_a_minus_b_mm": mean(deltas) * 1000,
                "wins_for_a": stats["wins"], "losses_for_a": stats["losses"], "ties_for_a": stats["ties"],
                "tie_tolerance_m": TIE_M, "a_better_by_gt_1um": stats["wins_gt_1um"], "a_better_by_gt_10um": stats["wins_gt_10um"],
            })
    overall_c5_vs_methods: dict[str, dict[str, Any]] = {}
    for other in METHOD_ORDER:
        if other == "C5_M110":
            continue
        a, b = ("C5_M110", other) if METHOD_ORDER.index("C5_M110") < METHOD_ORDER.index(other) else (other, "C5_M110")
        selected = [r for r in pair_rows if r["method_a_id"] == a and r["method_b_id"] == b]
        if a != "C5_M110":
            # Convert direction so all reported deltas/outcomes describe C5 relative to the other method.
            ds = [-r["delta_a_minus_b_m"] for r in selected]
            c5_q = [r["Q_b_m"] for r in selected]
            other_q = [r["Q_a_m"] for r in selected]
        else:
            ds = [r["delta_a_minus_b_m"] for r in selected]
            c5_q = [r["Q_a_m"] for r in selected]
            other_q = [r["Q_b_m"] for r in selected]
        stats = win_stats(ds)
        overall_c5_vs_methods[other] = {
            "wins": stats["wins"], "losses": stats["losses"], "ties": stats["ties"],
            "wins_gt_1um": stats["wins_gt_1um"], "wins_gt_10um": stats["wins_gt_10um"],
            "mean_delta_A_minus_B_mm": fmt(mean(ds) * 1000),
            "mean_C5_Q_mm": fmt(mean(c5_q) * 1000), "mean_other_Q_mm": fmt(mean(other_q) * 1000),
        }

    all72_c5 = overall_by_method_vs_b["C5_M110"]
    need(all72_c5["wins_vs_B"] == c5_review["wins_vs_B"], "recomputed C5 wins differ from parent summary")
    need(all72_c5["losses_vs_B"] == c5_review["losses_vs_B"], "recomputed C5 losses differ from parent summary")
    old_losses = sum(overall_by_method_vs_b[mid]["losses_vs_B"] for mid in sorted(expected_old_ids))
    need(old_losses == validation["losing_method_scene_pairs"], "recomputed historical losses differ from validation summary")

    historical_meta: list[dict[str, Any]] = []
    for mid in sorted(expected_old_ids):
        rows = old_by_method[mid]
        first = next(iter(rows.values()))
        b_identities = sorted({"|".join(legacy_b_identity_by_scene[s]) for s in scene_ids})
        historical_meta.append({
            "method_id": mid, "model_id": first["model_id"], "source_artifact": "corrected14_full72_benchmark_20261021/PAIR14_SCENE_RESULTS_VS_B.csv",
            "scene_count": len(rows), "candidate_score_source": first["candidate_score_source"],
            "candidate_scorer_sha256": first["candidate_scorer_sha256"], "candidate_raw_scan_sha256": first["candidate_raw_scan_sha256"],
            "candidate_rescore_runner_sha256": first["candidate_rescore_runner_sha256"], "per_scene_candidate_raw_sha256": "SCENE_METHOD_METRICS.csv",
            "legacy_B_reference_identities": ";".join(b_identities), "same_batch_identity_status": "NOT_ASSERTED_FOR_DISTINCT_METHODS",
        })
    for mid in ("C5_M110", "C3", "B_TRACEABLE"):
        source_name = {"C5_M110": "C5_new + C5_reuse", "C3": c5_review["data_sources"]["C3"], "B_TRACEABLE": c5_review["data_sources"]["B"]}[mid]
        historical_meta.append({
            "method_id": mid, "model_id": "", "source_artifact": source_name, "scene_count": 72,
            "candidate_score_source": "C5_DEV72_RAW_PARENT_AUDIT_V3_METRICS", "candidate_scorer_sha256": c5_review["metric_scorer_sha256"],
            "candidate_raw_scan_sha256": "", "candidate_rescore_runner_sha256": "", "per_scene_candidate_raw_sha256": "SCENE_METHOD_METRICS.csv",
            "legacy_B_reference_identities": "", "same_batch_identity_status": "SELF" if mid == "B_TRACEABLE" else "NOT_ASSERTED_FOR_DISTINCT_METHODS",
        })

    fields_scene = ["scene_id", "split", "task", "wind_group", "contract_id", "method_id", "method_label", "Q_0_20_m", "source_artifact", "model_id", "score_source", "scorer_sha256", "raw_scan_sha256", "raw_sha256", "rescore_runner_sha256", "replay_cell_status", "valid_replay_events", "external_arrays_sha256_match", "legacy_B_score_source", "legacy_B_scorer_sha256", "legacy_B_raw_scan_sha256", "legacy_B_rescore_runner_sha256", "parent_audit_sha256", "event_check_source", "event_check_sha256", "parent_audit_input_lock_sha256", "parent_audit_run_contract_sha256", "parent_audit_source_binding_sha256", "parent_audit_release_sha256", "metric_scorer_sha256", "external_identity_sha256"]
    fields_group_method = ["group_type", "group_id", "scene_count", "method_id", "method_label", "mean_Q_mm", "mean_delta_vs_traceable_B_mm", "wins_vs_B", "losses_vs_B", "ties_vs_B", "tie_tolerance_m", "wins_gt_1um", "wins_gt_10um"]
    fields_pair = ["scene_id", "split", "task", "wind_group", "method_a_id", "method_a_label", "method_b_id", "method_b_label", "Q_a_m", "Q_b_m", "delta_a_minus_b_m", "delta_a_minus_b_mm", "outcome_for_a", "a_better_by_gt_1um", "a_better_by_gt_10um"]
    fields_group_pair = ["group_type", "group_id", "scene_count", "method_a_id", "method_a_label", "method_b_id", "method_b_label", "mean_Q_a_mm", "mean_Q_b_mm", "mean_delta_a_minus_b_mm", "wins_for_a", "losses_for_a", "ties_for_a", "tie_tolerance_m", "a_better_by_gt_1um", "a_better_by_gt_10um"]
    fields_prov = ["method_id", "model_id", "source_artifact", "scene_count", "candidate_score_source", "candidate_scorer_sha256", "candidate_raw_scan_sha256", "candidate_rescore_runner_sha256", "per_scene_candidate_raw_sha256", "legacy_B_reference_identities", "same_batch_identity_status"]
    fields_b = ["scene_id", "split", "task", "wind_group", "historical_B_Q_DSSM14_m", "historical_B_Q_KAN14_m", "traceable_B_Q_m", "DSSM14_minus_traceable_B_m", "KAN14_minus_traceable_B_m", "historical_B_Qs_equal", "DSSM14_Q_exact_match", "KAN14_Q_exact_match", "legacy_DSSM_B_score_source", "legacy_DSSM_B_scorer_sha256", "legacy_KAN_B_score_source", "legacy_KAN_B_scorer_sha256", "traceable_B_raw_sha256"]

    output_blobs: dict[str, bytes] = {
        "SCENE_METHOD_METRICS.csv": dump_csv(method_scene_rows, fields_scene),
        "GROUP_METHOD_VS_B_SUMMARY.csv": dump_csv(group_method_rows, fields_group_method),
        "PAIRWISE_SCENE_COMPARISONS.csv": dump_csv(pair_rows, fields_pair),
        "GROUP_PAIRWISE_SUMMARY.csv": dump_csv(group_pair_rows, fields_group_pair),
        "ALL_LOSSES.csv": dump_csv(loss_rows, fields_pair),
        "METHOD_PROVENANCE.csv": dump_csv(historical_meta, fields_prov),
        "B_Q_MATCH_AUDIT.csv": dump_csv(b_match_rows, fields_b),
    }
    output_hashes = {name: hashlib.sha256(blob).hexdigest() for name, blob in output_blobs.items()}
    script_sha = sha256_file(Path(__file__))
    exact_b_matches = b_exact_by_old_method["CORRECTED_TRAIN_DSSM14_G12_R32"]
    b_max_abs = max(b_max_abs_by_old_method.values())
    summary = {
        "schema": "C5_ALL_METHOD_DEV72_SECONDARY_AGGREGATION_V1",
        "status": "COMPLETE_SECONDARY_SUMMARY_NO_RAW_REREAD",
        "scope": "Reaggregation of exactly the five specified audited summary files; no raw/MAT, TEST, Plant, training, rescoring, bootstrap, or threshold changes.",
        "script_sha256": script_sha,
        "inputs": input_hashes,
        "scene_count": len(scene_ids),
        "scene_set_sha256_sorted_newline_join": hashlib.sha256(("\n".join(scene_ids) + "\n").encode("utf-8")).hexdigest(),
        "method_ids": list(METHOD_ORDER),
        "method_labels": LABELS,
        "scene_set_validation": {mid: {"rows": len(method_scores[mid]), "unique_scene_ids": len(set(method_scores[mid]))} for mid in METHOD_ORDER},
        "B_Q_identity_check": {
            "comparison": "historical corrected14 B_Q_0_20_m versus C5 parent audit B_metrics.Q_0_20_m",
            "exact_scene_matches": exact_b_matches, "scene_count": len(scene_ids), "exact_mismatch_count": len(scene_ids) - exact_b_matches,
            "max_abs_decimal_diff_m": fmt(b_max_abs), "per_method_exact_matches": b_exact_by_old_method,
            "per_method_max_abs_decimal_diff_m": {k: fmt(v) for k, v in b_max_abs_by_old_method.items()},
            "mismatches_by_method": b_mismatches_by_method,
            "identity_note": "Exact Q equality does not collapse historical B cache/scorer identity into the new traceable B identity; the old per-scene source/scorer/raw-scan fields are retained.",
        },
        "corrected14_validation": {k: validation.get(k) for k in ("status", "pair14_status", "pair14_rows", "result_rows_parsed", "losing_method_scene_pairs", "test_files_read", "plant_calls_started_by_comparison", "optimizer_steps_started_by_comparison")},
        "c5_parent_review": {"status": c5_review.get("status"), "scope": c5_review.get("scope"),
            "parent_audit_input_lock_sha256": c5_review.get("input_lock_sha256"),
            "parent_audit_run_contract_sha256": c5_review.get("run_contract_sha256"),
            "parent_audit_source_binding_sha256": c5_review.get("source_binding_sha256"),
            "parent_audit_release_sha256": c5_review.get("release_sha256"),
            **{k: c5_review.get(k) for k in ("snapshot_sha256", "metric_scorer_sha256", "new_event_audit_script_sha256", "scene_count", "new_scenes_event_checked", "reused_scenes_event_audit_refs", "plant_calls_in_audit", "TEST_accessed", "training_steps", "optimizer_steps", "wins_vs_B", "losses_vs_B", "ties_vs_B_within_1e_12_m")}},
        "thresholds": {"tie_tolerance_m": fmt(TIE_M), "improvement_sensitivity_1um_m_strictly_greater": fmt(ONE_UM_M), "improvement_sensitivity_10um_m_strictly_greater": fmt(TEN_UM_M), "group_weighting": "equal weight per scene"},
        "overall_by_method_vs_B": overall_by_method_vs_b,
        "overall_C5_vs_methods": overall_c5_vs_methods,
        "group_definitions": [{"group_type": t, "group_id": i, "scene_count": len(s)} for t, i, s in groups],
        "loss_record_count_all_pairwise": len(loss_rows),
        "historical_method_ids_preserved": sorted(expected_old_ids),
        "same_batch_identity_status_by_method": {mid: ("SELF" if mid == "B_TRACEABLE" else "NOT_ASSERTED_FOR_DISTINCT_METHODS") for mid in METHOD_ORDER},
        "outputs": output_hashes,
    }
    summary_blob = dump_json(summary)
    output_hashes_with_summary = dict(output_hashes)
    output_hashes_with_summary["SUMMARY.json"] = hashlib.sha256(summary_blob).hexdigest()
    report_blob = make_report(summary, output_hashes_with_summary, script_sha)
    output_blobs["SUMMARY.json"] = summary_blob
    output_blobs["README_ZH.md"] = report_blob
    return output_blobs, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-existing", action="store_true", help="recompute in memory and byte-compare all existing outputs without writing")
    args = parser.parse_args()
    blobs, summary = build_artifacts()
    missing_or_existing = {name: (OUT / name).exists() for name in OUTPUTS}
    if args.verify_existing:
        need(all(missing_or_existing.values()), "verification requires every expected output to already exist")
        failures = []
        for name, expected in blobs.items():
            actual = (OUT / name).read_bytes()
            if actual != expected:
                failures.append(name)
        need(not failures, f"existing outputs differ from recomputation: {failures}")
        print(json.dumps({"status": "PASS_BYTE_IDENTICAL_EXISTING_OUTPUTS", "outputs": {n: sha256_file(OUT / n) for n in OUTPUTS}, "script_sha256": summary["script_sha256"]}, indent=2))
        return 0
    existing = [name for name, exists in missing_or_existing.items() if exists]
    need(not existing, f"refusing to overwrite existing outputs: {existing}; use --verify-existing")
    written: list[str] = []
    try:
        for name in OUTPUTS:
            with (OUT / name).open("xb") as f:
                f.write(blobs[name])
            written.append(name)
    except Exception:
        # Do not delete partial artifacts; preserve evidence for inspection.
        raise
    print(json.dumps({"status": summary["status"], "scene_count": summary["scene_count"], "B_Q_identity_check": summary["B_Q_identity_check"], "all72_by_method_vs_B": summary["overall_by_method_vs_B"], "C5_vs_methods": summary["overall_C5_vs_methods"], "script_sha256": summary["script_sha256"], "outputs": {n: sha256_file(OUT / n) for n in written}}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
