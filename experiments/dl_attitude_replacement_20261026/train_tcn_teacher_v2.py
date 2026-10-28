#!/usr/bin/env python3
"""Train one frozen 13->3 causal TCN distilled from the B attitude-RBF action."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import platform
import random
from datetime import datetime, timezone
from pathlib import Path

# PyTorch deterministic CUDA kernels require this before torch initializes CUDA.
os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"

import numpy as np
import torch
from scipy.io import savemat
from torch import nn
from torch.nn import functional as F


ROOT = Path(__file__).resolve().parents[2]
TASK_ROOT = Path(__file__).resolve().parent
DATASET_DIR = TASK_ROOT / "dataset_v4_teacher_distill"
DATASET_FILE = DATASET_DIR / "attitude_rbf_teacher_train_val_v2.npz"
DATASET_MANIFEST = DATASET_DIR / "DATASET_MANIFEST_v2.json"
RELEASE_LOCK = TASK_ROOT / "TRAINING_RELEASE_v3.json"
OUTPUT = TASK_ROOT / "training_v2_teacher_distill"
SEED = 2026102001
STEPS = 60000
BATCH = 512
LR = 1e-3
WEIGHT_DECAY = 1e-5
VAL_EVERY = 1000
WINDOW = 15
INPUT_DIM = 13
HIDDEN = 32


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class CausalTCN(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.input = nn.Conv1d(INPUT_DIM, HIDDEN, kernel_size=1)
        self.layers = nn.ModuleList(
            [nn.Conv1d(HIDDEN, HIDDEN, kernel_size=3, dilation=d) for d in (1, 2, 4)]
        )
        self.head = nn.Linear(HIDDEN, 3)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        z = F.relu(self.input(x))
        for conv, dilation in zip(self.layers, (1, 2, 4), strict=True):
            z = F.relu(conv(F.pad(z, (2 * dilation, 0))))
        return self.head(z[:, :, -1])


def make_windows(x_pad: torch.Tensor, scenes: torch.Tensor, steps: torch.Tensor) -> torch.Tensor:
    offsets = torch.arange(WINDOW, device=x_pad.device, dtype=torch.long)
    indices = (steps[:, None] + offsets[None, :])[:, None, :].expand(-1, INPUT_DIM, -1)
    return torch.gather(x_pad[scenes], 2, indices)


def validate(model: nn.Module, x_pad: torch.Tensor, y: torch.Tensor, batch: int = 512) -> float:
    model.eval()
    scene_sse = np.zeros(y.shape[0], dtype=np.float64)
    with torch.inference_mode():
        for scene in range(y.shape[0]):
            count = y.shape[1]
            for start in range(0, count, batch):
                stop = min(start + batch, count)
                scene_ids = torch.full((stop - start,), scene, device=y.device, dtype=torch.long)
                step_ids = torch.arange(start, stop, device=y.device, dtype=torch.long)
                xb = make_windows(x_pad, scene_ids, step_ids)
                pred = model(xb)
                err = pred - y[scene, start:stop]
                scene_sse[scene] += float(torch.sum(err * err).item())
    return float(np.mean(np.sqrt(scene_sse / (y.shape[1] * 3))))


def state_cpu(model: nn.Module) -> dict[str, torch.Tensor]:
    return {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}


def write_json(path: Path, value: dict[str, Any]) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(path)


def export_mat(model: CausalTCN, mean: np.ndarray, std: np.ndarray,
               target_rms: np.ndarray, path: Path) -> None:
    state = model.state_dict()
    payload: dict[str, np.ndarray] = {
        "input_mean": mean.astype(np.float64),
        "input_std": std.astype(np.float64),
        "target_rms": target_rms.astype(np.float64),
        "input_weight": state["input.weight"][:, :, 0].cpu().numpy().astype(np.float64),
        "input_bias": state["input.bias"].cpu().numpy().astype(np.float64),
        "head_weight": state["head.weight"].cpu().numpy().astype(np.float64),
        "head_bias": state["head.bias"].cpu().numpy().astype(np.float64),
    }
    for i, layer in enumerate(model.layers, start=1):
        payload[f"conv{i}_weight"] = state[f"layers.{i-1}.weight"].cpu().numpy().astype(np.float64)
        payload[f"conv{i}_bias"] = state[f"layers.{i-1}.bias"].cpu().numpy().astype(np.float64)
    savemat(path, payload, do_compression=True, oned_as="row")


def main() -> None:
    if OUTPUT.exists():
        raise FileExistsError(f"refusing to overwrite training output: {OUTPUT}")
    if not RELEASE_LOCK.is_file():
        raise FileNotFoundError("TRAINING_RELEASE_v3.json must be frozen before formal training")
    if not DATASET_FILE.is_file() or not DATASET_MANIFEST.is_file():
        raise FileNotFoundError("prepare_tcn_teacher_dataset_v2.py must finish before training")
    release = json.loads(RELEASE_LOCK.read_text(encoding="utf-8"))
    if release.get("status") != "FROZEN" or release.get("schema") != "DL1018_CAUSAL_TCN_TRAINING_RELEASE_V3":
        raise ValueError("training release lock is not frozen")
    for rel_path, expected_sha in release["source_files"].items():
        locked_path = ROOT / Path(rel_path)
        if not locked_path.is_file() or sha256(locked_path) != expected_sha.lower():
            raise ValueError(f"frozen training source changed: {rel_path}")
    data_meta = json.loads(DATASET_MANIFEST.read_text(encoding="utf-8"))
    expected_features = ["attitude_error_euler_rad_x3", "body_rate_rad_s_x3",
                         "nominal_bs_body_torque_Nm_x3", "morph_command_x4"]
    if (data_meta.get("schema") != "DL1018_CAUSAL_TCN_RBF_TEACHER_DATASET_V2"
            or data_meta.get("status") != "PASS" or data_meta.get("test_data_read") is not False
            or data_meta.get("nominal_inertia_read") is not False
            or data_meta.get("plant_truth_read") is not False
            or data_meta.get("split_counts") != {"TRAIN": 768, "VAL": 48}
            or data_meta.get("feature_order") != expected_features
            or data_meta.get("target") != "logged rbf_output_raw at event k, pre-beta, rad/s^2"):
        raise ValueError("dataset manifest is not PASS or indicates TEST access")
    if sha256(DATASET_FILE) != data_meta.get("npz_sha256"):
        raise ValueError("dataset NPZ SHA-256 differs from the frozen dataset manifest")

    random.seed(SEED)
    np_rng = np.random.default_rng(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(SEED)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
    torch.use_deterministic_algorithms(True)
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

    with np.load(DATASET_FILE, allow_pickle=False) as ds:
        train_x = np.asarray(ds["train_x"], dtype=np.float32)
        train_y = np.asarray(ds["train_y"], dtype=np.float32)
        val_x = np.asarray(ds["val_x"], dtype=np.float32)
        val_y = np.asarray(ds["val_y"], dtype=np.float32)
    if train_x.shape != (768, 1999, INPUT_DIM) or train_y.shape != (768, 1999, 3):
        raise ValueError(f"unexpected TRAIN shapes: {train_x.shape}, {train_y.shape}")
    if val_x.shape != (48, 1999, INPUT_DIM) or val_y.shape != (48, 1999, 3):
        raise ValueError(f"unexpected VAL shapes: {val_x.shape}, {val_y.shape}")
    if not all(np.isfinite(array).all() for array in (train_x, train_y, val_x, val_y)):
        raise ValueError("dataset contains non-finite features or teacher actions")

    mean = train_x.mean(axis=(0, 1), dtype=np.float64)
    std_raw = train_x.std(axis=(0, 1), dtype=np.float64)
    std = np.maximum(std_raw, 1e-6)
    target_rms = np.sqrt(np.mean(train_y.astype(np.float64) ** 2, axis=(0, 1)))
    if not np.isfinite(np.r_[mean, std, target_rms]).all() or np.any(target_rms <= 1e-8):
        raise ValueError("invalid TRAIN-only input or target normalizer")

    train_xn = ((train_x - mean) / std).astype(np.float32)
    val_xn = ((val_x - mean) / std).astype(np.float32)
    train_yn = (train_y / target_rms).astype(np.float32)
    val_yn = (val_y / target_rms).astype(np.float32)
    train_t = torch.as_tensor(train_yn, device=device)
    val_t = torch.as_tensor(val_yn, device=device)
    train_pad = F.pad(torch.as_tensor(train_xn, device=device).permute(0, 2, 1), (WINDOW - 1, 0))
    val_pad = F.pad(torch.as_tensor(val_xn, device=device).permute(0, 2, 1), (WINDOW - 1, 0))

    model = CausalTCN().to(device)
    initial = state_cpu(model)
    optimizer = torch.optim.Adam(model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)
    OUTPUT.mkdir(parents=True)
    progress_path = OUTPUT / "training_progress.json"
    progress = {"schema": "DL1018_CAUSAL_TCN_TEACHER_TRAINING_PROGRESS_V2", "status": "RUNNING",
                "completed_steps": 0, "target_steps": STEPS, "seed": SEED,
                "dataset_manifest_sha256": sha256(DATASET_MANIFEST),
                "dataset_npz_sha256": sha256(DATASET_FILE)}
    write_json(progress_path, progress)
    torch.save({"step": 0, "state_dict": initial}, OUTPUT / "initial.pt")
    rows: list[dict[str, Any]] = []
    best_metric = validate(model, val_pad, val_t)
    best_step = 0
    torch.save({"step": 0, "state_dict": initial,
                "val_scene_macro_teacher_action_rmse": best_metric}, OUTPUT / "best.pt")

    model.train()
    for step in range(1, STEPS + 1):
        s_cpu = np_rng.integers(0, train_x.shape[0], size=BATCH, dtype=np.int64)
        t_cpu = np_rng.integers(0, train_x.shape[1], size=BATCH, dtype=np.int64)
        scenes = torch.as_tensor(s_cpu, device=device)
        times = torch.as_tensor(t_cpu, device=device)
        xb = make_windows(train_pad, scenes, times)
        target = train_t[scenes, times]
        optimizer.zero_grad(set_to_none=True)
        pred = model(xb)
        loss = F.smooth_l1_loss(pred, target, beta=1.0)
        if not torch.isfinite(loss):
            raise FloatingPointError(f"non-finite training loss at step {step}")
        loss.backward()
        optimizer.step()

        if step % VAL_EVERY == 0 or step == STEPS:
            metric = validate(model, val_pad, val_t)
            rows.append({"step": step, "train_loss": float(loss.item()),
                         "val_scene_macro_teacher_action_rmse": metric})
            if metric < best_metric:
                best_metric = metric
                best_step = step
                torch.save({"step": step, "state_dict": state_cpu(model),
                            "val_scene_macro_teacher_action_rmse": metric}, OUTPUT / "best.pt")
            progress.update({"completed_steps": step, "best_step": best_step,
                             "best_val_scene_macro_teacher_action_rmse": best_metric,
                             "latest_train_loss": float(loss.item()), "updated_utc": datetime.now(timezone.utc).isoformat()})
            write_json(progress_path, progress)
            if len(rows) == 1 or step % 5000 == 0 or step == STEPS:
                print(f"step={step}/{STEPS} train_loss={loss.item():.7g} teacher_val={metric:.7g} best={best_metric:.7g}@{best_step}", flush=True)
            model.train()

    torch.save({"step": STEPS, "state_dict": state_cpu(model)}, OUTPUT / "final.pt")
    with (OUTPUT / "training_history.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("step", "train_loss",
                                                    "val_scene_macro_teacher_action_rmse"))
        writer.writeheader()
        writer.writerows(rows)
    best = torch.load(OUTPUT / "best.pt", map_location=device, weights_only=True)
    model.load_state_dict(best["state_dict"])
    model.eval()
    export_mat(model, mean, std, target_rms, OUTPUT / "tcn_attitude_weights_v2.mat")
    write_json(OUTPUT / "normalizer_v2.json", {
        "schema": "DL1018_CAUSAL_TCN_NORMALIZER_V2",
        "fit_split": "TRAIN", "input_mean": mean.tolist(),
        "input_std_raw": std_raw.tolist(), "input_std_used": std.tolist(),
        "target_rms": target_rms.tolist(), "dataset_manifest_sha256": sha256(DATASET_MANIFEST),
        "test_data_read": False,
    })

    with torch.inference_mode():
        parity_x = make_windows(val_pad, torch.tensor([0], device=device), torch.tensor([100], device=device))
        parity_y = model(parity_x).cpu().numpy().reshape(3) * target_rms
        parity_x_cpu = parity_x.cpu().numpy().reshape(INPUT_DIM, WINDOW)
    savemat(OUTPUT / "parity_vector_v2.mat", {"input_normalized": parity_x_cpu,
            "expected_teacher_rbf_output_rad_s2": parity_y}, do_compression=True)
    config = {
        "schema": "DL1018_CAUSAL_TCN_TEACHER_TRAINING_CONFIG_V2", "status": "PASS", "seed": SEED,
        "optimizer_steps": STEPS, "batch_size": BATCH, "validation_interval": VAL_EVERY,
        "optimizer": {"name": "Adam", "lr": LR, "weight_decay": WEIGHT_DECAY},
        "loss": "SmoothL1(beta=1.0), mean over normalized batch and three axes",
        "selection": "minimum B VAL48 scene-macro normalized teacher-action RMSE; earliest strict minimum",
        "architecture": {"input_dim": INPUT_DIM, "window": WINDOW, "hidden": HIDDEN,
                         "causal_conv_kernel": 3, "dilations": [1, 2, 4], "output_dim": 3},
        "target_contract": "logged rbf_output_raw at attitude event k, pre-beta, rad/s^2",
        "feature_order": data_meta["feature_order"], "dataset_manifest_sha256": sha256(DATASET_MANIFEST),
        "dataset_npz_sha256": sha256(DATASET_FILE), "best_step": best_step,
        "best_val_scene_macro_teacher_action_rmse": best_metric, "device": str(device),
        "python": platform.python_version(), "torch": torch.__version__,
        "gpu_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU",
        "cublas_workspace_config": os.environ["CUBLAS_WORKSPACE_CONFIG"],
        "test_data_read": False, "nominal_inertia_read_by_dataset_exporter": False,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "training_script_sha256": sha256(Path(__file__).resolve()),
        "training_release_sha256": sha256(RELEASE_LOCK),
    }
    write_json(OUTPUT / "training_config.json", config)
    progress.update({"status": "PASS", "completed_steps": STEPS,
                     "best_step": best_step,
                     "best_val_scene_macro_teacher_action_rmse": best_metric,
                     "updated_utc": datetime.now(timezone.utc).isoformat()})
    write_json(progress_path, progress)
    print(json.dumps({"status": "PASS", "best_step": best_step,
                      "best_val_scene_macro_teacher_action_rmse": best_metric,
                      "device": str(device), "output": str(OUTPUT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
