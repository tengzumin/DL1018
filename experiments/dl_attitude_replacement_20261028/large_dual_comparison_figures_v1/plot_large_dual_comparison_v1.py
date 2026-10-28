#!/usr/bin/env python3
"""Plot paired B/C5/frozen-gate/new-B768 comparisons from frozen scene scores.

The frozen 72-scene source is read-only. New B768 scores are joined by scene_id;
when present, every method in the figure is aggregated over that same scene set.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator


ROOT = Path(__file__).resolve().parents[3]
TASK_DIR = ROOT / "experiments" / "dl_attitude_replacement_20261028"
OUT_DIR = Path(__file__).resolve().parent
FROZEN_FILES = (
    TASK_DIR / "causal_n4_gate_train24_batch_v2" / "TRAIN24_SCORE_SUMMARY_v2.json",
    TASK_DIR / "cg48_v2" / "VAL48_SCORE_SUMMARY_v2.json",
)
NEW_CSV_ROOT = TASK_DIR / "large_gru_b768_v1" / "paired_results"
CURRENT_BASE_VARIANT = {
    "model_sha256": "4f0724426244d58e283da3f1ebbf6a01a9b39b02d2280eaaa22796eee8f1fd6b",
    "scorecard_key": "GRU13_B768_COSINE_S2026102001_N4_bd0dcbfef266f66d",
    "runner_identity_sha256": "cd57b462bcb2dd5345bb63b6d5a84892e4aecc4f0945eb986a278d50379b2a2b",
    "numeric_config_sha256": "9218ddc704b4cd5f19ed51a54e9b243de8fb6d4904c5aa0d95101e11e686ca16",
}
VARIANT_FIELDS = tuple(CURRENT_BASE_VARIANT)

METRICS = {
    "Q_m": {"label": "Q", "native_unit": "m", "plot_unit": "mm", "scale": 1000.0},
    "task_SO3_rad": {
        "label": "Task attitude",
        "native_unit": "rad",
        "plot_unit": "deg",
        "scale": 180.0 / math.pi,
    },
    "inner_SO3_rad": {
        "label": "Inner attitude",
        "native_unit": "rad",
        "plot_unit": "deg",
        "scale": 180.0 / math.pi,
    },
}
METHODS = ("B", "C5", "frozen_gateN4_72", "new_GRU_B768_N4")
METHOD_LABELS = {
    "B": "B",
    "C5": "C5",
    "frozen_gateN4_72": "Frozen\ndual loop",
    "new_GRU_B768_N4": "Large-data\ndual loop",
}
METHOD_COLORS = {
    "B": "#0072B2",                    # Okabe-Ito blue
    "C5": "#E69F00",                   # Okabe-Ito orange
    "frozen_gateN4_72": "#009E73",     # Okabe-Ito green
    "new_GRU_B768_N4": "#D55E00",      # Okabe-Ito vermillion
}


def _number(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def load_frozen() -> tuple[dict[str, dict[str, Any]], list[Path]]:
    """Return validated scene-level frozen metrics, without touching source files."""
    scenes: dict[str, dict[str, Any]] = {}
    for path in FROZEN_FILES:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for item in payload["scenes"]:
            scene_id = str(item["scene_id"])
            if scene_id in scenes:
                raise ValueError(f"Duplicate frozen scene_id: {scene_id}")
            metrics: dict[str, dict[str, float]] = {}
            for metric in METRICS:
                source_values = item[metric]
                metrics[metric] = {
                    "B": float(source_values["B"]),
                    "C5": float(source_values["C5"]),
                    # In these immutable summaries, candidate is the old frozen dual-loop.
                    "frozen_gateN4_72": float(source_values["candidate"]),
                }
            scenes[scene_id] = {
                "scene_id": scene_id,
                "task": str(item["task"]),
                "wind_code": str(item["wind_code"]),
                "HF_W09_W14": _as_bool(item["HF_W09_W14"]),
                "metrics": metrics,
            }
    if len(scenes) != 72:
        raise ValueError(f"Expected 72 frozen scenes from TRAIN24+VAL48, found {len(scenes)}")
    return scenes, list(FROZEN_FILES)


def _is_new_method(value: Any) -> bool:
    return str(value or "").strip().lower() == "new_gru_b768_n4"


def find_new_csvs(explicit: str | None, variant_root: str | None) -> tuple[list[Path], bool]:
    if explicit and variant_root:
        raise ValueError("Use only one of --new-csv and --variant-root")
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"New-model paired CSV not found: {path}")
        return [path], True
    if variant_root:
        root = Path(variant_root).expanduser()
        if not root.is_absolute():
            root = (Path.cwd() / root).resolve()
        if not root.is_dir():
            raise FileNotFoundError(f"Variant root is not a directory: {root}")
        paths = sorted(root.rglob("paired_metrics_v1.csv"))
        if not paths:
            raise FileNotFoundError(f"No paired_metrics_v1.csv found under variant root: {root}")
        return paths, True
    if not NEW_CSV_ROOT.exists():
        return [], False
    paths = list(NEW_CSV_ROOT.rglob("paired_metrics_v1.csv"))
    return sorted(paths, key=lambda p: str(p).lower()), False


def _score_identity(csv_path: Path, row: dict[str, str], scene_id: str) -> dict[str, str]:
    identity = {field: str(row.get(field, "")).strip() for field in VARIANT_FIELDS}
    score_path = csv_path.parent / "scores" / f"{scene_id}.json"
    if score_path.is_file():
        score = json.loads(score_path.read_text(encoding="utf-8-sig"))
        candidate_identity = score.get("candidate_model_identity", {})
        new_candidate = candidate_identity.get("new_candidate", {})
        from_score = {
            "model_sha256": str(score.get("candidate_model_sha256") or new_candidate.get("model_sha256") or ""),
            "scorecard_key": str(candidate_identity.get("scorecard_key") or ""),
            "runner_identity_sha256": str(candidate_identity.get("runner_identity_sha256") or ""),
            "numeric_config_sha256": str(candidate_identity.get("numeric_config_sha256") or ""),
        }
        if str(score.get("scene_id", "")) != scene_id:
            raise ValueError(f"Score sidecar scene_id mismatch: {score_path}")
        if row.get("phase") and score.get("phase") != row["phase"]:
            raise ValueError(f"CSV/score sidecar phase mismatch for {scene_id}: {csv_path}")
        for field, value in from_score.items():
            if identity[field] and value and identity[field] != value:
                raise ValueError(f"CSV/score sidecar {field} mismatch for {scene_id}: {csv_path}")
            if not identity[field]:
                identity[field] = value
        score_values = score.get("scores", {}).get("new_GRU_B768_N4", {})
        for metric in METRICS:
            row_value, score_value = _number(row.get(metric)), _number(score_values.get(metric))
            if row_value is not None and score_value is not None and not math.isclose(
                row_value, score_value, rel_tol=1e-12, abs_tol=1e-12
            ):
                raise ValueError(f"CSV/score sidecar {metric} mismatch for {scene_id}: {csv_path}")
    if not identity["model_sha256"]:
        raise ValueError(f"Missing new-candidate model_sha256 for {scene_id}: {csv_path}")
    return identity


def load_new_scores(
    paths: list[Path], explicit_scope: bool = False
) -> tuple[dict[str, dict[str, float]], dict[str, str]]:
    new: dict[str, dict[str, float]] = {}
    raw_by_scene: dict[str, str] = {}
    variant: dict[str, str] = {}
    for path in paths:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                if not _is_new_method(row.get("method")):
                    continue
                scene_id = str(row.get("scene_id", "")).strip()
                if not scene_id:
                    continue
                identity = _score_identity(path, row, scene_id)
                missing = [field for field in VARIANT_FIELDS if not identity.get(field)]
                if missing and not explicit_scope:
                    raise ValueError(
                        f"Cannot prove B768 variant identity in {path} ({scene_id}); missing {missing}. "
                        "Use --new-csv or --variant-root to select one fixed queue."
                    )
                for field, value in identity.items():
                    if not value:
                        continue
                    if field in variant and variant[field] != value:
                        raise ValueError(
                            f"Mixed B768 variants in comparison inputs: {field} differs "
                            f"({variant[field]} vs {value}); select one queue with --new-csv or --variant-root."
                        )
                    variant[field] = value
                values = {metric: _number(row.get(metric)) for metric in METRICS}
                # Use a scene only if all three metrics exist, keeping the six panels paired.
                if any(value is None for value in values.values()):
                    continue
                current = {metric: float(values[metric]) for metric in METRICS}
                raw_sha = str(row.get("raw_sha256", "")).strip()
                if scene_id in new:
                    same_scores = all(math.isclose(new[scene_id][m], current[m], rel_tol=1e-12, abs_tol=1e-12)
                                      for m in METRICS)
                    old_raw = raw_by_scene[scene_id]
                    if not same_scores or (old_raw and raw_sha and old_raw != raw_sha):
                        raise ValueError(
                            f"Conflicting duplicate scene result for {scene_id} under one B768 variant; "
                            "select one fixed queue with --new-csv or --variant-root."
                        )
                    continue
                new[scene_id] = current
                raw_by_scene[scene_id] = raw_sha
    if new and not explicit_scope and variant != CURRENT_BASE_VARIANT:
        differing = {key: (CURRENT_BASE_VARIANT[key], variant.get(key)) for key in VARIANT_FIELDS
                     if variant.get(key) != CURRENT_BASE_VARIANT[key]}
        raise ValueError(
            "Auto-discovered B768 results are not the pinned current base variant "
            f"{CURRENT_BASE_VARIANT['scorecard_key']}: {differing}. "
            "Use --new-csv or --variant-root to select one fixed variant explicitly."
        )
    return new, variant


def _plot_value(metric: str, value: float) -> float:
    return value * METRICS[metric]["scale"]


def write_scene_csv(
    destination: Path,
    status: str,
    source_label: str,
    frozen: dict[str, dict[str, Any]],
    new: dict[str, dict[str, float]],
    included_scene_ids: list[str],
    variant: dict[str, str],
) -> None:
    fields = [
        "status", "comparison_set", "scene_id", "task", "wind_code", "HF_W09_W14",
        "method", "metric", "value_native", "native_unit", "plot_value", "plot_unit", "source",
        "variant_model_sha256", "scorecard_key", "runner_identity_sha256", "numeric_config_sha256",
    ]
    with destination.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for scene_id in included_scene_ids:
            scene = frozen[scene_id]
            for method in METHODS:
                if method == "new_GRU_B768_N4":
                    if scene_id not in new:
                        continue
                    values = new[scene_id]
                    source = source_label
                else:
                    values = scene["metrics"]
                    source = "frozen TRAIN24+VAL48 summary"
                for metric, info in METRICS.items():
                    value = values[metric] if method == "new_GRU_B768_N4" else values[metric][method]
                    writer.writerow({
                        "status": status,
                        "comparison_set": "frozen_baseline_72" if status == "pending" else "same_scene_intersection",
                        "scene_id": scene_id,
                        "task": scene["task"],
                        "wind_code": scene["wind_code"],
                        "HF_W09_W14": int(scene["HF_W09_W14"]),
                        "method": method,
                        "metric": metric,
                        "value_native": f"{value:.12g}",
                        "native_unit": info["native_unit"],
                        "plot_value": f"{_plot_value(metric, value):.12g}",
                        "plot_unit": info["plot_unit"],
                        "source": source,
                        "variant_model_sha256": variant.get("model_sha256", ""),
                        "scorecard_key": variant.get("scorecard_key", ""),
                        "runner_identity_sha256": variant.get("runner_identity_sha256", ""),
                        "numeric_config_sha256": variant.get("numeric_config_sha256", ""),
                    })


def build_long_values(
    frozen: dict[str, dict[str, Any]],
    new: dict[str, dict[str, float]],
    included_scene_ids: list[str],
) -> dict[tuple[str, str, str], list[float]]:
    """Index values by (scope, metric, method), already restricted to paired scenes."""
    values: dict[tuple[str, str, str], list[float]] = {}
    scopes: dict[str, list[str]] = {
        "overall": included_scene_ids,
        "HF_W09_W14": [sid for sid in included_scene_ids if frozen[sid]["HF_W09_W14"]],
    }
    for task in ("T1", "T2", "T3"):
        scopes[f"task_{task}"] = [sid for sid in included_scene_ids if frozen[sid]["task"] == task]
    for scope, scene_ids in scopes.items():
        for metric in METRICS:
            for method in METHODS:
                sample: list[float] = []
                for scene_id in scene_ids:
                    if method == "new_GRU_B768_N4":
                        if scene_id in new:
                            sample.append(_plot_value(metric, new[scene_id][metric]))
                    else:
                        sample.append(_plot_value(metric, frozen[scene_id]["metrics"][metric][method]))
                values[(scope, metric, method)] = sample
    return values


def write_summary_csv(destination: Path, values: dict[tuple[str, str, str], list[float]], status: str) -> None:
    fields = ["status", "scope", "metric", "method", "n_scenes", "mean", "sd", "unit"]
    with destination.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for scope in ("overall", "HF_W09_W14", "task_T1", "task_T2", "task_T3"):
            for metric, info in METRICS.items():
                for method in METHODS:
                    sample = values[(scope, metric, method)]
                    writer.writerow({
                        "status": status,
                        "scope": scope,
                        "metric": metric,
                        "method": method,
                        "n_scenes": len(sample),
                        "mean": f"{statistics.mean(sample):.12g}" if sample else "",
                        "sd": f"{statistics.stdev(sample):.12g}" if len(sample) > 1 else "",
                        "unit": info["plot_unit"],
                    })


def plot_comparison(
    destination_png: Path,
    destination_pdf: Path,
    values: dict[tuple[str, str, str], list[float]],
    included_scene_ids: list[str],
    frozen: dict[str, dict[str, Any]],
    status: str,
    new_paths: list[Path],
    variant: dict[str, str],
) -> None:
    plt.rcParams.update({
        "font.family": "serif",
        "font.serif": ["Times New Roman", "DejaVu Serif"],
        "font.size": 9,
        "axes.titlesize": 10,
        "axes.titleweight": "bold",
        "axes.labelsize": 9,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "figure.dpi": 300,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.alpha": 0.20,
        "grid.linestyle": "-",
        "axes.axisbelow": True,
    })
    fig, axes = plt.subplots(2, 3, figsize=(14.4, 8.0), sharex=True)
    fig.subplots_adjust(top=0.81, bottom=0.15, left=0.085, right=0.99, wspace=0.27, hspace=0.48)
    if status == "pending":
        title = "Frozen 72-scene baseline | New B768 dual-loop pending"
        title_color = "#A33B20"
    elif status == "full":
        title = "Paired comparison | FULL 72/72 scenes"
        title_color = "#1B6E53"
    else:
        title = f"Paired comparison | PARTIAL {len(included_scene_ids)}/72 scenes"
        title_color = "#9B6B13"
    fig.suptitle(title, y=0.965, fontsize=15, fontweight="bold", color=title_color)
    if status == "pending":
        subtitle = "Frozen B, C5, and Gate N4 means use all 72 scenes. No B768 score is available yet."
    else:
        subtitle = "All methods use the same-scene intersection; panels show mean error with per-scene SD whiskers."
    fig.text(0.5, 0.925, subtitle, ha="center", va="center", fontsize=9.3, color="#3D4650")

    scope_titles = ("Overall", "HF winds W09–W14")
    scope_keys = ("overall", "HF_W09_W14")
    metric_keys = tuple(METRICS)
    all_n = len(included_scene_ids)
    hf_n = sum(1 for sid in included_scene_ids if frozen[sid]["HF_W09_W14"])

    for row, (scope_title, scope) in enumerate(zip(scope_titles, scope_keys)):
        for col, metric in enumerate(metric_keys):
            ax = axes[row, col]
            metric_info = METRICS[metric]
            panel_values = {method: values[(scope, metric, method)] for method in METHODS}
            panel_n = all_n if scope == "overall" else hf_n
            ax.set_title(f"{scope_title}  (N={panel_n})\n{metric_info['label']}", pad=8)
            ax.set_ylabel(f"Mean error ({metric_info['plot_unit']})")
            ax.yaxis.set_major_locator(MaxNLocator(nbins=5, min_n_ticks=3))

            if panel_n == 0:
                ax.set_ylim(0, 1)
                ax.text(0.5, 0.52, "No paired scenes in this subset", transform=ax.transAxes,
                        ha="center", va="center", color="#5A626C", fontsize=9)
                ax.set_xticks(range(len(METHODS)), [METHOD_LABELS[m] for m in METHODS])
                continue

            for x, method in enumerate(METHODS):
                sample = panel_values[method]
                if not sample:
                    if method == "new_GRU_B768_N4":
                        ax.text(x, 0.53, "pending", transform=ax.get_xaxis_transform(),
                                ha="center", va="center", color=METHOD_COLORS[method],
                                fontsize=8.3, fontweight="bold", rotation=90)
                    continue
                mean_value = statistics.mean(sample)
                sd_value = statistics.stdev(sample) if len(sample) > 1 else 0.0
                ax.bar(
                    x, mean_value, width=0.62, color=METHOD_COLORS[method],
                    edgecolor="white", linewidth=0.7, alpha=0.92, zorder=3,
                )
                if len(sample) > 1:
                    ax.errorbar(x, mean_value, yerr=sd_value, fmt="none", ecolor="#263238",
                                elinewidth=0.9, capsize=2.6, capthick=0.9, zorder=4)
                # Keep exact sample count visible in every panel.
                ax.text(x, mean_value + sd_value + max(mean_value, 1e-9) * 0.035,
                        f"{mean_value:.2f}", ha="center", va="bottom", fontsize=7.2, color="#343A40")

            plotted_tops = [
                statistics.mean(sample) + (statistics.stdev(sample) if len(sample) > 1 else 0.0)
                for sample in panel_values.values() if sample
            ]
            if plotted_tops:
                ax.set_ylim(bottom=0, top=max(plotted_tops) * 1.22)
            ax.set_xticks(range(len(METHODS)), [METHOD_LABELS[m] for m in METHODS])
            ax.grid(axis="x", visible=False)

    base_note = (
        "Bars: per-scene mean; whiskers: sample SD. Q is converted m→mm; SO(3) errors rad→deg. "
        "Frozen dual loop maps to ‘candidate’ in the immutable TRAIN24/VAL48 summaries."
    )
    method_note = (
        "Large-data dual loop: TRAIN768 with the B teacher; ‘B768’ describes the data/teacher setup, not a GRU architecture."
    )
    if new_paths:
        new_source_note = " Variant: " + variant.get("scorecard_key", variant.get("model_sha256", "explicit queue")) + "."
    else:
        new_source_note = " New-score CSV: not present."
    fig.text(0.5, 0.063, base_note, ha="center", va="center", fontsize=7.3, color="#4A535D", wrap=True)
    fig.text(0.5, 0.035, method_note + new_source_note, ha="center", va="center", fontsize=7.3, color="#4A535D", wrap=True)

    fig.savefig(destination_png, dpi=300, facecolor="white")
    fig.savefig(destination_pdf, facecolor="white")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument("--new-csv", help="use one fixed paired_metrics_v1.csv queue")
    inputs.add_argument("--variant-root", help="use CSVs below one fixed variant queue directory")
    parser.add_argument("--output-dir", help="output folder; defaults to this script's directory")
    args = parser.parse_args()
    output_dir = Path(args.output_dir).expanduser() if args.output_dir else OUT_DIR
    if not output_dir.is_absolute():
        output_dir = (Path.cwd() / output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    frozen, _ = load_frozen()
    new_paths, explicit_scope = find_new_csvs(args.new_csv, args.variant_root)
    new, variant = load_new_scores(new_paths, explicit_scope=explicit_scope)
    baseline_ids = list(frozen)
    if new:
        included = [scene_id for scene_id in baseline_ids if scene_id in new]
        status = "full" if len(included) == 72 else "partial"
        variant_name = variant.get("scorecard_key", variant.get("model_sha256", "explicit fixed queue"))
        source_label = f"{variant_name}; " + ";".join(str(path) for path in new_paths)
        if not included:
            # No matching frozen scene: do not report an unpaired new-model result.
            status = "pending"
            included = baseline_ids
            new = {}
            source_label = ""
    else:
        status = "pending"
        included = baseline_ids
        source_label = ""

    scene_csv = output_dir / "large_dual_comparison_scene_metrics_v1.csv"
    summary_csv = output_dir / "large_dual_comparison_task_summary_v1.csv"
    png_path = output_dir / "large_dual_comparison_v1.png"
    pdf_path = output_dir / "large_dual_comparison_v1.pdf"
    write_scene_csv(scene_csv, status, source_label, frozen, new, included, variant)
    values = build_long_values(frozen, new, included)
    write_summary_csv(summary_csv, values, status)
    plot_comparison(png_path, pdf_path, values, included, frozen, status, new_paths, variant)

    if status == "pending":
        print("Status: pending; frozen baseline coverage: 72/72; B768 paired scenes: 0/72")
    else:
        print(f"Status: {status}; paired scenes: {len(included)}/72")
    print(f"PNG: {png_path}")
    print(f"PDF: {pdf_path}")
    print(f"Scene data CSV: {scene_csv}")
    print(f"Task summary CSV: {summary_csv}")
    if new_paths:
        print("New CSV(s): " + "; ".join(str(path) for path in new_paths))
        print("Variant: " + json.dumps(variant, sort_keys=True))
    else:
        print(f"New CSV not found under: {NEW_CSV_ROOT}")


if __name__ == "__main__":
    main()
