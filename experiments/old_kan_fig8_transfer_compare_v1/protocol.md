# DL1018 旧 KAN 获胜包复现与当前八字迁移对照

状态：执行完成；34 次 Plant 调用全部完成，最终矩阵报告已生成（2026-10-21）。零 Plant 预检通过；未访问 TEST。

## 固定身份与合同

- 旧包：DL1009 提交 `3671d2d212af927abdb6d9149a1b249c372ac55e` 下 `kan_position_attitude_followup_v2/models/repair/N_KAN`，原始 N_KAN、normalizer 与自身 W0 成套使用。
- 新包：DL1018 共享 KAN14 `seed2026102001/final_step`，60,000 步；normalizer、encoder 和 W0 冻结，不换 best、不换 seed。
- 当前八字输入：`DL1018_DEV_T2_C00_W04`, `C02_W15`, `C03_W01`, `C06_W07`, `C08_W08`, `C09_W10`, `C12_W13`, `C14_W14`；逐场以官方生成器重建，并与既有稳定完整 B raw 做同数组核对。
- 两包统一：current-frame X14、FEATURE、PCF、κ=1、beta rise 1.8 s、Gamma 1/12、位置补偿每轴 ±3 m/s²、W 投影 ±60、泄漏 .002/s；位置 RBF 关闭，位置 BS 保留，B 姿态 BS/RBF 保留；C0/J0 固定；1 kHz Plant、100 Hz 位置事件、20 s、ZOH。
- 主矩阵两包均设置 `readiness_events=32`，与模型的 `context_length` 独立。首31个真实位置事件不输出、不更新，第32事件 t=.32 s 起以包自身 W0 输出再更新。每格重新构造 opts、W0、PCF 状态，不跨场继承。

## 预注册执行顺序

1. 零 Plant 预检：来源/hash、`which -all` 路径隔离、旧/新导出 parity、TRAIN/VAL X14、FEATURE/PCF 顺序、W0 复位、readiness 计数，以及 8 个当前 B 输入/完整性。任一失败先在本目录修复并重跑受影响检查。
2. 历史复现各一次：`PDEV_DIAG_D1_C01_1`、`PDEV_DIAG_D1_C12_124`。只用各自原始 `run_start.mat` 中的 scene/cfg/opts 和旧 V3.5 原始 runner。三段 Q 与历史值须各自绝对差 ≤1e-6 m；不重跑 B。
3. 当前八场，每场固定顺序 `OLD_G1_R32 → NEW_G1_R32 → OLD_G12_R32 → NEW_G12_R32`。共32次新 Plant；每格复用同场官方 B。
4. 若旧包任一 Gamma 配置未同时达到完整有效8/8、宏 Q 相对 B 改善≥10%、严格胜 B≥6/8，则执行已冻结的 C09 2×3参考/风桥接：复用当前 B 与 OLD_G1；另外5格各跑 B+OLD_G1，共10次。否则跳过并记录 `SKIPPED_OLD_PACKAGE_RECOVERED`。

预计主实验34次 Plant；桥接触发时44次。所有调用包括失败/中断最多48次；Plant 已标记开始的格子禁止自动重试，必须先检查原始输出与状态。禁止 TEST、训练、数据采集、清理 MAT、覆盖旧包、提交或推送 Git。

## 预注册分析

报告逐场与宏平均 Q_0_20、Q_0_5、Q_5_20；同场相对 B 的差值/改善/胜场、最差退化；Gamma 主效应和 package×Gamma 差分。伴随报告三轴 RMSE/峰值/P95、位置相位统计、姿态、饱和/裁剪、Motor-TV、控制器时延、更新与 readiness 计数、W/PCF/beta/phi 和 normalizer 越界率。DEV 只作诊断，不把选出的 Gamma 宣称为未见测试结论。

桥接仅识别固定 C09 上旧包相对 B 对参考信号整体与外部风频的敏感性，不把它泛化到其它构型，也不把相对 B 的变化归因成新包训练失败的充分因果证据。


