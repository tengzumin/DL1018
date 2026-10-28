# mlp15_composite_head_v1 独立集成审核（快照）

审核日期：2026-10-27。只读核对 v1 交付文档、source diff、MATLAB 源码及 release JSON；未启动 MATLAB、Plant、训练或测试，也未重建惯量。结论针对目录现有快照，不代表 DEV72 实际闭环通过。

## 结论

- **复合头未接入实际 DEV72 闭环入口。** v1 已实现并做无 Plant 核验的组合是 MLP step + generic `run_gate_holdout_closed_loop`。实际 DEV72 MLP 调用仍没有传入新 step 所需的 tracking 输入；按当前代码会在第一次 `head_enabled=true` 的 step 调用处触发 `DLMLP:HeadTime`。
- **release 配置没有锁定真实 C5 的角加速度限幅。** v1 的 `LOCKED_CFG` 由 `default_config()` 生成，默认是 `[8,8,6]`；ROOT 任务书记录真实 C5 配置为 `[Inf,Inf,6]`。虽然 DEV72 的独立准备函数会读取 C5 snapshot 的 `cfg`，当前复合头 release/完成记录未证明它绑定了该准备结果。
- **未发现固定控制路径中的变量惯量泄漏。** 由已有 options builder 传入 `formal_rbf_baseline=true` 时，DEV72 loop 以固定名义 arm 构造并反复使用同一 `fixedController`；真实变形只进入单独的 `Ptrue`。固定分支将 arm rates 置零，`inertia_dot_for_bs` 由零速率质量属性路径产生。当前 LOCKED_CFG/检查没有直接断言并记录 `Pfixed.inertia==J0`、`Pfixed.inertia_dot_for_bs==zeros(3)` 和 fixed mode 的数值结果，故这仍是源码路径核对，不是运行时配置证明。
- **航次仍为 0，状态符合待审核要求。** `RELEASE.json` 是 `PREPARED_ROOT_REVIEW_REQUIRED`，`authorized_Plant_calls=0`、`Plant_calls=0`、`authorized_scenes=[]`；没有 composite 闭环结果。

## 发现与证据

### [阻断] 实际 DEV72 事件块没有传 tracking 输入

- `SOURCE_DIFF.json:5-15` 将控制源码改动列为 `mlp15_attitude_step_v1.m` 与 generic `run_gate_holdout_closed_loop.m`，没有 `run_mlp15_dev72_closed_loop.m`。
- 新 step 在 `mlp15_attitude_step_v1.m:64-73` 的 `head_enabled` 路径要求 `sample_index`、`time_s`、`tracking_surface`、`tracking_euler_rate_map`、`actual_event_dt`。
- generic gate 在 `run_gate_holdout_closed_loop.m:2438-2454` 生成并传递了这些字段；而 DEV72 loop 的 `run_mlp15_dev72_closed_loop.m:2424-2436` 只传 `feature/J0/beta/dmax/head_enabled/sample_index/time_s` 和残差历史，没有后三个 tracking 字段。该 step 因此会在 `mlp15_attitude_step_v1.m:65-73` 拒绝输入。
- v1 的实际 generic dispatch 是 `run_mlp15_candidate_gate_attempt.m:37,131`，调用 `prepare_gate_candidate_no_plant` 和 `run_gate_holdout_closed_loop`；准备器在 `prepare_gate_candidate_no_plant.m:9-18` 明确绑定六场 ACTIVE GHP7 payload。完成记录也只描述 generic event entry (`LUNA_COMPLETION.md:10-17`)。真实 DEV72 dispatch 文件 `run_mlp15_dev72_attempt.m:26,77` 虽然仍存在，但它读取独立的 `MLP15_DEV72_RELEASE_v1.json` (`:4-10`)，没有由当前复合 release 接到这条路径。
- **最小修复：** 将新字段、实际相邻 MLP 事件间隔及 trace 写入 DEV72 loop 的同一 MLP 事件块；首事件 dt 为 0，后续使用当前事件时间减前一 head 事件时间。让新的唯一 driver 使用真实 DEV72 payload/identity 并调用 `run_mlp15_dev72_closed_loop`；source diff 保留 step + DEV loop 两个控制文件，generic gate 恢复 parent v1。沿用当前 0 航次 release guard，不在修复中启动 Plant。

