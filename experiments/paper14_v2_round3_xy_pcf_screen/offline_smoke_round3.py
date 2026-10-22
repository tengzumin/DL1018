#!/usr/bin/env python3
"""Verify the MATLAB-only synthetic equation report using independent NumPy math."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
MATLAB_REPORT = HERE / "reports" / "offline_math_smoke_matlab_final.json"
PYTHON_REPORT = HERE / "reports" / "offline_math_smoke_python_final.json"
LOCK_PATH = HERE / "frozen_inputs.json"
TOL = 1e-12


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def close(actual: np.ndarray, expected: np.ndarray, label: str) -> float:
    actual = np.asarray(actual, dtype=float)
    expected = np.asarray(expected, dtype=float)
    if actual.shape != expected.shape or not np.isfinite(actual).all() or not np.isfinite(expected).all():
        raise RuntimeError(f"{label} shape/finiteness mismatch: {actual.shape} vs {expected.shape}")
    error = float(np.max(np.abs(actual - expected))) if actual.size else 0.0
    if error > TOL:
        raise RuntimeError(f"{label} error {error:g} exceeds {TOL:g}")
    return error


def setup_manifest_sha(lock: dict) -> str:
    canonical = ";".join(
        f"{entry['name']}|{entry['sha256'].lower()}" for entry in lock["setupFiles"]
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def locked_source_sha(lock: dict, name: str) -> str:
    matches = [entry["sha256"].lower() for entry in lock["setupFiles"] if entry["name"] == name]
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one locked setup source named {name}")
    return matches[0]


def main() -> int:
    if not MATLAB_REPORT.is_file():
        raise RuntimeError("MATLAB offline smoke report is missing")
    if PYTHON_REPORT.exists():
        raise RuntimeError("refusing to overwrite existing Python parity report")
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8-sig"))
    lock_sha = sha256(LOCK_PATH)
    setup_sha = setup_manifest_sha(lock)
    report = json.loads(MATLAB_REPORT.read_text(encoding="utf-8-sig"))
    if (report.get("status") != "PASS" or report.get("run_episode_called") is not False
            or report.get("plant_called") is not False or report.get("actuator_called") is not False
            or report.get("training_called") is not False or report.get("test_accessed") is not False
            or report.get("scene_or_raw_read") is not False or report.get("optimizer_steps") != 0):
        raise RuntimeError("MATLAB smoke report does not prove the offline-only scope")
    if (report.get("frozen_inputs_sha256") != lock_sha
            or report.get("setup_manifest_sha256") != setup_sha
            or report.get("round3_runner_sha256") != locked_source_sha(lock, "run_round3_xy_pcf_screen.m")
            or report.get("offline_smoke_source_sha256") != locked_source_sha(lock, "offline_smoke_round3.m")
            or sha256(HERE / "offline_smoke_round3.py") != locked_source_sha(lock, "offline_smoke_round3.py")):
        raise RuntimeError("MATLAB/Python smoke source or lock identity is stale")
    x, y = report["synthetic_inputs"], report["synthetic_outputs"]
    surface = np.asarray(x["surface"], dtype=float).reshape(3)
    eta = np.asarray(x["eta_before"], dtype=float).reshape(3)
    k2 = np.asarray(x["k2"], dtype=float).reshape(3)
    residual = np.asarray(x["residual"], dtype=float).reshape(3)
    phi = np.asarray(x["phi"], dtype=float).reshape(33)
    W = np.asarray(x["W"], dtype=float)
    mask = np.asarray(x["mask"], dtype=float).reshape(3)
    dmax = np.asarray(x["dmax"], dtype=float).reshape(3)
    dt, event_dt, gamma, beta = map(float, (x["plant_dt"], x["event_dt"], x["gamma"], x["beta"]))
    if W.shape != (33, 3) or not np.isfinite(np.concatenate((surface, eta, k2, residual, phi, W.reshape(-1), mask, dmax))).all():
        raise RuntimeError("MATLAB synthetic inputs are nonfinite or have an invalid 33x3 W")
    decay = np.exp(-k2 * dt)
    integral = np.full(3, dt)
    positive = k2 > 0
    integral[positive] = -np.expm1(-k2[positive] * dt) / k2[positive]
    eta_next = decay * eta + integral * residual
    eta_effective = mask * eta
    coord = surface - eta_effective
    limits = np.array([7.0, 8.0, 10.0])
    s_eff = np.clip(coord, -limits, limits)
    raw = W.T @ phi
    applied = beta * np.clip(raw, -dmax, dmax)
    weight_after = np.clip(W + event_dt * (-gamma * beta * np.outer(phi, s_eff) - 0.002 * W), -60.0, 60.0)
    errors = {
        "eta_next": close(y["eta_next"], eta_next, "eta recurrence"),
        "eta_effective": close(y["eta_effective"], eta_effective, "eta mask"),
        "s_coord": close(y["s_coord"], coord, "surface coordinate"),
        "s_eff": close(y["s_eff"], s_eff, "surface clipping"),
        "raw_before_update": close(y["raw_before_update"], raw, "raw output before update"),
        "applied_output": close(y["applied_output"], applied, "clipped/applied output"),
        "weight_after": close(y["weight_after"], weight_after, "projected FEATURE update"),
    }
    if mask.tolist() != [1.0, 1.0, 0.0] or report.get("mask") != [1, 1, 0]:
        raise RuntimeError("candidate eta mask differs from [1,1,0]")
    high = np.clip(surface - eta, -limits, limits)
    off = np.clip(surface, -limits, limits)
    errors["same_record_xy_vs_on"] = close(s_eff[:2], high[:2], "same-record XY equals PCF-on")
    errors["same_record_z_vs_off"] = close(s_eff[2:], off[2:], "same-record Z equals PCF-off")
    if report.get("W0_output_W_sha256") != "88f8c4f2495438c3797655c48bab1bf0c11ac2e27bff1f5f2a7423a8f0a2cf53":
        raise RuntimeError("smoke did not bind the frozen W0 identity")
    if report.get("normalizer_arrays_identity_sha256") != "533aad9a2c66874cfa67f5d268661835e81e58b797cba7d6fc1c12d4013de5f0":
        raise RuntimeError("smoke did not bind the frozen normalizer-array identity")
    if hashlib.sha256(W.astype(np.float64, copy=False).tobytes(order="F")).hexdigest() != report["W0_output_W_sha256"]:
        raise RuntimeError("synthetic FEATURE state is not the frozen W0 matrix")
    output = {
        "schema": "ROUND3_OFFLINE_MATH_SMOKE_PYTHON_V1", "status": "PASS",
        "matlab_report_sha256": sha256(MATLAB_REPORT), "frozen_inputs_sha256": lock_sha,
        "setup_manifest_sha256": setup_sha,
        "round3_runner_sha256": locked_source_sha(lock, "run_round3_xy_pcf_screen.m"),
        "offline_smoke_source_sha256": sha256(HERE / "offline_smoke_round3.py"),
        "mask": [1, 1, 0], "tolerance": TOL, "max_errors": errors,
        "max_error": max(errors.values()), "phi_shape": [33], "W_shape": [33, 3],
        "raw_output_shape": [3], "weight_after_shape": [33, 3],
        "same_record_xy_equals_pcf_on": True, "same_record_z_equals_pcf_off": True,
        "output_precedes_update": True, "plant_or_episode_called": False, "test_accessed": False,
    }
    PYTHON_REPORT.write_text(json.dumps(output, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ROUND3_OFFLINE_PYTHON_SMOKE_FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
