# TRAIN-only HF10 频谱稳健性审计 v1

## Decision

独立方法确认 2–5 Hz 仍有候选残余缺口：无窗 DFT 的候选/B RMSE 比为 1.413x，Hann 去均值 Welch 为 1.577x，零相位滤波为 1.485x（>1 均表示候选频带误差高于 B）。保留“候选在 2–5 Hz 高于 B”的方向；撤回无窗 DFT 的精确幅值作为稳健估计。

撤回仅凭无窗 DFT 将 5–20 s 描述为近持平的强归因：Hann Welch 与零相位滤波分别给出 1.106x 与 1.026x；方向一致为候选略高，但幅值受估计器影响。旧 0–2 s 的 2.904x 比值则由 parent-vs-B 基线差解释，见启动归因。

## 诊断设置与结果

评分沿用冻结 `score_full72_candidate_v1.score_raw`：`sqrt(mean(theta^2))`，`theta = ||Log(R_task^T R_actual)||`；审计将每个候选、同场景 B、parent 的全程分数与冻结 scorer 和 TRAIN24 汇总逐项核对。频谱输入为同一 SO(3) log rotvec。

Welch 用 2 s Hann 分段、50% 重叠、0.5 Hz 频率间隔，分别做每段去均值和线性去趋势；比较 2–5 Hz 与 >5 Hz。第二种估计把四阶 Butterworth 2–5 Hz bandpass 和 >5 Hz high-pass 用 `sosfiltfilt` 离线零相位施加到完整轨迹，再按时间窗积分。下表是等场景合并 RMSE 比值，>1 表示候选高于 B。
注：Welch 0–2 s 仅有1段，2–5 s 仅2个重叠段，估计稳定性低。

| 方法 | 窗口 | 2–5 Hz 候选/B（RMSE 候选/B） | >5 Hz 候选/B（RMSE 候选/B） | 备注 |
|---|---:|---:|---:|---|
| Welch Hann 去均值 | 0–20 s | 1.577x (7.81e-03/4.95e-03 rad) | 3.018x (5.20e-04/1.72e-04 rad) | 0.5 Hz；19 段 |
| Welch Hann 去均值 | 0–2 s | 2.910x (1.22e-02/4.19e-03 rad) | 4.614x (7.43e-04/1.61e-04 rad) | 0.5 Hz；1 段 |
| Welch Hann 去均值 | 2–5 s | 1.677x (7.85e-03/4.68e-03 rad) | 2.729x (4.09e-04/1.50e-04 rad) | 0.5 Hz；2 段 |
| Welch Hann 去均值 | 5–20 s | 1.106x (5.60e-03/5.06e-03 rad) | 2.347x (4.03e-04/1.72e-04 rad) | 0.5 Hz；14 段 |
| Welch Hann 线性去趋势 | 0–20 s | 1.577x (7.81e-03/4.95e-03 rad) | 3.016x (5.21e-04/1.73e-04 rad) | 0.5 Hz；19 段 |
| Welch Hann 线性去趋势 | 0–2 s | 2.907x (1.22e-02/4.20e-03 rad) | 4.519x (7.47e-04/1.65e-04 rad) | 0.5 Hz；1 段 |
| Welch Hann 线性去趋势 | 2–5 s | 1.677x (7.86e-03/4.69e-03 rad) | 2.724x (4.10e-04/1.50e-04 rad) | 0.5 Hz；2 段 |
| Welch Hann 线性去趋势 | 5–20 s | 1.106x (5.60e-03/5.06e-03 rad) | 2.347x (4.03e-04/1.72e-04 rad) | 0.5 Hz；14 段 |
| 零相位滤波 | 0–20 s | 1.485x (6.64e-03/4.48e-03 rad) | 2.139x (7.30e-04/3.41e-04 rad) | 非因果；裁去两端各 1 s |
| 零相位滤波 | 2–5 s | 1.822x (7.79e-03/4.27e-03 rad) | 2.582x (8.54e-04/3.31e-04 rad) | 非因果；完整内部窗 |
| 零相位滤波 | 5–20 s | 1.026x (4.68e-03/4.55e-03 rad) | 1.424x (4.91e-04/3.45e-04 rad) | 非因果；计分至 19 s |

全记录 Welch 的 2–5 Hz 分辨率为 0.5 Hz；2–5 s 仅有两个重叠的 2 s 段，统计稳定性低。Hann 可压低端点旁瓣但不能消除泄漏；滤波截止是平滑过渡，不等价于砖墙频带。零相位滤波使用未来数据，5–20 s 结果裁去记录末端 1 s。
>5 Hz 的绝对量很小：全记录 Welch 候选/B pooled RMSE 为 5.20e-04/1.72e-04 rad（差 0.0199°），零相位滤波为 7.30e-04/3.41e-04 rad；不应只强调大比值。

## 启动归因

10/10 场景在 `t < 2 s` 的 candidate 与 parent 全部 state 最大差为 0，SO(3) log-vector 最大差为 0 rad；候选 raw 内记录的 gate 最大值为 0，gate 输出与 parent 输入最大差为 0 m/s²。启动期 candidate 与 parent 完全一致，2–5 Hz 的旧 0–2 s candidate/B 差已存在于 parent-vs-B，不能归因于 N4 gate。

启动期全频 task RMSE：candidate=parent 0.04863 rad，B 0.04962 rad，candidate/B=0.980；旧 2.904x 是2–5 Hz 无窗DFT频带比，不能与全频task score 等同。

## 下一步训练侧检验

用现有 TRAIN_C5_24 做按场景/风况分组的 out-of-fold 训练核验：只在其他 TRAIN folds 拟合任何 2–5 Hz 因果修正，在留出 TRAIN fold 上同时记录 parent、N4 candidate、B 的每场景绝对 2–5 Hz RMSE、>5 Hz 绝对 RMSE 与全程 task SO(3) RMSE。固定启动前 2 s 为 parent 旁路，不对 gate 做启动调参；以全程任务分数不退化作为和频带指标并列的检查。不要用上述同一 HF10 窗口选超参。
## 范围与限制

仅读取锁定 TRAIN HF10 的 candidate、绑定的同场景 B 和 parent raw、TRAIN 汇总、冻结评分代码/常数与已有 TRAIN 审计 JSON；无 Plant、TEST、VAL、惯量重建或调参。频谱诊断只描述已记录误差轨迹，不能证明闭环因果改善。

可复现脚本：`hf_spectral_robustness_audit_v1.py`。机器可读明细：`SPECTRAL_ROBUSTNESS_AUDIT_v1.json`。
