"""Seal the audited new B comparator and release exactly one C5 pilot."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
RUN = ROOT / "experiments/position_axis_coordinate_c5_20261023"
B = HERE.parent / "baseline_b_dev72_parent_review"


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def ref(path):
    return dict(path=str(Path(path).resolve()), sha256=sha(path))


def write(path, value):
    assert not path.exists(), path
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def main():
    release_path = RUN / "C5_FIRST_PARENT_RELEASE_v1.json"
    assert not release_path.exists() and not list(RUN.rglob("first_plant_step.marker"))
    lock_path = RUN / "C5_AXIS_COORDINATE_INPUT_LOCK_v1.json"
    assert sha(lock_path) == "10a7eea144e3574e05eea7b4f7b56112595eac0c81d27b5e8c7a5a41499f84b0"
    lock = load(lock_path)
    binding_path = RUN / "C5_SOURCE_BINDING_v1.json"
    assert sha(binding_path) == "8a8a77e3058c58eccaf5156277734567190888dc5806bf210f43dc19844872ac"
    for item in load(binding_path)["file_refs"]:
        assert sha(item["path"]) == item["sha256"]
    bp = B / "PARENT_B72_RAW_REVIEW.json"
    bm = B / "PARENT_TRACEABLE_B72_MANIFEST.json"
    baseline = load(bp)
    assert baseline["status"] == "PASS_NEW_B72_TRACEABLE_EXACTLY_REPRODUCES_HISTORICAL_B"
    assert baseline["scene_count"] == 72 and baseline["manifest_sha256"] == sha(bm)
    assert baseline["position_and_attitude_RBF_initial_weights_zero_in_all_72"]
    assert all(r["all_arrays_equal"] and r["numeric_arrays"] == 33 for r in baseline["comparisons"])
    assert baseline["actual_new_batch_Plant"] == 71 and baseline["reused_B1"] == 1
    c3_lock = load(lock["upstream_refs"]["c3_input_lock"]["path"])
    by_id = {r["scene_id"]: r for r in load(bm)["rows"]}
    ids = c3_lock["scene_ids_all_72"]
    assert len(ids) == len(by_id) == 72 and set(ids) == by_id.keys()
    records = [dict(scene_id=sid, raw_path=by_id[sid]["path"], raw_sha256=by_id[sid]["sha256"],
                    run_status_path=by_id[sid]["status_path"], run_status_sha256=by_id[sid]["status_sha256"], plant_calls=1)
               for sid in ids]
    manifest_path = HERE / "C5_B72_SCORING_MANIFEST_v1.json"
    review_path = HERE / "C5_B72_INPUT_PARENT_ATTESTATION_v1.json"
    write(manifest_path, dict(schema="C5_B72_SCORING_MANIFEST_V1", state="PASS_C5_B72_ALL72_PARENT_AUDIT",
                              records=records, canonical_manifest=ref(bm), canonical_parent_audit=ref(bp),
                              historical_runtime_provenance_retroactively_attested=False))
    write(review_path, dict(status="PASS_C5_B72_ALL72_PARENT_AUDIT", complete_scene_count=72,
                            scope="C5 input-identity attestation backed by the actual complete new B72 raw audit; no C5 performance claim",
                            canonical_parent_audit=ref(bp), canonical_manifest=ref(bm),
                            C5_scoring_manifest=ref(manifest_path), new_Plant=0, TEST_accessed=False,
                            all_complete_state_control_arrays_equal_to_historical_B=True,
                            historical_runtime_provenance_retroactively_attested=False))
    prep_path = RUN / "C5_AXIS_COORDINATE_PREPARE_RESULT_v1.json"
    prep = load(prep_path)
    pr = HERE / "PARENT_C5_PREPARE_REVIEW.json"
    assert load(pr)["status"] == "PASS_PREPARED_C5_M110_SOURCE_INPUT_AND_CROSSLANGUAGE_BINDINGS"
    assert load(pr)["natural_MATLAB_OS_exit"] == 0 and prep["plant_calls"] == 0
    contract_path = RUN / "C5_AXIS_COORDINATE_RUN_CONTRACT_v1.json"
    contract = load(contract_path)
    template = load(RUN / "C5_FIRST_PARENT_RELEASE_CONTRACT_v1.json")
    first = next(r for r in records if r["scene_id"] == lock["first_scene_id"])
    physical = next(r for r in lock["scenes"] if r["scene_id"] == lock["first_scene_id"])
    release = dict(template["required_values"])
    bbody = ROOT / "experiments/b_traceable_c3core_dev72_20261023/B_TRACEABLE_DEV72_BODY_COMPLETE_v3.json"
    release.update(schema=template["parent_release_schema"], state=template["required_release_state"],
                   c5_source_binding_sha256=sha(binding_path), c5_runner_path=lock["source_files"]["single_scene_runner"]["path"],
                   c5_runner_sha256=lock["source_files"]["single_scene_runner"]["sha256"],
                   first_launcher_sha256=lock["source_files"]["first_scene_launcher"]["sha256"],
                   c5_input_lock_sha256=sha(lock_path), c5_run_contract_sha256=sha(contract_path),
                   c5_prepare_result_sha256=sha(prep_path), c5_snapshot_sha256=sha(prep["snapshot_path"]),
                   scene_id=lock["first_scene_id"], b72_first_scene_status_sha256=first["run_status_sha256"],
                   b72_first_scene_status_path=first["run_status_path"], b72_first_scene_raw_sha256=first["raw_sha256"],
                   b72_first_scene_raw_path=first["raw_path"], physical_B_source_sha256=physical["B_source"]["sha256"],
                   c3_dev72_input_lock_sha256=lock["c3_dev72_input_lock_sha256"],
                   b72_input_lock_sha256=lock["upstream_refs"]["b72_input_lock"]["sha256"],
                   b72_run_contract_sha256=lock["upstream_refs"]["b72_run_contract"]["sha256"],
                   b72_prepare_result_sha256=lock["upstream_refs"]["b72_prepare_result"]["sha256"],
                   b72_release_sha256=lock["upstream_refs"]["b72_release"]["sha256"],
                   b72_batch_status_path=str(bbody), b72_batch_status_sha256=sha(bbody),
                   b72_parent_review_path=str(review_path), b72_parent_review_sha256=sha(review_path),
                   b72_raw_manifest_path=str(manifest_path), b72_raw_manifest_sha256=sha(manifest_path),
                   created_utc=datetime.now(timezone.utc).isoformat())
    assert set(template["required_fields"]) <= release.keys()
    assert all(release[k] == v for k, v in template["required_values"].items())
    assert prep["snapshot_sha256"] == release["c5_snapshot_sha256"]
    assert datetime.now(timezone.utc).isoformat() < contract["limits"]["deadline_utc"]
    release["parent_review_and_validation_refs"] = [ref(p) for p in [
        pr, HERE / "C5_ALGORITHM_PARENT_REVIEW_v1.json", HERE / "C5_NOPLANT_SOURCE_PARENT_REVIEW_v1.json",
        HERE / "check_c5_prepare_parent.py", HERE / "check_c5_raw_parent.py", bp, bm, review_path, manifest_path,
        HERE.parent / "c5_axis_coordinate_execution/C5_NOPLANT_EXECUTION_RECEIPT_v1.json", Path(__file__)]]
    release["execution_environment"] = dict(shell="PowerShell7", MATLAB_PREFDIR=str(RUN / "matlab_prefdir_first_v1"),
                                              stdout_path=str(HERE.parent / "c5_axis_coordinate_execution/C5_FIRST_STDOUT_v1.txt"))
    release["no_extension_rule"] = "Only one pilot. Root raw all-event/metadata/OS audit is required before any tail11 release. No training or TEST."
    write(release_path, release)
    print(json.dumps(dict(status=release["state"], release_sha256=sha(release_path), scene=release["scene_id"], max_new_Plant=1)))


if __name__ == "__main__":
    main()
