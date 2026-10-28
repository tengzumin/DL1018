"""Export a frozen A1T checkpoint and prepare a small NumPy/Torch/MATLAB parity fixture.

This runs only after ROOT releases a COMPLETED 60,000-step receipt. It does not
train, access TEST, evaluate labels, or call MATLAB/Plant.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

RUN = "experiments/attitude_cm18_datarepair_20261024/training_a1t_v1"
TRAINER = "experiments/attitude_cm18_datarepair_20261024/train_cm18_a1t_v1.py"
TASKBOOK = "reports/attitude_cm18_datarepair_20261024/A1T_TRAINING_TASKBOOK_v1_ZH.md"
TASKBOOK_SHA = "2fe158fd370019bfe9e3d95e6b3222e1f4d7829cfa1681bd8dd85d06615102e9"
READER = "experiments/attitude_cm18_datarepair_20261024/read_cstar_split_v1.py"
READER_SHA = "ced4251719f986d762f29ccced04fb80208a28e7aed1e2fe12d3b504955a4096"
NUMPY_MODEL = "experiments/attitude_cm18_a1_20261024/model_cm18_v1.py"
NUMPY_MODEL_SHA = "ad32c4f97bf96c63172547c944d80c45062502f1062b774934e0f7a868720cf6"
TORCH_MODEL = "experiments/attitude_cm18_a1_20261024/torch_model_cm18_v1.py"
TORCH_MODEL_SHA = "bc9fe34fe957cb624438eeccfdfe2ddd38ad40cc9a4e706ce58863c9271d5aa0"
MATLAB_FORWARD = "experiments/attitude_cm18_a1_20261024/matlab/cm18_a1_forward_v1.m"
MATLAB_FORWARD_SHA = "1ff450f9be6a5c16fe98cb4f169ef9930f1b806fecfc10ad664c11ce940f42e9"
A1R_NORMALIZER = "experiments/attitude_cm18_datarepair_20261024/training_a1r_v1/normalizer.json"
A1R_NORMALIZER_SHA = "712627125bf48c3d07cc71de10b13efcb4560b7c31673a179b371cc91d1fe48c"
A1R_CANONICAL_NORMALIZER_SHA = "faf8748f640c944c745406247ab8486825966abd763088ad1f4e0cde626ad14c"
BASE_DATASET = "reports/attitude_cm18_datarepair_20261024/repaired_all816_v1/DATASET_MANIFEST_v1.json"
BASE_DATASET_SHA = "3f51a1cd0e2e8c3eae79a16df363f2f8d47b0d5dbd876ecd95f1571d9e70a5e0"
C5_MANIFEST = "reports/attitude_cm18_datarepair_20261024/c5_val48_c5_teacher_v3/C5_VAL48_EVENT_CACHE_MANIFEST_v3.json"
C5_MANIFEST_SHA = "3e72f4726219cfd0e89476c70d24796a06c8f8447d4064cfdc471433a863a501"
SCENE_ID = "DL1018_VAL_T2_C04_W14"
EVENT_INDICES_ZERO_BASED = (0, 500, 1000, 1500, 1998)
OUTPUT = "experiments/attitude_cm18_datarepair_20261024/postselection_a1t_v1"
EXPECTED_SOURCE_SHA = {
    TRAINER: "2a5ea2ba6d0ccba1e0bf30a7d84f8a07723144fb44a070a63ca7fd6d68ade88b",
    READER: READER_SHA,
    NUMPY_MODEL: NUMPY_MODEL_SHA,
    TORCH_MODEL: TORCH_MODEL_SHA,
}
PARAMS = {
    "W1": ("fc1.weight", (32, 18)), "b1": ("fc1.bias", (32,)),
    "W2": ("fc2.weight", (32, 32)), "b2": ("fc2.bias", (32,)),
    "W3": ("fc3.weight", (24, 32)), "b3": ("fc3.bias", (24,)),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def repo_file(root: Path, relative: str) -> Path:
    path = (root / relative).resolve(strict=True)
    path.relative_to(root.resolve(strict=True))
    if not path.is_file():
        raise ValueError(f"expected file: {relative}")
    return path


def read_json(path: Path) -> dict[str, Any]:
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise ValueError(f"expected JSON object: {path}")
    return result


def load_module(root: Path, relative: str, name: str) -> Any:
    path = repo_file(root, relative)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def validate_sources(root: Path, release: dict[str, Any], release_pin: dict[str, Any]) -> dict[str, str]:
    rows = release.get("source_files")
    expected_paths = set(EXPECTED_SOURCE_SHA)
    if not isinstance(rows, list) or len(rows) != len(expected_paths):
        raise ValueError("A1T ROOT release must pin exactly trainer, reader, NumPy and Torch sources")
    observed: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("malformed source_files row")
        relative, claimed = row.get("path"), row.get("sha256")
        if relative not in expected_paths or relative in observed:
            raise ValueError("unexpected or duplicate A1T source pin")
        actual = sha256(repo_file(root, relative))
        if actual != str(claimed).lower() or actual != EXPECTED_SOURCE_SHA[relative]:
            raise ValueError(f"A1T source identity mismatch: {relative}")
        observed[relative] = actual
    if set(observed) != expected_paths:
        raise ValueError("incomplete A1T source pin set")
    if release_pin.get("source_files") != observed:
        raise ValueError("terminal receipt source pins differ from ROOT release")
    return observed


def canonical_hash(arrays: tuple[Any, ...], np: Any) -> str:
    digest = hashlib.sha256()
    for value in arrays:
        array = np.ascontiguousarray(value, dtype=np.float64)
        digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def validate_terminal(root: Path, release_sha: str, receipt_sha: str, np: Any):
    run = root / RUN
    receipt_path = repo_file(root, f"{RUN}/run_receipt.json")
    if sha256(receipt_path) != receipt_sha.lower():
        raise ValueError("terminal A1T run receipt SHA mismatch")
    receipt = read_json(receipt_path)
    if (receipt.get("schema") != "CM18_A1T_TRAINING_RECEIPT_V1"
            or receipt.get("status") != "COMPLETED"
            or receipt.get("optimizer_steps_completed") != 60000
            or receipt.get("optimizer_step_calls_attempted") != 60000
            or receipt.get("run_directory") != RUN
            or receipt.get("candidate_frozen") is not True
            or receipt.get("B_VAL48_selects_checkpoint") is not True
            or receipt.get("C5_VAL48_used_for_training_or_selection") is not False
            or receipt.get("TEST_accessed") is not False):
        raise ValueError("A1T receipt is not a frozen completed 60,000-step run")
    release_pin = receipt.get("release")
    if not isinstance(release_pin, dict) or release_pin.get("release_sha256") != release_sha.lower():
        raise ValueError("terminal receipt release pin differs from command")
    release_abs = Path(str(release_pin.get("release_path", ""))).resolve(strict=True)
    release_abs.relative_to(root.resolve(strict=True))
    if sha256(release_abs) != release_sha.lower():
        raise ValueError("A1T ROOT release file SHA mismatch")
    release = read_json(release_abs)
    if (release.get("schema") != "CM18_A1T_TRAINING_RELEASE_V1"
            or release.get("decision") != "APPROVE_ONE_FORMAL_TRAINING"
            or release.get("seed") != 2026102001
            or release.get("optimizer_steps") != 60000
            or release.get("batch_size") != 512
            or release.get("device") != "cuda:0"
            or release.get("output_directory") != RUN):
        raise ValueError("ROOT A1T release identity differs from the frozen protocol")
    if release_pin.get("taskbook_sha256") != TASKBOOK_SHA:
        raise ValueError("terminal receipt taskbook pin mismatch")
    if sha256(repo_file(root, TASKBOOK)) != TASKBOOK_SHA:
        raise ValueError("A1T taskbook source changed")
    if release.get("taskbook", {}).get("path") != TASKBOOK or release.get("taskbook", {}).get("sha256") != TASKBOOK_SHA:
        raise ValueError("ROOT release taskbook pin mismatch")
    ds = release.get("dataset_manifest", {})
    ds_path, ds_sha = ds.get("path"), str(ds.get("sha256", "")).lower()
    if not isinstance(ds_path, str) or len(ds_sha) != 64 or sha256(repo_file(root, ds_path)) != ds_sha:
        raise ValueError("ROOT release C* dataset manifest identity mismatch")
    audit_pin = release.get("normalizer_audit", {})
    audit_path, audit_sha = audit_pin.get("path"), str(audit_pin.get("sha256", "")).lower()
    if not isinstance(audit_path, str) or len(audit_sha) != 64:
        raise ValueError("ROOT release normalizer audit pin missing")
    if release_pin.get("dataset_manifest_path") != ds_path or release_pin.get("dataset_manifest_sha256") != ds_sha:
        raise ValueError("receipt C* dataset identity differs from ROOT release")
    if release_pin.get("normalizer_audit_path") != audit_path or release_pin.get("normalizer_audit_sha256") != audit_sha:
        raise ValueError("receipt normalizer audit identity differs from ROOT release")
    validate_sources(root, release, release_pin)

    config_path = repo_file(root, f"{RUN}/training_config.json")
    config = read_json(config_path)
    if (config.get("schema") != "CM18_A1T_TRAINING_CONFIG_V1"
            or config.get("seed") != 2026102001 or config.get("optimizer_steps") != 60000
            or config.get("batch_size") != 512 or config.get("c5_val48_used_for_selection") is not False
            or config.get("release") != release_pin):
        raise ValueError("A1T training config differs from completed receipt/protocol")

    history = []
    with repo_file(root, f"{RUN}/val_metrics.jsonl").open("r", encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                raise ValueError("blank row in A1T validation history")
            history.append(json.loads(line))
    steps = list(range(0, 60001, 1000))
    if len(history) != 61 or [row.get("optimizer_step") for row in history] != steps:
        raise ValueError("A1T validation history must contain all 61 steps 0..60000")
    best_score = float("inf")
    best_step = None
    best_sha_at_selection = None
    for row in history:
        score = float(row.get("b_val_scene_weighted_normalized_score", float("nan")))
        if not np.isfinite(score):
            raise ValueError("nonfinite B VAL score in A1T history")
        improved = score < best_score
        if improved:
            best_score, best_step = score, row["optimizer_step"]
            best_sha_at_selection = row.get("best_checkpoint_sha256")
        if row.get("best_updated") is not improved or row.get("best_step") != best_step:
            raise ValueError("validation best-update ledger differs from strict-min/earliest-tie selection")
        if row.get("best_checkpoint_sha256") != best_sha_at_selection:
            raise ValueError("validation best checkpoint hash ledger mismatch")
        if abs(float(row.get("best_score", float("nan"))) - best_score) > 1e-12:
            raise ValueError("validation running best score ledger mismatch")
    if (best_step != receipt.get("best_step")
            or abs(best_score - float(receipt.get("best_score", float("nan")))) > 1e-12):
        raise ValueError("receipt best selection is not the strict minimum of all 61 VAL records")
    checkpoint_path = repo_file(root, f"{RUN}/best.pt")
    checkpoint_sha = sha256(checkpoint_path)
    if (checkpoint_sha != receipt.get("best_checkpoint_sha256")
            or best_sha_at_selection != checkpoint_sha):
        raise ValueError("selected A1T best checkpoint SHA differs from receipt/history")

    normalizer_path = repo_file(root, f"{RUN}/normalizer.json")
    normalizer_file_sha = sha256(normalizer_path)
    if config.get("normalizer_sha256") != normalizer_file_sha:
        raise ValueError("A1T config normalizer SHA mismatch")
    norm = read_json(normalizer_path)
    if (norm.get("schema") != "CM18_A1T_NORMALIZER_V1"
            or norm.get("fit_rows") != 307200 or norm.get("train_scenes") != 768
            or norm.get("sample_indices_per_scene_zero_based") != "0,5,...,1995 (400 rows)"
            or norm.get("a1r_normalizer_file_sha256") != A1R_NORMALIZER_SHA
            or norm.get("a1r_normalizer_canonical_sha256") != A1R_CANONICAL_NORMALIZER_SHA):
        raise ValueError("A1T normalizer metadata/A1R lineage mismatch")
    a1r_norm_path = repo_file(root, A1R_NORMALIZER)
    if sha256(a1r_norm_path) != A1R_NORMALIZER_SHA:
        raise ValueError("frozen A1R normalizer file SHA mismatch")
    a1r_norm = read_json(a1r_norm_path)
    mean = np.asarray(norm.get("input_mean_float64"), dtype=np.float64)
    std = np.asarray(norm.get("input_std_float64"), dtype=np.float64)
    rms = np.asarray(norm.get("train_axis_rms_rad_s2_float64"), dtype=np.float64)
    a1r_mean = np.asarray(a1r_norm.get("input_mean_float64"), dtype=np.float64)
    a1r_std = np.asarray(a1r_norm.get("input_std_float64"), dtype=np.float64)
    if (mean.shape != (18,) or std.shape != (18,) or rms.shape != (3,)
            or not np.isfinite(mean).all() or not np.isfinite(std).all() or not np.isfinite(rms).all()
            or np.any(std < 1e-6) or np.any(rms <= 0)
            or not np.array_equal(mean, a1r_mean) or not np.array_equal(std, a1r_std)):
        raise ValueError("A1T canonical normalizer is invalid or input mean/std differ from frozen A1R")
    normalizer_sha = canonical_hash((mean, std, rms), np)
    if normalizer_sha != norm.get("canonical_float64_sha256"):
        raise ValueError("A1T canonical float64 normalizer bytes differ from its record")
    if release_pin.get("normalizer_audit_sha256") != norm.get("normalizer_audit_sha256"):
        raise ValueError("A1T normalizer audit pin differs from receipt")
    audit_path_obj = repo_file(root, audit_path)
    if sha256(audit_path_obj) != audit_sha:
        raise ValueError("independent A1T normalizer audit SHA mismatch")
    audit = read_json(audit_path_obj)
    if (audit.get("schema") != "CM18_CSTAR_ALL816_INDEPENDENT_AUDIT_V1"
            or audit.get("status") != "PASS" or audit.get("scene_count") != 816
            or audit.get("split_counts") != {"TRAIN": 768, "VAL": 48}
            or audit.get("train_fit_rows") != 307200
            or audit.get("canonical_normalizer_sha256") != normalizer_sha
            or audit.get("label_manifest_sha256") != ds_sha):
        raise ValueError("independent A1T normalizer audit differs from final training artifacts")
    ckpt_sha = receipt["best_checkpoint_sha256"]
    import torch
    if torch.cuda.is_initialized():
        raise RuntimeError("postselection export must be CPU-only")
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    if (checkpoint.get("schema") != "CM18_A1T_CHECKPOINT_V1"
            or checkpoint.get("kind") != "best" or checkpoint.get("optimizer_step") != best_step):
        raise ValueError("A1T checkpoint schema/kind/selected step mismatch")
    state = checkpoint.get("state_dict")
    if not isinstance(state, dict):
        raise ValueError("A1T checkpoint state_dict missing")
    float32_buffers = {}
    for name, expected in (("input_mean", mean), ("input_std", std), ("train_axis_rms_rad_s2", rms)):
        actual = state[name].detach().cpu().numpy()
        if actual.dtype != np.float32 or not np.array_equal(actual, expected.astype(np.float32)):
            raise ValueError(f"A1T checkpoint float32 normalizer buffer mismatch: {name}")
        float32_buffers[name] = np.ascontiguousarray(actual)
    float32_buffer_sha = hashlib.sha256(b"".join(
        float32_buffers[name].tobytes(order="C")
        for name in ("input_mean", "input_std", "train_axis_rms_rad_s2")
    )).hexdigest()
    if float32_buffer_sha != norm.get("float32_buffer_sha256"):
        raise ValueError("A1T checkpoint float32 normalizer-buffer SHA mismatch")
    float32_rounding_max_abs = {
        name: float(np.max(np.abs(float32_buffers[name].astype(np.float64) - expected)))
        for name, expected in (("input_mean", mean), ("input_std", std), ("train_axis_rms_rad_s2", rms))
    }
    parameters: dict[str, Any] = {}
    for name, (tensor_name, shape) in PARAMS.items():
        value = state[tensor_name].detach().cpu().numpy()
        if value.dtype != np.float32 or value.shape != shape or not np.isfinite(value).all():
            raise ValueError(f"invalid A1T trained parameter: {tensor_name}")
        parameters[name] = value.astype(np.float64)
    parameters.update(input_mean=mean, input_std=std, train_axis_rms_rad_s2=rms)
    return {
        "receipt": receipt, "receipt_sha256": receipt_sha.lower(), "release": release,
        "release_pin": release_pin, "release_sha256": release_sha.lower(),
        "best_step": int(best_step), "best_score": best_score,
        "checkpoint": checkpoint, "checkpoint_sha256": ckpt_sha,
        "normalizer": norm, "normalizer_sha256": normalizer_sha,
        "normalizer_file_sha256": normalizer_file_sha,
        "float32_buffer_sha256": float32_buffer_sha,
        "float32_rounding_max_abs": float32_rounding_max_abs,
        "parameters": parameters,
    }


def mat_text(value: Any, np: Any) -> str:
    array = np.asarray(value)
    if array.dtype.kind in "US":
        return "".join(str(part) for part in array.reshape(-1)).strip()
    if array.dtype.kind in "ui":
        return "".join(chr(int(part)) for part in array.reshape(-1) if int(part)).strip()
    raise ValueError(f"expected MATLAB text array, got {array.dtype}")


def load_b_fixture(root: Path, np: Any) -> tuple[Any, dict[str, Any]]:
    from scipy.io import loadmat
    manifest_path = repo_file(root, BASE_DATASET)
    if sha256(manifest_path) != BASE_DATASET_SHA:
        raise ValueError("repaired B ALL816 manifest SHA mismatch")
    manifest = read_json(manifest_path)
    if (manifest.get("schema") != "CM18_B_REF_REPAIRED_ALL816_DATASET_MANIFEST_V1"
            or manifest.get("status") != "PASS" or manifest.get("training_eligible") is not True):
        raise ValueError("repaired B dataset manifest is not eligible PASS")
    rows = [row for row in manifest.get("rows", []) if row.get("scene_id") == SCENE_ID]
    if len(rows) != 1 or rows[0].get("split") != "VAL" or rows[0].get("status") != "PASS" or rows[0].get("qualified") is not True:
        raise ValueError("fixed B parity scene is not one qualified VAL row")
    row = rows[0]
    if row.get("cache_schema") != "CM18_REPAIRED_EVENT_CACHE_V1":
        raise ValueError("fixed B parity scene does not use the expected repaired cache")
    path = repo_file(root, row["cache_path"])
    if path.stat().st_size != int(row["cache_bytes"]) or sha256(path) != str(row["cache_sha256"]).lower():
        raise ValueError("fixed B parity cache size/SHA mismatch")
    mat = loadmat(path, squeeze_me=False, struct_as_record=False,
                  variable_names=("X18", "scene_id", "split", "cache_schema"))
    if (mat_text(mat["scene_id"], np) != SCENE_ID or mat_text(mat["split"], np) != "VAL"
            or mat_text(mat["cache_schema"], np) != "CM18_REPAIRED_EVENT_CACHE_V1"):
        raise ValueError("fixed B cache embedded scene/split/schema mismatch")
    x = np.asarray(mat["X18"], dtype=np.float64)
    if x.shape != (1999, 18) or not np.isfinite(x).all():
        raise ValueError("fixed B cache X18 shape/finite check failed")
    return x, {"manifest_path": BASE_DATASET, "manifest_sha256": BASE_DATASET_SHA,
                "cache_path": row["cache_path"], "cache_sha256": row["cache_sha256"],
                "cache_bytes": int(row["cache_bytes"]), "scene_id": SCENE_ID, "split": "VAL"}


def load_c5_fixture(root: Path, np: Any) -> tuple[Any, dict[str, Any]]:
    from scipy.io import loadmat
    manifest_path = repo_file(root, C5_MANIFEST)
    if sha256(manifest_path) != C5_MANIFEST_SHA:
        raise ValueError("C5 VAL48 manifest SHA mismatch")
    manifest = read_json(manifest_path)
    rows = [row for row in manifest.get("scenes", []) if row.get("scene_id") == SCENE_ID]
    if (manifest.get("schema") != "C5_MATCHED_VAL48_EVENT_CACHE_MANIFEST_V3"
            or manifest.get("status") != "PASS" or manifest.get("training_eligible") is not False
            or len(rows) != 1 or rows[0].get("status") != "PASS" or rows[0].get("cache_available") is not True):
        raise ValueError("fixed C5 fixture row is missing or not diagnostic-only PASS")
    row = rows[0]
    path = repo_file(root, row["cache_path_relative"])
    if path.stat().st_size != int(row["cache_bytes"]) or sha256(path) != str(row["cache_sha256"]).lower():
        raise ValueError("fixed C5 parity cache size/SHA mismatch")
    mat = loadmat(path, simplify_cells=True, variable_names=("cache",))
    cache = mat.get("cache")
    if not isinstance(cache, dict) or cache.get("schema") != "CM18_VAL_C5_EVENT_CACHE_V2":
        raise ValueError("unexpected fixed C5 cache schema")
    identity, events = cache.get("identity", {}), cache.get("events", {})
    if identity.get("scene_id") != SCENE_ID or identity.get("training_eligible") not in (False, 0):
        raise ValueError("C5 cache scene or diagnostic-only identity mismatch")
    x = np.asarray(events.get("X18"), dtype=np.float64)
    if x.shape != (1999, 18) or not np.isfinite(x).all():
        raise ValueError("fixed C5 cache X18 shape/finite check failed")
    return x, {"manifest_path": C5_MANIFEST, "manifest_sha256": C5_MANIFEST_SHA,
                "cache_path": row["cache_path_relative"], "cache_sha256": row["cache_sha256"],
                "cache_bytes": int(row["cache_bytes"]), "scene_id": SCENE_ID, "split": "VAL",
                "training_eligible": False}


def write_json_new(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def run(root: Path, release_sha: str, receipt_sha: str) -> Path:
    root = root.resolve(strict=True)
    output = root / OUTPUT
    if output.exists():
        raise FileExistsError(f"refusing to overwrite {OUTPUT}")
    if os.environ.get("KMP_DUPLICATE_LIB_OK"):
        raise RuntimeError("KMP_DUPLICATE_LIB_OK is forbidden")
    os.environ.update(MKL_THREADING_LAYER="SEQUENTIAL", OMP_NUM_THREADS="1",
                      MKL_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1")
    import numpy as np
    import torch
    torch.set_num_threads(1)
    if torch.cuda.is_initialized():
        raise RuntimeError("A1T postselection must remain CPU-only")
    if sha256(repo_file(root, MATLAB_FORWARD)) != MATLAB_FORWARD_SHA:
        raise ValueError("frozen pure MATLAB forward source SHA mismatch")
    trained = validate_terminal(root, release_sha, receipt_sha, np)
    numpy_model = load_module(root, NUMPY_MODEL, "a1t_postselect_numpy_model")
    torch_model = load_module(root, TORCH_MODEL, "a1t_postselect_torch_model")
    b_x, b_identity = load_b_fixture(root, np)
    c5_x, c5_identity = load_c5_fixture(root, np)
    selected = np.asarray(EVENT_INDICES_ZERO_BASED, dtype=np.int64)
    if (not np.any(np.any(b_x[selected, 7:15] != 0.0, axis=1))
            or not np.any(np.any(c5_x[selected, 7:15] != 0.0, axis=1))):
        raise ValueError("each fixed B/C5 fixture group must contain a nonzero morphology-basis row")
    x_rows = []
    cases_meta = []
    for source, matrix, identity in (("B", b_x, b_identity), ("C5", c5_x, c5_identity)):
        for index in EVENT_INDICES_ZERO_BASED:
            x_rows.append(matrix[index].copy())
            cases_meta.append({"name": f"{source}_{SCENE_ID}_zero_based_{index}",
                               "source_group": source, "scene_id": SCENE_ID,
                               "event_index_zero_based": index, "synthetic_zero_basis": False,
                               "cache_path": identity["cache_path"], "cache_sha256": identity["cache_sha256"]})
    zero_features = b_x[0].copy()
    zero_features[7:15] = 0.0
    if np.any(zero_features[7:15] != 0.0):
        raise AssertionError("synthetic zero-basis feature construction failed")
    x_rows.append(zero_features)
    cases_meta.append({"name": f"SYNTHETIC_ZERO_BASIS_FROM_B_{SCENE_ID}_zero_based_0",
                       "source_group": "SYNTHETIC", "scene_id": SCENE_ID,
                       "event_index_zero_based": 0, "synthetic_zero_basis": True,
                       "derived_from_cache_path": b_identity["cache_path"],
                       "derived_from_cache_sha256": b_identity["cache_sha256"]})
    xcheck = np.asarray(x_rows, dtype=np.float64)
    if xcheck.shape != (11, 18) or not np.isfinite(xcheck).all():
        raise ValueError("fixed 11-row parity input shape/finite check failed")
    p = trained["parameters"]
    expected = numpy_model.forward(xcheck, p)
    model = torch_model.TorchCM18A1(p["input_mean"], p["input_std"], p["train_axis_rms_rad_s2"])
    model.load_numpy_parameters(p)
    model.eval()
    with torch.inference_mode():
        actual_torch = model(torch.as_tensor(xcheck, dtype=torch.float64, device="cpu"))
    comparisons = {}
    for key in ("coefficients_3x8", "basis_8", "normalized_output", "physical_output_rad_s2"):
        left = np.asarray(expected[key], dtype=np.float64)
        right = actual_torch[key].detach().cpu().numpy().astype(np.float64, copy=False)
        if left.shape != right.shape or not np.isfinite(left).all() or not np.isfinite(right).all():
            raise ValueError(f"non-finite or shape-mismatched Torch/NumPy {key}")
        error = float(np.max(np.abs(left - right)))
        if not np.isfinite(error) or error > 2e-12:
            raise ValueError(f"Torch-double/NumPy parity failed for {key}: {error}")
        comparisons[key] = error
    zero_index = len(x_rows) - 1
    if (not np.array_equal(expected["basis_8"][zero_index], np.zeros(8, dtype=np.float64))
            or not np.array_equal(expected["physical_output_rad_s2"][zero_index], np.zeros(3, dtype=np.float64))
            or not torch.equal(actual_torch["physical_output_rad_s2"][zero_index], torch.zeros(3, dtype=torch.float64))):
        raise ValueError("exact zero-basis output check failed")

    source_hashes = {relative: sha256(repo_file(root, relative))
                     for relative in (TRAINER, READER, NUMPY_MODEL, TORCH_MODEL, MATLAB_FORWARD)}
    deployment = {
        "schema": "CM18_A1T_DEPLOYMENT_PARAMETERS_V1",
        "artifact_class": "DO_NOT_GIT_UPLOAD",
        "status": "PYTHON_PARITY_PASS_MATLAB_PARITY_PENDING",
        "network": "18->32 tanh->32 tanh->24 coefficients; basis=[z/2;u]; exact zero-basis output",
        "label_semantics": "direct compensation C*: raw network target is C*/beta; runtime clip then beta is unchanged",
        "runtime_clip_beta_action_evaluated": False,
        "physical_reachability_review_required": True,
        "dtype": "float64 canonical normalizer; W/b promoted from frozen float32 best checkpoint",
        "parameters": {name: np.asarray(value, dtype=np.float64).tolist() for name, value in p.items()},
        "identity": {
            "training_release_sha256": trained["release_sha256"],
            "training_receipt_sha256": trained["receipt_sha256"],
            "checkpoint_sha256": trained["checkpoint_sha256"],
            "selected_step": trained["best_step"],
            "normalizer_file_sha256": trained["normalizer_file_sha256"],
            "actual_float32_normalizer_buffer_sha256": trained["float32_buffer_sha256"],
            "float32_buffer_to_canonical_max_abs": trained["float32_rounding_max_abs"],
            "canonical_normalizer_float64_sha256": trained["normalizer_sha256"],
            "dataset_manifest_path": trained["release"]["dataset_manifest"]["path"],
            "dataset_manifest_sha256": trained["release"]["dataset_manifest"]["sha256"],
            "numpy_model_sha256": source_hashes[NUMPY_MODEL],
            "torch_model_sha256": source_hashes[TORCH_MODEL],
            "matlab_forward_path": MATLAB_FORWARD,
            "matlab_forward_sha256": source_hashes[MATLAB_FORWARD],
            "postselect_source_sha256": sha256(Path(__file__).resolve()),
            "torch_double_numpy_max_abs": comparisons,
            "torch_numpy_parity_rows": int(len(xcheck)),
            "zero_basis_exact_zero": True,
            "deployment_authorized": False,
        },
    }
    output.mkdir(exist_ok=False)
    (output / ".gitignore").write_text("*\n!.gitignore\n!DO_NOT_GIT_UPLOAD.txt\n", encoding="utf-8")
    (output / "DO_NOT_GIT_UPLOAD.txt").write_text(
        "A1T candidate model and parity artifacts; do not upload to Git.\n", encoding="utf-8")
    deployment_path = output / "deployment_parameters_v1.json"
    write_json_new(deployment_path, deployment)
    deployment_sha = sha256(deployment_path)
    cases = []
    for ix, meta in enumerate(cases_meta):
        cases.append({
            **meta,
            "raw_features_18": np.asarray(xcheck[ix], dtype=np.float64).tolist(),
            "expected": {
                "coefficients_3x8": np.asarray(expected["coefficients_3x8"][ix], dtype=np.float64).tolist(),
                "basis_8": np.asarray(expected["basis_8"][ix], dtype=np.float64).tolist(),
                "normalized_output": np.asarray(expected["normalized_output"][ix], dtype=np.float64).tolist(),
                "physical_output_rad_s2": np.asarray(expected["physical_output_rad_s2"][ix], dtype=np.float64).tolist(),
            },
        })
    fixture = {
        "schema": "CM18_A1T_MATLAB_PARITY_FIXTURE_V1",
        "status": "PYTHON_PARITY_PASS_MATLAB_PARITY_PENDING",
        "tolerance_abs": 2e-12,
        "case_count": 11,
        "identity": {
            "deployment_parameters_sha256": deployment_sha,
            "checkpoint_sha256": trained["checkpoint_sha256"],
            "selected_step": trained["best_step"],
            "canonical_normalizer_float64_sha256": trained["normalizer_sha256"],
            "matlab_forward_path": MATLAB_FORWARD,
            "matlab_forward_sha256": source_hashes[MATLAB_FORWARD],
            "numpy_model_sha256": source_hashes[NUMPY_MODEL],
            "torch_model_sha256": source_hashes[TORCH_MODEL],
            "B_cache": b_identity,
            "C5_cache": c5_identity,
            "indices_zero_based": list(EVENT_INDICES_ZERO_BASED),
            "used_for_fit_or_selection": False,
        },
        "cases": cases,
    }
    write_json_new(output / "matlab_parity_fixture_v1.json", fixture)
    summary = {
        "schema": "CM18_A1T_POSTSELECT_EXPORT_RECEIPT_V1",
        "status": "PYTHON_PARITY_PASS_MATLAB_PARITY_PENDING",
        "training_receipt_sha256": trained["receipt_sha256"],
        "training_release_sha256": trained["release_sha256"],
        "checkpoint_sha256": trained["checkpoint_sha256"],
        "selected_step": trained["best_step"],
        "canonical_normalizer_sha256": trained["normalizer_sha256"],
        "deployment_parameters_sha256": deployment_sha,
        "matlab_fixture_sha256": sha256(output / "matlab_parity_fixture_v1.json"),
        "matlab_forward_sha256": source_hashes[MATLAB_FORWARD],
        "torch_double_numpy_max_abs": comparisons,
        "parity_cases": 11,
        "B_and_C5_same_scene_id": SCENE_ID,
        "fixture_indices_zero_based": list(EVENT_INDICES_ZERO_BASED),
        "fit_or_selection_used_fixture": False,
        "TEST_accessed": False,
        "Plant_calls": 0,
        "optimizer_steps": 0,
        "deployment_authorized": False,
    }
    write_json_new(output / "postselect_export_receipt_v1.json", summary)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--release-sha256", required=True)
    parser.add_argument("--receipt-sha256", required=True)
    args = parser.parse_args()
    if len(args.release_sha256) != 64 or len(args.receipt_sha256) != 64:
        parser.error("release and terminal receipt SHA256 values must be 64 hex characters")
    out = run(args.repo_root, args.release_sha256.lower(), args.receipt_sha256.lower())
    print(out)


if __name__ == "__main__":
    main()