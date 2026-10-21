from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.io
import torch

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "experiments" / "gru14_dssm14_student_refine_v1"
SOURCE = ROOT / "experiments" / "teacher_reuse_model_screen_v1"
sys.path.insert(0, str(SOURCE / "scripts"))
import export_fast_screen as export_base  # noqa: E402
import fit_models as fit  # noqa: E402
from student_data import load_student  # noqa: E402
from teacher_data import EpisodeBank  # noqa: E402

ENDS = np.arange(31, 1999, 5, dtype=np.int32)


def state_hash(state: dict) -> str:
    h = hashlib.sha256()
    for key in sorted(state):
        value = state[key].detach().cpu().contiguous().numpy()
        h.update(key.encode("utf-8"))
        h.update(str(value.dtype).encode("ascii"))
        h.update(np.asarray(value.shape, dtype=np.int64).tobytes())
        h.update(value.tobytes())
    return h.hexdigest()


def fixtures(model_id: str, seed: int) -> tuple[np.ndarray, list[dict]]:
    teacher = EpisodeBank("train")
    student = load_student(model_id, "train")
    rng = np.random.default_rng(seed)
    windows: list[np.ndarray] = []
    metadata: list[dict] = []

    def append_group(bank, source: str, role: str, task: str, quota: int) -> None:
        meta = bank.meta.reset_index(drop=True)
        episodes = np.flatnonzero((meta.task.astype(str).to_numpy() == task) &
                                  (meta.role.astype(str).to_numpy() == role))
        if not len(episodes):
            raise RuntimeError(f"Missing fixture source {model_id}/{source}/{task}/{role}")
        rng.shuffle(episodes)
        chosen = 0
        for ep in episodes:
            phase = bank.phase[ep]
            edges = np.flatnonzero(phase[1:] != phase[:-1]) + 1
            targets = [31, 1996]
            targets.extend(int(e) for e in edges)
            targets.extend(np.linspace(31, 1996, max(2 * quota, 4)).round().astype(int).tolist())
            ends = []
            for target in targets:
                end = int(ENDS[np.argmin(np.abs(ENDS - target))])
                if end not in ends:
                    ends.append(end)
                if len(ends) >= quota:
                    break
            for end in ends:
                windows.append(bank.x14[ep, end - 31:end + 1, :14].T.copy())
                metadata.append({"source": source, "role": role, "task": task,
                                 "scene_id": str(meta.iloc[ep].scene_id), "run_id": str(meta.iloc[ep].run_id),
                                 "endpoint_zero_based": end, "phase": int(phase[end]), "window": 32})
                chosen += 1
                if chosen >= quota:
                    return
        raise RuntimeError(f"Insufficient phase-edge fixtures for {model_id}/{source}/{task}/{role}")

    teacher_groups = [(task, role) for task in ("FIG8_3D", "HELIX", "SQUARE") for role in ("B", "POS_OFF")]
    teacher_q = [6, 6, 5, 5, 5, 5]
    for (task, role), quota in zip(teacher_groups, teacher_q):
        append_group(teacher, "TEACHER", role, task, quota)
    student_q = {"FIG8_3D": 11, "HELIX": 11, "SQUARE": 10}
    for task, quota in student_q.items():
        append_group(student, "STUDENT", "STUDENT", task, quota)
    X = np.stack(windows, axis=2).astype(np.float32)
    if X.shape != (14, 32, 64) or len(metadata) != 64:
        raise RuntimeError(f"Expected 64 X14/32 fixtures, got {X.shape}")
    if {m["source"] for m in metadata} != {"TEACHER", "STUDENT"} or \
            {m["task"] for m in metadata} != {"HELIX", "FIG8_3D", "SQUARE"}:
        raise RuntimeError("Fixtures must cover teacher+student data and all three tasks")
    return X, metadata


