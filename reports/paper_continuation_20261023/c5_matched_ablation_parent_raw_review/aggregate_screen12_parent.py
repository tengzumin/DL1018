"""Independent compact paired aggregation of the two frozen raw-audit receipts."""
from pathlib import Path
import csv
import hashlib
import json
import math

HERE = Path(__file__).resolve().parent
OUT = HERE / "SCREEN12_PARENT_COMPACT_v1.json"
CSV = HERE / "SCREEN12_ALL_PAIRED_AND_LOSSES_v1.csv"
assert not OUT.exists() and not CSV.exists()
sources = {
    "C5_FREEZE_TRAINED_W0": "0d6041208efe7b198be5deaeaf4db1db72516140a0efe21bb782698f990a92c8",
    "C5_NO_DELAYED_PREDICTION": "807aaedda90638fe03915293f80cc7ed979366d7de94e5a3f68b1d68f3660343",
}
results, table = {}, []
for variant, expected in sources.items():
    path = HERE / f"{variant}_SCREEN12_RAW_PARENT_AUDIT_v1.json"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected
    audit = json.loads(path.read_text(encoding="utf-8"))
    assert audit["status"] == "PASS_C5_MATCHED_ABLATION_SCREEN12_ALL_EVENTS"
    rows = audit["screen12_rows"]
    assert len(rows) == len({row["scene_id"] for row in rows}) == 12
    assert sum(row["event_checks"]["event_count"] for row in rows) == 23616
    groups = {"ALL12": rows, "HF_W09_W14": [r for r in rows if 9 <= r["wind_number"] <= 14],
              "W15": [r for r in rows if r["wind_number"] == 15]}
    for task in ("T1", "T2", "T3"):
        groups[task] = [r for r in rows if r["task"] == task]
    by_group = {}
    for name, selected in groups.items():
        means = {method: math.fsum(r["methods"][method]["Q_0_20_m"] for r in selected)/len(selected)
                 for method in (variant, "C5_M110", "B_TRACEABLE", "C3")}
        assert means == {m: audit["screen12_summary"]["groups"][name]["equal_scene_weighted_mean_metrics"][m]["Q_0_20_m"] for m in means}
        delta = [r["methods"][variant]["Q_0_20_m"]-r["methods"]["C5_M110"]["Q_0_20_m"] for r in selected]
        by_group[name] = {"n": len(selected), "mean_Q_m": means,
                          "ablation_vs_C5_wins": sum(x < -1e-12 for x in delta),
                          "ablation_vs_C5_losses": sum(x > 1e-12 for x in delta),
                          "ablation_vs_C5_ties": sum(abs(x) <= 1e-12 for x in delta)}
    results[variant] = by_group
    for row in rows:
        q = row["methods"][variant]["Q_0_20_m"]
        c5 = row["methods"]["C5_M110"]["Q_0_20_m"]
        b = row["methods"]["B_TRACEABLE"]["Q_0_20_m"]
        table.append({"variant": variant, "scene_id": row["scene_id"], "Q_m": q, "C5_Q_m": c5,
                      "B_Q_m": b, "delta_vs_C5_m": q-c5, "delta_vs_B_m": q-b,
                      "outcome_vs_C5": "WIN" if q-c5 < -1e-12 else "LOSS" if q-c5 > 1e-12 else "TIE"})
result = {"status": "PASS_INDEPENDENT_REAGGREGATION_OF_TWO_RAW_AUDITS", "sources_sha256": sources,
          "results": results, "event_count_total": 47232, "new_Plant_in_this_check": 0,
          "TEST_accessed": False, "scope": "Fixed screen12 only; no extrapolation to DEV72 or test."}
with OUT.open("x", encoding="utf-8") as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
with CSV.open("x", encoding="utf-8", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=list(table[0]))
    writer.writeheader()
    writer.writerows(table)
print(json.dumps({"status": result["status"], "event_count": 47232,
                  "compact_sha256": hashlib.sha256(OUT.read_bytes()).hexdigest(),
                  "csv_sha256": hashlib.sha256(CSV.read_bytes()).hexdigest()}))
