#!/usr/bin/env python3
"""Reproducibly render the matched C5 ablation figure from frozen summary/CSV inputs."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE.parents[1] / "c5_matched_ablation_dev72_parent_review"
SUMMARY_PATH = DATA_DIR / "MATCHED_ABLATION_DEV72_INDEPENDENT_SUMMARY_v1.json"
PAIRS_PATH = DATA_DIR / "MATCHED_ABLATION_DEV72_ALL_PAIRS_v1.csv"
EXPECTED_INPUT_SHA256 = {
    SUMMARY_PATH.name: "71b5b437b4d2515ef9abf1fa8ab19379a9e6e5520813ca5b499caed749fab9bd",
    PAIRS_PATH.name: "9ad962499032826a31ee0f4c3b424ec45793272f411314ab6c35d3356e34e49b",
}

FIG_PDF = HERE / "fig_c5_matched_ablation_v1.pdf"
FIG_PNG = HERE / "fig_c5_matched_ablation_v1.png"
METADATA_PATH = HERE / "FIGURE_METADATA_v1.json"
CAPTION_PATH = HERE / "CAPTION_ZH_v1.md"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_inputs() -> dict[str, dict[str, object]]:
    verified: dict[str, dict[str, object]] = {}
    for path in (SUMMARY_PATH, PAIRS_PATH):
        actual = sha256(path)
        expected = EXPECTED_INPUT_SHA256[path.name]
        if actual != expected:
            raise RuntimeError(
                f"Input SHA-256 mismatch for {path.name}: expected {expected}, got {actual}"
            )
        verified[path.name] = {
            "path_from_figure_directory": f"../../c5_matched_ablation_dev72_parent_review/{path.name}",
            "sha256": actual,
            "verified": True,
        }
    return verified


def load_inputs() -> tuple[dict[str, object], list[dict[str, str]]]:
    with SUMMARY_PATH.open("r", encoding="utf-8") as handle:
        summary = json.load(handle)
    if summary.get("status") != "PASS_INDEPENDENT_ALL_GROUP_RECOMPUTATION":
        raise RuntimeError(f"Unexpected summary status: {summary.get('status')}")
    if summary.get("paired_csv_SHA256", "").lower() != EXPECTED_INPUT_SHA256[PAIRS_PATH.name]:
        raise RuntimeError("Summary's paired_csv_SHA256 does not match the locked CSV input")
    if summary.get("raw_read") is not False or summary.get("TEST_accessed") is not False:
        raise RuntimeError("Input summary does not carry the expected no-raw/no-TEST flags")

    with PAIRS_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 144:
        raise RuntimeError(f"Expected 144 paired rows, got {len(rows)}")
    return summary, rows


def group_q_mm(summary: dict[str, object], group: str, method_key: str) -> float:
    variant_key = method_key if method_key in summary["variants"] else "C5_FREEZE_TRAINED_W0"
    metrics = summary["variants"][variant_key][group]["scene_equal_mean_metrics"]
    return float(metrics[method_key]["Q_0_20_m"]) * 1000.0


def main() -> None:
    input_hashes = verify_inputs()
    summary, pair_rows = load_inputs()

    no_pred_rows = [row for row in pair_rows if row["variant"] == "C5_NO_DELAYED_PREDICTION"]
    if len(no_pred_rows) != 72 or len({row["scene_id"] for row in no_pred_rows}) != 72:
        raise RuntimeError("NO_PRED input must contain exactly 72 unique paired scenes")
    if {task: sum(row["task"] == task for row in no_pred_rows) for task in ("T1", "T2", "T3")} != {
        "T1": 24, "T2": 24, "T3": 24
    }:
        raise RuntimeError("Unexpected task counts in NO_PRED paired rows")

    # The stored summary CIs are consumed verbatim below; this script does not resample them.
    bootstrap = {
        "seed": summary["bootstrap_seed"],
        "replicates": summary["bootstrap_replicates"],
        "unit": summary["bootstrap_unit"],
        "scope": summary["interval_scope"],
        "ci_source": "stored JSON field C5_minus_ablation_Q_95pct_scene_bootstrap_m",
        "ci_recomputed": False,
    }
    no_pred_summary = summary["variants"]["C5_NO_DELAYED_PREDICTION"]
    task_stats: dict[str, dict[str, object]] = {}
    for task in ("T1", "T2", "T3"):
        record = no_pred_summary[task]
        mean_mm = float(record["C5_minus_ablation_Q_m"]) * 1000.0
        ci_mm = [float(value) * 1000.0 for value in record["C5_minus_ablation_Q_95pct_scene_bootstrap_m"]]
        task_stats[task] = {
            "n": int(record["n"]),
            "mean_mm": mean_mm,
            "ci95_mm": ci_mm,
            "wins_losses_ties_from_saved_summary": record["C5_vs_ablation"],
        }
    if not (task_stats["T2"]["ci95_mm"][0] < 0 < task_stats["T2"]["ci95_mm"][1]):
        raise RuntimeError("Stored T2 paired interval is expected to cross zero")

    delta_m = np.array([float(row["C5_minus_ablation_Q_m"]) for row in no_pred_rows])
    reverse_mask = delta_m > 1e-12  # C5 has larger Q, so this scene favors NO_PRED.
    reverse_count = int(reverse_mask.sum())
    if reverse_count != 18:
        raise RuntimeError(f"Expected 18 reverse points (C5 worse), got {reverse_count}")
    delta_mm = delta_m * 1000.0

    # Publication-style serif text with TrueType embedding in the vector PDF.
    plt.rcParams.update({
        "font.family": "serif",
        "font.serif": ["Times New Roman", "DejaVu Serif"],
        "font.size": 8.5,
        "axes.titlesize": 9.5,
        "axes.titleweight": "bold",
        "axes.labelsize": 8.5,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.fontsize": 7.2,
        "legend.frameon": False,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.alpha": 0.18,
        "grid.linewidth": 0.55,
        "grid.linestyle": "-",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "axes.axisbelow": True,
    })

    palette = {
        "B": "#7A7A7A",
        "Frozen W0": "#E69F00",
        "NoPred": "#56B4E9",
        "C5": "#009E73",
        "T1": "#0072B2",
        "T2": "#D55E00",
        "T3": "#009E73",
        "reverse": "#CC3311",
    }
    group_defs = [
        ("ALL72", "All scenes\n(n=72)"),
        ("HF_W09_W14", "High-frequency wind\n(W09–W14; n=28)"),
        ("W15", "No wind\n(W15; n=6)"),
    ]
    method_defs = [
        ("B_TRACEABLE", "B", palette["B"]),
        ("C5_FREEZE_TRAINED_W0", "Frozen W0", palette["Frozen W0"]),
        ("C5_NO_DELAYED_PREDICTION", "NoPred", palette["NoPred"]),
        ("C5_M110", "C5", palette["C5"]),
    ]

    fig, (ax_bar, ax_pair) = plt.subplots(
        1, 2, figsize=(10.0, 4.1), gridspec_kw={"width_ratios": [1.08, 1.18]}
    )

    # Panel (a): group means taken directly from the frozen summary JSON.
    x = np.arange(len(group_defs), dtype=float)
    bar_width = 0.18
    offsets = (np.arange(len(method_defs)) - (len(method_defs) - 1) / 2.0) * bar_width
    for method_index, (method_key, label, color) in enumerate(method_defs):
        values = [group_q_mm(summary, group_key, method_key) for group_key, _ in group_defs]
        bars = ax_bar.bar(
            x + offsets[method_index], values, width=bar_width * 0.9,
            label=label, color=color, edgecolor="white", linewidth=0.55, zorder=3,
        )
        for bar, value in zip(bars, values):
            ax_bar.text(
                bar.get_x() + bar.get_width() / 2.0,
                bar.get_height() + 0.42,
                f"{value:.1f}",
                ha="center", va="bottom", fontsize=6.7, color="#333333",
            )
    ax_bar.set_xticks(x, [label for _, label in group_defs])
    ax_bar.set_ylabel("Q (mm; lower is better)")
    ax_bar.set_ylim(0, 42)
    ax_bar.set_title("(a) Equal-scene group means", loc="left", pad=8)
    ax_bar.grid(axis="y")
    ax_bar.grid(axis="x", visible=False)
    ax_bar.legend(loc="upper left", ncol=2, columnspacing=1.0, handlelength=1.2)

    # Panel (b): all 72 paired differences; only display jitter is generated here.
    task_order = ("T1", "T2", "T3")
    task_x = {task: i for i, task in enumerate(task_order)}
    rng = np.random.default_rng(20261023)  # deterministic horizontal display jitter only
    jitter_by_scene = {row["scene_id"]: float(rng.uniform(-0.17, 0.17)) for row in no_pred_rows}
    x_point = np.array([task_x[row["task"]] + jitter_by_scene[row["scene_id"]] for row in no_pred_rows])
    task_array = np.array([row["task"] for row in no_pred_rows])
    marker_by_task = {"T1": "o", "T2": "s", "T3": "^"}
    for task in task_order:
        mask = task_array == task
        ax_pair.scatter(
            x_point[mask], delta_mm[mask], s=22, marker=marker_by_task[task],
            c=palette[task], alpha=0.84, linewidths=0.35, edgecolors="white",
            zorder=3,
        )
    ax_pair.scatter(
        x_point[reverse_mask], delta_mm[reverse_mask], s=56, marker="o",
        facecolors="none", edgecolors=palette["reverse"], linewidths=1.25,
        label="C5 worse (n=18)", zorder=4,
    )
    ax_pair.axhline(0.0, color="#333333", linewidth=0.9, linestyle=(0, (3, 2)), zorder=2)

    mean_x_offset = 0.255
    for task_index, task in enumerate(task_order):
        mean = task_stats[task]["mean_mm"]
        ci_low, ci_high = task_stats[task]["ci95_mm"]
        ax_pair.errorbar(
            task_index + mean_x_offset, mean,
            yerr=np.array([[mean - ci_low], [ci_high - mean]]),
            fmt="D", markersize=4.1, color="#222222", ecolor="#222222",
            elinewidth=1.05, capsize=2.6, capthick=0.9,
            label="Mean and stored 95% CI" if task_index == 0 else None,
            zorder=5,
        )
        label = f"{mean:+.3f} [{ci_low:+.3f}, {ci_high:+.3f}]"
        ax_pair.text(task_index, 1.46, label, ha="center", va="top", fontsize=6.7, color="#333333")
    ax_pair.text(
        1.0, 1.11, "T2 interval crosses 0", ha="center", va="top",
        fontsize=7.0, color=palette["reverse"], fontweight="bold",
    )
    ax_pair.set_xticks([0, 1, 2], ["T1 (n=24)", "T2 (n=24)", "T3 (n=24)"])
    ax_pair.set_xlim(-0.5, 2.55)
    ax_pair.set_ylim(-2.22, 1.72)
    ax_pair.set_ylabel(r"$Q_{C5}-Q_{NoPred}$ (mm; lower favors C5)")
    ax_pair.set_title("(b) Paired scene differences", loc="left", pad=8)
    ax_pair.grid(axis="y")
    ax_pair.grid(axis="x", visible=False)
    ax_pair.legend(
        loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=2,
        columnspacing=1.0, handletextpad=0.5, fontsize=6.8,
    )

    fig.subplots_adjust(left=0.07, right=0.99, top=0.89, bottom=0.19, wspace=0.27)
    fig.savefig(
        FIG_PDF,
        format="pdf",
        metadata={"Title": "Matched C5 ablations on DEV72", "Creator": "Matplotlib", "CreationDate": None, "ModDate": None},
    )
    fig.savefig(FIG_PNG, format="png", dpi=300, metadata={"Software": "Matplotlib"})
    plt.close(fig)

    methods_by_group = {
        group_key: {
            label: group_q_mm(summary, group_key, method_key)
            for method_key, label, _ in method_defs
        }
        for group_key, _ in group_defs
    }
    metadata = {
        "schema": "C5_MATCHED_ABLATION_FIGURE_METADATA_V1",
        "script": {"path": Path(__file__).name, "sha256": sha256(Path(__file__).resolve())},
        "inputs": input_hashes,
        "inputs_flags_from_summary": {
            "raw_read": summary["raw_read"],
            "Plant_started": summary["Plant_started"],
            "TEST_accessed": summary["TEST_accessed"],
        },
        "figure": {
            "panel_a_group_mean_q_mm": methods_by_group,
            "panel_b_delta_definition": "C5_minus_NO_PRED_Q_0_20_m, converted from m to mm; negative favors C5 and positive favors NO_PRED",
            "panel_b_points": len(no_pred_rows),
            "panel_b_reverse_points_c5_worse": reverse_count,
            "panel_b_reverse_count_by_task": {
                task: int(sum((row["task"] == task) and (float(row["C5_minus_ablation_Q_m"]) > 1e-12) for row in no_pred_rows))
                for task in task_order
            },
            "panel_b_task_means_and_saved_ci_mm": task_stats,
            "paired_bootstrap": bootstrap,
            "display_jitter": {"seed": 20261023, "purpose": "horizontal scatter separation only", "used_for_statistics": False},
            "pdf_true_type_font_setting": {"pdf.fonttype": 42, "font_family": "Times New Roman / DejaVu Serif"},
            "png_dpi": 300,
        },
        "outputs": {
            FIG_PDF.name: {"sha256": sha256(FIG_PDF), "bytes": FIG_PDF.stat().st_size},
            FIG_PNG.name: {"sha256": sha256(FIG_PNG), "bytes": FIG_PNG.stat().st_size, "dpi": 300},
            CAPTION_PATH.name: {"sha256": sha256(CAPTION_PATH), "bytes": CAPTION_PATH.stat().st_size},
        },
    }
    METADATA_PATH.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {FIG_PDF}")
    print(f"Saved {FIG_PNG}")
    print(f"Saved {METADATA_PATH}")


if __name__ == "__main__":
    main()
