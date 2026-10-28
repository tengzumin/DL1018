# Current physical TRAIN24: paired W09 frequency audit

更正后的只读审计。物理 TRAIN_C5_24 manifest 的 canonical scene ID 使用 `DL1018_DEV_*` 前缀；本次精确使用 `DL1018_DEV_T1_C10_W09`、`DL1018_DEV_T3_C09_W09`，并对照同场 B、C5、冻结 GRU parent 和当前 candidate raw。谱分析没有运行 Plant/MATLAB、没有读取 TEST raw/score、没有做惯量重建。
此前 sibling audit 中 `data/raw/train/DL1018_TRAIN_*` 的计算属于旧 TRAIN 前缀，不是这里的当前 physical TRAIN24；其数字已在旧目录另附 erratum，已撤回，不能引用到当前结论。

## 高频定义与队列

冻结 scorer 按末尾 W 编号分组，W09–W14 标记为 `HF_W09_W14`。WN12 taskbook 对每种 topology 选 W09–W14 中最低风 DEV 与最高风 VAL 各一场，形成 W09/W14 配对；这里的 HF 指风场条件分层，不是按任务轨迹频率分组。当前两条 W09 raw 的环境风谱主峰为 f1=2.2 Hz、f2=3.2 Hz；相应积分窗为 `[1.5,2.5)` 与 `[2.5,3.5)` Hz。
环境风写入 `environment_wind_I`。task attitude 仅由 reference acceleration、reference yaw、重力和 30°倾角上限重建，不直接含风。两条任务轨迹分别是 HELIX 和 SQUARE，reference 的主要谱在 0.05–0.5 Hz，因此这两条 W09 的高频标签来自风输入。
当前物理 TRAIN24 的24个ID虽以 DEV 为 canonical 前缀，但 manifest 标明其等于 parent DEV24；冻结 GRU parent 已见过这些场景，所以这是 in-sample 开发诊断。

## task→command、姿态误差与分频结果

每格为 mrad；`task→command` 是 task reference Euler 减 raw 中 logged `command_filter_target_euler`。`task−actual` 总分按冻结 scorer 的任务姿态公式、20001个 state 计算；谱表使用前20000个共时 transition。

| scene | method | command target 平均 roll/pitch | task→command 平均 roll/pitch | task→command SO(3) RMSE | task→actual 平均 roll/pitch | task→actual SO(3) RMSE | task−actual bias² / score²¹ |
|---|---|---:|---:|---:|---:|---:|---:|
| DEV_T1_C10_W09 | B | -29.569/19.039 | 29.583/-19.039 | 43.992 | 34.011/-21.254 | 42.201 | 90.3% |
| DEV_T1_C10_W09 | C5 | -29.586/19.036 | 29.600/-19.037 | 48.514 | 33.944/-21.237 | 43.273 | 85.6% |
| DEV_T1_C10_W09 | GRU_PARENT | -29.825/19.141 | 29.840/-19.142 | 47.278 | 33.944/-21.244 | 43.308 | 85.5% |
| DEV_T1_C10_W09 | CURRENT_CANDIDATE | -29.840/19.149 | 29.854/-19.149 | 47.047 | 33.947/-21.242 | 43.168 | 86.1% |
| DEV_T3_C09_W09 | B | -5.659/55.506 | 5.659/-55.506 | 59.448 | 4.006/-56.881 | 59.061 | 93.2% |
| DEV_T3_C09_W09 | C5 | -5.579/55.356 | 5.579/-55.356 | 65.378 | 3.984/-56.850 | 60.705 | 88.1% |
| DEV_T3_C09_W09 | GRU_PARENT | -5.406/55.472 | 5.406/-55.472 | 65.233 | 3.984/-56.850 | 60.663 | 88.3% |
| DEV_T3_C09_W09 | CURRENT_CANDIDATE | -5.421/55.459 | 5.421/-55.459 | 65.227 | 3.982/-56.833 | 60.621 | 88.3% |

¹ bias² 比例是小角度 Euler 近似，只说明偏置主导程度，不是 SO(3) 严格可加分解。

