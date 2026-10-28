# 高频与无环境风复查：源码、原始数据和外部方法

日期：2026-10-22。范围为当前 corrected DSSM14/KAN14 的 DEV24+VAL48、已完成 R1–R3，以及本次新增离线诊断。论文结果证据包仍为 NOT_QUALIFIED；TEST48 未读取。没有新增训练、Plant 航次、控制器修改或数据清理。本报告不是对 DL1009/DL1018 历史全谱系审计的重新宣称。

## 审核结论

保留 DSSM14 主线。它确有总体收益，72 场 Q 从 B 的 17.0581 mm 降到 12.3872 mm，改善约 27.38%，但 46/72 胜不足既定 62 胜。高频和无风的问题不是同一种已证实故障，也没有证据支持继续扩大网络、整体关闭 PCF 或仅凭输出幅值否定在线更新。

本次新增的最有价值证据有三项：

1. **W15 上固定 W0 对已测目标的先验拟合偏弱，原 TRAIN 数据上也有同类迹象。** 固定 W0 在 96 条原训练无风航次的晚段 X/Y 目标拟合，分别有 67/96、72/96 条不如零预测。在线更新随后明显缩小同状态目标误差。在候选自己的六场 W15 日志上也重复出现先验失配。它是否造成闭环落后、是否特由 PCF 目标错配引起，仍未知；这不是“把补偿置零就能赢 B”的反事实证据。
2. **PCF 协调后匹配的残差对象与离线 Y 不同。** 数值关系 Y+r_f=a_actual−a_f 在全部 72 场同时间戳成立；高频晚段 r_f 的 X/Y RMS 为 0.374/0.415 m/s²，不可当作小量略去。它是目标契约的具体待检验问题，尚不是已证实 bug 或闭环根因。
3. **本批没有 command-filter 加速度裁剪；在线更新平均改善了同状态的拟合与低频残差。** 因而“限幅卡住”以及“在线必然学坏”的解释被削弱。滤波动态、剩余相位和三维耦合仍需与裁剪分开研究。

下一优先事项是把 **预训练目标、PCF 坐标和训练样本身份接起来**，而非继续调 Z mask 或 Gamma。当前缓存字段不足以直接精确重标 Y+M r_f，必须先定位已有 TRAIN raw/日志可恢复范围。本周期三轮已用完，不以这份调查自动开启第四轮。

## 1. 最新结果究竟差多少

主指标为 0–20 s 三维位置 RMSE；逐场未舍入值、胜负容差 1e-12 m。均值为场景等权。

| corrected DSSM14 分组 | n | B Q (mm) | DSSM Q (mm) | 候选−B (mm) | 胜/负 |
|---|---:|---:|---:|---:|---:|
| W00–W08 | 38 | 23.2149 | 13.9696 | −9.2452 | 38/0 |
| W09–W14 | 28 | 10.7190 | 11.2445 | +0.5255 | 5/23 |
| W15 | 6 | 7.6473 | 7.6977 | +0.0505 | 3/3 |
| 全部 | 72 | 17.0581 | 12.3872 | −4.6709 | 46/26 |

高频 19/28 场绝对差小于 1 mm；若把 ±1 mm 内作为敏感性区间，则为 1 胜、19 近似持平、8 负。这只是补充，不能替换冻结胜负规则。W15 为 1 胜、4 近似持平、1 负。

无风按任务并不一致：FIG8 2/2 胜，平均 −1.0422 mm；HELIX 1/2 胜，+0.3981 mm；SQUARE 0/2 胜，+0.7955 mm。每任务仅两场，不能推成全任务泛化结论。

KAN14 高频 0/28 胜、平均 +2.4838 mm，无风 0/6 胜、+2.6350 mm。继续换回当前 KAN14 缺乏依据。

