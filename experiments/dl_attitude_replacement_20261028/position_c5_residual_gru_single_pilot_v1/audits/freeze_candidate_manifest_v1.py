from __future__ import annotations

import hashlib
import json
from pathlib import Path


STUDY = Path(__file__).resolve().parents[1]
ROOT = STUDY.parents[2]
MODEL_PACKAGE = STUDY.parent / "position_c5_residual_gru_full_train_v1"
MODEL_MANIFEST = json.loads((MODEL_PACKAGE / "MODEL_MANIFEST_v1.json").read_text(encoding="utf-8"))
MODEL = STUDY / "candidate_runner_work/matlab/models/position_residual_gru_full_train24.mat"
CHECKPOINT = MODEL_PACKAGE / "position_residual_gru_full_train24.pt"
COSINE_STUDY = ROOT / "experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_full72_v1"
TAU_STUDY = ROOT / "experiments/dl_attitude_replacement_20261028/gru_prediction_tau01_v1"
COSINE_RELEASE = COSINE_STUDY / "RELEASE.json"
TAU_RELEASE = TAU_STUDY / "RELEASE.json"
TAU1_HELPER = COSINE_STUDY / "candidate_runner_work/matlab/runtime/delayed_prediction_step_candidate.m"
PARENT_PAYLOAD = STUDY / "MLP15_DEV72_PAYLOAD_MANIFEST_v2.json"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    assert sha256(MODEL) == MODEL_MANIFEST["mat_weights_sha256"]
    assert sha256(CHECKPOINT) == MODEL_MANIFEST["checkpoint_sha256"]
    cosine = json.loads(COSINE_RELEASE.read_text(encoding="utf-8"))
    files: list[dict[str, str]] = []
    for path in sorted(STUDY.rglob("*")):
        if not path.is_file() or path.name in {"SOURCE_LOCK_v1.json", "RELEASE.json"}:
            continue
        if path.suffix in {".mat", ".m", ".py"} or path.name == "MLP15_DEV72_PAYLOAD_MANIFEST_v2.json":
            files.append({"path": path.relative_to(STUDY).as_posix(), "sha256": sha256(path)})
    lock = {
        "schema": "POSITION_C5_RESIDUAL_GRU_SINGLE_PILOT_SOURCE_LOCK_V1",
        "root": str((STUDY / "candidate_runner_work").resolve()),
        "files": files,
        "scope": "isolated candidate runner, residual GRU MAT weights, and no-Plant/attempt/parity entry points",
    }
    lock_path = STUDY / "SOURCE_LOCK_v1.json"
    lock_path.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
    release = {
        "schema": "DL1018_POSITION_C5_RESIDUAL_GRU_NOPLANT_V1",
        "study_id": "position_c5_residual_gru_single_pilot_v1",
        "candidate_arm_id": "COSINE_GRU_C5_PLUS_POSITION_RESIDUAL_GRU_TRAIN24_V1",
        "status": "PREPARED_NO_PLANT_PENDING_ROOT_AUDIT",
        "authorization_phase": "NO_PLANT_REVIEW_ONLY",
        "fixed_scene_id": "DL1018_VAL_T3_C01_W14",
        "authorized_scenes": ["DL1018_VAL_T3_C01_W14"],
        "authorized_Plant_calls": 0,
        "Plant_calls": 0,
        "training_runs": 0,
        "TEST_read": False,
        "test_data_read": False,
        "inertia_reconstruction_enabled": False,
        "parent_study_id": "gru_stream_cosine_tracking_head_full72_v1",
        "parent_cosine_release_path": str(COSINE_RELEASE.resolve()),
        "parent_cosine_release_sha256": sha256(COSINE_RELEASE),
        "parent_tau01_release_path": str(TAU_RELEASE.resolve()),
        "parent_tau01_release_sha256": sha256(TAU_RELEASE),
        "parent_tau1_helper_path": str(TAU1_HELPER.resolve()),
        "parent_tau1_helper_sha256": sha256(TAU1_HELPER),
        "parent_payload_manifest_sha256": sha256(PARENT_PAYLOAD),
        "position_method_id": "C5_AXIS_MIXED_COORDINATE_M110",
        "position_nn_compensation_scale": 1,
        "position_delayed_prediction_h_s": 0.01,
        "position_delayed_prediction_tau_s": 1.0,
        "position_delayed_prediction_rho": 0.01,
        "notch_enabled": False,
        "position_residual_gru": {
            "enabled": True,
            "architecture": "GRU(14,32) -> Linear(32,3)",
            "weights_relative_path": "candidate_runner_work/matlab/models/position_residual_gru_full_train24.mat",
            "weights_sha256": sha256(MODEL),
            "checkpoint_sha256": sha256(CHECKPOINT),
            "model_manifest_sha256": sha256(MODEL_PACKAGE / "MODEL_MANIFEST_v1.json"),
            "seed": MODEL_MANIFEST["seed"],
            "optimizer_steps": MODEL_MANIFEST["steps"],
            "smooth_lambda": MODEL_MANIFEST["lambda"],
            "event_rate_hz": 100,
            "first_event_time_s": 0.01,
            "first_ready_event_index_zero_based": 31,
            "first_ready_event_time_s": 0.32,
            "hidden_reset_per_scene": True,
            "beta_formula": "clip(event_time_s/1.8,0,1)",
            "delta_clip_mps2": 0.5,
            "total_action_clip_mps2": 3.0,
            "apply_after": "C5 final applied acceleration, post-PCF, pre-mass force conversion",
        },
        "source_lock_path": "SOURCE_LOCK_v1.json",
        "source_lock_sha256": sha256(lock_path),
        "source_file_count": len(files),
        "release_notes": "Single-scene no-Plant preparation only. Parent is cosine GRU/C5 with notch disabled. Model was fit on TRAIN24; no TEST, Plant, or inertia reconstruction is authorized by this release.",
    }
    (STUDY / "RELEASE.json").write_text(json.dumps(release, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"study": str(STUDY), "source_lock_sha256": sha256(lock_path),
                      "source_file_count": len(files), "weights_sha256": sha256(MODEL),
                      "parent_cosine_release_sha256": release["parent_cosine_release_sha256"],
                      "parent_tau01_release_sha256": release["parent_tau01_release_sha256"]}, indent=2))


if __name__ == "__main__":
    main()
