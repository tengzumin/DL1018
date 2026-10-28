# C2 delayed-prediction runtime draft

Status: `DRAFT_NOT_AUTHORIZED_FOR_PLANT`. This isolated copy is not wired into a launcher and was not executed in MATLAB or Plant.

- Frozen source: `experiments/position_beta_clock_c2_20261023/runtime/run_dl1018_closed_loop.m`, SHA-256 `62943c0247afd94295776916a1d5370d4be2b5f93984ff4e52ce734f7f772992`.
- Runtime candidate: `run_dl1018_closed_loop.m`, SHA-256 `e5f1e30c433ee3f8206b36446cde71776589c161fe2a3ec60fbaf070585eb07f`.
- Pure MATLAB helper copy: `delayed_prediction_step_candidate.m`, SHA-256 `48feebf934b8eb90b4424f2286aa857c48213d229714f30af99aacf53329549d`.
- Unified diff: `runtime_candidate.diff`, SHA-256 `31400a5d753f8f080962b9a26807fd895ba3986f66628653ea5abe9325ecb6a4`; 89 added / 3 removed lines (excluding diff headers).

The new top-level option defaults to false and accepts only a logical scalar or finite real numeric scalar 0/1. In true mode, initialization requires FEATURE/update/full-PCF, X14 with 32-event context/readiness, 1 kHz plant and 100 Hz event schedule, the frozen scheduler phase and zero-based time grid that make the first ready event `n=320`, gamma 12, beta rise 1.8 s, dmax 3 per axis, finite 14-element model normalizer, and model output W0 equality. The helper must resolve from this isolated runtime directory before the loop.

At each valid FEATURE event, the draft passes zero-based `n=k-1` and `t(k)`. The first ready event has no previous sample; later events use the preceding valid event `j=n-10`, its saved feature and velocity, and the AF integral accumulated only through steps before the current step. The target is `(v[k]-v[j] - (AFIntegral[k]-AFIntegral[j]))/0.01`. Raw/applied outputs are computed by the helper before `W` changes; its single projection supplies the next weight. The legacy bias audit fields receive explicit zero values. AF integration advances only after this step's PCF `a_f` is computed.

The default-false control branch retains the original call. Static review was performed by reading the source diff and checking source hashes; no MATLAB parser/checkcode, numerical integration test, MAT/raw input, training, GPU, optimizer, or Plant was run. MATLAB syntax/parity and runtime behavior remain unverified.
