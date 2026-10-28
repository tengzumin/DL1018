"""Small text/source inventory comparison, with no simulations or raw reads."""
import csv
import difflib
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports/paper_continuation_20261023/c5_eight_loss_recovery"
C5_LOCK = ROOT / "experiments/position_axis_coordinate_c5_dev72_20261023/C5_DEV72_INPUT_LOCK_v3.json"
B_LOCK = ROOT / "experiments/b_traceable_c3core_dev72_20261023/B_TRACEABLE_DEV72_INPUT_LOCK_v3.json"
OLD = ROOT.parent / "DL1009/RBF-BS0/experiments/position_advantage_stage1_v1"

def sha(p):
    with p.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()

def load(p):
    return json.loads(p.read_text(encoding="utf-8-sig"))

c5, base = load(C5_LOCK), load(B_LOCK)
c5_sources = {Path(r["path"]).name: r for r in c5["active_source_inventory"]}
b_sources = {Path(r["path"]).name: r for r in base["active_source_inventory"]}
assert len(c5_sources) == len(b_sources) == 32
comp = []
for name, cr in c5_sources.items():
    br = b_sources[name]
    ch, bh = sha(Path(cr["path"])), sha(Path(br["path"]))
    assert ch == cr["sha256"] and bh == br["sha256"]
    comp.append({"name": name, "C5_path": cr["path"], "B_path": br["path"],
                 "C5_sha256": ch, "B_sha256": bh, "same_source_bytes": ch == bh})
identical = [r["name"] for r in comp if r["same_source_bytes"]]
different = [r["name"] for r in comp if not r["same_source_bytes"]]
assert different == ["run_dl1018_closed_loop.m"], different
helper = ROOT / "experiments/position_axis_coordinate_c5_dev72_20261023/delayed_prediction_step_candidate.m"
no_helper = ROOT / "experiments/position_c5_matched_ablations_dev72_v3_20261023/C5_NO_DELAYED_PREDICTION/delayed_prediction_step_candidate.m"
helper_diff = "".join(difflib.unified_diff(
    helper.read_text(encoding="utf-8-sig").splitlines(keepends=True),
    no_helper.read_text(encoding="utf-8-sig").splitlines(keepends=True),
    fromfile=str(helper), tofile=str(no_helper)))
old_hashes = {}
with (OLD / "configs/source_hashes.csv").open(encoding="utf-8-sig", newline="") as stream:
    for r in csv.DictReader(stream):
        old_hashes[r["relative_path"]] = r["sha256_before"]
old_cfg = ROOT.parent / "DL1009/RBF-BS0/code/code/default_config.m"
old_cfg_actual = sha(old_cfg)
old_cfg_bound = old_cfg_actual == old_hashes["code/code/default_config.m"]
assert old_cfg_bound
core = next(r for r in comp if r["name"] == "run_dl1018_closed_loop.m")
core_diff = "".join(difflib.unified_diff(
    Path(core["B_path"]).read_text(encoding="utf-8-sig").splitlines(keepends=True),
    Path(core["C5_path"]).read_text(encoding="utf-8-sig").splitlines(keepends=True),
    fromfile=core["B_path"], tofile=core["C5_path"]))
result = {
    "status": "PASS_STATIC_SHARED_CONTROL_BLOCKS_WITH_HISTORICAL_CONDITION_DIFFERENCES",
    "new_Plant": 0, "MATLAB": 0, "raw_reads": 0, "training": 0,
    "C5_input_lock_sha256": sha(C5_LOCK), "B_input_lock_sha256": sha(B_LOCK),
    "shared_inventory_identical_count": len(identical), "identical_names": identical,
    "different_names": different, "inventory_comparison": comp,
    "C5_vs_B_difference": "The locked runtime core adds C5 mask/mixed-reference code and diagnostics; its non-delayed paths retain C3 M=I defaults. All 31 other inventory files, including BS/filter/allocation/Plant, are byte-identical.",
    "current_model": c5["candidate_identity"],
    "current_corrected_model_mat": [r for r in c5["shared_input_files"] if r["role"] == "model_mat"],
    "NO_PRED_helper_diff": helper_diff,
    "historical_default_config": {"path": str(old_cfg), "actual_sha256": old_cfg_actual,
        "historical_before_sha256": old_hashes["code/code/default_config.m"], "hash_matches": old_cfg_bound,
        "source_filter_acceleration_limit_radps2": [8, 8, 6],
        "scope": "Old default source hash matches the historical preflight source list, and old stage entry calls default_config without filter override. Not a fresh per-run cfg extraction."},
    "current_effective_filter": {"acceleration_limit_radps2": ["Inf", "Inf", 6],
        "evidence": ["configs/contract_dl1018.json", "matlab/runtime/init_dl1018.m asserts effective_config.mat"],
        "important": "Reading current default_config.m alone would give [8,8,6], but current init loads the frozen effective_config.mat instead. Both current B/C5 use that same effective cfg."},
    "boundary": "Equal shared source files do not imply equal controller states across independent closed loops. Same-state checks separately reconstruct nominal BS/X14 and PCF on three explicitly selected current DEV hosts."
}
with (OUT / "SOURCE_FAIRNESS_v1.json").open("x", encoding="utf-8") as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2)
with (OUT / "B_C5_CORE_SOURCE_ONLY_v1.diff").open("x", encoding="utf-8") as stream:
    stream.write(core_diff)
with (OUT / "C5_NO_PRED_HELPER_ONLY_v1.diff").open("x", encoding="utf-8") as stream:
    stream.write(helper_diff)
print(json.dumps({"shared_inventory_identical": len(identical), "different": different,
                  "historical_default_source_bound": old_cfg_bound, "output": str(OUT)}, ensure_ascii=False))
