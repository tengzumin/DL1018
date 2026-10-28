# MLP15 scorer amendment v3

The earlier read-only scoring attempts are preserved:
- score v2r wrote SCORER_ERROR for all six rows because a local variable named trace shadowed MATLAB's matrix-trace function.
- score v2s stopped at its score-release amendment hash gate before reading candidate raw files because the script pointed at amendment v1 while the score-release manifest bound amendment v2.

The v2t scorer fixes the amendment path and the local trace variable name. It scores the same six v2 candidate raws and hash-bound B/C5/C5_10 references. No Plant run, raw change, metric change, tolerance change, or acceptance-gate change is made. The literal v2 advancement gate still rejects any candidate scene with a tilt-limited event.