# 续跑说明

任务：`DL1018_GRU14_DSSM14_STUDENT_REFINE_V1`。当前阶段：`COMPLETE`；状态：`COMPLETE`。

## 恢复原则

- 只在确认没有同阶段 Python/MATLAB 进程后恢复，避免重复 Plant。
- 每个轨迹目录中的 `plant_started.marker`、`raw_run.mat`、`metrics.json`、`manifest_row.json` 是该轨迹的恢复依据。marker 存在但 raw 不存在时先调查，不能盲目重跑。
- Student 采集复用原始 B/控制器与特征头；采集完成前不启动训练。训练中断从每 1000 步保存的 `latest_checkpoint.pt` 恢复。
- DEV 前必须有 `state/LOCKED_CANDIDATES.json`，此后不改变候选。TEST 不读取。

查看状态：`python experiments/gru14_dssm14_student_refine_v1/scripts/refine.py resume`。
