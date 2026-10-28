# C5 VAL48：完整认证通过

2026-10-25，Root。Root 阅读 v2/v3 完整差异后放行单条旧格式补证及 47 条缓存复用。入口 `reports/attitude_position_context_probe_20261024/certify_and_export_c5_val48_v3.m`，SHA `0a87b61fd8b4933e30a3d7fd7e8f33b6a567ed05c247a0739e173a78ed67b47e`。

实际 session 79700，MATLAB OS0，`C5_VAL48_V3_STATUS=PASS`。47 个缓存逐个重新核 SHA/bytes 和内容身份后引用，只有 T2_C00_W10 新导出。该条旧 run_start 缺摘要，但完整 runtime model（含 normalizer）、head W0、runtime weight 与 snapshot 精确一致，raw 初始位置权重也逐元素一致、差为零。并未跳过身份门。

最终 manifest：`c5_val48_c5_teacher_v3/C5_VAL48_EVENT_CACHE_MANIFEST_v3.json`，SHA `3e72f4726219cfd0e89476c70d24796a06c8f8447d4064cfdc471433a863a501`。48 场全 PASS，缓存总计 9,576,036 bytes，全部 VAL-only。历史 v1/v2 失败结果原样保留。

Root 另用独立 SciPy 入口实际读取全部 48 份缓存，核 SHA、bytes、来源身份、旧格式补证标志、数据类型、数组维度、完整 95,952 事件的 index/time/phase 与闭合数值，实际 OS0。证据 `ROOT_C5_VAL48_CACHE_INDEPENDENT_AUDIT_v3.json`。

本次只是已有教师轨迹的认证与提取，0 新 Plant、0 optimizer、0 TEST，不是新姿态候选的性能结果。这 48 场不进入 TRAIN，也不能称为新的独立测试。

运行时另有 Root 的 REST268 离线重建；两者均无 Plant/训练或正式控制耗时测量，短时并行不涉及实验重启。应用户资源授权，仅将已核 PID/command line 的 REST268 MATLAB worker 12928 优先级从 Normal 提至 AboveNormal；没有终止或改变其数值协议。
