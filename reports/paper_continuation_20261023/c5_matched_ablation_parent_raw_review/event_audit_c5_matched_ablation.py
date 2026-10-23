"""Independent 1,968-event checks for the two frozen C5 first-flight ablations."""
from __future__ import annotations

import hashlib

import h5py
import numpy as np


VARIANTS = {"C5_FREEZE_TRAINED_W0", "C5_NO_DELAYED_PREDICTION"}


def audit_events(raw_path, cfg, variant, expected_w0, expected_w0_sha256):
    assert variant in VARIANTS
    with h5py.File(raw_path, "r") as file:
        g = file["log"]

        def read(key):
            a = np.asarray(g[key])
            return a.T if a.ndim == 2 else a

        ids = np.flatnonzero(read("stage1_position_event_inference_valid").ravel())
        assert np.array_equal(ids, np.arange(320, 19991, 10)) and len(ids) == 1968
        for key in ("stage1_position_delayed_prediction_enabled", "stage1_position_replacement_enabled",
                    "stage1_position_pcf_coordination_enabled", "stage1_position_update_enabled"):
            assert read(key).item() == 1, key
        assert np.array_equal(read("stage1_position_coordinate_mask").ravel(), [1, 1, 0])
        assert read("stage1_position_search_gamma").item() == 12
        assert read("stage1_position_search_kappa").item() == 1

        initial = read("stage1_position_search_initial_weight")
        assert np.array_equal(initial, read("stage1_position_weight_initial"))
        assert np.array_equal(initial, np.asarray(expected_w0, dtype=float))
        assert hashlib.sha256(np.asarray(initial, dtype="<f8").tobytes(order="F")).hexdigest() == expected_w0_sha256.lower()
        phi = read("stage1_position_event_phi_33")[ids]
        wb = np.asarray(g["stage1_position_event_weight_before_33x3"]).transpose(0, 2, 1)
        wa = np.asarray(g["stage1_position_event_weight_after_33x3"]).transpose(0, 2, 1)
        assert wb.shape == wa.shape == (len(ids), 33, 3) and np.array_equal(wb[0], initial)

        state = read("state")
        req = read("stage1_position_pcf_a_req_mps2")
        af = read("stage1_position_pcf_a_f_mps2")
        rf = read("stage1_position_pcf_r_f_mps2")
        eta = read("stage1_position_pcf_eta_before_mps")
        ref_v = read("reference/velocity")
        ref_p = read("reference/position")
        physical_channels = {key: read(key) for key in (
            "requested_generalized", "controller_clipped_generalized",
            "allocated_generalized", "realized_generalized")}
        tilt_limited = read("tilt_limited").ravel()
        roll, pitch, yaw = read("filtered_attitude_reference").T
        thrust_axis = np.column_stack((
            np.cos(yaw)*np.sin(pitch)*np.cos(roll) + np.sin(yaw)*np.sin(roll),
            np.sin(yaw)*np.sin(pitch)*np.cos(roll) - np.cos(yaw)*np.sin(roll),
            np.cos(pitch)*np.cos(roll)))
        mass, gravity = float(np.asarray(cfg["plant"]["mass"]).item()), float(np.asarray(cfg["plant"]["g"]).item())
        nameplate_af = read("requested_generalized")[:, 0, None] / mass * thrust_axis - np.array([0, 0, gravity])

        target = read("stage1_position_delayed_prediction_target_mps2")[ids]
        previous = read("stage1_position_delayed_prediction_prev_index_zero_based").ravel()[ids]
        assert np.isnan(previous[0]) and np.isnan(target[0]).all()
        assert np.array_equal(previous[1:], ids[:-1])
        # y_k uses the logged reference integral over [j,k); phi_{k-1} is the old feature.
        mixed_reference = af.copy()
        mixed_reference[:, 2] = req[:, 2]
        y = np.array([((state[k, 3:6] - state[j, 3:6]) - .001 * mixed_reference[j:k].sum(axis=0)) / .01
                      for j, k in zip(ids[:-1], ids[1:])])
        old_phi = phi[:-1]
        old_residual = np.einsum("nfi,nf->ni", wb[1:], old_phi) - y
        disabled_old_phi_gradient = old_phi[:, :, None] * old_residual[:, None, :]
        beta = np.minimum((ids + 1) * .001 / 1.8, 1)
        raw = np.einsum("nfi,nf->ni", wb, phi)
        s = (ref_v[:-1] - state[:-1, 3:6] + ref_p[:-1] - state[:-1, :3])[ids]
        s_m110 = s - eta[ids] * np.array([1, 1, 0])
        s_eff = np.clip(s_m110, -np.array([7, 8, 10]), np.array([7, 8, 10]))
        applied = beta[:, None] * np.clip(raw, -3, 3)

        if variant == "C5_FREEZE_TRAINED_W0":
            expected = np.broadcast_to(initial, wb.shape).copy()
            preprojection = wb
        else:
            preprojection = wb - .12 * beta[:, None, None] * phi[:, :, None] * s_eff[:, None, :] - .00002 * wb
            expected = np.clip(preprojection, -60, 60)
        weight_update_error = float(np.max(np.abs(wa - expected)))
        if variant == "C5_FREEZE_TRAINED_W0":
            assert np.array_equal(wa, expected), "frozen weights differ from W0"
        else:
            assert weight_update_error < 1e-10, "no-prediction update differs from its specified equation"
        expected_projection = np.any(expected != preprojection, axis=(1, 2))
        actual_projection = read("stage1_position_event_projection").ravel()[ids].astype(bool)

        held = np.zeros((20000, 3))
        for q, k in enumerate(ids):
            held[k:min(k + 10, 20000)] = applied[q]
        reference_integral = np.vstack((np.zeros((1, 3)), np.cumsum(.001 * mixed_reference, axis=0)))[:-1]
        af_integral = np.vstack((np.zeros((1, 3)), np.cumsum(.001 * af, axis=0)))[:-1]

        def diff(a, b):
            a, b = np.asarray(a), np.asarray(b)
            assert np.isfinite(a).all() and np.isfinite(b).all()
            return float(np.max(np.abs(a - b)))

        checks = {
            "finite_full_state_and_reference": float(not (state.shape == (20001, 12) and np.isfinite(state).all()
                                                              and ref_v.shape == ref_p.shape == (20001, 3)
                                                              and np.isfinite(ref_v).all() and np.isfinite(ref_p).all()
                                                              and np.isfinite(req).all() and np.isfinite(af).all()
                                                              and np.isfinite(rf).all() and np.isfinite(eta).all())),
            **{f"finite_{key}": float(not (value.ndim == 2 and value.shape[0] == 20000
                                            and value.shape[1] > 0 and np.isfinite(value).all()))
               for key, value in physical_channels.items()},
            "finite_tilt_limited": float(not (tilt_limited.shape == (20000,) and np.isfinite(tilt_limited).all())),
            "phi_unit_norm": diff(np.linalg.norm(phi, axis=1), np.ones(len(ids))),
            "past_mixed_reference_target_[prev,current)": diff(target[1:], y),
            "surface_original_from_state": diff(read("stage1_position_pcf_event_s_original_mps")[ids], s),
            "surface_M110": diff(read("stage1_position_pcf_event_s_coord_mps")[ids], s_m110),
            "surface_clip_M110": diff(read("stage1_position_pcf_event_s_coord_eff_mps")[ids], s_eff),
            "eta_event_before": diff(read("stage1_position_pcf_event_eta_before_mps")[ids], eta[ids]),
            "output_before_weight_update": diff(read("stage1_position_event_raw_acceleration_mps2")[ids], raw),
            "applied_beta_output_clip": diff(read("stage1_position_event_applied_acceleration_mps2")[ids], applied),
            "beta_event_clock": diff(read("stage1_position_event_beta").ravel()[ids], beta),
            "event_period_10ms": diff(read("stage1_position_event_dt_s").ravel()[ids], np.full(len(ids), .01)),
            "actual_weight_update_or_freeze": diff(wa, expected),
            "actual_projection_flag": diff(actual_projection.astype(float), expected_projection.astype(float)),
            "weight_before_after_continuity": diff(wb[1:], wa[:-1]),
            "actual_prediction_term_norm_zero": diff(read("stage1_position_delayed_prediction_term_norm").ravel()[ids], np.zeros(len(ids))),
            "old_phi_target_history_finite": float(not (np.isfinite(old_phi).all() and np.isfinite(y).all()
                                                          and np.isfinite(disabled_old_phi_gradient).all())),
            "separate_actual_af_integral": diff(read("stage1_position_delayed_prediction_af_integral_before_step_mps"), af_integral),
            "M110_reference_integral": diff(read("stage1_position_delayed_prediction_reference_integral_before_step_mps"), reference_integral),
            "event_reference_integral": diff(read("stage1_position_delayed_prediction_event_reference_integral_mps")[ids], reference_integral[ids]),
            "event_velocity": diff(read("stage1_position_delayed_prediction_event_velocity_mps")[ids], state[ids, 3:6]),
            "held_compensation": diff(read("position_compensation_applied_acceleration_mps2"), held),
            "request_minus_held_equals_nominal": diff(req, read("position_nominal_acceleration_mps2") - held),
            "rf_equals_request_minus_af": diff(rf, req - af),
            "filtered_thrust_axis_af": diff(af, nameplate_af),
            "direct_mixed_prediction_reference": diff(read("stage1_position_pcf_prediction_reference_mps2"), mixed_reference),
            "eta_initial_zero": diff(eta[0], np.zeros(3)),
            "eta_event_continuity": diff(eta[1:], read("stage1_position_pcf_eta_after_mps")[:-1]),
            "eta_exact_held_step": diff(read("stage1_position_pcf_eta_after_mps"),
                                         np.exp(-.004) * eta + (-np.expm1(-.004) / 4) * rf),
        }
        assert max(checks.values()) < 1e-10, checks
        prediction_norm = read("stage1_position_delayed_prediction_term_norm").ravel()[ids]
        assert np.array_equal(prediction_norm, np.zeros(len(ids))), "actual prediction term norm must be exactly zero"
        if variant == "C5_FREEZE_TRAINED_W0":
            assert np.array_equal(wb, expected) and np.array_equal(wa, expected)
        return {"event_count": int(len(ids)), "checks": checks,
                "W0_sha256": expected_w0_sha256,
                "old_phi_target_pair_count": int(len(y)),
                "disabled_old_phi_gradient_max_abs": float(np.max(np.abs(disabled_old_phi_gradient))),
                "tilt_limited_fraction": float(np.mean(tilt_limited != 0)),
                "weight_update_mode": variant, "actual_prediction_norm_max": 0.0,
                "log_status": "STABLE"}
