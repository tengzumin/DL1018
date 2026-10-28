from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

import h5py
import numpy as np
from scipy.io import savemat

BASE = Path(__file__).resolve().parent
TEMPLATE = BASE / "n4T3C09_v1"
BATCH = BASE / "no_position_gru_notch_train24_batch_prepare_v1/BATCH_BINDINGS_v1.json"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def n4_expected(action: np.ndarray, events: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    centers, qvals, fs = [2.2, 3.2, 3.7, 4.8], [4.0] * 4, 100.0
    bs, aa = [], []
    for f, q in zip(centers, qvals):
        w = 2 * np.pi * f / fs
        alpha = np.sin(w) / (2 * q)
        scale = 1 + alpha
        bs.append(np.array([1, -2 * np.cos(w), 1], dtype=np.float64) / scale)
        aa.append(np.array([1, -2 * np.cos(w) / scale, (1 - alpha) / scale], dtype=np.float64))
    b, a = np.stack(bs), np.stack(aa)
    state = np.zeros((4, 3, 4), dtype=np.float64)
    held = np.zeros(3, dtype=np.float64)
    initialized = False
    out = np.zeros_like(action)
    clips = 0
    for k, event in enumerate(events):
        if not event:
            out[:, k] = held
            continue
        x = action[:, k]
        if not initialized:
            if np.max(np.abs(x)) > 1e-12:
                state[:] = x[None, :, None]
                held = x.copy()
                initialized = True
            else:
                held = x.copy()
            out[:, k] = held
            continue
        y = x.copy()
        for j in range(4):
            st = state[j]
            u = b[j, 0] * y + b[j, 1] * st[:, 0] + b[j, 2] * st[:, 1] \
                - a[j, 1] * st[:, 2] - a[j, 2] * st[:, 3]
            state[j] = np.column_stack((y, st[:, 0], u, st[:, 2]))
            y = u
        held = np.clip(y, -3, 3)
        clips += int(np.count_nonzero(np.abs(y - held) > 1e-12))
        out[:, k] = held
    return out, b, a, clips


def main(scene_id: str) -> None:
    row = next((r for r in json.loads(BATCH.read_text(encoding="utf-8-sig"))["bindings"]
                if r["scene_id"] == scene_id), None)
    if row is None:
        raise SystemExit(f"scene is not in the locked TRAIN24 binding file: {scene_id}")
    if scene_id == "DL1018_DEV_T1_C00_W03":
        short, wind = "T1C00", [0.6, 0.85]
    elif scene_id == "DL1018_DEV_T1_C11_W12":
        short, wind = "T1C11", [3.7, 4.8]
    else:
        raise SystemExit("this builder handles only the two remaining predeclared scenes")
    target = BASE / f"n4{short}_v1"
    if not target.is_dir():
        raise SystemExit(f"refusing to reuse nonempty output directory: {target}")
    if any(target.iterdir()) and (not (target / "candidate_runner_work").is_dir() or
            any((target / name).exists() for name in ("RELEASE.json", "SOURCE_LOCK_NO_PLANT_v1.json",
                "SOURCE_LOCK_SINGLE_CALL_v1.json", "TRAIN_SCENE_BINDING_v1.json", "runs"))):
        raise SystemExit(f"refusing to reuse nonempty output directory: {target}")
    study_id = f"static_n4_{short}_no_position_gru_v1"
    if not (target / "candidate_runner_work").exists():
        shutil.copytree(TEMPLATE / "candidate_runner_work", target / "candidate_runner_work")
    for name in ("patch_static_n4_runner.py", "write_n4_no_plant_release.py", "write_n4_single_call_release.py",
                 "validate_static_n4_raw.py", "score_static_n4_v1.py"):
        if not (target / name).exists():
            shutil.copy2(TEMPLATE / name, target / name)
    (target / "matlab").mkdir(exist_ok=True)
    if not (target / "matlab/run_static_n4_helper_parity.m").exists():
        shutil.copy2(TEMPLATE / "matlab/run_static_n4_helper_parity.m", target / "matlab/run_static_n4_helper_parity.m")
    for folder in ("audits", "runs", "references"):
        (target / folder).mkdir(exist_ok=True)

    # Convert the shared TRAIN24 binding row into the compact flat binding used by the runner.
    binding = json.loads((TEMPLATE / "TRAIN_SCENE_BINDING_v1.json").read_text(encoding="utf-8-sig"))
    comp = row["same_scene_comparators"]
    binding.update({
        "selected_scene_id": scene_id,
        "source_order_zero_based": row["source_order_zero_based"],
        "fold_id": row["diagnostic_fold_id"],
        "external_identity_sha256": row["scene_identity_sha256"],
        "scene_payload_source_path": row["scene_payload"]["path"],
        "scene_payload_source_sha256": row["scene_payload"]["sha256"],
        "parent_raw_path": comp["parent_cosine_gru"]["raw_path"],
        "parent_raw_sha256": comp["parent_cosine_gru"]["raw_sha256"],
        "parent_status_path": comp["parent_cosine_gru"]["status_path"],
        "parent_status_sha256": comp["parent_cosine_gru"]["status_sha256"],
        "parent_run_start_path": comp["parent_cosine_gru"]["run_start_path"],
        "parent_run_start_sha256": comp["parent_cosine_gru"]["run_start_sha256"],
        "c5_raw_path": comp["C5"]["raw_path"],
        "c5_raw_sha256": comp["C5"]["raw_sha256"],
        "c5_status_path": comp["C5"]["status_path"],
        "c5_status_sha256": comp["C5"]["status_sha256"],
        "c5_run_start_path": comp["C5"]["run_start_path"],
        "c5_run_start_sha256": comp["C5"]["run_start_sha256"],
        "b72_scoring_raw_path": comp["B"]["raw_path"],
        "b72_scoring_raw_sha256": comp["B"]["raw_sha256"],
        "b72_scoring_status_path": comp["B"]["status_path"],
        "b72_scoring_status_sha256": comp["B"]["status_sha256"],
        "study_id": study_id,
        "scene_identity_sha256": row["scene_identity_sha256"],
    })
    for key in list(binding):
        if key.startswith("fold_") and key != "fold_id":
            binding.pop(key)
        if key.startswith("oof_") or key in {"local_fold_checkpoint_path", "local_fold_checkpoint_sha256",
                "weights_mat_path", "weights_mat_sha256", "fold_checkpoint_path", "fold_checkpoint_sha256"}:
            binding.pop(key, None)
    payload_src = Path(row["scene_payload"]["path"])
    payload_dst = target / "TRAIN_SCENE_PAYLOAD_v1.mat"
    shutil.copy2(payload_src, payload_dst)
    binding["local_scene_payload_path"] = str(payload_dst.resolve())
    binding["local_scene_payload_sha256"] = sha(payload_dst)
    if binding["local_scene_payload_sha256"] != row["scene_payload"]["sha256"]:
        raise SystemExit("local scene payload hash differs from the source binding")
    (target / "TRAIN_SCENE_BINDING_v1.json").write_text(json.dumps(binding, indent=2) + "\n", encoding="utf-8")

    # Bind the scene's actual C5 action/event history for MATLAB helper parity.
    c5_path = Path(comp["C5"]["raw_path"])
    with h5py.File(c5_path, "r") as f:
        action = np.asarray(f["log/stage1_position_held_applied_acceleration_mps2"][()], dtype=np.float64)
        events = np.asarray(f["log/stage1_position_event"][()], dtype=bool).reshape(-1)
    if action.shape != (3, 20000) or events.size != 20000 or not np.isfinite(action).all():
        raise SystemExit("same-scene C5 event/action arrays have unexpected shape or nonfinite values")
    expected, b, a, clips = n4_expected(action, events)
    parity_mat = target / "MATLAB_EVENTWISE_PARITY_INPUTS_v1.mat"
    savemat(parity_mat, {"scene_id": scene_id, "action_mps2": action, "event": events.astype(np.uint8),
                         "expected_mps2": expected, "b": b, "a": a,
                         "clip_count": np.array([[clips]], dtype=np.float64)}, do_compression=True)
    parity_meta = {"status": "PASS_TRAIN_PARITY_INPUTS_READY", "scene_id": scene_id,
        "source_path": str(c5_path.resolve()), "source_sha256": sha(c5_path),
        "input_path": str(parity_mat.resolve()), "input_sha256": sha(parity_mat),
        "centers_hz": [2.2,3.2,3.7,4.8], "quality_factor_each": [4,4,4,4],
        "sample_rate_hz": 100, "transitions": 20000, "event_count": int(events.sum()),
        "expected_clip_count": clips, "Plant_calls": 0, "TEST_read": False, "VAL_read": False,
        "inertia_reconstruction_enabled": False}
    (target / "MATLAB_EVENTWISE_PARITY_INPUTS_v1.json").write_text(json.dumps(parity_meta, indent=2)+"\n", encoding="utf-8")

    # Patch only scene/study literals; the N4 runner and recurrence remain identical.
    runtime = target / "candidate_runner_work/matlab/runtime"
    runner = runtime / "run_mlp15_dev72_closed_loop.m"
    text = runner.read_text(encoding="utf-8")
    text = text.replace("static_n4_T3C09_no_position_gru_v1", study_id)
    runner.write_text(text, encoding="utf-8", newline="\n")
    for name in ("prepare_static_n4_train_scene_no_plant.m", "prepare_static_n4_train_scene_single_call.m"):
        p = runtime / name
        text = p.read_text(encoding="utf-8")
        text = text.replace("static_n4_T3C09_no_position_gru_v1", study_id)
        text = text.replace("DL1018_DEV_T3_C09_W09", scene_id)
        p.write_text(text, encoding="utf-8", newline="\n")
    parity_m = target / "matlab/run_static_n4_helper_parity.m"
    parity_m.write_text(parity_m.read_text(encoding="utf-8").replace("DL1018_DEV_T3_C09_W09", scene_id),
                        encoding="utf-8", newline="\n")
    for name in ("write_n4_no_plant_release.py", "write_n4_single_call_release.py"):
        p = target / name
        text = p.read_text(encoding="utf-8")
        text = text.replace("DL1018_DEV_T3_C09_W09", scene_id).replace("static_n4_T3C09_no_position_gru_v1", study_id)
        text = text.replace('!= 20:', f'!= {row["source_order_zero_based"]}:')
        text = text.replace('sources.add(HERE / "make_static_n4_parity_inputs.py")',
            'sources.add(ROOT / "experiments/dl_attitude_replacement_20261028/build_static_n4_scene_v1.py")')
        text = text.replace('"patch_static_n4_runner.py", "make_static_n4_parity_inputs.py",',
            '"patch_static_n4_runner.py",')
        text = text.replace('sources.add(no_plant_release)',
            'sources.add(no_plant_release)\n    sources.add(ROOT / "experiments/dl_attitude_replacement_20261028/build_static_n4_scene_v1.py")')
        p.write_text(text, encoding="utf-8", newline="\n")
    for name in ("validate_static_n4_raw.py", "score_static_n4_v1.py"):
        p = target / name
        text = p.read_text(encoding="utf-8").replace("DL1018_DEV_T3_C09_W09", scene_id)
        text = text.replace("static_n4_T3C09_no_position_gru_v1", study_id)
        text = text.replace('"wind_peaks_hz": [2.2, 3.2]', f'"wind_peaks_hz": {wind}')
        p.write_text(text, encoding="utf-8", newline="\n")
    print(f"BUILT={target}")
    print(f"SCENE={scene_id} IDENTITY={row['scene_identity_sha256']} PAYLOAD={binding['local_scene_payload_sha256']}")
    print(f"PARITY_EVENTS={int(events.sum())} PARITY_CLIPS={clips} STUDY_ID={study_id}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: build_static_n4_scene_v1.py <exact TRAIN scene_id>")
    main(sys.argv[1])
