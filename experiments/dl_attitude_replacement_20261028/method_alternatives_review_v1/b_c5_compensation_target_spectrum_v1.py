"""Read-only replay of the locked HF6 B/C5 position-compensation target spectrum."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import h5py
import numpy as np


ROOT = Path(__file__).resolve().parents[3]
SCORE = ROOT / "experiments/dl_attitude_replacement_20261028/gru_prediction_tau01_v1/audits/GRU_PREDICTION_TAU01_SCORE_final12.json"
SCORE_SHA256 = "132ac1ccf86f3c2b51a4c89eaebdb23170f62598205e7ce7072a6a7e47759fcb"
LOCKED_FILES = {
    "experiments/b_traceable_c3core_dev72_20261023/B_TRACEABLE_DEV72_INPUT_LOCK_v3.json": "8d738e5c70ba2fc8697550549d1a0537f08eadb49b99bc5684e5c26f6222f452",
    "experiments/position_axis_coordinate_c5_dev72_20261023/C5_DEV72_INPUT_LOCK_v3.json": "82024c01276cc4bfbd9b7772cf5332dee3fdfcbed422969589b68f1c90ed2d75",
    "experiments/position_delayed_prediction_c3_dev72_20261023/run_dl1018_closed_loop.m": "e5f1e30c433ee3f8206b36446cde71776589c161fe2a3ec60fbaf070585eb07f",
    "experiments/position_axis_coordinate_c5_dev72_20261023/run_dl1018_closed_loop.m": "48350037b66efe00301b138068f187c62cf92583f0f9ba2fabc9b24f248a963c",
    "matlab/core/position_bs_step.m": "ea533c3ae97cbc552208287e7f8d9b0a0f5a018f36fb5c8bd45520e19e73c681",
    "matlab/core/baseline_force_to_attitude.m": "ef42d1d08af24ed82da307a4d886b0c205e28e754177765a2584e3e9bb0cd039",
    "matlab/core/command_filter_step.m": "15c7eb27162e1971a1164304830f4afd3af35eb9bd709291e969dbfefd0d262b",
    "matlab/core/command_filter_init.m": "64fbd68ef652f419066e0546569ba4029bdc00da3eabb0f8019bdc12f66d14a5",
    "matlab/core/default_config.m": "685abb7b72a335fdc826673e6431098fe79af88409f17b1b70ce08edb214dc51",
}
MASS_KG, GRAVITY, DT, MAX_TILT = 0.695, 9.8, 0.001, np.pi / 6
SCENES = (
    "DL1018_DEV_T1_C10_W09",
    "DL1018_DEV_T2_C09_W10",
    "DL1018_DEV_T3_C09_W09",
    "DL1018_VAL_T1_C07_W14",
    "DL1018_VAL_T2_C04_W14",
    "DL1018_VAL_T3_C01_W14",
)
METHODS = ("B", "C5", "Parent_Cosine_GRU")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read3(log: h5py.Group, name: str, n: int) -> np.ndarray:
    x = np.asarray(log[name], dtype=float)
    if x.shape == (3, n):
        x = x.T
    assert x.shape == (n, 3), (name, x.shape)
    return x


def force_to_rp(acceleration: np.ndarray, yaw: np.ndarray) -> np.ndarray:
    specific = acceleration.copy()
    specific[:, 2] += GRAVITY
    a = np.cos(yaw) * specific[:, 0] + np.sin(yaw) * specific[:, 1]
    b = np.sin(yaw) * specific[:, 0] - np.cos(yaw) * specific[:, 1]
    roll = np.arctan2(b, np.hypot(specific[:, 2], a))
    pitch = np.arctan2(a, specific[:, 2])
    tilt = np.hypot(roll, pitch)
    scale = np.minimum(1.0, MAX_TILT / np.maximum(tilt, 1e-30))
    return np.column_stack((roll * scale, pitch * scale))


def band_rms(x: np.ndarray, low_hz: float = 2.0, high_hz: float = 5.0) -> float:
    n = len(x)
    spectrum = np.fft.rfft(x, axis=0)
    frequency = np.fft.rfftfreq(n, DT)
    one_sided_weight = np.ones(len(frequency))
    one_sided_weight[1:-1] = 2.0
    band = (frequency >= low_hz) & (frequency < high_hz)
    power = np.sum(np.abs(spectrum[band]) ** 2 * one_sided_weight[band, None]) / n**2
    return float(np.sqrt(power))


def main() -> None:
    assert sha256(SCORE) == SCORE_SHA256, "paired score manifest changed"
    for relpath, expected in LOCKED_FILES.items():
        assert sha256(ROOT / relpath) == expected, (relpath, "locked source SHA mismatch")
    score = json.loads(SCORE.read_text(encoding="utf-8"))
    scene_rows = {row["scene_id"]: row for row in score["scene_results"]}
    output = []

    for scene_id in SCENES:
        scene = scene_rows[scene_id]
        for method in METHODS:
            entry = scene["methods"][method]
            raw = Path(entry["raw_path"])
            raw_hash = sha256(raw)
            assert raw_hash == entry["raw_sha256"], (scene_id, method, "raw SHA mismatch")
            with h5py.File(raw, "r") as mat:
                log = mat["log"]
                n = int(np.asarray(log["transition_time"]).size)
                assert n == 20_000, (scene_id, method, n)
                nominal = read3(log, "position_nominal_acceleration_mps2", n)
                applied = read3(log, "position_compensation_applied_acceleration_mps2", n)
                commanded = read3(log, "position_commanded_force_N", n) / MASS_KG
                state = np.asarray(log["state"], dtype=float).T[:n]
                target = read3(log, "command_filter_target_euler", n)[:, :2]
                assert state.shape == (n, 12)
                assert np.max(np.abs(nominal - applied - commanded)) < 2e-10

                replay_target = force_to_rp(commanded, state[:, 8])
                replay_error = float(np.max(np.abs(replay_target - target)))
                assert replay_error < 1e-8, (scene_id, method, "target replay", replay_error)
                no_comp_target = force_to_rp(nominal, state[:, 8])
                compensation_target_delta = target - no_comp_target

                if method == "B":
                    source_comp = read3(log, "position_rbf_compensation_force_N", n) / MASS_KG
                    expected_flags = (0, 0, 0)
                else:
                    source_comp = read3(log, "stage1_position_held_applied_acceleration_mps2", n)
                    expected_flags = (1, 1, 1)
                source_error = float(np.max(np.abs(applied - source_comp)))
                assert source_error < 1e-12, (scene_id, method, "compensation source", source_error)
                flags = tuple(
                    int(np.asarray(log[name]).squeeze())
                    for name in (
                        "stage1_position_replacement_enabled",
                        "stage1_position_delayed_prediction_enabled",
                        "stage1_position_pcf_coordination_enabled",
                    )
                )
                assert flags == expected_flags, (scene_id, method, flags)

                output.append(
                    {
                        "scene": scene_id,
                        "method": method,
                        "raw_sha256": raw_hash,
                        "rebuild_max_abs_rad": replay_error,
                        "compensation_source_max_abs_mps2": source_error,
                        "compensation_rms_mps2": float(np.sqrt(np.mean(np.sum(applied**2, axis=1)))),
                        "target_2_5hz_rms_mrad": 1000 * band_rms(target),
                        "no_comp_target_2_5hz_rms_mrad": 1000 * band_rms(no_comp_target),
                        "comp_delta_target_2_5hz_rms_mrad": 1000 * band_rms(compensation_target_delta),
                        "stage1_flags": flags,
                    }
                )

    print("scene\tmethod\traw_sha256\tcomp_rms_mps2\ttarget_2_5hz_mrad\tno_comp_2_5hz_mrad\tdelta_2_5hz_mrad\trebuild_max_rad")
    for row in output:
        print(
            f"{row['scene']}\t{row['method']}\t{row['raw_sha256']}\t"
            f"{row['compensation_rms_mps2']:.8f}\t{row['target_2_5hz_rms_mrad']:.6f}\t"
            f"{row['no_comp_target_2_5hz_rms_mrad']:.6f}\t"
            f"{row['comp_delta_target_2_5hz_rms_mrad']:.6f}\t{row['rebuild_max_abs_rad']:.3e}"
        )
    print("method\tcomp_rms_mps2\ttarget_2_5hz_mrad\tno_comp_2_5hz_mrad\tdelta_2_5hz_mrad")
    for method in METHODS:
        rows = [row for row in output if row["method"] == method]
        values = [
            np.mean([row[key] for row in rows])
            for key in (
                "compensation_rms_mps2",
                "target_2_5hz_rms_mrad",
                "no_comp_target_2_5hz_rms_mrad",
                "comp_delta_target_2_5hz_rms_mrad",
            )
        ]
        print(method + "\t" + "\t".join(f"{value:.6f}" for value in values))


if __name__ == "__main__":
    main()
