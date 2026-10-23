# 当前续作入口

**最新进度（UTC 2026-10-23 10时后）：**严格消融两配置的12场均已自然OS0且全部raw/47,232事件主审通过。FREEZE平均Q31.106419mm、NO_PRED 9.710166mm、完整C5 9.055650mm；NO_PRED相对C5为3胜9负，无风3场均较差。见 `C5_ABLATION_SCREEN12_DECISION_ZH.md`、`c5_matched_ablation_parent_raw_review/SCREEN12_PARENT_COMPACT_v1.json` 及全部配对CSV。两个v3 FIRST加v4各11场均已结束，不重跑。当前累计自然完成180航次，训练0、TEST0。正在隔离实现两配置各补60的DEV72入口；尚未放行任何新增Plant。

物理引理非作者复核已实际落盘，主审以独立勘误明确恢复为“第二行加M乘第三行”，并完成实际M110三轴21基向量精确检查OS0。原冻结证明不改；条件误差界的代数通过，最终论文理论/贡献门仍待综合审核。下文按阶段保留的旧状态以本段及 `STATE.json` 为最新状态依据；旧失败账本不删除。

最新可机读状态见 `STATE.json`。任务仍在进行，论文证据包尚未达标；TEST未打开，原总截止 `2026-10-24T17:01:00Z` 保持。新增航次已获用户授权，毋须重复询问，但每批输入/源码/工程准备必须主审放行。主模型审查决策，最多两名 Luna xhigh 执行者；速度设置工具不提供。只用PS7、不打断旧实验、不删历史数据，磁盘预留后≥30GB，总新增产物≤80GB。

## 已完成并审核

- 新可追溯B72：主审读取新旧144个raw，全部72场33个数值数组逐元素完全相同。新基线可用；这不追溯补齐旧运行源码缺口。见 `baseline_b_dev72_parent_review/B72_PARENT_FINDINGS_ZH.md`。
- C3固定DEV72：61/72胜B（要求62），HF17/28，无风6/6。均值收益存在，整体验收仍未过。旧阶段只读保留。
- C4固定12场：全事件工程审核通过，科学门失败，不扩72。
- C5固定12场：全部23,616事件主审复算，五个预登记门通过；10/12胜，两个输场均保留。见 `c5_axis_coordinate_parent_review/C5_SCREEN12_PARENT_FINDINGS_ZH.md`、全配对CSV和 `figures/fig_c5_screen.pdf`。
- C5尾批v1：一MATLAB启动在Plant前因错误JSON对象字段退出1，0航次。原证据全部保留。v2只作字段来源修复及执行文件版本化，11场单批一次执行自然OS0，主审读取raw复算通过。
- 本续作自然完成156航次（B1+C4×12+B71+C5×72）；0训练、0新TEST。

## 正在做什么

C5固定DEV72已完成并主审全raw PASS：64/72胜、8负0平，所有胜场改善超过10微米。总体Q11.558928mm vs B17.058081mm；HF28 Q10.179304mm vs B10.719024mm，20/28胜；W15 Q6.334075mm vs B7.647292mm，6/6胜。每个任务和全部输场见 `c5_dev72_parent_review/C5_DEV72_PARENT_FINDINGS_ZH.md`。C5相对C3为53胜/19负，退化也保留。论文证据包未达标，TEST未打开。

新增60场单批session76276自然OS0，UTC08:01:29至08:26:46，MATLAB已退出；不要重启批次。全审v4只兼容账本8处UTC小数秒尾零格式，其余字段严格相等，原d7 checker及全部输入/输出不改。主审实际核60新raw118080更新，加12旧场23616，共141696事件；独立物理检查216raw，电机/广义输入/倾角命令限幅全为0，C5 head/surface clip全0。只描述这些轨迹，不作为稳定性证明。当前续作自然完成156航次，训练0/TEST0。

