# Round 1：冻结 W0 机制筛查主模型复核

日期：2026-10-22。审查者：主模型。范围：固定 12 场 VAL screen，X14；未访问 TEST。

## 完整性与可复现性

- 12/12 场有唯一 `attempt_01`，STABLE、20,000 transitions、W0 前后最大变化 0；48 个运行文件总计 560,781,729 bytes。无重试、失败或部分输出，闭环作业退出码 0。
- `run_start.mat` 与 `raw_run.mat` 在复核中未改变。W10 因航次后 `struct` 数组序列化错误缺失状态 sidecar；主模型仅从已验证 MAT 派生了带 `recovered_after_serialization_error=true` 标志的 sidecar。W10 运行秒数记录为30秒保守上界，不能当作精确 tic/toc；其余11场实测20.84–21.44秒，均值21.08秒。
- W10 的 `run_start.inputIdentity.frozen_inputs_sha256` 为 `e128c527cddcb81a42db9380775534b34d771e933e4bdaef7688ec78904cf1b6`；CONTINUE 的11个 run_start 一致绑定当时通过预检的 `13e4fc6da9a6ab4d4cdf81bcee978ca29a26d6e6c7ab5ee5018d7cc0dd9f5198`。后续追加审计记录会改变当前 lock，不回写历史 run_start。
- 12场 OFF raw 与冻结 B/ON 配对 reference 逐点一致（最大差≤1e-12 m）；原始输入身份复核通过。独立只读评分产生 `round1_screen_results.csv` 与 `round1_screen_summary.json`。

## 配对结果与预登记门槛

主指标为 0–20秒位置 Q，显示值以外全部按未舍入值比较。冻结权重 OFF 相对在线更新 ON：

| 组 | 场数 | ON 平均 Q | OFF 平均 Q | OFF−ON | Z RMSE 改善数 |
|---|---:|---:|---:|---:|---:|
| 高频 W09–W14 | 6 | 9.713 mm | 34.317 mm | +24.604 mm | 0/6 |
| 无风 W15 | 3 | 8.985 mm | 21.968 mm | +12.984 mm | — |
| 低风 W00–W08 | 3 | 10.736 mm | 33.829 mm | +23.093 mm | — |
| 全部12场 | 12 | 9.787 mm | 31.108 mm | +21.321 mm | — |

冻结权重屏幕的正式 gate **未通过**：高频组 OFF 没有改善、Z 轴0/6改善；低风与 W15 组退步都超过0.5 mm。保留全部数据，不将候选扩展到72场，不调参。现有在线候选相对 B 在该12场平均 Q 改善0.562 mm、7/12胜；高频 ON−B 为+0.080 mm（3/6胜），W15 为+0.356 mm（1/3胜）。这些12场数不能代替72场门槛。

W10单场的 B/ON/OFF Q 依次为8.517/8.694/29.993 mm，OFF−ON=+21.299 mm；单场仅作逐场复算，不作为单独组结论。

## 代码机制复核与下一步

私有 `run_dl1018_closed_loop.m` 在 FEATURE Head 分支中仅当 `stage1PositionUpdateEnabled=true` 时取学习方向：PCF 开启时使用 `clip(surface−eta_before)`，PCF 关闭时使用 `clip(surface)`；随后由 `position_only_search_head_step` 生成先输出、后更新的权重。更新关闭时走静态 Head 输出分支，PCF eta 即使继续更新也不会进入 Head 输出。故本轮是“启用/关闭自适应 W 更新”的总效应对照，不能区分 PCF 对学习方向的贡献；没有证据表明实现方程错配。

**主模型决定：结束 Round1，拒绝72场扩展。** 继续做一项且仅一项针对性 Round2：保持 DSSM14、FEATURE Head、W 更新、物理场景及其它选项不变，只将 `command_filter_coordination_v3_5.enabled` 从 true 改为 false，使在线更新由原始 surface 驱动；比较同一12场 PCF-on paired ON 与该 PCF-off 候选。目标是假设筛查：PCF 的 `eta` 扣除是否造成高频弱项。Round2 任务书和隔离代码仍须主模型审核；在审查通过前不启动航次。若 screen gate 不通过，保留 TEST，不继续扩72或调参。

该控制器消融本身不构成方法创新；理论 gate 仍未通过，尚无论文证据包达标结论。

## 后续源码分支复核与纠正（2026-10-22）

Round 2 任务书准备时，主模型最初把 DL1018 工作区内未锁定的 `position_stage1_update_head*.m` 误认为 R1 FEATURE 候选实际更新 helper。Luna 按冻结任务书做只读冲突检查后指出，该工作区 runner 不是原始运行器：正确的 R1 `run_dl1018_closed_loop.m` 来自已锁定的外部 `REFERENCE_FIX.../sources/local_runtime`。主模型随后重新逐行检查了这份锁定文件。

实际 `stage1SearchEnabled && stage1PositionUpdateEnabled` 分支先计算 PCF-on 的 `surface−eta_before` 或 PCF-off 的原始 `surface`，之后以相同 `[7,8,10]` 分轴限幅得到 `s_eff`，再调用 `position_only_search_head_step`。该 helper 的 SHA `3bd0fe9686c3b75793575e517d4cc5f08de58ab6a26a2bc7516aa690422bb7dc` 已在 R1 `frozen_inputs.json` 和运行源身份列表中锁定；PCF 离散 step `position_filter_realization_pcf_step_v3_5.m` 的 SHA `b4ae22db5bd444a162d0cd01a3a59a589f2e37077b089bb33693401b660228d0` 也已锁定。`position_stage1_update_head*.m` 位于 `stage1SearchEnabled=false` 的 fallback 分支，不是本候选配置实际调用的 helper。

因此先前“R1 漏锁活动更新 helper、存在历史源码 provenance 缺口”的判断已撤回。R1 的活动 FEATURE 更新 helper 身份已有锁；Round 2 仍需按该真实路径复核 `which()` 与哈希，但不应加入未调用 fallback helper 或据此声称历史数据身份不完整。Luna 未创建/修改代码或航次，发现后按任务书停止并上报；没有启动 MATLAB。
