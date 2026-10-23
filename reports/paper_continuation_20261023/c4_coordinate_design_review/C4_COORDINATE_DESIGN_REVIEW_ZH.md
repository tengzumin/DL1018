# C4 坐标假设：独立设计复核

**结论：有条件通过设计方向；先修正文案并在任务书冻结下述实现契约，再进入新入口审查。** 方程符号正确，C4不是旧R2的重复试验；它识别的是“跟踪面与预测标签同步切换”的整体坐标干预，不能拆称 eta 单因素或预测标签单因素。

C3理想 matched-surface 方程下，取标量 (m\in\{0,1\})（对应 (M=mI)），(s_m=s-m\eta)、(d_m=Y+mr_f=\dot v-[a_{req}-mr_f])。利用 (\dot\eta=-K_2\eta+r_f)，可得 (\dot e=s_m+m\eta-K_1e) 与 (\dot s_m=-e-K_2s_m+u-d_m)；(m=1) 为 C3，(m=0) 得 (s) 和 (Y=\dot v-a_{req})。**草案公式符号正确。** 这是连续理想匹配关系，不是 RK4 Plant 与 held-input PCF 的离散闭环证明。

实现上建议把同一个 (m) 显式用于两处：事件跟踪量 `clip(s-m*eta_before, limits)`；以及10 ms因果标签

\[
\bar d_m(j,k)=\frac{v_k-v_j-\int_{[j,k)}(a_{req}-m r_f)\,dt}{0.01}.
\]

每步积分只累计已发生的转移行 `[j,k)`；`a_req` 是含当步已应用 Head 补偿的请求加速度，不是裁剪后/实际实现加速度。(m=1) 时被积量为 (a_f)，(m=0) 时为 (a_{req})。在事件 (k) 先用当前 (W_k) 输出，再按原 beta、clip、联合梯度和投影得到 (W_{k+1})；不可把当前转移的请求量或未来速度放入标签。复用 C3 的零基事件映射：首个 ready (n=320) 无历史样本，之后必须有 (j=n-10\ge320)，不得合成 (j=310)。

源码上的最小落点是 C3 `run_dl1018_closed_loop.m` 的 1993–2015 行（跟踪量及延迟标签）、2232–2237 行（请求/PCF参考量与积分）和 2022 行之后已有的输出/更新路径：保留 `pcfCoordinationEnabled=true` 以生成同一请求、(a_f,r_f,\eta) 诊断；不要直接把该开关关掉。当前 delayed-prediction runtime contract 在 695–705 行明确要求 full-PCF，2228行以下只有该开关为真才调用 PCF helper 并记录 (a_{req},a_f,r_f,\eta)，且仅累计 (a_f)；`positionInfo.commanded_acceleration` 已在此前 2127 行计算。因此 C4 应用该同一请求另累计 (a_{req}-m r_f)，不要靠关闭开关来切换标签。因此 C4应新增二值坐标因子并并行累计 (a_{req}-m r_f)，而非冒充现有 PCF-off 分支。预测 helper 与 W0、特征、更新系数、输出时钟及投影保持不变。

它不是无信息重跑 R2：旧R2在**没有 C3 延迟预测项**时整组关闭 PCF，12场 Q 对 PCF-on 为 0/12 胜，均值差 `OFF−ON=+1.202 mm`；HF 为 `+1.134 mm`，W15 为 `+1.152 mm`。但旧 OFF 的 HF Z 有4/6场、W15 Z有3/3场胜，说明轴间权衡明显。C4保留 C3 复合预测更新，改变其输入面与标签坐标，回答的是不同问题。旧R2是对“PCF一关便更好”的强反证，不是对 C4 的直接否决。

补充的冻结轨迹分解提高了该假设的可区分性：72场 sampled-error accounting 的 T2-HF9 Z 组，9场等权平均的逐场位置 RMSE 为 3.704 mm；固定 forcing 下逐场响应 RMS 的等权均值为 eta 2.738 mm、残差误差 1.646 mm、采样余项 0.016 mm；eta×残差交叉项的等权均值为 +2.666e-6 m²。它说明 eta 通道在该组不是可忽略项，但这些是 C3 同一轨迹的线性 forcing 分解，不能将 RMS 相加，也不代表移除 eta 后其他闭环 forcing 保持不变。预期方向可作为固定12场的 stop/go 门，不能写成有把握的性能预测。C3固定host的同状态复算确实报告局部残差拟合改善，但首场拟合改善而位置误差变差；而“观察到的 Q 仍受 eta 驱动”尚未做因果分解。建议把草案首段改为：“C3固定host同状态复算显示延迟目标局部拟合降低；理想误差方程仍含 eta，但其对 Q 的因果贡献未识别。C4检验同步切换坐标能否改善固定场景闭环表现。”两场 FIG8 的 Z 与 Q 双降等门可保留为严格的预登记筛查，不得据12场推广、调整阈值或解释成稳定性结论。

复核依据：草案 SHA `C011989DC23A2D1DB5448BF601D32C9C994A87CB7EE6260092F2C0E227AE90EE`；实现机制审查 SHA `620249E63FD43E65BFB0679C75374302CD9536F4762416096C48AE5DF315B8C6`；C3结果摘要 SHA `9684FA2F968ECF5332F41843CB4AD8A1E21434A8110756F2CCC461B2201513E4`；R2汇总 SHA `47E047E03FF6BD1B06CA06925740CB0BF95A4108D5CE04AB630297B38E108BA2`；C3 runtime SHA `E5F1E30C433EE3F8206B36446CDE71776589C161FE2A3EC60FBAF070585EB07F`；prediction helper SHA `48FEEBF934B8EB90B4424F2286AA857C48213D229714F30AF99AACF53329549D`。仅静态审核，未运行 MATLAB/Plant。