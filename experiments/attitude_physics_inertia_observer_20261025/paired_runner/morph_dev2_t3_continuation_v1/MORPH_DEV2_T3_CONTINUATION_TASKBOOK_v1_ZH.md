# MORPH_DEV2 T3 单场续跑与runner修复任务书 v1

日期：2026-10-25；由root依据A02逐航次raw复核后批准**只实施隔离修复与静态审核**。当前未批准任何MATLAB/Plant航次；实际运行必须等待root审核冻结锁并签发新的独立release。

## 依据与范围

A02 attempt `MORPH_DEV2_20261025_A02` 已终止：T2 baseline/candidate两次真实闭环均返回STABLE和20,000 transitions，T3未运行。批次状态 `STOPPED_ON_FAILURE` 与candidate `FAILED_ENGINEERING` 原样保留。Root已独立复算两份raw并逐项审计20,000个candidate trace；发现本次停止由入口shape断言错误及results CSV调用错误造成，不是Plant停止或候选RBF打开。C02原始结果可用于后续配对汇总，但不得改写旧状态或复跑C02。

本任务只准备并审核**尚未运行的T3**：`DL1018_DEV_T3_C10_W11`，SQUARE、arm3/4主动变形、seed `2026123971`。复用已预检并封存的scene身份：spec SHA `56c29ea53ac1e8b1d261b5c88667b68a766ca77a128b32880be9d74c0c9fefba`，scene SHA `e06aa4dde902603f390554f4d8b022760b44a450b2c9868d68344d44ea5a809f`，metadata SHA `2bc2cafcd45c4ce2db4069b9f7477090f9c0851c30bdd304bde32e16a7073614`。

## 允许的最小工程修复

所有新实现放在本目录内，保留旧v1/v2入口、锁、A02数据和失败记录。仅允许修复已证实的两个**runner/reporting**缺陷，不改变控制器、候选、baseline、模型、场景、种子、dt、参数、position stack、BS、执行器或评分定义：

1. 修正RBF/trace形状校验：`attitude_fusion_rbf_output_enabled` 与 `attitude_fusion_rbf_update_enabled` 在MATLAB运行时返回单个运行级false标量；RBF三轴向量序列 `rbf_output_held`、`attitude_rbf_estimate_acceleration_rads2`、`attitude_rbf_compensation_torque_Nm` 在MATLAB wrapper直接收到的 `log` 中须严格为 N×3 且全零；`rbf_weight_norm/max/derivative_norm` 须为 N×1 且全零。说明：A02 v7.3 MAT经h5py/HDF5外部读取显示3×N及1×N，是存储维序呈现差异；不能把该方向用于MATLAB运行时断言。逐样本helper trace继续核验20,000个样本的因果时戳、morph command、omega、裁剪力矩、`estimateTorque=-tau_comp`、event/observer关系和RBF关闭。不要仅删除断言或降低到抽样检查。
2. 修正CSV writer所有`csv_metric`调用的参数数目；标量字段显式用`index=0`，向量字段按轴索引。部分失败也必须能落盘status、results CSV、report和failure receipt；任何`artifact_errors`均禁止COMPLETE receipt。

静态checker须锁定新wrapper、PowerShell 7 launcher、checker、任务书、状态文件，以及与A02一致的39个部署源码和17个既有输入。候选锁为NOT_FROZEN且执行授权false；root冻结与release分离。保留A02 evidence hashes作为前序配对结果元数据。新入口只能接受scope `MORPH_DEV2_T3_CONTINUATION`、一场T3和baseline→candidate顺序；拒绝旧release、已有attempt或未批准/改scope的release。

## 新release边界（root审核后才签发）

- 最多2次新runner调用：T3 baseline一次、candidate一次；共用同一scene对象；同一seed与起始状态配对。A02已消耗2次，本阶段合计不超过原计划4次。
- 禁止复跑C02、运行B、训练、TEST、DEV72、调参、换head、改变机制或扩展场景。性能升降均完整记录但不作为运行停止门槛；工程、完整性、安全或资源失败立即停止。
- candidate必须STABLE、20,000 transitions/20,001 states、无安全停止、motor saturation=0、generalized clipping=0、完整finite trace且RBF离线/在线开关和数值输出均为零。保存所有raw、run_start/status、scene audit、pair audit、CSV/report、命令、receipt和SHA。
- 本研究诊断阶段总输出上限2 GiB；A02 receipt已计 `487,834,198 bytes`。新continuation attempt上限 `1,650,000,000 bytes`，使累计不超过2 GiB并留出余量。C盘至少30 GiB；不足则不启动。不得删除/清理旧数据。
- 只用PowerShell 7；若出现已有MATLAB只等待其退出，不杀进程。一个MATLAB作业串行；不训练、不占GPU。attempt只启动一次；监测超时只轮询原进程，禁止重复启动。

## root放行门与后续

Luna xhigh只提交代码、candidate lock、静态审计、确切可复现命令，不得自行创建root release或启动MATLAB/Plant。Root独立检查代码、PowerShell解析、MATLAB `checkcode`、输入及scene hashes、CSV函数调用、所有冻结文件SHA和资源门槛；通过后root另写scope准确的release。运行后root从T3 raw独立复算，并把T2独立复核表与T3一起报告；任何负值、早晚段退化、轴向代价和不完整批次均保留。此续跑只回答第二个预登记应用域场景，不宣称论文证据包达标。
