"""Read the fixed, audited B24/C5-24 C* training pair without touching TEST."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import h5py
import numpy as np


TASKBOOK = "reports/attitude_cm18_datarepair_20261024/ROOT_B24_C524_TRAINING_TASKBOOK_v1_ZH.md"
TASKBOOK_SHA256 = "67db01666cded8dcc901ba29b335e64fda8c13c4bc50106e3184845242f66d2e"
C5_TASKBOOK = "reports/attitude_cm18_datarepair_20261024/ROOT_C5_MATCHED_TRAIN24_PROTOCOL_TASKBOOK_v1.json"
C5_TASKBOOK_SHA256 = "88d7312087025a331dd532410b0ef31ed2dcb7dd3175239ad1d47bc68dd65f0b"
B_DATASET = "reports/attitude_cm18_datarepair_20261024/cstar_all816_v1/CSTAR_RELABEL_ALL816_v1.json"
B_DATASET_SHA256 = "421298399aacf2d7f82031f2bdecc39eacacc28196c7b872b925866655d211a6"
B_READER = "experiments/attitude_cm18_datarepair_20261024/read_cstar_split_v1.py"
B_READER_SHA256 = "ced4251719f986d762f29ccced04fb80208a28e7aed1e2fe12d3b504955a4096"
C5_EXPORTER = "experiments/attitude_position_context_probe_20261024/c5_matched_train24_v1/export_c5_matched_train24_scene_v1.m"
C5_EXPORTER_SHA256 = "8b77f32b80e82291c3d1ab4ce0bc60f5719c2b97801094a52dc275049fb54861"
C5_AUDIT_BASE = "reports/attitude_position_context_probe_20261024/c5_matched_train24_v1/event_exports_v1"
C5_CSTAR_BATCH_AUDIT = "reports/attitude_position_context_probe_20261024/c5_matched_train24_v1/ROOT_TRAIN24_CSTAR_BATCH_NUMPY_AUDIT_v1.json"
C5_CAUSAL_INPUT_AUDIT = "reports/attitude_position_context_probe_20261024/c5_matched_train24_v1/ROOT_TRAIN24_CAUSAL_INPUT_AUDIT_v1.json"
N_EVENTS = 1999
SAMPLE_ORDINALS = np.arange(0, 1996, 5, dtype=np.int64)
PLANT_INDEX = np.arange(11, 20000, 10, dtype=np.int64)
EVENT_TIME = (PLANT_INDEX - 1).astype(np.float64) * 0.001
DMAX = np.asarray([45.0, 45.0, 4.7124], dtype=np.float64)
BETA_RISE_S = 2.2


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _repo_path(root: Path, value: str) -> Path:
    base = root.resolve(strict=True)
    path = (base / value).resolve(strict=True)
    try:
        path.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"path escapes repository: {value}") from exc
    return path


def _same_path(root: Path, a: str, b: str) -> bool:
    def resolve(value: str) -> Path:
        candidate = Path(value)
        return (candidate if candidate.is_absolute() else root / candidate).resolve(strict=False)
    return resolve(a).as_posix().casefold() == resolve(b).as_posix().casefold()


def _same_source_path(root: Path, a: str, b: str) -> bool:
    def resolve(value: str) -> Path:
        candidate = Path(value)
        return (candidate if candidate.is_absolute() else root / candidate).resolve(strict=False)
    return resolve(a).as_posix().casefold() == resolve(b).as_posix().casefold()


def _pin(root: Path, entry: Any, expected_path: str, expected_sha: str, label: str) -> Path:
    if not isinstance(entry, dict) or entry.get("path") != expected_path:
        raise ValueError(f"release {label} path mismatch")
    if str(entry.get("sha256", "")).lower() != expected_sha:
        raise ValueError(f"release {label} SHA mismatch")
    path = _repo_path(root, expected_path)
    if sha256(path) != expected_sha:
        raise ValueError(f"actual {label} SHA mismatch")
    return path


def _vector(mat: h5py.Group, key: str, dtype: Any) -> np.ndarray:
    if key not in mat:
        raise ValueError(f"C5 cache lacks events/{key}")
    raw = np.asarray(mat[key])
    value = np.asarray(raw, dtype=dtype).reshape(-1)
    if value.shape != (N_EVENTS,) or not np.isfinite(value).all():
        raise ValueError(f"C5 events/{key} must contain {N_EVENTS} finite values")
    if np.issubdtype(np.dtype(dtype), np.integer) and not np.array_equal(raw.reshape(-1), value):
        raise ValueError(f"C5 events/{key} must contain exact integer values")
    return value


def _matrix(mat: h5py.Group, key: str, width: int) -> np.ndarray:
    if key not in mat:
        raise ValueError(f"C5 cache lacks events/{key}")
    stored = np.asarray(mat[key], dtype=np.float64)
    value = stored.T
    if value.shape != (N_EVENTS, width) or not np.isfinite(value).all():
        raise ValueError(f"C5 events/{key} has wrong MATLAB/HDF5 orientation or non-finite values")
    return value


def _fixed_scene_ids(taskbook: dict[str, Any]) -> list[str]:
    rows = taskbook.get("scene_rows")
    if not isinstance(rows, list) or len(rows) != 24:
        raise ValueError("C5 protocol taskbook must contain 24 ordered scenes")
    ids = [row.get("canonical_scene_id") for row in rows]
    expected = {
        f"DL1018_TRAIN_{task}_C{morph}_W{wind}"
        for task in ("T1", "T2", "T3")
        for morph in ("00", "15")
        for wind in ("00", "09", "12", "15")
    }
    if len(set(ids)) != 24 or set(ids) != expected:
        raise ValueError("C5 taskbook IDs do not equal the fixed T1/T2/T3 x C00/C15 x W00/W09/W12/W15 design")
    return ids


def _verify_release_files(root: Path, release: dict[str, Any]) -> tuple[dict[str, Any], dict[str, dict]]:
    if release.get("schema") != "CM18_B24_C524_TRAINING_RELEASE_V1":
        raise ValueError("unexpected paired training release schema")
    _pin(root, release.get("taskbook"), TASKBOOK, TASKBOOK_SHA256, "taskbook")
    _pin(root, release.get("c5_taskbook"), C5_TASKBOOK, C5_TASKBOOK_SHA256, "C5 protocol taskbook")
    _pin(root, release.get("b_dataset_manifest"), B_DATASET, B_DATASET_SHA256, "B C* dataset")
    c5_taskbook = _json(_repo_path(root, C5_TASKBOOK))
    ids = _fixed_scene_ids(c5_taskbook)

    # Each global independent audit is pinned as a whole and must bind its current source.
    global_audits = release.get("c5_global_audits")
    if not isinstance(global_audits, dict):
        raise ValueError("release lacks the two global C5 TRAIN24 audits")
    audit_sources = {
        "cstar_batch": (C5_CSTAR_BATCH_AUDIT, "ROOT_TRAIN24_CSTAR_BATCH_NUMPY_AUDIT_V1", "root_audit_train24_cstar_batch_v1.py", "audit_source_sha256"),
        "causal_inputs": (C5_CAUSAL_INPUT_AUDIT, "ROOT_TRAIN24_CAUSAL_INPUT_AUDIT_V1", "root_audit_train24_causal_inputs_v1.py", "source_sha256"),
    }
    global_rows: dict[str, dict] = {}
    for key, (rel, schema, source_file, source_key) in audit_sources.items():
        item = global_audits.get(key)
        if not isinstance(item, dict) or item.get("path") != rel:
            raise ValueError(f"release global audit path mismatch: {key}")
        audit_path = _repo_path(root, rel)
        if sha256(audit_path) != str(item.get("sha256", "")).lower():
            raise ValueError(f"global audit SHA mismatch: {key}")
        audit = _json(audit_path)
        if (audit.get("schema") != schema or audit.get("status") != "PASS"
                or audit.get("scene_count") != 24 or str(audit.get("taskbook_sha256", "")).lower() != C5_TASKBOOK_SHA256
                or audit.get("TEST_accessed") is not False or audit.get("optimizer_steps") != 0
                or audit.get("Plant_calls") != 0):
            raise ValueError(f"global audit is not a complete offline PASS: {key}")
        actual_source_sha = sha256(_repo_path(root, f"reports/attitude_cm18_datarepair_20261024/{source_file}"))
        if str(audit.get(source_key, "")).lower() != actual_source_sha:
            raise ValueError(f"global audit source identity changed: {key}")
        scene_rows = audit.get("scenes")
        if not isinstance(scene_rows, list) or len(scene_rows) != 24:
            raise ValueError(f"global audit does not contain 24 scene rows: {key}")
        by_id = {row.get("scene_id"): row for row in scene_rows if isinstance(row, dict)}
        if len(by_id) != 24 or set(by_id) != set(ids):
            raise ValueError(f"global audit scene set differs: {key}")
        global_rows[key] = by_id

    row_pins = release.get("c5_scene_rows")
    if not isinstance(row_pins, list) or len(row_pins) != 24:
        raise ValueError("release must pin exactly 24 C5 scene audit/cache rows")
    if [row.get("scene_id") for row in row_pins] != ids:
        raise ValueError("release C5 rows must preserve frozen taskbook order")
    prepared: dict[str, dict] = {}
    exporter_path = _repo_path(root, C5_EXPORTER)
    if sha256(exporter_path) != C5_EXPORTER_SHA256:
        raise ValueError("C5 exporter SHA differs from reviewed source")
    for pin in row_pins:
        sid = pin["scene_id"]
        if sid in prepared:
            raise ValueError(f"duplicate C5 release row: {sid}")
        required = ("raw_path", "raw_sha256", "run_start_path", "run_start_sha256",
                    "cache_path", "cache_sha256", "export_audit_path", "export_audit_sha256")
        if any(not isinstance(pin.get(k), str) for k in required):
            raise ValueError(f"malformed C5 scene release identity: {sid}")
        audit_path = _repo_path(root, pin["export_audit_path"])
        if sha256(audit_path) != pin["export_audit_sha256"].lower():
            raise ValueError(f"per-scene C5 export audit SHA mismatch: {sid}")
        audit = _json(audit_path)
        ident = audit.get("identity", {})
        if (audit.get("schema") != "C5_MATCHED_TRAIN24_EVENT_EXPORT_AUDIT_V1"
                or audit.get("status") != "PASS" or audit.get("canonical_scene_id") != sid
                or audit.get("event_count") != N_EVENTS or audit.get("transition_count") != 20000
                or audit.get("state_sample_count") != 20001 or audit.get("run_engine_status") != "STABLE"
                or audit.get("safety_stop_reason") != "" or audit.get("source_scene_exact_copy") is not True
                or audit.get("exporter_plant_calls") != 0 or audit.get("exporter_engine_calls") != 0
                or audit.get("optimizer_steps") != 0 or audit.get("TEST_accessed") is not False):
            raise ValueError(f"per-scene C5 export audit is not a clean stable PASS: {sid}")
        checks = (
            ("raw_path", ident.get("flight_raw_path"), "raw_sha256", ident.get("flight_raw_sha256")),
            ("run_start_path", ident.get("flight_run_start_path"), "run_start_sha256", ident.get("flight_run_start_sha256")),
            ("cache_path", audit.get("cache_path"), "cache_sha256", audit.get("cache_sha256")),
        )
        for path_key, actual_path, sha_key, actual_sha in checks:
            if not _same_path(root, pin[path_key], str(actual_path)) or pin[sha_key].lower() != str(actual_sha).lower():
                raise ValueError(f"release/per-scene identity differs for {sid}: {path_key}")
            target = _repo_path(root, pin[path_key])
            if sha256(target) != pin[sha_key].lower():
                raise ValueError(f"actual file SHA mismatch for {sid}: {path_key}")
        task_row = next(row for row in c5_taskbook["scene_rows"] if row["canonical_scene_id"] == sid)
        if (not _same_source_path(root, str(ident.get("source_raw_path", "")), task_row["raw_path"])
                or not _same_source_path(root, str(ident.get("source_run_start_path", "")), task_row["run_start_path"])
                or ident.get("source_raw_sha256", "").lower() != task_row["raw_sha256"].lower()
                or ident.get("source_run_start_sha256", "").lower() != task_row["run_start_sha256"].lower()
                or ident.get("taskbook_sha256", "").lower() != C5_TASKBOOK_SHA256
                or ident.get("source_manifest_sha256", "").lower() != "0f86b47d01940e7b556b78a9664470531572809aa6857a59fc77d88a33681ec5"
                or ident.get("exporter_matlab_sha256", "").lower() != C5_EXPORTER_SHA256):
            raise ValueError(f"C5 export does not bind the selected source scene: {sid}")
        expected_runtime_id = sid if task_row["source_kind"] == "original_T1_T3_B_scene" else sid + "_ACC_FIX_V1"
        if (ident.get("runtime_scene_id") != expected_runtime_id
                or ident.get("sequence_index") != ids.index(sid) + 1
                or not _same_path(root, ident.get("exporter_matlab_path", ""), str(exporter_path))
                or str(pin["export_audit_path"]).replace("\\", "/") != f"{C5_AUDIT_BASE}/{sid}/{sid}_CSTAR_AUDIT_v1.json"):
            raise ValueError(f"C5 exporter/audit path identity mismatch: {sid}")
        if "run_status_path" in ident:
            status_path = _repo_path(root, ident["run_status_path"])
            if sha256(status_path) != ident.get("run_status_sha256", "").lower():
                raise ValueError(f"C5 terminal status SHA mismatch: {sid}")
            status = _json(status_path)
            if status.get("status") != "RUN_COMPLETE_STABLE" or status.get("engine_status") != "STABLE":
                raise ValueError(f"C5 run status is not terminal stable: {sid}")

        cstar = global_rows["cstar_batch"][sid]
        causal = global_rows["causal_inputs"][sid]
        if (cstar.get("event_cache_sha256", "").lower() != pin["cache_sha256"].lower()
                or cstar.get("raw_sha256", "").lower() != pin["raw_sha256"].lower()
                or cstar.get("exporter_sha256", "").lower() != C5_EXPORTER_SHA256
                or causal.get("status") != "PASS" or causal.get("covered_columns") != 15
                or causal.get("cache_sha256", "").lower() != pin["cache_sha256"].lower()
                or causal.get("raw_sha256", "").lower() != pin["raw_sha256"].lower()):
            raise ValueError(f"C5 scene does not match both global audits: {sid}")
        prepared[sid] = {"pin": pin, "audit": audit, "identity": ident}
    return c5_taskbook, prepared


def _read_c5_scene(root: Path, sid: str, record: dict[str, Any]) -> dict[str, Any]:
    cache = _repo_path(root, record["pin"]["cache_path"])
    with h5py.File(cache, "r") as stream:
        if "events" not in stream:
            raise ValueError(f"C5 event cache lacks events struct: {sid}")
        events = stream["events"]
        x = _matrix(events, "X18", 18)
        target = _matrix(events, "target_raw_output_rad_s2", 3)
        cstar = _matrix(events, "target_applied_acceleration_rad_s2", 3)
        target_after_clip_beta = _matrix(events, "target_after_clip_beta_rad_s2", 3)
        gflat = _matrix(events, "G_row_major", 9)
        e0 = _matrix(events, "E0_rad_s2", 3)
        beta = _vector(events, "beta", np.float64)
        event_index = _vector(events, "event_index", np.int64)
        plant = _vector(events, "plant_index", np.int64)
        event_time = _vector(events, "event_time_s", np.float64)
        phase = _vector(events, "phase_code", np.int64)
        if not all(key in events for key in ("schema", "canonical_scene_id", "runtime_scene_id", "split")):
            raise ValueError(f"C5 event cache lacks schema/identity fields: {sid}")
        text = lambda key: "".join(chr(int(v)) for v in np.asarray(events[key]).reshape(-1) if int(v))
        if (text("schema") != "CM18_C5_MATCHED_TRAIN24_CSTAR_EVENT_CACHE_V1"
                or text("canonical_scene_id") != sid
                or text("runtime_scene_id") != record["identity"]["runtime_scene_id"]
                or text("split") != "TRAIN"):
            raise ValueError(f"C5 event cache embedded identity mismatch: {sid}")
    if not np.array_equal(event_index, np.arange(1, N_EVENTS + 1)) or not np.array_equal(plant, PLANT_INDEX):
        raise ValueError(f"C5 event ordinals or Plant indices differ from the frozen clock: {sid}")
    if np.max(np.abs(event_time - EVENT_TIME)) > 1e-12 or np.any((phase < 0) | (phase > 5)):
        raise ValueError(f"C5 event time or phase code is invalid: {sid}")
    beta_expected = np.minimum(plant.astype(np.float64) * 0.001 / BETA_RISE_S, 1.0)
    if np.any(beta <= 0.0) or np.max(np.abs(beta - beta_expected)) > 1e-12:
        raise ValueError(f"C5 beta does not follow the frozen clock: {sid}")
    g = gflat.reshape(N_EVENTS, 3, 3)
    if np.max(np.abs(e0 - np.einsum("nij,nj->ni", g, cstar))) > 1e-8:
        raise ValueError(f"C5 E0-G*cStar physical residual gate failed: {sid}")
    expected_raw = cstar / beta[:, None]
    if np.max(np.abs(target - expected_raw)) > 1e-9:
        raise ValueError(f"C5 direct raw target is not cStar/beta: {sid}")
    expected_applied = beta[:, None] * np.clip(target, -DMAX, DMAX)
    if np.max(np.abs(expected_applied - target_after_clip_beta)) > 1e-9:
        raise ValueError(f"C5 clipped target arithmetic mismatch: {sid}")
    return {"scene_id": sid, "split": "TRAIN", "X18": x, "target_raw_output_rad_s2": target,
            "target_applied_acceleration_rad_s2": cstar, "event_time_s": event_time,
            "phase_code": phase, "plant_index": plant, "G_3x3": g, "E0_rad_s2": e0,
            "E0_provenance": "stored in audited C5 cache"}


def load_pair(root: Path, release: dict[str, Any], b_reader: Any) -> dict[str, Any]:
    """Load the two fixed 24-scene TRAIN branches in taskbook order."""
    root = Path(root).resolve(strict=True)
    task_path = _repo_path(root, TASKBOOK)
    if sha256(task_path) != TASKBOOK_SHA256:
        raise ValueError("B24/C5-24 taskbook SHA mismatch")
    task = task_path.read_text(encoding="utf-8").splitlines()
    if not task or not task[0].startswith("# B24 / C5-24 配对训练诊断任务书 v1"):
        raise ValueError("unexpected B24/C5-24 taskbook header")
    _, c5 = _verify_release_files(root, release)
    c5_task = _json(_repo_path(root, C5_TASKBOOK))
    ids = _fixed_scene_ids(c5_task)

    dataset_path = _repo_path(root, B_DATASET)
    if sha256(dataset_path) != B_DATASET_SHA256:
        raise ValueError("B24 C* dataset manifest SHA mismatch")
    manifest = _json(dataset_path)
    if (manifest.get("schema") != "CM18_A1T_CSTAR_RELABEL_ALL816_V1" or manifest.get("status") != "PASS"
            or manifest.get("training_eligible") is not True or manifest.get("TEST_accessed") is not False
            or manifest.get("scene_count") != 816 or manifest.get("qualified_count") != 816
            or manifest.get("failed_count") != 0 or manifest.get("split_counts") != {"TRAIN": 768, "VAL": 48}):
        raise ValueError("B24 C* label dataset is not the complete qualified PASS ALL816 dataset")
    scope = manifest.get("scope", {})
    if (scope.get("plant_calls") != 0 or scope.get("engine_calls") != 0
            or scope.get("training_steps") != 0 or scope.get("optimizer_steps") != 0
            or scope.get("TEST_accessed") is not False):
        raise ValueError("B24 relabel scope is not offline-only")
    if manifest.get("source_manifest_path") != "reports/attitude_cm18_datarepair_20261024/B_REF_REPAIRED_SOURCE_MANIFEST_v1.json" or manifest.get("source_manifest_sha256", "").lower() != "0f86b47d01940e7b556b78a9664470531572809aa6857a59fc77d88a33681ec5":
        raise ValueError("B24 repaired source-manifest lineage mismatch")
    rows = manifest.get("rows")
    if not isinstance(rows, list) or len(rows) != 816:
        raise ValueError("B24 dataset rows are incomplete")
    source_rows, base_rows = b_reader._verify_input_manifests(root, manifest)
    row_map = {row.get("scene_id"): i for i, row in enumerate(rows)}
    train_ids = [row["scene_id"] for row in rows if row.get("split") == "TRAIN"]
    if len(row_map) != 816 or len(train_ids) != 768 or not set(ids).issubset(set(train_ids)):
        raise ValueError("the 24 C5 taskbook scenes are not all qualified B TRAIN rows")
    dmax = np.asarray(manifest.get("dmax_rad_s2"), dtype=np.float64)
    beta_rise = float(manifest.get("beta_rise_time_s", np.nan))
    if not np.array_equal(dmax, DMAX) or beta_rise != BETA_RISE_S:
        raise ValueError("B24 clip/beta constants differ from the frozen paired taskbook")
    b_scenes = []
    for sid in ids:
        ordinal = row_map[sid]
        row = rows[ordinal]
        if row.get("status") != "PASS" or row.get("qualified") is not True or row.get("split") != "TRAIN":
            raise ValueError(f"B scene is not a qualified TRAIN row: {sid}")
        base_row = base_rows[ordinal]
        scene = b_reader._read_scene(root, row, source_rows[ordinal], base_row, dmax, beta_rise)
        cache_path = _repo_path(root, row["cache_path"])
        from scipy.io import loadmat
        gmat = loadmat(cache_path, squeeze_me=False, struct_as_record=False,
                       variable_names=("G_column_major", "G_layout"))
        layout = "".join(np.asarray(gmat["G_layout"]).reshape(-1).astype(str)).lower()
        if "column-major" not in layout:
            raise ValueError(f"B cache G layout is not explicitly column-major: {sid}")
        flat = np.asarray(gmat["G_column_major"], dtype=np.float64)
        if flat.shape != (N_EVENTS, 9) or not np.isfinite(flat).all():
            raise ValueError(f"B G column-major cache shape/finite gate failed: {sid}")
        g = flat.reshape(N_EVENTS, 3, 3).transpose(0, 2, 1)
        cstar = np.asarray(scene["target_applied_acceleration_rad_s2"], dtype=np.float64)
        scene.update({"G_3x3": g, "E0_rad_s2": np.einsum("nij,nj->ni", g, cstar),
                      "E0_provenance": "derived as G*cStar; not stored in B cache"})
        b_scenes.append(scene)

    c5_scenes = [_read_c5_scene(root, sid, c5[sid]) for sid in ids]
    for branch, scenes in (("B24", b_scenes), ("C5_24", c5_scenes)):
        if len(scenes) != 24 or [s["scene_id"] for s in scenes] != ids:
            raise ValueError(f"{branch} scene order/coverage differs from the fixed taskbook")
        for scene in scenes:
            if (scene["X18"].shape != (N_EVENTS, 18)
                    or scene["target_raw_output_rad_s2"].shape != (N_EVENTS, 3)
                    or not np.isfinite(scene["X18"]).all()
                    or not np.isfinite(scene["target_raw_output_rad_s2"]).all()):
                raise ValueError(f"{branch} features/target are malformed: {scene['scene_id']}")
    for b_scene, c5_scene in zip(b_scenes, c5_scenes, strict=True):
        for key in ("plant_index", "phase_code", "event_time_s"):
            b_values = np.asarray(b_scene[key]).reshape(-1)
            c5_values = np.asarray(c5_scene[key]).reshape(-1)
            if not np.array_equal(b_values, c5_values):
                raise ValueError(f"B/C5 {key} differs for matched scene: {b_scene['scene_id']}")
    return {"scene_ids": ids, "B24": b_scenes, "C5_24": c5_scenes,
            "C5_records": c5, "dataset_manifest_sha256": B_DATASET_SHA256,
            "taskbook_sha256": TASKBOOK_SHA256, "c5_taskbook_sha256": C5_TASKBOOK_SHA256}


def sampled_pair(scenes: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray, list[tuple[str, int, int]]]:
    x_rows, y_rows, row_map = [], [], []
    for scene in scenes:
        x = np.asarray(scene["X18"], dtype=np.float64)
        y = np.asarray(scene["target_raw_output_rad_s2"], dtype=np.float64)
        plant = np.asarray(scene["plant_index"], dtype=np.int64).reshape(-1)
        if x.shape != (N_EVENTS, 18) or y.shape != (N_EVENTS, 3) or plant.shape != (N_EVENTS,):
            raise ValueError(f"malformed fit source: {scene['scene_id']}")
        x_rows.append(x[SAMPLE_ORDINALS])
        y_rows.append(y[SAMPLE_ORDINALS])
        row_map.extend((scene["scene_id"], int(i), int(plant[i])) for i in SAMPLE_ORDINALS)
    return np.concatenate(x_rows), np.concatenate(y_rows), row_map


def canonical_row_map_sha(row_map: list[tuple[str, int, int]]) -> str:
    payload = json.dumps(row_map, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def sample_stream_sha(seed: int = 2026102001, steps: int = 60_000, batch_size: int = 512,
                      row_count: int = 9_600) -> str:
    rng = np.random.default_rng(seed)
    digest = hashlib.sha256()
    for _ in range(steps):
        indices = rng.integers(0, row_count, size=batch_size, dtype=np.int64)
        digest.update(np.asarray(indices, dtype="<i8").tobytes(order="C"))
    return digest.hexdigest()
