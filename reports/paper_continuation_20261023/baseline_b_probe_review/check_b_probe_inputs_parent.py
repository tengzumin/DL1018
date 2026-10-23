"""Parent verification of actual v2 B source bindings and prepared cfg/options."""
import hashlib
import importlib.util
import json
import shutil
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
RUN = ROOT / "experiments/b_traceable_c3core_20261023"


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def main():
    output = HERE / "PARENT_B_PROBE_V2_PREPARE_REVIEW.json"
    assert not output.exists()
    lock_path = RUN / "B_TRACEABLE_INPUT_LOCK_v2.json"
    prep_path = RUN / "B_TRACEABLE_PREPARE_RESULT_v2.json"
    exit_path = RUN / "B_TRACEABLE_VERIFY_SHUTDOWN_HANG_v2.json"
    verify_path = RUN / "B_TRACEABLE_VERIFY_RESULT_v2.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8-sig"))
    prep = json.loads(prep_path.read_text(encoding="utf-8-sig"))
    exit_record = json.loads(exit_path.read_text(encoding="utf-8-sig"))
    verification = json.loads(verify_path.read_text(encoding="utf-8-sig"))
    assert prep["status"] == "PREPARED_NO_PLANT_WAIT_PARENT_RELEASE"
    assert prep["plant_calls"] == prep["training_steps"] == prep["optimizer_steps"] == 0
    assert not prep["run_episode_called"] and not prep["TEST_accessed"]
    assert prep["input_lock_sha256"] == sha(lock_path)
    snapshot = Path(prep["snapshot_path"])
    assert sha(snapshot) == prep["snapshot_sha256"]
    assert verification["status"] == "PASS_NO_PLANT" and verification["plant_calls"] == 0
    assert not verification["episode_called"] and verification["which_checks"] == 31
    assert verification["prepare_result_sha256"] == sha(prep_path)
    assert verification["snapshot_sha256"] == sha(snapshot)
    assert verification["input_lock_sha256"] == sha(lock_path)
    assert exit_record["verify_result_sha256"] == sha(verify_path)
    assert exit_record["exec_tool_exit_code"] == 1 and exit_record["natural_matlab_os_exit_code"] is None
    assert exit_record["task_owned_pids_still_visible"] == [] and not exit_record["plant_attempted"]
    seen = {}
    def verify(value):
        if isinstance(value, dict):
            if "path" in value and "sha256" in value:
                p = Path(value["path"])
                assert sha(p) == value["sha256"], str(p)
                seen[str(p)] = value["sha256"]
            for child in value.values():
                verify(child)
        elif isinstance(value, list):
            for child in value:
                verify(child)
    verify(lock)
    active = lock["active_source_inventory"]
    assert len(active) == len({Path(r["path"]).name for r in active}) == 32
    prior_lock = ROOT / "experiments/position_delayed_prediction_c3_dev72_20261023/C3_DEV72_INPUT_LOCK_v2.json"
    prior = json.loads(prior_lock.read_text(encoding="utf-8-sig"))
    expected = {Path(r["path"]).name: r["sha256"] for r in prior["frozen_runtime_files"] + prior["frozen_plant_files"]}
    isolated = prior["source_files"]["isolated_c3_sources"]
    for ref in isolated.values() if isinstance(isolated, dict) else isolated:
        expected[Path(ref["path"]).name] = ref["sha256"]
    assert {Path(r["path"]).name: r["sha256"] for r in active} == expected
    helper = ROOT / "reports/paper14_v2/phase1/audit_w15_position_replay.py"
    spec = importlib.util.spec_from_file_location("existing_mat_reader", helper)
    reader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    cfg = reader.flatten(reader.matlab_section(snapshot, "cfg"))
    prior_cfg = reader.flatten(reader.matlab_section(Path(lock["upstream_refs"]["c3_dev72_prepared_snapshot"]["path"]), "cfg"))
    assert cfg.keys() == prior_cfg.keys() and all(reader.same_value(cfg[k], prior_cfg[k]) for k in cfg)
    opts = reader.flatten(reader.matlab_section(snapshot, "opts"))
    source_ids = HERE.parent / "baseline_b_source_review/SOURCE_IDS.json"
    expected_opts = json.loads(source_ids.read_text(encoding="utf-8-sig"))["b_options_contract"]["field_values"]
    assert opts.keys() == expected_opts.keys() and len(opts) == 13
    assert all(np.asarray(opts[k]).size == 1 and float(np.asarray(opts[k]).ravel()[0]) == float(v) for k, v in expected_opts.items())
    assert not list(RUN.rglob("first_plant_step.marker")) and not list(RUN.rglob("raw_run.mat"))
    reserve = 80000000
    used = sum(p.stat().st_size for p in RUN.rglob("*") if p.is_file())
    free = shutil.disk_usage(ROOT).free
    assert used + reserve <= 134217728 and free - reserve >= 30000000000
    result = {"status": "PASS", "actual_refs_verified": len(seen), "active_source_count": 32,
              "cfg_matching_leaves": len(cfg), "B_opts_matching_leaves": 13,
              "MATLAB_no_Plant_computation": "PASS; independent fresh MATLAB VERIFY also PASS",
              "MATLAB_natural_OS_exit": None, "exec_tool_exit_after_completed_verify": 1,
              "OS_limit": "Owned completed zero-Plant verifier was interrupted after shutdown hung, including quit(force); never claim normal exit 0",
              "new_Plant": 0, "TEST_accessed": False, "parent_manual_reserve_bytes": reserve,
              "directory_bytes_before_release": used, "free_bytes_before_release": free,
              "decoding_limit": "Reuses reviewed MAT section decoder; fresh actual file/SHA/inventory/cfg/B-contract comparisons",
              "refs": [{"path": str(p), "sha256": sha(p)} for p in [lock_path, prep_path, snapshot, verify_path, exit_path, source_ids, helper, Path(__file__)]]}
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: v for k, v in result.items() if k != "refs"}))


if __name__ == "__main__":
    main()