def matlab_outputs(model, model_id: str, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    tensor = torch.from_numpy(np.transpose(X, (2, 1, 0)).copy()).float()
    model.eval()
    with torch.no_grad():
        phi = model.encode(tensor).cpu().numpy().T
        pred = model.readout(torch.from_numpy(phi.T.copy()).float()).cpu().numpy().T
    return phi, pred


def main() -> None:
    protocol = json.loads((OUT / "protocol.json").read_text(encoding="utf-8"))
    if protocol.get("status") != "FROZEN_BEFORE_FIRST_PLANT":
        raise RuntimeError("Frozen protocol is missing")
    norms = fit.normalizers()
    packages: dict[str, dict] = {}
    canonical: dict[tuple[str, str], str] = {}
    rows = []
    for model_id in ("GRU14", "DSSM14"):
        cfg = next(c for c in fit.CONFIGS if c["model_id"] == model_id)
        X, fixture_meta = fixtures(model_id, 2026102030 + (model_id == "DSSM14"))
        for group in ("TEACHER_CONTINUE", "STUDENT_MIX20"):
            for seed in (2026102011, 2026102012):
                fit_dir = OUT / "models" / model_id / group / f"seed{seed}"
                report = json.loads((fit_dir / "fit_report.json").read_text(encoding="utf-8"))
                fit_steps = int(report.get("steps", 0))
                if report.get("status") != "COMPLETE" or fit_steps <= 0:
                    raise RuntimeError(f"Fit is incomplete: {fit_dir}")
                for kind, checkpoint_path in (("best_common_val", fit_dir / "best_common_val.pt"),
                                              ("final_step", fit_dir / "final_step.pt")):
                    ck = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
                    expected_step = int(report["selected_step"]) if kind == "best_common_val" else fit_steps
                    if int(ck.get("selected_step", -1)) != expected_step:
                        raise RuntimeError(f"Checkpoint/report step mismatch for {fit_dir} ({kind})")
                    weights_sha = state_hash(ck["state_dict"])
                    candidate_id = f"{model_id}_{group}_SEED{seed}_{kind}"
                    key = (model_id, weights_sha)
                    if key in canonical:
                        rows.append({"package_id": candidate_id, "model_id": model_id, "group": group,
                                     "seed": seed, "checkpoint_kind": kind,
                                     "selected_step": int(ck["selected_step"]), "weights_sha256": weights_sha,
                                     "mat_sha256": packages[canonical[key]]["mat_sha256"],
                                     "common_val_rmse_mps2": report["best_common_val_rmse_mps2"] if kind == "best_common_val"
                                     else report["final_step_common_val_rmse_mps2"],
                                     "package_path": packages[canonical[key]]["package_path"],
                                     "canonical_package_id": canonical[key], "alias_of_identical_weights": True})
                        continue
                    model = fit.make_model(cfg, norms)
                    model.load_state_dict(ck["state_dict"], strict=True)
                    model.eval()
                    fixture_phi, fixture_pred = matlab_outputs(model, model_id, X)
                    matlab_model = export_base.matlab_model(model_id, model, 32, seed, int(ck["selected_step"]))
                    matlab_model.update({"training_group": group, "checkpoint_kind": kind,
                                         "fit_id": report["fit_id"], "weights_sha256": weights_sha,
                                         "source_checkpoint_sha256": report["source_checkpoint_sha256"],
                                         "protocol_sha256": report["protocol_sha256"]})
                    folder = OUT / "models" / "export" / model_id / group / f"seed{seed}" / kind
                    folder.mkdir(parents=True, exist_ok=True)
                    mat_path = folder / "matlab_model_and_parity.mat"
                    scipy.io.savemat(mat_path, {"model": matlab_model, "windows": X,
                                                "expected_phi": fixture_phi, "expected_output": fixture_pred},
                                     do_compression=True, long_field_names=True)
                    export_report = {
                        "status": "EXPORTED_AWAITING_ZERO_PLANT_PARITY", "package_id": candidate_id,
                        "model_id": model_id, "group": group, "seed": seed, "checkpoint_kind": kind,
                        "selected_step": int(ck["selected_step"]), "weights_sha256": weights_sha,
                        "fit_report": report["fit_id"], "source_checkpoint_sha256": report["source_checkpoint_sha256"],
                        "fixture_count": len(fixture_meta), "fixture_source_counts": pd.Series(
                            [x["source"] for x in fixture_meta]).value_counts().to_dict(),
                        "fixture_tasks": sorted({x["task"] for x in fixture_meta}),
                        "fixture_metadata": fixture_meta, "mat_file": mat_path.relative_to(ROOT).as_posix(),
                        "mat_sha256": hashlib.sha256(mat_path.read_bytes()).hexdigest(),
                        "normalizer_frozen": True, "input_dim": 14, "window": 32,
                    }
                    (folder / "export_report.json").write_text(json.dumps(export_report, indent=2, ensure_ascii=False) + "\n",
                                                                encoding="utf-8")
                    entry = {"package_path": str(folder.relative_to(ROOT).as_posix()),
                             "mat_sha256": export_report["mat_sha256"], "weights_sha256": weights_sha}
                    packages[candidate_id] = entry
                    canonical[key] = candidate_id
                    rows.append({"package_id": candidate_id, "model_id": model_id, "group": group,
                                 "seed": seed, "checkpoint_kind": kind, "selected_step": int(ck["selected_step"]),
                                 "weights_sha256": weights_sha, "mat_sha256": export_report["mat_sha256"],
                                 "common_val_rmse_mps2": report["best_common_val_rmse_mps2"] if kind == "best_common_val"
                                 else report["final_step_common_val_rmse_mps2"],
                                 "package_path": entry["package_path"], "canonical_package_id": candidate_id,
                                 "alias_of_identical_weights": False})
                    print(f"PACKAGE_EXPORTED {candidate_id} step={ck['selected_step']} fixtures=64 hash={weights_sha[:12]}",
                          flush=True)
    manifest = pd.DataFrame(rows)
    manifest.to_csv(OUT / "manifests/package_manifest.csv", index=False)
    canonical_rows = manifest.loc[~manifest.alias_of_identical_weights].copy()
    canonical_rows.to_csv(OUT / "manifests/canonical_packages.csv", index=False)
    summary = {"status": "PACKAGES_EXPORTED_AWAITING_PARITY", "package_variants": len(rows),
               "distinct_packages": len(canonical_rows), "deduplicated_variants": len(rows) - len(canonical_rows),
               "plant_starts_this_stage": 0, "created_at_utc": pd.Timestamp.now(tz="UTC").isoformat()}
    (OUT / "reports/export_state.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"EXPORT_COMPLETE variants={len(rows)} distinct={len(canonical_rows)} plant_starts=0", flush=True)


if __name__ == "__main__":
    main()
