"""Paired B24/C5-24 CM18 training; requires a hash-pinned ROOT release."""

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
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SEED = 2026102001
STEPS = 60_000
BATCH_SIZE = 512
PROGRESS_EVERY = 1_000
OUTPUTS = {
    "B24": "experiments/attitude_position_context_probe_20261024/b24_c524_paired_v1/training_B24_v1",
    "C5_24": "experiments/attitude_position_context_probe_20261024/b24_c524_paired_v1/training_C5_24_v1",
}
MAX_OUTPUT_BYTES = 1 << 30
MIN_FREE_BYTES = 30 * 1024**3

TASKBOOK = "reports/attitude_cm18_datarepair_20261024/ROOT_B24_C524_TRAINING_TASKBOOK_v1_ZH.md"
TASKBOOK_SHA256 = "67db01666cded8dcc901ba29b335e64fda8c13c4bc50106e3184845242f66d2e"
C5_TASKBOOK = "reports/attitude_cm18_datarepair_20261024/ROOT_C5_MATCHED_TRAIN24_PROTOCOL_TASKBOOK_v1.json"
C5_TASKBOOK_SHA256 = "88d7312087025a331dd532410b0ef31ed2dcb7dd3175239ad1d47bc68dd65f0b"
B_DATASET = "reports/attitude_cm18_datarepair_20261024/cstar_all816_v1/CSTAR_RELABEL_ALL816_v1.json"
B_DATASET_SHA256 = "421298399aacf2d7f82031f2bdecc39eacacc28196c7b872b925866655d211a6"
NORMALIZER = "experiments/attitude_cm18_datarepair_20261024/training_a1t_v1/normalizer.json"
NORMALIZER_SHA256 = "23e8432f4a1c3f71bfaaa4e3a7b07c4b9f6b0201842e35ba3bcb032ac61fd781"
NORMALIZER_AUDIT = "reports/attitude_cm18_datarepair_20261024/ROOT_CSTAR_ALL816_INDEPENDENT_AUDIT_v1.json"
NORMALIZER_AUDIT_SHA256 = "f8db2f1fa13447db4fd5b91b5b945391f437de56a2d8cf3ee01cab7c59f75a06"
INITIAL_PARAMETERS = "experiments/attitude_cm18_datarepair_20261024/training_a1t_v1/initial_parameters.npz"
INITIAL_PARAMETERS_SHA256 = "1f3a469eeb648345bacf6f6aa3be906e10efebc91e24442914fd32e880439cb2"
READER = "experiments/attitude_position_context_probe_20261024/b24_c524_paired_v1/read_b24_c524_paired_v1.py"
TRAINER = "experiments/attitude_position_context_probe_20261024/b24_c524_paired_v1/train_cm18_b24_c524_paired_v1.py"
B_READER = "experiments/attitude_cm18_datarepair_20261024/read_cstar_split_v1.py"
NUMPY_MODEL = "experiments/attitude_cm18_a1_20261024/model_cm18_v1.py"
TORCH_MODEL = "experiments/attitude_cm18_a1_20261024/torch_model_cm18_v1.py"
FROZEN_SOURCE_HASHES = {
    B_READER: "ced4251719f986d762f29ccced04fb80208a28e7aed1e2fe12d3b504955a4096",
    NUMPY_MODEL: "ad32c4f97bf96c63172547c944d80c45062502f1062b774934e0f7a868720cf6",
    TORCH_MODEL: "bc9fe34fe957cb624438eeccfdfe2ddd38ad40cc9a4e706ce58863c9271d5aa0",
}
CANONICAL_NORMALIZER_SHA256 = "12c864b9c2404235e0ea3f313bb0801a99902eca7cfdfbf43f0d8d584d5d609a"


def _set_math_environment() -> None:
    if os.environ.get("KMP_DUPLICATE_LIB_OK"):
        raise RuntimeError("KMP_DUPLICATE_LIB_OK is forbidden")
    os.environ["MKL_THREADING_LAYER"] = "SEQUENTIAL"
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
    os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"


