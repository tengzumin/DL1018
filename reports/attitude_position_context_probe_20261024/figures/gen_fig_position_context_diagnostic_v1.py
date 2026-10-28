"""Pinned two-TRAIN-scene diagnostic; does not fit a model or read TEST/raw MAT."""
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np

HERE = Path(__file__).resolve().parent
PROBE = HERE.parent


def read_pinned(path, sha):
    data = path.read_bytes()
    assert hashlib.sha256(data).hexdigest() == sha, path
    return json.loads(data.decode("utf-8-sig"))


def main():
    prefix = HERE / "fig_position_context_diagnostic_v2"
    assert not prefix.with_suffix(".pdf").exists()
    assert not prefix.with_suffix(".png").exists()
    support = read_pinned(PROBE / "ROOT_ALPHA_XY_TRAIN_SUPPORT_DIAGNOSTIC_v1.json",
        "46aacf7b2c0b643b45b7f6962230cc7b44fe74035e8843479fa9e808a04a9173")
    evaluation = read_pinned(PROBE / "frozen_a1_evaluation_v1/ROOT_FROZEN_A1_EVALUATION_v1.json",
        "2631153d3a8e502923617e4de098c8556ffdaa1d80a5e7138fd16e5637968f97")
    bound = support["train_support"]["full_1999_event_support"]
    lo, hi = np.array(bound["min"]), np.array(bound["max"])
    plt.rcParams.update({"font.family": "serif", "font.size": 9,
        "pdf.fonttype": 42, "ps.fonttype": 42, "axes.spines.top": False,
        "axes.spines.right": False, "legend.frameon": False})
    fig, axes = plt.subplots(2, 2, figsize=(7, 6), layout="constrained")
    colors = {"B": "#0072B2", "C5": "#D55E00"}
    for col, task in enumerate(("T1", "T3")):
        ax = axes[0, col]
        ax.add_patch(Rectangle(lo, *(hi-lo), facecolor="0.94", edgecolor="0.35",
            linestyle="--", linewidth=1, label="Old TRAIN marginal bounds"))
        for mode, marker in (("C5", "."), ("B", "x")):
            flight = f"{task}_{mode}"
            info = evaluation["raw_event_exports"][flight]
            events = read_pinned(PROBE / "offline_events_v2" / f"events_{flight}_v2.json",
                info["file_sha256"])
            xy = np.array(events["X18"], dtype=float)[:, 3:5]
            assert xy.shape == (1999, 2)
            outside = np.any((xy < lo) | (xy > hi), axis=1).sum()
            expected = support["probe_scenes"][flight]["against_full_train_1999_support"]["outside_any_axis_event_count"]
            assert outside == expected
            ax.scatter(*xy.T, s=5 if mode == "C5" else 7, marker=marker,
                alpha=.45 if mode == "C5" else .7, color=colors[mode],
                label=f"{mode} position: {outside}/1999 outside", rasterized=True)
        ax.set(xlim=(-33, 33), ylim=(-33, 35), aspect="equal",
            xlabel=r"$\alpha_{BS,x}$ (rad s$^{-2}$)",
            ylabel=r"$\alpha_{BS,y}$ (rad s$^{-2}$)", title=f"{task}, C15, W14")
        ax.legend(loc="upper left" if col == 0 else "lower left", fontsize=6.5)
        ax = axes[1, col]
        for offset, mode in ((-.18, "B"), (.18, "C5")):
            values = evaluation["flight_metrics"][f"{task}_{mode}"]["all_event_prediction"]["axis_rmse_rad_s2"]
            ax.bar(np.arange(3)+offset, values, width=.34, color=colors[mode], label=f"{mode} position")
        ax.set(xticks=np.arange(3), xticklabels=["Roll", "Pitch", "Yaw"], ylim=(0, 1.7),
            ylabel=r"Frozen A1 residual RMSE (rad s$^{-2}$)")
        ax.grid(axis="y", alpha=.2)
        ax.legend(fontsize=7)
    fig.suptitle("Position-context transfer: two fixed TRAIN diagnostic scenes", fontsize=11)
    fig.savefig(prefix.with_suffix(".pdf"), bbox_inches="tight")
    fig.savefig(prefix.with_suffix(".png"), dpi=300, bbox_inches="tight")
    plt.close(fig)
    print("FIGURE_PASS: pinned sources; 4 x 1999 events; counts recomputed; no TEST or fitting")


if __name__ == "__main__":
    main()
