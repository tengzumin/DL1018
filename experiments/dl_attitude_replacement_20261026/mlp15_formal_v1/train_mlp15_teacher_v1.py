#!/usr/bin/env python3
"""Formal 13-feature, 15-event MLP distillation of the B attitude-RBF action."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"

import numpy as np
import torch
from scipy.io import savemat
from torch import nn
from torch.nn import functional as F


TASK_ROOT = Path(__file__).resolve().parents[1]
RUN_ROOT = Path(__file__).resolve().parent
SCREEN_ROOT = TASK_ROOT / "architecture_screen_v1"
DATASET = TASK_ROOT / "dataset_v4_teacher_distill" / "attitude_rbf_teacher_train_val_v2.npz"
MANIFEST = TASK_ROOT / "dataset_v4_teacher_distill" / "DATASET_MANIFEST_v2.json"
AMENDMENT = TASK_ROOT / "DL_ATTITUDE_REPLACEMENT_TASKBOOK_v1_AMENDMENT09_MLP15_FORMAL_TRAINING.md"
SCREEN_AUDIT = SCREEN_ROOT / "SCREEN_AUDIT_v1.json"
RELEASE = RUN_ROOT / "TRAINING_RELEASE_v1.json"
OUTPUT = RUN_ROOT / "run_v1"
SEED = 2026102001
STEPS = 60000
BATCH = 512
WINDOW = 15
INPUT_DIM = 13
VAL_BATCH = 4096
VAL_EVERY = 1000


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: dict[str, Any]) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(path)


def load_models():
    import sys

    sys.path.insert(0, str(SCREEN_ROOT))
    from screen_attitude_architectures_v1 import MLP15, make_windows

    return MLP15, make_windows


def evaluate(
    model: nn.Module,
    padded: torch.Tensor,
    y_val: np.ndarray,
    target_rms: np.ndarray,
    make_windows,
    device: torch.device,
) -> tuple[float, list[float], list[float]]:
    model.eval()
    scene_count, event_count, _ = y_val.shape
    prediction = np.empty(y_val.shape, dtype=np.float32)
    total = scene_count * event_count
    with torch.inference_mode():
        for start in range(0, total, VAL_BATCH):
            stop = min(start + VAL_BATCH, total)
            flat = torch.arange(start, stop, device=device)
            scenes = torch.div(flat, event_count, rounding_mode="floor")
            steps = torch.remainder(flat, event_count)
            windows = make_windows(padded, scenes, steps)
            prediction.reshape(-1, 3)[start:stop] = model(windows).cpu().numpy()
    error_norm = prediction.astype(np.float64) - y_val.astype(np.float64) / target_rms
    scene_macro = float(np.mean(np.sqrt(np.mean(error_norm ** 2, axis=(1, 2)))))
    error_phys = error_norm * target_rms
    axis_macro = np.mean(np.sqrt(np.mean(error_phys ** 2, axis=1)), axis=0).tolist()
    axis_pooled = np.sqrt(np.mean(error_phys ** 2, axis=(0, 1))).tolist()
    return scene_macro, axis_macro, axis_pooled


def save_atomic_checkpoint(path: Path, payload: dict[str, Any]) -> str:
    temp = path.with_suffix(path.suffix + ".tmp")
    torch.save(payload, temp)
    temp.replace(path)
    return sha256(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    release = json.loads(RELEASE.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    audit = json.loads(SCREEN_AUDIT.read_text(encoding="utf-8"))
    MLP15, make_windows = load_models()
    if release.get("status") != "FROZEN" or release.get("schema") != "DL1018_MLP15_TEACHER_TRAINING_RELEASE_V1":
        raise ValueError("formal MLP release is not frozen")
    expected_hashes = {
        "trainer_sha256": sha256(Path(__file__).resolve()),
        "amendment_sha256": sha256(AMENDMENT),
        "screen_script_sha256": sha256(SCREEN_ROOT / "screen_attitude_architectures_v1.py"),
        "screen_audit_sha256": sha256(SCREEN_AUDIT),
        "dataset_sha256": sha256(DATASET),
        "manifest_sha256": sha256(MANIFEST),
    }
    for key, value in expected_hashes.items():
        if release.get(key) != value:
            raise ValueError(f"frozen release hash mismatch: {key}")
    if (
        audit.get("status") != "PASS_INDEPENDENT_VAL48_RECOMPUTE"
        or audit.get("ranking", [None])[0] != "MLP15"
        or manifest.get("status") != "PASS"
        or manifest.get("split_counts") != {"TRAIN": 768, "VAL": 48}
        or manifest.get("feature_order") != [
            "attitude_error_euler_rad_x3", "body_rate_rad_s_x3",
            "nominal_bs_body_torque_Nm_x3", "morph_command_x4",
        ]
        or manifest.get("target") != "logged rbf_output_raw at event k, pre-beta, rad/s^2"
        or manifest.get("plant_truth_read") is not False
        or manifest.get("nominal_inertia_read") is not False
        or manifest.get("test_data_read") is not False
        or sha256(DATASET) != manifest.get("npz_sha256")
    ):
        raise ValueError("screen/data contract is not eligible for formal training")

    if OUTPUT.exists() and not args.resume:
        raise FileExistsError(f"refusing to overwrite formal output: {OUTPUT}")
    if args.resume and not OUTPUT.is_dir():
        raise FileNotFoundError("--resume requested but formal output directory is absent")

    with np.load(DATASET, allow_pickle=False) as data:
        train_x = np.asarray(data["train_x"], dtype=np.float32)
        train_y = np.asarray(data["train_y"], dtype=np.float32)
        val_x = np.asarray(data["val_x"], dtype=np.float32)
        val_y = np.asarray(data["val_y"], dtype=np.float32)
    if train_x.shape != (768, 1999, INPUT_DIM) or train_y.shape != (768, 1999, 3):
        raise ValueError("unexpected TRAIN shapes")
    if val_x.shape != (48, 1999, INPUT_DIM) or val_y.shape != (48, 1999, 3):
        raise ValueError("unexpected VAL shapes")
    if not all(np.isfinite(a).all() for a in (train_x, train_y, val_x, val_y)):
        raise ValueError("non-finite dataset values")

    mean = train_x.mean(axis=(0, 1), dtype=np.float64)
    std_raw = train_x.std(axis=(0, 1), dtype=np.float64)
    std = np.maximum(std_raw, 1e-6)
    target_rms = np.sqrt(np.mean(train_y.astype(np.float64) ** 2, axis=(0, 1)))
    if not np.isfinite(np.r_[mean, std, target_rms]).all() or np.any(target_rms <= 1e-8):
        raise ValueError("invalid TRAIN-only normalization")
    train_norm = ((train_x - mean) / std).astype(np.float32)
    val_norm = ((val_x - mean) / std).astype(np.float32)
    train_target = (train_y / target_rms).astype(np.float32)

    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    torch.use_deterministic_algorithms(True)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(SEED)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    train_pad = F.pad(
        torch.as_tensor(train_norm, device=device).permute(0, 2, 1),
        (WINDOW - 1, 0),
    )
    val_pad = F.pad(
        torch.as_tensor(val_norm, device=device).permute(0, 2, 1),
        (WINDOW - 1, 0),
    )
    target_tensor = torch.as_tensor(train_target, device=device)
    rng = np.random.default_rng(SEED)
    model = MLP15().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
    progress_path = OUTPUT / "training_progress.json"
    latest_path = OUTPUT / "latest.pt"
    history_path = OUTPUT / "training_history.jsonl"
    best_step = 0
    best_metric = float("inf")
    start_step = 1

    if args.resume:
        progress = json.loads(progress_path.read_text(encoding="utf-8"))
        latest_hash = sha256(latest_path)
        if progress.get("status") not in ("RUNNING", "INTERRUPTED") or progress.get("latest_sha256") != latest_hash:
            raise ValueError("resume checkpoint/status identity mismatch")
        resume = torch.load(latest_path, map_location=device, weights_only=False)
        if resume.get("schema") != "DL1018_MLP15_RESUME_V1" or resume.get("data_sha256") != sha256(DATASET):
            raise ValueError("resume checkpoint does not match frozen data")
        model.load_state_dict(resume["model_state"])
        optimizer.load_state_dict(resume["optimizer_state"])
        rng.bit_generator.state = resume["numpy_rng_state"]
        torch.set_rng_state(resume["torch_rng_state"].cpu())
        if torch.cuda.is_available() and resume.get("cuda_rng_state"):
            torch.cuda.set_rng_state_all(resume["cuda_rng_state"])
        start_step = int(resume["step"]) + 1
        best_step = int(resume["best_step"])
        best_metric = float(resume["best_metric"])
    else:
        OUTPUT.mkdir(parents=True)
        progress = {
            "schema": "DL1018_MLP15_TEACHER_TRAINING_PROGRESS_V1",
            "status": "RUNNING", "completed_steps": 0, "target_steps": STEPS,
            "seed": SEED, "dataset_sha256": sha256(DATASET),
            "manifest_sha256": sha256(MANIFEST), "plant_called": False,
            "test_data_read": False,
        }
        best_metric = evaluate(model, val_pad, val_y, target_rms, make_windows, device)[0]
        best_step = 0
        save_atomic_checkpoint(OUTPUT / "initial.pt", {
            "step": 0, "state_dict": {k: v.detach().cpu().clone() for k, v in model.state_dict().items()},
        })
        save_atomic_checkpoint(OUTPUT / "best.pt", {
            "step": 0, "state_dict": {k: v.detach().cpu().clone() for k, v in model.state_dict().items()},
            "val_scene_macro_teacher_action_rmse": best_metric,
            "dataset_sha256": sha256(DATASET),
        })
        latest_hash = save_atomic_checkpoint(latest_path, {
            "schema": "DL1018_MLP15_RESUME_V1", "step": 0,
            "data_sha256": sha256(DATASET),
            "model_state": model.state_dict(), "optimizer_state": optimizer.state_dict(),
            "numpy_rng_state": rng.bit_generator.state,
            "torch_rng_state": torch.get_rng_state(),
            "cuda_rng_state": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else [],
            "best_step": best_step, "best_metric": best_metric,
        })
        progress.update({
            "best_step": best_step, "best_val_scene_macro_teacher_action_rmse": best_metric,
            "latest_sha256": latest_hash, "updated_utc": datetime.now(timezone.utc).isoformat(),
        })
        write_json(progress_path, progress)

    for step in range(start_step, STEPS + 1):
        scenes = torch.as_tensor(rng.integers(0, train_x.shape[0], BATCH, dtype=np.int64), device=device)
        times = torch.as_tensor(rng.integers(0, train_x.shape[1], BATCH, dtype=np.int64), device=device)
        x = make_windows(train_pad, scenes, times)
        y = target_tensor[scenes, times]
        model.train()
        optimizer.zero_grad(set_to_none=True)
        prediction = model(x)
        loss = F.smooth_l1_loss(prediction, y, beta=1.0)
        if not torch.isfinite(loss):
            raise FloatingPointError(f"non-finite loss at step {step}")
        loss.backward()
        optimizer.step()

        if step % VAL_EVERY == 0 or step == STEPS:
            val_start = time.perf_counter()
            metric, axis_macro, axis_pooled = evaluate(
                model, val_pad, val_y, target_rms, make_windows, device,
            )
            val_seconds = time.perf_counter() - val_start
            if metric < best_metric:
                best_metric, best_step = metric, step
                save_atomic_checkpoint(OUTPUT / "best.pt", {
                    "step": step, "state_dict": {k: v.detach().cpu().clone()
                                                   for k, v in model.state_dict().items()},
                    "val_scene_macro_teacher_action_rmse": metric,
                    "dataset_sha256": sha256(DATASET),
                })
            row = {
                "step": step, "train_loss": float(loss.item()),
                "val_scene_macro_teacher_action_rmse": metric,
                "val_axis_scene_macro_rmse_rad_s2": axis_macro,
                "val_axis_pooled_rmse_rad_s2": axis_pooled,
                "validation_seconds": val_seconds,
            }
            with history_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            resume_payload = {
                "schema": "DL1018_MLP15_RESUME_V1", "step": step,
                "data_sha256": sha256(DATASET),
                "model_state": model.state_dict(),
                "optimizer_state": optimizer.state_dict(),
                "numpy_rng_state": rng.bit_generator.state,
                "torch_rng_state": torch.get_rng_state(),
                "cuda_rng_state": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else [],
                "best_step": best_step, "best_metric": best_metric,
            }
            latest_hash = save_atomic_checkpoint(latest_path, resume_payload)
            progress = {
                "schema": "DL1018_MLP15_TEACHER_TRAINING_PROGRESS_V1",
                "status": "RUNNING", "completed_steps": step, "target_steps": STEPS,
                "best_step": best_step, "best_val_scene_macro_teacher_action_rmse": best_metric,
                "latest_train_loss": float(loss.item()), "latest_sha256": latest_hash,
                "updated_utc": datetime.now(timezone.utc).isoformat(),
                "seed": SEED, "dataset_sha256": sha256(DATASET),
                "manifest_sha256": sha256(MANIFEST), "plant_called": False,
                "test_data_read": False,
            }
            write_json(progress_path, progress)
            print(json.dumps(row | {"best_step": best_step, "best_metric": best_metric}, ensure_ascii=False), flush=True)

    final_path = OUTPUT / "final.pt"
    save_atomic_checkpoint(final_path, {
        "step": STEPS, "state_dict": {k: v.detach().cpu().clone() for k, v in model.state_dict().items()},
    })
    best = torch.load(OUTPUT / "best.pt", map_location=device, weights_only=True)
    model.load_state_dict(best["state_dict"])
    model.eval()
    state = model.state_dict()
    savemat(OUTPUT / "mlp15_attitude_weights_v1.mat", {
        "input_mean": mean, "input_std": std, "target_rms": target_rms,
        "fc1_weight": state["net.0.weight"].cpu().numpy().astype(np.float64),
        "fc1_bias": state["net.0.bias"].cpu().numpy().astype(np.float64),
        "fc2_weight": state["net.2.weight"].cpu().numpy().astype(np.float64),
        "fc2_bias": state["net.2.bias"].cpu().numpy().astype(np.float64),
        "head_weight": state["net.4.weight"].cpu().numpy().astype(np.float64),
        "head_bias": state["net.4.bias"].cpu().numpy().astype(np.float64),
    }, do_compression=True, oned_as="row")

    flat = torch.tensor([100], device=device)
    scene = torch.tensor([0], device=device)
    time_index = torch.tensor([100], device=device)
    window = make_windows(val_pad, scene, time_index).cpu().numpy()[0]
    with torch.inference_mode():
        expected = model(torch.from_numpy(window[None]).to(device)).cpu().numpy()[0] * target_rms
    savemat(OUTPUT / "parity_vector_v1.mat", {
        "input_raw_window": val_x[0, 100 - WINDOW + 1:101].astype(np.float64),
        "input_normalized_window": window.astype(np.float64),
        "expected_teacher_action_rad_s2": expected.astype(np.float64),
        "scene_index_zero_based": np.asarray([[0]], dtype=np.int32),
        "event_index_zero_based": flat.cpu().numpy().reshape(1, 1).astype(np.int32),
    }, do_compression=True, oned_as="row")
    config = {
        "schema": "DL1018_MLP15_TEACHER_TRAINING_CONFIG_V1",
        "status": "PASS", "architecture": "MLP15", "input_dim": INPUT_DIM,
        "window_events": WINDOW, "flatten_order": "event-major, feature-minor",
        "hidden": [64, 32], "activation": "SiLU", "output_dim": 3,
        "seed": SEED, "optimizer_steps": STEPS, "batch_size": BATCH,
        "validation_interval": VAL_EVERY, "optimizer": "Adam",
        "learning_rate": 1e-3, "weight_decay": 1e-5,
        "loss": "SmoothL1(beta=1.0)",
        "selection": "earliest strict minimum full VAL48 normalized scene-macro teacher-action RMSE",
        "target": "B logged rbf_output_raw at event k, pre-beta, rad/s^2",
        "best_step": best_step, "best_val_scene_macro_teacher_action_rmse": best_metric,
        "input_mean_fit_split": "TRAIN", "input_std_fit_split": "TRAIN",
        "target_rms_fit_split": "TRAIN",
        "dataset_sha256": sha256(DATASET), "manifest_sha256": sha256(MANIFEST),
        "training_release_sha256": sha256(RELEASE),
        "trainer_sha256": sha256(Path(__file__).resolve()),
        "taskbook_amendment_sha256": sha256(AMENDMENT),
        "screen_audit_sha256": sha256(SCREEN_AUDIT),
        "test_data_read": False, "plant_truth_read": False,
        "variable_inertia_reconstruction_used": False,
        "device": str(device), "torch_version": torch.__version__,
        "gpu_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU",
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }
    write_json(OUTPUT / "training_config.json", config)
    progress.update({
        "status": "PASS", "completed_steps": STEPS, "best_step": best_step,
        "best_val_scene_macro_teacher_action_rmse": best_metric,
        "final_sha256": sha256(final_path),
        "weights_sha256": sha256(OUTPUT / "mlp15_attitude_weights_v1.mat"),
        "updated_utc": datetime.now(timezone.utc).isoformat(),
    })
    write_json(progress_path, progress)
    print(json.dumps({
        "status": "PASS", "best_step": best_step, "best_metric": best_metric,
        "output": str(OUTPUT), "test_data_read": False, "plant_called": False,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
