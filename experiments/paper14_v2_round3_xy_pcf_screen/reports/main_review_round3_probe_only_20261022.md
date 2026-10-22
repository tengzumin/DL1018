# 主模型审核：R3 单场 PROBE（scene payload 修复后）

审核时间：2026-10-22T00:17:04.662Z。决定仅覆盖一次 20 秒 PROBE，固定 VAL 场景 DL1018_VAL_T2_C00_W10。不批准 CONTINUE、剩余 11 场、72 场扩展、训练或 TEST。

## 核验与决定依据

当前冻结锁 SHA256 为 $lockSha；任务书 SHA256 为 $taskSha；11 项 setup manifest SHA256 为 $setupSha。runner SHA256 为 $runnerSha，静态检查源 SHA256 为 $staticSrcSha，启动器 SHA256 为 $launcherSha。候选仍是单因素 FEATURE Head 更新面 eta mask [1,1,0]，seed 2026102001，模型 $(@{normalizer=; raw_index=; single_difference=; analysis=; scene_list=; schema=ROUND3_XY_PCF_SCREEN_INPUTS_V1; experiment_dir=C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\paper14_v2_round3_xy_pcf_screen; repo_root=C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018; run=; scenes=System.Object[]; rescores=System.Object[]; runtimeFiles=System.Object[]; model=; matlab=; model_binding=; reuse_manifest=; lineage=; safety=; mechanism_evidence=System.Object[]; scoring_helper=; scene_payload_identity=; plantFiles=System.Object[]; setupFiles=System.Object[]; taskbook=; upstream_round1=; frozen_taskbook_manifest=; upstream_round2=; localRuntimeFiles=System.Object[]; round2_off_raws=System.Object[]}.model.canonical_id)，不训练、不改模型或输入。

发生过两次尚未产生候选航次的启动故障：初次 PowerShell 7 日期转换曾将 UTC deadline 当成本地时间，Luna 修复为保留 ISO 日期字符串；修复后 MATLAB 启动并在 R3 对 B raw 的位置数组方向断言处退出。原始 MAT 的 B 场景时间轴是 20,001 点、0 到 20 秒，位置数组实际为 20001×3；R3 原断言错误地只收 3×20001。R1/R2 对同一哈希 B raw 允许两种方向，并允许原始 scene ID 后缀 _ACC_FIX_V1，同场都曾稳定运行 20,000 transitions。这里是新 runner 断言过严，数据和采样条件没有改变。

当前 runner 仅放宽为接受 3×20001 或 20001×3，且仅允许冻结 ID 或该 ID 的 _ACC_FIX_V1 别名；它只把 scene_id 元数据规范化，不转置或改物理数组。静态测试现精确要求这两个 ID 分支和方向无关的尺寸条件，避免重复引入回归。冻结场景身份记录将 ON/B 的 14 个物理字段、20,001 个时间点绑定为相同 payload，最大物理差为 0。

新证据均通过且相互绑定：MATLAB smoke SHA256 $matSha；Python parity SHA256 $pySha（最大差异 4.440892098500626e-16）；静态报告 SHA256 $staticSha。8 项 scorer synthetic tests 通过，输入身份核验确认 12 个 VAL、24 份 ON/B raw、12 份 R2 OFF raw、候选 runs 为空且 TEST 未访问。当前修复未改变评分器或任何闭环参数。失败的 scene assert 在创建 attempt 目录与调用 episode/Plant 前执行；没有 candidate raw、run_start、status、probe summary 或新 MAT 输出。

独立 GPT-6-Luna xhigh 审阅确认 runner 物理数组不变更且无 P1 blocker，并要求静态测试精确锁定 alias 分支；该覆盖缺口已修复，setup lock 和三份离线报告随之重新生成。根会话也重新核对当前 lock/setup 哈希、报告绑定关系，并再次运行 8 项 synthetic tests 与 inputs-only identity。根会话模型无法由工具切换或独立验证成 Luna xhigh，不声称符合该模型设置。此前 review/preflight 已归档为旧 lock 证据，不适用于当前决定。

## 边界与决定

闭环 ISS/UUB/误差界理论 gate 仍未通过。PROBE 仅检验单场可执行性、身份、因果日志、安全和资源，不构成性能或论文结果证据。TEST 继续封存。**APPROVED：仅允许一次固定场景 PROBE。** 启动前必须执行新的 PowerShell 7 mode-specific fresh PASS preflight；模式、lock SHA、review、MATLAB 进程、GPU、磁盘与 deadline 任一检查不通过都不得启动。PROBE 完成后必须停止，先独立审核原始 raw、run_start、status、输入身份、mask 方程、安全和耗时，再决定是否 CONTINUE。
