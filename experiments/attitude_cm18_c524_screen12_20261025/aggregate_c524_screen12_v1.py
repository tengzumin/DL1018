"""Validate and summarize the frozen C5_24 12-scene closed-loop screen."""
from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EXP = ROOT / "experiments/attitude_cm18_c524_screen12_20261025"
REPORT = ROOT / "reports/attitude_cm18_c524_screen12_20261025"
BINDING = EXP / "C524_SCREEN12_BINDING_v1.json"
AUDIT_DIR = REPORT / "scene_audits"
OUTPUT_JSON = REPORT / "C524_SCREEN12_AGGREGATE_v1.json"
OUTPUT_CSV = REPORT / "C524_SCREEN12_PAIRED_SCENES_v1.csv"
OUTPUT_MD = REPORT / "C524_SCREEN12_RESULT_v1.md"
TOL = 1e-12


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def group(scene_id: str) -> str:
    match = re.search(r"_W(\d+)$", scene_id)
    if not match:
        raise ValueError(f"scene has no terminal wind ID: {scene_id}")
    wind = int(match.group(1))
    if wind == 15:
        return "W15_NO_WIND"
    if 9 <= wind <= 14:
        return "W09_W14_HIGH_FREQUENCY"
    return "OTHER_WIND"


def paired_counts(rows: list[dict], candidate: str, reference: str, metric: str) -> dict:
    wins = ties = losses = 0
    for row in rows:
        delta = row[candidate][metric] - row[reference][metric]
        if delta < -TOL:
            wins += 1
        elif delta > TOL:
            losses += 1
        else:
            ties += 1
    return {"wins": wins, "ties": ties, "losses": losses, "tolerance": TOL}


def method_summary(rows: list[dict], method: str) -> dict:
    return {
        "scene_count": len(rows),
        "position_Q_macro_mean_m": sum(r[method]["position_Q_rmse_m"] for r in rows) / len(rows),
        "position_peak_macro_mean_m": sum(r[method]["position_peak_m"] for r in rows) / len(rows),
        "SO3_RMSE_macro_mean_rad": sum(r[method]["SO3_rmse_rad"] for r in rows) / len(rows),
        "SO3_peak_macro_mean_rad": sum(r[method]["SO3_peak_rad"] for r in rows) / len(rows),
    }


