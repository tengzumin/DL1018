# TEST48 raw审核与评分wrapper

该目录提供未来TEST48结果的只读raw审核入口。审核通过后只生成一个JSON，供冻结的`test_statistics_v1`统计脚本读取。当前只完成代码与纯函数检查：未运行CLI、未打开TEST场景/MAT/轨迹结果，也未启动MATLAB、Plant或训练。

## 输入绑定

脚本固定六方法顺序：`B_TRACEABLE`、`CORRECTED_DSSM14_G12_R32`、`CORRECTED_KAN14_G12_R32`、`C5_M110`、`C5_FREEZE_TRAINED_W0`、`C5_NO_DELAYED_PREDICTION`。它逐项绑定冻结source manifest、父release、输入index、cfg/opts包及entry/launcher/helper SHA；根已完成的TEST输入身份与MATLAB roundtrip结论也以文件SHA `98a93686a1bdd00b64031fa5c1518fd63b62847cfad2e31019b27845e2eb8da1`绑定。scene ID来自冻结JSON index，并逐飞行对照`run_start.meta.scene_id`字符字段；脚本不尝试把共享MAT中MATLAB `string`类的opaque值解码为文本。

任何raw评分或MAT轨迹读取前，脚本先验证六份自然MATLAB OS0回执、`-singleCompThread`参数、固定顺序和不重叠时间区间。随后检查每种方法的batch/body/48条记录、文件身份SHA、输入与模型快照、物理场景跨方法一致性、20,000步执行器全有限完整性及安全/完成状态。DSSM/KAN各48场逐值核对raw `log.stage1_position_weight_initial`与冻结33×3 W0；C5和两项匹配消融分别使用已锁定事件审计函数，对144个飞行逐场复算1968个事件；B、DSSM和KAN不套用C5事件公式。

## 输出与统计字段

全部检查通过才会写出顶层`status=PASS_TEST48_RAW_IDENTITIES_PHYSICS_ALL_METHODS`、`TEST_accessed=true`和288条唯一`(scene_id, method)`评分行；遇到缺文件、SHA/身份不符、未知schema、非有限值或审计失败时，不写PASS文件。每行沿用原始`parent_raw_metrics.score()`的Q、三阶段XYZ RMSE、峰值、p95和饱和/裁剪值，并展平冻结统计合同要求的20个controller计时字段。计时保留全部20,000次调用，按`transition_time >= 0.320 s`与此前调用分别给出mean/p50/p95/p99/max及严格大于1 ms比例。

native遥测独立于controller计时汇总：原始`stage1_position_event_inference_valid`只作为事件标记报告，不称为连续ready；若同时存在`stage1_position_inference_time_s`，按valid事件和transition_time汇总实际事件调用计时。`learned_forward_debug`/`forward_debug`只有严格匹配`enabled=false,count=0`时才作为disabled记录；启用时只读取`history_ready`、`model_call`、`time`和`network_call_time_s`小数组，不把逐点遥测展开到输出。B没有native head且事件valid全false时明确标记`native_not_applicable`，不会合成一个head。

输出JSON保留逐行raw路径/SHA及输入身份SHA、来源文件、六个方法过程回执、source/model引用、执行器审计、DSSM/KAN初始化W0核对、C5三组事件审计和计时边界说明。`-singleCompThread`限制MATLAB数值计算线程设置，实际worker线程仍可能存在，根observer另行记录；测试避开已知重负载但不提供OS级隔离，controller调用计时也不构成完整1 kHz闭环证明。脚本不自动作论文/性能门或goal判断。若未来审核失败，应先按根审意见定位schema/身份原因；此wrapper不会重跑Plant。

## 纯函数自检

`self_check()`只使用4个内存计时值和两行`SYNTHETIC_A/B`列式struct样例，检查ready边界、1 ms严格比较及MATLAB Nx1列解包/嵌套路径cell保留。样例不是TEST输入，也不生成TEST形状行。

正式结果具备后由根按授权单次调用，例如：

```powershell
python reports/paper_continuation_20261023/test_raw_review_v1/audit_test48_raw_v1.py `
  --output-json reports/paper_continuation_20261023/test_raw_review_v1/TEST48_RAW_PARENT_AUDIT_v1.json
```

输出路径只能位于本目录；若文件已存在，脚本拒绝覆盖。当前没有审核结果JSON，因为本次任务禁止运行CLI或读取TEST结果。
