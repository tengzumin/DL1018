# LUNA 完成记录

日期：2026-10-27  
目录：`experiments/dl_attitude_replacement_20261026/mlp15_composite_head_v1`

## 交付状态

已完成新目录中的复合姿态头实现、300 事件 Python/MATLAB 无 Plant 核验、历史对照绑定和准备 release。**未启动 Plant、闭环航次、训练、DEV72 或 B/C5；未读取 TEST。** 当前不代表闭环通过，也不代表最终目标达成。

## 控制改动

- `candidate_runner_work/matlab/runtime/mlp15_attitude_step_v1.m`：保留 MLP 当前输出先于任何权重更新。过去残差 RLS 与 Joseph 协方差更新后，按任务书固定系数加入
  `tracking_drive = -(P_after * phi_current) * (beta_current * (target_rms .* (T_current' * s_current)))'`，
  再按真实事件间隔加到权重，最后仍投影到 Frobenius 范数 20。
- `candidate_runner_work/matlab/runtime/run_gate_holdout_closed_loop.m`：保持 MLP 13 维输入和历史 10 ms 残差区间/命令端点；传入当前 BS 的 `euler_rate_map`、`surface`、实际事件间隔，保存跟踪量、权重和更新 trace。闭环入口要求本地 release 为 `ROOT_RELEASED`、预算为正且当前 scene 获得授权；当前 prepared release 会在进入仿真前硬拒绝。

冻结模型 SHA256：`67a6564148ba8c1988d7457c04a5d3271516ff4010da18e61e29fd7da13be46b`。锁定配置读取 `K1=[1.5,1.5,1.3]`、固定名义 `J0`、`dmax=[45,45,4.7124]`、beta 上升时间 2.2 s、`P0=10I`、forgetting factor 0.999 和权重界 20。未重建时变惯量/惯量导数，控制器未使用真实惯量、风、臂长或 RBF 信号。

## 无 Plant 检查结果

最终报告：[audits/NO_PLANT_CHECK_v7.json](audits/NO_PLANT_CHECK_v7.json)。MATLAB 为显式 R2025b `25.2.0.2998904`。

- Python 独立 fixture 与实际 MATLAB step：300 事件；80 次残差更新、81 次跟踪更新、30 次投影、29 次 dmax 截断。
- 最小协方差 Cholesky 对角元 `0.9170`；最大 MATLAB/Python raw 输出误差 `8.18e-14 rad/s²`、权重误差 `7.74e-12`、协方差对角误差 `2.85e-14`。
- `dmax`、冻结 forward、过去区间端点/命令索引均通过。独立代数符号抵消误差 `1.39e-15`。
- 分别改变当前残差观测或当前跟踪信号，当前输出保持完全相同，后续输出改变。直接调用闭环入口的负向检查命中 `COMPOSITE:PlantBudgetZero`。
- 复制的 56 个 MATLAB 文件相对 v1 仅两处 SHA 不同：上述 MLP step 与 event entry。Code Analyzer 对照为既有 102 项、新增 0 项；新审计/准备 MATLAB 文件为 0 项诊断。

完整 Python fixture 在 [audits/make_composite_fixture.py](audits/make_composite_fixture.py)，MATLAB 检查为 [audits/check_composite_head_no_plant.m](audits/check_composite_head_no_plant.m)。

## 历史对照与 release

[MANIFEST.json](MANIFEST.json) 绑定六场 VAL 的 v1 prediction-only raw SHA、B、C5、冻结 MLP、载荷及相同物理 scene arrays SHA。只读独立指标报告为 [PREDICTION_ONLY_BASELINE_REPORT.json](PREDICTION_ONLY_BASELINE_REPORT.json)。六场宏平均 `(Q_m, SO3_rad, inner_tracking_rad)`：

- prediction-only：`(0.009475 m, 0.028167 rad, 0.020047 rad)`
- B：`(0.009143 m, 0.027613 rad, 0.017567 rad)`
- C5：`(0.008357 m, 0.026428 rad, 0.017602 rad)`
- 冻结 MLP：`(0.018425 m, 0.041750 rad, 0.056407 rad)`

以上只是既有 prediction-only 对照，尚无 composite raw，故 tracking 项相对 prediction-only 的闭环效果未评估。

[RELEASE.json](RELEASE.json) 状态为 `PREPARED_ROOT_REVIEW_REQUIRED`，`authorized_Plant_calls=0`、`Plant_calls=0`、授权 scene 为空。待 root 读码并审核后，首场仅为 W15 T1 `DL1018_VAL_T1_C08_W15`；T2/T3 须首场审核后另行放行。三场 W15 全部安全且 Q、外环 SO(3)、内环跟踪误差宏平均均优于 prediction-only 后，才建议继续 W12/W13。最终仍须优于 B、姿态优于 C5，并满足相对 C5 的位置宏平均退化不超过 10%。

最终 release SHA256：`b96e0c4877a2401afe237dff222fba4f29bb6939c752a55ca264a040e6156fcd`。源码 patch SHA256：`52b39613d618668bfa1007e842f5d981555b4bfd05fd64ab777428be0a9175e7`。

独立真实 raw 审核器已准备于 [audits/audit_composite_raw.m](audits/audit_composite_raw.m)：从 `state`、`filtered_attitude_rate`、`filtered_attitude_reference` 与锁定 K1 重建 Euler 映射和 BS surface，并独立重放网络、RLS/Joseph、跟踪项、投影及首次修正前的状态一致性。没有 composite raw，因此本阶段未运行这项真实 raw 对照。

源码差分见 [SOURCE_DIFF.patch](SOURCE_DIFF.patch)，文件 SHA 锁见 [SOURCE_LOCK.json](SOURCE_LOCK.json)，release 身份见 [RELEASE_RECORD.json](RELEASE_RECORD.json)。所有无 Plant 失败与修复记录在 [FAILURES.md](FAILURES.md)。

## 复现命令

在 PowerShell 7、项目根目录执行（仅 fixture、MATLAB 数值/源码检查和只读历史输入准备）：

```powershell
python 'experiments/dl_attitude_replacement_20261026/mlp15_composite_head_v1/audits/make_composite_fixture.py'
& 'C:/Program Files/MATLAB/R2025b/bin/matlab.exe' -batch "cd('C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018'); addpath('experiments/dl_attitude_replacement_20261026/mlp15_composite_head_v1/audits'); check_composite_head_no_plant; prepare_composite_release_no_plant"
& 'experiments/dl_attitude_replacement_20261026/mlp15_composite_head_v1/audits/finalize_source_diff.ps1'
```

检查报告采用递增版本名且拒绝覆盖既有结果。源码 patch finalize 仅调用 `git diff --no-index` 生成差分并刷新 SHA，不暂存、提交或推送。

## 理论范围与未完成项

符号恒等式只覆盖未截断的交叉项。采样与近似误差、dmax/权重投影、协方差变化和 Euler 坐标域仍不构成完整闭环证明。尚未执行 root 审核、真实 composite raw replay、三场 W15 或任何最终 B/C5 门槛；这些结果必须在后续获 root release 后另行评估。
