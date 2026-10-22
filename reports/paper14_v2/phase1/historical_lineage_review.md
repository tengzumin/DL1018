# 历史成功结果与 corrected14 血缘审阅

日期：2026-10-22。只读核对本地报告、协议、身份 JSON、汇总 CSV 与源码哈希；未打开 MAT/checkpoint/缓存内容，未读取 TEST 数据或指标，未运行实验或改代码，未操作实验进程。当前 corrected pair 的 raw 身份仅通过已发布的 CSV SHA 字段核对。

## 结论

旧成功结果真实存在，但与当前 corrected DSSM14/KAN14 不是同一模型、同一批 raw 或同一评估范围。它能证明旧模型包在特定开发场景和控制合同下表现好，不能证明当前模型已达到论文门槛，也不能把跨批次差异归因于单个网络部件。当前 corrected DSSM14 72 场为 46 胜，低于任务书的开发门槛 62/72；KAN14 为 28/72。两者都没有独立 TEST 结论。

## 结果沿革

| 阶段 | 实际条件与结果 | 可以得出的结论 |
|---|---|---|
| 教师复用六场筛选 | 2026-10-20 报告中 DSSM14 选用 seed `2026102001/final_step`，六场位置 Q=15.389 mm，同场 B=20.357 mm。它属于 TRAIN 六场筛选；候选含多架构、多 seed 和 best/final 包。 | DSSM14 曾在小型已看开发筛选中优于 B；不是 72 场结果或盲测。来源：`experiments/teacher_reuse_model_screen_v1/reports/FINAL_REPORT_ZH.md` SHA-256 `5B933F16…122BFCE`，第 34–47、67–70 行。 |
| 旧 N_KAN 的八场迁移成功 | `OLD_G12_R32` 在 8 个 `DEV_T2/FIG8_3D` 场景全部完整，Q=18.439 mm，B=20.805 mm，7/8 胜、相对改善 11.37%。旧包来自 DL1009 commit `3671d2d212af927abdb6d9149a1b249c372ac55e` 的 `N_KAN`，自带 normalizer 和 W0。旧包与新 KAN14 在同一 8 场/控制合同下做了 G1/G12 矩阵；两包在 G12 下宏 Q 分别为 18.439/24.118 mm。 | 旧包整体可在这 8 场工作；结果不识别 normalizer、encoder、W0 或训练历史的单独贡献。G1/G12 差异是该小范围控制增益对照，不是普适最优增益证据。来源：`experiments/old_kan_fig8_transfer_compare_v1/reports/FINAL_REPORT_ZH.md` SHA-256 `EACEE739…A4FC4ED02`，第 12–22、36–38 行；`protocol.md` SHA-256 `56DE49AD…4AC97F1`，第 7–11、24–26 行；`audit/SOURCE_IDENTITY.json` SHA-256 `10251C50…7E0797F`。 |
| 历史 FULL72 评估／旧 runtime replay | 2026-10-21 历史报告给出旧模型包在 VAL48/DEV24 的结果：DSSM14 分别 27/48、13/24 胜；NEW KAN14 为 17/48、8/24。该报告确认当时修正参考训练 G3 尚余 522 条未采集，528 条计划数据未齐、修正参考训练步数为 0；因此这是旧模型的评估与旧 raw replay，不是后来 G3 后训练出的 corrected 模型。`NN_RUNTIME_REPLAY.csv` 是对历史 216 个 NN raw 的离线重放一致性审计；报告明确 `FINAL_REPLAY_COMPLETE` 代表覆盖与诊断完成，不是性能胜利。 | 旧 FULL72 是与当前结果不同血缘的对照记录；runtime replay 只能证明历史日志重放和当时合同一致，不能证明当前 pair 的模型或逐运行参数身份。来源：兄弟目录 `REFERENCE_FIX_FULL72_20261021_022342_313/supporting_rescore/reports/FINAL_RESULTS_REPORT_ZH.md` SHA-256 `7F0AA2DD…E202EDF15`，第 4、14–25、56–58、64–76 行；历史 replay CSV SHA-256 `FCC9176B…F672B471`。 |
| 当前 corrected pair | 修正数据流程后，固定 seed `2026102001`、60,000 steps 发布 DSSM14 与 KAN14；G4 记录 TRAIN 1,536 episodes、3,070,464 event rows、605,184 windows。当前 72 场等权 Q：DSSM14 12.387 mm、46/72 胜；KAN14 15.042 mm、28/72 胜；同一当前 B 为 17.058 mm。范围只有 VAL48+DEV24、三种任务，无 TEST。 | 这是当前 corrected 模型的开发集结果。DSSM14 宏平均明显好于 B，但胜场未过既定 62/72 门槛；不能宣称论文证据包或独立泛化达标。来源：`reports/corrected14_full72_benchmark_20261021/RESULTS_14D_VS_B_ZH.md` SHA-256 `4AF9E7C5…8A16B75`，第 7–18、119–125 行；G4 记录 SHA-256 `21F1DE72…675F1C4`；拟合记录 SHA-256 `F3C897D3…ADD54CD7`；模型绑定报告见下方。 |

