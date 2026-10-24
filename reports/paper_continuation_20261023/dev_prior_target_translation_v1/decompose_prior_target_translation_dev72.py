"""Read-only decomposition of frozen W0 prior error under the logged PCF target shift.

This diagnostic reads only the frozen C5 DEV72 raw files listed by the audited
parent review. It invokes no scorer, simulator, trainer, or optimizer.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
from pathlib import Path

import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
REVIEW_PATH = ROOT / "reports/paper_continuation_20261023/c5_dev72_parent_review/C5_DEV72_RAW_PARENT_REVIEW_v3.json"
AUDIT_SOURCE = ROOT / "reports/paper_continuation_20261023/c5_dev72_parent_review/audit_c5_dev72_raw_parent_v4.py"
LOCK_PATH = ROOT / "experiments/position_axis_coordinate_c5_dev72_20261023/C5_DEV72_INPUT_LOCK_v3.json"
CONTRACT_PATH = ROOT / "experiments/position_axis_coordinate_c5_dev72_20261023/C5_DEV72_RUN_CONTRACT_v3.json"
DECODER_PATH = ROOT / "reports/paper14_v2/phase1/audit_w15_position_replay.py"
DEFAULT_OUTPUT = ROOT / "reports/paper_continuation_20261023/dev_prior_target_translation_v1/DEV72_PRIOR_TARGET_TRANSLATION_ENERGY_v1.json"
AUDIT_SOURCE_SHA256 = "d82e089c7d41f39c620daea63d95315632e6fb2f80addf4dc12e6a4603b8e57e"
DECODER_SHA256 = "372d92cb17da99884e742d3fa0c877200c3bb2bc6fac7f10e7a1a046b97a76af"
INPUT_LOCK_SHA256 = "82024c01276cc4bfbd9b7772cf5332dee3fdfcbed422969589b68f1c90ed2d75"
CONTRACT_SHA256 = "6ac3cd505dc13fc5b7e6e0cdef966b21225b54d6f847d32177d43f7c678c8150"
PARENT_REVIEW_SHA256 = "bb34889559d95a1c995d4d420e3b3d7a702908b58b47cce969dc508a1c697fab"
EXPECTED_W0_SHA256 = "88f8c4f2495438c3797655c48bab1bf0c11ac2e27bff1f5f2a7423a8f0a2cf53"
EXPECTED_IDS = np.arange(320, 19991, 10, dtype=np.int64)
MASK = np.array([1.0, 1.0, 0.0])
DT = 0.001


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_pinned_decoder():
    assert sha256_file(DECODER_PATH) == DECODER_SHA256
    spec = importlib.util.spec_from_file_location("pinned_c5_mat_decoder", DECODER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def matlab_array(decoder, node) -> np.ndarray:
    """Use the pinned decoder's MATLAB-axis normalization for one HDF5 leaf."""
    return np.asarray(decoder.h5_tree(node))


def scene_identity(scene_id: str) -> dict[str, str]:
    match = re.fullmatch(r"DL1018_(DEV|VAL)_T([1-3])_C\d+_W(\d{2})", scene_id)
    assert match, scene_id
    return {"split": match.group(1), "task": f"T{match.group(2)}", "wind": f"W{match.group(3)}"}


def phase_energy(e_phys: np.ndarray, e_coord: np.ndarray, c: np.ndarray, selected: np.ndarray) -> dict:
    assert selected.ndim == 1 and selected.size == e_phys.shape[0]
    assert np.any(selected)
    ep = np.sum(e_phys[selected] ** 2, axis=0)
    ec = np.sum(e_coord[selected] ** 2, axis=0)
    c2 = np.sum(c[selected] ** 2, axis=0)
    cross = -2.0 * np.sum(e_phys[selected] * c[selected], axis=0)
    residual = ec - (ep + c2 + cross)
    assert float(np.max(np.abs(residual))) < 1e-12, residual
    return {
        "interval_count": int(np.count_nonzero(selected)),
        "E_phys_axis_sum_(mps2)^2": ep.tolist(),
        "E_coord_axis_sum_(mps2)^2": ec.tolist(),
        "sum_c2_axis_(mps2)^2": c2.tolist(),
        "cross_minus2_ephys_c_axis_(mps2)^2": cross.tolist(),
        "identity_residual_axis_(mps2)^2": residual.tolist(),
    }


