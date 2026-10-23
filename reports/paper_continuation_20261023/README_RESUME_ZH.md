# 当前续作入口

最新可机读状态见 `STATE.json`。任务仍在进行，论文证据包尚未达标；TEST未打开，原总截止 `2026-10-24T17:01:00Z` 保持。新增航次已获用户授权，毋须重复询问，但每批输入/源码/工程准备必须主审放行。主模型审查决策，最多两名 Luna xhigh 执行者；速度设置工具不提供。只用PS7、不打断旧实验、不删历史数据，磁盘预留后≥30GB，总新增产物≤80GB。

## 已完成并审核

- 新可追溯B72：主审读取新旧144个raw，全部72场33个数值数组逐元素完全相同。新基线可用；这不追溯补齐旧运行源码缺口。见 `baseline_b_dev72_parent_review/B72_PARENT_FINDINGS_ZH.md`。
- C3固定DEV72：61/72胜B（要求62），HF17/28，无风6/6。均值收益存在，整体验收仍未过。旧阶段只读保留。
- C4固定12场：全事件工程审核通过，科学门失败，不扩72。
- C5固定12场：全部23,616事件主审复算，五个预登记门通过；10/12胜，两个输场均保留。见 `c5_axis_coordinate_parent_review/C5_SCREEN12_PARENT_FINDINGS_ZH.md`、全配对CSV和 `figures/fig_c5_screen.pdf`。
- C5尾批v1：一MATLAB启动在Plant前因错误JSON对象字段退出1，0航次。原证据全部保留。v2只作字段来源修复及执行文件版本化，11场单批一次执行自然OS0，主审读取raw复算通过。
- 本续作自然完成156航次（B1+C4×12+B71+C5×72）：B1+C4×12+新B71+C5×12；0训练、0新TEST。

## 正在做什么

C5固定DEV72已完成并主审全raw PASS：64/72胜、8负0平，所有胜场改善超过10微米。总体Q11.558928mm vs B17.058081mm；HF28 Q10.179304mm vs B10.719024mm，20/28胜；W15 Q6.334075mm vs B7.647292mm，6/6胜。每个任务和全部输场见 `c5_dev72_parent_review/C5_DEV72_PARENT_FINDINGS_ZH.md`。C5相对C3为53胜/19负，退化也保留。论文证据包未达标，TEST未打开。

新增60场单批session76276自然OS0，UTC08:01:29至08:26:46，MATLAB已退出；不要重启批次。全审v4只兼容账本8处UTC小数秒尾零格式，其余字段严格相等，原d7 checker及全部输入/输出不改。主审实际核60新raw118080更新，加12旧场23616，共141696事件；独立物理检查216raw，电机/广义输入/倾角命令限幅全为0，C5 head/surface clip全0。只描述这些轨迹，不作为稳定性证明。当前续作自然完成156航次，训练0/TEST0。

执行者 `c4_coordinate_execution` 按 `C5_MATCHED_ABLATION_CONDITIONAL_TASKBOOK_ZH.md` 与 `C5_ABLATION_IMPLEMENTATION_RELEASE_ZH.md` 仅实现两个严格消融与无Plant：实际冻结W0、仅移除旧预测梯度。优先core/wrapper逐字复用，仅helper干预实际更新；不关原update/delayed flag，不增加不必要proposal日志。新目录 `experiments/position_c5_matched_ablations_20261023`。先交源给根审再实际无Plant；尚无新Plant放行，不主动开24/144场。

执行者 `b_probe_execution_fresh` 按 `PHYSICAL_RESIDUAL_TRACKING_LEMMA_TASKBOOK_ZH.md` 推导原物理forcing与M坐标的精确关系，产物在physical_residual_tracking_lemma，尚不可当已证明结论引用。既有条件代数经非作者审查通过，但原均匀unit-feature球标量证书对所有U都不能闭合当前W0（主审精确反证），见theory_scope_decision。完整理论门未批准，不继续搜索U凑该旧证书。

## 复算与下一关

```powershell
python 'reports/paper_continuation_20261023/c5_axis_coordinate_parent_review/score_c5_screen12_parent.py'
python 'reports/paper_continuation_20261023/finite_horizon_certificate/parent_review/check_delay_storage_parent.py'
python 'reports/paper_continuation_20261023/finite_horizon_certificate/parent_review/check_perturbation_parent.py'
```

上述命令均实际退出0，已有输出时拒绝覆盖。审计重做应保留原目录并版本化输出，不重跑已完成Plant。当前完整DEV72性能已通过。下一步完成严格消融、贡献/理论审核与最终冻结，才可能解封一次TEST48。

代码库当前 `origin=https://github.com/tengzumin/DL1018.git`，分支 `codex/dl1018-causal-diagnosis-upload`。本续作尚未提交；最终只选择经审核代码、任务书、报告、小表和图，不上传MAT/checkpoint/cache/夹具/MATLAB偏好证书或私钥，不批量暂存工作区。

最终完整DEV72审计命令（已真实退出0；只读raw不Plant，已有输出拒绝覆盖）：

```powershell
python reports/paper_continuation_20261023/c5_dev72_parent_review/audit_c5_dev72_raw_parent_v4.py --batch-version v3 --output reports/paper_continuation_20261023/c5_dev72_parent_review/C5_DEV72_RAW_PARENT_REVIEW_v3.json
```

根独立分组复算、成对场景区间、全输场/物理检查与图表目检已完成。消融只放行实现/无Plant阶段，TEST仍封存。
