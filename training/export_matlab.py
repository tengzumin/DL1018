#!/usr/bin/env python3
"""Export one fixed KAN package and 64 event-window parity fixtures."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import scipy.io
import torch

from data import load_episodes
from models import KANModel


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--modality", choices=("position", "attitude"), required=True)
    parser.add_argument("--package", choices=("initial", "final_candidate", "selected"), required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    dim = 14 if args.modality == "position" else 29
    package = root / "models" / args.modality / args.package
    model_path = package / ("best_model.pt" if args.package in ("initial", "final_candidate") else "selected_model.pt")
    normalizer_path = package / "normalizer.npz"
    if not model_path.is_file() or not normalizer_path.is_file():
        raise FileNotFoundError(f"Incomplete {args.modality}/{args.package} package")
    norm = np.load(normalizer_path)
    model = KANModel(dim, norm["mu"], norm["sigma"],
                     position_unclipped_silu=args.modality == "position")
    checkpoint = torch.load(model_path, map_location="cpu", weights_only=False)
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    state = model.state_dict()
    common = {"input_dim": np.asarray([[dim]], dtype=np.int32),
              "input_mu": state["input_mu"].numpy().reshape(-1, 1),
              "input_sigma": state["input_sigma"].numpy().reshape(-1, 1),
              "knots": state["knots"].numpy().reshape(-1, 1),
              "spline_W": state["spline_W"].numpy(),
              "linear_W": state["linear_W"].numpy(),
              "feature_b": state["feature_b"].numpy().reshape(-1, 1)}
    if args.modality == "position":
        matlab_model = {**common, "architecture": "N_KAN",
                        "kan_silu_unclipped": np.asarray([[1]], dtype=np.uint8),
                        "output_W": state["readout.weight"].numpy().T}
        roles = ("B", "POS_OFF", "P_INIT_STUDENT") if args.package != "initial" else ("B", "POS_OFF")
        h5_kind = "position"
    else:
        dmax = np.asarray([[45.0], [45.0], [4.7124]])
        matlab_model = {**common, "params": {
            "spline_W": common["spline_W"], "linear_W": common["linear_W"],
            "feature_b": common["feature_b"],
            "readout__weight": state["readout.weight"].numpy()},
            "architecture": "KAN", "dmax": dmax, "D_A": dmax}
        roles = ("B", "P_STAR", "A_INIT_STUDENT") if args.package != "initial" else ("B", "P_STAR")
        h5_kind = "attitude"
    modality_dir = "position" if args.modality == "position" else "attitude"
    # Initial parity uses Teacher VAL; Final/Selected parity uses the same mixed
    # validation population used to protect the Final epoch-0 candidate.
    val_episodes = load_episodes(root, "val", h5_kind, roles)
    fixtures, count = [], 0
    for ep in val_episodes:
        for end in np.flatnonzero(ep.ready):
            if end < 31:
                continue
            fixtures.append(ep.x[end - 31:end + 1].T.astype(np.float32))
            count += 1
            if count == 64:
                break
        if count == 64:
            break
    if count != 64:
        raise RuntimeError(f"Expected 64 ready validation fixtures; got {count}")
    windows = np.stack(fixtures, axis=2)  # MATLAB [feature,event,fixture]
    # Keep 56 real validation windows and force the exported spline interface
    # through normalized zero, +/-4 knots and beyond-boundary SiLU inputs.
    mu_model = state["input_mu"].numpy().reshape(-1).astype(np.float32)
    sigma_model = state["input_sigma"].numpy().reshape(-1).astype(np.float32)
    boundary_cases = ((0, 4.0), (0, -4.0), (0, 5.0), (0, -5.0),
                      (dim - 1, 4.0), (dim - 1, -4.0), (dim - 1, 5.0), (dim - 1, -5.0))
    for q, (feature, z_value) in enumerate(boundary_cases, start=56):
        row = mu_model.copy()
        row[feature] = mu_model[feature] + sigma_model[feature] * z_value
        windows[:, :, q] = row[:, None]
    betas = np.resize(np.asarray([0.0, 0.5, 1.0], dtype=np.float64), 64)
    surfaces = np.resize(np.asarray([[4.0, -4.0, 2.0], [-4.0, 4.0, -2.0],
                                     [0.5, -0.5, 0.25]], dtype=np.float64), (64, 3))
    x = torch.from_numpy(np.transpose(windows, (2, 0, 1)))
    with torch.no_grad():
        phi = model.encode(x).numpy().T
        output = model(x).numpy().T
    out = package / "matlab_model_and_parity.mat"
    scipy.io.savemat(out, {"model": matlab_model, "windows": windows,
                           "expected_phi": phi, "expected_output": output,
                           "beta": betas.reshape(-1, 1), "surface": surfaces.T,
                           "fixture_count": np.asarray([[64]], dtype=np.int32)},
                     do_compression=True, long_field_names=True, oned_as="column")
    result = {"modality": modality_dir, "package": args.package,
              "checkpoint": str(model_path.relative_to(root)).replace("\\", "/"),
              "mat_file": str(out.relative_to(root)).replace("\\", "/"),
              "fixture_count": 64, "input_shape_matlab": list(windows.shape),
              "expected_phi_shape_matlab": list(phi.shape),
              "expected_output_shape_matlab": list(output.shape),
              "input_dim": dim, "parameter_count": sum(p.numel() for p in model.parameters())}
    (package / "export_report.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
