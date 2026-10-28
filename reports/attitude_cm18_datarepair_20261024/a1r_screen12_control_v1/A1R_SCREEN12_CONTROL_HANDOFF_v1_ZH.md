# A1R SCREEN12 控制组源码交接

状态：源码准备完成，等待 Root 源码审核与无 Plant 准备；当前未创建 MATLAB 快照、未启动 Plant/engine/训练，也没有单场 release。

新增文件及 SHA-256：

| 文件 | SHA-256 | 检查 |
|---|---|---|
| `experiments/attitude_cm18_datarepair_20261024/a1r_screen12_control_v1/build_a1r_forward_fixture_v1.py` | `ACD799ABB22F0A6D66D0E83F96744786946D986B22EFEA67CD4007E2E7B54E44` | `python -m py_compile` exit 0；按固定 B/C5 各 5 行计算非零 basis，总计 2 |
| `experiments/attitude_cm18_datarepair_20261024/a1r_screen12_control_v1/prepare_a1r_screen12_control_v1.m` | `D2BC32405B92DB708DEC808CCEBBD5BEEBDB4BE9B0552F1EE6409FD66DC41C12` | 源码静态检查；不调用 engine/Plant |
| `experiments/attitude_cm18_datarepair_20261024/a1r_screen12_control_v1/run_a1r_screen12_control_v1.m` | `FC99C4F1820B197C44B71D6FE9505D9EADFE2D467446B334C7DFC19BFA3D2628` | 源码静态检查；只允许一个 release 绑定场景和一次 `attempt_01` |

固定前向 fixture SHA 为 `04F79F473232341E5495EE77D19AF09650E56976881B9CCCF24901E7C1FAE7F5`。Root 已实际完成 MATLAB R2025b 的 11 例 parity，receipt `reports/attitude_cm18_datarepair_20261024/ROOT_A1R_ACTUAL_MATLAB_PARITY_v1.json` SHA `32D7313954F415182166D3B8060EC8CD3F632E08C8139D48AC6439C6E5E92D55`：PASS，真实非零 basis 两例，最大物理输出误差 `1.7763568394002505e-15`，0 Plant、0 engine、0 optimizer、未访问 TEST。准备器只核验该独立 receipt 与 fixture，不重复 parity。

准备器实际命令（Root 确认当前没有冲突 MATLAB 进程后执行；仅读锁定的 C5 raw、写 A1R 快照和 no-Plant preparation result）：

```powershell
& 'C:\Program Files\MATLAB\R2025b\bin\matlab.exe' -batch "cd('C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018'); addpath('C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\attitude_cm18_datarepair_20261024\a1r_screen12_control_v1'); prepare_a1r_screen12_control_v1();"
```

在同一 MATLAB 调用前可先静态检查两个入口；检查本身不调用 engine：

```matlab
checkcode('C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\attitude_cm18_datarepair_20261024\a1r_screen12_control_v1\prepare_a1r_screen12_control_v1.m','-id');
checkcode('C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\attitude_cm18_datarepair_20261024\a1r_screen12_control_v1\run_a1r_screen12_control_v1.m','-id');
```

Runner 不会因本交接自动获得放行。Root 每场单独创建 `reports/attitude_cm18_datarepair_20261024/a1r_screen12_control_v1/ROOT_A1R_SCREEN12_CONTROL_RELEASE_<sceneId>_v1.json`，schema 为 `A1R_SCREEN12_CONTROL_ROOT_RELEASE_V1`，decision 为 `APPROVE_ONE_A1R_SCREEN12_FLIGHT`。必需字段：`plant_authorized=true`、`training_authorized=false`、`optimizer_steps_authorized=0`、`TEST_accessed=false`、精确 `scene_id` 与 `sequence_index`，以及 `taskbook_sha256`、`approval_sha256`、`preparation_result_sha256`、`screen12_manifest_sha256`、`c5_snapshot_sha256`、`c5_active_source_inventory_sha256`、`deployment_parameters_sha256`、`checkpoint_sha256`、`selected_step`、`normalizer_float64_sha256`、`forward_fixture_sha256`、`matlab_parity_receipt_sha256`、`engine_sha256`、`forward_sha256`、`prediction_helper_sha256`、`prepare_script_sha256`、`runner_sha256`、`baseline_C5_raw_sha256`、`prepared_snapshot_sha256`。`prior_audit_sha256` 是此前场景独立 PASS 审计 SHA 的顺序数组；首航为空，后续每场必须包含此前所有场景。

12 场顺序由代码固定，首先 `DL1018_DEV_T1_C01_W15`，然后按冻结 SCREEN12 清单顺序完成其余 11 场。后续场景还需此前每场的 `RUN_COMPLETE_PENDING_ROOT_AUDIT` 状态和逐事件独立审计 `PASS`，否则停止。输出总预算为 `1,610,612,736` 字节；runner 遇到已存在 attempt、release 或锁身份不符时拒绝运行，不自动重试，也只移除内容仍匹配本次 token 的自有锁。
