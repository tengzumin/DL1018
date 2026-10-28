# 延迟原始残差创新：可审核方案草案

状态：`DRAFT_NOT_AUTHORIZED_FOR_PLANT`。本文件不是第四轮执行许可。原三轮及C2额外12航次已用尽，新增训练/闭环必须用户另批。上一目标轮为进展：完成12条raw与504行分组的目标语义核验，避免把raw/applied定义差异误认为高频晚段性能修复。

## 唯一干预与拟议参数

原FEATURE Head没有prediction项。本草案只在原tracking+leak更新中加一个对上一10ms物理残差的raw预测项；保留X14、原W0、encoder、normalizer、全轴PCF、原位置BS、B姿态控制、C0/J0、Plant和执行器。输出仍先于更新，仍按C2约定beta=min(k_MATLAB*dt/1.8,1)渐入并clip至±3m/s²。

索引严格区分：本接口与下文j/k均为Plant零基n，transition_time=n*dt，MATLAB循环索引k_MATLAB=n+1。因此候选beta=min((n+1)*dt/1.8,1)，首ready n=320/t=0.320s时beta=0.321/1.8。不能用t/1.8替代，否则把旧ON1时钟混入单因素试验。未来runtime应传k_MATLAB−1和t(k_MATLAB)。

对当前事件k、上一有效事件j=k−10，过去区间目标为

`y_prev=(v[k]−v[j])/0.01−(AF_integral[k]−AF_integral[j])/0.01`，

其中AF_integral[k]仅累积i<k的内部a_f[i]*dt。不得读取当前/未来a_f、真实风、真实构型或物理真值。预测用当前事件前W_k和旧phi_j：`r_prev=W_k^T phi_j−y_prev`，不除beta、不clip训练残差。首个ready事件无合法previous样本时，新项为0。

速度通道沿用现有BS控制器已使用的状态反馈。现有仿真直接把Plant状态作为理想测量输入，没有估计器；本草案继续这一共同假设，不把它包装成含噪传感器部署。不得新增truth-only导数、外力或构型通道。若用户要求改变此假设，必须另立传感器/估计器方案，不能拿当前对照身份混用。

`raw=W_k^T phi_k; applied=beta_k clip(raw,±3)`；随后

`W_next=clip(W_k−h*gamma*beta_k*phi_k*s_eff,k^T−h*lambda*W_k−rho*phi_j*r_prev^T,±60)`。

保持h=0.01s、gamma=12s⁻²、lambda=0.002s⁻¹、s_eff原±[7,8,10]裁剪。仅最后执行一次联合投影。

拟请求批准的单一新常数为tau=1s、rho=h/tau=0.01。依据仅是单位范数特征下单一固定样本的名义约1s误差衰减时间；不是搜索结果、最优值或完整闭环安全界。它目前只属于待批准草案，不配置到现有实验、不拟合或扫描。新增项是机制鉴别，不把已知复合自适应的组合本身称论文创新。

## 当前允许的工作与文件分工

- A只在construction/写一个Python纯参考函数、对应MATLAB纯函数文本和一个小型确定性自检。仅合成独立单步例，不用历史/训练模型，不累计学习、不optimizer、不执行MATLAB。为保证申请的新阶段有完整可审代码，可另在construction/runtime/写C2 core的独立集成草案副本和diff；原C2 core不动，不运行副本，不提供launcher。新增flag默认false，true时必须在Plant前核固定输入/配置/helper存在与FEATURE/update/full-PCF条件。AF积分只在本步a_f计算后累积，head事件的积分读数只含过去步；保留原bias审计兼容，记录新项目标/索引/范数以便未来复核。
- B只在review/独立审源码、单位、因果时序、首事件、投影、beta及科学预登记，明确代码草案通过与运行权限不同。
- 主审在本目录记录证明边界、独立复算合成算例并审核A的独立runtime差异草案；不得接入现有运行、改共享源或启动Plant。若integration仍未完成，则未来运行门保持关闭，不能把纯kernel通过说成整条runtime通过。
- 两名已有Luna max，不声称工具设置了1.5倍速度。PowerShell7；单CPU；产物总额5MiB，不做自引用字节定点等式。全部旧代码/报告/MAT/模型/账本保持原位，不删除、不停进程、不Git提交。

## 必要代码检查

首事件严格退化原Head；当前输出不含本次更新；旧phi配当前W；previous索引、时间间隔、单位范数及形状守门；beta=0不除零；一次联合box投影；解析prediction梯度差分。无previous时不得构造伪样本。Python与MATLAB文本的表达式逐项对应；未实际执行MATLAB时必须标明parity未证明。

## 未来拟请求的新额度与运行门（本轮不执行）

仅拟请求一个新的机制试验阶段：最多12个新增Plant航次、0训练、0seed/gain搜索、0完整72场、0TEST。固定同一VAL12字典序场景，单一候选tau=1s，复用身份一致的B和C2 beta-aligned c=1。先补齐隔离runtime、真实MATLAB无Plant/parity检查、输入/源码/模型封存及账本，再1场probe，审核后余11场；probe只作工程/输入/时序和安全门，不因单场Q好坏挑选后续场景。所有真实启动计数，失败保留，不自动补航次。预算≤1GiB、单个重负载作业、不干预旧实验，磁盘余量<30GiB不启动。

预登记观察：高频Z的5–20s及W15 X的0.33–5s同状态raw残差误差能否降低，同时位置Q不退化。机制评分必须作双向共同输入回放：分别以C2日志和候选日志为host，固定host的phi_j及区间y_prev，在同事件k对比两份W_before；各host单独报告，不把不同闭环状态下各自残差直接当作组件因果证明。不得在回放中累计新更新；两host也不当作两份独立场景样本。

须按所有场景与任务、风组、逐轴、早晚段报告，含完整安全、执行器、饱和、保持和实际耗时。残差更好而Q更差则否定“该更新足以改善控制”的机制解释；不挑轴、切head或改tau追指标。

若12场性能/机制不一致或新项无增益，则停止此候选，不追加搜索。即便12场通过，也只获得机制线索；完整72场、理论、贡献、消融及TEST仍需另行审核与预算，原论文性能验收不降低。
