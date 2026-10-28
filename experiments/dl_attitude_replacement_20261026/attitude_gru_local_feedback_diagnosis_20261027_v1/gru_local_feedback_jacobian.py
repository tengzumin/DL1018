from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
from collections import defaultdict
from pathlib import Path

import h5py
import numpy as np
from scipy.io import loadmat


ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent
SCENES = (
    "DL1018_VAL_T1_C08_W15", "DL1018_VAL_T2_C05_W15", "DL1018_VAL_T3_C02_W15",
    "DL1018_VAL_T1_C05_W12", "DL1018_VAL_T2_C02_W12", "DL1018_VAL_T3_C00_W13",
)
AXES = ("roll", "pitch", "yaw")
EPS = (1e-5, 5e-6)
POINTS_PER_SCENE = 200
OLD_DIAG = BASE / "attitude_local_feedback_diagnosis_20261027_v1"
RBF_DIAG = BASE / "attitude_rbf_local_reference_20261027_v1"
COS_STUDY = BASE / "gru_stream_cosine_dev_v1"
NCMD_STUDY = BASE / "gru_stream_ncmd_dev_v1"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def readj(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def import_file(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def assert_artifact(prov: dict, name: str, path: Path) -> str:
    expected = prov["artifacts"][name]["sha256"].lower()
    actual = sha(path).lower()
    if actual != expected:
        raise ValueError(f"locked artifact SHA mismatch: {path}")
    return actual


def load_fixed_constants(bs: dict) -> tuple[dict, dict]:
    old_prov = readj(OLD_DIAG / "PROVENANCE_v1.json")
    lock_path = Path(old_prov["locked_cfg_path"])
    if sha(lock_path).lower() != old_prov["locked_cfg_sha256"].lower():
        raise ValueError("fixed LOCKED_CFG SHA mismatch")
    lock = readj(lock_path)
    snapshot = Path(lock["cfg_snapshot_path"])
    if sha(snapshot).lower() != lock["cfg_snapshot_sha256"].lower():
        raise ValueError("fixed prepared CFG snapshot SHA mismatch")
    with h5py.File(snapshot, "r") as f:
        k1 = np.asarray(bs.matlab_array(f["cfg/control/bs/attitude/k1"]), dtype=np.float64).reshape(-1)
        k2 = np.asarray(bs.matlab_array(f["cfg/control/bs/attitude/k2"]), dtype=np.float64).reshape(-1)
    J0 = np.asarray(lock["J0_kgm2"], dtype=np.float64)
    Jfixed = np.asarray(lock["Pfixed_inertia_kgm2"], dtype=np.float64)
    Jdot0 = np.asarray(lock["Pfixed_inertia_dot_for_bs_kgm2_s"], dtype=np.float64)
    dmax = np.asarray(lock["dmax"], dtype=np.float64).reshape(-1)
    if not np.array_equal(J0, Jfixed) or np.any(Jdot0 != 0):
        raise ValueError("fixed J0/Jdot0 identity check failed")
    if not np.array_equal(k1, np.asarray(old_prov["fixed_constants"]["K1"])):
        raise ValueError("snapshot K1 differs from reviewed fixed constant")
    if not np.array_equal(k2, np.asarray(old_prov["fixed_constants"]["K2"])):
        raise ValueError("snapshot K2 differs from reviewed fixed constant")
    return {"K1": k1, "K2": k2, "J0": J0, "Jdot0": Jdot0, "dmax": dmax}, {
        "old_mlp_diagnosis_script": str(OLD_DIAG / "local_feedback_sensitivity.py"),
        "old_mlp_diagnosis_script_sha256": sha(OLD_DIAG / "local_feedback_sensitivity.py"),
        "fixed_locked_cfg_path": str(lock_path), "fixed_locked_cfg_sha256": sha(lock_path),
        "fixed_cfg_snapshot_path": str(snapshot), "fixed_cfg_snapshot_sha256": sha(snapshot),
    }


def load_gru(study: Path, candidate_label: str) -> dict:
    release_path = study / "RELEASE.json"
    release = readj(release_path)
    model_path = Path(release["model_path"])
    model_sha = sha(model_path)
    if model_sha.lower() != release["model_sha256"].lower():
        raise ValueError(f"{candidate_label}: frozen model SHA mismatch")
    py_ref_path = study / "audits" / "trained_model_parity_reference.py"
    if sha(py_ref_path).lower() != release["trained_python_reference_sha256"].lower():
        raise ValueError(f"{candidate_label}: trained Python reference SHA mismatch")
    parity_path = study / "audits" / "TRAINED_MODEL_PYTHON_PARITY_v1.json"
    if sha(parity_path).lower() != release["trained_python_report_sha256"].lower():
        raise ValueError(f"{candidate_label}: trained-model parity report SHA mismatch")
    parity = readj(parity_path)
    if parity["status"] != "PASS_TRAINED_GRU_PYTHON_STREAM_PARITY" or parity["model_sha256"].lower() != model_sha.lower():
        raise ValueError(f"{candidate_label}: frozen-model Python parity is not PASS")
    py = import_file(py_ref_path, f"forward_{candidate_label}")
    model = py.model_from_mat(loadmat(model_path, squeeze_me=True))
    if model["gru_weight_ih"].shape != (96, 13) or model["gru_weight_hh"].shape != (96, 32):
        raise ValueError(f"{candidate_label}: unexpected GRU shape")
    if model["head_weight"].shape != (3, 32):
        raise ValueError(f"{candidate_label}: unexpected head shape")
    if np.any(model["input_std"] <= 0) or np.any(model["target_rms"] <= 0):
        raise ValueError(f"{candidate_label}: invalid normalization")
    return {
        "label": candidate_label, "release_path": str(release_path), "release_sha256": sha(release_path),
        "model_path": str(model_path), "model_sha256": model_sha,
        "python_reference_path": str(py_ref_path), "python_reference_sha256": sha(py_ref_path),
        "parity_report_path": str(parity_path), "parity_report_sha256": sha(parity_path),
        "parity_status": parity["status"], "model": model, "forward_module": py,
    }


def damping(J: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    D = -0.5 * (J + J.T)
    return D, np.linalg.eigvalsh(D)


def net_torque(event: dict, omega: np.ndarray, model_info: dict, constants: dict,
               bs: dict, feature_mode: str = "full") -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    tau_bs, _ = bs.bs_nominal(event["eta"], omega, event["ref"], event["ref_rate"], event["ref_accel"],
                              constants["K1"], constants["K2"], constants["J0"], constants["Jdot0"])
    if feature_mode == "freeze_tau_input":
        omega_input, tau_input = omega, event["tau_bs"]
    elif feature_mode == "freeze_omega_input":
        omega_input, tau_input = event["omega"], tau_bs
    elif feature_mode == "full":
        omega_input, tau_input = omega, tau_bs
    else:
        raise ValueError(feature_mode)
    feature = np.r_[event["error"], omega_input, tau_input, event["arm"]]
    if feature.shape != (13,) or not np.all(np.isfinite(feature)):
        raise ValueError("invalid reconstructed deployed 13-feature input")
    model = model_info["model"]
    normalized = (feature - model["input_mean"]) / model["input_std"]
    hidden_before = event["hidden_before"][model_info["label"]].copy()
    y, hidden_after = model_info["forward_module"].forward_one(normalized, hidden_before.copy(), model)
    y = np.asarray(y, dtype=np.float64).reshape(3)
    hidden_after = np.asarray(hidden_after, dtype=np.float64).reshape(32)
    clipped = np.minimum(np.maximum(y, -constants["dmax"]), constants["dmax"])
    net = tau_bs - constants["J0"] @ (event["beta"] * clipped)
    return net, tau_bs, y, hidden_after


def jacobian(event: dict, model_info: dict, constants: dict, bs: dict,
             feature_mode: str = "full") -> tuple[dict, dict, float]:
    matrices = {}
    for eps in EPS:
        Jbs = np.zeros((3, 3), dtype=np.float64)
        Jnet = np.zeros((3, 3), dtype=np.float64)
        max_hdelta = 0.0
        h_before_copy = event["hidden_before"][model_info["label"]].copy()
        center_hidden = event["hidden_after"][model_info["label"]]
        for col in range(3):
            delta = np.zeros(3)
            delta[col] = eps
            plus_net, plus_bs, _, plus_h = net_torque(event, event["omega"] + delta, model_info, constants, bs, feature_mode)
            minus_net, minus_bs, _, minus_h = net_torque(event, event["omega"] - delta, model_info, constants, bs, feature_mode)
            Jbs[:, col] = (plus_bs - minus_bs) / (2 * eps)
            Jnet[:, col] = (plus_net - minus_net) / (2 * eps)
            max_hdelta = max(max_hdelta, float(np.max(np.abs(plus_h - center_hidden))),
                             float(np.max(np.abs(minus_h - center_hidden))))
        if not np.array_equal(event["hidden_before"][model_info["label"]], h_before_copy):
            raise AssertionError("perturbed evaluation mutated frozen hidden_before")
        matrices[eps] = {"bs": Jbs, "net": Jnet, "hidden_after_max_delta": max_hdelta}
    first, second = matrices[EPS[0]], matrices[EPS[1]]
    errors = {mode: float(np.max(np.abs(first[mode] - second[mode]))) for mode in ("bs", "net")}
    return first, errors, float(np.max(np.abs(first["bs"] - bs.bs_analytic_jacobian(
        event["eta"], event["omega"], constants["K1"], constants["K2"], constants["J0"], constants["Jdot0"]))))


def load_rbf_reference(bs: dict) -> tuple[dict, dict, dict, dict]:
    prov_path = RBF_DIAG / "PROVENANCE_v1.json"
    prov = readj(prov_path)
    c5_lock = Path(prov["source_locks"]["C5_input_lock_path"])
    v3_lock = Path(prov["source_locks"]["V3_source_lock_path"])
    if sha(c5_lock).lower() != prov["source_locks"]["C5_input_lock_sha256"].lower():
        raise ValueError("C5 input lock SHA mismatch")
    if sha(v3_lock).lower() != prov["source_locks"]["V3_source_lock_sha256"].lower():
        raise ValueError("v3 source lock SHA mismatch")
    validation_path = RBF_DIAG / "SOURCE_LOCK_VALIDATION_v1.json"
    if sha(validation_path).lower() != prov["source_locks"]["validation_artifact_sha256"].lower():
        raise ValueError("RBF source-lock validation SHA mismatch")
    replay_path = RBF_DIAG / "local_feedback_rbf_replay_all_v1.json"
    jac_path = RBF_DIAG / "local_feedback_rbf_local_jacobians_all_v1.csv"
    result_path = RBF_DIAG / "local_feedback_rbf_local_jacobian_result_all_v1.json"
    assert_artifact(prov, replay_path.name, replay_path)
    assert_artifact(prov, jac_path.name, jac_path)
    assert_artifact(prov, result_path.name, result_path)
    replay = readj(replay_path)
    result = readj(result_path)
    if replay["status"] != "PASS_RBF_FULL_EVENT_REPLAY" or result["status"] != "PASS_OFFLINE_LOCAL_JACOBIANS":
        raise ValueError("C5 RBF replay/Jacobian cache is not PASS")
    cache = {}
    with jac_path.open("r", newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            key = (row["scene_id"], int(row["sample_index"]))
            if key in cache:
                raise ValueError(f"duplicate RBF cache point: {key}")
            cache[key] = row
    if len(cache) != 1200:
        raise ValueError(f"expected 1200 RBF cache points, got {len(cache)}")
    replay_scenes = {row["scene_id"]: row for row in replay["scene_reports"]}
    if set(replay_scenes) != set(SCENES):
        raise ValueError("C5 RBF replay scene set mismatch")
    return prov, replay_scenes, cache, {
        "rbf_provenance_path": str(prov_path), "rbf_provenance_sha256": sha(prov_path),
        "c5_input_lock_path": str(c5_lock), "c5_input_lock_sha256": sha(c5_lock),
        "v3_source_lock_path": str(v3_lock), "v3_source_lock_sha256": sha(v3_lock),
        "rbf_replay_report_path": str(replay_path), "rbf_replay_report_sha256": sha(replay_path),
        "rbf_jacobian_cache_path": str(jac_path), "rbf_jacobian_cache_sha256": sha(jac_path),
        "rbf_jacobian_result_path": str(result_path), "rbf_jacobian_result_sha256": sha(result_path),
    }


def build_scene(scene_id: str, replay_scene: dict, cache: dict, models: dict,
                constants: dict, bs: dict) -> tuple[list[dict], dict]:
    raw_path = Path(replay_scene["raw_path"])
    run_start = Path(replay_scene["run_start_path"])
    if sha(raw_path).lower() != replay_scene["raw_sha256"].lower():
        raise ValueError(f"C5 raw SHA mismatch: {scene_id}")
    if sha(run_start).lower() != replay_scene["run_start_sha256"].lower():
        raise ValueError(f"C5 run_start SHA mismatch: {scene_id}")
    with h5py.File(run_start, "r") as f:
        bsg = f["runStart/cfg/control/bs/attitude"]
        rbf = f["runStart/cfg/rbf/attitude"]
        k1 = np.asarray(bs.matlab_array(bsg["k1"]), dtype=np.float64).reshape(-1)
        k2 = np.asarray(bs.matlab_array(bsg["k2"]), dtype=np.float64).reshape(-1)
        beta_rise = bs.scalar(rbf, "beta_rise_time")
        run_dmax = np.asarray(bs.matlab_array(rbf["dmax"]), dtype=np.float64).reshape(-1)
    if not np.array_equal(k1, constants["K1"]) or not np.array_equal(k2, constants["K2"]):
        raise ValueError(f"C5 run_start K1/K2 differs from fixed snapshot: {scene_id}")
    if not np.array_equal(run_dmax, constants["dmax"]):
        raise ValueError(f"C5 run_start dmax differs from fixed deployment value: {scene_id}")

    with h5py.File(raw_path, "r") as f:
        log = f["log"]
        state = np.asarray(bs.matlab_array(log["state"]), dtype=np.float64)
        time = bs.vec(log, "time")
        ref = np.asarray(bs.matlab_array(log["filtered_attitude_reference"]), dtype=np.float64)
        ref_rate = np.asarray(bs.matlab_array(log["filtered_attitude_rate"]), dtype=np.float64)
        ref_accel = np.asarray(bs.matlab_array(log["command_filter_acceleration_applied_rads2"]), dtype=np.float64)
        nominal_log = np.asarray(bs.matlab_array(log["attitude_bs_nominal_torque_Nm"]), dtype=np.float64)
        arms = np.asarray(bs.matlab_array(log["arms"]["command"]), dtype=np.float64)
        event_flags = np.asarray(bs.matlab_array(log["rbf_update_flag"]), dtype=bool).reshape(-1)
        beta_log = bs.vec(log, "attitude_event_beta")
    if state.shape != (20001, 12):
        raise ValueError(f"unexpected C5 state shape: {scene_id} {state.shape}")
    if ref.shape != (20000, 3) or ref_rate.shape != (20000, 3) or ref_accel.shape != (20000, 3):
        raise ValueError(f"unexpected C5 reference derivative shape: {scene_id}")
    if arms.shape != (20001, 4) or nominal_log.shape != (20000, 3) or event_flags.shape != (20000,):
        raise ValueError(f"unexpected C5 controller log shape: {scene_id}")
    dt = float(time[1] - time[0])
    if abs(dt - 0.001) > 1e-12 or np.max(np.abs(np.diff(time) - dt)) > 1e-10:
        raise ValueError(f"C5 timeline is not uniform 1 ms: {scene_id}")
    event_indices = np.flatnonzero(event_flags)
    if len(event_indices) != 1999 or replay_scene["event_count"] != 1999:
        raise ValueError(f"expected 1999 C5 events: {scene_id}")
    sample_indices = event_indices + 1  # MATLAB one-based sample index.
    if sample_indices[0] != 11 or sample_indices[-1] != 19991 or np.any(np.diff(sample_indices) != 10):
        raise ValueError(f"C5 event index/order mismatch: {scene_id}")
    event_times = time[event_indices]
    sample_time_error = float(np.max(np.abs(event_times - (sample_indices - 1) * dt)))
    if sample_time_error > 1e-10:
        raise ValueError(f"one-based sample index does not match C5 time: {scene_id}")
    beta = np.minimum(sample_indices * dt / beta_rise, 1.0)
    if beta_log.size == 20000:
        event_beta_log = beta_log[event_indices]
        finite = np.isfinite(event_beta_log)
        beta_err = float(np.max(np.abs(event_beta_log[finite] - beta[finite]))) if np.any(finite) else 0.0
        if beta_err > 1e-12:
            raise ValueError(f"logged C5 beta differs from sample-time formula: {scene_id}")
    else:
        beta_err = float("nan")
    mature_positions = np.flatnonzero(beta >= 1.0 - 1e-12)
    if len(mature_positions) != 1780 or replay_scene["mature_event_count"] != len(mature_positions):
        raise ValueError(f"C5 mature-event count mismatch: {scene_id}")
    selected_positions = np.rint(np.linspace(0, len(mature_positions) - 1, POINTS_PER_SCENE)).astype(int)
    if len(np.unique(selected_positions)) != POINTS_PER_SCENE:
        raise ValueError(f"duplicate uniform mature sample: {scene_id}")
    selected_events = set(mature_positions[selected_positions].tolist())

    hidden = {name: np.zeros(32, dtype=np.float64) for name in models}
    selected = []
    max_tau_error = 0.0
    tau_worst = None
    for ordinal, raw_i in enumerate(event_indices):
        sample = int(raw_i) + 1
        eta = state[raw_i, 6:9].copy()
        omega = state[raw_i, 9:12].copy()
        e = bs.wrap(ref[raw_i] - eta)
        tau_bs, _ = bs.bs_nominal(eta, omega, ref[raw_i], ref_rate[raw_i], ref_accel[raw_i],
                                  constants["K1"], constants["K2"], constants["J0"], constants["Jdot0"])
        err = float(np.max(np.abs(tau_bs - nominal_log[raw_i])))
        if err > max_tau_error:
            max_tau_error, tau_worst = err, sample
        feature = np.r_[e, omega, tau_bs, arms[raw_i]]
        if feature.shape != (13,) or not np.all(np.isfinite(feature)):
            raise ValueError(f"invalid deployed 13-feature at {scene_id}/{sample}")
        context = None
        if ordinal in selected_events:
            rbf_row = cache.get((scene_id, sample))
            if rbf_row is None:
                raise ValueError(f"missing same-point C5 RBF cache row {scene_id}/{sample}")
            if int(rbf_row["event_ordinal"]) != ordinal + 1 or abs(float(rbf_row["time_s"]) - time[raw_i]) > 1e-10:
                raise ValueError(f"RBF cache event/time join mismatch {scene_id}/{sample}")
            context = {
                "scene_id": scene_id, "sample_index": sample, "event_ordinal": ordinal + 1,
                "selection_rank": int(np.where(mature_positions[selected_positions] == ordinal)[0][0]),
                "time_s": float(time[raw_i]), "time_band": "first5" if time[raw_i] < 5 else ("last5" if time[raw_i] >= 15 else "middle"),
                "family": "W15" if scene_id.endswith("W15") else "HF", "beta": float(beta[ordinal]),
                "eta": eta, "omega": omega, "error": e, "ref": ref[raw_i].copy(),
                "ref_rate": ref_rate[raw_i].copy(), "ref_accel": ref_accel[raw_i].copy(),
                "arm": arms[raw_i].copy(), "tau_bs": tau_bs.copy(), "hidden_before": {},
                "hidden_after": {}, "center_raw": {}, "rbf_cache": rbf_row,
            }
        for name, info in models.items():
            model = info["model"]
            h_before = hidden[name].copy()
            x_norm = (feature - model["input_mean"]) / model["input_std"]
            y, h_after = info["forward_module"].forward_one(x_norm, h_before.copy(), model)
            y = np.asarray(y, dtype=np.float64).reshape(3)
            h_after = np.asarray(h_after, dtype=np.float64).reshape(32)
            if not np.all(np.isfinite(y)) or not np.all(np.isfinite(h_after)):
                raise ValueError(f"nonfinite GRU replay value: {name} {scene_id}/{sample}")
            if context is not None:
                context["hidden_before"][name] = h_before
                context["hidden_after"][name] = h_after.copy()
                context["center_raw"][name] = y.copy()
            hidden[name] = h_after.copy()
        if context is not None:
            selected.append(context)
    if max_tau_error > 1e-10:
        raise ValueError(f"BS nominal torque parity exceeds 1e-10: {scene_id} max={max_tau_error}")
    if len(selected) != POINTS_PER_SCENE:
        raise ValueError(f"expected 200 selected points: {scene_id}")
    return selected, {
        "scene_id": scene_id, "c5_raw_path": str(raw_path), "c5_raw_sha256": sha(raw_path),
        "run_start_path": str(run_start), "run_start_sha256": sha(run_start),
        "event_count": int(len(event_indices)), "matlab_first_sample_index": int(sample_indices[0]),
        "matlab_last_sample_index": int(sample_indices[-1]), "time_first_s": float(event_times[0]),
        "time_last_s": float(event_times[-1]), "mature_event_count": int(len(mature_positions)),
        "selected_point_count": len(selected), "uniform_selection_positions": selected_positions.tolist(),
        "max_sample_time_error_s": sample_time_error,
        "max_bs_nominal_torque_parity_Nm": max_tau_error, "worst_sample_index": tau_worst,
        "max_logged_beta_error": beta_err,
    }


def cache_matrix(row: dict, name: str) -> np.ndarray:
    return np.array([[float(row[f"J_{name}_{i}{j}"]) for j in range(3)] for i in range(3)], dtype=np.float64)


def summarise(rows: list[dict]) -> list[dict]:
    out = []
    for family in ("W15", "HF"):
        for band in ("first5", "middle", "last5"):
            group = [r for r in rows if r["family"] == family and r["time_band"] == band]
            if not group:
                continue
            for model_name in ("cosine_GRU", "ncmd_GRU"):
                item = {"family": family, "time_band": band, "model": model_name, "selected_events": len(group)}
                for mode in ("bs", "rbf", model_name):
                    vals = [r[f"lambda_min_{mode}"] for r in group]
                    item[f"lambda_min_{mode}_min"] = float(np.min(vals))
                    item[f"lambda_min_{mode}_median"] = float(np.median(vals))
                    item[f"lambda_min_{mode}_p05"] = float(np.quantile(vals, .05))
                    item[f"lambda_min_{mode}_p95"] = float(np.quantile(vals, .95))
                    item[f"lambda_min_{mode}_negative_percent"] = float(100*np.mean(np.asarray(vals) < 0))
                ratio = [r[f"increment_fro_over_bs_{model_name}"] for r in group]
                item["increment_fro_over_bs_median"] = float(np.median(ratio))
                item["increment_fro_over_bs_p95"] = float(np.quantile(ratio, .95))
                item["fd_epsilon_absdiff_max_p95"] = float(np.quantile([r[f"fd_epsilon_absdiff_max_{model_name}"] for r in group], .95))
                for axis in AXES:
                    for mode in ("bs", "rbf", model_name):
                        item[f"SymNeg_{mode}_{axis}_diagonal_median"] = float(np.median([r[f"SymNeg_{mode}_{axis}"] for r in group]))
                out.append(item)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene", choices=SCENES)
    parser.add_argument("--precheck", action="store_true", help="run one scene only and write a parity precheck")
    args = parser.parse_args()
    bs = import_file(OLD_DIAG / "local_feedback_sensitivity.py", "reviewed_bs_helpers")
    constants, fixed_source = load_fixed_constants(bs)
    cos = load_gru(COS_STUDY, "cosine_GRU")
    ncmd = load_gru(NCMD_STUDY, "ncmd_GRU")
    models = {"cosine_GRU": cos, "ncmd_GRU": ncmd}
    cos_forward = COS_STUDY / "candidate_runner_work/matlab/runtime/gru_stream_attitude_forward_v1.m"
    ncmd_forward = NCMD_STUDY / "candidate_runner_work/matlab/runtime/gru_stream_attitude_forward_v1.m"
    cos_step = COS_STUDY / "candidate_runner_work/matlab/runtime/gru_stream_attitude_step_v1.m"
    ncmd_step = NCMD_STUDY / "candidate_runner_work/matlab/runtime/gru_stream_attitude_step_v1.m"
    if sha(cos_forward) != sha(ncmd_forward) or sha(cos_step) != sha(ncmd_step):
        raise ValueError("cosine and NCMD deployed GRU forward/step sources differ")
    rbf_prov, replay_scenes, cache, rbf_source = load_rbf_reference(bs)
    if args.precheck:
        if args.scene is None:
            raise ValueError("--precheck requires --scene")
        scenes = [args.scene]
    else:
        scenes = [args.scene] if args.scene else list(SCENES)

    all_rows, scene_reports = [], []
    bs_cache_max = 0.0
    analytic_bs_max = 0.0
    eps_max = {"bs": 0.0, "cosine_GRU": 0.0, "ncmd_GRU": 0.0}
    center_raw_max = {"cosine_GRU": 0.0, "ncmd_GRU": 0.0}
    conditional = []
    for scene in scenes:
        print(f"C5 replay/GRU hidden: {scene}", flush=True)
        contexts, report = build_scene(scene, replay_scenes[scene], cache, models, constants, bs)
        scene_reports.append(report)
        for event in contexts:
            Jbs_fd: dict[float, np.ndarray] = {}
            Jnet_fd = {name: {} for name in models}
            hidden_delta = {name: 0.0 for name in models}
            nominal_tau = event["tau_bs"]
            cache_row = event["rbf_cache"]
            Jrbf = cache_matrix(cache_row, "rbf")
            Jbs_cached = cache_matrix(cache_row, "bs")
            for eps in EPS:
                Jbs = np.zeros((3, 3), dtype=np.float64)
                for name in models:
                    Jnet_fd[name][eps] = np.zeros((3, 3), dtype=np.float64)
                for col in range(3):
                    delta = np.zeros(3)
                    delta[col] = eps
                    tau_plus, _ = bs.bs_nominal(event["eta"], event["omega"]+delta, event["ref"], event["ref_rate"], event["ref_accel"], constants["K1"], constants["K2"], constants["J0"], constants["Jdot0"])
                    tau_minus, _ = bs.bs_nominal(event["eta"], event["omega"]-delta, event["ref"], event["ref_rate"], event["ref_accel"], constants["K1"], constants["K2"], constants["J0"], constants["Jdot0"])
                    Jbs[:, col] = (tau_plus - tau_minus) / (2*eps)
                    for name, info in models.items():
                        net_plus, _, _, hidden_plus = net_torque(event, event["omega"]+delta, info, constants, bs)
                        net_minus, _, _, hidden_minus = net_torque(event, event["omega"]-delta, info, constants, bs)
                        Jnet_fd[name][eps][:, col] = (net_plus - net_minus) / (2*eps)
                        hidden_delta[name] = max(hidden_delta[name], float(np.max(np.abs(hidden_plus-event["hidden_after"][name]))), float(np.max(np.abs(hidden_minus-event["hidden_after"][name]))))
                Jbs_fd[eps] = Jbs
            bs_cache_err = float(np.max(np.abs(Jbs_fd[EPS[0]] - Jbs_cached)))
            bs_cache_max = max(bs_cache_max, bs_cache_err)
            if bs_cache_err > 1e-8:
                raise ValueError(f"RBF cache BS Jacobian mismatch {scene}/{event['sample_index']}: {bs_cache_err}")
            Dbs, ebs = damping(Jbs_fd[EPS[0]])
            Drbf, erbf = damping(Jrbf)
            row = {k: event[k] for k in ("scene_id", "family", "sample_index", "event_ordinal", "selection_rank", "time_s", "time_band", "beta")}
            row["bs_nominal_torque_parity_Nm"] = report["max_bs_nominal_torque_parity_Nm"]
            row["rbf_cache_bs_jacobian_max_abs_diff"] = bs_cache_err
            row["lambda_min_bs"] = float(ebs[0])
            row["lambda_min_rbf"] = float(erbf[0])
            row["fd_epsilon_absdiff_max_bs"] = float(np.max(np.abs(Jbs_fd[EPS[0]]-Jbs_fd[EPS[1]])))
            row["fd_epsilon_absdiff_max_rbf"] = float(cache_row["fd_eps_absdiff_max_rbf"])
            for i, axis in enumerate(AXES):
                row[f"SymNeg_bs_{axis}"] = float(Dbs[i, i])
                row[f"SymNeg_rbf_{axis}"] = float(Drbf[i, i])
                for j in range(3):
                    row[f"J_bs_{i}{j}"] = float(Jbs_fd[EPS[0]][i, j])
                    row[f"J_rbf_{i}{j}"] = float(Jrbf[i, j])
            for name, info in models.items():
                y0, h0 = info["forward_module"].forward_one(
                    (np.r_[event["error"], event["omega"], nominal_tau, event["arm"]]-info["model"]["input_mean"])/info["model"]["input_std"],
                    event["hidden_before"][name].copy(), info["model"])
                center_raw_err = float(np.max(np.abs(np.asarray(y0).reshape(3)-event["center_raw"][name])))
                center_h_err = float(np.max(np.abs(np.asarray(h0).reshape(32)-event["hidden_after"][name])))
                center_raw_max[name] = max(center_raw_max[name], center_raw_err, center_h_err)
                if center_raw_err > 1e-10 or center_h_err > 1e-10:
                    raise ValueError(f"center stream replay mismatch {name}/{scene}/{event['sample_index']}")
                j1, j2 = Jnet_fd[name][EPS[0]], Jnet_fd[name][EPS[1]]
                Dnet, enet = damping(j1)
                eps_error = float(np.max(np.abs(j1-j2)))
                analytic_err = float(np.max(np.abs(Jbs_fd[EPS[0]]-bs.bs_analytic_jacobian(
                    event["eta"], event["omega"], constants["K1"], constants["K2"], constants["J0"], constants["Jdot0"]))))
                analytic_bs_max = max(analytic_bs_max, analytic_err)
                eps_max["bs"] = max(eps_max["bs"], float(row["fd_epsilon_absdiff_max_bs"]))
                eps_max[name] = max(eps_max[name], eps_error)
                row[f"lambda_min_{name}"] = float(enet[0])
                row[f"increment_fro_over_bs_{name}"] = float(np.linalg.norm(j1-Jbs_fd[EPS[0]], ord="fro")/np.linalg.norm(Jbs_fd[EPS[0]], ord="fro"))
                row[f"fd_epsilon_absdiff_max_{name}"] = eps_error
                row[f"analytic_bs_vs_fd_max_{name}"] = analytic_err
                row[f"hidden_after_perturbation_max_delta_{name}"] = hidden_delta[name]
                row[f"center_raw_output_max_abs_{name}"] = center_raw_err
                row[f"center_hidden_after_max_abs_{name}"] = center_h_err
                row[f"output_clipped_at_center_{name}"] = bool(np.any(np.abs(event["center_raw"][name]) >= constants["dmax"]-1e-12))
                for i, axis in enumerate(AXES):
                    row[f"SymNeg_{name}_{axis}"] = float(Dnet[i, i])
                    for j in range(3):
                        row[f"J_{name}_{i}{j}"] = float(j1[i, j])
                if enet[0] < 0:
                    conditional.append((event, info, float(enet[0])))
            all_rows.append(row)
    if len(all_rows) != len(scenes)*POINTS_PER_SCENE:
        raise ValueError("selected Jacobian point count mismatch")
    if not args.precheck and len(all_rows) != 1200:
        raise ValueError("full run must contain exactly 1200 fixed C5 points")

    result = {
        "schema": "DL1018_COSINE_NCMD_GRU_LOCAL_FEEDBACK_JACOBIAN_V1",
        "status": "PASS_ONE_SCENE_GRU_LOCAL_JACOBIAN_PRECHECK" if args.precheck else "PASS_FULL_1200_POINT_GRU_LOCAL_JACOBIAN",
        "candidate_models": {name: {k: v for k, v in info.items() if k not in ("model", "forward_module")} for name, info in models.items()},
        "scene_reports": scene_reports, "selected_source_points": len(all_rows),
        "model_jacobian_count": len(all_rows)*2, "epsilon_rad_s": list(EPS),
        "fixed_constants": {k: v.tolist() for k, v in constants.items()},
        "parity": {
            "sample_index_is_matlab_one_based": True,
            "event_time_from_sample_index_max_error_s": max(r["max_sample_time_error_s"] for r in scene_reports),
            "max_BS_nominal_torque_vs_C5_raw_Nm": max(r["max_bs_nominal_torque_parity_Nm"] for r in scene_reports),
            "max_RBF_cache_BS_Jacobian_abs_diff": bs_cache_max,
            "max_analytic_BS_vs_FD_abs_diff": analytic_bs_max,
            "max_hidden_before_stream_center_replay_abs_diff": max(center_raw_max.values()),
            "max_logged_C5_beta_error": max((r["max_logged_beta_error"] for r in scene_reports if np.isfinite(r["max_logged_beta_error"])), default=0.0),
            "epsilon_J_max_absdiff": eps_max,
        },
        "rbf_cache_join_count": len(all_rows),
        "conditional_decomposition_requested_for_negative_full_path": len(conditional),
        "plant_calls": 0, "training_jobs": 0, "TEST_read": False,
        "variable_inertia_read_or_reconstructed": False,
        "interpretation_limit": "Frozen C5 record and pre-event hidden state; one-event local derivative only, not a closed-loop counterfactual or stability certificate.",
    }
    source_hashes = {
        **fixed_source, **rbf_source,
        "old_bs_helper_module_sha256": sha(OLD_DIAG / "local_feedback_sensitivity.py"),
        "cosine_gru_forward_matlab_sha256": sha(cos_forward), "ncmd_gru_forward_matlab_sha256": sha(ncmd_forward),
        "cosine_gru_step_matlab_sha256": sha(cos_step), "ncmd_gru_step_matlab_sha256": sha(ncmd_step),
    }
    result["source_sha256"] = source_hashes

    prefix = "PRECHECK_" + scenes[0] if args.precheck else "FULL"
    out_csv = ROOT / (f"{prefix}_GRU_LOCAL_JACOBIANS_v1.csv" if args.precheck else "GRU_LOCAL_JACOBIANS_v1.csv")
    out_result = ROOT / (f"{prefix}_RESULT_v1.json" if args.precheck else "RESULT_v1.json")
    out_csv_rows = all_rows
    with out_csv.open("x", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(out_csv_rows[0]))
        writer.writeheader()
        writer.writerows(out_csv_rows)
    result["point_csv_path"] = str(out_csv)
    result["point_csv_sha256"] = sha(out_csv)
    out_result.write_text(json.dumps(result, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    print("CORE_RESULT="+json.dumps({
        "status": result["status"], "selected_points": len(all_rows),
        "max_bs_nominal_parity_Nm": result["parity"]["max_BS_nominal_torque_vs_C5_raw_Nm"],
        "max_rbf_cache_bs_jacobian_diff": bs_cache_max,
        "max_analytic_bs_fd_diff": analytic_bs_max, "epsilon_jacobian_max_absdiff": eps_max,
        "negative_lambda_points": len(conditional), "csv": str(out_csv), "result": str(out_result)},
        ensure_ascii=False), flush=True)

    # Only negative full-path candidate points receive the two path decomposition diagnostics.
    if conditional and not args.precheck:
        decomp_rows = []
        for event, info, full_lambda in conditional:
            mats = {}
            for mode in ("freeze_tau_input", "freeze_omega_input"):
                eps_mats = {}
                for eps in EPS:
                    J = np.zeros((3, 3), dtype=np.float64)
                    for col in range(3):
                        delta = np.zeros(3); delta[col] = eps
                        net_p = net_torque(event, event["omega"]+delta, info, constants, bs, mode)[0]
                        net_m = net_torque(event, event["omega"]-delta, info, constants, bs, mode)[0]
                        J[:, col] = (net_p-net_m)/(2*eps)
                    eps_mats[eps] = J
                _, eigs = damping(eps_mats[EPS[0]])
                mats[mode] = {"lambda_min": float(eigs[0]),
                              "epsilon_max_abs_diff": float(np.max(np.abs(eps_mats[EPS[0]]-eps_mats[EPS[1]])))}
            decomp_rows.append({"scene_id": event["scene_id"], "model": info["label"],
                                "sample_index": event["sample_index"], "time_s": event["time_s"],
                                "full_path_lambda_min": full_lambda,
                                "omega_feature_only_lambda_min": mats["freeze_tau_input"]["lambda_min"],
                                "nominal_torque_feature_only_lambda_min": mats["freeze_omega_input"]["lambda_min"],
                                "omega_feature_only_epsilon_diff": mats["freeze_tau_input"]["epsilon_max_abs_diff"],
                                "nominal_torque_feature_only_epsilon_diff": mats["freeze_omega_input"]["epsilon_max_abs_diff"]})
        decomp_path = ROOT / "NEGATIVE_POINT_PATH_DECOMPOSITION_v1.csv"
        with decomp_path.open("x", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=list(decomp_rows[0]))
            writer.writeheader(); writer.writerows(decomp_rows)
        result["conditional_decomposition_path"] = str(decomp_path)
        result["conditional_decomposition_sha256"] = sha(decomp_path)
        result["conditional_decomposition_points"] = len(decomp_rows)
        out_result.write_text(json.dumps(result, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")

    if not args.precheck:
        summary = summarise(all_rows)
        summary_path = ROOT / "SUMMARY_v1.json"
        summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
        result["summary_path"] = str(summary_path)
        result["summary_sha256"] = sha(summary_path)
        out_result.write_text(json.dumps(result, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
        report_lines = [
            "# Cosine / NCMD GRU 局部反馈 Jacobian",
            "",
            "固定六场 C5 raw 的记录状态、时间、参考、arms 和每个冻结 GRU 的 pre-event hidden；只扰动当前 omega。每次扰动都重新计算 BS nominal torque 并同时更新该特征，再以同一 hidden_before 做单步前向。净力矩为 tauBS(omega) - J0 beta clip(q)。",
            "",
            f"点数：{len(all_rows)} 个 C5状态点 × 两个模型 = {len(all_rows)*2} 个candidate Jacobian。BS torque/C5 raw最大差 {result['parity']['max_BS_nominal_torque_vs_C5_raw_Nm']:.3e} N m；RBF cache BS-J最大差 {bs_cache_max:.3e}；解析BS与FD最大差 {analytic_bs_max:.3e}。",
            "",
            f"负最小特征值点：{len(conditional)} 个（候选模型×状态点）。条件路径分解仅在这些点计算；见 NEGATIVE_POINT_PATH_DECOMPOSITION_v1.csv。",
            "",
            "解释边界：这是C5历史上的冻结记忆单事件局部敏感度，不是GRU闭环航次反事实或稳定性证明；只读固定J0/K1/K2/Jdot0，无变量惯量读取/重建。Plant=0、训练=0、TEST=未读。",
            "",
            "逐点矩阵/阻尼值见 GRU_LOCAL_JACOBIANS_v1.csv，分组分位数见 SUMMARY_v1.json。",
            "",
        ]
        report_path = ROOT / "REPORT_v1.md"
        report_path.write_text("\n".join(report_lines), encoding="utf-8")
        result["report_path"] = str(report_path)
        result["report_sha256"] = sha(report_path)
        out_result.write_text(json.dumps(result, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
