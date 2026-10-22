#!/usr/bin/env python3
"""Future read-only 12-scene scorer. This file is setup code, not an executed result."""
from __future__ import annotations
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import h5py
import numpy as np

HERE = Path(__file__).resolve().parent
LOCK = json.loads((HERE / "frozen_inputs.json").read_text(encoding="utf-8"))
IDS = [row["scene_id"] for row in LOCK["scenes"]]
TOL_M = float(LOCK["analysis"]["paired_raw_tolerance_m"])


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def reference_position(path: Path) -> np.ndarray:
    with h5py.File(path, "r") as f:
        return np.asarray(f["log/reference/position"], dtype=np.float64)


manifest_path = Path(LOCK["reuse_manifest"]["path"])
if sha256(manifest_path) != LOCK["reuse_manifest"]["sha256"]:
    raise RuntimeError("Frozen reuse manifest SHA-256 changed")
manifest = csv_rows(manifest_path)
if len(manifest) != 24 or {r["scene_id"] for r in manifest} != set(IDS):
    raise RuntimeError("Expected the exact 12-scene ON/B reuse manifest")
rows_by_key = {(r["scene_id"], r["role"]): r for r in manifest}
if len(rows_by_key) != 24:
    raise RuntimeError("Duplicate scene/role in frozen reuse manifest")

candidate_rescore = csv_rows(Path(LOCK["rescores"][0]["path"]))
baseline_rescore = csv_rows(Path(LOCK["rescores"][1]["path"]))
score_by_key = {}
for role, rows in (("ON_CANDIDATE", candidate_rescore), ("B_BASELINE", baseline_rescore)):
    for r in rows:
        if r.get("scene_id") in IDS:
            score_by_key[(r["scene_id"], role)] = r
if len(score_by_key) != 24:
    raise RuntimeError("Existing ON/B rescore tables do not have all 12 frozen VAL scenes")

scanner = LOCK["scoring_helper"]
scanner_path = Path(scanner["path"])
if sha256(scanner_path) != scanner["sha256"]:
    raise RuntimeError("Reviewed raw_scan.py SHA-256 changed")
sys.path.insert(0, str(scanner_path.parent))
spec = importlib.util.spec_from_file_location("frozen_round1_raw_scan", scanner_path)
if spec is None or spec.loader is None:
    raise RuntimeError("Cannot import the reviewed read-only raw scanner")
raw_scan = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = raw_scan
spec.loader.exec_module(raw_scan)

records: list[dict[str, object]] = []
for scene_id in IDS:
    files = {}
    for role in ("ON_CANDIDATE", "B_BASELINE"):
        row = rows_by_key[(scene_id, role)]
        path = Path(row["raw_path"])
        stat_before = path.stat()
        raw_hash = sha256(path)
        stat_after = path.stat()
        if (raw_hash != row["raw_sha256"].lower()
                or stat_after.st_size != stat_before.st_size
                or stat_after.st_mtime_ns != stat_before.st_mtime_ns):
            raise RuntimeError(f"Frozen raw SHA changed: {scene_id} {role}")
        files[role] = (row, path, stat_after, raw_hash)
        score_row = score_by_key[(scene_id, role)]
        if score_row.get("rescore_matches_pair_with_1e-12_m_tolerance", "").lower() != "true":
            raise RuntimeError(f"Existing {role} rescore misses the paired Q tolerance: {scene_id}")
    off_dir = HERE / "runs" / scene_id / "attempt_01"
    off_path = off_dir / "raw_run.mat"
    if not off_path.is_file():
        raise RuntimeError(f"Missing OFF attempt output: {off_path}")
    off_before = sha256(off_path)
    off_stat = off_path.stat()
    off = raw_scan.score(off_path)
    off_after = sha256(off_path)
    if off_after != off_before or off_path.stat().st_mtime_ns != off_stat.st_mtime_ns:
        raise RuntimeError(f"OFF raw changed during scoring: {scene_id}")
    if (off.get("status") != "scored" or not off.get("complete") or not off.get("finite")
            or off.get("log_status") != "STABLE" or int(off.get("transitions", 0)) != 20000
            or float(off.get("time_start", -1)) != 0.0 or float(off.get("time_end", -1)) != 19.999):
        raise RuntimeError(f"OFF run is unsafe/incomplete/nonfinite: {scene_id} {off}")

    refs = [reference_position(files[role][1]) for role in ("ON_CANDIDATE", "B_BASELINE")]
    refs.append(reference_position(off_path))
    for role in ("ON_CANDIDATE", "B_BASELINE"):
        row, path, read_stat, read_hash = files[role]
        after_stat = path.stat()
        after_hash = sha256(path)
        if (after_hash != read_hash or after_stat.st_size != read_stat.st_size
                or after_stat.st_mtime_ns != read_stat.st_mtime_ns):
            raise RuntimeError(f"Frozen {role} raw changed during payload read: {scene_id}")
    if any(a.shape != refs[0].shape for a in refs[1:]):
        raise RuntimeError(f"Paired reference position shapes differ: {scene_id}")
    ref_max = max(float(np.max(np.abs(a - refs[0]))) for a in refs[1:])
    if ref_max > TOL_M:
        raise RuntimeError(f"Paired references exceed {TOL_M:g} m tolerance: {scene_id} {ref_max}")

    on = score_by_key[(scene_id, "ON_CANDIDATE")]
    b = score_by_key[(scene_id, "B_BASELINE")]
    scene_lock = next(r for r in LOCK["scenes"] if r["scene_id"] == scene_id)
    record: dict[str, object] = {
        "scene_id": scene_id, "split": "VAL", "task": scene_lock["task"], "band": scene_lock["band"],
        "on_raw_sha256": files["ON_CANDIDATE"][0]["raw_sha256"],
        "b_raw_sha256": files["B_BASELINE"][0]["raw_sha256"], "off_raw_sha256": off_after,
        "paired_reference_max_abs_diff_m": ref_max, "off_safe_complete_finite": True,
        "q_on_0_20_m": float(on["independent_rescore_q_m"]),
        "q_b_0_20_m": float(b["independent_rescore_q_m"]),
        "q_off_0_20_m": float(off["Q_0_20"]),
    }
    for axis in "xyz":
        for phase in ("0_20", "0_5", "5_20"):
            record[f"rmse_{axis}_on_{phase}_m"] = float(on[f"rmse_{axis}_{phase}_m"])
            record[f"rmse_{axis}_b_{phase}_m"] = float(b[f"rmse_{axis}_{phase}_m"])
            record[f"rmse_{axis}_off_{phase}_m"] = float(off[f"RMSE_{axis}_{phase}"])
    records.append(record)