执行者 `c4_coordinate_execution` 按已审任务书实现两个严格消融：实际冻结W0、仅移除旧预测梯度。core/wrapper逐字复用，仅helper干预实际更新，不关原update/delayed flag。v1两配置实际无Plant自然OS0，根独立读snapshot核cfg120/opts43/model6/W0及12场sceneIdentity与原C5一致；FREEZE的FIRST在进入Plant前因漏定义scene_row而OS1，0attempt/0Plant，NO_PRED未启动。根源码审核也漏了该函数。原RUNNING batch和OS1均原位保留；该RUNNING并非仍在运行，不可据此结束进程或抢锁。

v2只修复scene_row、让共同preflight实际调用两种查找、把正式查找放进已有try；无算法变化。但PS taskDir残留v1目录，NoRetry guard在MATLAB启动前阻断，0MATLAB/0Plant。最新v3目录 `experiments/position_c5_matched_ablations_v3_20261023` 正在修启动路径：四份PS从自身PSCommandPath推导taskDir，MATLAB cd同步动态取该路径。旧v1/v2不再启动；新版本须主审检查实际路径与SHA后重新放行无Plant/FIRST，禁止自动重试、补11或扩72。目前严格消融实际航次仍为0，本续作自然完成仍为156。

五方法完整DEV72二次汇总见 `c5_all_method_dev_comparison/v2/README_ZH.md`，根已实际逐字节复算OS0。C5对原correctedDSSM14为60胜12负，对KAN14为71胜1负，全部对照/退化保留。v2明确区分父审计锁与方法自身运行身份；旧v1汇总不作为最新来源。

物理forcing引理已由执行者撰写、主审独立核验：`u−d0=epsilon_M+M*r_f`，精确采样关系、PCF极点抵消和有限卷积界通过；42个有理数基向量检查及12个来源/产物SHA通过。见 `physical_residual_tracking_lemma/PARENT_SCOPE_DECISION_ZH.md`。这仅接受条件误差界，不宣称实际Plant先验稳定；非作者执行者复核及最终理论门仍待完成。旧均匀unit-feature球标量证书对所有U都不能覆盖当前W0，不能继续搜索U凑证书。执行者 `b_probe_execution_fresh` 已转入两个消融 helper/fixture 的非作者代码复核，不启动实验。

## 复算与下一关

```powershell
python 'reports/paper_continuation_20261023/c5_axis_coordinate_parent_review/score_c5_screen12_parent.py'
python 'reports/paper_continuation_20261023/finite_horizon_certificate/parent_review/check_delay_storage_parent.py'
python 'reports/paper_continuation_20261023/finite_horizon_certificate/parent_review/check_perturbation_parent.py'
```

上述命令均实际退出0，已有输出时拒绝覆盖。审计重做应保留原目录并版本化输出，不重跑已完成Plant。当前完整DEV72性能已通过。下一步完成严格消融、贡献/理论审核与最终冻结，才可能解封一次TEST48。

代码库当前 `origin=https://github.com/tengzumin/DL1018.git`，分支 `codex/dl1018-causal-diagnosis-upload`。已审核开发集代码/报告/表图提交并推送为 `3712e0355eeff4dd3547a46d74a0ccb7d7cd57fb`，远端分支已实际核对。该批未包括尚在实现的消融及未审理论新稿；不上传MAT/checkpoint/cache/夹具/MATLAB偏好证书或私钥，不批量暂存工作区。后续Git写操作使用 `-c maintenance.auto=false -c gc.auto=0` 避免自动打包占用实验资源。

最终完整DEV72审计命令（已真实退出0；只读raw不Plant，已有输出拒绝覆盖）：

```powershell
python reports/paper_continuation_20261023/c5_dev72_parent_review/audit_c5_dev72_raw_parent_v4.py --batch-version v3 --output reports/paper_continuation_20261023/c5_dev72_parent_review/C5_DEV72_RAW_PARENT_REVIEW_v3.json
```

根独立分组复算、成对场景区间、全输场/物理检查与图表目检已完成。消融只放行实现/无Plant阶段，TEST仍封存。
