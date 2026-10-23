# C4 源码与无 Plant 入口（CODE_READY）

本轮只完成隔离源码、固定输入锁、No-Plant 准备入口和单场 release-gated runner。没有启动 MATLAB、Plant、训练或 TEST。任务书 SHA-256 为 `a785c5289244dcb41eb3ad6d23b8873a2e4dbbaca9f3b1d2b723a0823dc78ab5`。

C4 core 从冻结 C3 core 单独复制；helper 与 wrapper 保持原 SHA。改动只落在坐标因子契约、`s−mη` 跟踪坐标、因果参考积分/目标与独立日志。m=1 分支沿用原 `a_f` 累积和目标运算顺序，m=0 分支累积 `a_req`；保留独立的 `a_f` 积分日志、`a_req/a_f/r_f/eta`、事件前后权重和已 clip 坐标面。

- C4 core：`cec0d688226123a9b9f14e2a215f283e1ef859caa8371ac2b764d3b1c2bcc878`
- helper：`48feebf934b8eb90b4424f2286aa857c48213d229714f30af99aacf53329549d`
- 输入锁：`318bdaee3533c908da45140bcc2fef4e2ddb01e0fe63158c24057bde6bfdbd39`（32 项，31 个 `.m`、1 个 `.mat`；12 场顺序与任务书一致；锁本身不授予 Plant）
- 准备入口：`1e940ef58967aca7e371f4d53998a6890c5ae0535ca3d2df19fdc5c3eb27be14`
- 单场 runner：`53fed7e5f9fcb38ecae415429051c2cd26cce6e20a50fa57d8d30e8d432eb1ad`
- 锁构造器：`77d16060a21756dd057241ce3d36c17c72472c154812098cb0cbbbbe6653da3a`
- 合成检查脚本：`a058f33520a9a5c7aab9069fd60a1477646e3be00696b783ea3b9ea25b725c2a`

准备入口重建 C3 cfg/opts 并要求唯一新增语义字段 `position_coordinate_m=0`；核对 DSSM14 seed/step/W0/normalizer 身份、C3 固定 12 场 B/C3 身份、32 项实际 `which` 及 `checkcode`，写入单独的 cfg/opts 快照。它不加载旧 C3 raw MAT。runner 只接受精确绑定 `T2_C00_W10` 的首场 release，检查共享重仿真锁、资源与预算、输入身份，并在任一失败后保留证据且不重试。

无 Plant 合成检查采用确定性 1 kHz 数组：n=320 首次 ready 时无历史；n=330 目标仅用 `[320,330)` 十个已完成转移并配 `phi_320`。m=1 用原 `a_f` 累积与 `s−η`，逐项比较旧 C3 helper 输出、延迟梯度和联合投影；m=0 用独立 `a_req` 前缀积分经纯 Python delayed-prediction kernel 复算。另把 n=330 的请求量改成大哨兵，确认目标不变，并检查读出使用 `W_330`、更新得到 `W_331`。脚本已准备但本轮未执行。

当前仍未执行 MATLAB `checkcode` 或 No-Plant MATLAB 准备，因此没有 MATLAB PASS/退出码证据。后续必须分别记录 MATLAB 计算结果与 PowerShell 观察到的真实 OS 退出；不能用 stdout 的 PASS 文本推断 OS 退出成功。MATLAB 命令按主审要求使用绝对工作目录和单层 PowerShell 7 调用，不重复尝试退出参数。
