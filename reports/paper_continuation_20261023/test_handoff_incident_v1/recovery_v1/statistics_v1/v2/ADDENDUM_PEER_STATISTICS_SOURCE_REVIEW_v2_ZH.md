# Recovery288 统计器 receipt 类型修复补充审查

当前源码：statistics_v1/test48_statistics_recovery288_v1.py，SHA-256 9569179af549c94ccf40315483234dd176bfabeb58524810fbf59a4982aa3d8b。本补充针对前版 535a14ef2593dad33a564a4fddfce1ecf776fbcd8e0d6e6a8df453c861fee866 审查报告中的 receipt 整数类型发现。

statistics_v1 当前未保留 535a 源码副本，因此无法重建完整字节级 diff；本次只核对前版报告指出的比较点与新源码对应的修复和负例，不重复整篇统计器审查。

确认四个 receipt 字段均在值比较前要求 type(value) is int：block_index、matlab_os_exit_code、training_steps、optimizer_steps。这会拒绝 bool 冒充 int。recovery_schema_self_check 明确包含四个对应负例：boolean_block_index、boolean_os_exit_code、boolean_training_steps、boolean_optimizer_steps。静态计数确认当前自检共有23个 must_reject 用例。根另行报告已对该 SHA 运行 guarded 23负例和 synthetic analyze，全部通过；21个数值区及旧计算前缀 AST 核对也通过。本次独立检查未运行自检或正式 CLI。

该修复解决前版 P2 类型缺口；本次局部检查未发现新增阻断问题。未读取 TEST raw 或成绩，未运行 MATLAB/正式 CLI，也未改源码。
