"""Independent SciPy audit of actual 47 PASS caches; does not promote failed row."""
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MANIFEST = HERE / "c5_val48_c5_teacher_v2/C5_VAL48_EVENT_CACHE_MANIFEST_v2.json"
SHA = "ea669228e267c2207b02ed63b55fb395847c6d2e37af5aea631014f3a1d9cd81"


def main():
    out = HERE / "ROOT_C5_VAL47_CACHE_INDEPENDENT_AUDIT_v1.json"
    assert not out.exists()
    raw = MANIFEST.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SHA
    manifest = json.loads(raw)
    assert manifest["status"] == "FAIL"
    failed = [row for row in manifest["scenes"] if row["status"] != "PASS"]
    assert len(failed) == 1 and failed[0]["scene_id"] == "DL1018_VAL_T2_C00_W10"
    rows = []
    for row in manifest["scenes"]:
        if row["status"] != "PASS":
            continue
        path = (ROOT / row["cache_path_relative"]).resolve(strict=True)
        assert path.is_relative_to(ROOT.resolve())
        data = path.read_bytes()
        assert len(data) == row["cache_bytes"]
        assert hashlib.sha256(data).hexdigest() == row["cache_sha256"]
        cache = loadmat(path, simplify_cells=True)["cache"]
        identity, events = cache["identity"], cache["events"]
        assert cache["schema"] == "CM18_VAL_C5_EVENT_CACHE_V2"
        assert identity["scene_id"] == row["scene_id"] and identity["split"] == "VAL"
        assert not identity["training_eligible"]
        for field in ("candidate_raw_sha256", "candidate_run_start_sha256", "candidate_run_status_sha256"):
            assert identity[field] == row[field]
        assert identity["initial_attitude_rbf_weight_zero_from_raw_log"]
        assert identity["cfg_matches_snapshot"] and identity["shared_attitude_opts_match_snapshot"]
        assert identity["position_model_W0_matches_snapshot"]
        x, y = np.asarray(events["X18"]), np.asarray(events["target_raw"])
        assert x.shape == (1999, 18) and y.shape == (1999, 3)
        assert x.dtype == y.dtype == np.float64
        assert np.all(np.isfinite(x)) and np.all(np.isfinite(y))
        idx = np.asarray(events["plant_index"]).reshape(-1)
        assert np.array_equal(idx, np.arange(11, 20000, 10))
        t = np.asarray(events["event_time_s"]).reshape(-1)
        assert np.max(np.abs(t-(idx-1)*.001)) <= 1e-12
        phase = np.asarray(events["phase_code"])
        assert phase.dtype == np.uint8 and phase.size == 1999 and np.max(phase) <= 5
        closure = events["closure"]
        assert closure["requested_torque_vs_nominal_minus_applied_max_abs_Nm"] <= 1e-8
        assert closure["true_dynamics_equation_residual_max_abs_Nm"] <= 1e-12
        rows.append({"scene_id": row["scene_id"], "cache_sha256": row["cache_sha256"], "status": "PASS"})
    assert len(rows) == 47 and len({r["scene_id"] for r in rows}) == 47
    result = {"schema": "ROOT_C5_VAL47_CACHE_INDEPENDENT_AUDIT_V1", "status": "PASS_47_ONLY",
        "source_manifest_sha256": SHA, "cache_count": 47, "event_count": 47*1999,
        "missing_scene": "DL1018_VAL_T2_C00_W10", "rows": rows,
        "scope": {"cache_values_read": True, "raw_files_read": 0, "Plant_calls": 0,
            "optimizer_steps": 0, "TEST_accessed": False, "promotes_full_VAL48": False}}
    out.write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    print("ROOT_VAL47_CACHE_PASS: 47 actual caches, 93953 events; full48 remains incomplete")


if __name__ == "__main__":
    main()
