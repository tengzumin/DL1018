# D0 当前状态

- 时间：2026-10-19T08:28:21.297343+00:00
- DL1018：HEAD `12bce70c5f69fd5055bc6cf798303cf2c6d80050`，分支 `main`；受跟踪文件工作树清洁：`True`。
- DL1009：`3671d2d212af927abdb6d9149a1b249c372ac55e` / `codex/kan-position-repair-code`；只读参考，工作区含未提交变化（未清理、未修改）。
- 原运行状态：G06_P_DEV；G06 的 `STOP_POSITION_NOT_QUALIFIED` 保持不变。
- 原台账：2137 attempt 行，2064 episode 行。G04 报告为 PASS，432/432 稳定验收；这只代表航次可用，不代表 Student 胜过 B。
- D1 配对范围固定为全部 G04 TRAIN384 + VAL48，每场精确连接 B、POS_OFF、P_INIT_STUDENT；缺失时报告，不补采。
- 运行环境与原始小文件 SHA-256 在 `manifests/SOURCE_AND_PROTECTION.json`。
- 新增资源：Plant 0，fit 0。当前无主流水线启动授权；只做离线分析。
