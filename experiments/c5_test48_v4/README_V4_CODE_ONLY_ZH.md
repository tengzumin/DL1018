# TEST48 v4 执行入口（CODEONLY）

当前目录是 `TEST_UNSTARTED_DEPENDENCY_REPAIR_TASKBOOK_v2_ZH.md` 的隔离实现候选。只有根审核并分别提供对应 release 后，才允许调用下列阶段；本实现当前未启动 MATLAB、Plant 或训练。

| 模式 | 根 release | Plant 上限 | TEST 输入访问 | 输出 |
|---|---|---:|---|---|
| `PREPARE_NO_PLANT` | `PREPARE_NO_PLANT_PARENT_RELEASE_v1.json` | 0 | 读取 v3 已冻结包 | 六方法 cfg/opts、源/which 与 PCF helper 预检；自然 OS 回执 |
| `ENGINEERING_DEV2` | `ENGINEERING_DEV2_PARENT_RELEASE_v1.json` | 2 | 否，仅固定 VAL 场景 | DSSM、KAN 各一场独立工程复现；每场完整 raw 与身份回执 |
| `RUN_UNSTARTED_TEST_PARENT_APPROVED` | `RUN_UNSTARTED_TEST_PARENT_RELEASE_v1.json` | 240 | 是，复用 v3 冻结包 | 五种未进入 Plant 的方法各 48 场，顺序启动五个独立 MATLAB 进程 |

只从 PowerShell 7 启动器进入，不创建或推导任何 release：

```powershell
& './experiments/c5_test48_v4/RUN_TEST48_EXACT_v1.ps1' -Mode PREPARE_NO_PLANT
& './experiments/c5_test48_v4/RUN_TEST48_EXACT_v1.ps1' -Mode ENGINEERING_DEV2
& './experiments/c5_test48_v4/RUN_TEST48_EXACT_v1.ps1' -Mode RUN_UNSTARTED_TEST_PARENT_APPROVED
```

每次执行都先核 taskbook、code-only release、依赖审查、v3/v4 manifest、方法源/模型、平台引用、冻结 TEST 文件和截止时间；并复核 v3 B48 的 OS0 与 DSSM 的 OS1/零 Plant 失败凭据，逐个检查其余五方法的 48 个 v3 first-Plant marker 均不存在；之后核当前阶段 release、旧输出/活 MATLAB 进程、磁盘/产物/时间预算。任何旧输出、OS 非零、方法回执不通过或预算不足都停止并保留现状，不自动重试。运行阶段复用原 `experiments/c5_test48_v3/input/` 的共享 48 场景、六方法 cfg/opts 与 index 原字节；不调用 GET，不重新生成场景，不重跑 B。

v3 的 DSSM pre-Plant 失败目录和回执保持原位。B48 通过 v3 的 batch/body SHA 固定为已完成记录复用；v4 新 Plant 只可能落在 `experiments/c5_test48_v4/`。运行顺序固定为 DSSM、KAN、C5_M110、C5_FREEZE_TRAINED_W0、C5_NO_DELAYED_PREDICTION；所有训练、优化器更新、参数搜索均为 0。

DEV2 参考使用 v3 manifest 指定 cfg/opts snapshot 旁的完整旧 raw，均为 `DL1018_VAL_T1_C00_W07`。peer r001/r002 存档是不同 run_start/raw 字节身份，单独列在 manifest，不替代该基准。计时差异单独列示；完整 raw 数值比较仅排除 `controller_call_time_s`、`network_call_time_s`、`stage1_position_inference_time_s` 与 `stage1_position_event_inference_time_s` 四个计时字段，状态、控制、权重、事件时间与其他字段仍逐层比较。

硬截止、总新增 80e9 bytes 与预留后 30e9 bytes 下限继承 v2；预算计入旧 v3 输出和报告以及 v4 新增物。当前入口/启动器/contract/manifest 是待根审核的 CODEONLY 候选，未有任一阶段授权文件。