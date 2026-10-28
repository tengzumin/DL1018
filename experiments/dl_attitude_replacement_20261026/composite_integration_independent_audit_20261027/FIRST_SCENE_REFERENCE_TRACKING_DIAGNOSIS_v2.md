# First-scene 参考与跟踪误差诊断 v2

日期：2026-10-27。只读 Python/h5py 诊断同一 scene 的 candidate、B、C5、prediction-only 四份 raw；未运行 MATLAB/Plant，未修改 controller、指标或阈值，未重建惯量。

## 结论

固定任务参考必须从每份 raw 中相同的 `scene.reference.acceleration`、`scene.reference.yaw` 导出。v1 把每个闭环自己的 `raw_outer_attitude`/`command_filter_target_euler` 当成固定任务参考，定义错误；v1 JSON 已标为 `REFERENCE_DEFINITION_ERROR` 并保留原数值。本 v2 按 v3 raw audit 的 `metrics()` 公式纠正。

Candidate 全程 task SO(3) RMS 为 0.007240 rad，高于 C5 的 0.002995 rad；其全程 filtered→actual inner-tracking RMS 为 0.024897 rad，略低于 C5 的 0.025476 rad（约低 2.27%）。这种全程内环小幅优势没有出现在前、后 5 秒：candidate 的后 5 秒 inner error RMS 是 0.021557 rad，C5 为 0.015880 rad；同窗 task→actual 分别是 0.009030 与 0.002490 rad。误差差距主要在后 5 秒，并同时出现在固定任务→闭环 outer 指令、outer→filtered、filtered→actual 三段的描述性统计中。由于各 raw 的闭环状态轨迹不同，这不能证明其中任一段是单组件原因。

当前证据把问题定位到后 5 秒的整条任务姿态链路，不支持“内环全程更好，所以 task SO(3) 变差必由另一单组件造成”的因果说法。任务 SO(3) 仍未优于 B/C5，不能改用 inner 指标替代验收。

## 固定任务参考与对齐

固定任务 Euler 参考逐样本按 audit 公式构造（角度单位 rad）：

```text
A = cos(yaw)·ax + sin(yaw)·ay
B = sin(yaw)·ax − cos(yaw)·ay
roll0  = atan2(B, hypot(az + 9.8, A))
pitch0 = atan2(A, az + 9.8)
scale  = min(1, 30° / hypot(roll0, pitch0))
task   = [scale·roll0, scale·pitch0, yaw]
```

candidate/B/C5/prediction-only 的 scene 加速度、yaw、导出 task Euler 与 state 时间网格均逐位相同；每份 raw 的 `raw_outer_attitude` 也逐样本等于 `command_filter_target_euler`。所有阶段在相同时间、同一方法 raw 内配对：fixed task→raw outer→filtered reference→actual state Euler（MATLAB state 第 7:9 行）。前/后窗口采用 `[0,5)` s 与 `[15,20)` s，各 5,000 个 transition 样本；root 全程 task 指标另按 audit 的 20,001 个 state 样本复算。

SO(3) 用与 v3 audit 相同的 ZYX quaternion geodesic 角计算。下面每个阶段角度均独立计算，SO(3) 角不相加。轴向统计是 wrapped Euler 分量 RMSE，不等价于 SO(3) 分量，也不用于线性合成总角。详细 signed mean、MAE、RMSE、P95、max 数据见 JSON。

## Root 指标复核

| 方法 | Task SO(3) RMS（audit 全状态） | Inner tracking RMS（filtered→actual） | 复算偏差 |
|---|---:|---:|---:|
| Candidate | 0.007240 | 0.024897 | 0.000000 / 0.000000 |
| B | 0.006024 | 0.025478 | 0.000000 / 0.000000 |
| C5 | 0.002995 | 0.025476 | 0.000000 / 0.000000 |
| Prediction-only | 0.009872 | 0.030116 | 0.000000 / 0.000000 |

四份 raw 的复算均与 `ROOT_FIRST_SCENE_PYTHON_METRICS_v1.json` 精确一致（本次双精度复算差为 0）。

## SO(3) 阶段统计：mean / RMS / P95（rad）

| 方法 | 窗口 | 固定任务→raw outer | raw outer→filtered | filtered→actual | 固定任务→actual 总误差 |
|---|---|---:|---:|---:|---:|
| Candidate | first_5s | 0.001489 / 0.001779 / 0.003313 | 0.001327 / 0.001558 / 0.002963 | 0.000290 / 0.000315 / 0.000437 | 0.000216 / 0.000307 / 0.000757 |
| Candidate | last_5s | 0.022141 / 0.023566 / 0.038190 | 0.007075 / 0.008843 / 0.018787 | 0.020051 / 0.021557 / 0.030263 | 0.008050 / 0.009030 / 0.016481 |
| B | first_5s | 0.001343 / 0.001566 / 0.002947 | 0.001332 / 0.001553 / 0.002954 | 0.000003 / 0.000003 / 0.000005 | 0.000209 / 0.000257 / 0.000537 |
| B | last_5s | 0.008128 / 0.016634 / 0.053451 | 0.003276 / 0.004932 / 0.011953 | 0.008392 / 0.015876 / 0.043939 | 0.004102 / 0.006751 / 0.015836 |
| C5 | first_5s | 0.001325 / 0.001555 / 0.002898 | 0.001328 / 0.001556 / 0.002958 | 0.000003 / 0.000003 / 0.000005 | 0.000209 / 0.000298 / 0.000729 |
| C5 | last_5s | 0.007087 / 0.015029 / 0.034003 | 0.002441 / 0.003778 / 0.009672 | 0.008394 / 0.015880 / 0.043900 | 0.001525 / 0.002490 / 0.005845 |
| Prediction-only | first_5s | 0.001490 / 0.001780 / 0.003317 | 0.001327 / 0.001558 / 0.002963 | 0.000291 / 0.000317 / 0.000441 | 0.000216 / 0.000307 / 0.000757 |
| Prediction-only | last_5s | 0.024322 / 0.026195 / 0.043613 | 0.010925 / 0.015235 / 0.036557 | 0.022879 / 0.024656 / 0.038171 | 0.011347 / 0.014819 / 0.030863 |

