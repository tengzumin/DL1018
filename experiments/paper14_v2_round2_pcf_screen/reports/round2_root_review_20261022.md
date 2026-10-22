# DL1018 Round 2 根因审核与决定

审核日期：2026-10-22 Asia/Shanghai（2026-10-21 UTC）。审核对象是隔离的 `PAPER14_V2_R2_PCF_OFF_SCREEN_20261022_REVISION_4`、12 场 PCF-off 闭环筛查、其冻结配对输入，以及 PCF-on VAL raw 的同状态离线重放。只读使用本轮 VAL 输入；未读 TEST，未启动训练，未改旧 raw/模型/缓存，也未停止任何作业。检查时 MATLAB 进程数为 0。

## 决定

**R2 未通过预登记门槛；不扩 72 场、不调参、不解封 TEST。** 12 场 OFF 候选均完整且安全，但 Q 指标整体退步。此结果否定“整套 PCF 协调关闭是当前优先修复”的候选方向，不能单独宣称已经证伪 PCF/在线更新的全部作用，也不能把不同闭环轨迹差异归因成 eta 单状态的因果证明。

在剩余的第三轮额度内，唯一可检验的新假设是：**保留 X/Y 的 PCF eta 协调，只在 FEATURE Head 的 Z 更新面上不扣除 eta（mask=`[1,1,0]`）；是否能保留水平收益并取得 PCF-off 的 Z 改善，必须由同一冻结 12 场筛查决定。** 这是从 R2 逐轴结果提出的待检验机制，不是已验证改进。该轮不得训练，不得改其它网络、姿态控制或 Plant 条件；12 场门槛不通过就停止新增闭环。执行入口须另写隔离任务书、绑定 runner/helper/model/input 哈希，并由主模型审核后才能启动。

## 源码、单位和时序

实际执行代码不是工作区相似名称的 helper，而是 R2 输入锁中的隔离 runner 与 `position_only_search_head_step.m`。锁定 FEATURE 头在每个事件先算 `raw = W_before' * phi`，再输出 `beta * clip(raw, ±dmax)`，之后才按

`W_next = clip(W + dt * (-gamma * beta * phi * s_eff' - 0.002 * W), ±60)`

更新权重。R2 对照与候选均使用同一个 FEATURE helper；冻结模型、W0、normalizer、γ=12、β、Head、姿态环、C0/J0、Plant、执行器、X14 和采样条件一致，唯一处理因素是整套 `command_filter_coordination_v3_5` 开关。PCF-off 同时停止 eta 递推并令 eta 保持零；这不是只改一个输出轴。

信号的物理量关系经实际代码、锁定 raw 和全事件重放核实：

- `surface = v_ref + k1*(p_ref-p) - v`，单位 m/s；
- `a_f = (thrust/mass) R(euler_filtered) e3 - g e3`，`r_f = a_req - a_f`，单位 m/s²；
- `eta[k+1] = exp(-k2*dt) eta[k] + ((1-exp(-k2*dt))/k2) r_f[k]`，`k2=[4,4,4] s⁻¹`，故 eta 单位 m/s；
- PCF-on 更新使用事件开始时的 `s_coord=surface-eta_before`，再按 `[7,8,10] m/s` 限幅；事件时刻与 eta-before 日志一致。`a_f/r_f` 不直接进入控制命令，`r_f` 通过 eta 影响后续 Head 更新面。

任务书有一个文档单位错误：将 `[7,8,10]` 限幅写成 `m/s²`；实际 `default_config.m` 的字段是 surface `s_limit`，单位 m/s。PCF eta 公式与实现本身没有发现单位、符号、时序或限幅错误。

## 12 场闭环筛查

独立审计从 36 个 B/PCF-on/PCF-off raw 按锁定的三维位置 RMSE 公式重算，12×3 个 Q 与配对 CSV 完全一致；所有三种方法的 12 场均为 finite、complete、safe、identity-verified。R2 OFF 运行均为 STABLE、20,000 transitions、在线事件 1,968 次。主指标按未舍入值和 `1e-12 m` 容差判断。

