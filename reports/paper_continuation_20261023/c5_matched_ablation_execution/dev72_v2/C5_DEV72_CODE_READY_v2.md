# C5 matched ablation DEV72 v2 — CODE_READY

状态：源码与输入锁已冻结，等待主审源码审核。未运行 MATLAB、Plant、训练、B 或 TEST；不得据此执行任何航次。

v2 位于独立 sibling root `experiments/position_c5_matched_ablations_dev72_v2_20261023`。DEV72 v1 的源、锁、manifest 和失败/审计证据未修改。科学控制源没有变更：两配置的 core SHA 均为 `48350037b66efe00301b138068f187c62cf92583f0f9ba2fabc9b24f248a963c`，wrapper SHA `fcc1f5de659541e692483f8395d93fd2a251256286ebade5e510ed4c7a2e2330`；helper 分别与已审 v4 对应变体逐字相同（FREEZE `aab2a67b17886e5e71460fc972a57a389faef10fed9b30292befc64ab6511eaa`，NO_PRED `390fd63989922e0f252df51c392f18977b9957bec6534e4905634b8c94147248`）。每种配置复用已审12场，执行集合是 C3 锁定 `scene_ids_all_72` 原序过滤 reuse12 后的60场，顺序无排序；两份锁均核得 `72 = 12 + 60`，且 `first_scene_id = scene_ids_remaining_60[0] = DL1018_DEV_T1_C00_W03`。

本版收敛了首次源码审核发现的入口缺口：builder 现在对不同内容严格拒绝覆盖、移除 draft-refresh 环境开关；lock 的 `first_scene_id` 与运行 contract 一致；DEV72 synthetic checker 使用新 Dev72 contract 和单独结果文件 `C5_ABLATION_CROSSLANG_RESULT_DEV72_v2.json`，noPlant launcher 执行 checker→prepare→同一 runner 的 `PREFLIGHT_ONLY`；parent launcher用单个 variant 对应的 screen12 audit SHA 比较，避免 `-and/-or`优先级错误；noPlant launcher 在 MATLAB 前创建 reportDir。检查器、输出路径与 prepare/runner 的 synthetic schema/SHA 引用一致。

## 输入锁和契约 SHA

| variant | input lock | run contract | parent release contract | release template | reuse12 binding | source binding |
|---|---|---|---|---|---|---|
| FREEZE | `c9c8c35e5fe037f325a1b535c4c928462da945cfb1da74ddf024432388ef137e` | `31fd63333e1edfb93b06bf2cdcf11517fb4c42952d97cae67ad0625b6e77f9fa` | `e633b4b1aba9f7185df784748b799e87e9d516a481e010ad8a01026abc5a9e00` | `9f37fa243118261e280faaf46d579bb9111d1f5395bcf05f8600487c527867e7` | `aba2d6c73777612788c2c4dbdd68ca56aa7f200a5dff720a4b8b7c744eb80833` | `9984c757d31a6c80ef9e948a34ba5bc98f374c09f595bef98e0fdae38c8f76d2` |
| NO_PRED | `440e688093c6e96525c7f13820ae2580423d191efb5ec0236c3a6a2b85211a97` | `91669018d3d5f19a29c7162f4ed307f7f7371850ff0ffe647fe86bc49825bbcc` | `3f2b7071d69d41a7ccc56620939ea3e6bb12aefab753eb51c861899044289988` | `7b4596f18daae51b267b2f14355c11e18f89046e57e373cd15bbcd6fbd6b35ad` | `123f56a288469b5fdf403db09d9d63cab2ca3300283a9fbda6a54df833d83494` | `9c7aaec5b7911125bf0a6d2de9e2400b4ce7364912fca83884de6adc11d34ab3` |

Manifest SHA: `7d2d8040ea4de87f589d9e43fbb7d1a3344a9ac3bbe97118d05214b4f279ea44`. Builder SHA: `d15484655904107eefb363dd067db43fd6e41896f210d7a64c508a033129c93c`.

Parent release contract and template both define 44 required fields. A static union of all `release.<field>` checks in MATLAB runner and parent launcher found 44 fields, all present; template keys match the required field set exactly. Each variant source binding has 75 file refs, all present and SHA-matched; active runtime inventory is 32 files (31 `.m`, 1 `.mat`), shared inputs 6. V2 core/wrapper/helper and all source/upstream references were independently SHA checked.

PowerShell Parser returned 0 errors for both noPlant and both parent launchers. Python AST parsing of the builder passed. Static checks verified both variants use the same new synthetic result path across checker, prepare, runner, and launcher; DEV72 result, prep snapshot, runner preflight, noPlant exit, and failure outputs are currently absent. The copied old screen12 cross-language result is explicitly named `UNREFERENCED_SCREEN12_CROSSLANG_RESULT_v1.json`, is not referenced by either lock, and is not a new execution record.

## Awaiting review

NoPlant commands, to run FREEZE first and NO_PRED only after its natural OS return and separate review:

```powershell
& 'C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/position_c5_matched_ablations_dev72_v2_20261023/C5_FREEZE_TRAINED_W0/RUN_C5_ABLATION_DEV72_NOPLANT_EXACT_v2.ps1'
& 'C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/position_c5_matched_ablations_dev72_v2_20261023/C5_NO_DELAYED_PREDICTION/RUN_C5_ABLATION_DEV72_NOPLANT_EXACT_v2.ps1'
```

These are prepared commands only; no MATLAB process was started. A separate exact parent release is required before any Plant run.