"""CPU-only parity and autograd check; no optimizer or training loop."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import torch

from model_cm18_v1 import forward as numpy_forward
from torch_model_cm18_v1 import TorchCM18A1


def check_fixture(path: Path) -> dict[str, Any]:
    fixture = json.loads(Path(path).read_text(encoding="utf-8"))
    if fixture.get("schema") != "CM18_A1_PARITY_FIXTURE_V1":
        raise ValueError("unexpected parity fixture schema")
    parameters = {
        name: np.asarray(value, dtype=np.float64)
        for name, value in fixture["parameters"].items()
    }
    model = TorchCM18A1(
        parameters["input_mean"],
        parameters["input_std"],
        parameters["train_axis_rms_rad_s2"],
    ).cpu().double()
    model.load_numpy_parameters(parameters)

    loaded = model.numpy_parameters()
    for name, expected in parameters.items():
        if not np.array_equal(loaded[name], expected):
            raise AssertionError(f"parameter load changed {name}")
    parameter_count = sum(p.numel() for p in model.parameters())
    if parameter_count != 2456:
        raise AssertionError(f"expected 2456 trainable parameters, got {parameter_count}")

    x = np.asarray(fixture["raw_features"], dtype=np.float64)
    x_zero = np.asarray(fixture["zero_basis_features"], dtype=np.float64)
    tolerance = float(fixture["tolerance_abs"])
    expected = fixture["expected"]

    numpy_result = numpy_forward(x, parameters)
    torch_result = model(torch.from_numpy(x))
    fields = (
        "coefficients_3x8",
        "basis_8",
        "normalized_output",
        "physical_output_rad_s2",
    )
    max_abs_error = {}
    for field in fields:
        actual = torch_result[field].detach().cpu().numpy()
        reference = numpy_result[field]
        if not np.isfinite(actual).all():
            raise AssertionError(f"Torch output {field} is non-finite")
        np.testing.assert_allclose(actual, reference, rtol=0.0, atol=tolerance)
        np.testing.assert_allclose(
            actual,
            np.asarray(expected[field], dtype=np.float64),
            rtol=0.0,
            atol=tolerance,
        )
        max_abs_error[field] = float(np.max(np.abs(actual - reference)))

    batch = np.stack((x, x_zero), axis=0)
    torch_batch = model(torch.from_numpy(batch))
    numpy_batch = numpy_forward(batch, parameters)
    np.testing.assert_allclose(
        torch_batch["physical_output_rad_s2"].detach().cpu().numpy(),
        numpy_batch["physical_output_rad_s2"],
        rtol=0.0,
        atol=tolerance,
    )
    zero = torch_batch["physical_output_rad_s2"][1]
    if not torch.equal(zero, torch.zeros_like(zero)):
        raise AssertionError("Torch output must be exactly zero when z=u=0")

    probe = torch.tensor(x, dtype=torch.float64, requires_grad=True)
    if not torch.autograd.gradcheck(
        lambda value: model(value)["physical_output_rad_s2"],
        (probe,),
        eps=1e-6,
        atol=1e-7,
        rtol=1e-5,
    ):
        raise AssertionError("input-gradient finite-difference check failed")

    output = model(probe)
    grad = torch.autograd.grad(output["physical_output_rad_s2"][0], model.fc3.bias)[0]
    analytic = model.train_axis_rms_rad_s2[0] * output["basis_8"][0]
    coefficient_grad_error = torch.abs(grad[0] - analytic).item()
    if coefficient_grad_error > 1e-12:
        raise AssertionError("coefficient-bias gradient does not match A(x) @ b")

    return {
        "schema": "CM18_TORCH_PARITY_RESULT_V1",
        "status": "PASS",
        "parameter_count": parameter_count,
        "parameter_load_exact": True,
        "maximum_numpy_torch_absolute_error": max_abs_error,
        "batch_and_exact_zero_pass": True,
        "input_gradcheck_pass": True,
        "coefficient_bias_gradient_abs_error": coefficient_grad_error,
        "device": "cpu",
        "optimizer_steps": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(check_fixture(args.fixture), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
