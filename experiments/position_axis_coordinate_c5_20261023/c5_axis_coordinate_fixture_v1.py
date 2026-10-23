"""Generate deterministic, synthetic C5 axis-mask expectations from the frozen Python kernel."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT = HERE / "C5_CROSSLANG_FIXTURE_v1.json"
KERNEL = ROOT / "reports/delayed_prediction_proposal_20261023/construction/delayed_prediction_kernel.py"
HELPER = HERE / "delayed_prediction_step_candidate.m"
TOL = 2e-12


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def plain(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    if isinstance(value, dict):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value


def expected_out(out: dict) -> dict:
    # Fixed-shape fields make MATLAB jsondecode's struct contract unambiguous.
    return {key: plain(out[key]) for key in (
        "raw", "applied", "beta", "has_previous", "prediction_gradient",
        "preprojection_candidate", "W_next")}


def main() -> None:
    if OUT.exists():
        raise FileExistsError(f"refusing to overwrite {OUT}")
    spec = importlib.util.spec_from_file_location("delayed_prediction_kernel", KERNEL)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {KERNEL}")
    kernel = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(kernel)

    i = np.arange(33, dtype=np.float64)
    W0 = np.column_stack((0.006*np.sin(0.37*(i+1)),
                          0.005*np.cos(0.29*(i+1)),
                          0.004*np.sin(0.17*(i+3))))
    phi320 = np.sin(0.23*(i+1)); phi320 /= np.linalg.norm(phi320)
    phi330 = np.cos(0.19*(i+2)); phi330 /= np.linalg.norm(phi330)
    surfaces = [np.array([8.4, -9.0, 11.0]), np.array([2.2, -2.7, 3.4])]
    etas = [np.array([0.7, -0.5, 1.2]), np.array([0.5, -0.45, 0.8])]
    rows = np.arange(11, dtype=np.float64)
    a_req = np.column_stack((0.21 + 0.004*rows,
                             -0.16 + 0.003*rows,
                             0.07 - 0.002*rows))
    r_f = np.column_stack((0.023 + 0.0003*rows,
                           -0.031 + 0.0002*rows,
                           0.017 - 0.0001*rows))
    a_f = a_req - r_f
    # The current n=330 row is a deliberately large sentinel and is excluded from [320,330).
    a_req[10] = np.array([800.0, -900.0, 1000.0])
    a_f[10] = np.array([-1100.0, 1200.0, -1300.0])
    r_f[10] = a_req[10] - a_f[10]
    v320 = np.array([0.12, -0.24, 0.36])
    v330 = np.array([0.134, -0.251, 0.373])
    limits = np.array([7.0, 8.0, 10.0])
    mask_cases = [
        ("M_I", np.array([1.0, 1.0, 1.0])),
        ("M_zero", np.array([0.0, 0.0, 0.0])),
        ("M_110", np.array([1.0, 1.0, 0.0])),
    ]
    cases = []
    for case_id, mask in mask_cases:
        s_eff_320 = np.clip(surfaces[0] - mask*etas[0], -limits, limits)
        first = kernel.delayed_prediction_step(W0, phi320, s_eff_320, 320, 0.320)
        references = np.array(a_req, copy=True)
        references[:, mask == 1] = a_f[:, mask == 1]
        integral = np.zeros(3, dtype=np.float64)
        for q in range(10):
            integral = integral + references[q] * 0.001
        target = ((v330-v320)-integral)/0.01
        wrong_integral = np.zeros(3, dtype=np.float64)
        for q in range(11):
            wrong_integral = wrong_integral + references[q] * 0.001
        sentinel_target = ((v330-v320)-wrong_integral)/0.01
        s_eff_330 = np.clip(surfaces[1] - mask*etas[1], -limits, limits)
        second = kernel.delayed_prediction_step(
            first["W_next"], phi330, s_eff_330, 330, 0.330,
            phi_prev=phi320, y_prev=target, previous_index=320, previous_time_s=0.320)
        cases.append({
            "case_id": case_id,
            "mask": mask,
            "prediction_reference_rows_n320_to_n330_N11_by_3": references,
            "reference_integral_320_330_mps": integral,
            "target_330_mps2": target,
            "sentinel_target_if_row330_included_mps2": sentinel_target,
            "events": [
                {"n": 320, "time_s": 0.320, "surface": surfaces[0], "eta_before": etas[0],
                 "s_eff": s_eff_320, "has_previous_input": False, "previous_index": 0,
                 "previous_time_s": 0.0, "W_input": W0, "expected": expected_out(first)},
                {"n": 330, "time_s": 0.330, "surface": surfaces[1], "eta_before": etas[1],
                 "s_eff": s_eff_330, "has_previous_input": True, "previous_index": 320,
                 "previous_time_s": 0.320, "W_input": first["W_next"], "expected": expected_out(second)},
            ],
        })

    assert len(cases) == 3
    assert np.max(np.abs(cases[0]["target_330_mps2"]-cases[1]["target_330_mps2"])) > 1e-3
    assert np.max(np.abs(cases[2]["prediction_reference_rows_n320_to_n330_N11_by_3"][:, :2]-a_f[:, :2])) == 0
    assert np.max(np.abs(cases[2]["prediction_reference_rows_n320_to_n330_N11_by_3"][:, 2]-a_req[:, 2])) == 0
    assert all(np.linalg.norm(c["target_330_mps2"]-c["sentinel_target_if_row330_included_mps2"], np.inf) > 1e-3
               for c in cases)
    fixture = {
        "schema": "C5_AXIS_COORDINATE_CROSSLANG_FIXTURE_V1",
        "tolerance_abs": TOL,
        "plant_dt_s": 0.001,
        "event_period_s": 0.01,
        "W0": W0,
        "phi_320": phi320,
        "phi_330": phi330,
        "a_req_rows_n320_to_n330_N11_by_3": a_req,
        "a_f_rows_n320_to_n330_N11_by_3": a_f,
        "r_f_rows_n320_to_n330_N11_by_3": r_f,
        "v_320_mps": v320,
        "v_330_mps": v330,
        "cases": cases,
        "python_kernel_path": str(KERNEL.resolve()),
        "python_kernel_sha256": sha256(KERNEL),
        "matlab_helper_sha256": sha256(HELPER),
        "provenance": "synthetic arrays only; no Plant, raw MAT, model checkpoint, training, or TEST",
    }
    OUT.write_text(json.dumps(plain(fixture), indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps({"status": "FIXTURE_GENERATED_NO_PLANT", "path": str(OUT.resolve()),
                      "sha256": sha256(OUT), "kernel_sha256": sha256(KERNEL),
                      "helper_sha256": sha256(HELPER), "mask_cases": 3,
                      "events": 6, "integrated_rows_per_target": 10,
                      "current_row_sentinel": "n=330"}, indent=2))


if __name__ == "__main__":
    main()
