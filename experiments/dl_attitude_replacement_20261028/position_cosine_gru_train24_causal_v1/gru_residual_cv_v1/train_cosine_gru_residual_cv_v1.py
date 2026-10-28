#!/usr/bin/env python3
"""Fixed TRAIN24 wind-group CV for a causal position residual GRU head."""
from __future__ import annotations

import hashlib
import json
import os
import random
import time
from pathlib import Path

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F


ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "experiments/dl_attitude_replacement_20261028/position_cosine_gru_train24_causal_v1"
NPZ = DATA_DIR / "COSINE_GRU_C5_TRAIN24_POSITION_CAUSAL_PAIRS_v1.npz"
MANIFEST = DATA_DIR / "DATASET_MANIFEST_v1.json"
DATA_SOURCE_LOCK = DATA_DIR / "SOURCE_LOCK_v1.json"
SEED = 20261028
STEPS = 300
LR = 1e-3
LAMBDAS = (0.01,)
DT = 0.01
BETA_RISE_S = 1.8
ACTION_LIMIT = 3.0
DELTA_LIMIT = 0.5
FREQ_BANDS_HZ = ((0, 1), (1, 2), (2, 5), (5, 10), (10, 20), (20, 50))
TIME_TOL_S = 1.0e-12  # event times preserve the source double-precision transition clock


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


class ResidualGRU(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.gru = nn.GRU(input_size=14, hidden_size=32, num_layers=1, batch_first=True)
        self.head = nn.Linear(32, 3)
        nn.init.zeros_(self.head.weight)
        nn.init.zeros_(self.head.bias)

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        h, _ = self.gru(x)  # batch dimension is scene: hidden state resets at every scene boundary
        raw_delta = self.head(h)
        return raw_delta, raw_delta.clamp(-DELTA_LIMIT, DELTA_LIMIT)


def rmse(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(a.astype(np.float64) - b.astype(np.float64)))))


def score_scenes(indices: list[int], scene_ids: np.ndarray, ready: np.ndarray,
                 target: np.ndarray, base: np.ndarray, pred: np.ndarray) -> dict:
    per_scene = {}
    for i in indices:
        m = ready[i]
        e_base = base[i, m] - target[i, m]
        e_pred = pred[i, m] - target[i, m]
        per_scene[str(scene_ids[i])] = {
            "n_ready": int(m.sum()),
            "baseline_rmse_mps2": rmse(base[i, m], target[i, m]),
            "model_rmse_mps2": rmse(pred[i, m], target[i, m]),
            "baseline_axis_rmse_mps2": np.sqrt(np.mean(e_base.astype(np.float64) ** 2, axis=0)).tolist(),
            "model_axis_rmse_mps2": np.sqrt(np.mean(e_pred.astype(np.float64) ** 2, axis=0)).tolist(),
        }
    vals = list(per_scene.values())
    # Pooled metrics weight every event-axis equally; macro gives every scene equal weight.
    y_all = np.concatenate([target[i, ready[i]] for i in indices], axis=0)
    b_all = np.concatenate([base[i, ready[i]] for i in indices], axis=0)
    p_all = np.concatenate([pred[i, ready[i]] for i in indices], axis=0)
    b_axis = np.stack([v["baseline_axis_rmse_mps2"] for v in vals])
    p_axis = np.stack([v["model_axis_rmse_mps2"] for v in vals])
    diffs = [v["model_rmse_mps2"] - v["baseline_rmse_mps2"] for v in vals]
    return {
        "scene_count": len(indices),
        "pooled_baseline_rmse_mps2": rmse(b_all, y_all),
        "pooled_model_rmse_mps2": rmse(p_all, y_all),
        "scene_macro_baseline_rmse_mps2": float(np.mean([v["baseline_rmse_mps2"] for v in vals])),
        "scene_macro_model_rmse_mps2": float(np.mean([v["model_rmse_mps2"] for v in vals])),
        "scene_macro_baseline_axis_rmse_mps2": b_axis.mean(axis=0).tolist(),
        "scene_macro_model_axis_rmse_mps2": p_axis.mean(axis=0).tolist(),
        "wins_ties_losses_vs_baseline": [int(sum(d < -1e-12 for d in diffs)),
                                          int(sum(abs(d) <= 1e-12 for d in diffs)),
                                          int(sum(d > 1e-12 for d in diffs))],
        "per_scene": per_scene,
    }


