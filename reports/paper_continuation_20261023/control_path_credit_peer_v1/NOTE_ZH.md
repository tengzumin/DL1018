# C5 控制方向与 PCF 坐标：独立只读复核

**结论：未发现可由当前源码直接验证的 tracking 控制方向或符号错误。** C5 的负 tracking 更新与位置反步误差面符号一致；但它只支持一个有条件的自适应抵消解释，不能据此声称连续时间 Lyapunov 抵消在当前离散闭环逐步成立。PCF 坐标吸收的项仍会通过变换回物理误差时的 \(M r_f\) 进入位置误差 forcing。余下是模型适用性和有限采样假设，有限路径理论已显式保留这些差额。

## 符号与目标配对

源码定义 \(e_p=r-p\)、\(e_v=\dot r-v\)、\(s=e_v+K_1e_p\)，且 \(a_{\rm req}=a_{\rm nom}-u\)，其中 \(u\) 是 Head 输出的补偿加速度（实际传入力为 \(m u\)）。令连续物理残差 \(d_0=a_{\rm actual}-a_{\rm req}\)，在未饱和的理想运动学下：

\[
\dot e_p=s-K_1e_p,\qquad
\dot s=-e_p-K_2s+u-d_0.
\]

PCF 定义 \(r_f=a_{\rm req}-a_f\)，\(\dot\eta=-K_2\eta+r_f\)。固定对角掩码下令 \(s_c=s-M\eta\)，直接代入得

\[
\dot s_c=-e_p-K_2s_c+u-(d_0+Mr_f)
= -e_p-K_2s_c+u-d_M,\quad d_M:=d_0+Mr_f,
\]
\[
\dot e_p=s_c+M\eta-K_1e_p.
\]

所以更新方向没有反号：若理想局部模型满足 \(u=\beta W^\top\phi\)、\(d_M=\beta W_*^\top\phi\)，则 \(s_c^\top(u-d_M)\) 中的参数误差项由 \(\dot W=-\gamma\beta\phi s_c^\top\) 抵消。实际 C5 的更新方向正是 \(-h\gamma\beta\phi s_{\rm eff}^\top\)。不过以 \((e_p,s_c)\) 作储能时仍有 \(e_p^\top M\eta\) 交叉项；此外该抵消要求无面裁剪且目标有匹配的 \(\beta W_*^\top\phi\) 表示。C5 有 \(s_{\rm eff}=\operatorname{clip}(s_c)\)、输出裁剪、泄漏、预测梯度和盒投影，\(\beta<1\) 时目标 ramp 也不抵消，故不能把该理想等式当完整闭环证明。

代码对旧区间标签的坐标选择与 \(d_M\) 一致：掩码轴使用积分的 \(a_f\)，未掩码轴使用积分的 \(a_{\rm req}\)；由速度增量减该参考积分得到的是区间平均 \(d_M\)。C5 的 \(M=\operatorname{diag}(1,1,0)\)。这不是三轴瞬时标签：\(a_f,a_{\rm req}\) 在区间内变化，理论中的 \(\beta y-d_M\) 区间差项必须保留。

## PCF 抵消范围与离散相位

在补偿坐标 \(s_c\) 中，减去 \(M\eta\) 消去 \(\dot s\) 里显式的 \(M r_f\)；对应残差进入 \(d_M=d_0+Mr_f\)，供该坐标的学习目标使用。变回物理 \((e_p,s)\) 后，精确 sampled 引理仍有

\[
u-d_0=\epsilon_M+Mr_f,\qquad \epsilon_M=u-d_M.
\]

因此 \(Mr_f\) 没有从物理位置误差或 \(Q\) 中消失；未掩码轴不含该 PCF 项。指数 PCF 更新在每个 1 ms 输入保持区间内精确。增广协调坐标推导显式保留相对 Euler 形式的 \(\rho_\eta\)，但恢复到直接物理 \((e_p,\sigma)\) 递推时该项抵消；直接 \(A_2\) 响应只用 \(\rho_p,\rho_s\) 采样余项和完整 forcing \(\epsilon_M+Mr_f\)，不能再另加 \(\rho_\eta\) 通道，否则会重复计入。

