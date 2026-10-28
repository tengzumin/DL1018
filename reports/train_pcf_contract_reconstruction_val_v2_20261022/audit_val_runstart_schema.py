from __future__ import annotations

import csv
import hashlib
import json
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import h5py
import numpy as np
from scipy.io import loadmat, whosmat

import reconstruct_stratified as core


OUT = Path(__file__).resolve().parent
RESULTS = OUT / "VAL96_RUNSTART_SCHEMA_AUDIT.csv"
STATE = OUT / "VAL96_RUNSTART_SCHEMA_AUDIT.json"
EXPECTED_COUNT = 96
CHUNK = 8 << 20


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def signature(path: Path) -> dict:
    before = path.stat()
    t = time.perf_counter()
    digest = sha(path)
    elapsed = time.perf_counter() - t
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError(f"run_start changed while hashing: {path}")
    return {"sha256": digest, "bytes": after.st_size, "mtime_ns": after.st_mtime_ns, "hash_seconds": elapsed}


def now() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")


def main() -> None:
    for path, expected in core.EXPECTED.items():
        if sha(path) != expected:
            raise RuntimeError(f"frozen input-index SHA mismatch: {path}")
    raw_rows = [r for r in core.read_csv(core.RAW_INDEX) if r["split"].upper() == "VAL"]
    train_rows = [r for r in core.read_csv(core.TRAIN_INDEX) if r["split"].upper() == "VAL"]
    raw_by_id = {r["run_id"]: r for r in raw_rows}
    if len(raw_rows) != EXPECTED_COUNT or len(raw_by_id) != EXPECTED_COUNT or len(train_rows) != EXPECTED_COUNT:
        raise RuntimeError("frozen VAL indexes are not exactly 96 unique rows")
    if {r["run_id"] for r in raw_rows} != {r["run_id"] for r in train_rows}:
        raise RuntimeError("VAL training/raw index run_id sets differ")

    records = []
    for row in sorted(raw_rows, key=lambda r: r["run_id"]):
        path = core.scoped(row["run_start_path"])
        before = signature(path)
        if before["sha256"] != row["run_start_sha256"]:
            raise RuntimeError(f"frozen run_start SHA mismatch: {row['run_id']}")
        with path.open("rb") as f:
            prefix = f.read(128)
        item = {"run_id": row["run_id"], "run_start_path": str(path), "run_start_sha256": before["sha256"],
                "bytes": before["bytes"], "mtime_ns_before": before["mtime_ns"], "task": row["task"],
                "role": row["role"], "runtime_scene_id": row["runtime_scene_id"]}
        if prefix[124:128] == b"\x00\x02IM":
            with h5py.File(path, "r") as f:
                root_keys = sorted(f.keys())
                runstart = f.get("runStart")
                run_cfg = f.get("runStart/cfg")
                run_opts = f.get("runStart/opts")
                root_cfg = f.get("cfg")
                root_opts = f.get("opts")
                if isinstance(run_cfg, h5py.Group):
                    if root_opts is not None:
                        raise RuntimeError(f"{row['run_id']}: mixed /runStart/cfg and top-level /opts")
                    cfg_path, opts_path, fmt = "runStart/cfg", "runStart/opts", "MATLAB_7.3_RUNSTART_CFG_OPTS"
                elif isinstance(root_cfg, h5py.Group):
                    if run_opts is not None:
                        raise RuntimeError(f"{row['run_id']}: mixed top-level /cfg and /runStart/opts")
                    if root_opts is not None and not isinstance(root_opts, h5py.Group):
                        raise RuntimeError(f"{row['run_id']}: /opts exists but is not a group")
                    cfg_path, opts_path, fmt = "cfg", "opts", "MATLAB_7.3_ROOT_CFG_OPTS"
                else:
                    raise RuntimeError(f"{row['run_id']}: HDF5 has no recognized same-run cfg group")
                chosen_opts = f.get(opts_path)
                if chosen_opts is not None and not isinstance(chosen_opts, h5py.Group):
                    raise RuntimeError(f"{row['run_id']}: paired {opts_path} exists but is not a group")
                cfg = f[cfg_path]
                fields = {"mass": np.asarray(cfg["plant/mass"]), "g": np.asarray(cfg["plant/g"]),
                          "k1": np.asarray(cfg["control/bs/position/k1"]), "k2": np.asarray(cfg["control/bs/position/k2"])}
                if any(a.size not in (1, 3) or not np.isfinite(a).all() for a in fields.values()):
                    raise RuntimeError(f"{row['run_id']}: invalid target cfg field shape/value")
                flags = {}
                for name in ("physical_impulse_force_I", "rbf_disturbance_diagnostic", "state_perturbation"):
                    flags[name] = "ABSENT_OPTS" if chosen_opts is None else ("PRESENT" if name in chosen_opts else "ABSENT_FIELD")
                item.update(run_start_format=fmt, root_keys=";".join(root_keys), runStart_type=type(runstart).__name__ if runstart is not None else "ABSENT",
                            cfg_source="same-run /" + cfg_path,
                            opts_source=("same-run /" + opts_path) if chosen_opts is not None else "runtime defaults for absent /" + opts_path + f" (archived source {core.RUNTIME_SOURCE_SHA})",
                            cfg_mass_shape=str(fields["mass"].shape), cfg_g_shape=str(fields["g"].shape),
                            cfg_k1_shape=str(fields["k1"].shape), cfg_k2_shape=str(fields["k2"].shape),
                            cfg_mass=float(fields["mass"].reshape(-1)[0]), cfg_g=float(fields["g"].reshape(-1)[0]),
                            cfg_k1=";".join(map(str, fields["k1"].reshape(-1))), cfg_k2=";".join(map(str, fields["k2"].reshape(-1))),
                            opts_physical_impulse=flags["physical_impulse_force_I"],
                            opts_rbf_diagnostic=flags["rbf_disturbance_diagnostic"],
                            opts_state_perturbation=flags["state_perturbation"])
        else:
            variables = whosmat(path)
            names = {name for name, _, _ in variables}
            if "cfg" in names:
                raise RuntimeError(f"{row['run_id']}: MATLAB v5 has top-level cfg outside runStart")
            if "runStart" not in names:
                raise RuntimeError(f"{row['run_id']}: MATLAB v5 missing runStart variable")
            loaded = loadmat(path, variable_names=["runStart"], simplify_cells=True)["runStart"]
            cfg = loaded["cfg"]
            opts = loaded.get("opts")
            plant = cfg["plant"]
            pos = cfg["control"]["bs"]["position"]
            vals = {"mass": np.asarray(plant["mass"]), "g": np.asarray(plant["g"]),
                    "k1": np.asarray(pos["k1"]), "k2": np.asarray(pos["k2"])}
            if any(a.size not in (1, 3) or not np.isfinite(a).all() for a in vals.values()):
                raise RuntimeError(f"{row['run_id']}: invalid target cfg field shape/value")
            item.update(run_start_format="MATLAB_5", root_keys=";".join(sorted(names)), runStart_type=type(loaded).__name__,
                        cfg_source="same-run runStart.cfg",
                        opts_source="same-run runStart.opts" if isinstance(opts, dict) else f"runtime defaults for absent runStart.opts (archived source {core.RUNTIME_SOURCE_SHA})",
                        cfg_mass_shape=str(vals["mass"].shape), cfg_g_shape=str(vals["g"].shape),
                        cfg_k1_shape=str(vals["k1"].shape), cfg_k2_shape=str(vals["k2"].shape),
                        cfg_mass=float(vals["mass"].reshape(-1)[0]), cfg_g=float(vals["g"].reshape(-1)[0]),
                        cfg_k1=";".join(map(str, vals["k1"].reshape(-1))), cfg_k2=";".join(map(str, vals["k2"].reshape(-1))),
                        opts_physical_impulse="PRESENT" if isinstance(opts, dict) and "physical_impulse_force_I" in opts else "ABSENT_OPTS_OR_FIELD",
                        opts_rbf_diagnostic="PRESENT" if isinstance(opts, dict) and "rbf_disturbance_diagnostic" in opts else "ABSENT_OPTS_OR_FIELD",
                        opts_state_perturbation="PRESENT" if isinstance(opts, dict) and "state_perturbation" in opts else "ABSENT_OPTS_OR_FIELD")
        after = signature(path)
        if (before["sha256"], before["bytes"], before["mtime_ns"]) != (after["sha256"], after["bytes"], after["mtime_ns"]):
            raise RuntimeError(f"{row['run_id']}: run_start SHA/stat changed during schema audit")
        item["mtime_ns_after"] = after["mtime_ns"]
        item["hash_seconds_before"] = before["hash_seconds"]
        item["hash_seconds_after"] = after["hash_seconds"]
        item["source_sha_stat_unchanged"] = True
        records.append(item)

    counts = {}
    for item in records:
        counts[item["run_start_format"]] = counts.get(item["run_start_format"], 0) + 1
    fields = list(records[0])
    with RESULTS.open("x", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    state = {"phase": "VAL96_RUNSTART_SCHEMA_ONLY_AUDIT", "status": "PASS_SCHEMA_AUDIT", "completed_local": now(),
             "samples": len(records), "format_counts": counts, "raw_files_read": 0, "run_start_files_read": len(records),
             "source_index_sha256": {str(p): h for p, h in core.EXPECTED.items()},
             "runtime_source_sha256": core.RUNTIME_SOURCE_SHA, "results_csv": str(RESULTS.resolve()),
             "results_csv_sha256": sha(RESULTS), "all_run_start_sha_stat_unchanged": True}
    with STATE.open("x", encoding="utf-8") as f:
        f.write(json.dumps(state, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(state, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
