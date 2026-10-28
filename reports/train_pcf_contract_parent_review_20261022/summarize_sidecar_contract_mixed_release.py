from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from collections import defaultdict
from pathlib import Path

import numpy as np


OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
TRAIN_OUT = ROOT / "reports" / "train_pcf_contract_reconstruction_20261022"
TRAIN_WORKER_SHA = "5ca776c5f476c8e7ad824c11ab1381d48b6fdf0b385f9471522a8f5826a8021a"
TRAIN_CORE_SHA = "d2e2c807b8119b32eddba8f765c6c566bee40d5e37c0590363f9091d30a47f70"
TRAIN_STATE_SHA = "b5fb66aafc7f934ae199037bd318c85974d1e41724bc54c805ed14900beaf002"
TRAIN_RUNS_SHA = "4a072c8006042cbffa5e653e450432c748f337fa45790c330b9aa58a8ac32190"
TRAIN_METRICS_SHA = "c4d5fa3092266daf133977b8ffc97e30a1616516845f080032d97e19af0c0866"
# Fill only from the reviewed, PASS VAL peer release. --full fails closed until pinned.
VAL_OUT = ROOT / "reports" / "train_pcf_contract_reconstruction_val_v2_20261022"
VAL_WORKER_SHA = "e445610c306d33c014cc7ec59fdb9168cefca0713c3019e6fd61e31d800bc962"
VAL_CORE_SHA = "8cc54696cc2d05e11d4e55e263b5eb9c9250f11851deb1c0b1f8719c9810f711"
VAL_STATE_SHA = "05fd6672c009b4821084954777c30758a6076be5f06000b1ff1f0ace16c77499"
VAL_RUNS_SHA = "c48d1238d3c0b55babcb161909ad817f48b98f2f5d1b24c5a9b9afea85688fb3"
VAL_METRICS_SHA = "7d3ec99186d57867ee228ff66d73dcfedd75a3a14ff68bcf34f660e5357e938b"
MODEL_SOURCE_SHA = "f6fc258dbee1d33dbac608d94f690b23e5329d375d2806d9bb0601a667506ea5"
MODEL_ARRAY_ID = "8de4d6548316c7b6f97382ecc9d5fbce8c00dbf6d10dc4187789b34c9205eb26"
VALID_START = 31
EVENTS = 1999
DT = 0.01
FS = 1.0 / DT
MAX_OUTPUT_BYTES = 160 * (1 << 20)
TARGETS = ("Y_raw", "Y_clip", "Y_plus_Mrf_raw", "Y_plus_Mrf_clip")
AXES = (("X", (0,)), ("Y", (1,)), ("Z", (2,)), ("ALL", (0, 1, 2)))
METRICS = (
    "target_rms_mps2", "prior_applied_rms_mps2", "zero_rmse_mps2",
    "prior_applied_rmse_mps2", "prior_to_zero_rmse_ratio",
    "relative_sse_reduction_vs_zero", "zero_error_bias_mps2",
    "zero_absbias_mps2", "prior_error_bias_mps2", "prior_absbias_mps2",
    "zero_lowfreq_0_1hz_rms_mps2", "prior_lowfreq_0_1hz_rms_mps2",
)
SCENE_COLUMNS = (
    "split", "worker_script_sha256", "core_script_sha256", "run_id", "task", "role", "wind_band", "window", "phase_code",
    "events", "target", "axis", *METRICS, "worse_than_zero",
)
GROUP_COLUMNS = (
    "split", "worker_script_sha256", "core_script_sha256", "group_type", "group_value", "window", "phase_code", "target", "axis",
    "scenes", "mean_events_per_scene", *("mean_" + name for name in METRICS),
    "worse_than_zero_scene_count", "worse_than_zero_scene_fraction",
)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def signature(path: Path) -> dict:
    path = path.resolve(strict=True)
    before = path.stat()
    digest = sha(path)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError(f"input changed while hashing: {path}")
    return {"path": str(path), "sha256": digest, "bytes": after.st_size, "mtime_ns": after.st_mtime_ns}


def tracked(path: Path, inputs: dict[str, dict]) -> Path:
    path = path.resolve(strict=True)
    key = str(path)
    if key not in inputs:
        inputs[key] = signature(path)
    return path


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def expected_phase_paths(split: str) -> tuple[Path, Path, Path]:
    release = release_spec(split)
    stem = f"{split}_FIXED_MODEL_{release['worker_sha'][:12]}"
    out = Path(release["out"])
    return (out / f"{stem}_PHASE_STATE.json",
            out / f"{stem}_RUNS.csv",
            out / f"{stem}_METRICS.csv")