来源：[原配对表](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/reports/corrected14_full72_benchmark_20261021/PAIR14_SCENE_RESULTS_VS_B.csv)，本次 [全量分组](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/reports/hf_w15_reinvestigation_20261022/paired_summary.csv)、[敏感性](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/reports/hf_w15_reinvestigation_20261022/win_sensitivity.csv)、[全部 70 条输场：DSSM26+KAN44](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/reports/hf_w15_reinvestigation_20261022/all_losses_70.csv)。训练数据的 VAL 与这张开发评估表中的 VAL 属于不同记录，后文始终分开说明。

## 2. 三轮做完后，哪些建议已经被验证过

| 现有干预 | 可用结果 | 对建议的影响 |
|---|---|---|
| R1 冻结分支 | 同时关闭在线更新及关联 PCF 协调，12/12 比 ON 差 | 不能当成单纯 W 冻结实验；也不支持直接去掉适应 |
| R2 整体 PCF-off | 12/12 比 ON 差；高频平均 +1.1342 mm，无风 +1.1524 mm | 不再把整体关闭 PCF 当首选 |
| R3 仅 Head 更新面使用 M=diag(1,1,0) | 高频筛查 4/6 胜 B，组差 −0.0623 mm；W15 仍 +0.3484 mm、1/3 胜 B | 有限改善，不能宣称高频全 28 场通过；改 Z 没解决无风门 |

固定 VAL12 中原 ON 高频 3/6 胜、均差 +0.0801 mm，比全量高频 5/28、+0.5255 mm 容易。因此 R3 的六个高频结果不能外推到全部 28 场。

R3 W15 相对 B 的 X 轴 RMSE 平均仍高约 1.097 mm，早段和晚段均差；相对原 ON 的 Q 只改善 0.00746 mm。此前“26 输场 Z 都差”是正确的子集描述，不能推出无风继续优先动 Z。这部分仍是不同闭环轨迹的误差分解，不能把 X 直接归因给某一组件。

来源：[R3 实际评分](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/paper14_v2_round3_xy_pcf_screen/reports/round3_xy_screen_results.csv)、[本次筛查重算](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/reports/hf_w15_reinvestigation_20261022/screen_comparison.csv)、[既有结束审计](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/reports/paper14_v2/FINAL_CLOSEOUT_20261022.md)。

## 3. 目标与 PCF：实际核验了什么

源码对应：

- [position_bs_step](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/matlab/core/position_bs_step.m:17)：e=r−p，s=de+k1 e，a0=rAcc+k1 de+e+k2 s；a_req=a0−u。
- [标签导出](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/matlab/data/export_position_events_dl1018.m:40)：Y=a_actual−(a0−u)，包含气动、实现/分配、姿态跟踪和映射误差。
- [PCF helper](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/paper14_v2_round3_xy_pcf_screen/runtime/position_filter_realization_pcf_step_v3_5.m:13)：r_f=a_req−a_f，eta_dot=−K2 eta+r_f；a_f 是命令推力与滤波姿态形成的加速度，尚不是实际 Plant 加速度。
- [Head 更新](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/paper14_v2_round3_xy_pcf_screen/runtime/position_only_search_head_step.m:14)：先输出，再以 beta、phi、sEff 做跟踪误差驱动更新，另有泄漏/投影。

在理想连续坐标、常数对角 mask M 与标量/对角 K2 可交换的条件下：
~~~
sdot   = -e - K2*s + u - Y
sc     = s - M*eta
scdot  = -e - K2*sc + u - (Y + M*r_f)
~~~
原 all-axis PCF 为 M=I；R3 为 M=diag(1,1,0)，对应 XY 的 Y+r_f、Z 的 Y。这个推导不是完整离散闭环稳定性证明，未消除事件保持、surface 裁剪、beta、投影、采样与内环实现误差。

