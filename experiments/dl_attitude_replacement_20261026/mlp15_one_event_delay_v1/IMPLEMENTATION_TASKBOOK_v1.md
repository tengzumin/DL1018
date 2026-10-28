# MLP15 单事件完整补偿延迟 v1

## 边界

父版本为 `mlp15_composite_dev_v3`。唯一控制变化是在真实 MLP15 DEV 事件入口：事件 k 应用缓存的 `generatedTorque_(k-1)`，首次事件应用零；当前 step 仍正常生成 `generatedTorque_k` 并更新原状态，生成量缓存给下一事件。缓存值已经完成当前 beta 和 dmax，不再次缩放或裁剪。非事件样本继续保持最近一次 applied torque。

`mlp15_attitude_step_v1.m` 必须与 v3 逐字节相同。其余模型、输入、RLS/Joseph、tracking、P/weights、beta/dmax、固定 C5 位置栈、J0/Jdot0、BS、滤波、Plant、执行器、物理场景保持 v3 配置。残差历史只读取实际 `requested_generalized` issued torque。

Raw/trace分别保存生成和应用的完整 torque、生成与应用源事件 sample/time、实际 delay age、首次零应用标志。不得把 head/generated output 称为 applied torque。

## 实现与验证

仅复用 v3 候选源码树、driver/auditor结构、锁定配置、六场 manifest 和基线报告；不复制任何历史 raw、模型权重或 fixture。新 source lock 必须记录精确继承关系及唯一 DEV 源差异。初始 release 为 0 Plant 调用、无授权场景，等待 root 审核。

无 Plant 检查覆盖：step SHA 与 v3 一致；300 个合成事件及完整 1 ms 时间轴上的一事件延迟、首事件零、当前 generated 不影响当前 applied、无二次 beta/dmax、非事件保持、非等间隔事件源索引/时间/年龄；真实 cfg/位置身份/which 路径；实际 DEV 与外层 driver 均被 release0 拒绝。复用 v3 原 step 300 事件数学证据，不重算基线。

Raw auditor独立重放未修改的step，验证当前generated、前一事件applied、完整源索引/时间/年龄、全1ms保持、head权重/P/step torque，以及使用真实过去issued torque的残差更新。策略间状态不要求在首个应用差异后相同。

禁止 Plant、训练、TEST、真实惯量重建、调参/搜延迟、修改任何历史目录。Root审核后再决定是否放行 T1_C05_W12。