def main() -> None:
    if any(path.exists() for path in (OUTPUT_JSON, OUTPUT_CSV, OUTPUT_MD)):
        raise FileExistsError("aggregate outputs already exist; refusing overwrite")
    binding = read(BINDING)
    binding_sha = sha(BINDING)
    expected_ids = binding["scene_ids"]
    rows = []
    for scene_id in expected_ids:
        audit_path = AUDIT_DIR / f"{scene_id}_C524_AUDIT_v1.json"
        audit = read(audit_path)
        bound = next(row for row in binding["scene_rows"] if row["scene_id"] == scene_id)
        raw_path = Path(audit["candidate_raw_path"])
        c5_path = Path(audit["c5_rbf_raw_path"])
        b_path = Path(audit["original_b_raw_path"])
        if (audit.get("status") != "PASS" or audit.get("binding_sha256") != binding_sha
                or audit["candidate_raw_sha256"] != sha(raw_path)
                or audit["c5_rbf_raw_sha256"] != bound["c5_raw_sha256"]
                or audit["original_b_raw_sha256"] != bound["b_raw_sha256"]
                or str(c5_path) != bound["c5_raw_path"] or str(b_path) != bound["b_raw_path"]):
            raise ValueError(f"audit/binding/raw identity mismatch for {scene_id}")
        status = read(EXP / "runs" / scene_id / "attempt_01" / "run_status.json")
        if (status.get("status") != "RUN_COMPLETE_PENDING_AUDIT" or status.get("plant_calls") != 1
                or status.get("TEST_accessed") is not False):
            raise ValueError(f"run status or scope mismatch for {scene_id}")
        row = {
            "scene_id": scene_id,
            "group": group(scene_id),
            "candidate": audit["candidate_C5_position_C5_24_attitude"],
            "c5_rbf": audit["matched_C5_position_original_RBF"],
            "original_b": audit["original_B_overall_reference"],
            "candidate_raw_sha256": audit["candidate_raw_sha256"],
            "c5_raw_sha256": audit["c5_rbf_raw_sha256"],
            "b_raw_sha256": audit["original_b_raw_sha256"],
            "b_scene_id_raw": audit["original_b_scene_id_raw"],
            "b_scene_id_alias": audit["original_b_scene_id_alias"],
        }
        rows.append(row)

    all_run_files = [p for p in (EXP / "runs").rglob("*") if p.is_file()]
    output_bytes = sum(p.stat().st_size for p in all_run_files)
    if output_bytes > 1024**3:
        raise ValueError(f"screen outputs exceed 1 GiB: {output_bytes} bytes")

    methods = {"candidate": "candidate", "matched_C5_RBF": "c5_rbf", "original_B": "original_b"}
    groups = {"ALL_12": rows}
    for label in ("W09_W14_HIGH_FREQUENCY", "W15_NO_WIND", "OTHER_WIND"):
        groups[label] = [row for row in rows if row["group"] == label]
    summary = {}
    for label, selected in groups.items():
        summary[label] = {
            "methods": {name: method_summary(selected, key) for name, key in methods.items()},
            "position_Q_vs_matched_C5_RBF": paired_counts(selected, "candidate", "c5_rbf", "position_Q_rmse_m"),
            "position_Q_vs_original_B": paired_counts(selected, "candidate", "original_b", "position_Q_rmse_m"),
            "SO3_RMSE_vs_matched_C5_RBF": paired_counts(selected, "candidate", "c5_rbf", "SO3_rmse_rad"),
            "SO3_RMSE_vs_original_B": paired_counts(selected, "candidate", "original_b", "SO3_rmse_rad"),
            "candidate_minus_C5_RBF_Q_mean_m": (
                sum(r["candidate"]["position_Q_rmse_m"] - r["c5_rbf"]["position_Q_rmse_m"] for r in selected) / len(selected)
                if selected else None
            ),
            "candidate_minus_original_B_Q_mean_m": (
                sum(r["candidate"]["position_Q_rmse_m"] - r["original_b"]["position_Q_rmse_m"] for r in selected) / len(selected)
                if selected else None
            ),
            "candidate_minus_C5_RBF_SO3_mean_rad": (
                sum(r["candidate"]["SO3_rmse_rad"] - r["c5_rbf"]["SO3_rmse_rad"] for r in selected) / len(selected)
                if selected else None
            ),
        }

    csv_rows = []
    for row in rows:
        out = {"scene_id": row["scene_id"], "group": row["group"]}
        for label, method in (("C5_24", "candidate"), ("C5_RBF", "c5_rbf"), ("B", "original_b")):
            for metric in ("position_Q_rmse_m", "position_peak_m", "SO3_rmse_rad", "SO3_peak_rad",
                           "peak_body_rate_rad_s", "motor_saturated_samples", "generalized_clipped_samples",
                           "tilt_limited_samples", "controller_call_time_median_s", "controller_call_time_p95_s"):
                out[f"{label}_{metric}"] = row[method].get(metric)
        out["C5_24_minus_C5_RBF_Q_m"] = row["candidate"]["position_Q_rmse_m"] - row["c5_rbf"]["position_Q_rmse_m"]
        out["C5_24_minus_B_Q_m"] = row["candidate"]["position_Q_rmse_m"] - row["original_b"]["position_Q_rmse_m"]
        out["B_scene_id_raw"] = row["b_scene_id_raw"]
        out["B_scene_id_alias"] = row["b_scene_id_alias"]
        out["C5_24_raw_sha256"] = row["candidate_raw_sha256"]
        csv_rows.append(out)

    result = {
        "schema": "CM18_C5_24_SCREEN12_AGGREGATE_V1",
        "status": "PASS_ALL_12_AUDITED",
        "binding_sha256": binding_sha,
        "scene_count": len(rows),
        "plant_calls": len(rows),
        "training_steps": 0,
        "optimizer_steps": 0,
        "TEST_accessed": False,
        "output_bytes": output_bytes,
        "output_cap_bytes": 1024**3,
        "tie_tolerance_m": TOL,
        "performance_is_screen_only": True,
        "groups": summary,
        "scenes": [{
            "scene_id": row["scene_id"], "group": row["group"],
            "C5_24_Q_m": row["candidate"]["position_Q_rmse_m"],
            "C5_RBF_Q_m": row["c5_rbf"]["position_Q_rmse_m"],
            "B_Q_m": row["original_b"]["position_Q_rmse_m"],
            "C5_24_SO3_RMSE_rad": row["candidate"]["SO3_rmse_rad"],
            "C5_RBF_SO3_RMSE_rad": row["c5_rbf"]["SO3_rmse_rad"],
            "B_SO3_RMSE_rad": row["original_b"]["SO3_rmse_rad"],
            "C5_24_raw_sha256": row["candidate_raw_sha256"],
        } for row in rows],
    }
    OUTPUT_JSON.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(csv_rows[0]))
        writer.writeheader()
        writer.writerows(csv_rows)

    all_metrics = summary["ALL_12"]
    hf = summary["W09_W14_HIGH_FREQUENCY"]
    w15 = summary["W15_NO_WIND"]
    text = [
        "# C5_24 姿态环替代：固定 12 场闭环筛查结果",
        "",
        "12 场均完成 20 s 闭环仿真并通过逐场日志审计。该结果是机制筛查，不是 DEV72/TEST48 论文验收。",
        "候选为固定 C5 位置环 + C5_24 CM18 姿态环；匹配对照为相同 C5 位置环 + 原姿态 RBF。原 B 作为总体参考，其位置控制栈不同，不能用于单独归因姿态环。",
        "",
        f"- 总位置 Q：C5_24 {all_metrics['methods']['candidate']['position_Q_macro_mean_m']:.9g} m；C5+RBF {all_metrics['methods']['matched_C5_RBF']['position_Q_macro_mean_m']:.9g} m；原 B {all_metrics['methods']['original_B']['position_Q_macro_mean_m']:.9g} m。",
        f"- 逐场位置 Q 胜/平/负（1e-12 m 容差）：对 C5+RBF {all_metrics['position_Q_vs_matched_C5_RBF']['wins']}/{all_metrics['position_Q_vs_matched_C5_RBF']['ties']}/{all_metrics['position_Q_vs_matched_C5_RBF']['losses']}；对原 B {all_metrics['position_Q_vs_original_B']['wins']}/{all_metrics['position_Q_vs_original_B']['ties']}/{all_metrics['position_Q_vs_original_B']['losses']}。",
        f"- 高频 W09-W14（{hf['methods']['candidate']['scene_count']} 场）宏平均位置 Q：C5_24 {hf['methods']['candidate']['position_Q_macro_mean_m']:.9g} m；C5+RBF {hf['methods']['matched_C5_RBF']['position_Q_macro_mean_m']:.9g} m；原 B {hf['methods']['original_B']['position_Q_macro_mean_m']:.9g} m。",
        f"- 无风 W15（{w15['methods']['candidate']['scene_count']} 场）宏平均位置 Q：C5_24 {w15['methods']['candidate']['position_Q_macro_mean_m']:.9g} m；C5+RBF {w15['methods']['matched_C5_RBF']['position_Q_macro_mean_m']:.9g} m；原 B {w15['methods']['original_B']['position_Q_macro_mean_m']:.9g} m。",
        f"- 总 SO(3) 姿态误差宏平均：C5_24 {all_metrics['methods']['candidate']['SO3_RMSE_macro_mean_rad']:.9g} rad；C5+RBF {all_metrics['methods']['matched_C5_RBF']['SO3_RMSE_macro_mean_rad']:.9g} rad；原 B {all_metrics['methods']['original_B']['SO3_RMSE_macro_mean_rad']:.9g} rad。",
        f"- 高频 SO(3) 胜/平/负（相对 C5+RBF）：{hf['SO3_RMSE_vs_matched_C5_RBF']['wins']}/{hf['SO3_RMSE_vs_matched_C5_RBF']['ties']}/{hf['SO3_RMSE_vs_matched_C5_RBF']['losses']}；W15：{w15['SO3_RMSE_vs_matched_C5_RBF']['wins']}/{w15['SO3_RMSE_vs_matched_C5_RBF']['ties']}/{w15['SO3_RMSE_vs_matched_C5_RBF']['losses']}。",
        f"- 实际闭环产物 {output_bytes / 1024**2:.1f} MiB；无训练、无 TEST，未超过 1 GiB 上限。",
        "",
        "逐场数据见 `C524_SCREEN12_PAIRED_SCENES_v1.csv`，身份和分组汇总见 `C524_SCREEN12_AGGREGATE_v1.json`。旧 B 的 `_ACC_FIX_V1` 场景别名仅用于载荷身份核对，具体场次在 CSV 中标出。",
    ]
    OUTPUT_MD.write_text("\n".join(text) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "output_mib": round(output_bytes / 1024**2, 2),
                      "all_12": all_metrics, "high_frequency": hf, "w15": w15}, indent=2))


if __name__ == "__main__":
    main()
