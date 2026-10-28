from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
ROOT = HERE.parents[3]
RUNS = STUDY / "runs"
PILOT_RELEASE = HERE / "RELEASE_PILOT_ARCHIVE_v1.json"
RELEASE = STUDY / "RELEASE.json"
PILOT_SCORE = HERE / "ROOT_POSITION_APPLIED_LOWPASS_SINGLE_SCENE_AUDIT_v1.json"
PILOT_GAP = HERE / "PILOT_SOURCE_LOCK_ARCHIVE_GAP_v1.json"
RUN_BINDING = HERE / "HF6_RUN_BINDING_v1.json"
BASELINE_SCORE = ROOT / "experiments/dl_attitude_replacement_20261028/gru_tau01_delayed_start_v1/audits/ROOT_HF6_SCORE_v1.json"
METRIC = ROOT / "experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_full72_v1/audits/score_full72_candidate_v1.py"
OUT_JSON = HERE / "ROOT_POSITION_APPLIED_LOWPASS_HF6_SCORE_v1.json"
OUT_MD = HERE / "ROOT_POSITION_APPLIED_LOWPASS_HF6_SCORE_v1.md"
METHODS = ("B", "C5", "Parent_Cosine_GRU", "Delayed_Start_Candidate", "Position_Applied_Lowpass_tau0p1")
BASELINES = METHODS[:-1]
METRICS = ("Q_m", "task_SO3_rad", "inner_SO3_rad")
SAFETY = ("motor_saturation_samples", "generalized_clip_samples", "tilt_limited_samples",
          "attitude_head_projection_samples", "attitude_head_output_saturated_samples")
WIN_TOL = 1e-12


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


def text_field(group, name: str) -> str:
    import numpy as np
    return "".join(chr(int(x)) for x in np.asarray(group[name][()]).reshape(-1) if x)


def bind_baseline(info: dict, sid: str, method: str):
    raw = Path(info["raw_path"])
    require(raw.is_file() and sha(raw).lower() == info["raw_sha256"].lower(),
            f"{method} raw hash mismatch: {sid}")
    status_path_value = info.get("run_status_path") or info.get("status_path")
    status_sha = info.get("run_status_sha256") or info.get("status_sha256")
    require(status_path_value and status_sha, f"{method} status binding missing: {sid}")
    status_path = Path(status_path_value)
    require(sha(status_path).lower() == status_sha.lower(), f"{method} status hash mismatch: {sid}")
    status = readj(status_path)
    complete = status.get("state") == "COMPLETED" or status.get("status") == "RUN_COMPLETE_RAW_PENDING_AUDIT"
    stable = status.get("status_value", status.get("log_status", "STABLE")) == "STABLE"
    require(status.get("scene_id") == sid and complete and stable and status.get("safety_stop_reason", "") == "",
            f"{method} status is not stable/completed: {sid}")
    test_value = status.get("TEST_data_read", status.get("test_data_read",
                   status.get("TEST_accessed", status.get("TEST_read", False))))
    require(test_value is False, f"{method} status reports TEST access: {sid}")
    require(Path(status["raw_path"]).resolve() == raw.resolve() and
            status.get("raw_sha256", "").lower() == info["raw_sha256"].lower(),
            f"{method} status/raw binding mismatch: {sid}")
    return raw, status_path, status


def completed_runs(scene_ids: list[str]):
    found = {sid: [] for sid in scene_ids}
    for status_path in RUNS.glob("*/run_status.json"):
        status = readj(status_path)
        sid = status.get("scene_id")
        if sid in found and status.get("state") == "COMPLETED":
            found[sid].append(status_path)
    duplicates = {sid: paths for sid, paths in found.items() if len(paths) > 1}
    require(not duplicates, "Multiple completed candidate runs for a scene: " + str(duplicates))
    return {sid: paths[0] for sid, paths in found.items() if paths}, [sid for sid, paths in found.items() if not paths]


