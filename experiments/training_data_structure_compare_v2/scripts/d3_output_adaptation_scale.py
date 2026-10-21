from __future__ import annotations

import json
from pathlib import Path

import h5py
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "experiments/training_data_structure_compare_v2"


def vector(f: h5py.File, key: str, n: int) -> np.ndarray:
    return np.asarray(f[key], dtype=np.float64).reshape(-1)[:n]


def time_major(f: h5py.File, key: str, width: int, n: int = 20000) -> np.ndarray:
    x = np.asarray(f[key], dtype=np.float64)
    if x.shape == (width, n):
        x = x.T
    if x.shape != (n, width):
        raise ValueError(f"Unexpected {key} shape {x.shape}")
    return x


def centers35() -> np.ndarray:
    v = np.array([-1.5, -.75, 0, .75, 1.5])
    full = np.stack(np.meshgrid(v, v, v, indexing="ij"), axis=0).reshape(3, -1, order="F")
    mirror = {tuple(c): i for i, c in enumerate(full.T)}
    middle = int(np.argmin(np.sum(full * full, axis=0)))
    roots = [i for i in range(full.shape[1]) if i < mirror[tuple(-full[:, i])] and i != middle]
    selected, used = [middle], set()
    for _ in range(17):
        best, best_distance = None, -np.inf
        for c in roots:
            if c in used:
                continue
            pair = [c, mirror[tuple(-full[:, c])]]
            distance = min(float(np.min(np.sum((full[:, pair] - full[:, q, None]) ** 2, axis=0))) for q in selected)
            if distance > best_distance + 1e-12:
                best, best_distance = c, distance
        if best is None:
            raise AssertionError("Failed to reconstruct 35 symmetric RBF centers")
        used.add(best)
        selected += [best, mirror[tuple(-full[:, best])]]
    return full[:, selected]


def rbf_basis(z: np.ndarray, centers: np.ndarray) -> np.ndarray:
    z = np.asarray(z, dtype=np.float64) / np.array([6.0, 8.0, 10.0])
    d2 = np.sum((z[:, None, :] - centers.T[None, :, :]) ** 2, axis=2)
    return np.exp(-d2 / (2 * .95**2))


def stats(a: np.ndarray, label: str) -> dict:
    a = np.asarray(a, dtype=np.float64).reshape(-1)
    a = a[np.isfinite(a)]
    return {label + "_p10": float(np.quantile(a, .1)), label + "_median": float(np.median(a)),
            label + "_p90": float(np.quantile(a, .9)), label + "_max": float(np.max(a))}


