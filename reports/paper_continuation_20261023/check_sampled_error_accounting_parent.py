"""Exact sampled position-error accounting on frozen C3 trajectories only."""
import csv
import hashlib
import itertools
import json
from pathlib import Path

import h5py
import numpy as np
import scipy.io
from scipy.linalg import solve_discrete_lyapunov
from scipy.signal import lfilter


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / "sampled_error_accounting"


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1048576), b""):
            h.update(chunk)
    return h.hexdigest()


def groups(sid):
    wind = int(sid[-2:])
    result = ["ALL72"]
    if 9 <= wind <= 14:
        result.append("HF28")
        if "_T2_" in sid:
            result.append("T2-HF9")
    if wind == 15:
        result.append("W15")
    return result


def propagate_position(A, forcing, initial):
    # Transfer from b[n] in x[n+1]=A*x[n]+b[n] to e[n].
    trace, det = np.trace(A), np.linalg.det(A)
    denominator = [1.0, -trace, det]
    padded = np.vstack((forcing, [0.0, 0.0]))
    response = (lfilter([0.0, 1.0, -A[1, 1]], denominator, padded[:, 0])
                + lfilter([0.0, 0.0, A[0, 1]], denominator, padded[:, 1]))
    impulse = np.zeros(len(padded))
    impulse[0] = 1.0
    first = float((A @ initial)[0])
    return response + lfilter([initial[0], first - trace * initial[0]], denominator, impulse)