def load_candidate(sid: str, status_path: Path, scene_release_map: dict, gen2_release: dict,
                   gen1_sha: str):
    status = readj(status_path)
    run_dir = status_path.parent
    start_path = run_dir / "run_start.json"
    raw_path = Path(status["raw_path"])
    require(start_path.is_file() and raw_path.is_file(), f"Missing run_start/raw: {sid}")
    start = readj(start_path)
    status_sha, start_sha, raw_sha = sha(status_path), sha(start_path), sha(raw_path)
    require(status.get("scene_id") == sid and start.get("scene_id") == sid and
            start.get("candidate_study_id") == STUDY.name, f"Candidate identity mismatch: {sid}")
    require(status.get("state") == "COMPLETED" and status.get("status_value") == "STABLE" and
            status.get("safety_stop_reason", "") == "" and status.get("Plant_calls") == 1 and
            status.get("transitions") == 20000 and status.get("state_samples") == 20001,
            f"Candidate run incomplete/unsafe: {sid}")
    require(status.get("TEST_data_read") is False and start.get("TEST_data_read") is False and
            start.get("inertia_reconstruction_enabled") is False,
            f"Candidate scope violation: {sid}")
    require(Path(status["raw_path"]).resolve() == raw_path.resolve() and
            status.get("raw_sha256", "").lower() == raw_sha.lower(), f"Candidate raw/status mismatch: {sid}")

    release_sha = start.get("release_sha256", "").lower()
    lock_sha = start.get("source_lock_sha256", "").lower()
    manifest_sha = start.get("source_hash_manifest_sha256", "").lower()
    require(status.get("release_sha256", "").lower() == release_sha and
            status.get("source_lock_sha256", "").lower() == lock_sha, f"Candidate run_start/status lock mismatch: {sid}")
    release, generation, release_path = scene_release_map[sid]
    require(sha(release_path).lower() == release_sha and release.get("status") == "RELEASED" and
            release.get("study_id") == STUDY.name and sid in release.get("authorized_scenes", []),
            f"Candidate release binding/authorization mismatch: {sid}")
    require(release.get("source_lock_sha256", "").lower() == lock_sha and
            release.get("source_hash_manifest_sha256", "").lower() == manifest_sha,
            f"Candidate lock/manifest differs from its release: {sid}")
    if generation == 2:
        require(lock_sha == gen2_release["source_lock_sha256"].lower() and
                manifest_sha == gen2_release["source_hash_manifest_sha256"].lower(),
                f"Generation-2 source binding mismatch: {sid}")
    else:
        require(release_sha == gen1_sha and lock_sha == "3564cf7eee7d3f8abe99f4f3c2091ee3ab12f3fdd60e70ca2e6fc6a98de9a3d1" and
                manifest_sha == "46b649cb65ae87d9cee5e3ecfa0f14777240d1e22b17f76fe04a8b94328c1c05",
                "Pilot generation-1 lock identity mismatch")

    import h5py
    with h5py.File(raw_path, "r") as raw:
        identity = raw["runIdentity"]
        require(text_field(identity, "scene_id") == sid and text_field(identity, "release_sha256") == release_sha and
                text_field(identity, "source_lock_sha256") == lock_sha and
                text_field(identity, "source_hash_manifest_sha256") == manifest_sha,
                f"Raw runIdentity binding mismatch: {sid}")
        require(bool(identity["TEST_data_read"][()][0, 0]) is False and
                bool(identity["inertia_reconstruction_enabled"][()][0, 0]) is False and
                abs(float(identity["applied_acceleration_lowpass_tau_s"][()][0, 0]) - 0.1) < 1e-12 and
                abs(float(identity["applied_acceleration_lowpass_event_rate_hz"][()][0, 0]) - 100) < 1e-12 and
                bool(identity["position_force_and_pcf_use_same_filtered_output"][()][0, 0]) is True,
                f"Raw low-pass identity contract mismatch: {sid}")
    return {
        "path": raw_path, "raw_sha256": raw_sha, "run_status_path": status_path,
        "run_status_sha256": status_sha, "run_start_path": start_path, "run_start_sha256": start_sha,
        "status": status, "release": release, "release_path": release_path,
        "release_sha256": release_sha, "release_generation": generation,
        "source_lock_sha256": lock_sha, "source_hash_manifest_sha256": manifest_sha,
        "source_lock_snapshot_retained": generation == 2,
    }


