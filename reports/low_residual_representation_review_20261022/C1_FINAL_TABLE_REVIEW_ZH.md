# C1 固定 12 场独立表级复核

本复核只读冻结CSV/JSON、run_status.json和run_start.mat；不打开或重哈希raw_run.mat，不启动仿真。
组均值和逐场配对从per-run表独立重算，并核对worker的全部task×wind-band、风带、HF合并及宏平均表。

- 结果：**STOP_FROZEN_PERFORMANCE_GATE_FAILED**。场景12、条件B/ON1/ONC共36条；复用v8首场B一条，v9新运行35条。
- 源锁SHA256：`02668f6268944715e65e6d2cffa52b395417506132212b00e7d273d88df164e5`；v9 release SHA256：`7aa072835b0e633f9e40d0e471a17870735d32ddf079eafc61ac6790ea7974d0`；固定c*=0.280297964806146。
- 行级输场比较：ONC−ON1 12条，ONC−B 12条；完整列表见JSON。

## 固定组门

组门采用冻结规则的严格未舍入均值 `ONC <= 对照`；1e-12 m 仅用于逐场胜负分类。

- FAIL `W15_mean_ONC_le_B`；ΔQ=0.003437374439988811 m。
- FAIL `W15_mean_ONC_le_ON1`；ΔQ=0.0030815299435766261 m。
- FAIL `HF_W09_W14_mean_ONC_le_B`；ΔQ=0.0046459283577301395 m。
- FAIL `HF_W09_W14_mean_ONC_le_ON1`；ΔQ=0.0045658525110285463 m。
- FAIL `ALL12_mean_ONC_le_ON1`；ΔQ=0.0043614839890883956 m。

## 早晚段与饱和记录

下表为逐场RMSE先算、再按场景等权平均；单位mm。它说明W15的早段优势不能替代全程门：ONC早段1.991mm优于ON1的3.406mm，晚段13.851mm却高于ON1的10.080mm。

| 分组 | 条件 | Q(0–20s) | Q(0–5s) | Q(5–20s) |
|---|---|---:|---:|---:|
| W15 | B | 8.629 | 1.509 | 9.889 |
| W15 | ON1 | 8.985 | 3.406 | 10.080 |
| W15 | ONC | 12.066 | 1.991 | 13.851 |
| HF W09–W14 | B | 9.633 | 13.751 | 7.428 |
| HF W09–W14 | ON1 | 9.713 | 14.046 | 7.578 |
| HF W09–W14 | ONC | 14.279 | 21.053 | 10.658 |
| ALL12 | B | 10.349 | 11.592 | 9.164 |
| ALL12 | ON1 | 9.787 | 11.572 | 8.520 |
| ALL12 | ONC | 14.148 | 16.695 | 11.967 |

per-run表中36/36行的`motor_saturated_fraction`与`generalized_clipped_fraction`均为0。冻结primary scorer标记36条均稳定、完整、finite，并检查无`safety_stop_reason`；这是这些记录上的安全观察，不外推为全状态范围或更广工况的安全证明。所有实际耗时仍标记为`NON_RESEARCH_DESKTOP_LOAD_CONTAMINATED`，不得作为正式效率结论。

## 结论边界

该脚本独立核对表格汇总和来源/运行小型元数据，但没有第二次读取原始轨迹计算Q。全程Q与物理身份由主审原始H5复核/历史源审查提供；本表复核不重新读raw。本次筛查失败，不授权继续扩场、72场或TEST。计时保留桌面负载干扰标记，不能作正式效率结论。
