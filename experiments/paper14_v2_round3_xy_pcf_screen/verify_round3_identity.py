"""Read-only verifier for frozen R3 inputs and future candidate attempt identity."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import sys

import h5py
import numpy as np

HERE = Path(__file__).resolve().parent
LOCK_PATH = HERE / "frozen_inputs.json"
EXPECTED_IDS = (
    "DL1018_VAL_T2_C00_W10", "DL1018_VAL_T2_C02_W12", "DL1018_VAL_T2_C05_W15",
    "DL1018_VAL_T2_C06_W00", "DL1018_VAL_T1_C02_W09", "DL1018_VAL_T1_C05_W12",
    "DL1018_VAL_T1_C08_W15", "DL1018_VAL_T1_C00_W07", "DL1018_VAL_T3_C12_W09",
    "DL1018_VAL_T3_C00_W13", "DL1018_VAL_T3_C02_W15", "DL1018_VAL_T3_C03_W00",
)
EXPECTED_BANDS = (
    "W09_W11", "W12_W14", "W15", "W00_W08", "W09_W11", "W12_W14",
    "W15", "W00_W08", "W09_W11", "W12_W14", "W15", "W00_W08",
)
TOL = 1e-12


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def identity(path: Path) -> tuple[str, int, int]:
    before = path.stat()
    digest = sha256(path)
    after = path.stat()
    key0 = (before.st_size, before.st_mtime_ns)
    key1 = (after.st_size, after.st_mtime_ns)
    if key0 != key1:
        raise RuntimeError(f"file changed during hash read: {path}")
    return digest, after.st_size, after.st_mtime_ns


def check_hash(path_value: str, expected: str, label: str) -> tuple[str, int, int]:
    path = Path(path_value)
    if not path.is_file():
        raise RuntimeError(f"missing {label}: {path}")
    # The R3 static checker is source code, not TEST data; all other TEST-token paths remain sealed.
    is_local_static_source = path.resolve() == (HERE / "static_test_round3.ps1").resolve()
    if not is_local_static_source and re.search(r"(^|[_-])TEST([_-]|$)", str(path), re.I):
        raise RuntimeError(f"sealed TEST path refused: {path}")
    actual = identity(path)
    if actual[0].lower() != expected.lower():
        raise RuntimeError(f"{label} SHA256 mismatch: {path}")
    return actual


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def verify_inputs(lock: dict[str, object]) -> dict[str, object]:
    if lock.get("schema") != "ROUND3_XY_PCF_SCREEN_INPUTS_V1":
        raise RuntimeError("unexpected R3 lock schema")
    if Path(lock["experiment_dir"]).resolve() != HERE.resolve():
        raise RuntimeError("experiment_dir does not resolve to this isolated R3 directory")
    if lock["run"].get("eta_mask") != [1, 1, 0] or lock["single_difference"].get("R3") != [1, 1, 0]:
        raise RuntimeError("candidate eta mask changed")
    if lock["run"].get("head_type") != "FEATURE" or not lock["run"].get("pcf_enabled"):
        raise RuntimeError("R3 must retain FEATURE and PCF-on")
    if lock["safety"].get("read_test") is not False or lock["analysis"].get("test_access") is not False:
        raise RuntimeError("R3 lock does not explicitly forbid TEST access")
    if len(lock["scenes"]) != 12 or tuple(row["scene_id"] for row in lock["scenes"]) != EXPECTED_IDS:
        raise RuntimeError("R3 scene IDs/order are not the frozen 12 VAL IDs")
    if tuple(row["band"] for row in lock["scenes"]) != EXPECTED_BANDS:
        raise RuntimeError("R3 scene bands/order differ from taskbook")
    if any(row.get("split") != "VAL" or not row["scene_id"].startswith("DL1018_VAL_") for row in lock["scenes"]):
        raise RuntimeError("non-VAL scene found in R3 lock")

    taskbook = lock["taskbook"]
    check_hash(taskbook["path"], taskbook["sha256"], "frozen taskbook")
    if taskbook["sha256"].lower() != "a9d876f0e22175785f184707ba0f35090be3adf6a25317e83c39a9c88a1ccb4a":
        raise RuntimeError("frozen taskbook SHA differs from task assignment")
    check_hash(lock["frozen_taskbook_manifest"]["path"], lock["frozen_taskbook_manifest"]["sha256"], "taskbook manifest")

    upstream = lock["upstream_round2"]
    for label, path_key, hash_key in (
        ("R2 lock", "lock_path", "lock_sha256"), ("R2 results", "results_path", "results_sha256"),
        ("R2 summary", "summary_path", "summary_sha256"), ("R2 replay script", "audit_script_path", "audit_script_sha256"),
        ("R2 replay output", "audit_json_path", "audit_json_sha256"),
        ("R2 gate audit", "independent_gate_path", "independent_gate_sha256"),
        ("R2 root review", "root_review_path", "root_review_sha256"),
        ("R2 main review", "main_review_path", "main_review_sha256"),
        ("R2 probe review", "probe_review_path", "probe_review_sha256"),
    ):
        check_hash(upstream[path_key], upstream[hash_key], label)
    if upstream["lock_sha256"].lower() != "92bf5bb355e473360f4ea6023dc508ed7c5369733eb083dfe38b26e53bf6bd58":
        raise RuntimeError("upstream R2 input lock is not the frozen Round 2 lock")

    r2_lock = json.loads(Path(upstream["lock_path"]).read_text(encoding="utf-8-sig"))
    for section in ("model", "model_binding", "normalizer", "plantFiles", "runtimeFiles", "scene_list", "reuse_manifest", "rescores"):
        if lock.get(section) != r2_lock.get(section):
            raise RuntimeError(f"R3 must inherit {section} unchanged from the frozen R2 lock")
    if lock["run"].get("seed") != 2026102001 or lock["run"].get("optimizer_steps") != 0:
        raise RuntimeError("seed/optimizer contract changed")
    if lock["run"].get("plant_dt_s") != 0.001 or lock["run"].get("position_event_hz") != 100 or lock["run"].get("duration_s") != 20:
        raise RuntimeError("frozen clocks/duration changed")

    for entry in lock["runtimeFiles"]:
        check_hash(entry["path"], entry["sha256"], f"upstream runtime {Path(entry['path']).name}")
    for entry in lock["plantFiles"]:
        check_hash(entry["path"], entry["sha256"], f"Plant source {entry['name']}")
    for key in ("model_binding",):
        item = lock[key]
        check_hash(item["path"], item["sha256"], key)
    for key, path_key, hash_key in (
        ("model MAT", "mat_path", "mat_sha256"),
    ):
        check_hash(lock["model"][path_key], lock["model"][hash_key], key)
    check_hash(lock["normalizer"]["npz_path"], lock["normalizer"]["npz_file_sha256"], "normalizer NPZ")
    check_hash(lock["normalizer"]["train_only_report_path"], lock["normalizer"]["train_only_report_sha256"], "normalizer report")
    check_hash(lock["scene_list"]["path"], lock["scene_list"]["sha256"], "scene list")
    check_hash(lock["scene_payload_identity"]["path"], lock["scene_payload_identity"]["sha256"], "scene payload evidence")
    check_hash(lock["reuse_manifest"]["path"], lock["reuse_manifest"]["sha256"], "R2 ON/B manifest")
    check_hash(lock["scoring_helper"]["path"], lock["scoring_helper"]["sha256"], "raw scanner")

    for entry in lock["localRuntimeFiles"]:
        check_hash(entry["path"], entry["sha256"], f"local R3 runtime {entry['name']}")
        if entry["name"] != "run_dl1018_closed_loop.m":
            if entry["sha256"].lower() != entry["upstream_sha256"].lower():
                raise RuntimeError(f"unexpected local source change outside the R3 runner: {entry['name']}")
        if Path(entry["path"]).parent.resolve() != (HERE / "runtime").resolve():
            raise RuntimeError(f"local runtime file escaped the R3 runtime directory: {entry['path']}")
    for entry in lock["setupFiles"]:
        check_hash(entry["path"], entry["sha256"], f"R3 package source {entry['name']}")
        if Path(entry["path"]).parent.resolve() != HERE.resolve():
            raise RuntimeError(f"R3 setup source escaped its isolated directory: {entry['path']}")

    # The two R2 rescore tables may contain DEV and VAL only; never resolve TEST rows/paths.
    rescore_rows: dict[str, list[dict[str, str]]] = {}
    for entry in lock["rescores"]:
        check_hash(entry["path"], entry["sha256"], f"{entry['role']} rescore")
        rows = read_csv(Path(entry["path"]))
        if any(row.get("split", "").upper() not in {"DEV", "VAL"} for row in rows):
            raise RuntimeError(f"{entry['role']} rescore manifest contains a split outside DEV/VAL")
        if any(re.search(r"(^|[_/\\-])TEST([_/\\-]|$)", " ".join(row.values()), re.I) for row in rows):
            raise RuntimeError(f"{entry['role']} rescore table contains a TEST path or ID")
        rescore_rows[entry["role"]] = rows

    scene_rows = read_csv(Path(lock["scene_list"]["path"]))
    if len(scene_rows) != 12 or tuple(row["scene_id"] for row in scene_rows) != EXPECTED_IDS:
        raise RuntimeError("scene-list file is not the exact frozen order")
    evidence = read_csv(Path(lock["scene_payload_identity"]["path"]))
    evidence_by_id = {row["scene_id"]: row for row in evidence}
    if len(evidence_by_id) != 12 or set(evidence_by_id) != set(EXPECTED_IDS):
        raise RuntimeError("scene identity evidence is not exactly 12 VAL rows")

    manifest = read_csv(Path(lock["reuse_manifest"]["path"]))
    if len(manifest) != 24 or {row.get("split") for row in manifest} != {"VAL"}:
        raise RuntimeError("R2 reused ON/B manifest must have exactly 24 VAL rows")
    by_pair: dict[tuple[str, str], dict[str, str]] = {}
    for row in manifest:
        key = (row.get("scene_id", ""), row.get("role", ""))
        if key in by_pair or key[0] not in EXPECTED_IDS or key[1] not in {"ON_CANDIDATE", "B_BASELINE"}:
            raise RuntimeError(f"unexpected/duplicate R2 ON/B pair: {key}")
        by_pair[key] = row
        check_hash(row["raw_path"], row["raw_sha256"], f"R2 {key[1]} raw {key[0]}")
    if len(by_pair) != 24:
        raise RuntimeError("R2 ON/B raw manifest is incomplete")
    if set(rescore_rows) != {"ON_CANDIDATE", "B_BASELINE"}:
        raise RuntimeError("R2 rescore roles differ from frozen lock")
    for scene_id in EXPECTED_IDS:
        proof = evidence_by_id[scene_id]
        if (proof["status"] != "IDENTICAL" or int(proof["physical_field_count"]) != 14
                or int(proof["time_samples"]) != 20001 or float(proof["max_abs_physical_scene_diff"]) != 0.0):
            raise RuntimeError(f"R2 ON/B physical scene evidence failed: {scene_id}")
        for role, proof_key in (("ON_CANDIDATE", "on_raw_sha256"), ("B_BASELINE", "b_raw_sha256")):
            row = by_pair[(scene_id, role)]
            if row["raw_sha256"].lower() != proof[proof_key].lower():
                raise RuntimeError(f"R2 raw SHA differs from physical evidence: {scene_id} {role}")
            matches = [item for item in rescore_rows[role] if item.get("scene_id") == scene_id]
            if len(matches) != 1:
                raise RuntimeError(f"expected exactly one R2 {role} rescore row for {scene_id}")
            rescore = matches[0]
            if role == "ON_CANDIDATE":
                checks = (rescore.get("raw_path") == row["raw_path"], rescore.get("raw_sha256_expected", "").lower() == row["raw_sha256"].lower())
            else:
                checks = (rescore.get("resolved_raw_path") == row["raw_path"], rescore.get("resolved_raw_sha256_expected", "").lower() == row["raw_sha256"].lower())
            if not all(checks):
                raise RuntimeError(f"R2 {role} rescore/raw identity mismatch: {scene_id}")

    off_rows = lock["round2_off_raws"]
    if len(off_rows) != 12 or tuple(row["scene_id"] for row in off_rows) != EXPECTED_IDS:
        raise RuntimeError("R2 OFF raw evidence is not the exact ordered 12 VAL rows")
    for row in off_rows:
        if row["split"] != "VAL" or row["band"] != lock["scenes"][EXPECTED_IDS.index(row["scene_id"])]["band"]:
            raise RuntimeError(f"R2 OFF scene split/band mismatch: {row['scene_id']}")
        check_hash(row["raw_path"], row["raw_sha256"], f"R2 OFF raw {row['scene_id']}")
        check_hash(row["status_path"], row["status_sha256"], f"R2 OFF status {row['scene_id']}")
        check_hash(row["run_start_path"], row["run_start_sha256"], f"R2 OFF run_start {row['scene_id']}")
        status = json.loads(Path(row["status_path"]).read_text(encoding="utf-8-sig"))
        if (status.get("scene_id") != row["scene_id"] or status.get("status") != "STABLE"
                or status.get("pcf_enabled") is not False or status.get("update_enabled") is not True
                or status.get("head_type") != "FEATURE" or status.get("frozen_inputs_sha256") != upstream["lock_sha256"]
                or status.get("raw_sha256", "").lower() != row["raw_sha256"].lower()
                or status.get("run_start_sha256", "").lower() != row["run_start_sha256"].lower()):
            raise RuntimeError(f"R2 OFF run_status identity failed: {row['scene_id']}")

    return {"verified_scene_count": 12, "verified_reused_on_b_raw_count": 24,
            "verified_r2_off_raw_count": 12, "verified_local_runtime_count": len(lock["localRuntimeFiles"]),
            "verified_r3_setup_count": len(lock["setupFiles"]), "test_access": False}


def matlab_array(log: h5py.Group, name: str) -> np.ndarray:
    if name not in log:
        raise RuntimeError(f"candidate raw missing log/{name}")
    value = np.asarray(log[name])
    if value.dtype.kind in "iu" and log[name].attrs.get("MATLAB_class", b"") == b"char":
        return np.asarray("".join(chr(int(x)) for x in value.reshape(-1) if x))
    return value.T if value.ndim >= 2 else value


def verify_candidate(lock: dict[str, object], scene_id: str) -> dict[str, object]:
    if scene_id not in EXPECTED_IDS:
        raise RuntimeError(f"candidate scene is not in frozen VAL list: {scene_id}")
    scene = lock["scenes"][EXPECTED_IDS.index(scene_id)]
    attempt = HERE / "runs" / scene_id / "attempt_01"
    raw_path, status_path, start_path = attempt / "raw_run.mat", attempt / "run_status.json", attempt / "run_start.mat"
    raw_sha, status_sha, start_sha = (identity(raw_path)[0], identity(status_path)[0], identity(start_path)[0])
    status = json.loads(status_path.read_text(encoding="utf-8-sig"))
    if status.get("raw_sha256", "").lower() != raw_sha.lower() or status.get("run_start_sha256", "").lower() != start_sha.lower():
        raise RuntimeError(f"R3 status does not bind raw/run_start: {scene_id}")
    required = {
        "scene_id": scene_id, "frozen_inputs_sha256": sha256(LOCK_PATH),
        "model_mat_sha256": lock["model"]["mat_sha256"], "model_binding_sha256": lock["model_binding"]["sha256"],
        "normalizer_npz_sha256": lock["normalizer"]["npz_file_sha256"],
        "normalizer_arrays_identity_sha256": lock["normalizer"]["actual_runner_arrays_identity_sha256"],
        "W0_output_W_sha256": lock["model"]["w0_output_W_double_f_order_sha256"],
        "scene_payload_identity_csv_sha256": lock["scene_payload_identity"]["sha256"],
        "status": "STABLE", "head_type": "FEATURE", "pcf_enabled": True, "update_enabled": True,
        "eta_mask": [1, 1, 0], "last_transition": 20000,
    }
    for key, expected in required.items():
        if status.get(key) != expected:
            raise RuntimeError(f"R3 status field {key} differs for {scene_id}")
    if int(status.get("update_event_count", 0)) <= 0 or int(status.get("eta_event_count", 0)) != int(status.get("update_event_count", -1)):
        raise RuntimeError(f"R3 update/eta event count is missing or incomplete: {scene_id}")
    if (float(status.get("max_eta_mask_value_error_unitless", np.inf)) > TOL
            or float(status.get("max_eta_mask_identity_error_mps", np.inf)) > TOL
            or float(status.get("max_surface_coord_identity_error_mps", np.inf)) > TOL):
        raise RuntimeError(f"R3 eta mask/surface identity tolerance failed: {scene_id}")
    on_row = next(r for r in read_csv(Path(lock["reuse_manifest"]["path"])) if r["scene_id"] == scene_id and r["role"] == "ON_CANDIDATE")
    b_row = next(r for r in read_csv(Path(lock["reuse_manifest"]["path"])) if r["scene_id"] == scene_id and r["role"] == "B_BASELINE")
    off_row = next(r for r in lock["round2_off_raws"] if r["scene_id"] == scene_id)
    input_identity = status.get("input_identity", {})
    for key, value in (("on_raw_sha256", on_row["raw_sha256"]), ("b_raw_sha256", b_row["raw_sha256"]),
                       ("off_raw_sha256", off_row["raw_sha256"]), ("round2_input_lock_sha256", lock["upstream_round2"]["lock_sha256"])):
        if input_identity.get(key) != value:
            raise RuntimeError(f"R3 input_identity {key} mismatch for {scene_id}")

    with h5py.File(raw_path, "r") as raw:
        log = raw["log"]
        surface = np.asarray(matlab_array(log, "stage1_position_pcf_event_s_original_mps"), dtype=float)
        eta_before = np.asarray(matlab_array(log, "stage1_position_pcf_event_eta_before_mps"), dtype=float)
        eta_eff = np.asarray(matlab_array(log, "stage1_position_pcf_event_eta_effective_mps"), dtype=float)
        mask = np.asarray(matlab_array(log, "stage1_position_pcf_event_eta_mask"), dtype=float)
        s_coord = np.asarray(matlab_array(log, "stage1_position_pcf_event_s_coord_mps"), dtype=float)
        s_eff = np.asarray(matlab_array(log, "stage1_position_pcf_event_s_coord_eff_mps"), dtype=float)
        w_before = np.asarray(matlab_array(log, "stage1_position_event_weight_before_33x3"), dtype=float)
        w_after = np.asarray(matlab_array(log, "stage1_position_event_weight_after_33x3"), dtype=float)
    n = int(status["update_event_count"])
    if surface.ndim != 2 or surface.shape != (n, 3) or eta_before.shape != surface.shape or eta_eff.shape != surface.shape or mask.shape != surface.shape or s_coord.shape != surface.shape or s_eff.shape != surface.shape:
        raise RuntimeError(f"R3 event signal shapes are incomplete for {scene_id}")
    if w_before.shape != (33, 3, n) or w_after.shape != w_before.shape:
        raise RuntimeError(f"R3 event W-before/W-after must be 33x3xN for {scene_id}: {w_before.shape}")
    arrays = (surface, eta_before, eta_eff, mask, s_coord, s_eff, w_before, w_after)
    if not all(np.isfinite(array).all() for array in arrays):
        raise RuntimeError(f"R3 event log has nonfinite values: {scene_id}")
    expected_mask = np.tile(np.array([1.0, 1.0, 0.0]), (n, 1))
    err_mask = float(np.max(np.abs(mask - expected_mask)))
    err_eta = float(np.max(np.abs(eta_eff - eta_before * expected_mask)))
    err_coord = float(np.max(np.abs(s_coord - (surface - eta_eff))))
    limits = np.array([7.0, 8.0, 10.0])
    err_clip = float(np.max(np.abs(s_eff - np.clip(s_coord, -limits, limits))))
    delta = float(np.max(np.abs(w_after - w_before)))
    if err_mask > TOL or err_eta > TOL or err_coord > TOL or err_clip > TOL or delta <= float(lock["run"]["weight_delta_threshold_unitless"]):
        raise RuntimeError(f"R3 event equation/update checks failed for {scene_id}: mask={err_mask}, eta={err_eta}, coord={err_coord}, clip={err_clip}, dW={delta}")
    if identity(raw_path)[0] != raw_sha or identity(status_path)[0] != status_sha:
        raise RuntimeError(f"R3 raw/status changed during event verification: {scene_id}")
    return {"scene_id": scene_id, "status_sha256": status_sha, "raw_sha256": raw_sha,
            "update_event_count": n, "max_eta_mask_error_unitless": err_mask,
            "max_eta_effective_error_mps": err_eta,
            "max_surface_coord_error_mps": err_coord, "max_clip_error_mps": err_clip,
            "max_weight_delta_unitless": delta, "identity_status": "PASS"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs-only", action="store_true", help="verify frozen VAL inputs without candidate raws")
    parser.add_argument("--candidate", action="store_true", help="also verify present R3 attempts in all 12 frozen scenes")
    parser.add_argument("--report", type=Path, help="optional R3-local JSON report path")
    args = parser.parse_args()
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8-sig"))
    report: dict[str, object] = {"schema": "ROUND3_IDENTITY_VERIFY_V1", "frozen_inputs_sha256": sha256(LOCK_PATH),
                                **verify_inputs(lock), "candidate_runs": []}
    if args.candidate:
        report["candidate_runs"] = [verify_candidate(lock, scene_id) for scene_id in EXPECTED_IDS]
    if args.report:
        target = args.report.resolve()
        if HERE.resolve() not in target.parents:
            raise RuntimeError("verification report must stay inside the R3 directory")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ROUND3_IDENTITY_VERIFY_FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
