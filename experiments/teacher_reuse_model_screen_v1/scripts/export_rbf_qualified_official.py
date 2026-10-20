from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import scipy.io
import torch

import fit_models as fit
import export_fast_screen as base
import export_x20_extension as x20
from teacher_data import EpisodeBank, normalizers

OUT = fit.OUT
MODELS = ("KAN14", "DSSM14", "GRU20", "DSSM20")
SEEDS = fit.SEEDS
CHECKPOINTS = ("best_teacher_val", "final_step")
X20_CONFIGS = {
    "GRU20": {"model_id": "GRU20", "family": "GRU", "input_dim": 20, "window": 32, "group": "TEMPORAL"},
    "DSSM20": {"model_id": "DSSM20", "family": "DSSM", "input_dim": 20, "window": 32, "group": "TEMPORAL"},
}


def main() -> None:
    authorization = json.loads((OUT / "reports" / "rbf_qualified_extension_authorization.json").read_text(encoding="utf-8"))
    if authorization.get("status") != "USER_AUTHORIZED_SCOPE_EXTENSION" or \
            authorization.get("additional_official_configurations") != list(MODELS):
        raise RuntimeError("Missing authorization for the below-RBF official packages")
    fits = json.loads((OUT / "reports" / "rbf_qualified_official_fits.json").read_text(encoding="utf-8"))
    if fits.get("status") not in {"OFFICIAL_FITS_AT_40K", "OFFICIAL_FITS_AT_60K"} or len(fits.get("fits", [])) != 8:
        raise RuntimeError("All eight below-RBF official fits must finish before package export")
    bank, norms = EpisodeBank("val"), normalizers()
    exported = []
    for model_id in MODELS:
        config = (next(c for c in fit.CONFIGS if c["model_id"] == model_id)
                  if model_id in {"KAN14", "DSSM14"} else X20_CONFIGS[model_id])
        for seed in SEEDS:
            source = OUT / "models" / "official" / model_id / f"seed{seed}"
            report = json.loads((source / "fit_report.json").read_text(encoding="utf-8"))
            if int(report.get("last_step", 0)) not in {40000, 60000}:
                raise RuntimeError(f"Unexpected official fit length: {model_id} seed {seed}")
            model = fit.make_model(config, norms)
            x, metadata = base.fixtures(bank, 32, 64)
            for kind in CHECKPOINTS:
                checkpoint_path = source / f"{kind}.pt"
                checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
                model.load_state_dict(checkpoint["state_dict"])
                model.eval()
                selected_step = int(checkpoint["selected_step"])
                expected_phi, expected_output = base.forward(model, model_id, x)
                matlab = (base.matlab_model(model_id, model, 32, seed, selected_step)
                          if config["input_dim"] == 14 else x20.matlab_model(model_id, model, seed, selected_step))
                package = OUT / "models" / "official_export" / model_id / f"seed{seed}" / kind
                package.mkdir(parents=True, exist_ok=True)
                mat_path = package / "matlab_model_and_parity.mat"
                scipy.io.savemat(mat_path, {"model": matlab, "windows": x[:config["input_dim"]],
                                            "expected_phi": expected_phi, "expected_output": expected_output,
                                            "fixture_count": np.asarray([[64]], dtype=np.int32)},
                                 do_compression=True, long_field_names=True, oned_as="column")
                score = (report["selected_teacher_val_rmse_mps2"] if kind == "best_teacher_val"
                         else report["final_step_teacher_val_rmse_mps2"])
                item = {"status": "EXPORTED_AWAITING_MATLAB_PARITY", "model_id": model_id,
                        "seed": seed, "checkpoint_kind": kind, "selected_step": selected_step,
                        "teacher_val_rmse_mps2": float(score), "input_dim": config["input_dim"],
                        "window": 32, "architecture": matlab["architecture"], "fixture_count": len(metadata),
                        "fixture_metadata": metadata,
                        "checkpoint_path": checkpoint_path.relative_to(fit.ROOT).as_posix(),
                        "checkpoint_sha256": base.sha256(checkpoint_path),
                        "mat_path": mat_path.relative_to(fit.ROOT).as_posix(),
                        "mat_sha256": base.sha256(mat_path), "zero_plant": True,
                        "protocol_sha256": fit.sha256_file(OUT / "protocol.json"),
                        "authorization_path": "reports/rbf_qualified_extension_authorization.json"}
                (package / "export_report.json").write_text(json.dumps(item, indent=2, ensure_ascii=False) + "\n",
                                                            encoding="utf-8")
                exported.append({"model_id": model_id, "seed": seed, "checkpoint_kind": kind,
                                 "selected_step": selected_step, "teacher_val_rmse_mps2": score,
                                 "mat_path": item["mat_path"]})
                print(f"BELOW_RBF_EXPORT_READY {model_id} seed={seed} checkpoint={kind} "
                      f"step={selected_step} fixtures=64 Plant=0", flush=True)
    result = {"status": "EXPORTS_READY_FOR_ZERO_PLANT_PARITY", "exports": exported,
              "package_count": len(exported), "fixtures_per_package": 64, "plant_starts": 0}
    path = OUT / "reports" / "rbf_qualified_official_exports.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
