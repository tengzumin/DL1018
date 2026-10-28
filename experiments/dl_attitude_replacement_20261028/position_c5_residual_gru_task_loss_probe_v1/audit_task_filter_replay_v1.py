#!/usr/bin/env python3
"""Read-only TRAIN C5 task-command/filter replay and differentiability probe.

This validates the command path only. It deliberately does not fit a model: the
available TRAIN24 C5 raws use the older attitude-RBF backbone, while the
residual-GRU pilot's parent uses the cosine-GRU backbone.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import h5py
import numpy as np
import torch
from scipy.spatial.transform import Rotation


ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "reports/position_c5_train24_causal_dataset_v1"
DATA = DATA_DIR / "dataset/C5_TRAIN24_POSITION_CAUSAL_PAIRS_v1.npz"
MANIFEST = DATA_DIR / "C5_TRAIN24_POSITION_CAUSAL_MANIFEST_v1.json"
OUT = Path(__file__).resolve().parent
JSON_OUT = OUT / "TASK_FILTER_REPLAY_AUDIT_v1.json"
MD_OUT = OUT / "TASK_FILTER_REPLAY_AUDIT_v1.md"
DT = 0.001
EVENT_DT = 0.01
G = 9.8
MAX_TILT = math.pi / 6


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def matlab_char(x: np.ndarray) -> str:
    return "".join(chr(int(c)) for c in x.reshape(-1) if int(c) != 0)


def wrap(x: np.ndarray) -> np.ndarray:
    return np.arctan2(np.sin(x), np.cos(x))


def force_to_euler(acc: np.ndarray, adapter_yaw: np.ndarray, gravity: float,
                   max_tilt: float, output_yaw: np.ndarray | None = None) -> np.ndarray:
    specific = acc.copy()
    specific[:, 2] += gravity
    c, s = np.cos(adapter_yaw), np.sin(adapter_yaw)
    a = c * specific[:, 0] + s * specific[:, 1]
    b = s * specific[:, 0] - c * specific[:, 1]
    roll = np.arctan2(b, np.hypot(specific[:, 2], a))
    pitch = np.arctan2(a, specific[:, 2])
    tilt = np.hypot(roll, pitch)
    scale = np.minimum(1.0, max_tilt / np.maximum(tilt, np.finfo(float).eps))
    return np.column_stack((roll * scale, pitch * scale,
                            adapter_yaw if output_yaw is None else output_yaw))


def replay_filter(target: np.ndarray, initial_euler: np.ndarray,
                  wn: np.ndarray, damping: np.ndarray,
                  acceleration_limit: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    euler = initial_euler.astype(np.float64).copy()
    rate = np.zeros(3, dtype=np.float64)
    output = np.empty_like(target, dtype=np.float64)
    requested_acc = np.empty_like(target, dtype=np.float64)
    applied_acc = np.empty_like(target, dtype=np.float64)
    for i in range(len(target)):
        output[i] = euler
        error = wrap(target[i] - euler)
        req = wn * wn * error - 2.0 * damping * wn * rate
        requested_acc[i] = req
        applied_acc[i] = np.clip(req, -acceleration_limit, acceleration_limit)
        rate = rate + DT * applied_acc[i]
        euler = wrap(euler + DT * rate)
    return output, applied_acc, requested_acc


def quat_xyz(e: torch.Tensor) -> torch.Tensor:
    r, p, y = e.unbind(-1)
    cr, sr = torch.cos(r / 2), torch.sin(r / 2)
    cp, sp = torch.cos(p / 2), torch.sin(p / 2)
    cy, sy = torch.cos(y / 2), torch.sin(y / 2)
    return torch.stack((cr * cp * cy + sr * sp * sy,
                        sr * cp * cy - cr * sp * sy,
                        cr * sp * cy + sr * cp * sy,
                        cr * cp * sy - sr * sp * cy), dim=-1)


def quat_mul(a: torch.Tensor, b: torch.Tensor) -> torch.Tensor:
    aw, ax, ay, az = a.unbind(-1)
    bw, bx, by, bz = b.unbind(-1)
    return torch.stack((aw * bw - ax * bx - ay * by - az * bz,
                        aw * bx + ax * bw + ay * bz - az * by,
                        aw * by - ax * bz + ay * bw + az * bx,
                        aw * bz + ax * by - ay * bx + az * bw), dim=-1)


def torch_force_to_euler(acc: torch.Tensor, adapter_yaw: torch.Tensor,
                         gravity: float, max_tilt: float,
                         output_yaw: torch.Tensor | None = None) -> torch.Tensor:
    z = acc[..., 2] + gravity
    a = torch.cos(adapter_yaw) * acc[..., 0] + torch.sin(adapter_yaw) * acc[..., 1]
    b = torch.sin(adapter_yaw) * acc[..., 0] - torch.cos(adapter_yaw) * acc[..., 1]
    roll = torch.atan2(b, torch.hypot(z, a))
    pitch = torch.atan2(a, z)
    tilt = torch.hypot(roll, pitch)
    scale = torch.minimum(torch.ones_like(tilt), max_tilt / tilt.clamp_min(1e-12))
    yaw_out = adapter_yaw if output_yaw is None else output_yaw
    return torch.stack((roll * scale, pitch * scale, yaw_out), dim=-1)


def differentiable_segment_check(raw_path: Path, scene_id: str) -> dict:
    """One event perturbation verifies task-SO3 loss has a finite gradient."""
    with h5py.File(raw_path, "r") as f:
        g = f["log"]
        state = np.asarray(g["state"][:], dtype=np.float64).T
        nominal = np.asarray(g["position_nominal_acceleration_mps2"][:], dtype=np.float64).T
        applied = np.asarray(g["position_compensation_applied_acceleration_mps2"][:], dtype=np.float64).T
        initial = np.asarray(g["filtered_attitude_reference"][:, 300], dtype=np.float64)
        initial_rate = np.asarray(g["filtered_attitude_rate"][:, 300], dtype=np.float64)
        time = np.asarray(g["transition_time"][:], dtype=np.float64).reshape(-1)
        ref = f["scene/reference"]
        ref_acc = np.asarray(ref["acceleration"][:], dtype=np.float64).T
        ref_yaw = np.asarray(ref["yaw"][:], dtype=np.float64).reshape(-1)
        event = np.asarray(g["position_event_flag"][:], dtype=bool).reshape(-1)
        event_applied = applied[event]
        event_time = time[event]
        start, stop = 300, 500
        all_event_indices = np.flatnonzero(event)
        event_ordinal = 31  # first event after the fixed 31-event warmup
        event_index = int(all_event_indices[event_ordinal])
        if not (start <= event_index < stop):
            raise RuntimeError("Ready event lies outside the differentiability segment")
        base_event = float(event_time[event_ordinal])
        base_action = event_applied[event_ordinal]
        limit = np.array([3.0, 3.0, 3.0])
        beta = min(max(base_event / 1.8, 0.0), 1.0)
        wn = np.array([18.0, 18.0, 12.0])
        damping = np.ones(3)
        acc_limit = np.array([np.inf, np.inf, 6.0])

        # Start at the logged filter state immediately before the perturbed event.
        phi = torch.zeros(3, dtype=torch.float64, requires_grad=True)
        action_seq = torch.as_tensor(applied[start:stop], dtype=torch.float64).clone()
        corrected_event = torch.clamp(torch.as_tensor(base_action, dtype=torch.float64) +
                                      beta * torch.clamp(phi, -0.5, 0.5), -3.0, 3.0)
        local_event = event_index - start
        action_seq[local_event:local_event + 10] = corrected_event
        yaw = torch.as_tensor(state[start:stop, 8], dtype=torch.float64)
        cmd_acc = torch.as_tensor(nominal[start:stop], dtype=torch.float64) - action_seq
        target = torch_force_to_euler(cmd_acc, yaw, G, MAX_TILT,
                                      torch.as_tensor(ref_yaw[start:stop], dtype=torch.float64))

        euler = torch.as_tensor(initial, dtype=torch.float64)
        rate = torch.as_tensor(initial_rate, dtype=torch.float64)
        wn_t = torch.as_tensor(wn, dtype=torch.float64)
        damping_t = torch.as_tensor(damping, dtype=torch.float64)
        limit_t = torch.as_tensor(acc_limit, dtype=torch.float64)
        filt = []
        for i in range(stop - start):
            filt.append(euler)
            err = torch.atan2(torch.sin(target[i] - euler), torch.cos(target[i] - euler))
            req = wn_t.square() * err - 2.0 * damping_t * wn_t * rate
            accf = torch.maximum(torch.minimum(req, limit_t), -limit_t)
            rate = rate + DT * accf
            euler = torch.atan2(torch.sin(euler + DT * rate), torch.cos(euler + DT * rate))
        filt_t = torch.stack(filt)
        task = torch_force_to_euler(
            torch.as_tensor(ref_acc[start:stop], dtype=torch.float64),
            torch.as_tensor(ref_yaw[start:stop], dtype=torch.float64), G, MAX_TILT)
        q_task = quat_xyz(task)
        q_filt = quat_xyz(filt_t)
        q_conj = q_task * torch.tensor([1., -1., -1., -1.], dtype=torch.float64)
        q_rel = quat_mul(q_conj, q_filt)
        angle = 2.0 * torch.atan2(torch.linalg.vector_norm(q_rel[:, 1:], dim=-1),
                                  q_rel[:, 0].abs().clamp_min(1e-15))
        loss = angle.square().mean()
        grad = torch.autograd.grad(loss, phi)[0]
        return {"scene_id": scene_id, "segment_transition_indices_0based": [start, stop - 1],
                "perturbed_event_time_s": base_event, "task_loss_so3_squared_rad2": float(loss.detach()),
                "gradient_wrt_event_delta_mps2": grad.detach().tolist(),
                "gradient_norm": float(torch.linalg.vector_norm(grad).detach()),
                "finite_nonzero_gradient": bool(torch.isfinite(grad).all() and
                                                torch.linalg.vector_norm(grad) > 1e-14),
                "segment_only_autograd_smoke_check": True}


def main() -> None:
    if JSON_OUT.exists() or MD_OUT.exists():
        raise RuntimeError("Refusing to overwrite existing audit outputs")
    if sha(DATA).lower() != json.loads(MANIFEST.read_text(encoding="utf-8"))["data_sha256"].lower():
        raise RuntimeError("TRAIN causal NPZ hash mismatch")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("scope", {}).get("TEST_accessed") is not False or manifest.get("scope", {}).get("Plant_calls") != 0:
        raise RuntimeError("Existing TRAIN dataset scope lock failed")
    with np.load(DATA, allow_pickle=False) as z:
        ids = z["scene_ids"].astype(str).tolist()
        event_times = z["event_time_s"].astype(np.float64)
        x14 = z["x14_model_input"]
        ready = z["ready_mask"].astype(bool)
        event_actions = z["applied_acceleration_event_mps2"].astype(np.float64)
    if (len(ids) != 24 or x14.shape != (24, 1999, 14) or ready.shape != (24, 1999) or
            event_actions.shape != (24, 1999, 3)):
        raise RuntimeError("Unexpected TRAIN24 fixed dataset schema")

    per_scene = []
    gradient_scene = None
    for rec in manifest["scenes"]:
        sid = rec["scene_id"]
        if sid not in ids:
            raise RuntimeError(f"Unexpected non-TRAIN scene: {sid}")
        raw_path = ROOT / rec["raw_path"]
        status_path = ROOT / rec["status_path"]
        run_start_path = ROOT / rec["run_start_path"]
        for p, expected, name in ((raw_path, rec["raw_sha256"], "raw"),
                                  (status_path, rec["status_sha256"], "status"),
                                  (run_start_path, rec["run_start_sha256"], "run-start")):
            if sha(p).lower() != expected.lower():
                raise RuntimeError(f"{sid}: {name} hash mismatch")
        status = json.loads(status_path.read_text(encoding="utf-8"))
        if (status.get("status") != "RUN_COMPLETE_STABLE" or status.get("canonical_scene_id") != sid or
                status.get("transitions") != 20000 or status.get("state_samples") != 20001 or
                status.get("safety_stop_reason") or status.get("TEST_accessed") is not False or
                status.get("training_steps") != 0 or status.get("optimizer_steps") != 0 or
                status.get("raw_sha256", "").lower() != rec["raw_sha256"].lower()):
            raise RuntimeError(f"{sid}: raw/status/safety/source binding failed")

        with h5py.File(run_start_path, "r") as fs:
            rs = fs["runStart"]
            release_sha = matlab_char(np.asarray(rs["release_sha256"][()]))
            source_scene = matlab_char(np.asarray(rs["source_runtime_scene_id"][()]))
            wn = np.asarray(rs["cfg/control/command_filter/wn"][()], dtype=np.float64).reshape(-1)
            damping = np.asarray(rs["cfg/control/command_filter/damping"][()], dtype=np.float64).reshape(-1)
            acc_limit = np.asarray(rs["cfg/control/command_filter/acceleration_limit"][()], dtype=np.float64).reshape(-1)
            gravity = float(rs["cfg/plant/g"][()][0, 0])
            max_tilt = float(rs["cfg/control/limits/max_tilt"][()][0, 0])
        status_source_scene = status.get("source_runtime_scene_id", sid)
        if (release_sha.lower() != status["release_sha256"].lower() or
                source_scene != status_source_scene or not source_scene.startswith(sid)):
            raise RuntimeError(f"{sid}: run-start release/source identity mismatch")
        if not np.allclose(wn, [18, 18, 12]) or not np.allclose(damping, [1, 1, 1]) or not np.array_equal(acc_limit[:2], [np.inf, np.inf]) or acc_limit[2] != 6:
            raise RuntimeError(f"{sid}: unexpected per-run command-filter configuration")
        if abs(gravity - G) > 1e-12 or abs(max_tilt - MAX_TILT) > 1e-12:
            raise RuntimeError(f"{sid}: unexpected gravity/tilt constants")

        with h5py.File(raw_path, "r") as f:
            g = f["log"]
            state = np.asarray(g["state"][()], dtype=np.float64).T
            time = np.asarray(g["transition_time"][()], dtype=np.float64).reshape(-1)
            nominal = np.asarray(g["position_nominal_acceleration_mps2"][()], dtype=np.float64).T
            applied = np.asarray(g["position_compensation_applied_acceleration_mps2"][()], dtype=np.float64).T
            logged_target = np.asarray(g["command_filter_target_euler"][()], dtype=np.float64).T
            logged_filtered = np.asarray(g["filtered_attitude_reference"][()], dtype=np.float64).T
            logged_filter_acc = np.asarray(g["command_filter_acceleration_applied_rads2"][()], dtype=np.float64).T
            logged_filter_req = np.asarray(g["command_filter_acceleration_request_unclamped_rads2"][()], dtype=np.float64).T
            ref = f["scene/reference"]
            ref_acc = np.asarray(ref["acceleration"][()], dtype=np.float64).T
            ref_yaw = np.asarray(ref["yaw"][()], dtype=np.float64).reshape(-1)
            pos_event = np.asarray(g["position_event_flag"][()], dtype=bool).reshape(-1)

        if (state.shape != (20001, 12) or time.shape != (20000,) or nominal.shape != (20000, 3) or
                applied.shape != (20000, 3) or logged_target.shape != (20000, 3) or
                logged_filtered.shape != (20000, 3) or ref_acc.shape != (20001, 3) or
                ref_yaw.shape != (20001,) or int(pos_event.sum()) != 1999):
            raise RuntimeError(f"{sid}: raw dimensions/event count mismatch")
        event_idx = np.flatnonzero(pos_event)
        if event_idx[0] != 10 or not np.all(np.diff(event_idx) == 10):
            raise RuntimeError(f"{sid}: event cadence mismatch")
        expected_ready = np.arange(1999) >= 31
        if not np.array_equal(ready[ids.index(sid)], expected_ready):
            raise RuntimeError(f"{sid}: 31-event warmup/readiness mismatch")
        event_action_error = float(np.max(np.abs(event_actions[ids.index(sid)] - applied[event_idx]), initial=0.0))
        held_action_error = max(float(np.max(np.abs(applied[i:i + 10] - applied[i]), initial=0.0))
                                for i in event_idx)
        if event_action_error > 1e-6 or held_action_error > 1e-10:
            raise RuntimeError(f"{sid}: 100-Hz event action / following 10-ms hold mismatch")
        if np.max(np.abs(time - np.arange(20000) * DT), initial=0.0) > 1e-11:
            raise RuntimeError(f"{sid}: transition time/index mismatch")
        # The prepared NPZ stores event times as float32; the raw controller clock is float64.
        if not np.allclose(event_times[ids.index(sid)], time[event_idx], atol=2e-6, rtol=0):
            raise RuntimeError(f"{sid}: NPZ event-time index mismatch")

        # Exact runtime map: commanded acceleration = a_nominal - applied compensation.
        commanded_acc = nominal - applied
        reconstructed_target = force_to_euler(commanded_acc, state[:20000, 8], gravity,
                                              max_tilt, ref_yaw[:20000])
        replayed_filtered, replayed_acc, replayed_req = replay_filter(
            reconstructed_target, state[0, 6:9], wn, damping, acc_limit)
        target_delta = wrap(reconstructed_target - logged_target)
        filtered_delta = wrap(replayed_filtered - logged_filtered)
        ref_task = force_to_euler(ref_acc[:20000], ref_yaw[:20000], gravity, max_tilt)
        task_error = wrap(replayed_filtered - ref_task)
        task_so3 = (Rotation.from_euler("xyz", ref_task).inv() *
                    Rotation.from_euler("xyz", replayed_filtered)).magnitude()
        per_scene.append({
            "scene_id": sid,
            "raw_sha256": rec["raw_sha256"],
            "status_sha256": rec["status_sha256"],
            "run_start_sha256": rec["run_start_sha256"],
            "release_sha256": release_sha,
            "source_runtime_scene_id": source_scene,
            "command_filter": {"wn_rad_s": wn.tolist(), "damping": damping.tolist(),
                               "acceleration_limit_rad_s2": ["Inf", "Inf", float(acc_limit[2])],
                               "dt_s": DT, "initial_euler_source": "state[:,0,roll,pitch,yaw]",
                               "initial_rate_rad_s": [0.0, 0.0, 0.0]},
            "event_count": int(pos_event.sum()),
            "event_time_first_last_s": [float(time[event_idx[0]]), float(time[event_idx[-1]])],
            "event_to_next_10_transitions_hold_max_abs_mps2": held_action_error,
            "npz_event_action_vs_raw_max_abs_mps2": event_action_error,
            "target_reconstruction_max_abs_wrapped_rad": float(np.max(np.abs(target_delta))),
            "target_reconstruction_rmse_rad": float(np.sqrt(np.mean(target_delta ** 2))),
            "filtered_replay_max_abs_wrapped_rad": float(np.max(np.abs(filtered_delta))),
            "filtered_replay_rmse_rad": float(np.sqrt(np.mean(filtered_delta ** 2))),
            "filter_acceleration_replay_max_abs_rad_s2": float(np.max(np.abs(replayed_acc - logged_filter_acc))),
            "filter_requested_acceleration_replay_max_abs_rad_s2": float(np.max(np.abs(replayed_req - logged_filter_req))),
            "filter_acceleration_clamp_count_by_axis": np.sum(np.abs(replayed_req) > acc_limit[None, :] + 1e-12, axis=0).astype(int).tolist(),
            "frozen_trajectory_task_command_euler_rmse_rad": np.sqrt(np.mean(task_error ** 2, axis=0)).tolist(),
            "frozen_trajectory_task_SO3_rmse_rad": float(np.sqrt(np.mean(task_so3 ** 2))),
        })
        if gradient_scene is None:
            gradient_scene = (raw_path, sid)

    grad_check = differentiable_segment_check(*gradient_scene)
    if not grad_check["finite_nonzero_gradient"]:
        raise RuntimeError("Differentiable task-loss gradient smoke check failed")

    max_target = max(r["target_reconstruction_max_abs_wrapped_rad"] for r in per_scene)
    max_filter = max(r["filtered_replay_max_abs_wrapped_rad"] for r in per_scene)
    max_filter_acc = max(r["filter_acceleration_replay_max_abs_rad_s2"] for r in per_scene)
    max_filter_req = max(r["filter_requested_acceleration_replay_max_abs_rad_s2"] for r in per_scene)
    max_hold = max(r["event_to_next_10_transitions_hold_max_abs_mps2"] for r in per_scene)
    result = {
        "schema": "TRAIN24_C5_TASK_FILTER_REPLAY_AUDIT_V1",
        "scope": "TRAIN24 C5 raw only; no TEST data, new Plant calls, real-wind fields, or inertia reconstruction",
        "source_dataset_manifest_sha256": sha(MANIFEST),
        "source_dataset_sha256": sha(DATA),
        "source_scene_count": len(per_scene),
        "source_replay": "C5 matched TRAIN24 raw. This is a mapping/timing audit only; current cohort uses the older attitude-RBF backbone, so no residual-GRU fitting or generalization claim is made.",
        "runtime_equations": {
            "nominal_command_acceleration": "a_cmd = logged a_nominal - logged applied compensation acceleration",
            "outer_attitude_target": "roll/pitch=baseline_force_to_attitude(a_cmd, current state yaw, g, max_tilt); target yaw is reference yaw (runtime replaces adapter yaw with r.euler(3))",
            "task_reference": "baseline_force_to_attitude(reference acceleration, reference yaw, g, max_tilt)",
            "filter": "command_filter_step: wrapped target error, wn^2*error - 2*zeta*wn*rate, per-run acceleration clip, semi-implicit rate then Euler update; logged reference is pre-update filter state",
            "event_action_mapping_for_later_fit": "event action at t=0.01,...,19.99 s is held for its following 10 one-ms transitions; learned residual is zero before the first 31 events, first ready at t=0.32 s; beta=clip(t/1.8,0,1); event action=clip(a_C5+beta*clip(delta,-0.5,0.5),-3,3)",
        },
        "fixed_candidate_objective_before_same_backbone_fit": {
            "primary": "existing SmoothL1(action_event, interval_acceleration_target) on ready 10-ms events",
            "existing_smoothness": "0.01 * mean(second_difference(delta)^2) on contiguous ready events",
            "only_new_term": "0.1 * mean(task_SO3_geodesic(filtered_candidate_reference, reference_acceleration_yaw_target)^2) over all 20,000 transitions",
            "task_weight": 0.1,
            "training_scope_when_same_backbone_data_arrives": "whole-scene grouped TRAIN split; hold out complete scenes for validation; no row-wise split",
        },
        "differentiability_smoke_check": grad_check,
        "maximum_replay_errors": {"outer_target_wrapped_rad": max_target,
                                   "filtered_reference_wrapped_rad": max_filter,
                                   "filter_acceleration_rad_s2": max_filter_acc,
                                   "filter_requested_acceleration_rad_s2": max_filter_req,
                                   "event_hold_mps2": max_hold},
        "scenes": per_scene,
        "fit_status": "DEFERRED_UNTIL_COSINE_GRU_PARENT_TRAIN24_RAW_AVAILABLE",
    }
    JSON_OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    lines = [
        "# TRAIN24 task/filter replay audit",
        "",
        f"- Scenes checked: {len(per_scene)}; target replay max error {max_target:.3e} rad.",
        f"- Command-filter replay max error {max_filter:.3e} rad; applied filter-acceleration max error {max_filter_acc:.3e} rad/s^2.",
        f"- Requested filter-acceleration replay max error {max_filter_req:.3e} rad/s^2; 100-Hz action hold max error {max_hold:.3e} m/s^2.",
        f"- Autograd segment smoke check: finite nonzero gradient={grad_check['finite_nonzero_gradient']}, norm={grad_check['gradient_norm']:.6g}.",
        "- The candidate loss is fixed in the JSON. Fitting is deferred: these available C5 raws use the older attitude-RBF backbone and do not match the cosine-GRU parent used for deployment.",
        "- Read-only scope: no TEST, new Plant, real-wind fields, or inertia reconstruction.",
        "",
    ]
    MD_OUT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
