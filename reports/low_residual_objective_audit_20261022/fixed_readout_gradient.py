from __future__ import annotations
import argparse
import csv
import hashlib
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# Keep the diagnostic CPU-only and single-threaded.
for _name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_name] = "1"

import h5py
import numpy as np

OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT))
import replay_objective as replay

MODEL_SOURCE = replay.ARCHIVE / "corrected_pair_eval_v1" / "runs" / "r098" / "attempt_01" / "raw_run.mat"
MODEL_SHA256 = "f6fc258dbee1d33dbac608d94f690b23e5329d375d2806d9bb0601a667506ea5"
MODEL_ID = "CORRECTED_DSSM14_SEED2026102001_FINAL60000"
MODEL_ARRAY_ID = "8de4d6548316c7b6f97382ecc9d5fbce8c00dbf6d10dc4187789b34c9205eb26"
NORMALIZER_ID = "533aad9a2c66874cfa67f5d268661835e81e58b797cba7d6fc1c12d4013de5f0"
MODEL_NAMES = ("input_mu", "input_sigma", "input_W", "input_b", "project_W", "project_b", "output_W", "ssm_tau")
ARRAY_ID_ORDER = ("input_W", "input_b", "input_mu", "input_sigma", "output_W", "project_W", "project_b", "ssm_tau")
LAMBDA = 1e-5


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def local_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def array_set_id(model: dict[str, np.ndarray], names: tuple[str, ...]) -> str:
    h = hashlib.sha256()
    for name in names:
        a = np.ascontiguousarray(model[name])
        h.update(name.encode("utf-8") + b"\0")
        h.update(repr((a.shape, str(a.dtype))).encode("ascii") + b"\0")
        h.update(a.tobytes(order="C"))
    return h.hexdigest()


def load_model_once() -> tuple[dict[str, np.ndarray], dict[str, object]]:
    before_stat = replay.stat_key(MODEL_SOURCE)
    before_sha = replay.sha256_file(MODEL_SOURCE)
    require(before_sha == MODEL_SHA256, f"model raw SHA mismatch: {before_sha}")
    with h5py.File(MODEL_SOURCE, "r") as f:
        group = f["opts/stage1_position_runtime/model"]
        model = {name: np.asarray(group[name], dtype=np.float64) for name in MODEL_NAMES}
    after_stat = replay.stat_key(MODEL_SOURCE)
    after_sha = replay.sha256_file(MODEL_SOURCE)
    require(before_stat == after_stat and before_sha == after_sha, "model raw SHA/stat changed during array read")
    shapes = {
        "input_mu": (1, 14), "input_sigma": (1, 14), "input_W": (14, 32), "input_b": (1, 32),
        "project_W": (32, 32), "project_b": (1, 32), "output_W": (3, 33), "ssm_tau": (1, 32),
    }
    for name, arr in model.items():
        require(arr.shape == shapes[name] and np.isfinite(arr).all(), f"model array schema/nonfinite mismatch: {name} {arr.shape}")
    require(np.all(model["input_sigma"] > 0) and np.all(model["ssm_tau"] > 0), "nonpositive model normalizer/tau")
    model_array_id = array_set_id(model, ARRAY_ID_ORDER)
    normalizer_id = array_set_id(model, ("input_mu", "input_sigma"))
    require(model_array_id == MODEL_ARRAY_ID, f"model array identity mismatch: {model_array_id}")
    require(normalizer_id == NORMALIZER_ID, f"normalizer identity mismatch: {normalizer_id}")
    return model, {
        "path": str(MODEL_SOURCE), "file_sha256": after_sha, "bytes": MODEL_SOURCE.stat().st_size,
        "mtime_ns": MODEL_SOURCE.stat().st_mtime_ns, "model_id": MODEL_ID,
        "model_array_identity": model_array_id, "normalizer_identity": normalizer_id,
        "source_sha_stat_unchanged_during_single_read": True,
    }


