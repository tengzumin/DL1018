"""C5 source and paired dataflow audit; never opens MAT, raw, or TEST."""
from hashlib import sha256
from pathlib import Path
import csv
import json
import re

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
REPO = BASE.parents[2]
RUNNER = BASE / "matlab/runtime/run_paired_observer_closed_loop.m"
DEV_CSV = BASE / "configs/scene_specs_dev3.csv"
RECEIPT = BASE / "configs/scene_specs_dev3_receipt.json"

EXPECTED_ROWS = (
    ("DL1018_DEV_T1_C00_W03", "HELIX", "NONE", "0", "0", "3", "2026121803",
     "4546e417fcb2af93f09c83999e6dc0535cf07b58d4f4240e1d751f98ed19a824"),
    ("DL1018_DEV_T2_C02_W15", "FIG8_3D", "2", "1", "2", "15", "2026122847",
     "c8f3dde48b76ae351fe40c30866ff55fa8235e32914a5128e03a1f6b954456f5"),
    ("DL1018_DEV_T3_C10_W11", "SQUARE", "34", "2", "10", "11", "2026123971",
     "9f4d08ddc375a4be074c659e04827c49d957518e6098a2a3128788eb87d1452a"),
)


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise AssertionError(message)


runner = RUNNER.read_text(encoding="utf-8")
helper = (BASE / "matlab/runtime/phys_attitude_replacement_candidate_v2.m").read_text(encoding="utf-8")
bs = (BASE / "matlab/core/attitude_bs_step.m").read_text(encoding="utf-8")
c5 = (REPO / "experiments/position_axis_coordinate_c5_dev72_20261023/run_dl1018_closed_loop.m").read_text(encoding="utf-8")
builder = (BASE / "matlab/scenes/make_paired_dev_scene.m").read_text(encoding="utf-8")
options = (BASE / "matlab/runtime/make_paired_c5_options.m").read_text(encoding="utf-8")

# Only the isolated DEV-only CSV is parsed here. The source manifest is never opened.
require(digest(DEV_CSV) == "bd68a24a0d87764e8d6fabcf5372d8a36a38104a3a246df6523f514548ac7630",
        "isolated DEV CSV SHA")
require(digest(RECEIPT) == "3b4443302cddbf67368922c17234f54041d1f3e36db345b5ec71f5ffc0bf7067",
        "DEV extraction receipt SHA")
receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
require(receipt["source_path"] == "configs/scene_specs.csv" and
        receipt["source_sha256"] == "d116b74dc6d9ce3c21a40fcd48b4153a0adc09e98a6c8d341c0f1b6ba680b4e3" and
        receipt["extracted_csv_sha256"] == digest(DEV_CSV) and
        receipt["extraction_script_sha256"] == digest(BASE / "extract_dev3_specs.ps1") and
        receipt["taskbook_sha256"] == digest(BASE / "INPUT_IDENTITY_TASKBOOK_v1_ZH.md") and
        receipt["status"] == "THREE_EXACT_DEV_ROWS_VERIFIED", "DEV extraction provenance")
raw_lines = DEV_CSV.read_bytes().decode("utf-8").splitlines()
require(len(raw_lines) == 4, "DEV CSV must have only header and three rows")
rows = list(csv.DictReader(raw_lines))
require(len(rows) == len(receipt["rows"]) == 3, "DEV row count")
for row, record, expected, raw_line in zip(rows, receipt["rows"], EXPECTED_ROWS, raw_lines[1:]):
    scene_id, task, class_id, t, c, w, seed, row_hash = expected
    require(row["scene_id"] == record["scene_id"] == scene_id and
            row["split"] == record["split"] == "DEV" and
            row["split_code"] == str(record["split_code"]) == "2" and
            row["source_split_code"] == str(record["source_split_code"]) == "1" and
            row["sealed"] == str(record["sealed"]) == "0" and
            row["task"] == record["task"] == task and
            row["class_id"] == record["class_id"] == class_id and
            row["t"] == str(record["t"]) == t and row["c"] == str(record["c"]) == c and
            row["w"] == str(record["w"]) == w and row["seed"] == str(record["seed"]) == seed and
            sha256(raw_line.encode("utf-8")).hexdigest() == record["source_row_sha256"] == row_hash,
            f"DEV row identity: {scene_id}")