### [高] LOCKED_CFG 从默认配置生成，不能代表真实 C5 cfg

- `audits/prepare_composite_release_no_plant.m:21-36` 从 `bind_paired_fixed_j0(default_config())` 生成 `LOCKED_CFG.json`；而候选树 `core/default_config.m:66-67` 将 `command_filter.acceleration_limit` 设为 `[8;8;6]`。
- ROOT 任务书 `ROOT_DEV_INTEGRATION_REPAIR_TASKBOOK_v1.md:10-11` 明确要求以真实 `prepare_mlp15_dev72_no_plant(record.payload_path)` 返回的 `p.cfg/p.model` 建锁，并确认真实值 `[Inf,Inf,6]`。现有 `LOCKED_CFG.json` 记录 default config SHA 与 J0/dmax/beta，但没有 `command_filter`/C5 snapshot 身份；`RELEASE.json:27-53` 的嵌入锁定字段也不含命令滤波限幅。
- `prepare_mlp15_dev72_no_plant.m:76-84` 本身确实从 receipt 指定的 C5 snapshot 读取 `cfg` 并据此准备模型；`prepare_gate_candidate_no_plant.m:77-83` 也使用 snapshot cfg，但它对应 GHP7 generic 分支。因此，不能把这些代码存在等同为当前 release 已把真实 DEV72 cfg 锁进来。
- **最小修复：** 以 DEV72 no-Plant preparer 的返回 `p.cfg/p.model` 生成 LOCKED_CFG；保存 C5 snapshot、位置模型和 common position options 的身份，并断言/记录命令滤波限幅。JSON 中将 Inf 作为明文标签（例如 `"acceleration_limit_rad_s2":["Inf","Inf",6]`），不要以 `null` 表示。之后再校验 Pfixed 的 J0、Jdot 和 fixed mode。

### [通过但缺少显式锁定值] fixed J0 路径静态隔离了 Plant 真实惯量

- C5 options 路径为 `make_paired_c5_options.m:3` → `position_only_search_options.m:6` → `controller_options_dl1018.m:7-14`；其中 `formal_rbf_baseline=true`。
- `run_mlp15_dev72_closed_loop.m:151-169` 用固定 mode 建立 `fixedController` 并验证冻结 J0 身份；循环 `:1128-1137` 将 `Ptrue` 单独构造，正式模式下控制对象为 `P=fixedController`，不从 `rho_true/rhoDot_true` 重建 BS 惯量。
- `controller_parameters.m:35-55,70-76` 在 fixed mode 使用名义 arm lengths 和零 arm rates，再将质量属性导数写入 `P.inertia_dot_for_bs`；`arm_mass_properties.m:10-14` 将该零速率输入传到统一质量属性函数。这个路径没有变量惯量信号进入控制器的源码机制。
- **最小补强：** release prep / DEV no-Plant 检查直接断言并输出 `Pfixed.morphology_mode=='fixed'`、`Pfixed.inertia==J0`、`Pfixed.inertia_dot_for_bs==zeros(3)`，且由当前真实 C5 cfg 构造；将这些数值与 cfg snapshot SHA 写入新的锁定记录。不要改成从真实 arms 重建 J/Jdot。

### [状态核对] release 未放行

- `RELEASE.json:3-7` 与 `RELEASE_RECORD.json:4-8` 均显示授权航次和已用航次为 0；`LUNA_COMPLETION.md:6-8,40-42` 说明尚未运行 composite、DEV72 或 B/C5，且只待 root review。
- 保持 `PREPARED_ROOT_REVIEW_REQUIRED` 及空授权场景；完成实际 DEV72 source/which/配置核验前，不应将 v1 generic gate 的合成检查视为真实闭环放行依据。

## 审核范围说明

本报告是 v1 的**独立快照审核**。`LUNA_COMPLETION.md` 宣称 v1 的无 Plant step 核验完成，但它同时说明被修改的闭环入口是 generic gate，并未声称完成 DEV72 实际闭环集成。没有运行项目 MATLAB/Python 源码或 Plant 来复现上述静态接口错误。

