"""Episode-local event loading, normalization and exact hierarchical weights."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import h5py
import numpy as np
import pandas as pd


TASKS = ("HELIX", "FIG8_3D", "SQUARE")
PHASES = ("STATIC", "PRE", "EXTEND", "HOLD", "RETRACT", "RECOVERY")
WINDOW = 32


@dataclass
class Episode:
    run_id: str
    scene_id: str
    split: str
    role: str
    task: str
    class_index: int
    wind_cell: int
    path: Path
    x: np.ndarray
    y: np.ndarray
    raw: np.ndarray
    ready: np.ndarray
    phase: np.ndarray


@dataclass
class EventSet:
    x: np.ndarray
    y: np.ndarray
    raw: np.ndarray
    weights: np.ndarray
    role: np.ndarray
    task: np.ndarray
    class_index: np.ndarray
    wind_cell: np.ndarray
    scene_id: np.ndarray
    phase: np.ndarray
    run_id: np.ndarray
    end_index: np.ndarray
    episodes: list[Episode]


def _truth(values: pd.Series) -> np.ndarray:
    return values.astype(str).str.strip().str.lower().isin(("true", "1", "yes")).to_numpy()


def load_episodes(root: Path, split: str, modality: str, roles: tuple[str, ...]) -> list[Episode]:
    index = pd.read_csv(root / "logs" / "episode_index.csv", keep_default_na=False)
    wanted_split = split.lower()
    rows = index[(index["split"].str.lower() == wanted_split)
                 & index["source_role"].isin(roles) & _truth(index["accepted"])].copy()
    expected_file = "position_event_path" if modality == "position" else "attitude_event_path"
    dim = 14 if modality == "position" else 29
    result: list[Episode] = []
    for row in rows.itertuples(index=False):
        rel = getattr(row, expected_file)
        if not rel:
            continue
        path = root / Path(str(rel).replace("/", "\\"))
        if not path.is_file():
            raise FileNotFoundError(f"Accepted {modality} H5 missing for {row.run_id}: {path}")
        with h5py.File(path, "r") as f:
            xkey = "x14" if modality == "position" else "x29"
            ykey = "target_clip" if modality == "position" else "target_normalized"
            x = np.asarray(f[xkey], dtype=np.float64)
            y = np.asarray(f[ykey], dtype=np.float64)
            raw = np.asarray(f["target_raw"], dtype=np.float64)
            ready = np.asarray(f["ready"], dtype=np.uint8).astype(bool)
            phase = np.asarray(f["phase_code"], dtype=np.uint8).astype(np.int64)
        if x.shape != (1999, dim) or y.shape != (1999, 3) or raw.shape != (1999, 3):
            raise ValueError(f"Malformed {modality} episode {path}: {x.shape}, {y.shape}, {raw.shape}")
        if ready.sum() != 1968 or not np.array_equal(ready, np.arange(1999) >= 31):
            raise ValueError(f"Ready mask is not the fixed 32-event boundary: {path}")
        if not np.isfinite(x).all() or not np.isfinite(y).all() or not np.isfinite(raw).all():
            raise ValueError(f"Non-finite accepted data in {path}")
        if phase.min(initial=0) < 0 or phase.max(initial=0) >= len(PHASES):
            raise ValueError(f"Unknown phase code in {path}")
        result.append(Episode(str(row.run_id), str(row.scene_id), wanted_split,
                              str(row.source_role), str(row.task), int(row.class_index),
                              int(row.wind_cell), path, x, y, raw, ready, phase))
    if not result:
        raise RuntimeError(f"No accepted {modality} episodes for {split}/{roles}")
    return result


def fit_normalizer(episodes: list[Episode], modality: str) -> tuple[np.ndarray, np.ndarray]:
    dim = 14 if modality == "position" else 29
    if modality == "position":
        # First ten X14 features use TRAIN population moments; arm commands stay physical.
        values = np.concatenate([e.x for e in episodes], axis=0).astype(np.float64)
        mu, sigma = np.zeros(dim, dtype=np.float64), np.ones(dim, dtype=np.float64)
        mu[:10] = values[:, :10].mean(axis=0)
        sigma[:10] = np.maximum(values[:, :10].std(axis=0, ddof=0), 1e-4)
    else:
        values = np.concatenate([e.x[e.ready] for e in episodes], axis=0).astype(np.float64)
        mu = values.mean(axis=0)
        sigma = np.maximum(values.std(axis=0, ddof=0), 1e-6)
    if not np.isfinite(mu).all() or not np.isfinite(sigma).all() or np.any(sigma <= 0):
        raise ValueError("Normalizer contains invalid values")
    return mu, sigma


def make_event_set(episodes: list[Episode], stride: int,
                   source_mass: dict[str, float]) -> EventSet:
    if stride < 1:
        raise ValueError("stride must be positive")
    selected = [e for e in episodes if e.role in source_mass]
    if set(e.role for e in selected) != set(source_mass):
        raise ValueError(f"Source roles mismatch: {set(e.role for e in selected)} vs {set(source_mass)}")
    scene_counts: dict[tuple[str, str, int], int] = {}
    for e in selected:
        key = (e.role, e.task, e.class_index)
        scene_counts[key] = scene_counts.get(key, 0) + 1
    if set(e.task for e in selected) != set(TASKS) or set(e.class_index for e in selected) != set(range(16)):
        raise ValueError("Training pool must cover all three tasks and sixteen configurations")
    for role in source_mass:
        role_counts = {scene_counts.get((role, task, c), 0) for task in TASKS for c in range(16)}
        if len(role_counts) != 1 or next(iter(role_counts)) not in (1, 8, 16):
            raise ValueError(f"Incomplete role allocation for {role}: {role_counts}")
        expected_scenes = 1 if selected[0].split == "val" else (8 if role.endswith("STUDENT") else 16)
        if role_counts != {expected_scenes}:
            raise ValueError(f"Wrong role quota for {selected[0].split}/{role}: {role_counts}; "
                             f"expected {expected_scenes} scenes per task/configuration")
        for task in TASKS:
            for c in range(16):
                if scene_counts.get((role, task, c), 0) not in (1, 8, 16):
                    raise ValueError(f"Incomplete role/task/config allocation: {role}/{task}/{c}")
    xs, ys, raws, ws = [], [], [], []
    roles, tasks, classes, winds, scenes, phases, runs, ends = [], [], [], [], [], [], [], []
    role_phase_window_counts: dict[tuple[str, str, int], dict[int, int]] = {}
    per_episode: list[tuple[Episode, np.ndarray, np.ndarray]] = []
    for e in selected:
        endpoint = np.arange(WINDOW - 1, len(e.x), stride, dtype=np.int64)
        if not e.ready[endpoint].all():
            raise ValueError(f"Window endpoint before ready for {e.run_id}")
        ph = e.phase[endpoint]
        phases_present = np.unique(ph)
        counts = {int(p): int(np.count_nonzero(ph == p)) for p in phases_present}
        if not counts or any(n == 0 for n in counts.values()):
            raise ValueError(f"No valid phase windows for {e.run_id}")
        role_phase_window_counts[(e.role, e.scene_id, e.class_index)] = counts
        per_episode.append((e, endpoint, ph))
    for e, endpoint, ph in per_episode:
        scene_n = scene_counts[(e.role, e.task, e.class_index)]
        phase_n = len(role_phase_window_counts[(e.role, e.scene_id, e.class_index)])
        win_counts = role_phase_window_counts[(e.role, e.scene_id, e.class_index)]
        sample_w = np.asarray([source_mass[e.role] / (3 * 16 * scene_n * phase_n * win_counts[int(p)])
                               for p in ph], dtype=np.float64)
        xs.append(e.x[endpoint].astype(np.float32))
        ys.append(e.y[endpoint].astype(np.float32))
        raws.append(e.raw[endpoint].astype(np.float32))
        ws.append(sample_w)
        n = len(endpoint)
        roles.extend([e.role] * n); tasks.extend([e.task] * n)
        classes.extend([e.class_index] * n); winds.extend([e.wind_cell] * n)
        scenes.extend([e.scene_id] * n); phases.extend(ph.tolist())
        runs.extend([e.run_id] * n); ends.extend(endpoint.tolist())
    out = EventSet(np.concatenate(xs), np.concatenate(ys), np.concatenate(raws), np.concatenate(ws),
                   np.asarray(roles, dtype=object), np.asarray(tasks, dtype=object),
                   np.asarray(classes, dtype=np.int64), np.asarray(winds, dtype=np.int64),
                   np.asarray(scenes, dtype=object), np.asarray(phases, dtype=np.int64),
                   np.asarray(runs, dtype=object), np.asarray(ends, dtype=np.int64), selected)
    if not np.isclose(out.weights.sum(), 1.0, atol=1e-10):
        raise AssertionError(f"Global event weights sum to {out.weights.sum():.17g}, not one")
    for role, mass in source_mass.items():
        if not np.isclose(out.weights[out.role == role].sum(), mass, atol=1e-9):
            raise AssertionError(f"Source weight imbalance for {role}")
        for task in TASKS:
            actual = out.weights[(out.role == role) & (out.task == task)].sum()
            if not np.isclose(actual, mass / 3, atol=1e-9):
                raise AssertionError(f"Source/task weight imbalance for {role}/{task}: {actual}")
    wind_sums = np.asarray([out.weights[out.wind_cell == w].sum() for w in range(16)])
    if not np.allclose(wind_sums, np.full(16, 1.0 / 16.0), atol=1e-9, rtol=0):
        raise AssertionError(f"Wind-cell training mass is not balanced: {wind_sums.tolist()}")
    return out


def weight_report(data: EventSet) -> dict:
    source_task = {}
    for role in np.unique(data.role):
        for task in TASKS:
            m = (data.role == role) & (data.task == task)
            source_task[f"{role}/{task}"] = float(data.weights[m].sum())
    wind = {str(w): float(data.weights[data.wind_cell == w].sum()) for w in range(16)}
    phase = {str(p): float(data.weights[data.phase == p].sum()) for p in range(len(PHASES))}
    source_phase = {f"{role}/{p}": float(data.weights[(data.role == role) & (data.phase == p)].sum())
                    for role in np.unique(data.role) for p in range(len(PHASES))}
    return {"source_task_sums": source_task, "wind_sums": wind,
            "phase_sums": phase, "source_phase_sums": source_phase,
            "sample_count": int(len(data.weights)), "weight_total": float(data.weights.sum())}
