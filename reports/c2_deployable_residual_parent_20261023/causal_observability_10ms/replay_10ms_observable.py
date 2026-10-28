"""Offline, fixed-rule causal-availability check for original C1 ON1 logs.

This does not fit a model or launch a simulation.  At event k it uses only
logged velocity at k and k-10, plus the logged filter acceleration over the
preceding ten 1 ms transitions.  Physical acceleration is used only as an
offline oracle for validation.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import time
from pathlib import Path

import h5py
import numpy as np
from scipy.io import loadmat


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
C1_DIR = ROOT / "experiments/position_prior_calibration_c1_20261022_v9"
LOCK_PATH = C1_DIR / "C1_SOURCE_LOCK_v2.json"
MANIFEST_PATH = C1_DIR / "reports/C1_SCREEN_PER_RUN.csv"
LOCK_SHA = "02668f6268944715e65e6d2cffa52b395417506132212b00e7d273d88df164e5"
SCENE_SHA = "176ed5770824a241b5c41b9c786f2110b730a7783414152875181985d497a32e"
DT = 0.001
WINDOW = 10
EVENT_STRIDE = 10
LATE_START_S = 5.0
END_S = 20.0
EXPECTED_EVENTS = np.arange(320, 19991, EVENT_STRIDE, dtype=np.int64)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stat_signature(path: Path) -> tuple[int, int]:
    st = path.stat()
    return st.st_size, st.st_mtime_ns


def body_z(euler: np.ndarray) -> np.ndarray:
    roll, pitch, yaw = euler.T
    return np.column_stack((
        np.cos(yaw) * np.sin(pitch) * np.cos(roll) + np.sin(yaw) * np.sin(roll),
        np.sin(yaw) * np.sin(pitch) * np.cos(roll) - np.cos(yaw) * np.sin(roll),
        np.cos(pitch) * np.cos(roll),
    ))


def read_inputs() -> tuple[dict, list[dict], dict, dict]:
    assert sha256(LOCK_PATH) == LOCK_SHA, "C1 source lock SHA mismatch"
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8-sig"))
    scene_path = Path(lock["scene_list"]["path"])
    assert sha256(scene_path) == SCENE_SHA == lock["scene_list"]["sha256"]
    manifest_sha = sha256(MANIFEST_PATH)
    with MANIFEST_PATH.open(encoding="utf-8-sig", newline="") as stream:
        all_rows = list(csv.DictReader(stream))
    rows = [r for r in all_rows if r["condition"] == "ON1"]
    with scene_path.open(encoding="utf-8-sig", newline="") as stream:
        scenes = list(csv.DictReader(stream))
    assert len(rows) == len(scenes) == 12
    assert len({r["scene_id"] for r in rows}) == len(rows)
    scene_by_id = {r["scene_id"]: r for r in scenes}
    assert set(scene_by_id) == {r["scene_id"] for r in rows}
    ordered = []
    for scene in scenes:
        match = next(r for r in rows if r["scene_id"] == scene["scene_id"])
        assert match["task"] == scene["task"]
        assert match["wind_band"] == scene["band"]
        assert match["status"] == "STABLE" and match["safe_complete_finite"].lower() == "true"
        assert Path(match["raw_path"]).is_file()
        ordered.append(match)
    physical_names = {
        "run_dl1018_closed_loop.m",
        "vehicle_derivative.m",
        "rk4_vehicle_step.m",
        "morphology_aware_wind_load.m",
    }
    pinned_files = [Path(x["path"]) for x in lock["frozen_runtime_files"]]
    pinned_plant = [Path(x["path"]) for x in lock["frozen_plant_files"]]
    relevant = [p for p in pinned_files + pinned_plant if p.name in physical_names]
    assert {p.name for p in relevant} == physical_names
    relevant_identity = []
    for p in relevant:
        entry = next(x for x in lock["frozen_runtime_files"] + lock["frozen_plant_files"] if Path(x["path"]) == p)
        actual = sha256(p)
        assert actual == entry["sha256"], f"locked physical source mismatch: {p}"
        relevant_identity.append({"path": str(p), "sha256": actual})
    config_path = next(p for p in pinned_files if p.name == "effective_config.mat")
    config_entry = next(x for x in lock["frozen_runtime_files"] if Path(x["path"]) == config_path)
    assert sha256(config_path) == config_entry["sha256"]
    cfg_signature = stat_signature(config_path)
    cfg = loadmat(config_path, simplify_cells=True)["cfg"]["plant"]
    mass, gravity, dt = float(cfg["mass"]), float(cfg["g"]), float(cfg["dt"])
    assert math.isfinite(mass) and mass > 0 and math.isfinite(gravity) and abs(dt - DT) < 1e-15
    assert stat_signature(config_path) == cfg_signature and sha256(config_path) == config_entry["sha256"]
    static = {
        "lock_path": str(LOCK_PATH), "lock_sha256": LOCK_SHA,
        "manifest_path": str(MANIFEST_PATH), "manifest_sha256_before": manifest_sha,
        "scene_list_path": str(scene_path), "scene_list_sha256": SCENE_SHA,
        "effective_config_path": str(config_path), "effective_config_sha256": config_entry["sha256"],
        "mass_kg": mass, "gravity_mps2": gravity, "dt_s": dt,
        "physical_source_identities": relevant_identity,
        "manifest_run_count_all_conditions": len(all_rows), "original_on1_run_count": len(ordered),
    }
    return lock, ordered, static, {"scene_rows": scenes, "manifest_signature": stat_signature(MANIFEST_PATH)}


def read_one(run: dict, mass: float, gravity: float) -> tuple[dict, dict]:
    path = Path(run["raw_path"])
    before = stat_signature(path)
    actual_sha = sha256(path)
    assert actual_sha == run["raw_sha256"], f"raw SHA mismatch: {run['scene_id']}"
    with h5py.File(path, "r") as f:
        g = f["log"]

        def read(key: str) -> np.ndarray:
            return np.asarray(g[key]).T

        state = read("state")
        time_s = read("time").reshape(-1)
        transition_time = read("transition_time").reshape(-1)
        valid = read("stage1_position_event_inference_valid").reshape(-1).astype(bool)
        af = read("stage1_position_pcf_a_f_mps2")
        realized = read("realized_generalized")
        wind_force = read("wind_force_I")
        euler_filtered = read("filtered_attitude_reference")
        requested = read("requested_generalized")
        enabled = read("stage1_position_pcf_coordination_enabled").item()

    assert state.shape == (20001, 12)
    assert time_s.shape == (20001,) and transition_time.shape == (20000,)
    assert af.shape == wind_force.shape == euler_filtered.shape == (20000, 3)
    assert realized.shape == requested.shape == (20000, 4)
    assert int(enabled) == 1
    assert np.array_equal(np.flatnonzero(valid), EXPECTED_EVENTS)
    assert np.max(np.abs(np.diff(time_s) - DT)) < 1e-12
    assert np.max(np.abs(time_s[:-1] - transition_time)) < 1e-12
    assert np.max(np.abs(transition_time[EXPECTED_EVENTS] - time_s[EXPECTED_EVENTS])) < 1e-12
    for name, a in (("state", state), ("a_f", af), ("realized", realized),
                    ("wind_force", wind_force), ("filtered_euler", euler_filtered),
                    ("requested", requested)):
        assert np.isfinite(a).all(), f"nonfinite {name}: {run['scene_id']}"

    # Runtime state convention: x(:,4:6) is velocity and x(:,7:9) is Euler.
    # Reconstruct the k1 physical acceleration from realized thrust and logged
    # true wind, solely as an offline oracle (not a deployable signal).
    thrust_axis = body_z(state[:-1, 6:9])
    a_actual_k1 = (realized[:, :1] * thrust_axis + wind_force) / mass
    a_actual_k1[:, 2] -= gravity
    d_i = a_actual_k1 - af

    # Check that the logged filter acceleration is from the current requested
    # thrust and filtered attitude, preserving the same step's timing.
    af_from_request = requested[:, :1] * body_z(euler_filtered) / mass
    af_from_request[:, 2] -= gravity
    af_closure = float(np.max(np.abs(af - af_from_request)))
    assert af_closure < 1e-11, f"a_f time/physics closure failed: {run['scene_id']} ({af_closure})"

    event_ids = np.flatnonzero(valid)
    interval_mean_af = np.stack([af[k - WINDOW:k].mean(axis=0) for k in event_ids])
    interval_mean_di = np.stack([d_i[k - WINDOW:k].mean(axis=0) for k in event_ids])
    dhat = (state[event_ids, 3:6] - state[event_ids - WINDOW, 3:6]) / (WINDOW * DT) - interval_mean_af
    current_di = d_i[event_ids]
    event_times = transition_time[event_ids]
    assert np.isfinite(dhat).all() and np.isfinite(interval_mean_di).all() and np.isfinite(current_di).all()
    assert np.array_equal(event_ids[1:] - WINDOW, event_ids[:-1])
    prev_phi_mask = np.zeros(event_ids.shape, dtype=bool)
    prev_phi_mask[1:] = True
    late = (event_times >= LATE_START_S) & (event_times < END_S)
    assert int(late.sum()) == 1500 and prev_phi_mask[late].all()

    axes = {"ALL": [0, 1, 2], "X": [0], "Y": [1], "Z": [2]}
    late_ix = np.flatnonzero(late)
    rows = []
    aggregate = {}
    for axis, cols in axes.items():
        same_err = (dhat[late][:, cols] - interval_mean_di[late][:, cols]).reshape(-1)
        current_err = (dhat[late][:, cols] - current_di[late][:, cols]).reshape(-1)
        interval_truth = interval_mean_di[late][:, cols].reshape(-1)
        current_truth = current_di[late][:, cols].reshape(-1)
        aggregate[axis] = {
            "count": int(same_err.size),
            "same_ss": float(same_err @ same_err), "same_sum": float(same_err.sum()),
            "interval_truth_ss": float(interval_truth @ interval_truth),
            "current_ss": float(current_err @ current_err), "current_sum": float(current_err.sum()),
            "current_truth_ss": float(current_truth @ current_truth),
        }
        rows.append({
            "scope": "SCENE", "group": run["scene_id"], "scene_id": run["scene_id"],
            "task": run["task"], "wind_band": run["wind_band"], "axis": axis,
            "window": "5_to_20s", "event_count": int(late.sum()),
            "events_previous_valid_phi_mapped": int(prev_phi_mask[late].sum()),
            "dhat_vs_10ms_interval_d_rmse_mps2": float(np.sqrt(np.mean(same_err * same_err))),
            "dhat_vs_10ms_interval_d_bias_mps2": float(same_err.mean()),
            "interval_d_rms_mps2": float(np.sqrt(np.mean(interval_truth * interval_truth))),
            "dhat_vs_current_instant_d_rmse_mps2": float(np.sqrt(np.mean(current_err * current_err))),
            "dhat_vs_current_instant_d_bias_mps2": float(current_err.mean()),
            "current_instant_d_rms_mps2": float(np.sqrt(np.mean(current_truth * current_truth))),
        })
    record = {
        "scene_id": run["scene_id"], "task": run["task"], "wind_band": run["wind_band"],
        "raw_path": str(path), "raw_sha256": actual_sha, "raw_bytes": before[0],
        "raw_mtime_ns_before": before[1], "raw_mtime_ns_after": stat_signature(path)[1],
        "event_count": int(event_ids.size), "event_first_index": int(event_ids[0]),
        "event_last_index": int(event_ids[-1]), "event_first_time_s": float(event_times[0]),
        "event_last_time_s": float(event_times[-1]),
        "previous_valid_phi_mapping_count": int(prev_phi_mask.sum()),
        "previous_valid_phi_mapping_first_event_index": int(event_ids[1]),
        "previous_interval_event_count_5_to_20s": int(late.sum()),
        "a_f_from_current_request_max_abs_mps2": af_closure,
        "dt_max_abs_error_s": float(np.max(np.abs(np.diff(time_s) - DT))),
        "event_time_max_abs_error_s": float(np.max(np.abs(event_times - time_s[event_ids]))),
        "metrics": aggregate,
    }
    assert stat_signature(path) == before and sha256(path) == actual_sha == run["raw_sha256"]
    return record, {"rows": rows, "event_times": event_times}


def make_group_rows(records: list[dict], scene_rows: list[dict], scene_metrics: list[dict]) -> list[dict]:
    scene_meta = {r["scene_id"]: r for r in scene_rows}
    scopes = {
        "ALL12": set(scene_meta),
        "HF_W09_W14": {sid for sid, r in scene_meta.items() if r["band"] in ("W09_W11", "W12_W14")},
        "W15": {sid for sid, r in scene_meta.items() if r["band"] == "W15"},
    }
    assert len(scopes["HF_W09_W14"]) == 6 and len(scopes["W15"]) == 3
    rec_by_id = {r["scene_id"]: r for r in records}
    rows = []
    for group, ids in scopes.items():
        for axis in ("ALL", "X", "Y", "Z"):
            selected = [rec_by_id[sid] for sid in sorted(ids)]
            n = sum(x["metrics"][axis]["count"] for x in selected)
            same_ss = sum(x["metrics"][axis]["same_ss"] for x in selected)
            same_sum = sum(x["metrics"][axis]["same_sum"] for x in selected)
            interval_ss = sum(x["metrics"][axis]["interval_truth_ss"] for x in selected)
            current_ss = sum(x["metrics"][axis]["current_ss"] for x in selected)
            current_sum = sum(x["metrics"][axis]["current_sum"] for x in selected)
            current_truth_ss = sum(x["metrics"][axis]["current_truth_ss"] for x in selected)
            per_scene = [r for r in scene_metrics if r["scene_id"] in ids and r["axis"] == axis]
            rows.append({
                "scope": "GROUP", "group": group, "scene_id": "", "task": "",
                "wind_band": "", "axis": axis, "window": "5_to_20s",
                "scene_count": len(ids), "event_count": len(ids) * 1500,
                "events_previous_valid_phi_mapped": len(ids) * 1500,
                "dhat_vs_10ms_interval_d_rmse_mps2": float(math.sqrt(same_ss / n)),
                "dhat_vs_10ms_interval_d_bias_mps2": float(same_sum / n),
                "interval_d_rms_mps2": float(math.sqrt(interval_ss / n)),
                "dhat_vs_current_instant_d_rmse_mps2": float(math.sqrt(current_ss / n)),
                "dhat_vs_current_instant_d_bias_mps2": float(current_sum / n),
                "current_instant_d_rms_mps2": float(math.sqrt(current_truth_ss / n)),
                "mean_scene_interval_rmse_mps2": float(np.mean([x["dhat_vs_10ms_interval_d_rmse_mps2"] for x in per_scene])),
                "mean_scene_current_rmse_mps2": float(np.mean([x["dhat_vs_current_instant_d_rmse_mps2"] for x in per_scene])),
            })
    return rows


def write_json(path: Path, value: dict) -> None:
    assert not path.exists(), f"refusing to overwrite {path}"
    path.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")


def write_csv(path: Path, rows: list[dict]) -> None:
    assert not path.exists(), f"refusing to overwrite {path}"
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--smoke", action="store_true", help="one fixed first ON1 record")
    mode.add_argument("--full", action="store_true", help="all fixed 12 ON1 records")
    args = parser.parse_args()
    started = time.perf_counter()
    lock, runs, static, guard = read_inputs()
    mass, gravity = static["mass_kg"], static["gravity_mps2"]

    if args.smoke:
        record, _ = read_one(runs[0], mass, gravity)
        report = {
            "schema": "C2_CAUSAL_10MS_SMOKE_V1", "status": "PASS_ONE_ORIGINAL_ON1_RECORD",
            "run": {k: v for k, v in record.items() if k != "metrics"},
            "metrics": record["metrics"], "static_inputs": static,
            "formula": "dhat_prev(k)=(v[k]-v[k-10])/(10*dt)-mean(a_f[k-10:k]); truth_interval=mean(d_i[k-10:k]); current_lag_check=d_i[k]",
        }
        report["elapsed_seconds"] = time.perf_counter() - started
        report["script_sha256"] = sha256(Path(__file__))
        write_json(HERE / "SMOKE_FIRST_ON1.json", report)
        print(json.dumps({"status": report["status"], "scene_id": runs[0]["scene_id"],
                          "events": record["event_count"], "late_events": record["previous_interval_event_count_5_to_20s"],
                          "elapsed_seconds": report["elapsed_seconds"]}))
        return

    records, all_scene_rows = [], []
    for run in runs:
        record, outputs = read_one(run, mass, gravity)
        records.append(record)
        all_scene_rows.extend(outputs["rows"])
    group_rows = make_group_rows(records, guard["scene_rows"], all_scene_rows)
    assert len(records) == 12 and len(all_scene_rows) == 48 and len(group_rows) == 12
    assert sha256(LOCK_PATH) == LOCK_SHA
    assert sha256(MANIFEST_PATH) == static["manifest_sha256_before"]
    assert stat_signature(MANIFEST_PATH) == guard["manifest_signature"]
    scene_path = Path(lock["scene_list"]["path"])
    assert sha256(scene_path) == SCENE_SHA
    for record, run in zip(records, runs):
        path = Path(run["raw_path"])
        assert sha256(path) == record["raw_sha256"] == run["raw_sha256"]
    output_rows = all_scene_rows + group_rows
    report = {
        "schema": "C2_CAUSAL_10MS_FIXED12_V1",
        "status": "PASS_OFFLINE_CAUSAL_AVAILABILITY_APPROXIMATION",
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "static_inputs": static,
        "script_sha256": sha256(Path(__file__)),
        "sample_definition": {
            "source": "all 12 original C1 ON1 raw files from C1_SCREEN_PER_RUN.csv, in frozen scene-list order",
            "records": len(records), "event_indices_per_record": "320..19990 inclusive, step 10",
            "events_per_record": 1968, "first_event_index_320_previous_valid_head_event": False,
            "previous_valid_head_event_alignment": "k=330..19990 (1967 events); k=320 is computable as dhat but has no prior valid 100-Hz head event",
            "reported_window": "5.0 <= transition_time < 20.0 s",
            "events_per_record_in_window": 1500,
        },
        "definitions": {
            "state_velocity": "raw log.state columns 4:6 (MATLAB x(k,4:6)); current event state and 10 ms past state only",
            "a_f": "logged stage1_position_pcf_a_f_mps2; checked against requested thrust / mass * R(filtered_euler)e3 - g*e3",
            "a_actual_k1": "(realized_generalized_thrust*R(state_euler)e3 + logged wind_force_I)/mass - g*e3; offline physical oracle at each 1 ms step start",
            "d_i": "a_actual_k1 - a_f at the same 1 ms step",
            "dhat_prev": "(v[k]-v[k-10])/(10*dt) - mean(a_f[k-10:k]); available at event k, no future velocity used",
            "same_interval_truth": "mean(d_i[k-10:k]); compared with dhat_prev over the exact preceding interval",
            "current_instant_truth": "d_i[k]; only a timing-lag comparison, not observable at event k",
            "grouping": "ALL12; HF_W09_W14 combines W09_W11 and W12_W14; W15 remains separate",
        },
        "interpretation_limits": [
            "Finite difference versus RK4 step-start physical derivative is a sampling/integration approximation, not exact instantaneous acceleration.",
            "The log velocity is the simulated plant state, not a noisy sensor record; field sensor noise was not simulated here.",
            "If measured velocity has independent per-axis standard deviation sigma_v, the difference term contributes sqrt(2)*sigma_v/0.01 m/s^2 standard deviation; sigma_v is unknown and no noiseless deployment assumption is made.",
            "The true-wind physical acceleration is offline validation only; deployment-side estimate uses velocity and the internally known/logged filter acceleration.",
            "No claim of closed-loop causal benefit, prediction accuracy under real sensor noise, or controller change is supported by this descriptive check.",
        ],
        "records": [{k: v for k, v in r.items() if k != "metrics"} for r in records],
        "rows_csv": "CAUSAL_10MS_METRICS.csv",
        "elapsed_seconds": time.perf_counter() - started,
        "Plant": 0, "training": 0, "optimizer": 0, "GPU": 0, "TEST": False,
    }
    write_csv(HERE / "CAUSAL_10MS_METRICS.csv", output_rows)
    write_json(HERE / "CAUSAL_10MS_FIXED12.json", report)
    print(json.dumps({"status": report["status"], "records": len(records),
                      "metric_rows": len(output_rows), "elapsed_seconds": report["elapsed_seconds"],
                      "output_bytes": (HERE / "CAUSAL_10MS_METRICS.csv").stat().st_size + (HERE / "CAUSAL_10MS_FIXED12.json").stat().st_size}))


if __name__ == "__main__":
    main()