def release_spec(split: str) -> dict:
    if split == "TRAIN":
        release = {"out": TRAIN_OUT, "worker_sha": TRAIN_WORKER_SHA, "core_sha": TRAIN_CORE_SHA,
                   "state_sha": TRAIN_STATE_SHA, "runs_sha": TRAIN_RUNS_SHA,
                   "metrics_sha": TRAIN_METRICS_SHA}
    elif split == "VAL":
        release = {"out": VAL_OUT, "worker_sha": VAL_WORKER_SHA, "core_sha": VAL_CORE_SHA,
                   "state_sha": VAL_STATE_SHA, "runs_sha": VAL_RUNS_SHA,
                   "metrics_sha": VAL_METRICS_SHA}
    else:
        raise ValueError(f"unsupported split: {split}")
    missing = [key for key, value in release.items() if value is None]
    if missing:
        raise RuntimeError(f"{split} release is not pinned yet: {', '.join(missing)}")
    return release


def in_dir(path: Path, directory: Path) -> bool:
    try:
        path.resolve(strict=True).relative_to(directory.resolve(strict=True))
        return True
    except ValueError:
        return False


def load_phase(split: str, inputs: dict[str, dict]) -> dict:
    release = release_spec(split)
    state_path, expected_runs, expected_metrics = expected_phase_paths(split)
    tracked(state_path, inputs)
    if inputs[str(state_path.resolve())]["sha256"] != release["state_sha"]:
        raise RuntimeError(f"{split} phase-state SHA differs from the pinned release")
    state = read_json(state_path)
    status = "PASS_TRAIN_1536" if split == "TRAIN" else "PASS_VAL_96"
    n_expected = 1536 if split == "TRAIN" else 96
    if state.get("status") != status:
        raise RuntimeError(f"{split} is not complete: state status={state.get('status')!r}")
    if (state.get("worker_script_sha256") != release["worker_sha"] or state.get("core_script_sha256") != release["core_sha"]
            or state.get("split") != split or state.get("expected_samples") != n_expected
            or state.get("sidecar_count") != n_expected or state.get("all_samples_passed") is not True
            or state.get("sidecar_hashes_present") is not True
            or state.get("model", {}).get("model_array_identity") != MODEL_ARRAY_ID):
        raise RuntimeError(f"{split} PASS state identity/count mismatch")
    if state.get("model", {}).get("file_sha256") != MODEL_SOURCE_SHA:
        raise RuntimeError(f"{split} PASS state fixed-model source SHA mismatch")
    if any(state.get(k) != 0 for k in ("optimizer_steps", "plant_calls", "gpu_jobs")):
        raise RuntimeError(f"{split} state reports training, plant, or GPU work")
    if state.get("test_accessed") is not False or state.get("dev_labels_used") is not False:
        raise RuntimeError(f"{split} state reports TEST/dev-label access")
    if Path(state.get("runs_csv", "")).resolve() != expected_runs.resolve() or Path(state.get("metrics_csv", "")).resolve() != expected_metrics.resolve():
        raise RuntimeError(f"{split} state points at unexpected RUNS/METRICS files")
    worker_path = tracked(Path(state.get("worker_script", "")), inputs)
    core_path = tracked(Path(state.get("core_script", "")), inputs)
    if (not in_dir(worker_path, Path(release["out"])) or not in_dir(core_path, Path(release["out"]))
            or inputs[str(worker_path)]["sha256"] != release["worker_sha"]
            or inputs[str(core_path)]["sha256"] != release["core_sha"]):
        raise RuntimeError(f"{split} state does not resolve to the pinned worker/core sources")
    tracked(expected_runs, inputs)
    tracked(expected_metrics, inputs)
    if (inputs[str(expected_runs.resolve())]["sha256"] != release["runs_sha"]
            or inputs[str(expected_metrics.resolve())]["sha256"] != release["metrics_sha"]):
        raise RuntimeError(f"{split} RUNS/METRICS SHA differs from the pinned release")
    runs = read_csv(expected_runs)
    metrics = read_csv(expected_metrics)
    if len(runs) != n_expected or len({r.get("run_id") for r in runs}) != n_expected:
        raise RuntimeError(f"{split} RUNS count/identity mismatch")
    if len(metrics) != n_expected * 16:
        raise RuntimeError(f"{split} METRICS row count mismatch: {len(metrics)}")
    if any(r.get("status") != "PASS" or r.get("split") != split
           or r.get("worker_script_sha256") != release["worker_sha"] or r.get("core_script_sha256") != release["core_sha"]
           or r.get("model_array_identity") != MODEL_ARRAY_ID
           or r.get("model_source_sha256") != state.get("model", {}).get("file_sha256")
           for r in runs):
        raise RuntimeError(f"{split} RUNS contains an identity/status mismatch")
    if sum(int(r["sidecar_bytes"]) for r in runs) != int(state.get("sidecar_bytes_written", -1)):
        raise RuntimeError(f"{split} sidecar-byte total differs from PASS state")
    metric_keys = [(r.get("run_id"), r.get("target"), r.get("axis")) for r in metrics]
    expected_keys = {(r["run_id"], target, axis)
                     for r in runs for target in TARGETS for axis, _ in AXES}
    if len(set(metric_keys)) != len(metric_keys) or set(metric_keys) != expected_keys:
        raise RuntimeError(f"{split} METRICS keys do not match RUNS x 4 targets x 4 axes")
    if any(r.get("split") != split or int(r.get("valid_events", -1)) != EVENTS - VALID_START
           for r in metrics):
        raise RuntimeError(f"{split} METRICS split/valid-event mismatch")
    return {"split": split, "state_path": state_path, "state": state, "runs": runs,
            "metrics": metrics, "run_by_id": {r["run_id"]: r for r in runs}}


