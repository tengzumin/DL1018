# C5 DEV72 parent raw 审计准备任务书

## 范围与冻结身份

对象是 `C5_NO_DELAYED_PREDICTION` 的 72 个 DEV72 场景：60 条 v3 新 raw，加上 12 条已由 screen12 parent audit 验证的 raw。审计器只会顺序重查 60 条新 raw；复用 12 条时只核对固定清单中的 raw、status、run_start SHA 和既有审计记录，不重新打开这 12 个 raw。

核心输入均在脚本中按 SHA-256 固定：

| 身份 | 文件 | SHA-256 |
|---|---|---|
| v3 输入锁 | `experiments/position_c5_matched_ablations_dev72_v3_20261023/C5_NO_DELAYED_PREDICTION/C5_ABLATION_DEV72_INPUT_LOCK_v3.json` | `e0020306b8b7e7fba2948b93cbde30e0ec8f8470ede5dcef5e128d20c8728074` |
| run contract | `.../C5_ABLATION_DEV72_RUN_CONTRACT_v3.json` | `91669018d3d5f19a29c7162f4ed307f7f7371850ff0ffe647fe86bc49825bbcc` |
| source binding | `.../C5_ABLATION_DEV72_SOURCE_BINDING_v3.json` | `db605d55641ddda3c34d3cb6694a678678b683076951f836b58edc79db6ec06f` |
| 60-row batch status | `.../C5_ABLATION_DEV72_REMAINING60_BATCH_STATUS_v3.json` | `4527c178d5d3cfe10ff3c4546bae5cb9fdfd7d8fbb2531bedd119dfaf9b91cc9` |
| 60-row body complete | `.../C5_ABLATION_DEV72_REMAINING60_BODY_COMPLETE_v3.json` | `f54d3f1cbe80da43e73cc90d1cebbb8fb397d3d1cf862d9941097eec4d756577` |
| 12-row reuse binding | `.../C5_ABLATION_DEV72_REUSE12_BINDING_v3.json` | `123f56a288469b5fdf403db09d9d63cab2ca3300283a9fbda6a54df833d83494` |
| screen12 parent audit | `reports/paper_continuation_20261023/c5_matched_ablation_parent_raw_review/C5_NO_DELAYED_PREDICTION_SCREEN12_RAW_PARENT_AUDIT_v1.json` | `807aaedda90638fe03915293f80cc7ed979366d7de94e5a3f68b1d68f3660343` |
| first raw parent audit | `reports/paper_continuation_20261023/c5_matched_ablation_parent_raw_review/C5_NO_DELAYED_PREDICTION_FIRST_RAW_PARENT_AUDIT_v1.json` | `d0d0f3f2fa38f5499aca53c642a1ec65d20758bbc18e67cba2d55fede6e6289d` |
| current B/C5 score table | `reports/paper_continuation_20261023/c5_all_method_dev_comparison/SCENE_METHOD_METRICS.csv` | `a96f1754ba11acf760f6c0490d9452d8e5f03bac6ef49f9e1e78e82318d71416` |
| MAT decoder | `reports/paper14_v2/phase1/audit_w15_position_replay.py` | `372d92cb17da99884e742d3fa0c877200c3bb2bc6fac7f10e7a1a046b97a76af` |

表内 C5_M110 的新 60 行来自独立的 C5 DEV72 parent audit（SHA `bb34889559d95a1c995d4d420e3b3d7a702908b58b47cce969dc508a1c697fab`，event checker SHA `d82e089c7d41f39c620daea63d95315632e6fb2f80addf4dc12e6a4603b8e57e`）；v3 输入锁仅为 12 个 reused scenes 填有 `C5_reuse` raw SHA。脚本按此边界核对：B/C3 全部 72 行与锁相符；C5_M110 的 12 个复用 SHA 与锁相符，其余 60 行要求 score-table 指向该固定 parent audit。

候选固定为 DSSM14、seed `2026102001`、step `60000`、input 14、window 32、`W0` SHA `88f8c4f2495438c3797655c48bab1bf0c11ac2e27bff1f5f2a7423a8f0a2cf53`、normalizer SHA `533aad9a2c66874cfa67f5d268661835e81e58b797cba7d6fc1c12d4013de5f0`。冻结干预为 mask `[1,1,0]`、weight update 开、prediction gradient 关、legacy stage1 update 开；`position_delayed_prediction_enabled` 仍为 true。这里的 “NO_DELAYED_PREDICTION” 是关闭 prediction-gradient 项，不代表禁用延迟参考路径。

