# DEV3 A01 C00 candidate 离线残差诊断

仅读 candidate raw、该 run scene audit、release lock 与 helper/config 源；未读 baseline/TEST/旧 MAT，未运行 MATLAB/Plant。物理真值仅离线计算。Raw SHA-256：`6f2716992181d1b06c9e28259b1bf16f7adec11c24a4ab90d27a0212acf3b202`。

C00 退化检查：全程 max|Jhat−J0|=`0.000e+00` kg·m²，rho_hat 跨度最大 `0.000e+00` m，max|Jdothat|=`0.000e+00`，tau_shape RMS XYZ=`[0.0, 0.0, 0.0]` Nm。按 init/prepare/commit 重放，事件 r_tau 与命令均值误差最大 `0.000e+00` / `0.000e+00` Nm；LPF/projected d_hat 误差 `2.068e-25` rad/s²，beta/compensation torque误差 `1.102e-13` / `1.212e-24`。observer 和 a_extra 投影命中分别 `0` 与 `0`。

离线物理真值按 `wind_torque_B + realized_generalized[:,2:4] − controller_clipped_generalized[:,2:4]` 算；逐样本 max|truth| XYZ=`[2.73652628e-16 3.00025846e-16 9.03309816e-17]` Nm。事件窗 r_tau−真值：

- 0–2.2 s：X RMS=5.850e-12, max=2.410e-11; Y RMS=8.773e-12, max=3.687e-11; Z RMS=1.086e-18, max=3.952e-18 Nm；trapz−高阶 Simpson：X RMS=1.735e-11, max=5.435e-11; Y RMS=2.524e-11, max=8.273e-11; Z RMS=2.467e-22, max=1.129e-21 Nm。
- 2.2–20 s：X RMS=1.893e-12, max=1.348e-11; Y RMS=2.219e-12, max=1.433e-11; Z RMS=6.913e-18, max=5.508e-17 Nm；trapz−高阶 Simpson：X RMS=1.658e-11, max=7.870e-11; Y RMS=1.930e-11, max=1.311e-10; Z RMS=1.337e-22, max=1.468e-21 Nm。

解释边界：若 r_tau−真值紧随 trapz−Simpson 的量级，则支持梯形求积/离散动力学残差为主，真实物理扰动与估计滞后解释缺乏信号基础。本记录仅诊断该 candidate C00 的信号来源；它不建立跨 arm 因果，也不改变严格 gate FAIL。

脚本 `analyze_c00_candidate.py`；逐事件表 `event_diagnostics.csv`；阶段统计及实现重放/输入 hash 见 `phase_summary.csv`、`summary.json`。命令见 `command.txt`。
