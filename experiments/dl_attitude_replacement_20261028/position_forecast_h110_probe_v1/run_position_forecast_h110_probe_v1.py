#!/usr/bin/env python3
"""Offline C5 position forecast probe; reads only the pinned TRAIN24/VAL48 raw manifests."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import h5py
import numpy as np


ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
TRAIN_MANIFEST = ROOT / "experiments/dl_attitude_replacement_20261027/mlp15_nominal_residual_v1/TRAIN_C5_24_PHYSICAL_RESIDUAL_MANIFEST_v1.json"
VAL_FREEZE = ROOT / "experiments/dl_attitude_replacement_20261027/mlp15_nominal_residual_v1/C5_VAL48_OFFLINE_DIAGNOSTIC_v1/C5_VAL48_SOURCE_FREEZE_v1.json"
TRAIN_LOCK = ROOT / "experiments/position_axis_coordinate_c5_dev72_20261023/C5_DEV72_INPUT_LOCK_v3.json"
VAL_LOCK = ROOT / "experiments/position_axis_coordinate_c5_20261023/C5_AXIS_COORDINATE_INPUT_LOCK_v1.json"
LAMBDA = 0.001
CLIP = np.array([3.0, 3.0])  # pinned runtime asserts position dmax == [3, 3, 3] m/s^2
LABEL = "log/stage1_position_delayed_prediction_target_mps2"
PHI = "log/stage1_position_event_phi_33"
EVENT_VALID = "log/stage1_position_event_inference_valid"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_text_u16(ds: h5py.Dataset) -> str:
    return "".join(chr(int(c)) for c in np.asarray(ds).ravel(order="C") if c)


def load_scene(rec: dict, split: str, expected_models: list[dict]) -> dict:
    raw = ROOT / rec["raw_path"]
    assert raw.is_file(), f"missing raw: {raw}"
    raw_hash = sha256(raw)
    assert raw_hash == rec["raw_sha256"], f"raw hash mismatch: {rec['scene_id']}"
    with h5py.File(raw, "r") as f:
        for name in (PHI, LABEL, EVENT_VALID, "log/stage1_position_event", "log/stage1_position_event_step_index",
                     "log/stage1_position_delayed_prediction_prev_index_zero_based",
                     "log/stage1_position_event_raw_acceleration_mps2", "log/stage1_position_search_initial_weight",
                     "runIdentity/scene_id", "runIdentity/input_lock_sha256", "log/transition_time"):
            assert name in f, f"{rec['scene_id']} missing {name}"
        g = f["log"]
        phi = np.asarray(g[PHI.removeprefix("log/")], dtype=np.float64)
        phi_all = np.asarray(g["stage1_position_phi_33"], dtype=np.float64)
        y = np.asarray(g[LABEL.removeprefix("log/")], dtype=np.float64)
        valid = np.asarray(g[EVENT_VALID.removeprefix("log/")]).ravel() != 0
        event = np.asarray(g["stage1_position_event"]).ravel() != 0
        step = np.asarray(g["stage1_position_event_step_index"]).ravel()
        prev = np.asarray(g["stage1_position_delayed_prediction_prev_index_zero_based"]).ravel()
        online = np.asarray(g["stage1_position_event_raw_acceleration_mps2"], dtype=np.float64)
        w0 = np.asarray(g["stage1_position_search_initial_weight"], dtype=np.float64)
        times = np.asarray(g["transition_time"]).ravel()
        raw_scene = read_text_u16(f["runIdentity/scene_id"])
        input_lock_hash = read_text_u16(f["runIdentity/input_lock_sha256"])
        expected_model = next((x for x in expected_models if x["input_lock_sha256"] == input_lock_hash), None)
        assert expected_model is not None, f"unrecognized C5 input lock: {rec['scene_id']} {input_lock_hash}"
        w0_hash = read_text_u16(f["runIdentity/initial_W0_sha256"]) if "runIdentity/initial_W0_sha256" in f else (
            read_text_u16(f["runIdentity/W0_sha256"]) if "runIdentity/W0_sha256" in f else expected_model["W0_sha256"])
        normalizer_hash = read_text_u16(f["runIdentity/model_identity/normalizer_arrays_sha256"]) if \
            "runIdentity/model_identity/normalizer_arrays_sha256" in f else expected_model["normalizer_arrays_sha256"]
        identity_w0_hash = read_text_u16(f["runIdentity/model_identity/W0_sha256"]) if \
            "runIdentity/model_identity/W0_sha256" in f else expected_model["W0_sha256"]

    assert raw_scene == rec["scene_id"], f"scene identity mismatch: {rec['scene_id']} != {raw_scene}"
    assert input_lock_hash == expected_model["input_lock_sha256"], f"C5 input lock mismatch: {rec['scene_id']}"
    assert phi.shape == phi_all.shape == (33, 20000) and y.shape == (3, 20000) and online.shape == (3, 20000)
    assert w0.shape == (3, 33) and len(times) == 20000
    event_idx = np.flatnonzero(event)
    valid_idx = np.flatnonzero(valid)
    assert np.array_equal(event_idx, np.arange(10, 20000, 10)), rec["scene_id"]
    assert np.all(np.isin(valid_idx, event_idx)) and len(valid_idx) > 0
    assert np.array_equal(step, valid_idx + 1), f"MATLAB one-based event index mismatch: {rec['scene_id']}"
    assert np.allclose(times[valid_idx], valid_idx * 0.001, rtol=0, atol=1e-12)
    assert np.array_equal(phi[:, valid_idx], phi_all[:, valid_idx]), f"normalized runtime phi mismatch: {rec['scene_id']}"

    # H0 label is the completed [j, j+10] event interval; H110 is [j+110, j+120].
    # Keep only events where the current past label and both future labels exist.
    idx = valid_idx[(valid_idx + 120 < len(y[0]))]
    keep = (np.all(np.isfinite(phi[:, idx]), axis=0)
            & np.all(np.isfinite(y[:, idx]), axis=0)
            & np.all(np.isfinite(y[:, idx + 10]), axis=0)
            & np.all(np.isfinite(y[:, idx + 120]), axis=0)
            & np.all(np.isfinite(online[:, idx]), axis=0))
    idx = idx[keep]
    assert len(idx) > 0, f"no common prediction events: {rec['scene_id']}"
    for delta in (10, 120):
        k = idx + delta
        assert np.all(event[k]) and np.all(np.isfinite(prev[k]))
        assert np.array_equal(prev[k], k - 10), f"target endpoint/index mismatch at H{delta}: {rec['scene_id']}"
    assert np.all(np.isfinite(prev[idx])) and np.array_equal(prev[idx], idx - 10)

    # In MATLAB the logged 33x3 W0 is column-major; the HDF5 view is [3,33].
    w0_actual_hash = hashlib.sha256(np.asarray(w0, dtype="<f8").ravel(order="C").tobytes()).hexdigest()
    assert w0_actual_hash == w0_hash == identity_w0_hash == expected_model["W0_sha256"], \
        f"W0 numeric hash mismatch: {rec['scene_id']}"
    assert normalizer_hash == expected_model["normalizer_arrays_sha256"], f"normalizer identity mismatch: {rec['scene_id']}"
    assert np.allclose(w0 @ phi[:, valid_idx[0]], online[:, valid_idx[0]], rtol=0, atol=1e-12), \
        f"W0*phi does not reproduce the recorded raw head output: {rec['scene_id']}"
    return {
        "scene_id": rec["scene_id"], "split": split, "raw_path": rec["raw_path"],
        "raw_sha256": raw_hash, "input_lock_sha256": input_lock_hash,
        "w0_sha256": w0_hash, "normalizer_sha256": normalizer_hash,
        "j": idx, "phi": phi[:, idx].T, "y_h0": y[:, idx + 10].T[:, :2],
        "y_h110": y[:, idx + 120].T[:, :2], "y_past": y[:, idx].T[:, :2],
        "online_raw": online[:, idx].T[:, :2], "w0_xy": w0[:2, :].T,
    }


def fit_ridge(rows: list[dict], target: str) -> tuple[np.ndarray, float, int]:
    x = np.concatenate([r["phi"] for r in rows])
    y = np.concatenate([r[target] for r in rows])
    w0 = rows[0]["w0_xy"]
    assert all(np.array_equal(r["w0_xy"], w0) for r in rows)
    gram = x.T @ x / len(x)
    rhs = x.T @ y / len(x) + LAMBDA * w0
    w = np.linalg.solve(gram + LAMBDA * np.eye(33), rhs)
    objective = float(np.mean((x @ w - y) ** 2) * y.shape[1] + LAMBDA * np.sum((w - w0) ** 2))
    return w, objective, len(x)


def metric(pred: np.ndarray, target: np.ndarray) -> dict:
    e = pred - target
    return {"xy_rmse_mps2": float(np.sqrt(np.mean(np.sum(e * e, axis=1)))),
            "x_rmse_mps2": float(np.sqrt(np.mean(e[:, 0] ** 2))),
            "y_rmse_mps2": float(np.sqrt(np.mean(e[:, 1] ** 2)))}


def group(scene_id: str) -> str:
    wind = int(scene_id.rsplit("W", 1)[1])
    return "HF_W09_W14" if 9 <= wind <= 14 else ("W15" if wind == 15 else "W00_W08")


def main() -> None:
    train_meta = json.loads(TRAIN_MANIFEST.read_text(encoding="utf-8"))
    val_meta = json.loads(VAL_FREEZE.read_text(encoding="utf-8"))
    assert train_meta["train_split"] == "TRAIN_C5_24" and len(train_meta["records"]) == 24
    assert val_meta["validation_split"] == "C5_VAL48" and len(val_meta["records"]) == 48
    assert not train_meta.get("TEST_read", True) and not val_meta.get("TEST_accessed", True)
    models = {}
    for split, path in (("TRAIN_C5_24", TRAIN_LOCK), ("C5_VAL48_OLD", VAL_LOCK)):
        lock = json.loads(path.read_text(encoding="utf-8"))
        identity = lock["candidate_identity"]
        assert identity["id"] == "DSSM14" and identity["input_dim"] == 14 and identity["window"] == 32
        models[split] = {"input_lock_sha256": sha256(path), **identity}
    assert models["TRAIN_C5_24"]["W0_sha256"] == models["C5_VAL48_OLD"]["W0_sha256"]
    assert models["TRAIN_C5_24"]["normalizer_arrays_sha256"] == models["C5_VAL48_OLD"]["normalizer_arrays_sha256"]
    train = [load_scene(r, "TRAIN_C5_24", [models["TRAIN_C5_24"]]) for r in train_meta["records"]]
    val = [load_scene(r, "C5_VAL48", [models["TRAIN_C5_24"], models["C5_VAL48_OLD"]]) for r in val_meta["records"]]
    assert {r["scene_id"] for r in train}.isdisjoint({r["scene_id"] for r in val})
    identity = {(r["w0_sha256"], r["normalizer_sha256"]) for r in train + val}
    assert len(identity) == 1, "C5 W0/normalizer identity changes across scenes"

    w_h0, obj_h0, n_train = fit_ridge(train, "y_h0")
    w_h110, obj_h110, n_h110_train = fit_ridge(train, "y_h110")
    assert n_train == n_h110_train
    candidates = ("H110_ridge", "H0_ridge", "W0_prior", "past_label_persistence", "C5_online_raw_prebeta_preclip")
    preds: dict[str, dict[str, np.ndarray]] = {}
    scene_rows = []
    for r in val:
        raw = {"H110_ridge": r["phi"] @ w_h110,
               "H0_ridge": r["phi"] @ w_h0,
               "W0_prior": r["phi"] @ r["w0_xy"],
               "past_label_persistence": r["y_past"],
               "C5_online_raw_prebeta_preclip": r["online_raw"]}
        truth = r["y_h110"]
        preds[r["scene_id"]] = {k: np.clip(v, -CLIP, CLIP) for k, v in raw.items()}
        for name in candidates:
            scene_rows.append({"split": r["split"], "scene_id": r["scene_id"], "group": group(r["scene_id"]),
                               "target": "Y_H110_mps2", "predictor": name, "n_events": len(truth),
                               **metric(preds[r["scene_id"]][name], truth)})

    groups = {"ALL48": [r["scene_id"] for r in val]}
    for g in ("HF_W09_W14", "W15", "W00_W08"):
        groups[g] = [r["scene_id"] for r in val if group(r["scene_id"]) == g]
    summary = {}
    for g, ids in groups.items():
        summary[g] = {}
        for name in candidates:
            metrics = [next(x for x in scene_rows if x["scene_id"] == sid and x["predictor"] == name) for sid in ids]
            pooled = metric(np.concatenate([preds[sid][name] for sid in ids]),
                            np.concatenate([next(r["y_h110"] for r in val if r["scene_id"] == sid) for sid in ids]))
            summary[g][name] = {"n_scenes": len(ids), "n_events": int(sum(x["n_events"] for x in metrics)),
                                "macro_scene_rmse_xy_mps2": float(np.mean([x["xy_rmse_mps2"] for x in metrics])),
                                "macro_scene_x_rmse_mps2": float(np.mean([x["x_rmse_mps2"] for x in metrics])),
                                "macro_scene_y_rmse_mps2": float(np.mean([x["y_rmse_mps2"] for x in metrics])),
                                "pooled": pooled}

    train_fit = {}
    for name, w, yname, obj in (("H0_ridge", w_h0, "y_h0", obj_h0), ("H110_ridge", w_h110, "y_h110", obj_h110)):
        x = np.concatenate([r["phi"] for r in train])
        y = np.concatenate([r[yname] for r in train])
        train_fit[name] = {"target": yname, "n_events": len(x), "objective": obj,
                           "unclipped_train_rmse_xy_mps2": metric(x @ w, y)["xy_rmse_mps2"]}

    np.savez_compressed(OUT / "POSITION_FORECAST_H110_WEIGHTS_v1.npz",
                        W0_xy=train[0]["w0_xy"], W_H0=w_h0, W_H110=w_h110,
                        lambda_=np.array(LAMBDA), clip_xy_mps2=CLIP)
    with (OUT / "POSITION_FORECAST_H110_SCENE_METRICS_v1.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(scene_rows[0]))
        writer.writeheader(); writer.writerows(scene_rows)

    result = {
        "schema": "DL1018_POSITION_FORECAST_H110_PROBE_V1", "status": "OFFLINE_DEVELOPMENT_DIAGNOSTIC",
        "protocol": {"feature": "logged frozen C5 stage1_position_event_phi_33 at event j only",
                     "label": "logged stage1_position_delayed_prediction_target_mps2 XY",
                     "h0_label_index": "k=j+10, target is completed [j,j+10] 1ms event interval",
                     "h110_label_index": "k=j+120, target is completed [j+110,j+120] interval",
                     "past_baseline_index": "k=j, label interval is completed [j-10,j] and available at event j",
                     "ridge_objective": "mean(sum((Phi W - Y)^2, output_axis)) + 0.001*||W-W0||_F^2",
                     "lambda": LAMBDA, "clip_xy_mps2": CLIP.tolist(), "z": "not fitted or changed",
                     "fit_split": "TRAIN_C5_24 only", "evaluation_split": "C5_VAL48 only",
                     "sample_policy": "same finite event j set per scene for all predictors; feature rows use only phi[j]",
                     "val_status": "development diagnostic only; frozen C5 backbone already used development data",
                     "plant_calls_by_probe": 0, "TEST_accessed_by_probe": False,
                     "inertia_reconstructed": False, "large_network_trained": False},
        "sources": {"train_manifest": str(TRAIN_MANIFEST.relative_to(ROOT)), "train_manifest_sha256": sha256(TRAIN_MANIFEST),
                    "val_source_freeze": str(VAL_FREEZE.relative_to(ROOT)), "val_source_freeze_sha256": sha256(VAL_FREEZE),
                    "train_input_lock": str(TRAIN_LOCK.relative_to(ROOT)),
                    "train_input_lock_sha256": models["TRAIN_C5_24"]["input_lock_sha256"],
                    "val_input_locks": [{"path": str(p.relative_to(ROOT)), "sha256": sha256(p)} for p in (TRAIN_LOCK, VAL_LOCK)],
                    "train_raw_count_hash_verified": len(train), "val_raw_count_hash_verified": len(val),
                    "raw_input_lock_counts": {lock: sum(r["input_lock_sha256"] == lock for r in train + val)
                                               for lock in sorted({r["input_lock_sha256"] for r in train + val})},
                    "W0_sha256": next(iter(identity))[0], "normalizer_arrays_sha256": next(iter(identity))[1],
                    "train_raw_hashes": {r["scene_id"]: r["raw_sha256"] for r in train},
                    "val_raw_hashes": {r["scene_id"]: r["raw_sha256"] for r in val},
                    "val_raw_input_locks": {r["scene_id"]: r["input_lock_sha256"] for r in val}},
        "sample_counts": {"train_scenes": len(train), "train_events_per_scene_min_max":
                          [min(len(r["j"]) for r in train), max(len(r["j"]) for r in train)],
                          "train_events_total": n_train, "val_scenes": len(val),
                          "val_events_per_scene_min_max": [min(len(r["j"]) for r in val), max(len(r["j"]) for r in val)],
                          "val_events_total": int(sum(len(r["j"]) for r in val)),
                          "val_j_index_min_max": [min(int(r["j"][0]) for r in val), max(int(r["j"][-1]) for r in val)]},
        "train_fit_metrics": train_fit, "validation_H110_metrics": summary,
        "weights_file": "POSITION_FORECAST_H110_WEIGHTS_v1.npz",
        "weights_sha256": sha256(OUT / "POSITION_FORECAST_H110_WEIGHTS_v1.npz"),
        "scene_metrics_file": "POSITION_FORECAST_H110_SCENE_METRICS_v1.csv",
        "script_sha256": sha256(Path(__file__).resolve())}
    (OUT / "POSITION_FORECAST_H110_RESULTS_v1.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = ["# C5 位置 H110 离线因果预测探针", "",
             "这是开发诊断，不是独立验证或闭环结果。冻结 C5 backbone 已使用开发集；本探针只在 TRAIN_C5_24 拟合两组 ridge head，在 C5_VAL48 做离线诊断。", "",
             "## 方法与索引", "",
             "- 特征只取 C5 raw 中 `stage1_position_event_phi_33[:, j]`；逐场与同一时刻 runtime `stage1_position_phi_33` 精确相等，确认使用 DSSM 前向后的归一化特征。不把未来状态、未来输入、TEST 或惯量重建加入特征。",
             "- 标签字段为 `stage1_position_delayed_prediction_target_mps2` 的 XY 分量。原始 1ms 索引验证显示 H0 使用 `k=j+10`，该行的 `prev_index_zero_based=j`；H110 使用 `k=j+120`，其标签区间为 `[j+110,j+120]`，记录的前序索引为 `j+110`。过去标签基线取 `Y[j]`（区间 `[j-10,j]`），在预测时已可用。", 
             "- 两个 head 均最小化 `mean(sum((Phi W-Y)^2, XY)) + 0.001||W-W0||_F^2`，只拟合 XY；所有比较统一裁剪到 ±3 m/s²。Z 固定为 W0 原值，不拟合。", 
             "- 110ms 是由指令滤波器低频群延迟（2/18）设定的预测间隔；它不代表内环带宽。", "",
             "## 数据与身份", "",
             f"- TRAIN raw：{len(train)} 场，24 场清单 hash `{sha256(TRAIN_MANIFEST)}`；拟合事件数 {n_train}。",
             f"- VAL raw：{len(val)} 场，48 场 freeze hash `{sha256(VAL_FREEZE)}`；有效事件每场 {min(len(r['j']) for r in val)}–{max(len(r['j']) for r in val)}。全部 72 个 raw 均与各自 manifest SHA-256 相符。",
             f"- W0 SHA-256 `{next(iter(identity))[0]}`；归一化器数组 SHA-256 `{next(iter(identity))[1]}`。旧版 VAL raw 不总保存这两个 model_identity 字段，按 raw 的 input_lock SHA 绑定 C5 input lock，并逐场重算 W0 数组 hash；phi33 直接使用 runtime 已归一化的冻结 DSSM 输出。训练/验证 scene ID 不重叠。", "",
             "## TRAIN 拟合记录", "", "| Head | Target | N | 未裁剪训练 XY RMSE (m/s²) | Objective |", "|---|---|---:|---:|---:|"]
    for n, r in train_fit.items(): lines.append(f"| {n} | {r['target']} | {r['n_events']} | {r['unclipped_train_rmse_xy_mps2']:.6g} | {r['objective']:.6g} |")
    lines += ["", "## VAL48：全部对同一 H110 标签评分", "", "XY RMSE (m/s²)，候选使用相同有效事件与 ±3 m/s² 输出裁剪。", "",
              "| Group | Scenes | Predictor | Macro scene RMSE | Pooled XY RMSE | X RMSE pooled | Y RMSE pooled |", "|---|---:|---|---:|---:|---:|---:|"]
    for g, models in summary.items():
        for name, m in models.items():
            lines.append(f"| {g} | {m['n_scenes']} | {name} | {m['macro_scene_rmse_xy_mps2']:.6g} | {m['pooled']['xy_rmse_mps2']:.6g} | {m['pooled']['x_rmse_mps2']:.6g} | {m['pooled']['y_rmse_mps2']:.6g} |")
    lines += ["", "逐场结果见 `POSITION_FORECAST_H110_SCENE_METRICS_v1.csv`；拟合权重见 `POSITION_FORECAST_H110_WEIGHTS_v1.npz`；完整来源与 hash 见 `POSITION_FORECAST_H110_RESULTS_v1.json`。", "",
              "**限制：** C5_VAL48 只作为开发诊断；不能据此声称独立验证、真实部署收益或闭环成功。探针没有启动 Plant、训练大网、读取 TEST 或重建惯量。", ""]
    (OUT / "POSITION_FORECAST_H110_REPORT_v1.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote results for {len(train)} TRAIN and {len(val)} VAL scenes; train_events={n_train}; val_events={result['sample_counts']['val_events_total']}")


if __name__ == "__main__":
    main()
