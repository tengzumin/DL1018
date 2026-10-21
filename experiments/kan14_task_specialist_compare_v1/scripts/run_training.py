from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "experiments" / "kan14_task_specialist_compare_v1"
SOURCE = ROOT / "experiments" / "teacher_reuse_model_screen_v1"
SEED = 2026102001
TASKS = ("HELIX", "FIG8_3D", "SQUARE")
sys.path.insert(0, str(SOURCE / "scripts"))

import fit_models as fit  # noqa: E402
from teacher_data import EpisodeBank, WindowSet, normalizers  # noqa: E402

fit.OUT = OUT


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def source_hashes() -> dict[str, str]:
    paths = {
        "experiments/teacher_reuse_model_screen_v1/scripts/fit_models.py": SOURCE / "scripts" / "fit_models.py",
        "experiments/teacher_reuse_model_screen_v1/scripts/teacher_models.py": SOURCE / "scripts" / "teacher_models.py",
        "experiments/teacher_reuse_model_screen_v1/scripts/teacher_data.py": SOURCE / "scripts" / "teacher_data.py",
        "experiments/teacher_reuse_model_screen_v1/scripts/export_fast_screen.py": SOURCE / "scripts" / "export_fast_screen.py",
        "experiments/teacher_reuse_model_screen_v1/manifests/teacher_reuse_manifest.csv": SOURCE / "manifests" / "teacher_reuse_manifest.csv",
        "experiments/teacher_reuse_model_screen_v1/reports/data_interface_audit.json": SOURCE / "reports" / "data_interface_audit.json",
        "experiments/teacher_reuse_model_screen_v1/models/official/KAN14/seed2026102001/fit_report.json": SOURCE / "models" / "official" / "KAN14" / f"seed{SEED}" / "fit_report.json",
        "experiments/teacher_reuse_model_screen_v1/models/official/KAN14/seed2026102001/final_step.pt": SOURCE / "models" / "official" / "KAN14" / f"seed{SEED}" / "final_step.pt",
        "experiments/teacher_reuse_model_screen_v1/local_runtime/position_only_search_options.m": SOURCE / "local_runtime" / "position_only_search_options.m",
        "experiments/teacher_reuse_model_screen_v1/local_runtime/position_only_search_head_step.m": SOURCE / "local_runtime" / "position_only_search_head_step.m",
        "experiments/teacher_reuse_model_screen_v1/local_runtime/position_stage1_model_forward_v2.m": SOURCE / "local_runtime" / "position_stage1_model_forward_v2.m",
        "experiments/teacher_reuse_model_screen_v1/local_runtime/run_episode_dl1018.m": SOURCE / "local_runtime" / "run_episode_dl1018.m",
        "experiments/teacher_reuse_model_screen_v1/local_runtime/run_dl1018_closed_loop.m": SOURCE / "local_runtime" / "run_dl1018_closed_loop.m",
        "experiments/kan14_task_specialist_compare_v1/scripts/run_training.py": OUT / "scripts" / "run_training.py",
        "experiments/kan14_task_specialist_compare_v1/scripts/prepare_cleanup.py": OUT / "scripts" / "prepare_cleanup.py",
        "experiments/kan14_task_specialist_compare_v1/TASK_PROMPT_SOURCE.md": OUT / "TASK_PROMPT_SOURCE.md",
        "configs/effective_config.mat": ROOT / "configs" / "effective_config.mat",
        "configs/scene_specs.csv": ROOT / "configs" / "scene_specs.csv",
        "reports/POSITION_DEV.csv": ROOT / "reports" / "POSITION_DEV.csv",
        "logs/attempt_index.csv": ROOT / "logs" / "attempt_index.csv",
        "logs/episode_index.csv": ROOT / "logs" / "episode_index.csv",
        "models/position/initial/normalizer.npz": ROOT / "models" / "position" / "initial" / "normalizer.npz",
    }
    missing = [k for k, v in paths.items() if not v.is_file()]
    if missing:
        raise FileNotFoundError("Missing frozen protocol source(s): " + ", ".join(missing))
    return {key: sha256(path) for key, path in paths.items()}


