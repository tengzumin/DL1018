"""Three explicitly selected DEV hosts; source parity and forced-state replay only."""
import csv
import hashlib
import importlib.util
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports/paper_continuation_20261023/c5_eight_loss_recovery/same_state_v2"
TABLE = ROOT / "reports/paper_continuation_20261023/c5_matched_ablation_dev72_parent_review/MATCHED_ABLATION_DEV72_ALL_PAIRS_v1.csv"
KERNEL = ROOT / "reports/delayed_prediction_proposal_20261023/construction/delayed_prediction_kernel.py"
spec = importlib.util.spec_from_file_location("frozen_delayed_prediction_kernel", KERNEL)
kernel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kernel)

def digest(p):
    with p.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()

def native_path(p):
    return "\\\\?\\" + str(p.resolve()) if os.name == "nt" else str(p)

def err(a, b):
    a, b = np.asarray(a), np.asarray(b)
    assert a.shape == b.shape and np.isfinite(a).all() and np.isfinite(b).all(), (a.shape, b.shape)
    return float(np.max(np.abs(a - b)))

def rms(a):
    return float(np.sqrt(np.mean(np.square(a))))

with TABLE.open(encoding="utf-8-sig", newline="") as stream:
    pairs = [r for r in csv.DictReader(stream) if r["variant"] == "C5_NO_DELAYED_PREDICTION"]
assert len(pairs) == 72 and len({r["scene_id"] for r in pairs}) == 72
by_scene = {r["scene_id"]: r for r in pairs}
cases = [("DL1018_DEV_T2_C09_W10", "C5"),
         ("DL1018_DEV_T2_C09_W10", "NO_PRED"),
         ("DL1018_DEV_T1_C01_W15", "C5")]
checks, signals, access = [], [], []

