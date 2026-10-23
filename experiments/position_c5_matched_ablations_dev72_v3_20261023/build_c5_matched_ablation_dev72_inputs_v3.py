"""Freeze the 60-new/12-reused C5 matched-ablation DEV72 inputs."""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STAGE = Path(__file__).resolve().parent
SCREEN12_ROOT = ROOT / "experiments/position_c5_matched_ablations_v4_20261023"
C5_DEV72 = ROOT / "experiments/position_axis_coordinate_c5_dev72_20261023/C5_DEV72_INPUT_LOCK_v3.json"
C3_LOCK = ROOT / "experiments/position_delayed_prediction_c3_dev72_20261023/C3_DEV72_INPUT_LOCK_v2.json"
C3_CONTRACT = ROOT / "experiments/position_delayed_prediction_c3_dev72_20261023/C3_DEV72_RUN_CONTRACT_v2.json"
TASKBOOK = ROOT / "reports/paper_continuation_20261023/C5_MATCHED_ABLATION_CONDITIONAL_TASKBOOK_ZH.md"
FULL72_TASKBOOK = ROOT / "reports/paper_continuation_20261023/C5_MATCHED_ABLATION_FULL72_CONDITIONAL_TASKBOOK_DRAFT_ZH.md"
IMPLEMENTATION = ROOT / "reports/paper_continuation_20261023/C5_ABLATION_IMPLEMENTATION_RELEASE_ZH.md"
SCREEN_DECISION = ROOT / "reports/paper_continuation_20261023/C5_ABLATION_SCREEN12_DECISION_ZH.md"
KERNEL = ROOT / "reports/delayed_prediction_proposal_20261023/construction/delayed_prediction_kernel.py"
AUDIT_ROOT = ROOT / "reports/paper_continuation_20261023/c5_matched_ablation_parent_raw_review"

SHA = {
    "taskbook": "02cb08b46f41d5f64adea965e4f9704b75c3aa1e48bc7eee57e1dd94afce6ece",
    "full72_taskbook": "e1dd38ce715e82a078e0bcc4d632557ce589b8e521b59c2391b3e4069668f415",
    "implementation": "ceef16ba1188b1c395c531d245828b11ac904e789af57a4280d9ae3bc9520313",
    "kernel": "6615a9d9a6096777429065a598d631ca844f46cf4131032e7ff0a3d3067d9ebc",
    "c3_lock": "a95eda8e6ab8b45408d24b560366636bab62f72ea619bf46fa602142b6708730",
    "c3_contract": "9cbef5b5774a8b7a821c798f29caa6912755704f29f1a5e7f1f871f8ff1dc5fd",
}

