# C3联合离散界独立复核

结论：静态代数及源码时序复核通过，但仅限文中明示的条件一步界。它没有建立整体闭环Lyapunov稳定性，也没有解除执行门。

复核对象与冻结身份：`C3_JOINT_DISCRETE_BOUND_ZH.md` SHA-256 `6be6b7fca9913241b11f31bf8a9012f50c2b5654b89b73571aa76b03137e2736`；`SOURCE_BINDING.json` `6dfbd742be33f4f49eca45f13c64dd4d641ce46acca9657878377f9269613564`；代数脚本 `joint_update_algebra_check.py` `ef3bb0c251f79fa566741efc852bf6cfb9ada0b672d7fdb2b83ceb551f05fd37`；合成结果 `ALGEBRA_CHECK.json` `546a36434a5fbb08a2930d799e7fae46f84ecff127bfae4af4a7b564475d6919`。实际runtime/helper/source-lock SHA及报告绑定一致：`e5f1e30c433ee3f8206b36446cde71776589c161fe2a3ec60fbaf070585eb07f`、`48feebf934b8eb90b4424f2286aa857c48213d229714f30af99aac53329549d`、`863328963959c63d4628060fcff21e01d5322c487d077b5c20721d24ed9314a2`。

联合更新式与源码相符。helper执行 W_next = projection_box60(W_k − T_k − L_k − P_k)，其中预测项 P_k = rho × phi_j × (W_kᵀ phi_j − y)ᵀ，不带额外 beta；跟踪项含当前 beta，泄漏项为 h × lambda × W_k，三项合并后只做一次逐元素盒投影。平方范数展开的三个交叉项符号和系数正确。若比较器 W* 位于投影盒，报告使用的投影不等式及参数能量 E_W = ||W*−W_k||²/(2 gamma) 给出

    ΔE_W ≤ <W*−W_k, A_k>/gamma + (||A_k||²−||R_k||²)/(2 gamma),

其中 A_k = T_k + L_k + P_k，R_k 是这次合并投影修正。条件和符号均正确。

时间顺序也与runtime一致：在事件前权重 W_k 上先计算当前raw及 beta-clip输出，随后算下一权重；本事件已缓存/注入的输出不被当前更新回写。索引 n = k_MATLAB−1，beta使用 (n+1)dt/1.8，不会误用零基时间 n×dt。预测标签在k事件可用，是j=k−10到k的10ms速度差减去区间内 a_f ZOH 积分后的平均残差，并与旧特征 phi_j 配对；首次ready事件只允许缺少previous项，后续须有合法历史配对。PCF坐标代码取 s_c=s−eta，再限幅为 s_eff。

两项易混淆处处理正确：若理想控制项使用同一beta且 s_eff=s_c，tracking与输出误差分解中的线性参数项对任意 beta∈[0,1] 抵消，不要求 beta=1；但ramp残差、输出clip、s_eff−s_c、leak、预测项和联合平方交叉项仍在。合成代数核验只覆盖固定小矩阵与单步样例：联合平方展开差 3.55e−15，输出分解差 4.44e−16，孤立精确标签prediction步满足条件界。它验证公式计算，没有检验真实权重/初值或闭环轨迹。

必须保留的边界：W*∈B60 是假设；当前初值是否在盒内未由该文档读取模型核实。Vc 部分明确是理想连续模型下的假设式，实际离散PCF、RK4/保持、执行器与Plant误差余项 r_impl 没有符号或吸收界。状态/特征扰动、标签漂移和持续激励条件也未被界定。因此可称“实际联合参数一步投影不等式的条件推导”，不可称实际更新逐步耗散、闭环稳定或已证明论文理论成立。

本轮只读文档、绑定文件和合成代数结果；未读取raw/MAT、未运行脚本、未执行MATLAB/Plant/训练/GPU/TEST。后续DEV72授权与本数学审核相互独立，运行仍须通过主审release门。
