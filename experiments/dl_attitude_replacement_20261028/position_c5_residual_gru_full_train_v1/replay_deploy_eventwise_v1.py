#!/usr/bin/env python3
"""Independent one-event-at-a-time CPU replay of the exported GRU package."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import torch
from scipy.io import loadmat
from torch import nn


ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
DATA = ROOT / "reports/position_c5_train24_causal_dataset_v1/dataset/C5_TRAIN24_POSITION_CAUSAL_PAIRS_v1.npz"
CKPT = OUT / "position_residual_gru_full_train24.pt"
MAT = OUT / "position_residual_gru_full_train24.mat"
REFERENCE = OUT / "BATCH_SEQUENCE_REFERENCE_v1.npz"
MODEL_MANIFEST = OUT / "MODEL_MANIFEST_v1.json"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


class InferenceModel(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.gru = nn.GRU(input_size=14, hidden_size=32, num_layers=1, batch_first=True)
        self.head = nn.Linear(32, 3)


def main() -> None:
    manifest = json.loads(MODEL_MANIFEST.read_text(encoding="utf-8"))
    if sha256(DATA).lower() != manifest["source_data_sha256"].lower():
        raise RuntimeError("TRAIN24 data hash does not match package manifest")
    if sha256(CKPT).lower() != manifest["checkpoint_sha256"].lower():
        raise RuntimeError("PyTorch checkpoint hash mismatch")
    if sha256(MAT).lower() != manifest["mat_weights_sha256"].lower():
        raise RuntimeError("MAT weight file hash mismatch")
    if sha256(REFERENCE).lower() != manifest["batch_reference_sha256"].lower():
        raise RuntimeError("Batch-sequence reference hash mismatch")

    # Read only causal features, readiness, event time, and the C5 action being corrected.
    with np.load(DATA, allow_pickle=False) as z:
        ids = z["scene_ids"].astype(str)
        x = z["x14_model_input"].astype(np.float32)
        ready = z["ready_mask"].astype(bool)
        time_s = z["event_time_s"].astype(np.float32)
        applied = z["applied_acceleration_event_mps2"].astype(np.float32)
    if not np.isfinite(x).all() or not np.isfinite(applied).all():
        raise RuntimeError("Non-finite causal input/action found")
    expected_ready = np.broadcast_to(np.arange(x.shape[1]) >= 31, ready.shape)
    if not np.array_equal(ready, expected_ready):
        raise RuntimeError("Unexpected ready mask; expected warmup through event index 30")
    if not np.allclose(time_s[:, 0], 0.01, atol=2e-7, rtol=0):
        raise RuntimeError("Event stream must start at t=0.01s")
    if not np.allclose(time_s[:, 31], 0.32, atol=2e-7, rtol=0):
        raise RuntimeError("First ready event must occur at t=0.32s (zero-based event index 31)")
    with np.load(REFERENCE, allow_pickle=False) as z:
        ref_delta = z["emitted_delta_mps2"].astype(np.float32)
        ref_action = z["predicted_action_mps2"].astype(np.float32)

    package = torch.load(CKPT, map_location="cpu", weights_only=False)
    model = InferenceModel().cpu()
    model.load_state_dict(package["state_dict"], strict=True)
    model.eval()
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    mean = np.asarray(package["input_mean"], dtype=np.float32)
    std = np.asarray(package["input_std"], dtype=np.float32)
    rise = float(package["beta_rise_time_s"])
    delta_limit = float(package["delta_limit_mps2"])
    action_limit = float(package["action_limit_mps2"])

    # Cross-check every exported matrix against the separate MATLAB MAT artifact.
    mat = loadmat(MAT)
    state = package["state_dict"]
    mat_pairs = {
        "gru_weight_ih_l0": "gru.weight_ih_l0", "gru_weight_hh_l0": "gru.weight_hh_l0",
        "gru_bias_ih_l0": "gru.bias_ih_l0", "gru_bias_hh_l0": "gru.bias_hh_l0",
        "head_weight": "head.weight", "head_bias": "head.bias",
    }
    for mat_name, torch_name in mat_pairs.items():
        if not np.array_equal(mat[mat_name].squeeze(), state[torch_name].cpu().numpy().squeeze()):
            raise RuntimeError(f"MAT/PyTorch weight mismatch: {mat_name}")
    if not np.array_equal(mat["input_mean"].reshape(-1), mean) or not np.array_equal(mat["input_std"].reshape(-1), std):
        raise RuntimeError("MAT/PyTorch normalizer mismatch")

    emitted = np.zeros((len(ids), x.shape[1], 3), dtype=np.float32)
    action = np.zeros_like(emitted)
    pre_ready_hidden_norm = []
    with torch.no_grad():
        for scene in range(len(ids)):
            hidden = None  # explicit reset at every scene boundary
            for event in range(x.shape[1]):
                xn = (x[scene, event] - mean) / std
                xt = torch.from_numpy(xn).view(1, 1, 14)
                sequence_out, hidden = model.gru(xt, hidden)
                if event == 30:
                    pre_ready_hidden_norm.append(float(torch.linalg.vector_norm(hidden).item()))
                raw = model.head(sequence_out[:, 0, :]).cpu().numpy()[0]
                delta = np.clip(raw, -delta_limit, delta_limit) if ready[scene, event] else np.zeros(3, dtype=np.float32)
                beta = float(np.clip(time_s[scene, event] / rise, 0.0, 1.0))
                emitted[scene, event] = delta
                action[scene, event] = np.clip(applied[scene, event] + beta * delta,
                                                -action_limit, action_limit)

    delta_err = np.abs(emitted - ref_delta)
    action_err = np.abs(action - ref_action)
    max_delta = float(delta_err.max())
    max_action = float(action_err.max())
    unready_zero = bool(np.count_nonzero(emitted[~ready]) == 0)
    warmup_hidden_ok = bool(np.isfinite(pre_ready_hidden_norm).all() and np.all(np.asarray(pre_ready_hidden_norm) > 0))
    passed = max_delta <= 2e-6 and max_action <= 2e-6 and unready_zero and warmup_hidden_ok
    replay_path = OUT / "EVENTWISE_REPLAY_v1.npz"
    np.savez_compressed(replay_path, scene_ids=ids, emitted_delta_mps2=emitted,
                        predicted_action_mps2=action, ready_mask=ready, event_time_s=time_s)
    result = {
        "schema": "POSITION_RESIDUAL_GRU_EVENTWISE_REPLAY_V1",
        "status": "PASS" if passed else "FAIL",
        "scene_count": int(len(ids)), "events_per_scene": int(x.shape[1]),
        "total_events": int(x.shape[0] * x.shape[1]), "ready_events": int(ready.sum()),
        "per_scene_hidden_reset": True, "unready_delta_exactly_zero": unready_zero,
        "events_processed_from_first_event": True,
        "first_event_time_s": float(time_s[0, 0]),
        "first_ready_event_index_zero_based": 31,
        "first_ready_event_time_s": float(time_s[0, 31]),
        "pre_ready_x14_finite": bool(np.isfinite(x[:, :31]).all()),
        "warmup_hidden_state_finite_and_nonzero_all_scenes": warmup_hidden_ok,
        "warmup_hidden_norm_min_max": [float(np.min(pre_ready_hidden_norm)), float(np.max(pre_ready_hidden_norm))],
        "max_abs_delta_vs_batch_sequence_mps2": max_delta,
        "max_abs_action_vs_batch_sequence_mps2": max_action,
        "mat_weight_and_normalizer_arrays_match_pytorch": True,
        "replay_script_sha256": sha256(Path(__file__)),
        "fit_script_sha256": manifest["fit_script_sha256"],
        "source_manifest_sha256": manifest["source_manifest_sha256"],
        "source_label_alignment_sha256": manifest["source_label_alignment_sha256"],
        "data_sha256": sha256(DATA), "checkpoint_sha256": sha256(CKPT),
        "mat_weights_sha256": sha256(MAT), "eventwise_output_sha256": sha256(replay_path),
        "scope": "Python numerical replay only; no TEST, Plant, inertia reconstruction, or closed-loop integration",
        "deployment_caveat": "MAT file preserves raw PyTorch GRU gate order/reset convention; MATLAB runtime integration still requires separate interface and numerical review.",
    }
    (OUT / "EVENTWISE_REPLAY_v1.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
