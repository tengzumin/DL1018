# T3 A01 原始闭环独立复核

日期：2026-10-25。范围仅为重新读取已生成的 T3 A01 baseline/candidate raw，独立计算指标并检查 candidate 的 20,000 条物理补偿 trace；未启动 MATLAB、Plant、训练或 TEST。

## 结论

两个实际闭环航次均完成：每臂 20,000 transitions、STABLE、无安全停止、无 motor saturation、无 generalized clipping、无 tilt limit。T3 的 `batch_status.json` 为 `MORPH_DEV2_T3_CONTINUATION_COMPLETE`，但外层 launcher 写出了 `STOPPED_ON_FAILURE` receipt。此为 launcher 成功谓词错误，不是 Plant 或 candidate 失败；两份原始状态和 receipt 均原样保留。

launcher 将失败行计数条件写为 `Count -ne 2`，而成功应要求失败行数为 0，因此成功批次也进入失败分支。随后失败归档函数读取成功 `run_status` 不存在的 `reason` 属性，在 StrictMode 下再次报错。未来只在新的隔离版本修复，不能改写本次锁定的 v1 文件或 receipt，也不能重跑本 attempt。

## 独立原始复算

复核器从 MAT v7.3 原始数组重新计算 0–20 s 位置 RMSE、SO(3) RMSE、峰值、早晚段和限幅计数，并逐条复核 candidate trace。复核器与产物：

- `t3_a01_independent_v1/review.json` SHA-256：`90b87262b7abaeadf46e46ac28c5e6075c0df5d1c56c64087f3fece0db6fa2e1`
- `t3_a01_independent_v1/scores.csv`
- baseline raw SHA-256：`53b8c48b153a79dfa9a0e308cd46d3b8150a4cb78c4d01bbe093129f2adf3b1c`（47,826,554 bytes）
- candidate raw SHA-256：`d19a9ed4cd17876f535d99c8974fce7ac4f9a0ea157f0b4dcb652eedf91a860`（439,926,304 bytes）

| DL1018_DEV_T3_C10_W11 | baseline RBF | physics + observer candidate | candidate − baseline |
|---|---:|---:|---:|
| position Q RMSE (m) | 0.01243110 | 0.01010714 | −0.00232396 |
| SO(3) RMSE (rad) | 0.02401347 | 0.01396921 | −0.01004426 |
| position peak (m) | 0.03961748 | 0.03961813 | +6.55e−7 |
| attitude peak (rad) | 0.06930726 | 0.04029385 | −0.02901341 |
| motor saturation / clip / tilt-limit samples | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |

位置 RMSE 改善来自后段：0–2.2 s 位置 RMSE 微增 `9.28e−8 m`，2.2–20 s 降低 `0.00342253 m`。三个位置轴均改善，Z 轴幅度仅 `2.09e−5 m`。候选 controller-call 平均时间为 `0.504 ms`，该计时未包含候选 post-allocator commit，不能据此宣称实时性。

独立复核与 run_status 的八个主要位置/姿态 RMSE 及峰值均匹配到浮点舍入精度。Candidate 共 20,000 条 prepare/commit trace、1,999 个 observer 更新事件；时戳、臂命令、角速度、裁剪力矩、估计/补偿符号、事件标志和数值有限性逐项检查均 0 mismatch。RBF 输出/更新开关均为 false，所有 RBF 输出、补偿及权重历史全零。

## 证据边界与下一步

这是 C5 位置环固定条件下的一场 DEV 配对对照，支持“惯量形状前馈 + 命令残差 observer 值得扩展验证”，尚不能证明对全部任务/风况胜过 RBF。下一步应对冻结机制跑完整 DEV72 配对统计，并保留 C5 位置 stack、B 姿态 RBF、Plant、执行器和评分不变；若跨组通过，冻结后才按 C5 的隔离 TEST 流程评估。无需为此先启动神经训练：当前候选由物理方程和在线 observer 组成。静态 CM18 学习候选不应仅因离线误差好而替代这条闭环证据路径。
