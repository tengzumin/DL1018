# Cosine / NCMD GRU 局部反馈 Jacobian

固定六场 C5 raw 的状态、时间、参考、arms 与各自逐事件得到的 pre-event hidden；仅扰动当前 body ω。每次扰动都完整重算 BS nominal torque，并同步更新 GRU 当前 13 维特征，再以同一 hidden_before 单步前向。净力矩定义为 τBS(ω) − J0·β·clip(q)。这是记录状态上的单事件局部敏感度，不能解释成闭环反事实或稳定性证明。

## 校验与范围

- 六场均取固定均匀的 200 个成熟事件，共 1200 个点、两模型各 1200 个 Jacobian。事件 sample index 按 MATLAB 一基，时间与事件序号匹配。
- 重建中心 BS torque 与 C5 raw 最大差 1.388e−17 N·m；RBF 缓存的 BS Jacobian 最大差 0；解析 BS 与中心差分最大差 1.383e−12。
- ε=1e−5 与 5e−6 的 Jacobian 最大差：cosine 4.927e−11，NCMD 1.333e−9；BS 为 4.163e−12。
- 两模型 1200 点的最小特征值都没有负值：cosine 全局最小 0.070123、median 0.077647；NCMD 全局最小 0.061677、median 0.076605。依预设条件，没有生成负特征值路径分解文件。

## 观察

NCMD 的补偿 Jacobian Frobenius 范数相对 BS 的 median / p95 为 0.579 / 1.521；cosine 为 0.0186 / 0.0921。NCMD 在 W15 与 HF 的 middle 窗口中，yaw 方向 Sym(−J) 对角项相对 BS 的组内中位数增量分别为 0.1344 与 0.0972；roll/pitch 增量分别为 0.0070/0.0098 与 0.0051/0.0082。cosine 的对应增量整体较小。虽然 NCMD 的局部导数更强，所有被采样点的 Sym(−J) 最小特征值仍为正；本诊断没有发现所检点上的局部负阻尼证据。这不证明完整系统稳定，也不能据此断言控制表现改善或变差。

## 可复现文件

- 逐点 Jacobian 与特征值：`GRU_LOCAL_JACOBIANS_v1.csv`
- W15/HF、first5/middle/last5 分组及逐轴摘要：`SUMMARY_v1.json`
- 输入/模型/来源 SHA 与整体数值：`RESULT_v1.json`
- 实际分析脚本：`gru_local_feedback_jacobian.py`，SHA-256：`74ac93f9918eca3621155c02c4fc2572a20ccdfc56ff430c4655ade53053eb64`

PowerShell 7 实际命令（exit 0）：

```powershell
$env:MKL_THREADING_LAYER='SEQUENTIAL'; $env:OMP_NUM_THREADS='1'; $env:MKL_NUM_THREADS='1'; python 'experiments/dl_attitude_replacement_20261026/attitude_gru_local_feedback_diagnosis_20261027_v1/gru_local_feedback_jacobian.py'
```

仅读取 fixed J0/Jdot0 与 K1/K2，不读取或重建变量惯量。Plant=0、训练=0、TEST=未读。
