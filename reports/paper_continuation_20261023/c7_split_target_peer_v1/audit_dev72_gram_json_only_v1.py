from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
INPUT = ROOT / "reports/paper_continuation_20261023/dev_physical_response_decomposition_v1/DEV72_RESPONSE_GRAM_v2.json"
OUTPUT = Path(__file__).with_name("DEV72_GRAM_REAGGREGATION_RECEIPT_v1.json")
EXPECTED_INPUT_SHA256 = "855f1570cc6f4ac8ff2040b81c7b19c49c2a08ceda3dd3cce297cfbf2c186657"
EXPECTED_SOURCE_SHA256 = "d28fffa821adf038568580c286c6c665001a082a49a1bf6f65a24c183a81dc46"
PHASE_COUNTS = {"0_20s": 20_000, "0_5s": 5_000, "5_20s": 15_000}
AXES = ("x", "y", "z", "xyz")
CHANNELS = 9
SCENE_RE = re.compile(r"DL1018_(DEV|VAL)_T([1-3])_C\d+_W(\d{2})\Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def matrix(data: list[list[float]]) -> list[list[float]]:
    if len(data) != CHANNELS or any(len(row) != CHANNELS for row in data):
        raise ValueError("Expected a 9x9 Gram matrix")
    return [[float(value) for value in row] for row in data]


def matrix_mean(values: list[list[list[float]]]) -> list[list[float]]:
    count = len(values)
    return [
        [sum(value[i][j] for value in values) / count for j in range(CHANNELS)]
        for i in range(CHANNELS)
    ]


def matrix_sum(value: list[list[float]]) -> float:
    return sum(sum(row) for row in value)


def max_matrix_difference(a: list[list[float]], b: list[list[float]]) -> float:
    return max(abs(a[i][j] - b[i][j]) for i in range(CHANNELS) for j in range(CHANNELS))


def grouped_energy(g: list[list[float]]) -> dict[str, float]:
    epsilon = (5, 6, 7)
    masked = (8,)
    active = epsilon + masked
    epsilon_m2 = sum(g[i][j] for i in epsilon for j in epsilon)
    masked_m2 = sum(g[i][j] for i in masked for j in masked)
    cross_m2 = 2.0 * sum(g[i][j] for i in epsilon for j in masked)
    active_m2 = sum(g[i][j] for i in active for j in active)
    return {
        "epsilonM_m2": epsilon_m2,
        "masked_pcf_m2": masked_m2,
        "cross_epsilonM_masked_pcf_m2": cross_m2,
        "physical_active_epsilonM_plus_masked_pcf_m2": active_m2,
    }


def expected_groups(scene_id: str) -> set[str]:
    match = SCENE_RE.fullmatch(scene_id)
    if match is None:
        raise ValueError(f"Unexpected non-DEV/VAL scene ID: {scene_id}")
    _, task, wind = match.groups()
    groups = {"ALL72", f"T{task}"}
    if 9 <= int(wind) <= 14:
        groups.add("HF_W09_W14")
    if int(wind) == 15:
        groups.add("W15")
    return groups


def main() -> None:
    if sha256(INPUT) != EXPECTED_INPUT_SHA256:
        raise ValueError("Pinned DEV72 response JSON SHA256 mismatch")
    data = json.loads(INPUT.read_text(encoding="utf-8-sig"))
    if data.get("source_sha256") != EXPECTED_SOURCE_SHA256:
        raise ValueError("Response JSON does not name the pinned v2 source")
    scenes = data.get("scenes")
    if not isinstance(scenes, list) or len(scenes) != 72:
        raise ValueError("Expected exactly 72 DEV/VAL scene rows")
    ids = [scene.get("scene_id") for scene in scenes]
    if len(set(ids)) != 72:
        raise ValueError("Duplicate or missing scene IDs")

    split_counts = {"DEV": 0, "VAL": 0}
    max_scene_symmetry = 0.0
    max_xyz_gram_sum = 0.0
    max_scene_q_squared_closure = 0.0
    max_parent_q_difference = 0.0
    max_parent_phase_q_difference = 0.0
    max_group_gram_difference = 0.0
    max_group_pooled_rmse_difference = 0.0
    max_group_scene_mean_difference = 0.0
    max_group_scene_rms_difference = 0.0
    max_group_energy_difference = 0.0
    max_group_active_identity_residual = 0.0

    for scene in scenes:
        scene_id = scene["scene_id"]
        match = SCENE_RE.fullmatch(scene_id)
        if match is None:
            raise ValueError(f"Non-DEV/VAL scene in output: {scene_id}")
        split_counts[match.group(1)] += 1
        groups = expected_groups(scene_id)
        if set(scene["groups"]) != groups:
            raise ValueError(f"Incorrect group assignment for {scene_id}")
        for phase, expected_count in PHASE_COUNTS.items():
            item = scene["by_phase"][phase]
            if item["sample_count"] != expected_count:
                raise ValueError(f"Incorrect scoring count in {scene_id}/{phase}")
            grams = {axis: matrix(item["gram_m2"][axis]) for axis in AXES}
            for axis in AXES:
                g = grams[axis]
                for i in range(CHANNELS):
                    for j in range(CHANNELS):
                        max_scene_symmetry = max(max_scene_symmetry, abs(g[i][j] - g[j][i]))
                q = float(item["rmse_m"][axis])
                max_scene_q_squared_closure = max(
                    max_scene_q_squared_closure, abs(q * q - matrix_sum(g))
                )
            for i in range(CHANNELS):
                for j in range(CHANNELS):
                    xyz_sum = grams["x"][i][j] + grams["y"][i][j] + grams["z"][i][j]
                    max_xyz_gram_sum = max(max_xyz_gram_sum, abs(grams["xyz"][i][j] - xyz_sum))
            reported_energy = item["grouped_response_energy_m2"]
            for axis in AXES:
                calc = grouped_energy(grams[axis])
                for key, value in calc.items():
                    max_group_energy_difference = max(
                        max_group_energy_difference, abs(value - float(reported_energy[axis][key]))
                    )
                identity = calc["epsilonM_m2"] + calc["masked_pcf_m2"] + calc["cross_epsilonM_masked_pcf_m2"]
                max_group_active_identity_residual = max(
                    max_group_active_identity_residual,
                    abs(calc["physical_active_epsilonM_plus_masked_pcf_m2"] - identity),
                )

        max_parent_q_difference = max(
            max_parent_q_difference,
            abs(float(scene["parent_Q_0_20_m"]) - float(scene["reconstructed_Q_0_20_m"])),
        )
        for phase in ("0_5s", "5_20s"):
            max_parent_phase_q_difference = max(
                max_parent_phase_q_difference,
                float(scene["parent_phase_Q_checks"][phase]["absolute_difference_m"]),
            )

    if split_counts != {"DEV": 24, "VAL": 48}:
        raise ValueError(f"Unexpected split counts: {split_counts}")

    expected_group_names = ("ALL72", "HF_W09_W14", "W15", "T1", "T2", "T3")
    group_counts = {}
    for group_name in expected_group_names:
        if group_name == "ALL72":
            selected = scenes
        else:
            selected = [scene for scene in scenes if group_name in expected_groups(scene["scene_id"])]
        output_group = data["groups"][group_name]
        group_counts[group_name] = len(selected)
        if output_group["scene_count"] != len(selected):
            raise ValueError(f"Incorrect count for {group_name}")
        if set(output_group["scene_ids"]) != {scene["scene_id"] for scene in selected}:
            raise ValueError(f"Incorrect membership for {group_name}")

        for phase, expected_count in PHASE_COUNTS.items():
            out = output_group["by_phase"][phase]
            if out["sample_count_per_scene"] != expected_count:
                raise ValueError(f"Incorrect phase count for {group_name}/{phase}")
            phase_rows = [scene["by_phase"][phase] for scene in selected]
            for axis in AXES:
                grams = [matrix(row["gram_m2"][axis]) for row in phase_rows]
                average = matrix_mean(grams)
                reported = matrix(out["gram_m2"][axis])
                max_group_gram_difference = max(
                    max_group_gram_difference, max_matrix_difference(average, reported)
                )
                pooled = math.sqrt(max(matrix_sum(average), 0.0))
                max_group_pooled_rmse_difference = max(
                    max_group_pooled_rmse_difference,
                    abs(pooled - float(out["pooled_rmse_m"][axis])),
                )
                scene_mean = sum(float(row["rmse_m"][axis]) for row in phase_rows) / len(phase_rows)
                max_group_scene_mean_difference = max(
                    max_group_scene_mean_difference,
                    abs(scene_mean - float(out["scene_equal_mean_rmse_m"][axis])),
                )
                if axis == "xyz":
                    qs = [float(row["rmse_m"]["xyz"]) for row in phase_rows]
                    scene_rms = math.sqrt(sum(q * q for q in qs) / len(qs))
                    max_group_scene_rms_difference = max(
                        max_group_scene_rms_difference,
                        abs(scene_rms - float(out["scene_equal_rms_Q_m"])),
                    )
                    max_group_scene_mean_difference = max(
                        max_group_scene_mean_difference,
                        abs(scene_mean - float(out["scene_equal_mean_Q_m"])),
                    )
                calc = grouped_energy(average)
                for key, value in calc.items():
                    max_group_energy_difference = max(
                        max_group_energy_difference,
                        abs(value - float(out["grouped_response_energy_m2"][axis][key])),
                    )
                identity = calc["epsilonM_m2"] + calc["masked_pcf_m2"] + calc["cross_epsilonM_masked_pcf_m2"]
                max_group_active_identity_residual = max(
                    max_group_active_identity_residual,
                    abs(calc["physical_active_epsilonM_plus_masked_pcf_m2"] - identity),
                )

    checks = {
        "max_scene_gram_symmetry_abs": max_scene_symmetry,
        "max_scene_xyz_gram_sum_abs": max_xyz_gram_sum,
        "max_scene_Q_squared_closure_abs_m2": max_scene_q_squared_closure,
        "max_scene_full_Q_parent_abs_m": max_parent_q_difference,
        "max_scene_phase_Q_parent_abs_m": max_parent_phase_q_difference,
        "max_group_mean_gram_abs": max_group_gram_difference,
        "max_group_pooled_RMSE_abs_m": max_group_pooled_rmse_difference,
        "max_group_scene_mean_abs_m": max_group_scene_mean_difference,
        "max_group_scene_RMS_abs_m": max_group_scene_rms_difference,
        "max_group_energy_abs_m2": max_group_energy_difference,
        "max_group_active_energy_identity_abs_m2": max_group_active_identity_residual,
    }
    if any(value > 1e-12 for value in checks.values()):
        raise ValueError(f"Independent reaggregation failed tolerance: {checks}")
    if OUTPUT.exists():
        raise FileExistsError(f"Refusing to overwrite {OUTPUT}")

    receipt = {
        "status": "PASS_DEV72_JSON_ONLY_GRAM_REAGGREGATION",
        "method": "Independent standard-library reaggregation from the pinned DEV72 per-scene JSON Gram/Q records; no raw scene files were opened or replayed.",
        "input_json": INPUT.relative_to(ROOT).as_posix(),
        "input_json_sha256": sha256(INPUT),
        "input_generator_sha256": data["source_sha256"],
        "review_script_sha256": sha256(Path(__file__)),
        "split_counts": split_counts,
        "group_counts": group_counts,
        "phase_sample_counts_per_scene": PHASE_COUNTS,
        "test_scene_ids_present": False,
        "checks_abs_error_max": checks,
        "scope_limit": "Fixed-path descriptive attribution only; no counterfactual, causal, candidate-selection, TEST, or novelty inference.",
    }
    OUTPUT.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == "__main__":
    main()
