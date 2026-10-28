# Amendment 05 — batch Python/MATLAB parity gate

Date: 2026-10-26 (Asia/Shanghai).

## Scope

The frozen taskbook requires sample-wise parity with maximum absolute error at most 1e-5 before any Plant call. The original verifier compares one selected window. To make the stated gate explicit, the batch verifier will compare five event indices (0, 1, 100, 999, 1998) from every one of the 48 B validation scenes: 240 windows (720 scalar outputs), plus one full 1,999-event causal replay through the MATLAB runtime history buffer, using the first VAL scene with nonzero morphology commands.

This is a validation-strengthening amendment only. It does not change the trained model, training data, optimizer, candidate runtime, controller, six-scene pilot, DEV set, TEST seal, or method acceptance criteria.

## Execution

After the frozen 60,000-step teacher training passes, run export_tcn_teacher_parity_batch_v3.py on CPU, then run matlab/verify_tcn_teacher_parity_batch_v3.m. The latter writes the existing MATLAB_PYTHON_PARITY_V2.json release input with added sample counts and also writes MATLAB_PYTHON_PARITY_BATCH_V3.json.

Required result: 240 windows from 48 VAL scenes, no Plant/TEST access, finite outputs, and maximum absolute Python/MATLAB difference <=1e-5 for both the 240 windows and 1,999 sequential outputs. Any failure blocks candidate release and all Plant calls.


