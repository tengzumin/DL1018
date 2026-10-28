# MLP15 DEV72 评分规则 v1

这份规则补足 DEV72 任务书未明确 SO(3) 目标姿态来源的问题。首场闭环已结束；在查看候选/B 的位置或姿态误差数值之前，先固定本规则。它属于探索性 DEV 评价，不能追溯宣称为预注册 TEST 规则。

## 输入与配对

- 候选、B 必须绑定同一 C5_DEV72 输入锁中的场景 ID、解析参考、初始状态、臂长计划和风。
- B 仅读取输入锁指定的 B72 raw/status；不重跑 B。候选和 B 的 raw、status、payload 身份逐项校验 SHA。
- TEST 不读取、不参与计算。在线控制器不读取下述评分目标重建。

## 指标

- 位置 Q：所有 0–20 s 样本，sqrt(mean(sum((p-p_ref).^2,2)))，候选与 B 使用同一场景位置参考。
- 姿态目标：DEV B raw 的 scene 不含 R_task。离线对每个参考样本，用锁定 C5 配置在初始臂长下生成固定名义 Plant 参数 P0，并计算 eta_ref = baseline_force_to_attitude(a_ref, yaw_ref, P0)；再用项目的 ZYX 欧拉旋转约定得到 R_ref。a_ref 和 yaw_ref 只来自锁定的解析场景参考。此计算仅供离线计分，不进入 runner、状态、特征或控制输入。
- 姿态 SO(3) RMSE：对实际状态 Euler 姿态计算 theta=acos(clip((trace(R_ref' * R_actual)-1)/2,-1,1))，再计算 sqrt(mean(theta.^2))；按 0–20 s 全部样本等权。
- 场景胜负沿用原始未舍入数值及 1e-12 容差；组指标按场景等权，不将时间点视作独立样本。

## 工程首场门

首场只判断输入和实现是否正确：完整稳定 20,000 步、状态/参考/输出有限、无 safety stop、电机饱和或 generalized clipping；候选 tilt projection 次数不得高于同场 B；MLP 事件 trace 必须因果、有限，且 trace 的 Nm 输出逐事件等于送入 BS 姿态控制器的补偿输出；姿态 RBF、惯量重建、observer 和物理前馈必须关闭。位置或姿态单场输赢只记录，不单独决定首场工程门。

DEV72 是探索性闭环筛查；即便达到门槛，也不等于独立 TEST 或实机证据。
