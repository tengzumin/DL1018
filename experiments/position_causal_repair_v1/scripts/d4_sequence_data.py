from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import h5py
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "experiments" / "position_causal_repair_v1"
CACHE = OUT / "derived_events" / "D4_SEQUENCE_CACHE"


def truth(v: str) -> bool:
    return str(v).strip().lower() in {"true", "1", "yes"}


def time_major(dataset: h5py.Dataset, nt: int) -> np.ndarray:
    a = np.asarray(dataset, dtype=np.float64)
    if a.ndim == 2 and a.shape[1] in (nt, nt + 1) and a.shape[0] <= 64:
        a = a.T
    if a.ndim != 2 or a.shape[0] not in (nt, nt + 1):
        raise ValueError(f"Expected time-major data with {nt} or {nt+1} rows, got {dataset.name} {a.shape}")
    return a


def cache_path(split: str, run_id: str) -> Path:
    return CACHE / split / f"{run_id}.npz"


def build() -> None:
    index = pd.read_csv(ROOT / "logs/episode_index.csv", keep_default_na=False)
    index = index.loc[index.accepted.map(truth) & index.split.str.lower().isin(("train", "val"))]
    attempts = pd.read_csv(ROOT / "logs/attempt_index.csv", keep_default_na=False)
    attempts = attempts.loc[attempts.raw_path.astype(str).str.len() > 0].drop_duplicates("run_id", keep="last")
    raw_by_run = dict(zip(attempts.run_id.astype(str), attempts.raw_path.astype(str)))
    records = []
    for idx, row in enumerate(index.itertuples(index=False), start=1):
        split = str(row.split).lower()
        run_id = str(row.run_id)
        dest = cache_path(split, run_id)
        if dest.is_file():
            with np.load(dest, allow_pickle=False) as z:
                if str(z["run_id"]) != run_id or z["x14"].shape != (1999, 14) or z["x20"].shape != (1999, 20):
                    raise ValueError(f"Bad existing D4 cache: {dest}")
        else:
            if run_id not in raw_by_run:
                raise FileNotFoundError(f"Raw run path missing in attempt_index.csv: {run_id}")
            event_path = ROOT / Path(str(row.position_event_path).replace("/", "\\"))
            raw_path = ROOT / Path(raw_by_run[run_id].replace("/", "\\"))
            with h5py.File(event_path, "r") as f:
                x14 = np.asarray(f["x14"], dtype=np.float64)
                y = np.asarray(f["target_clip"], dtype=np.float64)
                raw = np.asarray(f["target_raw"], dtype=np.float64)
                ready = np.asarray(f["ready"], dtype=np.uint8).reshape(-1).astype(bool)
                phase = np.asarray(f["phase_code"], dtype=np.uint8).reshape(-1)
                beta = np.asarray(f["beta"], dtype=np.float64).reshape(-1)
                event_time = np.asarray(f["event_time_s"], dtype=np.float64).reshape(-1)
                plant_idx = np.asarray(f["plant_index"], dtype=np.int64).reshape(-1) - 1
            if x14.shape == (14, 1999):
                x14 = x14.T
            if x14.shape != (1999, 14) or y.shape != (1999, 3) or raw.shape != (1999, 3):
                raise ValueError(f"Unexpected position-event shape for {run_id}: {x14.shape}, {y.shape}, {raw.shape}")
            if len(ready) != 1999 or ready.sum() != 1968 or not np.array_equal(ready, np.arange(1999) >= 31):
                raise ValueError(f"Unexpected ready boundary for {run_id}")
            if len(plant_idx) != 1999 or plant_idx.min() < 0 or plant_idx.max() >= 20000:
                raise ValueError(f"Unexpected event plant indexes for {run_id}")
            with h5py.File(raw_path, "r") as f:
                lg = f["log"]
                state = time_major(lg["state"], 20000)
                nominal = time_major(lg["position_nominal_acceleration_mps2"], 20000)
                eta_full = time_major(lg["stage1_position_pcf_eta_before_mps"], 20000)
                eta = eta_full[plant_idx, :3]
                velocity = state[plant_idx, 3:6]
                a_nom = nominal[plant_idx, :3]
                x20 = np.column_stack((x14, velocity, a_nom))
                # The active Initial collector logged exact per-event PCF state/surface.
                if str(row.source_role) == "P_INIT_STUDENT":
                    eta_event = time_major(lg["stage1_position_pcf_event_eta_before_mps"], 20000)[plant_idx, :3]
                    surface_event = time_major(lg["stage1_position_pcf_event_s_original_mps"], 20000)[plant_idx, :3]
                    if np.max(np.abs(eta_event[ready] - eta[ready])) > 1e-12:
                        raise ValueError(f"Logged PCF eta event mismatch for {run_id}")
                    if np.max(np.abs(surface_event[ready] - x14[ready, 3:6])) > 1e-12:
                        raise ValueError(f"X14 surface differs from logged PCF surface for {run_id}")
            arrays = (x14, x20, y, raw, eta, beta, event_time)
            if any(not np.isfinite(a).all() for a in arrays):
                raise ValueError(f"Non-finite D4 sequence field for {run_id}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(dest, run_id=np.asarray(run_id), scene_id=np.asarray(str(row.scene_id)),
                                split=np.asarray(split), role=np.asarray(str(row.source_role)),
                                task=np.asarray(str(row.task)), class_index=np.asarray(int(row.class_index)),
                                wind_cell=np.asarray(int(row.wind_cell)), x14=x14.astype(np.float32),
                                x20=x20.astype(np.float32), y=y.astype(np.float32), raw=raw.astype(np.float32),
                                eta=eta.astype(np.float32), ready=ready, phase=phase, beta=beta.astype(np.float32),
                                event_time_s=event_time.astype(np.float32), plant_index=plant_idx.astype(np.int32))
        raw_path = raw_by_run.get(run_id, "")
        ep_path = str(row.position_event_path)
        records.append({"run_id": run_id, "scene_id": str(row.scene_id), "split": split,
                        "role": str(row.source_role), "task": str(row.task),
                        "class_index": int(row.class_index), "wind_cell": int(row.wind_cell),
                        "position_event_path": ep_path, "raw_path": raw_path,
                        "cache_path": dest.relative_to(ROOT).as_posix(), "ready_events": 1968})
        if idx % 50 == 0 or idx == len(index):
            print(f"D4 sequence cache {idx}/{len(index)}", flush=True)
    manifest = OUT / "manifests/D4_SEQUENCE_CACHE.csv"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(records).to_csv(manifest, index=False)
    print(f"D4 sequence cache ready: {len(records)} episodes; Plant=0, fit=0", flush=True)


