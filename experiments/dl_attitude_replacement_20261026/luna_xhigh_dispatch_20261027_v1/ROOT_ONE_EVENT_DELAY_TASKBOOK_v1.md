# 单事件补偿延迟：最小闭环因果任务书

2026-10-27。主模型root决策，Luna极高实施。当前论文目标未达标。用户已授权自主后续研发，但本执行阶段仅实现/无Plant，初始release0；root审核再放行航次。

## 证据及唯一假设

原六场composite完整稳定但性能FAIL，不扩DEV72/TEST。同C5状态1200点参照：BS/RBF负局部阻尼特征值0，冻结MLP711，RBF局部导数增量/BS中位0.000381，MLP3.389。nominal-torque特征固定仅去掉部分耦合。该局部证据支持检验当前事件神经直接反馈通道，但不证明完整闭环不稳定，不证明加延迟必好。

## 唯一控制因素

新目录mlp15_one_event_delay_v1，以已实际完成六场的mlp15_composite_dev_v3为父。模型、13维输入/15事件、归一化、RLS/Joseph、tracking、P/weights、beta、dmax、C5位置栈、固定J0/Jdot0、BS、滤波、Plant、执行器、全部物理场景保持不变。数值MLP step必须逐字节不变。

只在真实DEV事件入口改变补偿应用：事件k仍正常计算generatedTorque_k及更新，实际应用generatedTorque_(k-1)，第一事件应用零；非事件继续保持这个delayed held torque。延迟的是完整beta/dmax后的估计力矩，不能再乘一次当前beta。当前生成量仅存为下一事件可用；禁止未来量。实际issued torque历史用于同一合法残差观测，原更新公式不变。

trace必须分别记录generated与applied、源事件index/time、首次零输入及实际10ms年龄；原raw/head output不混称applied。采样/保持时间额外代价明列，不能用冻结记忆Jacobian变零宣称稳定。该试验比较的是整个延迟策略效果。

## 最小实现/验证

复制已有v3成功driver/实际DEV入口及小配置，不复制历史raw/模型/夹具，不改旧目录。沿用已修复marker hash排除、真实p.cfg绑定/full72模型重绑及失败raw先存。避免新generic入口/另一套框架。

无Plant验证：step SHA完全相同；至少300个合成事件，证明applied(k)=generated(k-1)、第一事件0、当前generated变化不能改变当前applied、beta/dmax不重复应用、不等间隔记录实际年龄；原step300事件数学证据原样复用。真实入口/driver release0拒绝；只做必要cfg/路径/身份核验，不重算不变baseline。新raw auditor复用v3，独立重放原step并验证generated/current和applied/previous、issued-history残差、W/P/控制力矩、场景和安全。新driver每场拒绝覆盖，完整日志/SHA/marker、失败保留。

## root后续闭环范围（本执行者初始仍0）

root审核后先跑DL1018_VAL_T1_C05_W12一场作工程核验，通过工程/安全/因果审核后补原其余五场（无风T1_C08_W15,T2_C05_W15,T3_C02_W15及HF T2_C02_W12,T3_C00_W13），最多6候选航次，不新跑B/C5/无延迟composite。此小试验完整覆盖两组，不按有利单场挑选。工程不安全或trace不符则暂停修复审阅；性能失败照实保存，不扫延迟/增益。

对照固定原v3同场raw，并同时报告prediction-only/B/C5，root独立复算Q、任务SO3、inner、逐轴/阶段/峰值/安全和全部输场。最终仍双环优于B、姿态优于C5、位置不超过C5既定退化边界；六场只是机制筛查，不是独立测试。未通过不扩DEV72/TEST。

PowerShell7、显式R2025b、单重负载；不终止已有任务，不读TEST，不训练，不重建实际惯量，不上传/删除历史。准确命令/续跑状态/输入源码模型身份保存新目录。