| scene | method | task−actual f1 band [1.5,2.5) Hz RMS | task−actual f2 band [2.5,3.5) Hz RMS | actual f1/f2 band RMS | task f1/f2 band RMS |
|---|---|---:|---:|---:|---:|
| DEV_T1_C10_W09 | B | 3.567 | 0.894 | 3.567/0.894 | 0.000/0.000 |
| DEV_T1_C10_W09 | C5 | 12.413 | 6.376 | 12.413/6.376 | 0.000/0.000 |
| DEV_T1_C10_W09 | GRU_PARENT | 12.329 | 6.328 | 12.329/6.328 | 0.000/0.000 |
| DEV_T1_C10_W09 | CURRENT_CANDIDATE | 11.705 | 6.450 | 11.705/6.450 | 0.000/0.000 |
| DEV_T3_C09_W09 | B | 4.253 | 1.238 | 4.296/1.144 | 0.626/0.261 |
| DEV_T3_C09_W09 | C5 | 16.647 | 8.763 | 16.538/8.726 | 0.626/0.261 |
| DEV_T3_C09_W09 | GRU_PARENT | 16.375 | 8.709 | 16.269/8.670 | 0.626/0.261 |
| DEV_T3_C09_W09 | CURRENT_CANDIDATE | 16.060 | 8.851 | 15.947/8.819 | 0.626/0.261 |

两场风谱在 f1/f2 两频带的向量 AC RMS 分别为 1.061/0.707 m/s。任务姿态在这些频带几乎没有能量，但 command target 已显著高于 B，滤波后的 reference 保留相近的相对增量，actual 又紧跟 filtered reference：

| scene | method | command target f1/f2 band RMS (mrad) | filtered reference f1/f2 band RMS (mrad) | actual f1/f2 band RMS (mrad) |
|---|---|---:|---:|---:|
| DEV_T1_C10_W09 | B | 4.761/1.773 | 2.992/0.790 | 3.567/0.894 |
| DEV_T1_C10_W09 | C5 | 19.994/15.019 | 12.555/6.697 | 12.413/6.376 |
| DEV_T1_C10_W09 | GRU_PARENT | 20.068/14.935 | 12.595/6.660 | 12.329/6.328 |
| DEV_T1_C10_W09 | CURRENT_CANDIDATE | 19.085/15.245 | 11.974/6.800 | 11.705/6.450 |
| DEV_T3_C09_W09 | B | 6.429/2.528 | 4.049/1.130 | 4.296/1.144 |
| DEV_T3_C09_W09 | C5 | 26.280/19.925 | 16.550/8.890 | 16.538/8.726 |
| DEV_T3_C09_W09 | GRU_PARENT | 26.016/19.983 | 16.385/8.916 | 16.269/8.670 |
| DEV_T3_C09_W09 | CURRENT_CANDIDATE | 25.520/20.287 | 16.064/9.054 | 15.947/8.819 |

B、C5、parent 与 candidate 的 task→command 均值偏置大致相同。command→filtered 的 f1/f2 幅值比也接近（约0.63/0.45），filtered→actual 误差较小。因此 B 与 current candidate 的 task 分数差并非 DC 偏置变化，主要与外环 command target 在 2.2/3.2 Hz 风频邻域的 AC 增量相关；没有观察到内环或共同滤波器传递比例发生明显变化。T1 candidate 比 parent 略好，T3 candidate 与 parent 接近，但两场仍分别比 B 高0.968与1.559 mrad。该频带关联来自配对 raw 的路径定位，不能单凭此证明风是唯一因果来源；不同路径 SO(3) RMSE 不可代数相加。

## 解释与局限

任务姿态在 2.2/3.2 Hz 带内接近零，actual−task 分频误差基本由 actual 的风频振荡贡献。command target 已出现高频增量，说明差异在姿态命令形成阶段；滤波器与 actual tracking 传递了该增量，而非制造了它。
只分析了 physical TRAIN24 内两个 W09 场景。它们属于 GRU parent 已见过的 DEV24，不能当作独立验证，也不能外推到整个 HF6 或全部 TRAIN24。C5 raw path/SHA 已锁，但上游 full72 manifest 将对应 C5 项标为 raw-pending-audit；此处仅作锁定 raw 频谱诊断，不升级其审计状态。旧前缀计算更正见 sibling `hf_definition_train_raw_audit_v1/WRONG_COHORT_ERRATUM_v1.md`；证据 SHA、raw 路径及逐轴结果记录在本目录 JSON/CSV。
