"""Parent audit of C4 m=0 events, past-interval target, force chain and metrics."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
RUN = ROOT / "experiments/position_coordinate_c4_20261023"


def sha(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def verify(status_path):
    status = load(status_path)
    assert status["status"] == "RUN_COMPLETE_RAW_PENDING_AUDIT" and status["plant_calls"] == 1
    assert status["coordinate_factor_m"] == 0 and not status["TEST_accessed"]
    assert status["training_steps"] == status["optimizer_steps"] == 0
    for name in ("raw", "run_start", "first_plant_step_marker"):
        assert sha(status[name + "_path"]) == status[name + "_sha256"]
    lock_path = RUN / "C4_INPUT_LOCK_v3.json"
    lock = load(lock_path)
    assert sha(lock_path) == status["input_lock_sha256"]
    for ref in lock["active_source_inventory"]:
        assert sha(ref["path"]) == ref["sha256"]
    row = [r for r in lock["scenes"] if r["scene_id"] == status["scene_id"]]
    assert len(row) == 1
    row = row[0]
    scorer_path = ROOT / "reports/delayed_prediction_c3_dev72_parent_20261023/parent_raw_metrics.py"
    scorer = load_module(scorer_path, "parent_existing_metric_scorer")
    candidate = dict(scene_id=status["scene_id"], method="C4_M0", path=status["raw_path"], sha256=status["raw_sha256"])
    c3_item = dict(scene_id=status["scene_id"], method="C3", path=row["C3_reuse"]["raw_path"], sha256=row["C3_reuse"]["raw_sha256"])
    c4_metrics, c3_metrics = scorer.score(candidate), scorer.score(c3_item)
    assert c4_metrics["external_identity_sha256"] == c3_metrics["external_identity_sha256"]
    if status["scene_id"] == "DL1018_VAL_T2_C00_W10":
        b_status_path = ROOT / "experiments/b_traceable_c3core_20261023/runs_b/DL1018_VAL_T2_C00_W10/B_TRACEABLE_C3CORE_V1/attempt_01/run_status.json"
        b_status = load(b_status_path)
        assert b_status["raw_sha256"] == "5a1fffedd408c070a77e3083643a33d9b422a55330ffecc1b6d1ab61b5d48957"
        b_item = dict(scene_id=status["scene_id"], method="B_TRACEABLE", path=b_status["raw_path"], sha256=b_status["raw_sha256"])
        b_identity_status = "NEW_TRACEABLE_B_ONE_SCENE"
    else:
        b_item = dict(scene_id=status["scene_id"], method="B_HISTORICAL", path=row["B_source"]["path"], sha256=row["B_source"]["sha256"])
        b_identity_status = "HISTORICAL_B_RUNTIME_TREE_UNCLOSED"
    b_metrics = scorer.score(b_item)
    assert c4_metrics["external_identity_sha256"] == b_metrics["external_identity_sha256"]
    with h5py.File(candidate["path"], "r") as file:
        g = file["log"]

        def read(key):
            value = np.asarray(g[key])
            return value.T if value.ndim == 2 else value

        ids = np.flatnonzero(read("stage1_position_event_inference_valid").ravel())
        assert np.array_equal(ids, np.arange(320, 19991, 10))
        for key in ("stage1_position_delayed_prediction_enabled", "stage1_position_replacement_enabled",
                    "stage1_position_pcf_coordination_enabled", "stage1_position_update_enabled"):
            assert read(key).item() == 1, key
        assert read("stage1_position_coordinate_m").item() == 0
        assert read("stage1_position_search_gamma").item() == 12
        assert read("stage1_position_search_kappa").item() == 1
        initial = read("stage1_position_search_initial_weight")
        assert np.array_equal(initial, read("stage1_position_weight_initial"))
        assert hashlib.sha256(np.asarray(initial, dtype="<f8").tobytes(order="F")).hexdigest() == lock["candidate_identity"]["W0_sha256"]
        phi = read("stage1_position_event_phi_33")[ids]
        wb = np.asarray(g["stage1_position_event_weight_before_33x3"]).transpose(0, 2, 1)
        wa = np.asarray(g["stage1_position_event_weight_after_33x3"]).transpose(0, 2, 1)
        assert wb.shape == wa.shape == (len(ids), 33, 3)
        assert np.array_equal(wb[0], initial)
        state = read("state")
        req = read("stage1_position_pcf_a_req_mps2")
        af = read("stage1_position_pcf_a_f_mps2")
        rf = read("stage1_position_pcf_r_f_mps2")
        eta = read("stage1_position_pcf_eta_before_mps")
        target = read("stage1_position_delayed_prediction_target_mps2")[ids]
        previous = read("stage1_position_delayed_prediction_prev_index_zero_based").ravel()[ids]
        assert np.isnan(previous[0]) and np.isnan(target[0]).all()
        assert np.array_equal(previous[1:], ids[:-1])
        # Disjoint block sums do not reuse the runtime cumulative-integral implementation.
        y = np.array([((state[k, 3:6] - state[j, 3:6]) - .001 * req[j:k].sum(axis=0)) / .01
                      for j, k in zip(ids[:-1], ids[1:])])
        beta = np.minimum((ids + 1) * .001 / 1.8, 1)
        raw = np.einsum("nfi,nf->ni", wb, phi)
        gradient = np.zeros_like(wb)
        gradient[1:] = phi[:-1, :, None] * (np.einsum("nfi,nf->ni", wb[1:], phi[:-1]) - y)[:, None, :]
        surface = (read("reference/velocity")[:-1] - state[:-1, 3:6]
                   + read("reference/position")[:-1] - state[:-1, :3])[ids]
        effective = np.clip(surface, -np.array([7, 8, 10]), np.array([7, 8, 10]))
        expected = np.clip(wb - .12 * beta[:, None, None] * phi[:, :, None] * effective[:, None, :]
                           - .00002 * wb - .01 * gradient, -60, 60)
        held = np.zeros((20000, 3))
        applied = beta[:, None] * np.clip(raw, -3, 3)
        for index, k in enumerate(ids):
            held[k:min(k + 10, 20000)] = applied[index]
        reference_integral = np.vstack((np.zeros((1, 3)), np.cumsum(.001 * req, axis=0)))[:-1]
        af_integral = np.vstack((np.zeros((1, 3)), np.cumsum(.001 * af, axis=0)))[:-1]

        def diff(a, b):
            assert np.isfinite(a).all() and np.isfinite(b).all()
            return float(np.max(np.abs(a - b)))

        checks = {
            "phi_unit_norm": diff(np.linalg.norm(phi, axis=1), np.ones(len(ids))),
            "past_aReq_target": diff(target[1:], y),
            "surface_original_from_actual_state": diff(read("stage1_position_pcf_event_s_original_mps")[ids], surface),
            "surface_m0": diff(read("stage1_position_pcf_event_s_coord_mps")[ids], surface),
            "surface_clip_m0": diff(read("stage1_position_pcf_event_s_coord_eff_mps")[ids], effective),
            "eta_event_before": diff(read("stage1_position_pcf_event_eta_before_mps")[ids], eta[ids]),
            "output_before_update": diff(read("stage1_position_event_raw_acceleration_mps2")[ids], raw),
            "applied_beta_clip": diff(read("stage1_position_event_applied_acceleration_mps2")[ids], applied),
            "beta_clock": diff(read("stage1_position_event_beta").ravel()[ids], beta),
            "event_period": diff(read("stage1_position_event_dt_s").ravel()[ids], np.full(len(ids), .01)),
            "joint_update_once": diff(wa, expected),
            "weight_continuity": diff(wb[1:], wa[:-1]),
            "prediction_term_norm": diff(read("stage1_position_delayed_prediction_term_norm").ravel()[ids], .01 * np.linalg.norm(gradient, axis=(1, 2))),
            "separate_actual_af_integral": diff(read("stage1_position_delayed_prediction_af_integral_before_step_mps"), af_integral),
            "m0_reference_integral": diff(read("stage1_position_delayed_prediction_reference_integral_before_step_mps"), reference_integral),
            "event_reference_integral": diff(read("stage1_position_delayed_prediction_event_reference_integral_mps")[ids], reference_integral[ids]),
            "event_velocity": diff(read("stage1_position_delayed_prediction_event_velocity_mps")[ids], state[ids, 3:6]),
            "held_compensation": diff(read("position_compensation_applied_acceleration_mps2"), held),
            "request_contains_applied_compensation": diff(req, read("position_nominal_acceleration_mps2") - held),
            "rf_definition": diff(rf, req - af),
        }
        assert max(checks.values()) < 1e-10, checks
    return {"status": "PASS_C4_RAW_ALL_EVENTS", "scene_id": status["scene_id"],
            "event_count": len(ids), "checks": checks, "C4_metrics": c4_metrics,
            "C3_metrics": c3_metrics, "B_metrics": b_metrics, "B_identity_status": b_identity_status,
            "Q_C4_minus_B_m": c4_metrics["Q_0_20_m"] - b_metrics["Q_0_20_m"],
            "Q_C4_minus_C3_m": c4_metrics["Q_0_20_m"] - c3_metrics["Q_0_20_m"],
            "Z_C4_minus_C3_m": c4_metrics["rmse_z_0_20_m"] - c3_metrics["rmse_z_0_20_m"],
            "raw_sha256": candidate["sha256"], "run_status_sha256": sha(status_path),
            "input_lock_sha256": sha(lock_path), "script_sha256": sha(Path(__file__)),
            "metric_scorer_sha256": sha(scorer_path), "timing_qualification": "NONISOLATED_NOT_FORMAL",
            "new_Plant_in_audit": 0, "TEST_accessed": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("status", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    assert not args.output.exists(), "Preserve previous evidence"
    result = verify(args.status)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: result[k] for k in ("status", "scene_id", "event_count", "Q_C4_minus_C3_m", "Z_C4_minus_C3_m")}))
