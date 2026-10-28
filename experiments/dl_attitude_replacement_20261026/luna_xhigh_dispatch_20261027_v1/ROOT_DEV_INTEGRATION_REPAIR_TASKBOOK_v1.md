# root 精确集成修复任务书（仅最终交付仍有此问题时执行）

2026-10-27。执行者仍必须 Luna/xhigh/default。主模型已读实际源码：当前复合头改动落在 generic `run_gate_holdout_closed_loop.m`，而六场真实对照的原执行函数是 `run_mlp15_dev72_closed_loop.m`。后者没有新增 tracking 输入。generic gate 的 GHP7 validator 曾在旧 DEV v1 因场景合同不符而失败，不能再次用于这六场 DEV/VAL。

本任务只解决真实调用路径及绑定；不改变任何方法参数，不加入新算法，不训练、不启动Plant、不读TEST。不要继续新建另一套generic场景适配框架。已有300事件数值结果和合法更新公式保留，只做必要的实际入口/配置证明。

## 唯一目标

1. 最终真实六场driver必须调用新树的 `run_mlp15_dev72_closed_loop`，源自已真实成功执行v1六场的同名函数。将已经实现并测试的 tracking_surface、tracking_euler_rate_map、actual_event_dt 传递和trace字段接到此DEV函数相同MLP事件块。恢复新树generic `run_gate_holdout_closed_loop.m` 与parent v1逐字节相同。控制源差分最终恰为 MLP step 与 DEV loop 两个文件；forward不变。
2. 不使用 `default_config()` 来替代真实锁定C5运行配置。采用既有 `prepare_mlp15_dev72_no_plant(record.payload_path)` 返回的 p.cfg/p.model，然后用同一builder绑定已固定的C5 full72 MLP模型并重建identity。其依赖的三个旧小型manifest/taskbook文件可从v1复制原字节到新study作只读依赖；不复制raw或模型。
3. 新 `LOCKED_CFG` 从上述真实p.cfg读取K1、J0、dmax、beta与command_filter；数值确认命令滤波角加速度是 `[Inf,Inf,6]`，不能悄悄恢复默认 `[8,8,6]`。同时按实际formal fixed路径构造Pfixed并确认 `Pfixed.inertia==J0`、`Pfixed.inertia_dot_for_bs==zeros(3)`、morphology_mode=fixed。记录cfg snapshot/位置模型/common_position_options来源身份。Inf需有文字标签，不能将JSON null误说为未知配置。
4. 提供可直接由root调用的唯一driver，例如 `run_composite_dev_attempt(sceneId)`。先检查root release状态、authorized_Plant_calls和authorized_scenes，0时硬拒绝，之后才允许创建attempt marker或进入Plant。实际DEV函数也须保留同一预算0硬拒绝；负向验证必须调用这个真实DEV入口而非generic入口。
5. 初始release保持 `PREPARED_ROOT_REVIEW_REQUIRED`、authorized_Plant_calls=0、authorized_scenes空。root审核后才修改release放行首场T1/W15。driver独立保存marker、run_start、raw、status和失败记录，拒绝覆盖同场输出；总潜在预算仍6，实际授权初始0。
6. manifest继续只绑定原六场以及B/C5/frozen/v1 prediction-only raw；实际p.scene的time、initial_state、reference、arms、environment_wind_I与全部配对raw完全一致。不要把GHP7 raw当DEV，不改任何物理数组/计分目标。
7. 实际raw审核器必须针对真实DEV输出，独立从current state、filtered reference/rate和锁定K1重建surface/T。保留输出先于更新、合并两个增量再投影、过去残差索引、SPD和禁用惯量重建检查。新增prediction_only比较必须有真实v1 raw绑定。

## root 已明确的设计语义

残差RLS保持上一和当前beta均为1才更新；新增tracking可以在当前beta=1且有上一事件时启动，因当前跟踪信号已知。故300事件fixture中的80次RLS/81次tracking可接受，必须在说明中明确，并在真实trace里验证两路时间。真实事件dt必须等于相邻head事件时间差，而非Plant dt。

无dmax饱和轴遮罩的tracking律只作受限离散系统实验，不声称饱和时仍精确抵消；不在这次修复中加入anti-windup或改增益。用户的双环B/C5最终标准不变。

## 保留与交付

当前已生成的preparation artifacts和NO_PLANT_CHECK_v1/v2先复制到独立 `preparation_attempt01/` 保留；不删除、不改历史工程。新source lock、diff、cfg绑定和检查采用明确新版本名并由新release引用，避免把旧入口检查冒充修复后的入口检查。

复用已有Python fixture数据，只因代码/入口变化重跑必要MATLAB核验（300事件仍便宜），补充实际DEV预算0拒绝、真实C5 cfg绑定及which路径检查。不要重复训练，不重新计算所有不变baseline指标。保存准确首场命令、source SHA、检查结果及修复完成说明。执行者本次Plant预算仍0，由root作最终首场决定。