for sid, host in cases:
    row = by_scene[sid]
    prefix = "C5_M110" if host == "C5" else "candidate"
    path = Path(row[prefix + "_path"])
    assert "_DEV_" in sid and "test" not in str(path).lower()
    before = path.stat()
    actual_sha = digest(path)
    assert actual_sha == row[prefix + "_sha256"]
    with h5py.File(native_path(path), "r") as file:
        g = file["log"]
        keys_read = []
        def read(key):
            keys_read.append(key)
            val = np.asarray(g[key])
            return val.T if val.ndim == 2 else val
        ids = np.flatnonzero(read("stage1_position_event_inference_valid").ravel())
        assert np.array_equal(ids, np.arange(320, 19991, 10))
        t = ids * .001
        phi = read("stage1_position_event_phi_33")[ids]
        wb = np.asarray(g["stage1_position_event_weight_before_33x3"]).transpose(0, 2, 1)
        wa = np.asarray(g["stage1_position_event_weight_after_33x3"]).transpose(0, 2, 1)
        keys_read += ["stage1_position_event_weight_before_33x3", "stage1_position_event_weight_after_33x3"]
        W0 = read("stage1_position_search_initial_weight")
        seff_log = read("stage1_position_pcf_event_s_coord_eff_mps")[ids]
        beta_log = read("stage1_position_event_beta").ravel()[ids]
        raw_log = read("stage1_position_event_raw_acceleration_mps2")[ids]
        applied_log = read("stage1_position_event_applied_acceleration_mps2")[ids]
        ylog = read("stage1_position_delayed_prediction_target_mps2")[ids]
        state = read("state")
        refp, refv, refa = [read("reference/" + k)[:-1] for k in ("position", "velocity", "acceleration")]
        ep = refp - state[:-1, :3]
        ev = refv - state[:-1, 3:6]
        surface = ep + ev
        nominal = refa + ev + ep + 4 * surface
        nominal_log = read("position_nominal_acceleration_mps2")
        eta = read("stage1_position_pcf_eta_before_mps")
        req = read("stage1_position_pcf_a_req_mps2")
        af = read("stage1_position_pcf_a_f_mps2")
        rf = read("stage1_position_pcf_r_f_mps2")
        beta = np.minimum((ids + 1) * .001 / 1.8, 1)
        coordinated = surface[ids] - eta[ids] * np.array([1, 1, 0])
        seff = np.clip(coordinated, [-7, -8, -10], [7, 8, 10])
        reference = af.copy()
        reference[:, 2] = req[:, 2]
        y = np.full((len(ids), 3), np.nan)
        for i, (j, k) in enumerate(zip(ids[:-1], ids[1:]), 1):
            y[i] = ((state[k, 3:6] - state[j, 3:6]) - .001 * reference[j:k].sum(axis=0)) / .01
        previous_raw = np.einsum("nfi,nf->ni", wb[1:], phi[:-1])
        residual = previous_raw - y[1:]
        pred_step = np.zeros_like(wb)
        pred_step[1:] = -.01 * phi[:-1, :, None] * residual[:, None, :]
        tracking_step = -.12 * beta[:, None, None] * phi[:, :, None] * seff[:, None, :]
        leak_step = -.00002 * wb
        expected_after = np.clip(wb + tracking_step + leak_step + (pred_step if host == "C5" else 0), -60, 60)
        ch = {
            "W0": err(wb[0], W0),
            "weight_continuity": err(wb[1:], wa[:-1]),
            "phi_norm": err(np.linalg.norm(phi, axis=1), np.ones(len(ids))),
            "beta_clock": err(beta_log, beta),
            "nominal_BS_reconstruction": err(nominal_log, nominal),
            "surface_M110": err(seff_log, seff),
            "past_interval_target": err(ylog[1:], y[1:]),
            "output_before_update": err(raw_log, np.einsum("nfi,nf->ni", wb, phi)),
            "beta_clip": err(applied_log, beta[:, None] * np.clip(raw_log, -3, 3)),
            "joint_source_update": err(wa, expected_after),
            "rf_definition": err(rf, req - af),
            "eta_exact_held": err(read("stage1_position_pcf_eta_after_mps"),
                                  np.exp(-.004) * eta - np.expm1(-.004) / 4 * rf),
        }
        feature = read("stage1_position_feature_14")[ids]
        # Preview uses the identical nominal BS acceleration, zero compensation and current yaw.
        preview_specific = nominal + np.array([0, 0, json.loads((ROOT / "configs/contract_dl1018.json").read_text(encoding="utf-8-sig"))["plant"]["gravity_mps2"]])
        preview_thrust_per_mass = np.linalg.norm(preview_specific, axis=1)
        feature_expected = np.column_stack((ep, surface, state[:-1, 6:9], preview_thrust_per_mass,
                                            read("arms/command")[:20000]))
        ch["pre_network_X14_from_same_state"] = err(feature, feature_expected[ids])
        # Two full recurrences on exactly the same host phi/s/eta/target. No Plant/state rollout.
        full_W, no_W = W0.copy(), W0.copy()
        full_u, no_u, full_res, no_res = [], [], [], []
        replay_parity = 0.0
        for i, k in enumerate(ids):
            prior = {} if i == 0 else dict(phi_prev=phi[i-1], y_prev=y[i],
                                           previous_index=int(ids[i-1]), previous_time_s=float(t[i-1]))
            proposal = kernel.delayed_prediction_step(full_W, phi[i], seff[i], int(k), float(t[i]), **prior)
            no_raw = no_W.T @ phi[i]
            no_next = np.clip(no_W - .12 * beta[i] * np.outer(phi[i], seff[i]) - .00002 * no_W, -60, 60)
            full_u.append(proposal["applied"])
            no_u.append(beta[i] * np.clip(no_raw, -3, 3))
            if i:
                full_res.append(full_W.T @ phi[i-1] - y[i])
                no_res.append(no_W.T @ phi[i-1] - y[i])
            if host == "C5":
                replay_parity = max(replay_parity, err(full_W, wb[i]), err(proposal["W_next"], wa[i]))
            else:
                replay_parity = max(replay_parity, err(no_W, wb[i]), err(no_next, wa[i]))
            full_W, no_W = proposal["W_next"], no_next
        ch["full_source_recurrence_parity"] = replay_parity
        assert max(ch.values()) < 1e-10, (sid, host, ch)
        full_u, no_u = np.asarray(full_u), np.asarray(no_u)
        full_res, no_res = np.asarray(full_res), np.asarray(no_res)
        # Isolated next-output effect of adding exactly one prediction step at source W.
        full_next = np.clip(wb[:-1] + tracking_step[:-1] + leak_step[:-1] + pred_step[:-1], -60, 60)
        no_next = np.clip(wb[:-1] + tracking_step[:-1] + leak_step[:-1], -60, 60)
        one_full_u = beta[1:, None] * np.clip(np.einsum("nfi,nf->ni", full_next, phi[1:]), -3, 3)
        one_no_u = beta[1:, None] * np.clip(np.einsum("nfi,nf->ni", no_next, phi[1:]), -3, 3)
        one_effect = one_full_u - one_no_u
        for phase, lo, hi in (("ready_to_beta_full", .32, 1.8), ("beta_full_to_5s", 1.8, 5), ("late_5_20", 5, 20), ("all_ready", .32, 20)):
            m = (t >= lo) & (t < hi)
            m_prev = (t[1:] >= lo) & (t[1:] < hi)
            for ax, axis in enumerate("xyz"):
                tr = tracking_step[m, :, ax]
                pr = pred_step[m, :, ax]
                dot = np.sum(tr * pr, axis=1)
                normprod = np.linalg.norm(tr, axis=1) * np.linalg.norm(pr, axis=1)
                nonzero = normprod > 1e-16
                signals.append({
                    "scene_id": sid, "host": host, "phase": phase, "axis": axis,
                    "events": int(m.sum()), "beta_mean": float(beta[m].mean()),
                    "source_surface_original_RMS_mps": rms(surface[ids[m], ax]),
                    "source_eta_RMS_mps": rms(eta[ids[m], ax]),
                    "source_surface_effective_RMS_mps": rms(seff[m, ax]),
                    "tracking_step_RMS_weight_column_norm": float(np.sqrt(np.mean(np.sum(tr*tr, axis=1)))),
                    "prediction_step_RMS_weight_column_norm": float(np.sqrt(np.mean(np.sum(pr*pr, axis=1)))),
                    "prediction_opposes_tracking_fraction": float(np.mean(dot[nonzero] < 0)) if nonzero.any() else 0.0,
                    "source_prediction_residual_RMS_mps2": rms(residual[m_prev, ax]),
                    "one_step_prediction_next_output_RMS_mps2": rms(one_effect[m_prev, ax]),
                    "mean_sEff_next_times_one_step_delta_u_mps3": float(np.mean(seff[1:][m_prev, ax] * one_effect[m_prev, ax])),
                    "forced_full_minus_no_pred_output_RMS_mps2": rms((full_u-no_u)[m, ax]),
                    "forced_full_fit_RMS_mps2": rms(full_res[m_prev, ax]),
                    "forced_no_pred_fit_RMS_mps2": rms(no_res[m_prev, ax]),
                })
        checks.append({"scene_id": sid, "host": host, "checks": ch, "max_error": max(ch.values()),
                       "event_count": len(ids), "source_Q_0_20_m_from_existing_table": float(row[prefix + "_Q_0_20_m"]),
                       "source_sha256": actual_sha})
        access.append({"scene_id": sid, "host": host, "path": str(path), "sha256": actual_sha,
                       "bytes": before.st_size, "datasets_read": keys_read})
    after = path.stat()
    assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)