batch 是 `C5_ABLATION_REMAINING60_2026-10-23T113102.946Z`，状态为 `COMPLETE_RAW_PENDING_PARENT_AUDIT`，60 条依照锁定的 `scene_ids_remaining_60` 顺序排列，batch index 为 1–60；每条预期状态 `RUN_COMPLETE_RAW_PENDING_AUDIT`、一个 Plant call、20,000 transitions、20,001 state samples、1,968 个事件。审计器会要求 training/optimizer steps 为 0，`TEST_accessed=false`。60 条预期共 118,080 个新事件；加上 12 条既有审计，共 141,696 个事件。

复用 12 条 raw identity（每行 raw SHA 与绑定清单及 parent manifest 一致）：

| Scene | Raw SHA-256 | Status SHA-256 | Run-start SHA-256 |
|---|---|---|---|
| `DL1018_VAL_T1_C00_W07` | `ce4cf4fed7cc5de26d56874ed82a5c927478957c101e32e43cf9adbf1d5a299c` | `7ff1f8a565ff0409f24af8c0b0a204312a5f2b9ff32cfdaf2050bd32a6d22575` | `660958df716fa0cb43fd2b937ff8b4d04a9d90414638b552fa32ae7d69f24397` |
| `DL1018_VAL_T1_C02_W09` | `82a0c07d86e884e3d89ed78d7312c97ba47b738a1c5cb0cae00b0f6957735337` | `42a3101a0ca174e14cc4618b7d5ae59988db7cfc977e7a2ee7440b805d5c34d9` | `dde38c88789db3054b715a1f44cd4641382d695cfa6705de0dcd9a8c469f678b` |
| `DL1018_VAL_T1_C05_W12` | `fc87272d3c07b20bcdd38905c1e2c0ce0f38bc74223d0e12f9a80a64a86e5212` | `8679e126b610e8c3624223e86ef328f31bcff906dd818622c0bcc48b4896446d` | `bb896af66e71c7a572f36149af29492649e8944d7b0628ea597f48c47976e2a0` |
| `DL1018_VAL_T1_C08_W15` | `464eeaf72eb34a0304c8c3c0a58ab67098f1459ae8c4a9a6083d54e4f43307a4` | `1ca17fd045ada4e08b1107fca66631a48d7c1480b3813670d507e6f106b094f7` | `e2eab63bccb23c21ddb22992429905d0bc39b5ceb880ae52e8c025e21486d896` |
| `DL1018_VAL_T2_C00_W10` | `41e6a4a83a994f20ebaad5ac42cd273169250951e59f045f3d11652ccc56f316` | `c6fad63af7a3e06d695306993f6f7de0cb0ec715e321785c02b56d0fc34c6c4d` | `4bc5b0a79d33fc2b235d624bf3042535191efe51bc7767a8b29ce4cc771addb5` |
| `DL1018_VAL_T2_C02_W12` | `7670eafdb65eccf06e7b774f5c06e059b4920f118b61d2e51b5b7a4eadacab4a` | `bc74c778f3faff6115ffdfa04cd8b35b9dfcb47f176c5a7810ad1734dddb21b7` | `3fc8e97445d72ee974afe1f4c61ce8248786cffe8e2b5f3af6606847d1342bb0` |
| `DL1018_VAL_T2_C05_W15` | `5bc7a70d3003d2bd267dee0b14da026c54e4d6ade91e00fef17fae4aa2122fcd` | `754f2c72640682a4d9efadcd2995fedf4425a2d9bd658ad8611cc2664b201e1a` | `633492431bf321f51f44495abe00cf5ac5a936009a30d408b83b0b452019462a` |
| `DL1018_VAL_T2_C06_W00` | `cee715c6fdc5763a25ae684c475b0687b06511adf1bf1e87203dafefb8f41016` | `9035b0bdf43340d5b8f48703747e46f1ce6abde30e86cbd84e1032bbb1c2dd56` | `9a552379d650dec39c56af64713cd43a34f9fb83612553008143e7fe5f101d83` |
| `DL1018_VAL_T3_C00_W13` | `f68502e5821a21eb961eff86f0d018fa0843a5407206a1dd03e9c15ecd35bc00` | `f132bbaaff44657c12fe8242a2067012dc250b601134df98b067a09b2fbdde07` | `9cd0b9d3bf05b00402bdf61d674d49cea06f52f242bc011b98f0f553019ea267` |
| `DL1018_VAL_T3_C02_W15` | `42426225a464691d1c0868179d30e95925b881c05443c18cd293ee79a500d64e` | `75a584459c6ff75a1b8a7b55e2018c35a08b29e98b7684191813840f6bd626b7` | `c20c6b6a2aae47dd5f8446ea5d477767f7adbab9952ce8e8669ee25453445f30` |
| `DL1018_VAL_T3_C03_W00` | `2ad9fac20c4b4f562c5e359e96f06ba5314622ab4e8f32d151123dca9304f0c1` | `acd3e585a35940028a4f19807cf55c50856d868904bbb2f42849b4da6f4c72fd` | `5e5599e4c91178aaa3c246aae3529a28a225a0ea66184eca7b93a7e60bb84dd0` |
| `DL1018_VAL_T3_C12_W09` | `1c2b4e097f622fd8c222be39c9e7f4c33c90ca85380b9a9eb971d221a76ef94e` | `8e339b31e968615d3951a474eb9ed210d23ecf0051b395add860b8a1aa8e5332` | `afcd491dcf22b49885e8b78bdcee52ccccd7885e8b9d1e30bbf8ceabe2375c34` |

