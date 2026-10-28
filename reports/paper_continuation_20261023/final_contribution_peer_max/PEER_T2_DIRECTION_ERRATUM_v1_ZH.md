# 独立同行审核 T2 配对方向勘误 v1

本勘误更正 `PEER_REVIEW_v1_ZH.md` 与其 JSON 中 T2 的逐场胜负方向。原审核文件保持不变；勘误仅修正 T2 方向字段，不改变任何均值、置信区间、总体胜负数或贡献范围。

原审核表的表头定义最后一列为“NO_PRED 相对 C5 的胜/负/平”，但 T2 行误写成 `13/11/0`。按锁定配对CSV中的 `C5_vs_ablation` 和 `C5_minus_ablation_Q_m` 逐场核对，T2 有 24 场：C5 胜 13 场，NO_PRED 胜 11 场，平局 0 场。因此，在原表头所指方向下，该行应为 **NO_PRED 11/13/0**。审核正文中“NO_PRED 13胜、C5 11胜”的文字原本正确。

原 JSON 中 `groups.T2.no_prediction_wlt_vs_c5` 与 `no_prediction_effect.t2_no_prediction_wlt_vs_c5` 同样将两个方向写反，均应改为 `[11,13,0]`。互补方向 `t2_c5_wlt_vs_no_prediction` 为 `[13,11,0]`。

均值差定义为 `Q_C5 − Q_NO_PRED`：T2 为 −0.001067120 mm（即 C5 均值低 1.067120 µm）。已保存的描述性 paired 95% 区间为 [−0.202648848, +0.196671676] mm，跨越 0。该均值、区间、总体 C5 相对 NO_PRED 的 54 胜/18 负/0 平，以及贡献审核的限定裁决均不变。短稿已按正确方向记载 T2 为 C5 13 胜、NO_PRED 11 胜。

## 可复核来源

- 原 peer review Markdown：`PEER_REVIEW_v1_ZH.md`，SHA-256 `94f7c839c0a75e07963461a5eeccd5a73d8b05147b5476d95b9481659a4640d3`
- 原 peer review JSON：`PEER_REVIEW_v1_ZH.json`，SHA-256 `90a38f7758c9eb6f258f7e492dc7714cf082837b6420c90347a3337343dd38c3`
- 逐场配对源：`../c5_matched_ablation_dev72_parent_review/MATCHED_ABLATION_DEV72_ALL_PAIRS_v1.csv`，SHA-256 `9ad962499032826a31ee0f4c3b424ec45793272f411314ab6c35d3356e34e49b`
- 独立汇总源：`../c5_matched_ablation_dev72_parent_review/MATCHED_ABLATION_DEV72_INDEPENDENT_SUMMARY_v1.json`，SHA-256 `71b5b437b4d2515ef9abf1fa8ab19379a9e6e5520813ca5b499caed749fab9bd`

逐场复核按 `variant=C5_NO_DELAYED_PREDICTION` 筛选 T2 的 24 行；`C5_vs_ablation=WIN` 计为 C5 胜，`LOSS` 计为 NO_PRED 胜，`1e-12 m` 为平局容差。计数为 C5 13 胜、11 负、0 平；对应的 NO_PRED 相对 C5 为 11 胜、13 负、0 平。本勘误不重算也不替代保存的区间。
