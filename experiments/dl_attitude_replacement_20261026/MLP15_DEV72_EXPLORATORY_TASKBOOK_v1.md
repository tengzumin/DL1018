# MLP15 姿态替代候选：探索性 DEV72 闭环评估任务书 v1

日期：2026-10-26。此版本是在原六场 pilot v2 判为 FAIL 后新增的探索性开发阶段。不得把它说成原 pilot 门通过；不得用于确认性结论或解封 TEST。

## 1. 固定候选与范围

- 候选：冻结 DL_MLP15，训练和 checkpoint 不变，best step 59,000。13 个因果运行时输入、15 个历史事件；监督标签来自 B 日志姿态 RBF 原始输出。
- 控制栈：C5 DSSM14 位置控制器（含原位置在线头）、BS 名义姿态控制器、Plant、allocator 与执行器保持 v2 身份。只替换姿态 RBF 的输出/更新。
- 候选不得读取/计算形态依赖 Jhat/Jdot_hat、Plant `rho_true/rhoDot_true`、Plant 真值力矩、RBF 隐状态；不启用 observer 或 physics feedforward。仅使用固定 C5 名义 J0 和原有输出边界。
- 范围为 C5 DEV72 input lock 的 72 个 DEV/VAL scene IDs。GHP7 pilot 的六个 payload SHA 与该 DEV72 cohort 不同；六个 raw 不冒充 DEV72，也不抵扣本阶段 72 次运行。
- 主对照为 `B_TRACEABLE_C3CORE_V1` 锁定的 72 份 B raw/status。逐场验证 raw、status、scene ID、external identity 与 SHA 后复用；不重跑 B 或 C5_RBF。C5_RBF 有身份合格的 raw 时列为次级参考，否则标缺失，不为凑齐而重跑。
- TEST48 不读取、不解封、不运行。

## 2. Pilot 失败的处理

原 `MLP15_CLOSED_LOOP_PILOT_TASKBOOK_v2.md` 要求零倾角投影事件；G2/W00 有 344 次，因此原 v2 gate 明确保留 FAIL。新阶段只根据已有证据区分同一个共用命令投影与硬安全事件，不回写旧结果。

DEV72 逐场记录 `tilt_limited` 次数和持续时长，并与同场 B 比较；候选任一场投影次数不得高于 B。任何安全停止、非有限轨迹、电机饱和或 generalized clip 均为硬失败。倾角投影计数仍完整披露，不能称为零限制或安全证明。

## 3. DEV72 放行条件

- 72/72 候选与 B 场景身份、seed、reference、风场、形态 schedule 一一匹配；每条 raw 与 run status SHA 复核。
- 候选完整 20,000 transitions、状态稳定、所有指标有限；无 safety stop、电机饱和或 generalized clipping。
- 逐场 tilt projection 计数不高于配对 B，且报告全部计数；另报告每个风组与任务组。
- DEV72 等权平均位置 Q(0–20 s) 与 SO(3) RMSE 均严格优于 B；位置 Q 至少 62/72 场胜 B。姿态逐场胜负完整报告。
- W09–W14 高频组及 W15 无风组中，位置 Q 与 SO(3) 均不劣于 B。
- 候选相对 C5_RBF 的结果仅作次级描述；不要求位置胜 C5，但如有身份合格姿态基线则报告姿态差异。
- 六场 pilot 仅用于候选选择/风险分析，不与 DEV72 合并计算宏平均或胜率。

通过仅允许主模型审核后另行准备消融与一次独立 TEST48；本任务书本身不授权访问 TEST。

## 4. 数据、实现和资源

- 逐场复用 C5 lock v3 所引用的 B72 raw/status，需先独立核验路径、SHA、20,000 transitions、`STABLE` 与 external identity；发现不匹配即停在 no-Plant 阶段，不重跑基线。
- 新建只含 72 个 locked DEV/VAL ID 的 scene payload、源码副本、attempt marker、run_start、raw、status 与评分材料，均写入本 study 子目录。历史 raw/MAT/cache/模型/账本只读，不覆盖或删除。
- payload 只能由 B72 raw 中的输入 `scene` 变量导出；候选控制器仍通过既有 runtime API 只接收声明的传感器/控制特征。保留并审核 source `runIdentity` 的 external identity；严禁将 Plant 真值字段加到控制器输入。
- 新增最多 72 个 MLP15 Plant calls；不训练、不调参、不搜索第二候选，不重跑 B/C5，不跑 TEST。保留所有启动和失败记录。
- 启动前必须通过 MATLAB no-Plant 检查、MLP15/B72 输入 SHA 清单、源码哈希、选项因果与无惯量路径断言；每次启动前检查无其他 MATLAB/Plant 重负载进程。不得打断运行中的实验。
- 只用 PowerShell 7 启动。剩余磁盘不足 30 GiB 时停止新航次，不删除数据。

## 5. 报告要求

提供 72 场配对表、任务/风组和 XYZ 指标、早晚阶段、峰值、tilt projection、安全停止/饱和/clip、模型推理耗时、所有失败场。区间按场景配对估计；不能把单航次时间点当独立样本，不能宣称跨训练种子或实机泛化。清楚标注本阶段是根据 pilot 观察新增的探索性 DEV，不与预注册零投影门或独立 TEST 结果混称。
