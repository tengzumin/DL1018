from __future__ import annotations

import csv
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import scipy.io
import torch

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "experiments" / "kan14_task_specialist_compare_v1"
SOURCE = ROOT / "experiments" / "teacher_reuse_model_screen_v1"
TASKS = ("HELIX", "FIG8_3D", "SQUARE")
SEED = 2026102001
sys.path.insert(0, str(SOURCE / "scripts"))

import fit_models as fit  # noqa: E402
import export_fast_screen as exporter  # noqa: E402
from teacher_data import EpisodeBank, normalizers  # noqa: E402


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def json_write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def make_fixtures(bank, task: str | None, count: int = 64):
    selected = bank.meta.reset_index(drop=True)
    groups = [(t, r) for t in sorted(selected.task.unique()) if task is None or t == task
              for r in ("B", "POS_OFF")]
    if not groups:
        raise RuntimeError(f"No teacher VAL groups for {task}")
    quota = [count // len(groups) + (i < count % len(groups)) for i in range(len(groups))]
    rows, metadata = [], []
    for (group_task, role), group_quota in zip(groups, quota):
        episodes = np.flatnonzero((selected.task.to_numpy() == group_task) &
                                  (selected.role.to_numpy() == role))
        if len(episodes) == 0:
            raise RuntimeError(f"Missing validation episodes for {group_task}/{role}")
        per_episode = np.full(len(episodes), group_quota // len(episodes), dtype=int)
        per_episode[:group_quota % len(episodes)] += 1
        for ep, needed in zip(episodes, per_episode):
            if needed <= 0:
                continue
            phase = bank.phase[ep]
            edges = np.flatnonzero(phase[1:] != phase[:-1]) + 1
            valid = np.arange(31, 1999, 5, dtype=np.int32)
            targets = [31, 1998]
            targets.extend(int(np.clip(e - 1, 31, 1998)) for e in edges)
            targets.extend(np.linspace(31, 1998, max(needed * 3, 3)).round().astype(int).tolist())
            chosen = []
            for target in targets:
                endpoint = int(valid[np.argmin(np.abs(valid - target))])
                if endpoint not in chosen:
                    chosen.append(endpoint)
                if len(chosen) == needed:
                    break
            if len(chosen) != needed:
                raise RuntimeError("Could not construct deterministic legal parity windows")
            for endpoint in chosen:
                rows.append(bank.x20[ep, endpoint - 31:endpoint + 1, :14].T.copy())
                metadata.append({"task": group_task, "role": role, "scene_id": str(selected.iloc[ep].scene_id),
                                 "run_id": str(selected.iloc[ep].run_id), "endpoint": endpoint,
                                 "phase": int(phase[endpoint]), "window": 32})
    if len(rows) != count:
        raise RuntimeError(f"Expected {count} fixtures but built {len(rows)}")
    return np.stack(rows, axis=2), metadata


def export_one(policy: str, task: str | None, checkpoint_path: Path, report_path: Path,
               package: Path, bank, norms: dict, protocol_hash: str) -> dict:
    fit_report = json.loads(report_path.read_text(encoding="utf-8"))
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    expected_step = 60000 if policy == "SHARED_KAN14" else 20000
    if (fit_report.get("status") != "COMPLETE" or fit_report.get("model_id") != "KAN14" or
            int(fit_report.get("seed", -1)) != SEED or int(fit_report.get("last_step", -1)) != expected_step or
            int(checkpoint.get("selected_step", -1)) != expected_step):
        raise RuntimeError(f"Fit/checkpoint identity mismatch for {policy} {task}")
    config = {"model_id": "KAN14", "family": "KAN", "input_dim": 14, "window": 32, "group": policy}
    model = fit.make_model(config, norms)
    model.load_state_dict(checkpoint["state_dict"], strict=True)
    model.eval()
    package.mkdir(parents=True, exist_ok=True)
    copied_checkpoint = package / "final_step.pt"
    copied_report = package / "fit_report.json"
    shutil.copy2(checkpoint_path, copied_checkpoint)
    shutil.copy2(report_path, copied_report)
    windows, fixture_meta = make_fixtures(bank, task, 64)
    expected_phi, expected_output = exporter.forward(model, "KAN14", windows)
    matlab_model = exporter.matlab_model("KAN14", model, 32, SEED, expected_step)
    mat_path = package / "matlab_model_and_parity.mat"
    scipy.io.savemat(mat_path, {
        "model": matlab_model, "windows": windows, "expected_phi": expected_phi,
        "expected_output": expected_output, "fixture_count": np.asarray([[64]], dtype=np.int32),
    }, do_compression=True, long_field_names=True, oned_as="column")
    task_name = task or "ALL_TASKS"
    record = {
        "status": "EXPORTED_AWAITING_MATLAB_PARITY", "policy_id": policy, "task": task,
        "model_id": "KAN14", "seed": SEED, "checkpoint_kind": "final_step", "selected_step": expected_step,
        "teacher_val_rmse_mps2": float(fit_report["final_step_teacher_val_rmse_mps2"]),
        "input_dim": 14, "window": 32, "context_length": 1, "architecture": "KAN",
        "parameter_count": int(fit_report["parameter_count"]), "normalizer_id": fit_report["normalizer_id"],
        "fit_report_sha256": sha256(copied_report), "checkpoint_sha256": sha256(copied_checkpoint),
        "mat_sha256": sha256(mat_path), "fixture_count": len(fixture_meta),
        "fixture_metadata": fixture_meta, "fixtures_split": "teacher VAL only",
        "protocol_sha256": protocol_hash, "package_id": f"{policy}_{task_name}_SEED{SEED}_FINAL_STEP",
        "zero_plant": True, "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    json_write(package / "export_report.json", record)
    print(f"KAN14_EXPORT_READY policy={policy} task={task_name} seed={SEED} step={expected_step} fixtures=64 mat={mat_path.relative_to(ROOT).as_posix()}", flush=True)
    return {"package_id": record["package_id"], "policy_id": policy, "task": task_name,
            "model_id": "KAN14", "seed": SEED, "checkpoint_kind": "final_step", "selected_step": expected_step,
            "fit_report_path": copied_report.relative_to(ROOT).as_posix(),
            "checkpoint_path": copied_checkpoint.relative_to(ROOT).as_posix(),
            "mat_path": mat_path.relative_to(ROOT).as_posix(), "fixture_count": 64,
            "parity_status": "PENDING", "teacher_val_rmse_mps2": record["teacher_val_rmse_mps2"]}


def main() -> None:
    protocol_path = OUT / "protocol.json"
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    protocol_hash = sha256(protocol_path)
    if protocol.get("status") != "FROZEN_BEFORE_FIRST_FIT" or int(protocol.get("seed", -1)) != SEED:
        raise RuntimeError("Export protocol is not the frozen single-seed protocol")
    train_results = OUT / "reports" / "training_results.csv"
    if not train_results.is_file():
        raise FileNotFoundError(train_results)
    for task in TASKS:
        fit_id = f"TASK_{task}_KAN14_SEED{SEED}"
        match = [r for r in csv.DictReader(train_results.open("r", newline="", encoding="utf-8-sig")) if r["fit_id"] == fit_id]
        if len(match) != 1 or match[0]["status"] != "COMPLETE" or int(match[0]["selected_step"]) > 20000:
            raise RuntimeError(f"Missing complete frozen task fit {fit_id}")

    val_bank = EpisodeBank("val")
    norms = normalizers()
    rows = []
    for task in TASKS:
        fit_id = f"TASK_{task}_KAN14_SEED{SEED}"
        folder = OUT / "models" / f"task_{task.lower()}" / "KAN14" / f"seed{SEED}"
        package = OUT / "models" / "task_specialists" / task / f"seed{SEED}" / "final_step"
        rows.append(export_one(f"TASK_KAN14_{task}", task, folder / "final_step.pt",
                               folder / "fit_report.json", package, val_bank, norms, protocol_hash))

    shared_folder = SOURCE / "models" / "official" / "KAN14" / f"seed{SEED}"
    shared_package = OUT / "models" / "shared" / "KAN14" / f"seed{SEED}" / "final_step"
    rows.append(export_one("SHARED_KAN14", None, shared_folder / "final_step.pt",
                           shared_folder / "fit_report.json", shared_package, val_bank, norms, protocol_hash))
    fields = ("package_id", "policy_id", "task", "model_id", "seed", "checkpoint_kind", "selected_step",
              "fit_report_path", "checkpoint_path", "mat_path", "fixture_count", "parity_status",
              "teacher_val_rmse_mps2")
    with (OUT / "manifests" / "package_registry.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    state_path = OUT / "state" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state.update({"status": "IN_PROGRESS", "phase": "MODEL_EXPORTS_READY",
                  "packages_expected": 4, "packages_exported": 4,
                  "parity": "PENDING", "updated_at_utc": datetime.now(timezone.utc).isoformat()})
    json_write(state_path, state)
    print("KAN14_EXPORTS_COMPLETE packages=4 parity=pending", flush=True)


if __name__ == "__main__":
    main()
