# DEV58 user steering addendum — 2026-10-25

This addendum records the user's latest direction and overrides only the output-size ceiling in `ATTITUDE_PHYS_INERTIA_DEV72_TASKBOOK_v1_ZH.md`.

- The user explicitly removed the 20 GiB output cap and authorized full resource scheduling. Preserve complete candidate MAT raw logs. Do not compress or replace raw output merely to meet the former cap. Monitor actual free disk space and never delete historical data automatically.
- Keep the comparison cohort fixed to the 72 locked DEV/VAL scenes. Run only the 58 candidate scenes not covered by the 12 screen scenes and 2 prior candidate raws. Reuse all 72 original B raw logs and the existing C5/candidate evidence; do not rerun B or C5.
- The candidate under evaluation is unchanged: frozen C5 DSSM14 position stack with online position head plus the physics/inertia attitude replacement. The primary paired comparator is each scene's `B_TRACEABLE_C3CORE_V1` raw referenced by the C5 DEV72 lock. The earlier diagnostic runner's locally generated B control is not a substitute for that locked B raw.
- The 12-scene screen passed the candidate-vs-locked-B position and SO(3) pilot gates: macro Q delta −2.4416233576 mm, macro SO(3) delta −0.00538716454 rad; W09–W14 and W15 means both improved on both metrics. Full DEV72 scoring remains required.
- `DL1018_DEV_T2_C02_W15` candidate raw remains marked `FAILED_ENGINEERING` by its original diagnostic run. Independent review `review/PRIOR_T2_RAW_REUSE_REVIEW_V2.json` rechecked its complete 20,000-step physical observer trace and all RBF-off traces, and independently rescored it against the locked B72 raw. The old gate used incompatible `numel` requirements for scalar flags and 3-axis histories. Preserve the original status; use the raw only with the independent review attached.
- Do not open TEST48 or start another method search in this stage. After the 58 candidate calls, independently rescore all 72 candidate raws against the locked B raws and report every scene, task, wind group, axis, stage, peak, safety and timing metric before deciding the next stage.

No Plant calls were made while preparing this addendum.
