# 两场主动形变 DEV 的固定方法诊断任务书 v1

2026-10-25，root 决策。当前**仅批准隔离执行入口的实现与静态检查，不批准 MATLAB/Plant 航次**。实际放行必须等离线 C00 公式/血缘核验完成、root 审核新入口和完整锁，并另发准确 release。执行者仅用 GPT‑6‑Luna xhigh，root 负责审核和决策。

## 前一轮结论与本阶段问题

原 DEV3_A01 已严格失败并终止，不改判据、不覆盖结果：C00/W03 的 candidate Q 比 baseline 高2.5209584565e-7 m，SO(3) RMSE 高1.34242585e-6 rad；两臂均 STABLE、20000 transitions，所有 saturation/clipping/tilt计数0。仅消耗2航次/40000 transitions，余4航次未执行。root 独立读新raw复算、原始MAT/status/receipt/source/input SHA审核均通过，见 `root_review_v1/DEV3_A01_INDEPENDENT_REVIEW_v1.json`。

该场没有形变：同记录物理wind torque RMS约1e-20～1e-18 Nm，actual-minus-clipped torque约1e-16 Nm，candidate估计约1e-12 Nm；旧RBF的误差面更新仍给出约1e-7 Nm修正。命令滤波器采用半隐式离散积分，存在可精确核对的相对于连续ZOH加速度参考的0.5dt²a项。以上不证明该项是闭环差异唯一原因，也不把数值小直接当作因果证明，但说明C00不能单独回答主动形变应用价值。

本阶段唯一优先假设：**固定的形态惯量前馈+扰动observer在真实形变工况中有可测应用收益，而C00揭示它不能替代RBF全部名义跟踪修正功能。** 目的为区分应用域，非宣布旧DEV3筛查通过。若离线核验发现实质实现错误，先停止本阶段放行并回到错误修复，不带错实现跑Plant。

## 固定对照和禁止改动

只使用原6航次计划尚未运行的4次、下列两场。39个部署源、cfg/J0、DSSM14模型/W0/normalizer、C5 position stack、BS/command filter/执行器、dt/种子与candidate helper完全冻结，逐项等于 `dev3_v1/source_lock_paired_runner_v1.json` 和原preflight候选输入锁。禁止训练、调参数、改滤波积分、加deadzone、选Head、拼B轴、读TEST或旧raw。baseline与candidate每场均fresh，各一次，不复用别的源码身份的baseline。

| 顺序 | scene ID | seed | 目的 |
|---|---|---:|---|
| 1 | DL1018_DEV_T2_C02_W15 | 2026122847 | 三维八字、臂2主动形变、零风；检验形态惯量/分配变化下的价值 |
| 2 | DL1018_DEV_T3_C10_W11 | 2026123971 | 方形轨迹、臂3/4形变、有风；检验交互工况及边界 |

每场仍为baseline→candidate，共用同一生成一次的scene内存对象；spec/scene/metadata SHA必须等于已通过的preflight锁。模型只load已allowlist的model变量，C5 snapshot只load cfg/opts/W0/modelIdentity；无其它MAT输入。

## 新入口和停止规则

仅在 `paired_runner/morph_dev2_diagnostic_v1/` 新建最小MATLAB wrapper、PowerShell7 launcher、静态审计及候选锁；复用已审DEV3入口的身份、CreateNew、raw先保存、评分与血缘检查实现，不引入通用调度框架。不得修改或调用旧DEV3 launcher重跑；原39部署源与全部旧文件原样保留。

新scope/schema必须明确是 `MORPH_DEV2_DIAGNOSTIC`，最终冻结输入锁与root批准release分离；无准确release路径/SHA或未冻结输入时拒绝调用runner。锁包含39部署源、17既有输入、新执行入口及实际依赖，运行前后复核全部SHA、规范common/effective options和场景；attempt已存在就拒绝重跑。禁止任何自动修复或重试，不结束/抢占已有进程。只用PowerShell7、一个MATLAB进程串行，不启动GPU训练。

工程或安全失败即停后续，raw/status/已算指标/异常完整保留；candidate仍要求STABLE/完整20000 transitions/20001状态、无安全停止、motor saturation=0、generalized clipping=0。tilt及Q/SO(3)结果全部报告。**性能升降本身不阻止下一诊断场**，因为本阶段在看到这两场任何结果前预登记要完整回答应用域；它不使用 `DEV3_SCREEN_PASS`、不自动进入72场/TEST、不把负结果改为通过。

计分完全沿用既定方法：Q为0–20 s全部20001状态点3D位置RMSE；SO(3)为20000控制区间的ZYX旋转测地RMSE，不伪造t20姿态参考。报告逐轴位置RMSE、位置/姿态峰值、early 0–2.2s与late 2.2–20s、未舍入配对差值、安全/饱和/tilt、部分controller_time口径及run墙钟。candidate全trace有限性、prepare/commit时戳/命令/omega/clipped torque、RBF关闭、signed estimate=-tau_comp必须核验。不得用不同闭环状态的组件输出差证明机制。

## 资源、审核及后续决定

新阶段最多4次runner调用；加旧A01累计至多6次，不重复C00。本阶段新增产物预算2GiB：首对实际raw为48.2MB+440.1MB，按三对线性预测约1.46GB，原1GiB不足原完整三对；形变trace还可能更大，因此明确记录本次资源调整，当前磁盘约194GiB。启动前和每航次前仍需≥30GiB可用，记录首对真实bytes/墙钟并估计后续，不启动明显超剩余预算的作业，不删除任何产物。

产物包括实际启动账本、不可覆盖的每臂原样`log` MAT及start/status/scene audit、每对diagnostic audit、全部正负结果表、batch stdout/stderr/receipt、短报告、可复现命令及完整锁。root从新raw独立复算，最后将C00失败和两场诊断**共同**列出，不只呈现形变赢场。

若两形变场无可信收益，否定当前应用收益假设，下一步只做有依据的最小机制分辨或停止该路线；若存在收益，先明确无形变退化和理想状态反馈/理想命令形态模型边界，再由root预登记更全面DEV、关键消融与理论/应用价值审核。这里没有任何论文证据包达标或TEST授权。
