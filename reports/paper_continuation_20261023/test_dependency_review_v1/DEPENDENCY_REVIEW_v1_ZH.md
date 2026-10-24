# TEST 依赖身份独立复核：DSSM/KAN PCF 路径

**结论：可通过补齐一项活动依赖并显式锁定解析路径来修复入口；现有 TEST 入口的来源预检并未闭合该依赖。** 对当前冻结 DSSM/KAN 选项，`position_filter_realization_pcf_step_v3_5.m` 是活动调用；`position_stage1_update_head_pcf_v3_5.m` 不在活动分支，不应仅凭 grep 追加。

`experiments/c5_test48_v3/test48_entry_v1.m:598–628` 的 `bind_method_path` 只将方法 `source_refs` 加入 MATLAB 路径，并只对这些引用检查 `which`。DSSM/KAN 各 12 项引用均没有 filter helper；其冻结 `runtime_tree` 是旧归档 `sources/local_runtime`（SHA-256 `5a4a1043…9745db0`），也不含该 helper。入口因此没有在进场前验证此必需函数。旧 core 的 `run_dl1018_closed_loop.m:2152–2158` 在 PCF coordination 启用时逐控制步直调该函数；当前文件身份为 `matlab/models/position_filter_realization_pcf_step_v3_5.m`，SHA-256 `b4ae22db…660228d0`。B 与 C5 refs 已绑定此 SHA，DSSM/KAN refs 未绑定。

旧 DEV KAN `r001` 和 DSSM `r002` 的 `run_start.mat`（分别 SHA-256 `0012bf34…26c9525`、`3b798c86…85743e`）均记录 `stage1_position_runtime.enabled=true`、`update_enabled=true`、`position_only_search_head.enabled=true`、`head_type=FEATURE`、`gamma=12`、`kappa=1` 和 PCF coordination enabled。故 ready 后进入 `if stage1SearchEnabled && stage1PositionUpdateEnabled`（旧 core L1952），使用已锁的 `position_only_search_head_step.m`；PCF surface/eta 在 L1953–1963 内联修正。`position_stage1_update_head_pcf_v3_5.m`（SHA-256 `a89e8f97…df91394a`）位于其后的 `elseif stage1PositionUpdateEnabled`（L1988–1994），对这两组固定选项不可达。若今后改变 search/update 选项，必须重新闭合新分支中的 helper 与底层 head 更新器。

旧 DEV 启动器 `scripts/run_corrected_pair_eval_stage.m:424–437` 会恢复默认路径并调用项目 `init_dl1018`；`matlab/runtime/init_dl1018.m:4–11` 再加入 `matlab/models`，所以旧运行环境具备解析当前 helper 的路径条件。但旧 raw 只保存归档 runtime tree 与 init 身份，没有 helper 的实际 `which` 路径或 helper SHA。只读重算同一首个 VAL 场景 `DL1018_VAL_T1_C00_W07` 的两个旧 raw：DSSM/KAN 的 20,000 步记录均满足 `r_f=a_req-a_f` 与 `eta_next=exp(-k2*dt)eta + (1-exp(-k2*dt))/k2*r_f`，最大绝对残差均为 0；这支持旧执行与当前 helper 的数值递推一致，但不能证明旧 MATLAB 实际解析的文件 SHA。

建议把上述 filter helper 以精确路径/SHA 加入 DSSM/KAN 的方法身份，且任何 Plant 调用前要求 `which('position_filter_realization_pcf_step_v3_5')` 与冻结路径完全相同并验证文件 SHA；同时断言上述冻结 opts 分支条件。对当前分支不追加 `position_stage1_update_head_pcf_v3_5`。两次工程复现可分别使用已审的 KAN `r001`、DSSM `r002` 和同一 VAL 首场景，保持原模型、scene、cfg/opts、W0、核心代码不变，将输出放入新目录并保留原 raw；比较全长状态/控制、初末权重和独立 Q。它们验证修复后的工程复现，不是新增候选或 TEST 证据。

v3 DSSM 失败记录应原样保留：已知失败发生在 Plant 调用前，0 Plant、0 raw，不构成轨迹分数；但 v3 有 OS1/NoRetry 记录。修复后必须由根以新冻结身份/独立 release 决定是否可作为第一次有效的轨迹级 TEST 执行，不能覆盖或改写 v3 失败，也不能称 v3 六方法已完成。DSSM/KAN 的逐方法 refs 还未列出所有公共 `matlab/core` 调用；若清单把 B refs 作为全局公共平台身份，release 应明确这种共享绑定，否则须先证明公共来源也被跨方法锁定。

本复核只读旧 DEV raw、源代码、静态 manifest 与失败诊断；未运行 MATLAB/Plant/训练，未读取 TEST 输入、TEST raw 或任何 TEST 成绩，没有修改代码或冻结记录。
