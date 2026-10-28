# Frozen A_KAN29 replacement preparation (v1)

本目录只准备把冻结的 DL1009 V3.6 A_KAN29 输出块接入 C5 姿态力矩通道；不启动 Plant、不训练，也不读取 TEST 原始结果或分数。C5 位置环、BS 姿态基线、参考滤波器、分配器、Plant 和其余参数保持冻结。候选固定为 lambda=1、online head disabled，旧姿态 RBF 的 enabled/update/output 三个开关关闭。只允许通过 attitude_kan29_c5_opts_overlay_v1.m 在内存中叠加，不调用会替换位置模型的 PA_F 工厂。

## 冻结来源

- C5 输入快照：experiments/position_axis_coordinate_c5_dev72_20261023/C5_DEV72_PREPARED_CFG_OPTS_v3.mat，SHA256 842ef395569e675db6e139c2684d72b976946915e5e0a58b9b7f24ec10c1d24a。
- C5 runner：experiments/position_axis_coordinate_c5_dev72_20261023/run_dl1018_closed_loop.m，SHA256 48350037b66efe00301b138068f187c62cf92583f0f9ba2fabc9b24f248a963c。
- A_KAN29 top-level MAT、parity fixtures、normalizer、冻结记录、TRAIN/VAL reuse 清单和 DEV scene 清单均复制到本实验的 artifacts/。源包来自 DL1009/RBF-BS0/experiments/attitude_kan_legal_input_reuse_upgrade_v3_6；副本必须逐文件 SHA 与源一致。
- 模型冻结记录指向 TRAIN128（B64 + P_CF64）及 VAL32（P_CF），X29 输入、lambda=1；此模型并非在 C5 场景中训练。只能作为冻结模型替换候选，后续闭环检查限 DEV。

## 预备检查

1. Python 只读核验 artifact SHA、freeze/reuse 身份，并按 MATLAB attitude_model_feature_x29_v39.m 实现对 148 个固定 parity fixture 的输出参考。
2. MATLAB no-Plant 检查加载 C5 snapshot 和 top-level A_KAN29 struct；只对比允许的姿态 option overlay，确认 cfg 与所有位置/其余 opts 字段不变。核验固定模式 J0、dmax/beta 单位与符号、100 Hz 事件节奏、32-event readiness、预测先于更新且 head 权重不变，并逐 fixture 对齐 Python/MATLAB 输出。
3. 检查只加载配置、计算参数和模型推理，不调用 runner、Plant dynamics、训练、优化器或 TEST。

候选输出是归一化 body angular-acceleration residual，物理限幅 dmax=[45,45,4.7124] rad/s^2；控制力矩接口为 dTau=J0*(beta*dmax.*clip(y))（N·m），其中 beta 按 C5 的 2.2 s rise-time 递增。BS 名义项和补偿项经原 attitude_bs_step 组合；本准备不对姿态误差定义做新假设。后续角度评估应以滤波后的 command orientation 为参考；若报告几何 body-rate error，使用 omega - R_actual' * R_ref * omega_ref 且 omega_ref=T(eta_ref)^-1*etaRate_ref，不要直接相减两个不同 body frame 的角速度分量。位置 Q 保留全 20 s，首 31 个姿态事件另报 readiness/warmup，不剔除。

根提供的单 DEV 基线 filtered-command SO(3) RMSE 已约 0.002056 deg、peak 0.00555 deg；这是已有高精度基线提示，不据此单场改参或选型。新候选不能预设必胜；报告应完整保留实际 DEV 表现。

## 当前状态与边界

本 v1 只包含隔离 artifact 副本和 option overlay；无 Plant、无训练。no-Plant Python/MATLAB checker 由根先审源码后才执行。闭环 DEV 验证及任何释放仍需根单独决定；TEST 不用于研发选型。历史 C5 输入和结果保持原样。
