"""Measure repaired TRAIN support against the four frozen probe event sets."""
import os
for key in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
    os.environ[key] = "1"
import hashlib
import json
from pathlib import Path
import numpy as np
from scipy.io import loadmat

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PROBE = ROOT / "reports/attitude_position_context_probe_20261024"


def main():
    out = HERE / "ROOT_REPAIRED_TRAIN_SUPPORT_v1.json"
    assert not out.exists()
    p = HERE / "repaired_all816_v1/DATASET_MANIFEST_v1.json"
    raw = p.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "3f51a1cd0e2e8c3eae79a16df363f2f8d47b0d5dbd876ecd95f1571d9e70a5e0"
    manifest = json.loads(raw)
    low, high = np.full(3,np.inf), np.full(3,-np.inf)
    fitlow, fithigh = low.copy(), high.copy()
    count = 0
    for row in manifest["rows"]:
        if row["split"] != "TRAIN": continue
        path = ROOT / row["cache_path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row["cache_sha256"]
        m = loadmat(path, variable_names=["X18"])
        x = m["X18"][:,3:6]
        assert x.shape == (1999,3) and np.all(np.isfinite(x))
        low = np.minimum(low,x.min(axis=0)); high = np.maximum(high,x.max(axis=0))
        fitlow = np.minimum(fitlow,x[::5].min(axis=0)); fithigh = np.maximum(fithigh,x[::5].max(axis=0))
        count += 1
    assert count == 768
    prior_path = PROBE / "ROOT_ALPHA_XY_TRAIN_SUPPORT_DIAGNOSTIC_v1.json"
    prior_raw = prior_path.read_bytes()
    assert hashlib.sha256(prior_raw).hexdigest() == "46aacf7b2c0b643b45b7f6962230cc7b44fe74035e8843479fa9e808a04a9173"
    prior = json.loads(prior_raw)
    pairs = {}
    for flight in ("T1_B","T1_C5","T3_B","T3_C5"):
        path = PROBE / "offline_events_v2" / f"events_{flight}_v2.json"
        raw = path.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == prior["probe_scenes"][flight]["event_export_sha256"]
        x = np.asarray(json.loads(raw)["X18"],dtype=float)[:,3:6]
        outside = (x<low)|(x>high)
        fitoutside = (x<fitlow)|(x>fithigh)
        pairs[flight] = {"events":1999,"old_TRAIN_xy_outside":prior["probe_scenes"][flight]["against_full_train_1999_support"]["outside_any_axis_event_count"],
            "repaired_TRAIN_xy_outside":int(np.any(outside[:,:2],axis=1).sum()),
            "repaired_TRAIN_xyz_outside_by_axis":outside.sum(axis=0).tolist(),
            "repaired_fit_xy_outside":int(np.any(fitoutside[:,:2],axis=1).sum())}
    result = {"schema":"ROOT_REPAIRED_TRAIN_SUPPORT_V1","status":"PASS_DIAGNOSTIC",
        "TRAIN_scenes":768,"features":["alphaBS_x","alphaBS_y","alphaBS_z"],
        "full_event_bounds":{"min":low.tolist(),"max":high.tolist()},
        "fit_stride_bounds":{"min":fitlow.tolist(),"max":fithigh.tolist()},"probes":pairs,
        "limits":"Marginal ranges only; no claim of joint support, error attribution or model generalization.",
        "scope":{"VAL_cache_values_read":False,"TEST_accessed":False,"Plant_calls":0,"optimizer_steps":0}}
    out.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2))


if __name__ == "__main__":
    main()