def scalar_text(z, name: str) -> str:
    value = np.asarray(z[name]).item()
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


def require_close(name: str, actual, expected, tol: float = 1e-12) -> float:
    actual = np.asarray(actual, dtype=np.float64)
    expected = np.asarray(expected, dtype=np.float64)
    if actual.shape != expected.shape or not np.isfinite(actual).all() or not np.isfinite(expected).all():
        raise RuntimeError(f"invalid shape/nonfinite data in {name}")
    err = float(np.max(np.abs(actual - expected))) if actual.size else 0.0
    if err > tol:
        raise RuntimeError(f"{name} mismatch: max_abs={err:.6g} > {tol:g}")
    return err


def lowfreq_rms_0_1hz(error: np.ndarray, time_s: np.ndarray) -> float:
    if len(error) < 2 or len(time_s) != len(error):
        raise RuntimeError("low-frequency window is too short or time-misaligned")
    if not np.allclose(np.diff(time_s), DT, rtol=0.0, atol=1e-12):
        raise RuntimeError("FFT requested for a non-contiguous/nonuniform time window")
    spectrum = np.fft.rfft(error, axis=0)
    freq = np.fft.rfftfreq(len(error), d=DT)
    weights = np.full(len(freq), 2.0)
    weights[0] = 1.0
    if len(error) % 2 == 0:
        weights[-1] = 1.0
    keep = freq <= 1.0 + 1e-12
    channel_ms = np.sum(weights[keep, None] * np.abs(spectrum[keep]) ** 2, axis=0) / (len(error) ** 2)
    return float(np.sqrt(np.mean(channel_ms)))


def one_metric(run: dict, window: str, phase_code, event_ids: np.ndarray,
               time_s: np.ndarray, targets: dict[str, np.ndarray], pred: np.ndarray,
               use_fft: bool) -> list[dict]:
    if not len(event_ids):
        raise RuntimeError(f"empty metric window: {run['run_id']} {window}")
    if use_fft and (np.any(np.diff(event_ids) != 1) or not np.allclose(np.diff(time_s[event_ids]), DT, rtol=0.0, atol=1e-12)):
        raise RuntimeError(f"FFT window is discontinuous: {run['run_id']} {window}")
    rows = []
    pred_ids = event_ids - VALID_START
    for target_name in TARGETS:
        target = targets[target_name][event_ids]
        applied = pred[pred_ids]
        for axis_name, axes in AXES:
            t = target[:, axes].reshape(-1)
            p = applied[:, axes].reshape(-1)
            zero_rmse = float(np.sqrt(np.mean(t * t)))
            prior_rmse = float(np.sqrt(np.mean((p - t) ** 2)))
            zero_bias = float(np.mean(-t))
            prior_bias = float(np.mean(p - t))
            zero_absbias = float(np.mean(np.abs(np.mean(-target[:, axes], axis=0))))
            prior_absbias = float(np.mean(np.abs(np.mean(applied[:, axes] - target[:, axes], axis=0))))
            if axis_name == "ALL":
                tf = target
                pf = applied
            else:
                tf = target[:, axes]
                pf = applied[:, axes]
            rows.append({
                "split": run["split"], "worker_script_sha256": run["worker_script_sha256"],
                "core_script_sha256": run["core_script_sha256"],
                "run_id": run["run_id"], "task": run["task"],
                "role": run["role"], "wind_band": run["wind_band"], "window": window,
                "phase_code": "" if phase_code is None else int(phase_code),
                "events": len(event_ids), "target": target_name, "axis": axis_name,
                "target_rms_mps2": zero_rmse,
                "prior_applied_rms_mps2": float(np.sqrt(np.mean(p * p))),
                "zero_rmse_mps2": zero_rmse, "prior_applied_rmse_mps2": prior_rmse,
                "prior_to_zero_rmse_ratio": prior_rmse / zero_rmse if zero_rmse > 0 else None,
                "relative_sse_reduction_vs_zero": 1.0 - (prior_rmse / zero_rmse) ** 2 if zero_rmse > 0 else None,
                "zero_error_bias_mps2": zero_bias, "zero_absbias_mps2": zero_absbias,
                "prior_error_bias_mps2": prior_bias, "prior_absbias_mps2": prior_absbias,
                "zero_lowfreq_0_1hz_rms_mps2": lowfreq_rms_0_1hz(-tf, time_s[event_ids]) if use_fft else None,
                "prior_lowfreq_0_1hz_rms_mps2": lowfreq_rms_0_1hz(pf - tf, time_s[event_ids]) if use_fft else None,
                "worse_than_zero": int(prior_rmse > zero_rmse),
            })
    return rows


