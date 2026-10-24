# TEST48 v2 入口：CODE ONLY 交接

本版本只修复首次 DEV 在 `verify_code_contract` 的 JSON 索引错误，并隔离到新目录；没有启动 MATLAB 或任何模式，没有生成/读取 TEST 数组。v1 的失败 receipt、日志、源码和 release 均保留原位，v2 没有复制或引用 v1 的 DEV release。

根级只读诊断确认 MATLAB `jsondecode` 将原异构 `method_order` 解为 `cell(6x1)`，而 `methods` 是 `struct(6x1)`。v2 在六个 method 对象中补齐同一组字段 `id, alias, source, uses_learned_model, model_id, actual_weight_update, actual_prediction_gradient`；原有字段值、方法 ID/alias/source、顺序及控制参数不变，缺失项用 JSON `null`。入口在任何 `.id` 点索引之前断言 `isstruct(c.method_order)` 且元素数为 6。

五个输入文件已复制到 `experiments/c5_test48_v2/` 与 `reports/paper_continuation_20261023/test_entry_v2/`。v2 只将目录路径切换到两个新目录；阶段、协议文件名仍保留 `_v1`。manifest 文件字节与已审核版本相同，SHA `66f6d2e0c042dff9aa07e75f6d0443d38d694097495b30d551dfd94f2c90919c`；其 211 个已核源引用、模型和统计/勘误身份未改。

## 文件 SHA-256

| 文件 | SHA-256 |
|---|---|
| `experiments/c5_test48_v2/test48_entry_v1.m` | `845996a910b2abec470acc063324ed2cbe17641255d4ae60ca48581f6ab4d299` |
| `experiments/c5_test48_v2/RUN_TEST48_EXACT_v1.ps1` | `94a61a314351defc0624b5fa3c3cfdb86fc64b214cd8e41c6d75b0121584518c` |
| `experiments/c5_test48_v2/TEST48_RUN_CONTRACT_v1.json` | `4c7a3422fb8e454272f461f5b797e239c93610291e232f8919b677005a6927a1` |
| `reports/paper_continuation_20261023/test_entry_v2/build_test48_method_manifest_v1.ps1` | `81e0375cba9175105a2de0d7a4d9fd7c170429f851f1c28c60c10f43e63f82eb` |
| `reports/paper_continuation_20261023/test_entry_v2/TEST_METHOD_SOURCE_MANIFEST_v1.json` | `66f6d2e0c042dff9aa07e75f6d0443d38d694097495b30d551dfd94f2c90919c` |
| `reports/paper_continuation_20261023/test_entry_v2/V1_TO_V2_MINIMAL_DIFF.patch` | `c88a3e386447496f0790f64e2c567e89bf4dee6bef262803c742a5b02fbe9c0e` |

`pwsh` AST parsing passed for the v2 builder and launcher. The builder rechecked the frozen source refs and reproduced the existing manifest SHA. A static contract check confirmed six homogeneous method objects, unchanged pre-existing semantic values, JSON nulls only for absent fields, and a manifest hash matching the contract. No MATLAB runtime check was performed.

There is no v2 DEV release yet. The only future DEV invocation, after root review and a new release binds the v2 entry/launcher/contract/manifest, is:

```powershell
& 'C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/c5_test48_v2/RUN_TEST48_EXACT_v1.ps1' -Mode DEV_INPUT_EQUIVALENCE_ONLY
```
