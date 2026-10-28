# MORPH_DEV2_DIAGNOSTIC 隔离入口状态

截至 2026-10-25：本目录仅含新诊断 wrapper/launcher 与 PS7 静态审计材料。范围为 T2、T3 两场，每场 baseline→candidate，最多 4 次 runner 调用；C00 旧筛查失败保持原判据和原结果。

本地候选锁状态为 `NOT_FROZEN`，root 尚未审核或冻结，root-approved release 尚未签发。不得通过本目录启动 MATLAB/Plant、训练、TEST 或重试。

`source_lock_morph_dev2_diagnostic_v1_candidate.json` 与 `MORPH_DEV2_DIAGNOSTIC_STATIC_AUDIT_v1.json` 是早期静态结果，因后续入口修订已过时，保留作审计历史，不可冻结。当前结果由 v2 候选锁和 v2 静态审计提供。

判定规则：完整记录所有性能正负结果；性能变化不阻止第二场。只有工程/安全失败停止后续场；candidate 必须 STABLE、20000 transitions、20001 states、无安全停止、motor saturation=0、generalized clipping=0。Q、SO(3)、tilt、2.2 s 分段和耗时均报告。
