from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any

import h5py
import numpy as np
from scipy.io import loadmat


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
RUN_DIR = ROOT / "experiments/position_prior_calibration_c1_20261022_v9"
LOCK = RUN_DIR / "C1_SOURCE_LOCK_v2.json"
RELEASE = RUN_DIR / "C1_RELEASE_v9.json"
RUNS_CSV = RUN_DIR / "reports/C1_SCREEN_PER_RUN.csv"
SCENES_CSV = ROOT / "reports/paper14_v2/phase1/ROUND_SCREEN_12_SCENES.csv"
PRE_REG = OUT / "PRE_REGISTRATION_ZH.md"
PRE_REG_SHA256 = "34eea0da6684b55917d94f4cf6973682e380c82a36476db89dd76c25cb45ecfc"

EXPECTED_STATIC = {
    LOCK: "02668f6268944715e65e6d2cffa52b395417506132212b00e7d273d88df164e5",
    RELEASE: "7aa072835b0e633f9e40d0e471a17870735d32ddf079eafc61ac6790ea7974d0",
    RUNS_CSV: "43aab1c0fa906dfa5e3d7f175339a5607bd4ec2e2cc55687741524d34fa08bac",
    SCENES_CSV: "176ed5770824a241b5c41b9c786f2110b730a7783414152875181985d497a32e",
}

INPUT_DATASET_PATHS = {
    "log/initial_state",
    "log/time",
    "log/transition_time",
    "log/environment_wind_I",
    "log/physical_impulse_force_I_N",
    "log/state_perturbation_enabled",
    "log/state_perturbation_requested_time_s",
    "log/state_perturbation_delta",
    "log/state_perturbation_applied_flag",
    "log/reference/position",
    "log/reference/velocity",
    "log/reference/acceleration",
    "log/reference/yaw",
    "log/reference/yaw_rate",
    "log/reference/yaw_acceleration",
}

OUTPUT_TOKENS = (
    "state/", "stage1_position_event_", "stage1_position_held_",
    "weight_final", "weight_after", "raw_acceleration", "applied_acceleration",
    "requested_generalized", "realized_generalized", "position_commanded_force",
    "wind_force_i", "wind_torque", "controller_call_time", "network_call_time",
    "q_0_", "rmse_", "peak", "p95", "divergence", "safety", "status",
)

METHOD_TOKENS = (
    "options_audit", "stage1_position_search", "stage1_position_weight_initial",
    "stage1_position_update_enabled", "stage1_position_replacement_enabled",
    "stage1_position_pcf_coordination_enabled", "stage1_position_beta_scale",
    "stage1_position_model_context_length", "stage1_position_readiness_events",
    "pcf_enabled", "update_enabled", "head_type", "gamma", "beta_scale",
    "model_id", "seed", "selected_step", "c_star", "weight_sha256",
)

METADATA_TOKENS = (
    "condition", "method", "release_sha", "preflight_sha", "started_utc",
    "timing_", "gpu_jobs", "optimizer_steps", "non_research_desktop_loads",
    "scene_source_raw_sha", "source_lock_sha", "model_mat_sha", "normalizer_npz_sha",
    "scene_payload_identity_csv_sha", "physical_payload_pair_sha", "run_identity",
)

CONFIG_TOKENS = (
    "enabled", "mode", "type", "gamma", "kappa", "beta", "rate", "hz",
    "dt", "mass", "gravity", "inertia", "gain", "limit", "dmax", "motor",
    "scheduler", "fallback", "safe", "readiness", "context", "seed",
)

MAX_INLINE_ELEMENTS = 2048
HASH_BLOCK = 4 * 1024 * 1024


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(HASH_BLOCK), b""):
            digest.update(block)
    return digest.hexdigest()


def stat_record(path: Path) -> dict[str, Any]:
    st = path.stat()
    return {
        "size": st.st_size,
        "mtime_ns": st.st_mtime_ns,
        "mtime_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(st.st_mtime)),
    }


def json_safe(value: Any) -> Any:
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        if math.isinf(value):
            return "+Inf" if value > 0 else "-Inf"
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, np.ndarray):
        if value.dtype.kind in "fc":
            return [json_safe(x) for x in value.tolist()]
        return [json_safe(x) for x in value.tolist()]
    if isinstance(value, (list, tuple)):
        return [json_safe(x) for x in value]
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    return str(value)


def attr_text(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, np.ndarray):
        return json_safe(value)
    if isinstance(value, np.generic):
        return json_safe(value)
    return value


