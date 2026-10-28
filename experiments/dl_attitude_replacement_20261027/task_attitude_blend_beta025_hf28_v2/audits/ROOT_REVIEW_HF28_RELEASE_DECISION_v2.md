# Root review: HF28 beta=0.25 V2 release decision

Date: 2026-10-27 (Asia/Shanghai)
Decision: **APPROVED, conditional first-flight gate**, for exactly 28 new candidate runner entries in V2.

## Root-cause finding from V1

The V1 batch created 10 attempt directories, recorded 9 candidate runner entries, and produced 0 raw flights. All nine statuses have Plant_calls=1, FAILED_NO_RETRY, and the same MATLAB:UndefinedFunction error. The captured stack identifies un_mlp15_dev72_closed_loop.m:280: isNetwork was read by the GRU route assertion before its sole assignment at line 351. This is an implementation-order fault before the first time-step transition, not evidence about candidate tracking or controller performance. The tenth directory (DL1018_DEV_T3_C15_W14) has no marker/start/status/raw and is not counted as a runner entry. V1 records remain unchanged; details are in ../../task_attitude_blend_beta025_hf28_v1/audits/HF28_V1_ABORT_AUDIT_v1.md.

## V2 repair audit

V2 uses an isolated source tree and a fresh output root. In un_mlp15_dev72_closed_loop.m, the exact existing assignment

isNetwork=(startsWith(method,'MLP-') || startsWith(method,'TCN-')) && isfield(opts,'network');

was moved from after the assertion to line 278, before its first read at line 281. Its expression and the assertion are unchanged. No controller gain, blend coefficient, model, feature, input, filter, limit, task, or score rule changed. The v2 release validator now binds the v2 study ID and code-lock identity. The isolated tree contains 64 MATLAB files; the frozen V2 code lock SHA-256 is 11cbffb152e358281cf64a95ccd79bfe1f5c96493017b7a7ce32b8b37ab564d5. The two-file source amendment records the upstream and final hashes.

## Inputs and comparison audit

The V2 taskbook SHA-256 is 79723521c2166a6105b91374ce8981020bc44d957316308622f7e2c8c47c3327; code lock SHA-256 is 11cbffb152e358281cf64a95ccd79bfe1f5c96493017b7a7ce32b8b37ab564d5; scorer SHA-256 is b45d0331eed4b8495d32b60f1659925719dda37dedb9bb36c98da97adca92165. Execution and input manifests retain SHA-256 9bf6f1e2e038eb1cd93ea3da928a4e3be8afbb130609f442b3df70b17050ce22 and ed20edfee69af078008b4697aec17f5d6389c4842682eb0b3d8d416c7b7b2164. The copied pair receipt is PASS_SCENE_ONLY for 28 scenes, reports no TEST read and no baseline metric recomputation, and binds the existing B/C5 pairs under its allowed scene identity fields. The six legacy C5 identity-hash gaps remain disclosed; comparison remains provisional. All external file hashes carried from the V1 release were rechecked before V2 release. The V2 directory contains no MAT, checkpoint, raw, or model binary copies.

No TEST data, B/C5 raw logs, or baseline scoring code paths are opened by the candidate batch. The existing B/C5 numeric values and identity-qualified scene pairs are reused. No training, inertia reconstruction, or Plant-truth deployment input is allowed.

## Approved execution and gates

1. Run only the first frozen scene, DL1018_DEV_T1_C10_W09, once in the V2 output tree.
2. Root reviews that attempt's exact input/run identities, raw hash, 20,000 transitions, stable/safe status, finite logged signals, zero actuator/tilt/head saturation counts, and timing. If any gate fails, stop this beta direction and preserve the attempt.
3. Only after that review passes, run the remaining 27 scenes once each with the locked batch runner. The full 28-scene gates and scoring rules remain exactly those in the taskbook; no scene is dropped, retried, or tuned.
4. Stop after this HF28 screen for a root decision. Do not expand to DEV72, rerun baselines, train, or access TEST under this release.

The V2 release authorizes at most 28 candidate runner entries, including a failed immediate entry. Its total new raw output cap is 5 GiB, and launch is prohibited below the 30 GiB free-space floor. No active MATLAB process was present at release preparation.

