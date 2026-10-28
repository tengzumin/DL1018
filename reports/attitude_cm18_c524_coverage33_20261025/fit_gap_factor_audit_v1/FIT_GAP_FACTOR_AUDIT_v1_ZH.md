# C5_COVERAGE33 拟合差结构审计

## 统计口径

主比值由冻结报告的逐场 `candidate_normalized_vector_nrmse` 得出：每场取 ordinal 0,5,…,1995 的 400 行，先逐场计算，再对 TRAIN+TRAIN_EXTRA（33 场）与 HOLDOUT（15 场）分别场景等权平均。复算为 `0.015295 → 0.267078`，比值 `17.461698×`；报告的 scene-block bootstrap 95% CI 为 `11.916585–27.683459×`。这是一项全支持逐点拟合差，不是 active-phase-only 比值。

DEV 次级分层使用每场全部 1999 个事件（15 场、29,985 行），先逐场计算后场景等权；task/wind 对照从主表按场景分组。parent centered-delta 表的 `centered_delta = scene_value − split_macro_mean`，与主表所列中心化列一致。所有下列关联仅作描述，不解释为因果。

## 可解释与不可识别的结构

| 维度 | 表内可复核结果 | 解释边界 |
|---|---|---|
| Morphology phase | DEV `active_phase` 为 0.305238（4558 事件；95% CI 0.242444–0.370631），高于全事件 0.266899；phase code 2/3/4 分别为 0.338191/0.419622/0.225103。 | DEV 误差集中于部分非零误差相位；TRAIN 没有同口径相位分层，不能判断该结构解释了多少 17.46×。 |
| 零误差相位核验 | phase code 1 与 5 分别覆盖 7985、7786 事件，NRMSE 数值上为零；phase code 0 是 0 场、0 事件。 | 全支持的比值把各相位纳入同一逐场指标，因而不是 active-only。若旧报告称“phase-0/5 零误差”，其中 phase-0 不受数据支持；实际为 code 1/5。由于无 TRAIN 相位指标，也不能拆出零误差相位对跨分割比值的定量贡献。 |
| Task | TRAIN33→HOLDOUT15：T1 0.017151→0.251767（12→4 场）；T2 0.012685→0.316685（10→6）；T3 0.015644→0.219799（11→5）。 | 三类任务都出现较大差，T2 描述值最高；场数小，且 task 与风况/场景交织，无法归因给 task。 |
| Wind | 主表 HOLDOUT 场均 NRMSE：W11 0.464129（1 场）、W13 0.463341（1）、W14 0.476539（1）；W15 0.140629（2）、W08 0.253266（3）。 | 可见风况间差异，但多数风码仅 1–3 场；不足以和 task 或场景效应分开。 |
| First event | DEV `first_morph_event` 为 0.110367（15 场各 1 事件；95% CI 0.086199–0.133415），低于 DEV 全事件与 active-phase。 | 首个形变事件不是高误差的充分概括；TRAIN 没有对应分层，不能用于解释跨分割差。 |
| 场景离群 | HOLDOUT NRMSE 最高五场之和占 15 场 NRMSE 总和 52.1%；最高值 0.476539。五场分布于 T1/T2/T3 与 W09/W08/W11/W13/W14。 | 差异有场景集中，但不由单一场景独占；没有联合分层/调整可估计其余 task 与 wind 影响。 |

**结论：** HOLDOUT 的误差表现出相位选择性，并伴随 task、wind 和场景层面的描述差异；但现有表不能识别 TRAIN33→HOLDOUT15 的 17.46× 主要由哪一项造成。全支持比值确实混合相位表现，不能称作 active-phase 比值；`phase_code_0` 也不能列为零误差相位。此审计没有确定根因。

**一个可证伪的最小验证方向：** 对同一冻结模型和同一 400-ordinal 主比较口径，补算 TRAIN33/HOLDOUT15 每场按相同 morphology-phase 标签分层的 NRMSE，并以场景为重抽样单位。若 active-phase 是主要结构，跨分割差应在 active/非零误差相位集中；若 phase 分层比值与全支持相近，或误差未集中于 active 相位，则该解释不成立。

## 来源与哈希

仅使用下列已生成报告与表格；未读取缓存、raw MAT 或 TEST，未运行模型/Plant、未训练。

| 来源 | SHA-256 |
|---|---|
| `fit_generalization_v1/FIT_GENERALIZATION_REPORT_v1_ZH.md` | `D2305C87118E638345B9DA13784D3C58D00D01A9CBF3394D5866BEFDBAFBA34C` |
| `fit_generalization_v1/primary_scene_metrics.csv` | `925CA8314647DE201B101FAC265309F269CE420918D583818223C8700729125D` |
| `fit_generalization_v1/secondary_scene_metrics.csv` | `83EC994C900C1D7CF3467736FCD8D3090DE342799776190873D05127DD78752E` |
| `fit_generalization_v1/secondary_strata_summary.csv` | `54ACAAA6FE8EB30BFCB2C7E61BF5209A588648EF82025EF7768262172EAC0FB2` |
| `fit_generalization_parent_review_v1/primary_scene_metrics_centered_deltas.csv` | `1E9A12B6A0FAD3266EB99279E742EA4B196DB0982DA8201D85DC8BB58C605789` |
| `fit_generalization_parent_review_v1/audit_record.md` | `1EE95E360F51BC1A1F4F58B07A8FAD77BB33B2CB0D43410FA8C0CC21C984B4E8` |