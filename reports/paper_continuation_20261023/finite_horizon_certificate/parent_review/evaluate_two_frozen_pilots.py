"""Evaluate the frozen path certificate on exactly the already audited C3/C4 pilot."""
import hashlib
import json
from pathlib import Path

import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
N = 20000
DT = .001


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def energy(a):
    return float(np.sum(np.asarray(a) ** 2))


def norm(a):
    return float(np.sqrt(energy(a)))


def evaluate(item):
    path = Path(item["raw_path"])
    assert sha(path) == item["raw_sha256"]
    mask = np.asarray(item["mask"], dtype=float)
    with h5py.File(path, "r") as file:
        g = file["log"]

        def read(key):
            a = np.asarray(g[key])
            return a.T if a.ndim == 2 else a

        state = read("state")
        position = read("reference/position")
        velocity = read("reference/velocity")
        acceleration = read("reference/acceleration")
        assert state.shape == (20001, 12) and position.shape == velocity.shape == acceleration.shape == (20001, 3)
        error = position - state[:, :3]
        eta = read("stage1_position_pcf_eta_before_mps")
        eta_after = read("stage1_position_pcf_eta_after_mps")
        req, rf = read("stage1_position_pcf_a_req_mps2"), read("stage1_position_pcf_r_f_mps2")
        applied = read("position_compensation_applied_acceleration_mps2")
        d = np.diff(state[:, 3:6], axis=0) / DT - req + mask * rf
        epsilon = applied - d
        rp = np.diff(position, axis=0) - DT * velocity[:-1] - np.diff(state[:, :3], axis=0) + DT * state[:-1, 3:6]
        rs = np.diff(velocity, axis=0) - DT * acceleration[:-1] + rp
        reta = eta_after - eta - DT * (-4 * eta + rf)
        eta_full = np.vstack((eta, eta_after[-1]))
        z = velocity - state[:, 3:6] + error - eta_full * mask
        f1, f2 = DT * mask * eta + rp, DT * epsilon + rs - mask * reta
        recurrence_error = max(np.max(np.abs(error[1:] - (.999 * error[:-1] + .001 * z[:-1] + f1))),
                               np.max(np.abs(z[1:] - (-.001 * error[:-1] + .996 * z[:-1] + f2))))
        assert recurrence_error < 1e-12
        ids = np.flatnonzero(read("stage1_position_event_inference_valid").ravel())
        assert np.array_equal(ids, np.arange(320, 19991, 10))
        phi = read("stage1_position_event_phi_33")[ids]
        before = np.asarray(g["stage1_position_event_weight_before_33x3"]).transpose(0, 2, 1)
        after = np.asarray(g["stage1_position_event_weight_after_33x3"]).transpose(0, 2, 1)
        assert np.array_equal(before[1:], after[:-1])
        initial = read("stage1_position_weight_initial")
        assert np.array_equal(before[0], initial)
        target = read("stage1_position_delayed_prediction_target_mps2")[ids[1:]]
        assert np.isfinite(target).all()
        evaluated_error = np.einsum("nfi,nf->ni", before[1:], phi[:-1]) - target
        comparator_error = phi[:-1] @ initial - target
        loss = .5 * energy(evaluated_error)
        comparator_loss = .5 * energy(comparator_error)
        beta = read("stage1_position_event_beta").ravel()[ids]
        seff = read("stage1_position_pcf_event_s_coord_eff_mps")[ids]
        H = .12 * beta[:, None, None] * phi[:, :, None] * seff[:, None, :] + .00002 * before
        R = float(np.max(np.linalg.norm(before[1:] - initial, axis=(1, 2))))
        D1 = energy(before[1] - initial)
        rho = .01
        loss_bound = (D1 + 2 * rho * comparator_loss + 2 * R * np.linalg.norm(H[1:], axis=(1, 2)).sum()
                      + (1 + 2 * rho / (1 - rho)) * energy(H[1:])) / (rho * (1 - rho))
        assert loss <= loss_bound + 1e-10
        raw = read("stage1_position_event_raw_acceleration_mps2")[ids[:-1]]
        ramp_energy = energy((beta[:-1, None] - 1) * raw)
        clip_energy = energy(beta[:-1, None] * (np.clip(raw, -3, 3) - raw))
        delta_weight_energy = energy(after[:-1] - before[:-1])
        output_error_energy = energy(applied[ids[:-1]] - target)
        output_bound_loss = 12 * loss + 6 * delta_weight_energy + 3 * ramp_energy + 3 * clip_energy
        output_bound_update = 12 * loss_bound + 6 * delta_weight_energy + 3 * ramp_energy + 3 * clip_energy
        assert output_error_energy <= output_bound_loss + 1e-10
        windows = d[320:19990].reshape(1967, 10, 3)
        mean = windows.mean(axis=1)
        xi, variation = target - mean, mean[:, None, :] - windows
        xi_energy, variation_energy = energy(xi), energy(variation)
        interior_actual = energy(epsilon[320:19990])
        interior_bound = 20 * output_bound_update + 20 * xi_energy + variation_energy
        assert interior_actual <= interior_bound + 1e-10
        boundaries = energy(epsilon[:320]) + energy(epsilon[19990:])
        epsilon_bound = float(np.sqrt(boundaries + interior_bound))
        A = np.array([[.999, .001], [-.001, .996]])
        homogeneous = np.vstack((error[0], z[0]))
        initial_energy = 0.
        for _ in range(N):
            initial_energy += energy(homogeneous[0])
            homogeneous = A @ homogeneous
        initial_norm = float(np.sqrt(initial_energy))
        Q = norm(error[:-1]) / np.sqrt(N)
        exact_forcing_bound = (initial_norm + 800 * norm(f1) + 200 * norm(f2)) / np.sqrt(N)
        loss_bridge_bound = (initial_norm + 800 * (DT * norm(mask * eta) + norm(rp))
                             + 200 * (DT * np.sqrt(boundaries + 20 * output_bound_loss + 20 * xi_energy + variation_energy)
                                      + norm(rs - mask * reta))) / np.sqrt(N)
        update_bridge_bound = (initial_norm + 800 * (DT * norm(mask * eta) + norm(rp))
                               + 200 * (DT * epsilon_bound + norm(rs - mask * reta))) / np.sqrt(N)
        assert Q <= exact_forcing_bound + 1e-12 and Q <= loss_bridge_bound + 1e-12 and Q <= update_bridge_bound + 1e-12
    return dict(method=item["method"], scene_id=item["scene_id"], mask=item["mask"], Q_m=Q,
                recurrence_max_abs_error=float(recurrence_error), evaluated_prediction_loss=loss,
                W0_comparator_loss=comparator_loss, actual_path_R=R, D1=D1, H_energy=energy(H[1:]),
                H_norm_sum=float(np.linalg.norm(H[1:], axis=(1, 2)).sum()), cumulative_loss_bound=loss_bound,
                applied_interval_error_energy=output_error_energy, xi_energy=xi_energy, within_window_variation_energy=variation_energy,
                initial_and_tail_epsilon_energy=boundaries, exact_forcing_RMSE_bound_m=exact_forcing_bound,
                prediction_loss_bridge_RMSE_bound_m=loss_bridge_bound, update_bridge_RMSE_bound_m=update_bridge_bound,
                update_bound_over_actual_Q=update_bridge_bound/Q, raw_path=str(path), raw_sha256=sha(path))


def main():
    scope_path = HERE / "TWO_PILOT_CERTIFICATE_SCOPE_v1.json"
    output = HERE / "TWO_PILOT_CERTIFICATE_VALUES_v1.json"
    assert not output.exists()
    scope = load(scope_path)
    assert scope["scene_id"] == "DL1018_VAL_T2_C00_W10" and len(scope["rows"]) == 2
    assert {r["method"] for r in scope["rows"]} == {"C3", "C4"}
    result = dict(status="PASS_TWO_ALREADY_AUDITED_PATH_BOUND_NUMERIC_INEQUALITIES_NOT_THEORY_GATE",
                  scope_sha256=sha(scope_path), script_sha256=sha(__file__), rows=[evaluate(item) for item in scope["rows"]],
                  new_Plant=0, TEST_accessed=False, training_steps=0,
                  limits="Two development pilots only; H is state-dependent; posterior path bounds do not prove prior closed-loop stability or comparative performance.")
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
