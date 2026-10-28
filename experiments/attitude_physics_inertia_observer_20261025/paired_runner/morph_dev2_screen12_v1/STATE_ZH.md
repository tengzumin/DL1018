# Screen12 state

## Root review checkpoint — 2026-10-25 16:17 CST (before root release)

- Scope: fixed 12-scene VAL subset from the C5 DEV72 cohort; baseline is C5 position plus B attitude RBF, candidate is the same C5 position stack with the frozen physics/observer attitude replacement.
- Static review: PowerShell 7 static checker passed after correcting the report budget denominator to 24; MATLAB `checkcode` parsed the runner and reported style/performance advisories only.
- No-Plant preparation manifest contains the fixed 12 scene IDs, reports zero Plant calls and training runs, and marks TEST as unaccessed.
- Root has not yet issued the separate screen12 release at this checkpoint. No screen12 closed-loop call has started. The frozen lock and signed release, if issued afterward, are the only authority to run this batch.
- Scope limits: 24 paired-arm calls / 480,000 transitions / 10 GiB output cap; no training, TEST, retry, C7, or history overwrite. Existing C02 and T3 pairs are reused only as separately documented DEV evidence and are excluded from this 12-scene average.
- After completion, preserve every raw/status file and review the full paired screen gate before any DEV72 expansion.