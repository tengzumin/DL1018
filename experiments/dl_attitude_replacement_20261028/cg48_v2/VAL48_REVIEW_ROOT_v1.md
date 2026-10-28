# VAL48 独立结果审计

## 范围与 ID 核验

- VAL48：schema `DL1018_CAUSAL_N4_VAL48_BATCH_SCORE_SUMMARY_V2`，48/48 scene；与输入、冻结计划、进度和 run_status 的 scene ID 顺序完全一致。
- TRAIN24：schema `DL1018_CAUSAL_N4_TRAIN24_BATCH_SCORE_SUMMARY_V2`，24 个 `DEV` scene；与 VAL48 的 ID 交集为 0，合并共 72 个唯一 scene。
- 本审计仅读取两个 score summary、VAL48 的计划/输入/进度/contract/source-lock/hash-preservation JSON，以及 48 个 `run_status.json`；未打开 `raw_run.mat`，未读 TEST，未运行 MATLAB/Plant，也未做惯量重建。现有 VAL48 batch 元数据记录的是已完成的 48 次 Plant call。
- 冻结数值配置相同：`True`；gate/model numeric value changed：`False`。

## Overall 与 HF_W09_W14 宏平均

表内 `Q_m / task_SO3_rad / inner_SO3_rad` 均为 scene 宏平均；数值越低越好。

### TRAIN24（DEV） · overall（n=24）

| method | Q_m | task_SO3_rad | inner_SO3_rad |
|---|---|---|---|
| candidate | 0.010353 | 0.053276 | 0.012358 |
| B | 0.015188 | 0.056741 | 0.013939 |
| C5 | 0.010725 | 0.054853 | 0.014051 |
| parent | 0.010338 | 0.054879 | 0.012552 |

candidate/C5 Q ratio-of-sums = 0.965284; candidate/B Q ratio-of-sums = 0.681636; candidate/B task ratio-of-macro-means = 0.938932.

### TRAIN24（DEV） · HF_W09_W14（n=10）

| method | Q_m | task_SO3_rad | inner_SO3_rad |
|---|---|---|---|
| candidate | 0.010159 | 0.054644 | 0.014427 |
| B | 0.011233 | 0.055091 | 0.016606 |
| C5 | 0.010663 | 0.058443 | 0.016860 |
| parent | 0.010126 | 0.058488 | 0.014894 |

candidate/C5 Q ratio-of-sums = 0.952766; candidate/B Q ratio-of-sums = 0.904435; candidate/B task ratio-of-macro-means = 0.991894.

### VAL48 · overall（n=48）

| method | Q_m | task_SO3_rad | inner_SO3_rad |
|---|---|---|---|
| candidate | 0.011544 | 0.058494 | 0.015406 |
| B | 0.017993 | 0.065183 | 0.017538 |
| C5 | 0.011975 | 0.060315 | 0.017556 |
| parent | 0.011524 | 0.060280 | 0.015414 |

candidate/C5 Q ratio-of-sums = 0.964015; candidate/B Q ratio-of-sums = 0.641622; candidate/B task ratio-of-macro-means = 0.897378.

### VAL48 · HF_W09_W14（n=18）

| method | Q_m | task_SO3_rad | inner_SO3_rad |
|---|---|---|---|
| candidate | 0.009538 | 0.054296 | 0.013198 |
| B | 0.010433 | 0.054663 | 0.014895 |
| C5 | 0.009910 | 0.058991 | 0.015037 |
| parent | 0.009487 | 0.059057 | 0.013218 |

candidate/C5 Q ratio-of-sums = 0.962432; candidate/B Q ratio-of-sums = 0.914187; candidate/B task ratio-of-macro-means = 0.993281.

### 合并72（DEV+VAL诊断） · overall（n=72）

| method | Q_m | task_SO3_rad | inner_SO3_rad |
|---|---|---|---|
| candidate | 0.011147 | 0.056754 | 0.014390 |
| B | 0.017058 | 0.062369 | 0.016338 |
| C5 | 0.011559 | 0.058494 | 0.016388 |
| parent | 0.011129 | 0.058480 | 0.014460 |

candidate/C5 Q ratio-of-sums = 0.964408; candidate/B Q ratio-of-sums = 0.653498; candidate/B task ratio-of-macro-means = 0.909980.

### 合并72（DEV+VAL诊断） · HF_W09_W14（n=28）

| method | Q_m | task_SO3_rad | inner_SO3_rad |
|---|---|---|---|
| candidate | 0.009760 | 0.054420 | 0.013637 |
| B | 0.010719 | 0.054816 | 0.015506 |
| C5 | 0.010179 | 0.058795 | 0.015688 |
| parent | 0.009715 | 0.058854 | 0.013817 |

candidate/C5 Q ratio-of-sums = 0.958816; candidate/B Q ratio-of-sums = 0.910537; candidate/B task ratio-of-macro-means = 0.992784.

## C5 姿态误差相对 B

相对差定义为 `100 × (C5/B − 1)`，正值表示 C5 误差更大；区间是 task-stratified paired scene bootstrap 的 95% percentile CI。

### task SO(3)

| group | n | B mean | C5 mean | C5−B | C5 vs B % | paired bootstrap 95% CI % |
|---|---|---|---|---|---|---|
| TRAIN24 overall | 24 | 0.056741 | 0.054853 | -0.0018878 | -3.33 | [-9.80, 2.27] |
| TRAIN24 HF | 10 | 0.055091 | 0.058443 | 0.0033516 | 6.08 | [3.06, 9.76] |
| VAL48 overall | 48 | 0.065183 | 0.060315 | -0.0048678 | -7.47 | [-12.91, -1.89] |
| VAL48 HF | 18 | 0.054663 | 0.058991 | 0.0043283 | 7.92 | [4.92, 11.01] |
| 72 overall | 72 | 0.062369 | 0.058494 | -0.0038744 | -6.21 | [-10.55, -1.91] |
| 72 HF | 28 | 0.054816 | 0.058795 | 0.0039795 | 7.26 | [4.99, 9.67] |

