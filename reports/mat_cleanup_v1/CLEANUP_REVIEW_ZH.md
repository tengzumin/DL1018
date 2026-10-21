# DL1018 MAT 清理只读盘点（阶段 1）

- 盘点时间：2026-10-21T10:27:23Z
- 唯一清理根：C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018
- 任务书：C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\reports\mat_cleanup_v1\MAT_CLEANUP_TASKBOOK_ZH.md，SHA-256 87a7b5bc1ec0d03e32a0a44867e6ecae022bbb4c0fc25ef0bad05b0d9a82fbf0
- 本文件及两份 CSV 是只读盘点交付；未删除、移动或改写任何 MAT，也未触碰代码、模型、真实 state/raw 或实验报告。
- 当前 experiments 目录普通 .mat 文件：1,243 个，总计 22,950,837,878 bytes（21.374633 GiB）；其中 raw_run.mat 466 个 / 22,438,965,012 bytes，run_start.mat 471 个 / 446,182,490 bytes。
- 删除候选：0 个（0 bytes）。原因是现存实验状态均已完成/结题，或其 raw/run_start 是报告所需独有证据；没有找到同时满足“明确废弃或被替代、已完成、无当前依赖”的具体普通 MAT。历史索引提及本身不作为依赖，但也没有足够证据把这些唯一实验原始证据划为可删项。

## 按实验统计

| 实验 | 状态/证据概况 | MAT 数 | raw_run 数 | run_start 数 | 全部 MAT GiB |
|---|---|---:|---:|---:|---:|
| gru14_dssm14_student_refine_v1 | state COMPLETE / phase COMPLETE; final refinement evidence | 929 | 336 | 337 | 15.414387 |
| kan14_task_specialist_compare_v1 | state COMPLETE / phase DEV24_COMPLETE; 48/48 comparison runs | 100 | 48 | 48 | 2.170070 |
| old_kan_fig8_transfer_compare_v1 | state COMPLETE / phase FINAL_REPORT; 34/34 complete | 68 | 34 | 34 | 1.622991 |
| position_causal_repair_v1 | state COMPLETE_D5_NO_PASS / phase FINAL_REPORT_COMPLETE; failed gate is recorded evidence | 5 | 0 | 3 | 0.000144 |
| position_only_closed_loop_search_v1 | state PASS_POSITION_DEV_BEATS_B / phase POSITION_SEARCH_COMPLETE; selected candidate package retained | 1 | 0 | 0 | 0.000042 |
| teacher_reuse_model_screen_v1 | state COMPLETE / phase LOCKED_DEV24_COMPLETE; explicit whole-directory protection | 135 | 48 | 49 | 2.166712 |
| training_data_structure_compare_v2 | state STOP_POSITION_NOT_QUALIFIED / phase FINAL_REPORTS_COMPLETE; source/protocol/cache evidence retained | 5 | 0 | 0 | 0.000288 |
| **合计** |  | **1243** | **466** | **471** | **21.374633** |

## 当前依赖与保护依据

- 保护清单 PROTECTED_MAT.csv 共 4028 条唯一、存在的普通 MAT 路径；其中有 2820 条由当前 FULL72/G3/144 格元数据直接引用（2784 条 data MAT、35 条 experiments MAT、1 条 config MAT），并把 experiments 下其他 MAT 也逐文件列为保留项。两部分有 35 条重叠。CSV 的 source 是实际读取的外部索引/本地协议或状态文件。
- 本轮读取并散列了 27 份当前索引/协议元数据（未散列海量 raw）；范围包括 FULL72 manifests/RAW_INDEX/CANARY_INDEX、scene_preflight 当前输入/稳定性索引、G3_SOURCE_FILES/G3_D4_CACHE_INDEX_1632/D4_SEQUENCE_CACHE、PAIR_TRAINING_INPUT_INDEX/训练协议/normalizer、144 模板与 288 baseline reuse。source path/size/mtime/SHA 可在本目录随审计记录复核。
- 144 格模板的 DL1018 实验来源落在 experiments/teacher_reuse_model_screen_v1；该目录按任务书整体保留。288 baseline reuse、FULL72 manifests 与 scene_preflight 引用的 data/raw 下 raw_run.mat、run_start.mat 以及配置 MAT 也均按任务书保留。
- G3 role/cache 索引引用的 DL1018 来源 MAT 已规范化为绝对路径写入保护清单；data/datasets/models/configs/matlab 与教师数据/缓存默认保留，即使不在候选范围也未作清理判断。
- FULL72 corrected-pair eval 的训练/导出/normalizer 协议只读解析；模型、normalizer、快照、fixture、sequence cache 与 MATLAB 配置 MAT 全部保留。旧 run_start 模板和复用 baseline 原始 MAT 均不列候选。

## 可疑/待父审判断项

