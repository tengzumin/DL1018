# SCREEN4 重放 attempt5 审核

实际 MATLAB R2025b 终止 OS1；新增闭环0，训练0。failure JSON明确记录 feature_closure_pass=true、old_action_closure_pass=true。代码顺序证明 make_summary 在新动作逐场计算之后执行，因此本次失败位于结果汇总，不是旧动作闭合失败。

错误位于 phase_axis_summary：out=struct([])为零字段结构体，首次 out(pos)=row 触发 MATLAB heterogeneousStrucAssignment。要求单点修复并用合成记录实际覆盖 newReady=true/false 两支。原v5目录及失败记录保留。

catch中的new_action_interpreted=false是异常报告默认值，不能据此宣称新动作计算未执行；也不能在CSV/完整摘要缺失时宣称新动作已优于旧RBF。修复后仍须完整运行并读取真实配对表。

首航审计口径已纠正：用filtered_attitude_reference/rate，而不是仅scene yaw；沿用C5实际姿态变换及0<=t<20计分，排除终端状态。首航尚未放行。
