"""Export and independently re-evaluate the one completed CM18-A2 run.

This command is intentionally gated on the final 60,000-step COMPLETED receipt.
It never trains or modifies a checkpoint; all output is exclusive-created under
deployment_retry1_v1 and contains model artifacts that must not be uploaded to Git.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import re
import sys
from pathlib import Path
from typing import Any


RUN_REL = Path("experiments/attitude_cm18_a2_20261024/training_retry1_v1")
DEPLOY_REL = Path("experiments/attitude_cm18_a2_20261024/deployment_retry1_v1")
TRAINER_REL = Path("experiments/attitude_cm18_a2_20261024/train_cm18_a2_retry1_v1.py")
SCREEN4_MANIFEST = "reports/attitude_cm18_a1_20261024/data_preparation_v1/events_screen4_v1/DATASET_MANIFEST_v1.json"
SCREEN4_SHA256 = "b36a9027202a15408d69676c5e16f7993652c4c7a82c6a8695a64eb77961ef7c"
INPUT_SHA256 = "a5f7fea9b0918c1449af6fa83929177d3bf7d5e70cb3b71711c40f6338d210a5"
SCREEN4_VAL_IDS = ("DL1018_VAL_T1_C00_W07", "DL1018_VAL_T1_C01_W08")
HOLD_PHASE_CODE = 3
EXPECTED_STEPS = 60_000
EXPECTED_SCENES = 48
EVENTS_PER_SCENE = 1999
NORMALIZER_REFIT_ATOL = 1e-10
EVAL_STEPS = tuple(range(0, EXPECTED_STEPS + 1, 1000))
PARAMETER_TENSORS = {
    "W1": ("fc1.weight", (32, 18)), "b1": ("fc1.bias", (32,)),
    "W2": ("fc2.weight", (32, 32)), "b2": ("fc2.bias", (32,)),
    "W3": ("fc3.weight", (24, 32)), "b3": ("fc3.bias", (24,)),
}
NORMALIZER_TENSORS = {
    "input_mean": ("input_mean", "input_mean_float32_buffer", (18,)),
    "input_std": ("input_std", "input_std_float32_buffer", (18,)),
    "train_axis_rms_rad_s2": ("train_axis_rms_rad_s2", "train_axis_rms_float32_buffer", (3,)),
}
AXIS_NAMES = ("x", "y", "z")


def _set_math_environment() -> None:
    if os.environ.get("KMP_DUPLICATE_LIB_OK"):
        raise RuntimeError("KMP_DUPLICATE_LIB_OK is forbidden")
    os.environ.update(MKL_THREADING_LAYER="SEQUENTIAL", OMP_NUM_THREADS="1",
                      MKL_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1",
                      CUBLAS_WORKSPACE_CONFIG=":4096:8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_repo_file(root: Path, relative: str | Path) -> Path:
    path = (root / relative).resolve(strict=True)
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"path escapes repository root: {relative}") from exc
    if not path.is_file():
        raise ValueError(f"expected file: {relative}")
    return path


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            raise ValueError(f"blank JSONL row at {path}:{line_number}")
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"expected JSON object at {path}:{line_number}")
        rows.append(value)
    return rows


def _write_json_exclusive(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def _load_trainer(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location("cm18_trainer_for_export_v1", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load trainer: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _assert_close(actual: float, expected: float, label: str, tolerance: float = 1e-12) -> None:
    if not math.isfinite(float(actual)) or not math.isfinite(float(expected)):
        raise ValueError(f"non-finite value while checking {label}")
    if abs(float(actual) - float(expected)) > tolerance:
        raise ValueError(f"{label} mismatch: {actual!r} vs {expected!r}")


def _assert_tree_close(actual: Any, expected: Any, label: str, np: Any) -> None:
    if isinstance(expected, dict):
        if not isinstance(actual, dict) or set(actual) != set(expected):
            raise ValueError(f"{label} fields differ")
        for key in expected:
            _assert_tree_close(actual[key], expected[key], f"{label}.{key}", np)
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            raise ValueError(f"{label} length differs")
        for index, (got, want) in enumerate(zip(actual, expected)):
            _assert_tree_close(got, want, f"{label}[{index}]", np)
    elif isinstance(expected, bool) or expected is None or isinstance(expected, str):
        if actual != expected:
            raise ValueError(f"{label} differs: {actual!r} vs {expected!r}")
    elif isinstance(expected, int):
        if actual != expected:
            raise ValueError(f"{label} differs: {actual!r} vs {expected!r}")
    elif isinstance(expected, (int, float)):
        if not np.isfinite(float(actual)) or abs(float(actual) - float(expected)) > 1e-12:
            raise ValueError(f"{label} differs: {actual!r} vs {expected!r}")
    else:
        raise TypeError(f"unsupported metric value at {label}: {type(expected).__name__}")


def _metric(actual: Any, target: Any, np: Any) -> dict[str, Any]:
    error = np.asarray(actual, dtype=np.float64) - np.asarray(target, dtype=np.float64)
    return {"events": int(error.shape[0]), "axis": {
        axis: {"mae_rad_s2": float(np.mean(np.abs(error[:, i]))),
               "rmse_rad_s2": float(np.sqrt(np.mean(np.square(error[:, i]))))}
        for i, axis in enumerate(AXIS_NAMES)}}


def _scene_result(scene: dict[str, Any], pred: Any, axis_rms: Any, np: Any) -> dict[str, Any]:
    target = np.asarray(scene["target_raw"], dtype=np.float64)
    pred = np.asarray(pred, dtype=np.float64)
    normalized_error = (pred - target) / axis_rms
    baseline_error = -target / axis_rms
    row = {
        "scene_id": scene["scene_id"],
        "normalized_scene_score": float(np.sqrt(np.mean(np.sum(np.square(normalized_error), axis=1)))),
        "zero_prediction_normalized_scene_score": float(np.sqrt(np.mean(np.sum(np.square(baseline_error), axis=1)))),
        "physical_error": _metric(pred, target, np),
        "zero_prediction_physical_error": _metric(np.zeros_like(target), target, np),
        "phase": {},
    }
    phase_codes = np.asarray(scene["phase_code"]).reshape(-1)
    for code in range(6):
        mask = phase_codes == code
        row["phase"][str(code)] = ({
            "physical_error": _metric(pred[mask], target[mask], np),
            "zero_prediction_physical_error": _metric(np.zeros_like(target[mask]), target[mask], np),
        } if np.any(mask) else {
            "events": 0, "physical_error": None, "zero_prediction_physical_error": None,
        })
    return row


def _normalizer_from_train(train_scenes: list[dict[str, Any]], np: Any) -> tuple[Any, Any, Any]:
    indices = np.arange(0, 1996, 5, dtype=np.int64)
    x = np.concatenate([scene["X18"][indices] for scene in train_scenes], axis=0)
    y = np.concatenate([scene["target_raw"][indices] for scene in train_scenes], axis=0)
    mean = x.mean(axis=0, dtype=np.float64)
    std = np.maximum(x.std(axis=0, dtype=np.float64, ddof=0), 1e-6)
    axis_rms = np.sqrt(np.mean(np.square(y, dtype=np.float64), axis=0, dtype=np.float64))
    if x.shape != (307_200, 18) or y.shape != (307_200, 3):
        raise ValueError("TRAIN normalizer refit must use exactly 307200 ordered rows")
    if not np.isfinite(mean).all() or not np.isfinite(std).all() or not np.isfinite(axis_rms).all() or np.any(axis_rms <= 0):
        raise ValueError("independently recomputed TRAIN normalizer is invalid")
    return mean, std, axis_rms


def _array_sha(arrays: tuple[Any, ...], dtype: Any, np: Any) -> str:
    return hashlib.sha256(b"".join(np.ascontiguousarray(value, dtype=dtype).tobytes(order="C")
                                    for value in arrays)).hexdigest()


def _recompute_cuda_val(model: Any, scenes: list[dict[str, Any]], axis_rms: Any,
                        torch: Any, np: Any) -> tuple[list[dict[str, Any]], list[Any]]:
    rows, predictions = [], []
    model.eval()
    with torch.inference_mode():
        for scene in scenes:
            scene_predictions = []
            x = scene["X18"]
            for start in range(0, len(x), 4096):
                batch = torch.as_tensor(x[start:start + 4096], dtype=torch.float32, device="cuda:0")
                output = model(batch)["physical_output_rad_s2"]
                scene_predictions.append(output.detach().cpu().numpy().astype(np.float64, copy=False))
            pred = np.concatenate(scene_predictions, axis=0)
            if pred.shape != (EVENTS_PER_SCENE, 3) or not np.isfinite(pred).all():
                raise ValueError(f"invalid CUDA prediction for {scene['scene_id']}")
            predictions.append(pred)
            rows.append(_scene_result(scene, pred, axis_rms, np))
    return rows, predictions


def _difference_stats(delta: Any, np: Any) -> dict[str, Any]:
    absolute = np.abs(np.asarray(delta, dtype=np.float64))
    percentiles = (50, 90, 95, 99, 99.9, 100)
    return {
        "max_abs_rad_s2": float(np.max(absolute)),
        "rms_rad_s2": float(np.sqrt(np.mean(np.square(delta, dtype=np.float64)))),
        "absolute_percentile_rad_s2": {str(p): float(np.percentile(absolute, p)) for p in percentiles},
    }


def _fixture(case_name: str, scene: dict[str, Any], index: int, parameters: dict[str, Any],
             scene_manifest_row: dict[str, Any], manifest_sha: str, numpy_model: Any,
             np: Any) -> dict[str, Any]:
    raw = np.asarray(scene["X18"][index], dtype=np.float64)
    zero = raw.copy()
    zero[7:15] = 0.0
    perturbed = raw.copy()
    perturbed[3:5] += np.array([17.0, -23.0], dtype=np.float64)
    result = numpy_model.forward(raw, parameters)
    perturbed_result = numpy_model.forward(perturbed, parameters)
    zero_result = numpy_model.forward(zero, parameters)
    if not np.array_equal(zero_result["physical_output_rad_s2"], np.zeros(3, dtype=np.float64)):
        raise AssertionError(f"{case_name}: zero morphology basis did not produce exact zero")
    if not np.array_equal(result["physical_output_rad_s2"][2], perturbed_result["physical_output_rad_s2"][2]):
        raise AssertionError(f"{case_name}: yaw output depends on masked alphaBS input")
    raw_bytes = np.ascontiguousarray(raw, dtype="<f8").tobytes(order="C")
    zero_bytes = np.ascontiguousarray(zero, dtype="<f8").tobytes(order="C")
    expected = {key: value.tolist() for key, value in result.items()}
    expected["perturbed_physical_output_rad_s2"] = perturbed_result["physical_output_rad_s2"].tolist()
    expected["zero_basis_physical_output_rad_s2"] = zero_result["physical_output_rad_s2"].tolist()
    expected["a1_full_physical_output_rad_s2"] = (
        np.einsum("ij,j->i", result["full_coefficients_3x8"], result["basis_8"])
        * np.asarray(parameters["train_axis_rms_rad_s2"], dtype=np.float64)
    ).tolist()
    return {
        "schema": "CM18_A2_PARITY_FIXTURE_V1",
        "case_identity": {
            "case": case_name,
            "scene_id": scene["scene_id"], "split": "VAL",
            "event_index_zero_based": int(index), "event_index_one_based": int(index + 1),
            "plant_index_matlab_1based": int(np.asarray(scene["plant_index"]).reshape(-1)[index]),
            "event_time_s": float(np.asarray(scene["event_time_s"]).reshape(-1)[index]),
            "phase_code": int(np.asarray(scene["phase_code"]).reshape(-1)[index]),
            "input_manifest_sha256": INPUT_SHA256,
            "screen4_manifest_sha256": manifest_sha,
            "cache_sha256": str(scene_manifest_row["cache_sha256"]).lower(),
            "raw_feature_sha256_little_endian_float64": hashlib.sha256(raw_bytes).hexdigest(),
            "zero_basis_feature_sha256_little_endian_float64": hashlib.sha256(zero_bytes).hexdigest(),
        },
        "raw_features": raw.tolist(),
        "perturbed_alphaBS_features": perturbed.tolist(),
        "zero_basis_features": zero.tolist(),
        "parameters": {name: np.asarray(value, dtype=np.float64).tolist() for name, value in parameters.items()},
        "expected": expected,
        "tolerance_abs": 1e-10,
    }


def _compare_recorded_rows(actual_rows: list[dict[str, Any]], expected_rows: list[dict[str, Any]],
                           np: Any) -> None:
    actual_ids = [row["scene_id"] for row in actual_rows]
    expected_ids = [row["scene_id"] for row in expected_rows]
    if actual_ids != expected_ids:
        raise ValueError("selected-step VAL scene ordering differs from the manifest")
    for actual, expected in zip(actual_rows, expected_rows):
        for key in ("normalized_scene_score", "zero_prediction_normalized_scene_score",
                    "physical_error", "zero_prediction_physical_error", "phase"):
            _assert_tree_close(actual[key], expected[key], f"{actual['scene_id']}.{key}", np)


def export(root: Path, release_path: Path, expected_release_sha: str) -> dict[str, Any]:
    root = root.resolve(strict=True)
    run_dir = (root / RUN_REL).resolve(strict=True)
    run_dir.relative_to(root)
    if not run_dir.is_dir():
        raise ValueError("formal training run directory is missing")
    output_dir = root / DEPLOY_REL
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite deployment output: {output_dir}")
    if not output_dir.parent.is_dir():
        raise FileNotFoundError(f"deployment parent directory is missing: {output_dir.parent}")

    receipt_path = _safe_repo_file(root, RUN_REL / "run_receipt.json")
    receipt = _json(receipt_path)
    if receipt.get("schema") != "CM18_A2_TRAINING_RECEIPT_V1" or receipt.get("status") != "COMPLETED":
        raise ValueError("export requires a naturally COMPLETED formal run")
    if receipt.get("optimizer_steps_completed") != EXPECTED_STEPS or receipt.get("active_stage") is not None:
        raise ValueError("run receipt does not certify exactly 60000 completed optimizer steps")
    if receipt.get("failure_reason") is not None or receipt.get("run_directory") != RUN_REL.as_posix():
        raise ValueError("run receipt has a failure or unexpected run directory")
    runtime = receipt.get("runtime")
    if (not isinstance(runtime, dict) or runtime.get("device") != "cuda:0"
            or runtime.get("deterministic_algorithms") is not True or runtime.get("tf32") is not False):
        raise ValueError("run receipt does not certify the frozen CUDA deterministic runtime")
    environment = receipt.get("environment")
    if not isinstance(environment, dict) or environment.get("CUBLAS_WORKSPACE_CONFIG") != ":4096:8":
        raise ValueError("run receipt is missing the frozen CUDA deterministic environment")
    receipt_release = receipt.get("release")
    if not isinstance(receipt_release, dict):
        raise ValueError("run receipt does not contain its pinned release identity")
    release_sha = str(receipt_release.get("release_sha256", "")).lower()
    if not re.fullmatch(r"[0-9a-f]{64}", release_sha):
        raise ValueError("run receipt release SHA256 is malformed")
    expected_release_sha = expected_release_sha.lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected_release_sha) or release_sha != expected_release_sha:
        raise ValueError("explicit ROOT release SHA256 does not match the run receipt pin")

    release_path = release_path.resolve(strict=True)
    try:
        release_path.relative_to(root)
    except ValueError as exc:
        raise ValueError("ROOT training release must be inside the repository") from exc
    trainer_path = _safe_repo_file(root, TRAINER_REL)
    trainer = _load_trainer(trainer_path)
    if trainer.FORMAL_OUTPUT != RUN_REL.as_posix():
        raise ValueError("trainer formal output path differs from the exporter")
    pinned, dataset_manifest = trainer._check_release(root, release_path, expected_release_sha)
    if pinned != receipt_release:
        raise ValueError("run receipt release identity differs from the pinned ROOT release")

    np = __import__("numpy")
    torch = __import__("torch")
    reader, numpy_model, torch_model = trainer._source_modules(root)
    config_path = _safe_repo_file(root, RUN_REL / "training_config.json")
    normalizer_path = _safe_repo_file(root, RUN_REL / "normalizer.json")
    initial_archive_path = _safe_repo_file(root, RUN_REL / "initial_parameters.npz")
    metrics_path = _safe_repo_file(root, RUN_REL / "val_metrics.jsonl")
    per_scene_path = _safe_repo_file(root, RUN_REL / "val_per_scene.jsonl")
    best_path = _safe_repo_file(root, RUN_REL / "best.pt")
    final_path = _safe_repo_file(root, RUN_REL / "final.pt")
    initial_path = _safe_repo_file(root, RUN_REL / "initial.pt")
    config, normalizer = _json(config_path), _json(normalizer_path)
    if config.get("schema") != "CM18_A2_TRAINING_CONFIG_V1" or config.get("release") != pinned:
        raise ValueError("training config release identity mismatch")
    if (config.get("candidate") != "A2_YAW_CONTEXT_INVARIANT"
            or config.get("forward_contract") != "full 18-feature forward supplies roll/pitch; shared-weight second forward sets raw feature indices 3:5 to zero before normalization and supplies yaw"):
        raise ValueError("training config does not certify the frozen A2 shared-forward contract")
    if (config.get("seed") != trainer.SEED or config.get("optimizer_steps") != EXPECTED_STEPS
            or config.get("training_scene_count") != 768 or config.get("training_fit_rows") != 307_200
            or config.get("validation_scene_count") != EXPECTED_SCENES
            or config.get("validation_events") != EXPECTED_SCENES * EVENTS_PER_SCENE
            or config.get("device") != "cuda:0" or config.get("dtype") != "float32"
            or config.get("amp") is not False or config.get("tf32") is not False
            or config.get("torch_deterministic_algorithms") is not True):
        raise ValueError("training config differs from the frozen formal run")
    if config.get("batch_size") != 512 or config.get("optimizer") != {
        "name": "Adam", "lr": 0.001, "betas": [0.9, 0.999], "eps": 1e-8, "weight_decay": 1e-5,
    }:
        raise ValueError("training config optimizer or batch size differs from the frozen taskbook")
    if normalizer.get("schema") != "CM18_A2_NORMALIZER_V1" or normalizer.get("fit_rows") != 307_200 or normalizer.get("train_scenes") != 768:
        raise ValueError("normalizer identity or TRAIN-only fit counts are invalid")
    if normalizer.get("sample_indices_per_scene") != "0,5,10,...,1995 (400 rows)" or normalizer.get("calculation_dtype") != "float64" or normalizer.get("std_ddof") != 0:
        raise ValueError("normalizer does not record the frozen TRAIN fitting rule")

    release_file_sha = _sha256(release_path)
    source_hashes = dict(pinned["source_files"])
    for relative, expected_sha in source_hashes.items():
        if _sha256(_safe_repo_file(root, relative)).lower() != str(expected_sha).lower():
            raise ValueError(f"source SHA changed after training: {relative}")
    source_hashes[str(TRAINER_REL.as_posix())] = _sha256(trainer_path)
    if _sha256(_safe_repo_file(root, trainer.TASKBOOK)).lower() != pinned["taskbook_sha256"]:
        raise ValueError("frozen taskbook changed after training")
    if _sha256(_safe_repo_file(root, trainer.INPUT_MANIFEST)).lower() != INPUT_SHA256:
        raise ValueError("input manifest identity mismatch")
    if str(pinned["input_manifest_sha256"]).lower() != INPUT_SHA256:
        raise ValueError("release input manifest identity mismatch")
    if str(dataset_manifest.get("input_manifest_sha256", "")).lower() != INPUT_SHA256:
        raise ValueError("ALL816 manifest input identity mismatch")

    train_scenes = reader.load_qualified_split(root, pinned["dataset_manifest_path"], "TRAIN", pinned["dataset_manifest_sha256"])
    val_scenes = reader.load_qualified_split(root, pinned["dataset_manifest_path"], "VAL", pinned["dataset_manifest_sha256"])
    if len(train_scenes) != 768 or len(val_scenes) != EXPECTED_SCENES or any(len(scene["X18"]) != EVENTS_PER_SCENE for scene in val_scenes):
        raise ValueError("pinned dataset does not load as 768 TRAIN and 48 full VAL scenes")
    if sum(len(scene["X18"]) for scene in val_scenes) != EXPECTED_SCENES * EVENTS_PER_SCENE:
        raise ValueError("VAL event total differs from the frozen 95952 events")

    canonical = {
        "input_mean": np.asarray(normalizer.get("input_mean_float64"), dtype=np.float64),
        "input_std": np.asarray(normalizer.get("input_std_float64"), dtype=np.float64),
        "train_axis_rms_rad_s2": np.asarray(normalizer.get("train_axis_rms_rad_s2_float64"), dtype=np.float64),
    }
    expected_shapes = {"input_mean": (18,), "input_std": (18,), "train_axis_rms_rad_s2": (3,)}
    for name, shape in expected_shapes.items():
        if canonical[name].shape != shape or not np.isfinite(canonical[name]).all():
            raise ValueError(f"canonical normalizer {name} is malformed")
    if np.any(canonical["input_std"] < 1e-6) or np.any(canonical["train_axis_rms_rad_s2"] <= 0):
        raise ValueError("canonical normalizer scales are invalid")
    canonical_sha = _array_sha((canonical["input_mean"], canonical["input_std"], canonical["train_axis_rms_rad_s2"]), np.float64, np)
    if canonical_sha != normalizer.get("float64_arrays_sha256"):
        raise ValueError("canonical float64 normalizer array SHA mismatch")
    fitted = _normalizer_from_train(train_scenes, np)
    normalizer_refit_delta = {}
    for name, value in zip(("input_mean", "input_std", "train_axis_rms_rad_s2"), fitted):
        delta = np.abs(canonical[name] - value)
        max_delta = float(np.max(delta))
        normalizer_refit_delta[name] = max_delta
        if not np.isfinite(max_delta) or max_delta > NORMALIZER_REFIT_ATOL:
            raise ValueError(f"normalizer differs from independent TRAIN-only refit by more than {NORMALIZER_REFIT_ATOL}: {name}={max_delta}")

    for name, (_, float_key, shape) in NORMALIZER_TENSORS.items():
        buffer = np.asarray(normalizer[float_key], dtype=np.float32)
        if buffer.shape != shape or not np.isfinite(buffer).all():
            raise ValueError(f"saved float32 normalizer buffer {float_key} is malformed")
    actual_buffer_sha = _array_sha(tuple(np.asarray(normalizer[float_key], dtype=np.float32)
                                         for _, float_key, _ in NORMALIZER_TENSORS.values()), np.float32, np)
    if actual_buffer_sha != normalizer.get("float32_buffer_sha256"):
        raise ValueError("saved float32 normalizer buffer SHA mismatch")

    metrics = _jsonl(metrics_path)
    if len(metrics) != len(EVAL_STEPS) or [row.get("optimizer_step") for row in metrics] != list(EVAL_STEPS):
        raise ValueError("validation summary must contain exactly step 0 and each 1000-step evaluation through 60000")
    current_best_score, current_best_step, current_best_sha = math.inf, -1, None
    for row in metrics:
        if row.get("schema") != "CM18_A2_VALIDATION_SUMMARY_V1":
            raise ValueError("validation summary schema mismatch")
        score = float(row.get("scene_weighted_normalized_score", math.nan))
        if not math.isfinite(score):
            raise ValueError("validation history contains a non-finite score")
        updated = score < current_best_score
        if updated:
            current_best_score, current_best_step = score, int(row["optimizer_step"])
            current_best_sha = str(row.get("best_checkpoint_sha256", "")).lower()
        elif current_best_sha is not None and str(row.get("best_checkpoint_sha256", "")).lower() != current_best_sha:
            raise ValueError("best checkpoint SHA changed without a strict score improvement")
        if row.get("best_updated") is not updated or row.get("best_step") != current_best_step:
            raise ValueError("validation history violates strict-improvement / earliest-tie selection")
        _assert_close(row.get("best_score", math.nan), current_best_score, "running best validation score")
        if not re.fullmatch(r"[0-9a-f]{64}", str(row.get("best_checkpoint_sha256", "")).lower()):
            raise ValueError("validation history has a malformed best checkpoint SHA")
    if current_best_step < 0:
        raise ValueError("no finite best validation checkpoint was selected")
    if receipt.get("best_step") != current_best_step:
        raise ValueError("run receipt best_step differs from validation history")
    _assert_close(receipt.get("best_score", math.nan), current_best_score, "run receipt best score")
    best_sha, final_sha = _sha256(best_path), _sha256(final_path)
    if best_sha != current_best_sha or final_sha != str(receipt.get("final_checkpoint_sha256", "")).lower():
        raise ValueError("best/final checkpoint file SHA does not match training records")
    initial_archive_sha = _sha256(initial_archive_path)
    if initial_archive_sha != str(config.get("initial_numpy_parameter_archive_sha256", "")).lower():
        raise ValueError("initial parameter archive SHA does not match training config")
    initial_checkpoint_sha = _sha256(initial_path)
    if initial_checkpoint_sha != str(config.get("initial_checkpoint_sha256", "")).lower():
        raise ValueError("initial checkpoint SHA does not match training config")

    per_scene_metrics = _jsonl(per_scene_path)
    expected_per_scene_rows = len(EVAL_STEPS) * EXPECTED_SCENES
    if len(per_scene_metrics) != expected_per_scene_rows:
        raise ValueError("VAL per-scene ledger row count is incomplete")
    counts_by_step: dict[int, int] = {}
    selected_recorded_rows = []
    per_scene_keys = set()
    val_ids = [scene["scene_id"] for scene in val_scenes]
    for row in per_scene_metrics:
        step = int(row.get("optimizer_step", -1))
        scene_id = row.get("scene_id")
        key = (step, scene_id)
        if step not in EVAL_STEPS or scene_id not in val_ids or key in per_scene_keys:
            raise ValueError("VAL per-scene ledger contains an unexpected or duplicate row")
        per_scene_keys.add(key)
        counts_by_step[step] = counts_by_step.get(step, 0) + 1
        if step == current_best_step:
            selected_recorded_rows.append(row)
    if counts_by_step != {step: EXPECTED_SCENES for step in EVAL_STEPS}:
        raise ValueError("VAL per-scene ledger does not have 48 rows at each evaluation step")
    if [row.get("scene_id") for row in selected_recorded_rows] != val_ids:
        raise ValueError("selected-step per-scene ledger differs from manifest scene order")

    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(1)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    if hasattr(torch, "set_float32_matmul_precision"):
        torch.set_float32_matmul_precision("highest")
    if not torch.cuda.is_available() or torch.cuda.device_count() < 1:
        raise RuntimeError("post-training independent VAL recomputation requires cuda:0")
    torch.cuda.set_device(0)
    checkpoint = torch.load(best_path, map_location="cpu", weights_only=True)
    if not isinstance(checkpoint, dict) or checkpoint.get("schema") != "CM18_A2_CHECKPOINT_V1" or checkpoint.get("kind") != "best":
        raise ValueError("best.pt has an unexpected checkpoint schema or kind")
    if checkpoint.get("optimizer_step") != current_best_step:
        raise ValueError("best.pt selected step differs from the strict-minimum validation history")
    _assert_close(checkpoint.get("selection_score", math.nan), current_best_score, "best.pt selection score")
    state = checkpoint.get("state_dict")
    required_state = {item[0] for item in PARAMETER_TENSORS.values()} | {item[0] for item in NORMALIZER_TENSORS.values()}
    if not isinstance(state, dict) or set(state) != required_state:
        raise ValueError("best.pt state_dict keys differ from the CM18-A2 schema")
    for name, (tensor_key, shape) in PARAMETER_TENSORS.items():
        tensor = state[tensor_key]
        if tuple(tensor.shape) != shape or tensor.dtype != torch.float32 or not torch.isfinite(tensor).all().item():
            raise ValueError(f"best.pt {tensor_key} must be finite float32 with shape {shape}")
    actual_buffers: dict[str, Any] = {}
    for name, (tensor_key, float_key, shape) in NORMALIZER_TENSORS.items():
        tensor = state[tensor_key]
        if tuple(tensor.shape) != shape or tensor.dtype != torch.float32 or not torch.isfinite(tensor).all().item():
            raise ValueError(f"best.pt {tensor_key} must be finite float32 with shape {shape}")
        actual_buffers[name] = tensor.detach().cpu().numpy().copy()
        if not np.array_equal(actual_buffers[name], np.asarray(normalizer[float_key], dtype=np.float32)):
            raise ValueError(f"best.pt float32 normalizer buffer differs from normalizer.json: {name}")
    best_buffer_sha = _array_sha(tuple(actual_buffers[name] for name in NORMALIZER_TENSORS), np.float32, np)
    if best_buffer_sha != actual_buffer_sha:
        raise ValueError("actual best.pt float32 normalizer identity mismatch")

    parameters = {
        name: state[tensor_key].detach().cpu().numpy().astype(np.float64)
        for name, (tensor_key, _) in PARAMETER_TENSORS.items()
    }
    parameters.update({name: canonical[name].copy() for name in canonical})
    model = torch_model.TorchCM18A2(canonical["input_mean"], canonical["input_std"], canonical["train_axis_rms_rad_s2"])
    model.float().to(torch.device("cuda:0"))
    model.load_state_dict(state, strict=True)
    if any(value.dtype != torch.float32 for value in model.state_dict().values()):
        raise ValueError("loaded training model is not entirely float32")
    recomputed_rows, f32_predictions = _recompute_cuda_val(model, val_scenes, canonical["train_axis_rms_rad_s2"], torch, np)
    recomputed_score = float(np.mean([row["normalized_scene_score"] for row in recomputed_rows]))
    baseline_score = float(np.mean([row["zero_prediction_normalized_scene_score"] for row in recomputed_rows]))
    _assert_close(recomputed_score, current_best_score, "independently recomputed selected-step VAL score")
    selected_summary = next(row for row in metrics if row["optimizer_step"] == current_best_step)
    _assert_close(baseline_score, selected_summary.get("zero_prediction_scene_weighted_normalized_score", math.nan),
                  "selected-step zero-prediction VAL baseline")
    _compare_recorded_rows(selected_recorded_rows, recomputed_rows, np)

    per_scene_deploy_delta = []
    phase_totals: dict[str, int] = {str(code): 0 for code in range(6)}
    for scene, f32_pred, row in zip(val_scenes, f32_predictions, recomputed_rows):
        double_pred = numpy_model.forward(scene["X18"], parameters)["physical_output_rad_s2"]
        if double_pred.shape != f32_pred.shape or not np.isfinite(double_pred).all():
            raise ValueError(f"invalid canonical double deployment output for {scene['scene_id']}")
        per_scene_deploy_delta.append(double_pred - f32_pred)
        row["phase_event_counts"] = {str(code): int(np.count_nonzero(np.asarray(scene["phase_code"]).reshape(-1) == code))
                                     for code in range(6)}
        for code, count in row["phase_event_counts"].items():
            phase_totals[code] += count
    delta = np.concatenate(per_scene_deploy_delta, axis=0)
    deployment_delta = {"overall": _difference_stats(delta, np),
                        "per_axis": {axis: _difference_stats(delta[:, i], np)
                                     for i, axis in enumerate(AXIS_NAMES)}}
    if delta.shape != (EXPECTED_SCENES * EVENTS_PER_SCENE, 3):
        raise AssertionError("deployment comparison did not cover all VAL events")

    screen_path = _safe_repo_file(root, SCREEN4_MANIFEST)
    if _sha256(screen_path).lower() != SCREEN4_SHA256:
        raise ValueError("pinned SCREEN4 manifest SHA256 mismatch")
    screen_manifest = _json(screen_path)
    if screen_manifest.get("mode") != "SCREEN4" or screen_manifest.get("input_manifest_sha256") != INPUT_SHA256:
        raise ValueError("SCREEN4 manifest identity mismatch")
    screen_scenes = reader.load_qualified_split(root, SCREEN4_MANIFEST, "VAL", SCREEN4_SHA256)
    screen_by_id = {scene["scene_id"]: scene for scene in screen_scenes}
    if set(screen_by_id) != set(SCREEN4_VAL_IDS):
        raise ValueError("SCREEN4 VAL identities differ from the frozen C00/C01 fixture cases")
    screen_rows = {row["scene_id"]: row for row in screen_manifest["rows"]}
    fixture_specs = (
        ("SCREEN4_VAL_C00_FIRST_EVENT", SCREEN4_VAL_IDS[0], 0, "trained_val_c00_first_event_parity_v1.json"),
        ("SCREEN4_VAL_C01_FIRST_U_NONZERO", SCREEN4_VAL_IDS[1], None, "trained_val_c01_first_u_nonzero_parity_v1.json"),
        ("SCREEN4_VAL_C01_FIRST_HOLD", SCREEN4_VAL_IDS[1], "HOLD", "trained_val_c01_first_hold_parity_v1.json"),
    )
    fixtures: dict[str, dict[str, Any]] = {}
    for case_name, scene_id, selector, filename in fixture_specs:
        scene = screen_by_id[scene_id]
        if selector == "HOLD":
            matches = np.flatnonzero(np.asarray(scene["phase_code"]).reshape(-1) == HOLD_PHASE_CODE)
        elif selector is None:
            matches = np.flatnonzero(np.any(np.asarray(scene["X18"])[:, 7:11] != 0.0, axis=1))
        else:
            matches = np.asarray([selector], dtype=np.int64)
        if len(matches) == 0:
            raise ValueError(f"SCREEN4 fixture selector has no matching event: {case_name}")
        fixtures[filename] = _fixture(case_name, scene, int(matches[0]), parameters,
                                       screen_rows[scene_id], SCREEN4_SHA256, numpy_model, np)

    manifest_path = str(pinned["dataset_manifest_path"])
    normalizer_sha = _sha256(normalizer_path)
    config_sha = _sha256(config_path)
    metrics_sha = _sha256(metrics_path)
    per_scene_sha = _sha256(per_scene_path)
    exporter_sha = _sha256(Path(__file__).resolve(strict=True))
    identity = {
        "candidate": "A2_YAW_CONTEXT_INVARIANT",
        "forward_contract": "full-input roll/pitch; shared-weight raw-alphaBS-zero yaw branch",
        "release_sha256": release_file_sha,
        "training": {
            "run_directory": RUN_REL.as_posix(),
            "run_receipt_sha256": _sha256(receipt_path),
            "training_config_sha256": config_sha,
            "val_metrics_sha256": metrics_sha,
            "val_per_scene_sha256": per_scene_sha,
            "initial_parameter_archive_sha256": initial_archive_sha,
            "initial_checkpoint_sha256": initial_checkpoint_sha,
            "seed": trainer.SEED, "optimizer_steps_completed": EXPECTED_STEPS,
            "device": "cuda:0", "dtype": "float32",
        },
        "checkpoint_sha256": best_sha,
        "checkpoint_kind": "best",
        "selected_step": current_best_step,
        "selected_scene_weighted_normalized_score": current_best_score,
        "normalizer_sha256": normalizer_sha,
        "normalizer_float64_arrays_sha256": canonical_sha,
        "train_normalizer_independent_refit_max_abs_delta": normalizer_refit_delta,
        "train_normalizer_independent_refit_tolerance_abs": NORMALIZER_REFIT_ATOL,
        "actual_float32_normalizer_buffers": {
            "sha256": best_buffer_sha,
            "input_mean": actual_buffers["input_mean"].tolist(),
            "input_std": actual_buffers["input_std"].tolist(),
            "train_axis_rms_rad_s2": actual_buffers["train_axis_rms_rad_s2"].tolist(),
        },
        "source_files": source_hashes,
        "input": {
            "input_manifest_path": pinned["input_manifest_path"],
            "input_manifest_sha256": pinned["input_manifest_sha256"],
            "dataset_manifest_path": manifest_path,
            "dataset_manifest_sha256": pinned["dataset_manifest_sha256"],
            "data_audit_sha256": pinned["data_audit_sha256"],
            "screen4_manifest_sha256": SCREEN4_SHA256,
        },
        "taskbook_sha256": pinned["taskbook_sha256"],
        "continuation_gates_sha256": pinned["continuation_gates_sha256"],
        "exporter_sha256": exporter_sha,
    }
    deployment = {
        "schema": "CM18_A2_DEPLOYMENT_PARAMETERS_V1",
        "artifact_class": "MODEL_PRODUCT_DO_NOT_GIT_UPLOAD",
        "dtype": "float64 canonical deployment arrays; W/b promoted from trained float32 checkpoint",
        "parameters": {name: np.asarray(value, dtype=np.float64).tolist() for name, value in parameters.items()},
        "identity": identity,
    }
    validation = {
        "schema": "CM18_A2_POSTTRAIN_VALIDATION_RECALC_V1", "status": "PASS",
        "source_checkpoint_sha256": best_sha, "selected_step": current_best_step,
        "recorded_and_recomputed_scene_weighted_normalized_score": current_best_score,
        "recomputed_scene_weighted_normalized_score": recomputed_score,
        "recomputed_zero_prediction_scene_weighted_normalized_score": baseline_score,
        "recorded_recalculation_max_abs_metric_difference": "<=1e-12",
        "train_normalizer_independent_refit_max_abs_delta": normalizer_refit_delta,
        "train_normalizer_independent_refit_tolerance_abs": NORMALIZER_REFIT_ATOL,
        "scene_count": len(val_scenes), "events_per_scene": EVENTS_PER_SCENE,
        "total_val_events": EXPECTED_SCENES * EVENTS_PER_SCENE,
        "phase_event_totals": phase_totals,
        "float32_cuda0_vs_canonical_double_deployment": deployment_delta,
        "scene_metrics": recomputed_rows,
        "checkpoint_training_or_optimizer_calls": 0,
        "new_rollouts_or_plant_calls": 0,
        "TEST_accessed": False,
    }

    output_dir.mkdir(exist_ok=False)
    gitignore_path = output_dir / ".gitignore"
    with gitignore_path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write("*\n!.gitignore\n")
    artifacts: dict[str, str] = {}
    outputs = {"deployment_parameters_v1.json": deployment,
               "validation_recomputed_v1.json": validation, **fixtures}
    for filename, payload in outputs.items():
        path = output_dir / filename
        _write_json_exclusive(path, payload)
        artifacts[filename] = _sha256(path)
    export_receipt = {
        "schema": "CM18_A2_DEPLOYMENT_EXPORT_RECEIPT_V1", "status": "PASS",
        "artifact_class": "MODEL_PRODUCT_DO_NOT_GIT_UPLOAD",
        "exporter_sha256": exporter_sha, "deployment_directory": DEPLOY_REL.as_posix(),
        "gitignore_sha256": _sha256(gitignore_path),
        "selected_step": current_best_step, "checkpoint_sha256": best_sha,
        "normalizer_sha256": normalizer_sha, "artifacts": artifacts,
        "screen4_parity_fixture_cases": [item[0] for item in fixture_specs],
        "matlab_checker": "experiments/attitude_cm18_a2_20261024/matlab/check_cm18_a2_parity_v1.m",
        "python_checker": "experiments/attitude_cm18_a2_20261024/check_cm18_a2_fixture_v1.py",
        "optimizer_calls": 0, "TEST_accessed": False,
    }
    _write_json_exclusive(output_dir / "export_receipt_v1.json", export_receipt)
    return {"status": "PASS", "deployment_directory": DEPLOY_REL.as_posix(),
            "selected_step": current_best_step, "checkpoint_sha256": best_sha,
            "normalizer_sha256": normalizer_sha, "val_events": EXPECTED_SCENES * EVENTS_PER_SCENE,
            "canonical_double_max_delta_rad_s2": deployment_delta["overall"]["max_abs_rad_s2"],
            "exporter_sha256": exporter_sha, "artifacts": artifacts}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--release", type=Path, required=True,
                        help="the exact ROOT training release used by the completed run")
    parser.add_argument("--release-sha256", required=True,
                        help="ROOT-owned SHA256 pin for the exact training release")
    args = parser.parse_args()
    root = args.repo_root.resolve(strict=True)
    release = args.release if args.release.is_absolute() else root / args.release
    result = export(root, release, args.release_sha256)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
