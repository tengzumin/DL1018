#!/usr/bin/env python3
"""TRAIN-only initial-gradient scale audit; no optimization or model fitting."""
from __future__ import annotations

import hashlib
import json
import math
import os
import random
from pathlib import Path

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

import numpy as np
import torch
from torch.nn import functional as F

import fit_task_aware_fourfold_v1 as fit
from task_aware_common import DATA_DIR, DATA_MANIFEST_PATH, DATA_PATH, SOURCE_LOCK_PATH, load_locked_inputs, replay_filter, force_to_euler, FILTER_LIMIT, sha256


OUT = Path(__file__).resolve().parent
RESULT_PATH = OUT / "TASK_GRADIENT_SCALE_AUDIT_v1.json"
SCRIPT_PATH = Path(__file__).resolve()
SEED = fit.SEED


def flat_grads(grads: tuple[torch.Tensor | None, ...], params: list[torch.nn.Parameter]) -> torch.Tensor:
    return torch.cat([torch.zeros_like(p).reshape(-1) if g is None else g.detach().reshape(-1)
                      for p, g in zip(params, grads)])


def grad_groups(grads: tuple[torch.Tensor | None, ...], named: list[tuple[str, torch.nn.Parameter]]) -> dict:
    by_name = {name: grad for (name, _), grad in zip(named, grads)}
    out = {}
    for group, prefix in (("gru", "gru."), ("head", "head.")):
        vals = [g.reshape(-1) for name, g in by_name.items() if name.startswith(prefix) and g is not None]
        out[group] = float(torch.linalg.vector_norm(torch.cat(vals))) if vals else 0.0
    out["all"] = float(torch.linalg.vector_norm(torch.cat([
        torch.zeros_like(p).reshape(-1) if by_name[name] is None else by_name[name].reshape(-1)
        for name, p in named])))
    return out


def cosine(a: torch.Tensor, b: torch.Tensor) -> float | None:
    na, nb = torch.linalg.vector_norm(a), torch.linalg.vector_norm(b)
    if float(na) == 0.0 or float(nb) == 0.0:
        return None
    return float(torch.dot(a, b) / (na * nb))


