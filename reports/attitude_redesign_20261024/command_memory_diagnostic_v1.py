#!/usr/bin/env python3
"""Reproduce the two-scene past-only command-memory diagnostic; no fitting."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import h5py
import numpy as np

N_SAMPLES = 20001
INITIAL_RHO_M = 0.15
PRESCRIBED_SPEED_MPS = 0.05
MEMORY_ZERO_TOL_S = 1e-12
SCENES = (
    ("train", "DL1018_TRAIN_T1_C01_W00", "data/raw/train/DL1018_TRAIN_T1_C01_W00/B/attempt_01/raw_run.mat",
     "c8e763e7bafea8e42a5018e05b57c8ce1987c5f97a29d5877839e759a4b03ea5"),
    ("val", "DL1018_VAL_T1_C01_W08", "data/raw/val/DL1018_VAL_T1_C01_W08/B/attempt_01/raw_run.mat",
     "9efc4dfcc21bf8a08a091168bb48b3b39dbb6cd4f371f890e78fb697c78c3685"),
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def past_command_integral(command: np.ndarray, time_s: np.ndarray) -> np.ndarray:
    """z[k] = sum(i < k) (t[i+1]-t[i]) * command[i]."""
    if command.ndim != 2 or command.shape[1] != 4 or time_s.shape != (command.shape[0],):
        raise ValueError(f"unexpected command/time shapes: {command.shape}, {time_s.shape}")
    dt = np.diff(time_s)
    if not np.isfinite(command).all() or not np.isfinite(time_s).all():
        raise ValueError("command or time contains non-finite values")
    if not np.all(dt > 0.0) or not np.allclose(dt, 0.001, rtol=0.0, atol=1e-12):
        raise ValueError("raw time must be strictly increasing at 1 ms intervals")
    if not np.isin(command, (-1.0, 0.0, 1.0)).all():
        raise ValueError("expected normalized command values in {-1, 0, 1}")

    z = np.zeros_like(command, dtype=np.float64)
    z[1:] = np.cumsum(dt[:, None] * command[:-1], axis=0)
    if not np.isfinite(z).all():
        raise ValueError("integrated command state contains non-finite values")
    return z


def self_check() -> None:
    time_s = np.array([0.0, 0.001, 0.002])
    command = np.array([[1.0, 0.0, 0.0, 0.0],
                        [0.0, 0.0, 0.0, 0.0],
                        [0.0, 0.0, 0.0, 0.0]])
    z = past_command_integral(command, time_s)
    assert np.array_equal(z[:, 0], np.array([0.0, 0.001, 0.001]))
    assert np.array_equal(z[:, 1:], np.zeros((3, 3)))


def read_command_and_time(path: Path) -> tuple[np.ndarray, np.ndarray]:
    with h5py.File(path, "r") as raw:
        command_stored = np.asarray(raw["scene/arms/command"][()])
        time_stored = np.asarray(raw["scene/time"][()])
    # MATLAB v7.3 stores these channels transposed relative to time-major use.
    if command_stored.shape != (4, N_SAMPLES) or time_stored.shape != (1, N_SAMPLES):
        raise ValueError(f"unexpected stored shapes: {command_stored.shape}, {time_stored.shape}")
    return command_stored.T.astype(np.float64, copy=False), time_stored.reshape(-1).astype(np.float64, copy=False)


def read_rho_truth_after_prediction(path: Path) -> np.ndarray:
    # Truth is opened only after z has been computed; it is used for comparison only.
    with h5py.File(path, "r") as raw:
        rho_stored = np.asarray(raw["scene/arms/rho_true"][()])
    if rho_stored.shape != (4, N_SAMPLES):
        raise ValueError(f"unexpected rho_true stored shape: {rho_stored.shape}")
    rho = rho_stored.T.astype(np.float64, copy=False)
    if not np.isfinite(rho).all():
        raise ValueError("rho_true contains non-finite values")
    return rho


def summarize_scene(repo: Path, item: tuple[str, str, str, str]) -> dict:
    split, scene_id, relative_path, expected_sha = item
    path = repo / relative_path
    if not path.is_file():
        raise FileNotFoundError(path)
    actual_sha = sha256_file(path)
    if actual_sha != expected_sha:
        raise ValueError(f"raw SHA mismatch for {scene_id}: {actual_sha}")

    command, time_s = read_command_and_time(path)
    z = past_command_integral(command, time_s)

    command_off = np.all(command == 0.0, axis=1)
    memory_nonzero = np.any(np.abs(z) > MEMORY_ZERO_TOL_S, axis=1)
    off_with_memory = command_off & memory_nonzero
    off_indices = np.flatnonzero(off_with_memory)
    memory_summary = {
        "command_off_definition": "all four command channels are exactly zero",
        "nonzero_memory_threshold_s": MEMORY_ZERO_TOL_S,
        "sample_count": int(off_indices.size),
        "first_sample_index_zero_based": int(off_indices[0]) if off_indices.size else None,
        "last_sample_index_zero_based": int(off_indices[-1]) if off_indices.size else None,
        "peak_abs_memory_s": float(np.max(np.abs(z[off_with_memory]))) if off_indices.size else 0.0,
        "interpretation": "command-off with prior accumulated command; consistent with held extension, but phase is not independently inferred from truth",
    }

    rho_proxy = INITIAL_RHO_M + PRESCRIBED_SPEED_MPS * z
    rho_true = read_rho_truth_after_prediction(path)
    error = rho_proxy - rho_true
    if not np.isfinite(rho_proxy).all() or not np.isfinite(error).all():
        raise ValueError("proxy or comparison error contains non-finite values")

    per_arm = []
    for arm in range(4):
        e = error[:, arm]
        per_arm.append({
            "arm_zero_based": arm,
            "max_abs_error_m": float(np.max(np.abs(e))),
            "rms_error_m": float(np.sqrt(np.mean(e * e))),
            "command_off_nonzero_memory_samples": int(np.count_nonzero(
                (command[:, arm] == 0.0) & (np.abs(z[:, arm]) > MEMORY_ZERO_TOL_S))),
        })

    return {
        "split": split,
        "scene_id": scene_id,
        "raw_relative_path": relative_path,
        "raw_sha256": actual_sha,
        "sample_count": N_SAMPLES,
        "sample_period_s": 0.001,
        "stored_shapes": {"command": [4, N_SAMPLES], "time": [1, N_SAMPLES], "rho_true": [4, N_SAMPLES]},
        "input_channels": 4,
        "internal_memory_channels": 4,
        "memory_definition": "z[k] = sum(i < k) diff(time)[i] * command[i]",
        "command_off_memory": memory_summary,
        "comparison_only": {
            "proxy_definition": "rho_proxy = 0.15 m + 0.05 m/s * z; no clipping or fitted alignment",
            "truth_used_only_after_proxy_computed": True,
            "max_abs_error_m": float(np.max(np.abs(error))),
            "rms_error_m": float(np.sqrt(np.mean(error * error))),
            "per_arm": per_arm,
        },
    }


def write_new_json(path: Path, payload: dict) -> None:
    encoded = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        fd = os.open(path, flags, 0o644)
    except FileExistsError as exc:
        raise FileExistsError(f"refusing to overwrite existing output: {path}") from exc
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise


def main() -> None:
    self_check()
    script_path = Path(__file__).resolve()
    repo = script_path.parents[2]
    output_path = script_path.with_name("COMMAND_MEMORY_DIAGNOSTIC_v1.json")
    scenes = [summarize_scene(repo, item) for item in SCENES]
    payload = {
        "schema": "COMMAND_MEMORY_DIAGNOSTIC_REPRODUCED_V1",
        "script_relative_path": str(script_path.relative_to(repo)).replace("\\", "/"),
        "script_sha256": sha256_file(script_path),
        "reproduction_command": "python reports/attitude_redesign_20261024/command_memory_diagnostic_v1.py",
        "definition": "past-only four-channel command integral, initialized at zero; rho_proxy is computed without rho_true",
        "assumptions_for_offline_comparison_only": {
            "initial_rho_m": INITIAL_RHO_M,
            "prescribed_extension_speed_mps": PRESCRIBED_SPEED_MPS,
            "not_measured_shape": True,
        },
        "scenes": scenes,
        "new_rollouts": 0,
        "training_steps": 0,
        "plant_runs": 0,
        "test_data_read": False,
    }
    write_new_json(output_path, payload)
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()

