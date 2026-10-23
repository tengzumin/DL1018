"""Parent verification of the actual B71 no-Plant evidence before batch release."""
import hashlib
import importlib.util
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
RUN = ROOT / "experiments/b_traceable_c3core_dev72_20261023"


def sha(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def main():
    output = HERE / "PARENT_B71_PREPARE_REVIEW.json"
    assert not output.exists()
    lock_path = RUN / "B_TRACEABLE_DEV72_INPUT_LOCK_v3.json"
    lock = load(lock_path)
    assert sha(lock_path) == "8d738e5c70ba2fc8697550549d1a0537f08eadb49b99bc5684e5c26f6222f452"
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
    b1 = lock["completed_reference"]
    assert lock["active_source_inventory"] == load(b1["input_lock"]["path"])["active_source_inventory"]
    assert len(lock["active_source_inventory"]) == 32
    c3 = load(lock["upstream_refs"]["c3_dev72_input_lock"]["path"])
    ids = sorted(r["scene_id"] for r in c3["scenes"] if r["scene_id"] != b1["scene_id"])
    assert len(ids) == 71 and ids == lock["new_scene_ids"]
    for r in lock["scenes"]:
        old = next(x for x in c3["scenes"] if x["scene_id"] == r["scene_id"])
        assert all(r["B_source"][k] == old["B_source"][k] for k in ("path", "sha256"))
        assert r["external_identity_sha256"] == old["external_identity_sha256"]
    prep_path = RUN / "B_TRACEABLE_DEV72_PREPARE_RESULT_v3.json"
    prep = load(prep_path)
    assert prep["status"] == "PREPARED_NO_PLANT_WAIT_PARENT_RELEASE_V3"
    assert prep["plant_calls"] == 0 and not prep["run_episode_called"] and not prep["TEST_accessed"]
    assert prep["new_scene_count"] == 71 and prep["which_checks"] == 31
    assert prep["input_lock_sha256"] == sha(lock_path)
    snapshot = Path(prep["snapshot_path"])
    assert sha(snapshot) == prep["snapshot_sha256"]
    os_path = RUN / "B_TRACEABLE_DEV72_PREPARE_OS_EXIT_v3.json"
    os_result = load(os_path)
    assert os_result["matlab_os_exit_code"] == 0 and os_result["matlab_called_once"]
    assert os_result["prepare_result_status"] == prep["status"]
    assert sha(os_result["command_file"]) == os_result["command_sha256"]
    assert os_result["input_lock_sha256"] == sha(lock_path)
    reader_path = ROOT / "reports/paper14_v2/phase1/audit_w15_position_replay.py"
    spec = importlib.util.spec_from_file_location("existing_mat_decoder", reader_path)
    reader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    counts = {}
    for section in ("cfg", "opts"):
        actual = reader.flatten(reader.matlab_section(snapshot, section))
        expected = reader.flatten(reader.matlab_section(Path(b1["cfg_opts_snapshot"]["path"]), section))
        assert actual.keys() == expected.keys()
        assert all(reader.same_value(actual[k], expected[k]) for k in actual)
        counts[section] = len(actual)
    assert counts == {"cfg": 120, "opts": 13}
    assert not (RUN / "runs_b").exists() and not (RUN / "B_TRACEABLE_DEV72_RELEASE_v3.json").exists()
    used = sum(p.stat().st_size for p in RUN.rglob("*") if p.is_file())
    free = shutil.disk_usage(ROOT).free
    reserve = 71 * 80000000
    assert used + reserve < 6442450944 and free - reserve > 30000000000
    contract_path = RUN / "B_TRACEABLE_DEV72_RUN_CONTRACT_v3.json"
    contract = load(contract_path)
    result = dict(status="PASS_B71_ACTUAL_PREPARE_SOURCE_SCENE_CFG_OPTS_OS0",
                  verified_unique_path_SHA_refs=len(seen), matching_B1_cfg_opts_leaves=counts,
                  actual_same_B1_active_sources=32, scenes=71, reused_B1=1,
                  no_Plant_prepare_natural_OS_exit=0, new_Plant_in_review=0,
                  per_scene_output_reserve_bytes=80000000, entire_71_reserved_bytes=reserve,
                  current_output_bytes=used, free_bytes=free, TEST_accessed=False,
                  minimum_seconds_per_remaining_scene=contract["limits"]["minimum_seconds_per_remaining_scene"],
                  decoder_limit="Reuses reviewed MAT decoder; fresh whole-tree/hash/path comparisons",
                  batch_exit_scope="One shared MATLAB batch process; per-scene records reference its actual return",
                  refs=[dict(path=str(p), sha256=sha(p)) for p in
                        (lock_path, prep_path, snapshot, os_path, contract_path, reader_path, Path(__file__))])
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: v for k, v in result.items() if k != "refs"}))


if __name__ == "__main__":
    main()
