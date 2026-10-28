"""Read-only HF_W09_W14 attitude-path diagnosis from locked Full72 score inputs."""
from __future__ import annotations
import csv, hashlib, json, math
from pathlib import Path
import h5py
import numpy as np
from scipy.spatial.transform import Rotation

OUT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "experiments" / "dl_attitude_replacement_20261026"
STUDY = BASE / "gru_stream_cosine_tracking_head_full72_v1"
AUDIT = STUDY / "audits"
SCORE_JSON = AUDIT / "FULL72_PAIRED_SCORE_v1.json"
SCORE_CSV = AUDIT / "FULL72_PAIRED_SCORE_v1.csv"
SCORE_SCRIPT = AUDIT / "score_full72_candidate_v1.py"
OUT_CSV = OUT_DIR / "HF_W09_W14_attitude_path_by_scene_phase.csv"
OUT_MD = OUT_DIR / "HF_W09_W14_attitude_path_diagnosis.md"
METHODS = ("Candidate", "B", "C5")
PHASES = (("0_5s", 0.0, 5.0), ("5_10s", 5.0, 10.0),
          ("10_15s", 10.0, 15.0), ("15_20s", 15.0, 20.0))
ALL_PHASE = ("ALL_0_20s_shared", 0.0, 20.0)
RUNNER_SOURCES = (
    ("Candidate runner", BASE / "gru_stream_cosine_tracking_head_full72_v1" /
     "candidate_runner_work" / "matlab" / "runtime" / "run_mlp15_dev72_closed_loop.m"),
    ("B runner", ROOT / "experiments" / "attitude_physics_inertia_observer_20261025" /
     "paired_runner" / "morph_dev2_dev72_v1" / "matlab" / "runtime" /
     "run_paired_observer_closed_loop.m"),
    ("C5 runner", ROOT / "experiments" / "position_axis_coordinate_c5_20261023" /
     "run_dl1018_closed_loop.m"),
)
SIGNALS = ("task_actual_rmse_rad", "task_command_target_rmse_rad",
           "command_target_filtered_rmse_rad", "filtered_actual_rmse_rad",
           "task_filtered_rmse_rad")


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def require(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)


