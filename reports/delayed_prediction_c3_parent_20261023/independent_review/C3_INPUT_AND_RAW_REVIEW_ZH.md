# C3 输入、setup 与 probe runner 独立审核

状态：输入/setup 门通过，最终 runner 源码静态审通过；尚无 C3 probe release，因此没有 Plant 启动授权。本审查未读取 raw/MAT 内容，也未运行 MATLAB、Plant、训练或 scorer。

## 已通过的输入与 setup 门

冻结的 C3 source lock SHA-256 为 863328963959c63d4628060fcff21e01d5322c487d077b5c20721d24ed9314a2，准备入口 prepare_c3_probe.m SHA 为 e4b3e5b10166396fa3ddf47055fe2f68d3c6a00dcaf1e3112dc2fce8aee14b0b，contract SHA 为 fc2fd5998915a3074f3d43706baea53cceb7d49176115fead94e2。锁中包含 c2_release，精确绑定 C2_RELEASE_v3.json SHA e075d00b0aad54b96587e7652378cee124e47ab3715186d80530197ec111b50e；C2 release 身份字段存在并被 runner 核验。

成功的 C3_PREPARE_RESULT.json SHA 为 b844c86de21d321d9cc03d1ef6dd69dfeecb9aa45e71f5589bf6eb7ec7602fb3，配置/选项快照 C3_PREPARED_CONFIG_OPTS.mat SHA 为 71c95e5cb9cc537fcc1fc2ea82f86c78c0f3f624de4de7a00951127950d4a64e。结果记录 cfg 与冻结 C2 run_start 完全相同，opts 唯一差异是 position_delayed_prediction_enabled；候选固定 tau=1s、rho=0.01，并绑定 DSSM14/W0/normalizer 身份。scene 原始 ID 是 DL1018_VAL_T2_C00_W10_ACC_FIX_V1，按 C2 已有规则规范为 DL1018_VAL_T2_C00_W10。结果明确 plant_calls=0、run_episode_called=false、training/optimizer 步数为零。

RUNTIME_CHECKCODE_EXIT.json 和 MATLAB_NO_PLANT_EXIT_03.json 均记录 exit 0、plant_called=false。它们通过 no-Plant setup/source 检查，不代表闭环执行 parity。C3 runtime 的 MATLAB/Python helper 有独立合成 parity 记录，但没有执行整条 runtime 或 Plant。当前目录仍无 C3_PROBE_RELEASE.json。

## Raw verifier 静态复核

verify_c3_raw.py 当前 SHA 为 275de5a3e56fd3c1e41f62f6a2a5f5ad95d44416dc022a4f6daace1e46f77b96。静态核对通过其索引与公式：事件为零基 320:10:19990；延迟目标由 v[k]-v[j] 与独立读取的 a_f[j:k] 十毫秒块均值构造；首事件明确无 previous；预测项使用旧 phi_j 与当前 W_before,k；输出先于更新；单步更新同时包含 tracking、leak、prediction 与一次 box projection。CLI 强制提供来自已保存 status/冻结 C2 账本的候选及 comparator SHA，不能用现场自算 hash 替代冻结身份；输出拒绝覆盖。此处仅审源码，未读取或重算 raw。

## 最终 runner 静态复核

run_c3_probe.m 最终 SHA 为 ca535a7dd12bcc83fd6a8888147440d3e165ceb622c071a470ec2ead2c963f4c，大小 20,937 bytes。早期 19,821-byte 草稿缺少完整路径断言和全局 marker 门；最终版已补齐，旧稿缺口不再是当前阻塞。

runner 会核验 C3 release 对精确 runner 路径/SHA、source lock、PREPARE result 和 cfg/opts snapshot 的绑定；同时核 C2 source lock、release、执行账本、probe summary 与具体首场 C2 raw/run_start 的锁定关系。C3 lock 的 c2_release 字段确实存在。它将 C3 scene 的 alias 与 canonical scene ID 对齐，并在运行前重新验证 B raw、C2 raw、run_start 和 snapshot 身份。

