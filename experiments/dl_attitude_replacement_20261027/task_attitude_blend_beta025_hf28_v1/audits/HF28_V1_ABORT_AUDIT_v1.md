# HF28 beta=0.25 v1 batch abort audit

- Recorded: 2026-10-27 (Asia/Shanghai)
- Release: 	ask_attitude_blend_beta025_hf28_v1/RELEASE.json
- Candidate screen: frozen 28-scene DEV/VAL W09–W14 cohort; TEST was not accessed.
- Result: **engineering-startup failure; no valid closed-loop flight was produced.**

## Verified accounting

- Nine candidate runner entries reached un_mlp15_dev72_closed_loop; each attempt status records Plant_calls=1 and FAILED_NO_RETRY.
- All nine errors are MATLAB:UndefinedFunction: isNetwork is used before assignment in the isolated runner. The first captured stack points to un_mlp15_dev72_closed_loop.m:280, called by un_beta025_hf28_attempt.m:105 and the batch at line 49.
- There are 10 ttempt_01 directories, but $emptyScene has no start marker, un_start.json, status, or raw; the process was stopped after the repeated startup fault. This directory is not counted as a runner call.
- Candidate raws: 0. Logged transitions: none. Baselines were neither rerun nor rescored. TEST was not read. No MATLAB process remained at audit time.
- The v1 batch ledger is retained as written. It records nine processed scenes and nine started calls; the tenth directory is preserved as an incomplete, non-retryable record.

## Root cause and disposition

In the isolated un_mlp15_dev72_closed_loop.m, the GRU route assertion at line 280 reads isNetwork, while the variable is only assigned at line 351. This occurs in controller setup, before the time-step simulation loop. The failure is an implementation-order bug, not candidate performance evidence.

The released v1 code, release, lock, markers, statuses, ledger, and stale batch lock are preserved without modification. No v1 scene will be retried. The corrected source and fresh 28-scene accounting are isolated in 	ask_attitude_blend_beta025_hf28_v2; v2 will move the existing isNetwork assignment before its first use without changing its expression, candidate method, inputs, or score gates.

## Failed scene entries

- `DL1018_DEV_T1_C10_W09` — `Plant_calls=1`, `MATLAB:UndefinedFunction`: 函数或变量 'isNetwork' 无法识别。
- `DL1018_DEV_T1_C11_W12` — `Plant_calls=1`, `MATLAB:UndefinedFunction`: 函数或变量 'isNetwork' 无法识别。
- `DL1018_DEV_T1_C15_W14` — `Plant_calls=1`, `MATLAB:UndefinedFunction`: 函数或变量 'isNetwork' 无法识别。
- `DL1018_DEV_T2_C09_W10` — `Plant_calls=1`, `MATLAB:UndefinedFunction`: 函数或变量 'isNetwork' 无法识别。
- `DL1018_DEV_T2_C12_W13` — `Plant_calls=1`, `MATLAB:UndefinedFunction`: 函数或变量 'isNetwork' 无法识别。
- `DL1018_DEV_T2_C14_W14` — `Plant_calls=1`, `MATLAB:UndefinedFunction`: 函数或变量 'isNetwork' 无法识别。
- `DL1018_DEV_T3_C09_W09` — `Plant_calls=1`, `MATLAB:UndefinedFunction`: 函数或变量 'isNetwork' 无法识别。
- `DL1018_DEV_T3_C10_W11` — `Plant_calls=1`, `MATLAB:UndefinedFunction`: 函数或变量 'isNetwork' 无法识别。
- `DL1018_DEV_T3_C13_W12` — `Plant_calls=1`, `MATLAB:UndefinedFunction`: 函数或变量 'isNetwork' 无法识别。

## Resource count

- v1 candidate runner calls consumed: **9 / 28**.
- Completed Plant transitions and usable raw flights: **0**.
- Remaining v1 entries: not run; v1 is closed under its no-retry rule.
- v2 authorization is independent and will be separately frozen before launch.
