# 同状态诊断草稿预审：暂不运行

2026-10-25，Root。对象为尚未冻结的 `a1t_same_state_decomposition_v1.m` 中间态；本记录不是最终源码通过意见。未运行该诊断，未修改既有 raw、模型或控制器。

1. **物理差分符号错误，会导致错误机制判断。** 草稿计算 `freshPhysicalDelta=alphaFresh-alphaHeld`，而控制器请求力矩为 `tauNom-J0*c`，故在线性分配条件下该差为 `-G*(cFresh-cHeld)`。草稿用正号作物理闭合参照，会把本应闭合的结果误记为不一致。已要求作者统一差分方向，并把任务书中的正号量单独解释为 held-minus-fresh 残差参照。
2. **项目根目录多退一级，运行前即会失败。** `experimentDir` 已为 `DL1018/experiments/attitude_cm18_datarepair_20261024`，恢复 repoRoot 应退两级，草稿退三级。已交作者修复。
3. **准备结果接口字段不匹配。** 实读封存 preparation JSON，逐场字段为 `scene_rows`，非草稿的 `scenes`；该 JSON 顶层也不存在 `c5_active_source_file_count`。应核对真实 inventory 长度及 PASS audit 中已验证数量，而非引用不存在字段。已交作者修复，并要求枚举其余身份 JSON 的实际字段。

以上均是新增诊断实现的问题，不是已完成 A1T 飞行代码的问题；不能据此解释既有姿态退化。作者修复后须交最终 SHA，由 Root 重读并经非作者复核，之后才能运行首个单场离线工程检查。当前 A1T 性能否决、C5 冻结、C7 暂缓和不访问新 TEST 的决定继续有效。
