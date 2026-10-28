"""Read-only arithmetic review of the pinned matched-position label decomposition."""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports/attitude_position_context_probe_20261024"
DECOMPOSITION = REPORT / "offline_label_decomposition_v2/MATCHED_POSITION_LABEL_DECOMPOSITION_v2.json"
EVALUATION = REPORT / "frozen_a1_evaluation_v1/ROOT_FROZEN_A1_EVALUATION_v1.json"
OUTPUT_DIR = REPORT / "offline_label_decomposition_v2_review_v1"
OUTPUT_JSON = OUTPUT_DIR / "ROOT_MATCHED_POSITION_LABEL_REVIEW_v1.json"
OUTPUT_CSV = OUTPUT_DIR / "matched_position_label_summary_v1.csv"

PINS = {
    "decomposition_source_sha256": "5d26c8d70e0f78c6d54bbf68c9c9cc4c02dbf463ef2cf701e0dfb0ed7aa49742",
    "decomposition_taskbook_sha256": "69c329de945bced5ba67adc23baa243b50074e0b8625ff86b9f8a78bcaf3b945",
    "decomposition_audit_sha256": "9225d2dec302d8fc988c8c47cf93bb87868901961d2bcb193c400dd07d34a440",
    "decomposition_prepare_sha256": "1c0f260340dd806b1ca29d28aa8c0c87cea044a7c4da7549abebdb1d4314c3e4",
    "dataset_manifest_sha256": "7dd3e1f786f6095ecc2ba56473e5cf0fab6b92cdd42e38a184d6ad1223f36271",
    "input_manifest_sha256": "a5f7fea9b0918c1449af6fa83929177d3bf7d5e70cb3b71711c40f6338d210a5",
    "exporter_sha256": "ddb1684b1d720d9bee80b3bcda2c95bf855faee1220fc54e9ba764695c5a54a9",
    "runner_sha256": "f4e904c428c1c2f9cf778a172dd2bf46c5765990b62d195c365a2c3b90727699",
    "engine_sha256": "48350037b66efe00301b138068f187c62cf92583f0f9ba2fabc9b24f248a963c",
    "wrapper_sha256": "fcc1f5de659541e692483f8395d93fd2a251256286ebade5e510ed4c7a2e2330",
    "evaluation_source_sha256": "eef17013190f4f9b7272afda3dc1929164ac46839f5d94e9e75a6126dce03425",
    "deployment_sha256": "ee00c46af42cbce83a630ae9b03eaf1a86bfc6047910ed68bc4e7b8b020aa6ae",
    "checkpoint_sha256": "105585385157da3f1b404ab24606d0717287638e4a1ca710790633cd16d233a4",
    "normalizer_sha256": "7d969a9144ed9cfd519348ba831014981942f93b491539bc2c5732b8401c8592",
    "normalizer_float64_arrays_sha256": "9a150eb8c5fc005ed9b20d890f0f815c8eeaf107add543f3453eebf3c85a48ef",
}
MODEL_SOURCES = {
    "experiments/attitude_cm18_a1_20261024/train_cm18_a1_v1.py": "7544a04329bc1e06ff5d7a113a077033a65f0b7c2de8a6f1b25ac54710e62c76",
    "experiments/attitude_cm18_a1_20261024/cache_reader_cm18_v1.py": "a2867cbf516d7ed655a6f50e05b8600ffb7582e0f2164b1ce21d5e647adf2b47",
    "experiments/attitude_cm18_a1_20261024/model_cm18_v1.py": "ad32c4f97bf96c63172547c944d80c45062502f1062b774934e0f7a868720cf6",
    "experiments/attitude_cm18_a1_20261024/torch_model_cm18_v1.py": "bc9fe34fe957cb624438eeccfdfe2ddd38ad40cc9a4e706ce58863c9271d5aa0",
}
FLIGHTS = {
    "T1_B": {
        "scene_id": "DL1018_TRAIN_T1_C15_W14", "position_mode": "B_POSITION_RBF", "attempt_id": 2,
        "event_sha256": "574edcdc35483c6069bd053ae345a2ddee1c61780b7e044dea422b7b01fbf08c",
        "status_sha256": "b6e26264ffd7d4c86f1c78aaa734ec5ee9d77bb415273fc2657366bb77fa61e4",
        "raw_sha256": "e44d75f8fb784ed30f7b72057fda2183ad09c9286271b8db15cc3f5aeafd830a",
        "run_start_sha256": "88433eb2d15552e3a30310a6b80c763b31e1f7285436b38b3cdd88bf1fe8d83b",
        "release_sha256": "b770618d897463b779f60b97d5ace24cd128f776b8aff91445e67843a41806dd",
    },
    "T1_C5": {
        "scene_id": "DL1018_TRAIN_T1_C15_W14", "position_mode": "C5_POSITION_M110", "attempt_id": 1,
        "event_sha256": "6440649b1f6b45b483158d963e34f99ee6d5d47b961860422556f9c450f75749",
        "status_sha256": "9975f2e18c8a510544bc6e65ad173df9b606ac4160c5ce22e5d20829815b65b1",
        "raw_sha256": "0ed32edca581d98901cf1b92a4816e3c5870a2b4344a10ad4697f1b85c05c01f",
        "run_start_sha256": "753e83b6d01928d7bc91bf094ca842e8527afdf1e496f8e6002fb69da9679e76",
        "release_sha256": "c86e4a9467f39d32f1eb05c560dd969a47517a3a8eb9598f6107f9aa5b44231e",
    },
    "T3_B": {
        "scene_id": "DL1018_TRAIN_T3_C15_W14", "position_mode": "B_POSITION_RBF", "attempt_id": 1,
        "event_sha256": "bc5e8499347d071f736a5aa7a0a8d1173e3b9633aaeb2182b14256666d2f7594",
        "status_sha256": "fd6576d070dd36d60a94c3a083aedbcef0a6168213bd6047d09b9583605b381a",
        "raw_sha256": "195f48180d180f2760186b11a20170d92febf659a3340cf117eff5431d201aad",
        "run_start_sha256": "4446356de080a727889adede094f5760b9ad85896d6726389e96bd48f3c105c0",
        "release_sha256": "82b6b12f8a31e9c0865728a71827205979bd19f28d457765790f3eabe2eaaff7",
    },
    "T3_C5": {
        "scene_id": "DL1018_TRAIN_T3_C15_W14", "position_mode": "C5_POSITION_M110", "attempt_id": 1,
        "event_sha256": "27c5af24ac01f0ea90eb8a1138a8d947c9c568f945c64c05cced3da08117a7f4",
        "status_sha256": "028d204a6773389399b2ecd251268db02c1e02edc88fd8e01fab99aaf8d82a3f",
        "raw_sha256": "aebdb44f6119110c6faf0c87511a5f5b3b9736a1c8d2e7bc007b2c78965cb74a",
        "run_start_sha256": "2890f2c0998226145a5e4f320b9264bf6604ef08e1ccaa7a9afbfd6a5d3aaadb",
        "release_sha256": "1c794dea4f4b549db4d6eeb10387e2ef228f9457cb89fd3c44579fbdcb3f3ea5",
    },
}
COMPONENTS = (
    "nominal_transfer", "old_compensation_transfer", "gyro_jdot", "wind", "request_gap", "realized_gap"
)
PHASES = {0: "STATIC", 1: "PRE", 2: "EXTEND", 3: "HOLD", 4: "RETRACT", 5: "RECOVERY"}
N_EVENTS = 1999
TOL_SUM = 1e-8
TOL_DIRECT = 1e-8
TOL_STATS = 1e-10


