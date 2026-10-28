# Root script review v2: task-attitude blend shadow

Date: 2026-10-27 (Asia/Shanghai)

## Decision

**Approved for one execution under the corrected taskbook.** Script SHA-256: `ed523cfed9bfd088ccb75faf43f3490a477802332090380de3ef63dc0f76da9f`.

This v2 approval supersedes the earlier script review, whose script hash was tied to the initial source-hash typo. The original failed attempt remains recorded and was aborted before opening raw files.

## Static review

- The script uses HDF5 selective reads and only the seven taskbook-whitelisted datasets; it contains no read of `log/state`, arms, motors, wind, Plant parameters, disturbance labels, B raws, or TEST.
- It verifies the identity CSV, prior yaw diagnostic, input recheck, candidate runner, shared filter, force adapter, locked config, and prior path table hashes before opening raws. It then checks that exactly the same 28 W09-W14 scenes are present for Candidate/C5 and verifies each raw is in-project and hash-matched.
- It checks the 0-20 s / 1 ms grid and transition alignment. It replays the original second-order filter from the first logged filter Euler/rate state and aborts unless all logged values reproduce within 1e-8.
- The only intervention is beta=0.25 shortest-geodesic SO(3) target blending. It reports all pre-registered per-scene/macro metrics and tilt-cap counts/fractions, applies the Candidate threshold of 58.949 mrad, and enforces the 100 MiB output cap.
- Outputs are isolated in the taskbook directory. The script does not invoke MATLAB/Plant, training, or any production source/model/config mutation.

Passing permits only preparation of a separate closed-loop taskbook; it is not evidence of closed-loop improvement.
