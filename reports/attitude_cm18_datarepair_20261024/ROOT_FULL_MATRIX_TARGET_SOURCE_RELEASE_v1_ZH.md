# 完整三轴同状态目标诊断：源码放行

2026-10-25，Root。已读取入口全文和修改，SHA `fe48f2d9d812cfa92364bd859490858a0e3eec01b3e6e80c773c829f9975042c`。仅执行 `audit_full_matrix_replacement_target_v1`，依据同名任务书；0 Plant、0 optimizer、0 TEST，不产生新训练标签。

审核核对了：真实/名义 allocation 均进入 G、E0 的减号与惯量项、当前动作与 raw 的纯 allocator 复算、旧残差闭合、理想与完整限幅后的补偿误差分开报告、G 不正则化、phase 分组和 scalar JSON 容量门。

Root 发现并要求修正一处时钟校验：raw 第 k 行的时间是 `(k-1)*dt`，当前候选实现的 beta 使用 `k*dt`。诊断保留既有 beta 接口，单独记录 1 ms 偏移，不能在本次悄悄改变 beta。逐航次身份从锁定 SHA 的上游分解 JSON 派生，再核真实输入文件，减少重复手抄 SHA。

本次是同状态代数诊断，不重积分 Plant。即使理想 c_star 的代数误差为零，也不能认定其可被现有输入预测、闭环改善或稳定。递归 residual 学习可能通过固定点起作用，该替代解释继续保留。
