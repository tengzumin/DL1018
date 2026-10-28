from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports" / "c2_comparator_config_audit_20261023"
RUNS = ROOT / "experiments" / "position_prior_calibration_c1_20261022_v9" / "reports" / "C1_SCREEN_PER_RUN.csv"
LOCK = ROOT / "experiments" / "position_prior_calibration_c1_20261022_v9" / "C1_SOURCE_LOCK_v2.json"
SCHEMA = OUT / "FULL12_H5_SCHEMA.csv"
FILE_IDS = OUT / "FULL12_FILE_IDENTITY.csv"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {}
    if isinstance(value, dict):
        for key, child in value.items():
            result.update(flatten(child, f"{prefix}/{key}" if prefix else str(key)))
    else:
        result[prefix] = value
    return result


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("x", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    runs = read_csv(RUNS)
    schema = read_csv(SCHEMA)
    file_ids = read_csv(FILE_IDS)
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    model_sha = lock["model"]["mat_sha256"]
    model_w0_sha = lock["model"]["w0_output_W_double_f_order_sha256"]
    normalizer_sha = lock["normalizer"]["npz_file_sha256"]
    lock_sha = sha256(LOCK)
    if len(runs) != 36:
        raise RuntimeError(f"expected 36 C1 per-run rows; got {len(runs)}")
    if len([x for x in runs if x["condition"] in ("B", "ON1")]) != 24:
        raise RuntimeError("expected 24 selected B/ON1 rows")

    file_id_map = {(x["scene_id"], x["condition"], x["file_kind"]): x for x in file_ids}
    schema_map: dict[tuple[str, str], dict[str, Any]] = {}
    for item in schema:
        if item["value_status"] != "INLINE" or not item["value_json"]:
            continue
        if item["path"].startswith("runIdentity/"):
            key = (item["scene_id"], item["condition"])
            schema_map.setdefault(key, {})["raw/" + item["path"]] = json.loads(item["value_json"])
        elif item["path"].startswith("runStart/"):
            key = (item["scene_id"], item["condition"])
            schema_map.setdefault(key, {})["run_start/" + item["path"]] = json.loads(item["value_json"])

    identity_rows: list[dict[str, Any]] = []
    status_by_run: dict[tuple[str, str], dict[str, Any]] = {}
    status_file_rows: list[dict[str, Any]] = []
    method = {"B": "C1_B_BASELINE", "ON1": "C1_ON_FEATURE_G12_C1"}
    for row in runs:
        if row["condition"] not in ("B", "ON1"):
            continue
        scene_id, condition = row["scene_id"], row["condition"]
        actual_release = row["actual_run_release"].lower()
        expected_lock_sha = row["source_lock_sha256"].lower()
        values = schema_map[(scene_id, condition)]
        checks = {
            "scene_id": (scene_id, values.get("raw/runIdentity/scene_id"), values.get("run_start/runStart/scene_id")),
            "condition": (condition, values.get("raw/runIdentity/condition"), values.get("run_start/runStart/condition")),
            "method": (method[condition], values.get("raw/runIdentity/method"), values.get("run_start/runStart/method")),
            "release_sha256": (actual_release, values.get("raw/runIdentity/release_sha256"), values.get("run_start/runStart/release_sha256")),
            "source_lock_sha256": (expected_lock_sha, values.get("raw/runIdentity/source_lock_sha256"), values.get("run_start/runStart/source_lock_sha256")),
            "model_mat_sha256": (model_sha, values.get("raw/runIdentity/model_mat_sha256"), values.get("run_start/runStart/model_mat_sha256")),
            "normalizer_npz_sha256": (normalizer_sha, values.get("raw/runIdentity/normalizer_npz_sha256"), values.get("run_start/runStart/normalizer_npz_sha256")),
            "model_W0_sha256": (model_w0_sha, None, values.get("run_start/runStart/model_W0_sha256")),
        }
        for field, (expected, raw_value, start_value) in checks.items():
            raw_ok = raw_value == expected if raw_value is not None else field == "model_W0_sha256"
            start_ok = start_value == expected
            identity_rows.append({
                "scene_id": scene_id,
                "condition": condition,
                "actual_run_release": actual_release,
                "identity_field": field,
                "expected": canonical(expected),
                "raw_runIdentity_value": canonical(raw_value) if raw_value is not None else "MISSING",
                "runStart_value": canonical(start_value) if start_value is not None else "MISSING",
                "raw_match": raw_ok,
                "runStart_match": start_ok,
                "result": "PASS" if raw_ok and start_ok else "FAIL",
            })
        if condition == "ON1" and values.get("raw/runIdentity/plant_called") != [[1]]:
            raise RuntimeError(f"ON1 plant_called identity mismatch: {scene_id}")
        if values.get("raw/runIdentity/optimizer_steps") != [[0.0]] or values.get("raw/runIdentity/gpu_jobs") != [[0.0]]:
            raise RuntimeError(f"optimizer/GPU identity mismatch: {scene_id} {condition}")
        if values.get("raw/runIdentity/test_accessed") != [[0]]:
            raise RuntimeError(f"TEST identity mismatch: {scene_id} {condition}")

        raw_path = Path(row["raw_path"])
        status_path = raw_path.parent / "run_status.json"
        expected_status_sha = row["run_status_sha256"].lower()
        before_sha = sha256(status_path)
        status = json.loads(status_path.read_text(encoding="utf-8"))
        after_sha = sha256(status_path)
        prior = file_id_map[(scene_id, condition, "run_status")]
        file_ok = (
            before_sha == after_sha == expected_status_sha == prior["expected_sha256_from_index"]
            and prior["sha_and_stat_unchanged"].lower() == "true"
        )
        for field, expected in (("scene_id", scene_id), ("condition", condition), ("release_sha256", actual_release), ("source_lock_sha256", expected_lock_sha)):
            actual = status.get(field)
            identity_rows.append({"scene_id": scene_id, "condition": condition, "actual_run_release": actual_release, "identity_field": "run_status." + field, "expected": canonical(expected), "raw_runIdentity_value": "", "runStart_value": canonical(actual), "raw_match": file_ok, "runStart_match": actual == expected, "result": "PASS" if file_ok and actual == expected else "FAIL"})
        for field, expected in (("raw_sha256", row["raw_sha256"].lower()), ("run_start_sha256", row["run_start_sha256"].lower())):
            actual = status.get(field)
            identity_rows.append({"scene_id": scene_id, "condition": condition, "actual_run_release": actual_release, "identity_field": "run_status." + field, "expected": canonical(expected), "raw_runIdentity_value": "", "runStart_value": canonical(actual), "raw_match": file_ok, "runStart_match": actual == expected, "result": "PASS" if file_ok and actual == expected else "FAIL"})
        if not file_ok:
            raise RuntimeError(f"run_status SHA/stat binding failed: {status_path}")
        status_by_run[(scene_id, condition)] = flatten(status)
        status_file_rows.append({"scene_id": scene_id, "condition": condition, "path": str(status_path), "expected_sha256": expected_status_sha, "sha256_before": before_sha, "sha256_after": after_sha, "matches_prior_before_after_and_manifest": file_ok})

    all_status_fields: list[dict[str, Any]] = []
    scene_ids = list(dict.fromkeys(x["scene_id"] for x in runs if x["condition"] in ("B", "ON1")))
    for scene_id in scene_ids:
        left, right = status_by_run[(scene_id, "B")], status_by_run[(scene_id, "ON1")]
        for path in sorted(set(left) | set(right)):
            b_has, on_has = path in left, path in right
            b_val, on_val = left.get(path), right.get(path)
            comparison = "EQUAL" if b_has and on_has and canonical(b_val) == canonical(on_val) else "VALUE_DIFF" if b_has and on_has else "MISSING_ON_ONE_SIDE"
            all_status_fields.append({"scene_id": scene_id, "field_path": path, "B_present": b_has, "ON1_present": on_has, "B_value_json": canonical(b_val) if b_has else "", "ON1_value_json": canonical(on_val) if on_has else "", "comparison": comparison})

    if any(x["result"] != "PASS" for x in identity_rows):
        raise RuntimeError("one or more run identity checks failed")
    write_csv(OUT / "FULL12_RECORD_IDENTITY.csv", ["scene_id", "condition", "actual_run_release", "identity_field", "expected", "raw_runIdentity_value", "runStart_value", "raw_match", "runStart_match", "result"], identity_rows)
    write_csv(OUT / "FULL12_STATUS_FILE_IDENTITY.csv", ["scene_id", "condition", "path", "expected_sha256", "sha256_before", "sha256_after", "matches_prior_before_after_and_manifest"], status_file_rows)
    write_csv(OUT / "FULL12_STATUS_FIELDS.csv", ["scene_id", "field_path", "B_present", "ON1_present", "B_value_json", "ON1_value_json", "comparison"], all_status_fields)
    summary = {
        "status": "PASS_RECORD_METADATA_AUDIT",
        "source_files": {"per_run_csv_sha256": sha256(RUNS), "source_lock_sha256": lock_sha, "schema_csv_sha256": sha256(SCHEMA), "file_identity_csv_sha256": sha256(FILE_IDS)},
        "selected_records": 24,
        "identity_checks": len(identity_rows),
        "identity_failures": 0,
        "status_files": len(status_file_rows),
        "status_file_failures": 0,
        "status_field_comparisons": len(all_status_fields),
        "status_field_differences": sum(x["comparison"] != "EQUAL" for x in all_status_fields),
        "actual_run_release_counts": {f"{condition}|{release}": sum(1 for r in runs if r["condition"] == condition and r["actual_run_release"].lower() == release) for condition in ("B", "ON1") for release in sorted({r["actual_run_release"].lower() for r in runs if r["condition"] == condition})},
        "plant_runs_expected": 12,
        "optimizer_steps_expected": 0,
        "gpu_jobs_expected": 0,
        "test_accessed_expected": False,
        "outputs": ["FULL12_RECORD_IDENTITY.csv", "FULL12_STATUS_FILE_IDENTITY.csv", "FULL12_STATUS_FIELDS.csv"],
    }
    (OUT / "FULL12_RECORD_METADATA_AUDIT.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