_set_math_environment()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _configure_torch_determinism(torch: Any) -> None:
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    if hasattr(torch, "set_float32_matmul_precision"):
        torch.set_float32_matmul_precision("highest")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _repo_path(root: Path, relative: str, must_exist: bool = True) -> Path:
    base = root.resolve(strict=True)
    path = (base / relative).resolve(strict=must_exist)
    try:
        path.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"path escapes repository: {relative}") from exc
    return path


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _write_json(path: Path, value: Any) -> None:
    temp = path.with_name(path.name + ".tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    for attempt in range(20):
        try:
            os.replace(temp, path)
            return
        except PermissionError as exc:
            if getattr(exc, "winerror", None) not in (5, 32, 33) or attempt == 19:
                raise
            time.sleep(0.05)


def _append_jsonl(path: Path, value: Any) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")))
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _load_module(root: Path, relative: str, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, _repo_path(root, relative))
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load pinned module: {relative}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _source_files(root: Path, release: dict[str, Any]) -> dict[str, str]:
    expected = {TRAINER, READER, B_READER, NUMPY_MODEL, TORCH_MODEL}
    rows = release.get("source_files")
    if not isinstance(rows, list) or len(rows) != len(expected):
        raise ValueError("release must pin exactly trainer, paired reader, B reader, and two A1 model sources")
    observed: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict) or row.get("path") not in expected or row["path"] in observed:
            raise ValueError("release source_files contains an unexpected or duplicate source")
        path, digest = row["path"], str(row.get("sha256", "")).lower()
        actual = _sha256(_repo_path(root, path))
        if len(digest) != 64 or actual != digest:
            raise ValueError(f"release source SHA mismatch: {path}")
        if path in FROZEN_SOURCE_HASHES and actual != FROZEN_SOURCE_HASHES[path]:
            raise ValueError(f"frozen model/reader source changed: {path}")
        observed[path] = actual
    if set(observed) != expected:
        raise ValueError("release source_files are incomplete")
    return observed


def _pin(root: Path, release: dict[str, Any], key: str, path: str, sha: str) -> None:
    item = release.get(key)
    if not isinstance(item, dict) or item.get("path") != path or str(item.get("sha256", "")).lower() != sha:
        raise ValueError(f"release {key} path/SHA mismatch")
    if _sha256(_repo_path(root, path)) != sha:
        raise ValueError(f"actual {key} SHA mismatch")


def _check_release(root: Path, release_path: Path, release_sha: str, purpose: str) -> tuple[dict, dict[str, str]]:
    root = root.resolve(strict=True)
    release_path = release_path.resolve(strict=True)
    try:
        release_path.relative_to(root)
    except ValueError as exc:
        raise ValueError("ROOT release must live inside the current repository") from exc
    if _sha256(release_path).lower() != release_sha.lower():
        raise ValueError("ROOT release SHA256 mismatch")
    release = _load_json(release_path)
    expected_decision = "APPROVE_ZERO_STEP" if purpose == "self-check" else "APPROVE_ONE_BRANCH_TRAINING"
    if (release.get("schema") != "CM18_B24_C524_TRAINING_RELEASE_V1"
            or release.get("decision") != expected_decision
            or release.get("seed") != SEED or release.get("optimizer_steps") != STEPS
            or release.get("batch_size") != BATCH_SIZE or release.get("device") != "cuda:0"):
        raise ValueError("ROOT release does not match the frozen paired training protocol")
    if purpose == "self-check":
        if release.get("branch") != "BOTH":
            raise ValueError("zero-step release must authorize both fixed branches")
    else:
        branch = release.get("branch")
        if branch not in OUTPUTS or release.get("output_directory") != OUTPUTS[branch]:
            raise ValueError("formal release must identify exactly one branch and its fixed output")
    _pin(root, release, "taskbook", TASKBOOK, TASKBOOK_SHA256)
    _pin(root, release, "c5_taskbook", C5_TASKBOOK, C5_TASKBOOK_SHA256)
    _pin(root, release, "b_dataset_manifest", B_DATASET, B_DATASET_SHA256)
    _pin(root, release, "normalizer", NORMALIZER, NORMALIZER_SHA256)
    _pin(root, release, "normalizer_audit", NORMALIZER_AUDIT, NORMALIZER_AUDIT_SHA256)
    _pin(root, release, "initial_parameters", INITIAL_PARAMETERS, INITIAL_PARAMETERS_SHA256)
    if release.get("normalizer", {}).get("canonical_sha256") != CANONICAL_NORMALIZER_SHA256:
        raise ValueError("release canonical normalizer digest mismatch")
    source_hashes = _source_files(root, release)
    return {**release, "_release_path": str(release_path), "_release_sha256": release_sha.lower()}, source_hashes


