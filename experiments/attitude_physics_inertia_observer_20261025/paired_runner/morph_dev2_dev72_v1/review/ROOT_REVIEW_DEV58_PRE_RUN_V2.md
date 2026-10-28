# DEV58 candidate-only pre-run root review — V2 / A02

Review date: 2026-10-25 (Asia/Shanghai)

## Decision

**ROOT_REVIEW_APPROVED_TO_RUN_DEV58_A02**

Approve constructing a new V2 source lock and release for attempt A02. This approval applies only after the generated candidate lock is independently checked, the issuer freezes that exact lock, and the launcher rechecks all hashes and active-process gates. It authorizes one 58-scene candidate-only batch; it does not authorize training, new B/C5 runs, retries, or TEST48.

## A01 failure and correction

A01 stopped before the first candidate runner invocation. Its `batch_status.json` records zero runner calls, zero Plant runs, zero transitions, and zero unknown invocations. The first scene directory is empty; no candidate raw, start marker, or invocation marker exists. The concrete implementation error was looking for the wrapper's own SHA under the inherited `lock.sources` list, while the source lock stores that file in `lock.wrapper`. The runner now records `char(lock.wrapper.sha256)`; `verify_files(lock)` checks the wrapper file SHA before the batch loop. A01's lock, release, attempt directory, console, and status remain unchanged as historical evidence.

## Frozen scope and comparator

- Run exactly the 58 scene IDs and order in `DEV58_PREPARED_MANIFEST_B72_V2.json`, one candidate call per scene. Reuse the 14 already reviewed candidate raws to complete the 72-scene development cohort.
- Reuse each scene's `B_TRACEABLE_C3CORE_V1` raw/status from the C5 DEV72 input lock. Do not rerun B or C5.
- Candidate remains frozen DSSM14 position control with its existing online position head and physics/inertia attitude observer; attitude RBF output/update remain disabled. No training or parameter search.
- Preserve every new raw MAT and failure marker. No fixed artifact-size cap and no automatic deletion. Keep the 30 GiB free-space floor to avoid partial raw writes. TEST48 remains sealed.

## Source and launcher review

- The MATLAB runner makes one candidate closed-loop call in its source, verifies exact same-scene B72 payload and frozen inputs, checks every reused candidate/B raw and status SHA, checks candidate causal/safety traces, and requires all 58 calls / 1,160,000 transitions for batch completion.
- The PowerShell 7 launcher checks MATLAB, Octave CLI/GUI, WSL host/VM processes and running WSL distributions; an active simulator, active WSL distribution, or failed WSL query rejects launch without stopping any process. It rejects an existing attempt directory.
- The V2 builder/issuer create distinct V2 lock/release paths and the A02 attempt ID. The runner checks that the supplied attempt directory equals the release-bound A02 path. Independent code review found no route for A02 to read from or overwrite A01's empty first-scene directory.
- The V2 lock and release do not exist at the time of this review. Their generated records and hashes must be checked before signing the release; the launcher is the final pre-Plant gate.

## Validation evidence

- `static_check_morph_dev2_dev58.ps1`: **PASS** — 58 candidate scenes, one closed-loop call in the source, zero new B/C5 runs, output-size cap absent, TEST false; V2 PS scripts parse.
- MATLAB R2025b `checkcode` on the changed runner: completed with advisory IDs (STCI, NASGU, AGROW, ALIGN, NOCOMMA, ISCL, MSNU); no parse/runtime blocker reported.
- Independent source review confirmed the `lock.wrapper.sha256` correction, hash verification order, and V2/A02 path isolation. It also confirmed A01 had zero runner/Plant/transitions and no raw to reuse.
- Most recent read-only process scan found no MATLAB/Octave/WSL process and no running WSL distribution. C: had approximately 186 GiB free.

## Run boundary

The new release must use a fresh A02 directory and separately record that A01 made zero candidate calls. On any engineering or safety failure, stop and preserve the attempt; do not overwrite it. This approval does not unlock TEST or automatically expand this 58-call release.
