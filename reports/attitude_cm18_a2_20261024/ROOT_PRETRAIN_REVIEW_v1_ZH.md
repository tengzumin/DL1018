# Root 正式训练前审核

决定：批准 A2 一次固定60000步正式训练；release SHA256 da2d803c612701ec0078855efe468660102a82d99d6a0b81a4a10aa073c66532。尚未批准闭环/TEST。

Root已读取NumPy/Torch双前向实现及检查脚本，并逐项对照A1 trainer unified diff。采样、TRAIN-only尺度、优化器、损失、VAL频率、严格最早最佳选择及主训练循环未改变；差异为A2模型、身份/目录和冻结任务书门。共享权重两前向整体作为一个处理因素，不归因为独立yaw头；计算成本需另测。

真实验证：CPU v2合成/初始模型检查PASS；MATLAB R2025b实际batch OS0 PASS，输出shape1×3、coeff3×8、basis1×8、零基底与偏航扰动不变、Python一致性通过；实际RTX3070 CUDA0 float32零步OS0 PASS，loss/grad有限，梯度分解最大差2.98e-8，偏航对raw alphaXY梯度精确0，backward前后state_dict未变。这里只验证未训练模型，不替代实际训练后parity。

审核拦住且已修复：MATLAB列向量乘行尺度的隐式3×3扩维；JSON向量行列契约；finite检查可能漏NaN；SHA字节应typecast而非int8饱和转换。CPU v1的batch_single_exact元数据强于实际检查，以v2容差口径为准。CPU v2中的MATLAB checker SHA早于最后字节修正，实际MATLAB结果/OS回执单独核验最终SHA，不伪称所有v2文件身份仍全相同。

真实CUDA检查使用A1全部TRAIN的canonical初值/尺度，并从两场SCREEN4 TRAIN合并选64活跃行；不是重新拟合SCREEN4。静态C00没有活跃形态行，不能要求每场32行。检查未创建优化器、未训练、未调用Plant。

GPU当前进程行均属于此前已审核的Windows桌面/WDDM基线子集，启动前GPU利用率0%；未发现另一研究训练进程。不是安静环境实时性能测试。训练器仍独立检查GPU新增进程与利用率、磁盘、数据/source身份和唯一输出目录。

启动由Root持有session54707。后续只轮询该句柄，不因观察超时重启；训练自然结束后先看真实receipt/全部VAL历史/选模与模型身份，再独立复算48VAL并执行训练后跨语言parity。未通过结果前冻结门则否定/诊断，不扩步数或改阈值。论文目标仍未达标。