实现时先以 \(W_q\) 产生本事件输出，再更新到 \(W_{q+1}\)；输出在 100 Hz 事件间保持。tracking 项用本事件的 \(\phi_q,s_{\rm eff,q}\)，但新权重到下一事件才作用；旧区间标签在下一事件才可用，并与上一事件的 \(\phi\) 配对。命令先经过力到姿态映射、受限姿态滤波，之后才计算当前 \(a_f,r_f\)。这使 \(d_M\) 对命令与闭环状态有依赖，且标签/输出有采样延迟；它不推翻负号方向，却排除了把连续时间同相抵消直接当成 sampled 闭环保证的做法。已读有限路径界按实际输出先于更新、延迟标签、\(\beta\)、裁剪、leak、投影及 \(Mr_f\) 分项，结论仅是已观测路径的条件界，不给未来稳定性保证。

## 有信息增量的路径诊断

此前的实际映射核验逐场检查了 \(u-d_0\) 的四项代数分解，但只记录重构最大残差；有限路径上界再用 Minkowski 合并各项，刻意丢掉正负交叉。单场 pilot 的 9 通道 Gram 先确认了物理响应重构可行。其后 v2 对固定 C5 的 72 条 DEV24+VAL48 路径完成分解；我独立从输出的逐场 Gram 矩阵重聚合全部 6 组、3 阶段、x/y/z/xyz，群组 Gram、pooled RMSE、scene-mean/rms 与 JSON 完全一致，逐场 Q 对 parent 的最大差为 \(9.2\times10^{-17}\,\mathrm m\)，active energy 恒等式残差为 \(1.1\times10^{-19}\,\mathrm m^2\)。ALL72 的 \(\epsilon_M\) 与 \(Mr_f\) 响应交叉项全程为 \(-9.25\times10^{-5}\,\mathrm m^2\)，早期为 \(+4.85\times10^{-5}\)，后期为 \(-1.395\times10^{-4}\)；这支持“交叉随阶段改变”的同轨迹描述，不是反事实因果或组件改善证据。先验目标平移诊断只冻结 \(W_0\)；C3 的 \(\eta\)/残差响应分解对应另一个闭环轨迹与不同分解。

可用已冻结 C5 DEV 轨迹作一次只读的线性路径账本，不必改变控制器或跑 Plant。按既有引理的 \(T_0=1\,\mathrm{s}\) 归一化，令 \(z_j=W_j^\top\phi_j\)、\(c_j=\operatorname{clip}(z_j)-z_j\)；\(y_j\) 是在事件 \(j+10\) 才得到的已完成区间标签，\(d_{M,n}=d_{0,n}+Mr_{f,n}\)，对旧区间 \(I_j\) 中每个 1 ms 采样 \(n\) 的精确物理 forcing 为

\[
\xi_n=u_j-d_{0,n}
=\underbrace{\beta_j(z_j-y_j)}_{f_{1,n}}
+\underbrace{(\beta_jy_j-d_{M,n})}_{f_{2,n}}
+\underbrace{\beta_jc_j}_{f_{3,n}}
+\underbrace{M r_{f,n}}_{f_{4,n}},\quad n\in I_j.
\]

注意 \(f_{1,n}+f_{2,n}=\beta_jz_j-d_{M,n}\)，标签 \(y_j\) 在这两项之和中严格消去。因此单独的 prediction 与 ramp/interval Gram 对标签分拆基准敏感；不能因其中一项的能量较大就认定该环节是性能瓶颈。固定本实验标签定义时可将它们作为可复现的描述子项，但更稳健的主报告层级是 \(\epsilon_M=f_1+f_2+f_3\)、\(Mr_f=f_4\) 及两响应的有符号交叉，再给出所有 active forcing 的联合响应和其对 \(Q^2\) 的闭合。更细的 \(f_1,f_2,f_3\) Gram 只能辅助解释，不能被写成因果归因。

