"""Freeze the two C5 matched-ablation inputs from the reviewed C5 screen12 lock."""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STAGE = Path(__file__).resolve().parent
C5 = ROOT / "experiments/position_axis_coordinate_c5_20261023"
TASKBOOK = ROOT / "reports/paper_continuation_20261023/C5_MATCHED_ABLATION_CONDITIONAL_TASKBOOK_ZH.md"
IMPLEMENTATION = ROOT / "reports/paper_continuation_20261023/C5_ABLATION_IMPLEMENTATION_RELEASE_ZH.md"
KERNEL = ROOT / "reports/delayed_prediction_proposal_20261023/construction/delayed_prediction_kernel.py"
TASKBOOK_SHA256 = "02cb08b46f41d5f64adea965e4f9704b75c3aa1e48bc7eee57e1dd94afce6ece"
IMPLEMENTATION_SHA256 = "ceef16ba1188b1c395c531d245828b11ac904e789af57a4280d9ae3bc9520313"
KERNEL_SHA256 = "6615a9d9a6096777429065a598d631ca844f46cf4131032e7ff0a3d3067d9ebc"
VARIANTS = {
    "C5_FREEZE_TRAINED_W0": {
        "actual_weight_update_enabled": False,
        "actual_prediction_gradient_enabled": False,
        "intervention": "candidate=W_k; prediction_gradient=zeros(33,3); W_next=clip(candidate,-60,60).",
    },
    "C5_NO_DELAYED_PREDICTION": {
        "actual_weight_update_enabled": True,
        "actual_prediction_gradient_enabled": False,
        "intervention": "prediction_gradient=zeros(33,3) before the original tracking+leak+prediction candidate and one joint projection.",
    },
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ref(path: Path) -> dict[str, str]:
    path = path.resolve()
    return {"path": str(path), "sha256": sha(path)}


def write_new(path: Path, value: dict) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+"\n", encoding="utf-8")


def add_unique(refs: dict[str, dict], item: dict, role: str | None = None) -> None:
    path = str(Path(item["path"]).resolve())
    key = path.lower()
    value = {"role": role or item.get("role", Path(path).name), "path": path, "sha256": item["sha256"]}
    if key in refs:
        assert refs[key]["sha256"].lower() == value["sha256"].lower(), f"conflicting SHA for {path}"
        return
    refs[key] = value


