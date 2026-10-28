# GRU_STREAM cosine deployment preparation

This isolated study prepares the deployment wrapper and no-Plant checks for the separately trained `GRU32_STREAM72_COSINE_S2026102001` model. The training change is only the frozen cosine learning-rate schedule in `ROOT_GRU_STREAM_COSINE_TASKBOOK_v1.md`; this study does not launch training.

## Scope

- The 58-file `candidate_runner_work` tree is byte-identical to `gru_stream_dev_v1/candidate_runner_work`: 0 changed, 0 added, 0 removed. `SOURCE_DIFF_v1.json` compares directly against that parent and includes every SHA-256 pair.
- The GRU method remains `GRU_STREAM`. Hidden reset/carry, legal 13-feature input, DMAX then event beta then fixed J0 mapping, and all C5 position/BS/configuration behavior are inherited unchanged. `controller_morphology_mode=fixed` fixes nominal controller parameters only; the paired scene still has active physical arm motion (`gate_geometry_arm=ACTIVE`).
- The only candidate identity is `GRU32_STREAM72_COSINE_S2026102001`; release schema stays `DL1018_GRU_STREAM_DEV_RELEASE_V1` because the byte-locked DEV engine accepts that schema, expected model at `gru_stream_cosine_c5_teacher_v1/runs/GRU32_STREAM72_COSINE_S2026102001/gru_stream_c5_teacher_weights_v1.mat`. Do not substitute the constant-LR model or toy weights.
- Full72 teacher-fit and fixed-hidden readout-bias gradient are recomputed using the existing read-only diagnosis script after export. No optimizer updates are part of that diagnostic.
- No run/raw files are copied. The six scene records retain only their existing path/SHA bindings. The small toy parity fixture/reports are inherited from the parent and remain separate from candidate-model parity.

## Checks and gate

Release is prepared for root review with `authorized_Plant_calls=0`, `Plant_calls=0`, no authorized scene, `TEST_read=false`. Before any root flight approval, the cosine export must pass full 1999-event Python-double/MATLAB-double and float32 parity, real prepared-CFG and `which` checks, source lock/direct-parent verification, and both actual-DEV/outer-driver zero-budget rejection. The full72 diagnostic must be recorded beside the existing constant-LR report. This preparation authorizes no Plant call.

After root approval, the first candidate scene is only `DL1018_VAL_T1_C08_W15`; the remaining five require separate root approval. No DEV72, TEST, parameter change, or rerun of completed attempts is authorized here.