def _load_shared_arrays(root: Path, numpy_model: Any, np: Any) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    norm = _load_json(_repo_path(root, NORMALIZER))
    if (norm.get("schema") != "CM18_A1T_NORMALIZER_V1" or norm.get("fit_rows") != 307200
            or norm.get("train_scenes") != 768 or norm.get("sample_indices_per_scene_zero_based") != "0,5,...,1995 (400 rows)"
            or norm.get("std_ddof") != 0 or norm.get("canonical_float64_sha256") != CANONICAL_NORMALIZER_SHA256
            or norm.get("normalizer_audit_path") != NORMALIZER_AUDIT
            or norm.get("normalizer_audit_sha256", "").lower() != NORMALIZER_AUDIT_SHA256):
        raise ValueError("A1T canonical normalizer metadata/lineage mismatch")
    mean = np.asarray(norm["input_mean_float64"], dtype=np.float64)
    std = np.asarray(norm["input_std_float64"], dtype=np.float64)
    axis = np.asarray(norm["train_axis_rms_rad_s2_float64"], dtype=np.float64)
    if (mean.shape != (18,) or std.shape != (18,) or axis.shape != (3,)
            or not np.isfinite(mean).all() or not np.isfinite(std).all() or not np.isfinite(axis).all()
            or np.any(std < 1e-6) or np.any(axis <= 0)):
        raise ValueError("shared A1T canonical normalizer arrays are invalid")
    digest = hashlib.sha256(b"".join(np.ascontiguousarray(a, dtype=np.float64).tobytes(order="C")
                                      for a in (mean, std, axis))).hexdigest()
    if digest != CANONICAL_NORMALIZER_SHA256:
        raise ValueError("canonical float64 normalizer bytes differ from the frozen digest")
    audit = _load_json(_repo_path(root, NORMALIZER_AUDIT))
    if (audit.get("schema") != "CM18_CSTAR_ALL816_INDEPENDENT_AUDIT_V1" or audit.get("status") != "PASS"
            or audit.get("canonical_normalizer_sha256", "").lower() != digest
            or audit.get("label_manifest_sha256", "").lower() != B_DATASET_SHA256
            or audit.get("scene_count") != 816 or audit.get("split_counts") != {"TRAIN": 768, "VAL": 48}):
        raise ValueError("independent canonical normalizer audit mismatch")
    with np.load(_repo_path(root, INITIAL_PARAMETERS), allow_pickle=False) as archive:
        params = {key: np.asarray(archive[key], dtype=np.float64).copy()
                  for key in ("W1", "b1", "W2", "b2", "W3", "b3")}
    expected = numpy_model.initialize_random_parameters(SEED, mean, std, axis)
    for key in params:
        if not np.array_equal(params[key], expected[key]):
            raise ValueError(f"frozen A1T initial parameters differ from seed rule: {key}")
    params.update(input_mean=mean.copy(), input_std=std.copy(), train_axis_rms_rad_s2=axis.copy())
    return params, {"mean": mean, "std": std, "axis_rms": axis}, norm


def _arrays(reader: Any, scenes: list[dict[str, Any]], np: Any) -> tuple[Any, Any, list[tuple[str, int, int]]]:
    x, y, row_map = reader.sampled_pair(scenes)
    if x.shape != (9_600, 18) or y.shape != (9_600, 3) or len(row_map) != 9_600:
        raise ValueError("paired training fit must be exactly 9600 ordered samples")
    return np.ascontiguousarray(x, dtype=np.float64), np.ascontiguousarray(y, dtype=np.float64), row_map


def _model_sources(root: Path) -> tuple[Any, Any, Any, Any]:
    return (
        _load_module(root, READER, "cm18_pair_reader_v1"),
        _load_module(root, NUMPY_MODEL, "cm18_a1_numpy_model_v1"),
        _load_module(root, TORCH_MODEL, "cm18_a1_torch_model_v1"),
        _load_module(root, B_READER, "cm18_b_cstar_reader_v1"),
    )