def metric_module(expected_sha: str):
    require(sha(METRIC).lower() == expected_sha.lower(), "Frozen score_raw source hash mismatch")
    spec = importlib.util.spec_from_file_location("frozen_full72_score_raw", METRIC)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    require(not OUT_JSON.exists() and not OUT_MD.exists(), "Refusing to overwrite existing HF6 outputs")
    gen1 = readj(PILOT_RELEASE)
    gen2 = readj(RELEASE)
    gen1_sha, gen2_sha = sha(PILOT_RELEASE), sha(RELEASE)
    require(gen1.get("status") == "RELEASED" and gen1.get("authorized_Plant_calls") == 1 and
            gen1.get("fixed_scene_id") == "DL1018_VAL_T3_C01_W14", "Invalid archived pilot release")
    require(gen2.get("status") == "RELEASED" and gen2.get("release_generation") == 2 and
            gen2.get("previous_release_sha256", "").lower() == gen1_sha.lower() and
            gen2.get("pilot_release_sha256", "").lower() == gen1_sha.lower(), "Invalid generation-2 release chain")
    scene_ids = list(gen2["authorized_scenes"])
    require(len(scene_ids) == 6 and len(set(scene_ids)) == 6 and
            scene_ids[0] == gen1["fixed_scene_id"] and
            set(scene_ids[1:]) == set(gen2["continuation_scene_ids"]), "HF6 release scene list mismatch")
    binding = readj(RUN_BINDING)
    binding_sha = sha(RUN_BINDING)
    require(binding.get("status") == "COMPLETE_HF6_POSITION_LOWPASS_SCREEN" and
            binding.get("scene_count") == 6 and binding.get("TEST_data_read") is False and
            binding.get("inertia_reconstruction_enabled") is False and binding.get("Plant_calls") == 6,
            "Per-scene HF6 run binding is incomplete or out of scope")
    require([r["scene_id"] for r in binding["scene_runs"]] == scene_ids[1:] and
            binding["prior_completed_scene"]["scene_id"] == scene_ids[0],
            "Run binding and release scene order differ")
    require(binding["release_chain"][0]["release_sha256"].lower() == gen1_sha.lower() and
            binding["release_chain"][1]["release_sha256"].lower() == gen2_sha.lower() and
            binding["source_lock_sha256"].lower() == gen2["source_lock_sha256"].lower(),
            "Run-binding release/source-lock generations differ from archived releases")

    runs, pending = completed_runs(scene_ids)
    if pending:
        print(json.dumps({"status": "WAITING_FOR_HF6_COMPLETION", "completed_scenes": len(runs),
                          "expected_scenes": 6, "pending_scene_ids": pending}, ensure_ascii=False))
        return

    baseline = readj(BASELINE_SCORE)
    require(baseline.get("status") == "COMPLETE_HF6_SCREEN" and baseline.get("completed_scene_count") == 6 and
            baseline.get("TEST_read") is False and baseline.get("inertia_reconstruction") is False,
            "Delayed-tau HF6 baseline score is not eligible")
    require(gen2.get("pilot_source_lock_archive_gap_report") == PILOT_GAP.relative_to(STUDY).as_posix(),
            "Generation-2 release does not bind the pilot lock-gap report")
    require(sha(PILOT_GAP).lower() == gen2["pilot_source_lock_archive_gap_report_sha256"].lower(),
            "Pilot lock-gap report hash mismatch")
    gap = readj(PILOT_GAP)
    require(gap.get("status") == "PRIOR_SOURCE_LOCK_AND_MANIFEST_BYTES_NOT_ARCHIVED" and
            gap.get("pilot_release_archive_sha256", "").lower() == gen1_sha.lower(),
            "Pilot source-lock archive-gap report mismatch")
    require(sha(STUDY / "SOURCE_LOCK_v1.json").lower() == gen2["source_lock_sha256"].lower() and
            sha(STUDY / "SOURCE_HASH_MANIFEST_v1.json").lower() == gen2["source_hash_manifest_sha256"].lower(),
            "Generation-2 source lock/manifest files are not retained at their bound hashes")
    manifest2 = readj(STUDY / "SOURCE_HASH_MANIFEST_v1.json")
    for rec in manifest2["files"]:
        require(sha(STUDY / rec["path"]).lower() == rec["sha256"].lower(),
                f"Generation-2 source file hash mismatch: {rec['path']}")

    release_map = {scene_ids[0]: (gen1, 1, PILOT_RELEASE)}
    release_map.update({sid: (gen2, 2, RELEASE) for sid in scene_ids[1:]})
    candidate = {sid: load_candidate(sid, runs[sid], release_map, gen2, gen1_sha)
                 for sid in scene_ids}
    expected_bindings = {r["scene_id"]: r for r in binding["scene_runs"]}
    expected_bindings[scene_ids[0]] = binding["prior_completed_scene"]
    for sid, result in candidate.items():
        expected = expected_bindings[sid]
        for field, actual in (("run_start_sha256", result["run_start_sha256"]),
                              ("run_status_sha256", result["run_status_sha256"]),
                              ("raw_sha256", result["raw_sha256"]),
                              ("release_sha256", result["release_sha256"])):
            require(expected[field].lower() == actual.lower(), f"Run-binding {field} mismatch: {sid}")
        require(Path(expected.get("raw_path", result["path"])).resolve() == result["path"].resolve(),
                f"Run-binding raw path mismatch: {sid}")

    pilot_score = readj(PILOT_SCORE)
    require(pilot_score.get("status") == "PASS_FROZEN_SCORE_AND_OUTPUT_PATH_AUDIT" and
            pilot_score.get("candidate_raw_sha256", "").lower() == candidate[scene_ids[0]]["raw_sha256"].lower(),
            "Pilot raw differs from the reviewed single-scene score")
    metric = metric_module(baseline["metric_source_sha256"])
    gravity = float(baseline["metric_constants"]["gravity_mps2"])
    max_tilt = float(baseline["metric_constants"]["max_tilt_rad"])
    baseline_rows = {r["scene_id"]: r for r in baseline["scene_results"]}
    require(set(scene_ids).issubset(baseline_rows), "HF6 baseline score is missing required scenes")

    results = []
    for sid in scene_ids:
        base_row = baseline_rows[sid]
        methods = {}
        candidate_info = candidate[sid]
        scored_candidate = metric.score_raw(candidate_info["path"], gravity, max_tilt)
        methods["Position_Applied_Lowpass_tau0p1"] = {
            **{k: float(scored_candidate[k]) for k in METRICS}, "safety": scored_candidate["safety"],
            "raw_path": str(candidate_info["path"]), "raw_sha256": candidate_info["raw_sha256"],
            "run_status_path": str(candidate_info["run_status_path"]),
            "run_status_sha256": candidate_info["run_status_sha256"],
            "run_start_sha256": candidate_info["run_start_sha256"],
            "release_generation": candidate_info["release_generation"],
            "release_sha256": candidate_info["release_sha256"],
            "source_lock_sha256": candidate_info["source_lock_sha256"],
            "source_hash_manifest_sha256": candidate_info["source_hash_manifest_sha256"],
            "source_lock_snapshot_retained": candidate_info["source_lock_snapshot_retained"],
        }
        for method in BASELINES:
            entry = base_row["methods"][method]
            raw, status_path, _ = bind_baseline(entry, sid, method)
            scored = metric.score_raw(raw, gravity, max_tilt)
            for key in METRICS:
                require(abs(scored[key] - entry[key]) <= 1e-12,
                        f"Frozen-score parity failed for {method}/{sid}/{key}")
            methods[method] = {
                **{k: float(scored[k]) for k in METRICS}, "safety": scored["safety"],
                "raw_path": str(raw), "raw_sha256": entry["raw_sha256"],
                "run_status_path": str(status_path),
                "run_status_sha256": entry.get("run_status_sha256", entry.get("status_sha256")),
            }
        if sid == scene_ids[0]:
            for method, pilot_key in (("B", "B"), ("C5", "C5"), ("Parent_Cosine_GRU", "Parent_Cosine_GRU"),
                                      ("Delayed_Start_Candidate", "Delayed_Start_Candidate")):
                for key in METRICS:
                    require(abs(methods[method][key] - pilot_score["methods"][pilot_key][key]) <= 1e-12,
                            f"Pilot score parity mismatch for {method}/{key}")
        results.append({
            "scene_id": sid, "split": "DEV" if "_DEV_" in sid else "VAL", "wind_group": "HF_W09_W14",
            "status_value": candidate_info["status"]["status_value"],
            "safety_stop_reason": candidate_info["status"]["safety_stop_reason"],
            "test_data_read": False, "plant_calls": candidate_info["status"]["Plant_calls"],
            "release_generation": candidate_info["release_generation"],
            "release_sha256": candidate_info["release_sha256"],
            "source_lock_sha256": candidate_info["source_lock_sha256"],
            "source_hash_manifest_sha256": candidate_info["source_hash_manifest_sha256"],
            "methods": methods,
        })

    candidate_name = "Position_Applied_Lowpass_tau0p1"
    means = {method: {key: sum(row["methods"][method][key] for row in results) / len(results)
                      for key in METRICS} for method in METHODS}
    delta_pct = {base: {key: 100 * (means[candidate_name][key] / means[base][key] - 1)
                        for key in METRICS} for base in BASELINES}
    wins = {base: {key: {
        "win": sum(row["methods"][candidate_name][key] < row["methods"][base][key] - WIN_TOL for row in results),
        "tie": sum(abs(row["methods"][candidate_name][key] - row["methods"][base][key]) <= WIN_TOL for row in results),
        "loss": sum(row["methods"][candidate_name][key] > row["methods"][base][key] + WIN_TOL for row in results),
    } for key in METRICS} for base in BASELINES}
    safety = {}
    for method in METHODS:
        safety[method] = {field: {
            "total_samples": sum(int(row["methods"][method]["safety"].get(field) or 0) for row in results),
            "scenes_with_events": sum(int(row["methods"][method]["safety"].get(field) or 0) > 0 for row in results),
            "unknown_scenes": sum(row["methods"][method]["safety"].get(field) is None for row in results),
        } for field in SAFETY}

    output = {
        "schema": "DL1018_POSITION_APPLIED_LOWPASS_HF6_SCORE_V1",
        "status": "COMPLETE_HF6_DEVELOPMENT_SCREEN",
        "candidate": "position-applied-acceleration low-pass tau=0.1 s, 100-Hz exact-ZOH update",
        "scope": "Six fixed DEV/VAL HF scenes; same-scene raw scoring only.",
        "completed_scene_count": len(results), "expected_scene_count": 6,
        "independent_validation_claimed": False, "fresh_holdout_required_for_winner": True,
        "TEST_read": False, "test_data_read": False, "inertia_reconstruction": False,
        "Plant_calls_by_scorer": 0, "training_runs_by_scorer": 0,
        "release_chain": [
            {"generation": 1, "path": str(PILOT_RELEASE), "sha256": gen1_sha,
             "source_lock_sha256": gen1["source_lock_sha256"],
             "source_hash_manifest_sha256": gen1["source_hash_manifest_sha256"],
             "retained_source_lock_snapshot": False, "scene_ids": [scene_ids[0]]},
            {"generation": 2, "path": str(RELEASE), "sha256": gen2_sha,
             "source_lock_sha256": gen2["source_lock_sha256"],
             "source_hash_manifest_sha256": gen2["source_hash_manifest_sha256"],
             "retained_source_lock_snapshot": True, "verified_source_file_count": len(manifest2["files"]),
             "scene_ids": scene_ids[1:]},
        ],
        "pilot_source_lock_archive_gap_report": {"path": str(PILOT_GAP), "sha256": sha(PILOT_GAP),
                                                   "status": gap["status"]},
        "hf6_run_binding_path": str(RUN_BINDING), "hf6_run_binding_sha256": binding_sha,
        "frozen_metric_source_path": str(METRIC), "frozen_metric_source_sha256": sha(METRIC),
        "metric_constants": {"gravity_mps2": gravity, "max_tilt_rad": max_tilt},
        "macro_mean": means, "candidate_delta_percent_vs_baseline": delta_pct,
        "candidate_scene_wins_ties_losses": wins, "safety_counts_by_method": safety,
        "scene_results": results,
        "interpretation": "Fixed-cohort development screen only; no independent validation or causal claim.",
    }
    OUT_JSON.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# Position-applied low-pass candidate: HF6 paired screen", "",
             "Six fixed DEV/VAL scenes; development screening only, not independent validation.", "",
             "| Method | Q (m) | task SO(3) (rad) | inner SO(3) (rad) |",
             "|---|---:|---:|---:|"]
    for method in METHODS:
        m = means[method]
        lines.append(f"| {method} | {m['Q_m']:.9g} | {m['task_SO3_rad']:.9g} | {m['inner_SO3_rad']:.9g} |")
    lines += ["", "Candidate minus each baseline (% of baseline mean; negative is lower error):", "",
              "| Baseline | Q | task SO(3) | inner SO(3) |", "|---|---:|---:|---:|"]
    for base in BASELINES:
        d = delta_pct[base]
        lines.append(f"| {base} | {d['Q_m']:+.2f}% | {d['task_SO3_rad']:+.2f}% | {d['inner_SO3_rad']:+.2f}% |")
    lines += ["", "Candidate source generations:", "",
              f"- Pilot scene: generation 1, release `{gen1_sha}`, source lock `{gen1['source_lock_sha256']}`; old lock/manifest bytes were not archived.",
              f"- Remaining scenes: generation 2, release `{gen2_sha}`, source lock `{gen2['source_lock_sha256']}`; {len(manifest2['files'])} source files verified.",
              "", "Per-scene results:", "", "| Scene | Gen | Q (m) | task SO(3) (rad) | inner SO(3) (rad) | Safe |",
              "|---|---:|---:|---:|---:|---|"]
    for row in results:
        m = row["methods"][candidate_name]
        safe = row["status_value"] == "STABLE" and row["safety_stop_reason"] == "" and all(
            (m["safety"].get(key) or 0) == 0 for key in SAFETY)
        lines.append(f"| {row['scene_id']} | {row['release_generation']} | {m['Q_m']:.9g} | {m['task_SO3_rad']:.9g} | {m['inner_SO3_rad']:.9g} | {'yes' if safe else 'no'} |")
    lines += ["", "The pilot generation-1 source-lock snapshot gap is retained in the audit record. HF6 is a fixed development screen; a winner still requires fresh holdout evidence.", ""]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": output["status"], "completed_scene_count": len(results),
                      "output_json": str(OUT_JSON), "output_markdown": str(OUT_MD), "macro_mean": means,
                      "candidate_delta_percent_vs_baseline": delta_pct,
                      "pilot_source_lock_snapshot_retained": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
