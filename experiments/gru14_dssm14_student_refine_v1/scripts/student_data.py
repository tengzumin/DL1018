from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "experiments" / "gru14_dssm14_student_refine_v1"
SOURCE = ROOT / "experiments" / "teacher_reuse_model_screen_v1"
sys.path.insert(0, str(SOURCE / "scripts"))
from teacher_data import EpisodeBank, WindowSet  # noqa: E402

ENDS = np.arange(31, 1999, 5, dtype=np.int32)
assert len(ENDS) == 394 and ENDS[0] == 31 and ENDS[-1] == 1996


def load_student(model_id: str, split: str):
    manifest_path = OUT / "manifests/student_episode_manifest.csv"
    manifest = pd.read_csv(manifest_path, keep_default_na=False)
    scene_meta = pd.read_csv(ROOT / "configs" / "scene_specs.csv").set_index("scene_id")
    selected = manifest.loc[(manifest.model_id == model_id) & (manifest.split == split) &
                            (manifest.status == "STABLE") & manifest.eligible_for_training.map(
                                lambda v: str(v).lower() in {"true", "1"})].copy()
    expected = 96 if split == "train" else 24
    if len(selected) != expected:
        raise RuntimeError(f"{model_id} Student {split}: need {expected} stable episodes, found {len(selected)}")
    x, y, raw, phase, rows = [], [], [], [], []
    for r in selected.itertuples(index=False):
        path = ROOT / Path(str(r.sequence_cache_path).replace("/", "\\"))
        if not path.is_file():
            raise FileNotFoundError(path)
        data = loadmat(path)
        X = np.asarray(data["X"], dtype=np.float32)
        Y = np.asarray(data["Y"], dtype=np.float32)
        Yraw = np.asarray(data["Yraw"], dtype=np.float32)
        P = np.asarray(data["phase"], dtype=np.uint8).reshape(-1)
        ready = np.asarray(data["ready"], dtype=bool).reshape(-1)
        run_id = str(np.asarray(data["run_id"]).reshape(-1)[0]).strip()
        if (run_id != str(r.run_id) or X.shape != (1999, 14) or Y.shape != (1999, 3)
                or Yraw.shape != (1999, 3) or len(P) != 1999 or ready.sum() != 1968
                or not np.array_equal(ready, np.arange(1999) >= 31)):
            raise ValueError(f"Bad Student sequence/identity/readiness: {path}")
        if not np.isfinite(X).all() or not np.isfinite(Y).all() or not np.isfinite(Yraw).all():
            raise ValueError(f"Non-finite Student sequence: {path}")
        x.append(X)
        y.append(Y)
        raw.append(Yraw)
        phase.append(P)
        scene = scene_meta.loc[str(r.scene_id)]
        rows.append({"run_id": str(r.run_id), "scene_id": str(r.scene_id), "split": split,
                     "role": "STUDENT", "task": str(scene.task), "class_index": int(scene.c),
                     "wind_cell": int(scene.w), "sequence_cache_path": str(r.sequence_cache_path)})
    bank = SimpleNamespace(x20=None, x14=np.stack(x), y=np.stack(y), raw=np.stack(raw),
                           phase=np.stack(phase), meta=pd.DataFrame(rows))
    return bank


def combine_banks(*banks):
    meta = pd.concat([b.meta for b in banks], ignore_index=True, sort=False)
    x20 = (np.concatenate([b.x20 for b in banks])
           if all(b.x20 is not None for b in banks) else None)
    return SimpleNamespace(x20=x20,
                           x14=np.concatenate([b.x14 for b in banks]),
                           y=np.concatenate([b.y for b in banks]),
                           raw=np.concatenate([b.raw for b in banks]),
                           phase=np.concatenate([b.phase for b in banks]), meta=meta)


