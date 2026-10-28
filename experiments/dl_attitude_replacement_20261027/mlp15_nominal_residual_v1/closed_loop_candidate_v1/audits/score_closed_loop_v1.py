"""Score the 12-scene physical-residual candidate against WN12-locked B/C5 raws."""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path

import h5py
import numpy as np

HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
ROOT = HERE.parents[4]
WN12 = ROOT / "experiments/dl_attitude_replacement_20261027/task_attitude_filter_wn12_hf_screen_v1"
METRIC_PATH = ROOT / "experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_full72_v1/audits/score_full72_candidate_v1.py"
OUTPUTS = (HERE / "CLOSED_LOOP_SCORE_v1.json", HERE / "CLOSED_LOOP_SCORE_v1.csv", HERE / "CLOSED_LOOP_SCORE_v1.md")
WIN_TOL = 1e-12

spec = importlib.util.spec_from_file_location("frozen_closed_loop_metrics", METRIC_PATH)
if spec is None or spec.loader is None:
    raise ImportError(METRIC_PATH)
metrics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metrics)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def readj(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def require(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)


def bound(path: Path, expected: str, label: str) -> str:
    require(path.is_file(), f"Missing {label}: {path}")
    actual = sha(path)
    require(actual.lower() == str(expected).lower(), f"{label} SHA-256 mismatch: {path}")
    return actual


def rooted(path_value: str | Path) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else ROOT / path


def path_key(path: str | Path) -> str:
    return os.path.normcase(os.path.normpath(str(Path(path).resolve())))


def h5text(dataset) -> str:
    value = np.asarray(dataset[()])
    if value.dtype.kind in "ui":
        return "".join(chr(int(c)) for c in value.reshape(-1) if int(c))
    if value.dtype.kind == "S":
        return b"".join(value.reshape(-1).tolist()).decode("utf-8").rstrip("\x00")
    if value.dtype.kind == "U":
        return "".join(value.reshape(-1).tolist()).rstrip("\x00")
    if value.shape == ():
        return str(value.item())
    raise ValueError(f"Unsupported MATLAB string dtype: {value.dtype}")


def h5bool(dataset) -> bool:
    return bool(np.asarray(dataset[()]).astype(bool).any())


def read_raw_identity(path: Path) -> dict:
    with h5py.File(path, "r") as f:
        require("scene/scene_id" in f and "runIdentity" in f, f"Missing scene/run identity in {path}")
        scene_id = h5text(f["scene/scene_id"])
        ident = f["runIdentity"]
        keys = ("scene_id", "attitude_arm", "geometry_arm", "release_sha256", "scene_payload_sha256",
                "b_raw_sha256", "c5_input_lock_sha256", "c5_snapshot_sha256", "position_model_sha256",
                "physical_residual_model_sha256", "physical_residual_target_contract")
        result = {key: h5text(ident[key]) for key in keys if key in ident}
        result["test_data_read"] = h5bool(ident["test_data_read"]) if "test_data_read" in ident else None
    result["embedded_scene_id"] = scene_id
    return result


def metrics_match(actual: dict, expected: dict, label: str) -> float:
    diffs = [abs(float(actual[key]) - float(expected[key])) for key in metrics.MAIN]
    require(max(diffs) <= 1e-12, f"{label} metric self-check differs from bound score: {diffs}")
    return max(diffs)


def validate_baseline_bindings(release: dict):
    manifest_path = WN12 / "MANIFEST.json"
    screen_path = WN12 / "SCREEN12_RESULTS_v1.json"
    manifest_sha, screen_sha = sha(manifest_path), sha(screen_path)
    manifest, screen = readj(manifest_path), readj(screen_path)
    require(manifest.get("status") == "PASS_READ_ONLY_VALIDATION_BINDINGS" and manifest.get("TEST_read") is False,
            "WN12 manifest is not a valid TEST-free baseline binding")
    records = manifest.get("records", [])
    ids = [row.get("scene_id") for row in records]
    require(len(records) == 12 and len(set(ids)) == 12 and all("TEST" not in sid.upper() for sid in ids),
            "WN12 manifest must bind exactly 12 unique non-TEST scenes")
    require(release.get("authorized_scenes") == ids and release.get("authorized_Plant_calls") == 12,
            "candidate release cohort/order differs from WN12 baseline cohort")
    require(screen.get("screen_scene_ids") == ids and len(screen.get("scenes", [])) == 12,
            "WN12 score scene order differs from its baseline manifest")
    require(screen.get("metric_scorer_path") == str(METRIC_PATH) and
            screen.get("metric_scorer_sha256", "").lower() == sha(METRIC_PATH).lower(),
            "WN12 score was not produced by the frozen metric scorer")
    constants_path = rooted(screen["metric_constants_path"])
    constants_sha = bound(constants_path, screen["metric_constants_sha256"], "WN12 metric constants")
    gravity = float(screen["metric_constants"]["gravity_mps2"])
    max_tilt = float(screen["metric_constants"]["max_tilt_rad"])

    parent_manifest_path = rooted(manifest["parent_manifest_path"])
    parent_score_path = rooted(manifest["parent_score_path"])
    bound(parent_manifest_path, manifest["parent_manifest_sha256"], "WN12 parent manifest")
    bound(parent_score_path, manifest["parent_score_sha256"], "WN12 parent score")
    parent_manifest, parent_score = readj(parent_manifest_path), readj(parent_score_path)
    require(parent_score.get("input_bindings", {}).get("manifest_sha256", "").lower() ==
            manifest["parent_manifest_sha256"].lower(), "WN12 parent score/manifest binding mismatch")
    parent_records = {r["scene_id"]: r for r in parent_manifest.get("records", [])}
    parent_scores = {r["scene_id"]: r for r in parent_score.get("rows", [])}
    screen_rows = {r["scene_id"]: r for r in screen["scenes"]}
    require(set(ids) <= set(parent_records) and set(ids) <= set(parent_scores),
            "WN12 cohort is missing from its bound parent data/score")
    bound_records = {}
    check_diffs = []
    for row in records:
        sid = row["scene_id"]
        parent = parent_records[sid]
        parent_score_row = parent_scores[sid]
        screen_row = screen_rows[sid]
        for method, pfx in (("B", "b"), ("C5", "c5")):
            raw_path = rooted(row[f"{pfx}_raw_path"])
            status_path = rooted(row[f"{pfx}_status_path"])
            raw_hash = bound(raw_path, row[f"{pfx}_raw_sha256"], f"{sid} {method} raw")
            status_hash = bound(status_path, row[f"{pfx}_status_sha256"], f"{sid} {method} status")
            require(path_key(raw_path) == path_key(parent[f"{pfx}_raw_path"]) and
                    raw_hash.lower() == parent[f"{pfx}_raw_sha256"].lower() and
                    path_key(status_path) == path_key(parent[f"{pfx}_status_path"]) and
                    status_hash.lower() == parent[f"{pfx}_status_sha256"].lower(),
                    f"{sid} {method} raw/status differs from bound parent manifest")
            identity = read_raw_identity(raw_path)
            require(identity["embedded_scene_id"] == sid, f"{sid} {method} raw scene identity mismatch")
            actual = metrics.score_raw(raw_path, gravity, max_tilt)
            expected_parent = parent_score_row["methods"][method]
            expected_screen = screen_row["scores"][method]
            check_diffs.append(metrics_match(actual, expected_parent, f"{sid} {method} parent score"))
            check_diffs.append(metrics_match(actual, expected_screen, f"{sid} {method} WN12 score"))
            bound_records.setdefault(sid, {})[method] = {
                "raw_path": str(raw_path), "raw_sha256": raw_hash,
                "status_path": str(status_path), "status_sha256": status_hash,
                "metrics": actual,
            }

    return {
        "manifest_path": str(manifest_path), "manifest_sha256": manifest_sha,
        "screen_score_path": str(screen_path), "screen_score_sha256": screen_sha,
        "parent_manifest_path": str(parent_manifest_path), "parent_manifest_sha256": sha(parent_manifest_path),
        "parent_score_path": str(parent_score_path), "parent_score_sha256": sha(parent_score_path),
        "metric_scorer_path": str(METRIC_PATH), "metric_scorer_sha256": sha(METRIC_PATH),
        "metric_constants_path": str(constants_path), "metric_constants_sha256": constants_sha,
        "gravity_mps2": gravity, "max_tilt_rad": max_tilt,
        "scene_ids": ids, "records": bound_records,
        "baseline_score_self_check": {
            "status": "PASS_FROZEN_METRICS_MATCH_PARENT_AND_WN12_B_C5_SCORES",
            "max_abs_metric_difference": max(check_diffs, default=0.0),
        },
        "source_limitations": {
            "B_historical_runtime_identity_gap_closed": False,
            "C5_parent_raw_audit_statuses": {r["scene_id"]: r.get("C5_parent_audit_status") for r in records},
            "WN12_screen_status": screen.get("status"),
            "WN12_screen_failure_reason": screen.get("limitations"),
        },
    }


def discover_candidate(sid: str, payload_sha: str, b_sha: str, release: dict,
                       release_sha: str, expected_baseline_identity: dict) -> dict:
    scene_root = STUDY / "runs" / sid
    statuses = sorted(scene_root.rglob("run_status.json")) if scene_root.exists() else []
    raws = sorted(scene_root.rglob("raw_run.mat")) if scene_root.exists() else []
    if not statuses and not raws:
        return {"status": "PENDING_NO_ATTEMPT", "metrics": None}
    pairs = []
    for status_path in statuses:
        raw_path = status_path.with_name("raw_run.mat")
        if raw_path.exists():
            pairs.append((status_path, raw_path))
    if len(pairs) != 1 or len(statuses) != 1 or len(raws) != 1:
        return {"status": "PENDING_ATTEMPT_NOT_UNIQUE", "status_paths": [str(p) for p in statuses],
                "raw_paths": [str(p) for p in raws], "metrics": None}
    status_path, raw_path = pairs[0]
    status, start = readj(status_path), readj(status_path.with_name("run_start.json"))
    require(status.get("scene_id") == sid and start.get("scene_id") == sid,
            f"Candidate run status/start scene mismatch for {sid}")
    require(status.get("state") == "COMPLETED" and status.get("status_value") == "STABLE" and
            status.get("plant_calls") == 1 and status.get("transitions") == 20000 and
            status.get("state_samples") == 20001 and status.get("test_data_read") is False,
            f"Candidate run is not a complete stable 20000/20001 TEST-free result: {sid}")
    require(path_key(status.get("raw_path", "")) == path_key(raw_path), f"Candidate raw/status path mismatch: {sid}")
    raw_hash = bound(raw_path, status.get("raw_sha256", ""), f"candidate raw {sid}")
    run_start_sha = sha(status_path.with_name("run_start.json"))
    require(start.get("physical_residual_model_sha256", "").lower() == release["model_sha256"].lower() and
            status.get("physical_residual_model_sha256", "").lower() == release["model_sha256"].lower(),
            f"Candidate physical-residual model identity mismatch: {sid}")
    require(start.get("scene_payload_sha256", "").lower() == payload_sha.lower() and
            status.get("scene_payload_sha256", "").lower() == payload_sha.lower(),
            f"Candidate payload SHA mismatch: {sid}")
    require(start.get("b_raw_sha256", "").lower() == b_sha.lower(), f"Candidate B-input SHA mismatch: {sid}")
    for key in ("c5_input_lock_sha256", "c5_snapshot_sha256", "position_model_sha256"):
        expected = expected_baseline_identity.get(key)
        if expected:
            require(start.get(key, "").lower() == expected.lower(), f"Candidate {key} mismatch: {sid}")
    ident = read_raw_identity(raw_path)
    require(ident.get("embedded_scene_id") == sid and ident.get("scene_id") == sid,
            f"Candidate raw embedded scene ID mismatch: {sid}")
    require(ident.get("physical_residual_model_sha256", "").lower() == release["model_sha256"].lower() and
            ident.get("scene_payload_sha256", "").lower() == payload_sha.lower() and
            ident.get("b_raw_sha256", "").lower() == b_sha.lower() and
            ident.get("test_data_read") is False,
            f"Candidate raw embedded identity/hash mismatch: {sid}")
    require(ident.get("release_sha256", "").lower() == start.get("release_sha256", "").lower(),
            f"Candidate raw/run-start release binding mismatch: {sid}")
    require(ident.get("attitude_arm") == release.get("candidate_arm_id") and
            ident.get("geometry_arm") == release.get("geometry_arm"),
            f"Candidate raw arm mismatch: {sid}")
    result = metrics.score_raw(raw_path, 9.8, np.pi / 6)
    # Use the exact constants locked by the WN12 audit (9.8 m/s^2, 30 degrees).
    return {"status": "SCORED", "raw_path": str(raw_path), "raw_sha256": raw_hash,
            "status_path": str(status_path), "status_sha256": sha(status_path),
            "run_start_path": str(status_path.with_name("run_start.json")), "run_start_sha256": run_start_sha,
            "run_start_release_sha256": start.get("release_sha256"), "raw_identity": ident,
            "metrics": result}


def compare(candidate: dict, baseline: dict) -> dict:
    result = {}
    for key in metrics.MAIN:
        delta = candidate[key] - baseline[key]
        result[key] = {"candidate_minus_baseline": delta,
                       "outcome": "WIN" if delta < -WIN_TOL else ("LOSS" if delta > WIN_TOL else "TIE")}
    return result


def summary(rows: list[dict], method: str) -> dict:
    if not rows:
        return {key: None for key in metrics.MAIN}
    return {key: float(np.mean([r["methods"][method][key] for r in rows])) for key in metrics.MAIN}


def aggregate(ready_rows: list[dict]) -> dict:
    groups = {"ALL12": ready_rows}
    for group in ("HF_W09_W14", "W15", "W00_W08"):
        groups[group] = [r for r in ready_rows if metrics.classify(r["scene_id"], r["source_split"])[2] == group]
    groups["NO_WIND_W00"] = [r for r in ready_rows if r["wind_index"] == 0]
    groups["LOW_WIND_W01_W08"] = [r for r in ready_rows if 1 <= r["wind_index"] <= 8]
    by_group = {name: {"scene_count": len(items),
                       "macro_scene_rmse": {m: summary(items, m) for m in ("Candidate", "B", "C5")}}
                for name, items in groups.items()}
    wins = {}
    for baseline in ("B", "C5"):
        wins[baseline] = {metric: {outcome: sum(r["candidate_vs"][baseline][metric]["outcome"] == outcome for r in ready_rows)
                                  for outcome in ("WIN", "TIE", "LOSS")} for metric in metrics.MAIN}
    safety = {}
    for method in ("Candidate", "B", "C5"):
        safety[method] = {}
        for key in ("motor_saturation_samples", "generalized_clip_samples", "tilt_limited_samples",
                    "attitude_head_projection_samples", "attitude_head_output_saturated_samples"):
            values = [r["methods"][method]["safety"].get(key) for r in ready_rows]
            safety[method][key] = None if any(v is None for v in values) else int(sum(values))
    macro_percent_vs_baseline = {}
    for group, data in by_group.items():
        macro_percent_vs_baseline[group] = {}
        for baseline in ("B", "C5"):
            macro_percent_vs_baseline[group][baseline] = {
                key: (None if data["scene_count"] == 0 or data["macro_scene_rmse"][baseline][key] == 0 else
                      100 * (data["macro_scene_rmse"]["Candidate"][key] - data["macro_scene_rmse"][baseline][key]) /
                      data["macro_scene_rmse"][baseline][key])
                for key in metrics.MAIN
            }
    return {"scene_count": len(ready_rows), "group_macro_scene_rmse": by_group,
            "macro_percent_vs_baseline": macro_percent_vs_baseline,
            "scene_wins": wins, "safety_sample_totals": safety}


def write_outputs(result: dict, csv_rows: list[dict]) -> None:
    json_path, csv_path, md_path = OUTPUTS
    if any(p.exists() for p in OUTPUTS):
        require(all(p.exists() for p in OUTPUTS), "partial existing score output set; refusing overwrite")
        prior = readj(json_path)
        old_hashes = prior.get("output_sha256", {})
        prior_is_same_audit = (prior.get("schema") == result["schema"] and
                               prior.get("release_sha256_current") == result["release_sha256_current"] and
                               prior.get("model_sha256") == result["model_sha256"] and
                               prior.get("metric_functions_sha256") == result["metric_functions_sha256"] and
                               old_hashes.get(csv_path.name) == sha(csv_path) and
                               old_hashes.get(md_path.name) == sha(md_path))
        require(str(prior.get("status", "")).startswith("PENDING_") or prior_is_same_audit,
                "existing score outputs are unrelated or were edited; refusing overwrite")
    fields = list(csv_rows[0]) if csv_rows else ["scene_id", "candidate_status"]
    for path in OUTPUTS:
        tmp = path.with_name(path.name + ".tmp")
        require(not tmp.exists(), f"temporary output exists: {tmp}")
    csv_tmp = csv_path.with_name(csv_path.name + ".tmp")
    with csv_tmp.open("x", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(csv_rows)
    md_tmp = md_path.with_name(md_path.name + ".tmp")
    lines = ["# Closed-loop candidate paired score", ""]
    if result["status"].startswith("PENDING_"):
        lines += [f"**Pending:** candidate raw is ready for {result['candidate_scene_count']}/12 scenes; no 12-scene macro or win/loss conclusion is reported.",
                  f"Missing or incomplete scenes: {', '.join(result['candidate_pending_scene_ids']) or 'none'}.", ""]
    else:
        lines += ["Candidate, B, and C5 were scored on the same 12 authorized scenes.", ""]
    lines += ["## Paired metrics", "", "| Cohort | N | Method | Q (m) | Task SO(3) (rad) | Inner SO(3) (rad) |",
              "|---|---:|---|---:|---:|---:|"]
    if result.get("aggregate"):
        for group, data in result["aggregate"]["group_macro_scene_rmse"].items():
            for method, value in data["macro_scene_rmse"].items():
                if data["scene_count"]:
                    lines.append(f"| {group} | {data['scene_count']} | {method} | {value['Q_m']:.9f} | {value['task_SO3_rad']:.9f} | {value['inner_SO3_rad']:.9f} |")
                else:
                    lines.append(f"| {group} | 0 | {method} | not sampled | not sampled | not sampled |")
        lines += ["", "Macro percent change of Candidate versus baseline (positive means higher error):", "",
                  "| Cohort | Baseline | Q | Task SO(3) | Inner SO(3) |", "|---|---|---:|---:|---:|"]
        for group, comparisons in result["aggregate"]["macro_percent_vs_baseline"].items():
            for baseline, values in comparisons.items():
                cells = ["not sampled" if value is None else f"{value:+.2f}%" for value in values.values()]
                lines.append(f"| {group} | {baseline} | " + " | ".join(cells) + " |")
        hf = result["aggregate"]["group_macro_scene_rmse"]["HF_W09_W14"]
        hf_task_pct = result["aggregate"]["macro_percent_vs_baseline"]["HF_W09_W14"]["B"]["task_SO3_rad"]
        hf_task_wins = sum(r["candidate_vs"]["B"]["task_SO3_rad"]["outcome"] == "WIN"
                           for r in result["rows"]
                           if metrics.classify(r["scene_id"], r["source_split"])[2] == "HF_W09_W14")
        all_q_c5_pct = result["aggregate"]["macro_percent_vs_baseline"]["ALL12"]["C5"]["Q_m"]
        lines += ["", f"Evidence conclusion: HF task attitude is {hf_task_pct:+.2f}% versus B ({hf_task_wins}/{hf['scene_count']} scene wins); ALL12 position error is {all_q_c5_pct:+.2f}% versus C5. This development screen misses the high-frequency task-attitude target; overall gains versus B do not establish a pass.", ""]
        lines += ["", "## Candidate scene wins", "", "| Baseline | Metric | Win | Tie | Loss |", "|---|---|---:|---:|---:|"]
        for baseline, values in result["aggregate"]["scene_wins"].items():
            for metric, count in values.items():
                lines.append(f"| {baseline} | {metric} | {count['WIN']} | {count['TIE']} | {count['LOSS']} |")
        lines += ["", "## Per-scene paired outcomes", "", "| Scene | B: Q | B: task | B: inner | C5: Q | C5: task | C5: inner |",
                  "|---|---|---|---|---|---|---|"]
        for row in result["rows"]:
            if "candidate_vs" not in row:
                continue
            cells = [row["scene_id"]]
            for baseline in ("B", "C5"):
                for metric in metrics.MAIN:
                    item = row["candidate_vs"][baseline][metric]
                    cells.append(f"{item['outcome']} ({item['candidate_minus_baseline']:+.6f})")
            lines.append("| " + " | ".join(cells) + " |")
        lines += ["", f"Safety sample totals: `{json.dumps(result['aggregate']['safety_sample_totals'], ensure_ascii=False)}`.", ""]
    lines += ["Metric functions: frozen `score_full72_candidate_v1.py`; Q is position-error RMS, task/inner attitude use SO(3) geodesic RMSE.",
              "B/C5 raw paths and hashes are inherited from WN12's bound manifest and parent score. B historical runtime-identity limitation remains.",
              "Only DEV/VAL scenes in the 12-scene authorization are used; TEST is not read.",
              "No W00 no-wind scene is in this cohort; the W00-W08 low-wind cohort contains only the listed wind indices.", ""]
    md_tmp.write_text("\n".join(lines), encoding="utf-8")
    result["output_sha256"] = {csv_path.name: sha(csv_tmp), md_path.name: sha(md_tmp)}
    json_tmp = json_path.with_name(json_path.name + ".tmp")
    json_tmp.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(csv_tmp, csv_path)
    os.replace(md_tmp, md_path)
    os.replace(json_tmp, json_path)


def main() -> None:
    release_path = STUDY / "RELEASE.json"
    release = readj(release_path)
    require(release.get("status") == "RELEASED" and release.get("TEST_read") is False and
            release.get("model_sha256") and release.get("authorized_Plant_calls") == 12,
            "candidate release is not the expected 12-scene TEST-free release")
    model_path = rooted(release["model_path"])
    bound(model_path, release["model_sha256"], "physical-residual model")
    release_sha = sha(release_path)
    baselines = validate_baseline_bindings(release)
    scene_rows, csv_rows = [], []
    pending_ids, ready_rows, run_release_hashes = [], [], set()
    for rec in readj(WN12 / "MANIFEST.json")["records"]:
        sid = rec["scene_id"]
        legacy_identity = readj(WN12 / "SCREEN12_RESULTS_v1.json")["scenes"][rec["order"] - 1]["identity"]
        candidate = discover_candidate(sid, rec["payload_sha256"], rec["b_raw_sha256"], release, release_sha,
                                       legacy_identity)
        if candidate["status"] == "SCORED":
            run_release_hashes.add(candidate["run_start_release_sha256"])
            methods = {"Candidate": candidate["metrics"],
                       "B": baselines["records"][sid]["B"]["metrics"],
                       "C5": baselines["records"][sid]["C5"]["metrics"]}
            row = {"scene_id": sid, "source_split": rec["source_split"], "wind_index": rec["wind_index"],
                   "methods": methods,
                   "candidate_vs": {b: compare(methods["Candidate"], methods[b]) for b in ("B", "C5")},
                   "candidate_raw_path": candidate["raw_path"], "candidate_raw_sha256": candidate["raw_sha256"],
                   "candidate_run_status_path": candidate["status_path"],
                   "candidate_run_status_sha256": candidate["status_sha256"],
                   "candidate_run_start_sha256": candidate["run_start_sha256"],
                   "baseline_bindings": {b: {k: v for k, v in baselines["records"][sid][b].items() if k != "metrics"}
                                         for b in ("B", "C5")}}
            ready_rows.append(row)
            csv_row = {"scene_id": sid, "candidate_status": "SCORED", "source_split": rec["source_split"],
                       "wind_index": rec["wind_index"],
                       "wind_group": metrics.classify(sid, rec["source_split"])[2],
                       "candidate_raw_sha256": candidate["raw_sha256"]}
            for method in ("Candidate", "B", "C5"):
                for key in metrics.MAIN:
                    csv_row[f"{method}_{key}"] = methods[method][key]
            for baseline in ("B", "C5"):
                for key in metrics.MAIN:
                    csv_row[f"Candidate_vs_{baseline}_{key}"] = row["candidate_vs"][baseline][key]["outcome"]
                    csv_row[f"Candidate_minus_{baseline}_{key}"] = row["candidate_vs"][baseline][key]["candidate_minus_baseline"]
            for method in ("Candidate", "B", "C5"):
                for key, value in methods[method]["safety"].items():
                    csv_row[f"{method}_{key}"] = value
            scene_rows.append(row)
            csv_rows.append(csv_row)
        else:
            pending_ids.append(sid)
            scene_rows.append({"scene_id": sid, "source_split": rec["source_split"], "wind_index": rec["wind_index"],
                               "candidate": candidate, "baseline_bindings": {
                                   b: {k: v for k, v in baselines["records"][sid][b].items() if k != "metrics"}
                                   for b in ("B", "C5")}})
            csv_row = {"scene_id": sid, "candidate_status": candidate["status"], "source_split": rec["source_split"],
                       "wind_index": rec["wind_index"],
                       "wind_group": metrics.classify(sid, rec["source_split"])[2],
                       "candidate_raw_sha256": ""}
            for method in ("B", "C5"):
                for key in metrics.MAIN:
                    csv_row[f"{method}_{key}"] = baselines["records"][sid][method]["metrics"][key]
            for method in ("Candidate",):
                for key in metrics.MAIN:
                    csv_row[f"{method}_{key}"] = ""
            for baseline in ("B", "C5"):
                for key in metrics.MAIN:
                    csv_row[f"Candidate_vs_{baseline}_{key}"] = "PENDING"
            csv_rows.append(csv_row)
    require(len(run_release_hashes) <= 1, "Candidate scenes were launched from different RELEASE snapshots")
    complete = len(ready_rows) == 12
    result = {
        "schema": "DL1018_MLP15_PHYSICAL_RESIDUAL_CLOSED_LOOP_SCORE_V1",
        "status": "SCORED_12_SCENE_SCREEN" if complete else "PENDING_CANDIDATE_RAW_SCENES",
        "candidate_scene_count": len(ready_rows), "authorized_scene_count": 12,
        "candidate_pending_scene_ids": pending_ids,
        "release_path": str(release_path), "release_sha256_current": release_sha,
        "release_sha256_at_run_start": next(iter(run_release_hashes), None),
        "run_release_sha_matches_current": (next(iter(run_release_hashes)) == release_sha if run_release_hashes else None),
        "model_path": str(model_path), "model_sha256": release["model_sha256"],
        "metric_functions_path": str(METRIC_PATH), "metric_functions_sha256": sha(METRIC_PATH),
        "baseline_binding": {k: v for k, v in baselines.items() if k != "records"},
        "baseline_only_macro_scene_rmse": {
            method: {key: float(np.mean([baselines["records"][sid][method]["metrics"][key]
                                         for sid in baselines["scene_ids"]])) for key in metrics.MAIN}
            for method in ("B", "C5")},
        "rows": scene_rows,
        "aggregate": aggregate(ready_rows) if complete else None,
        "TEST_read": False, "training_runs": 0, "baseline_reruns": 0,
        "scope": "12-scene in-sample DEV/VAL closed-loop screen; not independent validation or TEST evidence",
    }
    write_outputs(result, csv_rows)
    print(json.dumps({"status": result["status"], "candidate_scene_count": len(ready_rows),
                      "pending_scene_ids": pending_ids, "outputs": [str(p) for p in OUTPUTS],
                      "aggregate": result["aggregate"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
