# Root prelaunch review — filter wn12 engineering gate

Decision: approve exactly one engineering-gate Plant call for `DL1018_DEV_T1_C10_W09`.

Review basis:
- Independent `validate_filter_wn12_no_plant_v1.py` completed with `PASS_NO_PLANT_VALIDATION`.
- The 12 DEV/VAL inputs, paired B/C5 source raw/status hashes, and all 59 inherited MATLAB source files pass locked SHA checks.
- The candidate source tree is byte-identical to the parent for all 59 files. The sole runtime delta is the prepared command-filter natural frequency `[18,18,12]` to `[12,12,12] rad/s`; damping, acceleration limits, model, online head, C5 position loop, J0, source scene, and Plant remain bound to the parent.
- The MATLAB wrapper verifies the release, all locked inputs, exact scene manifest, model hash, runtime function paths, position identity, fixed J0, and no inertia reconstruction before creating the attempt marker. The PS7 launcher allows exactly one scene and stops on any MATLAB error.
- No MATLAB process was running at review. This approval does not authorize the remaining 11 scenes, training, TEST access, or any change to historical records.

Evidence limitations:
- The fixed-target offline replay is a screening hypothesis only; it does not establish closed-loop benefit.
- The frozen GRU was trained on all 72 DEV/VAL scenes; the 12-scene screen is in-sample development evidence, not independent validation.
- Engineering-gate pass criteria are stable 20,000-transition completion, identity/integrity pass, and zero safety stop, motor saturation, generalized clipping, or tilt limiting. Performance will be reviewed after the raw is scored.

DRAFT release SHA-256 before root authorization: `bdab97c9876d96156353a9d6ee9682a0f871298f273bd497de7a92b3fb9c4f02`.

Superseded after the recorded pre-Plant launch failure. Its one-call approval was withdrawn; see `ROOT_ATTEMPT_FAILURE_v1.md` and the fresh `ROOT_REPAIR_REVIEW_v2.md` for the current decision and source-diff status.
