"""Read the new traceable B flight and compare complete historical trajectories."""
import hashlib
import importlib.util
import json
from pathlib import Path

import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
RUN = ROOT / "experiments/b_traceable_c3core_20261023"


def sha(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def main():
    output = HERE / "PARENT_B_PROBE_RAW_REVIEW.json"
    assert not output.exists(), "Preserve earlier evidence"
    ledger_path = RUN / "B_TRACEABLE_EXECUTION_LEDGER_v2.json"
    ledger = read_json(ledger_path)
    status_path = RUN / "runs_b/DL1018_VAL_T2_C00_W10/B_TRACEABLE_C3CORE_V1/attempt_01/run_status.json"
    status = read_json(status_path)
    assert sha(status_path) == ledger["run_status_sha256"]
    assert status["status"] == "RUN_COMPLETE_RAW_PENDING_AUDIT" and status["plant_calls"] == 1
    assert status["transitions"] == 20000 and status["state_samples"] == 20001
    assert not status["TEST_accessed"] and status["training_steps"] == 0
    for path_key, hash_key in [
        ("raw_path", "raw_sha256"), ("run_start_path", "run_start_sha256"),
        ("first_plant_step_marker_path", "first_plant_step_marker_sha256")
    ]:
        assert sha(status[path_key]) == status[hash_key]
    assert ledger["os_exit_code"] == 0
    exit_path = ROOT / ledger["os_exit_record"]
    assert sha(exit_path) == ledger["os_exit_record_sha256"]
    release_path = ROOT / ledger["release_path"]
    assert sha(release_path) == status["release_sha256"] == ledger["release_sha256"]
    assert sha(ROOT / ledger["execution_script_path"]) == ledger["execution_script_sha256"]
    assert sha(ROOT / ledger["runner_path"]) == ledger["runner_sha256"]
    lock_path = RUN / "B_TRACEABLE_INPUT_LOCK_v2.json"
    lock = read_json(lock_path)
    assert sha(lock_path) == status["input_lock_sha256"]
    for ref in lock["active_source_inventory"]:
        assert sha(ref["path"]) == ref["sha256"]
    assert len(lock["active_source_inventory"]) == 32
    prep_path = RUN / "B_TRACEABLE_PREPARE_RESULT_v2.json"
    assert sha(prep_path) == status["prepare_result_sha256"]
    prep = read_json(prep_path)
    snapshot = Path(prep["snapshot_path"])
    assert sha(snapshot) == status["cfg_opts_snapshot_sha256"]

    reader_path = ROOT / "reports/paper14_v2/phase1/audit_w15_position_replay.py"
    reader = module(reader_path, "reviewed_mat_decoder")
    start = reader.matlab_section(Path(status["run_start_path"]), "runStart")
    count = {}
    for section in ("cfg", "opts"):
        actual = reader.flatten(start[section])
        expected = reader.flatten(reader.matlab_section(snapshot, section))
        if section == "opts":
            assert "r2e_first_plant_step_marker" in actual
            actual.pop("r2e_first_plant_step_marker")
        assert actual.keys() == expected.keys()
        assert all(reader.same_value(actual[k], expected[k]) for k in actual)
        count[section] = len(actual)
    assert count == {"cfg": 120, "opts": 13}

    manifest_path = ROOT / "reports/delayed_prediction_c3_dev72_parent_20261023/PARENT_HISTORICAL_216_MANIFEST.json"
    old = [row for row in read_json(manifest_path)["rows"]
           if row["method"] == "B" and row["scene_id"] == status["scene_id"]]
    assert len(old) == 1
    old = old[0]
    scorer_path = ROOT / "reports/delayed_prediction_c3_dev72_parent_20261023/parent_raw_metrics.py"
    scorer = module(scorer_path, "existing_parent_raw_scorer")
    new = {"scene_id": status["scene_id"], "method": "B_TRACEABLE_C3CORE_V1",
           "path": status["raw_path"], "sha256": status["raw_sha256"]}
    new_metrics, old_metrics = scorer.score(new), scorer.score(old)
    assert new_metrics["external_identity_sha256"] == old_metrics["external_identity_sha256"]
    assert new_metrics["Q_0_20_m"] == old_metrics["Q_0_20_m"]
    equality = {}
    keys = ["state", "initial_state", "time", "transition_time", "environment_wind_I",
            "wind_force_I", "wind_torque_B", "motor_command", "motor_setpoint",
            "requested_generalized", "realized_generalized", "allocated_generalized",
            "position_nominal_acceleration_mps2", "position_compensation_applied_acceleration_mps2",
            "attitude_nominal_torque_Nm", "attitude_compensation_applied_torque_Nm",
            "filtered_attitude_reference", "filtered_attitude_rate", "internal_position_reference",
            "rbf_position_weight_final", "rbf_position_update_flag", "rbf_update_flag"]
    with h5py.File(new["path"], "r") as nf, h5py.File(old["path"], "r") as of:
        ng, og = nf["log"], of["log"]
        keys += ["arms/" + k for k in ng["arms"]]
        keys += ["reference/" + k for k in ng["reference"]]
        for key in keys:
            a, b = np.asarray(ng[key]), np.asarray(og[key])
            assert a.shape == b.shape and np.isfinite(a).all() and np.isfinite(b).all(), key
            assert np.array_equal(a, b), (key, float(np.max(np.abs(a - b))))
            equality[key] = {"stored_shape": list(a.shape), "max_abs_difference": 0.0}
        disabled = ["stage1_position_replacement_enabled", "stage1_position_search_head_enabled",
                    "stage1_position_pcf_coordination_enabled", "stage1_position_delayed_prediction_enabled"]
        for key in disabled:
            assert np.asarray(ng[key]).size == 1 and not np.asarray(ng[key]).item(), key
        assert bool(np.asarray(ng["formal_rbf_baseline"]).item())
        pos_updates = int(np.count_nonzero(np.asarray(ng["rbf_position_update_flag"])))
        att_updates = int(np.count_nonzero(np.asarray(ng["rbf_update_flag"])))
        assert pos_updates == att_updates == 1999
        assert np.count_nonzero(np.asarray(ng["position_compensation_applied_acceleration_mps2"])) > 0
        flags = {k: False for k in disabled}
    result = {"status": "PASS_TRACEABLE_B_REPRODUCES_ONE_HISTORICAL_SCENE_EXACTLY",
              "scene_id": new["scene_id"], "new_Plant": 1, "new_flights_rerun": 0,
              "new_metrics": new_metrics, "old_metrics": old_metrics,
              "compared_cfg_opts_leaves": count, "full_numeric_arrays_equal": equality,
              "B_flags": flags, "position_RBF_updates": pos_updates,
              "attitude_RBF_updates": att_updates, "natural_matlab_OS_exit_code": 0,
              "training_steps": 0, "TEST_accessed": False,
              "historical_72_runtime_tree_gap_closed": False,
              "scope_limit": "Exact complete state/control/external reproduction for this one scene only; does not retroactively prove all historical runtime sources",
              "reuse_limit": "Uses existing reviewed MAT decoder and parent raw metric scorer; fresh hash/config/full-trajectory checks",
              "refs": [{"path": str(p), "sha256": sha(p)} for p in
                       [ledger_path, status_path, release_path, exit_path, lock_path, prep_path,
                        snapshot, manifest_path, reader_path, scorer_path, Path(__file__)]]}
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": result["status"], "Q_m": new_metrics["Q_0_20_m"],
                      "equal_arrays": len(equality), "cfg_opts_leaves": count,
                      "state_samples": 20001, "OS_exit": 0}))


if __name__ == "__main__":
    main()
