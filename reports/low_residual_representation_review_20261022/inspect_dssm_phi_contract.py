"""Bounded DSSM14 TRAIN representation audit. No training, MAT, VAL, or TEST access."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import time
from collections import Counter, defaultdict
from pathlib import Path

os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"

import numpy as np
import torch
from torch import nn


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
RECON = ROOT / "reports" / "train_pcf_contract_reconstruction_20261022"
SIDECARS = RECON / "fixed_model_sidecars"
RUNS = RECON / "TRAIN_FIXED_MODEL_5ca776c5f476_RUNS.csv"
MODEL_ROOT = ROOT.parent / "REFERENCE_FIX_FULL72_20261021_022342_313" / "corrected_reference_training_v1" / "corrected_pair_training"
MODEL_DIR = MODEL_ROOT / "models" / "official" / "DSSM14" / "seed2026102001"
CHECKPOINT = MODEL_DIR / "final_step.pt"
NORMALIZER = MODEL_ROOT / "data" / "normalizer_x14_train_only.npz"
FIT_RELEASE = MODEL_ROOT / "reports" / "PAIR_FINAL60K_FITS.json"
EXPORT_RELEASE = MODEL_ROOT / "reports" / "PAIR_FINAL60K_EXPORTS.json"
G6_PARITY = MODEL_ROOT / "reports" / "PAIR_MATLAB_PARITY_G6.json"
FIT_REPORT = MODEL_DIR / "fit_report.json"

WINDOW = 32
STRIDE = 5
THRESHOLDS_S = (5.0, 10.0, 15.0)
MAX_OUTPUT_BYTES = 100 * 1024 * 1024
MAX_EXACT_REPRESENTATIVE_ROWS = 20000
EXPORT_PARITY_TOL = 1e-5
RUNS_SHA = "4a072c8006042cbffa5e653e450432c748f337fa45790c330b9aa58a8ac32190"
CHECKPOINT_SHA = "544b018b78187d9d9cbbcbd5c3332244b80ad91cb137f32bd71198a4302dfbf5"
NORMALIZER_SHA = "520983e01aa9af38bd3c1aad15b5b8e6a65f5129a32e997e2234951ace198404"
MATLAB_EXPORT_SHA = "6f3628b10540c617496b2a20f249c4319af79c1a02d5945f1f91f0aead9c9b6e"
SOURCE_SHAS = {
    "pair_workflow.py": "a82f92465587f64f60b3c3109875a480a8ae164bf8562670808347820dbc233b",
    "teacher_data.py": "3d6ec20f544cda2ec99c3bddf17e595a75683c90fbd6b542475d006b6d2badad",
    "teacher_models.py": "7d38948b0ea2f70ec7d1f3c433063cdc7f264080e5f717262e56ba4fd8ec1c22",
    "fit_models.py": "31a08407f5b3fe66b42a7e930925e5ae4cdabfa0a764c218356eedb82ca4e9ff",
}
SMOKE_RUNS = {
    "G02_P_TEACHER_DL1018_TRAIN_T2_C00_W00_ACC_FIX_V1_B",
    "G02_P_TEACHER_DL1018_TRAIN_T1_C00_W00_B",
    "G02_P_TEACHER_DL1018_TRAIN_T3_C00_W00_B",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def fingerprint(path: Path) -> dict:
    s = path.stat()
    return {"sha256": sha256(path), "bytes": s.st_size, "mtime_ns": s.st_mtime_ns}


def json_read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def static_paths() -> dict[str, Path]:
    script_root = MODEL_ROOT / "scripts"
    return {
        **{name: script_root / name for name in SOURCE_SHAS},
        "checkpoint": CHECKPOINT,
        "normalizer": NORMALIZER,
        "fit_report": FIT_REPORT,
        "fit_release": FIT_RELEASE,
        "export_release": EXPORT_RELEASE,
        "g6_parity": G6_PARITY,
        "train_runs": RUNS,
    }


def verify_release_and_load_model() -> tuple[nn.Module, dict, dict[str, dict]]:
    paths = static_paths()
    expected = {
        **SOURCE_SHAS,
        "checkpoint": CHECKPOINT_SHA,
        "normalizer": NORMALIZER_SHA,
        "fit_report": "ab69002b465638ded0599964371eb17e3c1cecd0c587ca911c2054650c3cac72",
        "train_runs": RUNS_SHA,
    }
    before = {}
    for name, path in paths.items():
        require(path.is_file(), f"missing frozen input: {path}")
        before[name] = fingerprint(path)
        if name in expected:
            require(before[name]["sha256"] == expected[name], f"SHA mismatch: {name}")

    fit = json_read(FIT_RELEASE)
    require(fit.get("status") == "PASS_TWO_FIXED_FINAL60K_FITS", "fit release status mismatch")
    fit_model = next(x for x in fit["models"] if x.get("model_id") == "DSSM14")
    require(fit_model["seed"] == 2026102001, "fit seed mismatch")
    require(fit_model["final_checkpoint_sha256"] == CHECKPOINT_SHA, "fit checkpoint mismatch")
    require(fit["normalizer_sha256"] == NORMALIZER_SHA, "fit normalizer mismatch")

    exports = json_read(EXPORT_RELEASE)
    export_model = next(x for x in exports["exports"] if x.get("model_id") == "DSSM14")
    require(export_model["checkpoint_kind"] == "final_step", "export is not final_step")
    require(export_model["selected_step"] == 60000, "export step mismatch")
    require(export_model["checkpoint_sha256"] == CHECKPOINT_SHA, "export checkpoint mismatch")
    require(export_model["mat_sha256"] == MATLAB_EXPORT_SHA, "export MAT identity mismatch")

    parity = json_read(G6_PARITY)
    require(parity.get("status") == "PASS_G6_MATLAB_PARITY", "G6 parity status mismatch")
    require(parity.get("optimizer_steps") == 0 and parity.get("plant_calls") == 0, "G6 report is not read-only")
    require(parity.get("test_files_read") == 0, "G6 report records TEST access")
    parity_model = next(x for x in parity["models"] if x.get("model_id") == "DSSM14")
    require(parity_model["status"] == "PASS", "DSSM G6 model parity failed")
    require(parity_model["selected_step"] == 60000, "G6 step mismatch")
    require(parity_model["checkpoint_sha256"] == CHECKPOINT_SHA, "G6 checkpoint mismatch")
    require(parity_model["mat_sha256"] == MATLAB_EXPORT_SHA, "G6 export mismatch")
    require(float(parity_model["max_output_abs_error"]) <= float(parity["tolerance"]), "G6 output exceeds tolerance")

    norm = np.load(NORMALIZER, allow_pickle=False)
    mu = np.asarray(norm["mu"], dtype=np.float32)
    sigma = np.asarray(norm["sigma"], dtype=np.float32)
    require(mu.shape == (14,) and sigma.shape == (14,), "normalizer shape mismatch")

    payload = torch.load(CHECKPOINT, map_location="cpu", weights_only=True)
    require(payload.get("model_id") == "DSSM14", "checkpoint model mismatch")
    require(payload.get("seed") == 2026102001, "checkpoint seed mismatch")
    require(payload.get("selected_step") == 60000, "checkpoint is not final step 60000")
    require(payload.get("protocol_sha256") == fit["protocol_sha256"], "checkpoint protocol mismatch")
    state = payload["state_dict"]
    require(np.array_equal(state["input_mu"].numpy().reshape(-1), mu), "normalizer mu differs from checkpoint")
    require(np.array_equal(state["input_sigma"].numpy().reshape(-1), sigma), "normalizer sigma differs from checkpoint")

    class FrozenDSSM14(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.register_buffer("input_mu", torch.from_numpy(mu.copy()).reshape(1, 14))
            self.register_buffer("input_sigma", torch.from_numpy(sigma.copy()).reshape(1, 14))
            self.readout = nn.Linear(33, 3, bias=False)
            self.input_encoder = nn.Linear(14, 32)
            self.project = nn.Linear(32, 32)
            tau = torch.logspace(math.log10(0.02), math.log10(1.28), 32)
            self.log_tau = nn.Parameter(torch.log(tau))

        def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
            if x.ndim != 3 or x.shape[1:] != (32, 14):
                raise ValueError(f"expected [batch,32,14], got {tuple(x.shape)}")
            z = (x - self.input_mu[:, None, :]) / self.input_sigma[:, None, :]
            drive = torch.tanh(self.input_encoder(z))
            tau = torch.exp(self.log_tau).clamp(0.005, 5.0)
            alpha = torch.exp(-0.01 / tau)
            state = torch.zeros_like(drive[:, 0, :])
            for t in range(32):
                state = alpha * state + (1.0 - alpha) * drive[:, t, :]
            h = torch.tanh(self.project(state))
            v = torch.cat((h, torch.ones_like(h[:, :1])), dim=1)
            phi = v / torch.sqrt(1.0 + torch.sum(h * h, dim=1, keepdim=True))
            return z, phi, self.readout(phi)

    model = FrozenDSSM14().cpu()
    model.load_state_dict(state, strict=True)
    model.eval()

    # Recheck every static source after reading its associated metadata/checkpoint.
    after = {name: fingerprint(path) for name, path in paths.items()}
    require(before == after, "a frozen static input changed during model loading")
    release = {
        "checkpoint_sha256": before["checkpoint"]["sha256"],
        "normalizer_sha256": before["normalizer"]["sha256"],
        "normalizer_identity": "533aad9a2c66874cfa67f5d268661835e81e58b797cba7d6fc1c12d4013de5f0",
        "matlab_export_sha256_from_release": MATLAB_EXPORT_SHA,
        "g6_feature_abs_max": parity_model["max_feature_abs_error"],
        "g6_output_abs_max": parity_model["max_output_abs_error"],
        "g6_tolerance": parity["tolerance"],
    }
    return model, release, before


def read_train_runs() -> tuple[list[dict], dict]:
    require(sha256(RUNS) == RUNS_SHA, "TRAIN RUNS index SHA mismatch")
    with RUNS.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    require(len(rows) == 1536, f"expected 1536 TRAIN runs, got {len(rows)}")
    require(all(r.get("split") == "TRAIN" and r.get("status") == "PASS" for r in rows), "RUNS contains non-PASS or non-TRAIN rows")
    require(len({r["run_id"] for r in rows}) == len(rows), "duplicate run_id in TRAIN RUNS")
    return rows, {"sha256": RUNS_SHA, "rows": len(rows)}


def chosen_endpoints(event_time_s: np.ndarray) -> list[tuple[str, int]]:
    require(event_time_s.ndim == 1 and np.isfinite(event_time_s).all(), "invalid event_time_s")
    endpoints = np.arange(WINDOW - 1, len(event_time_s), STRIDE, dtype=np.int32)
    require(len(endpoints) == 394 and int(endpoints[-1]) == 1996, "stride-5 endpoint contract mismatch")
    chosen = []
    for threshold in THRESHOLDS_S:
        eligible = endpoints[event_time_s[endpoints] >= threshold]
        require(len(eligible) > 0, f"no stride endpoint >= {threshold}s")
        chosen.append((f"first_ge_{threshold:g}s", int(eligible[0])))
    chosen.append(("last_stride_endpoint", int(endpoints[-1])))
    require(len({x[1] for x in chosen}) == 4, "selected endpoints are not unique")
    return chosen


def expected_band(wind_cell: int) -> str:
    if 0 <= wind_cell <= 8:
        return "W00_W08"
    if 9 <= wind_cell <= 14:
        return "W09_W14"
    if wind_cell == 15:
        return "W15"
    raise RuntimeError(f"invalid wind_cell {wind_cell}")


def load_run_windows(row: dict) -> tuple[list[dict], list[np.ndarray], dict]:
    path = Path(row["sidecar_path"]).resolve()
    root = SIDECARS.resolve()
    require(path.is_relative_to(root) and path.name.startswith("TRAIN_"), f"sidecar escapes TRAIN root: {path}")
    before_stat = path.stat()
    before_sha = sha256(path)
    require(before_sha == row["sidecar_sha256"], f"sidecar SHA differs from frozen RUNS row: {row['run_id']}")
    require(before_stat.st_size == int(row["sidecar_bytes"]), f"sidecar byte count mismatch: {row['run_id']}")

    with np.load(path, allow_pickle=False) as z:
        for key, expected in (("run_id", row["run_id"]), ("task", row["task"]), ("role", row["role"]), ("split", "TRAIN"), ("runtime_scene_id", row["runtime_scene_id"])):
            require(str(z[key].item()) == expected, f"sidecar {key} identity mismatch: {row['run_id']}")
        x14 = np.asarray(z["X14"], dtype=np.float32)
        times = np.asarray(z["event_time_s"], dtype=np.float64)
        phase = np.asarray(z["phase_code"], dtype=np.uint8)
        ready = np.asarray(z["ready"], dtype=np.uint8)
        y_clip = np.asarray(z["Y_clip"], dtype=np.float32)
        valid_start = int(np.asarray(z["valid_start_zero_based"]).item())
        pred_valid = np.asarray(z["pred_raw_valid"], dtype=np.float64)
        event_index = np.asarray(z["event_index"], dtype=np.uint32)
        raw_index = np.asarray(z["raw_index"], dtype=np.uint32)
        plant_index = np.asarray(z["plant_index"], dtype=np.uint32)

        require(x14.shape == (1999, 14) and times.shape == (1999,), f"X14/time schema mismatch: {row['run_id']}")
        require(phase.shape == (1999,) and ready.shape == (1999,), f"phase/ready schema mismatch: {row['run_id']}")
        require(y_clip.shape == (1999, 3), f"Y_clip schema mismatch: {row['run_id']}")
        require(np.isfinite(x14).all() and np.isfinite(y_clip).all(), f"nonfinite TRAIN features/targets: {row['run_id']}")
        require(np.all(np.diff(times) > 0), f"event_time_s is not strictly increasing: {row['run_id']}")
        require(abs(times[0] - float(row["event_time_first_s"])) <= 1e-12 and abs(times[-1] - float(row["event_time_last_s"])) <= 1e-12, f"RUNS/sidecar time bounds differ: {row['run_id']}")
        chosen = chosen_endpoints(times)
        records, windows = [], []
        wind_cell = int(row["wind_cell"])
        require(row["wind_band"] == expected_band(wind_cell), f"wind_band mapping mismatch: {row['run_id']}")
        for label, end in chosen:
            start = end - WINDOW + 1
            require(start >= 0 and np.all(ready[start : end + 1] == 1), f"unready model window: {row['run_id']}@{end}")
            require(0 <= int(phase[end]) <= 5, f"invalid phase_code: {row['run_id']}@{end}")
            pred_index = end - valid_start
            require(0 <= pred_index < len(pred_valid), f"no sidecar output at selected endpoint: {row['run_id']}@{end}")
            hist = x14[start : end + 1].copy()
            require(hist.shape == (WINDOW, 14), "window extraction shape mismatch")
            records.append({
                "run_id": row["run_id"],
                "task": row["task"],
                "role": row["role"],
                "cache_scene_id": row["cache_scene_id"],
                "runtime_scene_id": row["runtime_scene_id"],
                "wind_cell": wind_cell,
                "wind_band": row["wind_band"],
                "selection": label,
                "end_position0": end,
                "event_time_s": float(times[end]),
                "event_index": int(event_index[end]),
                "raw_index": int(raw_index[end]),
                "plant_index": int(plant_index[end]),
                "phase_code": int(phase[end]),
                "target_y_clip": y_clip[end].copy(),
                "sidecar_pred_raw": pred_valid[pred_index].copy(),
                "sidecar_sha256": before_sha,
            })
            windows.append(hist)

    after_stat = path.stat()
    after_sha = sha256(path)
    require(before_sha == after_sha and before_stat.st_size == after_stat.st_size and before_stat.st_mtime_ns == after_stat.st_mtime_ns, f"sidecar changed while read: {row['run_id']}")
    return records, windows, {"run_id": row["run_id"], "sha256_before": before_sha, "sha256_after": after_sha, "bytes": before_stat.st_size}


def infer(model: nn.Module, records: list[dict], windows: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    require(len(records) == len(windows), "record/window count mismatch")
    z_out, phi_out, pred_out = [], [], []
    for start in range(0, len(windows), 128):
        xb = torch.from_numpy(np.stack(windows[start : start + 128])).to(dtype=torch.float32, device="cpu")
        with torch.inference_mode():
            z, phi, pred = model(xb)
        z_out.append(z.cpu().numpy().reshape(len(xb), -1).copy())
        phi_out.append(phi.cpu().numpy().copy())
        pred_out.append(pred.cpu().numpy().copy())
    return np.concatenate(z_out), np.concatenate(phi_out), np.concatenate(pred_out)


def array_sha(row: np.ndarray) -> str:
    return hashlib.sha256(np.asarray(row, dtype="<f4").tobytes()).hexdigest()


def row_out(sample: dict, z: np.ndarray, phi: np.ndarray, pred: np.ndarray) -> dict:
    err = pred.astype(np.float64) - sample["sidecar_pred_raw"]
    return {
        "run_id": sample["run_id"], "task": sample["task"], "role": sample["role"],
        "cache_scene_id": sample["cache_scene_id"], "wind_cell": sample["wind_cell"], "wind_band": sample["wind_band"],
        "selection": sample["selection"], "end_position0": sample["end_position0"],
        "event_time_s": f"{sample['event_time_s']:.17g}", "event_index": sample["event_index"],
        "raw_index": sample["raw_index"], "plant_index": sample["plant_index"], "phase_code": sample["phase_code"],
        "z_sha256": array_sha(z), "phi_sha256": array_sha(phi),
        "phi_norm_l2": f"{np.linalg.norm(phi.astype(np.float64)):.17g}",
        "target_y_clip_xyz": json.dumps(sample["target_y_clip"].astype(float).tolist(), separators=(",", ":")),
        "torch_pred_raw_xyz": json.dumps(pred.astype(float).tolist(), separators=(",", ":")),
        "sidecar_pred_raw_xyz": json.dumps(sample["sidecar_pred_raw"].astype(float).tolist(), separators=(",", ":")),
        "max_abs_torch_vs_sidecar": f"{np.max(np.abs(err)):.17g}",
        "sidecar_sha256": sample["sidecar_sha256"],
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("x", encoding="utf-8-sig", newline="") as f:
        if not rows:
            return
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def sample_id(s: dict) -> tuple[str, int]:
    return s["run_id"], int(s["end_position0"])


def valid_pair(a: dict, b: dict) -> bool:
    return a["run_id"] != b["run_id"] and a["cache_scene_id"] != b["cache_scene_id"]


def pair_values(i: int, j: int, records: list[dict], z64: np.ndarray, phi64: np.ndarray, pred: np.ndarray) -> dict:
    a, b = records[i], records[j]
    left, right = (i, j) if sample_id(a) <= sample_id(b) else (j, i)
    a, b = records[left], records[right]
    dy = b["target_y_clip"].astype(np.float64) - a["target_y_clip"].astype(np.float64)
    dp = pred[right].astype(np.float64) - pred[left].astype(np.float64)
    return {
        "left_run_id": a["run_id"], "left_end_position0": a["end_position0"], "left_time_s": f"{a['event_time_s']:.17g}",
        "left_scene_id": a["cache_scene_id"], "left_task": a["task"], "left_role": a["role"], "left_phase_code": a["phase_code"],
        "left_wind_cell": a["wind_cell"], "left_wind_band": a["wind_band"],
        "right_run_id": b["run_id"], "right_end_position0": b["end_position0"], "right_time_s": f"{b['event_time_s']:.17g}",
        "right_scene_id": b["cache_scene_id"], "right_task": b["task"], "right_role": b["role"], "right_phase_code": b["phase_code"],
        "right_wind_cell": b["wind_cell"], "right_wind_band": b["wind_band"],
        "dX_history_rms_448": f"{np.sqrt(np.mean((z64[left] - z64[right]) ** 2)):.17g}",
        "dphi_l2_33": f"{np.linalg.norm(phi64[left] - phi64[right]):.17g}",
        "delta_target_y_clip_right_minus_left_xyz": json.dumps(dy.tolist(), separators=(",", ":")),
        "delta_target_y_clip_norm": f"{np.linalg.norm(dy):.17g}",
        "delta_readout_raw_right_minus_left_xyz": json.dumps(dp.tolist(), separators=(",", ":")),
        "delta_readout_raw_norm": f"{np.linalg.norm(dp):.17g}",
    }


def legal_exact_pair_count(members: list[int], records: list[dict]) -> int:
    """Count unordered pairs with distinct runs and scenes without enumerating them."""
    n = len(members)
    all_pairs = n * (n - 1) // 2
    by_run = Counter(records[i]["run_id"] for i in members)
    by_scene = Counter(records[i]["cache_scene_id"] for i in members)
    by_run_scene = Counter((records[i]["run_id"], records[i]["cache_scene_id"]) for i in members)
    same_run = sum(k * (k - 1) // 2 for k in by_run.values())
    same_scene = sum(k * (k - 1) // 2 for k in by_scene.values())
    same_run_and_scene = sum(k * (k - 1) // 2 for k in by_run_scene.values())
    return all_pairs - same_run - same_scene + same_run_and_scene


def exact_bucket_specs(records: list[dict], zflat: np.ndarray, phi: np.ndarray) -> list[tuple]:
    groups: dict[tuple, list[int]] = defaultdict(list)
    for i, s in enumerate(records):
        groups[(s["task"], s["role"], s["phase_code"])].append(i)
    specs = []
    kind_arrays = (("normalized_history_float32_exact", zflat), ("phi33_float32_exact", phi))
    for key in sorted(groups):
        ids = groups[key]
        for kind_order, (kind, arr) in enumerate(kind_arrays):
            buckets: dict[bytes, list[int]] = defaultdict(list)
            for i in ids:
                buckets[np.asarray(arr[i], dtype="<f4").tobytes()].append(i)
            for bits in sorted(buckets):
                same = buckets[bits]
                if len(same) < 2 or legal_exact_pair_count(same, records) == 0:
                    continue
                same.sort(key=lambda i: sample_id(records[i]))
                specs.append((key, kind_order, kind, bits, same))
    return specs


def exact_pairs(records: list[dict], zflat: np.ndarray, phi: np.ndarray, z64: np.ndarray, phi64: np.ndarray, pred: np.ndarray) -> tuple[list[dict], dict]:
    specs = exact_bucket_specs(records, zflat, phi)
    total_by_kind = {"normalized_history_float32_exact": 0, "phi33_float32_exact": 0}
    for _, _, kind, _, members in specs:
        total_by_kind[kind] += legal_exact_pair_count(members, records)

    saved = []
    saved_by_kind = {"normalized_history_float32_exact": 0, "phi33_float32_exact": 0}
    for key, _, kind, _, members in specs:
        if len(saved) >= MAX_EXACT_REPRESENTATIVE_ROWS:
            break
        # Group first by run/scene so dense invalid same-run or same-scene pairs
        # are not scanned as an O(n^2) list of sample pairs.
        by_run_scene: dict[tuple[str, str], list[int]] = defaultdict(list)
        for i in members:
            by_run_scene[(records[i]["run_id"], records[i]["cache_scene_id"])].append(i)
        unit_keys = sorted(by_run_scene)
        for left_pos, left_key in enumerate(unit_keys):
            left_members = by_run_scene[left_key]
            for right_pos in range(left_pos + 1, len(unit_keys)):
                right_key = unit_keys[right_pos]
                if left_key[0] == right_key[0] or left_key[1] == right_key[1]:
                    continue
                for i in left_members:
                    for j in by_run_scene[right_key]:
                        left, right = sorted((i, j), key=lambda x: sample_id(records[x]))
                        row = pair_values(left, right, records, z64, phi64, pred)
                        row["identity_kind"] = kind
                        row["task_role_phase"] = "/".join(map(str, key))
                        saved.append(row)
                        saved_by_kind[kind] += 1
                        if len(saved) >= MAX_EXACT_REPRESENTATIVE_ROWS:
                            break
                    if len(saved) >= MAX_EXACT_REPRESENTATIVE_ROWS:
                        break
                if len(saved) >= MAX_EXACT_REPRESENTATIVE_ROWS:
                    break
            if len(saved) >= MAX_EXACT_REPRESENTATIVE_ROWS:
                break
    total = sum(total_by_kind.values())
    saved_count = len(saved)
    stats = {
        "representative_row_cap": MAX_EXACT_REPRESENTATIVE_ROWS,
        "total_legal_pairs_by_kind": total_by_kind,
        "saved_representatives_by_kind": saved_by_kind,
        "truncated_by_kind": {kind: saved_by_kind[kind] < total_by_kind[kind] for kind in total_by_kind},
        "total_legal_pairs": total,
        "saved_representatives": saved_count,
        "truncated": saved_count < total,
    }
    return saved, stats


def nearest_pairs(records: list[dict], zflat: np.ndarray, phi: np.ndarray, pred: np.ndarray) -> tuple[list[dict], dict]:
    groups: dict[tuple, list[int]] = defaultdict(list)
    for i, s in enumerate(records):
        groups[(s["task"], s["role"], s["phase_code"])].append(i)
    z64 = zflat.astype(np.float64)
    phi64 = phi.astype(np.float64)
    output = {}
    unique_candidates = 0
    directed_candidates = 0
    for key, ids in groups.items():
        ids.sort(key=lambda i: sample_id(records[i]))
        # Count and inspect each selected query against eligible cross-run/cross-scene candidates.
        for i in ids:
            js = [j for j in ids if valid_pair(records[i], records[j])]
            directed_candidates += len(js)
            unique_candidates += sum(sample_id(records[j]) > sample_id(records[i]) for j in js)
            if not js:
                continue
            js_arr = np.asarray(js, dtype=np.int32)
            dx = z64[js_arr] - z64[i]
            d_history = np.sqrt(np.mean(dx * dx, axis=1))
            dp = phi64[js_arr] - phi64[i]
            d_phi = np.sqrt(np.sum(dp * dp, axis=1))
            same_cell = np.asarray([records[j]["wind_cell"] == records[i]["wind_cell"] for j in js], dtype=bool)
            for relation, mask in (("same_wind_cell", same_cell), ("cross_wind_cell", ~same_cell)):
                if not mask.any():
                    continue
                for metric, distances in (("nearest_by_history", d_history), ("nearest_by_phi", d_phi)):
                    local = np.flatnonzero(mask)
                    # js is sorted by run/end; argmin breaks exact ties deterministically.
                    best_pos = int(local[np.argmin(distances[local])])
                    j = int(js_arr[best_pos])
                    left, right = sorted((i, j), key=lambda x: sample_id(records[x]))
                    pkey = (metric, relation, sample_id(records[left]), sample_id(records[right]))
                    if pkey not in output:
                        row = pair_values(left, right, records, z64, phi64, pred)
                        row["nearest_metric"] = metric
                        row["wind_relation"] = relation
                        row["selected_by_queries"] = 0
                        row["task_role_phase"] = "/".join(map(str, key))
                        output[pkey] = row
                    output[pkey]["selected_by_queries"] += 1
    return list(output.values()), {
        "task_role_phase_group_count": len(groups),
        "max_group_size": max((len(v) for v in groups.values()), default=0),
        "eligible_unique_cross_run_scene_candidate_pairs": unique_candidates,
        "eligible_directed_query_candidates": directed_candidates,
        "query_count": len(records),
        "deduplicated_nearest_pair_rows": len(output),
    }


def outputs_prefix(mode: str) -> str:
    return f"{mode}_{sha256(Path(__file__))[:12]}"


def finish_output_guard() -> None:
    total = sum(p.stat().st_size for p in OUT.iterdir() if p.is_file())
    require(total <= MAX_OUTPUT_BYTES, f"review directory exceeds 100 MiB: {total}")


def main() -> None:
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--smoke", action="store_true", help="only three fixed TRAIN runs; never reads VAL")
    mode.add_argument("--full-train", action="store_true", help="all 1536 TRAIN runs; requires parent review of this script SHA")
    args = ap.parse_args()

    started = time.perf_counter()
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    OUT.mkdir(parents=True, exist_ok=True)
    model, release, static_before = verify_release_and_load_model()
    rows, run_index = read_train_runs()
    if args.smoke:
        selected = [r for r in rows if r["run_id"] in SMOKE_RUNS]
        require(len(selected) == 3 and {r["task"] for r in selected} == {"FIG8_3D", "HELIX", "SQUARE"}, "fixed smoke run selection mismatch")
        mode_name = "smoke"
    else:
        selected = rows
        require(len(selected) == 1536, "full mode must read exactly the 1536 TRAIN rows")
        mode_name = "train"

    records, windows, sidecar_guards = [], [], []
    for row in selected:
        rec, win, guard = load_run_windows(row)
        records.extend(rec)
        windows.extend(win)
        sidecar_guards.append(guard)
    expected_count = 12 if args.smoke else 6144
    require(len(records) == expected_count, f"expected {expected_count} selected windows, got {len(records)}")
    zflat, phi, pred = infer(model, records, windows)
    del windows
    require(zflat.shape == (expected_count, WINDOW * 14) and phi.shape == (expected_count, 33) and pred.shape == (expected_count, 3), "inference output shape mismatch")
    parity_err = np.asarray([np.max(np.abs(pred[i].astype(np.float64) - s["sidecar_pred_raw"])) for i, s in enumerate(records)])
    require(float(parity_err.max(initial=0.0)) <= EXPORT_PARITY_TOL, f"Torch/checkpoint output differs from frozen sidecar export: {parity_err.max()}")
    require(np.max(np.abs(np.linalg.norm(phi.astype(np.float64), axis=1) - 1.0)) <= 3e-6, "phi is not unit norm")

    static_after = {name: fingerprint(path) for name, path in static_paths().items()}
    require(static_before == static_after, "a static source changed during audit")
    sample_rows = [row_out(s, zflat[i], phi[i], pred[i]) for i, s in enumerate(records)]
    prefix = outputs_prefix(mode_name)
    if args.smoke:
        csv_path = OUT / f"{prefix}_checks.csv"
        json_path = OUT / f"{prefix}_metadata.json"
        write_csv(csv_path, sample_rows)
        meta = {
            "status": "PASS_THREE_TRAIN_RUN_SMOKE",
            "scope": "TRAIN only; no MAT, VAL, TEST, Plant, GPU, or optimizer",
            "selected_runs": sorted(SMOKE_RUNS),
            "selected_windows": len(records),
            "selection_rule": "first sidecar event_time_s >= 5/10/15 plus last stride-5 endpoint",
            "actual_endpoint_times_s": [s["event_time_s"] for s in records],
            "source_hashes_and_stats_before": static_before,
            "source_hashes_and_stats_after": static_after,
            "run_index": run_index,
            "model_release": release,
            "sidecar_guards": sidecar_guards,
            "parity_tolerance": EXPORT_PARITY_TOL,
            "max_torch_vs_sidecar_pred_raw_abs": float(parity_err.max(initial=0.0)),
            "phi_unit_norm_abs_max": float(np.max(np.abs(np.linalg.norm(phi.astype(np.float64), axis=1) - 1.0))),
            "elapsed_s": time.perf_counter() - started,
            "output_files": {"checks_csv": csv_path.name, "metadata_json": json_path.name},
        }
        json_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    else:
        exact, exact_stats = exact_pairs(records, zflat, phi, zflat.astype(np.float64), phi.astype(np.float64), pred)
        nearest, pair_stats = nearest_pairs(records, zflat, phi, pred)
        win_csv = OUT / f"{prefix}_windows.csv"
        exact_csv = OUT / f"{prefix}_exact_pairs.csv"
        nearest_csv = OUT / f"{prefix}_nearest_pairs.csv"
        json_path = OUT / f"{prefix}_metadata.json"
        write_csv(win_csv, sample_rows)
        write_csv(exact_csv, exact)
        write_csv(nearest_csv, nearest)
        meta = {
            "status": "PASS_TRAIN_DSSM_REPRESENTATION_AUDIT",
            "scope": "TRAIN only; no MAT, VAL, TEST, Plant, GPU, or optimizer",
            "run_count": len(selected), "window_count": len(records),
            "selection_rule": "first sidecar event_time_s >= 5/10/15 plus last stride-5 endpoint",
            "actual_endpoint_time_min_max_s": [float(min(s["event_time_s"] for s in records)), float(max(s["event_time_s"] for s in records))],
            "phase_group": "endpoint phase_code; exact same task/role/phase only",
            "candidate_rules": "different run_id and different cache_scene_id; all other selected windows in matching task/role/phase",
            "wind_grouping": {"source": "frozen RUNS.wind_band", "values": sorted({s["wind_band"] for s in records}), "W15_cell": 15, "planned_HF_band": "W09_W14"},
            "distance_definitions": {"history": "sqrt(mean((z_i-z_j)^2)) over 448 model-normalized float32 values, accumulated float64", "phi": "L2 over 33 float32 phi values, accumulated float64"},
            "exact_equality": "bytewise float32 equality after checkpoint normalization for z or phi33; no tolerance-based near threshold",
            "pair_stats": pair_stats,
            "exact_pair_stats": exact_stats, "nearest_pair_rows": len(nearest),
            "source_hashes_and_stats_before": static_before,
            "source_hashes_and_stats_after": static_after,
            "run_index": run_index,
            "model_release": release,
            "sidecar_guards": sidecar_guards,
            "parity_tolerance": EXPORT_PARITY_TOL,
            "max_torch_vs_sidecar_pred_raw_abs": float(parity_err.max(initial=0.0)),
            "phi_unit_norm_abs_max": float(np.max(np.abs(np.linalg.norm(phi.astype(np.float64), axis=1) - 1.0))),
            "elapsed_s": time.perf_counter() - started,
            "interpretation_limit": "Descriptive sample relations only; no mathematical non-identifiability lower bound and no closed-loop causal claim.",
            "output_files": {"windows_csv": win_csv.name, "exact_pairs_csv": exact_csv.name, "nearest_pairs_csv": nearest_csv.name, "metadata_json": json_path.name},
        }
        json_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    finish_output_guard()
    print(json.dumps({"status": meta["status"], "output_files": meta["output_files"], "max_torch_vs_sidecar_pred_raw_abs": meta["max_torch_vs_sidecar_pred_raw_abs"], "elapsed_s": meta["elapsed_s"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
