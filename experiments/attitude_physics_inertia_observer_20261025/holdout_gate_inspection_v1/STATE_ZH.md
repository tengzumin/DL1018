# 主动变形与姿态替代：阶段状态

更新时间：2026-10-25（本机日期）。

## 研究方向

用户已明确优先尝试深度学习姿态替代，并尽量减少显式惯量重建。当前 physics/observer 只作为公平比较与机制参照，不再自动扩成正式主结果。pilot 后优先设计小型因果时序网络（如 TCN）输出有界姿态残差力矩，部署时冻结网络，不先做在线学习；输入仅取可部署的姿态误差、机体系角速度、BS 名义角加速度/力矩和可测/可命令臂长及其速度，不使用 Jhat、Jdot_hat 或 Plant 真值。先检查可复用的 RBF/闭环记录作为离线监督数据；如果需要仿真真值标签，严格与输入分离并按场景划分。物理惯量重建留作这轮对照或后续消融，只有结果显示必要时再考虑部署。位置环继续固定 C5，主指标同时检查相对 B 的位置和姿态。

## 当前实验步骤

- 正在完成主动变形窄门 pilot 的放行前审核；尚未启动 Plant 航次、训练或 holdout。
- pilot 设计：6 个场景 × 9 个配置，共 54 calls，含 B、C5+原姿态 RBF、C5+RBF+共同物理前馈、physics/observer 2×2、两种固定几何对照。
- pilot 只核验前馈对照、runner/安全、几何任务和初步性能；不自动启动旧草案的 432-call physics/observer holdout。未生成的 48-scene holdout 继续封存，供冻结后的 DL 研究按新任务书使用。

## 已完成的无 Plant 核验

- 18 个 payload（6 个场景 × ACTIVE/FIXED_MIN/FIXED_BOUND15）已绑定锁定 C5 位置栈；canonical `R_task` 重建最大误差为 0；candidate 与 B validator 均通过；损坏 SHA 被拒绝。
- root no-Plant audit v2：`PASS_NO_PLANT_BINDING_AUDIT`；Plant calls=0、训练=0、pilot 未启动、holdout payload 未生成、TEST 数据未读取；8 组 candidate preflight 均通过。
- 外部 ID/seed 冲突审计及 B 原始源码/配置身份核验此前通过。
- 代码审查发现 B wrapper 曾只凭函数无异常返回就标记 `COMPLETED`，未校验完整 20 秒轨迹；隔离 wrapper 已加完整时间轴、状态数、有限控制量和 `STABLE` 检查。source-lock 已改为精确覆盖，但当前 lock 因 candidate/B 源码后续修改而过期；需重新生成。MATLAB 重新解析待做。
- C5+RBF+F 的力矩符号按 `M_nom−estimateTorque` 对齐；F×O=11 helper 曾通过 31 步 no-Plant 与冻结 v2 路径逐样本一致性。
- 文献核对：变形四旋翼的深度强化学习已有仿真先例，神经网络姿态扰动补偿也已有先例；当前贡献需放在固定 C5 位置栈上的严格匹配姿态替代与窄门任务证据，不声称“首个 DL 变形控制”。MorphoCopter 作者仓库可参考 Acados/ROS2/Gazebo/PX4 应用规划，但不是 MATLAB 闭环的直接替换件。

## 放行前剩余事项

1. 完成 candidate/B runner 逐行审查与 MATLAB R2025b 无 Plant 解析，复核精确 source lock 清单。
2. 54-slot pilot scorer 已写完静态版本：保留缺失、重复、失败和不完整航次，绑定 taskbook/source/payload/raw SHA，计算 Q、canonical R_task SO(3)、actuator/safety traces 与实际几何净空；MATLAB 解析待做。
3. 当前 receipt v2 的 taskbook SHA 与已更新草案不同；冻结 taskbook 后需生成新 receipt v3 与 `pilot_payloads_bound_c5_v4`，不能覆盖历史 v3 payload。再据最终任务书、scorer 与输入身份生成 release。
4. 最近资源复查（2026-10-25 22:43，中国标准时间）可用 RAM 约 1.36 GiB，C: 约 158.39 GiB 可用，逻辑核 16 个；未见 MATLAB/Octave 运行进程。启动前重新检查资源，使用独立 MATLAB 进程，不结束或打断既有实验。
5. pilot 审核后制定新的 DL 姿态替代任务书与训练/验证/封存测试方案；当前没有授权训练或 holdout。

## 现场状态

最近一次进程检查未见 MATLAB/Octave；本研究尚无 Plant 航次 marker/raw/start log。所有历史工程、MAT、模型和成绩均保留原位；不读取旧 TEST raw/status/成绩。