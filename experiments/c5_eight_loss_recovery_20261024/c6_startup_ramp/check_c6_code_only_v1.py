"""C6 algebra/boundary checks and three already-reviewed DEV forced-state hosts."""
import csv
import hashlib
import importlib.util
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
OUT = ROOT / "reports/paper_continuation_20261023/c5_eight_loss_recovery/c6_startup_ramp"
PRIOR = ROOT / "reports/paper_continuation_20261023/c5_eight_loss_recovery/same_state_v2/SAME_STATE_REPLAY_REVIEW_v1.json"

def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def error(a, b):
    a, b = np.asarray(a), np.asarray(b)
    assert a.shape == b.shape and np.isfinite(a).all() and np.isfinite(b).all()
    return float(np.max(np.abs(a-b)))

def rejects(fn):
    try:
        fn()
    except (ValueError, TypeError):
        return True
    raise AssertionError("Invalid input accepted")

def native(path):
    return "\\\\?\\" + str(path.resolve()) if os.name == "nt" else str(path)

c5_path = ROOT / "reports/delayed_prediction_proposal_20261023/construction/delayed_prediction_kernel.py"
c5 = module(c5_path, "frozen_C5")
c6 = module(HERE / "delayed_prediction_kernel.py", "isolated_C6")
binding = json.loads((OUT / "C6_SOURCE_BINDING_v1.json").read_text(encoding="utf-8"))
assert binding["taskbook_sha256"] == "092014be47bffa186f690d8e8e73ba64ea9e83d083df070b530b2c5c59c009dd"
for item in binding["sources"]:
    source, target = Path(item["source"]), Path(item["target"])
    assert sha(source) == item["source_sha256"] and sha(target) == item["target_sha256"]
    text = source.read_text(encoding="utf-8-sig")
    change = item["single_functional_change"]
    assert target.read_text(encoding="utf-8-sig") == text.replace(change["before"], change["after"])
assert c6.self_check()["status"] == "PASS_SYNTHETIC_SINGLE_STEP_ONLY"
rng = np.random.default_rng(2026102406)
W = rng.normal(0, .2, (33, 3))
phi = rng.normal(size=33); phi /= np.linalg.norm(phi)
old_phi = rng.normal(size=33); old_phi /= np.linalg.norm(old_phi)
surface, target = np.array([.2, -.1, .3]), np.array([.4, -.3, .2])
original = W.copy()
first5 = c5.delayed_prediction_step(W, phi, surface, 320, .32)
first6 = c6.delayed_prediction_step(W, phi, surface, 320, .32)
assert all(np.array_equal(first5[k], first6[k]) for k in ("raw", "applied", "preprojection_candidate", "W_next"))
assert np.array_equal(W, original)
checks = {"first_ready_no_history_identical": True, "input_weight_unchanged": True,
          "legacy_shape_clock_gradient_and_projection_self_check": True}
pre_diff_max = 0.0
for n in (330, 900, 1790, 1800, 1900):
    prior = dict(phi_prev=old_phi, y_prev=target, previous_index=n-10, previous_time_s=(n-10)*.001)
    a = c5.delayed_prediction_step(W, phi, surface, n, n*.001, **prior)
    b = c6.delayed_prediction_step(W, phi, surface, n, n*.001, **prior)
    assert np.array_equal(a["raw"], b["raw"]) and np.array_equal(a["applied"], b["applied"])
    expected = c6.RHO * (1-a["beta"]) * a["prediction_gradient"]
    pre_diff_max = max(pre_diff_max, error(b["preprojection_candidate"]-a["preprojection_candidate"], expected))
    if a["beta"] == 1:
        assert np.array_equal(a["W_next"], b["W_next"])
checks.update(output_before_update_identical=True, beta_one_same_input_identical=True,
              exact_preprojection_difference_max_abs=pre_diff_max)

# Joint projection: both signs hit the box; a second case detects premature clipping.
wb = np.zeros((33, 3)); wb[0, :2] = [59.9, -59.9]
unit = np.zeros(33); unit[0] = 1
def boundary(y):
    return c6.delayed_prediction_step(wb, unit, [-7, 7, 0], 900, .9,
        phi_prev=unit, y_prev=y, previous_index=890, previous_time_s=.89)