本次以冻结索引中 72 份原始 MAT、每场 1,968 有效事件重算实际加速度，不使用速度差分。加速度按 [vehicle_derivative](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/matlab/core/vehicle_derivative.m:35) 的实际欧拉姿态、已实现推力、气动力、质量与重力计算；[simulation_parameters](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/matlab/core/simulation_parameters.m:16) 的质量取 cfg.plant.mass。Y+r_f=a_actual−a_f、请求与应用补偿、当前权重输出的最大闭合误差不超过 8.9e-16 m/s²；beta ramp 和滤波 clip replay 误差为零。全部原始文件读前读后 SHA 与 stat 不变。恒等式检查本身不是独立 ground-truth 或因果验证。

以下为 5–20 s、逐场 RMSE 再等权平均；W0、在线 Wbefore、同事件 Wafter 都用同一个记录状态、phi、beta 评估，单位 m/s²：

| 组/目标/轴 | 目标 RMS（零预测误差） | W0 误差 | Wbefore 误差 | Wafter 同状态误差 |
|---|---:|---:|---:|---:|
| 高频 Y，X | .6701 | .3812 | .3071 | .3061 |
| 高频 Y，Y | .6947 | .4139 | .3188 | .3177 |
| 高频 Y+r_f，X | .4243 | .2805 | .1878 | .1871 |
| 高频 Y+r_f，Y | .4245 | .3265 | .2156 | .2148 |
| W15 Y，X | .1431 | .1676 | .0509 | .0499 |
| W15 Y，Y | .1420 | .1892 | .0477 | .0469 |
| W15 Y+r_f，X | .1366 | .1678 | .0590 | .0576 |
| W15 Y+r_f，Y | .1237 | .1829 | .0660 | .0644 |

所有 18 个“风组×轴×目标”晚段聚合，单次更新后的 RMSE 都较低。但高频约 33%–43% 的单事件平方误差仍可能增加；不能把平均改善说成每一步均改善。跟踪更新本来就不是直接最小化标签 MSE，以上也不要求两种学习对象数学上必须相同。

新增低频核验采用 100 Hz 有限窗 DFT 的 0–1 Hz 能量，含 DC，只作描述性诊断。高频协调目标 Z 的 W0/在线低频误差 RMS 为 .12283/.01162，逐场时间平均误差的绝对值再平均为 .11844/.00361；W15 协调目标 X 的低频误差为 .16678/.05568，Y 为 .18215/.06371。因此不能说在线相对先验普遍增加低频或 Z 偏差。它是否相对 B 留下更多低频位置代价仍未被该同状态对比识别。有限窗泄漏存在；这里没有测得完整闭环相位。

**判断：目标坐标差异成立且量级不小；“它导致输 B”仍待干预。** 现有证据不支持直接清零 W0、冻结 Z 或把 Y 全量替换后宣称修复。

来源：[脚本](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/reports/hf_w15_reinvestigation_20261022/audit_target_contract.py)、[逐场表](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/reports/hf_w15_reinvestigation_20261022/target_contract_by_scene.csv)、[组表](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/reports/hf_w15_reinvestigation_20261022/target_contract_groups.csv)、[身份和闭合检查](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/reports/hf_w15_reinvestigation_20261022/target_contract_metadata.json)。

## 4. 无风先验：进一步追到原训练数据

为区分“仅候选状态分布偏移”与“原学习目标上也存在短板”，本次对原固定训练索引中的 W15 做了 CPU 固定模型推理：TRAIN96（3任务×16构型×B/POS_OFF 两角色）与原训练 VAL6。没有优化器、拟合或新采集；它们不是新的独立 TEST。

独立 NumPy 实现精确 32 事件窗口、每次零状态的 DSSM，与原记录 1,968 个 phi 的最大差 2.22e-16。模型/normalizer 来自已绑定的 corrected 原始运行；所有缓存 SHA 与训练索引匹配，读取后不变。比较 beta 后、每轴 ±3 的实际先验输出与缓存物理 Y；另存未裁剪预测对训练 clipped label 的误差。

