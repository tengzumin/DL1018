# 用户授权：仅当前DL1018目录的废弃实验MAT清理

父审 /root 审核清单，GPT-6-Luna/max 执行；与另一个Luna的实验任务并行。用户明确要求删除没用的废弃/之前实验MAT，并限制“只能够在当前文件夹进行删减操作”。复用教师数据集按保留理解，避免破坏数据复用。

## 不可越过的删除边界

唯一可删根目录的精确绝对路径：C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018 。候选文件必须解析到此根目录内；只删扩展名.mat的普通文件，大小写不敏感。不得删除此目录外任何文件；DL1009、REFERENCE_FIX_FULL72_20261021_022342_313、FIG8_ACC_FIX_CAUSAL等兄弟目录完全不能删除。不得删除目录，不得递归Remove-Item，不得通过junction/symlink/reparse point访问外部；任何路径祖先含reparse point即排除。

不删源码、配置、日志、报告、图、CSV/JSON、H5/HDF5、PT/PTH、其他文件格式。所有模型、normalizer、MATLAB配置/fixture、场景快照与代码资源MAT保留；不以“老文件”或“文件大”作为无用证据。

## 必须保留的内容

1. 当前144格及FULL72/G3/两模型训练的所有有效依赖，包括模板run_start、复用baseline原raw、模型、checkpoint关联MAT、normalizer、导出/前向fixture。当前科学产物已2格，实验Luna正在重绑source身份；你只能读，不能编辑/移动/删其中任何文件。
2. DL1018/data、datasets、models、configs、matlab以及所有教师数据/数据集/缓存目录默认全保留。experiments/teacher_reuse_model_screen_v1 整个目录默认保留。复用教师数据集和其仍需的原MAT来源必须保留。
3. 从当前full-root的manifests、reports、scene_preflight索引、corrected_reference_training_v1下G3真实role/cache来源索引与训练/导出/normalizer协议、以及当前eval的144 manifest和PAIR_EVAL_BASELINE_REUSE_288.csv提取指向DL1018的真实MAT依赖，规范化成绝对路径保护清单。可只读查看目录外这些元数据来建立依赖，但不能在那里删除。数据来源H5索引若含source raw路径，也要保护它们。
4. 对实验目录内名为model/normalizer/snapshot/parity/fixture等MAT及models/datasets/cache目录一律保留；无法确认是否废弃或仍被引用的MAT先保留并注明。

## 阶段1：只读候选清单（先做，到此交父审）

优先使用已有审计库存与rg查找；仅盘点DL1018/experiments中已经完成、被后续方案替代且当前无使用进程的历史实验原始输出MAT，主要是runs内raw_run.mat/run_start.mat。不要泛化到整个data树；其它位置没有授权自动删。结合本地任务状态/报告证明它是历史实验，不能凭时间猜测。

保存到本目录：PROTECTED_MAT.csv（path/reason/source）、DELETE_CANDIDATES.csv（绝对path、bytes、mtime_ns、experiment、abandoned_or_superseded_evidence、not_active_dependency_reason）、CLEANUP_REVIEW_ZH.md（按实验汇总数量/GiB、保护规则、可疑项）。已有SHA可复用，不必对海量历史raw重复hash以抢占实验I/O；删除前必须核尺寸/mtime未变。

扫描不跟随reparse points；列出活动MATLAB/python任务的实际命令路径，排除查询自身；不能结束/暂停任何进程。目录名匹配先保守，保护当前实验优先。仅历史审计索引里“列出了文件”不等于当前执行依赖；但仍是关键论文证据或模型来源时应列保留理由交父审判断。

阶段1交付后停止，不删除；父审会审核具体清单并签MAT_DELETE_PARENT_RELEASE.json后给执行命令。这里是内部父审，不需要再向用户请求重复批准。

## 阶段2：仅在父审发出确切清单SHA后执行

本阶段现在未放行。后续只允许删除父审签名清单中每一条普通MAT，逐项验证resolved绝对路径在唯一DL1018根、extension=.mat、无reparse祖先、非PROTECTED、尺寸/mtime与清单一致、没有活动任务引用。使用PowerShell Remove-Item -LiteralPath逐文件删除，不加-Recurse，不跨shell拼接删除，不覆盖或移动到兄弟目录。任何漂移/疑似依赖立即跳过并报告，不能扩大清单。

保存DELETED_FILES.csv与SKIPPED_FILES.csv、删除前后可用空间及受保护文件存在/元数据未变核验，生成真实清理报告。不得宣称释放空间等于文件名义总大小；实际磁盘free变化另列。实验仍在进行，绝不触碰新生成/正在写入文件。清理完成继续协助父审，但无权改实验代码/科学结果或启动/停止Plant。


## 父审具体放行（阶段2生效）

父审已指定三个历史实验输出目录并签PARENT_DELETE_DECISION_ZH.md及MAT_DELETE_PARENT_RELEASE.json；阶段1的字面废弃状态要求被本次具体决定取代。实际只可按DELETE_CANDIDATES_PARENT_REVIEW.csv中的817条执行，权威保护清单为PROTECTED_CURRENT_MAT.csv。gru14实验的dev24/student_raw也在本批精确清单内，不能扩到其models/cache；其他两实验只限runs。其余原边界完全不变。删除前后保存保护文件存在/size/mtime快照，候选变化或活动任务冲突即跳过，原始清单不可修改；删除完保存DELETED_FILES.csv、SKIPPED_FILES.csv、磁盘free前后与真实汇总。父审批准只对应发送时明确给出的manifest/release SHA。
