"""Same-state yaw action consistency; offline diagnosis, no fitting or simulation."""
import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "offline_label_decomposition_v2/MATCHED_POSITION_LABEL_DECOMPOSITION_v2.json"
SHA = "2c98a3e6ce6915bb03e00c4a74db1415ac1f71c2515773b48b3e4fa173f60093"


def rms(x):
    return float(np.sqrt(np.mean(np.square(x))))


def main():
    out = HERE / "ROOT_YAW_REPLACEMENT_TARGET_CHECK_v1.json"
    assert not out.exists()
    data = SOURCE.read_bytes()
    assert hashlib.sha256(data).hexdigest() == SHA
    source = json.loads(data)
    assert source["status"] == "PASS"
    rows = []
    for scene in source["scenes"]:
        assert scene["preconditions"]["simple_formula_applicable"] is True
        record = scene["event_records"]
        d = np.asarray(record["target_raw_rad_s2"], dtype=float)[:, 2]
        g = np.asarray(record["g_zz"], dtype=float).reshape(-1)
        old = np.asarray(record["c_old_z"], dtype=float).reshape(-1)
        assert d.shape == g.shape == old.shape == (1999,)
        assert np.all(np.isfinite(np.concatenate([d, g, old]))) and np.all(g > 0)
        # alpha_true(c)-alpha_BS = E0-g*c, while behavior label d=E0+(1-g)*c_old.
        e0 = d - (1-g)*old
        ideal = e0/g
        ideal_residual = e0-g*ideal
        behavior_prediction_residual = e0-g*d
        assert np.max(np.abs(ideal_residual)) < 1e-12
        rows.append({"flight_id": scene["flight_id"], "event_count": len(d),
            "g_range": [float(g.min()), float(g.max())],
            "behavior_label_RMS_rad_s2": rms(d),
            "ideal_same_state_compensation_RMS_rad_s2": rms(ideal),
            "label_vs_ideal_gap_RMS_rad_s2": rms(d-ideal),
            "same_state_alpha_error_if_output_exact_behavior_label_RMS_rad_s2": rms(behavior_prediction_residual),
            "ideal_output_above_existing_yaw_clip_count": int(np.count_nonzero(np.abs(ideal) > 4.7124)),
            "ideal_same_state_equation_closure_max_abs_rad_s2": float(np.max(np.abs(ideal_residual)))})
    report = {"schema": "ROOT_YAW_REPLACEMENT_TARGET_CHECK_V1", "status": "PASS_DIAGNOSTIC_ONLY",
        "source_sha256": SHA, "rows": rows,
        "interpretation": "Perfect prediction of a behavior residual need not cancel nominal acceleration error after replacing that behavior action. The ideal action is a same-state offline diagnostic, not a demonstrated closed-loop solution.",
        "limits": ["Yaw only under each source's verified decoupling/no clipping/no actuator-lag preconditions.",
            "Changes to future state, requested thrust, reference filters and feedback are outside this algebraic check.",
            "True inertia and wind are offline label quantities, forbidden as extra deployment inputs.",
            "No new target, model, training, Plant run or success criterion is released by this diagnostic."],
        "scope": {"Plant_calls": 0, "optimizer_steps": 0, "TEST_accessed": False}}
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
