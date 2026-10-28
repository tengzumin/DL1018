"""Lock 24 same-scene TRAIN bindings for the no-position-GRU dual-notch study.

This is a source-only preparation step. It never launches MATLAB or Plant and
does not create attempt directories or run markers.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
INPUT_PATH = HERE / "COHORT_INPUT_v1.json"
OUTPUT_PATH = HERE / "BATCH_BINDINGS_v1.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def digest_json(value: Any) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def source_path(value: str) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (REPO / path).resolve()


def locked_file(spec: dict[str, str]) -> Path:
    path = source_path(spec["path"])
    if not path.is_file():
        raise FileNotFoundError(path)
    actual = sha256_file(path)
    if actual.lower() != spec["sha256"].lower():
        raise ValueError(f"SHA-256 mismatch: {path}")
    return path


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def verify_artifact(path_value: str, expected_sha: str) -> str:
    path = source_path(path_value)
    if not path.is_file():
        raise FileNotFoundError(path)
    actual = sha256_file(path)
    if actual.lower() != expected_sha.lower():
        raise ValueError(f"SHA-256 mismatch: {path}")
    return str(path)


def verify_status(path_value: str, expected_sha: str, scene_id: str, raw_sha: str, *, role: str) -> dict[str, Any]:
    path = source_path(path_value)
    if sha256_file(path).lower() != expected_sha.lower():
        raise ValueError(f"{role} status hash mismatch: {path}")
    status = read_json(path)
    if status.get("scene_id") != scene_id or str(status.get("raw_sha256", "")).lower() != raw_sha.lower():
        raise ValueError(f"{role} status is not bound to {scene_id}: {path}")
    if int(status.get("transitions", -1)) != 20000 or int(status.get("state_samples", -1)) != 20001:
        raise ValueError(f"{role} run is incomplete for {scene_id}")
    if any(status.get(flag, False) for flag in ("TEST_read", "TEST_accessed", "VAL_read", "VAL_data_read")):
        raise ValueError(f"{role} status reports TEST/VAL access for {scene_id}")
    return status


def same_path(left: str, right: str) -> bool:
    return source_path(left) == source_path(right)


def main() -> None:
    if OUTPUT_PATH.exists():
        raise FileExistsError(f"Refusing to overwrite {OUTPUT_PATH}")

    inputs = read_json(INPUT_PATH)
    if inputs.get("schema") != "NO_POSITION_GRU_NOTCH_TRAIN24_BATCH_INPUT_V1":
        raise ValueError("Unexpected cohort input schema")
    if inputs.get("study_id") != "no_position_gru_notch_train24_batch_prepare_v1":
        raise ValueError("Unexpected study id")

    cohort = inputs["cohort"]
    scene_ids = cohort["scene_ids"]
    if len(scene_ids) != 24 or len(set(scene_ids)) != 24 or not all(x.startswith("DL1018_DEV_") for x in scene_ids):
        raise ValueError("Cohort must be the fixed 24 unique canonical DEV ids")

    dataset_manifest_path = locked_file(cohort["dataset_manifest"])
    dataset_path = locked_file(cohort["dataset_path"])
    source_lock_path = locked_file(cohort["dataset_source_lock"])
    physical_manifest_path = locked_file(cohort["physical_manifest"])
    c5_input_lock_path = locked_file(cohort["c5_input_lock"])
    manifest = read_json(dataset_manifest_path)
    source_lock = read_json(source_lock_path)
    physical_manifest = read_json(physical_manifest_path)
    c5_input_lock = read_json(c5_input_lock_path)

    if manifest.get("scene_count") != 24 or manifest.get("source_scene_ids") != scene_ids:
        raise ValueError("Dataset manifest does not equal the explicit 24-scene cohort")
    if source_path(source_lock["data_path"]) != dataset_path:
        raise ValueError("Dataset source lock points to a different TRAIN24 dataset")
    if source_lock.get("data_sha256") != cohort["dataset_path"]["sha256"]:
        raise ValueError("Source lock does not bind the TRAIN24 dataset")
    if source_path(source_lock["physical_manifest_path"]) != physical_manifest_path:
        raise ValueError("Dataset source lock points to a different physical manifest")
    if source_lock.get("physical_manifest_sha256", "").lower() != cohort["physical_manifest"]["sha256"].lower():
        raise ValueError("Dataset source lock physical-manifest hash differs")
    if physical_manifest.get("train_split") != "TRAIN_C5_24" or physical_manifest.get("train_scene_count") != 24:
        raise ValueError("Physical manifest is not the locked TRAIN_C5_24 source")
    if physical_manifest.get("scene_ids") != scene_ids:
        raise ValueError("Physical manifest scene order differs from the explicit cohort")
    if c5_input_lock.get("schema") != "C5_AXIS_COORDINATE_DEV72_INPUT_LOCK_V3":
        raise ValueError("Unexpected C5 input-lock schema")

    physical_records = physical_manifest["records"]
    train_records = source_lock["scene_rows"]
    c5_records = [row for row in c5_input_lock["scenes"] if row["scene_id"] in set(scene_ids)]
    if [row["scene_id"] for row in physical_records] != scene_ids or [row["scene_id"] for row in train_records] != scene_ids:
        raise ValueError("Physical/source-lock row order differs from the explicit cohort")
    if len(c5_records) != len(scene_ids):
        raise ValueError("C5 input lock contains duplicate or missing TRAIN scene rows")
    physical_rows = {row["scene_id"]: row for row in physical_records}
    train_rows = {row["scene_id"]: row for row in train_records}
    c5_rows = {row["scene_id"]: row for row in c5_records}
    if set(physical_rows) != set(scene_ids) or set(train_rows) != set(scene_ids) or set(c5_rows) != set(scene_ids):
        raise ValueError("A physical, source-lock, or C5-binding row is missing from TRAIN_C5_24")

    anchors: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    for anchor in inputs["single_scene_anchors"]:
        binding_path = locked_file({"path": anchor["binding_path"], "sha256": anchor["binding_sha256"]})
        release_path = locked_file({"path": anchor["release_path"], "sha256": anchor["release_sha256"]})
        binding = read_json(binding_path)
        release = read_json(release_path)
        if binding.get("selected_scene_id") != anchor["scene_id"]:
            raise ValueError("Anchor binding scene differs from its lock row")
        if anchor["scene_id"] not in scene_ids or release.get("fixed_scene_id") != anchor["scene_id"]:
            raise ValueError("Anchor release is outside the explicit TRAIN_C5_24 cohort")
        if release.get("study_id") != anchor["study_id"]:
            raise ValueError("Anchor release study id differs from its lock row")
        if release.get("position_residual_gru", {}).get("enabled") is not False:
            raise ValueError("Anchor unexpectedly enables position residual GRU")
        if release.get("position_residual_gru", {}).get("weights_deserialized") is not False:
            raise ValueError("Anchor unexpectedly deserializes position residual-GRU weights")
        if release.get("position_residual_gru", {}).get("runtime_field_present") is not False:
            raise ValueError("Anchor unexpectedly includes a position residual-GRU runtime field")
        if release.get("inertia_reconstruction_enabled") is not False:
            raise ValueError("Anchor unexpectedly reconstructs inertia")
        anchors.append((anchor, binding, release))

    if len(anchors) != 2:
        raise ValueError("Exactly the locked T1 and T3 single-scene anchors are required")
    anchor_bindings = [item[1] for item in anchors]
    shared_binding_fields = (
        "dataset_manifest_sha256", "dataset_sha256", "dataset_source_lock_sha256",
        "parent_cosine_release_sha256", "parent_cosine_manifest_sha256", "parent_cosine_source_lock_sha256",
        "parent_cosine_model_sha256", "position_model_sha256", "c5_input_lock_sha256",
        "c5_snapshot_sha256", "c5_receipt_sha256",
    )
    for field in shared_binding_fields:
        values = {str(binding.get(field, "")).lower() for binding in anchor_bindings}
        if len(values) != 1:
            raise ValueError(f"T1/T3 anchors disagree on {field}")
    expected_cohort_hashes = {
        "dataset_manifest_sha256": cohort["dataset_manifest"]["sha256"],
        "dataset_sha256": cohort["dataset_path"]["sha256"],
        "dataset_source_lock_sha256": cohort["dataset_source_lock"]["sha256"],
        "c5_input_lock_sha256": cohort["c5_input_lock"]["sha256"],
    }
    if any(anchor_bindings[0].get(field, "").lower() != expected.lower() for field, expected in expected_cohort_hashes.items()):
        raise ValueError("T1/T3 anchors do not bind the fixed cohort inputs")
    expected_models = inputs["shared_model_hashes"]
    for field, expected in (
        ("parent_cosine_model_sha256", expected_models["parent_cosine_model"]),
        ("position_model_sha256", expected_models["position_dssm14_model"]),
        ("c5_snapshot_sha256", expected_models["c5_snapshot"]),
        ("c5_receipt_sha256", expected_models["c5_receipt"]),
        ("parent_cosine_release_sha256", expected_models["parent_release"]),
        ("parent_cosine_manifest_sha256", expected_models["parent_manifest"]),
        ("parent_cosine_source_lock_sha256", expected_models["parent_source_lock"]),
    ):
        if anchor_bindings[0].get(field, "").lower() != expected.lower():
            raise ValueError(f"Anchor {field} differs from the input lock")
    for field, expected in (
        ("parent_release_sha256", expected_models["parent_release"]),
        ("parent_manifest_sha256", expected_models["parent_manifest"]),
        ("parent_source_lock_sha256", expected_models["parent_source_lock"]),
    ):
        if source_lock.get(field, "").lower() != expected.lower():
            raise ValueError(f"TRAIN24 source lock {field} differs from the shared model lock")

    reference_release = anchors[0][2]
    fixed_filter = inputs["fixed_filter"]
    for _, _, release in anchors:
        notch = release["applied_acceleration_dual_notch"]
        for key in ("enabled", "sample_rate_hz", "centers_hz", "quality_factor_each", "action_limit_mps2", "b", "a", "event_update_hz", "held_between_events", "parameter_sweep"):
            if notch.get(key) != fixed_filter[key]:
                raise ValueError(f"T1/T3 notch does not match fixed input parameter: {key}")
        if not notch.get("enabled") or notch.get("parameter_sweep"):
            raise ValueError("Dual notch must be enabled with no parameter sweep")
    if fixed_filter["filter_location"] != "post_final_C5_action_pre_force_injection":
        raise ValueError("Unexpected fixed filter location")

    shared_models: dict[str, Any] = {}
    anchor = anchor_bindings[0]
    model_fields = {
        "parent_cosine_model": ("parent_cosine_model_path", "parent_cosine_model_sha256"),
        "position_dssm14_model": ("position_model_path", "position_model_sha256"),
        "c5_snapshot": ("c5_snapshot_path", "c5_snapshot_sha256"),
        "c5_receipt": ("c5_receipt_path", "c5_receipt_sha256"),
        "parent_release": ("parent_cosine_release_path", "parent_cosine_release_sha256"),
        "parent_manifest": ("parent_cosine_manifest_path", "parent_cosine_manifest_sha256"),
        "parent_source_lock": ("parent_cosine_source_lock_path", "parent_cosine_source_lock_sha256"),
    }
    for name, (path_key, hash_key) in model_fields.items():
        path = source_path(anchor[path_key])
        actual = sha256_file(path)
        if actual.lower() != anchor[hash_key].lower():
            raise ValueError(f"Shared {name} hash changed: {path}")
        shared_models[name] = {"path": str(path), "sha256": actual}

    receipt = read_json(source_path(anchor["c5_receipt_path"]))
    common_position_options_sha256 = str(receipt["common_position_options_sha256"])
    if any(str(read_json(source_path(b["c5_receipt_path"]))["common_position_options_sha256"]) != common_position_options_sha256 for b in anchor_bindings[1:]):
        raise ValueError("T1/T3 C5 frozen options differ")
    if str(receipt["input_records"]["model_mat"]["sha256"]).lower() != expected_models["position_dssm14_model"].lower():
        raise ValueError("C5 receipt does not bind the locked DSSM14 model")
    if str(receipt["input_records"]["c5_snapshot_mat"]["sha256"]).lower() != expected_models["c5_snapshot"].lower():
        raise ValueError("C5 receipt does not bind the locked snapshot")

    runtime_sources = []
    for spec in inputs["runtime_references"]["source_files"]:
        path = locked_file(spec)
        runtime_sources.append({"path": str(path), "sha256": spec["sha256"]})
    scorer = locked_file({"path": inputs["score_contract"]["scorer_path"], "sha256": inputs["score_contract"]["scorer_sha256"]})
    j0_helper = locked_file(inputs["fixed_controller"]["fixed_j0_helper"])
    if j0_helper != source_path(inputs["fixed_controller"]["fixed_j0_helper"]["path"]):
        raise ValueError("Fixed-J0 helper path normalization failed")

    scene_folds = manifest["scene_folds"]
    bindings = []
    for order, scene_id in enumerate(scene_ids):
        physical = physical_rows[scene_id]
        train = train_rows[scene_id]
        c5_lock_row = c5_rows[scene_id]
        b_record = c5_lock_row["B72_scoring"]
        identity = str(train["scene_identity_sha256"])
        if physical.get("split") != "TRAIN_C5_24" or train.get("declared_split") != "TRAIN_C5_24":
            raise ValueError(f"Non-TRAIN_C5_24 source row: {scene_id}")
        if c5_lock_row.get("source_split") != "DEV":
            raise ValueError(f"C5 source lock row is not canonical DEV for {scene_id}")
        if not (identity.lower() == str(physical["scene_identity_sha256"]).lower() == str(c5_lock_row["external_identity_sha256"]).lower()):
            raise ValueError(f"B/C5/parent scene identity mismatch: {scene_id}")
        if b_record.get("scene_id") != scene_id or b_record.get("plant_calls") != 1:
            raise ValueError(f"B baseline is not the completed same-scene run: {scene_id}")

        for group, path_key, sha_key in (
            ("payload", "payload_path", "payload_sha256"),
            ("parent_raw", "parent_cosine_gru_raw_path", "parent_cosine_gru_raw_sha256"),
            ("parent_status", "parent_status_path", "parent_status_sha256"),
            ("c5_raw", "raw_path", "raw_sha256"),
            ("c5_status", "status_path", "status_sha256"),
            ("c5_run_start", "run_start_path", "run_start_sha256"),
            ("b_raw", "raw_path", "raw_sha256"),
            ("b_status", "run_status_path", "run_status_sha256"),
        ):
            if group in ("payload", "parent_raw", "parent_status"):
                record = train
            elif group in ("c5_raw", "c5_status", "c5_run_start"):
                record = physical
            else:
                record = b_record
            verify_artifact(record[path_key], str(record[sha_key]))

        payload_path = str(source_path(train["payload_path"]))
        parent_raw_path = str(source_path(train["parent_cosine_gru_raw_path"]))
        parent_status_path = str(source_path(train["parent_status_path"]))
        parent_start_path = str(Path(parent_raw_path).with_name("run_start.json"))
        parent_start_sha = str(train["parent_run_start_sha256"])
        if sha256_file(Path(parent_start_path)).lower() != parent_start_sha.lower():
            raise ValueError(f"Parent run-start hash mismatch: {scene_id}")
        parent_start = read_json(Path(parent_start_path))
        if parent_start.get("scene_id") != scene_id:
            raise ValueError(f"Parent run-start scene mismatch: {scene_id}")

        c5_raw_path = str(source_path(physical["raw_path"]))
        c5_status_path = str(source_path(physical["status_path"]))
        c5_run_start_path = str(source_path(physical["run_start_path"]))
        b_raw_path = str(source_path(b_record["raw_path"]))
        b_status_path = str(source_path(b_record["run_status_path"]))
        parent_raw_sha = str(train["parent_cosine_gru_raw_sha256"])
        c5_raw_sha = str(physical["raw_sha256"])
        b_raw_sha = str(b_record["raw_sha256"])
        if str(parent_start.get("c5_raw_sha256", "")).lower() != c5_raw_sha.lower():
            raise ValueError(f"Parent run-start does not bind same-scene C5: {scene_id}")
        if str(parent_start.get("b_raw_sha256", "")).lower() != b_raw_sha.lower():
            raise ValueError(f"Parent run-start does not bind same-scene B: {scene_id}")
        if str(parent_start.get("payload_sha256", "")).lower() != str(train["payload_sha256"]).lower():
            raise ValueError(f"Parent run-start does not bind same-scene payload: {scene_id}")
        if parent_start.get("TEST_read", False) or parent_start.get("VAL_data_read", False):
            raise ValueError(f"Parent run-start reports TEST/VAL access: {scene_id}")

        b_status = verify_status(b_status_path, str(b_record["run_status_sha256"]), scene_id, b_raw_sha, role="B")
        c5_status = verify_status(c5_status_path, str(physical["status_sha256"]), scene_id, c5_raw_sha, role="C5")
        parent_status = verify_status(parent_status_path, str(train["parent_status_sha256"]), scene_id, parent_raw_sha, role="parent")
        if b_status.get("log_status") != "STABLE" or c5_status.get("status") != "RUN_COMPLETE_RAW_PENDING_AUDIT":
            raise ValueError(f"B/C5 comparator status is not accepted for {scene_id}")
        if parent_status.get("state") != "COMPLETED" or parent_status.get("status_value") != "STABLE":
            raise ValueError(f"Parent comparator is not stable for {scene_id}")
        if int(parent_status.get("Plant_calls", -1)) != 1:
            raise ValueError(f"Parent comparator does not record one completed call: {scene_id}")
        if str(c5_status.get("raw_sha256", "")).lower() != c5_raw_sha.lower():
            raise ValueError(f"C5 status raw hash mismatch: {scene_id}")

        matching_folds = [fold for fold in scene_folds if scene_id in fold["holdout_scene_ids"]]
        if len(matching_folds) != 1:
            raise ValueError(f"Scene does not belong to exactly one declared diagnostic fold: {scene_id}")
        fold = matching_folds[0]
        if scene_id in fold["train_scene_ids"]:
            raise ValueError(f"Scene is both train and holdout in fold {fold['fold_id']}: {scene_id}")

        binding = {
            "schema": "NO_POSITION_GRU_NOTCH_TRAIN24_SCENE_BINDING_V1",
            "source_split": "TRAIN_C5_24",
            "scene_id": scene_id,
            "source_order_zero_based": order,
            "scene_identity_sha256": identity,
            "diagnostic_fold_id": fold["fold_id"],
            "scene_payload": {"path": payload_path, "sha256": str(train["payload_sha256"])},
            "same_scene_comparators": {
                "B": {"raw_path": b_raw_path, "raw_sha256": b_raw_sha, "status_path": b_status_path, "status_sha256": str(b_record["run_status_sha256"])},
                "C5": {"raw_path": c5_raw_path, "raw_sha256": c5_raw_sha, "status_path": c5_status_path, "status_sha256": str(physical["status_sha256"]), "run_start_path": c5_run_start_path, "run_start_sha256": str(physical["run_start_sha256"])},
                "parent_cosine_gru": {"raw_path": parent_raw_path, "raw_sha256": parent_raw_sha, "status_path": parent_status_path, "status_sha256": str(train["parent_status_sha256"]), "run_start_path": parent_start_path, "run_start_sha256": parent_start_sha},
            },
            "shared_model_identity_sha256": digest_json(shared_models),
            "c5_common_position_options_sha256": common_position_options_sha256,
            "attempt": {
                "attempt_id": "attempt_01",
                "attempt_dir": str(HERE / "runs" / scene_id / "attempt_01"),
                "raw_path": str(HERE / "runs" / scene_id / "attempt_01" / "raw_run.mat"),
                "status_path": str(HERE / "runs" / scene_id / "attempt_01" / "run_status.json"),
                "run_start_path": str(HERE / "runs" / scene_id / "attempt_01" / "run_start.json"),
                "attempt_started_marker_path": str(HERE / "runs" / scene_id / "attempt_01" / "attempt_started.marker"),
                "first_plant_step_marker_path": str(HERE / "runs" / scene_id / "attempt_01" / "first_plant_step.marker"),
                "preflight_marker_path": str(HERE / "audits" / "preflight" / f"{scene_id}.json"),
                "score_path": str(HERE / "audits" / "scores" / f"{scene_id}.json"),
            },
        }
        binding["binding_sha256"] = digest_json(binding)
        bindings.append(binding)

    shared_identity = {
        "models": shared_models,
        "dataset_manifest": {"path": str(dataset_manifest_path), "sha256": cohort["dataset_manifest"]["sha256"]},
        "dataset": {"path": str(dataset_path), "sha256": cohort["dataset_path"]["sha256"]},
        "dataset_source_lock": {"path": str(source_lock_path), "sha256": cohort["dataset_source_lock"]["sha256"]},
        "physical_manifest": {"path": str(physical_manifest_path), "sha256": cohort["physical_manifest"]["sha256"]},
        "c5_input_lock": {"path": str(c5_input_lock_path), "sha256": cohort["c5_input_lock"]["sha256"]},
        "runtime_sources": runtime_sources,
        "frozen_scorer": {"path": str(scorer), "sha256": inputs["score_contract"]["scorer_sha256"]},
        "fixed_j0_helper": {"path": str(j0_helper), "sha256": inputs["fixed_controller"]["fixed_j0_helper"]["sha256"]},
    }
    result = {
        "schema": "NO_POSITION_GRU_NOTCH_TRAIN24_BATCH_BINDINGS_V1",
        "status": "PREPARED_NO_PLANT_INPUTS_LOCKED",
        "study_id": inputs["study_id"],
        "scope": inputs["scope"],
        "input_config_sha256": sha256_file(INPUT_PATH),
        "preparer_script_path": str(Path(__file__).resolve()),
        "preparer_script_sha256": sha256_file(Path(__file__).resolve()),
        "cohort": {"split": "TRAIN_C5_24", "scene_count": 24, "scene_ids": scene_ids},
        "shared_identity": shared_identity,
        "shared_identity_sha256": digest_json(shared_identity),
        "fixed_controller": inputs["fixed_controller"],
        "fixed_filter": fixed_filter,
        "attempt_policy": inputs["attempt_policy"],
        "score_contract": inputs["score_contract"],
        "interpretation_limit": manifest.get("parent_model_exposure", {}).get("limit", "TRAIN-only diagnostic; not independent validation."),
        "bindings": bindings,
    }
    with OUTPUT_PATH.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    print(f"Prepared {len(bindings)} scene bindings; Plant_calls=0; output={OUTPUT_PATH}")


if __name__ == "__main__":
    main()