def weighted_windows(bank, role_mass: dict[str, float]) -> WindowSet:
    meta = bank.meta.reset_index(drop=True)
    roles = meta.role.astype(str).to_numpy()
    tasks = meta.task.astype(str).to_numpy()
    classes = meta.class_index.to_numpy(dtype=np.int16)
    n_ep = len(meta)
    ep_idx = np.repeat(np.arange(n_ep, dtype=np.int32), len(ENDS))
    end_idx = np.tile(ENDS, n_ep)
    endpoint_phase = bank.phase[ep_idx, end_idx]
    weights = np.zeros(len(ep_idx), dtype=np.float64)
    for role, mass in role_mass.items():
        ep_for_role = np.flatnonzero(roles == role)
        if not len(ep_for_role):
            if mass > 0:
                raise ValueError(f"Missing source role {role}")
            continue
        task_values = sorted(set(tasks[ep_for_role]))
        for task in task_values:
            task_eps = ep_for_role[tasks[ep_for_role] == task]
            class_values = sorted(set(classes[task_eps]))
            for class_id in class_values:
                class_eps = task_eps[classes[task_eps] == class_id]
                scene_mass = mass / len(task_values) / len(class_values) / len(class_eps)
                for epi in class_eps:
                    sl = slice(epi * len(ENDS), (epi + 1) * len(ENDS))
                    phase = endpoint_phase[sl]
                    values, counts = np.unique(phase, return_counts=True)
                    count_by_phase = dict(zip(values.tolist(), counts.tolist()))
                    phase_mass = scene_mass / len(values)
                    weights[sl] = np.asarray([phase_mass / count_by_phase[int(p)] for p in phase])
    if not np.isfinite(weights).all() or not np.isclose(weights.sum(), 1.0, atol=1e-9):
        raise ValueError(f"Hierarchical weights do not sum to one: {weights.sum()}")
    return WindowSet(bank, 32, ep_idx, end_idx, weights.astype(np.float32))


def build(model_id: str) -> dict:
    teacher_train = EpisodeBank("train")
    teacher_val = EpisodeBank("val")
    student_train = load_student(model_id, "train")
    student_val = load_student(model_id, "val")
    train_teacher = weighted_windows(teacher_train, {"B": 0.5, "POS_OFF": 0.5})
    train_mix_bank = combine_banks(teacher_train, student_train)
    train_mix = weighted_windows(train_mix_bank, {"B": 0.4, "POS_OFF": 0.4, "STUDENT": 0.2})
    teacher_val_windows = weighted_windows(teacher_val, {"B": 0.5, "POS_OFF": 0.5})
    student_val_windows = weighted_windows(student_val, {"STUDENT": 1.0})
    check = {
        "status": "PASS", "model_id": model_id,
        "teacher_train_episodes": len(teacher_train.meta), "student_train_episodes": len(student_train.meta),
        "teacher_val_episodes": len(teacher_val.meta), "student_val_episodes": len(student_val.meta),
        "teacher_train_windows": len(train_teacher.weights), "student_train_windows": len(student_train.meta) * 394,
        "mix_train_windows": len(train_mix.weights), "teacher_val_windows": len(teacher_val_windows.weights),
        "student_val_windows": len(student_val_windows.weights),
        "train_teacher_role_mass": {r: float(train_teacher.weights[train_teacher.role == r].sum())
                                     for r in sorted(set(train_teacher.role.tolist()))},
        "train_mix_role_mass": {r: float(train_mix.weights[train_mix.role == r].sum())
                                for r in sorted(set(train_mix.role.tolist()))},
        "teacher_val_role_mass": {r: float(teacher_val_windows.weights[teacher_val_windows.role == r].sum())
                                  for r in sorted(set(teacher_val_windows.role.tolist()))},
        "student_val_class_counts_per_task": {t: len(set(student_val.meta.loc[student_val.meta.task == t,
                                                                               "class_index"]))
                                              for t in sorted(student_val.meta.task.unique())},
        "all_window_endpoints": len(ENDS), "endpoint_first": int(ENDS[0]), "endpoint_last": int(ENDS[-1]),
        "window_length": 32, "stride": 5, "normalizer_reestimated": False,
        "dev_test_accessed": False,
    }
    if check["teacher_train_windows"] != 605184 or check["student_train_windows"] != 37824 \
            or check["mix_train_windows"] != 643008 or check["teacher_val_windows"] != 37824 \
            or check["student_val_windows"] != 9456:
        raise RuntimeError(f"Unexpected window totals: {check}")
    OUT.joinpath("reports", "student_loader_check.json").write_text(
        json.dumps(check, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"train_teacher": train_teacher, "train_mix": train_mix,
            "teacher_val": teacher_val_windows, "student_val": student_val_windows, "check": check}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("model_id", choices=("GRU14", "DSSM14"))
    args = parser.parse_args()
    result = build(args.model_id)
    print(json.dumps(result["check"], indent=2, ensure_ascii=False))
