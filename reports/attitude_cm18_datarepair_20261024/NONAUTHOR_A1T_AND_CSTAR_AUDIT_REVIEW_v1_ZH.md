# A1T trainer 与 C* ALL816 audit 非作者复核

复核日期：2026-10-25。只读检查冻结 trainer `train_cm18_a1t_v1.py` SHA256 `2a5ea2ba6d0ccba1e0bf30a7d84f8a07723144fb44a070a63ca7fd6d68ade88b`、reader SHA256 `ced4251719f986d762f29ccced04fb80208a28e7aed1e2fe12d3b504955a4096`、ROOT auditor `root_audit_cstar_all816_v1.py` SHA256 `3b3a321da972801eb4c3f8e6630e68360c52bf89aba4dc387e80b5e9bcea5788`，并对照冻结 A1T taskbook、A1R normalizer/training约定。未执行 reader、self-check、训练、Plant、full audit，也未访问运行中的 relabel 会话输出。

未发现训练目标、模型输出尺度或事件时序方面的阻断。A1T 训练目标和 B VAL 选模均使用未限幅 raw target `c*/beta`；reader同时核验 `beta*raw=c*` 与 beta 后限幅目标。TRAIN用原序序列中 `0,5,...,1995` 的400行，float64/ddof=0重算目标轴RMS；输入 mean/std 复用冻结 A1R normalizer。验证使用全部1999事件，按每场 normalized score 等权平均，并以严格下降和最早平分规则选 best。事件时钟 `0.01..19.99 s`、plant index `11:10:19991`、beta公式和运行时 `clip→beta` 与任务书一致。

ROOT auditor 的 TRAIN stride 与目标 RMS 排列复现了原 A1 高级索引后的 C 连续布局。`G_column_major.reshape(1999,3,3,order='F')` 保留首维 event；逐事件 G 的恢复正确。此前对 reshape 的疑虑经小型数组索引验证已撤回。

一个非阻断的审计完整性遗漏：ROOT auditor 检查逐行 status/qualified 和文件哈希，但没有显式断言每行 `cache_schema`，也没有直接核顶层 `qualified_count`、`failed_count`、`split_counts`。A1T trainer 的 release gate 会核这些字段，因此不会绕过训练门；若 ROOT auditor 的 PASS 本身要独立证明 manifest schema/计数，可补这几项断言。其余物理闭合值来自已审核 MATLAB 执行，不由 Python 重算；脚本对此限制的说明准确。
