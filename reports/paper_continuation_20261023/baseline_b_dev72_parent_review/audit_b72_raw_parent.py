"""Audit only the released B71 batch plus the frozen, already completed B1."""
import csv
import hashlib
import importlib.util
import json
from pathlib import Path

import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
RUN = ROOT / "experiments/b_traceable_c3core_dev72_20261023"
C3 = ROOT / "reports/delayed_prediction_c3_dev72_parent_20261023"
EXPECTED = {
    "B_TRACEABLE_DEV72_RELEASE_v3.json": "f8fd7865a394d7195948d6a47d6769b0c5c64ce28cd0ccc19e9d47d02506f3d1",
    "B_TRACEABLE_DEV72_INPUT_LOCK_v3.json": "8d738e5c70ba2fc8697550549d1a0537f08eadb49b99bc5684e5c26f6222f452",
    "B_TRACEABLE_DEV72_PREPARED_CFG_OPTS_v3.mat": "1736946bf085a4badb3c13662f47c2af25ed88f7cffbe65f0412a9fc3cb8003d",
    "run_b_traceable_dev72_v3.m": "85378c7ee2ef93681c30fae3e756a57487f0da6aae8ca3d98940404d12192b12",
    "RUN_B_TRACEABLE_DEV72_EXACT_v3.ps1": "0dab63188af439a594d8e8cb1f86d236be9671390b1e4459510346de9745f0a7",
}


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def write_json(path, value):
    assert not path.exists(), f"Preserve existing audit: {path}"
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def write_csv(path, rows):
    assert rows and not path.exists()
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def assert_tree(reader, actual, expected):
    left, right = reader.flatten(actual), reader.flatten(expected)
    assert left.keys() == right.keys(), (set(left) - set(right), set(right) - set(left))
    assert all(reader.same_value(left[k], right[k]) for k in left)
    return len(left)


def compare_numeric(new_path, old_path):
    keys = ["state", "initial_state", "time", "transition_time", "environment_wind_I",
            "wind_force_I", "wind_torque_B", "motor_command", "motor_setpoint",
            "requested_generalized", "realized_generalized", "allocated_generalized",
            "position_nominal_acceleration_mps2", "position_compensation_applied_acceleration_mps2",
            "attitude_nominal_torque_Nm", "attitude_compensation_applied_torque_Nm",
            "filtered_attitude_reference", "filtered_attitude_rate", "internal_position_reference",
            "rbf_position_weight_final", "rbf_position_update_flag", "rbf_update_flag"]
    differences = {}
    with h5py.File(new_path, "r") as nf, h5py.File(old_path, "r") as of:
        ng, og = nf["log"], of["log"]
        arm_fields = {"command", "rhoDot_hat", "rhoDot_true", "rho_hat", "rho_true"}
        reference_fields = {"position", "velocity", "acceleration", "yaw", "yaw_rate", "yaw_acceleration"}
        assert set(ng["arms"]) == set(og["arms"]) == arm_fields
        assert set(ng["reference"]) == set(og["reference"]) == reference_fields
        keys += ["arms/" + k for k in sorted(arm_fields)]
        keys += ["reference/" + k for k in sorted(reference_fields)]
        assert len(keys) == len(set(keys)) == 33
        for key in keys:
            a, b = np.asarray(ng[key]), np.asarray(og[key])
            assert a.shape == b.shape and np.isfinite(a).all() and np.isfinite(b).all(), key
            if not np.array_equal(a, b):
                differences[key] = float(np.max(np.abs(a - b)))
        for key in ["stage1_position_replacement_enabled", "stage1_position_search_head_enabled",
                    "stage1_position_pcf_coordination_enabled", "stage1_position_delayed_prediction_enabled"]:
            assert np.asarray(ng[key]).size == 1 and not np.asarray(ng[key]).item(), key
        assert bool(np.asarray(ng["formal_rbf_baseline"]).item())
        assert np.count_nonzero(np.asarray(ng["position_compensation_applied_acceleration_mps2"])) > 0
        for key in ["rbf_position_update_flag", "rbf_update_flag"]:
            assert np.count_nonzero(np.asarray(ng[key])) == 1999, key
        for name in ["rbf_position_event_audit", "rbf_event_audit"]:
            g = ng[name]
            times = np.asarray(g["time"]).ravel()
            weights = np.asarray(g["weight_before"])
            assert len(times) == len(weights) == 8
            assert abs(times[0] - .01) < 1e-12 and np.count_nonzero(weights[0]) == 0
    return len(keys), differences