def _state_sha256(model: Any) -> str:
    digest = hashlib.sha256()
    for name, tensor in sorted(model.state_dict().items()):
        array = tensor.detach().cpu().contiguous().numpy()
        digest.update(name.encode("utf-8") + b"\0")
        digest.update(str(array.dtype).encode("ascii") + b"\0")
        digest.update(str(tuple(array.shape)).encode("ascii") + b"\0")
        digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def _checkpoint(torch: Any, model: Any, path: Path, step: int, kind: str) -> str:
    temp = path.with_name(path.name + ".tmp")
    torch.save({"schema": "CM18_B24_C524_CHECKPOINT_V1", "kind": kind,
                "optimizer_step": step,
                "state_dict": {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}}, temp)
    os.replace(temp, path)
    return _sha256(path)


def _sample_digest(reader: Any) -> str:
    return reader.sample_stream_sha(seed=SEED, steps=STEPS, batch_size=BATCH_SIZE, row_count=9_600)


def _normalized_ranges(x: Any, y: Any, mean: Any, std: Any, axis: Any, np: Any) -> dict[str, Any]:
    xn = (x - mean) / std
    yn = y / axis
    return {"input_min": xn.min(axis=0).tolist(), "input_max": xn.max(axis=0).tolist(),
            "target_min_normalized": yn.min(axis=0).tolist(),
            "target_max_normalized": yn.max(axis=0).tolist()}


def _verify_pair(root: Path, release: dict[str, Any], reader: Any, b_reader: Any, np: Any) -> tuple[dict, Any, Any, list, str, str]:
    pair = reader.load_pair(root, release, b_reader)
    xb, yb, rowb = _arrays(reader, pair["B24"], np)
    xc, yc, rowc = _arrays(reader, pair["C5_24"], np)
    row_hash_b = reader.canonical_row_map_sha(rowb)
    row_hash_c = reader.canonical_row_map_sha(rowc)
    if rowb != rowc or row_hash_b != row_hash_c:
        raise ValueError("B24/C5-24 ordered (scene,event ordinal,plant index) row maps differ")
    if release.get("paired_row_map_sha256", "").lower() != row_hash_b:
        raise ValueError("ROOT release ordered paired row-map SHA mismatch")
    sample_hash = _sample_digest(reader)
    if release.get("sample_index_stream_sha256", "").lower() != sample_hash:
        raise ValueError("ROOT release sample-index stream SHA mismatch")
    return pair, xb, yb, [xc, yc], row_hash_b, sample_hash