def load_sidecar(run: dict, state: dict, inputs: dict[str, dict]) -> dict:
    release = release_spec(run["split"])
    path = Path(run["sidecar_path"]).resolve(strict=True)
    sidecar_dir = Path(release["out"]) / "fixed_model_sidecars"
    if not in_dir(path, sidecar_dir):
        raise RuntimeError(f"sidecar escapes frozen worker output directory: {path}")
    sig = signature(path)
    inputs.setdefault(str(path), sig)
    if sig["sha256"] != run["sidecar_sha256"] or sig["bytes"] != int(run["sidecar_bytes"]):
        raise RuntimeError(f"sidecar SHA/size differs from RUNS: {run['run_id']}")
    with np.load(path, allow_pickle=False) as z:
        required = ("event_time_s", "event_index", "plant_index", "raw_index", "phase_code",
                    "beta_candidate", "Y_raw", "Y_clip", "r_f", "mixed_raw", "mixed_clip",
                    "a_req", "a_f", "pred_raw_valid", "pred_applied_valid", "valid_start_zero_based",
                    "run_id", "split", "task", "role", "runtime_scene_id")
        if any(name not in z for name in required):
            raise RuntimeError(f"sidecar missing required arrays: {run['run_id']}")
        meta = {name: scalar_text(z, name) for name in ("run_id", "split", "task", "role", "runtime_scene_id")}
        if any(meta[k] != str(run[k]) for k in meta):
            raise RuntimeError(f"sidecar identity mismatch for {run['run_id']}: {meta}")
        if (run.get("worker_script_sha256") != release["worker_sha"] or run.get("core_script_sha256") != release["core_sha"]
                or run.get("model_array_identity") != state.get("model", {}).get("model_array_identity")):
            raise RuntimeError(f"RUNS model/source identity mismatch for {run['run_id']}")
        t = np.asarray(z["event_time_s"], dtype=np.float64).reshape(-1)
        event_index = np.asarray(z["event_index"], dtype=np.int64).reshape(-1)
        plant_index = np.asarray(z["plant_index"], dtype=np.int64).reshape(-1)
        raw_index = np.asarray(z["raw_index"], dtype=np.int64).reshape(-1)
        phase = np.asarray(z["phase_code"], dtype=np.int64).reshape(-1)
        beta = np.asarray(z["beta_candidate"], dtype=np.float32).reshape(-1)
        y = np.asarray(z["Y_raw"], dtype=np.float64)
        y_clip = np.asarray(z["Y_clip"], dtype=np.float32)
        rf = np.asarray(z["r_f"], dtype=np.float64)
        mixed = np.asarray(z["mixed_raw"], dtype=np.float64)
        mixed_clip = np.asarray(z["mixed_clip"], dtype=np.float32)
        a_req = np.asarray(z["a_req"], dtype=np.float64)
        a_f = np.asarray(z["a_f"], dtype=np.float64)
        pred_raw = np.asarray(z["pred_raw_valid"], dtype=np.float64)
        pred = np.asarray(z["pred_applied_valid"], dtype=np.float64)
        valid_start = int(np.asarray(z["valid_start_zero_based"]).item())
    if valid_start != VALID_START or any(a.shape != (EVENTS,) for a in (t, event_index, plant_index, raw_index, phase, beta)):
        raise RuntimeError(f"sidecar event indexing/length mismatch: {run['run_id']}")
    if any(a.shape != (EVENTS, 3) for a in (y, y_clip, rf, mixed, mixed_clip, a_req, a_f)):
        raise RuntimeError(f"sidecar target shape mismatch: {run['run_id']}")
    nvalid = EVENTS - valid_start
    if pred_raw.shape != (nvalid, 3) or pred.shape != (nvalid, 3):
        raise RuntimeError(f"sidecar prediction shape mismatch: {run['run_id']}")
    if not all(np.isfinite(a).all() for a in (t, beta, y, y_clip, rf, mixed, mixed_clip, a_req, a_f, pred_raw, pred)):
        raise RuntimeError(f"sidecar contains nonfinite contract data: {run['run_id']}")
    if not (np.array_equal(event_index, np.arange(1, EVENTS + 1))
            and np.array_equal(plant_index, raw_index + 1)
            and np.allclose(np.diff(t), DT, rtol=0.0, atol=1e-12)):
        raise RuntimeError(f"sidecar time/index mapping mismatch: {run['run_id']}")
    if np.any((phase < 0) | (phase > 5)):
        raise RuntimeError(f"unexpected phase_code outside 0..5: {run['run_id']}")
    beta_expected = np.clip(t / 1.8, 0.0, 1.0).astype(np.float32)
    if not np.array_equal(beta, beta_expected):
        raise RuntimeError(f"candidate beta clip mismatch: {run['run_id']}")
    beta64 = np.clip(t / 1.8, 0.0, 1.0)
    pred_expected = beta64[valid_start:, None] * np.clip(pred_raw, -3.0, 3.0)
    max_beta_prediction_err = require_close("candidate beta applied to clipped prediction", pred, pred_expected)
    mixed_expected = y.copy()
    mixed_expected[:, :2] += rf[:, :2]
    max_mixed_err = require_close("mixed target Y+diag(1,1,0)rf", mixed, mixed_expected)
    if not np.array_equal(mixed[:, 2], y[:, 2]):
        raise RuntimeError(f"mixed-target Z axis changed: {run['run_id']}")
    max_rf_err = require_close("r_f=a_req-a_f", rf, a_req - a_f)
    if np.max(np.abs(y_clip.astype(np.float64) - np.clip(y, -3.0, 3.0))) > 5e-7:
        raise RuntimeError(f"float32 Y_clip does not quantize clipped double Y: {run['run_id']}")
    if np.max(np.abs(mixed_clip.astype(np.float64) - np.clip(mixed, -3.0, 3.0))) > 5e-7:
        raise RuntimeError(f"float32 mixed_clip does not quantize clipped double mixed target: {run['run_id']}")
    return {"time_s": t, "phase_code": phase, "y": y, "rf": rf, "mixed": mixed,
            "pred": pred, "pred_raw": pred_raw, "valid_start": valid_start,
            "max_mixed_err": max_mixed_err, "max_rf_err": max_rf_err,
            "max_beta_prediction_err": max_beta_prediction_err,
            "candidate_beta_max_abs": float(np.max(np.abs(beta.astype(np.float64) - beta64)))}


