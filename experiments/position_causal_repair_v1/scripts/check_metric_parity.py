from __future__ import annotations

import csv
import json
from pathlib import Path

from d1_pair_analyze import ROOT, OUT, reduce_raw

SCENES = ("DL1018_DEV_T1_C04_W00", "DL1018_DEV_T1_C07_W08")
ROLES = ("B", "P_A")
FIELDS = {
    "Q_0_20_m": "Q_0_20_m", "Q_5_20_m": "Q_5_20_m", "A_0_20_rad": "A_0_20_rad",
    "position_peak_m": "position_peak_m", "position_p95_m": "position_p95_m",
    "motor_TV_normalized_per_s": "motor_TV_normalized_per_s",
    "motor_saturation_fraction": "motor_saturation_fraction",
    "generalized_clip_fraction": "generalized_clip_fraction",
}
TOL = 1e-8


def read(p: Path) -> list[dict[str, str]]:
    with p.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def main() -> None:
    attempts = read(ROOT / "logs/attempt_index.csv")
    specs = {r["scene_id"]: r for r in read(ROOT / "configs/scene_specs.csv")}
    dev = {r["run_id"]: r for r in read(ROOT / "reports/POSITION_DEV.csv")}
    results = []
    for scene in SCENES:
        for role in ROLES:
            cand = [r for r in attempts if r["gate_id"] == "G06_P_DEV" and r["scene_id"] == scene
                    and r["collector_id"] == role and r["status"] == "STABLE"]
            if len(cand) != 1:
                raise RuntimeError(f"Expected one stable G06 record for {scene}/{role}: {len(cand)}")
            attempt = cand[0]
            raw = ROOT / Path(attempt["raw_path"].replace("/", "\\"))
            actual = reduce_raw(raw, attempt, specs[scene])
            official = dev.get(attempt["run_id"])
            if official is None:
                raise RuntimeError(f"Run not in original POSITION_DEV.csv: {attempt['run_id']}")
            diffs = {}
            for py_key, csv_key in FIELDS.items():
                expected = float(official[csv_key]); got = float(actual[py_key])
                diffs[py_key] = {"official": expected, "recomputed": got, "abs_diff": abs(expected-got),
                                 "within_tolerance": abs(expected-got) <= TOL}
            results.append({"scene_id": scene, "role": role, "run_id": attempt["run_id"],
                            "metrics": diffs, "max_abs_diff": max(x["abs_diff"] for x in diffs.values())})
    passed = all(x["within_tolerance"] for r in results for x in r["metrics"].values())
    out = {"comparison": "Python h5py reducer vs original MATLAB POSITION_DEV.csv",
           "scenes": list(SCENES), "roles": list(ROLES), "float_tolerance": TOL,
           "bitwise_comparison": "not claimed; CSV serialization and MATLAB/Python floating-point paths differ",
           "passed": passed, "records": results}
    p = OUT / "reports/D1_METRIC_PARITY.json"
    p.write_text(json.dumps(out, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"passed": passed, "records": len(results),
                      "max_abs_diff": max(x["max_abs_diff"] for x in results), "report": str(p)}, ensure_ascii=False))
    if not passed:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
