# 新B可追溯基线：单场工程核验任务书

主审决定：实施准备工作；完成下列无Plant核验并经主审绑定确切代码/输入身份后，放行一次Plant。用户已授权必要新增航次，不再另询额度。此任务不修改C3算法，也不把新运行当作旧B运行时源码身份的追溯证明。

## 要回答的问题与固定条件

在冻结C3源码及cfg下，通过原B构造器重新生成B，是否保持原B的完整状态轨迹及物理输入？这是新基线入口核验，不是候选改进或组件因果实验。

- 唯一场景：`DL1018_VAL_T2_C00_W10`，使用C3 DEV72输入锁中该场的`B_source`实际文件/SHA；允许原别名`_ACC_FIX_V1`仅在内存标准化，原文件不改。
- 固定cfg：C3 `C3_DEV72_PREPARED_CONFIG_OPTS_v2.mat` 中的cfg，与冻结effective config完整树比对。只加载所需变量，B不加载模型或候选opts。
- B opts：用绑定的 `controller_options_dl1018(cfg,'B')` 重新构造；不能从FEATURE候选opts删字段得到。明确断言RBF位置输出/更新启用，stage1 replacement/search/PCF关闭，delayed prediction缺省false或显式false；原B姿态RBF、100Hz事件、C0/J0、Plant及执行器不改。
- wrapper为C3冻结的 `run_episode_dl1018`，实际method `B2-RBF-Full-SPLIT`。collector标签 `B_TRACEABLE_C3CORE_V1` 只用于本批记录。
- 冻结C3有效32文件库存（31个.m与1个MAT）逐一复核路径及实际SHA，MATLAB `.m` 的which解析不得有shadow；绑定完整库存、运行入口及新runner。B不必使用预测helper，但其封存副本不得变化。
- 确定性原B零初始RBF，不引入新训练种子；训练/optimizer/GPU/TEST均为0，20000个1ms转移，0–20s评分，原1e-12m胜负容差。

## 实现及保护

新代码/输入锁/结果只能写 `experiments/b_traceable_c3core_20261023`；审核表只写本报告目录下 `baseline_b_probe_review`。不改冻结C3或旧B任何文件。复用现有已审工具，不创建通用实验框架。

runner须有无Plant准备与明确放行后执行两个入口；准备阶段不调用episode/RK4。先保存精确cfg/完整B opts、source路径/hash、场景身份和断言结果。用实际UTF-8字节计算合同哈希，避免LF/CRLF旧故障。

执行前主审release必须绑定新runner、input lock、无Plant结果及cfg/opts快照的实际SHA。执行时重新检查这些文件、所有源与场景。新建attempt目录，已有输出拒绝覆盖；调用前保存完整run_start和attempt标记，首次Plant标记使用既有hook。完成后保存raw、身份、status、准确命令、真实OS退出码及资源账本。对未知非零退出不自动补跑。

只用PowerShell7。使用既有共享重负载锁，锁忙则等待，不抢锁/结束其他进程；最多1个重仿真。新增本阶段至多1航次、128MiB，磁盘余量保持≥30GB；沿用原总产物预算及UTC `2026-10-24T17:01:00Z` 截止。开始前确认其他实验状态，但不得打断。

## 审核与后续决定

1. 工程/安全：完整STABLE、有限值、20000转移、无安全退出；物理输入与冻结场景逐项相同；实际B模式及更新事件正确，完整cfg/opts与源库存可追溯。
2. 直接读新旧raw比较完整20001×12状态、参考与物理场景，报告最大差、是否逐元素相同；独立重算Q/XYZ/峰值/饱和，不仅比较舍入表。
3. 预期：新旧状态逐元素相同。若不同，保留结果，首先定位源码/选项/数值路径差异，不启动其余71场，不把旧B强行改称已复现。相同也不能恢复旧72场当时未封存的源码树身份。
4. 本任务结束后由主审决定是否冻结其余71场新B，建立与全部C3开发记录配对的可追溯基线。该扩展属于新任务书，不改变本单场账本；无需再询用户新增航次许可。

候选C3的61/72开发胜场失败结论保留；TEST继续封存。此任务不做新候选、网络、参数或场景搜索。
