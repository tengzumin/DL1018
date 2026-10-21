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
OUT = ROOT / "experiments" / "teacher_reuse_model_screen_v1"
sys.path.insert(0, str(OUT / "scripts"))
import fit_models as fit  # noqa: E402
from teacher_data import EpisodeBank, normalizers  # noqa: E402

SEED = 2026102001


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def fixtures(bank: EpisodeBank, length: int, count: int = 64) -> tuple[np.ndarray, list[dict]]:
    """Balanced deterministic teacher-VAL windows near phase edges and through each task/role."""
    rows: list[np.ndarray] = []
    metadata: list[dict] = []
    selected = bank.meta.reset_index(drop=True)
    groups = [(task, role) for task in sorted(selected.task.unique()) for role in ("B", "POS_OFF")]
    per_group = [count // len(groups) + (i < count % len(groups)) for i in range(len(groups))]
    for (task, role), quota in zip(groups, per_group):
        episodes = np.flatnonzero((selected.task.to_numpy() == task) & (selected.role.to_numpy() == role))
        if len(episodes) == 0:
            raise RuntimeError(f"Missing teacher VAL episodes for {task}/{role}")
        group_rows = []
        group_meta = []
        each = np.full(len(episodes), quota // len(episodes), dtype=int)
        each[:quota % len(episodes)] += 1
        for ep_i, n in zip(episodes, each):
            phase = bank.phase[ep_i]
            edges = np.flatnonzero(phase[1:] != phase[:-1]) + 1
            valid = np.arange(length - 1, len(phase), 5, dtype=np.int32)
            targets = [length - 1, len(phase) - 1]
            targets.extend(int(np.clip(e - 1, length - 1, len(phase) - 1)) for e in edges)
            targets.extend(np.linspace(length - 1, len(phase) - 1, max(n * 2, 2)).round().astype(int).tolist())
            chosen: list[int] = []
            for target in targets:
                endpoint = int(valid[np.argmin(np.abs(valid - target))])
                if endpoint not in chosen:
                    chosen.append(endpoint)
                if len(chosen) == n:
                    break
            for end in chosen:
                group_rows.append(bank.x20[ep_i, end - length + 1:end + 1].T.copy())
                group_meta.append({"task": task, "role": role, "scene_id": str(selected.iloc[ep_i].scene_id),
                                   "run_id": str(selected.iloc[ep_i].run_id), "endpoint": end,
                                   "phase": int(phase[end]), "window": length})
        if len(group_rows) > quota:
            group_rows, group_meta = group_rows[:quota], group_meta[:quota]
        if len(group_rows) < quota:
            raise RuntimeError(f"Could not construct {quota} valid fixtures for {task}/{role}; got {len(group_rows)}")
        rows.extend(group_rows)
        metadata.extend(group_meta)
    if len(rows) != count:
        raise RuntimeError(f"Expected {count} fixtures, got {len(rows)}")
    return np.stack(rows, axis=2), metadata


def numpy_state(model) -> dict[str, np.ndarray]:
    return {key: value.detach().cpu().numpy() for key, value in model.state_dict().items()}


def matlab_model(model_id: str, model, window: int, seed: int, step: int) -> dict:
    state = numpy_state(model)
    input_dim = model.input_dim
    base = {"input_dim": np.asarray([[input_dim]], np.int32),
            "window": np.asarray([[window]], np.int32),
            "context_length": np.asarray([[1 if model_id.startswith(("MLP", "KAN")) else window]], np.int32),
            "seed": np.asarray([[seed]], np.int64), "selected_step": np.asarray([[step]], np.int32),
            "model_id": model_id,
            "input_mu": state["input_mu"].reshape(-1, 1),
            "input_sigma": state["input_sigma"].reshape(-1, 1),
            "output_W": state["readout.weight"].T.copy()}
    if model_id.startswith("MLP"):
        base["architecture"] = "MLP"
        for layer in ("fc1", "fc2", "fc3"):
            base[f"{layer}_W"] = state[f"{layer}.weight"]
            base[f"{layer}_b"] = state[f"{layer}.bias"].reshape(-1, 1)
    elif model_id == "KAN14":
        base.update({"architecture": "KAN", "knots": state["knots"].reshape(-1, 1),
                     "spline_W": state["spline_W"], "linear_W": state["linear_W"],
                     "feature_b": state["feature_b"].reshape(-1, 1), "silu_unclipped": np.asarray([[1]], np.uint8)})
    elif model_id.startswith("TCN"):
        dilations = (1, 2, 4, 8, 16) if window == 32 else (1, 2, 4, 8, 16, 32, 64)
        base.update({"architecture": "TCN", "dilations": np.asarray(dilations, dtype=np.int32).reshape(1, -1),
                     "stem_W": state["stem.weight"], "stem_b": state["stem.bias"].reshape(-1, 1),
                     "project_W": state["project.weight"], "project_b": state["project.bias"].reshape(-1, 1)})
        for i, _ in enumerate(dilations):
            for part in ("conv", "mix"):
                base[f"block{i + 1}_{part}_W"] = state[f"blocks.{i}.{part}.weight"]
                base[f"block{i + 1}_{part}_b"] = state[f"blocks.{i}.{part}.bias"].reshape(-1, 1)
    elif model_id == "GRU14":
        base.update({"architecture": "GRU", "gru_W_ih": state["gru.weight_ih_l0"],
                     "gru_W_hh": state["gru.weight_hh_l0"], "gru_b_ih": state["gru.bias_ih_l0"].reshape(-1, 1),
                     "gru_b_hh": state["gru.bias_hh_l0"].reshape(-1, 1),
                     "project_W": state["project.weight"], "project_b": state["project.bias"].reshape(-1, 1)})
    elif model_id == "DSSM14":
        tau = np.exp(state["log_tau"]).clip(0.005, 5.0)
        base.update({"architecture": "DSSM", "ssm_tau": tau.reshape(-1, 1),
                     "input_W": state["input_encoder.weight"], "input_b": state["input_encoder.bias"].reshape(-1, 1),
                     "project_W": state["project.weight"], "project_b": state["project.bias"].reshape(-1, 1)})
    else:
        raise ValueError(f"Unsupported model: {model_id}")
    return base


def forward(model, model_id: str, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    tensor = torch.from_numpy(np.transpose(x[:model.input_dim], (2, 1, 0)).copy()).float()
    if model_id == "KAN14":
        tensor = tensor[:, -1, :]
    if not model.sequence and model_id != "KAN14":
        tensor = tensor[:, -1, :]
    with torch.no_grad():
        phi = model.encode(tensor)
        pred = model.readout(phi)
    return phi.cpu().numpy().T, pred.cpu().numpy().T


def main() -> None:
    protocol = json.loads((OUT / "protocol.json").read_text(encoding="utf-8"))
    if protocol.get("status") != "FROZEN_BEFORE_FIRST_FIT":
        raise RuntimeError("Protocol is not frozen")
    train_reports = OUT / "reports" / "training_results.csv"
    if not train_reports.is_file():
        raise FileNotFoundError(train_reports)
    bank = EpisodeBank("val")
    norms = normalizers()
    outputs = []
    for cfg in fit.CONFIGS:
        model_id = cfg["model_id"]
        package = OUT / "models" / "fast_screen" / model_id / f"seed{SEED}"
        report = json.loads((package / "fit_report.json").read_text(encoding="utf-8"))
        checkpoint_path = package / "best_teacher_val.pt"
        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
        if report["status"] != "COMPLETE" or int(report["seed"]) != SEED:
            raise RuntimeError(f"Incomplete representative checkpoint for {model_id}")
        model = fit.make_model(cfg, norms)
        model.load_state_dict(checkpoint["state_dict"])
        model.eval()
        x, fixture_meta = fixtures(bank, cfg["window"])
        expected_phi, expected_output = forward(model, model_id, x)
        m = matlab_model(model_id, model, cfg["window"], SEED, int(checkpoint["selected_step"]))
        mat_path = package / "matlab_model_and_parity.mat"
        scipy.io.savemat(mat_path, {"model": m, "windows": x[:cfg["input_dim"], :, :],
                                    "expected_phi": expected_phi, "expected_output": expected_output,
                                    "fixture_count": np.asarray([[x.shape[2]]], dtype=np.int32)},
                         do_compression=True, long_field_names=True, oned_as="column")
        report_out = {"status": "EXPORTED_AWAITING_MATLAB_PARITY", "model_id": model_id,
                      "seed": SEED, "selected_step": int(checkpoint["selected_step"]),
                      "teacher_val_rmse_mps2": float(report["selected_teacher_val_rmse_mps2"]),
                      "input_dim": cfg["input_dim"], "window": cfg["window"],
                      "architecture": m["architecture"], "parameter_count": int(report["parameter_count"]),
                      "checkpoint_path": checkpoint_path.relative_to(ROOT).as_posix(),
                      "checkpoint_sha256": sha256(checkpoint_path), "mat_path": mat_path.relative_to(ROOT).as_posix(),
                      "mat_sha256": sha256(mat_path), "fixture_count": len(fixture_meta),
                      "fixture_metadata": fixture_meta, "zero_plant": True,
                      "protocol_sha256": sha256(OUT / "protocol.json")}
        (package / "export_report.json").write_text(json.dumps(report_out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        outputs.append({"model_id": model_id, "path": report_out["mat_path"], "fixtures": len(fixture_meta)})
        print(json.dumps(outputs[-1], ensure_ascii=False), flush=True)
    print(json.dumps({"status": "EXPORTS_READY_FOR_MATLAB_PARITY", "models": outputs}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