def read_scene(row: dict, decoder, expected_w0_sha: str) -> dict:
    scene_id = row["scene_id"]
    metrics = row["C5_metrics"]
    assert metrics["scene_id"] == scene_id and metrics["method"] == "C5_M110"
    raw_path = Path(metrics["path"])
    assert raw_path.is_file(), raw_path
    raw_sha = sha256_file(raw_path)
    assert raw_sha.lower() == metrics["sha256"].lower(), (scene_id, raw_sha, metrics["sha256"])

    with h5py.File(raw_path, "r") as mat:
        log = mat["log"]

        def read(key: str) -> np.ndarray:
            assert key in log, (scene_id, key)
            return matlab_array(decoder, log[key])

        ids = np.flatnonzero(read("stage1_position_event_inference_valid").astype(bool).ravel())
        assert np.array_equal(ids, EXPECTED_IDS) and ids.size == 1968, scene_id
        mask = np.asarray(read("stage1_position_coordinate_mask"), dtype=float).ravel()
        assert np.array_equal(mask, MASK), (scene_id, mask)
        w0 = np.asarray(read("stage1_position_search_initial_weight"), dtype=np.float64)
        assert w0.shape == (33, 3) and np.isfinite(w0).all(), (scene_id, w0.shape)
        w0_sha = hashlib.sha256(np.asarray(w0, dtype="<f8").tobytes(order="F")).hexdigest()
        assert w0_sha.lower() == expected_w0_sha.lower(), (scene_id, w0_sha)

        phi = np.asarray(read("stage1_position_event_phi_33"), dtype=float)
        state = np.asarray(read("state"), dtype=float)
        a_req = np.asarray(read("stage1_position_pcf_a_req_mps2"), dtype=float)
        r_f = np.asarray(read("stage1_position_pcf_r_f_mps2"), dtype=float)
        target = np.asarray(read("stage1_position_delayed_prediction_target_mps2"), dtype=float)[ids]
        previous = np.asarray(read("stage1_position_delayed_prediction_prev_index_zero_based"), dtype=float).ravel()[ids]

    assert phi.shape[1] == 33 and phi.shape[0] > ids[-1], (scene_id, phi.shape)
    assert state.shape[1] >= 6 and state.shape[0] > ids[-1], (scene_id, state.shape)
    assert a_req.shape[1] == r_f.shape[1] == 3 and a_req.shape[0] >= ids[-1], scene_id
    assert np.isnan(previous[0]) and np.array_equal(previous[1:], ids[:-1]), scene_id
    assert target.shape == (ids.size, 3) and np.isnan(target[0]).all(), scene_id

    start, end = ids[:-1], ids[1:]
    assert np.all(end - start == 10)
    interval_dt = (end - start)[:, None] * DT
    dv = (state[end, 3:6] - state[start, 3:6]) / interval_dt
    req_integral = np.vstack((np.zeros((1, 3)), np.cumsum(DT * a_req, axis=0)))
    rf_integral = np.vstack((np.zeros((1, 3)), np.cumsum(DT * r_f, axis=0)))
    mean_req = (req_integral[end] - req_integral[start]) / interval_dt
    c = ((rf_integral[end] - rf_integral[start]) / interval_dt) * MASK
    y0 = dv - mean_req
    y_m = y0 + c
    assert float(np.max(np.abs(y_m - target[1:]))) < 1e-10, (scene_id, float(np.max(np.abs(y_m - target[1:]))))

    # The first member of each completed interval is phi_prev; use the launch-frozen trained W0.
    prediction = phi[start] @ w0
    e_phys = prediction - y0
    e_coord = prediction - y_m
    identity_residual = e_coord**2 - (e_phys**2 + c**2 - 2.0 * e_phys * c)
    assert float(np.max(np.abs(identity_residual))) < 1e-12, scene_id

    early = end <= 5000  # completed intervals ending at t <= 5 s
    late = start >= 5000  # completed intervals starting at t >= 5 s
    assert np.all(early | late) and not np.any(early & late), scene_id
    phases = {
        "all_0_20": np.ones(start.size, dtype=bool),
        "0_5": early,
        "5_20": late,
    }
    assert sum(np.count_nonzero(mask_) for key, mask_ in phases.items() if key != "all_0_20") == start.size
    identity = scene_identity(scene_id)
    return {
        "scene_id": scene_id,
        **identity,
        "external_identity_sha256": metrics["external_identity_sha256"],
        "raw_path": str(raw_path),
        "raw_sha256": raw_sha,
        "w0_sha256": w0_sha,
        "interval_count": int(start.size),
        "max_abs_recorded_target_difference_mps2": float(np.max(np.abs(y_m - target[1:]))),
        "max_abs_energy_identity_residual_(mps2)^2": float(np.max(np.abs(identity_residual))),
        "phases": {name: phase_energy(e_phys, e_coord, c, selector) for name, selector in phases.items()},
    }


