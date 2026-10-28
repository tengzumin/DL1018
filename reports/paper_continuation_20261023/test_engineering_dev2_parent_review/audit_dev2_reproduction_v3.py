"""Independently compare the two approved engineering DEV replays with old raw.

No TEST files are loaded. Import is inert; explicit paths are required by the CLI.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
REPORT = ROOT / "reports/paper_continuation_20261023"
MANIFEST = REPORT / "test_entry_v3/TEST_METHOD_SOURCE_MANIFEST_v1.json"
WRAPPER = REPORT / "test_raw_review_v1/audit_test48_raw_v1.py"
PINS = {
    "manifest": "b9ed7fef91bf61b03e4f51d8a9cbaf7233484ac6faa4750827aefb7e247f9633",
    "wrapper": "31229d1b9d137ec2847b25b7a32c3d0183e517fac963dc2ed01de74bcde11d45",
    "DSSM": "e54111ca11559ccb5d1e7c9ca9824db0b225234b2cff3497d5cfe71e1878c8d8",
    "KAN": "977a948da36402f869046782344e9a8231f34cc5d982a1ee8c462170fc695c2d",
}
SCENE = "DL1018_VAL_T1_C00_W07"
# Wall-clock costs vary between processes. Physical/event time vectors are compared.
EXCLUDED_TIMERS = {
    "controller_call_time_s", "network_call_time_s",
    "stage1_position_inference_time_s", "stage1_position_event_inference_time_s",
}
REQUIRED = {
    "state", "initial_state", "time", "transition_time", "reference/position",
    "requested_generalized", "controller_clipped_generalized", "allocated_generalized",
    "realized_generalized", "motor_command", "motor_setpoint", "motor_saturated",
    "generalized_clipped", "tilt_limited", "arms/command", "environment_wind_I",
    "stage1_position_weight_initial", "stage1_position_weight_final",
    "stage1_position_event_weight_before_33x3", "stage1_position_event_weight_after_33x3",
    "stage1_position_pcf_r_f_mps2", "stage1_position_pcf_eta_before_mps",
    "stage1_position_pcf_eta_after_mps", "stage1_position_applied_acceleration_mps2",
}


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load_wrapper():
    assert sha(MANIFEST) == PINS["manifest"]
    assert sha(WRAPPER) == PINS["wrapper"]
    spec = importlib.util.spec_from_file_location("dev2_pinned_raw_helpers", WRAPPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, module.verify_helpers()


def numeric_inventory(group):
    result = {}

    def visit(name, obj):
        if isinstance(obj, h5py.Dataset) and obj.dtype.kind in "fiub":
            if obj.attrs.get("MATLAB_class") not in (b"char", b"string"):
                result[name] = obj

    group.visititems(visit)
    return result


def audit(alias, new_path, manifest, wrapper, helpers):
    scorer, c5, _, decoder, _ = helpers
    method = next(v for v in manifest["methods"] if v["alias"] == alias)
    old_start = Path(method["cfg_opts_snapshot_path"])
    old_path = old_start.with_name("raw_run.mat")
    new_path = new_path.resolve(strict=True)
    assert new_path.is_relative_to(ROOT / "experiments/c5_test48_v5")
    assert SCENE in str(new_path) and "TEST_" not in str(new_path)
    assert old_path != new_path and sha(old_start) == method["cfg_opts_snapshot_sha256"]
    assert sha(old_path) == PINS[alias]
    new_sha = sha(new_path)
    new_start = new_path.with_name("run_start.mat")
    for name in ("cfg", "opts"):
        old_value = wrapper.mat_section(old_start, name, c5, decoder)
        new_value = wrapper.mat_section(new_start, name, c5, decoder)
        if name == "opts":
            old_value.pop("r2e_first_plant_step_marker", None)
            new_value.pop("r2e_first_plant_step_marker", None)
        wrapper.equal_mat(
            old_value, new_value, c5, decoder, f"{alias} historical {name}",
        )
    input_rows = []
    with h5py.File(old_start, "r") as old, h5py.File(new_start, "r") as new:
        for section in ("scene", "sceneMeta", "spec"):
            left, right = numeric_inventory(old[section]), numeric_inventory(new[section])
            assert set(left) == set(right)
            for key in sorted(left):
                a, b = np.asarray(left[key]), np.asarray(right[key])
                assert a.dtype == b.dtype and a.shape == b.shape
                assert np.array_equal(a, b, equal_nan=True), f"{section}/{key}"
                input_rows.append(f"{section}/{key}")
    rows = []
    with h5py.File(old_path, "r") as old, h5py.File(new_path, "r") as new:
        left, right = numeric_inventory(old["log"]), numeric_inventory(new["log"])
        assert set(left) == set(right), (set(left) - set(right), set(right) - set(left))
        assert REQUIRED <= left.keys()
        for key in sorted(left):
            if key in EXCLUDED_TIMERS:
                a = np.asarray(right[key])
                assert np.isfinite(a).all() and (a >= 0).all()
                continue
            a, b = np.asarray(left[key]), np.asarray(right[key])
            assert a.dtype == b.dtype and a.shape == b.shape, key
            assert np.array_equal(a, b, equal_nan=True), key
            rows.append({"field": key, "shape": list(a.shape), "dtype": str(a.dtype),
                         "exact_value_equal_including_matching_NaN": True})
    metrics = []
    for path, digest in ((old_path, PINS[alias]), (new_path, new_sha)):
        metrics.append(scorer.score(dict(scene_id=SCENE, method=method["method_id"],
                                         path=str(path), sha256=digest)))
    for key in metrics[0]:
        if key not in {"path", "sha256", "controller_mean_s", "controller_p95_s"}:
            assert metrics[0][key] == metrics[1][key], key
    assert sha(new_path) == new_sha and sha(old_path) == PINS[alias]
    return {"alias": alias, "scene_id": SCENE, "historical_raw_path": str(old_path),
            "historical_raw_sha256": PINS[alias], "new_raw_path": str(new_path),
            "new_raw_sha256": new_sha, "historical_run_start_sha256": sha(old_start),
            "new_run_start_sha256": sha(new_start), "numeric_log_arrays": rows,
            "excluded_wall_clock_fields": sorted(EXCLUDED_TIMERS),
            "excluded_scope": "Non-numeric diagnostic strings/cells and identity metadata; numeric physical/event times remain compared.",
            "cfg_opts_match_excluding_marker_paths": True,
            "numeric_scene_metadata_spec_fields_exact": input_rows,
            "opaque_string_limit": "MATLAB string object serialization is not text decoding; full scene semantic equality is separately checked by the released MATLAB engineering entry. Character scene identity is reviewed in run_start metadata.",
            "Q_m": metrics[1]["Q_0_20_m"],
            "external_identity_sha256": metrics[1]["external_identity_sha256"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dssm", type=Path, required=True)
    parser.add_argument("--kan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    assert not args.output.exists()
    wrapper, helpers = load_wrapper()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
    result = {"schema": "PARENT_DEV2_FULL_ARRAY_REPRODUCTION_V1", "TEST_accessed": False,
              "status": "PASS_TWO_OLD_DEV_FULL_NUMERIC_LOG_REPRODUCTIONS",
              "scope": "Engineering numerical comparison; natural OS/source/release/marker review is separate.",
              "checker_sha256": sha(Path(__file__)),
              "rows": [audit("DSSM", args.dssm, manifest, wrapper, helpers),
                       audit("KAN", args.kan, manifest, wrapper, helpers)]}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "output": str(args.output),
                      "sha256": sha(args.output)}))


if __name__ == "__main__":
    main()