def matlab_class(obj: h5py.Group | h5py.Dataset) -> str | None:
    value = obj.attrs.get("MATLAB_class")
    if isinstance(value, bytes):
        return value.decode("ascii", errors="replace")
    if isinstance(value, np.ndarray) and value.size == 1:
        item = value.reshape(-1)[0]
        return item.decode("ascii", errors="replace") if isinstance(item, bytes) else str(item)
    return None


def mat_shape(hdf5_shape: tuple[int, ...] | None) -> list[int] | None:
    if hdf5_shape is None:
        return None
    if len(hdf5_shape) <= 1:
        return list(hdf5_shape)
    return list(reversed(hdf5_shape))


def decode_char(arr: np.ndarray) -> str:
    flat = np.asarray(arr).reshape(-1, order="F")
    chars: list[str] = []
    for item in flat:
        n = int(item)
        if n:
            chars.append(chr(n))
    return "".join(chars)


def decode_h5_value(h5: h5py.File, obj: h5py.Group | h5py.Dataset, depth: int = 0) -> Any:
    if depth > 12:
        return "<MAX_DEPTH>"
    if isinstance(obj, h5py.Group):
        return {name: decode_h5_value(h5, obj[name], depth + 1) for name in sorted(obj.keys())}
    data = obj[()]
    cls = matlab_class(obj)
    ref_type = h5py.check_dtype(ref=obj.dtype)
    if ref_type is not None:
        a = np.asarray(data)
        if a.size > MAX_INLINE_ELEMENTS:
            return {"shape": list(a.shape), "dtype": str(a.dtype), "decoded": False}
        decoded = []
        for ref in a.reshape(-1, order="F"):
            if not ref:
                decoded.append(None)
            else:
                decoded.append(decode_h5_value(h5, h5[ref], depth + 1))
        return {"reference_array_shape": list(a.shape), "items": decoded}
    a = np.asarray(data)
    if cls == "char" and a.size <= MAX_INLINE_ELEMENTS:
        return decode_char(a)
    if a.size <= MAX_INLINE_ELEMENTS:
        return json_safe(a)
    return {"shape": list(a.shape), "dtype": str(a.dtype), "value_omitted": True}


def finite_counts(data: np.ndarray) -> tuple[int | None, int | None]:
    a = np.asarray(data)
    if a.dtype.kind not in "fc":
        return None, None
    finite = np.isfinite(a)
    return int(finite.sum()), int((~finite).sum())


def array_identity(data: np.ndarray) -> tuple[str, int | None, int | None]:
    a = np.asarray(data)
    finite, nonfinite = finite_counts(a)
    h = hashlib.sha256()
    h.update(str(a.dtype).encode("ascii"))
    h.update(b"\0")
    h.update(json.dumps(list(a.shape), separators=(",", ":")).encode("ascii"))
    h.update(b"\0")
    h.update(np.ascontiguousarray(a).tobytes())
    return h.hexdigest(), finite, nonfinite


def schema_rows(h5: h5py.File, root_name: str, obj: h5py.Group | h5py.Dataset, prefix: str = "") -> list[dict[str, Any]]:
    path = f"{prefix}/{root_name}" if prefix else root_name
    rows: list[dict[str, Any]] = []
    if isinstance(obj, h5py.Group):
        fields = obj.attrs.get("MATLAB_fields")
        field_names = []
        if isinstance(fields, np.ndarray):
            for f in fields.reshape(-1):
                try:
                    field_names.append(b"".join(np.asarray(f).reshape(-1).tolist()).decode("ascii", errors="replace"))
                except Exception:
                    field_names.append(str(f))
        rows.append({
            "path": path,
            "kind": "group",
            "matlab_class": matlab_class(obj),
            "matlab_fields_json": json.dumps(field_names, ensure_ascii=False),
            "h5_dtype": "",
            "hdf5_shape": "",
            "matlab_shape": "",
            "value_status": "GROUP",
            "value_json": "",
            "content_sha256": "",
            "finite_count": "",
            "nonfinite_count": "",
        })
        for name in sorted(obj.keys()):
            rows.extend(schema_rows(h5, name, obj[name], path))
        return rows

    cls = matlab_class(obj)
    size = int(np.prod(obj.shape, dtype=np.int64)) if obj.shape else 1
    ref_type = h5py.check_dtype(ref=obj.dtype)
    use_decode = size <= MAX_INLINE_ELEMENTS or cls == "char" or ref_type is not None
    value = decode_h5_value(h5, obj) if use_decode else None
    content_sha = ""
    finite = nonfinite = None
    if size <= MAX_INLINE_ELEMENTS:
        arr = np.asarray(obj[()])
        finite, nonfinite = finite_counts(arr)
    else:
        arr = None
    if ref_type is None and size <= MAX_INLINE_ELEMENTS:
        content_sha = array_identity(arr)[0]
    rows.append({
        "path": path,
        "kind": "dataset",
        "matlab_class": cls or "",
        "matlab_fields_json": "",
        "h5_dtype": str(obj.dtype),
        "hdf5_shape": json.dumps(list(obj.shape)),
        "matlab_shape": json.dumps(mat_shape(obj.shape)),
        "value_status": "INLINE" if use_decode else "SHAPE_ONLY",
        "value_json": json.dumps(json_safe(value), ensure_ascii=False, separators=(",", ":")) if use_decode else "",
        "content_sha256": content_sha,
        "finite_count": "" if finite is None else finite,
        "nonfinite_count": "" if nonfinite is None else nonfinite,
    })
    return rows


