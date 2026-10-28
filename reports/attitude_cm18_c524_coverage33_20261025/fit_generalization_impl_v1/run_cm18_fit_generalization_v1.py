"""Offline, fail-closed CM18 fit/generalization diagnostic for C5_COVERAGE33."""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import re
import shutil
import stat
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
TASKBOOK_REL = "reports/attitude_cm18_c524_coverage33_20261025/C5_CM18_FIT_GENERALIZATION_TASKBOOK_v1_ZH.md"
RELEASE_REL = "reports/attitude_cm18_c524_coverage33_20261025/C5_COVERAGE33_TRAINING_RELEASE_v1.json"
MANIFEST_REL = "experiments/attitude_cm18_c524_coverage33_20261025/data/C524_COVERAGE33_RELABEL_MANIFEST_v1.json"
BINDING_REL = "experiments/attitude_cm18_c524_coverage33_20261025/C5_COVERAGE33_CLOSED_LOOP_BINDING_v3.json"
NORMALIZER_REL = "experiments/attitude_cm18_datarepair_20261024/training_a1t_v1/normalizer.json"
CHECKPOINT_REL = "experiments/attitude_cm18_c524_coverage33_20261025/training_C5_COVERAGE33_v1/final.pt"
MODEL_REL = "experiments/attitude_cm18_c524_coverage33_20261025/models/C5_COVERAGE33_model.mat"
RESULT_REPORT_REL = "reports/attitude_cm18_c524_coverage33_20261025/C5_COVERAGE33_15SCENE_CLOSED_LOOP_RESULT_v1_ZH.md"
AUDIT_DIR_REL = "reports/attitude_cm18_c524_coverage33_20261025/scene_audits"
OUTPUT_REL = "reports/attitude_cm18_c524_coverage33_20261025/fit_generalization_v1"
IMPL_REL = "reports/attitude_cm18_c524_coverage33_20261025/fit_generalization_impl_v1"
SCRIPT_REL = f"{IMPL_REL}/run_cm18_fit_generalization_v1.py"
ALLOWLIST_REL = f"{IMPL_REL}/IMPLEMENTATION_ALLOWLIST_v1.json"
MAPPER_REL = "experiments/attitude_cm18_c524_screen12_20261025/export_c524_models_v1.py"
NUMPY_MODEL_REL = "experiments/attitude_cm18_a1_20261024/model_cm18_v1.py"
TRAINER_REL = "experiments/attitude_cm18_c524_coverage33_20261025/train_c5_coverage33_v1.py"
PAIRED_TRAINER_REL = "experiments/attitude_position_context_probe_20261024/b24_c524_paired_v1/train_cm18_b24_c524_paired_v1.py"
READER_REL = "experiments/attitude_position_context_probe_20261024/b24_c524_paired_v1/read_b24_c524_paired_v1.py"
TORCH_MODEL_REL = "experiments/attitude_cm18_a1_20261024/torch_model_cm18_v1.py"

EXPECTED_FILES: dict[str, str] = {
    TASKBOOK_REL: "e0e274a2c12a038001a5b2bfe77ada944ed32c9a48c105933c97cdf5456c41ca",
    RELEASE_REL: "02f23f05b2fa20d5026e2dee1d4c77daa2572b34b3d95059f08c009315e7f803",
    MANIFEST_REL: "7d6a7d079d32120849cee62eadecd8e69a68d5a538608dd8959849ac5fe2dd8c",
    BINDING_REL: "87ac859a29488d66f87330a7f0060183fb9a3e07178244677db28cbd8a527ee8",
    NORMALIZER_REL: "23e8432f4a1c3f71bfaaa4e3a7b07c4b9f6b0201842e35ba3bcb032ac61fd781",
    CHECKPOINT_REL: "960ef67b7dd2ac1d2d1bca5d13e818674b2f14357d85ae6035590914c250cb07",
    MODEL_REL: "66f8053782e7afb823afa24368cea8002b55b536a587a8e8b13dbb9e13cf3142",
    RESULT_REPORT_REL: "41c38fe91ff121be1853826db94e830ad4c3a76ebee8623bcab0de5cd6a2a3c3",
    TRAINER_REL: "53e23f688633e95e4e8386e186dcba4cbb166cc3a4a1acaa542e84eaea337fc3",
    PAIRED_TRAINER_REL: "8e3a1155661d58456f8c4e3d5adeb72ddcd9b1d96d5ff358b68fdd97c7ecf70b",
    READER_REL: "18453497548f39be472bfc197360d1bb86dedf14ae76e5a7cce31261c83fa8bd",
    NUMPY_MODEL_REL: "ad32c4f97bf96c63172547c944d80c45062502f1062b774934e0f7a868720cf6",
    TORCH_MODEL_REL: "bc9fe34fe957cb624438eeccfdfe2ddd38ad40cc9a4e706ce58863c9271d5aa0",
    MAPPER_REL: "c25e6ed5fcc41e28e22e5dc18950ad5b89480efef5e5cef63ed8d2d3a6455d73",
    f"{AUDIT_DIR_REL}/DL1018_DEV_T2_C02_W15_C5_COVERAGE33_AUDIT_v1.json": "24522cf3f746fdaa694ad3429f2ee57f4b51a1f6947c66fe007494f7d4520e96",
    f"{AUDIT_DIR_REL}/DL1018_DEV_T3_C03_W15_C5_COVERAGE33_AUDIT_v1.json": "7ce85c16e6730ab52f9af068d3ddab9edd7fda81f7c8164158376819ddea88cf",
    f"{AUDIT_DIR_REL}/DL1018_DEV_T1_C04_W00_C5_COVERAGE33_AUDIT_v1.json": "8c8f0c123446be3cb42bf3169742abaa681b086f1cdbcd09ea346c793882cff1",
    f"{AUDIT_DIR_REL}/DL1018_DEV_T1_C07_W08_C5_COVERAGE33_AUDIT_v1.json": "1fac3c42cbdc9d53e701440336d7fc3d3b92fa5b8092f115f9236553aad09329",
    f"{AUDIT_DIR_REL}/DL1018_DEV_T1_C10_W09_C5_COVERAGE33_AUDIT_v1.json": "5220182cc3792b7c6267ca66894c81c2eb28b11a5bf726793453231050737b0c",
    f"{AUDIT_DIR_REL}/DL1018_DEV_T1_C11_W12_C5_COVERAGE33_AUDIT_v1.json": "b8189068a8541be8e19794a236fd6d4b144060be3ff6ef40d3b93af1fb30c507",
    f"{AUDIT_DIR_REL}/DL1018_DEV_T2_C03_W01_C5_COVERAGE33_AUDIT_v1.json": "bad8bcb937b8e1f4b17828a60c47e60d9810f47fc303fcb3b3634381241fd8d4",
    f"{AUDIT_DIR_REL}/DL1018_DEV_T2_C08_W08_C5_COVERAGE33_AUDIT_v1.json": "3699c5953e796998baaa9edb9d884862b0b847c4bc40a9f9eeb44baa45ad7753",
    f"{AUDIT_DIR_REL}/DL1018_DEV_T2_C09_W10_C5_COVERAGE33_AUDIT_v1.json": "ac4d8070d09bcb37b99e0b6562266933e5c0319f7ba40ac3533675949fd49e75",
    f"{AUDIT_DIR_REL}/DL1018_DEV_T2_C12_W13_C5_COVERAGE33_AUDIT_v1.json": "5ebfce84e5d9281e729f3423e5928f21a1deb0082fc572a8cc829f1645e69c8b",
    f"{AUDIT_DIR_REL}/DL1018_DEV_T2_C14_W14_C5_COVERAGE33_AUDIT_v1.json": "1553202ce39718f492e69d5e854830ec8c031d2b17f01f195b4d4f0ecc667cac",
    f"{AUDIT_DIR_REL}/DL1018_DEV_T3_C06_W08_C5_COVERAGE33_AUDIT_v1.json": "5384c0d503699833a1f50ac14e01e3958e2944647653f9aeea5b3b1c2d6adb8c",
    f"{AUDIT_DIR_REL}/DL1018_DEV_T3_C09_W09_C5_COVERAGE33_AUDIT_v1.json": "3528287294906f477dc7e1cd4d34d1b0af0d7218bc235555ced7891a0fd33b36",
    f"{AUDIT_DIR_REL}/DL1018_DEV_T3_C10_W11_C5_COVERAGE33_AUDIT_v1.json": "2d58ea567df4b151941c53ab14c41ff6eede1d4a68ed067642ecefd663258516",
    f"{AUDIT_DIR_REL}/DL1018_DEV_T3_C13_W12_C5_COVERAGE33_AUDIT_v1.json": "77229798617241cc50fb48238507d3308afc3882783ccc6cb71c23c1e90f4b83",
}

RUNTIME_PACKAGES = {
    "numpy": {"version": "1.26.4", "record_sha256": "d58d7a0b758d026db1c63165604e220d4531697fbf3419712b8c71106deb5522"},
    "h5py": {"version": "3.11.0", "record_sha256": "d1dd580e8e607799826ab35ce66899f24e2604d170969fceea9eefa2abec6207"},
    "torch": {"version": "2.6.0+cu124", "record_sha256": "575502ebf002f5942bf952418545b410c21d92a7efec60c8933de74ef3c0968b"},
    "scipy": {"version": "1.13.1", "record_sha256": "35b1e40609c6a73d71ef165e121b680150c7028ca1ce74c74df2027a17eb9895"},
}

EXPECTED_TRAIN24 = [
    "DL1018_TRAIN_T1_C00_W00", "DL1018_TRAIN_T1_C00_W09", "DL1018_TRAIN_T1_C00_W12", "DL1018_TRAIN_T1_C00_W15",
    "DL1018_TRAIN_T1_C15_W00", "DL1018_TRAIN_T1_C15_W09", "DL1018_TRAIN_T1_C15_W12", "DL1018_TRAIN_T1_C15_W15",
    "DL1018_TRAIN_T2_C00_W00", "DL1018_TRAIN_T2_C00_W09", "DL1018_TRAIN_T2_C00_W12", "DL1018_TRAIN_T2_C00_W15",
    "DL1018_TRAIN_T2_C15_W00", "DL1018_TRAIN_T2_C15_W09", "DL1018_TRAIN_T2_C15_W12", "DL1018_TRAIN_T2_C15_W15",
    "DL1018_TRAIN_T3_C00_W00", "DL1018_TRAIN_T3_C00_W09", "DL1018_TRAIN_T3_C00_W12", "DL1018_TRAIN_T3_C00_W15",
    "DL1018_TRAIN_T3_C15_W00", "DL1018_TRAIN_T3_C15_W09", "DL1018_TRAIN_T3_C15_W12", "DL1018_TRAIN_T3_C15_W15",
]
TRAIN24_RUNTIME_SCENE_IDS = {
    sid: sid + ("_ACC_FIX_V1" if "_T2_" in sid else "") for sid in EXPECTED_TRAIN24
}
EXPECTED_EXTRA = [
    "DL1018_DEV_T1_C01_W15", "DL1018_DEV_T1_C00_W03", "DL1018_DEV_T1_C15_W14",
    "DL1018_DEV_T1_C05_W06", "DL1018_DEV_T2_C00_W04", "DL1018_DEV_T2_C06_W07",
    "DL1018_DEV_T3_C00_W05", "DL1018_DEV_T3_C15_W14", "DL1018_DEV_T3_C05_W02",
]
EXPECTED_DEV = [
    "DL1018_DEV_T2_C02_W15", "DL1018_DEV_T3_C03_W15", "DL1018_DEV_T1_C04_W00",
    "DL1018_DEV_T1_C07_W08", "DL1018_DEV_T1_C10_W09", "DL1018_DEV_T1_C11_W12",
    "DL1018_DEV_T2_C03_W01", "DL1018_DEV_T2_C08_W08", "DL1018_DEV_T2_C09_W10",
    "DL1018_DEV_T2_C12_W13", "DL1018_DEV_T2_C14_W14", "DL1018_DEV_T3_C06_W08",
    "DL1018_DEV_T3_C09_W09", "DL1018_DEV_T3_C10_W11", "DL1018_DEV_T3_C13_W12",
]
SAMPLE_ORDINALS = tuple(range(0, 1996, 5))
PLANT_INDEX = tuple(range(11, 20000, 10))
AXIS_RMS = (8.71283036857775, 8.721630269411728, 0.6125819446901479)
BOOTSTRAP_REPLICATES = 10_000
BOOTSTRAP_SEED = 20261025
MAX_OUTPUT_BYTES = 1 << 30
CLIP_RAD_S2 = (45.0, 45.0, 4.7124)
TRAIN24_PREFIX = "reports/attitude_position_context_probe_20261024/c5_matched_train24_v1/event_exports_v1"
NEW_CACHE_DIR = "experiments/attitude_cm18_c524_coverage33_20261025/data"


