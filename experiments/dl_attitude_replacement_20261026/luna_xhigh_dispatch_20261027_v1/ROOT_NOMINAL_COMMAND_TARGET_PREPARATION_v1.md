# 名义命令端口监督目标：隔离准备任务

主审 /root，Luna xhigh 实施。只授权本项目内隔离数据构建和核验；训练、Plant、TEST授权均0。端口方程独立复核及数据核验后，root才决定正式训练，不把本任务视为目标已正确或论文通过。

## 依据与唯一待检验假设

余弦lr仅改优化日程使全72教师拟合向量RMSE下降61.785%，但六场任务SO3仍0/6胜C5且位置、inner亦0/6胜C5；已关闭，不扩72。更精确模仿RBF并不充分。对同一C5记录10674个成熟区间，余弦GRU→RBF教师向量RMSE约0.578，RBF教师→近似名义残差约0.969 rad/s²。唯一下一假设为：将监督从RBF策略输出改为可观测的区间平均名义命令残差，可能改善匹配部署模型的补偿。这个量是离线差分近似，不是真实瞬时气动力矩，不预先保证闭环更好。

## 端口和单位

原始Plant实际接收realized_generalized，控制器下发给固定名义分配器的是requested_generalized。主动变形时两者可在零饱和/零裁剪下不同。目标针对固定J0/C0名义命令模型，应采用请求力矩tau_req，而非把它称为实际体轴力矩：

R_cmd(e) = (omega[e+10]-omega[e])/(t[e+10]-t[e]) + mean_i inv(J0)*(cross(omega[i],J0*omega[i])-tau_req[i]), i=e..e+9.

omega为body rate，J0为已锁定固定名义矩阵，tau_req取requested_generalized的第2–4列。单位rad/s²。R_real若用realized，二者差为mean(inv(J0)*(tau_real-tau_req))，用于离线端口核验，不作为新标签或输入。必须由实际allocate_control/vehicle_derivative及独立数值复核确认本定义与部署匹配；不能把零饱和当端口相等，也不能直接认定旧RLS诊断公式错误。

## 数据构建

新目录 nominal_command_target_data_v1。仅读既有matched_teacher_data_v1.npz中C5 TRAIN24+VAL48_AS_DEV_TRAIN的输入、场景ID，以及对应72份C5 raw/status与绑定manifest；排除B数组/TEST。旧文件只读。

特征X完全复用原NPZ，逐数组SHA/shape/dtype与旧值相等。每场事件Python零基e=10,20,...,19990，共1999；新目标取从当前事件到下一10ms边界的区间，包括最后19990→20000（raw有20001状态/20000控制，须实际核验）。旧语义诊断为只比较相邻attitude事件而少一尾区间，不可将其1998计数直接作为新训练长度。

保存 unclipped_R_cmd 与按现有dmax逐轴clipped_R_cmd，dmax必须从LOCKED_CFG读取完整精度（约[45,45,4.7124]，不得按该显示值重新截断），训练候选只使用后者，保持post-DMAX/pre-beta输出合同。记录每场/轴/阶段的clip数量、比例、RMS、bias及与旧教师的差异。未来区间量仅用于离线监督；部署forward仍只能当前/过去的合法13维特征，不可把未来gyro/命令、残差标签或真实Plant量加为输入。

不读取/重建Jtrue/Jhat/Jdot/Ctrue、真实质量/风；realized量仅允许独立端口核验，不用于标签生成。完整J0固定矩阵从已审LOCKED_CFG获取，不能以估计惯量替代。环境理想无噪声反馈及有限差分/积分近似边界必须披露。

输出仅新的目标NPZ、包含72条源raw/status和X/ID/target SHA的manifest、统计CSV/JSON、源脚本/准确复算命令。可不复制旧X，在manifest钉住旧NPZ并保存新Y，训练器未来再读取两份输入；不得覆盖或重标旧NPZ。保留float64诊断目标，训练目标float32转换须明确记录。数据新增预算1GiB，不启动Teacher采集/训练/Plant，不新跑B/C5。

## 交付与下一步

先交root最小脚本与0训练/0Plant结果，独立端口复核未解决前不训练。root审核后如批准，后续唯一正式候选将保持余弦lr、同GRU结构/normalizer/init/seed/60000步/batch4/TBPTT128/顺序和全部控制栈，仅改变监督目标；该正式训练尚未授权。旧teacher normalizer的target_rms也保持不重拟合，避免同时改变损失权重。数学runtime继续与当前GRU部署一致，后续仍先首场再六场，不自动DEV72/TEST。
