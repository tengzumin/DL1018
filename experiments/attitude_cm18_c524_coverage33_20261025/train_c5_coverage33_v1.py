"""Train the frozen C5_COVERAGE33 CM18 attitude candidate."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import random
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TASKBOOK = "reports/attitude_cm18_c524_screen12_20261025/C524_COVERAGE33_TASKBOOK_v2_ZH.md"
TASKBOOK_SHA = "934fc1b8a614c5a32993add65a0aee89d48e7c31ea368646063e5576b78c7017"
RELABELER = "experiments/attitude_cm18_c524_coverage33_20261025/relabel_c524_coverage33_v1.m"
RELABEL_MANIFEST = "experiments/attitude_cm18_c524_coverage33_20261025/data/C524_COVERAGE33_RELABEL_MANIFEST_v1.json"
RELABEL_MANIFEST_SHA = "7d6a7d079d32120849cee62eadecd8e69a68d5a538608dd8959849ac5fe2dd8c"
OLD_TRAIN_RELEASE = "reports/attitude_cm18_datarepair_20261024/ROOT_B24_C524_C5_24_TRAINING_RELEASE_v1.json"
OLD_TRAIN_RELEASE_SHA = "5c42d2e613d8075899cbb03e492d756a6f7f58b3a73f257fa11d5e7eee03d3b0"
C5_RUNS = "experiments/position_axis_coordinate_c5_dev72_20261023/runs_dev72_v3"
C5_CANDIDATE_DIR = "C5_AXIS_MASK_M110/attempt_01"
C5_CANDIDATE = "C5_AXIS_MIXED_COORDINATE_M110"
C5_FROZEN_FILES_SHA = {
    "experiments/position_axis_coordinate_c5_dev72_20261023/C5_DEV72_INPUT_LOCK_v3.json":
        "82024c01276cc4bfbd9b7772cf5332dee3fdfcbed422969589b68f1c90ed2d75",
    "experiments/position_axis_coordinate_c5_dev72_20261023/C5_DEV72_PREPARED_CFG_OPTS_v3.mat":
        "842ef395569e675db6e139c2684d72b976946915e5e0a58b9b7f24ec10c1d24a",
    "experiments/position_axis_coordinate_c5_dev72_20261023/C5_DEV72_RELEASE_v3.json":
        "4177f92a83a2a2ba80a98b3a8fb2f7806d64c3e6322ff3ce637a605db319f053",
    "experiments/position_axis_coordinate_c5_dev72_20261023/C5_DEV72_RUN_CONTRACT_v3.json":
        "6ac3cd505dc13fc5b7e6e0cdef966b21225b54d6f847d32177d43f7c678c8150",
}
OLD_TRAINER = "experiments/attitude_position_context_probe_20261024/b24_c524_paired_v1/train_cm18_b24_c524_paired_v1.py"
READER = "experiments/attitude_position_context_probe_20261024/b24_c524_paired_v1/read_b24_c524_paired_v1.py"
NUMPY_MODEL = "experiments/attitude_cm18_a1_20261024/model_cm18_v1.py"
TORCH_MODEL = "experiments/attitude_cm18_a1_20261024/torch_model_cm18_v1.py"
SOURCE_SHA = {
    OLD_TRAINER: "8e3a1155661d58456f8c4e3d5adeb72ddcd9b1d96d5ff358b68fdd97c7ecf70b",
    READER: "18453497548f39be472bfc197360d1bb86dedf14ae76e5a7cce31261c83fa8bd",
    NUMPY_MODEL: "ad32c4f97bf96c63172547c944d80c45062502f1062b774934e0f7a868720cf6",
    TORCH_MODEL: "bc9fe34fe957cb624438eeccfdfe2ddd38ad40cc9a4e706ce58863c9271d5aa0",
}
NORMALIZER = "experiments/attitude_cm18_datarepair_20261024/training_a1t_v1/normalizer.json"
NORMALIZER_SHA = "23e8432f4a1c3f71bfaaa4e3a7b07c4b9f6b0201842e35ba3bcb032ac61fd781"
INITIAL = "experiments/attitude_cm18_datarepair_20261024/training_a1t_v1/initial_parameters.npz"
INITIAL_SHA = "1f3a469eeb648345bacf6f6aa3be906e10efebc91e24442914fd32e880439cb2"
CANONICAL_NORMALIZER_SHA = "12c864b9c2404235e0ea3f313bb0801a99902eca7cfdfbf43f0d8d584d5d609a"
CONFIG_PATH = "reports/attitude_cm18_c524_coverage33_20261025/C5_COVERAGE33_TRAINING_RELEASE_v1.json"
OUTPUT = "experiments/attitude_cm18_c524_coverage33_20261025/training_C5_COVERAGE33_v1"
SEED, STEPS, BATCH, PROGRESS_EVERY = 2026102001, 60_000, 512, 1_000
SAMPLE_ORDINALS = list(range(0, 1996, 5))
PLANT_INDEX = list(range(11, 20_000, 10))
EXPECTED_EXTRA = [
    "DL1018_DEV_T1_C01_W15", "DL1018_DEV_T1_C00_W03", "DL1018_DEV_T1_C15_W14",
    "DL1018_DEV_T1_C05_W06", "DL1018_DEV_T2_C00_W04", "DL1018_DEV_T2_C06_W07",
    "DL1018_DEV_T3_C00_W05", "DL1018_DEV_T3_C15_W14", "DL1018_DEV_T3_C05_W02",
]
EXPECTED_HOLDOUT = [
    "DL1018_DEV_T2_C02_W15", "DL1018_DEV_T3_C03_W15", "DL1018_DEV_T1_C04_W00",
    "DL1018_DEV_T1_C07_W08", "DL1018_DEV_T1_C10_W09", "DL1018_DEV_T1_C11_W12",
    "DL1018_DEV_T2_C03_W01", "DL1018_DEV_T2_C08_W08", "DL1018_DEV_T2_C09_W10",
    "DL1018_DEV_T2_C12_W13", "DL1018_DEV_T2_C14_W14", "DL1018_DEV_T3_C06_W08",
    "DL1018_DEV_T3_C09_W09", "DL1018_DEV_T3_C10_W11", "DL1018_DEV_T3_C13_W12",
]
MAX_OUTPUT_BYTES, MIN_FREE_BYTES = 1 << 30, 30 * 1024**3


def _set_math_environment() -> None:
    if os.environ.get("KMP_DUPLICATE_LIB_OK"):
        raise RuntimeError("KMP_DUPLICATE_LIB_OK is forbidden")
    os.environ.update(MKL_THREADING_LAYER="SEQUENTIAL", OMP_NUM_THREADS="1",
                      MKL_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1",
                      CUBLAS_WORKSPACE_CONFIG=":4096:8")


_set_math_environment()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _path(root: Path, rel: str) -> Path:
    base = root.resolve(strict=True)
    p = (base / rel).resolve(strict=True)
    p.relative_to(base)
    return p


def _json(path: Path) -> dict[str, Any]:
    obj = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(obj, dict):
        raise ValueError(f"expected JSON object: {path}")
    return obj


def _new_json(path: Path, obj: Any) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite frozen artifact: {path}")
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("x", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _module(root: Path, rel: str, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, _path(root, rel))
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load pinned module {rel}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _text(group: Any, key: str) -> str:
    raw = group[key][()]
    arr = raw.reshape(-1)
    if arr.dtype.kind in "ui":
        return "".join(chr(int(c)) for c in arr if int(c))
    return "".join(str(x) for x in arr).strip("\x00")


def _extra_scene(root: Path, row: dict[str, Any], np: Any, h5py: Any) -> dict[str, Any]:
    path = _path(root, row["event_cache_path"])
    if _sha(path) != row["event_cache_sha256"].lower():
        raise ValueError(f"extra C5 cache SHA mismatch: {row['scene_id']}")
    with h5py.File(path, "r") as f:
        e = f["events"]
        if (_text(e, "schema") != "CM18_C5_COVERAGE33_EVENTS_V1"
                or _text(e, "scene_id") != row["scene_id"]
                or _text(e, "split") != "TRAIN_EXTRA"):
            raise ValueError(f"extra C5 cache identity mismatch: {row['scene_id']}")
        x = np.asarray(e["X18"], dtype=np.float64).T
        y = np.asarray(e["target_raw_output_rad_s2"], dtype=np.float64).T
        cstar = np.asarray(e["target_applied_acceleration_rad_s2"], dtype=np.float64).T
        after_clip = np.asarray(e["target_after_clip_beta_rad_s2"], dtype=np.float64).T
        e0 = np.asarray(e["E0_rad_s2"], dtype=np.float64).T
        gflat = np.asarray(e["G_row_major"], dtype=np.float64).T
        beta = np.asarray(e["beta"], dtype=np.float64).reshape(-1)
        ordinal_raw = np.asarray(e["event_index"], dtype=np.float64).reshape(-1)
        plant_raw = np.asarray(e["plant_index"], dtype=np.float64).reshape(-1)
        event_time = np.asarray(e["event_time_s"], dtype=np.float64).reshape(-1)
        phase_raw = np.asarray(e["phase_code"], dtype=np.float64).reshape(-1)
    if (not np.array_equal(ordinal_raw, np.round(ordinal_raw))
            or not np.array_equal(plant_raw, np.round(plant_raw))
            or not np.array_equal(phase_raw, np.round(phase_raw))):
        raise ValueError(f"extra C5 event clock contains noninteger indices: {row['scene_id']}")
    ordinal = ordinal_raw.astype(np.int64)
    plant = plant_raw.astype(np.int64)
    phase = phase_raw.astype(np.int64)
    if (x.shape != (1999, 18) or y.shape != (1999, 3) or cstar.shape != (1999, 3)
            or after_clip.shape != (1999, 3) or e0.shape != (1999, 3)
            or gflat.shape != (1999, 9) or beta.shape != (1999,)
            or event_time.shape != (1999,) or phase.shape != (1999,)
            or not all(np.isfinite(a).all() for a in (x, y, cstar, after_clip, e0, gflat, beta, event_time))
            or not np.array_equal(ordinal, np.arange(1, 2000))
            or not np.array_equal(plant, np.asarray(PLANT_INDEX))
            or np.any((phase < 0) | (phase > 5))):
        raise ValueError(f"extra C5 arrays/clock malformed: {row['scene_id']}")
    beta_expected = np.minimum(plant.astype(np.float64) * 0.001 / 2.2, 1.0)
    event_time_expected = (plant.astype(np.float64) - 1.0) * 0.001
    if (np.max(np.abs(beta - beta_expected)) > 1e-12
            or np.max(np.abs(event_time - event_time_expected)) > 1e-12):
        raise ValueError(f"extra C5 beta/event-time clock mismatch: {row['scene_id']}")
    g = gflat.reshape(1999, 3, 3)
    if (np.max(np.abs(y - cstar / beta[:, None])) > 1e-9
            or np.max(np.abs(e0 - np.einsum("nij,nj->ni", g, cstar))) > 1e-8
            or np.max(np.abs(after_clip - beta[:, None] * np.clip(
                y, -np.asarray([45.0, 45.0, 4.7124]), np.asarray([45.0, 45.0, 4.7124])))) > 1e-9):
        raise ValueError(f"extra C5 direct-label closure failed: {row['scene_id']}")
    return {"scene_id": row["scene_id"], "X18": x, "target_raw_output_rad_s2": y,
            "plant_index": plant, "cache_path": row["event_cache_path"],
            "cache_sha256": row["event_cache_sha256"]}


def _check_c5_provenance(root: Path, rows: list[dict[str, Any]], split: str) -> None:
    for row in rows:
        scene_id = row["scene_id"]
        if row.get("split") != split:
            raise ValueError(f"C5 provenance split mismatch: {scene_id}")
        run_dir = f"{C5_RUNS}/{scene_id}/{C5_CANDIDATE_DIR}"
        expected = {
            "c5_raw_path": f"{run_dir}/raw_run.mat",
            "c5_run_start_path": f"{run_dir}/run_start.mat",
            "c5_run_status_path": f"{run_dir}/run_status.json",
        }
        actual_paths: dict[str, Path] = {}
        for field, expected_rel in expected.items():
            actual = _path(root, row[field])
            pinned = _path(root, expected_rel)
            if os.path.normcase(str(actual)) != os.path.normcase(str(pinned)):
                raise ValueError(f"C5 provenance path mismatch: {scene_id} {field}")
            actual_paths[field] = actual

        digests = {
            "c5_raw_path": row["c5_raw_sha256"],
            "c5_run_start_path": row["c5_run_start_sha256"],
            "c5_run_status_path": row["c5_run_status_sha256"],
        }
        for field, expected_sha in digests.items():
            if _sha(actual_paths[field]) != str(expected_sha).lower():
                raise ValueError(f"C5 provenance file SHA mismatch: {scene_id} {field}")

        status = _json(actual_paths["c5_run_status_path"])
        status_paths = {
            "raw_path": expected["c5_raw_path"],
            "run_start_path": expected["c5_run_start_path"],
            "run_status_path": expected["c5_run_status_path"],
        }
        for field, expected_rel in status_paths.items():
            status_path = _path(root, status[field])
            pinned = _path(root, expected_rel)
            if os.path.normcase(str(status_path)) != os.path.normcase(str(pinned)):
                raise ValueError(f"C5 status path mismatch: {scene_id} {field}")
        if (status.get("scene_id") != scene_id
                or status.get("candidate") != C5_CANDIDATE
                or status.get("coordinate_mask") != [1, 1, 0]
                or str(status.get("raw_sha256", "")).lower() != str(row["c5_raw_sha256"]).lower()
                or str(status.get("run_start_sha256", "")).lower()
                    != str(row["c5_run_start_sha256"]).lower()):
            raise ValueError(f"C5 status identity/SHA binding mismatch: {scene_id}")
        frozen_sha = {
            "input_lock_sha256": C5_FROZEN_FILES_SHA[
                "experiments/position_axis_coordinate_c5_dev72_20261023/C5_DEV72_INPUT_LOCK_v3.json"],
            "cfg_opts_snapshot_sha256": C5_FROZEN_FILES_SHA[
                "experiments/position_axis_coordinate_c5_dev72_20261023/C5_DEV72_PREPARED_CFG_OPTS_v3.mat"],
            "release_sha256": C5_FROZEN_FILES_SHA[
                "experiments/position_axis_coordinate_c5_dev72_20261023/C5_DEV72_RELEASE_v3.json"],
            "run_contract_sha256": C5_FROZEN_FILES_SHA[
                "experiments/position_axis_coordinate_c5_dev72_20261023/C5_DEV72_RUN_CONTRACT_v3.json"],
        }
        if any(str(status.get(field, "")).lower() != expected_sha
               for field, expected_sha in frozen_sha.items()):
            raise ValueError(f"C5 frozen release binding mismatch: {scene_id}")


def _load_inputs(root: Path) -> dict[str, Any]:
    import h5py
    import numpy as np

    for rel, expected in {TASKBOOK: TASKBOOK_SHA, RELABEL_MANIFEST: RELABEL_MANIFEST_SHA,
                          NORMALIZER: NORMALIZER_SHA, INITIAL: INITIAL_SHA,
                          OLD_TRAIN_RELEASE: OLD_TRAIN_RELEASE_SHA,
                          **C5_FROZEN_FILES_SHA,
                          **SOURCE_SHA}.items():
        if _sha(_path(root, rel)) != expected:
            raise ValueError(f"pinned input changed: {rel}")
    if _sha(_path(root, RELABELER)) != _json(_path(root, RELABEL_MANIFEST))["relabeler_sha256"].lower():
        raise ValueError("C5_COVERAGE33 relabeler changed after caches were built")
    taskbook = _path(root, TASKBOOK).read_text(encoding="utf-8-sig")
    if "DL1018_DEV_T2_C02_W15" not in taskbook or "DL1018_DEV_T1_C02_W15" in taskbook:
        raise ValueError("corrected v2 C02 scene binding is missing")
    m = _json(_path(root, RELABEL_MANIFEST))
    if (m.get("schema") != "CM18_C5_COVERAGE33_RELABEL_MANIFEST_V1" or m.get("status") != "PASS"
            or m.get("taskbook_sha256", "").lower() != TASKBOOK_SHA
            or m.get("fit_rows_total") != 13_200 or m.get("fit_rows_extra") != 3_600
            or m.get("Plant_calls_during_relabel") != 0 or m.get("optimizer_steps") != 0
            or m.get("C5_VAL48_accessed") is not False or m.get("TEST_accessed") is not False):
        raise ValueError("relabel manifest is not the pinned offline PASS")
    extras = m.get("extra_dev_scenes", [])
    holdouts = m.get("holdout_dev_scenes", [])
    if ([r.get("scene_id") for r in extras] != EXPECTED_EXTRA
            or [r.get("scene_id") for r in holdouts] != EXPECTED_HOLDOUT):
        raise ValueError("frozen C5_COVERAGE33 scene order/set changed")
    _check_c5_provenance(root, extras, "TRAIN_EXTRA")
    _check_c5_provenance(root, holdouts, "HOLDOUT")

    reader = _module(root, READER, "c524_coverage33_reader")
    old_release_path = _path(root, OLD_TRAIN_RELEASE)
    old_release = _json(old_release_path)
    c5_task, verified_c5 = reader._verify_release_files(root, old_release)
    old_ids = reader._fixed_scene_ids(c5_task)
    old_scenes = [reader._read_c5_scene(root, sid, verified_c5[sid]) for sid in old_ids]
    if len(old_scenes) != 24 or [s["scene_id"] for s in old_scenes] != old_ids:
        raise ValueError("audited original C5 TRAIN24 scene order changed")
    train24_by_id = {r["scene_id"]: r for r in m.get("train24_scenes", [])}
    if set(train24_by_id) != set(old_ids) or len(train24_by_id) != 24:
        raise ValueError("original C5 TRAIN24 cache identities differ from the audited taskbook")
    for s in old_scenes:
        row = train24_by_id[s["scene_id"]]
        if (_sha(_path(root, row["cache_path"])) != row["cache_sha256"].lower()
                or Path(row["cache_path"]).resolve() != Path(verified_c5[s["scene_id"]]["pin"]["cache_path"]).resolve()):
            raise ValueError(f"original C5 TRAIN24 cache differs from the relabel manifest: {s['scene_id']}")

    extra_scenes = [_extra_scene(root, row, np, h5py) for row in extras]
    scenes = old_scenes + extra_scenes
    xrows, yrows, row_map = [], [], []
    for s in scenes:
        x = np.asarray(s["X18"], dtype=np.float64)
        y = np.asarray(s["target_raw_output_rad_s2"], dtype=np.float64)
        plant = np.asarray(s["plant_index"], dtype=np.int64).reshape(-1)
        if x.shape != (1999, 18) or y.shape != (1999, 3) or not np.isfinite(x).all() or not np.isfinite(y).all():
            raise ValueError(f"training arrays invalid: {s['scene_id']}")
        xrows.append(x[SAMPLE_ORDINALS]); yrows.append(y[SAMPLE_ORDINALS])
        row_map.extend((s["scene_id"], ordinal, int(plant[ordinal])) for ordinal in SAMPLE_ORDINALS)
    x = np.ascontiguousarray(np.concatenate(xrows), dtype=np.float64)
    y = np.ascontiguousarray(np.concatenate(yrows), dtype=np.float64)
    if x.shape != (13_200, 18) or y.shape != (13_200, 3):
        raise ValueError("C5_COVERAGE33 fit set must contain exactly 13,200 ordered rows")
    row_sha = reader.canonical_row_map_sha(row_map)
    sample_sha = reader.sample_stream_sha(seed=SEED, steps=STEPS, batch_size=BATCH, row_count=len(x))
    return {"np": np, "reader": reader, "taskbook": c5_task, "old_ids": old_ids,
            "extra_ids": EXPECTED_EXTRA, "holdouts": EXPECTED_HOLDOUT, "x": x, "y": y,
            "row_map_sha256": row_sha, "sample_stream_sha256": sample_sha,
            "scenes": scenes, "manifest": m}


def _models(root: Path) -> tuple[Any, Any, Any, Any]:
    np = __import__("numpy")
    numpy_model = _module(root, NUMPY_MODEL, "c524_coverage33_numpy_model")
    torch_model = _module(root, TORCH_MODEL, "c524_coverage33_torch_model")
    old_trainer = _module(root, OLD_TRAINER, "c524_coverage33_reference_trainer")
    params, norm, norm_record = old_trainer._load_shared_arrays(root, numpy_model, np)
    return numpy_model, torch_model, old_trainer, (params, norm, norm_record)


def _state_sha(model: Any) -> str:
    h = hashlib.sha256()
    for name, tensor in sorted(model.state_dict().items()):
        a = tensor.detach().cpu().contiguous().numpy()
        h.update(name.encode() + b"\0" + str(a.dtype).encode() + b"\0")
        h.update(str(tuple(a.shape)).encode() + b"\0" + a.tobytes(order="C"))
    return h.hexdigest()


def _self_check(root: Path, data: dict[str, Any]) -> dict[str, Any]:
    import numpy as np
    import torch

    numpy_model, torch_model, _, shared = _models(root)
    params, norm, _ = shared
    torch.manual_seed(SEED)
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    model = torch_model.TorchCM18A1(norm["mean"], norm["std"], norm["axis_rms"])
    model.load_numpy_parameters(params)
    if any(not np.array_equal(model.numpy_parameters()[k], params[k]) for k in params):
        raise AssertionError("CM18 float64 initialization differs from pinned W0")
    active = np.flatnonzero(np.any(data["x"][:, 7:15] != 0.0, axis=1))[:64]
    if len(active) != 64:
        raise AssertionError("coverage training set lacks 64 nonzero morphology rows")
    with torch.no_grad():
        t64 = model(torch.as_tensor(data["x"][active], dtype=torch.float64))["physical_output_rad_s2"].numpy()
    n64 = numpy_model.forward(data["x"][active], params)["physical_output_rad_s2"]
    parity = float(np.max(np.abs(t64 - n64)))
    if not math.isfinite(parity) or parity >= 1e-10:
        raise AssertionError(f"NumPy/Torch float64 parity failed: {parity}")
    if not torch.cuda.is_available() or torch.cuda.device_count() < 1:
        raise RuntimeError("C5_COVERAGE33 training requires cuda:0")
    torch.cuda.set_device(0)
    model = model.float().to("cuda:0")
    f32_params = model.numpy_parameters()
    if any(not np.array_equal(f32_params[k], np.asarray(params[k], dtype=np.float32)) for k in params):
        raise AssertionError("float32 parameters are not the exact pinned W0 cast")
    zx = data["x"][active[:4]].astype(np.float32)
    zx[:, 7:15] = 0.0
    with torch.no_grad():
        z = model(torch.as_tensor(zx, device="cuda:0"))["physical_output_rad_s2"]
    if not torch.equal(z, torch.zeros_like(z)):
        raise AssertionError("zero morphology basis must produce exactly zero action")
    xx = torch.as_tensor(data["x"][active].astype(np.float32), device="cuda:0")
    yy = torch.as_tensor((data["y"][active] / norm["axis_rms"]).astype(np.float32), device="cuda:0")
    axis = torch.as_tensor(norm["axis_rms"].astype(np.float32), device="cuda:0")
    loss = torch.nn.functional.smooth_l1_loss(model(xx)["physical_output_rad_s2"] / axis, yy,
                                               beta=1.0, reduction="mean")
    loss.backward()
    if (not torch.isfinite(loss).item()
            or any(p.grad is None or not torch.isfinite(p.grad).all().item() for p in model.parameters())):
        raise AssertionError("CUDA forward/backward non-finite")
    return {"status": "PASS", "scene_count": 33, "fit_rows": 13_200,
            "float64_numpy_torch_max_abs_delta_rad_s2": parity,
            "cuda_initial_loss": float(loss.detach().item()),
            "cuda_gradients_finite": True, "zero_basis_exact_zero": True,
            "initial_float32_state_sha256": _state_sha(model),
            "cuda_name": torch.cuda.get_device_name(0), "optimizer_steps": 0,
            "Plant_calls": 0, "TEST_accessed": False}


def _normalized_ranges(x: Any, y: Any, mean: Any, std: Any, axis: Any, np: Any) -> dict[str, Any]:
    return {"input_min": ((x - mean) / std).min(axis=0).tolist(),
            "input_max": ((x - mean) / std).max(axis=0).tolist(),
            "target_min_normalized": (y / axis).min(axis=0).tolist(),
            "target_max_normalized": (y / axis).max(axis=0).tolist()}


def _release(root: Path, data: dict[str, Any], selfcheck: dict[str, Any]) -> dict[str, Any]:
    return {"schema": "CM18_C5_COVERAGE33_TRAINING_RELEASE_V1",
            "decision": "APPROVE_ONE_MODEL_TRAINING", "created_at_utc": _now(),
            "taskbook": {"path": TASKBOOK, "sha256": TASKBOOK_SHA},
            "relabel_manifest": {"path": RELABEL_MANIFEST, "sha256": RELABEL_MANIFEST_SHA},
            "relabeler": {"path": RELABELER, "sha256": _sha(_path(root, RELABELER))},
            "original_c5_train24_release": {"path": OLD_TRAIN_RELEASE, "sha256": OLD_TRAIN_RELEASE_SHA},
            "source_files": {rel: _sha(_path(root, rel)) for rel in [str(Path(__file__).resolve().relative_to(root)).replace("\\", "/"), OLD_TRAINER, READER, NUMPY_MODEL, TORCH_MODEL]},
            "normalizer": {"path": NORMALIZER, "sha256": NORMALIZER_SHA,
                           "canonical_sha256": CANONICAL_NORMALIZER_SHA},
            "initial_parameters": {"path": INITIAL, "sha256": INITIAL_SHA},
            "train_scene_ids": [s["scene_id"] for s in data["scenes"]],
            "holdout_scene_ids": data["holdouts"], "train_scene_count": 33,
            "fit_rows": 13_200, "sample_ordinals_zero_based": "0,5,...,1995",
            "row_map_sha256": data["row_map_sha256"],
            "sample_index_stream_sha256": data["sample_stream_sha256"],
            "model": {"architecture": "CM18-A1 18-32-32-24 tanh/bilinear", "parameter_count": 2456,
                      "initial_float32_state_sha256": selfcheck["initial_float32_state_sha256"]},
            "training": {"seed": SEED, "steps": STEPS, "batch_size": BATCH,
                         "optimizer": "Adam", "lr": 0.001, "betas": [0.9, 0.999],
                         "eps": 1e-8, "weight_decay": 1e-5,
                         "loss": "SmoothL1 beta=1; mean over normalized three-axis output"},
            "checkpoint_selection": "none; fixed final step 60000",
            "holdout_or_validation_used_for_training_or_selection": False,
            "C5_VAL48_accessed": False, "TEST_accessed": False,
            "self_check": selfcheck, "output_directory": OUTPUT}


def _write_receipt(path: Path, value: dict[str, Any]) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n"); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)


def _checkpoint(torch: Any, model: Any, path: Path, step: int, kind: str) -> str:
    tmp = path.with_name(path.name + ".tmp")
    torch.save({"schema": "CM18_C5_COVERAGE33_CHECKPOINT_V1", "kind": kind,
                "optimizer_step": step,
                "state_dict": {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}}, tmp)
    os.replace(tmp, path)
    return _sha(path)


def _train(root: Path, data: dict[str, Any], release_path: Path, release_sha: str) -> None:
    import numpy as np
    import torch

    if _sha(release_path) != release_sha.lower():
        raise ValueError("training release SHA mismatch")
    release = _json(release_path)
    source_rel = str(Path(__file__).resolve().relative_to(root)).replace("\\", "/")
    expected_sources = {source_rel, OLD_TRAINER, READER, NUMPY_MODEL, TORCH_MODEL}
    expected_training = {"seed": SEED, "steps": STEPS, "batch_size": BATCH,
                         "optimizer": "Adam", "lr": 0.001, "betas": [0.9, 0.999],
                         "eps": 1e-8, "weight_decay": 1e-5,
                         "loss": "SmoothL1 beta=1; mean over normalized three-axis output"}
    if (release.get("schema") != "CM18_C5_COVERAGE33_TRAINING_RELEASE_V1"
            or release.get("decision") != "APPROVE_ONE_MODEL_TRAINING"
            or release.get("output_directory") != OUTPUT
            or release.get("fit_rows") != 13_200
            or release.get("train_scene_count") != 33
            or release.get("train_scene_ids") != [s["scene_id"] for s in data["scenes"]]
            or release.get("holdout_scene_ids") != data["holdouts"]
            or release.get("row_map_sha256") != data["row_map_sha256"]
            or release.get("sample_index_stream_sha256") != data["sample_stream_sha256"]):
        raise ValueError("training release does not bind the frozen C5_COVERAGE33 design")
    if set(release.get("source_files", {})) != expected_sources or release.get("training") != expected_training:
        raise ValueError("training release source set or optimizer configuration changed")
    self_check = release.get("self_check")
    if (not isinstance(self_check, dict) or self_check.get("status") != "PASS"
            or self_check.get("scene_count") != 33 or self_check.get("fit_rows") != 13_200
            or self_check.get("optimizer_steps") != 0 or self_check.get("Plant_calls") != 0
            or self_check.get("TEST_accessed") is not False
            or self_check.get("cuda_gradients_finite") is not True
            or self_check.get("zero_basis_exact_zero") is not True):
        raise ValueError("training release lacks a passing zero-step C5_COVERAGE33 self-check")
    model_spec = release.get("model")
    if (not isinstance(model_spec, dict)
            or model_spec.get("architecture") != "CM18-A1 18-32-32-24 tanh/bilinear"
            or model_spec.get("parameter_count") != 2456):
        raise ValueError("training release model architecture or parameter count changed")
    if (release.get("normalizer", {}).get("canonical_sha256") != CANONICAL_NORMALIZER_SHA
            or release.get("relabeler", {}).get("path") != RELABELER
            or release.get("relabeler", {}).get("sha256") != _sha(_path(root, RELABELER))):
        raise ValueError("training release normalizer or relabeler identity mismatch")
    for rel, expected in release.get("source_files", {}).items():
        if _sha(_path(root, rel)) != expected.lower():
            raise ValueError(f"training source changed since release: {rel}")
    for key, rel in (("taskbook", TASKBOOK), ("relabel_manifest", RELABEL_MANIFEST),
                     ("original_c5_train24_release", OLD_TRAIN_RELEASE),
                     ("normalizer", NORMALIZER), ("initial_parameters", INITIAL)):
        entry = release[key]
        if entry["path"] != rel or _sha(_path(root, rel)) != entry["sha256"].lower():
            raise ValueError(f"training release input mismatch: {key}")
    output = _path(root, OUTPUT) if (root / OUTPUT).exists() else root / OUTPUT
    if output.exists():
        raise FileExistsError(f"refusing to overwrite training output: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    free = __import__("shutil").disk_usage(output.parent).free
    if free < MIN_FREE_BYTES:
        raise RuntimeError("less than 30 GiB free before training")
    numpy_model, torch_model, old_trainer, shared = _models(root)
    params, norm, norm_record = shared
    if not torch.cuda.is_available() or torch.cuda.device_count() < 1:
        raise RuntimeError("formal training requires cuda:0")
    torch.cuda.set_device(0)
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    if hasattr(torch, "set_float32_matmul_precision"):
        torch.set_float32_matmul_precision("highest")
    random.seed(SEED); np.random.seed(SEED); torch.manual_seed(SEED); torch.cuda.manual_seed_all(SEED)
    model = torch_model.TorchCM18A1(norm["mean"], norm["std"], norm["axis_rms"])
    model.load_numpy_parameters(params)
    model = model.float().to("cuda:0")
    initial_state_sha = _state_sha(model)
    parameter_count = sum(p.numel() for p in model.parameters())
    if parameter_count != model_spec["parameter_count"]:
        raise ValueError("actual CM18 parameter count differs from the training release")
    expected_initial_sha = model_spec.get("initial_float32_state_sha256", "").lower()
    checked_initial_sha = self_check.get("initial_float32_state_sha256", "").lower()
    if (not expected_initial_sha or expected_initial_sha != checked_initial_sha
            or initial_state_sha != expected_initial_sha):
        raise ValueError("actual float32 W0 state SHA differs from self-check/training release")
    output.mkdir(exist_ok=False)
    receipt = {"schema": "CM18_C5_COVERAGE33_TRAINING_RECEIPT_V1", "status": "RUNNING",
               "started_at_utc": _now(), "command": sys.argv, "release_path": str(release_path),
               "release_sha256": release_sha.lower(), "training_source_sha256": release["source_files"],
               "taskbook_sha256": TASKBOOK_SHA, "relabel_manifest_sha256": RELABEL_MANIFEST_SHA,
               "train_scene_ids": release["train_scene_ids"], "fit_rows": 13_200,
               "row_map_sha256": data["row_map_sha256"],
               "sample_index_stream_sha256_expected": data["sample_stream_sha256"],
               "optimizer_steps_target": STEPS, "optimizer_steps_completed": 0,
               "optimizer_step_calls_attempted": 0, "checkpoint_selection": "fixed_final_60000_no_validation_selection",
               "holdout_used_for_training_or_selection": False, "C5_VAL48_accessed": False,
               "TEST_accessed": False, "Plant_calls": 0, "free_bytes_at_start": free,
               "initial_float32_state_sha256": initial_state_sha,
               "runtime": {"python": sys.version, "numpy": np.__version__, "torch": torch.__version__,
                           "cuda": torch.version.cuda, "gpu": torch.cuda.get_device_name(0),
                           "device": "cuda:0", "dtype": "float32", "amp": False, "tf32": False,
                           "deterministic_algorithms": True}}
    _write_receipt(output / "run_receipt.json", receipt)
    failure_step = None
    try:
        _checkpoint(torch, model, output / "initial.pt", 0, "initial")
        torch.cuda.synchronize()
        device = torch.device("cuda:0")
        train_x = torch.as_tensor(data["x"].astype(np.float32), device=device)
        train_y = torch.as_tensor((data["y"] / norm["axis_rms"]).astype(np.float32), device=device)
        axis = torch.as_tensor(norm["axis_rms"].astype(np.float32), device=device)
        optimizer = torch.optim.Adam(model.parameters(), lr=0.001, betas=(0.9, 0.999),
                                     eps=1e-8, weight_decay=1e-5)
        rng = np.random.default_rng(SEED)
        digest = hashlib.sha256()
        started = time.perf_counter(); model.train()
        for step in range(1, STEPS + 1):
            failure_step = step
            sample = rng.integers(0, len(train_x), size=BATCH, dtype=np.int64)
            digest.update(np.asarray(sample, dtype="<i8").tobytes(order="C"))
            ix = torch.as_tensor(sample, dtype=torch.long, device=device)
            optimizer.zero_grad(set_to_none=True)
            pred = model(train_x[ix])["physical_output_rad_s2"] / axis
            loss = torch.nn.functional.smooth_l1_loss(pred, train_y[ix], beta=1.0, reduction="mean")
            loss_value = float(loss.detach().item())
            if not math.isfinite(loss_value):
                raise FloatingPointError(f"non-finite loss at step {step}")
            loss.backward()
            for name, p in model.named_parameters():
                if p.grad is None or not torch.isfinite(p.grad).all().item():
                    raise FloatingPointError(f"missing/non-finite gradient: {name} at step {step}")
            receipt["optimizer_step_calls_attempted"] = step
            optimizer.step()
            receipt["optimizer_steps_completed"] = step
            if any(not torch.isfinite(p).all().item() for p in model.parameters()):
                raise FloatingPointError(f"non-finite model parameter at step {step}")
            if step % PROGRESS_EVERY == 0:
                _write_receipt(output / "progress.json", {"optimizer_steps_completed": step,
                    "optimizer_steps_target": STEPS, "latest_loss": loss_value,
                    "sample_stream_sha256_so_far": digest.hexdigest(),
                    "elapsed_s": time.perf_counter() - started, "updated_at_utc": _now()})
                with (output / "train_loss.jsonl").open("a", encoding="utf-8", newline="\n") as f:
                    f.write(json.dumps({"optimizer_step": step, "loss": loss_value}) + "\n")
                    f.flush(); os.fsync(f.fileno())
                receipt["latest_loss"] = loss_value
                _write_receipt(output / "run_receipt.json", receipt)
                if sum(p.stat().st_size for p in output.rglob("*") if p.is_file()) > MAX_OUTPUT_BYTES:
                    raise RuntimeError("training output exceeded 1 GiB")
        if digest.hexdigest() != release["sample_index_stream_sha256"]:
            raise AssertionError("actual RNG stream differs from the frozen release")
        final_sha = _checkpoint(torch, model, output / "final.pt", STEPS, "final")
        receipt.update({"status": "COMPLETED", "ended_at_utc": _now(),
                        "optimizer_steps_completed": STEPS, "optimizer_step_calls_attempted": STEPS,
                        "sample_index_stream_sha256_actual": digest.hexdigest(),
                        "final_checkpoint_sha256": final_sha,
                        "final_float32_state_sha256": _state_sha(model),
                        "elapsed_s": time.perf_counter() - started, "candidate_frozen": True})
        _write_receipt(output / "run_receipt.json", receipt)
    except BaseException as exc:
        receipt.update({"status": "FAILED", "ended_at_utc": _now(), "failure_step": failure_step,
                        "failure_reason": f"{type(exc).__name__}: {exc}",
                        "traceback": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))})
        _write_receipt(output / "run_receipt.json", receipt)
        raise
    if sum(p.stat().st_size for p in output.rglob("*") if p.is_file()) > MAX_OUTPUT_BYTES:
        raise RuntimeError("training output exceeded 1 GiB")
    print(json.dumps({"status": "COMPLETED", "output": str(output),
                      "optimizer_steps": STEPS, "checkpoint_sha256": final_sha}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--prepare-release", action="store_true")
    parser.add_argument("--train", action="store_true")
    parser.add_argument("--release", type=Path)
    parser.add_argument("--release-sha256")
    args = parser.parse_args()
    if sum((args.self_check, args.prepare_release, args.train)) != 1:
        parser.error("choose exactly one of --self-check, --prepare-release, or --train")
    root = args.repo_root.resolve(strict=True)
    data = _load_inputs(root)
    if args.self_check:
        if args.release or args.release_sha256:
            parser.error("--self-check does not take a release")
        result = _self_check(root, data)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if args.prepare_release:
        if args.release or args.release_sha256:
            parser.error("--prepare-release does not take a release")
        result = _self_check(root, data)
        release = _release(root, data, result)
        path = root / CONFIG_PATH
        _new_json(path, release)
        print(json.dumps({"status": "PREPARED", "release": str(path),
                          "sha256": _sha(path), "self_check": result}, ensure_ascii=False, indent=2))
        return
    if args.release is None or args.release_sha256 is None:
        parser.error("--train requires --release and --release-sha256")
    _train(root, data, args.release.resolve(strict=True), args.release_sha256)


if __name__ == "__main__":
    main()