def main():
    output = HERE / "PARENT_B72_RAW_REVIEW.json"
    assert not output.exists(), "Preserve completed audit"
    refs = {}

    def bind(path, digest=None):
        p = Path(path)
        value = sha(p)
        if digest is not None:
            assert value == digest, p
        refs[str(p.resolve())] = value
        return p

    for name, digest in EXPECTED.items():
        bind(RUN / name, digest)
    lock = read(RUN / "B_TRACEABLE_DEV72_INPUT_LOCK_v3.json")
    release = read(RUN / "B_TRACEABLE_DEV72_RELEASE_v3.json")
    assert release["state"] == "APPROVED_B_TRACEABLE_DEV72_V3"
    assert len(lock["new_scene_ids"]) == len(set(lock["new_scene_ids"])) == 71
    body_path = bind(RUN / "B_TRACEABLE_DEV72_BODY_COMPLETE_v3.json")
    exit_path = bind(RUN / "B_TRACEABLE_DEV72_BATCH_OS_EXIT_v3.json")
    body, batch_exit = read(body_path), read(exit_path)
    assert body["status"] == batch_exit["body_complete_status"] == "RUN_COMPLETE_RAW_PENDING_AUDIT"
    assert body["completed_scene_count"] == body["plant_calls"] == batch_exit["completed_scene_count"] == 71
    assert batch_exit["matlab_os_exit_code"] == 0 and batch_exit["attempted_scene_count"] == 71
    assert batch_exit["exit_scope"] == "SHARED_BATCH_PROCESS"
    assert not body["TEST_accessed"] and body["training_steps"] == body["optimizer_steps"] == 0
    for key, name in [("input_lock_sha256", "B_TRACEABLE_DEV72_INPUT_LOCK_v3.json"),
                      ("release_sha256", "B_TRACEABLE_DEV72_RELEASE_v3.json"),
                      ("cfg_opts_snapshot_sha256", "B_TRACEABLE_DEV72_PREPARED_CFG_OPTS_v3.mat"),
                      ("runner_sha256", "run_b_traceable_dev72_v3.m"),
                      ("run_command_sha256", "RUN_B_TRACEABLE_DEV72_EXACT_v3.ps1")]:
        assert body[key] == EXPECTED[name]
    assert batch_exit["release_sha256"] == EXPECTED["B_TRACEABLE_DEV72_RELEASE_v3.json"]
    assert batch_exit["command_sha256"] == EXPECTED["RUN_B_TRACEABLE_DEV72_EXACT_v3.ps1"]
    for item in lock["active_source_inventory"]:
        bind(item["path"], item["sha256"])
    assert len(lock["active_source_inventory"]) == 32

    old_manifest = bind(C3 / "PARENT_HISTORICAL_216_MANIFEST.json",
                        "8ba7c412452f35a727c862ec6ff5e7fa932d2c34d084574ce756bf63e5308dfe")
    c3_manifest = bind(C3 / "PARENT_C3_ALL72_RAW_MANIFEST.json",
                       "4d23aa8fb74d506151e7159a07027ad474e2b080d1448ba4d0a3e056b9ea8aa6")
    old = {r["scene_id"]: r for r in read(old_manifest)["rows"] if r["method"] == "B"}
    c3_raw = {r["scene_id"]: r for r in read(c3_manifest)["rows"]}
    assert len(old) == len(c3_raw) == 72 and old.keys() == c3_raw.keys()
    scorer_path = bind(C3 / "parent_raw_metrics.py",
                       "c64482d0adbc4358417648ec08351bd78f1d3dbdb38950435fa71b9cb0f531b1")
    reader_path = bind(ROOT / "reports/paper14_v2/phase1/audit_w15_position_replay.py",
                       "372d92cb17da99884e742d3fa0c877200c3bb2bc6fac7f10e7a1a046b97a76af")
    scorer, reader = module(scorer_path, "existing_parent_metrics"), module(reader_path, "existing_mat_reader")
    snapshot = RUN / "B_TRACEABLE_DEV72_PREPARED_CFG_OPTS_v3.mat"
    cfg, opts = reader.matlab_section(snapshot, "cfg"), reader.matlab_section(snapshot, "opts")
    source_identity = reader.matlab_section(snapshot, "sourceIdentity")
    exits = {r["scene_id"]: r for r in batch_exit["scene_os_exit_records"]}
    completed = {r["scene_id"]: r for r in body["completed_scenes"]}
    assert len(exits) == len(completed) == 71 and exits.keys() == completed.keys() == set(lock["new_scene_ids"])
    b1 = lock["completed_reference"]
    for role in ["run_status", "raw", "run_start", "os_exit", "parent_raw_root_review", "execution_ledger"]:
        bind(b1[role]["path"], b1[role]["sha256"])
    b1_status = read(b1["run_status"]["path"])
    assert read(b1["parent_raw_root_review"]["path"])["status"] == "PASS_TRACEABLE_B_REPRODUCES_ONE_HISTORICAL_SCENE_EXACTLY"
    assert read(b1["execution_ledger"]["path"])["os_exit_code"] == 0
    all_statuses = {b1["scene_id"]: (b1_status, Path(b1["run_status"]["path"]))}
    for sid, row in completed.items():
        status_path = bind(row["status_path"], row["status_sha256"])
        status = read(status_path)
        assert status["scene_id"] == sid and status["raw_sha256"] == row["raw_sha256"]
        exit_ref = exits[sid]
        scene_exit = read(bind(exit_ref["path"], exit_ref["sha256"]))
        assert scene_exit["matlab_os_exit_code"] == 0
        assert scene_exit["exit_scope"] == "SHARED_BATCH_PROCESS_NOT_INDIVIDUAL_SCENE_PROCESS"
        assert scene_exit["status_sha256"] == sha(status_path)
        assert scene_exit["command_sha256"] == EXPECTED["RUN_B_TRACEABLE_DEV72_EXACT_v3.ps1"]
        assert scene_exit["raw_sha256_from_status"] == status["raw_sha256"]
        assert status["release_sha256"] == EXPECTED["B_TRACEABLE_DEV72_RELEASE_v3.json"]
        assert status["input_lock_sha256"] == EXPECTED["B_TRACEABLE_DEV72_INPUT_LOCK_v3.json"]
        assert status["cfg_opts_snapshot_sha256"] == EXPECTED["B_TRACEABLE_DEV72_PREPARED_CFG_OPTS_v3.mat"]
        for key in ["contract_sha256", "prepare_result_sha256"]:
            assert status[key] == body[key] == release[key]
        all_statuses[sid] = status, status_path
    assert all_statuses.keys() == old.keys()
    metrics, manifest_rows, comparisons = [], [], []
    for i, sid in enumerate(sorted(all_statuses)):
        status, status_path = all_statuses[sid]
        assert status["status"] == "RUN_COMPLETE_RAW_PENDING_AUDIT" and status["plant_calls"] == 1
        assert status["transitions"] == 20000 and status["state_samples"] == 20001
        assert status["training_steps"] == 0 and not status["TEST_accessed"]
        for pkey, hkey in [("raw_path", "raw_sha256"), ("run_start_path", "run_start_sha256"),
                           ("first_plant_step_marker_path", "first_plant_step_marker_sha256")]:
            bind(status[pkey], status[hkey])
        if "attempt_started_marker_path" in status:
            bind(status["attempt_started_marker_path"], status["attempt_started_marker_sha256"])
        start = reader.matlab_section(Path(status["run_start_path"]), "runStart")
        leaves_cfg = assert_tree(reader, start["cfg"], cfg)
        actual_opts = reader.flatten(start["opts"])
        assert "r2e_first_plant_step_marker" in actual_opts
        actual_opts.pop("r2e_first_plant_step_marker")
        expected_opts = reader.flatten(opts)
        assert actual_opts.keys() == expected_opts.keys()
        assert all(reader.same_value(actual_opts[k], expected_opts[k]) for k in actual_opts)
        assert leaves_cfg == 120 and len(actual_opts) == 13
        if sid != b1["scene_id"]:
            assert_tree(reader, start["source_identity"], source_identity)
        new = dict(scene_id=sid, method="B_TRACEABLE", path=status["raw_path"], sha256=status["raw_sha256"])
        nm, om = scorer.score(new), scorer.score(old[sid])
        bind(old[sid]["path"], old[sid]["sha256"])
        assert nm["external_identity_sha256"] == om["external_identity_sha256"]
        n_arrays, differences = compare_numeric(new["path"], old[sid]["path"])
        comparisons.append(dict(scene_id=sid, numeric_arrays=n_arrays, all_arrays_equal=not differences,
                                differing_arrays=differences, Q_new_minus_old_m=nm["Q_0_20_m"] - om["Q_0_20_m"],
                                cfg_leaves=leaves_cfg, opts_leaves=13,
                                position_and_attitude_initial_weight_zero=True, RBF_updates_per_loop=1999))
        metrics.append(nm)
        manifest_rows.append(dict(**new, status_path=str(status_path), status_sha256=sha(status_path),
                                  external_identity_sha256=nm["external_identity_sha256"],
                                  reused_B1=sid == b1["scene_id"]))
        print(json.dumps(dict(progress=i + 1, scene_id=sid, equal=not differences)), flush=True)

    csv_path = bind(C3 / "PARENT_ALL288_METRICS.csv",
                    "acf0e3137ab171a8801a0a7672515a17ca85e8a16c1e067512c261c49ddbcd11")
    with csv_path.open(encoding="utf-8-sig", newline="") as stream:
        c3 = {r["scene_id"]: r for r in csv.DictReader(stream) if r["method"] == "C3"}
    assert c3.keys() == old.keys()
    paired = []
    for bm in metrics:
        sid = bm["scene_id"]
        cm = c3[sid]
        assert cm["sha256"] == c3_raw[sid]["sha256"]
        assert cm["external_identity_sha256"] == bm["external_identity_sha256"]
        delta = bm["Q_0_20_m"] - float(cm["Q_0_20_m"])
        paired.append(dict(scene_id=sid, B_Q_m=bm["Q_0_20_m"], C3_Q_m=float(cm["Q_0_20_m"]),
                           improvement_m=delta, C3_win=delta > 1e-12, C3_loss=delta < -1e-12,
                           C3_win_gt_1um=delta > 1e-6, C3_win_gt_10um=delta > 1e-5))
    groups = []
    predicates = [("ALL72", lambda s: True), ("HF_W09_W14", lambda s: 9 <= int(s[-2:]) <= 14),
                  ("W15", lambda s: s.endswith("W15"))]
    predicates += [(f"T{t}", lambda s, t=t: f"_T{t}_" in s) for t in [1, 2, 3]]
    for group, predicate in predicates:
        part = [r for r in paired if predicate(r["scene_id"])]
        groups.append(dict(group=group, n=len(part), wins=sum(r["C3_win"] for r in part),
                           losses=sum(r["C3_loss"] for r in part),
                           wins_gt_1um=sum(r["C3_win_gt_1um"] for r in part),
                           wins_gt_10um=sum(r["C3_win_gt_10um"] for r in part),
                           B_Q_mean_m=float(np.mean([r["B_Q_m"] for r in part])),
                           C3_Q_mean_m=float(np.mean([r["C3_Q_m"] for r in part]))))
    all_equal = all(r["all_arrays_equal"] and r["Q_new_minus_old_m"] == 0 for r in comparisons)
    status = "PASS_NEW_B72_TRACEABLE_EXACTLY_REPRODUCES_HISTORICAL_B" if all_equal else "REVIEW_REQUIRED_NEW_B_DIFFERS_FROM_HISTORICAL_B"
    write_csv(HERE / "PARENT_B72_METRICS.csv", metrics)
    write_csv(HERE / "PARENT_C3_VS_TRACEABLE_B72.csv", paired)
    write_csv(HERE / "PARENT_C3_VS_TRACEABLE_B72_GROUPS.csv", groups)
    write_csv(HERE / "PARENT_C3_ALL_LOSSES_VS_TRACEABLE_B.csv", [r for r in paired if r["C3_loss"]])
    manifest_path = HERE / "PARENT_TRACEABLE_B72_MANIFEST.json"
    write_json(manifest_path, dict(scope="DEV72_ONLY_TRACEABLE_B1_PLUS_B71_NO_TEST", status=status,
                                  release_sha256=EXPECTED["B_TRACEABLE_DEV72_RELEASE_v3.json"],
                                  new_Plant_in_this_audit=0, reused_B1=1, new_B71=71, rows=manifest_rows))
    result = dict(status=status, new_Plant_in_this_audit=0, actual_new_batch_Plant=71, reused_B1=1,
                  scene_count=72, fresh_new_and_old_raw_reads=144, comparisons=comparisons, groups=groups,
                  manifest_path=str(manifest_path), manifest_sha256=sha(manifest_path),
                  all_new_source_inventory_sha_verified=True, cfg_opts_actual_leaves_per_scene=[120, 13],
                  position_and_attitude_RBF_initial_weights_zero_in_all_72=True,
                  scene_exit_scope="71_SCENES_SHARE_ONE_BATCH_OS0; B1_SEPARATE_PRIOR_OS0",
                  TEST_accessed=False, training_steps=0, historical_runtime_identity_gap_closed=False,
                  scope_limit="New B72 has complete frozen runtime identity. Exact reproduction does not retroactively attest historical runtime sources.",
                  C3_reuse="Frozen parent-audited C3 metrics and raw manifest reused; C3 raw not reread by this script.",
                  decoder_and_scorer_reuse="Existing reviewed MAT decoder and parent raw scorer; fresh cfg, weights, complete state/control comparisons.",
                  timing_qualification="NONISOLATED_NOT_FORMAL",
                  refs=[dict(path=p, sha256=d) for p, d in refs.items()] + [dict(path=str(Path(__file__).resolve()), sha256=sha(__file__))])
    write_json(output, result)
    print(json.dumps(dict(status=status, scenes=72, groups=groups), ensure_ascii=False))


if __name__ == "__main__":
    main()
