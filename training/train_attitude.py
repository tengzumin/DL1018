#!/usr/bin/env python3
"""Run exactly one prescribed DL1018 legal-X29 attitude fit."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from common import fit
from data import fit_normalizer, load_episodes, make_event_set


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--mode", choices=("initial", "final"), required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    if args.mode == "initial":
        train_roles = ("B", "P_STAR")
        val_roles = ("B", "P_STAR")
        mass = {"B": 0.5, "P_STAR": 0.5}
        seed = 2026101803
    else:
        train_roles = ("B", "P_STAR", "A_INIT_STUDENT")
        val_roles = train_roles
        mass = {"B": 0.25, "P_STAR": 0.25, "A_INIT_STUDENT": 0.5}
        seed = 2026101804
    train_eps = load_episodes(root, "train", "attitude", train_roles)
    val_eps = load_episodes(root, "val", "attitude", val_roles)
    train = make_event_set(train_eps, 5, mass)
    val_mass = mass if args.mode == "final" else {"B": 0.5, "P_STAR": 0.5}
    # Attitude validation uses every ready endpoint, unlike stride-5 training.
    val = make_event_set(val_eps, 1, val_mass)
    if args.mode == "initial":
        mu, sigma = fit_normalizer(train_eps, "attitude")
    else:
        norm = np.load(root / "models" / "attitude" / "initial" / "normalizer.npz")
        mu, sigma = norm["mu"], norm["sigma"]
    init = None if args.mode == "initial" else root / "models" / "attitude" / "initial" / "best_model.pt"
    report = fit(root=root, modality="attitude", mode=args.mode, seed=seed,
                 train=train, val=val, mu=mu, sigma=sigma, initial_checkpoint=init)
    print(json.dumps(report, indent=2, ensure_ascii=False), flush=True)
    if not report.get("training_passed", False):
        raise SystemExit(10)


if __name__ == "__main__":
    main()
