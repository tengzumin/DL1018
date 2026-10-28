"""Independent full48 numerical cache audit; caches remain VAL-only."""
import hashlib
import json
from pathlib import Path
import numpy as np
from scipy.io import loadmat

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    path = HERE / "c5_val48_c5_teacher_v3/C5_VAL48_EVENT_CACHE_MANIFEST_v3.json"
    data = path.read_bytes()
    manifest_sha = hashlib.sha256(data).hexdigest()
    assert manifest_sha == "3e72f4726219cfd0e89476c70d24796a06c8f8447d4064cfdc471433a863a501"
    manifest = json.loads(data)
    assert manifest["status"] == "PASS" and manifest["summary"]["passed"] == 48
    assert len(manifest["scenes"]) == len({r["scene_id"] for r in manifest["scenes"]}) == 48
    assert sum(r["cache_reused_from_v2"] for r in manifest["scenes"]) == 47
    rows = []
    for row in manifest["scenes"]:
        cache_path = (ROOT / row["cache_path_relative"]).resolve(strict=True)
        assert cache_path.is_relative_to(ROOT.resolve())
        raw = cache_path.read_bytes()
        assert len(raw) == row["cache_bytes"] and hashlib.sha256(raw).hexdigest() == row["cache_sha256"]
        cache = loadmat(cache_path, simplify_cells=True)["cache"]
        identity, events = cache["identity"], cache["events"]
        assert identity["scene_id"] == row["scene_id"] and identity["split"] == "VAL"
        assert not identity["training_eligible"]
        for field in ("candidate_raw_sha256", "candidate_run_start_sha256", "candidate_run_status_sha256"):
            assert identity[field] == row[field]
        for field in ("initial_attitude_rbf_weight_zero_from_raw_log", "cfg_matches_snapshot",
                      "shared_attitude_opts_match_snapshot", "position_model_W0_matches_snapshot"):
            assert identity[field]
        if row["scene_id"] == "DL1018_VAL_T2_C00_W10":
            for field in ("legacy_nested_model_exact", "legacy_model_metadata_exact",
                          "legacy_normalizer_arrays_exact", "legacy_runtime_weight_exact",
                          "legacy_head_W0_exact", "legacy_raw_initial_position_weight_exact"):
                assert identity[field]
            assert row["raw_initial_position_weight_max_abs_delta"] == 0
        x, y = events["X18"], events["target_raw"]
        assert x.shape == (1999, 18) and y.shape == (1999, 3)
        assert x.dtype == y.dtype == np.float64
        assert np.all(np.isfinite(x)) and np.all(np.isfinite(y))
        idx = np.asarray(events["plant_index"]).reshape(-1)
        assert np.array_equal(idx, np.arange(11, 20000, 10))
        assert np.max(np.abs(np.asarray(events["event_time_s"]).reshape(-1)-(idx-1)*.001)) <= 1e-12
        assert events["phase_code"].dtype == np.uint8 and events["phase_code"].size == 1999
        assert np.max(events["phase_code"]) <= 5
        assert events["closure"]["requested_torque_vs_nominal_minus_applied_max_abs_Nm"] <= 1e-8
        assert events["closure"]["true_dynamics_equation_residual_max_abs_Nm"] <= 1e-12
        rows.append({"scene_id": row["scene_id"], "cache_sha256": row["cache_sha256"], "status": "PASS"})
    out = HERE / "ROOT_C5_VAL48_CACHE_INDEPENDENT_AUDIT_v3.json"
    assert not out.exists()
    out.write_text(json.dumps({"schema": "ROOT_C5_VAL48_CACHE_INDEPENDENT_AUDIT_V3",
        "status": "PASS", "source_manifest_sha256": manifest_sha, "scenes": 48,
        "events": 48*1999, "reused": 47, "new": 1, "rows": rows,
        "scope": {"cache_numeric_reads": 48, "raw_numeric_reads": 0, "Plant_calls": 0,
                  "optimizer_steps": 0, "TEST_accessed": False, "training_eligible": False}}, indent=2)+"\n")
    print("ROOT_VAL48_CACHE_PASS: all48 actual cache arrays/identities, 95952 events, VAL-only")


if __name__ == "__main__":
    main()
