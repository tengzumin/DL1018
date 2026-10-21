from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "experiments" / "gru14_dssm14_student_refine_v1"
SOURCE = ROOT / "experiments" / "teacher_reuse_model_screen_v1"
MATLAB = next((p for p in (Path(r"C:\Program Files\MATLAB\R2025b\bin\matlab.exe"),
                            Path(r"C:\Program Files\MATLAB\R2022b\bin\matlab.exe")) if p.is_file()), None)
SELECTION_SEED = 2026102010
TASK_T = {"HELIX": 1, "FIG8_3D": 2, "SQUARE": 3}
BRIDGE_CLASS = {"HELIX": 2, "FIG8_3D": 1, "SQUARE": 3}
CHECKPOINTS = {
    "GRU14": (2026102002, "0a97b872375ef2de5ab9f2b35c735bdf1c738d03f7e7fb02275f87da777d70eb"),
    "DSSM14": (2026102001, "af4b480aa4bc2b087ec7acd9fb9847d036e44e3eccfa43c07033cd15ec59d8bc"),
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    temp.replace(path)


def make_plan() -> pd.DataFrame:
    specs = pd.read_csv(ROOT / "configs/scene_specs.csv", keep_default_na=False)
    rows: list[pd.Series] = []
    for task_idx, task in enumerate(("HELIX", "FIG8_3D", "SQUARE")):
        train = specs.loc[(specs.split == "TRAIN") & (specs.task == task)].copy()
        assert len(train) == 256 and set(train.c.astype(int)) == set(range(16))
        winds = list(range(15)) + [[0, 5, 10][task_idx]]
        rng = np.random.default_rng(SELECTION_SEED + task_idx)
        assigned = rng.permutation(winds).tolist()
        bridge_c = BRIDGE_CLASS[task]
        assigned[bridge_c] = 8
        remaining = [w for w in winds if w != 8]
        rng.shuffle(remaining)
        for c in range(16):
            w = assigned[c] if c == bridge_c else None
            if w is None:
                w = remaining.pop()
                assigned[c] = w
            hit = train.loc[(train.c.astype(int) == c) & (train.w.astype(int) == w)]
            assert len(hit) == 1, (task, c, w, len(hit))
            rows.append(hit.iloc[0].copy())
            no_wind = train.loc[(train.c.astype(int) == c) & (train.w.astype(int) == 15)]
            assert len(no_wind) == 1
            rows.append(no_wind.iloc[0].copy())
        # Each task has every windy cell once, plus one extra rotating W00/W05/W10.
        assert sorted(assigned).count(8) == 1 and len(assigned) == 16
        assert set(assigned) == set(range(15))

    val_rows: list[pd.Series] = []
    for task_idx, task in enumerate(("HELIX", "FIG8_3D", "SQUARE")):
        val = specs.loc[(specs.split == "VAL") & (specs.task == task)].copy()
        assert len(val) == 16
        no_wind = val.loc[val.w.astype(int) == 15]
        c00 = val.loc[val.c.astype(int) == 0]
        assert len(no_wind) == len(c00) == 1
        chosen = [no_wind.iloc[0], c00.iloc[0]]
        chosen_ids = {str(r.scene_id) for r in chosen}
        rng = np.random.default_rng(SELECTION_SEED + 100 + task_idx)
        candidates = [r for _, r in val.iterrows() if str(r.scene_id) not in chosen_ids]
        rng.shuffle(candidates)
        band_count: dict[str, int] = {}
        amp_count: dict[str, int] = {}
        for r in chosen:
            band = str(r.wind_band)
            amp = str(r.amplitude_level)
            band_count[band] = band_count.get(band, 0) + 1
            amp_count[amp] = amp_count.get(amp, 0) + 1
        for _ in range(6):
            best_i = max(
                range(len(candidates)),
                key=lambda i: (
                    1.0 / (1 + band_count.get(str(candidates[i].wind_band), 0))
                    + 1.0 / (1 + amp_count.get(str(candidates[i].amplitude_level), 0)),
                    -i,
                ),
            )
            r = candidates.pop(best_i)
            chosen.append(r)
            band = str(r.wind_band)
            amp = str(r.amplitude_level)
            band_count[band] = band_count.get(band, 0) + 1
            amp_count[amp] = amp_count.get(amp, 0) + 1
        assert len(chosen) == 8 and len({int(r.c) for r in chosen}) == 8
        val_rows.extend(chosen)

    selected = pd.DataFrame(rows + val_rows).drop_duplicates("scene_id")
    assert (selected.split == "TRAIN").sum() == 96
    assert (selected.split == "VAL").sum() == 24
    for task, group in selected.loc[selected.split == "TRAIN"].groupby("task"):
        assert (group.w.astype(int) == 15).sum() == 16
        assert set(group.loc[group.w.astype(int) != 15, "w"].astype(int)) == set(range(15))
        bridge_c = BRIDGE_CLASS[task]
        assert ((group.c.astype(int) == bridge_c) & (group.w.astype(int) == 8)).any()
    for task, group in selected.loc[selected.split == "VAL"].groupby("task"):
        assert len(group) == 8 and (group.w.astype(int) == 15).sum() == 1
        assert (group.c.astype(int) == 0).sum() == 1

    plan = []
    for model_id, (seed, _) in CHECKPOINTS.items():
        for _, r in selected.iterrows():
            split = str(r.split).lower()
            role = f"P_{model_id}_STUDENT_V1"
            plan.append({
                "model_id": model_id, "original_seed": seed, "split": split,
                "role": role, "scene_id": r.scene_id, "task": r.task,
                "t": int(r.t), "c": int(r.c), "w": int(r.w),
                "wind_band": r.wind_band, "amplitude_level": r.amplitude_level,
                "r_style": r.r_style, "A1_mps": float(r.A1_mps), "A2_mps": float(r.A2_mps),
                "selection_seed": SELECTION_SEED,
                "reuse_eligible": False,
            })
    return pd.DataFrame(plan).sort_values(["model_id", "split", "task", "c", "w"]).reset_index(drop=True)


def prepare() -> None:
    protocol_path = OUT / "protocol.json"
    if protocol_path.exists():
        raise RuntimeError(f"Frozen protocol already exists; inspect and resume instead: {protocol_path}")
    source_hashes = {
        "scene_specs.csv": sha256(ROOT / "configs/scene_specs.csv"),
        "teacher_manifest.csv": sha256(SOURCE / "manifests/teacher_reuse_manifest.csv"),
        "data_interface_audit.json": sha256(SOURCE / "reports/data_interface_audit.json"),
        "teacher_models.py": sha256(SOURCE / "scripts/teacher_models.py"),
        "fit_models.py": sha256(SOURCE / "scripts/fit_models.py"),
        "export_fast_screen.py": sha256(SOURCE / "scripts/export_fast_screen.py"),
        "run_episode_dl1018.m": sha256(ROOT / "matlab/runtime/run_episode_dl1018.m"),
        "export_position_events_dl1018.m": sha256(ROOT / "matlab/data/export_position_events_dl1018.m"),
        "controller_options_dl1018.m": sha256(ROOT / "matlab/runtime/controller_options_dl1018.m"),
    }
    manifest = pd.read_csv(SOURCE / "manifests/teacher_reuse_manifest.csv", keep_default_na=False)
    for split, expected in (("train", 1536), ("val", 96)):
        subset = manifest.loc[(manifest.split == split) & manifest.role.isin(("B", "POS_OFF"))]
        assert len(subset) == expected and set(subset.role.value_counts().to_dict().values()) == {768 if split == "train" else 48}
        for value in subset.sequence_cache_path:
            path = ROOT / Path(value.replace("/", "\\"))
            assert path.is_file(), path
    checkpoint_info = {}
    for model_id, (seed, expected_hash) in CHECKPOINTS.items():
        ckpt = SOURCE / "models" / "official" / model_id / f"seed{seed}" / "final_step.pt"
        package = SOURCE / "models" / "official_export" / model_id / f"seed{seed}" / "final_step"
        mat = package / "matlab_model_and_parity.mat"
        report = json.loads((package / "export_report.json").read_text(encoding="utf-8"))
        actual = sha256(ckpt)
        assert actual == expected_hash, (model_id, actual, expected_hash)
        assert report["status"] == "MATLAB_PARITY_PASS" and report["checkpoint_sha256"] == expected_hash
        assert sha256(mat) == report["mat_sha256"]
        checkpoint_info[model_id] = {
            "original_seed": seed, "checkpoint": ckpt.relative_to(ROOT).as_posix(),
            "checkpoint_sha256": actual, "matlab_package": mat.relative_to(ROOT).as_posix(),
            "matlab_package_sha256": sha256(mat), "original_selected_step": 60000,
            "fit_report": (SOURCE / "models" / "official" / model_id / f"seed{seed}" / "fit_report.json").relative_to(ROOT).as_posix(),
            "export_report": (package / "export_report.json").relative_to(ROOT).as_posix(),
        }
    plan = make_plan()
    plan_path = OUT / "manifests/student_scene_plan.csv"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan.to_csv(plan_path, index=False)
    (OUT / "manifests/teacher_reuse_manifest.csv").write_bytes(
        (SOURCE / "manifests/teacher_reuse_manifest.csv").read_bytes()
    )
    summary = {}
    for model_id, group in plan.groupby("model_id"):
        summary[model_id] = {split: int((group.split == split).sum()) for split in ("train", "val")}
    protocol = {
        "task_id": "DL1018_GRU14_DSSM14_STUDENT_REFINE_V1",
        "status": "FROZEN_BEFORE_FIRST_PLANT",
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "project_root": ROOT.as_posix(),
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "upstream_position_head": {"head_type": "FEATURE", "gamma": 12, "kappa": 1, "PCF": True,
                                   "state_bound": 60, "leakage": 0.002, "beta_rise_s": 1.8,
                                   "output_clip_mps2": 3, "event_hz": 100, "plant_zoh_hz": 1000},
        "physical_contract": {"plant": "B2-RBF-Full-SPLIT", "keep_original_B_plant_position_attitude_bs_rbf_fixed_C0_J0": True,
                              "disable_only_position_rbf_output_and_update": True, "keep_B_attitude_rbf_and_updates": True,
                              "state_times": 20001, "transitions": 20000, "dt_s": 0.001},
        "input_contract": {"input_dim": 14, "feature_order": ["e_p(3)", "s_p(3)", "Euler(3)", "preview_thrust_per_mass(1)", "raw_arm_commands(4)"],
                           "history_events": 32, "event_hz": 100, "endpoint_zero_based": "31,36,...,1996", "stride": 5,
                           "endpoints_per_episode": 394, "independent_zero_state_window": True,
                           "normalizer_frozen_from_original_package": True},
        "checkpoints": checkpoint_info,
        "scene_selection": {"seed": SELECTION_SEED, "algorithm": "TRAIN: all per-task/class W15 plus one windy W00-W14 per class; every windy cell once per task and one extra W00/W05/W10 rotating by task; bridge W08 fixed. VAL: eight per task including W15 and C00; deterministic greedy wind-band/amplitude coverage; no outcome/label use.",
                            "counts_per_model": summary,
                            "plan_path": plan_path.relative_to(ROOT).as_posix(),
                            "plan_sha256": sha256(plan_path),
                            "selected_w15_wind_amplitudes_zero": bool((plan.loc[plan.w == 15, ["A1_mps", "A2_mps"]] == 0).all().all())},
        "teacher_reuse": {"manifest_path": "experiments/gru14_dssm14_student_refine_v1/manifests/teacher_reuse_manifest.csv",
                          "source_manifest_sha256": source_hashes["teacher_manifest.csv"],
                          "train_episodes": 1536, "val_episodes": 96,
                          "train_roles": {"B": 768, "POS_OFF": 768}, "val_roles": {"B": 48, "POS_OFF": 48}},
        "training": {"groups": ["TEACHER_CONTINUE", "STUDENT_MIX20"], "seeds": [2026102011, 2026102012],
                     "extra_steps": 10000, "total_fits": 8, "total_optimizer_steps": 80000,
                     "optimizer": "Adam", "lr": 1e-4, "weight_decay": 1e-5, "batch": 256,
                     "teacher_role_mass": {"B": 0.5, "POS_OFF": 0.5},
                     "student_mix_role_mass": {"B": 0.4, "POS_OFF": 0.4, "own_student": 0.2},
                     "loss": "mean_axis SmoothL1(pred/3,target_clip/3), exactly one hierarchical sample weight, N/batch correction",
                     "selection": "sqrt(0.8*teacher_val_RMSE^2 + 0.2*own_student_val_RMSE^2); evaluate every 1000; positive best and final 10000"},
        "canary": {"scenes": ["T1_C02_W08", "T1_C02_W15", "T2_C01_W08", "T2_C01_W15", "T3_C03_W08", "T3_C03_W15"],
                   "selection_order": ["fewest losses vs same-scene B", "lowest worst positive relative degradation", "lowest six-scene macro Q", "lowest common val", "ascending seed", "checkpoint name"]},
        "dev24": {"four_groups": ["GRU14_TEACHER_CONTINUE", "GRU14_STUDENT_MIX20", "DSSM14_TEACHER_CONTINUE", "DSSM14_STUDENT_MIX20"],
                  "lock_before_first_dev_plant": True, "all_24_per_group": True, "test_access": False},
        "source_sha256": source_hashes,
        "plant_started": False,
        "reuse_eligible_raw_episodes": 0,
    }
    write_json(protocol_path, protocol)
    print(f"PREPARE_PASS scenes={len(plan)//2} models=2 plan={plan_path.relative_to(ROOT)} sha256={sha256(plan_path)}")
    print(f"TRAIN=96/model VAL=24/model TRAIN_W15_ZERO={protocol['scene_selection']['selected_w15_wind_amplitudes_zero']} reuse=0")


def matlab_call(function: str, args: str) -> None:
    if MATLAB is None:
        raise FileNotFoundError("MATLAB executable was not found under Program Files/MATLAB")
    root = ROOT.as_posix().replace("'", "''")
    local = (OUT / "local_runtime").as_posix().replace("'", "''")
    search = (ROOT / "experiments/position_only_closed_loop_search_v1/local_runtime").as_posix().replace("'", "''")
    call_args = f",{args}" if args else ""
    script = f"addpath(genpath('{root}/matlab')); addpath(genpath('{search}'),'-begin'); addpath(genpath('{local}'),'-begin'); {function}('{root}'{call_args});"
    subprocess.run([str(MATLAB), "-batch", script], cwd=ROOT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "preflight", "collect", "train", "export", "canary", "dev", "report", "resume"))
    parser.add_argument("--first", action="store_true", help="collect one first-check episode per model only")
    parser.add_argument("--extend-edge", action="store_true",
                        help="extend completed fits whose best validation checkpoint is at the training endpoint")
    args = parser.parse_args()
    if args.command == "prepare":
        prepare()
    elif args.command == "preflight":
        has_plant = bool(list((OUT / "student_raw").rglob("plant_started.marker")))
        function = "student_refine_adapter_preflight" if has_plant else "student_refine_preflight"
        matlab_call(function, "")
        report_path = OUT / "reports" / ("runtime_adapter_preflight.json" if has_plant else "zero_plant_preflight.json")
        if has_plant:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            adapter = ROOT / "experiments/teacher_reuse_model_screen_v1/local_runtime/position_stage1_model_forward_v2.m"
            report["runtime_adapter_sha256"] = sha256(adapter)
            write_json(report_path, report)
            write_json(OUT / "reports/runtime_repair.json", {
                "status": "ENGINEERING_ADAPTER_REPAIRED_AND_PREFLIGHTED",
                "failed_attempt": "STUDENT_GRU14_TRAIN_DL1018_TRAIN_T2_C00_W14_ATTEMPT_01",
                "failure": "POSADV:ModelArchitecture: position-only adapter did not support GRU/DSSM.",
                "repair": "Use teacher-reuse position_stage1_model_forward_v2 for its supported GRU/DSSM architecture; preserve failed attempt and retry in attempt_02.",
                "adapter_path": adapter.relative_to(ROOT).as_posix(),
                "adapter_sha256": report["runtime_adapter_sha256"],
                "created_at_utc": datetime.now(timezone.utc).isoformat(),
            })
    elif args.command == "collect":
        if args.first:
            matlab_call("collect_student_refine", "{'GRU14','DSSM14'},1")
        else:
            matlab_call("collect_student_refine", "{'GRU14','DSSM14'},inf")
    elif args.command == "train":
        train_command = [sys.executable, str(OUT / "scripts/train_refine.py")]
        if args.extend_edge:
            train_command.append("--extend-edge")
        subprocess.run(train_command, cwd=ROOT, check=True)
    elif args.command == "export":
        subprocess.run([sys.executable, str(OUT / "scripts/export_refine.py")], cwd=ROOT, check=True)
    elif args.command == "canary":
        matlab_call("student_refine_package_preflight", "")
        matlab_call("run_student_refine_physical", "'BRIDGE6'")
        subprocess.run([sys.executable, str(OUT / "scripts/finalize_refine.py"), "lock"], cwd=ROOT, check=True)
    elif args.command == "dev":
        lock_path = OUT / "manifests/locked_candidates.csv"
        if not lock_path.is_file():
            subprocess.run([sys.executable, str(OUT / "scripts/finalize_refine.py"), "lock"], cwd=ROOT, check=True)
        lock = pd.read_csv(lock_path)
        if len(lock) != 4:
            raise RuntimeError("DEV requires exactly four frozen candidates selected from BRIDGE6.")
        matlab_call("run_student_refine_physical", "'DEV24'")
    elif args.command == "report":
        subprocess.run([sys.executable, str(OUT / "scripts/finalize_refine.py"), "report"], cwd=ROOT, check=True)
    elif args.command == "resume":
        subprocess.run([sys.executable, str(OUT / "scripts/finalize_refine.py"), "status"], cwd=ROOT, check=True)
    else:
        raise SystemExit(f"Stage {args.command} is not implemented yet; frozen prepare is the only available stage.")


if __name__ == "__main__":
    main()
