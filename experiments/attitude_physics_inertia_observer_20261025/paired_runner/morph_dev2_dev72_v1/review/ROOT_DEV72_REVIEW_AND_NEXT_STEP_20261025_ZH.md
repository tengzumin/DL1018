# DEV72 独立复算审核与下一步决定

更新：2026-10-25。范围：仅审核已完成的 DEV72 candidate 对锁定 B72 配对结果；没有读取旧 TEST48 raw/指标，没有启动 TEST、训练或 Plant。

## 结论

DEV72 达到本阶段任务书的开发门，candidate 可进入冻结后的独立评估准备。当前验证是**闭环系统级比较**：candidate 使用 C5 DSSM14/M110 位置栈（冻结 encoder、normalizer、初始 W0，位置 head 按原算法在线更新），姿态采用解析惯量前馈与有界 disturbance observer，并关闭姿态 RBF 输出/更新；B 使用原位置与姿态 RBF。位置栈和姿态控制同时改变，因此收益不能单独归因姿态 RBF 替换。两臂各自生成的 filtered attitude reference 也不同，SO(3) 是各自闭环跟踪误差，不是同目标下的姿态环因果消融。

## 运行与输入核验

- A02 为 58 场 candidate-only 完整批次：58 runner/Plant 调用、1,160,000 transitions、未知调用 0、训练 0、`TEST_accessed=false`；58 场均完成且安全门通过。A01 启动前失败和其状态保持原样。
- 完整 72 场由 58 个 A02 candidate、12 个 screen12 复用 candidate、T2/T3 两个既有 candidate，与 C5 lock 中 72 份同场 B72 raw 配对；没有重跑 B/C5。所有 raw/status SHA、场景身份、A02 release/source-lock/manifest/runner SHA、逐场 pair audit、同场初态/参考/风/形态命令和 rho/rhoDot 序列均通过核验。
- 独立评分器曾因要求 `run_status` 中不存在的 `external_identity_sha256` 字段而在第一场停止，没有写结果。核对 runner 契约后，改为从 `pair_XX_audit.json` 联合 frozen manifest 核验该身份，并补齐 release 绑定及四条形态序列的逐元素比较。修正后历史自校核与 A02 首场复算通过；V3 报告记录评分器 SHA，V1/V2 均保留。

## 主要结果（V3 独立复算）

| 指标 | Candidate | B | Candidate−B | 逐场胜/平/负 | 配对场景 bootstrap 95% CI |
|---|---:|---:|---:|---:|---:|
| 位置 Q RMSE | 10.553 mm | 17.058 mm | −6.505 mm（−38.13%） | 69/0/3 | [−8.245, −4.912] mm |
| 姿态 SO(3) RMSE | 9.804 mrad | 16.338 mrad | −6.534 mrad（−39.99%） | 69/0/3 | [−7.329, −5.737] mrad |

三个任务组（HELIX、FIG8_3D、SQUARE）的 Q 与 SO(3) 平均均低于 B。W09–W14 高频组 Q 为 9.190 vs 10.719 mm（差 −1.528 mm），SO(3) 为 9.600 vs 15.506 mrad（差 −5.906 mrad）；W15 无风组 Q 为 4.401 vs 7.647 mm（差 −3.246 mm），SO(3) 为 10.642 vs 17.214 mrad（差 −6.572 mrad）。完整 W00–W15 逐风组的 Q 与 SO(3) 宏平均均低于 B。

XYZ 位置轴 RMSE 均有改善：X −4.037 mm、Y −4.547 mm、Z −0.965 mm。前 2.2 秒位置 Q 平均差 −0.852 mm，后 2.2–20 秒差 −7.757 mm；姿态前段差 +0.038 mrad、后段差 −6.926 mrad。场景等权位置误差 P95 差 −10.649 mm，SO(3) P95 差 −13.910 mrad。逐场 controller-call 时间均值的场景宏平均为 0.463 ms（B 为 0.091 ms），逐场 P95 的宏平均为 0.772 ms（B 为 0.218 ms）；该计时排除 candidate post-allocator commit，不构成完整 1 kHz deadline 证明。

所有 72 个 candidate raw 均为 STABLE；72 场均无安全停止、电机饱和、generalized clipping 或 tilt limit。72 对同场输入逐元素相同。

## 实际形态运动分组（描述性）

V3 先按命令将 66 场归为主动变形、6 场归为固定几何；随后逐一读取 72 个 candidate MAT 中的 `log.arms.rho_true`，以每场最大臂长峰峰值是否大于 `1e-6 m` 核验实际动作。结果为 66/66 主动组确有运动、6/6 固定组没有运动，命令与实际运动 0 个不匹配；最大臂长峰峰变化约 `0.10 m`。

| 分组 | n | Q Candidate / B | Q Δ（mm），胜/平/负 | SO(3) Candidate / B | SO(3) Δ（mrad），胜/平/负 |
|---|---:|---:|---:|---:|---:|
| 实际主动变形 | 66 | 10.558 / 16.956 mm | −6.398，65/0/1 | 10.682 / 17.813 mrad | −7.131，66/0/0 |
| 固定几何 | 6 | 10.505 / 18.180 mm | −7.675，4/0/2 | 0.145 / 0.112 mrad | +0.033，3/0/3 |

