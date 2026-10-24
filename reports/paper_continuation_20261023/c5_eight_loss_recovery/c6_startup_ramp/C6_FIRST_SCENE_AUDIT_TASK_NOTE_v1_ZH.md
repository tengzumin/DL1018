# C6 首场配对审计入口说明

入口：`experiments/c5_eight_loss_recovery_20261024/c6_startup_ramp/audit_c6_first_scene_pair_v1.py`  
源码 SHA-256：`5dda7f17e0381be47e34757961f6b021e3d4c5f6c7f5c59b618fdf23d40cff9b`

脚本固定审计 `DL1018_VAL_T1_C00_W07` 的 C6 启动爬坡、同场 C5 M110 与已冻结 B72。它绑定锁定的 C6 helper 与 beta-scaled Python kernel；`stage1_position_delayed_prediction_term_norm` / `stage1DelayedTermNorm` 仅按未乘 beta 的 `rho·||gradient||` 参考项解释，C6 实际预测更新按 `beta·rho·gradient` 复核。入口还核对准备快照 SHA、C6/C5/B 输入身份、runStart 与快照中的 cfg/opts（仅允许去掉首个 Plant marker），自然退出回执，以及 raw 内状态/参考/风/舵机样本和转移字段的维度、有限值、时间网格与初始状态连续性。

仅在根审核并串行放行后运行。运行成功后才以独占创建方式写入 `C6_FIRST_SCENE_RAW_REVIEW_v1.json` 与 `C6_FIRST_SCENE_METADATA_OS_REVIEW_v1.json`；首场 PASS 不构成 tail11 授权。此版 AST 解析通过；通过 AST 截取并执行 `decoder` 之前的 metadata/file-hash 断言前缀，所有断言通过。该预检只对文件计算 SHA，不解码 MAT payload、不读取 raw 数值、不评分、不写审计结果，也未启动 MATLAB。该入口不会访问 TEST。
