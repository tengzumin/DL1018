from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat, savemat

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "no_position_gru_notch_T3_single_v1" / "DUAL_NOTCH_EVENTWISE_PARITY_INPUTS_v1.mat"
OUT = HERE / "MATLAB_EVENTWISE_PARITY_INPUTS_v1.mat"
META = HERE / "MATLAB_EVENTWISE_PARITY_INPUTS_v1.json"
CENTERS = (2.2, 3.2, 3.7, 4.8)
Q = (4.0, 4.0, 4.0, 4.0)
FS = 100.0


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    d = loadmat(SOURCE)
    action = np.asarray(d["scene2_action_mps2"], dtype=np.float64)
    events = np.asarray(d["scene2_event"], dtype=np.uint8).reshape(-1).astype(bool)
    if action.shape != (3, 20000) or events.size != 20000 or not np.isfinite(action).all():
        raise SystemExit("unexpected frozen TRAIN action/event input")
    bs, aa = [], []
    for center, q in zip(CENTERS, Q):
        w0 = 2 * np.pi * center / FS
        alpha = np.sin(w0) / (2 * q)
        scale = 1 + alpha
        bs.append(np.array([1, -2 * np.cos(w0), 1], dtype=np.float64) / scale)
        aa.append(np.array([1, -2 * np.cos(w0) / scale, (1 - alpha) / scale], dtype=np.float64))
    b, a = np.stack(bs), np.stack(aa)
    sections = np.zeros((4, 3, 4), dtype=np.float64)
    held = np.zeros(3, dtype=np.float64)
    initialized = False
    expected = np.zeros_like(action)
    clips = 0
    for k in range(action.shape[1]):
        if not events[k]:
            expected[:, k] = held
            continue
        x = action[:, k]
        if not initialized:
            if np.max(np.abs(x)) > 1e-12:
                sections[:] = x[None, :, None]
                held = x.copy()
                initialized = True
            else:
                held = x.copy()
            expected[:, k] = held
            continue
        y = x.copy()
        for j in range(4):
            st = sections[j]
            u = b[j, 0] * y + b[j, 1] * st[:, 0] + b[j, 2] * st[:, 1] \
                - a[j, 1] * st[:, 2] - a[j, 2] * st[:, 3]
            sections[j] = np.column_stack((y, st[:, 0], u, st[:, 2]))
            y = u
        applied = np.clip(y, -3.0, 3.0)
        clips += int(np.count_nonzero(np.abs(y - applied) > 1e-12))
        held = applied
        expected[:, k] = applied
    savemat(OUT, {
        "scene_id": "DL1018_DEV_T3_C09_W09",
        "action_mps2": action,
        "event": events.astype(np.uint8),
        "expected_mps2": expected,
        "b": b,
        "a": a,
        "clip_count": np.array([[clips]], dtype=np.float64),
    }, do_compression=True)
    META.write_text(json.dumps({
        "status": "PASS_TRAIN_PARITY_INPUTS_READY",
        "scene_id": "DL1018_DEV_T3_C09_W09",
        "source_path": str(SOURCE.resolve()),
        "source_sha256": sha(SOURCE),
        "input_path": str(OUT.resolve()),
        "input_sha256": sha(OUT),
        "centers_hz": list(CENTERS),
        "quality_factor_each": list(Q),
        "sample_rate_hz": FS,
        "transitions": 20000,
        "event_count": int(events.sum()),
        "expected_clip_count": clips,
        "Plant_calls": 0,
        "TEST_read": False,
        "VAL_read": False,
        "inertia_reconstruction_enabled": False,
    }, indent=2) + "\n", encoding="utf-8")
    print(f"N4_PARITY_INPUT={OUT}")


if __name__ == "__main__":
    main()
