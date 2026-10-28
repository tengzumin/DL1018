# RBF成功参照最小诊断放行

2026-10-27。仅Python只读诊断，0 Plant/0训练/0 TEST。Luna极高实施，root审核。

局部MLP耦合负特征值不是根因证明；成功RBF可能也需要此补偿。独立inventory确认原C5 raw只保留最初8事件81x3完整姿态权重，但1999事件的6维输入、学习surface、gamma调制、dt/flag及run_start RBF配置可用；初始姿态W为零。禁止将位置33基W0当姿态初值，禁止从norm逆推权重。

执行目录attitude_rbf_local_reference_20261027_v1。按原basis/update实码前向重放，投影按实码执行，不求逆。先核对8次完整快照、1999次unclipped/clipped输出、phi及权重范数、导数范数；通过后取同样均匀200成熟事件/场计算固定W下RBF局部导数。

比较BS、RBF、冻结MLP在同一C5状态/参考/历史，不增加adaptive MLP条件头。固定J0/Jdot0/K1/K2，只读命令参考与反馈；MLP同C5记录重建过去14事件历史。中心差分1e-5，5e-6数值校验；先原点τBS/补偿/net torque对日志，再解释导数。假设性局部MLP评估不当作真实闭环或独立验证。

不重建实际惯量、不读取可变Plant inertia、不添加模型/控制项/增益、不启动MATLAB。若不能复现，记录不充分/不匹配，不跳过检查、不凭不同闭环轨迹的负λ比例下根因结论。
