#!/usr/bin/env python3
"""Small TRAIN-only, noncausal per-event feasibility probe; no model fitting or Plant."""
from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

import numpy as np
import torch

import fit_task_aware_fourfold_v1 as fit
from task_aware_common import (DATA_PATH, DATA_MANIFEST_PATH, SOURCE_LOCK_PATH,
                               FILTER_LIMIT, force_to_euler, load_locked_inputs, replay_filter, sha256)


OUT = Path(__file__).resolve().parent
RESULT_PATH = OUT / "TASK_FEASIBILITY_ORACLE_PROBE_v1.json"
NO_TASK_PATH = OUT.parent / "gru_residual_cv_v1/CV_OOF_PREDICTIONS_v1.npz"
TASK_PATH = OUT / "TASK_AWARE_CV_OOF_v1.npz"
NO_TASK_HASH = "9dc29cc2d94b990bafc2bdf77cc8c704fb14e2c0582987e3057cd6464e177d0f"
MAX_ITER = 15
MAX_BACKTRACK = 8
STEP_DELTA = 0.02
POSITION_TOL_RMSE = 1e-8
WARMUP_EVENT = 31
FREQ_WINDOW = 20000


def pos_rmse(action: np.ndarray, target: np.ndarray, ready: np.ndarray) -> float:
    e = action[ready].astype(np.float64) - target[ready].astype(np.float64)
    return float(np.sqrt(np.mean(e * e)))


def task_rmse_scipy(i: int, action: np.ndarray, trajectory: dict) -> float:
    return float(fit.evaluate_task_action(i, action.astype(np.float64), trajectory))


def task_target_2_5hz_share(trajectory: dict) -> tuple[float, float, float]:
    # Deterministic selector computed from TRAIN-only C5 outer command target, not wind or task-head outcomes.
    applied = trajectory["applied_acc_1ms"].astype(np.float64)
    command = trajectory["nominal_acc_1ms"].astype(np.float64) - applied
    target_euler = force_to_euler(command, trajectory["state_yaw_1ms"].astype(np.float64),
                                  trajectory["reference_yaw_1ms"].astype(np.float64))
    sig = target_euler - target_euler.mean(axis=0, keepdims=True)
    win = np.hanning(len(sig))[:, None]
    spec = np.fft.rfft(sig * win, axis=0)
    power = np.abs(spec) ** 2
    freq = np.fft.rfftfreq(len(sig), d=0.001)
    broad = (freq >= 0.1) & (freq <= 20.0)
    band = (freq >= 2.0) & (freq <= 5.0)
    broad_e = float(power[broad].sum())
    band_e = float(power[band].sum())
    return (band_e / broad_e if broad_e > 0 else 0.0, band_e, broad_e)