require("scene_specs_dev3.csv" in builder and "scene_specs_dev3_receipt.json" in builder and
        "double(specRow.source_split_code)==1" in builder and "double(specRow.sealed)==0" in builder and
        "height(rows)==3" in builder, "scene builder DEV-only source checks")

require("positionDelayedPredictionEnabled&&isequal(positionCoordinateMask,[1;1;0])" in runner, "C5 M110 guard")
require("delayed_prediction_step_candidate(stage1PositionWeight,phi,sEff" in runner, "C5 delayed helper")
require("'C5_AXIS_MIXED_COORDINATE_M110'" in runner, "C5 method identity")
require("if rbfAtt400 && (rbfAttitudeRuntimeEnabled||attitudeFusionActive||physCandidate)" in runner, "shared attitude branch")
candidate = runner.split("                        if physCandidate\n", 1)[1].split("                        elseif attitudeEvent", 1)[0]
require("phys_attitude_replacement_candidate_v2( ...\n                                'prepare'" in candidate, "candidate prepare")
require("rbf_mimo_update" not in candidate and "rbf_mimo_basis" not in candidate,
        "candidate attitude RBF inference/update bypass")
baseline_attitude = runner.split("                        elseif attitudeEvent", 1)[1].split(
    "                            if attitudeFusionActive", 1)[0]
require("rbf_mimo_update" in baseline_attitude and "rbfAtt" in baseline_attitude,
        "baseline attitude RBF update")
require("candidate.(flags{i})=false" in options and
        all(flag in options for flag in ("rbf_attitude_enabled", "rbf_attitude_output_enabled",
                                         "rbf_attitude_update_enabled")), "candidate attitude-only RBF disable flags")
require("[dpos,rbfPos,posInfo]=rbf_mimo_update" in runner and "updateDt=0;" in runner and
        "dF=stage1PositionHeldForce;" in runner and
        "[dpos,rbfPos,posInfo]=rbf_mimo_update" in c5 and "dF=stage1PositionHeldForce;" in c5,
        "shared C5 position zero-dt compatibility call and Head force override")
require("'alpha_bs_body',ai0.nominal_body_angular_acceleration" in candidate, "BS body alpha provenance")
require("'morph_command',s.arms.command(k,:).'" in candidate, "command provenance")
require("dT=physOut.estimateTorque_Nm" in candidate, "candidate BS input")
require("'estimateTorque_Nm',-tauComp" in helper and "rawMoment = nominalMoment - estimateTorque(:)" in bs, "torque sign")
require("J0 = memory.J0_controller_fixed_kgm2" in helper and
        "memory.J0_controller_fixed_kgm2 = double(J0)" in helper and
        "J0=cfg.attitude_replacement.J0_controller_fixed_kgm2" in helper and
        "cfg.plant.inertia" not in helper, "explicit controller J0 in helper")
require("isequal(J0frozen,double(fixedController.inertia))" in runner and
        "paired_sha256_double(double(fixedController.inertia))" in runner, "controller J0 matrix and SHA")
allocation = runner.index("[motorSetpointNow,wrenchNow,a]=allocate_control(command,P,Ptrue,previousMotor);")
commit = runner[allocation:runner.index("controllerClippedWrench(k,:)", allocation)]
require("'tau_cmd_clipped_Nm',a.clipped_generalized(2:4)" in commit and "'time_s',t(k)" in commit, "commit inputs")
for banned in ("actualGeneralized", "wrenchNow(2", "Ptrue.", "rho_true", "rhoDot_true", "wind", "derivative"):
    require(banned not in candidate and banned not in commit, f"helper boundary: {banned}")
