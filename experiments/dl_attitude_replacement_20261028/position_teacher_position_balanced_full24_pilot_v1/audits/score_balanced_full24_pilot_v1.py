#!/usr/bin/env python3
"""Score one completed fixed VAL pilot with the frozen tau_score function."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
ROOT = HERE.parents[3]
SCENE = "DL1018_VAL_T3_C01_W14"
OFFICIAL = ROOT / "experiments/dl_attitude_replacement_20261028/gru_prediction_tau01_v1/audits/GRU_PREDICTION_TAU01_SCORE_final12.json"
SCORER = ROOT / "experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_full72_v1/audits/score_full72_candidate_v1.py"
OUT = HERE / "SINGLE_PILOT_SCORE_v1.json"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def readj(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def verify_status(method: str, rec: dict) -> tuple[Path, dict]:
    raw_path = Path(rec["raw_path"])
    if not raw_path.is_file() or sha(raw_path).lower() != rec["raw_sha256"].lower():
        raise RuntimeError(f"{method} raw missing or SHA mismatch")
    status_key = "run_status_path" if "run_status_path" in rec else "status_path"
    status_sha_key = "run_status_sha256" if "run_status_sha256" in rec else "status_sha256"
    status_path = Path(rec[status_key])
    if not status_path.is_file() or sha(status_path).lower() != rec[status_sha_key].lower():
        raise RuntimeError(f"{method} status missing or SHA mismatch")
    status = readj(status_path)
    if status.get("scene_id") != SCENE or status.get("TEST_accessed") is True or status.get("test_data_read") is True:
        raise RuntimeError(f"{method} status is not bound to the fixed non-TEST scene")
    if status.get("transitions") != 20000 or status.get("state_samples") != 20001:
        raise RuntimeError(f"{method} run is incomplete")
    if status.get("state") not in (None, "COMPLETED") or status.get("log_status") not in (None, "STABLE") or status.get("status_value") not in (None, "STABLE"):
        raise RuntimeError(f"{method} run is not stable")
    if status.get("raw_sha256", rec["raw_sha256"]).lower() != rec["raw_sha256"].lower():
        raise RuntimeError(f"{method} status raw SHA differs from score binding")
    return raw_path, status


def main() -> None:
    if OUT.exists():
        raise RuntimeError(f"Refusing to overwrite {OUT}")
    official = readj(OFFICIAL)
    if official.get("status") != "COMPLETE_12_SCREEN" or official.get("TEST_read") is not False or official.get("test_data_read") is not False:
        raise RuntimeError("Frozen final12 comparator record is incomplete or violates no-TEST scope")
    if sha(SCORER).lower() != official["metric_source_sha256"].lower():
        raise RuntimeError("Frozen scorer source SHA does not match official final12 scoring")
    scene = next((r for r in official["scene_results"] if r["scene_id"] == SCENE), None)
    if scene is None:
        raise RuntimeError("Fixed scene is not in the official paired score record")
    constants = official["metric_constants"]
    spec = importlib.util.spec_from_file_location("frozen_tau_scorer", SCORER)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load frozen tau_score module")
    scorer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scorer)
    release_path = STUDY / "RELEASE.json"
    release = readj(release_path)
    lock_path = STUDY / "SOURCE_LOCK_v1.json"
    if (release.get("status") != "RELEASED" or release.get("authorized_Plant_calls") != 1 or
            release.get("Plant_calls") != 1 or release.get("TEST_read") is not False or
            sha(lock_path).lower() != release["source_lock_sha256"].lower()):
        raise RuntimeError("Candidate release/budget/source-lock binding is invalid")
    run_dir = STUDY / "runs" / SCENE / "attempt_001"
    candidate_status_path = run_dir / "run_status.json"
    candidate_raw_path = run_dir / "raw_run.mat"
    candidate_status = readj(candidate_status_path)
    if (candidate_status.get("state") != "COMPLETED" or candidate_status.get("status_value") != "STABLE" or
            candidate_status.get("scene_id") != SCENE or candidate_status.get("plant_calls") != 1 or
            candidate_status.get("test_data_read") is not False or
            candidate_status.get("release_sha256") != sha(release_path) or
            candidate_status.get("source_lock_sha256") != release["source_lock_sha256"]):
        raise RuntimeError("Candidate run status is not complete, stable or bound to release/source lock")
    candidate_sha = sha(candidate_raw_path)
    if candidate_status.get("raw_sha256") != candidate_sha:
        raise RuntimeError("Candidate raw/status SHA mismatch")

    rows = {"PositionBalancedFull24": {"raw_path": str(candidate_raw_path.resolve()),
                                       "raw_sha256": candidate_sha,
                                       "run_status_path": str(candidate_status_path.resolve()),
                                       "run_status_sha256": sha(candidate_status_path),
                                       "release_sha256": sha(release_path),
                                       "source_lock_sha256": release["source_lock_sha256"],
                                       "status": candidate_status}}
    official_methods = {"Parent_Cosine_GRU": "Parent_Cosine_GRU", "B": "B", "C5": "C5"}
    results = {"PositionBalancedFull24": scorer.score_raw(candidate_raw_path, float(constants["gravity_mps2"]), float(constants["max_tilt_rad"]))}
    for output_name, official_name in official_methods.items():
        rec = scene["methods"][official_name]
        raw_path, status = verify_status(official_name, rec)
        actual = scorer.score_raw(raw_path, float(constants["gravity_mps2"]), float(constants["max_tilt_rad"]))
        for metric in ("Q_m", "task_SO3_rad", "inner_SO3_rad"):
            if not math.isclose(actual[metric], float(rec[metric]), rel_tol=0, abs_tol=1e-12):
                raise RuntimeError(f"Re-score differs from official {official_name}.{metric}")
        results[output_name] = actual
        rows[output_name] = {"raw_path": str(raw_path.resolve()), "raw_sha256": rec["raw_sha256"],
                             "status_path": rec["run_status_path"] if "run_status_path" in rec else rec["status_path"],
                             "status_sha256": rec["run_status_sha256"] if "run_status_sha256" in rec else rec["status_sha256"],
                             "status": status, "official_final12_score_matches": True}
    candidate = results["PositionBalancedFull24"]
    comparisons = {}
    for comparator in ("B", "C5", "Parent_Cosine_GRU"):
        comparisons[comparator] = {}
        for metric in ("Q_m", "task_SO3_rad", "inner_SO3_rad"):
            base = results[comparator][metric]
            val = candidate[metric]
            comparisons[comparator][metric] = {
                "candidate_minus_comparator": val - base,
                "relative_change": (val - base) / base if base else None,
                "candidate_lower_is_better": val < base,
            }
    report = {
        "schema": "POSITION_TEACHER_POSITION_BALANCED_FULL24_SINGLE_PILOT_SCORE_V1",
        "status": "SCORED_ONE_FIXED_VAL_SCENE",
        "scene_id": SCENE,
        "scope": "One fixed VAL development screen; not independent validation or a generalization claim.",
        "scorer_path": str(SCORER.resolve()), "scorer_sha256": sha(SCORER),
        "official_final12_path": str(OFFICIAL.resolve()), "official_final12_sha256": sha(OFFICIAL),
        "metric_constants": constants,
        "release_sha256": sha(release_path), "source_lock_sha256": release["source_lock_sha256"],
        "plant_calls": 1, "TEST_read": False, "inertia_reconstruction_enabled": False,
        "scores": results, "comparisons": comparisons, "input_bindings": rows,
    }
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"done": True, "scores": {k: v for k, v in results.items()}, "report": str(OUT)}, indent=2), flush=True)


if __name__ == "__main__":
    main()
