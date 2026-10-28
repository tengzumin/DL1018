# 主审：GHP7-balanced MLP15 首场闭环放行审核 v1

日期：2026-10-26（Asia/Shanghai）

## 审核结论

批准且仅批准 DL1018_GHP7_G1_W00 一次工程门航次。当前不放行其余五场、DEV72 或 TEST48。

## 已核验事实

- 冻结候选为 MLP15(13×15→64→32→3)，60000 步离线训练完成；MATLAB/PyTorch parity 最大绝对误差为 2.591743831e-7 rad/s²，低于 1e-5 容差。
- G3 两场是开发诊断 holdout，不是独立 TEST。离线误差门通过，但闭环收益尚未验证。
- 新候选仅替换姿态 RBF 输出：RBF 输出和更新关闭，MLP 权重冻结；输入为许可的 13 维量，不含惯量重建、Plant 真值或 observer。
- 新候选继续使用 C5 DSSM14/M110 位置环及同一 ACTIVE Plant/BS/allocator 构造；六场 no-Plant 预检的 position_options_sha256 全部相同。
- 六场预检保留 max_tilt=30° 与残差 dmax=[45,45,4.7124] rad/s²。这是已确认的共同 C5 条件，不是新候选单独加限幅。
- 本审核形成时 PowerShell 7 静态预检尚未执行；后续已通过，详见 STATIC_PREFLIGHT_GHP7_BALANCE_v1.json。MATLAB R2025b 六场 no-Plant 预检及四个新增 MATLAB 文件的 Code Analyzer 均通过，诊断为 0 项。
- 共用 C5 runner 的 52 个文件由原 source lock 固定；本候选使用其原闭环执行器，不复制或修改共用 runner。

## 工程审核与风险控制

已检查新绑定入口与共用 make_gate_holdout_options、姿态臂规格、MLP15 runtime step 及闭环函数的接口。模型形状、冻结推理路径、输入维数、共同位置身份和两项限值均与冻结任务书一致。为避免进程在启动 marker 落盘后意外中断而漏掉防重计数，入口现按 marker 本身识别已占用场景；残缺 marker 会 fail closed。

run wrapper 的 run_status.state=COMPLETED 表示 wrapper 返回，不等于稳定或安全通过。审核必须同时检查 raw 内的 log.status、safety_stop_reason、完整步数、可行性、限幅/饱和计数；工程首场通过后也只允许按续跑 release 执行。

## 首场后的硬门

G1/W00 必须 20000 transitions 完整、STABLE、无 safety stop、application_feasible=true，且 raw 中模型/输入/位置栈身份与任务书一致；记录倾角投影、残差 dmax、motor/generalized saturation 和耗时。失败仍保留航次与 raw，不重跑该场，不放行另外五场。

六场最终开发筛查门沿用任务书：宏平均位置 Q 严格优于 B 且不高于 C5 的 1.10 倍；宏平均 SO(3) RMSE 严格优于 B 和 C5；每场完整、稳定、无安全停止且应用可行。历史可行性逐场为：G2/W00 的 B 与 C5 均为 false；G2/W12 的 B 为 false、C5 为 true。必须原样披露；候选必须以自身 raw 证明可行，不能继承或改写历史状态。

GHP7 已用于之前候选筛查，因此即使六场通过也只支持开发晋级，不构成独立测试或论文泛化证据。



## 首次启动尝试记录

首次 MATLAB 启动在读取 Code Analyzer 报告时因相对目录错误失败，发生在 attempt marker 与 Plant 之前；输出根目录、marker 和 raw 均不存在，因此实际闭环/Plant 消耗为 0。错误已记录在 audits/PREPLANT_LAUNCH_FAILURE_v1.json，并已修正入口读取 audits 子目录。修正后重新运行 Code Analyzer、六场 no-Plant 预检和封存校验；仍使用原 G1/W00 唯一授权。

