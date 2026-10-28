# C5 轴坐标 DEV72 父级 raw 审计准备

## 范围

本提案只针对 Full72 scorer 当前绑定的 `experiments/position_axis_coordinate_c5_dev72_20261023/C5_DEV72_INPUT_LOCK_v3.json`，schema 为 `C5_AXIS_COORDINATE_DEV72_INPUT_LOCK_V3`，候选为 `C5_AXIS_MIXED_COORDINATE_M110`，坐标掩码为 `[1, 1, 0]`。它使用轴坐标 C5 v3 的 60 个新 raw，并按 SHA 复用该实验先前已审的 12 个 C5 screen raw。

明确排除 `C5_NO_DELAYED_PREDICTION` 和任何 matched-ablation v3 文件；它们是不同实验。本任务只新增本目录中的提案脚本和本任务书。未运行 MATLAB、Plant、训练或任何 raw 审计，未打开或哈希任何 60 个 C5 raw MAT，也未更改旧审计器、batch status、Full72 score 产物。

## 当前锁定身份

| 文件/绑定 | SHA-256 |
|---|---|
| C5 v3 输入锁 `C5_DEV72_INPUT_LOCK_v3.json` | `82024c01276cc4bfbd9b7772cf5332dee3fdfcbed422969589b68f1c90ed2d75` |
| C5 v3 批次状态 `C5_DEV72_BATCH_STATUS_v3.json` | `20cc9caca553ebf676fd7b39087fe0a2640fcd976aaf7c8cdb0030c76b5bea22` |
| C5 v3 源绑定 `C5_DEV72_SOURCE_BINDING_v3.json` | `360fe096bdcdfefcdb320469736596c44587f07cc7e40c97e61ed318ecf95934` |
| C5 v3 release `C5_DEV72_RELEASE_v3.json` | `4177f92a83a2a2ba80a98b3a8fb2f7806d64c3e6322ff3ce637a605db319f053` |
| C5 v3 run contract | `6ac3cd505dc13fc5b7e6e0cdef966b21225b54d6f847d32177d43f7c678c8150` |
| C5 v3 parent release contract | `3e7106037c4176027ec07e8769284ac39007c634d307839d5e36da2726adc27e` |
| C5 v3 prepare receipt | `ca1fbd9bdf2d7a7b02b15d36ed010fbb1851b4607394c426f6d4d6d408ce3095` |
| C5 v3 body-complete receipt | `ea205a0cdd46026112d5381910887f71f3103d71d495980b504c06be3772b4c5` |
| Full72 `FULL72_PAIRED_SCORE_v1.json` | `d197cd0e7fc580b6b575ec193571dc595a4527f3bbba2c0e7e0b48daf021b0ff` |
| Full72 `score_full72_candidate_v1.py` | `6baf689802f4d73ead813449e52a8fe85cb0be92c3185850c93646da2d54dd16` |
| v3 prepared cfg/opts snapshot SHA recorded by prepare/status | `842ef395569e675db6e139c2684d72b976946915e5e0a58b9b7f24ec10c1d24a` |

Full72 score metadata指向同一 C5 v3 lock/status SHA，72 行中 60 行保持 `RUN_COMPLETE_RAW_PENDING_AUDIT`，另 12 行为已审 C5 screen 复用项。当前 batch status 为 `COMPLETE_RAW_PENDING_PARENT_AUDIT`，记录 60 场、60 Plant calls、0 training/optimizer steps、`TEST_accessed=false`。拟议脚本会在运行前重新校验这些身份与分区。

注意：v3 lock 文档中的字段 `c5_input_lock_sha256=10a7ee…` 是其上游历史 C5 screen lock 的 SHA，供 12 个复用场绑定；它不是当前 v3 lock 文件 SHA。当前 v3 lock 的文件 SHA 是表中的 `82024c…`。脚本分别命名并检查这两个哈希，防止混用。

## 12 场复用依据

复用来源为 `reports/paper_continuation_20261023/c5_axis_coordinate_parent_review/screen12_parent_review/SUMMARY.json`，SHA-256 为 `fe217ac8b259706b1953e07dd44586b6a64368a6d4f5e0145e8f507863d82ad8`。该文件有 12 条 `PASS_C5_RAW_ALL_EVENTS` 审计，每场 1968 个事件、总计 23,616 个事件。逐场核验已确认其 `raw_sha256`、`run_status_sha256` 与 v3 lock 的 `C5_reuse` 及 Full72 C5 行逐项相等；Full72 也把这 12 行标记为已审。拟议审计器只复用 SUMMARY 中已存在的证据行，不重读这 12 个 MAT。