def _zero_step(root: Path, release: dict[str, Any], sources: dict[str, str]) -> dict[str, Any]:
    import numpy as np
    import torch

    reader, numpy_model, torch_model, b_reader = _model_sources(root)
    pair, xb, yb, c_data, row_sha, sample_sha = _verify_pair(root, release, reader, b_reader, np)
    xc, yc = c_data
    params, normalizer, normalizer_record = _load_shared_arrays(root, numpy_model, np)
    torch.manual_seed(SEED)
    _configure_torch_determinism(torch)
    model = torch_model.TorchCM18A1(normalizer["mean"], normalizer["std"], normalizer["axis_rms"])
    model.load_numpy_parameters(params)
    if sum(p.numel() for p in model.parameters()) != 2456:
        raise AssertionError("CM18 parameter count is not 2456")
    if any(not np.array_equal(model.numpy_parameters()[k], params[k]) for k in params):
        raise AssertionError("float64 module initialization differs from frozen A1T W/b and normalizer")
    if not torch.cuda.is_available() or torch.cuda.device_count() < 1:
        raise RuntimeError("zero-step paired check requires cuda:0, but CUDA is unavailable")
    torch.cuda.set_device(0)
    active_rows: dict[str, Any] = {}
    parity_deltas: dict[str, float] = {}
    for name, x in (("B24", xb), ("C5_24", xc)):
        active = np.flatnonzero(np.any(x[:, 7:15] != 0.0, axis=1))[:64]
        if len(active) != 64:
            raise AssertionError(f"{name} lacks 64 nonzero-morphology rows for parity/forward check")
        active_rows[name] = active
        with torch.no_grad():
            cpu_features = torch.as_tensor(x[active], dtype=torch.float64, device="cpu")
            torch_cpu_output = model(cpu_features)["physical_output_rad_s2"].numpy()
        numpy_output = numpy_model.forward(x[active], params)["physical_output_rad_s2"]
        delta = float(np.max(np.abs(numpy_output - torch_cpu_output)))
        if not np.isfinite(delta) or delta >= 1e-10:
            raise AssertionError(f"{name} float64 NumPy/Torch parity failed: {delta}")
        parity_deltas[name] = delta
    model = model.float().to(torch.device("cuda:0"))
    initial_f32 = model.numpy_parameters()
    for name, src in params.items():
        if not np.array_equal(initial_f32[name], np.asarray(src, dtype=np.float32)):
            raise AssertionError(f"float32 initial parameter/buffer cast differs: {name}")
    initial_float32_state_sha = _state_sha256(model)
    buffers = model.numpy_parameters()
    for name, src in (("input_mean", normalizer["mean"]), ("input_std", normalizer["std"]),
                      ("train_axis_rms_rad_s2", normalizer["axis_rms"])):
        if not np.array_equal(buffers[name], src.astype(np.float32)):
            raise AssertionError(f"float32 {name} buffer is not the exact canonical float32 cast")

    results = {}
    axis_t = model.train_axis_rms_rad_s2
    for name, x, y in (("B24", xb, yb), ("C5_24", xc, yc)):
        active = active_rows[name]
        features = torch.as_tensor(x[active].astype(np.float32), dtype=torch.float32, device="cuda:0")
        target = torch.as_tensor((y[active] / normalizer["axis_rms"]).astype(np.float32),
                                 dtype=torch.float32, device="cuda:0")
        model.zero_grad(set_to_none=True)
        output = model(features)["physical_output_rad_s2"]
        normalized_output = output / axis_t
        loss = torch.nn.functional.smooth_l1_loss(normalized_output, target, beta=1.0, reduction="mean")
        loss.backward()
        if (not torch.isfinite(loss).item()
                or any(p.grad is None or not torch.isfinite(p.grad).all().item() for p in model.parameters())):
            raise FloatingPointError(f"{name} CUDA forward/backward is non-finite")
        results[name] = {"loss": float(loss.detach().item()), "rows": int(len(active)),
                         "numpy_torch_float64_max_abs_delta_rad_s2": parity_deltas[name],
                         "grad_norm": float(torch.sqrt(sum((p.grad.detach() ** 2).sum() for p in model.parameters())).item())}

    zero_features = xb[0].astype(np.float32).copy()
    zero_features[7:15] = 0.0
    with torch.no_grad():
        zero_output = model(torch.as_tensor(zero_features, device="cuda:0"))["physical_output_rad_s2"]
    if not torch.equal(zero_output, torch.zeros_like(zero_output)):
        raise AssertionError("zero-basis physical output is not exactly zero")
    if (row_sha != release["paired_row_map_sha256"].lower()
            or sample_sha != release["sample_index_stream_sha256"].lower()):
        raise AssertionError("zero-step common row/sampling identity changed")
    return {
        "schema": "CM18_B24_C524_ZERO_STEP_SELF_CHECK_V1", "status": "PASS",
        "release_path": release["_release_path"], "release_sha256": release["_release_sha256"],
        "source_files": sources, "taskbook_sha256": TASKBOOK_SHA256,
        "c5_taskbook_sha256": C5_TASKBOOK_SHA256, "b_dataset_manifest_sha256": B_DATASET_SHA256,
        "ordered_scene_ids": pair["scene_ids"], "scenes_per_branch": 24,
        "fit_rows_per_branch": 9_600, "event_rows_per_scene": 1_999,
        "sample_ordinals_zero_based": "0,5,...,1995", "paired_row_map_sha256": row_sha,
        "sample_index_stream_sha256": sample_sha,
        "normalizer_source_sha256": NORMALIZER_SHA256,
        "canonical_normalizer_sha256": CANONICAL_NORMALIZER_SHA256,
        "initial_parameters_source_sha256": INITIAL_PARAMETERS_SHA256,
        "target_scale_source_scope": "A1T B TRAIN768 canonical target RMS, shared unchanged between branches",
        "E0_provenance": {"B24": "derived from stored G_column_major*cStar; B cache has no E0 field",
                          "C5_24": "stored E0_rad_s2 in audited C5 event cache"},
        "standardized_ranges": {
            "B24": _normalized_ranges(xb, yb, normalizer["mean"], normalizer["std"], normalizer["axis_rms"], np),
            "C5_24": _normalized_ranges(xc, yc, normalizer["mean"], normalizer["std"], normalizer["axis_rms"], np),
        },
        "forward_backward": results, "parameter_count": 2456,
        "initial_float32_state_sha256": initial_float32_state_sha,
        "zero_basis_output_exact_zero": True, "optimizer_steps": 0, "optimizer_step_calls": 0,
        "formal_training_started": False, "Plant_calls": 0, "TEST_accessed": False,
        "C5_VAL48_used": False, "checkpoint_selection": "none; fixed final step is the only candidate",
        "environment": {key: os.environ.get(key) for key in
                        ("MKL_THREADING_LAYER", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
                         "OPENBLAS_NUM_THREADS", "CUBLAS_WORKSPACE_CONFIG")},
    }