def summarize(rows: list[dict], phase: str) -> dict:
    selected = [row for row in rows]
    assert selected
    energy = [row["phases"][phase] for row in selected]
    ep = np.sum([item["E_phys_axis_sum_(mps2)^2"] for item in energy], axis=0)
    ec = np.sum([item["E_coord_axis_sum_(mps2)^2"] for item in energy], axis=0)
    c2 = np.sum([item["sum_c2_axis_(mps2)^2"] for item in energy], axis=0)
    cross = np.sum([item["cross_minus2_ephys_c_axis_(mps2)^2"] for item in energy], axis=0)
    residual = ec - (ep + c2 + cross)
    n = sum(item["interval_count"] for item in energy)
    assert float(np.max(np.abs(residual))) < 1e-10, residual
    return {
        "scene_count": len(selected),
        "interval_count": n,
        "E_phys_axis_sum_(mps2)^2": ep.tolist(),
        "E_coord_axis_sum_(mps2)^2": ec.tolist(),
        "sum_c2_axis_(mps2)^2": c2.tolist(),
        "cross_minus2_ephys_c_axis_(mps2)^2": cross.tolist(),
        "identity_residual_axis_(mps2)^2": residual.tolist(),
        "E_phys_mean_per_interval_axis_(mps2)^2": (ep / n).tolist(),
        "E_coord_mean_per_interval_axis_(mps2)^2": (ec / n).tolist(),
        "sum_c2_mean_per_interval_axis_(mps2)^2": (c2 / n).tolist(),
        "cross_mean_per_interval_axis_(mps2)^2": (cross / n).tolist(),
        "E_phys_total_sum_(mps2)^2": float(ep.sum()),
        "E_coord_total_sum_(mps2)^2": float(ec.sum()),
        "sum_c2_total_(mps2)^2": float(c2.sum()),
        "cross_total_(mps2)^2": float(cross.sum()),
        "identity_residual_total_(mps2)^2": float(residual.sum()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline same-state W0/y0/yM energy decomposition for frozen C5 DEV72.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    assert sha256_file(AUDIT_SOURCE) == AUDIT_SOURCE_SHA256
    assert sha256_file(DECODER_PATH) == DECODER_SHA256
    assert sha256_file(LOCK_PATH) == INPUT_LOCK_SHA256
    assert sha256_file(CONTRACT_PATH) == CONTRACT_SHA256
    assert sha256_file(REVIEW_PATH) == PARENT_REVIEW_SHA256
    review = json.loads(REVIEW_PATH.read_text(encoding="utf-8-sig"))
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8-sig"))
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8-sig"))
    assert review["status"] == "PASS_C5_DEV72_RAW_ALL_EVENTS_PARENT_AUDIT"
    assert review["scene_count"] == len(review["rows"]) == 72
    assert review["TEST_accessed"] is False and review["plant_calls_in_audit"] == 0
    assert review["new_event_audit_script_sha256"] == AUDIT_SOURCE_SHA256
    assert review["mat_decoder_sha256"] == DECODER_SHA256
    assert review["input_lock_sha256"] == INPUT_LOCK_SHA256
    assert review["run_contract_sha256"] == CONTRACT_SHA256
    assert len(lock["scene_ids_all_72"]) == 72 and lock["coordinate_mask"] == [1, 1, 0]
    assert [row["scene_id"] for row in review["rows"]] == lock["scene_ids_all_72"]
    assert sum(scene["source_split"] == "DEV" for scene in lock["scenes"]) == 24
    assert sum(scene["source_split"] == "VAL" for scene in lock["scenes"]) == 48
    assert contract["model"]["id"] == "DSSM14" and contract["model"]["seed"] == 2026102001
    assert contract["model"]["selected_step"] == 60000 and contract["model"]["W0_sha256"] == EXPECTED_W0_SHA256
    decoder = load_pinned_decoder()

    per_scene = [read_scene(row, decoder, contract["model"]["W0_sha256"]) for row in review["rows"]]
    assert len({row["scene_id"] for row in per_scene}) == 72
    assert all(row["w0_sha256"] == EXPECTED_W0_SHA256 for row in per_scene)
    groups = {
        "ALL72": per_scene,
        "HF_W09_W14": [row for row in per_scene if 9 <= int(row["wind"][1:]) <= 14],
        "W15": [row for row in per_scene if row["wind"] == "W15"],
        "T1": [row for row in per_scene if row["task"] == "T1"],
        "T2": [row for row in per_scene if row["task"] == "T2"],
        "T3": [row for row in per_scene if row["task"] == "T3"],
    }
    assert {name: len(rows) for name, rows in groups.items()} == {
        "ALL72": 72, "HF_W09_W14": 28, "W15": 6, "T1": 24, "T2": 24, "T3": 24,
    }
    summaries = {
        group: {phase: summarize(rows, phase) for phase in ("all_0_20", "0_5", "5_20")}
        for group, rows in groups.items()
    }
    result = {
        "status": "PASS_DEV72_W0_PRIOR_TARGET_TRANSLATION_DECOMPOSITION",
        "interpretation": "offline same-recorded-state readout/target accounting only; no closed-loop counterfactual, causality, stability, or novelty claim",
        "prior_evidence_boundary": "The Y versus Y+Mrf relation and fixed-W0 comparisons, including early/late windows and axes, are established on TRAIN/training-VAL Teacher B/POS_OFF traces; this script only measures the distinct frozen C5 M110 PCF-on DEV72 paths and makes the squared-energy cross term explicit.",
        "identity": {
            "parent_review_json_sha256": PARENT_REVIEW_SHA256,
            "input_lock_sha256": INPUT_LOCK_SHA256,
            "run_contract_sha256": CONTRACT_SHA256,
            "pinned_decoder_sha256": DECODER_SHA256,
            "pinned_event_audit_source_sha256": AUDIT_SOURCE_SHA256,
            "script_sha256": sha256_file(Path(__file__)),
            "model_id": contract["model"]["id"],
            "seed": contract["model"]["seed"],
            "selected_step": contract["model"]["selected_step"],
            "W0_sha256": contract["model"]["W0_sha256"],
            "coordinate_mask": lock["coordinate_mask"],
            "scene_count": 72,
            "raw_files_sha_verified": 72,
            "scorer_calls": 0,
            "plant_calls": 0,
            "training_or_optimizer_steps": 0,
        },
        "definitions": {
            "interval_pair": "j=ids[q], k=ids[q+1]; ids are logged valid event indices, every 10 plant steps",
            "phi_prev": "logged stage1_position_event_phi_33 at j",
            "prediction": "frozen trained W0^T phi_prev, without online adaptation/beta/output clip",
            "y0": "(v[k]-v[j])/(0.001*(k-j)) - mean(stage1_position_pcf_a_req_mps2[j:k])",
            "c": "mean(mask * stage1_position_pcf_r_f_mps2[j:k]), mask=[1,1,0]",
            "yM": "y0+c; independently checked against the logged delayed_prediction_target_mps2 at k",
            "identity": "||e_coord||^2 = ||e_phys||^2 + ||c||^2 - 2<e_phys,c>, e_phys=W0^T phi_prev-y0, e_coord=W0^T phi_prev-yM",
            "phase_partition": "0_5 includes completed intervals ending at t<=5s; 5_20 starts at t>=5s",
            "units": "axis energies are summed squared acceleration errors in (m/s^2)^2; per-interval means are also reported",
        },
        "group_summaries": summaries,
        "per_scene": per_scene,
    }
    if args.output.exists():
        raise FileExistsError(args.output)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "output": str(args.output), "scenes": len(per_scene), "groups": {k: len(v) for k, v in groups.items()}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())