复用审计的历史执行器为 `reports/paper_continuation_20261023/c5_axis_coordinate_parent_review/check_c5_raw_parent.py`（SHA-256 `59cb79f91d49e3d5ca3c268007038a66a3692f75a2cd354535f13cb8ad39fdcb`）。其指标 scorer `reports/delayed_prediction_c3_dev72_parent_20261023/parent_raw_metrics.py`（`c64482d0adbc4358417648ec08351bd78f1d3dbdb38950435fa71b9cb0f531b1`）和 MATLAB v7.3 解码器 `reports/paper14_v2/phase1/audit_w15_position_replay.py`（`372d92cb17da99884e742d3fa0c877200c3bb2bc6fac7f10e7a1a046b97a76af`）也已固定到脚本输入绑定。旧 checker 针对单场 v1 状态格式硬编码了旧 lock/snapshot 路径，不能直接调用；新脚本保留其 M110 事件方程检查，改用 C5 v3 lock/status/schema，并加上 Full72 scorer 的路径、SHA 与场景配对校验。

## 拟议运行行为

提案脚本：`audit_c5_axis_coordinate_dev72_parent_raw_v3.py`。它只有显式传入 `--execute-after-root-review` 才会进入元数据预检；预检要求 Full72 scorer、当前 C5 v3 输入、12 场复用记录、source/release/status 和依赖 SHA 全部吻合。输出只能新建在本目录 `audit_output_v1/`，目录及每个 JSON 均采用独占创建，旧证据不会覆盖。

预检通过后按 v3 lock 的原场景顺序逐场处理：12 场只复制经 raw/status SHA 对齐的既有审计记录；60 场严格串行处理，始终在完成当前 scene 后才触及下一 scene。每个新 raw 会先做 SHA 校验，再由事件检查用 h5py 读取，随后由旧位置 metric scorer 对同一 raw 再次读取并校验 SHA。审计复算其 1968 次 M110 事件、过去时刻目标、beta 时钟、联合更新、保持补偿、力链及 PCF 步进，并从 raw 的 `scene/reference/position` 按 Full72 scorer 的 20,001-state 定义计算 Q 后逐场核对。旧位置 metric helper 的 `Q_0_20_m` 使用 20,000 个 transition states，故不与 Full72 的 `Q_m` 直接比较。每场成功后立即以独占创建写出一份 JSON；全部 72 场成功后才写总摘要。任何校验失败即抛错，不生成 PASS 总摘要。代码没有并行、重试、MATLAB、Plant、训练或 TEST 数据访问路径。

建议命令（仅在 root 独立代码审查通过后执行）：

```powershell
python reports/c5_axis_coordinate_parent_audit_prep_v3_20261027/audit_c5_axis_coordinate_dev72_parent_raw_v3.py --execute-after-root-review
```

## 尚未解决的 MAT schema 假设

准备阶段遵守不打开/不哈希 C5 raw MAT 的限制，因此下列 v3 MAT 细节没有实物验证；脚本全部采用显式字段/形状断言，遇到差异会 fail closed：

1. 新 `run_start.mat` 仍有可由旧解码器读取的 `runStart` section，并包含 `cfg`、`opts`、`source_identity`；snapshot 对应 sections 仍命名为 `cfg`、`opts`、`sourceIdentity`。
2. v3 prepared snapshot 的结构叶子数仍是 `cfg=120`、`opts=43`，除运行时 `r2e_first_plant_step_marker` 外与 `runStart` 对应值一致。
3. raw 仍以 HDF5 `log` 组储存；旧 checker 使用的 `stage1_position_*`、`state`、`filtered_attitude_reference`、`reference/velocity`、`reference/position` 字段名及其转置规则在 v3 保持一致，且 Full72 scorer 使用的 `scene/reference/position` 存在、解码后为 `(20001,3)`。事件为 320 到 19990、步长 10，事件权重张量布局可转为 `(1968,33,3)`。
4. v3 原始运行的 M110 常数和离散步方程仍与已审 v1 screen 一致：mask `[1,1,0]`、gamma 12、kappa 1、`k1=[1,1,1]`、`k2=[4,4,4]`、20000 转移、20001 状态、每场 1968 个更新事件。若版本有意改过任何一项，需先由 root 审阅并更新审计定义，不能删掉断言后继续。

本次唯一的代码验证是对提案 Python 文件做 AST 语法解析；未执行脚本、测试或任何 MAT I/O。root 在审阅代码与上述 MAT 假设前，不应启动 raw 审计。
