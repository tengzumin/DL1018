#!/usr/bin/env python3
"""Locked TRAIN/VAL diagnostic Ridge fitting; no neural-network training or Plant run."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

for key in ("OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "OMP_NUM_THREADS", "BLIS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[key] = "1"

import h5py
import numpy as np


BASE = Path("reports/attitude_redesign_20261024")
OUT = BASE / "offline_input_probe_v1"
LOCK = OUT / "INPUT_SCENE_LOCK_v1.json"
PARAMETERS = OUT / "PARAMETERS_v1.json"
CLARIFICATIONS = BASE / "OFFLINE_PROBE_CLARIFICATIONS_v1.json"
RESULT = OUT / "OFFLINE_INPUT_PROBE_RESULT_v1.json"
ARCHIVE = OUT / "OFFLINE_INPUT_PROBE_ARRAYS_v1.npz"
RIDGE, FLOOR, STRIDE = 1e-3, 1e-6, 5
PHASE = {0: "STATIC", 1: "PRE", 2: "EXTEND", 3: "HOLD", 4: "RETRACT", 5: "RECOVERY"}
FEATURES = [
    "omega_B_x_rad_s", "omega_B_y_rad_s", "omega_B_z_rad_s",
    "alpha_BS_x_rad_s2", "alpha_BS_y_rad_s2", "alpha_BS_z_rad_s2", "requested_thrust_over_mass_m_s2",
    "command_1_dimensionless", "command_2_dimensionless", "command_3_dimensionless", "command_4_dimensionless",
    "command_integral_1_s", "command_integral_2_s", "command_integral_3_s", "command_integral_4_s",
    "previous_interval_torque_x_Nm", "previous_interval_torque_y_Nm", "previous_interval_torque_z_Nm",
]
GROUPS = {
    "G0_B7": list(range(7)),
    "G1_B7_u4": list(range(7)) + list(range(7, 11)),
    "G2_B7_z4": list(range(7)) + list(range(11, 15)),
    "G3_B7_z4_u4": list(range(7)) + list(range(11, 15)) + list(range(7, 11)),
    "G4_B7_z4_u4_a3": list(range(7)) + list(range(11, 15)) + list(range(7, 11)) + list(range(15, 18)),
}
MODELS = ["ZERO", *GROUPS]


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def need(ok: bool, why: str) -> None:
    if not ok:
        raise RuntimeError(why)


def path_in(root: Path, rel: str | Path) -> Path:
    p = (root / rel).resolve()
    need(p.is_relative_to(root.resolve()), f"path escapes repo: {rel}")
    return p


def verify(path: Path, expected: str, label: str) -> None:
    need(path.is_file(), f"missing {label}: {path}")
    need(sha(path).lower() == expected.lower(), f"SHA256 mismatch: {label} {path}")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def file_roles(scene: dict) -> dict:
    result = {f["role"]: f for f in scene["files"]}
    need(set(result) == {"B_h5", "raw_run", "run_start"}, f"bad input roles: {scene['scene_id']}")
    return result


def locked_inputs(root: Path) -> tuple[dict, dict, dict, dict]:
    lock_path = path_in(root, LOCK)
    lock = read_json(lock_path)
    need(lock.get("schema") == "OFFLINE_ATTITUDE_INPUT_PROBE_SCENE_LOCK_V1", "bad scene-lock schema")
    scenes = lock["scenes"]
    need(len(scenes) == 96 and sum(s["split"] == "TRAIN" for s in scenes) == 48
         and sum(s["split"] == "VAL" for s in scenes) == 48, "scene lock must contain 48 TRAIN + 48 VAL")
    need(len({s["scene_id"] for s in scenes}) == 96 and all(s["split"] in ("TRAIN", "VAL") for s in scenes),
         "duplicate IDs or forbidden split in lock")
    input_hashes, source_hashes = [], []
    for scene in scenes:
        for item in scene["files"]:
            need(f"/{scene['split'].lower()}/" in item["path"].lower() and "/test/" not in item["path"].lower(),
                 f"input path does not match locked split: {item['path']}")
            p = path_in(root, item["path"])
            need(p.stat().st_size == item["size_bytes"], f"size mismatch: {item['path']}")
            verify(p, item["sha256"], item["role"])
            input_hashes.append({"path": item["path"], "sha256": item["sha256"], "size_bytes": item["size_bytes"]})
    need(len(input_hashes) == 288, "expected 288 locked input files")
    for item in lock["feature_reconstruction_sources"]:
        verify(path_in(root, item["path"]), item["sha256"], "reconstruction source")
        source_hashes.append(item)

    clar_path, params_path = path_in(root, CLARIFICATIONS), path_in(root, PARAMETERS)
    clar, params = read_json(clar_path), read_json(params_path)
    need(clar.get("schema") == "OFFLINE_ATTITUDE_PROBE_CLARIFICATIONS_V1", "bad clarification schema")
    need(params.get("schema") == "OFFLINE_INPUT_PROBE_NOMINAL_PARAMETERS_V1", "bad PARAMETERS schema")
    need(params.get("scene_lock_sha256", "").lower() == sha(lock_path).lower(), "PARAMETERS not bound to scene lock")
    param_sources = params.get("source_files", [])
    need(param_sources, "PARAMETERS source list is empty")
    for item in param_sources:
        verify(path_in(root, item["path"]), item["sha256"], "PARAMETERS source")
    for key in ("root_physical_configuration_sha256", "root_nonzero_pair_result_sha256", "matlab_reconstruction_receipt_sha256"):
        need(len(params.get(key, "")) == 64, f"missing provenance SHA: {key}")
    audit = {
        "scene_lock_sha256": sha(lock_path), "inputs_verified": input_hashes,
        "source_hashes_verified": source_hashes, "clarifications_sha256": sha(clar_path),
        "parameters_sha256": sha(params_path), "parameters_sources": params.get("source_files", []),
    }
    return lock, params, clar, audit


def parameter_rows(lock: dict, params: dict) -> dict:
    rows = {r["scene_id"]: r for r in params.get("scenes", [])}
    by_lock = {r["scene_id"]: r for r in lock["scenes"]}
    need(len(rows) == 96 and set(rows) == set(by_lock), "PARAMETERS scene IDs differ from lock")
    gc = params.get("global_consistency", {})
    need(gc.get("unique_J0_count") == 1 and gc.get("unique_mass_count") == 1, "J0/mass are not globally unique")
    need(params.get("construction", {}).get("controller_mode") == "fixed", "J0 must use fixed controller parameters")
    signature = None
    j0_ref = jdot_ref = mass_ref = None
    for sid, p in rows.items():
        s, files = by_lock[sid], file_roles(by_lock[sid])
        need(p.get("split") == s["split"], f"parameter split mismatch: {sid}")
        need(Path(p.get("run_start_path", "")).as_posix() == Path(files["run_start"]["path"]).as_posix(), f"run_start path mismatch: {sid}")
        need(p.get("run_start_sha256", "").lower() == files["run_start"]["sha256"].lower(), f"run_start SHA mismatch: {sid}")
        need(p.get("morphology_mode") and p.get("inertia_derivative_mode"), f"missing cfg modes: {sid}")
        config_sha = p.get("physical_configuration_sha256", "")
        need(len(config_sha) == 64, f"missing physical-configuration SHA: {sid}")
        sig = (config_sha, p["morphology_mode"], p["inertia_derivative_mode"])
        signature = sig if signature is None else signature
        need(sig == signature, f"physical cfg signature/modes differ: {sid}")
        j0, jdot = np.asarray(p["J0_kg_m2"], float), np.asarray(p["Jdot0_for_bs_kg_m2_s"], float)
        mass = float(p["mass_kg"])
        need(j0.shape == (3, 3) and jdot.shape == (3, 3) and np.isfinite(j0).all()
             and np.isfinite(jdot).all() and np.isfinite(mass) and mass > 0, f"invalid J0/Jdot/mass: {sid}")
        need(np.allclose(j0, j0.T, rtol=0, atol=1e-12) and np.linalg.eigvalsh(j0).min() > 0, f"invalid J0: {sid}")
        if j0_ref is None:
            j0_ref, jdot_ref, mass_ref = j0, jdot, mass
        else:
            need(np.allclose(j0, j0_ref, rtol=1e-12, atol=1e-12)
                 and np.allclose(jdot, jdot_ref, rtol=1e-12, atol=1e-12)
                 and np.isclose(mass, mass_ref, rtol=1e-12, atol=1e-12), f"nominal parameters differ: {sid}")
    return rows


def text_attr(v) -> str:
    if isinstance(v, bytes):
        return v.decode("utf-8", errors="replace")
    return str(v.item() if isinstance(v, np.ndarray) and v.shape == () else v)


def extract_scene(root: Path, scene: dict, p: dict) -> dict:
    files = file_roles(scene)
    with h5py.File(path_in(root, files["B_h5"]["path"]), "r") as h, h5py.File(path_in(root, files["raw_run"]["path"]), "r") as r:
        need(text_attr(h.attrs.get("scene_id", "")) == scene["scene_id"] and text_attr(h.attrs.get("split", "")) == scene["split"],
             f"H5 identity mismatch: {scene['scene_id']}")
        need(text_attr(h.attrs.get("model_id", "")) == "B" and text_attr(h.attrs.get("contract_version", "")) == "DL1018_V311_R2E_PAPER_FINAL",
             f"H5 model/contract mismatch: {scene['scene_id']}")
        pi = np.asarray(h["plant_index"], float).reshape(-1)
        t_event, phase = np.asarray(h["event_time_s"], float).reshape(-1), np.asarray(h["phase_code"], int).reshape(-1)
        y, xh5 = np.asarray(h["target_raw"], float), np.asarray(h["x"], float)
        need(pi.size == 1999 and y.shape == (1999, 3) and xh5.shape == (1999, 29), f"H5 shape mismatch: {scene['scene_id']}")
        need(np.isfinite(y).all() and np.isfinite(xh5).all() and np.isin(phase, list(PHASE)).all(), f"bad H5 values: {scene['scene_id']}")
        need(np.equal(pi, np.floor(pi)).all(), f"noninteger plant_index: {scene['scene_id']}")
        idx = pi.astype(np.int64) - 1
        need(idx.min() >= 10 and idx.max() < 20000 and np.all(np.diff(idx) == 10), f"bad event index sequence: {scene['scene_id']}")
        phase_map = text_attr(h.attrs.get("phase_code_mapping", ""))
        need("0=STATIC" in phase_map and "5=RECOVERY" in phase_map, f"phase-code mapping mismatch: {scene['scene_id']}")

        time_raw = np.asarray(r["log/time"], float).reshape(-1)
        time_scene = np.asarray(r["scene/time"], float).reshape(-1)
        dt = np.diff(time_raw)
        need(time_raw.shape == (20001,) and time_scene.shape == (20001,) and np.allclose(time_raw, time_scene, atol=1e-12, rtol=0)
             and np.allclose(dt, .001, atol=1e-12, rtol=0), f"raw time/step mismatch: {scene['scene_id']}")
        need(np.allclose(t_event, time_raw[idx], atol=1e-12, rtol=0), f"event time/index mismatch: {scene['scene_id']}")
        attitude_flag = np.asarray(r["log/attitude_event_flag"], np.uint8).reshape(-1).astype(bool)
        rbf_flag = np.asarray(r["log/rbf_update_flag"], np.uint8).reshape(-1).astype(bool)
        canonical_match = np.array_equal(np.flatnonzero(attitude_flag), idx)
        rbf_match = np.array_equal(np.flatnonzero(rbf_flag), idx)
        need(canonical_match, f"H5 plant_index does not match canonical attitude_event_flag: {scene['scene_id']}")

        state = np.asarray(r["log/state"], float)
        tau_nom = np.asarray(r["log/attitude_bs_nominal_torque_Nm"], float)
        request = np.asarray(r["log/requested_generalized"], float)
        command = np.asarray(r["scene/arms/command"], float)
        need(state.shape == (12, 20001) and tau_nom.shape == (3, 20000) and request.shape == (4, 20000)
             and command.shape == (4, 20001), f"raw array shape mismatch: {scene['scene_id']}")
        need(all(np.isfinite(a).all() for a in (state, tau_nom, request, command)), f"nonfinite raw input: {scene['scene_id']}")
        need(np.isin(command, (-1., 0., 1.)).all(), f"invalid normalized command: {scene['scene_id']}")

        omega = state[9:12, idx].T
        tau = tau_nom[:, idx].T
        j0 = np.asarray(p["J0_kg_m2"], float)
        jdot = np.asarray(p["Jdot0_for_bs_kg_m2_s"], float)
        alpha = np.linalg.solve(j0, (tau - np.cross(omega, omega @ j0.T) - omega @ jdot.T).T).T
        thrust_mass = request[0, idx] / float(p["mass_kg"])
        # z[k] integrates only completed intervals; each command is the left endpoint value.
        z = np.cumsum(command[:, :-1] * dt[None, :], axis=1)
        z = np.column_stack((np.zeros(4), z))[:, idx].T
        u = command[:, idx].T
        # For event k, use request rows k-10,...,k-1 in MATLAB indexing; exclude current row k.
        a3 = np.stack([np.average(request[1:4, i-10:i].T, axis=0, weights=dt[i-10:i]) for i in idx])
        errors = {
            "omega": float(np.max(np.abs(omega - xh5[:, 6:9]))),
            "alpha_BS": float(np.max(np.abs(alpha - xh5[:, 21:24]))),
            "thrust_mass": float(np.max(np.abs(thrust_mass - xh5[:, 24]))),
        }
        need(errors["omega"] <= 1e-10 and errors["alpha_BS"] <= 1e-7 and errors["thrust_mass"] <= 1e-8,
             f"raw-derived B7 disagrees with H5 crosscheck: {scene['scene_id']} {errors}")
        x18 = np.column_stack((omega, alpha, thrust_mass, u, z, a3))
        need(x18.shape == (1999, 18) and np.isfinite(x18).all(), f"bad feature matrix: {scene['scene_id']}")
        return {"scene": scene, "idx": idx, "event_time": t_event, "phase": phase, "x": x18, "y": y,
                "crosscheck": errors, "rbf_mask_matches": bool(rbf_match)}


def phi(x: np.ndarray) -> np.ndarray:
    i, j = np.triu_indices(x.shape[1])
    return np.column_stack((np.ones(len(x)), x, x[:, i] * x[:, j]))


def fit(x: np.ndarray, y: np.ndarray) -> dict:
    mu, sd = x.mean(axis=0), np.maximum(x.std(axis=0), FLOOR)
    xn = (x - mu) / sd
    p = phi(xn)
    penalty = np.ones(p.shape[1]); penalty[0] = 0
    w = np.linalg.solve(p.T @ p / len(p) + RIDGE * np.diag(penalty), p.T @ y / len(p))
    return {"mean": mu, "std": sd, "w": w}


def predict(m: dict, x: np.ndarray, scale: np.ndarray) -> np.ndarray:
    return phi((x - m["mean"]) / m["std"]) @ m["w"] * scale


def metrics(pred: np.ndarray, y: np.ndarray, scale: np.ndarray) -> dict:
    e = pred - y
    return {
        "axis_rmse_rad_s2": np.sqrt(np.mean(e**2, axis=0)).tolist(),
        "physical_vector_rmse_rad_s2": float(np.sqrt(np.mean(np.sum(e**2, axis=1)))),
        "normalized_vector_rmse": float(np.sqrt(np.mean(np.sum((e / scale)**2, axis=1)))),
        "peak_vector_error_rad_s2": float(np.max(np.linalg.norm(e, axis=1))),
        "output_amplitude_rms_rad_s2": float(np.sqrt(np.mean(np.sum(pred**2, axis=1)))),
        "target_amplitude_rms_rad_s2": float(np.sqrt(np.mean(np.sum(y**2, axis=1)))),
        "output_peak_rad_s2": float(np.max(np.linalg.norm(pred, axis=1))),
    }


def metric_tables(data: list[dict], pred: dict, scale: np.ndarray) -> tuple[list, list, list]:
    per_scene = []
    metric_names = ("axis_rmse_rad_s2", "physical_vector_rmse_rad_s2", "normalized_vector_rmse",
                    "peak_vector_error_rad_s2", "output_amplitude_rms_rad_s2",
                    "target_amplitude_rms_rad_s2", "output_peak_rad_s2")
    for i, d in enumerate(data):
        groups = [("ALL", None, np.ones(len(d["y"]), bool))]
        groups += [(PHASE[c], c, d["phase"] == c) for c in range(6)]
        s = d["scene"]
        for model in MODELS:
            for phase_name, code, mask in groups:
                values = metrics(pred[model][i][mask], d["y"][mask], scale) if mask.any() else dict.fromkeys(metric_names)
                per_scene.append({"model": model, "split": s["split"], "scene_id": s["scene_id"],
                                  "task": s["task"], "condition": s["condition"], "wind_group": s["wind_group"],
                                  "phase": phase_name, "phase_code": code, "scene_count": int(mask.any()),
                                  "event_count": int(mask.sum()), **values})

    group_defs = [
        ("split", ("split",), False), ("task", ("split", "task"), False),
        ("condition", ("split", "condition"), False), ("wind_group", ("split", "wind_group"), False),
        ("phase_code", ("split", "phase_code"), True), ("task+phase", ("split", "task", "phase_code"), True),
        ("condition+phase", ("split", "condition", "phase_code"), True),
        ("wind+phase", ("split", "wind_group", "phase_code"), True),
    ]
    names = metric_names
    aggregated = []
    for model in MODELS:
        source = [r for r in per_scene if r["model"] == model]
        for label, keys, phase_group in group_defs:
            buckets = defaultdict(list)
            for r in source:
                if r["event_count"] == 0 or (r["phase"] != "ALL") != phase_group:
                    continue
                buckets[tuple(r[k] for k in keys)].append(r)
            for key, members in buckets.items():
                row = {k: v for k, v in zip(keys, key)}
                for name in names:
                    a = np.asarray([m[name] for m in members], float)
                    row[name] = np.mean(a, axis=0).tolist() if a.ndim == 2 else float(a.mean())
                row.update({"model": model, "group_by": label, "scene_count": len(members),
                            "event_count": sum(m["event_count"] for m in members)})
                aggregated.append(row)
    focus = [r for r in per_scene if (r["condition"] == "C00" and r["phase"] == "ALL")
             or r["phase"] in ("PRE", "RECOVERY")]
    return per_scene, aggregated, focus


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fit", action="store_true", required=True, help="explicitly run the five fixed closed-form fits")
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[3]
    started = time.perf_counter()
    result_path, archive_path = path_in(root, RESULT), path_in(root, ARCHIVE)
    tmp_result, tmp_archive = result_path.with_name(result_path.name + ".tmp"), archive_path.with_name(archive_path.name + ".tmp.npz")
    need(args.fit, "pass --fit explicitly")
    need(not result_path.exists() and not archive_path.exists() and not tmp_result.exists() and not tmp_archive.exists(),
         "refusing to overwrite existing outputs")
    lock, params, clar, audit = locked_inputs(root)
    p_rows = parameter_rows(lock, params)
    data = [extract_scene(root, s, p_rows[s["scene_id"]]) for s in lock["scenes"]]

    train = [d for d in data if d["scene"]["split"] == "TRAIN"]
    x_fit = np.concatenate([d["x"][::STRIDE] for d in train])
    y_fit = np.concatenate([d["y"][::STRIDE] for d in train])
    scale = np.maximum(np.sqrt(np.mean(y_fit**2, axis=0)), FLOOR)
    yn_fit = y_fit / scale
    models = {name: fit(x_fit[:, cols], yn_fit) for name, cols in GROUPS.items()}
    need(len(models) == 5, "expected exactly five Ridge fits")

    predictions = {"ZERO": [np.zeros_like(d["y"]) for d in data]}
    for name, cols in GROUPS.items():
        predictions[name] = [predict(models[name], d["x"][:, cols], scale) for d in data]
    per_scene, grouped, focus = metric_tables(data, predictions, scale)

    offsets = np.cumsum([0] + [len(d["y"]) for d in data])
    arrays = {
        "scene_ids": np.asarray([d["scene"]["scene_id"] for d in data], "U32"),
        "scene_offsets": offsets,
        "scene_split": np.asarray([d["scene"]["split"] for d in data], "U5"),
        "event_scene_id": np.concatenate([np.repeat(d["scene"]["scene_id"], len(d["y"])) for d in data]).astype("U32"),
        "event_split": np.concatenate([np.repeat(d["scene"]["split"], len(d["y"])) for d in data]).astype("U5"),
        "event_task": np.concatenate([np.repeat(d["scene"]["task"], len(d["y"])) for d in data]).astype("U2"),
        "event_condition": np.concatenate([np.repeat(d["scene"]["condition"], len(d["y"])) for d in data]).astype("U3"),
        "event_wind_group": np.concatenate([np.repeat(d["scene"]["wind_group"], len(d["y"])) for d in data]).astype("U3"),
        "plant_index_matlab_1based": np.concatenate([d["idx"] + 1 for d in data]),
        "event_time_s": np.concatenate([d["event_time"] for d in data]),
        "phase_code": np.concatenate([d["phase"] for d in data]).astype(np.uint8),
        "features_raw_B7_u4_z4_a3": np.concatenate([d["x"] for d in data]),
        "target_raw_rad_s2": np.concatenate([d["y"] for d in data]),
        "target_normalized_train_rms": np.concatenate([d["y"] / scale for d in data]),
        "target_scale_train_fit_rms_rad_s2": scale,
        "fit_sample_mask": np.concatenate([np.arange(len(d["y"])) % STRIDE == 0 if d["scene"]["split"] == "TRAIN"
                                            else np.zeros(len(d["y"]), bool) for d in data]),
    }
    for name, cols in GROUPS.items():
        m = models[name]
        arrays[f"normalized_features_{name}"] = np.concatenate([(d["x"][:, cols] - m["mean"]) / m["std"] for d in data])
        arrays[f"coefficients_{name}"] = m["w"]
        arrays[f"feature_mean_{name}"] = m["mean"]
        arrays[f"feature_std_{name}"] = m["std"]
        arrays[f"prediction_{name}_rad_s2"] = np.concatenate(predictions[name])
    arrays["prediction_ZERO_rad_s2"] = np.concatenate(predictions["ZERO"])

    np.savez_compressed(tmp_archive, **arrays)
    result = {
        "schema": "OFFLINE_ATTITUDE_INPUT_PROBE_RESULT_V1", "status": "PASS_OFFLINE_INFORMATION_PROBE",
        "scope": "locked TRAIN/VAL only; historical behavior-conditioned offline target prediction, not causal or closed-loop evidence",
        "command_argv": [sys.executable, *sys.argv], "script_sha256": sha(Path(__file__)), "input_audit": audit,
        "parameter_provenance": {k: params.get(k) for k in ("root_physical_configuration_sha256", "root_nonzero_pair_result_sha256",
                                                                "matlab_reconstruction_receipt_sha256", "construction", "global_consistency")},
        "scene_count": {"TRAIN": 48, "VAL": 48}, "fit_samples": {"stride": STRIDE, "train_rows": len(y_fit)},
        "estimator": {"models": GROUPS, "zero_output_reference": True, "closed_form_fit_calls": 5, "optimizer_steps": 0,
                      "ridge_lambda": RIDGE, "feature_std_floor": FLOOR, "target_axis_rms_floor": FLOOR,
                      "design": "intercept + standardized linear terms + all i<=j products",
                      "solve": "(Phi.T@Phi/N + lambda*diag(0,1,...)) W = Phi.T@Y_norm/N"},
        "feature_names_B7_u4_z4_a3": FEATURES,
        "semantics": {"u4": "current dimensionless normalized signed-rate command {-1,0,1}",
                      "z4": "past-only command integral in seconds; initial zero; no true/estimated rho read",
                      "a3": "weighted mean torque from the previous complete 10 x 1 ms requests; current event excluded",
                      "alpha_BS": "J0^-1*(tau_nominal - omega cross (J0*omega) - Jdot0_for_bs*omega), rad/s^2",
                      "target": "H5 target_raw instantaneous body angular-acceleration residual, rad/s^2"},
        "train_target_axis_rms_rad_s2": scale.tolist(), "scene_metrics": per_scene,
        "group_metrics_scene_equal": grouped, "C00_PRE_RECOVERY_output_and_target_amplitude": focus,
        "raw_H5_crosscheck_max_abs": [{"scene_id": d["scene"]["scene_id"], **d["crosscheck"],
                                        "rbf_update_flag_also_matches": d["rbf_mask_matches"]} for d in data],
        "outputs": {"array_archive": ARCHIVE.name, "array_archive_sha256": sha(tmp_archive), "array_archive_bytes": tmp_archive.stat().st_size},
        "metric_definitions": clar["metrics"], "elapsed_seconds": time.perf_counter() - started,
        "actual_process_exit_code_note": "Record PowerShell's actual process exit code in the execution receipt.",
        "provenance_limit": lock["provenance_limit"],
    }
    with tmp_result.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")
    os.replace(tmp_archive, archive_path)
    os.replace(tmp_result, result_path)
    print(f"PASS: five closed-form fits; wrote {result_path.name} and {archive_path.name}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        raise
