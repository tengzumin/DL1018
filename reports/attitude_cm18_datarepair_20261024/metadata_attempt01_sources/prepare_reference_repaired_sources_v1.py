from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path

SCHEMA = "CM18_REFERENCE_REPAIRED_SOURCE_MANIFEST_V1"
TASKBOOK = "reports/attitude_cm18_datarepair_20261024/ROOT_REFERENCE_REPAIR_DATA_TASKBOOK_v1_ZH.md"
INPUT = "reports/attitude_cm18_a1_20261024/data_preparation_v1/INPUT_MANIFEST_v1.json"
A1_DATASET = "reports/attitude_cm18_a1_20261024/data_preparation_v1/events_all816_v1/DATASET_MANIFEST_v1.json"
LINEAGE = "reports/attitude_position_context_probe_20261024/ROOT_T2_REFERENCE_DATA_LINEAGE_AUDIT_v1.json"
VAL_CANDIDATES = "reports/attitude_position_context_probe_20261024/C5_MATCHED_VAL_REUSE_CANDIDATES_v1.json"
C5_LOCK = "experiments/position_axis_coordinate_c5_dev72_20261023/C5_DEV72_INPUT_LOCK_v3.json"
EXTRACTOR = "experiments/attitude_cm18_datarepair_20261024/extract_cm18_events_v1.m"
PREPARE_SCRIPT = "experiments/attitude_cm18_datarepair_20261024/prepare_reference_repaired_sources_v1.py"
EXPORTER = "experiments/attitude_cm18_datarepair_20261024/export_reference_repaired_t2_events_v1.m"
OUTPUT = "reports/attitude_cm18_datarepair_20261024/B_REF_REPAIRED_SOURCE_MANIFEST_v1.json"
TRAIN_OPTS_AUDIT = "reports/attitude_cm18_datarepair_20261024/ROOT_CORRECTED_T2_TRAIN256_B_CFG_OPTS_AUDIT_v1.json"

PINNED = {
    TASKBOOK: "452c23426cd42bb297094b13b04316f7d2d2b1cb1f4c4f71040e38cba607a199",
    INPUT: "a5f7fea9b0918c1449af6fa83929177d3bf7d5e70cb3b71711c40f6338d210a5",
    A1_DATASET: "7dd3e1f786f6095ecc2ba56473e5cf0fab6b92cdd42e38a184d6ad1223f36271",
    LINEAGE: "b193ae3f0e3dc0af57bd5fb976695f083e4c35173d2058439268ba82fa4844b2",
    VAL_CANDIDATES: "80ef7a37cb0fff237086ccc138772c71494cacd50a916ed2dba4037d4f833494",
    C5_LOCK: "82024c01276cc4bfbd9b7772cf5332dee3dfcfbed422969589b68f1c90ed2d75",
    EXTRACTOR: "15d8fb369b93e3a251d70c7eb7a590f732da839d35a5bebfb2011f25123e37c1",
    TRAIN_OPTS_AUDIT: "84e70c7df9af05c49ecb9d5acaa4c042a62283905ac00f1ddd44ffe9ae19b58d",
}
G3_INDEX_SHA = "3c8291c12628acfb9d950fb67cb84b56fe09cdaeaeac38706e8903291873e84e"
G3_COHORT_SHA = "2502e832e6719f7c83c8d7dfe1c0b778560cdd2c7ac5daafcaf480e0628d4588"
INPUT_SHA = PINNED[INPUT]
ALLOWED_G3_STATUS = {"RUN_COMPLETE_STABLE", "PILOT6_VALIDATED"}
ALLOWED_G3_ACTION = {"RUN_PLANT", "PILOT6_IMPORT"}
CACHE_ROOT = "data/events/attitude_cm18_datarepair_20261024"
SCREEN4 = {
    "DL1018_TRAIN_T2_C00_W00",
    "DL1018_TRAIN_T2_C15_W14",
    "DL1018_VAL_T2_C00_W10",
    "DL1018_VAL_T2_C15_W09",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def norm_path(value: str) -> str:
    return os.path.normcase(os.path.normpath(str(value))).replace("/", "\\")


def repo_file(root: Path, relative: str) -> Path:
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"unsafe repository-relative path: {relative}")
    path = (root / rel).resolve(strict=True)
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"path escaped repository: {relative}")
    return path


