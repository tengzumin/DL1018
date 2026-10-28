from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SCENE = "DL1018_DEV_T3_C09_W09"
STUDY_ID = "static_n4_T3C09_no_position_gru_v1"
CENTERS = [2.2, 3.2, 3.7, 4.8]
Q = [4.0, 4.0, 4.0, 4.0]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def notch_coefficients() -> tuple[list[list[float]], list[list[float]]]:
    b_rows, a_rows = [], []
    for center, q in zip(CENTERS, Q):
        w0 = 2 * np.pi * center / 100.0
        alpha = np.sin(w0) / (2 * q)
        scale = 1 + alpha
        b_rows.append([float(x) for x in np.array([1, -2 * np.cos(w0), 1]) / scale])
        a_rows.append([1.0, float(-2 * np.cos(w0) / scale), float((1 - alpha) / scale)])
    return b_rows, a_rows


def main() -> None:
    release_path = HERE / "RELEASE.json"
    lock_path = HERE / "SOURCE_LOCK_NO_PLANT_v1.json"
    if release_path.exists() or lock_path.exists():
        raise SystemExit("refusing to overwrite an existing release or lock")
    binding_path = HERE / "TRAIN_SCENE_BINDING_v1.json"
    binding = json.loads(binding_path.read_text(encoding="utf-8-sig"))
    if binding.get("selected_scene_id") != SCENE or binding.get("source_order_zero_based") != 20:
        raise SystemExit("scene binding is not the exact physical TRAIN T3/C09 row")
    b, a = notch_coefficients()
    sources: set[Path] = set()
    sources.add(binding_path)
    sources.add(HERE / "TRAIN_SCENE_PAYLOAD_v1.mat")
    sources.add(HERE / "MATLAB_EVENTWISE_PARITY_INPUTS_v1.mat")
    sources.add(HERE / "MATLAB_EVENTWISE_PARITY_INPUTS_v1.json")
    sources.add(HERE / "audits/MATLAB_EVENTWISE_PARITY_v1.json")
    sources.add(HERE / "matlab/run_static_n4_helper_parity.m")
    sources.add(HERE / "patch_static_n4_runner.py")
    sources.add(HERE / "make_static_n4_parity_inputs.py")
    sources.add(HERE / "write_n4_no_plant_release.py")
    sources.add(ROOT / "experiments/dl_attitude_replacement_20261028/n4_closed_loop_protocol_v1.json")
    sources.add(ROOT / "experiments/dl_attitude_replacement_20261028/n4_train24_replay/TRAIN24_STATIC_N4_REPLAY_v1.json")
    sources.add(ROOT / "experiments/dl_attitude_replacement_20261028/position_compensation_dual_notch_train_replay_v1/TRAIN_FROZEN_DUAL_NOTCH_REPLAY_v1.json")
    sources.update(p for p in (HERE / "candidate_runner_work").rglob("*") if p.is_file())
    for field in (
        "dataset_manifest_path", "dataset_source_lock_path", "parent_cosine_release_path",
        "parent_cosine_manifest_path", "parent_cosine_source_lock_path", "parent_cosine_model_path",
        "parent_raw_path", "parent_status_path", "parent_run_start_path", "c5_input_lock_path",
        "c5_raw_path", "c5_status_path", "c5_run_start_path", "b72_scoring_raw_path",
        "b72_scoring_status_path", "c5_snapshot_path", "position_model_path", "c5_receipt_path",
    ):
        sources.add(Path(binding[field]))
    # Frozen scorer and its constants are used only after the one call, but bind now.
    sources.add(ROOT / "experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_full72_v1/audits/score_full72_candidate_v1.py")
    sources.add(ROOT / "experiments/dl_attitude_replacement_20261026/mlp15_composite_dev_v3/RELEASE.json")
    missing = [str(p) for p in sources if not p.is_file()]
    if missing:
        raise SystemExit("missing locked source(s): " + ", ".join(missing))
    files = [{"path": str(p.resolve()), "sha256": sha(p)} for p in sorted(sources, key=lambda x: str(x).lower())]
    lock = {"schema": "STATIC_N4_T3C09_NO_PLANT_SOURCE_LOCK_V1", "study_id": STUDY_ID, "files": files}
    lock_path.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
    release = {
        "schema": "DL1018_POSITION_C5_STATIC_N4_NO_POSITION_GRU_NOPLANT_V1",
        "study_id": STUDY_ID,
        "status": "PREPARED_NO_PLANT_PENDING_ROOT_AUDIT",
        "fixed_scene_id": SCENE,
        "authorized_scenes": [SCENE],
        "authorized_Plant_calls": 0,
        "Plant_calls": 0,
        "potential_budget_calls": 0,
        "source_lock_path": str(lock_path.resolve()),
        "source_lock_sha256": sha(lock_path),
        "train_scene_binding_path": str(binding_path.resolve()),
        "train_scene_binding_sha256": sha(binding_path),
        "payload_path": str((HERE / "TRAIN_SCENE_PAYLOAD_v1.mat").resolve()),
        "payload_sha256": sha(HERE / "TRAIN_SCENE_PAYLOAD_v1.mat"),
        "applied_acceleration_static_n4": {
            "enabled": True,
            "centers_hz": CENTERS,
            "quality_factor_each": Q,
            "sample_rate_hz": 100.0,
            "action_limit_mps2": 3.0,
            "b": b,
            "a": a,
            "event_update": "C5 100-Hz position events only; zero-order hold between events",
            "state_initialization": "first nonzero event initializes all section histories and passes sample unchanged",
            "application_point": "final C5 applied compensation before force injection",
            "runtime_wind_or_W_code_branching": False,
        },
        "extra_position_residual_gru_enabled": False,
        "extra_position_gru_weights_loaded_or_forwarded": False,
        "TEST_read": False,
        "VAL_data_read": False,
        "inertia_reconstruction_enabled": False,
        "Plant_truth_deployment_input": False,
        "parameter_sweep": False,
        "prior_two_notch_status": "FAIL_FIXED_FROZEN_REPLAY",
        "prior_two_notch_result_sha256": "92c14d6252818b3c184554763677cf4b26efab470393c07d8f55d55733875f9d",
        "n4_train24_replay_sha256": "dcaa34dc1a02d73337f60dcb53f860831345e2a8400cc2b9b7d47b20a3a98fd9",
    }
    release_path.write_text(json.dumps(release, indent=2) + "\n", encoding="utf-8")
    print(f"RELEASE={release_path}")
    print(f"SOURCE_LOCK={lock_path} files={len(files)}")


if __name__ == "__main__":
    main()