| 场组 | n | B 宏平均 Q (mm) | PCF-on Q (mm) | PCF-off Q (mm) | OFF−B (mm) | 结果 |
|---|---:|---:|---:|---:|---:|---|
| 高频 W09–W14 | 6 | 9.633 | 9.713 | 10.847 | +1.214 | 0/6 胜 ON；高频 Z 对 ON 为 4/6 胜 |
| W15 | 3 | 8.629 | 8.985 | 10.137 | +1.508 | 对 B 不满足不劣 |
| W00–W08 | 3 | 13.502 | 10.736 | 12.124 | −1.378 | 对 B 不劣 |
| 全 12 场宏平均 | 12 | 10.349 | 9.787 | 10.989 | +0.640 | OFF 对 ON 0 胜/12 负；对 B 5 胜/7 负 |

故高频 Q、W15 和全局宏平均三道筛查门槛失败。高频逐轴 `OFF−ON` 均值为 X `+1.156 mm`、Y `+1.009 mm`、Z `−0.456 mm`：PCF-off 的 Z 有改善，但水平轴退化使三维 Q 变差。全 12 场、全四组明细见 [配对结果 CSV](../reports/round2_screen_results.csv)、[摘要 JSON](../reports/round2_screen_summary.json) 和 [独立重算记录](../reports/round2_gate_independent_recalculation.json)。

## 同状态机制重放

`offline_replay_round2.py` 从 12 份身份匹配的 PCF-on VAL raw 只读提取 23,616 次 FEATURE 事件。对全部事件核对了 `r_f=a_req-a_f`、1 kHz eta 离散递推、eta-before 时间戳、surface 与 FEATURE 的第 4–6 项、`surface-eta`、分轴限幅、更新前输出和更新后 W。最大误差为：残差、事件时间戳、面关系、限幅和权重更新均 `0`；按精确离散递推复算 eta 的舍入误差为 `3.01e−15 m/s`；输出重放最大 `4.44e−16`；跨场初始 W0 完全相等。

另在每个记录事件状态上以相同 W、相同 φ 比较 PCF-on 与“同一事件直接使用 surface”的即时更新方向，再递归重放关闭 eta 的离线 Head 输出。此处固定的是 PCF-on 的记录状态，**不含 Plant 状态反馈，不是 PCF-off 闭环成绩或闭环因果估计**。高频组汇总：

| 输出轴 | eta RMS (m/s) | surface RMS (m/s) | surface 与 surface−eta 符号翻转比例 | 同一 W 的更新梯度余弦 | 固定记录上的离线 Head raw 差 RMS (m/s²) |
|---|---:|---:|---:|---:|---:|
| X | 0.01538 | 0.01539 | 36.4% | 0.306 | 0.11625 |
| Y | 0.01783 | 0.01515 | 39.0% | 0.241 | 0.14262 |
| Z | 0.00207 | 0.00523 | 13.4% | 0.775 | 0.15254 |

这与闭环现象一起支持一个更窄的测试问题：PCF 面修正在水平轴上常与未修正面的方向不同，而 OFF 闭环的水平 Q 变差；垂直 eta 信号更小、符号翻转更少，而 OFF 的 Z RMSE 在多数高频场改善。它仍然只是选择下一项可区分假设的证据，不证明 mask 的闭环结果。逐场×时段×轴明细见 [同状态离线重放 CSV](round2_same_state_replay_by_scene_window_axis.csv)，逐项误差与输入 SHA 见 [重放审计 JSON](round2_same_state_replay_audit.json)。

## 评分器实现错误与审计缺口

锁定原版 `rescore_round2.py` 实际运行时在写入前失败：R1/R2 identity 比较对 `runtimeFiles` 假定必有 `name`，但冻结锁只有 path/SHA；若继续则访问缺字段会抛 `KeyError`。另外 scorer 取 `RMSE_X` 大写键，但锁定 `raw_scan.py` 返回 `RMSE_x`。为保留证据，原版与冻结锁未改；仅在隔离副本 [审计评分器](../rescore_round2_audited.py) 增加 path stem 作为缺失名称、并对齐小写轴键。变更不动公式；独立 raw 重算与该副本分数全量一致。原 scorer 的失败属于实现错误，不是实验结果失败。

