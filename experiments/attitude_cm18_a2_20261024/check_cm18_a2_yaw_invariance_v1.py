"""Small CPU-only A2 invariance/gradient/parity check; never trains or reads caches."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from typing import Any

if os.environ.get("KMP_DUPLICATE_LIB_OK"):
    raise RuntimeError("KMP_DUPLICATE_LIB_OK is forbidden")
for _name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
    os.environ[_name] = "1"
os.environ["MKL_THREADING_LAYER"] = "SEQUENTIAL"
os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"

import numpy as np
import torch
import torch.nn.functional as F

from model_cm18_a2_v1 import forward as a2_forward, initialize_random_parameters as a2_initialize
from torch_model_cm18_a2_v1 import TorchCM18A2


A1_DIR = Path("experiments/attitude_cm18_a1_20261024")
A2_DIR = Path("experiments/attitude_cm18_a2_20261024")
REPORT_DIR = Path("reports/attitude_cm18_a2_20261024")
SEED = 2026102001
PARAMETER_NAMES = ("W1", "b1", "W2", "b2", "W3", "b3", "input_mean", "input_std", "train_axis_rms_rad_s2")


def _load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parameters_from_archive(path: Path, normalizer_path: Path) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    norm = json.loads(normalizer_path.read_text(encoding="utf-8"))
    with np.load(path, allow_pickle=False) as archive:
        saved = {name: archive[name].copy() for name in PARAMETER_NAMES}
    expected = {
        "input_mean": np.asarray(norm["input_mean_float64"], dtype=np.float64),
        "input_std": np.asarray(norm["input_std_float64"], dtype=np.float64),
        "train_axis_rms_rad_s2": np.asarray(norm["train_axis_rms_rad_s2_float64"], dtype=np.float64),
    }
    for name, value in expected.items():
        if not np.array_equal(saved[name], value):
            raise AssertionError(f"A1 initial archive and canonical normalizer differ for {name}")
    return saved, norm


def _write_fixture(path: Path, p: dict[str, np.ndarray], a1: Any) -> str:
    x = np.linspace(-0.7, 0.8, 18, dtype=np.float64)
    x[3:5] = [2.75, -4.5]
    x[7:11] = [-1.0, 0.25, 1.0, -0.5]
    x[11:15] = [0.04, 0.02, 0.06, 0.08]
    perturbed = x.copy()
    perturbed[3:5] = [-901.0, 733.0]
    zero = x.copy()
    zero[7:15] = 0.0
    a2_case = a2_forward(x, p)
    a2_perturbed = a2_forward(perturbed, p)
    a2_zero = a2_forward(zero, p)
    a1_case = a1.forward(x, p)
    fixture = {
        "schema": "CM18_A2_PARITY_FIXTURE_V1",
        "description": "Synthetic float64 shared-weight fixture; raw alphaBS x/y are masked before normalization only in yaw branch.",
        "raw_features": x.tolist(),
        "perturbed_alphaBS_features": perturbed.tolist(),
        "zero_basis_features": zero.tolist(),
        "parameters": {name: p[name].tolist() for name in PARAMETER_NAMES},
        "expected": {
            "physical_output_rad_s2": a2_case["physical_output_rad_s2"].tolist(),
            "normalized_output": a2_case["normalized_output"].tolist(),
            "coefficients_3x8": a2_case["coefficients_3x8"].tolist(),
            "basis_8": a2_case["basis_8"].tolist(),
            "yaw_masked_raw_features": a2_case["yaw_masked_raw_features"].tolist(),
            "yaw_masked_normalized_features": a2_case["yaw_masked_normalized_features"].tolist(),
            "perturbed_physical_output_rad_s2": a2_perturbed["physical_output_rad_s2"].tolist(),
            "zero_basis_physical_output_rad_s2": a2_zero["physical_output_rad_s2"].tolist(),
            "a1_full_physical_output_rad_s2": a1_case["physical_output_rad_s2"].tolist(),
        },
        "tolerance_abs": 1e-11,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(fixture, indent=2, allow_nan=False) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != encoded:
            raise FileExistsError(f"existing fixture differs; refusing to overwrite: {path}")
    else:
        path.write_text(encoded, encoding="utf-8", newline="\n")
    return _sha256(path)


def run_checks(repo: Path, fixture_path: Path, result_path: Path) -> dict[str, Any]:
    repo = repo.resolve(strict=True)
    a1_dir = repo / A1_DIR
    a1_ref = _load_module(a1_dir / "model_cm18_v1.py", "cm18_a1_reference_for_a2_check")
    archive = a1_dir / "training_run_v1" / "initial_parameters.npz"
    norm_path = a1_dir / "training_run_v1" / "normalizer.json"
    saved, norm = _parameters_from_archive(archive, norm_path)
    mean, std, axis_rms = saved["input_mean"], saved["input_std"], saved["train_axis_rms_rad_s2"]

    a1_initialized = a1_ref.initialize_random_parameters(SEED, mean, std, axis_rms)
    p = a2_initialize(SEED, mean, std, axis_rms)
    for name in PARAMETER_NAMES:
        if not np.array_equal(a1_initialized[name], saved[name]):
            raise AssertionError(f"A1 deterministic initializer differs from sealed initial archive: {name}")
        if not np.array_equal(p[name], saved[name]):
            raise AssertionError(f"A2 initial parameter is not exactly A1 initial parameter: {name}")

    torch_model = TorchCM18A2(mean, std, axis_rms).cpu().double()
    torch_model.load_numpy_parameters(p)
    loaded = torch_model.numpy_parameters()
    if any(not np.array_equal(loaded[name], p[name]) for name in PARAMETER_NAMES):
        raise AssertionError("Torch A2 parameter loading changed an initial array")
    parameter_count = sum(parameter.numel() for parameter in torch_model.parameters())
    if parameter_count != 2456:
        raise AssertionError(f"expected 2456 trainable parameters, got {parameter_count}")

    rng = np.random.default_rng(0xA2C018)
    x = rng.normal(size=(7, 18)).astype(np.float64)
    x[:, 7:11] = rng.uniform(-1, 1, size=(7, 4))
    x[:, 11:15] = rng.uniform(0, 0.5, size=(7, 4))
    changed = x.copy()
    changed[:, 3:5] = rng.normal(0, 1000, size=(7, 2))
    result, changed_result = a2_forward(x, p), a2_forward(changed, p)
    if not np.array_equal(result["physical_output_rad_s2"][:, 2], changed_result["physical_output_rad_s2"][:, 2]):
        raise AssertionError("NumPy yaw output changed under arbitrary current alphaBS x/y perturbation")
    if not np.array_equal(result["coefficients_3x8"][:, :2], result["full_coefficients_3x8"][:, :2]):
        raise AssertionError("roll/pitch coefficients are not from the full-input forward")
    if not np.array_equal(result["coefficients_3x8"][:, 2], result["yaw_masked_coefficients_3x8"][:, 2]):
        raise AssertionError("yaw coefficients are not from the masked-input forward")
    if np.any(result["yaw_masked_raw_features"][:, 3:5] != 0.0):
        raise AssertionError("yaw branch did not mask raw alphaBS x/y to literal zero")
    if np.allclose(mean[3:5], 0.0, rtol=0.0, atol=0.0):
        raise AssertionError("sealed normalizer unexpectedly has zero alphaBS x/y means")
    expected_norm = -mean[3:5] / std[3:5]
    np.testing.assert_array_equal(result["yaw_masked_normalized_features"][:, 3:5], np.broadcast_to(expected_norm, (len(x), 2)))
    if np.all(result["yaw_masked_normalized_features"][:, 3:5] == 0.0):
        raise AssertionError("mask was incorrectly applied after normalization")

    a1_result = a1_ref.forward(x, p)
    np.testing.assert_array_equal(result["physical_output_rad_s2"][:, :2], a1_result["physical_output_rad_s2"][:, :2])
    np.testing.assert_array_equal(result["coefficients_3x8"][:, :2], a1_result["coefficients_3x8"][:, :2])

    zero_basis = x[:2].copy()
    zero_basis[:, 7:15] = 0.0
    zero_result = a2_forward(zero_basis, p)["physical_output_rad_s2"]
    if not np.array_equal(zero_result, np.zeros((2, 3), dtype=np.float64)):
        raise AssertionError("zero morphology basis must produce exact zero output")
    single = a2_forward(x[0], p)
    batch_first = a2_forward(x, p)
    np.testing.assert_allclose(single["physical_output_rad_s2"], batch_first["physical_output_rad_s2"][0], rtol=0.0, atol=1e-12)

    xt = torch.tensor(x, dtype=torch.float64, requires_grad=True)
    tout = torch_model(xt)
    yaw_input_grad = torch.autograd.grad(tout["physical_output_rad_s2"][:, 2].sum(), xt, retain_graph=True)[0]
    if not torch.equal(yaw_input_grad[:, 3:5], torch.zeros_like(yaw_input_grad[:, 3:5])):
        raise AssertionError("yaw physical output must have exact zero input partials for raw alphaBS x/y")
    tchanged = torch.as_tensor(changed, dtype=torch.float64)
    if not torch.equal(tout["physical_output_rad_s2"][:, 2].detach(), torch_model(tchanged)["physical_output_rad_s2"][:, 2]):
        raise AssertionError("Torch yaw output changed under arbitrary current alphaBS x/y perturbation")

    numpy_batch = a2_forward(x, p)
    parity_errors = {}
    for field in ("physical_output_rad_s2", "normalized_output", "coefficients_3x8", "basis_8"):
        actual = tout[field].detach().cpu().numpy()
        reference = numpy_batch[field]
        parity_errors[field] = float(np.max(np.abs(actual - reference)))
        np.testing.assert_allclose(actual, reference, rtol=0.0, atol=1e-12)
    torch_single = torch_model(torch.as_tensor(x[0], dtype=torch.float64))
    np.testing.assert_allclose(torch_single["physical_output_rad_s2"].detach().numpy(), tout["physical_output_rad_s2"][0].detach().numpy(), rtol=0.0, atol=1e-12)
    torch_zero = torch_model(torch.as_tensor(zero_basis, dtype=torch.float64))["physical_output_rad_s2"]
    if not torch.equal(torch_zero, torch.zeros_like(torch_zero)):
        raise AssertionError("Torch zero morphology basis must produce exact zero output")

    target = torch.as_tensor(rng.normal(size=(len(x), 3)), dtype=torch.float64)
    out = torch_model(xt)
    scaled = out["physical_output_rad_s2"] / torch_model.train_axis_rms_rad_s2
    full_scaled = out["full_coefficients_3x8"]
    basis = out["basis_8"]
    full_phys = torch.bmm(full_scaled, basis.unsqueeze(-1)).squeeze(-1) * torch_model.train_axis_rms_rad_s2
    yaw_phys = torch.sum(out["yaw_masked_coefficients_3x8"][:, 2, :] * basis, dim=1) * torch_model.train_axis_rms_rad_s2[2]
    full_loss = F.smooth_l1_loss(full_phys[:, :2] / torch_model.train_axis_rms_rad_s2[:2], target[:, :2], beta=1.0, reduction="mean")
    yaw_loss = F.smooth_l1_loss(yaw_phys / torch_model.train_axis_rms_rad_s2[2], target[:, 2], beta=1.0, reduction="mean")
    joint_loss = F.smooth_l1_loss(scaled, target, beta=1.0, reduction="mean")
    if not all(torch.isfinite(value).item() for value in (full_loss, yaw_loss, joint_loss)):
        raise AssertionError("full, yaw, and joint losses must be finite")
    params = tuple(torch_model.parameters())
    full_grads = torch.autograd.grad(full_loss, params, retain_graph=True)
    yaw_grads = torch.autograd.grad(yaw_loss, params, retain_graph=True)
    joint_grads = torch.autograd.grad(joint_loss, params)
    max_joint_gradient_error = 0.0
    full_norm, yaw_norm_grad = 0.0, 0.0
    for g_full, g_yaw, g_joint in zip(full_grads, yaw_grads, joint_grads):
        if not all(torch.isfinite(value).all().item() for value in (g_full, g_yaw, g_joint)):
            raise AssertionError("full, yaw, and joint parameter gradients must be finite")
        full_norm += float(torch.sum(g_full.square()).item())
        yaw_norm_grad += float(torch.sum(g_yaw.square()).item())
        expected = (2.0 / 3.0) * g_full + (1.0 / 3.0) * g_yaw
        max_joint_gradient_error = max(max_joint_gradient_error, float(torch.max(torch.abs(g_joint - expected)).item()))
    full_norm, yaw_norm_grad = full_norm ** 0.5, yaw_norm_grad ** 0.5
    if not all(np.isfinite(value) for value in (full_norm, yaw_norm_grad, max_joint_gradient_error)):
        raise AssertionError("gradient norms and joint-gradient error must be finite")
    if full_norm == 0 or yaw_norm_grad == 0:
        raise AssertionError("both shared forward paths must contribute a nonzero parameter gradient")
    if max_joint_gradient_error > 1e-13:
        raise AssertionError(f"joint three-axis gradient does not equal weighted shared-branch gradients: {max_joint_gradient_error}")
    if not torch.isfinite(joint_loss):
        raise AssertionError("joint A2 loss is non-finite")

    fixture_path = fixture_path.resolve()
    if not fixture_path.is_relative_to(repo):
        raise ValueError("fixture must be written within the repository")
    fixture_sha = _write_fixture(fixture_path, p, a1_ref)
    result = {
        "schema": "CM18_A2_SOURCE_CHECK_RESULT_V1",
        "status": "PASS",
        "device": "cpu",
        "torch_dtype": "float64",
        "training_started": False,
        "optimizer_objects_created": 0,
        "optimizer_steps": 0,
        "plant_calls": 0,
        "cache_files_read": 0,
        "parameter_count": parameter_count,
        "a1_initial_arrays_sha256": _sha256(archive),
        "a1_normalizer_sha256": _sha256(norm_path),
        "initial_arrays_exactly_match_a1": True,
        "raw_zero_before_normalization": True,
        "nonzero_alphaBS_normalizer_means": mean[3:5].tolist(),
        "normalized_masked_alphaBS": expected_norm.tolist(),
        "yaw_perturbation_invariance_exact": True,
        "yaw_input_partial_exact_zero": True,
        "roll_pitch_match_a1_exact": True,
        "zero_basis_exact_zero": True,
        "batch_single_atol_1e-12_pass": True,
        "numpy_torch_float64_max_abs_error": parity_errors,
        "joint_gradient_matches_two_shared_branches_max_abs_error": max_joint_gradient_error,
        "branch_gradient_l2": {"full_roll_pitch": full_norm, "masked_yaw": yaw_norm_grad},
        "joint_smooth_l1": float(joint_loss.detach().item()),
        "fixture_path": str(fixture_path.relative_to(repo)).replace("\\", "/"),
        "fixture_sha256": fixture_sha,
        "source_files": {
            str((A2_DIR / name).as_posix()): _sha256(repo / A2_DIR / name)
            for name in ("model_cm18_a2_v1.py", "torch_model_cm18_a2_v1.py", "check_cm18_a2_yaw_invariance_v1.py",
                         "matlab/cm18_a2_forward_v1.m", "matlab/check_cm18_a2_parity_v1.m")
        },
        "environment": {name: os.environ.get(name) for name in ("MKL_THREADING_LAYER", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "CUBLAS_WORKSPACE_CONFIG")},
    }
    if result_path.exists():
        raise FileExistsError(f"refusing to overwrite result: {result_path}")
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--fixture", type=Path, default=Path("reports/attitude_cm18_a2_20261024/cm18_a2_parity_fixture_v1.json"))
    parser.add_argument("--result", type=Path, default=Path("reports/attitude_cm18_a2_20261024/A2_SOURCE_CHECK_RESULT_v2.json"))
    args = parser.parse_args()
    print(json.dumps(run_checks(args.repo_root, args.fixture if args.fixture.is_absolute() else args.repo_root / args.fixture,
                                args.result if args.result.is_absolute() else args.repo_root / args.result),
                     indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
