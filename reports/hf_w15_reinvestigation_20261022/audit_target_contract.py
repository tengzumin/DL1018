"""Read-only full72 comparison of physical and PCF-coordinate residual targets.

Run with PowerShell 7: python -B reports/hf_w15_reinvestigation_20261022/audit_target_contract.py
No simulation, training, model change, TEST read, or source-data write.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import h5py
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
INDEX = ROOT / "reports/paper14_v2/phase1/mechanism_components_by_scene.csv"
INDEX_SHA = "f1ba9ff2335ea75e992436f753fb75ff1678271f33bf6d2fe706db4b45572e3b"
ARCHIVE = ROOT.parent / "REFERENCE_FIX_FULL72_20261021_022342_313"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def low_band_rms(error: np.ndarray) -> float:
    """Descriptive DFT energy in 0--1 Hz, including DC, at 100 Hz.

    Finite-window DFT assumes periodic extension; this is not a causal filter,
    transfer function, or a measurement of deployed phase delay.
    """
    n = len(error)
    spectrum = np.fft.rfft(error)
    weights = np.full(len(spectrum), 2.0)
    weights[0] = 1.0
    if n % 2 == 0:
        weights[-1] = 1.0
    take = np.fft.rfftfreq(n, d=0.01) <= 1.0 + 1e-12
    return float(np.sqrt(np.sum(weights[take] * np.abs(spectrum[take]) ** 2)) / n)


def main() -> None:
    if sha(INDEX) != INDEX_SHA:
        raise RuntimeError("Frozen full72 input index changed")
    index = pd.read_csv(INDEX, keep_default_na=False)
    if len(index) != 72 or index.scene_id.nunique() != 72 or index.raw_sha256_before.nunique() != 72:
        raise RuntimeError("Expected exactly 72 unique frozen records")
    if set(index.split) != {"DEV", "VAL"}:
        raise RuntimeError("Only DEV/VAL records are permitted")
    rows, identities, filter_rows, configurations = [], [], [], []
    maxima = {k: 0.0 for k in ("a_req_vs_nominal_minus_applied", "rf_vs_req_minus_filtered",
                               "target_identity", "before_vs_logged_applied", "legacy_target_rms",
                               "beta_ramp", "filter_clip_replay")}
    for n, record in enumerate(index.to_dict("records"), 1):
        path = Path(record["raw_path"]).resolve()
        if not path.is_relative_to(ARCHIVE.resolve()):
            raise RuntimeError(f"Path outside frozen archive: {path}")
        stat_before = (path.stat().st_size, path.stat().st_mtime_ns)
        hash_before = sha(path)
        if hash_before != record["raw_sha256_before"]:
            raise RuntimeError(f"Input raw SHA mismatch: {record['scene_id']}")
        with h5py.File(path, "r") as f:
            def get(name):
                return np.asarray(f[name], dtype=np.float64)

            valid = np.flatnonzero(get("log/stage1_position_event_inference_valid").reshape(-1) > 0)
            times = get("log/transition_time").reshape(-1)[valid]
            if len(valid) != 1968 or np.max(np.abs(np.diff(times) - 0.01)) > 1e-10:
                raise RuntimeError("Unexpected inference event times")
            state = get("log/state")[:, valid]
            roll, pitch, yaw = state[6:9]
            z_body = np.vstack((np.cos(yaw) * np.sin(pitch) * np.cos(roll) + np.sin(yaw) * np.sin(roll),
                                np.sin(yaw) * np.sin(pitch) * np.cos(roll) - np.cos(yaw) * np.sin(roll),
                                np.cos(pitch) * np.cos(roll)))
            mass = float(get("cfg/plant/mass").item())
            gravity = float(get("cfg/plant/g").item())
            thrust = get("log/realized_generalized")[0, valid]
            actual = z_body * thrust / mass + get("log/wind_force_I")[:, valid] / mass
            actual[2] -= gravity
            nominal = get("log/position_nominal_acceleration_mps2")[:, valid]
            applied = get("log/position_compensation_applied_acceleration_mps2")[:, valid]
            requested = get("log/stage1_position_pcf_a_req_mps2")[:, valid]
            filtered = get("log/stage1_position_pcf_a_f_mps2")[:, valid]
            rf = get("log/stage1_position_pcf_r_f_mps2")[:, valid]
            physical_y = actual - (nominal - applied)
            coordinate_y = physical_y + rf
            beta = get("log/stage1_position_event_beta").reshape(-1)[valid]
            beta_rise = float(get("cfg/rbf/position/beta_rise_time").item())
            if beta_rise <= 0 or not np.isfinite(beta_rise):
                raise RuntimeError("Invalid beta rise time")
            phi = get("log/stage1_position_event_phi_33")[:, valid]
            w0 = get("log/stage1_position_search_initial_weight").reshape(3, 33)
            wb = get("log/stage1_position_event_weight_before_33x3")
            wa = get("log/stage1_position_event_weight_after_33x3")
            if wb.shape != (1968, 3, 33) or wa.shape != wb.shape:
                raise RuntimeError("Unexpected weight history shape")
            dmax = get("cfg/rbf/position/dmax").reshape(3, 1)
            prior = beta * np.clip(w0 @ phi, -dmax, dmax)
            before = beta * np.clip(np.einsum("eij,je->ie", wb, phi), -dmax, dmax)
            after = beta * np.clip(np.einsum("eij,je->ie", wa, phi), -dmax, dmax)
            checks = {
                "a_req_vs_nominal_minus_applied": np.max(np.abs(requested - (nominal - applied))),
                "rf_vs_req_minus_filtered": np.max(np.abs(rf - (requested - filtered))),
                "target_identity": np.max(np.abs(coordinate_y - (actual - filtered))),
                "before_vs_logged_applied": np.max(np.abs(before - applied)),
                "legacy_target_rms": abs(np.sqrt(np.mean((beta * np.clip(physical_y, -dmax, dmax)) ** 2))
                                          - float(record["target_signal_rms_mps2"])),
                "beta_ramp": np.max(np.abs(beta - np.clip(times / beta_rise, 0, 1))),
            }
            for key, value in checks.items():
                maxima[key] = max(maxima[key], float(value))
            if max(checks.values()) > 1e-9:
                raise RuntimeError(f"Equation/timestamp check failed {record['scene_id']}: {checks}")
            all_times = get("log/transition_time").reshape(-1)
            filter_requested = get("log/command_filter_acceleration_request_unclamped_rads2")
            filter_applied = get("log/command_filter_acceleration_applied_rads2")
            if (filter_requested.shape != (3, len(all_times)) or filter_applied.shape != filter_requested.shape
                    or not np.isfinite(filter_requested).all() or not np.isfinite(filter_applied).all()):
                raise RuntimeError("Invalid command-filter history")
            limits = get("cfg/control/command_filter/acceleration_limit").reshape(3, 1)
            if np.isnan(limits).any() or (limits <= 0).any():
                raise RuntimeError("Invalid effective command-filter limits")
            clip_error = float(np.max(np.abs(filter_applied - np.clip(filter_requested, -limits, limits))))
            maxima["filter_clip_replay"] = max(maxima["filter_clip_replay"], clip_error)
            if clip_error > 1e-9:
                raise RuntimeError("Command-filter clipping replay mismatch")
            configurations.append({"scene_id": record["scene_id"], "beta_rise_time_s": beta_rise,
                                   "filter_acceleration_limit_rads2": [float(x) if np.isfinite(x) else "Inf" for x in limits.ravel()]})
            for phase, take in (("all_0_20", all_times >= 0), ("early_0_5", all_times < 5),
                                ("late_5_20", all_times >= 5)):
                for axis, label in enumerate(("roll", "pitch", "yaw")):
                    r, a = filter_requested[axis, take], filter_applied[axis, take]
                    filter_rows.append({"scene_id": record["scene_id"], "band": record["band"],
                                        "task": record["task"], "phase": phase, "axis": label,
                                        "clip_fraction": float(np.mean(np.abs(r - a) > 1e-9)),
                                        "request_rms_rads2": float(np.sqrt(np.mean(r * r))),
                                        "applied_rms_rads2": float(np.sqrt(np.mean(a * a))),
                                        "max_abs_request_rads2": float(np.max(np.abs(r)))})
            phases = {"all_valid_0p32_20": np.ones(len(times), dtype=bool),
                      "beta1_1p8_20": times >= 1.8 - 1e-12, "late_5_20": times >= 5 - 1e-12}
            for phase, take in phases.items():
                for target_name, target in (("physical_Y", physical_y), ("pcf_coordinate_Y_plus_rf", coordinate_y)):
                    for axis, label in enumerate("xyz"):
                        t, p, b, a, r = (x[axis, take] for x in (target, prior, before, after, rf))
                        rmse = lambda x: float(np.sqrt(np.mean(x * x)))
                        details = {}
                        for name, prediction in (("prior", p), ("before", b), ("after_same_state", a)):
                            error = prediction - t
                            details[f"{name}_error_mean_mps2"] = float(np.mean(error))
                            details[f"{name}_error_abs_mean_mps2"] = abs(float(np.mean(error)))
                            details[f"{name}_error_low_0_1Hz_rms_mps2"] = low_band_rms(error)
                        rows.append({"scene_id": record["scene_id"], "split": record["split"],
                                     "task": record["task"], "band": record["band"],
                                     "phase": phase, "target": target_name, "axis": label, "events": int(take.sum()),
                                     "target_rms_mps2": rmse(t), "rf_rms_mps2": rmse(r),
                                     "prior_rmse_mps2": rmse(p - t), "before_rmse_mps2": rmse(b - t),
                                     "after_same_state_rmse_mps2": rmse(a - t),
                                     "one_step_mse_gain": float(np.mean((b - t) ** 2 - (a - t) ** 2)),
                                     "one_step_worse_fraction": float(np.mean((a - t) ** 2 > (b - t) ** 2 + 1e-12)),
                                     **details})
        stat_after = (path.stat().st_size, path.stat().st_mtime_ns)
        hash_after = sha(path)
        if hash_after != hash_before or stat_before != stat_after:
            raise RuntimeError("Source raw changed during read-only audit")
        identities.append({"scene_id": record["scene_id"], "raw_sha256": hash_before, "unchanged": True})
        if n % 12 == 0:
            print(f"Read-only target audit {n}/72", flush=True)
    result = pd.DataFrame(rows)
    result.to_csv(OUT / "target_contract_by_scene.csv", index=False)
    numeric = [c for c in result if c.endswith(("mps2", "gain", "fraction"))]
    grouped = result.groupby(["band", "phase", "target", "axis"], sort=True)
    summary = grouped[numeric].mean().reset_index()
    summary["scene_count"] = grouped.scene_id.nunique().to_numpy()
    summary.to_csv(OUT / "target_contract_groups.csv", index=False)
    filter_result = pd.DataFrame(filter_rows)
    filter_result.to_csv(OUT / "filter_limits_by_scene.csv", index=False)
    filter_group = filter_result.groupby(["band", "phase", "axis"], sort=True)
    filter_summary = filter_group[["clip_fraction", "request_rms_rads2", "applied_rms_rads2", "max_abs_request_rads2"]].mean().reset_index()
    filter_summary["scene_count"] = filter_group.scene_id.nunique().to_numpy()
    filter_summary.to_csv(OUT / "filter_limits_groups.csv", index=False)
    metadata = {"status": "PASS_READONLY_TARGET_CONTRACT_AUDIT", "source_index_sha256": INDEX_SHA,
                "script_sha256": sha(Path(__file__)), "scenes": 72, "all_raw_sha_and_stat_unchanged": True,
                "identity_check_maxima_mps2": maxima, "raw_identities": identities,
                "effective_configurations": configurations,
                "physical_target": "Y=a_actual-(a_nominal-u_applied)",
                "coordinate_target": "Y+r_f=a_actual-a_filtered, since r_f=a_requested-a_filtered",
                "scope": "Both targets and before/after outputs evaluated on the same recorded state and phi. These are residual-fit diagnostics, not new closed-loop performance or intervention effects.",
                "low_frequency_definition": "100 Hz finite-window DFT energy in 0--1 Hz including DC; periodic-extension leakage applies; no causal phase estimate.",
                "plant_calls": 0, "optimizer_steps": 0, "test_accessed": False}
    metadata["output_sha256"] = {name: sha(OUT / name) for name in (
        "target_contract_by_scene.csv", "target_contract_groups.csv", "filter_limits_by_scene.csv", "filter_limits_groups.csv")}
    (OUT / "target_contract_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: metadata[k] for k in ("status", "scenes", "identity_check_maxima_mps2", "plant_calls", "optimizer_steps", "test_accessed")}), flush=True)


if __name__ == "__main__":
    main()