def make_variant(old_lock: dict, old_contract: dict, variant_id: str) -> dict:
    folder = STAGE / variant_id
    assert folder.is_dir(), f"missing isolated folder: {folder}"
    outputs = (
        "C5_ABLATION_RUN_CONTRACT_v1.json",
        "C5_ABLATION_PARENT_RELEASE_CONTRACT_v1.json",
        "C5_ABLATION_INPUT_LOCK_v1.json",
        "C5_ABLATION_SOURCE_BINDING_v1.json",
    )
    for name in outputs:
        assert not (folder / name).exists(), f"refusing to overwrite {folder / name}"
    paths = {
        "input_lock_builder": Path(__file__),
        "prepare_entry": folder / "prepare_c5_matched_ablation_v1.m",
        "runner_entry": folder / "run_c5_matched_ablation_v1.m",
        "contract": folder / "C5_ABLATION_RUN_CONTRACT_v1.json",
        "parent_release_contract": folder / "C5_ABLATION_PARENT_RELEASE_CONTRACT_v1.json",
        "synthetic_generator": STAGE / "make_c5_matched_ablation_fixture_v1.py",
        "synthetic_check": folder / "check_c5_matched_ablation_synthetic_v1.m",
        "synthetic_fixture": folder / "C5_ABLATION_CROSSLANG_FIXTURE_v2.json",
        "python_kernel": KERNEL,
        "no_plant_launcher": folder / "RUN_C5_ABLATION_NOPLANT_EXACT_v1.ps1",
        "parent_launcher": folder / "RUN_C5_ABLATION_PARENT_EXACT_v1.ps1",
    }
    local_sources = [
        ("runtime_core", folder / "run_dl1018_closed_loop.m"),
        ("episode_wrapper", folder / "run_episode_dl1018.m"),
        ("prediction_helper", folder / "delayed_prediction_step_candidate.m"),
    ]
    for name, path in paths.items():
        if name in {"contract", "parent_release_contract"}:
            continue  # These are produced below; every other path is an input.
        assert path.is_file(), f"missing locked source: {path}"
    for _, path in local_sources:
        assert path.is_file(), f"missing locked source: {path}"
    assert sha(TASKBOOK) == TASKBOOK_SHA256
    assert sha(IMPLEMENTATION) == IMPLEMENTATION_SHA256
    assert sha(KERNEL) == KERNEL_SHA256
    assert old_lock["source_counts"] == {"total": 32, "matlab": 31, "mat": 1}
    scene_ids = list(old_contract["scene_ids"])
    assert len(scene_ids) == 12 and scene_ids == old_lock["scene_ids_reuse_12"]
    first_scene = scene_ids[0]

    contract = {
        "schema": "C5_MATCHED_ABLATION_RUN_CONTRACT_V1",
        "state": "LOCKED_C5_MATCHED_ABLATION_NO_PLANT_PARENT_REVIEW_REQUIRED_V1",
        "variant_id": variant_id,
        "ablation_mode": variant_id,
        "candidate": old_contract["candidate"],
        "coordinate_mask": [1, 1, 0],
        "coordinate_mask_semantics": old_contract["coordinate_mask_semantics"],
        "pcf_auxiliary_enabled": True,
        "legacy_stage1_update_enabled": True,
        "stage1_update_enabled": True,
        "position_delayed_prediction_enabled": True,
        "actual_weight_update_enabled": VARIANTS[variant_id]["actual_weight_update_enabled"],
        "actual_prediction_gradient_enabled": VARIANTS[variant_id]["actual_prediction_gradient_enabled"],
        "intervention": VARIANTS[variant_id]["intervention"],
        "model": copy.deepcopy(old_contract["model"]),
        "fixed_parameters": copy.deepcopy(old_contract["fixed_parameters"]),
        "scene_ids": scene_ids,
        "first_scene_id": first_scene,
        "limits": {
            **copy.deepcopy(old_contract["limits"]),
            "max_new_Plant": 12,
            "first_flights_per_configuration": 1,
            "tail_flights_per_configuration": 11,
            "seconds_per_remaining_scene_for_deadline_guard": 180,
            "process_exit_buffer_seconds": 600,
        },
        "prohibitions": {
            "training_steps": 0, "optimizer_steps": 0, "new_B_sorties": 0,
            "TEST_accessed": False, "automatic_retry": False,
            "parameter_or_seed_search": False, "M_search": False,
            "scenario_or_metric_switching": False,
        },
        "scoring_comparator": old_contract["scoring_comparator"],
        "parent_release_required_before_Plant": True,
        "plant_authorized_by_this_contract": False,
    }
    contract_path = paths["contract"]
    write_new(contract_path, contract)

    release_contract = {
        "schema": "C5_MATCHED_ABLATION_PARENT_RELEASE_CONTRACT_V1",
        "state": "RELEASE_REQUIRED_NO_PLANT_AUTHORITY_V1",
        "variant_id": variant_id,
        "required_fields": [
            "plant_authorized", "phase", "variant_id", "ablation_mode", "actual_weight_update_enabled",
            "actual_prediction_gradient_enabled", "legacy_stage1_update_enabled", "input_lock_sha256",
            "run_contract_sha256", "source_binding_sha256", "prepare_result_sha256", "snapshot_sha256",
            "parent_release_contract_sha256", "synthetic_fixture_sha256", "synthetic_result_sha256",
            "runner_preflight_sha256", "runner_sha256",
            "launcher_sha256", "first_scene_id", "scene_ids", "max_new_Plant", "training_steps",
            "optimizer_steps", "new_B_sorties", "TEST_accessed", "automatic_retry", "parameter_or_seed_search",
            "candidate", "coordinate_mask", "deadline_utc", "minimum_free_bytes",
            "per_scene_output_reserve_bytes", "max_output_bytes",
        ],
        "plant_authorized": False,
        "max_new_Plant": 0,
        "first_scene_id": first_scene,
        "note": "This is a required-field contract only; it is not an execution release.",
    }
    release_contract_path = paths["parent_release_contract"]
    write_new(release_contract_path, release_contract)

    old_active = copy.deepcopy(old_lock["active_source_inventory"])
    active = []
    for item in old_active:
        if item["role"] in {role for role, _ in local_sources}:
            new_path = dict(local_sources)[item["role"]]
            active.append({"role": item["role"], **ref(new_path)})
        else:
            active.append(copy.deepcopy(item))
    assert len(active) == 32 and sum(Path(x["path"]).suffix.lower() == ".m" for x in active) == 31
    assert len({x["role"] for x in active}) == 32

    upstream = copy.deepcopy(old_lock["upstream_refs"])
    upstream.update({
        "c5_axis_input_lock": ref(C5 / "C5_AXIS_COORDINATE_INPUT_LOCK_v1.json"),
        "c5_axis_run_contract": ref(C5 / "C5_AXIS_COORDINATE_RUN_CONTRACT_v1.json"),
        "c5_taskbook": ref(TASKBOOK),
        "c5_implementation_release": ref(IMPLEMENTATION),
    })
    for item in [*active, *old_lock["shared_input_files"], *upstream.values()]:
        path = Path(item["path"])
        assert path.is_file() and sha(path).lower() == item["sha256"].lower(), f"input SHA mismatch: {path}"

    source_files = {name: ref(path) for name, path in paths.items()}
    source_files["isolated_sources"] = [{"role": role, **ref(path)} for role, path in local_sources]
    lock = copy.deepcopy(old_lock)
    lock.update({
        "schema": "C5_MATCHED_ABLATION_INPUT_LOCK_V1",
        "state": contract["state"],
        "plant_authorized_by_this_lock": False,
        "created_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "taskbook_sha256": TASKBOOK_SHA256,
        "implementation_release_sha256": IMPLEMENTATION_SHA256,
        "variant_id": variant_id,
        "ablation_mode": variant_id,
        "actual_weight_update_enabled": VARIANTS[variant_id]["actual_weight_update_enabled"],
        "actual_prediction_gradient_enabled": VARIANTS[variant_id]["actual_prediction_gradient_enabled"],
        "legacy_stage1_update_enabled": True,
        "stage1_update_enabled": True,
        "position_delayed_prediction_enabled": True,
        "coordinate_mask": [1, 1, 0],
        "first_scene_id": first_scene,
        "scene_ids": scene_ids,
        "source_files": source_files,
        "active_source_inventory": active,
        "source_counts": {"total": 32, "matlab": 31, "mat": 1},
        "upstream_refs": upstream,
        "source_order_sha256": hashlib.sha256("\n".join(scene_ids).encode("utf-8")).hexdigest(),
        "scope": contract,
        "notes": [
            "No Plant release is created by this lock.",
            "Uses exactly the reviewed C5 screen12 order and M110 configuration.",
            "The isolated core and episode wrapper are byte-identical to frozen C5; only the local helper differs.",
            "Legacy stage1 update and delayed-prediction branches stay enabled for PCF/target accounting.",
            "Freeze mode's actual weight update is false; no-pred mode retains tracking/leak updates with zero applied prediction gradient.",
        ],
    })
    lock_path = folder / "C5_ABLATION_INPUT_LOCK_v1.json"
    write_new(lock_path, lock)

    refs: dict[str, dict] = {}
    for name, item in source_files.items():
        if name == "isolated_sources":
            for source in item: add_unique(refs, source, source["role"])
        else:
            add_unique(refs, item, name)
    for item in active: add_unique(refs, item, item["role"])
    for item in old_lock["shared_input_files"]: add_unique(refs, item, item["role"])
    for name, item in upstream.items(): add_unique(refs, item, name)
    add_unique(refs, ref(lock_path), "input_lock")
    binding = {
        "schema": "C5_MATCHED_ABLATION_SOURCE_BINDING_V1",
        "state": "SOURCE_BOUND_NO_PLANT_PARENT_REVIEW_REQUIRED_V1",
        "variant_id": variant_id,
        "ablation_mode": variant_id,
        "actual_weight_update_enabled": VARIANTS[variant_id]["actual_weight_update_enabled"],
        "actual_prediction_gradient_enabled": VARIANTS[variant_id]["actual_prediction_gradient_enabled"],
        "legacy_stage1_update_enabled": True,
        "input_lock_path": str(lock_path.resolve()),
        "input_lock_sha256": sha(lock_path),
        "contract_sha256": sha(contract_path),
        "runner_path": str(paths["runner_entry"].resolve()),
        "runner_sha256": sha(paths["runner_entry"]),
        "prepare_sha256": sha(paths["prepare_entry"]),
        "coordinate_mask": [1, 1, 0],
        "active_source_count": len(active), "shared_input_count": len(old_lock["shared_input_files"]),
        "file_refs": list(refs.values()),
        "plant_authorized": False,
        "created_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    assert binding["active_source_count"] == 32 and binding["shared_input_count"] == 6
    binding_path = folder / "C5_ABLATION_SOURCE_BINDING_v1.json"
    write_new(binding_path, binding)
    return {"variant_id": variant_id, "lock_path": str(lock_path.resolve()), "lock_sha256": sha(lock_path),
            "contract_path": str(contract_path.resolve()), "contract_sha256": sha(contract_path),
            "source_binding_path": str(binding_path.resolve()), "source_binding_sha256": sha(binding_path),
            "scenes": scene_ids, "source_count": len(active), "shared_input_count": len(old_lock["shared_input_files"])}


def main() -> None:
    assert sha(TASKBOOK) == TASKBOOK_SHA256 and sha(IMPLEMENTATION) == IMPLEMENTATION_SHA256
    assert sha(KERNEL) == KERNEL_SHA256
    old_lock = json.loads((C5 / "C5_AXIS_COORDINATE_INPUT_LOCK_v1.json").read_text(encoding="utf-8"))
    old_contract = json.loads((C5 / "C5_AXIS_COORDINATE_RUN_CONTRACT_v1.json").read_text(encoding="utf-8"))
    assert old_lock["schema"] == "C5_AXIS_COORDINATE_INPUT_LOCK_V1"
    assert old_contract["coordinate_mask"] == [1, 1, 0]
    assert old_contract["scene_ids"] == old_lock["scene_ids_reuse_12"]
    outputs = [make_variant(old_lock, old_contract, mode) for mode in VARIANTS]
    print(json.dumps({"status": "LOCKED_NO_PLANT_PARENT_REVIEW_REQUIRED_V1", "variants": outputs}, indent=2))


if __name__ == "__main__":
    main()
