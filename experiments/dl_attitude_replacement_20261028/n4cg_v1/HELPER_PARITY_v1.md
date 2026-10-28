# Causal N4 gate helper parity v1

## Result

- Status: `PASS_MATLAB_HELPER_PARITY`; MATLAB R2025b pure-helper run; no Plant/full runner.
- Maximum absolute error across `uout`, raw N4 output, `Ebp/Elp/ratio/gtarget/g`: `2.220e-16` (limit `2.0e-10`).
- Python SOS recurrence matches SciPy `sosfilt`; fixture size: 700 events × 3 axes.
- Frozen protocol SHA-256: `cc2c0f85e9145664db7afad10fbe1fbac3bc491b206579649cedff007d460b9b`; source-lock SHA-256: `e0d4088e25c523b5323a728721113050954f9989d04fb279be31308ed68fdb91`.

## Fixed behavior

100-Hz causal SOS filters use zero initial states. Each of the 1,999 C5 position events updates filters, energy EMAs, the N4 state, and (after 2 s) the gate; 31 all-NaN warmup actions are zero inputs. Between events the output/state are held. The gate does not read wind/W/future values or use an extra position GRU.

## TRAIN24 gate limitation

The linked frozen TRAIN24 audit reports gate mean zero on 4 of 10 W09–W14 high-group scenes (T1_C10_W09, T1_C11_W12, T3_C09_W09, T3_C13_W12). Across that group, median `g>0.1` occupancy is 28.75% and median `g>=0.5` occupancy is 0.64%; this fixed estimator can underactivate on multiple high-group scenes. This is a diagnostic limitation, not a reason to tune thresholds here.

## Scope

Helper parity only. No full-runner insertion-time check, Plant call, TEST/VAL read, inertia reconstruction, parameter sweep, or change to prior N4/N2 outcome labels.