class StopError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _expected_train24_runtime_scene_id(scene_id: str) -> str:
    try:
        return TRAIN24_RUNTIME_SCENE_IDS[scene_id]
    except KeyError as exc:
        raise StopError("STOP_CACHE_CLOSURE", f"unexpected TRAIN24 canonical scene ID: {scene_id}") from exc


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise StopError("STOP_IDENTITY", f"invalid pinned JSON {path}: {type(exc).__name__}: {exc}") from exc
    if not isinstance(value, dict):
        raise StopError("STOP_IDENTITY", f"expected JSON object: {path}")
    return value


def _inside(root: Path, path: Path) -> Path:
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(root.resolve(strict=True))
    except ValueError as exc:
        raise StopError("STOP_IDENTITY", f"path escapes project root: {path}") from exc
    return resolved


def _assert_output_path_safe(root: Path) -> Path:
    """Reject output paths that escape through a symlink/junction/reparse point."""
    root_real = root.resolve(strict=True)
    output = root / OUTPUT_REL
    try:
        output.relative_to(root)
    except ValueError as exc:
        raise StopError("STOP_IDENTITY", f"output path is not rooted in project: {output}") from exc
    cursor = root
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    for part in Path(OUTPUT_REL).parts:
        cursor = cursor / part
        try:
            info = cursor.lstat()
        except FileNotFoundError:
            break
        if stat.S_ISLNK(info.st_mode) or (getattr(info, "st_file_attributes", 0) & reparse_flag):
            raise StopError("STOP_IDENTITY", f"output path contains a symlink/junction/reparse point: {cursor}")
        if cursor != output and not stat.S_ISDIR(info.st_mode):
            raise StopError("STOP_IDENTITY", f"output parent is not a directory: {cursor}")
        try:
            resolved = cursor.resolve(strict=True)
            resolved.relative_to(root_real)
        except (OSError, ValueError) as exc:
            raise StopError("STOP_IDENTITY", f"output path or existing parent escapes project root: {cursor}") from exc
    try:
        resolved_output = output.resolve(strict=False)
        resolved_output.relative_to(root_real)
    except (OSError, ValueError) as exc:
        raise StopError("STOP_IDENTITY", f"output path resolves outside project root: {output}") from exc
    return output


def _fixed_file(root: Path, rel: str, expected_sha: str) -> Path:
    path = _inside(root, root / rel)
    actual = _sha(path)
    if actual != expected_sha:
        raise StopError("STOP_IDENTITY", f"SHA-256 mismatch for {rel}: {actual}")
    return path


def _check_runtime_metadata() -> dict[str, str]:
    versions: dict[str, str] = {}
    for name, pin in RUNTIME_PACKAGES.items():
        try:
            dist = importlib.metadata.distribution(name)
            record = next((item for item in (dist.files or ()) if str(item).endswith(".dist-info/RECORD")), None)
            if record is None:
                raise ValueError("distribution has no RECORD")
            record_path = Path(dist.locate_file(record)).resolve(strict=True)
            if dist.version != pin["version"] or _sha(record_path) != pin["record_sha256"]:
                raise ValueError("pinned package version or RECORD SHA mismatch")
            versions[name] = dist.version
        except Exception as exc:
            raise StopError("STOP_IDENTITY", f"runtime dependency pin failed for {name}: {exc}") from exc
    return versions


def _expected_allowlist() -> dict[str, Any]:
    return {
        "schema": "CM18_C5_COVERAGE33_FIT_GENERALIZATION_ALLOWLIST_V1",
        "implementation_path": SCRIPT_REL,
        "fixed_input_sha256": dict(sorted(EXPECTED_FILES.items())),
        "runtime_packages": RUNTIME_PACKAGES,
        "cache_path_policy": {
            "manifest_path": MANIFEST_REL,
            "manifest_sha256": EXPECTED_FILES[MANIFEST_REL],
            "TRAIN24_prefix": TRAIN24_PREFIX,
            "TRAIN_EXTRA_and_DEV_directory": NEW_CACHE_DIR,
            "only_manifest_fields": ["train24_scenes[].cache_path/cache_sha256", "extra_dev_scenes[].event_cache_path/event_cache_sha256", "holdout_dev_scenes[].event_cache_path/event_cache_sha256"],
            "forbidden": ["raw MAT", "C5_VAL48", "TEST", "cache-directory search"],
        },
    }


def _verify_allowlist(root: Path) -> tuple[Path, str]:
    allow_path = _inside(root, root / ALLOWLIST_REL)
    allow = _json(allow_path)
    expected = _expected_allowlist()
    if set(allow) != set(expected) | {"implementation_sha256"} or {key: allow.get(key) for key in expected} != expected:
        raise StopError("STOP_IDENTITY", "implementation allowlist differs from the hard-coded path/SHA allowlist")
    script_path = _inside(root, root / SCRIPT_REL)
    script_sha = _sha(script_path)
    if allow.get("implementation_sha256") != script_sha:
        raise StopError("STOP_IDENTITY", "implementation script SHA does not match allowlist")
    return allow_path, script_sha


def _check_cli_paths(args: argparse.Namespace, root: Path) -> None:
    expected = {
        "taskbook": TASKBOOK_REL,
        "train_release": RELEASE_REL,
        "relabel_manifest": MANIFEST_REL,
        "closed_loop_binding": BINDING_REL,
        "normalizer": NORMALIZER_REL,
        "audit_dir": AUDIT_DIR_REL,
        "output_dir": OUTPUT_REL,
    }
    for name, rel in expected.items():
        actual = Path(getattr(args, name)).as_posix().replace("./", "")
        if actual.casefold() != rel.casefold():
            raise StopError("STOP_IDENTITY", f"--{name.replace('_', '-')} must be the fixed path {rel}")
    out = _assert_output_path_safe(root)
    if out.exists():
        if not out.is_dir() or any(out.iterdir()):
            raise StopError("STOP_IDENTITY", f"output path exists with prior content; refusing overwrite: {out}")


def _check_release(release: dict[str, Any]) -> None:
    taskbook_ref = release.get("taskbook", {})
    manifest_ref = release.get("relabel_manifest", {})
    original_ref = release.get("original_c5_train24_release", {})
    if (release.get("schema") != "CM18_C5_COVERAGE33_TRAINING_RELEASE_V1"
            or release.get("decision") != "APPROVE_ONE_MODEL_TRAINING"
            or release.get("output_directory") != "experiments/attitude_cm18_c524_coverage33_20261025/training_C5_COVERAGE33_v1"
            or taskbook_ref.get("path") != "reports/attitude_cm18_c524_screen12_20261025/C524_COVERAGE33_TASKBOOK_v2_ZH.md"
            or str(taskbook_ref.get("sha256", "")).lower() != "934fc1b8a614c5a32993add65a0aee89d48e7c31ea368646063e5576b78c7017"
            or manifest_ref.get("path") != MANIFEST_REL
            or str(manifest_ref.get("sha256", "")).lower() != EXPECTED_FILES[MANIFEST_REL]
            or original_ref.get("path") != "reports/attitude_cm18_datarepair_20261024/ROOT_B24_C524_C5_24_TRAINING_RELEASE_v1.json"
            or str(original_ref.get("sha256", "")).lower() != "5c42d2e613d8075899cbb03e492d756a6f7f58b3a73f257fa11d5e7eee03d3b0"
            or release.get("train_scene_count") != 33 or release.get("fit_rows") != 13_200
            or release.get("TEST_accessed") is not False or release.get("C5_VAL48_accessed") is not False
            or release.get("holdout_or_validation_used_for_training_or_selection") is not False
            or release.get("checkpoint_selection") != "none; fixed final step 60000"
            or release.get("row_map_sha256", "").lower() != "bc202f6653fb04169990dac9dd209805bbf661b1797c3e64788206e6d6c75521"
            or release.get("sample_index_stream_sha256", "").lower() != "c3bbbf2f82a8bb50e4851b08614816024c7b912e36f9f6c6a0bc1a215d3ec9a9"
            or release.get("sample_ordinals_zero_based") != "0,5,...,1995"):
        raise StopError("STOP_IDENTITY", "training release is not the fixed C5_COVERAGE33 release")
    training = release.get("training", {})
    model = release.get("model", {})
    if (training.get("seed") != 2026102001 or training.get("steps") != 60_000
            or model.get("architecture") != "CM18-A1 18-32-32-24 tanh/bilinear"
            or model.get("parameter_count") != 2456):
        raise StopError("STOP_IDENTITY", "training steps or model architecture differ from fixed release")
    self_check = release.get("self_check", {})
    if (self_check.get("status") != "PASS" or self_check.get("scene_count") != 33
            or self_check.get("fit_rows") != 13_200 or self_check.get("Plant_calls") != 0
            or self_check.get("TEST_accessed") is not False):
        raise StopError("STOP_IDENTITY", "training release self-check or scope counters are invalid")
    if set(release.get("source_files", {})) != {
        TRAINER_REL, PAIRED_TRAINER_REL, READER_REL, NUMPY_MODEL_REL, TORCH_MODEL_REL
    }:
        raise StopError("STOP_IDENTITY", "training source allowlist differs from the pinned source contract")
    for rel, expected in release["source_files"].items():
        if EXPECTED_FILES.get(rel) != str(expected).lower():
            raise StopError("STOP_IDENTITY", f"training source SHA is not pinned by implementation allowlist: {rel}")