@dataclass
class SeqEpisode:
    run_id: str
    scene_id: str
    split: str
    role: str
    task: str
    class_index: int
    wind_cell: int
    cache: Path
    x14: np.ndarray
    x20: np.ndarray
    y: np.ndarray
    raw: np.ndarray
    eta: np.ndarray
    ready: np.ndarray
    phase: np.ndarray
    beta: np.ndarray
    time: np.ndarray
    plant_index: np.ndarray
    event_weights: np.ndarray | None = None


def load_split(split: str) -> list[SeqEpisode]:
    manifest_path = OUT / "manifests/D4_SEQUENCE_CACHE.csv"
    if not manifest_path.is_file():
        raise FileNotFoundError("Run d4_sequence_data.py --prepare first")
    manifest = pd.read_csv(manifest_path, keep_default_na=False)
    selected = manifest.loc[manifest.split == split.lower()]
    result = []
    for r in selected.itertuples(index=False):
        path = ROOT / Path(str(r.cache_path).replace("/", "\\"))
        with np.load(path, allow_pickle=False) as z:
            result.append(SeqEpisode(str(z["run_id"]), str(z["scene_id"]), str(z["split"]),
                str(z["role"]), str(z["task"]), int(z["class_index"]), int(z["wind_cell"]), path,
                z["x14"], z["x20"], z["y"], z["raw"], z["eta"], z["ready"], z["phase"],
                z["beta"], z["event_time_s"], z["plant_index"]))
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true")
    args = parser.parse_args()
    if args.prepare:
        build()
    else:
        print("Pass --prepare to build the offline D4 sequence cache")
