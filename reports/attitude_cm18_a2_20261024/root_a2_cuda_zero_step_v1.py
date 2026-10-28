"""Independent A2 CUDA zero-step check; run only after review, never trains or launches Plant."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
from typing import Any

if os.environ.get("KMP_DUPLICATE_LIB_OK"):
    raise RuntimeError("KMP_DUPLICATE_LIB_OK is forbidden")
os.environ.update(
    MKL_THREADING_LAYER="SEQUENTIAL",
    OMP_NUM_THREADS="1",
    MKL_NUM_THREADS="1",
    OPENBLAS_NUM_THREADS="1",
    CUBLAS_WORKSPACE_CONFIG=":4096:8",
)

import numpy as np
import torch
import torch.nn.functional as F

torch.set_num_threads(1)
torch.set_num_interop_threads(1)


ROOT = Path(__file__).resolve().parents[2]
SCREEN4 = "reports/attitude_cm18_a1_20261024/data_preparation_v1/events_screen4_v1/DATASET_MANIFEST_v1.json"
SCREEN4_SHA = "b36a9027202a15408d69676c5e16f7993652c4c7a82c6a8695a64eb77961ef7c"
SOURCE_RESULT = "reports/attitude_cm18_a2_20261024/A2_SOURCE_CHECK_RESULT_v2.json"
A1_READER = "experiments/attitude_cm18_a1_20261024/cache_reader_cm18_v1.py"
A1_READER_SHA = "a2867cbf516d7ed655a6f50e05b8600ffb7582e0f2164b1ce21d5e647adf2b47"
A2_TORCH_MODEL = "experiments/attitude_cm18_a2_20261024/torch_model_cm18_a2_v1.py"
A2_NUMPY_MODEL = "experiments/attitude_cm18_a2_20261024/model_cm18_a2_v1.py"
A1_RUN = "experiments/attitude_cm18_a1_20261024/training_run_v1"
PARAMETER_NAMES = ("W1", "b1", "W2", "b2", "W3", "b3", "input_mean", "input_std", "train_axis_rms_rad_s2")
SOURCE_CHECK_EXPECTED = {
    "training_started": False,
    "optimizer_objects_created": 0,
    "optimizer_steps": 0,
    "plant_calls": 0,
    "cache_files_read": 0,
    "parameter_count": 2456,
    "initial_arrays_exactly_match_a1": True,
    "yaw_perturbation_invariance_exact": True,
    "yaw_input_partial_exact_zero": True,
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve(strict=True)
    if not path.is_relative_to(root.resolve(strict=True)):
        raise ValueError(f"path escaped repository: {relative}")
    return path


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def finite_tensor(name: str, value: torch.Tensor) -> None:
    if not torch.isfinite(value).all().item():
        raise FloatingPointError(f"{name} contains a non-finite value")


def gradient_norm(name: str, gradients: tuple[torch.Tensor, ...]) -> float:
    total = torch.zeros((), dtype=torch.float64, device=gradients[0].device)
    for gradient in gradients:
        finite_tensor(f"{name} gradient", gradient)
        total = total + gradient.detach().to(torch.float64).square().sum()
    result = float(torch.sqrt(total).item())
    if not math.isfinite(result):
        raise FloatingPointError(f"{name} gradient norm is non-finite")
    return result


def run(root: Path) -> dict[str, Any]:
    root = root.resolve(strict=True)
    if not torch.cuda.is_available() or torch.cuda.device_count() < 1:
        raise RuntimeError("CUDA zero-step check requires cuda:0; no CPU fallback")
    torch.cuda.set_device(0)
    if torch.cuda.current_device() != 0:
        raise RuntimeError("active CUDA device is not device 0")
    device = torch.device("cuda:0")

    source_result_path = safe_path(root, SOURCE_RESULT)
    source_result = json.loads(source_result_path.read_text(encoding="utf-8"))
    if source_result.get("schema") != "CM18_A2_SOURCE_CHECK_RESULT_V1" or source_result.get("status") != "PASS":
        raise ValueError("A2 v2 CPU source-check result is missing or not PASS")
    if source_result.get("device") != "cpu" or source_result.get("torch_dtype") != "float64":
        raise ValueError("A2 source-check result must certify CPU float64 checks")
    for key, expected in SOURCE_CHECK_EXPECTED.items():
        if source_result.get(key) != expected:
            raise ValueError(f"A2 source-check prerequisite {key} is not {expected!r}")

    source_files = source_result.get("source_files")
    if not isinstance(source_files, dict) or not source_files:
        raise ValueError("A2 v2 CPU result must contain source_files SHA pins")
    verified_sources = {}
    for relative in (A2_NUMPY_MODEL, A2_TORCH_MODEL):
        expected_sha = source_files.get(relative)
        if not isinstance(expected_sha, str) or len(expected_sha) != 64:
            raise ValueError(f"A2 CPU result is missing source SHA for {relative}")
        actual_sha = sha256(safe_path(root, relative))
        if actual_sha != expected_sha.lower():
            raise ValueError(f"A2 CPU-pinned source changed: {relative}")
        verified_sources[relative] = actual_sha
    reader_path = safe_path(root, A1_READER)
    if sha256(reader_path) != A1_READER_SHA:
        raise ValueError("A1 qualified cache-reader SHA mismatch")
    verified_sources[A1_READER] = A1_READER_SHA

    manifest_path = safe_path(root, SCREEN4)
    if sha256(manifest_path) != SCREEN4_SHA:
        raise ValueError("pinned SCREEN4 manifest SHA mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    train_rows = [row for row in manifest["rows"] if row.get("split") == "TRAIN"]
    if len(train_rows) != 2 or any(row.get("qualified") is not True or row.get("status") != "PASS" for row in train_rows):
        raise ValueError("SCREEN4 must contain exactly two qualified TRAIN caches")

    archive_path = safe_path(root, f"{A1_RUN}/initial_parameters.npz")
    normalizer_path = safe_path(root, f"{A1_RUN}/normalizer.json")
    archive_sha = sha256(archive_path)
    normalizer_sha = sha256(normalizer_path)
    if archive_sha != source_result.get("a1_initial_arrays_sha256"):
        raise ValueError("A1 initial array archive SHA differs from A2 CPU result")
    if normalizer_sha != source_result.get("a1_normalizer_sha256"):
        raise ValueError("A1 normalizer SHA differs from A2 CPU result")
    normalizer = json.loads(normalizer_path.read_text(encoding="utf-8"))
    with np.load(archive_path, allow_pickle=False) as archive:
        parameters = {name: archive[name].copy() for name in PARAMETER_NAMES}
    canonical = {
        "input_mean": np.asarray(normalizer["input_mean_float64"], dtype=np.float64),
        "input_std": np.asarray(normalizer["input_std_float64"], dtype=np.float64),
        "train_axis_rms_rad_s2": np.asarray(normalizer["train_axis_rms_rad_s2_float64"], dtype=np.float64),
    }
    for name, values in parameters.items():
        if not np.isfinite(values).all():
            raise ValueError(f"initial parameter {name} is non-finite")
    for name, values in canonical.items():
        if not np.array_equal(parameters[name], values):
            raise ValueError(f"A1 archive and canonical normalizer differ for {name}")

    reader = load_module(reader_path, "a2_cuda_zero_step_cache_reader")
    scenes = reader.load_qualified_split(root, SCREEN4, "TRAIN", SCREEN4_SHA)
    expected_scenes = [row["scene_id"] for row in train_rows]
    if [scene["scene_id"] for scene in scenes] != expected_scenes:
        raise ValueError("SCREEN4 TRAIN scene order/identity mismatch")

    stride_rows = np.arange(0, 1996, 5, dtype=np.int64)
    candidate_x = np.concatenate([scene["X18"][stride_rows] for scene in scenes], axis=0)
    candidate_y = np.concatenate([scene["target_raw"][stride_rows] for scene in scenes], axis=0)
    candidate_scene = np.concatenate([
        np.full(stride_rows.size, scene["scene_id"], dtype=object) for scene in scenes
    ])
    candidate_index = np.concatenate([
        scene["plant_index"].reshape(-1)[stride_rows] for scene in scenes
    ])
    active = np.flatnonzero(np.any(candidate_x[:, 7:15] != 0.0, axis=1))[:64]
    if active.size != 64:
        raise ValueError("fewer than 64 active SCREEN4 TRAIN rows across both scenes")
    x, y = candidate_x[active], candidate_y[active]
    selected_identity = [
        f"{candidate_scene[i]}:{int(candidate_index[i])}" for i in active
    ]
    rows_by_scene = {
        scene["scene_id"]: int(np.count_nonzero(candidate_scene[active] == scene["scene_id"]))
        for scene in scenes
    }
    if x.shape != (64, 18) or y.shape != (64, 3) or not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError("expected 64 finite active SCREEN4 TRAIN rows")

    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    if hasattr(torch, "set_float32_matmul_precision"):
        torch.set_float32_matmul_precision("highest")
    if (
        not torch.are_deterministic_algorithms_enabled()
        or not torch.backends.cudnn.deterministic
        or torch.backends.cudnn.benchmark
        or torch.backends.cuda.matmul.allow_tf32
        or torch.backends.cudnn.allow_tf32
        or os.environ.get("CUBLAS_WORKSPACE_CONFIG") != ":4096:8"
    ):
        raise RuntimeError("CUDA deterministic / TF32-off preflight failed")

    torch.manual_seed(2026102001)
    torch.cuda.manual_seed_all(2026102001)
    torch_model_module = load_module(safe_path(root, A2_TORCH_MODEL), "a2_cuda_zero_step_model")
    model = torch_model_module.TorchCM18A2(
        canonical["input_mean"], canonical["input_std"], canonical["train_axis_rms_rad_s2"]
    )
    model.load_numpy_parameters(parameters)
    model = model.float().to(device).train()
    if sum(parameter.numel() for parameter in model.parameters()) != 2456:
        raise ValueError("A2 model parameter count changed")
    if any(parameter.device != device for parameter in model.parameters()):
        raise RuntimeError("A2 model parameters are not on cuda:0")

    before = {name: value.detach().cpu().clone() for name, value in model.state_dict().items()}
    raw = torch.as_tensor(x, dtype=torch.float32, device=device).requires_grad_(True)
    target = torch.as_tensor(
        y / canonical["train_axis_rms_rad_s2"], dtype=torch.float32, device=device
    )
    output = model(raw)
    yaw_input_gradient = torch.autograd.grad(
        output["physical_output_rad_s2"][:, 2].sum(), raw, retain_graph=True
    )[0]
    finite_tensor("raw-input gradient", yaw_input_gradient)
    if not torch.equal(
        yaw_input_gradient[:, 3:5], torch.zeros_like(yaw_input_gradient[:, 3:5])
    ):
        raise AssertionError("yaw output has nonzero gradient to raw alphaBS x/y")
    if torch.any(output["yaw_masked_raw_features"][:, 3:5] != 0.0).item():
        raise AssertionError("yaw branch did not set raw alphaBS x/y to zero")

    axis_rms = model.train_axis_rms_rad_s2
    scaled_output = output["physical_output_rad_s2"] / axis_rms
    full_physical = (
        torch.bmm(output["full_coefficients_3x8"], output["basis_8"].unsqueeze(-1)).squeeze(-1)
        * axis_rms
    )
    yaw_physical = (
        output["yaw_masked_coefficients_3x8"][:, 2, :] * output["basis_8"]
    ).sum(dim=1) * axis_rms[2]
    full_loss = F.smooth_l1_loss(
        full_physical[:, :2] / axis_rms[:2], target[:, :2], beta=1.0, reduction="mean"
    )
    yaw_loss = F.smooth_l1_loss(
        yaw_physical / axis_rms[2], target[:, 2], beta=1.0, reduction="mean"
    )
    joint_loss = F.smooth_l1_loss(scaled_output, target, beta=1.0, reduction="mean")
    for name, loss in (("full roll/pitch loss", full_loss), ("masked yaw loss", yaw_loss), ("joint loss", joint_loss)):
        finite_tensor(name, loss)

    trainable = tuple(model.parameters())
    full_gradients = torch.autograd.grad(full_loss, trainable, retain_graph=True)
    yaw_gradients = torch.autograd.grad(yaw_loss, trainable, retain_graph=True)
    joint_gradients = torch.autograd.grad(joint_loss, trainable, retain_graph=True)
    full_norm = gradient_norm("full roll/pitch", full_gradients)
    yaw_norm = gradient_norm("masked yaw", yaw_gradients)
    gradient_error = 0.0
    for full_gradient, yaw_gradient, joint_gradient in zip(full_gradients, yaw_gradients, joint_gradients):
        finite_tensor("joint parameter gradient", joint_gradient)
        expected = (2.0 / 3.0) * full_gradient + (1.0 / 3.0) * yaw_gradient
        gradient_error = max(
            gradient_error, float(torch.max(torch.abs(joint_gradient - expected)).item())
        )
    if not math.isfinite(gradient_error) or gradient_error > 1e-5:
        raise AssertionError(f"joint/shared-branch gradient relation failed: {gradient_error}")
    if full_norm == 0.0 or yaw_norm == 0.0:
        raise AssertionError("both shared forward branches must produce nonzero gradients")

    joint_loss.backward()
    backward_gradients = [parameter.grad for parameter in model.parameters()]
    if any(gradient is None for gradient in backward_gradients):
        raise AssertionError("backward left a trainable parameter without a gradient")
    for gradient in backward_gradients:
        finite_tensor("backward parameter gradient", gradient)
    if not any(torch.count_nonzero(gradient).item() for gradient in backward_gradients):
        raise AssertionError("backward produced no nonzero parameter gradient")
    torch.cuda.synchronize(device)
    unchanged = all(
        torch.equal(value, model.state_dict()[name].detach().cpu())
        for name, value in before.items()
    )
    if not unchanged:
        raise AssertionError("backward changed model parameters or buffers")

    with torch.no_grad():
        f32_output = model(raw)["physical_output_rad_s2"].detach().cpu().numpy().astype(np.float64)
        double_model = torch_model_module.TorchCM18A2(
            canonical["input_mean"], canonical["input_std"], canonical["train_axis_rms_rad_s2"]
        )
        double_model.load_numpy_parameters(parameters)
        double_model = double_model.to(device).eval()
        double_raw = torch.as_tensor(x, dtype=torch.float64, device=device)
        double_output = double_model(double_raw)["physical_output_rad_s2"].cpu().numpy()
    parity_delta = float(np.max(np.abs(f32_output - double_output)))
    if not math.isfinite(parity_delta):
        raise FloatingPointError("float32/canonical-double delta is non-finite")

    cache_identities = [
        {
            "scene_id": row["scene_id"],
            "split": row["split"],
            "cache_path": row["cache_path"],
            "cache_sha256": row["cache_sha256"],
            "cache_bytes": int(row["cache_bytes"]),
        }
        for row in train_rows
    ]
    return {
        "schema": "CM18_A2_CUDA_ZERO_STEP_CHECK_V1",
        "status": "PASS",
        "source_check_result_path": SOURCE_RESULT,
        "source_check_result_sha256": sha256(source_result_path),
        "cpu_result_source_files": source_files,
        "sha256_verified_sources": verified_sources,
        "checker_source_sha256": sha256(Path(__file__).resolve()),
        "a1_initial_arrays_sha256": archive_sha,
        "a1_normalizer_sha256": normalizer_sha,
        "normalizer_source": "canonical A1 formal initial archive/normalizer; no SCREEN4 refit",
        "dataset_manifest_path": SCREEN4,
        "dataset_manifest_sha256": SCREEN4_SHA,
        "cache_identities": cache_identities,
        "cache_files_read": 2,
        "forward_backward_rows": 64,
        "row_selection": "first 64 active rows after concatenating SCREEN4 TRAIN scenes in manifest order, offsets 0,5,...,1995",
        "selected_rows_by_scene": rows_by_scene,
        "selected_scene_plant_indices": selected_identity,
        "cuda_device": str(device),
        "cuda_current_device": int(torch.cuda.current_device()),
        "cuda_name": torch.cuda.get_device_name(0),
        "cuda_capability": list(torch.cuda.get_device_capability(0)),
        "torch_deterministic_algorithms": torch.are_deterministic_algorithms_enabled(),
        "cudnn_deterministic": torch.backends.cudnn.deterministic,
        "cudnn_benchmark": torch.backends.cudnn.benchmark,
        "cuda_matmul_tf32": torch.backends.cuda.matmul.allow_tf32,
        "cudnn_tf32": torch.backends.cudnn.allow_tf32,
        "cublas_workspace_config": os.environ["CUBLAS_WORKSPACE_CONFIG"],
        "losses": {
            "full_roll_pitch_smooth_l1": float(full_loss.detach().cpu()),
            "masked_yaw_smooth_l1": float(yaw_loss.detach().cpu()),
            "joint_smooth_l1": float(joint_loss.detach().cpu()),
        },
        "all_losses_finite": True,
        "all_branch_and_backward_gradients_finite": True,
        "branch_gradient_l2": {"full_roll_pitch": full_norm, "masked_yaw": yaw_norm},
        "joint_gradient_decomposition_max_abs_error": gradient_error,
        "yaw_alphaBS_xy_raw_input_gradient_exact_zero": True,
        "state_dict_unchanged_after_backward": unchanged,
        "optimizer_instances_created": 0,
        "optimizer_step_calls": 0,
        "float32_vs_canonical_double_initial_model_max_abs_output_delta_rad_s2": parity_delta,
        "training_started": False,
        "Plant_calls": 0,
        "TEST_accessed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument(
        "--result",
        type=Path,
        default=Path("reports/attitude_cm18_a2_20261024/ROOT_A2_CUDA_ZERO_STEP_RESULT_v1.json"),
    )
    args = parser.parse_args()
    root = args.repo_root.resolve(strict=True)
    result_path = args.result if args.result.is_absolute() else root / args.result
    result_path = result_path.resolve()
    if not result_path.is_relative_to(root):
        raise ValueError("result path must be inside the repository")
    if result_path.exists():
        raise FileExistsError(f"refusing to overwrite result: {result_path}")
    result = run(root)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    with result_path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()

