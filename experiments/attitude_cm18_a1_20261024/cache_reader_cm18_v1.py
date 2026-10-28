"""Read and identity-check qualified TRAIN/VAL CM18 event-cache scenes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat


VARIABLES = (
    "X18",
    "target_raw",
    "event_time_s",
    "phase_code",
    "plant_index",
    "scene_id",
    "split",
    "input_identity",
    "export_meta",
)


def _matlab_text(value: Any) -> str:
    array = np.asarray(value)
    if array.dtype.kind in "US":
        return "".join(str(part) for part in array.reshape(-1)).strip()
    if array.dtype.kind in "ui":
        return "".join(chr(int(part)) for part in array.reshape(-1) if int(part)).strip()
    raise ValueError(f"expected MATLAB char array, got {array.dtype}")


def _mat_struct(value: Any, name: str) -> Any:
    array = np.asarray(value)
    if array.shape != (1, 1):
        raise ValueError(f"{name} must be a 1x1 MATLAB struct")
    result = array[0, 0]
    if not hasattr(result, "_fieldnames"):
        raise ValueError(f"{name} is not a MATLAB struct")
    return result


def _scalar_int(value: Any, name: str) -> int:
    array = np.asarray(value)
    if array.size != 1 or not np.issubdtype(array.dtype, np.number):
        raise ValueError(f"{name} must be a numeric scalar")
    number = float(array.reshape(-1)[0])
    if not np.isfinite(number) or number != int(number):
        raise ValueError(f"{name} must be a finite integer")
    return int(number)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_repo_path(repo_root: Path, relative_path: str) -> Path:
    root = repo_root.resolve(strict=True)
    path = (root / relative_path).resolve(strict=True)
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"cache path escapes repository root: {relative_path}") from exc
    return path


def _read_scene(repo_root: Path, row: dict[str, Any], input_manifest_sha256: str) -> dict[str, Any]:
    scene_id = row.get("scene_id")
    split = row.get("split")
    if not isinstance(scene_id, str) or split not in ("TRAIN", "VAL"):
        raise ValueError("manifest row must identify one TRAIN/VAL scene")
    if row.get("qualified") is not True or row.get("status") != "PASS":
        raise ValueError(f"unqualified cache row: {scene_id}")

    path = _safe_repo_path(repo_root, row["cache_path"])
    if path.stat().st_size != int(row["cache_bytes"]):
        raise ValueError(f"cache size mismatch: {scene_id}")
    if _sha256(path) != str(row["cache_sha256"]).lower():
        raise ValueError(f"cache SHA256 mismatch: {scene_id}")

    mat = loadmat(path, squeeze_me=False, struct_as_record=False, variable_names=VARIABLES)
    missing = set(VARIABLES) - set(mat)
    if missing:
        raise ValueError(f"{scene_id}: missing MAT variables {sorted(missing)}")
    x = np.asarray(mat["X18"])
    target = np.asarray(mat["target_raw"])
    event_time = np.asarray(mat["event_time_s"])
    phase = np.asarray(mat["phase_code"])
    plant_index = np.asarray(mat["plant_index"])
    n = 1999
    if x.shape != (n, 18) or x.dtype != np.float64:
        raise ValueError(f"{scene_id}: X18 must be float64 {(n, 18)}")
    if target.shape != (n, 3) or target.dtype != np.float64:
        raise ValueError(f"{scene_id}: target_raw must be float64 {(n, 3)}")
    if event_time.shape != (n, 1) or event_time.dtype != np.float64:
        raise ValueError(f"{scene_id}: event_time_s must be float64 {(n, 1)}")
    if phase.shape != (n, 1) or phase.dtype != np.uint8:
        raise ValueError(f"{scene_id}: phase_code must be uint8 {(n, 1)}")
    if plant_index.shape != (n, 1) or not np.issubdtype(plant_index.dtype, np.integer):
        raise ValueError(f"{scene_id}: plant_index must be an integer vector {(n, 1)}")
    if not all(np.isfinite(array).all() for array in (x, target, event_time)):
        raise ValueError(f"{scene_id}: cache contains non-finite numeric data")

    idx = plant_index.reshape(-1).astype(np.int64)
    expected_idx = np.arange(11, 20000, 10, dtype=np.int64)
    if not np.array_equal(idx, expected_idx):
        raise ValueError(f"{scene_id}: plant_index is not 11:10:19991")
    t = event_time.reshape(-1)
    if np.max(np.abs(t - (idx - 1) * 0.001)) > 1e-12 or np.any(np.diff(t) <= 0):
        raise ValueError(f"{scene_id}: event_time_s does not align with plant_index")
    phase_values = phase.reshape(-1)
    if np.any(phase_values > 5):
        raise ValueError(f"{scene_id}: phase_code must lie in 0..5")

    if _matlab_text(mat["scene_id"]) != scene_id or _matlab_text(mat["split"]) != split:
        raise ValueError(f"{scene_id}: embedded scene identity differs from manifest")
    identity = _mat_struct(mat["input_identity"], "input_identity")
    meta = _mat_struct(mat["export_meta"], "export_meta")
    if _matlab_text(identity.input_manifest_sha256) != input_manifest_sha256:
        raise ValueError(f"{scene_id}: input manifest identity mismatch")
    if _matlab_text(meta.scene_id) != scene_id or _matlab_text(meta.split) != split:
        raise ValueError(f"{scene_id}: export_meta identity mismatch")
    if _matlab_text(meta.status) != "PASS" or _scalar_int(meta.qualified, "qualified") != 1:
        raise ValueError(f"{scene_id}: export_meta is not qualified")
    if _scalar_int(meta.event_count, "event_count") != n:
        raise ValueError(f"{scene_id}: export_meta event_count mismatch")

    input_sha = row.get("input_sha256")
    for key, field in (
        ("event_h5", "event_h5_sha256"),
        ("raw_run", "raw_run_sha256"),
        ("run_start", "run_start_sha256"),
    ):
        if _matlab_text(getattr(identity, field)) != input_sha.get(key):
            raise ValueError(f"{scene_id}: {field} differs from dataset manifest")

    return {
        "scene_id": scene_id,
        "split": split,
        "X18": x,
        "target_raw": target,
        "event_time_s": event_time,
        "phase_code": phase,
        "plant_index": plant_index,
    }


def load_qualified_split(
    repo_root: Path,
    manifest_relative_path: str,
    split: str,
    expected_manifest_sha256: str,
) -> list[dict[str, Any]]:
    """Load one pinned, fully-qualified TRAIN or VAL split without scaling it."""
    if split not in ("TRAIN", "VAL"):
        raise ValueError("only TRAIN and VAL are permitted")
    manifest_path = _safe_repo_path(repo_root, manifest_relative_path)
    if _sha256(manifest_path) != expected_manifest_sha256.lower():
        raise ValueError("dataset manifest SHA256 mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "CM18_A1_DATASET_MANIFEST_V1":
        raise ValueError("unexpected dataset manifest schema")
    if manifest.get("mode") not in ("SCREEN4", "ALL816"):
        raise ValueError("unexpected dataset manifest mode")
    if manifest.get("TEST_accessed") is not False:
        raise ValueError("dataset manifest does not certify TEST isolation")
    rows = manifest.get("rows")
    if not isinstance(rows, list) or len(rows) != int(manifest.get("scene_count", -1)):
        raise ValueError("dataset manifest row count mismatch")
    if int(manifest.get("qualified_count", -1)) != len(rows) or int(manifest.get("failed_count", -1)) != 0:
        raise ValueError("dataset manifest contains unqualified rows")
    scene_ids = [row.get("scene_id") for row in rows]
    if len(set(scene_ids)) != len(rows):
        raise ValueError("duplicate scene_id in dataset manifest")
    selected = [row for row in rows if row.get("split") == split]
    if not selected:
        raise ValueError(f"manifest has no {split} scenes")
    input_manifest_sha256 = str(manifest["input_manifest_sha256"]).lower()
    return [_read_scene(Path(repo_root), row, input_manifest_sha256) for row in selected]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--manifest", required=True, help="repository-relative manifest path")
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--split", choices=("TRAIN", "VAL"), required=True)
    args = parser.parse_args()
    scenes = load_qualified_split(args.repo_root, args.manifest, args.split, args.manifest_sha256)
    print(json.dumps({
        "schema": "CM18_CACHE_READER_RESULT_V1",
        "status": "PASS",
        "split": args.split,
        "scene_count": len(scenes),
        "event_count": sum(len(scene["X18"]) for scene in scenes),
        "scenes": [scene["scene_id"] for scene in scenes],
        "training_or_optimizer_calls": 0,
    }, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