def main() -> None:
    if RESULT_PATH.exists():
        raise RuntimeError(f"Refusing to overwrite {RESULT_PATH}")
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    device = torch.device("cpu")

    bundle = load_locked_inputs()
    data, manifest = bundle["arrays"], bundle["manifest"]
    ids = data["scene_ids"].astype(str).tolist()
    x = data["x14_model_input"].astype(np.float32)
    ready = data["ready_mask"].astype(bool)
    event_t = data["event_time_s"].astype(np.float64)
    base_event = data["applied_acceleration_event_mps2"].astype(np.float32)
    target = data["target_interval_clip_mps2"].astype(np.float32)
    trj = bundle["trajectories"]

    selected = []
    folds_out = {}
    for fold_i, spec in enumerate(manifest["scene_folds"]):
        train_ids = spec["train_scene_ids"]
        # Predetermined, outcome-independent selection: first and last manifest-ordered TRAIN scene.
        selected_ids = [train_ids[0], train_ids[-1]]
        train_indices = [ids.index(s) for s in train_ids]
        mu = x[train_indices].reshape(-1, 14).mean(axis=0)
        sd = x[train_indices].reshape(-1, 14).std(axis=0)
        sd[sd < 1e-6] = 1.0
        xn = ((x - mu[None, None, :]) / sd[None, None, :]).astype(np.float32)

        seed = SEED + fold_i
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)
        model = fit.ResidualGRU().to(device)
        model.eval()
        named = list(model.named_parameters())
        params = [p for _, p in named]
        rows = []
        for sid in selected_ids:
            i = ids.index(sid)
            tx = torch.as_tensor(xn[i:i + 1], device=device)
            mask = torch.as_tensor(ready[i:i + 1], device=device)
            beta = torch.as_tensor(np.clip(event_t[i:i + 1] / fit.BETA_RISE_S, 0.0, 1.0)[..., None], dtype=torch.float32)
            base = torch.as_tensor(base_event[i:i + 1], dtype=torch.float32)
            y = torch.as_tensor(target[i:i + 1], dtype=torch.float32)
            raw, delta = model(tx)
            d = torch.where(mask[:, :, None], delta, torch.zeros_like(delta))
            pred = torch.clamp(base + beta * d, -fit.ACTION_LIMIT, fit.ACTION_LIMIT)
            pos_loss = F.smooth_l1_loss(pred[mask], y[mask], reduction="mean")
            d2 = d[:, 2:] - 2.0 * d[:, 1:-1] + d[:, :-2]
            adjacent = mask[:, 2:] & mask[:, 1:-1] & mask[:, :-2]
            smooth_loss = d2[adjacent].square().mean()
            trajectory = trj[i]
            task_loss = fit.make_candidate_task_loss(
                pred, torch.as_tensor(trajectory["nominal_acc_1ms"][None], dtype=torch.float32),
                torch.as_tensor(trajectory["applied_acc_1ms"][None, :10, :], dtype=torch.float32),
                torch.as_tensor(trajectory["state_yaw_1ms"][None], dtype=torch.float32),
                torch.as_tensor(trajectory["reference_yaw_1ms"][None], dtype=torch.float32),
                torch.as_tensor(trajectory["initial_euler"][None], dtype=torch.float32),
                torch.as_tensor(trajectory["task_target_euler"][None], dtype=torch.float32), device)

            gp = torch.autograd.grad(pos_loss, params, retain_graph=True, allow_unused=True)
            gs = torch.autograd.grad(smooth_loss, params, retain_graph=True, allow_unused=True)
            gt = torch.autograd.grad(task_loss, params, retain_graph=True, allow_unused=True)
            vp, vs, vt = (flat_grads(g, params) for g in (gp, gs, gt))
            vpos = vp + fit.LAMBDA_SMOOTH * vs
            vtask = fit.LAMBDA_TASK * vt
            vtotal = vpos + vtask

            raw_np = raw.detach().cpu().numpy()
            pred_preclip = (base + beta * d).detach().cpu().numpy()
            applied = np.concatenate((trajectory["applied_acc_1ms"][:10],
                                      np.repeat(base_event[i], 10, axis=0)), axis=0)
            command_target = force_to_euler(trajectory["nominal_acc_1ms"] - applied,
                                            trajectory["state_yaw_1ms"], trajectory["reference_yaw_1ms"])
            _, cf_applied, cf_requested = replay_filter(command_target, trajectory["initial_euler"])
            rows.append({
                "scene_id": sid,
                "initial_model_output_abs_max": float(np.abs(raw_np).max()),
                "position_smooth_l1": float(pos_loss.detach()),
                "smoothness_mean_d2_sq": float(smooth_loss.detach()),
                "task_mean_so3_sq_rad2": float(task_loss.detach()),
                "gradient_norm_by_parameter_group": {
                    "position": grad_groups(gp, named),
                    "smoothing_unweighted": grad_groups(gs, named),
                    "task_unweighted": grad_groups(gt, named),
                    "task_weighted_lambda_0_1": grad_groups(tuple(None if g is None else fit.LAMBDA_TASK * g for g in gt), named),
                    "position_plus_0_01_smoothing": grad_groups(tuple(None if a is None and b is None else
                        (torch.zeros_like(p) if a is None else a) + fit.LAMBDA_SMOOTH * (torch.zeros_like(p) if b is None else b)
                        for (name, p), a, b in zip(named, gp, gs)), named),
                    "total_objective": grad_groups(tuple(None if a is None and b is None else
                        (torch.zeros_like(p) if a is None else a) + fit.LAMBDA_SMOOTH * (torch.zeros_like(p) if b is None else b) +
                        fit.LAMBDA_TASK * (torch.zeros_like(p) if c is None else c)
                        for (name, p), a, b, c in zip(named, gp, gs, gt)), named),
                },
                "vector_norms": {"position": float(torch.linalg.vector_norm(vp)),
                                 "smoothing_unweighted": float(torch.linalg.vector_norm(vs)),
                                 "task_unweighted": float(torch.linalg.vector_norm(vt)),
                                 "task_weighted_lambda_0_1": float(torch.linalg.vector_norm(vtask)),
                                 "position_plus_0_01_smoothing": float(torch.linalg.vector_norm(vpos)),
                                 "total_objective": float(torch.linalg.vector_norm(vtotal))},
                "direction": {"cos_position_vs_unweighted_task": cosine(vp, vt),
                              "cos_position_plus_smoothing_vs_weighted_task": cosine(vpos, vtask),
                              "cos_total_vs_position_plus_smoothing": cosine(vtotal, vpos),
                              "weighted_task_to_position_gradient_norm_ratio": float(torch.linalg.vector_norm(vtask) /
                                  torch.linalg.vector_norm(vpos).clamp_min(1e-30)),
                              "suggested_lambda_for_10pct_initial_norm": float(0.1 * torch.linalg.vector_norm(vpos) /
                                  torch.linalg.vector_norm(vt).clamp_min(1e-30))},
                "clip_activity": {
                    "raw_delta_abs_ge_0_5_fraction": float(np.mean(np.abs(raw_np) >= fit.DELTA_LIMIT)),
                    "predicted_delta_clip_saturated_fraction": float(np.mean(np.abs(raw_np) > fit.DELTA_LIMIT)),
                    "total_action_preclip_abs_ge_3_fraction": float(np.mean(np.abs(pred_preclip) >= fit.ACTION_LIMIT)),
                    "total_action_clip_saturated_fraction": float(np.mean(np.abs(pred_preclip) > fit.ACTION_LIMIT)),
                    "task_filter_request_abs_gt_limit_by_axis": np.sum(np.abs(cf_requested) > FILTER_LIMIT[None, :] + 1e-12, axis=0).astype(int).tolist(),
                    "task_filter_transition_count": int(len(cf_requested)),
                    "task_filter_applied_acceleration_max_abs_by_axis": np.max(np.abs(cf_applied), axis=0).tolist()},
            })

        folds_out[spec["fold_id"]] = {"seed": seed, "train_scene_count": len(train_ids),
                                       "normalizer_scope": "manifest TRAIN scenes only",
                                       "normalizer_mean_sha256": hashlib.sha256(mu.astype(np.float64).tobytes()).hexdigest(),
                                       "normalizer_std_sha256": hashlib.sha256(sd.astype(np.float64).tobytes()).hexdigest(),
                                       "selected_scene_rule": "first and last TRAIN IDs in manifest order",
                                       "scenes": rows}
        selected.extend([r["scene_id"] for r in rows])

    ratios = [r["direction"]["weighted_task_to_position_gradient_norm_ratio"]
              for f in folds_out.values() for r in f["scenes"]]
    suggested = [r["direction"]["suggested_lambda_for_10pct_initial_norm"]
                 for f in folds_out.values() for r in f["scenes"]]
    result = {
        "schema": "COSINE_GRU_POSITION_TASK_INITIAL_GRADIENT_SCALE_AUDIT_V1",
        "scope": "TRAIN_C5_24 only; no VAL/TEST raw, Plant, wind fields, or inertia reconstruction/use; diagnostics only, no optimizer updates.",
        "dataset_sha256": sha256(DATA_PATH), "manifest_sha256": sha256(DATA_MANIFEST_PATH),
        "dataset_source_lock_sha256": sha256(SOURCE_LOCK_PATH),
        "task_aware_script_sha256": sha256(OUT / "fit_task_aware_fourfold_v1.py"),
        "no_task_control_sha256": sha256(OUT.parent / "gru_residual_cv_v1/CV_OOF_PREDICTIONS_v1.npz"),
        "gradient_definition": "Per-scene initial model gradients of the exact fixed training losses; position SmoothL1, unweighted smoothing mean(d2(delta)^2), frozen-trajectory SO3 mean(theta^2). The task gradient is additionally reported multiplied by lambda_task=0.1.",
        "selection": "For each of four manifest folds, use the first and last scene in that fold's TRAIN scene list; chosen before inspecting gradient results. Each fold uses the training-only normalizer and seed=20261028+fold index.",
        "architecture_and_init": "GRU(14,32)->Linear(32,3); zero head; zero delta at initialization; scene hidden reset.",
        "clipping_and_filter": {"delta_clip_mps2": fit.DELTA_LIMIT, "total_action_clip_mps2": fit.ACTION_LIMIT,
                                "task_filter_limits_rad_s2": ["Inf", "Inf", 6],
                                "filter_transition_dt_s": 0.001, "action_event_dt_s": 0.01},
        "summary": {"selected_evaluation_count": len(selected), "unique_selected_scene_count": len(set(selected)),
                    "selected_scenes_with_exact_clip_activity": int(sum(
                        (r["clip_activity"]["raw_delta_abs_ge_0_5_fraction"] > 0 or
                         r["clip_activity"]["total_action_preclip_abs_ge_3_fraction"] > 0 or
                         sum(r["clip_activity"]["task_filter_request_abs_gt_limit_by_axis"]) > 0)
                        for f in folds_out.values() for r in f["scenes"])),
                    "weighted_task_to_position_gradient_ratio_median": float(np.median(ratios)),
                    "weighted_task_to_position_gradient_ratio_min_max": [float(np.min(ratios)), float(np.max(ratios))],
                    "target_weighted_task_to_position_gradient_ratio": 0.1,
                    "lambda_for_median_gradient_ratio_10pct": float(fit.LAMBDA_TASK * 0.1 / np.median(ratios)),
                    "median_scene_specific_lambda_for_10pct_ratio": float(np.median(suggested)),
                    "scene_specific_lambda_for_10pct_ratio_min_max": [float(np.min(suggested)), float(np.max(suggested))]},
        "folds": folds_out,
        "interpretation_limit": "Initial, per-selected-scene gradient diagnostics are not full-batch training gradients and do not establish closed-loop effects. Any rescaling is a train-only design choice requiring root review before a separate run.",
    }
    RESULT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    result["diagnostic_json_sha256"] = sha256(RESULT_PATH)
    print(json.dumps({"path": str(RESULT_PATH), "sha256": result["diagnostic_json_sha256"],
                      "summary": result["summary"],
                      "scene_ratio": {r["scene_id"] + "@" + fkey: r["direction"]["weighted_task_to_position_gradient_norm_ratio"]
                                      for fkey, f in folds_out.items() for r in f["scenes"]},
                      "scene_cosine": {r["scene_id"] + "@" + fkey: r["direction"]["cos_position_plus_smoothing_vs_weighted_task"]
                                       for fkey, f in folds_out.items() for r in f["scenes"]}}, indent=2), flush=True)


if __name__ == "__main__":
    main()
