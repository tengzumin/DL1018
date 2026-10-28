"""Freeze the one-scene TRAIN-only lead candidate before its no-Plant audit."""
from pathlib import Path
import hashlib
import json

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
SCENE = "DL1018_DEV_T1_C00_W03"
REQUIRED_BINDING_PATHS = (
    "dataset_manifest_path", "dataset_source_lock_path", "parent_cosine_model_path",
    "c5_snapshot_path", "position_model_path", "c5_receipt_path", "local_scene_payload_path",
    "parent_raw_path", "parent_status_path", "parent_run_start_path", "c5_raw_path",
    "c5_status_path", "b72_scoring_raw_path", "b72_scoring_status_path",
)


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_new(path, value):
    if path.exists():
        raise RuntimeError(f"Refusing to overwrite {path}")
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def main():
    if (HERE / "SOURCE_LOCK_v2.json").exists() or (HERE / "RELEASE.json").exists():
        raise RuntimeError("Refusing to reuse an existing lead lock or release")
    parity_actual = HERE / "parity" / "MATLAB_PARITY_ACTUAL_v1.csv"
    if not parity_actual.is_file():
        raise RuntimeError("Run parity/helper_parity_v1.py first")
    binding_path = HERE / "bindings" / f"{SCENE}.json"
    binding = json.loads(binding_path.read_text(encoding="utf-8"))
    assert binding["status"] == "PASS_TRAIN_ONLY_PAIR_BINDING"
    assert binding["selected_scene_id"] == SCENE
    assert binding["source_split"].startswith("TRAIN_C5_24")
    assert binding["Plant_calls"] == 0 and not binding["TEST_read"] and not binding["VAL_data_read"]

    n4_release = json.loads((BASE / "n4cg_v2" / "RELEASE.json").read_text(encoding="utf-8"))
    static_n4 = n4_release["applied_acceleration_static_n4"]
    lead = {
        "enabled": True,
        "sample_rate_hz": 100,
        "b": [17 / 7, -15 / 7],
        "a": [1, -5 / 7],
        "difference_equation": "y[n]=(17/7)x[n]-(15/7)x[n-1]+(5/7)y[n-1]",
        "application_point": "after raw N4 output and before gate blend",
        "gate_input": "original C5 applied action u",
        "startup_gate_zero_until_s": 2,
        "state_initialization": "on first nonzero N4 output, x1=y1=N4(u)",
        "state_update": "every 100-Hz event, including while gate is closed; hold between events",
        "final_action": "clip(u+g*(lead(N4(u))-u),-3,3)",
    }

    sources = {p.resolve() for p in (HERE / "candidate_runner_work").rglob("*") if p.is_file()}
    sources.update(p.resolve() for p in (HERE / "bindings").glob("*.json"))
    sources.update(p.resolve() for p in (HERE / "parity").rglob("*") if p.is_file())
    sources.update({Path(__file__).resolve(), (HERE / "freeze_single_source_lock_v1.py").resolve()})
    for key in REQUIRED_BINDING_PATHS:
        p = Path(binding[key]).resolve()
        assert p.is_file() and sha(p) == binding[key.removesuffix("_path") + "_sha256"], key
        sources.add(p)
    files = [{"path": str(p), "sha256": sha(p)} for p in sorted(sources, key=lambda x: str(x).lower())]
    lock = {"study_id": "causal_n4_gate_v2", "scene_id": SCENE, "candidate": "N4 causal gate plus fixed lead", "files": files}
    lock_path = HERE / "SOURCE_LOCK_v2.json"
    write_new(lock_path, lock)
    release = {
        "schema": "DL1018_CAUSAL_N4_LEAD_GATE_NOPLANT_V1",
        "study_id": "causal_n4_gate_v2",
        "status": "PREPARED_NO_PLANT_PENDING_ROOT_AUDIT",
        "authorized_scenes": [SCENE],
        "fixed_scene_id": SCENE,
        "authorized_Plant_calls": 0,
        "Plant_calls": 0,
        "potential_budget_calls": 0,
        "source_lock_sha256": sha(lock_path),
        "applied_acceleration_static_n4": static_n4,
        "applied_acceleration_lead": lead,
        "extra_position_residual_gru_enabled": False,
        "TEST_read": False,
        "VAL_data_read": False,
        "inertia_reconstruction_enabled": False,
        "Plant_truth_deployment_input": False,
    }
    write_new(HERE / "RELEASE.json", release)
    write_new(HERE / "RELEASE_NOPLANT_v1.json", release)
    print(json.dumps({"source_lock_sha256": sha(lock_path), "release_sha256": sha(HERE / "RELEASE.json"),
                      "locked_files": len(files), "scene": SCENE, "Plant_calls": 0}, indent=2))


if __name__ == "__main__":
    main()
