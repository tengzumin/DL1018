# REPAIR03 C5_VAL48 离线评分结果

- 执行命令：`conda run -n TCN0906 python experiments/dl_attitude_replacement_20261027/mlp15_nominal_residual_v1/C5_VAL48_OFFLINE_DIAGNOSTIC_REPAIR03/score_c5_val48_once_REPAIR03_v1.py`；退出码 `0`。
- 冻结身份预检通过：48 场、144 个身份文件；VAL raw/status/run_start 字节哈希全部匹配。checkpoint SHA-256 为 `9c924f1566447644287595253026e035b2fcb716a57be0e60d6f04bafdd8ed74`；冻结 scorer SHA-256 为 `432d989f9e729898f80b551ccb943e80e7a701889c07d3b12c30d6831cd7bf8c`。
- 48/48 场、95,952 个事件完成因果门和离线评分。逐场宏平均残差 RMSE：候选 `4.778399 rad/s²`，零补偿基线 `6.957267 rad/s²`。按轴 pooled RMSE（roll/pitch/yaw）：候选 `6.767487 / 6.602727 / 0.663595`，零补偿 `8.258491 / 10.384244 / 0.740177 rad/s²`。
- 训练、TEST、Plant 和闭环均未运行。分数衡量 C5_VAL48 上对物理残差标签的离线预测误差；不能解释为姿态跟踪或位置闭环指标，也不是独立 TEST 证据。

## 输出

- [评分结果](C5_VAL48_SCORE_RESULT_v1.json)
- [评分摘要](C5_VAL48_SCORE_SUMMARY_v1.json)
- [单次评分收据](C5_VAL48_DIAGNOSTIC_RECEIPT_v1.json)
- [REPAIR03 执行收据](REPAIR03_EXECUTION_RECEIPT_v1.json)
- [因果检查](VAL_CAUSAL_GATE_v1.json)
