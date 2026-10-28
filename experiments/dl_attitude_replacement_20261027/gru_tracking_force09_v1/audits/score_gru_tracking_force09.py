"""Hash-bound partial/final paired scoring for the fixed 12-scene GRU force09 screen."""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
ROOT = STUDY.parents[2]
WN12 = ROOT / "experiments" / "dl_attitude_replacement_20261027" / "task_attitude_filter_wn12_hf_screen_v1"
SCREEN_PATH = WN12 / "SCREEN12_RESULTS_v1.json"
METRIC_PATH = (ROOT / "experiments" / "dl_attitude_replacement_20261026" /
               "gru_stream_cosine_tracking_head_full72_v1" / "audits" /
               "score_full72_candidate_v1.py")
METRIC_SHA256 = "6baf689802f4d73ead813449e52a8fe85cb0be92c3185850c93646da2d54dd16"
MAIN = ("Q_m", "task_SO3_rad", "inner_SO3_rad")
GROUPS = {
    "ALL12": 12,
    "HF_W09_W14": 6,
    "W15": 3,
    "W00_W08": 3,
}
METHODS = ("Candidate", "B", "C5")
WIN_TOL = 1e-12


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


def load_metrics():
    require(bound(METRIC_PATH, METRIC_SHA256, "frozen FULL72 metric scorer"),
            "unreachable")
    spec = importlib.util.spec_from_file_location("frozen_full72_metrics", METRIC_PATH)
    require(spec is not None and spec.loader is not None, f"Cannot import metric scorer: {METRIC_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def classify(scene_id: str):
    m = re.search(r"_W(\d{2})$", scene_id)
    require(m is not None, f"Cannot parse wind group from {scene_id}")
    w = int(m.group(1))
    return "HF_W09_W14" if 9 <= w <= 14 else ("W15" if w == 15 else "W00_W08")


def validate_bindings():
    release_path = STUDY / "RELEASE.json"
    release = readj(release_path)
    require(release.get("schema") == "DL1018_GRU_TRACKING_FORCE09_SCREEN_RELEASE_V1" and
            release.get("study_id") == "gru_tracking_force09_v1" and
            release.get("candidate_arm_id") == "GRU32_STREAM72_COSINE_TRACKING_HEAD_FORCE09" and
            release.get("status") == "RELEASED" and
            release.get("authorized_Plant_calls") == 12 and
            abs(float(release.get("position_nn_compensation_scale", -1)) - .9) < 1e-12 and
            release.get("TEST_read") is False,
            "Force09 release identity, budget, scale, or TEST boundary is invalid")

    source_manifest_path = STUDY / "SOURCE_HASH_MANIFEST_v1.json"
    source_manifest_sha = bound(source_manifest_path, release["source_hash_manifest_sha256"],
                                "candidate source manifest")
    source_manifest = readj(source_manifest_path)
    require(source_manifest.get("schema") == "DL1018_GRU_TRACKING_FORCE09_SOURCE_HASH_MANIFEST_V1" and
            source_manifest.get("source_file_count") == len(source_manifest.get("files", [])),
            "Candidate source manifest schema/count is invalid")
    for row in source_manifest["files"]:
        bound(STUDY / row["path"], row["sha256"], f"candidate source {row['path']}")

    input_manifest_path = STUDY / "SCENE_INPUT_MANIFEST_v1.json"
    input_manifest_sha = bound(input_manifest_path, release["scene_input_manifest_sha256"],
                               "fixed 12-scene input manifest")
    manifest = readj(input_manifest_path)
    require(manifest.get("schema") == "DL1018_GRU_TRACKING_FORCE09_INPUT_MANIFEST_V1" and
            manifest.get("status") == "PASS_FIXED12_INPUT_BINDINGS" and
            manifest.get("scene_count") == 12 and len(manifest.get("records", [])) == 12 and
            manifest.get("TEST_read") is False and manifest.get("Plant_calls") == 0,
            "Fixed input manifest is invalid")
    ids = [r["scene_id"] for r in manifest["records"]]
    require(len(set(ids)) == 12 and set(ids) == set(release["authorized_scenes"]),
            "Input-manifest scenes differ from the exact authorized 12")
    parent_path = Path(release["parent_manifest_path"])
    parent_sha = bound(parent_path, release["parent_manifest_sha256"], "FULL72 parent manifest")
    parent = readj(parent_path)
    require(parent.get("schema") == "GRU_STREAM_COSINE_TRACKING_HEAD_FULL72_MANIFEST_V1" and
            parent.get("candidate") == release["parent_candidate"] and
            parent.get("scene_count") == 72 and parent.get("dev_scene_count") == 24 and
            parent.get("val_scene_count") == 48 and parent.get("TEST_read") is False and
            str(parent.get("candidate_model_sha256", "")).lower() ==
            str(release["gru_model_sha256"]).lower(),
            "Parent model/manifest scope differs from the locked WN18 FULL72 GRU")
    require(str(manifest.get("parent_manifest_sha256", "")).lower() == parent_sha.lower(),
            "Scene manifest does not bind the parent FULL72 manifest")
    bound(Path(release["gru_model_path"]), release["gru_model_sha256"], "frozen WN18 GRU model")

    screen = readj(SCREEN_PATH)
    require(str(screen.get("metric_scorer_path", "")).lower() == str(METRIC_PATH).lower() and
            str(screen.get("metric_scorer_sha256", "")).lower() == METRIC_SHA256,
            "WN12 screen does not bind the expected frozen metric scorer")
    constants_path = Path(screen["metric_constants_path"])
    bound(constants_path, screen["metric_constants_sha256"], "frozen metric constants")
    constants = readj(constants_path)
    gravity = float(constants["gravity_mps2"])
    max_tilt = float(constants["max_tilt_rad"])
    require(abs(gravity - float(screen["metric_constants"]["gravity_mps2"])) < 1e-12 and
            abs(max_tilt - float(screen["metric_constants"]["max_tilt_rad"])) < 1e-12,
            "Metric constants differ from the WN12 screen binding")
    return release_path, release, release, manifest, source_manifest_sha, input_manifest_sha, \
        parent_sha, gravity, max_tilt, screen


def validate_base_row(record: dict, method: str):
    raw_path = Path(record[f"{method.lower()}_raw_path"])
    raw_sha = bound(raw_path, record[f"{method.lower()}_raw_sha256"], f"{method} raw")
    status_path = Path(record[f"{method.lower()}_status_path"])
    status_sha = bound(status_path, record[f"{method.lower()}_status_sha256"], f"{method} status")
    status = readj(status_path)
    test_clear = status.get("TEST_accessed") is False and \
        status.get("TEST_read", False) is False
    require(status.get("scene_id") == record["scene_id"] and
            status.get("status") == "RUN_COMPLETE_RAW_PENDING_AUDIT" and
            status.get("log_status") == "STABLE" and
            status.get("transitions") == 20000 and status.get("state_samples") == 20001 and
            status.get("plant_calls") == 1 and status.get("training_steps") == 0 and
            status.get("optimizer_steps") == 0 and test_clear and
            str(status.get("raw_sha256", "")).lower() == raw_sha.lower(),
            f"{method} source status/input identity failed for {record['scene_id']}")
    return raw_path, raw_sha, status_path, status_sha, status


def candidate_for(record: dict, release: dict, release_sha: str, source_sha: str,
                  input_sha: str, parent_sha: str, metrics, gravity: float, max_tilt: float):
    sid = record["scene_id"]
    attempt = STUDY / "runs" / sid / "GRU_FORCE09_ATTEMPT_01"
    status_path = attempt / "run_status.json"
    start_path = attempt / "run_start.json"
    if not status_path.is_file():
        state = "IN_PROGRESS" if (attempt / "run_start.json").is_file() else "NOT_STARTED"
        return None, {"scene_id": sid, "state": state}

    status = readj(status_path)
    if status.get("state") != "COMPLETED":
        return None, {"scene_id": sid, "state": str(status.get("state", "UNKNOWN")),
                      "status_path": str(status_path), "status_sha256": sha(status_path)}
    require(start_path.is_file(), f"Completed candidate has no run_start: {sid}")
    start = readj(start_path)
    status_sha = sha(status_path)
    start_sha = sha(start_path)
    require(status.get("scene_id") == sid and status.get("Plant_calls") == 1 and
            status.get("TEST_read") is False and
            abs(float(status.get("position_nn_compensation_scale", -1)) - .9) < 1e-12 and
            str(status.get("gru_model_sha256", "")).lower() ==
            str(release["gru_model_sha256"]).lower(),
            f"Completed candidate status identity failed for {sid}")
    for key, expected in (
        ("release_sha256", release_sha),
        ("source_hash_manifest_sha256", source_sha),
        ("scene_input_manifest_sha256", input_sha),
        ("parent_manifest_sha256", parent_sha),
        ("scene_payload_sha256", record["payload_sha256"]),
        ("b_raw_sha256", record["b_raw_sha256"]),
        ("c5_input_lock_sha256", release["c5_input_lock_sha256"]),
        ("gru_model_sha256", release["gru_model_sha256"]),
    ):
        require(str(start.get(key, "")).lower() == str(expected).lower(),
                f"run_start {key} binding mismatch for {sid}")
    require(start.get("scene_id") == sid and
            start.get("candidate") == release["candidate_arm_id"] and
            start.get("attitude_arm") == "GRU_STREAM" and
            abs(float(start.get("position_nn_compensation_scale", -1)) - .9) < 1e-12,
            f"run_start scene/model-arm/scale mismatch for {sid}")
    raw_path = Path(status["raw_path"])
    expected_raw = attempt / "raw_run.mat"
    require(raw_path.resolve() == expected_raw.resolve(),
            f"Candidate raw path is outside the exact attempt directory for {sid}")
    raw_sha = bound(raw_path, status["raw_sha256"], f"candidate raw {sid}")
    require(status.get("transitions") == 20000 and status.get("state_samples") == 20001 and
            status.get("status_value") == "STABLE",
            f"Candidate is not a complete stable run for {sid}")
    scored = metrics.score_raw(raw_path, gravity, max_tilt)
    scored.update({
        "raw_path": str(raw_path), "raw_sha256": raw_sha,
        "run_start_path": str(start_path), "run_start_sha256": start_sha,
        "run_status_path": str(status_path), "run_status_sha256": status_sha,
        "release_sha256": release_sha,
        "source_hash_manifest_sha256": source_sha,
        "scene_input_manifest_sha256": input_sha,
        "gru_model_sha256": release["gru_model_sha256"],
        "position_nn_compensation_scale": .9,
    })
    return scored, {"scene_id": sid, "state": "COMPLETED"}


def macro(rows: list[dict], group: str):
    selected = [r for r in rows if group == "ALL12" or r["wind_group"] == group]
    out = {"scene_count": len(selected), "expected_scene_count": GROUPS[group],
           "complete": len(selected) == GROUPS[group]}
    out["macro_mean_observed"] = {
        method: {
            key: sum(r["methods"][method][key] for r in selected) / len(selected)
            for key in MAIN
        } for method in METHODS
    } if selected else None
    wins = {}
    for baseline in ("B", "C5"):
        wins[baseline] = {}
        for key in MAIN:
            diffs = [r["methods"]["Candidate"][key] - r["methods"][baseline][key]
                     for r in selected]
            wins[baseline][key] = {
                "win": sum(d < -WIN_TOL for d in diffs),
                "tie": sum(abs(d) <= WIN_TOL for d in diffs),
                "loss": sum(d > WIN_TOL for d in diffs),
            }
    out["per_scene_wins_losses_ties"] = wins
    return out


def write_csv(path: Path, rows: list[dict]):
    fields = ["scene_id", "split", "wind_group"]
    for method in METHODS:
        fields.extend(f"{method}_{key}" for key in MAIN)
    for baseline in ("B", "C5"):
        fields.extend(f"Candidate_minus_{baseline}_{key}" for key in MAIN)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            flat = {"scene_id": row["scene_id"], "split": row["split"],
                    "wind_group": row["wind_group"]}
            for method in METHODS:
                flat.update({f"{method}_{key}": row["methods"][method][key] for key in MAIN})
            for baseline in ("B", "C5"):
                flat.update({f"Candidate_minus_{baseline}_{key}":
                             row["methods"]["Candidate"][key] - row["methods"][baseline][key]
                             for key in MAIN})
            writer.writerow(flat)


def write_markdown(path: Path, result: dict):
    lines = [
        "# GRU tracking force09 paired score",
        "",
        f"Status: **{result['status']}**. Completed scenes: "
        f"{result['completed_scene_count']}/12.",
        "",
        "This is a fixed 12-scene development screen. The parent GRU model used DEV24+VAL48 "
        "development data; VAL is not an independent holdout. A winning candidate still needs "
        "fresh holdout evaluation.",
        "",
        "| Group | n / expected | Complete | Method | Q (m) | task SO(3) (rad) | inner SO(3) (rad) |",
        "|---|---:|:---:|---|---:|---:|---:|",
    ]
    for group, summary in result["groups"].items():
        means = summary["macro_mean_observed"]
        for method in METHODS:
            m = means[method] if means else None
            values = ["—", "—", "—"] if m is None else [
                f"{m['Q_m']:.9g}", f"{m['task_SO3_rad']:.9g}", f"{m['inner_SO3_rad']:.9g}"]
            lines.append(f"| {group} | {summary['scene_count']} / {summary['expected_scene_count']} | "
                         f"{'yes' if summary['complete'] else 'no'} | {method} | "
                         + " | ".join(values) + " |")
    lines.extend(["", "Pending or failed scenes:"])
    if result["pending_scenes"]:
        lines.extend(f"- {r['scene_id']}: {r['state']}" for r in result["pending_scenes"])
    else:
        lines.append("- none")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
                        help="output tag, e.g. partial02 or final12")
    args = parser.parse_args()
    require(re.fullmatch(r"[A-Za-z0-9_.-]+", args.tag) is not None, "Invalid output tag")
    json_out = HERE / f"GRU_TRACKING_FORCE09_SCORE_{args.tag}.json"
    csv_out = HERE / f"GRU_TRACKING_FORCE09_SCORE_{args.tag}.csv"
    md_out = HERE / f"GRU_TRACKING_FORCE09_SCORE_{args.tag}.md"
    for path in (json_out, csv_out, md_out):
        require(not path.exists(), f"Refusing to overwrite existing score artifact: {path}")

    metric_module = load_metrics()
    (release_path, release, _, manifest, source_sha, input_sha,
     parent_sha, gravity, max_tilt, screen) = validate_bindings()
    release_sha = sha(release_path)
    rows, pending = [], []
    for record in manifest["records"]:
        sid = record["scene_id"]
        b_path, b_sha, b_status_path, b_status_sha, b_status = validate_base_row(record, "B")
        c5_path, c5_sha, c5_status_path, c5_status_sha, c5_status = validate_base_row(record, "C5")
        candidate, state = candidate_for(record, release, release_sha, source_sha, input_sha,
                                         parent_sha, metric_module, gravity, max_tilt)
        if candidate is None:
            pending.append(state)
            continue
        paired = {
            "Candidate": candidate,
            "B": metric_module.score_raw(b_path, gravity, max_tilt),
            "C5": metric_module.score_raw(c5_path, gravity, max_tilt),
        }
        paired["B"].update({"raw_path": str(b_path), "raw_sha256": b_sha,
                            "status_path": str(b_status_path), "status_sha256": b_status_sha})
        paired["C5"].update({"raw_path": str(c5_path), "raw_sha256": c5_sha,
                             "status_path": str(c5_status_path), "status_sha256": c5_status_sha})
        rows.append({
            "scene_id": sid, "split": record["source_split"],
            "wind_group": classify(sid), "methods": paired,
            "input_bindings": {
                "payload_sha256": record["payload_sha256"],
                "b_raw_sha256": b_sha, "b_status_sha256": b_status_sha,
                "c5_raw_sha256": c5_sha, "c5_status_sha256": c5_status_sha,
                "candidate_run_start_sha256": candidate["run_start_sha256"],
                "candidate_run_status_sha256": candidate["run_status_sha256"],
            },
        })

    complete = len(rows) == 12 and not pending and {r["scene_id"] for r in rows} == \
        {r["scene_id"] for r in manifest["records"]}
    groups = {name: macro(rows, name) for name in GROUPS}
    if complete:
        for name, expected in GROUPS.items():
            require(groups[name]["scene_count"] == expected,
                    f"Complete 12-scene group count mismatch for {name}")
    result = {
        "schema": "DL1018_GRU_TRACKING_FORCE09_PAIRED_SCORE_V1",
        "status": "COMPLETE_12_SCREEN" if complete else "PARTIAL_12_SCREEN",
        "study_id": release["study_id"],
        "candidate_arm_id": release["candidate_arm_id"],
        "completed_scene_count": len(rows),
        "expected_scene_count": 12,
        "pending_scenes": pending,
        "groups": groups,
        "scene_results": rows,
        "release_sha256": release_sha,
        "source_hash_manifest_sha256": source_sha,
        "scene_input_manifest_sha256": input_sha,
        "parent_manifest_sha256": parent_sha,
        "gru_model_sha256": release["gru_model_sha256"],
        "parent_model_scope": release.get("parent_model_scope"),
        "independent_validation_claimed": False,
        "fresh_holdout_required_for_winner": True,
        "position_nn_compensation_scale": .9,
        "command_filter_wn_rad_s": release["command_filter_wn_rad_s"],
        "metric_source_path": str(METRIC_PATH),
        "metric_source_sha256": METRIC_SHA256,
        "metric_constants_path": screen["metric_constants_path"],
        "metric_constants_sha256": screen["metric_constants_sha256"],
        "metric_constants": {"gravity_mps2": gravity, "max_tilt_rad": max_tilt},
        "metric_definitions": {
            "Q_m": "RMS Euclidean position error over all 20001 state samples.",
            "task_SO3_rad": "SO(3) geodesic RMSE against task attitude reconstructed by the frozen FULL72 metric scorer.",
            "inner_SO3_rad": "SO(3) geodesic RMSE against filtered_attitude_reference over 20000 transitions.",
            "macro_mean": "Arithmetic mean of the per-scene metric over completed rows in that group.",
        },
        "run_identity_binding": "Candidate raw is scored only after run_start binds release, source/input manifests, parent model, scene payload, B raw, C5 lock, GRU model, and alpha=.9; B/C5 raw and status SHA values are bound by SCENE_INPUT_MANIFEST_v1.json.",
        "plant_calls_by_scorer": 0,
        "training_runs_by_scorer": 0,
        "TEST_read": False,
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }
    json_out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_csv(csv_out, rows)
    write_markdown(md_out, result)
    print(json.dumps({"status": result["status"], "completed": len(rows), "expected": 12,
                      "pending": pending, "json": str(json_out), "csv": str(csv_out),
                      "markdown": str(md_out)}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