clip = boundary([100, -100, 0])
assert clip["preprojection_candidate"][0, 0] > 60 and clip["preprojection_candidate"][0, 1] < -60
assert np.array_equal(clip["W_next"][0, :2], [60, -60])
joint = boundary([-20, 20, 0])
beta = joint["beta"]
base = wb - .12*beta*np.outer(unit, [-7, 7, 0]) - .00002*wb
premature = np.clip(np.clip(base, -60, 60) - .01*beta*joint["prediction_gradient"], -60, 60)
assert error(joint["W_next"], np.clip(joint["preprojection_candidate"], -60, 60)) == 0
assert error(joint["W_next"], premature) > .1
checks.update(joint_box_both_signs=True, detects_premature_sequential_projection=True)
bad_w = W.copy(); bad_w[0, 0] = np.nan
bad_phi = phi.copy(); bad_phi[0] = np.nan
bad_y = target.copy(); bad_y[1] = np.nan
invalid = [
    lambda: c6.delayed_prediction_step(bad_w, phi, surface, 320, .32),
    lambda: c6.delayed_prediction_step(W, bad_phi, surface, 320, .32),
    lambda: c6.delayed_prediction_step(W, phi*2, surface, 320, .32),
    lambda: c6.delayed_prediction_step(W, phi, [np.nan, 0, 0], 320, .32),
    lambda: c6.delayed_prediction_step(W, phi, surface, 330, .33),
    lambda: c6.delayed_prediction_step(W, phi, surface, 320, np.nan),
    lambda: c6.delayed_prediction_step(W, phi, surface, 330, .33, phi_prev=old_phi,
        y_prev=bad_y, previous_index=320, previous_time_s=.32),
    lambda: c6.delayed_prediction_step(W, phi, surface, 330, .33, phi_prev=old_phi,
        y_prev=target, previous_index=310, previous_time_s=.31),
]
assert all(rejects(fn) for fn in invalid)
checks["invalid_inputs_rejected"] = len(invalid)
assert pre_diff_max < 2e-12

prior_review = json.loads(PRIOR.read_text(encoding="utf-8"))
assert prior_review["status"] == "PASS_THREE_DEV_HOST_SOURCE_PARITY_AND_FORCED_STATE_REPLAY"
assert [(a["scene_id"], a["host"]) for a in prior_review["raw_access"]] == [
    ("DL1018_DEV_T2_C09_W10", "C5"), ("DL1018_DEV_T2_C09_W10", "NO_PRED"),
    ("DL1018_DEV_T1_C01_W15", "C5")]
