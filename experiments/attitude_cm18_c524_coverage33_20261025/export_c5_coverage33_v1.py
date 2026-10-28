"""Export only the frozen C5_COVERAGE33 final checkpoint for MATLAB deployment."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch
from scipy.io import savemat


ROOT = Path(__file__).resolve().parents[2]
EXP_REL = "experiments/attitude_cm18_c524_coverage33_20261025"
TRAINING_REL = f"{EXP_REL}/training_C5_COVERAGE33_v1"
RELEASE_REL = "reports/attitude_cm18_c524_coverage33_20261025/C5_COVERAGE33_TRAINING_RELEASE_v1.json"
TASKBOOK_REL = "reports/attitude_cm18_c524_screen12_20261025/C524_COVERAGE33_TASKBOOK_v2_ZH.md"
TASKBOOK_SHA = "934fc1b8a614c5a32993add65a0aee89d48e7c31ea368646063e5576b78c7017"
MANIFEST_REL = f"{EXP_REL}/data/C524_COVERAGE33_RELABEL_MANIFEST_v1.json"
MANIFEST_SHA = "7d6a7d079d32120849cee62eadecd8e69a68d5a538608dd8959849ac5fe2dd8c"
NORMALIZER_REL = "experiments/attitude_cm18_datarepair_20261024/training_a1t_v1/normalizer.json"
CANONICAL_NORMALIZER_SHA = "12c864b9c2404235e0ea3f313bb0801a99902eca7cfdfbf43f0d8d584d5d609a"
MAPPER_REL = "experiments/attitude_cm18_c524_screen12_20261025/export_c524_models_v1.py"
MAPPER_SHA = "c25e6ed5fcc41e28e22e5dc18950ad5b89480efef5e5cef63ed8d2d3a6455d73"
HELPER_REL = "experiments/attitude_cm18_a1_20261024/matlab/cm18_a1_forward_v1.m"
HELPER_SHA = "1ff450f9be6a5c16fe98cb4f169ef9930f1b806fecfc10ad664c11ce940f42e9"
CHECKER_REL = f"{EXP_REL}/check_c5_coverage33_matlab_parity_v1.m"
MODEL_REL = f"{EXP_REL}/models/C5_COVERAGE33_model.mat"
FIXTURE_REL = f"{EXP_REL}/models/matlab_parity_fixture.mat"
EXPORT_RECEIPT_REL = f"{EXP_REL}/models/export_receipt.json"
OUTPUT_REL = f"{EXP_REL}/models"
EXPECTED_ARCH = "CM18-A1 18-32-32-24 tanh/bilinear"
EXPECTED_PARAMETER_COUNT = 2456
EXPECTED_TRAINING = {
    "seed": 2026102001, "steps": 60000, "batch_size": 512, "optimizer": "Adam",
    "lr": 0.001, "betas": [0.9, 0.999], "eps": 1e-8, "weight_decay": 1e-5,
    "loss": "SmoothL1 beta=1; mean over normalized three-axis output",
}
EXPECTED_STATE_SHAPES = {
    "fc1.weight": (32, 18), "fc1.bias": (32,),
    "fc2.weight": (32, 32), "fc2.bias": (32,),
    "fc3.weight": (24, 32), "fc3.bias": (24,),
    "input_mean": (18,), "input_std": (18,), "train_axis_rms_rad_s2": (3,),
}


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _repo_file(relative: str) -> Path:
    base = ROOT.resolve(strict=True)
    path = (base / relative).resolve(strict=True)
    path.relative_to(base)
    return path


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    _expect(isinstance(value, dict), f"expected JSON object: {path}")
    return value


def _load_mapper() -> Any:
    path = _repo_file(MAPPER_REL)
    _expect(_sha(path) == MAPPER_SHA, "the pinned generic CM18 exporter changed")
    spec = importlib.util.spec_from_file_location("coverage33_cm18_export_mapping", path)
    _expect(spec is not None and spec.loader is not None, "cannot load generic CM18 mapping")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _state_sha(state: dict[str, Any]) -> str:
    h = hashlib.sha256()
    for name in sorted(state):
        tensor = state[name]
        _expect(torch.is_tensor(tensor), f"checkpoint state entry is not a tensor: {name}")
        array = tensor.detach().cpu().contiguous().numpy()
        h.update(name.encode("utf-8") + b"\0" + str(array.dtype).encode("ascii") + b"\0")
        h.update(str(tuple(array.shape)).encode("ascii") + b"\0" + array.tobytes(order="C"))
    return h.hexdigest()


def _validate_release(release: dict[str, Any], release_sha: str, receipt: dict[str, Any],
                      checkpoint_path: Path, checkpoint_sha: str) -> dict[str, Any]:
    _expect(release.get("schema") == "CM18_C5_COVERAGE33_TRAINING_RELEASE_V1"
            and release.get("decision") == "APPROVE_ONE_MODEL_TRAINING"
            and release.get("output_directory") == TRAINING_REL
            and release.get("train_scene_count") == 33 and release.get("fit_rows") == 13200
            and release.get("TEST_accessed") is False and release.get("C5_VAL48_accessed") is False
            and release.get("holdout_or_validation_used_for_training_or_selection") is False,
            "training release schema, scope, or output path is not the frozen C5_COVERAGE33 release")
    _expect(release.get("training") == EXPECTED_TRAINING,
            "training release does not pin the 60,000-step C5_COVERAGE33 training configuration")
    model = release.get("model", {})
    self_check = release.get("self_check", {})
    initial_sha = str(model.get("initial_float32_state_sha256", "")).lower()
    _expect(model.get("architecture") == EXPECTED_ARCH
            and model.get("parameter_count") == EXPECTED_PARAMETER_COUNT
            and re.fullmatch(r"[0-9a-f]{64}", initial_sha) is not None
            and self_check.get("status") == "PASS"
            and self_check.get("zero_basis_exact_zero") is True
            and self_check.get("Plant_calls") == 0
            and self_check.get("TEST_accessed") is False
            and self_check.get("initial_float32_state_sha256", "").lower() == initial_sha,
            "training release architecture, initial model identity, or zero-step self-check is invalid")

    _expect(release.get("taskbook", {}).get("path") == TASKBOOK_REL
            and release.get("taskbook", {}).get("sha256", "").lower() == TASKBOOK_SHA
            and _sha(_repo_file(TASKBOOK_REL)) == TASKBOOK_SHA,
            "training release taskbook identity is invalid")
    _expect(release.get("relabel_manifest", {}).get("path") == MANIFEST_REL
            and release.get("relabel_manifest", {}).get("sha256", "").lower() == MANIFEST_SHA
            and _sha(_repo_file(MANIFEST_REL)) == MANIFEST_SHA,
            "training release relabel manifest identity is invalid")

    normalizer_ref = release.get("normalizer", {})
    _expect(normalizer_ref.get("path") == NORMALIZER_REL
            and normalizer_ref.get("canonical_sha256", "").lower() == CANONICAL_NORMALIZER_SHA,
            "training release normalizer reference is invalid")
    normalizer_path = _repo_file(NORMALIZER_REL)
    _expect(_sha(normalizer_path) == normalizer_ref.get("sha256", "").lower(),
            "training normalizer SHA differs from the training release")
    norm = _json(normalizer_path)

    source_files = release.get("source_files", {})
    _expect(isinstance(source_files, dict) and set(source_files) == {
        "experiments/attitude_cm18_c524_coverage33_20261025/train_c5_coverage33_v1.py",
        "experiments/attitude_position_context_probe_20261024/b24_c524_paired_v1/train_cm18_b24_c524_paired_v1.py",
        "experiments/attitude_position_context_probe_20261024/b24_c524_paired_v1/read_b24_c524_paired_v1.py",
        "experiments/attitude_cm18_a1_20261024/model_cm18_v1.py",
        "experiments/attitude_cm18_a1_20261024/torch_model_cm18_v1.py",
    }, "training release source list differs from the frozen C5_COVERAGE33 allowlist")
    for relative, expected_sha in source_files.items():
        _expect(_sha(_repo_file(relative)) == str(expected_sha).lower(),
                f"training source changed since release: {relative}")

    _expect(receipt.get("schema") == "CM18_C5_COVERAGE33_TRAINING_RECEIPT_V1"
            and receipt.get("status") == "COMPLETED"
            and receipt.get("candidate_frozen") is True
            and receipt.get("optimizer_steps_target") == 60000
            and receipt.get("optimizer_steps_completed") == 60000
            and receipt.get("optimizer_step_calls_attempted") == 60000
            and receipt.get("fit_rows") == 13200
            and receipt.get("TEST_accessed") is False
            and receipt.get("C5_VAL48_accessed") is False
            and receipt.get("Plant_calls") == 0
            and receipt.get("holdout_used_for_training_or_selection") is False
            and receipt.get("release_sha256", "").lower() == release_sha
            and receipt.get("training_source_sha256") == source_files
            and receipt.get("initial_float32_state_sha256", "").lower() == initial_sha
            and receipt.get("sample_index_stream_sha256_expected") == release.get("sample_index_stream_sha256")
            and receipt.get("sample_index_stream_sha256_actual") == release.get("sample_index_stream_sha256"),
            "training receipt is not a completed, frozen, release-matched 60,000-step run")
    _expect(receipt.get("final_checkpoint_sha256", "").lower() == checkpoint_sha
            and _sha(checkpoint_path) == checkpoint_sha,
            "final checkpoint SHA does not match both the external pin and training receipt")
    _expect(receipt.get("final_float32_state_sha256", "").lower() != "",
            "training receipt lacks the frozen final float32 state SHA")
    return {"normalizer": norm, "initial_float32_state_sha256": initial_sha}


def _load_checkpoint(path: Path, receipt: dict[str, Any],
                     norm: dict[str, Any], initial_sha: str) -> tuple[dict[str, Any], str]:
    checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    _expect(isinstance(checkpoint, dict)
            and checkpoint.get("schema") == "CM18_C5_COVERAGE33_CHECKPOINT_V1"
            and checkpoint.get("kind") == "final"
            and checkpoint.get("optimizer_step") == 60000
            and set(checkpoint) == {"schema", "kind", "optimizer_step", "state_dict"},
            "checkpoint schema/kind/step is not the frozen final C5_COVERAGE33 checkpoint")
    state = checkpoint.get("state_dict")
    _expect(isinstance(state, dict) and set(state) == set(EXPECTED_STATE_SHAPES),
            "checkpoint state dictionary does not match CM18-A1 architecture")
    for name, shape in EXPECTED_STATE_SHAPES.items():
        tensor = state[name]
        _expect(torch.is_tensor(tensor) and tuple(tensor.shape) == shape and tensor.dtype == torch.float32
                and bool(torch.isfinite(tensor).all()), f"invalid checkpoint state tensor: {name}")

    learned_count = sum(state[name].numel() for name in (
        "fc1.weight", "fc1.bias", "fc2.weight", "fc2.bias", "fc3.weight", "fc3.bias"))
    _expect(learned_count == EXPECTED_PARAMETER_COUNT, "checkpoint parameter count differs from release")
    for name, normalizer_key in (("input_mean", "input_mean_float64"),
                                 ("input_std", "input_std_float64"),
                                 ("train_axis_rms_rad_s2", "train_axis_rms_rad_s2_float64")):
        expected = np.asarray(norm[normalizer_key], dtype=np.float32)
        _expect(np.array_equal(state[name].numpy(), expected),
                f"checkpoint normalization buffer differs from frozen initial model: {name}")
    _expect(bool(torch.all(state["input_std"] >= 1e-6))
            and bool(torch.all(state["train_axis_rms_rad_s2"] > 0)),
            "checkpoint contains invalid normalization scales")
    final_state_sha = _state_sha(state)
    _expect(final_state_sha == receipt.get("final_float32_state_sha256", "").lower(),
            "checkpoint weights differ from the completed training receipt")
    _expect(receipt.get("initial_float32_state_sha256", "").lower() == initial_sha,
            "training receipt initial model SHA differs from its frozen release")
    return state, final_state_sha


def _new_write(path: Path, payload: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-sha256", required=True, help="externally verified frozen training-release SHA-256")
    parser.add_argument("--checkpoint-sha256", required=True, help="externally verified final.pt SHA-256")
    args = parser.parse_args()
    release_sha = args.release_sha256.lower()
    checkpoint_sha = args.checkpoint_sha256.lower()
    _expect(re.fullmatch(r"[0-9a-f]{64}", release_sha) is not None
            and re.fullmatch(r"[0-9a-f]{64}", checkpoint_sha) is not None,
            "release and checkpoint SHA-256 values must be 64 hexadecimal characters")

    release_path = _repo_file(RELEASE_REL)
    checkpoint_path = _repo_file(f"{TRAINING_REL}/final.pt")
    training_receipt_path = _repo_file(f"{TRAINING_REL}/run_receipt.json")
    output_dir = ROOT / OUTPUT_REL
    _expect(not output_dir.exists(), "refusing to overwrite existing official models directory")
    _expect(_sha(release_path) == release_sha, "training release differs from the external SHA-256 pin")
    receipt = _json(training_receipt_path)
    validated = _validate_release(_json(release_path), release_sha, receipt, checkpoint_path, checkpoint_sha)
    state, final_state_sha = _load_checkpoint(
        checkpoint_path, receipt, validated["normalizer"],
        validated["initial_float32_state_sha256"])

    mapper_path = _repo_file(MAPPER_REL)
    mapper = _load_mapper()
    helper_path = _repo_file(HELPER_REL)
    checker_path = _repo_file(CHECKER_REL)
    _expect(_sha(helper_path) == HELPER_SHA, "deployed MATLAB CM18 forward helper differs from frozen identity")
    params = mapper.parameters(state, validated["normalizer"])
    rng = np.random.default_rng(20261025)
    probe = rng.normal(size=(64, 18)).astype(np.float64)
    probe[0, 7:15] = 0.0
    expected = mapper.forward(probe, params)
    _expect(expected.shape == (64, 3) and np.isfinite(expected).all()
            and np.array_equal(expected[0], np.zeros(3, dtype=np.float64)),
            "Python reference vector or exact zero-morphology constraint failed")

    model_buffer = io.BytesIO()
    savemat(model_buffer, {"model": params}, do_compression=True, long_field_names=True, oned_as="row")
    fixture_buffer = io.BytesIO()
    savemat(fixture_buffer, {"X18": probe, "C5_COVERAGE33_expected": expected,
                             "zero_basis_rows": np.asarray([1], dtype=np.int32)},
            do_compression=True, long_field_names=True, oned_as="row")
    model_bytes, fixture_bytes = model_buffer.getvalue(), fixture_buffer.getvalue()

    receipt_out = {
        "schema": "CM18_C5_COVERAGE33_EXPORT_V1", "status": "PASS",
        "candidate_id": "C5_COVERAGE33", "model_id": "C5_COVERAGE33",
        "training_release_path": RELEASE_REL, "training_release_sha256": release_sha,
        "training_receipt_path": f"{TRAINING_REL}/run_receipt.json",
        "training_receipt_sha256": _sha(training_receipt_path),
        "checkpoint_path": f"{TRAINING_REL}/final.pt", "checkpoint_sha256": checkpoint_sha,
        "model_mat_path": MODEL_REL, "model_mat_sha256": _sha_bytes(model_bytes),
        "architecture": EXPECTED_ARCH, "parameter_count": EXPECTED_PARAMETER_COUNT,
        "initial_float32_state_sha256": validated["initial_float32_state_sha256"],
        "final_float32_state_sha256": final_state_sha,
        "normalizer_path": NORMALIZER_REL, "normalizer_sha256": _sha(_repo_file(NORMALIZER_REL)),
        "generic_mapper_path": MAPPER_REL, "generic_mapper_sha256": _sha(mapper_path),
        "exporter_path": f"{EXP_REL}/export_c5_coverage33_v1.py",
        "exporter_sha256": _sha(Path(__file__).resolve()),
        "parity_checker_path": CHECKER_REL, "parity_checker_sha256": _sha(checker_path),
        "matlab_helper_path": HELPER_REL, "matlab_helper_sha256": _sha(helper_path),
        "matlab_parameter_order": "CM18-A1 forward v1; fc3 flat outputs reshape as 3x8 row-major coefficients",
        "fixture_path": FIXTURE_REL, "fixture_sha256": _sha_bytes(fixture_bytes),
        "fixture_rows": int(probe.shape[0]), "zero_basis_rows_matlab_1based": [1],
        "zero_basis_exact_zero": True,
        "python_reference_max_abs_by_axis_rad_s2": np.max(np.abs(expected), axis=0).tolist(),
        "plant_calls": 0, "training_steps": 60000, "optimizer_steps": 60000,
        "TEST_accessed": False,
        "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
    }
    receipt_bytes = (json.dumps(receipt_out, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    experiment_dir = _repo_file(EXP_REL)
    with tempfile.TemporaryDirectory(prefix=".C5_COVERAGE33_models_tmp_", dir=experiment_dir) as temp_name:
        staging_dir = Path(temp_name)
        _new_write(staging_dir / "C5_COVERAGE33_model.mat", model_bytes)
        _new_write(staging_dir / "matlab_parity_fixture.mat", fixture_bytes)
        _new_write(staging_dir / "export_receipt.json", receipt_bytes)
        _expect(not output_dir.exists(), "models directory appeared during export; refusing publication")
        os.rename(staging_dir, output_dir)
    print(json.dumps({"status": "PASS", "candidate_id": "C5_COVERAGE33",
                      "checkpoint_sha256": checkpoint_sha, "model_mat_sha256": receipt_out["model_mat_sha256"],
                      "fixture_sha256": receipt_out["fixture_sha256"],
                      "export_receipt_path": EXPORT_RECEIPT_REL}, ensure_ascii=False))


if __name__ == "__main__":
    main()