def target_map(a: dict) -> dict[str, np.ndarray]:
    # Reclip double-precision raw arrays; stored *_clip sidecar arrays are float32.
    return {"Y_raw": a["y"], "Y_clip": np.clip(a["y"], -3.0, 3.0),
            "Y_plus_Mrf_raw": a["mixed"], "Y_plus_Mrf_clip": np.clip(a["mixed"], -3.0, 3.0)}


def max_worker_metric_delta(rows: list[dict], metrics_by_key: dict[tuple, dict]) -> float:
    fields = ("target_rms_mps2", "prior_applied_rms_mps2", "zero_rmse_mps2",
              "prior_applied_rmse_mps2", "prior_to_zero_rmse_ratio",
              "relative_sse_reduction_vs_zero", "prior_error_bias_mps2", "zero_error_bias_mps2")
    delta = 0.0
    for row in rows:
        key = (row["run_id"], row["target"], row["axis"])
        m = metrics_by_key.get(key)
        if m is None:
            raise RuntimeError(f"missing worker METRICS row: {key}")
        for name in fields:
            if row[name] is None:
                if m[name] != "UNDEFINED_ZERO_ENERGY":
                    raise RuntimeError(f"undefined zero-energy metric mismatch {key} {name}")
                continue
            actual = float(row[name])
            expected = float(m[name])
            err = abs(actual - expected)
            delta = max(delta, err)
            if err > 2e-12:
                raise RuntimeError(f"independent metric mismatch {key} {name}: {err:.6g}")
    return delta


def group_keys(row: dict):
    yield "overall", "ALL"
    yield "wind_band", row["wind_band"]
    yield "task_x_wind_band", f"{row['task']}|{row['wind_band']}"
    yield "role_x_wind_band", f"{row['role']}|{row['wind_band']}"


def add_to_groups(acc: dict, row: dict):
    identity = (row["split"], row["worker_script_sha256"], row["core_script_sha256"],
                row["window"], row["phase_code"], row["target"], row["axis"])
    values = {name: row[name] for name in METRICS}
    for group_type, group_value in group_keys(row):
        key = (group_type, group_value) + identity
        a = acc[key]
        a["scenes"] += 1
        a["events"] += int(row["events"])
        a["worse"] += int(row["worse_than_zero"])
        for name, value in values.items():
            if value is not None:
                a[name] += float(value)
                a[name + "_n"] += 1