将 \(f_1,\ldots,f_4\) 分别通过已核的物理 \((e,\sigma)\) 离散递推，并把初值、\(\rho_p,\rho_s\) 响应也保留，可得同一条已实现轨迹上的 \(E_i\)。报告每场/组/阶段的有符号 \(2\langle E_i,E_j\rangle\)，连同 \(\|E_i\|^2\)，并核对它们与实际 \(Q^2\) 的重构闭合。pilot 以全 Gram 矩阵求和，等价于对每对不同通道将上三角内积乘 2 后加一次。该 DEV72 诊断比仅有四项 forcing 最大残差或三角不等式上界多回答一个问题：哪些误差源在固定轨迹上同向累加、哪些互相抵消。v2 已将区间内 logged \(u_j\) 对重复后的 \(\beta_j\operatorname{clip}(z_j)\)、四项 forcing 对实际 \(u-d_0\)、物理状态递推及逐场 parent Q 的差都设为硬门；本次独立复算这些闭合均在浮点误差内。

该分解只是**同一闭环轨迹的描述性线性响应归账**，不是删掉某项后的反事实因果贡献；\(f_i\)、状态、特征与 \(W_q\) 都来自同一反馈路径，改变其中一项会改变整条轨迹。它可增强机制解释，但不是新的控制方法或独立性能证据。

## 目标掩码与 tracking 掩码分离的判断

源码里尚无 \(M_s=110,M_y=000\) 臂。C5 将同一个 `positionCoordinateMask` 同时用于 \(s_c=s-M_s\eta\) 与标签参考加速度（掩码轴取 \(a_f\)，未掩码轴取 \(a_{req}\)），因此现有实现固定 \(M_y=M_s\)；C4 的标量 `positionCoordinateM` 也同时控制两处，\(m=0\) 不是新臂。C5 旧区间标签由完成区间速度变化和参考积分生成，标签可写成 \(d_y=d_0+M_y r_f\)，不需要当前 \(r_f\)，不会因分离掩码引入代数环。

由 \(s_c=s-M_s\eta\) 得 \(\dot s_c=-e-K_2s_c+u-d_0-M_s r_f\)。在理想 \(\beta=1\)、无裁剪且 \(u=d_y\) 时，物理 forcing 为 \(u-d_0=M_y r_f\)，协调面 forcing 为 \((M_y-M_s)r_f\)。因此 \(M_s=110,M_y=000\) 若能准确预测 \(d_0\)，可消掉理想物理 forcing，却在协调面留下 \(-M_s r_f\)；实际还要保留 \(\beta\) ramp、预测残差、输出 clip、projection、leak 和 10 ms 保持。这个交叉臂可检验 PCF tracking 与学习目标坐标是否需要匹配，但单独的成功结果主要是已知坐标一致性原则的消融，不足以证明新的控制律或单独通过原创性门。若未来批准，只能保持 \(M_s=110\) 与其余 C5 条件冻结、只改 \(M_y=000\)，并报告 \(u-d_0\)、\((M_y-M_s)r_f\) 及其 signed 响应项；不据此预判改善。

## 判定与证据定位

没有发现表面计算使用零 residual preview 的错误：该调用的 surface 只由当前 \(r,p,\dot r,v\) 决定，与 residualForce 无关。也未发现 \(s_c=s-M\eta\) 或 \(\eta\) 更新方向错误。需要继续作为研究假设披露的是：目标残差 \(d_M\) 受当前控制、非线性姿态/推力实现和滤波影响，有限路径证明没有证明它可由固定 \(W_*\) 全程表示或具备外生性；学习符号正确本身不保证真实物理误差单调下降。

本复核只读源码、DEV 理论与 DEV72 输出，没有打开 TEST raw、读取/计算 TEST 性能分数或将其用于机制选型。一次范围过宽的只读 rg 命令意外显示 TEST 元数据 ID/path/hash；该暴露已在 `TEST_METADATA_SEARCH_INCIDENT_v1.json` 记录，本次不声称从未看过历史 TEST 元数据。未运行 Plant/MATLAB、未调参。SHA-256 与定位如下：

