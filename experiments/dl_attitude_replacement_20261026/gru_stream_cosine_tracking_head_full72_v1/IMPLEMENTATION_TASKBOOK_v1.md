# Cosine GRU tracking-head full DEV72 screen — implementation taskbook

Status: root approved the exact frozen candidate for 66 new DEV/VAL closed-loop calls. `RELEASE.json` is `RELEASED`; no candidate call or marker has started, no training was run, and TEST remains sealed.

## Scope and inheritance

This study screens the already frozen `GRU32_STREAM72_COSINE_TRACKING_HEAD_S2026102001` candidate on the original 72-scene DEV24+VAL48 cohort. The direct parent is `gru_stream_cosine_tracking_head_dev_v1`. Its 59-file `candidate_runner_work` tree is copied byte-for-byte; source diff records 0 changed and 0 added `.m` files. The cosine GRU weights, online tracking-DeltaW rule, fixed nominal J0/Jdot0, event clock, safety limits, and configuration snapshot remain the parent values. The command filter remains `command_filter.acceleration_limit=[Inf Inf 6]`, `wn=[18,18,12]`, and `damping=[1,1,1]`.

The 72-scene payload cohort comes from the already `PASS_NO_PLANT` payload manifest. Six candidate raw/status/audit triples from the direct parent are reused by reference only; none is copied or re-run. The remaining 66 scenes are the only possible new candidate attempts: 24 DEV and 42 VAL. The first six are all VAL. The driver rejects scenes already marked `candidate_reuse=true`; it cannot overwrite or repeat those runs. Existing B and C5 sources are read-only path/SHA references.

The C5 DEV72 input lock has 12 reused C5 raws and 60 new C5 raws. The 60 new C5 records currently say `RUN_COMPLETE_RAW_PENDING_PARENT_AUDIT`; they are included only as locked comparison sources with this audit status preserved. This package does not promote those records to parent-audited status. Root approved candidate flights; any final comparative claim against C5 remains provisional until those 60 baseline raws receive their parent audit.

## Candidate and performance boundary

The six-scene parent result is a pilot, not a full-cohort result. In its HF subset, the inner tracking error improved by about 12.8% versus C5, while HF task SO(3) RMSE still did not beat B or C5. The 72-scene run evaluates this same frozen candidate; it does not claim that the HF issue is solved, and it authorizes no controller change or follow-on tuning.

The Plant remains morphologically active (`gate_geometry_arm=ACTIVE`). `controller_morphology_mode=fixed` describes fixed nominal controller parameters only. No Jhat/Jdot, reconstructed variable inertia, Plant-truth force/torque, or TEST data is a deployment input.

## Evaluation plan

The 66 unreused scene IDs are authorized in the frozen order recorded in `RELEASE.json`, with HF W09–W14 scenes first. `audits/run_full72_authorized_batch.m` verifies that order and the root decision hash, then executes one scene at a time through the bound driver and independent raw auditor. Preserve every marker, raw, status, and failure; the progress ledger is `audits/FULL72_PROGRESS_LEDGER_vNN.json` (next unused version). Ledger v1 preserves the initial no-Plant dispatch failure: the MATLAB wrapper could not resolve the full72 driver before creating any attempt directory. It records 66 `UndefinedFunction` pre-dispatch failures, 0 markers, and 0 Plant calls; the runner now binds and asserts both function paths before iterating. The batch runner skips existing attempts and never retries a failed or partial run. The six reused parent raws are identity references, not reruns.

After all 72 candidate rows have valid raw/audit evidence, score paired B/C5/candidate metrics using the top-level `scene.reference` and the established SciPy `Rotation.from_euler('xyz', ...)` SO(3) geodesic helper. Report equal-scene overall, DEV24, VAL48, HF (W09–W14), W15, and W00–W08 summaries; per-scene wins/losses; position Q; task and inner wrapped Euler axis RMSE (as separate diagnostics); task SO(3) RMSE as the main attitude metric; 0–5 s and 15–20 s windows; safety stops, motor/generalized clipping, projection counts, and resource accounting. Include micro-difference sensitivity at fixed absolute delta tolerances without changing the primary metric or declaring ties as wins.

The future HF follow-up, if needed after full72, is an offline command-path decomposition of task reference → requested command → filtered reference → state over all HF scenes and axes. The existing six-run diagnostic suggests the upstream task-to-command/filter path deserves inspection; six scenes alone do not justify a controller change.

## Execution boundary

Root approval is recorded in `audits/ROOT_RELEASE_DECISION_v1.json`; the release authorizes exactly 66 unreused scenes, with HF W09–W14 scenes first. No attempt has started. The R2025b no-Plant precheck and all release/source bindings passed before authorization. The PowerShell input preflight verifies all locked file SHA values, scene IDs, split/order, external identity links, and source status. Root then ran the R2025b no-Plant scene preflight: `FULL72_SCENE_ARRAY_PRECHECK_v1.json` PASS for 72/72 payload/B/C5 arrays and all six reused candidate raw arrays, including actual cfg, J0/Jdot0, candidate model SHA, DSSM position identity, and isolated `which` paths (report SHA `9df937eae0647f3ef3c3a669e0a0c11a5f202c2e2a11999894f543b323c5a115`). No TEST, no training, no new candidate, no baseline reruns, no threshold tuning, and no claim of final success are part of this package.



## Preflight evidence and raw-audit binding

Root completed the R2025b no-Plant preflight: `audits/FULL72_SCENE_ARRAY_PRECHECK_v1.json` has status `PASS_NO_PLANT_ALL72_SCENE_ARRAY_EQUALITY` (SHA-256 `9df937eae0647f3ef3c3a669e0a0c11a5f202c2e2a11999894f543b323c5a115`). It confirms all 72 payload/B/C5 `time`, `initial_state`, `reference`, `arms`, and wind arrays match; the six reused candidate raws match those fields; actual prepared cfg, fixed J0/Jdot0, candidate model, DSSM position identity, and isolated `which` paths pass. Plant=0, training=0, TEST=false.

The new raw auditor accepts the complete 72-row DEV/VAL manifest. For the six reused rows it verifies the parent raw/status/audit path and SHA and emits a reuse-reference record without re-auditing the raw under this study's release. For a new row it requires a current RELEASED authorization, binds the current release/input precheck, and then runs the parent's full GRU/DeltaW trace replay, torque-application, sample/hold, safety, and command-closure checks. No flight is authorized by this auditor.

MATLAB R2025b `checkcode` completed on `audit_gru_stream_tracking_head_raw.m` with exit code 0 and no diagnostics. Exact command is recorded in `RELEASE.json`; the command only runs static parsing/checking.



Sequential batch runner: C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\dl_attitude_replacement_20261026\gru_stream_cosine_tracking_head_full72_v1\audits\run_full72_authorized_batch.m (SHA-256 a6e933ff4d18a076b14db7dbd552d1b305576a6026c6495e3d4e1b69ed68f1d4). R2025b checkcode passed with no diagnostics; log: C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\dl_attitude_replacement_20261026\gru_stream_cosine_tracking_head_full72_v1\audits\BATCH_RUNNER_CHECKCODE_R2025b_ATTEMPT05.log (SHA-256 6a8c14b39dcdb740b5b9950478913d78b7ce09e8f75259684804653d5e5c680d).




