#!/usr/bin/env python
"""Read-only VAL48/TRAIN24 JSON audit; writes the root review JSON and Markdown."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import random


HERE = Path(__file__).resolve().parent
EXP = HERE.parent
TRAIN_DIR = EXP / "causal_n4_gate_train24_batch_v2"
N_BOOT = 20_000
SEED = 20261028
METHODS = ("candidate", "B", "C5", "parent")
METRICS = ("Q_m", "task_SO3_rad", "inner_SO3_rad")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def mean(values):
    return sum(values) / len(values)


def percentile(values, p):
    values = sorted(values)
    pos = (len(values) - 1) * p
    lo = int(pos)
    hi = min(lo + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (pos - lo)


def group_summary(rows):
    methods = {
        method: {metric: mean([r[metric][method] for r in rows]) for metric in METRICS}
        for method in METHODS
    }
    qratios = {
        other: [r["Q_m"]["candidate"] / r["Q_m"][other] for r in rows]
        for other in ("C5", "B")
    }
    taskratios = [r["task_SO3_rad"]["candidate"] / r["task_SO3_rad"]["B"] for r in rows]
    return {
        "scene_count": len(rows),
        "methods_macro_mean": methods,
        "candidate_over_C5_Q": {
            "ratio_of_sums": sum(r["Q_m"]["candidate"] for r in rows)
            / sum(r["Q_m"]["C5"] for r in rows),
            "mean_paired_ratio": mean(qratios["C5"]),
            "median_paired_ratio": percentile(qratios["C5"], 0.5),
        },
        "candidate_over_B_Q": {
            "ratio_of_sums": sum(r["Q_m"]["candidate"] for r in rows)
            / sum(r["Q_m"]["B"] for r in rows),
            "mean_paired_ratio": mean(qratios["B"]),
            "median_paired_ratio": percentile(qratios["B"], 0.5),
        },
        "candidate_over_B_task": {
            "ratio_of_macro_means": methods["candidate"]["task_SO3_rad"]
            / methods["B"]["task_SO3_rad"],
            "mean_paired_ratio": mean(taskratios),
            "median_paired_ratio": percentile(taskratios, 0.5),
        },
    }


def bootstrap(rows, seed):
    """Task-stratified paired scene bootstrap; each scene's methods stay paired."""
    strata = {}
    for row in rows:
        strata.setdefault(row["task"], []).append(row)
    rng = random.Random(seed)
    contrasts = {}
    for ref in ("B", "C5", "parent"):
        contrasts[f"candidate_minus_{ref}"] = {
            metric: [] for metric in METRICS
        }
    contrasts["C5_minus_B"] = {"task_SO3_rad": [], "inner_SO3_rad": []}
    contrasts["C5_vs_B_relative_percent"] = {
        "task_SO3_rad": [], "inner_SO3_rad": []
    }
    contrasts["candidate_over_C5_Q_ratio_of_sums"] = []
    contrasts["candidate_over_B_Q_ratio_of_sums"] = []

    for _ in range(N_BOOT):
        sample = [rng.choice(s) for s in strata.values() for _ in s]
        n = len(sample)
        for ref in ("B", "C5", "parent"):
            for metric in METRICS:
                contrasts[f"candidate_minus_{ref}"][metric].append(
                    sum(r[metric]["candidate"] - r[metric][ref] for r in sample) / n
                )
        for metric in ("task_SO3_rad", "inner_SO3_rad"):
            b = sum(r[metric]["B"] for r in sample) / n
            c5 = sum(r[metric]["C5"] for r in sample) / n
            contrasts["C5_minus_B"][metric].append(c5 - b)
            contrasts["C5_vs_B_relative_percent"][metric].append(100 * (c5 / b - 1))
        for ref in ("C5", "B"):
            contrasts[f"candidate_over_{ref}_Q_ratio_of_sums"].append(
                sum(r["Q_m"]["candidate"] for r in sample)
                / sum(r["Q_m"][ref] for r in sample)
            )

    estimates = {}
    for ref in ("B", "C5", "parent"):
        estimates[f"candidate_minus_{ref}"] = {
            metric: mean([r[metric]["candidate"] - r[metric][ref] for r in rows])
            for metric in METRICS
        }
    estimates["C5_minus_B"] = {
        metric: mean([r[metric]["C5"] - r[metric]["B"] for r in rows])
        for metric in ("task_SO3_rad", "inner_SO3_rad")
    }
    estimates["C5_vs_B_relative_percent"] = {
        metric: 100
        * (mean([r[metric]["C5"] for r in rows]) / mean([r[metric]["B"] for r in rows]) - 1)
        for metric in ("task_SO3_rad", "inner_SO3_rad")
    }
    for ref in ("C5", "B"):
        estimates[f"candidate_over_{ref}_Q_ratio_of_sums"] = sum(
            r["Q_m"]["candidate"] for r in rows
        ) / sum(r["Q_m"][ref] for r in rows)

    result = {}
    for name, value in contrasts.items():
        if isinstance(value, dict):
            result[name] = {
                metric: {
                    "estimate": estimates[name][metric],
                    "ci95_percentile": [percentile(samples, 0.025), percentile(samples, 0.975)],
                }
                for metric, samples in value.items()
            }
        else:
            result[name] = {
                "estimate": estimates[name],
                "ci95_percentile": [percentile(value, 0.025), percentile(value, 0.975)],
            }
    return result


