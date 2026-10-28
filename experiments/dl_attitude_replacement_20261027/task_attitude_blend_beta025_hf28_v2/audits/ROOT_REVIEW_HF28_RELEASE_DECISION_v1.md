# Root review: beta=0.25 HF28 candidate screen

Date: 2026-10-27 (Asia/Shanghai)  
Decision: **APPROVE exactly one candidate-only, 28-scene W09-W14 DEV/VAL screen.** This is an engineering screen; passing it is not a paper result and does not authorize DEV72 expansion or TEST access.

## Candidate and question

The candidate keeps the frozen C5/DSSM14 M110 position loop and fixed `J0`, with the existing GRU_STREAM attitude replacement and online tracking head. Its only new active change is a fixed `beta=0.25` shortest-geodesic SO(3) blend from the position-loop attitude target toward the same-step trajectory task attitude. The task attitude uses only exogenous trajectory acceleration and yaw. No RBF attitude output/update, inertia reconstruction, `Jhat/Jdot`, Plant truth deployment input, training, or parameter search is enabled.

The screen asks whether this blend can improve actual high-frequency task-attitude RMSE over both frozen B and C5 while keeping position Q strictly below B and within 5% of C5. The full 28-scene cohort is 10 DEV and 18 VAL scenes; all are W09-W14. The frozen numeric B/C5 values match `FULL72_PAIRED_SCORE_v1.csv` exactly for every selected row. TEST is sealed.

## Independent checks completed

- The bounded scene-pair preflight returned `PASS_SCENE_ONLY`: all 28 payload/B/C5 input hashes matched; B identity and scene binding passed 28/28; C5 scene ID, TEST flag, and the five allowlisted scene fields passed 28/28. Six legacy C5 raws lack `external_identity_sha256`; the field is never inferred, and the C5 comparison remains explicitly provisional. No baseline `log` or metric was read or recomputed.
- A no-Plant preparation dry run for `DL1018_DEV_T1_C10_W09` passed. Its GRU model hash matched the locked manifest; the generated GRU options retained the frozen DSSM14 position identity; controller `J0` matched the locked C5 config and controller `Jdot` was zero.
- The SO(3) helper matched an independent matrix-log/exponential calculation with Frobenius error `3.0118316749220701e-16` on a nontrivial test vector.
- `activate_paired_runner` resolved all copied MATLAB sources to the isolated source tree. The required runner, preparation, GRU, scorer-support, and plant-parameter functions all resolved to the copied tree.
- MATLAB `checkcode` reported zero findings for the pair auditor, release validator, attempt driver, batch driver, and SO(3) helper. The Python scorer parsed successfully with `ast.parse`.
- The first full release-validator call correctly stopped before raw/Plant access because MATLAB compared the authorized scene IDs as a column vector against the manifest's row vector. The validator now normalizes both arrays to columns. A fresh release/code lock then passed `validate_beta025_hf28_release` for all 28 scenes and the 64-file source lock.
- The scorer binds each candidate raw to its same-attempt `run_start.json` and `run_status.json`, checks the expected scene/model/release/input identities and raw SHA, requires the embedded `runIdentity` group, and leaves missing, mismatched, or unreadable candidates unscored. It recomputes candidate timing and safety gates from that raw; B/C5 scores remain manifest-only.
- The batch has an atomic exclusive lock, rejects direct attempt calls outside that lock, performs no retries, caps candidate output at 5 GiB, and stops before a new flight below 30 GiB free space.
- At approval time, there were no candidate attempt markers and no active MATLAB/Octave process. No closed-loop flight, training, baseline rerun, or TEST access has occurred in this HF28 study.

## Frozen artifacts and hashes

- Taskbook: `ROOT_TASKBOOK_HF28_BETA025_DRAFT_v1.md`, SHA-256 `0fa802389250cd9a4bc84f8b5f949a2e60716f9290d17feee02b21927b1cc69e`.
- Execution manifest: SHA-256 `9bf6f1e2e038eb1cd93ea3da928a4e3be8afbb130609f442b3df70b17050ce22`.
- Input manifest: SHA-256 `ed20edfee69af078008b4697aec17f5d6389c4842682eb0b3d8d416c7b7b2164`.
- MATLAB source lock: 64 `.m` files, SHA-256 `bf3e970661291e9c9d679d4fdc134329f69a5505f3ba3d748790c681c2021861`.
- Candidate scorer: SHA-256 `ff873573093259d885577a7f2238b52bf9df50eb8f43692059a53222b72242ca`.
- Pair preflight receipt: SHA-256 `b0609512f700e52c1b47a1edb54bd6c56f2df42a918631d24e27c7366d01d7a5`.
- Pair preflight review: SHA-256 `3a7e293d3a07d020dbe430139f364f77e970c83779183969963f780992d33a68`.

## Approval boundary

The release is limited to 28 sequential candidate calls under the exact hashes above. Reuse existing B/C5 scores; do not rerun either baseline. After scoring, stop for an independent root review before any larger development run. If a gate fails, retain every attempt and score row, do not retry a scene, and do not open TEST. The known C5 attestation gap and parent-audit status must remain visible in every result summary.
