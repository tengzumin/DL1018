from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import scipy.io
import torch

from d4_kan import PositionKAN
from d4_sequence_data import load_split

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "experiments" / "position_causal_repair_v1"
FAMILIES = {"C1": "C1_X20_FIXED_INFORMATION", "C2": "C2_X14_ADAPTATION_AWARE"}
SEED = 2026101901


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", choices=FAMILIES, required=True)
    args = ap.parse_args()
    family = FAMILIES[args.candidate]
    package = OUT / "models" / family / f"seed{SEED}"
    checkpoint_path = package / "best_model.pt"
    norm = np.load(package / "normalizer.npz")
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    dim = int(checkpoint["input_dim"])
    model = PositionKAN(dim, norm["mu"], norm["sigma"])
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()

    fixtures = []
    for ep in load_split("val"):
        arr = ep.x20 if dim == 20 else ep.x14
        for end in np.flatnonzero(ep.ready):
            if end >= 31:
                fixtures.append(arr[end - 31:end + 1].T.astype(np.float32))
                if len(fixtures) == 56:
                    break
        if len(fixtures) == 56:
            break
    if len(fixtures) != 56:
        raise RuntimeError(f"Expected 56 ready VAL fixtures, got {len(fixtures)}")
    windows = np.empty((dim, 32, 64), dtype=np.float32)
    windows[:, :, :56] = np.stack(fixtures, axis=2)
    mu = norm["mu"].astype(np.float32).reshape(-1)
    sigma = norm["sigma"].astype(np.float32).reshape(-1)
    boundary_cases = ((0, 4.0), (0, -4.0), (0, 5.0), (0, -5.0),
                      (dim - 1, 4.0), (dim - 1, -4.0), (dim - 1, 5.0), (dim - 1, -5.0))
    for q, (feature, value) in enumerate(boundary_cases, start=56):
        row = mu.copy()
        row[feature] += sigma[feature] * value
        windows[:, :, q] = row[:, None]
    xb = torch.from_numpy(np.transpose(windows, (2, 0, 1)))
    with torch.no_grad():
        expected_phi = model.encode(xb).numpy().T
        expected_output = model(xb).numpy().T

    state = model.state_dict()
    matlab_model = {
        "input_dim": np.asarray([[dim]], dtype=np.int32),
        "architecture": "N_KAN",
        "kan_silu_unclipped": np.asarray([[1]], dtype=np.uint8),
        "input_mu": state["input_mu"].numpy().reshape(-1, 1),
        "input_sigma": state["input_sigma"].numpy().reshape(-1, 1),
        "knots": state["knots"].numpy().reshape(-1, 1),
        "spline_W": state["spline_W"].numpy(),
        "linear_W": state["linear_W"].numpy(),
        "feature_b": state["feature_b"].numpy().reshape(-1, 1),
        "output_W": state["readout.weight"].numpy().T,
        "model_id": f"{family}_SEED{SEED}",
    }
    mat_path = package / "matlab_model_and_parity.mat"
    scipy.io.savemat(mat_path, {"model": matlab_model, "windows": windows,
                                "expected_phi": expected_phi,
                                "expected_output": expected_output,
                                "fixture_count": np.asarray([[64]], dtype=np.int32)},
                     do_compression=True, long_field_names=True, oned_as="column")
    report = {
        "status": "EXPORTED_AWAITING_MATLAB_PARITY", "family": family, "seed": SEED,
        "input_dim": dim, "architecture": "N_KAN", "parameter_count": sum(p.numel() for p in model.parameters()),
        "fixture_count": 64, "input_shape_matlab": list(windows.shape),
        "expected_phi_shape_matlab": list(expected_phi.shape),
        "expected_output_shape_matlab": list(expected_output.shape),
        "checkpoint_sha256": sha256(checkpoint_path), "mat_file": mat_path.relative_to(ROOT).as_posix(),
        "zero_plant": True,
    }
    (package / "export_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
