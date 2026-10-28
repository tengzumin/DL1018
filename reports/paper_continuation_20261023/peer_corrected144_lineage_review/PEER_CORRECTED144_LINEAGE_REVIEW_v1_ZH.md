# Corrected14 144 场原始数据谱系独立复核

**结论：确认完整 144/144 原始 raw 身份与覆盖；46/72 DSSM、28/72 KAN 计数复算成立。** 本复核仅使用 DEV/VAL 证据；未读 TEST raw/成绩，也未运行 MATLAB、Plant、训练或实验。

最终表 `PAIR14_SCENE_RESULTS_VS_B.csv` 有 144 行，DSSM/KAN 各 72。原 `corrected_pair_eval_v1` 的 `RAW_INDEX.csv` 覆盖 manifest index 1–123，123 条 `RUN_COMPLETE_STABLE`；独立 `corrected_pair_eval_tail21_v1` 的 `RAW_INDEX.csv` 覆盖 index 124–144，21 条 `RUN_COMPLETE_STABLE`。组合审计明确记录 “original indices 1..123 + isolated tail indices 124..144”，状态 `PASS_COMPOSED_144_ALL_STABLE_TWO_SESSIONS`。因此原 session `STOPPED_TIMEOUT` 不能作为其余 21 条未运行的证据。

我按 `(source_scene_id, method_id)` 合并两份原始索引、组合 raw metrics / runtime replay 与最终表，144 个 key 无遗漏、无重复。对 144 条候选 raw 路径逐个检查磁盘文件并重新计算 SHA-256，共核验 6.52 GiB：144/144 文件存在；索引 SHA、结果表 `candidate_raw_sha256`、磁盘 SHA、组合报告 `raw_sha256_after` 与 replay `independent_raw_sha256` 全部一致。144 行的 run status 都是 complete/finite/20,000 transitions；runtime replay 144/144 有效（每行 1,968 个事件），且 `external_arrays_sha256_match=True`。

按 `1e-12 m` 容差逐场重算，corrected DSSM14 为 **46/0/26**，均值 **12.387217899 mm**（B：17.058080675 mm）；corrected KAN14 为 **28/0/44**，均值 **15.041578554 mm**（B：17.058080675 mm）。最终表候选 Q 与组合 raw scan Q 的最大绝对差为 `4.86e-17 m`。

模型身份闭合：DSSM 的 72 条 raw index 记录 model id / export SHA 均与批准模型一致，72 条 replay 共用同一 W0 SHA、`W0_error=0` 且模型数组身份匹配；KAN 同样 72/72。

| 方法 | raw 存在/哈希匹配 | 1e-12 m 胜/平/负 | 候选均值 Q (mm) | 唯一 W0 SHA |
|---|---:|---:|---:|---|
| corrected DSSM14 | 72/72 | 46/0/26 | 12.387218 | `87fa03a567ced9f144eca26eceadebba59269cbebf800a0eb72c1a755fe7bbd0` |
| corrected KAN14 | 72/72 | 28/0/44 | 15.041579 | `b729a81fe67456a70bb25ebd3240682019bff21641ba597dcd92772080e6833d` |

来源 SHA、模型/W0 摘要和 144 行逐场路径与哈希见 [JSON](PEER_CORRECTED144_LINEAGE_v1.json) 与 [逐场 CSV](PEER_CORRECTED144_RAW_LINEAGE_v1.csv)。DSSM 独立重评分记录也绑定两份 raw index（主索引 `364367e46ae8e3eb3335efd34a834b984a2a87fc1cef0dd5bf4991bbf342d8b4`，tail21 `3527883329ec23f51928d3967071d307a42683adc831cee8958822c7b732d116`），72/72 条 Q 均复核。

范围限制：offline comparison 的单独 `formal_v2_gate` 为 `BLOCKED_SCHEMA_AND_STALE_MANIFEST_PIN`。此门限的 schema/stale-manifest 问题仍需如实披露；本次只确认 raw 身份、覆盖与胜负计数，不声称其已被本复核消除。
