# C4 noPlant cross-language execution

All MATLAB invocations were single-layer PowerShell 7 scripts calling MATLAB directly. No Plant, episode runner, training, model fitting, or TEST access occurred.

The Python prechecks are recorded in [C4_CROSSLANG_PYTHON_PRECHECK_v1.md](C4_CROSSLANG_PYTHON_PRECHECK_v1.md); all three commands returned exit code `0`. Fixture SHA-256: `1306fa797179380d86df4a93deb0594f2f2e99a920d8eeb68aef0957044181a0`.

The first batch used `RUN_C4_CROSSLANG_NOPLANT_EXACT_v1.ps1` (SHA-256 `b7f12c4a7c7b9c679225a3f1cc588196578693d5f8ae849c9d44a356a9e2a157`) and returned MATLAB OS exit `1`. It preserved `C4_CROSSLANG_SYNTHETIC_RESULT_v1.json` with `MATLAB:structRefFromNonStruct`: MATLAB decoded the heterogeneous event objects as cells. This failed result remains unchanged.

The reviewed v2 checker unwraps either cell or struct arrays for both cases and events. Its source SHA-256 is `b37e6e22474a43a7ff1ad3db87cde074b2b488f74f9b1fa4ca343b32b64f2f91`; the v2 PowerShell command SHA-256 is `600a7cb945d4b3535718bb7136d4745a40ea6b71b3db4c26193749e7815e8a94`. The script passed PowerShell Parser validation. That batch returned MATLAB OS exit `1` after the cross-language checker passed with maximum absolute error `2.2204460492503131e-16` at tolerance `2e-12`. The result explicitly covers both `m=1` direct-`a_f` and `m=0` direct-`a_req` paths, n=320 without previous data, `[320,330)` integration, current-row sentinel exclusion, helper outputs before update, and Python/MATLAB helper parity.

The subsequent noPlant prepare stopped at `source_path(lock.shared_input_files,'model_mat')` with `Expected one locked source model_mat.` The lock entry's role is `model_mat`, but its path basename is `matlab_model_and_parity.mat`; the prepare helper searches basenames rather than roles. The prepare entry itself is SHA-bound by the frozen lock (`1e940ef58967aca7e371f4d53998a6890c5ae0535ca3d2df19fdc5c3eb27be14`). The preparation result and snapshot were not created, and neither the lock nor its bound prepare source was changed.

After the v2 role lookup repair, the prepare-only batch used `RUN_C4_PREPARE_NOPLANT_EXACT_v2.ps1` (SHA-256 `3c5f1ca4b79c45004c6c86acd60ac9029eed8dfc49246f7ba9c541357114f770`) with lock SHA-256 `7f9d482313701940a272b1b4030af87bc2c0a5d926d9929e57bb84ea0d0aae96`. It returned MATLAB OS exit `1` at `sceneIdentity(k)=c3Pack.sceneIdentity(ix)`: the C3 struct includes `payload_review_sha256`, which the C4 template omitted. The noPlant result and snapshot were not created. The third batch's true OS exit record is [C4_PREPARE_MATLAB_OS_EXIT_v2.json](C4_PREPARE_MATLAB_OS_EXIT_v2.json). No fourth batch was launched.

The fixed helper, C4 core, and original v1 input lock retain SHA-256 `48feebf934b8eb90b4424f2286aa857c48213d229714f30af99aacf53329549d`, `cec0d688226123a9b9f14e2a215f283e1ef859caa8371ac2b764d3b1c2bcc878`, and `318bdaee3533c908da45140bcc2fef4e2ddb01e0fe63158c24057bde6bfdbd39`, respectively. No Plant was started.
