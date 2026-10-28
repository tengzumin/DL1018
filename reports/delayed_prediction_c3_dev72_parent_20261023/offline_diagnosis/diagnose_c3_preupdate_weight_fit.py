"""Fixed-input C3 W0 versus pre-update Wk residual-fit audit (no rollout)."""
import csv
import hashlib
import json
import sys
from pathlib import Path

import h5py
import numpy as np


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PARENT = ROOT / "reports" / "delayed_prediction_c3_dev72_parent_20261023"
MANIFEST_PATH = PARENT / "PARENT_C3_ALL72_RAW_MANIFEST.json"
Q_TABLE_PATH = PARENT / "PARENT_ALL288_METRICS.csv"
SUMMARY_PATH = PARENT / "PARENT_DEV72_SUMMARY.json"
LOCK_PATH = ROOT / "experiments" / "position_delayed_prediction_c3_dev72_20261023" / "C3_DEV72_INPUT_LOCK_v2.json"
COMMON_PATH = ROOT / "reports" / "delayed_prediction_c3_parent_20261023" / "common_input_residual.py"
SCENE_CSV = HERE / "C3_PREUPDATE_WEIGHT_FIT_PER_SCENE.csv"
GROUP_CSV = HERE / "C3_PREUPDATE_WEIGHT_FIT_GROUPS.csv"
SUMMARY_JSON = HERE / "C3_PREUPDATE_WEIGHT_FIT_SUMMARY.json"
REPORT_MD = HERE / "C3_PREUPDATE_WEIGHT_FIT_NOTE.md"
HASHES_JSON = HERE / "C3_PREUPDATE_WEIGHT_FIT_FILE_HASHES.json"


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_csv(path, rows, fields):
    with path.open("x", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def group_for(scene_id):
    parts = scene_id.split("_")
    task = parts[2]
    wind = int(parts[-1][1:])
    groups = ["ALL72"]
    if 9 <= wind <= 14:
        groups.append("HF28")
    if wind == 15:
        groups.append("W15")
    if task == "T2" and 9 <= wind <= 14:
        groups.append("T2-HF9")
    return groups


def main():
    outputs = [SCENE_CSV, GROUP_CSV, SUMMARY_JSON, REPORT_MD, HASHES_JSON]
    if any(p.exists() for p in outputs):
        raise FileExistsError("Preserve prior offline_diagnosis outputs; refusing overwrite")
    sys.path.insert(0, str(COMMON_PATH.parent))
    from common_input_residual import read as read_fixed_arrays

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8-sig"))
    manifest_sha = sha256(MANIFEST_PATH)
    assert manifest["scope"] == "C3_FROZEN_DEV72_12_REUSED_PLUS_60_NEW_NO_TEST"
    assert len(manifest["rows"]) == len(manifest["status_refs"]) == 72
    assert len({r["scene_id"] for r in manifest["rows"]}) == 72
    assert sha256(COMMON_PATH)
    verified_sources = []
    for ref in manifest["source_refs"]:
        p = Path(ref["path"])
        actual = sha256(p)
        assert actual == ref["sha256"], f"source identity mismatch: {p}"
        verified_sources.append({"path": str(p), "sha256": actual})
    assert sha256(LOCK_PATH) == next(
        ref["sha256"] for ref in manifest["source_refs"] if Path(ref["path"]).name == LOCK_PATH.name
    )
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8-sig"))
    expected_w0_sha = lock["candidate_identity"]["W0_sha256"]

    q_rows = {}
    with Q_TABLE_PATH.open("r", newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            key = (row["scene_id"], row["method"])
            if key in q_rows:
                raise AssertionError(f"duplicate pre-existing Q row: {key}")
            if row["method"] in ("B", "C3"):
                q_rows[key] = float(row["Q_0_20_m"])
    q_table_sha = sha256(Q_TABLE_PATH)
    status_by_scene = {s["path"]: s for s in manifest["status_refs"]}
    assert len(status_by_scene) == 72

    # Reuse the previously reviewed MAT array reader/target reconstruction.
    import common_input_residual
    common_reader_sha = sha256(COMMON_PATH)
    per_scene = []
    scene_arrays = {}
    all_w0_hashes = set()
    for row in manifest["rows"]:
        scene_id, raw_path = row["scene_id"], Path(row["path"])
        status_ref = next(s for s in manifest["status_refs"] if Path(s["path"]).parent == raw_path.parent)
        status_path = Path(status_ref["path"])
        assert sha256(status_path) == status_ref["sha256"], f"status hash mismatch: {scene_id}"
        status = json.loads(status_path.read_text(encoding="utf-8-sig"))
        assert status["scene_id"] == scene_id
        assert status["raw_path"] == str(raw_path)
        assert status["raw_sha256"] == row["sha256"]
        assert status["status"] == "RUN_COMPLETE_RAW_PENDING_AUDIT" and status["log_status"] == "STABLE"
        assert status["training_steps"] == status["optimizer_steps"] == 0
        assert status["TEST_accessed"] is False

        data = read_fixed_arrays(raw_path, row["sha256"])
        ids, phi, weights = data["ids"], data["phi"], data["W"]
        assert len(ids) == 1968 and np.array_equal(ids, np.arange(320, 19991, 10))
        j, k = ids[:-1], ids[1:]
        assert len(j) == 1967 and np.array_equal(k - j, np.full(1967, 10))
        y = np.array([(data["v"][kk] - data["v"][jj]) / 0.01 - data["af"][jj:kk].mean(0)
                      for jj, kk in zip(j, k)])
        with h5py.File(raw_path, "r") as h5:
            log = h5["log"]
            w0 = np.asarray(log["stage1_position_search_initial_weight"]).T.astype(np.float64, copy=False)
            w_initial = np.asarray(log["stage1_position_weight_initial"]).T.astype(np.float64, copy=False)
        assert w0.shape == (33, 3) and np.isfinite(w0).all()
        assert np.array_equal(w0, w_initial), f"logged W0 fields differ: {scene_id}"
        w0_sha = hashlib.sha256(np.asarray(w0, dtype="<f8").ravel(order="F").tobytes()).hexdigest()
        assert w0_sha == expected_w0_sha, f"logged W0 SHA mismatch: {scene_id}"
        all_w0_hashes.add(w0_sha)

        # W_k is the logged weight immediately before current event k;
        # the prediction is evaluated on the preceding event's phi_j.
        pred_online = np.einsum("nfi,nf->ni", weights[1:], phi[:-1])
        pred_w0 = np.einsum("fi,nf->ni", w0, phi[:-1])
        err_online, err_w0 = pred_online - y, pred_w0 - y
        assert np.isfinite(err_online).all() and np.isfinite(err_w0).all()
        current_t = k * 0.001
        masks = {
            "ALL_0_20": np.ones(len(k), dtype=bool),
            "EARLY_0.33_5": (current_t >= 0.33) & (current_t < 5.0),
            "LATE_5_20": (current_t >= 5.0) & (current_t < 20.0),
        }
        q_c3 = q_rows[(scene_id, "C3")]
        q_b = q_rows[(scene_id, "B")]
        scene_metrics = []
        for phase, mask in masks.items():
            for axis_i, axis in enumerate("XYZ"):
                e0, ew = err_w0[mask, axis_i], err_online[mask, axis_i]
                rec = {
                    "scene_id": scene_id,
                    "groups": ";".join(group_for(scene_id)),
                    "phase": phase,
                    "axis": axis,
                    "n_intervals": int(mask.sum()),
                    "W0_rmse_mps2": float(np.sqrt(np.mean(e0 ** 2))),
                    "W0_bias_mps2": float(np.mean(e0)),
                    "Wk_preupdate_rmse_mps2": float(np.sqrt(np.mean(ew ** 2))),
                    "Wk_preupdate_bias_mps2": float(np.mean(ew)),
                    "Wk_minus_W0_rmse_mps2": float(np.sqrt(np.mean(ew ** 2)) - np.sqrt(np.mean(e0 ** 2))),
                    "Wk_minus_W0_bias_mps2": float(np.mean(ew) - np.mean(e0)),
                    "Q_C3_existing_m": q_c3,
                    "Q_B_existing_m": q_b,
                    "Q_C3_minus_B_existing_m": q_c3 - q_b,
                    "raw_sha256": row["sha256"],
                    "status_sha256": status_ref["sha256"],
                    "W0_sha256": w0_sha,
                }
                scene_metrics.append(rec)
                per_scene.append(rec)
        scene_arrays[scene_id] = scene_metrics
    assert all_w0_hashes == {expected_w0_sha}

    group_order = ["ALL72", "HF28", "W15", "T2-HF9"]
    expected_sizes = {"ALL72": 72, "HF28": 28, "W15": 6, "T2-HF9": 9}
    grouped = {g: [s for s in scene_arrays if g in group_for(s)] for g in group_order}
    assert {g: len(ids) for g, ids in grouped.items()} == expected_sizes
    group_rows = []
    for group in group_order:
        ids = grouped[group]
        for phase in ("ALL_0_20", "EARLY_0.33_5", "LATE_5_20"):
            for axis in "XYZ":
                cells = [next(x for x in scene_arrays[s] if x["phase"] == phase and x["axis"] == axis) for s in ids]
                deltas = np.array([x["Wk_minus_W0_rmse_mps2"] for x in cells])
                q_c3 = np.array([next(x["Q_C3_existing_m"] for x in scene_arrays[s]) for s in ids])
                q_b = np.array([next(x["Q_B_existing_m"] for x in scene_arrays[s]) for s in ids])
                group_rows.append({
                    "group": group,
                    "n_scenes": len(ids),
                    "phase": phase,
                    "axis": axis,
                    "aggregation": "unweighted mean of per-scene metrics",
                    "n_intervals_per_scene": cells[0]["n_intervals"],
                    "W0_rmse_mps2_mean_scene": float(np.mean([x["W0_rmse_mps2"] for x in cells])),
                    "W0_bias_mps2_mean_scene": float(np.mean([x["W0_bias_mps2"] for x in cells])),
                    "Wk_preupdate_rmse_mps2_mean_scene": float(np.mean([x["Wk_preupdate_rmse_mps2"] for x in cells])),
                    "Wk_preupdate_bias_mps2_mean_scene": float(np.mean([x["Wk_preupdate_bias_mps2"] for x in cells])),
                    "Wk_minus_W0_rmse_mps2_mean_scene": float(np.mean(deltas)),
                    "scenes_Wk_rmse_lower_than_W0": int(np.sum(deltas < 0)),
                    "scenes_Wk_rmse_higher_than_W0": int(np.sum(deltas > 0)),
                    "scenes_equal_rmse": int(np.sum(deltas == 0)),
                    "existing_mean_C3_Q_m": float(np.mean(q_c3)),
                    "existing_mean_B_Q_m": float(np.mean(q_b)),
                    "existing_mean_Q_C3_minus_B_m": float(np.mean(q_c3 - q_b)),
                })

    scene_fields = list(per_scene[0].keys())
    group_fields = list(group_rows[0].keys())
    write_csv(SCENE_CSV, per_scene, scene_fields)
    write_csv(GROUP_CSV, group_rows, group_fields)

    get_group = lambda g, p, a: next(r for r in group_rows if r["group"] == g and r["phase"] == p and r["axis"] == a)
    t2z = {p: get_group("T2-HF9", p, "Z") for p in ("ALL_0_20", "EARLY_0.33_5", "LATE_5_20")}
    hfz = {p: get_group("HF28", p, "Z") for p in ("ALL_0_20", "EARLY_0.33_5", "LATE_5_20")}
    allz = {p: get_group("ALL72", p, "Z") for p in ("ALL_0_20", "EARLY_0.33_5", "LATE_5_20")}
    summary = {
        "schema": "C3_PREUPDATE_WEIGHT_FIT_DIAGNOSIS_V1",
        "plant_training_search_test": 0,
        "scope": "72 frozen C3 records; fixed recorded trajectory; no counterfactual rollout",
        "interval_target": "(v[k]-v[j])/0.01 - mean(a_f[j:k]); adjacent valid event pair j=k-10; units m/s^2",
        "weight_comparison": "trained W0 vs logged W_k immediately before current event k, both evaluated on the same earlier phi_j",
        "timing": {"all": "current k in [0.33,20) s", "early": "[0.33,5) s", "late": "[5,20) s", "intervals_per_run": 1967},
        "groups": {g: {"n_scenes": len(grouped[g]), "definition": {"ALL72": "all 72", "HF28": "wind W09-W14", "W15": "wind W15", "T2-HF9": "task T2 and wind W09-W14"}[g]} for g in group_order},
        "W0_sha256": expected_w0_sha,
        "T2_HF9_Z": t2z,
        "HF28_Z": hfz,
        "ALL72_Z": allz,
        "interpretation": "These are local residual-prediction fit metrics on the recorded C3 trajectory, not a counterfactual closed-loop test. A lower W_k residual does not establish adequate prediction, causal benefit, or application safety; a higher residual would not alone prove closed-loop causation.",
        "provenance": {
            "manifest": {"path": str(MANIFEST_PATH), "sha256": manifest_sha},
            "verified_manifest_source_refs": verified_sources,
            "common_input_residual_py": {"path": str(COMMON_PATH), "sha256": common_reader_sha},
            "input_lock": {"path": str(LOCK_PATH), "sha256": sha256(LOCK_PATH)},
            "preexisting_Q_table": {"path": str(Q_TABLE_PATH), "sha256_observed": q_table_sha, "usage": "read-only join of existing B and C3 Q; no Q recomputation"},
            "preexisting_summary": {"path": str(SUMMARY_PATH), "sha256_observed": sha256(SUMMARY_PATH)},
        },
    }
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8", newline="\n")

    tz = t2z["ALL_0_20"]
    if tz["Wk_minus_W0_rmse_mps2_mean_scene"] < 0:
        conclusion = (f"T2-HF9 的Z区间残差拟合中，更新前 Wk 相对 W0 的等场均值RMSE变化为 "
                     f"{tz['Wk_minus_W0_rmse_mps2_mean_scene']:.6g} m/s²；"
                     f"{tz['scenes_Wk_rmse_lower_than_W0']}/{tz['n_scenes']} 场更低。因此，‘在线更新损坏Z预测’这一简单解释不受该必要方向检验支持。")
    else:
        conclusion = (f"T2-HF9 的Z区间残差拟合中，更新前 Wk 相对 W0 的等场均值RMSE变化为 "
                     f"{tz['Wk_minus_W0_rmse_mps2_mean_scene']:.6g} m/s²；"
                     f"{tz['scenes_Wk_rmse_higher_than_W0']}/{tz['n_scenes']} 场更高。该观察只支持固定轨迹下局部预测误差方向，不能证明闭环因果。")
    note = (
        "# C3更新前权重的固定轨迹残差拟合核对\n\n"
        + conclusion + "\n\n"
        + f"全72场Z轴等场RMSE变化（Wk−W0）：{allz['ALL_0_20']['Wk_minus_W0_rmse_mps2_mean_scene']:.6g} m/s²；"
        + f"HF28：{hfz['ALL_0_20']['Wk_minus_W0_rmse_mps2_mean_scene']:.6g} m/s²。\n\n"
        + "每条记录沿用冻结的事件φ、区间目标及W0，Wk取当前事件更新前记录；早/晚段按任务书固定。结果使用每场等权汇总。指标单位m/s²，位置Q单位m，仅从既有B/C3指标表只读附加。\n\n"
        + "这不是反事实闭环试验：局部拟合较好不代表预测足够准确，也不能推出补偿应用必错或证明因果。无Plant、训练、搜索或TEST。详细逐场/分组表见CSV。\n"
    )
    REPORT_MD.write_text(note, encoding="utf-8", newline="\n")

    artifacts = [SCENE_CSV, GROUP_CSV, SUMMARY_JSON, REPORT_MD, Path(__file__)]
    hashes = {p.name: sha256(p) for p in artifacts}
    HASHES_JSON.write_text(json.dumps({"schema": "C3_OFFLINE_DIAGNOSIS_HASHES_V1", "files": hashes}, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"scene_rows": len(per_scene), "group_rows": len(group_rows), "summary": summary["T2_HF9_Z"], "hashes": hashes}, ensure_ascii=False))


if __name__ == "__main__":
    main()
