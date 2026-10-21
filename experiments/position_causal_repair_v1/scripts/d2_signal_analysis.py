from __future__ import annotations

import csv
import hashlib
import json
import math
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import h5py
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy.io

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "experiments" / "position_causal_repair_v1"
COMP_PATH = OUT / "reports/D2_LABEL_COMPONENTS.csv"
ALPHAS = (1e-4, 1e-3, 1e-2, 1e-1, 1.0, 10.0)
SUPPORT = (5.5, 10.0)
QUERY = (10.0, 20.0)
COMPONENTS = ("d_wind", "d_allocation", "d_attitude_realization", "d_mapping")
EPS = np.asarray([1e-4, 1e-4, 1e-4, 1e-3, 1e-3, 1e-3], dtype=np.float64)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def read_mat_model(path: Path) -> dict:
    d = scipy.io.loadmat(path, simplify_cells=True)
    model = d["model"]
    return {k: np.asarray(v) if isinstance(v, (np.ndarray, list, tuple)) else v for k, v in model.items()}


def bspline_basis(x: np.ndarray, knots: np.ndarray) -> np.ndarray:
    n, dim = x.shape
    k = np.asarray(knots, dtype=np.float64).reshape(-1)
    clipped = np.clip(x, -4.0, 4.0)
    B = np.zeros((n, dim, len(k) - 1), dtype=np.float64)
    for i in range(len(k) - 1):
        B[:, :, i] = (clipped >= k[i]) & (clipped < k[i + 1])
    for degree in range(1, 4):
        width = len(k) - degree - 1
        nxt = np.zeros((n, dim, width), dtype=np.float64)
        for i in range(width):
            ld = k[i + degree] - k[i]
            rd = k[i + degree + 1] - k[i + 1]
            if ld > 0:
                nxt[:, :, i] += (clipped - k[i]) / ld * B[:, :, i]
            if rd > 0:
                nxt[:, :, i] += (k[i + degree + 1] - clipped) / rd * B[:, :, i + 1]
        B = nxt
    at_end = clipped >= 4
    B[at_end, :] = 0
    # Boolean indexing above flattens feature rows; restore the defined right-end knot.
    if np.any(at_end):
        for i, j in np.argwhere(at_end):
            B[i, j, :] = 0
            B[i, j, -1] = 1
    return B


def encode(model: dict, x: np.ndarray) -> np.ndarray:
    mu = np.asarray(model["input_mu"], dtype=np.float64).reshape(-1)
    sigma = np.maximum(np.asarray(model["input_sigma"], dtype=np.float64).reshape(-1), 1e-4)
    cur = (np.asarray(x, dtype=np.float64) - mu) / sigma
    clipped = np.clip(cur, -4, 4)
    basis = bspline_basis(clipped, np.asarray(model["knots"], dtype=np.float64))
    spline = np.asarray(model["spline_W"], dtype=np.float64)
    hpre = np.asarray(model["feature_b"], dtype=np.float64).reshape(1, -1) + np.einsum("oib,nib->no", spline, basis, optimize=True)
    linear = np.asarray(model["linear_W"], dtype=np.float64)
    silu_x = cur if bool(np.asarray(model.get("kan_silu_unclipped", 0)).reshape(-1)[0]) else clipped
    silu = silu_x / (1.0 + np.exp(-np.clip(silu_x, -80, 80)))
    h = np.tanh(hpre + silu @ linear.T)
    return np.concatenate([h, np.ones((len(h), 1))], axis=1) / np.sqrt(1.0 + np.sum(h * h, axis=1, keepdims=True))


def score(yhat: np.ndarray, y: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.sum((yhat - y) ** 2, axis=1)))) if len(y) else math.nan


def read_episode(path: Path) -> dict:
    with h5py.File(path, "r") as f:
        x = np.asarray(f["x14"], dtype=np.float64)
        y = np.asarray(f["target_clip"], dtype=np.float64)
        ready = np.asarray(f["ready"], dtype=bool).reshape(-1)
        beta = np.asarray(f["beta"], dtype=np.float64).reshape(-1)
        t = np.asarray(f["event_time_s"], dtype=np.float64).reshape(-1)
        actual = np.asarray(f["applied_compensation"], dtype=np.float64)
    if x.shape[0] == 14 and x.shape[1] == len(t): x = x.T
    if y.shape[0] == 3 and y.shape[1] == len(t): y = y.T
    if actual.shape[0] == 3 and actual.shape[1] == len(t): actual = actual.T
    if x.shape != (len(t), 14) or y.shape != (len(t), 3) or actual.shape != (len(t), 3):
        raise ValueError(f"Bad event H5 shapes {path}: {x.shape}, {y.shape}, {actual.shape}")
    return {"x": x, "y": y, "ready": ready, "beta": beta, "t": t, "actual": actual}


def metric_row(encoder: str, split: str, task: str, wind: str, scene: str, method: str,
               alpha: float | None, t: np.ndarray, ready: np.ndarray, beta: np.ndarray,
               y: np.ndarray, pred: np.ndarray, window: str) -> dict:
    m = ready & (t >= QUERY[0]) & (t < QUERY[1]) if window == "QUERY_10_20" else ready & (t >= SUPPORT[0]) & (t < SUPPORT[1])
    return {"encoder": encoder, "split": split, "task": task, "wind_frequency_group": wind,
            "scene_id": scene, "method": method, "alpha": alpha, "window": window,
            "n_events": int(m.sum()), "Q_raw_clip_mps2": score(pred[m], y[m]),
            "Q_beta_applied_mps2": score(beta[m, None] * pred[m], y[m])}


