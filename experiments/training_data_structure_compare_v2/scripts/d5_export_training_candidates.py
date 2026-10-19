from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import scipy.io
import torch

HERE = Path(__file__).resolve()
ROOT = HERE.parents[3]
OUT = ROOT / "experiments/training_data_structure_compare_v2"
sys.path.insert(0, str(OUT / "scripts"))
sys.path.insert(0, str(ROOT / "training"))

import d4_official_fits as base
from d4_wide_mlp_fit import WideCurrentMLP

SEED = 2026101911
FAMILIES = ("MIXED_KAN", "TEACHER_KAN", "DEEP_KAN", "HISTORY_KAN", "WIDE_MLP")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def fixtures() -> tuple[np.ndarray, np.ndarray]:
    windows: list[np.ndarray] = []
    for ep in base.load_episodes("val"):
        for end in base.endpoint_indices(ep):
            if end >= 31:
                windows.append(ep.x14[end - 31:end + 1].T.astype(np.float32))
                if len(windows) == 56:
                    break
        if len(windows) == 56:
            break
    if len(windows) != 56:
        raise RuntimeError(f"Expected 56 ready VAL windows, got {len(windows)}")

    norm = np.load(ROOT / "models/position/initial/normalizer.npz")
    mu = np.asarray(norm["mu"], dtype=np.float32).reshape(-1)
    sigma = np.maximum(np.asarray(norm["sigma"], dtype=np.float32).reshape(-1), 1e-4)
    result = np.empty((14, 32, 64), dtype=np.float32)
    result[:, :, :56] = np.stack(windows, axis=2)
    for q, (feature, value) in enumerate(((0, 4.0), (0, -4.0), (0, 5.0), (0, -5.0),
                                          (13, 4.0), (13, -4.0), (13, 5.0), (13, -5.0)), start=56):
        row = mu.copy()
        row[feature] += sigma[feature] * value
        result[:, :, q] = row[:, None]
    return result, mu


def load_candidate(family: str, mu: np.ndarray, sigma: np.ndarray):
    package = OUT / "models" / family / f"seed{SEED}"
    if family == "WIDE_MLP":
        checkpoint_path = package / "best_model.pt"
        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
        model = WideCurrentMLP(mu, sigma)
        model.load_state_dict(checkpoint["state_dict"])
        model.eval()
        selected_step = int(checkpoint["selected_step"])
        fit_status = "COMPLETE"
        return package, checkpoint_path, model, selected_step, fit_status

    model = base.Candidate(family, mu, sigma)
    if family == "HISTORY_KAN":
        checkpoint_path = package / "latest_checkpoint.pt"
        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
        model.load_state_dict(checkpoint["best_state"])
        selected_step = int(checkpoint["best_step"])
        fit_status = "PAUSED_BY_USER_PARTIAL_FIT"
    else:
        checkpoint_path = package / "best_model.pt"
        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
        model.load_state_dict(checkpoint["state_dict"])
        selected_step = int(checkpoint["selected_step"])
        fit_status = "COMPLETE"
    model.eval()
    return package, checkpoint_path, model, selected_step, fit_status


