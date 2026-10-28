# 增量动力学原论文与代码核查

2026-10-25，Root。只读文献核查；未安装或运行外部仓库，未改变当前诊断顺序。

## 实读来源

- Altawaitan / Atanasov，[Adapting Neural Robot Dynamics on the Fly for Predictive Control，arXiv v2](https://arxiv.org/html/2604.04039v2)，版本日期 2026-09-05；核查摘要、§IV-A、§IV-B。
- [作者项目页](https://altwaitan.github.io/on_the_fly/)明确链接[官方仓库](https://github.com/ExistentialRobotics/erl_on_the_fly)。GitHub API 核定 main 为 `b158cb80e5dde5a792dc204d66ef19c041a8a903`，提交日期 2026-04-10。仓库提交早于论文 v2，不能假定两者逐项一致。
- 实读该提交 [learner_ddp.cpp](https://github.com/ExistentialRobotics/erl_on_the_fly/blob/b158cb80e5dde5a792dc204d66ef19c041a8a903/agilib/src/controller/ddp/learner_ddp.cpp) 的 `setFromBuffer`、`nominalRollout`、`run`，未声称审核整个控制器。

## 核查结果与适用边界

论文采用增量状态模型、多步预测损失和低秩在线参数适应；其姿态增量在四元数流形上构造。这与当前固定权重 CM18 的瞬时角加速度补偿目标不同，不是可直接替换的模块。论文不能证明本项目的高频退化原因，也不能证明应立即采用在线适应。

代码中 `setFromBuffer` 按环形缓存时间顺序取状态/动作；`nominalRollout` 从记录初态出发，依次用预测状态与记录动作推进预测，并分别加权位置、姿态、速度和角速度误差。`run` 记录更新前后预测指标并发布待应用参数。这里的预测轨迹误差仍不等同于真实闭环跟踪成绩。

Root 判断：该工作提供了“瞬时拟合指标之外还应核查时间累积误差”的原始依据，但不构成当前换模型或重训的放行理由。先完成已批准的同状态 fit / clip / hold 分解；若仍需研究时间累积误差，应另行冻结包含因果时序、训练输入身份和闭环验收的任务书。保留位置环 C5、姿态 RBF 替换范围及主动变形应用主线。

本次只产生文献记录：新增 Plant、训练、optimizer、TEST 访问均为零；不宣称复现、跨平台运行或全源码审计。
