from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
PARENT = ROOT / "reports/paper_continuation_20261023/c5_dev72_parent_review/C5_DEV72_RAW_PARENT_REVIEW_v3.json"
DATA_ROOTS = (ROOT / "experiments/position_axis_coordinate_c5_dev72_20261023", ROOT / "experiments/position_axis_coordinate_c5_20261023")
OUTPUT = Path(__file__).with_name("DEV72_RESPONSE_GRAM_v2.json")

PARENT_SHA256 = "bb34889559d95a1c995d4d420e3b3d7a702908b58b47cce969dc508a1c697fab"
DT = 0.001
N = 20_000
STATE_N = N + 1
A11, A12, A21, A22 = 0.999, 0.001, -0.001, 0.996
CHANNELS = [
    "initial",
    "sampling_position",
    "sampling_surface",
    "pre_ready",
    "tail",
    "prediction",
    "ramp_and_interval",
    "head_clip",
    "masked_pcf",
]
AXIS_NAMES = ("x", "y", "z")
PHASES = (("0_20s", 0, 20_000), ("0_5s", 0, 5_000), ("5_20s", 5_000, 20_000))
SCENE_RE = re.compile(r"DL1018_(?:DEV|VAL)_T([1-3])_C\d+_W(\d{2})\Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_matlab_array(group: h5py.Group, name: str) -> np.ndarray:
    value = np.asarray(group[name])
    return value.T if value.ndim == 2 else value


def max_abs(value: np.ndarray) -> float:
    return float(np.max(np.abs(value))) if value.size else 0.0


def phase_summary(response: np.ndarray, start: int, end: int) -> dict:
    # response is state response in metres: [sample, channel, axis].
    values = response[start:end]
    count = int(end - start)
    grams = {}
    for axis_index, axis_name in enumerate(AXIS_NAMES):
        matrix = values[:, :, axis_index]
        grams[axis_name] = (matrix.T @ matrix / count).tolist()
    grams["xyz"] = (
        np.asarray(grams["x"]) + np.asarray(grams["y"]) + np.asarray(grams["z"])
    ).tolist()

    arrays = {key: np.asarray(value, dtype=np.float64) for key, value in grams.items()}
    rmse = {
        key: float(np.sqrt(max(float(matrix.sum()), 0.0)))
        for key, matrix in arrays.items()
    }

    # F1/F2's delayed target y cancels in their sum. Keep the interpretable
    # grouped response alongside raw channel Gram so target splitting is not
    # mistaken for independently meaningful energy attribution.
    epsilon_indices = (5, 6, 7)  # prediction + ramp_and_interval + head_clip
    masked_indices = (8,)
    active_indices = epsilon_indices + masked_indices
    grouped_energy = {}
    for key, matrix in arrays.items():
        epsilon_m2 = float(matrix[np.ix_(epsilon_indices, epsilon_indices)].sum())
        masked_m2 = float(matrix[np.ix_(masked_indices, masked_indices)].sum())
        active_m2 = float(matrix[np.ix_(active_indices, active_indices)].sum())
        cross_m2 = float(2.0 * matrix[np.ix_(epsilon_indices, masked_indices)].sum())
        grouped_energy[key] = {
            "epsilonM_m2": epsilon_m2,
            "masked_pcf_m2": masked_m2,
            "physical_active_epsilonM_plus_masked_pcf_m2": active_m2,
            "cross_epsilonM_masked_pcf_m2": cross_m2,
        }

    return {
        "sample_count": count,
        "gram_m2": grams,
        "rmse_m": rmse,
        "grouped_response_energy_m2": grouped_energy,
    }


def load_and_decompose(row: dict) -> dict:
    scene_id = row["scene_id"]
    metric = row["C5_metrics"]
    match = SCENE_RE.fullmatch(scene_id)
    if match is None:
        raise ValueError(f"Unexpected DEV scene id: {scene_id}")
    if metric.get("scene_id") != scene_id or metric.get("method") != "C5_M110":
        raise ValueError(f"Parent C5 identity mismatch: {scene_id}")

    raw_path = Path(metric["path"]).resolve()
    if not any(raw_path.is_relative_to(root.resolve()) for root in DATA_ROOTS):
        raise ValueError(f"Raw path is outside both pinned C5 source trees: {scene_id}")
    raw_relative = raw_path.relative_to(ROOT.resolve())
    expected_raw_sha = metric["sha256"]
    actual_raw_sha = sha256(raw_path)
    if actual_raw_sha != expected_raw_sha:
        raise ValueError(f"Raw SHA256 mismatch: {scene_id}")

    with h5py.File(raw_path, "r") as source:
        log = source["log"]

        def get(name: str) -> np.ndarray:
            return read_matlab_array(log, name)

        state = get("state")
        reference_position = get("reference/position")
        reference_velocity = get("reference/velocity")
        reference_acceleration = get("reference/acceleration")
        a_req = get("stage1_position_pcf_a_req_mps2")
        r_f = get("stage1_position_pcf_r_f_mps2")
        u_logged = get("position_compensation_applied_acceleration_mps2")

        if state.shape != (STATE_N, 12):
            raise ValueError(f"{scene_id}: state shape {state.shape}")
        for name, value in (
            ("reference_position", reference_position),
            ("reference_velocity", reference_velocity),
            ("reference_acceleration", reference_acceleration),
        ):
            if value.shape != (STATE_N, 3):
                raise ValueError(f"{scene_id}: {name} shape {value.shape}")
        for name, value in (("a_req", a_req), ("r_f", r_f), ("u_logged", u_logged)):
            if value.shape != (N, 3):
                raise ValueError(f"{scene_id}: {name} shape {value.shape}")
        for name, value in (
            ("state", state),
            ("reference_position", reference_position),
            ("reference_velocity", reference_velocity),
            ("reference_acceleration", reference_acceleration),
            ("a_req", a_req),
            ("r_f", r_f),
            ("u_logged", u_logged),
        ):
            if not np.isfinite(value).all():
                raise ValueError(f"{scene_id}: nonfinite {name}")

        position = state[:, :3]
        velocity = state[:, 3:6]
        e = reference_position - position
        sigma = reference_velocity + e - velocity  # T0 = 1
        d0 = np.diff(velocity, axis=0) / DT - a_req
        rho_p = (
            np.diff(reference_position, axis=0)
            - DT * reference_velocity[:-1]
            - (np.diff(position, axis=0) - DT * velocity[:-1])
        )
        rho_s = np.diff(reference_velocity, axis=0) - DT * reference_acceleration[:-1] + rho_p

        # These are transition identities already checked by the pinned parent
        # bridge audit. Recheck them here as reconstruction gates, not as a new
        # plant or controller result.
        e_residual = e[1:] - (A11 * e[:-1] + A12 * sigma[:-1] + rho_p)
        sigma_residual = sigma[1:] - (
            A21 * e[:-1] + A22 * sigma[:-1] + DT * (u_logged - d0) + rho_s
        )
        if max_abs(e_residual) >= 5e-12 or max_abs(sigma_residual) >= 5e-12:
            raise ValueError(f"{scene_id}: actual e/sigma recursion residual exceeds 5e-12")

        event_valid_raw = get("stage1_position_event_inference_valid").reshape(-1)
        if not np.isfinite(event_valid_raw).all():
            raise ValueError(f"{scene_id}: nonfinite event-valid field")
        event_valid = event_valid_raw.astype(bool)
        event_ids = np.flatnonzero(event_valid)
        expected_ids = np.arange(320, 19_991, 10, dtype=np.int64)
        if not np.array_equal(event_ids, expected_ids):
            raise ValueError(f"{scene_id}: unexpected event ids")
        phi = get("stage1_position_event_phi_33")[event_ids]
        weight_before = np.asarray(log["stage1_position_event_weight_before_33x3"]).transpose(0, 2, 1)
        if phi.shape != (event_ids.size, 33) or weight_before.shape != (event_ids.size, 33, 3):
            raise ValueError(f"{scene_id}: event feature/weight shape mismatch")
        z = np.einsum("nfi,nf->ni", weight_before, phi)
        beta_all = get("stage1_position_event_beta").reshape(-1)
        beta = beta_all[event_ids]
        y_all = get("stage1_position_delayed_prediction_target_mps2")
        y = y_all[event_ids][1:]
        if y.shape != (event_ids.size - 1, 3):
            raise ValueError(f"{scene_id}: delayed-target shape {y.shape}")
        for name, value in (("phi", phi), ("weight_before", weight_before), ("z", z), ("beta", beta), ("y", y)):
            if not np.isfinite(value).all():
                raise ValueError(f"{scene_id}: nonfinite {name}")

    interval_count = (event_ids.size - 1) * 10
    if interval_count != 19_670:
        raise ValueError(f"{scene_id}: unexpected held interval length {interval_count}")
    z_interval = np.repeat(z[:-1], 10, axis=0)
    y_interval = np.repeat(y, 10, axis=0)
    beta_interval = np.repeat(beta[:-1], 10)[:, None]
    mask = np.array([1.0, 1.0, 0.0])
    r_f_mid = r_f[320:19_990]
    d_m = d0[320:19_990] + mask * r_f_mid
    terms = (
        beta_interval * (z_interval - y_interval),
        beta_interval * y_interval - d_m,
        beta_interval * (np.clip(z_interval, -3.0, 3.0) - z_interval),
        mask * r_f_mid,
    )
    beta_clip = beta_interval * np.clip(z_interval, -3.0, 3.0)
    u_mid = u_logged[320:19_990]
    forcing_mid = u_mid - d0[320:19_990]
    forcing_term_sum = np.sum(np.stack(terms, axis=0), axis=0)
    if max_abs(u_mid - beta_clip) >= 5e-12:
        raise ValueError(f"{scene_id}: logged compensation differs from beta*clip(z) by at least 5e-12")
    if max_abs(forcing_term_sum - forcing_mid) >= 5e-12:
        raise ValueError(f"{scene_id}: F-term closure residual exceeds 5e-12")

    # Nine-channel forcing decomposition; all values are in acceleration
    # units before multiplying by DT for the sigma-state transition.
    forcing = np.zeros((N, len(CHANNELS), 2, 3), dtype=np.float64)
    forcing[:, 1, 0, :] = rho_p
    forcing[:, 2, 1, :] = rho_s
    forcing[:320, 3, 1, :] = DT * (u_logged - d0)[:320]
    forcing[19_990:, 4, 1, :] = DT * (u_logged - d0)[19_990:]
    for term_index, term in enumerate(terms):
        forcing[320:19_990, 5 + term_index, 1, :] = DT * term

    response = np.zeros((STATE_N, len(CHANNELS), 2, 3), dtype=np.float64)
    response[0, 0, 0, :] = e[0]
    response[0, 0, 1, :] = sigma[0]
    for index in range(N):
        response[index + 1, :, 0, :] = (
            A11 * response[index, :, 0, :]
            + A12 * response[index, :, 1, :]
            + forcing[index, :, 0, :]
        )
        response[index + 1, :, 1, :] = (
            A21 * response[index, :, 0, :]
            + A22 * response[index, :, 1, :]
            + forcing[index, :, 1, :]
        )

    e_rebuilt = response[:, :, 0, :].sum(axis=1)
    sigma_rebuilt = response[:, :, 1, :].sum(axis=1)
    if not np.isfinite(response).all():
        raise ValueError(f"{scene_id}: nonfinite component response")
    if max_abs(e_rebuilt - e) >= 5e-12 or max_abs(sigma_rebuilt - sigma) >= 5e-12:
        raise ValueError(f"{scene_id}: component response does not reconstruct e/sigma")

    phase_results = {}
    for phase_name, start, end in PHASES:
        phase_results[phase_name] = phase_summary(response[:N, :, 0, :], start, end)

    q_parent = float(metric["Q_0_20_m"])
    q_rebuilt = phase_results["0_20s"]["rmse_m"]["xyz"]
    if abs(q_rebuilt - q_parent) >= 1e-10:
        raise ValueError(f"{scene_id}: reconstructed Q differs from parent C5 metrics")
    phase_parent_checks = {}
    for phase_name, parent_key in (("0_5s", "Q_0_5_m"), ("5_20s", "Q_5_20_m")):
        parent_q = float(metric[parent_key])
        actual_q = phase_results[phase_name]["rmse_m"]["xyz"]
        if abs(actual_q - parent_q) >= 1e-10:
            raise ValueError(f"{scene_id}: {phase_name} Q differs from parent C5 metrics")
        phase_parent_checks[phase_name] = {
            "parent_Q_m": parent_q,
            "reconstructed_Q_m": actual_q,
            "absolute_difference_m": abs(actual_q - parent_q),
        }

    task_index, wind_index = int(match.group(1)), int(match.group(2))
    groups = ["ALL72", f"T{task_index}"]
    if 9 <= wind_index <= 14:
        groups.append("HF_W09_W14")
    if wind_index == 15:
        groups.append("W15")

    return {
        "scene_id": scene_id,
        "raw_relative_path": raw_relative.as_posix(),
        "raw_sha256": actual_raw_sha,
        "groups": groups,
        "parent_Q_0_20_m": q_parent,
        "reconstructed_Q_0_20_m": q_rebuilt,
        "parent_phase_Q_checks": phase_parent_checks,
        "position_reconstruction_max_m": max_abs(e_rebuilt - e),
        "surface_reconstruction_max_m": max_abs(sigma_rebuilt - sigma),
        "actual_e_transition_residual_max_m": max_abs(e_residual),
        "actual_sigma_transition_residual_max_m": max_abs(sigma_residual),
        "u_logged_minus_beta_clip_z_max_mps2": max_abs(u_mid - beta_clip),
        "F_terms_sum_minus_actual_u_minus_d0_max_mps2": max_abs(forcing_term_sum - forcing_mid),
        "by_phase": phase_results,
    }


def group_summary(name: str, scenes: list[dict]) -> dict:
    if not scenes:
        raise ValueError(f"Empty required group: {name}")
    by_phase = {}
    for phase_name, _, _ in PHASES:
        phase_data = [scene["by_phase"][phase_name] for scene in scenes]
        grams = {
            axis: np.mean(
                [np.asarray(item["gram_m2"][axis], dtype=np.float64) for item in phase_data],
                axis=0,
            )
            for axis in (*AXIS_NAMES, "xyz")
        }
        rmse = {
            axis: float(np.sqrt(max(float(matrix.sum()), 0.0)))
            for axis, matrix in grams.items()
        }

        epsilon_indices = (5, 6, 7)
        masked_indices = (8,)
        active_indices = epsilon_indices + masked_indices
        grouped_energy = {}
        for axis, matrix in grams.items():
            epsilon_m2 = float(matrix[np.ix_(epsilon_indices, epsilon_indices)].sum())
            masked_m2 = float(matrix[np.ix_(masked_indices, masked_indices)].sum())
            active_m2 = float(matrix[np.ix_(active_indices, active_indices)].sum())
            cross_m2 = float(2.0 * matrix[np.ix_(epsilon_indices, masked_indices)].sum())
            grouped_energy[axis] = {
                "epsilonM_m2": epsilon_m2,
                "masked_pcf_m2": masked_m2,
                "physical_active_epsilonM_plus_masked_pcf_m2": active_m2,
                "cross_epsilonM_masked_pcf_m2": cross_m2,
            }

        q_values = [item["rmse_m"]["xyz"] for item in phase_data]
        scene_equal_axis_rmse = {
            axis: float(np.mean([item["rmse_m"][axis] for item in phase_data]))
            for axis in (*AXIS_NAMES, "xyz")
        }
        by_phase[phase_name] = {
            "sample_count_per_scene": phase_data[0]["sample_count"],
            "gram_m2": {axis: matrix.tolist() for axis, matrix in grams.items()},
            "pooled_rmse_m": rmse,
            "scene_equal_mean_rmse_m": scene_equal_axis_rmse,
            "scene_equal_mean_Q_m": float(np.mean(q_values)),
            "scene_equal_rms_Q_m": float(np.sqrt(np.mean(np.square(q_values)))),
            "grouped_response_energy_m2": grouped_energy,
        }

    return {
        "group": name,
        "scene_count": len(scenes),
        "scene_ids": [scene["scene_id"] for scene in scenes],
        "aggregation": "Equal scene weight; all scenes have the same sample count in each phase.",
        "by_phase": by_phase,
    }


def main() -> None:
    if sha256(PARENT) != PARENT_SHA256:
        raise ValueError("Pinned parent review SHA256 mismatch")
    if OUTPUT.exists():
        raise FileExistsError(f"Refusing to overwrite {OUTPUT}")

    parent = json.loads(PARENT.read_text(encoding="utf-8-sig"))
    rows = parent.get("rows")
    if not isinstance(rows, list) or len(rows) != 72:
        raise ValueError("Pinned parent review must contain exactly 72 rows")

    scene_ids = [row.get("scene_id") for row in rows]
    if len(set(scene_ids)) != 72:
        raise ValueError("Duplicate or missing scene_id in parent rows")

    scene_results = [load_and_decompose(row) for row in rows]
    expected_tasks = {f"T{task}" for task in (1, 2, 3)}
    if {group for scene in scene_results for group in scene["groups"] if group.startswith("T")} != expected_tasks:
        raise ValueError("DEV task group coverage is incomplete")

    group_names = ("ALL72", "HF_W09_W14", "W15", "T1", "T2", "T3")
    groups = {
        name: group_summary(name, [scene for scene in scene_results if name in scene["groups"]])
        for name in group_names
    }
    result = {
        "status": "PASS_DEV72_FIXED_PATH_RESPONSE_GRAM",
        "scope": (
            "Descriptive decomposition of 72 existing C5_M110 development paths (original DEV24+VAL48). "
            "No TEST data, Plant calls, training, counterfactual, or candidate selection."
        ),
        "parent_review_path": PARENT.relative_to(ROOT).as_posix(),
        "parent_review_sha256": PARENT_SHA256,
        "source_sha256": sha256(Path(__file__)),
        "scene_count": len(scene_results),
        "transition_count": N,
        "state_count": STATE_N,
        "scored_state_indices_zero_based": [0, N - 1],
        "terminal_state_index_zero_based_recursion_only": N,
        "dt_s": DT,
        "physical_recursion_A": [[A11, A12], [A21, A22]],
        "error_state_definition": {
            "e": "reference_position - state_position",
            "sigma": "reference_velocity + e - state_velocity; T0=1",
        },
        "channels": CHANNELS,
        "channel_units": {
            "initial": "initial e/sigma normalized state in m; T0=1 s",
            "sampling_position": "rho_p position transition forcing in m",
            "sampling_surface": "T0*rho_s normalized surface transition forcing in m; T0=1 s",
            "pre_ready": "actual DT*(u-d0) in sigma transition forcing, samples 0..319",
            "tail": "actual DT*(u-d0) in sigma transition forcing, samples 19990..19999",
            "prediction": "DT*beta*(z-y), sigma transition forcing",
            "ramp_and_interval": "DT*(beta*y-dM), sigma transition forcing",
            "head_clip": "DT*beta*(clip(z)-z), sigma transition forcing",
            "masked_pcf": "DT*M*r_f, sigma transition forcing",
        },
        "grouped_channel_definitions": {
            "epsilonM": ["prediction", "ramp_and_interval", "head_clip"],
            "masked_pcf": ["masked_pcf"],
            "physical_active": ["prediction", "ramp_and_interval", "head_clip", "masked_pcf"],
            "warning": (
                "The delayed target y cancels algebraically between prediction and ramp_and_interval; "
                "individual F1/F2 energies depend on that decomposition. Interpret their grouped "
                "response and cross-terms, not either channel alone."
            ),
        },
        "phase_definitions": {
            "0_20s": "state samples 0..19999 (20000 samples)",
            "0_5s": "state samples 0..4999 (5000 samples)",
            "5_20s": "state samples 5000..19999 (15000 samples)",
            "state_sample_20000": "used only for final recursion/reconstruction check, excluded from Q/Gram",
        },
        "gram_definition": "G[i,j] = mean_time(response_i * response_j), units m^2; all symmetric cross terms retained.",
        "group_aggregation": "Equal weight per scene; pooled Gram is also reported, separately from scene-equal mean Q.",
        "input_raw_sha256_by_scene": {scene["scene_id"]: scene["raw_sha256"] for scene in scene_results},
        "diagnostic_maxima": {
            "position_reconstruction_max_m": max(scene["position_reconstruction_max_m"] for scene in scene_results),
            "surface_reconstruction_max_m": max(scene["surface_reconstruction_max_m"] for scene in scene_results),
            "actual_e_transition_residual_max_m": max(scene["actual_e_transition_residual_max_m"] for scene in scene_results),
            "actual_sigma_transition_residual_max_m": max(scene["actual_sigma_transition_residual_max_m"] for scene in scene_results),
            "u_logged_minus_beta_clip_z_max_mps2": max(scene["u_logged_minus_beta_clip_z_max_mps2"] for scene in scene_results),
            "F_terms_sum_minus_actual_u_minus_d0_max_mps2": max(scene["F_terms_sum_minus_actual_u_minus_d0_max_mps2"] for scene in scene_results),
        },
        "groups": groups,
        "scenes": scene_results,
        "interpretation_limit": (
            "Fixed-path linear response identity only. It does not predict retraining, a changed target, "
            "a counterfactual closed-loop trajectory, causal component benefit, or novelty."
        ),
    }

    with OUTPUT.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({
        "status": result["status"],
        "scene_count": result["scene_count"],
        "output": OUTPUT.name,
        "source_sha256": result["source_sha256"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
