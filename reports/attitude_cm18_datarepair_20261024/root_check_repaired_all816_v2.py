"""Independent cache-value audit and TRAIN-only normalizer fingerprint."""
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


def main():
    out = HERE / "ROOT_REPAIRED_ALL816_INDEPENDENT_AUDIT_v2.json"
    assert not out.exists()
    path = HERE / "repaired_all816_v1/DATASET_MANIFEST_v1.json"
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    assert sha == "3f51a1cd0e2e8c3eae79a16df363f2f8d47b0d5dbd876ecd95f1571d9e70a5e0"
    m = json.loads(raw)
    assert m["status"] == "PASS" and m["qualified_count"] == 816 and m["failed_count"] == 0
    source = json.loads((HERE / "B_REF_REPAIRED_SOURCE_MANIFEST_v1.json").read_text())
    assert [r["scene_id"] for r in m["rows"]] == [r["scene_id"] for r in source["scenes"]]
    c5 = json.loads((HERE / "c5_val48_c5_teacher_v3/C5_VAL48_EVENT_CACHE_MANIFEST_v3.json").read_text())
    c5_raw_shas = {r["candidate_raw_sha256"] for r in c5["scenes"]}
    fit_x, fit_y, counts = [], [], {"TRAIN": 0, "VAL": 0}
    fingerprints, repaired, reused = [], 0, 0
    for row, src in zip(m["rows"], source["scenes"]):
        p = (ROOT / row["cache_path"]).resolve(strict=True)
        assert p.is_relative_to(ROOT.resolve())
        b = p.read_bytes()
        assert len(b) == row["cache_bytes"] and hashlib.sha256(b).hexdigest() == row["cache_sha256"]
        d = loadmat(p, simplify_cells=True)
        assert d["scene_id"] == row["scene_id"] and d["split"] == row["split"]
        x, y = d["X18"], d["target_raw"]
        assert x.dtype == y.dtype == np.float64 and x.shape == (1999,18) and y.shape == (1999,3)
        assert np.all(np.isfinite(x)) and np.all(np.isfinite(y))
        index = np.asarray(d["plant_index"]).reshape(-1)
        assert np.issubdtype(index.dtype, np.integer) and np.array_equal(index, np.arange(11,20000,10))
        assert np.max(np.abs(np.asarray(d["event_time_s"]).reshape(-1)-(index-1)*.001)) <= 1e-12
        phase = np.asarray(d["phase_code"])
        assert phase.dtype == np.uint8 and phase.size == 1999 and np.max(phase) <= 5
        identity = d["input_identity"]
        if "_T2_" in row["scene_id"]:
            repaired += 1
            assert d["cache_schema"] == "CM18_REPAIRED_EVENT_CACHE_V1"
            assert identity["corrected_raw_sha256"] == src["corrected_source"]["raw"]["sha256"]
            assert identity["corrected_raw_sha256"] not in c5_raw_shas
            assert not d["original_a1_identity"]["cache_used_as_repaired_label"]
            assert src["corrected_source"]["role"] == "B"
        else:
            reused += 1
            assert identity["raw_run_sha256"] == src["original_a1_source"]["raw_run"]["sha256"]
            assert identity["raw_run_sha256"] not in c5_raw_shas
        if row["split"] == "TRAIN":
            assert x[::5].shape == (400,18)
            # Match frozen A1 advanced-index C layout, not a Fortran-layout stride view.
            sample_indices = np.arange(0,1996,5,dtype=np.int64)
            fit_x.append(x[sample_indices]); fit_y.append(y[sample_indices])
        counts[row["split"]] += 1
        fingerprints.append(row["scene_id"]+":"+row["cache_sha256"])
    assert counts == {"TRAIN":768,"VAL":48} and repaired == 272 and reused == 544
    x, y = np.concatenate(fit_x), np.concatenate(fit_y)
    assert x.shape == (307200,18) and y.shape == (307200,3)
    mean, std = x.mean(axis=0,dtype=np.float64), np.maximum(x.std(axis=0,ddof=0,dtype=np.float64),1e-6)
    scale = np.sqrt(np.mean(np.square(y,dtype=np.float64),axis=0,dtype=np.float64))
    assert np.all(np.isfinite(mean)) and np.all(np.isfinite(std)) and np.all(np.isfinite(scale)) and np.all(scale>0)
    norm_sha = hashlib.sha256(b"".join(np.ascontiguousarray(a,dtype=np.float64).tobytes() for a in (mean,std,scale))).hexdigest()
    result = {"schema":"ROOT_REPAIRED_ALL816_INDEPENDENT_AUDIT_V2","status":"PASS",
        "dataset_manifest_sha256":sha,"scenes":816,"split_counts":counts,"repaired":repaired,"reused":reused,
        "TRAIN_events":768*1999,"VAL_events":48*1999,"TRAIN_fit_rows":307200,
        "TRAIN_only_float64_normalizer_sha256":norm_sha,
        "ordered_cache_identity_sha256":hashlib.sha256("\n".join(fingerprints).encode()).hexdigest(),
        "scope":{"independent_SciPy_cache_numeric_reads":816,"C5_teacher_raw_used_in_B_dataset":False,
                 "raw_numeric_reads":0,"Plant_calls":0,"optimizer_steps":0,"TEST_accessed":False}}
    out.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2))


if __name__ == "__main__":
    main()
