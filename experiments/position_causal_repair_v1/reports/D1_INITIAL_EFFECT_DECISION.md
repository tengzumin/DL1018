# D1：G04 全量同场配对结果与 Initial 决策

口径：432 个 G04 Student 场景（TRAIN 384、VAL 48）逐场连接历史 B、POS_OFF 与 P_INIT_STUDENT。Q 为每条完整航次先算 0–20 s 的向量位置 RMSE，再按任务宏平均；没有混池采样点。A 同理按向量姿态误差 RMS。MATLAB percentile 使用已校验的 Hazen 定义。机械 phase 直接复现 `metrics_dl1018.m` 的命令/rho 阈值分类；时间分箱为固定区间。

## TRAIN（n=384）

- B 按任务宏 Q：0.020805874 m。
- POS_OFF 按任务宏 Q：0.113605116 m。
- P_INIT_STUDENT 按任务宏 Q：0.0418718903 m。
- P_INIT 胜 B：12/384；胜 POS_OFF：375/384。

## VAL（n=48）

- B 按任务宏 Q：0.0198604509 m。
- POS_OFF 按任务宏 Q：0.108564327 m。
- P_INIT_STUDENT 按任务宏 Q：0.0408585127 m。
- P_INIT 胜 B：2/48；胜 POS_OFF：48/48。

## ALL（n=432）

- B 按任务宏 Q：0.020700827 m。
- POS_OFF 按任务宏 Q：0.113045028 m。
- P_INIT_STUDENT 按任务宏 Q：0.0417592928 m。
- P_INIT 胜 B：14/432；胜 POS_OFF：423/432。

## A、按任务胜负

- FIG8_3D: P_INIT 胜 B 2/144；胜 POS_OFF 144/144；任务宏 Q B/POS_OFF/P_INIT = 0.02399072/0.1178465/0.04582395 m。
- HELIX: P_INIT 胜 B 4/144；胜 POS_OFF 138/144；任务宏 Q B/POS_OFF/P_INIT = 0.01909734/0.1109929/0.04105177 m。
- SQUARE: P_INIT 胜 B 8/144；胜 POS_OFF 141/144；任务宏 Q B/POS_OFF/P_INIT = 0.01901442/0.1102957/0.03840216 m。

## B、退化从何时出现

- TRAIN P_INIT−POS_OFF 各时间分箱逐场差的平均值：-0.0142092/-0.0481619/-0.0758821/-0.0854982/-0.0831129 m。
- VAL P_INIT−POS_OFF 各时间分箱逐场差的平均值：-0.0121753/-0.043263/-0.0715482/-0.0822829/-0.0775697 m。
- ALL P_INIT−POS_OFF 各时间分箱逐场差的平均值：-0.0139833/-0.0476175/-0.0754006/-0.085141/-0.082497 m。

## C、是否由少数极端场景拉高

- P_INIT−B 单场 Q 差：中位数 +0.0220821 m，P10/P90 +0.00817127/+0.0305813 m；变差场数 418/432。
- 全量逐场差、极值和尾部清单见 D1_G04_PAIRED_ALL.csv；不以稳定性替代性能。

## D、风频组

- NO_WIND n=27，P_INIT 胜 B 0/27，胜 POS_OFF 18/27；P_INIT−B macro Q=+0.018528 m。
- LOW n=162，P_INIT 胜 B 14/162，胜 POS_OFF 162/162；P_INIT−B macro Q=+0.015101 m。
- MID n=162，P_INIT 胜 B 0/162，胜 POS_OFF 162/162；P_INIT−B macro Q=+0.024432 m。
- HIGH n=81，P_INIT 胜 B 0/81，胜 POS_OFF 81/81；P_INIT−B macro Q=+0.0270699 m。

## E、任务方向差异

三个任务逐项胜率及 macro Q 如 A；只有任务间方向实际相反时才判为相反表现。任务分组不能单独证明需要专家模型。

## 初始干预分支

- P_INIT−POS_OFF 单场 Q 差均值：-0.0712857354 m；P_INIT−B：+0.0210584658 m。
- 决策：若 Student 优于 POS_OFF 但逊于 B，则保留固定补偿有净价值、但未能替代 B 的 RBF 能力；继续按 D2/D3 分离运行链、Final warm-fit 与适应目标。
- 结论等级：这是同场行为比较；不单独证明唯一根因。
