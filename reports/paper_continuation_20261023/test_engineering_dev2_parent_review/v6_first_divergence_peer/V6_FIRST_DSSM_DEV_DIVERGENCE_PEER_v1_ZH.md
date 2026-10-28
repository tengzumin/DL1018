# v6 DSSM 工程复现首分叉独立复核

结论：**全轨迹复现失败由运行前模型身份不一致解释；不是 PCF 首次分叉，也不是可以归为浮点舍入的误差。** 本复核只读 v3 清单指向的历史 DEV 文件和 v6 的一个工程 DEV raw；没有读取 TEST 结果、运行 MATLAB/Plant、训练或重试。根记录本次自然 OS1、1 次 Plant，KAN 尚未启动。

历史 `run_start.mat` SHA 为 `1b6417…6986cde`，历史 `raw_run.mat` SHA 为 `e54111…1878c8d8`；v6 `run_start.mat` SHA 为 `65915d…87b5c13`，新 raw SHA 为 `c33050…fc51fa81`，均与清单/任务给定身份相符。详见同目录 JSON 的完整路径、SHA 和逐数组摘要；审计脚本只扫描 377 个数值日志数组（排除四项 wall-timer），308 个完全相同、69 个不同，无形状或 dtype 不一致。

分叉链条如下：

| 时点 / 对象 | 直接复核结果 |
|---|---|
| 启动前模型 | 旧、新 `output_W`/搜索头 W0 最大差 `0.4603508599`；旧 W0 的 float64 列主序 SHA 为 `8a0674…cccc5c`，新 W0 与当前锁定模型一致，SHA `88f8c4…a2cf53`。除 W0 外，DSSM 的 `input_W/input_b/input_mu/input_sigma/ssm_tau/project_W/project_b` 也全不同；模型 ID、架构、seed、selected step 等元数据相同。 |
| 首次 ready 推理，调用时刻 `t=0.320 s` | 该次推理使用的 32 个 X14 历史列逐值相同；截至调用样本的物理 state 也相同。两份记录的 33D 编码特征最大差 `0.0148046185`。按锁定 DSSM 前向公式独立用同一历史窗复算，分别以 `3.51e-17` 与 `2.78e-17` 最大误差吻合旧、新记录，确认编码差来自所载模型参数。 |
| 同一调用的头输出 / PCF | `FEATURE` 头 raw 输出旧 `[-0.0194020,-0.0811014,0.00218157]`、新 `[-0.00945315,-0.0791043,0.00356660]`。交叉代入 W0 与编码输出，只有旧 W0+旧编码、新 W0+新编码分别重现各自 raw，说明两项身份差都参与输出差。头部的 PCF 坐标输入、beta、事件间隔和 filter 前 eta 完全相同；头 applied 输出最大差 `0.00176869 m/s²`，随后 PCF `a_req/r_f/a_f/eta_after` 分别差 `0.00176869/0.00176864/0.00025011/1.7651e-6`。因此 PCF 差异是上游头输出后的传播，当前证据不指向 PCF helper。 |
| 物理响应 | `state` 首个数值不等于零的样本差在 `t=0.321 s`，为 `4.95e-14`；首个超过 `1e-12` 的差在 `t=0.323 s`，为 `2.15e-12`；全程最大差 `0.1314036215`。 |

代码锚点支持因果顺序：v6 的 [test48_entry_v4.m](../../../../experiments/c5_test48_v6/test48_entry_v4.m:503) 从历史 `old.opts` 起步后，在 503–517 行以当前锁定 `model.mat` 覆盖 `stage1_position_runtime.model`、`weight` 与搜索头 `W0`。运行核先由 666–681 行从这些 opts 取初始权重；1979–1988 行形成 X14 历史并调用模型前向；2028–2103 行完成头输出/更新并将 applied 输出变成 held force；2228–2235 行再将该命令送入 PCF。模型前向和头公式见锁定 helper 的 `position_stage1_model_forward_v2.m:54–64,136`、`position_only_search_head_step.m:12–18`。

最小后续核验不是再跑 144 个 DEV：在任何新块启动前，先决定论文/TEST 对 DSSM/KAN 的定义究竟要忠实复现历史 DEV 内嵌模型，还是采用当前外部 `model.mat` 锁定版。若要求历史复现，应将历史 `run_start.opts.stage1_position_runtime.model`（完整模型数组）、初始 `weight`、head `W0` 作为明确的新模型身份冻结，并先做不启 Plant 的字段级 SHA/opts 等同性检查；不能继续声称符合当前 `model.mat`/W0 SHA。若保留当前外部模型锁，则这次 raw 只能标作身份不等价的工程诊断，不能作为历史 raw 的数值复现。已完成的失败尝试应保留且排除于正式结果，不自动重试。

恢复历史 D/K 模型**在执行顺序上仍可与尚未启动的五个 TEST 方法块兼容**：B48 已经生成但分数未读，若仅重发未启动块的新冻结 release、保持同一批 48 个输入及物理设置并明确记录 B 的旧 release 身份，尚未发生方法间结果查看或参数选择；但它会改变 D/K 的冻结模型身份，必须另行版本化，当前 v6 release 不可沿用该身份继续运行。恢复后 D/K 与 C5 的特征/初始化表征差异仍须披露。这样的整体性能比较可作为方法包比较；若要把 C5 相对历史 D/K 的差值因果归于控制机制，仍需相同表征与初始化、只改变指定控制机制的配对证据。现有 C5 内部的冻结/去延迟预测消融可支持各自受限的内部对照，不证明 D/K→C5 的跨模型机制因果效应；这不意味着为本次身份问题补跑 144 个 DEV。

可机读复算：`V6_FIRST_DSSM_DEV_DIVERGENCE_PEER_v1.json`；执行器：`diagnose_v6_first_divergence.py`。数值逐数组复核排除了 `controller_call_time_s`、`network_call_time_s`、`stage1_position_inference_time_s`、`stage1_position_event_inference_time_s` 四个 wall-timer。