require("phys_attitude_replacement_candidate_v2( ...\n                    'commit',physMemory,commitInput,cfg)" in commit, "candidate commit")
require("if ~physCandidate,rbfOutputHeld(k,:)=dT.';end" in runner, "RBF log isolation")
require("if ~physCandidate\n                        attitudeRbfAccelerationApplied" in runner, "RBF attribution isolation")
require("isequaln(opts,expected)" in runner, "exact arm options")
require("isequaln(normalizedBaseline,normalizedCandidate)" in options, "common option parity")
require("stage1DelayedPredictionReferenceIntegral" in runner and "stage1PcfPredictionReference" in runner, "C5 position trace")
require("stage1DelayedPredictionReferenceIntegral" in c5, "C5 source binding")

required = {
    "matlab/core/allocate_control.m": "matlab/core/allocate_control.m",
    "matlab/core/attitude_bs_step.m": "matlab/core/attitude_bs_step.m",
    "matlab/core/arm_mass_properties.m": "matlab/core/arm_mass_properties.m",
    "matlab/core/rbf_mimo_update.m": "matlab/core/rbf_mimo_update.m",
    "matlab/core/rbf_event_scheduler_step.m": "matlab/core/rbf_event_scheduler_step.m",
    "matlab/models/position_filter_realization_pcf_step_v3_5.m": "matlab/models/position_filter_realization_pcf_step_v3_5.m",
    "matlab/models/position_stage1_update_head_pcf_v3_5.m": "matlab/models/position_stage1_update_head_pcf_v3_5.m",
    "matlab/runtime/delayed_prediction_step_candidate.m": "experiments/position_axis_coordinate_c5_dev72_20261023/delayed_prediction_step_candidate.m",
    "matlab/runtime/phys_attitude_replacement_candidate.m": "experiments/attitude_physics_inertia_observer_20261025/phys_attitude_replacement_candidate.m",
    "matlab/runtime/phys_attitude_replacement_candidate_v2.m": "experiments/attitude_physics_inertia_observer_20261025/phys_attitude_replacement_candidate_v2.m",
    "matlab/runtime/controller_options_dl1018.m": "matlab/runtime/controller_options_dl1018.m",
}
for relative, origin in required.items():
    require(digest(BASE / relative) == digest(REPO / origin), f"copied dependency differs: {relative}")
for path in (BASE / "matlab").rglob("*.m"):
    require(path.is_file() and path.resolve().is_relative_to(BASE), f"outside source tree: {path}")
for path in (REPO / "matlab/core").glob("*.m"):
    require(digest(BASE / "matlab/core" / path.name) == digest(path), f"core closure differs: {path.name}")

sources = sorted((BASE / "matlab").rglob("*.m"))
symbols = {path.stem: path for path in sources}
require(len(sources) == len(symbols) == 39, "39 unique isolated MATLAB sources")
c5_lock_path = REPO / "experiments/position_axis_coordinate_c5_dev72_20261023/C5_DEV72_INPUT_LOCK_v3.json"
c5_contract_path = REPO / "experiments/position_axis_coordinate_c5_dev72_20261023/C5_DEV72_RUN_CONTRACT_v3.json"
c5_prepare_path = REPO / "experiments/position_axis_coordinate_c5_dev72_20261023/C5_DEV72_PREPARE_RESULT_v3.json"
c5_lock = json.loads(c5_lock_path.read_text(encoding="utf-8"))
c5_prepare = json.loads(c5_prepare_path.read_text(encoding="utf-8"))
require(digest(c5_lock_path) == c5_prepare["input_lock_sha256"] and
        digest(c5_contract_path) == c5_prepare["run_contract_sha256"], "C5 v3 input/contract identity")
inventory = c5_lock["active_source_inventory"]
require(len(inventory) == 32 and c5_lock["source_counts"] ==
        {"total": 32, "matlab": 31, "mat": 1}, "C5 active inventory size")
