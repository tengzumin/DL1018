#!/usr/bin/env python3
"""Equal-budget offline screen of four attitude-RBF teacher regressors."""
from __future__ import annotations

import hashlib
import json
import math
import os
import random
import time
from pathlib import Path
from typing import Any

os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F


TASK_ROOT = Path(__file__).resolve().parents[1]
SCREEN_ROOT = Path(__file__).resolve().parent
DATASET = TASK_ROOT / "dataset_v4_teacher_distill" / "attitude_rbf_teacher_train_val_v2.npz"
MANIFEST = TASK_ROOT / "dataset_v4_teacher_distill" / "DATASET_MANIFEST_v2.json"
RELEASE = SCREEN_ROOT / "SCREEN_RELEASE_v1.json"
AMENDMENT = TASK_ROOT / "DL_ATTITUDE_REPLACEMENT_TASKBOOK_v1_AMENDMENT08_ARCHITECTURE_SCREEN.md"
OUTPUT = SCREEN_ROOT / "runs_v1"
SEED = 2026102001
STEPS = 2000
BATCH = 512
WINDOW = 15
INPUT_DIM = 13
HIDDEN = 32
VAL_BATCH = 4096
FAMILIES = ("MLP15", "GRU15", "DSSM15", "TCN15")


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


class MLP15(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(WINDOW * INPUT_DIM, 64), nn.SiLU(),
            nn.Linear(64, 32), nn.SiLU(), nn.Linear(32, 3),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x.flatten(start_dim=1))


