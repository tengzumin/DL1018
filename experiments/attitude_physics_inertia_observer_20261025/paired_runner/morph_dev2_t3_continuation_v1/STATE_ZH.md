# T3 continuation entry 状态

- 当前状态：准备隔离入口与静态审计；候选锁将保持 `NOT_FROZEN`，root 尚未签发本入口 release。
- 场景唯一限定为 `DL1018_DEV_T3_C10_W11` / seed `2026123971`，执行顺序为 baseline → candidate，最多2次 runner 调用。
- 新attempt产物上限 `1,650,000,000 bytes`；启动前要求 C 盘可用空间至少30 GiB。已有attempt一律拒绝续跑或覆盖。
- MATLAB运行端直接返回的向量日志严格检查为 N×3、权重标量日志为 N×1；A02 v7.3 MAT由 h5py/HDF5外部读取显示3×N/1×N属于存储维序呈现差异。
- candidate仍需完整20,000样本trace、STABLE、零安全停止、零饱和与裁剪、RBF关闭且数值全零。性能及早晚段差值记录，但不作为停止条件。
- C02/A02及39个部署源码、17个既有输入保持冻结；前序A02 root review和raw manifest只作为配对元数据锁定。
- 失败状态、部分raw、CSV、报告及receipt需保留；任何`artifact_errors`或缺失状态/报告都不得出COMPLETE receipt。
- 静态checker只做PS7解析、源/输入/证据SHA和文本契约审核，不调用MATLAB、Plant、TEST或训练。
