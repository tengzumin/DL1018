from __future__ import annotations

import json
from pathlib import Path

import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "experiments" / "position_causal_repair_v1"


def matrix(g: h5py.Group, name: str, rows: int, cols: int) -> np.ndarray:
    a = np.asarray(g[name], dtype=np.float64)
    if a.shape == (cols, rows):
        a = a.T
    if a.shape != (rows, cols):
        raise ValueError((name, a.shape, rows, cols))
    return a


def main() -> None:
    manifest = OUT / "manifests/BRIDGE6.csv"
    import pandas as pd

    bridge = pd.read_csv(manifest)
    p = bridge.loc[(bridge.scene_id == "DL1018_TRAIN_T1_C02_W08")
                   & (bridge.role == "P_INIT_STUDENT")].iloc[0]
    raw = ROOT / p.raw_path
    event = ROOT / f"data/events/position/train/{p.scene_id}/P_INIT_STUDENT.h5"
    with h5py.File(raw, "r") as f:
        g = f["log"]
        valid = np.asarray(g["stage1_position_event_inference_valid"], dtype=bool).reshape(-1)
        ticks = np.flatnonzero(valid)
        phi = matrix(g, "stage1_position_event_phi_33", 20000, 33)[ticks]
        raw_pred = matrix(g, "stage1_position_event_raw_acceleration_mps2", 20000, 3)[ticks]
        applied_pred = matrix(g, "stage1_position_event_applied_acceleration_mps2", 20000, 3)[ticks]
        beta = np.asarray(g["stage1_position_event_beta"], dtype=np.float64).reshape(-1)[ticks]
        dt = np.asarray(g["stage1_position_effective_update_dt_s"], dtype=np.float64).reshape(-1)[ticks]
        surface = matrix(g, "stage1_position_pcf_event_s_original_mps", 20000, 3)[ticks]
        eta = matrix(g, "stage1_position_pcf_event_eta_before_mps", 20000, 3)[ticks]
        w_before = np.asarray(g["stage1_position_event_weight_before_33x3"], dtype=np.float64).transpose(2, 1, 0)
        w_after = np.asarray(g["stage1_position_event_weight_after_33x3"], dtype=np.float64).transpose(2, 1, 0)
        projected = np.asarray(g["stage1_position_event_projection"], dtype=np.float64).reshape(-1)[ticks].astype(bool)
    with h5py.File(event, "r") as f:
        event_plant = np.asarray(f["plant_index"], dtype=np.int64).reshape(-1) - 1
        event_ready = np.asarray(f["ready"], dtype=bool).reshape(-1)
        event_surface = np.asarray(f["x14"], dtype=np.float64)[:, 3:6]
    assert len(ticks) == 1968 and w_before.shape == w_after.shape == (33, 3, 1968)
    assert np.array_equal(event_plant[event_ready], ticks)
    assert np.max(np.abs(event_surface[event_ready] - surface)) <= 1e-12

    w = w_before[:, :, 0].copy()
    max_pre = max_raw = max_applied = max_post = max_chain = 0.0
    projections = int(projected.sum())
    explicit_before = []
    explicit_after = []
    for j in range(len(ticks)):
        explicit_before.append(w.copy())
        max_pre = max(max_pre, float(np.max(np.abs(w - w_before[:, :, j]))))
        r = w.T @ phi[j]
        a = beta[j] * np.clip(r, -3.0, 3.0)
        max_raw = max(max_raw, float(np.max(np.abs(r - raw_pred[j]))))
        max_applied = max(max_applied, float(np.max(np.abs(a - applied_pred[j]))))
        s_eff = np.clip(surface[j] - eta[j], [-7.0, -8.0, -10.0], [7.0, 8.0, 10.0])
        nxt = np.clip(w + dt[j] * (-beta[j] * np.outer(phi[j], s_eff) - 0.002 * w), -60.0, 60.0)
        max_post = max(max_post, float(np.max(np.abs(nxt - w_after[:, :, j]))))
        if j:
            max_chain = max(max_chain, float(np.max(np.abs(w_before[:, :, j] - w_after[:, :, j - 1]))))
        explicit_after.append(nxt.copy())
        w = nxt

    lam = 1.0 - .002 * .01
    weights_fast = np.empty_like(w_before)
    accum = np.zeros((33, 3), dtype=np.float64)
    for j in range(len(ticks)):
        if j:
            accum += (lam ** (-j)) * beta[j - 1] * np.outer(phi[j - 1],
                    np.clip(surface[j - 1] - eta[j - 1], [-7.0, -8.0, -10.0], [7.0, 8.0, 10.0]))
        weights_fast[:, :, j] = (lam ** j) * (w_before[:, :, 0] - .01 * accum)
    max_fast_before = float(np.max(np.abs(weights_fast - np.stack(explicit_before, axis=2))))
    max_abs_weight = float(np.max(np.abs(np.concatenate([np.stack(explicit_before, axis=2).ravel(),
                                                        np.stack(explicit_after, axis=2).ravel()]))))
    result = {
        "status": "PASS" if max(max_pre, max_raw, max_applied, max_post, max_chain, max_fast_before) <= 1e-10 else "FAIL",
        "scene_id": str(p.scene_id), "run_id": str(p.run_id), "events": len(ticks), "event_h5_surface_max_abs": float(np.max(np.abs(event_surface[event_ready] - surface))),
        "max_weight_before_error": max_pre, "max_raw_prediction_error_mps2": max_raw,
        "max_applied_prediction_error_mps2": max_applied, "max_weight_after_error": max_post,
        "max_weight_chain_error": max_chain, "max_fast_formula_error": max_fast_before,
        "projection_events": projections, "max_abs_weight": max_abs_weight,
        "dt_unique_s": np.unique(dt).tolist(), "new_plant_starts": 0,
        "method": "production phi/surface/eta/beta/dt; output-before-update; PCF eta subtraction; 0.002 leakage; [-60,60] projection; separate algebraic recurrence checked against explicit loop"
    }
    (OUT / "reports/D4_RECURRENCE_PARITY.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
