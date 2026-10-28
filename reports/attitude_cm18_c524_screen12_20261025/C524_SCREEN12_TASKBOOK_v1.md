# C5_24 attitude-RBF replacement: fixed 12-scene screen

- Status: prepared, no Plant calls.
- Candidate: frozen C5_24 final-60k model replacing the attitude RBF.
- Matched control: existing C5 position controller with its original RBF; reuse pinned raw logs.
- Overall reference: original B raw logs; its scene payload is checked against the same frozen scene.
- Legacy B scene ID suffix `_ACC_FIX_V1`, when present, is recorded and normalized only for payload identity comparison.
- B24 is not used as original B.
- Fixed scene order: DL1018_DEV_T1_C01_W15, DL1018_DEV_T1_C00_W03, DL1018_DEV_T1_C15_W14, DL1018_DEV_T1_C05_W06, DL1018_DEV_T2_C00_W04, DL1018_DEV_T2_C02_W15, DL1018_VAL_T2_C15_W09, DL1018_DEV_T2_C06_W07, DL1018_DEV_T3_C00_W05, DL1018_DEV_T3_C03_W15, DL1018_DEV_T3_C15_W14, DL1018_DEV_T3_C05_W02
- Maximum new closed-loop calls: 12; one per scene; no retry. First run the engineering scene, review its status, then run the remaining 11.
- Position C5 config and active-source inventory are preserved; only attitude-RBF flags are disabled and CM18 inference is enabled.
- No training, no TEST access, no parameter search. Output cap: 100 MiB per flight and 1 GiB total.
- Binding SHA-256: `155944827aec5c31686503034909c058b184aea8edc57483650cf8720aaff6a0`
- C5_24 checkpoint SHA-256: `1562e243ec00447d86c3f155c3153b784610aa5ed0aa68b199dcece5ccc36efd`
- C5_24 MAT SHA-256: `18bfb15c89b3e516b158b86124fce72aad2733b56a7c50ef4209942a84f6c7f4`
- Original B and matched C5+RBF are reused as references; B-vs-candidate is overall comparison, C5+RBF-vs-candidate isolates the attitude-loop replacement within the C5 stack.
