from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PARENT = ROOT / "reports" / "delayed_prediction_c3_dev72_parent_20261023"
EXPT = ROOT / "experiments" / "position_delayed_prediction_c3_dev72_20261023"
OWN = PARENT / "independent_review"
METRICS = PARENT / "PARENT_ALL288_METRICS.csv"
LOCK = EXPT / "C3_DEV72_INPUT_LOCK_v2.json"
PROGRESS = EXPT / "C3_DEV72_SUMMARY_v2.json"
PARENT_SUMMARY = PARENT / "PARENT_DEV72_SUMMARY.json"
PARENT_LOSSES = PARENT / "PARENT_ALL_LOSING_PAIRS.csv"
OUT_JSON = OWN / "C3_DEV72_METRICS_PEER_RECALC.json"
OUT_MD = OWN / "C3_DEV72_METRICS_PEER_REVIEW_ZH.md"
TOL = 1e-12
METHODS = ("B", "DSSM14", "KAN14", "C3")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_json(path: Path):
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def paired_counts(rows: list[dict], comparator: str) -> dict:
    counts = {"WIN": 0, "LOSS": 0, "TIE": 0}
    for row in rows:
        delta = float(row["C3"]["Q_0_20_m"]) - float(row[comparator]["Q_0_20_m"])
        if delta < -TOL:
            counts["WIN"] += 1
        elif delta > TOL:
            counts["LOSS"] += 1
        else:
            counts["TIE"] += 1
    return counts


def summarize_group(group_name: str, scene_ids: list[str], by_scene: dict[str, dict]) -> dict:
    rows = [by_scene[s] for s in scene_ids]
    result = {"n": len(rows), "methods": {}, "C3_paired": {}}
    for method in METHODS:
        result["methods"][method] = {
            field: sum(float(r[method][field]) for r in rows) / len(rows)
            for field in ("Q_0_20_m", "Q_0_5_m", "Q_5_20_m")
        }
    for comparator in METHODS[:-1]:
        result["C3_paired"][comparator] = paired_counts(rows, comparator)
    return result


