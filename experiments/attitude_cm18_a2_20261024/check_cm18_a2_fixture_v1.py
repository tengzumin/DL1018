"""Verify one A2 NumPy-to-fixture parity case on CPU; no training or Plant."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

if os.environ.get("KMP_DUPLICATE_LIB_OK"):
    raise RuntimeError("KMP_DUPLICATE_LIB_OK is forbidden")
os.environ.update(MKL_THREADING_LAYER="SEQUENTIAL", OMP_NUM_THREADS="1",
                  MKL_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1")

import numpy as np

from model_cm18_a2_v1 import forward


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(fixture_path: Path, result_path: Path) -> dict[str, object]:
    fixture_path = fixture_path.resolve(strict=True)
    if result_path.exists():
        raise FileExistsError(f"refusing to overwrite result: {result_path}")
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    if fixture.get("schema") != "CM18_A2_PARITY_FIXTURE_V1":
        raise ValueError("unexpected A2 parity fixture schema")
    p = {name: np.asarray(value, dtype=np.float64) for name, value in fixture["parameters"].items()}
    expected = fixture["expected"]
    tolerance = float(fixture["tolerance_abs"])
    x = np.asarray(fixture["raw_features"], dtype=np.float64)
    perturbed = np.asarray(fixture["perturbed_alphaBS_features"], dtype=np.float64)
    zero = np.asarray(fixture["zero_basis_features"], dtype=np.float64)
    output = forward(x, p)
    changed = forward(perturbed, p)
    zero_output = forward(zero, p)["physical_output_rad_s2"]
    errors: dict[str, float] = {}
    for name in ("physical_output_rad_s2", "normalized_output", "coefficients_3x8", "basis_8",
                 "yaw_masked_raw_features", "yaw_masked_normalized_features"):
        actual = output[name]
        reference = np.asarray(expected[name], dtype=np.float64)
        if actual.shape != reference.shape or not np.isfinite(actual).all() or not np.isfinite(reference).all():
            raise AssertionError(f"{name} shape or finite-value check failed")
        errors[name] = float(np.max(np.abs(actual - reference)))
        np.testing.assert_allclose(actual, reference, rtol=0.0, atol=tolerance)
    perturb_expected = np.asarray(expected["perturbed_physical_output_rad_s2"], dtype=np.float64)
    zero_expected = np.asarray(expected["zero_basis_physical_output_rad_s2"], dtype=np.float64)
    full_expected = np.asarray(expected["a1_full_physical_output_rad_s2"], dtype=np.float64)
    if not all(np.isfinite(value).all() for value in (perturb_expected, zero_expected, full_expected,
                                                       changed["physical_output_rad_s2"], zero_output)):
        raise AssertionError("perturbation or zero-basis fixture contains non-finite values")
    np.testing.assert_allclose(changed["physical_output_rad_s2"], perturb_expected, rtol=0.0, atol=tolerance)
    np.testing.assert_allclose(zero_output, zero_expected, rtol=0.0, atol=0.0)
    if not np.array_equal(zero_output, np.zeros(3, dtype=np.float64)):
        raise AssertionError("zero morphology basis must produce exact zero")
    np.testing.assert_allclose(output["physical_output_rad_s2"][:2], full_expected[:2], rtol=0.0, atol=tolerance)
    if not np.array_equal(output["physical_output_rad_s2"][2], changed["physical_output_rad_s2"][2]):
        raise AssertionError("yaw output changed under current alphaBS x/y perturbation")
    if np.any(output["yaw_masked_raw_features"][3:5] != 0.0):
        raise AssertionError("yaw mask was not applied to raw input")

    source_path = Path(__file__).resolve(strict=True)
    model_path = Path(__file__).with_name("model_cm18_a2_v1.py").resolve(strict=True)
    result = {
        "schema": "CM18_A2_FIXTURE_CHECK_RESULT_V1",
        "status": "PASS",
        "case_identity": fixture.get("case_identity"),
        "fixture_path": str(fixture_path),
        "fixture_sha256": _sha256(fixture_path),
        "checker_source_sha256": _sha256(source_path),
        "model_source_sha256": _sha256(model_path),
        "maximum_absolute_errors": errors,
        "yaw_invariance_exact": True,
        "zero_basis_exact_zero": True,
        "plant_calls": 0,
        "optimizer_steps": 0,
    }
    result_path.parent.mkdir(parents=True, exist_ok=True)
    with result_path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("result", type=Path)
    args = parser.parse_args()
    print(json.dumps(check(args.fixture, args.result), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
