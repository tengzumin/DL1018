#!/usr/bin/env python3
"""Summarize a separately audited TEST48 raw-score JSON; never opens MAT files."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from numbers import Real
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[3]
REPORTS = ROOT / "reports" / "paper_continuation_20261023"
CONTRACT = REPORTS / "TEST48_SCORE_STATISTICS_CONTRACT_v1.json"
FREEZE = REPORTS / "TEST48_SCIENTIFIC_FREEZE_v1_ZH.md"
SCORER = ROOT / "reports" / "delayed_prediction_c3_dev72_parent_20261023" / "parent_raw_metrics.py"
CONTRACT_SHA256 = "c7d2983a031b56b16950ede637cce598f6c169b1fea6dc3a092f4337489d992c"
FREEZE_SHA256 = "bbcf14230f3bc7585f68ce4baf33227e85d1f20899b9fd11d7ec95af221068f6"
SCORER_SHA256 = "c64482d0adbc4358417648ec08351bd78f1d3dbdb38950435fa71b9cb0f531b1"

METHODS = (
    "B_TRACEABLE",
    "CORRECTED_DSSM14_G12_R32",
    "CORRECTED_KAN14_G12_R32",
    "C5_M110",
    "C5_FREEZE_TRAINED_W0",
    "C5_NO_DELAYED_PREDICTION",
)
CANDIDATE = "C5_M110"
PRIMARY_Q = "Q_0_20_m"
TIE_TOL_M = 1e-12
SENSITIVITY_M = (1e-6, 1e-5)
BOOTSTRAP_REPLICATES = 10_000
BOOTSTRAP_SEED = 2026102301
CI_GROUP_ORDER = ("ALL48", "HF_W09_W14", "W15", "T1", "T2", "T3")
BANDS = (("W00_W02", 0, 2), ("W03_W05", 3, 5), ("W06_W08", 6, 8),
         ("W09_W11", 9, 11), ("W12_W14", 12, 14))
BASE_SCORE_FIELDS = (
    "Q_0_20_m", "Q_0_5_m", "Q_5_20_m",
    *(f"rmse_{axis}_{phase}_m" for phase in ("0_20", "0_5", "5_20") for axis in "xyz"),
    "peak_m", "p95_m", "motor_saturated_fraction", "generalized_clipped_fraction",
    "controller_mean_s", "controller_p50_s", "controller_p95_s", "controller_p99_s", "controller_max_s",
    "controller_over_1ms_fraction", "controller_ready_calls", "controller_nonready_calls",
    *(f"controller_ready_{stat}_s" for stat in ("mean", "p50", "p95", "p99", "max")),
    "controller_ready_over_1ms_fraction",
    *(f"controller_nonready_{stat}_s" for stat in ("mean", "p50", "p95", "p99", "max")),
    "controller_nonready_over_1ms_fraction",
)
IDENTITY_KEYS = {"scene_id", "method", "path", "sha256", "external_identity_sha256"}
QUALITY_TOKENS = ("status", "safety", "stop", "complete", "finite", "last_transition")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def verify_sources() -> dict:
    expected = ((CONTRACT, CONTRACT_SHA256), (FREEZE, FREEZE_SHA256), (SCORER, SCORER_SHA256))
    for path, digest in expected:
        if sha256_file(path) != digest:
            raise ValueError(f"Frozen source SHA mismatch: {path}")
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if (contract.get("schema") != "TEST48_SCORE_STATISTICS_CONTRACT_V1"
            or contract.get("candidate") != CANDIDATE
            or contract.get("win_tie_tolerance_m") != TIE_TOL_M
            or tuple(contract.get("strict_win_sensitivity_m", ())) != SENSITIVITY_M
            or contract.get("bootstrap", {}).get("replicates") != BOOTSTRAP_REPLICATES
            or contract.get("bootstrap", {}).get("seed") != BOOTSTRAP_SEED
            or tuple(contract.get("bootstrap", {}).get("groups", ())) != CI_GROUP_ORDER):
        raise ValueError("Contract contents do not match this frozen implementation")
    return {
        "contract_path": str(CONTRACT.relative_to(ROOT)), "contract_sha256": CONTRACT_SHA256,
        "freeze_path": str(FREEZE.relative_to(ROOT)), "freeze_sha256": FREEZE_SHA256,
        "score_source_path": str(SCORER.relative_to(ROOT)), "score_source_sha256": SCORER_SHA256,
    }


def _reject_json_constant(value: str):
    raise ValueError(f"Non-finite JSON value is not allowed: {value}")


def parse_scene_id(scene_id: str) -> tuple[str, str]:
    if "_TEST_" not in scene_id:
        raise ValueError(f"Expected a frozen TEST scene ID, got {scene_id!r}")
    tasks = re.findall(r"(?:^|_)(T[123])(?=_|$)", scene_id)
    winds = re.findall(r"(?:^|_)(W\d{2})(?=_|$)", scene_id)
    if len(tasks) != 1 or len(winds) != 1 or not 0 <= int(winds[0][1:]) <= 15:
        raise ValueError(f"Cannot uniquely read task and W00-W15 from {scene_id!r}")
    return tasks[0], winds[0]


def numeric_scalars(value, prefix: str = "") -> dict[str, float]:
    """Flatten scalar numeric metrics; lists (including per-call timing samples) are not pooled."""
    out = {}
    if isinstance(value, dict):
        for key, item in value.items():
            name = str(key)
            normalized = name.lower()
            if (normalized in IDENTITY_KEYS or normalized.endswith("_path")
                    or normalized.endswith("_sha256") or normalized in {"row_index", "scene_index", "method_order"}):
                continue
            child = f"{prefix}.{name}" if prefix else name
            out.update(numeric_scalars(item, child))
    elif isinstance(value, bool):
        out[prefix] = float(value)
    elif isinstance(value, Real):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"Non-finite metric at {prefix}")
        out[prefix] = number
    return out


def quality_scalars(value, prefix: str = "") -> dict[str, object]:
    out = {}
    if isinstance(value, dict):
        for key, item in value.items():
            name = str(key)
            child = f"{prefix}.{name}" if prefix else name
            if isinstance(item, dict):
                out.update(quality_scalars(item, child))
            elif any(token in child.lower() for token in QUALITY_TOKENS) and isinstance(item, (str, bool, int, float)):
                out[child] = item
    return out


def validate_payload(payload: dict) -> tuple[dict[str, dict], dict[str, tuple[str, str]]]:
    if payload.get("status") != "PASS_TEST48_RAW_IDENTITIES_PHYSICS_ALL_METHODS":
        raise ValueError("Input is not the required audited TEST48 raw result")
    if payload.get("TEST_accessed") is not True:
        raise ValueError("Input must attest TEST_accessed=true")
    rows = payload.get("rows")
    if not isinstance(rows, list) or len(rows) != 48 * len(METHODS):
        raise ValueError("Expected exactly 288 scene-method rows")

    by_scene = defaultdict(dict)
    metadata = {}
    external_by_scene = defaultdict(set)
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Each row must be a JSON object")
        sid, method = row.get("scene_id"), row.get("method")
        if not isinstance(sid, str) or method not in METHODS:
            raise ValueError("Each row needs a known method and string scene_id")
        task, wind = parse_scene_id(sid)
        if method in by_scene[sid]:
            raise ValueError(f"Duplicate (scene_id, method): {sid}, {method}")
        if not isinstance(row.get("path"), str) or not row["path"]:
            raise ValueError(f"Missing raw path identity for {sid}/{method}")
        if not isinstance(row.get("sha256"), str) or not row["sha256"]:
            raise ValueError(f"Missing raw SHA identity for {sid}/{method}")
        external = row.get("external_identity_sha256")
        if not isinstance(external, str) or not external:
            raise ValueError(f"Missing external-input identity for {sid}/{method}")
        external_by_scene[sid].add(external)
        for field in BASE_SCORE_FIELDS:
            value = row.get(field)
            if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(float(value)):
                raise ValueError(f"Missing or invalid {field} for {sid}/{method}")
        for field in ("controller_ready_calls", "controller_nonready_calls"):
            value = row[field]
            if float(value) < 0 or not float(value).is_integer():
                raise ValueError(f"Invalid call count {field} for {sid}/{method}")
        by_scene[sid][method] = row
        metadata[sid] = (task, wind)

    scene_ids = sorted(by_scene)
    if len(scene_ids) != 48:
        raise ValueError(f"Expected 48 unique TEST IDs, found {len(scene_ids)}")
    for sid in scene_ids:
        if set(by_scene[sid]) != set(METHODS):
            raise ValueError(f"Methods do not share the same six rows for {sid}")
        if len(external_by_scene[sid]) != 1:
            raise ValueError(f"Paired external input identity differs across methods for {sid}")
    if set(task for task, _ in metadata.values()) != {"T1", "T2", "T3"}:
        raise ValueError("Expected all three tasks T1/T2/T3")
    if set(wind for _, wind in metadata.values()) != {f"W{i:02d}" for i in range(16)}:
        raise ValueError("Expected every wind unit W00-W15")
    if len({(task, wind) for task, wind in metadata.values()}) != 48:
        raise ValueError("Expected one frozen scene for each T1/T2/T3 x W00-W15 cell")
    return by_scene, metadata


def group_members(metadata: dict[str, tuple[str, str]]) -> dict[str, list[str]]:
    ids = sorted(metadata)
    groups = {"ALL48": ids}
    for task in ("T1", "T2", "T3"):
        groups[task] = [sid for sid in ids if metadata[sid][0] == task]
    for wind_index in range(16):
        wind = f"W{wind_index:02d}"
        groups[wind] = [sid for sid in ids if metadata[sid][1] == wind]
    for name, low, high in BANDS:
        groups[name] = [sid for sid in ids if low <= int(metadata[sid][1][1:]) <= high]
    groups["HF_W09_W14"] = [sid for sid in ids if 9 <= int(metadata[sid][1][1:]) <= 14]
    empty = [name for name, members in groups.items() if not members]
    if empty:
        raise ValueError(f"Declared summary groups are empty: {empty}")
    return groups


def wlt(differences, tolerance: float) -> dict[str, int]:
    wins = sum(delta < -tolerance for delta in differences)
    losses = sum(delta > tolerance for delta in differences)
    return {"wins": int(wins), "losses": int(losses), "ties": len(differences) - int(wins) - int(losses)}


def mean_metric(values: list[float]) -> dict[str, object]:
    return {"n": len(values), "mean": math.fsum(values) / len(values) if values else None}


def group_summary(group_ids: list[str], by_scene: dict, metrics_by_row: dict, metadata: dict) -> dict:
    names = sorted({name for sid in group_ids for method in METHODS for name in metrics_by_row[sid][method]})
    result = {"n_scenes": len(group_ids), "metrics_by_method": {}, "C5_vs": {}}
    for method in METHODS:
        method_metrics = {}
        for name in names:
            values = [metrics_by_row[sid][method][name] for sid in group_ids if name in metrics_by_row[sid][method]]
            method_metrics[name] = mean_metric(values)
        result["metrics_by_method"][method] = method_metrics
    for other in METHODS:
        if other == CANDIDATE:
            continue
        deltas = [float(by_scene[sid][CANDIDATE][PRIMARY_Q]) - float(by_scene[sid][other][PRIMARY_Q]) for sid in group_ids]
        result["C5_vs"][other] = {
            "mean_delta_Q_0_20_m": math.fsum(deltas) / len(deltas),
            "wlt_1e-12_m": wlt(deltas, TIE_TOL_M),
            "sensitivity_wlt": {f"{threshold:.0e}_m": wlt(deltas, threshold) for threshold in SENSITIVITY_M},
        }
    return result


def bootstrap_indices(rng: np.random.Generator, group_name: str, n_scenes: int) -> tuple[np.ndarray, str]:
    indices = rng.integers(0, n_scenes, size=(BOOTSTRAP_REPLICATES, n_scenes), dtype=np.int64)
    canonical = np.ascontiguousarray(indices, dtype="<i8")
    digest = hashlib.sha256(
        group_name.encode("utf-8") + b"\0" + str(canonical.shape).encode("ascii") + b"\0<i8\0" + canonical.tobytes(order="C")
    ).hexdigest()
    return indices, digest


def bootstrap_cis(by_scene: dict, groups: dict) -> dict:
    rng = np.random.Generator(np.random.PCG64(BOOTSTRAP_SEED))
    result = {}
    for group_name in CI_GROUP_ORDER:
        ids = groups[group_name]
        indices, index_sha = bootstrap_indices(rng, group_name, len(ids))
        group_result = {
            "n_scenes": len(ids),
            "index_sha256": index_sha,
            "indices_saved": False,
            "index_encoding": "group_name\\0shape\\0<i8\\0C-order little-endian int64 bytes",
            "contrasts_C5_minus_other": {},
        }
        for other in METHODS:
            if other == CANDIDATE:
                continue
            delta = np.asarray([by_scene[sid][CANDIDATE][PRIMARY_Q] - by_scene[sid][other][PRIMARY_Q] for sid in ids], dtype=np.float64)
            bootstrap_means = delta[indices].mean(axis=1)
            low, high = np.quantile(bootstrap_means, [0.025, 0.975], method="linear")
            group_result["contrasts_C5_minus_other"][other] = {
                "mean_delta_Q_0_20_m": math.fsum(float(x) for x in delta) / len(delta),
                "ci95_m": [float(low), float(high)],
            }
        result[group_name] = group_result
    return result


def _quality_failure(key: str, value) -> bool:
    name = key.lower()
    if value is None:
        return False
    if "stop" in name or "safety" in name:
        if isinstance(value, str):
            return value.strip().lower() not in {"", "none", "null", "false", "0", "no"}
        return bool(value)
    if "complete" in name:
        if isinstance(value, str):
            return value.strip().lower() not in {"complete", "completed", "true", "pass", "ok", "yes", "1"}
        return not bool(value)
    return False


def integrity_report(by_scene: dict) -> dict:
    fields = set()
    statuses = defaultdict(Counter)
    stop_rows, incomplete_rows = [], []
    for sid, methods in by_scene.items():
        for method, row in methods.items():
            quality = quality_scalars(row)
            fields.update(quality)
            for key, value in quality.items():
                if key.lower().endswith("status") or ".status" in key.lower():
                    statuses[key][str(value)] += 1
            if any(("stop" in key.lower() or "safety" in key.lower()) and _quality_failure(key, value)
                   for key, value in quality.items()):
                stop_rows.append({"scene_id": sid, "method": method, "fields": quality})
            if any("complete" in key.lower() and _quality_failure(key, value) for key, value in quality.items()):
                incomplete_rows.append({"scene_id": sid, "method": method, "fields": quality})
    return {
        "quality_fields_present": sorted(fields),
        "row_status_counts": {key: dict(sorted(counts.items())) for key, counts in statuses.items()},
        "safety_stop_rows": stop_rows,
        "incomplete_rows": incomplete_rows,
        "note": "Reported from supplied row fields; the audited-input status is required separately. No new attitude-improvement gate is applied.",
    }


def analyze_payload(payload: dict, input_sha256: str, source_info: dict) -> dict:
    by_scene, metadata = validate_payload(payload)
    groups = group_members(metadata)
    metrics_by_row = {sid: {method: numeric_scalars(row) for method, row in methods.items()} for sid, methods in by_scene.items()}
    metric_schemas = {tuple(sorted(metrics_by_row[sid][method])) for sid in by_scene for method in METHODS}
    if len(metric_schemas) != 1:
        raise ValueError("Numeric metric fields are incomplete or inconsistent across the 288 rows")
    group_stats = {
        name: group_summary(ids, by_scene, metrics_by_row, metadata)
        for name, ids in groups.items()
    }

    per_scene = []
    for sid in sorted(by_scene):
        row = {"scene_id": sid, "task": metadata[sid][0], "wind": metadata[sid][1], "metrics_by_method": {}, "identity_by_method": {}}
        for method in METHODS:
            scored = by_scene[sid][method]
            row["metrics_by_method"][method] = metrics_by_row[sid][method]
            row["identity_by_method"][method] = {
                key: scored[key] for key in ("path", "sha256", "external_identity_sha256")
            }
        per_scene.append(row)

    contrasts = {}
    for other in METHODS:
        if other == CANDIDATE:
            continue
        scene_rows = []
        losses = []
        deltas = []
        for sid in sorted(by_scene):
            c5_q = float(by_scene[sid][CANDIDATE][PRIMARY_Q])
            other_q = float(by_scene[sid][other][PRIMARY_Q])
            delta = c5_q - other_q
            delta_wlt = wlt([delta], TIE_TOL_M)
            item = {
                "scene_id": sid, "task": metadata[sid][0], "wind": metadata[sid][1],
                "Q_C5_m": c5_q, "Q_other_m": other_q, "C5_minus_other_m": delta,
                "wlt_1e-12_m": delta_wlt,
                "sensitivity_wlt": {f"{threshold:.0e}_m": wlt([delta], threshold) for threshold in SENSITIVITY_M},
            }
            scene_rows.append(item)
            deltas.append(delta)
            if delta_wlt["losses"]:
                losses.append({"scene_id": sid, "task": metadata[sid][0], "wind": metadata[sid][1],
                               "C5_minus_other_m": delta, "Q_C5_m": c5_q, "Q_other_m": other_q})
        contrasts[other] = {
            "mean_delta_Q_0_20_m": math.fsum(deltas) / len(deltas),
            "wlt_1e-12_m": wlt(deltas, TIE_TOL_M),
            "sensitivity_wlt": {f"{threshold:.0e}_m": wlt(deltas, threshold) for threshold in SENSITIVITY_M},
            "all_48_per_scene_differences": scene_rows,
            "all_C5_losses_at_1e-12_m": losses,
        }

    all_q = group_stats["ALL48"]["metrics_by_method"]
    hf_q = group_stats["HF_W09_W14"]["metrics_by_method"]
    w15_q = group_stats["W15"]["metrics_by_method"]
    c5_vs_b_wins = contrasts["B_TRACEABLE"]["wlt_1e-12_m"]["wins"]
    acceptance_metrics = {
        "c5_wins_vs_b_at_least_41_of_48": {"observed": c5_vs_b_wins, "threshold": 41, "met": c5_vs_b_wins >= 41},
        "all48_mean_Q_strictly_below_B": {
            "C5_m": all_q[CANDIDATE][PRIMARY_Q]["mean"], "B_m": all_q["B_TRACEABLE"][PRIMARY_Q]["mean"],
            "met": all_q[CANDIDATE][PRIMARY_Q]["mean"] < all_q["B_TRACEABLE"][PRIMARY_Q]["mean"],
        },
        "HF_mean_Q_no_larger_than_B": {
            "C5_m": hf_q[CANDIDATE][PRIMARY_Q]["mean"], "B_m": hf_q["B_TRACEABLE"][PRIMARY_Q]["mean"],
            "met": hf_q[CANDIDATE][PRIMARY_Q]["mean"] <= hf_q["B_TRACEABLE"][PRIMARY_Q]["mean"],
        },
        "W15_mean_Q_no_larger_than_B": {
            "C5_m": w15_q[CANDIDATE][PRIMARY_Q]["mean"], "B_m": w15_q["B_TRACEABLE"][PRIMARY_Q]["mean"],
            "met": w15_q[CANDIDATE][PRIMARY_Q]["mean"] <= w15_q["B_TRACEABLE"][PRIMARY_Q]["mean"],
        },
        "paper_gate_or_goal_decision": "NOT_AUTOMATED_BY_STATISTICS_SCRIPT",
    }

    return {
        "schema": "TEST48_DESCRIPTIVE_STATISTICS_V1",
        "analysis_status": "COMPUTED_ONLY_FROM_REQUIRED_AUDITED_INPUT",
        "input_status": payload["status"],
        "TEST_accessed": True,
        "source": {
            **source_info,
            "input_json_sha256": input_sha256,
            "statistics_script_sha256": sha256_file(Path(__file__).resolve()),
            "numpy_version": np.__version__,
        },
        "methods_order": list(METHODS),
        "candidate": CANDIDATE,
        "primary_difference_definition": "C5_M110 Q_0_20_m minus comparator Q_0_20_m; negative favors C5.",
        "scene_equal_weighting": "Each TEST scene contributes one score row per method; no time windows or raw samples are pooled.",
        "tie_tolerance_m": TIE_TOL_M,
        "sensitivity_tolerances_m": list(SENSITIVITY_M),
        "summary_groups": group_stats,
        "C5_vs_other_methods": contrasts,
        "per_scene_metrics_and_raw_identities": per_scene,
        "bootstrap": {
            "replicates": BOOTSTRAP_REPLICATES,
            "seed": BOOTSTRAP_SEED,
            "unit": "paired physical TEST scene sampled with replacement within group",
            "common_indices_across_method_contrasts": True,
            "group_order": list(CI_GROUP_ORDER),
            "interval": "numpy.quantile of scene-equal mean paired Q differences at 0.025/0.975, method=linear",
            "scope": "Descriptive fixed-simulation-design intervals only; no multiplicity adjustment or cross-training-seed inference.",
            "confidence_intervals": bootstrap_cis(by_scene, groups),
        },
        "run_integrity": integrity_report(by_scene),
        "performance_checks_not_a_gate_decision": acceptance_metrics,
        "timing_note": "Required per-scene timing fields include controller mean/p50/p95/p99/max and over-1ms fraction, ready/nonready call counts and mean/p50/p95/p99/max and over-1ms fractions. JIT effects are retained upstream; this script does not trim timed calls or pool per-call/window samples.",
        "selection_or_tuning_from_TEST": False,
        "paper_gate_or_goal_complete": False,
    }


def self_check() -> dict:
    """Small synthetic-only checks for equal weighting, W/L/T, and common bootstrap hashes."""
    differences = [-2e-6, 0.0, 2e-6, -2e-5, 2e-5]
    assert wlt(differences, TIE_TOL_M) == {"wins": 2, "losses": 2, "ties": 1}
    assert wlt(differences, 1e-6) == {"wins": 2, "losses": 2, "ties": 1}
    assert wlt(differences, 1e-5) == {"wins": 1, "losses": 1, "ties": 3}
    assert mean_metric([1.0, 3.0]) == {"n": 2, "mean": 2.0}
    rng_a = np.random.Generator(np.random.PCG64(BOOTSTRAP_SEED))
    rng_b = np.random.Generator(np.random.PCG64(BOOTSTRAP_SEED))
    indices_a, hash_a = bootstrap_indices(rng_a, "DEV_OR_SYNTHETIC_SELF_CHECK", 5)
    indices_b, hash_b = bootstrap_indices(rng_b, "DEV_OR_SYNTHETIC_SELF_CHECK", 5)
    assert indices_a.shape == (BOOTSTRAP_REPLICATES, 5) and hash_a == hash_b
    return {
        "schema": "DEV_OR_SYNTHETIC_SELF_CHECK_V1",
        "status": "DEV_OR_SYNTHETIC_SELF_CHECK",
        "TEST_accessed": False,
        "synthetic_only": True,
        "checks": {
            "scene_equal_mean_of_two_scores": 2.0,
            "wlt_at_1e-12_m": wlt(differences, TIE_TOL_M),
            "wlt_at_1e-6_m": wlt(differences, 1e-6),
            "wlt_at_1e-5_m": wlt(differences, 1e-5),
            "bootstrap_shape": list(indices_a.shape),
            "deterministic_index_sha256": hash_a,
        },
        "note": "No real TEST scene IDs, raw files, or measured values were read or generated.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-json", type=Path, required=True, help="Root-audited TEST48 raw score JSON")
    parser.add_argument("--output-json", type=Path, required=True, help="New statistics JSON path; existing files are refused")
    args = parser.parse_args()
    if not args.input_json.is_file():
        raise SystemExit(f"Missing input JSON: {args.input_json}")
    try:
        source_info = verify_sources()
        raw_bytes = args.input_json.read_bytes()
        payload = json.loads(raw_bytes.decode("utf-8-sig"), parse_constant=_reject_json_constant)
        result = analyze_payload(payload, sha256_bytes(raw_bytes), source_info)
        serialized = json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
        with args.output_json.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(serialized)
    except (OSError, ValueError, TypeError, KeyError) as error:
        raise SystemExit(f"Statistics refused: {error}") from error
    print(json.dumps({"analysis_status": result["analysis_status"], "rows": 288,
                      "output_json": str(args.output_json), "paper_gate_or_goal_decision": "NOT_AUTOMATED"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
