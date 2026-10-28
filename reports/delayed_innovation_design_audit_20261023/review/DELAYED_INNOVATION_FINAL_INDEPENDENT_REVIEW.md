# 延迟创新离线构造：最终独立审核

日期：2026-10-23。结论：**离线构造与数值核验通过；论文资格仍为 `NOT_QUALIFIED`。**这份审核只覆盖冻结 C1 ON1 历史记录上的延迟损失诊断，不代表新学习律、反事实轨迹或闭环收益。

## 审核范围与来源

我静态核了 C1 锁定 runtime、position Head、feature forward、PCF exact-step 与 command-filter 调用时序，并审核最终构造脚本和派生表。A 的脚本逐条读取 12 个已冻结 ON1 raw 并记录读取前后 SHA/stat；父审另用独立 raw 复核器完成 12 条、36 个实际方向有限差分及 180 项指标重算。为避免重复大负载，我没有再打开原始 MAT；我独立解析了 252 行 CSV，检查唯一键/分层计数，并从 XYZ 行重算 ALL 轴 RMSE。

本次执行脚本 SHA-256：`bb6a90e4489825709995900bdb9fe69896c0a902b1239bb515859d131b2259ad`。产物为 [DELAYED_INNOVATION_SUMMARY.json](../construction/DELAYED_INNOVATION_SUMMARY.json) SHA-256 `4d542a1d80d2633e9bbcbd4f6e86dbc4786989a80323cf5785a171ff36698f4f`、[DELAYED_INNOVATION_GROUPS.csv](../construction/DELAYED_INNOVATION_GROUPS.csv) SHA-256 `14ee3a792c5138787450846f24a15fa796281099b055026dcfc132c4b41ad460`，以及 [DEVELOPMENT_FAILURES.json](../construction/DEVELOPMENT_FAILURES.json) SHA-256 `c17823707aff039104440b10545f0353ad090d1fcea4a652b5733b9b6c8b811a`。父审独立复核状态为 `PASS_PARENT_INDEPENDENT_RAW_RECONSTRUCTION`，复核器 SHA-256 `8eda0c89cf28385e776d24c0b5ed97af55b4d3bb05d2f970e3768d07f67d53b1`。

## 物理与时间契约

冻结 runtime 每个 100 Hz Head event 先读取 `W_before` 并输出 `β clip(φᵀW_before, ±3)`，再更新权重；权重变化包含 `γ=12 s⁻²` 跟踪项、`0.002` 泄漏和逐元素 `±60` 投影。输出在同一 1 ms 控制/Plant tick 转为位置补偿力。feature 为 `[h;1]/sqrt(1+||h||²)`，故 `||φ||=1`。PCF 每个 1 ms tick 用当前 held input 做 exact exponential η 步进；Head event 使用该步更新前的滤波姿态与 η，未发现额外的一拍延迟。

Plant 以 1 ms held input 做 RK4 区间积分。因此 `d̂=(v[k]-v[j])/0.01−mean(a_f[j:k])` 是过去 10 ms 的 `a_actual−a_f = Y+r_f` 区间平均近似，不是瞬时加速度，也不是纯 `Y`。样本按事件索引 `j=k−10` 配对，`k=330…19990`，每条 1,967 对、总计 23,604 对；未为首事件伪造历史样本。该标签只用了当前/过去速度及内部滤波加速度；实机测量噪声未知，速度差分会以 `1/T=100 s⁻¹` 放大端点误差。

延迟 replay 输出为 `u_rep=β_j clip(φ_jᵀW_before[k], ±3)`，与历史区间标签比较。解析梯度为 `G=φ_j[β_j(m⊙e)]ᵀ`，其中 `m=1{|φ_jᵀW_before[k]|<3}`。实现中的广播维度、历史/当前权重索引与 clip active set 均已核；A 的 37 个有限差分点（36 个实际点加一个合成点）全部通过，最大绝对误差 `8.27e−11`、最大相对误差 `1.10e−7`。父审对 36 个实际点复算，并对每场 15 个指标、共 180 项作独立对照；最大指标差 `3.19e−14`。

脚本记录的 12 条 raw 前后 SHA/stat 全部一致。`φ` 范数最大误差 `2.22e−16`；历史未裁剪输出由 `W_before[j]ᵀφ_j` 重建的最大误差 `4.44e−16 m/s²`；历史 β/clip 输出、held interval output、`W_after[j]` 到 `W_before[k]`、原更新式逐项闭合误差均为 0。父审独立复核确认标签与指标结果。

