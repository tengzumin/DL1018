# C5 DEV72 五方法逐场二次汇总

本文件由指定的五份已审核汇总文件再计算；没有重读 MAT/raw，没有重新评分，也没有重新审核历史 corrected14 raw。corrected DSSM14/KAN14 是 2026-10-21 历史 PAIR14 方法，不是与新可追溯 B 同一批次或同一次运行。

## 身份与核对

- 五种方法各有 72 个唯一场景，场景集合完全相同。输入 B 的未舍入 Q 与 traceable B：57/72 个场景十进制值相等；最大绝对差为 `0.000000000000000005 m`。历史 B scorer 来源仍保留在逐场表中，不能因此把历史模型和新 B 称为同次运行。
- C5 审核状态 `PASS_C5_DEV72_RAW_ALL_EVENTS_PARENT_AUDIT`；60 个新场景、12 个已审核复用场景。此次只复用报告/CSV中已有分数和身份字段。
- tie 容差为 `0.000000000001 m`；敏感性计数分别严格要求改善超过 1 μm、10 μm。各组对场景等权，不做 bootstrap。

## ALL72 结果

| 方法 | method_id | 平均 Q (mm) | 相对 traceable B 胜/平/负 | >1 μm / >10 μm 胜 |
|---|---|---:|---:|---:|
| C5 M110 | `C5_M110` | 11.558928371025634605555555555555555555555555555556 | 64/0/8 | 64 / 64 |
| B traceable | `B_TRACEABLE` | 17.058080675350785701388888888888888888888888888889 | 0/72/0 | 0 / 0 |
| C3 | `C3` | 11.759244913238592368055555555555555555555555555556 | 61/0/11 | 60 / 60 |
| corrected DSSM14 | `CORRECTED_TRAIN_DSSM14_G12_R32` | 12.387217899198615972222222222222222222222222222222 | 46/0/26 | 46 / 46 |
| corrected KAN14 | `CORRECTED_TRAIN_KAN14_G12_R32` | 15.041578553598643611111111111111111111111111111111 | 28/0/44 | 28 / 28 |

## C5 对各方法的逐场比较

| 对照方法 | C5 胜/平/负 | C5 >1 μm / >10 μm 胜 | C5−对照平均差 (mm) |
|---|---:|---:|---:|
| B traceable | 64/0/8 | 64 / 64 | -5.4991523043251510958333333333333333333333333333333 |
| C3 | 53/0/19 | 53 / 49 | -0.2003165422129577625000 |
| corrected DSSM14 | 60/0/12 | 60 / 60 | -0.82828952817298136666666666666666666666666666666667 |
| corrected KAN14 | 71/0/1 | 71 / 71 | -3.4826501825730090055555555555555555555555555555556 |

## 分组和文件

`GROUP_METHOD_VS_B_SUMMARY.csv` 给出 ALL、HF(W09–W14)、W15、各任务及各风组的等权均值和相对 B 胜负；`GROUP_PAIRWISE_SUMMARY.csv` 同样汇总所有方法两两比较，含 C5 对每个方法。`SCENE_METHOD_METRICS.csv` 保留逐场 Q 和方法身份；历史 DSSM14/KAN14 行保留完整 method_id、model_id、candidate scorer/raw-scan/rescore SHA、逐场 raw SHA，以及原始 B scorer/source 身份。`ALL_LOSSES.csv` 包含所有逐场方法对中的输场记录；`B_Q_MATCH_AUDIT.csv` 列出两套历史 B 与 traceable B 的逐场精确十进制差。

## 来源 SHA256

脚本：`3689ea2b83b39682e3dc4c1011ecaeeddd7d61ec1c5cb1e60f39b22327169f8e`
- `corrected14_scene_csv`: `b2264145e9d18896f5764ffe38302576dd08c80e7cce1c277323246092169137`
- `corrected14_validation_json`: `e3759ba831ce8dd71f41846c49f9f7068b1e93b065afcf43c656d358a02c5bac`
- `corrected14_report_md`: `4af9e7c5a925c6bc0730184bec3dc74879a4fde2a163938b4e112e6de8a16b75`
- `c5_metrics_csv`: `3986e5ed42986c317b64fecfa508d5791709812f5c8443bf04cbce52e04a3a4c`
- `c5_raw_parent_review_json`: `bb34889559d95a1c995d4d420e3b3d7a702908b58b47cce969dc508a1c697fab`

- `SCENE_METHOD_METRICS.csv`: `a96f1754ba11acf760f6c0490d9452d8e5f03bac6ef49f9e1e78e82318d71416`
- `GROUP_METHOD_VS_B_SUMMARY.csv`: `691050a7e8a4a6a8ff95d42bee7abdc03f719bffd60d4071997bf84a5ad27c52`
- `PAIRWISE_SCENE_COMPARISONS.csv`: `ec6246545a0fe06405447b56c40e5307f9976823f2fb26fe1481a46445f4f5d2`
- `GROUP_PAIRWISE_SUMMARY.csv`: `5fe27aa8414dce58050955eefc141beaf94844cc8e536d5b17a0d00b1e438d79`
- `ALL_LOSSES.csv`: `7bdf062b816642477c803ba3589709af59f7acdec7674cb7c4896182b803e30a`
- `METHOD_PROVENANCE.csv`: `3325968ca10d63bce713e419a631b62071ad1e21b8ffae5a03e4fff7dda5a77f`
- `B_Q_MATCH_AUDIT.csv`: `da9ac840a77c60d7c7c4973899c75c04d15558861a93958739e16d6185928402`
- `SUMMARY.json`: `8316997c18451f79a2a14fb369dab10a87c3001b3f90b72c96be7b7ea43d1eb2`

## 可重现命令

在仓库根目录首次生成：

```powershell
python reports/paper_continuation_20261023/c5_all_method_dev_comparison/aggregate_dev72.py
```

在输出文件已存在时做无写入的逐字节复算核对：

```powershell
python reports/paper_continuation_20261023/c5_all_method_dev_comparison/aggregate_dev72.py --verify-existing
```

汇总范围仅限 DEV/VAL 开发场景；不含 TEST，不含新仿真、训练或 raw 重审。