def main() -> None:
    require(not OUT_JSON.exists() and not OUT_MD.exists(), "Refusing to overwrite existing peer outputs")
    input_hashes = {p.name: sha256(p) for p in (METRICS, LOCK, PROGRESS, PARENT_SUMMARY, PARENT_LOSSES)}
    lock = read_json(LOCK)
    progress = read_json(PROGRESS)
    parent_summary = read_json(PARENT_SUMMARY)
    source_by_scene = {x["scene_id"]: x for x in lock["scenes"]}
    rows = list(csv.DictReader(METRICS.open("r", newline="", encoding="utf-8-sig")))
    require(len(rows) == 288, f"Expected 288 metrics rows, got {len(rows)}")

    by_scene: dict[str, dict] = defaultdict(dict)
    for row in rows:
        scene, method = row["scene_id"], row["method"]
        require(scene in source_by_scene, f"Unknown scene in metrics CSV: {scene}")
        require(method in METHODS and method not in by_scene[scene], f"Bad/duplicate method row: {scene}/{method}")
        require(row["external_identity_sha256"] == source_by_scene[scene]["external_identity_sha256"],
                f"External input identity mismatch: {scene}/{method}")
        if method == "B":
            expected_b = source_by_scene[scene]["B_source"]
            require(row["sha256"] == expected_b["sha256"], f"B source hash mismatch: {scene}")
        by_scene[scene][method] = row
    scene_ids = sorted(by_scene)
    require(len(scene_ids) == 72 and set(scene_ids) == set(lock["scene_ids_all_72"]),
            "Metrics scenes differ from frozen 72-scene inventory")
    require(all(set(by_scene[s]) == set(METHODS) for s in scene_ids), "Missing method row in a scene")

    new_runs = {r["scene_id"]: r for r in progress["runs"]}
    require(set(new_runs) == set(lock["scene_ids_new_60"]), "New C3 run set differs from lock")
    for scene in lock["scene_ids_new_60"]:
        row = by_scene[scene]["C3"]
        run = new_runs[scene]
        require(row["sha256"] == run["raw_sha256"] and row["path"] == run["raw_path"],
                f"New C3 metrics row is not bound to audited run: {scene}")

    split_ids = {"DEV": [], "VAL": []}
    task_ids: dict[str, list[str]] = defaultdict(list)
    wind_band_ids: dict[str, list[str]] = defaultdict(list)
    wind_cell_ids: dict[str, list[str]] = defaultdict(list)
    for scene in scene_ids:
        meta = source_by_scene[scene]
        split_ids[meta["source_split"]].append(scene)
        task_ids[meta["task"]].append(scene)
        match = re.search(r"_W(\d{2})$", scene)
        require(match is not None, f"Cannot decode frozen wind cell: {scene}")
        w = int(match.group(1))
        band = "W00_W08" if w <= 8 else ("W09_W14" if w <= 14 else "W15")
        wind_band_ids[band].append(scene)
        wind_cell_ids[f"W{w:02d}"].append(scene)
    require(len(split_ids["DEV"]) == 24 and len(split_ids["VAL"]) == 48,
            "Frozen split counts differ from DEV24+VAL48")
    require({k: len(v) for k, v in wind_band_ids.items()} ==
            {"W00_W08": 38, "W09_W14": 28, "W15": 6}, "Wind band counts differ from frozen scope")

    groups = {"ALL72": scene_ids, "DEV24": split_ids["DEV"], "VAL48": split_ids["VAL"]}
    groups.update({f"TASK_{k}": v for k, v in sorted(task_ids.items())})
    groups.update({f"WIND_{k}": wind_band_ids[k] for k in ("W00_W08", "W09_W14", "W15")})
    groups.update({f"WIND_CELL_{k}": wind_cell_ids[k] for k in sorted(wind_cell_ids)})
    grouped = {name: summarize_group(name, ids, by_scene) for name, ids in groups.items()}

    all72 = grouped["ALL72"]
    hf = grouped["WIND_W09_W14"]
    w15 = grouped["WIND_W15"]
    gates = {
        "wins_at_least_62_of_72": all72["C3_paired"]["B"]["WIN"] >= 62,
        "overall_mean_strictly_better_B": all72["methods"]["C3"]["Q_0_20_m"] < all72["methods"]["B"]["Q_0_20_m"],
        "HF_mean_not_above_B": hf["methods"]["C3"]["Q_0_20_m"] <= hf["methods"]["B"]["Q_0_20_m"],
        "W15_mean_not_above_B": w15["methods"]["C3"]["Q_0_20_m"] <= w15["methods"]["B"]["Q_0_20_m"],
    }

    losses = []
    for comparator in METHODS[:-1]:
        for scene in scene_ids:
            c3q = float(by_scene[scene]["C3"]["Q_0_20_m"])
            otherq = float(by_scene[scene][comparator]["Q_0_20_m"])
            delta = c3q - otherq
            if delta > TOL:
                losses.append({
                    "scene_id": scene,
                    "split": source_by_scene[scene]["source_split"],
                    "task": source_by_scene[scene]["task"],
                    "wind": re.search(r"_(W\d{2})$", scene).group(1),
                    "comparator": comparator,
                    "comparator_Q_m": otherq,
                    "C3_Q_m": c3q,
                    "delta_C3_minus_comparator_m": delta,
                })
    losses.sort(key=lambda x: (x["comparator"], x["scene_id"]))

    parent_losses = list(csv.DictReader(PARENT_LOSSES.open("r", newline="", encoding="utf-8-sig")))
    parent_loss_keys = {(x["scene_id"], x["comparator"]) for x in parent_losses}
    peer_loss_keys = {(x["scene_id"], x["comparator"]) for x in losses}
    require(peer_loss_keys == parent_loss_keys, "Recomputed C3 losing pairs differ from parent loss table")
    for parent_row in parent_losses:
        peer = next(x for x in losses if x["scene_id"] == parent_row["scene_id"] and
                    x["comparator"] == parent_row["comparator"])
        require(abs(peer["delta_C3_minus_comparator_m"] - float(parent_row["delta_C3_minus_comparator_m"])) < 1e-12,
                f"Loss delta differs from parent loss table: {parent_row['scene_id']}/{parent_row['comparator']}")

    # Compare the key aggregate outputs to the independently stored parent summary, without using it as input.
    parent_groups = parent_summary["groups"]
    for peer_key, parent_key in (("ALL72", "ALL72"), ("WIND_W09_W14", "HF_W09_W14"), ("WIND_W15", "W15")):
        for method in METHODS:
            peer_q = grouped[peer_key]["methods"][method]["Q_0_20_m"]
            parent_q = parent_groups[parent_key]["methods"][method]["Q_0_20_m"]
            require(abs(peer_q - parent_q) < 1e-14, f"Aggregate Q mismatch for {peer_key}/{method}")

    # Re-hash small ledgers to make sure they remained unchanged while the simple recalc ran.
    for p in (METRICS, LOCK, PROGRESS, PARENT_SUMMARY, PARENT_LOSSES):
        require(sha256(p) == input_hashes[p.name], f"Input changed during aggregation: {p.name}")

    output = {
        "schema": "C3_DEV72_METRICS_PEER_RECALC_V1",
        "status": "PASS_METRICS_RECALC_NUMERIC_GATE_FAIL",
        "metric_definition": "scene-equal mean of Q_0_20_m (3D position RMSE); pair win uses 1e-12 m tolerance",
        "input_hashes": input_hashes,
        "counts": {"scene_count": len(scene_ids), "method_rows": len(rows),
                   "DEV": len(split_ids["DEV"]), "VAL": len(split_ids["VAL"]),
                   "new_C3": len(lock["scene_ids_new_60"]), "reused_C3_not_reread": len(lock["scene_ids_reuse_12"])},
        "performance_gates": gates,
        "paired_counts": {m: all72["C3_paired"][m] for m in METHODS[:-1]},
        "groups": grouped,
        "all_C3_losing_pairs": losses,
        "parent_loss_table_rows": len(parent_losses),
        "scope_limit": "Development evidence only; 12 C3 rows are reused VAL subset, not independent scenes. No raw was read for this metrics-only recalc.",
    }
    with OUT_JSON.open("x", encoding="utf-8", newline="\n") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")

    def mm(x: float) -> str:
        return f"{1000*x:.6f}"

    lines = [
        "# C3 DEV72 指标独立表级复算",
        "",
        "输入仅为冻结的 `PARENT_ALL288_METRICS.csv` 与场景/终态清单；本复算不重读任何 raw。Q 为 0–20 秒三维位置 RMSE，场景等权，成对胜负容差为 1e-12 m。",
        "",
        f"指标表 SHA-256：`{input_hashes[METRICS.name]}`。共 {len(scene_ids)} 场、{len(rows)} 条 method 行（DEV {len(split_ids['DEV'])}，VAL {len(split_ids['VAL'])}）。",
        "",
        f"C3 对 B 为 {all72['C3_paired']['B']['WIN']} 胜、{all72['C3_paired']['B']['LOSS']} 负、{all72['C3_paired']['B']['TIE']} 平；门槛是至少 62/72 胜，因此该门失败（61/72=84.722%，不能四舍五入成 85% 通过）。",
        f"其余三项 Q 均值门通过：ALL72 C3 {mm(all72['methods']['C3']['Q_0_20_m'])} mm vs B {mm(all72['methods']['B']['Q_0_20_m'])} mm；HF W09–W14（n={hf['n']}) C3 {mm(hf['methods']['C3']['Q_0_20_m'])} mm vs B {mm(hf['methods']['B']['Q_0_20_m'])} mm；W15（n={w15['n']}) C3 {mm(w15['methods']['C3']['Q_0_20_m'])} mm vs B {mm(w15['methods']['B']['Q_0_20_m'])} mm。",
        f"全 comparator 的 C3 输场配对共 {len(losses)} 条（B 11、DSSM14 16、KAN14 1），与冻结 `PARENT_ALL_LOSING_PAIRS.csv` 的场景/comparator 集合及 delta 逐条核对一致。对 B 的 11 个输场按任务数：" + ", ".join(f"{k} {v}" for k, v in sorted(Counter(x["task"] for x in losses if x["comparator"] == "B").items())) + "；均位于 W09–W14 组。",
        "",
        "性能门总结果为 3 项通过、胜场数门失败；完整性、安全门由独立 raw/source 审核另行覆盖。该 72 场是开发证据，包含 12 个复用的 VAL 子集结果，不是独立 72 场样本或 TEST 证据。",
        "",
        f"逐组、逐方法 Q、所有输场与精度字段见同目录 `C3_DEV72_METRICS_PEER_RECALC.json`（SHA-256 `{sha256(OUT_JSON)}`）。",
    ]
    with OUT_MD.open("x", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")

    print(json.dumps({
        "status": output["status"], "gate": gates,
        "all72": {m: grouped["ALL72"]["methods"][m]["Q_0_20_m"] for m in METHODS},
        "HF": {m: grouped["WIND_W09_W14"]["methods"][m]["Q_0_20_m"] for m in METHODS},
        "W15": {m: grouped["WIND_W15"]["methods"][m]["Q_0_20_m"] for m in METHODS},
        "C3_vs_B": all72["C3_paired"]["B"], "loss_pairs": len(losses),
        "json_sha256": sha256(OUT_JSON), "md_sha256": sha256(OUT_MD),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
