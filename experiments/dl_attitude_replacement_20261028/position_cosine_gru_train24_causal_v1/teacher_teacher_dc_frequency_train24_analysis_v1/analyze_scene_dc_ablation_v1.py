#!/usr/bin/env python3
"""TRAIN-only frozen-task ablation of each method's scene-mean action correction."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "experiments/dl_attitude_replacement_20261028/position_cosine_gru_train24_causal_v1"
SOURCE = DATA_DIR / "task_aware_cv_v1"
TEACHER = SOURCE / "TRAIN24_TEACHER_DISTILLATION_OOF_v1.npz"
NO_DC = DATA_DIR / "teacher_position_balanced_cv_v1/TEACHER_POSITION_BALANCED_OOF_v1.npz"
WITH_DC = DATA_DIR / "teacher_position_balanced_dc_penalty_cv_v1/DC_PENALTY_OOF_v1.npz"
ANALYSIS_RESULT = OUT / "TEACHER_DC_FREQUENCY_TIME_RESULTS_v1.json"
OUT_JSON = OUT / "SCENE_DC_ABLATION_v1.json"
OUT_MD = OUT / "SCENE_DC_ABLATION_v1.md"
sys.path.insert(0, str(SOURCE))
import fit_task_aware_fourfold_v1 as fit  # noqa: E402
from task_aware_common import load_locked_inputs  # noqa: E402


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def arrays(path: Path) -> dict:
    with np.load(path, allow_pickle=False) as z:
        return {k: z[k] for k in z.files}


def task_windows(action: np.ndarray, trajectory: dict) -> dict:
    applied = np.concatenate((trajectory["applied_acc_1ms"][:10], np.repeat(action, 10, axis=0)), axis=0).astype(np.float64)
    command = trajectory["nominal_acc_1ms"].astype(np.float64) - applied
    euler = fit.force_to_euler(command, trajectory["state_yaw_1ms"], trajectory["reference_yaw_1ms"])
    filtered, _, _ = fit.replay_filter(euler, trajectory["initial_euler"].astype(np.float64))
    target = trajectory["task_target_euler"].astype(np.float64)
    theta = (Rotation.from_euler("xyz", target).inv() * Rotation.from_euler("xyz", filtered)).magnitude()
    t = np.arange(len(theta), dtype=np.float64) * .001
    out = {"all_20s": float(np.sqrt(np.mean(theta ** 2)))}
    for a, b in ((0, 5), (5, 10), (10, 15), (15, 20)):
        out[f"{a}_{b}s"] = float(np.sqrt(np.mean(theta[(t >= a) & (t < b)] ** 2)))
    return out


def main() -> None:
    if OUT_JSON.exists() or OUT_MD.exists(): raise RuntimeError("Refusing to overwrite DC ablation outputs")
    bundle = load_locked_inputs()
    data = bundle["arrays"]
    ids = data["scene_ids"].astype(str).tolist()
    base = np.clip(data["applied_acceleration_event_mps2"].astype(np.float32), -3, 3)
    ready = data["ready_mask"].astype(bool)
    teacher, no_dc, dc = arrays(TEACHER), arrays(NO_DC), arrays(WITH_DC)
    actions = {
        "teacher": teacher["teacher_action_mps2"].astype(np.float32),
        "student_no_dc": no_dc["student_action_mps2"].astype(np.float32),
        "student_dc": dc["student_action_mps2"].astype(np.float32),
    }
    for z in (teacher, no_dc, dc):
        if z["scene_ids"].astype(str).tolist() != ids or not np.array_equal(z["ready_mask"].astype(bool), ready):
            raise RuntimeError("TRAIN action rows mismatch")
    scenes = {}
    for i, sid in enumerate(ids):
        scenes[sid] = {}
        for method, a in actions.items():
            d = (a[i] - base[i]).astype(np.float64)
            mu = d[ready[i]].mean(axis=0)
            d[~ready[i]] = 0
            no_mean = d.copy(); no_mean[ready[i]] -= mu
            mean_only = np.zeros_like(d); mean_only[ready[i]] = mu
            scenes[sid][method] = {
                "scene_mean_delta_xyz_mps2": mu.tolist(),
                "scene_mean_delta_norm_mps2": float(np.linalg.norm(mu)),
                "full_action": task_windows(a[i], bundle["trajectories"][i]),
                "dc_only_action": task_windows(np.clip(base[i] + mean_only, -3, 3), bundle["trajectories"][i]),
                "scene_mean_removed_action": task_windows(np.clip(base[i] + no_mean, -3, 3), bundle["trajectories"][i]),
            }
    summary = {}
    for method in actions:
        summary[method] = {}
        for key in ("full_action", "dc_only_action", "scene_mean_removed_action"):
            summary[method][key] = {window: float(np.mean([s[method][key][window] for s in scenes.values()]))
                                    for window in ("all_20s", "0_5s", "5_10s", "10_15s", "15_20s")}
        summary[method]["scene_mean_delta_norm_macro_mps2"] = float(np.mean([s[method]["scene_mean_delta_norm_mps2"] for s in scenes.values()]))
    result = {"schema": "COSINE_GRU_TRAIN24_SCENE_DC_FROZEN_TASK_ABLATION_V1",
              "scope": "Only locked TRAIN_C5_24; existing actions on frozen C5 trajectories; no VAL/TEST, new Plant call, or inertia reconstruction.",
              "analysis_source_sha256": sha(ANALYSIS_RESULT),
              "results": summary, "per_scene": scenes,
              "limit": "DC-only and mean-removed actions are offline counterfactuals on fixed trajectories; not closed-loop evidence."}
    OUT_JSON.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    lines = ["# Scene-mean action ablation (TRAIN24 frozen task)", "",
             "Scene mean is measured from ready event actions. `DC-only` injects that vector on ready rows; `mean-removed` subtracts it from the full correction. Both are offline ablations on frozen C5 trajectories.", "",
             "| Method | DC norm macro | Full SO(3) | DC-only SO(3) | Mean-removed SO(3) |",
             "|---|---:|---:|---:|---:|"]
    for method, row in summary.items():
        lines.append(f"| {method} | {row['scene_mean_delta_norm_macro_mps2']:.6f} | {row['full_action']['all_20s']:.6f} | {row['dc_only_action']['all_20s']:.6f} | {row['scene_mean_removed_action']['all_20s']:.6f} |")
    lines += ["", "Per-method 5-second window scores are in the JSON. The DC-only/mean-removed contrasts are non-additive frozen-task diagnostics and do not predict closed-loop Q.", ""]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"summary": summary, "json_sha256": sha(OUT_JSON), "report_sha256": sha(OUT_MD)}, ensure_ascii=False), flush=True)


if __name__ == "__main__": main()
