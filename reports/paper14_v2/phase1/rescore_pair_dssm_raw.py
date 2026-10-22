#!/usr/bin/env python3
"""Independently rescore the 72 DSSM14 raws bound to the corrected pair table.

Run from DL1018 with PowerShell 7:
  python -B reports/paper14_v2/phase1/rescore_pair_dssm_raw.py

Raw SHA-256 is the join key; approved runtime scene aliases are retained in the
output. Reads only the two named VAL/DEV indexes and their selected raw files.
"""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
BASE = ROOT.parent / "REFERENCE_FIX_FULL72_20261021_022342_313"
AUDIT = ROOT.parent / "DL1009_DL1018_FULL_AUDIT_20261020_233501"
EVAL = BASE / "corrected_reference_training_v1"
INDEXES = [
    EVAL / "corrected_pair_eval_v1" / "reports" / "RAW_INDEX.csv",
    EVAL / "corrected_pair_eval_tail21_v1" / "reports" / "RAW_INDEX.csv",
]
PAIR = ROOT / "reports" / "corrected14_full72_benchmark_20261021" / "PAIR14_SCENE_RESULTS_VS_B.csv"
SCANNER = AUDIT / "scripts" / "raw_scan.py"
SCANNER_SHA256 = "680c9a3fe95d9c3b4fb9c7702343078fc679c3f64a41a44865aa4aa7435100d4"
OUT_CSV = OUT / "candidate_dssm_raw_rescore.csv"
OUT_JSON = OUT / "candidate_dssm_raw_rescore.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


if sha256(SCANNER) != SCANNER_SHA256:
    raise RuntimeError("raw_scan.py SHA-256 differs from the reviewed helper")
sys.path.insert(0, str(SCANNER.parent))
spec = importlib.util.spec_from_file_location("audited_raw_scan", SCANNER)
if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot load scoring helper: {SCANNER}")
raw_scan = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = raw_scan
spec.loader.exec_module(raw_scan)

selected: list[dict[str, str]] = []
index_hashes: dict[str, str] = {}
for index_path in INDEXES:
    index_sha = sha256(index_path)
    index_hashes[str(index_path)] = index_sha
    rows = [
        row for row in read_csv(index_path)
        if row.get("method_id") == "CORRECTED_TRAIN_DSSM14_G12_R32"
        and row.get("action") == "RUN"
        and row.get("status") == "RUN_COMPLETE_STABLE"
        and row.get("complete", "").lower() == "true"
        and row.get("finite", "").lower() == "true"
    ]
    for row in rows:
        row["_raw_index_path"] = str(index_path)
        row["_raw_index_sha256"] = index_sha
    selected.extend(rows)

by_sha: dict[str, dict[str, str]] = {}
for row in selected:
    digest = row["raw_sha256"].lower()
    if digest in by_sha and by_sha[digest]["source_scene_id"] != row["source_scene_id"]:
        raise RuntimeError(f"one raw SHA maps to multiple source scenes: {digest}")
    by_sha[digest] = row
if len(by_sha) != 72:
    raise RuntimeError(f"expected 72 unique selected DSSM raw SHAs, got {len(by_sha)}")

pair_rows = [
    row for row in read_csv(PAIR)
    if row.get("method_id") == "CORRECTED_TRAIN_DSSM14_G12_R32"
]
if len(pair_rows) != 72 or len({row["candidate_raw_sha256"].lower() for row in pair_rows}) != 72:
    raise RuntimeError("pair table must contain 72 DSSM rows with unique raw SHA")
pair_by_sha = {row["candidate_raw_sha256"].lower(): row for row in pair_rows}
if set(by_sha) != set(pair_by_sha):
    raise RuntimeError("selected DSSM raw SHA set differs from frozen pair table")

rescored: list[dict[str, object]] = []
for digest, row in sorted(by_sha.items(), key=lambda item: (item[1]["split"], item[1]["source_scene_id"])):
    pair = pair_by_sha[digest]
    scene_id = row["source_scene_id"]
    if (row["split"], row["task"], row["source_scene_id"]) != (
        pair["split"], pair["task"], pair["source_scene_id"]
    ):
        raise RuntimeError(f"scene/split/task mismatch for raw SHA {digest}")
    rel_path = Path(row["raw_path"])
    path = ROOT.parent / rel_path
    if not path.is_file():
        raise FileNotFoundError(path)
    before_sha = sha256(path)
    if before_sha != digest:
        raise RuntimeError(f"pre-score raw SHA mismatch for {scene_id}")
    before_stat = path.stat()
    scored = raw_scan.score(path)
    after_stat = path.stat()
    after_sha = sha256(path)
    if after_sha != before_sha or (before_stat.st_size, before_stat.st_mtime_ns) != (
        after_stat.st_size, after_stat.st_mtime_ns
    ):
        raise RuntimeError(f"raw changed during read-only scoring: {scene_id}")
    if scored.get("status") != "scored" or not scored.get("complete") or not scored.get("finite"):
        raise RuntimeError(f"invalid raw score for {scene_id}: {scored.get('status')}")
    if int(scored["transitions"]) != 20000 or float(scored["time_start"]) != 0.0 or float(scored["time_end"]) != 19.999:
        raise RuntimeError(f"unexpected score time grid for {scene_id}")

    q = float(scored["Q_0_20"])
    pair_q = float(pair["candidate_Q_0_20_m"])
    b_q = float(pair["B_Q_0_20_m"])
    rescored.append({
        "split": row["split"], "task": row["task"], "scene_id": scene_id,
        "runtime_scene_id": row["runtime_scene_id"],
        "runtime_id_alias": row["runtime_scene_id"] != scene_id,
        "raw_index_path": row["_raw_index_path"],
        "raw_index_sha256": row["_raw_index_sha256"],
        "raw_path": str(path), "raw_sha256_expected": digest,
        "raw_sha256_before": before_sha, "raw_sha256_after": after_sha,
        "pair_table_candidate_q_m": pair_q, "independent_rescore_q_m": q,
        "rescore_minus_pair_candidate_m": q - pair_q,
        "pair_table_b_q_m": b_q,
        "rescore_matches_pair_with_1e-12_m_tolerance": abs(q - pair_q) <= 1e-12,
        **{
            f"rmse_{axis}_{phase}_m": float(scored[f"RMSE_{axis}_{phase}"])
            for axis in "xyz" for phase in ("0_20", "0_5", "5_20")
        },
    })

