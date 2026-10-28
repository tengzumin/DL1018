# 姿态教师数据范围主审

2026-10-27。实际核对full72任务书、training_config.json、matched_teacher DATASET_MANIFEST_v1。

当前67a... MLP模型使用C5 TRAIN24和原VAL48拼接的72场开发数据，143928唯一事件；normalizer全72，最终60000步，无独立VAL或checkpoint选择。任务书显式将VAL48改为DEV_TRAIN。因此六场筛查仅是已见训练条件下的新闭环部署表现，不能称为独立验证；TEST仍封存。

标签合同为post-DMAX/pre-beta rbf_output_raw，单位rad/s²。不得因变量名raw误称限幅前标签。诊断须按实码核对。

位置DSSM14旧训练为1536 episodes/605184 windows；姿态当前场景数量明显较少，但数据量差异只是局限，不能单独作为已证明根因。未授权以此直接新采集、重训或放行TEST。当前先完成同状态shadow与目标语义诊断，再决定唯一优先改动。

这不改变六场候选失败结论，也不以训练内拟合或闭环安全替代最终双环B/C5目标。
