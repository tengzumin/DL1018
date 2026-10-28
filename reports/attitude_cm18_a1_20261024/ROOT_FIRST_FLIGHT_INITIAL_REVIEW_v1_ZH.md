# CM18-A1 首航初审

固定 DEV T1_C01_W15、原C5位置控制与原Plant/分配器、替换姿态RBF为固定CM18模型。MATLAB R2025b真实执行OS0，20,000个transition完整，20,001个状态，STABLE，安全停止原因为空，实际first-Plant marker存在。新增1航次，训练0，TEST访问0，产物49,620,898 bytes。

ROOT使用独立Python/SciPy从新旧raw计算实际filtered姿态参考的SO3误差、运输body-rate误差，以及0<=t<20位置Q。完整数值见ROOT_FIRST_FLIGHT_METRICS_v1.json。

| 指标 | C5+姿态RBF | C5+CM18-A1 |
|---|---:|---:|
| 位置Q (mm) | 5.688936 | 3.410864 |
| SO3 RMSE (deg) | .953558 | .325110 |
| SO3峰值 (deg) | 2.893543 | .678273 |
| body-rate向量RMSE (rad/s) | .01908525 | .00722610 |
| 电机饱和transition | 0 | 0 |

0–5s微小差异仍保留，不能宣称每个窗口都改善。仅单场工程证据，不能推断72场或独立测试胜率，也不构成稳定性证明。

决定：初步性能与完整性通过。剩余11场仅允许准备源码，尚不放行；先用独立脚本对1999事件的输入过去性、forward、clip、beta、J0补偿、保持、RBF关闭与安全进行真实raw复核。C5历史/C7保持冻结，模型不重训。
