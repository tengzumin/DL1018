# T1/T3 W09 dual-notch: paired read-only review

只核对同一W09组的两条已完成TRAIN_C5_24闭环raw：`DL1018_DEV_T1_C10_W09` 与 `DL1018_DEV_T3_C09_W09`。来源为各自的单场dual-notch score artifact及同场B/C5/parent/pre-notch raws；冻结scorer和频谱均已逐raw重算匹配。T3 source lock 101/101项SHA匹配，动作递推独立重放最大误差为0；T1递推与score已由前一份只读审计核验。未读取TEST/VAL raw或score，未发起新Plant调用，未做惯量重建。run status中两条既有actual run各记载一次Plant调用。 T3动作输入逐event等于日志中的post-residual-GRU动作（最大差0），双notch 2.2/3.2Hz、Q4在100Hz event更新并逐点ZOH；从首个非零动作0.32s初始化后，raw/applied/held输出重放误差均为0、clip为0，输出力等于0.695kg乘动作。

## 两场算术均值

Q_m单位m，task/inner为SO(3) RMSE、单位mrad；均为这两条同场记录的不加权算术均值，越低越好。

| 方法 | Q_m | task SO(3) | inner SO(3) | task误差f1=2.2Hz带 | task误差f2=3.2Hz带 |
|---|---:|---:|---:|---:|---:|
| B | 0.011003 | 50.631 | 16.970 | 3.910 | 1.066 |
| C5 | 0.010055 | 51.989 | 17.030 | 14.530 | 7.570 |
| parent_GRU | 0.009456 | 51.986 | 14.945 | 14.352 | 7.518 |
| candidate_pre_dual_notch | 0.010231 | 51.895 | 14.949 | 13.882 | 7.651 |
| dual_notch_candidate | 0.010471 | 49.978 | 14.702 | 4.318 | 1.141 |

相对B，dual-notch两场平均Q_m低4.84%，task SO(3)低1.29%；但平均Q_m仍比C5高4.14%、比parent高10.74%。也就是说，这两场均值保留了相对B的Q_m优势，却没有达到C5或parent的位置分数。平均task SO(3)比B/C5/parent/pre-notch低1.29%/3.87%/3.86%/3.69%。

按f1/f2频带看，dual-notch两场平均task−actual RMS为4.318/1.141 mrad，仍比B的3.910/1.066高10.44%/7.03%；它显著优于C5和parent频带误差，但这两条W09记录尚未在这两个频带达到B。T1/T3各自单场falsifier均PASS，但该falsifier比较的是pre-notch候选，不能替代对B的频带非劣条件。

## 结论边界

这只是两个W09 TRAIN场景的平均值，而且都属于parent DEV24；不代表全TRAIN24，更不能证明全72场平均位置提升约32%。两场都通过pre-notch对照的单场task/位置门槛，但旧frozen replay的低频action差量门槛仍为FAIL（T1 2.233%、T3 3.116%，超过2%），score artifact保留了该失败状态。

逐场score、频谱、SHA及scope标记见同目录JSON；单场原始结果仍以各自 `position_compensation_dual_notch_train_diag_single_call_T1_v1/audits/DUAL_NOTCH_SINGLE_CALL_T1_SCORE_v1.json` 与T3对应文件为准。
