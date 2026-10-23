# C4 坐标干预独立源码审查

**审查结论：科学核心静态审查通过；工程准备与发布仍有未满足条件，当前不构成 Plant 放行。** 本审查按任务书冻结的整体坐标因子 m 检查源码及现存无 Plant 合成证据；没有启动 MATLAB，也没有修改实验实现。逐项文件身份见同目录 SOURCE_IDS.json。

## 科学核心

C4 隔离 core run_dl1018_closed_loop.m 相对冻结 C3 core 的差异集中于 position_coordinate_m 契约、tracking 坐标、预测参考积分/目标和相应日志。C4 要求延迟预测时显式提供二值 m（C4 core:23–32）。事件计算在先前 PCF 计算开启时形成 s - m*eta_before，再应用原轴限幅（2006–2017）；所以固定 m=0 时 tracking 面为 s，m=1 时沿用 s-eta_before。

目标分支要求上一事件恰为 j=n-10，且 j>=320（2020–2026）。m=1 直接以实际 a_f 累计值及其上一事件值形成目标，m=0 直接以 a_req 累计值及其上一事件值形成目标（2027–2046）。首个 n=320 事件没有虚构历史输入；后续目标在调用 helper 前形成，并配前事件 phi_j。积分只在本步输出和控制计算后累加已完成的 1 ms 转移（2261–2277），不会把当前事件之后的转移放进当前目标。日志分别保留实际 a_f 与 prediction-reference 积分、m、事件目标和坐标面（2869–2890）。

C4 与 C3 的 delayed_prediction_step_candidate.m 哈希相同；它先用 W_k 产生 raw/applied 输出，再以旧预测误差构成梯度，合并 tracking、leak、prediction 更新并做一次联合投影（helper:37–46）。C4 的 episode wrapper 也与 C3 哈希相同。静态差异没有显示输出 helper、特征、Plant、执行器或其他控制机制改变；未发现违反任务书时序/坐标语义的算法缺陷。

现存跨语言合成结果 C4_CROSSLANG_SYNTHETIC_RESULT_v2.json 为 PASS_SYNTHETIC_CROSSLANGUAGE_ONLY，最大绝对误差 2.2204460492503131e-16。Python fixture 从独立 Python reference kernel 生成；MATLAB checker v2 自己按 fixture 输入计算 m=0/1 的区间积分、目标，再调用冻结 MATLAB helper 与 Python 预期数组比较，并检查首事件无历史、当前行 sentinel 排除及输出先于更新。它确为跨语言核验，不是同一 Python 核自比。其明确局限是 checker 只验证合成公式和 helper、不调用闭环 core（checker:2）；闭环 core 的 m 接线由上述静态差异审查覆盖。v1 checker 因 MATLAB JSON events 为 cell 却按 struct 点索引而失败；v2 明确兼容 cell/struct 后通过。旧失败文件保留，不覆盖。

## 工程入口与证据

第一次入口修复把 shared input 的 model_mat 角色误按文件 basename 查找，导致 prepare/runner 找不到真实文件名。prepare v2 和 runner v2 改为精确匹配 items.role（prepare:59,134–136；runner:63,142），已修正该问题。lock builder v2 只版本化 lock/contract 与 prepare/runner 引用等元数据，不改变候选模型、场景清单、32 源运行库存或算法输入。C4 B_source 继续引用冻结 C3 的物理场景文件是正确的：它定义 Plant scene 输入，不应替换成新 B1 计分运行。

保留的历史 RUN_C4_CROSSLANG_NOPLANT_EXACT_v2.ps1 实际调用 prepare_c4_coordinate_v1，其 OS exit 1 记录不能当作新 v2 命令，也不应重跑或覆盖。checker v2 的合成 PASS 已单独留存。之后独立 prepare_c4_coordinate_v2 无 Plant 尝试也以 OS exit 1 结束，记录为 C4_PREPARE_MATLAB_OS_EXIT_v2.json，prepare_result_status=null 且 plant_authorized=false。该次失败的源码原因是 scene identity 模板字段不完整：prepare v2 第 81–82 行仅声明 scene_id/raw_scene_id/canonical_scene_id/alias_normalized_in_memory/B_raw_path/B_raw_sha256，第 98 行把 C3 snapshot 的完整 sceneIdentity(ix) 赋给该结构；C3 identity 另有 payload_review_sha256 字段，造成异构结构赋值失败。按主审转述，修复方案是在新的 v3 prepare 中以 repmat(c3Pack.sceneIdentity(1),1,12) 保留完整字段，再逐行赋值并保留身份断言。v3 尚待源码核对及实际无 Plant 结果，因此这是当前明确的工程阻断项，不是 C4 控制算法缺陷。

## 放行前条件

目前没有 C4_PREPARE_RESULT_v2.json、v2 snapshot 或 C4_RELEASE_v2.json；runner v2 的 release 校验只要求绑定 lock、contract、prepare、snapshot、runner、scene id 与 B_source 哈希（runner:18–25）。不能据此启动 Plant。后续 release/audit 还须显式绑定：

- 新 v3 prepare、精确 lock/contract/runner、完整 cfg/opts snapshot、实际无 Plant 结果与真实 OS exit；
- 本次 Python fixture generator、独立 Python kernel、fixture、MATLAB checker v2、合成 PASS 结果，以及对应无 Plant 命令/退出记录；
- 新 B1 的 raw_run.mat、run_status.json 与主审根审计身份。新 B1 是首场评分比较基线；它与 B_source 物理场景输入是不同角色，不能互换。已记录 B1 raw SHA 5a1fffedd408c070a77e3083643a33d9b422a55330ffecc1b6d1ab61b5d48957、status SHA 4de20ba0f17cb0cc498220032626f15b621c8d44dbaab2ea24d3457741a30175；主审报告 B1 独立复算与 33 组完整数组比较通过。

**结论边界：** 这是有条件的代码审查结论，不是准备通过或 Plant 授权。待 v3 最小修复通过源码核对、无 Plant prepare/snapshot/退出证据完整、release 绑定上述身份后，由主审另行决定是否放行首场。