VARIANTS = {
    "C5_FREEZE_TRAINED_W0": (False, "candidate=W_k; prediction_gradient=zeros(33,3); W_next=clip(candidate,-60,60)."),
    "C5_NO_DELAYED_PREDICTION": (True, "prediction_gradient=zeros(33,3) before the original tracking+leak+prediction candidate and one joint projection."),
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ref(path: Path) -> dict[str, str]:
    path = path.resolve()
    return {"path": str(path), "sha256": sha(path)}


def write_new(path: Path, value: dict) -> None:
    encoded = json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") == encoded:
            return
        raise FileExistsError(f"refusing to overwrite different evidence at {path}")
    path.write_text(encoded, encoding="utf-8")


def add_unique(refs: dict[str, dict], item: dict, role: str | None = None) -> None:
    path = str(Path(item["path"]).resolve())
    key = path.lower()
    value = {"role": role or item.get("role", Path(path).name), "path": path, "sha256": item["sha256"]}
    if key in refs:
        assert refs[key]["sha256"].lower() == value["sha256"].lower(), f"conflicting SHA for {path}"
        return
    refs[key] = value


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def check_ref(item: dict) -> None:
    p = Path(item["path"])
    assert p.is_file() and sha(p).lower() == item["sha256"].lower(), f"missing/SHA mismatch: {p}"


def reuse12_records(variant: str) -> tuple[dict, dict]:
    first_audit_path = AUDIT_ROOT / f"{variant}_FIRST_RAW_PARENT_AUDIT_v1.json"
    screen_audit_path = AUDIT_ROOT / f"{variant}_SCREEN12_RAW_PARENT_AUDIT_v1.json"
    first_audit = load_json(first_audit_path)
    screen_audit = load_json(screen_audit_path)
    assert first_audit["status"] == "PASS_C5_MATCHED_ABLATION_FIRST_RAW_ALL_EVENTS"
    assert screen_audit["status"] == "PASS_C5_MATCHED_ABLATION_SCREEN12_ALL_EVENTS"
    assert screen_audit["variant_id"] == variant and screen_audit["screen12_complete"] is True
    assert len(screen_audit["screen12_rows"]) == 12 and screen_audit["scene_count_newly_audited"] == 11
    assert first_audit["variant_id"] == variant and first_audit["event_count"] == 1968
    first_release = first_audit["source_files"]["release"]
    first_batch = first_audit["source_files"]["batch"]
    first_body = first_audit["source_files"]["body"]
    first_os = first_audit["natural_os_exit"]
    first_art = first_audit["run_artifacts"]
    first_batch_json = load_json(Path(first_batch["path"]))
    first_records = first_batch_json["records"]
    first_rec = first_records if isinstance(first_records, dict) else first_records[0]
    tail_dir = SCREEN12_ROOT / variant
    tail_batch_path = tail_dir / "C5_ABLATION_TAIL11_BATCH_STATUS_v1.json"
    tail_body_path = tail_dir / "C5_ABLATION_TAIL11_BODY_COMPLETE_v1.json"
    tail_release_path = tail_dir / "C5_ABLATION_TAIL11_PARENT_RELEASE_v1.json"
    tail_os_path = ROOT / "reports/paper_continuation_20261023/c5_matched_ablation_execution/v4" / f"C5_{variant}_TAIL11_MATLAB_OS_EXIT_v1.json"
    tail_batch = load_json(tail_batch_path)
    tail_body = load_json(tail_body_path)
    tail_release = load_json(tail_release_path)
    tail_os = load_json(tail_os_path)
    assert tail_batch["status"] == "COMPLETE_RAW_PENDING_PARENT_AUDIT" and len(tail_batch["records"]) == 11
    assert tail_body["status"] == "COMPLETE_RAW_PENDING_PARENT_AUDIT" and tail_body["scene_count"] == 11
    assert tail_release["plant_authorized"] is True and tail_release["phase"] == "TAIL11"
    assert tail_os["matlab_os_exit_code"] == 0
    recs = []
    for row in screen_audit["screen12_rows"]:
        scene = row["scene_id"]
        method = row["methods"][variant]
        if row["phase"] == "FIRST_PILOT_REUSE":
            assert scene == first_audit["scene_id"] and method["sha256"] == first_art["raw_sha256"]
            rec = {"scene_id": scene, "phase": "FIRST_PILOT_REUSE",
                   "raw_path": first_art["raw_path"], "raw_sha256": first_art["raw_sha256"],
                   "run_status_path": first_art["run_status_path"], "run_status_sha256": first_art["run_status_sha256"],
                   "run_start_path": first_art["run_start_path"], "run_start_sha256": first_art["run_start_sha256"],
                   "attempt_started_marker_path": first_rec["attempt_started_marker_path"],
                   "attempt_started_marker_sha256": first_rec["attempt_started_marker_sha256"],
                   "first_plant_step_marker_path": first_rec["first_plant_step_marker_path"],
                   "first_plant_step_marker_sha256": first_rec["first_plant_step_marker_sha256"],
                   "phase_release_path": first_release["path"], "phase_release_sha256": first_release["sha256"],
                   "phase_batch_path": first_batch["path"], "phase_batch_sha256": first_batch["sha256"],
                   "phase_body_path": first_body["path"], "phase_body_sha256": first_body["sha256"],
                   "natural_os_exit_path": first_os["path"], "natural_os_exit_sha256": first_os["sha256"],
                   "first_parent_audit_path": str(first_audit_path.resolve()), "first_parent_audit_sha256": sha(first_audit_path),
                   "screen12_parent_audit_path": str(screen_audit_path.resolve()), "screen12_parent_audit_sha256": sha(screen_audit_path),
                   "event_count": 1968, "audit_status": screen_audit["status"],
                   "external_identity_sha256": method["external_identity_sha256"]}
        else:
            batch_record = next(x for x in tail_batch["records"] if x["scene_id"] == scene)
            assert method["sha256"] == batch_record["raw_sha256"]
            rec = {"scene_id": scene, "phase": "TAIL11",
                   "raw_path": batch_record["raw_path"], "raw_sha256": batch_record["raw_sha256"],
                   "run_status_path": batch_record["run_status_path"], "run_status_sha256": batch_record["run_status_sha256"],
                   "run_start_path": batch_record["run_start_path"], "run_start_sha256": batch_record["run_start_sha256"],
                   "attempt_started_marker_path": batch_record["attempt_started_marker_path"],
                   "attempt_started_marker_sha256": batch_record["attempt_started_marker_sha256"],
                   "first_plant_step_marker_path": batch_record["first_plant_step_marker_path"],
                   "first_plant_step_marker_sha256": batch_record["first_plant_step_marker_sha256"],
                   "phase_release_path": str(tail_release_path.resolve()), "phase_release_sha256": sha(tail_release_path),
                   "phase_batch_path": str(tail_batch_path.resolve()), "phase_batch_sha256": sha(tail_batch_path),
                   "phase_body_path": str(tail_body_path.resolve()), "phase_body_sha256": sha(tail_body_path),
                   "natural_os_exit_path": str(tail_os_path.resolve()), "natural_os_exit_sha256": sha(tail_os_path),
                   "first_parent_audit_path": str(first_audit_path.resolve()), "first_parent_audit_sha256": sha(first_audit_path),
                   "screen12_parent_audit_path": str(screen_audit_path.resolve()), "screen12_parent_audit_sha256": sha(screen_audit_path),
                   "event_count": 1968, "audit_status": screen_audit["status"],
                   "external_identity_sha256": method["external_identity_sha256"]}
        for name, value in rec.items():
            if name.endswith("_path"):
                p = Path(value); sha_key = name[:-5] + "_sha256"
                if sha_key in rec:
                    assert p.is_file() and sha(p).lower() == rec[sha_key].lower(), f"reuse artifact mismatch: {p}"
        recs.append(rec)
    assert [x["scene_id"] for x in recs] == [x["scene_id"] for x in screen_audit["screen12_rows"]]
    assert len({tuple(sorted(x.keys())) for x in recs}) == 1, "MATLAB jsondecode requires uniform record field sets."
    binding = {
        "schema": "C5_MATCHED_ABLATION_DEV72_REUSE12_BINDING_V2",
        "state": "PARENT_AUDITED_SCREEN12_REUSE_ONLY_V2",
        "variant_id": variant,
        "screen12_order": [x["scene_id"] for x in recs],
        "screen12_parent_audit_path": str(screen_audit_path.resolve()),
        "screen12_parent_audit_sha256": sha(screen_audit_path),
        "first_parent_audit_path": str(first_audit_path.resolve()),
        "first_parent_audit_sha256": sha(first_audit_path),
        "screen12_parent_audit_event_audit_sha256": screen_audit["event_audit_sha256"],
        "screen12_parent_audit_entry_sha256": screen_audit["audit_entry_sha256"],
        "records": recs,
        "plant_calls_in_audit": 0,
        "TEST_accessed": False,
        "training_steps": 0,
        "optimizer_steps": 0,
    }
    return binding, {"first_audit": first_audit, "screen_audit": screen_audit}

def make_variant(variant: str, c5_lock: dict, c5_contract: dict, c3_lock: dict, screen_lock: dict) -> dict:
    folder = STAGE / variant
    assert folder.is_dir()
    output_names = [
        "C5_ABLATION_DEV72_RUN_CONTRACT_v3.json", "C5_ABLATION_DEV72_PARENT_RELEASE_CONTRACT_v3.json",
        "C5_ABLATION_DEV72_REUSE12_BINDING_v3.json", "C5_ABLATION_DEV72_INPUT_LOCK_v3.json",
        "C5_ABLATION_DEV72_SOURCE_BINDING_v3.json", "C5_ABLATION_DEV72_PARENT_RELEASE_TEMPLATE_v3.json",
    ]
    assert c5_lock["scene_ids_all_72"] == c3_lock["scene_ids_all_72"]
    all72 = list(c3_lock["scene_ids_all_72"])
    reuse12 = list(screen_lock["scene_ids_reuse_12"])
    assert len(all72) == 72 and len(set(all72)) == 72 and len(reuse12) == 12 and len(set(reuse12)) == 12
    remaining60 = [scene for scene in all72 if scene not in set(reuse12)]
    assert len(remaining60) == 60 and len(set(remaining60)) == 60
    assert remaining60 == c5_lock["scene_ids_new_60"]
    assert remaining60 == c3_lock["scene_ids_new_60"]
    assert set(remaining60).isdisjoint(reuse12) and set(remaining60) | set(reuse12) == set(all72)
    assert [x["scene_id"] for x in c5_lock["scenes"]] == all72
    c3_by_id = {x["scene_id"]: x for x in c3_lock["scenes"]}
    c5_by_id = {x["scene_id"]: x for x in c5_lock["scenes"]}
    assert list(c3_by_id) == all72 and list(c5_by_id) == all72
    reuse_binding, _ = reuse12_records(variant)
    assert reuse_binding["screen12_order"] == reuse12
    reuse_binding_path = folder / "C5_ABLATION_DEV72_REUSE12_BINDING_v3.json"
    write_new(reuse_binding_path, reuse_binding)

    release_required = [
        "schema", "state", "plant_authorized", "phase", "variant_id", "ablation_mode", "actual_weight_update_enabled",
        "actual_prediction_gradient_enabled", "legacy_stage1_update_enabled", "input_lock_sha256",
        "run_contract_sha256", "source_binding_sha256", "prepare_result_sha256", "snapshot_sha256",
        "parent_release_contract_sha256", "synthetic_fixture_sha256", "synthetic_result_sha256",
        "runner_preflight_sha256", "runner_sha256", "launcher_sha256", "first_scene_id",
        "scene_ids_all_72", "scene_ids_remaining_60", "scene_ids_reuse_12", "max_new_Plant",
        "training_steps", "optimizer_steps", "new_B_sorties", "TEST_accessed", "automatic_retry",
        "parameter_or_seed_search", "candidate", "coordinate_mask", "deadline_utc", "minimum_free_bytes",
        "per_scene_output_reserve_bytes", "max_output_bytes", "reuse12_binding_sha256",
        "reuse12_parent_screen_audit_sha256", "reuse12_first_audit_sha256", "screen12_event_audit_sha256",
        "c3_dev72_lock_sha256", "c3_dev72_contract_sha256", "c3_dev72_snapshot_sha256",
    ]
    parent_contract = {
        "schema": "C5_MATCHED_ABLATION_DEV72_PARENT_RELEASE_CONTRACT_V2",
        "state": "RELEASE_REQUIRED_FOR_REMAINING60_NO_AUTHORITY_V2",
        "variant_id": variant, "phase": "REMAINING60", "required_fields": release_required,
        "plant_authorized": False, "max_new_Plant": 0,
        "note": "Required fields for a separately reviewed release. This template/contract is not release authority.",
    }
    parent_contract_path = folder / "C5_ABLATION_DEV72_PARENT_RELEASE_CONTRACT_v3.json"
    write_new(parent_contract_path, parent_contract)

    fixed = copy.deepcopy(screen_lock["scope"]["fixed_parameters"])
    contract = {
        "schema": "C5_MATCHED_ABLATION_DEV72_RUN_CONTRACT_V2",
        "state": "LOCKED_C5_MATCHED_ABLATION_DEV72_NO_PLANT_WAIT_PARENT_REVIEW_V2",
        "variant_id": variant, "ablation_mode": variant,
        "candidate": screen_lock["scope"]["candidate"], "coordinate_mask": [1, 1, 0],
        "coordinate_mask_semantics": screen_lock["scope"]["coordinate_mask_semantics"],
        "pcf_auxiliary_enabled": True, "legacy_stage1_update_enabled": True,
        "stage1_update_enabled": True, "position_delayed_prediction_enabled": True,
        "actual_weight_update_enabled": VARIANTS[variant][0],
        "actual_prediction_gradient_enabled": False, "intervention": VARIANTS[variant][1],
        "model": copy.deepcopy(screen_lock["scope"]["model"]), "fixed_parameters": fixed,
        "scene_ids_all_72": all72, "scene_ids_remaining_60": remaining60, "scene_ids_reuse_12": reuse12,
        "first_scene_id": remaining60[0], "scoring_comparator": "B_TRACEABLE_DEV72",
        "limits": {"max_new_Plant": 60, "max_total_scenes": 72, "max_output_bytes": 5 * 1024**3,
                   "minimum_free_bytes": 30000000000, "per_scene_output_reserve_bytes": 80000000,
                   "deadline_utc": "2026-10-24T17:01:00Z", "seconds_per_remaining_scene_for_deadline_guard": 180,
                   "process_exit_buffer_seconds": 600},
        "prohibitions": {"training_steps": 0, "optimizer_steps": 0, "new_B_sorties": 0,
                         "TEST_accessed": False, "automatic_retry": False,
                         "parameter_or_seed_search": False, "M_search": False,
                         "scenario_or_metric_switching": False},
        "reuse_rule": "Reuse exactly the parent-audited screen12 outputs; execute only the original C3 DEV72 order stable-filtered to the remaining 60.",
        "parent_release_required_before_Plant": True, "plant_authorized_by_this_contract": False,
    }
    contract_path = folder / "C5_ABLATION_DEV72_RUN_CONTRACT_v3.json"
    write_new(contract_path, contract)
    template = {key: ("__PARENT_RELEASE_VALUE_REQUIRED__" if key not in {"scene_ids_all_72", "scene_ids_remaining_60", "scene_ids_reuse_12"}
                      else contract[key]) for key in release_required}
    template.update({"schema": "C5_MATCHED_ABLATION_DEV72_PARENT_RELEASE_TEMPLATE_V2",
                     "state": "TEMPLATE_NOT_AUTHORIZED", "plant_authorized": False,
                     "phase": "REMAINING60", "variant_id": variant,
                     "ablation_mode": variant, "scene_ids_all_72": all72,
                     "scene_ids_remaining_60": remaining60, "scene_ids_reuse_12": reuse12,
                     "max_new_Plant": 0})
    template_path = folder / "C5_ABLATION_DEV72_PARENT_RELEASE_TEMPLATE_v3.json"
    write_new(template_path, template)

    paths = {
        "input_lock_builder": STAGE / "build_c5_matched_ablation_dev72_inputs_v3.py",
        "prepare_entry": folder / "prepare_c5_matched_ablation_dev72_v3.m",
        "runner_entry": folder / "run_c5_matched_ablation_dev72_v3.m",
        "contract": contract_path, "parent_release_contract": parent_contract_path,
        "reuse12_binding": reuse_binding_path,
        "synthetic_generator": STAGE / "make_c5_matched_ablation_fixture_v3.py",
        "synthetic_check": folder / "check_c5_matched_ablation_dev72_synthetic_v3.m",
        "synthetic_fixture": folder / "C5_ABLATION_CROSSLANG_FIXTURE_v3.json",
        "python_kernel": ROOT / "reports/delayed_prediction_proposal_20261023/construction/delayed_prediction_kernel.py",
        "no_plant_launcher": folder / "RUN_C5_ABLATION_DEV72_NOPLANT_EXACT_v3.ps1",
        "parent_launcher": folder / "RUN_C5_ABLATION_DEV72_PARENT_EXACT_v3.ps1",
    }
    local_sources = [
        ("runtime_core", folder / "run_dl1018_closed_loop.m"),
        ("episode_wrapper", folder / "run_episode_dl1018.m"),
        ("prediction_helper", folder / "delayed_prediction_step_candidate.m"),
    ]
    for key, path in paths.items():
        assert path.is_file(), f"missing source for {key}: {path}"
    for _, path in local_sources: assert path.is_file(), f"missing active source: {path}"
    assert sha(TASKBOOK) == SHA["taskbook"] and sha(FULL72_TASKBOOK) == SHA["full72_taskbook"]
    assert sha(IMPLEMENTATION) == SHA["implementation"] and sha(KERNEL) == SHA["kernel"]
    assert SCREEN_DECISION.is_file()
    assert sha(C3_LOCK) == SHA["c3_lock"] and sha(C3_CONTRACT) == SHA["c3_contract"]
    assert screen_lock["source_counts"] == {"total": 32, "matlab": 31, "mat": 1}
    assert len(screen_lock["shared_input_files"]) == 6
    active = []
    local_by_role = dict(local_sources)
    for old in screen_lock["active_source_inventory"]:
        if old["role"] in local_by_role:
            active.append({"role": old["role"], **ref(local_by_role[old["role"]])})
        else:
            active.append(copy.deepcopy(old))
    assert len(active) == 32 and sum(Path(x["path"]).suffix.lower() == ".m" for x in active) == 31
    assert len({x["role"] for x in active}) == 32

    c3_lock = load_json(C3_LOCK)
    c3_contract = load_json(C3_CONTRACT)
    upstream = copy.deepcopy(screen_lock["upstream_refs"])
    upstream.update({
        "c3_dev72_input_lock": ref(C3_LOCK), "c3_dev72_run_contract": ref(C3_CONTRACT),
        "c3_dev72_prepare_result": ref(ROOT / "experiments/position_delayed_prediction_c3_dev72_20261023/C3_DEV72_PREPARE_RESULT_v2.json"),
        "c3_dev72_prepared_snapshot": ref(ROOT / "experiments/position_delayed_prediction_c3_dev72_20261023/C3_DEV72_PREPARED_CONFIG_OPTS_v2.mat"),
        "c5_dev72_input_lock": ref(C5_DEV72),
        "c5_matched_ablation_taskbook": ref(TASKBOOK), "c5_matched_ablation_full72_taskbook": ref(FULL72_TASKBOOK),
        "c5_ablation_implementation_release": ref(IMPLEMENTATION),
        "c5_screen12_parent_decision": ref(SCREEN_DECISION),
        "c5_freeze_screen12_parent_audit": ref(AUDIT_ROOT / "C5_FREEZE_TRAINED_W0_SCREEN12_RAW_PARENT_AUDIT_v1.json"),
        "c5_no_pred_screen12_parent_audit": ref(AUDIT_ROOT / "C5_NO_DELAYED_PREDICTION_SCREEN12_RAW_PARENT_AUDIT_v1.json"),
    })
    for item in [*active, *screen_lock["shared_input_files"], *upstream.values()]: check_ref(item)
    source_files = {name: ref(path) for name, path in paths.items()}
    source_files["isolated_sources"] = [{"role": role, **ref(path)} for role, path in local_sources]
    scene_rows = []
    for scene_id in all72:
        row = copy.deepcopy(c5_by_id[scene_id])
        assert row["B_source"]["path"] == c3_by_id[scene_id]["B_source"]["path"]
        assert row["B_source"]["sha256"] == c3_by_id[scene_id]["B_source"]["sha256"]
        row["C3_reference"] = copy.deepcopy(c5_by_id[scene_id]["C3_reference"])
        assert row["C3_reference"] == c5_lock["scenes"][all72.index(scene_id)]["C3_reference"]
        row["C5_ABLATION_REUSE"] = {"reused": scene_id in set(reuse12), "variant_id": variant}
        scene_rows.append(row)
    lock = copy.deepcopy(screen_lock)
    lock.update({
        "schema": "C5_MATCHED_ABLATION_DEV72_INPUT_LOCK_V2", "state": contract["state"],
        "plant_authorized_by_this_lock": False, "created_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "full72_taskbook_sha256": SHA["full72_taskbook"], "c3_dev72_input_lock_sha256": SHA["c3_lock"],
        "c3_dev72_run_contract_sha256": SHA["c3_contract"], "variant_id": variant, "ablation_mode": variant,
        "actual_weight_update_enabled": VARIANTS[variant][0], "actual_prediction_gradient_enabled": False,
        "legacy_stage1_update_enabled": True, "stage1_update_enabled": True,
        "position_delayed_prediction_enabled": True, "coordinate_mask": [1, 1, 0],
        "scene_ids_all_72": all72, "scene_ids_remaining_60": remaining60, "scene_ids_reuse_12": reuse12,
        "first_scene_id": remaining60[0], "scene_ids": all72, "scenes": scene_rows,
        "reuse12_binding": ref(reuse_binding_path), "source_files": source_files,
        "active_source_inventory": active, "source_counts": {"total": 32, "matlab": 31, "mat": 1},
        "upstream_refs": upstream, "source_order_sha256": hashlib.sha256("\n".join(all72).encode()).hexdigest(),
        "scope": contract,
        "notes": [
            "No Plant release is created by this lock.",
            "The full snapshot contains all 72 C3 DEV scenes in original locked order; only the stable-filtered remaining 60 can run.",
            "The parent-audited 12 C5 matched-ablation outcomes are referenced by path and SHA only; raw/release files are not copied.",
            "The C5 runtime core and episode wrapper are byte-identical to reviewed screen12; only the configuration helper differs by the frozen ablation.",
        ],
    })
    lock_path = folder / "C5_ABLATION_DEV72_INPUT_LOCK_v3.json"
    write_new(lock_path, lock)
    refs: dict[str, dict] = {}
    for name, item in source_files.items():
        if name == "isolated_sources":
            for source in item: add_unique(refs, source, source["role"])
        else: add_unique(refs, item, name)
    for item in active: add_unique(refs, item, item["role"])
    for item in screen_lock["shared_input_files"]: add_unique(refs, item, item["role"])
    for name, item in upstream.items(): add_unique(refs, item, name)
    add_unique(refs, ref(lock_path), "input_lock")
    binding = {
        "schema": "C5_MATCHED_ABLATION_DEV72_SOURCE_BINDING_V2", "state": "SOURCE_BOUND_NO_PLANT_PARENT_REVIEW_REQUIRED_V2",
        "variant_id": variant, "ablation_mode": variant, "coordinate_mask": [1, 1, 0],
        "actual_weight_update_enabled": VARIANTS[variant][0], "actual_prediction_gradient_enabled": False,
        "legacy_stage1_update_enabled": True, "input_lock_path": str(lock_path.resolve()), "input_lock_sha256": sha(lock_path),
        "run_contract_path": str(contract_path.resolve()), "run_contract_sha256": sha(contract_path), "contract_sha256": sha(contract_path),
        "parent_release_contract_path": str(parent_contract_path.resolve()), "parent_release_contract_sha256": sha(parent_contract_path),
        "runner_path": str(paths["runner_entry"].resolve()), "runner_sha256": sha(paths["runner_entry"]),
        "prepare_path": str(paths["prepare_entry"].resolve()), "prepare_sha256": sha(paths["prepare_entry"]),
        "reuse12_binding_path": str(reuse_binding_path.resolve()), "reuse12_binding_sha256": sha(reuse_binding_path),
        "all_scene_count": 72, "remaining_scene_count": 60, "reused_scene_count": 12,
        "active_source_count": 32, "shared_input_count": 6, "file_refs": list(refs.values()),
        "plant_authorized": False, "created_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    binding_path = folder / "C5_ABLATION_DEV72_SOURCE_BINDING_v3.json"
    write_new(binding_path, binding)
    return {"variant_id": variant, "lock_path": str(lock_path.resolve()), "lock_sha256": sha(lock_path),
            "contract_path": str(contract_path.resolve()), "contract_sha256": sha(contract_path),
            "source_binding_path": str(binding_path.resolve()), "source_binding_sha256": sha(binding_path),
            "scene_count": len(all72), "remaining_count": len(remaining60), "reuse_count": len(reuse12)}


def main() -> None:
    assert sha(TASKBOOK) == SHA["taskbook"] and sha(FULL72_TASKBOOK) == SHA["full72_taskbook"]
    assert sha(IMPLEMENTATION) == SHA["implementation"] and sha(KERNEL) == SHA["kernel"]
    assert SCREEN_DECISION.is_file()
    assert sha(C3_LOCK) == SHA["c3_lock"] and sha(C3_CONTRACT) == SHA["c3_contract"]
    c5_lock = load_json(C5_DEV72)
    c3_lock = load_json(C3_LOCK)
    c3_contract = load_json(C3_CONTRACT)
    assert c3_contract["scene_ids_all_72"] == c3_lock["scene_ids_all_72"]
    results = []
    for variant in VARIANTS:
        screen_lock_path = SCREEN12_ROOT / variant / "C5_ABLATION_INPUT_LOCK_v1.json"
        screen_contract_path = SCREEN12_ROOT / variant / "C5_ABLATION_RUN_CONTRACT_v1.json"
        results.append(make_variant(variant, c5_lock, c3_contract, c3_lock, load_json(screen_lock_path)))
    manifest = {"schema": "C5_MATCHED_ABLATION_DEV72_CODE_INPUT_MANIFEST_V2",
                "status": "LOCKED_NO_PLANT_WAIT_PARENT_SOURCE_REVIEW", "variants": results,
                "scene_order_source": {"path": str(C3_LOCK.resolve()), "sha256": sha(C3_LOCK), "field": "scene_ids_all_72"},
                "reuse_order_source": "C5 screen12 parent audits; stable-filter removed from C3 scene_ids_all_72; no sorting.",
                "plant_authorized": False, "training_steps": 0, "optimizer_steps": 0, "TEST_accessed": False}
    write_new(STAGE / "C5_ABLATION_DEV72_CODE_INPUT_MANIFEST_v3.json", manifest)
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
