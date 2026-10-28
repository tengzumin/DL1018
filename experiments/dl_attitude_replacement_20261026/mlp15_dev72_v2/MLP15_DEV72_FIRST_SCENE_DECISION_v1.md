# DEV72 首场决定 v1

时间：2026-10-26。首场为 DL1018_DEV_T1_C00_W03。

- 单场 Plant 航次完整稳定：20,000 transitions，状态/参考有限。
- 候选 raw、status、B72 raw/status、payload、external identity、release 和 source lock 哈希均通过核对。
- 候选与 B 的解析参考、初始状态、arms 和风数组逐元素一致。
- MLP15 有 1,999 个姿态事件；每个 13 维输入有限且时间/样本索引因果；每个 estimateTorque_Nm 与实际送入姿态补偿的 Nm 输出逐事件相等，最大差 0。
- RBF 输出/更新、MLP 在线更新、惯量重建、observer、物理前馈关闭。
- 候选/B 电机饱和和 generalized clipping 均为 0；tilt projection 均为 0；无 safety stop。
- 探索性离线计分：候选/B 位置 Q 分别 8.397/13.273 mm；按锁定解析轨迹加速度与 yaw 离线构造目标的 SO(3) RMSE 分别 47.739/53.702 mrad。
- 工程首场门 PASS。单场指标只作记录，不作为 DEV72 总体门的替代。

接口说明：B72 scene 没有 R_task。评分规则 v1 在查看候选/B 指标前固定；它用共同解析 reference 和项目既有力到姿态映射离线构造姿态目标，不进入控制器。此次属于探索性 DEV 阶段，不能称为预注册 TEST。

两次未消耗 Plant 的启动/检查错误均留有 logs 记录：首次 launcher 的偏好目录参数/输出路径错误；随后一次只读 raw inspection 使用相对 MATLAB_PREFDIR 导致 MATLAB 在 startup 退出。它们均未生成 attempt marker，也未改动原始输入。正式运行使用 PowerShell 7 与绝对隔离 MATLAB_PREFDIR。