def guarded_x14(run: dict[str, str], source: dict[str, str]) -> np.ndarray:
    path = Path(source["cache_path"])
    before_stat = replay.stat_key(path)
    before_sha = replay.sha256_file(path)
    require(before_sha == source["cache_sha256"], f"{run['run_id']}: cache pre-read SHA mismatch")
    cache = np.load(path, allow_pickle=False)
    try:
        require(replay.scalar_text(cache, "run_id") == run["run_id"], f"{run['run_id']}: cache run_id mismatch on X14 read")
        require(replay.scalar_text(cache, "split").upper() == "TRAIN", f"{run['run_id']}: non-TRAIN cache on X14 read")
        arr = np.asarray(cache["x14"])
        require(arr.shape == (1999, 14) and arr.dtype == np.float32 and np.isfinite(arr).all(),
                f"{run['run_id']}: X14 schema/nonfinite mismatch")
        x14 = np.array(arr, dtype=np.float64, copy=True)
    finally:
        cache.close()
    after_stat = replay.stat_key(path)
    after_sha = replay.sha256_file(path)
    require(before_stat == after_stat and before_sha == after_sha, f"{run['run_id']}: cache SHA/stat changed during X14 read")
    return x14


def encode_endpoints(x14: np.ndarray, ends: np.ndarray, model: dict[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    require(x14.shape == (1999, 14) and np.isfinite(x14).all(), "encoder input must be finite (1999,14) X14")
    drive = np.tanh(((x14 - model["input_mu"]) / model["input_sigma"]) @ model["input_W"] + model["input_b"])
    alpha = np.exp(-0.01 / model["ssm_tau"]).reshape(32)
    state = np.zeros((len(ends), 32), dtype=np.float64)
    for lag in range(32):
        state += (1.0 - alpha) * alpha ** lag * drive[ends - lag]
    hidden = np.tanh(state @ model["project_W"] + model["project_b"])
    phi = np.concatenate((hidden, np.ones((len(hidden), 1), dtype=np.float64)), axis=1)
    phi /= np.sqrt(1.0 + np.sum(hidden * hidden, axis=1, keepdims=True))
    pred = phi @ model["output_W"].T
    require(phi.shape == (len(ends), 33) and pred.shape == (len(ends), 3), "encoded feature/prediction shape mismatch")
    require(np.isfinite(phi).all() and np.isfinite(pred).all(), "encoded feature/prediction nonfinite")
    return phi, pred


def analytic_gradient(phi: np.ndarray, pred: np.ndarray, y: np.ndarray, weight: np.ndarray) -> np.ndarray:
    d = (pred - y) / 3.0
    clipped = np.clip(d, -1.0, 1.0)
    g = (clipped * weight.astype(np.float64, copy=False)[:, None]).T @ phi / 9.0
    require(g.shape == (3, 33) and np.isfinite(g).all(), "analytic readout gradient invalid")
    return g


def torch_autograd_check(phi: np.ndarray, y: np.ndarray, weight: np.ndarray, W: np.ndarray) -> dict[str, float]:
    import torch
    import torch.nn.functional as F

    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    n = min(16, len(phi))
    ph = torch.tensor(phi[:n], dtype=torch.float64, device="cpu")
    target = torch.tensor(y[:n], dtype=torch.float64, device="cpu")
    wt = torch.tensor(weight[:n].astype(np.float64), dtype=torch.float64, device="cpu")
    w = torch.tensor(W, dtype=torch.float64, device="cpu", requires_grad=True)
    pred = ph @ w.T
    loss = torch.sum(wt * F.smooth_l1_loss(pred / 3.0, target / 3.0, reduction="none").mean(dim=1))
    loss.backward()
    expected = analytic_gradient(phi[:n], (phi[:n] @ W.T), y[:n], weight[:n])
    max_abs = float(torch.max(torch.abs(w.grad - torch.from_numpy(expected))).item())
    max_rel = float((torch.linalg.vector_norm(w.grad - torch.from_numpy(expected)) /
                     torch.clamp(torch.linalg.vector_norm(w.grad), min=1e-300)).item())
    require(max_abs <= 2e-14 and max_rel <= 2e-13, f"float64 autograd/analytic gradient mismatch: {max_abs}, {max_rel}")
    return {"windows": n, "loss": float(loss.item()), "max_abs_gradient_error": max_abs, "relative_gradient_error": max_rel,
            "device": "cpu", "optimizer_created": False}


def run_gradient(run: dict[str, str], source: dict[str, str],
                 scene_counts: dict[tuple[str, str, int], int],
                 model: dict[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, float]:
    ends, side_pred, y, _raw_y, phase, weights, _phase_counts, _phase_n = replay.load_one(
        run, source, scene_counts)
    x14 = guarded_x14(run, source)
    phi, pred = encode_endpoints(x14, ends, model)
    parity = float(np.max(np.abs(pred - side_pred)))
    require(parity <= 1e-12, f"{run['run_id']}: raw W0 prediction parity exceeded 1e-12: {parity}")
    g = analytic_gradient(phi, pred, y, weights)
    return ends, phi, pred, y, weights, g, parity


def cosine(a: np.ndarray, b: np.ndarray) -> tuple[float | None, float]:
    dot = float(np.sum(a * b))
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    return (dot / (na * nb) if na > 0 and nb > 0 else None), dot


def write_json_once(path: Path, data: dict[str, object]) -> None:
    require(not path.exists(), f"refusing to overwrite existing output: {path}")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def append_failure(exc: BaseException, command: str, started: float) -> None:
    path = OUT / "GRADIENT_FAILURES.csv"
    row = {
        "generated_local": local_now(), "command": command,
        "script_sha256": replay.sha256_file(Path(__file__)),
        "exception_type": type(exc).__name__, "exception": str(exc),
        "wall_seconds": time.perf_counter() - started,
        "optimizer_steps": 0, "plant_calls": 0, "gpu_jobs": 0, "test_accessed": False,
    }
    exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(row))
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def group_labels(run: dict[str, str]) -> tuple[tuple[str, str], ...]:
    task, role = run["task"], run["role"]
    band, cell = run["wind_band"], run["wind_cell"]
    return (
        ("ALL", "ALL"),
        ("WIND_BAND", band),
        ("WIND_CELL", cell),
        ("TASK_ROLE_WIND_BAND", f"{task}|{role}|{band}"),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Fixed-W0 readout-gradient diagnostic; no parameter updates")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--smoke", action="store_true", help="one frozen TRAIN run plus float64 autograd check")
    modes.add_argument("--execute-after-audit", action="store_true", help="all TRAIN1536; requires separate parent approval")
    args = parser.parse_args()
    started = time.perf_counter()
    command = "python -B " + " ".join(sys.argv)
    try:
        runs, source_by_id, scene_counts = replay.check_static_inputs()
        model, model_source = load_model_once()
        W = model["output_W"]
        G_wd = LAMBDA * W
        if args.smoke:
            run = runs[0]
            ends, phi, pred, y, weight, G_data, parity = run_gradient(
                run, source_by_id[run["run_id"]], scene_counts, model)
            auto = torch_autograd_check(phi, y, weight, W)
            cos_dw, dot_dw = cosine(G_data, G_wd)
            result = {
                "status": "PASS_READOUT_GRADIENT_SMOKE_ONE_TRAIN_RUN",
                "generated_local": local_now(), "command": command,
                "script_sha256": replay.sha256_file(Path(__file__)),
                "replay_script_sha256": replay.sha256_file(Path(replay.__file__)),
                "train_runs_sha256": replay.EXPECTED["runs_sha256"],
                "training_index_sha256": replay.EXPECTED["train_index_sha256"],
                "model_source": model_source, "run_id": run["run_id"],
                "task": run["task"], "role": run["role"], "wind_band": run["wind_band"], "wind_cell": run["wind_cell"],
                "endpoint_count": int(len(ends)), "endpoint_recipe_0based": "31+5*k, k=0..393",
                "max_abs_raw_prediction_vs_sidecar": parity, "parity_tolerance": 1e-12,
                "float32_weight_mass": float(weight.astype(np.float64).sum()),
                "sample_G_data_frobenius_norm": float(np.linalg.norm(G_data)),
                "sample_lambdaW_frobenius_norm": float(np.linalg.norm(G_wd)),
                "sample_data_vs_lambdaW_dot": dot_dw, "sample_data_vs_lambdaW_cosine": cos_dw,
                "autograd_check": auto,
                "diagnostic_scope": "fixed-readout Euclidean gradient only; not Adam, full-network, or closed-loop direction",
                "optimizer_steps": 0, "plant_calls": 0, "gpu_jobs": 0, "test_accessed": False, "dev_labels_used": False,
                "wall_seconds": time.perf_counter() - started,
            }
            replay.check_static_inputs()
            write_json_once(OUT / "GRADIENT_SMOKE.json", result)
            print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
            return 0

        outputs = ("READOUT_GRADIENT_GROUPS.csv", "READOUT_GRADIENT_GLOBAL.json", "READOUT_GRADIENT_STATE.json")
        for name in outputs:
            require(not (OUT / name).exists(), f"refusing to overwrite existing output: {OUT / name}")
        groups: dict[tuple[str, str], dict[str, object]] = {}
        total_weight = 0.0
        max_parity = 0.0
        for i, run in enumerate(runs, start=1):
            source = source_by_id[run["run_id"]]
            ends, phi, pred, y, weight, g_run, parity = run_gradient(run, source, scene_counts, model)
            max_parity = max(max_parity, parity)
            total_weight += float(weight.astype(np.float64).sum())
            for key in group_labels(run):
                agg = groups.get(key)
                if agg is None:
                    agg = {"gradient": np.zeros((3, 33), dtype=np.float64), "windows": 0, "mass": 0.0, "runs": set()}
                    groups[key] = agg
                agg["gradient"] += g_run
                agg["windows"] += int(len(ends))
                agg["mass"] += float(weight.astype(np.float64).sum())
                agg["runs"].add(run["run_id"])
            if i % 128 == 0 or i == len(runs):
                print(f"PROGRESS {i}/{len(runs)} TRAIN runs; weight_mass={total_weight:.9f}; max_parity={max_parity:.3g}; elapsed={time.perf_counter()-started:.1f}s", flush=True)

        require(len(runs) == 1536 and sum(int(g["windows"]) for k, g in groups.items() if k[0] == "ALL") == 605184,
                "TRAIN gradient run/window cardinality mismatch")
        require(abs(total_weight - 1.0) < 2e-6, f"float32 hierarchical weight mass mismatch: {total_weight}")
        require(max_parity <= 1e-12, f"maximum raw prediction parity exceeded tolerance: {max_parity}")
        replay.check_static_inputs()
        G_data = np.asarray(groups[("ALL", "ALL")]["gradient"])
        G_total = G_data + G_wd
        rows: list[dict[str, object]] = []
        for (scope, label), agg in sorted(groups.items()):
            grad = np.asarray(agg["gradient"])
            for axis_idx, axis in enumerate(("X", "Y", "Z")):
                ga = grad[axis_idx]
                gd = G_data[axis_idx]
                gt = G_total[axis_idx]
                cos_data, dot_data = cosine(ga, gd)
                cos_total, dot_total = cosine(ga, gt)
                mass = float(agg["mass"])
                norm = float(np.linalg.norm(ga))
                rows.append({
                    "scope": scope, "group": label, "axis": axis,
                    "runs": len(agg["runs"]), "endpoints": int(agg["windows"]), "weight_mass": mass,
                    "gradient_norm": norm, "gradient_norm_per_weight_mass": norm / mass if mass else None,
                    "gradient_vector_json": json.dumps(ga.tolist(), separators=(",", ":")),
                    "dot_global_data_same_axis": dot_data, "cos_global_data_same_axis": cos_data,
                    "dot_global_regularized_same_axis": dot_total, "cos_global_regularized_same_axis": cos_total,
                })
        csv_path = OUT / "READOUT_GRADIENT_GROUPS.csv"
        with csv_path.open("x", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        cos_data_wd, dot_data_wd = cosine(G_data, G_wd)
        cos_data_total, dot_data_total = cosine(G_data, G_total)
        cos_wd_total, dot_wd_total = cosine(G_wd, G_total)
        summary = {
            "status": "PASS_TRAIN1536_FIXED_READOUT_GRADIENT",
            "generated_local": local_now(), "command": command,
            "script_sha256": replay.sha256_file(Path(__file__)),
            "replay_script_sha256": replay.sha256_file(Path(replay.__file__)),
            "train_runs_sha256": replay.EXPECTED["runs_sha256"],
            "training_index_sha256": replay.EXPECTED["train_index_sha256"],
            "phase_state_sha256": replay.EXPECTED["phase_state_sha256"],
            "model_source": model_source,
            "episodes": len(runs), "endpoints": len(runs) * 394,
            "endpoint_recipe_0based": "31+5*k, k=0..393",
            "total_float32_weight_mass": total_weight,
            "max_abs_raw_prediction_vs_sidecar": max_parity, "parity_tolerance": 1e-12,
            "loss_gradient": "sum_i w_i * clip((p_i-y_i)/3,-1,1)^T @ phi_i / 9; exact cache float32 labels and float32 hierarchical weights",
            "regularization": {"source": "frozen Adam weight_decay", "lambda": LAMBDA, "term": "lambda * frozen output_W", "gradient_role": "reported separately; no parameters updated"},
            "G_data_matrix_3x33": G_data.tolist(), "lambdaW_matrix_3x33": G_wd.tolist(), "G_total_matrix_3x33": G_total.tolist(),
            "G_data_frobenius_norm": float(np.linalg.norm(G_data)),
            "lambdaW_frobenius_norm": float(np.linalg.norm(G_wd)),
            "G_total_frobenius_norm": float(np.linalg.norm(G_total)),
            "pre_full_smoke_script_sha256": "838cca836b85430e5c017112fa4a2b29c9f21ef072d96cbbe77adef20fb4a3fd",
            "pre_full_smoke_note": "Serialization-only change after approved smoke; numeric path and guards unchanged.",
            "dot_Gdata_lambdaW": dot_data_wd, "cos_Gdata_lambdaW": cos_data_wd,
            "dot_Gdata_Gtotal": dot_data_total, "cos_Gdata_Gtotal": cos_data_total,
            "dot_lambdaW_Gtotal": dot_wd_total, "cos_lambdaW_Gtotal": cos_wd_total,
            "groups": {scope: sum(1 for k in groups if k[0] == scope) for scope in sorted({k[0] for k in groups})},
            "group_csv": {"path": str(csv_path), "sha256": replay.sha256_file(csv_path), "bytes": csv_path.stat().st_size, "rows": len(rows)},
            "interpretation_limit": "Fixed-readout Euclidean geometry at W0 only; group-vs-global alignment does not equal Adam's actual update, full-network gradient direction, or closed-loop causal effect.",
            "optimizer_steps": 0, "plant_calls": 0, "gpu_jobs": 0, "test_accessed": False, "dev_labels_used": False,
            "wall_seconds": time.perf_counter() - started,
        }
        write_json_once(OUT / "READOUT_GRADIENT_GLOBAL.json", summary)
        state = {
            "status": summary["status"], "generated_local": local_now(), "command": command,
            "script_sha256": summary["script_sha256"], "summary_sha256": replay.sha256_file(OUT / "READOUT_GRADIENT_GLOBAL.json"),
            "groups_sha256": summary["group_csv"]["sha256"], "episodes": len(runs), "windows": len(runs) * 394,
            "optimizer_steps": 0, "plant_calls": 0, "gpu_jobs": 0, "test_accessed": False,
            "wall_seconds": summary["wall_seconds"], "failures": [],
        }
        write_json_once(OUT / "READOUT_GRADIENT_STATE.json", state)
        print(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except Exception as exc:
        append_failure(exc, command, started)
        print(json.dumps({
            "status": "FAILED", "generated_local": local_now(), "command": command,
            "script_sha256": replay.sha256_file(Path(__file__)), "exception_type": type(exc).__name__,
            "exception": str(exc), "wall_seconds": time.perf_counter() - started,
            "optimizer_steps": 0, "plant_calls": 0, "gpu_jobs": 0, "test_accessed": False,
        }, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


