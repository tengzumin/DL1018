"""Build a read-only NumPy reference fixture for the frozen A1R MATLAB forward."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat

SCENE_ID = "DL1018_VAL_T2_C04_W14"
EVENT_INDICES = (0, 500, 1000, 1500, 1998)
DEPLOYMENT = "experiments/attitude_cm18_datarepair_20261024/postselection_a1r_v1/deployment_parameters_v1.json"
DEPLOYMENT_SHA = "b3ab7a3d99df639d4cc0a10ec2b6fcd4622388f58c90c25424e472164ef38d23"
NUMPY_MODEL = "experiments/attitude_cm18_a1_20261024/model_cm18_v1.py"
NUMPY_MODEL_SHA = "ad32c4f97bf96c63172547c944d80c45062502f1062b774934e0f7a868720cf6"
FORWARD = "experiments/attitude_cm18_a1_20261024/matlab/cm18_a1_forward_v1.m"
FORWARD_SHA = "1ff450f9be6a5c16fe98cb4f169ef9930f1b806fecfc10ad664c11ce940f42e9"
B_MANIFEST = "reports/attitude_cm18_datarepair_20261024/repaired_all816_v1/DATASET_MANIFEST_v1.json"
B_MANIFEST_SHA = "3f51a1cd0e2e8c3eae79a16df363f2f8d47b0d5dbd876ecd95f1571d9e70a5e0"
C5_MANIFEST = "reports/attitude_cm18_datarepair_20261024/c5_val48_c5_teacher_v3/C5_VAL48_EVENT_CACHE_MANIFEST_v3.json"
C5_MANIFEST_SHA = "3e72f4726219cfd0e89476c70d24796a06c8f8447d4064cfdc471433a863a501"
OUTPUT = "experiments/attitude_cm18_datarepair_20261024/a1r_screen12_control_v1/artifacts/a1r_forward_parity_fixture_v1.json"
TOLERANCE = 2e-12


def sha256(path: Path) -> str:
    import hashlib
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def repo_file(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"path escapes repository: {relative}")
    return path


def verify_file(root: Path, relative: str, expected_sha: str) -> Path:
    path = repo_file(root, relative)
    if not path.is_file() or sha256(path) != expected_sha:
        raise ValueError(f"missing or changed pinned input: {relative}")
    return path


def mat_text(value: Any) -> str:
    array = np.asarray(value)
    if array.dtype.kind in "US":
        return "".join(str(part) for part in array.reshape(-1)).strip()
    if array.dtype.kind in "ui":
        return "".join(chr(int(part)) for part in array.reshape(-1) if int(part)).strip()
    raise ValueError(f"expected MATLAB text array, got {array.dtype}")


def load_b(root: Path) -> tuple[np.ndarray, dict[str, Any]]:
    manifest = read_json(verify_file(root, B_MANIFEST, B_MANIFEST_SHA))
    if (manifest.get("schema") != "CM18_B_REF_REPAIRED_ALL816_DATASET_MANIFEST_V1"
            or manifest.get("status") != "PASS" or manifest.get("training_eligible") is not True):
        raise ValueError("fixed B manifest is not eligible PASS")
    rows = [row for row in manifest.get("rows", []) if row.get("scene_id") == SCENE_ID]
    if (len(rows) != 1 or rows[0].get("split") != "VAL" or rows[0].get("status") != "PASS"
            or rows[0].get("qualified") is not True
            or rows[0].get("cache_schema") != "CM18_REPAIRED_EVENT_CACHE_V1"):
        raise ValueError("fixed B parity row is not a qualified VAL cache")
    row = rows[0]
    path = verify_file(root, str(row["cache_path"]), str(row["cache_sha256"]).lower())
    if path.stat().st_size != int(row["cache_bytes"]):
        raise ValueError("fixed B cache byte count mismatch")
    mat = loadmat(path, squeeze_me=False, struct_as_record=False,
                  variable_names=("X18", "scene_id", "split", "cache_schema"))
    if (mat_text(mat["scene_id"]) != SCENE_ID or mat_text(mat["split"]) != "VAL"
            or mat_text(mat["cache_schema"]) != "CM18_REPAIRED_EVENT_CACHE_V1"):
        raise ValueError("fixed B cache identity mismatch")
    x = np.asarray(mat["X18"], dtype=np.float64)
    if x.shape != (1999, 18) or not np.isfinite(x).all():
        raise ValueError("fixed B X18 shape/finite check failed")
    return x, {"manifest_path": B_MANIFEST, "manifest_sha256": B_MANIFEST_SHA,
               "cache_path": row["cache_path"], "cache_sha256": row["cache_sha256"],
               "cache_bytes": int(row["cache_bytes"]), "scene_id": SCENE_ID, "split": "VAL"}


def load_c5(root: Path) -> tuple[np.ndarray, dict[str, Any]]:
    manifest = read_json(verify_file(root, C5_MANIFEST, C5_MANIFEST_SHA))
    rows = [row for row in manifest.get("scenes", []) if row.get("scene_id") == SCENE_ID]
    if (manifest.get("schema") != "C5_MATCHED_VAL48_EVENT_CACHE_MANIFEST_V3"
            or manifest.get("status") != "PASS" or manifest.get("training_eligible") is not False
            or len(rows) != 1 or rows[0].get("status") != "PASS"
            or rows[0].get("cache_available") is not True):
        raise ValueError("fixed C5 cache is absent or not diagnostic-only PASS")
    row = rows[0]
    path = verify_file(root, str(row["cache_path_relative"]), str(row["cache_sha256"]).lower())
    if path.stat().st_size != int(row["cache_bytes"]):
        raise ValueError("fixed C5 cache byte count mismatch")
    cache = loadmat(path, simplify_cells=True, variable_names=("cache",)).get("cache")
    if not isinstance(cache, dict) or cache.get("schema") != "CM18_VAL_C5_EVENT_CACHE_V2":
        raise ValueError("unexpected fixed C5 cache schema")
    identity, events = cache.get("identity", {}), cache.get("events", {})
    if identity.get("scene_id") != SCENE_ID or identity.get("training_eligible") not in (False, 0):
        raise ValueError("fixed C5 cache identity mismatch")
    x = np.asarray(events.get("X18"), dtype=np.float64)
    if x.shape != (1999, 18) or not np.isfinite(x).all():
        raise ValueError("fixed C5 X18 shape/finite check failed")
    return x, {"manifest_path": C5_MANIFEST, "manifest_sha256": C5_MANIFEST_SHA,
               "cache_path": row["cache_path_relative"], "cache_sha256": row["cache_sha256"],
               "cache_bytes": int(row["cache_bytes"]), "scene_id": SCENE_ID, "split": "VAL",
               "training_eligible": False}


def main() -> None:
    os.environ.update(MKL_THREADING_LAYER="SEQUENTIAL", OMP_NUM_THREADS="1",
                      MKL_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1")
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--output", default=OUTPUT)
    args = parser.parse_args()
    root = args.repo_root.resolve()
    deployment_path = verify_file(root, DEPLOYMENT, DEPLOYMENT_SHA)
    forward_path = verify_file(root, FORWARD, FORWARD_SHA)
    numpy_path = verify_file(root, NUMPY_MODEL, NUMPY_MODEL_SHA)
    deployment = read_json(deployment_path)
    identity = deployment.get("identity", {})
    if (deployment.get("schema") != "CM18_A1R_DEPLOYMENT_PARAMETERS_V1"
            or identity.get("selected_step") != 40000
            or identity.get("checkpoint_sha256") != "5fa4308b6220e530e6c2e7a6f45c4b6e22ddddef80d1bc5cafdcf58564bc5ef3"
            or identity.get("normalizer_float64_sha256") != "faf8748f640c944c745406247ab8486825966abd763088ad1f4e0cde626ad14c"):
        raise ValueError("A1R deployment identity mismatch")
    spec = importlib.util.spec_from_file_location("cm18_a1r_numpy_reference", numpy_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot import pinned NumPy forward helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    b_x, b_identity = load_b(root)
    c5_x, c5_identity = load_c5(root)
    selected = np.asarray(EVENT_INDICES, dtype=np.int64)
    for label, matrix in (("B", b_x), ("C5", c5_x)):
        if not np.any(np.any(matrix[selected, 7:15] != 0.0, axis=1)):
            raise ValueError(f"{label} selected cache has no nonzero morphology basis")

    cases_meta: list[dict[str, Any]] = []
    x_rows: list[np.ndarray] = []
    for source, matrix, identity_row in (("B", b_x, b_identity), ("C5", c5_x, c5_identity)):
        for index in EVENT_INDICES:
            x_rows.append(matrix[index].copy())
            cases_meta.append({"name": f"{source}_{SCENE_ID}_{index}", "source_group": source,
                               "scene_id": SCENE_ID, "event_index_zero_based": index,
                               "synthetic_zero_basis": False, "cache_path": identity_row["cache_path"],
                               "cache_sha256": identity_row["cache_sha256"],
                               "derived_from_cache_path": None, "derived_from_cache_sha256": None})
    zero_features = b_x[0].copy()
    zero_features[7:15] = 0.0
    if np.any(zero_features[7:15] != 0.0):
        raise AssertionError("synthetic zero-basis construction failed")
    x_rows.append(zero_features)
    cases_meta.append({"name": f"SYNTHETIC_ZERO_BASIS_{SCENE_ID}", "source_group": "SYNTHETIC",
                       "scene_id": SCENE_ID, "event_index_zero_based": 0,
                       "synthetic_zero_basis": True, "cache_path": None, "cache_sha256": None,
                       "derived_from_cache_path": b_identity["cache_path"],
                       "derived_from_cache_sha256": b_identity["cache_sha256"]})
    x_check = np.asarray(x_rows, dtype=np.float64)
    if x_check.shape != (11, 18) or not np.isfinite(x_check).all():
        raise ValueError("fixed parity rows must be finite with shape 11x18")
    nonzero_basis_rows = int(np.count_nonzero(np.any(x_check[:10, 7:15] != 0.0, axis=1)))
    if nonzero_basis_rows != 2:
        raise ValueError(f"expected one nonzero selected basis row per source group, got {nonzero_basis_rows}")

    parameters = {name: np.asarray(value, dtype=np.float64)
                  for name, value in deployment["parameters"].items()}
    expected = module.forward(x_check, parameters)
    zero = len(x_check) - 1
    if (not np.array_equal(expected["basis_8"][zero], np.zeros(8))
            or not np.array_equal(expected["physical_output_rad_s2"][zero], np.zeros(3))):
        raise ValueError("zero-basis output must be exactly zero")
    cases = []
    for ix, meta in enumerate(cases_meta):
        cases.append({**meta, "raw_features_18": x_check[ix].tolist(),
                      "expected": {key: np.asarray(expected[key][ix], dtype=np.float64).tolist()
                                   for key in ("coefficients_3x8", "basis_8", "normalized_output",
                                               "physical_output_rad_s2")}})
    builder_path = Path(__file__).resolve()
    fixture = {"schema": "CM18_A1R_SCREEN12_FORWARD_PARITY_FIXTURE_V1",
               "status": "NUMPY_REFERENCE_PASS_MATLAB_PARITY_PENDING",
               "tolerance_abs": TOLERANCE, "case_count": len(cases), "cases": cases,
               "identity": {"deployment_parameters_path": DEPLOYMENT,
                            "deployment_parameters_sha256": DEPLOYMENT_SHA,
                            "checkpoint_sha256": identity["checkpoint_sha256"], "selected_step": 40000,
                            "normalizer_float64_sha256": identity["normalizer_float64_sha256"],
                            "numpy_model_path": NUMPY_MODEL, "numpy_model_sha256": sha256(numpy_path),
                            "matlab_forward_path": FORWARD, "matlab_forward_sha256": sha256(forward_path),
                            "fixture_builder_path": builder_path.relative_to(root).as_posix(),
                            "fixture_builder_sha256": sha256(builder_path), "B_cache": b_identity,
                            "C5_cache": c5_identity, "indices_zero_based": list(EVENT_INDICES),
                            "nonzero_basis_real_rows": nonzero_basis_rows,
                            "used_for_training_or_selection": False}}
    output = repo_file(root, args.output)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    marker = output.parent / "DO_NOT_GIT_UPLOAD.txt"
    if not marker.exists():
        marker.write_text("A1R parity fixture; do not upload to Git.\n", encoding="utf-8")
    ignore = output.parent / ".gitignore"
    if not ignore.exists():
        ignore.write_text("*\n!.gitignore\n!DO_NOT_GIT_UPLOAD.txt\n", encoding="utf-8")
    temp = output.with_suffix(output.suffix + ".tmp")
    temp.write_text(json.dumps(fixture, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    temp.replace(output)
    print(json.dumps({"status": fixture["status"], "case_count": len(cases),
                      "nonzero_basis_real_rows": nonzero_basis_rows,
                      "deployment_sha256": DEPLOYMENT_SHA, "fixture_sha256": sha256(output),
                      "output": output.relative_to(root).as_posix()}, sort_keys=True))


if __name__ == "__main__":
    main()
