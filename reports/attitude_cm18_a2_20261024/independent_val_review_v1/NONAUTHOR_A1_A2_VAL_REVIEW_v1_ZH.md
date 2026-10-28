# A1 与 A2：全部 48 场 VAL 独立复核

本复核只读取 A1/A2 的 `validation_recomputed_v1.json` 和 ROOT gate JSON。两份 VAL 报告均为 PASS，各含 48 场 × 1,999 events（95,952），scene ID 集合一致，checkpoint selected step 均为 30,000。A1 reference gate 的来源 SHA、A2 gate 的 candidate SHA 与实际文件一致；逐场重算汇总与 gate 在 1e-12 内相符。未访问 TEST、checkpoint 或其它训练数据，也未运行模型、Plant、GPU 或训练。

指标定义：normalized macro 为 48 个逐场 normalized score 等权平均；physical vector macro 为每场 `sqrt(RMSE_x²+RMSE_y²+RMSE_z²)` 再等权平均；yaw pooled 为每场 yaw RMSE 的均方根。分组 CSV 另含 x/y/z 逐场 RMSE 的宏平均和 pooled RMSE。

| VAL 指标 | A1 | A2 retry1 | 相对变化 | 门槛 |
|---|---:|---:|---:|---|
| normalized macro | 0.230377064 | 0.242880511 | +5.43% | FAIL（超过 1.05×） |
| physical vector macro (rad/s²) | 0.330094285 | 0.324793898 | -1.61% | PASS |
| yaw pooled RMSE (rad/s²) | 0.175469917 | 0.192411994 | +9.66% | FAIL（超过 1.05×） |

负 delta 表示 A2 改善。48 场计数：normalized 24 改善、21 变差、3 持平；yaw 23 改善、22 变差、3 持平。逐场 CSV 的排名为序位排名；完全相同的 delta 以 scene ID 稳定排序，因此三场零变化会占相邻排名，不能解释为彼此存在差异。

按任务分组的逐场宏平均变化如下；完整 T/C/W 分组和逐轴 macro/pooled 数值见分组 CSV。

| 任务 | 场数 | normalized delta | physical vector delta (rad/s²) | x RMSE delta | y RMSE delta | z RMSE delta | yaw pooled delta (rad/s²) |
|---|---:|---:|---:|---:|---:|---:|---:|
| T1 | 16 | +0.015592 | -0.004329 | -0.011323 | -0.004872 | +0.008815 | +0.011930 |
| T2 | 16 | -0.003351 | -0.000231 | -0.011377 | +0.011558 | -0.001847 | +0.006400 |
| T3 | 16 | +0.025269 | -0.011342 | -0.027058 | -0.003493 | +0.014397 | +0.032661 |

以下是全量排序的两端前五。

## Normalized 最大回归

1. `DL1018_VAL_T3_C01_W14` — 0.79514463 → 1.0467911 (+0.25164645)
2. `DL1018_VAL_T2_C14_W08` — 0.80812221 → 0.95024594 (+0.14212373)
3. `DL1018_VAL_T3_C05_W02` — 0.25513893 → 0.37609518 (+0.12095625)
4. `DL1018_VAL_T1_C01_W08` — 0.45994821 → 0.57015468 (+0.11020647)
5. `DL1018_VAL_T3_C11_W08` — 0.26338888 → 0.36383838 (+0.1004495)

## Normalized 最大改善

1. `DL1018_VAL_T3_C07_W04` — 0.37983077 → 0.27863964 (-0.10119113)
2. `DL1018_VAL_T2_C07_W01` — 0.33260673 → 0.25876707 (-0.073839663)
3. `DL1018_VAL_T2_C10_W04` — 0.46206642 → 0.39007939 (-0.071987025)
4. `DL1018_VAL_T2_C11_W05` — 0.25448849 → 0.20191197 (-0.052576519)
5. `DL1018_VAL_T3_C08_W05` — 0.26129667 → 0.21884274 (-0.042453932)

## Yaw 最大回归

1. `DL1018_VAL_T3_C01_W14` — 0.44173761 → 0.5823355 (+0.14059789)
2. `DL1018_VAL_T2_C14_W08` — 0.44562944 → 0.51873996 (+0.073110518)
3. `DL1018_VAL_T3_C05_W02` — 0.12848117 → 0.19841106 (+0.069929891)
4. `DL1018_VAL_T1_C01_W08` — 0.25005613 → 0.31361647 (+0.063560341)
5. `DL1018_VAL_T3_C11_W08` — 0.14369628 → 0.19882179 (+0.055125508)

## Yaw 最大改善

1. `DL1018_VAL_T3_C07_W04` — 0.20786061 → 0.15272299 (-0.055137621)
2. `DL1018_VAL_T2_C07_W01` — 0.18324766 → 0.14194888 (-0.041298785)
3. `DL1018_VAL_T2_C10_W04` — 0.25409534 → 0.21463945 (-0.039455893)
4. `DL1018_VAL_T2_C11_W05` — 0.13899187 → 0.110797 (-0.028194864)
5. `DL1018_VAL_T3_C08_W05` — 0.14178059 → 0.11718077 (-0.024599824)

全部 48 场逐场的 normalized/yaw/x/y/z/vector 变化及回归、改善排名见 `NONAUTHOR_A1_A2_VAL_PER_SCENE_v1.csv`。按 T1/T2/T3、C00–C15 condition/morphology key、W00–W15 wind key 的完整分组统计见 `NONAUTHOR_A1_A2_VAL_GROUPS_v1.csv`。按 scene ID 的显式 C key 分组；不从两个汇总 JSON 反推 C 之外的连续物理形态量。

ROOT 的 `ROOT_A2_VAL_GATE_RESULT_v1.json` 为 FAIL；该候选未通过预定 VAL 门，不能据此放行 Plant。离线 VAL 行为误差变化不等于闭环收益。

机制边界：固定真实形态和其他物理条件时，理想 yaw 动作对当前 `alphaBS_xy` 的偏导可以为零。但 X18 不含真实形态，因此 `alphaBS_xy` 可能在行为数据中充当未观测形态/动力学上下文的统计代理。物理条件不变性不能直接推出部分观测条件下最优回归函数也必须对 `alphaBS_xy` 不变。现有两份 VAL 汇总没有隔离该代理信息机制，不能把它认定为已证实根因。

## 文件身份

- A1 validation JSON SHA256：`6225eb5509ce72c52c5624599b8eded142ebf65a6f1a812e41eeead5750c2c60`
- A2 validation JSON SHA256：`bf14738b129418d622369a2bc7a2ac2e77fe0eac3ed4ed9157b5039d12b7251c`
- A1 reference gate SHA256：`839890f6ee5fd91b44e0e398c925121b6a2ee996e3e3330cb9f2c0149090fd0f`
- A2 gate SHA256：`294523ff57d820183d2a710acaf26a565f36a970dcde34dbf526733121b93655`
