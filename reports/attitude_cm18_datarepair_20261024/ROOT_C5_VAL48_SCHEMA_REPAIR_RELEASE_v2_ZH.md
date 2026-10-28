# C5 VAL48 离线认证：一次有原因的格式修复重试

2026-10-25，Root。v1 实际 session 91339、OS1，48 场未通过、0 缓存。历史结果与源文件保留。实际失败均为认证器的格式假设，不是新候选的闭环结果。

独立只读诊断 `ROOT_VAL48_ATTEMPT01_SCHEMA_DIAGNOSTIC_v1.json` 查明：36 个新运行的父审计 rows 是异构 cell；11 个复用运行的权重审计只保存前八次快照（总事件仍是 1999）；唯一 T2_C00_W10 的旧 status 不含 physical source SHA，但冻结 run_start 的 scene_raw_sha256 记录同一物理 B 原件。Root 另用 h5py 实际确认三类代表 raw 的审计维度及 .01 至 .08 s 时间。

Root 阅读 v1/v2 完整差异后，放行 `reports/attitude_position_context_probe_20261024/certify_and_export_c5_val48_v2.m`，SHA256 `321eda74a475757d6f0806f130c47a9d9c4ff4878f598470eede07b178cf2895`，独立输出目录 `c5_val48_c5_teacher_v2`。只修正上述三项；旧字段补证仅限固定场景与已锁 schema，且继续核同一 raw 的父审计身份，不降低身份要求。

实际 Root session 91665。外层 assert 要求最终 manifest PASS；无 Plant、训练或 TEST。认证器的 PASS 仅支持缓存复用资格，不代表姿态 RBF 已成功替换。最终资源合计还需 Root 对整个 datarepair 目录复算，不能只依赖认证器的局部计数。
