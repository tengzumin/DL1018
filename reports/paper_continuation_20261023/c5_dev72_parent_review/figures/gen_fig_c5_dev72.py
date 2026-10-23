#!/usr/bin/env python3
"""Generate the paired C5 DEV72 result figure after the frozen audit completes."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[4]
REVIEW = ROOT / "reports/paper_continuation_20261023/c5_dev72_parent_review"
REPORT = ROOT / "reports/paper_continuation_20261023/c5_dev72_execution"
EXP = ROOT / "experiments/position_axis_coordinate_c5_dev72_20261023"
AUDIT = REVIEW / "C5_DEV72_RAW_PARENT_REVIEW_v3.json"
OS_EXIT = REPORT / "C5_DEV72_MATLAB_OS_EXIT_v3.json"
BATCH = EXP / "C5_DEV72_BATCH_STATUS_v3.json"
BODY = EXP / "C5_DEV72_BODY_COMPLETE_v3.json"
CONTRACT = EXP / "C5_DEV72_RUN_CONTRACT_v3.json"
LOCK = EXP / "C5_DEV72_INPUT_LOCK_v3.json"
PDF = Path(__file__).with_name("fig_c5_dev72.pdf")
PNG = Path(__file__).with_name("fig_c5_dev72.png")
META = Path(__file__).with_name("fig_c5_dev72_metadata.json")
SCENE_RE = re.compile(r"DL1018_(DEV|VAL)_T([1-3])_C\d\d_W(\d\d)\Z")
EXPECTED_SEED = 2026102001
TIE_TOLERANCE_M = 1e-12
PASS = "PASS_C5_DEV72_RAW_ALL_EVENTS_PARENT_AUDIT"
REJECT = "REJECT_C5_FIXED_CANDIDATE"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def scene_parts(scene_id: str):
    match = SCENE_RE.fullmatch(scene_id)
    assert match, scene_id
    return match.group(1), int(match.group(2)), int(match.group(3))


def validate_summary(audit: dict):
    assert audit["schema"] == "C5_AXIS_COORDINATE_DEV72_RAW_PARENT_AUDIT_V1"
    assert audit["status"] in (PASS, REJECT), audit.get("status")
    assert audit["matlab_os_exit_code"] == 0
    assert (audit["scene_count"], audit["new_scenes_event_checked"],
            audit["reused_scenes_event_audit_refs"]) == (72, 60, 12)
    assert audit["plant_calls_in_audit"] == 0 and audit["TEST_accessed"] is False
    assert audit["training_steps"] == audit["optimizer_steps"] == 0
    gates = audit["performance_gates"]
    assert gates and all(type(value) is bool for value in gates.values())
    assert (audit["status"] == PASS) == all(gates.values())

    rows, events = audit["rows"], audit["event_check_rows"]
    assert len(rows) == len(events) == 72
    assert len({r["scene_id"] for r in rows}) == len({r["scene_id"] for r in events}) == 72
    assert [r["scene_id"] for r in rows] == [r["scene_id"] for r in events]
    assert all(r["status"] in ("PASS_C5_RAW_ALL_EVENTS", "PASS_REUSED_C5_SCREEN_AUDIT") for r in rows)
    assert all(e["status"].startswith("PASS") and e["event_count"] == 1968 for e in events)
    assert sum(e["source"] == "DEV72_NEW_RAW_PARENT_RECOMPUTATION" for e in events) == 60
    assert sum(e["source"] == "C5_SCREEN_PARENT_AUDIT_REUSED" for e in events) == 12

    parsed = {r["scene_id"]: scene_parts(r["scene_id"]) for r in rows}
    assert sum(9 <= parsed[r["scene_id"]][2] <= 14 for r in rows) == 28
    assert sum(parsed[r["scene_id"]][2] == 15 for r in rows) > 0
    for row in rows:
        delta = row["C5_metrics"]["Q_0_20_m"] - row["B_metrics"]["Q_0_20_m"]
        assert math.isfinite(delta) and abs(delta - row["Q_C5_minus_B_m"]) <= 1e-12
        expect = "WIN" if delta < -TIE_TOLERANCE_M else ("LOSS" if delta > TIE_TOLERANCE_M else "TIE")
        assert row["comparison_vs_B"] == expect
        for method in ("B_metrics", "C3_metrics", "C5_metrics"):
            metrics = row[method]
            assert math.isfinite(metrics["Q_0_20_m"])
            assert all(math.isfinite(metrics[f"rmse_{axis}_0_20_m"]) for axis in "xyz")
    return rows, parsed


def load_inputs():
    for path in (AUDIT, OS_EXIT, BATCH, BODY, CONTRACT, LOCK):
        assert path.is_file(), f"Required completed-audit evidence is missing: {path}"
    audit = read_json(AUDIT)
    assert sha256(OS_EXIT) == audit["matlab_os_exit_sha256"]
    assert sha256(BATCH) == audit["batch_sha256"] and sha256(BODY) == audit["body_sha256"]
    assert sha256(CONTRACT) == audit["run_contract_sha256"] and sha256(LOCK) == audit["input_lock_sha256"]
    os_exit, batch, body, contract = map(read_json, (OS_EXIT, BATCH, BODY, CONTRACT))
    assert os_exit["schema"] == "C5_AXIS_COORDINATE_DEV72_MATLAB_OS_EXIT_V3"
    assert os_exit["matlab_os_exit_code"] == 0 and os_exit["matlab_process_count"] == 1
    assert os_exit["preflight_matlab_process_count"] == 0 and os_exit["plant_calls"] == 60
    assert os_exit["batch_status"] == os_exit["body_status"] == "COMPLETE_RAW_PENDING_PARENT_AUDIT"
    assert os_exit["body_sha256_after_os_return"].lower() == sha256(BODY)
    assert batch["status"] == body["status"] == "COMPLETE_RAW_PENDING_PARENT_AUDIT"
    assert batch["completed_scenes"] == body["completed_scene_count"] == 60
    assert batch["plant_calls"] == body["plant_calls"] == 60
    assert batch["TEST_accessed"] is body["TEST_accessed"] is False
    assert contract["model"]["seed"] == EXPECTED_SEED
    rows, parsed = validate_summary(audit)
    return audit, rows, parsed, {"audit": sha256(AUDIT), "os_exit": sha256(OS_EXIT),
                                 "batch": sha256(BATCH), "body": sha256(BODY),
                                 "contract": sha256(CONTRACT), "lock": sha256(LOCK)}


def mean_q(rows, method):
    return float(np.mean([r[f"{method}_metrics"]["Q_0_20_m"] for r in rows]))


def self_test():
    counts = [5, 5, 4, 4, 4, 4, 4, 4, 4, 4, 4, 5, 5, 5, 5, 6]
    rows, events = [], []
    for wind, count in enumerate(counts):
        for i in range(count):
            task, trial = (("DEV", 1), ("VAL", 2), ("DEV", 3), ("VAL", 1), ("DEV", 2), ("VAL", 3))[i % 6]
            sid = f"DL1018_{task}_T{trial}_C{i:02d}_W{wind:02d}"
            b = {"Q_0_20_m": .009, **{f"rmse_{a}_0_20_m": .004 for a in "xyz"}}
            c3 = {"Q_0_20_m": .0092, **{f"rmse_{a}_0_20_m": .0042 for a in "xyz"}}
            c5 = {"Q_0_20_m": .0085, **{f"rmse_{a}_0_20_m": .0038 for a in "xyz"}}
            rows.append({"status": "PASS_C5_RAW_ALL_EVENTS", "scene_id": sid,
                         "comparison_vs_B": "WIN", "Q_C5_minus_B_m": -.0005,
                         "B_metrics": b, "C3_metrics": c3, "C5_metrics": c5})
    assert len(rows) == 72 and sum(9 <= scene_parts(r["scene_id"])[2] <= 14 for r in rows) == 28
    for i, row in enumerate(rows):
        reused = i < 12
        events.append({"scene_id": row["scene_id"], "status": "PASS_REUSED_C5_SCREEN_AUDIT" if reused else "PASS_C5_RAW_ALL_EVENTS",
                       "event_count": 1968, "source": "C5_SCREEN_PARENT_AUDIT_REUSED" if reused else "DEV72_NEW_RAW_PARENT_RECOMPUTATION"})
    audit = {"schema": "C5_AXIS_COORDINATE_DEV72_RAW_PARENT_AUDIT_V1", "status": PASS,
             "matlab_os_exit_code": 0, "scene_count": 72, "new_scenes_event_checked": 60,
             "reused_scenes_event_audit_refs": 12, "plant_calls_in_audit": 0, "TEST_accessed": False,
             "training_steps": 0, "optimizer_steps": 0,
             "performance_gates": {"gate_a": True}, "rows": rows, "event_check_rows": events}
    checked, _ = validate_summary(audit)
    assert len(checked) == 72 and mean_q(checked, "C5") < mean_q(checked, "B")
    print("SYNTHETIC_AUDIT_ENTRY=PASS (no figure rendered)")


def render(audit, rows, parsed, input_hashes):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    assert not any(path.exists() for path in (PDF, PNG, META)), "Refusing to overwrite figure artifacts."
    plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman", "DejaVu Serif"],
                         "font.size": 7.2, "axes.labelsize": 7.2, "axes.titlesize": 8,
                         "legend.fontsize": 5.8, "xtick.labelsize": 5.8, "ytick.labelsize": 6,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "axes.grid": True, "grid.alpha": .16, "grid.linewidth": .45,
                         "savefig.dpi": 300, "pdf.fonttype": 42, "ps.fonttype": 42})
    colors = {"B": "#8A8A8A", "C3": "#0072B2", "C5": "#D55E00",
              "DEV": "#0072B2", "VAL": "#D55E00", "X": "#0072B2", "Y": "#E69F00", "Z": "#009E73"}
    fig, axes = plt.subplots(2, 2, figsize=(6.75, 5.0))
    ax_a, ax_b, ax_c, ax_d = axes.flat
    fig.subplots_adjust(left=.105, right=.985, bottom=.17, top=.94, wspace=.37, hspace=.48)

    # (a) Paired whole-window Q, same scene on both axes.
    task_colors = {1: "#0072B2", 2: "#E69F00", 3: "#009E73"}
    task_markers = {1: "o", 2: "s", 3: "^"}
    for task in (1, 2, 3):
        task_rows = [r for r in rows if parsed[r["scene_id"]][1] == task]
        good = [r for r in task_rows if r["comparison_vs_B"] != "LOSS"]
        bad = [r for r in task_rows if r["comparison_vs_B"] == "LOSS"]
        ax_a.scatter([r["B_metrics"]["Q_0_20_m"] * 1000 for r in good],
                     [r["C5_metrics"]["Q_0_20_m"] * 1000 for r in good],
                     s=15, marker=task_markers[task], color=task_colors[task], edgecolors="white", linewidths=.3,
                     alpha=.9, zorder=3)
        ax_a.scatter([r["B_metrics"]["Q_0_20_m"] * 1000 for r in bad],
                     [r["C5_metrics"]["Q_0_20_m"] * 1000 for r in bad],
                     s=20, marker=task_markers[task], facecolors="none", edgecolors=task_colors[task], linewidths=.9,
                     zorder=4)
    vals = [r[m]["Q_0_20_m"] * 1000 for r in rows for m in ("B_metrics", "C5_metrics")]
    assert all(value > 0 for value in vals)
    limits = (min(vals) * .85, max(vals) * 1.15)
    ax_a.plot(limits, limits, color="#333333", lw=.8, ls="--", zorder=1)
    ax_a.set(xlim=limits, ylim=limits, xlabel="B: Q (mm)", ylabel="C5: Q (mm)")
    ax_a.set_xscale("log")
    ax_a.set_yscale("log")
    ax_a.set_aspect("equal", adjustable="box")
    ax_a.set_title("(a) Paired scene-level Q", loc="left", pad=3)
    ax_a.legend(handles=[Line2D([], [], marker=task_markers[t], ls="", color=task_colors[t], label=f"T{t}")
                         for t in (1, 2, 3)] +
                        [Line2D([], [], marker="o", ls="", markerfacecolor="none", markeredgecolor="#333",
                                label="C5 > B", color="none")],
                loc="lower right", frameon=False, ncol=1, handletextpad=.35, borderpad=.1)

    # (b) Equal-weight scene means for the three predeclared groups.
    groups = [("ALL72", rows), ("HF_W09_W14", [r for r in rows if 9 <= parsed[r["scene_id"]][2] <= 14]),
              ("W15", [r for r in rows if parsed[r["scene_id"]][2] == 15])]
    x = np.arange(len(groups)); width = .23
    for j, method in enumerate(("B", "C3", "C5")):
        values = [mean_q(group_rows, method) * 1000 for _, group_rows in groups]
        ax_b.bar(x + (j - 1) * width, values, width=width * .9, color=colors[method], label=method,
                 edgecolor="white", linewidth=.35, zorder=3)
    ax_b.set_xticks(x, [f"{name.replace('_W09_W14', '')}\n(n={len(group_rows)})" for name, group_rows in groups])
    ax_b.set_ylabel("Mean Q (mm)")
    ax_b.set_title("(b) Equal-weight group means", loc="left", pad=3)
    ax_b.legend(loc="upper right", frameon=False, ncol=3, handlelength=1.1, columnspacing=.7)

    # (c) Every populated wind group, retaining both gains and losses.
    wind_groups = sorted({parsed[r["scene_id"]][2] for r in rows})
    wind_means = [float(np.mean([(r["C5_metrics"]["Q_0_20_m"] - r["B_metrics"]["Q_0_20_m"]) * 1000
                                 for r in rows if parsed[r["scene_id"]][2] == wind])) for wind in wind_groups]
    wind_counts = [sum(parsed[r["scene_id"]][2] == wind for r in rows) for wind in wind_groups]
    bar_colors = [colors["C5"] if value > 0 else (colors["C3"] if value < 0 else colors["B"])
                  for value in wind_means]
    ax_c.axhline(0, color="#222222", lw=.8, zorder=2)
    ax_c.bar(np.arange(len(wind_groups)), wind_means, color=bar_colors, width=.68,
             edgecolor="white", linewidth=.3, zorder=3)
    for i, (value, count) in enumerate(zip(wind_means, wind_counts)):
        ax_c.annotate(f"n={count}", (i, value), xytext=(0, 4 if value >= 0 else -9),
                      textcoords="offset points", ha="center", va="bottom" if value >= 0 else "top",
                      fontsize=5.0, clip_on=True)
    ax_c.set_xticks(np.arange(len(wind_groups)), [f"W{w:02d}" for w in wind_groups],
                    rotation=55, ha="right", fontsize=5.5)
    ax_c.set_ylabel("Mean C5 − B Q (mm)")
    ax_c.set_title("(c) Per-wind-group Q difference", loc="left", pad=3)
    ax_c.margins(y=.3)

    # (d) Axis RMSE differences; these are not combined into Q.
    comparison_groups = [("ALL72", rows), ("HF28", groups[1][1]), ("W15", groups[2][1])]
    x = np.arange(len(comparison_groups)); width = .23
    for j, axis in enumerate("xyz"):
        values = [float(np.mean([(r["C5_metrics"][f"rmse_{axis}_0_20_m"] -
                                 r["B_metrics"][f"rmse_{axis}_0_20_m"]) * 1000 for r in selected]))
                  for _, selected in comparison_groups]
        ax_d.bar(x + (j - 1) * width, values, width=width * .9, color=colors[axis.upper()],
                 label=axis.upper(), edgecolor="white", linewidth=.35, zorder=3)
    ax_d.axhline(0, color="#222222", lw=.8, zorder=2)
    ax_d.set_xticks(x, [f"{name}\n(n={len(selected)})" for name, selected in comparison_groups])
    ax_d.set_ylabel("Axis RMSE difference (mm)")
    ax_d.set_title("(d) XYZ RMSE: C5 − B", loc="left", pad=3)
    ax_d.legend(loc="upper right", frameon=False, ncol=3, handlelength=1.1, columnspacing=.7)

    script_sha = sha256(Path(__file__))
    pdf_meta = {"Title": "C5 DEV72 paired performance", "Creator": f"gen_fig_c5_dev72.py; source SHA256 {script_sha}"}
    png_meta = {"Title": "C5 DEV72 paired performance", "Description": f"Source SHA256 {script_sha}"}
    fig.savefig(PDF, format="pdf", metadata=pdf_meta)
    fig.savefig(PNG, format="png", dpi=300, metadata=png_meta)
    plt.close(fig)
    metadata = {"schema": "C5_DEV72_FIGURE_METADATA_V1", "audit_status": audit["status"],
                "source_script_sha256": script_sha, "input_sha256": input_hashes,
                "scene_count": 72, "fixed_seed": EXPECTED_SEED, "scope": "DEV_ONLY_NO_TEST",
                "pdf_path": str(PDF), "pdf_sha256": sha256(PDF),
                "png_path": str(PNG), "png_sha256": sha256(PNG)}
    META.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(metadata, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true", help="Validate synthetic audit input only; render nothing.")
    args = parser.parse_args()
    if args.self_test:
        self_test()
    else:
        audit, rows, parsed, hashes = load_inputs()
        render(audit, rows, parsed, hashes)
