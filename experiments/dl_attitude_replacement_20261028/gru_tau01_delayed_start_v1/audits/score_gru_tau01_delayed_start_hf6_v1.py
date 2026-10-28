"""Hash-bound HF6 paired screen for delayed-start GRU; uses the frozen FULL72 scorer."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
ROOT = STUDY.parents[2]
TAU_STUDY = ROOT / "experiments" / "dl_attitude_replacement_20261028" / "gru_prediction_tau01_v1"
TAU_SCORE_PATH = TAU_STUDY / "audits" / "GRU_PREDICTION_TAU01_SCORE_final12.json"
PLAN_PATH = HERE / "HF6_CONTINUATION_PLAN_v1.json"
BINDING_PATH = HERE / "HF6_RUN_BINDING_v1.json"
OLD_RELEASE_PATH = HERE / "RELEASE_v1_PRE_HF5.json"
OLD_RELEASE_SHA_PATH = HERE / "RELEASE_v1_PRE_HF5.sha256"
RELEASE_PATH = STUDY / "RELEASE.json"
SOURCE_LOCK_PATH = STUDY / "SOURCE_LOCK_v1.json"
SOURCE_MANIFEST_PATH = STUDY / "SOURCE_HASH_MANIFEST_v1.json"
SCENE_MANIFEST_PATH = STUDY / "SCENE_INPUT_MANIFEST_v1.json"
LOCKED_CFG_PATH = STUDY / "LOCKED_CFG.json"
C5_INPUT_LOCK_PATH = ROOT / "experiments" / "position_axis_coordinate_c5_dev72_20261023" / "C5_DEV72_INPUT_LOCK_v3.json"
OUT_JSON = HERE / "ROOT_HF6_SCORE_v1.json"
OUT_MD = HERE / "ROOT_HF6_SCORE_v1.md"
METRICS = ("Q_m", "task_SO3_rad", "inner_SO3_rad")
SAFETY = (
    "motor_saturation_samples", "generalized_clip_samples", "tilt_limited_samples",
    "attitude_head_projection_samples", "attitude_head_output_saturated_samples",
)
WIN_TOL = 1e-12
METHOD_LABELS = {
    "Delayed_Start_Candidate": "candidate",
    "Tau01": "tau01",
    "Parent_Cosine_GRU": "parent",
    "B": "B",
    "C5": "C5",
}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def readj(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def require(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)


def same_path(a: str | Path, b: str | Path) -> bool:
    return Path(a).resolve() == Path(b).resolve()


def verify_static_bindings():
    plan, binding = readj(PLAN_PATH), readj(BINDING_PATH)
    old_release, new_release = readj(OLD_RELEASE_PATH), readj(RELEASE_PATH)
    source_lock, source_manifest = readj(SOURCE_LOCK_PATH), readj(SOURCE_MANIFEST_PATH)
    scene_manifest, locked_cfg = readj(SCENE_MANIFEST_PATH), readj(LOCKED_CFG_PATH)
    tau_score = readj(TAU_SCORE_PATH)

    require(binding.get("status") == "PASS_HF6_COMPLETE" and binding.get("scene_count") == 6,
            "HF6 run-binding audit is not complete")
    require(plan.get("fixed_hf6_scene_ids") == [r["scene_id"] for r in binding["scene_runs"]],
            "HF6 plan and per-scene run binding order differ")
    require(binding.get("candidate") == new_release.get("candidate") and
            plan.get("candidate") == new_release.get("candidate"), "candidate identity mismatch")
    require(sha(OLD_RELEASE_PATH).lower() == plan["previous_release_sha256"].lower() ==
            binding["release_chain"][0]["release_sha256"].lower(), "prior release hash mismatch")
    require(sha(RELEASE_PATH).lower() == plan["current_release_sha256"].lower() ==
            binding["release_chain"][1]["release_sha256"].lower(), "continuation release hash mismatch")
    release_hash_text = OLD_RELEASE_SHA_PATH.read_text(encoding="utf-8-sig").split()[0]
    require(release_hash_text.lower() == sha(OLD_RELEASE_PATH).lower(), "prior release .sha256 file mismatch")
    require(new_release.get("previous_release_sha256", "").lower() == sha(OLD_RELEASE_PATH).lower(),
            "release chain does not connect to archived prior release")

    for rel, rel_path in ((old_release, OLD_RELEASE_PATH), (new_release, RELEASE_PATH)):
        require(rel.get("status") == "RELEASED" and rel.get("study_id") == "gru_tau01_delayed_start_v1",
                f"invalid release: {rel_path}")
        require(rel.get("source_lock_sha256", "").lower() == sha(SOURCE_LOCK_PATH).lower(),
                f"release source lock mismatch: {rel_path}")
        require(rel.get("source_hash_manifest_sha256", "").lower() == sha(SOURCE_MANIFEST_PATH).lower(),
                f"release source manifest mismatch: {rel_path}")
        require(rel.get("scene_input_manifest_sha256", "").lower() == sha(SCENE_MANIFEST_PATH).lower(),
                f"release scene manifest mismatch: {rel_path}")
        require(rel.get("locked_cfg_sha256", "").lower() == sha(LOCKED_CFG_PATH).lower(),
                f"release locked configuration mismatch: {rel_path}")
        require(rel.get("TEST_read") is False and rel.get("test_data_read") is False and
                rel.get("inertia_reconstruction_enabled") is False, f"release scope violation: {rel_path}")
    require(binding.get("source_lock_sha256", "").lower() == sha(SOURCE_LOCK_PATH).lower(),
            "run-binding source lock mismatch")
    require(locked_cfg.get("c5_input_lock_sha256", "").lower() == sha(C5_INPUT_LOCK_PATH).lower(),
            "C5 input lock hash mismatch")
    require(locked_cfg.get("c5_input_lock_sha256", "").lower() == new_release.get("c5_input_lock_sha256", locked_cfg["c5_input_lock_sha256"]).lower(),
            "release and locked C5 input lock mismatch")
    require(tau_score.get("status") == "COMPLETE_12_SCREEN" and
            tau_score.get("completed_scene_count") == 12 and tau_score.get("TEST_read") is False and
            tau_score.get("test_data_read") is False, "tau01 formal comparison score is invalid")
    require(sha(TAU_SCORE_PATH).lower() == readj(HERE / "ROOT_PILOT_SCORE_v1.json")["frozen_scoring"]["formal_tau01_score_sha256"].lower(),
            "tau01 formal score hash differs from the already reviewed pilot binding")

    tau_metric_path = Path(tau_score["metric_source_path"])
    require(sha(tau_metric_path).lower() == tau_score["metric_source_sha256"].lower(),
            "frozen metric scorer SHA-256 mismatch")
    parent_release = readj(Path(tau_score["parent_release_path"]))
    require(sha(Path(tau_score["parent_release_path"])).lower() == tau_score["parent_release_sha256"].lower(),
            "parent release SHA-256 mismatch")
    parent_manifest = Path(tau_score["parent_release_path"]).parent / "MANIFEST.json"
    require(parent_release.get("manifest_sha256", "").lower() == tau_score["parent_manifest_sha256"].lower(),
            "parent release does not bind the expected manifest")
    require(sha(parent_manifest).lower() == tau_score["parent_manifest_sha256"].lower(),
            "parent manifest SHA-256 mismatch")
    require(tau_score["metric_constants_path"] and
            sha(Path(tau_score["metric_constants_path"])).lower() == tau_score["metric_constants_sha256"].lower(),
            "frozen metric constants SHA-256 mismatch")

    records = {r["scene_id"]: r for r in scene_manifest["records"]}
    tau_rows = {r["scene_id"]: r for r in tau_score["scene_results"]}
    required = set(plan["fixed_hf6_scene_ids"])
    require(required.issubset(records) and required.issubset(tau_rows),
            "HF6 scenes are missing from input or tau01 score manifest")
    require(scene_manifest.get("TEST_read") is False, "scene input manifest indicates TEST access")
    return plan, binding, old_release, new_release, records, tau_rows, tau_score


def validate_official_comparator(method: str, info: dict, sid: str, scene_record: dict):
    raw = Path(info["raw_path"])
    require(raw.is_file() and sha(raw).lower() == info["raw_sha256"].lower(),
            f"{method} raw hash mismatch for {sid}")
    status_path_value = info.get("run_status_path") or info.get("status_path")
    status_hash_value = info.get("run_status_sha256") or info.get("status_sha256")
    require(status_path_value and status_hash_value, f"{method} status binding missing for {sid}")
    status_path = Path(status_path_value)
    require(sha(status_path).lower() == status_hash_value.lower(), f"{method} status file hash mismatch for {sid}")
    status = readj(status_path)
    complete = (status.get("state") == "COMPLETED" or
                status.get("status") == "RUN_COMPLETE_RAW_PENDING_AUDIT")
    stable = status.get("status_value", status.get("log_status", "STABLE")) == "STABLE"
    require(status.get("scene_id") == sid and complete and stable and
            status.get("safety_stop_reason", "") == "",
            f"{method} status is not a stable completed run for {sid}")
    require(status.get("test_data_read", status.get("TEST_accessed", status.get("TEST_read", False))) is False,
            f"{method} run reports TEST access for {sid}")
    require(same_path(status.get("raw_path", ""), raw) and
            status.get("raw_sha256", "").lower() == info["raw_sha256"].lower(),
            f"{method} status-to-raw binding mismatch for {sid}")
    if method in ("B", "C5"):
        require(status.get("transitions") == 20000 and status.get("state_samples") == 20001,
                f"{method} status sample count mismatch for {sid}")
    if method == "B":
        require(same_path(raw, scene_record["b_raw_path"]) and info["raw_sha256"].lower() == scene_record["b_raw_sha256"].lower() and
                same_path(status_path, scene_record["b_status_path"]) and status_hash_value.lower() == scene_record["b_status_sha256"].lower(),
                f"B input manifest binding mismatch for {sid}")
    elif method == "C5":
        require(same_path(raw, scene_record["c5_raw_path"]) and info["raw_sha256"].lower() == scene_record["c5_raw_sha256"].lower() and
                same_path(status_path, scene_record["c5_status_path"]) and status_hash_value.lower() == scene_record["c5_status_sha256"].lower(),
                f"C5 input manifest binding mismatch for {sid}")
    return raw, status_path


def validate_candidate_scene(sid: str, binding_row: dict, scene_record: dict,
                             old_release: dict, new_release: dict, locked_cfg: dict):
    run_start_path = Path(binding_row["run_start_path"])
    run_status_path = Path(binding_row["run_status_path"])
    raw_path = Path(binding_row["raw_path"])
    start_sha, status_sha, raw_sha = sha(run_start_path), sha(run_status_path), sha(raw_path)
    require(start_sha.lower() == binding_row["run_start_sha256"].lower(), f"run_start hash mismatch {sid}")
    require(status_sha.lower() == binding_row["run_status_sha256"].lower(), f"run_status hash mismatch {sid}")
    require(raw_sha.lower() == binding_row["raw_sha256"].lower(), f"candidate raw hash mismatch {sid}")
    start, status = readj(run_start_path), readj(run_status_path)
    release_sha = binding_row["release_sha256"].lower()
    release_path, release, generation = (
        (OLD_RELEASE_PATH, old_release, 1) if release_sha == sha(OLD_RELEASE_PATH).lower()
        else (RELEASE_PATH, new_release, 2)
    )
    require(sha(release_path).lower() == release_sha, f"wrong release archive bound to {sid}")
    require(sid in release.get("authorized_scenes", []), f"scene not authorized by its bound release: {sid}")
    for obj, name in ((start, "run_start"), (status, "run_status")):
        require(obj.get("scene_id") == sid and obj.get("candidate") == release["candidate"],
                f"{name} identity mismatch for {sid}")
        require(obj.get("release_sha256", "").lower() == release_sha, f"{name} release binding mismatch for {sid}")
        require(obj.get("source_lock_sha256", "").lower() == binding_row["source_lock_sha256"].lower(),
                f"{name} source lock mismatch for {sid}")
        require(obj.get("source_lock_sha256", "").lower() == sha(SOURCE_LOCK_PATH).lower(),
                f"{name} source lock file hash mismatch for {sid}")
        require(obj.get("test_data_read", False) is False, f"{name} reports TEST access for {sid}")
    require(status.get("state") == "COMPLETED" and status.get("status_value") == "STABLE" and
            status.get("Plant_calls") == 1 and status.get("transitions") == 20000 and
            status.get("state_samples") == 20001 and status.get("safety_stop_reason") == "",
            f"candidate run is incomplete or unsafe: {sid}")
    require(Path(status["raw_path"]).resolve() == raw_path.resolve() and
            status.get("raw_sha256", "").lower() == raw_sha.lower(), f"run_status raw binding mismatch {sid}")
    require(start.get("source_hash_manifest_sha256", "").lower() == sha(SOURCE_MANIFEST_PATH).lower() and
            status.get("source_lock_sha256", "").lower() == sha(SOURCE_LOCK_PATH).lower(),
            f"candidate source lock/manifest mismatch {sid}")
    require(start.get("scene_input_manifest_sha256", "").lower() == sha(SCENE_MANIFEST_PATH).lower() and
            start.get("parent_manifest_sha256", "").lower() == new_release["parent_manifest_sha256"].lower(),
            f"candidate scene/parent manifest mismatch {sid}")
    require(start.get("source_split") == scene_record["source_split"] and
            start.get("scene_payload_sha256", "").lower() == scene_record["payload_sha256"].lower() and
            start.get("external_identity_sha256", "").lower() == scene_record["external_identity_sha256"].lower(),
            f"candidate scene payload binding mismatch {sid}")
    require(start.get("b_raw_sha256", "").lower() == scene_record["b_raw_sha256"].lower() and
            start.get("c5_input_lock_sha256", "").lower() == locked_cfg["c5_input_lock_sha256"].lower() and
            start.get("c5_snapshot_sha256", "").lower() == locked_cfg["c5_snapshot_sha256"].lower(),
            f"candidate B/C5 input-lock binding mismatch {sid}")
    require(start.get("gru_model_sha256", "").lower() == new_release["model_sha256"].lower(),
            f"candidate model binding mismatch {sid}")
    require(binding_row.get("test_data_read") is False and binding_row.get("inertia_reconstruction_enabled") is False,
            f"run-binding scope violation {sid}")
    return {
        "path": raw_path, "sha256": raw_sha, "release_path": release_path,
        "release_sha256": release_sha, "release_generation": generation,
        "run_start_sha256": start_sha, "run_status_sha256": status_sha,
        "source_lock_sha256": status["source_lock_sha256"], "status": status,
    }


def load_scorer(tau_score: dict):
    metric_path = Path(tau_score["metric_source_path"])
    require(sha(metric_path).lower() == tau_score["metric_source_sha256"].lower(),
            "frozen scorer SHA-256 mismatch")
    spec = importlib.util.spec_from_file_location("frozen_full72_score_raw", metric_path)
    require(spec is not None and spec.loader is not None, "cannot load frozen FULL72 scorer")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module, metric_path


def score_scene(sid: str, binding_row: dict, scene_record: dict, tau_row: dict,
                old_release: dict, new_release: dict, locked_cfg: dict,
                scorer, gravity: float, max_tilt: float):
    new = validate_candidate_scene(sid, binding_row, scene_record, old_release, new_release, locked_cfg)
    inputs = {
        "Delayed_Start_Candidate": {"raw_path": str(new["path"]), "raw_sha256": new["sha256"],
                                     "run_status_path": binding_row["run_status_path"],
                                     "run_status_sha256": new["run_status_sha256"],
                                     "release_path": str(new["release_path"]),
                                     "release_sha256": new["release_sha256"],
                                     "release_generation": new["release_generation"]},
    }
    for key in ("B", "C5", "Parent_Cosine_GRU", "Tau01"):
        info = tau_row["methods"]["Candidate" if key == "Tau01" else key]
        raw, status_path = validate_official_comparator(key, info, sid, scene_record)
        inputs[key] = {"raw_path": str(raw), "raw_sha256": info["raw_sha256"],
                       "run_status_path": str(status_path),
                       "run_status_sha256": info.get("run_status_sha256") or info.get("status_sha256"),
                       "binding_source": "tau01 formal final12 paired score"}
    paired = {}
    for method, info in inputs.items():
        m = scorer.score_raw(Path(info["raw_path"]), gravity, max_tilt)
        paired[method] = {
            **{k: float(m[k]) for k in METRICS},
            "safety": m["safety"],
            "axis_phase": m["axis_phase"],
            "raw_path": info["raw_path"],
            "raw_sha256": info["raw_sha256"],
            "run_status_path": info["run_status_path"],
            "run_status_sha256": info["run_status_sha256"],
            **({"release_path": info["release_path"], "release_sha256": info["release_sha256"],
                "release_generation": info["release_generation"]} if method == "Delayed_Start_Candidate" else {}),
        }
    candidate_q = paired["Delayed_Start_Candidate"]["Q_m"]
    if sid == "DL1018_VAL_T3_C01_W14":
        pilot = readj(HERE / "ROOT_PILOT_SCORE_v1.json")
        require(pilot["raw_sha256"].lower() == new["sha256"].lower(), "pilot raw differs from HF6 prior scene")
        for method, pilot_key in (("Delayed_Start_Candidate", "Delayed_Start_Candidate"),
                                  ("Tau01", "Tau01"), ("Parent_Cosine_GRU", "Parent_Cosine_GRU"),
                                  ("B", "B"), ("C5", "C5")):
            for metric in METRICS:
                require(abs(paired[method][metric] - pilot["paired"][pilot_key][metric]) <= 1e-12,
                        f"pilot parity mismatch for {method}/{metric}")
    return {
        "scene_id": sid,
        "split": scene_record["source_split"],
        "wind_group": "HF_W09_W14",
        "release_generation": new["release_generation"],
        "release_sha256": new["release_sha256"],
        "run_start_sha256": new["run_start_sha256"],
        "run_status_sha256": new["run_status_sha256"],
        "source_lock_sha256": new["source_lock_sha256"],
        "completed": True,
        "status_value": new["status"]["status_value"],
        "safety_stop_reason": new["status"]["safety_stop_reason"],
        "test_data_read": new["status"]["test_data_read"],
        "plant_calls": new["status"]["Plant_calls"],
        "methods": paired,
    }


def macro(rows: list[dict]):
    return {m: {k: sum(r["methods"][m][k] for r in rows) / len(rows) for k in METRICS}
            for m in METHOD_LABELS}


def summarize(rows: list[dict]):
    means = macro(rows)
    candidate = "Delayed_Start_Candidate"
    delta = {base: {k: 100.0 * (means[candidate][k] / means[base][k] - 1.0) for k in METRICS}
             for base in ("Tau01", "Parent_Cosine_GRU", "B", "C5")}
    wins = {}
    for base in ("Tau01", "Parent_Cosine_GRU", "B", "C5"):
        wins[base] = {}
        for k in METRICS:
            ds = [r["methods"][candidate][k] - r["methods"][base][k] for r in rows]
            wins[base][k] = {"win": sum(x < -WIN_TOL for x in ds),
                             "tie": sum(abs(x) <= WIN_TOL for x in ds),
                             "loss": sum(x > WIN_TOL for x in ds)}
    safety = {}
    for m in METHOD_LABELS:
        counts = {}
        scenes_with_event = {f: 0 for f in SAFETY}
        unknown = {f: 0 for f in SAFETY}
        for f in SAFETY:
            vals = [r["methods"][m]["safety"].get(f) for r in rows]
            counts[f] = sum(int(v) for v in vals if v is not None)
            scenes_with_event[f] = sum(v is not None and int(v) > 0 for v in vals)
            unknown[f] = sum(v is None for v in vals)
        safety[m] = {"sample_totals": counts, "scenes_with_event": scenes_with_event,
                     "unknown_scene_counts": unknown}
    return means, delta, wins, safety


def write_markdown(path: Path, result: dict):
    lines = ["# Delayed-start GRU HF6 paired screen", "",
             f"Status: **{result['status']}**. Completed scenes: {result['completed_scene_count']}/6.",
             "Fixed DEV/VAL HF6 screen; this is development screening, not independent validation. TEST was not read.", "",
             "| Method | Q (m) | task SO(3) (rad) | inner SO(3) (rad) |",
             "|---|---:|---:|---:|"]
    for method in METHOD_LABELS:
        m = result["groups"]["HF6"]["macro_mean_observed"][method]
        lines.append(f"| {method} | {m['Q_m']:.9g} | {m['task_SO3_rad']:.9g} | {m['inner_SO3_rad']:.9g} |")
    lines.extend(["", "Candidate relative change versus baseline (%; negative is lower error):", "",
                  "| Baseline | Q | task SO(3) | inner SO(3) |", "|---|---:|---:|---:|"])
    for method, values in result["groups"]["HF6"]["candidate_delta_percent_vs_baseline"].items():
        lines.append(f"| {method} | {values['Q_m']:+.3f}% | {values['task_SO3_rad']:+.3f}% | {values['inner_SO3_rad']:+.3f}% |")
    lines.extend(["", "Safety totals by method:", ""])
    for method, values in result["groups"]["HF6"]["safety_counts_by_method"].items():
        nonzero = sum(values["scenes_with_event"].values())
        lines.append(f"- {method}: {nonzero} nonzero safety event counters across {result['completed_scene_count']} scenes.")
    lines.extend(["", "Per-scene candidate metrics:", "",
                  "| Scene | Split | Release gen | Q (m) | task SO(3) (rad) | inner SO(3) (rad) |",
                  "|---|---|---:|---:|---:|---:|"])
    for row in result["scene_results"]:
        m = row["methods"]["Delayed_Start_Candidate"]
        lines.append(f"| {row['scene_id']} | {row['split']} | {row['release_generation']} | {m['Q_m']:.9g} | {m['task_SO3_rad']:.9g} | {m['inner_SO3_rad']:.9g} |")
    lines.extend(["", "Release file hashes are recorded per scene; the pilot scene uses archived generation 1 and the other five use generation 2.",
                  "Cohort results are limited to this fixed six-scene development screen and do not establish independent validation.", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--validate-only", action="store_true",
                    help="score the prior pilot scene and check parity, without writing the HF6 result")
    args = ap.parse_args()
    plan, binding, old_release, new_release, scene_records, tau_rows, tau_score = verify_static_bindings()
    by_id = {r["scene_id"]: r for r in binding["scene_runs"]}
    selected = (plan["prior_completed_scene_ids"] if args.validate_only else plan["fixed_hf6_scene_ids"])
    for sid in selected:
        require(sid in by_id and by_id[sid].get("state") == "COMPLETED" and
                by_id[sid].get("status_value") == "STABLE", f"scene is not complete/stable: {sid}")
    if not args.validate_only and len(selected) != 6:
        raise RuntimeError("final HF6 run must include all six authorized scenes")
    if not args.validate_only and (OUT_JSON.exists() or OUT_MD.exists()):
        raise RuntimeError("refusing to overwrite existing HF6 score artifacts")

    locked_cfg = readj(LOCKED_CFG_PATH)
    scorer, metric_path = load_scorer(tau_score)
    constants = tau_score["metric_constants"]
    rows = [score_scene(sid, by_id[sid], scene_records[sid], tau_rows[sid],
                        old_release, new_release, locked_cfg, scorer,
                        float(constants["gravity_mps2"]), float(constants["max_tilt_rad"]))
            for sid in selected]
    if args.validate_only:
        print(json.dumps({"status": "FIRST_SCENE_VALIDATION_OK", "scene_id": rows[0]["scene_id"],
                          "release_generation": rows[0]["release_generation"],
                          "paired": {m: {k: rows[0]["methods"][m][k] for k in METRICS}
                                     for m in METHOD_LABELS},
                          "result_file_written": False}, indent=2, ensure_ascii=False))
        return

    means, delta, wins, safety = summarize(rows)
    result = {
        "schema": "DL1018_GRU_TAU01_DELAYED_START_HF6_PAIRED_SCORE_V1",
        "status": "COMPLETE_HF6_SCREEN",
        "study_id": new_release["study_id"], "candidate": new_release["candidate"],
        "scope": "Fixed six-scene DEV/VAL HF_W09_W14 development screen; not independent validation.",
        "completed_scene_count": len(rows), "expected_scene_count": 6,
        "split_counts": {split: sum(r["split"] == split for r in rows) for split in ("DEV", "VAL")},
        "independent_validation_claimed": False, "fresh_holdout_required_for_winner": True,
        "release_archives": {
            "generation_1": {"path": str(OLD_RELEASE_PATH), "sha256": sha(OLD_RELEASE_PATH)},
            "generation_2": {"path": str(RELEASE_PATH), "sha256": sha(RELEASE_PATH)},
        },
        "source_lock_sha256": sha(SOURCE_LOCK_PATH),
        "source_hash_manifest_sha256": sha(SOURCE_MANIFEST_PATH),
        "scene_input_manifest_sha256": sha(SCENE_MANIFEST_PATH),
        "locked_cfg_sha256": sha(LOCKED_CFG_PATH),
        "c5_input_lock_sha256": sha(C5_INPUT_LOCK_PATH),
        "run_binding_path": str(BINDING_PATH), "run_binding_sha256": sha(BINDING_PATH),
        "tau01_formal_score_path": str(TAU_SCORE_PATH), "tau01_formal_score_sha256": sha(TAU_SCORE_PATH),
        "metric_source_path": str(metric_path), "metric_source_sha256": sha(metric_path),
        "metric_constants": constants,
        "groups": {"HF6": {
            "scene_count": len(rows), "expected_scene_count": 6, "complete": True,
            "macro_mean_observed": means,
            "candidate_delta_percent_vs_baseline": delta,
            "candidate_per_scene_wins_losses_ties": wins,
            "safety_counts_by_method": safety,
        }},
        "scene_results": rows,
        "Plant_calls_by_scorer": 0, "training_runs_by_scorer": 0,
        "TEST_read": False, "test_data_read": False, "inertia_reconstruction": False,
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }
    result["groups"]["HF6"]["macro_mean_observed"] = means
    OUT_JSON.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_markdown(OUT_MD, result)
    print(json.dumps({"status": result["status"], "completed": len(rows), "json": str(OUT_JSON),
                      "markdown": str(OUT_MD)}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
