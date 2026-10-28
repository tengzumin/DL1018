"""Independent direct-MAT check of all nine FIG8 high-frequency fit records."""
import csv
import hashlib
import json
from pathlib import Path

import h5py
import numpy as np


HERE = Path(__file__).resolve().parent
OUT = HERE / "PARENT_T2_HF_FIXED_INPUT_FIT_REVIEW.json"


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1048576), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    assert not OUT.exists(), "Preserve prior audit output"
    manifest = HERE / "PARENT_C3_ALL72_RAW_MANIFEST.json"
    table = HERE / "offline_diagnosis/C3_PREUPDATE_WEIGHT_FIT_PER_SCENE.csv"
    groups = HERE / "offline_diagnosis/C3_PREUPDATE_WEIGHT_FIT_GROUPS.csv"
    rows = json.loads(manifest.read_text(encoding="utf-8-sig"))["rows"]
    selected = [r for r in rows if "_T2_" in r["scene_id"] and 9 <= int(r["scene_id"][-2:]) <= 14]
    assert len(selected) == 9
    with table.open(encoding="utf-8-sig", newline="") as handle:
        cells = {(r["scene_id"], r["phase"], r["axis"]): r for r in csv.DictReader(handle)}
    with groups.open(encoding="utf-8-sig", newline="") as handle:
        group_cells = {(r["phase"], r["axis"]): r for r in csv.DictReader(handle) if r["group"] == "T2-HF9"}
    deltas, checks, max_diff = {}, [], 0.0
    for row in selected:
        raw = Path(row["path"])
        assert sha(raw) == row["sha256"]
        with h5py.File(raw, "r") as handle:
            log = handle["log"]
            ids = np.flatnonzero(np.asarray(log["stage1_position_event_inference_valid"]).ravel())
            assert np.array_equal(ids, np.arange(320, 19991, 10))
            feature = np.asarray(log["stage1_position_event_phi_33"])[:, ids[:-1]].T
            weights = np.asarray(log["stage1_position_event_weight_before_33x3"])[1:]
            initial = np.asarray(log["stage1_position_search_initial_weight"])
            velocity = np.asarray(log["state"])[3:6]
            # Disjoint 10-sample blocks implement the past-interval integral;
            # no import of the executor's MAT reader or reconstruction routine.
            af = np.asarray(log["stage1_position_pcf_a_f_mps2"])[:, 320:19990].T
        target = ((velocity[:, ids[1:]] - velocity[:, ids[:-1]]) / .01).T - af.reshape(1967, 10, 3).mean(axis=1)
        online = np.matmul(weights, feature[:, :, None])[:, :, 0]
        trained = (initial @ feature.T).T
        t = ids[1:] / 1000
        phases = {"ALL_0_20": np.ones(1967, bool), "EARLY_0.33_5": t < 5, "LATE_5_20": t >= 5}
        for phase, mask in phases.items():
            for axis, label in enumerate("XYZ"):
                e0, ew = trained[mask, axis] - target[mask, axis], online[mask, axis] - target[mask, axis]
                values = {"W0_rmse_mps2": np.sqrt(np.mean(e0 * e0)), "W0_bias_mps2": e0.mean(),
                          "Wk_preupdate_rmse_mps2": np.sqrt(np.mean(ew * ew)), "Wk_preupdate_bias_mps2": ew.mean()}
                values["Wk_minus_W0_rmse_mps2"] = values["Wk_preupdate_rmse_mps2"] - values["W0_rmse_mps2"]
                values["Wk_minus_W0_bias_mps2"] = values["Wk_preupdate_bias_mps2"] - values["W0_bias_mps2"]
                existing = cells[row["scene_id"], phase, label]
                assert int(existing["n_intervals"]) == mask.sum()
                for field, value in values.items():
                    difference = abs(float(existing[field]) - float(value))
                    max_diff = max(max_diff, difference)
                    assert difference < 1e-12, (row["scene_id"], phase, label, field, difference)
                deltas.setdefault((phase, label), []).append(float(values["Wk_minus_W0_rmse_mps2"]))
        checks.append({"scene_id": row["scene_id"], "raw_sha256": row["sha256"], "cells_checked": 9})
    for key, values in deltas.items():
        assert abs(np.mean(values) - float(group_cells[key]["Wk_minus_W0_rmse_mps2_mean_scene"])) < 1e-12
    z = deltas["ALL_0_20", "Z"]
    result = {"status": "PASS", "raw_scenes": 9, "metric_cells": 81, "numeric_fields_per_cell": 6,
              "maximum_absolute_difference_mps2": max_diff,
              "T2_HF9_Z_mean_Wk_minus_W0_rmse_mps2": float(np.mean(z)),
              "T2_HF9_Z_scenes_improving": int(np.sum(np.array(z) < 0)),
              "conclusion": "Reject simple online-update-corrupts-Z-fit explanation; fixed C3 trajectory only, no causal rollout claim",
              "new_sorties": 0, "TEST_accessed": False, "checks": checks,
              "source_refs": [{"path": str(p), "sha256": sha(p)} for p in [manifest, table, groups, Path(__file__)]]}
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: result[k] for k in ["status", "raw_scenes", "metric_cells", "maximum_absolute_difference_mps2", "T2_HF9_Z_mean_Wk_minus_W0_rmse_mps2", "T2_HF9_Z_scenes_improving"]}))


if __name__ == "__main__":
    main()
