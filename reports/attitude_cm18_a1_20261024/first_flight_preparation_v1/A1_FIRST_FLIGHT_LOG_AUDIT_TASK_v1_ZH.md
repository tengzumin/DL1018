# CM18-A1 首航 raw 独立审计

审计入口为 `experiments/attitude_cm18_a1_20261024/first_flight_preparation_v1/audit_a1_first_flight_v1.m`。它只读取固定 `DL1018_DEV_T1_C01_W15` 的首航 `raw_run.mat`、`run_start.mat`、`run_status.json` 和已锁定输入；不调用闭环 engine、episode wrapper、Plant 或训练。raw 缺失时以 `A1LogAudit:RawMissing` 退出，且不生成 PASS 文件；任何身份、形状或数值闭合失败均抛错。PASS JSON 仅在全项通过后以新文件方式写入本目录，不覆盖旧结果。

它先核 ROOT 首航 release、runner status/start、首个转移 marker、部署模型、no-Plant preparation snapshot、完整 C5 source/shared-input inventory 和 20,000 次实际转移身份。要求 20,001 个有限状态样本、20,000 个 transition-left 样本、状态 `STABLE`、无安全停止及 1,999 个 100 Hz CM18 事件。

评分严格沿用原 C5 单场 scorer：`Q=sqrt(mean(sum((reference.position-state(:,1:3)).^2,2)))`，使用 `0<=time<20` 的 20,000 行；terminal `t=20` 状态不参与。另报 `0<=t<5`、`5<=t<20` 与逐轴 RMSE。姿态参考用 engine 实际记录的 `filtered_attitude_reference` / `filtered_attitude_rate`，SO(3)误差为 `R_actual' * R_ref` 的 geodesic angle；Euler 逐轴误差沿用 wrapped-angle。参考欧拉率先按 ZYX 逆运动学映射到参考机体系，再由 `R_actual' * R_ref` 运输到实际机体系，最后与实际 body-rate 相减。报告 SO(3) RMSE/峰值及运输机体系角速度误差的向量和逐轴 RMSE/峰值，均分上述时间窗。

对每个 CM18 事件，独立重建 X18 `[omega_B, alpha_BS, thrust/mass, u_current, z_before, a_previous]`，其中 `z_before` 是此前命令按 1 ms 左端积分，`a_previous` 是此前十个完整 transition 的请求 torque 加权均值。使用部署 JSON 权重独立前向计算，再复算逐轴 clip、`beta=min(k*dt/2.2,1)`（engine 的 `k` 是 MATLAB 1-based transition index）、held acceleration、固定 `J0` 转矩及 `tau_requested=tau_nominal-tau_compensation`；同时核验整个 hold 区间和姿态 RBF/fusion/head 全关闭。另报位置峰值、姿态/角速度峰值、三项安全阈值持续时间、逐电机饱和与广义命令裁剪计数、CM18 clipped-event 计数。

仅 ROOT 在唯一首航自然终结后执行：

```powershell
$matlabExe='C:\Program Files\MATLAB\R2025b\bin\matlab.exe'
$entry='C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\attitude_cm18_a1_20261024\first_flight_preparation_v1'
$batch="addpath('$entry'); audit_a1_first_flight_v1()"
& $matlabExe -batch $batch
```

当前文件仅完成源码准备与缺失 raw 的 guard 检查；它不代表首航已通过审计。
