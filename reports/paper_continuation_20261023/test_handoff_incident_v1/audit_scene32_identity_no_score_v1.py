"""Incident-only completeness/identity audit. Never computes tracking errors or Q."""
from pathlib import Path
import datetime
import hashlib
import importlib.util
import json
import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
SCENE = "DL1018_TEST_T2_C15_W13"
ATTEMPT = ROOT / "experiments/c5_test48_v9/runs/DSSM" / SCENE / "attempt_01"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text(node):
    return "".join(chr(int(x)) for x in node[()].ravel())


def compare(a, b, where, rows):
    assert type(a) is type(b), where
    if isinstance(a, h5py.Group):
        assert set(a.keys()) == set(b.keys()), where
        for key in a:
            if key == "scene_id":
                continue  # Opaque string object headers vary; exact IDs checked in pinned index/meta/log.
            compare(a[key], b[key], where + "/" + key, rows)
    else:
        assert a.dtype == b.dtype and a.shape == b.shape, where
        assert a.dtype.kind != "O", "Unexpected physical reference cell: " + where
        assert np.array_equal(a[()], b[()], equal_nan=True), where
        rows.append(where)


def main():
    raw, start = ATTEMPT / "raw_run.mat", ATTEMPT / "run_start.mat"
    hashes = {"raw": sha(raw), "run_start": sha(start)}
    shared = ROOT / "experiments/c5_test48_v3/input/TEST_SCENES_SHARED_v1.mat"
    cfgpack = ROOT / "experiments/c5_test48_v3/input/TEST_METHOD_CFG_OPTS_v1.mat"
    assert sha(shared) == "da207d858e8918f27c19fef30d4ad57206e20f1971e743515043d1a88a995d5c"
    assert sha(cfgpack) == "389fdfabd9fbd350d3bdd6df934cfe718eb7208bef2b7b4af02f1192cbb1b9e4"
    index_path = shared.with_name("TEST_INPUT_INDEX_v1.json")
    assert sha(index_path) == "90940a818d293c66c34423a63088113557518c5ecdfd528a3f37867f391eef68"
    assert json.loads(index_path.read_text())["scene_ids"][31] == SCENE
    matched = []
    with h5py.File(raw) as f, h5py.File(start) as s, h5py.File(shared) as p:
        expected = p[p["scenePacks"][()].ravel()[31]]["scene"]
        compare(expected, s["scene"], "frozen_scene_vs_run_start", matched)
        compare(s["scene"], f["scene"], "run_start_scene_vs_raw", matched)
        assert text(s["meta/scene_id"]) == SCENE
        assert text(s["meta/method_id"]) == "CORRECTED_DSSM14_G12_R32"
        assert text(s["meta/collector_tag"]) == "DSSM14_G12_R32"
        assert text(f["log/status"]) == "STABLE"
        assert text(f["log/collector"]) == "DSSM14_G12_R32"
        assert text(f["log/scene_id"]) == SCENE
        assert text(f["log/method"]) == "B2-RBF-Full-SPLIT"
        assert f["log/time"].shape == (1, 20001) and f["log/state"].shape == (12, 20001)
        assert np.allclose(f["log/time"][()].ravel(), np.arange(20001) * .001, rtol=0, atol=1e-12)
        assert int(f["log/last_transition"][()].item()) == 20000
        finite = []
        for key in ["state", "reference/position", "requested_generalized", "allocated_generalized", "realized_generalized", "motor_command"]:
            assert np.isfinite(f["log/" + key][()]).all(), key
            finite.append(key)
        assert "runIdentity" not in f

    reader_path = ROOT / "reports/paper_continuation_20261023/test_raw_review_v1/audit_test48_raw_v1.py"
    assert sha(reader_path) == "31229d1b9d137ec2847b25b7a32c3d0183e517fac963dc2ed01de74bcde11d45"
    spec = importlib.util.spec_from_file_location("incident_identity_helpers", reader_path)
    v1 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(v1)
    _, c5, _, decoder, _ = v1.verify_helpers()
    snapshots = v1.read_mat_cell_list(cfgpack, "methodSnapshots", c5, decoder, 6)
    frozen = snapshots[1]
    for name in ["cfg", "opts"]:
        actual = v1.mat_section(start, name, c5, decoder)
        expected = frozen[name]
        if name == "opts":
            actual = dict(actual)
            actual.pop("r2e_first_plant_step_marker", None)
        v1.equal_mat(expected, actual, c5, decoder, "scene32 frozen " + name)
    assert sha(raw) == hashes["raw"] and sha(start) == hashes["run_start"]
    result = {"status": "PASS_SCENE32_NUMERIC_COMPLETENESS_AND_FROZEN_IDENTITY_ONLY", "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "scene_id": SCENE, "hashes": hashes, "physical_fields_compared": matched, "finite_log_fields": finite,
              "cfg_opts_match_frozen_pack": True, "OS_exit": "UNKNOWN", "runIdentity_missing": True,
              "original_status_rewritten": False, "score_or_tracking_error_computed": False,
              "scope": "Incident recovery evidence only; does not satisfy original natural-OS0/final-identity gate, and does not approve a paper result or a rerun."}
    output = HERE / "PARENT_SCENE32_IDENTITY_NO_SCORE_v1.json"
    assert not output.exists()
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
