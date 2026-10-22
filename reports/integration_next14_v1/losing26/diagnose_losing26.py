from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

import h5py
import numpy as np


OUT = Path(__file__).resolve().parent
WORKSPACE = Path(__file__).resolve().parents[3]
BASE = WORKSPACE.parent
REF = BASE / "REFERENCE_FIX_FULL72_20261021_022342_313"
BENCH = WORKSPACE / "reports" / "corrected14_full72_benchmark_20261021"
V2 = REF / "supporting_rescore" / "corrected_training_comparison_v2"
PLAN_V3 = V2 / "comparison_plan_v3.json"
CURRENT14 = V2 / "outputs" / "current14"
PAIR_ROOT = REF / "corrected_reference_training_v1" / "corrected_pair_eval_v1"
TAIL_ROOT = REF / "corrected_reference_training_v1" / "corrected_pair_eval_tail21_v1"
PAIR_METHOD = "CORRECTED_TRAIN_DSSM14_G12_R32"
AXES = "xyz"
PHASES = ((0.0, 5.0, "0_5"), (5.0, 10.0, "5_10"),
          (10.0, 15.0, "10_15"), (15.0, 20.0, "15_20"))
PRIMARY_PHASES = ((0.0, 5.0, "0_5"), (5.0, 20.0, "5_20"), (0.0, 20.0, "0_20"))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError(f"refusing to write an empty table: {path.name}")
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="raise", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def fnum(value: object) -> float:
    out = float(value)
    if not math.isfinite(out):
        raise ValueError(f"nonfinite value: {value!r}")
    return out


def key(row: dict) -> tuple[str, str, str, str]:
    return tuple(str(row.get(k, "")) for k in ("split", "task", "source_scene_id", "contract_id"))


def map_unique(rows: list[dict], label: str, keyfn=key) -> dict:
    out = {}
    for row in rows:
        k = keyfn(row)
        if k in out:
            raise ValueError(f"duplicate {label} identity: {k}")
        out[k] = row
    return out


def resolve_base_relative(value: str) -> Path:
    p = Path(str(value).strip())
    return p.resolve() if p.is_absolute() else (BASE / p).resolve()


