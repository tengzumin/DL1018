#!/usr/bin/env python3
"""Independently rescore the 72 B raws used by the corrected pair table.

Run from DL1018 with PowerShell 7:
  python -B reports/paper14_v2/phase1/rescore_pair_b_raw.py

This reads the frozen B raw files and the prior rescore manifest, verifies
their identities before and after scoring, and writes only beside this script.
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
METRICS = BASE / "supporting_rescore" / "outputs" / "RAW_METRICS.json"
PAIR = ROOT / "reports" / "corrected14_full72_benchmark_20261021" / "PAIR14_SCENE_RESULTS_VS_B.csv"
SCANNER = AUDIT / "scripts" / "raw_scan.py"
SCANNER_SHA256 = "680c9a3fe95d9c3b4fb9c7702343078fc679c3f64a41a44865aa4aa7435100d4"
OUT_CSV = OUT / "baseline_b_raw_rescore.csv"
OUT_JSON = OUT / "baseline_b_raw_rescore.json"


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

metrics = json.loads(METRICS.read_text(encoding="utf-8"))
b_rows = [
    row for row in metrics["results"]
    if row.get("method_id") == "B" and row.get("split") in {"DEV", "VAL"}
]
if len(b_rows) != 72 or len({row["source_scene_id"] for row in b_rows}) != 72:
    raise RuntimeError(f"expected 72 unique B rows in RAW_METRICS, got {len(b_rows)}")

pair_rows = [
    row for row in read_csv(PAIR)
    if row.get("method_id") == "CORRECTED_TRAIN_DSSM14_G12_R32"
]
if len(pair_rows) != 72 or len({row["source_scene_id"] for row in pair_rows}) != 72:
    raise RuntimeError(f"expected 72 unique DSSM14 pair rows, got {len(pair_rows)}")
pair_by_scene = {row["source_scene_id"]: row for row in pair_rows}

rescored: list[dict[str, object]] = []
for row in b_rows:
    scene_id = row["source_scene_id"]
    if scene_id not in pair_by_scene:
        raise RuntimeError(f"B scene absent from corrected pair: {scene_id}")
    pair = pair_by_scene[scene_id]
    if row["split"] != pair["split"] or row["task"] != pair["task"]:
        raise RuntimeError(f"split/task mismatch for {scene_id}")

    path = Path(row["resolved_raw_path"])
    if not path.is_file():
        raise FileNotFoundError(path)
    source_path = ROOT.parent / Path(row["source_raw_path"])
    source_sha = row["source_raw_sha256"].lower()
    expected_sha = row["raw_sha256_before"].lower()
    if expected_sha != row["raw_sha256_after"].lower():
        raise RuntimeError(f"prior rescore says resolved raw changed for {scene_id}")
    before_sha = sha256(path)
    if before_sha != expected_sha:
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
        raise RuntimeError(f"unexpected scored time grid for {scene_id}")

    rescored_q = float(scored["Q_0_20"])
    cached_q = float(row["Q_0_20"])
    pair_q = float(pair["B_Q_0_20_m"])
    rescored.append({
        "split": row["split"], "task": row["task"], "scene_id": scene_id,
        "raw_scan_scene_id": row.get("scene_id", ""),
        "manifest_source_raw_path": row["source_raw_path"],
        "resolved_raw_path": str(path),
        "resolved_path_differs_from_manifest_source": path.resolve() != source_path.resolve(),
        "manifest_source_raw_sha256": source_sha,
        "resolved_raw_sha256_expected": expected_sha,
        "raw_sha256_before": before_sha, "raw_sha256_after": after_sha,
        "cached_q_m": cached_q, "pair_table_b_q_m": pair_q,
        "independent_rescore_q_m": rescored_q,
        "rescore_minus_pair_b_m": rescored_q - pair_q,
        "rescore_matches_pair_with_1e-12_m_tolerance": abs(rescored_q - pair_q) <= 1e-12,
        **{
            f"rmse_{axis}_{phase}_m": float(scored[f"RMSE_{axis}_{phase}"])
            for axis in "xyz" for phase in ("0_20", "0_5", "5_20")
        },
        "cached_scorer_sha256": row.get("scorer_sha256", ""),
        "raw_scan_sha256": row.get("raw_scan_sha256", ""),
    })

with OUT_CSV.open("w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(rescored[0]))
    writer.writeheader()
    writer.writerows(rescored)

q_values = [float(row["independent_rescore_q_m"]) for row in rescored]
pair_q_values = [float(row["pair_table_b_q_m"]) for row in rescored]
differences = [abs(a - b) for a, b in zip(q_values, pair_q_values)]
summary = {
    "scope": "72 current corrected-pair B raws; DEV24 + VAL48; no simulation or write to raw files",
    "metrics_json": str(METRICS),
    "metrics_json_sha256": sha256(METRICS),
    "pair_csv": str(PAIR),
    "pair_csv_sha256": sha256(PAIR),
    "scorer_path": str(SCANNER),
    "scorer_sha256": sha256(SCANNER),
    "rows": len(rescored),
    "raw_scan_scene_id_fallback_count": sum(r["raw_scan_scene_id"] == "attempt_01" for r in rescored),
    "resolved_raw_sha_matches_prior_rescore": sum(
        r["raw_sha256_before"] == r["resolved_raw_sha256_expected"] for r in rescored
    ),
    "raw_unchanged_during_score": sum(r["raw_sha256_before"] == r["raw_sha256_after"] for r in rescored),
    "resolved_path_differs_from_manifest_source_count": sum(
        r["resolved_path_differs_from_manifest_source"] for r in rescored
    ),
    "manifest_source_sha_matches_resolved_sha_count": sum(
        r["manifest_source_raw_sha256"] == r["resolved_raw_sha256_expected"] for r in rescored
    ),
    "pair_q_matches_with_1e-12_m_tolerance": sum(r["rescore_matches_pair_with_1e-12_m_tolerance"] for r in rescored),
    "max_abs_rescore_vs_pair_q_m": max(differences),
    "macro_pair_b_q_m": sum(pair_q_values) / len(pair_q_values),
    "macro_rescored_b_q_m": sum(q_values) / len(q_values),
    "cached_scorer_sha256_counts": {
        key: sum(row["cached_scorer_sha256"] == key for row in rescored)
        for key in sorted({str(row["cached_scorer_sha256"]) for row in rescored})
    },
    "output_csv": str(OUT_CSV),
}
OUT_JSON.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
print(json.dumps(summary, indent=2))
