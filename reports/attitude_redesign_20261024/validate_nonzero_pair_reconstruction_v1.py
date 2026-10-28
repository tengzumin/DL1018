"""Post-hoc threshold check for the existing MATLAB offline replay JSON."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "reports" / "attitude_redesign_20261024"
RESULT = OUT_DIR / "nonzero_pair_reconstruction_v1.json"
RECEIPT = OUT_DIR / "nonzero_pair_validation_receipt_v1.json"
TOL = 1e-8

EXPECTED = {
    "train": "DL1018_TRAIN_T1_C01_W00",
    "val": "DL1018_VAL_T1_C01_W08",
}
ARTIFACTS = [
    "data/events/attitude/train/DL1018_TRAIN_T1_C01_W00/B.h5",
    "data/raw/train/DL1018_TRAIN_T1_C01_W00/B/attempt_01/run_start.mat",
    "data/raw/train/DL1018_TRAIN_T1_C01_W00/B/attempt_01/raw_run.mat",
    "data/raw/train/DL1018_TRAIN_T1_C01_W00/B/attempt_01/plant_started.marker",
    "data/events/attitude/val/DL1018_VAL_T1_C01_W08/B.h5",
    "data/raw/val/DL1018_VAL_T1_C01_W08/B/attempt_01/run_start.mat",
    "data/raw/val/DL1018_VAL_T1_C01_W08/B/attempt_01/raw_run.mat",
    "data/raw/val/DL1018_VAL_T1_C01_W08/B/attempt_01/plant_started.marker",
]
SOURCES = [
    "matlab/core/simulation_parameters.m",
    "matlab/core/controller_parameters.m",
    "matlab/core/arm_mass_properties.m",
    "matlab/core/distributed_mass_properties.m",
    "matlab/core/arm_directions.m",
    "matlab/core/allocation_matrix.m",
    "matlab/core/vehicle_derivative.m",
    "matlab/data/export_attitude_events_dl1018.m",
    "matlab/runtime/run_dl1018_closed_loop.m",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


assert RESULT.is_file(), f"Missing existing replay result: {RESULT}"
assert not RECEIPT.exists(), f"Refusing to overwrite receipt: {RECEIPT}"
result = json.loads(RESULT.read_text(encoding="utf-8"))
scenes = result["scenes"]
assert len(scenes) == 2
by_split = {scene["split"]: scene for scene in scenes}
assert set(by_split) == set(EXPECTED)

checked = []
for split, scene_id in EXPECTED.items():
    scene = by_split[split]
    assert scene["scene_id"] == scene_id
    assert scene["event_alignment_exact"] is True
    assert scene["event_count"] == 1999
    assert scene["target_reconstruction_is_offline_diagnostic_only"] is True
    assert scene["replay_maxabs_error_rads2"] <= TOL
    assert scene["decomposition_closure_maxabs_rads2"] <= TOL
    assert scene["target_h5_maxabs_rads2"] > 1.0
    checked.append(
        {
            "split": split,
            "scene_id": scene_id,
            "event_count": scene["event_count"],
            "replay_maxabs_error_rads2": scene["replay_maxabs_error_rads2"],
            "decomposition_closure_maxabs_rads2": scene[
                "decomposition_closure_maxabs_rads2"
            ],
            "target_h5_maxabs_rads2": scene["target_h5_maxabs_rads2"],
            "target_h5_rms_vector_rads2": scene["target_h5_rms_vector_rads2"],
            "maxabs_realized_minus_requested_wrench_by_channel": scene[
                "maxabs_realized_minus_requested_wrench_by_channel"
            ],
        }
    )

receipt = {
    "check": "post-hoc JSON threshold verification; does not rerun MATLAB",
    "assertions_passed": True,
    "tolerance_rads2": TOL,
    "matlab_execution": {
        "executable": r"C:\Program Files\MATLAB\R2025b\bin\matlab.exe",
        "command": r'''& 'C:\Program Files\MATLAB\R2025b\bin\matlab.exe' -batch "run('reports/attitude_redesign_20261024/nonzero_pair_reconstruction_v1.m')"''',
        "os_exit_code": 0,
        "output_json": str(RESULT.relative_to(ROOT)).replace("\\", "/"),
        "separate_console_log_saved": False,
        "note": "Exit code and command are recorded from the original exec result; its JSON output is hash-pinned below.",
    },
    "matlab_result_sha256": sha256(RESULT),
    "matlab_script_sha256": sha256(OUT_DIR / "nonzero_pair_reconstruction_v1.m"),
    "python_validator_sha256": sha256(Path(__file__).resolve()),
    "python_validation": {
        "command": "python reports/attitude_redesign_20261024/validate_nonzero_pair_reconstruction_v1.py",
        "os_exit_code": 0,
        "assertion_scope": "existing MATLAB JSON replay and decomposition errors <= 1e-8 rad/s^2",
    },
    "artifact_sha256": {p: sha256(ROOT / p) for p in ARTIFACTS},
    "source_sha256": {p: sha256(ROOT / p) for p in SOURCES},
    "scenes": checked,
}
RECEIPT.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(json.dumps({"receipt": str(RECEIPT), "assertions_passed": True, "scenes": checked}, ensure_ascii=False))
