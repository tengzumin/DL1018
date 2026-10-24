# Recovery288 raw 审核器 CODEONLY 任务书 v1

## 当前阶段

本文件只定义实现边界和拟议差异，供根审查。现阶段不新增审核器、不运行 Python、不打开 TEST raw、不评分，也不创建审核结果。根审查确认后，才实现一个独立审核器；实际 raw 审核另需全部输入就绪及根单独放行。

## 目标与范围

新增单文件审核器：`reports/paper_continuation_20261023/test_handoff_incident_v1/recovery_v1/raw_review_v1/audit_test48_raw_recovery288_v1.py`。它在既有 v5 reader 上做最小 provenance / record-adapter 改造，输出范围为 48 个场景 × 6 个方法 = 288 条记录：

1. `B_TRACEABLE`：复用 v3 的 B48 原始输出及其原始身份/OS 收据；不重跑。
2. `CORRECTED_DSSM14_G12_R32`：旧 DSSM scene 1–31 已提交记录；scene 32 原始记录；恢复新增 tail scene 33–48。
3. `CORRECTED_KAN14_G12_R32`、`C5_M110`、`C5_FREEZE_TRAINED_W0`、`C5_NO_DELAYED_PREDICTION`：每方法复用对应 v9 的 48 条输出，验证新的 Recovery208 方法级自然退出收据。

DSSM 的历史退出状态必须明确写为 `UNKNOWN`。scene 32 的原始记录缺少 `runIdentity`，需以根已完成的无评分身份/完整性报告及逐字段审核结果说明这一缺口；不得合成 `runIdentity`、不得把 `UNKNOWN` 改为 OS0，也不得声称旧六方法/进程 OS0 门通过。新 tail16 的独立过程收据仅证明新的 tail16 进程实际退出；它不能追溯证明旧 DSSM 进程退出状态。

## 唯一基线与拟议差异

基线文件：`reports/paper_continuation_20261023/test_raw_review_v5/audit_test48_raw_v5.py`，已批准 SHA-256 `1c7380abd2b1f29e0f7045017abaeef87f54d751ad74a710bfbdbdac504730ff`。该版本绑定 v1 reader、v3 B48、v9 五方法源和方法运行合同；其现有真实 CLI 预检要求全部六个旧自然 OS0 收据，所以不能直接用于这次恢复证据组合。

拟议的窄差异仅限：

| 区域 | v5 当前行为 | recovery288 适配 |
|---|---|---|
| 仓库根与输出目录 | 根按 v5 文件深度推导；结果写 v5 目录 | 根改为适配新子目录深度；唯一输出仍写新 `raw_review_v1` 子目录 |
| 过程收据预检 | 要求 B48 加五个 v9 旧 schema OS0 收据 | 先验证 B48 原收据，再验证五个新 `RECOVERY208_PROCESS_OS_EXIT_V1` 收据：DSSM_TAIL16 16 次及四个完整 v9 方法各 48 次；逐项核对自然等待、OS code、PID、block/method/call 数、入口/launcher/source/release/scope SHA、日志 SHA 与时序 |
| DSSM 方法记录组装 | 把 v9 DSSM 当成普通完整 48 场方法块 | 拼接旧 1–31、旧 scene32 与新 tail33–48；分别走旧身份验证、scene32 缺失身份的明示核验、新 tail 恢复身份验证；来源/索引/状态不互相冒充 |
| 四个 v9 方法 | 读旧 v9 OS 收据，再检查原 v9 48 场 body/batch/raw | 保持 body/batch/raw 验证路径不变；自然退出证据改读各自 Recovery208 sidecar，v9 raw 内仍按原 v9 source/release 身份验证 |
| 最终 provenance/status | 只允许旧六收据全部 OS0 后进入原始 PASS 状态 | 报告新的 Recovery288 数据/身份审核状态，并单独报告 `original_DSSM_natural_os_exit=UNKNOWN` 与旧六收据门 `NOT_PASSED/UNKNOWN`；绝不复用旧 PASS 字符串 |