def source_file(root: Path, value: str) -> Path:
    path = Path(value).resolve(strict=True)
    return path


def file_record(path: Path, expected_sha: str | None = None) -> dict:
    if not path.is_file():
        raise FileNotFoundError(path)
    size = path.stat().st_size
    if size <= 0:
        raise ValueError(f"empty source file: {path}")
    actual_sha = sha256(path) if expected_sha is None else expected_sha.lower()
    if expected_sha is not None and (len(actual_sha) != 64 or any(c not in "0123456789abcdef" for c in actual_sha)):
        raise ValueError(f"invalid recorded SHA-256: {path}")
    return {"path": str(path), "size_bytes": size, "sha256": actual_sha,
            "sha256_origin": "computed_file_hash" if expected_sha is None else "pinned_source_record_not_rehashed"}


def a1_roles(scene: dict) -> dict:
    result = {x["role"]: x for x in scene["files"]}
    if set(result) != {"event_h5", "raw_run", "run_start"}:
        raise ValueError(f"unexpected A1 input roles: {scene['scene_id']}")
    return result


def check_metadata_pins(root: Path) -> tuple[dict, dict, dict, dict, dict, Path]:
    for rel, expected in PINNED.items():
        path = repo_file(root, rel)
        if sha256(path) != expected:
            raise ValueError(f"pinned input changed: {rel}")
    inp = load_json(repo_file(root, INPUT))
    old = load_json(repo_file(root, A1_DATASET))
    lineage = load_json(repo_file(root, LINEAGE))
    candidates = load_json(repo_file(root, VAL_CANDIDATES))
    c5_lock = load_json(repo_file(root, C5_LOCK))
    train_audit = load_json(repo_file(root, TRAIN_OPTS_AUDIT))
    if inp.get("schema") != "ATTITUDE_CM18_A1_INPUT_MANIFEST_V1" or len(inp.get("scenes", [])) != 816:
        raise ValueError("A1 input manifest schema/count mismatch")
    if old.get("schema") != "CM18_A1_DATASET_MANIFEST_V1" or old.get("mode") != "ALL816":
        raise ValueError("A1 ALL816 dataset manifest schema/mode mismatch")
    if old.get("input_manifest_sha256") != INPUT_SHA or len(old.get("rows", [])) != 816:
        raise ValueError("A1 ALL816 dataset manifest identity/count mismatch")
    if old.get("scene_count") != 816 or old.get("qualified_count") != 816 or old.get("failed_count") != 0 or old.get("TEST_accessed"):
        raise ValueError("A1 ALL816 manifest is not fully PASS or accessed TEST")
    if any(r.get("status") != "PASS" or not r.get("qualified") for r in old["rows"]):
        raise ValueError("A1 ALL816 contains a non-PASS cache row")
    if lineage.get("schema") != "ROOT_T2_REFERENCE_DATA_LINEAGE_AUDIT_V1":
        raise ValueError("unexpected T2 lineage schema")
    idx_pin = lineage.get("pins", {}).get("CORRECTED_T2_TRAIN_INDEX", {})
    if idx_pin.get("sha256", "").lower() != G3_INDEX_SHA:
        raise ValueError("lineage G3 index SHA pin mismatch")
    g3_path = Path(idx_pin.get("path", "")).resolve(strict=True)
    if sha256(g3_path) != G3_INDEX_SHA:
        raise ValueError("external G3 index file SHA mismatch")
    g3_cohort_path = g3_path.parent.parent / "manifests" / "G3_COHORT_1632.csv"
    if sha256(g3_cohort_path) != G3_COHORT_SHA:
        raise ValueError("G3 cohort manifest SHA mismatch")
    state_pin = lineage.get("pins", {}).get("CORRECTED_TRAIN_STATE", {})
    pilot_state_path = Path(state_pin.get("path", "")).resolve(strict=True)
    if not state_pin.get("sha256") or sha256(pilot_state_path) != state_pin["sha256"].lower():
        raise ValueError("corrected training state SHA mismatch")
    fixed_helper = lineage.get("pins", {}).get("FIXED_FORMULA_HELPER", {})
    if fixed_helper.get("sha256", "").lower() != "ce7f1b680155ec0bff8a70dc3794c00898e4c3e7befa7d09c50160b7aabdf26e":
        raise ValueError("corrected reference helper SHA mismatch")
    helper_path = source_file(root, fixed_helper["path"])
    if sha256(helper_path) != fixed_helper["sha256"].lower():
        raise ValueError("corrected reference helper source changed")
    snapshot = lineage.get("cfg_opts_check", {}).get("C5_snapshot_path")
    if not snapshot or sha256(source_file(root, snapshot)) != "842ef395569e675db6e139c2684d72b976946915e5e0a58b9b7f24ec10c1d24a":
        raise ValueError("C5 cfg/opts snapshot pin mismatch")
    if candidates.get("schema") != "ROOT_C5_MATCHED_VAL_REUSE_CANDIDATES_V1":
        raise ValueError("unexpected VAL candidate schema")
    if c5_lock.get("schema") != "C5_AXIS_COORDINATE_DEV72_INPUT_LOCK_V3":
        raise ValueError("unexpected C5 input lock schema")
    if (train_audit.get("schema") != "ROOT_CORRECTED_T2_TRAIN256_B_CFG_OPTS_AUDIT_V1"
            or train_audit.get("all256_pass") is not True or len(train_audit.get("rows", [])) != 256
            or any(r.get("cfg_exact") is not True or r.get("B_opts_exact_except_marker") is not True
                   or r.get("different_option_fields") != [] for r in train_audit["rows"])):
        raise ValueError("the pinned 256-scene B cfg/opts audit is not a full exact PASS")
    return inp, old, lineage, candidates, train_audit, g3_path


