from pathlib import Path
import hashlib
import json
import numpy as np
from scipy.io import loadmat

here = Path(__file__).resolve().parent
lock_path = here / "C3_SOURCE_LOCK.json"
lock = json.loads(lock_path.read_text(encoding="utf-8"))
model_item = next(x for x in lock["shared_input_files"] if x["role"] == "model_mat")
npz_item = next(x for x in lock["shared_input_files"] if x["role"] == "normalizer_npz")
c2_lock_item = lock["c2_source_lock"]
c2_lock = json.loads(Path(c2_lock_item["path"]).read_text(encoding="utf-8"))
c2_expected = c2_lock["shared_c1_inputs"]["normalizer_arrays_sha256"]
model = loadmat(model_item["path"], squeeze_me=False, struct_as_record=False)["model"][0, 0]
npz = np.load(npz_item["path"])
fields = (("input_mu", "mu"), ("input_sigma", "sigma"))
arrays = {
    field: np.asarray(getattr(model, field), dtype="<f8").reshape(-1, order="F")
    for field, _ in fields
}
checks = {
    field: bool(np.array_equal(arrays[field],
                               np.asarray(npz[npz_field], dtype="<f8").reshape(-1, order="F")))
    for field, npz_field in fields
}
payload = b"".join(
    (field + "\0((1, 14), 'float64')\0").encode("utf-8")
    + arrays[field].tobytes(order="C")
    for field, _ in fields
)
computed = hashlib.sha256(payload).hexdigest()
report = {
    "schema": "C3_NORMALIZER_HASH_DIAGNOSTIC_V1",
    "status": "PASS_ARRAY_IDENTITY_AND_C2_HASH",
    "c3_prepare_entry_sha256_at_failed_attempt": hashlib.sha256(
        Path(lock["prepare_entry_path"]).read_bytes()).hexdigest(),
    "c3_source_lock_sha256_at_failed_attempt": hashlib.sha256(lock_path.read_bytes()).hexdigest(),
    "model_mat_path": model_item["path"],
    "model_mat_sha256": hashlib.sha256(Path(model_item["path"]).read_bytes()).hexdigest(),
    "normalizer_npz_path": npz_item["path"],
    "normalizer_npz_sha256": hashlib.sha256(Path(npz_item["path"]).read_bytes()).hexdigest(),
    "c2_source_lock_path": c2_lock_item["path"],
    "c2_source_lock_sha256": hashlib.sha256(Path(c2_lock_item["path"]).read_bytes()).hexdigest(),
    "array_identity": checks,
    "all_arrays_equal": all(checks.values()),
    "expected_sha256_from_frozen_c2": c2_expected,
    "expected_sha256_in_c3_lock": lock["normalizer_arrays_sha256"],
    "computed_sha256_using_c2_c1_header_and_float64_bytes": computed,
    "hash_matches_both_frozen_locks": computed.lower() == c2_expected.lower() == lock["normalizer_arrays_sha256"].lower(),
    "c2_canonical_header": "field + NUL + ((1, 14), 'float64') + NUL; UTF-8, followed by 14 float64 bytes",
    "failed_c3_reason": "The original C3 helper hashed uint64 dimension-count/shape prefixes, unlike the frozen C2/C1 canonical header."
}
out = here / "C3_NORMALIZER_HASH_DIAGNOSTIC.json"
out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, sort_keys=True))