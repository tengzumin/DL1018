# 小残差先验定位、修复与复测：当前执行任务书

用户本轮指示：继续查清问题，完成必要修复后继续运行。当前先执行已有后续任务书的离线定位；训练与闭环重启必须基于本阶段实证另写具体单因素任务书。原三轮已经用尽，不篡改旧STOP、不把新运行记回旧轮次，也不默认重开72小时或无限预算。论文验收标准、X14、封存TEST和历史数据保护保持有效。

## 冻结身份

唯一模型：CORRECTED_DSSM14_SEED2026102001_FINAL60000。
模型来自 ../REFERENCE_FIX_FULL72_20261021_022342_313/corrected_reference_training_v1/corrected_pair_eval_v1/runs/r098/attempt_01/raw_run.mat，SHA256 f6fc258dbee1d33dbac608d94f690b23e5329d375d2806d9bb0601a667506ea5。
模型数组身份8de4d6548316c7b6f97382ecc9d5fbce8c00dbf6d10dc4187789b34c9205eb26；normalizer身份533aad9a2c66874cfa67f5d268661835e81e58b797cba7d6fc1c12d4013de5f0。

真实训练链是归档 corrected_pair_training/scripts/pair_workflow.py → teacher_data.py、teacher_models.py、fit_models.py；bank_from_g3注入已核验的X14/cache和原层次权重。训练仅Teacher B/POS_OFF，各源权重0.5；TRAIN1536、原训练VAL96。不是旧models/position/final_candidate/selection.json所指KAN/Student谱系。

上述四份脚本SHA依次为：

- pair_workflow.py：a82f92465587f64f60b3c3109875a480a8ae164bf8562670808347820dbc233b。
- teacher_data.py：3d6ec20f544cda2ec99c3bddf17e595a75683c90fbd6b542475d006b6d2badad。
- teacher_models.py：7d38948b0ea2f70ec7d1f3c433063cdc7f264080e5f717262e56ba4fd8ec1c22。
- fit_models.py：31a08407f5b3fe66b42a7e930925e5ae4cdabfa0a764c218356eedb82ca4e9ff。

源TRAIN index和已通过侧车身份沿上一阶段的TRAIN_COMPLETED_PHASE_PARENT_GATE.json、VAL_COMPLETED_PHASE_PARENT_GATE.json；所有源数据只读，不重建原始MAT或覆盖既有产物。

## 分工和执行顺序

主模型审核源码、端点/权重、数学与实际结果，作继续/修复/复测/停止决定。执行者沿用户最新要求使用Luna max；工具无速度档位核验接口。最多两位：

1. 实施者独占 reports/low_residual_objective_audit_20261022/。先冻结脚本及一条预检，再全TRAIN复算原目标和固定readout梯度，不更新参数。新增上限200MiB。
2. 表示复核者独占 reports/low_residual_representation_review_20261022/。先冻结model-specific表示诊断方案，再跑有界TRAIN检查；不做605184²全局距离搜索。新增上限100MiB。
3. 主审独占本目录，保存独立小批复算、审批与最终决定。新增上限20MiB。

只用PowerShell7，CPU单线程，不结束进程或抢锁。当前离线阶段0 optimizer、0新训练、0 Plant、0 TEST；不使用DEV72标签调门限。原训练VAL只在方案冻结后一次诊断，不作超参数搜索。

## 原目标复算契约

端点为0基31+5k，k=0..393，共394/运行、605184/全TRAIN；输入为时间正序的32个X14事件，目标取同端点的cache float32 y。层次权重先double计算、再转float32，与原训练相同。

```text
per_window = mean_axis SmoothL1(pred_raw/3, cache_y/3)
L = sum_i weight_i * per_window_i
minibatch estimator = (N/actual_batch_size) * sum_batch weight_i * per_window_i
```

不用beta/输出clip后的部署量冒充训练输出。已有侧车pred_raw是导出模型的double计算，须明示它与Torch float32训练路径的差异；小批纯Torch functional对照，不导入会启动训练/改路径的旧脚本。全量统计用同一冻结模型、同一cache标签，报告精度界限。

按任务、角色、风组、轴、形态阶段报告原loss贡献、样本质量、原始/clip目标质量、先验与零预测误差；按运行等权的描述另列，不能混为原层次目标。先验loss份额、零预测loss份额与梯度份额分别定义。

如果计算readout梯度，W为3×33且p=W phi：dL/dW=sum_i weight_i * clip((p_i−y_i)/3,−1,1) outer phi_i /9。用小批autograd核对，不创建optimizer。原Adam weight_decay=1e-5，data gradient与lambda W分开；不能把固定readout欧式梯度冲突冒称实际Adam、全网络方向或闭环因果。

## 表示诊断门槛

必须使用当前DSSM的32事件历史和33维phi；不能套用旧KAN仅末帧的逻辑。按task/role/phase控制、排除同运行邻接窗口，分别描述同风/跨风、W15和高频。预登记数值等价标准、候选端点、距离定义、最多查询/候选数及成本；不能在看到VAL后调阈值。保留连续距离/目标差，近邻相关不能证明数学不可辨识下界；未找到碰撞也不能证明信息充分。

## 后续修复与运行的决定

存在具体实现错误时，在新版本目录作最小修复并做隔离回归；实验条件或目标设计变化必须标为方法改动。若数据支持小残差损失折中且表示证据不构成明显混淆，再冻结一个候选和对应的单因素对照及训练/筛查预算；不是直接拼接B输出、扩大网络、搜seed或重开旧三轮。

冻结任务书必须有输入/代码/模型身份、seed2026102001、每配置最多60000 optimizer steps、固定12场机制门、失败解释、航次/存储与耗时上限。通过主审才启动，筛查失败不得继续72场。TEST仍需全部既有开发/理论/贡献门通过并另行冻结。证据不足则只做能区分假设的最小诊断，不以用户“继续”代替科学证据。