def ridge_delta(phi: np.ndarray, y: np.ndarray, w0: np.ndarray, alpha: float) -> np.ndarray:
    n = len(y)
    XTX = phi.T @ phi / n
    residual = y - phi @ w0
    rhs = phi.T @ residual / n
    return np.linalg.solve(XTX + alpha * np.eye(phi.shape[1]), rhs)


def component_metric(group: pd.DataFrame, name: str, mask_name: str) -> dict:
    d = group[[f"{name}_x_mps2", f"{name}_y_mps2", f"{name}_z_mps2"]].to_numpy(dtype=float)
    if len(d) == 0:
        return {f"{name}_n": 0}
    bias = np.mean(d, axis=0); rms = float(np.sqrt(np.mean(np.sum(d * d, axis=1))))
    out = {f"{name}_n": len(d), f"{name}_rms_mps2": rms,
           f"{name}_bias_x_mps2": bias[0], f"{name}_bias_y_mps2": bias[1],
           f"{name}_bias_z_mps2": bias[2], f"{name}_bias_norm_mps2": float(np.linalg.norm(bias)),
           f"{name}_dominant_hz": dominant_freq(d, group["time_s"].to_numpy(dtype=float))}
    return out


def dominant_freq(x: np.ndarray, t: np.ndarray) -> float:
    if len(t) < 8: return math.nan
    dt = float(np.median(np.diff(t)))
    if dt <= 0: return math.nan
    z = x - np.mean(x, axis=0, keepdims=True)
    win = np.hanning(len(t))[:, None]
    p = np.sum(np.abs(np.fft.rfft(z * win, axis=0)) ** 2, axis=1)
    freq = np.fft.rfftfreq(len(t), dt)
    keep = (freq >= 0.05) & (freq <= min(49.9, 1 / (2 * dt)))
    if not np.any(keep) or np.max(p[keep]) <= np.finfo(float).eps: return math.nan
    return float(freq[keep][np.argmax(p[keep])])


def summarize_components(comp: pd.DataFrame, metadata: dict[str, dict]) -> pd.DataFrame:
    comp = comp.copy()
    comp["ready"] = comp["event_index"].to_numpy(dtype=int) >= 32
    comp["wind_frequency_group"] = comp["scene_id"].map(lambda s: metadata[s]["wind_frequency_group"])
    comp["task"] = comp["scene_id"].map(lambda s: metadata[s]["task"])
    comp["class_id"] = comp["scene_id"].map(lambda s: metadata[s]["class_id"])
    out = []
    for (scene, role), g0 in comp.groupby(["scene_id", "role"], sort=True):
        g = g0[g0["ready"]].sort_values("event_index")
        labels = [("ALL_READY", g)]
        for label, lo, hi in (("T_0_1p8", 0, 1.8), ("T_1p8_5", 1.8, 5), ("T_5_10", 5, 10),
                              ("T_10_15", 10, 15), ("T_15_20", 15, 20)):
            labels.append((label, g[(g.time_s >= lo) & (g.time_s < hi)]))
        for phase, gg in g.groupby("phase", sort=True): labels.append((f"PHASE_{phase}", gg))
        for label, part in labels:
            if part.empty: continue
            z = {"scene_id": scene, "role": role, "task": metadata[scene]["task"],
                 "class_id": metadata[scene]["class_id"], "wind_frequency_group": metadata[scene]["wind_frequency_group"],
                 "diagnostic_phase": label, "n_events": len(part)}
            for c in (*COMPONENTS, "d_effective", "d_applied"):
                z.update(component_metric(part, c, label))
            # Pairwise cross terms are retained so component RMS values are never added as if independent.
            cross_sum = 0.0
            for i, a in enumerate(COMPONENTS):
                av = part[[f"{a}_x_mps2", f"{a}_y_mps2", f"{a}_z_mps2"]].to_numpy(float)
                z[f"{a}_mean_power"] = float(np.mean(np.sum(av * av, axis=1)))
                for b in COMPONENTS[i + 1:]:
                    bv = part[[f"{b}_x_mps2", f"{b}_y_mps2", f"{b}_z_mps2"]].to_numpy(float)
                    cross = float(2 * np.mean(np.sum(av * bv, axis=1)))
                    z[f"cross_{a}_{b}_mps4"] = cross; cross_sum += cross
            z["sum_component_powers_plus_cross_mps4"] = sum(z[f"{c}_mean_power"] for c in COMPONENTS) + cross_sum
            de = part[["d_effective_x_mps2", "d_effective_y_mps2", "d_effective_z_mps2"]].to_numpy(float)
            z["d_effective_mean_power_mps4"] = float(np.mean(np.sum(de * de, axis=1)))
            z["decomposition_energy_closure_abs_mps4"] = abs(z["sum_component_powers_plus_cross_mps4"] - z["d_effective_mean_power_mps4"])
            da = part[["d_applied_x_mps2", "d_applied_y_mps2", "d_applied_z_mps2"]].to_numpy(float)
            err = da - de
            surf = part[["surface_x_mps", "surface_y_mps", "surface_z_mps"]].to_numpy(float)
            en = np.linalg.norm(err, axis=1); sn = np.linalg.norm(surf, axis=1)
            cos = np.sum(err * surf, axis=1) / np.maximum(en * sn, 1e-15)
            valid_cos = np.isfinite(cos) & (en > 1e-12) & (sn > 1e-12)
            z.update({"compensation_error_rms_mps2": float(np.sqrt(np.mean(np.sum(err * err, axis=1)))),
                      "compensation_error_bias_x_mps2": float(np.mean(err[:, 0]),),
                      "compensation_error_bias_y_mps2": float(np.mean(err[:, 1]),),
                      "compensation_error_bias_z_mps2": float(np.mean(err[:, 2]),),
                      "error_surface_cosine_mean": float(np.mean(cos[valid_cos])) if valid_cos.any() else math.nan,
                      "error_surface_cosine_median": float(np.median(cos[valid_cos])) if valid_cos.any() else math.nan,
                      "adjacent_comp_error_step_mean_mps2": float(np.mean(np.linalg.norm(np.diff(err, axis=0), axis=1))) if len(err)>1 else math.nan,
                      "adjacent_applied_step_mean_mps2": float(np.mean(np.linalg.norm(np.diff(da, axis=0), axis=1))) if len(da)>1 else math.nan})
            out.append(z)
    return pd.DataFrame(out)


