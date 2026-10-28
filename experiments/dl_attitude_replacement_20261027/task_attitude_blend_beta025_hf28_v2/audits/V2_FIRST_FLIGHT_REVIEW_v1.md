# V2 first-flight root review

Date: 2026-10-27 (Asia/Shanghai)
Scene: `DL1018_DEV_T1_C10_W09` (DEV, W09)
Decision: **technical first-flight gate passed; continue the frozen remaining 27 scenes without code or parameter changes.**

- Run status: `COMPLETED`, `STABLE`, 20,000 transitions and 20,001 state samples; required signals finite; safety stop reason empty.
- Safety counters: motor saturation 0, generalized clip 0, tilt limit 0, attitude-head projection 0, output saturation 0.
- Raw file SHA-256: `4be87eb2b33b597cca23495e822216af1b382f0606093c89f70f768189c5f8da`, identical to `run_status.json`. The embedded HDF5 `runIdentity` exists and all 28 fields exactly equal `run_start.json`; release, code, model, position, C5, payload, B/C5 raw, scene and candidate identities match. TEST access, inertia reconstruction and Plant-truth input are false.
- Controller call timing: p50 0.1041 ms, p95 0.5528 ms, max 38.4932 ms, compared with 1 ms sample period. The max is a timing outlier and remains reported; the frozen taskbook does not make wall time a stop gate.
- Frozen scorer, candidate-only single-scene diagnostic: candidate position Q 32.5102 mm; B 10.9846 mm; C5 10.4659 mm. Candidate task SO(3) RMSE 42.3231 mrad; B 42.2008 mrad; C5 43.2726 mrad. This is a poor position result and a slight attitude loss to B on this one scene. It is not the pre-registered macro screen decision; the taskbook contains no single-scene score cutoff, and changing the rule after observing this scene would bias the screen.

The first-flight gate required exact identity, a complete stable flight, finite signals, zero actuator/head safety counts, and timing disclosure. Those conditions passed. The frozen 28-scene decision uses equal-scene macro means, so the remaining 27 scenes will run once under the already released taskbook. No tuning or scene exclusion is allowed. Stop on any incomplete/unsafe flight or runner failure; otherwise score all 28 together and decide against the pre-registered HF28 macro gates. This result is a development screen only, not independent TEST evidence.