def _runtime_snapshot() -> dict[str, Any]:
    result: dict[str, Any] = {"device": "cuda:0", "cuda_query": None}
    exe = shutil.which("nvidia-smi")
    if exe:
        try:
            proc = subprocess.run([exe, "--query-gpu=name,utilization.gpu,memory.used,memory.total",
                                   "--format=csv,noheader,nounits"], capture_output=True, text=True,
                                  timeout=10, check=True)
            result["cuda_query"] = proc.stdout.strip()
        except Exception as exc:
            result["cuda_query_error"] = f"{type(exc).__name__}: {exc}"
    return result


def _check_budget(run_dir: Path) -> None:
    size = sum(p.stat().st_size for p in run_dir.rglob("*") if p.is_file())
    if size > MAX_OUTPUT_BYTES:
        raise RuntimeError(f"paired training output exceeds 1 GiB: {size} bytes")


def _formal_train(root: Path, release: dict[str, Any], sources: dict[str, str]) -> Path:
    import numpy as np

    root = root.resolve(strict=True)
    branch = release["branch"]
    output_rel = OUTPUTS[branch]
    output = _repo_path(root, output_rel, must_exist=False)
    if output.exists():
        raise FileExistsError(f"refusing to reuse paired training output: {output}")
    if not output.parent.is_dir():
        raise FileNotFoundError(f"paired output parent missing: {output.parent}")
    free = shutil.disk_usage(output.parent).free
    if free < MIN_FREE_BYTES:
        raise RuntimeError(f"less than 30 GiB free before training: {free} bytes")

    reader, numpy_model, torch_model, b_reader = _model_sources(root)
    pair, xb, yb, c_data, row_sha, sample_sha = _verify_pair(root, release, reader, b_reader, np)
    xc, yc = c_data
    x, y = (xb, yb) if branch == "B24" else (xc, yc)
    params, norm, norm_record = _load_shared_arrays(root, numpy_model, np)
    runtime_preflight = _runtime_snapshot()
    output.mkdir(exist_ok=False)
    receipt: dict[str, Any] = {
        "schema": "CM18_B24_C524_TRAINING_RECEIPT_V1", "status": "INITIALIZING",
        "started_at_utc": _now(), "ended_at_utc": None, "command": sys.argv,
        "branch": branch, "run_directory": output_rel, "release_path": release["_release_path"],
        "release_sha256": release["_release_sha256"], "source_files": sources,
        "paired_row_map_sha256": row_sha, "sample_index_stream_sha256_expected": sample_sha,
        "free_bytes_at_start": free, "runtime_preflight": runtime_preflight,
        "optimizer_steps_target": STEPS, "optimizer_steps_completed": 0,
        "optimizer_step_calls_attempted": 0, "active_stage": "initialize_runtime",
        "failure_reason": None, "Plant_calls": 0, "TEST_accessed": False,
        "checkpoint_selection": "fixed_final_60000_no_validation_selection",
        "B24_and_C5_24_use_same_A1T_initial_Wb_normalizer_seed_and_sample_stream": True,
        "C5_VAL48_used_for_training_or_selection": False,
        "label_semantics": "direct Cstar/beta target; not the legacy behavior-residual target",
        "B_E0_provenance": "derived as G_column_major*cStar; no stored E0 in B Cstar cache",
    }
    _write_json(output / "run_receipt.json", receipt)
    failure_step: int | None = None
    model = None
    torch = None
    try:
        import torch as torch_module
        torch = torch_module
        if not torch.cuda.is_available() or torch.cuda.device_count() < 1:
            raise RuntimeError("paired formal training requires CUDA device cuda:0")
        torch.cuda.set_device(0)
        _configure_torch_determinism(torch)
        random.seed(SEED)
        torch.manual_seed(SEED)
        torch.cuda.manual_seed_all(SEED)

        model = torch_model.TorchCM18A1(norm["mean"], norm["std"], norm["axis_rms"])
        model.load_numpy_parameters(params)
        if any(not np.array_equal(model.numpy_parameters()[k], params[k]) for k in params):
            raise AssertionError("double initialization differs from shared A1T initial W/b and normalizer")
        model = model.float().to(torch.device("cuda:0"))
        initial_f32 = model.numpy_parameters()
        for name, src in params.items():
            if not np.array_equal(initial_f32[name], np.asarray(src, dtype=np.float32)):
                raise AssertionError(f"float32 initial parameter/buffer is not exact canonical cast: {name}")
        initial_f32_sha = _state_sha256(model)
        init_sha = _checkpoint(torch, model, output / "initial.pt", 0, "initial")
        receipt["active_stage"] = "train"
        receipt["runtime"] = {"python": sys.version, "numpy": np.__version__, "torch": torch.__version__,
                              "cuda_runtime": torch.version.cuda, "gpu_name": torch.cuda.get_device_name(0),
                              "device": "cuda:0", "dtype": "float32", "amp": False,
                              "tf32": False, "deterministic_algorithms": True}
        receipt["initial_checkpoint_sha256"] = init_sha
        receipt["initial_float32_state_sha256"] = initial_f32_sha
        receipt["status"] = "RUNNING"
        _write_json(output / "run_receipt.json", receipt)
        _write_json(output / "training_config.json", {
            "schema": "CM18_B24_C524_TRAINING_CONFIG_V1", "branch": branch,
            "seed": SEED, "optimizer_steps": STEPS, "batch_size": BATCH_SIZE,
            "optimizer": {"name": "Adam", "lr": 0.001, "betas": [0.9, 0.999],
                          "eps": 1e-8, "weight_decay": 1e-5},
            "loss": "SmoothL1(beta=1.0), mean over batch and 3 axes; output/target normalized by shared A1T axis RMS",
            "sampling": "NumPy default_rng(seed); uniform with replacement over 9600 ordered rows",
            "selection": "none; only fixed final step 60000 is retained",
            "scene_count": 24, "fit_rows": 9600, "paired_row_map_sha256": row_sha,
            "sample_index_stream_sha256": sample_sha,
            "normalizer_sha256": NORMALIZER_SHA256,
            "canonical_normalizer_sha256": CANONICAL_NORMALIZER_SHA256,
            "initial_parameters_sha256": INITIAL_PARAMETERS_SHA256,
            "standardized_ranges": _normalized_ranges(x, y, norm["mean"], norm["std"], norm["axis_rms"], np),
            "target_scale_source": "A1T B TRAIN768 canonical target RMS; shared for both branches",
            "E0_note": "B24 E0 is derived from G*cStar and is not a stored B cache field",
        })
        device = torch.device("cuda:0")
        train_x = torch.as_tensor(np.ascontiguousarray(x, dtype=np.float32), dtype=torch.float32, device=device)
        train_y = torch.as_tensor(np.ascontiguousarray(y / norm["axis_rms"], dtype=np.float32),
                                   dtype=torch.float32, device=device)
        axis = torch.as_tensor(norm["axis_rms"].astype(np.float32), dtype=torch.float32, device=device)
        optimizer = torch.optim.Adam(model.parameters(), lr=0.001, betas=(0.9, 0.999),
                                     eps=1e-8, weight_decay=1e-5)
        rng = np.random.default_rng(SEED)
        digest = hashlib.sha256()
        model.train()
        started = time.perf_counter()
        for step in range(1, STEPS + 1):
            failure_step = step
            sample = rng.integers(0, len(train_x), size=BATCH_SIZE, dtype=np.int64)
            digest.update(np.asarray(sample, dtype="<i8").tobytes(order="C"))
            indices = torch.as_tensor(sample, dtype=torch.long, device=device)
            optimizer.zero_grad(set_to_none=True)
            prediction = model(train_x[indices])["physical_output_rad_s2"] / axis
            loss = torch.nn.functional.smooth_l1_loss(prediction, train_y[indices], beta=1.0, reduction="mean")
            loss_value = float(loss.detach().item())
            if not math.isfinite(loss_value):
                raise FloatingPointError(f"non-finite loss at step {step}")
            loss.backward()
            for name, parameter in model.named_parameters():
                if parameter.grad is None or not torch.isfinite(parameter.grad).all().item():
                    raise FloatingPointError(f"missing/non-finite gradient {name} at step {step}")
                if not torch.isfinite(parameter).all().item():
                    raise FloatingPointError(f"non-finite parameter before step {step}: {name}")
            receipt["optimizer_step_calls_attempted"] = step
            optimizer.step()
            receipt["optimizer_steps_completed"] = step
            if any(not torch.isfinite(parameter).all().item() for parameter in model.parameters()):
                raise FloatingPointError(f"non-finite parameter after step {step}")
            if step % PROGRESS_EVERY == 0:
                receipt["status"] = "RUNNING"
                _write_json(output / "progress.json", {
                    "optimizer_steps_completed": step, "optimizer_steps_target": STEPS,
                    "latest_loss": loss_value, "sample_index_stream_sha256_so_far": digest.hexdigest(),
                    "elapsed_s": time.perf_counter() - started, "updated_at_utc": _now(),
                })
                _append_jsonl(output / "train_loss.jsonl", {"optimizer_step": step, "loss": loss_value})
                _write_json(output / "run_receipt.json", receipt)
                _check_budget(output)

        failure_step = None
        stream_sha = digest.hexdigest()
        if stream_sha != release["sample_index_stream_sha256"].lower():
            raise AssertionError("actual branch sample-index stream differs from the pinned common stream")
        final_sha = _checkpoint(torch, model, output / "final.pt", STEPS, "final")
        receipt.update({"status": "COMPLETED", "ended_at_utc": _now(), "active_stage": None,
                        "optimizer_steps_completed": STEPS, "optimizer_step_calls_attempted": STEPS,
                        "sample_index_stream_sha256_actual": stream_sha,
                        "final_checkpoint_sha256": final_sha, "final_float32_state_sha256": _state_sha256(model),
                        "elapsed_s": time.perf_counter() - started, "candidate_frozen": True})
        _write_json(output / "run_receipt.json", receipt)
        _check_budget(output)
        return output
    except BaseException as exc:
        if model is not None:
            try:
                _checkpoint(torch, model, output / "failure_state.pt",
                            int(receipt.get("optimizer_steps_completed", 0)), "failure_state")
            except BaseException:
                pass
        receipt.update({"status": "FAILED", "ended_at_utc": _now(),
                        "active_stage": None, "failure_step": failure_step,
                        "failure_reason": f"{type(exc).__name__}: {exc}",
                        "traceback": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))})
        try:
            _write_json(output / "run_receipt.json", receipt)
        except BaseException:
            pass
        raise