评分器、Q/分段误差公式、物理场景比对、事件审计、执行器有限性、native-readiness、初始权重检查、数值闭合和统计范围必须逐字保留。v5 审批已标记受保护评分/事件/执行器/native/最终数值闭合区 SHA-256 `66a0ca7e9c137b5a01e529394a9a251e8049a797c3879ac15471d30fa8ef53f2`；实现交付时会另做逐字/哈希核对并列出完整差异，不通过改算法放宽身份门。

## 恢复过程凭证

审核器将只认下列清晰分层的证据：

- 恢复范围固定 SHA-256：`2480b9ac36eaa608a090c312ce2f3d63f37b3830c5054912e559fae720dc1a95`。
- 首 31 条及 scene32 的父级无评分报告：`PARENT_FIRST31_COMMITTED_FILE_AUDIT_v1.json` SHA-256 `5e0e2299c397375eafc680b617dba6e99cb8b3d2e434fc54b8541e63339746d5`；`PARENT_SCENE32_IDENTITY_NO_SCORE_v1.json` SHA-256 `09fbc3c51cd029cbd79da5adb43ad7a43937efaafdd28fb92608250944d12e15`。
- 新恢复源交付身份报告：`PARENT_RECOVERY208_CODE_DELIVERY_v1.json` SHA-256 `858568e6fc1eacd8a84109a579d3fd7f1db6da6c1e8d43f835f6ce6ef9b3b424`；其中协调器 SHA `facc25cff281b883b3d036c6a1c412ac948801409476da902d94e7954fc9093c`、DSSM tail entry SHA `d8e2c47f1310eed71922aa580f9881ca1d508110c3e45fbacf6461a2d66f11fc`。
- 新 Recovery208 run release 在本任务书编写时尚不存在；最终审核器应要求它存在并核对协调器要求的全部精确绑定，不得预写或伪造其 SHA。
- 旧 v9 DSSM 过程的 OS 退出保持 `UNKNOWN`；五个新 block receipts 与旧历史过程分开存档和汇报。

## 读取顺序与禁止事项

1. 先检查源文件/manifest/contract、父级报告、Recovery208 release 与各过程 OS 收据、日志哈希、batch/body/status 元数据。未全部通过自然退出与身份预检前，不得打开任何 TEST raw 或触发评分。
2. 预检通过后，才可逐条读取范围内的 raw，按 v5 原样执行数值与物理/事件审计。scene32 的缺失 `runIdentity` 是显式例外分支，结果须保留该限制。
3. 不修改 v1/v5 reader、统计源码、旧 v9 输出/收据、raw、status、batch、冻结输入或任何训练/控制源；不创建修补 raw、不重跑场景、不访问未授权 TEST raw。
4. 新 reader 仅能写入自身子目录；`--output-json` 必须拒绝目录外路径和覆盖既有文件。实现阶段只做静态源码检查与不触及 TEST raw 的最小 synthetic 检查，真实 CLI 留待根另行放行。
5. 不把全部六个“旧自然 OS0”条件重新标为 PASS。可报告“B48 原始收据 + 五个 Recovery208 新过程收据均自然 OS0”，同时独立报告“旧 DSSM 过程 OS UNKNOWN / 旧六进程门未通过”。

## 根审后实施的交付检查

根审通过任务书后，实施仅提交一个 Python 审核器源码和一份新源码身份/差异报告（不运行真实 raw CLI）。交付至少记录：新审核器 SHA-256、v5 源 SHA、score/physics/event/native/closure 受保护区逐字相等结果、所有文件级差异、命令行写入边界、DSSM scene32 状态披露、旧 OS0 门未通过的断言，以及未打开 TEST raw/未评分/未启动 MATLAB 或 Plant 的事实。根独立审核后，再决定 CODEONLY synthetic 检查和何时放行真实 postrun raw CLI。