def build_rows(root: Path, inp: dict, old: dict, lineage: dict, candidates: dict,
               train_audit: dict, g3_path: Path) -> list[dict]:
    old_by_id = {r["scene_id"]: r for r in old["rows"]}
    inp_by_id = {r["scene_id"]: r for r in inp["scenes"]}
    if len(inp_by_id) != 816 or list(inp_by_id) != [x["scene_id"] for x in inp["scenes"]]:
        raise ValueError("duplicate or malformed A1 scene order")
    if set(old_by_id) != set(inp_by_id):
        raise ValueError("A1 cache rows do not cover exactly the input manifest")

    with g3_path.open("r", encoding="utf-8-sig", newline="") as f:
        g3 = list(csv.DictReader(f))
    selected_g3 = [r for r in g3 if r.get("split") == "TRAIN" and r.get("task") == "FIG8_3D"
                   and r.get("role") == "B" and r.get("eligible", "").lower() == "true"]
    if len(selected_g3) != 256:
        raise ValueError(f"expected 256 eligible T2 TRAIN B index rows, found {len(selected_g3)}")
    g3_by_scene = {}
    audit_by_scene = {}
    for audit_row in train_audit["rows"]:
        alias = audit_row["scene_id"]
        suffix = "_ACC_FIX_V1"
        if not alias.endswith(suffix):
            raise ValueError(f"noncanonical cfg/opts audit runtime ID: {alias}")
        canonical = alias[:-len(suffix)]
        if canonical in audit_by_scene:
            raise ValueError(f"duplicate cfg/opts audit row: {canonical}")
        audit_by_scene[canonical] = audit_row
    for row in selected_g3:
        if row.get("status") not in ALLOWED_G3_STATUS or row.get("action") not in ALLOWED_G3_ACTION:
            raise ValueError(f"illegal completed G3 status/action: {row.get('run_id')}")
        if (row["status"], row["action"]) not in {
            ("RUN_COMPLETE_STABLE", "RUN_PLANT"), ("PILOT6_VALIDATED", "PILOT6_IMPORT")
        }:
            raise ValueError(f"inconsistent G3 status/action: {row.get('run_id')}")
        alias = row["runtime_scene_id"]
        suffix = "_ACC_FIX_V1"
        if not alias.endswith(suffix):
            raise ValueError(f"noncanonical corrected runtime ID: {alias}")
        canonical = alias[:-len(suffix)]
        if canonical in g3_by_scene:
            raise ValueError(f"duplicate G3 source scene: {canonical}")
        audit_row = audit_by_scene.get(canonical)
        if audit_row is None or audit_row["run_start_sha256"].lower() != row["run_start_sha256"].lower():
            raise ValueError(f"G3 run_start is not the exact row audited for B opts: {canonical}")
        g3_by_scene[canonical] = row
    candidates_by_scene = {r["scene_id"]: r for r in candidates.get("scenes", []) if r.get("scene_id", "").startswith("DL1018_VAL_T2_")}
    if len(candidates_by_scene) != 16:
        raise ValueError(f"expected exactly 16 T2 VAL candidates, found {len(candidates_by_scene)}")
    c5_lock = load_json(repo_file(root, C5_LOCK))
    lock_by_scene = {r["scene_id"]: r for r in c5_lock.get("scenes", [])}

    rows = []
    empty_source = {"class": "", "runtime_scene_id": "", "role": "", "task": "", "action": "",
                    "status": "", "eligible": False, "candidate_action": "",
                    "input_lock_external_identity_sha256": "",
                    "cfg_opts_audit_run_start_sha256": "",
                    "raw": {"path": "", "size_bytes": 0, "sha256": "", "sha256_origin": ""},
                    "run_start": {"path": "", "size_bytes": 0, "sha256": "", "sha256_origin": ""}}
    for ordinal, scene in enumerate(inp["scenes"], 1):
        sid, split = scene["scene_id"], scene["split"]
        roles = a1_roles(scene)
        old_row = old_by_id[sid]
        cache_rel = old_row["cache_path"]
        cache_path = repo_file(root, cache_rel)
        if cache_path.stat().st_size != old_row["cache_bytes"]:
            raise ValueError(f"recorded A1 cache size changed: {sid}")
        a1_source = {role: {"path": item["path"], "size_bytes": item["size_bytes"], "sha256": item["sha256"]}
                     for role, item in roles.items()}
        original_a1_cache = {"path": cache_rel, "sha256": old_row["cache_sha256"],
                 "size_bytes": old_row["cache_bytes"], "status": old_row["status"],
                 "reused": "_T2_" not in sid, "use_as_repaired_label": "_T2_" not in sid}
        cache = dict(original_a1_cache) if "_T2_" not in sid else {
            "path": f"{CACHE_ROOT}/{split}_{sid}.mat", "sha256": "", "size_bytes": 0,
            "status": "NOT_EXPORTED", "reused": False, "use_as_repaired_label": True}
        source = json.loads(json.dumps(empty_source))
        export_gates = "REUSE_CERTIFIED_A1_CACHE" if "_T2_" not in sid else "PENDING_CORRECTED_SOURCE_AND_EVENT_GATES"
        common = {"ordinal": ordinal, "scene_id": sid, "split": split,
                  "original_a1_source": a1_source, "original_a1_cache": original_a1_cache,
                  "cache": cache, "corrected_source": source,
                  "export_gates": export_gates}
        if "_T2_" not in sid:
            if sid.split("_")[2] not in {"T1", "T3"}:
                raise ValueError(f"unexpected non-T2 scene: {sid}")
            for item in roles.values():
                p = repo_file(root, item["path"])
                if p.stat().st_size != item["size_bytes"]:
                    raise ValueError(f"recorded A1 source size changed: {sid}:{item['role']}")
            rows.append({**common, "source_action": "REUSE_A1_CERTIFIED_CACHE"})
            continue

        for item in roles.values():
            p = repo_file(root, item["path"])
            if p.stat().st_size != item["size_bytes"]:
                raise ValueError(f"recorded original A1 source size changed: {sid}:{item['role']}")
        cache = {"path": f"{CACHE_ROOT}/{split}_{sid}.mat", "sha256": "", "size_bytes": 0,
                 "status": "NOT_EXPORTED", "reused": False, "use_as_repaired_label": True}
        if split == "TRAIN":
            row = g3_by_scene.get(sid)
            if row is None:
                raise ValueError(f"missing corrected G3 T2 TRAIN B source: {sid}")
            raw = source_file(root, row["raw_path"])
            start = source_file(root, row["run_start_path"])
            if raw.stat().st_size <= 0 or start.stat().st_size <= 0:
                raise ValueError(f"empty corrected G3 source: {sid}")
            if sha256(start) != row["run_start_sha256"].lower():
                raise ValueError(f"G3 run_start SHA mismatch: {sid}")
            source = {"class": "CORRECTED_T2_TRAIN_B_G3", "runtime_scene_id": row["runtime_scene_id"],
                      "role": row["role"], "task": row["task"], "action": row["action"],
                      "status": row["status"], "eligible": True, "candidate_action": "",
                      "input_lock_external_identity_sha256": "",
                      "cfg_opts_audit_run_start_sha256": audit_by_scene[sid]["run_start_sha256"].lower(),
                      "raw": {"path": str(raw), "size_bytes": raw.stat().st_size,
                              "sha256": row["raw_sha256"].lower(), "sha256_origin": "pinned_G3_index_record; rehash_before_export"},
                      "run_start": {"path": str(start), "size_bytes": start.stat().st_size,
                                    "sha256": row["run_start_sha256"].lower(), "sha256_origin": "G3_index_and_file_rehashed"}}
        else:
            cand = candidates_by_scene.get(sid)
            lock_row = lock_by_scene.get(sid)
            if cand is None or lock_row is None:
                raise ValueError(f"missing T2 VAL candidate/input-lock source: {sid}")
            if cand.get("split") != "VAL" or cand.get("collector") != "B":
                raise ValueError(f"T2 VAL candidate is not physical B: {sid}")
            physical = cand["C5_physical_B_source"]
            lock_source = lock_row.get("B_source", {})
            if norm_path(physical["path"]) != norm_path(lock_source.get("path", "")) or \
                    physical["sha256"].lower() != lock_source.get("sha256", "").lower():
                raise ValueError(f"C5 input lock and VAL physical-B candidate differ: {sid}")
            raw = source_file(root, physical["path"])
            start = raw.with_name("run_start.mat").resolve(strict=True)
            if raw.stat().st_size <= 0 or raw.name.lower() != "raw_run.mat" or start.stat().st_size <= 0:
                raise ValueError(f"invalid T2 VAL B source files: {sid}")
            expected_alias = sid + "_ACC_FIX_V1"
            if raw.parent.parent.parent.name != expected_alias:
                raise ValueError(f"T2 VAL source path lacks exact corrected scene alias: {sid}")
            if physical["sha256"].lower() == roles["raw_run"]["sha256"].lower():
                raise ValueError(f"T2 VAL corrected B source aliases old A1 raw: {sid}")
            source = {"class": "CORRECTED_T2_VAL_PHYSICAL_B", "runtime_scene_id": expected_alias,
                      "role": "B", "task": "FIG8_3D", "action": "C5_INPUT_LOCK_PHYSICAL_B_SOURCE",
                      "status": "CANDIDATE_SOURCE_PINNED_RAW_GATE_PENDING", "eligible": True,
                      "candidate_action": cand["C5_candidate"]["action"],
                      "input_lock_external_identity_sha256": lock_row["external_identity_sha256"],
                      "cfg_opts_audit_run_start_sha256": "",
                      "raw": {"path": str(raw), "size_bytes": raw.stat().st_size,
                              "sha256": physical["sha256"].lower(), "sha256_origin": "pinned_C5_candidate_and_input_lock; rehash_before_export"},
                      "run_start": {"path": str(start), "size_bytes": start.stat().st_size,
                                    "sha256": sha256(start), "sha256_origin": "computed_file_hash"}}
        common["cache"] = cache
        common["corrected_source"] = source
        common["export_gates"] = "raw_and_run_start_sha256;cfg_equals_C5_snapshot;B_opts_equal_except_firstPlant_marker;corrected_scene_equals_A1_except_accel_yz;audit_reference_fixed;1999_event_extract_closure"
        rows.append({**common, "source_action": "REBUILD_FROM_CORRECTED_T2_B_RAW"})
    if len(rows) != 816 or sum(r["source_action"] == "REUSE_A1_CERTIFIED_CACHE" for r in rows) != 544:
        raise ValueError("source mapping count mismatch (expected 544 reuse + 272 rebuild)")
    expected_train = {r["scene_id"] for r in inp["scenes"] if r["split"] == "TRAIN" and "_T2_" in r["scene_id"]}
    expected_val = {r["scene_id"] for r in inp["scenes"] if r["split"] == "VAL" and "_T2_" in r["scene_id"]}
    if set(g3_by_scene) != expected_train or set(candidates_by_scene) != expected_val:
        raise ValueError("corrected T2 source rows do not exactly cover the frozen A1 T2 scenes")
    return rows