def _check_binding(binding: dict[str, Any], release_sha: str, manifest_sha: str) -> list[str]:
    if (binding.get("schema") != "CM18_C5_COVERAGE33_CLOSED_LOOP_BINDING_V1"
            or binding.get("status") != "FROZEN_READY_FOR_15_SCENE_CLOSED_LOOP" or binding.get("candidate_id") != "C5_COVERAGE33"
            or binding.get("model_id") != "C5_COVERAGE33"
            or binding.get("checkpoint_path") != CHECKPOINT_REL
            or str(binding.get("checkpoint_sha256", "")).lower() != EXPECTED_FILES[CHECKPOINT_REL]
            or binding.get("model_path") != MODEL_REL
            or str(binding.get("model_sha256", "")).lower() != EXPECTED_FILES[MODEL_REL]
            or binding.get("training_release_path") != RELEASE_REL
            or str(binding.get("training_release_sha256", "")).lower() != release_sha
            or binding.get("relabel_manifest_path") != MANIFEST_REL
            or str(binding.get("relabel_manifest_sha256", "")).lower() != manifest_sha
            or binding.get("training_steps") != 60_000 or binding.get("optimizer_steps") != 60_000
            or binding.get("plant_calls") != 0 or binding.get("TEST_accessed") is not False):
        raise StopError("STOP_IDENTITY", "closed-loop binding v3 differs from fixed model/release/manifest identity")
    scene_ids = binding.get("scene_ids")
    rows = binding.get("scene_rows")
    if (scene_ids != EXPECTED_DEV or not isinstance(rows, list)
            or not all(isinstance(row, dict) for row in rows)
            or [row.get("scene_id") for row in rows] != EXPECTED_DEV):
        raise StopError("STOP_SPLIT_LEAKAGE", "binding DEV scene IDs/order differ from the fixed 15-scene list")
    if any(row.get("split") != "HOLDOUT" for row in rows):
        raise StopError("STOP_SPLIT_LEAKAGE", "binding contains a non-HOLDOUT scene")
    return list(scene_ids)


def _check_audits(root: Path, binding: dict[str, Any], binding_sha: str,
                  release_sha: str, manifest_sha: str, dev_rows: list[dict[str, Any]]) -> None:
    manifest_by_id = {row["scene_id"]: row for row in dev_rows}
    for ordinal, sid in enumerate(EXPECTED_DEV, start=1):
        rel = f"{AUDIT_DIR_REL}/{sid}_C5_COVERAGE33_AUDIT_v1.json"
        path = _fixed_file(root, rel, EXPECTED_FILES[rel])
        audit = _json(path)
        if (audit.get("schema") != "CM18_C5_COVERAGE33_SCENE_AUDIT_V1"
                or audit.get("scene_id") != sid or audit.get("scene_ordinal") != ordinal
                or audit.get("status") != "PASS" or audit.get("candidate_status") != "STABLE"
                or audit.get("model_id") != "C5_COVERAGE33"
                or str(audit.get("binding_sha256", "")).lower() != binding_sha
                or str(audit.get("checkpoint_sha256", "")).lower() != EXPECTED_FILES[CHECKPOINT_REL]
                or str(audit.get("model_sha256", "")).lower() != EXPECTED_FILES[MODEL_REL]
                or str(audit.get("training_release_sha256", "")).lower() != release_sha
                or str(audit.get("relabel_manifest_sha256", "")).lower() != manifest_sha
                or audit.get("training_steps") != 60_000 or audit.get("optimizer_steps") != 60_000
                or audit.get("plant_calls") != 1 or audit.get("transitions") != 20_000
                or audit.get("state_samples") != 20_001 or audit.get("cm18_events") != 1_999
                or audit.get("safety_stop_reason") != "" or audit.get("TEST_accessed") is not False
                or not isinstance(audit.get("candidate_C5_COVERAGE33"), dict)):
            raise StopError("STOP_IDENTITY", f"DEV scene audit identity/scope mismatch: {sid}")
        bound = binding["scene_rows"][ordinal - 1]
        manifest_row = manifest_by_id[sid]
        # The audit's candidate_raw_sha256 is the C5_COVERAGE33 run. The teacher raw
        # identity is separately named c5_rbf_raw_* and must match binding/manifest.
        # Neither raw path nor raw bytes are opened here.
        teacher_sha = str(audit.get("c5_rbf_raw_sha256", "")).lower()
        teacher_path = str(audit.get("c5_rbf_raw_path", "")).replace("/", "\\").casefold()
        bound_sha = str(bound.get("c5_raw_sha256", "")).lower()
        manifest_sha_value = str(manifest_row.get("c5_raw_sha256", "")).lower()
        bound_path = str(bound.get("c5_raw_path", "")).replace("/", "\\").casefold()
        manifest_path = str(manifest_row.get("c5_raw_path", "")).replace("/", "\\").casefold()
        if (teacher_sha != bound_sha or teacher_sha != manifest_sha_value
                or teacher_path != bound_path or teacher_path != manifest_path):
            raise StopError("STOP_IDENTITY", f"DEV audit/binding/manifest raw identity metadata disagree: {sid}")
        candidate = audit["candidate_C5_COVERAGE33"]
        if candidate.get("cm18_inference_event_count") != 1_999:
            raise StopError("STOP_IDENTITY", f"DEV audit does not record 1999 CM18 inference events: {sid}")


def _check_normalizer(norm: dict[str, Any], release: dict[str, Any]) -> tuple[list[float], list[float], list[float]]:
    ref = release.get("normalizer", {})
    if (ref.get("path") != NORMALIZER_REL or str(ref.get("sha256", "")).lower() != EXPECTED_FILES[NORMALIZER_REL]
            or str(ref.get("canonical_sha256", "")).lower() != "12c864b9c2404235e0ea3f313bb0801a99902eca7cfdfbf43f0d8d584d5d609a"
            or norm.get("schema") != "CM18_A1T_NORMALIZER_V1"
            or str(norm.get("canonical_float64_sha256", "")).lower() != ref.get("canonical_sha256", "").lower()):
        raise StopError("STOP_IDENTITY", "normalizer/release canonical identity mismatch")
    mean = norm.get("input_mean_float64")
    std = norm.get("input_std_float64")
    rms = norm.get("train_axis_rms_rad_s2_float64")
    if not (isinstance(mean, list) and len(mean) == 18 and isinstance(std, list) and len(std) == 18
            and isinstance(rms, list) and len(rms) == 3):
        raise StopError("STOP_IDENTITY", "canonical normalizer input/output arrays have an unknown schema")
    vals = [float(v) for v in mean + std + rms]
    if not all(math.isfinite(v) for v in vals) or any(float(v) < 1e-6 for v in std) or any(float(v) <= 0 for v in rms):
        raise StopError("STOP_IDENTITY", "normalizer arrays contain non-finite or non-positive scales")
    if any(float(a) != float(b) for a, b in zip(rms, AXIS_RMS)):
        raise StopError("STOP_IDENTITY", "fixed A1T output-axis RMS differs from taskbook")
    return [float(x) for x in mean], [float(x) for x in std], [float(x) for x in rms]


def _verify_path_policy(root: Path, rel: str, scene_id: str, kind: str) -> Path:
    raw_path = Path(rel)
    resolved = _inside(root, raw_path if raw_path.is_absolute() else root / raw_path)
    normalized = resolved.relative_to(root.resolve(strict=True)).as_posix()
    if kind == "TRAIN24":
        expected_parent = f"{TRAIN24_PREFIX}/{scene_id}"
        if not normalized.startswith(expected_parent + "/") or not normalized.endswith(f"/{scene_id}_CSTAR_EVENTS_v1.mat"):
            raise StopError("STOP_IDENTITY", f"TRAIN24 cache path is outside fixed allowlist: {scene_id}")
    else:
        if not normalized.startswith(NEW_CACHE_DIR + "/") or not normalized.endswith(f"/{scene_id}_EVENTS_v1.mat"):
            raise StopError("STOP_IDENTITY", f"TRAIN_EXTRA/DEV cache path is outside fixed allowlist: {scene_id}")
    return resolved


