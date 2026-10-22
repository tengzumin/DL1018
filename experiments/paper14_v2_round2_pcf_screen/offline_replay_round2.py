#!/usr/bin/env python3
"""Read-only same-record-state replay audit for Round 2 PCF logs.

This script reads the frozen PCF-on VAL raws referenced by R2 run_status.json,
reconstructs the deployed FEATURE-head update, and applies a PCF-off update to
the same recorded event states. It never runs the Plant and never writes to any
input file. Outputs are audit CSV/JSON files within the isolated R2 reports dir.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import h5py
import numpy as np


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RUNS = HERE / "runs"
REPORTS = HERE / "reports"
EXPECTED_SCENES = 12
TIME_WINDOWS = ((0.0, 5.0, "0_5s"), (5.0, 10.0, "5_10s"), (10.0, 20.0, "10_20s"))
TOL = 2e-12


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def arr(group: h5py.Group, name: str) -> np.ndarray:
    return np.asarray(group[name][()], dtype=np.float64)


def timeline(group: h5py.Group, name: str) -> np.ndarray:
    x = arr(group, name)
    return x.reshape(-1)


def vec3_t(group: h5py.Group, name: str) -> np.ndarray:
    x = arr(group, name)
    if x.ndim != 2 or x.shape[0] != 3:
        raise ValueError(f"{name}: expected MATLAB 3xN array, got {x.shape}")
    return x.T


def phase(scene: str) -> str:
    if "_W15" in scene:
        return "W15"
    if any(f"_W{i:02d}" in scene for i in range(9, 15)):
        return "W09_W14"
    return "W00_W08"


def checked_close(name: str, actual: np.ndarray, expected: np.ndarray, tol: float = TOL) -> float:
    if actual.shape != expected.shape:
        raise ValueError(f"{name}: shape mismatch {actual.shape} != {expected.shape}")
    if not (np.isfinite(actual).all() and np.isfinite(expected).all()):
        raise ValueError(f"{name}: nonfinite values in comparison")
    err = float(np.max(np.abs(actual - expected)))
    if not np.isfinite(err) or err > tol:
        raise ValueError(f"{name}: max abs error {err:.6g} > {tol:g}")
    return err


def same_path(a: str | Path, b: str | Path) -> bool:
    return os.path.normcase(os.path.abspath(str(a))) == os.path.normcase(os.path.abspath(str(b)))


def matlab_vector(text: str, pattern: str, label: str) -> np.ndarray:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        raise ValueError(f"locked default_config.m does not expose {label}")
    values = np.array([float(x) for x in re.findall(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", match.group(1))])
    if values.size == 0 or not np.isfinite(values).all():
        raise ValueError(f"could not parse finite {label} from locked source")
    return values


def matlab_text(group: h5py.Group, name: str) -> str:
    units = np.asarray(group[name][()]).reshape(-1, order="F").astype(np.uint16)
    return bytes(units.astype("<u2").tobytes()).decode("utf-16-le").rstrip("\x00")


def main() -> None:
    REPORTS.mkdir(exist_ok=True)
    frozen = json.loads((HERE / "frozen_inputs.json").read_text(encoding="utf-8"))
    frozen_sha = sha256(HERE / "frozen_inputs.json")
    if frozen_sha != "92bf5bb355e473360f4ea6023dc508ed7c5369733eb083dfe38b26e53bf6bd58":
        raise ValueError("Round 2 frozen input lock identity changed")
    helper_item = next(x for x in frozen["runtimeFiles"] if Path(x["path"]).name == "position_only_search_head_step.m")
    helper_path = Path(helper_item["path"])
    helper_hash = sha256(helper_path)
    if helper_hash != helper_item["sha256"]:
        raise ValueError("locked FEATURE update helper hash changed")
    helper_text = helper_path.read_text(encoding="utf-8")
    weight_bound_match = re.search(
        r"stateNext\s*=\s*max\(min\(unprojected,\s*([-+]?\d+(?:\.\d+)?)\),\s*-\s*([-+]?\d+(?:\.\d+)?)\)",
        helper_text,
    )
    if not weight_bound_match or float(weight_bound_match.group(1)) != float(weight_bound_match.group(2)):
        raise ValueError("locked FEATURE helper does not expose a symmetric scalar weight projection")
    weight_limit = float(weight_bound_match.group(1))
    support_sources = []
    for source_name in ("default_config.m", "controller_parameters.m", "position_bs_step.m",
                        "position_filter_realization_pcf_step_v3_5.m"):
        matches = [x for section in ("plantFiles", "runtimeFiles") for x in frozen[section]
                   if Path(x["path"]).name == source_name]
        if len(matches) != 1 or sha256(Path(matches[0]["path"])) != matches[0]["sha256"]:
            raise ValueError(f"locked support source identity failed: {source_name}")
        support_sources.append({"path": matches[0]["path"], "sha256": matches[0]["sha256"]})

    default_config_path = next(Path(x["path"]) for section in ("plantFiles", "runtimeFiles")
                               for x in frozen[section] if Path(x["path"]).name == "default_config.m")
    config_text = default_config_path.read_text(encoding="utf-8")
    dt_setting = matlab_vector(config_text, r"cfg\.plant\.dt\s*=\s*([^;]+);", "plant dt")
    k2 = matlab_vector(config_text, r"['\"]k2['\"]\s*,\s*\[([^\]]+)\]", "position k2")
    s_limit = matlab_vector(config_text, r"['\"]s_limit['\"]\s*,\s*\[([^\]]+)\]", "position surface limit")
    if dt_setting.size != 1 or not np.array_equal(k2, [4.0, 4.0, 4.0]) or not np.array_equal(s_limit, [7.0, 8.0, 10.0]):
        raise ValueError("locked source parameters differ from the audited replay equation")
    dt = float(dt_setting[0])
    event_dt = 1.0 / float(frozen["run"]["position_event_hz"])

    scene_list_item = frozen["scene_list"]
    scene_list_path = Path(scene_list_item["path"])
    if sha256(scene_list_path) != scene_list_item["sha256"]:
        raise ValueError("frozen 12-scene VAL list identity changed")
    frozen_scenes = frozen["scenes"]
    expected_scene_ids = [x["scene_id"] for x in frozen_scenes]
    if (len(expected_scene_ids) != EXPECTED_SCENES or len(set(expected_scene_ids)) != EXPECTED_SCENES or
            any(x.get("split") != "VAL" or "TEST" in x["scene_id"].upper() for x in frozen_scenes)):
        raise ValueError("frozen scene contract is not exactly 12 unique VAL scenes")
    scene_list_rows = list(csv.DictReader(scene_list_path.open(encoding="utf-8-sig", newline="")))
    if [r["scene_id"] for r in scene_list_rows] != expected_scene_ids:
        raise ValueError("frozen lock scene list and frozen_inputs.scenes disagree")

    results_path = REPORTS / "round2_screen_results.csv"
    result_rows = list(csv.DictReader(results_path.open(encoding="utf-8-sig", newline="")))
    result_by_scene = {r["scene_id"]: r for r in result_rows}
    if len(result_rows) != EXPECTED_SCENES or len(result_by_scene) != EXPECTED_SCENES or set(result_by_scene) != set(expected_scene_ids):
        raise ValueError("scored scenes do not exactly match the frozen 12-scene VAL list")
    frozen_meta = {x["scene_id"]: x for x in frozen_scenes}
    for scene, row in result_by_scene.items():
        if row["split"] != "VAL" or row["task"] != frozen_meta[scene]["task"]:
            raise ValueError(f"{scene}: score table split/task differs from frozen scene identity")
        if "TEST" in scene.upper():
            raise ValueError(f"TEST scene forbidden in offline replay: {scene}")

    rescore_items = {x["role"]: x for x in frozen["rescores"]}
    expected_raws: dict[str, dict[str, dict[str, str]]] = {"ON_CANDIDATE": {}, "B_BASELINE": {}}
    rescore_split_counts: dict[str, dict[str, int]] = {}
    for role, item in rescore_items.items():
        path = Path(item["path"])
        if sha256(path) != item["sha256"]:
            raise ValueError(f"frozen {role} rescore identity changed")
        rows = list(csv.DictReader(path.open(encoding="utf-8-sig", newline="")))
        if any(r.get("split") not in {"DEV", "VAL"} for r in rows):
            raise ValueError(f"{role}: rescore metadata contains a non-DEV/VAL row; refuse TEST scope")
        if any("TEST" in str(v).upper() for r in rows for k, v in r.items()
               if k in {"scene_id", "raw_path", "resolved_raw_path", "manifest_source_raw_path"}):
            raise ValueError(f"{role}: rescore metadata contains a TEST scene/path")
        rescore_split_counts[role] = {split: sum(r.get("split") == split for r in rows) for split in ("DEV", "VAL")}
        expected_raws[role] = {r["scene_id"]: r for r in rows if r["split"] == "VAL"}
    if not set(expected_scene_ids).issubset(expected_raws["ON_CANDIDATE"]) or not set(expected_scene_ids).issubset(expected_raws["B_BASELINE"]):
        raise ValueError("frozen raw rescore tables do not cover all 12 VAL scenes")

    all_event_rows: list[dict] = []
    scene_checks: list[dict] = []
    init_weights: list[np.ndarray] = []
    event_n_total = 0
    maximums: dict[str, float] = defaultdict(float)

    for scene in expected_scene_ids:
        status_path = RUNS / scene / "attempt_01" / "run_status.json"
        status = json.loads(status_path.read_text(encoding="utf-8"))
        ident = status["input_identity"]
        on_path = Path(ident["on_raw_path"])
        expected_on = expected_raws["ON_CANDIDATE"][scene]
        expected_b = expected_raws["B_BASELINE"][scene]
        if any("TEST" in str(v).upper() for v in (scene, on_path, expected_on["raw_path"], expected_b["resolved_raw_path"])):
            raise ValueError(f"{scene}: TEST path or scene rejected")
        if not same_path(on_path, expected_on["raw_path"]):
            raise ValueError(f"{scene}: PCF-on raw path differs from frozen candidate rescore")
        if (expected_on["raw_sha256_expected"] != expected_on["raw_sha256_before"] or
                expected_on["raw_sha256_before"] != expected_on["raw_sha256_after"]):
            raise ValueError(f"{scene}: frozen candidate raw rescore hash is not stable")
        if not same_path(ident["b_raw_path"], expected_b["resolved_raw_path"]):
            raise ValueError(f"{scene}: B raw path differs from frozen baseline rescore")
        if (expected_b["resolved_raw_sha256_expected"] != expected_b["raw_sha256_before"] or
                expected_b["raw_sha256_before"] != expected_b["raw_sha256_after"]):
            raise ValueError(f"{scene}: frozen B raw rescore hash is not stable")
        if ident.get("frozen_inputs_path") and not same_path(ident["frozen_inputs_path"], HERE / "frozen_inputs.json"):
            raise ValueError(f"{scene}: run status points at another frozen input lock")
        if ident["frozen_inputs_sha256"] != frozen_sha or status["frozen_inputs_sha256"] != frozen_sha:
            raise ValueError(f"{scene}: frozen input lock hash mismatch")
        for status_key, frozen_value in (
            ("model_mat_sha256", frozen["model"]["mat_sha256"]),
            ("model_binding_sha256", frozen["model_binding"]["sha256"]),
            ("normalizer_npz_sha256", frozen["normalizer"]["npz_file_sha256"]),
            ("normalizer_report_sha256", frozen["normalizer"]["train_only_report_sha256"]),
            ("normalizer_arrays_identity_sha256", frozen["normalizer"]["actual_runner_arrays_identity_sha256"]),
            ("W0_output_W_sha256", frozen["model"]["w0_output_W_double_f_order_sha256"]),
            ("scene_payload_identity_csv_sha256", frozen["scene_payload_identity"]["sha256"]),
        ):
            if status.get(status_key) != frozen_value or ident.get(status_key) != frozen_value:
                raise ValueError(f"{scene}: {status_key} does not match frozen input lock")
        if (status.get("b_raw_sha256") != expected_b["resolved_raw_sha256_expected"] or
                ident.get("b_raw_sha256") != expected_b["resolved_raw_sha256_expected"]):
            raise ValueError(f"{scene}: B raw hash differs from frozen baseline rescore")
        b_path = Path(ident["b_raw_path"])
        b_hash_actual = sha256(b_path)
        if (b_hash_actual != expected_b["resolved_raw_sha256_expected"] or
                b_hash_actual != status.get("b_raw_sha256") or b_hash_actual != ident.get("b_raw_sha256")):
            raise ValueError(f"{scene}: actual B raw file SHA differs from frozen rescore/status")
        on_hash = sha256(on_path)
        if (on_hash != ident["on_raw_sha256"] or on_hash != status["on_raw_sha256"] or
                on_hash != expected_on["raw_sha256_expected"] or on_hash != expected_on["raw_sha256_before"]):
            raise ValueError(f"{scene}: PCF-on raw identity/hash mismatch")
        run_start_path = status_path.parent / "run_start.mat"
        if sha256(run_start_path) != status["run_start_sha256"]:
            raise ValueError(f"{scene}: run_start identity/hash mismatch")
        if status["scene_id"] != scene or status["head_type"] != "FEATURE" or not status["update_enabled"] or not status["pcf_enabled"] is False:
            raise ValueError(f"{scene}: R2 OFF status does not match frozen arm contract")

        with h5py.File(on_path, "r") as f:
            g = f["log"]
            source_scene_id = matlab_text(f["meta"], "source_scene_id")
            if source_scene_id != scene or "TEST" in source_scene_id.upper():
                raise ValueError(f"{scene}: raw internal source_scene_id mismatch or TEST identity")
            pcf_flag = int(np.asarray(g["stage1_position_pcf_coordination_enabled"][()]).reshape(-1)[0])
            update_flag = int(np.asarray(g["stage1_position_update_enabled"][()]).reshape(-1)[0])
            head_flag = np.asarray(g["stage1_position_search_head_type"][()]).reshape(-1).astype(int)
            head_type = "".join(chr(int(z)) for z in head_flag)
            if pcf_flag != 1 or update_flag != 1 or head_type != "FEATURE":
                raise ValueError(f"{scene}: ON raw head/update/PCF flags disagree: {head_type}/{update_flag}/{pcf_flag}")

            steps = timeline(g, "stage1_position_event_step_index").astype(int)
            ix = steps - 1  # MATLAB event step index is 1-based.
            n = len(ix)
            transition_time = timeline(g, "transition_time")
            if (not np.isfinite(transition_time).all() or len(transition_time) != 20000 or
                    not np.allclose(np.diff(transition_time), dt, rtol=0, atol=1e-12) or
                    not np.allclose(transition_time, np.arange(len(transition_time)) * dt, rtol=0, atol=1e-12)):
                raise ValueError(f"{scene}: transition_time does not match locked Plant clock")
            if n != 1968 or np.any(ix < 0) or np.any(ix >= len(transition_time)) or np.any(np.diff(ix) <= 0):
                raise ValueError(f"{scene}: event index integrity failed (n={n})")
            event_n_total += n

            phi = arr(g, "stage1_position_event_phi_33").T[ix]
            wb_raw = arr(g, "stage1_position_event_weight_before_33x3")
            wa_raw = arr(g, "stage1_position_event_weight_after_33x3")
            if wb_raw.shape != (n, 3, 33) or wa_raw.shape != (n, 3, 33):
                raise ValueError(f"{scene}: unexpected MATLAB weight event dimensions {wb_raw.shape}/{wa_raw.shape}")
            wb = np.transpose(wb_raw, (0, 2, 1))
            wa = np.transpose(wa_raw, (0, 2, 1))
            init_weights.append(wb[0].copy())

            surface = vec3_t(g, "stage1_position_pcf_event_s_original_mps")[ix]
            eta_event = vec3_t(g, "stage1_position_pcf_event_eta_before_mps")[ix]
            coord_logged = vec3_t(g, "stage1_position_pcf_event_s_coord_mps")[ix]
            eff_logged = vec3_t(g, "stage1_position_pcf_event_s_coord_eff_mps")[ix]
            eta_timeline = vec3_t(g, "stage1_position_pcf_eta_before_mps")
            eta_after = vec3_t(g, "stage1_position_pcf_eta_after_mps")
            a_req = vec3_t(g, "stage1_position_pcf_a_req_mps2")
            a_f = vec3_t(g, "stage1_position_pcf_a_f_mps2")
            r_f = vec3_t(g, "stage1_position_pcf_r_f_mps2")
            feature = arr(g, "stage1_position_feature_14").T
            gamma = float(np.asarray(g["stage1_position_search_gamma"][()]).reshape(-1)[0])
            dt_event = timeline(g, "stage1_position_effective_update_dt_s")[ix]
            beta = timeline(g, "stage1_position_event_beta")[ix]
            logged_raw = vec3_t(g, "stage1_position_event_raw_acceleration_mps2")[ix]
            logged_applied = vec3_t(g, "stage1_position_event_applied_acceleration_mps2")[ix]

            event_arrays = (steps, phi, wb, wa, surface, eta_event, coord_logged, eff_logged,
                            eta_timeline[ix], eta_after[ix], a_req[ix], a_f[ix], r_f[ix],
                            feature[ix], dt_event, beta, logged_raw, logged_applied)
            if not all(np.isfinite(x).all() for x in event_arrays):
                raise ValueError(f"{scene}: nonfinite event payload")
            if not all(np.isfinite(x).all() for x in (eta_timeline, eta_after, a_req, a_f, r_f)):
                raise ValueError(f"{scene}: nonfinite PCF timeline payload")
            if not np.allclose(dt_event, event_dt, rtol=0, atol=1e-12):
                raise ValueError(f"{scene}: effective update interval differs from locked cadence")

            # Check the complete PCF residual/integrator recursion at every 1-ms step.
            err_rf = checked_close(f"{scene}: r_f=a_req-a_f", r_f, a_req - a_f)
            err_eta_initial = checked_close(f"{scene}: initial eta is zero", eta_timeline[0], np.zeros(3))
            err_eta_continuity = checked_close(f"{scene}: eta state is continuous across steps",
                                               eta_timeline[1:], eta_after[:-1])
            dt_all = np.diff(transition_time, prepend=transition_time[0] - dt)
            decay = np.exp(-dt_all[:, None] * k2[None, :])
            integral = -np.expm1(-dt_all[:, None] * k2[None, :]) / k2[None, :]
            eta_expected = decay * eta_timeline + integral * r_f
            err_eta = checked_close(f"{scene}: eta exact discrete recurrence", eta_after, eta_expected)
            err_event_eta = checked_close(f"{scene}: event eta timestamp", eta_event, eta_timeline[ix])

            coord = surface - eta_event
            err_coord = checked_close(f"{scene}: s_coord=surface-eta_before", coord_logged, coord)
            eff = np.clip(coord, -s_limit, s_limit)
            err_eff = checked_close(f"{scene}: s_eff clip", eff_logged, eff)
            err_surface_feature = checked_close(f"{scene}: surface matches feature [4:7]", surface, feature[ix, 3:6])

            # Replay the actual output-then-update rule from the locked FEATURE helper.
            raw_replay = np.einsum("nbo,nb->no", wb, phi)
            err_raw = checked_close(f"{scene}: output uses W_before", logged_raw, raw_replay)
            w_on_replay = np.clip(
                wb + dt_event[:, None, None] * (
                    -gamma * beta[:, None, None] * phi[:, :, None] * eff[:, None, :] - 0.002 * wb
                ), -weight_limit, weight_limit,
            )
            err_w_update = checked_close(f"{scene}: PCF-on update equation", wa, w_on_replay)
            unprojected_on = wb + dt_event[:, None, None] * (
                -gamma * beta[:, None, None] * phi[:, :, None] * eff[:, None, :] - 0.002 * wb
            )
            projection_count = int(np.count_nonzero(np.any(np.abs(unprojected_on) > weight_limit, axis=(1, 2))))

            # Confirm no output cap is active on the measured ON events; this lets us
            # compare raw head predictions without relying on an unlocked dmax value.
            output_beta = beta[:, None]
            output_linear_error = float(np.max(np.abs(logged_applied - output_beta * logged_raw)))
            if output_linear_error > TOL:
                raise ValueError(f"{scene}: ON output cap appears active or output scaling differs ({output_linear_error:g})")

            # Counterfactual, same-state replay: the logged ON surface/phi sequence is
            # held fixed while an otherwise identical PCF-off weight recursion evolves.
            # This is local mechanism evidence, not a closed-loop outcome estimate.
            w_off = wb[0].copy()
            on_raw_local = np.empty((n, 3))
            off_raw_local = np.empty((n, 3))
            off_minus_on_surface = np.clip(surface, -s_limit, s_limit) - eff
            update_signal_cos = np.full((n, 3), np.nan)
            same_state_delta_dw_norm = np.zeros((n, 3))
            for j in range(n):
                on_before_err = float(np.max(np.abs(wb[j] - (wb[0] if j == 0 else wa[j - 1]))))
                if j and on_before_err > TOL:
                    raise ValueError(f"{scene}: recorded PCF-on weights are not sequential at event {j}")
                on_raw_local[j] = wb[j].T @ phi[j]
                off_raw_local[j] = w_off.T @ phi[j]
                on_s_eff = eff[j]
                off_s_eff = np.clip(surface[j], -s_limit, s_limit)
                # Compare the two update signals at the same recorded W. This
                # isolates the PCF surface term; the leak term is identical.
                grad_on_same_w = -gamma * beta[j] * np.outer(phi[j], on_s_eff) - 0.002 * wb[j]
                grad_off_same_w = -gamma * beta[j] * np.outer(phi[j], off_s_eff) - 0.002 * wb[j]
                for ax in range(3):
                    a = grad_on_same_w[:, ax]
                    b = grad_off_same_w[:, ax]
                    denom = np.linalg.norm(a) * np.linalg.norm(b)
                    if denom > 0:
                        update_signal_cos[j, ax] = float(np.dot(a, b) / denom)
                    same_state_delta_dw_norm[j, ax] = float(dt_event[j] * np.linalg.norm(b - a))
                grad_off_counterfactual = -gamma * beta[j] * np.outer(phi[j], off_s_eff) - 0.002 * w_off
                w_off = np.clip(w_off + dt_event[j] * grad_off_counterfactual, -weight_limit, weight_limit)

            err_on_local = checked_close(f"{scene}: local replay PCF-on raw", on_raw_local, logged_raw)
            e0 = feature[ix, :3]
            relative = np.abs(surface) > 1e-12
            flips = (np.sign(surface) != np.sign(coord)) & relative
            clip_on = np.abs(coord) > s_limit
            clip_off = np.abs(surface) > s_limit
            event_times = transition_time[ix]

            scene_checks.append({
                "scene_id": scene,
                "band": phase(scene),
                "on_raw_path": str(on_path),
                "on_raw_sha256": on_hash,
                "b_raw_path": ident["b_raw_path"],
                "b_raw_sha256": b_hash_actual,
                "frozen_inputs_sha256": frozen_sha,
                "raw_internal_source_scene_id": source_scene_id,
                "run_start_sha256": status["run_start_sha256"],
                "events": n,
                "head_type": head_type,
                "gamma": gamma,
                "first_event_t_s": float(event_times[0]),
                "last_event_t_s": float(event_times[-1]),
                "max_abs_r_f_identity_error_mps2": err_rf,
                "max_abs_initial_eta_error_mps": err_eta_initial,
                "max_abs_eta_state_continuity_error_mps": err_eta_continuity,
                "max_abs_eta_recurrence_error_mps": err_eta,
                "max_abs_eta_event_timestamp_error_mps": err_event_eta,
                "max_abs_surface_feature_identity_error_mps": err_surface_feature,
                "max_abs_coord_identity_error_mps": err_coord,
                "max_abs_s_eff_clip_error_mps": err_eff,
                "max_abs_output_before_update_error_mps2": err_raw,
                "max_abs_weight_update_replay_error": err_w_update,
                "max_abs_local_on_output_replay_error_mps2": err_on_local,
                "output_cap_or_beta_residual_mps2": output_linear_error,
                "weight_projection_events": projection_count,
                "surface_eta_sign_flip_fraction_axis_xyz": [
                    float(flips[:, ax].sum() / max(1, relative[:, ax].sum())) for ax in range(3)
                ],
                "eta_surface_abs_ratio_median_axis_xyz": [
                    float(np.median(np.abs(eta_event[relative[:, ax], ax] / surface[relative[:, ax], ax])))
                    if relative[:, ax].any() else 0.0 for ax in range(3)
                ],
                "actual_on_position_error_rmse_m_axis_xyz": [float(np.sqrt(np.mean(e0[:, ax] ** 2))) for ax in range(3)],
                "offline_counterfactual_raw_head_rms_delta_mps2_axis_xyz": [
                    float(np.sqrt(np.mean((off_raw_local[:, ax] - on_raw_local[:, ax]) ** 2))) for ax in range(3)
                ],
                "offline_counterfactual_raw_head_signed_mean_delta_mps2_axis_xyz": [
                    float(np.mean(off_raw_local[:, ax] - on_raw_local[:, ax])) for ax in range(3)
                ],
            })

            for t0, t1, label in TIME_WINDOWS:
                take = (event_times >= t0) & (event_times < t1)
                if not take.any():
                    continue
                for ax, axis in enumerate("xyz"):
                    active = relative[take, ax]
                    ratio = np.abs(eta_event[take, ax][active] / surface[take, ax][active]) if active.any() else np.array([])
                    c = update_signal_cos[take, ax]
                    c = c[np.isfinite(c)]
                    all_event_rows.append({
                        "scene_id": scene,
                        "band": phase(scene),
                        "time_window": label,
                        "axis": axis,
                        "events": int(take.sum()),
                        "surface_rms_mps": float(np.sqrt(np.mean(surface[take, ax] ** 2))),
                        "eta_rms_mps": float(np.sqrt(np.mean(eta_event[take, ax] ** 2))),
                        "off_minus_on_s_eff_rms_mps": float(np.sqrt(np.mean(off_minus_on_surface[take, ax] ** 2))),
                        "eta_abs_surface_ratio_median": float(np.median(ratio)) if ratio.size else math.nan,
                        "surface_eta_sign_flip_fraction": float(flips[take, ax].sum() / max(1, active.sum())),
                        "pcf_on_surface_clip_fraction": float(clip_on[take, ax].mean()),
                        "pcf_off_surface_clip_fraction": float(clip_off[take, ax].mean()),
                        "same_W_update_gradient_cosine_mean": float(np.mean(c)) if c.size else math.nan,
                        "offline_off_minus_on_raw_head_rms_mps2": float(np.sqrt(np.mean((off_raw_local[take, ax] - on_raw_local[take, ax]) ** 2))),
                        "offline_off_minus_on_raw_head_signed_mean_mps2": float(np.mean(off_raw_local[take, ax] - on_raw_local[take, ax])),
                        "same_state_update_delta_difference_rms": float(np.sqrt(np.mean(same_state_delta_dw_norm[take, ax] ** 2))),
                    })

            for key, value in {
                "max_abs_r_f_identity_error_mps2": err_rf,
                "max_abs_initial_eta_error_mps": err_eta_initial,
                "max_abs_eta_state_continuity_error_mps": err_eta_continuity,
                "max_abs_eta_recurrence_error_mps": err_eta,
                "max_abs_eta_event_timestamp_error_mps": err_event_eta,
                "max_abs_surface_feature_identity_error_mps": err_surface_feature,
                "max_abs_coord_identity_error_mps": err_coord,
                "max_abs_s_eff_clip_error_mps": err_eff,
                "max_abs_output_before_update_error_mps2": err_raw,
                "max_abs_weight_update_replay_error": err_w_update,
                "max_abs_local_on_output_replay_error_mps2": err_on_local,
            }.items():
                maximums[key] = max(maximums[key], value)

    if len(scene_checks) != EXPECTED_SCENES:
        raise ValueError(f"completed {len(scene_checks)} scenes, expected {EXPECTED_SCENES}")
    init_max = max(float(np.max(np.abs(w - init_weights[0]))) for w in init_weights)
    if init_max > TOL:
        raise ValueError(f"W0 differs across scenes: max error {init_max:g}")

    timing_path = REPORTS / "round2_same_state_replay_by_scene_window_axis.csv"
    with timing_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_event_rows[0]))
        writer.writeheader()
        writer.writerows(all_event_rows)
    report = {
        "audit_id": "DL1018_R2_PCF_SAME_STATE_OFFLINE_REPLAY_V1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "read-only same-record-state replay; no Plant execution; no TEST access",
        "interpretation_limit": "PCF-off counterfactual uses the PCF-on logged states/features; it identifies local update-law effects, not a closed-loop causal outcome or tracking improvement.",
        "equations": {
            "position_surface": "z2 = v_ref + k1*(p_ref-p) - v, units m/s",
            "pcf_residual": "r_f = a_req - a_f, units m/s^2",
            "pcf_eta_step": "eta[k+1]=exp(-k2*dt)*eta[k]+(1-exp(-k2*dt))/k2*r_f[k], k2=[4,4,4] 1/s, eta units m/s",
            "head_signal": "s_coord=surface-eta_before; s_eff=clip(s_coord, +/-[7,8,10] m/s); surface equals MATLAB position feature(4:6)",
            "feature_update": "W_next=clip(W+dt*(-gamma*beta*phi*s_eff^T-0.002*W), +/-60), output is W_before^T*phi",
            "counterfactual": "same phi/surface/eta samples, recursively evolve a PCF-off W; no plant/state feedback is replayed",
        },
        "locked_update_helper": {"path": str(helper_path), "sha256": helper_hash},
        "locked_support_sources": support_sources,
        "locked_source_parameters": {"plant_dt_s": dt, "event_dt_s": event_dt,
                                      "position_k2_per_s": k2.tolist(), "surface_limit_mps": s_limit.tolist(),
                                      "feature_weight_projection": [-weight_limit, weight_limit]},
        "frozen_input_lock_sha256": frozen_sha,
        "frozen_scene_list_sha256": scene_list_item["sha256"],
        "frozen_on_rescore_sha256": rescore_items["ON_CANDIDATE"]["sha256"],
        "frozen_b_rescore_sha256": rescore_items["B_BASELINE"]["sha256"],
        "frozen_rescore_split_counts_checked": rescore_split_counts,
        "test_scope_guard": "Both frozen rescore manifests are asserted to contain only DEV/VAL rows and no TEST scene/path; only the frozen VAL scene IDs are used for raw access.",
        "source_units_note": "[7,8,10] limits the position surface in m/s. It is not an acceleration limit; the taskbook's one sentence labeling it m/s^2 is a documentation-unit error.",
        "scene_count": len(scene_checks),
        "event_count": event_n_total,
        "common_W0_max_abs_identity_error": init_max,
        "maximum_errors": dict(maximums),
        "scene_checks": scene_checks,
        "grouped_window_axis_csv": timing_path.name,
    }
    out = REPORTS / "round2_same_state_replay_audit.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    print(json.dumps({
        "report": str(out),
        "csv": str(timing_path),
        "scene_count": len(scene_checks),
        "event_count": event_n_total,
        "common_W0_max_abs_identity_error": init_max,
        "maximum_errors": dict(maximums),
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
