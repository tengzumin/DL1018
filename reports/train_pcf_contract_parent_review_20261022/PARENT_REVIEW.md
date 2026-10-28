# 主审检查点：TRAIN PCF 目标重建

2026-10-22。用户已授权继续上一报告的离线任务，并明确执行者使用 Luna max；本次两位执行者的派遣参数均为 gpt-6-luna / max。工具不提供速度选项，不独立宣称模型后端/速度已核验。

## 执行边界

实施目录：reports/train_pcf_contract_reconstruction_20261022/。
本主审目录只保存独立核验及审核决定；不并发修改实施者文件。0训练、0optimizer、0Plant、0GPU、0TEST；不删除/移动历史数据，不改控制器，不停实验，不提交Git。原三轮研发预算没有重开。

## 冻结输入与分层复核

原训练索引 SHA256：257089f1dc455b7bc97bf1c772be31d1d8ae83079e7ec41f591d96e31fed39ca。
G3来源索引 SHA256：3c8291c12628acfb9d950fb67cb84b56fe09cdaeaeac38706e8903291873e84e。
分层名单 SHA256：4019aac3a23f1aef4a70f5d37b364d1ca09bfd1bcfe9ce39e486b3772af18b49。

主审从原索引独立求 task×role×wind-band 分组的最小run_id，与实施者18条名单逐项相等。每任务/角色的三类候选数为144/96/16，合计18组；没有挑选新输场或变换样本。

## 已独立实际读取的三条 TRAIN 样本

固定为 FIG8_3D/B/W00-W08、HELIX/POS_OFF/W09-W14、SQUARE/B/W15，每条1999事件。见 verify_three_records.py、three_records_checks.csv、three_records_metadata.json。

- 原始状态、参考、真实实现推力/气动力，配合来源runStart.cfg重建a0、a_req及实际加速度；质量/重力/BS增益不取当前default_config。
- 名义加速度及a_req=a0−u误差≤5.6e-16 m/s²。
- 物理Y对事件H5误差≤2.6e-15 m/s²；独立X14对事件H5误差≤1.8e-15。
- event时间与一基Plant索引完全匹配；H5到NPZ的Y/X14 float32舍入逐元素相等。
- 混合目标闭合≤1.2e-16；M=diag(1,1,0)时正确关系是：
  Y+M r_f = a_actual − [(I−M)a_req+M a_f]。
  只有XY等于a_actual−a_f，Z保持原Y。
- 这三条Teacher的stage1 r_f字段全为NaN占位，不能当作零残差。独立重建r_f RMS分别为.05016/.04575/.03193 m/s²。
- raw/run_start/H5/cache的SHA与来源索引一致，读取前后SHA/stat不变。
- 进一步确认runStart.opts中的physical impulse/diagnostic injection/state perturbation均缺省false；原始日志的impulse enabled/force及state perturbation字段为false或0，无未计外力证据。cache Plant索引0基、H5事件/Plant索引1基、clip y及phase_code也补查通过。
- 首次主审核验因误假设event H5为component-major在形状运算处停止；显式适配event-major/component-major后通过。无原数据修改、无实验调用。

这证明三条记录上的数值重建与原导出契约一致，不证明目标变换闭环收益。

## 数学与时间语义审核

独立审核者确认理想连续sc=s−M eta的匹配项为Y+M r_f，M与K2须可交换。它是候选监督目标，不是唯一正确训练目标，更不是完整离散闭环稳定性/最优性证明。

重建r_f用请求推力requested_generalized(:,1)和本步filtered_attitude_reference；不能替换为裁剪后或实现推力，不用下一拍filter状态。实际Y使用真实实现wrench。B/POS_OFF的影子标签仍受其自身策略和滤波历史影响，不能当成候选PCF-on的独立扰动分布。

X14未显式含filter状态，可能存在表示/信息不足；即使代数闭合，也不能自动宣称新目标可由X14辨识。

## 训练目标源代码的独立旁证

检查冻结归档的corrected_pair_training/scripts/teacher_data.py和fit_models.py：
均匀打乱端点，单次层次样本权重，loss为mean_axis SmoothL1(pred/3,target_clip/3)。
没有看到权重在sampler和loss重复应用的证据。没有逐风组/逐轴目标幅度归一。幅度不同自然导致loss贡献不同，这不是已证实实现bug。本阶段不据此改权重或拟合模型。

## 当前审核状态

18条实施结果已完成主审算术核验：18组各一条、1999事件、全PASS；与主审3条独立结果交叉一致。名义a0和a_req闭合最大5.6e-16，物理Y对H5最大2.66e-15，X14最大3.56e-15，混合目标恒等式2.23e-16，时间差0。run_start格式6条v7.3、12条MAT5，全部PCF禁用。该分层规则字典序首条均落C00，不能声称代表了所有形变阶段；全量仍逐条执行检查。

早期18条估时尚未包含固定模型推理及全量checkpoint开销，不作为最终耗时记录。之后已在全量worker中补齐额外外力/扰动硬拒绝和cache role/task/scene身份检查，并通过源码审核及冻结版本smoke。

## 首次全量执行放行

主审和独立审核者均通过首次正常执行路径。冻结core d2e2c807b811、worker 5ca776c5f476；准确SHA及边界见 TRAIN_EXECUTION_APPROVAL.json。TRAIN于2026-10-22 20:17:25+08:00正式启动，PID 75380；同版本VAL96须待TRAIN成功并经主审完整性核对后才执行。没有授权resume路径或修改冻结脚本。

父审独立读取最终smoke侧车，验证混合目标、Z保持、beta及输出clip，并用double原目标再clip重算16行worker指标，最大误差1.12e-16。侧车clipped字段保存float32，若用其要求double的1e-12逐位一致是不恰当比较；后处理从double raw计算clipped指标。主审曾重复调用已有smoke，触发拒绝覆盖保护，没有改变源文件或既有侧车；FAILURES.csv追加该事实，release里的失败账本SHA仍是冻结时快照。

新增独立训练目标尺度审计：audit_zero_predictor_loss_scale.py只读1536个TRAIN缓存并保护hash/stat，按原层次权重和32事件窗口、stride5重算605184个训练端点。W15样本权重总质量6.25%，零预测器下的SmoothL1目标贡献仅0.5842%。这不是训练后loss、梯度贡献、重复加权bug或闭环因果证明；原训练器没有发现sampler与loss重复应用权重。

坐标推导和位置误差之间的限制见 COORDINATE_INTERPRETATION_ZH.md；后处理必须比较prior相对zero的质量，不能把目标尺度缩小误认成新机制成功。

