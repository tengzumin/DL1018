# C5 严格消融：实现与无 Plant 阶段放行

主审已实际执行完整 DEV72 审计（v4只兼容账本时间戳尾零），审计进程退出0。C5为64胜/8负/0平，总Q11.558928371mm，B为17.058080675mm；HF28均值10.179304496mm低于B10.719024064mm；W15均值6.334075115mm低于B7.647291830mm。64胜均改善超过10微米。另独立读216个raw，C5共141,696个事件无输出/面裁剪，状态/广义输入有限，完整安全记录通过。性能进入条件成立。

依据 `C5_MATCHED_ABLATION_CONDITIONAL_TASKBOOK_ZH.md`（02cb08b46f41d5f64adea965e4f9704b75c3aa1e48bc7eee57e1dd94afce6ece），现在仅批准两项消融的隔离代码与无Plant验证。**本文件不是新航次release，不授权自动启动Plant。** 模型、normalizer、cfg、opts、M110、PCF、目标积分、32事件readiness、beta、位置/姿态控制与物理执行链保持原值。

最小实现优先：每个配置独立目录，复制 C5 core/wrapper 原字节，仅在旁置 helper 中干预实际权重更新，避免切 `update_enabled` 或 `position_delayed_prediction_enabled` 分支。`C5_FREEZE_TRAINED_W0` 使实际 W_next=W_k（初值W0且一直保持），实际投影/预测项日志必须对应未应用更新，不能把未应用提案误称实际作用。`C5_NO_DELAYED_PREDICTION` 只将旧梯度作用置零，tracking/leak/单次投影保持；可通过在 helper 中将旧梯度清零实现，与有效rho=0数学等价，历史phi/y和原区间标签仍完整记录。不能悄悄改tau、gamma、先验或readiness。

两项配置均应分别封存身份和原12场ID/顺序，不依赖运行文件名暗示模式；旧C5及全部B/C3不新跑。只增加必要的消融标识/实际更新语义记录，不建立通用实验框架。重用已通过的v3编排结构，完整主函数名/本地函数边界/两模式guard/实际字段映射须静态检查；实际MATLAB必须跑同一runner preflight-only到Plant前return，prepare+预检自然OS0才交主审。

独立Python核两种helper公式，涵盖首事件无历史、已完成十步标签、输出先于更新、原输出/权重边界；完整原模式要与原fixture逐数一致。冻结模式检查整个序列实际W始终W0；预测关闭模式检查相对原式仅移除旧梯度贡献。不能复用旧受PCF混杂的R1冻结结果。

后续主审拟先每配置1场安全/工程核验，再各补11，共最多24场；若factor身份、安全和完整性成立，再决定补齐各60，合计最多144新航次和12GiB。消融输赢不作为挑场依据，反向结果完整报告，不据此调参。原硬截止2026-10-24T17:01:00Z、周期新增80GiB、预留后30GB、单重负载/单GPU、不打断现有实验、不自动重试/删除均保持。实际每批flight仍需独立源码/输入/无Plant审计release。

当前贡献与理论门未批准，TEST仍封存；C5开发性能通过不等于论文证据包完成。主审审计输入 `C5_DEV72_RAW_PARENT_REVIEW_v3.json` SHA bb34889559d95a1c995d4d420e3b3d7a702908b58b47cce969dc508a1c697fab；新批自然OS记录 SHA fc83b80308dfa0d6107e7d4e33ae6dd68ae3715ed9c7c4004ef0580598c2f9b9。不得修改旧G06 STOP或旧参考缓存保护。