### inner SO(3)

| group | n | B mean | C5 mean | C5−B | C5 vs B % | paired bootstrap 95% CI % |
|---|---|---|---|---|---|---|
| TRAIN24 overall | 24 | 0.013939 | 0.014051 | 0.0001119 | 0.80 | [0.18, 1.62] |
| TRAIN24 HF | 10 | 0.016606 | 0.016860 | 0.0002546 | 1.53 | [0.68, 2.74] |
| VAL48 overall | 48 | 0.017538 | 0.017556 | 0.0000185 | 0.11 | [-0.34, 0.60] |
| VAL48 HF | 18 | 0.014895 | 0.015037 | 0.0001420 | 0.95 | [0.51, 1.47] |
| 72 overall | 72 | 0.016338 | 0.016388 | 0.0000496 | 0.30 | [-0.08, 0.73] |
| 72 HF | 28 | 0.015506 | 0.015688 | 0.0001822 | 1.18 | [0.71, 1.78] |

## VAL48 candidate paired bootstrap

差值定义为 candidate − comparator；负值表示 candidate 的误差较低。以下是 overall 与 HF 子集的逐 scene 配对区间。

### VAL48 overall

| comparator | metric | candidate−comparator estimate [95% CI] |
|---|---|---|
| B | Q_m | -0.006448 [-0.008747, -0.004373] |
| B | task_SO3_rad | -0.006689 [-0.010603, -0.003306] |
| B | inner_SO3_rad | -0.002132 [-0.002469, -0.001799] |
| C5 | Q_m | -0.000431 [-0.000508, -0.000359] |
| C5 | task_SO3_rad | -0.001821 [-0.002794, -0.000970] |
| C5 | inner_SO3_rad | -0.002150 [-0.002470, -0.001834] |
| parent | Q_m | 0.000020 [0.000006, 0.000037] |
| parent | task_SO3_rad | -0.001787 [-0.002786, -0.000917] |
| parent | inner_SO3_rad | -0.000007 [-0.000050, 0.000039] |

- candidate/C5 Q ratio-of-sums: 0.964015 [0.956820, 0.970186].
- candidate/B Q ratio-of-sums: 0.641622 [0.584577, 0.711268].

### VAL48 HF_W09_W14

| comparator | metric | candidate−comparator estimate [95% CI] |
|---|---|---|
| B | Q_m | -0.000895 [-0.001243, -0.000513] |
| B | task_SO3_rad | -0.000367 [-0.000617, -0.000165] |
| B | inner_SO3_rad | -0.001697 [-0.002134, -0.001249] |
| C5 | Q_m | -0.000372 [-0.000460, -0.000283] |
| C5 | task_SO3_rad | -0.004696 [-0.006536, -0.002978] |
| C5 | inner_SO3_rad | -0.001839 [-0.002277, -0.001393] |
| parent | Q_m | 0.000051 [0.000017, 0.000088] |
| parent | task_SO3_rad | -0.004761 [-0.006627, -0.003009] |
| parent | inner_SO3_rad | -0.000020 [-0.000131, 0.000098] |

- candidate/C5 Q ratio-of-sums: 0.962432 [0.954817, 0.970521].
- candidate/B Q ratio-of-sums: 0.914187 [0.886775, 0.947682].

## Scene misses、action replay 与安全

- VAL48 candidate/C5 Q aggregate ratio = 0.964015（目标 ≤1.05）；逐 scene 超过 1.05：0 个。
- HF candidate task ≤ B：14/18 scene；HF 宏平均 candidate/B = 0.993281（aggregate 通过）。
- Action-chain replay（2e−10）通过 48/48；score safety-fault scene = 0，fatal stop = 0；48 个 run_status 均 COMPLETED/STABLE、20,000 transitions、20,001 samples、每 scene 1 call。

### candidate task_SO3 高于 B 的 scene

| scene_id | HF | candidate rad | B rad | Δ rad | candidate/B % |
|---|---|---|---|---|---|
| DL1018_VAL_T1_C01_W08 | False | 0.090595 | 0.086790 | 0.0038054 | 4.38 |
| DL1018_VAL_T1_C04_W11 | True | 0.057784 | 0.057615 | 0.0001691 | 0.29 |
| DL1018_VAL_T2_C00_W10 | True | 0.053439 | 0.053295 | 0.0001446 | 0.27 |
| DL1018_VAL_T3_C01_W14 | True | 0.061806 | 0.061792 | 0.0000137 | 0.02 |
| DL1018_VAL_T3_C11_W08 | False | 0.091919 | 0.090363 | 0.0015561 | 1.72 |
| DL1018_VAL_T3_C13_W10 | True | 0.061042 | 0.061012 | 0.0000302 | 0.05 |

HF 四个 per-scene miss（上表标记 HF）；另外两个 miss 不属于 HF。candidate/C5 Q 单 scene >1.05：无。

## 解释边界

合并72仅用于 DEV24+VAL48 开发诊断；parent comparator 已见这72个 scene，所以这不是独立测试结果。所有 TEST scope flags 为 false。

复算区间：20,000 次按 task 分层的 scene bootstrap，固定 seed `20261028`；方法按 scene 配对，报告 percentile 95% CI。JSON 中包含全部组别与 CI。
