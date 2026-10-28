#!/usr/bin/env python3
"""Create an inference-only TRAIN fixture for PT-versus-MATLAB GRU parity."""
from __future__ import annotations
import json, sys
from pathlib import Path
import numpy as np
import torch
from scipy.io import loadmat, savemat

TASK = Path(__file__).resolve().parent
ROOT = TASK.parents[2]
RUN = TASK / "runs/GRU13_B768_COSINE_S2026102001"
DATA = ROOT / "experiments/dl_attitude_replacement_20261028/large_attitude_b768_root_v1/DATASET.npz"
WEIGHTS = RUN / "gru_stream_large_b768_weights_v1.mat"
CHECKPOINT = RUN / "final_step_60000.pt"
SCREEN = ROOT / "experiments/dl_attitude_replacement_20261026/architecture_screen_v1"

def main():
    progress = json.loads((RUN / "training_progress.json").read_text(encoding="utf-8"))
    if progress.get("status") != "PASS" or progress.get("completed_steps") != 60000:
        raise RuntimeError("parity requires the completed 60k checkpoint")
    for path in (CHECKPOINT, WEIGHTS, DATA):
        if not path.is_file(): raise FileNotFoundError(path)
    sys.path.insert(0, str(SCREEN))
    from screen_attitude_architectures_v1 import GRU15
    ckpt = torch.load(CHECKPOINT, map_location="cpu", weights_only=False)
    model = GRU15().cpu().eval()
    model.load_state_dict(ckpt["state_dict"], strict=True)
    mean = ckpt["input_mean"].detach().cpu().numpy().astype(np.float32).reshape(13)
    std = ckpt["input_std"].detach().cpu().numpy().astype(np.float32).reshape(13)
    rms = ckpt["target_rms"].detach().cpu().numpy().astype(np.float32).reshape(3)
    mat = loadmat(WEIGHTS)
    pairs = (("input_mean", mean), ("input_std", std), ("target_rms", rms),
             ("gru_weight_ih", ckpt["state_dict"]["gru.weight_ih_l0"].numpy()),
             ("gru_weight_hh", ckpt["state_dict"]["gru.weight_hh_l0"].numpy()),
             ("gru_bias_ih", ckpt["state_dict"]["gru.bias_ih_l0"].numpy()),
             ("gru_bias_hh", ckpt["state_dict"]["gru.bias_hh_l0"].numpy()),
             ("head_weight", ckpt["state_dict"]["head.weight"].numpy()),
             ("head_bias", ckpt["state_dict"]["head.bias"].numpy()))
    for name, expected in pairs:
        if name not in mat or not np.array_equal(np.asarray(mat[name]).reshape(expected.shape), expected):
            raise AssertionError(f"MAT export differs from PT checkpoint: {name}")
    with np.load(DATA, allow_pickle=False) as z:
        raw = z["train_x"][0].copy(); episode_id = str(z["train_ids"][0])
    if raw.shape != (1999, 13) or not np.isfinite(raw).all():
        raise ValueError("expected one finite 1999x13 TRAIN episode")
    x = torch.from_numpy(((raw - mean) / std).astype(np.float32)).unsqueeze(0)
    with torch.inference_mode():
        seq, _ = model.gru(x)
        expected_raw = (model.head(seq)[0].numpy() * rms).astype(np.float64)
        hidden = None; step_outputs = []; step_hidden = []
        for k in range(raw.shape[0]):
            one, hidden = model.gru(x[:, k:k + 1], hidden)
            step_outputs.append((model.head(one)[0, 0].numpy() * rms).astype(np.float64))
            step_hidden.append(hidden[0, 0].numpy().astype(np.float64))
        step_outputs = np.asarray(step_outputs); step_hidden = np.asarray(step_hidden)
        reset_hidden = None; reset_outputs = []
        for k in range(raw.shape[0]):
            one, reset_hidden = model.gru(x[:, k:k + 1], reset_hidden)
            reset_outputs.append((model.head(one)[0, 0].numpy() * rms).astype(np.float64))
        reset_outputs = np.asarray(reset_outputs)
    max_pt_step_error = float(np.max(np.abs(step_outputs - expected_raw)))
    if max_pt_step_error > 2e-4 or not np.array_equal(reset_outputs, step_outputs):
        raise AssertionError(f"PT continuous/reset check failed: max={max_pt_step_error:g}")
    fixture = RUN / "MATLAB_PARITY_FIXTURE_v1.mat"
    savemat(fixture, {"input_features_raw": raw.astype(np.float64),
        "expected_raw_output_pt": expected_raw, "expected_hidden_after_pt": step_hidden,
        "train_episode_id": episode_id, "event_count": np.array([[raw.shape[0]]], dtype=np.int32),
        "input_mean": mean.reshape(1, -1).astype(np.float64),
        "input_std": std.reshape(1, -1).astype(np.float64),
        "target_rms": rms.reshape(1, -1).astype(np.float64)}, do_compression=True, oned_as="row")
    result = {"status": "PASS_PYTHON_FIXTURE_READY", "train_episode_id": episode_id,
        "event_count": int(raw.shape[0]), "pt_mat_weights_exact": True,
        "pt_full_vs_stepwise_max_abs_output": max_pt_step_error, "reset_replay_exact": True,
        "fixture": str(fixture), "matlab_forward_helper": "gru_stream_attitude_forward_v1",
        "tolerance_matlab_vs_pt_output_abs": 1e-3, "tolerance_matlab_vs_pt_hidden_abs": 2e-4}
    (RUN / "PYTHON_PARITY_PRECHECK_v1.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))

if __name__ == "__main__": main()
