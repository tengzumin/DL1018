# DEV58 candidate-only pre-run root review

Review date: 2026-10-25 (Asia/Shanghai)

## Decision

**ROOT_REVIEW_APPROVED_TO_RUN_DEV58**

Approve freezing the inputs and issuing the separate root release for the one-time 58-scene candidate-only development batch described below. This approval does not authorize training, new B/C5 runs, retries, or access to TEST48.

## Fixed scope and identity

- Run only the 58 scenes in `DEV58_PREPARED_MANIFEST_B72_V2.json`, in its frozen order, once each, as the candidate arm. The 14 independently reviewed prior candidate raws are reused to assemble the 72-scene development cohort.
- Compare every candidate against the same-scene `B_TRACEABLE_C3CORE_V1` raw/status referenced by the C5 DEV72 input lock. Do not launch B or C5 again.
- Candidate identity is the frozen DSSM14 position stack with its online position head, paired with the physics/inertia attitude observer; attitude RBF output and updates stay disabled. No training or parameter search.
- The runner allows 58 candidate calls / 1,160,000 transitions, requires stable complete runs and the existing engineering/safety checks, preserves one raw MAT per run, and stops on a failure. TEST remains sealed.

## Source and execution review

- Reviewed the MATLAB runner, its single `run_paired_observer_closed_loop(...)` call, immutable input checks, candidate/B scene-payload equality checks, raw/status SHA checks, per-run failure preservation, and complete-batch transition count.
- Reviewed the PS7 launcher, candidate lock builder, release builder, and static checker. Launcher now checks MATLAB, Octave CLI/GUI, WSL host/VM processes and the live WSL distribution list. It fails closed if the WSL query fails or any simulator/WSL instance is active. It never stops an existing process.
- Corrected failure recording so a returned candidate log preserves its valid `last_transition`, runner status, and safety-stop reason rather than replacing the transition count with an unknown marker.
- The source lock is generated after this review and must SHA-lock all runtime files, the manifest, scene CSV/receipt, comparator references, reuse reviews, this review, and the steering addendum. The release script must then freeze that exact lock without overwriting any prior lock/release.

## Validation evidence

- `static_check_morph_dev2_dev58.ps1`: **PASS** — 58 scenes, one candidate closed-loop call in the source, zero new B/C5 runs, no output-size cap, TEST false.
- MATLAB R2025b `checkcode`: completed on the changed runner, no-Plant manifest preparation, and scene builder. It reports code-quality advisories (for example preallocation/style suggestions); no syntax/runtime blocker was found. The run scope and hashes are rechecked by the freeze/release/launcher chain.
- Independent runner review initially found the Octave GUI/detached-WSL process-detection gap. The launcher was patched, and the follow-up review found no remaining launch-blocking issue. The reviewer also checked the `last_transition` error-path change.
- Immediately before release, the observed MATLAB/Octave/WSL process scan was empty and `wsl.exe --list --running --quiet` returned no running distributions. C: had approximately 186 GiB free.

## Remaining limits and safeguards

The 58-call count is this frozen DEV72 completion batch, not a cap on the broader research objective. The 30 GiB free-space floor remains a partial-write safeguard; there is no fixed artifact-size cap and no automatic deletion. If any run fails or a safety gate fails, preserve its marker/raw/status and stop the batch for review. Do not repair results in place or use this approval to unlock TEST.