来源解析门现已覆盖全部执行文件：锁中 9 个 runtime 项含 8 个 .m，22 个 Plant .m，加上隔离的 C3 core、wrapper 和 prediction helper 后得到 32 个源条目，其中 31 个 .m、1 个 effective-config MAT。active_source_files 将锁定 runtime core/wrapper 替换成隔离副本，逐项 SHA 验证全部 32 个条目；对 31 个 MATLAB 文件逐项要求 which 精确返回锁定绝对路径。独立对照锁清单，31 个函数 basename 均唯一，当前文件 SHA 全部匹配。runner 在 fresh MATLAB 调用中先执行 restoredefaultpath，再加入锁定来源并做逐项 which 检查；若路径被遮蔽会在创建 attempt/Plant invocation 前 fail closed。init_dl1018 也包含在逐项检查中，且明确取自 C1 R2 runtime lock。

首航次预算与防重跑门闭合：runner 要求单次 probe release、0 training/optimizer、0 full72/TEST；启动前确认 runs_c3 下 attempt_started.marker 与 first_plant_step.marker 数量均为零，同时拒绝已存在目标 attempt、summary 或 marker。单重负载共享文件锁在创建 attempt 前获得；预留 80 MB、1 GiB 总输出上限、30 GB 磁盘余量和写后上限均有检查。失败保留记录且不自动重试。目录当前没有 runs_c3，已观察到的两个 marker 数均为零。

未执行最终 runner，所以 fresh MATLAB 的逐项 which 门尚未经过一次真实入口调用；此门位于任何 attempt marker/Plant 调用之前，且新运行应使用 fresh MATLAB。runner 源码本身的静态检查通过。没有已签发 release，本文仅给静态源审 PASS，不启动 Plant，也不预先批准 probe。

## 结论

C3 输入身份、no-Plant PREPARE 与最终 runner 静态源/预算门均通过。主审可在独立 fresh preflight 和签署精确绑定此 runner 的单场 release 后决定是否启动 probe。首场运行后的 raw 仍须按独立 verifier 审核完整事件、物理目标和联合更新；helper parity、setup 输出与 source SHA 不替代该审核。

## 单场 probe 原始日志审核

C3 status 为 RUN_COMPLETE_RAW_PENDING_AUDIT，内部 log_status=STABLE；status 声明 raw SHA 为 1434368441a5fec4fbd9bc5154014beeb453045237a6f93ff20d44dd33171f6f，审核前后文件 SHA 与该值一致，大小 50,049,146 bytes。run_start SHA、首个 Plant marker SHA、release SHA、source lock、PREPARE result 与 snapshot SHA 均与 status 一致。raw 内 runIdentity 中的 scene、condition、release/source-lock/PREPARE/snapshot/C2/B identities 也与 status 一致；training_steps、optimizer_steps 为 0，TEST_accessed=false。单场有一条 attempt_started marker 和一条 first_plant_step marker。

我用锁定 C2 ledger 的 comparator SHA 007d008db2029ea53a71b6478cd2086f82ad55360d86656f83b91827e8048900 执行已审的 verify_c3_raw.py；comparator 路径来自同场冻结 baseline 项并与 status 的路径一致，SHA 同时匹配 ledger 与 status。输出 C3_PROBE_RAW_INDEPENDENT_REVIEW.json SHA 为 efbbe12e6e29646a11c0b83f3537d3ba619cda94d4f157b97a772e93face4e30。此处是独立运行该共享审计程序，不是另写算法的第二实现；程序直接按 disjoint a_f[j:k] 块重建标签，并验证外部输入摘要、head 递推和更新连续性。

通过 1,968 个有效事件（零基 320:10:19990）。最大绝对误差：beta clock 0；event dt 1.99e-15 s；延迟目标 4.63e-13 m/s²；raw 输出与 W_before×phi 4.44e-16 m/s²；beta/clip 应用 4.44e-16 m/s²；完整 joint update 4.58e-15；weight continuity 0；prediction-term norm 3.57e-15。均低于 1e-10 的逐项容差。外部输入 digest 与 C2 一致，摘要 SHA 为 954cddfbe68c7682dc176ac98cfe9d7936e61101805a8cf4316c6fba4b10809a。C2 scorer 还验证 20,000 transitions、状态/reference 全有限、STABLE、无 safety-stop reason、控制时间有限；motor saturation fraction 与 generalized-clipped fraction 都为 0。计算耗时仍标记 NONISOLATED_NOT_FORMAL。

本审核认为首场工程、数据身份、输出/更新时序与安全完整性门通过，未发现阻止剩余固定 11 场的技术问题。是否继续仍由主审按已签阶段授权发下一 release；不以单场 Q 选择场景或宣称机制性能。此判定不替代剩余场次的逐 raw 审核。
