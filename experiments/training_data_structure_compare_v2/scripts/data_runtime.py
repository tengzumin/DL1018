from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "experiments" / "training_data_structure_compare_v2"
SOURCE = ROOT / "experiments" / "position_causal_repair_v1"
SOURCE_MANIFEST = SOURCE / "manifests" / "D4_SEQUENCE_CACHE.csv"
SOURCE_CACHE = SOURCE / "derived_events" / "D4_SEQUENCE_CACHE"
ROLES = ("B", "POS_OFF", "P_INIT_STUDENT")
MIXED_MASS = {"B": 0.25, "POS_OFF": 0.25, "P_INIT_STUDENT": 0.50}
TEACHER_MASS = {"B": 0.50, "POS_OFF": 0.50}
TASKS = ("HELIX", "FIG8_3D", "SQUARE")


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
    x14: np.ndarray
    x20: np.ndarray
    y: np.ndarray
    raw: np.ndarray
    eta_logged: np.ndarray
    phase: np.ndarray
    ready: np.ndarray
    beta: np.ndarray
    event_time_s: np.ndarray
    plant_index: np.ndarray
    weights: np.ndarray | None = None


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_reuse_manifest() -> pd.DataFrame:
    df = pd.read_csv(SOURCE_MANIFEST, keep_default_na=False)
    rows = []
    for r in df.itertuples(index=False):
        cache = ROOT / Path(str(r.cache_path).replace("/", "\\"))
        if not cache.is_file():
            raise FileNotFoundError(cache)
        rows.append({"run_id": r.run_id, "scene_id": r.scene_id, "split": r.split,
                     "role": r.role, "task": r.task, "class_index": r.class_index,
                     "wind_cell": r.wind_cell, "source_cache_path": cache.relative_to(ROOT).as_posix(),
                     "size_bytes": cache.stat().st_size, "sha256": sha256(cache)})
    out = pd.DataFrame(rows)
    out.to_csv(OUT / "manifests/REUSED_SEQUENCE_CACHE.csv", index=False)
    return out


def load_episodes(split: str, roles: tuple[str, ...] | None = None) -> list[Episode]:
    m = pd.read_csv(OUT / "manifests/REUSED_SEQUENCE_CACHE.csv", keep_default_na=False)
    q = m[m.split.astype(str).str.lower() == split.lower()]
    if roles is not None:
        q = q[q.role.isin(roles)]
    eps: list[Episode] = []
    for r in q.itertuples(index=False):
        p = ROOT / Path(str(r.source_cache_path).replace("/", "\\"))
        with np.load(p, allow_pickle=False) as z:
            x14 = np.asarray(z["x14"], dtype=np.float32)
            x20 = np.asarray(z["x20"], dtype=np.float32)
            y = np.asarray(z["y"], dtype=np.float32)
            raw = np.asarray(z["raw"], dtype=np.float32)
            eta = np.asarray(z["eta"], dtype=np.float32)
            ready = np.asarray(z["ready"], dtype=bool)
            phase = np.asarray(z["phase"], dtype=np.int64)
            beta = np.asarray(z["beta"], dtype=np.float32)
            event_time = np.asarray(z["event_time_s"], dtype=np.float32)
            plant_index = np.asarray(z["plant_index"], dtype=np.int32)
        if x14.shape != (1999, 14) or x20.shape != (1999, 20) or y.shape != (1999, 3):
            raise ValueError(f"Unexpected cached shapes for {r.run_id}: {x14.shape}, {x20.shape}, {y.shape}")
        if ready.sum() != 1968 or not np.array_equal(ready, np.arange(1999) >= 31):
            raise ValueError(f"Unexpected 32-event readiness for {r.run_id}")
        if not np.isfinite(x14).all() or not np.isfinite(y).all():
            raise ValueError(f"Nonfinite training cache: {r.run_id}")
        eps.append(Episode(str(r.run_id), str(r.scene_id), str(r.split), str(r.role),
                           str(r.task), int(r.class_index), int(r.wind_cell), p, x14, x20,
                           y, raw, eta, phase, ready, beta, event_time, plant_index))
    return eps


def endpoint_indices(ep: Episode, stride: int = 5) -> np.ndarray:
    ids = np.arange(31, len(ep.ready), stride, dtype=np.int64)
    if not ep.ready[ids].all():
        raise ValueError(f"Not-ready endpoint in {ep.run_id}")
    return ids


def assign_weights(eps: list[Episode], masses: dict[str, float], stride: int = 5) -> int:
    counts: dict[tuple[str, str, int], int] = {}
    phases: dict[str, tuple[np.ndarray, dict[int, int]]] = {}
    for ep in eps:
        counts[(ep.role, ep.task, ep.class_index)] = counts.get((ep.role, ep.task, ep.class_index), 0) + 1
        ids = endpoint_indices(ep, stride)
        values, nums = np.unique(ep.phase[ids], return_counts=True)
        phases[ep.run_id] = ids, {int(k): int(v) for k, v in zip(values, nums)}
    weights = 0
    for ep in eps:
        ids, phase_counts = phases[ep.run_id]
        scene_n = counts[(ep.role, ep.task, ep.class_index)]
        phase_n = len(phase_counts)
        w = np.zeros(len(ep.ready), dtype=np.float64)
        for i in ids:
            w[i] = masses[ep.role] / (3 * 16 * scene_n * phase_n * phase_counts[int(ep.phase[i])])
        ep.weights = w
        weights += len(ids)
    total = sum(float(e.weights.sum()) for e in eps)
    if not np.isclose(total, 1.0, atol=1e-9):
        raise AssertionError(f"Weights sum to {total}, expected 1")
    for role, mass in masses.items():
        got = sum(float(e.weights.sum()) for e in eps if e.role == role)
        if not np.isclose(got, mass, atol=1e-9):
            raise AssertionError(f"Source mass mismatch {role}: {got} vs {mass}")
    return weights


def write_micro_pool() -> list[dict]:
    m = pd.read_csv(OUT / "manifests/REUSED_SEQUENCE_CACHE.csv", keep_default_na=False)
    scene_ids = [f"DL1018_TRAIN_T1_C02_W{w:02d}" for w in (4, 8)]
    scene_ids += [f"DL1018_TRAIN_T2_C01_W{w:02d}" for w in (4, 8)]
    scene_ids += [f"DL1018_TRAIN_T3_C03_W{w:02d}" for w in (4, 8)]
    q = m[(m.split == "train") & m.scene_id.isin(scene_ids) & m.role.isin(("B", "POS_OFF"))].copy()
    found = set(q.scene_id)
    if found != set(scene_ids) or len(q) != 12 or q.groupby(["scene_id", "role"]).size().ne(1).any():
        raise RuntimeError(f"Micro pool does not match frozen 12-episode rule: {len(q)} / {sorted(found)}")
    q["window_rule"] = "endpoint indices 31,36,...,1996 inclusive; 32 causal events; stride=5"
    q["endpoint_count"] = q["run_id"].map(lambda _: len(np.arange(31, 1999, 5)))
    q["purpose"] = "DIAGNOSTIC_ONLY; no VAL/DEV selection; never Plant"
    q.to_csv(OUT / "manifests/MICRO_POOL.csv", index=False)
    return q.to_dict(orient="records")