def group_rows(acc: dict) -> list[dict]:
    rows = []
    for key, a in sorted(acc.items(), key=lambda item: tuple(str(x) for x in item[0])):
        group_type, group_value, split, worker_sha, core_sha, window, phase_code, target, axis = key
        out = {"split": split, "worker_script_sha256": worker_sha,
               "core_script_sha256": core_sha, "group_type": group_type, "group_value": group_value,
               "window": window, "phase_code": phase_code, "target": target, "axis": axis,
               "scenes": a["scenes"], "mean_events_per_scene": a["events"] / a["scenes"],
               "worse_than_zero_scene_count": a["worse"],
               "worse_than_zero_scene_fraction": a["worse"] / a["scenes"]}
        for name in METRICS:
            count = a[name + "_n"]
            out["mean_" + name] = a[name] / count if count else None
        rows.append(out)
    return rows


def csv_text(rows: list[dict], columns: tuple[str, ...]) -> str:
    f = io.StringIO(newline="")
    writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return f.getvalue()


def verify_inputs_unchanged(inputs: dict[str, dict]) -> dict[str, dict]:
    after = {}
    for path in sorted(inputs):
        current = signature(Path(path))
        before = inputs[path]
        if (current["sha256"], current["bytes"], current["mtime_ns"]) != (before["sha256"], before["bytes"], before["mtime_ns"]):
            raise RuntimeError(f"input SHA/stat changed during summarization: {path}")
        after[path] = current
    return after


def run_single(inputs: dict[str, dict]):
    train = load_phase("TRAIN", inputs)
    run = sorted(train["runs"], key=lambda r: r["run_id"])[0]
    side = load_sidecar(run, train["state"], inputs)
    targets = target_map(side)
    valid = np.arange(side["valid_start"], EVENTS)
    rows = one_metric(run, "allvalid", None, valid, side["time_s"], targets, side["pred"], True)
    by_key = {(r["run_id"], r["target"], r["axis"]): r for r in train["metrics"] if r["run_id"] == run["run_id"]}
    max_delta = max_worker_metric_delta(rows, by_key)
    after = verify_inputs_unchanged(inputs)
    sidecar_key = str(Path(run["sidecar_path"]).resolve())
    return {"status": "PASS_SINGLE_SIDECAR", "run_id": run["run_id"],
            "sidecar_sha256": inputs[sidecar_key]["sha256"],
            "metrics_rows_independently_recomputed": len(rows),
            "max_worker_metric_abs_delta": max_delta,
            "max_mixed_identity_abs_error": side["max_mixed_err"],
            "max_rf_sign_abs_error": side["max_rf_err"],
            "max_beta_prediction_abs_error": side["max_beta_prediction_err"],
            "candidate_beta_float32_max_quantization": side["candidate_beta_max_abs"],
            "all_read_input_sha_stat_unchanged": True, "inputs_checked": len(after)}