def protocol_payload() -> dict:
    return {
        "task": "DL1018_KAN14_TASK_SPECIALIST_COMPARE_V1",
        "status": "FROZEN_BEFORE_FIRST_FIT",
        "created_at_utc": utcnow(),
        "user_override": "Single seed only: 2026102001. Seed 2026102002 intentionally omitted.",
        "seed": SEED,
        "tasks": list(TASKS),
        "question": "With the same KAN14 architecture, X14 input, teacher source, normalizer and total optimizer-step budget, do three task-specific experts outperform one shared KAN14 on the same task-matched DEV24 scenes?",
        "data": {
            "source_manifest": "experiments/teacher_reuse_model_screen_v1/manifests/teacher_reuse_manifest.csv",
            "roles": ["B", "POS_OFF"], "splits": ["train", "val"],
            "per_task": {"train_episodes": 512, "train_B": 256, "train_POS_OFF": 256,
                         "val_episodes": 32, "val_B": 16, "val_POS_OFF": 16,
                         "physical_train_scenes": 256, "physical_val_scenes": 16,
                         "train_endpoints_per_episode": 394, "val_endpoints_per_episode": 394,
                         "train_windows": 201728, "val_windows": 12608},
            "train_total_episodes": 1536, "val_total_episodes": 96,
            "train_total_windows": 605184, "val_total_windows": 37824,
            "endpoint_zero_based": "31,36,...,1996; stride 5; 394 endpoints per episode",
            "normalizer_id": "TEACHER_TRAIN_INITIAL_X14_PLUS_TRAIN_X20_EXTRAS",
            "task_filtering": "Filter by manifest task after preserving TRAIN/VAL and B/POS_OFF membership; renormalize each filtered task's existing hierarchical endpoint weights to sum exactly 1. Do not use DEV/TEST for training, normalization, or checkpoint selection.",
            "student_data": "excluded", "new_training_data": 0, "test_accessed": False,
        },
        "comparison": {
            "shared": {"model_id": "KAN14", "seed": SEED,
                       "checkpoint": "experiments/teacher_reuse_model_screen_v1/models/official/KAN14/seed2026102001/final_step.pt",
                       "steps": 60000},
            "experts": [{"model_id": f"KAN14_{task}", "task": task, "seed": SEED, "steps": 20000,
                         "checkpoint_kind_for_closed_loop": "final_step"} for task in TASKS],
            "fit_count": 3, "additional_optimizer_steps": 60000,
            "all_random_initialization": True, "shared_warm_start": False,
            "matched_initialization_within_seed": True,
        },
        "training": {"optimizer": "Adam", "lr": 1e-3, "weight_decay": 1e-5,
                     "batch_size": 256, "eval_interval_steps": 1000,
                     "loss": "mean_axis SmoothL1(pred/3,target_clip/3), one hierarchical sample weight; unbiased N/batch scaling",
                     "architecture": "existing KAN14", "input_dim": 14, "window_contract": 32,
                     "context_length": 1, "parameter_count": 4163},
        "head_and_plant": {
            "head_type": "FEATURE", "gamma": 12, "kappa": 1, "PCF": True,
            "position_rbf_output": False, "position_rbf_update": False,
            "attitude_controller": "original B attitude RBF, output and update enabled",
            "plant": "existing B Plant, fixed C0/J0, actuator/mass/reference/wind/initial state, 1 ms integration, existing physical stop conditions",
            "position_update_hz": 100, "plant_dt_s": 0.001, "application": "1 kHz held output / ZOH",
            "state_bound": 60, "leakage": 0.002, "beta_rise_s": 1.8,
            "output_dmax_mps2": [3, 3, 3],
            "X14": ["position error xyz", "position sliding surface xyz", "Euler xyz", "zero-compensation preview thrust and m1", "four raw arm commands"],
            "controller_state_reset_each_episode": True,
        },
        "dev24": {"scene_manifest": "reports/POSITION_DEV.csv", "scenes": 24,
                   "shared_runs": 24, "expert_runs": 24, "runs_this_single_seed": 48,
                   "expert_routing": "HELIX expert on HELIX eight scenes; FIG8_3D expert on FIG8_3D eight scenes; SQUARE expert on SQUARE eight scenes.",
                   "baseline": "same-scene B DEV24 results and raw data reused; no B refly",
                   "primary_metric": "Q_0_20_m", "macro": "equal-weight mean of per-scene Q_0_20_m",
                   "selection_or_early_stop": "none; complete all 48 runs unless a physical hard stop makes a run incomplete; do not select a checkpoint by DEV",
                   "test_accessed": False},
        "resource_budget": {"new_fits": 3, "new_optimizer_steps": 60000,
                             "closed_loop_plant_starts_max": 48,
                             "new_teacher_or_student_collection": 0, "test_runs": 0},
        "source_sha256": source_hashes(),
        "frozen_at_utc": utcnow(),
    }