def spectral_rms(x: np.ndarray, t: np.ndarray) -> dict:
    """Single-sided band RMS, averaged across axes, for a uniform 100 Hz event stream."""
    x = x.astype(np.float64)
    x = x - x.mean(axis=0, keepdims=True)
    n = len(x)
    freqs = np.fft.rfftfreq(n, d=DT)
    z = np.fft.rfft(x, axis=0)
    weights = np.full(len(freqs), 2.0)
    weights[0] = 1.0
    if n % 2 == 0:
        weights[-1] = 1.0
    power = (np.abs(z) ** 2) * weights[:, None] / (n * n)
    out = {}
    for lo, hi in FREQ_BANDS_HZ:
        m = (freqs >= lo) & ((freqs < hi) if hi < 50 else (freqs <= hi))
        out[f"{lo:g}-{hi:g}Hz_rms_mps2"] = float(np.sqrt(power[m].sum(axis=0).mean()))
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    data_hash = sha256(NPZ)
    if data_hash.lower() != manifest["dataset_sha256"].lower():
        raise RuntimeError("Cosine-GRU TRAIN24 NPZ SHA256 does not match its manifest")
    source_lock = json.loads(DATA_SOURCE_LOCK.read_text(encoding="utf-8"))
    if sha256(DATA_SOURCE_LOCK).lower() != manifest["source_lock_sha256"].lower():
        raise RuntimeError("Dataset source-lock SHA256 mismatch")
    if sha256(DATA_DIR / "TRAIN_C5_24_PHYSICAL_RESIDUAL_MANIFEST_source_v1.json").lower() != source_lock["physical_manifest_sha256"].lower():
        raise RuntimeError("Copied physical TRAIN24 manifest SHA256 mismatch")
    if manifest["scope"].get("TEST_read") is not False or manifest["scope"].get("Plant_called_by_builder") is not False or manifest["scope"].get("inertia_reconstruction") is not False:
        raise RuntimeError("Dataset manifest scope lock failed")
    if source_lock.get("data_sha256", "").lower() != data_hash.lower() or "TRAIN_C5_24 physical IDs only" not in source_lock.get("scope", ""):
        raise RuntimeError("Dataset source lock mismatch")

    with np.load(NPZ, allow_pickle=False) as z:
        arrays = {k: z[k] for k in z.files}
    scene_ids = arrays["scene_ids"]
    winds = arrays["wind_cells"].astype(int)
    fold_ids = arrays["fold_id"].astype(str)
    x = arrays["x14_model_input"].astype(np.float32)
    x_logged = arrays["x14_logged"].astype(np.float32)
    ready = arrays["ready_mask"].astype(bool)
    time_s = arrays["event_time_s"].astype(np.float64)
    interval_end = arrays["interval_end_time_s"].astype(np.float64)
    base = arrays["applied_acceleration_event_mps2"].astype(np.float32)
    target = arrays["target_interval_clip_mps2"].astype(np.float32)
    delta = arrays["delta_target_post_clip_mps2"].astype(np.float32)
    if x.shape != (24, 1999, 14) or not np.array_equal(x, x_logged):
        raise RuntimeError("Expected matching causal logged/model 14-feature tensors")
    if target.shape != base.shape or delta.shape != base.shape or not np.isfinite(x).all() or not np.isfinite(base).all() or not np.isfinite(target).all():
        raise RuntimeError("Non-finite TRAIN24 input/action/target")
    if np.isfinite(delta[~ready]).any() or not np.isfinite(delta[ready]).all() or not np.allclose(delta[ready], target[ready] - base[ready], atol=2e-7, rtol=1e-6):
        raise RuntimeError("Residual labels do not equal clipped interval target minus logged applied action")
    if not np.allclose(np.diff(time_s, axis=1), DT, atol=TIME_TOL_S, rtol=0):
        raise RuntimeError("Irregular event time; this script assumes the fixed 10ms event cadence")
    if not np.allclose(interval_end - time_s, DT, atol=TIME_TOL_S, rtol=0):
        raise RuntimeError("Label interval is not exactly the next 10ms after feature time")
    if not np.array_equal(ready, np.broadcast_to(np.arange(1999) >= 31, ready.shape)):
        raise RuntimeError("Unexpected readiness mask")
    if not np.array_equal(fold_ids, np.asarray([next(f["fold_id"] for f in manifest["scene_folds"] if s in f["holdout_scene_ids"]) for s in scene_ids])):
        raise RuntimeError("NPZ fold_id values do not match the source manifest")
    if len(set(scene_ids.tolist())) != 24 or any("DL1018_DEV_" not in str(s) for s in scene_ids):
        raise RuntimeError("Expected only the 24 locked physical DEV IDs")
    folds = manifest["scene_folds"]
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    torch.set_num_threads(1)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    torch.use_deterministic_algorithms(True)
    ids = [str(s) for s in scene_ids]
    fold_reports: dict[str, dict] = {}
    oof = {lam: np.full_like(base, np.nan) for lam in LAMBDAS}
    train_predictions = {lam: [] for lam in LAMBDAS}
    checkpoints = OUT / "checkpoints"
    checkpoints.mkdir(exist_ok=True)
    t_start = time.time()

    for fold_i, spec in enumerate(folds):
        fold_name = spec["fold_id"]
        train_ids, hold_ids = spec["train_scene_ids"], spec["holdout_scene_ids"]
        tr = [ids.index(s) for s in train_ids]
        ho = [ids.index(s) for s in hold_ids]
        if (len(tr) != spec["train_scene_count"] or len(ho) != spec["holdout_scene_count"]
                or set(ids[i] for i in ho) != set(hold_ids) or np.any(fold_ids[ho] != fold_name)
                or np.any(fold_ids[tr] == fold_name) or set(tr) & set(ho)):
            raise RuntimeError(f"Scene-group split mismatch: {fold_name}")

        # Fit the 14-channel normalizer on this fold's training scenes only.
        mu = x[tr].reshape(-1, 14).mean(axis=0)
        sd = x[tr].reshape(-1, 14).std(axis=0)
        sd[sd < 1e-6] = 1.0
        xn = ((x - mu[None, None, :]) / sd[None, None, :]).astype(np.float32)
        beta = np.clip(time_s / BETA_RISE_S, 0.0, 1.0).astype(np.float32)
        tx = torch.as_tensor(xn, device=device)
        ta = torch.as_tensor(base, device=device)
        ty = torch.as_tensor(target, device=device)
        tb = torch.as_tensor(beta[..., None], device=device)
        tm = torch.as_tensor(ready, device=device)
        fold_reports[fold_name] = {"wind_code_range": spec["wind_code_range"], "train_scene_ids": train_ids,
                                   "holdout_scene_ids": hold_ids, "normalizer_mean": mu.tolist(),
                                   "normalizer_std": sd.tolist(), "lambda_runs": {}}

        for lam in LAMBDAS:
            # Same fold seed gives the two lambda arms identical initialization and ordering.
            seed = SEED + fold_i
            random.seed(seed)
            np.random.seed(seed)
            torch.manual_seed(seed)
            if torch.cuda.is_available():
                torch.cuda.manual_seed_all(seed)
            model = ResidualGRU().to(device)
            optimizer = torch.optim.Adam(model.parameters(), lr=LR)
            tr_idx = torch.as_tensor(tr, dtype=torch.long, device=device)
            last = None
            for step in range(STEPS):
                model.train()
                optimizer.zero_grad(set_to_none=True)
                raw_delta, d = model(tx[tr_idx])
                d = torch.where(tm[tr_idx, :, None], d, torch.zeros_like(d))
                pred = torch.clamp(ta[tr_idx] + tb[tr_idx] * d, -ACTION_LIMIT, ACTION_LIMIT)
                loss = F.smooth_l1_loss(pred[tm[tr_idx]], ty[tr_idx][tm[tr_idx]], reduction="mean")
                if lam:
                    d2 = d[:, 2:] - 2.0 * d[:, 1:-1] + d[:, :-2]
                    consecutive = tm[tr_idx, 2:] & tm[tr_idx, 1:-1] & tm[tr_idx, :-2]
                    consecutive &= (torch.abs(torch.as_tensor(np.diff(time_s[tr], axis=1)[:, 1:],
                                                                 device=device) - DT) < TIME_TOL_S)
                    smooth = d2[consecutive].square().mean()
                    loss = loss + float(lam) * smooth
                loss.backward()
                optimizer.step()
                last = float(loss.detach().cpu())

            model.eval()
            with torch.no_grad():
                raw_all, d_all = model(tx)
                d_all = torch.where(tm[:, :, None], d_all, torch.zeros_like(d_all))
                pred_all = torch.clamp(ta + tb * d_all, -ACTION_LIMIT, ACTION_LIMIT)
            raw_np = raw_all.cpu().numpy()
            d_np = d_all.cpu().numpy()
            p_np = pred_all.cpu().numpy()
            oof[lam][ho] = p_np[ho]
            train_predictions[lam].append((tr, p_np[tr].copy()))
            fold_train = score_scenes(tr, scene_ids, ready, target, np.clip(base, -ACTION_LIMIT, ACTION_LIMIT), p_np)
            fold_hold = score_scenes(ho, scene_ids, ready, target, np.clip(base, -ACTION_LIMIT, ACTION_LIMIT), p_np)
            hold_d = d_np[ho][ready[ho]]
            hold_raw = raw_np[ho][ready[ho]]
            hold_preclip = base[ho] + beta[ho, :, None] * d_np[ho]
            hold_final = p_np[ho]
            fold_reports[fold_name]["lambda_runs"][str(lam)] = {
                "seed": seed, "fixed_optimizer_steps": STEPS, "last_training_objective": last,
                "train": fold_train, "holdout": fold_hold,
                "holdout_output": {
                    "beta_mean_ready": float(beta[ho][ready[ho]].mean()),
                    "delta_rms_mps2": float(np.sqrt(np.mean(hold_d.astype(np.float64) ** 2))),
                    "raw_head_abs_ge_0_5_fraction": float(np.mean(np.abs(hold_raw) >= DELTA_LIMIT)),
                    "final_action_abs_ge_3_fraction": float(np.mean(np.abs(hold_preclip[ready[ho]]) >= ACTION_LIMIT)),
                    "final_action_fraction_at_clip": float(np.mean(np.isclose(np.abs(hold_final[ready[ho]]), ACTION_LIMIT, atol=1e-7))),
                },
            }
            # Checkpoint only model parameters plus fold-fitted input normalization.
            ckpt = {"state_dict": model.cpu().state_dict(), "normalizer_mean": mu,
                    "normalizer_std": sd, "fold": fold_name, "lambda": lam,
                    "seed": seed, "steps": STEPS, "data_sha256": data_hash}
            torch.save(ckpt, checkpoints / f"{fold_name}_lambda_{lam:g}.pt")

    # OOF is the relevant grouped-CV score: each TRAIN24 scene is held out once by wind.
    oof_summary = {}
    for lam in LAMBDAS:
        if not np.isfinite(oof[lam]).all():
            raise RuntimeError(f"Missing OOF prediction for lambda={lam}")
        oof_summary[str(lam)] = score_scenes(list(range(24)), scene_ids, ready, target,
                                             np.clip(base, -ACTION_LIMIT, ACTION_LIMIT), oof[lam])
        oof_summary[str(lam)]["by_fold_id"] = {}
        # Per-held-out-fold OOF summary and output saturation/spectral diagnostics.
        for spec in folds:
            fold_name = spec["fold_id"]
            ix = np.flatnonzero(fold_ids == fold_name).tolist()
            pred_w = oof[lam][ix]
            vals = []
            bands = {kind: {f"{lo:g}-{hi:g}Hz_rms_mps2": [] for lo, hi in FREQ_BANDS_HZ}
                     for kind in ("baseline_action", "model_action", "applied_correction")}
            for q, i in enumerate(ix):
                vals.append({
                    "scene_id": ids[i],
                    "baseline_action_clip_fraction": float(np.mean(np.abs(base[i, ready[i]]) >= ACTION_LIMIT)),
                    "model_action_clip_fraction": float(np.mean(np.isclose(np.abs(pred_w[q, ready[i]]), ACTION_LIMIT, atol=1e-7))),
                    "model_delta_rms_mps2": float(np.sqrt(np.mean((pred_w[q, ready[i]] - np.clip(base[i, ready[i]], -ACTION_LIMIT, ACTION_LIMIT)) ** 2))),
                })
                base_ready = np.clip(base[i, ready[i]], -ACTION_LIMIT, ACTION_LIMIT)
                signals = {
                    "baseline_action": base_ready,
                    "model_action": pred_w[q, ready[i]],
                    "applied_correction": pred_w[q, ready[i]] - base_ready,
                }
                for kind, signal in signals.items():
                    for k, v in spectral_rms(signal, time_s[i, ready[i]]).items():
                        bands[kind][k].append(v)
            oof_summary[str(lam)]["by_fold_id"][fold_name] = score_scenes(ix, scene_ids, ready, target,
                                                                            np.clip(base, -ACTION_LIMIT, ACTION_LIMIT), oof[lam])
            oof_summary[str(lam)]["by_fold_id"][fold_name]["wind_code_range"] = spec["wind_code_range"]
            oof_summary[str(lam)]["by_fold_id"][fold_name]["output_diagnostics"] = {
                "scene_macro_model_action_clip_fraction": float(np.mean([v["model_action_clip_fraction"] for v in vals])),
                "scene_macro_baseline_action_clip_fraction": float(np.mean([v["baseline_action_clip_fraction"] for v in vals])),
                "scene_macro_model_delta_rms_mps2": float(np.mean([v["model_delta_rms_mps2"] for v in vals])),
                "scene_macro_spectrum_rms_by_band_mps2": {
                    kind: {k: float(np.mean(v)) for k, v in spectrum.items()}
                    for kind, spectrum in bands.items()
                },
            }

    pred_path = OUT / "CV_OOF_PREDICTIONS_v1.npz"
    np.savez_compressed(pred_path, scene_ids=scene_ids, wind_cells=winds.astype(np.int16), fold_id=fold_ids,
                        event_time_s=time_s, ready_mask=ready,
                        target_clip_mps2=target, applied_baseline_mps2=base,
                        prediction_lambda_0_01=oof[0.01])
    lock = {
        "schema": "COSINE_GRU_C5_POSITION_RESIDUAL_GRU_CV_SOURCE_LOCK_V1",
        "source_scope": "Only physical TRAIN_C5_24 IDs and their parent cosine-GRU raw pairs; no VAL/TEST raw, Plant, or inertia reconstruction",
        "npz_path": str(NPZ.relative_to(ROOT)).replace("\\", "/"), "npz_sha256": data_hash,
        "manifest_sha256": sha256(MANIFEST), "dataset_source_lock_sha256": sha256(DATA_SOURCE_LOCK),
        "builder_sha256": sha256(DATA_DIR / "build_cosine_gru_train24_causal_pairs_v1.py"),
        "script_sha256": sha256(Path(__file__)), "scene_count": len(scene_ids),
        "event_count_per_scene": int(x.shape[1]), "ready_count_per_scene": int(ready[0].sum()),
        "folds": [{"fold_id": f["fold_id"], "wind_code_range": f["wind_code_range"],
                   "train_scene_ids": f["train_scene_ids"], "holdout_scene_ids": f["holdout_scene_ids"]}
                  for f in folds],
        "optimizer_steps_per_fold_lambda": STEPS, "seed_base": SEED, "lambda_values": list(LAMBDAS),
        "parent_model_exposure": manifest["parent_model_exposure"],
        "device": str(device), "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    write_json(OUT / "SOURCE_LOCK_v1.json", lock)
    results = {
        "schema": "COSINE_GRU_C5_POSITION_RESIDUAL_GRU_CV_RESULTS_V1", "source_lock": "SOURCE_LOCK_v1.json",
        "architecture": "GRU(14,32), Linear(32,3), zero-initialized output; scene is batch item and hidden reset per scene",
        "target": "SmoothL1(clip(a_current + beta(t)*clip(delta,-0.5,0.5),-3,3), clip(y_10ms,-3,3)); beta=clip(event_time_s/1.8,0,1)",
        "smoothing": "lambda * mean(second difference of clipped delta squared), only triples of consecutive ready 10ms events in same scene",
        "normalizer": "per-fold channel mean/std from that fold's manifest-listed training scenes only, all 1999 causal input events",
        "folds": fold_reports,
        "wind_group_oof": oof_summary,
        "runtime_seconds": time.time() - t_start,
        "important_limit": "Development-only residual-head CV on physical TRAIN_C5_24 scene IDs. The frozen parent cosine-GRU was trained/evaluated on DEV24+VAL48 and has seen these exact DEV24 scenes; this is neither independent validation of the full system nor closed-loop evidence.",
    }
    write_json(OUT / "RESULTS_v1.json", results)
    print(json.dumps({"device": str(device), "runtime_seconds": results["runtime_seconds"],
                      "oof": {k: {"macro_base": v["scene_macro_baseline_rmse_mps2"],
                                  "macro_model": v["scene_macro_model_rmse_mps2"],
                                  "pooled_base": v["pooled_baseline_rmse_mps2"],
                                  "pooled_model": v["pooled_model_rmse_mps2"],
                                  "wins": v["wins_ties_losses_vs_baseline"]}
                              for k, v in oof_summary.items()}}, indent=2))


if __name__ == "__main__":
    main()
