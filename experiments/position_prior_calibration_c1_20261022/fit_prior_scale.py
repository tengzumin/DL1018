from __future__ import annotations
import argparse, csv, json, os, sys, time
from datetime import datetime
from pathlib import Path

for _n in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_n] = "1"
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reports" / "low_residual_objective_audit_20261022"))
import replay_objective as replay

REPLAY_SHA = "9e6d3a43b89ed6ecffd01519b6162ee67397b47ff25c2e32685c099a9fdad9a5"
BANDS = ("W00_W08", "W09_W14", "W15")
TIE_TOL = 1e-12
SMOKE_C = 0.5


def req(ok, msg):
    if not ok:
        raise RuntimeError(msg)


def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def run_coefficients(p, y, w):
    req(p.shape == y.shape and p.ndim == 2 and p.shape[1] == 3, "p/y shape mismatch")
    req(w.shape == (len(y),), "weight shape mismatch")
    req(np.isfinite(p).all() and np.isfinite(y).all() and np.isfinite(w).all(), "nonfinite p/y/weight")
    q = w.astype(np.float64, copy=False)
    mass = float(q.sum())
    req(mass > 0 and np.isfinite(mass), "invalid original phase weight mass")
    q = q / mass
    Ey = float(np.sum(q * np.sum(y * y, axis=1)))
    req(np.isfinite(Ey) and Ey > 0, "E_y must be finite and positive; no epsilon or run dropping")
    A = float(np.sum(q * np.sum(p * p, axis=1)) / Ey)
    B = float(np.sum(q * np.sum(p * y, axis=1)) / Ey)
    req(np.isfinite(A) and np.isfinite(B) and A >= 0, "invalid A/B")
    return A, B, Ey, q


def risk(a, b, c):
    return a * c * c - 2.0 * b * c + 1.0


def minimax(group):
    req(set(group) == set(BANDS), "requires exactly the three frozen wind bands")
    for g, (a, b) in group.items():
        req(np.isfinite(a) and np.isfinite(b) and a >= 0, f"invalid coefficient for {g}")
    cand = {0.0: ["endpoint:0"], 1.0: ["endpoint:1"]}
    detail = []

    def add(c, label):
        if np.isfinite(c) and 0.0 <= c <= 1.0:
            cand.setdefault(float(c), []).append(label)

    for g, (a, b) in sorted(group.items()):
        if a > 0:
            c = b / a
            detail.append({"kind": "stationary", "group": g, "c": c, "in_interval": 0.0 <= c <= 1.0})
            add(c, f"stationary:{g}")
        else:
            detail.append({"kind": "linear_or_constant", "group": g, "A": a, "B": b,
                           "note": "endpoints and pair intersections cover its minimum"})
    names = sorted(group)
    for i, g1 in enumerate(names):
        a1, b1 = group[g1]
        for g2 in names[i + 1:]:
            a2, b2 = group[g2]
            da, db = a1 - a2, b1 - b2
            if da == 0:
                detail.append({"kind": "identical_functions" if db == 0 else "parallel_difference",
                               "pair": [g1, g2], "common_c0": True})
            else:
                c = 2.0 * db / da
                inside = bool(np.isfinite(c) and 0 <= c <= 1)
                detail.append({"kind": "pair_intersection", "pair": [g1, g2], "c": c, "in_interval": inside})
                if inside:
                    add(c, f"intersection:{g1}|{g2}")
    rows = []
    for c, sources in sorted(cand.items()):
        vals = {g: risk(*group[g], c) for g in names}
        req(all(np.isfinite(v) for v in vals.values()), f"nonfinite risk at c={c}")
        worst = max(names, key=lambda g: vals[g])
        rows.append({"c": c, "sources": sorted(set(sources)), "risk_by_band": vals,
                     "worst_risk": vals[worst], "worst_band": worst})
    best = min(x["worst_risk"] for x in rows)
    tied = [x for x in rows if x["worst_risk"] <= best + TIE_TOL]
    chosen = max(tied, key=lambda x: x["c"])
    r1 = max(risk(*group[g], 1.0) for g in names)
    rs = float(chosen["worst_risk"])
    improvement = r1 - rs
    return {
        "c_star": float(chosen["c"]), "selected_candidate": chosen, "candidates": rows,
        "candidate_generation_details": detail, "minimum_worst_risk": best,
        "tie_tolerance": TIE_TOL, "tie_rule": "within 1e-12, choose largest c",
        "worst_risk_c1": r1, "worst_risk_cstar": rs, "worst_risk_reduction_vs_c1": improvement,
        "gate_1_minus_c_at_least_0_01": 1.0 - float(chosen["c"]) >= 0.01,
        "gate_risk_reduction_at_least_0_01": improvement >= 0.01,
        "train_gate_pass": bool(1.0 - float(chosen["c"]) >= 0.01 and improvement >= 0.01),
    }


def direct_ratio(p, y, q, Ey, c):
    return float(np.sum(q * np.sum((c * p - y) ** 2, axis=1)) / Ey)


