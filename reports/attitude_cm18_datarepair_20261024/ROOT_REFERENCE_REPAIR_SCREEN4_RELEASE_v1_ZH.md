# B_REF_REPAIRED：首四场离线导出放行

2026-10-25，Root。依据已冻结 `ROOT_REFERENCE_REPAIR_DATA_TASKBOOK_v1_ZH.md`，仅离线导出，无 Plant/optimizer/TEST。

Root 已读取两入口全文及修正：统一 JSON scene 字段以保证 MATLAB struct 解码、嵌套身份字段引用、真实 G3/PILOT6/VAL MAT 格式、81×3 姿态首权重审计、实际初态、完整 cfg/B opts、参考与 log 一致性及合计空间门。

metadata 第一次实际启动因 C5 input-lock 的硬编码 SHA 抄写顺序错误退出，未生成缓存或 manifest。失败源码已保存在 `metadata_attempt01_sources`，原件与被锁输入没有变化。实际文件正确 SHA 是 `82024c01276cc4bfbd9b7772cf5332dee3fdfcbed422969589b68f1c90ed2d75`。

当前冻结源：

- prepare：`22c164946375541a18425d06056b35a01c6f3a639bf8e0e7596ba04ef71cb315`
- exporter：`eedd6f2299f31349d63f090c00f42513e33d686ac9bfa337bb45f799ab86dc03`
- source manifest：`0f86b47d01940e7b556b78a9664470531572809aa6857a59fc77d88a33681ec5`

Python metadata 实际退出 0。Root 独立核 816 场顺序与原 A1 完全一致、768 TRAIN/48 VAL、544 复用/272 重建、T2 全为真实 corrected B、全部 source 文件 SHA 与统一行结构，通过 `ROOT_SOURCE_MAPPING_AUDIT_v1.json`。这只是来源映射资格，不能代替缓存认证。

Root 实际启动 MATLAB SCREEN4，session 37307。固定顺序为 TRAIN T2_C00_W00、TRAIN T2_C15_W14、VAL T2_C00_W10、VAL T2_C15_W09。必须读取实际四份缓存和身份/物理闭合收据后再决定 REST268。不得只凭文件数或 exit0 扩展。