## Roll wrapped Euler RMSE（rad）

| 方法 | 窗口 | 固定任务→raw outer | raw outer→filtered | filtered→actual | 固定任务→actual |
|---|---|---:|---:|---:|---:|
| Candidate | first_5s | 0.001443 | 0.001302 | 0.000263 | 0.000304 |
| Candidate | last_5s | 0.013361 | 0.006507 | 0.010096 | 0.006270 |
| B | first_5s | 0.001277 | 0.001295 | 0.000003 | 0.000244 |
| B | last_5s | 0.011935 | 0.003966 | 0.006661 | 0.006335 |
| C5 | first_5s | 0.001287 | 0.001303 | 0.000003 | 0.000296 |
| C5 | last_5s | 0.008587 | 0.002214 | 0.006664 | 0.002057 |
| Prediction-only | first_5s | 0.001445 | 0.001302 | 0.000265 | 0.000304 |
| Prediction-only | last_5s | 0.011459 | 0.010859 | 0.004701 | 0.008853 |

## Pitch wrapped Euler RMSE（rad）

| 方法 | 窗口 | 固定任务→raw outer | raw outer→filtered | filtered→actual | 固定任务→actual |
|---|---|---:|---:|---:|---:|
| Candidate | first_5s | 0.001040 | 0.000856 | 0.000172 | 0.000038 |
| Candidate | last_5s | 0.019412 | 0.005988 | 0.018900 | 0.006019 |
| B | first_5s | 0.000907 | 0.000857 | 0.000001 | 0.000080 |
| B | last_5s | 0.011586 | 0.002931 | 0.014413 | 0.002322 |
| C5 | first_5s | 0.000872 | 0.000852 | 0.000001 | 0.000037 |
| C5 | last_5s | 0.012334 | 0.003062 | 0.014416 | 0.001393 |
| Prediction-only | first_5s | 0.001041 | 0.000856 | 0.000173 | 0.000038 |
| Prediction-only | last_5s | 0.023555 | 0.010686 | 0.024023 | 0.011497 |

## Yaw wrapped Euler RMSE（rad）

| 方法 | 窗口 | 固定任务→raw outer | raw outer→filtered | filtered→actual | 固定任务→actual |
|---|---|---:|---:|---:|---:|
| Candidate | first_5s | 0.000000 | 0.000000 | 0.000010 | 0.000010 |
| Candidate | last_5s | 0.000000 | 0.000000 | 0.002437 | 0.002437 |
| B | first_5s | 0.000000 | 0.000000 | 0.000000 | 0.000000 |
| B | last_5s | 0.000000 | 0.000000 | 0.000160 | 0.000160 |
| C5 | first_5s | 0.000000 | 0.000000 | 0.000000 | 0.000000 |
| C5 | last_5s | 0.000000 | 0.000000 | 0.000152 | 0.000152 |
| Prediction-only | first_5s | 0.000000 | 0.000000 | 0.000010 | 0.000010 |
| Prediction-only | last_5s | 0.000000 | 0.000000 | 0.003040 | 0.003040 |

## 判断与下一项最小区分实验

Candidate 相对 C5 的全程 task SO(3) RMS 多 0.004245 rad（约 2.42 倍），inner tracking RMS 少 0.000579 rad。后 5 秒 candidate/C5 的阶段 RMS 依次为 task→outer 0.023566 / 0.015029，outer→filtered 0.008843 / 0.003778，filtered→actual 0.021557 / 0.015880。

最小区分建议：先做一次 no-Plant、无参数搜索的 common-state shadow replay。固定一份已记录的状态序列及 task 参考，在同一时间戳把 candidate/C5 两套选项分别送过 outer-reference 与 command-filter 链路，记录 raw outer、filtered reference 和相同状态下的 inner command/innovation；这样能判断差异在共同输入下是否仍出现在参考/滤波或 inner 计算中。该 replay 只用于区分机制，不作为 closed-loop task SO(3) 放行证据。若需要验证任务指标因果效应，需另做受控的单因素配对闭环比较；本报告不请求启动它。

不要从不同闭环 raw 的阶段差异推断单组件因果；当前只有一个 scene。保持 task SO(3) 指标为最终要求，candidate 还没有优于 B/C5。

## v1 状态与审计范围

`FIRST_SCENE_REFERENCE_TRACKING_DIAGNOSIS.json` 保留 v1 原始统计，但其 `status=REFERENCE_DEFINITION_ERROR`，错误原因与本 v2 路径已写入 JSON。v1 数值不是固定任务分解，勿引用为结论。

分析数据只来自 candidate、B、C5、prediction-only 四份 `raw_run.mat`；为定位 raw 路径及核对 root 数值，另只读了 v3 manifest 的 T1 记录、candidate `run_start.json`、root first-scene metrics JSON，以及 v3 audit 中定义指标的 `metrics()/angle_error()/quat()` 片段。未读取 frozen raw；未读取任何 J 数值来重建惯量。

