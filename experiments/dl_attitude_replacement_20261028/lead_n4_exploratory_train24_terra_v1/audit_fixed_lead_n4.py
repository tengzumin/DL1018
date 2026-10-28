"""One fixed lead plus N4, replayed offline on physical TRAIN24 actions only.

This is exploratory analysis, not a runtime controller, a validation, or a
closed-loop experiment. It writes only to its own report directory.
"""
from pathlib import Path
import csv
import hashlib
import json

import numpy as np
from scipy.signal import bilinear, lfilter, lfilter_zi


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
NPZ = ROOT / "experiments/dl_attitude_replacement_20261028/position_cosine_gru_train24_causal_v1/COSINE_GRU_C5_TRAIN24_POSITION_CAUSAL_PAIRS_v1.npz"
N4_REPORT = ROOT / "experiments/dl_attitude_replacement_20261028/n4_train24_replay/TRAIN24_STATIC_N4_REPLAY_v1.json"
EXPECTED_SHA = "15d689f08fd6d8a53a64c59dbdf62b33f9b8e8a12ce083fb12834cd106df2eeb"
FS = 100.0
CENTERS = (2.2, 3.2, 3.7, 4.8)
Q = 4.0
LEAD_B, LEAD_A = bilinear([0.08, 1.0], [0.03, 1.0], FS)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def section(f):
    w = 2 * np.pi * f / FS
    alpha = np.sin(w) / (2 * Q)
    d = 1 + alpha
    return np.array([1, -2 * np.cos(w), 1]) / d, np.array([1, -2 * np.cos(w) / d, (1 - alpha) / d])


SECTIONS = [section(f) for f in CENTERS]


def response(freq, lead=False):
    z = np.exp(-2j * np.pi * np.asarray(freq) / FS)
    result = np.ones_like(z, dtype=complex)
    for b, a in SECTIONS + ([(LEAD_B, LEAD_A)] if lead else []):
        num = sum(c * z**i for i, c in enumerate(b))
        den = sum(c * z**i for i, c in enumerate(a))
        result *= num / den
    return result


def lead_response(freq):
    z = np.exp(-2j * np.pi * np.asarray(freq) / FS)
    return (LEAD_B[0] + LEAD_B[1] * z) / (LEAD_A[0] + LEAD_A[1] * z)


def filter_once(x, use_lead):
    """N4 clip followed by optional lead and final clip; 100-Hz event inputs."""
    nonzero = np.flatnonzero(np.max(np.abs(x), axis=1) > 1e-12)
    if not len(nonzero):
        return x.copy(), 0, 0
    first = nonzero[0]
    y = x[first:].copy()
    for b, a in SECTIONS:
        y, _ = lfilter(b, a, y, axis=0, zi=lfilter_zi(b, a)[:, None] * y[0])
    n4_clips = int(np.count_nonzero(np.abs(y) > 3))
    y = np.clip(y, -3, 3)
    if use_lead:
        y, _ = lfilter(LEAD_B, LEAD_A, y, axis=0, zi=lfilter_zi(LEAD_B, LEAD_A)[:, None] * y[0])
    final_clips = int(np.count_nonzero(np.abs(y) > 3))
    return np.vstack((x[:first], np.clip(y, -3, 3))), n4_clips, final_clips


def as_transition_trace(x):
    # Logged event indices are 10,20,...,19990; prior ten 1-ms steps are zero.
    return np.vstack((np.zeros((10, 3)), np.repeat(x, 10, axis=0)))


def band_rms(x, lo, hi):
    x = x - x.mean(axis=0, keepdims=True)
    n = len(x)
    win = np.hanning(n)
    psd = np.abs(np.fft.rfft(x * win[:, None], axis=0)) ** 2 / (1000 * np.sum(win**2))
    psd[1:-1] *= 2
    hz = np.fft.rfftfreq(n, 0.001)
    return float(np.sqrt(np.sum(psd[(hz >= lo) & (hz < hi)]) * 1000 / n))


def group_delay_ms(lead):
    freq = np.linspace(0.05, 0.5, 1001)
    phase = np.unwrap(np.angle(response(freq, lead)))
    return -1000 * np.gradient(phase, 2 * np.pi * freq)


