"""Independent read-only scoring of explicit new DEV3 raw files.

Usage: python score_new_dev3_raw.py <new run_raw.mat> [...]
Only raw paths inside the sibling dev3_v1 tree are accepted. No model, old
experiment, or TEST file is opened. Results go to stdout, with raw SHA256.
"""
from hashlib import sha256
from pathlib import Path
import json
import sys

import h5py
import numpy as np
from scipy.spatial.transform import Rotation


ALLOWED = (Path(__file__).resolve().parent.parent / "dev3_v1").resolve()


def digest(path):
    h = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def metrics(state, reference_position, filtered_euler):
    assert state.shape == (20001, 12)
    assert reference_position.shape == (20001, 3)
    assert filtered_euler.shape == (20000, 3)
    assert all(np.isfinite(a).all() for a in (state, reference_position, filtered_euler))
    error = state[:, :3] - reference_position
    q = np.linalg.norm(error, axis=1)
    # SciPy's extrinsic xyz convention gives Rz(yaw) Ry(pitch) Rx(roll).
    actual = Rotation.from_euler("xyz", state[:-1, 6:9])
    desired = Rotation.from_euler("xyz", filtered_euler)
    trace = np.einsum("nij,nij->n", desired.as_matrix(), actual.as_matrix())
    angle = np.arccos(np.clip((trace - 1) / 2, -1, 1))
    stable_angle = (desired.inv() * actual).magnitude()
    return {
        "Q_rmse_m": float(np.sqrt(np.mean(q * q))),
        "axis_rmse_m": np.sqrt(np.mean(error * error, axis=0)).tolist(),
        "Q_peak_m": float(q.max()),
        "SO3_rmse_rad": float(np.sqrt(np.mean(angle * angle))),
        "SO3_peak_rad": float(angle.max()),
        "SO3_stable_formula_rmse_rad": float(np.sqrt(np.mean(stable_angle ** 2))),
        "SO3_formula_max_difference_rad": float(np.max(np.abs(angle - stable_angle))),
        "Q_state_samples": 20001,
        "SO3_transition_samples": 20000,
    }


def score(path):
    path = path.resolve(strict=True)
    assert path.is_relative_to(ALLOWED), f"Outside new DEV3 scope: {path}"
    assert path.name == "run_raw.mat", f"Unexpected raw name: {path.name}"
    with h5py.File(path, "r") as source:
        log = source["log"]

        def read(key):
            return np.asarray(log[key]).T

        time = read("time").ravel()
        transition_time = read("transition_time").ravel()
        assert time.shape == (20001,) and transition_time.shape == (20000,)
        assert np.allclose(time, np.arange(20001) * .001, atol=1e-12, rtol=0)
        assert np.array_equal(transition_time, time[:-1])
        state, position, euler = read("state"), read("reference/position"), read("filtered_attitude_reference")
        result = metrics(state, position, euler)
        for key, columns in (("requested_generalized", 4), ("controller_clipped_generalized", 4),
                             ("motor_command", 4)):
            values = read(key)
            assert values.shape == (20000, columns) and np.isfinite(values).all(), key
        for key in ("motor_saturated", "generalized_clipped"):
            values = read(key)
            assert values.shape == (20000, 4) and np.isin(values, [0, 1]).all(), key
            result[key + "_transition_count"] = int(np.any(values.astype(bool), axis=1).sum())
        tilt = read("tilt_limited").ravel()
        assert tilt.shape == (20000,) and np.isin(tilt, [0, 1]).all()
        result["tilt_limited_transition_count"] = int(tilt.sum())
        result["last_transition"] = int(read("last_transition").item())
        result["status"] = "".join(chr(int(x)) for x in read("status").ravel())
        assert result["last_transition"] == 20000 and result["status"] == "STABLE"
        result["controller_call_time_s_mean_partial_scope"] = float(read("controller_call_time_s").mean())
    result.update(raw_path=str(path), raw_sha256=digest(path),
                  scoring="Q:0..20 inclusive; SO3:transition_time [0,20); independent SciPy rotations")
    return result


if __name__ == "__main__":
    assert 1 <= len(sys.argv[1:]) <= 6, "Pass one to six explicit new DEV3 raw paths."
    print(json.dumps([score(Path(p)) for p in sys.argv[1:]], indent=2, ensure_ascii=False, allow_nan=False))