def ensure_protocol() -> str:
    path = OUT / "protocol.json"
    proposed = protocol_payload()
    if path.is_file():
        current = json.loads(path.read_text(encoding="utf-8"))
        for key in ("task", "seed", "tasks", "data", "comparison", "training", "head_and_plant", "dev24", "resource_budget"):
            if current.get(key) != proposed.get(key):
                raise RuntimeError(f"Existing frozen protocol differs at {key}; refusing to overwrite or continue")
        if current.get("status") != "FROZEN_BEFORE_FIRST_FIT":
            raise RuntimeError("Protocol is not frozen before fit")
        return sha256(path)
    json_write(path, proposed)
    return sha256(path)


def task_windows(full: EpisodeBank, task: str, full_windows=None) -> WindowSet:
    if full_windows is None:
        full_windows = full.windows(32)
    episode_task = full.meta.task.to_numpy(dtype=str)
    task_episode_ids = np.flatnonzero(episode_task == task)
    sample_mask = episode_task[full_windows.ep_idx] == task
    if len(task_episode_ids) == 0 or not np.any(sample_mask):
        raise RuntimeError(f"No {task} episodes/windows in {full.meta.iloc[0].split}")
    remap = np.full(len(episode_task), -1, dtype=np.int32)
    remap[task_episode_ids] = np.arange(len(task_episode_ids), dtype=np.int32)
    meta = full.meta.iloc[task_episode_ids].reset_index(drop=True)
    bank = SimpleNamespace(meta=meta, x20=full.x20[task_episode_ids],
                           x14=full.x14[task_episode_ids], y=full.y[task_episode_ids],
                           raw=full.raw[task_episode_ids], phase=full.phase[task_episode_ids])
    weights64 = full_windows.weights[sample_mask].astype(np.float64)
    unnormalized_mass = float(weights64.sum())
    if not np.isclose(unnormalized_mass, 1.0 / 3.0, atol=1e-6):
        raise RuntimeError(f"Expected global task mass 1/3 before renormalization, got {unnormalized_mass}")
    weights64 /= unnormalized_mass
    data = WindowSet(bank, 32, remap[full_windows.ep_idx[sample_mask]],
                     full_windows.end_idx[sample_mask], weights64.astype(np.float32))
    expected_windows = 201728 if full.meta.iloc[0].split == "train" else 12608
    if len(data.weights) != expected_windows:
        raise RuntimeError(f"Unexpected {full.meta.iloc[0].split} {task} endpoint count: {len(data.weights)}")
    if not np.isclose(float(data.weights.sum()), 1.0, atol=2e-6):
        raise RuntimeError(f"Renormalized {task} weights do not sum to 1")
    return data


