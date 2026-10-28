"""Root audit: actual repaired caches, source identity, shape and split; no raw scan."""
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    out = HERE / "ROOT_REFERENCE_REPAIRED_SCREEN4_CACHE_AUDIT_v1.json"
    assert not out.exists()
    source_path = HERE / "B_REF_REPAIRED_SOURCE_MANIFEST_v1.json"
    source_sha = "0f86b47d01940e7b556b78a9664470531572809aa6857a59fc77d88a33681ec5"
    assert sha(source_path) == source_sha
    source = json.loads(source_path.read_text())
    by_id = {r["scene_id"]: r for r in source["scenes"]}
    receipt_path = HERE / "export_screen4_v1/SCREEN4_EXPORT_RECEIPT_v1.json"
    receipt = json.loads(receipt_path.read_text())
    assert receipt["status"] == "PASS" and receipt["scene_count"] == 4
    assert receipt["source_manifest_sha256"] == source_sha
    assert [r["scene_id"] for r in receipt["rows"]] == source["screen4_scene_ids"]
    rows = []
    for row in receipt["rows"]:
        src = by_id[row["scene_id"]]
        path = (ROOT / row["cache_path"]).resolve(strict=True)
        assert path.is_relative_to(ROOT.resolve())
        assert path.stat().st_size == row["cache_bytes"] and sha(path) == row["cache_sha256"]
        cache = loadmat(path, simplify_cells=True)
        assert cache["cache_schema"] == "CM18_REPAIRED_EVENT_CACHE_V1"
        assert cache["scene_id"] == row["scene_id"] and cache["split"] == src["split"]
        identity = cache["input_identity"]
        assert identity["source_manifest_sha256"] == source_sha
        assert identity["corrected_raw_sha256"] == src["corrected_source"]["raw"]["sha256"] == row["raw_sha256"]
        assert identity["corrected_run_start_sha256"] == src["corrected_source"]["run_start"]["sha256"] == row["run_start_sha256"]
        assert identity["runtime_scene_id"] == row["scene_id"]+"_ACC_FIX_V1"
        old = cache["original_a1_identity"]
        assert old["raw_sha256"] == src["original_a1_source"]["raw_run"]["sha256"]
        assert old["raw_sha256"] != identity["corrected_raw_sha256"]
        assert not old["cache_used_as_repaired_label"] and not identity["old_A1_H5_read"]
        x, y = cache["X18"], cache["target_raw"]
        assert x.shape == (1999, 18) and y.shape == (1999, 3)
        assert x.dtype == y.dtype == np.float64 and np.all(np.isfinite(x)) and np.all(np.isfinite(y))
        idx = cache["plant_index"].reshape(-1)
        assert idx.dtype == np.uint32 and np.array_equal(idx, np.arange(11, 20000, 10))
        assert np.max(np.abs(cache["event_time_s"].reshape(-1)-(idx-1)*.001)) <= 1e-12
        assert cache["phase_code"].dtype == np.uint8 and np.max(cache["phase_code"]) <= 5
        meta = cache["export_meta"]
        assert meta["requested_torque_vs_nominal_minus_applied_max_abs_Nm"] <= 1e-8
        assert meta["true_dynamics_equation_residual_max_abs_Nm"] <= 1e-12
        rows.append({"scene_id": row["scene_id"], "status": "PASS", "cache_sha256": row["cache_sha256"]})
    result = {"schema": "ROOT_REFERENCE_REPAIRED_SCREEN4_CACHE_AUDIT_V1", "status": "PASS",
        "receipt_sha256": sha(receipt_path), "source_manifest_sha256": source_sha,
        "event_count": 4*1999, "rows": rows,
        "scope": {"raw_numeric_reads": 0, "cache_numeric_reads": 4, "Plant_calls": 0,
            "optimizer_steps": 0, "TEST_accessed": False, "all816_certified": False}}
    out.write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    print("ROOT_REPAIRED_SCREEN4_PASS: four actual caches; 7996 events; distinct corrected raw identities")


if __name__ == "__main__":
    main()
