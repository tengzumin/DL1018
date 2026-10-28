# Root taskbook addendum 06: correct the isolated parity path before VAL scoring

This addendum follows ADDENDUM05 and `ROOT_VAL48_REPAIR01_REVIEW_v1.md`. The first REPAIR01 executor invocation passed metadata audit and scorer preflight, then stopped at the frozen scorer's guard requiring its MATLAB parity manifest and every parity artifact to live under the scorer output directory. The scorer failed before writing its VAL score-start marker. The execution log and failure report are retained; 0 scenes and 0 events were scored and no numerical VAL array was read.

## Narrow continuation

Authorize preparation of one new, isolated directory: `C5_VAL48_OFFLINE_DIAGNOSTIC_REPAIR02`. Preserve REPAIR01 and all prior outputs. Copy the already-reviewed MATLAB parity bundle into REPAIR02 byte-for-byte and verify each SHA-256. Derive a new score lock by changing only parity manifest/artifact paths to those copies; preserve the candidate, evaluation rules, feature/label builder, identity inputs, and every other score rule. Bind the derived lock, copied parity bundle, REPAIR01 metadata adapter and audit, and the original source locks in a new execution lock.

The REPAIR02 executor must first repeat the metadata-only 48-scene audit and frozen scorer preflight using the derived lock. Root reviews the final script and lock before authorizing one numerical score. Then the executor may invoke the frozen scorer exactly once, with output directed only to REPAIR02. Refuse overwrite; preserve every partial artifact if that invocation fails. No second numerical attempt is authorized by this addendum.

No fitting or tuning, TEST access, B/C5 rerun, Plant call, or closed-loop run is authorized. This remains one reused C5_VAL48 generalization diagnostic; it cannot establish closed-loop attitude benefit.