def main():
    assert not OUT.exists(), "Refuse to overwrite prior accounting"
    cfg_path = ROOT / "configs/effective_config.mat"
    assert sha(cfg_path) == "cec90417369c7a44580b0315b2473ae86eb62550012188340b1dd5f3a796522f"
    cfg = scipy.io.loadmat(cfg_path, simplify_cells=True)["cfg"]
    k1 = np.asarray(cfg["control"]["bs"]["position"]["k1"], float)
    k2 = np.asarray(cfg["control"]["bs"]["position"]["k2"], float)
    assert np.array_equal(k1, [1, 1, 1]) and np.array_equal(k2, [4, 4, 4])
    manifest = ROOT / "reports/delayed_prediction_c3_dev72_parent_20261023/PARENT_C3_ALL72_RAW_MANIFEST.json"
    payload = json.loads(manifest.read_text(encoding="utf-8-sig"))
    assert len(payload["rows"]) == 72
    for ref in payload["source_refs"]:
        assert sha(ref["path"]) == ref["sha256"]
    dt = .001
    A = np.array([[1 - dt, dt], [-dt, 1 - 4 * dt]])
    P = solve_discrete_lyapunov(A.T, np.eye(2))
    assert np.linalg.eigvalsh(P).min() > 0
    assert np.max(np.abs(A.T @ P @ A - P + np.eye(2))) < 1e-10
    # A.T P A = P-I gives the exact induced-P contraction factor.
    alpha = float(np.sqrt(1 - 1 / np.linalg.eigvalsh(P).max()))
    assert 0 < alpha < 1
    records, checks = [], []
    names = ["initial", "eta", "residual", "sampling"]
    for row in payload["rows"]:
        assert sha(row["path"]) == row["sha256"]
        with h5py.File(row["path"], "r") as handle:
            log = handle["log"]
            def read(key):
                return np.asarray(log[key], dtype=float).T
            state = read("state")
            rp, rv, ra = [read("reference/" + key) for key in ("position", "velocity", "acceleration")]
            req, af, rf = [read("stage1_position_pcf_" + key + "_mps2") for key in ("a_req", "a_f", "r_f")]
            eta0, eta1 = [read("stage1_position_pcf_eta_" + key + "_mps") for key in ("before", "after")]
            applied = read("stage1_position_held_applied_acceleration_mps2")
        assert state.shape == (20001, 12) and eta0.shape == (20000, 3)
        assert np.array_equal(eta1[:-1], eta0[1:])
        e = rp - state[:, :3]
        s = rv + e * k1 - state[:, 3:6]
        eta = np.vstack((eta0, eta1[-1]))
        sc = s - eta
        nominal = ra[:-1] + k1 * (rv[:-1] - state[:-1, 3:6]) + e[:-1] + k2 * s[:-1]
        command_gap = float(np.max(np.abs(nominal - applied - req)))
        assert command_gap < 2e-12
        assert np.max(np.abs(req - af - rf)) < 2e-12
        rho_p = np.diff(rp, axis=0) - dt * rv[:-1] - (np.diff(state[:, :3], axis=0) - dt * state[:-1, 3:6])
        rho_s = np.diff(rv, axis=0) - dt * ra[:-1] + k1 * rho_p
        d_c = np.diff(state[:, 3:6], axis=0) / dt - req + rf
        rho_eta = eta1 - eta0 - dt * (-k2 * eta0 + rf)
        max_identity, max_response, max_mse = 0.0, 0.0, 0.0
        for axis, label in enumerate("XYZ"):
            actual = np.column_stack((e[:, axis], sc[:, axis]))
            zero = np.zeros(20000)
            forcing = {"eta": np.column_stack((dt * eta0[:, axis], zero)),
                       "residual": np.column_stack((zero, dt * (applied[:, axis] - d_c[:, axis]))),
                       "sampling": np.column_stack((rho_p[:, axis], rho_s[:, axis] - rho_eta[:, axis]))}
            residual = actual[1:] - actual[:-1] @ A.T - sum(forcing.values())
            max_identity = max(max_identity, float(np.max(np.abs(residual))))
            assert max_identity < 2e-12
            responses = {key: propagate_position(A, value, np.zeros(2)) for key, value in forcing.items()}
            responses["initial"] = propagate_position(A, np.zeros((20000, 2)), actual[0])
            reconstructed = sum(responses.values())
            max_response = max(max_response, float(np.max(np.abs(reconstructed - e[:, axis]))))
            assert max_response < 2e-10
            result = {"scene_id": row["scene_id"], "groups": ";".join(groups(row["scene_id"])), "axis": label,
                      "actual_position_RMSE_m": float(np.sqrt(np.mean(e[:-1, axis] ** 2)))}
            mse_sum = 0.0
            for name in names:
                value = float(np.mean(responses[name][:-1] ** 2))
                result[name + "_response_RMS_m"] = float(np.sqrt(value))
                result[name + "_response_MSE_m2"] = value
                mse_sum += value
            for left, right in itertools.combinations(names, 2):
                value = float(2 * np.mean(responses[left][:-1] * responses[right][:-1]))
                result[left + "_cross_" + right + "_m2"] = value
                mse_sum += value
            gap = abs(mse_sum - result["actual_position_RMSE_m"] ** 2)
            max_mse = max(max_mse, gap)
            assert gap < 2e-13
            records.append(result)
        checks.append({"scene_id": row["scene_id"], "raw_sha256": row["sha256"], "command_identity_max_mps2": command_gap,
                       "recurrence_identity_max_absolute": max_identity, "response_sum_max_m": max_response,
                       "MSE_accounting_max_m2": max_mse})
    group_rows = []
    for group, size in (("ALL72", 72), ("HF28", 28), ("W15", 6), ("T2-HF9", 9)):
        for axis in "XYZ":
            cells = [r for r in records if group in r["groups"].split(";") and r["axis"] == axis]
            assert len(cells) == size
            group_rows.append({"group": group, "axis": axis, "n_scenes": size,
                               **{k: float(np.mean([r[k] for r in cells])) for k in cells[0] if k not in ("scene_id", "groups", "axis")}})
    OUT.mkdir()
    for name, data in (("PER_SCENE.csv", records), ("GROUPS.csv", group_rows)):
        with (OUT / name).open("x", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(data[0]))
            writer.writeheader()
            writer.writerows(data)
    result = {"status": "PASS", "new_Plant": 0, "TEST_accessed": False, "scene_count": 72,
              "interpretation": "Exact frozen-trajectory forcing accounting; no claim that removing a term preserves other forcing or improves an actual counterfactual rollout",
              "A": A.tolist(), "P": P.tolist(), "P_norm_contraction_alpha": alpha,
              "spectral_radius_A": float(max(abs(np.linalg.eigvals(A)))), "checks": checks,
              "source_refs": [{"path": str(p), "sha256": sha(p)} for p in [manifest, cfg_path, HERE / "EXACT_SAMPLED_ERROR_ACCOUNTING_TASKBOOK_ZH.md", Path(__file__)]]}
    (OUT / "REVIEW.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": result["status"], "scenes": 72, "max_response_error_m": max(r["response_sum_max_m"] for r in checks),
                      "T2_HF_Z": next(r for r in group_rows if r["group"] == "T2-HF9" and r["axis"] == "Z")}))


if __name__ == "__main__":
    main()