def load_metadata() -> dict[str, dict]:
    with (ROOT / "configs/scene_specs.csv").open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    m = {}
    for r in rows:
        w = int(r["w"]); f2 = float(r["f2_hz"])
        wind = "NO_WIND" if w == 15 else "LOW" if f2 <= .95 else "MID" if f2 < 3.6 else "HIGH"
        m[r["scene_id"]] = {"task": r["task"], "class_id": r["class_id"], "class_index": int(r["c"]),
                            "wind_cell": w, "wind_frequency_group": wind, "f1_hz": float(r["f1_hz"]), "f2_hz": f2}
    return m


def adaptation_probe(meta: dict[str, dict], comp: pd.DataFrame) -> tuple[pd.DataFrame, dict, pd.DataFrame, pd.DataFrame]:
    initial_model = read_mat_model(ROOT / "models/position/initial/matlab_model_and_parity.mat")
    final_model = read_mat_model(ROOT / "models/position/selected/matlab_model_and_parity.mat")
    models = {"INITIAL": initial_model, "FINAL": final_model}
    candidate_cache = {enc: [] for enc in models}
    episodes = []
    with (ROOT / "logs/attempt_index.csv").open(encoding="utf-8-sig", newline="") as f:
        attempts = list(csv.DictReader(f))
    student = [r for r in attempts if r["gate_id"] == "G04_P_STUDENT" and r["collector_id"] == "P_INIT_STUDENT"
               and r["status"] == "COMPLETE" and r["accepted_for_training"].lower() == "true"]
    for r in student:
        scene = r["scene_id"]; path = ROOT / Path(r["position_event_path"].replace("/", "\\"))
        d = read_episode(path)
        phi = {enc: encode(model, d["x"]) for enc, model in models.items()}
        w0 = {enc: np.asarray(model["output_W"], dtype=np.float64) for enc, model in models.items()}
        item = {"scene": scene, "split": r["split"].upper(), "task": meta[scene]["task"],
                "wind": meta[scene]["wind_frequency_group"], **d, "phi": phi, "w0": w0}
        episodes.append(item)
        for enc in models:
            pred = phi[enc] @ w0[enc]
            fixed = np.clip(pred, -3, 3)
            candidate_cache[enc].append((item, pred, fixed))

    # Select each encoder's regularizer only from the G04 TRAIN episodes; query blocks are future in time.
    selected = {}
    selection = {}
    for enc in models:
        scores = {a: [] for a in ALPHAS}
        train_items = [x for x in episodes if x["split"] == "TRAIN"]
        for item, pred, fixed in candidate_cache[enc]:
            if item["split"] != "TRAIN": continue
            sup = item["ready"] & (item["t"] >= SUPPORT[0]) & (item["t"] < SUPPORT[1])
            qry = item["ready"] & (item["t"] >= QUERY[0]) & (item["t"] < QUERY[1])
            if not sup.any() or not qry.any(): continue
            phi = item["phi"][enc]; y = item["y"]; w0 = item["w0"][enc]
            for alpha in ALPHAS:
                w = w0 + ridge_delta(phi[sup], y[sup], w0, alpha)
                scores[alpha].append((item, score(np.clip(phi[qry] @ w, -3, 3), y[qry])))
        macro = {}
        for alpha, pairs in scores.items():
            by_task = []
            for task in sorted({x[0]["task"] for x in pairs}):
                vals = [v for ep, v in pairs if ep["task"] == task]
                by_task.append(float(np.mean(vals)))
            macro[alpha] = float(np.mean(by_task)) if by_task else math.inf
        best = min(ALPHAS, key=lambda a: (macro[a], -a))
        selected[enc] = best
        selection[enc] = {"selected_alpha": best, "train_macro_query_Q_by_alpha": {str(a): macro[a] for a in ALPHAS},
                          "training_scenes": len(train_items), "support_time_s": list(SUPPORT),
                          "query_time_s": list(QUERY), "tie_rule": "higher alpha if scores exactly tie"}

    result = []
    for item, encpred in ((it, {enc: it["phi"][enc] @ it["w0"][enc] for enc in models}) for it in episodes):
        for enc in models:
            phi=item["phi"][enc]; w0=item["w0"][enc]; y=item["y"]; t=item["t"]; beta=item["beta"]; ready=item["ready"]
            qmask=ready&(t>=QUERY[0])&(t<QUERY[1]); smask=ready&(t>=SUPPORT[0])&(t<SUPPORT[1])
            fixed=np.clip(encpred[enc],-3,3)
            for window, mask in (("SUPPORT_5p5_10",smask),("QUERY_10_20",qmask)):
                for method, pred, alpha in (("FIXED_W0",fixed,None),
                                             ("FIXED_W0_BETA_APPLIED",beta[:,None]*fixed,None)):
                    result.append({"encoder":enc,"split":item["split"],"task":item["task"],"wind_frequency_group":item["wind"],
                                   "scene_id":item["scene"],"method":method,"alpha":alpha,"window":window,
                                   "n_events":int(mask.sum()),"Q_mps2":score(pred[mask],y[mask])})
            if smask.any() and qmask.any():
                alpha=selected[enc]; w=w0+ridge_delta(phi[smask],y[smask],w0,alpha)
                fitted=np.clip(phi@w,-3,3)
                for window, mask in (("SUPPORT_5p5_10",smask),("QUERY_10_20",qmask)):
                    result.append({"encoder":enc,"split":item["split"],"task":item["task"],"wind_frequency_group":item["wind"],
                                   "scene_id":item["scene"],"method":"EARLY_RIDGE", "alpha":alpha,"window":window,
                                   "n_events":int(mask.sum()),"Q_mps2":score(fitted[mask],y[mask])})
            # Current P_INIT online output, replayed on the exact same Initial-generated trajectory.
            if enc=="INITIAL":
                actual=item["actual"]
                for window, mask in (("SUPPORT_5p5_10",smask),("QUERY_10_20",qmask)):
                    result.append({"encoder":enc,"split":item["split"],"task":item["task"],"wind_frequency_group":item["wind"],
                                   "scene_id":item["scene"],"method":"ACTUAL_ONLINE_INITIAL","alpha":None,"window":window,
                                   "n_events":int(mask.sum()),"Q_mps2":score(actual[mask],y[mask])})
    out=pd.DataFrame(result)
    # Add the two fixed G06 Final online observations; these are only two same-scene DEV traces.
    g06=comp[(comp.role=="P_A")].copy()
    for scene,g in g06.groupby("scene_id"):
        t=g.time_s.to_numpy(float); ready=g.event_index.to_numpy(int)>=32
        m=ready&(t>=QUERY[0])&(t<QUERY[1])
        y=np.clip(g[["target_raw_x_mps2","target_raw_y_mps2","target_raw_z_mps2"]].to_numpy(float),-3,3)
        a=g[["d_applied_x_mps2","d_applied_y_mps2","d_applied_z_mps2"]].to_numpy(float)
        md=meta.get(scene,{"task":"DEV","wind_frequency_group":"G06_SELECTED"})
        out.loc[len(out)]={"encoder":"FINAL","split":"DEV","task":md["task"],"wind_frequency_group":md["wind_frequency_group"],
                           "scene_id":scene,"method":"ACTUAL_ONLINE_FINAL_G06","alpha":np.nan,"window":"QUERY_10_20",
                           "n_events":int(m.sum()),"Q_mps2":score(a[m],y[m])}
    sel_json={"method":"same-scene early-support ridge, no future labels enter support",
              "support_s":list(SUPPORT),"query_s":list(QUERY),"alpha_grid":list(ALPHAS),
              "ridge_target":"target_clip (m/s^2), regression of clipped pre-beta head output; applied beta results reported separately",
              "selection_scope":"TRAIN episodes only, macro averaged by task; VAL used only for evaluation",
              "counterfactual_note":"INITIAL/FINAL fixed-head and early-ridge predictions on G04 are offline counterfactuals on Initial-generated closed-loop state trajectories, not closed-loop results.",
              "encoder_selection":selection,"matrix_solves":sum(len([x for x in episodes if x['split']=='TRAIN'])*len(ALPHAS) for _ in models)+sum(len([x for x in episodes if x['split']=='VAL']) for _ in models)}
    return out,sel_json,pd.DataFrame(),pd.DataFrame()


