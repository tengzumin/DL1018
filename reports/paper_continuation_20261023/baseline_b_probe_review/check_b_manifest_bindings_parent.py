"""Verify historical B manifest sidecar bindings without opening trajectories."""
import csv
import hashlib
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    output = HERE / "PARENT_B72_MANIFEST_SIDECAR_BINDING_REVIEW.json"
    assert not output.exists()
    ids_path = HERE.parent / "baseline_b_source_review/SOURCE_IDS.json"
    ids = json.loads(ids_path.read_text(encoding="utf-8-sig"))
    manifest = ROOT.parent / ids["historical_b"]["manifest_path"]
    assert sha(manifest) == ids["historical_b"]["manifest_sha256"]
    metadata = ROOT / ids["historical_b"]["metadata_review"]["path"]
    assert sha(metadata) == ids["historical_b"]["metadata_review"]["sha256"]
    prior = {r["scene_id"]: r for r in json.loads(metadata.read_text(encoding="utf-8-sig"))["rows"]}
    helper = ROOT / "reports/paper14_v2/phase1/audit_w15_position_replay.py"
    module_spec = importlib.util.spec_from_file_location("existing_mat_reader", helper)
    reader = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(reader)
    with manifest.open(encoding="utf-8-sig", newline="") as handle:
        rows = [r for r in csv.DictReader(handle) if r["method_id"] == "B"]
    assert len(rows) == 72
    checked = []
    for row in rows:
        sid = row["source_scene_id"].removesuffix("_ACC_FIX_V1")
        source = ROOT.parent / row["source_run_start_path"]
        assert sha(source) == row["source_run_start_sha256"]
        old = prior[sid]["identities"]["B"]
        sibling = Path(old["path"])
        assert sha(sibling) == old["sha256"]
        counts, omitted = {}, []
        for section in ("cfg", "opts"):
            left = reader.flatten(reader.matlab_section(source, section))
            right = reader.flatten(reader.matlab_section(sibling, section))
            if section == "opts":
                for data in (left, right):
                    if "r2e_first_plant_step_marker" in data:
                        data.pop("r2e_first_plant_step_marker")
                        omitted.append("r2e_first_plant_step_marker")
            assert left.keys() == right.keys(), (sid, section, left.keys() ^ right.keys())
            assert all(reader.same_value(left[k], right[k]) for k in left), (sid, section)
            counts[section] = len(left)
        checked.append({"scene_id": sid, "manifest_source_path": str(source.resolve()),
                        "manifest_source_sha256": row["source_run_start_sha256"],
                        "raw_sibling_path": str(sibling), "raw_sibling_sha256": old["sha256"],
                        "sidecar_bytes_differ": sha(source) != old["sha256"],
                        "compared_leaf_counts": counts, "ignored_noncontrol_field": sorted(set(omitted))})
    assert len({r["scene_id"] for r in checked}) == 72
    result = {"status": "PASS", "B_manifest_source_run_start_SHA_verified": 72,
              "source_vs_raw_sibling_cfg_opts_equal_except_marker": 72,
              "sidecars_with_different_bytes": sum(r["sidecar_bytes_differ"] for r in checked),
              "comparison_reader": "Reuses existing MATLAB section/leaf decoder; independent manifest binding and sidecar comparison, not independent decoder",
              "historical_runtime_tree_gap_closed": False, "new_Plant": 0, "TEST_accessed": False,
              "rows": checked, "refs": [{"path": str(p), "sha256": sha(p)} for p in [manifest, metadata, ids_path, helper, Path(__file__)]]}
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: v for k, v in result.items() if k not in ("rows", "refs")}))


if __name__ == "__main__":
    main()
