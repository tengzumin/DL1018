"""Read-only marginal alpha_BS x/y support diagnostic for pinned TRAIN caches."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_REL = "reports/attitude_cm18_a1_20261024/data_preparation_v1/events_all816_v1/DATASET_MANIFEST_v1.json"
INPUT_MANIFEST_SHA256 = "a5f7fea9b0918c1449af6fa83929177d3bf7d5e70cb3b71711c40f6338d210a5"
MANIFEST_SHA256 = "7dd3e1f786f6095ecc2ba56473e5cf0fab6b92cdd42e38a184d6ad1223f36271"
CACHE_READER_REL = "experiments/attitude_cm18_a1_20261024/cache_reader_cm18_v1.py"
CACHE_READER_SHA256 = "a2867cbf516d7ed655a6f50e05b8600ffb7582e0f2164b1ce21d5e647adf2b47"
TRAINER_REL = "experiments/attitude_cm18_a1_20261024/train_cm18_a1_v1.py"
TRAINER_SHA256 = "7544a04329bc1e06ff5d7a113a077033a65f0b7c2de8a6f1b25ac54710e62c76"
EXPORTER_REL = "experiments/attitude_position_context_probe_20261024/export_matched_position_probe_events_v2.m"
EXPORTER_SHA256 = "ddb1684b1d720d9bee80b3bcda2c95bf855faee1220fc54e9ba764695c5a54a9"
EVENT_DIR_REL = "reports/attitude_position_context_probe_20261024/offline_events_v2"
FEATURE_COLUMNS = (3, 4)  # zero-based X18 columns alpha_BS_x/y
SAMPLED_EVENT_INDEX = np.arange(0, 1996, 5, dtype=np.int64)

PROBES = {
    "T1_B": {
        "scene_id": "DL1018_TRAIN_T1_C15_W14",
        "position_mode": "B_POSITION_RBF",
        "attempt_id": 2,
        "export_sha256": "574edcdc35483c6069bd053ae345a2ddee1c61780b7e044dea422b7b01fbf08c",
    },
    "T1_C5": {
        "scene_id": "DL1018_TRAIN_T1_C15_W14",
        "position_mode": "C5_POSITION_M110",
        "attempt_id": 1,
        "export_sha256": "6440649b1f6b45b483158d963e34f99ee6d5d47b961860422556f9c450f75749",
    },
    "T3_B": {
        "scene_id": "DL1018_TRAIN_T3_C15_W14",
        "position_mode": "B_POSITION_RBF",
        "attempt_id": 1,
        "export_sha256": "bc5e8499347d071f736a5aa7a0a8d1173e3b9633aaeb2182b14256666d2f7594",
    },
    "T3_C5": {
        "scene_id": "DL1018_TRAIN_T3_C15_W14",
        "position_mode": "C5_POSITION_M110",
        "attempt_id": 1,
        "export_sha256": "27c5af24ac01f0ea90eb8a1138a8d947c9c568f945c64c05cced3da08117a7f4",
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def need(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def safe_repo_path(relative: str) -> Path:
    root = ROOT.resolve(strict=True)
    path = (root / relative).resolve(strict=True)
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"repository-relative path escaped root: {relative}") from exc
    return path


def load_reader():
    path = safe_repo_path(CACHE_READER_REL)
    need(sha256(path) == CACHE_READER_SHA256, "pinned cache_reader source SHA mismatch")
    trainer_path = safe_repo_path(TRAINER_REL)
    need(sha256(trainer_path) == TRAINER_SHA256, "pinned trainer sampling source SHA mismatch")
    spec = importlib.util.spec_from_file_location("pinned_cm18_cache_reader", path)
    need(spec is not None and spec.loader is not None, "cannot import pinned cache_reader")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_manifest() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    path = safe_repo_path(MANIFEST_REL)
    need(sha256(path) == MANIFEST_SHA256, "ALL816 manifest SHA mismatch")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    need(manifest.get("schema") == "CM18_A1_DATASET_MANIFEST_V1" and
         manifest.get("mode") == "ALL816" and manifest.get("TEST_accessed") is False,
         "unexpected ALL816 manifest identity or TEST isolation marker")
    rows = manifest.get("rows")
    need(isinstance(rows, list) and len(rows) == 816 and
         int(manifest.get("scene_count", -1)) == 816 and
         int(manifest.get("qualified_count", -1)) == 816 and
         int(manifest.get("failed_count", -1)) == 0,
         "ALL816 manifest counts/status are not complete")
    scene_ids = [row.get("scene_id") for row in rows]
    need(len(set(scene_ids)) == 816, "manifest scene IDs are not unique")
    need(all(row.get("qualified") is True and row.get("status") == "PASS" for row in rows),
         "manifest contains a failed or unqualified row")
    split_counts = {split: sum(row.get("split") == split for row in rows) for split in ("TRAIN", "VAL", "TEST")}
    need(split_counts == {"TRAIN": 768, "VAL": 48, "TEST": 0},
         f"unexpected split counts: {split_counts}")
    need(str(manifest.get("input_manifest_sha256", "")).lower() == INPUT_MANIFEST_SHA256,
         "manifest input identity differs from pinned input manifest")
    return manifest, [row for row in rows if row.get("split") == "TRAIN"]


def train_bounds(reader: Any, manifest: dict[str, Any], train_rows: list[dict[str, Any]]) -> dict[str, Any]:
    full_lo = np.full(2, np.inf, dtype=np.float64)
    full_hi = np.full(2, -np.inf, dtype=np.float64)
    sampled_lo = np.full(2, np.inf, dtype=np.float64)
    sampled_hi = np.full(2, -np.inf, dtype=np.float64)
    full_count = sampled_count = cache_bytes = 0
    loaded_ids: list[str] = []
    input_manifest_sha = str(manifest["input_manifest_sha256"]).lower()
    need(SAMPLED_EVENT_INDEX.shape == (400,) and int(SAMPLED_EVENT_INDEX[-1]) == 1995,
         "frozen TRAIN index rule no longer yields 400 rows")

    for row in train_rows:
        # _read_scene verifies cache path containment, byte count, SHA, MAT schema,
        # finite values, event timing/index, scene/split and input-manifest identity.
        scene = reader._read_scene(ROOT, row, input_manifest_sha)
        x = scene["X18"]
        xy = x[:, FEATURE_COLUMNS]
        xy_sampled = xy[SAMPLED_EVENT_INDEX]
        need(xy.shape == (1999, 2) and xy_sampled.shape == (400, 2),
             f"{scene['scene_id']}: alphaXY row-count mismatch")
        full_lo = np.minimum(full_lo, np.min(xy, axis=0))
        full_hi = np.maximum(full_hi, np.max(xy, axis=0))
        sampled_lo = np.minimum(sampled_lo, np.min(xy_sampled, axis=0))
        sampled_hi = np.maximum(sampled_hi, np.max(xy_sampled, axis=0))
        full_count += xy.shape[0]
        sampled_count += xy_sampled.shape[0]
        cache_bytes += int(row["cache_bytes"])
        loaded_ids.append(scene["scene_id"])

    need(len(loaded_ids) == 768 and len(set(loaded_ids)) == 768 and
         full_count == 768 * 1999 and sampled_count == 768 * 400,
         "TRAIN cache count or event totals mismatch")
    return {
        "cache_scene_count": len(loaded_ids),
        "cache_bytes_verified_sum": cache_bytes,
        "full_event_rows_per_scene": 1999,
        "full_event_count": full_count,
        "training_sample_rule": {
            "zero_based_event_indices": "0,5,...,1995",
            "stride": 5,
            "rows_per_scene": 400,
            "sampled_event_count": sampled_count,
            "source": TRAINER_REL,
            "source_sha256": TRAINER_SHA256,
        },
        "feature_names": ["alpha_BS_x", "alpha_BS_y"],
        "full_1999_event_support": {"min": full_lo.tolist(), "max": full_hi.tolist()},
        "stride_0_5_support": {"min": sampled_lo.tolist(), "max": sampled_hi.tolist()},
        "loaded_scene_ids_sha256": hashlib.sha256("\n".join(loaded_ids).encode("utf-8")).hexdigest(),
    }


def probe_events() -> dict[str, dict[str, Any]]:
    event_dir = safe_repo_path(EVENT_DIR_REL)
    need(sha256(safe_repo_path(EXPORTER_REL)) == EXPORTER_SHA256,
         "pinned v2 event exporter SHA mismatch")
    result = {}
    for flight, expected in PROBES.items():
        path = event_dir / f"events_{flight}_v2.json"
        need(path.is_file() and sha256(path) == expected["export_sha256"],
             f"{flight}: event export is missing or SHA mismatch")
        exported = json.loads(path.read_text(encoding="utf-8"))
        need(exported.get("schema") == "MATCHED_POSITION_PROBE_EVENT_EXPORT_V2" and
             exported.get("status") == "PASS", f"{flight}: event export status/schema mismatch")
        identity = exported.get("identity", {})
        need(identity.get("flight_id") == flight and
             identity.get("scene_id") == expected["scene_id"] and
             identity.get("split") == "TRAIN" and
             identity.get("position_mode") == expected["position_mode"] and
             int(identity.get("attempt_id", -1)) == expected["attempt_id"] and
             identity.get("exporter_source_sha256", "").lower() == EXPORTER_SHA256,
             f"{flight}: event export identity mismatch")
        x = np.asarray(exported.get("X18"), dtype=np.float64)
        need(x.shape == (1999, 18) and np.isfinite(x).all(),
             f"{flight}: event export X18 shape/finite check failed")
        event_index = np.asarray(exported.get("event_index"), dtype=np.int64).reshape(-1)
        plant_index = np.asarray(exported.get("plant_index"), dtype=np.int64).reshape(-1)
        event_time = np.asarray(exported.get("event_time_s"), dtype=np.float64).reshape(-1)
        need(np.array_equal(event_index, np.arange(1, 2000, dtype=np.int64)) and
             np.array_equal(plant_index, np.arange(11, 20000, 10, dtype=np.int64)) and
             event_time.shape == (1999,) and np.isfinite(event_time).all() and
             np.max(np.abs(event_time - np.arange(0.01, 20.0, 0.01))) <= 1e-12,
             f"{flight}: event sequence/timebase mismatch")
        result[flight] = {"xy": x[:, FEATURE_COLUMNS], "identity": identity,
                          "event_export_sha256": expected["export_sha256"]}
    return result


def range_report(probe_xy: np.ndarray, low: np.ndarray, high: np.ndarray) -> dict[str, Any]:
    below = probe_xy < low
    above = probe_xy > high
    outside = below | above
    count = probe_xy.shape[0]
    per_axis = {}
    for axis, column in (("alpha_BS_x", 0), ("alpha_BS_y", 1)):
        per_axis[axis] = {
            "below_count": int(np.count_nonzero(below[:, column])),
            "above_count": int(np.count_nonzero(above[:, column])),
            "outside_count": int(np.count_nonzero(outside[:, column])),
            "outside_rate": float(np.mean(outside[:, column])),
        }
    any_outside = np.any(outside, axis=1)
    return {
        "probe_event_count": count,
        "probe_xy_min": np.min(probe_xy, axis=0).tolist(),
        "probe_xy_max": np.max(probe_xy, axis=0).tolist(),
        "outside_by_axis": per_axis,
        "outside_any_axis_event_count": int(np.count_nonzero(any_outside)),
        "outside_any_axis_event_rate": float(np.mean(any_outside)),
        "comparison": "strict component-wise outside test: value < TRAIN min or value > TRAIN max",
    }


def run() -> dict[str, Any]:
    reader = load_reader()
    manifest, train_rows = read_manifest()
    bounds = train_bounds(reader, manifest, train_rows)
    probes = probe_events()
    low_full = np.asarray(bounds["full_1999_event_support"]["min"], dtype=np.float64)
    high_full = np.asarray(bounds["full_1999_event_support"]["max"], dtype=np.float64)
    low_sampled = np.asarray(bounds["stride_0_5_support"]["min"], dtype=np.float64)
    high_sampled = np.asarray(bounds["stride_0_5_support"]["max"], dtype=np.float64)
    probe_results = {}
    for flight, data in probes.items():
        xy = data["xy"]
        probe_results[flight] = {
            "scene_id": data["identity"]["scene_id"],
            "position_mode": data["identity"]["position_mode"],
            "attempt_id": data["identity"]["attempt_id"],
            "event_export_sha256": data["event_export_sha256"],
            "against_full_train_1999_support": range_report(xy, low_full, high_full),
            "against_trained_stride_0_5_support": range_report(xy, low_sampled, high_sampled),
        }
    aggregate = np.concatenate([entry["xy"] for entry in probes.values()], axis=0)
    return {
        "schema": "ROOT_ALPHA_XY_TRAIN_MARGINAL_SUPPORT_DIAGNOSTIC_V1",
        "status": "PASS",
        "identity": {
            "dataset_manifest_path": MANIFEST_REL,
            "dataset_manifest_sha256": MANIFEST_SHA256,
            "input_manifest_sha256": INPUT_MANIFEST_SHA256,
            "cache_reader_path": CACHE_READER_REL,
            "cache_reader_sha256": CACHE_READER_SHA256,
            "trainer_path": TRAINER_REL,
            "trainer_sha256": TRAINER_SHA256,
            "event_exporter_path": EXPORTER_REL,
            "event_exporter_sha256": EXPORTER_SHA256,
        },
        "train_support": bounds,
        "probe_scenes": probe_results,
        "aggregate_four_probe_flights": {
            "event_count": int(aggregate.shape[0]),
            "against_full_train_1999_support": range_report(aggregate, low_full, high_full),
            "against_trained_stride_0_5_support": range_report(aggregate, low_sampled, high_sampled),
        },
        "interpretation_limits": [
            "This is marginal per-feature min/max coverage, not joint-support coverage or a causal test.",
            "A cache event outside a component-wise TRAIN range does not by itself establish harmful extrapolation.",
            "Only SHA-pinned TRAIN cache MAT files and the four SHA-pinned probe event JSON files are read; no raw MAT, VAL/TEST cache, Plant, training, or optimizer is used.",
        ],
        "scope": {
            "TRAIN_caches_read": 768,
            "TRAIN_event_rows_read": 768 * 1999,
            "training_stride_rows_examined": 768 * 400,
            "probe_events_per_flight": 1999,
            "probe_flights": list(PROBES),
            "raw_files_read": 0,
            "VAL_accessed": False,
            "TEST_accessed": False,
            "plant_calls": 0,
            "training_steps": 0,
            "optimizer_steps": 0,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("reports/attitude_position_context_probe_20261024/ROOT_ALPHA_XY_TRAIN_SUPPORT_DIAGNOSTIC_v1.json"))
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output = output.resolve()
    try:
        output.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise ValueError("output path must remain inside the repository") from exc
    need(not output.exists(), f"refusing to overwrite {output}")
    result = run()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": result["status"], "output": str(output),
                      "train_caches": result["scope"]["TRAIN_caches_read"],
                      "probe_flights": result["scope"]["probe_flights"]}, indent=2))


if __name__ == "__main__":
    main()