def walk_datasets(group: h5py.Group, prefix: str) -> dict[str, h5py.Dataset]:
    out: dict[str, h5py.Dataset] = {}
    for name in group.keys():
        child = group[name]
        path = f"{prefix}/{name}"
        if isinstance(child, h5py.Dataset):
            out[path] = child
        else:
            out.update(walk_datasets(child, path))
    return out


def canonical_value(value: Any) -> str:
    return json.dumps(json_safe(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def flatten_dict(value: Any, prefix: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {}
    if isinstance(value, dict) and "reference_array_shape" not in value:
        for key, child in value.items():
            child_path = f"{prefix}/{key}" if prefix else key
            result.update(flatten_dict(child, child_path))
        return result
    if isinstance(value, dict) and "items" in value and "reference_array_shape" in value:
        result[prefix] = value
        return result
    result[prefix] = value
    return result


def classify(path: str) -> str:
    p = path.lower()
    if any(token in p for token in METADATA_TOKENS):
        return "运行记录元数据"
    if any(token in p for token in INPUT_DATASET_PATHS) or p.startswith("log/reference/") or "/arms/" in p:
        return "配对物理输入"
    if any(token in p for token in METHOD_TOKENS):
        return "预定方法差异或方法配置候选"
    if any(token in p for token in OUTPUT_TOKENS):
        return "闭环输出差异"
    if any(token in p for token in CONFIG_TOKENS):
        return "静态配置候选"
    return "已记录字段差异待源码定性"


def csv_write(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("x", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json_safe(v) if isinstance(v, (dict, list, np.ndarray)) else v for k, v in row.items()})


def check_static_inputs() -> dict[str, Any]:
    output = {}
    for path, expected in EXPECTED_STATIC.items():
        actual = sha256_file(path)
        if actual != expected:
            raise RuntimeError(f"static input SHA mismatch {path}: {actual} != {expected}")
        output[str(path)] = {"sha256": actual, **stat_record(path)}
    if not PRE_REG.exists() or sha256_file(PRE_REG) != PRE_REG_SHA256:
        raise RuntimeError("pre-registration SHA mismatch; do not start full pass")
    output[str(PRE_REG)] = {"sha256": PRE_REG_SHA256, **stat_record(PRE_REG)}
    return output


def load_manifest() -> tuple[list[dict[str, str]], dict[str, Any], dict[str, Any]]:
    with RUNS_CSV.open(newline="", encoding="utf-8-sig") as stream:
        all_runs = list(csv.DictReader(stream))
    with SCENES_CSV.open(newline="", encoding="utf-8-sig") as stream:
        scene_rows = list(csv.DictReader(stream))
    scene_ids = [r.get("scene_id", r.get("sceneId", "")) for r in scene_rows]
    if len(scene_ids) != 12 or len(set(scene_ids)) != 12:
        raise RuntimeError(f"scene list is not 12 unique ids: {scene_ids}")
    selected = []
    for scene_id in scene_ids:
        group = [r for r in all_runs if r["scene_id"] == scene_id and r["condition"] in ("B", "ON1")]
        by_condition = {r["condition"]: r for r in group}
        if len(group) != 2 or set(by_condition) != {"B", "ON1"}:
            raise RuntimeError(f"expected exactly B/ON1 for {scene_id}, got {[r['condition'] for r in group]}")
        selected.extend([by_condition["B"], by_condition["ON1"]])
    if len(selected) != 24:
        raise RuntimeError(f"wrong selected rows: {len(selected)}")
    return selected, {"all_rows": len(all_runs), "scene_ids": scene_ids}, {r["scene_id"]: r for r in scene_rows}


def decode_tree(h5: h5py.File, root_name: str) -> dict[str, Any]:
    if root_name not in h5:
        return {"_missing": True}
    return decode_h5_value(h5, h5[root_name])


def get_small_fields(tree: dict[str, Any], root: str) -> dict[str, Any]:
    flat = flatten_dict(tree, root)
    return flat


def load_h5_record(row: dict[str, str], static_identities: dict[str, Any], sample_only: bool) -> dict[str, Any]:
    raw_path = Path(row["raw_path"])
    start_path = raw_path.parent / "run_start.mat"
    status_path = raw_path.parent / "run_status.json"
    paths = [(raw_path, row["raw_sha256"]), (start_path, row["run_start_sha256"]), (status_path, row["run_status_sha256"])]
    before = {}
    for path, expected in paths:
        if not path.is_file():
            raise RuntimeError(f"missing input file: {path}")
        before[str(path)] = {"sha256": sha256_file(path), **stat_record(path)}
        if before[str(path)]["sha256"] != expected.lower():
            raise RuntimeError(f"input SHA mismatch against C1 index: {path}")

    schema: list[dict[str, Any]] = []
    with h5py.File(raw_path, "r") as raw:
        raw_root_keys = sorted(raw.keys())
        for root_name in raw_root_keys:
            if root_name == "#refs#":
                continue
            schema.extend(schema_rows(raw, root_name, raw[root_name]))
        raw_identity = decode_tree(raw, "runIdentity") if "runIdentity" in raw else {"_missing": True}
        input_data = {}
        raw_datasets = walk_datasets(raw["log"], "log") if "log" in raw and isinstance(raw["log"], h5py.Group) else {}
        selected_paths = set(INPUT_DATASET_PATHS)
        selected_paths.update(p for p in raw_datasets if p.startswith("log/arms/"))
        for path in sorted(selected_paths):
            if path in raw_datasets:
                array = np.asarray(raw_datasets[path][()])
                h, fin, nfin = array_identity(array)
                input_data[path] = {"present": True, "shape_hdf5": list(array.shape), "shape_matlab": mat_shape(array.shape), "dtype": str(array.dtype), "array_sha256": h, "finite_count": fin, "nonfinite_count": nfin}
            else:
                input_data[path] = {"present": False}
        # State start sample and logged initial_state are separate stored values.
        if "log/state" in raw_datasets and "log/initial_state" in raw_datasets:
            state = np.asarray(raw_datasets["log/state"][()])
            init = np.asarray(raw_datasets["log/initial_state"][()]).reshape(-1)
            if state.ndim == 2 and state.shape[0] == 12:
                state0 = state[:, 0]
            elif state.ndim == 2 and state.shape[1] == 12:
                state0 = state[0, :]
            else:
                raise RuntimeError(f"unknown state layout {state.shape} in {raw_path}")
            input_data["log/state@initial_sample"] = {"shape_hdf5": list(state0.shape), "dtype": str(state.dtype), "matches_initial_state": bool(np.array_equal(state0, init)), "max_abs_diff": float(np.max(np.abs(state0 - init))) if state0.size else 0.0}
        run_identity = raw_identity
        log_small = {}
        log_ds = raw_datasets
        for path, ds in log_ds.items():
            arr_size = int(np.prod(ds.shape, dtype=np.int64)) if ds.shape else 1
            cls = matlab_class(ds)
            if arr_size <= MAX_INLINE_ELEMENTS or cls == "char" or h5py.check_dtype(ref=ds.dtype) is not None:
                log_small[path] = decode_h5_value(raw, ds)
        has_cfg_opts = {"cfg": "cfg" in raw, "opts": "opts" in raw}
        raw_summary = {"root_keys": raw_root_keys, "has_root_cfg_opts": has_cfg_opts, "runIdentity": run_identity, "log_small_values": log_small}

    with h5py.File(start_path, "r") as start:
        start_root_keys = sorted(start.keys())
        start_schema = []
        for root_name in start_root_keys:
            if root_name == "#refs#":
                continue
            start_schema.extend(schema_rows(start, root_name, start[root_name]))
        start_tree = {name: decode_tree(start, name) for name in start_root_keys if name != "#refs#"}
        has_cfg_opts = {"cfg": "cfg" in start, "opts": "opts" in start}
    schema.extend(start_schema)

    status = json.loads(status_path.read_text(encoding="utf-8"))
    after = {}
    for path, expected in paths:
        after[str(path)] = {"sha256": sha256_file(path), **stat_record(path)}
        if before[str(path)] != after[str(path)]:
            raise RuntimeError(f"input changed during read: {path}")
        if after[str(path)]["sha256"] != expected.lower():
            raise RuntimeError(f"post-read SHA mismatch against C1 index: {path}")
    if str(start_tree.get("runStart", {}).get("scene_id", "")) != row["scene_id"]:
        raise RuntimeError(f"runStart scene_id does not match index for {row['scene_id']} {row['condition']}")
    if str(raw_summary.get("runIdentity", {}).get("scene_id", "")) != row["scene_id"]:
        raise RuntimeError(f"raw runIdentity scene_id does not match index for {row['scene_id']} {row['condition']}")

    return {
        "manifest": row,
        "raw_path": str(raw_path),
        "run_start_path": str(start_path),
        "run_status_path": str(status_path),
        "before": before,
        "after": after,
        "raw_root_keys": raw_root_keys,
        "run_start_root_keys": start_root_keys,
        "raw": raw_summary,
        "run_start": start_tree,
        "run_status": status,
        "input_data": input_data,
        "schema": schema,
        "has_cfg_opts": {"raw": raw_summary["has_root_cfg_opts"], "run_start": has_cfg_opts},
    }


def scene_input_datasets(records: dict[tuple[str, str], dict[str, Any]], scene_id: str) -> list[dict[str, Any]]:
    b = records[(scene_id, "B")]
    on = records[(scene_id, "ON1")]
    b_inputs, on_inputs = b["input_data"], on["input_data"]
    paths = sorted(set(b_inputs) | set(on_inputs))
    rows = []
    for path in paths:
        left, right = b_inputs.get(path, {"present": False}), on_inputs.get(path, {"present": False})
        if path == "log/state@initial_sample":
            equal = left.get("matches_initial_state") and right.get("matches_initial_state")
            status = "INITIAL_STATE_CONSISTENT_WITH_RAW_STATE" if equal else "INITIAL_STATE_MISMATCH"
        else:
            equal = left.get("present") == right.get("present")
            if equal and left.get("present"):
                equal = left.get("array_sha256") == right.get("array_sha256") and left.get("shape_hdf5") == right.get("shape_hdf5") and left.get("dtype") == right.get("dtype")
            status = "EXACT_MATCH" if equal else "DIFF_OR_MISSING"
        rows.append({
            "scene_id": scene_id,
            "field_path": path,
            "classification": "paired physical input",
            "B_present": left.get("present", True),
            "ON1_present": right.get("present", True),
            "B_shape_hdf5": left.get("shape_hdf5", ""),
            "ON1_shape_hdf5": right.get("shape_hdf5", ""),
            "B_dtype": left.get("dtype", ""),
            "ON1_dtype": right.get("dtype", ""),
            "B_content_sha256": left.get("array_sha256", ""),
            "ON1_content_sha256": right.get("array_sha256", ""),
            "comparison": status,
        })
    # Compare the full recursively logged arm/morphology subtree, not only its root.
    with h5py.File(b["raw_path"], "r") as bh5, h5py.File(on["raw_path"], "r") as oh5:
        bds = walk_datasets(bh5["log/arms"], "log/arms") if "log/arms" in bh5 else {}
        ods = walk_datasets(oh5["log/arms"], "log/arms") if "log/arms" in oh5 else {}
        for path in sorted(set(bds) | set(ods)):
            left, right = bds.get(path), ods.get(path)
            if left is None or right is None:
                equal = False
                bdesc = {"present": left is not None}
                odesc = {"present": right is not None}
            else:
                a, c = np.asarray(left[()]), np.asarray(right[()])
                bdesc = {"present": True, "shape_hdf5": list(a.shape), "dtype": str(a.dtype), "array_sha256": array_identity(a)[0]}
                odesc = {"present": True, "shape_hdf5": list(c.shape), "dtype": str(c.dtype), "array_sha256": array_identity(c)[0]}
                equal = bdesc == odesc
            rows.append({"scene_id": scene_id, "field_path": path, "classification": "paired morphology input", "B_present": bdesc.get("present"), "ON1_present": odesc.get("present"), "B_shape_hdf5": bdesc.get("shape_hdf5", ""), "ON1_shape_hdf5": odesc.get("shape_hdf5", ""), "B_dtype": bdesc.get("dtype", ""), "ON1_dtype": odesc.get("dtype", ""), "B_content_sha256": bdesc.get("array_sha256", ""), "ON1_content_sha256": odesc.get("array_sha256", ""), "comparison": "EXACT_MATCH" if equal else "DIFF_OR_MISSING"})
    return rows


def field_map(tree: dict[str, Any], prefix: str) -> dict[str, Any]:
    return flatten_dict(tree, prefix)


def compare_pair_fields(records: dict[tuple[str, str], dict[str, Any]], scene_id: str) -> list[dict[str, Any]]:
    b, on = records[(scene_id, "B")], records[(scene_id, "ON1")]
    b_fields: dict[str, Any] = {}
    on_fields: dict[str, Any] = {}
    for name in ("runStart",):
        b_fields.update(field_map(b["run_start"].get(name, {}), f"run_start/{name}"))
        on_fields.update(field_map(on["run_start"].get(name, {}), f"run_start/{name}"))
    b_fields.update(field_map(b["raw"].get("runIdentity", {}), "raw/runIdentity"))
    on_fields.update(field_map(on["raw"].get("runIdentity", {}), "raw/runIdentity"))
    b_fields.update(b["raw"].get("log_small_values", {}))
    on_fields.update(on["raw"].get("log_small_values", {}))
    rows = []
    for path in sorted(set(b_fields) | set(on_fields)):
        have_b, have_on = path in b_fields, path in on_fields
        vb, vo = b_fields.get(path), on_fields.get(path)
        if have_b and have_on:
            same = canonical_value(vb) == canonical_value(vo)
            if same:
                continue
            status = "VALUE_DIFF"
        else:
            status = "MISSING_ON_ONE_SIDE"
        rows.append({
            "scene_id": scene_id,
            "field_path": path,
            "classification": classify(path),
            "B_present": have_b,
            "ON1_present": have_on,
            "B_value_json": canonical_value(vb) if have_b else "",
            "ON1_value_json": canonical_value(vo) if have_on else "",
            "comparison": status,
        })
    return rows


def config_tree_value(value: Any) -> Any:
    if hasattr(value, "_fieldnames"):
        return {name: config_tree_value(getattr(value, name)) for name in value._fieldnames}
    if isinstance(value, np.ndarray):
        if value.dtype == object:
            vals = [config_tree_value(x) for x in value.reshape(-1, order="F")]
            return {"kind": "matlab_object_array", "shape": list(value.shape), "values": vals}
        arr = np.asarray(value)
        finite, nonfinite = finite_counts(arr)
        return {"kind": "matlab_array", "shape": list(arr.shape), "dtype": str(arr.dtype), "finite_count": finite, "nonfinite_count": nonfinite, "values": json_safe(arr) if arr.size <= 10000 else None}
    if isinstance(value, dict):
        return {str(k): config_tree_value(v) for k, v in sorted(value.items())}
    if isinstance(value, (np.generic, bytes, float, int, bool, str)) or value is None:
        return json_safe(value)
    return str(value)


def extract_locked_cfg(lock_obj: dict[str, Any]) -> dict[str, Any]:
    cfg_entry = next(x for x in lock_obj["frozen_runtime_files"] if x["path"].lower().endswith("effective_config.mat"))
    path = Path(cfg_entry["path"])
    before = {"sha256": sha256_file(path), **stat_record(path)}
    if before["sha256"] != cfg_entry["sha256"]:
        raise RuntimeError("effective_config.mat SHA differs from frozen source lock")
    loaded = loadmat(path, variable_names=["cfg"], squeeze_me=False, struct_as_record=False, chars_as_strings=False)
    if "cfg" not in loaded:
        raise RuntimeError("locked effective_config.mat does not have cfg variable")
    tree = config_tree_value(loaded["cfg"])
    after = {"sha256": sha256_file(path), **stat_record(path)}
    if before != after:
        raise RuntimeError("locked effective_config.mat changed while reading")
    return {"path": str(path), "expected_sha256": cfg_entry["sha256"], "before": before, "after": after, "per_run_snapshot_present": False, "provenance": "shared frozen config input verified by C1 runner/source lock; this is not a per-run cfg snapshot", "tree": tree}


def verify_source_files(lock_obj: dict[str, Any], release_obj: dict[str, Any]) -> list[dict[str, Any]]:
    sources = []
    for entry in lock_obj["frozen_runtime_files"]:
        path = Path(entry["path"])
        actual = sha256_file(path)
        sources.append({"name": path.name, "path": str(path), "expected_sha256": entry["sha256"], "actual_sha256": actual, "match": actual == entry["sha256"]})
        if actual != entry["sha256"]:
            raise RuntimeError(f"frozen runtime source mismatch: {path}")
    for key in ("builder_path", "runner_path"):
        path = Path(release_obj[key])
        actual = sha256_file(path)
        sources.append({"name": path.name, "path": str(path), "expected_sha256": release_obj[key.replace("_path", "_sha256")], "actual_sha256": actual, "match": actual == release_obj[key.replace("_path", "_sha256")]})
        if actual != release_obj[key.replace("_path", "_sha256")]:
            raise RuntimeError(f"C1 builder/runner source mismatch: {path}")
    return sources


def run(mode: str) -> None:
    start_wall = time.perf_counter()
    static_identities = check_static_inputs()
    lock_obj = json.loads(LOCK.read_text(encoding="utf-8"))
    release_obj = json.loads(RELEASE.read_text(encoding="utf-8"))
    sources = verify_source_files(lock_obj, release_obj)
    locked_cfg = extract_locked_cfg(lock_obj)
    selected_rows, manifest_info, scene_info = load_manifest()
    if mode == "sample":
        sample_scene = manifest_info["scene_ids"][0]
        selected_rows = [r for r in selected_rows if r["scene_id"] == sample_scene]
    name_prefix = "FIRST_PAIR" if mode == "sample" else "FULL12"
    outputs = [OUT / f"{name_prefix}_FILE_IDENTITY.csv", OUT / f"{name_prefix}_H5_SCHEMA.csv", OUT / f"{name_prefix}_PAIR_INPUT_MATCH.csv", OUT / f"{name_prefix}_PAIR_FIELD_DIFF.csv", OUT / f"{name_prefix}_AUDIT.json", OUT / f"{name_prefix}_LOCKED_CFG_TREE.json"]
    if any(p.exists() for p in outputs):
        raise RuntimeError(f"refusing to overwrite existing outputs: {[str(p) for p in outputs if p.exists()]}")

    state_path = OUT / f"{name_prefix}_STATE.json"
    state = {"status": "RUNNING", "mode": mode, "started_local": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "completed_files": 0, "expected_files": len(selected_rows) * 3, "current_scene": None, "current_condition": None, "command": f"python -B {Path(__file__).relative_to(ROOT).as_posix()} --{mode}"}
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    records: dict[tuple[str, str], dict[str, Any]] = {}
    all_schema: list[dict[str, Any]] = []
    file_rows: list[dict[str, Any]] = []
    input_rows: list[dict[str, Any]] = []
    diff_rows: list[dict[str, Any]] = []
    try:
        for row in selected_rows:
            state.update({"current_scene": row["scene_id"], "current_condition": row["condition"]})
            state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
            rec = load_h5_record(row, static_identities, mode == "sample")
            records[(row["scene_id"], row["condition"])] = rec
            all_schema.extend({"scene_id": row["scene_id"], "condition": row["condition"], "file_kind": kind, **item} for kind, schemas in (("raw", [x for x in rec["schema"] if not x["path"].startswith("runStart")]), ("run_start", [x for x in rec["schema"] if x["path"].startswith("runStart")])) for item in schemas)
            expected_by_path = {
                rec["raw_path"]: row["raw_sha256"],
                rec["run_start_path"]: row["run_start_sha256"],
                rec["run_status_path"]: row["run_status_sha256"],
            }
            for key, identity in rec["before"].items():
                file_rows.append({"scene_id": row["scene_id"], "condition": row["condition"], "file_kind": "raw" if key == rec["raw_path"] else "run_start" if key == rec["run_start_path"] else "run_status", "path": key, "expected_sha256_from_index": expected_by_path[key], "before": identity, "after": rec["after"][key], "sha_and_stat_unchanged": rec["before"][key] == rec["after"][key]})
            state["completed_files"] += 3
            state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
            print(f"AUDIT {row['scene_id']} {row['condition']} done; {state['completed_files']}/{state['expected_files']} files", flush=True)

        for scene_id in (manifest_info["scene_ids"] if mode == "full" else [manifest_info["scene_ids"][0]]):
            input_rows.extend(scene_input_datasets(records, scene_id))
            diff_rows.extend(compare_pair_fields(records, scene_id))

        cfg_out = OUT / f"{name_prefix}_LOCKED_CFG_TREE.json"
        cfg_out.write_text(json.dumps(locked_cfg, indent=2, ensure_ascii=False), encoding="utf-8")
        csv_write(OUT / f"{name_prefix}_FILE_IDENTITY.csv", ["scene_id", "condition", "file_kind", "path", "expected_sha256_from_index", "before", "after", "sha_and_stat_unchanged"], file_rows)
        csv_write(OUT / f"{name_prefix}_H5_SCHEMA.csv", ["scene_id", "condition", "file_kind", "path", "kind", "matlab_class", "matlab_fields_json", "h5_dtype", "hdf5_shape", "matlab_shape", "value_status", "value_json", "content_sha256", "finite_count", "nonfinite_count"], all_schema)
        csv_write(OUT / f"{name_prefix}_PAIR_INPUT_MATCH.csv", ["scene_id", "field_path", "classification", "B_present", "ON1_present", "B_shape_hdf5", "ON1_shape_hdf5", "B_dtype", "ON1_dtype", "B_content_sha256", "ON1_content_sha256", "comparison"], input_rows)
        csv_write(OUT / f"{name_prefix}_PAIR_FIELD_DIFF.csv", ["scene_id", "field_path", "classification", "B_present", "ON1_present", "B_value_json", "ON1_value_json", "comparison"], diff_rows)
        audit = {
            "status": "PASS_RECORD_AUDIT" if all(x["sha_and_stat_unchanged"] for x in file_rows) else "FAIL_INPUT_MUTATION",
            "mode": mode,
            "created_local": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "wall_seconds": time.perf_counter() - start_wall,
            "command": f"python -B {Path(__file__).relative_to(ROOT).as_posix()} --{mode}",
            "static_identities": static_identities,
            "frozen_source_checks": sources,
            "release": {k: release_obj[k] for k in ("state", "source_lock_sha256", "builder_sha256", "runner_sha256", "prior_release_sha256", "c_star", "max_total_sorties", "plant_authorized", "optimizer_steps", "test_accessed")},
            "manifest": manifest_info,
            "selected_run_records": len(selected_rows),
            "expected_raw_run_start_pairs": len(selected_rows),
            "file_records": len(file_rows),
            "h5_schema_rows": len(all_schema),
            "pair_input_comparisons": len(input_rows),
            "pair_field_differences": len(diff_rows),
            "run_start_schema": "Only runStart identity and partial options_audit; no per-run full cfg/opts snapshot observed in first pair; all selected file schemas captured in CSV.",
            "shared_cfg": {"path": locked_cfg["path"], "sha256": locked_cfg["expected_sha256"], "same_locked_file_for_all_runs": True, "per_run_cfg_snapshot_present": False},
            "opts": {"full_per_run_snapshot_present": False, "captured_options_audit_fields": "Enumerated recursively in H5_SCHEMA and pair diff; source-derived option construction is not described as an actual runtime snapshot."},
            "root_cfg_opts_presence": {f"{s}|{c}": rec["has_cfg_opts"] for (s, c), rec in records.items()},
            "status_counts": {str(v): sum(1 for rec in records.values() if rec["run_status"].get("status") == v) for v in sorted({rec["run_status"].get("status") for rec in records.values()})},
            "nonfinite_input_counts": {f"{s}|{c}|{p}": meta["nonfinite_count"] for (s, c), rec in records.items() for p, meta in rec["input_data"].items() if meta.get("present") and meta.get("nonfinite_count") not in (None, 0)},
        }
        (OUT / f"{name_prefix}_AUDIT.json").write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")
        state.update({"status": audit["status"], "completed_files": len(file_rows), "current_scene": None, "current_condition": None, "finished_local": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "wall_seconds": audit["wall_seconds"], "audit_json": str(OUT / f"{name_prefix}_AUDIT.json")})
        state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        print(json.dumps({"status": audit["status"], "mode": mode, "selected_run_records": len(selected_rows), "h5_schema_rows": len(all_schema), "pair_input_comparisons": len(input_rows), "pair_field_differences": len(diff_rows), "wall_seconds": audit["wall_seconds"], "outputs": [str(p) for p in outputs]}, ensure_ascii=False, indent=2))
    except Exception as exc:
        state.update({"status": "FAILED", "failure": repr(exc), "failed_local": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "wall_seconds": time.perf_counter() - start_wall})
        state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        fail_path = OUT / "FAILURES.csv"
        exists = fail_path.exists()
        with fail_path.open("a", newline="", encoding="utf-8-sig") as stream:
            writer = csv.DictWriter(stream, fieldnames=["time_local", "mode", "completed_files", "current_scene", "current_condition", "failure"])
            if not exists:
                writer.writeheader()
            writer.writerow({"time_local": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "mode": mode, "completed_files": state["completed_files"], "current_scene": state.get("current_scene"), "current_condition": state.get("current_condition"), "failure": repr(exc)})
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--sample", action="store_true")
    group.add_argument("--full", action="store_true")
    args = parser.parse_args()
    run("sample" if args.sample else "full")


if __name__ == "__main__":
    main()
