# 原场景设计的schedule占位值核验

第二次DEV无Plant实际运行在逐字段记录器拒绝 `spec.start_a1_s` 后自然OS1；未完成首场比较，没有Plant或TEST调用。错误信息泛称nonfinite，不能据此认定物理数组含无穷值。

根已直接读取原 `configs/scene_specs.csv` 的72个DEV/VAL行，非有限字面值只出现在八个字段：start_a1_s至start_a4_s，以及retract_a1_s至retract_a4_s，原文件值为NaN。这些是原封存设计的schedule占位，不是新引入的物理轨迹数值；当前场景通过valid_scene的实际time、初态、参考、风和臂状态数组有限检查之后，才到达此失败。

仅允许以下读记录器修复：在spec上述八个严格命名的字段中，允许两侧同形同类且 `isequaln` 完全相等的占位/数值，任何NaN掩码、Inf符号或有限值不同均失败。保存原字段class、shape和数组哈希，不删除或填补NaN，不放宽其他字段的非有限约束。实际物理数组继续必须全部有限，原1e-12物理差阈值不变，command/ID严格相等。metadata原有完全相同且非NaN的Inf例外仍按原范围处理。

本修复是来源表真实schema的记录兼容，不改变任何场景生成、动力学、控制、模型、参数或统计。旧v2失败、日志、源码和release原位保留，新建v3隔离版本。须根审新源码后另行放行一次DEV无Plant，本文件不授权任何执行模式或TEST解封。
