"""Independently bind C4 preparation, source inventory and validation artifacts."""
import hashlib
import importlib.util
import json
import shutil
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
RUN = ROOT / "experiments/position_coordinate_c4_20261023"


def sha(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def main():
    output = HERE / "PARENT_C4_PREPARE_REVIEW.json"
    assert not output.exists()
    lock_path = RUN / "C4_INPUT_LOCK_v3.json"
    lock = load(lock_path)
    seen = {}

    def refs(value):
        if isinstance(value, dict):
            if "path" in value and "sha256" in value:
                path = Path(value["path"])
                if str(path) not in seen:
                    assert sha(path) == value["sha256"], str(path)
                    seen[str(path)] = value["sha256"]
            for child in value.values():
                refs(child)
        elif isinstance(value, list):
            for child in value:
                refs(child)

    refs(lock)
    c3_lock = load(lock["upstream_refs"]["c3_input_lock"]["path"])
    c3_sources = {Path(r["path"]).name: r["sha256"] for r in c3_lock["frozen_runtime_files"] + c3_lock["frozen_plant_files"]}
    isolated = c3_lock["source_files"]["isolated_c3_sources"]
    for r in isolated.values() if isinstance(isolated, dict) else isolated:
        c3_sources[Path(r["path"]).name] = r["sha256"]
    c4_sources = {Path(r["path"]).name: r["sha256"] for r in lock["active_source_inventory"]}
    assert len(c4_sources) == len(c3_sources) == 32 and c3_sources.keys() == c4_sources.keys()
    changed = [k for k in c4_sources if c4_sources[k] != c3_sources[k]]
    assert changed == ["run_dl1018_closed_loop.m"]
    prep_path = RUN / "C4_PREPARE_RESULT_v3.json"
    prep = load(prep_path)
    assert prep["status"] == "PREPARED_NO_PLANT_WAIT_PARENT_RELEASE_V3" and prep["plant_calls"] == 0
    assert not prep["run_episode_called"] and not prep["TEST_accessed"]
    assert prep["input_lock_sha256"] == sha(lock_path)
    snapshot = Path(prep["snapshot_path"])
    assert sha(snapshot) == prep["snapshot_sha256"]
    validation_path = RUN / "C4_CROSSLANG_SYNTHETIC_RESULT_v2.json"
    validation = load(validation_path)
    assert validation["status"] == "PASS_SYNTHETIC_CROSSLANGUAGE_ONLY"
    assert validation["max_abs_error"] <= 2e-12 and not validation["plant_or_real_data_used"]
    fixture = RUN / "C4_CROSSLANG_FIXTURE_v1.json"
    assert sha(fixture) == validation["fixture_sha256"]
    assert validation["matlab_helper_sha256"] == c4_sources["delayed_prediction_step_candidate.m"]
    fixture_value = load(fixture)
    assert sha(fixture_value["python_kernel_path"]) == fixture_value["python_kernel_sha256"]
    decoder_path = ROOT / "reports/paper14_v2/phase1/audit_w15_position_replay.py"
    spec = importlib.util.spec_from_file_location("existing_mat_decoder", decoder_path)
    decoder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(decoder)
    c3_snapshot = Path(lock["upstream_refs"]["c3_prepared_snapshot"]["path"])
    counts = {}
    for section in ("cfg", "opts"):
        actual = decoder.flatten(decoder.matlab_section(snapshot, section))
        expected = decoder.flatten(decoder.matlab_section(c3_snapshot, section))
        if section == "opts":
            assert np.asarray(actual.pop("position_coordinate_m")).item() == 0
        assert actual.keys() == expected.keys()
        assert all(decoder.same_value(actual[k], expected[k]) for k in actual), section
        counts[section] = len(actual)
    w0 = np.asarray(decoder.matlab_section(snapshot, "W0"), dtype="<f8")
    assert w0.shape == (33, 3)
    assert hashlib.sha256(w0.tobytes(order="F")).hexdigest() == lock["candidate_identity"]["W0_sha256"]
    assert np.all(np.abs(w0) <= 60)
    assert not list(RUN.rglob("first_plant_step.marker")) and not list(RUN.rglob("raw_run.mat"))
    used = sum(p.stat().st_size for p in RUN.rglob("*") if p.is_file())
    free = shutil.disk_usage(ROOT).free
    assert used + 80000000 < 1073741824 and free - 80000000 > 30000000000
    result = {"status": "PASS_PREPARED_C4_M0_SOURCE_INPUT_AND_CROSSLANGUAGE_BINDINGS",
              "unique_actual_path_SHA_checks": len(seen), "active_source_count": 32,
              "changed_active_sources_vs_C3": changed, "matching_C3_cfg_opts_leaves": counts,
              "only_extra_option": {"position_coordinate_m": 0}, "W0_sha256": lock["candidate_identity"]["W0_sha256"],
              "W0_max_abs_mps2": float(np.abs(w0).max()), "W0_inside_projection_box": True,
              "synthetic_max_abs_error": validation["max_abs_error"], "new_Plant": 0,
              "TEST_accessed": False, "manual_first_flight_output_reserve_bytes": 80000000,
              "directory_bytes": used, "disk_free_bytes": free,
              "limits": ["Synthetic helper check does not exercise actual runtime wiring; raw all-event audit required after pilot",
                         "Inventory has 32 items including one MAT; 31 MATLAB which assertions, despite prepare metadata labeling count32",
                         "Superseded v1 input lock had a literal created_utc; active builder records its actual build time",
                         "Uses existing reviewed MAT decoder; fresh source/file/hash/options comparisons"],
              "refs": [{"path": str(p), "sha256": sha(p)} for p in
                       [lock_path, prep_path, snapshot, validation_path, fixture,
                        RUN / "c4_coordinate_fixture_v1.py", RUN / "check_c4_coordinate_synthetic_v2.m",
                        Path(fixture_value["python_kernel_path"]), decoder_path, Path(__file__)]]}
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: result[k] for k in ("status", "unique_actual_path_SHA_checks", "matching_C3_cfg_opts_leaves", "synthetic_max_abs_error")}))


if __name__ == "__main__":
    main()