def main():
    assert digest(NPZ) == EXPECTED_SHA
    old = json.loads(N4_REPORT.read_text(encoding="utf-8-sig"))
    old_by_scene = {r["scene_id"]: r for r in old["results"]}
    data = np.load(NPZ, allow_pickle=False)
    ids = [str(s) for s in data["scene_ids"]]
    assert len(ids) == 24 and set(ids) == set(old_by_scene)
    assert data["applied_acceleration_event_mps2"].shape == (24, 1999, 3)
    assert np.array_equal(data["event_index_zero_based"], np.tile(np.arange(10, 20000, 10), (24, 1)))
    rows = []
    for i, scene in enumerate(ids):
        # Non-ready outputs are represented as NaN in the logged dataset.
        logged = data["applied_acceleration_event_mps2"][i].astype(float)
        assert np.isfinite(logged[data["ready_mask"][i]]).all() and not np.isinf(logged).any()
        action = np.nan_to_num(logged)
        assert np.all(action[~data["ready_mask"][i]] == 0)
        assert np.max(np.abs(action)) <= 3 + 1e-10
        n4, n4_clips, _ = filter_once(action, False)
        combined, n4_clips_2, lead_clips = filter_once(action, True)
        original_t = as_transition_trace(action)
        n4_t = as_transition_trace(n4)
        combined_t = as_transition_trace(combined)
        denominator = band_rms(original_t, .05, .5)
        assert denominator > 0
        r_n4 = 100 * band_rms(n4_t - original_t, .05, .5) / denominator
        r_lead = 100 * band_rms(combined_t - original_t, .05, .5) / denominator
        prior = old_by_scene[scene]["low_frequency_0p05_0p5_hz"]["action_delta_rms_percent_of_before"]
        rows.append(dict(scene_id=scene, n4_lowband_delta_pct=r_n4,
                         old_n4_lowband_delta_pct=prior, n4_lead_lowband_delta_pct=r_lead,
                         n4_clip_count=n4_clips, lead_clip_count=lead_clips,
                         n4_clip_count_when_lead=n4_clips_2))
    with (HERE / "TRAIN24_FIXED_LEAD_ACTIONS_v1.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    freq = np.linspace(0, 50, 5001)
    h0, hl, h1 = response(freq), lead_response(freq), response(freq, True)
    with (HERE / "FIXED_LEAD_N4_RESPONSE_0_50HZ_v1.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["frequency_hz", "n4_magnitude", "n4_phase_deg", "lead_magnitude", "lead_phase_deg", "combined_magnitude", "combined_phase_deg"])
        for x, a, b, c in zip(freq, h0, hl, h1):
            writer.writerow([f"{x:.2f}", f"{abs(a):.12g}", "" if abs(a) < 1e-10 else f"{np.angle(a, deg=True):.9g}",
                             f"{abs(b):.12g}", f"{np.angle(b, deg=True):.9g}", f"{abs(c):.12g}",
                             "" if abs(c) < 1e-10 else f"{np.angle(c, deg=True):.9g}"])

    step = np.ones(2000)
    for b, a in SECTIONS:
        step = lfilter(b, a, step)
    step_n4 = step.copy()
    step_lead = lfilter(LEAD_B, LEAD_A, step)
    low0, low1 = group_delay_ms(False), group_delay_ms(True)
    selected = [0.05, 0.1, 0.25, 0.45, 0.5, 0.85, 1.15, 1.75, 2.0, 2.2, 2.5, 3.0, 3.2, 3.7, 4, 4.8, 5, 6, 8, 10, 20, 50]
    points = []
    for f in selected:
        a, c = complex(response(f)), complex(response(f, True))
        points.append({"frequency_hz": f, "n4_magnitude": abs(a), "n4_phase_deg": None if abs(a) < 1e-10 else float(np.angle(a, deg=True)),
                       "combined_magnitude": abs(c), "combined_phase_deg": None if abs(c) < 1e-10 else float(np.angle(c, deg=True))})
    report = {
        "status": "EXPLORATORY_FIXED_OFFLINE_REPLAY_NOT_PREDECLARED_NOT_CLOSED_LOOP",
        "scene_count": 24, "split": "TRAIN_C5_24 physical, DEV scene prefixes", "input_npz_sha256": EXPECTED_SHA,
        "script_sha256": digest(Path(__file__)), "fixed_notch_centers_hz": CENTERS, "q": Q, "event_sample_hz": FS,
        "fixed_lead_s": "(1+0.08*s)/(1+0.03*s)", "bilinear_b": LEAD_B.tolist(), "bilinear_a": LEAD_A.tolist(),
        "lowband_group_delay_ms_n4": [float(low0.min()), float(low0.max())],
        "lowband_group_delay_ms_combined": [float(low1.min()), float(low1.max())],
        "lowband_delta_percent_n4_range": [min(r["n4_lowband_delta_pct"] for r in rows), max(r["n4_lowband_delta_pct"] for r in rows)],
        "lowband_delta_percent_combined_range": [min(r["n4_lead_lowband_delta_pct"] for r in rows), max(r["n4_lead_lowband_delta_pct"] for r in rows)],
        "lowband_delta_percent_combined_median": float(np.median([r["n4_lead_lowband_delta_pct"] for r in rows])),
        "max_difference_from_old_n4_pct_points": max(abs(r["old_n4_lowband_delta_pct"] - r["n4_lowband_delta_pct"]) for r in rows),
        "n4_clip_counts": sum(r["n4_clip_count"] for r in rows), "lead_clip_counts": sum(r["lead_clip_count"] for r in rows),
        "transfer_white_noise_gain_n4": float(np.sqrt(np.trapz(abs(h0)**2, freq) / 50)),
        "transfer_white_noise_gain_combined": float(np.sqrt(np.trapz(abs(h1)**2, freq) / 50)),
        "max_combined_sampled_frequency_gain": float(abs(h1).max()),
        "step_response_no_clip_no_first_nonzero_override_n4_range": [float(step_n4.min()), float(step_n4.max())],
        "step_response_no_clip_no_first_nonzero_override_combined_range": [float(step_lead.min()), float(step_lead.max())],
        "points": points, "Plant_called": False, "VAL_read": False, "TEST_read": False,
        "inertia_reconstruction": False, "parameter_sweep": False,
    }
    (HERE / "EXPLORATORY_FIXED_LEAD_N4_RESULT_v1.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
