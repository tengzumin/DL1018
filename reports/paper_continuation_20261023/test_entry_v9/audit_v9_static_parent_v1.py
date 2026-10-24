"""Root static source review; never decodes TEST outcomes or starts MATLAB."""
import datetime
import difflib
import hashlib
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[3]
OUT = pathlib.Path(__file__).resolve().parent
EXP = ROOT / "experiments/c5_test48_v9"


def sha(path):
    h = hashlib.sha256()
    with pathlib.Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8-sig"))


def resolve(path):
    p = pathlib.Path(path)
    return p if p.is_absolute() else ROOT / p


def function(text, name):
    parts = re.split(r"(?m)(?=^function\b)", text)
    matches = [p for p in parts if p and re.search(r"\b" + name + r"\s*\(", p.splitlines()[0])]
    assert len(matches) == 1, name
    return matches[0]


def main():
    c = read(EXP / "TEST48_RUN_CONTRACT_v4.json")
    mpath = resolve(c["method_source_manifest_path"])
    m = read(mpath)
    oldc = read(ROOT / "experiments/c5_test48_v8/TEST48_RUN_CONTRACT_v4.json")
    oldm = read(ROOT / "reports/paper_continuation_20261023/test_entry_v8/TEST_METHOD_SOURCE_MANIFEST_v4.json")
    for key in ["method_order", "engineering_dev2", "v3_frozen_inputs", "execution", "limits", "global_platform_lock_sha256", "global_platform_ref_count"]:
        assert c[key] == oldc[key], key
    for key in ["methods", "shared_source_refs", "engineering_dev2", "v3_frozen_inputs", "v3_unstarted_guard", "global_platform_refs", "global_platform_lock_sha256", "v4_execution"]:
        assert m[key] == oldm[key], key
    assert mpath == OUT / "TEST_METHOD_SOURCE_MANIFEST_v4.json"
    assert c["taskbook_path"].endswith("TEST_STAGE_PATH_CONTRACT_REPAIR_TASKBOOK_v2_ZH.md")
    assert c["code_only_release_path"].endswith("TEST_STAGE_PATH_CONTRACT_REPAIR_CODE_ONLY_RELEASE_v2.json")
    entry = EXP / "test48_entry_v4.m"
    launcher = EXP / "RUN_TEST48_EXACT_v1.ps1"
    text = entry.read_text()
    oldtext = (ROOT / "experiments/c5_test48_v8/test48_entry_v4.m").read_text()
    protected = ["run_one_method", "compare_raw_tree", "compare_engineering_raw", "bind_method_path", "verify_global_platform_which", "prepare_no_plant"]
    for name in protected:
        assert function(text, name) == function(oldtext, name), name
    stage = function(text, "verify_stage_release")
    expected = function(oldtext, "verify_stage_release").replace(
        "taskbookPath=fullfile(root,'reports','paper_continuation_20261023','TEST_UNSTARTED_DEPENDENCY_REPAIR_TASKBOOK_v4_ZH.md');",
        "contract=jsondecode(fileread(contractPath));\ntaskbookPath=repo_path(root,char(contract.taskbook_path));")
    assert stage == expected, "stage helper changed beyond path resolution"
    identity = function(text, "read_method_contract")
    for fragment in ["expected='CORRECTED_TRAIN_DSSM14_G12_R32'; deployed='DSSM14_G12_R32';", "expected='CORRECTED_TRAIN_KAN14_G12_R32'; deployed='NEW_KAN14_G12_R32';", "methodContract=struct('candidate',deployed,'collector_tag',deployed);", "assert(strcmp(actual,expected)", "Unknown corrected method identity"]:
        assert fragment in identity, fragment
    ps = launcher.read_text()
    for fragment in ["test_entry_v9'", "TEST_STAGE_PATH_CONTRACT_REPAIR_TASKBOOK_v2_ZH.md'", "TEST_STAGE_PATH_CONTRACT_REPAIR_CODE_ONLY_RELEASE_v2.json'", "addpath('experiments/c5_test48_v9')"]:
        assert fragment in ps, fragment
    checked = []
    cache = {}

    def refs(obj, where):
        if isinstance(obj, dict):
            for key, value in obj.items():
                pair = "sha256" if key == "path" else key[:-5] + "_sha256" if key.endswith("_path") else None
                if pair and value and isinstance(value, str) and pair in obj and re.fullmatch("[0-9a-fA-F]{64}", str(obj[pair])):
                    p = resolve(value)
                    assert p.is_file() or (key == "runtime_tree_path" and p.is_dir()), (where, key, str(p))
                    if p not in cache:
                        if p.is_dir():
                            files = sorted(p.rglob("*.m"), key=lambda q: q.name)
                            assert len({q.name for q in files}) == len(files), "ambiguous tree filename ordering"
                            canonical = "".join(str(q) + ":" + sha(q) + "\n" for q in files)
                            cache[p] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
                        else:
                            cache[p] = sha(p)
                    assert cache[p] == obj[pair].lower(), (where, key, str(p))
                    checked.append({"location": where + "." + key, "path": str(p), "sha256": cache[p]})
                refs(value, where + "." + key)
        elif isinstance(obj, list):
            for i, value in enumerate(obj):
                refs(value, f"{where}[{i}]")

    refs(c, "contract")
    refs(m, "manifest")
    assert sha(entry) == c["entry_sha256"] and sha(launcher) == c["launcher_sha256"]
    assert sha(mpath) == c["method_source_manifest_sha256"]
    result = {"schema": "PARENT_V9_SOURCE_REVIEW_V1", "status": "PASS_STATIC_SOURCE_PATH_AND_CORRECTED_METADATA_MAPPING", "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "taskbook_sha256": c["taskbook_sha256"], "entry_sha256": sha(entry), "launcher_sha256": sha(launcher), "contract_sha256": sha(EXP / "TEST48_RUN_CONTRACT_v4.json"), "method_source_manifest_sha256": sha(mpath),
              "actual_reference_pairs_checked": len(checked), "unique_files_checked": len(cache), "protected_functions_normalized_EOL_exact": protected,
              "six_methods_models_engineering_frozen_inputs_scientific_limits_unchanged": True, "historical_metadata_and_deployed_collector_separate": True,
              "stage_helper_only_contract_taskbook_resolution_changed": True, "MATLAB_started": False, "TEST_outcomes_accessed": False, "references": checked}
    target = OUT / "PARENT_V9_SOURCE_REVIEW_v1.json"
    assert not target.exists()
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "PARENT_V8_V9_ENTRY_DIFF_v1.txt").write_text("".join(difflib.unified_diff(oldtext.splitlines(True), text.splitlines(True), fromfile="v8", tofile="v9")), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "references"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