八场旧包迁移协议的运行条件是 current-frame X14、FEATURE+PCF、κ=1、beta rise 1.8 s、Gamma=1/12、位置补偿每轴 ±3 m/s²、W 元素投影 ±60、leakage 0.002/s、位置 RBF 关闭且位置 BS 保留；B 姿态 BS/RBF 和 C0/J0 固定；Plant 1 kHz、位置事件 100 Hz、20 s、ZOH。每格独立重置 W0/PCF；readiness=32 与模型 context length 分开，首 32 个事件后才开始输出。当前 corrected pair 的 published method ID 为 G12/R32，但这次仅核验 model binding 与重放汇总，未审其逐场 `run_start`，故不将旧协议代替当前运行参数证明。来源：`experiments/old_kan_fig8_transfer_compare_v1/protocol.md` SHA-256 `56DE49AD5E7D5BE71C9ADA806CF4FA400BB636D4339863D6DC635F6A14AC97F1`，第 7–11 行；当前实际 forward/model binding 如下列证据表。
## 哪些变化已确证，哪些仍不能归因

| 项目 | 已核实事实 | 分类与解释边界 |
|---|---|---|
| 参考生成实现 | 已确认旧 FIG8 Y/Z 加速度二阶项少乘因子 2；位置、速度、HELIX/SQUARE 公式未变。8 场原/修参考配对复核中，NEW KAN 相对同场 B 的宏差距从 +3.313 mm 降至 +0.347 mm，8/8 场差距均缩小，但修正后仍宏观输 B。 | **实现错误已确认并修复；对 NEW KAN FIG8 有可归因的局部影响。** 它不能解释所有旧/新模型差异。来源：`reports/integration_next14_v1/PARENT_REVIEW_AND_DECISION_ZH.md` SHA-256 `961C7012…7D967` 第 13 行；历史修正报告 SHA `7F0AA2DD…E202EDF15` 第 42–54、72–76 行。 |
| KAN 分支 dispatch | 历史审查还记录 `P_NEW` 未进入 KAN applied 分支；这是与参考公式分开的实现缺陷。 | **实现错误已记录；**现有证据没有把它定量归因到 OLD_G12 或当前 corrected pair 的胜负。见历史修正报告第 72 行。 |
| 模型/训练血缘 | 八场旧成功包为 DL1009 `N_KAN` 完整迁移包；CURRENT KAN14 是独立的 seed 2026102001、final_step 60k 包。当前 corrected DSSM/KAN 又是修正数据流程后拟合的新发布包。旧 repair 的准确 `--initial-dir` warm-start 未留完整记录。 | **实验条件与身份变化，不等于实现故障。** 旧/新架构、normalizer、W0、训练和选模历史混在 package 级变化内；不能据 package 对比指定单一根因。 |
| 场景和统计口径 | 旧成功矩阵只选 8 个 DEV T2 FIG8 场景，按 8 场宏平均；当前为 48 VAL+24 DEV、HELIX/FIG8/SQUARE 三任务、每个场景等权的 72 场主指标。两者都报告 0–20 s 位置 Q，但支持范围完全不同。 | **评估覆盖变化。** 指标同名不使 8 场与 72 场成为同一试验。FULL72 不含盲测。 |
| B/参考输入 | 旧 8 场 CSV 与当前 pair CSV 的重叠场景 B-Q 八场全部不同，绝对差为 2.809–7.845 mm；例如零风 `C02_W15` 从 14.035 降到 6.978 mm。旧协议称旧 B 来自官方生成器核对过的稳定 raw；当前报告称 FULL B 51 条来自已验证缓存、21 条重扫。 | **有效比较条件确实改变。** FIG8 参考修正是已知条件变化之一；仅凭 Q 表不能断言每个 B 差值由哪段代码或缓存造成，也不能声称 B 控制器版本已改。旧/当前 B raw 没有在本次审阅中逐文件读取或建立完全等同的 SHA 对照。 |
| 历史 replay 与当前 pair 身份 | `NN_RUNTIME_REPLAY.csv` 中旧 DSSM、旧 KAN 各 72 行，与当前 pair CSV 按 split/task/scene/contract 均可对上 72/72；但候选 raw SHA 每种方法均 0/72 相同。当前 pair 的模型绑定报告给出实际 forward SHA、DSSM/KAN MAT 与 checkpoint SHA，64 个 parity fixtures 通过。 | **把历史 replay 当作当前 pair 参数或 raw 证据属于 provenance 混同，报告现已修正。** 当前 per-run `run_start` 的 gamma/kappa 本次未审；不能沿用旧 replay 的 gamma/kappa。模型发布身份虽已绑定，也不替代逐运行 opts 核验。 |
| 身份聚合哈希 | 早前 `model_arrays_sha` 汇总哈希不同，核对结果是五个数值元数据键集合不同；共享学习权重 key 的逐项哈希一致，scalar flags 相同。 | 没有证据证明这是 learned-weight 冲突；这是聚合哈希口径差异。 |

