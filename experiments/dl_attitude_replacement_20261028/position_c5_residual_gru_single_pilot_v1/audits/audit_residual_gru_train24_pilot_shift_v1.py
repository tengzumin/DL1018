"""Read-only X14 normalization and raw-head saturation audit, TRAIN24 vs one VAL pilot."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import h5py
import numpy as np
import torch
from torch import nn

HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
ROOT = HERE.parents[3]
TRAIN = ROOT / "reports/position_c5_train24_causal_dataset_v1/dataset/C5_TRAIN24_POSITION_CAUSAL_PAIRS_v1.npz"
TRAIN_MANIFEST = ROOT / "reports/position_c5_train24_causal_dataset_v1/C5_TRAIN24_POSITION_CAUSAL_MANIFEST_v1.json"
TRAIN_DIR = ROOT / "experiments/dl_attitude_replacement_20261028/position_c5_residual_gru_full_train_v1"
PILOT = STUDY / "runs/DL1018_VAL_T3_C01_W14/raw_run.mat"
MANIFEST = TRAIN_DIR / "MODEL_MANIFEST_v1.json"
CKPT = TRAIN_DIR / "position_residual_gru_full_train24.pt"
FIT = TRAIN_DIR / "TRAIN_FIT_v1.json"
OUT = HERE / "RESIDUAL_GRU_TRAIN24_PILOT_SHIFT_v1.json"
NAMES = ["preview_error_x", "preview_error_y", "preview_error_z",
         "surface_x", "surface_y", "surface_z",
         "attitude_x", "attitude_y", "attitude_z", "normalized_preview_thrust",
         "arm_command_1", "arm_command_2", "arm_command_3", "arm_command_4"]
WINDOWS = [("warmup_0.01_0.31s", .01, .32), ("ready_0.32_1s", .32, 1),
           ("beta_ramp_1_1.8s", 1, 1.8), ("steady_1.8_5s", 1.8, 5),
           ("5_10s", 5, 10), ("10_20s", 10, 20.01)]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stats(x: np.ndarray) -> dict:
    return {"mean": np.mean(x, axis=0).tolist(), "std": np.std(x, axis=0).tolist(),
            "min": np.min(x, axis=0).tolist(), "p01": np.quantile(x, .01, axis=0).tolist(),
            "median": np.quantile(x, .5, axis=0).tolist(), "p99": np.quantile(x, .99, axis=0).tolist(),
            "max": np.max(x, axis=0).tolist()}


def main():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    data_manifest = json.loads(TRAIN_MANIFEST.read_text(encoding="utf-8"))
    fit = json.loads(FIT.read_text(encoding="utf-8"))
    assert sha(TRAIN) == manifest["source_data_sha256"]
    assert sha(CKPT) == manifest["checkpoint_sha256"]
    assert fit["scope"].startswith("TRAIN24 only")
    assert data_manifest["scope"]["TEST_accessed"] is False and data_manifest["scope"]["Plant_calls"] == 0
    with np.load(TRAIN, allow_pickle=False) as z:
        xtr = z["x14_model_input"].astype(np.float64)
        ids = z["scene_ids"].astype(str)
        winds = z["wind_cells"].astype(int)
        ready_tr = z["ready_mask"].astype(bool)
        time_tr = z["event_time_s"].astype(float)
    package = torch.load(CKPT, map_location="cpu", weights_only=False)
    mu = np.asarray(package["input_mean"], dtype=float)
    sd = np.asarray(package["input_std"], dtype=float)
    ztr = (xtr-mu[None, None, :])/sd[None, None, :]

    with h5py.File(PILOT, "r") as f:
        log = f["log"]
        event = np.asarray(log["stage1_position_event"][()], dtype=bool).reshape(-1)
        valid = np.asarray(log["stage1_position_event_inference_valid"][()], dtype=bool).reshape(-1)
        time_full = np.asarray(log["transition_time"][()], dtype=float).reshape(-1)
        idx = np.flatnonzero(event)
        x_full = np.asarray(log["stage1_position_feature_14"][()], dtype=float).T
        xin_full = np.asarray(log["stage1_position_feature_input"][()], dtype=float).T
        raw_full = np.asarray(log["stage1_position_residual_gru_raw_delta_mps2"][()], dtype=float).T
        beta_full = np.asarray(log["stage1_position_residual_gru_beta"][()], dtype=float).reshape(-1)
    xp = x_full[idx]
    xpin = xin_full[idx]
    rawp = raw_full[idx]
    tp = time_full[idx]
    rp = valid[idx]
    betap = beta_full[idx]
    assert xtr.shape == (24, 1999, 14) and xp.shape == (1999, 14)
    assert np.array_equal(xp, xpin)
    assert np.array_equal(ready_tr, np.broadcast_to(np.arange(1999) >= 31, ready_tr.shape))
    assert np.array_equal(rp, np.arange(1999) >= 31)
    assert np.allclose(tp[[0, -1]], [.01, 19.99], atol=1e-12, rtol=0)
    assert np.allclose(tp[31], .32, atol=1e-12, rtol=0)
    assert np.allclose(betap, np.clip(tp/1.8, 0, 1), atol=1e-12, rtol=0)
    zpilot = (xp-mu)/sd
    ready_xtr, ready_ztr = xtr[ready_tr], ztr[ready_tr]
    ready_xp, ready_zp = xp[rp], zpilot[rp]
    train_min, train_max = np.min(xtr, axis=(0, 1)), np.max(xtr, axis=(0, 1))

    # Reproduce in-sample TRAIN24 raw head outputs; this is inference only, not training.
    model = nn.GRU(input_size=14, hidden_size=32, num_layers=1, batch_first=True)
    head = nn.Linear(32, 3)
    model.load_state_dict({k.removeprefix("gru."): v for k, v in package["state_dict"].items()
                           if k.startswith("gru.")}, strict=True)
    head.load_state_dict({k.removeprefix("head."): v for k, v in package["state_dict"].items()
                          if k.startswith("head.")}, strict=True)
    model.eval(); head.eval()
    with torch.no_grad():
        xn = torch.as_tensor(ztr, dtype=torch.float32)
        out, _ = model(xn)
        rawtr = head(out).numpy().astype(float)
    c = .5
    clip_tr = np.abs(rawtr[ready_tr]) >= c
    clip_p = np.abs(rawp[rp]) >= c
    require_clip = float(np.mean(clip_p))
    train_clip = float(np.mean(clip_tr))

    # Verify the controller-mode difference directly on the 24 manifest-bound TRAIN raw runs.
    train_modes = []
    for scene in data_manifest["scenes"]:
        raw_path = ROOT / scene["raw_path"]
        assert sha(raw_path) == scene["raw_sha256"]
        with h5py.File(raw_path, "r") as f:
            g = f["log"]
            train_modes.append({"scene_id": scene["scene_id"],
                                "attitude_fusion_rbf_output_enabled": int(np.asarray(g["attitude_fusion_rbf_output_enabled"][()]).squeeze()),
                                "attitude_fusion_rbf_update_enabled": int(np.asarray(g["attitude_fusion_rbf_update_enabled"][()]).squeeze()),
                                "gru_stream_tracking_head_field_present": "gru_stream_tracking_head_enabled" in g})
    with h5py.File(PILOT, "r") as f:
        pg = f["log"]
        pilot_mode = {"attitude_fusion_rbf_output_enabled": int(np.asarray(pg["attitude_fusion_rbf_output_enabled"][()]).squeeze()),
                      "attitude_fusion_rbf_update_enabled": int(np.asarray(pg["attitude_fusion_rbf_update_enabled"][()]).squeeze()),
                      "gru_stream_tracking_head_enabled": int(np.asarray(pg["gru_stream_tracking_head_enabled"][()]).squeeze())}

    # Build compact dimension summaries (raw distribution and standardized support).
    per_feature = []
    train_stats, pilot_stats = stats(ready_xtr), stats(ready_xp)
    for j, name in enumerate(NAMES):
        trmin, trmax = train_min[j], train_max[j]
        q = ready_zp[:, j]
        per_feature.append({
            "index_1based": j+1, "name": name,
            "train24_ready_raw": {k: train_stats[k][j] for k in ("mean", "std", "min", "p01", "median", "p99", "max")},
            "pilot_ready_raw": {k: pilot_stats[k][j] for k in ("mean", "std", "min", "p01", "median", "p99", "max")},
            "frozen_normalizer": {"mean": float(mu[j]), "std": float(sd[j])},
            "pilot_ready_z": {"mean": float(np.mean(q)), "std": float(np.std(q)),
                              "min": float(np.min(q)), "p01": float(np.quantile(q, .01)),
                              "median": float(np.median(q)), "p99": float(np.quantile(q, .99)),
                              "max": float(np.max(q)), "fraction_abs_gt_3": float(np.mean(np.abs(q)>3)),
                              "fraction_abs_gt_5": float(np.mean(np.abs(q)>5)),
                              "fraction_outside_train24_raw_minmax": float(np.mean((ready_xp[:,j]<trmin)|(ready_xp[:,j]>trmax)))}
        })

    by_wind = {}
    for w in (0, 9, 12, 15):
        mask = (winds[:, None] == w) & ready_tr
        xx = xtr[mask]
        by_wind[f"W{w:02d}"] = {"ready_rows": int(mask.sum()), "raw_mean": np.mean(xx, axis=0).tolist(),
                                  "raw_std": np.std(xx, axis=0).tolist(),
                                  "z_abs_gt3_fraction_by_dim": np.mean(np.abs((xx-mu)/sd)>3, axis=0).tolist()}

    raw_tr_ready, raw_p_ready = rawtr[ready_tr], rawp[rp]
    per_window = []
    for label, lo, hi in WINDOWS:
        mt = (time_tr >= lo) & (time_tr < hi) & ready_tr
        mp = (tp >= lo) & (tp < hi) & rp
        if not np.any(mp):
            continue
        cp = np.abs(rawp[mp]) >= c
        per_window.append({"window": label, "pilot_ready_events": int(mp.sum()),
                           "beta_mean": float(np.mean(betap[mp])),
                           "raw_head_rms_mps2_by_axis": np.sqrt(np.mean(rawp[mp]**2, axis=0)).tolist(),
                           "raw_clip_fraction_component": float(np.mean(cp)),
                           "raw_clip_fraction_by_axis": np.mean(cp, axis=0).tolist(),
                           "any_axis_clipped_event_fraction": float(np.mean(np.any(cp, axis=1))),
                           "train24_raw_clip_fraction_component_same_time_window":
                               float(np.mean(np.abs(rawtr[mt]) >= c)) if np.any(mt) else None})

    # Diagnostic association only: univariate standardized outlier vs any-axis raw clipping.
    clipped_event = np.any(clip_p, axis=1)
    conditional = []
    for j, name in enumerate(NAMES):
        hi = np.abs(ready_zp[:, j]) > 3
        conditional.append({"feature": name, "fraction_ready_abs_z_gt3": float(hi.mean()),
                            "clip_event_rate_if_abs_z_gt3": float(np.mean(clipped_event[hi])) if hi.any() else None,
                            "clip_event_rate_if_abs_z_le3": float(np.mean(clipped_event[~hi])) if (~hi).any() else None})

    result = {
        "schema": "POSITION_RESIDUAL_GRU_TRAIN24_PILOT_FEATURE_SHIFT_V1",
        "scope": "Read-only comparison: fixed TRAIN24 dataset/model and the already-recorded single VAL pilot. Pilot is diagnostic only; no training or selection used it.",
        "data_binding": {"train_npz_sha256": sha(TRAIN), "train_model_manifest_sha256": sha(MANIFEST),
                         "train_data_manifest_sha256": sha(TRAIN_MANIFEST),
                         "checkpoint_sha256": sha(CKPT), "pilot_raw_sha256": sha(PILOT),
                         "train_scene_ids": ids.tolist(), "pilot_scene_id": "DL1018_VAL_T3_C01_W14"},
        "feature_order": NAMES,
        "event_timing": {"train_event_count_per_scene": 1999, "pilot_event_count": int(len(idx)),
                         "train_ready_events_per_scene": 1968, "pilot_ready_events": int(rp.sum()),
                         "first_event_time_train_pilot_s": [float(np.min(time_tr)), float(tp[0])],
                         "first_ready_time_train_pilot_s": [float(np.min(time_tr[ready_tr])), float(tp[31])],
                         "last_event_time_train_pilot_s": [float(np.max(time_tr)), float(tp[-1])],
                         "beta_formula": "clip(event_time/1.8,0,1)", "pilot_beta_mean_ready": float(np.mean(betap[rp]))},
        "feature_dimensions": per_feature,
        "controller_regime_evidence": {"train_scene_count": len(train_modes),
                                        "train_all_rbf_output_enabled": all(x["attitude_fusion_rbf_output_enabled"] == 1 for x in train_modes),
                                        "train_all_rbf_update_enabled": all(x["attitude_fusion_rbf_update_enabled"] == 1 for x in train_modes),
                                        "train_scenes_with_gru_stream_tracking_head_field": sum(x["gru_stream_tracking_head_field_present"] for x in train_modes),
                                        "pilot": pilot_mode,
                                        "train_scene_modes": train_modes,
                                        "interpretation": "Logged position X14 was collected under the TRAIN C5 attitude/RBF mode; the pilot kept C5 position but disabled RBF attitude output and enabled the cosine-GRU tracking head. This is a strong policy-context mismatch candidate, not single-factor causal proof."},
        "train_ready_raw_stats_by_wind": by_wind,
        "raw_head": {"raw_clip_threshold_mps2": c,
                     "train24_in_sample_ready_component_fraction": train_clip,
                     "pilot_ready_component_fraction": require_clip,
                     "pilot_clip_by_axis": np.mean(clip_p, axis=0).tolist(),
                     "train24_clip_by_axis": np.mean(clip_tr, axis=0).tolist(),
                     "train24_raw_rms_mps2_by_axis": np.sqrt(np.mean(raw_tr_ready**2, axis=0)).tolist(),
                     "pilot_raw_rms_mps2_by_axis": np.sqrt(np.mean(raw_p_ready**2, axis=0)).tolist(),
                     "train24_raw_abs_p99_mps2_by_axis": np.quantile(np.abs(raw_tr_ready), .99, axis=0).tolist(),
                     "pilot_raw_abs_p99_mps2_by_axis": np.quantile(np.abs(raw_p_ready), .99, axis=0).tolist(),
                     "pilot_positive_clip_fraction_by_axis": np.mean(raw_p_ready >= c, axis=0).tolist(),
                     "pilot_negative_clip_fraction_by_axis": np.mean(raw_p_ready <= -c, axis=0).tolist()},
        "time_windows": per_window,
        "pilot_abs_z_gt3_vs_head_clip_association": conditional,
        "limitations": ["Train raw outputs are in-sample inference over the same 24 scenes, not OOF; compare separately with the existing fold OOF 0–2.2% range.",
                        "Univariate z-tail/clip association is descriptive, not causal; the GRU hidden state couples prior features.",
                        "Pilot raw clipping is a single VAL diagnostic and is not used for retraining, normalization refit, or tuning.",
                        "No TEST data, Plant call, or inertia reconstruction was accessed by this audit."],
        "source_fit_report": fit,
    }
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps({"output": str(OUT), "train_clip": train_clip, "pilot_clip": require_clip,
                      "per_dim": [{"name": f["name"], "pilot_abs_z_gt3": f["pilot_ready_z"]["fraction_abs_gt_3"],
                                  "pilot_outside_train_range": f["pilot_ready_z"]["fraction_outside_train24_raw_minmax"]}
                                 for f in per_feature],
                      "time_windows": per_window}, indent=2))


if __name__ == "__main__":
    main()
