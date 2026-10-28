# 独立同行审核 T2 配对方向勘误 v2

本 v2 更正勘误 v1 对原 peer review 正文的描述错误。勘误 v1 曾称原审核正文中“NO_PRED 13 胜、C5 11 胜”的文字正确；该判断也反了。原 peer review Markdown 的 T2 胜负文字同样错误。原文件保持冻结，不覆盖 v1 或改写原审核文件。

正确方向为：T2 共 24 场，**C5 胜 13 场，NO_PRED 胜 11 场，平局 0 场**。因此，原审核表头“NO_PRED 相对 C5 的胜/负/平”下，T2 应写 **11/13/0**；原 Markdown 正文中有关 T2 的句子应改为“C5 13 胜，NO_PRED 11 胜”。原 JSON 的 `groups.T2.no_prediction_wlt_vs_c5` 和 `no_prediction_effect.t2_no_prediction_wlt_vs_c5` 均应为 `[11,13,0]`，互补方向 `t2_c5_wlt_vs_no_prediction` 为 `[13,11,0]`。勘误 v1 的 JSON 已使用这些正确方向值。

配对均值差 `Q_C5 − Q_NO_PRED` 为 −0.001067120 mm，已保存描述性 paired 95% 区间为 [−0.202648848, +0.196671676] mm，跨越 0。均值、区间、全72场总体 C5 相对 NO_PRED 的 54 胜/18 负/0 平及贡献范围均不变。

## 来源与版本关系

- 原 peer review Markdown：`PEER_REVIEW_v1_ZH.md`，SHA-256 `94f7c839c0a75e07963461a5eeccd5a73d8b05147b5476d95b9481659a4640d3`
- 原 peer review JSON：`PEER_REVIEW_v1_ZH.json`，SHA-256 `90a38f7758c9eb6f258f7e492dc7714cf082837b6420c90347a3337343dd38c3`
- 配对CSV：`../c5_matched_ablation_dev72_parent_review/MATCHED_ABLATION_DEV72_ALL_PAIRS_v1.csv`，SHA-256 `9ad962499032826a31ee0f4c3b424ec45793272f411314ab6c35d3356e34e49b`
- 被本 v2 更正的勘误 v1 Markdown SHA-256：`48f946797af5d4d6fe4e80e7e6332a590c3ba3c2536e0a895ff59687ce694be0`
- 勘误 v1 JSON SHA-256：`ea4aa1e376798e4cf4b341129e7e1e784d8432ca5f96f27f0e22be81fbee48e3`

逐场核对沿用配对CSV的 `variant=C5_NO_DELAYED_PREDICTION`、`task=T2` 24行和 `1e-12 m` 平局容差；按 `C5_vs_ablation` 计得 C5 13 胜、11 负、0 平。v1 的方向字段值本身正确；本 v2 仅纠正 v1 对原 Markdown 正文方向的陈述。配套论文初稿已按 C5 13 胜、NO_PRED 11 胜记载。