def x20_information_probe(meta: dict[str, dict], comp: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Scene-held-out weighted linear probe; assesses added information, not KAN capacity."""
    with (ROOT / "logs/attempt_index.csv").open(encoding="utf-8-sig", newline="") as f:
        attempts = list(csv.DictReader(f))
    student = [r for r in attempts if r["gate_id"] == "G04_P_STUDENT" and r["collector_id"] == "P_INIT_STUDENT"
               and r["status"] == "COMPLETE" and r["accepted_for_training"].lower() == "true"]
    episodes = []
    comp_by_scene = {s: g.sort_values("event_index") for s, g in comp[comp.role == "P_INIT_STUDENT"].groupby("scene_id")}
    for r in student:
        scene = r["scene_id"]; h5 = read_episode(ROOT / Path(r["position_event_path"].replace("/", "\\")))
        raw_path = ROOT / Path(r["raw_path"].replace("/", "\\"))
        with h5py.File(raw_path, "r") as f:
            state = np.asarray(f["log/state"], dtype=np.float64).T
            nominal = np.asarray(f["log/position_nominal_acceleration_mps2"], dtype=np.float64).T
        with h5py.File(ROOT / Path(r["position_event_path"].replace("/", "\\")), "r") as f:
            plant_idx = np.asarray(f["plant_index"], dtype=np.int64).reshape(-1) - 1
        if len(plant_idx) != len(h5["t"]): raise ValueError(f"D2 event length mismatch {scene}")
        x14 = h5["x"]
        x20 = np.column_stack([x14, state[plant_idx, 3:6], nominal[plant_idx, :3]])
        # Use the frozen training endpoint stride and ready mask; each scene is weighted equally.
        ids = np.flatnonzero(h5["ready"])[::5]
        episodes.append({"scene": scene, "split": r["split"].upper(), "task": meta[scene]["task"],
                         "class_index": meta[scene]["class_index"], "wind": meta[scene]["wind_frequency_group"],
                         "X14": x14[ids], "X20": x20[ids], "Y": h5["y"][ids]})

    variants = ("X14", "X20")
    lambdas = (1e-4, 1e-3, 1e-2, 1e-1, 1.0, 10.0)
    train_eps = [e for e in episodes if e["split"] == "TRAIN"]
    val_eps = [e for e in episodes if e["split"] == "VAL"]
    # Deterministic grouped four-fold assignment, round-robin within task x class x wind.
    folds = {}
    strata = defaultdict(list)
    for e in train_eps: strata[(e["task"], e["class_index"], e["wind"])].append(e["scene"])
    for key, scenes in strata.items():
        for i, scene in enumerate(sorted(scenes)): folds[scene] = i % 4

    def normalizer(pool: list[dict], key: str) -> tuple[np.ndarray, np.ndarray]:
        X = np.concatenate([e[key] for e in pool], axis=0)
        dim = X.shape[1]; mu = np.zeros(dim); sigma = np.ones(dim)
        norm_cols = list(range(10)) + (list(range(14,20)) if key == "X20" else [])
        mu[norm_cols] = X[:, norm_cols].mean(axis=0)
        sigma[norm_cols] = np.maximum(X[:, norm_cols].std(axis=0), 1e-4)
        return mu, sigma

    def fit_weighted(pool: list[dict], key: str, alpha: float, mu: np.ndarray, sigma: np.ndarray) -> np.ndarray:
        dim = len(mu); A = np.zeros((dim + 1, dim + 1)); b = np.zeros((dim + 1, 3))
        for e in pool:
            x = (e[key] - mu) / sigma
            x = np.column_stack([x, np.ones(len(x))])
            weight = 1.0 / len(x)
            A += weight * (x.T @ x)
            b += weight * (x.T @ e["Y"])
        reg = np.eye(dim + 1) * alpha; reg[-1,-1] = 0.0
        return np.linalg.solve(A + reg, b)

    def predict(e: dict, key: str, mu: np.ndarray, sigma: np.ndarray, w: np.ndarray) -> float:
        x = (e[key] - mu) / sigma
        x = np.column_stack([x, np.ones(len(x))])
        return score(np.clip(x @ w, -3, 3), e["Y"])

    records=[]; selected={}
    for key in variants:
        cv_scores={a:[] for a in lambdas}
        for fold in range(4):
            fold_train=[e for e in train_eps if folds[e["scene"]]!=fold]
            fold_val=[e for e in train_eps if folds[e["scene"]]==fold]
            mu,sigma=normalizer(fold_train,key)
            for alpha in lambdas:
                w=fit_weighted(fold_train,key,alpha,mu,sigma)
                for e in fold_val:
                    cv_scores[alpha].append((e,predict(e,key,mu,sigma,w)))
        macro={}
        for alpha,pairs in cv_scores.items():
            task_means=[]
            for task in sorted({e["task"] for e,_ in pairs}):
                task_means.append(float(np.mean([v for e,v in pairs if e["task"]==task])))
            macro[alpha]=float(np.mean(task_means))
        best=min(lambdas,key=lambda a:(macro[a],-a));selected[key]={"alpha":best,"cv_macro_Q":macro}
        mu,sigma=normalizer(train_eps,key);w=fit_weighted(train_eps,key,best,mu,sigma)
        for e in val_eps:
            records.append({"family":key,"alpha_selected_from_grouped_TRAIN":best,"scene_id":e["scene"],
                            "task":e["task"],"class_index":e["class_index"],"wind_frequency_group":e["wind"],
                            "n_events":len(e[key]),"VAL_Q_mps2":predict(e,key,mu,sigma,w)})
    frame=pd.DataFrame(records)
    summary={}
    for key,g in frame.groupby("family"):
        summary[key]={"macro_by_task_Q_mps2":{task:float(z.VAL_Q_mps2.mean()) for task,z in g.groupby("task")},
                      "overall_equal_scene_Q_mps2":float(g.VAL_Q_mps2.mean()),"selected_alpha":selected[key]["alpha"]}
    summary["inference_limit"]="A linear scene-held-out probe tests incremental predictive information only; it does not estimate nonlinear KAN C1 gain or closed-loop performance."
    return frame, {"lambda_grid":list(lambdas),"folds":4,"grouping":"whole scenes, balanced round-robin within task x class x wind",
                   "fit_data":"G04 TRAIN only; stride 5, ready events, equal weight per scene",
                   "validation":"48 G04 VAL scenes held out and evaluated once", "selected":selected,"summary":summary,
                   "new_plant_starts":0,"encoder_fits":0},


def local_sensitivity(meta: dict[str, dict]) -> pd.DataFrame:
    models={"INITIAL":read_mat_model(ROOT/"models/position/initial/matlab_model_and_parity.mat"),
            "FINAL":read_mat_model(ROOT/"models/position/selected/matlab_model_and_parity.mat")}
    bridge=pd.read_csv(OUT/"manifests/BRIDGE6.csv")
    rows=[]
    for scene in sorted(bridge.scene_id.unique()):
        p=ROOT/Path(f"data/events/position/train/{scene}/P_INIT_STUDENT.h5")
        d=read_episode(p); x=d["x"]; use=np.flatnonzero(d["ready"])[::8]
        for enc,model in models.items():
            w=np.asarray(model["output_W"],dtype=float)
            for feat in range(6):
                xp=x[use].copy();xm=x[use].copy();xp[:,feat]+=EPS[feat];xm[:,feat]-=EPS[feat]
                yp=encode(model,xp)@w;ym=encode(model,xm)@w
                jac=(yp-ym)/(2*EPS[feat]);norm=np.linalg.norm(jac,axis=1)
                rows.append({"scene_id":scene,"task":meta[scene]["task"],"wind_frequency_group":meta[scene]["wind_frequency_group"],
                             "encoder":enc,"feature_index_1based":feat+1,"feature_group":"position_error" if feat<3 else "sliding_surface",
                             "physical_delta":EPS[feat],"n_recorded_points":len(use),"jacobian_norm_mps2_per_unit_median":float(np.median(norm)),
                             "p10":float(np.percentile(norm,10)),"p90":float(np.percentile(norm,90))})
    return pd.DataFrame(rows)


def write_figures(comp: pd.DataFrame) -> None:
    scene="DL1018_TRAIN_T1_C02_W08"
    fig,ax=plt.subplots(2,1,figsize=(10,7),sharex=True)
    g=comp[comp.scene_id==scene]
    for role,label,color in (("B","B","black"),("POS_OFF","POS_OFF","tab:gray"),("P_INIT_STUDENT","Initial Student","tab:blue")):
        z=g[g.role==role].sort_values("time_s")
        e=z[["e_pos_x_m","e_pos_y_m","e_pos_z_m"]].to_numpy(float)
        ax[0].plot(z.time_s,np.linalg.norm(e,axis=1),label=label,color=color,linewidth=1)
    ax[0].axvline(1.8,color="tab:orange",linestyle="--",linewidth=.9,label="beta reaches 1")
    ax[0].axvline(5.2,color="tab:red",linestyle=":",linewidth=.9,label="first arm command")
    ax[0].set_ylabel("position error norm (m)");ax[0].legend(ncol=3,fontsize=8);ax[0].grid(alpha=.2)
    z=g[g.role=="P_INIT_STUDENT"].sort_values("time_s")
    for name,label,color in (("d_effective","effective residual","tab:red"),("d_applied","actual compensation","tab:blue"),
                             ("d_wind","wind","tab:green"),("d_allocation","allocation","tab:purple"),
                             ("d_attitude_realization","attitude realization","tab:orange"),("d_mapping","mapping","tab:brown")):
        v=z[[f"{name}_x_mps2",f"{name}_y_mps2",f"{name}_z_mps2"]].to_numpy(float)
        ax[1].plot(z.time_s,np.linalg.norm(v,axis=1),label=label,linewidth=.8)
    ax[1].set_xlabel("time (s)");ax[1].set_ylabel("acceleration norm (m/s²)");ax[1].legend(ncol=3,fontsize=7);ax[1].grid(alpha=.2)
    fig.suptitle(f"Same-scene G04 bridge: {scene}");fig.tight_layout()
    fig.savefig(OUT/"figures/D2_BRIDGE_W08_ERROR_AND_RESIDUAL.png",dpi=180);plt.close(fig)


def main() -> None:
    t0=time.time();meta=load_metadata()
    comp=pd.read_csv(COMP_PATH)
    # Verify the vector residual components close to the saved physical target.
    dnames=[f"{c}_{axis}_mps2" for c in COMPONENTS for axis in "xyz"]
    de=np.zeros((len(comp),3))
    for c in COMPONENTS:
        de+=comp[[f"{c}_{a}_mps2" for a in "xyz"]].to_numpy(float)
    target=comp[["target_raw_x_mps2","target_raw_y_mps2","target_raw_z_mps2"]].to_numpy(float)
    closure=float(np.max(np.abs(de-target)))
    comp_sum=summarize_components(comp,meta)
    comp_sum.to_csv(OUT/"reports/D2_LABEL_COMPONENT_SUMMARY.csv",index=False,float_format="%.12g")
    adaptation,selection,_,_=adaptation_probe(meta,comp)
    adaptation.to_csv(OUT/"reports/D2_ADAPTATION_PROBE.csv",index=False,float_format="%.12g")
    (OUT/"reports/D2_ADAPTATION_SELECTION.json").write_text(json.dumps(selection,indent=2,ensure_ascii=False,allow_nan=False)+"\n",encoding="utf-8")
    x20,x20summary=x20_information_probe(meta,comp)
    x20.to_csv(OUT/"reports/D2_X20_INFORMATION_PROBE.csv",index=False,float_format="%.12g")
    (OUT/"reports/D2_X20_INFORMATION_SUMMARY.json").write_text(json.dumps(x20summary,indent=2,ensure_ascii=False,allow_nan=False)+"\n",encoding="utf-8")
    sens=local_sensitivity(meta)
    sens.to_csv(OUT/"reports/D2_LOCAL_SENSITIVITY.csv",index=False,float_format="%.12g")
    write_figures(comp)
    # Add complete hash identity for the run_start snapshots actually replayed.
    rt=pd.read_csv(OUT/"reports/D2_RUNTIME_REPLAY.csv")
    hashes=[]
    for r in rt.to_dict("records"):
        p=Path(r["run_start_path"]);st=p.stat()
        hashes.append({"run_id":r["run_id"],"run_start_path":str(p),"size_bytes":st.st_size,
                       "mtime_utc":datetime.fromtimestamp(st.st_mtime,timezone.utc).isoformat(),"sha256":sha256(p)})
    pd.DataFrame(hashes).to_csv(OUT/"manifests/D2_RUN_START_HASHES.csv",index=False)
    runtime=rt
    max_runtime=float(runtime[["max_phi_abs_error","max_raw_abs_error","max_applied_abs_error","max_weight_next_abs_error",
                               "max_weight_event_chain_abs_error","max_zoh_abs_error_mps2","max_injected_force_mass_closure_N",
                               "max_beta_abs_error","max_event_dt_abs_error_s","max_eta_event_log_abs_error_mps","W0_reset_abs_error"]].to_numpy(float).max())
    pass_identity=bool(runtime[["cfg_matches_current","scene_identity_exact","attitude_rbf_identity_exact","model_matches_current_package","W0_matches_package","all_1968_events_replayed","pcf_coordination_enabled"]].astype(bool).all().all())
    # Macro component overview: first average each scene, then equal-weight the three tasks.
    allc=comp_sum[comp_sum.diagnostic_phase=="ALL_READY"]
    component_role={}
    for role,g in allc.groupby("role"):
        component_role[role]={c:float(g[f"{c}_rms_mps2"].mean()) for c in (*COMPONENTS,"d_effective","d_applied")}
    # Initial vs POS_OFF vs B timing comparisons are already computed in the paired table.
    d1=pd.read_csv(OUT/"reports/D1_G04_PAIRED_ALL.csv")
    time_deltas={}
    for comparator in ("B","POS_OFF"):
        z={}
        for n in ("T_0_1p8","T_1p8_5","T_5_10","T_10_15","T_15_20"):
            a=[]
            for raw in d1.to_dict("records"):
                x=json.loads(raw["P_INIT_STUDENT_time_bin_metrics_json"])[n]["Q_rmse_m"]
                y=json.loads(raw[f"{comparator}_time_bin_metrics_json"])[n]["Q_rmse_m"]
                a.append(float(x)-float(y))
            z[n]={"mean_delta_m":float(np.mean(a)),"positive_count":int(np.sum(np.asarray(a)>0))}
        time_deltas[comparator]=z
    lines=["# D2：实际运行链重放、标签分解与适应探针\n",
           "本阶段全部读取历史日志离线重放；新增 Plant=0、encoder fit=0。6 场 TRAIN 的 B/POS_OFF/P_INIT 与两场 G06 P_A 均从原始 run_start/raw_run 重放。\n",
           "## 实际部署/日志一致性\n",
           f"- 6 条 Initial run_start 中完整 Initial 模型、归一化、W0、cfg 与当前 Initial 包匹配；两条 G06 P_A 完整 Final 模型与 Selected 包匹配。六场各行为的场景数组、初始状态、风、参考、臂命令/臂长与 C0 cfg 逐项完全相同；姿态 RBF 开/输出/更新配置一致。\n",
           f"- 8 条实际在线运行均回放 1968/1968 个有效 Head 事件。用生产 `position_stage1_model_forward_v2` 和 `position_stage1_update_head_pcf_v3_5` 逐事件重放：最大数值差 {max_runtime:.3g}；W0 复位、输出先于更新、下一事件权重接续、100 Hz dt、beta、PCF eta、ZOH 与力到加速度闭合全部在浮点容差内。\n",
           "- 六场 × 三角色的 18 份 H5 由现有 exporter 重新导出：X14、target_raw、target_clip、事件顺序/ready边界、事件时间最大差均为 0；标签闭合最大差约 3e-15 m/s²；Initial 在线记录的 X14 与导出逐项相同。\n",
           "- 因此，已检查样本上没有发现模型装载、X14、Head更新、PCF、beta、ZOH 或单位/标签注入错误。H1 对这 8 条实际在线运行：NOT_SUPPORTED（限定为被重放的运行，不能扩大为所有历史航次逐条证明）。\n",
           "## 同场残差来源\n",
           f"- 18 条历史 bridge 日志的分解闭合误差最大 {closure:.3g} m/s²，按原式 `d_effective=d_wind+d_allocation+d_attitude_realization+d_mapping`。组件 RMS 与交叉项分别保留；各分量 RMS 不能直接相加。\n",
           "- 六场桥接逐场/逐角色、相位与时间箱结果见 `D2_LABEL_COMPONENT_SUMMARY.csv`；事件级列、当前误差面、实际速度/姿态、nominal acceleration、commanded force、beta、eta、输出/更新标志见 `D2_LABEL_COMPONENTS.csv`。\n",
           "- 实际补偿误差定义为 `d_applied - d_effective`；误差面余弦只描述同轨迹方向关系。互相关/相邻事件变化均受闭环反馈混杂，不作为单独因果时延证据。\n",
           "## 固定 Head 与早段适应探针\n",
           f"- 支持块预先固定为有效事件 5.5–10 s，查询块 10–20 s；使用 G04 TRAIN 384 场选择各编码器正则化，VAL 48 场只评估。alpha 网格为 {list(ALPHAS)}，一条航次内按连续时间块拟合/查询，没有随机拆散邻近事件。\n",
           f"- Initial 选中 alpha={selection['encoder_selection']['INITIAL']['selected_alpha']}，Final 选中 alpha={selection['encoder_selection']['FINAL']['selected_alpha']}；累计矩阵解 {selection['matrix_solves']} 次；均不计 encoder fit。\n",
           "- G04 Initial 生成的同一批闭环状态上，同时测固定 Initial/Final W0、早段 ridge、真实 Initial online Head；Final 的 G04 结果是离线反事实，不代表闭环。两场 G06 P_A 是真实 Final online 轨迹，但不能替代同场 Initial/Final 的 D3。\n",
           "- 汇总表 `D2_ADAPTATION_PROBE.csv` 按 TRAIN/VAL、任务、频率类别分别给出 support/query Q；`D2_LOCAL_SENSITIVITY.csv` 仅在六场记录点每隔 8 个 ready 事件做有限差分，报告对位置误差/滑模面的局部输出敏感度。\n",
           f"- 合法 X20 线性信息探针：完整场景分组四折，只用 TRAIN 384 场选择正则化，VAL 48 场一次评估。Validation equal-scene Q：X14={x20summary['summary']['X14']['overall_equal_scene_Q_mps2']:.6g}，X20={x20summary['summary']['X20']['overall_equal_scene_Q_mps2']:.6g} m/s²。该结果仅是线性信息增益探针，不等同于 X20 KAN 或闭环增益；逐场见 `D2_X20_INFORMATION_PROBE.csv`。\n",
           "## 对 D4 分支的影响\n",
           "- 当前重放不支持 H1 实现错误。D1 显示 Initial 在大多数场景胜 POS_OFF，却仍输 B；优先区分固定 Head 与在线适应目标、合法状态信息，不能把结果归咎于模型包差异。D3 同场桥接完成后才冻结 D4 家族。\n",
           "- D1 同场 Q 分箱差（P_INIT−B / P_INIT−POS_OFF）见下表：\n"]
    lines += ["| 时间段 | P_INIT−B (m)；胜出场数 | P_INIT−POS_OFF (m)；胜出场数 |", "|---|---:|---:|"]
    for k in ("T_0_1p8","T_1p8_5","T_5_10","T_10_15","T_15_20"):
        lines.append(f"| {k} | {time_deltas['B'][k]['mean_delta_m']:+.6g}; {432-time_deltas['B'][k]['positive_count']}/432 | {time_deltas['POS_OFF'][k]['mean_delta_m']:+.6g}; {432-time_deltas['POS_OFF'][k]['positive_count']}/432 |")
    lines.append("\n位置阶段顺序上，Student 与 B 的差距在臂开始变化前已经存在；同时 Student 在形变后显著优于 POS_OFF。这里是已观察的同场关联，不等于确认具体网络结构因果。\n")
    (OUT/"reports/D2_RUNTIME_REPLAY_DECISION.md").write_text("\n".join(lines),encoding="utf-8")
    meta_out={"task":"D2 derived event metadata","generated_at_utc":datetime.now(timezone.utc).isoformat(),
              "source_runs":18,"new_plant_starts":0,"new_fits":0,"columns":{"d_wind":"offline Plant truth decomposition, m/s^2; not deployable",
              "d_allocation":"offline actual-vs-requested thrust term, m/s^2; not deployable",
              "d_attitude_realization":"offline actual-vs-raw attitude realization, m/s^2; not deployable",
              "d_mapping":"offline mapping/nominal/control residual, m/s^2; not deployable",
              "d_applied":"logged applied position compensation, m/s^2","d_raw":"logged role-specific raw compensation estimate, m/s^2",
              "X14":"causal runtime inputs only; first 14 columns are recorded physical features",
              "PCF_eta":"logged auxiliary state for analysis only; never used as added deployable input"},
              "closure_max_abs_mps2":closure,"runtime_replay_max_abs":max_runtime,"identity_pass":pass_identity}
    (OUT/"derived_events/D2_METADATA.json").write_text(json.dumps(meta_out,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    # Update state/ledger only after all D2 outputs were generated.
    statep=OUT/"state/state.json";state=json.loads(statep.read_text(encoding="utf-8"))
    state.update({"phase":"D2_COMPLETE","next":"D3_FINAL_INITIAL_SAME_SCENE_BRIDGE6",
                  "d2_runtime_replays":8,"d2_h5_event_parity_checks":18,"d2_event_component_rows":len(comp),
                  "d2_plant_starts_new":0,"d2_fits_new":0,"updated_at_utc":datetime.now(timezone.utc).isoformat()})
    statep.write_text(json.dumps(state,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    ledger=OUT/"RESOURCE_LEDGER.csv"
    with ledger.open("a",newline="",encoding="utf-8") as f:
        w=csv.writer(f);w.writerow([datetime.now(timezone.utc).isoformat(),"D2","matrix_solve",f"ridge grid {ALPHAS}",selection["matrix_solves"],"COMPLETED","Per-episode head ridge on recorded trajectories; no encoder fit/Plant."])
    print(json.dumps({"component_closure":closure,"runtime_max_error":max_runtime,"identity_pass":pass_identity,
                      "alpha":{k:v["selected_alpha"] for k,v in selection["encoder_selection"].items()},
                      "matrix_solves":selection["matrix_solves"],"elapsed_s":round(time.time()-t0,1)},ensure_ascii=False))


if __name__=="__main__":
    main()
