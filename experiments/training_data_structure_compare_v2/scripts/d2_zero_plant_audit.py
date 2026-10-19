from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "experiments/training_data_structure_compare_v2"
sys.path.insert(0, str(OUT / "scripts"))
from data_runtime import assign_weights, endpoint_indices, load_episodes  # noqa: E402


def main() -> None:
    ep_index = pd.read_csv(ROOT / "logs/episode_index.csv", keep_default_na=False)
    attempts = pd.read_csv(ROOT / "logs/attempt_index.csv", keep_default_na=False)
    manifest = pd.read_csv(OUT / "manifests/REUSED_SEQUENCE_CACHE.csv", keep_default_na=False)
    accepted = ep_index.loc[ep_index.accepted.astype(str).str.lower().isin(("true", "1")) &
                            ep_index.split.str.lower().isin(("train", "val"))].copy()
    if accepted.run_id.duplicated().any() or manifest.run_id.duplicated().any():
        raise AssertionError("Duplicate accepted run_id or reused-cache identity")
    if set(accepted.run_id) != set(manifest.run_id):
        raise AssertionError("The cache manifest does not exactly match accepted TRAIN/VAL episodes")
    scene_meta = accepted.scene_id.str.extract(r"_T(?P<t>\d+)_C(?P<c>\d+)_W(?P<w>\d+)$").astype(int)
    accepted = accepted.join(scene_meta)
    if accepted[["t", "c", "w"]].isna().any().any():
        raise AssertionError("Could not parse task/config/wind identity for all episodes")
    accepted["config_id"] = accepted.c.map(lambda v: f"C{v:02d}")
    accepted["wind_cell"] = accepted.w
    if set(accepted.t) != {1, 2, 3} or set(accepted.config_id) != {f"C{i:02d}" for i in range(16)}:
        raise AssertionError("Unexpected task or configuration coverage")
    train = accepted.loc[accepted.split.str.lower() == "train"]
    val = accepted.loc[accepted.split.str.lower() == "val"]
    if set(train.scene_id) & set(val.scene_id) or set(train.run_id) & set(val.run_id):
        raise AssertionError("TRAIN/VAL scene or run leakage")
    if attempts.run_id.duplicated().any():
        # Retried attempts are expected in the append-only run index; accepted identities must resolve once.
        resolved = attempts.drop_duplicates("run_id", keep="last")
    else:
        resolved = attempts
    resolved_ids = set(resolved.run_id)
    if not set(accepted.run_id).issubset(resolved_ids):
        raise AssertionError("Accepted episodes are missing from attempt_index.csv")

    train_eps = load_episodes("train", ("B", "POS_OFF", "P_INIT_STUDENT"))
    val_eps = load_episodes("val", ("B", "POS_OFF", "P_INIT_STUDENT"))
    expected_train = {"B": 768, "POS_OFF": 768, "P_INIT_STUDENT": 384}
    expected_val = {"B": 48, "POS_OFF": 48, "P_INIT_STUDENT": 48}
    for eps, expected in ((train_eps, expected_train), (val_eps, expected_val)):
        got = pd.Series([e.role for e in eps]).value_counts().to_dict()
        if got != expected:
            raise AssertionError(f"Unexpected split/role counts: {got}")
        for ep in eps:
            ids = endpoint_indices(ep)
            if (not np.isfinite(ep.x14).all() or not np.isfinite(ep.raw).all() or
                    not np.isfinite(ep.y).all() or not np.array_equal(ep.plant_index, np.sort(ep.plant_index)) or
                    np.any(np.diff(ep.event_time_s) <= 0) or np.any(np.diff(ep.plant_index) <= 0) or
                    not ep.ready[ids].all() or
                    np.max(np.abs(ep.y - np.clip(ep.raw, -3, 3))) > 4e-6):
                raise AssertionError(f"Cache chronology/finite/label/ready mismatch: {ep.run_id}")

    total_train_endpoints = assign_weights(train_eps, {"B": .25, "POS_OFF": .25, "P_INIT_STUDENT": .50})
    weight_rows = []
    collision_rows = []
    norm = np.load(ROOT / "models/position/initial/normalizer.npz")
    mu = np.asarray(norm["mu"], dtype=np.float32).reshape(-1)
    sigma = np.maximum(np.asarray(norm["sigma"], dtype=np.float32).reshape(-1), 1e-4)
    rng = np.random.default_rng(2026101910)
    collision_pool: dict[tuple[str, str], list[dict]] = {}
    for ep in train_eps:
        ids = endpoint_indices(ep)
        phases = ep.phase[ids]
        w = ep.weights[ids]
        config = re.search(r"_C(\d+)_W", ep.scene_id).group(1)
        for phase in np.unique(phases):
            m = phases == phase
            weight_rows.append({"split": "train", "role": ep.role, "task": ep.task,
                                "config_id": f"C{int(config):02d}", "wind_cell": ep.wind_cell,
                                "phase": int(phase), "scene_id": ep.scene_id, "run_id": ep.run_id,
                                "endpoint_count": int(m.sum()), "effective_weight": float(w[m].sum()),
                                "per_event_weight_min": float(w[m].min()),
                                "per_event_weight_max": float(w[m].max()),
                                "target_raw_rms_mps2": float(np.sqrt(np.mean(ep.raw[ids[m]] ** 2))),
                                "target_clip_fraction": float(np.mean(np.abs(ep.raw[ids[m]]) > 3))})
        # Deterministic, run-grouped sample for the finite X14/history collision probe.
        take = np.sort(rng.choice(ids, size=min(8, len(ids)), replace=False))
        group = collision_pool.setdefault((ep.role, ep.task), [])
        for end in take:
            h = ep.x14[end - 31:end + 1, :10].astype(np.float32)
            if h.shape != (32, 10):
                raise AssertionError(f"Short history window for {ep.run_id}/{end}")
            group.append({"run_id": ep.run_id, "scene_id": ep.scene_id, "role": ep.role,
                          "task": ep.task, "phase": int(ep.phase[end]),
                          "x": ((ep.x14[end] - mu) / sigma).astype(np.float32),
                          "history": ((h - mu[:10]) / sigma[:10]).reshape(-1),
                          "y": ep.raw[end].astype(np.float32), "endpoint": int(end)})

    per_run = pd.DataFrame(weight_rows)
    per_run.to_csv(OUT / "reports/EFFECTIVE_TRAINING_MASS.csv", index=False)
    weighted = (per_run.groupby(["role", "task", "config_id", "wind_cell", "phase"], as_index=False)
                .agg(effective_weight=("effective_weight", "sum"), endpoint_count=("endpoint_count", "sum"),
                     scenes=("scene_id", "nunique"), per_event_weight_min=("per_event_weight_min", "min"),
                     per_event_weight_max=("per_event_weight_max", "max"),
                     target_raw_rms_mps2=("target_raw_rms_mps2", "mean"),
                     target_clip_fraction=("target_clip_fraction", "mean")))
    weighted.to_csv(OUT / "derived/EFFECTIVE_TRAINING_MASS_BY_STRATUM.csv", index=False)

    for (role, task), items in collision_pool.items():
        run_ids = np.asarray([x["run_id"] for x in items], dtype=object)
        phase_ids = np.asarray([x["phase"] for x in items], dtype=np.int64)
        labels = np.stack([x["y"] for x in items])
        for feature_name, key in (("X14_CURRENT", "x"), ("HISTORY_X14_0_9_32_EVENTS", "history")):
            features = np.stack([x[key] for x in items]).astype(np.float64)
            tree = cKDTree(features)
            k = min(32, len(items))
            dists, neighbors = tree.query(features, k=k, workers=1)
            if k == 1:
                dists, neighbors = dists[:, None], neighbors[:, None]
            for i in range(len(items)):
                j = next((int(jj) for jj in neighbors[i] if run_ids[int(jj)] != run_ids[i]), None)
                if j is None:
                    continue
                collision_rows.append({"feature_set": feature_name, "role": role, "task": task,
                                       "query_run_id": run_ids[i], "neighbor_run_id": run_ids[j],
                                       "query_phase": int(phase_ids[i]), "neighbor_phase": int(phase_ids[j]),
                                       "query_endpoint": items[i]["endpoint"],
                                       "neighbor_endpoint": items[j]["endpoint"],
                                       "feature_distance": float(np.linalg.norm(features[i] - features[j])),
                                       "label_delta_norm_mps2": float(np.linalg.norm(labels[i] - labels[j])),
                                       "query_label_x": float(labels[i, 0]), "query_label_y": float(labels[i, 1]),
                                       "query_label_z": float(labels[i, 2]),
                                       "neighbor_label_x": float(labels[j, 0]),
                                       "neighbor_label_y": float(labels[j, 1]),
                                       "neighbor_label_z": float(labels[j, 2])})
    collision = pd.DataFrame(collision_rows)
    collision.to_csv(OUT / "reports/X14_HISTORY_COLLISION_PROBE.csv", index=False)
    close_cut = float(collision.loc[collision.feature_set == "X14_CURRENT", "feature_distance"].quantile(.05))
    close = collision[(collision.feature_set == "X14_CURRENT") & (collision.feature_distance <= close_cut)]
    collision_summary = (collision.groupby(["feature_set", "role", "task"], as_index=False)
                         .agg(pairs=("label_delta_norm_mps2", "size"),
                              feature_distance_p50=("feature_distance", "median"),
                              label_delta_p50_mps2=("label_delta_norm_mps2", "median"),
                              label_delta_p90_mps2=("label_delta_norm_mps2", lambda x: x.quantile(.9))))
    collision_summary.to_csv(OUT / "derived/X14_HISTORY_COLLISION_SUMMARY.csv", index=False)
    close.to_csv(OUT / "derived/X14_CLOSEST_CURRENT_PAIRS_P05.csv", index=False)

    mass_summary = weighted.groupby("role", as_index=False).effective_weight.sum()
    if dict(zip(mass_summary.role, mass_summary.effective_weight.round(8))) != {
            "B": .25, "POS_OFF": .25, "P_INIT_STUDENT": .50}:
        raise AssertionError("Effective source mass differs from frozen .25/.25/.50 objective")
    task_mass = weighted.groupby(["role", "task"], as_index=False).effective_weight.sum()
    expected_task_mass = {"B": .25 / 3, "POS_OFF": .25 / 3, "P_INIT_STUDENT": .50 / 3}
    for role, expected in expected_task_mass.items():
        values = task_mass.loc[task_mass.role == role, "effective_weight"].to_numpy(dtype=np.float64)
        if values.shape != (3,) or not np.allclose(values, expected, atol=1e-8):
            raise AssertionError(f"Task mass is not balanced within {role}: {values}")

    diff_rows = [
        ("task_and_geometry", "one 3D figure-eight task; 16 classes; the final KAN pool has 64 complete Student flights (4/class)", "HELIX / FIG8_3D / SQUARE; C00-C15; teacher and Student pools kept distinct", "DL1009 position_advantage_stage1_v1/reports/FINAL_REPORT.md; DL1018 logs/episode_index.csv"),
        ("training_sources", "winning N-KAN fit uses only the 64 complete, stable Student flights; failed/incomplete rollouts excluded by the frozen complete-flight rule", "B=768, POS_OFF=768, Student=384; all accepted TRAIN episodes retained", "DL1009 position_advantage_stage1_v1/reports/FINAL_REPORT.md; DL1018 configs/dataset_plan.json"),
        ("fit_budget", "N-KAN final fit: 6 epochs, max 100, patience 5, batch 256, 75,648 TRAIN windows, 12,608 VAL windows; seed 20261013", "all four fits have exactly 60,000 Adam steps, batch 256, same initial checkpoint and fixed 144-episode VAL", "DL1009 position_advantage_stage1_v1/models/final/N_KAN/fit_status.json; taskbook sections 3.1/3.6"),
        ("architecture_screen", "N-KAN final validation score .287010; initial screen also had lower residual scores for N-TCN .161733 and GRU .161875, but N-TCN rollouts hit nine safety stops; architecture scores do not equal closed-loop ranking", "compare shallow KAN, deeper function-preserving KAN, causal history branch, and data source with one common objective", "DL1009 position_advantage_stage1_v1/reports/initial_model_screen.csv and FINAL_REPORT.md"),
        ("history_and_features", "DL1009 N-KAN and current DL1018 X14 KAN read only the latest event from a 32-event interface", "HISTORY_KAN adds 32 real events of X14[0:10]; current arm commands remain only in the original KAN branch", "DL1009/DL1018 training/models.py; taskbook section 3.5"),
        ("same_scene_outcome", "DEV 32/32: N-KAN Q .024400 m vs B .034324 m; TEST not confirmed (1/32 explicit safety stop)", "reuse DL1018 BRIDGE6 only; paired canaries evaluate the new fits under the unchanged DL1018 controller", "DL1009 position_advantage_stage1_v1/reports/FINAL_REPORT.md; DL1018 causal repair D3 report"),
        ("control_and_environment", "DL1009 and DL1018 are different contracts, Plant masses/winds, and trajectory/task suites; old score is not a same-Plant counterfactual", "hold DL1018 B, attitude RBF, PCF, beta, limits, and safety path fixed across the four families", "DL1009 RBFBS0 README/method report; DL1018 configs/contract_dl1018.json"),
    ]
    pd.DataFrame(diff_rows, columns=("aspect", "DL1009_evidence", "DL1018_protocol", "evidence_source")).to_csv(
        OUT / "reports/OLD_NEW_PROTOCOL_DIFF.csv", index=False)

    report = f"""# 数据与训练质量审计（零 Plant）

## 索引和缓存

- accepted TRAIN/VAL 记录与本轮复用的序列缓存清单逐 run_id 一一对应；accepted ID 唯一，TRAIN 与 VAL 没有共享 run 或 scene。
- TRAIN episode：B {expected_train['B']}、POS_OFF {expected_train['POS_OFF']}、Student {expected_train['P_INIT_STUDENT']}；共同 VAL：三类各 {expected_val['B']}。TRAIN 共 {total_train_endpoints:,} 个 stride-5 就绪终点；每个终点仍来自原始100Hz序列，stride仅用于离线监督采样，不是部署更新率。
- 每条缓存均为1999事件、32事件 ready 边界；事件时间严格递增，Plant索引递增，X14/标签有限，`target_clip` 与 `clip(target_raw, -3, 3)` 闭合误差不超过4e-6 m/s²。32帧张量的部署 KAN 前向只使用最新帧，来源代码 `training/models.py`。
- accepted run_id 在 attempt_index 中均可唯一解析到最后一条 attempt 记录。append-only attempt 索引含重复 run_id 是重试记录，不会形成重复 accepted episode；训练打包按 episode_index 的 accepted 唯一 run 读取。

## 覆盖与质量权重

- Teacher 的每个 task×class 覆盖16个风格场景；Student 每个 task×class覆盖8个。每类在16个 C 配置均有记录；各角色与任务的采集覆盖见 `derived/EFFECTIVE_TRAINING_MASS_BY_STRATUM.csv`。
- 按当前正式权重函数重建：全局来源质量为 B 0.25、POS_OFF 0.25、Student 0.50；每个来源再将总质量平均分给三个任务，并在 task×class、scene、phase 与该 phase 的 endpoint 数上归一化。具体 config/wind/phase 汇总、单事件权重范围见同表及 `EFFECTIVE_TRAINING_MASS.csv`。
- 因同类 episode数为 Teacher 16、Student 8，且来源质量分别为0.25/0.50，Student 每场总权重是每个 Teacher 的4倍；这是明确的来源配方结果。新训练按均匀打乱 endpoint 抽样，在 loss 里乘一次冻结质量；不再叠加 WeightedRandomSampler，不双重加权。短/长 phase 总权重相等，phase内按 endpoint 平分。
- 每条 episode 内的 x14、target、event_time、phase、beta、ready、plant_index按同一 event index保存；训练窗口不会跨 episode 拼接，也不会将 VAL/DEV 作为 TRAIN。

## 有限近邻冲突探针

- 对每个 TRAIN run 固定随机抽8个 ready endpoint，只在同来源、同任务内寻找最近的跨 run 邻居；比较当前标准化X14与32事件真实历史（仅X14前10列）。本探针不用于选模。
- 当前X14最近5%跨 run 配对的X14距离阈值为 {close_cut:.4g}；逐来源/任务的样本数、距离和标签差分位数见 `derived/X14_HISTORY_COLLISION_SUMMARY.csv`，配对明细见 `X14_HISTORY_COLLISION_PROBE.csv`。
- 近邻标签差说明记录数据里存在状态相似但目标不同的关联样本；同 run 排除、只抽样、且该指标不是条件方差/可辨识性证明。历史向量相较当前帧的配对结果可显示它是否区分这些抽样邻居，但不能单独证明历史分支会改善闭环。

## 旧 DL1009 与本轮 DL1018 的协议差异

逐项和证据路径见 `OLD_NEW_PROTOCOL_DIFF.csv`。DL1009获胜包不是“同条件下一个浅KAN小数据fit”：旧研究有多架构筛选与后续分阶段训练/repair；其当前任务与 DL1018 三任务混合任务、数据来源比例、控制合同、Plant、选模协议均不同。旧包成绩可作历史参考，不能用单个权重包差异归因。本轮使用新数据、原始DL1018 Initial作同一起点，固定控制合同，只比较数据来源、容量、历史三项方案。

## 训练与验证口径

后续训练和共同 VAL 均报告物理 m/s² 的 RMSE/偏置、逐任务和逐来源值，使用同一标签、同一 clip 与同一固定 Head 目标；训练加权损失与物理 RMSE分开。VAL 是已有开发数据，不称blind test。Student 航次成绩较差不构成删样本理由。
"""
    (OUT / "reports/DATA_AND_WEIGHT_AUDIT.md").write_text(report, encoding="utf-8")
    print(json.dumps({"accepted_episodes": len(accepted), "train_endpoints": total_train_endpoints,
                      "collision_rows": len(collision), "close_pair_count": len(close),
                      "micro_pool": 12, "new_plants": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
