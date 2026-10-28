# B_REF_REPAIRED：剩余 268 场离线重建放行

2026-10-25，Root。SCREEN4 MATLAB 实际 session 37307、OS0，四条 PASS。Root 用独立 SciPy 入口实际读取四份缓存，核 SHA/bytes、corrected 与 original raw 身份区分、split、X18/target 浮点精度、整数 index、event time、phase 及闭合值，7996 事件全部通过。证据 `ROOT_REFERENCE_REPAIRED_SCREEN4_CACHE_AUDIT_v1.json`，不只依据导出器的 PASS。

因此依原任务书放行 REST268，保持同一源码、source manifest 和提取函数，不重导首四场。source manifest SHA `0f86b47d01940e7b556b78a9664470531572809aa6857a59fc77d88a33681ec5`；exporter SHA `eedd6f2299f31349d63f090c00f42513e33d686ac9bfa337bb45f799ab86dc03`。

0 Plant、0 optimizer、0 TEST，独立输出 `export_rest268_v1`。必须保留任何失败并停止，不自动修改重跑；全部缓存及 544 条原缓存须另行合并认证后，才能批准训练。C5 VAL 的单条旧格式补证是另一任务，不影响这里的 source 身份。