c5_matches = []
for item in inventory:
    origin = Path(item["path"])
    if origin.suffix.lower() == ".mat":
        require(item["role"] == "effective_config.mat", "unexpected C5 MAT inventory entry")
        continue  # Historical C5 input, explicitly excluded from this deployment.
    require(origin.suffix.lower() == ".m" and digest(origin) == item["sha256"],
            f"C5 source SHA: {item['role']}")
    if origin.stem in {"run_episode_dl1018", "init_dl1018"}:
        c5_matches.append({"role": item["role"], "origin": str(origin),
                           "origin_sha256": item["sha256"], "isolated": None,
                           "reason": "replaced by paired entry/activation"})
        continue
    name = "run_paired_observer_closed_loop" if origin.stem == "run_dl1018_closed_loop" else origin.stem
    require(name in symbols, f"C5 dependency absent in isolation: {name}")
    relative = symbols[name].relative_to(BASE).as_posix()
    actual = digest(symbols[name])
    if name != "run_paired_observer_closed_loop":
        require(actual == item["sha256"], f"C5 active dependency differs: {name}")
    c5_matches.append({"role": item["role"], "origin": str(origin),
                       "origin_sha256": item["sha256"], "isolated": relative,
                       "isolated_sha256": actual,
                       "relationship": "paired adaptation" if name == "run_paired_observer_closed_loop" else "byte-identical"})
require(len(c5_matches) == 31, "all C5 active MATLAB sources accounted for")
roots = ("activate_paired_runner", "bind_paired_fixed_j0", "make_paired_dev_scene", "make_paired_c5_options",
         "run_paired_observer_closed_loop")
expected_active = ("position_only_search_head_step", "delayed_prediction_step_candidate",
                   "position_stage1_model_forward_v2", "position_filter_realization_pcf_step_v3_5",
                   "rbf_mimo_update", "attitude_bs_step", "allocate_control",
                   "phys_attitude_replacement_candidate_v2", "rk4_vehicle_step")
seen, pending = set(), list(roots)
while pending:
    name = pending.pop()
    if name in seen:
        continue
    seen.add(name)
    body = symbols[name].read_text(encoding="utf-8")
    for dependency in symbols:
        if dependency != name and re.search(r"(?<![\w.])@?" + re.escape(dependency) + r"\s*\(", body):
            pending.append(dependency)
        elif dependency != name and re.search(r"@" + re.escape(dependency) + r"\b", body):
            pending.append(dependency)
require(set(expected_active).issubset(seen), "active MATLAB symbol closure")
sha_list = {str(path.relative_to(BASE)).replace("\\", "/"): digest(path) for path in sources}
origins = {name: {"path": origin, "sha256": digest(REPO / origin)} for name, origin in required.items()}
for path in (REPO / "matlab/core").glob("*.m"):
    relative = f"matlab/core/{path.name}"
    origins.setdefault(relative, {"path": relative, "sha256": digest(path)})
for name in ("position_stage1_update_head.m", "trim_head_audit_v39.m"):
    relative = f"matlab/models/{name}"
    origins.setdefault(relative, {"path": relative, "sha256": digest(REPO / relative)})
origins["matlab/scenes/make_paired_dev_scene.m"] = {
    "path": "matlab/scenes/make_scenes_dl1018.m",
    "sha256": digest(REPO / "matlab/scenes/make_scenes_dl1018.m"),
}
origins["matlab/runtime/run_paired_observer_closed_loop.m"] = {
    "path": "experiments/position_axis_coordinate_c5_dev72_20261023/run_dl1018_closed_loop.m",
    "sha256": digest(REPO / "experiments/position_axis_coordinate_c5_dev72_20261023/run_dl1018_closed_loop.m"),
}
for item in c5_matches:
    if item["isolated"] and item["relationship"] == "byte-identical":
        origins[item["isolated"]] = {"path": item["origin"], "sha256": item["origin_sha256"]}