def run_full(inputs: dict[str, dict]):
    phases = [load_phase("TRAIN", inputs), load_phase("VAL", inputs)]
    train_state, val_state = phases[0]["state"], phases[1]["state"]
    train_indices = train_state.get("source_indices", {})
    val_indices = val_state.get("source_indices", {})
    shared_index_keys = ("training_index_sha256", "raw_index_sha256", "availability_sha256")
    if (train_state.get("model", {}).get("model_array_identity") != val_state.get("model", {}).get("model_array_identity")
            or train_state.get("model", {}).get("file_sha256") != val_state.get("model", {}).get("file_sha256")
            or any(train_indices.get(k) != val_indices.get(k) for k in shared_index_keys)
            or train_indices.get("sample_count") != 1536 or val_indices.get("sample_count") != 96
            or train_state.get("runtime_source_sha256_before") != val_state.get("runtime_source_sha256_before")
            or train_state.get("runtime_source_sha256_after") != val_state.get("runtime_source_sha256_after")):
        raise RuntimeError("TRAIN/VAL do not share fixed-model, index, or runtime identity")
    if set(phases[0]["run_by_id"]) & set(phases[1]["run_by_id"]):
        raise RuntimeError("TRAIN and VAL run_id sets overlap")
    metric_lookup = {}
    for phase in phases:
        metric_lookup.update({(r["run_id"], r["target"], r["axis"]): r for r in phase["metrics"]})
    scene_buffer = io.StringIO(newline="")
    scene_writer = csv.DictWriter(scene_buffer, fieldnames=SCENE_COLUMNS, lineterminator="\n")
    scene_writer.writeheader()
    aggregate = defaultdict(lambda: {"scenes": 0, "events": 0, "worse": 0,
                                    **{name: 0.0 for name in METRICS},
                                    **{name + "_n": 0 for name in METRICS}})
    max_metric_delta = 0.0
    max_mixed_err = max_rf_err = max_beta_pred_err = 0.0
    candidate_beta_quantization_max = 0.0
    processed = 0
    for phase in phases:
        for run in sorted(phase["runs"], key=lambda r: r["run_id"]):
            side = load_sidecar(run, phase["state"], inputs)
            targets = target_map(side)
            valid = np.arange(side["valid_start"], EVENTS)
            time_s = side["time_s"]
            pred = side["pred"]
            windows = (
                ("allvalid", valid),
                ("beta1_ge_1p8s", valid[time_s[valid] >= 1.8]),
                ("late_ge_5s", valid[time_s[valid] >= 5.0]),
                ("early_lt_5s", valid[time_s[valid] < 5.0]),
            )
            for name, ids in windows:
                rows = one_metric(run, name, None, ids, time_s, targets, pred, True)
                if name == "allvalid":
                    max_metric_delta = max(max_metric_delta, max_worker_metric_delta(rows, metric_lookup))
                for row in rows:
                    scene_writer.writerow(row)
                    add_to_groups(aggregate, row)
            valid_phase = side["phase_code"][valid]
            for code in np.unique(valid_phase):
                ids = valid[valid_phase == code]
                rows = one_metric(run, "phase_code", int(code), ids, time_s, targets, pred, False)
                for row in rows:
                    scene_writer.writerow(row)
                    add_to_groups(aggregate, row)
            max_mixed_err = max(max_mixed_err, side["max_mixed_err"])
            max_rf_err = max(max_rf_err, side["max_rf_err"])
            max_beta_pred_err = max(max_beta_pred_err, side["max_beta_prediction_err"])
            candidate_beta_quantization_max = max(candidate_beta_quantization_max, side["candidate_beta_max_abs"])
            processed += 1
    if processed != 1536 + 96:
        raise RuntimeError(f"processed sidecar count mismatch: {processed}")
    group_csv = csv_text(group_rows(aggregate), GROUP_COLUMNS)
    scene_csv = scene_buffer.getvalue()
    inputs_after = verify_inputs_unchanged(inputs)
    input_signatures = []
    for path in sorted(inputs):
        before, after = inputs[path], inputs_after[path]
        input_signatures.append({"path": path, "sha256_before": before["sha256"],
                                 "sha256_after": after["sha256"], "bytes_before": before["bytes"],
                                 "bytes_after": after["bytes"], "mtime_ns_before": before["mtime_ns"],
                                 "mtime_ns_after": after["mtime_ns"]})
    script_sig = inputs[str(Path(__file__).resolve())]
    train_release, val_release = release_spec("TRAIN"), release_spec("VAL")
    prefix = f"train_{train_release['worker_sha'][:12]}_val_{val_release['worker_sha'][:12]}"
    scene_path = OUT / f"sidecar_contract_scene_metrics_mixed_{prefix}.csv"
    group_path = OUT / f"sidecar_contract_group_metrics_mixed_{prefix}.csv"
    meta_path = OUT / f"sidecar_contract_metadata_mixed_{prefix}.json"
    if any(p.exists() for p in (scene_path, group_path, meta_path)):
        raise RuntimeError("refusing to overwrite existing sidecar-contract outputs")
    metadata = {
        "status": "PASS_FULL_SIDECAR_CONTRACT_SUMMARY",
        "release_identities_by_split": {
            "TRAIN": {"output_dir": str(train_release["out"]),
                      "worker_script_sha256": train_release["worker_sha"],
                      "core_script_sha256": train_release["core_sha"],
                      "phase_state_sha256": train_release["state_sha"],
                      "runs_sha256": train_release["runs_sha"],
                      "metrics_sha256": train_release["metrics_sha"]},
            "VAL": {"output_dir": str(val_release["out"]),
                    "worker_script_sha256": val_release["worker_sha"],
                    "core_script_sha256": val_release["core_sha"],
                    "phase_state_sha256": val_release["state_sha"],
                    "runs_sha256": val_release["runs_sha"],
                    "metrics_sha256": val_release["metrics_sha"]}},
        "model_source_sha256": MODEL_SOURCE_SHA,
        "model_array_identity": MODEL_ARRAY_ID,
        "summarizer_script_sha256": script_sig["sha256"],
        "summarizer_script_bytes": script_sig["bytes"],
        "split_counts": {p["split"]: len(p["runs"]) for p in phases},
        "sidecars_processed": processed,
        "worker_metric_rows_independently_recomputed": 1536 * 16 + 96 * 16,
        "max_worker_metric_abs_delta": max_metric_delta,
        "max_mixed_identity_abs_error": max_mixed_err,
        "max_r_f_sign_abs_error": max_rf_err,
        "max_candidate_beta_prediction_abs_error": max_beta_pred_err,
        "max_candidate_beta_float32_quantization_abs": candidate_beta_quantization_max,
        "target_definition": "Y_raw and clip(Y_raw); mixed_raw=Y_raw+diag(1,1,0)r_f and clip(mixed_raw); all metric targets reclip float64 raw arrays",
        "window_definition": {"allvalid": "valid model rows, zero-based event index >=31",
                              "beta1_ge_1p8s": "valid event_time_s >=1.8 s; beta_candidate=1",
                              "late_ge_5s": "valid event_time_s >=5 s",
                              "early_lt_5s": "valid event_time_s <5 s",
                              "phase_code": "metrics grouped within each scene/code; no FFT"},
        "low_frequency_definition": "0-1 Hz inclusive, DC included; rFFT Parseval weights (DC/Nyquist 1, interior positive bins 2), denominator N^2, only contiguous uniform-time windows at 100 Hz; not computed after phase concatenation",
        "aggregate_weighting": "equal scene/run within split and group; worker-compatible signed ALL-axis bias is the mean across time and axes, while ALL-axis absbias is the mean of absolute per-axis time biases; worse_than_zero_scene_count compares each scene prior RMSE against its own zero RMSE",
        "interpretation_boundary": [
            "TRAIN and VAL use separately pinned worker/core releases; their source SHAs are recorded per output row and are not claimed to be identical.",
            "The two releases are joined only under the same fixed model, input/runtime identity, and Y/r_f/prediction equations verified by each sidecar.",
            "These supervised fit metrics do not establish closed-loop causal performance.",
            "Lower RMS of Y+Mrf reflects a different target and is not evidence that it is more appropriate.",
        ],
        "all_input_sha_stat_unchanged": True,
        "input_signatures": input_signatures,
        "outputs": {"scene_csv": str(scene_path), "scene_csv_bytes": len(scene_csv.encode("utf-8-sig")),
                    "group_csv": str(group_path), "group_csv_bytes": len(group_csv.encode("utf-8-sig")),
                    "metadata_json": str(meta_path)},
    }
    meta_text = json.dumps(metadata, indent=2, ensure_ascii=False) + "\n"
    total_bytes = len(scene_csv.encode("utf-8-sig")) + len(group_csv.encode("utf-8-sig")) + len(meta_text.encode("utf-8"))
    if total_bytes > MAX_OUTPUT_BYTES:
        raise RuntimeError(f"outputs exceed 160 MiB: {total_bytes} bytes")
    metadata["outputs"]["total_bytes_including_metadata"] = total_bytes
    meta_text = json.dumps(metadata, indent=2, ensure_ascii=False) + "\n"
    if len(scene_csv.encode("utf-8-sig")) + len(group_csv.encode("utf-8-sig")) + len(meta_text.encode("utf-8")) > MAX_OUTPUT_BYTES:
        raise RuntimeError("metadata pushed outputs over 160 MiB")
    with scene_path.open("xb") as f:
        f.write(b"\xef\xbb\xbf" + scene_csv.encode("utf-8"))
    with group_path.open("xb") as f:
        f.write(b"\xef\xbb\xbf" + group_csv.encode("utf-8"))
    with meta_path.open("x", encoding="utf-8") as f:
        f.write(meta_text)
    return {"status": metadata["status"], "sidecars_processed": processed,
            "scene_csv": str(scene_path), "group_csv": str(group_path), "metadata_json": str(meta_path),
            "total_output_bytes": metadata["outputs"]["total_bytes_including_metadata"]}


def main():
    parser = argparse.ArgumentParser(description="Read-only independent post-processing of PASS fixed-model sidecars.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--single-sidecar", action="store_true", help="validate one PASS TRAIN sidecar and print checks only")
    mode.add_argument("--full", action="store_true", help="summarize PASS TRAIN1536 and VAL96 sidecars")
    args = parser.parse_args()
    inputs: dict[str, dict] = {}
    script_path = tracked(Path(__file__), inputs)
    result = run_single(inputs) if args.single_sidecar else run_full(inputs)
    # The running script itself is an input too.
    final_script = signature(script_path)
    before_script = inputs[str(script_path)]
    if (final_script["sha256"], final_script["bytes"], final_script["mtime_ns"]) != (before_script["sha256"], before_script["bytes"], before_script["mtime_ns"]):
        raise RuntimeError("summarizer source SHA/stat changed during run")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
