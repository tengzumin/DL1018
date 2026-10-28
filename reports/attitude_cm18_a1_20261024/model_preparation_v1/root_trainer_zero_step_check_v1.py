"""Independent CM18 SCREEN4 zero-step check; CUDA runs only when explicitly requested."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path

# These must be set before importing NumPy, SciPy, or Torch.
if os.environ.get("KMP_DUPLICATE_LIB_OK"):
    raise RuntimeError("KMP_DUPLICATE_LIB_OK is forbidden")
os.environ.update(MKL_THREADING_LAYER="SEQUENTIAL", OMP_NUM_THREADS="1",
                  MKL_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1",
                  CUBLAS_WORKSPACE_CONFIG=":4096:8")

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[3]
SCREEN4 = "reports/attitude_cm18_a1_20261024/data_preparation_v1/events_screen4_v1/DATASET_MANIFEST_v1.json"
SCREEN4_SHA = "b36a9027202a15408d69676c5e16f7993652c4c7a82c6a8695a64eb77961ef7c"
SEED = 2026102001
PINS = {
    "experiments/attitude_cm18_a1_20261024/cache_reader_cm18_v1.py": "a2867cbf516d7ed655a6f50e05b8600ffb7582e0f2164b1ce21d5e647adf2b47",
    "experiments/attitude_cm18_a1_20261024/model_cm18_v1.py": "ad32c4f97bf96c63172547c944d80c45062502f1062b774934e0f7a868720cf6",
    "experiments/attitude_cm18_a1_20261024/torch_model_cm18_v1.py": "bc9fe34fe957cb624438eeccfdfe2ddd38ad40cc9a4e706ce58863c9271d5aa0",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_module(root: Path, relative: str, name: str):
    path = (root / relative).resolve(strict=True)
    if not path.is_relative_to(root.resolve(strict=True)):
        raise ValueError(f"source path escaped repo: {relative}")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(root: Path, device_name: str) -> dict:
    root = root.resolve(strict=True)
    manifest = (root / SCREEN4).resolve(strict=True)
    if sha256(manifest) != SCREEN4_SHA:
        raise ValueError("pinned SCREEN4 manifest SHA mismatch")
    hashes = {rel: sha256((root / rel).resolve(strict=True)) for rel in PINS}
    if hashes != PINS:
        raise ValueError(f"pinned model/reader source SHA mismatch: {hashes}")
    reader = load_module(root, next(k for k in PINS if k.endswith("cache_reader_cm18_v1.py")), "zero_check_reader")
    numpy_model = load_module(root, next(k for k in PINS if k.endswith("model_cm18_v1.py")), "zero_check_numpy_model")
    torch_model = load_module(root, next(k for k in PINS if k.endswith("torch_model_cm18_v1.py")), "zero_check_torch_model")
    train = reader.load_qualified_split(root, SCREEN4, "TRAIN", SCREEN4_SHA)
    if len(train) != 2 or [s["split"] for s in train] != ["TRAIN", "TRAIN"]:
        raise ValueError("SCREEN4 must provide its two TRAIN scenes in manifest order")
    indices = np.arange(0, 1996, 5, dtype=np.int64)
    x = np.concatenate([s["X18"][indices] for s in train], axis=0)
    y = np.concatenate([s["target_raw"][indices] for s in train], axis=0)
    mean = x.mean(axis=0, dtype=np.float64)
    std = np.maximum(x.std(axis=0, dtype=np.float64, ddof=0), 1e-6)
    rms = np.sqrt(np.mean(np.square(y, dtype=np.float64), axis=0, dtype=np.float64))
    if x.shape != (800, 18) or y.shape != (800, 3) or np.any(rms <= 0):
        raise ValueError("invalid SCREEN4 TRAIN-only normalizer inputs")
    active = np.flatnonzero(np.any(x[:, 7:15] != 0.0, axis=1))[:64]
    if len(active) != 64:
        raise ValueError("fewer than 64 nonzero [z/2,u] basis rows in SCREEN4 TRAIN")

    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    if hasattr(torch, "set_float32_matmul_precision"):
        torch.set_float32_matmul_precision("highest")
    if device_name == "cuda:0":
        if not torch.cuda.is_available() or torch.cuda.device_count() < 1:
            raise RuntimeError("cuda:0 requested but unavailable")
        torch.cuda.set_device(0)
    device = torch.device(device_name)
    torch.manual_seed(SEED)
    if device.type == "cuda":
        torch.cuda.manual_seed_all(SEED)

    parameters = numpy_model.initialize_random_parameters(SEED, mean, std, rms)
    model = torch_model.TorchCM18A1(mean, std, rms)
    model.load_numpy_parameters(parameters)
    model = model.float().to(device).train()
    before = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
    raw = torch.as_tensor(x[active].astype(np.float32), dtype=torch.float32, device=device)
    target = torch.as_tensor((y[active] / rms).astype(np.float32), dtype=torch.float32, device=device)
    pred = model(raw)["physical_output_rad_s2"] / model.train_axis_rms_rad_s2
    loss = torch.nn.functional.smooth_l1_loss(pred, target, beta=1.0, reduction="mean")
    if not torch.isfinite(loss).item():
        raise FloatingPointError("non-finite forward loss")
    loss.backward()
    gradients = [p.grad for p in model.parameters()]
    if any(g is None or not torch.isfinite(g).all().item() for g in gradients):
        raise FloatingPointError("missing or non-finite parameter gradient")
    if not any(torch.count_nonzero(g).item() for g in gradients):
        raise AssertionError("backward produced no nonzero gradients")
    after = model.state_dict()
    unchanged = all(torch.equal(value, after[key].detach().cpu()) for key, value in before.items())
    if not unchanged:
        raise AssertionError("backward changed model parameters or buffers")

    f32_output = model(raw)["physical_output_rad_s2"].detach().cpu().numpy().astype(np.float64)
    promoted = {key: value.astype(np.float64) for key, value in model.numpy_parameters().items()}
    promoted.update(input_mean=mean.copy(), input_std=std.copy(), train_axis_rms_rad_s2=rms.copy())
    double_model = torch_model.TorchCM18A1(mean, std, rms)
    double_model.load_numpy_parameters(promoted)
    double_model = double_model.to(device).eval()
    with torch.no_grad():
        double_output = double_model(torch.as_tensor(x[active], dtype=torch.float64, device=device))["physical_output_rad_s2"].cpu().numpy()
    deviation = float(np.max(np.abs(f32_output - double_output)))
    return {
        "schema": "CM18_A1_TRAINER_ZERO_STEP_CHECK_V1", "status": "PASS",
        "device": device_name, "gpu_name": torch.cuda.get_device_name(0) if device.type == "cuda" else None,
        "screen4_manifest_sha256": SCREEN4_SHA, "source_sha256": hashes,
        "train_fit_rows": int(len(x)), "nonzero_basis_rows": int(len(active)),
        "normalizer_source": "SCREEN4 TRAIN only, offsets 0,5,...,1995, float64; std ddof=0",
        "train_axis_rms_rad_s2": rms.tolist(), "loss": float(loss.detach().cpu()),
        "all_parameter_gradients_finite": True, "at_least_one_nonzero_gradient": True,
        "parameters_and_buffers_unchanged_after_backward": unchanged,
        "optimizer_instances_created": 0, "optimizer_step_calls": 0,
        "float32_vs_canonical_double_max_abs_output_delta_rad_s2": deviation,
        "torch_deterministic_algorithms": True, "tf32": False,
        "environment": {k: os.environ.get(k) for k in ("MKL_THREADING_LAYER", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "CUBLAS_WORKSPACE_CONFIG")},
        "training_started": False, "Plant_calls": 0, "TEST_accessed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--device", choices=("cpu", "cuda:0"), default="cpu")
    args = parser.parse_args()
    report = run(args.repo_root, args.device)
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()