for name in ("position_stage1_update_head.m", "position_stage1_update_head_pcf_v3_5.m", "trim_head_audit_v39.m"):
    relative = f"matlab/models/{name}"
    origins[relative] = {"path": relative, "sha256": digest(REPO / relative)}
origins["production_generic_runner"] = {
    "path": "matlab/runtime/run_dl1018_closed_loop.m",
    "sha256": digest(REPO / "matlab/runtime/run_dl1018_closed_loop.m"),
}
for name in ("PAIRED_RUNNER_TASKBOOK_DRAFT_v1_ZH.md", "PAIRED_RUNNER_TASKBOOK_ADDENDUM_v1.1_ZH.md"):
    origins[name] = {"path": f"experiments/attitude_physics_inertia_observer_20261025/{name}",
                     "sha256": digest(BASE.parent / name)}
for name in ("extract_dev3_specs.ps1", "INPUT_IDENTITY_TASKBOOK_v1_ZH.md",
             "configs/scene_specs_dev3.csv", "configs/scene_specs_dev3_receipt.json"):
    origins[name] = {"path": f"experiments/attitude_physics_inertia_observer_20261025/paired_runner/{name}",
                     "sha256": digest(BASE / name)}
synthetic_lock_path = REPO / "experiments/attitude_physics_inertia_observer_20261025/synthetic/source_lock_candidate_v3.json"
synthetic_lock = json.loads(synthetic_lock_path.read_text(encoding="utf-8"))
require(synthetic_lock["synthetic_audit_status"] == "PASS", "synthetic v3 status")
for item in synthetic_lock["source_files"] + synthetic_lock["evidence_artifacts"]:
    require(digest(REPO / item["path"]) == item["sha256"], f"synthetic v3 evidence SHA: {item['path']}")
for name in ("phys_attitude_replacement_candidate_v2.m", "attitude_bs_step.m",
             "arm_mass_properties.m", "distributed_mass_properties.m", "arm_directions.m"):
    isolated = symbols[Path(name).stem]
    original = next(item for item in synthetic_lock["source_files"] if Path(item["path"]).name == name)
    require(digest(isolated) == original["sha256"], f"synthetic v3 source still valid: {name}")
result = {"status": "STATIC_CODE_PASS_PENDING_ROOT_REVIEW_NO_MATLAB", "source_count": len(sources),
          "isolated_sha256": sha_list, "source_origins": origins,
          "c5_v3_active_inventory_matches": c5_matches,
          "c5_v3_input_lock_sha256": digest(c5_lock_path),
          "c5_v3_run_contract_sha256": digest(c5_contract_path),
          "c5_v3_prepare_result_sha256": digest(c5_prepare_path),
          "synthetic_v3_source_lock_sha256": digest(synthetic_lock_path),
          "synthetic_v3_audit_sha256": digest(REPO / synthetic_lock["evidence_artifacts"][0]["path"]),
          "full_input_lock_taskbook_sha256": digest(BASE / "FULL_INPUT_LOCK_TASKBOOK_v1_ZH.md"),
          "checker_sha256": digest(Path(__file__)),
          "legacy_audit_status": "SUPERSEDED_BEFORE_C5_FORWARD_FIX",
          "dev3_input_identity": {"source_path": receipt["source_path"],
                                  "source_sha256_from_receipt": receipt["source_sha256"],
                                  "row_sha256": [row[-1] for row in EXPECTED_ROWS]},
          "lexical_symbol_closure": sorted(seen),
          "unused_isolated_symbols": sorted(set(symbols) - seen),
          "limits": "Code and dataflow assertions only; no MATLAB syntax or runtime execution."}
out = HERE / "CODE_ONLY_STATIC_AUDIT_v2.json"
with out.open("x", encoding="utf-8", newline="\n") as stream:
    stream.write(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
print(f"STATIC_CODE_PASS_PENDING_ROOT_REVIEW_NO_MATLAB: {len(sources)} isolated MATLAB sources; {out}")
