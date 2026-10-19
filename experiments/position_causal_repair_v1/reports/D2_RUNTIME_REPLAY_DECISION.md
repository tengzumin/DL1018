# D2：实际运行链重放、标签分解与适应探针

本阶段全部读取历史日志离线重放；新增 Plant=0、encoder fit=0。6 场 TRAIN 的 B/POS_OFF/P_INIT 与两场 G06 P_A 均从原始 run_start/raw_run 重放。

## 实际部署/日志一致性

- 6 条 Initial run_start 中完整 Initial 模型、归一化、W0、cfg 与当前 Initial 包匹配；两条 G06 P_A 完整 Final 模型与 Selected 包匹配。六场各行为的场景数组、初始状态、风、参考、臂命令/臂长与 C0 cfg 逐项完全相同；姿态 RBF 开/输出/更新配置一致。

- 8 条实际在线运行均回放 1968/1968 个有效 Head 事件。用生产 `position_stage1_model_forward_v2` 和 `position_stage1_update_head_pcf_v3_5` 逐事件重放：最大数值差 1.99e-15；W0 复位、输出先于更新、下一事件权重接续、100 Hz dt、beta、PCF eta、ZOH 与力到加速度闭合全部在浮点容差内。

- 六场 × 三角色的 18 份 H5 由现有 exporter 重新导出：X14、target_raw、target_clip、事件顺序/ready边界、事件时间最大差均为 0；标签闭合最大差约 3e-15 m/s²；Initial 在线记录的 X14 与导出逐项相同。

- 因此，已检查样本上没有发现模型装载、X14、Head更新、PCF、beta、ZOH 或单位/标签注入错误。H1 对这 8 条实际在线运行：NOT_SUPPORTED（限定为被重放的运行，不能扩大为所有历史航次逐条证明）。

## 同场残差来源

- 18 条历史 bridge 日志的分解闭合误差最大 1.33e-14 m/s²，按原式 `d_effective=d_wind+d_allocation+d_attitude_realization+d_mapping`。组件 RMS 与交叉项分别保留；各分量 RMS 不能直接相加。

- 六场桥接逐场/逐角色、相位与时间箱结果见 `D2_LABEL_COMPONENT_SUMMARY.csv`；事件级列、当前误差面、实际速度/姿态、nominal acceleration、commanded force、beta、eta、输出/更新标志见 `D2_LABEL_COMPONENTS.csv`。

- 实际补偿误差定义为 `d_applied - d_effective`；误差面余弦只描述同轨迹方向关系。互相关/相邻事件变化均受闭环反馈混杂，不作为单独因果时延证据。

## 固定 Head 与早段适应探针

- 支持块预先固定为有效事件 5.5–10 s，查询块 10–20 s；使用 G04 TRAIN 384 场选择各编码器正则化，VAL 48 场只评估。alpha 网格为 [0.0001, 0.001, 0.01, 0.1, 1.0, 10.0]，一条航次内按连续时间块拟合/查询，没有随机拆散邻近事件。

- Initial 选中 alpha=0.01，Final 选中 alpha=0.01；累计矩阵解 4704 次；均不计 encoder fit。

- G04 Initial 生成的同一批闭环状态上，同时测固定 Initial/Final W0、早段 ridge、真实 Initial online Head；Final 的 G04 结果是离线反事实，不代表闭环。两场 G06 P_A 是真实 Final online 轨迹，但不能替代同场 Initial/Final 的 D3。

- 汇总表 `D2_ADAPTATION_PROBE.csv` 按 TRAIN/VAL、任务、频率类别分别给出 support/query Q；`D2_LOCAL_SENSITIVITY.csv` 仅在六场记录点每隔 8 个 ready 事件做有限差分，报告对位置误差/滑模面的局部输出敏感度。

- 合法 X20 线性信息探针：完整场景分组四折，只用 TRAIN 384 场选择正则化，VAL 48 场一次评估。Validation equal-scene Q：X14=0.491362，X20=0.475756 m/s²。该结果仅是线性信息增益探针，不等同于 X20 KAN 或闭环增益；逐场见 `D2_X20_INFORMATION_PROBE.csv`。

## 对 D4 分支的影响

- 当前重放不支持 H1 实现错误。D1 显示 Initial 在大多数场景胜 POS_OFF，却仍输 B；优先区分固定 Head 与在线适应目标、合法状态信息，不能把结果归咎于模型包差异。D3 同场桥接完成后才冻结 D4 家族。

- D1 同场 Q 分箱差（P_INIT−B / P_INIT−POS_OFF）见下表：

| 时间段 | P_INIT−B (m)；胜出场数 | P_INIT−POS_OFF (m)；胜出场数 |
|---|---:|---:|
| T_0_1p8 | +0.00472884; 20/432 | -0.0139833; 402/432 |
| T_1p8_5 | +0.0372521; 0/432 | -0.0476175; 405/432 |
| T_5_10 | +0.0278282; 13/432 | -0.0754006; 428/432 |
| T_10_15 | +0.0168221; 32/432 | -0.085141; 420/432 |
| T_15_20 | +0.0108857; 66/432 | -0.082497; 422/432 |

位置阶段顺序上，Student 与 B 的差距在臂开始变化前已经存在；同时 Student 在形变后显著优于 POS_OFF。这里是已观察的同场关联，不等于确认具体网络结构因果。