def audit_split(full: EpisodeBank, task: str, data: WindowSet, split: str) -> dict:
    meta = full.meta.loc[full.meta.task == task]
    role_counts = {k: int(v) for k, v in meta.role.value_counts().sort_index().items()}
    expected = {"B": 256, "POS_OFF": 256} if split == "train" else {"B": 16, "POS_OFF": 16}
    if role_counts != expected or len(meta) != sum(expected.values()):
        raise RuntimeError(f"Unexpected {split} {task} role/episode counts: {role_counts}")
    role_weight = {role: float(data.weights[data.role == role].sum()) for role in ("B", "POS_OFF")}
    class_weight = {f"{role}/C{c:02d}": float(data.weights[(data.role == role) & (data.bank.meta.class_index.to_numpy()[data.ep_idx] == c)].sum())
                    for role in ("B", "POS_OFF") for c in range(16)}
    task_weight = {v: float(data.weights[data.task == v].sum()) for v in sorted(set(data.task.tolist()))}
    if any(not np.isclose(v, 0.5, atol=2e-6) for v in role_weight.values()):
        raise RuntimeError(f"{split} {task} role weights are not 0.5 each: {role_weight}")
    if len(data.weights) != (201728 if split == "train" else 12608):
        raise RuntimeError("Task endpoint count differs from frozen training contract")
    return {"split": split, "task": task, "episodes": len(meta), "role_episodes": role_counts,
            "physical_scenes": int(meta.scene_id.nunique()), "windows": len(data.weights),
            "window_endpoint_contract": "31,36,...,1996; 394 per episode",
            "unnormalized_global_mass": 1.0 / 3.0, "normalized_weight_sum": float(data.weights.sum()),
            "weight_by_role": role_weight, "weight_by_role_class": class_weight,
            "weight_by_task": task_weight,
            "weight_by_role_phase": {f"{role}/phase{phase}": float(data.weights[(data.role == role) & (data.phase == phase)].sum())
                                     for role in ("B", "POS_OFF") for phase in range(6)}}


def shared_checkpoint_preflight(norms: dict) -> dict:
    folder = SOURCE / "models" / "official" / "KAN14" / f"seed{SEED}"
    report = json.loads((folder / "fit_report.json").read_text(encoding="utf-8"))
    ckpt = fit.torch.load(folder / "final_step.pt", map_location="cpu", weights_only=False)
    expected = {"model_id": "KAN14", "seed": SEED, "status": "COMPLETE", "selected_step": 60000,
                "last_step": 60000, "normalizer_id": "TEACHER_TRAIN_INITIAL_X14_PLUS_TRAIN_X20_EXTRAS",
                "parameter_count": 4163}
    for key, value in expected.items():
        if report.get(key) != value:
            raise RuntimeError(f"Shared KAN14 report mismatch for {key}: {report.get(key)!r}")
    if ckpt.get("model_id") != "KAN14" or int(ckpt.get("seed", -1)) != SEED or int(ckpt.get("selected_step", -1)) != 60000:
        raise RuntimeError("Shared KAN14 final checkpoint identity/step mismatch")
    base_cfg = {"model_id": "KAN14", "family": "KAN", "input_dim": 14, "window": 32, "group": "CURRENT"}
    model = fit.make_model(base_cfg, norms)
    model.load_state_dict(ckpt["state_dict"], strict=True)
    if not np.array_equal(model.input_mu.detach().cpu().numpy().reshape(-1), norms["X14"]["mu"]):
        raise RuntimeError("Shared checkpoint X14 mean differs from frozen teacher normalizer")
    if not np.array_equal(model.input_sigma.detach().cpu().numpy().reshape(-1), norms["X14"]["sigma"]):
        raise RuntimeError("Shared checkpoint X14 sigma differs from frozen teacher normalizer")
    return {"status": "PASS", "model_id": "KAN14", "seed": SEED, "selected_step": 60000,
            "parameter_count": sum(p.numel() for p in model.parameters()),
            "normalizer_id": report["normalizer_id"], "fit_report_path": str((folder / "fit_report.json").relative_to(ROOT).as_posix()),
            "fit_report_sha256": sha256(folder / "fit_report.json"),
            "checkpoint_path": str((folder / "final_step.pt").relative_to(ROOT).as_posix()),
            "checkpoint_sha256": sha256(folder / "final_step.pt"),
            "normalizer_state_exact_match": True}


