# Notch + tau=0.1 single-scene score and route audit

Frozen FULL72 `score_raw` on one completed VAL scene. The auditor made no Plant calls and did not read TEST or reconstruct inertia. Development diagnostic only; not independent validation.

| Method | Q (mm) | task SO(3) (mrad) | inner SO(3) (mrad) |
|---|---:|---:|---:|
| B | 11.405 | 61.792 | 17.915 |
| C5 | 9.990 | 65.383 | 17.965 |
| Parent_Cosine_GRU | 9.621 | 65.417 | 15.910 |
| Applied_Notch_3p5Hz_Q1 | 10.100 | 61.548 | 16.555 |
| Applied_Notch_plus_tau01 | 12.587 | 61.510 | 16.541 |

Candidate minus comparator (negative means lower error):

| Comparator | ΔQ (mm) | Δtask (mrad) | Δinner (mrad) |
|---|---:|---:|---:|
| B | +1.182 | -0.282 | -1.374 |
| C5 | +2.597 | -3.873 | -1.424 |
| Parent_Cosine_GRU | +2.966 | -3.908 | +0.631 |
| Applied_Notch_3p5Hz_Q1 | +2.486 | -0.039 | -0.014 |

## Run binding and route

Raw SHA `6cbd44c40936335c4fa8e361b23d4e8f8b3f9b683d88b828812cbdc352c443cf`; status `STABLE`; 20000 transitions; original run Plant calls=1; auditor Plant calls=0.
Release `e4756d237f5c3b597f6f5a7bddc67af793d317b6e890882bbde599f2e1cc1ae3`, source lock `bb645bb0faed705cdcc617de0d8a60a8e765645b23d594fc7328bdad18a9aca7`; 66 locked source files verified. τ=0.1 s, ρ=0.1, `FIXED_NO_RAMP`; notch 3.5 Hz, Q=1.0.
Stage1 events=1999 (indices 10–19990 every 10 ms); valid head outputs=1968, pre-ready zero-input events=31. Clip events by axis=[0, 0, 0]; peak raw/limit=0.3989.

| Check | Max abs error |
|---|---:|
| notch_recurrence_mps2 | 0.000e+00 |
| notch_clip_mps2 | 0.000e+00 |
| clip_flag_mismatches | 0.000e+00 |
| event_to_held_zoh_mps2 | 0.000e+00 |
| held_to_total_compensation_mps2 | 1.110e-16 |
| compensation_to_force_N | 0.000e+00 |
| held_force_N | 0.000e+00 |
| injected_force_N | 0.000e+00 |
| command_from_nominal_minus_comp_mps2 | 2.220e-16 |
| PCF_a_req_from_actual_command_mps2 | 0.000e+00 |

The exact logged IIR recurrence and clip reproduce the held compensation; force, position command, and PCF `a_req` match the notch-filtered path. See JSON for raw hashes and frozen-score source bindings.

Reproduce from repository root: `python experiments/dl_attitude_replacement_20261028/gru_cosine_c5_notch35_tau01_v1/audits/score_audit_notch_tau01_single_v1.py`.