- position_causal_repair_v1 仅 5 个 MAT（3 个 raw/run_start），状态为 COMPLETE_D5_NO_PASS；它记录 failed gate 及后续不得运行 D6 的结论，是关键否定证据，保留。
- old_kan_fig8_transfer_compare_v1 有 68 个 raw/run_start MAT，状态 COMPLETE 且有 final report；当前未找到明确可替代其比较证据的声明，保留。
- gru14_dssm14_student_refine_v1 有 673 个 raw/run_start MAT、15.414387 GiB；状态/恢复报告标记 COMPLETE，且这些是完整轨迹证据，保留。体积不作为删除依据。
- kan14_task_specialist_compare_v1 有 96 个 raw/run_start MAT，状态 COMPLETE、48/48；结果 MAT 是其唯一轨迹证据，保留。
- position_only_closed_loop_search_v1/README.md 描述过 72 个 runs/**/raw_run.mat，但当前安全扫描在该实验目录只发现 1 个 MAT（position_only_candidate_package.mat），未发现任何 raw_run.mat/run_start.mat。这属于索引/文件现状差异，未据文档新增候选；候选包保留。
- teacher_reuse_model_screen_v1 全目录按任务书保留；当前 144 模板、baseline/canary 元数据直接引用其中的 POSTHOC DSSM14 raw/run_start。

## reparse、范围与进程检查

- DL1018 路径祖先 reparse/junction：0；experiments 扫描跳过的 reparse/symlink 项：0。扫描仅读取 experiments，没有跨到兄弟 FULL72/DL1009/FIG8 目录。
- WMI 进程检查不包含发起查询的 PowerShell；实际命令如下：
  - MATLAB.exe PID 32100 — executable: C:\Program Files\MATLAB\R2025b\bin\matlab.exe
  -   -batch addpath('C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\REFERENCE_FIX_FULL72_20261021_022342_313\corrected_reference_training_v1\corrected_pair_eval_v1\scripts'); run_corrected_pair_eval_stage('C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018','C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\REFERENCE_FIX_FULL72_20261021_022342_313\corrected_reference_training_v1\corrected_pair_eval_v1','RUN','MAIN_142')
  - MATLAB.exe PID 40812 — executable: C:\Program Files\MATLAB\R2025b\bin\win64\MATLAB.exe
  -   same -batch RUN MAIN_142 command as PID 32100
  - No MATLAB/Python process command line targeting DL1018 other than the two MAIN_142 MATLAB processes was observed. The 10 Python processes observed were MCP CAD workers running mcp_cad.exe, not DL1018 experiment processes.

## 索引输入快照（SHA-256）

