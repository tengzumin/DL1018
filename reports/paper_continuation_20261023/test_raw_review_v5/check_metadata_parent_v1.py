"""Run only parent-reviewed metadata gates; deny every TEST MAT/result open."""
import builtins
import copy
import datetime
import hashlib
import importlib.util
import io
import json
from pathlib import Path

import h5py
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
READER = HERE / "audit_test48_raw_v5.py"
PIN = "1c7380abd2b1f29e0f7045017abaeef87f54d751ad74a710bfbdbdac504730ff"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert sha(READER) == PIN
    denied = []
    old_io, old_builtin = io.open, builtins.open
    old_hdf, old_np = h5py.File, np.load

    def guarded(original):
        def run(file, *args, **kwargs):
            if isinstance(file, (str, Path)):
                name = str(file).replace("\\", "/").casefold()
                historical_dev = "/c5_test48_v6/engineering_dev2/dssm/dl1018_val_t1_c00_w07/attempt_01/raw_run.mat"
                if "c5_test48_" in name and Path(name).suffix in {".mat", ".csv", ".npz"} and not name.endswith(historical_dev):
                    denied.append(name)
                    raise AssertionError("TEST MAT/result open denied")
            return original(file, *args, **kwargs)
        return run

    def no_array_open(*args, **kwargs):
        raise AssertionError("No HDF/NPZ decoding allowed in metadata-only parent check")

    io.open, builtins.open = guarded(old_io), guarded(old_builtin)
    h5py.File, np.load = no_array_open, no_array_open
    try:
        spec = importlib.util.spec_from_file_location("parent_final_reader", READER)
        reader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reader)
        v1 = reader.load_v1()
        contract, manifest, _, info = reader.verify_v4_code_and_manifest(v1)
        old = reader.load_json(v1.SOURCE_MANIFEST)
        lineage = reader.validate_method_lineage(old, manifest, v1)
        release, release_info = reader.verify_v4_run_release(contract, info, v1)
        reader.verify_v3_failure_history(v1)
        reader.verify_v4_failure_and_path_diagnostic_history(v1)
        history = reader.verify_v5_v8_history(v1, manifest)
        stages = reader.verify_stage_preconditions(release, v1, manifest)

        def reject(mutator):
            bad = copy.deepcopy(manifest)
            mutator(bad)
            try:
                reader.validate_method_lineage(old, bad, v1)
            except (AssertionError, ValueError, KeyError):
                return True
            raise AssertionError("Mutated model/source identity accepted")

        mutations = [
            lambda m: m["methods"][1]["source_refs"].append(copy.deepcopy(m["methods"][1]["source_refs"][0])),
            lambda m: m["methods"][1]["source_refs"][0].update(sha256="0" * 64),
            lambda m: m["methods"][1]["source_refs"][0].update(role="unvalidated_snapshot"),
            lambda m: m["methods"][2]["source_refs"][0].update(path=m["methods"][1]["source_refs"][0]["path"]),
            lambda m: m["methods"][1]["model_refs"][0].update(sha256="0" * 64),
            lambda m: m["methods"][3]["source_refs"].append(copy.deepcopy(m["methods"][3]["source_refs"][0])),
        ]
        assert all(reject(fn) for fn in mutations)
        assert not denied
        result = {
            "status": "PASS_PARENT_METADATA_GATES_AND_SIX_INVALID_LINEAGES_REJECTED",
            "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "reader_sha256": PIN, "checker_sha256": sha(Path(__file__)),
            "source_lineage": lineage, "release_sha256": release_info["sha256"],
            "prior_v5_v8_processes_checked": len(history),
            "v9_stage_artifacts_checked": len(stages["stage_artifacts"]),
            "invalid_model_or_source_mutations_rejected": len(mutations),
            "denied_TEST_open_attempts": denied,
            "TEST_MAT_raw_or_scores_read": False, "reader_CLI_executed": False,
            "historical_failed_DEV_raw": "Only the SHA-bound v6 fixed VAL failure is byte-hashed; no HDF decoding. Initial guard was overbroad and blocked this DEV file, then was narrowed to this exact allowed path.",
            "new_Plant": 0,
        }
    finally:
        io.open, builtins.open = old_io, old_builtin
        h5py.File, np.load = old_hdf, old_np
    output = HERE / "PARENT_METADATA_REVIEW_v1.json"
    assert not output.exists()
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