历史 NNR 与当前 pair 的离线 CSV 联结结果为：DSSM `72/72` scene+contract 对应、`0/72` raw SHA 相同；KAN 同样为 `72/72` 对应、`0/72` raw SHA 相同。当前 pair 实际 forward/model 身份来自 `corrected_reference_training_v1/corrected_pair_eval_v1/reports/PAIR_EVAL_MODEL_BINDING_FORWARD.json`（SHA-256 `CC5616B3C10DEF65B8CB3636D92219DD5ED4848A1651D4C1F1D81F147FD384AF`）：隔离 forward `position_stage1_model_forward_v2.m` SHA `dc803aa1…a293676`，DSSM MATLAB export SHA `6f3628b1…d9c9b6e`、checkpoint SHA `544b018b…02dfbf5`；KAN MATLAB export SHA `0a24606f…b8219c9`、checkpoint SHA `bff45dd3…e2d4269`。该 preflight 记录 64 个模型 parity fixtures 通过，但不绑定每场 raw 的 runtime opts。最终配对 CSV SHA 为 `B2264145…169137`，输入验证摘要 SHA 为 `E3759BA8…02C5BAC`。

## 最终根因判断与边界

能够确定的具体错误是 FIG8 参考加速度二阶项因子 2 遗漏；它已在源码层修复，并有同条件原/修参考复核支持其影响一部分 NEW KAN FIG8 退化。另有一项 KAN dispatch 缺陷已记录，但其对现有汇总结果的贡献未量化。当前 DSSM14/KAN14 的训练数据、模型包、normalizer/W0 和运行 raw 均与旧成功包不同；旧成功只覆盖 8 场，旧 FULL72 replay 也不是当前 pair。场景重叠下 B-Q 变化进一步证明有效评估条件变了，但没有足够的逐 run B 身份证据把变化拆成具体原因。因此，**旧模型成功、历史模型全面胜 B、当前 corrected 模型退化**都不是可由现有证据支持的概括；当前可靠结论是当前 corrected DSSM14 平均胜 B、但 26/72 输场且未过预定胜场门槛，需先在当前 pair 自身的同状态机制分析中定位原因。