| 输入文件（FULL72 相对路径） | bytes | mtime_ns | SHA-256 |
|---|---:|---:|---|
| corrected_reference_training_v1/corrected_pair_eval_v1/manifests/CORRECTED_PAIR_EVAL_144_TEMPLATE.csv | 177027 | 1792577933952307000 | ef978326d7d8e585514c0261e2ddd280876c9d3002114188bc14a08691759b7d |
| corrected_reference_training_v1/corrected_pair_eval_v1/manifests/PAIR_EVAL_BASELINE_REUSE_288.csv | 274823 | 1792577933962324300 | 369e1c8da6d58f2460ee0f39c1a7ef284269190bd808dc4c7d85c6044f5f41df |
| corrected_reference_training_v1/corrected_pair_eval_v1/reports/PAIR_EVAL_MODEL_ACCEPTANCE.json | 5319 | 1792569383542464800 | d2443465fac3d3f407798458b1cb8eb5432a245df80dd7068053bf3888ebbb44 |
| corrected_reference_training_v1/corrected_pair_eval_v1/reports/PAIR_EVAL_PREPARATION_INDEX.json | 11660 | 1792577936183370200 | bfa77acdb8fbdac9d161efa0c35d2b0d225916cf759292114e992c5c6c2f0db6 |
| corrected_reference_training_v1/corrected_pair_training/manifests/PAIR_TRAINING_INPUT_INDEX.csv | 768926 | 1792564318698972400 | 257089f1dc455b7bc97bf1c772be31d1d8ae83079e7ec41f591d96e31fed39ca |
| corrected_reference_training_v1/corrected_pair_training/models/official/DSSM14/seed2026102001/fit_report.json | 6996 | 1792566230832173300 | ab69002b465638ded0599964371eb17e3c1cecd0c587ca911c2054650c3cac72 |
| corrected_reference_training_v1/corrected_pair_training/models/official/KAN14/seed2026102001/fit_report.json | 6962 | 1792565302116922300 | 33fa2811b4cd5aa6c0d028d634269055f93d3052bd3939c2beac9835020e073e |
| corrected_reference_training_v1/corrected_pair_training/protocol.json | 3011 | 1792564327913374200 | 28e63d588f1e693140a04f3bbcedc9f608cda74306e310ce5bae9e21961feba6 |
| corrected_reference_training_v1/corrected_pair_training/reports/PAIR_PREPARATION_INDEX.json | 22507 | 1792545883316121200 | 293869fd9c87ffe94c4f92772e8dfd50450514ffc0a86a83d9cfef1591a8c40b |
| corrected_reference_training_v1/corrected_pair_training/reports/TRAIN_ONLY_NORMALIZER.json | 1834 | 1792564327894812700 | b1d8a4e0386a6f91d11d51daeec0a01605dcf3fa58fd19f594dadd57e4e4d54e |
| corrected_reference_training_v1/g3_collection/cache_build/manifests/D4_SEQUENCE_CACHE.csv | 267562 | 1792561522882918500 | 9de5c2c4042467031f3092cc456e015e8f30f0b9438c6ba8bb09751bd2f60b7b |
| corrected_reference_training_v1/g3_collection/manifests/G3_SOURCE_FILES.csv | 1491714 | 1792538209318284900 | f7eefad816014197119e72b653cd120687d189420d7c470f1d4ef197edde55e7 |
| corrected_reference_training_v1/g3_collection/reports/G3_D4_CACHE_INDEX_1632.csv | 1643067 | 1792561625107931900 | 3c8291c12628acfb9d950fb67cb84b56fe09cdaeaeac38706e8903291873e84e |
| manifests/CANARIES_4.csv | 1957 | 1792521161429515400 | 9874bf3d466159f6b2788e19d4ee9abcdd4bdbb8b97f6f7052b52401f06862ce |
| manifests/MATRIX_288.csv | 158736 | 1792521161428237600 | 45ef9cf2e64a62657112576bb3bb980efde14966a46d8a145f2867f2926c30db |
| manifests/MATRIX_FINAL_288.csv | 158440 | 1792522097435555400 | 5a9b8e06e00d20d3205dc6436b6cfe169f73e5dca2b5fec6616a68b57069aba1 |
| manifests/SCENES_72.csv | 13452 | 1792521161425065700 | ad63fc94815a984a0630ed4c63412cd99d3cabe6844b5862c564798ac29dfd26 |
| reports/BUILD_MANIFEST.json | 2529 | 1792521161435615600 | a75506f1b82af2a5295d5a76b2c112a96097c6cbc4dcea877a12844df908a24c |
| reports/CANARY_INDEX.csv | 2054 | 1792525420431158900 | 14f6c4149f2b0522d84d23f60ea7816cf94b1e433853691015be29ec8713b23e |
| reports/RAW_INDEX.csv | 144560 | 1792532163797988700 | 4213d3b9993fe64940e558dbb7da198b18d9fa9cfa44064fcbbea80ea04806f5 |
| reports/SOURCE_CONTRACT_PREFLIGHT.json | 1000 | 1792522097435555400 | a778cae03862fb3b7954220c8c6f503ec1f3329e98345531d88c1817dc169686 |
| scene_preflight/reports/SCENE_INPUT_PREFLIGHT.json | 251232 | 1792524778365793800 | 506c8c2496bdac4a1d2722aa4d34387265ee5bc1ddf4dc30918256ed23e0b9e7 |
| scene_preflight/reports/SCENE_INPUT_PREFLIGHT_FILE_STABILITY.csv | 25842 | 1792524778313409500 | 19172af70230d33f8edfe63216cde568bd1da344995f4fb87ce505b90f48213b |
| scene_preflight/reports/SCENE_INPUT_PREFLIGHT_REUSE.csv | 23286 | 1792524778294319900 | b14571e24b6e26f5ca10759d7a42040fc49eec3bba7139bc58da26b8123bc505 |
| scene_preflight/reports/SCENE_INPUT_PREFLIGHT_REUSE.json | 56238 | 1792524778329812300 | 87e4b2798aed47f33e0e584df2b3c2872e8935a82d4b4b5c470cf587cd152ed6 |
| scene_preflight/reports/SCENE_INPUT_PREFLIGHT_SCENES.csv | 44414 | 1792524778250522500 | 537642e931c2c70f31831d0c6285b45709280b3dffd383623d83a586fc28d298 |
| scene_preflight/reports/SCENE_INPUT_PREFLIGHT_SCENES.json | 172451 | 1792524778324657500 | 56c323b342d58c7f35924d968da14a72ed493c3d632412cd2f40a7f31c97d6ad |

## 文件交付

- PROTECTED_MAT.csv — 4028 条 protected MAT 路径。
- DELETE_CANDIDATES.csv — 空候选表（仅含字段头），SHA-256 beb7bf963db515dbba0b346205810ebc1da8e5f172867c8d609cc46784cdfc68。
- 缺失的直接引用路径：0。当前写入保护清单的路径均通过普通文件/根目录/reparse 检查。

阶段 1 到此停止。未执行删除；需父审针对候选清单复核并签署后，才可进入阶段 2。