def truth(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def prepare() -> None:
    pair_csv = BENCH / "PAIR14_SCENE_RESULTS_VS_B.csv"
    scene_csv = CURRENT14 / "SCENE_COMPARISON_V2.csv"
    plan = read_json(PLAN_V3)
    full_plan_path = (V2 / plan["full_plan"]).resolve()
    full_plan = read_json(full_plan_path)
    pair_spec = plan["pair14"]
    composed_path = (V2 / pair_spec["composed_report"]).resolve()
    composed = read_json(composed_path)
    full_raw_index_path = REF / "reports" / "RAW_INDEX.csv"
    full_source = next(s for s in full_plan["sources"] if s["cohort_id"] == "FULL288")
    full_metrics_path = (full_plan_path.parent / full_source["metrics_csv"]).resolve()
    if sha256(full_metrics_path).lower() != full_source["expected_file_sha256"]["metrics_csv"].lower():
        raise ValueError("FULL288 RAW_METRICS SHA differs from its frozen comparison plan")
    full_b_metrics = [r for r in read_csv(full_metrics_path) if r.get("method_id") == "B"]
    full_raw_index = [r for r in read_csv(full_raw_index_path) if r.get("method_id") == "B"]
    original_index_path = PAIR_ROOT / "reports" / "RAW_INDEX.csv"
    tail_index_path = TAIL_ROOT / "reports" / "RAW_INDEX.csv"
    original_index = read_csv(original_index_path)
    tail_index = read_csv(tail_index_path)
    original_by_index = {int(r["manifest_index"]): r for r in original_index}
    tail_by_index = {int(r["manifest_index"]): r for r in tail_index}
    raw_metrics = {int(r["manifest_index"]): r for r in composed["raw_metrics"]}
    replay = {int(r["manifest_index"]): r for r in composed["runtime_replay"]}

    pair_rows = [r for r in read_csv(pair_csv) if r.get("method_id") == PAIR_METHOD]
    scene_rows = read_csv(scene_csv)
    candidate_rows = [r for r in scene_rows if r.get("cohort_id") == "PAIR14_144" and r.get("method_id") == PAIR_METHOD]
    b_rows = [r for r in scene_rows if r.get("cohort_id") == "FULL288" and r.get("method_id") == "B"]
    pair_by = map_unique(pair_rows, "PAIR14 DSSM14")
    candidate_by = map_unique(candidate_rows, "current14 DSSM14")
    b_by = map_unique(b_rows, "current14 FULL B")
    full_ix_by = map_unique(full_raw_index, "FULL B RAW_INDEX")
    full_metrics_by = map_unique(full_b_metrics, "FULL B RAW_METRICS")

    if len(pair_by) != 72 or len(candidate_by) != 72 or len(b_by) != 72 or len(full_ix_by) != 72 or len(full_metrics_by) != 72:
        raise ValueError("expected exactly 72 unique DSSM14/B pairs across score tables and FULL indexes")
    if composed.get("status") != "PASS_COMPOSED_144_ALL_STABLE_TWO_SESSIONS":
        raise ValueError("latest composed PAIR14 report is not PASS")

    all_pairs = []
    for k, pair in pair_by.items():
        scene, cand, b, cix = candidate_by[k], b_by[k], b_by[k], full_ix_by[k]
        # Keep the PAIR score CSV, current14 comparison, and B index bound to the same scene.
        if (pair["split"], pair["task"], pair["source_scene_id"], pair["contract_id"]) != k:
            raise ValueError(f"PAIR14 key mismatch: {k}")
        if (scene["split"], scene["task"], scene["source_scene_id"], scene["contract_id"]) != k:
            raise ValueError(f"candidate current14 key mismatch: {k}")
        if (b["split"], b["task"], b["source_scene_id"], b["contract_id"]) != k:
            raise ValueError(f"FULL B comparison key mismatch: {k}")
        if (cix["split"], cix["task"], cix["source_scene_id"], cix["contract_id"]) != k:
            raise ValueError(f"FULL B RAW_INDEX key mismatch: {k}")
        if fnum(pair["B_Q_0_20_m"]) != fnum(b["q_0_20_m"]):
            raise ValueError(f"PAIR14 B Q differs from current14 FULL B: {k}")
        if abs(fnum(pair["candidate_Q_0_20_m"]) - fnum(scene["q_0_20_m"])) > 1e-14:
            raise ValueError(f"PAIR14 candidate Q differs from current14: {k}")
        if abs(fnum(pair["delta_candidate_minus_B_mm"]) - fnum(scene["paired_delta_vs_B_mm"])) > 1e-9:
            raise ValueError(f"PAIR14 delta differs from current14: {k}")
        if pair["result_vs_B"] != scene["paired_result_vs_B"]:
            raise ValueError(f"PAIR14 result differs from current14: {k}")
        if not truth(pair["external_arrays_sha256_match"]):
            raise ValueError(f"PAIR14 external arrays not matched to B: {k}")
        if cix["status"] not in {"REUSE_VALID", "RUN_COMPLETE_STABLE"} or cix.get("physical_status") != "RUN_COMPLETE_STABLE":
            raise ValueError(f"B RAW_INDEX is not a stable completed row: {k}")
        if cix.get("complete", "").lower() != "true" or cix.get("finite", "").lower() != "true" or int(cix.get("transitions", 0)) != 20000:
            raise ValueError(f"B RAW_INDEX quality mismatch: {k}")
        full_raw = resolve_base_relative(b["raw_path"])
        if resolve_base_relative(cix["raw_path"]) != full_raw or str(cix["raw_sha256"]).lower() != str(b["raw_sha256"]).lower():
            raise ValueError(f"B current14 row does not bind FULL RAW_INDEX: {k}")
        if (int(scene["manifest_index"]) < 1 or int(scene["manifest_index"]) > 144
                or scene["cell_status"] != "SCORED_VALID" or scene["raw_index_status"] != "RUN_COMPLETE_STABLE"):
            raise ValueError(f"candidate current14 row is not scored/stable: {k}")
        if int(scene["manifest_index"]) <= 123:
            selected_ix = original_by_index[int(scene["manifest_index"])]
            source_index_path, source_root, session = original_index_path, PAIR_ROOT, "original_1_123"
        else:
            selected_ix = tail_by_index[int(scene["manifest_index"])]
            source_index_path, source_root, session = tail_index_path, TAIL_ROOT, "tail21_124_144"
        ridx = int(scene["manifest_index"])
        candidate_replay = replay[ridx]
        candidate_raw_metric = raw_metrics[ridx]
        if (key(selected_ix) != k or selected_ix["method_id"] != PAIR_METHOD
                or selected_ix["status"] != "RUN_COMPLETE_STABLE"
                or not truth(selected_ix["complete"]) or not truth(selected_ix["finite"])
                or int(selected_ix["transitions"]) != 20000):
            raise ValueError(f"selected PAIR14 session RAW_INDEX mismatch: {k}")
        candidate_raw = resolve_base_relative(scene["raw_path"])
        if (resolve_base_relative(selected_ix["raw_path"]) != candidate_raw
                or selected_ix["raw_sha256"].lower() != scene["raw_sha256"].lower()):
            raise ValueError(f"candidate current14 row does not bind selected session RAW_INDEX: {k}")
        if (candidate_replay["cell_status"] != "REPLAY_VALID"
                or candidate_replay.get("runtime_contract_diagnostic") != "MATCH"
                or candidate_replay.get("numerical_replay_thresholds_all_within") is not True
                or candidate_replay.get("model_array_identity_match") is not True
                or candidate_replay.get("independent_raw_sha256", "").lower() != scene["raw_sha256"].lower()):
            raise ValueError(f"candidate runtime replay is not bound/valid: {k}")
        b_external = str(full_metrics_by[k].get("external_arrays_sha256", "")).lower()
        c_external = str(candidate_raw_metric.get("external_arrays_sha256", "")).lower()
        if not b_external or b_external != c_external:
            raise ValueError(f"composed PAIR14 external arrays mismatch FULL B: {k}")
        if abs(fnum(scene["q_0_20_m"]) - fnum(pair["candidate_Q_0_20_m"])) > 1e-14:
            raise ValueError(f"candidate Q cross-check failed: {k}")
        early_delta = (fnum(scene["q_0_5_m"]) - fnum(b["q_0_5_m"])) * 1000.0
        late_delta = (fnum(scene["q_5_20_m"]) - fnum(b["q_5_20_m"])) * 1000.0
        all_pairs.append({
            "key": k, "pair": pair, "candidate": scene, "b": b, "b_index": cix,
            "candidate_index": selected_ix, "candidate_replay": candidate_replay,
            "candidate_raw_metric": candidate_raw_metric, "candidate_index_path": source_index_path,
            "candidate_session": session, "candidate_root": source_root,
            "b_external_arrays_sha256": b_external, "candidate_external_arrays_sha256": c_external,
            "early_delta_mm": early_delta, "late_delta_mm": late_delta,
        })

    losses = [p for p in all_pairs if p["pair"]["result_vs_B"] == "LOSS"]
    wins = [p for p in all_pairs if p["pair"]["result_vs_B"] == "WIN"]
    ties = [p for p in all_pairs if p["pair"]["result_vs_B"] == "TIE"]
    if (len(losses), len(wins), len(ties)) != (26, 46, 0):
        raise ValueError(f"unexpected 72-pair outcome counts: {len(wins)}/{len(ties)}/{len(losses)}")
    mean_b_mm = float(np.mean([fnum(p["b"]["q_0_20_m"]) for p in all_pairs]) * 1000)
    mean_c_mm = float(np.mean([fnum(p["candidate"]["q_0_20_m"]) for p in all_pairs]) * 1000)
    if abs(mean_b_mm - 17.058080675350787) > 1e-9 or abs(mean_c_mm - 12.387217899198616) > 1e-9:
        raise ValueError(f"72-scene macro mean mismatch: B={mean_b_mm}, DSSM14={mean_c_mm}")
    worst = max(losses, key=lambda p: fnum(p["pair"]["delta_candidate_minus_B_mm"]))
    if abs(fnum(worst["pair"]["delta_candidate_minus_B_mm"]) - 2.4062681782696176) > 1e-9:
        raise ValueError("maximum DSSM14 loss mismatch")
    phase_counts = Counter()
    for p in losses:
        early, late = p["early_delta_mm"], p["late_delta_mm"]
        phase_counts["BOTH_WORSE" if early > 1e-9 and late > 1e-9 else
                     "EARLY_ONLY" if early > 1e-9 else
                     "LATE_ONLY" if late > 1e-9 else "NEITHER"] += 1
    if dict(phase_counts) != {"BOTH_WORSE": 12, "EARLY_ONLY": 4, "LATE_ONLY": 10}:
        raise ValueError(f"current14 0-5/5-20 loss pattern differs from parent independent check: {dict(phase_counts)}")

    # Fixed before opening any raw: earliest VAL winner by source_scene_id for each task.
    references = {}
    for task in sorted({p["key"][1] for p in all_pairs}):
        eligible = sorted((p for p in wins if p["key"][1] == task and p["key"][0] == "VAL"),
                          key=lambda p: p["key"][2])
        if not eligible:
            raise ValueError(f"no VAL win available for fixed {task} reference")
        references[task] = eligible[0]
    selected = {p["key"]: p for p in losses}
    selected.update({p["key"]: p for p in references.values()})
    if len(selected) != 29:
        raise ValueError(f"expected 29 physical scenes, got {len(selected)}")

    integrity_path = TAIL_ROOT / "reports" / "b_comparison_offline_v1" / "actual_raw_file_integrity_216.csv"
    integrity = read_csv(integrity_path)
    integrity_by = map_unique(integrity, "actual raw file integrity",
                              lambda r: (r["cohort"], r["method_id"], r["split"], r["task"], r["source_scene_id"], r["contract_id"]))
    whitelist = []
    for k, p in sorted(selected.items()):
        role = "LOSS" if p["pair"]["result_vs_B"] == "LOSS" else "FIXED_TASK_WIN"
        candidate = p["candidate"]
        b = p["b"]
        b_path = resolve_base_relative(b["raw_path"])
        c_path = resolve_base_relative(candidate["raw_path"])
        for method, row, path, ix_path, ix, external, replay_row, cohort in (
                ("B", b, b_path, full_raw_index_path, p["b_index"], p["b_external_arrays_sha256"], {}, "FULL_B"),
                ("DSSM14", candidate, c_path, p["candidate_index_path"], p["candidate_index"],
                 p["candidate_external_arrays_sha256"], p["candidate_replay"], "PAIR14")):
            ident = (cohort, ix["method_id"], k[0], k[1], k[2], k[3])
            integ = integrity_by.get(ident)
            if not integ or integ["status"] != "PASS" or integ["expected_sha256"].lower() != str(row["raw_sha256"]).lower():
                raise ValueError(f"existing actual raw integrity report does not bind {method} {k}")
            whitelist.append({
                "selection_role": role, "split": k[0], "task": k[1], "source_scene_id": k[2],
                "contract_id": k[3], "result_vs_B": p["pair"]["result_vs_B"],
                "paired_delta_mm": p["pair"]["delta_candidate_minus_B_mm"],
                "q_0_20_m": row["q_0_20_m"], "q_0_5_m": row.get("q_0_5_m", ""),
                "q_5_20_m": row.get("q_5_20_m", ""), "method": method,
                "manifest_index": row.get("manifest_index", ix.get("manifest_index", "")),
                "session": "FULL_B" if method == "B" else p["candidate_session"],
                "raw_path": str(path), "expected_raw_sha256": row["raw_sha256"],
                "external_arrays_sha256": external, "raw_index_path": str(ix_path.resolve()),
                "raw_index_sha256": sha256(ix_path), "index_status": ix["status"],
                "physical_status": ix.get("physical_status", ix["status"]),
                "transitions": ix["transitions"], "integrity_size_bytes": integ["expected_size"],
                "integrity_mtime_ns": integ["expected_mtime_ns"],
                "candidate_replay_status": replay_row.get("cell_status", ""),
                "candidate_W0_error": replay_row.get("W0_error", ""),
                "candidate_raw_replay_max": replay_row.get("raw_replay_max", ""),
                "candidate_applied_replay_max": replay_row.get("applied_replay_max", ""),
                "candidate_runtime_contract": replay_row.get("runtime_contract_diagnostic", ""),
            })

    source_files = [pair_csv, scene_csv, PLAN_V3, full_plan_path, full_metrics_path, full_raw_index_path,
                    original_index_path, tail_index_path, composed_path, integrity_path,
                    BENCH / "VALIDATION_SUMMARY.json"]
    sources = {str(p.resolve()): {"sha256": sha256(p), "size_bytes": p.stat().st_size} for p in source_files}
    summary = {
        "status": "WHITELIST_PREPARED_NO_RAW_OPENED",
        "purpose": "Corrected DSSM14 26-loss offline diagnosis with 3 fixed task win references",
        "selection_rule": "26 DSSM14 losses from PAIR14_SCENE_RESULTS_VS_B; per task, earliest VAL DSSM14 win by source_scene_id as fixed reference; then B and DSSM14 only.",
        "raw_files_whitelisted": len(whitelist), "selected_physical_scenes": len(selected),
        "corrected_dssm14_72": {"n": len(all_pairs), "wins": len(wins), "losses": len(losses), "ties": len(ties),
                                "mean_B_mm": mean_b_mm, "mean_DSSM14_mm": mean_c_mm,
                                "worst_loss_scene": worst["key"][2],
                                "worst_loss_delta_mm": fnum(worst["pair"]["delta_candidate_minus_B_mm"])},
        "loss_phase_patterns_0_5_vs_5_20": dict(phase_counts),
        "mean_loss_delta_mm": float(np.mean([fnum(p["pair"]["delta_candidate_minus_B_mm"]) for p in losses])),
        "fixed_task_win_references": {task: p["key"][2] for task, p in references.items()},
        "raw_scope": "Only VAL/DEV rows; 29 scenes x {FULL B, corrected DSSM14}; no TEST row or TEST raw path is in the whitelist.",
        "existing_reuse": {
            "PAIR14_composed_report": str(composed_path.resolve()),
            "runtime_replay": "Reuse the 144 corrected PAIR14 verified REPLAY_VALID rows; no replay runner is invoked.",
            "raw_scan": "The analyzer imports raw_scan.arr and raw_scan.score as pure helpers; it never calls raw_scan.main.",
            "prior_adaptation_audit": "Not reused as corrected evidence: its fixed 216 rows are FULL72 old NN methods.",
        },
        "sources": sources,
    }
    write_csv(OUT / "raw_whitelist.csv", whitelist)
    write_json(OUT / "identity_and_scope.json", summary)
    print(json.dumps({k: summary[k] for k in ("status", "raw_files_whitelisted", "selected_physical_scenes",
                                                "corrected_dssm14_72", "loss_phase_patterns_0_5_vs_5_20",
                                                "fixed_task_win_references")}, ensure_ascii=False, indent=2))


def import_raw_helpers():
    audit = BASE / "DL1009_DL1018_FULL_AUDIT_20261020_233501" / "scripts"
    if not audit.is_dir():
        raise FileNotFoundError(f"raw_scan helper directory missing: {audit}")
    sys.path.insert(0, str(audit))
    from raw_scan import arr, score  # pure helpers; never call raw_scan.main()
    return arr, score


def field_array(log, arr_fn, name: str):
    try:
        return np.asarray(arr_fn(log, name))
    except (KeyError, ValueError, TypeError):
        return None


def as_rows(a: np.ndarray | None, n: int, columns: int | None = None) -> np.ndarray | None:
    if a is None:
        return None
    a = np.asarray(a)
    if a.ndim == 0:
        return a.reshape(1)
    if columns is not None:
        if a.ndim == 1 and columns == 1:
            a = a.reshape(-1, 1)
        if a.ndim == 2 and a.shape == (columns, n):
            a = a.T
        if a.ndim == 2 and a.shape[1] == columns:
            return a
        return None
    if a.shape[0] == n:
        return a.reshape(n, -1) if a.ndim > 1 else a.reshape(n, 1)
    return a.reshape(a.shape[0], -1)


def event_rows(a: np.ndarray | None, n: int, event_ix: np.ndarray, columns: int | None = None):
    rows = as_rows(a, n, columns)
    if rows is None:
        return None, None
    if rows.shape[0] == n:
        return rows[event_ix], "TRANSITION_ALIGNED"
    if rows.shape[0] == len(event_ix):
        return rows, "VALID_EVENT_ALIGNED"
    return None, f"SHAPE_MISMATCH_{rows.shape[0]}"


def finite_rmse(values: np.ndarray | None, mask: np.ndarray, axis: int | None = None) -> tuple[float | None, int]:
    if values is None:
        return None, 0
    a = np.asarray(values)
    if a.ndim == 1:
        a = a[:, None]
    selected = a[mask]
    if not selected.size:
        return None, 0
    if axis is not None:
        if selected.ndim == 1:
            selected = selected[:, None]
        selected = selected[:, axis]
    finite = np.isfinite(selected)
    if not finite.any():
        return None, 0
    return float(np.sqrt(np.mean(np.square(selected[finite])))), int(finite.sum())


def finite_norm_stats(values: np.ndarray | None, mask: np.ndarray) -> tuple[float | None, float | None, int]:
    if values is None:
        return None, None, 0
    a = np.asarray(values)
    if a.ndim == 1:
        norm = np.abs(a)
    else:
        norm = np.linalg.norm(a, axis=1)
    picked = norm[mask]
    picked = picked[np.isfinite(picked)]
    if not picked.size:
        return None, None, 0
    return float(np.mean(picked)), float(np.quantile(picked, 0.95)), int(picked.size)


def any_active(values: np.ndarray | None, n: int) -> np.ndarray | None:
    if values is None:
        return None
    a = np.asarray(values)
    if a.ndim == 0:
        return np.repeat(bool(a), n)
    if a.shape[0] == n:
        return np.any(a.reshape(n, -1) != 0, axis=1)
    return None


def analyze_one(row: dict[str, str], arr_fn, raw_score_fn) -> dict:
    path = Path(row["raw_path"])
    before = path.stat()
    actual_sha = sha256(path)
    after_hash = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after_hash.st_size, after_hash.st_mtime_ns):
        raise RuntimeError(f"raw changed while hashing: {path}")
    if actual_sha.lower() != row["expected_raw_sha256"].lower():
        raise ValueError(f"raw SHA differs from current table/index: {path}")
    if (before.st_size != int(row["integrity_size_bytes"])
            or before.st_mtime_ns != int(row["integrity_mtime_ns"])):
        raise ValueError(f"raw size/mtime differs from actual integrity report: {path}")

    raw_metrics = raw_score_fn(path)
    if raw_metrics.get("status") != "scored" or raw_metrics.get("stable_read") is not True:
        raise ValueError(f"existing raw_scan pure score helper did not pass: {path}: {raw_metrics.get('status')}")
    if int(raw_metrics["transitions"]) != 20000 or not raw_metrics.get("complete") or not raw_metrics.get("finite"):
        raise ValueError(f"raw_scan transition/finite contract differs: {path}")
    if str(raw_metrics.get("external_arrays_sha256", "")).lower() != row["external_arrays_sha256"].lower():
        raise ValueError(f"raw external array identity differs from verified FULL B: {path}")
    for q_name, src_name in (("Q_0_20", "q_0_20_m"), ("Q_0_5", "q_0_5_m"), ("Q_5_20", "q_5_20_m")):
        if abs(fnum(raw_metrics[q_name]) - fnum(row[src_name])) > 2e-11:
            raise ValueError(f"raw_scan {q_name} differs from current comparison table: {path}")

    with h5py.File(path, "r") as f:
        log = f["log"]
        times = np.asarray(arr_fn(log, "transition_time"), dtype=np.float64).reshape(-1)
        state = as_rows(field_array(log, arr_fn, "state"), len(times), 12)
        ref_pos = as_rows(field_array(log, arr_fn, "reference/position"), len(times), 3)
        if state is None or ref_pos is None or len(times) != 20000:
            raise ValueError(f"state/reference layout mismatch: {path}")
        # Native logs contain one extra terminal state/reference sample beyond the
        # transition grid; raw_scan.score uses the first N rows for N transitions.
        # Match that exact convention before time-aligned descriptive statistics.
        if state.shape[0] == len(times) + 1:
            state = state[:len(times)]
        if ref_pos.shape[0] == len(times) + 1:
            ref_pos = ref_pos[:len(times)]
        if state.shape[0] != len(times) or ref_pos.shape[0] != len(times):
            raise ValueError(f"state/reference row count does not match transition grid: {path}")
        if not np.all(np.diff(times) > 0):
            raise ValueError(f"transition_time is not strictly increasing: {path}")
        position_error = ref_pos - state[:, :3]
        velocity = state[:, 3:6]
        actual_acc_fd = np.gradient(velocity, times, axis=0, edge_order=2)
        actual_acc_fd[[0, -1], :] = np.nan
        nominal = as_rows(field_array(log, arr_fn, "position_nominal_acceleration_mps2"), len(times), 3)
        nominal_residual = actual_acc_fd - nominal if nominal is not None else None
        valid_raw = field_array(log, arr_fn, "stage1_position_event_inference_valid")
        valid_mask = (np.asarray(valid_raw).reshape(-1).astype(bool)
                      if valid_raw is not None and np.asarray(valid_raw).size == len(times)
                      else np.zeros(len(times), dtype=bool))
        event_ix = np.flatnonzero(valid_mask)
        event_times = times[event_ix]

        field_names = (
            "position_nominal_acceleration_mps2",
            "stage1_position_event_inference_valid",
            "stage1_position_event_raw_acceleration_mps2",
            "stage1_position_event_applied_acceleration_mps2",
            "stage1_position_event_beta",
            "stage1_position_event_weight_delta_fro",
            "position_head_update_executed",
            "stage1_position_pcf_a_req_mps2",
            "stage1_position_pcf_a_f_mps2",
            "stage1_position_pcf_eta_before_mps",
            "stage1_position_pcf_eta_after_mps",
            "stage1_position_event_projection",
            "motor_saturated",
            "generalized_clipped",
        )
        arrays = {name: field_array(log, arr_fn, name) for name in field_names}
        event_fields = {}
        coverage = []
        for name in field_names:
            value = arrays[name]
            aligned, align_status = event_rows(value, len(times), event_ix, 3 if name.endswith(("_mps2", "_mps")) else None)
            finite_n = int(np.isfinite(aligned).all(axis=1).sum()) if aligned is not None and aligned.ndim > 1 else (
                int(np.isfinite(aligned).sum()) if aligned is not None else 0)
            non_event_nan = None
            if value is not None and np.asarray(value).ndim >= 1 and np.asarray(value).shape[0] == len(times):
                v = np.asarray(value).reshape(len(times), -1)
                non_event_nan = int((~np.isfinite(v[~valid_mask])).sum())
            coverage.append({
                "split": row["split"], "task": row["task"], "source_scene_id": row["source_scene_id"],
                "method": row["method"], "field": name, "present": value is not None,
                "shape": "" if value is None else "x".join(map(str, np.asarray(value).shape)),
                "valid_inference_events": len(event_ix), "finite_valid_event_rows": finite_n,
                "non_event_nonfinite_values_excluded": non_event_nan,
                "alignment": align_status or "NOT_LOGGED",
            })
            if aligned is not None:
                event_fields[name] = aligned
        if len(event_ix):
            step_index = field_array(log, arr_fn, "stage1_position_event_step_index")
            if step_index is not None:
                sidx = np.asarray(step_index).reshape(-1).astype(np.int64)
                if not np.array_equal(sidx, event_ix + 1):
                    raise ValueError(f"valid inference mask does not match logged step_index: {path}")

        error_norm = np.linalg.norm(position_error, axis=1)
        one_second_q = []
        for second in range(20):
            mask = (times >= second) & (times < second + 1)
            one_second_q.append(float(np.sqrt(np.mean(np.sum(position_error[mask] ** 2, axis=1)))))
        time_hash = hashlib.sha256(np.asarray(times, dtype="<f8").tobytes()).hexdigest()
        position_rows = []
        control_rows = []
        error_rmse_by_phase = {}
        first_event = float(event_times[0]) if len(event_times) else None
        update_times = None
        update_flag = any_active(arrays["position_head_update_executed"], len(times))
        if update_flag is not None and len(event_ix):
            update_times = times[np.flatnonzero(update_flag & valid_mask)]
        raw_evt = event_fields.get("stage1_position_event_raw_acceleration_mps2")
        applied_evt = event_fields.get("stage1_position_event_applied_acceleration_mps2")
        beta_evt = event_fields.get("stage1_position_event_beta")
        clip_evt = None
        clip_times = None
        if raw_evt is not None and applied_evt is not None and beta_evt is not None:
            beta1 = np.asarray(beta_evt).reshape(-1)
            if len(beta1) == len(event_times) and raw_evt.ndim == 2 and applied_evt.ndim == 2:
                eligible = np.isfinite(beta1) & (beta1 > 1e-12)
                normalized_applied = np.full_like(applied_evt, np.nan, dtype=float)
                normalized_applied[eligible] = applied_evt[eligible] / beta1[eligible, None]
                clip_evt = np.any(np.abs(raw_evt) > np.abs(normalized_applied) + 1e-8, axis=1) & eligible
                clip_times = event_times[clip_evt]

        motor_active = any_active(arrays["motor_saturated"], len(times))
        generalized_active = any_active(arrays["generalized_clipped"], len(times))
        projection_evt, _ = event_rows(arrays["stage1_position_event_projection"], len(times), event_ix)
        projection_times = None
        if projection_evt is not None:
            projection_mask = (np.zeros(0, dtype=bool) if len(event_ix) == 0 else
                               np.any(np.asarray(projection_evt).reshape(len(event_ix), -1) != 0, axis=1))
            projection_times = event_times[projection_mask]

        for lo, hi, label in (*PHASES, (5.0, 20.0, "5_20"), (0.0, 20.0, "0_20")):
            trans_mask = (times >= lo) & (times < hi)
            evt_mask = (event_times >= lo) & (event_times < hi)
            ep = position_error[trans_mask]
            q = float(np.sqrt(np.mean(np.sum(ep ** 2, axis=1)))) if ep.size else None
            error_rmse_by_phase[label] = q
            for axis_i, axis in enumerate(AXES):
                pos_rmse = float(np.sqrt(np.mean(position_error[trans_mask, axis_i] ** 2))) if trans_mask.any() else None
                nom_rmse = finite_rmse(nominal, trans_mask, axis_i)[0] if nominal is not None else None
                actual_rmse = finite_rmse(actual_acc_fd, trans_mask, axis_i)[0]
                residual_rmse = finite_rmse(nominal_residual, trans_mask, axis_i)[0] if nominal_residual is not None else None
                axis_row = {
                    "selection_role": row["selection_role"], "split": row["split"], "task": row["task"],
                    "source_scene_id": row["source_scene_id"], "contract_id": row["contract_id"],
                    "result_vs_B": row["result_vs_B"],
                    "paired_delta_mm": row["paired_delta_mm"], "method": row["method"],
                    "phase": label, "time_start_s": lo, "time_end_s_exclusive": hi, "axis": axis,
                    "transition_samples": int(trans_mask.sum()), "valid_inference_events": int(evt_mask.sum()),
                    "position_error_rmse_m": pos_rmse, "a_nominal_rmse_mps2": nom_rmse,
                    "a_actual_from_state_derivative_rmse_mps2": actual_rmse,
                    "a_actual_fd_minus_a_nominal_rmse_mps2": residual_rmse,
                }
                for name, label2 in (
                        ("stage1_position_pcf_a_req_mps2", "pcf_a_req"),
                        ("stage1_position_pcf_a_f_mps2", "pcf_a_f"),
                        ("stage1_position_event_raw_acceleration_mps2", "event_raw_acceleration"),
                        ("stage1_position_event_applied_acceleration_mps2", "event_applied_acceleration")):
                    vals = event_fields.get(name)
                    vmask = evt_mask
                    axis_row[f"{label2}_rmse_mps2"] = finite_rmse(vals, vmask, axis_i)[0] if vals is not None else None
                position_rows.append(axis_row)

            valid_this = event_times[evt_mask]
            def aligned_phase(name: str):
                values = event_fields.get(name)
                return values, evt_mask if values is not None else np.zeros(len(event_times), dtype=bool)
            delta_w, dw_mask = aligned_phase("stage1_position_event_weight_delta_fro")
            update_count = int(np.count_nonzero(update_flag[event_ix][evt_mask])) if update_flag is not None and len(event_ix) else None
            eta_before, eta_before_p95, _ = finite_norm_stats(event_fields.get("stage1_position_pcf_eta_before_mps"), evt_mask)
            eta_after_mean, eta_after_p95, _ = finite_norm_stats(event_fields.get("stage1_position_pcf_eta_after_mps"), evt_mask)
            raw_clip_count = int(np.count_nonzero(clip_evt[evt_mask])) if clip_evt is not None else None
            def active_count(mask_values):
                return int(np.count_nonzero(mask_values[trans_mask])) if mask_values is not None else None
            delta_values = np.asarray(delta_w).reshape(-1) if delta_w is not None else np.asarray([])
            dw_valid = delta_values[dw_mask & np.isfinite(delta_values)] if len(delta_values) == len(dw_mask) else np.asarray([])
            projection_count = (int(np.count_nonzero(projection_mask[evt_mask]))
                                if projection_evt is not None else None)
            control_rows.append({
                "selection_role": row["selection_role"], "split": row["split"], "task": row["task"],
                "source_scene_id": row["source_scene_id"], "contract_id": row["contract_id"],
                "result_vs_B": row["result_vs_B"],
                "paired_delta_mm": row["paired_delta_mm"], "method": row["method"],
                "phase": label, "time_start_s": lo, "time_end_s_exclusive": hi,
                "transitions": int(trans_mask.sum()), "valid_inference_events": int(evt_mask.sum()),
                "first_inference_s": float(valid_this[0]) if len(valid_this) else None,
                "head_update_executed_count": update_count,
                "head_update_first_s": float(update_times[0]) if update_times is not None and len(update_times) else None,
                "weight_delta_fro_mean": float(dw_valid.mean()) if len(dw_valid) else None,
                "weight_delta_fro_p95": float(np.quantile(dw_valid, 0.95)) if len(dw_valid) else None,
                "weight_delta_fro_nonzero_count": int(np.count_nonzero(dw_valid > 0)) if len(dw_valid) else None,
                "pcf_eta_before_norm_mean_mps": eta_before,
                "pcf_eta_before_norm_p95_mps": eta_before_p95,
                "pcf_eta_after_norm_mean_mps": eta_after_mean,
                "pcf_eta_after_norm_p95_mps": eta_after_p95,
                "raw_to_applied_clip_equiv_events": raw_clip_count,
                "raw_to_applied_clip_equiv_fraction": raw_clip_count / int(evt_mask.sum()) if raw_clip_count is not None and evt_mask.sum() else None,
                "raw_to_applied_clip_first_s": float(clip_times[0]) if clip_times is not None and len(clip_times) else None,
                "stage1_projection_active_events": projection_count,
                "stage1_projection_first_s": float(projection_times[0]) if projection_times is not None and len(projection_times) else None,
                "motor_saturated_transition_count": active_count(motor_active),
                "motor_saturated_transition_fraction": active_count(motor_active) / int(trans_mask.sum()) if motor_active is not None and trans_mask.sum() else None,
                "generalized_clipped_transition_count": active_count(generalized_active),
                "generalized_clipped_transition_fraction": active_count(generalized_active) / int(trans_mask.sum()) if generalized_active is not None and trans_mask.sum() else None,
                "motor_saturated_first_s": float(times[np.flatnonzero(motor_active)[0]]) if motor_active is not None and motor_active.any() else None,
                "generalized_clipped_first_s": float(times[np.flatnonzero(generalized_active)[0]]) if generalized_active is not None and generalized_active.any() else None,
            })

        w0 = field_array(log, arr_fn, "stage1_position_weight_initial")
        w0_norm = float(np.linalg.norm(np.asarray(w0, dtype=np.float64))) if w0 is not None else None
        first_raw = float(event_times[0]) if len(event_times) else None
        last_raw = float(event_times[-1]) if len(event_times) else None
        per_file = {
            "selection_role": row["selection_role"], "split": row["split"], "task": row["task"],
            "source_scene_id": row["source_scene_id"], "contract_id": row["contract_id"],
            "result_vs_B": row["result_vs_B"], "paired_delta_mm": row["paired_delta_mm"],
            "method": row["method"], "raw_path": str(path), "raw_sha256": actual_sha,
            "raw_scan_external_arrays_sha256": raw_metrics["external_arrays_sha256"],
            "transition_count": len(times), "valid_inference_event_count": len(event_ix),
            "valid_inference_first_s": first_raw, "valid_inference_last_s": last_raw,
            "time_grid_sha256": time_hash, "peak_position_error_m": float(np.nanmax(error_norm)),
            "peak_position_error_time_s": float(times[int(np.nanargmax(error_norm))]),
            "Q_0_20_m": raw_metrics["Q_0_20"], "Q_0_5_m": raw_metrics["Q_0_5"],
            "Q_5_20_m": raw_metrics["Q_5_20"],
            "runtime_W0_error": row["candidate_W0_error"],
            "logged_W0_norm": w0_norm,
            "logged_W0_nonzero": bool(w0_norm is not None and w0_norm > 0),
            "runtime_replay_status": row["candidate_replay_status"],
            "runtime_contract": row["candidate_runtime_contract"],
            "runtime_raw_replay_max": row["candidate_raw_replay_max"],
            "runtime_applied_replay_max": row["candidate_applied_replay_max"],
            "first_head_update_s": float(update_times[0]) if update_times is not None and len(update_times) else None,
            "first_raw_to_applied_clip_equiv_s": float(clip_times[0]) if clip_times is not None and len(clip_times) else None,
            "first_stage1_projection_active_s": float(projection_times[0]) if projection_times is not None and len(projection_times) else None,
            "first_motor_saturated_s": float(times[np.flatnonzero(motor_active)[0]]) if motor_active is not None and motor_active.any() else None,
            "first_generalized_clipped_s": float(times[np.flatnonzero(generalized_active)[0]]) if generalized_active is not None and generalized_active.any() else None,
            "one_second_q_m": one_second_q,
        }

    final = path.stat()
    if (before.st_size, before.st_mtime_ns) != (final.st_size, final.st_mtime_ns):
        raise RuntimeError(f"raw changed during read: {path}")
    per_file["raw_size_bytes"] = final.st_size
    return {"file": per_file, "phase_axis": position_rows, "control_phase": control_rows,
            "coverage": coverage, "phase_q": error_rmse_by_phase}