def matlab_struct(family: str, model, model_id: str) -> dict:
    state = model.state_dict()
    out: dict[str, object] = {
        "input_dim": np.asarray([[14]], dtype=np.int32),
        "input_mu": state["kan.input_mu"].numpy().reshape(-1, 1) if family != "WIDE_MLP" else state["mu"].numpy().reshape(-1, 1),
        "input_sigma": state["kan.input_sigma"].numpy().reshape(-1, 1) if family != "WIDE_MLP" else state["sigma"].numpy().reshape(-1, 1),
        "output_W": (state["kan.readout.weight"] if family != "WIDE_MLP" else state["head.weight"]).numpy().T,
        "model_id": model_id,
    }
    if family == "WIDE_MLP":
        out.update({
            "architecture": "N_WIDE_SILU_MLP",
            "fc1_W": state["fc1.weight"].numpy(), "fc1_b": state["fc1.bias"].numpy().reshape(-1, 1),
            "fc2_W": state["fc2.weight"].numpy(), "fc2_b": state["fc2.bias"].numpy().reshape(-1, 1),
            "fc3_W": state["fc3.weight"].numpy(), "fc3_b": state["fc3.bias"].numpy().reshape(-1, 1),
        })
        return out

    out.update({
        "architecture": "N_KAN" if family in ("MIXED_KAN", "TEACHER_KAN") else
                        ("N_DEEP_KAN" if family == "DEEP_KAN" else "N_HISTORY_KAN"),
        "kan_silu_unclipped": np.asarray([[1]], dtype=np.uint8),
        "knots": state["kan.knots"].numpy().reshape(-1, 1),
        "spline_W": state["kan.spline_W"].numpy(),
        "linear_W": state["kan.linear_W"].numpy(),
        "feature_b": state["kan.feature_b"].numpy().reshape(-1, 1),
    })
    if family == "DEEP_KAN":
        out.update({"deep_spline_W": state["deep.spline_W"].numpy(),
                    "deep_linear_W": state["deep.linear_W"].numpy(),
                    "deep_b": state["deep.bias"].numpy().reshape(-1, 1)})
    if family == "HISTORY_KAN":
        for i in range(4):
            prefix = f"history.convs.{i}."
            out[f"history_conv{i + 1}_W"] = state[prefix + "weight"].numpy()
            out[f"history_conv{i + 1}_b"] = state[prefix + "bias"].numpy().reshape(-1, 1)
        out["history_proj_W"] = state["history.proj.weight"].numpy()
        out["history_proj_b"] = state["history.proj.bias"].numpy().reshape(-1, 1)
    return out


def main() -> None:
    norm = np.load(ROOT / "models/position/initial/normalizer.npz")
    mu = np.asarray(norm["mu"], dtype=np.float32).reshape(-1)
    sigma = np.maximum(np.asarray(norm["sigma"], dtype=np.float32).reshape(-1), 1e-4)
    windows, _ = fixtures()
    xb = torch.from_numpy(np.transpose(windows, (2, 0, 1)))
    x10 = xb[:, :10, :]

    for family in FAMILIES:
        package, checkpoint_path, model, selected_step, fit_status = load_candidate(family, mu, sigma)
        with torch.no_grad():
            if family == "WIDE_MLP":
                expected_phi = model.features(xb).numpy().T
                expected_output = model(xb).numpy().T
            elif family == "HISTORY_KAN":
                expected_phi = model.features(xb, x10).numpy().T
                expected_output = model(xb, x10).numpy().T
            else:
                expected_phi = model.features(xb).numpy().T
                expected_output = model(xb).numpy().T

        model_id = f"{family}_SEED{SEED}_STEP{selected_step}"
        matlab_model = matlab_struct(family, model, model_id)
        mat_path = package / "matlab_model_and_parity.mat"
        scipy.io.savemat(mat_path, {"model": matlab_model, "windows": windows,
                                    "expected_phi": expected_phi, "expected_output": expected_output,
                                    "fixture_count": np.asarray([[64]], dtype=np.int32)},
                         do_compression=True, long_field_names=True, oned_as="column")
        report = {
            "status": "EXPORTED_AWAITING_MATLAB_PARITY", "family": family, "seed": SEED,
            "fit_status": fit_status, "selected_step": selected_step,
            "input_dim": 14, "architecture": matlab_model["architecture"],
            "parameter_count": sum(p.numel() for p in model.parameters()), "fixture_count": 64,
            "checkpoint_sha256": sha256(checkpoint_path),
            "checkpoint_path": checkpoint_path.relative_to(ROOT).as_posix(),
            "mat_file": mat_path.relative_to(ROOT).as_posix(), "zero_plant": True,
            "history_note": "Uses the saved best checkpoint from the user-paused partial fit; no resume or extra training." if family == "HISTORY_KAN" else "",
            "mlp_note": "Random-init current-X14 MLP; different starting function from Initial, so treat as exploratory and keep this limitation in all comparisons." if family == "WIDE_MLP" else "",
        }
        (package / "export_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