def main() -> None:
    bridge = pd.read_csv(OUT.parent / "position_causal_repair_v1/manifests/BRIDGE6.csv", keep_default_na=False)
    attempts = pd.read_csv(ROOT / "logs/attempt_index.csv", keep_default_na=False).drop_duplicates(
        "run_id", keep="last").set_index("run_id")
    c = centers35()
    out = []
    for r in bridge.itertuples(index=False):
        p = ROOT / Path(str(attempts.loc[r.run_id, "raw_path"]).replace("/", "\\"))
        with h5py.File(p, "r") as f:
            time = vector(f, "log/transition_time", 20000)
            if r.role == "B":
                g = f["log/rbf_position_event_audit"]
                z = np.asarray(g["input"], dtype=np.float64)
                if z.shape[1] != 3 and z.shape[0] == 3:
                    z = z.T
                phi = rbf_basis(z, c)
                norms = np.asarray(g["phi_norm"], dtype=np.float64).reshape(-1)
                if not np.allclose(np.linalg.norm(phi, axis=1), norms, atol=1e-10, rtol=1e-10):
                    raise AssertionError("Reconstructed B RBF norm mismatches its raw audit")
                wb = np.asarray(g["weight_before"], dtype=np.float64)
                wa = np.asarray(g["weight_after"], dtype=np.float64)
                du = np.einsum("eaj,ej->ea", wa - wb, phi)
                dx = np.full_like(du, np.nan)
                for i in range(1, len(z)):
                    dx[i] = np.einsum("aj,j->a", wb[i], phi[i] - phi[i - 1])
                idx = np.flatnonzero(vector(f, "log/position_event_flag", 20000).astype(bool))[:len(norms)]
                beta = vector(f, "log/position_event_beta", 20000)[idx]
                dt = vector(f, "log/rbf_position_event_dt", 20000)[idx]
                full_norm_all = vector(f, "log/rbf_position_basis_norm", 20000)
                full_beta_all = vector(f, "log/position_event_beta", 20000)
                full_events = vector(f, "log/position_event_flag", 20000).astype(bool)
                full_norm = full_norm_all[full_events]
                row = {"scene_id": r.scene_id, "role": "B_RBF", "events_used": len(idx),
                       "first_ready_s": float(time[idx[0]]), "coordination_surface_rms_mps": np.nan,
                       "coordination_surface_delta_rms_mps": np.nan,
                       **stats(norms, "feature_norm"), **stats(dt, "effective_dt_s"), **stats(beta, "beta"),
                       **stats(np.linalg.norm(du, axis=1), "update_output_delta_mps2"),
                       **stats(np.linalg.norm(dx[1:], axis=1), "input_output_delta_mps2"),
                       "rollout_beta_median": float(np.median(full_beta_all[full_events])),
                       "rollout_feature_norm_median": float(np.median(full_norm))}
                out.append(row)
            elif r.role == "P_INIT_STUDENT":
                idx = np.flatnonzero(vector(f, "log/stage1_position_event_inference_valid", 20000).astype(bool))
                phi = time_major(f, "log/stage1_position_event_phi_33", 33)[idx]
                wb = np.asarray(f["log/stage1_position_event_weight_before_33x3"], dtype=np.float64)
                wa = np.asarray(f["log/stage1_position_event_weight_after_33x3"], dtype=np.float64)
                du = np.einsum("eaj,ej->ea", wa - wb, phi)
                dx = np.full_like(du, np.nan)
                for i in range(1, len(idx)):
                    dx[i] = np.einsum("aj,j->a", wb[i], phi[i] - phi[i - 1])
                beta = vector(f, "log/stage1_position_event_beta", 20000)[idx]
                dt = vector(f, "log/stage1_position_effective_update_dt_s", 20000)[idx]
                original = time_major(f, "log/stage1_position_pcf_event_s_original_mps", 3)[idx]
                coord = time_major(f, "log/stage1_position_pcf_event_s_coord_mps", 3)[idx]
                norms = np.linalg.norm(phi, axis=1)
                row = {"scene_id": r.scene_id, "role": "INITIAL_KAN_HEAD", "events_used": len(idx),
                       "first_ready_s": float(time[idx[0]]),
                       "coordination_surface_rms_mps": float(np.sqrt(np.mean(coord**2))),
                       "coordination_surface_delta_rms_mps": float(np.sqrt(np.mean((coord - original)**2))),
                       **stats(norms, "feature_norm"), **stats(dt, "effective_dt_s"), **stats(beta, "beta"),
                       **stats(np.linalg.norm(du, axis=1), "update_output_delta_mps2"),
                       **stats(np.linalg.norm(dx[1:], axis=1), "input_output_delta_mps2"),
                       "rollout_beta_median": float(np.median(beta)),
                       "rollout_feature_norm_median": float(np.median(norms))}
                out.append(row)
    df = pd.DataFrame(out)
    df.to_csv(OUT / "reports/OUTPUT_ADAPTATION_SCALE.csv", index=False)
    r = df[df.role == "B_RBF"]
    k = df[df.role == "INITIAL_KAN_HEAD"]
    ratio = float(np.median(6 * r.rollout_feature_norm_median.to_numpy()**2 /
                            np.maximum(k.rollout_beta_median.to_numpy() *
                                       k.rollout_feature_norm_median.to_numpy()**2, 1e-12)))
    report = f"""# Position RBF 与 KAN Head：更新尺度审计

代码核对：Position RBF有35个高斯基，gamma=1.2×5=6，面限幅[7,8,10]、beta渐入1.8秒、leak=.002、权重±60、输出±3 m/s²。X14 KAN的33维归一化特征范数恒为1；Head更新为 `-beta·phi·s_eff'`，输出还乘beta。RBF更新为 `-Phi·gamma·s_eff'`，输出乘beta。两者保留相同的误差限幅/泄漏/投影/输出上限。

六场原日志实际显示：RBF更新范数和beta来自B原始日志；RBF前8个事件的Phi由冻结配置重建且范数逐项匹配日志。KAN使用全部ready事件的真实Phi、Head更新前后权重、beta及有效dt。每场的输入变化与参数更新对当前raw输出的影响分列在`OUTPUT_ADAPTATION_SCALE.csv`。RBF从首个位置事件更新；KAN经过32个真实事件后约0.32秒就绪。

忽略clip、leak、投影且固定相同误差面时，单步raw更新系数是RBF `gamma||Phi||²` 与KAN `beta||phi||²`；施加到命令后的系数分别再乘beta，因此为 `beta gamma||Phi||²` 与 `beta²||phi||²`。六场全程记录的raw局部系数中位比约 **{ratio:.2f}×**。这是实际参数与日志上的局部尺度，不是闭环带宽证明；姿态、滤波、beta、饱和、轨迹状态和在线Head共同决定实测响应。PCF协调面差值见CSV；B的虚拟协调态只沿其记录轨迹重建。

更新尺度差异值得作为结构/训练背景，但相同position update律早已存在于旧版RBF与新KAN对照中，不能单独归因为新旧性能反转。本轮主训练对照保持原Head增益与控制条件不变。
"""
    (OUT / "reports/OUTPUT_ADAPTATION_SCALE.md").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