本审阅未使用原始 MAT、模型或 TEST；没有据此声称跨训练种子鲁棒性或对损失作闭环因果归因。
## 身份证据索引

| 产物 | 路径 | SHA-256 / 记录值 |
|---|---|---|
| 旧八场最终报告 | `experiments/old_kan_fig8_transfer_compare_v1/reports/FINAL_REPORT_ZH.md` | `EACEE739D09CD7C9FFDDC3BDE90EA23596358680969F86DCBE4A121A4FC4ED02` |
| 旧八场协议 | `experiments/old_kan_fig8_transfer_compare_v1/protocol.md` | `56DE49AD5E7D5BE71C9ADA806CF4FA400BB636D4339863D6DC635F6A14AC97F1` |
| 旧/新包身份清单 | `experiments/old_kan_fig8_transfer_compare_v1/audit/SOURCE_IDENTITY.json` | `10251C50A9557682A628BD669C7534C27B40D11D69974B65389898A387E0797F`；旧包模型导出 `69f4a6bd4cd14c7cd443f1c3552b5f1588d7d022c5d076b3f1f44dbda33d7f12`，normalizer `86d85db3f0d2d9f01d1b339e66d31dfc460aa9c35aa7534442fa4d22b39f5326`；旧源 runner `49594695e9b31ac00da36ebffabd068afd1a57dbb0b19a508a70304d3c7a40cb` |
| 旧 G12 代表运行状态（只读 JSON） | `experiments/old_kan_fig8_transfer_compare_v1/runs/main_matrix/DL1018_DEV_T2_C00_W04/OLD_G12_R32/attempt_01/run_status.json` | 状态 JSON SHA `9FF7F73EB1CAE1502FC2BCF296E7F1216F53F820476D74F8218DBE602A422648`；其中记录 raw SHA `597025084a1c6368ed73d3a18300ae20c4426a134f40e7d5267408cc9bf63bc0`，20,000 transitions、PASS、Q=0.0176070028783343 m、gamma=12、readiness=32。此处引用的是状态记录，不是本次读取 raw MAT。 |
| 旧 G12/包矩阵 CSV | `experiments/old_kan_fig8_transfer_compare_v1/reports/FIG8_MODEL_GAMMA_PAIRED.csv` | `07FE09B9B5980E0D24DEB1ECCE8D923D66F5A1AC878DCA9E0F325D0D815079AF` |
| 历史 corrected-reference FULL72 报告 | `..\REFERENCE_FIX_FULL72_20261021_022342_313\supporting_rescore\reports\FINAL_RESULTS_REPORT_ZH.md` | `7F0AA2DDAAB6459039DEF945D4545EA1BDFCD1F4767DD1C86F9BD80E202EDF15` |
| 历史 NN replay | `..\REFERENCE_FIX_FULL72_20261021_022342_313\supporting_rescore\runtime_replay\outputs\NN_RUNTIME_REPLAY.csv` | `FCC9176B0B7A49602F0AA4B7B5C199C163632A76D958023B0C5855A8F672B471` |
| corrected 14D 最终结果 | `reports/corrected14_full72_benchmark_20261021/RESULTS_14D_VS_B_ZH.md` | `4AF9E7C5A925C6BC0730184BEC3DC74879A4FDE2A163938B4E112E6DE8A16B75` |
| corrected pair 场景表 | `reports/corrected14_full72_benchmark_20261021/PAIR14_SCENE_RESULTS_VS_B.csv` | `B2264145E9D18896F5764FFE38302576DD08C80E7CCE1C277323246092169137` |
| 当前模型/forward binding | `..\REFERENCE_FIX_FULL72_20261021_022342_313\corrected_reference_training_v1\corrected_pair_eval_v1\reports\PAIR_EVAL_MODEL_BINDING_FORWARD.json` | `CC5616B3C10DEF65B8CB3636D92219DD5ED4848A1651D4C1F1D81F147FD384AF` |
| corrected-reference 源码修复审查 | `reports/integration_next14_v1/PARENT_REVIEW_AND_DECISION_ZH.md` | `961C70129C868FF7B8B274AB5414ED8C6315E686DC28C3BB5D406C327476D967` |

