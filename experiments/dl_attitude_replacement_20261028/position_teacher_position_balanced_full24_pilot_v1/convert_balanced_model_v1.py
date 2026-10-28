#!/usr/bin/env python3
"""Verify the balanced checkpoint/export pair and write MATLAB weights."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import torch
from scipy.io import savemat

HERE = Path(__file__).resolve().parent
LINEAGE = HERE / "training_lineage"
PT = HERE / "position_balanced_full24.pt"
NPZ = HERE / "position_balanced_full24_weights.npz"
RESULT = LINEAGE / "FULL24_TRAINING_RESULT_v1.json"
CONFIG = LINEAGE / "PREDECLARED_FULL24_CONFIG_v1.json"
TRAIN_SCRIPT = LINEAGE / "train_full24_deployment_model_v1.py"
MAT = HERE / "position_balanced_full24.mat"
MANIFEST = HERE / "MODEL_MANIFEST_v1.json"
SOURCE = HERE.parent / "position_cosine_gru_train24_causal_v1" / "task_aware_cv_v1"
TEACHER_NPZ = SOURCE / "TRAIN24_FEASIBILITY_TEACHER_DELTAS_v1.npz"
TEACHER_META = SOURCE / "TRAIN24_FEASIBILITY_TEACHER_MANIFEST_v1.json"
DATA_DIR = HERE.parent / "position_cosine_gru_train24_causal_v1"
DATA = DATA_DIR / "COSINE_GRU_C5_TRAIN24_POSITION_CAUSAL_PAIRS_v1.npz"
DATA_MANIFEST = DATA_DIR / "DATASET_MANIFEST_v1.json"
DATA_LOCK = DATA_DIR / "SOURCE_LOCK_v1.json"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    for p in (MAT, MANIFEST):
        if p.exists():
            raise RuntimeError(f"Refusing to overwrite {p}")
    result = json.loads(RESULT.read_text(encoding="utf-8"))
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    if (result["checkpoint_sha256"] != sha(PT) or result["weights_export_sha256"] != sha(NPZ) or
            result["config_sha256"] != sha(CONFIG) or result["script_sha256"] != sha(TRAIN_SCRIPT) or
            result["dataset_sha256"] != sha(DATA) or result["teacher_npz_sha256"] != sha(TEACHER_NPZ) or
            result["training_scene_ids"] != config["training_scene_ids"]):
        raise RuntimeError("Balanced full24 result/config/checkpoint lineage mismatch")
    ckpt = torch.load(PT, map_location="cpu", weights_only=False)
    with np.load(NPZ, allow_pickle=False) as z:
        values = {k: z[k].copy() for k in z.files}
    state_map = {
        "gru_weight_ih_l0": "gru.weight_ih_l0", "gru_weight_hh_l0": "gru.weight_hh_l0",
        "gru_bias_ih_l0": "gru.bias_ih_l0", "gru_bias_hh_l0": "gru.bias_hh_l0",
        "head_weight": "head.weight", "head_bias": "head.bias",
    }
    for export_name, state_name in state_map.items():
        if not np.array_equal(values[export_name], ckpt["state_dict"][state_name].cpu().numpy()):
            raise RuntimeError(f"NPZ export differs from checkpoint tensor {state_name}")
    if (not np.array_equal(values["input_mean"], ckpt["normalizer_mean"]) or
            not np.array_equal(values["input_std"], ckpt["normalizer_std"]) or
            ckpt["scene_ids"] != result["training_scene_ids"] or
            ckpt["teacher_npz_sha256"] != sha(TEACHER_NPZ)):
        raise RuntimeError("Checkpoint normalizer, scene IDs or teacher binding mismatch")
    if values["gru_weight_ih_l0"].shape != (96, 14) or values["gru_weight_hh_l0"].shape != (96, 32) or values["head_weight"].shape != (3, 32):
        raise RuntimeError("Unexpected balanced model dimensions")
    savemat(MAT, {
        **{k: values[k] for k in state_map},
        "input_mean": values["input_mean"], "input_std": values["input_std"],
        "seed": np.int64(ckpt["seed"]), "optimizer_steps": np.int32(ckpt["steps"]),
        "beta_rise_time_s": np.float64(1.8), "delta_limit_mps2": np.float64(0.5),
        "action_limit_mps2": np.float64(3.0), "pytorch_gru_gate_order": "reset,update,new",
    }, do_compression=True)
    teacher_meta = json.loads(TEACHER_META.read_text(encoding="utf-8"))
    manifest = {
        "schema": "POSITION_C5_TEACHER_POSITION_BALANCED_FULL24_MODEL_MANIFEST_V1",
        "weights_mat_sha256": sha(MAT), "checkpoint_sha256": sha(PT),
        "weights_export_npz_sha256": sha(NPZ), "training_result_sha256": sha(RESULT),
        "training_config_sha256": sha(CONFIG), "training_script_sha256": sha(TRAIN_SCRIPT),
        "dataset_sha256": sha(DATA), "dataset_manifest_sha256": sha(DATA_MANIFEST),
        "dataset_source_lock_sha256": sha(DATA_LOCK), "teacher_npz_sha256": sha(TEACHER_NPZ),
        "teacher_manifest_sha256": sha(TEACHER_META),
        "teacher_generator_script_sha256": sha(SOURCE / "fit_teacher_distillation_oof_v1.py"),
        "scene_count": 24, "train_scene_ids": result["training_scene_ids"],
        "seed": int(ckpt["seed"]), "optimizer_steps": int(ckpt["steps"]),
        "normalizer_scope": "all 24 TRAIN scenes only",
        "architecture": "GRU(14,32)->Linear(32,3)",
        "objective": config["objective"],
        "runtime_input": "causal X14 only; teacher excluded",
        "beta_rise_time_s": 1.8, "delta_limit_mps2": 0.5, "action_limit_mps2": 3.0,
        "teacher_used_at_inference": False,
        "teacher_manifest_schema": teacher_meta["schema"],
        "scope": "Full24 deployment fit only; no validation or OOF score produced.",
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"mat_sha256": sha(MAT), "checkpoint_sha256": sha(PT),
                      "npz_sha256": sha(NPZ), "model_manifest_sha256": sha(MANIFEST),
                      "train_scene_count": 24, "optimizer_steps": ckpt["steps"]}, indent=2), flush=True)


if __name__ == "__main__":
    main()