groups = [("ALL72", pairs), ("HF28", [r for r in pairs if 9 <= int(r["wind"][1:]) <= 14]),
          ("W15", [r for r in pairs if r["wind"] == "W15"])]
groups += [(task, [r for r in pairs if r["task"] == task]) for task in ("T1", "T2", "T3")]
groups += [(f"T2_W{w:02d}", [r for r in pairs if r["task"] == "T2" and r["wind"] == f"W{w:02d}"]) for w in range(16)]
group_rows = []
for name, rr in groups:
    if not rr:
        continue
    for phase in ("0_20", "0_5", "5_20"):
        b = np.array([float(r[f"B_TRACEABLE_Q_{phase}_m"]) for r in rr])
        c = np.array([float(r[f"C5_M110_Q_{phase}_m"]) for r in rr])
        n = np.array([float(r[f"candidate_Q_{phase}_m"]) for r in rr])
        group_rows.append({"group": name, "phase": phase, "n": len(rr),
                           "B_macro_mm": float(b.mean()*1000), "C5_macro_mm": float(c.mean()*1000),
                           "NO_PRED_macro_mm": float(n.mean()*1000),
                           "C5_wins_B": int(np.sum(c < b-1e-12)), "NO_PRED_wins_B": int(np.sum(n < b-1e-12)),
                           "C5_wins_NO_PRED": int(np.sum(c < n-1e-12)),
                           "C5_minus_NO_PRED_macro_mm": float(np.mean(c-n)*1000)})
loss_rows = []
for r in pairs:
    if float(r["C5_M110_Q_0_20_m"]) <= float(r["B_TRACEABLE_Q_0_20_m"]) + 1e-12:
        continue
    item = {"scene_id": r["scene_id"], "task": r["task"], "wind": r["wind"]}
    for phase in ("0_20", "0_5", "5_20"):
        for label, prefix in (("B", "B_TRACEABLE"), ("C5", "C5_M110"), ("NO_PRED", "candidate")):
            item[f"{label}_{phase}_mm"] = 1000*float(r[f"{prefix}_Q_{phase}_m"])
    loss_rows.append(item)
assert len(loss_rows) == 8
OUT.mkdir(exist_ok=False)
for name, rr in (("SAME_STATE_SIGNALS_v1.csv", signals), ("DEV72_GROUP_PHASE_TRADEOFF_v1.csv", group_rows),
                 ("EIGHT_LOSSES_PHASE_NO_PRED_v1.csv", loss_rows)):
    with (OUT / name).open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rr[0]))
        writer.writeheader()
        writer.writerows(rr)
result = {"status": "PASS_THREE_DEV_HOST_SOURCE_PARITY_AND_FORCED_STATE_REPLAY",
          "created_utc": datetime.now(timezone.utc).isoformat(),
          "checks": checks, "raw_access": access, "table_sha256": digest(TABLE), "kernel_sha256": digest(KERNEL),
          "new_Plant": 0, "MATLAB": 0, "training": 0, "current_TEST_access": False,
          "boundary": "Both recurrences use each single host's recorded phi/s/eta/target. Outputs and gradient alignment identify algebraic behavior only; they are not counterfactual closed-loop Q or component-cause proof."}
with (OUT / "SAME_STATE_REPLAY_REVIEW_v1.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
print(json.dumps({"status": result["status"], "max_source_error": max(r["max_error"] for r in checks),
                  "hosts": [(r["scene_id"], r["host"]) for r in checks], "output": str(OUT)}, ensure_ascii=False, indent=2))

