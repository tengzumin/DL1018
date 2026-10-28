#!/usr/bin/env python3
"""Post-run score attempt_002 with the existing frozen tau_score function."""
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
ATTEMPT = "attempt_002"
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


def verify_official(method: str, rec: dict, scene_id: str) -> tuple[Path, dict]:
    raw = Path(rec["raw_path"])
    if not raw.is_file() or sha(raw).lower() != rec["raw_sha256"].lower():
        raise RuntimeError(f"{method} raw SHA mismatch")
    status_key, status_sha_key = (("run_status_path", "run_status_sha256") if "run_status_path" in rec
                                 else ("status_path", "status_sha256"))
    status_path = Path(rec[status_key])
    if not status_path.is_file() or sha(status_path).lower() != rec[status_sha_key].lower():
        raise RuntimeError(f"{method} status SHA mismatch")
    status = readj(status_path)
    if (status.get("scene_id") != scene_id or status.get("transitions") != 20000 or
            status.get("state_samples") != 20001 or status.get("TEST_accessed") is True or
            status.get("test_data_read") is True or status.get("raw_sha256", rec["raw_sha256"]) != rec["raw_sha256"]):
        raise RuntimeError(f"{method} status is not a complete fixed-scene non-TEST run")
    if status.get("state") not in (None, "COMPLETED") or status.get("log_status") not in (None, "STABLE") or status.get("status_value") not in (None, "STABLE"):
        raise RuntimeError(f"{method} run is not stable")
    return raw, status


def main() -> None:
    if OUT.exists():
        raise RuntimeError(f"Refusing to overwrite {OUT}")
    official = readj(OFFICIAL)
    if official.get("status") != "COMPLETE_12_SCREEN" or official.get("TEST_read") is not False or official.get("test_data_read") is not False:
        raise RuntimeError("Final12 comparator audit is incomplete or touched TEST")
    if sha(SCORER).lower() != official["metric_source_sha256"].lower():
        raise RuntimeError("Frozen scorer SHA differs from official final12 record")
    scene = next((r for r in official["scene_results"] if r["scene_id"] == SCENE), None)
    if scene is None:
        raise RuntimeError("Fixed scene is absent from final12 score record")
    spec = importlib.util.spec_from_file_location("frozen_tau_score", SCORER)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load frozen scorer")
    scorer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scorer)

    release_path = STUDY / "RELEASE.json"
    lock_path = STUDY / "SOURCE_LOCK_v1.json"
    release = readj(release_path)
    if (release.get("status") != "RELEASED" or release.get("authorized_Plant_calls") != 1 or
            release.get("Plant_calls") != 1 or release.get("TEST_read") is not False or
            sha(lock_path).lower() != release["source_lock_sha256"].lower()):
        raise RuntimeError("Candidate release/source lock/budget invalid")
    candidate_dir = STUDY / "runs" / SCENE / ATTEMPT
    candidate_raw = candidate_dir / "raw_run.mat"
    candidate_status_path = candidate_dir / "run_status.json"
    candidate_status = readj(candidate_status_path)
    if (candidate_status.get("state") != "COMPLETED" or candidate_status.get("status_value") != "STABLE" or
            candidate_status.get("plant_calls") != 1 or candidate_status.get("scene_id") != SCENE or
            candidate_status.get("test_data_read") is not False or
            candidate_status.get("release_sha256") != sha(release_path) or
            candidate_status.get("source_lock_sha256") != release["source_lock_sha256"] or
            sha(candidate_raw) != candidate_status.get("raw_sha256")):
        raise RuntimeError("Candidate attempt_002 raw/status is incomplete or unbound")

    constants = official["metric_constants"]
    candidate_score = scorer.score_raw(candidate_raw, float(constants["gravity_mps2"]), float(constants["max_tilt_rad"]))
    results = {"PositionBalancedFull24": candidate_score}
    bindings = {
        "PositionBalancedFull24": {
            "raw_path": str(candidate_raw.resolve()), "raw_sha256": sha(candidate_raw),
            "run_status_path": str(candidate_status_path.resolve()), "run_status_sha256": sha(candidate_status_path),
            "release_sha256": sha(release_path), "source_lock_sha256": release["source_lock_sha256"],
            "status": candidate_status,
        }
    }
    for method in ("B", "C5", "Parent_Cosine_GRU"):
        rec = scene["methods"][method]
        raw, status = verify_official(method, rec, SCENE)
        score = scorer.score_raw(raw, float(constants["gravity_mps2"]), float(constants["max_tilt_rad"]))
        for metric in ("Q_m", "task_SO3_rad", "inner_SO3_rad"):
            if not math.isclose(score[metric], float(rec[metric]), rel_tol=0, abs_tol=1e-12):
                raise RuntimeError(f"Frozen re-score disagrees with final12 {method}.{metric}")
        results[method] = score
        status_key, status_sha_key = (("run_status_path", "run_status_sha256") if "run_status_path" in rec
                                     else ("status_path", "status_sha256"))
        bindings[method] = {"raw_path": str(raw.resolve()), "raw_sha256": rec["raw_sha256"],
                            "status_path": rec[status_key], "status_sha256": rec[status_sha_key],
                            "status": status, "final12_score_reproduced": True}
    comparison = {}
    for method in ("B", "C5", "Parent_Cosine_GRU"):
        comparison[method] = {}
        for metric in ("Q_m", "task_SO3_rad", "inner_SO3_rad"):
            candidate, reference = results["PositionBalancedFull24"][metric], results[method][metric]
            comparison[method][metric] = {"candidate_minus_reference": candidate-reference,
                "relative_change": (candidate-reference)/reference if reference else None,
                "candidate_lower_is_better": candidate < reference}

    report = {
        "schema": "POSITION_TEACHER_POSITION_BALANCED_FULL24_SINGLE_PILOT_SCORE_V1",
        "status": "SCORED_ONE_FIXED_VAL_SCENE", "scene_id": SCENE, "attempt": ATTEMPT,
        "scope": "One fixed VAL development screen; not independent validation or a generalization claim.",
        "score_wrapper_path": str(Path(__file__).resolve()), "score_wrapper_sha256": sha(Path(__file__)),
        "score_wrapper_is_postrun_only": True,
        "scorer_path": str(SCORER.resolve()), "scorer_sha256": sha(SCORER),
        "official_final12_path": str(OFFICIAL.resolve()), "official_final12_sha256": sha(OFFICIAL),
        "metric_constants": constants, "release_sha256": sha(release_path),
        "source_lock_sha256": release["source_lock_sha256"], "plant_calls": 1,
        "TEST_read": False, "inertia_reconstruction_enabled": False,
        "scores": results, "comparisons": comparison, "input_bindings": bindings,
    }
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"done": True, "scores": results, "report": str(OUT)}, indent=2), flush=True)


if __name__ == "__main__":
    main()
