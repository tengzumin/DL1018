from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.io import savemat


ROOT = Path(__file__).resolve().parents[4]
STUDY = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "experiments/dl_attitude_replacement_20261028/position_c5_residual_gru_full_train_v1"
DATA = ROOT / "reports/position_c5_train24_causal_dataset_v1/dataset/C5_TRAIN24_POSITION_CAUSAL_PAIRS_v1.npz"
OUT = STUDY / "audits/MATLAB_PARITY_INPUTS_v1.mat"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    model_manifest = json.loads((PACKAGE / "MODEL_MANIFEST_v1.json").read_text(encoding="utf-8"))
    replay_manifest = json.loads((PACKAGE / "EVENTWISE_REPLAY_v1.json").read_text(encoding="utf-8"))
    replay_path = PACKAGE / "EVENTWISE_REPLAY_v1.npz"
    if sha256(DATA) != model_manifest["source_data_sha256"]:
        raise RuntimeError("TRAIN24 data hash mismatch")
    if sha256(PACKAGE / "position_residual_gru_full_train24.mat") != model_manifest["mat_weights_sha256"]:
        raise RuntimeError("Frozen residual model MAT hash mismatch")
    if replay_manifest["status"] != "PASS" or sha256(replay_path) != replay_manifest["eventwise_output_sha256"]:
        raise RuntimeError("Python eventwise replay is not the frozen PASS artifact")
    with np.load(DATA, allow_pickle=False) as z, np.load(replay_path, allow_pickle=False) as ref:
        x14 = z["x14_model_input"].astype(np.float32)
        applied = z["applied_acceleration_event_mps2"].astype(np.float32)
        time_s = z["event_time_s"].astype(np.float32)
        ready = z["ready_mask"].astype(np.uint8)
        py_delta = ref["emitted_delta_mps2"].astype(np.float32)
        py_action = ref["predicted_action_mps2"].astype(np.float32)
        scene_ids = z["scene_ids"].astype(str)
    if x14.shape != (24, 1999, 14) or applied.shape != (24, 1999, 3):
        raise RuntimeError("Unexpected frozen TRAIN24 input shape")
    if not np.isfinite(x14).all() or not np.isfinite(applied).all():
        raise RuntimeError("Non-finite TRAIN24 X14 or applied action")
    if not np.array_equal(ready, np.broadcast_to(np.arange(1999) >= 31, ready.shape)):
        raise RuntimeError("Ready mask differs from the frozen 31-event warmup")
    savemat(OUT, {"x14": x14, "base_action": applied, "event_time_s": time_s,
                  "ready": ready, "python_delta": py_delta, "python_action": py_action,
                  "scene_ids": scene_ids.reshape(-1, 1)}, do_compression=True)
    receipt = {
        "schema": "POSITION_RESIDUAL_GRU_MATLAB_PARITY_INPUTS_V1",
        "status": "READY",
        "scene_count": 24,
        "events_per_scene": 1999,
        "ready_events_per_scene": 1968,
        "first_event_time_s": float(time_s[0, 0]),
        "first_ready_event_index_zero_based": 31,
        "first_ready_event_time_s": float(time_s[0, 31]),
        "pre_ready_x14_finite": bool(np.isfinite(x14[:, :31]).all()),
        "data_sha256": sha256(DATA),
        "python_replay_sha256": sha256(replay_path),
        "model_mat_sha256": sha256(PACKAGE / "position_residual_gru_full_train24.mat"),
        "parity_input_sha256": sha256(OUT),
        "scene_ids": scene_ids.tolist(),
        "scope": "TRAIN24 only; no TEST, Plant, or inertia reconstruction",
    }
    (STUDY / "audits/MATLAB_PARITY_INPUTS_v1.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
