# v9 路径与历史记录身份适配：静态补充任务书

本任务书替代 v1 的待执行 CODEONLY 范围；v1 及其 release、v9 初版摘要保留。沿用 v1 全部限制和失败证据。本次是同一个尚未启动 MATLAB 的 v9 静态交付，不新增一次工程重试。

允许原路径修复：verify_stage_release 从传入 contractPath 读取 contract，经 repo_path(root,contract.taskbook_path) 定位任务书；原 schema、五项 SHA、权限、no_retry 检查不变。版本、任务书/release/SHA 绑定与累计预算按 v9，保留 v8 失败。

另允许一个经实际 MAT 元数据确认的身份适配修复，范围仅 read_method_contract：

- CORRECTED_DSSM14_G12_R32 必须校验 historical meta.method_id 等于 CORRECTED_TRAIN_DSSM14_G12_R32；返回 candidate、collector_tag 仍为原部署标签 DSSM14_G12_R32。
- CORRECTED_KAN14_G12_R32 必须校验 historical meta.method_id 等于 CORRECTED_TRAIN_KAN14_G12_R32；返回 candidate、collector_tag 仍为原部署标签 NEW_KAN14_G12_R32。
- 未识别 corrected 方法显式拒绝。保留实际 run_start 路径/SHA 校验，不允许改为接受多个历史身份，不跳过断言，不改返回的部署身份。

理由：真实 corrected r002/r001 的 meta.method_id 是 CORRECTED_TRAIN_*，而 collector 是另外一套冻结标签。旧 fallback 混淆两者，在 DEV2 Plant 前必然拒绝。此改动只适配已锁定记录的身份，不修改控制器、网络、模型、normalizer、W0、物理或统计。六个保护函数的规范换行文本 exact；六方法对象、engineering spec、冻结 TEST 三文件及全部数值不变。

仅写 experiments/c5_test48_v9 四静态文件及 reports/paper_continuation_20261023/test_entry_v9 新摘要。保留 V9_PATH_AUDIT_SUMMARY.md，新增 V9_FINAL_STATIC_AUDIT_v2.md。绑定本任务书与 v2 CODEONLY release。对所有调用路径和元数据消费者检查已完成后交付实际四 SHA、PS AST、JSON 和完整 diff；不得运行 MATLAB。

根审核后才另发 PREPARE release；随后 DEV2、TEST 仍分别审核。DEV2 最多两场固定 VAL、TEST 只五方法 240 个未启动组合，B48 复用。不得读取 TEST 性能。原 v1 最后一次路径类修复限制仍有效。只用 PowerShell 7，不抢锁、不终止实验、不删除旧数据。deadline 2026-10-24T17:01:00Z、产物总额 80e9、预留后空闲至少 30e9。
