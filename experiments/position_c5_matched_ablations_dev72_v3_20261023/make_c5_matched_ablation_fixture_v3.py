"""Write fixed synthetic expectations for the two isolated C5 helper ablations."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
KERNEL = ROOT / "reports/delayed_prediction_proposal_20261023/construction/delayed_prediction_kernel.py"
KERNEL_SHA256 = "6615a9d9a6096777429065a598d631ca844f46cf4131032e7ff0a3d3067d9ebc"
TOL = 2e-12
MASK = np.array([1.0, 1.0, 0.0])
LIMITS = np.array([7.0, 8.0, 10.0])


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


def expected(out: dict) -> dict:
    keys = ("raw", "applied", "beta", "has_previous", "previous_raw",
            "previous_residual", "prediction_gradient", "preprojection_candidate", "W_next")
    return {key: plain(out[key]) for key in keys}


def ablated_out(base: dict, W: np.ndarray, mode: str) -> dict:
    result = dict(base)
    zero = np.zeros((33, 3), dtype=np.float64)
    result["prediction_gradient"] = zero
    if mode == "C5_FREEZE_TRAINED_W0":
        candidate = W.copy()
    elif mode == "C5_NO_DELAYED_PREDICTION":
        # Baseline candidate contains -rho*gradient; remove only that term.
        candidate = base["preprojection_candidate"] + (0.01 / 1.0) * base["prediction_gradient"]
    else:
        raise ValueError(mode)
    result["preprojection_candidate"] = candidate
    result["W_next"] = np.clip(candidate, -60.0, 60.0)
    return result


def make_events(kernel, mode: str, Winit: np.ndarray, phi320: np.ndarray,
                phi330: np.ndarray, s320: np.ndarray, s330: np.ndarray,
                target: np.ndarray) -> list[dict]:
    base320 = kernel.delayed_prediction_step(Winit, phi320, s320, 320, 0.320)
    first = ablated_out(base320, Winit, mode)
    W330 = first["W_next"]
    base330 = kernel.delayed_prediction_step(
        W330, phi330, s330, 330, 0.330, phi_prev=phi320,
        y_prev=target, previous_index=320, previous_time_s=0.320)
    second = ablated_out(base330, W330, mode)
    return [
        {"n": 320, "time_s": 0.320, "W_input": Winit, "phi": phi320, "s_eff": s320,
         "has_previous_input": False, "phi_prev": [], "y_prev": [], "previous_index": 0,
         "previous_time_s": 0.0, "expected": expected(first),
         "baseline_expected": expected(base320)},
        {"n": 330, "time_s": 0.330, "W_input": W330, "phi": phi330, "s_eff": s330,
         "has_previous_input": True, "phi_prev": phi320, "y_prev": target,
         "previous_index": 320, "previous_time_s": 0.320,
         "expected": expected(second), "baseline_expected": expected(base330)},
    ]


def fixture_for(kernel, mode: str, helper: Path) -> dict:
    i = np.arange(33, dtype=np.float64)
    W0 = np.column_stack((0.006*np.sin(0.37*(i+1)),
                          0.005*np.cos(0.29*(i+1)),
                          0.004*np.sin(0.17*(i+3))))
    phi320 = np.sin(0.23*(i+1)); phi320 /= np.linalg.norm(phi320)
    phi330 = np.cos(0.19*(i+2)); phi330 /= np.linalg.norm(phi330)
    surfaces = [np.array([8.4, -9.0, 11.0]), np.array([2.2, -2.7, 3.4])]
    etas = [np.array([0.7, -0.5, 1.2]), np.array([0.5, -0.45, 0.8])]
    s320 = np.clip(surfaces[0] - MASK*etas[0], -LIMITS, LIMITS)
    s330 = np.clip(surfaces[1] - MASK*etas[1], -LIMITS, LIMITS)
    rows = np.arange(11, dtype=np.float64)
    a_req = np.column_stack((0.21 + 0.004*rows, -0.16 + 0.003*rows, 0.07 - 0.002*rows))
    r_f = np.column_stack((0.023 + 0.0003*rows, -0.031 + 0.0002*rows, 0.017 - 0.0001*rows))
    a_f = a_req - r_f
    # Deliberate current-row sentinel: the target at n=330 uses only rows [320,330).
    a_req[10] = [800.0, -900.0, 1000.0]
    a_f[10] = [-1100.0, 1200.0, -1300.0]
    r_f[10] = a_req[10] - a_f[10]
    refs = a_req.copy(); refs[:, MASK == 1] = a_f[:, MASK == 1]
    integral = np.zeros(3)
    for q in range(10):
        integral = integral + refs[q] * 0.001
    v320 = np.array([0.12, -0.24, 0.36]); v330 = np.array([0.134, -0.251, 0.373])
    target = ((v330-v320)-integral)/0.01
    wrong_integral = np.zeros(3)
    for q in range(11):
        wrong_integral = wrong_integral + refs[q] * 0.001
    wrong_target = ((v330-v320)-wrong_integral)/0.01
    events = make_events(kernel, mode, W0, phi320, phi330, s320, s330, target)

    # Projection/output-limit case: W starts inside the box; the first update crosses both faces.
    Wedge = np.zeros((33, 3)); Wedge[0, :] = [59.9, -59.9, 0.4]
    phiedge = np.zeros(33); phiedge[0] = 1.0
    sedge = np.array([-7.0, 7.0, 0.0])
    edge = make_events(kernel, mode, Wedge, phiedge, phiedge, sedge, -sedge, np.array([0.1, -0.2, 0.3]))

    # Independent algebra checks for the single intervention.
    for event in events + edge:
        actual = event["expected"]; base = event["baseline_expected"]
        assert np.max(np.abs(np.asarray(actual["raw"])-np.asarray(base["raw"]))) == 0
        assert np.max(np.abs(np.asarray(actual["applied"])-np.asarray(base["applied"]))) == 0
        assert np.max(np.abs(np.asarray(actual["prediction_gradient"]))) == 0
        if mode == "C5_FREEZE_TRAINED_W0":
            assert np.array_equal(actual["preprojection_candidate"], event["W_input"])
            assert np.array_equal(actual["W_next"], event["W_input"])
        else:
            expected_candidate = (np.asarray(base["preprojection_candidate"])
                                  + 0.01*np.asarray(base["prediction_gradient"]))
            assert np.max(np.abs(np.asarray(actual["preprojection_candidate"])-expected_candidate)) == 0
    assert np.max(np.abs(target-wrong_target)) > 1e-3
    assert np.max(np.abs(events[1]["expected"]["previous_residual"])) >= 0
    assert np.max(np.abs(edge[0]["baseline_expected"]["applied"])) == edge[0]["baseline_expected"]["beta"]*3.0
    assert np.max(np.abs(edge[0]["baseline_expected"]["W_next"])) == 60.0
    return {
        "schema": "C5_MATCHED_ABLATION_CROSSLANG_FIXTURE_V1",
        "mode": mode, "mask": MASK, "tolerance_abs": TOL,
        "plant_dt_s": 0.001, "event_period_s": 0.01,
        "W0": W0, "phi_320": phi320, "phi_330": phi330,
        "surface_320": surfaces[0], "surface_330": surfaces[1],
        "eta_320": etas[0], "eta_330": etas[1],
        "a_req_rows_n320_to_n330_N11_by_3": a_req,
        "a_f_rows_n320_to_n330_N11_by_3": a_f,
        "r_f_rows_n320_to_n330_N11_by_3": r_f,
        "reference_rows_n320_to_n330_N11_by_3": refs,
        "reference_integral_320_330_mps": integral,
        "target_330_mps2": target,
        "sentinel_target_if_row330_included_mps2": wrong_target,
        "v_320_mps": v320, "v_330_mps": v330,
        "events": events, "boundary_events": edge,
        "python_kernel_path": str(KERNEL.resolve()), "python_kernel_sha256": KERNEL_SHA256,
        "matlab_helper_path": str(helper.resolve()), "matlab_helper_sha256": sha256(helper),
        "provenance": "deterministic synthetic arrays only; no Plant/raw MAT/model checkpoint/training/TEST",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("C5_FREEZE_TRAINED_W0", "C5_NO_DELAYED_PREDICTION"), required=True)
    args = parser.parse_args()
    folder = HERE / args.mode
    helper = folder / "delayed_prediction_step_candidate.m"
    output = folder / "C5_ABLATION_CROSSLANG_FIXTURE_v3.json"
    if output.exists():
        raise FileExistsError(f"refusing to overwrite {output}")
    spec = importlib.util.spec_from_file_location("delayed_prediction_kernel", KERNEL)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import frozen Python kernel {KERNEL}")
    kernel = importlib.util.module_from_spec(spec); spec.loader.exec_module(kernel)
    if sha256(KERNEL) != KERNEL_SHA256:
        raise RuntimeError("frozen Python delayed-prediction kernel SHA changed")
    fixture = fixture_for(kernel, args.mode, helper)
    output.write_text(json.dumps(plain(fixture), indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps({"status": "FIXTURE_GENERATED_NO_PLANT", "mode": args.mode,
                      "path": str(output.resolve()), "fixture_sha256": sha256(output),
                      "helper_sha256": sha256(helper), "kernel_sha256": sha256(KERNEL),
                      "events": 4, "first_event_without_history": True,
                      "completed_interval_rows": 10, "current_row_sentinel": 330}, indent=2))


if __name__ == "__main__":
    main()