def preflight(protocol_hash: str) -> tuple[dict, dict]:
    manifest = rows(SOURCE / "manifests" / "teacher_reuse_manifest.csv")
    by_split_task: dict[tuple[str, str], list[dict]] = {}
    for row in manifest:
        if row["role"] not in {"B", "POS_OFF"}:
            raise RuntimeError(f"Unexpected non-teacher role in frozen manifest: {row['role']}")
        if row["split"] not in {"train", "val"}:
            raise RuntimeError(f"Forbidden split in teacher manifest: {row['split']}")
        by_split_task.setdefault((row["split"], row["task"]), []).append(row)
    expected = {("train", task): 512 for task in TASKS} | {("val", task): 32 for task in TASKS}
    actual = {key: len(value) for key, value in by_split_task.items()}
    if actual != expected:
        raise RuntimeError(f"Teacher manifest task counts differ from contract: {actual}")
    for (split, task), values in by_split_task.items():
        counts = {role: sum(r["role"] == role for r in values) for role in ("B", "POS_OFF")}
        expect = 256 if split == "train" else 16
        if counts != {"B": expect, "POS_OFF": expect}:
            raise RuntimeError(f"{split} {task} role counts differ from contract: {counts}")

    norms = normalizers()
    if len(norms["X14"]["mu"]) != 14 or len(norms["X14"]["sigma"]) != 14 or np.any(norms["X14"]["sigma"] <= 0):
        raise RuntimeError("Invalid frozen X14 normalizer")
    shared = shared_checkpoint_preflight(norms)
    full_train = EpisodeBank("train")
    full_val = EpisodeBank("val")
    if len(full_train.meta) != 1536 or len(full_val.meta) != 96:
        raise RuntimeError("Loaded teacher cache does not match 1536 TRAIN / 96 VAL rows")
    train_full_windows, val_full_windows = full_train.windows(32), full_val.windows(32)
    weight_rows = []
    for task in TASKS:
        train_data = task_windows(full_train, task, train_full_windows)
        val_data = task_windows(full_val, task, val_full_windows)
        weight_rows.extend((audit_split(full_train, task, train_data, "train"),
                            audit_split(full_val, task, val_data, "val")))
    audit = {"status": "PASS_DATA_AND_WEIGHT_PREFLIGHT", "protocol_sha256": protocol_hash,
             "seed": SEED, "new_fit_count": 3, "seed_2026102002_fit_count": 0,
             "student_records_read": 0, "dev_test_records_read_for_fitting": 0,
             "shared_checkpoint": shared, "normalizer_id": "TEACHER_TRAIN_INITIAL_X14_PLUS_TRAIN_X20_EXTRAS",
             "X14_mu": norms["X14"]["mu"].tolist(), "X14_sigma": norms["X14"]["sigma"].tolist(),
             "task_split_audits": weight_rows,
             "aggregate": {"train_episodes": len(full_train.meta), "val_episodes": len(full_val.meta),
                           "train_windows": len(train_full_windows.weights), "val_windows": len(val_full_windows.weights),
                           "train_weight_sum": float(train_full_windows.weights.sum()),
                           "val_weight_sum": float(val_full_windows.weights.sum())},
             "created_at_utc": utcnow()}
    json_write(OUT / "reports" / "DATA_AND_WEIGHT_AUDIT.json", audit)
    return audit, shared


