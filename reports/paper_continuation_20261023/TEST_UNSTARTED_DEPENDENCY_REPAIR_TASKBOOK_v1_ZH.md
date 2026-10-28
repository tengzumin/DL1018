# TEST未进入Plant组合的依赖修复任务书（仅代码）

## 实际故障与范围

v3正式批次B48自然OS0，真实回执SHA `32a86e4a16574f7eef4d447ef8bf0ed7bac78ebb15e7fe03ef9d1814183cf506`。DSSM首场在调用PCF helper时自然OS1，回执SHA `b6bee28f012250f21020757984ae2cda601ce56f37161eefad820b6bf3058f1a`；完成0、Plant0、无raw、无first-Plant marker。其余四方法未启动。所有旧源码、输入、B48和失败产物原位保留。

本任务只实现v4隔离入口，不授权MATLAB、Plant或训练。只写 `experiments/c5_test48_v4/` 与 `reports/paper_continuation_20261023/test_entry_v4/`。不得修改v3、原始控制器、模型、normalizer、场景、物理Plant、执行器、旧gate/cache保护、原评分和统计源码。另一个执行者独立复核依赖身份，禁止并发改其目录。

## 唯一工程修复

根实际源码检查显示DSSM/KAN的旧source_refs只列档案local_runtime八个m文件，活动位置分支却调用 `position_filter_realization_pcf_step_v3_5`。B/C5已冻结该函数为 `matlab/models/position_filter_realization_pcf_step_v3_5.m`，SHA `b4ae22db5bd444a162d0cd01a3a59a589f2e37077b089bb33693401b660228d0`。仅在两方法的依赖清单和路径绑定中补此既有源文件，核其签名/真实which及同历史行为的证据；禁止改函数正文或增益/公式。若独立审查证明身份或行为不成立，停止交根，不代选新helper。

## 输入与复用

只加载v3已冻结共享输入与六方法cfg/opts，禁止调用GET或生成任何TEST数组：共享MAT SHA `da207d858e8918f27c19fef30d4ad57206e20f1971e743515043d1a88a995d5c`，cfg/opts MAT SHA `389fdfabd9fbd350d3bdd6df934cfe718eb7208bef2b7b4af02f1192cbb1b9e4`，index SHA `90940a818d293c66c34423a63088113557518c5ecdfd528a3f37867f391eef68`。root输入审查和load-roundtrip证据全保留。原六方法科学顺序、原48 IDs、每场W0重置、全部算法/source/model身份和统计规则不变；v4清单显式映射v3原清单与仅补充的两个依赖引用。

B48只复用，绝不新增B航次。DSSM、KAN、C5、FREEZE、NO_PRED尚未实际进入Plant的240个组合才能进入v4运行范围；原DSSM失败启动如实计账，不能改成成功或隐去。本任务不是依据TEST性能的修复，尚未读取任何TEST评分。

## 两步执行接口（均待另行根放行）

1. 无Plant准备：逐一核五种方法的完整路径/源SHA、PCF helper真实解析与合法数学输入调用，冻结cfg/opts与v3精确一致；用已审DEV证据核helper行为及活动依赖。写真实OS0/失败回执。不得启动TEST Plant、训练或生成场景。
2. 自然OS0且根审通过后，另行放行未运行的五方法，每方法48场、每方法新鲜独立MATLAB进程、顺序执行，最多240个唯一Plant。新输出只在v4/runs，仍短路径。不得覆盖/移动v3失败目录来解除NoRetry；不得重跑B或已存在first-Plant的TEST组合。每次真实启动计账、first-Plant/完整raw/status/源码模型身份保留。

v3源码可以复制隔离后仅改入口、额外依赖、输入/输出/回执版本与复用规则；数学run循环/输出先于更新/控制计时边界保持，提交清楚的差异说明。无用的DEV/TEST生成模式无需复制。参数固定seed2026102001、既有模型step60000，训练0；不扫参数，不读分数。新工程修复最多两次有原因重试，任何真实错误保留并停根，不自动扩大。

正式计时仍单一重负载作业，暂停全量审核/绘图/编译/Git；本次失败引起的方法块间间隔与前置失败启动须在最终耗时报告披露。更新只读worker/launcher观察入口时保留v1，不把旧失败回执当新在跑进程，也不结束任何进程。

原截止2026-10-24T17:01:00Z、总新增80e9 bytes、预留后剩余30e9 bytes保持。预算计入v3已完成产物和v4新增产物，不能只算v4。最终raw reader另写版本以处理B/v3与五方法/v4身份，不改原score函数或统计规则，不把旧失败标PASS。

若发现原DSSM实际已进入Plant、已有性能结果被用于选型，或科学算法需要改变，不能据本任务恢复同一独立TEST；交根作独立性裁决。当前只授权生成可审代码与差异报告。