def analyze() -> None:
    whitelist_path = OUT / "raw_whitelist.csv"
    if not whitelist_path.is_file():
        raise FileNotFoundError("run --prepare first; analysis reads only raw_whitelist.csv")
    whitelist = read_csv(whitelist_path)
    if len(whitelist) != 58 or {r["split"] for r in whitelist} - {"VAL", "DEV"}:
        raise ValueError("whitelist must contain exactly 58 VAL/DEV rows")
    if any("TEST" in r["raw_path"].upper() for r in whitelist):
        raise ValueError("TEST path found in raw whitelist")
    scenes = defaultdict(set)
    for row in whitelist:
        scenes[(row["split"], row["task"], row["source_scene_id"], row["contract_id"])].add(row["method"])
    if len(scenes) != 29 or any(methods != {"B", "DSSM14"} for methods in scenes.values()):
        raise ValueError("whitelist is not 29 paired B/DSSM14 scenes")
    arr_fn, raw_score_fn = import_raw_helpers()
    results = []
    for i, row in enumerate(whitelist, 1):
        results.append(analyze_one(row, arr_fn, raw_score_fn))
        if i % 5 == 0 or i == len(whitelist):
            print(f"analyzed {i}/{len(whitelist)} whitelisted VAL/DEV raw files", flush=True)

    files = [r["file"] for r in results]
    phase_axis = [v for r in results for v in r["phase_axis"]]
    control_phase = [v for r in results for v in r["control_phase"]]
    coverage = [v for r in results for v in r["coverage"]]
    files_by_scene_method = {(r["file"]["split"], r["file"]["task"], r["file"]["source_scene_id"], r["file"]["contract_id"], r["file"]["method"]): r for r in results}
    pairs = []
    for scene_key in sorted(scenes):
        b = files_by_scene_method[(*scene_key, "B")]
        c = files_by_scene_method[(*scene_key, "DSSM14")]
        bf, cf = b["file"], c["file"]
        if bf["time_grid_sha256"] != cf["time_grid_sha256"]:
            raise ValueError(f"pair transition_time grid mismatch: {scene_key}")
        if abs(fnum(bf["Q_0_20_m"]) - fnum(cf["Q_0_20_m"]) + fnum(cf["paired_delta_mm"]) / 1000.0) > 2e-11:
            raise ValueError(f"raw-derived full Q delta differs from the score row: {scene_key}")
        first_worse_1s = next((i for i, (cq, bq) in enumerate(zip(cf["one_second_q_m"], bf["one_second_q_m"]))
                               if cq > bq + 1e-12), None)
        pair = {
            "selection_role": cf["selection_role"], "split": cf["split"], "task": cf["task"],
            "source_scene_id": cf["source_scene_id"], "contract_id": cf["contract_id"],
            "result_vs_B": cf["result_vs_B"], "paired_delta_mm": cf["paired_delta_mm"],
            "B_Q_0_20_m": bf["Q_0_20_m"], "DSSM14_Q_0_20_m": cf["Q_0_20_m"],
            "B_Q_0_5_m": bf["Q_0_5_m"], "DSSM14_Q_0_5_m": cf["Q_0_5_m"],
            "B_Q_5_20_m": bf["Q_5_20_m"], "DSSM14_Q_5_20_m": cf["Q_5_20_m"],
            "raw_derived_delta_0_5_mm": (fnum(cf["Q_0_5_m"]) - fnum(bf["Q_0_5_m"])) * 1000,
            "raw_derived_delta_5_20_mm": (fnum(cf["Q_5_20_m"]) - fnum(bf["Q_5_20_m"])) * 1000,
            "first_1s_bin_DSSM14_Q_gt_B": first_worse_1s,
            "first_1s_bin_start_s_DSSM14_Q_gt_B": first_worse_1s,
            "DSSM14_valid_inference_events": cf["valid_inference_event_count"],
            "DSSM14_W0_runtime_error": cf["runtime_W0_error"], "DSSM14_logged_W0_norm": cf["logged_W0_norm"],
            "DSSM14_runtime_replay": cf["runtime_replay_status"],
            "DSSM14_raw_replay_max": cf["runtime_raw_replay_max"],
            "DSSM14_applied_replay_max": cf["runtime_applied_replay_max"],
            "DSSM14_first_inference_s": cf["valid_inference_first_s"],
            "DSSM14_first_head_update_s": cf["first_head_update_s"],
            "DSSM14_first_raw_to_applied_clip_equiv_s": cf["first_raw_to_applied_clip_equiv_s"],
            "DSSM14_first_stage1_projection_s": cf["first_stage1_projection_active_s"],
            "DSSM14_first_motor_saturated_s": cf["first_motor_saturated_s"],
            "DSSM14_first_generalized_clipped_s": cf["first_generalized_clipped_s"],
            "B_first_motor_saturated_s": bf["first_motor_saturated_s"],
            "B_first_generalized_clipped_s": bf["first_generalized_clipped_s"],
        }
        pairs.append(pair)

    phase_index = {(r["split"], r["task"], r["source_scene_id"], r["contract_id"], r["method"], r["phase"], r["axis"]): r for r in phase_axis}
    group_axis = []
    for split in ("VAL", "DEV"):
        for task in ("FIG8_3D", "HELIX", "SQUARE"):
            loss_pairs = [p for p in pairs if p["selection_role"] == "LOSS" and p["split"] == split and p["task"] == task]
            if not loss_pairs:
                continue
            for phase in ("0_5", "5_20", "0_20", "5_10", "10_15", "15_20"):
                for axis in AXES:
                    deltas = []
                    for p in loss_pairs:
                        k = (p["split"], p["task"], p["source_scene_id"], p["contract_id"])
                        b = phase_index.get((*k, "B", phase, axis))
                        c = phase_index.get((*k, "DSSM14", phase, axis))
                        if b and c and b["position_error_rmse_m"] is not None and c["position_error_rmse_m"] is not None:
                            deltas.append((c["position_error_rmse_m"] - b["position_error_rmse_m"]) * 1000)
                    if deltas:
                        group_axis.append({"split": split, "task": task, "phase": phase, "axis": axis,
                                           "losing_scenes": len(deltas), "mean_DSSM14_minus_B_axis_RMSE_mm": float(np.mean(deltas)),
                                           "DSSM14_axis_RMSE_worse_count": sum(d > 1e-12 for d in deltas),
                                           "DSSM14_axis_RMSE_better_count": sum(d < -1e-12 for d in deltas),
                                           "max_worsening_mm": max(deltas), "min_delta_mm": min(deltas)})
    group_control = []
    for split in ("VAL", "DEV"):
        for task in ("FIG8_3D", "HELIX", "SQUARE"):
            for phase in ("0_5", "5_20", "0_20", "5_10", "10_15", "15_20"):
                scope = [r for r in control_phase if r["split"] == split and r["task"] == task and r["phase"] == phase and r["selection_role"] == "LOSS" and r["method"] == "DSSM14"]
                if not scope:
                    continue
                def mean_field(name):
                    values = [fnum(r[name]) for r in scope if r[name] not in (None, "")]
                    return float(np.mean(values)) if values else None
                group_control.append({"split": split, "task": task, "phase": phase, "losing_scenes": len(scope),
                                      "mean_valid_inference_events": mean_field("valid_inference_events"),
                                      "mean_head_update_count": mean_field("head_update_executed_count"),
                                      "mean_weight_delta_fro": mean_field("weight_delta_fro_mean"),
                                      "mean_raw_to_applied_clip_equiv_fraction": mean_field("raw_to_applied_clip_equiv_fraction"),
                                      "mean_pcf_eta_before_norm_p95_mps": mean_field("pcf_eta_before_norm_p95_mps"),
                                      "mean_pcf_eta_after_norm_p95_mps": mean_field("pcf_eta_after_norm_p95_mps"),
                                      "mean_motor_saturated_fraction": mean_field("motor_saturated_transition_fraction"),
                                      "mean_generalized_clipped_fraction": mean_field("generalized_clipped_transition_fraction")})

    phase_counts = Counter()
    for p in pairs:
        if p["selection_role"] == "LOSS":
            e, l = p["raw_derived_delta_0_5_mm"], p["raw_derived_delta_5_20_mm"]
            phase_counts["BOTH_WORSE" if e > 1e-9 and l > 1e-9 else
                         "EARLY_ONLY" if e > 1e-9 else
                         "LATE_ONLY" if l > 1e-9 else "NEITHER"] += 1
    if dict(phase_counts) != {"BOTH_WORSE": 12, "EARLY_ONLY": 4, "LATE_ONLY": 10}:
        raise ValueError(f"raw-derived 26-loss phase pattern mismatch: {dict(phase_counts)}")

    for name, rows in (("raw_file_diagnostics.csv", files), ("scene_pairs.csv", pairs),
                       ("loss_26_scene_table.csv", [p for p in pairs if p["selection_role"] == "LOSS"]),
                       ("fixed_task_win_refs.csv", [p for p in pairs if p["selection_role"] == "FIXED_TASK_WIN"]),
                       ("phase_axis_metrics.csv", phase_axis), ("control_phase_metrics.csv", control_phase),
                       ("field_coverage.csv", coverage), ("group_axis_summary.csv", group_axis),
                       ("group_control_summary.csv", group_control)):
        write_csv(OUT / name, rows)
    identity = read_json(OUT / "identity_and_scope.json")
    identity.update({
        "status": "RAW_ANALYSIS_COMPLETE",
        "actual_raw_files_read": len(files), "raw_file_sha_verified": len(files),
        "raw_scan_pure_helper_q_and_external_identity_verified": len(files),
        "pair_transition_grid_identity_verified": len(pairs),
        "runtime_replay_reused_valid_corrected_candidate_rows": sum(r["file"]["method"] == "DSSM14" for r in results),
        "raw_phase_patterns_recomputed": dict(phase_counts),
        "raw_scan_helper_source": str((BASE / "DL1009_DL1018_FULL_AUDIT_20261020_233501" / "scripts" / "raw_scan.py").resolve()),
        "raw_scan_helper_sha256": sha256(BASE / "DL1009_DL1018_FULL_AUDIT_20261020_233501" / "scripts" / "raw_scan.py"),
        "interpretation_limit": "State-velocity acceleration is a centered numerical derivative at 1 ms transition samples, with the first/last samples excluded; it is not a logged plant acceleration. Fields with no valid inference events remain unavailable. All component comparisons are descriptive associations on separate closed-loop trajectories.",
    })
    write_json(OUT / "identity_and_scope.json", identity)
    print(json.dumps({"status": identity["status"], "raw_files_read": len(files), "paired_scenes": len(pairs),
                      "loss_phase_patterns": dict(phase_counts),
                      "output_dir": str(OUT)}, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true", help="validate score/index identity and write the raw whitelist; opens no raw files")
    parser.add_argument("--analyze", action="store_true", help="analyze only paths already recorded in raw_whitelist.csv")
    args = parser.parse_args()
    if args.prepare == args.analyze:
        parser.error("choose exactly one of --prepare or --analyze")
    if args.prepare:
        prepare()
    else:
        analyze()


if __name__ == "__main__":
    main()