def initial_state(protocol_hash: str) -> None:
    state_path = OUT / "state" / "state.json"
    if state_path.is_file():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state.get("protocol_sha256") != protocol_hash:
            raise RuntimeError("Existing state belongs to a different frozen protocol")
        return
    json_write(state_path, {"task": "DL1018_KAN14_TASK_SPECIALIST_COMPARE_V1",
                            "status": "IN_PROGRESS", "phase": "TASK_EXPERT_TRAINING",
                            "protocol_sha256": protocol_hash, "seed": SEED,
                            "fits_expected": 3, "fits_completed": [], "optimizer_steps_completed_total": 0,
                            "plant_starts": 0, "started_at_utc": utcnow(), "updated_at_utc": utcnow()})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    protocol_hash = ensure_protocol()
    audit, _ = preflight(protocol_hash)
    print(f"KAN14_TASK_PREFLIGHT_PASS seed={SEED} tasks=3 fits=3 steps=60000 train_windows_per_task=201728 val_windows_per_task=12608", flush=True)
    if args.preflight_only:
        return

    initial_state(protocol_hash)
    schedule = {"official_eval_interval": 1000, "fast_eval_interval": 1000}
    norms = normalizers()
    full_train, full_val = EpisodeBank("train"), EpisodeBank("val")
    train_full_windows, val_full_windows = full_train.windows(32), full_val.windows(32)
    completed: list[str] = []
    step0_hashes: dict[str, str] = {}
    for task in TASKS:
        config = {"model_id": "KAN14", "family": "KAN", "input_dim": 14, "window": 32,
                  "group": f"TASK_{task}"}
        train_data = task_windows(full_train, task, train_full_windows)
        val_data = task_windows(full_val, task, val_full_windows)
        fit.seed_all(SEED)
        initial_model = fit.make_model(config, norms)
        digest = hashlib.sha256()
        for name, value in sorted(initial_model.state_dict().items()):
            digest.update(name.encode("utf-8"))
            digest.update(value.detach().cpu().contiguous().numpy().tobytes())
        step0_hashes[task] = digest.hexdigest()
        print(f"TASK_KAN14_FIT_START task={task} seed={SEED} train={len(train_data.weights)} val={len(val_data.weights)} weight_sum={train_data.weights.sum():.8f} steps=20000", flush=True)
        report = fit.fit_one(config, SEED, train_data, val_data, norms, schedule,
                             protocol_hash, f"TASK_{task}", 20000)
        if report["status"] != "COMPLETE" or int(report["last_step"]) != 20000:
            raise RuntimeError(f"Incomplete task expert {task}: status={report['status']} step={report['last_step']}")
        completed.append(f"TASK_{task}_KAN14_SEED{SEED}")
        fit.update_state(f"TASK_{task}", "", completed, 0, "FIT_COMPLETE", len(completed))
        print(f"TASK_KAN14_FIT_COMPLETE task={task} seed={SEED} best={report['selected_teacher_val_rmse_mps2']:.8g}@{report['selected_step']} final={report['final_step_teacher_val_rmse_mps2']:.8g} steps_per_s={report['steps_per_s_mean']:.2f}", flush=True)

    if len(set(step0_hashes.values())) != 1:
        raise RuntimeError(f"Matched-seed KAN initial weights differ by task: {step0_hashes}")
    json_write(OUT / "reports" / "MATCHED_INITIALIZATION.json", {
        "status": "PASS", "seed": SEED, "task_initial_state_sha256": step0_hashes,
        "identical_across_tasks": True,
        "meaning": "The same seed, architecture and frozen normalizer reproduce identical initial state_dicts before each independent task fit.",
    })
    state = json.loads((OUT / "state" / "state.json").read_text(encoding="utf-8"))
    state.update({"status": "IN_PROGRESS", "phase": "TASK_EXPERT_TRAINING_COMPLETE",
                  "fits_completed": completed, "optimizer_steps_completed_total": 60000,
                  "active_fit": None, "updated_at_utc": utcnow()})
    json_write(OUT / "state" / "state.json", state)
    print(f"TASK_KAN14_TRAINING_COMPLETE seed={SEED} fits={len(completed)}/3 steps=60000", flush=True)


if __name__ == "__main__":
    main()