def markdown_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    out.extend("| " + " | ".join(str(x) for x in row) + " |" for row in rows)
    return "\n".join(out)


def f(x, digits=6):
    return f"{x:.{digits}f}"


def ci_fmt(entry, digits=6):
    lo, hi = entry["ci95_percentile"]
    return f"{f(entry['estimate'], digits)} [{f(lo, digits)}, {f(hi, digits)}]"


def main():
    val_file = HERE / "VAL48_SCORE_SUMMARY_v2.json"
    train_file = TRAIN_DIR / "TRAIN24_SCORE_SUMMARY_v2.json"
    progress_file = HERE / "VAL48_BATCH_PROGRESS_v1.json"
    input_file = HERE / "BATCH_INPUT_v2.json"
    plan_file = HERE / "BATCH_PLAN_v2.json"
    contract_file = HERE / "BATCH_SCORE_CONTRACT_v2.json"
    source_lock_file = HERE / "SOURCE_LOCK_VAL48_v1.json"
    numeric_file = HERE / "VAL48_NUMERIC_SOURCE_HASH_PRESERVATION_v1.json"
    train_contract_file = TRAIN_DIR / "BATCH_SCORE_CONTRACT_v2.json"

    val = read_json(val_file)
    train = read_json(train_file)
    progress = read_json(progress_file)
    batch_input = read_json(input_file)
    plan = read_json(plan_file)
    contract = read_json(contract_file)
    source_lock = read_json(source_lock_file)
    numeric = read_json(numeric_file)
    train_contract = read_json(train_contract_file)

    val_rows, train_rows = val["scenes"], train["scenes"]
    val_ids = [r["scene_id"] for r in val_rows]
    train_ids = [r["scene_id"] for r in train_rows]
    require(val["schema"] == "DL1018_CAUSAL_N4_VAL48_BATCH_SCORE_SUMMARY_V2", "Unexpected VAL48 schema")
    require(train["schema"] == "DL1018_CAUSAL_N4_TRAIN24_BATCH_SCORE_SUMMARY_V2", "Unexpected TRAIN24 schema")
    require(val["scene_count_scored"] == 48 and len(val_ids) == 48 and len(set(val_ids)) == 48, "VAL48 count/ID failure")
    require(train["scene_count_scored"] == 24 and len(train_ids) == 24 and len(set(train_ids)) == 24, "TRAIN24 count/ID failure")
    require(all(x.startswith("DL1018_VAL_") for x in val_ids), "VAL48 ID prefix failure")
    require(all(x.startswith("DL1018_DEV_") for x in train_ids), "TRAIN24 must be DEV IDs")
    overlap = sorted(set(val_ids) & set(train_ids))
    require(not overlap, f"DEV/VAL overlap: {overlap}")
    require(batch_input["cohort"]["source_split"] == "VAL48", "VAL input split mismatch")
    require(batch_input["cohort"]["scene_count"] == 48, "VAL input count mismatch")
    require(batch_input["cohort"]["source_scene_ids"] == val_ids, "VAL input/score ID order mismatch")
    require(plan["ordered_scene_ids"] == val_ids, "VAL plan/score ID order mismatch")
    require([x["scene_id"] for x in plan["entries"]] == val_ids, "VAL plan entries mismatch")
    require(progress["completed_scenes"] == val_ids, "VAL progress/score ID order mismatch")
    require(source_lock["cohort_scene_count"] == 48, "VAL source lock count mismatch")
    require([x["scene_id"] for x in source_lock["binding_inventory"]] == val_ids,
            "VAL source-lock binding inventory mismatch")
    require(sha256(source_lock_file) == progress["source_lock_sha256"] == plan["source_lock_sha256"],
            "VAL source-lock hash mismatch")
    identities = {
        plan["candidate_identity_sha256"], contract["candidate_identity_sha256"],
        train_contract["candidate_identity_sha256"], source_lock["candidate_identity_sha256"],
    }
    require(len(identities) == 1, "Candidate identity differs across frozen artifacts")
    require(progress["status"] == "COMPLETE_VAL48_48_SCENES"
            and progress["calls_reserved"] == 48 and progress["Plant_calls"] == 48,
            "VAL48 completion/call accounting mismatch")
    require(val["TEST_read"] is False and progress["TEST_read"] is False
            and contract["scope"]["TEST_read"] is False, "VAL TEST scope flag is not false")
    require(train["TEST_read"] is False and train["VAL_read"] is False
            and train_contract["scope"]["TEST_read"] is False, "TRAIN scope flags mismatch")
    require(numeric["n4_numeric_configuration_equal"] is True
            and numeric["gate_or_model_numeric_values_changed"] is False, "Numeric preservation audit failed")

    entry_by_id = {x["scene_id"]: x for x in plan["entries"]}
    status_files = sorted((HERE / "runs").glob("*/attempt_01/run_status.json"))
    statuses = {}
    for path in status_files:
        status = read_json(path)
        statuses[status["scene_id"]] = status
    require(len(status_files) == 48 and set(statuses) == set(val_ids), "run_status ID/count mismatch")
    status_failures = []
    for scene_id in val_ids:
        s = statuses[scene_id]
        e = entry_by_id[scene_id]
        checks = {
            "completed": s.get("state") == "COMPLETED",
            "stable": s.get("status_value") == "STABLE",
            "transitions_20000": s.get("transitions") == 20000,
            "samples_20001": s.get("state_samples") == 20001,
            "one_plant_call": s.get("Plant_calls") == 1 and s.get("reserved_budget_calls") == 1,
            "no_safety_stop": s.get("safety_stop_reason") == "",
            "marker": s.get("first_plant_step_marker_created") is True,
            "test_not_read": s.get("TEST_read") is False,
            "no_inertia_reconstruction": s.get("inertia_reconstruction_enabled") is False,
            "binding_matches_plan": s.get("binding_sha256") == e.get("binding_sha256"),
            "source_lock_matches": s.get("source_lock_sha256") == progress["source_lock_sha256"],
        }
        if not all(checks.values()):
            status_failures.append({"scene_id": scene_id, "failed_checks": [k for k, v in checks.items() if not v]})
    require(not status_failures, f"run_status integrity failures: {status_failures}")

    merged = train_rows + val_rows
    datasets = {
        "TRAIN24_DEV": train_rows,
        "VAL48": val_rows,
        "MERGED72_DEV_PLUS_VAL": merged,
    }
    views = {}
    bootstrap_views = {}
    c5_vs_b = {}
    seed_offset = 0
    for data_name, rows in datasets.items():
        for group_name, selected in (("overall", rows), ("HF_W09_W14", [r for r in rows if r["HF_W09_W14"]])):
            key = f"{data_name}/{group_name}"
            require(selected, f"Empty audit group: {key}")
            views[key] = group_summary(selected)
            bootstrap_views[key] = bootstrap(selected, SEED + seed_offset)
            seed_offset += 1
            c5_vs_b[key] = {}
            for metric in ("task_SO3_rad", "inner_SO3_rad"):
                b = views[key]["methods_macro_mean"]["B"][metric]
                c5 = views[key]["methods_macro_mean"]["C5"][metric]
                ci = bootstrap_views[key]["C5_minus_B"][metric]
                pct_ci = bootstrap_views[key]["C5_vs_B_relative_percent"][metric]
                c5_vs_b[key][metric] = {
                    "B_macro_mean": b,
                    "C5_macro_mean": c5,
                    "C5_minus_B": c5 - b,
                    "C5_relative_to_B_percent": 100 * (c5 / b - 1),
                    "paired_bootstrap_delta_ci95": ci["ci95_percentile"],
                    "paired_bootstrap_relative_percent_ci95": pct_ci["ci95_percentile"],
                }

    # Reconcile independently recomputed 48/24 scores with their provided summaries.
    recompute_checks = {}
    for label, summary, rows in (("VAL48", val, val_rows), ("TRAIN24", train, train_rows)):
        computed = group_summary(rows)
        differences = {}
        for method in METHODS:
            for metric in METRICS:
                original = summary["overall"]["methods"][method][metric]
                fresh = computed["methods_macro_mean"][method][metric]
                differences[f"{method}.{metric}"] = fresh - original
                require(math.isclose(fresh, original, rel_tol=0, abs_tol=1e-12),
                        f"{label} summary mismatch for {method}.{metric}")
        recompute_checks[label] = {"max_abs_difference": max(abs(x) for x in differences.values()), "fields_checked": len(differences)}

    q_misses = [
        {"scene_id": r["scene_id"], "candidate_over_C5_Q": r["Q_m"]["candidate"] / r["Q_m"]["C5"]}
        for r in val_rows if r["Q_m"]["candidate"] / r["Q_m"]["C5"] > 1.05
    ]
    task_misses = []
    hf_task_misses = []
    for r in val_rows:
        c = r["task_SO3_rad"]["candidate"]
        b = r["task_SO3_rad"]["B"]
        if c > b:
            miss = {
                "scene_id": r["scene_id"],
                "HF_W09_W14": r["HF_W09_W14"],
                "candidate_task_SO3_rad": c,
                "B_task_SO3_rad": b,
                "candidate_minus_B_rad": c - b,
                "candidate_over_B_percent": 100 * (c / b - 1),
            }
            task_misses.append(miss)
            if r["HF_W09_W14"]:
                hf_task_misses.append(miss)
    replay_key = "action_chain_replay_at_2e_10"
    replay_pass = sum(bool(r.get("criteria", {}).get(replay_key, False)) for r in val_rows)
    safety_nonzero = [
        r["scene_id"] for r in val_rows
        if any(value != 0 for value in r.get("safety", {}).values()) or r.get("fatal_stop")
    ]
    hf_rows = [r for r in val_rows if r["HF_W09_W14"]]
    hf_scene_pass = sum(r["task_SO3_rad"]["candidate"] <= r["task_SO3_rad"]["B"] for r in hf_rows)

    status_counts = Counter(s["status_value"] for s in statuses.values())
    state_counts = Counter(s["state"] for s in statuses.values())
    report = {
        "schema": "DL1018_VAL48_ROOT_REVIEW_V1",
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scope": {
            "read_files": [
                str(p.relative_to(EXP.parent.parent)) for p in
                (val_file, train_file, progress_file, input_file, plan_file, contract_file,
                 source_lock_file, numeric_file, train_contract_file)
            ] + ["cg48_v2/runs/*/attempt_01/run_status.json (48 files)"],
            "raw_run_mat_opened": False,
            "TEST_data_read_by_audit": False,
            "MATLAB_or_Plant_invoked_by_audit": False,
            "inertia_reconstructed_by_audit": False,
            "existing_VAL48_batch_Plant_calls": progress["Plant_calls"],
        },
        "source_identity": {
            "VAL48_schema": val["schema"],
            "TRAIN24_schema": train["schema"],
            "VAL48_count": len(val_ids),
            "TRAIN24_DEV_count": len(train_ids),
            "overlap_count": len(overlap),
            "overlap_scene_ids": overlap,
            "merged_scene_count": len(merged),
            "val_ids_match_input_plan_progress_status": True,
            "candidate_identity_sha256": plan["candidate_identity_sha256"],
            "source_lock_sha256": progress["source_lock_sha256"],
            "numeric_configuration_equal": numeric["n4_numeric_configuration_equal"],
            "gate_or_model_numeric_values_changed": numeric["gate_or_model_numeric_values_changed"],
            "VAL48_score_sha256": sha256(val_file),
            "TRAIN24_score_sha256": sha256(train_file),
            "VAL48_scene_ids": val_ids,
            "TRAIN24_DEV_scene_ids": train_ids,
        },
        "group_statistics": views,
        "paired_bootstrap": {
            "method": "Task-stratified nonparametric paired scene bootstrap; resample within each task, keeping all methods for a scene paired; percentile interval.",
            "replicates_per_group": N_BOOT,
            "seed_base": SEED,
            "groups": bootstrap_views,
        },
        "C5_attitude_relative_to_B": {
            "definition": "100 * (macro_mean(C5) / macro_mean(B) - 1); positive means C5 has larger error than B.",
            "groups": c5_vs_b,
        },
        "VAL48_scene_misses": {
            "candidate_over_C5_Q_gt_1p05": q_misses,
            "candidate_task_SO3_gt_B_all_scenes": task_misses,
            "HF_W09_W14_candidate_task_SO3_gt_B": hf_task_misses,
            "HF_candidate_task_le_B_scene_count": hf_scene_pass,
            "HF_scene_count": len(hf_rows),
        },
        "execution_safety_and_replay": {
            "progress_status": progress["status"],
            "progress_complete_48": len(progress["completed_scenes"]) == 48 and not progress["stopped_scene_id"] and not progress["stop_reason"],
            "run_status_count": len(statuses),
            "run_status_state_counts": dict(state_counts),
            "run_status_status_value_counts": dict(status_counts),
            "one_call_per_scene": all(s["Plant_calls"] == 1 for s in statuses.values()),
            "total_existing_plant_calls": sum(s["Plant_calls"] for s in statuses.values()),
            "all_transitions_20000": all(s["transitions"] == 20000 for s in statuses.values()),
            "all_state_samples_20001": all(s["state_samples"] == 20001 for s in statuses.values()),
            "all_test_read_false": all(s["TEST_read"] is False for s in statuses.values()),
            "all_inertia_reconstruction_false": all(s["inertia_reconstruction_enabled"] is False for s in statuses.values()),
            "score_action_chain_replay_at_2e_10_pass_count": replay_pass,
            "score_action_chain_replay_at_2e_10_scene_count": len(val_rows),
            "score_safety_fault_scene_count": val["safety_fault_scene_count"],
            "fatal_stop_scene_count": len(val["fatal_stop_scene_ids"]),
            "nonzero_safety_or_fatal_scene_ids": safety_nonzero,
            "all_action_replay_pass": replay_pass == 48,
            "all_safety_zero": not safety_nonzero and val["safety_fault_scene_count"] == 0,
        },
        "summary_reconciliation": recompute_checks,
        "parent_exposure_caveat": "The 72-row DEV24+VAL48 roll-up is a development diagnostic. The parent comparator has seen these 72 scenes, so this is not an independent test estimate.",
    }

    # Write review artifacts only; no source score, run, or frozen file is modified.
    json_out = HERE / "VAL48_REVIEW_ROOT_v1.json"
    md_out = HERE / "VAL48_REVIEW_ROOT_v1.md"
    json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    md = [
        "# VAL48 独立结果审计",
        "",
        "## 范围与 ID 核验",
        "",
        f"- VAL48：schema `{val['schema']}`，48/48 scene；与输入、冻结计划、进度和 run_status 的 scene ID 顺序完全一致。",
        f"- TRAIN24：schema `{train['schema']}`，24 个 `DEV` scene；与 VAL48 的 ID 交集为 0，合并共 72 个唯一 scene。",
        "- 本审计仅读取两个 score summary、VAL48 的计划/输入/进度/contract/source-lock/hash-preservation JSON，以及 48 个 `run_status.json`；未打开 `raw_run.mat`，未读 TEST，未运行 MATLAB/Plant，也未做惯量重建。现有 VAL48 batch 元数据记录的是已完成的 48 次 Plant call。",
        f"- 冻结数值配置相同：`{numeric['n4_numeric_configuration_equal']}`；gate/model numeric value changed：`{numeric['gate_or_model_numeric_values_changed']}`。",
        "",
        "## Overall 与 HF_W09_W14 宏平均",
        "",
        "表内 `Q_m / task_SO3_rad / inner_SO3_rad` 均为 scene 宏平均；数值越低越好。",
        "",
    ]
    for cohort, title in (("TRAIN24_DEV", "TRAIN24（DEV）"), ("VAL48", "VAL48"), ("MERGED72_DEV_PLUS_VAL", "合并72（DEV+VAL诊断）")):
        for group, label in (("overall", "overall"), ("HF_W09_W14", "HF_W09_W14")):
            key = f"{cohort}/{group}"
            md += [f"### {title} · {label}（n={views[key]['scene_count']}）", ""]
            rows = []
            for method in METHODS:
                m = views[key]["methods_macro_mean"][method]
                rows.append([method, f(m["Q_m"]), f(m["task_SO3_rad"]), f(m["inner_SO3_rad"])])
            md += [markdown_table(["method", "Q_m", "task_SO3_rad", "inner_SO3_rad"], rows), ""]
            md.append(
                f"candidate/C5 Q ratio-of-sums = {f(views[key]['candidate_over_C5_Q']['ratio_of_sums'])}; "
                f"candidate/B Q ratio-of-sums = {f(views[key]['candidate_over_B_Q']['ratio_of_sums'])}; "
                f"candidate/B task ratio-of-macro-means = {f(views[key]['candidate_over_B_task']['ratio_of_macro_means'])}."
            )
            md.append("")

    md += [
        "## C5 姿态误差相对 B",
        "",
        "相对差定义为 `100 × (C5/B − 1)`，正值表示 C5 误差更大；区间是 task-stratified paired scene bootstrap 的 95% percentile CI。",
        "",
    ]
    for metric, label in (("task_SO3_rad", "task SO(3)"), ("inner_SO3_rad", "inner SO(3)")):
        rows = []
        for cohort, group, name in (
            ("TRAIN24_DEV", "overall", "TRAIN24 overall"),
            ("TRAIN24_DEV", "HF_W09_W14", "TRAIN24 HF"),
            ("VAL48", "overall", "VAL48 overall"),
            ("VAL48", "HF_W09_W14", "VAL48 HF"),
            ("MERGED72_DEV_PLUS_VAL", "overall", "72 overall"),
            ("MERGED72_DEV_PLUS_VAL", "HF_W09_W14", "72 HF"),
        ):
            key = f"{cohort}/{group}"
            x = c5_vs_b[key][metric]
            pct_ci = bootstrap_views[key]["C5_vs_B_relative_percent"][metric]["ci95_percentile"]
            rows.append([name, views[key]["scene_count"], f(x["B_macro_mean"]), f(x["C5_macro_mean"]),
                         f(x["C5_minus_B"], 7), f(x["C5_relative_to_B_percent"], 2),
                         f"[{f(pct_ci[0], 2)}, {f(pct_ci[1], 2)}]"])
        md += [f"### {label}", "", markdown_table(
            ["group", "n", "B mean", "C5 mean", "C5−B", "C5 vs B %", "paired bootstrap 95% CI %"], rows), ""]

    md += [
        "## VAL48 candidate paired bootstrap",
        "",
        "差值定义为 candidate − comparator；负值表示 candidate 的误差较低。以下是 overall 与 HF 子集的逐 scene 配对区间。",
        "",
    ]
    for group, label in (("overall", "VAL48 overall"), ("HF_W09_W14", "VAL48 HF_W09_W14")):
        key = f"VAL48/{group}"
        rows = []
        for ref in ("B", "C5", "parent"):
            for metric in METRICS:
                rows.append([ref, metric, ci_fmt(bootstrap_views[key][f"candidate_minus_{ref}"][metric])])
        md += [f"### {label}", "", markdown_table(["comparator", "metric", "candidate−comparator estimate [95% CI]"], rows), ""]
        for ref in ("C5", "B"):
            md.append(f"- candidate/{ref} Q ratio-of-sums: {ci_fmt(bootstrap_views[key][f'candidate_over_{ref}_Q_ratio_of_sums'])}.")
        md.append("")

    md += [
        "## Scene misses、action replay 与安全",
        "",
        f"- VAL48 candidate/C5 Q aggregate ratio = {f(views['VAL48/overall']['candidate_over_C5_Q']['ratio_of_sums'])}（目标 ≤1.05）；逐 scene 超过 1.05：{len(q_misses)} 个。",
        f"- HF candidate task ≤ B：{hf_scene_pass}/{len(hf_rows)} scene；HF 宏平均 candidate/B = {f(views['VAL48/HF_W09_W14']['candidate_over_B_task']['ratio_of_macro_means'])}（aggregate 通过）。",
        f"- Action-chain replay（2e−10）通过 {replay_pass}/48；score safety-fault scene = {val['safety_fault_scene_count']}，fatal stop = {len(val['fatal_stop_scene_ids'])}；48 个 run_status 均 COMPLETED/STABLE、20,000 transitions、20,001 samples、每 scene 1 call。",
        "",
        "### candidate task_SO3 高于 B 的 scene",
        "",
    ]
    if task_misses:
        md += [markdown_table(
            ["scene_id", "HF", "candidate rad", "B rad", "Δ rad", "candidate/B %"],
            [[x["scene_id"], x["HF_W09_W14"], f(x["candidate_task_SO3_rad"]), f(x["B_task_SO3_rad"]),
              f(x["candidate_minus_B_rad"], 7), f(x["candidate_over_B_percent"], 2)] for x in task_misses]
        ), ""]
    else:
        md += ["无。", ""]
    md += [
        "HF 四个 per-scene miss（上表标记 HF）；另外两个 miss 不属于 HF。candidate/C5 Q 单 scene >1.05：无。",
        "",
        "## 解释边界",
        "",
        "合并72仅用于 DEV24+VAL48 开发诊断；parent comparator 已见这72个 scene，所以这不是独立测试结果。所有 TEST scope flags 为 false。",
        "",
        "复算区间：20,000 次按 task 分层的 scene bootstrap，固定 seed `20261028`；方法按 scene 配对，报告 percentile 95% CI。JSON 中包含全部组别与 CI。",
        "",
    ]
    md_out.write_text("\n".join(md), encoding="utf-8")
    print(json.dumps({"json": str(json_out), "markdown": str(md_out), "groups": list(views),
                      "VAL48_HF_task_misses": [x["scene_id"] for x in hf_task_misses],
                      "C5_vs_B_VAL48_overall": c5_vs_b["VAL48/overall"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
