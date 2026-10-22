from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_INPUT = ROOT / "experiments/paper14_v2_round3_xy_pcf_screen/reports/round3_xy_screen_results.csv"
GROUPS = {
    "W00–W08": ("W00_W08",),
    "W09–W14": ("W09_W11", "W12_W14"),
    "W15": ("W15",),
}
BAND_COLORS = {
    "W00–W08": "#4C72B0",
    "W09–W14": "#55A868",
    "W15": "#C44E52",
    "All 12": "#777777",
}
TASK_COLORS = {"T1": "#4C72B0", "T2": "#DD8452", "T3": "#55A868"}
TASK_MARKERS = {"T1": "o", "T2": "s", "T3": "^"}
TOL_M = 1e-12


def paired_delta(candidate: pd.Series, baseline: pd.Series) -> np.ndarray:
    return (candidate.astype(float) - baseline.astype(float)).to_numpy() * 1000.0


def summarize(scope: str, metric: str, baseline: np.ndarray, candidate: np.ndarray,
              delta: np.ndarray, outcomes: pd.Series | None = None) -> dict[str, object]:
    row: dict[str, object] = {
        "scope": scope,
        "metric": metric,
        "n": len(delta),
        "mean_B_mm": float(np.mean(baseline)),
        "mean_R3_mm": float(np.mean(candidate)),
        "mean_delta_R3_minus_B_mm": float(np.mean(delta)),
        "min_scene_delta_mm": float(np.min(delta)),
        "max_scene_delta_mm": float(np.max(delta)),
        "wins": "",
        "ties": "",
        "losses": "",
    }
    if outcomes is not None:
        row["wins"] = int((outcomes == "WIN").sum())
        row["ties"] = int((outcomes == "TIE").sum())
        row["losses"] = int((outcomes == "LOSS").sum())
    return row


def make_summary(df: pd.DataFrame) -> pd.DataFrame:
    q_base = df["b_q_0_20_m"].astype(float)
    q_r3 = df["xy_q_0_20_m"].astype(float)
    q_delta_m = q_r3 - q_base
    logged_delta_m = df["delta_q_xy_minus_b_m"].astype(float)
    if not np.allclose(q_delta_m, logged_delta_m, rtol=0.0, atol=1e-12):
        raise ValueError("Logged R3-B Q deltas do not match paired Q columns within 1e-12 m")
    outcome = pd.Series(np.where(q_delta_m < -TOL_M, "WIN",
                                np.where(q_delta_m > TOL_M, "LOSS", "TIE")))
    logged_outcome = df["q_outcome_xy_vs_b"].astype(str).reset_index(drop=True)
    if not np.array_equal(outcome.to_numpy(), logged_outcome.to_numpy()):
        raise ValueError("Recomputed win/tie/loss labels differ from the screen CSV")

    summary_rows: list[dict[str, object]] = []
    for label, bands in GROUPS.items():
        mask = df["band"].isin(bands)
        group = df.loc[mask].reset_index(drop=True)
        q_b = group["b_q_0_20_m"].astype(float).to_numpy() * 1000.0
        q_c = group["xy_q_0_20_m"].astype(float).to_numpy() * 1000.0
        delta = q_c - q_b
        group_outcomes = pd.Series(np.where(delta < -TOL_M * 1000, "WIN",
                                             np.where(delta > TOL_M * 1000, "LOSS", "TIE")))
        summary_rows.append(summarize(label, "Position Q (0–20 s)", q_b, q_c, delta, group_outcomes))

    all_delta = q_delta_m.to_numpy() * 1000.0
    summary_rows.append(summarize(
        "All 12", "Position Q (0–20 s)", q_base.to_numpy() * 1000.0,
        q_r3.to_numpy() * 1000.0, all_delta, outcome.reset_index(drop=True)))

    w15 = df.loc[df["band"] == "W15"]
    if len(w15) != 3:
        raise ValueError(f"Expected three W15 scenes; found {len(w15)}")
    for axis in ("x", "y", "z"):
        b = w15[f"rmse_{axis}_b_0_20_m"].astype(float).to_numpy() * 1000.0
        c = w15[f"rmse_{axis}_xy_0_20_m"].astype(float).to_numpy() * 1000.0
        delta = c - b
        summary_rows.append(summarize(f"W15 {axis.upper()}", "Axis RMSE (0–20 s)", b, c, delta))

    return pd.DataFrame(summary_rows)


