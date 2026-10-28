# 姿态 RBF 替代：冻结物理方法与 C5 同栈 12 场筛查

日期：2026-10-25。此任务书批准隔离实现、静态检查和无 Plant 检查；闭环启动须等 root 审核实现、实际场景清单与输入锁后签发 root release。不得改写 T3 continuation v1 或历史 raw/status/receipt。

## 目的与当前选择

目标是评估主动变形四旋翼位置 C5 栈中的姿态 RBF 替代价值。位置环仍用冻结 C5 DSSM14/M110/在线头，姿态 baseline 用原 B 在线 RBF；candidate 使用已有解析方法 `phys_attitude_replacement_candidate_v2.m`：命令积分估计臂长，计算时变惯量/惯量导数前馈，并以有界 disturbance observer 补偿合扰动。

不再训练静态 CM18：已有 15 个留出 DEV 场景中，C5_COVERAGE33 的等场景 Q 与 SO(3) 均值明显差于 RBF。当前物理 candidate 在既有 C02/W15 与 T3/C10/W11 两场都安全完整且优于同栈 RBF；T3 candidate−baseline 的 Q RMSE 为 −2.324 mm、SO(3) RMSE 为 −0.01004 rad。该信号仍是开发证据，不足以直接宣称普遍有效。

## 冻结对照与输入

- 唯一代码候选：`experiments/attitude_physics_inertia_observer_20261025/phys_attitude_replacement_candidate_v2.m`。保持当前方程、0.05 m/s 命令积分速率、observer 0.10 s 时间常数、现有 `dmax` 与 `beta_rise_time`；不调参、不训练、不加新状态信号。
- baseline：冻结 C5 位置方案 + 原姿态 RBF online update/output。
- candidate：同一 C5 位置模型、normalizer、W0、M110、BS/Plant/allocator/滤波/限幅和初始状态，仅关闭姿态 RBF，并启用上述物理 helper。
- 两臂同场、同 seed、同 1 ms 步长、同 20 s 轨迹；每臂 20,000 transitions/20,001 states。每场 baseline 先于 candidate。
- helper 仅可使用形变命令 `u[4]`、机体系角速度 `omega[3]`、补偿前名义机体系角加速度 `alphaBS[3]`、上一完整 100 Hz 区间的 controller-clipped 力矩命令与时间戳，以及固定 nominal `J0`/几何配置。不得读取真实臂长、Plant 真值、真实风矩、实际电机力矩或 `realized_generalized`。
- 必须保留逐样本因果审计：输出先于当前区间 commit；observer 只消费已完成区间；`estimateTorque=-tau_comp`；姿态 RBF flags/offline-online outputs/weight histories 全零。

## 固定首轮 12 场

严格复用 C5 首轮固定筛查 cohort，不重选：

`DL1018_VAL_T1_C00_W07`, `DL1018_VAL_T1_C02_W09`, `DL1018_VAL_T1_C05_W12`, `DL1018_VAL_T1_C08_W15`, `DL1018_VAL_T2_C00_W10`, `DL1018_VAL_T2_C02_W12`, `DL1018_VAL_T2_C05_W15`, `DL1018_VAL_T2_C06_W00`, `DL1018_VAL_T3_C00_W13`, `DL1018_VAL_T3_C02_W15`, `DL1018_VAL_T3_C03_W00`, `DL1018_VAL_T3_C12_W09`。

scene specs、seeds、cfg 与 C5 model/normalizer/options 必须来自同一份可验证输入清单；实现阶段先输出完整实际 SHA manifest，再由 root 冻结。C02 `DL1018_DEV_T2_C02_W15` 与 T3 `DL1018_DEV_T3_C10_W11` 已完成的两组结果可另列，不代替这 12 场，也不得重复运行。

完整开发 cohort 为位置 C5 的原 72 场。上述 C5 12 场属于其中的 VAL48；已完成的 C02/T3 两组属于 DEV24，并因两份独立 raw 复算通过、39 源/17 输入锁相同而允许原样复用。故 12 场首筛通过后，补齐 58 个尚未配对的场景即可完成 72 场，禁止重跑这两场或重复计算场景等权宏平均。

## 预注册记录与筛查门

每场输出 baseline、candidate、candidate−baseline，逐场和场景等权汇总：SO(3) 主姿态 RMSE/峰值、按轴 attitude-error RMSE、位置 Q/XYZ RMSE/峰值、首个变形事件前后与 active-phase 分段值、角速度峰值、motor saturation、generalized clipping、tilt limiting、安全停止、非有限值、controller-call p50/p95/max 和原始 MAT SHA。保持原始未舍入值；同时报告极小收益的敏感性。

扩展完整 DEV72 前需同时满足：12/12 两臂完整 STABLE；candidate 无新增安全停止、非有限值、饱和或裁剪；宏平均位置 Q 不劣于 baseline（容差 1e−9 m）；宏平均 SO(3) RMSE 严格优于 baseline；W09–W14 高频组及 W15 无风组的 SO(3) 均值均不劣。输场逐项保留。若未通过则停止扩展，不在同一 12 场上边看边调参数。

## 资源、范围和推进

- 本轮上限 24 次 Plant 调用/480,000 transitions；计划新产物上限 10 GiB，C 盘启动前至少 30 GiB 可用。单 MATLAB 重负载作业、串行航次；不打断任何已运行实验。只用 PowerShell 7。
- 不读、不运行、不修改 TEST48；不训练或访问 TEST。C7 继续暂停。C5 历史结果与原始数据不覆盖、不删除。
- 源码、manifest、attempt 与报告仅写本隔离子目录。若 12 场门通过，root 在新版本 taskbook 中放行余下 DEV72 场景；完整 DEV 通过并冻结全部代码/参数/统计后，才准备独立 TEST48。
- root 负责实现审核、raw 独立复算和继续/修复/停止决定；执行者不自行扩场、不更改参数或统计门。
