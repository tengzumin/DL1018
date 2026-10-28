# GRU cosine 六场配对结果

六场均 COMPLETED 且 raw audit PASS。本报告只读 raw；未启动 MATLAB、训练、重跑 baseline 或读取 TEST。

SO(3) 是四元数测地角 RMSE。wrapped Euler roll/pitch/yaw 数值是逐轴分解，不是 SO(3) 分量，也不替代 SO(3) 指标。

## 主指标宏平均

| Group | Method | Q (mm) | Task SO(3) (mrad) | Inner (mrad) |
|---|---|---:|---:|---:|
| ALL6 | cosine_GRU | 8.6066 | 26.7310 | 18.2042 |
| ALL6 | constant_GRU | 8.4724 | 26.9308 | 17.5380 |
| ALL6 | B | 9.1432 | 27.6132 | 17.5668 |
| ALL6 | C5 | 8.3565 | 26.4275 | 17.6019 |
| W15 | cosine_GRU | 7.8736 | 3.7727 | 22.1619 |
| W15 | constant_GRU | 7.7825 | 4.1435 | 21.6631 |
| W15 | B | 8.6285 | 6.6261 | 21.4379 |
| W15 | C5 | 7.5167 | 3.2120 | 21.4358 |
| HF | cosine_GRU | 9.3397 | 49.6893 | 14.2464 |
| HF | constant_GRU | 9.1622 | 49.7181 | 13.4128 |
| HF | B | 9.6580 | 48.6002 | 13.6957 |
| HF | C5 | 9.1963 | 49.6430 | 13.7680 |

## cosine逐场输赢

B: wins Q_m 5/6, SO3_rad 3/6, inner_tracking_rad 0/6; losses Q_m=DL1018_VAL_T3_C00_W13, SO3_rad=DL1018_VAL_T1_C05_W12,DL1018_VAL_T2_C02_W12,DL1018_VAL_T3_C00_W13, inner_tracking_rad=DL1018_VAL_T1_C08_W15,DL1018_VAL_T2_C05_W15,DL1018_VAL_T3_C02_W15,DL1018_VAL_T1_C05_W12,DL1018_VAL_T2_C02_W12,DL1018_VAL_T3_C00_W13
C5: wins Q_m 0/6, SO3_rad 0/6, inner_tracking_rad 0/6; losses Q_m=DL1018_VAL_T1_C08_W15,DL1018_VAL_T2_C05_W15,DL1018_VAL_T3_C02_W15,DL1018_VAL_T1_C05_W12,DL1018_VAL_T2_C02_W12,DL1018_VAL_T3_C00_W13, SO3_rad=DL1018_VAL_T1_C08_W15,DL1018_VAL_T2_C05_W15,DL1018_VAL_T3_C02_W15,DL1018_VAL_T1_C05_W12,DL1018_VAL_T2_C02_W12,DL1018_VAL_T3_C00_W13, inner_tracking_rad=DL1018_VAL_T1_C08_W15,DL1018_VAL_T2_C05_W15,DL1018_VAL_T3_C02_W15,DL1018_VAL_T1_C05_W12,DL1018_VAL_T2_C02_W12,DL1018_VAL_T3_C00_W13
constant_GRU: wins Q_m 2/6, SO3_rad 6/6, inner_tracking_rad 2/6; losses Q_m=DL1018_VAL_T2_C05_W15,DL1018_VAL_T3_C02_W15,DL1018_VAL_T1_C05_W12,DL1018_VAL_T2_C02_W12, SO3_rad=none, inner_tracking_rad=DL1018_VAL_T2_C05_W15,DL1018_VAL_T3_C02_W15,DL1018_VAL_T1_C05_W12,DL1018_VAL_T2_C02_W12

逐场分数与raw/audit SHA见 COSINE_SIX_SCENE_PAIRED_v1.csv；全部方法的xyz和task/inner wrapped Euler轴误差，按full、0–5s、15–20s分段见 COSINE_SIX_SCENE_AXIS_PHASE_v1.csv。

cosine六场安全计数：motor saturation 0, generalized clip 0, tilt limited 0.
账本：授权6次、实际完成6次，新增raw 404607812 bytes；部署研究训练0、baseline重跑0、TEST未读。实际Plant计数由六份status汇总；原Stage release与航后final RELEASE SHA分别记录。
