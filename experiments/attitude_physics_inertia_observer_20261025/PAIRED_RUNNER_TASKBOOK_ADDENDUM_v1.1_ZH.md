# 隔离 runner 三场配对筛查任务书 v1.1 补充条款

root decision 记录时间：2026-10-25 13:14（Asia/Shanghai）。本补充条款依据 [paired runner 草案 v1](PAIRED_RUNNER_TASKBOOK_DRAFT_v1_ZH.md)，其 SHA-256 为 `48fe5f1d5f1cc6ed144fee506443d9e54a0c42ac99bb636556e8fc2c21b761eb`；当前 synthetic v2 候选锁 `synthetic/source_lock_candidate_v2.json` 的 SHA-256 为 `0245aba9bcfd2f693cf6ec05d8e1dea3a380ff32d2911c949afb9c433ee2b296`。两者仅作为本次决策依据；后者不是六航次所需的完整冻结锁。

1. root 现仅放行 `paired_runner` 隔离树内的代码接入、依赖与输入身份盘点，以及不调用 MATLAB/Plant 的静态检查。此放行不包含 MATLAB、Plant、训练或任何闭环航次；不改生产源码、原草案或现有源锁，不读取 TEST、MAT 或 raw 数据，历史结果原样保留。
2. 两臂均须复用 `experiments/position_axis_coordinate_c5_dev72_20261023/run_dl1018_closed_loop.m` 的 C5 DEV72 position behavior，包括 delayed prediction / M110；不能以生产通用 runner 的 position 行为代替。baseline 与 candidate 的共用 position stack、场景、配置和输入身份保持一致，仅姿态分支按草案预注册处理差异变化。相关隔离副本及依赖须进入完整 runner 锁。
3. 后续六个 fresh DEV 闭环航次，须先使 synthetic v2 审计通过，完成隔离 runner、完整 DEV-only scene inputs 和 `source_lock_paired_runner_v1.json`，再由 root 独立审查代码、审计结果与完整源锁并明确放行。此前不得启动航次。用户已有持续推进授权，满足这些门槛后不需另行询问用户；root 的后续审查与放行仍不可省略。