def write_json(path, obj):
    req(not path.exists(), f"refusing overwrite: {path}")
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def write_csv(path, rows):
    req(not path.exists() and rows, f"refusing overwrite/empty output: {path}")
    with path.open("x", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def fail(exc, command, started):
    path = OUT / "C1_FAILURES.csv"
    row = {"time": now(), "command": command, "script_sha256": replay.sha256_file(Path(__file__)),
           "exception_type": type(exc).__name__, "exception": str(exc),
           "wall_seconds": time.perf_counter() - started, "optimizer_steps": 0,
           "plant_calls": 0, "gpu_jobs": 0, "test_accessed": False}
    existed = path.exists()
    with path.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row))
        if not existed:
            w.writeheader()
        w.writerow(row)


def main():
    parser = argparse.ArgumentParser(description="One-shot TRAIN-only analytic calibration of frozen raw W0 scale")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--smoke", action="store_true", help="synthetic minimax and one-run TRAIN algebra check")
    modes.add_argument("--fit-train-after-audit", action="store_true", help="single TRAIN1536 fit; requires parent approval")
    args = parser.parse_args()
    started = time.perf_counter()
    command = "python -B " + " ".join(sys.argv)
    try:
        req(replay.sha256_file(Path(replay.__file__)) == REPLAY_SHA, "frozen replay helper SHA mismatch")
        runs, source_by_id, scene_counts = replay.check_static_inputs()
        if args.smoke:
            synthetic = {"W00_W08": (4.0, 0.8), "W09_W14": (0.1, 0.2), "W15": (0.05, 0.2)}
            solved = minimax(synthetic)
            cross = 2.0 * (0.8 - 0.2) / (4.0 - 0.1)
            req(abs(solved["c_star"] - cross) <= 1e-14, "synthetic minimax crossing check failed")
            req(any("intersection:W00_W08|W09_W14" in x["sources"] for x in solved["candidates"]),
                "synthetic active intersection missing from candidates")
            run = runs[0]
            ends, p, y, _raw, phase, w, phase_counts, phase_n = replay.load_one(
                run, source_by_id[run["run_id"]], scene_counts)
            A, B, Ey, q = run_coefficients(p, y, w)
            direct = direct_ratio(p, y, q, Ey, SMOKE_C)
            poly = risk(A, B, SMOKE_C)
            err = abs(direct - poly)
            req(err <= 1e-12, f"TRAIN direct-MSE identity failed: {err}")
            replay.check_static_inputs()
            result = {
                "status": "PASS_C1_SYNTHETIC_AND_TRAIN_SMOKE", "generated_local": now(), "command": command,
                "script_sha256": replay.sha256_file(Path(__file__)), "replay_script_sha256": replay.sha256_file(Path(replay.__file__)),
                "runs_sha256": replay.EXPECTED["runs_sha256"], "training_index_sha256": replay.EXPECTED["train_index_sha256"],
                "synthetic": {"group_coefficients": synthetic, "expected_crossing": cross, "solver": solved},
                "train_run": {"run_id": run["run_id"], "task": run["task"], "role": run["role"],
                              "wind_band": run["wind_band"], "wind_cell": run["wind_cell"], "endpoints": len(ends),
                              "endpoint_recipe": "31+5*k, k=0..393", "phase_n": phase_n, "phase_code_counts": phase_counts,
                              "q_sum": float(q.sum()), "E_y": Ey, "A": A, "B": B,
                              "fixed_smoke_c_not_fit": SMOKE_C, "direct_mse_ratio": direct,
                              "polynomial_mse_ratio": poly, "absolute_identity_error": err},
                "definitions": "p is unclipped raw W0 sidecar output; y is same-endpoint exact cache float32; q is this run's original phase weight normalized to one.",
                "optimizer_steps": 0, "plant_calls": 0, "gpu_jobs": 0, "test_accessed": False, "dev_labels_used": False,
                "wall_seconds": time.perf_counter() - started,
            }
            write_json(OUT / "C1_SMOKE.json", result)
            print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
            return 0

        for name in ("C1_RUN_COEFFICIENTS.csv", "C1_GROUP_COEFFICIENTS.csv", "C1_CALIBRATION_RESULT.json", "C1_STATE.json"):
            req(not (OUT / name).exists(), f"refusing overwrite: {OUT / name}")
        run_rows = []
        grouped = {band: [] for band in BANDS}
        windows = 0
        for i, run in enumerate(runs, 1):
            ends, p, y, _raw, phase, w, phase_counts, phase_n = replay.load_one(
                run, source_by_id[run["run_id"]], scene_counts)
            band = run["wind_band"]
            req(band in grouped, f"unexpected wind band: {band}")
            A, B, Ey, q = run_coefficients(p, y, w)
            l1 = risk(A, B, 1.0)
            req(np.isfinite(l1), f"{run['run_id']}: nonfinite c=1 risk")
            grouped[band].append((A, B))
            windows += len(ends)
            run_rows.append({"run_id": run["run_id"], "task": run["task"], "role": run["role"],
                             "wind_band": band, "wind_cell": run["wind_cell"], "endpoints": len(ends),
                             "phase_n": phase_n, "phase_counts_json": json.dumps(phase_counts, sort_keys=True, separators=(",", ":")),
                             "q_sum": float(q.sum()), "E_y": Ey, "A": A, "B": B, "relative_mse_ratio_c1": l1})
            if i % 128 == 0 or i == len(runs):
                print(f"PROGRESS {i}/{len(runs)} TRAIN runs; endpoints={windows}; elapsed={time.perf_counter()-started:.1f}s", flush=True)
        req(len(runs) == 1536 and windows == 605184, "TRAIN cardinality mismatch")
        req(all(grouped[g] for g in BANDS), "empty frozen wind band")
        replay.check_static_inputs()
        group_coeffs = {g: (float(np.mean([v[0] for v in grouped[g]])),
                            float(np.mean([v[1] for v in grouped[g]]))) for g in BANDS}
        for g in BANDS:
            expected_n = sum(1 for r in runs if r["wind_band"] == g)
            req(len(grouped[g]) == expected_n, f"{g}: group run count mismatch")
        solved = minimax(group_coeffs)
        result = {
            "status": "PASS_C1_TRAIN_CALIBRATION_GATE" if solved["train_gate_pass"] else "STOP_C1_TRAIN_GATE_NOT_MET",
            "generated_local": now(), "command": command, "script_sha256": replay.sha256_file(Path(__file__)),
            "replay_script_sha256": replay.sha256_file(Path(replay.__file__)),
            "runs_sha256": replay.EXPECTED["runs_sha256"], "training_index_sha256": replay.EXPECTED["train_index_sha256"],
            "phase_state_sha256": replay.EXPECTED["phase_state_sha256"], "model_source_sha256": replay.EXPECTED["model_sha256"],
            "model_id": "CORRECTED_DSSM14_SEED2026102001_FINAL60000",
            "episodes": len(runs), "endpoints": windows, "endpoint_recipe": "31+5*k, k=0..393",
            "p_definition": "raw unclipped frozen W0 sidecar endpoint prediction; not beta/clip deployment output",
            "y_definition": "same-endpoint exact cache float32 training label",
            "q_definition": "original per-run phase weights returned by replay helper, renormalized per run",
            "group_coefficients": {g: {"runs": len(grouped[g]), "A_equal_run_mean": group_coeffs[g][0],
                                       "B_equal_run_mean": group_coeffs[g][1]} for g in BANDS},
            "solver": solved, "fit_scope": "one analytic TRAIN-only scalar calibration; no VAL fit, optimizer, encoder/normalizer update, seed search, or candidate search",
            "next_action": "separate review required; this script launches no Plant" if solved["train_gate_pass"] else "STOP before Plant; frozen gate not met",
            "optimizer_steps": 0, "plant_calls": 0, "gpu_jobs": 0, "test_accessed": False, "dev_labels_used": False,
            "wall_seconds": time.perf_counter() - started,
        }
        band_rows = [{"wind_band": g, "run_count": len(grouped[g]), "A_equal_run_mean": group_coeffs[g][0],
                      "B_equal_run_mean": group_coeffs[g][1], "risk_c1": risk(*group_coeffs[g], 1.0),
                      "risk_cstar": risk(*group_coeffs[g], solved["c_star"])} for g in BANDS]
        write_csv(OUT / "C1_RUN_COEFFICIENTS.csv", run_rows)
        write_csv(OUT / "C1_GROUP_COEFFICIENTS.csv", band_rows)
        result["run_coefficients_sha256"] = replay.sha256_file(OUT / "C1_RUN_COEFFICIENTS.csv")
        result["group_coefficients_sha256"] = replay.sha256_file(OUT / "C1_GROUP_COEFFICIENTS.csv")
        write_json(OUT / "C1_CALIBRATION_RESULT.json", result)
        state = {"status": result["status"], "generated_local": now(), "command": command,
                 "script_sha256": result["script_sha256"], "result_sha256": replay.sha256_file(OUT / "C1_CALIBRATION_RESULT.json"),
                 "run_csv_sha256": result["run_coefficients_sha256"], "group_csv_sha256": result["group_coefficients_sha256"],
                 "episodes": len(runs), "endpoints": windows, "optimizer_steps": 0, "plant_calls": 0,
                 "gpu_jobs": 0, "test_accessed": False, "failures": []}
        write_json(OUT / "C1_STATE.json", state)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except Exception as exc:
        fail(exc, command, started)
        print(json.dumps({"status": "FAILED", "generated_local": now(), "command": command,
                          "script_sha256": replay.sha256_file(Path(__file__)),
                          "exception_type": type(exc).__name__, "exception": str(exc),
                          "wall_seconds": time.perf_counter() - started, "optimizer_steps": 0,
                          "plant_calls": 0, "gpu_jobs": 0, "test_accessed": False},
                         ensure_ascii=False, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


