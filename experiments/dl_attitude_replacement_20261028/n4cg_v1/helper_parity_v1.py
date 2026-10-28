#!/usr/bin/env python3
"""Freeze and check Python/MATLAB parity for the causal-gated static N4 helper."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from scipy import __version__ as scipy_version
from scipy.io import loadmat, savemat
from scipy.signal import butter, sosfilt

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
AUDIT_DIR = ROOT / "experiments/dl_attitude_replacement_20261028/causal_n4_gate_train24_audit_v1"
AUDIT_SCRIPT = AUDIT_DIR / "audit_causal_n4_gate_train24_v1.py"
AUDIT_JSON = AUDIT_DIR / "CAUSAL_N4_GATE_TRAIN24_AUDIT_v1.json"
PROTOCOL = HERE / "HELPER_PROTOCOL_v1.json"
LOCK = HERE / "HELPER_SOURCE_LOCK_v1.json"
FIXTURE = HERE / "HELPER_PARITY_FIXTURE_v1.mat"
MATLAB_RESULT = HERE / "MATLAB_PARITY_RESULT_v1.json"
REPORT = HERE / "HELPER_PARITY_v1.md"
MAX_ERROR = 2e-10
DT = 0.01
FS = 100.0
BP_SOS = butter(2, [2.0, 5.0], btype="bandpass", fs=FS, output="sos")
LP_SOS = butter(2, 2.0, btype="lowpass", fs=FS, output="sos")
FILES = [
    "helper_parity_v1.py",
    "position_compensation_static_n4_init.m",
    "position_compensation_static_n4_step.m",
    "position_compensation_n4_causal_gate_init.m",
    "position_compensation_n4_causal_gate_step.m",
    "run_helper_parity_v1.m",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_once(path: Path, text: str) -> None:
    if path.exists():
        raise RuntimeError(f"Refusing to overwrite {path}")
    path.write_text(text, encoding="utf-8")


def n4_coefficients() -> tuple[np.ndarray, np.ndarray]:
    b = np.zeros((4, 3), dtype=np.float64)
    a = np.zeros((4, 3), dtype=np.float64)
    for i, f in enumerate((2.2, 3.2, 3.7, 4.8)):
        w0 = 2.0 * np.pi * f / FS
        alpha = np.sin(w0) / 8.0
        scale = 1.0 + alpha
        b[i] = np.array([1.0, -2.0 * np.cos(w0), 1.0]) / scale
        a[i] = [1.0, -2.0 * np.cos(w0) / scale, (1.0 - alpha) / scale]
    return b, a


def n4_init() -> dict:
    b, a = n4_coefficients()
    return {"b": b, "a": a, "sections": np.zeros((3, 4, 4)),
            "held": np.zeros(3), "initialized": False}


def n4_step(s: dict, x: np.ndarray) -> np.ndarray:
    if not s["initialized"]:
        if np.max(np.abs(x)) > 1e-12:
            s["sections"] = np.broadcast_to(x[:, None, None], (3, 4, 4)).copy()
            s["held"] = x.copy()
            s["initialized"] = True
        else:
            s["held"] = x.copy()
        return x.copy()
    y = x.copy()
    for j in range(4):
        z = s["sections"][:, j, :]
        b = s["b"][j]
        a = s["a"][j]
        yn = b[0] * y + b[1] * z[:, 0] + b[2] * z[:, 1] - a[1] * z[:, 2] - a[2] * z[:, 3]
        s["sections"][:, j, :] = np.column_stack((y, z[:, 0], yn, z[:, 2]))
        y = yn
    s["held"] = np.clip(y, -3.0, 3.0)
    return y


def sos_step(sos: np.ndarray, state: np.ndarray, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    y = x.copy()
    for section, row in enumerate(sos):
        b0, b1, b2, a0, a1, a2 = row
        if a0 != 1.0:
            raise RuntimeError("Expected normalized SciPy SOS coefficients")
        z1 = state[:, section, 0].copy()
        z2 = state[:, section, 1].copy()
        yn = b0 * y + z1
        state[:, section, 0] = b1 * y - a1 * yn + z2
        state[:, section, 1] = b2 * y - a2 * yn
        y = yn
    return state, y


def run_gate(action: np.ndarray, times: np.ndarray) -> dict[str, np.ndarray]:
    action = np.asarray(action, dtype=np.float64)
    times = np.asarray(times, dtype=np.float64).reshape(-1)
    if action.shape != (len(times), 3) or not np.isfinite(action).all():
        raise ValueError("Expected finite event action with shape N-by-3")
    if len(times) < 2 or not np.allclose(np.diff(times), DT, atol=2e-12, rtol=0.0):
        raise ValueError("Events must be uniformly spaced at 100 Hz")
    state_bp = np.zeros((3, BP_SOS.shape[0], 2))
    state_lp = np.zeros((3, LP_SOS.shape[0], 2))
    e_bp = e_lp = gate = 0.0
    n4 = n4_init()
    out = np.zeros_like(action)
    n4_out = np.zeros_like(action)
    bp_hist = np.zeros_like(action)
    lp_hist = np.zeros_like(action)
    diag = np.zeros((len(times), 5), dtype=np.float64)  # Ebp, Elp, ratio, target, g
    rho_e = np.exp(-DT / 1.0)
    rho_g = np.exp(-DT / 0.3)
    for i, (u, t) in enumerate(zip(action, times)):
        state_bp, bp = sos_step(BP_SOS, state_bp, u)
        state_lp, lp = sos_step(LP_SOS, state_lp, u)
        bp_hist[i] = bp
        lp_hist[i] = lp
        e_bp = rho_e * e_bp + (1.0 - rho_e) * float(bp @ bp)
        e_lp = rho_e * e_lp + (1.0 - rho_e) * float(lp @ lp)
        ratio = e_bp / (e_bp + e_lp + 1e-8)
        target_raw = float(np.clip((ratio - 0.35) / 0.30, 0.0, 1.0))
        n4_u = n4_step(n4, u)
        if t < 2.0:
            target = 0.0
            gate = 0.0
        else:
            target = target_raw
            gate = rho_g * gate + (1.0 - rho_g) * target
        out[i] = np.clip(u + gate * (n4_u - u), -3.0, 3.0)
        n4_out[i] = n4_u
        diag[i] = (e_bp, e_lp, ratio, target, gate)
    return {"out": out, "n4": n4_out, "diag": diag, "bp": bp_hist, "lp": lp_hist}


def synthetic_fixture() -> tuple[np.ndarray, np.ndarray, dict[str, np.ndarray]]:
    n = 700
    times = (np.arange(n, dtype=np.float64) + 1.0) * DT
    u = np.column_stack((
        0.08 * np.sin(2 * np.pi * 0.22 * times) + 0.22 * np.sin(2 * np.pi * 2.2 * times) + 0.11 * np.sin(2 * np.pi * 4.8 * times),
        0.07 * np.cos(2 * np.pi * 0.31 * times) + 0.19 * np.sin(2 * np.pi * 3.2 * times) + 0.06 * np.sin(2 * np.pi * 2.0 * times),
        0.05 * np.sin(2 * np.pi * 0.17 * times) + 0.13 * np.sin(2 * np.pi * 4.1 * times),
    ))
    u[:31] = 0.0
    return u, times, run_gate(u, times)


def protocol_doc(audit: dict) -> dict:
    return {
        "schema": "CAUSAL_N4_GATE_HELPER_PROTOCOL_V1",
        "status": "PREDECLARED_HELPER_ONLY_NO_PLANT",
        "study": "fixed causal gate blended with static N4; helper parity only",
        "scope": {"Plant_called": False, "full_runner_called": False,
                  "TEST_read": False, "VAL_read": False, "inertia_reconstruction": False,
                  "wind_or_W_used_by_helper": False, "additional_position_GRU": False},
        "event_contract": "100-Hz event updates only; event time from transition_time; 1999 events; all 31 pre-ready all-NaN action rows become zero and still update every filter/N4 state; non-event outputs are ZOH.",
        "signal_filters": {
            "designer": f"scipy {scipy_version} scipy.signal.butter",
            "sample_rate_hz": FS,
            "bandpass": {"order": 2, "cutoff_hz": [2.0, 5.0], "sos": BP_SOS.tolist()},
            "lowpass": {"order": 2, "cutoff_hz": 2.0, "sos": LP_SOS.tolist()},
            "initial_state": "zero SOS DF-II-transposed state, each raw; update once at each position event",
        },
        "gate": {
            "energy": "E[k]=exp(-dt/tau)*E[k-1]+(1-exp(-dt/tau))*sum(filtered[k,:]^2), E[0]=0",
            "energy_tau_s": 1.0, "ratio": "Ebp/(Ebp+Elp+1e-8)",
            "target": "clip((ratio-0.35)/0.30,0,1)", "gate_tau_s": 0.3,
            "startup": "for event time t<2.0s force exported gtarget=0 and g state=0; first t>=2.0s sample starts tau=0.3 EMA from zero",
        },
        "blend": {
            "N4_centers_hz": [2.2, 3.2, 3.7, 4.8], "N4_Q_each": 4.0,
            "N4_state": "same static N4 helper as n4T3C09_v1; update every event from startup; first nonzero action initializes/bypasses as before",
            "output": "clip(u_C5 + g*(u_N4_raw-u_C5), -3, 3) per axis at every event",
            "between_events": "zero-order hold output and all state",
        },
        "parity": {"fixture": "deterministic 700-event 3-axis signal; compares full output, raw N4, and Ebp/Elp/ratio/gtarget/g",
                   "max_abs_tolerance": MAX_ERROR},
        "linked_train24_audit": {"json": str(AUDIT_JSON), "json_sha256": sha256(AUDIT_JSON),
                                 "script": str(AUDIT_SCRIPT), "script_sha256": sha256(AUDIT_SCRIPT),
                                 "status": audit.get("status"),
                                 "binding_sha256": audit.get("source", {}).get("bindings_sha256")},
        "interpretation": "helper-level numerical parity does not establish full-runner boundary parity or closed-loop efficacy; TRAIN24 gate audit shows underactivation on multiple high-group scenes.",
    }


def freeze() -> None:
    for p in (PROTOCOL, LOCK, FIXTURE, MATLAB_RESULT, REPORT):
        if p.exists():
            raise RuntimeError(f"Refusing to overwrite existing artifact: {p}")
    audit = read_json(AUDIT_JSON)
    if audit.get("status") != "PASS_TRAIN_ONLY_READONLY_GATE_AUDIT_NO_MODEL_TRAINED_NO_PLANT":
        raise RuntimeError("Linked TRAIN24 gate audit is not the expected read-only result")
    if audit.get("source", {}).get("scene_count") != 24 or audit.get("source", {}).get("parent_raw_hash_verified_count") != 24:
        raise RuntimeError("Linked TRAIN24 audit does not bind all 24 parent raws")
    protocol = protocol_doc(audit)
    u, times, expected = synthetic_fixture()
    bp_reference = sosfilt(BP_SOS, u, axis=0)
    lp_reference = sosfilt(LP_SOS, u, axis=0)
    if (not np.isfinite(expected["out"]).all() or np.max(np.abs(expected["diag"][:, 0])) == 0 or
            np.max(np.abs(expected["bp"] - bp_reference)) > 2e-12 or
            np.max(np.abs(expected["lp"] - lp_reference)) > 2e-12):
        raise RuntimeError("Synthetic fixture failed the SciPy SOS recurrence check")
    savemat(FIXTURE, {
        "u": u.T, "time_s": times.reshape(1, -1), "expected_out": expected["out"].T,
        "expected_n4_raw": expected["n4"].T, "expected_diag": expected["diag"].T,
        "bp_sos_reference": BP_SOS, "lp_sos_reference": LP_SOS,
        "bp_filter_reference": bp_reference.T, "lp_filter_reference": lp_reference.T,
    }, do_compression=True, oned_as="row")
    write_once(PROTOCOL, json.dumps(protocol, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    files = [{"path": str(HERE / name), "sha256": sha256(HERE / name)} for name in FILES]
    lock = {"schema": "CAUSAL_N4_GATE_HELPER_SOURCE_LOCK_V1", "protocol_sha256": sha256(PROTOCOL),
            "fixture_path": str(FIXTURE), "fixture_sha256": sha256(FIXTURE), "files": files,
            "linked_train24_audit_json_sha256": sha256(AUDIT_JSON),
            "linked_train24_audit_script_sha256": sha256(AUDIT_SCRIPT)}
    write_once(LOCK, json.dumps(lock, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"status": "FROZEN_HELPER_AND_PARITY_FIXTURE", "protocol_sha256": sha256(PROTOCOL),
                      "source_lock_sha256": sha256(LOCK), "fixture_sha256": sha256(FIXTURE),
                      "plant_called": False}, indent=2))


def check() -> None:
    lock = read_json(LOCK)
    if sha256(PROTOCOL) != lock.get("protocol_sha256") or sha256(FIXTURE) != lock.get("fixture_sha256"):
        raise RuntimeError("Frozen protocol or parity fixture hash changed")
    if sha256(AUDIT_JSON) != lock.get("linked_train24_audit_json_sha256") or sha256(AUDIT_SCRIPT) != lock.get("linked_train24_audit_script_sha256"):
        raise RuntimeError("Linked TRAIN24 audit artifact changed")
    for item in lock["files"]:
        path = Path(item["path"])
        if not path.is_file() or sha256(path) != item["sha256"]:
            raise RuntimeError(f"Locked helper source changed: {path}")
    result = read_json(MATLAB_RESULT)
    if result.get("status") != "PASS_MATLAB_HELPER_PARITY" or result.get("max_abs_error") > MAX_ERROR:
        raise RuntimeError("MATLAB helper parity is missing or failed")
    fixture = loadmat(FIXTURE)
    u = np.asarray(fixture["u"], dtype=np.float64).T
    times = np.asarray(fixture["time_s"], dtype=np.float64).reshape(-1)
    expected = run_gate(u, times)
    for key, matlab_key in (("out", "expected_out"), ("n4", "expected_n4_raw"), ("diag", "expected_diag")):
        recorded = np.asarray(fixture[matlab_key], dtype=np.float64).T
        err = float(np.max(np.abs(expected[key] - recorded)))
        if err > 5e-13:
            raise RuntimeError(f"Python parity fixture self-check failed for {key}: {err}")
    report = [
        "# Causal N4 gate helper parity v1", "", "## Result", "",
        f"- Status: `{result['status']}`; MATLAB R2025b pure-helper run; no Plant/full runner.",
        f"- Maximum absolute error across `uout`, raw N4 output, `Ebp/Elp/ratio/gtarget/g`: `{result['max_abs_error']:.3e}` (limit `{MAX_ERROR:.1e}`).",
        f"- Python SOS recurrence matches SciPy `sosfilt`; fixture size: {u.shape[0]} events × 3 axes.",
        f"- Frozen protocol SHA-256: `{lock['protocol_sha256']}`; source-lock SHA-256: `{sha256(LOCK)}`.",
        "", "## Fixed behavior", "",
        "100-Hz causal SOS filters use zero initial states. Each of the 1,999 C5 position events updates filters, energy EMAs, the N4 state, and (after 2 s) the gate; 31 all-NaN warmup actions are zero inputs. Between events the output/state are held. The gate does not read wind/W/future values or use an extra position GRU.",
        "", "## TRAIN24 gate limitation", "",
        "The linked frozen TRAIN24 audit reports gate mean zero on 4 of 10 W09–W14 high-group scenes (T1_C10_W09, T1_C11_W12, T3_C09_W09, T3_C13_W12). Across that group, median `g>0.1` occupancy is 28.75% and median `g>=0.5` occupancy is 0.64%; this fixed estimator can underactivate on multiple high-group scenes. This is a diagnostic limitation, not a reason to tune thresholds here.",
        "", "## Scope", "",
        "Helper parity only. No full-runner insertion-time check, Plant call, TEST/VAL read, inertia reconstruction, parameter sweep, or change to prior N4/N2 outcome labels.", "",
    ]
    write_once(REPORT, "\n".join(report))
    print(json.dumps({"status": "PASS_HELPER_PARITY_AND_LOCK_CHECK", "max_abs_error": result["max_abs_error"],
                      "report": str(REPORT), "plant_called": False}, indent=2))


def main() -> None:
    if len(sys.argv) == 2 and sys.argv[1] == "--freeze":
        freeze()
    elif len(sys.argv) == 2 and sys.argv[1] == "--check":
        check()
    else:
        raise SystemExit("usage: helper_parity_v1.py --freeze | --check")


if __name__ == "__main__":
    main()
