# 新 B 可追溯基线：源码与历史身份审阅

**结论：源码分支可支持一场新的、可追溯 B 基线；未发现阻止该单场入口的控制器分支问题。** 这只表示采用专用 prepare/runner 并通过任务书门后可运行，不是对尚未交付的 runner/release 放行，也不表示恢复了旧 B 的 runtime 身份。

旧 B 配置快照比此前口径完整：基线 manifest 的 72 条 B 行均有 `source_run_start_path` 与 `source_run_start_sha256`；我按 manifest 相对路径在 `drone_tcn` 根解析并重算，72/72 文件 SHA 匹配。已完成的 `HISTORICAL72_CFG_OPTS_REVIEW.json` 显示这些 sidecar 的 B `cfg` 均有 120 个叶子，72 场 cfg 无差异；B 的 13 项 opts 可从 sidecar审计与锁定构造器确认。raw 本体只有 24/72 带完整 cfg，因此“48 个 raw 无 cfg”不能写成“48 个运行快照缺失”。21 场 manifest 源 sidecar 与旧 raw 同目录 sidecar 字节不同；沿用已有审计，其差异是首步 marker 路径字段。报告应以 manifest 绑定的源 sidecar 为准。

但旧 B 的实际执行源码树仍未闭合：旧 B manifest 没有 `runtime_tree_sha256`；`verify_historical_runtime_identity.py` 明确输出 `PASS_DSSM72_IDENTITY_B_UNCLOSED`。因此旧记录能恢复完整 cfg/opts 和逐场 raw/run_start 身份，不能证明当年加载的是当前 C3 或任何已知 runtime tree。

B 方法及新入口可以明确到字段。`controller_options_dl1018(cfg,'B')` 的 13 项为：formal baseline=true；位置/姿态 RBF 频率各 100 Hz；phase start/full phase start 均 −0.1；位置/姿态 RBF gamma scale 分别取锁定 cfg 的 5/19；位置 RBF output/update=true；姿态 RBF enabled/output/update=true；v1_adaptive=false。B opts 不带 stage1 replacement/search/PCF/prediction；RBF 权重由 runtime 零初始化。C3 wrapper 将实际 runtime method 固定为 `B2-RBF-Full-SPLIT`，外传 method 仅作为 collector 标签。C3 core 中 prediction flag 缺省 false，PCF 依赖 active stage1 runtime；`stage1PositionActive=false` 时新增候选分支不可达。B 的旧位置 RBF 100-Hz scheduled 分支仍按 `beta=min(k*dt/T,1)` 运行，位置 RBF output/update flags 为 true；姿态 RBF 和后续控制/Plant 仍走共同正式基线链。不要从 FEATURE opts 删除 stage1 字段来伪造 B：那会保留位置 RBF disabled 状态。必须重新调用 B 构造器。

最小可复核单场为锁定 C3 输入中的 `DL1018_VAL_T2_C00_W10`，B 源 raw 只作为场景物理输入身份，路径与 SHA 由 C3 input lock 绑定（`05ad0e…e059b7`）；不把那条旧 B raw 当新输出。按冻结任务书加载 C3 prepared cfg 并与 effective config 树核对，以 B 构造器新建 opts，保存完整 cfg/opts 快照、源库存/`which`/SHA 和新 raw/status/marker。旧 `_ACC_FIX_V1` 名称只在内存映射为 canonical scene，原输入文件不改。

尚须单独审核新 B runner、fresh preflight、release、实际源解析与完整输出身份后，主审才能放行 Plant。该单场即使与旧 B 全状态相同，也只验证这条输入和这套新冻结 C3 源；它不会改写旧 72 场历史，也不会补齐旧 runtime-tree 缺口。无 raw MAT 内容被读取，无 MATLAB/Plant/训练/TEST 启动。

元数据收口：`SOURCE_IDS.json` 初次写入时 manifest 路径有换行，现已改为单行相对路径；按该路径重算 manifest SHA 与记录值一致，JSON 可解析。

源码定位：C3 runtime `run_dl1018_closed_loop.m` 第 16–24、51–58、375–380、606–631、820–850、1764–1792、1962–2023 行；wrapper `run_episode_dl1018.m` 第 6–18 行；B 构造器 `controller_options_dl1018.m` 第 8–20 行。锁定文件与哈希见同目录 `SOURCE_IDS.json`。