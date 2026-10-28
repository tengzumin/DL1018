"""Read-only A1R SCREEN12 pairing, gated by all twelve independent raw audits.

No simulation, Plant, training, or model inference is performed. Outputs are
created only after every A1R audit and all three raw identities per scene pass.
"""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

REPORT_REL = "reports/attitude_cm18_datarepair_20261024"
SCREEN_REPORT_REL = "reports/attitude_cm18_a1_20261024"
MANIFEST_REL = f"{SCREEN_REPORT_REL}/CM18_A1_DEV_SCREEN12_v1.json"
BASELINE_SCORE_REL = f"{SCREEN_REPORT_REL}/ROOT_SCREEN12_PAIRED_METRICS_v1.json"
SCORER_REL = f"{SCREEN_REPORT_REL}/root_screen12_metrics_v1.py"
A1R_REPORT_REL = f"{REPORT_REL}/a1r_screen12_control_v1"
A1R_RUN_REL = "experiments/attitude_cm18_datarepair_20261024/a1r_screen12_control_v1/runs"
A1_RUN_REL = "experiments/attitude_cm18_a1_20261024"
AUDITOR_REL = f"{A1R_REPORT_REL}/audit_a1r_screen12_log_v1.py"

PINS = {
    "manifest_sha256": "fdca3f17c0f39d19eb5b08e94e7e5b1f148ec03cf861eacec64d86ab7922f923",
    "baseline_score_sha256": "6c6a1eb8d2b499d211a5f57379ac6d4a5f3cb7ae560d5bbad070b4bc8d649e27",
    "scorer_sha256": "3b345050b31cabdfcb08dab405d9e34b736e1f65c02bc9fd22d3a0f08c9aeb52",
    "a1r_auditor_sha256": "8e99eedfa8c02229cb456e165d1dccf243a7357d4a276e7869620a6498715210",
    "a1r_execution_runner_sha256": "3fcc70da28a6b783523a870f3adbaf11c0f022b6722c82af474009ae8aa7347b",
    "a1r_prepared_runner_sha256": "fc99c4f1820b197c44b71d6fe9505d9eadfe2d467446b334c7dfc19bfa3d2628",
    "deployment_sha256": "b3ab7a3d99df639d4cc0a10ec2b6fcd4622388f58c90c25424e472164ef38d23",
    "checkpoint_sha256": "5fa4308b6220e530e6c2e7a6f45c4b6e22ddddef80d1bc5cafdcf58564bc5ef3",
    "normalizer_sha256": "faf8748f640c944c745406247ab8486825966abd763088ad1f4e0cde626ad14c",
}
SCENARIO_METRICS = (
    "position_Q_m", "position_peak_m", "SO3_RMSE_deg", "SO3_peak_deg",
    "body_rate_RMSE_rads",
)
PERIODS = ("all", "pre", "post")
CONTROLLERS = ("C5_RBF", "A1", "A1R")
AUDIT_SCHEMA = "A1R_SCREEN12_INDEPENDENT_LOG_AUDIT_V1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def repo_path(root: Path, value: str | Path) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = root / candidate
    result = candidate.resolve()
    if not result.is_relative_to(root.resolve()):
        raise ValueError(f"path escapes repository: {value}")
    return result


def same_repo_path(root: Path, left: str | Path, right: str | Path) -> bool:
    return repo_path(root, left) == repo_path(root, right)


def checked_scorer(root: Path):
    path = repo_path(root, SCORER_REL)
    if sha256(path).lower() != PINS["scorer_sha256"]:
        raise ValueError("frozen ROOT score implementation SHA mismatch")
    spec = importlib.util.spec_from_file_location("root_screen12_metrics_v1_pinned", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load frozen scorer: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, "score", None)):
        raise ValueError("frozen scorer does not expose score(path)")
    return module


def validate_score(actual: dict[str, Any], expected: dict[str, Any], scene: str, label: str) -> float:
    if actual.get("raw_sha256", "").lower() != expected.get("raw_sha256", "").lower():
        raise ValueError(f"{scene}: frozen {label} raw SHA changed")
    max_delta = 0.0
    actual_metrics, expected_metrics = actual["metrics"], expected["metrics"]
    for period in PERIODS:
        a, e = actual_metrics[period], expected_metrics[period]
        if a["n"] != e["n"]:
            raise ValueError(f"{scene}: frozen {label} {period} sample count changed")
        for key in SCENARIO_METRICS:
            delta = abs(float(a[key]) - float(e[key]))
            max_delta = max(max_delta, delta)
            if delta > 1e-14:
                raise ValueError(f"{scene}: frozen {label} {period}/{key} changed by {delta:.17g}")
        axis_delta = max(abs(float(x) - float(y)) for x, y in zip(
            a["position_axis_RMSE_m"], e["position_axis_RMSE_m"], strict=True))
        max_delta = max(max_delta, axis_delta)
        if axis_delta > 1e-14:
            raise ValueError(f"{scene}: frozen {label} {period} position axes changed")
    for key in ("motor_saturated_transitions", "cm18_events"):
        if key in expected_metrics and actual_metrics.get(key) != expected_metrics[key]:
            raise ValueError(f"{scene}: frozen {label} {key} changed")
    return max_delta


