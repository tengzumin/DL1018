from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "experiments" / "teacher_reuse_model_screen_v1"
ROLES = ("B", "POS_OFF")


def local_path(value: str) -> Path:
    return ROOT / Path(str(value).replace("/", "\\"))


class EpisodeBank:
    """Episode-major continuous events. Windows are gathered only per batch."""

    def __init__(self, split: str, run_ids: set[str] | None = None):
        manifest = pd.read_csv(OUT / "manifests/teacher_reuse_manifest.csv", keep_default_na=False)
        selected = manifest.loc[(manifest.split == split) & manifest.role.isin(ROLES)].copy()
        if run_ids is not None:
            selected = selected.loc[selected.run_id.isin(run_ids)].copy()
        selected = selected.sort_values(["task", "class_index", "scene_id", "role"]).reset_index(drop=True)
        if selected.empty:
            raise RuntimeError(f"No teacher episodes for {split}")
        n, t = len(selected), 1999
        self.meta = selected
        self.x20 = np.empty((n, t, 20), dtype=np.float32)
        self.y = np.empty((n, t, 3), dtype=np.float32)
        self.raw = np.empty((n, t, 3), dtype=np.float32)
        self.phase = np.empty((n, t), dtype=np.uint8)
        for i, row in enumerate(selected.itertuples(index=False)):
            with np.load(local_path(row.sequence_cache_path), allow_pickle=False) as z:
                if str(z["run_id"]) != str(row.run_id):
                    raise RuntimeError(f"Cache identity mismatch: {row.run_id}")
                self.x20[i] = z["x20"]
                self.y[i] = z["y"]
                self.raw[i] = z["raw"]
                self.phase[i] = z["phase"]
        self.x14 = self.x20[:, :, :14]
        if not np.isfinite(self.x20).all() or not np.isfinite(self.y).all():
            raise RuntimeError(f"Non-finite teacher data in {split}")

    def windows(self, length: int, stride: int = 5) -> "WindowSet":
        if length not in (32, 128):
            raise ValueError(f"Unsupported context length {length}")
        ends = np.arange(length - 1, 1999, stride, dtype=np.int32)
        e_count = len(self.meta)
        ep_idx = np.repeat(np.arange(e_count, dtype=np.int32), len(ends))
        end_idx = np.tile(ends, e_count)
        selected = self.meta
        episode_counts: dict[tuple[str, str, int], int] = {}
        for row in selected.itertuples(index=False):
            key = (str(row.role), str(row.task), int(row.class_index))
            episode_counts[key] = episode_counts.get(key, 0) + 1
        weights = np.empty(len(ep_idx), dtype=np.float64)
        phase_samples = self.phase[ep_idx, end_idx]
        for i, row in enumerate(selected.itertuples(index=False)):
            sl = slice(i * len(ends), (i + 1) * len(ends))
            ph = phase_samples[sl]
            unique, counts = np.unique(ph, return_counts=True)
            phase_n = len(unique)
            scene_n = episode_counts[(str(row.role), str(row.task), int(row.class_index))]
            base = 0.5 / (3.0 * 16.0 * scene_n * phase_n)
            count_map = dict(zip(unique.tolist(), counts.tolist()))
            weights[sl] = np.asarray([base / count_map[int(p)] for p in ph], dtype=np.float64)
        if not np.isclose(weights.sum(), 1.0, atol=1e-10):
            raise RuntimeError(f"{self.meta.iloc[0].split} window mass does not sum to one: {weights.sum()}")
        if len(ends) != (394 if length == 32 else 375):
            raise RuntimeError(f"Unexpected {length}-event endpoint count {len(ends)}")
        return WindowSet(self, length, ep_idx, end_idx, weights.astype(np.float32))


@dataclass
class WindowSet:
    bank: EpisodeBank
    length: int
    ep_idx: np.ndarray
    end_idx: np.ndarray
    weights: np.ndarray

    def __post_init__(self) -> None:
        self.target = self.bank.y[self.ep_idx, self.end_idx]
        self.raw_target = self.bank.raw[self.ep_idx, self.end_idx]
        self.phase = self.bank.phase[self.ep_idx, self.end_idx]
        self.role = self.bank.meta.role.to_numpy(dtype=str)[self.ep_idx]
        self.task = self.bank.meta.task.to_numpy(dtype=str)[self.ep_idx]
        self.wind = self.bank.meta.wind_cell.to_numpy(dtype=np.int16)[self.ep_idx]
        self.scene = self.bank.meta.scene_id.to_numpy(dtype=str)[self.ep_idx]

    def batch_numpy(self, ids: np.ndarray, input_dim: int) -> np.ndarray:
        x = self.bank.x20 if input_dim == 20 else self.bank.x14
        ep = self.ep_idx[ids]
        end = self.end_idx[ids]
        offsets = np.arange(self.length - 1, -1, -1, dtype=np.int32)
        return np.ascontiguousarray(x[ep[:, None], end[:, None] - offsets[None, :], :input_dim])


def normalizers() -> dict[str, dict[str, np.ndarray]]:
    audit = json.loads((OUT / "reports/data_interface_audit.json").read_text(encoding="utf-8"))
    norm = audit["normalizer"]
    mu14 = np.asarray(norm["selected_x14_mu"], dtype=np.float32)
    sigma14 = np.asarray(norm["selected_x14_sigma"], dtype=np.float32)
    mu20 = np.asarray(norm["x20_mu"], dtype=np.float32)
    sigma20 = np.asarray(norm["x20_sigma"], dtype=np.float32)
    return {"X14": {"mu": mu14, "sigma": sigma14}, "X20": {"mu": mu20, "sigma": sigma20}}
