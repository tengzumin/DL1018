from __future__ import annotations

import argparse
import json
from pathlib import Path

import h5py
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "experiments" / "gru14_dssm14_student_refine_v1"


def time_major(ds: h5py.Dataset, nt: int) -> np.ndarray:
    a = np.asarray(ds, dtype=np.float64)
    if a.ndim == 2 and a.shape[1] in (nt, nt + 1) and a.shape[0] <= 64:
        a = a.T
    if a.ndim != 2 or a.shape[0] not in (nt, nt + 1):
        raise ValueError(f"Unexpected time-major field {ds.name}: {a.shape}")
    return a


def raw_metrics(path: Path) -> dict:
    with h5py.File(path, "r") as f:
        log = f["log"]
        t = np.asarray(log["transition_time"], dtype=np.float64).reshape(-1)
        n = min(len(t), int(log["state"].shape[-1] if log["state"].shape[0] <= 64 else log["state"].shape[0]) - 1)
        state = time_major(log["state"], len(t))[:n]
        ref = time_major(log["reference"]["position"], len(t))[:n]
        att_ref = time_major(log["filtered_attitude_reference"], len(t))[:n]
        err = ref - state[:, :3]
        att = np.arctan2(np.sin(att_ref - state[:, 6:9]), np.cos(att_ref - state[:, 6:9]))
        mask = (t[:n] >= 0) & (t[:n] < 20)
        return {"position_Q_0_20_m": float(np.sqrt(np.mean(np.sum(err[mask] ** 2, axis=1)))),
                "position_axis_rmse_m": np.sqrt(np.mean(err[mask] ** 2, axis=0)).tolist(),
                "attitude_Q_0_20_rad": float(np.sqrt(np.mean(np.sum(att[mask] ** 2, axis=1)))),
                "attitude_axis_rmse_rad": np.sqrt(np.mean(att[mask] ** 2, axis=0)).tolist(),
                "transition_count": n}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recent", type=int, default=5)
    args = parser.parse_args()
    metric_files = list((OUT / "student_raw").rglob("metrics.json"))
    reports = [(f, json.loads(f.read_text(encoding="utf-8"))) for f in metric_files]
    reports.sort(key=lambda x: x[1].get("finished_at_utc", ""))
    if args.recent > 0:
        reports = reports[-args.recent:]
    teachers = pd.read_csv(OUT / "manifests/teacher_reuse_manifest.csv", keep_default_na=False)
    teachers = teachers.loc[teachers.role == "B"].drop_duplicates("scene_id").set_index("scene_id")
    old = pd.read_csv(ROOT / "experiments/position_causal_repair_v1/reports/D1_G04_PAIRED_ALL.csv")
    for file, row in reports:
        student = raw_metrics(ROOT / Path(row["raw_path"].replace("/", "\\")))
        scene_id = row["scene_id"]
        teacher = teachers.loc[scene_id]
        b = raw_metrics(ROOT / Path(str(teacher.raw_path).replace("/", "\\")))
        if scene_id in set(old.scene_id.astype(str)):
            ref_q = float(old.loc[old.scene_id.astype(str) == scene_id, "B_Q_0_20_m"].iloc[0])
            if abs(ref_q - b["position_Q_0_20_m"]) > 1e-8:
                raise RuntimeError(f"B raw does not match accepted same-scene baseline for {scene_id}: {ref_q} vs {b['position_Q_0_20_m']}")
        if abs(student["position_Q_0_20_m"] - float(row["position_Q_0_20_m"])) > 1e-10:
            raise RuntimeError(f"Student raw metric mismatch for {scene_id}")
        delta = student["position_Q_0_20_m"] - b["position_Q_0_20_m"]
        print(f"STUDENT_PAIR model={row['model_id']} scene={scene_id} status={row['status']} "
              f"position_RMSE={student['position_Q_0_20_m']:.9f}m same_scene_B={b['position_Q_0_20_m']:.9f}m "
              f"delta={delta:+.9f}m attitude_RMSE={student['attitude_Q_0_20_rad']:.9f}rad "
              f"axes={student['position_axis_rmse_m']} attitude_axes={student['attitude_axis_rmse_rad']}")


if __name__ == "__main__":
    main()
