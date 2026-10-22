# 主模型审核：R3 单场 PROBE

审核日期：2026-10-22（Asia/Shanghai）。决定范围仅为 R3 顺序 1 的单次 20 秒 PROBE：`DL1018_VAL_T2_C00_W10`。这份审核不授权 CONTINUE、剩余 11 场、72 场扩展、训练或 TEST。

## 核验结论

我检查了冻结任务书、R2 输入继承、R3 源码锁、实际候选与上游闭环 runner 的差异、执行器/安全日志、评分器、launcher、preflight、离线 smoke 和独立 Luna 复核。候选仍只有单因素 `FEATURE` 更新面的 eta mask `[1,1,0]`；X/Y PCF 协调保留，Z 轴更新面不扣 eta。候选 Head/PCF/Plant/执行器、模型、训练、场景与步长没有随评分器修复改变。R3 runtime 相对锁定上游仍只增加 mask 强制、事件日志字段和 mask 后更新面的计算。

独立复核识别的两处评分实现缺口已修复并列入当前冻结包：

- `tilt_limited` 现经锁定 `h5_arr` 逐 raw 读取；缺字段、非 20,000 tick、非有限或非二值会失败。每场报告 B、PCF-on、PCF-off 和候选的触发数/比例。“新增”按冻结配对记录逐 tick 定义为候选触发而三个控制均未触发；任何候选独有触发会阻止筛查通过。
- `transition_time` 现需为 20,000 个有限 tick，并逐点匹配 `k * plant_dt_s`；`plant_dt_s=0.001 s`，绝对容差 `1e-12 s`，`rtol=0`。四方法时间轴还必须逐元素一致。

八项合成 scorer 测试覆盖 tilt union、新事件、长度/取值/有限性，以及固定网格、非均匀内部 tick、非有限时间和步长错误。修复后的 MATLAB smoke、Python parity、静态检查和输入身份核验全部通过。Python/MATLAB 最大误差为 `4.440892098500626e-16`。当前 source lock SHA256 为 `f6a45b2ef9aac6f4ff365b14466868b68fbd3111b0fe8ee2a12a5ef76c852fa4`，taskbook SHA256 为 `a9d876f0e22175785f184707ba0f35090be3adf6a25317e83c39a9c88a1ccb4a`，setup manifest SHA256 为 `6e1c72d4577adadf0fc986bcccde47a6b4712aa6dc49baf93c957deb17330905`，runner SHA256 为 `a10765729ce97611c8d0c2d076ce5311a683fde0cd81b87c66fd200839f49a14`。

最终证据：`reports/static_test_round3.json` SHA256 `05bb882b08c3d6bf84569cca046b3ee6047dc29a8cb389d00812dad7b681f6b8`；MATLAB smoke SHA256 `a8bfd526f3ede1b127651577c42fb8c6553008269b0d46a28b129e19239feb94`；Python smoke SHA256 `69bd3f7f39a4752fc9cfb6d29c2994ec00a0e431e23d375c0b29182e3ae3a27d`。Luna xhigh 的最终只读复核无 P1 blocker。

无 marker 的最新只读 preflight 绑定上述 source lock，MATLAB 进程数 0、GPU 资源审计 PASS、可用磁盘 167,039,791,104 bytes；唯一阻断项是缺少本审核记录，且没有授予任何运行授权。launcher 将重新执行 mode-specific preflight，并在 PASS、锁与审核记录匹配时才启动 MATLAB。

## 理论与证据边界

部署链的闭环 ISS/UUB/误差界证明仍未达到任务书验收：现有局部权重/滤波/输出界不足以证明含 PCF、采样保持、姿态/分配/电机限制的全闭环稳定性。故 TEST 继续封存。本次 PROBE 仅检验锁、记录完整性、实际事件方程、单场安全和耗时，不构成 H3 性能证据，也不证明方法新颖性或泛化。

执行与独立审核子代理按用户要求指定 GPT-6-Luna xhigh；协作工具不能核验推理速度，因此没有把“正常速度”写成实测结果。当前主 Codex 会话的模型身份/推理级别不能由工具切换或独立核验；本审核不声称主审模型满足 Luna xhigh。主审职责仍由当前会话完成。

## 决定

**APPROVED：仅允许一个 PROBE。** 启动前必须由 PowerShell 7 生成全新 PROBE preflight，并且只有它报告 PASS、当前锁/报告哈希一致、MATLAB 进程为 0、GPU 审计 PASS、磁盘和截止时间门槛通过时才可调用 launcher。PROBE 完成后必须停止；CONTINUE 需另行审核 raw、run_start、status、输入身份、mask 方程、性能、安全和耗时，并创建独立审核记录及新的 CONTINUE preflight。