此分组只说明系统级差异在主动变形场景中与固定场景不同：位置两组均优于 B；姿态组平均改善集中在主动变形组，固定几何组 `n=6` 且均值略差。它不能识别“主动变形本身造成了改进”，因为 B 与 candidate 同时运行了相同的变形输入，但两者位置控制器和生成的姿态参考不同。不得将此写成形态变化的因果收益。

## 退化场与解释边界

Q 退化的三场：`DEV_T2_C09_W10` +0.409 mm、`VAL_T2_C00_W10` +0.252 mm、`VAL_T3_C00_W13` +0.841 mm；SO(3) 退化的三场：`VAL_T1_C00_W07` +0.029 mrad、`VAL_T2_C00_W10` +0.186 mrad、`VAL_T3_C00_W13` +0.177 mrad。四个不同场景的退化都小于 1 mm 或 0.2 mrad；没有安全异常，位置峰值仍低于 B。三个 Q 退化分别主要来自早/中段 Y 或前段 X/Y 的小幅残差，未见足够证据归因形态事件或姿态 RBF。目标姿态参考本身跨臂不同，故不能以 SO(3) 差值解释单一姿态机制。

复用 T2 的旧 `run_status` 仍标为 `FAILED_ENGINEERING`，本复算不改状态；既有独立审查认为这是旧 trace-shape 检查器误报，raw 稳定且因果 trace 已复核。V2 汇总保留这一标签和一个历史 gate-failed 计数。

## 论文主张边界与下一步决定

- 只读源码审计确认 B 锁与 candidate 锁中的 22/22 Plant 文件相同，28 个同名公共 helper 也同 SHA；但两个闭环入口不同，且 B 与 candidate 的位置栈及其闭环姿态参考值不同。因此 DEV72 的改善是系统配置比较，不能单独支持“physics/observer 姿态环优于原 RBF”的因果主张。下一次姿态机制比较应增加同一 C5 DSSM14/M110 位置栈 + 原 B 姿态 RBF 的 matched control；该 arm 可与 physics candidate 共用隔离 runner，除姿态 RBF 开关/physics helper 外选项完全相同。
- candidate helper 只读取当前角速度、BS 名义角加速度、形态命令、离散事件和冻结 `cfg`；静态公式审查未发现直接读取 `rho_true`、Plant wrench 或实际力矩的路径，补偿符号与 `M_nom - estimateTorque` 接线相符。观测残差是 applied-minus-command、风和模型误差等混合项；限幅只保证补偿输出有界，不推出 observer 收敛、闭环稳定或状态安全。部署结论依赖已知 distributed-v1 模型和准静态形态假设。
- 当前 HELIX/FIG8_3D/SQUARE 场景没有门洞、障碍接触或通行指标。实际 `rho_true` 核验只证明预设动作确实发生，不能证明主动变形比固定几何更有任务价值。机体桨半径 `0.0635 m` 也只标为五英寸桨几何估算。
- 因此不把通用 HOLDOUT48 直接当作应用验证。下一阶段先冻结一个独立 gate-inspection mission：出门、开阔区横向检视机动、回门；设置同轨迹/初态/风下的主动形变、固定安全短形态和固定宽形态，并对 candidate 增加匹配姿态 RBF arm 与 feedforward×observer 消融。门洞净空只按离线几何包络复核；Plant 没有碰撞响应，不能写成碰撞仿真通过。新任务的无 Plant 轨迹/包络审核通过后再做独立场景 pilot，pilot 后冻结未使用的 48 场 holdout，holdout 一次性执行且不回调参数。文献与代码库对照见 `MORPH_ATTITUDE_LITERATURE_AND_CODE_REPOS_20261025.md`。

## TEST 决定

不使用旧 `experiments/c5_test48_v9` 作为新 candidate 的独立 TEST。只读路径/marker 清点显示旧 TEST 已有 C5FREEZE、C5M110、C5NOPRED、KAN 各 48 个实际航次，以及 DSSM 32 个；旧 source manifest/release 还存在状态矛盾，旧方法清单不含当前 attitude replacement。其 raw 与性能指标没有被本轮打开。旧 TEST 结果不得用于新 candidate 的独立背书或调参。

下一阶段任务书尚未放行任何航次；旧 `experiments/c5_test48_v9` 与新的 holdout 分开封存，不能重命名为独立测试。先完成 gate mission 的输入生成、包络与因果消融设计，再写一次性执行授权。

## 复现文件

- `DEV72_INDEPENDENT_RESCORE_v3.json`：72 场完整数据、指标、身份、风组、形态命令组和不确定性。
- `DEV72_INDEPENDENT_RESCORE_v3.csv`：逐场结果表。
- `DEV72_INDEPENDENT_RESCORE_GUIDE_v1_ZH.md`：指标定义与运行方式。
- `ATTITUDE_PHYS_INERTIA_DEV72_TASKBOOK_v1_ZH.md`：本轮冻结任务书；TEST48 不在其执行授权内。
