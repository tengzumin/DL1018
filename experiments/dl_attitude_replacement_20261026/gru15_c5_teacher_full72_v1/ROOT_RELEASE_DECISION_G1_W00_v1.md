# 主审决定：放行 GRU15 G1/W00 工程门

日期：2026-10-26

## 已核验

- GRU15 full72 训练收据为 PASS：seed `2026102001`、60,000 steps、72 个 C5-RBF 开发场景、143,928 个事件；训练未调用 Plant 或读取 TEST48。
- 冻结权重 SHA-256：`cea74bb1f178b4716f9d10780bd643269703c0583479c2e6430998aecafea11c`。MATLAB parity PASS，runtime-step 最大误差 `2.04530072e-7 rad/s²`，低于 `1e-5` 容差。
- G1/W00 no-Plant 准备通过；13 维输入与 15 事件因果窗口符合白名单。`Jhat/Jdot_hat`、质量/惯量属性、Plant 真值、RBF 权重/隐状态、observer 与物理前馈均不进入模型输入；姿态 RBF 输出与在线更新关闭。
- MATLAB Code Analyzer 对新增/改动的小型 MATLAB 文件为 0 diagnostics；对大 runner 与 MLP full72 隔离基线逐 ID 对照，无新增诊断。
- 候选与复用 B/C5 同用已绑定的 C5 DSSM14/M110 位置环、Plant、执行器、倾角投影 30° 和姿态残差 `dmax=[45,45,4.7124] rad/s²`。B/C5 历史 raw 只读复用，不重跑。
- payload manifest、baseline reuse manifest、C5 输入锁、位置模型、场景和 `R_task` 身份检查均通过；TEST48 未读取。

## 决定

放行 **一次** G1/W00 ACTIVE 候选 Plant 航次，结果写入新的 `pilot_runs_gru15_c5_full72_v1`。本次不放行其余五场；首场 raw、状态、安全字段、因果 trace 和配对身份经主审复核后，再更新 release 继续筛查。失败航次和 marker 均保留，不重跑同场冒充新结果。
