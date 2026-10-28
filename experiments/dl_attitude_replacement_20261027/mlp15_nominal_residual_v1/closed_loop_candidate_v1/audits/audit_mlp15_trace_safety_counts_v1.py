"""Read-only per-scene MLP15 trace safety counters for completed authorized raws."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import h5py
import numpy as np
from scipy.io import loadmat

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
MODEL_ROOT = ROOT / "experiments/dl_attitude_replacement_20261027/mlp15_nominal_residual_v1"
STUDIES = {
    "original": MODEL_ROOT / "closed_loop_candidate_v1",
    "update_first": MODEL_ROOT / "closed_loop_update_first_v1",
}
MODEL = MODEL_ROOT / "runs/MLP15_TRAIN_C5_24_PHYSICAL_RESIDUAL_SEED2026102001_REPAIR01/mlp15_attitude_weights_v1.mat"
DEFAULT_OUT = HERE / "MLP15_TRACE_SAFETY_COUNTS_v1.json"
TOL = 1e-10


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def txt(dataset) -> str:
    a = np.asarray(dataset[()]).reshape(-1)
    if a.dtype.kind in "ui":
        return "".join(chr(int(v)) for v in a if int(v))
    if a.dtype.kind == "S":
        return b"".join(a.tolist()).decode("utf-8").rstrip("\x00")
    if a.dtype.kind == "U":
        return "".join(a.tolist()).rstrip("\x00")
    return str(a.item()) if a.size == 1 else ""


def v(group, key) -> np.ndarray:
    return np.asarray(group[key][()], dtype=np.float64).reshape(-1)


def s(group, key) -> float:
    return float(v(group, key)[0])


def matrix(group, key) -> np.ndarray:
    return np.asarray(group[key][()], dtype=np.float64).T


def audit_scene(study_name: str, study: Path, scene_id: str, scale: np.ndarray) -> dict:
    run = study / "runs" / scene_id / "PHYS_RESIDUAL_ATTEMPT_01"
    raw_path, status_path = run / "raw_run.mat", run / "run_status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    if (status.get("scene_id") != scene_id or status.get("state") != "COMPLETED" or
            status.get("status_value") != "STABLE" or status.get("plant_calls") != 1 or
            status.get("test_data_read") is not False):
        raise ValueError(f"incomplete/unauthorized run identity: {scene_id} ({study_name})")
    raw_hash = sha(raw_path)
    if raw_hash.lower() != status.get("raw_sha256", "").lower():
        raise ValueError(f"raw/status SHA mismatch: {scene_id} ({study_name})")
    release_path = study / "RELEASE.json"
    release = json.loads(release_path.read_text(encoding="utf-8"))
    if (scene_id not in release.get("authorized_scenes", []) or release.get("TEST_read") is not False or
            "TEST" in scene_id.upper()):
        raise ValueError(f"release cohort/TEST guard failed: {scene_id} ({study_name})")

    with h5py.File(raw_path, "r") as raw:
        ident = raw["runIdentity"]
        if (txt(ident["scene_id"]) != scene_id or txt(ident["physical_residual_model_sha256"]).lower() !=
                release["model_sha256"].lower() or txt(ident["release_sha256"]).lower() != sha(release_path).lower() or
                bool(np.asarray(ident["test_data_read"][()]).astype(bool).any())):
            raise ValueError(f"embedded raw identity mismatch: {scene_id} ({study_name})")
        J0 = np.asarray(ident["fixed_J0_kg_m2"][()], dtype=np.float64).T
        log = raw["log"]
        flags = np.asarray(log["attitude_event_flag"][()]).reshape(-1).astype(bool)
        refs = log["mlp15_attitude_trace"][()].reshape(-1)
        time = np.asarray(log["time"][()], dtype=np.float64).reshape(-1)
        applied = np.asarray(log["attitude_compensation_applied_torque_Nm"][()], dtype=np.float64).T
        if flags.shape != refs.shape or flags.size != 20000 or time.size != 20001 or int(flags.sum()) != 1999:
            raise ValueError(f"event/time dimensions changed: {scene_id} ({study_name})")

        records = []
        clip_axes = np.zeros(3, dtype=np.int64)
        clip_events = 0
        raw_formula_max = torque_formula_max = applied_max = 0.0
        before_norm = after_norm = rls_norm = output_norm = 0.0
        state_projection = output_projection = rls_update = tracking_update = 0
        projected_output_cap_max = 0.0
        endpoint_future_excess = issued_index_excess = observation_alignment_error = 0.0

        event_qs = np.flatnonzero(flags)
        for q in event_qs:
            g = raw[refs[q]]
            h = g["causal_head"]
            sample, event_time = int(s(g, "sample_index")), s(g, "time_s")
            wb, wa = matrix(h, "weight_before"), matrix(h, "weight_after")
            max_before, max_after = np.linalg.norm(wb), np.linalg.norm(wa)
            before_norm = max(before_norm, max_before)
            after_norm = max(after_norm, max_after)
            state_projection += int(bool(s(h, "projection_active")))
            rls_update += int(bool(s(h, "update_executed")))
            tracking_update += int("tracking_update_executed" in h and
                                    bool(np.asarray(h["tracking_update_executed"][()]).astype(bool).any()))

            base = v(h, "base_residual_rad_s2")
            raw_residual = v(g, "raw_residual_rad_s2")
            clipped = v(g, "clipped_residual_rad_s2")
            phi = v(h, "phi")
            if "weight_output_used" in h:
                w_output = matrix(h, "weight_output_used")
                w_rls = matrix(h, "weight_after_rls")
                outproj = bool(s(h, "output_projection_active"))
                output_projection += int(outproj)
                rls_norm = max(rls_norm, float(np.linalg.norm(w_rls)))
                output_norm = max(output_norm, float(np.linalg.norm(w_output)))
                expected_w = w_rls.copy()
                n_rls = np.linalg.norm(expected_w)
                if n_rls > 20:
                    expected_w *= 20 / n_rls
                projected_output_cap_max = max(projected_output_cap_max,
                                               float(np.max(np.abs(w_output - expected_w))))
                used_weight = w_output
            else:
                # Legacy output-before-update uses the stored pre-update weight.
                used_weight = wb
            raw_formula_max = max(raw_formula_max,
                float(np.max(np.abs(raw_residual - (base + scale * (used_weight.T @ phi))))))

            dclip = np.abs(raw_residual - clipped)
            if np.any(dclip > TOL):
                clip_events += 1
            clip_axes += dclip > TOL
            beta = s(g, "beta")
            estimate = v(g, "estimateTorque_Nm")
            expected_torque = J0 @ (beta * clipped)
            torque_formula_max = max(torque_formula_max, float(np.max(np.abs(estimate - expected_torque))))
            applied_max = max(applied_max, float(np.max(np.abs(applied[int(q)] - estimate))))

            prev = int(s(h, "previous_feature_sample_index"))
            if sample < 1 or abs(event_time - time[sample - 1]) > TOL:
                raise ValueError(f"event/sample timestamp mismatch: {scene_id} sample={sample}")
            if prev:
                end = s(h, "observation_end_time_s")
                start = s(h, "observation_start_time_s")
                endpoint_future_excess = max(endpoint_future_excess, end - event_time)
                issued_index_excess = max(issued_index_excess, s(h, "issued_torque_max_sample_index") - (sample - 1))
                observation_alignment_error = max(observation_alignment_error,
                    abs((end - start) - .01), abs(end - event_time))
            records.append({"sample": sample, "previous_sample": prev,
                            "weight_before": wb, "weight_after": wa})

        continuity_max = 0.0
        valid_obs = 0
        by_sample = {r["sample"]: r for r in records}
        for r in records:
            if r["previous_sample"]:
                valid_obs += 1
                prior = by_sample.get(r["previous_sample"])
                if prior is None or r["sample"] - prior["sample"] != 10:
                    raise ValueError(f"previous feature/event pairing mismatch: {scene_id}")
                # Read each weight_before only for this continuity check.
                continuity_max = max(continuity_max,
                    float(np.max(np.abs(r["weight_before"] - prior["weight_after"]))))

        generic_projection = (int(np.asarray(log["attitude_head_projection_active"][()]).astype(bool).sum())
                              if "attitude_head_projection_active" in log else None)
        generic_saturated = (int(np.asarray(log["attitude_head_output_saturated"][()]).astype(bool).sum())
                             if "attitude_head_output_saturated" in log else None)
        has_output_fields = "weight_output_used" in raw[refs[event_qs[0]]]["causal_head"]
        return {
            "study": study_name, "scene_id": scene_id, "raw_sha256": raw_hash,
            "status": status["status_value"], "plant_calls": status["plant_calls"],
            "test_data_read": False, "attitude_events": len(records), "valid_observations": valid_obs,
            "projection_counts": {
                "MLP_final_state_projection_active": state_projection,
                "MLP_output_projection_active": output_projection if has_output_fields else None,
                "legacy_v39_head_projection_active": generic_projection,
                "legacy_v39_head_output_saturated": generic_saturated,
            },
            "residual_clip": {"event_count": clip_events, "axis_sample_counts": clip_axes.tolist()},
            "max_weight_fro_norm": {
                "weight_before": before_norm, "weight_after_final": after_norm,
                "weight_after_rls": rls_norm if has_output_fields else None,
                "weight_output_used": output_norm if has_output_fields else None,
            },
            "output_identity_max_abs": raw_formula_max,
            "output_weight_matches_frobenius20_projection_max_abs": projected_output_cap_max if has_output_fields else None,
            "estimate_torque_equals_J0_beta_clipped_max_abs_Nm": torque_formula_max,
            "logged_applied_torque_equals_event_estimate_max_abs_Nm": applied_max,
            "timing": {"endpoint_future_excess_max_s": max(0.0, endpoint_future_excess),
                       "issued_index_excess_over_event_minus1_max": max(0.0, issued_index_excess),
                       "observation_interval_alignment_max_abs_s": observation_alignment_error,
                       "stored_weight_after_to_next_before_max_abs": continuity_max},
            "online_updates": {"RLS_update_events": rls_update, "tracking_update_events": tracking_update},
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    scale = np.asarray(loadmat(MODEL)["target_rms"], dtype=np.float64).reshape(-1)
    result = {"schema": "DL1018_MLP15_TRACE_SAFETY_COUNTS_V1",
              "status": "PASS_READ_ONLY_AUTHORIZED_RAW_AUDIT",
              "scope": "per-scene counters only; no raw trace vectors saved; TEST is rejected by release/status guards",
              "tracking_drive_confounded_design": True,
              "tracking_drive_note": "Both original and update-first candidate inherit an RLS+tracking composite head; this audit does not attribute the 12-scene results to the taskbook's pure target-only factor.",
              "studies": {}}
    for name, study in STUDIES.items():
        release = json.loads((study / "RELEASE.json").read_text(encoding="utf-8"))
        ids = release.get("authorized_scenes", [])
        if release.get("TEST_read") is not False or any("TEST" in sid.upper() for sid in ids):
            raise ValueError(f"TEST authorization invariant failed: {name}")
        rows = []
        pending = []
        for sid in ids:
            raw_path = study / "runs" / sid / "PHYS_RESIDUAL_ATTEMPT_01" / "raw_run.mat"
            status_path = raw_path.with_name("run_status.json")
            if not raw_path.is_file() or not status_path.is_file():
                pending.append(sid)
                continue
            status = json.loads(status_path.read_text(encoding="utf-8"))
            if status.get("state") != "COMPLETED":
                pending.append(sid)
                continue
            rows.append(audit_scene(name, study, sid, scale))
        result["studies"][name] = {"authorized_scene_count": len(ids), "audited_scene_count": len(rows),
                                    "pending_scene_ids": pending, "scenes": rows}
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite {args.output}; choose --output with a new version")
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({name: {"audited": v["audited_scene_count"], "pending": len(v["pending_scene_ids"])}
                      for name, v in result["studies"].items()}, ensure_ascii=False))
    print(args.output)


if __name__ == "__main__":
    main()