def audit_gate(root: Path, manifest: dict[str, Any], rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    qualified: list[dict[str, Any]] = []
    incomplete: list[dict[str, str]] = []
    first_scene = manifest.get("first_engineering_scene")
    for index, row in enumerate(rows):
        scene = str(row["scene_id"])
        attempt = "attempt_02" if scene == first_scene else "attempt_01"
        audit_path = repo_path(root, f"{A1R_REPORT_REL}/A1R_SCREEN12_LOG_AUDIT_{scene}_v1.json")
        status_path = repo_path(root, f"{A1R_RUN_REL}/{scene}/{attempt}/run_status.json")
        raw_path = repo_path(root, f"{A1R_RUN_REL}/{scene}/{attempt}/raw_run.mat")
        start_path = repo_path(root, f"{A1R_RUN_REL}/{scene}/{attempt}/run_start.mat")
        missing = [p.name for p in (audit_path, status_path, raw_path, start_path) if not p.is_file()]
        if missing:
            incomplete.append({"scene_id": scene, "state": "MISSING", "artifacts": ",".join(missing)})
            continue
        audit = read_json(audit_path)
        status = read_json(status_path)
        reasons: list[str] = []
        actual_raw_sha = sha256(raw_path).lower()
        actual_start_sha = sha256(start_path).lower()
        if audit.get("schema") != AUDIT_SCHEMA or audit.get("status") != "PASS":
            reasons.append(f"audit={audit.get('status', 'unknown')}")
        if audit.get("scene_id") != scene:
            reasons.append("audit_scene_mismatch")
        if str(audit.get("audit_source_sha256", "")).lower() != PINS["a1r_auditor_sha256"]:
            reasons.append("auditor_source_sha_mismatch")
        if str(audit.get("raw_sha256", "")).lower() != actual_raw_sha:
            reasons.append("audit_raw_sha_mismatch")
        if str(audit.get("run_start_sha256", "")).lower() != actual_start_sha:
            reasons.append("audit_run_start_sha_mismatch")
        if not same_repo_path(root, audit.get("raw_path", ""), raw_path):
            reasons.append("audit_raw_path_mismatch")
        if (status.get("schema") != "A1R_SCREEN12_CONTROL_RUN_STATUS_V2"
                or status.get("status") != "RUN_COMPLETE_PENDING_ROOT_AUDIT"
                or status.get("scene_id") != scene
                or str(status.get("raw_sha256", "")).lower() != actual_raw_sha
                or str(status.get("run_start_sha256", "")).lower() != actual_start_sha
                or str(status.get("root_release_sha256", "")).lower()
                != str(audit.get("release_sha256", "")).lower()
                or not same_repo_path(root, status.get("raw_path", ""), raw_path)
                or status.get("plant_calls") != 1
                or status.get("training_steps") != 0
                or status.get("optimizer_steps") != 0
                or status.get("cm18_events") != audit.get("counts", {}).get("cm18_events")
                or status.get("TEST_accessed") is not False
                or str(status.get("execution_runner_sha256", "")).lower() != PINS["a1r_execution_runner_sha256"]
                or str(status.get("prepared_runner_sha256", "")).lower() != PINS["a1r_prepared_runner_sha256"]):
            reasons.append("runner_status_identity_or_scope_mismatch")
        if str(audit.get("deployment_parameters_sha256", "")).lower() != PINS["deployment_sha256"]:
            reasons.append("deployment_sha_mismatch")
        if str(audit.get("checkpoint_sha256", "")).lower() != PINS["checkpoint_sha256"]:
            reasons.append("checkpoint_sha_mismatch")
        if str(audit.get("normalizer_float64_sha256", "")).lower() != PINS["normalizer_sha256"]:
            reasons.append("normalizer_sha_mismatch")
        if reasons:
            incomplete.append({"scene_id": scene, "state": "REJECTED", "reasons": ";".join(reasons)})
            continue
        qualified.append({
            "scene_id": scene, "task": row["task"], "category": row["category"],
            "attempt": attempt, "raw_path": raw_path, "run_start_path": start_path,
            "audit_path": audit_path, "audit_sha256": sha256(audit_path).lower(),
            "audit_source_sha256": audit["audit_source_sha256"].lower(),
            "raw_sha256": actual_raw_sha, "run_start_sha256": actual_start_sha,
            "release_sha256": str(audit["release_sha256"]).lower(),
            "event_count": int(audit["counts"]["cm18_events"]),
        })
    return qualified, incomplete


def a1_path(root: Path, scene: str, first_scene: str) -> Path:
    subdir = "first_flight_preparation_v1" if scene == first_scene else "screen12_remaining_v1"
    return repo_path(root, f"{A1_RUN_REL}/{subdir}/runs/{scene}/attempt_01/raw_run.mat")


def score_all(root: Path, rows: list[dict[str, Any]], prior: dict[str, Any], qualified: list[dict[str, Any]], first_scene: str) -> list[dict[str, Any]]:
    scorer = checked_scorer(root)
    prior_by_scene = {r["scene_id"]: r for r in prior["rows"]}
    qualified_by_scene = {r["scene_id"]: r for r in qualified}
    output: list[dict[str, Any]] = []
    for row in rows:
        scene = str(row["scene_id"])
        old_row = prior_by_scene[scene]
        audit_row = qualified_by_scene[scene]
        c5_path = repo_path(root, row["baseline_C5_raw_path"])
        a1_raw_path = a1_path(root, scene, first_scene)
        for path, label in ((c5_path, "C5_RBF"), (a1_raw_path, "A1"), (audit_row["raw_path"], "A1R")):
            if not path.is_file():
                raise FileNotFoundError(f"{scene}: missing {label} raw: {path}")
        if sha256(c5_path).lower() != str(row["baseline_C5_raw_sha256"]).lower():
            raise ValueError(f"{scene}: manifest C5 raw identity changed")
        scored = {
            "C5_RBF": scorer.score(c5_path),
            "A1": scorer.score(a1_raw_path),
            "A1R": scorer.score(audit_row["raw_path"]),
        }
        baseline_delta = {
            "C5_RBF": validate_score(scored["C5_RBF"], old_row["C5_RBF"], scene, "C5_RBF"),
            "A1": validate_score(scored["A1"], old_row["CM18_A1"], scene, "A1"),
        }
        if scored["A1R"]["raw_sha256"].lower() != audit_row["raw_sha256"]:
            raise ValueError(f"{scene}: scorer raw SHA differs from PASS audit")
        if scored["A1R"]["metrics"].get("cm18_events") != audit_row["event_count"]:
            raise ValueError(f"{scene}: scorer and audit CM18 event counts differ")
        output.append({
            "scene_id": scene, "task": row["task"], "category": row["category"],
            "audit": audit_row, "scored": scored,
            "baseline_score_recheck_max_abs_delta": baseline_delta,
        })
    return output


def scene_csv(rows: list[dict[str, Any]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=scene_columns(), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        out: dict[str, Any] = {
            "scene_id": row["scene_id"], "task": row["task"], "category": row["category"],
            "A1R_audit_status": "PASS", "A1R_audit_sha256": row["audit"]["audit_sha256"],
            "A1R_audit_source_sha256": row["audit"]["audit_source_sha256"],
            "A1R_raw_sha256": row["scored"]["A1R"]["raw_sha256"],
            "A1R_run_start_sha256": row["audit"]["run_start_sha256"],
            "A1R_root_release_sha256": row["audit"]["release_sha256"],
            "C5_RBF_raw_sha256": row["scored"]["C5_RBF"]["raw_sha256"],
            "A1_raw_sha256": row["scored"]["A1"]["raw_sha256"],
            "A1R_cm18_events": row["audit"]["event_count"],
            "baseline_score_recheck_max_abs_delta_C5": row["baseline_score_recheck_max_abs_delta"]["C5_RBF"],
            "baseline_score_recheck_max_abs_delta_A1": row["baseline_score_recheck_max_abs_delta"]["A1"],
        }
        for controller in CONTROLLERS:
            metrics = row["scored"][controller]["metrics"]
            out[f"{controller}_motor_saturated_transitions"] = metrics["motor_saturated_transitions"]
            out[f"{controller}_cm18_events"] = metrics.get("cm18_events", "")
            for period in PERIODS:
                for key in ("n", "position_Q_m", "position_peak_m", "SO3_RMSE_deg",
                            "SO3_peak_deg", "body_rate_RMSE_rads"):
                    out[f"{controller}_{period}_{key}"] = metrics[period][key]
                for axis, value in zip("xyz", metrics[period]["position_axis_RMSE_m"], strict=True):
                    out[f"{controller}_{period}_position_{axis}_RMSE_m"] = value
        for baseline in ("C5_RBF", "A1"):
            for period in PERIODS:
                for key in SCENARIO_METRICS:
                    out[f"delta_A1R_minus_{baseline}_{period}_{key}"] = (
                        row["scored"]["A1R"]["metrics"][period][key]
                        - row["scored"][baseline]["metrics"][period][key]
                    )
        writer.writerow(out)
    return buffer.getvalue().encode("utf-8")


def scene_columns() -> list[str]:
    columns = [
        "scene_id", "task", "category", "A1R_audit_status", "A1R_audit_sha256",
        "A1R_audit_source_sha256", "A1R_raw_sha256", "A1R_run_start_sha256",
        "A1R_root_release_sha256", "C5_RBF_raw_sha256", "A1_raw_sha256", "A1R_cm18_events",
        "baseline_score_recheck_max_abs_delta_C5", "baseline_score_recheck_max_abs_delta_A1",
    ]
    for controller in CONTROLLERS:
        columns.extend((f"{controller}_motor_saturated_transitions", f"{controller}_cm18_events"))
        for period in PERIODS:
            columns.extend(f"{controller}_{period}_{key}" for key in (
                "n", "position_Q_m", "position_peak_m", "SO3_RMSE_deg", "SO3_peak_deg",
                "body_rate_RMSE_rads", "position_x_RMSE_m", "position_y_RMSE_m", "position_z_RMSE_m"))
    for baseline in ("C5_RBF", "A1"):
        for period in PERIODS:
            columns.extend(f"delta_A1R_minus_{baseline}_{period}_{key}" for key in SCENARIO_METRICS)
    return columns


def group_csv(rows: list[dict[str, Any]]) -> bytes:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(str(row["task"]), str(row["category"]))].append(row)
    fields = ["task", "category", "scene_count"]
    for baseline in ("C5_RBF", "A1"):
        for period in PERIODS:
            fields.extend((f"A1R_SO3_wins_vs_{baseline}_{period}",
                           f"A1R_position_Q_wins_vs_{baseline}_{period}",
                           f"A1R_body_rate_wins_vs_{baseline}_{period}"))
    for controller in CONTROLLERS:
        for period in PERIODS:
            fields.extend(f"{controller}_{period}_mean_{key}" for key in SCENARIO_METRICS)
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for (task, category), members in groups.items():
        out: dict[str, Any] = {"task": task, "category": category, "scene_count": len(members)}
        for baseline in ("C5_RBF", "A1"):
            for period in PERIODS:
                for metric, column in (("SO3_RMSE_deg", "SO3"), ("position_Q_m", "position_Q"),
                                       ("body_rate_RMSE_rads", "body_rate")):
                    wins = sum(row["scored"]["A1R"]["metrics"][period][metric]
                               < row["scored"][baseline]["metrics"][period][metric] - 1e-12
                               for row in members)
                    out[f"A1R_{column}_wins_vs_{baseline}_{period}"] = wins
        for controller in CONTROLLERS:
            for period in PERIODS:
                for metric in SCENARIO_METRICS:
                    out[f"{controller}_{period}_mean_{metric}"] = sum(
                        row["scored"][controller]["metrics"][period][metric] for row in members
                    ) / len(members)
        writer.writerow(out)
    return buffer.getvalue().encode("utf-8")


def write_new(path: Path, data: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(data)


def main() -> int:
    root = Path(__file__).resolve().parents[3]
    manifest_path = repo_path(root, MANIFEST_REL)
    prior_path = repo_path(root, BASELINE_SCORE_REL)
    if sha256(manifest_path).lower() != PINS["manifest_sha256"]:
        raise ValueError("SCREEN12 manifest SHA mismatch")
    if sha256(prior_path).lower() != PINS["baseline_score_sha256"]:
        raise ValueError("frozen C5/A1 paired score report SHA mismatch")
    manifest, prior = read_json(manifest_path), read_json(prior_path)
    rows = manifest.get("scenes", [])
    if (manifest.get("schema") != "CM18_A1_FUTURE_DEVELOPMENT_SCREEN12_V1"
            or len(rows) != 12 or len({row.get("scene_id") for row in rows}) != 12
            or prior.get("schema") != "ROOT_CM18_SCREEN12_PAIRED_SCORE_V1"
            or prior.get("manifest_sha256") != PINS["manifest_sha256"]
            or prior.get("completed") != 12 or prior.get("missing") != []):
        raise ValueError("frozen SCREEN12 manifest or baseline score schema/count mismatch")
    prior_by_scene = {row["scene_id"]: row for row in prior["rows"]}
    if set(prior_by_scene) != {row["scene_id"] for row in rows}:
        raise ValueError("baseline paired scores do not contain the exact SCREEN12 scene set")
    qualified, incomplete = audit_gate(root, manifest, rows)
    if incomplete or len(qualified) != 12:
        print(json.dumps({"status": "INCOMPLETE", "audited_PASS": len(qualified),
                          "expected": 12, "scenes": incomplete,
                          "final_tables_written": False}, ensure_ascii=False, indent=2))
        return 2
    for row in rows:
        old = prior_by_scene[row["scene_id"]]
        if (old.get("task") != row.get("task") or old.get("category") != row.get("category")
                or old.get("C5_RBF", {}).get("raw_sha256", "").lower()
                != str(row.get("baseline_C5_raw_sha256", "")).lower()):
            raise ValueError(f"{row['scene_id']}: baseline scene/task/category identity mismatch")
    scored_rows = score_all(root, rows, prior, qualified, str(manifest["first_engineering_scene"]))
    scene_bytes, group_bytes = scene_csv(scored_rows), group_csv(scored_rows)
    out_dir = repo_path(root, A1R_REPORT_REL)
    scene_path = out_dir / "ROOT_A1R_SCREEN12_PAIRED_SCENES_v1.csv"
    group_path = out_dir / "ROOT_A1R_SCREEN12_PAIRED_GROUPS_v1.csv"
    report_path = out_dir / "ROOT_A1R_SCREEN12_PAIRED_SCORE_v1.json"
    if any(path.exists() for path in (scene_path, group_path, report_path)):
        raise FileExistsError("refusing to overwrite an existing A1R paired score artifact")
    write_new(scene_path, scene_bytes)
    write_new(group_path, group_bytes)
    result = {
        "schema": "ROOT_A1R_SCREEN12_PAIRED_SCORE_V1",
        "status": "COMPLETE_PENDING_ROOT_REVIEW",
        "scene_count": len(scored_rows), "a1r_independent_audit_pass_count": len(qualified),
        "manifest_sha256": sha256(manifest_path),
        "prior_c5_a1_score_sha256": sha256(prior_path),
        "frozen_scorer_path": SCORER_REL,
        "frozen_scorer_sha256": sha256(repo_path(root, SCORER_REL)),
        "a1r_auditor_sha256": PINS["a1r_auditor_sha256"],
        "raw_scope": "Only the fixed SCREEN12 C5_RBF, original A1, and A1R raws; each A1R raw is included only after its independent audit is PASS and raw SHA matches.",
        "score_scope": "Per-scene all/pre/post metrics are preserved; group CSV reports equal-scene arithmetic means and win counts. No scene is filtered by outcome.",
        "tables": {
            "scenes": {"path": str(scene_path.relative_to(root)), "sha256": hashlib.sha256(scene_bytes).hexdigest(),
                       "bytes": len(scene_bytes), "rows": len(scored_rows)},
            "groups": {"path": str(group_path.relative_to(root)), "sha256": hashlib.sha256(group_bytes).hexdigest(),
                       "bytes": len(group_bytes), "rows": len({(r['task'], r['category']) for r in scored_rows})},
        },
        "per_scene": [{"scene_id": row["scene_id"], "task": row["task"], "category": row["category"],
                       "a1r_raw_sha256": row["scored"]["A1R"]["raw_sha256"],
                       "a1r_audit_sha256": row["audit"]["audit_sha256"],
                       "a1r_audit_status": "PASS"} for row in scored_rows],
        "baseline_recheck_max_abs_delta": {
            key: max(row["baseline_score_recheck_max_abs_delta"][key] for row in scored_rows)
            for key in ("C5_RBF", "A1")
        },
    }
    report_bytes = (json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    write_new(report_path, report_bytes)
    print(json.dumps({"status": result["status"], "scene_count": len(scored_rows),
                      "scenes_csv": str(scene_path.relative_to(root)),
                      "groups_csv": str(group_path.relative_to(root)),
                      "report_json": str(report_path.relative_to(root))}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
