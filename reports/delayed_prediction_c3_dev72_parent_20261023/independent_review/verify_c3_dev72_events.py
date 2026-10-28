"""Read-only C3 event audit, independent of the C2 comparator scorer."""

from __future__ import annotations

import hashlib
from pathlib import Path

import h5py
import numpy as np


EXPECTED_W0_SHA256 = "88f8c4f2495438c3797655c48bab1bf0c11ac2e27bff1f5f2a7423a8f0a2cf53"
ALLOWED_RUN_IDENTITY_SCHEMAS = {
    "C3_DELAYED_PREDICTION_RUN_IDENTITY_V1",  # frozen 12-scene C3 rows
    "C3_DELAYED_PREDICTION_DEV72_RUN_IDENTITY_V1",  # new DEV72 rows
}
EXPECTED_EVENT_INDICES = np.arange(320, 19991, 10, dtype=np.int64)
TOL = 1e-10


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _matlab_array(group: h5py.Group, name: str) -> np.ndarray:
    """Read a numeric MATLAB v7.3 array using the repository's HDF5 orientation."""
    value = np.asarray(group[name])
    return value.T if value.ndim == 2 else value


def _matlab_char(dataset: h5py.Dataset) -> str:
    value = np.asarray(dataset)
    if value.dtype.kind in "ui":
        return "".join(chr(int(code)) for code in value.reshape(-1)).rstrip("\x00")
    if value.dtype.kind == "S":
        return b"".join(value.reshape(-1).tolist()).decode("utf-8").rstrip("\x00")
    if value.dtype.kind == "U":
        return "".join(value.reshape(-1).tolist()).rstrip("\x00")
    raise AssertionError(f"Unsupported MATLAB char storage: {value.dtype}")


def _max_abs(value: np.ndarray) -> float:
    value = np.asarray(value)
    if value.size == 0:
        return 0.0
    if not np.isfinite(value).all():
        return float("inf")
    return float(np.max(np.abs(value)))


