# 父审删除决定

用户已明确授权清理之前/废弃实验的MAT，且只能在当前DL1018目录内删除。阶段1要求找到字面ABANDONED状态过于保守；COMPLETE只说明曾完成，不代表当前仍在使用。本次父审基于当前27份数据/模型/评测来源索引、已完成状态与正在执行的正确参考FULL72/修正训练144格方案，指定以下历史轨迹输出为用户所称之前实验中不再使用的部分：

- gru14_dssm14_student_refine_v1 的dev24、student_raw：665个MAT，16,291,979,129 bytes。
- kan14_task_specialist_compare_v1 的runs：92个MAT，2,230,085,010 bytes。
- old_kan_fig8_transfer_compare_v1 的runs：60个MAT，1,536,872,001 bytes。

仅限清单中的raw_run.mat/run_start.mat。该决定不否认旧结果，只按用户要求删除已被当前实验方案接替且无活动引用的历史轨迹文件。所有旧报告/指标/代码、独立模型/normalizer/缓存保留；三组中20个代表性审计MAT另保留。teacher_reuse_model_screen_v1整个目录、data/datasets、复用教师数据、当前27份元数据直接引用的MAT及所有非MAT均保留。position_causal_repair等小体积关键否定证据也保留。

原PROTECTED_MAT.csv中“仅因没有字面废弃声明而保留”的817条经父审解除软保护；其余保护不变。原阶段1清单完整保留作为审查历史；本次权威候选为DELETE_CANDIDATES_PARENT_REVIEW.csv，权威保护为PROTECTED_CURRENT_MAT.csv，不能仍用旧软保护表替代本决定，也不能据此扩大到其他文件。

执行必须逐文件校验绝对路径、后缀、普通文件、无reparse祖先、白名单目录、非保护清单及原尺寸/mtime；任何漂移跳过。仅PowerShell Remove-Item -LiteralPath逐文件，不加-Recurse，不删目录，不跨shell；不删除DL1018外任何文件、不停止进程、不修改实验结果。当前MAIN进程命令含DL1018初始化路径，不等于这三个旧实验仍活动；仅实际指向这些旧实验的进程才构成冲突。
