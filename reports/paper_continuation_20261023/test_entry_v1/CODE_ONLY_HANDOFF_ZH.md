# TEST48 独立入口：CODE ONLY 交接

当前交付只完成了入口源码与冻结身份清单，没有运行 MATLAB、生成 TEST 场景数组、启动 Plant、训练或读取 TEST 结果。三个运行阶段仍各自要求外部父级 release；当前 code-only release 不授权这些阶段。

DEV 阶段先校验源码、上游锁和资源基线，再从固定 72 个 DEV/VAL ID 中逐项生成当前/历史两套场景包。生成器调用之前，入口已按六方法顺序各调用一次 `build_method_snapshot(root,method,cfg)`，记录 cfg/opts、模型与归一化器身份、W0 摘要及 `which` 路径绑定。DEV 还逐字段写出两组生成包差异、数组形状/类型/SHA、最大差和 bit-equal 标记。唯一临时规范化是已绑定勘误记录的 `reference_contract_id=DL1018_SCENE_REF_FIG8_A2_V2`：必须先核实该值且历史生成器中缺失，再只从比较副本删除此注记。

TEST 输入冻结必须另有父级授权，并保持 G01 与原始 48 行 TEST 场景设计已封存。它一次生成并共享同一组排序后的 48 场景，为六方法分别保存 cfg/opts 快照；生成的数组索引逐字段保存 shape、MATLAB class 与 SHA。正式运行按六方法独立、顺序 MATLAB 进程执行，每场重置权重并逐项落盘 marker、run-start、raw 与 status。控制器计时边界保持不变，计时截至 allocator/Plant/MAT 保存之前。正式 release 需要绑定当前入口与 launcher 字节 SHA。

资源门使用锁定观察值 `21,371,186,747` 字节作周期既有产物基数，累计 TEST 产物及保留空间不得超过十进制 `80,000,000,000` 字节，并保留 `30,000,000,000` 字节磁盘余量。正式阶段按剩余场景总数和剩余 MATLAB 进程数保留时间预算。单场或单方法失败即停，不覆盖、不重试。

## 新建/冻结文件

| 文件 | SHA-256 |
|---|---|
| `experiments/c5_test48_v1/test48_entry_v1.m` | `68022e05ee1d81542ea60970c472ba743a53aaeef201e4e1bdbe8c7413157646` |
| `experiments/c5_test48_v1/RUN_TEST48_EXACT_v1.ps1` | `e5fda783ae711815acf8a6a379845e192551b3ceec6eaae8b78d4a9c15adc13b` |
| `experiments/c5_test48_v1/TEST48_RUN_CONTRACT_v1.json` | `7224e535be4ff531a8a147e865fdb910a405f87668ddcf494a369e9301819754` |
| `reports/paper_continuation_20261023/test_entry_v1/build_test48_method_manifest_v1.ps1` | `7cfc8c8d422ecaaba7a04c68512aa03782a6ab523ae4715b6e399b58e7ff41f9` |
| `reports/paper_continuation_20261023/test_entry_v1/TEST_METHOD_SOURCE_MANIFEST_v1.json` | `e857629e032a7803ad641e81ea581307dcf2f66530e9e5728ce490909d368efe` |

manifest 固定六方法的实际锁、合同、cfg/opts 快照、源文件、模型与 normalizer；并绑定 DEV metadata 勘误、周期资源观察记录、场景生成器和 `TEST48_SCORE_STATISTICS_CONTRACT_v1.json`（SHA `c7d2983a031b56b16950ede637cce598f6c169b1fea6dc3a092f4337489d992c`）。PowerShell 7 构建器已两次从仓库根目录运行并得到相同 manifest SHA；其 corrected runtime 树摘要也逐项重算并匹配锁定身份。

## 静态验证

- `pwsh` 对 manifest 构建器与运行 launcher 执行 `System.Management.Automation.Language.Parser.ParseFile`，两者 AST 均通过。
- `pwsh` 解析 manifest/contract，确认六方法、统计合同引用、manifest SHA、资源基数和十进制总上限一致。
- 未运行 MATLAB，也未生成、读取或评分 TEST 数组。MATLAB 文件仅完成静态审阅，需由后续授权阶段验证运行时行为。

后续仅在根级分别提供对应 release 且 release 绑定此处 entry/launcher SHA 后，才可运行以下单层 PS7 命令；它们此刻只是受门控的命令文本，不构成授权：

```powershell
& 'C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/c5_test48_v1/RUN_TEST48_EXACT_v1.ps1' -Mode DEV_INPUT_EQUIVALENCE_ONLY
& 'C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/c5_test48_v1/RUN_TEST48_EXACT_v1.ps1' -Mode TEST_INPUT_FREEZE_ONLY
& 'C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/c5_test48_v1/RUN_TEST48_EXACT_v1.ps1' -Mode LOCKED_TEST48_PARENT_APPROVED
```
