# PCF 假设核验（本轮独立复建）

## 推导：先区分两种误差面

真实位置外环写为 `e = p_ref - p`、`s = v_ref + K1 e - v`，`a_nom = alpha_dot + e + K2 s`。位置网络施加的补偿加速度记为 `a_comp`，故外环送往姿态/推力转换的请求为 `a_req = a_nom - a_comp`。按 Plant 平动方程，`a_actual = a_req + d_train`，其中 `d_train = a_actual - a_req` 正是事件导出监督目标所用的跟踪残差。

PCF 用 `r_f = a_req - a_f`，其中 `a_f` 是以滤波后姿态与名义推力合成的可实现参考加速度；其 1 kHz 精确零阶保持更新是 `xi[k+1] = exp(-K2*dt) xi[k] + (1-exp(-K2*dt))/K2 * r_f[k]`。控制器只在100 Hz事件上使用 `s_c = s - xi`。代入可得：

`dot(s_c) = -e - K2*s_c + a_comp - (d_train + r_f)`。

因此，在协调坐标下，未建模项对应 `d_coord = d_train + r_f`；原始 `d_train` 仍是未加 PCF 的跟踪残差。用 `d_train` 初始化离线 Head 是可解释的初始化选择，而不是自动的标签错误：启用协调状态后，在线 Head 更新看到 `s_c`，其更新和闭环误差会进一步改变参数与作用对象。离线回归目标与在线协调目标不完全相同，这是设计取舍，是否重要须看量级和闭环，不能只凭代数差异认定重复补偿。

这里的代数式按实际 `position_bs_step`、实际 `a_req`、PCF 实现及输出事件更新顺序推导。离散训练/事件值不能把连续式当精确事件导数；本轮辅助态使用全体 1 kHz 样本按运行器的 exact-ZOH 公式重放，再对齐100 Hz事件。B/POS_OFF原记录中的PCF关闭/零值仅作为原日志保留；`xi_virtual` 是在其已记录轨迹上以同一定义重建的反事实状态，不代表它们实际运行了PCF闭环。

## 独立复建闭合

- 六场桥接、四角色（B、POS_OFF、Initial、Final），读取24条20秒raw日志；新建 `PCF_RECONSTRUCTION.csv`，包含事件级 `a_req/a_f/r_f/d_train/d_coord/xi/s/s_c`。按每条轨迹完整1 kHz更新辅助态后再抽取事件。
- 实际加速度由原始状态、姿态、实现总推力、风力、合同质量/重力按Plant平动方程独立计算；与现有 B/POS_OFF/Initial H5 未裁剪目标的最大差见 closure JSON。活动PCF日志上的 `a_req/a_f/r_f/xi` 重放闭合最大误差也列于同一文件。
- 1.8–10 s 实际复建的 `r_f` 量级跨角色/轴的分位范围为 0.001779 到 0.5467 m/s²；完整分场、分轴、分时段 RMS/偏置和与 `d_train` 相关性见 `PCF_RECONSTRUCTION_SUMMARY.csv`。`r_f` 只有在具体轴/时段与残差方向、幅度同时足够时才可能解释已见差距；相关性不是干预因果证据。
- Initial 与 Final 原冻结模型在每一条相同记录轨迹上分别计算裁剪 `d_train` 和 `d_coord` 目标的同口径物理 RMSE，见 `PCF_SAME_MODEL_TWO_OBJECTIVES.csv`。这是记录轨迹离线目标，不是闭环复飞。
- 已见闭环桥接仍以既有同场记录为准：宏Q与1.8–10 s分段指标保存在 `derived/BRIDGE6_EXISTING_CLOSED_LOOP.csv`；新残差回归不能改写这些实飞结果。

## 实测结果补充

1.8–5 s / 5–10 s逐场逐轴平均RMS：Initial轨迹`r_f`为0.171/0.221 m/s²、`d_train`为0.285/0.402；Final为0.201/0.302、`d_train`为0.313/0.469；B为0.134/0.156、`d_train`为0.254/0.351；POS_OFF为0.074/0.093、`d_train`为0.214/0.311。`r_f`与`d_train`的池化相关约−0.69至−0.93；逐场、逐轴、逐时段结果见`PCF_RECONSTRUCTION_SUMMARY.csv`。

物理重建与现有 B/POS_OFF/Initial H5未裁剪目标的最大差为`1.83e-15 m/s²`；活动PCF日志上的`a_f/r_f`重放最大差为`3.55e-15 m/s²`，统一虚拟xi与实际记录xi的1 kHz最大差为`5.55e-17 m`。合同质量0.695 kg、重力9.8 m/s²、K2=[4,4,4] s⁻¹；详见`derived/PCF_RECONSTRUCTION_CLOSURE.json`。

在同一24条轨迹上，Initial与Final模型平均裁剪物理RMSE分别从`d_train`的0.3606/0.3423 m/s²变为`d_coord`的0.2681/0.2740 m/s²。这里是离线重评分，不是按新目标训练，也不是闭环复飞。原同场闭环宏Q为B 0.020357 m、Initial 0.038299 m、Final 0.029577 m：Final比Initial低0.008722 m，但仍比B高0.009220 m。加速度残差差不能直接换算成位置Q因果效应。

## 诊断字段纠正

本轮只读原日志字段 `stage1_position_pcf_event_eta_before_mps`。旧 D2 导出脚本候选名 `stage1_position_event_eta_before_mps` 与实际名不一致；旧 C2 序列缓存读取的是正确正式字段 `stage1_position_pcf_eta_before_mps`，因此没有证据把 C2 监督数据标为受该列名影响。本报告没有改旧脚本或旧报告，也没有把空诊断列升级成标签污染结论。

## 结论等级

**存在目标设计取舍，尚不能称原标签错误。** 物理日志独立复建支持上述连续坐标关系；PCF实现的 exact-ZOH 重放闭合到浮点误差，这不是先验采纳GPT的归因。实测 `r_f` 在1.8–10 s与 `d_train` 同量级的一部分且多为反向。Initial与Final在同一批24条记录轨迹上，平均裁剪物理RMSE分别从 `d_train` 目标的0.3606/0.3423 m/s²变为 `d_coord` 的0.2681/0.2740 m/s²。因此PCF—监督坐标差异可复现且量级值得重视；这证明它显著改变了离线目标分数，不证明它单独导致闭环输B。

原 `d_train` 仍准确表示无补偿的物理跟踪残差，线上又通过 `s_c` 更新Head。本轮没有对照训练 `d_coord` 并做同场闭环，所以不能将其判为错误标签。既有同场宏Q仍为B 0.020357 m、Initial 0.038299 m、Final 0.029577 m；Final虽比Initial改善0.008722 m，仍比B差0.009220 m。加速度残差差不能直接换算成位置Q因果效应。按任务书，本轮保留原标签和控制律。
