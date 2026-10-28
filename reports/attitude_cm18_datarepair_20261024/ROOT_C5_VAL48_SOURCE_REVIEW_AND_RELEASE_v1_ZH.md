# C5 VAL48 离线认证：源码审核与放行

2026-10-25，Root。依据已冻结的 `ROOT_C5_VAL48_REUSE_EXPORT_ADDENDUM_v1_ZH.md`。

实际入口为 `reports/attitude_position_context_probe_20261024/certify_and_export_c5_val48_v1.m`，不是 experiments 下的计划路径；功能范围相同。Root 已读全文及后续改动。冻结 SHA256：`6aa38f592653666bea09f4a1be7b6576c454c5689d662beefabaa736c506dfa4`。

审核修正：补上 raw 日志首个姿态 RBF 权重全零检查、30 GiB 空间门和合计数据预算；合计预算路径已修正为实际 `data/events/attitude_cm18_datarepair_20261024`，不能漏计 B 参考修复缓存。Root 核对新 SHA 后实际启动。checkcode 报 10 条静态警告，无已知解析错误。

放行一次对现有 48 场 VAL 的只读认证及小型缓存提取。禁止 Plant、训练和 TEST；历史文件不修改。Root 持有 session 91339。stdout 必须最终 `C5_VAL48_STATUS=PASS` 且外层 assert/退出码通过；仅进程退出或文件存在均不足以通过。失败记录保留，不自动覆盖重跑。

这不是新姿态模型实验。旧 RBF 教师日志只用作数据与基准；后续姿态替代候选部署必须关闭原姿态 RBF 输出和更新，不能把保留 RBF 的探针误称为替代效果。
