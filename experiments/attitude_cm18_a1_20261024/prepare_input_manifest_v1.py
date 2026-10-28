#!/usr/bin/env python3
"""Hash-lock TRAIN/VAL B event H5 and raw inputs; this script reads no arrays."""
from __future__ import annotations

import hashlib
import json
import os
import string
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports/attitude_cm18_a1_20261024/data_preparation_v1/INPUT_MANIFEST_v1.json"
EXPECTED = {"train": 768, "val": 48}
REFERENCE_SOURCES = {
    "matlab/core/arm_mass_properties.m": "8ec66e107156b5219f7e41aca2464eef1ec8043eb7f67df313c0f23ef4b551f5",
    "matlab/core/distributed_mass_properties.m": "db380b506e4bacc37bc398d5726c5ebd25be8ebc08b6c9e76ff59bc78fd45d3a",
    "matlab/core/arm_directions.m": "517bbfcd0df9526b189f64bff067a49551f573ad96e682ee005533ab510e686c",
    "matlab/core/simulation_parameters.m": "962b5434c23d5ac1a9ac568f136635a8ea651a775165d84b7d95250ca88bb9ae",
    "matlab/core/controller_parameters.m": "4fad5e78c0bd4177461647af167e7c86a7defa628b43d523b0b7da2ef5556398",
    "matlab/core/vehicle_derivative.m": "c3258dd5b70268d1465ca7701855b065244aebfaf5816c85e959d39015cd2786",
    "matlab/core/attitude_bs_step.m": "cf6b20ffc4df2625d9316a80340d69542e380d14feaed66ef8498e793fdaccbc",
    "matlab/data/export_attitude_events_dl1018.m": "baeca25a27ee411e900d38333c888a91aa7ce2c5a17ad58cc6989f7aea684141",
    "matlab/data/attitude_events_source_v311.m": "a97bc8585e916e7fc78651200eaf2ae04e4a90ce575865ce5fa7989f52f94792",
    "matlab/data/attitude_feature_row_v3_6.m": "ed65a4fa52321aace622549bb4f444410264f53fc753f12fd49e6acd02415616",
    "experiments/position_axis_coordinate_c5_dev72_20261023/run_dl1018_closed_loop.m": "48350037b66efe00301b138068f187c62cf92583f0f9ba2fabc9b24f248a963c",
}


def need(ok: bool, why: str) -> None:
    if not ok:
        raise RuntimeError(why)


def sha256(path: Path) -> tuple[str, int]:
    before = path.stat()
    h = hashlib.sha256()
    size = 0
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
            size += len(block)
    after = path.stat()
    need((before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns),
         f"file changed while hashing: {path}")
    need(size == after.st_size, f"short read while hashing: {path}")
    return h.hexdigest(), size


def rel(path: Path) -> str:
    resolved = path.resolve()
    need(resolved.is_relative_to(ROOT), f"path escapes repository: {path}")
    return resolved.relative_to(ROOT).as_posix()


def hash_record(path: Path, role: str) -> dict:
    digest, size = sha256(path)
    return {"role": role, "path": rel(path), "size_bytes": size, "sha256": digest}


def main() -> int:
    need(not OUT.exists() and not OUT.with_suffix(OUT.suffix + ".tmp").exists(),
         f"refusing to overwrite manifest: {OUT}")

    sources = []
    for relative, expected in REFERENCE_SOURCES.items():
        path = ROOT / relative
        digest, size = sha256(path)
        need(digest == expected, f"reference source SHA mismatch: {relative}")
        sources.append({"role": "reference_source_not_asserted_as_raw_producer",
                        "path": relative, "size_bytes": size, "sha256": digest})
    local_sources = [
        Path(__file__).resolve(),
        ROOT / "experiments/attitude_cm18_a1_20261024/export_cm18_events_v1.m",
        ROOT / "experiments/attitude_cm18_a1_20261024/run_cm18_export_v1.m",
    ]
    need(all(len(value) == 64 and all(c in string.hexdigits for c in value)
             for value in REFERENCE_SOURCES.values()),
         "reference source digest constants must be 64 hexadecimal characters")
    for path in local_sources:
        need(path.is_file(), f"missing new source: {path}")
        sources.append(hash_record(path, "new_preparation_source"))

    scenes = []
    for split, expected_count in EXPECTED.items():
        event_dir = ROOT / "data/events/attitude" / split
        h5_paths = sorted(event_dir.glob("*/B.h5"), key=lambda p: p.parent.name)
        need(len(h5_paths) == expected_count, f"{split}: expected {expected_count} B.h5 files, found {len(h5_paths)}")
        ids = [p.parent.name for p in h5_paths]
        need(len(set(ids)) == len(ids), f"duplicate scene IDs in {split}")
        for h5_path in h5_paths:
            scene_id = h5_path.parent.name
            raw_dir = ROOT / "data/raw" / split / scene_id / "B/attempt_01"
            raw_path, start_path = raw_dir / "raw_run.mat", raw_dir / "run_start.mat"
            need(h5_path.is_file() and raw_path.is_file() and start_path.is_file(),
                 f"incomplete B input triplet: {split}/{scene_id}")
            scenes.append({
                "split": split.upper(), "scene_id": scene_id, "collector": "B",
                "files": [hash_record(h5_path, "event_h5"),
                          hash_record(raw_path, "raw_run"),
                          hash_record(start_path, "run_start")],
            })

    need(sum(x["split"] == "TRAIN" for x in scenes) == 768 and
         sum(x["split"] == "VAL" for x in scenes) == 48 and len(scenes) == 816,
         "expected exactly TRAIN768 + VAL48")
    need(len({x["scene_id"] for x in scenes}) == 816, "TRAIN/VAL scene IDs overlap")
    # Recheck source files after input hashing so the manifest cannot bind a mixed source state.
    for row in sources:
        current, current_size = sha256(ROOT / row["path"])
        need(current == row["sha256"] and current_size == row["size_bytes"],
             f"source changed during manifest creation: {row['path']}")

    payload = {
        "schema": "ATTITUDE_CM18_A1_INPUT_MANIFEST_V1",
        "scope": {"splits": ["TRAIN", "VAL"], "train_scenes": 768, "val_scenes": 48,
                  "test_accessed": False, "raw_numeric_arrays_read": False,
                  "h5_numeric_arrays_read": False, "raw_files_copied": False},
        "raw_lineage_note": "Old B behavior-trajectory inputs; reference source hashes do not assert recovery of the original B producer source.",
        "new_sources": [x for x in sources if x["role"] == "new_preparation_source"],
        "reference_sources": [x for x in sources if x["role"] != "new_preparation_source"],
        "scenes": scenes,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(OUT.suffix + ".tmp")
    with tmp.open("x", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.rename(tmp, OUT)
    print(f"Wrote {OUT.relative_to(ROOT)}: 768 TRAIN + 48 VAL; no TEST or numeric arrays read")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
