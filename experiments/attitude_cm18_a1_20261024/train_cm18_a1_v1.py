"""One-shot CM18-A1 formal trainer; only SCREEN4 zero-step self-check is ungated."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import random
import shutil
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SEED = 2026102001
STEPS = 60_000
BATCH_SIZE = 512
EVAL_EVERY = 1_000
PROGRESS_EVERY = 100
MAX_OUTPUT_BYTES = 1 << 30
MIN_FREE_BYTES = 30_000_000_000
INPUT_MANIFEST_SHA256 = "a5f7fea9b0918c1449af6fa83929177d3bf7d5e70cb3b71711c40f6338d210a5"
SCREEN4_MANIFEST = "reports/attitude_cm18_a1_20261024/data_preparation_v1/events_screen4_v1/DATASET_MANIFEST_v1.json"
SCREEN4_MANIFEST_SHA256 = "b36a9027202a15408d69676c5e16f7993652c4c7a82c6a8695a64eb77961ef7c"
TASKBOOK = "reports/attitude_cm18_a1_20261024/A1_FORMAL_TRAINING_TASKBOOK_v1_ZH.md"
INPUT_MANIFEST = "reports/attitude_cm18_a1_20261024/data_preparation_v1/INPUT_MANIFEST_v1.json"
AUDIT = "reports/attitude_cm18_a1_20261024/data_preparation_v1/ROOT_ALL816_INDEPENDENT_AUDIT_v1.json"
TRAINER = "experiments/attitude_cm18_a1_20261024/train_cm18_a1_v1.py"
READER = "experiments/attitude_cm18_a1_20261024/cache_reader_cm18_v1.py"
NUMPY_MODEL = "experiments/attitude_cm18_a1_20261024/model_cm18_v1.py"
TORCH_MODEL = "experiments/attitude_cm18_a1_20261024/torch_model_cm18_v1.py"
FORMAL_OUTPUT = "experiments/attitude_cm18_a1_20261024/training_run_v1"


def _set_math_environment() -> None:
    if os.environ.get("KMP_DUPLICATE_LIB_OK"):
        raise RuntimeError("KMP_DUPLICATE_LIB_OK is forbidden for CM18-A1")
    os.environ["MKL_THREADING_LAYER"] = "SEQUENTIAL"
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
    os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"


_set_math_environment()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_path(root: Path, relative: str) -> Path:
    root = root.resolve(strict=True)
    path = (root / relative).resolve(strict=True)
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"release path escapes repository root: {relative}") from exc
    return path


def _write_json(path: Path, value: Any) -> None:
    temp = path.with_name(path.name + ".tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temp.replace(path)


def _append_jsonl(path: Path, value: Any) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")))
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _source_modules(root: Path) -> tuple[Any, Any, Any]:
    def load(relative: str, name: str) -> Any:
        spec = importlib.util.spec_from_file_location(name, _safe_path(root, relative))
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load pinned module: {relative}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    reader = load(READER, "cm18_cache_reader_v1")
    numpy_model = load(NUMPY_MODEL, "cm18_numpy_model_v1")
    torch_model = load(TORCH_MODEL, "cm18_torch_model_v1")
    return reader, numpy_model, torch_model


def _check_release(root: Path, release_path: Path, expected_release_sha: str) -> tuple[dict[str, Any], dict[str, Any]]:
    root = root.resolve(strict=True)
    release_path = release_path.resolve(strict=True)
    release = _load_json(release_path)
    if _sha256(release_path).lower() != expected_release_sha.lower():
        raise ValueError("ROOT release SHA256 mismatch")
    if release.get("schema") != "CM18_A1_TRAINING_RELEASE_V1":
        raise ValueError("unexpected ROOT training release schema")
    if release.get("decision") != "APPROVE_ONE_FORMAL_TRAINING":
        raise ValueError("ROOT release does not approve one formal training run")
    if release.get("seed") != SEED or release.get("optimizer_steps") != STEPS or release.get("device") != "cuda:0":
        raise ValueError("ROOT release training constants differ from the frozen taskbook")
    if release.get("output_directory") != FORMAL_OUTPUT:
        raise ValueError("ROOT release output_directory differs from the sole permitted run directory")
    approved_gpu_rows = release.get("gpu_background_rows")
    if not isinstance(approved_gpu_rows, list) or any(not isinstance(row, str) or not row.strip() or row != row.strip() for row in approved_gpu_rows):
        raise ValueError("ROOT release must pin the approved nvidia-smi background process rows")
    if len(set(approved_gpu_rows)) != len(approved_gpu_rows):
        raise ValueError("ROOT release gpu_background_rows must be unique")

    expected_sources = {TRAINER, READER, NUMPY_MODEL, TORCH_MODEL}
    sources = release.get("source_files")
    if not isinstance(sources, list) or len(sources) != len(expected_sources):
        raise ValueError("ROOT release must pin exactly four CM18 source files")
    seen: set[str] = set()
    source_hashes: dict[str, str] = {}
    for item in sources:
        if not isinstance(item, dict):
            raise ValueError("malformed source_files entry")
        path, sha = item.get("path"), item.get("sha256")
        if path not in expected_sources or path in seen or not isinstance(sha, str):
            raise ValueError("source_files must contain each required path exactly once")
        seen.add(path)
        actual = _sha256(_safe_path(root, path)).lower()
        if actual != sha.lower():
            raise ValueError(f"source identity mismatch: {path}")
        source_hashes[path] = actual
    if seen != expected_sources:
        raise ValueError("ROOT release source identities are incomplete")

    for key, expected_path in (("taskbook", TASKBOOK), ("data_audit", AUDIT)):
        entry = release.get(key)
        if not isinstance(entry, dict) or entry.get("path") != expected_path:
            raise ValueError(f"ROOT release {key} path mismatch")
        actual = _sha256(_safe_path(root, expected_path)).lower()
        if actual != str(entry.get("sha256", "")).lower():
            raise ValueError(f"ROOT release {key} SHA256 mismatch")
    audit = _load_json(_safe_path(root, AUDIT))
    if audit.get("status") != "PASS" or audit.get("audit_mode") != "ALL816":
        raise ValueError("independent data audit must be PASS for ALL816")
    dataset_counts = audit.get("dataset_counts")
    if not isinstance(dataset_counts, dict) or dataset_counts.get("scenes") != 816:
        raise ValueError("independent ALL816 audit must count exactly 816 scenes")
    if dataset_counts.get("passed_cache_audits") != 816 or dataset_counts.get("failed_cache_audits") != 0:
        raise ValueError("independent ALL816 audit must pass all 816 cache audits")
    expected_audit_events = {"TRAIN": 768 * 1999, "VAL": 48 * 1999}
    if dataset_counts.get("event_count_by_split") != expected_audit_events:
        raise ValueError("independent ALL816 audit event counts do not match the frozen split totals")

    input_pin = release.get("input_manifest")
    if not isinstance(input_pin, dict) or input_pin.get("path") != INPUT_MANIFEST:
        raise ValueError("ROOT release input manifest path mismatch")
    if str(input_pin.get("sha256", "")).lower() != INPUT_MANIFEST_SHA256:
        raise ValueError("ROOT release input manifest SHA does not match the frozen identity")
    if _sha256(_safe_path(root, INPUT_MANIFEST)).lower() != INPUT_MANIFEST_SHA256:
        raise ValueError("input manifest file SHA256 mismatch")

    dataset_pin = release.get("dataset_manifest")
    if not isinstance(dataset_pin, dict):
        raise ValueError("ROOT release dataset_manifest is missing")
    manifest_relative = dataset_pin.get("path")
    manifest_sha = str(dataset_pin.get("sha256", "")).lower()
    if not isinstance(manifest_relative, str) or len(manifest_sha) != 64:
        raise ValueError("malformed ROOT dataset manifest pin")
    manifest_path = _safe_path(root, manifest_relative)
    if _sha256(manifest_path).lower() != manifest_sha:
        raise ValueError("final ALL816 manifest SHA256 mismatch")
    if str(audit.get("dataset_manifest_sha256", "")).lower() != manifest_sha:
        raise ValueError("independent ALL816 audit dataset manifest identity mismatch")
    if str(audit.get("input_manifest_sha256_actual", "")).lower() != INPUT_MANIFEST_SHA256:
        raise ValueError("independent ALL816 audit input manifest identity mismatch")
    manifest = _load_json(manifest_path)
    _validate_dataset_manifest(manifest, "ALL816")
    if str(manifest.get("input_manifest_sha256", "")).lower() != INPUT_MANIFEST_SHA256:
        raise ValueError("final ALL816 manifest input identity mismatch")
    return {
        "release_sha256": expected_release_sha.lower(),
        "dataset_manifest_path": manifest_relative,
        "dataset_manifest_sha256": manifest_sha,
        "input_manifest_path": INPUT_MANIFEST,
        "input_manifest_sha256": INPUT_MANIFEST_SHA256,
        "source_files": source_hashes,
        "taskbook_sha256": str(release["taskbook"]["sha256"]).lower(),
        "data_audit_sha256": str(release["data_audit"]["sha256"]).lower(),
        "gpu_background_rows": approved_gpu_rows,
    }, manifest


def _validate_dataset_manifest(manifest: dict[str, Any], mode: str) -> None:
    expected_scene_count = 816 if mode == "ALL816" else 4
    expected_train, expected_val = (768, 48) if mode == "ALL816" else (2, 2)
    if manifest.get("schema") != "CM18_A1_DATASET_MANIFEST_V1" or manifest.get("mode") != mode:
        raise ValueError(f"dataset manifest must be mode={mode}")
    if manifest.get("TEST_accessed") is not False:
        raise ValueError("dataset manifest does not certify TEST isolation")
    rows = manifest.get("rows")
    if not isinstance(rows, list) or len(rows) != expected_scene_count:
        raise ValueError(f"dataset manifest must contain exactly {expected_scene_count} rows")
    if manifest.get("scene_count") != expected_scene_count or manifest.get("qualified_count") != expected_scene_count or manifest.get("failed_count") != 0:
        raise ValueError("dataset manifest counts are not fully qualified")
    scene_ids = []
    split_counts = {"TRAIN": 0, "VAL": 0}
    for row in rows:
        if not isinstance(row, dict) or row.get("qualified") is not True or row.get("status") != "PASS":
            raise ValueError("dataset manifest includes a failed or unqualified row")
        scene_id, split = row.get("scene_id"), row.get("split")
        if not isinstance(scene_id, str) or not scene_id or split not in split_counts:
            raise ValueError("dataset manifest rows may contain TRAIN/VAL scenes only")
        scene_ids.append(scene_id)
        split_counts[split] += 1
    if len(set(scene_ids)) != expected_scene_count:
        raise ValueError("dataset manifest contains duplicate scene identities")
    if split_counts != {"TRAIN": expected_train, "VAL": expected_val}:
        raise ValueError(f"dataset split counts mismatch: {split_counts}")


def _read_scenes(root: Path, manifest_path: str, manifest_sha: str, mode: str, reader: Any | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if reader is None:
        reader = _source_modules(root)[0]
    train = reader.load_qualified_split(root, manifest_path, "TRAIN", manifest_sha)
    val = reader.load_qualified_split(root, manifest_path, "VAL", manifest_sha)
    if mode == "ALL816" and (len(train) != 768 or len(val) != 48):
        raise ValueError("reader returned unexpected ALL816 split counts")
    if mode == "SCREEN4" and (len(train) != 2 or len(val) != 2):
        raise ValueError("reader returned unexpected SCREEN4 split counts")
    return train, val


def _training_arrays(scenes: list[dict[str, Any]], np: Any) -> tuple[Any, Any, Any, Any, Any]:
    sample_indices = np.arange(0, 1996, 5, dtype=np.int64)
    if sample_indices.shape != (400,) or sample_indices[-1] != 1995:
        raise AssertionError("frozen 400-event TRAIN sampling rule changed")
    xs = np.concatenate([scene["X18"][sample_indices] for scene in scenes], axis=0)
    ys = np.concatenate([scene["target_raw"][sample_indices] for scene in scenes], axis=0)
    mean = xs.mean(axis=0, dtype=np.float64)
    std = np.maximum(xs.std(axis=0, ddof=0, dtype=np.float64), 1e-6)
    axis_rms = np.sqrt(np.mean(np.square(ys, dtype=np.float64), axis=0, dtype=np.float64))
    if not np.isfinite(mean).all() or not np.isfinite(std).all() or not np.isfinite(axis_rms).all() or np.any(axis_rms <= 0):
        raise ValueError("TRAIN-only normalizers are invalid")
    return xs, ys, mean, std, axis_rms


def _state_sha256(model: Any) -> str:
    digest = hashlib.sha256()
    for name, tensor in sorted(model.state_dict().items()):
        array = tensor.detach().cpu().contiguous().numpy()
        digest.update(name.encode("utf-8") + b"\0")
        digest.update(array.dtype.str.encode("ascii") + b"\0")
        digest.update(json.dumps(list(array.shape), separators=(",", ":")).encode("ascii") + b"\0")
        digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def _save_checkpoint(torch: Any, model: Any, path: Path, step: int, kind: str, score: float | None = None) -> str:
    state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
    torch.save({"schema": "CM18_A1_CHECKPOINT_V1", "kind": kind, "optimizer_step": step, "selection_score": score, "state_dict": state}, path)
    return _sha256(path)


def _json_metrics(actual: Any, target: Any, np: Any) -> dict[str, Any]:
    error = np.asarray(actual, dtype=np.float64) - np.asarray(target, dtype=np.float64)
    axis = {}
    for i, name in enumerate(("x", "y", "z")):
        values = error[:, i]
        axis[name] = {"mae_rad_s2": float(np.mean(np.abs(values))), "rmse_rad_s2": float(np.sqrt(np.mean(np.square(values))))}
    return {"events": int(error.shape[0]), "axis": axis}


def _scene_eval(model: Any, scene: dict[str, Any], axis_rms: Any, device: Any, torch: Any, np: Any) -> dict[str, Any]:
    model.eval()
    predictions: list[Any] = []
    with torch.no_grad():
        for start in range(0, len(scene["X18"]), 4096):
            raw = torch.as_tensor(scene["X18"][start:start + 4096], dtype=torch.float32, device=device)
            output = model(raw)["physical_output_rad_s2"]
            predictions.append(output.detach().cpu().numpy().astype(np.float64, copy=False))
    pred = np.concatenate(predictions, axis=0)
    target = scene["target_raw"]
    normalized_error = (pred - target) / axis_rms
    baseline_normalized_error = -target / axis_rms
    score = float(np.sqrt(np.mean(np.sum(np.square(normalized_error), axis=1))))
    baseline_score = float(np.sqrt(np.mean(np.sum(np.square(baseline_normalized_error), axis=1))))
    result: dict[str, Any] = {
        "scene_id": scene["scene_id"],
        "normalized_scene_score": score,
        "zero_prediction_normalized_scene_score": baseline_score,
        "physical_error": _json_metrics(pred, target, np),
        "zero_prediction_physical_error": _json_metrics(np.zeros_like(target), target, np),
        "phase": {},
    }
    phases = scene["phase_code"].reshape(-1)
    for phase_code in range(6):
        mask = phases == phase_code
        if np.any(mask):
            result["phase"][str(phase_code)] = {
                "physical_error": _json_metrics(pred[mask], target[mask], np),
                "zero_prediction_physical_error": _json_metrics(np.zeros_like(target[mask]), target[mask], np),
            }
        else:
            result["phase"][str(phase_code)] = {"events": 0, "physical_error": None, "zero_prediction_physical_error": None}
    return result


def _evaluate(model: Any, val_scenes: list[dict[str, Any]], axis_rms: Any, device: Any, torch: Any, np: Any) -> tuple[float, float, list[dict[str, Any]]]:
    rows = [_scene_eval(model, scene, axis_rms, device, torch, np) for scene in val_scenes]
    score = float(np.mean([row["normalized_scene_score"] for row in rows]))
    baseline = float(np.mean([row["zero_prediction_normalized_scene_score"] for row in rows]))
    return score, baseline, rows


def _check_output_budget(run_dir: Path) -> None:
    total = sum(path.stat().st_size for path in run_dir.rglob("*") if path.is_file())
    if total > MAX_OUTPUT_BYTES:
        raise RuntimeError(f"output budget exceeded: {total} > {MAX_OUTPUT_BYTES} bytes")


def _runtime_preflight(output_parent: Path, approved_gpu_rows: list[str]) -> dict[str, Any]:
    free = shutil.disk_usage(output_parent).free
    if free < MIN_FREE_BYTES:
        raise RuntimeError(f"less than 30 GB free at output filesystem: {free} bytes")
    command = shutil.which("nvidia-smi")
    if command is None:
        raise RuntimeError("nvidia-smi is required to verify that no other GPU compute job is active")
    result = subprocess.run(
        [command, "--query-compute-apps=pid,process_name", "--format=csv,noheader,nounits"],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"nvidia-smi compute-process preflight failed: {result.stderr.strip()}")
    active = [line.strip() for line in result.stdout.splitlines() if line.strip() and "No running processes found" not in line]
    unknown = sorted(set(active) - set(approved_gpu_rows))
    if unknown:
        raise RuntimeError(f"unapproved GPU process rows are active; no process was terminated: {unknown}")
    utilization = subprocess.run(
        [command, "--query-gpu=index,utilization.gpu", "--format=csv,noheader,nounits"],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if utilization.returncode != 0:
        raise RuntimeError(f"nvidia-smi GPU-utilization preflight failed: {utilization.stderr.strip()}")
    utilization_rows = [line.strip() for line in utilization.stdout.splitlines() if line.strip()]
    utilization_percent = []
    try:
        utilization_percent = [float(row.rsplit(",", 1)[1].strip().removesuffix("%")) for row in utilization_rows]
    except (IndexError, ValueError) as exc:
        raise RuntimeError(f"cannot parse nvidia-smi GPU utilization rows: {utilization_rows}") from exc
    if not utilization_percent or any(value > 10.0 for value in utilization_percent):
        raise RuntimeError(f"GPU utilization must be at most 10% on every device: {utilization_rows}")
    return {
        "free_disk_bytes_at_start": free,
        "approved_nvidia_smi_compute_process_rows": approved_gpu_rows,
        "actual_nvidia_smi_compute_process_rows": active,
        "nvidia_smi_gpu_utilization_rows": utilization_rows,
        "nvidia_smi_gpu_utilization_percent": utilization_percent,
    }


def _record_failure(run_dir: Path, receipt: dict[str, Any], exc: BaseException, failure_step: int | None) -> None:
    detail = {
        "schema": "CM18_A1_TRAINING_FAILURE_V1",
        "recorded_at_utc": _now(),
        "stage": receipt.get("active_stage"),
        "optimizer_step_attempted": failure_step,
        "optimizer_steps_completed": receipt.get("optimizer_steps_completed", 0),
        "exception_type": type(exc).__name__,
        "message": str(exc),
        "traceback": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
    }
    _write_json(run_dir / "failure.json", detail)
    receipt.update({
        "status": "FAILED",
        "ended_at_utc": _now(),
        "failure_reason": f"{type(exc).__name__}: {exc}",
        "failure_step": failure_step,
    })
    _write_json(run_dir / "run_receipt.json", receipt)


def _formal_train(root: Path, release_path: Path, release_sha: str) -> Path:
    root = root.resolve(strict=True)
    pinned, manifest = _check_release(root, release_path, release_sha)
    run_dir = root / FORMAL_OUTPUT
    if run_dir.exists():
        raise FileExistsError(f"formal output directory already exists; refusing reuse: {run_dir}")
    if not run_dir.parent.is_dir():
        raise FileNotFoundError(f"formal output parent does not exist: {run_dir.parent}")
    preflight = _runtime_preflight(run_dir.parent, pinned["gpu_background_rows"])
    run_dir.mkdir(exist_ok=False)
    receipt: dict[str, Any] = {
        "schema": "CM18_A1_TRAINING_RECEIPT_V1",
        "status": "INITIALIZING",
        "started_at_utc": _now(),
        "ended_at_utc": None,
        "command": sys.argv,
        "cwd": str(Path.cwd()),
        "run_directory": FORMAL_OUTPUT,
        "release": pinned,
        "environment": {key: os.environ.get(key) for key in ("MKL_THREADING_LAYER", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "CUBLAS_WORKSPACE_CONFIG")},
        "preflight": preflight,
        "optimizer_steps_completed": 0,
        "active_stage": "import_runtime",
        "failure_reason": None,
    }
    _write_json(run_dir / "run_receipt.json", receipt)
    failure_step: int | None = None
    model = None
    torch = None
    try:
        import numpy as np
        import torch as torch_module

        torch = torch_module
        reader, numpy_model, torch_model = _source_modules(root)
        receipt["runtime"] = {
            "python": sys.version,
            "numpy": np.__version__,
            "torch": torch.__version__,
            "cuda_runtime": torch.version.cuda,
            "gpu_name": None,
            "device": "cuda:0",
            "deterministic_algorithms": True,
            "tf32": False,
        }
        if not torch.cuda.is_available() or torch.cuda.device_count() < 1:
            raise RuntimeError("formal CM18-A1 training requires CUDA device cuda:0")
        torch.cuda.set_device(0)
        receipt["runtime"]["gpu_name"] = torch.cuda.get_device_name(0)
        torch.use_deterministic_algorithms(True)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        if hasattr(torch, "set_float32_matmul_precision"):
            torch.set_float32_matmul_precision("highest")
        random.seed(SEED)
        torch.manual_seed(SEED)
        torch.cuda.manual_seed_all(SEED)

        receipt["active_stage"] = "load_all816_caches"
        _write_json(run_dir / "run_receipt.json", receipt)
        train_scenes, val_scenes = _read_scenes(root, pinned["dataset_manifest_path"], pinned["dataset_manifest_sha256"], "ALL816", reader)
        if len(train_scenes) != 768 or len(val_scenes) != 48:
            raise ValueError("ALL816 reader split totals do not match 768 TRAIN + 48 VAL")
        x_train64, y_train64, input_mean, input_std, axis_rms = _training_arrays(train_scenes, np)
        if x_train64.shape != (307_200, 18) or y_train64.shape != (307_200, 3):
            raise ValueError("TRAIN fit rows must be exactly 307200")
        val_event_count = sum(len(scene["X18"]) for scene in val_scenes)
        if val_event_count != 48 * 1999:
            raise ValueError("VAL must use all 1999 events from each of 48 scenes")

        parameters = numpy_model.initialize_random_parameters(SEED, input_mean, input_std, axis_rms)
        model = torch_model.TorchCM18A1(input_mean, input_std, axis_rms)
        model.load_numpy_parameters(parameters)
        for name, value in model.numpy_parameters().items():
            if not np.array_equal(value, parameters[name]):
                raise AssertionError(f"NumPy initialization was not copied exactly: {name}")
        model = model.float().to(torch.device("cuda:0"))
        initial_f32 = model.numpy_parameters()
        for name in parameters:
            if not np.array_equal(initial_f32[name], parameters[name].astype(np.float32)):
                raise AssertionError(f"float32 start differs from NumPy initialization cast: {name}")
        model_initial_sha = _state_sha256(model)
        std_floor_indices = np.flatnonzero(input_std == 1e-6).tolist()
        promoted_std = initial_f32["input_std"].astype(np.float64)
        promoted_std_below_floor = np.flatnonzero(promoted_std < 1e-6).tolist()

        norm_payload = {
            "schema": "CM18_A1_NORMALIZER_V1",
            "fit_rows": 307_200,
            "train_scenes": 768,
            "sample_indices_per_scene": "0,5,10,...,1995 (400 rows)",
            "calculation_dtype": "float64",
            "std_ddof": 0,
            "input_mean_float64": input_mean.tolist(),
            "input_std_float64": input_std.tolist(),
            "train_axis_rms_rad_s2_float64": axis_rms.tolist(),
            "input_mean_float32_buffer": initial_f32["input_mean"].tolist(),
            "input_std_float32_buffer": initial_f32["input_std"].tolist(),
            "train_axis_rms_float32_buffer": initial_f32["train_axis_rms_rad_s2"].tolist(),
            "std_floor_indices_float64": std_floor_indices,
            "float32_std_promoted_to_float64_below_floor_indices": promoted_std_below_floor,
            "float32_buffer_sha256": hashlib.sha256(b"".join(initial_f32[k].tobytes(order="C") for k in ("input_mean", "input_std", "train_axis_rms_rad_s2"))).hexdigest(),
            "float64_arrays_sha256": hashlib.sha256(b"".join(np.ascontiguousarray(a, dtype=np.float64).tobytes() for a in (input_mean, input_std, axis_rms))).hexdigest(),
            "float32_checkpoint_state_sha256": model_initial_sha,
            "float32_checkpoint_rule": "training checkpoint stores float32 weights, biases, and normalizer buffers",
            "deployment_export_rule": "use canonical float64 normalizer arrays above; promote trained float32 W/b to float64; never reconstruct canonical scales from float32 checkpoint buffers",
        }
        _write_json(run_dir / "normalizer.json", norm_payload)
        np.savez_compressed(
            run_dir / "initial_parameters.npz",
            **parameters,
            **{f"actual_float32_{key}": value for key, value in initial_f32.items()},
        )
        initial_parameter_file_sha = _sha256(run_dir / "initial_parameters.npz")
        initial_checkpoint_sha = _save_checkpoint(torch, model, run_dir / "initial.pt", 0, "initial")

        training_config = {
            "schema": "CM18_A1_TRAINING_CONFIG_V1",
            "release": pinned,
            "seed": SEED,
            "optimizer": {"name": "Adam", "lr": 0.001, "betas": [0.9, 0.999], "eps": 1e-8, "weight_decay": 1e-5},
            "optimizer_steps": STEPS,
            "batch_size": BATCH_SIZE,
            "batch_sampling": "NumPy default_rng(2026102001), independent with-replacement integers over the 307200 ordered TRAIN fit rows",
            "loss": "SmoothL1(beta=1.0, mean over batch and 3 axes), physical model prediction and target divided by saved TRAIN axis RMS",
            "device": "cuda:0",
            "dtype": "float32",
            "amp": False,
            "tf32": False,
            "torch_deterministic_algorithms": True,
            "training_scene_count": len(train_scenes),
            "training_fit_rows": int(len(x_train64)),
            "validation_scene_count": len(val_scenes),
            "validation_events": val_event_count,
            "initial_numpy_parameter_archive_sha256": initial_parameter_file_sha,
            "initial_float32_state_sha256": model_initial_sha,
            "initial_checkpoint_sha256": initial_checkpoint_sha,
            "environment": receipt["environment"],
            "runtime": receipt["runtime"],
        }
        _write_json(run_dir / "training_config.json", training_config)
        _check_output_budget(run_dir)

        device = torch.device("cuda:0")
        train_x = torch.as_tensor(x_train64.astype(np.float32), dtype=torch.float32, device=device)
        train_y_norm = torch.as_tensor((y_train64 / axis_rms).astype(np.float32), dtype=torch.float32, device=device)
        axis_rms_t = torch.as_tensor(axis_rms.astype(np.float32), dtype=torch.float32, device=device)
        val_y_norm_check = np.concatenate([scene["target_raw"] for scene in val_scenes], axis=0)
        if not np.isfinite(val_y_norm_check).all():
            raise ValueError("non-finite VAL target")
        del val_y_norm_check
        optimizer = torch.optim.Adam(model.parameters(), lr=0.001, betas=(0.9, 0.999), eps=1e-8, weight_decay=1e-5)
        rng = np.random.default_rng(SEED)
        best_score = math.inf
        best_step = -1
        receipt.update({"status": "RUNNING", "optimizer_steps_completed": 0, "active_stage": "evaluate_step0"})
        _write_json(run_dir / "run_receipt.json", receipt)

        def evaluate_at(step: int) -> None:
            nonlocal best_score, best_step
            score, baseline, scene_rows = _evaluate(model, val_scenes, axis_rms, device, torch, np)
            updated = score < best_score
            if updated:
                best_score, best_step = score, step
                checkpoint_sha = _save_checkpoint(torch, model, run_dir / "best.pt", step, "best", score)
            else:
                checkpoint_sha = _sha256(run_dir / "best.pt")
            summary = {
                "schema": "CM18_A1_VALIDATION_SUMMARY_V1",
                "optimizer_step": step,
                "scene_weighted_normalized_score": score,
                "zero_prediction_scene_weighted_normalized_score": baseline,
                "best_updated": updated,
                "best_step": best_step,
                "best_score": best_score,
                "best_checkpoint_sha256": checkpoint_sha,
            }
            _append_jsonl(run_dir / "val_metrics.jsonl", summary)
            for row in scene_rows:
                _append_jsonl(run_dir / "val_per_scene.jsonl", {"optimizer_step": step, **row})
            _check_output_budget(run_dir)

        evaluate_at(0)
        receipt.update({"best_step": best_step, "best_score": best_score, "active_stage": "train"})
        _write_json(run_dir / "run_receipt.json", receipt)
        model.train()
        for step in range(1, STEPS + 1):
            failure_step = step
            sampled = rng.integers(0, len(train_x), size=BATCH_SIZE, dtype=np.int64)
            batch_index = torch.as_tensor(sampled, dtype=torch.long, device=device)
            optimizer.zero_grad(set_to_none=True)
            physical = model(train_x[batch_index])["physical_output_rad_s2"]
            prediction_norm = physical / axis_rms_t
            loss = torch.nn.functional.smooth_l1_loss(prediction_norm, train_y_norm[batch_index], beta=1.0, reduction="mean")
            loss_value = float(loss.detach().item())
            if not math.isfinite(loss_value):
                raise FloatingPointError(f"non-finite loss at optimizer_step={step}: {loss_value}")
            loss.backward()
            for name, parameter in model.named_parameters():
                if parameter.grad is None or not torch.isfinite(parameter.grad).all().item():
                    raise FloatingPointError(f"missing or non-finite gradient at optimizer_step={step}: {name}")
            for name, parameter in model.named_parameters():
                if not torch.isfinite(parameter).all().item():
                    raise FloatingPointError(f"non-finite parameter before optimizer step {step}: {name}")
            optimizer.step()
            receipt["optimizer_steps_completed"] = step
            if any(not torch.isfinite(parameter).all().item() for parameter in model.parameters()):
                raise FloatingPointError(f"non-finite parameter after optimizer_step={step}")
            if step % PROGRESS_EVERY == 0:
                _write_json(run_dir / "progress.json", {"optimizer_steps_completed": step, "optimizer_steps_target": STEPS, "latest_loss": loss_value, "updated_at_utc": _now()})
            if step % EVAL_EVERY == 0:
                receipt["active_stage"] = f"validation_step_{step}"
                receipt["best_step"] = best_step
                receipt["best_score"] = best_score
                _write_json(run_dir / "run_receipt.json", receipt)
                evaluate_at(step)
                receipt["active_stage"] = "train"
                receipt["best_step"] = best_step
                receipt["best_score"] = best_score
                _write_json(run_dir / "run_receipt.json", receipt)
                model.train()
            if step % PROGRESS_EVERY == 0:
                _check_output_budget(run_dir)
        failure_step = None
        receipt["active_stage"] = "save_final"
        final_sha = _save_checkpoint(torch, model, run_dir / "final.pt", STEPS, "final")
        receipt.update({"status": "COMPLETED", "optimizer_steps_completed": STEPS, "ended_at_utc": _now(), "best_step": best_step, "best_score": best_score, "final_checkpoint_sha256": final_sha, "active_stage": None})
        _write_json(run_dir / "run_receipt.json", receipt)
        _check_output_budget(run_dir)
        return run_dir
    except BaseException as exc:
        if model is not None and torch is not None:
            try:
                _save_checkpoint(torch, model, run_dir / "final.pt", int(receipt.get("optimizer_steps_completed", 0)), "final_on_failure")
            except BaseException:
                pass
        try:
            _record_failure(run_dir, receipt, exc, failure_step)
        except BaseException:
            # Keep the already-created INITIALIZING receipt if the filesystem itself failed.
            pass
        raise


def _self_check_screen4(root: Path) -> dict[str, Any]:
    import numpy as np
    import torch

    manifest_path = _safe_path(root, SCREEN4_MANIFEST)
    if _sha256(manifest_path).lower() != SCREEN4_MANIFEST_SHA256:
        raise ValueError("SCREEN4 manifest SHA256 mismatch")
    manifest = _load_json(manifest_path)
    _validate_dataset_manifest(manifest, "SCREEN4")
    if str(manifest.get("input_manifest_sha256", "")).lower() != INPUT_MANIFEST_SHA256:
        raise ValueError("SCREEN4 manifest input identity mismatch")
    required_ids = {
        "DL1018_TRAIN_T1_C00_W00", "DL1018_TRAIN_T1_C01_W00",
        "DL1018_VAL_T1_C00_W07", "DL1018_VAL_T1_C01_W08",
    }
    if {row["scene_id"] for row in manifest["rows"]} != required_ids:
        raise ValueError("SCREEN4 scene identities differ from the frozen four-cache set")
    reader, numpy_model, torch_model = _source_modules(root)
    train_scenes, val_scenes = _read_scenes(root, SCREEN4_MANIFEST, SCREEN4_MANIFEST_SHA256, "SCREEN4", reader)
    x, y, mean, std, axis_rms = _training_arrays(train_scenes, np)
    if x.shape != (800, 18) or y.shape != (800, 3):
        raise AssertionError("SCREEN4 must fit on exactly 800 TRAIN rows")
    parameters = numpy_model.initialize_random_parameters(SEED, mean, std, axis_rms)
    torch.use_deterministic_algorithms(True)
    torch.manual_seed(SEED)
    model = torch_model.TorchCM18A1(mean, std, axis_rms)
    model.load_numpy_parameters(parameters)
    model.float()
    actual_f32 = model.numpy_parameters()
    active_rows = np.flatnonzero(np.any(x[:, 7:15] != 0.0, axis=1))[:64]
    if len(active_rows) != 64:
        raise AssertionError("SCREEN4 must provide 64 nonzero morphology-basis rows")
    features = torch.as_tensor(x[active_rows].astype(np.float32), dtype=torch.float32)
    targets = torch.as_tensor((y[active_rows] / axis_rms).astype(np.float32), dtype=torch.float32)
    predicted = model(features)["physical_output_rad_s2"] / model.train_axis_rms_rad_s2
    loss = torch.nn.functional.smooth_l1_loss(predicted, targets, beta=1.0, reduction="mean")
    loss.backward()
    if not torch.isfinite(loss).item() or any(parameter.grad is None or not torch.isfinite(parameter.grad).all().item() for parameter in model.parameters()):
        raise AssertionError("SCREEN4 0-step forward/backward produced non-finite loss or gradients")
    double_parameters = {key: value.astype(np.float64) for key, value in actual_f32.items()}
    double_parameters["input_mean"] = mean.copy()
    double_parameters["input_std"] = std.copy()
    double_parameters["train_axis_rms_rad_s2"] = axis_rms.copy()
    double_model = torch_model.TorchCM18A1(mean, std, axis_rms)
    double_model.load_numpy_parameters(double_parameters)
    with torch.no_grad():
        double_pred = double_model(torch.as_tensor(x[active_rows], dtype=torch.float64))["physical_output_rad_s2"].cpu().numpy()
    float_pred = model(features)["physical_output_rad_s2"].detach().cpu().numpy().astype(np.float64)
    deployment_delta = float(np.max(np.abs(float_pred - double_pred)))
    std_floor_idx = np.flatnonzero(std == 1e-6).tolist()
    actual_f32_std = actual_f32["input_std"].astype(np.float64)
    f32_roundtrip_below_floor = np.flatnonzero(actual_f32_std < 1e-6).tolist()
    if not std_floor_idx or not set(std_floor_idx).issubset(f32_roundtrip_below_floor):
        raise AssertionError("SCREEN4 must expose the float32 1e-6 normalizer floor rounding")
    canonical_norm_sha = hashlib.sha256(b"".join(np.ascontiguousarray(a, dtype=np.float64).tobytes() for a in (mean, std, axis_rms))).hexdigest()
    actual_norm_sha = hashlib.sha256(b"".join(actual_f32[k].tobytes(order="C") for k in ("input_mean", "input_std", "train_axis_rms_rad_s2"))).hexdigest()
    return {
        "schema": "CM18_A1_SCREEN4_SELF_CHECK_V1",
        "status": "PASS",
        "mode": "SCREEN4",
        "manifest_path": SCREEN4_MANIFEST,
        "manifest_sha256": SCREEN4_MANIFEST_SHA256,
        "scene_ids": [scene["scene_id"] for scene in train_scenes + val_scenes],
        "train_scene_count": len(train_scenes),
        "val_scene_count": len(val_scenes),
        "train_fit_rows": int(len(x)),
        "val_events": sum(len(scene["X18"]) for scene in val_scenes),
        "normalizer_source": "SCREEN4 TRAIN rows at event indices 0,5,...,1995; float64; std ddof=0",
        "input_mean_float64": mean.tolist(),
        "input_std_float64": std.tolist(),
        "train_axis_rms_rad_s2_float64": axis_rms.tolist(),
        "float64_canonical_normalizer_sha256": canonical_norm_sha,
        "actual_float32_normalizer_buffer_sha256": actual_norm_sha,
        "std_floor_indices_float64": std_floor_idx,
        "float32_std_promoted_to_float64_below_floor_indices": f32_roundtrip_below_floor,
        "deployment_export_rule": "preserve canonical float64 normalizers; promote trained float32 W/b to float64; do not reconstruct canonical scales from float32 buffers",
        "initial_float32_state_sha256": _state_sha256(model),
        "initial_float32_vs_canonical_double_max_abs_output_delta_rad_s2": deployment_delta,
        "torch_dtype": "float32",
        "forward_backward_loss": float(loss.detach().item()),
        "nonzero_basis_rows_checked": int(len(active_rows)),
        "optimizer_steps": 0,
        "optimizer_step_calls": 0,
        "training_started": False,
        "environment": {key: os.environ.get(key) for key in ("MKL_THREADING_LAYER", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "CUBLAS_WORKSPACE_CONFIG")},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--self-check", choices=("SCREEN4",))
    parser.add_argument("--release", type=Path)
    parser.add_argument("--release-sha256")
    args = parser.parse_args()
    root = args.repo_root.resolve(strict=True)
    if args.self_check == "SCREEN4":
        if args.release is not None or args.release_sha256 is not None:
            parser.error("--self-check SCREEN4 cannot be combined with a formal release")
        result = _self_check_screen4(root)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return
    if args.release is None or args.release_sha256 is None:
        parser.error("formal training requires both ROOT --release and --release-sha256 pins")
    if len(args.release_sha256) != 64:
        parser.error("--release-sha256 must be a 64-character SHA256")
    run_dir = _formal_train(root, args.release, args.release_sha256)
    print(json.dumps({"status": "COMPLETED", "run_directory": str(run_dir), "optimizer_steps": STEPS}, indent=2))


if __name__ == "__main__":
    main()