with OUT_CSV.open("w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(rescored[0]))
    writer.writeheader()
    writer.writerows(rescored)

scene_groups = {
    "ALL": lambda row: True,
    "HF_W09_W14": lambda row: 9 <= int(row["scene_id"].rsplit("_W", 1)[1]) <= 14,
    "W15": lambda row: row["scene_id"].endswith("_W15"),
    "W00_W08": lambda row: 0 <= int(row["scene_id"].rsplit("_W", 1)[1]) <= 8,
}
gate_summary = {}
for name, include in scene_groups.items():
    rows = [row for row in rescored if include(row)]
    b_values = [float(row["pair_table_b_q_m"]) for row in rows]
    c_values = [float(row["independent_rescore_q_m"]) for row in rows]
    margins = [b - c for b, c in zip(b_values, c_values)]
    gate_summary[name] = {
        "n": len(rows),
        "wins": sum(margin > 1e-12 for margin in margins),
        "ties": sum(abs(margin) <= 1e-12 for margin in margins),
        "losses": sum(margin < -1e-12 for margin in margins),
        "macro_b_q_m": sum(b_values) / len(rows),
        "macro_dssm_q_m": sum(c_values) / len(rows),
        "macro_delta_dssm_minus_b_mm": 1000 * (sum(c_values) - sum(b_values)) / len(rows),
        "wins_below_0p1_mm": sum(1e-12 < margin < 1e-4 for margin in margins),
        "wins_below_0p5_mm": sum(1e-12 < margin < 5e-4 for margin in margins),
    }

b_rows = {row["scene_id"]: row for row in read_csv(OUT / "baseline_b_raw_rescore.csv")}
if len(b_rows) != 72 or set(b_rows) != {row["scene_id"] for row in rescored}:
    raise RuntimeError("independent B raw-score table is missing or not scene matched")
axis_phase_summary = {}
for name, include in scene_groups.items():
    rows = [row for row in rescored if include(row)]
    axis_phase_summary[name] = {}
    for axis in "xyz":
        axis_phase_summary[name][axis] = {}
        for phase in ("0_20", "0_5", "5_20"):
            candidate_rmse = [float(row[f"rmse_{axis}_{phase}_m"]) for row in rows]
            baseline_rmse = [float(b_rows[row["scene_id"]][f"rmse_{axis}_{phase}_m"]) for row in rows]
            axis_phase_summary[name][axis][phase] = {
                "n_scenes": len(rows),
                "b_scene_macro_rmse_m": sum(baseline_rmse) / len(rows),
                "dssm_scene_macro_rmse_m": sum(candidate_rmse) / len(rows),
                "delta_dssm_minus_b_mm": 1000 * (sum(candidate_rmse) - sum(baseline_rmse)) / len(rows),
            }

pair_differences = [abs(float(row["independent_rescore_q_m"]) - float(row["pair_table_candidate_q_m"])) for row in rescored]
summary = {
    "scope": "selected corrected DSSM14 G12/R32 VAL48 + DEV24 raws only; no simulation or write to raw files",
    "indexes": {path: {"sha256": digest} for path, digest in index_hashes.items()},
    "scorer_path": str(SCANNER),
    "scorer_sha256": sha256(SCANNER),
    "pair_csv": str(PAIR),
    "pair_csv_sha256": sha256(PAIR),
    "selected_index_rows": len(selected),
    "selected_unique_raw_sha": len(by_sha),
    "selected_runtime_alias_rows": sum(row["runtime_scene_id"].endswith("_ACC_FIX_V1") for row in by_sha.values()),
    "selected_raw_sha_set_matches_pair": set(by_sha) == set(pair_by_sha),
    "raw_sha_matches_before": sum(row["raw_sha256_before"] == row["raw_sha256_expected"] for row in rescored),
    "raw_unchanged_during_score": sum(row["raw_sha256_before"] == row["raw_sha256_after"] for row in rescored),
    "pair_q_matches_with_1e-12_m_tolerance": sum(row["rescore_matches_pair_with_1e-12_m_tolerance"] for row in rescored),
    "max_abs_rescore_vs_pair_q_m": max(pair_differences),
    "gate_summary": gate_summary,
    "axis_phase_scene_macro_rmse_summary": axis_phase_summary,
    "output_csv": str(OUT_CSV),
}
OUT_JSON.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
print(json.dumps(summary, indent=2))
