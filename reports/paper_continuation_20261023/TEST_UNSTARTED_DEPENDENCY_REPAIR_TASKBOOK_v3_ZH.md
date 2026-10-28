# 路径验证器隔离修复任务书 v3

继承任务书 v2（SHA `18736084674fe585904fa991490b2b81308b8e631d73cf8d6d8c26592160f32d`）的三阶段、输入、科学方法、计分、预算和截止要求，仅增加以下已实证的工程修复。当前只授权生成代码，不授权任何 MATLAB、Plant、训练或评分。

v4 准备自然 OS1、Plant0、无结果，原源码和失败全部保留。唯一一次隔离路径诊断自然 OS0，结果 SHA `eaae3bf66870116413e3efdd8f5f659612372ad9035ccae8619c98d121879139`，OS 回执 SHA `43bed0c650ce2f6c99c4251ca40759d19bf92393abc3dac7d76dd773c403ae36`。六方法先前绑定均命中锁定 archive；验证函数又反复 addpath('-end') 后，六项同名 forward 切到项目 models，另162项不变。该新验证器改变路径顺序是工程错误，不能归因于候选控制算法。

仅复制 v4 的四个静态文件到 `experiments/c5_test48_v5/` 和 `reports/paper_continuation_20261023/test_entry_v5/`：MATLAB入口、PS启动器、contract、manifest。禁止复制运行目录、缓存、MAT、prefdir或旧输出。保留文件基本名和V4数据schema，目录v5仅表示入口工程修订，不是新方法。

唯一逻辑修复：删除 `verify_global_platform_which` 中在核验前遍历 global refs 的 addpath('-end') 循环；保留 rehash 及全部 which/same_path 断言，保持 bind_method_path 原样。除此仅替换入口/输出目录为v5、任务书及CODEONLY release为v3，并刷新精确SHA。模型、控制器、normalizer、场景、共同平台、源引用、权重更新、计时和评分保持锁定原字节。manifest可增加顶层旧v4准备失败与诊断回执链接，不改变六方法科学字段。

主审将独立核对 v4/v5 文本差异，只接受上述删除和版本/身份变更；不得趁此补入新逻辑。仍依次另放 PREPARE_NO_PLANT、两场已锁VAL工程复现、最后240个未进入Plant的TEST组合。不得重跑B，不得改旧失败为PASS。此次为已定位同类路径工程错误的第一次隔离修复；再失败先报告，不自动重试。

只用PowerShell7，不结束任何现有进程。保持2026-10-24T17:01:00Z硬截止、周期新增80e9 bytes及预留后30e9 bytes下限，新增v5产物也计入同一总预算。预算函数仅在原v3/v4计数上增加v5目录，不能用新目录重置历史消耗。只有代码任务，无Plant放行。
