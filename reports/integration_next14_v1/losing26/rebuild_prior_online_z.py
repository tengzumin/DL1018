from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import h5py
import numpy as np


sys.dont_write_bytecode = True
OUT = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT.parent
AUDIT_SCRIPTS = BASE / "DL1009_DL1018_FULL_AUDIT_20261020_233501" / "scripts"
sys.path.insert(0, str(AUDIT_SCRIPTS))
from raw_scan import arr  # pure HDF5 array orientation helper


FIELDS = (
    "stage1_position_event_inference_valid",
    "stage1_position_event_step_index",
    "stage1_position_event_phi_33",
    "stage1_position_event_weight_before_33x3",
    "stage1_position_event_weight_after_33x3",
    "stage1_position_weight_initial",
    "stage1_position_event_raw_acceleration_mps2",
)
SEGMENTS = ((0.0, 5.0, "0_5"), (5.0, 20.0, "5_20"), (0.0, 20.0, "0_20"))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="raise", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def rows_by_event(a: np.ndarray, n_events: int, label: str) -> np.ndarray:
    a = np.asarray(a, dtype=np.float64)
    if a.ndim == 3 and a.shape[:2] == (33, 3) and a.shape[2] == n_events:
        a = np.moveaxis(a, -1, 0)
    if a.shape != (n_events, 33, 3):
        raise ValueError(f"{label}: oriented shape {a.shape}, expected {(n_events, 33, 3)}")
    return a


def matrix_33x3(a: np.ndarray) -> np.ndarray:
    a = np.asarray(a, dtype=np.float64)
    if a.shape == (3, 33):
        a = a.T
    if a.shape != (33, 3):
        raise ValueError(f"W_initial shape {a.shape}, expected (33,3)")
    return a


def describe(a: np.ndarray) -> tuple[str, int, int]:
    a = np.asarray(a)
    return "x".join(map(str, a.shape)), int(a.size), int(np.isfinite(a).sum())


def output_stats(a: np.ndarray) -> tuple[float, float]:
    return float(np.mean(a)), float(np.sqrt(np.mean(np.square(a))))