class GRU15(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.gru = nn.GRU(INPUT_DIM, HIDDEN, batch_first=True)
        self.head = nn.Linear(HIDDEN, 3)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        _, state = self.gru(x)
        return self.head(state[-1])


class DSSM15(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.encoder = nn.Linear(INPUT_DIM, HIDDEN)
        self.log_tau = nn.Parameter(torch.log(torch.logspace(
            math.log10(0.02), math.log10(1.28), HIDDEN
        )))
        self.project = nn.Linear(HIDDEN, 3)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        drive = torch.tanh(self.encoder(x))
        tau = torch.exp(self.log_tau).clamp(0.005, 5.0)
        alpha = torch.exp(-0.01 / tau)
        state = torch.zeros_like(drive[:, 0, :])
        for i in range(WINDOW):
            state = alpha * state + (1.0 - alpha) * drive[:, i, :]
        return self.project(torch.tanh(state))


class TCN15(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.input = nn.Conv1d(INPUT_DIM, HIDDEN, kernel_size=1)
        self.layers = nn.ModuleList(
            nn.Conv1d(HIDDEN, HIDDEN, kernel_size=3, dilation=d) for d in (1, 2, 4)
        )
        self.head = nn.Linear(HIDDEN, 3)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        z = F.relu(self.input(x.transpose(1, 2)))
        for conv, dilation in zip(self.layers, (1, 2, 4), strict=True):
            z = F.relu(conv(F.pad(z, (2 * dilation, 0))))
        return self.head(z[:, :, -1])


def make_windows(
    padded: torch.Tensor, scenes: torch.Tensor, steps: torch.Tensor,
) -> torch.Tensor:
    offsets = torch.arange(WINDOW, device=padded.device, dtype=torch.long)
    indices = steps[:, None] + offsets[None, :]
    gathered = torch.gather(
        padded[scenes], 2,
        indices[:, None, :].expand(-1, INPUT_DIM, -1),
    )
    return gathered.transpose(1, 2).contiguous()


def evaluate(
    model: nn.Module,
    padded: torch.Tensor,
    targets: np.ndarray,
    target_rms: np.ndarray,
    device: torch.device,
) -> dict[str, Any]:
    model.eval()
    scene_count, event_count, _ = targets.shape
    prediction = np.empty(targets.shape, dtype=np.float32)
    flat_count = scene_count * event_count
    with torch.inference_mode():
        for start in range(0, flat_count, VAL_BATCH):
            stop = min(start + VAL_BATCH, flat_count)
            flat = torch.arange(start, stop, device=device)
            scenes = torch.div(flat, event_count, rounding_mode="floor")
            steps = torch.remainder(flat, event_count)
            windows = make_windows(padded, scenes, steps)
            prediction.reshape(-1, 3)[start:stop] = model(windows).cpu().numpy()
    err_norm = prediction.astype(np.float64) - (targets / target_rms).astype(np.float64)
    per_scene = np.sqrt(np.mean(err_norm * err_norm, axis=(1, 2)))
    err_phys = err_norm * target_rms
    axis_scene_macro = np.mean(np.sqrt(np.mean(err_phys * err_phys, axis=1)), axis=0)
    axis_pooled = np.sqrt(np.mean(err_phys * err_phys, axis=(0, 1)))
    return {
        "normalized_scene_macro_teacher_action_rmse": float(np.mean(per_scene)),
        "physical_axis_scene_macro_rmse_rad_s2": axis_scene_macro.tolist(),
        "physical_axis_pooled_rmse_rad_s2": axis_pooled.tolist(),
        "val_scene_count": int(scene_count),
        "events_per_scene": int(event_count),
    }


def build_model(name: str) -> nn.Module:
    return {
        "MLP15": MLP15,
        "GRU15": GRU15,
        "DSSM15": DSSM15,
        "TCN15": TCN15,
    }[name]()


def main() -> None:
    if OUTPUT.exists():
        raise FileExistsError(f"refusing to overwrite screen output: {OUTPUT}")
    release = json.loads(RELEASE.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if release.get("status") != "FROZEN" or release.get("schema") != "DL1018_ATTITUDE_ARCHITECTURE_SCREEN_V1":
        raise ValueError("screen release is not frozen")
    if sha256(Path(__file__).resolve()) != release.get("screen_script_sha256"):
        raise ValueError("screen script differs from its frozen release hash")
    if sha256(AMENDMENT) != release.get("taskbook_amendment_sha256"):
        raise ValueError("screen taskbook amendment differs from its frozen release hash")
    if sha256(DATASET) != release.get("dataset_sha256") or sha256(MANIFEST) != release.get("manifest_sha256"):
        raise ValueError("frozen TRAIN/VAL data identity mismatch")
    if (
        manifest.get("status") != "PASS"
        or manifest.get("split_counts") != {"TRAIN": 768, "VAL": 48}
        or manifest.get("feature_order") != [
            "attitude_error_euler_rad_x3", "body_rate_rad_s_x3",
            "nominal_bs_body_torque_Nm_x3", "morph_command_x4",
        ]
        or manifest.get("target") != "logged rbf_output_raw at event k, pre-beta, rad/s^2"
        or manifest.get("plant_truth_read") is not False
        or manifest.get("nominal_inertia_read") is not False
        or manifest.get("test_data_read") is not False
        or release.get("families") != list(FAMILIES)
        or release.get("steps_per_model") != STEPS
    ):
        raise ValueError("screen contract/data manifest is not the frozen TRAIN/VAL-only contract")

    random.seed(SEED)
    np.random.seed(SEED)
    torch.use_deterministic_algorithms(True)
    if torch.cuda.is_available():
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        torch.cuda.manual_seed_all(SEED)
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

    with np.load(DATASET, allow_pickle=False) as data:
        train_x = np.asarray(data["train_x"], dtype=np.float32)
        train_y = np.asarray(data["train_y"], dtype=np.float32)
        val_x = np.asarray(data["val_x"], dtype=np.float32)
        val_y = np.asarray(data["val_y"], dtype=np.float32)
    if train_x.shape != (768, 1999, INPUT_DIM) or train_y.shape != (768, 1999, 3):
        raise ValueError(f"unexpected TRAIN shapes: {train_x.shape}, {train_y.shape}")
    if val_x.shape != (48, 1999, INPUT_DIM) or val_y.shape != (48, 1999, 3):
        raise ValueError(f"unexpected VAL shapes: {val_x.shape}, {val_y.shape}")
    if not all(np.isfinite(a).all() for a in (train_x, train_y, val_x, val_y)):
        raise ValueError("non-finite screen data")

    mean = train_x.mean(axis=(0, 1), dtype=np.float64)
    std = np.maximum(train_x.std(axis=(0, 1), dtype=np.float64), 1e-6)
    target_rms = np.sqrt(np.mean(train_y.astype(np.float64) ** 2, axis=(0, 1)))
    if not np.isfinite(np.r_[mean, std, target_rms]).all() or np.any(target_rms <= 1e-8):
        raise ValueError("invalid TRAIN-only normalizer or target RMS")
    train_norm = ((train_x - mean) / std).astype(np.float32)
    val_norm = ((val_x - mean) / std).astype(np.float32)
    train_target = (train_y / target_rms).astype(np.float32)
    val_target = val_y.astype(np.float32)
    train_pad = F.pad(
        torch.as_tensor(train_norm, device=device).permute(0, 2, 1),
        (WINDOW - 1, 0),
    )
    val_pad = F.pad(
        torch.as_tensor(val_norm, device=device).permute(0, 2, 1),
        (WINDOW - 1, 0),
    )
    target_tensor = torch.as_tensor(train_target, device=device)
    common_rng = np.random.default_rng(SEED)
    batch_indices = [
        (
            common_rng.integers(0, train_x.shape[0], BATCH, dtype=np.int64),
            common_rng.integers(0, train_x.shape[1], BATCH, dtype=np.int64),
        )
        for _ in range(STEPS)
    ]

    OUTPUT.mkdir(parents=True)
    results: list[dict[str, Any]] = []
    write_json(OUTPUT / "screen_status.json", {
        "status": "RUNNING", "families": list(FAMILIES), "completed_families": [],
        "steps_per_model": STEPS, "seed": SEED, "device": str(device),
        "plant_called": False, "test_data_read": False,
    })
    for family in FAMILIES:
        torch.manual_seed(SEED)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(SEED)
        model = build_model(family).to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
        param_count = sum(p.numel() for p in model.parameters())
        candidate_dir = OUTPUT / family
        candidate_dir.mkdir()
        train_start = time.perf_counter()
        model.train()
        for step, (scene_np, time_np) in enumerate(batch_indices, start=1):
            scenes = torch.as_tensor(scene_np, device=device)
            times = torch.as_tensor(time_np, device=device)
            x = make_windows(train_pad, scenes, times)
            y = target_tensor[scenes, times]
            optimizer.zero_grad(set_to_none=True)
            prediction = model(x)
            loss = F.smooth_l1_loss(prediction, y, beta=1.0)
            if not torch.isfinite(loss):
                raise FloatingPointError(f"{family}: non-finite loss at step {step}")
            loss.backward()
            optimizer.step()
            if step % 500 == 0:
                checkpoint = candidate_dir / f"step_{step:05d}.pt"
                torch.save({
                    "architecture": family, "step": step,
                    "state_dict": {key: value.detach().cpu().clone()
                                   for key, value in model.state_dict().items()},
                    "input_mean": mean, "input_std": std, "target_rms": target_rms,
                }, checkpoint)
                write_json(OUTPUT / "screen_status.json", {
                    "status": "RUNNING", "families": list(FAMILIES),
                    "completed_families": [r["architecture"] for r in results],
                    "current_family": family, "current_step": step,
                    "last_checkpoint_sha256": sha256(checkpoint),
                    "steps_per_model": STEPS, "seed": SEED, "device": str(device),
                    "plant_called": False, "test_data_read": False,
                })
        train_seconds = time.perf_counter() - train_start

        val_start = time.perf_counter()
        metrics = evaluate(model, val_pad, val_target, target_rms, device)
        val_seconds = time.perf_counter() - val_start
        checkpoint = candidate_dir / f"step_{STEPS:05d}.pt"
        if not checkpoint.is_file():
            raise FileNotFoundError(f"final screen checkpoint missing for {family}")
        item = {
            "architecture": family, "steps": STEPS, "parameter_count": int(param_count),
            "training_seconds": train_seconds, "full_val_seconds": val_seconds,
            **metrics, "checkpoint_sha256": sha256(checkpoint),
            "plant_called": False, "test_data_read": False,
        }
        results.append(item)
        write_json(candidate_dir / "metrics.json", item)
        write_json(OUTPUT / "screen_status.json", {
            "status": "RUNNING", "families": list(FAMILIES),
            "completed_families": [r["architecture"] for r in results],
            "steps_per_model": STEPS, "seed": SEED, "device": str(device),
            "plant_called": False, "test_data_read": False,
        })
        print(json.dumps(item, ensure_ascii=False), flush=True)
        del model, optimizer
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    results.sort(key=lambda row: (
        row["normalized_scene_macro_teacher_action_rmse"],
        row["training_seconds"],
        row["architecture"],
    ))
    summary = {
        "schema": "DL1018_ATTITUDE_ARCHITECTURE_SCREEN_RESULT_V1",
        "status": "PASS_OFFLINE_SCREEN_ONLY",
        "architecture_ranking": [r["architecture"] for r in results],
        "results": results, "dataset_sha256": sha256(DATASET),
        "manifest_sha256": sha256(MANIFEST),
        "screen_script_sha256": sha256(Path(__file__).resolve()),
        "training_steps_per_model": STEPS, "seed": SEED, "device": str(device),
        "test_data_read": False, "plant_called": False,
        "interpretation": "Shortlist only; teacher-action fit is not closed-loop evidence.",
    }
    write_json(OUTPUT / "screen_results.json", summary)
    write_json(OUTPUT / "screen_status.json", {
        "status": "PASS_OFFLINE_SCREEN_ONLY", "families": list(FAMILIES),
        "completed_families": [r["architecture"] for r in results],
        "steps_per_model": STEPS, "seed": SEED, "device": str(device),
        "plant_called": False, "test_data_read": False,
    })
    print(json.dumps({
        "status": summary["status"], "ranking": summary["architecture_ranking"],
        "result_path": str(OUTPUT / "screen_results.json"),
        "plant_called": False, "test_data_read": False,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
