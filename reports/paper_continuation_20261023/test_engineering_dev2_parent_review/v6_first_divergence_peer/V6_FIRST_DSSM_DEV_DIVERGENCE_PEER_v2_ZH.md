# v6 DSSM 首分叉复核 v2：实际运行源码勘误

本文件补充并更正 v1 的**源码身份/行号**，不覆盖 v1，也不改变其 raw 数值复算。复核后确认：v1 的数值对照仍有效，但 v1 把核心执行锚点指向了 `experiments/position_delayed_prediction_c3_dev72_20261023/run_dl1018_closed_loop.m`；该文件不是本次 DSSM 工程复现所绑定的核心源码，不能用作“实际执行源码”证据。

v3 冻结的 DSSM `source_refs` 实际锁定 `REFERENCE_FIX_FULL72_20261021_022342_313/corrected_reference_training_v1/corrected_pair_eval_v1/sources/local_runtime/run_dl1018_closed_loop.m`，SHA `01d83dec95aea5d30feef3afd0628a2ce0911f70465f0773a4f568a01b08450b`，当前文件 SHA 实复核一致。相应模型前向 helper `position_stage1_model_forward_v2.m` SHA `dc803aa102c49d67dd687ae941f8a60bb0c465f74fd01e5ae93ad1ea1a293676`，搜索头 `position_only_search_head_step.m` SHA `3bd0fe9686c3b75793575e517d4cc5f08de58ab6a26a2bc7516aa690422bb7dc`，均与 DSSM source manifest 锁定一致。

应采用以下真实源码锚点：

| 执行环节 | 锁定文件及行号 |
|---|---|
| 初始 head weight 读取及记录 | `local_runtime/run_dl1018_closed_loop.m:659–660`；`searchW0` 读取 `:668,673` |
| X14、事件历史及首次前向推理 | `local_runtime/run_dl1018_closed_loop.m:1928–1947` |
| 输出/更新、施加 held force | `local_runtime/run_dl1018_closed_loop.m:2009,2015–2016,2029` |
| PCF 调用及实际命令输入日志 | `local_runtime/run_dl1018_closed_loop.m:2153–2156` |
| DSSM recurrence、归一化特征 | `local_runtime/position_stage1_model_forward_v2.m:54–64,136` |
| FEATURE 头输出及更新 | `local_runtime/position_only_search_head_step.m:12–18` |
| v6 从历史 opts 起步但以当前模型覆盖的准备步骤 | `experiments/c5_test48_v6/test48_entry_v4.m:503–517` |

因此，“历史 raw 与本次 raw 的 W0/模型参数身份不同，且在首个 ready 推理时同一 X14 窗得到不同编码输出”的数值结论不变；现在可把其因果链准确映射到被清单锁定的 local-runtime 源码。v1 JSON 的 `source_code_anchors.initial_weight_from_runtime_opts`、`X14_history_and_forward_inference`、`same_event_head_update_and_held_force`、`PCF_filter_input_and_outputs` 请以同目录 `..._v2.json` 中的更正值为准。此版本没有重读 raw、没有运行作业或读取 TEST。

对恢复路径的独立判断：若目标是复现既有历史 D/K DEV，沿用历史 `run_start.opts.stage1_position_runtime.model`、`weight` 与 head `W0`，并为该历史模型身份另行冻结，是技术上最小且与尚未启动的五个 TEST 块相容的做法。B48 已生成但分数未读，不妨碍在未启动块前发布新 release；应把 B 的 v3 身份与剩余方法的新 release 明确并列，保留本次 v6 失败 raw，不以旧 release 名义继续执行。该改动改变当前 DSSM/KAN 的冻结模型身份，故须重做静态/零 Plant 身份检查并完成新 release 绑定，不能只改一份 opts 后直接运行。

这条修复只能解决“方法输入身份是否按历史基线复现”，不会让跨方法结果成为表征控制后的因果比较。若 C5 与恢复后的历史 D/K 表征/W0 不同，跨组成绩只能作为完整方法包比较；要把差异归于控制机制，需同表征、同初始化而仅改变指定控制处理的配对证据。已有同一 C5 表征内的 FREEZE/NO_PRED 消融支持受限的内部对照，但不隔离 C5 对历史 D/K 的跨模型增益；也不单独证明 PCF 的因果贡献。此结论不要求为本身份错误另跑 144 个 DEV。

相关原件保留：v1 JSON SHA `4b6677bea60ec5ef42060c43538cc3600765a51d2f0ee5c682bebb776f78bc91`，v1 报告 SHA `5bfebfe97faf3e725ab5ed173919ce09f53ba5e3514c16168dd10437e642d3dd`。机器可读锚点勘误见 `V6_FIRST_DSSM_DEV_DIVERGENCE_PEER_v2.json`。