审计副本没有写回冻结 lock 的 `setupFiles`，因此需在发布根报告时同时绑定副本 SHA。评分器对 `FEATURE` 和 `run_start.mat` 内 scene/inputIdentity 的显式断言不足；本次由 OFF `run_status`、ON raw 字段、冻结 `input_identity` 与全 12 raw 参考输入逐元素核验补上，均符合任务书。此为评分器审计覆盖缺口，不改变本轮数字。

独立 Luna xhigh 代码复核进一步指出，同状态重放脚本最初虽选中了正确的 12 份 raw，但本身没有把结果表场景与冻结场景清单、ON/B 重评分表的路径/SHA 完整绑定，也没有禁止 TEST 路径；比较函数会忽略局部 NaN，参数/时钟检查仍有硬编码。该发现不改变已复核的输入或数字，但会降低未来重放的失败关闭能力。现已在隔离审计器中补齐：严格匹配冻结 VAL 清单和两份冻结重评分表；核验每场 run status、run-start、模型/normalizer/W0/scene identity 与 MAT 内部 source scene ID；对实际 B raw 重新计算 SHA；检查 eta 初值为零及 `eta_before[k+1]=eta_after[k]` 连续关系；拒绝 TEST 标记或路径，并断言两份清单仅含 DEV/VAL；要求参与比较的数值有限；从锁定 default_config、Plant transition_time、Head 频率和哈希锁定 FEATURE helper 提取/核对 dt、k2、surface 限幅、权重投影。审计器重跑仍得到 12 场、23,616 个事件，初始 eta 与跨步连续误差为 0，eta 递推最大误差 `3.00454e−15`，输出重放最大误差 `4.44089e−16`，其他方程核对误差为 0。两份被冻结重评分清单确认为 DEV=24、VAL=48、无 TEST 行；本审计只访问 12 个冻结 VAL raw。此修复只增强审计器，不修改原评分结果、旧锁或任何运行产物。

## 历史结论与仍需交付

历史论文起点及 Round1 结果沿用 [第一阶段父审](../../../reports/paper14_v2/phase1/PARENT_SOURCE_REVIEW_ZH.md)：旧 G12/R32 成功只覆盖旧模型包的 8 个 FIG8 场；当前 corrected DSSM14 是不同 seed、数据、模型与完整场景配对，不能把旧成功迁移为当前验证结论。已确认的旧 FIG8 参考生成 Y/Z 二阶项漏乘因子 2，以及 KAN `P_NEW` 未应用 dispatch，是历史实现问题；当前 corrected DSSM14 高频失败并未发现新的监督、PCF 或 Head 实现错误。旧成功包、当前包和部分 B/raw 不同属于实验条件变化，不能混为一个代码回归。

理论与文献门槛仍未通过。现有审查只支持参数盒投影、输入有界时 eta 的离散滤波界，以及理想连续位置外环的条件界；尚无与 1 kHz Plant、100 Hz projected-Euler Head、ZOH、姿态和执行器限幅完整对应的数值 ISS/UUB 定理。不能进入 TEST，直到第三轮候选通过开发门槛，且理论、机制贡献与消融审计也完成。

## 复现与输入保护

离线重放命令：

```powershell
python -m py_compile "experiments/paper14_v2_round2_pcf_screen/offline_replay_round2.py"
python "experiments/paper14_v2_round2_pcf_screen/offline_replay_round2.py"
```

加固后的离线审计器 SHA256：`1d7e78d855ccd4c11e996c86c9e244a48e78c60dc93346c55b06829d1d5fcacc`；审计 JSON SHA256：`6f4f75adc18b5f07cda29f60d5a7518670fb93613658cd8b8fbdd9fec3688aed`；逐场逐时段 CSV SHA256：`ea18f81fc1e2503acdf60f90afb278758f2c2fe369e87ec0944e3b0b322618bc`。输出身份及场景明细见 [重放审计 JSON](round2_same_state_replay_audit.json)。

本脚本校验锁定 helper、PCF step、反步面、参数源码和 12 个 ON raw 的 SHA；只向本 R2 `reports/` 写 JSON/CSV，不改输入 MAT。round2 独立审核代理对闭环评分独立复算，主模型另运行同状态方程重放。TEST、历史缓存、模型和原始 MAT 均保持原位。
