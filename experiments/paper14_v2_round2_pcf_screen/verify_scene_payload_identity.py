"""Read-only verification of the twelve frozen VAL ON/B scene payload pairs."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import sys

import h5py
import numpy as np


HERE = Path(__file__).resolve().parent
LOCK_PATH = HERE / "frozen_inputs.json"
PHYSICAL_FIELDS = (
    "arms/command",
    "arms/rhoDot_hat",
    "arms/rhoDot_true",
    "arms/rho_hat",
    "arms/rho_true",
    "environment_wind_I",
    "initial_state",
    "reference/acceleration",
    "reference/position",
    "reference/velocity",
    "reference/yaw",
    "reference/yaw_acceleration",
    "reference/yaw_rate",
    "time",
)
EXPECTED_SHAPES = {
    "arms/command": (4, 20001),
    "arms/rhoDot_hat": (4, 20001),
    "arms/rhoDot_true": (4, 20001),
    "arms/rho_hat": (4, 20001),
    "arms/rho_true": (4, 20001),
    "environment_wind_I": (3, 20001),
    "initial_state": (1, 12),
    "reference/acceleration": (3, 20001),
    "reference/position": (3, 20001),
    "reference/velocity": (3, 20001),
    "reference/yaw": (1, 20001),
    "reference/yaw_acceleration": (1, 20001),
    "reference/yaw_rate": (1, 20001),
    "time": (1, 20001),
}
EXPECTED_IDS = (
    "DL1018_VAL_T2_C00_W10",
    "DL1018_VAL_T2_C02_W12",
    "DL1018_VAL_T2_C05_W15",
    "DL1018_VAL_T2_C06_W00",
    "DL1018_VAL_T1_C02_W09",
    "DL1018_VAL_T1_C05_W12",
    "DL1018_VAL_T1_C08_W15",
    "DL1018_VAL_T1_C00_W07",
    "DL1018_VAL_T3_C12_W09",
    "DL1018_VAL_T3_C00_W13",
    "DL1018_VAL_T3_C02_W15",
    "DL1018_VAL_T3_C03_W00",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_file_identity(path: Path) -> tuple[str, int, int]:
    before = path.stat()
    digest = sha256(path)
    after = path.stat()
    before_id = (before.st_size, before.st_mtime_ns)
    after_id = (after.st_size, after.st_mtime_ns)
    if before_id != after_id:
        raise RuntimeError(f"File changed during SHA read: {path}")
    return digest, before.st_size, before.st_mtime_ns


def scene_leaf_paths(group: h5py.Group) -> set[str]:
    paths: set[str] = set()

    def collect(name: str, obj: h5py.Dataset | h5py.Group) -> None:
        if isinstance(obj, h5py.Dataset):
            paths.add(name)

    group.visititems(collect)
    return paths


def load_physical_payload(path: Path) -> tuple[dict[str, np.ndarray], int]:
    with h5py.File(path, "r") as mat:
        if "scene" not in mat or not isinstance(mat["scene"], h5py.Group):
            raise RuntimeError(f"Missing scene group in {path}")
        group = mat["scene"]
        paths = scene_leaf_paths(group)
        expected_paths = set(PHYSICAL_FIELDS) | {"scene_id"}
        if paths != expected_paths:
            raise RuntimeError(f"Unexpected scene dataset paths in {path}: {sorted(paths)}")
        payload: dict[str, np.ndarray] = {}
        for field in PHYSICAL_FIELDS:
            source = np.asarray(group[field][()])
            if source.dtype.kind != "f" or source.dtype.itemsize != 8:
                raise RuntimeError(f"Expected float64 physical field {field} in {path}: {source.dtype}")
            if source.shape != EXPECTED_SHAPES[field] or not np.isfinite(source).all():
                raise RuntimeError(f"Unexpected shape or nonfinite values for {field} in {path}: {source.shape}")
            payload[field] = np.asarray(source, dtype="<f8", order="C")
        time = payload["time"].reshape(-1)
        if time.size != 20001 or abs(float(time[0])) > 1e-12 or abs(float(time[-1]) - 20.0) > 1e-12:
            raise RuntimeError(f"Scene time does not cover 0..20 s at 1 kHz in {path}")
        return payload, len(paths)


def payload_sha256(payload: dict[str, np.ndarray]) -> str:
    digest = hashlib.sha256()
    for field in sorted(PHYSICAL_FIELDS):
        array = payload[field]
        shape = ",".join(str(dimension) for dimension in array.shape)
        digest.update(field.encode("utf-8") + b"\0")
        digest.update(shape.encode("ascii") + b"\0")
        digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def main() -> int:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8-sig"))
    expected_scene_path = Path(lock["scene_list"]["path"])
    manifest_path = Path(lock["reuse_manifest"]["path"])
    evidence_path = Path(lock["scene_payload_identity"]["path"])
    for label, path, expected in (
        ("scene list", expected_scene_path, lock["scene_list"]["sha256"]),
        ("reuse manifest", manifest_path, lock["reuse_manifest"]["sha256"]),
        ("scene payload evidence", evidence_path, lock["scene_payload_identity"]["sha256"]),
    ):
        actual, _, _ = stable_file_identity(path)
        if actual.lower() != expected.lower():
            raise RuntimeError(f"Locked {label} SHA mismatch: {path}")

    scene_rows = read_csv(expected_scene_path)
    if tuple(row["scene_id"] for row in scene_rows) != EXPECTED_IDS:
        raise RuntimeError("Frozen scene list does not match the exact twelve VAL IDs/order")
    raw_rows = read_csv(manifest_path)
    if len(raw_rows) != 24 or any(row.get("split") != "VAL" for row in raw_rows):
        raise RuntimeError("Reuse manifest must contain exactly 24 VAL raw files")
    evidence_rows = {row["scene_id"]: row for row in read_csv(evidence_path)}
    if len(evidence_rows) != 12 or set(evidence_rows) != set(EXPECTED_IDS):
        raise RuntimeError("Scene payload evidence must contain exactly twelve unique rows")

    manifest: dict[tuple[str, str], dict[str, str]] = {}
    for row in raw_rows:
        key = (row["scene_id"], row["role"])
        if row["scene_id"] not in EXPECTED_IDS or row["role"] not in ("ON_CANDIDATE", "B_BASELINE"):
            raise RuntimeError(f"Unexpected scene or role in reuse manifest: {key}")
        if key in manifest:
            raise RuntimeError(f"Duplicate raw manifest entry: {key}")
        manifest[key] = row
    if len(manifest) != 24:
        raise RuntimeError("Reuse manifest does not have one ON and one B raw for each scene")

    for scene_id in EXPECTED_IDS:
        proof = evidence_rows[scene_id]
        if (proof["status"] != "IDENTICAL" or int(proof["physical_field_count"]) != 14 or
                int(proof["time_samples"]) != 20001 or
                float(proof["max_abs_physical_scene_diff"]) != 0.0):
            raise RuntimeError(f"Frozen scene evidence row is not an exact 14-field identity: {scene_id}")
        pair_payloads: dict[str, dict[str, np.ndarray]] = {}
        pair_digests: dict[str, str] = {}
        for role, evidence_hash_key in (
            ("ON_CANDIDATE", "on_raw_sha256"),
            ("B_BASELINE", "b_raw_sha256"),
        ):
            row = manifest[(scene_id, role)]
            path = Path(row["raw_path"])
            expected_raw_sha = row["raw_sha256"].lower()
            if proof[evidence_hash_key].lower() != expected_raw_sha:
                raise RuntimeError(f"Scene evidence raw hash binding differs: {scene_id} {role}")
            before = stable_file_identity(path)
            if before[0].lower() != expected_raw_sha:
                raise RuntimeError(f"Locked raw SHA mismatch: {scene_id} {role} {path}")
            payload, dataset_count = load_physical_payload(path)
            after = stable_file_identity(path)
            if before != after:
                raise RuntimeError(f"Raw identity changed during scene read: {scene_id} {role}")
            if dataset_count != 15:
                raise RuntimeError(f"Expected 14 physical arrays plus scene_id metadata: {scene_id} {role}")
            pair_payloads[role] = payload
            pair_digests[role] = payload_sha256(payload)

        on_payload = pair_payloads["ON_CANDIDATE"]
        b_payload = pair_payloads["B_BASELINE"]
        max_abs_diff = 0.0
        for field in PHYSICAL_FIELDS:
            on_array = on_payload[field]
            b_array = b_payload[field]
            if on_array.shape != b_array.shape or not np.array_equal(on_array, b_array):
                raise RuntimeError(f"Physical scene field differs: {scene_id} {field}")
            max_abs_diff = max(max_abs_diff, float(np.max(np.abs(on_array - b_array))))
        if pair_digests["ON_CANDIDATE"] != pair_digests["B_BASELINE"] or max_abs_diff != 0.0:
            raise RuntimeError(f"Canonical payload identity mismatch: {scene_id}")
        print(f"PASS {scene_id}: 14 fields, 20001 points, diff={max_abs_diff:.1f}, sha256={pair_digests['ON_CANDIDATE']}")

    print("READ_ONLY_SCENE_PAYLOAD_VERIFY PASS: 12/12 VAL pairs; 24 raw SHA/size/mtime stable; no files written.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # fail closed with a concise audit message
        print(f"READ_ONLY_SCENE_PAYLOAD_VERIFY FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