| 原 TRAIN W15 晚段 | 目标 RMS | W0 预测 RMSE | W0 差于零预测的航次 |
|---|---:|---:|---:|
| X | .13032 | .16851 | 67/96 |
| Y | .14507 | .18268 | 72/96 |
| Z | .00893 | .01225 | 82/96 |

B 与 POS_OFF 两角色分别聚合后，三个轴均出现 W0 误差高于零预测误差。原训练 VAL6 的 X/Y/Z 分别为 3/6、4/6、5/6 条差于零；并非所有任务/轴都退化。

这表明无风弱点在预训练先验的原数据目标上已有迹象，不能只归因于未见过的闭环状态。它也不证明训练代码错了：全局多风、多任务的加权目标可能容许小残差工况欠拟合；标签又包含随控制策略改变的内环实现误差。当前统计是无权重 episode 宏平均，不能冒充训练器的加权 loss。仍需区分目标选择、样本权重/归一化、特征表示与角色分布的影响。

来源：[固定模型审计](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/reports/hf_w15_reinvestigation_20261022/audit_w15_prior_source.py)、[逐航次](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/reports/hf_w15_reinvestigation_20261022/w15_source_prior_by_episode.csv)、[按任务角色分组](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/reports/hf_w15_reinvestigation_20261022/w15_source_prior_groups.csv)、[身份与边界](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/reports/hf_w15_reinvestigation_20261022/w15_source_prior_metadata.json)。

W15 表示环境风速为零，机体运动仍有相对气流。既有 72 场分解中 W15 气动力 RMS 宏均值约 .00209，dAtt 约 .10714 m/s²；气动力小但并非必须为零，姿态实现项也没有消失。各项相关，不能把 RMS 直接当可相加的方差贡献。依据：[相对气流实现](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/matlab/core/morphology_aware_wind_load.m)、[原全场分解](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/reports/paper14_v2/phase1/mechanism_components_by_scene.csv)。

## 5. 高频：区分采样、滤波动态和裁剪

72 场实际有效 command-filter 加速度限值都是 [Inf,Inf,6] rad/s²，不是默认文件中的 [8,8,6]。本次逐时刻核验 request 与 applied，全部场、全部轴的裁剪比例均为 0；yaw 请求为 0。不能用默认值推断实际 roll/pitch 被限幅。[有效配置](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/matlab/runtime/prepare_effective_config_dl1018.m:31)、[逐场核验](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/reports/hf_w15_reinvestigation_20261022/filter_limits_by_scene.csv)。

roll/pitch 参考滤波的 wn=18 rad/s、阻尼1。其理想连续模型在 2.2/3.2/3.7/4.8 Hz 的幅值为 .629/.445/.375/.263，相位约 −75/−96/−105/−118°。这是孤立参考滤波环节的解析值，不是 NN→实际加速度的闭环实测相位；B 共享该环节。实际气动力含非线性与谐波，不等于双正弦环境风速本身。因此它支持检查实现时序，不能单独证明滤波导致 NN 输 B。

100 Hz 更新并不代表 50 Hz 补偿带宽；32 事件窗口也不代表稳态固定延迟 .32 s。DSSM 包含不同时间常数、非线性投影，完整有效相位须定义具体输入/输出并核验。

## 6. 论文与作者代码：可用的启发及不可照搬之处

只采用原论文、作者/机构仓库；没有运行第三方代码或移植实现。