def _synthetic_check() -> None:
    import numpy as np

    from read_b24_c524_paired_v1 import canonical_row_map_sha, sample_stream_sha

    row_map = [(f"S{i // 400:02d}", i % 400 * 5, 11 + i % 400 * 50) for i in range(9_600)]
    if len(row_map) != 9_600 or canonical_row_map_sha(row_map) != canonical_row_map_sha(list(row_map)):
        raise AssertionError("synthetic ordered row-map digest is unstable")
    if sample_stream_sha(steps=16) != sample_stream_sha(steps=16):
        raise AssertionError("synthetic RNG stream digest is unstable")
    g = np.asarray([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0], [7.0, 8.0, 9.0]])
    flat_col = g.reshape(9, order="F")
    decoded = flat_col.reshape(1, 3, 3).transpose(0, 2, 1)[0]
    if not np.array_equal(decoded, g):
        raise AssertionError("B column-major G decode is incorrect")
    print("SELF_CHECK=PASS synthetic_rowmap=9600 sample_rng=16_steps B_G_column_major=PASS; no dataset/optimizer/GPU/Plant")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--synthetic-check", action="store_true")
    parser.add_argument("--release", type=Path)
    parser.add_argument("--release-sha256")
    args = parser.parse_args()
    root = args.repo_root.resolve(strict=True)
    if args.synthetic_check:
        if args.self_check or args.release or args.release_sha256:
            parser.error("--synthetic-check is separate from release-driven checks")
        _synthetic_check()
        return
    if args.release is None or args.release_sha256 is None:
        parser.error("an actual ROOT release path and SHA256 are required")
    purpose = "self-check" if args.self_check else "training"
    release, sources = _check_release(root, args.release, args.release_sha256, purpose)
    if args.self_check:
        result = _zero_step(root, release, sources)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return
    output = _formal_train(root, release, sources)
    print(json.dumps({"status": "COMPLETED", "branch": release["branch"],
                      "run_directory": str(output), "optimizer_steps": STEPS}, indent=2))


if __name__ == "__main__":
    main()