def self_check() -> None:
    assert "DL1018_TRAIN_T2_C00_W00_ACC_FIX_V1"[:-len("_ACC_FIX_V1")] == "DL1018_TRAIN_T2_C00_W00"
    assert len(SCREEN4) == 4 and all("_T2_" in s for s in SCREEN4)
    assert CACHE_ROOT.startswith("data/events/")
    source_keys = {"class", "runtime_scene_id", "role", "task", "action", "status", "eligible",
                   "candidate_action", "input_lock_external_identity_sha256", "cfg_opts_audit_run_start_sha256",
                   "raw", "run_start"}
    file_keys = {"path", "size_bytes", "sha256", "sha256_origin"}
    cache_keys = {"path", "sha256", "size_bytes", "status", "reused", "use_as_repaired_label"}
    empty_file = {"path": "", "size_bytes": 0, "sha256": "", "sha256_origin": ""}
    populated_file = {"path": "raw_run.mat", "size_bytes": 1, "sha256": "0" * 64,
                      "sha256_origin": "pinned_source_record"}
    empty_source = {key: "" for key in source_keys if key not in {"eligible", "raw", "run_start"}}
    empty_source.update({"eligible": False, "raw": empty_file, "run_start": empty_file})
    populated_source = {key: "" for key in source_keys if key not in {"eligible", "raw", "run_start"}}
    populated_source.update({"eligible": True, "raw": populated_file, "run_start": populated_file})
    cache_template = {key: None for key in cache_keys}
    reuse_row = {"ordinal": 1, "scene_id": "DL1018_TRAIN_T1_C00_W00", "split": "TRAIN",
                 "original_a1_source": {}, "original_a1_cache": cache_template.copy(),
                 "cache": cache_template.copy(), "corrected_source": empty_source,
                 "export_gates": "REUSE_CERTIFIED_A1_CACHE", "source_action": "REUSE_A1_CERTIFIED_CACHE"}
    rebuild_row = {"ordinal": 2, "scene_id": "DL1018_TRAIN_T2_C00_W00", "split": "TRAIN",
                   "original_a1_source": {}, "original_a1_cache": cache_template.copy(),
                   "cache": cache_template.copy(), "corrected_source": populated_source,
                   "export_gates": "PENDING_CORRECTED_SOURCE_AND_EVENT_GATES",
                   "source_action": "REBUILD_FROM_CORRECTED_T2_B_RAW"}
    assert set(reuse_row) == set(rebuild_row)
    assert set(reuse_row["corrected_source"]) == set(rebuild_row["corrected_source"]) == source_keys
    assert set(reuse_row["cache"]) == set(rebuild_row["cache"]) == cache_keys
    assert set(reuse_row["corrected_source"]["raw"]) == set(rebuild_row["corrected_source"]["raw"]) == file_keys
    assert set(reuse_row["corrected_source"]["run_start"]) == set(rebuild_row["corrected_source"]["run_start"]) == file_keys
    print("SELF_CHECK_PASS: fixed alias, 4-scene screen, uniform scene/cache/source keys")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare metadata-only B_REF_REPAIRED source mapping; no raw arrays are loaded.")
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    if args.self_check:
        self_check()
        return

    root = Path(__file__).resolve().parents[2]
    out_path = repo_file(root, OUTPUT) if (root / OUTPUT).exists() else (root / OUTPUT)
    if out_path.exists() or out_path.with_suffix(out_path.suffix + ".tmp").exists():
        raise FileExistsError(f"refusing to overwrite prepared source manifest: {out_path}")
    inp, old, lineage, candidates, train_audit, g3_path = check_metadata_pins(root)
    rows = build_rows(root, inp, old, lineage, candidates, train_audit, g3_path)

    source_files = []
    for rel in [TASKBOOK, INPUT, A1_DATASET, LINEAGE, VAL_CANDIDATES, C5_LOCK, TRAIN_OPTS_AUDIT, PREPARE_SCRIPT, EXPORTER,
                EXTRACTOR, "matlab/core/arm_mass_properties.m", "matlab/core/distributed_mass_properties.m",
                "matlab/core/arm_directions.m"]:
        p = repo_file(root, rel)
        source_files.append({"path": rel, "sha256": sha256(p), "size_bytes": p.stat().st_size})
    g3_cohort_path = g3_path.parent.parent / "manifests" / "G3_COHORT_1632.csv"
    state_pin = lineage["pins"]["CORRECTED_TRAIN_STATE"]
    pilot_state_path = Path(state_pin["path"]).resolve(strict=True)
    external_sources = [
        (str(g3_path), G3_INDEX_SHA),
        (str(g3_cohort_path), G3_COHORT_SHA),
        (str(pilot_state_path), state_pin["sha256"].lower()),
        (lineage["pins"]["FIXED_FORMULA_HELPER"]["path"], lineage["pins"]["FIXED_FORMULA_HELPER"]["sha256"].lower()),
        (lineage["cfg_opts_check"]["C5_snapshot_path"], "842ef395569e675db6e139c2684d72b976946915e5e0a58b9b7f24ec10c1d24a"),
    ]
    for name, expected in external_sources:
        p = source_file(root, name)
        if sha256(p) != expected.lower():
            raise ValueError(f"pinned external source changed: {name}")
        source_files.append({"path": str(p), "sha256": expected.lower(), "size_bytes": p.stat().st_size})
    manifest = {
        "schema": SCHEMA,
        "status": "PREPARED_METADATA_ONLY_RAW_AND_CACHE_EXPORT_PENDING",
        "taskbook_sha256": PINNED[TASKBOOK],
        "input_manifest_sha256": INPUT_SHA,
        "a1_dataset_manifest_sha256": PINNED[A1_DATASET],
        "source_pins": {"lineage_path": LINEAGE, "lineage_sha256": PINNED[LINEAGE],
                        "g3_index_path": str(g3_path), "g3_index_sha256": G3_INDEX_SHA,
                        "g3_cohort_path": str(g3_cohort_path), "g3_cohort_sha256": G3_COHORT_SHA,
                        "corrected_train_state_path": str(pilot_state_path),
                        "corrected_train_state_sha256": state_pin["sha256"].lower(),
                        "val_candidates_path": VAL_CANDIDATES, "val_candidates_sha256": PINNED[VAL_CANDIDATES],
                        "c5_input_lock_path": C5_LOCK, "c5_input_lock_sha256": PINNED[C5_LOCK],
                        "train_cfg_opts_audit_path": TRAIN_OPTS_AUDIT,
                        "train_cfg_opts_audit_sha256": PINNED[TRAIN_OPTS_AUDIT],
                        "corrected_reference_helper_path": lineage["pins"]["FIXED_FORMULA_HELPER"]["path"],
                        "corrected_reference_helper_sha256": lineage["pins"]["FIXED_FORMULA_HELPER"]["sha256"].lower(),
                        "c5_snapshot_path": lineage["cfg_opts_check"]["C5_snapshot_path"],
                        "c5_snapshot_sha256": "842ef395569e675db6e139c2684d72b976946915e5e0a58b9b7f24ec10c1d24a"},
        "source_files": source_files,
        "counts": {"all_scenes": 816, "reuse_a1_t1_t3_cache": 544,
                   "rebuild_corrected_t2": 272, "t2_train_g3_b": 256, "t2_val_physical_b": 16,
                   "screen4_fixed": 4},
        "screen4_scene_ids": ["DL1018_TRAIN_T2_C00_W00", "DL1018_TRAIN_T2_C15_W14",
                              "DL1018_VAL_T2_C00_W10", "DL1018_VAL_T2_C15_W09"],
        "scenes": rows,
        "scope": {"metadata_only": True, "raw_numeric_arrays_read": False,
                  "cache_numeric_arrays_read": False, "raw_files_copied": False,
                  "exported": False, "Plant_calls": 0, "training_steps": 0,
                  "optimizer_steps": 0, "TEST_accessed": False},
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    temp = out_path.with_suffix(out_path.suffix + ".tmp")
    encoded = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if len(encoded) > 8 * 1024 * 1024:
        raise ValueError("source manifest exceeds 8 MiB metadata budget")
    with temp.open("xb") as f:
        f.write(encoded)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, out_path)
    print(f"SOURCE_MANIFEST_WRITTEN {out_path.relative_to(root).as_posix()} bytes={len(encoded)} scenes=816 reuse=544 rebuild=272")


if __name__ == "__main__":
    main()



