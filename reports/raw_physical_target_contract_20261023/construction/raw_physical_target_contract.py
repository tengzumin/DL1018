from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
TASKBOOK = ROOT / "reports/raw_physical_target_contract_20261023/TASKBOOK_ZH.md"
READER_PATH = ROOT / "reports/delayed_innovation_design_audit_20261023/construction/delayed_innovation_audit.py"
READER_SHA = "bb6a90e4489825709995900bdb9fe69896c0a902b1239bb515859d131b2259ad"
CSV_PATH = HERE / "RAW_PHYSICAL_TARGET_GROUPS.csv"
JSON_PATH = HERE / "RAW_PHYSICAL_TARGET_SUMMARY.json"
REPORT_PATH = HERE / "REPORT_ZH.md"
D_MAX = 3.0
AXES = ("X", "Y", "Z", "ALL")
CAP = 5 * 1024 * 1024
DEVELOPMENT_FAILURES = [{
    "stage": "single-row smoke attempt 1",
    "command": "$env:OPENBLAS_NUM_THREADS='1'; $env:OMP_NUM_THREADS='1'; $env:MKL_NUM_THREADS='1'; $env:NUMEXPR_NUM_THREADS='1'; $env:VECLIB_MAXIMUM_THREADS='1'; $env:BLIS_NUM_THREADS='1'; python -B 'reports\\raw_physical_target_contract_20261023\\construction\\raw_physical_target_contract.py' --smoke",
    "script_sha256": "876e6d6ecd101875fb939ede948dd0df5f187dcbb1d6192eaa7eff806ba55448",
    "exit_code": 1,
    "error": "ValueError: operands could not be broadcast together with shapes (1967,33,1) (1967,1,1967,3)",
    "resolution": "Use the frozen reader's validated applied gradient directly; compute only the raw gradient locally.",
    "new_outputs_written": False,
}]


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_reader():
    assert sha(READER_PATH) == READER_SHA
    spec = importlib.util.spec_from_file_location("fixed_delayed_reader", READER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_run(reader, run, preflight):
    rec, a = reader.read_one(run, preflight, reader.BETA_RISE_S)
    path = Path(rec["raw_path"])
    with reader.h5py.File(path, "r") as f:
        phi_all = reader.read_raw_array(f["log"], "stage1_position_event_phi_33")
    j, k = reader.EXPECTED_EVENTS[:-1], reader.EXPECTED_EVENTS[1:]
    phi = phi_all[j]
    z, y = np.asarray(a["replay_z"]), np.asarray(a["target"])
    beta, t = np.asarray(a["beta"]), np.asarray(a["time"])
    app = beta[:, None] * np.clip(z, -D_MAX, D_MAX)
    er, ea = z - y, app - y
    active = np.abs(z) < D_MAX
    gr = phi[:, :, None] * er[:, None, :]
    ga = np.asarray(a["gradient"], dtype=np.float64)
    assert ga.shape == gr.shape
    assert np.array_equal(k - j, np.full(1967, 10))
    assert z.shape == y.shape == app.shape == (1967, 3) and phi.shape == (1967, 33)
    assert np.isfinite(z).all() and np.isfinite(y).all() and np.isfinite(phi).all()
    assert np.isfinite(beta).all() and np.isfinite(t).all()
    assert np.max(np.abs(app - a["replay"])) <= 1e-14
    eq = (beta[:, None] == 1.0) & active
    eq_stats = {
        "coordinates": int(eq.sum()),
        "prediction_diff": float(np.max(np.abs((z - app)[eq]))) if eq.any() else None,
        "error_diff": float(np.max(np.abs((er - ea)[eq]))) if eq.any() else None,
        "gradient_diff": float(np.max(np.abs((gr - ga) * eq[:, None, :]))) if eq.any() else None,
    }
    if eq.any():
        assert max(eq_stats["prediction_diff"], eq_stats["error_diff"], eq_stats["gradient_diff"]) <= 1e-14
    assert reader.stat_signature(path) == rec["raw_stat_after"]
    assert sha(path) == rec["raw_sha256_after"] == run["raw_sha256"]
    rec["raw_sha256_after_phi_read"] = rec["raw_sha256_after"]
    rec["raw_stat_after_phi_read"] = rec["raw_stat_after"]
    rec["raw_sha256_unchanged"] = True
    return {"record": rec, "z": z, "y": y, "app": app, "er": er, "ea": ea,
            "beta": beta, "time": t, "phi": phi, "gr": gr, "ga": ga, "eq": eq_stats}


def groups(items):
    out = []

    def add(scope, key, pred):
        members = {x["record"]["scene_id"]: np.asarray(pred(x), bool) for x in items}
        members = {k: v for k, v in members.items() if v.any()}
        out.append((scope, key, members))

    add("ALL12", "ALL12", lambda x: np.ones(len(x["beta"]), bool))
    for task in sorted({x["record"]["task"] for x in items}):
        add("TASK", task, lambda x, q=task: np.full(len(x["beta"]), x["record"]["task"] == q))
    bands = sorted({x["record"]["wind_band"] for x in items})
    assert len(bands) == 4
    for band in bands:
        add("WIND", band, lambda x, q=band: np.full(len(x["beta"]), x["record"]["wind_band"] == q))
    hf_bands = {"W09_W11", "W12_W14"}
    assert hf_bands.issubset(set(bands))
    add("HF", "W09_W14", lambda x: np.full(len(x["beta"]), x["record"]["wind_band"] in hf_bands))
    for scene in sorted(x["record"]["scene_id"] for x in items):
        add("RUN", scene, lambda x, q=scene: np.full(len(x["beta"]), x["record"]["scene_id"] == q))
    assert len({x["record"]["task"] for x in items}) == 3
    return out


PHASES = ("ALL", "OLD_BETA_LT_1", "OLD_BETA_EQ_1", "CURRENT_033_18", "CURRENT_18_5", "CURRENT_5_20")


def phase_mask(item, phase):
    if phase == "ALL":
        return np.ones(len(item["beta"]), bool)
    if phase == "OLD_BETA_LT_1":
        return item["beta"] < 1.0
    if phase == "OLD_BETA_EQ_1":
        return item["beta"] == 1.0
    lo, hi = {"CURRENT_033_18": (.33, 1.8), "CURRENT_18_5": (1.8, 5.0),
              "CURRENT_5_20": (5.0, 20.0)}[phase]
    return (item["time"] >= lo) & (item["time"] < hi)


def cos(a, b):
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    return float(np.vdot(a.ravel(), b.ravel()) / (na * nb)) if na and nb else None


def metric_rows(items):
    by_scene = {x["record"]["scene_id"]: x for x in items}
    rows = []
    for scope, key, base_members in groups(items):
        for phase in PHASES:
            members = {sid: mask & phase_mask(by_scene[sid], phase) for sid, mask in base_members.items()}
            for axis in AXES:
                col = None if axis == "ALL" else ("X", "Y", "Z").index(axis)
                err_r, err_a, dz, grs, gas, pair_delta, betas, times, zs = ([] for _ in range(9))
                pair_cos, used, pairs = [], set(), 0
                for sid, mask in members.items():
                    x = by_scene[sid]
                    if not mask.any():
                        continue
                    used.add(sid)
                    pairs += int(mask.sum())
                    er, ea, dr = x["er"][mask], x["ea"][mask], (x["z"] - x["app"])[mask]
                    gr, ga = x["gr"][mask], x["ga"][mask]
                    z = x["z"][mask]
                    if col is not None:
                        er, ea, dr = er[:, col], ea[:, col], dr[:, col]
                        gr, ga, z = gr[:, :, col], ga[:, :, col], z[:, col]
                    err_r.append(er.ravel()); err_a.append(ea.ravel()); dz.append(dr.ravel())
                    grs.append(gr.reshape(len(gr), -1)); gas.append(ga.reshape(len(ga), -1))
                    pair_delta.append(np.linalg.norm(gr - ga, axis=1) if col is not None
                                      else np.linalg.norm(gr - ga, axis=(1, 2)))
                    dot = np.sum(grs[-1] * gas[-1], axis=1)
                    den = np.linalg.norm(grs[-1], axis=1) * np.linalg.norm(gas[-1], axis=1)
                    pair_cos.extend((dot[den > 0] / den[den > 0]).tolist())
                    betas.append(x["beta"][mask]); times.append(x["time"][mask]); zs.append(z)
                assert pairs > 0, f"empty metric cell: {scope}/{key}/{phase}/{axis}"
                er, ea, dz = np.concatenate(err_r), np.concatenate(err_a), np.concatenate(dz)
                gr, ga = np.concatenate(grs), np.concatenate(gas)
                beta, t, z = np.concatenate(betas), np.concatenate(times), np.concatenate(zs)
                gsr, gsa = gr.sum(axis=0), ga.sum(axis=0)
                pc = np.asarray(pair_cos)
                rows.append({
                    "scope": scope, "group_id": key, "phase": phase, "axis": axis, "n_runs": len(used),
                    "n_pairs": pairs, "n_scalar_outputs": int(er.size),
                    "current_time_min_s": float(t.min()), "current_time_max_s": float(t.max()),
                    "old_beta_mean": float(beta.mean()), "old_beta_lt1_pair_count": int((beta < 1).sum()),
                    "old_beta_eq1_pair_count": int((beta == 1).sum()),
                    "raw_error_bias_mps2": float(er.mean()), "applied_error_bias_mps2": float(ea.mean()),
                    "raw_rmse_mps2": float(np.sqrt(np.mean(er ** 2))),
                    "applied_rmse_mps2": float(np.sqrt(np.mean(ea ** 2))),
                    "raw_per_scalar_half_squared_error_mean": float(.5 * np.mean(er ** 2)),
                    "applied_per_scalar_half_squared_error_mean": float(.5 * np.mean(ea ** 2)),
                    "applied_over_raw_per_scalar_half_squared_error_mean_ratio": float(np.mean(ea ** 2) / np.mean(er ** 2))
                        if np.mean(er ** 2) else None,
                    "prediction_delta_rmse_mps2": float(np.sqrt(np.mean(dz ** 2))),
                    "raw_gradient_sum_l2": float(np.linalg.norm(gsr)),
                    "applied_gradient_sum_l2": float(np.linalg.norm(gsa)),
                    "summed_gradient_delta_l2": float(np.linalg.norm(gsr - gsa)),
                    "summed_gradient_direction_cosine": cos(gsr, gsa),
                    "mean_pair_gradient_direction_cosine_nonzero": float(pc.mean()) if pc.size else None,
                    "median_pair_gradient_direction_cosine_nonzero": float(np.median(pc)) if pc.size else None,
                    "nonzero_pair_cosine_count": int(pc.size),
                    "mean_pair_gradient_delta_l2": float(np.concatenate(pair_delta).mean()),
                    "raw_saturated_axis_count": int((np.abs(z) > D_MAX).sum()),
                    "raw_active_axis_count": int((np.abs(z) < D_MAX).sum()),
                    "exact_clip_boundary_axis_count": int((np.abs(z) == D_MAX).sum()),
                    "within_1e_12_clip_boundary_axis_count": int((np.abs(np.abs(z) - D_MAX) <= 1e-12).sum()),
                })
    return rows


def write_full(items, rows, static, elapsed):
    assert not any(p.exists() for p in (CSV_PATH, JSON_PATH, REPORT_PATH)), "refusing to overwrite outputs"
    taskbook_sha, reader_sha = sha(TASKBOOK), sha(READER_PATH)
    fixed_paths = {
        TASKBOOK.resolve(): taskbook_sha, READER_PATH.resolve(): READER_SHA,
        Path(static["preflight_path"]): static["preflight_sha256"],
        Path(static["C1_source_lock_path"]): static["C1_source_lock_sha256"],
        Path(static["C1_manifest_path"]): static["C1_manifest_sha256"],
        Path(static["scene_list_path"]): static["scene_list_sha256"],
    }
    fixed_paths.update({Path(v["path"]): v["sha256"] for v in static["frozen_runtime_sources"].values()})
    fixed_paths[Path(static["effective_config"]["path"])] = static["effective_config"]["sha256"]
    fixed_paths[Path(static["model_identity_from_C1_lock"]["mat_path"])] = static["model_identity_from_C1_lock"]["mat_sha256"]
    n = static["normalizer_identity_from_C1_lock"]
    fixed_paths[Path(n["path"])] = n["sha256"]
    fixed_paths[Path(n["train_only_report_path"])] = n["train_only_report_sha256"]
    fixed_paths.update({Path(v["path"]): v["sha256"] for v in static["causal_observability_inputs"].values()})
    snapshots = []
    for path, expected in fixed_paths.items():
        actual = sha(path)
        assert actual == expected, f"static input changed: {path}"
        snapshots.append({"path": str(path), "sha256": actual})
    assert all(x["record"]["raw_sha256_unchanged"] for x in items)
    assert len(rows) == 504
    eq_n = sum(x["eq"]["coordinates"] for x in items)
    eq_pred = max(x["eq"]["prediction_diff"] or 0.0 for x in items)
    eq_error = max(x["eq"]["error_diff"] or 0.0 for x in items)
    eq_grad = max(x["eq"]["gradient_diff"] or 0.0 for x in items)
    assert eq_n > 0 and max(eq_pred, eq_error, eq_grad) <= 1e-14

    with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    def find(scope, key, phase, axis="ALL"):
        return next(r for r in rows if r["scope"] == scope and r["group_id"] == key
                    and r["phase"] == phase and r["axis"] == axis)
    report = [
        "# 原始物理目标与旧 applied 输出：固定12条同状态比较", "",
        "状态：PASS。只读历史 raw；无拟合、优化器、权重累积更新或闭环。",
        f"12条 ON1 记录，每条1967个有效窗口，总计23604对。读取器 SHA-256 {READER_SHA}，且有 main guard；只调用 parse_input_identities、read_one、read_raw_array。raw 所有读前/读后 SHA/stat 均一致。",
        "",
        "固定同一当前 W_k、旧 phi_j 和区间目标 y：z=W_k^T phi_j；raw 残差 z-y；applied 残差 beta_j clip(z,±3)-y。梯度按任务书的 G_raw 和 G_applied 定义，clip 导数 m=1 当且仅当 |z|<3。",
        "",
        f"beta_j=1 且未饱和坐标 {eq_n} 个：预测、残差、梯度最大差分别 {eq_pred:.3g}、{eq_error:.3g}、{eq_grad:.3g}，局部恒等式通过。",
        "",
        "| 范围 | 阶段 | 窗口数 | raw RMSE | applied RMSE | raw 每标量半平方误差均值 | applied 每标量半平方误差均值 | 饱和轴 | 近边界轴 | 梯度和方向余弦 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    report_scopes = (("ALL12", "ALL12"), ("HF", "W09_W14"), ("WIND", "W15"))
    for scope, key in report_scopes:
        for phase in PHASES:
            r = find(scope, key, phase)
            co = "NA" if r["summed_gradient_direction_cosine"] is None else f"{r['summed_gradient_direction_cosine']:.7g}"
            report.append(f"| {scope}/{key} | {phase} | {r['n_pairs']} | {r['raw_rmse_mps2']:.8g} | {r['applied_rmse_mps2']:.8g} | "
                          f"{r['raw_per_scalar_half_squared_error_mean']:.8g} | {r['applied_per_scalar_half_squared_error_mean']:.8g} | "
                          f"{r['raw_saturated_axis_count']} | {r['within_1e_12_clip_boundary_axis_count']} | {co} |")
    report += [
        "", "CSV 固定为21个范围（ALL12、3任务、4风组、合并HF W09_W14、12运行）×6阶段（ALL、旧beta两组、当前时间三组）×4轴向（X/Y/Z/ALL），共504行。完整任务/风组/运行/XYZ拆分及梯度差和平均单对余弦见 RAW_PHYSICAL_TARGET_GROUPS.csv。",
        "表中的半平方误差是逐标量坐标的描述统计，不是原训练目标的loss。",
        "",
        "解释边界：beta_j=1 且未饱和时两种预测、误差和局部梯度相同，因此只移除 beta·clip 不会改变该子集上的同状态更新方向定义；早期更新改变后，后续 W 与闭环状态可以分叉，本检查不证明反事实轨迹相同。这里固定物理区间目标 y=d-hat，不把它与预训练 Y 或 Y+r_f 的目标选择混为一谈。",
        "",
        "开发记录：第1次单条烟测曾有shape广播异常，未写产物；最终脚本复用冻结reader已核的applied梯度。精确命令、失败脚本SHA与错误见JSON。",
        "",
        "本检查0训练/拟合/optimizer/累计更新/gain选择/Plant/MATLAB/GPU/TEST。无 raw 副本。", "",
    ]
    REPORT_PATH.write_text("\n".join(report), encoding="utf-8")
    summary = {
        "schema": "RAW_PHYSICAL_TARGET_CONTRACT_SUMMARY_V1", "status": "PASS",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "script_path": str(Path(__file__).resolve()), "script_sha256": sha(Path(__file__)),
        "taskbook_path": str(TASKBOOK.resolve()), "taskbook_sha256": taskbook_sha,
        "reused_reader_path": str(READER_PATH.resolve()), "reused_reader_sha256": reader_sha,
        "reader_functions": ["parse_input_identities", "read_one", "read_raw_array"],
        "development_failures": DEVELOPMENT_FAILURES,
        "static_input_sha_snapshots": snapshots,
        "contract": {
            "window": "j=k-10; current zero-based k=330..19990 step 10",
            "target": "y=(v[k]-v[j])/(10*dt)-mean(a_f[j:k])",
            "raw_prediction_error": "W_k^T phi_j-y",
            "applied_prediction_error": "beta_j*clip(W_k^T phi_j,-3,3)-y",
            "raw_gradient": "phi_j*(z-y)^T",
            "applied_gradient": "phi_j*(beta_j*m*(beta_j*clip(z)-y))^T; m=1 iff abs(z)<3",
            "time_groups_use_current_t_k": ["[0.33,1.8)", "[1.8,5)", "[5,20)"],
            "beta_groups_use_old_beta_j": ["<1", "==1"],
            "gradient_cosines": "summed group gradient cosine and mean/median nonzero per-pair cosine",
            "scopes": "ALL12 (1), TASK (3), WIND (4), combined HF W09_W14 (1), RUN (12)",
            "phases": list(PHASES), "axes": list(AXES),
            "half_squared_error_metric": "mean over scalar coordinates of 0.5*error^2; descriptive statistic, not training loss",
        },
        "counts": {"runs": len(items), "pairs_per_run": 1967, "pairs_total": len(items)*1967,
                   "csv_rows": len(rows), "output_cap_bytes": CAP},
        "cpu_thread_environment": {k: os.environ.get(k) for k in
                                   ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
                                    "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "BLIS_NUM_THREADS")},
        "beta1_unsaturated_identity": {
            "coordinates": eq_n, "prediction_max_abs_difference_mps2": eq_pred,
            "error_max_abs_difference_mps2": eq_error, "gradient_max_abs_difference": eq_grad,
            "pass": True, "interpretation": "same-state local equality only",
        },
        "per_run": [{
            "scene_id": x["record"]["scene_id"], "task": x["record"]["task"], "wind_band": x["record"]["wind_band"],
            "raw_path": x["record"]["raw_path"], "raw_sha256_before": x["record"]["raw_sha256_before"],
            "raw_sha256_after": x["record"]["raw_sha256_after_phi_read"],
            "raw_stat_before": x["record"]["raw_stat_before"], "raw_stat_after": x["record"]["raw_stat_after_phi_read"],
            "raw_bytes": x["record"]["raw_bytes"], "pairs": x["record"]["eligible_previous_valid_phi_pairs"],
            "raw_unchanged": x["record"]["raw_sha256_unchanged"], "beta1_unsaturated": x["eq"],
        } for x in items],
        "elapsed_s": elapsed,
        "training_fitting_optimizer_cumulative_update_gain_search_plant_matlab_gpu_test_used": False,
        "outputs": {"csv_path": str(CSV_PATH.resolve()), "csv_sha256": sha(CSV_PATH),
                    "report_path": str(REPORT_PATH.resolve()), "report_sha256": sha(REPORT_PATH)},
    }
    summary["total_new_artifact_bytes_including_script"] = 0
    for _ in range(5):
        encoded = json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        size = Path(__file__).stat().st_size + CSV_PATH.stat().st_size + REPORT_PATH.stat().st_size + len(encoded.encode("utf-8"))
        if summary["total_new_artifact_bytes_including_script"] == size:
            break
        summary["total_new_artifact_bytes_including_script"] = size
    JSON_PATH.write_text(encoded, encoding="utf-8")
    size = sum(p.stat().st_size for p in (Path(__file__), CSV_PATH, JSON_PATH, REPORT_PATH))
    assert size <= CAP, f"derived artifacts exceed 5 MiB: {size}"
    assert size == summary["total_new_artifact_bytes_including_script"]
    return summary


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--smoke", action="store_true")
    mode.add_argument("--full", action="store_true")
    args = parser.parse_args()
    if args.full:
        assert not any(p.exists() for p in (CSV_PATH, JSON_PATH, REPORT_PATH)), "refusing to rerun over outputs"
    thread_keys = ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
                   "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "BLIS_NUM_THREADS")
    assert all(os.environ.get(k) == "1" for k in thread_keys), "run with all CPU thread limits set to 1"
    start = time.perf_counter()
    reader = load_reader()
    lock, preflight, runs, static = reader.parse_input_identities()
    assert len(runs) == 12
    selected = runs[:1] if args.smoke else runs
    items = []
    preflight_by_scene = {x["scene_id"]: x for x in preflight["raw_records"]}
    for run in selected:
        items.append(read_run(reader, run, preflight_by_scene[run["scene_id"]]))
    if args.smoke:
        x = items[0]
        print(json.dumps({"status": "SMOKE_PASS_NO_OUTPUT", "scene_id": x["record"]["scene_id"],
                          "pairs": int(x["y"].shape[0]), "beta1_unsaturated": x["eq"],
                          "raw_unchanged": x["record"]["raw_sha256_unchanged"],
                          "outputs_written": False, "elapsed_s": time.perf_counter()-start},
                         ensure_ascii=False, indent=2, allow_nan=False))
        return
    rows = metric_rows(items)
    result = write_full(items, rows, static, time.perf_counter()-start)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
