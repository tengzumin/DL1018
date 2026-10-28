from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
STUDY_ID = "static_n4_T3C09_no_position_gru_v1"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    release_path = HERE / "RELEASE.json"
    no_plant_release = HERE / "references/PRIOR_NO_PLANT_RELEASE_v1.json"
    if no_plant_release.exists() or (HERE / "SOURCE_LOCK_SINGLE_CALL_v1.json").exists():
        raise SystemExit("refusing to overwrite prior release or single-call lock")
    shutil.copy2(release_path, no_plant_release)
    prior_audit = HERE / "audits/NO_PLANT_PREFLIGHT_v1.json"
    prior_lock = HERE / "SOURCE_LOCK_NO_PLANT_v1.json"
    audit = json.loads(prior_audit.read_text(encoding="utf-8-sig"))
    if audit.get("status") != "PASS_FULL_RUNNER_NOPLANT_BOUNDARY" or audit.get("Plant_calls") != 0:
        raise SystemExit("single-call release requires the passing zero-Plant full-runner audit")
    sources: set[Path] = set()
    sources.update(p for p in (HERE / "candidate_runner_work").rglob("*") if p.is_file())
    for name in (
        "TRAIN_SCENE_BINDING_v1.json", "TRAIN_SCENE_PAYLOAD_v1.mat",
        "MATLAB_EVENTWISE_PARITY_INPUTS_v1.mat", "MATLAB_EVENTWISE_PARITY_INPUTS_v1.json",
        "patch_static_n4_runner.py", "make_static_n4_parity_inputs.py",
        "write_n4_no_plant_release.py", "write_n4_single_call_release.py",
        "matlab/run_static_n4_helper_parity.m", "audits/MATLAB_EVENTWISE_PARITY_v1.json",
        "audits/NO_PLANT_PREFLIGHT_v1.json", "SOURCE_LOCK_NO_PLANT_v1.json",
    ):
        sources.add(HERE / name)
    sources.add(no_plant_release)
    sources.add(ROOT / "experiments/dl_attitude_replacement_20261028/n4_closed_loop_protocol_v1.json")
    sources.add(ROOT / "experiments/dl_attitude_replacement_20261028/n4_train24_replay/TRAIN24_STATIC_N4_REPLAY_v1.json")
    sources.add(ROOT / "experiments/dl_attitude_replacement_20261028/position_compensation_dual_notch_train_replay_v1/TRAIN_FROZEN_DUAL_NOTCH_REPLAY_v1.json")
    binding = json.loads((HERE / "TRAIN_SCENE_BINDING_v1.json").read_text(encoding="utf-8-sig"))
    for field in (
        "dataset_manifest_path", "dataset_source_lock_path", "parent_cosine_release_path",
        "parent_cosine_manifest_path", "parent_cosine_source_lock_path", "parent_cosine_model_path",
        "parent_raw_path", "parent_status_path", "parent_run_start_path", "c5_input_lock_path",
        "c5_raw_path", "c5_status_path", "c5_run_start_path", "b72_scoring_raw_path",
        "b72_scoring_status_path", "c5_snapshot_path", "position_model_path", "c5_receipt_path",
    ):
        sources.add(Path(binding[field]))
    sources.add(ROOT / "experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_full72_v1/audits/score_full72_candidate_v1.py")
    sources.add(ROOT / "experiments/dl_attitude_replacement_20261026/mlp15_composite_dev_v3/RELEASE.json")
    missing = [str(p) for p in sources if not p.is_file()]
    if missing:
        raise SystemExit("missing locked source(s): " + ", ".join(missing))
    files = [{"path": str(p.resolve()), "sha256": sha(p)} for p in sorted(sources, key=lambda x: str(x).lower())]
    lock_path = HERE / "SOURCE_LOCK_SINGLE_CALL_v1.json"
    lock = {"schema": "STATIC_N4_T3C09_SINGLE_CALL_SOURCE_LOCK_V1", "study_id": STUDY_ID, "files": files}
    lock_path.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
    release = json.loads(no_plant_release.read_text(encoding="utf-8-sig"))
    release.update({
        "schema": "DL1018_POSITION_C5_STATIC_N4_NO_POSITION_GRU_SINGLE_CALL_V1",
        "status": "RELEASED",
        "authorized_Plant_calls": 1,
        "Plant_calls": 1,
        "potential_budget_calls": 1,
        "source_lock_path": str(lock_path.resolve()),
        "source_lock_sha256": sha(lock_path),
        "prior_no_plant_preflight_path": str(prior_audit.resolve()),
        "prior_no_plant_preflight_sha256": sha(prior_audit),
        "prior_no_plant_source_lock_path": str(prior_lock.resolve()),
        "prior_no_plant_source_lock_sha256": sha(prior_lock),
        "prior_no_plant_release_path": str(no_plant_release.resolve()),
        "prior_no_plant_release_sha256": sha(no_plant_release),
    })
    release_path.write_text(json.dumps(release, indent=2) + "\n", encoding="utf-8")
    print(f"SINGLE_RELEASE={release_path}")
    print(f"SINGLE_SOURCE_LOCK={lock_path} files={len(files)}")


if __name__ == "__main__":
    main()