| 方法 | 核验到的要点 | 对 DL1018 的价值和边界 |
|---|---|---|
| Neural-Fly，Science Robotics 2022 | 在线 law 联合 tracking、noisy force prediction error 和正则；不只是换编码器 | 可借鉴复合适应。必须有因果残差测量并重新推导 PCF/单位/离散误差。公开仓库主要是离线学习及数据工具，不能称完整飞行在线控制器 |
| DATT，CoRL 2023 | 参考预览+学习策略+L1 速度预测器；官方代码 estimator 默认 dt=.02、alpha=.99 | 完整策略改变范围超出位置残差。默认单独低通在 2.2–4.8 Hz 幅值约 .036–.017，不能拿其论文证明直接拷贝参数就能抗本项目高频 |
| Cascaded INDI，CEP 2018 | 加速度、控制与执行器状态要匹配滤波延迟 | 强支持核对残差实现时序；更换姿态内环超出合同。机构 indiFlight 是后续研究代码，不是该论文原 Paparazzi 完整复刻 |
| Richards 等，RSS 2021 | 用闭环跟踪模拟作为元学习目标，官方代码在线只适应线性层 | 支持“预测拟合不是最终目标”；其平面全驱动仿真及动力学假设不覆盖当前欠驱动、滤波和执行器链 |
| SSML-AC，2024 v1 / ICRA 2025 | 全层复合适应、带噪残差观测，有 Crazyflie 飞测；论文仍简化欠驱动性 | 不能直接套稳定性保证或决定全层更新。截至本次官方仓库只有 README/LICENSE，未找到可审核的算法源文件 |

