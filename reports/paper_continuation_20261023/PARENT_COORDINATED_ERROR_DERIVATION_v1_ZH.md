# 主审核：固定坐标下的连续误差恒等式

这是源码定义的连续极限核对，不是实际离散闭环稳定证明。

取 e=r_p-p，de=r_v-v，z2=de+K1 e。位置BS给 a_nom=r_a+K1 de+e+K2 z2，a_req=a_nom-u。定义 d0=a_actual-a_req，则恒等地

    e_dot=z2-K1 e
    z2_dot=-e-K2 z2+u-d0.

PCF 定义 rf=a_req-af，eta_dot=-K2 eta+rf。固定对角 M 与 K2 对易，sc=z2-M eta，dM=d0+M rf，故

    e_dot=sc+M eta-K1 e
    sc_dot=-e-K2 sc+u-dM.

这说明在实际记录状态上，PCF项可在协调面方程中代数抵消；不能仅因补偿到实际加速度的局部雅可比非单位，就断定原tracking更新应乘该雅可比。dM本身可依赖u，恒等式仍成立；但把它当候选输出无关的常量做反事实预测不成立。这两件事必须分开。

若暂令 u=beta W^T phi，dM=beta Wstar^T phi+epsilon，则 sc*(u-dM)含正号 beta sc phi^T(W-Wstar)。权重误差Lyapunov交叉项可由 W_dot=-Gamma beta phi sc^T 抵消，因此代码tracking项的负号与该形式一致。该推导没有证明固定Wstar确实能近似输入相关dM，也没有证明PE、稳定性或未来性能。

V=(||e||²+||sc||²)/2 的连续导数还保留 e^T M eta；不能删去这一项。实际代码又有sc裁剪、输出clip、beta渐入、10ms先输出后更新、1ms离散积分、变化特征、泄漏和投影，均不能以以上连续抵消式自动保证。

结论：目前未由名义输入灵敏度问题推出tracking符号实现错误。下一步只应检查具体离散余项/目标定义与日志的一致性，不应贸然换成filtered-X或MPC，也不能称这些普通结构为新贡献。

来源：matlab/core/position_bs_step.m；matlab/models/position_filter_realization_pcf_step_v3_5.m；experiments/position_axis_coordinate_c5_dev72_20261023/delayed_prediction_step_candidate.m。独立执行者的推导尚待交叉核对。