signal_rows, host_reviews = [], []
for item in prior_review["raw_access"]:
    path = Path(item["path"])
    assert "test" not in str(path).lower() and "_DEV_" in item["scene_id"]
    before = path.stat()
    assert before.st_size == item["bytes"]
    with h5py.File(native(path), "r") as file:
        g = file["log"]
        ids = np.flatnonzero(np.asarray(g["stage1_position_event_inference_valid"]).ravel())
        assert np.array_equal(ids, np.arange(320, 19991, 10))
        def events(key):
            node = g[key]
            assert node.ndim == 2 and node.shape[1] == 20000
            return np.asarray(node[:, ids]).T
        ph = events("stage1_position_event_phi_33")
        se = events("stage1_position_pcf_event_s_coord_eff_mps")
        y = events("stage1_position_delayed_prediction_target_mps2")
        source_raw = events("stage1_position_event_raw_acceleration_mps2")
        W0 = np.asarray(g["stage1_position_search_initial_weight"]).T
    after = path.stat()
    assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
    aW, bW, noW = W0.copy(), W0.copy(), W0.copy()
    au, bu, ar, br, opp, loss_delta, track_delta, weight_delta = [], [], [], [], [], [], [], []
    parity, diff_max = 0.0, 0.0
    for i, n in enumerate(ids):
        old = {} if i == 0 else dict(phi_prev=ph[i-1], y_prev=y[i],
            previous_index=int(ids[i-1]), previous_time_s=float(ids[i-1]*.001))
        a = c5.delayed_prediction_step(aW, ph[i], se[i], int(n), float(n*.001), **old)
        b_same = c6.delayed_prediction_step(aW, ph[i], se[i], int(n), float(n*.001), **old)
        b = c6.delayed_prediction_step(bW, ph[i], se[i], int(n), float(n*.001), **old)
        expected = .01*(1-a["beta"])*a["prediction_gradient"]
        diff_max = max(diff_max, error(b_same["preprojection_candidate"]-a["preprojection_candidate"], expected))
        assert np.array_equal(a["raw"], b_same["raw"]) and np.array_equal(a["applied"], b_same["applied"])
        if a["beta"] == 1:
            assert np.array_equal(a["W_next"], b_same["W_next"])
        no_raw = noW.T @ ph[i]
        parity = max(parity, error(a["raw"] if item["host"] == "C5" else no_raw, source_raw[i]))
        au.append(a["applied"]); bu.append(b["applied"])
        if i:
            ar.append(aW.T @ ph[i-1]-y[i]); br.append(bW.T @ ph[i-1]-y[i])
            loss_delta.append(.5*((b_same["W_next"].T@ph[i-1]-y[i])**2 -
                                    (a["W_next"].T@ph[i-1]-y[i])**2))
        else:
            ar.append(np.full(3, np.nan)); br.append(np.full(3, np.nan))
            loss_delta.append(np.full(3, np.nan))
        track_delta.append(se[i]*a["beta"]*((b_same["W_next"]-a["W_next"]).T@ph[i]))
        original_pred = -.01*a["prediction_gradient"]
        opp.append([np.linalg.norm(original_pred[:, ax]) for ax in range(3)])
        noW = np.clip(noW-.12*a["beta"]*np.outer(ph[i], se[i])-.00002*noW, -60, 60)
        aW, bW = a["W_next"], b["W_next"]
        weight_delta.append(np.linalg.norm(bW-aW))
    assert parity < 1e-10 and diff_max < 2e-12
    au, bu, ar, br, opp, loss_delta, track_delta = [np.asarray(x) for x in
        (au, bu, ar, br, opp, loss_delta, track_delta)]
    t, beta = ids*.001, np.minimum((ids+1)*.001/1.8, 1)
    for phase, lo, hi in (("startup_032_18", .32, 1.8), ("18_5", 1.8, 5), ("5_20", 5, 20)):
        mask = (t >= lo) & (t < hi)
        for ax, axis in enumerate("xyz"):
            signal_rows.append({
                "scene_id": item["scene_id"], "host": item["host"], "phase": phase, "axis": axis,
                "events": int(mask.sum()), "beta_mean": float(beta[mask].mean()),
                "C5_prediction_step_RMS_on_C5_W": float(np.sqrt(np.mean(opp[mask, ax]**2))),
                "C6_prediction_step_RMS_on_same_C5_W": float(np.sqrt(np.mean((beta[mask]*opp[mask, ax])**2))),
                "one_step_prediction_loss_C6_minus_C5": float(np.nanmean(loss_delta[mask, ax])),
                "one_step_tracking_surface_times_delta_readout_m2_per_s3": float(np.mean(track_delta[mask, ax])),
                "forced_C6_minus_C5_output_RMS_mps2": float(np.sqrt(np.mean((bu[mask, ax]-au[mask, ax])**2))),
                "forced_C5_prediction_fit_RMS_mps2": float(np.sqrt(np.nanmean(ar[mask, ax]**2))),
                "forced_C6_prediction_fit_RMS_mps2": float(np.sqrt(np.nanmean(br[mask, ax]**2))),
            })
    host_reviews.append({
        "scene_id": item["scene_id"], "host": item["host"], "path": str(path),
        "source_raw_sha256_previously_verified": item["sha256"],
        "source_raw_whole_file_rehashed_this_check": False,
        "source_identity_attestation": str(PRIOR), "source_bytes_and_stat_unchanged_during_read": True,
        "datasets_read": ["stage1_position_event_inference_valid", "stage1_position_event_phi_33",
                          "stage1_position_pcf_event_s_coord_eff_mps", "stage1_position_delayed_prediction_target_mps2",
                          "stage1_position_event_raw_acceleration_mps2", "stage1_position_search_initial_weight"],
        "source_raw_output_parity_max_abs": parity,
        "one_step_exact_difference_max_abs": diff_max,
        "forced_weight_difference_after_20s_fro": float(weight_delta[-1]),
    })
result = {
    "status": "PASS_C6_CODE_ONLY_ALGEBRA_AND_THREE_RECORDED_DEV_HOSTS",
    "created_utc": datetime.now(timezone.utc).isoformat(),
    "checks": checks, "hosts": host_reviews,
    "checker_sha256": sha(Path(__file__)), "C6_source_binding_sha256": sha(OUT / "C6_SOURCE_BINDING_v1.json"),
    "prior_DEV_source_review_sha256": sha(PRIOR),
    "new_Plant": 0, "MATLAB_invocations": 0, "training_steps": 0, "GPU": 0,
    "current_TEST_performance_accessed": False,
    "MATLAB_validation": "Source copied from frozen helper with exactly one expression change; MATLAB was not executed.",
    "boundary": "Beta=1 equivalence uses identical W and inputs only. Forced-state outputs/label fits are not closed-loop Q; earlier C6 weights can affect every later output and closed-loop state.",
    "inherited_reference_self_check_note": "Copied reference retains the original C5 synthetic self-check and historical development notes; new C6 execution evidence is this file.",
}
with (OUT / "C6_FORCED_STATE_TRADEOFF_v1.csv").open("x", encoding="utf-8", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=list(signal_rows[0])); writer.writeheader(); writer.writerows(signal_rows)
with (OUT / "C6_CODE_ONLY_REVIEW_v1.json").open("x", encoding="utf-8") as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
print(json.dumps({"status": result["status"], "checks": checks,
    "host_max_parity": max(h["source_raw_output_parity_max_abs"] for h in host_reviews),
    "host_max_exact_difference": max(h["one_step_exact_difference_max_abs"] for h in host_reviews)}, ensure_ascii=False, indent=2))