def run() -> None:
    whitelist = [r for r in read_csv(OUT / "raw_whitelist.csv") if r["method"] == "DSSM14"]
    if len(whitelist) != 29 or {r["split"] for r in whitelist} - {"VAL", "DEV"}:
        raise ValueError("expected exactly the 29 whitelisted VAL/DEV DSSM14 raws")
    result_rows, coverage_rows = [], []

    for row in whitelist:
        path = Path(row["raw_path"])
        before = path.stat()
        digest = sha256(path)
        if digest.lower() != row["expected_raw_sha256"].lower():
            raise ValueError(f"raw SHA mismatch: {path}")
        if (before.st_size != int(row["integrity_size_bytes"])
                or before.st_mtime_ns != int(row["integrity_mtime_ns"])):
            raise ValueError(f"raw size/mtime differs from whitelist: {path}")
        if row["candidate_replay_status"] != "REPLAY_VALID" or float(row["candidate_W0_error"]) > 1e-8:
            raise ValueError(f"trained W0 identity is not verified: {row['source_scene_id']}")

        with h5py.File(path, "r") as f:
            log = f["log"]
            values, native_shapes = {}, {}
            for name in FIELDS:
                if name not in log:
                    raise KeyError(f"missing {name}: {path}")
                native_shapes[name] = "x".join(map(str, log[name].shape))
                values[name] = np.asarray(arr(log, name))

            times = np.asarray(arr(log, "transition_time"), dtype=np.float64).reshape(-1)
            valid_raw = np.asarray(values[FIELDS[0]], dtype=np.float64).reshape(-1)
            if not np.isfinite(valid_raw).all():
                raise ValueError(f"non-finite inference mask: {path}")
            valid = valid_raw.astype(bool)
            event_ix = np.flatnonzero(valid)
            n_events = len(event_ix)
            if len(times) != 20000 or n_events != 1968 or not np.all(np.diff(times) > 0):
                raise ValueError(f"transition/event contract mismatch: {path}")
            step_raw = np.asarray(values[FIELDS[1]], dtype=np.float64).reshape(-1)
            if not np.isfinite(step_raw).all() or not np.array_equal(step_raw, np.rint(step_raw)):
                raise ValueError(f"non-finite/non-integer step index: {path}")
            step_index = step_raw.astype(np.int64)
            if not np.array_equal(step_index, event_ix + 1):
                raise ValueError(f"step-index/event-mask mismatch: {path}")
            if abs(times[event_ix[0]] - 0.32) > 1e-12 or abs(times[event_ix[-1]] - 19.99) > 1e-10:
                raise ValueError(f"valid event time bounds mismatch: {path}")

            phi_all = np.asarray(values[FIELDS[2]], dtype=np.float64)
            if phi_all.shape != (len(times), 33):
                raise ValueError(f"phi_33 oriented shape mismatch: {phi_all.shape}")
            phi = phi_all[event_ix]
            w_before_all = rows_by_event(values[FIELDS[3]], n_events, "weight_before")
            w_after_all = rows_by_event(values[FIELDS[4]], n_events, "weight_after")
            w_initial = matrix_33x3(values[FIELDS[5]])
            raw_all = np.asarray(values[FIELDS[6]], dtype=np.float64)
            if raw_all.shape != (len(times), 3):
                raise ValueError(f"raw acceleration oriented shape mismatch: {raw_all.shape}")
            raw_actual = raw_all[event_ix]
            if not all(np.isfinite(a).all() for a in (phi, w_before_all, w_after_all, w_initial, raw_actual)):
                raise ValueError(f"non-finite value on valid events: {path}")

            online = np.einsum("nij,ni->nj", w_before_all, phi)
            prior = phi @ w_initial
            max_raw_reconstruction_error = float(np.max(np.abs(online - raw_actual)))
            if max_raw_reconstruction_error > 1e-8:
                raise ValueError(f"W_before x phi does not reproduce logged raw: {path}, {max_raw_reconstruction_error}")
            online_z = online[:, 2]
            prior_z = prior[:, 2]
            delta_z = online_z - prior_z
            event_times = times[event_ix]

            identity = {k: row[k] for k in ("selection_role", "split", "task", "source_scene_id", "contract_id")}
            for lo, hi, segment in SEGMENTS:
                mask = (event_times >= lo) & (event_times < hi)
                if not mask.any():
                    raise ValueError(f"empty valid event segment {segment}: {path}")
                prior_mean, prior_rms = output_stats(prior_z[mask])
                online_mean, online_rms = output_stats(online_z[mask])
                delta_mean, delta_rms = output_stats(delta_z[mask])
                result_rows.append({
                    **identity, "segment": segment, "event_count": int(mask.sum()),
                    "raw_sha256": digest, "W_initial_fro_norm": float(np.linalg.norm(w_initial)),
                    "online_raw_reconstruction_max_abs_mps2": max_raw_reconstruction_error,
                    "W_initial_z_mean_mps2": prior_mean, "W_initial_z_rms_mps2": prior_rms,
                    "online_raw_z_mean_mps2": online_mean, "online_raw_z_rms_mps2": online_rms,
                    "online_minus_W_initial_z_mean_mps2": delta_mean,
                    "online_minus_W_initial_z_rms_mps2": delta_rms,
                })

            event_shapes = {
                FIELDS[0]: valid,
                FIELDS[1]: step_index,
                FIELDS[2]: phi,
                FIELDS[3]: w_before_all,
                FIELDS[4]: w_after_all,
                FIELDS[5]: w_initial,
                FIELDS[6]: raw_actual,
            }
            for name, value in event_shapes.items():
                shape, total, finite = describe(value)
                coverage_rows.append({
                    **identity, "field": name, "native_h5_shape": native_shapes[name],
                    "arr_or_event_shape": shape, "event_count": n_events,
                    "selected_values": total, "finite_selected_values": finite,
                    "finite_valid_event_rows": int(np.isfinite(value).reshape(n_events, -1).all(axis=1).sum())
                    if value.ndim > 1 and value.shape[0] == n_events else finite,
                })

        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise RuntimeError(f"raw changed during read: {path}")
        print(f"rebuilt {len(result_rows) // 3}/29 candidate raws", flush=True)

    write_csv(OUT / "prior_online_z_rebuild.csv", result_rows)
    write_csv(OUT / "prior_online_z_field_coverage.csv", coverage_rows)

    summaries = {}
    for role in ("LOSS", "FIXED_TASK_WIN"):
        summaries[role] = {}
        for _, _, segment in SEGMENTS:
            xs = [r for r in result_rows if r["selection_role"] == role and r["segment"] == segment]
            n = len(xs)
            summaries[role][segment] = {
                "scenes": n,
                "events_per_scene": sorted({r["event_count"] for r in xs}),
            }
            for metric in ("W_initial_z_mean_mps2", "W_initial_z_rms_mps2",
                           "online_raw_z_mean_mps2", "online_raw_z_rms_mps2",
                           "online_minus_W_initial_z_mean_mps2", "online_minus_W_initial_z_rms_mps2"):
                vals = np.asarray([r[metric] for r in xs], dtype=np.float64)
                summaries[role][segment][f"macro_{metric}"] = float(np.mean(vals))
    summary = {
        "status": "PASS_W_BEFORE_PHI_RAW_RECONSTRUCTION",
        "scope": "29 whitelist DSSM14 VAL/DEV raws only; no B, TEST, beta, clip, or target used",
        "fields_checked": list(FIELDS),
        "field_coverage_rows": len(coverage_rows),
        "scene_segment_rows": len(result_rows),
        "all_raw_reconstruction_max_abs_mps2": float(max(r["online_raw_reconstruction_max_abs_mps2"] for r in result_rows)),
        "raw_reconstruction_threshold_mps2": 1e-8,
        "phase_segments": {
            s: {"events_per_scene": sorted({r["event_count"] for r in result_rows if r["segment"] == s})}
            for _, _, s in SEGMENTS
        },
        "by_selection_role": summaries,
        "interpretation": "W_initial x phi and W_before x phi are same-state raw model outputs. Their difference is an output change, not an error, improvement, or causal attribution; no target was introduced.",
    }
    (OUT / "prior_online_z_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": summary["status"], "scene_segment_rows": len(result_rows),
        "field_coverage_rows": len(coverage_rows),
        "max_raw_reconstruction_abs_mps2": summary["all_raw_reconstruction_max_abs_mps2"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run()