def _manifest_rows(manifest: dict[str, Any], release: dict[str, Any], binding_ids: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if (manifest.get("schema") != "CM18_C5_COVERAGE33_RELABEL_MANIFEST_V1"
            or manifest.get("status") != "PASS" or manifest.get("taskbook_sha256") != "934fc1b8a614c5a32993add65a0aee89d48e7c31ea368646063e5576b78c7017"
            or manifest.get("fit_rows_total") != 13_200 or manifest.get("fit_rows_extra") != 3_600
            or manifest.get("event_count_new_scenes") != 47_976
            or manifest.get("Plant_calls_during_relabel") != 0 or manifest.get("engine_calls_during_relabel") != 0
            or manifest.get("optimizer_steps") != 0 or manifest.get("C5_VAL48_accessed") is not False
            or manifest.get("TEST_accessed") is not False):
        raise StopError("STOP_IDENTITY", "relabel manifest is not the pinned offline PASS")
    train24 = manifest.get("train24_scenes")
    extra = manifest.get("extra_dev_scenes")
    dev = manifest.get("holdout_dev_scenes")
    if (not isinstance(train24, list) or not isinstance(extra, list) or not isinstance(dev, list)
            or not all(isinstance(row, dict) for row in train24 + extra + dev)):
        raise StopError("STOP_CACHE_CLOSURE", "manifest cache lists contain a non-object row")
    for row in train24:
        if (set(row) != {"scene_id", "cache_path", "cache_sha256"}
                or any(not isinstance(row.get(key), str) or not row.get(key)
                       for key in ("scene_id", "cache_path", "cache_sha256"))):
            raise StopError("STOP_CACHE_CLOSURE", "TRAIN24 manifest cache row schema is unknown")
    for rows, split in ((extra, "TRAIN_EXTRA"), (dev, "HOLDOUT")):
        expected_keys = {"scene_id", "split", "event_count", "fit_rows", "event_cache_path", "event_cache_sha256"}
        if (any(not expected_keys.issubset(row) for row in rows)
                or any(not isinstance(row.get(key), str) or not row.get(key)
                       for row in rows for key in ("scene_id", "split", "event_cache_path", "event_cache_sha256"))):
            raise StopError("STOP_CACHE_CLOSURE", f"{split} cache manifest row schema is unknown")
    if ([row.get("scene_id") for row in train24] != EXPECTED_TRAIN24
            or [row.get("scene_id") for row in extra] != EXPECTED_EXTRA
            or [row.get("scene_id") for row in dev] != binding_ids):
        raise StopError("STOP_SPLIT_LEAKAGE", "manifest scene IDs/order differ from fixed TRAIN/DEV lists")
    release_train = release.get("train_scene_ids")
    if release_train != EXPECTED_TRAIN24 + EXPECTED_EXTRA or release.get("holdout_scene_ids") != EXPECTED_DEV:
        raise StopError("STOP_SPLIT_LEAKAGE", "training release TRAIN/HOLDOUT scene lists differ from fixed split")
    if set(EXPECTED_TRAIN24 + EXPECTED_EXTRA).intersection(binding_ids):
        raise StopError("STOP_SPLIT_LEAKAGE", "TRAIN/DEV scene IDs overlap")
    for rows, split, fit_rows in ((extra, "TRAIN_EXTRA", 400), (dev, "HOLDOUT", 0)):
        for row in rows:
            if (row.get("split") != split or row.get("event_count") != 1_999
                    or row.get("fit_rows") != fit_rows):
                raise StopError("STOP_CACHE_CLOSURE", f"{split} manifest event/fit count mismatch: {row.get('scene_id')}")
            closure = row.get("closure_max_abs")
            if not isinstance(closure, (int, float)) or not math.isfinite(float(closure)) or float(closure) > 1e-8:
                raise StopError("STOP_CACHE_CLOSURE", f"{split} manifest closure summary is invalid: {row.get('scene_id')}")
    t_counts = {f"T{i}": sum(1 for sid in EXPECTED_TRAIN24 + EXPECTED_EXTRA if re.search(fr"_(T{i})_", sid)) for i in (1, 2, 3)}
    d_counts = {f"T{i}": sum(1 for sid in EXPECTED_DEV if re.search(fr"_(T{i})_", sid)) for i in (1, 2, 3)}
    if t_counts != {"T1": 12, "T2": 10, "T3": 11} or d_counts != {"T1": 4, "T2": 6, "T3": 5}:
        raise StopError("STOP_SPLIT_LEAKAGE", "fixed T-family scene counts differ from taskbook")
    return train24 + extra, dev


def _h5_text(node: Any, key: str) -> str:
    import numpy as np

    if key not in node:
        raise StopError("STOP_CACHE_CLOSURE", f"cache lacks events/{key}")
    raw = np.asarray(node[key]).reshape(-1)
    if raw.dtype.kind in "ui":
        try:
            return "".join(chr(int(value)) for value in raw if int(value)).strip("\x00")
        except Exception as exc:
            raise StopError("STOP_CACHE_CLOSURE", f"invalid UTF code units in events/{key}: {exc}") from exc
    return "".join(str(value) for value in raw).strip("\x00")


def _read_vector(node: Any, key: str, integer: bool = False) -> Any:
    import numpy as np

    if key not in node:
        raise StopError("STOP_CACHE_CLOSURE", f"cache lacks events/{key}")
    raw = np.asarray(node[key]).reshape(-1)
    if raw.shape != (1_999,):
        raise StopError("STOP_CACHE_CLOSURE", f"cache events/{key} length is not 1999")
    if integer:
        value_float = np.asarray(raw, dtype=np.float64)
        if not np.isfinite(value_float).all() or not np.array_equal(value_float, np.round(value_float)):
            raise StopError("STOP_CACHE_CLOSURE", f"cache events/{key} is not finite integral data")
        return value_float.astype(np.int64)
    value = np.asarray(raw, dtype=np.float64)
    if not np.isfinite(value).all():
        raise StopError("STOP_CACHE_CLOSURE", f"cache events/{key} has non-finite values")
    return value


def _read_matrix(node: Any, key: str, width: int) -> Any:
    import numpy as np

    if key not in node:
        raise StopError("STOP_CACHE_CLOSURE", f"cache lacks events/{key}")
    stored = np.asarray(node[key], dtype=np.float64)
    value = stored.T
    if value.shape != (1_999, width) or not np.isfinite(value).all():
        raise StopError("STOP_CACHE_CLOSURE", f"cache events/{key} has wrong HDF5/MAT orientation or non-finite values")
    return np.ascontiguousarray(value)


def _load_one_cache(root: Path, row: dict[str, Any], split: str, kind: str) -> dict[str, Any]:
    import h5py
    import numpy as np

    sid = row["scene_id"]
    if kind == "TRAIN24":
        path_rel, expected_sha = row["cache_path"], str(row["cache_sha256"]).lower()
    else:
        path_rel, expected_sha = row["event_cache_path"], str(row["event_cache_sha256"]).lower()
    path = _verify_path_policy(root, path_rel, sid, kind)
    actual_sha = _sha(path)
    if actual_sha != expected_sha:
        raise StopError("STOP_IDENTITY", f"cache SHA mismatch: {sid} ({actual_sha})")
    try:
        with h5py.File(path, "r") as stream:
            if "events" not in stream or not isinstance(stream["events"], h5py.Group):
                raise StopError("STOP_CACHE_CLOSURE", f"cache lacks HDF5 events group: {sid}")
            events = stream["events"]
            schema = _h5_text(events, "schema")
            if kind == "TRAIN24":
                if (schema != "CM18_C5_MATCHED_TRAIN24_CSTAR_EVENT_CACHE_V1"
                        or _h5_text(events, "canonical_scene_id") != sid
                        or _h5_text(events, "runtime_scene_id") != _expected_train24_runtime_scene_id(sid)
                        or _h5_text(events, "split") != "TRAIN"):
                    raise StopError("STOP_CACHE_CLOSURE", f"TRAIN24 embedded identity mismatch: {sid}")
            else:
                if (schema != "CM18_C5_COVERAGE33_EVENTS_V1"
                        or _h5_text(events, "scene_id") != sid
                        or _h5_text(events, "split") != split):
                    raise StopError("STOP_CACHE_CLOSURE", f"TRAIN_EXTRA/DEV embedded identity mismatch: {sid}")
            x = _read_matrix(events, "X18", 18)
            target = _read_matrix(events, "target_raw_output_rad_s2", 3)
            cstar = _read_matrix(events, "target_applied_acceleration_rad_s2", 3)
            after_clip = _read_matrix(events, "target_after_clip_beta_rad_s2", 3)
            e0 = _read_matrix(events, "E0_rad_s2", 3)
            gflat = _read_matrix(events, "G_row_major", 9)
            beta = _read_vector(events, "beta")
            event_index = _read_vector(events, "event_index", integer=True)
            plant = _read_vector(events, "plant_index", integer=True)
            event_time = _read_vector(events, "event_time_s")
            phase = _read_vector(events, "phase_code", integer=True)
    except StopError:
        raise
    except Exception as exc:
        raise StopError("STOP_CACHE_CLOSURE", f"cache decode failed for {sid}: {type(exc).__name__}: {exc}") from exc

    import numpy as np

    if not np.array_equal(event_index, np.arange(1, 2_000, dtype=np.int64)):
        raise StopError("STOP_CACHE_CLOSURE", f"one-based event_index does not map to zero-based ordinal for {sid}")
    expected_plant = np.asarray(PLANT_INDEX, dtype=np.int64)
    if not np.array_equal(plant, expected_plant):
        raise StopError("STOP_CACHE_CLOSURE", f"plant_index clock mismatch for {sid}")
    beta_expected = np.minimum(expected_plant.astype(np.float64) * 0.001 / 2.2, 1.0)
    time_expected = (expected_plant.astype(np.float64) - 1.0) * 0.001
    if (np.any(beta <= 0.0) or np.max(np.abs(beta - beta_expected)) > 1e-12
            or np.max(np.abs(event_time - time_expected)) > 1e-12
            or np.any((phase < 0) | (phase > 5))):
        raise StopError("STOP_CACHE_CLOSURE", f"beta/time/phase clock mismatch for {sid}")
    closure = float(np.max(np.abs(target - cstar / beta[:, None])))
    if not math.isfinite(closure) or closure > 1e-8:
        raise StopError("STOP_CACHE_CLOSURE", f"Cstar/beta label closure exceeds 1e-8 for {sid}: {closure}")
    g = gflat.reshape(1_999, 3, 3)
    residual_closure = float(np.max(np.abs(e0 - np.einsum("nij,nj->ni", g, cstar))))
    clip_closure = float(np.max(np.abs(after_clip - beta[:, None] * np.clip(
        target, -np.asarray(CLIP_RAD_S2), np.asarray(CLIP_RAD_S2)))))
    if residual_closure > 1e-8 or clip_closure > 1e-8:
        raise StopError("STOP_CACHE_CLOSURE", f"stored physical closure/clip closure failed for {sid}")
    if not np.isfinite(x).all() or not np.isfinite(target).all() or not np.isfinite(cstar).all():
        raise StopError("STOP_CACHE_CLOSURE", f"non-finite X18 or label data for {sid}")
    return {
        "scene_id": sid, "split": split, "cache_path": path.relative_to(root).as_posix(),
        "cache_sha256": actual_sha, "schema": schema, "X18": x, "target": target,
        "cstar": cstar, "beta": beta, "phase": phase, "event_index": event_index,
        "plant_index": plant, "event_time_s": event_time,
        "event_count": len(event_index), "label_closure_max_abs": closure,
        "manifest_declared_closure_max_abs": row.get("closure_max_abs"),
        "residual_closure_max_abs": residual_closure, "clip_closure_max_abs": clip_closure,
        "ordinal_zero_based": np.arange(1_999, dtype=np.int64),
    }


def _rowmap_sha(train_scenes: list[dict[str, Any]]) -> str:
    rowmap = []
    for scene in train_scenes:
        sid = scene["scene_id"]
        for ordinal in SAMPLE_ORDINALS:
            rowmap.append((sid, int(ordinal), int(scene["plant_index"][ordinal])))
    payload = json.dumps(rowmap, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _sample_stream_sha(row_count: int = 13_200) -> str:
    import numpy as np

    rng = np.random.default_rng(2026102001)
    digest = hashlib.sha256()
    for _ in range(60_000):
        values = rng.integers(0, row_count, size=512, dtype=np.int64)
        digest.update(np.asarray(values, dtype="<i8").tobytes(order="C"))
    return digest.hexdigest()


def _preflight(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    import numpy as np

    _check_cli_paths(args, root)
    allowlist_path, script_sha = _verify_allowlist(root)
    paths = {rel: _fixed_file(root, rel, sha) for rel, sha in EXPECTED_FILES.items()}
    runtime_versions = _check_runtime_metadata()
    release = _json(paths[RELEASE_REL])
    manifest = _json(paths[MANIFEST_REL])
    binding = _json(paths[BINDING_REL])
    normalizer = _json(paths[NORMALIZER_REL])
    _check_release(release)
    mean, std, axis_rms = _check_normalizer(normalizer, release)
    binding_ids = _check_binding(binding, EXPECTED_FILES[RELEASE_REL], EXPECTED_FILES[MANIFEST_REL])
    rows_train, rows_dev = _manifest_rows(manifest, release, binding_ids)
    _check_audits(root, binding, EXPECTED_FILES[BINDING_REL], EXPECTED_FILES[RELEASE_REL], EXPECTED_FILES[MANIFEST_REL], rows_dev)
    train_scenes: list[dict[str, Any]] = []
    for row in rows_train:
        kind = "TRAIN24" if row["scene_id"] in EXPECTED_TRAIN24 else "TRAIN_EXTRA"
        train_scenes.append(_load_one_cache(root, row, "TRAIN" if kind == "TRAIN24" else "TRAIN_EXTRA", kind))
    dev_scenes = [_load_one_cache(root, row, "HOLDOUT", "DEV") for row in rows_dev]
    if ([scene["scene_id"] for scene in train_scenes] != EXPECTED_TRAIN24 + EXPECTED_EXTRA
            or [scene["scene_id"] for scene in dev_scenes] != EXPECTED_DEV):
        raise StopError("STOP_SPLIT_LEAKAGE", "loaded cache scene order differs from fixed taskbook")
    if len(train_scenes) != 33 or len(dev_scenes) != 15:
        raise StopError("STOP_STATISTICS", "fixed scene block count differs from 33 TRAIN and 15 DEV")
    row_sha = _rowmap_sha(train_scenes)
    stream_sha = _sample_stream_sha()
    if row_sha != release["row_map_sha256"].lower():
        raise StopError("STOP_IDENTITY", f"reconstructed training row-map SHA mismatch: {row_sha}")
    if stream_sha != release["sample_index_stream_sha256"].lower():
        raise StopError("STOP_IDENTITY", f"reconstructed training sample-index stream SHA mismatch: {stream_sha}")
    if len(set(scene["scene_id"] for scene in train_scenes) & set(scene["scene_id"] for scene in dev_scenes)):
        raise StopError("STOP_SPLIT_LEAKAGE", "TRAIN and DEV cache IDs overlap")
    t_counts = {f"T{i}": sum(1 for s in train_scenes if re.search(fr"_(T{i})_", s["scene_id"])) for i in (1, 2, 3)}
    d_counts = {f"T{i}": sum(1 for s in dev_scenes if re.search(fr"_(T{i})_", s["scene_id"])) for i in (1, 2, 3)}
    if t_counts != {"T1": 12, "T2": 10, "T3": 11} or d_counts != {"T1": 4, "T2": 6, "T3": 5}:
        raise StopError("STOP_SPLIT_LEAKAGE", "loaded T-family counts differ from fixed taskbook")
    return {
        "root": root, "paths": paths, "allowlist_path": allowlist_path, "script_sha256": script_sha,
        "runtime_versions": runtime_versions,
        "release": release, "manifest": manifest, "binding": binding, "normalizer": normalizer,
        "input_mean": np.asarray(mean, dtype=np.float64), "input_std": np.asarray(std, dtype=np.float64),
        "axis_rms": np.asarray(axis_rms, dtype=np.float64), "train_scenes": train_scenes,
        "dev_scenes": dev_scenes, "row_map_sha256": row_sha, "sample_stream_sha256": stream_sha,
        "train_t_family_counts": t_counts, "dev_t_family_counts": d_counts,
    }


AXIS_NAMES = ("x", "y", "z")
METRIC_NAMES = tuple(
    [f"physical_rmse_{axis}" for axis in AXIS_NAMES]
    + [f"physical_bias_{axis}" for axis in AXIS_NAMES]
    + ["physical_vector_rmse"]
    + [f"physical_vector_bias_{axis}" for axis in AXIS_NAMES]
    + ["physical_vector_bias_norm"]
    + [f"normalized_rmse_{axis}" for axis in AXIS_NAMES]
    + [f"normalized_bias_{axis}" for axis in AXIS_NAMES]
    + ["normalized_vector_nrmse"]
    + [f"normalized_vector_bias_{axis}" for axis in AXIS_NAMES]
    + ["normalized_vector_bias_norm"]
)


def _metrics(prediction: Any, target: Any, axis_rms: Any) -> dict[str, float]:
    import numpy as np

    p = np.asarray(prediction, dtype=np.float64)
    y = np.asarray(target, dtype=np.float64)
    scale = np.asarray(axis_rms, dtype=np.float64)
    if p.ndim != 2 or y.shape != p.shape or p.shape[1] != 3 or p.shape[0] == 0:
        raise StopError("STOP_STATISTICS", "metric input has an empty or malformed event block")
    if not np.isfinite(p).all() or not np.isfinite(y).all():
        raise StopError("STOP_STATISTICS", "metric input contains a non-finite prediction or label")
    error = p - y
    normalized = error / scale[None, :]
    physical_bias = np.mean(error, axis=0)
    normalized_bias = np.mean(normalized, axis=0)
    out: dict[str, float] = {}
    for j, axis in enumerate(AXIS_NAMES):
        out[f"physical_rmse_{axis}"] = float(np.sqrt(np.mean(error[:, j] ** 2)))
        out[f"physical_bias_{axis}"] = float(physical_bias[j])
        out[f"normalized_rmse_{axis}"] = float(np.sqrt(np.mean(normalized[:, j] ** 2)))
        out[f"normalized_bias_{axis}"] = float(normalized_bias[j])
    out["physical_vector_rmse"] = float(np.sqrt(np.mean(np.sum(error ** 2, axis=1))))
    for j, axis in enumerate(AXIS_NAMES):
        out[f"physical_vector_bias_{axis}"] = float(physical_bias[j])
    out["physical_vector_bias_norm"] = float(np.linalg.norm(physical_bias))
    out["normalized_vector_nrmse"] = float(np.sqrt(np.mean(np.mean(normalized ** 2, axis=1))))
    for j, axis in enumerate(AXIS_NAMES):
        out[f"normalized_vector_bias_{axis}"] = float(normalized_bias[j])
    out["normalized_vector_bias_norm"] = float(np.linalg.norm(normalized_bias))
    if set(out) != set(METRIC_NAMES) or not all(math.isfinite(v) for v in out.values()):
        raise StopError("STOP_STATISTICS", "metric computation produced an incomplete/non-finite metric set")
    return out


def _load_frozen_model(preflight: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
    import numpy as np
    import torch
    import importlib.util

    checkpoint_path = preflight["paths"][CHECKPOINT_REL]
    try:
        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    except Exception as exc:
        raise StopError("STOP_IDENTITY", f"pinned checkpoint could not be decoded safely: {type(exc).__name__}: {exc}") from exc
    if (not isinstance(checkpoint, dict)
            or set(checkpoint) != {"schema", "kind", "optimizer_step", "state_dict"}
            or checkpoint.get("schema") != "CM18_C5_COVERAGE33_CHECKPOINT_V1"
            or checkpoint.get("kind") != "final" or checkpoint.get("optimizer_step") != 60_000):
        raise StopError("STOP_IDENTITY", "checkpoint schema/kind/optimizer step differs from fixed release")
    state = checkpoint.get("state_dict")
    shapes = {
        "fc1.weight": (32, 18), "fc1.bias": (32,), "fc2.weight": (32, 32), "fc2.bias": (32,),
        "fc3.weight": (24, 32), "fc3.bias": (24,), "input_mean": (18,), "input_std": (18,),
        "train_axis_rms_rad_s2": (3,),
    }
    if not isinstance(state, dict) or set(state) != set(shapes):
        raise StopError("STOP_IDENTITY", "checkpoint state_dict does not match the pinned nine-key CM18 schema")
    for key, shape in shapes.items():
        tensor = state[key]
        if (not torch.is_tensor(tensor) or tuple(tensor.shape) != shape or tensor.dtype != torch.float32
                or not bool(torch.isfinite(tensor).all())):
            raise StopError("STOP_IDENTITY", f"checkpoint tensor shape/dtype/value mismatch: {key}")
    if sum(state[k].numel() for k in ("fc1.weight", "fc1.bias", "fc2.weight", "fc2.bias", "fc3.weight", "fc3.bias")) != 2456:
        raise StopError("STOP_IDENTITY", "checkpoint learned parameter count differs from the pinned model")

    norm = preflight["normalizer"]
    for key, field in (("input_mean", "input_mean_float64"), ("input_std", "input_std_float64"),
                       ("train_axis_rms_rad_s2", "train_axis_rms_rad_s2_float64")):
        expected = np.asarray(norm[field], dtype=np.float32)
        if not np.array_equal(state[key].detach().cpu().numpy(), expected):
            raise StopError("STOP_IDENTITY", f"checkpoint normalization buffer differs from canonical normalizer: {key}")

    spec = importlib.util.spec_from_file_location("cm18_c5_pinned_export_mapper", preflight["paths"][MAPPER_REL])
    if spec is None or spec.loader is None:
        raise StopError("STOP_IDENTITY", "cannot import pinned C524 export mapper")
    mapper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mapper)
    model_spec = importlib.util.spec_from_file_location("cm18_c5_pinned_numpy_model", preflight["paths"][NUMPY_MODEL_REL])
    if model_spec is None or model_spec.loader is None:
        raise StopError("STOP_IDENTITY", "cannot import pinned CM18 NumPy model")
    numpy_model = importlib.util.module_from_spec(model_spec)
    model_spec.loader.exec_module(numpy_model)
    parameters = mapper.parameters(state, norm)
    # Check the pinned mapper's parameter contract without an extra model forward.
    parameter_shapes = {
        "W1": (32, 18), "b1": (32,), "W2": (32, 32), "b2": (32,),
        "W3": (24, 32), "b3": (24,), "input_mean": (18,),
        "input_std": (18,), "train_axis_rms_rad_s2": (3,),
    }
    if set(parameters) != set(parameter_shapes):
        raise StopError("STOP_IDENTITY", "pinned exporter parameter keys differ from the fixed CM18 contract")
    for key, shape in parameter_shapes.items():
        if (parameters[key].shape != shape or parameters[key].dtype != np.float64
                or not np.isfinite(parameters[key]).all()):
            raise StopError("STOP_IDENTITY", f"pinned exporter parameter contract mismatch: {key}")
    return numpy_model, {"parameters": parameters,
                         "checkpoint_schema": checkpoint["schema"], "optimizer_step": checkpoint["optimizer_step"]}


def _predict_all(preflight: dict[str, Any], model_bundle: dict[str, Any], numpy_model: Any) -> None:
    import numpy as np

    all_scenes = preflight["train_scenes"] + preflight["dev_scenes"]
    x_all = np.ascontiguousarray(np.concatenate([scene["X18"] for scene in all_scenes]), dtype=np.float64)
    prediction = numpy_model.forward(x_all, model_bundle["parameters"])["physical_output_rad_s2"]
    if prediction.shape != (48 * 1_999, 3) or not np.isfinite(prediction).all():
        raise StopError("STOP_STATISTICS", "frozen model inference returned malformed/non-finite outputs")
    cursor = 0
    for scene in all_scenes:
        scene["prediction"] = np.ascontiguousarray(prediction[cursor:cursor + 1_999])
        cursor += 1_999
    if cursor != len(prediction):
        raise StopError("STOP_STATISTICS", "inference row accounting failed")
    preflight["inference_calls"] = 1
    preflight["inference_rows"] = int(len(prediction))


def _scene_meta(scene: dict[str, Any]) -> dict[str, str]:
    sid = scene["scene_id"]
    family = re.search(r"_(T[123])_", sid)
    wind = re.search(r"_W(\d{2})$", sid)
    if family is None or wind is None:
        raise StopError("STOP_STATISTICS", f"cannot parse fixed T/W group from scene ID: {sid}")
    return {"T_family": family.group(1), "W": "W" + wind.group(1)}


def _score_scene(scene: dict[str, Any], indices: Any, axis_rms: Any,
                 subset: str) -> dict[str, Any]:
    import numpy as np

    idx = np.asarray(indices, dtype=np.int64).reshape(-1)
    if len(idx) == 0 or np.any(idx < 0) or np.any(idx >= scene["event_count"]):
        raise StopError("STOP_STATISTICS", f"empty/invalid event subset {subset} for {scene['scene_id']}")
    y = scene["target"][idx]
    pred = scene["prediction"][idx]
    zeros = np.zeros_like(y)
    return {
        "split": scene["split"], "scene_id": scene["scene_id"], **_scene_meta(scene),
        "subset": subset, "event_count": int(len(idx)),
        "ordinal_min_zero_based": int(np.min(scene["ordinal_zero_based"][idx])),
        "ordinal_max_zero_based": int(np.max(scene["ordinal_zero_based"][idx])),
        "ordinal_sha256": hashlib.sha256(np.asarray(scene["ordinal_zero_based"][idx], dtype="<i8").tobytes()).hexdigest(),
        "candidate": _metrics(pred, y, axis_rms), "zero_output": _metrics(zeros, y, axis_rms),
    }


def _mean_metric(rows: list[dict[str, Any]], method: str) -> dict[str, float] | None:
    if not rows:
        return None
    return {key: float(sum(row[method][key] for row in rows) / len(rows)) for key in METRIC_NAMES}


def _finite_quantile(values: Any, q: float) -> float | str:
    import numpy as np

    arr = sorted(float(v) for v in values)
    if not arr:
        raise StopError("STOP_STATISTICS", "cannot form bootstrap percentile from empty replicate set")
    pos = (len(arr) - 1) * q
    low, high = int(math.floor(pos)), int(math.ceil(pos))
    if low == high:
        value = arr[low]
    else:
        alpha = pos - low
        a, b = arr[low], arr[high]
        if math.isinf(a) or math.isinf(b):
            value = math.inf if a >= 0 or b >= 0 else -math.inf
        else:
            value = a + alpha * (b - a)
    if math.isinf(value):
        return "+inf" if value > 0 else "-inf"
    if not math.isfinite(value):
        raise StopError("STOP_STATISTICS", "bootstrap percentile is non-finite")
    return float(value)


def _metric_bootstrap(rows: list[dict[str, Any]], method: str, rng: Any) -> dict[str, list[float | str] | None]:
    import numpy as np

    if not rows:
        return {key: None for key in METRIC_NAMES}
    values = np.asarray([[row[method][key] for key in METRIC_NAMES] for row in rows], dtype=np.float64)
    n = len(rows)
    reps = np.empty((BOOTSTRAP_REPLICATES, len(METRIC_NAMES)), dtype=np.float64)
    for rep in range(BOOTSTRAP_REPLICATES):
        picked = rng.integers(0, n, size=n)
        reps[rep] = np.mean(values[picked], axis=0)
    return {
        key: [_finite_quantile(reps[:, j], 0.025), _finite_quantile(reps[:, j], 0.975)]
        for j, key in enumerate(METRIC_NAMES)
    }


def _strata_summary(rows: list[dict[str, Any]], rng: Any, group_name: str,
                    missing_scene_ids: list[str] | None = None) -> dict[str, Any]:
    return {
        "group": group_name,
        "scene_count": len(rows),
        "event_count": int(sum(row["event_count"] for row in rows)),
        "scene_ids": [row["scene_id"] for row in rows],
        "missing_scene_ids": missing_scene_ids or [],
        "bootstrap_ci_unstable": len(rows) < 5,
        "candidate_macro": _mean_metric(rows, "candidate"),
        "candidate_ci95": _metric_bootstrap(rows, "candidate", rng),
        "zero_output_macro": _mean_metric(rows, "zero_output"),
        "zero_output_ci95": _metric_bootstrap(rows, "zero_output", rng),
    }


def _main_bootstrap(train_rows: list[dict[str, Any]], dev_rows: list[dict[str, Any]], rng: Any) -> dict[str, Any]:
    import numpy as np

    if len(train_rows) != 33 or len(dev_rows) != 15:
        raise StopError("STOP_STATISTICS", "main bootstrap requires exactly 33 TRAIN and 15 DEV scene blocks")
    train = np.asarray([r["candidate"]["normalized_vector_nrmse"] for r in train_rows], dtype=np.float64)
    dev = np.asarray([r["candidate"]["normalized_vector_nrmse"] for r in dev_rows], dtype=np.float64)
    if not np.isfinite(train).all() or not np.isfinite(dev).all():
        raise StopError("STOP_STATISTICS", "main bootstrap scene scores are non-finite")
    rep_t = np.empty(BOOTSTRAP_REPLICATES, dtype=np.float64)
    rep_d = np.empty(BOOTSTRAP_REPLICATES, dtype=np.float64)
    rep_delta = np.empty(BOOTSTRAP_REPLICATES, dtype=np.float64)
    rep_ratio = np.empty(BOOTSTRAP_REPLICATES, dtype=np.float64)
    zero_t_d = 0
    for rep in range(BOOTSTRAP_REPLICATES):
        t = float(np.mean(train[rng.integers(0, len(train), size=len(train))]))
        d = float(np.mean(dev[rng.integers(0, len(dev), size=len(dev))]))
        rep_t[rep], rep_d[rep], rep_delta[rep] = t, d, d - t
        if t == 0.0:
            if d > 0.0:
                rep_ratio[rep] = math.inf
                zero_t_d += 1
            else:
                rep_ratio[rep] = 1.0
        else:
            rep_ratio[rep] = d / t
    t_macro = float(np.mean(train))
    d_macro = float(np.mean(dev))
    if t_macro == 0.0:
        point_ratio: float | str = "+inf" if d_macro > 0.0 else 1.0
    else:
        point_ratio = d_macro / t_macro
    ci = {
        "TRAIN_NRMSE": [_finite_quantile(rep_t, 0.025), _finite_quantile(rep_t, 0.975)],
        "DEV_NRMSE": [_finite_quantile(rep_d, 0.025), _finite_quantile(rep_d, 0.975)],
        "DEV_minus_TRAIN": [_finite_quantile(rep_delta, 0.025), _finite_quantile(rep_delta, 0.975)],
        "DEV_over_TRAIN": [_finite_quantile(rep_ratio, 0.025), _finite_quantile(rep_ratio, 0.975)],
    }
    return {
        "replicates": BOOTSTRAP_REPLICATES, "seed": BOOTSTRAP_SEED,
        "sampling_unit": "scene block; TRAIN and DEV independently sampled with replacement",
        "zero_T_positive_D_replicates": int(zero_t_d),
        "T": t_macro, "D": d_macro, "D_minus_T": d_macro - t_macro,
        "D_over_T": point_ratio, "ci95_percentile": ci,
    }


def _decisions(t: float, d: float, ratio: float | str, ratio_ci: list[Any]) -> list[str]:
    labels: list[str] = []
    if t >= 1.0:
        labels.append("FIT_POOR")
    ratio_ge = (ratio == "+inf") or (isinstance(ratio, (float, int)) and float(ratio) >= 1.2)
    lower = ratio_ci[0]
    lower_gt_one = (lower == "+inf") or (isinstance(lower, (float, int)) and float(lower) > 1.0)
    if ratio_ge and lower_gt_one:
        labels.append("GENERALIZATION_GAP")
    if t <= 0.25 and d <= 0.25:
        labels.append("LOW_POINTWISE_ERROR_CLOSED_LOOP_GAP_REMAINS")
    if not labels:
        labels.append("INCONCLUSIVE")
    return labels


def _make_primary_scenes(preflight: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    import numpy as np

    indices = np.asarray(SAMPLE_ORDINALS, dtype=np.int64)
    train_rows = [_score_scene(scene, indices, preflight["axis_rms"], "primary_400_ordinals_0_5_1995")
                  for scene in preflight["train_scenes"]]
    dev_rows = [_score_scene(scene, indices, preflight["axis_rms"], "primary_400_ordinals_0_5_1995")
                for scene in preflight["dev_scenes"]]
    if len(train_rows) != 33 or len(dev_rows) != 15 or any(row["event_count"] != 400 for row in train_rows + dev_rows):
        raise StopError("STOP_STATISTICS", "primary fixed 400-row per-scene sample is incomplete")
    return train_rows, dev_rows


def _make_secondary(preflight: dict[str, Any], rng: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    import numpy as np

    rows: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    dev_scenes = preflight["dev_scenes"]
    all_idx = np.arange(1_999, dtype=np.int64)
    full_rows = [_score_scene(scene, all_idx, preflight["axis_rms"], "DEV_secondary_all_1999") for scene in dev_scenes]
    rows.extend(full_rows)
    summaries.append(_strata_summary(full_rows, rng, "DEV_all_1999"))

    first_rows: list[dict[str, Any]] = []
    missing_first: list[str] = []
    for scene in dev_scenes:
        idx = np.flatnonzero(np.isin(scene["phase"], (2, 4)))
        if len(idx) == 0:
            missing_first.append(scene["scene_id"])
        else:
            first_rows.append(_score_scene(scene, idx[:1], preflight["axis_rms"], "first_morph_event"))
    rows.extend(first_rows)
    summaries.append(_strata_summary(first_rows, rng, "DEV_first_morph_event", missing_first))

    phase_specs: list[tuple[str, Any]] = [("active_phase", np.isin(np.arange(6), (2, 4)))]
    phase_specs.extend((f"phase_code_{code}", code) for code in range(6))
    for label, code_or_mask in phase_specs:
        selected: list[dict[str, Any]] = []
        for scene in dev_scenes:
            mask = np.isin(scene["phase"], (2, 4)) if label == "active_phase" else scene["phase"] == code_or_mask
            idx = np.flatnonzero(mask)
            if len(idx):
                selected.append(_score_scene(scene, idx, preflight["axis_rms"], label))
        rows.extend(selected)
        summaries.append(_strata_summary(selected, rng, f"DEV_{label}",
                                         [s["scene_id"] for s in dev_scenes if s["scene_id"] not in {r["scene_id"] for r in selected}]))

    for w in range(16):
        label = f"W{w:02d}"
        selected = []
        for scene in dev_scenes:
            if _scene_meta(scene)["W"] == label:
                selected.append(_score_scene(scene, all_idx, preflight["axis_rms"], label))
        rows.extend(selected)
        summaries.append(_strata_summary(selected, rng, f"DEV_{label}"))
    hi_w = [scene for scene in dev_scenes if _scene_meta(scene)["W"] in {f"W{i:02d}" for i in range(9, 15)}]
    high_rows = [_score_scene(scene, all_idx, preflight["axis_rms"], "W09-W14") for scene in hi_w]
    rows.extend(high_rows)
    summaries.append(_strata_summary(high_rows, rng, "DEV_W09-W14"))
    return rows, summaries


def _flatten_primary(rows: list[dict[str, Any]], macros: dict[str, dict[str, float]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        split = row["split"]
        macro_split = "TRAIN" if split in ("TRAIN", "TRAIN_EXTRA") else split
        if macro_split not in macros:
            raise StopError("STOP_STATISTICS", f"primary split has no macro center: {split}")
        base = {key: row[key] for key in ("split", "scene_id", "T_family", "W", "subset", "event_count",
                                           "ordinal_min_zero_based", "ordinal_max_zero_based", "ordinal_sha256")}
        for method, prefix in (("candidate", "candidate"), ("zero_output", "zero_output")):
            for metric in METRIC_NAMES:
                base[f"{prefix}_{metric}"] = row[method][metric]
            if "normalized_vector_nrmse" in row[method]:
                base[f"{prefix}_normalized_vector_nrmse_centered_from_split_macro"] = (
                    row[method]["normalized_vector_nrmse"] - macros[macro_split][method]["normalized_vector_nrmse"])
        out.append(base)
    return out


def _assert_primary_flatten_splits() -> None:
    splits = ("TRAIN", "TRAIN_EXTRA", "HOLDOUT")
    rows = []
    for split, candidate_value, zero_value in zip(splits, (0.25, 0.75, 0.9), (0.3, 0.7, 0.95)):
        row = {"split": split, "scene_id": split, "T_family": "T1", "W": "W00", "subset": "primary",
               "event_count": 400, "ordinal_min_zero_based": 0, "ordinal_max_zero_based": 1995,
               "ordinal_sha256": "self-check"}
        row["candidate"] = {metric: 0.0 for metric in METRIC_NAMES}
        row["candidate"]["normalized_vector_nrmse"] = candidate_value
        row["zero_output"] = {metric: 0.0 for metric in METRIC_NAMES}
        row["zero_output"]["normalized_vector_nrmse"] = zero_value
        rows.append(row)
    macros = {"TRAIN": {"candidate": {"normalized_vector_nrmse": 0.5},
                         "zero_output": {"normalized_vector_nrmse": 0.5}},
              "HOLDOUT": {"candidate": {"normalized_vector_nrmse": 0.8},
                           "zero_output": {"normalized_vector_nrmse": 0.85}}}
    flat = _flatten_primary(rows, macros)
    assert [row["split"] for row in flat] == list(splits)
    candidate_centered = [row["candidate_normalized_vector_nrmse_centered_from_split_macro"] for row in flat]
    zero_centered = [row["zero_output_normalized_vector_nrmse_centered_from_split_macro"] for row in flat]
    assert all(math.isclose(a, b, abs_tol=1e-12) for a, b in zip(candidate_centered, (-0.25, 0.25, 0.1)))
    assert all(math.isclose(a, b, abs_tol=1e-12) for a, b in zip(zero_centered, (-0.2, 0.2, 0.1)))


def _flatten_secondary_scene(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        base = {key: row[key] for key in ("split", "scene_id", "T_family", "W", "subset", "event_count",
                                           "ordinal_min_zero_based", "ordinal_max_zero_based", "ordinal_sha256")}
        for method, prefix in (("candidate", "candidate"), ("zero_output", "zero_output")):
            for metric in METRIC_NAMES:
                base[f"{prefix}_{metric}"] = row[method][metric]
        out.append(base)
    return out


def _flatten_strata_summary(summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flat: list[dict[str, Any]] = []
    for summary in summaries:
        row: dict[str, Any] = {
            "group": summary["group"], "scene_count": summary["scene_count"],
            "event_count": summary["event_count"], "bootstrap_ci_unstable": summary["bootstrap_ci_unstable"],
            "scene_ids": ";".join(summary["scene_ids"]), "missing_scene_ids": ";".join(summary["missing_scene_ids"]),
        }
        for method, prefix in (("candidate", "candidate"), ("zero_output", "zero_output")):
            macro_key = f"{method}_macro"
            ci_key = f"{method}_ci95"
            macro = summary[macro_key]
            ci = summary[ci_key]
            for metric in METRIC_NAMES:
                row[f"{prefix}_{metric}"] = None if macro is None else macro[metric]
                interval = ci[metric]
                row[f"{prefix}_{metric}_ci95_low"] = None if interval is None else interval[0]
                row[f"{prefix}_{metric}_ci95_high"] = None if interval is None else interval[1]
        flat.append(row)
    return flat


def _csv_write(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise StopError("STOP_STATISTICS", f"refusing to write empty CSV: {path.name}")
    fields: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                fields.append(key)
                seen.add(key)
    with path.open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)
        stream.flush()
        os.fsync(stream.fileno())


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if hasattr(value, "item"):
        return _json_safe(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return "+inf" if value > 0 else "-inf"
    return value


def _json_write(path: Path, payload: Any) -> None:
    raw = json.dumps(_json_safe(payload), ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8") + b"\n"
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _fmt(value: Any, digits: int = 6) -> str:
    if value is None:
        return "—"
    if isinstance(value, str):
        return value
    return f"{float(value):.{digits}f}"


def _make_report(summary: dict[str, Any]) -> str:
    main = summary["main_comparison"]
    boot = main["bootstrap"]
    dec = ", ".join(main["decision_labels"])
    lines = [
        "# C5_COVERAGE33 冻结模型拟合与跨场离线诊断",
        "",
        "本报告只比较同一个冻结 CM18 checkpoint 对 TRAIN/DEV cache 中直接 `Cstar/beta` 标签的纯前向逐点残差。它不是闭环结果，也不是独立测试或 TEST 泛化结论。",
        "",
        "## 主比较（每场 ordinal 0,5,…,1995 共 400 行）",
        "",
        "| 项目 | 值 | scene-block bootstrap 95% CI |",
        "|---|---:|---:|",
        f"| TRAIN_NRMSE T | {_fmt(boot['T'])} | {_fmt(boot['ci95_percentile']['TRAIN_NRMSE'][0])} – {_fmt(boot['ci95_percentile']['TRAIN_NRMSE'][1])} |",
        f"| DEV_NRMSE D | {_fmt(boot['D'])} | {_fmt(boot['ci95_percentile']['DEV_NRMSE'][0])} – {_fmt(boot['ci95_percentile']['DEV_NRMSE'][1])} |",
        f"| D − T | {_fmt(boot['D_minus_T'])} | {_fmt(boot['ci95_percentile']['DEV_minus_TRAIN'][0])} – {_fmt(boot['ci95_percentile']['DEV_minus_TRAIN'][1])} |",
        f"| D / T | {_fmt(boot['D_over_T'])} | {_fmt(boot['ci95_percentile']['DEV_over_TRAIN'][0])} – {_fmt(boot['ci95_percentile']['DEV_over_TRAIN'][1])} |",
        "",
        f"预注册标签：**{dec}**。T=0,D>0 的 ratio replicate 数：{boot['zero_T_positive_D_replicates']} / {boot['replicates']}。区间按 scene block 独立重抽 TRAIN 33 场与 DEV 15 场，不重抽事件行。",
        "",
        "## 固定分割与校验",
        "",
        f"TRAIN 33 场：T1/T2/T3 = {summary['preflight']['train_t_family_counts']['T1']}/{summary['preflight']['train_t_family_counts']['T2']}/{summary['preflight']['train_t_family_counts']['T3']}；DEV 15 场：{summary['preflight']['dev_t_family_counts']['T1']}/{summary['preflight']['dev_t_family_counts']['T2']}/{summary['preflight']['dev_t_family_counts']['T3']}。",
        f"重建 row-map SHA：`{summary['preflight']['row_map_sha256_reconstructed']}`；sample-stream SHA：`{summary['preflight']['sample_index_stream_sha256_reconstructed']}`。",
        f"所有 cache：{summary['preflight']['cache_count']} / {summary['preflight']['cache_expected']} 个通过身份、时钟、行图与 Cstar/beta 闭合；最大标签闭合误差 {_fmt(summary['preflight']['max_label_closure_abs'], 12)} rad/s²。",
        "",
        "## 附加 DEV 分层",
        "",
        "附加分层不改变主判定；少于 5 场的区间标为不稳定，仅作描述。每场先计算指标，再按场景等权汇总。",
        "",
        "| 分层 | 场数 | 事件数 | 候选宏平均 normalized vector NRMSE | 95% CI |",
        "|---|---:|---:|---:|---:|",
    ]
    for item in summary["secondary_strata"]:
        macro = item["candidate_macro"]
        ci = item["candidate_ci95"]["normalized_vector_nrmse"]
        if macro is None:
            score, interval = "—", "—"
        else:
            score = _fmt(macro["normalized_vector_nrmse"])
            interval = f"{_fmt(ci[0])} – {_fmt(ci[1])}" if ci is not None else "—"
        lines.append(f"| {item['group']} | {item['scene_count']} | {item['event_count']} | {score} | {interval} |")
    lines.extend([
        "",
        "TRAIN 与 DEV 各自的逐场物理/归一化 RMSE、signed bias、向量 bias、零输出基线以及中心化差值见 `primary_scene_metrics.csv`；DEV 全事件与分层逐场结果见 `secondary_scene_metrics.csv`，场景等权摘要和 bootstrap 区间见 `secondary_strata_summary.csv`。",
        "",
        "## 范围与资源回执",
        "",
        f"本评估只读取 allowlist 中的 33 TRAIN 与 15 DEV EVENTS cache；固定 checkpoint 共执行 {summary['inference']['calls']} 次 NumPy 前向、处理 {summary['inference']['rows']} 行；不读取 raw MAT、不读取 C5_VAL48/TEST、不训练、不调用 Plant/engine、不启动闭环。训练步数、optimizer steps、Plant calls、engine calls 与 episode calls 均为 0。",
        "",
        f"Taskbook SHA：`{summary['taskbook_sha256']}`；checkpoint SHA：`{summary['checkpoint_sha256']}`；model SHA：`{summary['model_sha256']}`；normalizer SHA：`{summary['normalizer_sha256']}`。",
        "",
        "该结果仅诊断此 checkpoint 在固定 33 TRAIN / 15 DEV cache 标签上的逐点拟合差异；它不代表轨迹级闭环效能、其它场景总体表现或独立测试。",
        "",
    ])
    return "\n".join(lines)


def _input_inventory(preflight: dict[str, Any]) -> list[dict[str, Any]]:
    records = [{"path": rel, "sha256": sha} for rel, sha in sorted(EXPECTED_FILES.items())]
    for scene in preflight["train_scenes"] + preflight["dev_scenes"]:
        records.append({"path": scene["cache_path"], "sha256": scene["cache_sha256"],
                        "scene_id": scene["scene_id"], "split": scene["split"]})
    return records


def _scene_preflight_rows(preflight: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    ordinals = list(SAMPLE_ORDINALS)
    for scene in preflight["train_scenes"] + preflight["dev_scenes"]:
        rows.append({
            "scene_id": scene["scene_id"], "split": scene["split"],
            "cache_path": scene["cache_path"], "cache_sha256": scene["cache_sha256"],
            "event_count": scene["event_count"], "event_index_one_based_start": 1,
            "event_index_one_based_end": 1999,
            "primary_ordinal_count": len(ordinals), "primary_ordinals_zero_based": ordinals,
            "ordinal_map_rule": "zero_based_ordinal = event_index - 1; each TRAIN/DEV primary subset uses exact ordinals 0,5,...,1995",
            "manifest_declared_closure_max_abs_rad_s2": scene["manifest_declared_closure_max_abs"],
            "label_closure_max_abs_rad_s2": scene["label_closure_max_abs"],
            "residual_closure_max_abs_rad_s2": scene["residual_closure_max_abs"],
            "clip_closure_max_abs_rad_s2": scene["clip_closure_max_abs"],
        })
    return rows


def _write_outputs(preflight: dict[str, Any], model_bundle: dict[str, Any],
                   primary_train: list[dict[str, Any]], primary_dev: list[dict[str, Any]],
                   secondary_rows: list[dict[str, Any]], secondary_summary: list[dict[str, Any]],
                   main_bootstrap: dict[str, Any], runtime_versions: dict[str, str],
                   command: str, started_utc: str, elapsed_seconds: float) -> dict[str, Any]:
    import numpy as np

    output = _assert_output_path_safe(preflight["root"])
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise StopError("STOP_IDENTITY", "output directory became non-empty before publication")
    root_real = preflight["root"].resolve(strict=True)
    stage_parent = output.parent.resolve(strict=True)
    try:
        stage_parent.relative_to(root_real)
    except ValueError as exc:
        raise StopError("STOP_IDENTITY", "staging parent escapes project root") from exc
    stage: Path | None = Path(tempfile.mkdtemp(prefix=f".{output.name}.stage_", dir=stage_parent))
    try:
        train_macro = {
            method: _mean_metric(primary_train, method) for method in ("candidate", "zero_output")
        }
        dev_macro = {
            method: _mean_metric(primary_dev, method) for method in ("candidate", "zero_output")
        }
        macros = {"TRAIN": train_macro, "HOLDOUT": dev_macro}
        primary_flat = _flatten_primary(primary_train + primary_dev, macros)
        secondary_flat = _flatten_secondary_scene(secondary_rows)
        strata_flat = _flatten_strata_summary(secondary_summary)
        _csv_write(stage / "primary_scene_metrics.csv", primary_flat)
        _csv_write(stage / "secondary_scene_metrics.csv", secondary_flat)
        _csv_write(stage / "secondary_strata_summary.csv", strata_flat)
        threshold_labels = _decisions(main_bootstrap["T"], main_bootstrap["D"],
                                      main_bootstrap["D_over_T"], main_bootstrap["ci95_percentile"]["DEV_over_TRAIN"])
        all_scenes = preflight["train_scenes"] + preflight["dev_scenes"]
        summary = {
            "schema": "CM18_C5_COVERAGE33_FIT_GENERALIZATION_RESULT_V1",
            "scope": "frozen checkpoint pointwise cache-label diagnostics; TRAIN in-sample rows vs fixed scene-blocked DEV",
            "taskbook_sha256": EXPECTED_FILES[TASKBOOK_REL],
            "script_path": SCRIPT_REL, "script_sha256": preflight["script_sha256"],
            "allowlist_path": ALLOWLIST_REL, "allowlist_sha256": _sha(preflight["allowlist_path"]),
            "command": command,
            "input_files": _input_inventory(preflight),
            "checkpoint_sha256": EXPECTED_FILES[CHECKPOINT_REL],
            "model_sha256": EXPECTED_FILES[MODEL_REL],
            "model_id": "C5_COVERAGE33", "checkpoint_schema": model_bundle["checkpoint_schema"],
            "checkpoint_optimizer_step": model_bundle["optimizer_step"],
            "inference": {"calls": preflight["inference_calls"], "rows": preflight["inference_rows"],
                          "deterministic": True, "model_forward": "pinned NumPy CM18 model once over concatenated fixed 48 caches"},
            "normalizer_sha256": EXPECTED_FILES[NORMALIZER_REL],
            "normalizer_canonical_sha256": preflight["normalizer"]["canonical_float64_sha256"],
            "normalizer_input_mean_float64": preflight["input_mean"].tolist(),
            "normalizer_input_std_float64": preflight["input_std"].tolist(),
            "normalizer_output_axis_rms_rad_s2_float64": preflight["axis_rms"].tolist(),
            "runtime": {"python": sys.version, "platform": platform.platform(), "packages": runtime_versions,
                        "OMP_NUM_THREADS": os.environ.get("OMP_NUM_THREADS"),
                        "MKL_NUM_THREADS": os.environ.get("MKL_NUM_THREADS")},
            "preflight": {
                "cache_count": len(all_scenes), "cache_expected": 48,
                "train_scene_count": 33, "dev_scene_count": 15,
                "train_t_family_counts": preflight["train_t_family_counts"],
                "dev_t_family_counts": preflight["dev_t_family_counts"],
                "manifest_scene_order_matches": True, "binding_scene_order_matches": True,
                "audit_identity_crosscheck": "PASS",
                "train_dev_scene_intersection": [],
                "row_map_sha256_reconstructed": preflight["row_map_sha256"],
                "sample_index_stream_sha256_reconstructed": preflight["sample_stream_sha256"],
                "sample_ordinals_zero_based": list(SAMPLE_ORDINALS),
                "scene_cache_audit": _scene_preflight_rows(preflight),
                "max_label_closure_abs": float(max(s["label_closure_max_abs"] for s in all_scenes)),
                "max_residual_closure_abs": float(max(s["residual_closure_max_abs"] for s in all_scenes)),
                "max_clip_closure_abs": float(max(s["clip_closure_max_abs"] for s in all_scenes)),
            },
            "primary": {
                "rows_per_scene": 400, "ordinal_rule": "zero-based event ordinal 0,5,...,1995",
                "train_scene_macro_candidate": train_macro["candidate"],
                "train_scene_macro_zero_output": train_macro["zero_output"],
                "dev_scene_macro_candidate": dev_macro["candidate"],
                "dev_scene_macro_zero_output": dev_macro["zero_output"],
                "train_scene_rows": primary_train, "dev_scene_rows": primary_dev,
            },
            "main_comparison": {"bootstrap": main_bootstrap, "decision_labels": threshold_labels,
                                "criteria": {"FIT_POOR": "T >= 1.0", "GENERALIZATION_GAP": "D/T >= 1.2 and ratio-CI lower > 1",
                                             "LOW_POINTWISE_ERROR_CLOSED_LOOP_GAP_REMAINS": "T <= 0.25 and D <= 0.25"}},
            "secondary_strata": secondary_summary,
            "resource_counters": {"training_steps": 0, "optimizer_steps": 0, "Plant_calls": 0,
                                  "engine_calls": 0, "episode_calls": 0, "TEST_accessed": False},
            "started_at_utc": started_utc, "elapsed_seconds": elapsed_seconds,
            "final_report_path": f"{OUTPUT_REL}/FIT_GENERALIZATION_REPORT_v1_ZH.md",
        }
        _json_write(stage / "summary.json", summary)
        report = _make_report(summary).encode("utf-8")
        with (stage / "FIT_GENERALIZATION_REPORT_v1_ZH.md").open("xb") as stream:
            stream.write(report)
            stream.flush()
            os.fsync(stream.fileno())
        report_sha = _sha(stage / "FIT_GENERALIZATION_REPORT_v1_ZH.md")
        file_hashes = {p.name: _sha(p) for p in sorted(stage.iterdir()) if p.is_file()}
        receipt = {
            "schema": "CM18_C5_COVERAGE33_FIT_GENERALIZATION_RECEIPT_V1",
            "status": "PASS", "scope": "offline frozen-checkpoint inference only",
            "taskbook_path": TASKBOOK_REL, "taskbook_sha256": EXPECTED_FILES[TASKBOOK_REL],
            "script_path": SCRIPT_REL, "script_sha256": preflight["script_sha256"],
            "allowlist_path": ALLOWLIST_REL, "allowlist_sha256": _sha(preflight["allowlist_path"]),
            "exact_command": command,
            "input_files": _input_inventory(preflight),
            "final_report_path": f"{OUTPUT_REL}/FIT_GENERALIZATION_REPORT_v1_ZH.md",
            "final_report_sha256": report_sha,
            "published_file_sha256": file_hashes,
            "training_steps": 0, "optimizer_steps": 0, "Plant_calls": 0,
            "engine_calls": 0, "episode_calls": 0, "TEST_accessed": False,
            "inference_calls": preflight["inference_calls"], "inference_rows": preflight["inference_rows"],
            "runtime": {"python": sys.version, "platform": platform.platform(), "packages": runtime_versions},
            "started_at_utc": started_utc, "elapsed_seconds": elapsed_seconds,
        }
        _json_write(stage / "run_receipt.json", receipt)
        total = sum(p.stat().st_size for p in stage.iterdir() if p.is_file())
        if total > MAX_OUTPUT_BYTES:
            raise StopError("STOP_STATISTICS", f"result bundle exceeds {MAX_OUTPUT_BYTES} bytes")
        _assert_output_path_safe(preflight["root"])
        if output.exists():
            if not output.is_dir() or any(output.iterdir()):
                raise StopError("STOP_IDENTITY", f"refusing to replace non-empty output directory: {output}")
            output.rmdir()
        stage_info = stage.lstat()
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        if (not stat.S_ISDIR(stage_info.st_mode)
                or stat.S_ISLNK(stage_info.st_mode)
                or (getattr(stage_info, "st_file_attributes", 0) & reparse_flag)
                or stage.parent.resolve(strict=True) != stage_parent):
            raise StopError("STOP_IDENTITY", "staging directory identity changed before publication")
        try:
            stage.resolve(strict=True).relative_to(stage_parent)
        except (OSError, ValueError) as exc:
            raise StopError("STOP_IDENTITY", "staging directory escapes its project-local parent") from exc
        os.replace(stage, output)
        stage = None
        return {"output_path": output.relative_to(preflight["root"]).as_posix(),
                "report_sha256": report_sha, "files": file_hashes,
                "receipt_path": f"{OUTPUT_REL}/run_receipt.json", "output_bytes": total}
    finally:
        if stage is not None:
            try:
                stage_info = stage.lstat()
            except FileNotFoundError:
                stage_info = None
            if stage_info is not None:
                reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
                if (not stat.S_ISDIR(stage_info.st_mode) or stat.S_ISLNK(stage_info.st_mode)
                        or (getattr(stage_info, "st_file_attributes", 0) & reparse_flag)
                        or not stage.name.startswith(f".{output.name}.stage_")
                        or stage.parent.resolve(strict=True) != stage_parent):
                    raise StopError("STOP_IDENTITY", "refusing to clean an unexpected staging path")
                try:
                    stage.resolve(strict=True).relative_to(stage_parent)
                    stage.resolve(strict=True).relative_to(root_real)
                except (OSError, ValueError) as exc:
                    raise StopError("STOP_IDENTITY", "staging cleanup path escapes the project version directory") from exc
                shutil.rmtree(stage)


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def main() -> int:
    _assert_primary_flatten_splits()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--taskbook", required=True)
    parser.add_argument("--train-release", dest="train_release", required=True)
    parser.add_argument("--relabel-manifest", dest="relabel_manifest", required=True)
    parser.add_argument("--closed-loop-binding", dest="closed_loop_binding", required=True)
    parser.add_argument("--normalizer", required=True)
    parser.add_argument("--audit-dir", dest="audit_dir", required=True)
    parser.add_argument("--output-dir", dest="output_dir", required=True)
    args = parser.parse_args()
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"
    started = _utc_now()
    start = time.monotonic()
    command = "\n".join([
        "$env:OMP_NUM_THREADS = '1'", "$env:MKL_NUM_THREADS = '1'",
        f"python -B {SCRIPT_REL} `",
        f"  --taskbook {TASKBOOK_REL} `", f"  --train-release {RELEASE_REL} `",
        f"  --relabel-manifest {MANIFEST_REL} `", f"  --closed-loop-binding {BINDING_REL} `",
        f"  --normalizer {NORMALIZER_REL} `", f"  --audit-dir {AUDIT_DIR_REL} `",
        f"  --output-dir {OUTPUT_REL}",
    ])
    try:
        root = ROOT.resolve(strict=True)
        preflight = _preflight(root, args)
        numpy_model, model_bundle = _load_frozen_model(preflight)
        _predict_all(preflight, model_bundle, numpy_model)
        primary_train, primary_dev = _make_primary_scenes(preflight)
        rng = __import__("numpy").random.default_rng(BOOTSTRAP_SEED)
        main_bootstrap = _main_bootstrap(primary_train, primary_dev, rng)
        # Metric CIs are separate scene-level resamples; each scene remains one bootstrap block.
        primary_train_summary = {
            method: _metric_bootstrap(primary_train, method, rng) for method in ("candidate", "zero_output")
        }
        primary_dev_summary = {
            method: _metric_bootstrap(primary_dev, method, rng) for method in ("candidate", "zero_output")
        }
        secondary_rows, secondary_summary = _make_secondary(preflight, rng)
        # Add the primary macro metric intervals without changing the registered T/D ratio gate.
        main_bootstrap["TRAIN_metric_ci95"] = primary_train_summary
        main_bootstrap["DEV_metric_ci95"] = primary_dev_summary
        elapsed = time.monotonic() - start
        result = _write_outputs(preflight, model_bundle, primary_train, primary_dev, secondary_rows,
                                secondary_summary, main_bootstrap, preflight["runtime_versions"], command, started, elapsed)
        print(json.dumps({"status": "PASS", **result}, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except StopError as exc:
        print(json.dumps({"status": exc.code, "reason": str(exc), "TEST_accessed": False},
                         ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    except Exception as exc:
        print(json.dumps({"status": "STOP_STATISTICS", "reason": f"{type(exc).__name__}: {exc}",
                          "TEST_accessed": False}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

