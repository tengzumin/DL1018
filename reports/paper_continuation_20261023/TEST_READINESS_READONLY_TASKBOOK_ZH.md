# 一次独立TEST前的只读准备任务书

状态：只读代码与身份准备；不构成解封、MATLAB、Plant或训练放行。当前两组DEV72严格消融在运行，禁止改动它们的任何源码、锁、记录与输入。工作目录仅新增 `reports/paper_continuation_20261023/test_readiness_readonly/`；最多一名Luna xhigh执行者。

## 明确输入和边界

读取已闭合开发集的源码/合同/配置/模型元数据，定位一次独立TEST所需的六种方法：新可追溯B、原corrected DSSM14、corrected KAN14、C5 M110、C5_FREEZE_TRAINED_W0、C5_NO_DELAYED_PREDICTION。C3的已有完整开发结果继续作坐标消融，不额外增加第七种TEST方法。这里只固定对照定义，不提前决定最终方法贡献门或候选选择。

允许读取 `configs/scene_specs.csv` 的划分、scene_id、seed等设计元数据，以及G01、dataset_plan、gate_status封存状态；不得打开任何TEST raw/metrics/状态轨迹/数值场景数组，不生成TEST场景，不运行MATLAB或Python仿真。文件名观察报告已存在 `TEST_SEAL_METADATA_OBSERVATION_v1.json`；它不是对过去未使用TEST的密码学证明。

## 要查明并交付的内容

1. 逐方法给出实际现存、已被开发审计绑定的runtime core、wrapper、helper、模型、normalizer、cfg/opts快照路径和SHA。区分原DSSM/KAN旧快照与当前C5，禁止用“最新版本”替代。读真实schema再列字段；不预设modelIdentity字段，不把历史B物理输入来源误作新B计分来源。
2. 查明现存场景生成器的参考加速度、形态和风构造是否与corrected参考合同一致。仅审源码并列出可以在DEV已用场景完成的无Plant全数组等价检查；不得解除旧G01/参考缓存保护或执行BUILD。指出GET中restoredefaultpath、cfg来源和which绑定的风险，给出最小隔离调用方案。
3. 审核现有 `controller_call_time_s` 计时边界。至少确认是否包括网络推理/更新、PCF与姿态，是否排除分配/Plant/日志保存。列出六方法的可比性以及正式计时需观测的进程/硬件条件；不把原NONISOLATED记录改称正式基准。
4. 给出最小可执行入口改动方案与真实schema样本摘要；优先复用已审代码，暂不实现新大框架、不写放行书、不批量复制代码或MAT。对相同接口的源差异用逐项diff解释。

交付 `TEST_READINESS_SOURCE_FINDINGS_v1_ZH.md` 和小型机器可读身份表，附所有实际执行的只读命令。发现旧TEST迹象则只报告元数据位置，不读取结果。不得修改STATE、Git、运行中目录、原G06 STOP或封存状态；由主审核后独立决定实现/无Plant阶段。
