from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import h5py


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
LOCK = ROOT / "experiments/position_prior_calibration_c1_20261022_v9/C1_SOURCE_LOCK_v2.json"
RELEASE = ROOT / "experiments/position_prior_calibration_c1_20261022_v9/C1_RELEASE_v9.json"
RUNS = ROOT / "experiments/position_prior_calibration_c1_20261022_v9/reports/C1_SCREEN_PER_RUN.csv"
SCENES = ROOT / "reports/paper14_v2/phase1/ROUND_SCREEN_12_SCENES.csv"

EXPECTED = {
    LOCK: "02668f6268944715e65e6d2cffa52b395417506132212b00e7d273d88df164e5",
    RELEASE: "7aa072835b0e633f9e40d0e471a17870735d32ddf079eafc61ac6790ea7974d0",
    RUNS: "43aab1c0fa906dfa5e3d7f175339a5607bd4ec2e2cc55687741524d34fa08bac",
    SCENES: "176ed5770824a241b5c41b9c786f2110b730a7783414152875181985d497a32e",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def describe_dataset(path: str, obj: h5py.Dataset) -> dict:
    return {
        "path": path,
        "shape": list(obj.shape),
        "dtype": str(obj.dtype),
        "chunks": list(obj.chunks) if obj.chunks else None,
    }


def main() -> None:
    identity = {}
    for path, expected in EXPECTED.items():
        actual = sha256(path)
        if actual != expected:
            raise SystemExit(f"frozen input SHA mismatch: {path}: {actual} != {expected}")
        st = path.stat()
        identity[str(path)] = {"sha256": actual, "size": st.st_size, "mtime_ns": st.st_mtime_ns}

    with RUNS.open(newline="", encoding="utf-8-sig") as stream:
        rows = [r for r in csv.DictReader(stream) if r["condition"] == "ON1"]
    if len(rows) != 12 or len({r["scene_id"] for r in rows}) != 12:
        raise SystemExit(f"expected 12 unique ON1 rows, got {len(rows)}")
    row = rows[0]
    raw = Path(row["raw_path"])
    raw_before = {"sha256": sha256(raw), "size": raw.stat().st_size, "mtime_ns": raw.stat().st_mtime_ns}
    if raw_before["sha256"] != row["raw_sha256"]:
        raise SystemExit("first ON1 raw SHA mismatch against C1 per-run record")

    wanted = ("position", "force", "attitude", "euler", "event", "pcf", "beta", "phi", "weight", "state", "reference", "time", "wind", "generalized", "command", "eta", "acceleration", "actual", "filtered", "scene_id", "mass", "gravity", "impulse", "disturbance", "perturb")
    with h5py.File(raw, "r") as h5:
        root_keys = sorted(h5.keys())
        top = {}
        for key in root_keys:
            obj = h5[key]
            top[key] = {
                "kind": "group" if isinstance(obj, h5py.Group) else "dataset",
                "shape": list(obj.shape) if isinstance(obj, h5py.Dataset) else None,
                "dtype": str(obj.dtype) if isinstance(obj, h5py.Dataset) else None,
                "keys": sorted(obj.keys())[:80] if isinstance(obj, h5py.Group) else None,
            }
        matches = []
        for root_key in root_keys:
            obj = h5[root_key]
            if isinstance(obj, h5py.Group):
                for name in obj.keys():
                    if any(token in name.lower() for token in wanted):
                        child = obj[name]
                        if isinstance(child, h5py.Dataset):
                            matches.append(describe_dataset(f"{root_key}/{name}", child))
                        else:
                            matches.append({"path": f"{root_key}/{name}", "kind": "group", "keys": sorted(child.keys())[:40]})
    raw_after = {"sha256": sha256(raw), "size": raw.stat().st_size, "mtime_ns": raw.stat().st_mtime_ns}
    if raw_before != raw_after:
        raise SystemExit(f"raw changed during read: before={raw_before}, after={raw_after}")

    result = {
        "status": "SCHEMA_INSPECTED",
        "frozen_inputs": identity,
        "on1_count": len(rows),
        "on1_rows": [{k: r[k] for k in ("scene_id", "task", "wind_band", "raw_path", "raw_sha256", "run_start_sha256", "run_status_sha256")} for r in rows],
        "inspection_sample": {"scene_id": row["scene_id"], "raw": str(raw), "before": raw_before, "after": raw_after},
        "root": {"keys": root_keys, "top": top},
        "target_related_datasets": matches,
    }
    path = OUT / "FIRST_RAW_SCHEMA.json"
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"status": result["status"], "on1_count": len(rows), "sample": result["inspection_sample"], "root": result["root"], "target_related_datasets": matches}, indent=2))


if __name__ == "__main__":
    main()
