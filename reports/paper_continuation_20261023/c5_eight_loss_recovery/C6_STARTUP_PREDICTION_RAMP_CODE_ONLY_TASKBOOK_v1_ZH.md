# C6：唯一优先假设与单因素隔离实现

根已实际读 C5 helper 与三条同记录回放摘要。正式冻结 C5 TEST 已启动，不修改其任何文件/方法/次序。本新分支仅属于用户本轮授权的八输场隔离修复尝试，不使用 TEST 结果作研发。

目前未证实部署实现错误。待检验机制是：ready 后至 beta 饱和之前，tracking 梯度乘 beta，prediction 梯度没有乘 beta；两者瞬态相对权重因此与稳态不同。同记录梯度反向不等于有害，尤其 prediction 可能提供必要的残差目标校正，故本假设只能由干预验证。现有消融显示 T2 的早段代价与其他组/后段收益并存，不能直接移除预测。

只允许一个候选 C6_STARTUP_PREDICTION_RAMP，单因素修改：

`candidate = W - h*gamma*beta*(phi*s_eff') - h*lambda*W - rho*beta*predGrad`

即在 C5 原式预测项上乘已有 beta，beta 时钟、readiness、tau=1、h=.01、tracking/leak/projection、W0/model/normalizer、PCF M110、所有输出和部署输入不变。不得另造增益、阈值、场景切换或更长延迟。beta>=1 后当前状态下两公式完全相同，但之前权重不同会影响后续闭环，不声称后段性能保持不变。

写入 experiments/c5_eight_loss_recovery_20261024/c6_startup_ramp 及当前隔离报告下 c6_startup_ramp。从冻结 C5 复制必要 MATLAB helper，并实现同公式 Python reference，保存源 SHA 和最小 diff。禁止修改冻结 C5、主正式代码、当前或历史数据。不启动 MATLAB/Plant/训练/GPU。

轻量离线验证限于：输出先于更新；首 ready 无历史时与 C5 完全相同；beta=1 时相同输入/权重输出与更新完全相同；0<beta<1 时 preprojection 差值等于 rho*(1-beta)*predGrad；只做一次联合投影；联合 clip 边界与 NaN/非法输入拒绝保持；用已读三个当前 DEV host 的同一记录状态重放，不新增批量 raw 读取。结果只报告代数/一步目标与跟踪梯度取舍，不把强制状态重放的输出差或标签误差当作闭环 Q 改善。

交付 helper/参考实现/真实输出、失败解释、输入身份、源码 diff/SHA，以及供根审核的最小闭环任务说明。后续是否跑闭环、场景和执行时机由根单独冻结，正式测试重负载优先。本次 MATLAB/Plant/训练授权均为零，不做参数搜索。保持总期限与磁盘上限，原失效记录保留。