def validate(df: pd.DataFrame) -> None:
    if len(df) != 12 or df["scene_id"].nunique() != 12:
        raise ValueError(f"Expected 12 unique fixed-screen scenes; got rows={len(df)} unique={df['scene_id'].nunique()}")
    counts = df["band"].value_counts().to_dict()
    if counts != {"W09_W11": 3, "W12_W14": 3, "W15": 3, "W00_W08": 3}:
        raise ValueError(f"Unexpected fixed-screen band counts: {counts}")
    for column in ("reference_position_input_elementwise_equal", "xy_safe"):
        if not df[column].astype(str).str.lower().eq("true").all():
            raise ValueError(f"Not all rows satisfy {column}=true")
    if not df["xy_status"].astype(str).eq("STABLE").all():
        raise ValueError("At least one R3 screen run is not STABLE")
    if not df["xy_identity_status"].astype(str).str.len().gt(0).all():
        raise ValueError("Missing R3 identity status")
    for column in ("xy_motor_saturated_fraction", "xy_generalized_clipped_fraction", "xy_new_tilt_limited_count"):
        if not np.allclose(df[column].astype(float), 0.0):
            raise ValueError(f"Nonzero safety/limit field in {column}")


def plot(df: pd.DataFrame, summary: pd.DataFrame, output_dir: Path) -> None:
    plt.rcParams.update({
        "font.family": "serif",
        "font.serif": ["DejaVu Serif"],
        "font.size": 8.5,
        "axes.titlesize": 9,
        "axes.titleweight": "bold",
        "axes.labelsize": 8.5,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.fontsize": 7.5,
        "legend.frameon": False,
        "figure.dpi": 300,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.alpha": 0.18,
        "grid.linestyle": ":",
        "lines.linewidth": 1.2,
        "lines.markersize": 5,
    })

    fig, (ax_q, ax_axis) = plt.subplots(
        1, 2, figsize=(7.0, 3.65), gridspec_kw={"width_ratios": [1.25, 1.0]}
    )
    fig.suptitle("R3 fixed 12-scene VAL screening (development subset)", y=0.985,
                 fontsize=10, fontweight="bold")

    labels = ["W00–W08", "W09–W14", "W15", "All 12"]
    y = {label: len(labels) - 1 - idx for idx, label in enumerate(labels)}
    group_rows = {label: df[df["band"].isin(bands)].reset_index(drop=True)
                  for label, bands in GROUPS.items()}

    for label in ("W00–W08", "W09–W14", "W15"):
        group = group_rows[label]
        q_delta = paired_delta(group["xy_q_0_20_m"], group["b_q_0_20_m"])
        offsets = np.linspace(-0.12, 0.12, len(group)) if len(group) > 1 else np.array([0.0])
        color = BAND_COLORS[label]
        yy = y[label] + offsets
        mean = float(np.mean(q_delta))
        ax_q.hlines(y[label], float(np.min(q_delta)), float(np.max(q_delta)),
                    color=color, linewidth=1.4, alpha=0.75, zorder=1)
        ax_q.scatter(q_delta, yy, s=28, color=color, edgecolor="white", linewidth=0.5,
                     zorder=3)
        ax_q.scatter([mean], [y[label]], marker="D", s=42, color="black", edgecolor="white",
                     linewidth=0.5, zorder=4)
        ax_q.annotate(f"{mean:+.3f}", (mean, y[label]), xytext=(0, 10),
                      textcoords="offset points", ha="center", va="bottom", fontsize=7.2,
                      bbox=dict(facecolor="white", edgecolor="none", pad=0.25))

    all_mean = float(summary.loc[summary["scope"] == "All 12", "mean_delta_R3_minus_B_mm"].iloc[0])
    ax_q.scatter([all_mean], [y["All 12"]], marker="D", s=42, color=BAND_COLORS["All 12"],
                 edgecolor="white", linewidth=0.5, zorder=4)
    ax_q.annotate(f"{all_mean:+.3f}", (all_mean, y["All 12"]), xytext=(0, 10),
                  textcoords="offset points", ha="center", va="bottom", fontsize=7.2,
                  bbox=dict(facecolor="white", edgecolor="none", pad=0.25))
    ax_q.axvline(0.0, color="#333333", linestyle="--", linewidth=1.0, zorder=0)
    ax_q.set_yticks([y[k] for k in labels], ["W00–W08 (n=3)", "W09–W14 (n=6)", "W15 (n=3)", "All 12 mean"])
    ax_q.set_xlabel("ΔQ (mm), R3 − B; negative is better")
    ax_q.set_title("(a) 3D position RMSE")
    ax_q.set_xlim(-5.0, 2.4)
    ax_q.set_ylim(-0.5, 3.5)
    ax_q.xaxis.grid(True)
    ax_q.yaxis.grid(False)

    w15 = df[df["band"] == "W15"].reset_index(drop=True)
    axis_y = {"X": 2, "Y": 1, "Z": 0}
    axis_colors = {"X": "#C44E52", "Y": "#4C72B0", "Z": "#55A868"}
    means = []
    for axis in ("X", "Y", "Z"):
        b = w15[f"rmse_{axis.lower()}_b_0_20_m"].astype(float).to_numpy() * 1000.0
        c = w15[f"rmse_{axis.lower()}_xy_0_20_m"].astype(float).to_numpy() * 1000.0
        delta = c - b
        offsets = np.linspace(-0.10, 0.10, len(w15))
        mean = float(np.mean(delta))
        means.append(mean)
        for idx, row in w15.iterrows():
            task = str(row["scene_id"]).split("_")[2]
            task = task[:2]
            ax_axis.scatter(delta[idx], axis_y[axis] + offsets[idx],
                            marker=TASK_MARKERS[task], color=TASK_COLORS[task], s=32,
                            edgecolor="white", linewidth=0.5, zorder=3)
        ax_axis.hlines(axis_y[axis], float(np.min(delta)), float(np.max(delta)),
                       color=axis_colors[axis], linewidth=1.2, alpha=0.65, zorder=1)
        ax_axis.scatter([mean], [axis_y[axis]], marker="D", s=42, color="black",
                        edgecolor="white", linewidth=0.5, zorder=4)

    ax_axis.axvline(0.0, color="#333333", linestyle="--", linewidth=1.0, zorder=0)
    ax_axis.set_yticks([axis_y["X"], axis_y["Y"], axis_y["Z"]], [f"X ({means[0]:+.3f})", f"Y ({means[1]:+.3f})", f"Z ({means[2]:+.3f})"])
    ax_axis.set_xlabel("ΔRMSE (mm), R3 − B; negative is better")
    ax_axis.set_title("(b) W15 per-axis RMSE (n=3)")
    ax_axis.set_xlim(-1.05, 1.55)
    ax_axis.set_ylim(-0.5, 2.75)
    ax_axis.xaxis.grid(True)
    ax_axis.yaxis.grid(False)

    task_handles = [Line2D([0], [0], marker=TASK_MARKERS[t], color="none",
                           markerfacecolor=TASK_COLORS[t], markeredgecolor="white",
                           markersize=5.5, label=f"{t} scene") for t in ("T1", "T2", "T3")]
    task_handles.append(Line2D([0], [0], marker="D", color="black", linestyle="none",
                               markersize=5.5, label="Macro mean"))
    ax_axis.legend(handles=task_handles, loc="upper left", ncol=2, columnspacing=0.8,
                   handletextpad=0.3, borderaxespad=0.15)
    fig.text(0.5, 0.005,
             "Points are paired scenes; whiskers show observed min–max, diamonds show equal-scene means. No confidence intervals are implied.",
             ha="center", va="bottom", fontsize=7.2)
    fig.tight_layout(rect=(0.01, 0.055, 0.99, 0.94), w_pad=1.7)

    output_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_dir / "fig_r3_screen_evidence.pdf", bbox_inches="tight")
    fig.savefig(output_dir / "fig_r3_screen_evidence.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot the registered R3 12-scene VAL screen from its score CSV.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--outdir", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()

    df = pd.read_csv(args.input)
    validate(df)
    summary = make_summary(df)
    args.outdir.mkdir(parents=True, exist_ok=True)
    summary.to_csv(args.outdir / "r3_screen_evidence_summary.csv", index=False, float_format="%.9f")
    plot(df, summary, args.outdir)
    sha = hashlib.sha256(args.input.read_bytes()).hexdigest()
    print(f"input={args.input.resolve()}")
    print(f"input_sha256={sha}")
    all_row = summary.loc[summary["scope"] == "All 12"].iloc[0]
    hf_row = summary.loc[summary["scope"] == "W09–W14"].iloc[0]
    w15_row = summary.loc[summary["scope"] == "W15"].iloc[0]
    print(f"rows={len(df)} unique_scenes={df['scene_id'].nunique()} wins={int(all_row['wins'])} ties={int(all_row['ties'])} losses={int(all_row['losses'])}")
    print(f"deltaQ_mm all12={all_row['mean_delta_R3_minus_B_mm']:+.6f} highfreq={hf_row['mean_delta_R3_minus_B_mm']:+.6f} W15={w15_row['mean_delta_R3_minus_B_mm']:+.6f}")
    print(f"outputs={args.outdir.resolve()}")


if __name__ == "__main__":
    main()