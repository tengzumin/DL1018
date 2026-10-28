#!/usr/bin/env python3
"""Verify the full24 checkpoint/NPZ pair and export MATLAB-compatible weights."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import torch
from scipy.io import savemat

HERE = Path(__file__).resolve().parent
PT = HERE / "DEPLOYMENT_MODEL_v1.pt"
NPZ = HERE / "DEPLOYMENT_WEIGHTS_v1.npz"
RESULT = HERE / "FULL24_TRAINING_RESULT_v1.json"
CONFIG = HERE / "PREDECLARED_FULL24_CONFIG_v1.json"
TRAIN_SCRIPT = HERE / "train_full24_dc_penalty_deployment_v1.py"
LOCK = HERE / "FULL24_SOURCE_LOCK_v1.json"
MAT = HERE / "DEPLOYMENT_MODEL_v1.mat"
MANIFEST = HERE / "MODEL_MANIFEST_v1.json"
REPRO = HERE / "REPRODUCIBILITY_v1.md"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    for p in (MAT, MANIFEST, REPRO):
        if p.exists():
            raise RuntimeError(f"Refusing to overwrite {p}")
    result = json.loads(RESULT.read_text(encoding="utf-8"))
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    if (result["checkpoint_sha256"] != sha(PT) or
            result["weights_export_npz_sha256"] != sha(NPZ) or
            result["config_sha256"] != sha(CONFIG) or
            result["script_sha256"] != sha(TRAIN_SCRIPT) or
            lock["training_result_sha256"] != sha(RESULT) or
            result["dataset_sha256"] != config["input_hashes"]["dataset_sha256"] or
            result["training_scene_ids"] != config["training_scene_ids"] or
            lock["checkpoint_sha256"] != sha(PT)):
        raise RuntimeError("Deployment result/config/checkpoint/source-lock lineage mismatch")
    checkpoint = torch.load(PT, map_location="cpu", weights_only=False)
    with np.load(NPZ, allow_pickle=False) as z:
        values = {k: z[k].copy() for k in z.files}
    state_map = {
        "gru_weight_ih_l0": "gru.weight_ih_l0", "gru_weight_hh_l0": "gru.weight_hh_l0",
        "gru_bias_ih_l0": "gru.bias_ih_l0", "gru_bias_hh_l0": "gru.bias_hh_l0",
        "head_weight": "head.weight", "head_bias": "head.bias",
    }
    for export_name, state_name in state_map.items():
        if not np.array_equal(values[export_name], checkpoint["state_dict"][state_name].cpu().numpy()):
            raise RuntimeError(f"NPZ differs from checkpoint tensor {state_name}")
    if (not np.array_equal(values["input_mean"], checkpoint["normalizer_mean"]) or
            not np.array_equal(values["input_std"], checkpoint["normalizer_std"]) or
            checkpoint["scene_ids"] != result["training_scene_ids"] or
            checkpoint["teacher_used_at_inference"] is not False):
        raise RuntimeError("Checkpoint normalizer or runtime scope mismatch")
    expected_shapes = {"gru_weight_ih_l0": (96, 14), "gru_weight_hh_l0": (96, 32),
                       "gru_bias_ih_l0": (96,), "gru_bias_hh_l0": (96,),
                       "head_weight": (3, 32), "head_bias": (3,),
                       "input_mean": (14,), "input_std": (14,)}
    if any(values[k].shape != shape for k, shape in expected_shapes.items()):
        raise RuntimeError("Unexpected MATLAB deployment tensor shapes")
    savemat(MAT, {
        **{k: values[k] for k in state_map},
        "input_mean": values["input_mean"], "input_std": values["input_std"],
        "seed": np.int64(checkpoint["seed"]), "optimizer_steps": np.int32(checkpoint["steps"]),
        "beta_rise_time_s": np.float64(1.8), "delta_limit_mps2": np.float64(0.5),
        "action_limit_mps2": np.float64(3.0),
        "pytorch_gru_gate_order": "reset,update,new",
        "teacher_used_at_inference": np.uint8(0),
    }, do_compression=True)
    manifest = {
        "schema": "POSITION_C5_TEACHER_POSITION_DC_PENALTY_FULL24_DEPLOY_MODEL_MANIFEST_V1",
        "weights_mat_sha256": sha(MAT), "checkpoint_sha256": sha(PT),
        "weights_export_npz_sha256": sha(NPZ), "training_result_sha256": sha(RESULT),
        "training_source_lock_sha256": sha(LOCK), "training_config_sha256": sha(CONFIG),
        "training_script_sha256": sha(TRAIN_SCRIPT),
        "dataset_sha256": result["dataset_sha256"],
        "teacher_npz_sha256": result["teacher_npz_sha256"],
        "cv_oof_sha256": result["cv_experiment_oof_sha256"],
        "training_scene_count": 24, "training_scene_ids": result["training_scene_ids"],
        "architecture": "GRU(14,32)->Linear(32,3)",
        "weights_shapes": expected_shapes,
        "normalizer_scope": "all 24 TRAIN_C5_24 causal X14 rows only",
        "objective": config["base_loss"] + " + " + config["dc_penalty"],
        "teacher_used_at_inference": False,
        "action_contract": "clip(C5_action + clip(event_time_s/1.8,0,1)*clip(delta,-0.5,0.5), -3,3) m/s^2; zero delta while not ready",
        "scope": "Full24 deployment weights only; no validation or OOF score produced; no Plant call.",
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    repro = [
        "# Full24 DC-penalty deployment model reproducibility", "",
        "This is one deterministic full24 deployment fit using the predeclared four-fold DC-penalty recipe. It is not a validation or OOF result. Teacher deltas are training supervision only; inference does not load teacher labels.", "",
        "Training: GRU(14,32) → Linear(32,3), Adam 1e-3, 300 steps, seed 20261028. Objective weights are 0.5 teacher normalized MSE, 0.5 position normalized MSE, and 0.5 per-scene DC action-mean penalty. The full24 training-only DC scale is 0.1×the full24 teacher-delta RMS.",
        "X14 normalizer and all three objective scales use only the 24 authorized TRAIN_C5_24 scenes. No VAL/TEST data were read; no Plant call or inertia reconstruction was made. No validation score was generated.", "",
        "## Artifacts", "",
        f"- PyTorch checkpoint: `DEPLOYMENT_MODEL_v1.pt` — SHA-256 `{sha(PT)}`",
        f"- NumPy weight export: `DEPLOYMENT_WEIGHTS_v1.npz` — SHA-256 `{sha(NPZ)}`",
        f"- MATLAB weights: `DEPLOYMENT_MODEL_v1.mat` — SHA-256 `{sha(MAT)}`",
        f"- Model manifest: `MODEL_MANIFEST_v1.json` — SHA-256 `{sha(MANIFEST)}`",
        f"- Training config: `PREDECLARED_FULL24_CONFIG_v1.json` — SHA-256 `{sha(CONFIG)}`",
        f"- Training script: `train_full24_dc_penalty_deployment_v1.py` — SHA-256 `{sha(TRAIN_SCRIPT)}`",
        f"- Training source lock: `FULL24_SOURCE_LOCK_v1.json` — SHA-256 `{sha(LOCK)}`",
        f"- Training result/log: `FULL24_TRAINING_RESULT_v1.json` — SHA-256 `{sha(RESULT)}`",
        "",
        "## Runtime contract", "",
        "At each 100-Hz event, input the causal X14 vector in logged order, carry the 32-value hidden state within a scene (reset it to zero at scene start; advance during warm-up), and pass the current C5 acceleration action, event time, and readiness flag. Normalize using the MAT/checkpoint mean and standard deviation; apply PyTorch GRU gate order reset/update/new; clip delta to ±0.5 m/s²; apply the 1.8-s ramp and total action clip ±3 m/s². Teacher labels are absent from this interface.",
        "",
    ]
    REPRO.write_text("\n".join(repro), encoding="utf-8")
    print(json.dumps({"mat_sha256": sha(MAT), "manifest_sha256": sha(MANIFEST),
                      "reproducibility_sha256": sha(REPRO), "checkpoint_sha256": sha(PT)}, indent=2), flush=True)


if __name__ == "__main__":
    main()
