# C5 DEV72 五方法逐场二次汇总

本文件由指定的五份已审核汇总文件再计算；没有重读 MAT/raw，没有重新评分，也没有重新审核历史 corrected14 raw。corrected DSSM14/KAN14 来自 2026-10-21 历史 PAIR14 汇总。对不同方法之间的同批次身份不作断言。

## 身份与核对

- 五种方法各有 72 个唯一场景，场景集合完全相同。输入 B 的未舍入 Q 与 traceable B：57/72 个场景十进制值相等；最大绝对差为 `0.000000000000000005 m`。历史 B scorer 来源仍保留在逐场表中；不同方法的同批次身份未作断言。
- C5 审核状态 `PASS_C5_DEV72_RAW_ALL_EVENTS_PARENT_AUDIT`；60 个新场景、12 个已审核复用场景。此次只复用报告/CSV中已有分数和身份字段。
- tie 容差为 `0.000000000001 m`；敏感性计数分别严格要求改善超过 1 μm、10 μm。各组对场景等权，不做 bootstrap。

## ALL72 结果

| 方法 | method_id | 平均 Q (mm) | 相对 traceable B 胜/平/负 | >1 μm / >10 μm 胜 |
|---|---|---:|---:|---:|
| C5 M110 | `C5_M110` | 11.558928 | 64/0/8 | 64 / 64 |
| B traceable | `B_TRACEABLE` | 17.058081 | 0/72/0 | 0 / 0 |
| C3 | `C3` | 11.759245 | 61/0/11 | 60 / 60 |
| corrected DSSM14 | `CORRECTED_TRAIN_DSSM14_G12_R32` | 12.387218 | 46/0/26 | 46 / 46 |
| corrected KAN14 | `CORRECTED_TRAIN_KAN14_G12_R32` | 15.041579 | 28/0/44 | 28 / 28 |

## C5 对各方法的逐场比较

| 对照方法 | C5 胜/平/负 | C5 >1 μm / >10 μm 胜 | C5−对照平均差 (mm) |
|---|---:|---:|---:|
| B traceable | 64/0/8 | 64 / 64 | -5.499152 |
| C3 | 53/0/19 | 53 / 49 | -0.200317 |
| corrected DSSM14 | 60/0/12 | 60 / 60 | -0.828290 |
| corrected KAN14 | 71/0/1 | 71 / 71 | -3.482650 |

## 分组和文件

`GROUP_METHOD_VS_B_SUMMARY.csv` 给出 ALL、HF(W09–W14)、W15、各任务及各风组的等权均值和相对 B 胜负；`GROUP_PAIRWISE_SUMMARY.csv` 同样汇总所有方法两两比较，含 C5 对每个方法。`SCENE_METHOD_METRICS.csv` 保留逐场 Q 和方法身份；历史 DSSM14/KAN14 行保留完整 method_id、model_id、candidate scorer/raw-scan/rescore SHA、逐场 raw SHA，以及原始 B scorer/source 身份。`ALL_LOSSES.csv` 只收录每个无序方法对中方向列 `method_a` 判为 LOSS 的记录；反向方向的输者可在完整 `PAIRWISE_SCENE_COMPARISONS.csv` 中查看。`B_Q_MATCH_AUDIT.csv` 列出两套历史 B 与 traceable B 的逐场精确十进制差。README 的 mm 表格数字显示到 6 位小数；CSV/JSON 保留完整精度。

## 来源 SHA256

脚本：`e633ca920b95bb332c8c693ff03e6a6f1a75a520e31aa44e51149a69a3af84c0`
- `corrected14_scene_csv`: `b2264145e9d18896f5764ffe38302576dd08c80e7cce1c277323246092169137`
- `corrected14_validation_json`: `e3759ba831ce8dd71f41846c49f9f7068b1e93b065afcf43c656d358a02c5bac`
- `corrected14_report_md`: `4af9e7c5a925c6bc0730184bec3dc74879a4fde2a163938b4e112e6de8a16b75`
- `c5_metrics_csv`: `3986e5ed42986c317b64fecfa508d5791709812f5c8443bf04cbce52e04a3a4c`
- `c5_raw_parent_review_json`: `bb34889559d95a1c995d4d420e3b3d7a702908b58b47cce969dc508a1c697fab`

- `SCENE_METHOD_METRICS.csv`: `9c90539bcdc120b9dbb9bb9810ef06894ded47848349fc02090be0380c5a19a1`
- `GROUP_METHOD_VS_B_SUMMARY.csv`: `691050a7e8a4a6a8ff95d42bee7abdc03f719bffd60d4071997bf84a5ad27c52`
- `PAIRWISE_SCENE_COMPARISONS.csv`: `ec6246545a0fe06405447b56c40e5307f9976823f2fb26fe1481a46445f4f5d2`
- `GROUP_PAIRWISE_SUMMARY.csv`: `5fe27aa8414dce58050955eefc141beaf94844cc8e536d5b17a0d00b1e438d79`
- `ALL_LOSSES.csv`: `7bdf062b816642477c803ba3589709af59f7acdec7674cb7c4896182b803e30a`
- `METHOD_PROVENANCE.csv`: `4ab5362da89f63fe2eea6a5f77ac3e687e9b47afaa5f60854cd02ea57d0fe75f`
- `B_Q_MATCH_AUDIT.csv`: `da9ac840a77c60d7c7c4973899c75c04d15558861a93958739e16d6185928402`
- `SUMMARY.json`: `b39b2f28c05dbbeba3ad9136c2bfb4964c3c771151932edaaa842bd3cf66c582`

## 可重现命令

在仓库根目录首次生成：

```powershell
python reports/paper_continuation_20261023/c5_all_method_dev_comparison/v2/aggregate_dev72_v2.py
```

在输出文件已存在时做无写入的逐字节复算核对：

```powershell
python reports/paper_continuation_20261023/c5_all_method_dev_comparison/v2/aggregate_dev72_v2.py --verify-existing
```

汇总范围仅限 DEV/VAL 开发场景；不含 TEST，不含新仿真、训练或 raw 重审。