CSV 恰有 21 个 scope × 3 个阶段 × 4 个轴字段的 252 个唯一行；每阶段 84 行。早段/晚段分别 5,604/18,000 对，合计 23,604。独立从 X/Y/Z RMSE 重算 ALL 轴 RMSE，最大差 `5.55e−17 m/s²`。

## 数值结果及解释

下表为 ALL 轴、均按事件样本合并的 m/s² RMSE。这里的“历史”与“当前权重 replay”都在同一冻结轨迹上评价，后者不是重新 rollout。

| 范围 | 场数 | 历史误差 RMSE | 当前权重 replay RMSE | 平均梯度范数 | 梯度下降方向与实际总 ΔW 平均 cos | 正向对齐比例 |
|---|---:|---:|---:|---:|---:|---:|
| ALL12 | 12 | 0.108009 | 0.107432 | 0.137656 | 0.6081 | 85.49% |
| HF（W09–W14） | 6 | 0.140915 | 0.140461 | 0.196683 | 0.3970 | 75.42% |
| W15 | 3 | 0.050302 | 0.049157 | 0.067470 | 0.8687 | 97.61% |

replay 误差分别小约 `0.000577`、`0.000454`、`0.001145 m/s²`。这些差值是冻结轨迹上的回放差异，不是新更新后的预测误差或闭环改善。`ΔW` 是实录 `W_after−W_before`，含跟踪、泄漏、投影；cosine/正向比例仅描述单个历史点的局部几何关系，不能称为对实际更新的因果作用。范围和早/晚分层都已保留在 CSV。

## 数学边界与文献

对固定旧特征、固定 β/标签、clip 活动集不变且不含其它更新/投影的单次纯梯度步 `W⁺=W−ρG`，active 轴满足 `e⁺=(1−ρβ²)e`；`0<ρβ²<2` 时该固定样本损失下降。此为局部代数界，不适用于原跟踪+泄漏+投影联合更新或闭环系统。`ρ` 应是无量纲逐事件步长，不能直接复用单位为 `s⁻²` 的 tracking γ。β 小时归一化噪声会被放大；目标超过 `3β` 输出幅值时存在不可消除的饱和残差。预测/跟踪联用仍缺少对内生 PCF 状态、Plant/姿态/执行器耦合、离散采样与积分误差、测量噪声、饱和投影及激励条件的完整证明。

相关先例不支持把“command filter + NN prediction/composite update”本身当创新：Pan et al. 2017 出版社摘要已说明 command-filtered NN composite tracking/prediction errors 与 IE；本次全文受 403 限制，结论仅据摘要。[Pan et al., 2017](https://www.sciencedirect.com/science/article/pii/S0893608017301867)。有限时间 command-filtered composite NN 工作也相关；其 NSF PDF 抓取超时，报告只依摘要/元数据。[Sun et al., 2020](https://par.nsf.gov/servlets/purl/10338331)。积分复合学习使用积分 regressor/control stack，不等于这里的速度有限差分加单一旧 `φ_j`。[Pan et al., 2016](https://ietresearch.onlinelibrary.wiley.com/doi/10.1049/iet-cta.2016.0032)；[Parikh et al., 2019](https://ncr.mae.ufl.edu/papers/IJACSP192.pdf)。Neural-Fly 与 control-oriented meta-learning 也分别是已有的在线残差控制与闭环控制目标优化路线，不可把其保证移植到本构造。[Neural-Fly paper](https://arxiv.org/abs/2205.06908), [作者代码](https://github.com/aerorobotics/neural-fly)；2204.06716 的作者仓库是 [spenrich/Control-Oriented-Meta-Learning](https://github.com/spenrich/Control-Oriented-Meta-Learning)，而 [StanfordASL 仓库](https://github.com/StanfordASL/Adaptive-Control-Oriented-Meta-Learning) 的 README 对应 2021 RSS / arXiv:2103.04490，未混配代码与论文。

文献比较和理论均不构成新颖性或闭环资格。当前论文状态应保持 `NOT_QUALIFIED`；本审核没有授权训练、增益选择、Plant 试验或 TEST。

## 保留的离线开发失败

失败账本含 5 条，均保留且无分析产物覆盖：一次因源 SHA 常量笔误在 raw 读取前失败；两次单记录 smoke 暴露非事件字段按设计为 NaN、被过严有限性门误拒；一次解析梯度数组广播维度错误；一次 smoke harness 使用旧报告年份路径而未导入脚本/读取 raw。记录显示没有 Plant、MATLAB、optimizer、GPU、TEST 或训练；已读 raw 的 smoke 记录 SHA/stat 未变化，输出写入数为 0。它们是离线开发失败，不能从账本中删去或改计为科学结果。
