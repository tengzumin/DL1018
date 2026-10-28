# 首次 FILE_SHARE_DELETE 测试失败记录

- 实际运行命令：`python reports/attitude_cm18_a2_20261024/retry1_tinyfixture_v1/check_windows_replace_retry_v1.py --repo-root <repo-root>`。
- 运行结果：OS1。短锁和长锁检查已先通过；第三项错误假设“FILE_SHARE_DELETE 活句柄下 Path.replace 可立即替换”导致测试退出。
- 真实错误：`PermissionError: [WinError 5] Access is denied`，调用链为 `check_windows_replace_retry_v1.py` → retry trainer `_write_json` → `Path.replace` / `os.replace`。
- 保留的fixture目录：`case_20261024T135225_4850d381`，含短锁、长锁原目标及失败的 `.tmp`，以及 `share_delete.json`。
- 该结果被保留为失败事实。隔离复测确认 native `ReplaceFileW` 与 `os.replace` 的差异后，按 ROOT 决定不切 writer API；v2 改为 FILE_SHARE_DELETE 活句柄持有约150ms后释放，并验证持锁期间 WinError 5 后重试成功。