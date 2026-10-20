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
from teacher_data import EpisodeBank, normalizers  # noqa: E402

MODELS = ("MLP14", "GRU14")
SEEDS = (2026102001, 2026102002)
CHECKPOINTS = ("best_teacher_val", "final_step")


def main() -> None:
    fits = json.loads((OUT / "reports" / "official_fit_60k_extension.json").read_text(encoding="utf-8"))
    if fits.get("status") != "OFFICIAL_FITS_AT_60K" or len(fits.get("fits", [])) != 4:
        raise RuntimeError("All four official 60k fits must finish before package export")
    bank = EpisodeBank("val")
    norms = normalizers()
    exported = []
    for model_id in MODELS:
        config = next(cfg for cfg in fit.CONFIGS if cfg["model_id"] == model_id)
        for seed in SEEDS:
            source = OUT / "models" / "official" / model_id / f"seed{seed}"
            report = json.loads((source / "fit_report.json").read_text(encoding="utf-8"))
            if report.get("status") != "COMPLETE" or int(report.get("last_step", 0)) != 60000:
                raise RuntimeError(f"Official fit is not complete: {model_id} seed {seed}")
            model = fit.make_model(config, norms)
            x, metadata = base.fixtures(bank, 32, 64)
            for kind in CHECKPOINTS:
                checkpoint_path = source / f"{kind}.pt"
                checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
                model.load_state_dict(checkpoint["state_dict"])
                model.eval()
                selected_step = int(checkpoint["selected_step"])
                expected_phi, expected_output = base.forward(model, model_id, x)
                matlab = base.matlab_model(model_id, model, 32, seed, selected_step)
                package = OUT / "models" / "official_export" / model_id / f"seed{seed}" / kind
                package.mkdir(parents=True, exist_ok=True)
                mat_path = package / "matlab_model_and_parity.mat"
                scipy.io.savemat(mat_path, {"model": matlab, "windows": x[:14],
                                            "expected_phi": expected_phi, "expected_output": expected_output,
                                            "fixture_count": np.asarray([[64]], dtype=np.int32)},
                                 do_compression=True, long_field_names=True, oned_as="column")
                score = (report["selected_teacher_val_rmse_mps2"] if kind == "best_teacher_val"
                         else report["final_step_teacher_val_rmse_mps2"])
                item = {"status": "EXPORTED_AWAITING_MATLAB_PARITY", "model_id": model_id,
                        "seed": seed, "checkpoint_kind": kind, "selected_step": selected_step,
                        "teacher_val_rmse_mps2": float(score), "input_dim": 14, "window": 32,
                        "architecture": matlab["architecture"], "fixture_count": len(metadata),
                        "fixture_metadata": metadata, "checkpoint_path": checkpoint_path.relative_to(ROOT).as_posix(),
                        "checkpoint_sha256": base.sha256(checkpoint_path), "mat_path": mat_path.relative_to(ROOT).as_posix(),
                        "mat_sha256": base.sha256(mat_path), "zero_plant": True,
                        "original_protocol_sha256": fit.sha256_file(OUT / "protocol.json")}
                (package / "export_report.json").write_text(json.dumps(item, indent=2, ensure_ascii=False) + "\n",
                                                            encoding="utf-8")
                exported.append({"model_id": model_id, "seed": seed, "checkpoint_kind": kind,
                                 "selected_step": selected_step, "teacher_val_rmse_mps2": score,
                                 "mat_path": item["mat_path"]})
                print(f"OFFICIAL_EXPORT_READY {model_id} seed={seed} checkpoint={kind} "
                      f"step={selected_step} fixtures=64 Plant=0", flush=True)
    result = {"status": "OFFICIAL_EXPORTS_READY_FOR_ZERO_PLANT_PARITY", "exports": exported,
              "package_count": len(exported), "fixtures_per_package": 64, "plant_starts": 0}
    path = OUT / "reports" / "official_selected_exports.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
