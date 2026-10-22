#!/usr/bin/env python3
"""Independent read-only scorer for the fixed 12-scene R3 XY-mask screen."""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

import h5py
import numpy as np

HERE = Path(__file__).resolve().parents[1]
LOCK_PATH = HERE / "frozen_inputs.json"
LOCK = json.loads(LOCK_PATH.read_text(encoding="utf-8-sig"))
IDS = [row["scene_id"] for row in LOCK["scenes"]]
TOL = float(LOCK["analysis"]["paired_raw_tolerance_m"])
WEIGHT_TOL = float(LOCK["run"]["weight_delta_threshold_unitless"])
SETUP = {entry["name"]: entry for entry in LOCK["setupFiles"]}
TILT_TICKS = 20000
PLANT_DT = float(LOCK["run"]["plant_dt_s"])


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_identity(path: Path) -> tuple[str, int, int]:
    before = path.stat()
    digest = sha256(path)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError(f"file changed during SHA read: {path}")
    return digest, after.st_size, after.st_mtime_ns


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def test_path(path: Path) -> None:
    if any(re.search(r"(^|[_-])TEST([_-]|$)", part, re.I) for part in path.parts):
        raise RuntimeError(f"refusing sealed TEST path: {path}")


def load_scanner() -> object:
    item = LOCK["scoring_helper"]
    path = Path(item["path"])
    if sha256(path) != item["sha256"].lower():
        raise RuntimeError("locked raw_scan.py SHA changed")
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("r3_locked_raw_scan", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load locked raw_scan.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    original_score = module.score
    def score_with_axis_aliases(path):
        metrics = original_score(path)
        for axis in "xyz":
            for phase in ("0_20", "0_5", "5_20"):
                lower = f"RMSE_{axis}_{phase}"
                if lower in metrics:
                    metrics[f"RMSE_{axis.upper()}_{phase}"] = metrics[lower]
        return metrics
    module.score = score_with_axis_aliases
    return module


def h5_arr(scanner: object, log: h5py.Group, name: str) -> np.ndarray:
    if name not in log:
        raise RuntimeError(f"missing raw field log/{name}")
    return np.asarray(scanner.arr(log, name))


def transition_time_vector(value: object, expected_ticks: int = TILT_TICKS) -> np.ndarray:
    axis = np.asarray(value)
    is_vector = axis.ndim == 1 or (axis.ndim == 2 and 1 in axis.shape)
    if not is_vector or axis.size != expected_ticks:
        raise RuntimeError(f"transition_time must be a {expected_ticks}-tick vector; shape={axis.shape}")
    try:
        axis = axis.astype(float, copy=False).reshape(-1)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("transition_time must be numeric") from exc
    if not np.isfinite(axis).all():
        raise RuntimeError("transition_time contains nonfinite values")
    canonical = np.arange(expected_ticks, dtype=float) * PLANT_DT
    if not np.allclose(axis, canonical, rtol=0.0, atol=1e-12):
        raise RuntimeError(f"transition_time differs from the locked {PLANT_DT:g}-s plant grid")
    return axis


def tilt_flag_vector(value: object, role: str, expected_ticks: int = TILT_TICKS) -> np.ndarray:
    flags = np.asarray(value)
    is_vector = flags.ndim == 1 or (flags.ndim == 2 and 1 in flags.shape)
    if not is_vector or flags.size != expected_ticks:
        raise RuntimeError(f"{role} tilt_limited must be a {expected_ticks}-tick vector; shape={flags.shape}")
    if flags.dtype.kind not in "biuf" or not np.isfinite(flags).all():
        raise RuntimeError(f"{role} tilt_limited contains invalid/nonfinite values")
    if not np.isin(flags, (0, 1)).all():
        raise RuntimeError(f"{role} tilt_limited must contain only 0/1 flags")
    return flags.reshape(-1).astype(bool)


def new_tilt_limited_mask(
    xy: object, b: object, pcf_on: object, pcf_off: object, expected_ticks: int = TILT_TICKS
) -> np.ndarray:
    xy_flags = tilt_flag_vector(xy, "R3_XY", expected_ticks)
    b_flags = tilt_flag_vector(b, "B_BASELINE", expected_ticks)
    on_flags = tilt_flag_vector(pcf_on, "PCF_ON", expected_ticks)
    off_flags = tilt_flag_vector(pcf_off, "PCF_OFF", expected_ticks)
    return xy_flags & ~(b_flags | on_flags | off_flags)


def text_value(scanner: object, log: h5py.Group, name: str) -> str:
    value = h5_arr(scanner, log, name)
    if value.dtype.kind in "SU":
        return "".join(str(part) for part in value.reshape(-1)).strip()
    if value.dtype.kind in "iu":
        return "".join(chr(int(part)) for part in value.reshape(-1) if part).strip()
    return str(value.reshape(-1)[0]).strip()


def score_raw(
    scanner: object, path: Path, expected_sha: str, role: str
) -> tuple[dict[str, object], np.ndarray, np.ndarray, np.ndarray]:
    test_path(path)
    before = stable_identity(path)
    if before[0].lower() != expected_sha.lower():
        raise RuntimeError(f"{role} raw SHA differs from frozen identity: {path}")
    scan = scanner.score(path)
    with h5py.File(path, "r") as raw:
        if "log" not in raw:
            raise RuntimeError(f"{role} raw has no log group: {path}")
        log = raw["log"]
        transition = transition_time_vector(h5_arr(scanner, log, "transition_time"))
        state = np.asarray(h5_arr(scanner, log, "state"), dtype=float)
        ref = np.asarray(h5_arr(scanner, log, "reference/position"), dtype=float)
        controller = np.asarray(h5_arr(scanner, log, "controller_call_time_s"), dtype=float).reshape(-1)
        saturated = np.asarray(h5_arr(scanner, log, "motor_saturated"), dtype=float)
        clipped = np.asarray(h5_arr(scanner, log, "generalized_clipped"), dtype=float)
        tilt_limited = tilt_flag_vector(h5_arr(scanner, log, "tilt_limited"), role, transition.size)
        status = text_value(scanner, log, "status")
        last = float(np.asarray(h5_arr(scanner, log, "last_transition")).reshape(-1)[0])
        reason = text_value(scanner, log, "safety_stop_reason")
    if stable_identity(path) != before:
        raise RuntimeError(f"{role} raw changed during scoring: {path}")
    if scan.get("status") != "scored" or scan.get("transitions") != 20000 or scan.get("complete") is not True or scan.get("finite") is not True:
        raise RuntimeError(f"{role} raw is incomplete/nonfinite: {path}")
    if transition.size != 20000 or transition[0] != 0.0 or transition[-1] != 19.999 or np.any(np.diff(transition) <= 0):
        raise RuntimeError(f"{role} transition timebase invalid: {path}")
    if state.ndim != 2 or state.shape[0] != 20001 or state.shape[1] < 9 or ref.shape != (20001, 3):
        raise RuntimeError(f"{role} state/reference dimensions invalid: {path}")
    if controller.size != 20000 or not np.isfinite(controller).all() or np.any(controller < 0):
        raise RuntimeError(f"{role} controller_call_time_s missing or invalid: {path}")
    if not all(np.isfinite(array).all() for array in (state, ref, saturated, clipped)):
        raise RuntimeError(f"{role} raw metrics contain NaN/Inf: {path}")
    if status != "STABLE" or last != 20000 or reason:
        raise RuntimeError(f"{role} status/safety failed: {path}; status={status}, last={last}, reason={reason!r}")
    if saturated.shape[0] != 20000 or clipped.shape[0] != 20000:
        raise RuntimeError(f"{role} saturation/clipping arrays have wrong time dimension: {path}")
    metrics = {**scan,
        "status": status, "last_transition": int(last), "safe": True,
        "safety_stop_reason": reason, "controller_call_time_mean_s": float(np.mean(controller)),
        "controller_call_time_p95_s": float(np.quantile(controller, .95)),
        "controller_call_time_max_s": float(np.max(controller)),
        "motor_saturated_fraction": float(np.mean(np.any(saturated != 0, axis=1))),
        "generalized_clipped_fraction": float(np.mean(np.any(clipped != 0, axis=1))),
        "tilt_limited_count": int(np.count_nonzero(tilt_limited)),
        "tilt_limited_fraction": float(np.mean(tilt_limited)),
        "raw_sha256": before[0], "raw_size_bytes": before[1],
        "raw_integrity_status": "PASS_SHA_SIZE_MTIME_AND_ARRAYS"}
    for key in ("Q_0_20", "peak", "p95", "RMSE_X_0_20", "RMSE_Y_0_20", "RMSE_Z_0_20",
                "RMSE_X_0_5", "RMSE_Y_0_5", "RMSE_Z_0_5", "RMSE_X_5_20", "RMSE_Y_5_20", "RMSE_Z_5_20"):
        if key not in metrics or not np.isfinite(float(metrics[key])):
            raise RuntimeError(f"{role} metric missing/nonfinite: {key}")
    return metrics, ref, tilt_limited, transition


def status_summary_row(r2_row: dict[str, str], prefix: str) -> None:
    if (r2_row.get(f"{prefix}_status") != "STABLE" or r2_row.get(f"{prefix}_last_transition") != "20000"
            or r2_row.get(f"{prefix}_finite", "").lower() != "true"
            or r2_row.get(f"{prefix}_complete", "").lower() != "true"
            or r2_row.get(f"{prefix}_safe", "").lower() != "true"
            or r2_row.get(f"{prefix}_safety_stop_reason", "") != ""):
        raise RuntimeError(f"frozen R2 {prefix} summary status is not complete/safe")


def verify_candidate_events(scanner: object, path: Path, status: dict[str, object]) -> dict[str, object]:
    with h5py.File(path, "r") as raw:
        log = raw["log"]
        surface = np.asarray(h5_arr(scanner, log, "stage1_position_pcf_event_s_original_mps"), dtype=float)
        eta = np.asarray(h5_arr(scanner, log, "stage1_position_pcf_event_eta_before_mps"), dtype=float)
        eta_eff = np.asarray(h5_arr(scanner, log, "stage1_position_pcf_event_eta_effective_mps"), dtype=float)
        mask = np.asarray(h5_arr(scanner, log, "stage1_position_pcf_event_eta_mask"), dtype=float)
        coord = np.asarray(h5_arr(scanner, log, "stage1_position_pcf_event_s_coord_mps"), dtype=float)
        eff = np.asarray(h5_arr(scanner, log, "stage1_position_pcf_event_s_coord_eff_mps"), dtype=float)
        w_before = np.asarray(h5_arr(scanner, log, "stage1_position_event_weight_before_33x3"), dtype=float)
        w_after = np.asarray(h5_arr(scanner, log, "stage1_position_event_weight_after_33x3"), dtype=float)
    count = int(status["update_event_count"])
    if surface.shape != (count, 3) or any(a.shape != surface.shape for a in (eta, eta_eff, mask, coord, eff)):
        raise RuntimeError("candidate eta/surface event arrays have incorrect dimensions")
    if w_before.shape != (33, 3, count) or w_after.shape != w_before.shape:
        raise RuntimeError("candidate W-before/W-after must be 33x3xN")
    arrays = (surface, eta, eta_eff, mask, coord, eff, w_before, w_after)
    if not all(np.isfinite(array).all() for array in arrays):
        raise RuntimeError("candidate event arrays contain NaN/Inf")
    expected_mask = np.tile(np.array([1.0, 1.0, 0.0]), (count, 1))
    errors = {
        "eta_mask": float(np.max(np.abs(mask - expected_mask))),
        "eta_effective": float(np.max(np.abs(eta_eff - eta * expected_mask))),
        "surface_coord": float(np.max(np.abs(coord - (surface - eta_eff)))),
        "clip": float(np.max(np.abs(eff - np.clip(coord, [-7, -8, -10], [7, 8, 10])))),
        "weight_delta": float(np.max(np.abs(w_after - w_before))),
    }
    if max(errors[k] for k in ("eta_mask", "eta_effective", "surface_coord", "clip")) > TOL:
        raise RuntimeError(f"candidate eta/surface equations fail: {errors}")
    if errors["weight_delta"] <= WEIGHT_TOL:
        raise RuntimeError("candidate W did not change above the unitless update threshold")
    return {"event_count": count, **errors}


def outcome(delta: float) -> str:
    if delta < -TOL:
        return "WIN"
    if delta > TOL:
        return "LOSS"
    return "TIE"


def main() -> int:
    if LOCK.get("safety", {}).get("read_test") is not False:
        raise RuntimeError("R3 lock must forbid TEST access")
    for name, entry in SETUP.items():
        if sha256(Path(entry["path"])) != entry["sha256"].lower():
            raise RuntimeError(f"R3 package source SHA changed: {name}")
    if sha256(Path(LOCK["taskbook"]["path"])) != LOCK["taskbook"]["sha256"].lower():
        raise RuntimeError("frozen taskbook SHA changed")
    for entry in LOCK["rescores"]:
        if sha256(Path(entry["path"])) != entry["sha256"].lower():
            raise RuntimeError(f"frozen {entry['role']} rescore SHA changed")
        for row in read_csv(Path(entry["path"])):
            if row.get("split", "").upper() not in {"DEV", "VAL"} or "TEST" in " ".join(row.values()).upper():
                raise RuntimeError("frozen rescore table is not DEV/VAL-only")

    scanner = load_scanner()
    verifier_path = HERE / "reports" / "verify_round3_identity_compat.py"
    spec = importlib.util.spec_from_file_location("round3_identity_verifier", verifier_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load R3 identity verifier")
    verifier = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = verifier
    spec.loader.exec_module(verifier)
    input_audit = verifier.verify_inputs(LOCK)

    r2_rows = read_csv(Path(LOCK["upstream_round2"]["results_path"]))
    r2_by_id = {row["scene_id"]: row for row in r2_rows}
    if len(r2_by_id) != 12 or set(r2_by_id) != set(IDS):
        raise RuntimeError("R2 frozen results are not exactly the 12 VAL rows")
    manifest = read_csv(Path(LOCK["reuse_manifest"]["path"]))
    manifest_by_key = {(row["scene_id"], row["role"]): row for row in manifest}
    off_by_id = {row["scene_id"]: row for row in LOCK["round2_off_raws"]}
    records: list[dict[str, object]] = []
    for scene in LOCK["scenes"]:
        scene_id = scene["scene_id"]
        r2_row = r2_by_id[scene_id]
        per_method: dict[str, dict[str, object]] = {}
        references: list[np.ndarray] = []
        tilt_flags: dict[str, np.ndarray] = {}
        time_axes: list[np.ndarray] = []
        for method, role, prefix in (("B", "B_BASELINE", "b"), ("PCF_ON", "ON_CANDIDATE", "on")):
            row = manifest_by_key[(scene_id, role)]
            metrics, ref, tilt, time_axis = score_raw(scanner, Path(row["raw_path"]), row["raw_sha256"], method)
            status_summary_row(r2_row, prefix)
            if r2_row[f"{prefix}_raw_sha256"].lower() != row["raw_sha256"].lower():
                raise RuntimeError(f"R2 {method} raw hash differs from results row: {scene_id}")
            # The R2 rescoring CSVs bind the raw/hash; the published R2 CSV supplies a second score cross-check.
            expected_q = float(r2_row[f"{prefix}_q_0_20_m"])
            if abs(float(metrics["Q_0_20"]) - expected_q) > TOL:
                raise RuntimeError(f"independent R2 {method} Q differs from frozen R2 result: {scene_id}")
            for axis in "XYZ":
                for phase in ("0_20", "0_5", "5_20"):
                    key = f"RMSE_{axis}_{phase}"
                    csv_key = f"rmse_{axis.lower()}_{prefix}_{phase}_m"
                    if abs(float(metrics[key]) - float(r2_row[csv_key])) > TOL:
                        raise RuntimeError(f"independent R2 {method} {key} differs from frozen result: {scene_id}")
            metrics["raw_sha256"] = row["raw_sha256"]
            metrics["identity_status"] = "R2_LOCK_RESCORE_AND_RAW_HASH"
            per_method[method] = metrics
            tilt_flags[method] = tilt
            time_axes.append(time_axis)
            references.append(ref)

        off_entry = off_by_id[scene_id]
        off_metrics, off_ref, off_tilt, off_time_axis = score_raw(
            scanner, Path(off_entry["raw_path"]), off_entry["raw_sha256"], "R2_PCF_OFF"
        )
        if r2_row["off_raw_sha256"].lower() != off_entry["raw_sha256"].lower():
            raise RuntimeError(f"R2 OFF raw hash differs from frozen result row: {scene_id}")
        for prefix, metrics in (("off", off_metrics),):
            status_summary_row(r2_row, prefix)
            if abs(float(metrics["Q_0_20"]) - float(r2_row["off_q_0_20_m"])) > TOL:
                raise RuntimeError(f"independent R2 OFF Q differs from frozen result: {scene_id}")
        off_metrics["raw_sha256"] = off_entry["raw_sha256"]
        off_metrics["identity_status"] = "R2_OFF_STATUS_RAW_AND_LOCK_SHA"
        per_method["PCF_OFF"] = off_metrics
        tilt_flags["PCF_OFF"] = off_tilt
        time_axes.append(off_time_axis)
        references.append(off_ref)

        attempt = HERE / "runs" / scene_id / "attempt_01"
        raw_path, status_path = attempt / "raw_run.mat", attempt / "run_status.json"
        status = json.loads(status_path.read_text(encoding="utf-8-sig"))
        candidate_math = verifier.verify_candidate(LOCK, scene_id)
        candidate, xy_ref, xy_tilt, xy_time_axis = score_raw(scanner, raw_path, status["raw_sha256"], "R3_XY")
        if status.get("episode_runtime_seconds", 0) <= 0 or status.get("attempt_execution_and_raw_persistence_seconds", 0) <= 0:
            raise RuntimeError(f"R3 timing fields missing: {scene_id}")
        candidate["episode_runtime_s"] = float(status["episode_runtime_seconds"])
        candidate["attempt_execution_and_raw_persistence_s"] = float(status["attempt_execution_and_raw_persistence_seconds"])
        candidate["raw_sha256"] = status["raw_sha256"]
        candidate["identity_status"] = "R3_RUN_STATUS_SOURCE_RAW_AND_EVENT_EQUATIONS"
        candidate["update_event_count"] = int(status["update_event_count"])
        candidate["eta_mask"] = "[1,1,0]"
        candidate["event_equations"] = candidate_math
        per_method["R3_XY"] = candidate
        tilt_flags["R3_XY"] = xy_tilt
        time_axes.append(xy_time_axis)
        references.append(xy_ref)
        if any(ref.shape != references[0].shape or not np.array_equal(ref, references[0]) for ref in references[1:]):
            raise RuntimeError(f"B/ON/OFF/XY logged reference-position inputs differ: {scene_id}")
        if any(not np.array_equal(axis, time_axes[0]) for axis in time_axes[1:]):
            raise RuntimeError(f"B/ON/OFF/XY transition_time axes differ: {scene_id}")
        new_tilt = new_tilt_limited_mask(
            tilt_flags["R3_XY"], tilt_flags["B"], tilt_flags["PCF_ON"], tilt_flags["PCF_OFF"], time_axes[0].size
        )
        candidate["new_tilt_limited_count"] = int(np.count_nonzero(new_tilt))

        out: dict[str, object] = {"scene_id": scene_id, "split": "VAL", "task": scene["task"], "band": scene["band"],
                                  "reference_position_input_elementwise_equal": True}
        for method, prefix in (("B", "b"), ("PCF_ON", "on"), ("PCF_OFF", "off"), ("R3_XY", "xy")):
            metric = per_method[method]
            out[f"{prefix}_raw_sha256"] = metric["raw_sha256"]
            for key in ("Q_0_20", "peak", "p95", "motor_saturated_fraction", "generalized_clipped_fraction",
                        "tilt_limited_count", "tilt_limited_fraction",
                        "controller_call_time_mean_s", "controller_call_time_p95_s", "controller_call_time_max_s"):
                name = f"{prefix}_{key.lower()}" if key != "Q_0_20" else f"{prefix}_q_0_20_m"
                out[name] = int(metric[key]) if key == "tilt_limited_count" else float(metric[key])
            for axis in "XYZ":
                for phase in ("0_20", "0_5", "5_20"):
                    out[f"rmse_{axis.lower()}_{prefix}_{phase}_m"] = float(metric[f"RMSE_{axis}_{phase}"])
            out[f"{prefix}_status"] = metric["status"]
            out[f"{prefix}_last_transition"] = int(metric["last_transition"])
            out[f"{prefix}_safe"] = bool(metric["safe"])
            out[f"{prefix}_identity_status"] = str(metric["identity_status"])
        out["xy_episode_runtime_s"] = candidate["episode_runtime_s"]
        out["xy_attempt_execution_and_raw_persistence_s"] = candidate["attempt_execution_and_raw_persistence_s"]
        out["xy_update_event_count"] = candidate["update_event_count"]
        out["xy_new_tilt_limited_count"] = candidate["new_tilt_limited_count"]
        out["delta_q_xy_minus_b_m"] = float(candidate["Q_0_20"]) - float(per_method["B"]["Q_0_20"])
        out["delta_q_xy_minus_on_m"] = float(candidate["Q_0_20"]) - float(per_method["PCF_ON"]["Q_0_20"])
        out["delta_q_xy_minus_off_m"] = float(candidate["Q_0_20"]) - float(per_method["PCF_OFF"]["Q_0_20"])
        out["q_outcome_xy_vs_b"] = outcome(out["delta_q_xy_minus_b_m"])
        out["q_outcome_xy_vs_on"] = outcome(out["delta_q_xy_minus_on_m"])
        out["q_outcome_xy_vs_off"] = outcome(out["delta_q_xy_minus_off_m"])
        out["delta_rmse_z_xy_minus_on_0_20_m"] = float(candidate["RMSE_Z_0_20"]) - float(per_method["PCF_ON"]["RMSE_Z_0_20"])
        out["z_outcome_xy_vs_on"] = outcome(out["delta_rmse_z_xy_minus_on_0_20_m"])
        records.append(out)

    high = [row for row in records if row["band"] in {"W09_W11", "W12_W14"}]
    groups = {band: [row for row in records if row["band"] == band] for band in ("W09_W11", "W12_W14", "W15", "W00_W08")}
    mean = lambda rows, key: float(np.mean([float(row[key]) for row in rows]))
    def summarize(rows: list[dict[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {"n": len(rows)}
        for prefix in ("b", "on", "off", "xy"):
            result[f"mean_q_{prefix}_m"] = mean(rows, f"{prefix}_q_0_20_m")
            tilt_ticks = sum(int(row[f"{prefix}_tilt_limited_count"]) for row in rows)
            result[f"total_tilt_limited_ticks_{prefix}"] = tilt_ticks
            result[f"tilt_limited_fraction_{prefix}"] = float(tilt_ticks / (TILT_TICKS * len(rows)))
            for axis in "xyz":
                result[f"mean_rmse_{axis}_{prefix}_0_20_m"] = mean(rows, f"rmse_{axis}_{prefix}_0_20_m")
        result["total_new_tilt_limited_ticks_xy"] = sum(int(row["xy_new_tilt_limited_count"]) for row in rows)
        for ref in ("b", "on", "off"):
            delta = f"delta_q_xy_minus_{ref}_m"
            result[f"mean_q_xy_minus_{ref}_m"] = mean(rows, delta)
            result[f"q_outcomes_xy_vs_{ref}"] = {name: sum(r[f"q_outcome_xy_vs_{ref}"] == name for r in rows) for name in ("WIN", "TIE", "LOSS")}
        result["mean_delta_rmse_z_xy_minus_on_0_20_m"] = mean(rows, "delta_rmse_z_xy_minus_on_0_20_m")
        result["z_wins_xy_vs_on"] = sum(r["z_outcome_xy_vs_on"] == "WIN" for r in rows)
        return result
    summary_groups = {name: summarize(rows) for name, rows in groups.items()}
    summary_groups["W09_W14"] = summarize(high)
    summary_groups["ALL_12"] = summarize(records)
    high_xy = mean(high, "xy_q_0_20_m")
    gate1 = all(row["xy_status"] == "STABLE" and row["xy_last_transition"] == 20000 and row["xy_safe"]
                and row["xy_update_event_count"] > 0 and row["xy_motor_saturated_fraction"] == 0.0
                and row["xy_generalized_clipped_fraction"] == 0.0 and row["xy_new_tilt_limited_count"] == 0
                for row in records)
    gate2 = (high_xy < mean(high, "on_q_0_20_m") - TOL and high_xy < mean(high, "off_q_0_20_m") - TOL
             and high_xy <= mean(high, "b_q_0_20_m") + TOL)
    gate3 = sum(float(row["rmse_z_xy_0_20_m"]) < float(row["rmse_z_on_0_20_m"]) - TOL for row in high) >= 4
    gate4 = all(mean(groups[band], "xy_q_0_20_m") <= mean(groups[band], "b_q_0_20_m") + TOL for band in ("W15", "W00_W08"))
    gate5 = mean(records, "xy_q_0_20_m") < mean(records, "b_q_0_20_m") - TOL
    gates = {"all_12_stable_complete_finite_safe_identity_and_no_saturation": bool(gate1),
             "high_frequency_xy_q_below_on_and_off_and_not_worse_than_b": bool(gate2),
             "high_frequency_z_rmse_beats_on_in_at_least_4_of_6": bool(gate3),
             "w15_and_w00_w08_means_not_worse_than_b": bool(gate4),
             "all_12_macro_xy_q_strictly_below_b": bool(gate5)}
    passed = all(gates.values())
    summary = {"schema": "ROUND3_XY_PCF_SCREEN_RESULTS_V1", "status": "COMPLETE_12_SCENE_SCREEN",
               "metric_rows": len(records), "candidate": "DSSM14_PCF_XY", "eta_mask": [1, 1, 0],
               "q_comparison_tolerance_m": TOL, "groups": summary_groups, "registered_gates": gates,
               "registered_gate_pass": passed,
               "decision": "REQUEST_SEPARATE_72_SCENE_REVIEW" if passed else "SCREEN_NOT_PASSED_NO_72_NO_TUNING",
               "claim_limit": "The fixed 12-scene screen only decides whether to request a separate 72-scene review. It does not prove H3, theory, generalization, or TEST performance.",
               "theory_gate": "No full closed-loop ISS/UUB proof is established; empirical screening cannot repair that gap.",
               "test_accessed": False,
               "scoring_compatibility": {"locked_rescore_sha256": sha256(HERE / "rescore_round3.py"),
                                         "locked_raw_scan_sha256": LOCK["scoring_helper"]["sha256"],
                                         "compat_rescore_sha256": sha256(Path(__file__).resolve()),
                                         "compat_identity_verifier_sha256": sha256(verifier_path),
                                         "rmse_key_aliases": "RMSE_x/y/z_* -> RMSE_X/Y/Z_*"},
               "input_identity_audit": input_audit, "records": records}
    report_dir = HERE / "reports"
    with (report_dir / "round3_xy_screen_results.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    (report_dir / "round3_xy_screen_summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": summary["status"], "metric_rows": len(records), "registered_gates": gates,
                      "decision": summary["decision"]}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ROUND3_SCORE_FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
