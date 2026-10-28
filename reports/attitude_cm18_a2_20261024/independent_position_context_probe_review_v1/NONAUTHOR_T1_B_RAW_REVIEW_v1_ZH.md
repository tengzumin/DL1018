# 非作者复核：T1_B attempt_02 raw

结论：T1_B attempt_02 的身份与运行账本一致，Root 原始数据审计为 PASS；未见时序或安全阻断。本复核只读取现成 JSON 与文件身份，没有运行 Plant。

- `run_status.json` 为 `RUN_COMPLETE_STABLE`，固定 T1_B / B_POSITION_RBF / attempt 2；记录 20,000 transitions、20,001 states、1 次 Plant、0 training/optimizer steps、未访问 TEST，`safety_stop_reason` 为空。
- status 记录的 raw SHA 与文件实际 SHA 相同：`e44d75f8fb784ed30f7b72057fda2183ad09c9286271b8db15cc3f5aeafd830a`。Root release 的 status SHA、文件 SHA 相同：`b770618d897463b779f60b97d5ace24cd128f776b8aff91445e67843a41806dd`；release attempt_id=2，其 v2 runner pin 与当前 runner SHA `f4e904c428c1c2f9cf778a172dd2bf46c5765990b62d195c365a2c3b90727699` 相同。
- `ROOT_T1_B_RAW_AUDIT_v1.json` 为 PASS，记录源 scene 完全一致、cfg/opts 除 Plant marker 外一致、1999 attitude events、1999 position-RBF events、两路首事件 `W_before` 为零、motor saturated steps=0、generalized clipped steps=0。该审计文件 SHA-256：`6bfcb20cad451d25bcbb12a71ec04921028085322fe48d7ea87c0b3b3f7ddeb0`（去空格即 SHA-256）。
- 先前 attempt_01 的 `FAILED_NO_RETRY` 记录仍保留，并确认无 raw、无 first-Plant marker；attempt_02 使用独立目录，未覆盖失败账本。

范围：scene/config、完整事件阵列等数值由 Root 的 MATLAB raw audit 报告给出；本非作者复核独立交叉核对其 PASS 状态、attempt/release/raw 身份哈希及运行摘要，不声称重新计算完整 MATLAB 物理指标。