def verify(raw_path, expected_sha, canonical_scene_id):
    """Verify frozen candidate event equations and raw identity without a C2 scorer.

    ``expected_sha`` must come from the saved C3 status/release ledger. This
    function never derives an expected hash from the file being checked.
    """
    path = Path(raw_path).resolve(strict=True)
    expected_sha = str(expected_sha).lower()
    canonical_scene_id = str(canonical_scene_id)
    assert len(expected_sha) == 64 and all(c in "0123456789abcdef" for c in expected_sha)

    before_stat = path.stat()
    before_sha = _sha256(path)
    assert before_sha == expected_sha, f"raw SHA mismatch: {before_sha}"

    with h5py.File(path, "r") as raw:
        assert "runIdentity" in raw and "log" in raw, "Missing C3 raw identity/log"
        identity = raw["runIdentity"]
        identity_schema = _matlab_char(identity["schema"])
        assert identity_schema in ALLOWED_RUN_IDENTITY_SCHEMAS, identity_schema
        actual_scene_id = _matlab_char(identity["scene_id"])
        assert actual_scene_id == canonical_scene_id, (actual_scene_id, canonical_scene_id)

        log = raw["log"]
        read = lambda name: _matlab_array(log, name)
        valid = read("stage1_position_event_inference_valid").ravel().astype(bool)
        ids = np.flatnonzero(valid)
        assert np.array_equal(ids, EXPECTED_EVENT_INDICES), "Unexpected ready-event schedule"
        assert ids.size == 1968

        assert read("stage1_position_delayed_prediction_enabled").item() == 1
        assert read("stage1_position_replacement_enabled").item() == 1
        assert read("stage1_position_search_gamma").item() == 12
        assert read("stage1_position_search_kappa").item() == 1
        assert read("stage1_position_pcf_coordination_enabled").item() == 1

        initial = read("stage1_position_search_initial_weight")
        weight_initial = read("stage1_position_weight_initial")
        initial_sha = hashlib.sha256(
            np.asarray(initial, dtype="<f8").tobytes(order="F")
        ).hexdigest()
        assert initial_sha == EXPECTED_W0_SHA256, f"Unexpected fixed W0: {initial_sha}"
        assert np.array_equal(weight_initial, initial), "Candidate initial weight differs from W0"

        phi_all = read("stage1_position_event_phi_33")
        phi = phi_all[ids]
        wb = np.asarray(log["stage1_position_event_weight_before_33x3"]).transpose(0, 2, 1)
        wa = np.asarray(log["stage1_position_event_weight_after_33x3"]).transpose(0, 2, 1)
        assert wb.shape == wa.shape == (ids.size, 33, 3)
        assert np.array_equal(wb[0], initial), "First ready-event weight differs from W0"

        velocity = read("state")[:, 3:6]
        af = read("stage1_position_pcf_a_f_mps2")
        target = read("stage1_position_delayed_prediction_target_mps2")[ids]
        prev = read("stage1_position_delayed_prediction_prev_index_zero_based").ravel()[ids]
        assert np.isnan(prev[0]) and np.isnan(target[0]).all(), "First ready event must have no fabricated history"
        assert np.array_equal(prev[1:], ids[:-1]), "Delayed target does not use the previous ready event"

        # The interval is [j,k); this direct block mean is independent of the
        # runtime's accumulated delayed-target log.
        expected_target = np.asarray([
            (velocity[k] - velocity[j]) / 0.01 - af[j:k].mean(axis=0)
            for j, k in zip(ids[:-1], ids[1:])
        ])
        beta = np.minimum((ids + 1) * 0.001 / 1.8, 1.0)
        raw_output = np.einsum("nfi,nf->ni", wb, phi)
        residual = np.einsum("nfi,nf->ni", wb[1:], phi[:-1]) - expected_target
        gradient = np.zeros_like(wb)
        gradient[1:] = phi[:-1, :, None] * residual[:, None, :]
        s_eff = read("stage1_position_pcf_event_s_coord_eff_mps")[ids]
        expected_after = np.clip(
            wb
            - 0.12 * beta[:, None, None] * phi[:, :, None] * s_eff[:, None, :]
            - 0.00002 * wb
            - 0.01 * gradient,
            -60.0,
            60.0,
        )

        checks = {
            "unit_phi": _max_abs(np.linalg.norm(phi, axis=1) - 1.0),
            "finite_event_arrays": 0.0 if all(
                np.isfinite(a).all() for a in (phi, wb, wa, raw_output, s_eff, expected_target)
            ) else float("inf"),
            "beta_clock": _max_abs(read("stage1_position_event_beta").ravel()[ids] - beta),
            "event_dt": _max_abs(read("stage1_position_event_dt_s").ravel()[ids] - 0.01),
            "past_interval_target": _max_abs(target[1:] - expected_target),
            "output_before_update": _max_abs(
                read("stage1_position_event_raw_acceleration_mps2")[ids] - raw_output
            ),
            "applied_beta_clip": _max_abs(
                read("stage1_position_event_applied_acceleration_mps2")[ids]
                - beta[:, None] * np.clip(raw_output, -3.0, 3.0)
            ),
            "joint_projected_update": _max_abs(wa - expected_after),
            "weight_continuity": _max_abs(wb[1:] - wa[:-1]),
            "prediction_term_norm": _max_abs(
                read("stage1_position_delayed_prediction_term_norm").ravel()[ids]
                - 0.01 * np.linalg.norm(gradient, axis=(1, 2))
            ),
        }
        assert all(np.isfinite(error) and error < TOL for error in checks.values()), checks

    after_stat = path.stat()
    after_sha = _sha256(path)
    assert after_sha == before_sha == expected_sha, "raw changed during verification"
    assert (before_stat.st_size, before_stat.st_mtime_ns) == (
        after_stat.st_size,
        after_stat.st_mtime_ns,
    ), "raw stat changed during verification"
    return {
        "status": "PASS_C3_EVENT_AUDIT",
        "raw_path": str(path),
        "raw_sha256": after_sha,
        "run_identity_schema": identity_schema,
        "canonical_scene_id": actual_scene_id,
        "event_count": int(ids.size),
        "first_event_index_zero_based": int(ids[0]),
        "last_event_index_zero_based": int(ids[-1]),
        "w0_sha256": initial_sha,
        "checks_max_abs": checks,
    }
