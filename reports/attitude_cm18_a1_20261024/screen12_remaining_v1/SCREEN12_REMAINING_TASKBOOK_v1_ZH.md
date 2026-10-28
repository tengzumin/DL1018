# CM18-A1：SCREEN12 剩余11场准备与单场运行任务书 v1（草稿）

## 状态与边界

本目录只准备固定清单的剩余11场单场入口。首航 `DL1018_DEV_T1_C01_W15` 已完成；只有首航逐事件 raw audit 文件 `A1_FIRST_FLIGHT_LOG_AUDIT_v1.json` 为 `PASS` 后，才允许执行无Plant preparation。当前文件不放行Plant。实际运行还必须有ROOT签名的 `ROOT_SCREEN12_REMAINING_RELEASE_v1.json` 及命令行SHA；缺失、字段不符或哈希不符均拒绝。

不训练、不读取TEST、不修改或重新生成模型，不修改C5/CM18引擎、C5基线、SCREEN12清单或任何历史run。模型固定为deployment JSON内的`selected_step=30000`及对应checkpoint。C5的cfg、位置算法、位置坐标掩码`[1;1;0]`、原始场景、Plant和安全约束保持原身份；每个新snapshot仅保留首航已审的CM18 opts差异与本场first-step marker路径。

## 固定场景范围

输入只能是 `reports/attitude_cm18_a1_20261024/CM18_A1_DEV_SCREEN12_v1.json`（SHA-256 `fdca3f17c0f39d19eb5b08e94e7e5b1f148ec03cf861eacec64d86ab7922f923`）。排除首航场景后，严格按清单顺序运行以下11场；每行的C5 raw路径与SHA由manifest固定：

|任务|类别|scene_id|
|---|---|---|
|T1|STATIC|`DL1018_DEV_T1_C00_W03`|
|T1|ALL_ARMS|`DL1018_DEV_T1_C15_W14`|
|T1|MULTI_ARM|`DL1018_DEV_T1_C05_W06`|
|T2|STATIC|`DL1018_DEV_T2_C00_W04`|
|T2|ACTIVE_NO_WIND|`DL1018_DEV_T2_C02_W15`|
|T2|ALL_ARMS|`DL1018_VAL_T2_C15_W09`|
|T2|MULTI_ARM|`DL1018_DEV_T2_C06_W07`|
|T3|STATIC|`DL1018_DEV_T3_C00_W05`|
|T3|ACTIVE_NO_WIND|`DL1018_DEV_T3_C03_W15`|
|T3|ALL_ARMS|`DL1018_DEV_T3_C15_W14`|
|T3|MULTI_ARM|`DL1018_DEV_T3_C05_W02`|

清单中虽然包含一个VAL场景，它仍按冻结SCREEN12原样运行；不得增删、换场或按结果重选。清单不含TEST场景。

## Preparation与ROOT release

`prepare_cm18_screen12_remaining_v1`先核SCREEN12 manifest、首航PASS audit及其原始首航raw SHA、首航no-Plant准备快照、C5快照、部署JSON、引擎和11份C5 baseline raw。之后每场保存独立MAT snapshot，并生成 `SCREEN12_REMAINING_PREPARATION_RESULT_v1.json`。它不调用闭环engine、episode wrapper或Plant；若任何输入不符或输出已存在，保留现场并终止。

ROOT release固定路径为本目录下 `ROOT_SCREEN12_REMAINING_RELEASE_v1.json`。ROOT应在首航audit PASS、检查完准备结果后另行创建此release。release至少具备以下严格字段和值：

- `schema=CM18_A1_SCREEN12_REMAINING_ROOT_RELEASE_V1`，`state=APPROVED_CM18_A1_SCREEN12_REMAINING_V1`，`decision=APPROVE_SCREEN12_REMAINING_11`，`plant_authorized=true`，`max_new_flights=11`。
- `first_flight_audit_status=PASS`；精确绑定 `screen12_manifest_sha256`、`first_flight_audit_sha256`、`preparation_result_sha256`、`prepare_script_sha256`、`runner_sha256`、`engine_sha256`、`forward_sha256`、`prediction_helper_sha256`、`deployment_parameters_sha256`、`c5_snapshot_sha256` 与 `c5_active_source_inventory_sha256`。
- `allowed_scene_ids` 必须严格等于上表11个scene ID及顺序。
- `scene_bindings`必须恰好11行并保持该顺序，每行`scene_id`、`baseline_C5_raw_sha256`、`prepared_snapshot_sha256`须逐项等于准备结果。release文件本身还通过启动命令提供的SHA-256固定。

无完整release时，runner必须在写入任何ledger或attempt文件前拒绝。首航单场release不授权此批次；不能把“SCREEN12未来额度”当成ROOT release。

## 单场启动与停止规则

runner入口 `run_cm18_screen12_remaining_v1(sceneId,rootReleasePath,expectedReleaseSha256)` 每次只启动指定的一场。ROOT从命令行串行启动，每次等待上一场进程终止后再考虑下一场；本入口不循环发起多场。该场已有attempt目录、ledger已有该场START、或当前ledger包含失败/不完整START时均拒绝，不覆盖、不重试。每个`RUN_STARTED`必须对应同场唯一的`RUN_TERMINAL`；终态失败或缺终态将阻止后续场启动。任何场失败时ROOT停止整批并保留全部证据。

输出位于 `experiments/attitude_cm18_a1_20261024/screen12_remaining_v1/runs/<scene_id>/attempt_01/`，包含真实run_start、first-step marker、raw MAT、run_status；同目录树的`SCREEN12_REMAINING_LEDGER.jsonl`按行追加START和终态，保留11场顺序与身份。每场最大输出100 MiB。只有`STABLE`、无安全停止、20,000 transitions、20,001 state samples、1,999 CM18 events、全部状态/参考有限且first-step marker存在时，状态才记为`RUN_COMPLETE_PENDING_ROOT_AUDIT`；这仍不是独立事件审计结论。

每场必须在独立MATLAB进程中单独启动，禁止并发。ROOT可以用PowerShell外层串行循环；每场必须等MATLAB退出、OS状态为0且run_status完整后才启动下一场，任何失败立即停止。实际路径由ROOT当前MATLAB安装提供：

```powershell
$matlabExe='C:\Program Files\MATLAB\R2025b\bin\matlab.exe'
$entry='C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\attitude_cm18_a1_20261024\screen12_remaining_v1'
$sceneId='DL1018_DEV_T1_C00_W03'
$release='C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\reports\attitude_cm18_a1_20261024\screen12_remaining_v1\ROOT_SCREEN12_REMAINING_RELEASE_v1.json'
$releaseSha256='<ROOT release实际SHA-256>'
$batch="addpath('$entry','-begin'); r=run_cm18_screen12_remaining_v1('$sceneId','$release','$releaseSha256'); disp(r.status);"
& $matlabExe -batch $batch
```

当前是任务书草稿和源码准备：不得照此模板启动Plant，直到首航event audit PASS且ROOT生成/审核新release。
