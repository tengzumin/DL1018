from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import scipy.io
import torch

HERE = Path(__file__).resolve()
ROOT = HERE.parents[3]
OUT = ROOT / "experiments" / "teacher_reuse_model_screen_v1"
sys.path.insert(0, str(HERE.parent))

import fit_models as fit  # noqa: E402
import export_fast_screen as base  # noqa: E402
from teacher_data import EpisodeBank  # noqa: E402
from x20_extension import KANFeature20  # noqa: E402

SEED_IDS = (2026102001, 2026102002)
MODEL_IDS = ("KAN20", "GRU20", "DSSM20")


def make_model(model_id: str, seed: int):
    folder = OUT / "models" / "fast_screen" / model_id / f"seed{seed}"
    report = json.loads((folder / "fit_report.json").read_text(encoding="utf-8"))
    if report.get("status") != "COMPLETE" or int(report.get("last_step", 0)) != 2000:
        raise RuntimeError(f"Incomplete small-screen fit: {model_id} seed {seed}")
    ck = torch.load(folder / "best_teacher_val.pt", map_location="cpu", weights_only=False)
    # Use the extension's exact KAN20 implementation; sequence families share the original constructors.
    from teacher_data import normalizers
    norms = normalizers()
    if model_id == "KAN20":
        model = KANFeature20(norms["X20"]["mu"], norms["X20"]["sigma"])
    elif model_id == "GRU20":
        model = fit.make_model({"model_id": model_id, "family": "GRU", "input_dim": 20, "window": 32,
                                "group": "TEMPORAL"}, norms)
    elif model_id == "DSSM20":
        model = fit.make_model({"model_id": model_id, "family": "DSSM", "input_dim": 20, "window": 32,
                                "group": "TEMPORAL"}, norms)
    else:
        raise ValueError(model_id)
    model.load_state_dict(ck["state_dict"])
    model.eval()
    return model, report, ck


def matlab_model(model_id: str, model, seed: int, selected_step: int) -> dict:
    state = base.numpy_state(model)
    out = {"model_id": model_id, "input_dim": np.asarray([[20]], np.int32),
           "window": np.asarray([[32]], np.int32),
           "context_length": np.asarray([[1 if model_id == "KAN20" else 32]], np.int32),
           "seed": np.asarray([[seed]], np.int64), "selected_step": np.asarray([[selected_step]], np.int32),
           "input_mu": state["input_mu"].reshape(-1, 1), "input_sigma": state["input_sigma"].reshape(-1, 1),
           "output_W": state["readout.weight"].T.copy()}
    if model_id == "KAN20":
        out.update({"architecture": "KAN", "knots": state["knots"].reshape(-1, 1),
                    "spline_W": state["spline_W"], "linear_W": state["linear_W"],
                    "feature_b": state["feature_b"].reshape(-1, 1),
                    "silu_unclipped": np.asarray([[0]], np.uint8)})
    elif model_id == "GRU20":
        out.update({"architecture": "GRU", "gru_W_ih": state["gru.weight_ih_l0"],
                    "gru_W_hh": state["gru.weight_hh_l0"], "gru_b_ih": state["gru.bias_ih_l0"].reshape(-1, 1),
                    "gru_b_hh": state["gru.bias_hh_l0"].reshape(-1, 1),
                    "project_W": state["project.weight"], "project_b": state["project.bias"].reshape(-1, 1)})
    elif model_id == "DSSM20":
        tau = np.exp(state["log_tau"]).clip(0.005, 5.0)
        out.update({"architecture": "DSSM", "ssm_tau": tau.reshape(-1, 1),
                    "input_W": state["input_encoder.weight"], "input_b": state["input_encoder.bias"].reshape(-1, 1),
                    "project_W": state["project.weight"], "project_b": state["project.bias"].reshape(-1, 1)})
    else:
        raise ValueError(model_id)
    return out


def main() -> None:
    authorization = json.loads((OUT / "reports" / "x20_extension_authorization.json").read_text(encoding="utf-8"))
    if authorization.get("status") != "USER_AUTHORIZED_EXTENSION":
        raise RuntimeError("Missing user-authorized extension record")
    bank = EpisodeBank("val")
    exported = []
    for model_id in MODEL_IDS:
        for seed in SEED_IDS:
            folder = OUT / "models" / "fast_screen" / model_id / f"seed{seed}"
            model, report, checkpoint = make_model(model_id, seed)
            x, metadata = base.fixtures(bank, 32, 64)
            tensor = torch.from_numpy(np.transpose(x[:20], (2, 1, 0)).copy()).float()
            if not model.sequence:
                tensor = tensor[:, -1, :]
            with torch.no_grad():
                expected_phi = model.encode(tensor).cpu().numpy().T
                expected_output = model.readout(torch.from_numpy(expected_phi.T).float()).detach().cpu().numpy().T
            matlab = matlab_model(model_id, model, seed, int(checkpoint["selected_step"]))
            mat_path = folder / "matlab_model_and_parity.mat"
            scipy.io.savemat(mat_path, {"model": matlab, "windows": x[:20],
                                        "expected_phi": expected_phi, "expected_output": expected_output,
                                        "fixture_count": np.asarray([[64]], dtype=np.int32)},
                             do_compression=True, long_field_names=True, oned_as="column")
            item = {"status": "EXPORTED_AWAITING_MATLAB_PARITY", "model_id": model_id, "seed": seed,
                    "selected_step": int(checkpoint["selected_step"]),
                    "teacher_val_rmse_mps2": float(report["selected_teacher_val_rmse_mps2"]),
                    "input_dim": 20, "window": 32, "context_length": int(matlab["context_length"].item()),
                    "architecture": matlab["architecture"], "fixture_count": len(metadata),
                    "fixture_metadata": metadata, "zero_plant": True,
                    "original_protocol_sha256": fit.sha256_file(OUT / "protocol.json"),
                    "authorization_path": authorization["status"]}
            (folder / "export_report.json").write_text(json.dumps(item, indent=2, ensure_ascii=False) + "\n",
                                                       encoding="utf-8")
            exported.append(item)
            print(f"X20_EXPORT_READY {model_id} seed={seed} fixtures=64 Plant=0", flush=True)
    summary = {"status": "EXPORTS_READY_FOR_ZERO_PLANT_PARITY", "exports": exported,
               "plant_starts": 0}
    path = OUT / "reports" / "x20_extension_exports.json"
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