def need(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as stream:
        return json.load(stream)


def vector(value: Any, name: str, dtype: Any = np.float64) -> np.ndarray:
    array = np.asarray(value, dtype=dtype).reshape(-1)
    need(np.isfinite(array).all() if np.issubdtype(array.dtype, np.number) else True,
         f"{name} has non-finite values")
    return array


def matrix(value: Any, shape: tuple[int, int], name: str) -> np.ndarray:
    array = np.asarray(value, dtype=np.float64)
    need(array.shape == shape and np.isfinite(array).all(), f"{name} shape/value mismatch: {array.shape}")
    return array


def close(name: str, actual: float, expected: float, tol: float = TOL_STATS) -> float:
    delta = abs(float(actual) - float(expected))
    need(math.isfinite(delta) and delta <= tol, f"{name} differs: {actual} vs {expected} (tol {tol})")
    return delta


def check_scalar(value: Any, expected: float, name: str, tol: float = TOL_STATS) -> float:
    need(isinstance(value, (int, float)) and math.isfinite(float(value)), f"{name} is not a finite scalar")
    return close(name, float(value), expected, tol)


def pair_names() -> list[tuple[str, str]]:
    return [(COMPONENTS[i], COMPONENTS[j]) for i in range(6) for j in range(i + 1, 6)]


def check_summary(summary: dict[str, Any], group_name: str, phase_code: int,
                  component_values: np.ndarray, target: np.ndarray) -> tuple[dict[str, Any], list[dict[str, Any]], float]:
    count = int(target.size)
    need(summary.get("phase") == group_name and int(summary.get("phase_code", -999)) == phase_code and
         int(summary.get("event_count", -1)) == count,
         f"{group_name}: summary label/count mismatch")
    residual = component_values.sum(axis=1) - target if count else np.empty(0)
    stats = summary.get("components", [])
    expected_pairs = pair_names()
    pairs = summary.get("pairwise_mean_products", [])
    need(len(stats) == len(COMPONENTS), f"{group_name}: expected six component statistics")
    pair_rows: list[dict[str, Any]] = []
    group_result: dict[str, Any] = {
        "group": group_name, "phase_code": phase_code, "event_count": count,
        "max_abs_label_closure": float(np.max(np.abs(residual))) if count else None,
        "components": [], "pairwise_mean_products": [],
    }
    max_stat_error = 0.0
    expanded = 0.0
    if count:
        means = component_values.mean(axis=0)
        second = np.mean(component_values ** 2, axis=0)
        rms = np.sqrt(second)
        for i, name in enumerate(COMPONENTS):
            row = stats[i]
            need(row.get("name") == name, f"{group_name}: component order/name mismatch at {i}")
            max_stat_error = max(max_stat_error, check_scalar(row.get("mean"), means[i], f"{group_name}.{name}.mean"))
            max_stat_error = max(max_stat_error, check_scalar(row.get("second_moment"), second[i], f"{group_name}.{name}.second_moment"))
            max_stat_error = max(max_stat_error, check_scalar(row.get("rms"), rms[i], f"{group_name}.{name}.rms"))
            group_result["components"].append({"name": name, "mean": float(means[i]),
                "second_moment": float(second[i]), "rms": float(rms[i])})
            expanded += float(second[i])
        need(len(pairs) == 15, f"{group_name}: expected all 15 cross-products")
        for pair_index, (left, right) in enumerate(expected_pairs):
            pair = pairs[pair_index]
            need(pair.get("first") == left and pair.get("second") == right,
                 f"{group_name}: cross-product ordering mismatch at {pair_index}")
            product = float(np.mean(component_values[:, COMPONENTS.index(left)] *
                                    component_values[:, COMPONENTS.index(right)]))
            max_stat_error = max(max_stat_error, check_scalar(pair.get("mean_product"), product,
                  f"{group_name}.{left}*{right}"))
            expanded += 2.0 * product
            item = {"first": left, "second": right, "mean_product": product}
            pair_rows.append(item)
            group_result["pairwise_mean_products"].append(item)
        target_mean = float(np.mean(target))
        target_second = float(np.mean(target ** 2))
        target_rms = math.sqrt(target_second)
        expansion_error = expanded - target_second
        max_stat_error = max(max_stat_error, check_scalar(summary.get("target_mean"), target_mean,
                              f"{group_name}.target_mean"))
        max_stat_error = max(max_stat_error, check_scalar(summary.get("target_second_moment"), target_second,
                              f"{group_name}.target_second_moment"))
        max_stat_error = max(max_stat_error, check_scalar(summary.get("target_rms"), target_rms,
                              f"{group_name}.target_rms"))
        max_stat_error = max(max_stat_error, check_scalar(summary.get("expanded_sum_second_moment"),
                              expanded, f"{group_name}.expanded_sum_second_moment"))
        max_stat_error = max(max_stat_error, check_scalar(summary.get("second_moment_expansion_error"),
                              expansion_error, f"{group_name}.second_moment_expansion_error"))
        check_scalar(summary.get("max_abs_closure_residual"), float(np.max(np.abs(residual))),
                     f"{group_name}.max_abs_closure_residual", TOL_SUM)
        need(abs(expansion_error) <= TOL_SUM, f"{group_name}: six-term second-moment expansion fails")
        need(float(np.max(np.abs(residual))) <= TOL_SUM, f"{group_name}: six-term target closure fails")
        group_result.update({"target_mean": target_mean, "target_second_moment": target_second,
            "target_rms": target_rms, "expanded_sum_second_moment": expanded,
            "second_moment_expansion_error": expansion_error})
    else:
        need(not pairs, f"{group_name}: empty phase unexpectedly has cross-products")
        for row in stats:
            need(row.get("mean") == [] and row.get("second_moment") == [] and row.get("rms") == [],
                 f"{group_name}: empty phase component stats must remain empty")
        for field in ("expanded_sum_second_moment", "target_mean", "target_second_moment",
                      "target_rms", "second_moment_expansion_error", "max_abs_closure_residual"):
            need(summary.get(field) == [], f"{group_name}: empty phase field {field} must remain empty")
    return group_result, pair_rows, max_stat_error


def validate_evaluation(evaluation: dict[str, Any]) -> dict[str, Any]:
    need(evaluation.get("schema") == "ROOT_MATCHED_POSITION_FROZEN_A1_EVALUATION_V1" and
         evaluation.get("status") == "PASS_GATES", "Frozen A1 evaluation is not PASS_GATES")
    identity = evaluation.get("identity", {})
    expected = {
        "deployment_sha256": PINS["deployment_sha256"],
        "checkpoint_sha256": PINS["checkpoint_sha256"],
        "normalizer_sha256": PINS["normalizer_sha256"],
        "normalizer_float64_arrays_sha256": PINS["normalizer_float64_arrays_sha256"],
        "event_exporter_sha256": PINS["exporter_sha256"],
        "raw_audit_sha256": PINS["decomposition_audit_sha256"],
        "taskbook_sha256": PINS["decomposition_taskbook_sha256"],
        "input_manifest_sha256": PINS["input_manifest_sha256"],
        "dataset_manifest_sha256": PINS["dataset_manifest_sha256"],
    }
    for field, pin in expected.items():
        need(str(identity.get(field, "")).lower() == pin, f"A1 evaluation identity mismatch: {field}")
    need(int(identity.get("selected_step", -1)) == 30000 and identity.get("model_source_files") == MODEL_SOURCES,
         "Frozen A1 checkpoint step or model source set mismatch")
    expected_sources = dict(MODEL_SOURCES)
    expected_sources["experiments/attitude_position_context_probe_20261024/evaluate_frozen_a1_matched_position_probe_v1.py"] = PINS["evaluation_source_sha256"]
    actual_sources = identity.get("source_files", {})
    for relative, expected_sha in expected_sources.items():
        need(str(actual_sources.get(relative, "")).lower() == expected_sha,
             f"A1 evaluation source reference mismatch: {relative}")
    return identity


def build_csv_rows(flight: str, scene: dict[str, Any], groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for group in groups:
        row: dict[str, Any] = {
            "flight_id": flight, "scene_id": scene["scene_id"], "position_mode": scene["position_mode"],
            "group": group["group"], "phase_code": group["phase_code"], "event_count": group["event_count"],
            "max_abs_label_closure": group["max_abs_label_closure"],
            "target_mean": group.get("target_mean"), "target_second_moment": group.get("target_second_moment"),
            "target_rms": group.get("target_rms"),
            "expanded_sum_second_moment": group.get("expanded_sum_second_moment"),
            "second_moment_expansion_error": group.get("second_moment_expansion_error"),
        }
        for component in group["components"]:
            name = component["name"]
            row[f"{name}_mean"] = component["mean"]
            row[f"{name}_second_moment"] = component["second_moment"]
            row[f"{name}_rms"] = component["rms"]
        for pair in group["pairwise_mean_products"]:
            row[f"cross_{pair['first']}__{pair['second']}_mean_product"] = pair["mean_product"]
        rows.append(row)
    return rows


def run() -> dict[str, Any]:
    need(not OUTPUT_DIR.exists() and not OUTPUT_JSON.exists() and not OUTPUT_CSV.exists(),
         f"Refusing to overwrite review outputs: {OUTPUT_DIR}")
    need(EVALUATION.is_file(), f"Missing frozen A1 evaluation: {EVALUATION}")
    need(DECOMPOSITION.is_file(), f"Missing final V2 decomposition: {DECOMPOSITION}")
    decomposition_sha = sha256(DECOMPOSITION)
    evaluation_sha = sha256(EVALUATION)
    need(sha256(ROOT / "experiments/attitude_position_context_probe_20261024/evaluate_frozen_a1_matched_position_probe_v1.py") ==
         PINS["evaluation_source_sha256"],
         "Frozen A1 evaluation source SHA mismatch")
    evaluation = load_json(EVALUATION)
    evaluation_identity = validate_evaluation(evaluation)
    decomposition = load_json(DECOMPOSITION)
    need(decomposition.get("schema") == "MATCHED_POSITION_LABEL_DECOMPOSITION_V2" and
         decomposition.get("status") == "PASS", "Physical decomposition report is not PASS/V2")
    need(decomposition.get("component_names") == list(COMPONENTS), "Six-term component order/name mismatch")
    need(str(decomposition.get("source_sha256", "")).lower() == PINS["decomposition_source_sha256"],
         "Decomposition source SHA mismatch")
    for field, pin in (("taskbook_sha256", PINS["decomposition_taskbook_sha256"]),
                       ("raw_audit_sha256", PINS["decomposition_audit_sha256"]),
                       ("prepare_result_sha256", PINS["decomposition_prepare_sha256"]),
                       ("dataset_manifest_sha256", PINS["dataset_manifest_sha256"]),
                       ("event_exporter_source_sha256", PINS["exporter_sha256"]),
                       ("position_engine_sha256", PINS["engine_sha256"]),
                       ("position_episode_wrapper_sha256", PINS["wrapper_sha256"])):
        need(str(decomposition.get(field, "")).lower() == pin, f"Decomposition provenance mismatch: {field}")
    scope = decomposition.get("scope", {})
    need(scope.get("events_per_flight") == N_EVENTS and scope.get("training_steps") == 0 and
         scope.get("optimizer_steps") == 0 and scope.get("plant_calls") == 0 and
         scope.get("TEST_accessed") is False and scope.get("old_B_raw_or_H5_read") is False,
         "Decomposition scope metadata mismatch")
    scene_rows = decomposition.get("scenes", [])
    need(len(scene_rows) == 4, "Decomposition must contain exactly four flights")
    scenes = {row.get("flight_id"): row for row in scene_rows}
    need(set(scenes) == set(FLIGHTS), "Decomposition flight set mismatch")
    eval_identity_exports = evaluation_identity.get("event_export_sha256_by_flight", {})
    eval_identity_raw = evaluation_identity.get("raw_sha256_by_flight", {})
    eval_identity_status = evaluation_identity.get("status_sha256_by_flight", {})
    eval_rows = evaluation.get("raw_event_exports", {})
    summaries: dict[str, Any] = {}
    csv_rows: list[dict[str, Any]] = []
    maximums: dict[str, float] = {"label_sum": 0.0, "direct_target": 0.0, "summary_stat": 0.0}
    for flight, contract in FLIGHTS.items():
        scene = scenes[flight]
        for field in ("scene_id", "position_mode", "attempt_id", "status_sha256", "raw_sha256",
                      "run_start_sha256", "release_sha256", "event_export_sha256"):
            expected = contract["event_sha256" if field == "event_export_sha256" else field]
            actual = scene.get(field)
            if field.endswith("sha256"):
                expected = expected.lower()
                actual = str(actual or "").lower()
            need(actual == expected, f"{flight}: decomposition {field} does not match pinned contract")
        need(scene.get("split") == "TRAIN" and int(scene.get("event_count", -1)) == N_EVENTS,
             f"{flight}: split or event count mismatch")
        need(str(eval_identity_exports.get(flight, "")).lower() == contract["event_sha256"],
             f"{flight}: A1 evaluator event export SHA differs from physical decomposition")
        need(str(eval_identity_raw.get(flight, "")).lower() == contract["raw_sha256"] and
             str(eval_identity_status.get(flight, "")).lower() == contract["status_sha256"],
             f"{flight}: A1 evaluator raw/status identity differs")
        eval_event = eval_rows.get(flight, {})
        need(str(eval_event.get("file_sha256", "")).lower() == contract["event_sha256"],
             f"{flight}: evaluator event payload SHA differs")
        need(eval_event.get("identity", {}).get("scene_id") == contract["scene_id"] and
             eval_event.get("identity", {}).get("position_mode") == contract["position_mode"] and
             int(eval_event.get("identity", {}).get("attempt_id", -1)) == contract["attempt_id"],
             f"{flight}: evaluator event identity mismatch")
        records = scene.get("event_records", {})
        plant_index = vector(records.get("plant_index", []), f"{flight}.plant_index", np.int64)
        event_time = vector(records.get("event_time_s", []), f"{flight}.event_time_s")
        phase_code = vector(records.get("phase_code", []), f"{flight}.phase_code", np.int64)
        target = matrix(records.get("target_raw_rad_s2", []), (N_EVENTS, 3), f"{flight}.target_raw_rad_s2")
        direct = matrix(records.get("target_direct_rad_s2", []), (N_EVENTS, 3), f"{flight}.target_direct_rad_s2")
        components = matrix(records.get("components_yaw_rad_s2", []), (N_EVENTS, 6), f"{flight}.components_yaw_rad_s2")
        recorded_sum = vector(records.get("component_sum_yaw_rad_s2", []), f"{flight}.component_sum_yaw_rad_s2")
        recorded_residual = vector(records.get("closure_residual_yaw_rad_s2", []), f"{flight}.closure_residual_yaw_rad_s2")
        need(plant_index.shape == (N_EVENTS,) and np.array_equal(plant_index, np.arange(11, 19992, 10)),
             f"{flight}: plant event indices mismatch")
        need(event_time.shape == (N_EVENTS,) and np.max(np.abs(event_time - np.arange(1, 2000) / 100.0)) <= 1e-12,
             f"{flight}: event times mismatch")
        need(phase_code.shape == (N_EVENTS,) and np.all((phase_code >= 0) & (phase_code <= 5)),
             f"{flight}: phase codes mismatch")
        summed = components.sum(axis=1)
        residual = summed - target[:, 2]
        label_closure = float(np.max(np.abs(residual)))
        direct_closure = float(np.max(np.abs(direct - target)))
        need(label_closure <= TOL_SUM and direct_closure <= TOL_DIRECT,
             f"{flight}: event-level label/direct closure exceeded tolerance")
        need(np.max(np.abs(recorded_sum - summed)) <= TOL_STATS and
             np.max(np.abs(recorded_residual - residual)) <= TOL_STATS,
             f"{flight}: stored event closure vectors disagree")
        need(abs(label_closure - float(scene["max_abs_six_term_yaw_label_closure_rad_s2"])) <= TOL_STATS and
             abs(direct_closure - float(scene["max_abs_direct_physics_vs_export_target_rad_s2"])) <= TOL_STATS,
             f"{flight}: closure maxima disagree with scene summary")
        eval_event_phase = vector(eval_event.get("phase_code", []), f"{flight}.evaluator.phase_code", np.int64)
        eval_event_plant = vector(eval_event.get("plant_index", []), f"{flight}.evaluator.plant_index", np.int64)
        eval_target = matrix(eval_event.get("target", []), (N_EVENTS, 3), f"{flight}.evaluator.target")
        need(np.array_equal(eval_event_phase, phase_code) and np.array_equal(eval_event_plant, plant_index) and
             np.max(np.abs(eval_target - target)) <= TOL_STATS,
             f"{flight}: event phase/index/target differs from the frozen A1 evaluator reference")
        maximums["label_sum"] = max(maximums["label_sum"], label_closure)
        maximums["direct_target"] = max(maximums["direct_target"], direct_closure)
        group_outputs: list[dict[str, Any]] = []
        all_result, _, stat_error = check_summary(scene.get("overall_summary", {}), "ALL", -1, components, target[:, 2])
        maximums["summary_stat"] = max(maximums["summary_stat"], stat_error)
        group_outputs.append(all_result)
        phase_summaries = scene.get("phase_summary", [])
        need(len(phase_summaries) == 6, f"{flight}: expected six phase summaries")
        for code, phase_name in PHASES.items():
            mask = phase_code == code
            summary = next((item for item in phase_summaries if item.get("phase") == phase_name), None)
            need(summary is not None, f"{flight}: missing phase summary {phase_name}")
            phase_result, _, stat_error = check_summary(summary, phase_name, code, components[mask], target[mask, 2])
            maximums["summary_stat"] = max(maximums["summary_stat"], stat_error)
            group_outputs.append(phase_result)
        summaries[flight] = {
            "scene_id": contract["scene_id"], "position_mode": contract["position_mode"],
            "attempt_id": contract["attempt_id"], "event_export_sha256": contract["event_sha256"],
            "raw_sha256": contract["raw_sha256"], "event_count": N_EVENTS,
            "max_abs_six_term_yaw_label_closure_rad_s2": label_closure,
            "max_abs_direct_target_all_axis_difference_rad_s2": direct_closure,
            "groups": group_outputs,
        }
        csv_rows.extend(build_csv_rows(flight, contract, group_outputs))
    source_path = Path(__file__).resolve()
    result = {
        "schema": "ROOT_MATCHED_POSITION_LABEL_ARITHMETIC_REVIEW_V1",
        "status": "PASS",
        "identity": {
            "review_source_path": str(source_path.relative_to(ROOT)).replace("\\", "/"),
            "review_source_sha256": sha256(source_path),
            "decomposition_path": str(DECOMPOSITION.relative_to(ROOT)).replace("\\", "/"),
            "decomposition_sha256": decomposition_sha,
            "decomposition_source_sha256": PINS["decomposition_source_sha256"],
            "frozen_a1_evaluation_path": str(EVALUATION.relative_to(ROOT)).replace("\\", "/"),
            "frozen_a1_evaluation_sha256": evaluation_sha,
            "a1_deployment_sha256": PINS["deployment_sha256"], "a1_checkpoint_sha256": PINS["checkpoint_sha256"],
            "a1_selected_step": 30000, "event_export_sha256_by_flight": eval_identity_exports,
        },
        "scope": {"flights": list(FLIGHTS), "events_per_flight": N_EVENTS, "events_total": 4 * N_EVENTS,
            "raw_mat_read": False, "TEST_accessed": False, "training_steps": 0, "optimizer_steps": 0,
            "plant_calls": 0, "model_forward_calls": 0,
            "method": "Recompute arithmetic from the final decomposition JSON and compare event export/model references in the frozen A1 evaluator JSON; no raw/cache/model forward is opened or executed.",
            "interpretation_limit": "RMS values and cross-products are descriptive moment terms; this report does not express them as causal percentages."},
        "tolerances": {"event_label_sum_abs": TOL_SUM, "direct_target_all_axis_abs": TOL_DIRECT,
            "summary_stat_abs": TOL_STATS},
        "maxima": maximums,
        "flights": summaries,
    }
    return result, csv_rows


def main() -> None:
    result, rows = run()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=False)
    with OUTPUT_JSON.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    columns = ["flight_id", "scene_id", "position_mode", "group", "phase_code", "event_count",
               "max_abs_label_closure", "target_mean", "target_second_moment", "target_rms",
               "expanded_sum_second_moment", "second_moment_expansion_error"]
    for name in COMPONENTS:
        columns.extend([f"{name}_mean", f"{name}_second_moment", f"{name}_rms"])
    columns.extend(f"cross_{left}__{right}_mean_product" for left, right in pair_names())
    with OUTPUT_CSV.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({"status": result["status"], "json": str(OUTPUT_JSON), "csv": str(OUTPUT_CSV),
                      "events_total": result["scope"]["events_total"], "maxima": result["maxima"]}, indent=2))


if __name__ == "__main__":
    main()
