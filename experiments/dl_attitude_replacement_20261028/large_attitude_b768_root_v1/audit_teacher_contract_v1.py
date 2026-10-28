"""Read-only spot audit of the B-only large attitude teacher dataset."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import h5py
import numpy as np
from scipy.io import loadmat

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
EXT = EXP.parents[2] / "REFERENCE_FIX_FULL72_20261021_022342_313" / "corrected_reference_training_v1"
COHORT = EXT / "g3_collection" / "manifests" / "G3_COHORT_1632.csv"
DATA = HERE / "DATASET.npz"
DATA_MANIFEST = HERE / "DATASET_MANIFEST.json"
OUT_JSON = HERE / "B768_TEACHER_CONTRACT_AUDIT_v1.json"
OUT_MD = HERE / "B768_TEACHER_CONTRACT_AUDIT_v1.md"
DMAX_EXPECTED = np.array([45.0, 45.0, 4.7124])
J0_C5_REFERENCE = [0.003257553333333334, 0.0032575533333333334, 0.006360648333333333]
TASKS = ("FIG8_3D", "HELIX", "SQUARE")
KNOWN_ACTIONS = {"PILOT6_IMPORT", "RUN_PLANT", "REUSE_HS_ACCEPTED", "REUSE_FULL72_B_REBUILD_D2_D4"}


def h5_text(ds):
    a = np.asarray(ds).reshape(-1)
    if a.dtype.kind in "ui":
        return "".join(chr(int(x)) for x in a if int(x) != 0)
    if a.dtype.kind in "SU":
        return "".join(x.decode() if isinstance(x, bytes) else str(x) for x in a).rstrip("\x00")
    return str(a[0]) if len(a) == 1 else ""


def get_h5_cfg_contract(path: Path):
    with h5py.File(path, "r") as f:
        cfg = f["runStart/cfg"] if "runStart/cfg" in f else f["cfg"]
        mode = h5_text(cfg["controller_morphology_mode"]).lower()
        rbf = cfg["rbf/attitude"]
        return mode, np.asarray(rbf["dmax"], dtype=float).reshape(-1), float(np.asarray(rbf["beta_rise_time"], dtype=float).reshape(-1)[0]), "mat_v73_hdf5"


def get_contract(path: Path):
    try:
        return get_h5_cfg_contract(path)
    except OSError:
        m = loadmat(path, variable_names=["runStart", "cfg"], simplify_cells=True)
        cfg = m["runStart"]["cfg"] if "runStart" in m else m["cfg"]
        return (str(cfg["controller_morphology_mode"]).lower(),
                np.asarray(cfg["rbf"]["attitude"]["dmax"], dtype=float).reshape(-1),
                float(np.asarray(cfg["rbf"]["attitude"]["beta_rise_time"], dtype=float).reshape(-1)[0]),
                "mat_v5_scipy")


def expected_source(row):
    action = row["g3_action"]
    if action == "RUN_PLANT":
        return row["g3_raw_path"], row["g3_run_start_path"], "g3_raw_path", "g3_run_start_path"
    if action in KNOWN_ACTIONS - {"RUN_PLANT"}:
        return row["raw_source_path"], row["input_run_start_path"], "raw_source_path", "input_run_start_path"
    raise ValueError(f"unsupported g3_action: {action}")


def main():
    rows = list(csv.DictReader(COHORT.open(encoding="utf-8-sig", newline="")))
    assert len(rows) == 1632 and {r["split"] for r in rows} == {"TRAIN", "VAL"}
    rows = [r for r in rows if r["role"] == "B"]
    manifest = json.loads(DATA_MANIFEST.read_text(encoding="utf-8"))
    records = manifest["records"]
    by_id = {r["planned_run_id"]: r for r in rows}
    assert len(rows) == len(records) == 816 and len(by_id) == 816
    assert len({r["episode_id"] for r in records}) == 816
    path_audit = []
    contract_audit = []
    for rec in records:
        row = by_id[rec["episode_id"]]
        assert row["split"] == rec["split"] and row["source_scene_id"] == rec["scene_id"]
        assert row["task"] == rec["task"] and row["role"] == rec["role"] == "B"
        raw, start, raw_key, start_key = expected_source(row)
        assert Path(raw).is_file() and Path(start).is_file()
        assert Path(rec["raw_path"]).resolve() == Path(raw).resolve()
        assert "test" not in raw.lower() and "test" not in start.lower()
        path_audit.append({"episode_id": rec["episode_id"], "action": row["g3_action"], "raw_field": raw_key, "run_start_field": start_key})
        mode, dmax, beta_rise, file_format = get_contract(Path(start))
        assert mode == "fixed" and np.array_equal(dmax, DMAX_EXPECTED) and beta_rise == 2.2
        contract_audit.append({"episode_id": rec["episode_id"], "mode": mode, "dmax_rad_s2": dmax.tolist(), "beta_rise_s": beta_rise, "run_start_format": file_format})

    with np.load(DATA, allow_pickle=False) as z:
        train_ids = z["train_ids"].astype(str)
        val_ids = z["val_ids"].astype(str)
        train_scenes = z["train_scene_ids"].astype(str)
        val_scenes = z["val_scene_ids"].astype(str)
        train_tasks = z["train_task_ids"].astype(str)
        val_tasks = z["val_task_ids"].astype(str)
        train_roles = z["train_role_ids"].astype(str)
        val_roles = z["val_role_ids"].astype(str)
        assert z["train_x"].shape == (768, 1999, 13) and z["train_y"].shape == (768, 1999, 3)
        assert z["val_x"].shape == (48, 1999, 13) and z["val_y"].shape == (48, 1999, 3)
        assert len(set(train_ids)) == 768 and len(set(val_ids)) == 48
        assert set(train_ids).isdisjoint(val_ids)
        assert set(train_ids) == {r["planned_run_id"] for r in rows if r["split"] == "TRAIN"}
        assert set(val_ids) == {r["planned_run_id"] for r in rows if r["split"] == "VAL"}
        assert set(train_scenes).isdisjoint(val_scenes)
        assert len(set(train_scenes)) == 768 and len(set(val_scenes)) == 48
        assert np.all(train_roles == "B") and np.all(val_roles == "B")
        assert {t: int(np.count_nonzero(train_tasks == t)) for t in TASKS} == {t: 256 for t in TASKS}
        assert {t: int(np.count_nonzero(val_tasks == t)) for t in TASKS} == {t: 16 for t in TASKS}
        assert np.isfinite(z["train_x"]).all() and np.isfinite(z["train_y"]).all()
        assert np.isfinite(z["val_x"]).all() and np.isfinite(z["val_y"]).all()

        # One fixed TRAIN scene for each task; match the saved 13-D inputs and labels to raw event rows.
        sample_results = []
        for task in TASKS:
            row = next(r for r in rows if r["split"] == "TRAIN" and r["task"] == task and "C15_W00" in r["planned_run_id"])
            rec = next(r for r in records if r["episode_id"] == row["planned_run_id"])
            raw_path, start_path, _, _ = expected_source(row)
            _, dmax, beta_rise, _ = get_contract(Path(start_path))
            ix = int(np.flatnonzero(train_ids == row["planned_run_id"])[0])
            with h5py.File(raw_path, "r") as f:
                log = f["log"]
                events = np.flatnonzero(np.asarray(log["attitude_event_flag"]).reshape(-1).astype(bool))
                assert np.array_equal(events, np.arange(10, 20000, 10))
                transition_time = np.asarray(log["transition_time"], dtype=float).reshape(-1)
                expected_t = np.arange(1, 2000, dtype=float) * .01
                assert np.max(np.abs(transition_time[events] - expected_t)) < 1e-10
                state = np.asarray(log["state"], dtype=float).T
                ref = np.asarray(log["filtered_attitude_reference"], dtype=float).T
                tau_nom = np.asarray(log["attitude_bs_nominal_torque_Nm"], dtype=float).T
                command = np.asarray(f["scene/arms/command"], dtype=float).T
                y = np.asarray(log["rbf_output_raw"], dtype=float).T
                y_u = np.asarray(log["rbf_output_unclipped"], dtype=float).T
                y_applied = np.asarray(log["attitude_rbf_estimate_acceleration_rads2"], dtype=float).T
                update = np.asarray(log["rbf_update_flag"]).reshape(-1)
                err = ref[events] - state[events, 6:9]
                err = np.arctan2(np.sin(err), np.cos(err))
                x = np.concatenate((err, state[events, 9:12], tau_nom[events], command[events]), axis=1)
                y_event = y[events]
                beta_expected = np.minimum((events + 1) * .001 / beta_rise, 1.0)
                clip_err = float(np.max(np.abs(y_event - np.clip(y_u[events], -dmax, dmax))))
                beta_apply_err = float(np.max(np.abs(y_applied[events] - beta_expected[:, None] * y_event)))
                assert np.all(update[events] == 1)
                assert x.shape == (1999, 13) and y_event.shape == (1999, 3)
                assert np.max(np.abs(x.astype(np.float32) - z["train_x"][ix])) <= 2e-6
                assert np.max(np.abs(y_event.astype(np.float32) - z["train_y"][ix])) <= 2e-6
                assert clip_err <= 1e-10 and beta_apply_err <= 1e-9
                assert float(np.max(np.abs(y_event))) > 0
                sample_results.append({
                    "episode_id": row["planned_run_id"], "task": task, "g3_action": row["g3_action"],
                    "event_count": len(events), "event_time_s_first_last": [float(expected_t[0]), float(expected_t[-1])],
                    "input_shape": list(x.shape), "target_shape": list(y_event.shape),
                    "input_npz_max_abs_error": float(np.max(np.abs(x.astype(np.float32) - z["train_x"][ix]))),
                    "target_npz_max_abs_error": float(np.max(np.abs(y_event.astype(np.float32) - z["train_y"][ix]))),
                    "target_clip_max_abs_error_rad_s2": clip_err,
                    "applied_beta_formula_max_abs_error_rad_s2": beta_apply_err,
                    "beta_formula": "min((zero_based_transition_index+1)*0.001/beta_rise_time_s,1)",
                    "logged_attitude_event_beta_used": False,
                    "target_max_abs_rad_s2": np.max(np.abs(y_event), axis=0).tolist(),
                })

    result = {
        "status": "PASS_B768_TRAINING_TEACHER_CONTRACT",
        "dataset_npz": str(DATA), "dataset_sha256": hashlib.sha256(DATA.read_bytes()).hexdigest(),
        "rows": {"train": 768, "val": 48, "all_roles": "B only", "physical_scene_overlap": False,
                 "train_task_counts": {t: 256 for t in TASKS}, "val_task_counts": {t: 16 for t in TASKS}},
        "source_path_resolution": {"status": "PASS_816_OF_816", "policy": "RUN_PLANT uses g3_raw_path/g3_run_start_path; all other recognized actions use raw_source_path/input_run_start_path", "action_counts": {k: sum(x["action"] == k for x in path_audit) for k in sorted(KNOWN_ACTIONS)}},
        "run_start_contract": {"status": "PASS_816_OF_816", "formats": {fmt: sum(x["run_start_format"] == fmt for x in contract_audit) for fmt in sorted({x["run_start_format"] for x in contract_audit})}, "controller_morphology_mode": "fixed", "dmax_rad_s2": DMAX_EXPECTED.tolist(), "beta_rise_time_s": 2.2},
        "feature_contract": {"status": "PASS_3_TASK_SPOTCHECK", "order": ["wrapped(filtered_attitude_reference-state_euler) rad x3", "state body_rate rad/s x3", "attitude_bs_nominal_torque Nm x3", "scene arms command unitless x4"], "event_alignment": "input[k] and rbf_output_raw[k] at same current 100-Hz transition event; events at 0.01..19.99s; no future fields", "matches": "C5 teacher FEATURE_ORDER and online trace feature_raw contract"},
        "target_contract": {"status": "PASS_3_TASK_SPOTCHECK", "field": "/log/rbf_output_raw", "meaning": "post-output-limit/pre-beta attitude RBF disturbance estimate", "unit": "rad/s^2 (RBF acceleration estimate; runtime applies beta then maps through plant inertia to torque)", "checks": "raw==clip(rbf_output_unclipped, +/- dmax); logged applied acceleration==cfg beta ramp * raw target", "existing_C5_fixed_J0_reference_kg_m2": J0_C5_REFERENCE, "J0_audit_status": "reference copied from existing C5 builder constant only; not re-derived or verified against these B768 raws"},
        "sample_checks": sample_results,
        "limitations": ["Raw full-file SHA-256 was not checked by extractor or this spot audit.", "Raw feature/label alignment and target/applied-ramp were independently checked on one TRAIN B episode per task; run_start cfg contract was checked for all 816 B episodes.", "attitude_event_beta log is not used because it is nonfinite on sampled raws; beta is recomputed from run_start cfg and runtime equation.", "No inertia fields or torque reconstruction were read.", "No TEST rows or raw files were read; no training was started."],
    }
    OUT_JSON.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        "# B768 attitude teacher contract audit v1", "",
        "**Status: PASS for the B-only training data contract.** This approves the extracted TRAIN/VAL arrays as causal 13-D inputs and 3-D post-limit/pre-beta RBF targets; it does not certify a not-yet-frozen GRU deployment implementation.", "",
        "## Checks", "",
        "- NPZ: TRAIN 768 and VAL 48; 1999 events per episode; shapes `(768,1999,13)/(768,1999,3)` and `(48,1999,13)/(48,1999,3)`. Task counts are 256/16 per task; physical TRAIN and VAL scenes are disjoint.",
        "- Source binding: action-specific raw/run_start paths match all 816 B records. `RUN_PLANT` uses G3 paths; PILOT/REUSE actions use source paths.",
        "- Run-start cfg: all 816 are `fixed`, dmax `[45,45,4.7124] rad/s²`, beta rise `2.2 s`.",
        "- Three task spot checks match NPZ features/labels to current event samples. Inputs are wrapped attitude error (rad), body rate (rad/s), nominal BS torque (N·m), and four arm commands. Target is `rbf_output_raw`, clipped by dmax before the beta ramp.",
        "- For each sample, `rbf_output_raw == clip(rbf_output_unclipped, ±dmax)` and the logged applied acceleration matches `min(k·dt/beta_rise,1) * rbf_output_raw` to numerical precision. The beta log itself is nonfinite in these raws, so it was not used.",
        f"- The target is acceleration disturbance in rad/s². The existing C5 builder's fixed J0 reference is `{J0_C5_REFERENCE}` kg·m²; this is recorded as provenance only and was not re-derived or applied to the B768 raws. No inertia fields or torque reconstruction were read.",
        "- The 13-D ordering matches the C5 teacher builder and C5 online feature trace contract. A new GRU runtime still needs to implement this same current-event feature order and beta application before deployment is considered audited.",
        "", "## Scope limits", "",
        "Raw full-file SHA-256 is not verified. Raw-to-NPZ features and labels were checked on one TRAIN B episode per task; run-start cfg was checked across all 816 B episodes. The existing fixed J0 reference was not revalidated against this expanded cohort. No TEST rows/files were accessed and no training was started.",
        "", "Machine-readable details are in `B768_TEACHER_CONTRACT_AUDIT_v1.json`.", "",
    ]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": result["status"], "audit_json": str(OUT_JSON), "audit_md": str(OUT_MD), "samples": sample_results}, ensure_ascii=False))


if __name__ == "__main__":
    main()
