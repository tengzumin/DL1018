"""Audit one explicitly named C7 VAL raw episode; never discovers or batches files."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import h5py
import numpy as np


ROOT = Path(__file__).resolve().parents[3]
TASKBOOK = ROOT / "reports/paper_continuation_20261023/C7_SPLIT_TARGET_EXECUTION_TASKBOOK_v1.json"
TASKBOOK_SHA256 = "2602443a2f2ddab710338387e238187c99d81cf3e6f65725eeabc3ea2a8bc4dc"
RUNTIME = ROOT / "experiments/position_split_target_c7_20261024/run_dl1018_closed_loop.m"
RUNTIME_SHA256 = "9b03b3c979a0402fdcd0f50ff389db9a4dcb72c50537bd4d9bc41bd77ac4c33d"
HELPER = ROOT / "experiments/position_split_target_c7_20261024/delayed_prediction_step_candidate.m"
HELPER_SHA256 = "48feebf934b8eb90b4424f2286aa857c48213d229714f30af99aacf53329549d"
WRAPPER = ROOT / "experiments/position_split_target_c7_20261024/run_episode_dl1018.m"
WRAPPER_SHA256 = "fcc1f5de659541e692483f8395d93fd2a251256286ebade5e510ed4c7a2e2330"
DT = 0.001
EVENT_H = 0.01
A_REQ_SIGMA_COEFF = 5.0
ATOL = 5e-10


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_matlab(dataset: h5py.Dataset) -> np.ndarray:
    """Match the fixed C5 decoder: transpose MATLAB 2-D fields; keep 1-D fields."""
    value = np.asarray(dataset)
    return value.T if value.ndim == 2 else value


def read_event_weights(dataset: h5py.Dataset) -> np.ndarray:
    """MATLAB 33x3xN arrays are stored N x 3 x 33 in v7.3 HDF5."""
    value = np.asarray(dataset)
    if value.ndim != 3:
        raise ValueError(f"expected 3-D event weights, got {value.shape}")
    return value.transpose(0, 2, 1)


def matlab_text(dataset: h5py.Dataset) -> str:
    value = np.asarray(dataset)
    if value.dtype.kind in "SU":
        flat = value.reshape(-1)
        parts = [item.decode("utf-8") if isinstance(item, bytes) else str(item) for item in flat]
        return "".join(parts).rstrip("\x00")
    if value.dtype.kind in "ui":
        return "".join(chr(int(code)) for code in value.reshape(-1) if int(code) != 0)
    if value.dtype.kind == "O":
        return "".join(str(item) for item in value.reshape(-1)).rstrip("\x00")
    raise ValueError(f"unsupported MATLAB text dtype {value.dtype}")


def vector(log: h5py.Group, name: str) -> np.ndarray:
    return read_matlab(log[name]).reshape(-1)


def scalar(log: h5py.Group, name: str) -> float:
    value = np.asarray(read_matlab(log[name])).reshape(-1)
    if value.size != 1:
        raise ValueError(f"{name}: expected scalar, got {value.shape}")
    return float(value[0])


def matrix(log: h5py.Group, name: str, columns: int) -> np.ndarray:
    value = np.asarray(read_matlab(log[name]))
    if value.ndim != 2 or value.shape[1] != columns:
        raise ValueError(f"{name}: expected (*,{columns}), got {value.shape}")
    return value


def maximum_residual(actual: np.ndarray, expected: np.ndarray, name: str) -> float:
    actual = np.asarray(actual, dtype=np.float64)
    expected = np.asarray(expected, dtype=np.float64)
    if actual.shape != expected.shape:
        raise ValueError(f"{name}: shape mismatch {actual.shape} != {expected.shape}")
    if not np.isfinite(actual).all() or not np.isfinite(expected).all():
        raise ValueError(f"{name}: non-finite value")
    residual = float(np.max(np.abs(actual - expected))) if actual.size else 0.0
    if residual > ATOL:
        raise AssertionError(f"{name}: max abs residual {residual:.6g} > {ATOL:g}")
    return residual


def audit_one(raw_path: Path, expected_scene_id: str, expected_collector: str) -> dict:
    taskbook_bytes = TASKBOOK.read_bytes()
    if hashlib.sha256(taskbook_bytes).hexdigest() != TASKBOOK_SHA256:
        raise ValueError("C7 taskbook hash changed")
    taskbook = json.loads(taskbook_bytes.decode("utf-8-sig"))
    if expected_scene_id not in taskbook["scene_ids"] or "_VAL_" not in expected_scene_id:
        raise ValueError("expected_scene_id must be one of the taskbook's fixed VAL scenes")

    raw_path = raw_path.resolve(strict=True)
    if expected_scene_id not in str(raw_path) or "TEST" in str(raw_path).upper():
        raise ValueError("raw path or parent directory must name this fixed VAL scene and must not be a TEST path")
    pinned = ((RUNTIME, RUNTIME_SHA256), (HELPER, HELPER_SHA256), (WRAPPER, WRAPPER_SHA256))
    source_hashes = {}
    for path, expected in pinned:
        actual = sha256(path)
        if actual != expected:
            raise ValueError(f"pinned C7 source changed: {path}")
        source_hashes[path.relative_to(ROOT).as_posix()] = actual

    before = raw_path.stat()
    raw_sha = sha256(raw_path)
    maxima: dict[str, float] = {}
    with h5py.File(raw_path, "r") as mat:
        if "log" not in mat:
            raise ValueError("raw file has no log group")
        log = mat["log"]
        scene_id = matlab_text(log["scene_id"])
        if scene_id != expected_scene_id:
            raise ValueError(f"embedded scene_id {scene_id!r} != requested {expected_scene_id!r}")
        collector = matlab_text(log["collector"])
        if not expected_collector or collector != expected_collector:
            raise ValueError(f"collector {collector!r} != explicitly pinned {expected_collector!r}")
        flags = {
            "stage1_position_pcf_coordination_enabled": scalar(log, "stage1_position_pcf_coordination_enabled"),
            "stage1_position_delayed_prediction_enabled": scalar(log, "stage1_position_delayed_prediction_enabled"),
            "stage1_position_search_head_enabled": scalar(log, "stage1_position_search_head_enabled"),
            "stage1_position_update_enabled": scalar(log, "stage1_position_update_enabled"),
        }
        if any(value != 1 for value in flags.values()):
            raise AssertionError(f"C7 runtime flags must all be enabled, got {flags}")
        head_type = matlab_text(log["stage1_position_search_head_type"])
        if head_type != "FEATURE":
            raise AssertionError(f"unexpected position search head {head_type!r}")

        ms = read_matlab(log["stage1_position_tracking_mask_Ms"]).reshape(-1)
        my = read_matlab(log["stage1_position_prediction_target_mask_My"]).reshape(-1)
        if not np.array_equal(ms, [1, 1, 0]) or not np.array_equal(my, [0, 0, 0]):
            raise AssertionError(f"unexpected C7 masks Ms={ms.tolist()}, My={my.tolist()}")

        context = float(np.asarray(read_matlab(log["stage1_position_model_context_length"])).reshape(-1)[0])
        readiness = float(np.asarray(read_matlab(log["stage1_position_readiness_events"])).reshape(-1)[0])
        if context != 32 or readiness != 32:
            raise AssertionError(f"unexpected model context/readiness {context}/{readiness}")
        w0 = np.asarray(read_matlab(log["stage1_position_search_initial_weight"]), dtype=np.float64)
        w_initial = np.asarray(read_matlab(log["stage1_position_weight_initial"]), dtype=np.float64)
        if w0.shape != (33, 3) or w_initial.shape != (33, 3):
            raise ValueError(f"unexpected frozen/initial W shapes {w0.shape}, {w_initial.shape}")
        w0_sha = hashlib.sha256(np.asarray(w0, dtype="<f8").tobytes(order="F")).hexdigest()
        if w0_sha != taskbook["fixed_model"]["W0_sha256"]:
            raise AssertionError(f"raw W0 hash {w0_sha} != taskbook pin {taskbook['fixed_model']['W0_sha256']}")
        maxima["initial_W_equals_search_W0"] = maximum_residual(w_initial, w0, "initial_W_equals_search_W0")
        feature_input = matrix(log, "stage1_position_feature_input", 14)

        state = matrix(log, "state", 12)
        rp = matrix(log, "reference/position", 3)
        rv = matrix(log, "reference/velocity", 3)
        ra = matrix(log, "reference/acceleration", 3)
        u = matrix(log, "position_compensation_applied_acceleration_mps2", 3)
        req = matrix(log, "stage1_position_pcf_a_req_mps2", 3)
        prediction_ref = matrix(log, "stage1_position_pcf_prediction_reference_mps2", 3)
        ntrans = min(state.shape[0] - 1, rp.shape[0] - 1, rv.shape[0] - 1,
                     ra.shape[0] - 1, u.shape[0], req.shape[0], prediction_ref.shape[0])
        if state.shape[0] != 20001 or ntrans != 20000:
            raise ValueError(f"expected a 20 s, 1 ms raw episode; state={state.shape}, transitions={ntrans}")

        e = rp[:ntrans] - state[:ntrans, :3]
        sigma = rv[:ntrans] + e - state[:ntrans, 3:6]
        req_expected = ra[:ntrans] + A_REQ_SIGMA_COEFF * sigma - u[:ntrans]
        maxima["physical_a_req_identity"] = maximum_residual(req[:ntrans], req_expected, "physical_a_req_identity")
        maxima["My000_prediction_reference_equals_a_req"] = maximum_residual(
            prediction_ref[:ntrans], req[:ntrans], "My000_prediction_reference_equals_a_req")

        valid = vector(log, "stage1_position_event_inference_valid").astype(bool)
        ids = np.flatnonzero(valid)
        expected_ids = np.arange(320, 19991, 10, dtype=np.int64)
        if not np.array_equal(ids, expected_ids):
            raise AssertionError(f"event indices differ: n={len(ids)}, first/last={ids[:1]}/{ids[-1:]}")
        logged_ids = vector(log, "stage1_position_event_step_index").astype(np.int64)
        if not np.array_equal(logged_ids, ids + 1):
            raise AssertionError("event_step_index must be MATLAB's one-based row index (zero-based event n plus one)")

        phi_all = matrix(log, "stage1_position_event_phi_33", 33)
        if phi_all.shape[0] != ntrans or feature_input.shape[0] != ntrans:
            raise ValueError(f"event feature logs must align to transitions: phi={phi_all.shape}, X14={feature_input.shape}")
        phi = phi_all[ids]
        if not np.isfinite(phi).all() or not np.isfinite(feature_input[ids]).all() or \
                np.max(np.abs(np.linalg.norm(phi, axis=1) - 1)) > 1e-10:
            raise AssertionError("event feature rows must be finite unit vectors")
        w_before = read_event_weights(log["stage1_position_event_weight_before_33x3"])
        w_after = read_event_weights(log["stage1_position_event_weight_after_33x3"])
        if w_before.shape != (len(ids), 33, 3) or w_after.shape != w_before.shape:
            raise ValueError(f"unexpected event W arrays {w_before.shape}, {w_after.shape}")
        maxima["first_event_W_before_equals_W0"] = maximum_residual(
            w_before[0], w0, "first_event_W_before_equals_W0")
        beta_all = vector(log, "stage1_position_event_beta")
        beta = beta_all[ids]
        beta_expected = np.minimum((ids + 1) * DT / 1.8, 1.0)
        maxima["event_beta_clock"] = maximum_residual(beta, beta_expected, "event_beta_clock")

        target_all = matrix(log, "stage1_position_delayed_prediction_target_mps2", 3)
        prev_all = vector(log, "stage1_position_delayed_prediction_prev_index_zero_based")
        if target_all.shape[0] != ntrans or prev_all.shape[0] != ntrans:
            raise ValueError("delayed target/index logs must align to the 20,000 plant transitions")
        target_logged = target_all[ids]
        prev_logged = prev_all[ids]
        if not np.isnan(target_logged[0]).all() or not np.isnan(prev_logged[0]):
            raise AssertionError("first ready event n=320 must have no completed interval target")
        if not np.isfinite(target_logged[1:]).all():
            raise AssertionError("all later ready events must have finite completed interval targets")
        target_expected = np.empty((len(ids) - 1, 3), dtype=np.float64)
        for row, n in enumerate(ids[1:]):
            j = int(n - 10)
            target_expected[row] = (state[n, 3:6] - state[j, 3:6]
                                    - DT * np.sum(req[j:n], axis=0)) / EVENT_H
        maxima["completed_interval_target_My000"] = maximum_residual(
            target_logged[1:], target_expected, "completed_interval_target_My000")
        maxima["old_interval_phi_index"] = maximum_residual(
            prev_logged[1:], ids[:-1].astype(np.float64), "old_interval_phi_index")

        # Cross-check logged cumulative reference integrals against the raw per-step My=000 reference.
        cum_ref = matrix(log, "stage1_position_delayed_prediction_reference_integral_before_step_mps", 3)
        event_cum_ref = matrix(log, "stage1_position_delayed_prediction_event_reference_integral_mps", 3)
        maxima["event_reference_integral_log"] = maximum_residual(
            event_cum_ref[ids], cum_ref[ids], "event_reference_integral_log")
        if cum_ref.shape[0] != ntrans or event_cum_ref.shape[0] != ntrans:
            raise ValueError("delayed integral logs must align to the 20,000 plant transitions")
        integral_from_start = np.vstack((np.zeros((1, 3)), np.cumsum(prediction_ref[:ntrans] * DT, axis=0)))
        maxima["reference_integral_reconstruction"] = maximum_residual(
            cum_ref, integral_from_start[:ntrans], "reference_integral_reconstruction")

        surface = matrix(log, "stage1_position_pcf_event_s_original_mps", 3)[ids]
        eta_before = matrix(log, "stage1_position_pcf_event_eta_before_mps", 3)[ids]
        sc = matrix(log, "stage1_position_pcf_event_s_coord_mps", 3)[ids]
        sc_eff = matrix(log, "stage1_position_pcf_event_s_coord_eff_mps", 3)[ids]
        sc_expected = surface - eta_before * ms
        maxima["tracking_surface_Ms110"] = maximum_residual(sc, sc_expected, "tracking_surface_Ms110")
        maxima["tracking_surface_clip"] = maximum_residual(
            sc_eff, np.clip(sc_expected, [-7, -8, -10], [7, 8, 10]), "tracking_surface_clip")

        raw_event = matrix(log, "stage1_position_event_raw_acceleration_mps2", 3)[ids]
        applied_event = matrix(log, "stage1_position_event_applied_acceleration_mps2", 3)[ids]
        raw_expected = np.einsum("nfi,nf->ni", w_before, phi)
        applied_expected = beta[:, None] * np.clip(raw_expected, -3, 3)
        maxima["output_uses_weight_before"] = maximum_residual(raw_event, raw_expected, "output_uses_weight_before")
        maxima["event_applied_output"] = maximum_residual(applied_event, applied_expected, "event_applied_output")

        # Recompute the exact MATLAB helper update, including delayed target, leak and one box projection.
        w_next_expected = np.empty_like(w_after)
        s_eff = sc_eff
        for row, n in enumerate(ids):
            grad = np.zeros((33, 3), dtype=np.float64)
            if row:
                old_phi = phi[row - 1]
                previous_raw = w_before[row].T @ old_phi
                residual = previous_raw - target_logged[row]
                grad = np.outer(old_phi, residual)
            candidate = (w_before[row] - EVENT_H * 12.0 * beta[row] * np.outer(phi[row], s_eff[row])
                         - EVENT_H * 0.002 * w_before[row] - EVENT_H * grad)
            w_next_expected[row] = np.clip(candidate, -60, 60)
        maxima["weight_before_sequence"] = maximum_residual(
            w_before[1:], w_after[:-1], "weight_before_sequence")
        maxima["helper_weight_next"] = maximum_residual(w_after, w_next_expected, "helper_weight_next")

        held_raw = matrix(log, "stage1_position_held_raw_acceleration_mps2", 3)
        held_applied = matrix(log, "stage1_position_held_applied_acceleration_mps2", 3)
        if held_raw.shape[0] < ntrans or held_applied.shape[0] < ntrans:
            raise ValueError("held-output logs do not cover every plant transition")
        expected_raw_hold = np.zeros((ntrans, 3), dtype=np.float64)
        expected_applied_hold = np.zeros_like(expected_raw_hold)
        for row, n in enumerate(ids):
            end = min(int(n) + 10, ntrans)
            expected_raw_hold[n:end] = raw_expected[row]
            expected_applied_hold[n:end] = applied_expected[row]
        maxima["held_raw_interval"] = maximum_residual(
            held_raw[:ntrans], expected_raw_hold, "held_raw_interval")
        maxima["held_applied_interval"] = maximum_residual(
            held_applied[:ntrans], expected_applied_hold, "held_applied_interval")
        maxima["physical_u_matches_held_output"] = maximum_residual(
            u[:ntrans], expected_applied_hold, "physical_u_matches_held_output")

        before, after = before, raw_path.stat()
        if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
            raise AssertionError("raw file changed while read")

    return {
        "status": "PASS_SINGLE_C7_VAL_RAW_EVENT_AND_PHYSICAL_IDENTITY_AUDIT",
        "scene_id": expected_scene_id,
        "collector": expected_collector,
        "raw_path": str(raw_path),
        "raw_sha256": raw_sha,
        "taskbook_sha256": TASKBOOK_SHA256,
        "c7_source_sha256": source_hashes,
        "fixed_masks": {"Ms": [1, 1, 0], "My": [0, 0, 0]},
        "runtime_flags": flags,
        "position_search_head_type": head_type,
        "logged_W0_f64le_fortran_sha256": w0_sha,
        "taskbook_W0_sha256": taskbook["fixed_model"]["W0_sha256"],
        "event_count": int(len(ids)),
        "event_indices_zero_based": [int(ids[0]), int(ids[-1])],
        "max_abs_residuals": maxima,
        "tolerance": ATOL,
        "model_identity_scope": "Checks pinned C7 runtime/helper/wrapper, raw W0 hash against the taskbook, initial/event W consistency, 14-D feature shape, and 32-event context/readiness. The frozen normalizer is not logged in raw and still requires a separate snapshot/model audit.",
        "reads_only_explicit_VAL_raw": True,
        "TEST_accessed": False,
        "Plant_started": False,
        "training_started": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", required=True, type=Path, help="one explicitly named C7 VAL .mat file")
    parser.add_argument("--expected-scene-id", required=True)
    parser.add_argument("--expected-collector", required=True,
                        help="exact method tag pinned by the C7 runner/lock")
    parser.add_argument("--out", type=Path, help="optional new JSON receipt; existing paths are refused")
    args = parser.parse_args()
    result = audit_one(args.raw, args.expected_scene_id, args.expected_collector)
    encoded = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.out:
        if args.out.exists():
            raise FileExistsError(args.out)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(encoded, encoding="utf-8")
    print(encoded, end="")


if __name__ == "__main__":
    main()
