# C1实际Head契约及有限结论

主审只读归档position_only_search_options.m与position_only_search_head_step.m，SHA分别为4e8322934ddb524961fa762426800564f6c758e00b943b622c9143ed734f19bf、3bd0fe9686c3b75793575e517d4cc5f08de58ab6a26a2bc7516aa690422bb7dc。R2 frozen_inputs.json钉住该源；本页不修改它们。

FEATURE构造实际设置p.weight=kappa*W0，W0为33×3含常数feature。运行时raw=Wᵀphi，applied=beta*clip(raw,±dmax)，随后更新

```text
W_next = elementwise_clip((1−0.002*dt)*W − dt*12*beta*phi*sEffᵀ, ±60).
```

输出先于更新。FEATURE分支不使用kappa调整运行时输出；kappa仅构造初值及保留元数据，BIAS分支另有语义，C1不使用BIAS。model.output_W与Head.W0保持原模型，不能误改它们代替初始state。PCF启用及全部三轴sEff规则均与原ON相同。

可给出一个受迫Head结论，而非闭环稳定性证明：假定两份Head逐事件接收完全相同的phi、sEff、beta、dt，且0<=0.002*dt<=1。逐元素投影是Frobenius范数下非扩张映射，因此

```text
||ΔW_next||F <= (1−0.002*dt) ||ΔW||F.
```

又因feature单位范数、输出clip非扩张及0<=beta<=1，同事件的应用补偿差至多beta*||ΔW||F。初值差为(1−c)*W0。若dt恒为0.01，20秒2000次更新中仅泄漏对应的乘子为(1−0.00002)^2000≈0.960789；初值差不会被此泄漏在20秒内迅速消除。初始无有效推理的事件及实际dt应另从真实日志核对，不能硬套2000次计数。

真实闭环中的phi和sEff会随状态与PCF改变，以上相同受迫输入假设不成立。因此该不等式只解释初值干预可能持续、可由配对实验检验，不能预测Q、不能证明两个闭环差收缩，更不能取代论文要求的实际误差动力学稳定性/误差界。C1不会凭权重投影有界宣称闭环稳定。