原始来源：[Neural-Fly 论文](https://arxiv.org/html/2205.06908v2)、[作者仓库](https://github.com/aerorobotics/neural-fly)；[DATT 论文](https://arxiv.org/html/2310.09053v2)、[adaptation 源码](https://github.com/KevinHuang8/DATT/blob/main/learning/adaptation_module.py)；[INDI 论文](https://arxiv.org/pdf/1701.07254)、[机构同步滤波源码](https://github.com/tudelft/indiflight/blob/indi/src/main/flight/indi_init.c)；[RSS 正式页](https://www.roboticsproceedings.org/rss17/p056.html)、[作者代码](https://github.com/StanfordASL/Adaptive-Control-Oriented-Meta-Learning)；[SSML-AC 原论文](https://arxiv.org/html/2410.07575v1)、[官方仓库](https://github.com/LeCAR-Lab/SSML-AC)。文件 blob 身份见本目录 external_sources.json 和 additional_reference_sources.json。

这些工作支持改进“先验目标—残差观测—在线更新—实际跟踪”的关系，不能替当前数据证明收益，也不构成本项目现成创新。

## 7. 对用户提供建议的取舍

参考文稿审查的是 main/1f7b31d 且未读本地原始 MAT，时间与证据范围早于本次 R1–R3 和新增诊断。将其作为外部评审线索，不作为运行命令。

- **接受**：保留已取得的总体收益；不扩大网络；不强迫无风输出零；检查同状态目标、低频误差与下游时序；复合适应作为后续研究方向。
- **已执行并推进**：同状态 W0/在线权重对 Y 与 Y+r_f、低频/均值的全部 72 场核验，以及原 TRAIN/VAL 无风先验复核。
- **更新**：“先验 Z 好、在线改坏”目前没有得到本次数据支持；无风优先 Z 的说法被 R3 水平 X 残差削弱；不能重复此前已失败的整体 PCF-off。
- **暂不接受为执行方案**：直接改标签重训、临时另选六场或先冻结某轴。这会绕过已有固定 VAL12、三轮上限和因果/数据身份门。下周期应保持已冻结开发筛查，不能把挑选输场叫独立测试。
- **公式可作为局部解释**：k1=1、k2=4 的理想误差通道 e''+5e'+5e=u−Y 以及单频相位抵消公式成立于其简化假设；不是实际完整闭环稳定性或根因证明。

## 8. 审核决定与唯一优先动作

**优先做“PCF 匹配目标的 TRAIN 数据可重建性与先验诊断”，保留编码器和全部控制配置。** 这是待检验机制的诊断，不是新的性能承诺。

已完成的字段检查发现：1,536 份 TRAIN NPZ 全部 SHA 匹配且使用同一种 schema，均有事件 eta，但没有直接 a_req/a_f/r_f 字段。公共事件导出器也不输出它们。100 Hz eta 仅约束区间滤波积分，不能凭差分精确恢复 1 kHz 点值 r_f；缺失字段不能当成零，也不能用 DEV72 填充训练数据。[缓存字段审计](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/reports/hf_w15_reinvestigation_20261022/training_cache_field_availability.json)。进一步将训练索引与 G3 来源索引按 run_id 一对一联结，raw/event/cache SHA 全匹配：1,536 份 TRAIN raw、run_start、event H5 路径目前均存在，raw 共约 58.60 GiB。本次这一步只查存在性/大小，没有打开这批 TRAIN raw，尚未验证其字段完整性与可重建时序。[可用性证据](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/reports/hf_w15_reinvestigation_20261022/training_raw_availability.json)。因此可以先从已有原始数据补契约，无须先采新 Teacher。

后续顺序：
1. 复用本次可用性索引，检查允许 TRAIN raw/运行日志的实际字段与时标；能恢复时按同时间戳重建 Y+M r_f，输出源身份和闭合检查。以冻结 M 为单位，不同时换 mask，不重复原数据采集。
2. 在原 TRAIN 和训练 VAL 上比较原先验的 Y、匹配目标及零基准，按任务/角色/风组/轴报告，不优化参数。若证据不支持目标问题，放弃重标优先假设。
3. 只有另行立项、身份与上述诊断通过后，才冻结一个单因素任务书：保持 DSSM 编码器/输入/normalizer，考察一种目标变换对读出层的影响，与同设置原目标训练对照，固定 seed 2026102001、每配置≤60k steps、不搜 seed。该训练对照需要明确的新预算，不能默认复用旧 checkpoint 作为“同训练对照”。
4. 若匹配目标仍不足，再考虑上一完整区间速度增量构成的积分残差观测与 tracking 项联合更新。它只在下一事件可用，须处理测量、滤波、噪声、保持和一拍延迟；不能把 Plant 真值塞入部署。它才是可能的方法研究，仍需单因素对照与完整理论。

高频希望从目标与实现时序一致性获益；无风希望减少原先验对小残差的偏差，并保留适应带来的纠正。**没有证据保证一个改动同时战胜所有高频与无风。** 如果诊断/筛查否定假设，停止该方向，不反复调阈值凑胜场。

严格新配对还须解决既有 B 的逐运行源码身份缺口，或在新预算中生成同一冻结 runtime 的 B；历史 B 分数仍可作描述对照，方程重放不能补回原执行环境。旧 G06 STOP、历史参考保护和 TEST48 封存保持原结论。

## 9. 可复现范围与执行记录

所有输出在本目录。只运行 PowerShell 7 中的离线 Python，无 MATLAB、GPU、Plant 或 optimizer。target 审计增加低频列后重读同一冻结 72 场；前后 SHA/stat 均一致。缓存字段检查首次因 whitelist 只允许归档、未覆盖索引明确引用的当前项目缓存而在路径断言中停止；加入当前项目这个已授权来源后通过。该失败发生在路径检查，是离线工具问题，不是实验航次。

~~~powershell
python -B reports/hf_w15_reinvestigation_20261022/audit_target_contract.py
python -B reports/hf_w15_reinvestigation_20261022/audit_training_cache_fields.py
python -B reports/hf_w15_reinvestigation_20261022/audit_training_raw_availability.py
python -B reports/hf_w15_reinvestigation_20261022/audit_w15_prior_source.py
python -B reports/hf_w15_reinvestigation_20261022/summarize_existing.py
~~~

两名既有执行者按 Luna xhigh 约束请求只读审核；协作接口不提供速度控制，不能独立证明实际模型/正常速度档位。结果表由独立执行者重算，主模型检查原始公式和适用边界。详见 REVIEW_ZH.md 与 AUDIT_STATE.json。本次没有提交/推送，MAT、模型、缓存原位保留。

