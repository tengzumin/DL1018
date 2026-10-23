"""Recompute the entire preregistered C4 screen, including all negative outcomes."""
import csv
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
RUN = ROOT / "experiments/position_coordinate_c4_20261023"
TOL = 1e-12


def sha(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def write_csv(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    output = HERE / "screen12_parent_review"
    assert not output.exists(), "Preserve prior screen evidence"
    contract_path = RUN / "C4_RUN_CONTRACT_v3.json"
    contract = load(contract_path)
    ids = contract["scene_ids"]
    assert len(set(ids)) == len(ids) == 12
    checker_path = HERE / "check_c4_raw_parent.py"
    checker = module(checker_path, "frozen_parent_c4_raw_checker")
    pilot_release = load(RUN / "C4_RELEASE_v3.json")
    assert sha(checker_path) == next(r["sha256"] for r in pilot_release["validation_and_comparator_refs"] if Path(r["path"]).name == checker_path.name)
    decoder = module(ROOT / "reports/paper14_v2/phase1/audit_w15_position_replay.py", "existing_mat_decoder")
    snapshot = RUN / "C4_PREPARED_CFG_OPTS_v3.mat"
    expected = {s: decoder.flatten(decoder.matlab_section(snapshot, s)) for s in ("cfg", "opts")}
    audited, metrics, pairs = [], [], []
    for sid in ids:
        status_path = RUN / "runs_c4_v3" / sid / "C4_COORDINATE_M0/attempt_01/run_status.json"
        row = checker.verify(status_path)
        status = load(status_path)
        start = decoder.matlab_section(Path(status["run_start_path"]), "runStart")
        for section in ("cfg", "opts"):
            actual = decoder.flatten(start[section])
            if section == "opts":
                actual.pop("r2e_first_plant_step_marker")
            assert actual.keys() == expected[section].keys(), (sid, section)
            assert all(decoder.same_value(actual[k], expected[section][k]) for k in actual), (sid, section)
        row["cfg_opts_snapshot_match"] = {s: len(expected[s]) for s in expected}
        audited.append(row)
        for name in ("C4_metrics", "C3_metrics", "B_metrics"):
            item = dict(row[name])
            item["B_identity_status"] = row["B_identity_status"]
            metrics.append(item)
        delta = row["Q_C4_minus_B_m"]
        pairs.append(dict(scene_id=sid, Q_C4_m=row["C4_metrics"]["Q_0_20_m"],
                          Q_C3_m=row["C3_metrics"]["Q_0_20_m"], Q_B_m=row["B_metrics"]["Q_0_20_m"],
                          Q_C4_minus_B_m=delta, Q_C4_minus_C3_m=row["Q_C4_minus_C3_m"],
                          Z_C4_minus_C3_m=row["Z_C4_minus_C3_m"],
                          C4_vs_B="WIN" if delta < -TOL else "LOSS" if delta > TOL else "TIE",
                          B_identity_status=row["B_identity_status"]))
    groups = {}
    sets = {"ALL12": ids, "HF6": [sid for sid in ids if 9 <= int(sid[-2:]) <= 14],
            "W15": [sid for sid in ids if sid.endswith("W15")]}
    sets.update({"T" + str(t): [sid for sid in ids if "_T" + str(t) + "_" in sid] for t in (1, 2, 3)})
    assert len(sets["HF6"]) == 6 and len(sets["W15"]) == 3
    for name, selection in sets.items():
        chosen = [r for r in audited if r["scene_id"] in selection]
        groups[name] = dict(n=len(chosen), **{method: float(np.mean([r[method + "_metrics"]["Q_0_20_m"] for r in chosen])) for method in ("C4", "C3", "B")})
    fig8 = [r for r in audited if r["scene_id"] in ("DL1018_VAL_T2_C00_W10", "DL1018_VAL_T2_C02_W12")]
    assert len(fig8) == 2
    gates = {"both_FIG8_HF_Q_and_Z_strictly_lower_than_C3": all(r["Q_C4_minus_C3_m"] < -TOL and r["Z_C4_minus_C3_m"] < -TOL for r in fig8),
             "ALL12_mean_Q_no_higher_than_C3": groups["ALL12"]["C4"] <= groups["ALL12"]["C3"] + TOL,
             "HF6_mean_Q_no_higher_than_B": groups["HF6"]["C4"] <= groups["HF6"]["B"] + TOL,
             "W15_mean_Q_no_higher_than_B": groups["W15"]["C4"] <= groups["W15"]["B"] + TOL,
             "all_12_complete_finite_STABLE_full_event_audits": all(r["status"] == "PASS_C4_RAW_ALL_EVENTS" for r in audited)}
    result = dict(status="C4_SCREEN_PASS" if all(gates.values()) else "C4_SCREEN_FAIL_NO_DEV72_EXTENSION",
                  gates=gates, groups=groups, wins_vs_B=sum(p["C4_vs_B"] == "WIN" for p in pairs),
                  wins_with_improvement_gt_1um=sum(p["Q_C4_minus_B_m"] < -1e-6 for p in pairs),
                  wins_with_improvement_gt_10um=sum(p["Q_C4_minus_B_m"] < -1e-5 for p in pairs),
                  tolerance_m=TOL, event_count=sum(r["event_count"] for r in audited),
                  max_raw_check_abs_error=max(max(r["checks"].values()) for r in audited),
                  B_limit="One fresh traceable B; other eleven historical B source identity remains disclosed until separate fresh B stage completes",
                  timing_qualification="NONISOLATED_NOT_FORMAL", training=0, TEST_accessed=False,
                  refs=[dict(path=str(p), sha256=sha(p)) for p in (contract_path, checker_path, Path(__file__), snapshot)],
                  audits=audited)
    output.mkdir()
    (output / "SUMMARY.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    write_csv(output / "ALL36_METRICS.csv", metrics)
    write_csv(output / "ALL12_PAIRS.csv", pairs)
    write_csv(output / "ALL_LOSSES_VS_B.csv", [p for p in pairs if p["C4_vs_B"] == "LOSS"])
    print(json.dumps({k: result[k] for k in ("status", "gates", "groups", "wins_vs_B", "event_count")}))


if __name__ == "__main__":
    main()
