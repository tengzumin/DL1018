# C5 主动变形应用分层审计执行补遗

- 状态：单次主脚本运行成功，退出码 0；未重跑。
- 执行时间（UTC）：2026-10-25T03:59:39Z
- 运行环境：PowerShell 7.6.8；Python 3.12.7。
- 脚本 SHA256：`10c2401f7ee4b0f29be7ea095068bbf3bbd0e41d43c200b04b6adac35f0f7417`。
- 输入处理：9 项冻结输入运行前哈希全部匹配，运行后哈希仍全部匹配；MAT/TEST 输入由脚本以只读方式打开。
- 产物边界：5 个主输出均写入本目录；运行前目标及 `.tmp` 均不存在，无覆盖。
- 本目录预检未发现更早失败尝试或旧输出；该次执行是本目录登记的唯一尝试。

## 冻结 TEST 输入与顺序契约

- `TEST_INPUT_INDEX_v1.json` 含 48 个排序 scene IDs；按换行连接的 ID 集 SHA256：`90e59e5461650cf718a2eeb48b68a4f3c38e3e5b4046ca721116d143b731769e`。完整 ID 列表见 `AUDIT_ATTEMPT_LEDGER_20261025.md`。
- TEST producer SHA256：`0490da98749b114ed9e9553fc7cb44349e0c5c9d182551d8a05c844a009b9bf2`；共享场景 MAT SHA256：`da207d858e8918f27c19fef30d4ad57206e20f1971e743515043d1a88a995d5c`。producer 排序后以同一循环顺序生成和保存 packs。
- TEST long/wide 配对交叉核对：48 场；最大绝对差 `3.4694469519536142E-18` m。

## 分层结果摘要

- Parent-review batch：72 条（原始 split DEV 24 + VAL 48；新运行 60 条，复用 12 条，故不是 72 个独立 DEV 场景）。总计 64 胜、8 负、0 平。
- TEST48：48 场，总计 46 胜、2 负、0 平。
- 分组均值以 C5-B 的 Q 差（mm）列出；W/L/T 使用 ±1e-12 m 阈值。

| 数据集 | 活动臂组 | 场数 | 均值 ΔQ (mm) | 胜 | 负 | 平 |
|---|---:|---:|---:|---:|---:|---:|
| DEV72_PARENT_REVIEW_BATCH | 1 | 17 | -2.260 | 15 | 2 | 0 |
| DEV72_PARENT_REVIEW_BATCH | 2 | 28 | -6.486 | 26 | 2 | 0 |
| DEV72_PARENT_REVIEW_BATCH | 3 | 16 | -7.776 | 15 | 1 | 0 |
| DEV72_PARENT_REVIEW_BATCH | 4 | 5 | -1.088 | 4 | 1 | 0 |
| DEV72_PARENT_REVIEW_BATCH | NONE | 6 | -7.676 | 4 | 2 | 0 |
| TEST48 | 1 | 12 | -8.876 | 12 | 0 | 0 |
| TEST48 | 2 | 18 | -9.492 | 18 | 0 | 0 |
| TEST48 | 3 | 12 | -1.282 | 10 | 2 | 0 |
| TEST48 | 4 | 3 | -2.591 | 3 | 0 | 0 |
| TEST48 | NONE | 3 | -3.242 | 3 | 0 | 0 |

- TEST 实测活动臂实例：96；真实伸展幅度范围：0.03–0.10 m；活动段 `rhoDot_true` 峰值均为 0.05 m/s。所有场景的 `rho_hat` 恒为 0.15 m，`rhoDot_hat` 恒为 0 m/s。
- DEV 活动臂数取自 `scene_specs.csv` 四个 target；TEST 活动臂数取自冻结 packs 的 `rho_true` 变化，并逐场核对配置活动臂掩码一致。
- TEST 每任务 16 场；每任务活动臂组分布均为 NONE=1、1 臂=4、2 臂=6、3 臂=4、4 臂=1。
- 参考速度/加速度峰值范数（T1/T2/T3）：1.076739 m/s 与 0.936841 m/s²；1.473154 m/s 与 1.350131 m/s²；0.750000 m/s 与 0.461880 m/s²。

## 五个主输出 SHA256

| 文件 | SHA256 | 字节 |
|---|---|---:|
| `morph_active_count_performance.csv` | `492100488ea608c2e1f91fa59e6c07e1452c1488f193d131b3e23864fee71f5c` | 6907 |
| `morph_active_count_losses.csv` | `39c90e18d1a96509337b9841986cf1e3057ee5529ae9ce93e534704b8195fa4a` | 4432 |
| `test_scene_morphology_reference.csv` | `f0fb7d44c59217ba9d3dd29f45a0dc5ee16c8d8c14a7f0dfca33bcf486a13c50` | 11282 |
| `audit_summary_v1.json` | `7f68a7bb13465f2f4a8ef424b707d68c118fd42e0e95a607f4cd86967a318721` | 42521 |
| `FINDINGS_ZH.md` | `ac61816aa3e4d45dca7ea7407f04e9388547f5cebae331a459343315898d9cd3` | 1854 |

## 运行后输入校验

| 输入 | 运行后 SHA256 | 与冻结 pin 一致 |
|---|---|---|
| `scene_specs` | `d116b74dc6d9ce3c21a40fcd48b4153a0adc09e98a6c8d341c0f1b6ba680b4e3` | 是 |
| `dev_input_lock` | `82024c01276cc4bfbd9b7772cf5332dee3fdfcbed422969589b68f1c90ed2d75` | 是 |
| `dev_parent_review` | `bb34889559d95a1c995d4d420e3b3d7a702908b58b47cce969dc508a1c697fab` | 是 |
| `test_long_metrics` | `178f29fb3732a5eda5cb4f0d4a9ba17f72b2f470ad7418f7a829fe525be64db2` | 是 |
| `test_wide_crosscheck` | `8da2901ede8034388b6e512ef04fa53bd9dc7fdae0a1e41657047c8930641ce3` | 是 |
| `test_input_index` | `90940a818d293c66c34423a63088113557518c5ecdfd528a3f37867f391eef68` | 是 |
| `test48_producer` | `0490da98749b114ed9e9553fc7cb44349e0c5c9d182551d8a05c844a009b9bf2` | 是 |
| `test_shared_scenes` | `da207d858e8918f27c19fef30d4ad57206e20f1971e743515043d1a88a995d5c` | 是 |
| `pinned_hdf5_reader` | `d82e089c7d41f39c620daea63d95315632e6fb2f80addf4dc12e6a4603b8e57e` | 是 |

