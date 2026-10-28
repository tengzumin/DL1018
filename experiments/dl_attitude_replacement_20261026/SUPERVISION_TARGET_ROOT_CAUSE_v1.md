# DL-TCN 监督目标与固定惯量根因审计

日期：2026-10-26（Asia/Shanghai）  
审计范围：冻结数据集 VAL48；只读 raw/run-start；无 Plant、无 TEST。

## 结论

当前 `training_v1_retry01` 不能作为“TCN 替代姿态 RBF”的候选放行。它的标签不是旧 RBF 的补偿动作，而是旧 RBF 已参与闭环后的剩余角加速度；同时数据导出器把 `cfg.plant.inertia` 当成了 BS 固定控制器惯量，训练特征因此和运行时 BS 特征不一致。

本次没有终止训练进程。进程截至 04:06（Asia/Shanghai）仍在运行，8,000/60,000 steps，best VAL residual RMSE 0.06017。保留它及全部日志作为监督目标错误的诊断记录；在新候选完成前不启动 Plant pilot。

## 证据

### 1. 训练特征用了错误的惯量来源

`prepare_tcn_dataset_v1.py` 从 `cfg.plant.inertia` 取矩阵，再用记录的 BS 名义力矩计算 `alpha_bs`。但实际固定控制器的惯量由项目函数 `simulation_parameters` 与 `controller_parameters(...,'fixed')` 根据名义臂长和分布式质量模型计算；它不是 `cfg.plant.inertia` 这个 base 值。

MATLAB R2025b 对全部 VAL48 的 run-start 按实际项目函数复算，得到：

```text
cfg.plant.inertia = diag(0.012, 0.012, 0.022) kg·m²
fixed controller J0 = diag(0.003257553333333334,
                           0.003257553333333333,
                           0.006360648333333333) kg·m²
```

48 场的固定控制器 `J0` 完全一致；base inertia 与控制器 `J0` 的相对 Frobenius 差为 2.538。按正确控制器 `J0` 从名义力矩复算后，NPZ 中已有 `alpha_bs_body` 特征的宏观 RMS 偏差为 `[0.9879, 0.8775, 0.1698] rad/s²`。闭环 TCN runner 则从 `attitude_bs_step` 直接取其真实 nominal body angular acceleration，因此训练/推理特征不一致。

### 2. 目标标签不等于需要替代的 RBF 动作

当前标签是：

```text
(omega[k+10] - omega[k]) / 0.010 - alpha_bs_body[k]
```

B 的 run-start 记录姿态 RBF 已启用、输出已启用、在线更新已启用。这个标签是 RBF 参与之后的闭环剩余量，而模型输出随后又被当成 `estimateTorque` 送入 BS；它并不是教师 RBF 原本输出的量。

VAL48 的 raw 与 run-start SHA 均复核通过，共 95,952 个事件。raw 中记录的 `rbf_output_raw` 是事件时刻教师 RBF 的限幅输出（pre-beta，`rad/s²`）；`attitude_rbf_compensation_torque_Nm` 则是已乘 beta 并由固定控制器 `J0` 换算后的实际命令。按冻结 beta 和固定 controller `J0` 复算教师力矩，48 场相对误差中位数为 `6.8e-9`、最大值 `2.12e-4`，证明该 raw 动作可直接作为替代头的监督目标，无需形态相关惯量重建。

同一输出坐标下，VAL48 教师 RBF pre-beta 输出 RMS 宏平均为 `[6.7811, 8.5377, 0.5185] rad/s²`，当前监督残差 RMS 宏平均为 `[0.6807, 0.7571, 0.1464] rad/s²`；逐场教师输出/当前标签 RMS 比中位数 `11.27`、P95 `44.35`、最大 `59.12`。因此目标语义差异很大，不是小噪声。

机器可复核记录：

- [`CONTROLLER_J0_AUDIT_VAL48_v1.json`](CONTROLLER_J0_AUDIT_VAL48_v1.json)：MATLAB 对全部 VAL48 run-start 的 fixed controller `J0` 复算。
- [`SUPERVISION_TARGET_AUDIT_v1.json`](SUPERVISION_TARGET_AUDIT_v1.json)：48 场 raw/run-start SHA、现有特征偏差、教师动作语义及命令换算复核。
- [`audit_tcn_dataset_controller_j0_v1.m`](audit_tcn_dataset_controller_j0.m)：参数路径复算脚本。
- [`audit_supervision_target_against_rbf_v1.py`](audit_supervision_target_against_rbf_v1.py)：只读数据核对脚本。

## 修复决定

1. 保留现有失败语义的模型、训练进程与文件；不覆盖、不删除，也不用于论文性能结论。
2. 修订后的监督目标直接使用 `rbf_output_raw`。这是输出头真正要替代的 RBF 动作，避免将教师动作和闭环残差混为一谈。
3. 输入中把 `alpha_bs_body` 换为 BS 名义力矩。该信号在 raw 日志和运行时 `attitude_bs_step` 都直接可得，不必用错误的 `cfg.plant.inertia` 重建角加速度。
4. 输出仍为有界角加速度补偿；运行时仅使用冻结 C5 固定控制器 `J0`、既有 beta 与限幅映射力矩。不使用 `Jhat`、`Jdot_hat`、Plant 真值或 observer。
5. 在当前 GPU 训练完成前，不启动第二个训练作业；修正数据、代码、release 和 no-Plant/MATLAB 对齐可先在隔离版本准备。之后只运行一个修正候选训练，再依任务书通过 parity/no-Plant 门后进入六场 pilot。