if len(records) != 12 or not all(r["off_safe_complete_finite"] for r in records):
    raise RuntimeError("The registered decision requires 12/12 safe, complete, finite OFF runs")

hf = [r for r in records if r["band"] in ("W09_W11", "W12_W14")]
low = [r for r in records if r["band"] == "W00_W08"]
w15 = [r for r in records if r["band"] == "W15"]
mean = lambda rows, key: float(np.mean([float(r[key]) for r in rows]))
hf_q_improvement = mean(hf, "q_on_0_20_m") - mean(hf, "q_off_0_20_m")
hf_z_wins = sum(float(r["rmse_z_off_0_20_m"]) < float(r["rmse_z_on_0_20_m"]) - TOL_M for r in hf)
low_q_regression = mean(low, "q_off_0_20_m") - mean(low, "q_on_0_20_m")
w15_q_regression = mean(w15, "q_off_0_20_m") - mean(w15, "q_on_0_20_m")
gate = (hf_q_improvement > TOL_M and hf_z_wins >= 4 and
        low_q_regression <= 0.0005 and w15_q_regression <= 0.0005 and len(records) == 12)
summary = {
    "schema": "FROZEN_W0_SCREEN_RESULTS_V1", "status": "COMPLETE_12_SCENE_SCREEN",
    "safe_complete_finite_off_runs": len(records), "paired_reference_tolerance_m": TOL_M,
    "hf_w09_w14": {"n": len(hf), "mean_q_on_m": mean(hf, "q_on_0_20_m"),
                    "mean_q_off_m": mean(hf, "q_off_0_20_m"), "mean_q_improvement_m": hf_q_improvement,
                    "z_rmse_off_wins_of_6": hf_z_wins},
    "w00_w08": {"n": len(low), "mean_q_regression_off_minus_on_m": low_q_regression},
    "w15": {"n": len(w15), "mean_q_regression_off_minus_on_m": w15_q_regression},
    "registered_gate_pass": gate,
    "decision": "PROPOSE_EXPAND_72" if gate else "FALSIFY_CURRENT_HYPOTHESIS_KEEP_ALL_DATA_NO_TUNING",
    "claim_limit": "A 12-scene screen cannot establish the full 72-scene target.",
    "metric_rows": len(records),
}
report_dir = HERE / "reports"
report_dir.mkdir(parents=True, exist_ok=True)
with (report_dir / "round1_screen_results.csv").open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=list(records[0]))
    writer.writeheader()
    writer.writerows(records)
(report_dir / "round1_screen_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps(summary, indent=2))