## 审计规则与输出

审计器在开始 raw 检查前固定核对锁、run contract、source binding、prepare/preflight、parent release、batch/body、reuse12 binding、screen12/first audit、事件检查器、decoder/scorer 与分数表 SHA；并逐一重哈希 source binding 中的 75 个 source refs 和准备快照。它拒绝非绝对路径、非本目录直属的 `audit_run_*` 输出目录或任何已存在的输出目录。

对 60 条新跑，审计器顺序核对锁定 raw 路径与 raw SHA、run_status SHA/字段、run_start SHA/字段、两类 marker 的路径和 SHA、physical B 与 C3 来源路径和 SHA、状态文件及其 run_start/marker SHA、32 项 active source identity、W0/model identity、TEST/training 标志，并复用已固定的 C5 事件检查器逐 raw 验证 1,968 个事件和零 prediction-gradient。还使用固定 scorer 生成新 C5_NO_DELAYED 分数，与当前表中的同场景 `B_TRACEABLE`、`C3`、`C5_M110` 对照。

输出只写入显式提供的新目录，使用 exclusive-create：`C5_NO_DELAYED_DEV72_PARENT_RAW_AUDIT_v1.json` 和 `.csv`。任何 SHA、schema、路径、行数或字段不符都会失败关闭；不会修改实验输入或历史输出。

## 后续顺序命令

等当前 Full72 MATLAB 实验结束后，再在 PowerShell 7 中顺序执行：

```powershell
Set-Location 'C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\reports\c5_dev72_parent_raw_audit_prep_v3_20261027'
$out = Join-Path $PWD 'audit_run_20261027T120000'
python .\audit_c5_dev72_nodelay_parent_raw_v3.py --output-dir $out
```

该命令不启动 Plant 或 MATLAB，不训练模型，不访问 TEST。审计器只用 Python/h5py 读取锁定的 MATLAB v7.3 快照、60 条新 C5 raw 和需要核验的来源文件。

## 准备阶段验证与限制

- 仅用 Python AST 解析检查了新脚本语法；没有运行审计器、打开/加载/扫描任何 C5 raw MAT、运行 Plant 或 MATLAB、训练、访问 TEST，也没有读写 Full72 候选实验。
- 当前分数表共 360 行；`B_TRACEABLE`、`C3`、`C5_M110` 各 72 行，另含两个 corrected 模型各 72 行。它没有完整的 C5_NO_DELAYED 72 行；既有 no-delay 分数只覆盖 screen12。新脚本只把旧 12 行作为审计复用并为新 60 行重新计分，不会把 `C5_M110` 标签改成 no-delay。
- 新 v3 run_start/rawIdentity MAT 内容未在准备阶段打开。脚本沿用已审计 C5 checker 的 schema 约定（`C5_MATCHED_ABLATION_RUN_START_V1` / `C5_MATCHED_ABLATION_RUN_IDENTITY_V1`）；任何实际 schema 差异都会拒绝审计。开始生产审计前应由 root review 这项约定。
