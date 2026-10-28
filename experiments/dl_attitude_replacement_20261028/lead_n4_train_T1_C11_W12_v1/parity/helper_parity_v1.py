"""Run a deterministic Python/MATLAB parity check for the fixed-lead helper."""
import csv
import math
import pathlib
import shutil
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent
INPUT = ROOT / "PARITY_INPUT_v1.csv"
ACTUAL = ROOT / "MATLAB_PARITY_ACTUAL_v1.csv"

BP = (
    (0.007820208033497190, 0.015640416066994380, 0.007820208033497190, 1.0, -1.765303227856989, 0.8375337582790457),
    (1.0, -2.0, 1.0, 1.0, -1.8957260285978639, 0.9145978814242006),
)
LO = (
    (0.0020805671354922929, 0.0041611342709845858, 0.0020805671354922929, 1.0, -1.8925388671474799, 0.90417385083708357),
    (1.0, -2.0, 1.0, 1.0, -1.9667173311097974, 0.96797153273500514),
)


def fixture():
    rows = []
    for k in range(800):
        t = k / 100.0
        u = [
            0.62 * math.sin(2 * math.pi * 0.45 * t) + 0.48 * math.sin(2 * math.pi * 3.3 * t) + 0.08,
            0.55 * math.sin(2 * math.pi * 0.72 * t + 0.3) + 0.36 * math.sin(2 * math.pi * 7.1 * t),
            0.50 * math.sin(2 * math.pi * 1.15 * t - 0.2) + 0.42 * math.sin(2 * math.pi * 4.2 * t),
        ]
        if 4.0 <= t < 4.12:
            u[0] += 2.7
        if abs(t - 6.01) < 1e-12:
            u[0] += 6.0  # Exercise the fixed output limiter in this helper-only fixture.
        rows.append([t, int(k % 5 != 0), *u])
    return rows


def sos_step(sos, state, x):
    y = list(x)
    for j, row in enumerate(sos):
        next_y = [row[0] * y[a] + state[a][j][0] for a in range(3)]
        for a in range(3):
            state[a][j][0] = row[1] * y[a] - row[4] * next_y[a] + state[a][j][1]
            state[a][j][1] = row[2] * y[a] - row[5] * next_y[a]
        y = next_y
    return y


def n4_init():
    b_bank, a_bank = [], []
    for f in (2.2, 3.2, 3.7, 4.8):
        w0 = 2 * math.pi * f / 100.0
        alpha = math.sin(w0) / 8.0
        scale = 1 + alpha
        b_bank.append((1 / scale, -2 * math.cos(w0) / scale, 1 / scale))
        a_bank.append((1.0, -2 * math.cos(w0) / scale, (1 - alpha) / scale))
    return {"b": b_bank, "a": a_bank, "hist": [[[0.0] * 4 for _ in range(4)] for _ in range(3)], "initialized": False}


def n4_step(state, x):
    if not state["initialized"]:
        if max(abs(v) for v in x) > 1e-12:
            state["hist"] = [[[v, v, v, v] for _ in range(4)] for v in x]
            state["initialized"] = True
        return list(x)
    y = list(x)
    for j, (b, a) in enumerate(zip(state["b"], state["a"])):
        for axis in range(3):
            h = state["hist"][axis][j]
            z = y[axis]
            y[axis] = b[0] * z + b[1] * h[0] + b[2] * h[1] - a[1] * h[2] - a[2] * h[3]
            state["hist"][axis][j] = [z, h[0], y[axis], h[2]]
    return y


def expected(rows):
    bp_state = [[[0.0, 0.0] for _ in BP] for _ in range(3)]
    lo_state = [[[0.0, 0.0] for _ in LO] for _ in range(3)]
    n4 = n4_init()
    ebp = elo = ratio = gtarget = g = 0.0
    lead_x1 = [0.0] * 3
    lead_y1 = [0.0] * 3
    lead_initialized = False
    held = [0.0] * 3
    held_raw = [0.0] * 3
    held_lead = [0.0] * 3
    rho_e, rho_g = math.exp(-0.01), math.exp(-0.01 / 0.3)
    event_count = clip_count = 0
    out = []
    for t, event, *u in rows:
        clip = [False] * 3
        if event:
            event_count += 1
            bp = sos_step(BP, bp_state, u)
            lo = sos_step(LO, lo_state, u)
            ebp = rho_e * ebp + (1 - rho_e) * sum(v * v for v in bp)
            elo = rho_e * elo + (1 - rho_e) * sum(v * v for v in lo)
            ratio = ebp / (ebp + elo + 1e-8)
            raw = n4_step(n4, u)
            held_raw = list(raw)
            if not lead_initialized:
                if max(abs(v) for v in raw) > 1e-12:
                    lead_x1 = list(raw)
                    lead_y1 = list(raw)
                    lead_initialized = True
                lead = list(raw)
            else:
                lead = [(17 / 7) * raw[a] - (15 / 7) * lead_x1[a] + (5 / 7) * lead_y1[a] for a in range(3)]
                lead_x1, lead_y1 = list(raw), list(lead)
            held_lead = list(lead)
            if t < 2:
                gtarget = g = 0.0
            else:
                gtarget = min(max((ratio - 0.35) / 0.30, 0.0), 1.0)
                g = rho_g * g + (1 - rho_g) * gtarget
            unclip = [u[a] + g * (lead[a] - u[a]) for a in range(3)]
            held = [min(max(v, -3.0), 3.0) for v in unclip]
            clip = [abs(unclip[a] - held[a]) > 1e-12 for a in range(3)]
            clip_count += sum(clip)
        out.append([
            t, float(event), *u, *held, *held_raw, *held_lead,
            ebp, elo, ratio, gtarget, g, *(float(v) for v in clip),
            float(event_count), float(clip_count), float(lead_initialized),
        ])
    return out


def main():
    matlab = shutil.which("matlab") or r"C:\Program Files\MATLAB\R2025b\bin\matlab.exe"
    if not pathlib.Path(matlab).is_file():
        raise SystemExit("MATLAB executable not found on PATH; parity was not run.")
    rows = fixture()
    with INPUT.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)
    m_input = str(INPUT).replace("'", "''")
    m_output = str(ACTUAL).replace("'", "''")
    m_root = str(ROOT).replace("\\", "/").replace("'", "''")
    command = f"addpath('{m_root}');run_helper_parity_v1('{m_input}','{m_output}')"
    subprocess.run([matlab, "-batch", command], check=True, cwd=ROOT)
    with ACTUAL.open(newline="", encoding="utf-8") as f:
        actual = [[float(x) for x in row] for row in csv.reader(f) if row]
    expect = expected(rows)
    if len(actual) != len(expect) or any(len(a) != len(e) for a, e in zip(actual, expect)):
        raise SystemExit(f"Parity failed: Python rows/cols={len(expect)}/{len(expect[0])}, MATLAB={len(actual)}/{len(actual[0]) if actual else 0}")
    max_error = max(abs(a - e) for ar, er in zip(actual, expect) for a, e in zip(ar, er))
    if max_error > 2e-10:
        raise SystemExit(f"Parity failed: max_abs_error={max_error:.3g} (limit 2e-10)")
    print(f"PARITY PASS: MATLAB R2025b, rows={len(actual)}, events={int(actual[-1][22])}, clips={int(actual[-1][23])}, max_abs_error={max_error:.3g}")


if __name__ == "__main__":
    main()