def candidate_tensors(i: int, bundle: dict, base_event: np.ndarray,
                      target: np.ndarray, ready: np.ndarray, event_t: np.ndarray):
    tr = bundle["trajectories"][i]
    dtype = torch.float64
    device = torch.device("cpu")
    mask = torch.as_tensor(ready[i:i + 1], dtype=torch.bool)
    beta = torch.as_tensor(np.clip(event_t[i:i + 1] / fit.BETA_RISE_S, 0.0, 1.0)[..., None], dtype=dtype)
    base = torch.as_tensor(base_event[i:i + 1], dtype=dtype)
    y = torch.as_tensor(target[i:i + 1], dtype=dtype)
    nominal = torch.as_tensor(tr["nominal_acc_1ms"][None], dtype=dtype)
    first10 = torch.as_tensor(tr["applied_acc_1ms"][None, :10, :], dtype=dtype)
    state_yaw = torch.as_tensor(tr["state_yaw_1ms"][None], dtype=dtype)
    ref_yaw = torch.as_tensor(tr["reference_yaw_1ms"][None], dtype=dtype)
    init_euler = torch.as_tensor(tr["initial_euler"][None], dtype=dtype)
    task_target = torch.as_tensor(tr["task_target_euler"][None], dtype=dtype)

    def action_from_delta(delta: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        d = torch.where(mask[:, :, None], delta.clamp(-fit.DELTA_LIMIT, fit.DELTA_LIMIT), torch.zeros_like(delta))
        action = torch.clamp(base + beta * d, -fit.ACTION_LIMIT, fit.ACTION_LIMIT)
        return action, d

    def position_mse(action: torch.Tensor) -> torch.Tensor:
        return (action[mask] - y[mask]).square().mean()

    def task_mse(action: torch.Tensor) -> torch.Tensor:
        return fit.make_candidate_task_loss(action, nominal, first10, state_yaw, ref_yaw,
                                            init_euler, task_target, device)

    return tr, mask, beta, base, y, action_from_delta, position_mse, task_mse


def oracle_optimize(i: int, scene_id: str, bundle: dict, base_event: np.ndarray,
                    target: np.ndarray, ready: np.ndarray, event_t: np.ndarray,
                    baseline_action: np.ndarray, baseline_pos_rmse: float) -> dict:
    tr, mask, beta, base, y, action_from_delta, position_mse, task_mse = candidate_tensors(
        i, bundle, base_event, target, ready, event_t)
    delta = torch.zeros((1, len(event_t[i]), 3), dtype=torch.float64, requires_grad=True)
    cap_mse = baseline_pos_rmse ** 2
    history = []
    accepted = 0
    stopped = "fixed_iteration_budget"

    for it in range(MAX_ITER):
        action, _ = action_from_delta(delta)
        p_loss = position_mse(action)
        t_loss = task_mse(action)
        if not torch.isfinite(p_loss) or not torch.isfinite(t_loss):
            stopped = "nonfinite_current_loss"
            break
        gp, gt = torch.autograd.grad(p_loss, delta, retain_graph=True)[0], torch.autograd.grad(t_loss, delta)[0]
        direction = -gt.detach()
        pos_dir = torch.sum(gp.detach() * direction)
        gp_norm = torch.linalg.vector_norm(gp.detach())
        # Project task descent into the non-increasing position-error half-space.
        if float(pos_dir) > 0.0 and float(gp_norm) > 1e-20:
            direction = direction - (pos_dir / gp.detach().square().sum().clamp_min(1e-30)) * gp.detach()
        dnorm = torch.linalg.vector_norm(direction)
        if float(dnorm) <= 1e-20:
            stopped = "no_nonzero_projected_task_descent"
            break
        # Add a small inward component to handle second-order feasibility curvature at the baseline boundary.
        if float(gp_norm) > 1e-20:
            direction = direction - 0.02 * dnorm * gp.detach() / gp_norm
        scale = direction.abs().max().clamp_min(1e-30)
        direction = direction / scale
        accepted_this = False
        current_task = float(t_loss.detach())
        for bt in range(MAX_BACKTRACK + 1):
            step = STEP_DELTA * (0.5 ** bt)
            with torch.no_grad():
                proposal = torch.where(mask[:, :, None], (delta.detach() + step * direction).clamp(
                    -fit.DELTA_LIMIT, fit.DELTA_LIMIT), torch.zeros_like(delta))
                proposal_action, proposal_d = action_from_delta(proposal)
                new_pos = float(position_mse(proposal_action))
                feasible = new_pos <= cap_mse + POSITION_TOL_RMSE * max(1.0, baseline_pos_rmse)
                if not feasible:
                    continue
                new_task = float(task_mse(proposal_action))
                if np.isfinite(new_task) and new_task < current_task - 1e-14:
                    delta = proposal.detach().requires_grad_(True)
                    accepted += 1
                    accepted_this = True
                    history.append({"iteration": it + 1, "backtrack": bt, "step_max_delta": step,
                                    "position_rmse_mps2": float(np.sqrt(new_pos)),
                                    "position_cap_mps2": baseline_pos_rmse,
                                    "task_so3_rmse_rad": float(np.sqrt(new_task)),
                                    "max_abs_delta_mps2": float(proposal_d.abs().max())})
                    break
        if not accepted_this:
            stopped = "no_feasible_task_decrease_found_within_backtracking_budget"
            break

    with torch.no_grad():
        final_action_t, final_delta_t = action_from_delta(delta)
        final_p = float(torch.sqrt(position_mse(final_action_t)))
        final_t = float(torch.sqrt(task_mse(final_action_t)))
        final_action = final_action_t[0].cpu().numpy()
        final_delta = final_delta_t[0].cpu().numpy()
    raw_cmd = tr["nominal_acc_1ms"].astype(np.float64) - np.concatenate(
        (tr["applied_acc_1ms"][:10], np.repeat(final_action, 10, axis=0)), axis=0)
    target_euler = force_to_euler(raw_cmd, tr["state_yaw_1ms"].astype(np.float64),
                                  tr["reference_yaw_1ms"].astype(np.float64))
    filt_out, filt_acc, filt_req = replay_filter(target_euler, tr["initial_euler"].astype(np.float64))
    scipy_task = task_rmse_scipy(i, final_action, tr)
    return {
        "scene_id": scene_id,
        "objective": "minimize fixed-trajectory SO3 RMSE subject to ready-event position residual RMSE <= C5 baseline RMSE",
        "position_constraint_cap_mps2": baseline_pos_rmse,
        "position_constraint_tolerance_mps2": POSITION_TOL_RMSE,
        "initial": {"position_rmse_mps2": baseline_pos_rmse,
                    "task_so3_rmse_rad": task_rmse_scipy(i, baseline_action, tr),
                    "task_forward_torch_scipy_abs_error_rad": abs(float(np.sqrt(task_mse(torch.as_tensor(baseline_action[None], dtype=torch.float64)))) -
                                                                    task_rmse_scipy(i, baseline_action, tr))},
        "oracle_sample": {"position_rmse_mps2": final_p, "position_cap_mps2": baseline_pos_rmse,
                          "position_excess_over_cap_mps2": max(0.0, final_p - baseline_pos_rmse),
                          "task_so3_rmse_rad_torch": final_t, "task_so3_rmse_rad_scipy_replay": scipy_task,
                          "torch_vs_scipy_task_abs_error_rad": abs(final_t - scipy_task),
                          "max_abs_delta_mps2": float(np.abs(final_delta).max()),
                          "delta_ready_clip_abs_ge_0_5_fraction": float(np.mean(np.abs(final_delta[ready[i]]) >= fit.DELTA_LIMIT)),
                          "delta_before_ready_abs_max_mps2": float(np.abs(final_delta[:WARMUP_EVENT]).max()),
                          "total_action_abs_ge_3_fraction": float(np.mean(np.abs(final_action) >= fit.ACTION_LIMIT)),
                          "filter_clip_count_by_axis": np.sum(np.abs(filt_req) > FILTER_LIMIT[None, :] + 1e-12, axis=0).astype(int).tolist(),
                          "filter_request_max_abs_by_axis_rad_s2": np.max(np.abs(filt_req), axis=0).tolist(),
                          "filter_applied_max_abs_by_axis_rad_s2": np.max(np.abs(filt_acc), axis=0).tolist(),
                          "task_target_filter_output_samples": int(len(filt_out))},
        "optimization": {"accepted_steps": accepted, "max_iterations": MAX_ITER,
                         "max_backtracking_trials_per_step": MAX_BACKTRACK + 1,
                         "initial_step_max_event_delta_mps2": STEP_DELTA,
                         "stop_reason": stopped, "accepted_history": history},
        "noncausal_limit": "delta is selected jointly from the full future scene trajectory; this is a sampled frozen-state oracle point, not a causal deployable controller or a global optimum/lower bound.",
    }


def main() -> None:
    if RESULT_PATH.exists():
        raise RuntimeError(f"Refusing to overwrite {RESULT_PATH}")
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    bundle = load_locked_inputs()
    data, manifest = bundle["arrays"], bundle["manifest"]
    ids = data["scene_ids"].astype(str).tolist()
    target = data["target_interval_clip_mps2"].astype(np.float32)
    ready = data["ready_mask"].astype(bool)
    base_event = data["applied_acceleration_event_mps2"].astype(np.float32)
    event_t = data["event_time_s"].astype(np.float64)
    with np.load(NO_TASK_PATH, allow_pickle=False) as f:
        no_ids = f["scene_ids"].astype(str).tolist()
        no_task = f["prediction_lambda_0_01"].astype(np.float32)
        no_ready, no_target = f["ready_mask"], f["target_clip_mps2"]
    with np.load(TASK_PATH, allow_pickle=False) as f:
        task_ids = f["scene_ids"].astype(str).tolist()
        task_action = f["task_action_lambda_task_0_1"].astype(np.float32)
        task_fold = f["fold_id"].astype(str).tolist()
        task_ready, task_target = f["ready_mask"], f["target_clip_mps2"]
    if (sha256(NO_TASK_PATH) != NO_TASK_HASH or ids != no_ids or ids != task_ids or
            not np.array_equal(no_ready, ready) or not np.array_equal(task_ready, ready) or
            not np.array_equal(no_target, target) or not np.array_equal(task_target, target)):
        raise RuntimeError("Existing OOF heads do not bind the exact TRAIN-only scene/target protocol")
    expected_fold = {sid: fold["fold_id"] for fold in manifest["scene_folds"] for sid in fold["holdout_scene_ids"]}
    if task_fold != [expected_fold[sid] for sid in ids]:
        raise RuntimeError("Task-aware OOF scene/fold binding differs from manifest")

    freq_rows = []
    for i, sid in enumerate(ids):
        share, band_e, broad_e = task_target_2_5hz_share(bundle["trajectories"][i])
        freq_rows.append({"scene_id": sid, "share_2_5hz_of_0_1_20hz": share,
                          "energy_2_5hz": band_e, "energy_0_1_20hz": broad_e})
    order = sorted(freq_rows, key=lambda x: x["share_2_5hz_of_0_1_20hz"])
    selected_rows = [order[0], order[len(order) // 2], order[-1]]
    selected_ids = list(dict.fromkeys(x["scene_id"] for x in selected_rows))
    results = {}
    for sid in selected_ids:
        i = ids.index(sid)
        base = np.clip(base_event[i], -fit.ACTION_LIMIT, fit.ACTION_LIMIT)
        candidates = {"C5_baseline": base, "ordinary_head_lambda_0_01": no_task[i],
                      "task_head_lambda_0_1": task_action[i]}
        comparison = {}
        for name, action in candidates.items():
            comparison[name] = {"position_ready_rmse_mps2": pos_rmse(action, target[i], ready[i]),
                                "task_so3_rmse_rad": task_rmse_scipy(i, action, bundle["trajectories"][i]),
                                "max_abs_action_mps2": float(np.abs(action).max())}
        baseline_pos = comparison["C5_baseline"]["position_ready_rmse_mps2"]
        results[sid] = {"frequency_selector": next(x for x in freq_rows if x["scene_id"] == sid),
                        "baseline_and_oof_heads": comparison,
                        "oracle_sample": oracle_optimize(i, sid, bundle, base_event, target, ready, event_t,
                                                          base, baseline_pos)}
        print(json.dumps({"scene_id": sid, "frequency_share_2_5hz": results[sid]["frequency_selector"]["share_2_5hz_of_0_1_20hz"],
                          "heads": comparison, "oracle_initial": results[sid]["oracle_sample"]["initial"],
                          "oracle_result": results[sid]["oracle_sample"]["oracle_sample"],
                          "optimizer": results[sid]["oracle_sample"]["optimization"]}, ensure_ascii=False), flush=True)

    result = {
        "schema": "COSINE_GRU_C5_TRAIN24_TASK_POSITION_FEASIBILITY_ORACLE_PROBE_V1",
        "scope": "TRAIN_C5_24 parent cosine-GRU raw/OOF heads only; no VAL/TEST raw, Plant, real-wind fields, or inertia reconstruction/use.",
        "dataset_sha256": sha256(DATA_PATH), "dataset_manifest_sha256": sha256(DATA_MANIFEST_PATH),
        "dataset_source_lock_sha256": sha256(SOURCE_LOCK_PATH),
        "no_task_oof_sha256": sha256(NO_TASK_PATH), "task_oof_sha256": sha256(TASK_PATH),
        "selection": "Exploratory deterministic sample: lowest, median-rank, and highest per-scene 2-5 Hz command-target energy share of 0.1-20 Hz among TRAIN_C5_24; command target reconstructed from C5 applied action, current yaw, and reference yaw before oracle optimization. This is TRAIN selection, not independent validation or preregistration.",
        "frequency_ranked_train_scenes": order,
        "oracle_protocol": {"variable": "independent per-event delta for each selected scene; only ready events can vary",
                            "delta_bounds_mps2": [-fit.DELTA_LIMIT, fit.DELTA_LIMIT],
                            "beta": "clip(event_time_s/1.8,0,1)", "total_action_clip_mps2": [-fit.ACTION_LIMIT, fit.ACTION_LIMIT],
                            "position_constraint": "RMSE of (candidate applied action - clipped 10-ms position target), ready events only, must not exceed C5 baseline RMSE",
                            "task_objective": "minimize SO3 geodesic RMSE over 20,000 1-ms frozen-state command-filter outputs against reference-derived task target",
                            "filter": "same 1-ms pre-update semi-implicit command-filter replay; initial logged Euler, zero rate; acceleration limits [Inf,Inf,6]",
                            "optimizer": "projected task-gradient descent with position-gradient half-space projection, fixed 15-iteration budget and up to 9 feasibility backtracking trials per step; starts at C5 delta=0",
                            "future_information": "noncausal oracle: each event delta is optimized with the entire trajectory available; not a deployable policy"},
        "selected_scene_count": len(selected_ids), "selected_scenes": results,
        "limitations": ["The reported result is a sampled feasible point from a fixed-budget optimizer, not a global optimum, lower bound, or proof that no better feasible action exists.",
                        "State, current yaw, reference, and later command-filter task targets are frozen; residual-induced closed-loop state changes are omitted.",
                        "The high-frequency selector uses reconstructed C5 command-target signal only; no wind or test field is read."],
    }
    result["script_sha256"] = sha256(Path(__file__))
    RESULT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"path": str(RESULT_PATH), "sha256": sha256(RESULT_PATH),
                      "selected_scenes": {sid: {"band_share": v["frequency_selector"]["share_2_5hz_of_0_1_20hz"],
                                                "head_comparison": v["baseline_and_oof_heads"],
                                                "oracle_initial": v["oracle_sample"]["initial"],
                                                "oracle_final": v["oracle_sample"]["oracle_sample"],
                                                "iterations": v["oracle_sample"]["optimization"]} for sid, v in results.items()}}, indent=2), flush=True)


if __name__ == "__main__":
    main()