- matlab/core/position_bs_step.m，ea533c3ae97cbc552208287e7f8d9b0a0f5a018f36fb5c8bd45520e19e73c681：第 17–27、52–61 行给出 \(e_p,e_v,s,a_{\rm req}\) 与补偿力单位。
- matlab/models/position_filter_realization_pcf_step_v3_5.m，b4ae22db5bd444a162d0cd01a3a59a589f2e37077b089bb33693401b660228d0：第 13–21 行给出 \(a_f,r_f\) 与指数保持 \(\eta\) 更新。
- experiments/position_axis_coordinate_c5_dev72_20261023/delayed_prediction_step_candidate.m，48feebf934b8eb90b4424f2286aa857c48213d229714f30af99aacf53329549d：第 41–43 行给出输出先于负 tracking、leak、旧标签梯度及盒裁剪更新。
- experiments/position_axis_coordinate_c5_dev72_20261023/run_dl1018_closed_loop.m，48350037b66efe00301b138068f187c62cf92583f0f9ba2fabc9b24f248a963c：第 1982–2015 行取 surface/PCF 面；第 2023–2044、2054–2060 行生成延迟区间标签并保存上一特征；第 2128、2138、2155 行保持并注入补偿；第 2250–2270 行完成姿态滤波、再计算 PCF 和所选标签参考。
- reports/paper_continuation_20261023/physical_residual_tracking_lemma/PHYSICAL_RESIDUAL_TRACKING_LEMMA_ZH.md，ba5db2bfe3a99b949b11d266755f6b8202bb812d7a0cb1e8177500b8e3a1c179，以及 ERRATUM_MASKED_RESTORATION_ZH.md，b48b87864b8a327e6958ddeb5d7eed6c3170b2cf4091a22b1754b2729f040231：物理坐标精确采样递推与 \(Mr_f\) forcing；增广坐标显式保留而恢复到物理坐标时抵消 \(\rho_\eta\)，并明确固定 M110 勘误范围。
- reports/paper_continuation_20261023/BOX_PROJECTION_FINITE_PATH_BOUND_ZH.md，48b63a205f27d4ef595fcf6a25ef1c8b45c8169c11251a77d244bc0c66b85406，及 THEORY_FINITE_PATH_SCOPE_ACCEPTANCE_v2_ZH.md，a7d29ad6bd8cb6f5175cced87b181b2ff22317dfb0303428dfd3efa59aaff7ec：有限路径证明保留 tracking/leak 内积、ramp、输出 clip、标签区间变化、\(Mr_f\)、物理采样余项，并限定为后验路径界。
- reports/paper_continuation_20261023/ACTUAL_PHYSICAL_BRIDGE_DEV72_CHECK_v1.json：核验 72 场四项 forcing 重构的普通浮点残差；逐场 summary 不含 forcing 响应交叉能量。单场 pilot 源 reports/paper_continuation_20261023/parent_response_pilot_v1/pilot.py SHA 504daa88eb891ddac4f54f66e3f9fc085a3891f67e27366a93b900b3c8e74ed4；结果 PILOT_RESULT_v1.json SHA 0791bcce051f24fa623587f6b12e4f17222058d262c1f606aa55b2fecfa7de2b；它核验一场的完整 Gram/Q 闭合，不替代 DEV72 阶段分组。reports/paper_continuation_20261023/dev_prior_target_translation_v1/DEV72_PRIOR_TARGET_TRANSLATION_FINDINGS_v1.md：当前 W0 同轨迹目标能量及平移交叉，只覆盖冻结 W0 的目标拟合问题。
- reports/paper_continuation_20261023/dev_physical_response_decomposition_v1/full72_response_gram_v2.py，D28FFFA821ADF038568580C286C6C665001A082A49A1BF6F65A24C183A81DC46；输出 DEV72_RESPONSE_GRAM_v2.json SHA 855F1570CC6F4AC8FF2040B81C7B19C49C2A08CEDA3DD3CCE297CFBF2C186657。源门控固定 C5 parent 72 行、两条 C5 目录白名单、DEV/VAL ID；报告范围 DEV24+VAL48。
- reports/paper_continuation_20261023/control_path_credit_peer_v1/TEST_METADATA_SEARCH_INCIDENT_v1.json，SHA B460EAFD4D28959135B79D5FB220ADD1F8240CD74746F656AD92001D0686AC44：记录宽范围检索造成的 metadata-only 暴露。
