#!/usr/bin/env python3
"""Train one MLP15 with a frozen 50/50 base-C5 vs GHP7 teacher sampler."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

import numpy as np
import torch
from scipy.io import savemat
from torch.nn import functional as F

TASK_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = TASK_ROOT.parents[2]
RESEARCH_ROOT = PROJECT_ROOT / "experiments/dl_attitude_replacement_20261026"
BASE_TASK = RESEARCH_ROOT / "mlp15_c5_teacher_full72_v1"
BASE_DATA_TASK = RESEARCH_ROOT / "mlp15_c5_teacher_redistill_v1"
SCREEN_ROOT = RESEARCH_ROOT / "architecture_screen_v1"
TRAIN_BUNDLE = TASK_ROOT / "data/ghp7_g1_g2_train_v1.npz"
DATA_MANIFEST = TASK_ROOT / "data/GHP7_TEACHER_DATA_MANIFEST_v1.json"
LOCK_PATH = TASK_ROOT / "MLP15_C5_GHP7_BALANCE_SOURCE_LOCK_v1.json"
OUTPUT_DIR = TASK_ROOT / "runs/C5_MLP15_GHP7_BALANCE_SEED2026102001"

SEED, STEPS, BATCH, WINDOW, INPUT_DIM = 2026102001, 60_000, 512, 15, 13
BASE_SCENES, GHP7_SCENES = 72, 4
HALF_BATCH = BATCH // 2
FEATURE_ORDER = [
    "wrapped_attitude_error_euler_rad_x3", "body_rate_rad_s_x3",
    "nominal_bs_body_torque_Nm_x3", "morph_command_x4",
]
TRAIN_IDS = [
    "DL1018_GHP7_G1_W00", "DL1018_GHP7_G1_W12",
    "DL1018_GHP7_G2_W00", "DL1018_GHP7_G2_W12",
]
D_MAX = np.asarray([45.0, 45.0, 4.7124], dtype=np.float64)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_array(array: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def write_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def load_release() -> dict[str, Any]:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    release = lock.get("training_release", {})
    if (lock.get("status") != "APPROVED_FOR_OFFLINE_TRAINING"
            or release.get("approved") is not True or release.get("authorized_jobs") != 1
            or not release.get("approved_by") or not release.get("approval_reference")):
        raise PermissionError("source lock is pending root review; offline training is not released")
    for relative, expected in lock["source_file_sha256"].items():
        path = (PROJECT_ROOT / relative).resolve(strict=True)
        path.relative_to(PROJECT_ROOT.resolve())
        if sha256_file(path) != expected:
            raise ValueError(f"locked source hash mismatch: {relative}")
    if sha256_file(TRAIN_BUNDLE) != lock["ghp7_train_bundle_sha256"]:
        raise ValueError("GHP7 training bundle SHA mismatch")
    if sha256_file(BASE_DATA_TASK / "matched_teacher_data_v1.npz") != lock["base_dataset_sha256"]:
        raise ValueError("base C5 teacher data SHA mismatch")
    return lock


def fit_normalizer(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mean = x.mean(axis=(0, 1), dtype=np.float64)
    std = np.maximum(x.std(axis=(0, 1), dtype=np.float64), 1e-6)
    target_rms = np.sqrt(np.mean(y.astype(np.float64) ** 2, axis=(0, 1)))
    if not np.isfinite(np.r_[mean, std, target_rms]).all() or np.any(target_rms <= 1e-8):
        raise ValueError("invalid mixed-training normalizer")
    return mean, std, target_rms


def load_training_arrays(lock: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, list[str]]:
    sys.path.insert(0, str(BASE_TASK))
    import train_mlp15_c5_full72_v1 as base

    old_lock = base.load_and_verify_lock(require_release=False)
    _, _, base_ids = base._validate_manifest(old_lock)
    base_x, base_y = base._load_c5_training_arrays(old_lock, base_ids)
    with np.load(TRAIN_BUNDLE, allow_pickle=False) as archive:
        ghp_x = np.asarray(archive["x"], dtype=np.float32)
        ghp_y = np.asarray(archive["y"], dtype=np.float32)
        ghp_ids = np.asarray(archive["scene_ids"]).astype(str).tolist()
    if ghp_ids != TRAIN_IDS or ghp_x.shape != (GHP7_SCENES, 1999, INPUT_DIM) or ghp_y.shape != (GHP7_SCENES, 1999, 3):
        raise ValueError("GHP7 train scenes, order, or array shapes differ from the frozen taskbook")
    if (not np.isfinite(ghp_x).all() or not np.isfinite(ghp_y).all()
            or sha256_array(ghp_x) != lock["ghp7_train_x_sha256"]
            or sha256_array(ghp_y) != lock["ghp7_train_y_sha256"]):
        raise ValueError("GHP7 training arrays are non-finite or differ from the source lock")
    x = np.concatenate((base_x, ghp_x), axis=0)
    y = np.concatenate((base_y, ghp_y), axis=0)
    if x.shape != (76, 1999, INPUT_DIM) or y.shape != (76, 1999, 3):
        raise ValueError("combined mixed-training data shape mismatch")
    return x, y, base_ids + ghp_ids


def load_model_helpers():
    sys.path.insert(0, str(SCREEN_ROOT))
    from screen_attitude_architectures_v1 import MLP15, make_windows
    return MLP15, make_windows


def train(device_name: str) -> None:
    lock = load_release()
    if OUTPUT_DIR.exists():
        raise FileExistsError(f"single authorized training output exists: {OUTPUT_DIR}")
    x, y, scene_ids = load_training_arrays(lock)
    OUTPUT_DIR.mkdir(parents=True)
    mean, std, target_rms = fit_normalizer(x, y)
    x_norm = ((x - mean) / std).astype(np.float32)
    y_norm = (y / target_rms).astype(np.float32)
    if device_name == "cuda:0" and not torch.cuda.is_available():
        raise RuntimeError("cuda:0 requested but unavailable")
    device = torch.device("cuda:0" if device_name == "cuda:0" or
                          (device_name == "auto" and torch.cuda.is_available()) else "cpu")

    random.seed(SEED); np.random.seed(SEED); torch.manual_seed(SEED)
    torch.use_deterministic_algorithms(True)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(SEED)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False

    MLP15, make_windows = load_model_helpers()
    padded = F.pad(torch.as_tensor(x_norm, device=device).permute(0, 2, 1), (WINDOW - 1, 0))
    targets = torch.as_tensor(y_norm, device=device)
    rng = np.random.default_rng(SEED)
    model = MLP15().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
    config = {
        "schema": "DL1018_MLP15_C5_GHP7_BALANCE_CONFIG_V1", "status": "RUNNING",
        "architecture": "MLP15", "input_dim": INPUT_DIM, "window_events": WINDOW,
        "hidden": [64, 32], "activation": "SiLU", "output_dim": 3,
        "seed": SEED, "optimizer": "Adam", "learning_rate": 1e-3,
        "weight_decay": 1e-5, "batch_size": BATCH, "loss": "SmoothL1(beta=1.0)",
        "optimizer_steps": STEPS, "checkpoint_policy": "final_step_only_at_60000",
        "sampling": "256 samples/step from 72-scene C5 base and 256 from four GHP7 G1/G2 C5 scenes",
        "unique_scenes": 76, "unique_events": 76 * 1999,
        "scene_ids_in_training_order": scene_ids,
        "feature_order": FEATURE_ORDER,
        "target_contract": "C5 logged rbf_output_raw, post-dmax/pre-beta, rad/s^2",
        "normalizer_fit": "all 72 base C5 scenes plus four GHP7 G1/G2 training scenes",
        "source_lock_sha256": sha256_file(LOCK_PATH),
        "ghp7_train_manifest_sha256": sha256_file(DATA_MANIFEST),
        "device": str(device), "plant_called": False, "TEST48_read": False,
        "ghp7_holdout_opened": False, "created_utc": datetime.now(timezone.utc).isoformat(),
    }
    progress_path = OUTPUT_DIR / "training_progress.json"
    history_path = OUTPUT_DIR / "training_history.jsonl"
    write_json(OUTPUT_DIR / "training_config.json", config)
    write_json(progress_path, {"status": "RUNNING", "completed_steps": 0,
                               "target_steps": STEPS, "plant_called": False,
                               "TEST48_read": False, "ghp7_holdout_opened": False})
    history_path.write_text("", encoding="utf-8")
    started = time.perf_counter()
    loss_sum = 0.0
    try:
        for step in range(1, STEPS + 1):
            base_scene = rng.integers(0, BASE_SCENES, HALF_BATCH, dtype=np.int64)
            ghp_scene = BASE_SCENES + rng.integers(0, GHP7_SCENES, HALF_BATCH, dtype=np.int64)
            scenes_np = np.concatenate((base_scene, ghp_scene))
            times_np = rng.integers(0, 1999, BATCH, dtype=np.int64)
            order = rng.permutation(BATCH)
            scenes = torch.as_tensor(scenes_np[order], device=device)
            times = torch.as_tensor(times_np[order], device=device)
            windows = make_windows(padded, scenes, times)
            target = targets[scenes, times]
            model.train(); optimizer.zero_grad(set_to_none=True)
            loss = F.smooth_l1_loss(model(windows), target, beta=1.0)
            if not torch.isfinite(loss):
                raise FloatingPointError(f"non-finite loss at step {step}")
            loss.backward(); optimizer.step(); loss_sum += float(loss.item())
            if step % 1000 == 0:
                row = {"step": step, "train_loss_mean_last_1000_steps": loss_sum / 1000,
                       "latest_batch_train_loss": float(loss.item())}
                with history_path.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(row) + "\n")
                loss_sum = 0.0
                write_json(progress_path, {"status": "RUNNING", "completed_steps": step,
                                           "target_steps": STEPS, "latest_logged_loss": row["latest_batch_train_loss"],
                                           "updated_utc": datetime.now(timezone.utc).isoformat(),
                                           "plant_called": False, "TEST48_read": False,
                                           "ghp7_holdout_opened": False})
                print(json.dumps(row), flush=True)
    except Exception as error:
        write_json(progress_path, {"status": "FAILED", "target_steps": STEPS,
                                   "error": f"{type(error).__name__}: {error}",
                                   "plant_called": False, "TEST48_read": False,
                                   "ghp7_holdout_opened": False})
        raise

    model.eval(); state = model.state_dict()
    checkpoint = OUTPUT_DIR / "final_step_60000.pt"
    torch.save({"status": "PASS", "step": STEPS, "state_dict": state,
                "input_mean": torch.as_tensor(mean.copy()), "input_std": torch.as_tensor(std.copy()),
                "target_rms": torch.as_tensor(target_rms.copy()), "config": config}, checkpoint)
    normalizer = OUTPUT_DIR / "normalizer.npz"
    np.savez_compressed(normalizer, input_mean=mean, input_std=std, target_rms=target_rms)
    weights_path = OUTPUT_DIR / "mlp15_attitude_weights_v1.mat"
    savemat(weights_path, {
        "input_mean": mean.reshape(1, -1), "input_std": std.reshape(1, -1),
        "target_rms": target_rms.reshape(1, -1),
        "fc1_weight": state["net.0.weight"].cpu().numpy().astype(np.float64),
        "fc1_bias": state["net.0.bias"].cpu().numpy().astype(np.float64),
        "fc2_weight": state["net.2.weight"].cpu().numpy().astype(np.float64),
        "fc2_bias": state["net.2.bias"].cpu().numpy().astype(np.float64),
        "head_weight": state["net.4.weight"].cpu().numpy().astype(np.float64),
        "head_bias": state["net.4.bias"].cpu().numpy().astype(np.float64),
    }, do_compression=True, oned_as="row")
    fixture_window = make_windows(padded, torch.tensor([BASE_SCENES], device=device),
                                  torch.tensor([100], device=device))
    with torch.inference_mode():
        raw_output = model(fixture_window).cpu().numpy()[0] * target_rms
    parity = OUTPUT_DIR / "parity_vector_v1.mat"
    savemat(parity, {
        "input_normalized_window": fixture_window.cpu().numpy()[0].astype(np.float64),
        "expected_model_output_raw_rad_s2": raw_output.astype(np.float64),
        "expected_runtime_output_clipped_rad_s2": np.clip(raw_output, -D_MAX, D_MAX).astype(np.float64),
        "scene_index_zero_based": np.asarray([[BASE_SCENES]], dtype=np.int32),
        "event_index_zero_based": np.asarray([[100]], dtype=np.int32),
    }, do_compression=True, oned_as="row")
    elapsed = time.perf_counter() - started
    config.update({"status": "PASS", "elapsed_seconds": elapsed,
                   "checkpoint_sha256": sha256_file(checkpoint),
                   "normalizer_sha256": sha256_file(normalizer),
                   "weights_sha256": sha256_file(weights_path)})
    write_json(OUTPUT_DIR / "training_config.json", config)
    write_json(progress_path, {"status": "PASS", "completed_steps": STEPS,
                               "target_steps": STEPS, "updated_utc": datetime.now(timezone.utc).isoformat(),
                               "plant_called": False, "TEST48_read": False,
                               "ghp7_holdout_opened": False})
    output_files = [checkpoint, normalizer, weights_path, parity, history_path,
                    progress_path, OUTPUT_DIR / "training_config.json"]
    receipt = {
        "schema": "DL1018_MLP15_C5_GHP7_BALANCE_RECEIPT_V1", "status": "PASS",
        "training_job_count": 1, "optimizer_steps": STEPS,
        "base_c5_scenes": BASE_SCENES, "ghp7_train_scenes": GHP7_SCENES,
        "unique_training_scenes": BASE_SCENES + GHP7_SCENES,
        "unique_training_events": (BASE_SCENES + GHP7_SCENES) * 1999,
        "training_event_presentations": STEPS * BATCH,
        "sampling_per_batch": {"base_c5": HALF_BATCH, "ghp7_g1_g2": HALF_BATCH},
        "selection_used": False, "plant_called": False, "TEST48_read": False,
        "ghp7_holdout_opened": False, "dataset_identity": config["scene_ids_in_training_order"],
        "source_lock_sha256": config["source_lock_sha256"],
        "output_sha256": {path.name: sha256_file(path) for path in output_files},
        "elapsed_seconds": elapsed,
    }
    write_json(OUTPUT_DIR / "run_receipt.json", receipt)
    print(json.dumps({"status": "PASS", "steps": STEPS, "unique_scenes": 76,
                      "unique_events": 76 * 1999, "seconds": elapsed,
                      "plant_called": False, "TEST48_read": False,
                      "ghp7_holdout_opened": False}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda:0"), default="auto")
    train(parser.parse_args().device)


if __name__ == "__main__":
    main()