def so3_angles(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return (Rotation.from_euler("xyz", b).inv() *
            Rotation.from_euler("xyz", a)).magnitude()


def rmse_angles(a: np.ndarray, b: np.ndarray) -> float:
    angle = so3_angles(a, b)
    return float(np.sqrt(np.mean(angle ** 2)))


def task_euler(ref_acc: np.ndarray, yaw: np.ndarray, gravity: float,
               max_tilt: float) -> np.ndarray:
    acc = ref_acc.copy()
    acc[:, 2] += gravity
    a = np.cos(yaw) * acc[:, 0] + np.sin(yaw) * acc[:, 1]
    b = np.sin(yaw) * acc[:, 0] - np.cos(yaw) * acc[:, 1]
    roll = np.arctan2(b, np.hypot(acc[:, 2], a))
    pitch = np.arctan2(a, acc[:, 2])
    scale = np.minimum(1.0, max_tilt / np.maximum(np.hypot(roll, pitch), np.finfo(float).eps))
    return np.column_stack((roll * scale, pitch * scale, yaw))


def load_trace(method: str, rec: dict) -> dict:
    source = rec["methods"][method]
    path = Path(source["raw_path"])
    require(path.is_file(), f"Missing {method} raw: {path}")
    actual_sha = sha(path)
    require(actual_sha.lower() == source["raw_sha256"].lower(),
            f"Locked raw SHA mismatch for {rec['scene_id']} {method}")
    stat_before = path.stat()
    with h5py.File(path, "r") as f:
        log = f["log"]
        state = np.asarray(log["state"][()], dtype=np.float64).T
        time = np.asarray(log["time"][()], dtype=np.float64).reshape(-1)
        transition_time = np.asarray(log["transition_time"][()], dtype=np.float64).reshape(-1)
        target = np.asarray(log["command_filter_target_euler"][()], dtype=np.float64).T
        inner = np.asarray(log["filtered_attitude_reference"][()], dtype=np.float64).T
        ref_acc = np.asarray(f["scene/reference/acceleration"][()], dtype=np.float64).T
        yaw = np.asarray(f["scene/reference/yaw"][()], dtype=np.float64).reshape(-1)
    stat_after = path.stat()
    require((stat_before.st_size, stat_before.st_mtime_ns) ==
            (stat_after.st_size, stat_after.st_mtime_ns),
            f"Raw changed while reading: {path}")
    require(state.shape == (20001, 12) and time.shape == (20001,),
            f"Unexpected state/time dimensions for {rec['scene_id']} {method}")
    require(transition_time.shape == target.shape[:1] == inner.shape[:1] == (20000,),
            f"Unexpected transition/attitude dimensions for {rec['scene_id']} {method}")
    require(target.shape == inner.shape == (20000, 3),
            f"Unexpected command/filter dimensions for {rec['scene_id']} {method}")
    require(ref_acc.shape == (20001, 3) and yaw.shape == (20001,),
            f"Unexpected reference dimensions for {rec['scene_id']} {method}")
    require(np.max(np.abs(np.diff(time) - 0.001)) < 1e-10 and
            time[0] == 0.0 and time[-1] == 20.0,
            f"Unexpected 1 ms time base for {rec['scene_id']} {method}")
    require(np.array_equal(transition_time, time[:20000]),
            f"Transition time is not exactly time[0:20000] for {rec['scene_id']} {method}")
    for name, array in (("state", state), ("time", time), ("transition_time", transition_time),
                        ("command target", target), ("filtered reference", inner),
                        ("reference acceleration", ref_acc), ("reference yaw", yaw)):
        require(np.isfinite(array).all(), f"Non-finite {name} for {rec['scene_id']} {method}")
    return {"path": str(path), "raw_sha256": actual_sha, "time": time,
            "transition_time": transition_time, "state": state, "target": target,
            "inner": inner, "ref_acc": ref_acc, "yaw": yaw}


def ref_change_stats(t: np.ndarray, acc: np.ndarray, yaw: np.ndarray) -> dict:
    dt = np.diff(t)
    require(len(dt) and np.max(np.abs(dt - 0.001)) < 1e-10,
            "Reference change window is not 1 ms aligned")
    da = np.diff(acc, axis=0)
    yaw_unwrapped = np.unwrap(yaw)
    dyaw = np.diff(yaw_unwrapped)
    accel_rate = np.linalg.norm(da / dt[:, None], axis=1)
    yaw_rate = dyaw / dt
    return {
        "ref_accel_norm_min_mps2": float(np.min(np.linalg.norm(acc, axis=1))),
        "ref_accel_norm_max_mps2": float(np.max(np.linalg.norm(acc, axis=1))),
        "ref_accel_step_rms_mps2": float(np.sqrt(np.mean(np.sum(da ** 2, axis=1)))),
        "ref_accel_rate_rms_mps3": float(np.sqrt(np.mean(accel_rate ** 2))),
        "ref_accel_rate_peak_mps3": float(np.max(accel_rate)),
        "ref_accel_changed_steps_gt_1e-9": int(np.sum(np.linalg.norm(da, axis=1) > 1e-9)),
        "ref_yaw_unwrapped_span_rad": float(np.ptp(yaw_unwrapped)),
        "ref_yaw_step_rms_rad": float(np.sqrt(np.mean(dyaw ** 2))),
        "ref_yaw_rate_rms_rad_s": float(np.sqrt(np.mean(yaw_rate ** 2))),
        "ref_yaw_rate_peak_abs_rad_s": float(np.max(np.abs(yaw_rate))),
        "ref_yaw_changed_steps_gt_1e-9": int(np.sum(np.abs(dyaw) > 1e-9)),
    }


def main() -> None:
    score = json.loads(SCORE_JSON.read_text(encoding="utf-8-sig"))
    score_script_sha = sha(SCORE_SCRIPT)
    require(score_script_sha.lower() == score["scorer"]["sha256"].lower(),
            "Frozen scorer SHA does not match the score JSON")
    require(score["candidate"] == "GRU32_STREAM72_COSINE_TRACKING_HEAD_S2026102001" and
            score["scene_count"] == 72, "Unexpected Full72 score identity")
    constants = score["metric_constants"]
    gravity = float(constants["gravity_mps2"])
    max_tilt = float(constants["max_tilt_rad"])
    rows = [r for r in score["rows"] if "HF_W09_W14" in r["groups"]]
    require(len(rows) == 28 and len({r["scene_id"] for r in rows}) == 28,
            "HF_W09_W14 must contain exactly 28 unique scenes")
    require(all(r["split"] in ("DEV", "VAL") and
                9 <= int(r["scene_id"].rsplit("_W", 1)[1]) <= 14 for r in rows),
            "Unexpected split or wind ID in HF_W09_W14 selection")

    out_rows: list[dict] = []
    raw_identities: set[tuple[str, str, str]] = set()
    recomputed: dict[tuple[str, str], tuple[float, float]] = {}
    for rec in rows:
        traces = {m: load_trace(m, rec) for m in METHODS}
        base = traces["Candidate"]
        for method in ("B", "C5"):
            for key in ("time", "transition_time", "ref_acc", "yaw"):
                require(np.array_equal(base[key], traces[method][key]),
                        f"Shared {key} differs across methods for {rec['scene_id']}")
        t = base["time"]
        task = task_euler(base["ref_acc"], base["yaw"], gravity, max_tilt)
        for method, trace in traces.items():
            actual_all = trace["state"][:, 6:9]
            actual = actual_all[:20000]
            task_full = rmse_angles(actual_all, task)
            inner_full = rmse_angles(actual, trace["inner"])
            require(abs(task_full - rec["methods"][method]["task_SO3_rad"]) <= 1e-10,
                    f"Recomputed full task_SO3 differs from score for {rec['scene_id']} {method}")
            require(abs(inner_full - rec["methods"][method]["inner_SO3_rad"]) <= 1e-10,
                    f"Recomputed full inner_SO3 differs from score for {rec['scene_id']} {method}")
            recomputed[(rec["scene_id"], method)] = (task_full, inner_full)
            raw_identities.add((rec["scene_id"], method, trace["raw_sha256"]))
            for phase, start, end in PHASES + (ALL_PHASE,):
                mask = (trace["transition_time"] >= start) & (trace["transition_time"] < end)
                expected_count = 20000 if phase == ALL_PHASE[0] else 5000
                require(int(mask.sum()) == expected_count,
                        f"Bad phase count for {rec['scene_id']} {method} {phase}")
                idx = np.flatnonzero(mask)
                sl = slice(idx[0], idx[-1] + 1)
                tw, actual_w, target_w, inner_w = task[idx], actual[idx], trace["target"][idx], trace["inner"][idx]
                metrics = {
                    "task_actual_rmse_rad": rmse_angles(actual_w, tw),
                    "task_command_target_rmse_rad": rmse_angles(target_w, tw),
                    "command_target_filtered_rmse_rad": rmse_angles(inner_w, target_w),
                    "filtered_actual_rmse_rad": rmse_angles(actual_w, inner_w),
                    "task_filtered_rmse_rad": rmse_angles(inner_w, tw),
                }
                change = ref_change_stats(trace["transition_time"][sl],
                                          trace["ref_acc"][idx], trace["yaw"][idx])
                out_rows.append({
                    "scene_id": rec["scene_id"], "split": rec["split"], "method": method,
                    "phase": phase, "start_s_inclusive": start, "end_s_exclusive": end,
                    "sample_count": int(mask.sum()), "raw_path": trace["path"],
                    "raw_sha256": trace["raw_sha256"],
                    "scorer_full_task_SO3_rad": rec["methods"][method]["task_SO3_rad"],
                    "scorer_full_inner_SO3_rad": rec["methods"][method]["inner_SO3_rad"],
                    **metrics, **change,
                })

    require(len(raw_identities) == 84, "Expected exactly 84 unique scene/method/raw identities")
    require(not OUT_CSV.exists() and not OUT_MD.exists(), "Refusing to overwrite diagnostic output")
    fields = list(out_rows[0])
    with OUT_CSV.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(out_rows)

    def mean(phase: str, method: str, metric: str) -> float:
        values = [r[metric] for r in out_rows if r["phase"] == phase and r["method"] == method]
        require(len(values) == 28, f"Bad summary count for {phase} {method} {metric}")
        return float(np.mean(values))

    def mrad(value: float) -> str:
        return f"{1000.0 * value:.3f}"

    lines = [
        "# HF_W09_W14 attitude-path diagnosis",
        "",
        "Offline read-only diagnosis of the frozen GRU32 Full72 Candidate, B, and C5 raws. No Plant/MATLAB, training, or TEST data were accessed. C5 remains pending parent raw audit per the frozen score report.",
        "",
        "## Scope and alignment",
        "",
        f"Selected exactly {len(rows)} unique DEV/VAL scenes with wind IDs W09–W14; read 84 locked raw files (28 scenes × 3 methods). Each raw SHA-256 was checked against the frozen score JSON before reading.",
        "",
        "Raw dimensions match the scorer: state/reference acceleration are 20001 samples; time is 0.000–20.000 s at 1 ms; filtered_attitude_reference and command_filter_target_euler are 20000×3; transition_time is exactly time[0:20000]. Within every scene, Candidate/B/C5 time, transition_time, reference acceleration, and reference yaw are exactly equal.",
        "",
        "Window metrics use the shared transition instants [0,5), [5,10), [10,15), [15,20), 5000 samples per window. This keeps task, command target, filtered reference, and actual attitude on the same timestamps. The full-duration score reproduction also includes the final state at t=20 s, as the frozen scorer does.",
        "",
        "Task Euler attitude reuses the frozen score equation: add gravity to reference acceleration z; derive roll/pitch from reference acceleration and yaw; scale roll/pitch together to the locked max tilt; keep reference yaw. For same-time Euler attitudes A and B, each geodesic sample is θₖ = angle(R_B(tₖ)ᵀ R_A(tₖ)), matching the frozen `Rotation.from_euler('xyz', B).inv() * Rotation.from_euler('xyz', A)` convention; each reported RMSE is sqrt(mean(θₖ²)). `command_filter_target_euler` is the runner's per-transition target from `positionInfo.commanded_acceleration` via `baseline_force_to_attitude`; its timestamps are `transition_time`.",
        "The command-target logging and conversion are visible in the frozen run sources: Candidate `run_mlp15_dev72_closed_loop.m` (target conversion near line 1303, log field near 2960); B `run_paired_observer_closed_loop.m` (near 1221 and 2780); C5 `run_dl1018_closed_loop.m` (near 1169 and 2694).",
        "",
        "## Frozen source identities",
        "",
        f"- Diagnostic script SHA-256: `{sha(Path(__file__))}`",
        f"- Frozen score script SHA-256: `{score_script_sha}`",
        f"- Frozen score JSON SHA-256: `{sha(SCORE_JSON)}`",
        f"- Frozen paired score CSV SHA-256: `{sha(SCORE_CSV)}`",
        f"- Gravity / tilt cap: `{gravity:.12g} m/s²` / `{max_tilt:.12g} rad`",
        f"- Task-formula release SHA-256: `{constants['constants_release_sha256']}`; formula source SHA-256: `{constants['formula_sha256']}`",
        *[f"- {name} source SHA-256: `{sha(path)}` ({path})" for name, path in RUNNER_SOURCES],
        "- Raw identities and SHA-256 values: the 84 scene/method rows in the CSV.",
        "",
        "## Frozen HF macro comparison",
        "",
        "| Method | Task SO(3) actual (mrad) | Inner SO(3) actual (mrad) |",
        "|---|---:|---:|",
    ]
    for method in METHODS:
        task_mean = float(np.mean([recomputed[(r["scene_id"], method)][0] for r in rows]))
        inner_mean = float(np.mean([recomputed[(r["scene_id"], method)][1] for r in rows]))
        lines.append(f"| {method} | {mrad(task_mean)} | {mrad(inner_mean)} |")
    lines += ["", "The recomputed full-duration task and inner SO(3) RMSE match the frozen per-scene values within 1e-10 rad for all 84 raws.", ""]

    phase_labels = {"0_5s": "0–5 s", "5_10s": "5–10 s", "10_15s": "10–15 s",
                    "15_20s": "15–20 s", "ALL_0_20s_shared": "ALL: 0–20 s shared 20,000 samples"}
    for phase, _, _ in PHASES + (ALL_PHASE,):
        lines += [f"## {phase_labels[phase]}", "",
                  "Absolute group values are macro means across 28 scenes (one RMSE per scene, then equal scene weight); differences are Candidate minus comparator. Values are SO(3) RMSE in mrad.", "",
                  "| Group result | Task→command target | Command target→filtered | Filtered→actual | Task→filtered | Task→actual |",
                  "|---|---:|---:|---:|---:|---:|"]
        for method in METHODS:
            vals = [mrad(mean(phase, method, metric)) for metric in
                    ("task_command_target_rmse_rad", "command_target_filtered_rmse_rad",
                     "filtered_actual_rmse_rad", "task_filtered_rmse_rad", "task_actual_rmse_rad")]
            lines.append(f"| Absolute: {method} | " + " | ".join(vals) + " |")
        for comparator in ("B", "C5"):
            deltas = [mrad(mean(phase, "Candidate", metric) - mean(phase, comparator, metric)) for metric in
                      ("task_command_target_rmse_rad", "command_target_filtered_rmse_rad",
                       "filtered_actual_rmse_rad", "task_filtered_rmse_rad", "task_actual_rmse_rad")]
            lines.append(f"| Candidate − {comparator} | " + " | ".join(deltas) + " |")
        lines += ["", "Shared external reference-command movement (mean of per-scene rates; identical across Candidate/B/C5 within each scene):", "",
                  "| Signal | Mean RMS rate | Largest per-scene peak rate | Units |",
                  "|---|---:|---:|---|"]
        for metric, title, unit, peak_metric in (
            ("ref_accel_rate_rms_mps3", "Reference acceleration", "m/s³", "ref_accel_rate_peak_mps3"),
            ("ref_yaw_rate_rms_rad_s", "Reference yaw", "rad/s", "ref_yaw_rate_peak_abs_rad_s")):
            vals = [r for r in out_rows if r["phase"] == phase and r["method"] == "Candidate"]
            lines.append(f"| {title} | {np.mean([r[metric] for r in vals]):.6g} | {np.max([r[peak_metric] for r in vals]):.6g} | {unit} |")
        lines.append("")

    task_delta = mean("0_5s", "Candidate", "task_actual_rmse_rad") - mean("0_5s", "B", "task_actual_rmse_rad")
    lines += [
        "## What the data supports",
        "",
        "- Over ALL shared samples, Candidate actual is 1.689 mrad closer to its filtered reference than B, while Candidate's filtered reference is 3.176 mrad farther from task and its task→actual error is 4.038 mrad higher. Candidate's command target is 17.658 mrad farther from task, and command target→filtered gap is 42.360 mrad higher than B. This supports a pre-inner-loop/reference-chain mismatch accompanying the score reversal: the actual attitude follows Candidate's filtered reference better overall, but that reference is less aligned with the external task. The five SO(3) RMSE links are non-additive, so this does not quantify a causal share.",
        "- In the four same-time bins Candidate task→actual is worse than B by 3.292–4.396 mrad; Candidate task→command target is higher by 16.717–18.976 mrad and command target→filtered by 38.643–45.143 mrad. Candidate filtered→actual is slightly worse in 0–5 s (+0.385 mrad) and better in the later bins (−2.695, −1.137, −1.859 mrad).",
        "- Candidate→B and Candidate→C5 segment deltas are printed for every requested phase and ALL shared samples; a negative delta means a smaller geodesic RMSE for Candidate. The path RMSEs do not add algebraically, so they locate where discrepancies appear but do not assign an additive share of task error.",
        "- The external reference acceleration/yaw is unchanged across the three methods within every scene. The per-phase rate/span values quantify the shared, time-varying commands; they are not candidate-specific input differences.",
        "",
        "## Interpretation limits",
        "",
        "The logged command target depends on each run's position-controller commanded acceleration and its yaw at that instant. Therefore task→command target measures outer-loop/setpoint divergence from the externally defined task attitude; command target→filtered reference measures the gap across the command filter/reference chain; filtered reference→actual measures inner tracking. The association of a segment with the score pattern is supported by these observations, but causality would require a controlled rerun or intervention. Candidate Full72 is an in-sample DEV/VAL screen; B run labels remain raw-pending-audit and C5 parent audit remains pending as qualified in the frozen score report.",
        "",
        f"CSV: `{OUT_CSV.name}` (420 per-scene/method/phase rows: four windows plus ALL shared samples).",
        "",
    ]
    with OUT_MD.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write("\n".join(lines))


if __name__ == "__main__":
    main()
